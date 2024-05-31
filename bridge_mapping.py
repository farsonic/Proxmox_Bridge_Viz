import subprocess
import re
import json
import graphviz
import os

app = Flask(__name__)

def get_brctl_show_output():
    result = subprocess.run(['brctl', 'show'], stdout=subprocess.PIPE, text=True                                                                                                                                                           )
    return result.stdout

def parse_brctl_show(output):
    bridges = {}
    lines = output.splitlines()

    for line in lines:
        if re.match(r'^\w', line):  # Start of a new bridge entry
            parts = line.split()
            bridge_name = parts[0]
            bridges[bridge_name] = []
            if len(parts) > 3:  # Check if there's an interface on the same line
                interface = ' '.join(parts[3:])
                bridges[bridge_name].append(interface)
        elif re.match(r'^\s', line):  # Continuation line with an interface
            interface = line.strip()
            bridges[bridge_name].append(interface)

    return bridges

def get_interface_isolation_status(interface):
    try:
        with open(f'/sys/devices/virtual/net/{interface}/brport/isolated') as f:
            return int(f.read().strip())
    except IOError:
        return None

def run_lldpctl(interface):
    try:
        result = subprocess.run(['lldpctl', interface], stdout=subprocess.PIPE,                                                                                                                                                            text=True)
        return result.stdout
    except Exception as e:
        print(f"Error running lldpctl: {e}")
        return None

def parse_lldpctl_output(output):
    sysname = None
    portid = None
    vlans = []

    if output:
        lines = output.splitlines()
        for line in lines:
            if 'SysName:' in line:
                sysname = line.split('SysName:')[1].strip()
            elif 'PortID:' in line:
                portid = line.split('PortID:')[1].strip()
            elif 'VLAN:' in line:
                vlan_id = line.split(',')[0].split(':')[1].strip()
                vlans.append(vlan_id)

    return sysname, portid, vlans

def find_matching_bridge(bridges, ln_interface):
    pr_interface = ln_interface.replace('ln_', 'pr_')
    for bridge, interfaces in bridges.items():
        if pr_interface in interfaces:
            return bridge, pr_interface
    return None, None

def format_interface_label(interface, sysname, portid, vlans):
    label = interface
    if '.' in interface:
        base, vlan = interface.split('.')
        label = f"{interface} (VLAN {vlan})"
        if vlan in vlans:
            label += " [Configured]"
    if sysname and portid:
        label += f" (SYSNAME: {sysname}, PORTID: {portid})"
    return label

def determine_edge_color(interface, isolation_status):
    if 'vmbr' in interface:
        return 'darkblue'
    if isolation_status == 1:
        return 'red'
    elif isolation_status == 0:
        return 'darkgreen'
    elif '.' in interface:
        return 'darkblue'
    return 'black'

def get_interface_comment(interface):
    if interface.startswith('tap'):
        return 'KVM VM'
    elif interface.startswith('veth'):
        return 'LXC Container'
    return ''

def generate_graphviz(bridges, nominated_bridge, ln_interface, matching_bridge,                                                                                                                                                            pr_interface, switch_info):
    dot = graphviz.Digraph(comment='Bridge Connections')

    # Add the nominated bridge and its interfaces
    with dot.subgraph(name=f'cluster_{nominated_bridge}') as c:
        c.attr(label=f"{nominated_bridge} Bridge (User defined)", style='filled'                                                                                                                                                           , color='lightgrey')
        c.node(nominated_bridge, label=f"{nominated_bridge} Bridge", shape='box'                                                                                                                                                           )

        # Place veth or tap interfaces at the top
        for interface in sorted(bridges[nominated_bridge], key=lambda x: (x.star                                                                                                                                                           tswith('veth') or x.startswith('tap'), x)):
            lldp_output = run_lldpctl(interface.split('.')[0]) if interface.star                                                                                                                                                           tswith('enp') else None
            sysname, portid, vlans = parse_lldpctl_output(lldp_output)
            label = format_interface_label(interface, sysname, portid, vlans)
            comment = get_interface_comment(interface)
            if comment:
                label += f" ({comment})"
            c.node(interface, label=label)
            isolation_status = get_interface_isolation_status(interface)
            color = determine_edge_color(interface, isolation_status)
            if interface.startswith('veth') or interface.startswith('tap'):
                c.edge(interface, nominated_bridge, color=color)
            else:
                c.edge(nominated_bridge, interface, color=color)

    # Add the matching bridge and its interfaces
    with dot.subgraph(name=f'cluster_{matching_bridge}') as c:
        c.attr(label=f"{matching_bridge} Bridge (System defined)", style='filled                                                                                                                                                           ', color='lightblue')
        c.node(matching_bridge, label=f"{matching_bridge} Bridge", shape='box')

        # Connect pr_ interface to the top of the bridge
        lldp_output = run_lldpctl(pr_interface.split('.')[0]) if pr_interface.st                                                                                                                                                           artswith('enp') else None
        sysname, portid, vlans = parse_lldpctl_output(lldp_output)
        label = format_interface_label(pr_interface, sysname, portid, vlans)
        c.node(pr_interface, label=label)
        isolation_status = get_interface_isolation_status(pr_interface)
        color = determine_edge_color(pr_interface, isolation_status)
        c.edge(pr_interface, matching_bridge, color=color)

        # Connect other interfaces below
        for interface in bridges[matching_bridge]:
            if interface != pr_interface:
                lldp_output = run_lldpctl(interface.split('.')[0]) if interface.                                                                                                                                                           startswith('enp') else None
                sysname, portid, vlans = parse_lldpctl_output(lldp_output)
                label = format_interface_label(interface, sysname, portid, vlans                                                                                                                                                           )
                comment = get_interface_comment(interface)
                if comment:
                    label += f" ({comment})"
                c.node(interface, label=label)
                isolation_status = get_interface_isolation_status(interface)
                color = determine_edge_color(interface, isolation_status)
                if interface.startswith('veth') or interface.startswith('tap'):
                    c.edge(interface, matching_bridge, color=color)
                else:
                    c.edge(matching_bridge, interface, color=color)

    # Add the connection between ln_ and pr_ interfaces
    dot.edge(ln_interface, pr_interface, style='dashed')

    # Add switch information subgraph
    if switch_info:
        sysname, portid = switch_info
        with dot.subgraph(name='cluster_switch') as c:
            c.attr(label='Connected Switch', style='filled', color='lightyellow'                                                                                                                                                           )
            c.node('switch', label=f"Switch: {sysname}", shape='box')
            c.node('port', label=f"Port: {portid}", shape='ellipse')
            c.edge('port', 'switch')
        dot.edge(pr_interface, 'port', style='dashed')

    # Save the DOT source to a file
    dot_file = f'{nominated_bridge}_bridge_connections.dot'
    png_file = f'{nominated_bridge}_bridge_connections.png'
    pdf_file = f'{nominated_bridge}_bridge_connections.pdf'
    with open(dot_file, 'w') as f:
        f.write(dot.source)

    # Generate PNG and PDF from DOT file
    dot.render(filename=dot_file, format='png', cleanup=False)
    dot.render(filename=dot_file, format='pdf', cleanup=False)

    return dot, png_file, pdf_file, dot_file

@app.route('/')
def index():
    brctl_output = get_brctl_show_output()
    bridges = parse_brctl_show(brctl_output)
    save_bridges_to_json(bridges, 'bridges.json')
    return "Bridges have been saved to bridges.json. Go to /view to see the diag                                                                                                                                                           ram."

@app.route('/view')
def view():
    # Parse brctl show output every time to get the current state
    brctl_output = get_brctl_show_output()
    bridges = parse_brctl_show(brctl_output)

    nominated_bridge = request.args.get('bridge', 'vlan80')  # Default to 'vlan8                                                                                                                                                           0' if not specified

    if nominated_bridge not in bridges:
        return f"Bridge {nominated_bridge} not found in the output.", 404

    ln_interface = None
    for interface in bridges[nominated_bridge]:
        if interface.startswith('ln_'):
            ln_interface = interface
            break

    switch_info = None
    if ln_interface:
        for interface in bridges[nominated_bridge]:
            if interface.startswith('enp'):
                lldp_output = run_lldpctl(interface.split('.')[0])
                sysname, portid, _ = parse_lldpctl_output(lldp_output)
                if sysname and portid:
                    switch_info = (sysname, portid)
                    break

        matching_bridge, pr_interface = find_matching_bridge(bridges, ln_interfa                                                                                                                                                           ce)
        if matching_bridge:
            graph, png_file, pdf_file, dot_file = generate_graphviz(bridges, nom                                                                                                                                                           inated_bridge, ln_interface, matching_bridge, pr_interface, switch_info)
            svg_output = graph.pipe(format='svg').decode('utf-8')
            return render_template_string("""
            <html>
            <head>
                <script>
                    let refreshInterval;
                    function setRefresh() {
                        const interval = document.getElementById('refreshInterva                                                                                                                                                           l').value;
                        if (refreshInterval) {
                            clearInterval(refreshInterval);
                        }
                        if (interval !== '0') {
                            refreshInterval = setInterval(() => {
                                window.location.reload();
                            }, interval * 1000);
                        }
                    }
                    function pauseRefresh() {
                        if (refreshInterval) {
                            clearInterval(refreshInterval);
                            refreshInterval = null;
                        }
                    }
                </script>
            </head>
            <body onload="setRefresh()">
                <h1>Bridge Connections</h1>
                <div>{{ svg_output|safe }}</div>
                <a href="/download?file={{ png_file }}">Download PNG</a><br>
                <a href="/download?file={{ pdf_file }}">Download PDF</a><br>
                <a href="/download?file={{ dot_file }}">Download DOT</a><br>
                <label for="refreshInterval">Refresh interval (seconds):</label>
                <input type="number" id="refreshInterval" name="refreshInterval"                                                                                                                                                            value="10" min="0" onchange="setRefresh()">
                <button onclick="pauseRefresh()">Pause Refresh</button>
            </body>
            </html>
            """, svg_output=svg_output, png_file=png_file, pdf_file=pdf_file, do                                                                                                                                                           t_file=dot_file)
        else:
            return f"No matching bridge found for {ln_interface}.", 404
    else:
        return f"No ln_ interface found in bridge {nominated_bridge}.", 404

@app.route('/download')
def download():
    file_path = request.args.get('file')
    if file_path and os.path.exists(file_path):
        return send_file(file_path, as_attachment=True, download_name=os.path.ba                                                                                                                                                           sename(file_path))
    else:
        return abort(404, description="File not found")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

## Visualise Proxmox SDN Bridge interfaces

A quick tool to allow users to view the connections between Linux bridges on a Proxmox VE host. 

Start the webserver directly on the proxmox server 

```
root@pve1:/var/tmp# python3 bridge_mapping.py
 * Serving Flask app 'bridge_mapping'
 * Debug mode: on
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://192.168.0.223:5000
Press CTRL+C to quit
 * Restarting with stat
 * Debugger is active!
 * Debugger PIN: 577-998-005
```

This will start a webserver on port 5000 that will allow the user to query a specific bridge using the following syntax. 

```
http://192.168.0.223:5000/view?bridge=BRIDGNAME
```

### Example output 

![image](https://github.com/farsonic/Proxmox_Bridge_Viz/assets/5546448/a5f10164-e289-4f79-84da-bfca8d6cb9a2)

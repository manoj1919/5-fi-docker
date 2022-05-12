# 5-fi-docker
Clone the git

then run

`cd 5-fi-docker/ueransim`

first build UERANSIM docker images. To do that run:

`make`

then build free5gc and run as [shown here](https://github.com/manoj1919/5-fi-docker/tree/master/free5gc-compose#readme)

# python-api
Pre-requisites:
Python3
flask (pip3 install flask)

go to flask-api folder and run python_api.py like below

`cd flask-api`
`sudo python3 python_api.py <port number>`

The following are the url calls you can make:
 
 1. List all containers:
 `<ip.address>:<port>/monitor_home`
 
 2. Display container stats:
 `<ip.address>:<port>/monitor_nf/<container_id>`
 
 3. List all gNBs:
` <ip.address>:<port>/manage_ran/list_ran_nodes`
  
The steps in the process of handover in the demo and corresponding url calls:
  
  1. Go to source gNB monitor page by following url:

 `<ip.address>:<port>/monitor_nf/<source_gnb_container_id>`
 
 2. Click on handover-prepare button that opens a popup of avaialble ues to handover. The url to get available ues to populate in popup:
  
 `<ip.address>:<port>/uelist/<source_gnb_container_id>`
 
 3. select one of the ues in the popup and click ok. this should call following url:
 
 `<ip.address>:<port>/handover_prepare/<source_gnb_container_id>?ueid= <ueid of selected ue in the popup>`
 
 4. Go to target gNB monitor page by follwoing url:
 
 `<ip.address>:<port>/monitor_nf/<target_gnb_container_id>`
 
 5. click on path switch request button. A popup will appear.That should call following url to populate popup:
 
 `<ip.address>:<port>/list_pathsw`
 
 6. select one of the items in the popup, that should call following url:
 
 `<ip.address>:<port>/pathsw/<target_gnb_container_id>?id=<id of selected entry in the popup>`
  

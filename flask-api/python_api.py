import docker
import datetime
import shutil
import time
from flask import Flask, request, jsonify
import stats
import measurements
import threading
import sys, os
import handover_db
import packets
import copy
app= Flask(__name__)
client=docker.from_env()
stop=0

def get_logs(client,id):
    for container in client.containers.list():
        if id in str(container.id):
            logs = container.logs().decode("utf-8")
            return logs

def num_PDUsessions(client,id):
    for container in client.containers.list():
        if id in str(container.id):
            run=container.exec_run('nr-cli --dump')
            temp1=(run.output.decode("utf-8")).split("\n")
            ue_imsi=temp1[0]
            temp1=container.exec_run('nr-cli ' + ue_imsi + ' -e ps-list')
            temp2=(temp1.output.decode("utf-8")).split("PDU Session")
            st = "state: PS-ACTIVE"
            res = [i for i in temp2 if st in i]
            return len(res)

def get_IPaddress(client,id):
    container=client.containers.list(filters={"id":id})
    if len(container)==0:
        print ("no container running with given id")
        return
    try:
        ip_add = container[0].attrs["NetworkSettings"]["Networks"]["free5gc-compose_privnet"]["IPAddress"]
    except: 
        print ("Error in getting IP address")
    return ip_add    

def ues_served(client, id):
    list_ue_containers=[]
    for container in client.containers.list():
        if 'ue' in container.name:
            run = container.exec_run('echo "$GNB_HOSTNAME"')
            out=run.output.decode("utf-8")
            if id.name in str(out):
                list_ue_containers.append(container)
    return list_ue_containers


#################################################
@app.route('/start_demo')
def docker_start():
    pwd=os.getcwd()
    os.chdir('../free5gc-compose')
    os.system('docker-compose up -d')
    os.chdir(pwd)
    return "success",200
@app.route('/restart_demo')
def docker_restart():
    pwd=os.getcwd()
    shutil.copy('../free5gc-compose/config/uerouting_orig.yaml','../free5gc-compose/config/uerouting.yaml')
    os.chdir('../free5gc-compose')
    os.system('docker-compose down')
    os.system('docker-compose up -d')
    #stop_loop()
    os.chdir(pwd)
    return jsonify({"response":"success"}), 200
@app.route('/stop_demo')
def docker_stop():
    pwd=os.getcwd()
    shutil.copy('../free5gc-compose/config/uerouting_orig.yaml','../free5gc-compose/config/uerouting.yaml')
    os.chdir('../free5gc-compose')
    os.system('docker-compose down --remove-orphans')
    #stop_loop()
    os.chdir(pwd)
    return jsonify({"response":"success"}), 200    
####################################################

list_nfs=['nrf','amf','upf','gnb','ue','udm','udr','smf','ausf','nssf','pcf']    

@app.route('/monitor_home')
def monitor_home():
    monitor_home_page={"count_active_cells":0,"count_available_cells":0,"malfunction":"Everything is working fine","List_NFs":[],"counts_in_topo":{},"traffic_data": {\
        'title': 'Traffic served over-time','x-title':'Time','y-title':'User traffic served ','data':[]}}
    #NF_details={"type":'',"name":'', 'count': 0, "containerid":"", "internet":""}
    counts_details={"nfs":0,"upfs":0, 'gnbs': 0, "rrhs":0, "ues":0}
    bytesdata={}
    for container in client.containers.list():
        NF_details={}
        if 'port' in str(container.name) or 'mongo' in str(container.name) or 'webui' in str(container.name) or 'mytb' in str(container.name):
            continue
        NF_details["name"]=container.name
        match = next((x for x in list_nfs if x in container.name), False)
        if match==False:
            continue
        NF_details["type"] = match#remove_numbers(container.name)
        NF_details["containerid"]=container.id
        NF_details["shortid"]=container.short_id
        NF_details["count"] =len(client.containers.list(filters={'name':NF_details['type']+'.*'}))  
        if "branching" in str(container.name):
            NF_details["internet"] = 'BU'
        if "anchor-upf1" in str(container.name):
            NF_details["internet"] = 'yes'    
        if "anchor-upf2" in str(container.name):
            NF_details["internet"] = 'no'                                
        monitor_home_page["List_NFs"].append(NF_details)
        if "free5gc" in str(container.image):
            counts_details["nfs"]+=1
        if 'ue' in str(container.name):
            data=measurements.read(container.name)
            for row in data:
                if row[0] in bytesdata.keys():
                    bytesdata[row[3]].append(int(row[-1].strip())+int(row[-2].strip()))
                else:
                    bytesdata[row[3]]=[(int(row[-1])+int(row[-2]))]
    for key in bytesdata.keys():
        monitor_home_page["traffic_data"]["data"].append({key:bytesdata[key]})
    counts_details["upfs"]= len(client.containers.list(filters={'name':'upf.*'}))
    counts_details["gnbs"]= len(client.containers.list(filters={'name':'gnb.*'}))
    counts_details["rrhs"]= len(client.containers.list(filters={'name':'gnb.*'}))
    counts_details["ues"]= len(client.containers.list(filters={'name':'ue.*'}))
    counts_details["edges"]= 1
    monitor_home_page["counts_in_topo"]=counts_details
    monitor_home_page["count_active_cells"]=counts_details["gnbs"]
    monitor_home_page["count_available_cells"]=counts_details['gnbs']
    return jsonify(monitor_home_page),200


@app.route('/monitor_nf/<id>')
def monitor_nf(id):
    #dictionaries for json
    chart_dict={"title":'','x-axis_title':'','y-axis_title':'','data':[]}
    chart1_dict=copy.deepcopy(chart_dict)
    chart2_dict=copy.deepcopy(chart_dict)
    chart3_dict=copy.deepcopy(chart_dict)
    chart1_dict["title"] = "CPU Usage (percentage used)"
    chart1_dict["x-axis_title"]= "Time"
    chart1_dict["y-axis_title"]= "Percentage used"
    chart2_dict["title"] = "Memory Usage (percentage used)"
    chart2_dict["x-axis_title"]= "Time"
    chart2_dict["y-axis_title"]= "Percentage used"
    chart3_dict["title"] = "Network Usage (Bytes)"
    chart3_dict["x-axis_title"]= "Time"
    chart3_dict["y-axis_title"]= "MB"
    stats_data={ "time_stamp":'',
    "cpu_percent_usage":0,
    "mem_percent_usage":0,
    "Transmit_bytes":0,
    "Received_bytes":0}
    monitor_nf={"name_of_nf":'',
    "no_PDUsessions":0,
    "no_UEsserved":0,
    "no_ActiveUEs":0,
    "State":'',
    "Health":'',
    "Handover-prepare_button":'False',
    "Path_sw_req_button":'False',
    "DNN":'internet',
    "NF_stats":{"chart1":chart_dict},
    "NF_Logs":'',
    "NF_packets":''}
    ct = datetime.datetime.now()
    container=client.containers.list(filters={"id":id})
    if len(container)==0:
        print ("no container running with given id")
        return   
    state= 'active' 
    health= 'good'
    DNN = 'internet'
    #no_PDUsessions=0
    Management_IP=''
    no_servedUEs=0
    no_ActiveUEs=0
    monitor_nf["name_of_nf"]=container[0].name
    if 'upf' in container[0].name:
        DNN = 'internet'      
    #if 'ue' in container[0].name:
        #no_PDUsessions = num_PDUsessions(client,container[0].id)
    if 'gnb' in container[0].name:
        no_servedUEs = measurements.get_num_ActiveUEs(client,container[0].id)
        no_ActiveUEs = measurements.get_num_ActiveUEs(client,container[0].id)
        monitor_nf["Handover-prepare_button"]='True'
        monitor_nf["Path_sw_req_button"]='True'
        chart1_dict["title"] = "Average DL throughput of connected UEs (Mbps)"
        chart1_dict["x-axis_title"]= "Time"
        chart1_dict["y-axis_title"]= "Mbps"
        chart2_dict["title"] = "Average UL throughput of connected UEs (Mbps)"
        chart2_dict["x-axis_title"]= "Time"
        chart2_dict["y-axis_title"]= "Mbps"
        chart3_dict["title"] = "Average Latency of connected UEs (ms)"
        chart3_dict["x-axis_title"]= "Time"
        chart3_dict["y-axis_title"]= "milliseconds"
        no_PDUsessions = 0
        for ue in ues_served(client,container[0]):
            no_PDUsessions += num_PDUsessions(client,ue.id)
    Management_IP = get_IPaddress(client,container[0].id)
    
    # res = get_stats(client,container[0].id)
    #monitor_nf["no_PDUsessions"]=no_PDUsessions
    monitor_nf["Management_IP"]=Management_IP
    monitor_nf["no_UEsserved"]=no_servedUEs
    monitor_nf["no_ActiveUEs"]=no_ActiveUEs
    monitor_nf["State"]=state
    monitor_nf["Health"]=health
    monitor_nf["DNN"]=DNN
    monitor_nf["NF_Logs"]=get_logs(client,id)
    if 'gnb' not in container[0].name:
        raw_stats=stats.read_stats_db(id)    
        for row in raw_stats:
            chart1_dict["data"].append({row[2]:row[3]})
            chart2_dict["data"].append({row[2]:row[4]})
            chart3_dict["data"].append({row[2]:[row[5],row[6]]})
    if 'gnb' in container[0].name:
        meas=measurements.read(container[0].name)
        ul_dict={}
        dl_dict={}
        lat_dict={}
        for row in meas:
            if row[3] not in ul_dict.keys():
                ul_dict[row[3]]=[row[4]]
                dl_dict[row[3]]=[row[5]]
                lat_dict[row[3]]=[row[6]]
            else:
                ul_dict[row[3]].append(row[4])
                dl_dict[row[3]].append(row[5])
                lat_dict[row[3]].append(row[6])
        for key in ul_dict.keys():
            chart1_dict["data"].append({key:((sum(ul_dict[key])/len(ul_dict[key]))/1000000)})
            chart2_dict["data"].append({key:((sum(dl_dict[key])/len(dl_dict[key]))/1000000)})
            chart3_dict["data"].append({key:((sum(lat_dict[key])/len(lat_dict[key])))})
    monitor_nf["NF_stats"]={"chart1":chart1_dict,"chart2":chart2_dict,"chart3":chart3_dict}
    monitor_nf["NF_packets"]=packets.get_packets(container[0].name)
    return jsonify(monitor_nf),200

@app.route('/monitor_nf_basic/<id>')
def monitor_nf_basic(id):
    #dictionaries for json
    monitor_nf={"name_of_nf":'',
    "no_PDUsessions":0,
    "no_UEsserved":0,
    "no_ActiveUEs":0,
    "State":'',
    "Health":'',
    "Handover-prepare_button":'False',
    "Path_sw_req_button":'False',
    "DNN":'internet',
    "Management_IP":''
    }
    container=client.containers.list(filters={"id":id})
    if len(container)==0:
        print ("no container running with given id")
        return   
    state= 'active' 
    health= 'good'
    #no_PDUsessions=0
    Management_IP=''
    no_servedUEs=0
    no_ActiveUEs=0
    monitor_nf["name_of_nf"]=container[0].name
    if 'gnb' in container[0].name:
        no_servedUEs = measurements.get_num_ActiveUEs(client,container[0].id)
        no_ActiveUEs = measurements.get_num_ActiveUEs(client,container[0].id)
        monitor_nf["Handover-prepare_button"]='True'
        monitor_nf["Path_sw_req_button"]='True'
        no_PDUsessions = 0
        for ue in ues_served(client,container[0]):
            no_PDUsessions += num_PDUsessions(client,ue.id)
    Management_IP = get_IPaddress(client,container[0].id)
    monitor_nf["Management_IP"]=Management_IP
    monitor_nf["no_UEsserved"]=no_servedUEs
    monitor_nf["no_ActiveUEs"]=no_ActiveUEs
    monitor_nf["State"]=state
    monitor_nf["Health"]=health
    return jsonify(monitor_nf),200

@app.route('/monitor_nf_logs/<id>')
def monitor_nf_logs(id):
    #dictionaries for json
    
    monitor_nf={ "NF_Logs":''
   }
    container=client.containers.list(filters={"id":id})
    if len(container)==0:
        print ("no container running with given id")
        return   
    monitor_nf["NF_Logs"]=get_logs(client,id)
    return jsonify(monitor_nf),200

@app.route('/monitor_nf_stats/<id>')
def monitor_nf_stats(id):
    #dictionaries for json
    chart_dict={"title":'','x-axis_title':'','y-axis_title':'','data':[]}
    chart1_dict=copy.deepcopy(chart_dict)
    chart2_dict=copy.deepcopy(chart_dict)
    chart3_dict=copy.deepcopy(chart_dict)
    chart1_dict["title"] = "CPU Usage"
    chart1_dict["x-axis_title"]= "Time"
    chart1_dict["y-axis_title"]= "Percentage used"
    chart2_dict["title"] = "Memory Usage"
    chart2_dict["x-axis_title"]= "Time"
    chart2_dict["y-axis_title"]= "Percentage used"
    chart3_dict["title"] = "Network Usage"
    chart3_dict["x-axis_title"]= "Time"
    chart3_dict["y-axis_title"]= "MB"
    monitor_nf={
    "NF_stats":{"chart1":chart_dict}
    }
    container=client.containers.list(filters={"id":id})
    if len(container)==0:
        print ("no container running with given id")
        return  
    if 'gnb' in container[0].name:
        chart1_dict["title"] = "Average DL throughput of connected UEs"
        chart1_dict["x-axis_title"]= "Time"
        chart1_dict["y-axis_title"]= "Mbps"
        chart2_dict["title"] = "Average UL throughput of connected UEs"
        chart2_dict["x-axis_title"]= "Time"
        chart2_dict["y-axis_title"]= "Mbps"
        chart3_dict["title"] = "Average Latency of connected UEs"
        chart3_dict["x-axis_title"]= "Time"
        chart3_dict["y-axis_title"]= "milliseconds"
    if 'gnb' not in container[0].name:
        raw_stats=stats.read_stats_db(id)    
        for row in raw_stats:
            chart1_dict["data"].append({row[2]:row[3]})
            chart2_dict["data"].append({row[2]:row[4]})
            chart3_dict["data"].append({row[2]:[row[5],row[6]]})
    if 'gnb' in container[0].name:
        meas=measurements.read(container[0].name)
        ul_dict={}
        dl_dict={}
        lat_dict={}
        for row in meas:
            if row[3] not in ul_dict.keys():
                ul_dict[row[3]]=[row[4]]
                dl_dict[row[3]]=[row[5]]
                lat_dict[row[3]]=[row[6]]
            else:
                ul_dict[row[3]].append(row[4])
                dl_dict[row[3]].append(row[5])
                lat_dict[row[3]].append(row[6])
        for key in ul_dict.keys():
            chart1_dict["data"].append({key:((sum(ul_dict[key])/len(ul_dict[key]))/100000)})
            chart2_dict["data"].append({key:((sum(dl_dict[key])/len(dl_dict[key]))/100000)})
            chart3_dict["data"].append({key:((sum(lat_dict[key])/len(lat_dict[key]))/100000)})
    monitor_nf["NF_stats"]={"chart1":chart1_dict,"chart2":chart2_dict,"chart3":chart3_dict}
    return jsonify(monitor_nf),200

@app.route('/monitor_nf_packets/<id>')
def monitor_nf_packets(id):
    #dictionaries for json
    monitor_nf={"NF_packets":''}
    container=client.containers.list(filters={"id":id})
    monitor_nf["NF_packets"]=packets.get_packets(container[0].name)
    return jsonify(monitor_nf),200

@app.route("/stop")
def stop_loop():
    stats.kill_stats_collection()
    measurements.kill_meas_collection()
    return "successfuly stopped the loop",200


#run nr-cli <gnb-id> and run list ues that we will give back
@app.route("/uelist/<id>")
def list_ues(id):
    container=client.containers.list(filters={"id":id})[0]
    run=container.exec_run('nr-cli --dump')
    temp1=(run.output.decode("utf-8")).split("\n")
    gnb_id=temp1[0]
    run=container.exec_run('nr-cli ' + gnb_id + ' -e ue-list')
    temp1=run.output.decode("utf-8").split("\n")
    ue_list=[]
    ue_details={}
    for item in temp1:
        if "ue-id" in item:
            if len(ue_details.keys())>0:
                ue_list.append(ue_details)
            ue_details={}
        try:
            ue_details[item.split(':')[0]]= item.split(':')[1]
        except IndexError:
            continue
    ue_list.append(ue_details)
    return jsonify({'UElist':ue_list}),200
    
@app.route("/handover_prepare/<id>") #handover-prepare/<gnb-containerid and gnb-id and ueid>
# run handover prepare command
def handover_prepare(id):
    url_params=request.args
    container=client.containers.list(filters={"id":id})[0]
    run=container.exec_run('nr-cli --dump')
    temp1=(run.output.decode("utf-8")).split("\n")
    gnb_id=temp1[0]
    cmd='nr-cli ' + gnb_id + ' -e "handover-prepare ' + url_params['ueid']+'"'
    run=container.exec_run(cmd)
    temp1=run.output.decode("utf-8")
    details={}
    if 'copy for handover' in temp1:
        details={}
        raw_str=temp1.split('copy for')[-1]
        for item in raw_str.split('\n'):
            if ':' in item:
                if '[debug]' in item:
                    item=item.split('[debug]')[-1]
                details[item.split(':')[0].strip()]= item.split(':')[1].strip()
    
    return jsonify({'handover details':handover_db.push(details[list(details.keys())[0]],url_params['ueid'],container.name)}),200


@app.route("/list_pathsw")
def list_path_switch():
    return jsonify(handover_db.read_contents()),200


# run path switch    
@app.route("/pathsw/<gnb_containerid>")
def path_switch(gnb_containerid):
    url_params=request.args
    handover_text=handover_db.pop(url_params['id'])
    container=client.containers.list(filters={"id":gnb_containerid})[0]
    run=container.exec_run('nr-cli --dump')
    temp1=(run.output.decode("utf-8")).split("\n")
    gnb_id=temp1[0]
    cmd='nr-cli ' + gnb_id + ' -e "handover ' + handover_text+'"'
    run=container.exec_run(cmd)
    temp1=run.output.decode("utf-8")
    return "Handover success",200

#manage ran-list RAN nodes
@app.route('/manage_ran/list_ran_nodes')
def list_ran():
    list_nodes={}
    for container in client.containers.list():
        if 'gnb' in container.name:
            node_attrs={"Availability":"Green",
            "cloud connectivity":"Online",
            "Site name": "Local",
            "Site Role": "Macro cell",
            "Device Model": "UERANSIM-gNB",
            "Serial number": "",
            "Bandwidth Tier": 500,
            "Management IP":""}
            run=container.exec_run('nr-cli --dump')
            temp1=(run.output.decode("utf-8")).split("\n")
            gnb_id=temp1[0]
            node_attrs["Serial number"] = gnb_id
            ip_add = container.attrs['NetworkSettings']['Networks']['free5gc-compose_privnet']['IPAddress']
            node_attrs["Management IP"] = ip_add
            list_nodes[container.name] = node_attrs
            node_attrs={}
    return jsonify (list_nodes),200
    
#subscriber management -insert and view subscribers
@app.route('/manage_ran/subscribers',methods = ['GET', 'POST','DELETE'])
def manage_subscribers():
    import subscribers_db
    if request.method=='GET':
        return jsonify(subscribers_db.view_subscribers()), 200
    data=request.form
    if request.method=='POST':
        list_imsis=subscribers_db.view_subscribers()
        for key in list_imsis:
            if data["ueId"]==list_imsis[key]["ueId"]:
                return "User already exists"
        subscribers_db.insert_subscriber(data)
        return jsonify(subscribers_db.view_subscribers()), 201
    if request.method=='DELETE':
        subscribers_db.delete_subscriber({'ueId':data['ueId']})
        return jsonify(subscribers_db.view_subscribers()),200
@app.route('/manage_ran/subscribers/<ueId>',methods = ['PUT'])
def delete_subscriber(ueId):
    import subscribers_db
    if request.method=='PUT':
        new_data=request.form
        subscribers_db.modify_subscriber({'ueId':ueId},new_data)
        return jsonify(subscribers_db.view_subscribers()),200
    else:
        return "Bad request",400
        
#List measurements for a UE
@app.route('/manage_ran/uemeasurements/<id>')
def UE_measurements(id):
    #dictionaries for json
    Meas_Data={"name_of_nf":'',
    "all_data":[]}
    measurements_data={
    "time_stamp":'',
    "dl_thp":0,
    "ul_thp":0,
    "latency":0,
    "tx_bytes":0,
    "rx_bytes":0,
    }
    container=client.containers.list(filters={"id":id})
    if len(container)==0:
        print ("no container running with given id")
        return    
    result = measurements.read(container[0].name)
    for row in result:
        measurements_data["time_stamp"]=row[3]
        measurements_data["dl_thp"]=row[4]
        measurements_data["ul_thp"]=row[5]
        measurements_data["latency"]=row[6] 
        measurements_data["tx_bytes"]=row[7] 
        measurements_data["rx_bytes"]=row[8] 
        Meas_Data["all_data"].append(measurements_data)
        Meas_Data["name_of_nf"] = row[0]
        measurements_data={}
    return jsonify(Meas_Data),200

@app.route('/ping/<name>')
def ping_Latency(name):
    #dictionaries for json    
    latency_values={ "Latency":''
   }
    container=client.containers.list(filters={"name":name})
    if len(container)==0:
        print ("no container running with given name")
        return   
    latency_values["Latency"]=measurements.get_PingLatency(client,name)
    return jsonify(latency_values),200

@app.route('/suggested_actions_core')
def sug_act_core():
    check=measurements.read_actions()
    return jsonify(check),200

@app.route('/execute_sug_action')
def exec_act_core():
    shutil.copy('../free5gc-compose/config/uerouting_changed.yaml','../free5gc-compose/config/uerouting.yaml')
    client_lowlevel = docker.APIClient(base_url='unix://var/run/docker.sock')
    container=client.containers.list(filters={"name":"branching-upf"})[0]
    client_lowlevel.restart(container.id)
    container=client.containers.list(filters={"name":"smf"})[0]
    client_lowlevel.restart(container.id)
    time.sleep(1)
    container=client.containers.list(filters={"name":"ue1"})[0]
    #run=container.exec_run('nr-cli --dump')
    #temp1=(run.output.decode("utf-8")).split("\n")
    #ue_imsi=temp1[0]
    #temp1=container.exec_run('nr-cli ' + ue_imsi + ' -e ps-release-all')
    #time.sleep(10)
    #temp1=container.exec_run('nr-cli ' + ue_imsi + ' -e ps-establish')
    # container=client.containers.list(filters={"name":"ue1"})[0]
    client_lowlevel.restart(container.id)
    measurements.pop_latency()
    return jsonify({'response':'userplane change success'}),200
@app.route('/pop_sug_action')
def pop_sug_action():
    measurements.pop_latency()
    return "success",200

# start a thread to dump packet data and stats data into db

stats_thread=threading.Thread(target=stats.get_stats, args=(client,), name="docker_stats")
stats_thread.start()
handover_db.drop_db()
measurements_thread=threading.Thread(target=measurements.get_measurements, args=(client,), name="docker_measurements")
measurements_thread.start()

if len(sys.argv) < 2:
    print("Provide port number properly")
    stop=1
    exit()
if len(sys.argv) >2:
    if sys.argv[2] =='stop':
        stop_loop()

#start flask app
if __name__=='__main__':
    app.run(host = '0.0.0.0', port=sys.argv[1])
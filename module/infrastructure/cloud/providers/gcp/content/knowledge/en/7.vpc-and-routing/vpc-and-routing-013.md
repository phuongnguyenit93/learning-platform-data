# Hands-On: Building a Private VPC for a Multi-Tier Application

In the **CLOUD_PROVIDERS_GCP** module, we use Google Cloud to organize projects, protect resources with IAM and VPCs, deploy services on Compute Engine, GKE, or Cloud Run, store data, automate releases, and monitor reliability as well as cost. This hands-on lab in the **VPC and Routing** chapter builds a private **Virtual Private Cloud (VPC)** network, then places three application tiers into separate subnets to verify traffic paths and access boundaries.

Instead of merely drawing diagrams, you will create a custom mode VPC, three regional subnets, firewall rules, Cloud NAT, three VMs, and small HTTP services. Afterward, you will test both **allowed** and **denied** connections, inspect the configuration via gcloud, and clean up resources to prevent unexpected charges.

> **Lab scope:** The data tier is **simulated using an HTTP file-serving service**, allowing you to observe networking without provisioning a real database. This is a learning environment; the public HTTP examples, network-tag-based rules, and sample data must be hardened for TLS, IAM, data security, and HA before production use.

## 1. Requirements and Expected Outcomes

Upon completing this lesson, you will be able to:

1. Explain how a **VPC has global scope**, while **subnets have regional scope** and VMs belong to a zone.
2. Create a custom mode VPC with three **non-overlapping** private IPv4 ranges.
3. Open only the **Internet → Web → App → Data** path, rather than letting all tiers talk freely to one another.
4. Deploy App and Data VMs **without external IPs**, providing Internet egress via **Cloud NAT** when downloading packages.
5. Connect for administration via **Identity-Aware Proxy (IAP) TCP forwarding** instead of opening SSH to the entire Internet.
6. Verify routes, firewalls, IPs, and services, and test an intentionally blocked connection.
7. Understand how to extend the lab to Cloud SQL, GKE, and Cloud Run, and how to manage costs and resources.

### 1.1. Three-Tier Model

| Tier | VM name | Subnet | Fixed internal IP in example | Service | Accessible from |
| --- | --- | --- | --- | --- | --- |
| **Web / presentation** | `lab3-web` | `lab3-web-subnet` | `10.70.10.10` | Nginx port 80 | Internet (lab HTTP only), IAP SSH |
| **App / business logic** | `lab3-app` | `lab3-app-subnet` | `10.70.20.10` | Python HTTP API port 8080 | Web subnet only and IAP SSH |
| **Data / simulated** | `lab3-data` | `lab3-data-subnet` | `10.70.30.10` | HTTP sample-file reader port 9090 | App subnet only and IAP SSH |

All VMs sit in **one sample zone** within region `asia-southeast1` for simplicity; their subnets belong to that same **region**. VPC `lab3-vpc` has global scope, allowing subnets to be added in other regions if needed. The `10.70.x.x` addresses are examples: before running in a real project, check against existing network ranges, VPNs, Shared VPCs, and other connections.

~~~mermaid
flowchart TB
    User["Internet browser"] -->|HTTP :80, lab| Web["Web VM / Nginx<br/>10.70.10.10"]
    Web -->|HTTP :8080| App["App VM / Python<br/>10.70.20.10"]
    App -->|HTTP :9090| Data["Data VM / sample service<br/>10.70.30.10"]
    IAP["Administrator via IAP"] -. "SSH :22" .-> Web
    IAP -. "SSH :22" .-> App
    IAP -. "SSH :22" .-> Data
    subgraph VPC["VPC lab3-vpc — global"]
      subgraph Region["Region asia-southeast1"]
        Web
        App
        Data
      end
    end
    NAT["Cloud NAT — regional"] -->|"Egress when needed"| Internet["Internet"]
    App -. "Via NAT" .-> NAT
    Data -. "Via NAT" .-> NAT
~~~

This diagram shows **permitted flows**; it does not imply all other network paths are automatically blocked merely by splitting subnets. Subnets handle IP allocation and routing; **firewalls** are the layer controlling connectivity between VMs. In this lab, ingress rules are explicitly scoped while egress uses the VPC's default configuration.

### 1.2. Network Parameters

| Resource | Scope | Lab value |
| --- | --- | --- |
| VPC | Global | `lab3-vpc`, custom mode |
| Region | Regional | `asia-southeast1` |
| Zone | Zonal | `asia-southeast1-b` (verify sample machine availability) |
| Web subnet | Regional | `10.70.10.0/24` |
| App subnet | Regional | `10.70.20.0/24` |
| Data subnet | Regional | `10.70.30.0/24` |
| VM | Zonal | Three Ubuntu `e2-small` VMs with default disks |
| NAT gateway | Regional | `lab3-nat` on `lab3-router` |

This is an educational topology and does not imply these machine types and regions are always cheapest, free, or compliant with data residency laws. Choose a dedicated lab project and clean up resources at the end.

## 2. Preparing Environment, Permissions, and Costs

You need:

- A **Google Cloud project** with an active Cloud Billing account permitted to create VMs, VPCs, subnets, firewalls, and Cloud NAT. Never use a production project.
- **gcloud CLI** installed and authenticated; command examples use Bash on Linux/macOS or Cloud Shell. In PowerShell, variable syntax differs.
- Appropriate IAM permissions to enable APIs, create Compute Engine/networking resources, manage firewalls, and use IAP. SSH via IAP may require `roles/iap.tunnelResourceAccessor` along with VM login permissions (e.g., OS Login when configured), instance access permissions, and related settings.
- An approved budget: **VMs, persistent disks, external IPv4s, Cloud NAT, network traffic**, and logs can incur charges. Budget alerts help monitor spend but do not cap billing automatically.
- An environment free of existing resources with conflicting names or IP ranges. If they already exist, stop and choose different names/ranges aligned with your organization's IP plan.

The **resource creation/deletion** commands below are for learners to run in an approved lab project. This guide presents the commands; reading it does not create infrastructure automatically.

### 2.1. Set Variables and Confirm Project

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export REGION="asia-southeast1"
export ZONE="asia-southeast1-b"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project
gcloud projects describe "$PROJECT_ID" --format="value(projectId)"
~~~

Replace `YOUR_LAB_PROJECT_ID` with your verified Project ID. Selecting the right project in the CLI is critical: if it points to production, all subsequent examples could mutate the wrong project.

### 2.2. Check APIs and Zonal Capacity

~~~bash
gcloud services list --enabled \
  --filter="name:(compute.googleapis.com OR iap.googleapis.com)"

gcloud compute machine-types describe e2-small --zone="$ZONE"
~~~

If the Compute Engine API or IAP API is not yet enabled, an authorized user can enable them in the lab project:

~~~bash
gcloud services enable compute.googleapis.com iap.googleapis.com
~~~

Enabling APIs may require permissions such as `serviceusage.services.enable`. Enabled APIs do not guarantee all quotas, limits, or VM creation permissions are sufficient. If your organization uses OS Login, ensure OS Login permissions and configurations are in place before attempting SSH.

## 3. Create Custom Mode VPC and Three Subnets

### 3.1. Create the VPC Network

~~~bash
gcloud compute networks create lab3-vpc \
  --subnet-mode=custom \
  --bgp-routing-mode=regional
~~~

**Why choose custom mode?** We want explicit control over where subnets are placed and each tier's IP range. Creating a VPC in custom mode generates no subnets automatically. `--bgp-routing-mode=regional` governs how relevant **dynamic routes** behave in the VPC; no BGP is configured in this lab.

### 3.2. Create Web, App, and Data Subnets in the Same Region

~~~bash
gcloud compute networks subnets create lab3-web-subnet \
  --network=lab3-vpc \
  --region="$REGION" \
  --range=10.70.10.0/24

gcloud compute networks subnets create lab3-app-subnet \
  --network=lab3-vpc \
  --region="$REGION" \
  --range=10.70.20.0/24 \
  --enable-private-ip-google-access

gcloud compute networks subnets create lab3-data-subnet \
  --network=lab3-vpc \
  --region="$REGION" \
  --range=10.70.30.0/24 \
  --enable-private-ip-google-access
~~~

`--enable-private-ip-google-access` enables eligible access to Google APIs from resources without external IPs; it **does not replace Cloud NAT for general Internet connectivity**. In this lab, App and Data will use NAT when reaching public package repositories.

### 3.3. Verify Locations and CIDRs

~~~bash
gcloud compute networks describe lab3-vpc \
  --format="yaml(name,subnetworks,autoCreateSubnetworks,routingConfig)"

gcloud compute networks subnets list \
  --filter="network:lab3-vpc"

gcloud compute networks subnets describe lab3-app-subnet \
  --region="$REGION"
~~~

You should see three subnets all belonging to `lab3-vpc`, yet each subnet is a regional resource with its own CIDR range. If you add subnets in another region later, keep the address plan **non-overlapping**. A VM in a zone of another region cannot directly attach to a subnet in Singapore.

## 4. Create Cloud NAT for the Two Private Tiers

App and Data VMs will have no external IPs. To let them initiate outbound Internet connections when installing packages or downloading updates, use **Public Cloud NAT** in the same region. Cloud NAT serves eligible outbound flows and return traffic; it **does not open public inbound ports** to the VMs.

~~~bash
gcloud compute routers create lab3-router \
  --network=lab3-vpc \
  --region="$REGION"

gcloud compute routers nats create lab3-nat \
  --router=lab3-router \
  --router-region="$REGION" \
  --nat-all-subnet-ip-ranges \
  --auto-allocate-nat-external-ips
~~~

Here Cloud Router is a regional resource required for NAT configuration; no BGP session is needed for this NAT example. `--nat-all-subnet-ip-ranges` covers eligible subnet ranges in the **NAT's region**; it does not mean a NAT in Singapore serves VMs across all regions of a global VPC.

In real environments, evaluate scoping NAT to specific subnet ranges, quotas, port exhaustion risk, and traffic processing costs. `nat-all-subnet-ip-ranges` is used in this lab to minimize flags during practice.

Inspect:

~~~bash
gcloud compute routers nats describe lab3-nat \
  --router=lab3-router \
  --router-region="$REGION"
~~~

## 5. Configure Tiered Firewalls

A custom mode VPC has **implied deny ingress** and **implied allow egress**, unless overridden by higher-priority policies or rules. By default, VMs in the same VPC cannot call every port on each other. We create four clearly scoped ingress rules:

| Rule | Allowed source | Target | Port |
| --- | --- | --- | --- |
| `lab3-allow-iap-ssh` | `35.235.240.0/20` — IAP TCP forwarding range | Three VMs with matching network tags | TCP 22 |
| `lab3-allow-web-http` | `0.0.0.0/0` — Internet, lab only | Web | TCP 80 |
| `lab3-allow-web-to-app` | `10.70.10.0/24` | App | TCP 8080 |
| `lab3-allow-app-to-data` | `10.70.20.0/24` | Data | TCP 9090 |

### 5.1. Allow Administrative SSH via IAP

~~~bash
gcloud compute firewall-rules create lab3-allow-iap-ssh \
  --network=lab3-vpc \
  --direction=INGRESS \
  --priority=1000 \
  --allow=tcp:22 \
  --source-ranges=35.235.240.0/20 \
  --target-tags=lab3-web,lab3-app,lab3-data
~~~

This rule permits SSH connections to target VMs only from IAP's IP range; operators **still need appropriate IAM permissions and VM login credentials**. A firewall rule alone does not grant OS access.

### 5.2. Expose Public HTTP Only at the Web Tier

~~~bash
gcloud compute firewall-rules create lab3-allow-web-http \
  --network=lab3-vpc \
  --direction=INGRESS \
  --priority=1000 \
  --allow=tcp:80 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=lab3-web
~~~

Use public HTTP only to **test sample data containing no secrets**. In production, use HTTPS, a properly protected load balancer, TLS certificates, source-restricted rules, and application access controls.

### 5.3. Allow Only Web → App and App → Data

~~~bash
gcloud compute firewall-rules create lab3-allow-web-to-app \
  --network=lab3-vpc \
  --direction=INGRESS \
  --priority=1000 \
  --allow=tcp:8080 \
  --source-ranges=10.70.10.0/24 \
  --target-tags=lab3-app

gcloud compute firewall-rules create lab3-allow-app-to-data \
  --network=lab3-vpc \
  --direction=INGRESS \
  --priority=1000 \
  --allow=tcp:9090 \
  --source-ranges=10.70.20.0/24 \
  --target-tags=lab3-data
~~~

**Important:** a source CIDR allows any machine with a matching IP in the source subnet to call the target tier on that port. That is a **subnet-level** restriction, not application-identity authorization. In production designs, consider tighter scoping via supported source/target selectors (such as service accounts or firewall policies), combined with application-layer auth and network-tag review controls. Anyone permitted to attach tags to VMs can influence which rules target them.

At this stage, the subnets already have automatically created **subnet routes** from Google Cloud. You do not need static routes or VPC Peering among the three subnets because they live in the same VPC. Still, having routes does not mean firewalls allow all traffic.

## 6. Create Three VMs, Each in Its Corresponding Subnet

For clarity, all three VMs are created in `asia-southeast1-b` using the Debian 12 image. Each VM has one network interface attached to the matching regional subnet. `lab3-web` receives an **ephemeral external IP** per the default single-NIC VM creation behavior; App and Data pass `--no-address` to have no external IP.

~~~bash
# Web tier: has external IP so browsers can call lab HTTP
gcloud compute instances create lab3-web \
  --zone="$ZONE" \
  --machine-type=e2-small \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --subnet=lab3-web-subnet \
  --private-network-ip=10.70.10.10 \
  --tags=lab3-web

# App tier: internal IP only
gcloud compute instances create lab3-app \
  --zone="$ZONE" \
  --machine-type=e2-small \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --subnet=lab3-app-subnet \
  --private-network-ip=10.70.20.10 \
  --no-address \
  --tags=lab3-app

# Data tier: internal IP only
gcloud compute instances create lab3-data \
  --zone="$ZONE" \
  --machine-type=e2-small \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --subnet=lab3-data-subnet \
  --private-network-ip=10.70.30.10 \
  --no-address \
  --tags=lab3-data
~~~

### 6.1. Verify IP Addresses After Creating VMs

~~~bash
gcloud compute instances list \
  --filter="name~^lab3-" \
  --format="table(name,zone,networkInterfaces[0].networkIP,status)"

gcloud compute instances describe lab3-web \
  --zone="$ZONE" \
  --format="yaml(networkInterfaces,tags)"

gcloud compute instances describe lab3-app \
  --zone="$ZONE" \
  --format="yaml(networkInterfaces,tags)"

gcloud compute instances describe lab3-data \
  --zone="$ZONE" \
  --format="yaml(networkInterfaces,tags)"
~~~

Verify that the three internal addresses match the design table, each VM belongs to the right subnet, and App/Data **have no `accessConfigs` providing an external IPv4**. Verify network tag names in the output, since firewall rules target only VMs carrying the target tags.

If an instance fails to create, read the error message: it may be quota, IP exhaustion, insufficient permissions, name collision, wrong subnet range, unsupported machine type in zone, or organization policy. **Do not delete and recreate the entire VPC** just to work around a single quota error.

### 6.2. SSH via IAP Without Exposing Port 22 Publicly

Connect to each VM in turn from Cloud Shell or a machine with gcloud:

~~~bash
# Open an SSH session to the Data VM
gcloud compute ssh lab3-data \
  --zone="$ZONE" \
  --tunnel-through-iap
~~~

Once finished on a VM, type `exit` to return to the gcloud shell, then connect to the next VM by name.

~~~bash
gcloud compute ssh lab3-app --zone="$ZONE" --tunnel-through-iap
gcloud compute ssh lab3-web --zone="$ZONE" --tunnel-through-iap
~~~

These commands **open an interactive session one at a time**; do not paste two commands consecutively without exiting the previous session first. If IAP SSH fails, check APIs, the firewall rule from `35.235.240.0/20`, IAP roles, VM login permissions, OS Login/SSH keys, network tags, and error messages. IAP TCP forwarding does not replace OS-level login authorization.

## 7. Start Sample Services in Order: Data → App → Web

The goal is to create a verifiable request chain:

`browser → Nginx Web:80 → App:8080 → Data:9090 → App → Web → browser`.

The Data tier content is a plain text file containing no sensitive data. The App tier uses Python's standard library to fetch the file over HTTP and return the response. The Web tier uses Nginx as a reverse proxy. All examples run on Debian 12; commands in each subsection run **inside the corresponding VM**, not on the machine running gcloud.

### 7.1. On Data VM: Serve Sample File on Port 9090

Log in:

~~~bash
gcloud compute ssh lab3-data --zone="$ZONE" --tunnel-through-iap
~~~

**Inside the Data VM shell**, install Python and create sample data:

~~~bash
sudo apt-get update
sudo apt-get install -y python3 curl
sudo install -d -m 755 /opt/lab3-data
printf 'records=demo-only\n' | sudo tee /opt/lab3-data/records.txt >/dev/null
~~~

Create a systemd service so it keeps running after SSH exits:

~~~bash
sudo tee /etc/systemd/system/lab3-data.service >/dev/null <<'UNIT'
[Unit]
Description=Lab 3-tier data simulator
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=www-data
ExecStart=/usr/bin/python3 -m http.server 9090 --bind 10.70.30.10 --directory /opt/lab3-data
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now lab3-data.service
sudo systemctl status lab3-data.service --no-pager
curl -fsS http://10.70.30.10:9090/records.txt
~~~

Expected output of the final `curl`:

~~~text
records=demo-only
~~~

This service serves simulated data only. Never use `python3 -m http.server` for real data, as it lacks the authentication, access control, TLS, and data protection of a dedicated database service.

Exit the Data VM session with `exit`.

### 7.2. On App VM: Call Data and Return Result on Port 8080

Log in:

~~~bash
gcloud compute ssh lab3-app --zone="$ZONE" --tunnel-through-iap
~~~

**Inside the App VM shell**, install Python and verify the app subnet can reach Data:

~~~bash
sudo apt-get update
sudo apt-get install -y python3 curl
curl -fsS --connect-timeout 3 http://10.70.30.10:9090/records.txt
~~~

The last command should return `records=demo-only`. If it fails, check the Data service, routes, `lab3-allow-app-to-data` firewall, actual IP addresses, and local firewalls before writing the app.

Create the sample API:

~~~bash
sudo install -d -m 755 /opt/lab3-app
sudo tee /opt/lab3-app/server.py >/dev/null <<'PY'
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

DATA_URL = "http://10.70.30.10:9090/records.txt"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return

        try:
            with urlopen(DATA_URL, timeout=3) as upstream:
                records = upstream.read(128).decode("utf-8").strip()
        except Exception:
            self.send_error(502, "Data tier unavailable")
            return

        body = ("app-tier-ok; " + records + "\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

ThreadingHTTPServer(("10.70.20.10", 8080), Handler).serve_forever()
PY
~~~

Register the systemd service:

~~~bash
sudo tee /etc/systemd/system/lab3-app.service >/dev/null <<'UNIT'
[Unit]
Description=Lab 3-tier application simulator
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=www-data
ExecStart=/usr/bin/python3 /opt/lab3-app/server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now lab3-app.service
sudo systemctl status lab3-app.service --no-pager
curl -fsS http://10.70.20.10:8080/
~~~

Expected output:

~~~text
app-tier-ok; records=demo-only
~~~

The App VM **does not reach Data via an external IP**; this is a connection to an internal IP in another subnet within the **same VPC**. Subnet routes provide the path, while the firewall permits TCP 9090 from the App range to the Data VM.

Exit the App VM with `exit`.

### 7.3. On Web VM: Nginx Forwards Requests to App

Log in:

~~~bash
gcloud compute ssh lab3-web --zone="$ZONE" --tunnel-through-iap
~~~

**Inside the Web VM shell**, install and configure Nginx:

~~~bash
sudo apt-get update
sudo apt-get install -y nginx curl

sudo tee /etc/nginx/sites-available/default >/dev/null <<'NGINX'
server {
    listen 80 default_server;
    server_name _;

    location / {
        proxy_pass http://10.70.20.10:8080;
        proxy_connect_timeout 3s;
        proxy_read_timeout 5s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGINX

sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
curl -fsS http://localhost/
~~~

Expected output:

~~~text
app-tier-ok; records=demo-only
~~~

Here Web does not need direct access to Data. Nginx simply proxies requests to `10.70.20.10:8080`; App calls Data at `10.70.30.10:9090` and returns the result.

Exit the Web VM. From a **shell outside the VMs**, fetch Web's external IP and test from a browser or curl:

~~~bash
WEB_IP="$(gcloud compute instances describe lab3-web \
  --zone="$ZONE" \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')"

printf 'Public web IP: %s\n' "$WEB_IP"
curl -fsS "http://$WEB_IP/"
~~~

If everything is running, the response is `app-tier-ok; records=demo-only`. This confirms the **permitted three-tier chain** works; it does not prove the system is secure enough for real data. The lab uses unencrypted HTTP and a temporary public IP; never transmit passwords, keys, or customer data through this endpoint.

## 8. Test Both Permitted and Denied Paths

Never evaluate a firewall solely from one successful HTTP result. A multi-tier design meets requirements when **intended paths work** and **unauthorized connections fail to reach their targets**.

### 8.1. Test Matrix

| Source | Destination | Port | Expectation | Basis |
| --- | --- | --- | --- | --- |
| Internet | Web external IP | TCP 80 | **Allowed** | `lab3-allow-web-http` |
| Web VM | App internal IP | TCP 8080 | **Allowed** | `lab3-allow-web-to-app` |
| App VM | Data internal IP | TCP 9090 | **Allowed** | `lab3-allow-app-to-data` |
| Web VM | Data internal IP | TCP 9090 | **Blocked** | Data allows only sources in the App subnet |
| Data VM | App internal IP | TCP 8080 | **Blocked** | App allows only sources in the Web subnet |
| Internet | App or Data external IP | Any | **No public IPv4 endpoint** | Both VMs created with `--no-address` |
| Admin via IAP | Tagged VM | TCP 22 | **Only with matching IAM/SSH rights** | IAP source range and VM login |

These expectations apply to a **lab project containing only the rules created in this lesson**. If organization-level firewall policies, other rules, multiple NICs, or higher-priority rules exist, results may differ. Always inspect **effective firewall policies** in active organizational environments.

### 8.2. Test Allowed Connections

On the Web VM (SSH in from gcloud shell, then run inside the VM):

~~~bash
curl -fsS --connect-timeout 3 http://10.70.20.10:8080/
~~~

Expected: `app-tier-ok; records=demo-only`. This confirms Web → App is allowed and App called Data successfully.

On the App VM:

~~~bash
curl -fsS --connect-timeout 3 http://10.70.30.10:9090/records.txt
~~~

Expected: `records=demo-only`. Even though App and Data sit in two different subnets of the same VPC, Google Cloud provides subnet routes to the destination. No VPC Peering or internal VPN is needed between these two subnets.

### 8.3. Test Blocked Connections

On the Web VM:

~~~bash
# Expected timeout: Web MUST NOT connect directly to Data
curl --verbose --connect-timeout 3 --max-time 5 \
  http://10.70.30.10:9090/records.txt
~~~

On the Data VM:

~~~bash
# Expected timeout: Data MUST NOT initiate connections to App:8080
curl --verbose --connect-timeout 3 --max-time 5 \
  http://10.70.20.10:8080/
~~~

The `curl` commands in negative tests are **expected to fail/time out**; that is verification evidence to analyze, not a failure to fix. If instead of timing out you receive data, re-check rules applied to subnets/VMs, routes, and higher-level policies.

**Note on stateful firewalls:** Data is still permitted to **send reply packets** for connections validly initiated by App. Never cite that return traffic as proof that Data is allowed to initiate brand-new connections to App.

### 8.4. Inspect Network Configuration via gcloud

From Cloud Shell or your gcloud machine, after exiting all SSH sessions:

~~~bash
# Inspect VPC, subnets, and CIDR ranges
gcloud compute networks describe lab3-vpc
gcloud compute networks subnets list --filter="network:lab3-vpc"

# Inspect routes listed by Compute Engine
gcloud compute routes list --filter="network:lab3-vpc"

# Inspect created ingress rules
gcloud compute firewall-rules list --filter="network:lab3-vpc"

# Verify subnet and network tags on a VM
gcloud compute instances describe lab3-data \
  --zone="$ZONE" \
  --format="yaml(networkInterfaces,tags)"
~~~

Subnet routes do not require manually creating static routes. However, `gcloud compute routes list` does not always reflect every effective path for dynamic routing or advanced networking products. As labs grow more complex, use Cloud Router info, effective firewalls, and **Connectivity Tests** in Network Intelligence Center (when supported for the scenario).

### 8.5. Check Logs When a Tier Does Not Respond

If Web returns HTTP 502, inspect starting closest to the destination:

1. From the App VM, `curl` Data to confirm the data tier is running.
2. From the Web VM, `curl` App to confirm connectivity and app-tier response.
3. On the App VM, read `sudo systemctl status lab3-app` and `sudo journalctl -u lab3-app -n 40 --no-pager`.
4. On the Data VM, read `sudo systemctl status lab3-data` and `sudo journalctl -u lab3-data -n 40 --no-pager`.
5. On the Web VM, read `sudo nginx -t` and `sudo journalctl -u nginx -n 40 --no-pager`.
6. Cross-check exact IPs, ports, zones, network tags, ingress firewalls, local firewalls, server bind addresses, and IAM permissions when using tools.

| Observed error | Common cause | How to check |
| --- | --- | --- |
| Cannot create VM | Quota, missing permissions, unsupported zone/machine type, duplicate name or IP | Read gcloud error; verify project, subnet, zone capacity, and quotas |
| SSH via IAP fails | IAP API/IAM, TCP 22 rule, OS Login or SSH keys, wrong tag | Verify both IAP permissions and VM login permissions |
| App/Data cannot install packages | Cloud NAT wrong region/scope, missing default route, DNS, egress firewall | Check NAT, subnet, routes, and apt output |
| Web returns 502 | App service error, port 8080 blocked, or App cannot reach Data | Check App/Data hop by hop and journalctl |
| Web can reach Data directly | Overly broad ingress rule or another allowing policy | Inspect effective firewalls, source CIDRs, targets, and rule priorities |
| App VM has an external IP | Accidentally omitted `--no-address` at creation | Read `networkInterfaces.accessConfigs`; remediate via change process |
| App → Data has route yet times out | Ingress rule, OS firewall, or Data service not listening | Check both network path and port 9090 service |

Logs may contain IP addresses and infrastructure details; share only on a need-to-know basis. If enabling VPC Flow Logs or Firewall Rules Logging for deeper inspection, account for sampling rates, collection settings, data retention, and Logging charges.

## 9. Analyzing Design Decisions

### 9.1. Why Three Subnets When All Share One VPC?

A VPC can contain subnets in the same or different regions. In this lab, three subnets in the same region establish **IP planning, placement, and resource organization** boundaries for Web, App, and Data. However, a subnet **is not a physical firewall**: if you create broad ingress rules, Web can still reach Data directly via subnet routes.

We chose three subnets so learners can clearly see flows and CIDR source filters. In production, you might share a subnet with service-account-based authorization and finer network policies, or separate VPCs for stronger isolation. Decisions depend on trust boundaries, administrative ownership, and specific control requirements.

### 9.2. Why Do App and Data Lack External IPs?

Inner-tier applications do not need to accept direct requests from the Internet. Withholding external IPs shrinks public exposure; IAP provides admin access and NAT handles necessary outbound connections. Still, **lacking an external IP does not automatically mean secure**: a VM inside a VPC can still be reached over internal networks or peering/hybrid links if firewalls and identities are poorly managed.

### 9.3. Why Doesn't Cloud NAT Replace a Firewall?

Cloud NAT performs **address translation for eligible egress**. It does not ensure the App application only talks to one Internet domain, performs no authentication, and does not enforce IAM roles. To control outbound destinations, combine egress firewalls, proxies, or solutions matching requirements; DNS and encrypted traffic inspection may also be needed.

### 9.4. What If Moving to Managed Services?

This lab uses VMs to make NICs and routes easy to observe. In real architectures, account for each service's specific connectivity mechanism:

| Replaceable component | Google Cloud option | Key differences to note |
| --- | --- | --- |
| Web VM | External Application Load Balancer + VM/GKE/Cloud Run backends | HTTPS, certificates, health checks, backend services, and health-check firewall rules |
| App VM | Cloud Run | VPC egress via Direct VPC egress or Serverless VPC Access per supported config; Cloud Run is not a NIC-attached VM like this example |
| Containerized App | VPC-native GKE | Node subnet and Pod/Service secondary IP ranges must be sized with enough capacity |
| Simulated Data VM | Cloud SQL via private IP | Requires private services access or supported private connectivity; Cloud SQL IP is not directly allocated from `lab3-data-subnet` by default |
| Multi-project org resource access | Shared VPC | Host project owns VPC/subnets; service projects run workloads with delegated IAM |

Switching from the simulated Data tier to Cloud SQL also requires managing DB users, secrets, backups, HA, scaling, and secure connections. **A firewall allowing TCP to a database does not grant permission to read tables or execute queries.**

### 9.5. Does a Private VPC Protect Against Region Outages?

The VPC is **global**, yet all three VMs currently run in a single zone of one region. A zone or region outage can take down the entire Web → App → Data chain. For HA, add availability zones/regions, load balancing, appropriate replicas, and data recovery mechanisms. Making a VPC global or adding a subnet in another region **does not automatically** create running backends there.

When scaling out, define SLO targets, **RTO** (Recovery Time Objective), and **RPO** (Recovery Point Objective). Also verify data residency, cross-region network transfer charges, and live failover capability.

## 10. Monitoring Costs and Cleaning Up All Lab Resources

The resources below can incur charges even when you are not visiting the website:

- VMs and boot persistent disks while VMs exist or storage volumes remain undeleted.
- Web's external IPv4 and Public NAT addresses per current pricing policies.
- Cloud NAT and processed traffic, plus Internet or cross-region data transfer.
- Cloud Logging/Flow Logs and any extra resources created while extending the lab.

Record resource names, project, region, and test timestamps. **Budget alerts are not hard spending caps**: always verify and delete resources when finished.

### 10.1. Inspect Before Deleting

From the gcloud shell outside the VMs:

~~~bash
gcloud config get-value project
gcloud compute instances list --filter="name~^lab3-"
gcloud compute networks list --filter="name=lab3-vpc"
gcloud compute firewall-rules list --filter="network:lab3-vpc"
gcloud compute routers nats list \
  --router=lab3-router \
  --router-region="$REGION"
~~~

**Double-check the project name and that every resource belongs to the lab.** If multiple users share the project or a resource has been adopted by another team, halt deletion and verify with owners. The commands below apply strictly to resources **you just created in this lab**.

### 10.2. Delete in Dependency Order

~~~bash
# 1. Delete the three VMs in the lab zone
gcloud compute instances delete \
  lab3-web lab3-app lab3-data \
  --zone="$ZONE" --quiet

# 2. Delete the four lab ingress firewall rules
gcloud compute firewall-rules delete \
  lab3-allow-iap-ssh \
  lab3-allow-web-http \
  lab3-allow-web-to-app \
  lab3-allow-app-to-data \
  --quiet

# 3. Delete NAT before Cloud Router
gcloud compute routers nats delete lab3-nat \
  --router=lab3-router \
  --router-region="$REGION" \
  --quiet

gcloud compute routers delete lab3-router \
  --region="$REGION" --quiet

# 4. Delete subnets once VMs no longer use them
gcloud compute networks subnets delete \
  lab3-web-subnet lab3-app-subnet lab3-data-subnet \
  --region="$REGION" --quiet

# 5. Delete the VPC once all dependent components are removed
gcloud compute networks delete lab3-vpc --quiet
~~~

If a deletion command fails, read the message regarding dependent resources and **handle only the remaining lab pieces**. Never replace it with commands deleting all VMs, all VPCs, or a shared project.

Final verification:

~~~bash
gcloud compute instances list --filter="name~^lab3-"
gcloud compute networks list --filter="name=lab3-vpc"
gcloud compute firewall-rules list --filter="network:lab3-vpc"
~~~

Once all three queries return no lab resources, also check Console if you created extra disks, reserved IPs, log sinks, or extensions outside this guide. Charges accrued prior to deletion may still appear in billing reports after a reporting delay.

## 11. Extension Exercises and Self-Check Questions

**Exercise 1 — Identity-based source restriction.** Explore how to replace the `10.70.10.0/24` range-based firewall rule with a tighter control model for appropriate Web machines. Explain the risk when someone permitted to create VMs or attach network tags can alter which machines match a rule.

**Exercise 2 — Environment separation.** Design an additional `dev-vpc` network for testing; compare organizing with two separate VPCs versus Shared VPC for service projects. Describe who is permitted to create subnets and who is permitted to deploy workloads.

**Exercise 3 — Multi-region deployment.** If you want Web and App in a standby region, which subnets and components must you add? Analyze routing, firewalls, load balancing, replication, quotas, RTO/RPO, and data transfer charges.

**Exercise 4 — Release automation.** If migrating App to Cloud Run, redraw the HTTP flow and the egress path to the database's private IP. Identify the runtime service account and least-privilege IAM roles instead of using an admin account across all services.

**Exercise 5 — Fault investigation.** Predict what happens if you temporarily remove the `lab3-allow-web-to-app` rule: what will external users see? Does the App-to-Data path still work independently? Review the firewall matrix before answering.

### Review Questions

1. **Does a global VPC make every subnet global?** No. VPCs are global, subnets are regional, VMs are zonal.
2. **Does creating three subnets automatically prevent Web from calling Data directly?** No. Firewalls and appropriate access-control policies are required.
3. **Can App without an external IP download packages from the Internet?** Possibly, if a valid egress path like Cloud NAT, routes, DNS, and firewalls are configured.
4. **Does enabling Cloud NAT open inbound Internet access to App?** No. Public Cloud NAT serves eligible outbound and return traffic.
5. **Does IAP SSH require IAM and VM login permissions?** Yes. Opening TCP 22 to the IAP range in a firewall is only part of the requirement.
6. **Why do we need negative (blocked) tests?** Because working permitted connections do not prove internal tiers and data are isolated.
7. **Should production keep the HTTP-simulated Data service from this lab?** No. Use an appropriate database service with encryption, authentication, backups, least-privilege IAM, and HA design.

## Official Documentation for Cross-Reference

- [VPC networks](https://cloud.google.com/vpc/docs/vpc): global VPCs, regional subnets, and route scopes.
- [VPC subnets](https://cloud.google.com/vpc/docs/subnets): CIDR planning, subnet modes, and Private Google Access.
- [VPC firewall rules](https://cloud.google.com/firewall/docs/firewalls): ingress/egress, targets, sources, and implied rules.
- [Cloud NAT overview](https://cloud.google.com/nat/docs/overview): regional NAT, outbound flows, and limits.
- [Connect to Linux VMs using IAP](https://cloud.google.com/compute/docs/connect/ssh-using-iap): IAM, firewalls, IAP TCP forwarding, and SSH.
- [Shared VPC](https://cloud.google.com/vpc/docs/shared-vpc): separating network and workload responsibilities between host/service projects.
- [Cloud Run VPC networking](https://cloud.google.com/run/docs/configuring/vpc-direct-vpc): connecting serverless workloads to private networks.
- [Cloud SQL private IP](https://cloud.google.com/sql/docs/mysql/configure-private-ip): connecting to managed databases via private IP per product.
- [VPC network pricing](https://cloud.google.com/vpc/network-pricing) and [Compute Engine pricing](https://cloud.google.com/compute/all-pricing): checking charges by region and resource type.

gcloud commands, IAM roles, regional product availability, and pricing are subject to change. Before running in a real project, verify against current documentation, granted permissions, and your organization's network topology. This lab succeeds when you can both call the **Web → App → Data** chain and prove Web **cannot call Data directly**, and then **delete all lab resources** upon completion.

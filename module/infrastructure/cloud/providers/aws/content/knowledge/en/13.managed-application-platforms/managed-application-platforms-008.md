# Lightsail Instances and Suitable Use Cases

> **Chapter:** Managed Application Platforms  
> **Module:** `CLOUD_PROVIDERS_AWS` — exploring the AWS ecosystem from Regions/AZs, IAM, and VPCs to compute, storage, databases, integration, and serverless; practicing service selection and designing systems that are secure, observable, resilient, and cost-controlled.

A small business needs to put a company website, WordPress site, or simple web application on the Internet. With Amazon EC2, the team has to consider AMIs, instance types, EBS, VPCs, subnets, route tables, Security Groups, Elastic IPs, and many other pieces. **Amazon Lightsail** bundles common choices into a simpler experience: pick a **blueprint**, an **instance plan (bundle)**, and a Region/Availability Zone, then launch a server with basic networking and storage included.

Lightsail reduces initial infrastructure decisions, **not by turning virtual servers into a fully managed application service**. Operators remain responsible for the operating system, patches, SSH accounts, web server configuration, application data, certificates, and backup plans. This lesson focuses on **Lightsail instances** and how to recognize when they are a better fit than EC2, Elastic Beanstalk, App Runner, or container platforms.

Examples use the `example.com` domain, documentation IPs, and hypothetical resource names. Resource availability, IPv4/IPv6 networking modes, bundle names, pricing, and Lightsail features vary by Region and over time; always verify against the live AWS Console, API, and current pricing when deploying for real.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain **Lightsail instance**, **blueprint**, **bundle**, **Region**, **Availability Zone**, **static IP**, and **instance firewall**.
2. Design a basic `DNS → Lightsail instance → application` architecture with HTTP/HTTPS, secure SSH access, and a stable IP address.
3. Distinguish **root disk**, **attached block storage**, **snapshots**, and **application/database backups**.
4. Evaluate scalability, running multiple instances behind a Lightsail load balancer, and single-Region redundancy limits.
5. Account for **bundle pricing**, extra storage, snapshots, IPs, traffic, and other Lightsail resources.
6. Choose the right service based on need: small website, testing, steady-state system, or complex production application.
7. Use the AWS Console and AWS CLI to inspect configuration, security, and resources before making changes.

## 2. What Is a Lightsail Instance Really?

**Amazon Lightsail** is a cloud computing service aimed at simplifying deployments of small applications, websites, and workloads with relatively predictable resource needs. A **Lightsail instance** is a **virtual private server**, typically running Linux/Unix or Windows per supported plans and blueprints.

An instance comprises these core components:

| Component | Meaning | Operator Decisions Required |
| --- | --- | --- |
| **Blueprint** | OS or pre-installed application image | Choose bare OS vs. WordPress/LAMP/matching stack |
| **Bundle / instance plan** | Compute and storage resource bundle | CPU, RAM, root disk capacity, transfer allowance, price |
| **Region and AZ** | Location where the VM runs | Latency, data residency, supported AZs, and fault-tolerance plan |
| **Root disk** | System disk attached to the instance | Capacity, file placement, and snapshot strategy |
| **Networking** | Private address, public address per plan type, firewall | Open ports, IPv4/IPv6, DNS, and admin access |
| **Key pair / credentials** | Initial administrative access credentials | Linux SSH key or how Windows passwords are retrieved/managed |
| **Monitoring** | Instance metrics and alarms supported by Lightsail | CPU, burst capacity, network, disk, status/cost |

A Lightsail bundle advertises monthly resources, making estimates easier than picking separate EC2/EBS/network items. However, **the total bill does not automatically equal a single bundle price** because add-on services, snapshot storage, transfer overages, and address/resource fees can apply under current pricing rules.

### 2.1. How "Managed" Is Lightsail?

Do not confuse **Lightsail simplifying infrastructure** with **AWS operating the entire application**.

| Managed by AWS / Lightsail | Still Managed by the Workload Owner |
| --- | --- |
| Physical infrastructure and underlying hosts | OS patching and software updates inside the instance |
| VM provisioning, plans, and bundled storage | Web server, runtime, application code, config, and deploy errors |
| Service-level create/delete and snapshot mechanics | Verified data backups and application restores |
| Networking/addresses and Lightsail-level instance firewall | Access rules, SSH keys, OS firewall, TLS certificates |
| Baseline metrics and basic alerting mechanisms | Application logs, tracing, business monitoring, incident response |

For example, deploying a WordPress blueprint does not mean AWS automatically tests and updates all your site's plugins or maintains transactionally consistent backups of every new order. If a site is compromised via an outdated plugin, your operations team must patch, investigate, and recover.

### 2.2. Lightsail Is More Than Just Instances

Beyond instances, Lightsail offers resources with varying levels of management:

- **Static IPs**, DNS zones, and DNS records.
- **Block storage disks** and snapshots.
- **Load balancers** for eligible Lightsail instances.
- **Managed relational databases** on supported engines and plans.
- **Object storage**, **Lightsail container services**, and content distribution options.

This lesson **does not equate** those products with instances. For example, a **Lightsail container service** is a separate container deployment model, whereas a Lightsail instance remains a VM requiring OS administration. A Lightsail managed database reduces DB ops compared to self-installing MySQL on an instance, yet you still own schemas, access controls, queries, and data.

## 3. Blueprint and Bundle: Two Different Decisions

When creating an instance, the interface prompts you to pick a **blueprint** and then an **instance plan**.

### 3.1. What Is a Blueprint?

A **blueprint** specifies the OS or a pre-installed application/software stack:

| Blueprint Group | Examples of Provided Stacks | When Suitable |
| --- | --- | --- |
| **OS only** | Ubuntu, Amazon Linux, Debian, Windows Server by Region | You want to install Nginx, Java, Node.js, PostgreSQL clients yourself |
| **Application + OS** | WordPress, LAMP, common stacks/apps | You want to launch a familiar web stack quickly |
| **Purpose-built blueprints** | App servers or other catalog stacks | After evaluating security support, update paths, and backups |

Pre-built application images speed up launch, though they carry defaults for web servers, config paths, accounts, and runtime versions. **Read the blueprint documentation** before upgrading—never assume pre-installed defaults meet production standards.

### 3.2. What Is a Bundle/Plan?

A **bundle** is the resource tier chosen at instance creation. Key attributes to compare:

- **vCPU and CPU performance model:** compute capacity and burst capacity where plans use burstable CPU.
- **RAM:** enough for runtime, caches, connection pools, and the OS.
- **Root SSD storage:** holds the OS, application, and any data stored on the root disk.
- **Data transfer allowance:** monthly transfer included in the plan under specific billing rules.
- **Platform and network type:** Linux/Windows, IPv4/IPv6, instance class, and Regional availability.

A **Java/JVM** workload with insufficient RAM can repeatedly hit OOM kills or GC latency spikes even at low CPU. Conversely, a static landing page may run fine on a tiny plan, yet adding image processing or background jobs turns CPU burst and disk I/O into bottlenecks.

**Note on CPU burst:** some Lightsail instance plans can exceed baseline CPU briefly using burst capacity. Under sustained high CPU load, performance may drop below short-benchmark results. Monitor CPU utilization and burst metrics, and run sustained load tests rather than a handful of requests.

### 3.3. Example Plan Selection from Requirements

Suppose a Java Spring Boot application has:

~~~text
Application: catalog API + internal admin portal
Current load: ~10 requests/second, rising during campaigns
Runtime: JVM, needing 2 GiB RAM in test configuration
Storage: 10 GiB uploaded data, continuing to grow
Requirements: HTTPS, daily backups, 4-hour RTO
~~~

Plan-selection process:

1. Measure **steady-state RAM + JVM heap + native memory + OS + local DB/proxy if co-located**.
2. Measure p95/p99 CPU, burst intervals, and background job duration.
3. Size disk for OS, logs, artifacts, uploads, temp backups, and growth headroom.
4. Estimate outbound transfer from request volume and response payload size.
5. Check actual Regional plans, then **benchmark** using the real runtime/image.

There is no "exact plan" from "10 req/s" alone: identical request rates with different query/response sizes and CPU profiles can require completely different plans.

## 4. Regions, Availability Zones, and Fault-Tolerance Limits

A Lightsail instance launches inside **one Availability Zone** in **one supported AWS Region**. Region drives latency, data residency compliance, and connectable services; AZ is the infrastructure fault domain.

### 4.1. A Single Instance Is a Single Point of Failure

~~~mermaid
flowchart LR
    U["Users"] --> DNS["DNS"]
    DNS --> VM["Lightsail instance\n1 AZ"]
    VM --> APP["Web server + application"]
    VM --> DATA["Files/DB on the same instance"]
~~~

Pros: few moving parts, easy to learn and manage. Cons:

- If the instance stops, the OS hangs, disk fails, or the AZ degrades, **the application can go down**.
- Co-locating the app and database on one instance complicates backups, restores, and recovery.
- A bad update affects the entire service simultaneously.

Snapshots provide **recoverability**, not instant HA for a single instance. If strict uptime or a tight RTO is required, the design must expand further.

### 4.2. Scaling Within One Region

A multi-instance design can combine a **Lightsail load balancer**, multiple web instances across eligible AZs, and a separate database:

~~~mermaid
flowchart TB
    U["Users"] --> DNS["DNS: app.example.com"]
    DNS --> LB["Lightsail load balancer\nHTTP/HTTPS + health checks"]
    subgraph REG["One AWS Region"]
      subgraph A["AZ A"]
        WA["Lightsail web instance A\nstateless"]
      end
      subgraph B["AZ B"]
        WB["Lightsail web instance B\nstateless"]
      end
      DB["Lightsail managed database\nHA if plan supports and enabled"]
    end
    LB --> WA
    LB --> WB
    WA --> DB
    WB --> DB
    WA -.->|"Shared images/files"| OBJ["Object storage / S3 as needed"]
    WB -.->|"Shared images/files"| OBJ
~~~

This reduces dependence on **one web instance**, yet does not automatically guarantee:

- Database redundancy during an AZ outage.
- Shared sessions, uploads, and critical state across instances.
- Enough remaining **capacity** if one AZ is lost.
- Load balancers, secrets, background jobs, DNS, and data stores meeting RTO/RPO.

Do not simply "put two instances behind an LB" while each writes order data to local files; requests will see inconsistent state.

### 4.3. Recovery Objectives

| Concept | Question |
| --- | --- |
| **RTO** | After a failure, how quickly must the application restore service? |
| **RPO** | What is the maximum acceptable data loss measured in time? |
| **HA** | Under which failures does the application keep serving without manual restore? |
| **DR** | When losing resources, an AZ, or a Region, how do you recover app and data? |

A once-daily snapshot **does not** meet a one-minute RPO for continuous order transactions. Multi-AZ **does not** automatically survive a Regional outage or prevent accidental deletions from replicating to standby copies.

## 5. IPs, Firewalls, and DNS for Lightsail Instances

### 5.1. Public IP, Private IP, and Static IP

A Lightsail instance receives a **private network address** within its supported networking model. Depending on plan type and settings, it has a **public IPv4**, **IPv6**, or another option.

For a website pointing a domain at a VM, consider a **static IPv4 address**:

- A static public IP avoids changing DNS records when replacing instances or performing related network operations.
- A static IP is a separate resource you **allocate and attach** per Region and support rules.
- You can reattach a static IP to a replacement instance per service rules to shorten DNS cutover; DNS TTL and app readiness still matter.
- **Default public addresses** should not be treated as permanent identifiers across stop/rebuild lifecycles.
- Check **static IP / public IPv4 pricing and billing rules** for attached vs. unattached states and current plans—do not assume all public IPs are free.

If using an **IPv6-only plan** in a supported Region, verify how clients, targets, and apps depend on IPv4. Never publish only AAAA records and assume every IPv4 user can connect.

### 5.2. Instance Firewall

Lightsail provides its own instance firewall. It typically controls **inbound traffic** by protocol, port, and source address; IPv4 and IPv6 rules must be checked separately per supported features.

| Purpose | Protocol / Port | Recommended Source |
| --- | --- | --- |
| HTTP website or HTTPS redirect | TCP 80 | Public if the website is genuinely public |
| HTTPS website | TCP 443 | Public if the website is genuinely public |
| Linux administration via SSH | TCP 22 | **Trusted admin IPs/networks only**, whenever possible |
| Windows RDP administration | TCP 3389 | **Restricted IPs/VPN**, never open widely to the Internet |
| Database inside instance | MySQL 3306 / PostgreSQL 5432 | Never open publicly unless genuinely required and tightly controlled |

**Do not equate the Lightsail firewall with EC2 Security Groups.** Lightsail exposes simpler network controls; do not assume full SG-to-SG referencing, subnet/NACL controls, or granular egress rules like EC2. If complex network segmentation is required, dedicated EC2/VPC may be necessary.

In addition to the Lightsail firewall, check the **OS firewall** (e.g., `ufw`/`firewalld` or Windows Firewall) and application listener config. Opening Lightsail TCP 443 does nothing if Nginx is not listening on 443 or TLS certificates are invalid.

### 5.3. DNS and HTTPS

Website example:

~~~text
Domain:         www.example.com
Static IPv4:    198.51.100.25  (documentation example IP)
DNS record:     www.example.com A → 198.51.100.25
Application:    Nginx/Apache on Lightsail :80/:443
~~~

Flow diagram:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant R as DNS resolver
    participant V as Lightsail instance
    B->>R: Query www.example.com
    R-->>B: 198.51.100.25 (example)
    B->>V: HTTPS to :443
    V-->>B: Web page / API response
~~~

You can manage DNS records with a **Lightsail DNS zone** or **Amazon Route 53**, depending on requirements. Ensure domain delegation points to the right authoritative DNS and check **TTL** before IP changes. You can use Let's Encrypt on the web server if managing TLS directly, or Lightsail load balancer certificates when running behind an eligible LB.

**Note:** `198.51.100.25` is a documentation-only IP, not a real address. A valid DNS record alone does not guarantee the site works: the listener, OS firewall, Lightsail firewall, and TLS must all be configured properly.

## 6. Creating an Instance via Console: Controlled Workflow

The lab objective is to stand up a **test website** on a Linux instance named `lab-lightsail-web`. Execute only in an authorized account/Region, check pricing before creating resources, and **never use real customer data**.

### 6.1. Preparation

1. Verify the account, Region, and **AWS Budgets / estimated spend**.
2. Decide between an OS-only blueprint and a pre-installed application blueprint.
3. Choose a bundle with enough RAM/CPU/storage for the lab; note price, transfer allowance, and billing terms.
4. Choose an AZ in a supported Region; note explicitly that this is **one instance, one AZ**.
5. Create and safeguard an SSH key pair, or use Lightsail Console browser SSH where supported.

### 6.2. Creation in the Lightsail Console

1. Open **Amazon Lightsail → Instances → Create instance**.
2. Select the Region/AZ and an appropriate Linux blueprint.
3. Review the bundle, network/IP mode, and root disk size.
4. If adding a launch script / user data, use only reviewed scripts.
5. Name it `lab-lightsail-web` and add management tags such as `Environment=lab`.
6. Create the instance and check its status and private/public IPs after provisioning.
7. Inspect inbound firewall rules; open only `80/443` for web traffic and restrict `22` to admin sources.
8. When a stable domain is needed, attach a static IP and configure DNS/TLS.

Exact console labels and bundle names may evolve. For production environments, capture the entire configuration as a runbook, IaC, or API workflow for repeatability.

### 6.3. Secure SSH Access

Linux instances can be managed using Lightsail Console **browser-based SSH** (when supported) or an SSH client on an admin workstation.

~~~bash
# Replace username and address to match your actual blueprint and instance
ssh -i ./lightsail-lab-key.pem ubuntu@PUBLIC_IP
~~~

Restrict permissions on the private key file; never commit keys to Git, paste them in chat, publish them in docs, or bake them into Docker images. Default usernames vary by blueprint—never assume every AMI/blueprint uses `ubuntu`. When connecting from an admin machine, both the Lightsail firewall and OS firewall must permit your source IP.

For Windows, administration uses browser-based RDP or an RDP client per Lightsail support; protect passwords and restrict the RDP port.

### 6.4. Deploying a Minimal Website on Ubuntu (Lab)

Run only on a **lab Ubuntu/Debian instance** verified to hold no critical data. Example serving an HTML page via Nginx:

~~~bash
sudo apt-get update
sudo apt-get install -y nginx
sudo systemctl enable --now nginx
sudo systemctl status nginx

cat <<'HTML' | sudo tee /var/www/html/index.html >/dev/null
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Lightsail Lab</title></head>
<body><h1>Website running on Lightsail</h1></body>
</html>
HTML

curl -I http://127.0.0.1/
~~~

This is an **HTTP lab**. Before exposing a real production site, add HTTPS with a valid certificate, OS/app patching, backups, and security hardening. Never leave basic HTTP as a production setup.

### 6.5. Four Layers to Check After Deployment

~~~text
Client → DNS A/AAAA record
       → Instance static/public IP
       → Lightsail firewall + OS firewall
       → Nginx / application listening on 80/443
~~~

If `curl http://127.0.0.1` returns 200 locally while external requests time out, suspect IP, routing, firewall, or DNS. If external HTTP works while HTTPS fails, inspect port 443, the TLS listener, and the certificate.

## 7. Storage: Root Disk, Attached Disks, and Backups

### 7.1. Root Disk

The root disk comes with the bundle and holds the OS plus anything you write on the instance. If databases, logs, and uploads all sit on the root disk, growth can fill the disk and break package managers, databases, or the app.

**Never leave the root disk as the sole storage location** for systems needing recovery. Offload data to attached disks, object storage, or a managed database as needed.

### 7.2. Attached Block Storage Disks

Lightsail offers additional disks depending on Region and OS/instance support:

- Separate capacity, billing, and lifecycle.
- Must be **attached**, formatted with a filesystem if new, **mounted**, and configured to remount on reboot.
- Tied to an AZ—do not assume you can arbitrarily attach a disk to an instance in another AZ without snapshotting and restoring.
- If multiple instances need concurrent read/write access, a block disk attached to one instance is **not a shared filesystem**.

### 7.3. Snapshots

**Snapshots** capture the state of an instance or disk per product capabilities. You can take **manual snapshots** or enable **automatic snapshots** where supported by resource type and Region.

| Target | What Can the Snapshot Be Used For? | Limitations to Remember |
| --- | --- | --- |
| **Instance snapshot** | Recreate the instance or move to a larger plan via supported workflows | Provisioning, DNS update, and restore time still apply |
| **Block disk snapshot** | Recreate a disk per policy | Must attach, mount, and verify the filesystem/app |
| **Logical / application DB backup** | Restore transactional data consistently at the app layer | VM disk snapshots do not guarantee consistency for active DB writes |

When a database is running, disk-level snapshots may be **crash-consistent** rather than **application-consistent**, depending on quiescing and the DB engine. For critical data, use database-native backups/restores, test restores on clones, and define clear **RPO/RTO**.

### 7.4. Recovering from a Snapshot

~~~mermaid
flowchart LR
    A["Instance failure / bad update"] --> S["Select valid snapshot"]
    S --> NEW["Create replacement instance"]
    NEW --> TEST["Verify OS, data, app, TLS"]
    TEST --> IP["Reattach static IP or update DNS"]
    IP --> LIVE["Client verification + monitoring"]
~~~

This workflow loses any data written **after the snapshot timestamp** and takes time to execute. If the business sets a few-minute RPO or sub-minute RTO, a daily snapshot is **insufficient**.

### 7.5. Snapshot Governance and Data Lifecycles

- Schedule snapshots per requirements and set **retention** using available features.
- Store copies/backups in line with your AZ/Region fault-tolerance strategy.
- Encrypt data and restrict IAM permissions to create, restore, and delete snapshots.
- Distinguish deleting an instance from deleting **remaining snapshots and disks**; orphaned snapshots/disks continue accruing charges.
- Run actual restore drills rather than trusting a dashboard saying "snapshot completed."

## 8. Lightsail Load Balancers and Scaling Websites

### 8.1. Vertical Scaling

When an instance lacks RAM, CPU, or storage, one option is choosing a **larger plan**. Depending on instance type and supported workflows, you may need to **take a snapshot and launch a new instance** from it on a higher bundle—do not assume every running instance can resize in place.

Changing plans may require:

1. Taking a snapshot after ensuring data consistency.
2. Launching a new instance from the snapshot with the target plan.
3. Verifying app/config, public/private networking, and firewall rules.
4. Reassigning the static IP or updating DNS per procedure.
5. Monitoring traffic, CPU, and errors before cleaning up the old instance.

Vertical scaling does not eliminate the single point of failure: one larger instance still lives in a single AZ.

### 8.2. Horizontal Scaling

When an app needs multiple web instances, a **Lightsail load balancer** can distribute requests across eligible instances. Prerequisites:

- All instances serve the **same application version** with consistent configuration.
- **Health checks** hit an endpoint reflecting true readiness, not merely an open port.
- Sessions, uploads, caches, and critical data are **not trapped on a single instance**.
- Selected AZs match service support and desired fault tolerance.
- TLS certificates, domains, and DNS paths are verified end-to-end.

**Do not confuse a Lightsail load balancer with an EC2/EKS ALB.** EC2/VPC ALBs offer advanced routing rules, target groups, and deep AWS integrations; Lightsail provides a simpler experience with its own protocol, configuration, and integration limits.

### 8.3. Remaining Capacity When an Instance or AZ Fails

Suppose an API runs two web instances, each safely handling `80 requests/second` in benchmarks, with peak load at `120 requests/second`:

~~~text
Total when both healthy   = 2 × 80 = 160 req/s
After losing one instance = 1 × 80 =  80 req/s
Required load             = 120 req/s
→ Insufficient capacity even though one instance remains up.
~~~

To keep serving 120 req/s when one instance fails, **provision enough spare capacity on the remaining nodes**, or accept throttling/degradation while scaling. Real behavior also depends on the database, CPU burst credits, network, disk I/O, and app behavior.

## 9. Databases, Uploads, and Components to Decouple from Instances

### 9.1. Self-Installing a Database on the Instance

Running both the web server and DB on one instance is **simple and low-cost** for demos or low-criticality sites. Drawbacks:

- CPU, RAM, and I/O contention between the app and DB.
- The OS disk/snapshot becomes coupled to both app and data.
- Scaling out web instances forces migrating to a **shared database**.
- Backups, restores, and runtime/DB upgrades can take down the whole stack.

For orders or critical transactions, consider a **Lightsail managed database** or a service like Amazon RDS if needs exceed Lightsail's scope.

### 9.2. Managed Relational Databases

Lightsail managed databases offer MySQL/PostgreSQL on currently supported engines/plans, simplifying part of database administration. Some plans/options support **high availability**; check exact specs, limits, and costs.

The application team must still:

- Manage schemas, migrations, transactions, and indexes.
- Control DB authentication, network access, secrets, and app privileges.
- Monitor connections, storage, latency, and query performance.
- Plan backups/restores and test failover.

**Do not assume every Lightsail managed database is Multi-AZ by default.** HA depends on the chosen plan and configuration—verify when selecting the plan.

### 9.3. File Uploads and Static Assets

With two web instances:

~~~text
Client uploads image → Web A writes /var/www/uploads/abc.jpg
Next client request  → Web B lacks abc.jpg
~~~

This is an **unshared local state** bug. Store files in **Lightsail object storage**, **Amazon S3**, or an appropriate shared store, while keeping keys/URLs and access checks in the DB. When using S3, manage IAM/credentials, encryption, bucket policies, and costs. Do not assume Lightsail instances automatically include an **EC2 instance profile** for seamless AWS credential retrieval—verify actual integration options and avoid hard-coding access keys.

### 9.4. Background Jobs and Queues

An app serving HTTP requests while running nightly reports on the same instance can burn CPU burst credits and spike latency. As workflows grow more complex, split out workers and queues using appropriate AWS services or move to ECS, App Runner, or Lambda where suitable.

## 10. Securing Lightsail in Production

### 10.1. Layers to Protect

~~~mermaid
flowchart TB
    NET["Internet / trusted networks"] --> FW["Lightsail firewall"]
    FW --> OSFW["OS firewall + SSH config"]
    OSFW --> WEB["TLS + web server"]
    WEB --> APP["Application authentication/authorization"]
    APP --> DATA["Database / object storage / secrets"]
~~~

**Never substitute one security layer for another.** Closing every port except 443 does not stop SQL injection in app code; TLS does not enforce authorization for logged-in users.

### 10.2. Minimum Security Checklist

- **SSH/RDP:** open only when needed; restrict to admin sources; protect private keys and apply brute-force protections.
- **OS and runtime updates:** apply security patches, package updates, and app/WordPress plugin updates yourself.
- **TLS:** provision and renew certificates; never accept plaintext HTTP for production apps handling sensitive data.
- **Secret management:** never hard-code DB passwords or API keys in repositories, public user data, or webroot files; restrict file permissions.
- **Least privilege:** separate OS users, avoid running apps as `root` unnecessarily, and limit filesystem and DB privileges.
- **Firewall:** review IPv4 and IPv6 rules separately; never leave unintended ports exposed.
- **Backups:** configure snapshot/app backups, retention, and restore tests; do not treat snapshots as a shield against all attacks.
- **Logging:** collect web access/error logs, auth logs, and app logs; configure rotation/retention and protect sensitive fields.
- **AWS account IAM:** enforce MFA, narrow Lightsail admin permissions, enable CloudTrail, and review IP/firewall changes.
- **Cost guardrails:** set AWS Budgets, owner/environment tags, and alerts for forgotten resources.

**Note on credentials:** do not treat a Lightsail instance as having full EC2 instance profile/role capabilities or full VPC network controls by default. If a workload calls many AWS APIs and needs automated workload identity credentials, verify supported options or prefer EC2/ECS/Lambda with explicit workload IAM roles.

### 10.3. Shared Responsibility Model

AWS manages security **of** the cloud (underlying infrastructure), while you manage security **in** the workload: OS configuration, applications, IAM, keys, data, firewalls, backups, and access control. Low-cost, simple bundles do not erase operational responsibility.

## 11. Observability and Troubleshooting

### 11.1. Metrics to Watch

| Layer | Key Signals |
| --- | --- |
| **Compute** | CPU utilization, burst capacity metrics (where supported), instance state |
| **Network** | Inbound/outbound traffic, failed connections, firewall rules, DNS, and TLS |
| **Disk** | Filesystem space, inodes, I/O, or disk metrics per monitoring capabilities |
| **Application** | HTTP 4xx/5xx rates, p95/p99 latency, request counts, process health |
| **Database** | Connections, free space, slow queries, backups, and DB availability |
| **Backups** | Latest snapshot timestamp, restore test results, backup age |
| **Billing** | Instance, storage, snapshot, static/public IP, transfer, and add-on charges |

Lightsail provides a monitoring view with built-in metrics and alarms. **Do not assume all app-level metrics like filesystem % or HTTP latency appear automatically:** you may need extra agents or logging tools.

### 11.2. Common Errors

| Symptom | Primary Suspects | How to Investigate |
| --- | --- | --- |
| Website times out after instance creation | Port 80/443 firewall closed, wrong DNS/IP, OS firewall blocking | Check public/static IP, Lightsail firewall, and web listener |
| `Connection refused` on port 80 | Nginx/app not running or listening on wrong port | `systemctl status nginx`, `ss -lntp`, local curl |
| HTTPS warns invalid certificate | Expired cert, hostname mismatch, 443 TLS unconfigured | Inspect certificate, SNI, redirects, DNS |
| SSH times out | Wrong IP/source CIDR, firewall, or SSH daemon | Check Lightsail firewall port 22, OS firewall, and `sshd` status |
| SSH `Permission denied (publickey)` | Wrong user/key, mismatched key pair, or bad permissions | Verify blueprint username, key pair, and SSH logs |
| High CPU and slow responses | Undersized plan or exhausted burst capacity | Track CPU/burst over time; run sustained load tests |
| Instance running, yet site returns 500 | Runtime, app, or DB error | Web/app logs, DB connections, disk space |
| Disk full | Uploads, logs, caches, or backups filling root disk | `df -h`, careful `du`, log rotation, storage plan |
| Site unreachable after restoring from snapshot | Different public IP, secrets, config, DNS, or firewall | Verify every layer; move static IP only after testing |
| Bill still climbs when site is unused | Instance/disk/snapshot/IP/LB still exists or plan keeps billing | Audit resource inventory and AWS billing |

**Never fix an issue by opening all ports to `0.0.0.0/0` or disabling the OS firewall.** Identify the failing layer first and make targeted changes.

### 11.3. Inspection Commands Inside a Linux Instance

~~~bash
# Read-only; run once legitimately logged into the Linux lab VM
uname -a
df -h
free -h
sudo ss -lntp
sudo systemctl status nginx
curl -I http://127.0.0.1/
~~~

Do not assume every OS ships with Nginx or `systemd`. For containers or other app frameworks, adjust commands to match your actual runtime.

## 12. AWS CLI for Lightsail: Safely Inspecting Resources

Examples assume Region `ap-southeast-1`, configured AWS CLI, and read permissions for Lightsail. All commands below are **read-only** and neither create nor delete instances.

### 12.1. View Identity and Available Plans

~~~bash
aws sts get-caller-identity

aws lightsail get-regions \
  --query "regions[].{Name:name,AvailabilityZones:availabilityZones[].zoneName}" \
  --output json

aws lightsail get-blueprints \
  --region ap-southeast-1 \
  --query "blueprints[].{Id:blueprintId,Name:name,Platform:platform}" \
  --output table

aws lightsail get-bundles \
  --region ap-southeast-1 \
  --query "bundles[].{Id:bundleId,Price:price,CPUs:cpuCount,MemoryGB:ramSizeInGb,DiskGB:diskSizeInGb,TransferGB:transferPerMonthInGb}" \
  --output table
~~~

When output is long, filter plans in the AWS Console or add JMESPath filters to `get-bundles`. Some plans may not exist in every Region or OS type; querying the API is far more reliable than memorizing bundle names from old guides.

### 12.2. View Instances and Addresses

~~~bash
aws lightsail get-instances \
  --region ap-southeast-1 \
  --query "instances[].{Name:name,State:state.name,AZ:location.availabilityZone,PublicIP:publicIpAddress,PrivateIP:privateIpAddress,Blueprint:blueprintId,Bundle:bundleId}" \
  --output table

aws lightsail get-instance \
  --region ap-southeast-1 \
  --instance-name lab-lightsail-web
~~~

If the instance does not exist in that account/Region, a by-name lookup returns not found—do not infer it does not exist in any other Region.

### 12.3. View Instance Firewall, Static IPs, and Snapshots

~~~bash
aws lightsail get-instance-port-states \
  --region ap-southeast-1 \
  --instance-name lab-lightsail-web \
  --query "portStates[].{From:fromPort,To:toPort,Protocol:protocol,State:state,CIDRs:cidrs,IPv6:ipv6Cidrs}" \
  --output json

aws lightsail get-static-ips \
  --region ap-southeast-1 \
  --output json

aws lightsail get-instance-snapshots \
  --region ap-southeast-1 \
  --query "instanceSnapshots[].{Name:name,From:fromInstanceName,Created:createdAt}" \
  --output table
~~~

Inspect `portStates` for admin ports unnecessarily open to all IPv4/IPv6 sources, and cross-check with the OS firewall. `get-instance-snapshots` proves snapshots exist, **not that a restore will succeed**.

### 12.4. View Supporting Infrastructure

~~~bash
aws lightsail get-load-balancers \
  --region ap-southeast-1

aws lightsail get-relational-databases \
  --region ap-southeast-1
~~~

Do not create a load balancer or database just because these lists are empty. Each resource type has its own support rules and **separate pricing**.

### 12.5. Prepare Reviews Before Creating or Deleting

APIs such as `create-instances`, `allocate-static-ip`, `open-instance-public-ports`, `create-instance-snapshot`, and `delete-instance` alter infrastructure or cost. In production, run them only after confirming:

1. Exact verified name, Region, blueprint, and bundle.
2. IP/port scope and resource owner.
3. Data backed up prior to the operation.
4. Cost estimate and lab cleanup plan.
5. Rollback/restore plan if the change fails.

## 13. Lightsail Costs: Simple Bundles Still Have Extras Outside the Plan

### 13.1. Line Items to Account For

| Group | Potential Charges | How to Avoid Surprises |
| --- | --- | --- |
| **Instance** | Compute, RAM, root disk, and bundled transfer per hourly/monthly plan | Right-size plan; delete labs when done |
| **Attached disks** | Extra disk capacity and snapshots | Audit unused disks and retention |
| **Snapshots** | Stored snapshot gigabytes | Retain per RPO/policy; do not delete needed backups |
| **Static / public IP** | Charges depending on plan and attachment state | Audit unattached static IPs and current billing rules |
| **Data transfer** | Traffic above plan allowance or separately billed transfer types | Measure egress; avoid serving unnecessary large files |
| **Load balancer** | LB monthly/hourly fee and related usage | Provision only when multiple instances are truly needed |
| **Managed DB / object storage** | Service plans, requests, storage, and transfer | Track size, backups, and traffic |
| **Logging, DNS, other AWS services** | Route 53, CloudWatch, S3, cross-service egress | Include in total application budget |

**Stopping an instance does not stop all charges.** In many cases, Lightsail instance plans continue billing until the resource is **deleted**, even while stopped; disks, snapshots, and IPs also have separate billing lifecycles. Always check current billing rules before treating stop as a cost-saving switch.

### 13.2. Estimation Model

Suppose an architecture runs two instances, one load balancer, and one managed database. Without tying to specific list prices:

~~~text
Total period cost
  ≈ 2 × corresponding instance plan price
  + Lightsail load balancer price
  + managed database plan price
  + attached disk / snapshot storage
  + overage traffic / IP addresses / requests
  + DNS / logs / additional AWS services (if used)
~~~

If uploaded storage grows 30% monthly, include **retention and growth rate** in forecasts rather than only today's bill. If the site serves videos or large files, outbound transfer can outweigh raw request counts.

### 13.3. Trading Off Resource Price Against Operational Effort

A cheap Lightsail instance still requires engineering time to patch the OS, rotate secrets, install monitoring, and recover failures. A more managed service may carry higher resource fees while cutting operational labor. Decide based on **total cost of ownership (TCO)**, including staff time, downtime risk, and security obligations.

## 14. When Is a Lightsail Instance a Good Fit?

### 14.1. Strong Fits

- Small business websites, blogs, or WordPress sites with relatively steady load.
- Demo/MVP pages, prototypes, dev environments, and AWS learning projects.
- Simple web apps needing **OS admin access** without designing a multi-tier VPC.
- Workloads with minimal reliance on advanced AWS services that fit on one or a few instances.
- Small teams wanting **predictable resource bundles** who can accept the chosen model's maintenance windows and RTO.

**Example:** a company needs an informational site and small booking system; a few web pages on Lightsail with tested snapshots, HTTPS, a tight firewall, and a managed database can be a sensible start if security and data rules are met.

### 14.2. When to Consider Moving to Another Platform

- Workloads needing **custom VPC topologies**, multiple subnet routes/Network ACLs, complex PrivateLink, Transit Gateway, or advanced network control.
- Needs for **fine-grained IAM workload roles**, infrastructure-wide automation, and deep AWS service integrations.
- Multi-tier **Auto Scaling**, canary deployment strategies, complex target groups/rules, or ECS/EKS orchestration.
- Highly volatile traffic, very strict SLO/RTO targets, or distributed data workloads.
- CPU, memory, GPU, storage IOPS, or instance families beyond Lightsail bundles.
- Complex automation/IaC/observability, strict compliance, or multiple teams with strict permission boundaries.

This does not mean "Lightsail cannot run production." It **can** run real apps with matching requirements, provided the design proves security, recovery, capacity, and service fit. Conversely, jumping to EC2/EKS too early can add unnecessary complexity.

## 15. Comparing Lightsail Instances with Other AWS Options

| Service | Deployment Unit | Control Level | Primary Ops Responsibility | When to Consider |
| --- | --- | --- | --- | --- |
| **Lightsail instance** | Bundled VPS | OS/app on VM; simplified networking | OS patching, app, backups, TLS, operations | Websites, MVPs, simple workloads |
| **Amazon EC2** | Custom instance type in VPC | Very flexible networking, instances, storage, IAM | OS/app and configured infrastructure | Custom networking, scaling, advanced AWS integrations |
| **Elastic Beanstalk** | Application/environment; typically EC2, LB, and related services underneath | Choose platform and many environment settings | Code/app and parts of OS/config/patching per scope | Deploying web apps on managed platforms with less manual wiring |
| **AWS App Runner** | Source code / container image | Less server control; service-managed deploys | Code, runtime behavior, matching IAM/networking | HTTP web APIs/containers wanting minimal server ops |
| **Amazon ECS on Fargate** | Container task/service | Container networking, scaling, and deployments | Images, tasks/services, IAM, VPC/ALB | Microservices and container workloads with explicit network control |
| **Amazon EKS** | Kubernetes workloads | Kubernetes APIs and controller ecosystem | Cluster/apps, networking, upgrades/add-ons per mode | Proven requirement for Kubernetes |
| **AWS Lambda** | Event-driven function | No server admin; runtime/event model limits | Function code, permissions, integrations | Short API/event jobs needing no always-on VPS |

**What to avoid:** never compare purely by "CPU/RAM sticker price." A small 24/7 API may suit Lightsail or App Runner, while an API requiring private subnets, multiple security zones, and IAM task roles may suit ECS Fargate better—even at the exact same request volume.

### 15.1. Quick Decision Tree

~~~mermaid
flowchart TD
    START["Need to deploy an AWS app"] --> OS{"Need full OS administration?"}
    OS -->|"Yes"| SIMPLE{"Simple workload, standard networking, suitable bundle?"}
    SIMPLE -->|"Yes"| LS["Evaluate Lightsail instance"]
    SIMPLE -->|"No"| EC2["Evaluate EC2 + VPC/ASG/ELB"]
    OS -->|"No"| APP{"HTTP/container app or event-driven?"}
    APP -->|"HTTP app"| RUN["Evaluate App Runner / Beanstalk"]
    APP -->|"Multi-service containers"| ECS["Evaluate ECS Fargate"]
    APP -->|"Explicit Kubernetes need"| EKS["Evaluate EKS"]
    APP -->|"Event / function"| LAM["Evaluate Lambda"]
~~~

*This is a directional aid, not an absolute rulebook. Always check pricing, Region, compliance, latency, data, networking, and operational goals.*

## 16. Roadmap When Lightsail Is No Longer Enough

A product often starts on one instance and evolves:

| Stage | Potentially Suitable Architecture | Signals to Adjust |
| --- | --- | --- |
| **Experimentation** | One instance + snapshots + HTTPS | Demo works, low cost |
| **Small live website** | One instance + static IP + backups/monitoring | Steady traffic, RTO tolerates restore time |
| **Growth** | Multiple instances + Lightsail LB + managed DB/object storage | Need load distribution; cannot hold local state |
| **Higher complexity** | EC2 + ALB/ASG/RDS or App Runner/ECS | Need advanced scaling, routing, IAM, or VPC control |
| **Multi-team / microservices** | ECS/EKS and managed services | Container CI/CD, service discovery, and deep observability in place |

### 16.1. Migrating via Snapshot/Export

Lightsail supports workflows to **export snapshots to Amazon EC2** or launch EC2 resources from Lightsail snapshots for eligible resource types. Never treat this as a "one-click migrate everything" button:

- Verify the OS/blueprint and snapshot **support export**.
- EC2 requires redesigning **VPC, subnets, routes, Security Groups, IPs, IAM roles, EBS, and monitoring**.
- Databases, external disks, object storage, secrets, cron jobs, certificates, and DNS may require separate migration.
- Test the app in the new EC2 environment, measure cutover downtime/data sync, and then switch traffic.
- Keep a rollback plan during DNS TTL and traffic transition.

### 16.2. Migrate by Tier Instead of "Scaling Up One Giant Server"

For a growing website, a cleaner progression is:

1. Decouple the **database** from the web instance and back up data independently.
2. Move **uploads/static assets** to object storage.
3. Refactor the application to be **stateless** and externalize session storage.
4. Set up CI/CD, secrets management, logs, and health checks.
5. Pick the target platform based on real scaling, IAM, and networking needs.

This sequence reduces instance lock-in and enables thorough testing before moving production data.

## 17. Case Study: Booking Website for a Small Business

### 17.1. Context

A business needs a website with appointment booking and reminder emails:

~~~text
Daily visitors:       2,000 users/day
Peak traffic:         ~15–25 req/s
Features:             login, booking, image uploads
Data:                 customers and booking transactions
Operations staff:     one developer also acting as admin
Initial goal:         simple deployment, predictable cost
~~~

Numbers are illustrative; you cannot derive a bundle solely from visitor counts without benchmarking. Since the system stores personal data, enforce access control, encryption, and organizational data compliance.

### 17.2. Phase 1: Choosing Lightsail

A candidate setup might include:

- One Linux Lightsail instance running the app and Nginx.
- Static IP, DNS, and HTTPS.
- A managed database, or at minimum verified app/DB backups.
- Uploads stored in object storage, not locked onto the root disk.
- Firewall allowing only web ports and SSH from admin networks.
- Snapshots, backups, metrics, alerts, and budgets.

**Rationale:** minimal infrastructure parts, fast to launch, and manageable by a small team that owns OS/app ops. Limitation: with one instance, an AZ/host outage or maintenance causes downtime.

### 17.3. When Traffic Grows and Uptime Becomes Critical

Six months later, online booking is the primary revenue channel; an hour of downtime hurts many customers. The team observes:

- CPU stays persistently high with depleted burst capacity.
- Uploads sit on the local filesystem, blocking horizontal web scaling.
- Snapshot restores take too long for the new RTO.
- Co-locating the DB on the instance makes restores and upgrades risky.

Sensible next steps:

1. Move uploads and stateful data off the instance and decouple the DB.
2. Load-test multiple instances behind a load balancer if requirements still fit within Lightsail.
3. Define the new RTO/RPO and choose an HA-capable database plan.
4. If complex networking, IAM, scaling, or deployment pipelines are required, evaluate **App Runner / ECS Fargate / EC2** for the new architecture.

**Conclusion:** neither cling to Lightsail at all costs nor leap straight to EKS prematurely. The right service is the one that satisfies business goals at manageable cost and complexity.

## 18. Reinforcement Exercises

### Exercise 1 — Choose Lightsail or EC2?

Team A needs a company WordPress blog with predictable load and a single admin. Team B needs multi-subnet networking, Transit Gateway, per-workload IAM roles, Auto Scaling, and dozens of microservices.

**Hint:** Team A should **evaluate Lightsail** if comfortable managing OS, backups, and uptime; Team B typically needs **EC2/ECS/EKS with a custom VPC** or a matching platform rather than forcing dozens of microservices onto a few Lightsail instances.

### Exercise 2 — Why Is a Static IP Useful?

A website points its `A` record to the instance's current public IP, but after replacing the instance, the IP changes and DNS still points to the old address.

**Hint:** attach a **static IP** to the Lightsail instance where supported; when replacing the server, perform a controlled cutover and check DNS TTL. Never treat default dynamic public IPs as permanent.

### Exercise 3 — SSH Misconfiguration

A Linux VM opens TCP 22 to all IPv4/IPv6 addresses. A developer wants to leave it open so they can always connect.

**Hint:** this invites brute-force and Internet scanning attacks. Restrict to admin networks, protect private keys, disable/limit password login per OS policy, monitor auth logs, and prepare an approved emergency access method.

### Exercise 4 — Are Snapshots Enough for RPO?

An order-taking app takes a nightly instance snapshot at 00:00. The server fails at 17:00 the next day. The business requires a maximum RPO of 15 minutes.

**Hint:** daily snapshots fail a 15-minute RPO. You need a different backup/replication frequency and strategy, plus **restore tests** to measure actual RTO.

### Exercise 5 — Two Instances Behind an LB, Yet Images Disappear

A user uploads an image hitting instance A; the next request is routed by the LB to instance B and gets a 404. What must change?

**Hint:** the app stores state on **local disk**. Move images to object storage or a shared store, store metadata/keys in the DB, and ensure both instances read/serve images identically.

### Exercise 6 — Estimating Fault-Tolerance Capacity

Two instances safely serve up to 80 req/s each in benchmarks; peak traffic is 120 req/s. One instance abruptly drops offline.

**Hint:** remaining capacity is 80 req/s—**not enough** for 120 req/s. Provision sufficient standby capacity, autoscaling, or load-shedding plans aligned with RTO/SLO; an LB does not create compute capacity.

### Exercise 7 — Calculating Full Cost

A manager budgets only the bundle price, ignoring snapshots, data transfer, managed DB, and load balancer fees. Add an estimation checklist covering resources, expected traffic, ownership, and budget alerts.

**Hint:** the bundle price is only **part** of TCO. Account for all active resources, stopped-instance billing rules, snapshot retention, static IPs, disks, and related services.

### Exercise 8 — Platform Migration Plan

An API currently on Lightsail needs private connectivity to multiple AWS services, automated workload identity, canary CI/CD, and multiple deployments per day. Propose criteria for choosing among App Runner, ECS Fargate, or EC2.

**Hint:** compare VPC ingress/egress needs, IAM roles, deployment/revision mechanics, rollbacks, scaling, and operational overhead; exporting a VM snapshot does not replace redesigning IAM, networking, and automated rollouts.

## 19. Common Misconceptions

| Statement | Correct Understanding |
| --- | --- |
| "Lightsail is managed web hosting where AWS patches everything automatically." | A Lightsail instance is a **VM**; you still manage the OS, app, and security. |
| "A WordPress blueprint guarantees plugins and the DB are backed up properly." | You still need a separate backup plan and verified restore tests. |
| "The instance is stopped, so it costs nothing." | Check resource-lifecycle billing rules; stopping does not necessarily halt plan charges. |
| "An instance's public IP is always permanent." | Understand IP lifecycles; use a static IP when a stable address is required. |
| "Opening firewall port 443 makes HTTPS work automatically." | You also need a web listener, TLS certificate, DNS, and matching OS firewall rules. |
| "Snapshot = HA." | Snapshots provide **recoverability**, not automatic traffic failover. |
| "Having a load balancer is enough to survive an AZ failure." | You also need sufficient instance capacity, externalized state, HA DBs, and valid egress. |
| "The biggest bundle is always the best way to scale." | Vertical scaling keeps a single point of failure and hits upper ceiling limits. |
| "Lightsail has identical VPC/IAM features to EC2." | Lightsail simplifies and constrains certain settings; verify actual requirements. |
| "Lightsail is only for demos." | It can run small production apps if availability, security, and data goals are met. |
| "EC2/EKS is always a better choice." | Operational complexity and cost can far exceed what small apps require. |

## 20. Pre-Production Decision Checklist

- [ ] Workload purpose is clear (website, API, CMS, or internal app) with an assigned operations owner.
- [ ] Blueprint, bundle, CPU burst/RAM/storage, and Region/AZ tested under expected load.
- [ ] Public IPv4/IPv6 model, static IP, DNS, TLS, and instance replacement steps documented.
- [ ] Lightsail firewall and OS firewall restrict SSH/RDP and expose only required app ports.
- [ ] OS patching, runtime updates, secret handling, user permissions, and authentication processes defined.
- [ ] Uploads, databases, sessions, and logs placed where backup and recovery strategies apply.
- [ ] Snapshots/backups have retention rules, regular checks, and tested restores.
- [ ] RPO/RTO, health checks, capacity, and single-instance/AZ failure impact quantified.
- [ ] Metrics, log rotation, alerts, budgets, and owners configured.
- [ ] Lightsail network/IAM/scaling limits checked against both current and future needs.
- [ ] Lightsail compared with EC2, App Runner, Elastic Beanstalk, ECS, or Lambda on TCO and operations.
- [ ] Lab cleanup plan and platform migration path defined for future growth beyond limits.

## 21. Key Takeaways

A **Lightsail instance** is a simplified VPS option on AWS: pick a **blueprint**, **bundle**, and **Region/AZ**, manage **IPs/firewalls/DNS**, and install and operate your application on the chosen OS. It helps small teams get simple applications online quickly with predictable resource plans.

Key limitations go beyond raw machine sizing: **one instance is a single point of failure**, the OS and app still need maintenance, backups do not equal HA, and complex networking/IAM/scaling can outgrow Lightsail. When multi-AZ resilience, shared data, automated deployments, and deeper scalability are needed, evaluate Lightsail's supported load balancers/databases **or** transition to dedicated AWS services.

Choose Lightsail when it is **good enough for your business and operational requirements**, not solely for simple bundle pricing. Move to higher-capability services when security, RTO/RPO, scaling, or automation targets demand it.

### Official AWS Documentation

- [What is Amazon Lightsail?](https://docs.aws.amazon.com/lightsail/latest/userguide/what-is-amazon-lightsail.html) — Lightsail concepts and components.
- [Amazon Lightsail User Guide](https://docs.aws.amazon.com/lightsail/latest/userguide/) — creating/managing instances, blueprints, bundles, storage, and networking.
- [Amazon Lightsail pricing](https://aws.amazon.com/lightsail/pricing/) — plans, transfer allowances, and related service charges.
- [Amazon Lightsail static IP addresses](https://docs.aws.amazon.com/lightsail/latest/userguide/understanding-static-ip-addresses-in-amazon-lightsail.html) — using static IPs and DNS.
- [Lightsail networking and firewalls](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-editing-firewall-rules.html) — inbound ports, sources, and IP versions.
- [Amazon Lightsail snapshots](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-snapshots.html) — instance and block storage backups/restores.
- [Lightsail load balancers](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-load-balancers.html) — load balancing and HTTPS support.
- [Lightsail managed databases](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-relational-databases.html) — database options.
- [AWS CLI Lightsail reference](https://docs.aws.amazon.com/cli/latest/reference/lightsail/index.html) — `get-bundles`, `get-instances`, `get-instance-port-states`, and snapshots.
- [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/) — AWS infrastructure vs. customer workload responsibilities.

# Hands-On Lab: Deploying a Java Service on Compute Engine

> **Chapter:** Compute Engine  
> **Lesson:** Hands-On Lab: Deploying a Java Service on Compute Engine  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners need to know how to **choose services, protect resources, automate releases, and track reliability and cost**. This lesson turns those principles into a hands-on lab: deploying an HTTP API written in **Java** onto a **Google Compute Engine** virtual machine, running it as a system service, and testing it via a secure administrative path.

The goal is to understand the **end-to-end path** from source code → compilation → VM → Java process → network port → health checks → logs → operations. The example uses **JDK 17** and the minimal HTTP server built into the JDK so learners do not depend on Maven or frameworks. Once finished, you can swap the sample program for a **Spring Boot JAR** or a real Java app, while adding production requirements such as TLS, authentication, input validation, autoscaling, load balancing, and application observability.

**Cost and security warning:** `gcloud compute instances create`, creating VPCs/subnets, firewall rules, service accounts, and installing packages **modify real resources**. Run them only in an approved sandbox project; a running VM, persistent disk, external IPv4 address, network traffic, Cloud NAT, and logging can all incur charges. Never run creation/deletion commands against production without a formal change process.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Describe operator responsibilities when choosing **Compute Engine** over Cloud Run or GKE.
2. Create a VPC, subnet, restricted firewall ingress rule, and Debian VM in an authorized project and zone.
3. Distinguish permissions of the **VM administrator** from the **VM-attached service account** and the Linux OS service account running the app.
4. Compile a minimal Java service, package a JAR, and install it into a service directory with proper file permissions.
5. Use **systemd** to manage restarts, configure JVM flags, and inspect status and logs with `journalctl`.
6. Reach the HTTP API over **IAP SSH port forwarding** without exposing application ports to the Internet.
7. Establish a checklist for monitoring, version releases, rollbacks, backups, and resource cleanup.
8. Identify what else is required when graduating from a single VM to a production environment with a **managed instance group (MIG)** and load balancer.

## 2. Lab Architecture

~~~mermaid
flowchart LR
    D["Learner<br/>Cloud Shell / gcloud"]
    D --> I["IAP TCP forwarding<br/>SSH 22"]
    I --> V["Compute Engine VM<br/>Debian 12 / JDK 17"]
    V --> S["systemd: orders-api"]
    S --> A["Java HTTP API<br/>127.0.0.1:8080"]
    S --> J["journald"]
    VM["Custom-mode VPC<br/>Subnet + firewall"] -. "Applied to" .-> V
    SA["Runtime service account<br/>Least-privilege IAM"] -. "Attached to VM" .-> V
    D -. "SSH -L local port 18080" .-> A
~~~

**Intentional design decisions:**

- **Single VM only** to keep foundational steps clear. This is **not an HA architecture**; a zone, VM, boot disk, or process failure interrupts service.
- The API **binds solely to `127.0.0.1:8080` inside the VM**, so it **does not listen on the VM's network IP**. We test through SSH port forwarding rather than opening TCP/8080.
- The VM receives an **ephemeral external IPv4** in the lab to easily install OS packages from Debian repositories; the custom-mode VPC firewall opens zero Internet ingress except SSH from allowed IAP ranges. **Having an external IP does not make the service public automatically.**
- When deploying a VM **without an external IP**, design an appropriate outbound path (such as Public NAT for downloading packages and artifacts) while still using IAP for administration.
- The runtime service account receives no broad roles because the sample service calls no Google Cloud APIs. SSH login identities remain governed by IAM and OS Login/IAP policies.

### 2.1. Sample Parameters

| Component | Illustrative Value | Meaning |
|---|---|---|
| Project | `PROJECT_ID` | Sandbox project with billing and appropriate permissions |
| Region | `asia-southeast1` | Singapore; chosen as an example, not mandatory |
| Zone | `asia-southeast1-a` | One zone within the sample region |
| VPC | `java-lab-vpc` | Custom-mode VPC network |
| Subnet | `java-lab-subnet` | `10.60.0.0/24` |
| Firewall | `java-lab-allow-iap-ssh` | Allows only IAP TCP forwarding to TCP/22 on VMs with target tag |
| VM | `java-orders-lab` | Debian 12, illustrative `e2-standard-2` |
| Runtime service account | `java-lab-runtime@PROJECT_ID.iam.gserviceaccount.com` | Workload identity; no app IAM roles granted yet |
| Linux service user | `javaorders` | Avoids running the app as root |
| Application | `/opt/java-orders/orders-api.jar` | Deployed JAR artifact |
| API listen address | `127.0.0.1:8080` | Loopback port inside VM only |
| Port forwarding | `localhost:18080 → VM:127.0.0.1:8080` | Learner accesses via SSH through IAP |

**Academic scope:** this guide does not assume your project already grants VPC or SSH creation permissions. If you only have read access, you can still complete the design, command review, and expected-output analysis without executing mutations.

## 3. Prerequisites Before Creating Resources

You need:

- A Google account authorized on a **sandbox project** linked to a billing account.
- **Google Cloud CLI (`gcloud`)** in Cloud Shell or an authenticated workstation.
- Permissions to create VMs, VPCs, subnets, firewalls, and service accounts **only when running a live lab**, plus permission to attach the service account to VMs.
- **IAP-secured Tunnel User** (`roles/iap.tunnelResourceAccessor`) and appropriate **OS Login** role (`roles/compute.osLogin`, or OS Login Admin only if genuinely required), plus VM inspection permissions.
- Organization policies allowing an ephemeral external IP in the sandbox. If your organization blocks external IPs, use the **no external IP + designed outbound NAT** pattern instead of trying to bypass policy.
- Basic Linux familiarity: SSH, `sudo`, `systemctl`, `journalctl`, `curl`, `ss`.

Before creating anything, verify:

~~~bash
gcloud auth list
gcloud config get-value project
gcloud projects describe PROJECT_ID \
  --format="yaml(projectId,name,projectNumber)"
gcloud compute zones describe asia-southeast1-a \
  --project=PROJECT_ID \
  --format="yaml(name,region,status)"
~~~

If `gcloud config get-value project` prints a different project, **pass `--project=PROJECT_ID` explicitly on every mutating command**, as shown in the examples below. Never rely solely on the default Cloud Shell project.

### 3.1. Estimating Costs and Avoiding Free-Tier Misconceptions

An `e2-standard-2` VM and persistent disk **do not automatically fall under the Free Tier**. External IPv4 addresses can also incur charges even while attached to a VM; auxiliary services like logging and egress have their own pricing rules.

Before starting the lab, open **Billing → Budgets & alerts** (if permitted) to review budgets, configure alerts, and record recipients. **Standard budget alerts do not automatically stop spending.** Log your start/end times, list of resources scheduled for deletion, and accountable owner.

### 3.2. Standardizing Permissions and Source Config

Use properly formatted placeholders and substitute real names before running. `PROJECT_ID`, `ZONE`, `VM_NAME`, and `SUBNET_NAME` in this guide are not pre-existing resources.

**Never copy private keys, API tokens, database passwords, or service account JSON keys into startup scripts, command history, or repositories.** The sample Java app needs no secrets; when moving to production, use Secret Manager and managed identities by design.

## 4. Step 1 — Creating a Private Network for the Lab

A **custom-mode VPC** lets learners explicitly define subnets, firewalls, and network boundaries. Do not blindly reuse a default VPC without knowing its default rules, as some default firewall rules open SSH ingress from very broad ranges.

The following commands **modify** your project:

~~~bash
# Create a custom-mode VPC.
gcloud compute networks create java-lab-vpc \
  --project=PROJECT_ID \
  --subnet-mode=custom

# Create a regional subnet with a private CIDR.
gcloud compute networks subnets create java-lab-subnet \
  --project=PROJECT_ID \
  --network=java-lab-vpc \
  --region=asia-southeast1 \
  --range=10.60.0.0/24

# Allow SSH only from IAP TCP forwarding to VMs carrying the lab tag.
gcloud compute firewall-rules create java-lab-allow-iap-ssh \
  --project=PROJECT_ID \
  --network=java-lab-vpc \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --rules=tcp:22 \
  --source-ranges=35.235.240.0/20 \
  --target-tags=java-lab-ssh
~~~

**Explanation:**

- A VPC is **global**; a subnet is **regional**.
- `10.60.0.0/24` is an example; check for **CIDR overlap** with other VPCs, peering, or on-premises networks if shared.
- Source range `35.235.240.0/20` is the IPv4 range for **IAP TCP forwarding** in eligible SSH setups; it opens only TCP/22 and targets only VMs tagged `java-lab-ssh`.
- No rule in this example opens TCP/8080, TCP/80, or TCP/443 to the VM. A custom VPC's implied ingress rule denies unsolicited inbound traffic.
- **Hierarchical firewall policies** or **network firewall policies** at the org/folder/VPC level can further restrict traffic; this rule cannot override higher-priority deny rules.

### 4.1. Why Does the Lab Use an External IP Despite Exposing No Public Service?

The external IP here serves **outbound** access to Debian repositories when installing the JDK. In organizations with established networking foundations, a cleaner, more secure setup is a **VM without an external IP**, using **Public NAT** for needed egress and IAP for SSH. However, never pass `--no-address` and expect `apt-get update` to reach the Internet automatically: **Private Google Access does not replace NAT for general public package repositories**.

When auditing networking, never conflate these three separate things:

1. The VM has an external IPv4 address.
2. The VPC has a default route to the Internet and permits egress.
3. An ingress allow rule exists for the application port.

Item (1) alone does not let strangers on the Internet call your API; item (3) is part of allowing external ingress, alongside TLS, application auth, and OS firewalls.

## 5. Step 2 — Creating the Runtime Service Account and VM

### 5.1. Separating Administrator Identity from Application Identity

The **learner** logs into Cloud Shell as a managed user with resource-creation permissions. The **VM** attaches a dedicated Google service account. The Java process must **not** run as Linux `root`.

Three identity layers:

| Identity | Used For | Recommended Permissions |
|---|---|---|
| Managed user / Google account | Deploying, SSHing, and maintaining the VM | Sandbox roles plus needed IAP/OS Login roles |
| VM Google Cloud service account | Calling Google APIs from the app when needed | Resource-specific minimal roles; none needed for demo |
| Linux user `javaorders` | Running the Java OS process | Read-only on JAR and required directories only |

Create a dedicated service account for the lab:

~~~bash
gcloud iam service-accounts create java-lab-runtime \
  --project=PROJECT_ID \
  --display-name="Java Compute Engine lab runtime"
~~~

Because this account only serves the sample HTTP API without calling Google Cloud APIs, **do not grant Editor or Owner**. Once a real app needs Cloud Storage or Pub/Sub, grant minimal roles on exact buckets or topics and verify via IAM Policy Troubleshooter.

### 5.2. Creating the Virtual Machine

~~~bash
gcloud compute instances create java-orders-lab \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --machine-type=e2-standard-2 \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=20GB \
  --boot-disk-type=pd-balanced \
  --subnet=java-lab-subnet \
  --tags=java-lab-ssh \
  --labels=env=lab,app=orders-api \
  --metadata=enable-oslogin=TRUE \
  --service-account=java-lab-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --scopes=cloud-platform
~~~

**Rationale for key flags:**

- `e2-standard-2` gives ample headroom for the JDK and test API, purely as a lab example rather than production sizing.
- `debian-12` selects the image family in `debian-cloud`, resolving to the latest active version at creation time.
- `--metadata=enable-oslogin=TRUE` enables **OS Login** SSH management where permitted by org policy.
- `--service-account=...` sets the **runtime identity**; attaching it may require **Service Account User** (`iam.serviceAccounts.actAs`).
- `--scopes=cloud-platform` sets a broad OAuth access scope, yet **grants zero IAM roles** to the service account. Actual API access remains governed by IAM and org policies. For new setups, enforce least privilege through IAM.
- Omitting `--no-address` in this basic flow allows an ephemeral external IPv4 per network and project policy. **No ingress allow rule** is opened for the app.

**If the command fails:** read the exact error regarding IAM, disabled APIs, billing, quotas, zonal capacity, image, or Organization Policy. Never resolve errors by broadly granting `roles/owner`.

### 5.3. Verifying VM and Network Configuration

~~~bash
gcloud compute instances describe java-orders-lab \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --format="yaml(name,status,machineType,networkInterfaces,serviceAccounts,tags,metadata)"

gcloud compute firewall-rules describe java-lab-allow-iap-ssh \
  --project=PROJECT_ID
~~~

Verify VM status `RUNNING`, internal IP, network, tag, and runtime service account. Confirm no other org/folder/VPC firewall rule inadvertently exposes the app.

## 6. Step 3 — Logging into the VM via IAP

In Cloud Shell, run:

~~~bash
gcloud compute ssh java-orders-lab \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --tunnel-through-iap
~~~

`--tunnel-through-iap` forces SSH over IAP TCP forwarding. This works even when the VM has no external IP, given valid IAP/OS Login roles, matching firewall rules, and standard SSH config.

Once inside Debian:

~~~bash
whoami
hostname
cat /etc/os-release
java -version || true
sudo systemctl status ssh --no-pager
ip -br address
~~~

These read-only checks confirm you are inside the Debian VM. `java -version` will report `command not found` before installing the JDK; that is expected.

### 6.1. If SSH Fails

| Symptom | Likely Causes to Check | Resolution |
|---|---|---|
| `PERMISSION_DENIED` opening IAP tunnel | Missing `roles/iap.tunnelResourceAccessor` or policy block | Verify caller identity and IAM on the exact VM/IAP resource |
| OS Login rejected | Missing `roles/compute.osLogin`, wrong role, or org policy | Inspect OS Login settings and IAM bindings |
| SSH timeout | Missing IAP TCP/22 firewall, VM stopped, route/OS SSHD fault | Verify target tags, firewall rules, VM state, and OS logs |
| `NOT_FOUND` | Wrong project/zone or missing view permissions | Run `instances describe` and verify project selector |
| Cannot assign external IP | Organization Policy restriction | Use private VM + Public NAT properly; do not bypass |
| Logged in yet code is missing | Connected to a different VM or deploy hasn't run | Check `hostname` and copy/build steps |

**IAP only controls the network transport path**; it does not replace OS Login, SSH authentication, or IAM for actions inside the VM.

## 7. Step 4 — Installing Java and Creating the Sample API

Inside the **SSH session on the VM**, update package lists and install JDK 17:

~~~bash
sudo apt-get update
sudo apt-get install -y openjdk-17-jdk-headless curl
java -version
javac -version
~~~

Debian 12 provides OpenJDK 17 in its standard repositories. If your organization uses a custom mirror or newer image with different package names, check the appropriate package name; never download a JDK from untrusted third-party URLs just because `apt` fails.

### 7.1. Writing a Framework-Free Java Service

Create `OrdersApi.java` in your SSH user's working directory:

~~~bash
cat > OrdersApi.java <<'EOF'
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;

public final class OrdersApi {
    public static void main(String[] args) throws IOException {
        String host = System.getenv().getOrDefault("BIND_HOST", "127.0.0.1");
        int port = Integer.parseInt(System.getenv().getOrDefault("PORT", "8080"));

        HttpServer server = HttpServer.create(
            new InetSocketAddress(host, port), 64);

        server.createContext("/healthz", exchange -> {
            if (!"GET".equals(exchange.getRequestMethod())) {
                reply(exchange, 405, "text/plain", "Method Not Allowed\n");
                return;
            }
            reply(exchange, 200, "text/plain", "OK\n");
        });

        server.createContext("/api/orders", exchange -> {
            if (!"GET".equals(exchange.getRequestMethod())
                    || !"/api/orders".equals(exchange.getRequestURI().getPath())) {
                reply(exchange, 405, "text/plain", "Method Not Allowed\n");
                return;
            }
            reply(exchange, 200, "application/json",
                  "{\"orders\":[],\"source\":\"compute-engine\"}\n");
        });

        server.setExecutor(Executors.newFixedThreadPool(4));
        System.out.println("Orders API listening on " + host + ":" + port);
        server.start();
    }

    private static void reply(HttpExchange exchange, int status,
                              String contentType, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", contentType + "; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }
}
EOF
~~~

This is a **mock API**: `GET /healthz` returns `200 OK` and `GET /api/orders` returns an empty JSON list. There is no database and no customer data. For a real API, a Spring Boot app can connect to Cloud SQL, Cloud Storage, or Pub/Sub via its runtime service account and proper permissions.

### 7.2. Compiling and Packaging

~~~bash
javac --add-modules jdk.httpserver OrdersApi.java

jar --create \
  --file orders-api.jar \
  --main-class=OrdersApi \
  OrdersApi.class

ls -lh OrdersApi.class orders-api.jar
~~~

The `jdk.httpserver` module is a minimal built-in JDK HTTP server suitable for **learning**, **not** a full-featured production API server. `jar --main-class` produces an executable JAR with an entry point.

### 7.3. Smoke-Testing Before Configuring systemd

~~~bash
java --add-modules jdk.httpserver \
  -Xms64m -Xmx256m \
  -jar orders-api.jar
~~~

In a **second SSH session on the same VM**, run:

~~~bash
curl --fail --show-error http://127.0.0.1:8080/healthz
curl --fail --show-error http://127.0.0.1:8080/api/orders
~~~

Expected output:

~~~text
OK
{"orders":[],"source":"compute-engine"}
~~~

Stop the manual test run with `Ctrl+C` in the Java terminal before enabling systemd; if port 8080 stays bound, systemd will fail with `Address already in use`.

## 8. Step 5 — Running Java as a Linux Service via systemd

Closing a terminal window or disconnecting SSH must not kill the application. `systemd` manages the Java process independently, starts it automatically after reboots, and routes stdout/stderr to the journal.

### 8.1. Creating a Dedicated Non-Privileged Linux User

~~~bash
sudo useradd \
  --system \
  --home-dir /opt/java-orders \
  --shell /usr/sbin/nologin \
  javaorders

sudo install -d \
  -o javaorders -g javaorders -m 0750 \
  /opt/java-orders

sudo install \
  -o javaorders -g javaorders -m 0640 \
  orders-api.jar /opt/java-orders/orders-api.jar
~~~

If user `javaorders` already exists when repeating the lab, skip `useradd`; verify `id javaorders` and directory ownership instead of creating a duplicate. Mode `0640` lets the service user read the JAR while restricting replacements to admins.

**Never run the app as `root`** just to sidestep permission errors. When a real app must write data, create a dedicated directory such as `/var/lib/orders-api` with minimal write permissions.

### 8.2. Creating the Unit File

~~~bash
sudo tee /etc/systemd/system/orders-api.service > /dev/null <<'EOF'
[Unit]
Description=Orders API demo on Compute Engine
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=javaorders
Group=javaorders
WorkingDirectory=/opt/java-orders
Environment=PORT=8080
Environment=BIND_HOST=127.0.0.1
ExecStart=/usr/bin/java --add-modules jdk.httpserver -Xms64m -Xmx256m -jar /opt/java-orders/orders-api.jar
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now orders-api
~~~

**Key configuration notes:**

- `User=javaorders` and `Group=javaorders`: runs without root privileges.
- `ExecStart`: invokes Java via absolute path using the JAR installed under `/opt`.
- `-Xms64m -Xmx256m`: illustrative JVM heap only, not production sizing for Spring Boot or live traffic. OS memory, heap, metaspace, and native allocations still need separate sizing and monitoring.
- `Environment=BIND_HOST=127.0.0.1`: binds only to loopback. Must be updated architecturally before placing behind a load balancer.
- `Restart=on-failure`: restarts the process if it exits with an error; does not replace active health checks, readiness/liveness probes, or failover.
- `NoNewPrivileges`, `ProtectHome`, `ProtectSystem`, and `PrivateTmp`: baseline systemd sandboxing; real applications may require adjusting write paths and syscalls.

If the service fails to start, inspect logs rather than switching to `User=root`:

~~~bash
sudo systemctl status orders-api --no-pager
sudo journalctl -u orders-api -n 100 --no-pager
sudo ss -lntp | grep ':8080' || true
~~~

### 8.3. Verifying Startup Enablement

~~~bash
sudo systemctl is-enabled orders-api
sudo systemctl is-active orders-api
curl --fail --show-error http://127.0.0.1:8080/healthz
~~~

An application enabled via `systemctl enable` starts automatically after reboots, yet **still lacks HA**, and **reboots drop active connections**. Zero-downtime demands multiple instances, load balancing, and rolling deployments.

## 9. Step 6 — Testing from Cloud Shell via IAP Port Forwarding

Close the interactive VM SSH session after confirming systemd is running, then open **a Cloud Shell terminal** to start SSH port forwarding:

~~~bash
gcloud compute ssh java-orders-lab \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --tunnel-through-iap \
  -- -N -L 18080:127.0.0.1:8080
~~~

This forwards **Cloud Shell `localhost:18080` → VM `localhost:8080`** over SSH through IAP. The terminal stays open without printing a shell prompt—expected behavior with `-N`. Leave this terminal open while testing.

Open a **second Cloud Shell terminal** and run:

~~~bash
curl --fail --show-error http://127.0.0.1:18080/healthz
curl --fail --show-error http://127.0.0.1:18080/api/orders
~~~

Expected output:

~~~text
OK
{"orders":[],"source":"compute-engine"}
~~~

**Why not expose TCP/8080 to the Internet?**

1. This demo API lacks TLS, authorization, rate limiting, and full input validation.
2. Binding to loopback lets you test functionality without exposing the service publicly.
3. IAP governs **SSH transport** and IAM; it does not turn a raw demo HTTP server into a hardened public API.
4. Serving real users requires proper ingress via a load balancer, TLS, user authentication, and application policies.

To stop port forwarding, press `Ctrl+C` in the SSH tunnel terminal. Stopping the SSH tunnel **does not stop** `orders-api` running under systemd.

### 9.1. Distinguishing Three Types of Verification

| Test | What It Verifies | What It Does NOT Prove |
|---|---|---|
| `curl 127.0.0.1:8080` **on VM** | JVM bound the port and HTTP handler responds locally | Whether anything outside the VPC can reach it |
| `curl 127.0.0.1:18080` **from Cloud Shell via SSH -L** | IAP + SSH + port forward + JVM all work | Whether port 8080 is open on the VPC |
| HTTPS call via production load balancer | End-to-end client → frontend → backend → app path | Whether all zones/instances are healthy from one request |

**Avoid confusion:** port forwarding tunnels inside SSH, so you **do not need** to open TCP/8080 ingress in the VPC firewall. You only need the SSH/IAP path to the VM and the process listening on loopback inside the VM.

## 10. Step 7 — Observing Status, Logs, and Resources

### 10.1. Checking the Service on Linux

~~~bash
sudo systemctl status orders-api --no-pager
sudo journalctl -u orders-api --since "30 minutes ago" --no-pager
sudo journalctl -u orders-api -f
ps -eo pid,user,%cpu,%mem,cmd | grep '[j]ava'
free -h
df -h
sudo ss -lntp | grep ':8080' || true
~~~

- `journalctl -u` reads stdout/stderr logs of the systemd-managed process.
- `-f` tails logs live; press `Ctrl+C` to stop tailing without **stopping the service**.
- `free -h` inspects host RAM; `df -h` inspects filesystem usage. Java heap is only part of the total memory footprint.
- `ss` shows which address and port the app listens on. Here we expect `127.0.0.1:8080`, not `0.0.0.0:8080`.

### 10.2. Cloud Monitoring and Cloud Logging

Google Cloud collects baseline VM metrics automatically. For deeper **memory, disk, and process** metrics and centralized OS log collection, deploy the **Ops Agent** per official documentation.

Safe rollout flow:

1. Identify the project/VM and confirm organizational approval to install the Ops Agent.
2. Verify the runtime service account holds required logging/metrics roles, such as `roles/logging.logWriter` and `roles/monitoring.metricWriter` at appropriate scope.
3. Install the Ops Agent matching the OS image and configure log/metric pipelines for the workload.
4. Confirm `orders-api.service` logs actually arrive; never assume all `journald` streams forward to Cloud Logging without configuration.
5. Build dashboards and alerts for availability, CPU, memory, disk, startup failures, and application response times based on real telemetry.

**Never grant `Editor` to the VM service account to fix log ingestion errors.** Identify the exact missing permission and role and apply it through IAM governance.

### 10.3. Metrics to Watch When Moving to Production

| Category | Metric / Signal | Risk to Detect |
|---|---|---|
| Virtual Machine | CPU, memory pressure, disk utilization | VM resource exhaustion or full disk |
| JVM | Heap, GC pauses, thread pools, file descriptors | OOMs, latency spikes, or leaks |
| HTTP API | RPS, p95/p99 latency, 4xx/5xx, health/readiness | User errors even while VM stays `RUNNING` |
| Operating System | Reboots, package updates, process restarts | Missing serving processes |
| Networking | Port binding, firewalls, VPC routes, NAT/egress | Valid IP yet unreachable |
| Data | Cloud SQL connections, timeouts, backup status | DB faults breaking API calls |
| Security | Failed SSH attempts, IAM changes, patch status, secrets | Unauthorized access or credential leaks |
| Cost | VM hours, disks, external IPs, network egress/logging | Lab/prod budget overruns |

The demo API has only a basic `/healthz`; in real apps, **liveness** and **readiness** should be distinct. Readiness can safely verify critical dependencies without running expensive probes that overload the app or expose sensitive internals.

## 11. Step 8 — Release Versioning and Rollback Workflow

Getting a service running once is not enough for repeated deployments. You need **versioned artifacts**, release traceability, and a tested rollback path.

### 11.1. Updating the JAR on the Demo VM

After building and testing a new JAR in dev:

1. Verify source commit, Java target version, and artifact checksum.
2. Transfer the artifact via an approved channel such as `gcloud compute scp ... --tunnel-through-iap` or pull from Artifact Registry/Cloud Storage using the runtime identity.
3. Back up the previous JAR for rollback.
4. Stop the service within a change window, install the new JAR owned by `javaorders`, and restart.
5. Verify `/healthz` and `/api/orders`, inspecting `journalctl` and metrics.
6. If checks fail, restore the previous JAR and re-verify.

Example **commands inside the VM**, assuming the new artifact sits at `$HOME/orders-api-new.jar`:

~~~bash
# Back up current artifact for rollback on this lab VM.
sudo cp -a /opt/java-orders/orders-api.jar \
  /opt/java-orders/orders-api.jar.backup

# Install new artifact owned by the service user.
sudo install \
  -o javaorders -g javaorders -m 0640 \
  "$HOME/orders-api-new.jar" \
  /opt/java-orders/orders-api.jar

sudo systemctl restart orders-api
sudo systemctl is-active orders-api
curl --fail --show-error http://127.0.0.1:8080/healthz
~~~

If health checks fail:

~~~bash
sudo systemctl stop orders-api
sudo cp -a /opt/java-orders/orders-api.jar.backup \
  /opt/java-orders/orders-api.jar
sudo systemctl start orders-api
sudo systemctl status orders-api --no-pager
~~~

This is an in-place file rollback on **one VM**—**not** a zero-downtime deployment. An older JAR may also be incompatible with newer database schema changes, so production must plan **application and data** rollbacks together.

### 11.2. Why Use CI/CD and an Artifact Repository?

A production pipeline typically follows:

~~~mermaid
flowchart LR
    G["Git commit / Pull request"]
    G --> CI["Build + unit tests + SAST/dependency checks"]
    CI --> AR["Versioned JAR/image<br/>Artifact Registry"]
    AR --> CD["Deploy to staging"]
    CD --> AP["Approval + policy checks"]
    AP --> R["MIG rolling update / canary"]
    R --> OBS["Health checks + monitoring"]
    OBS --> RB["Proceed or roll back"]
~~~

This lab compiles directly on the VM to demonstrate the mechanics. Production environments should **build once and deploy the exact tested artifact everywhere**, using dedicated CI/CD identities, restricting human `ssh`, and retaining release audit trails.

## 12. Exposing the Java API Externally: From One VM to Production Architecture

Never expose a minimal HTTP server directly via `--address=0.0.0.0` and `0.0.0.0/0:8080`. Better production patterns exist:

### 12.1. External Application Load Balancer + MIG

~~~mermaid
flowchart TB
    U["Internet clients"]
    U --> DNS["Cloud DNS: api.example.com"]
    DNS --> HTTPS["External Application Load Balancer<br/>HTTPS + certificate"]
    HTTPS --> MIG["Regional Managed Instance Group"]
    MIG --> VM1["Java VM #1<br/>zone a"]
    MIG --> VM2["Java VM #2<br/>zone b"]
    VM1 --> SQL["Cloud SQL private connectivity"]
    VM2 --> SQL
    VM1 --> PUB["Pub/Sub / Cloud Storage"]
    VM2 --> PUB
    MON["Cloud Monitoring / Cloud Logging"] -. "Telemetry" .-> MIG
~~~

A **MIG** uses an **instance template** defining machine type, image, startup scripts/artifact fetch, service account, and network. The load balancer uses health checks to route traffic only to healthy backends, paired with autoscaling and rolling updates.

Moving from this demo to a MIG + load balancer requires deliberate changes:

- The app must listen on the **interface used by backends**, not just `127.0.0.1` (or sit behind an appropriate reverse proxy/sidecar). **Only change `BIND_HOST` once proper ingress controls are ready.**
- Backend firewalls must permit only **load balancer/proxy and health-check source ranges** matching the **exact load balancer type**—never `0.0.0.0/0`.
- Terminate **TLS** at the frontend, plus end-to-end TLS if policy requires.
- Use a **regional MIG** spanning multiple zones to survive zonal failures; verify zonal capacity and autoscaling.
- Keep the app **stateless**, storing durable state in Cloud SQL, Cloud Storage, or equivalent managed services.
- Separate **liveness** and **readiness**, and implement graceful shutdown draining so rolling updates drop zero requests.
- Enforce production-grade IAM, Secret Manager, database auth, backups, and logging.

### 12.2. Should You Choose Cloud Run or GKE Instead of VMs?

| Option | Best Fit When | Operational Responsibilities |
|---|---|---|
| **Compute Engine VM** | Deep OS/JVM tuning, legacy software, explicit process/disk/network control | OS/JDK patching, host security, HA, scaling, deploys, logging |
| **Compute Engine + MIG** | Need VM control alongside HA, autoscaling, and rolling updates | Still manage images/templates/OS alongside MIG/LB |
| **Cloud Run** | Stateless HTTP API/containers wanting minimal server ops and request-driven scaling | Container images, IAM/ingress, dependencies, observability |
| **GKE** | Many containerized services needing Kubernetes orchestration, networking, and policies | Cluster/workload configs, RBAC, networking, images, SLOs |

If a Java REST API is already containerized, has minimal OS dependencies, and sees variable traffic, **Cloud Run** dramatically cuts VM maintenance. If you need custom kernel drivers, long-running host processes, or fine-grained host control, Compute Engine remains a strong fit. Base the decision on workload, SLOs, security, and total cost.

## 13. Managing Secrets, IAM, VPCs, and Security Patches

### 13.1. Separating Permission Layers

| Layer | Permissions to Govern | Example |
|---|---|---|
| Cloud IAM | Who can create VMs, edit firewalls, SSH, or view logs | Dev teams do not need `roles/owner` |
| IAP/OS Login | Who can enter VMs and under what policy | Appropriate IAP + OS Login roles |
| Linux | Who can read/write JARs, configs, and logs | Non-root `javaorders` user |
| Runtime service account | Which Cloud Storage/Pub/Sub resources the app can call | Bucket/topic-specific minimal roles |
| Network | Which sources/destinations/ports the VM can reach | Custom VPC, firewalls, Cloud NAT |
| Application | Whether API callers can view/edit orders | OAuth/JWT and authorization inside the Java app |

### 13.2. Never Store Secrets in Public Service Unit Files

In the lab, the service file holds only `PORT` and `BIND_HOST`. Production apps may need database passwords, API keys, or tokens. Avoid placing them in:

- `ExecStart` or `Environment=DB_PASSWORD=...` inside unit files that might be widely readable or backed up insecurely.
- Source code, JAR files, Git repositories, startup scripts, or logs.
- Long-lived JSON service account keys when the VM's attached identity can be used.

Use **Secret Manager** accessed via the runtime service account with roles scoped to exact secrets; implement caching, rotation, and resilient handling for transient Secret Manager unavailability.

### 13.3. Securing Compute Engine VMs

- **OS Login/IAP:** eliminates ad-hoc SSH key distribution and public SSH exposure.
- **Shielded VM:** configure Secure Boot/vTPM/Integrity Monitoring where supported by the image and workload.
- **OS patching:** establish a Debian/JDK patching cadence, test in staging, and roll out/reboot during maintenance windows.
- **Disk encryption/backups:** Compute Engine encrypts disks at rest; check organizational requirements for CMEK and backup retention.
- **Least privilege:** never grant Owner/Editor to a runtime service account just to pull artifacts.
- **Network firewalls:** restrict ingress, govern egress, and understand org/folder hierarchical firewall policies.
- **Auditing:** retain IAM/firewall/VM changes and deployment logs per approved retention rules.

## 14. Common Issues and Diagnostics

| Symptom | Likely Cause | How to Check |
|---|---|---|
| `gcloud compute instances create` permission error | Missing IAM permission, `iam.serviceAccounts.actAs`, or org policy | Read exact error, verify scope, request least-privilege role |
| VM lacks outbound for `apt-get update` | Used `--no-address` without NAT/egress path | Check Public NAT, default route, egress firewall, and DNS |
| SSH IAP `PERMISSION_DENIED` | Missing IAP/OS Login roles or policy block | Verify caller's IAM bindings |
| SSH IAP timeout | TCP/22 firewall from IAP mismatch, VM/SSHD error | Check target tags, firewall rules, VM status, and OS logs |
| `javac: command not found` | Only JRE installed or JDK missing | Check `java -version` and `javac -version` |
| `Module jdk.httpserver not found` | JRE/JDK image omits module | Install standard JDK and recompile |
| `Address already in use` | Manual Java test still running or another process holds 8080 | Run `ss -lntp`; stop test process before starting systemd |
| `systemctl status` shows `failed` | Bad `ExecStart`, JAR permissions, JVM crash, unit syntax error | Run `journalctl -u orders-api` and `systemd-analyze verify` |
| `curl localhost:8080` works on VM, Cloud Shell tunnel fails | `ssh -L` not running, local port conflict, or wrong project/zone | Check port 18080 in Cloud Shell and IAP tunnel |
| Cloud Shell tunnel works yet Internet cannot reach API | Lab **opens no HTTP ingress** and app binds loopback | Expected secure behavior, not a bug |
| Service runs yet zero logs in Cloud Logging | Ops Agent not installed/configured or missing agent IAM | Check local journal and logging pipeline |
| API returns 500 talking to prod Cloud SQL | DB auth, networking, pool exhaustion, or app bug | Inspect logs, Cloud SQL private IP, and secrets |
| VM stopped yet charges continue | Disks, external IPs/reservations, snapshots remain | Inspect Billing report by SKU |
| Single VM drops connections on reboot | No redundant replicas / HA | Implement multi-zone MIG and load balancer |

### 14.1. Layered Diagnostic Flow

~~~mermaid
flowchart TD
    A["Client receives no HTTP response"] --> B{"Testing via IAP SSH -L?"}
    B -->|No| C["Lab exposes no public HTTP<br/>Use IAP tunnel or configure LB"]
    B -->|Yes| D{"Does IAP/SSH connect?"}
    D -->|No| E["Check IAM, IAP, OS Login, VM, firewall port 22"]
    D -->|Yes| F{"Does curl 127.0.0.1:8080 succeed on VM?"}
    F -->|No| G["Inspect systemctl, journalctl, ss, Java/JAR/port"]
    F -->|Yes| H{"Does curl 127.0.0.1:18080 succeed from Cloud Shell?"}
    H -->|No| I["Check local forwarding, port 18080, terminal"]
    H -->|Yes| J["Lab OK; verify JSON, logs, reboot, and cleanup"]
~~~

## 15. Cleaning Up Lab Resources

**Cleanup is mandatory** to prevent unexpected charges. First confirm the resources in `PROJECT_ID` belong exclusively to this lab and are not shared with another workload. Check ownership before deleting.

In Cloud Shell (not the VM SSH terminal):

~~~bash
# Verify resource identity before deletion.
gcloud compute instances describe java-orders-lab \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a

# Delete the lab VM. Verify whether the boot disk deletes per policy.
gcloud compute instances delete java-orders-lab \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a

# Delete the lab firewall rule.
gcloud compute firewall-rules delete java-lab-allow-iap-ssh \
  --project=PROJECT_ID

# Delete the subnet first, then the VPC.
gcloud compute networks subnets delete java-lab-subnet \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud compute networks delete java-lab-vpc \
  --project=PROJECT_ID
~~~

After confirming the service account is unused by any other app, delete it:

~~~bash
gcloud iam service-accounts delete \
  java-lab-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID
~~~

**Never delete a service account solely by matching name** if it is shared outside the lab or owned by someone else. After cleanup, verify:

- **Compute Engine → VM instances, Disks, Snapshots**: any orphaned resources remaining?
- **VPC network → IP addresses**: any static external IPs still reserved?
- Were any **Cloud NAT, Cloud Router, load balancers, or Artifact Registry** resources created in lab variations?
- Review Billing reports for charges accrued while the VM ran, keeping reporting lag in mind.

`delete` commands may ask for confirmation and fail if dependencies still reference the resource. **Never use force-delete flags** merely to bypass dependency errors without understanding what still uses the resource.

## 16. Practice Exercises and Self-Assessment Questions

### 16.1. Exercise A — Tracing the Request Path

Based on this lesson's architecture, trace the path from **Cloud Shell** to `GET /api/orders` on the VM. Explain:

1. Why is IAP TCP forwarding needed when passing `--tunnel-through-iap`?
2. Why does the API still answer HTTP even though the VPC only opens TCP/22 from `35.235.240.0/20`?
3. Does having an external IPv4 on the VM make port 8080 public?
4. Without an external IPv4, what must be provisioned so `apt-get` can fetch packages from the Internet?

**Hint:** HTTP travels inside SSH port forwarding hitting VM loopback; TCP/8080 never crosses VPC ingress directly. A private VM needs proper outbound routing such as Public NAT for IPv4 Internet access.

### 16.2. Exercise B — Interpreting systemd Failures

Suppose running:

~~~bash
sudo systemctl status orders-api --no-pager
~~~

returns:

~~~text
Active: failed (Result: exit-code)
...
java.net.BindException: Address already in use
~~~

List at least three diagnostic steps, including checking which process holds the port, checking manual Java test runs, and reviewing the unit file. Should you change `User=javaorders` to `root` as a quick fix? Why or why not?

**Hint:** check with `ss -lntp`, stop the manual Java test process, and inspect the unit file; switching to root will not resolve a port conflict and increases security risk.

### 16.3. Exercise C — Securing the Service Account

The dev team wants the app to download files from Cloud Storage. One member suggests granting `roles/editor` to the runtime service account "to avoid errors."

Propose:

- Which role should be evaluated if the app only reads objects from one specific bucket?
- Should the IAM binding be placed at the project or bucket level?
- How does the app obtain credentials on the VM without storing a JSON service account key?
- How do you distinguish an IAM `PERMISSION_DENIED` error from a VPC/firewall failure?

**Hint:** evaluate `roles/storage.objectViewer` on that exact bucket per required operations; use the VM-attached identity / Application Default Credentials; inspect exact error messages and permissions.

### 16.4. Exercise D — Upgrading to Zero-Downtime Service

After the single-VM demo, the client asks for:

- Resilience against a single-zone outage.
- Deploying new Java versions without dropping all requests.
- HTTPS with a stable domain name.
- Load-based autoscaling and p95 latency monitoring.

Describe a minimal architecture using a **regional MIG, instance templates, HTTPS load balancer, health checks, Cloud DNS, and Monitoring**. Clarify what must change for `BIND_HOST`, backend firewalls, readiness probes, graceful shutdown, and artifact pipelines. Compare this with deploying on **Cloud Run**.

### 16.5. Exercise E — Cost and Cleanup

A learner stops their VM yet forgets to check disks and external IPs. They had also created a snapshot and an unattached static external IP.

1. Does stopping the VM definitely bring billing to zero?
2. Which items must be checked in Cloud Billing reports?
3. Why is `gcloud compute instances delete` alone not enough to guarantee all lab resources are gone?
4. Propose an automated approach to remind owners to clean up and enforce sandbox TTLs per organizational policy.

## 17. Completion Checklist

- [ ] Selected the right sandbox project, region, zone, and configured appropriate budgets/alerts.
- [ ] Created a custom VPC and non-overlapping subnet as required.
- [ ] Opened **SSH from IAP only** to target VMs; never exposed demo HTTP to the Internet.
- [ ] Created a dedicated runtime service account without broad administrative roles.
- [ ] Created a Debian VM with deliberate machine type, boot disk, and network settings.
- [ ] Logged in via IAP and verified OS Login/IAM.
- [ ] Installed the JDK, compiled `OrdersApi.java`, and packaged the JAR.
- [ ] Tested `/healthz` and `/api/orders` locally inside the VM.
- [ ] Configured a non-privileged Linux user and the `orders-api.service` unit.
- [ ] Verified systemd auto-start, `journalctl` logs, and loopback port binding.
- [ ] Tested the API from Cloud Shell via SSH `-L` and IAP.
- [ ] Distinguished systemd local logging from Cloud Logging and OS/JVM metrics.
- [ ] Outlined release/rollback workflows and migrating to a MIG + load balancer.
- [ ] Distinguished security boundaries across Compute Engine VMs, Cloud Run, and databases.
- [ ] Deleted lab resources after confirming ownership and verified zero lingering unwanted spend.

## 18. Official Documentation

Before executing commands in live Google Cloud environments, verify current syntax and support for your project, region, and OS at deployment time:

- [Compute Engine: Create and start a VM instance](https://cloud.google.com/compute/docs/instances/create-start-instance)
- [Compute Engine: VM instance overview](https://cloud.google.com/compute/docs/instances)
- [Connect to Linux VMs using IAP TCP forwarding](https://cloud.google.com/iap/docs/using-tcp-forwarding)
- [OS Login overview](https://cloud.google.com/compute/docs/oslogin)
- [VPC firewall rules overview](https://cloud.google.com/firewall/docs/firewalls)
- [VPC networks and subnets](https://cloud.google.com/vpc/docs/vpc)
- [Cloud NAT overview](https://cloud.google.com/nat/docs/overview)
- [Service accounts attached to VMs](https://cloud.google.com/compute/docs/access/service-accounts)
- [Install and manage Ops Agent](https://cloud.google.com/stackdriver/docs/solutions/agents/ops-agent/installation)
- [Managed instance groups](https://cloud.google.com/compute/docs/instance-groups)
- [External Application Load Balancer overview](https://cloud.google.com/load-balancing/docs/https)
- [Compute Engine pricing](https://cloud.google.com/compute/vm-instance-pricing)
- [Cloud Billing budgets](https://cloud.google.com/billing/docs/how-to/budgets)
- [Java HttpServer module (JDK)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)

**Key Takeaway:** deploying Java on Compute Engine is much more than running `java -jar`. An operable deployment requires **proper identity, restricted networking, managed OS and JVM runtimes, self-healing processes, health checks, logging, release/rollback pipelines, and cost controls**. A single-VM lab teaches every link in the chain; production adds **HTTPS, authentication, multiple instances, load balancing, patching, and monitoring**—or evaluating managed services like Cloud Run when appropriate.

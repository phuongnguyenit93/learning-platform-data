# Private IP, Private Service Connect, and Cloud SQL Connectivity

A Java API running on Cloud Run needs to reach Cloud SQL for PostgreSQL without exposing the database to the internet. Two private connectivity options are easily confused: **Private IP via Private Services Access (PSA)** and **Private Service Connect (PSC)**. Both use internal addresses, yet they differ in network layout, cross-VPC service sharing, and DNS operations. Picking the wrong one can leave your app hitting `connection timeout`, introduce permission risks, or force infrastructure rework when expanding across multiple projects.

This lesson belongs to the **Cloud SQL and AlloyDB** chapter of the **CLOUD_PROVIDERS_GCP** module. It ties project/IAM/VPC fundamentals together with Compute Engine, GKE, Cloud Run, Cloud SQL, security, deployment automation, and reliability/cost observability. The focus is on **how to design, configure, and diagnose the network path to Cloud SQL**, rather than deep SQL schema administration.

After this lesson, you will be able to:

- Distinguish **public IP**, **private IP via PSA**, and **PSC endpoints**.
- Allocate a PSA IP range, establish a Service Networking connection, and create a Cloud SQL instance without a public IP.
- Configure a PSC-enabled Cloud SQL instance, create an endpoint in a consumer VPC, and verify `ACCEPTED` status.
- Use private DNS so applications can connect over PSC from multiple VPCs, distinguishing DNS names from instance connection names.
- Connect Java using the Cloud SQL Java Connector with `ipTypes=PRIVATE` or `ipTypes=PSC`, ADC/IAM, and bounded JDBC pools.
- Identify the right network path for Compute Engine, GKE, and Cloud Run; separate **network connectivity**, **IAM**, and **database authentication**.
- Diagnose `NETWORK_NOT_PEERED`, DNS lookup failures, `403`, timeouts, `too many connections`, and plan controlled migrations.

> **Lab scope:** commands creating VPCs, address ranges, Cloud SQL instances, PSC endpoints, and DNS records can incur charges or impact running systems. Project names, IPs, instances, and service accounts are examples only; operate strictly within an authorized lab environment. Never delete a PSA range, peering, or endpoint still used by live applications.

## 1. The Big Picture: Three Connectivity Paths

| Access Path | Client-Side Address | Best Fit | Key Prerequisites |
|---|---|---|---|
| **Public IP** | Cloud SQL public IP/hostname | Authorized clients outside the VPC where internet transit is allowed | Firewall/authorized networks or Cloud SQL Auth Proxy/Connector; TLS/auth |
| **Private IP via PSA** | Cloud SQL private IP allocated from the service range | Workloads in the same VPC or with a supported route to the configured VPC | `VPC_PEERING` IP range, Service Networking connection, routes, DB auth |
| **Private Service Connect** | **PSC endpoint internal IP** in consumer subnet, or DNS pointing to it | Multiple teams/projects/VPCs sharing access to one Cloud SQL instance | PSC-enabled Cloud SQL, service attachment, `ACCEPTED` endpoint, DNS/IAM/DB auth |

**Private IP ≠ Private Service Connect.** Traditional Cloud SQL private IP relies on **Private Services Access**; PSC uses a **service attachment** published by Cloud SQL and a **forwarding rule/endpoint** owned by the consumer VPC. A new or upgraded Cloud SQL instance can support **both PSA and PSC** where eligible; the two modes are not always mutually exclusive.

### Network Overview

~~~mermaid
flowchart TD
  subgraph APP["Application project / consumer VPC"]
    A["Cloud Run (Direct VPC egress) / GKE / VM"]
    E["PSC endpoint: 10.20.0.10"]
  end
  subgraph NET["Private Services Access"]
    P["Service Networking VPC peering"]
  end
  subgraph SQL["Database project / Cloud SQL"]
    S["Cloud SQL PostgreSQL"]
    T["Service attachment (PSC)"]
  end
  A -->|"Private IP via PSA"| P
  P --> S
  A -->|"PSC private endpoint"| E
  E --> T
  T --> S
~~~

Private networking reduces the attack surface, but **does not automatically encrypt every SQL connection** and **does not replace passwords or IAM database authentication**. For direct JDBC TCP connections, configure TLS and verify server identity per policy; use **Cloud SQL Auth Proxy** or **Cloud SQL Language Connectors** when you want managed encryption and IAM-backed connection authentication.

## 2. How Does Private Services Access (PSA) Work?

PSA reserves a **non-overlapping** IP range inside your VPC for Google-managed services. **Service Networking** establishes a peering connection to the service producer network; Cloud SQL receives a private IP from that range.

~~~text
VM/GKE/Cloud Run egress inside VPC app-vpc
       │
       │ routed to the PSA IP range
       ▼
Private Services Access (Service Networking peering)
       │
       ▼
Cloud SQL instance private IP (no public IP needed)
~~~

**Design points:**

- Plan the PSA IP range long-term: avoid overlapping application subnets, on-premises networks, or ranges reserved for other services.
- Peering connects **your app VPC to Google's service network**; it **does not create transitive routing** across every peered VPC. A workload in VPC B cannot reach a Cloud SQL PSA IP in VPC A simply because both VPCs have separate peerings.
- Cloud Run, Cloud Functions, and App Engine Standard normally need **Direct VPC egress or a Serverless VPC Access connector** into the right VPC to reach private IPs. VMs and GKE Pods in the same VPC use private routing subject to routes/firewalls.
- With **Shared VPC**, IP ranges and network configuration live in the **host project**, while instances can live in service projects. Check which project owns Service Networking and cross-project roles.

## 3. Lab A — Cloud SQL PostgreSQL Using PSA Private IP

Lab goal: use a dedicated VPC `orders-vpc`, allocate a PSA range, create a Cloud SQL PostgreSQL instance **with no public IP**, and connect from a workload with network reachability to the VPC. Commands assume permissions to manage networking, Service Networking, and Cloud SQL.

### Step 1 — Prepare APIs and VPC

~~~bash
PROJECT_ID="orders-lab-project"
REGION="asia-southeast1"
VPC="orders-vpc"
SUBNET="orders-subnet"
INSTANCE="orders-pg-private"
PSA_RANGE="google-managed-services-$VPC"

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  compute.googleapis.com \
  servicenetworking.googleapis.com \
  sqladmin.googleapis.com

# In a fresh lab project, only create resources if they do not already exist.
gcloud compute networks create "$VPC" \
  --subnet-mode=custom

gcloud compute networks subnets create "$SUBNET" \
  --network="$VPC" \
  --region="$REGION" \
  --range=10.20.0.0/24
~~~

In projects with existing networks, **do not create a duplicate VPC**; substitute your approved VPC. Other VPCs only need peering/ranges configured if not already present. CIDR `10.20.0.0/24` is the **application subnet**, not the PSA range.

### Step 2 — Allocate a Non-Overlapping PSA Range

~~~bash
# Google Cloud selects an unused /16 range in the VPC.
gcloud compute addresses create "$PSA_RANGE" \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --network="projects/$PROJECT_ID/global/networks/$VPC"

gcloud compute addresses describe "$PSA_RANGE" \
  --global
~~~

In enterprise environments, plan an explicit CIDR (such as `10.70.0.0/16`) and pass `--addresses=10.70.0.0` after auditing the entire network. **Never assign a subnet already used by VMs as the PSA range.** Required address capacity depends on the number of services, regions, databases, and network topology.

### Step 3 — Establish the Service Networking Private Connection

~~~bash
gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges="$PSA_RANGE" \
  --network="$VPC" \
  --project="$PROJECT_ID"

gcloud services vpc-peerings list \
  --network="$VPC" \
  --project="$PROJECT_ID"
~~~

If the command returns an **operation ID**, wait for it to finish; do not rush to create the instance before peering is ready. If a network already has a connection, **do not create a duplicate connection**; when an existing range fills up, add ranges via `vpc-peerings update` after impact review.

### Step 4 — Create Cloud SQL Without a Public IP

~~~bash
gcloud sql instances create "$INSTANCE" \
  --project="$PROJECT_ID" \
  --database-version=POSTGRES_16 \
  --region="$REGION" \
  --tier=db-custom-2-7680 \
  --availability-type=ZONAL \
  --network="projects/$PROJECT_ID/global/networks/$VPC" \
  --allocated-ip-range="$PSA_RANGE" \
  --no-assign-ip

gcloud sql instances describe "$INSTANCE" \
  --project="$PROJECT_ID" \
  --format="yaml(connectionName,ipAddresses,settings.ipConfiguration)"
~~~

`ZONAL` here keeps lab costs down and provides **no multi-zone failover**; production generally requires evaluating `REGIONAL` HA, backups/PITR, automated backups, maintenance windows, and replicas/failover. A Cloud SQL instance is billable even when idle; verify budget before creating.

**Reading the output:** `ipAddresses` will include a private address once ready; no public IP is assigned due to `--no-assign-ip`. The string `PROJECT:REGION:INSTANCE` is the **instance connection name** used by Auth Proxy/Connectors; it is **not** a DNS name or IP that `psql` can resolve directly.

### Step 5 — Verify Connectivity from an Authorized Client

From a **VM or GKE Pod in the same VPC** with a PostgreSQL client installed:

~~~bash
# Grab PRIVATE_IP from the verified describe output.
PRIVATE_IP="10.x.y.z"    # replace with actual address
DB_USER="orders_reader"  # pre-created and authorized DB user
DB_NAME="orders"

# Tests TCP reachability only; does not prove DB auth.
nc -vz "$PRIVATE_IP" 5432

# Direct connection: requires TLS per instance policy/CA.
# This example assumes certificate verification is configured:
psql "host=$PRIVATE_IP port=5432 dbname=$DB_NAME user=$DB_USER sslmode=verify-full sslrootcert=/path/to/server-ca.pem"
~~~

`sslmode=verify-full` requires the server certificate's subject/SAN to match the hostname used; **if you connect by raw IP and the certificate lacks a matching IP SAN, TLS verification fails**. In production, use a valid endpoint hostname/CA bundle or use Cloud SQL Auth Proxy/Language Connector for simpler managed TLS. Never drop to `sslmode=disable` just to bypass errors.

### Connecting Securely with Cloud SQL Auth Proxy

When a client has **ADC** and `roles/cloudsql.client`, Cloud SQL Auth Proxy v2 handles IAM authentication and TLS to the instance automatically. On a VM/GKE Pod with routing to the **private IP**:

~~~bash
INSTANCE_CONNECTION_NAME="$PROJECT_ID:$REGION:$INSTANCE"

# Run Auth Proxy v2 in its own terminal.
./cloud-sql-proxy --private-ip --port 5432 "$INSTANCE_CONNECTION_NAME"

# In another terminal on the SAME host/network namespace:
psql "host=127.0.0.1 port=5432 dbname=orders user=orders_reader"
~~~

The proxy secures the hop from itself to Cloud SQL; **the hop from the app to the local proxy** is local TCP. The proxy does not create VPC routes, does not supply database usernames/passwords, and is not a connection pooler. When running Cloud SQL Auth Proxy as a GKE sidecar in the same Pod, `localhost` is the shared Pod loopback; if running on a separate VM, never expose the proxy port to the internet.

## 4. What Is Private Service Connect (PSC)?

PSC lets an application in a **consumer VPC** reach Cloud SQL through an **endpoint with an internal IP from the consumer subnet**, instead of peering every VPC directly to the service network via PSA.

Components:

| Component | Owner | Role |
|---|---|---|
| **Cloud SQL PSC-enabled instance** | Database project | Publishes the managed database service |
| **Service attachment** | Cloud SQL / producer | Target URI for endpoints |
| **Allowed PSC projects** | Cloud SQL instance config | List of projects allowed to create endpoints to the instance |
| **PSC endpoint / forwarding rule** | Consumer project/VPC | Reserves an IP in the consumer subnet and forwards traffic to the service attachment |
| **Private DNS** | Consumer VPC / Cloud DNS | Maps the hostname used by connectors/proxies to the endpoint IP |

~~~mermaid
flowchart LR
  subgraph DB["Database project: data-prod"]
    SQL["Cloud SQL PostgreSQL"]
    SA["Cloud SQL service attachment"]
    SQL --- SA
  end
  subgraph A["Consumer VPC A: orders-prod"]
    APP1["Java Cloud Run / GKE"]
    EP1["Endpoint IP: 10.10.0.20"]
    APP1 --> EP1
  end
  subgraph B["Consumer VPC B: reports-prod"]
    APP2["Report service"]
    EP2["Endpoint IP: 10.30.0.20"]
    APP2 --> EP2
  end
  EP1 --> SA
  EP2 --> SA
~~~

**Key benefits:** each VPC maintains its own endpoint/DNS within IP space managed by that team; separate projects, organizations, and teams can reach the **same Cloud SQL instance** when authorized. PSC reduces reliance on multi-party VPC peering, though **it does not grant default access to every VPC in the organization**: you still need allowed projects, endpoints, and valid networking/DNS/DB auth.

**Current capabilities:** Cloud SQL supports creating **PSC-only** instances or **combined PSA + PSC** configurations where eligible. Enabling PSC on an existing PSA instance can **cause downtime**; never run it during peak hours without checking version documentation and maintenance windows. **PSC outbound connectivity** (where Cloud SQL reaches back into a consumer network via a network attachment) solves a different problem and is unnecessary for app → database traffic here.

## 5. Lab B — Creating a PSC Cloud SQL Instance and Consumer Endpoint

Assume a **database project** and a **consumer project**. Goal: a PSC-enabled PostgreSQL instance in `data-lab` allows endpoint creation in `app-lab`. Traffic from app to database flows over the PSC IP with no public IP assigned.

### Step 1 — Create the PSC Instance

~~~bash
DB_PROJECT="data-lab-project"
APP_PROJECT="app-lab-project"
REGION="asia-southeast1"
DB_INSTANCE="orders-pg-psc"

# Database/platform team, run in the database project.
gcloud services enable sqladmin.googleapis.com \
  --project="$DB_PROJECT"

gcloud sql instances create "$DB_INSTANCE" \
  --project="$DB_PROJECT" \
  --region="$REGION" \
  --database-version=POSTGRES_16 \
  --tier=db-custom-2-7680 \
  --availability-type=ZONAL \
  --no-assign-ip \
  --enable-private-service-connect \
  --allowed-psc-projects="$APP_PROJECT"

gcloud sql instances describe "$DB_INSTANCE" \
  --project="$DB_PROJECT" \
  --format="yaml(connectionName,pscServiceAttachmentLink,settings.ipConfiguration)"
~~~

`--allowed-psc-projects` lists **project IDs or numbers** permitted to create endpoints targeting the Cloud SQL service attachment. It is **not** a list of database users or service accounts authorized to log in. On existing instances, check combined PSC/PSA support, downtime impact, and permissions before running `gcloud sql instances patch`.

### Step 2 — Retrieve the Service Attachment from Cloud SQL

~~~bash
SERVICE_ATTACHMENT="$(gcloud sql instances describe "$DB_INSTANCE" \
  --project="$DB_PROJECT" \
  --format='value(pscServiceAttachmentLink)')"

echo "$SERVICE_ATTACHMENT"
~~~

The URI looks like `projects/PRODUCER_PROJECT/regions/REGION/serviceAttachments/NAME`. **Never construct this URI from the instance name or guess the producer project**; always use the exact value returned by Cloud SQL.

### Step 3 — Prepare the VPC/Subnet in the Consumer Project

~~~bash
APP_VPC="orders-consumer-vpc"
APP_SUBNET="orders-consumer-subnet"
PSC_ADDRESS="orders-sql-psc-ip"
PSC_ENDPOINT="orders-sql-psc-endpoint"

gcloud services enable compute.googleapis.com \
  --project="$APP_PROJECT"

# Create only if VPC/subnet do not exist yet; CIDR must be planned.
gcloud compute networks create "$APP_VPC" \
  --project="$APP_PROJECT" --subnet-mode=custom
gcloud compute networks subnets create "$APP_SUBNET" \
  --project="$APP_PROJECT" \
  --network="$APP_VPC" \
  --region="$REGION" \
  --range=10.30.0.0/24

# Reserve an internal IP from the primary subnet range for the PSC endpoint.
gcloud compute addresses create "$PSC_ADDRESS" \
  --project="$APP_PROJECT" \
  --region="$REGION" \
  --subnet="$APP_SUBNET"
~~~

The PSC endpoint's subnet must be in the **same region as the service attachment**. With **Shared VPC**, the network/subnet may reside in the **host project** while the endpoint resides in the host or service project per support and IAM; pass exact **full resource URIs** and ensure host-project network permissions rather than swapping project names arbitrarily.

### Step 4 — Create the Forwarding Rule to the Service Attachment

~~~bash
gcloud compute forwarding-rules create "$PSC_ENDPOINT" \
  --project="$APP_PROJECT" \
  --region="$REGION" \
  --network="projects/$APP_PROJECT/global/networks/$APP_VPC" \
  --address="$PSC_ADDRESS" \
  --target-service-attachment="$SERVICE_ATTACHMENT"

gcloud compute forwarding-rules describe "$PSC_ENDPOINT" \
  --project="$APP_PROJECT" \
  --region="$REGION" \
  --format="yaml(IPAddress,pscConnectionStatus,target,network)"
~~~

Expect `pscConnectionStatus: ACCEPTED` and `IPAddress` to be an IP from the consumer subnet. If status is `PENDING` or `REJECTED`, **do not jump straight to debugging Java or DB passwords**: check allowed projects, service attachment URI, endpoint region, quotas, and service networking policies first.

By default, **do not** add `--allow-psc-global-access` when workloads are in the same region. That flag opens access to the endpoint from other regions; enable it only if required after evaluating latency, egress/firewalls, and security policy.

### Step 5 — Test TCP Connectivity from a Client Inside the VPC

~~~bash
# Run from a Compute Engine VM/GKE Pod with a route to APP_VPC.
PSC_IP="10.30.0.10"   # REPLACE with IPAddress from describe
nc -vz "$PSC_IP" 5432
~~~

`nc` succeeding proves only TCP reachability to the PostgreSQL port, **not database authentication**. Direct connections via `psql`/JDBC still need valid DB credentials and TLS/certificate verification; alternatively, use Cloud SQL Auth Proxy or a Language Connector in the next step.

## 6. DNS for PSC: Why Use a Hostname?

Each consumer VPC can allocate a **different** IP for its PSC endpoint pointing to the same Cloud SQL instance. That is why **DNS is recommended**: apps in VPC A and VPC B use the contract database hostname, while private DNS resolves it to each VPC's local endpoint IP.

~~~text
orders-db.<google-provided-domain> → 10.30.0.10  (inside APP_VPC)
orders-db.<google-provided-domain> → 10.50.0.10  (inside REPORT_VPC)
~~~

With Cloud SQL PSC, some configurations provide **DNS automation** that creates records automatically via service connection policies when auto-connections are used; manual configuration is the alternative. Read the **actual DNS name returned by Cloud SQL for the instance** — never invent hostnames. Cloud SQL versions may expose both a **per-instance DNS name** and a **global write endpoint DNS** (e.g., for advanced DR in supported editions), which serve different roles.

### When Using Auth Proxy or Java Connector

- **Cloud SQL Auth Proxy v2.5+** supports PSC and requires a **DNS name** resolvable from wherever the proxy runs.
- **Cloud SQL Java Connector v1.13+** supports `ipTypes=PSC`, relying on that DNS record/path to the endpoint.
- Direct TCP Java/JDBC connections can use either the endpoint IP or resolved hostname; direct connections must manage SSL/TLS and DB credentials themselves.
- An **instance connection name** formatted as `project:region:instance` identifies the instance to Cloud SQL APIs/connectors and does not replace a DNS A record pointing to the endpoint.

Workflow:

1. Retrieve the PSC hostname provided by Cloud SQL (or use supported DNS automation).
2. Create a **Cloud DNS private zone/record** for the consumer VPC pointing to the endpoint IP (when configuring manually); verify the exact DNS suffix required by the docs/instance.
3. From a VM/GKE/Cloud Run workload with VPC DNS visibility, run `nslookup HOSTNAME` or `dig HOSTNAME` and confirm it returns the consumer endpoint IP.
4. Verify endpoint `ACCEPTED`, `nc -vz HOSTNAME 5432`, and only then test connector/DB auth.
5. For multiple VPCs, configure private zone visibility per VPC; never publish internal records to public DNS unnecessarily.

**DNS only tells clients where to connect; it never grants IAM or DB user permissions.** A name resolving to the right endpoint can still time out due to firewalls or missing routes, or fail with `FATAL: password authentication failed` due to bad DB credentials.

## 7. Java: Cloud SQL Connector Over PSA or PSC

In Java, the **Cloud SQL Java Connector** handles IAM authentication and encrypted transport to Cloud SQL. It **does not create network connectivity**; the app must still reach the private IP or PSC endpoint through the VPC. Use **Application Default Credentials (ADC)** in Cloud Run/GKE/VMs along with IAM `roles/cloudsql.client` when using the Connector or Proxy.

### Dependency Setup

For PostgreSQL with HikariCP, a Maven/Gradle project needs:

- PostgreSQL JDBC driver `org.postgresql:postgresql`.
- Cloud SQL Java Connector for PostgreSQL `com.google.cloud.sql:postgres-socket-factory`.
- HikariCP `com.zaxxer:HikariCP`.
- Google Cloud auth/Secret Manager client if loading the DB password via ADC.

Pick compatible versions via BOM/dependency management and check the official Connector guide. The snippet below is a reusable helper class inside an already configured Java build.

### Java Connection Pool — Selecting the IP Type Intentionally

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class CloudSqlDataSource {
    private CloudSqlDataSource() {}

    public static HikariDataSource create(
            String connectionName,
            String database,
            String dbUser,
            String dbPassword,
            String ipType) {

        if (!ipType.equals("PRIVATE") && !ipType.equals("PSC")) {
            throw new IllegalArgumentException("Expected PRIVATE or PSC");
        }

        HikariConfig cfg = new HikariConfig();
        cfg.setJdbcUrl("jdbc:postgresql:///" + database);
        cfg.setUsername(dbUser);
        cfg.setPassword(dbPassword); // Load from Secret Manager; never hardcode.
        cfg.addDataSourceProperty(
            "socketFactory", "com.google.cloud.sql.postgres.SocketFactory");
        cfg.addDataSourceProperty("cloudSqlInstance", connectionName);
        cfg.addDataSourceProperty("ipTypes", ipType);
        cfg.addDataSourceProperty("cloudSqlRefreshStrategy", "lazy");

        cfg.setMaximumPoolSize(5);
        cfg.setMinimumIdle(0);
        cfg.setConnectionTimeout(10_000);
        cfg.setIdleTimeout(60_000);
        return new HikariDataSource(cfg);
    }
}
~~~

Initialization example:

~~~java
String instance = System.getenv("INSTANCE_CONNECTION_NAME");
String database = System.getenv("DB_NAME");
String dbUser = System.getenv("DB_USER");
String dbPassword = loadFromSecretManager(); // Implemented by the application.

// PSA private IP:
var psaPool = CloudSqlDataSource.create(
    instance, database, dbUser, dbPassword, "PRIVATE");

// Or PSC endpoint + private DNS ready:
var pscPool = CloudSqlDataSource.create(
    instance, database, dbUser, dbPassword, "PSC");
~~~

These are **mutually exclusive alternatives** — do not initialize both pools for the same workload without a reason. `loadFromSecretManager()` is a placeholder for your app's own method, not a built-in Java API. Initialize the pool **once per app instance** and call `close()` on shutdown; never create a new pool per request.

| `ipTypes` | Network Path Selected by Connector | Dependencies |
|---|---|---|
| `PRIVATE` | Cloud SQL private IP via PSA | Network/peering/routing, private IP exists |
| `PSC` | PSC endpoint in consumer VPC | PSC enabled, endpoint ACCEPTED, DNS resolvable |
| `PUBLIC` | Cloud SQL public IP | Public IP and access policy; unsuitable for private labs |

**Do not omit `ipTypes` when you require private routing**: Connectors have version-dependent defaults and IP type preference orders; set `PRIVATE` or `PSC` explicitly to enforce the network path and avoid falling back to a public IP unexpectedly. For PSC, use a Cloud SQL Java Connector version that supports PSC and configure the DNS record required by the Connector.

### IAM and Database Authentication Are Two Separate Steps

- **IAM Cloud SQL Client**: lets the Connector/Proxy fetch instance metadata/certificates and establish the managed tunnel.
- **Database account**: PostgreSQL username/password and `GRANT SELECT/INSERT/...` inside the database. Not granted automatically by `roles/cloudsql.client`.
- **IAM database authentication** (optional): requires enabling the feature on Cloud SQL, creating an IAM DB user, granting a role like Cloud SQL Instance User, and configuring the Connector/Auth Proxy for IAM DB auth; this is an **alternative** to traditional passwords.

When clients **connect directly** via `psql`/JDBC TCP to a private IP or PSC IP, IAM Cloud SQL Client is not required if only DB credentials and allowed network access are used; however, TLS/auth and organizational policies still apply. Never grant an Admin role just to open a SQL port.

## 8. Connection Sources: VMs, GKE, and Cloud Run

| Workload Source | PSA Private IP | PSC | What Must Be Checked |
|---|---|---|---|
| **Compute Engine VM** | VM in VPC with PSA and valid routes | VM has route to endpoint IP in consumer VPC | Firewalls, network tags, DNS, DB auth |
| **GKE** | Nodes/Pods have egress to PSA VPC | Pods have egress to consumer PSC endpoint | VPC-native GKE, NetworkPolicy, service account/ADC |
| **Cloud Run** | Direct VPC egress or Serverless VPC Access to PSA VPC | Direct VPC egress/connector to VPC hosting PSC endpoint | Same-region subnet constraints, IAM, DNS, egress setting |
| **App Engine Standard/Functions** | Appropriate VPC egress to PSA VPC | Appropriate VPC egress to consumer endpoint | Network/product support and IAM |
| **On-premises** | VPN/Interconnect to PSA VPC with advertised routes | VPN/Interconnect/valid route to consumer endpoint | DNS forwarding, firewalls, latency, TLS |

**You cannot simply "have Cloud SQL Client IAM" and connect from a laptop to a private IP.** The machine must have network reachability into the VPC (VPN/Interconnect, secured bastion, internal dev environment). Running the Proxy on a laptop **does not tunnel across VPCs**, even if it fetches IAM tokens fine.

### Sample Cloud Run Direct VPC Egress

When deploying a **Cloud Run service** from a prebuilt container image, pick the network and subnet that can reach your PSA or PSC endpoint:

~~~bash
RUN_PROJECT="app-lab-project"
REGION="asia-southeast1"
NETWORK="orders-consumer-vpc"
SUBNET="orders-consumer-subnet"
RUN_SA="orders-runtime@$RUN_PROJECT.iam.gserviceaccount.com"
IMAGE="$REGION-docker.pkg.dev/$RUN_PROJECT/apps/orders-api:v1"

gcloud run deploy orders-api \
  --project="$RUN_PROJECT" \
  --image="$IMAGE" \
  --region="$REGION" \
  --service-account="$RUN_SA" \
  --network="$NETWORK" \
  --subnet="$SUBNET" \
  --vpc-egress=private-ranges-only \
  --no-allow-unauthenticated
~~~

This assumes the VPC/subnet is in the **same project** as the Cloud Run service; Shared VPC requires host-project permissions and setup per documentation. `private-ranges-only` routes internal IPs through the VPC; `all-traffic` routes all egress through the VPC and may require Cloud NAT for internet access. **VPC egress config does not create the PSC endpoint or PSA connection** — prepare those first.

### GKE and NetworkPolicy Pitfalls

A GKE Pod with `roles/cloudsql.client` via Workload Identity Federation but subject to a default-deny egress `NetworkPolicy` cannot reach the PSC endpoint or PSA range unless explicitly allowed. Allow the exact **database IP and TCP 5432** (PostgreSQL) or **TCP 3306** (MySQL), plus DNS and access to Google APIs needed by the Connector. With Cloud SQL Auth Proxy/Connector, separately verify paths to the Cloud SQL Admin API, metadata server, and IAM token exchange.

Example `NetworkPolicy` allowing egress to **one PSC endpoint IP** for Pods labeled `app=orders-api`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-orders-db-psc
  namespace: orders
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 10.30.0.10/32
      ports:
        - protocol: TCP
          port: 5432
~~~

This is **not a complete egress policy**: in a default-deny namespace, the app also needs DNS, metadata/ADC, Cloud SQL Admin API, Secret Manager, etc. Never apply sample CIDRs directly without knowing the real IP addresses.

## 9. Security, Reliability, and Operations

### Defense-in-Depth Layers

| Layer | Control | Example |
|---|---|---|
| **VPC/IP** | PSA private path or PSC endpoint, firewalls/network policies | Only the app tier can reach the database port |
| **IAM** | Minimal runtime SA, Cloud SQL Client when using Connector | Never grant `roles/editor` to an entire app |
| **Database** | DB users, password / IAM DB auth, schema grants, row-level access | App reader cannot run `DROP TABLE` |
| **Transport** | Cloud SQL Connector/Auth Proxy or verified CA/certificate TLS | Never disable certificate validation to hide errors |
| **Secrets** | Secret Manager and rotation | Never store DB passwords inside Docker images |
| **Application** | Prepared statements, multi-tenant authorization, idempotency | One tenant cannot read another tenant's orders |

**PSC is not PostgreSQL IAM authorization.** Allowed projects only control who may create a PSC endpoint to the instance. Once an endpoint is accepted, you must still govern who can reach that IP over the network and who holds DB credentials.

### High Availability and Migration

Keep two concepts separate:

- **Private network connectivity**: PSA/PSC is the app → instance transport path; it does not add HA, backups, PITR, or replication.
- **Database availability**: `REGIONAL` instances, HA/failover, replicas, backups, monitoring, connection retries, and recovery plans.

When migrating from PSA to PSC or enabling both:

1. Inventory connection sources (VMs, GKE, Cloud Run), DB clients, DNS, VPCs, IAM, and dependencies.
2. Verify Cloud SQL edition, engine/version, and **PSA + PSC** support; assess patch downtime.
3. Create the new endpoint in the consumer VPC; wait for `ACCEPTED` and verify private DNS.
4. Canary-test connectivity with Connector `ipTypes=PSC`, verify real queries/transactions, and measure P95 latency.
5. Shift clients gradually; keep PSA during the rollback window if the instance and workflow permit.
6. Remove old PSA ranges/routing only after zero workloads depend on them, avoiding breaking other Google services sharing PSA peering.

**Never modify private networking on a production instance or delete peerings without a maintenance window.** Some Cloud SQL network changes require a restart and cause downtime.

### Pools, Timeouts, and Avoiding Connection Storms

Suppose there are **20 Cloud Run instances**, each opening a JDBC pool of up to 10 connections. The database may have to serve **200 connections** from a single service alone, excluding read replicas, BI jobs, and migrations.

~~~text
Maximum possible connections (nominal)
  = Max app instances × Max JDBC connections / instance
  = 20 × 10 = 200
~~~

Keep `maximumPoolSize` small per SLO and Cloud SQL limits, with explicit connection and idle timeouts; minimize idle connections in serverless runtimes. For large PostgreSQL workloads, evaluate managed connection pooling or PgBouncer where supported by product/edition and design; **pooling never fixes slow queries**.

### Accounting for All Costs

Cloud SQL instance CPU/RAM/storage/backups are still billed when private. PSA involves managing IP ranges and networking; PSC incurs **endpoint/data processing or related charges per Private Service Connect pricing**, plus egress/cross-region transfer, Cloud DNS, NAT/VPC connectors if used, logging, and monitoring. Multi-region/HA and replicas heavily impact total cost.

**Do not conclude PSC is always cheaper or costlier than PSA from a single IP unit price.** Compare total costs across IP/routing operations, per-VPC endpoints, network traffic, security boundaries, HA, operations, and migration.

## 10. Runbook: Diagnosing Connection Failures

Always investigate in order: **instance → network → DNS → TCP → IAM Connector → database authentication → application**. Many failures look like `connection failed` yet have completely different causes.

| Symptom | Possible Cause | Priority Step |
|---|---|---|
| `SERVICE_NETWORKING_NOT_ENABLED` | Service Networking API disabled | Enable `servicenetworking.googleapis.com` in the right project; check host/service project for Shared VPC |
| `NETWORK_NOT_PEERED` when creating private IP | PSA private connection incomplete | Check `gcloud services vpc-peerings list`, operation status, and allocated range |
| PSA IP range exhausted/overlap | PSA range overlaps CIDR or lacks space | Plan a new range; never alter an active range carelessly |
| PSC `REJECTED` | Consumer project missing from allowed list or misconfigured endpoint | Check instance PSC settings, service attachment, and endpoint state |
| Prolonged PSC `PENDING` | Provisioning unfinished, org policy, or quota | Check `forwarding-rules describe`, Cloud SQL operations, network team IAM |
| PSC DNS `NXDOMAIN` | Missing private zone/record or VPC lacks visibility | Check DNS zone visibility, actual Cloud SQL hostname, DNS automation |
| `Connection timed out` | Missing route, firewall/NetworkPolicy block, Cloud Run lacks VPC egress | Run `nc` from the **actual runtime network** to IP:5432 |
| `Connection refused` | Wrong IP/port, inactive endpoint, DB service not ready | Check endpoint IP / instance health and engine type |
| Connector returns `403` | Runtime SA lacks Cloud SQL Client or wrong project/API | Check IAM bindings, ADC, Cloud SQL Admin API |
| `FATAL: password authentication failed` | Wrong DB username/password or stale secret | Check DB users and Secret Manager version; never grant random IAM roles |
| `no pg_hba.conf entry`/TLS failure | Auth/SSL mismatch with client/CA | Check DB engine logs, TLS mode, Connector/Proxy |
| `too many connections` | `Pool × instances` exceeds capacity | Check active connections, Hikari pool, Cloud Run max instances |
| Intermittent timeouts | Stale DNS, failover, pool holding dead sockets, cross-region links | Check DNS TTL, reconnect/backoff, P95 latency, HA events |
| New Cloud Run deploy fails while old works | New revision changed network/subnet or runtime SA | Diff VPC config and identity across revisions |

### Read-Only Diagnostic Commands

~~~bash
DB_PROJECT="data-lab-project"
DB_INSTANCE="orders-pg-psc"
APP_PROJECT="app-lab-project"
REGION="asia-southeast1"
PSC_ENDPOINT="orders-sql-psc-endpoint"

# Cloud SQL: engine, status, IP, PSC attachment, and settings.
gcloud sql instances describe "$DB_INSTANCE" \
  --project="$DB_PROJECT" \
  --format="yaml(state,region,connectionName,ipAddresses,pscServiceAttachmentLink,settings.ipConfiguration)"

# Consumer PSC endpoint: IP and connection status.
gcloud compute forwarding-rules describe "$PSC_ENDPOINT" \
  --project="$APP_PROJECT" \
  --region="$REGION" \
  --format="yaml(IPAddress,pscConnectionStatus,target)"

# PSA: run if the database uses Private Services Access.
gcloud services vpc-peerings list \
  --network=orders-vpc \
  --project=orders-lab-project

# Cloud Run: network/SA and latest revision.
gcloud run services describe orders-api \
  --project="$APP_PROJECT" \
  --region="$REGION"
~~~

Inside the **application VM/Pod** (not a Cloud Shell lacking VPC reachability):

~~~bash
# Use the PSC hostname provided by Cloud SQL for the consumer network.
nslookup "ACTUAL_CLOUD_SQL_PSC_DNS_NAME"
nc -vz "ACTUAL_CLOUD_SQL_PSC_DNS_NAME" 5432

# If DNS is not set up yet while the endpoint is ACCEPTED:
nc -vz "ACTUAL_PSC_ENDPOINT_INTERNAL_IP" 5432
~~~

**Interpreting results:**

1. Hostname fails to resolve: **DNS visibility/record** issue, nothing to do with DB passwords yet.
2. Resolves to the right IP but TCP times out: **VPC route/firewall/egress/endpoint** issue.
3. TCP succeeds, Connector fails to get a token: **ADC/IAM/Cloud SQL Admin API** issue.
4. Connector reaches DB but `password authentication failed`: **database identity/grants** issue, not `roles/cloudsql.client`.
5. Connected yet queries are slow: inspect **DB performance, indexes, pools, locks, and network latency**.

When suspecting firewalls, check the **exact network tags and egress direction** of the workload. Never temporarily open `0.0.0.0/0` in VPC firewalls or Cloud SQL authorized networks for a "quick test"; it muddies root cause and increases risk.

### Logs, Metrics, and Auditing

| Source | Signals to Monitor |
|---|---|
| Cloud SQL | Instance health, active connections, CPU, memory, storage, failover, query latency |
| VPC Flow Logs / Firewall Rules Logging | Traffic to PSC IP or PSA range being dropped or misrouted |
| PSC forwarding rule metrics/status | `pscConnectionStatus`, data processed, endpoint health |
| Cloud DNS | Resolution success/latency and private zone bindings |
| Cloud Run / GKE | Connection errors, cold starts, Hikari pool exhaustion, 5xx |
| Cloud Audit Logs | Changes to Cloud SQL settings, PSC allowed projects, IAM, VPC resources |
| Billing | Cloud SQL compute/storage/backups, PSC traffic/endpoints, networking, DNS, logging |

Enable only needed log types per retention policy: DB logs or client debug logs can contain queries/PII. Never print database passwords, IAM tokens, or full connection strings containing secrets to logs.

## 11. PSA vs. PSC? Topology-Driven Decisions

| Scenario | Candidate to Consider First | Rationale |
|---|---|---|
| One Java API and database in the **same VPC**, minimal network churn | **PSA private IP** | Fewer per-VPC endpoints/DNS records if peering already exists |
| Multiple independent team projects/VPCs accessing the **same instance** | **PSC** | Each consumer gets its own endpoint, avoiding multi-VPC peering chains |
| Phased transition from legacy PSA apps to multi-VPC topology | **PSA + PSC** where supported | Both paths coexist during migration |
| Workloads only from on-prem over VPN/Interconnect | **Evaluate both** | Route propagation, DNS, and firewalls decide |
| Instance needs DR / cross-region read/write | **PSC + DNS/write endpoint** where edition supports | Logical DNS reduces hardcoded IP coupling; still needs full DR design |
| Java app simply needs Cloud SQL over private networking | **Connector + PSA or PSC** | Connector handles auth/TLS; network method follows topology |

**No single default fits every enterprise.** With one VPC and an instance running smoothly on PSA, there is no mandatory reason to switch to PSC. With multiple VPCs/projects sharing access, PSC often gives cleaner operational boundaries, at the cost of managing more endpoints, DNS records, IAM, and quotas.

### Enterprise Scenario

A company has:

~~~text
Project data-prod:
   Cloud SQL PostgreSQL orders-db (HA, backups)

Project shop-prod:
   Cloud Run orders-api
   VPC orders-vpc

Project reports-prod:
   GKE analytics cluster
   VPC reports-vpc
~~~

Using PSA from `orders-vpc` alone does **not automatically give GKE in `reports-vpc` a route** to Cloud SQL just because the VPCs share an organization. With PSC, the database team allows both consumer projects, each team creates an endpoint in its own VPC, configures DNS, and tests connectivity. Runtime SAs receive `roles/cloudsql.client` when using Connectors, while the database maintains **separate users/grants** for API read/write vs. analytics read-only.

For the reporting app, prefer a **read replica** or rate-limited workload so it does not degrade the primary's SLO. Using multiple PSC endpoints **does not provide automatic database load balancing or HA**; endpoints targeting the same primary still depend on that single primary.

## 12. Specific Notes on AlloyDB

This chapter covers both **Cloud SQL and AlloyDB for PostgreSQL**, yet **you do not use Cloud SQL commands to create an AlloyDB cluster**. AlloyDB also provides private networking options, including **PSC for AlloyDB**, with different resources and tools:

- **AlloyDB clusters/instances** are managed via `gcloud alloydb ...` and a separate API; Cloud SQL uses `gcloud sql instances ...`.
- With AlloyDB PSC, endpoints still attach a service attachment to a consumer VPC, but the DNS name comes from the AlloyDB instance's **`pscDnsName`** field, requiring a private DNS record pointing to the endpoint IP when using **AlloyDB Auth Proxy/Language Connectors**.
- **Cloud SQL Auth Proxy/Java Connector** and **AlloyDB Auth Proxy/Language Connector** are **two different toolsets**; never mix them simply because both support PostgreSQL.
- AlloyDB networking, HA, read pools, DR, connection pooling, and pricing must be evaluated separately. Never carry Cloud SQL limits, CLI flags, or costs over to AlloyDB.

For Cloud SQL exercises in this document, all `gcloud sql`, `ipTypes=PSC`, and `CloudSqlDataSource` examples apply to **Cloud SQL PostgreSQL**, not AlloyDB.

## 13. Production Deployment Checklist

- [ ] Confirmed Cloud SQL engine/edition, instance, project/region, HA/backup requirements, and SLO.
- [ ] Selected PSA, PSC, or combined mode based on **VPC topology** and team/project boundaries.
- [ ] PSA uses a non-overlapping IP range, Service Networking connection is active, and IP capacity is planned.
- [ ] PSC is enabled on the instance, allowed projects match, and endpoints show `ACCEPTED`.
- [ ] PSC private DNS resolves to the right IP inside **every consumer VPC**; Connector/Proxy versions are compatible.
- [ ] Cloud Run/GKE/VMs have egress paths to the target IP; NetworkPolicy/firewalls allow DB and API traffic.
- [ ] Runtime SAs use ADC and least-privilege IAM; Cloud SQL Client is kept separate from DB users/grants.
- [ ] Using Connector/Proxy or verified TLS for direct TCP; zero passwords in container images or Git.
- [ ] `JDBC pool × instance count` stays within DB capacity; timeouts, reconnects, and failover are tested.
- [ ] Canary migration, rollout/rollback, DR, audit logs, monitoring, and billing alerts are in place.
- [ ] Guarded against deleting private connections, PSC endpoints, or Cloud SQL instances while consumers remain.

## 14. Practice Exercises

**Exercise 1 — Architecture comparison.** Diagram both VM → Cloud SQL via PSA and VM → PSC endpoint → Cloud SQL. Indicate the owning network project, client-side IP address, and DNS dependencies in each design.

**Exercise 2 — Setting up PSA.** Starting from an existing lab VPC, list the commands to enable Service Networking, reserve a `VPC_PEERING` range, create the private connection, and launch a Cloud SQL PostgreSQL instance with no public IP. Explain why the VM subnet `10.20.0.0/24` must not be used as the PSA range.

**Exercise 3 — Cross-project PSC.** Database project A allows projects B and C. Design one endpoint per VPC, choose IPs/subnets, verify `pscConnectionStatus`, and describe the private DNS records required if endpoint IPs differ.

**Exercise 4 — Java Connector.** Write a Java method creating a HikariCP pool with `ipTypes=PRIVATE`, then switch it to `PSC`. List **at least three prerequisites** beyond changing `ipTypes` for Java to actually connect over PSC.

**Exercise 5 — Cloud Run.** A service's runtime SA has Cloud SQL Client, yet connections to `10.30.0.10:5432` time out. List the Direct VPC egress, subnet, `ACCEPTED` endpoint, firewall, and DNS checks to run before adding any IAM roles.

**Exercise 6 — Error classification.** Classify `NETWORK_NOT_PEERED`, `PSC REJECTED`, `NXDOMAIN`, `403 Cloud SQL Admin API`, and `FATAL password authentication failed` respectively as **PSA**, **PSC admission**, **DNS**, **IAM Connector**, or **database auth** failures.

**Exercise 7 — Connection capacity.** A Java service has 30 Cloud Run instances, each with a max pool of 8 connections. Calculate the nominal maximum connections, explain the risk if Cloud SQL only has 150 free slots, and propose pool/scaling adjustments.

**Exercise 8 — Migration design.** A team currently uses PSA and adds three apps from other VPCs. Plan enabling PSA + PSC together, canary testing, switching DNS/Connector, monitoring SLOs, and rolling back if PSC fails. Why must you not delete PSA immediately once one PSC endpoint shows `ACCEPTED`?

**Exercise 9 — AlloyDB.** A colleague runs Cloud SQL Auth Proxy against `gcloud alloydb` and asks why it fails. Explain the differences between Cloud SQL and AlloyDB PSC, `pscDnsName`, AlloyDB Auth Proxy/Connectors, and which docs to consult.

## Official References

- [Cloud SQL — Private IP connection overview](https://cloud.google.com/sql/docs/postgres/private-ip) — architecture and prerequisites for private IP connectivity.
- [Configure private services access (PSA)](https://cloud.google.com/sql/docs/postgres/configure-private-services-access) — allocating IP ranges, Service Networking, and peering.
- [Connect to Cloud SQL using private IP](https://cloud.google.com/sql/docs/postgres/connect-instance-private-ip) — VPC clients, Auth Proxy, and testing.
- [Cloud SQL Private Service Connect overview](https://cloud.google.com/sql/docs/postgres/about-private-service-connect) — endpoints, service attachments, and DNS.
- [Configure Private Service Connect](https://cloud.google.com/sql/docs/postgres/configure-private-service-connect) — PSC instances, allowed projects, forwarding rules, and states.
- [Configure DNS for PSC](https://cloud.google.com/sql/docs/postgres/configure-dns) — DNS automation and private zones.
- [Configure both PSA and PSC](https://cloud.google.com/sql/docs/postgres/configure-private-services-access-and-private-service-connect) — migration and limits.
- [Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/connect-auth-proxy) — securing connections, `--private-ip`, and PSC.
- [Cloud SQL Java Connector JDBC](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory/blob/main/docs/jdbc.md) — `ipTypes=PRIVATE/PSC`, ADC, and pooling.
- [Connect Cloud Run to Cloud SQL](https://cloud.google.com/sql/docs/postgres/connect-run) — serverless private IP and DB authentication.
- [Cloud Run Direct VPC egress](https://cloud.google.com/run/docs/configuring/vpc-direct-vpc) — routing to consumer VPCs.
- [AlloyDB — Private Service Connect overview](https://cloud.google.com/alloydb/docs/about-private-service-connect) — cluster/instance model and `pscDnsName`.
- [AlloyDB — Configure Private Service Connect](https://cloud.google.com/alloydb/docs/configure-private-service-connect) — endpoints and private DNS.
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing) and [Private Service Connect pricing](https://cloud.google.com/vpc/network-pricing#private-service-connect) — database and network cost estimation.

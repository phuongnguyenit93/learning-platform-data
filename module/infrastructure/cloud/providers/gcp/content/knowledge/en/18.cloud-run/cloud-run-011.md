# Connecting Cloud Run to Cloud SQL and Private Services

> **Chapter:** Cloud Run  
> **Module:** CLOUD_PROVIDERS_GCP

A Java API running on **Cloud Run** needs to store orders in **Cloud SQL for PostgreSQL**, read an internal cache, and call a payment-processing service restricted strictly to internal callers. To deploy safely, you must solve **three separate questions**: which network path packets take, which identity is authorized to connect, and how the application manages connections as Cloud Run autoscales.

In the **CLOUD_PROVIDERS_GCP** module, learners progress from projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, databases, release automation, and reliability/cost monitoring. This lesson focuses on **Cloud Run services**, illustrated with **PostgreSQL**; the networking principles also apply to Cloud Run jobs, MySQL, SQL Server, and other private services, though ports, drivers, and permissions must be adjusted per product.

**Learning outcomes:**

1. Distinguish **ingress**, **egress**, **VPC routing**, **IAM**, and **database authentication**.
2. Choose **Direct VPC egress** or a **Serverless VPC Access connector** and `private-ranges-only`/`all-traffic` modes.
3. Connect Cloud Run to Cloud SQL via **public IP + Cloud SQL connector/proxy** or **private IP + VPC** without mixing mechanisms.
4. Use the **Cloud SQL Java Connector**, Secret Manager, and a least-privilege runtime service account.
5. Reach VMs, internal services, or another Cloud Run service with proper authentication.
6. Size connection pools for Cloud Run autoscaling to avoid exhausting Cloud SQL connections.
7. Verify DNS, routes, firewalls, IAM, logs, timeouts, and safe recovery.

## 1. Reference Architecture and Control Layers

~~~mermaid
flowchart TB
    CLIENT["Authenticated client"] --> INGRESS["Cloud Run ingress + Invoker IAM"]
    INGRESS --> API["Cloud Run: orders-api\nJava, runtime service account"]
    API --> EGRESS["Direct VPC egress\nprivate-ranges-only"]
    subgraph VPC["Resources in VPC"]
      EGRESS --> SQL["Cloud SQL PostgreSQL\nPrivate IP :5432"]
      EGRESS --> CACHE["Cache / VM / internal LB\nPrivate IP"]
    end
    API --> SECRET["Secret Manager\nDB credentials"]
    API --> IAM["Cloud SQL Admin API + IAM\n(when using Java Connector)"]
    API --> TASK["Cloud Run private service\nvia internal path + ID token"]
    TASK --> INV["roles/run.invoker"]
    API --> OBS["Cloud Logging / Monitoring"]
~~~

**Inbound and outbound paths are independent:**

- **Ingress** governs **which sources may call Cloud Run's HTTP endpoint**; `--ingress=internal` does not automatically grant an outbound path to Cloud SQL.
- **Egress** governs **how outbound Cloud Run traffic** traverses a VPC; `--network/--subnet` does not automatically make Cloud Run's URL internal-only.
- **VPC/firewalls/routes/DNS** decide whether a network path to a private IP/endpoint exists.
- **IAM** controls authorization to call Google APIs, such as the Cloud SQL Connector or invoking an authenticated Cloud Run service.
- **DB username/password or IAM database authentication** governs access **inside PostgreSQL**; it is not automatically granted by `roles/cloudsql.client`.

**Key takeaway:** A `403` may indicate missing IAM; `connection timed out` usually points to networking; `password authentication failed` is PostgreSQL authentication. Never "fix" all of them by opening firewalls or granting Project Owner.

## 2. Connection Method Selection Matrix

| Target | Common connection path | Required authentication |
| --- | --- | --- |
| Cloud SQL **public IP** | Cloud SQL Java Connector or Cloud Run built-in Auth Proxy/Unix socket | `cloudsql.client` IAM for connector/proxy **and** DB credentials |
| Cloud SQL **private IP** | Direct VPC egress/connector → TCP to private IP, or **Java Connector with PRIVATE** | Network + DB auth; Java Connector also needs IAM/API |
| Cloud SQL via **Private Service Connect (PSC)** | Private endpoint/address and DNS/routing per PSC setup | Network + DB auth; connector if used also needs IAM/API |
| Compute Engine VM / GKE internal Load Balancer | Direct VPC egress/connector → internal IP/port | Ingress/egress firewalls, TLS, and app auth |
| Memorystore/Redis-compatible cache | VPC egress → internal endpoint | Permissions/network and AUTH/TLS per product edition |
| **Private Cloud Run service** | Path recognized by Cloud Run as internal + **Google-signed ID token** | Caller holds `roles/run.invoker` on callee |
| Google APIs such as Secret Manager | Google API endpoint and runtime service identity | IAM on secret/resource; typically no direct DB TCP path needed |

**Note:** Cloud SQL **private IP** is not Private Google Access (PGA). Cloud SQL private IP typically relies on **Private Services Access (PSA)** or **PSC** depending on how the instance is created. PGA is a mechanism for reaching **supported Google APIs** from sources without external IPs. The two mechanisms solve different destination types.

### 2.1. Public IP + Connector/Proxy Still Uses Encryption and IAM

A public IP on Cloud SQL **does not mean** the application opens an unprotected public PostgreSQL connection. With a **Cloud SQL Language Connector or Cloud SQL Auth Proxy**, the channel enforces **IAM authorization and encryption**; in production, still evaluate minimizing public exposure and adopting private connectivity per policy.

If using **Cloud Run's built-in Cloud SQL connection** via `--add-cloudsql-instances`, Cloud Run exposes a Unix socket at `/cloudsql/PROJECT:REGION:INSTANCE`. However, **Java does not natively support Unix-domain sockets via standard plain JDBC**; for Java, the **Cloud SQL Java Connector (JDBC Socket Factory)** is typically the natural choice.

### 2.2. Private IP Offers Two Distinct Implementation Choices

**A. Direct TCP connection:** `Cloud Run → VPC → private IP:5432`, where the application handles **TLS/certificate validation** itself as required by policy, using PostgreSQL credentials. **No** `--add-cloudsql-instances` or Cloud SQL Client IAM is needed just to open TCP to the database; if using IAM DB auth, additional requirements apply.

**B. Cloud SQL Java Connector with `ipTypes=PRIVATE`:** the app uses the JDBC Socket Factory; the connector establishes an encrypted channel and authenticates the connection via IAM, **yet still requires a VPC route to the private IP**. You must enable the Cloud SQL Admin API, grant `roles/cloudsql.client`, and provide DB auth (or configured IAM DB auth). Enabling VPC egress alone does not replace connector permissions.

**Never treat** the Java Connector as a VPN tunnel: it cannot establish a private IP path if Cloud Run lacks VPC connectivity.

## 3. Direct VPC Egress and Serverless VPC Access

Cloud Run provides two ways to send **outbound** traffic into a VPC:

| Criterion | **Direct VPC egress** | **Serverless VPC Access connector** |
| --- | --- | --- |
| Architecture | Cloud Run connects directly to a VPC/subnet, **without connector VMs** | Regional connector acts as an intermediary into the VPC |
| Current recommendation | **Preferred for new designs** when supported in region/product | Compatibility with legacy architectures or specific constraints |
| Primary flags | `--network`, `--subnet`, `--vpc-egress` | `--vpc-connector`, `--vpc-egress` |
| Scaling/cost | No connector VM operations cost; related traffic and IP resources apply | Connector has its own capacity, autoscaling, and baseline cost |
| Firewall | Can use **network tags** on Cloud Run revisions to govern egress | Uses connector rules/service agent per guidance |
| Inbound path to Cloud Run service | **Does not create direct internal ingress** | **Does not create direct internal ingress** |

Cloud Run **services and jobs** use Direct VPC for **egress**, not as an inbound TCP listener inside the VPC like a VM. When VPC clients must call Cloud Run, configure **ingress/ILB/PSC/endpoint routing** separately.

### 3.1. Two Outbound Routing Modes

| Egress mode | Behavior | Scenario |
| --- | --- | --- |
| `private-ranges-only` | Routes only traffic to **internal address ranges** per product rules through the VPC | Cloud SQL private IP, VMs/private LBs |
| `all-traffic` | Routes **all outbound traffic** through the VPC | Need firewalls, proxy/NAT, egress inspection, or custom routes |

If using `all-traffic` when the app needs Internet access, design **Public Cloud NAT/proxies** and matching firewalls/routes; enabling the egress mode alone does not create NAT. When targeting **PSC endpoints, addresses outside standard private ranges, or special DNS**, verify exact resolved destination IPs and routes so you do not pick `private-ranges-only` by mistake.

### 3.2. Direct VPC Egress Checklist

1. **Subnet region must match the Cloud Run service region.**
2. The VPC/subnet exists and Cloud Run identities/service agents have permission to use it (especially in **Shared VPC**).
3. The subnet has **enough IP addresses** for scale-out; Cloud Run holds IPs during initialization and release windows.
4. Firewalls for **Cloud Run source egress** and **destination ingress** permit required TCP/ports; if hierarchical policies apply, check organization level too.
5. Cloud SQL private connectivity (PSA/PSC) is established and the target genuinely has a private IP/endpoint.
6. Return routes, peering, Cloud VPN/Interconnect, DNS, egress restrictions, and endpoint addresses align.
7. If the app only needs a private IP database, **do not reflexively enable `all-traffic`**.

In Shared VPC, service identities, host/service projects, and **Compute Network User permissions** must follow documentation. Never edit permissions across the entire host project just to bypass a permission error.

### 3.3. Sample Inspection and Configuration Commands

~~~bash
# Read-only inspection, makes no changes
gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud compute networks subnets describe run-egress-subnet \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud sql instances describe orders-db \
  --project=LAB_PROJECT_ID
~~~

Assuming service `orders-api` **already has a valid image and deploy permissions**, the command below updates its revision to route through the VPC:

~~~bash
# MODIFIES service; run only in an approved lab
gcloud run services update orders-api \
  --network=app-vpc \
  --subnet=run-egress-subnet \
  --vpc-egress=private-ranges-only \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

If using an existing connector:

~~~bash
# ALTERNATIVE OPTION; do not stack both connection methods
gcloud run services update orders-api \
  --vpc-connector=orders-vpc-connector \
  --vpc-egress=private-ranges-only \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

**Do not run both commands back-to-back "just to be extra secure"**: pick one egress mode per revision, verify the resulting configuration, and check traffic impact. When the VPC subnet lives in a host project, use Shared VPC configuration and full resource names per docs.

## 4. Access Permissions and Resource Preparation

### 4.1. Consistent Lab Values

| Resource | Illustrative value |
| --- | --- |
| Project (Cloud Run + SQL in the same lab project) | `LAB_PROJECT_ID` |
| Region | `asia-southeast1` |
| Cloud Run service | `orders-api` |
| Runtime service account | `orders-runtime@LAB_PROJECT_ID.iam.gserviceaccount.com` |
| VPC / subnet | `app-vpc` / `run-egress-subnet` |
| Cloud SQL instance | `orders-db` (PostgreSQL) |
| Instance connection name | `LAB_PROJECT_ID:asia-southeast1:orders-db` |
| Cloud SQL private IP | `10.80.0.5` (**illustrative only**) |
| Database / user | `orders` / `orders_app` |
| Secret Manager | `orders-db-password` |
| Other internal service | `payments-internal` |
| Cloud Run image | `IMAGE_URI_BY_DIGEST` (real application image) |

**Never use** illustrative IPs/names as real production values. Retrieve real private IPs from instance metadata and DNS/PSC per setup. Test resources should live in an authorized, budgeted project not serving live production workloads.

### 4.2. IAM by Role

| Identity | Corresponding permission | Notes |
| --- | --- | --- |
| Cloud Run deployer | Cloud Run management permissions + `iam.serviceAccounts.actAs` on runtime SA | Distinct from runtime SA |
| **Runtime service account** | `roles/cloudsql.client` if using Cloud SQL Connector/Proxy | Granted in the project containing Cloud SQL |
| Runtime SA reading secret | `roles/secretmanager.secretAccessor` on **the exact secret** | Separate dev/prod secrets |
| Cloud Run calling private Cloud Run | `roles/run.invoker` on **callee service** | Requires valid ID token |
| Runtime SA calling other Google APIs | Exact role on target resource | Do not grant Editor by default |
| VPC/Shared VPC administrator | Permissions to configure subnets, peering, PSC, and egress | Do not merge into app runtime SA |

If Cloud Run and Cloud SQL live in **two separate projects**, check **Cloud SQL Admin API in both projects** when using a connector/proxy and grant `cloudsql.client` to the calling identity on the Cloud SQL project. Private networking via Shared VPC/PSC must be configured independently.

**Cloud SQL Client IAM is not a PostgreSQL role.** Beyond IAM, the database itself must have `orders_app` granted `CONNECT`, required schema/table privileges, and either a password or properly configured IAM database auth. Avoid running the application as the `postgres` superuser.

### 4.3. Secrets and Non-Sensitive Configuration

Use **Secret Manager** for DB passwords, certificates, or sensitive data; use standard environment variables for non-sensitive settings such as database name, instance connection name, or app flags.

~~~bash
# Read metadata without printing secret values
gcloud secrets describe orders-db-password \
  --project=LAB_PROJECT_ID

gcloud sql instances describe orders-db \
  --format="yaml(name,region,connectionName,ipAddresses,settings.ipConfiguration)" \
  --project=LAB_PROJECT_ID
~~~

Cloud Run can reference secrets as environment variables or mounted volumes. With **env vars**, values are resolved at instance startup; secret rotation does not automatically update already running containers. With **volumes**, the `latest` version can be re-read differently; design rotation and retries per docs. In production, consider pinning **numeric versions** for reproducible, auditable rollouts.

Never store DB passwords in Dockerfiles, image layers, Git source, CI logs, public Cloud Run YAML, or URL query parameters.

## 5. Connecting to Cloud SQL PostgreSQL with the Java Connector

For a Java app on Cloud Run needing Cloud SQL **private IP**, a convenient option is the **Cloud SQL JDBC Socket Factory** (Cloud SQL Java Connector): the connector handles IAM authorization and establishes an encrypted tunnel, while we specify `PRIVATE` to select the private IP address. VPC networking **must still be ready**.

### 5.1. Dependencies and JDBC Configuration

The Java application needs the PostgreSQL JDBC driver, HikariCP (or an equivalent pool), and a compatible **Cloud SQL PostgreSQL Socket Factory** library. Do not hardcode library versions here: choose versions tested against your JDK/framework and the [Cloud SQL Java Connector](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory).

Example DataSource factory method:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class OrderDataSource {
    private OrderDataSource() {}

    public static HikariDataSource create() {
        String dbName = System.getenv("DB_NAME");
        String dbUser = System.getenv("DB_USER");
        String dbPass = System.getenv("DB_PASS"); // Injected from Secret Manager
        String instance = System.getenv("INSTANCE_CONNECTION_NAME");

        HikariConfig cfg = new HikariConfig();
        cfg.setJdbcUrl("jdbc:postgresql:///" + dbName);
        cfg.setUsername(dbUser);
        cfg.setPassword(dbPass);

        cfg.addDataSourceProperty(
            "socketFactory", "com.google.cloud.sql.postgres.SocketFactory");
        cfg.addDataSourceProperty("cloudSqlInstance", instance);
        cfg.addDataSourceProperty("ipTypes", "PRIVATE");
        cfg.addDataSourceProperty("cloudSqlRefreshStrategy", "lazy");

        cfg.setMaximumPoolSize(5);
        cfg.setMinimumIdle(0);
        cfg.setConnectionTimeout(10_000);
        cfg.setMaxLifetime(1_800_000);

        return new HikariDataSource(cfg);
    }
}
~~~

**How to read the code:**

- `cloudSqlInstance` takes the `PROJECT:REGION:INSTANCE` identifier, **not** a hostname or IP.
- `ipTypes=PRIVATE` forces the connector to select a private IP; missing Direct VPC egress/connector or missing private IP will fail.
- `cloudSqlRefreshStrategy=lazy` fits serverless where CPU may not run continuously between requests; avoid relying on scheduled background refreshes when CPU is throttled.
- `DB_PASS` is the PostgreSQL credential; **Cloud SQL Client IAM** on the runtime service account remains a separate requirement when using the connector.
- `maximumPoolSize=5` is strictly a lab value; size it against **concurrent Cloud Run instances**, DB limits, and transaction durations.

This is a **DataSource snippet**, not a complete HTTP application; wire it into Spring Boot/Quarkus with proper dependencies, retry policies, and exception handling. Never create a new DataSource/pool **per request**; normally create one shared pool for the container lifecycle.

### 5.2. Read-Only DB Check Example

Once the DataSource is created, the app can expose an **internal-only** check endpoint:

~~~java
try (var connection = dataSource.getConnection();
     var statement = connection.prepareStatement("SELECT 1");
     var results = statement.executeQuery()) {
    if (results.next()) {
        return "db-ok";
    }
}
~~~

Never return raw SQL exception details, usernames, internal hostnames, or stack traces to public clients. Cloud Run health/liveness checks **should not blindly depend on the DB** if a database hiccup would restart/penalize every container and amplify recovery load. Use separate DB readiness/telemetry when needed.

### 5.3. Why Choose the Connector Over Direct TCP?

| Criterion | Java Connector + private IP | Direct TCP to private IP |
| --- | --- | --- |
| Target identifier | Instance connection name | Private IP or private DNS |
| Connection auth to Cloud SQL | IAM + Cloud SQL Admin API | VPC reachability, DB auth; Cloud SQL IAM does not participate automatically |
| Encryption to Cloud SQL | Connector provides TLS | Must configure TLS/CA and validate per policy yourself |
| Network path | **VPC private connectivity still required** | VPC private connectivity required |
| App complexity | Adds library and IAM/API dependency | Standard driver plus TLS/certificate management |
| Best suited when | Prefer IAM-backed encrypted connections | Standardized on TLS/DB host management or different connector requirements |

If choosing **direct TCP** in production, do not use an example like `jdbc:postgresql://10.80.0.5:5432/orders` with default SSL assuming "private IP encrypts automatically." Enforce the Cloud SQL instance's TLS policy, verify server identity, and configure certificates/JDBC properties accordingly.

## 6. Binding the Cloud Run Revision to VPC, Identity, and Secret

Assume the Java image is already built/pushed to Artifact Registry, health-checked, and referenced **by digest**. Do not use the sample `hello` image expecting DB tests to work.

### 6.1. Deploy a Private Service with Direct VPC Egress

~~~bash
# MODIFIES infrastructure and creates revision: only in an approved lab project
gcloud run deploy orders-api \
  --image=IMAGE_URI_BY_DIGEST \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --service-account=orders-runtime@LAB_PROJECT_ID.iam.gserviceaccount.com \
  --network=app-vpc \
  --subnet=run-egress-subnet \
  --vpc-egress=private-ranges-only \
  --ingress=internal \
  --no-allow-unauthenticated \
  --max-instances=10 \
  --concurrency=20
~~~

**Explaining ingress:** `--ingress=internal` restricts Cloud Run to sources **classified by Cloud Run as internal**—meaning a developer on a laptop **cannot** call the URL directly. It also still requires Invoker IAM. To test from outside, use an approved test environment, proxy, or internal path; never open `--allow-unauthenticated` to work around a 403.

### 6.2. Grant Runtime Permissions (Performed by an Administrator)

The following examples are **illustrative only** for IAM bindings. Substitute real project/SA values and verify scope before running:

~~~bash
# Cloud SQL Connector/Proxy permission; project hosting Cloud SQL
gcloud projects add-iam-policy-binding LAB_PROJECT_ID \
  --member="serviceAccount:orders-runtime@LAB_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"

# Read-only access to the single password secret
gcloud secrets add-iam-policy-binding orders-db-password \
  --member="serviceAccount:orders-runtime@LAB_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=LAB_PROJECT_ID
~~~

In production, organization policy may require project/resource-scoped IAM or custom roles. Never use a default service account holding Editor or embed JSON keys inside containers.

### 6.3. Configure DB Variables and Secret Manager

~~~bash
# MODIFIES revision; DB user, secret, and instance must already exist
gcloud run services update orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --set-env-vars="DB_NAME=orders,DB_USER=orders_app,INSTANCE_CONNECTION_NAME=LAB_PROJECT_ID:asia-southeast1:orders-db" \
  --update-secrets="DB_PASS=orders-db-password:7"
~~~

`:7` is an **illustrative secret version**; replace it with the real created and approved version. Create secrets out-of-band using secret management tooling—never store passwords in Markdown or shell history.

**`--add-cloudsql-instances` is not needed in the Java Connector example** because the connector is initialized by JDBC. Conversely, if a Python/Go app uses Cloud Run's **built-in Auth Proxy via Unix socket** against a Cloud SQL public IP, you must configure the Cloud SQL connection so the socket mounts at `/cloudsql/INSTANCE_CONNECTION_NAME` and grant Cloud SQL Client. These two approaches are **not cumulative required flags**.

### 6.4. Inspect the Revision After Deployment

~~~bash
gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud run revisions list \
  --service=orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud run services logs read orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --limit=50
~~~

Verify network/subnet/egress, runtime service account, secret references, revision rollout, and logs. Never print secret values in logs. **A Ready revision alone does not prove DB connectivity succeeded** if code only connects upon incoming requests; smoke test from an authorized caller and verify the `SELECT 1` check.

## 7. Alternative: Built-In Cloud SQL Connection via Public IP

Cloud Run supports built-in Cloud SQL Auth Proxy integration for languages that use **Unix sockets**. PostgreSQL-specific example:

~~~bash
# Modifies Cloud Run revision: attaches Cloud SQL connection config
gcloud run services update orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --add-cloudsql-instances=LAB_PROJECT_ID:asia-southeast1:orders-db
~~~

Socket path:

~~~text
/cloudsql/LAB_PROJECT_ID:asia-southeast1:orders-db/.s.PGSQL.5432
~~~

Some PostgreSQL libraries append the `.s.PGSQL.5432` suffix automatically; others require specifying the full path. Linux Unix socket path length limits must also be considered. **Java should prefer the Cloud SQL Java Connector** rather than assuming JDBC drivers support Unix sockets natively like Python/Go.

**Notes:**

- Using the public IP path with the built-in Cloud SQL connection still requires **IAM `roles/cloudsql.client`**, Cloud SQL Admin API, and DB auth.
- On Cloud Run's **first-generation execution environment**, documentation notes Cloud SQL server CA mode restrictions (per-instance CA only) due to the embedded legacy Auth Proxy; verify execution environment and CA mode when using the public-proxy path.
- **Built-in Cloud SQL integration does not turn an instance into private-IP-only.** Check public/private IP settings separately.
- Private SQL over Direct VPC egress with **Java Connector `ipTypes=PRIVATE`** is the primary approach in this lesson; do not mix the command above into the same flow "just to be sure."

## 8. Connecting to Other Private VPC Services

Not every private service is Cloud SQL. A Cloud Run app may call:

| Internal target | Example | Prerequisites |
| --- | --- | --- |
| Compute Engine VM | `10.70.1.10:8080` | VPC routes, VM ingress firewall, app auth |
| GKE internal Load Balancer | `10.70.2.20:8443` | ILB/backend health, VPC reachability, TLS |
| Memorystore | Private IP/endpoint of Redis/Valkey | Product-specific authorized network, AUTH/TLS where enabled |
| Cloud SQL private IP | `10.80.0.5:5432` | PSA/PSC, DB auth, and connector/TLS per method |
| Private Google API endpoint | PSC endpoint or `private.googleapis.com` | DNS, routes, and Google API IAM |
| Internal-ingress Cloud Run service | Cloud Run URL or internal LB/PSC | **Path recognized by Cloud Run as internal + ID token/Invoker IAM** |

### 8.1. VM / Private Load Balancer

For an HTTP service running on a VM with only an internal IP, the app can call:

~~~text
http://10.70.1.10:8080/internal/status
~~~

**Conditions:** the VM must listen on the internal interface (not just `127.0.0.1`), firewalls must permit Cloud Run's exact source range to the port, VPC routes/return paths must match, and the app itself must authenticate requests. **Internal IP does not replace mTLS or application authentication.**

Under Direct VPC egress, you can assign a network tag to the revision:

~~~bash
# Illustrative revision update in lab only
gcloud run services update orders-api \
  --network=app-vpc \
  --subnet=run-egress-subnet \
  --network-tags=orders-egress \
  --vpc-egress=private-ranges-only \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

Reference this tag in appropriate egress firewall rules rather than opening outbound access to every port. Ingress firewall rules on the **target VM** are still required based on actual source ranges and current policies.

### 8.2. Private Google Access / PSC Is Not NAT

- **Private Google Access** enables access to supported Google APIs/services from internal addresses; subnets, DNS, routing, and IAM must align.
- **Private Service Connect** provides private endpoints for Google APIs or supported managed services depending on PSC type; endpoints, DNS, and acceptance must be configured properly.
- **Public Cloud NAT** handles outbound traffic to the Internet per routes/firewalls; **it does not provide inbound access** to VMs or private Cloud SQL.
- **Cloud SQL private IP via PSA** connects to a managed producer network; do not confuse it with an API request to `sqladmin.googleapis.com`.

If a PSC endpoint uses an address outside standard private ranges, adjust egress mode/routes per actual guidance and check which destination IP application DNS resolves to.

## 9. Calling an Internal Cloud Run Service: Network Path and ID Token

Suppose `orders-api` must call `payments-internal` over HTTPS. The receiving service configures `ingress=internal` and **requires authentication**. Two conditions **must both hold**:

1. **Network ingress:** requests arrive from a source Cloud Run considers **internal**, over a supported VPC/endpoint path.
2. **Invoker IAM:** `orders-api`'s runtime service account holds `roles/run.invoker` on `payments-internal` and sends a Google-signed **ID token** with a valid audience.

Granting `roles/run.invoker` **does not bypass** ingress restrictions; setting `ingress=internal` likewise **does not allow** callers to skip authentication.

### 9.1. Why Can Same-Project Calls Still Be Blocked?

If the Cloud Run caller only sets `private-ranges-only`, calling `https://...run.app` may **skip the VPC** because the URL resolves to an address outside private ranges. The callee with `ingress=internal` may reject it even though both services share the same project.

Cloud Run-supported designs include:

- Caller uses **Direct VPC egress or a connector in `all-traffic` mode**, the subnet has **Private Google Access**, and the path to `run.app` via VPC is recognized by Google as internal.
- Front the callee with **Private Service Connect** or an **internal Application Load Balancer**, calling its private endpoint/IP.
- Configure **private.googleapis.com/restricted.googleapis.com** for `run.app` via DNS and PGA per documentation, verifying the actual path.

**Never use `--ingress=all` to "fix" an error when business requirements mandate private-only access.** Diagnose source, URL resolution, routes, ingress, and IAM independently.

### 9.2. Service Invocation Permission Example

~~~bash
# IAM ON THE RECEIVING SERVICE, performed by an authorized administrator
gcloud run services add-iam-policy-binding payments-internal \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --member="serviceAccount:orders-runtime@LAB_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
~~~

Inside `orders-api`, use the **Google Auth Library** to fetch a Google-signed **ID token** from the runtime identity via Application Default Credentials / metadata server; never download JSON service account keys.

~~~text
callee_service_url = "https://payments-internal-<hash>-as.a.run.app"
audience = callee_service_url  # Or configured custom audience
id_token = GoogleAuthLibrary.fetch_id_token(audience)

GET <callee_service_url>/internal/quote
Authorization: Bearer <id_token>
~~~

This is **pseudocode**, not runnable verbatim code. With default Cloud Run authentication, `aud` must be the **callee's service URL**, even when calling a traffic tag URL; custom domains are not default audiences. When traversing an internal LB/PSC with another hostname, still align audience handling with supported configuration.

**Never log ID tokens.** ID tokens differ from OAuth **access tokens** used to call Google APIs. On 401, check token presence, signature, expiry, and audience; on 403, check `run.invoker`, ingress policy, and resource permissions.

### 9.3. Separating Ingress/Egress Across Two Cloud Run Services

~~~mermaid
flowchart LR
  A["orders-api\nCaller"] -->|"Direct VPC egress / connector"| VPC["VPC + PGA or PSC/ILB"]
  VPC -->|"HTTPS + ID token"| B["payments-internal\nInternal ingress + IAM"]
  DB["Cloud SQL private IP"] -. "TCP:5432 via VPC" .-> A
~~~

A single Cloud Run service can simultaneously:

- Receive internal requests via ingress + IAM.
- Send requests to PostgreSQL private IP via VPC.
- Send HTTPS calls to another Cloud Run service using an ID token over a recognized internal path.

Each of these three flows has **separate requirements** and must not be lumped together as one vague "private Cloud Run" concept.

## 10. Connection Pools, Autoscaling, and Database Reliability

Cloud Run autoscales by launching multiple container instances; **each instance can maintain its own connection pool**. Sizing a pool as if running on one fixed server risks exhausting Cloud SQL's `max_connections` during traffic spikes.

### 10.1. Calculating the Connection Budget

Estimation formula:

~~~text
Max DB connections from one revision ≈
  concurrent Cloud Run container instances × maximumPoolSize per instance
~~~

Example:

| Parameter | Illustrative value |
| --- | ---: |
| DB connection budget allocated to orders-api | 120 |
| Cloud Run max instances (configured limit) | 10 |
| Hikari maximumPoolSize | 5 |
| Expected connections at saturation | 10 × 5 = 50 |
| Reserve for overlapping old/new revisions | Must budget separately |
| Reserve for migrations, admin, and other services | Must budget separately |

Do not treat 50 as an absolute ceiling: during a **rollout**, old and new revisions coexist; scaling bursts or platform events can fluctuate active instance counts, and other workloads share the DB. When updating max instances, check whether **service-level or revision-level** limits apply in your Cloud Run setup.

For Cloud Run's **built-in Cloud SQL connection**, Cloud SQL docs note a limit of **100 connections to a single database per Cloud Run instance**; that specific limit **does not apply identically** to the Java Language Connector, Cloud SQL Auth Proxy sidecar, or direct TCP. Nevertheless, **database-wide limits** apply to every connection method. <https://docs.cloud.google.com/sql/docs/postgres/quotas>

### 10.2. Application Settings

- **Reuse pools across requests** rather than opening a fresh connection per request.
- Set `maximumPoolSize` to fit the DB budget; `minimumIdle=0` can suit elastic workloads.
- Keep connection and query timeouts **short and bounded** so requests do not hang past the request timeout.
- Use backoff + jitter for **transient** connection errors; never retry indefinitely on bad passwords or missing IAM.
- Keep transactions short; never hold a DB connection open while waiting on an external HTTP call.
- Maintain separate readiness/telemetry for DB connectivity; liveness probes should not fail on every brief DB blip.
- If high connection counts and traffic are needed, evaluate supported database connection pooling or managed connection pooling, verifying compatibility with your SQL engine and connector.

**CPU throttling:** under request-based billing, background pool-maintenance threads may not run continuously while idle. Cloud SQL docs recommend setting Java Connector `cloudSqlRefreshStrategy=lazy` for serverless. If the workload requires continuous background pool refreshes, evaluate instance-based billing and its cost.

### 10.3. HA Failover and Error Handling

During a Cloud SQL HA failover, active sessions can drop; applications must:

1. Detect broken connections and evict them from the pool.
2. Open fresh connections to the current database endpoint/identity.
3. Retry **idempotent operations** with backoff; never blindly replay financial writes or order creations.
4. Monitor 5xx/latency and database connections.
5. Verify migration compatibility when rolling back revisions.

**Never turn every `connection refused` error into a trigger to restart all Cloud Run instances.** VPC/DB/Secret Manager outages are often shared failures; mass restarts usually make recovery harder.

## 11. Production Security and Operations

### 11.1. Inbound Controls

| Setting | Meaning |
| --- | --- |
| `ingress=internal` | Only sources Cloud Run considers internal |
| `ingress=internal-and-cloud-load-balancing` | Allows controlled traffic via external Application Load Balancer; blocks direct Internet access to `run.app` by default |
| `ingress=all` | Allows all network sources to reach the endpoint; **IAM remains independent** |
| `--no-allow-unauthenticated` | Requires Invoker authentication; does not change ingress config |
| Disabled default URL when suitable | Removes one access path; check dependent integrations/triggers first |

A service using a private IP DB **can still have a public HTTP endpoint** if ingress is unrestricted. Never confuse "private DB" with "private API."

### 11.2. Outbound Controls from Cloud Run

- Use **Direct VPC egress**, subnets, and network tags properly scoped for minimal egress.
- Check VPC firewalls and hierarchical policies; Cloud SQL private networking uses provider/PSC peering, **not just plain VM firewalls**.
- If choosing `all-traffic`, configure NAT/proxies, DNS, and routes instead of expecting Internet access to work automatically.
- For Google APIs (Secret Manager, Cloud SQL Admin API), verify supported access paths and IAM—**never open TCP/5432 to Google API IPs**.
- Never log passwords, connection strings with credentials, or ID tokens.
- Restrict runtime service account permissions; never mix build/deploy identities with runtime identities.
- Use TLS/mTLS or connectors ensuring proper encryption; private IP **does not automatically authenticate the DB server**.

### 11.3. Change and Rollback Planning

Changing VPC egress, subnets, service accounts, or Cloud SQL connection settings creates a new **revision**. Roll out as a low-traffic canary where appropriate, keep the previous revision for rollback, and watch connection errors, latency, and DB capacity. After rolling back a revision, **IAM, secrets, and database schemas do not automatically revert**.

**Costs to budget:** Cloud Run CPU/memory/requests, Cloud SQL HA/storage/backups, connectors or Direct VPC data transfer, Cloud NAT if used, Secret Manager, Cloud Logging/Monitoring, and cross-region transfer. Placing Cloud Run and Cloud SQL in the **same region** generally lowers latency and some costs/risks, though data residency and DR still require evaluation.

## 12. Systematic Observability and Troubleshooting

### 12.1. Read-Only Inspection Commands

~~~bash
# Check networking, ingress, runtime identity, and revision
gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

# Check private/public IP and instance connection name
gcloud sql instances describe orders-db \
  --project=LAB_PROJECT_ID

# Check Cloud Run source subnet
gcloud compute networks subnets describe run-egress-subnet \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

# Check logs (without printing secrets)
gcloud run services logs read orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --limit=100
~~~

Beyond the CLI, inspect **Cloud Run request/container logs, Cloud SQL Insights/connection metrics, Cloud Monitoring, VPC Flow Logs, and Firewall Rules Logging** when enabled. VPC Flow Logs use sampling/aggregation and do not replace real application testing.

### 12.2. Diagnostic Table

| Symptom | Likely failing layer | Verification steps |
| --- | --- | --- |
| Cloud Run revision not Ready | Image not listening on `PORT`, startup/crash, or bad env | Container logs, container contract, health checks |
| `connection timed out` to private IP:5432 | VPC egress, subnet/region, firewall, PSC/PSA, DNS | Verify routes and real private IP; test from actual source |
| `connection refused` | No listener, wrong IP/port, DB failing over | Cloud SQL state, port, and logs |
| Java Connector reports 403 | `roles/cloudsql.client`, Cloud SQL Admin API, service identity | IAM on SQL project, Admin API across relevant projects |
| `password authentication failed` | Wrong PostgreSQL username/password, DB role, or secret version | DB auth, Secret Manager reference, rotation |
| `permission denied for relation` | Missing PostgreSQL table/schema privilege | DB `GRANT`, migrations; do not inflate Google Cloud IAM |
| `No route to host` or DNS NXDOMAIN | Misconfigured route/peering/DNS/PSC endpoint | DNS records, VPC peering, subnet, firewall |
| SQL public IP disabled and app stops working | Connector/proxy still targeting `PUBLIC`, `PRIVATE` not configured | `ipTypes=PRIVATE`, VPC routing, private IP |
| Private Cloud Run callee returns 401 | Missing/wrong-audience/expired ID token | Credential library, `aud`, bearer header |
| Callee returns 403 | `run.invoker`, internal ingress rejecting path, org policy | Network classification + IAM |
| DB `too many connections` | Cloud Run scale × pool size exceeds DB budget | Instance counts, pool configs, rollout overlap |
| Pool holds stale connections after idle | DB closed idle connection, background refresh throttled | Connection validation, lazy refresh, billing mode |
| PSC endpoint access fails | DNS/consumer endpoint/service attachment/acceptance or route | PSC configuration and allowed consumers |
| Setting `all-traffic` breaks Internet access | Missing Cloud NAT/proxy or blocked by egress policy | Default route, NAT, firewalls, DNS |
| Service A calling internal Service B blocked | Request to `run.app` did not traverse VPC as internal | VPC `all-traffic` + PGA, PSC/ILB, or proper DNS |
| Secret update has no effect on running instances | Env secret resolved only at startup | Deploy new revision / rotation plan |

### 12.3. Root-Cause Workflow

~~~mermaid
flowchart TD
    ERR["Error calling Cloud SQL / private service"] --> DEST{"What type of target?"}
    DEST -->|"Cloud SQL private IP"| ROUTE["Check VPC, IP/PSA/PSC, DNS, port 5432"]
    DEST -->|"Private Cloud Run"| IN["Check internal ingress + VPC route path"]
    DEST -->|"VM/cache/private LB"| NET["Check listener, firewall, DNS, and routes"]
    ROUTE --> AUTH{"TCP to target succeeds?"}
    AUTH -->|"No"| RNET["Fix network; do not change DB password/IAM yet"]
    AUTH -->|"Yes"| DB["Check Connector IAM, TLS, DB auth, and SQL grants"]
    IN --> ID["Check ID token audience and run.invoker"]
    NET --> APP["Check app auth/TLS/health"]
    DB --> MET["Check pools, timeouts, autoscaling, and logs"]
    ID --> MET
    APP --> MET
    RNET --> MET
~~~

**Separate three layers when reading logs:** *network reachability → authentication → application/SQL permissions*. Avoid "enabling `all-traffic` + Editor + public DB IP," which hides root causes and introduces new risks.

## 13. Guided Lab

**Objective:** Connect a Cloud Run Java service with a valid image to a Cloud SQL PostgreSQL private IP, protect secrets, and size the connection budget. You do not need to modify production; the lab can be completed as a design and Q&A walkthrough if no sandbox is available.

### 13.1. Preflight

1. Verify project/region, `orders-db` **already has a private IP**, PSA/PSC is configured, and database `orders`/user `orders_app` exist.
2. Verify VPC/subnet matches Cloud Run's region, has adequate IPs, and reaches private Cloud SQL.
3. Create or verify the runtime service account holds Cloud SQL Client IAM (for Java Connector) and Secret Manager Secret Accessor on the exact secret.
4. Ensure the Java image runs on Cloud Run, reads env/secrets, and uses JDBC Socket Factory `ipTypes=PRIVATE`—**do not** rely solely on an echo/hello container.
5. Confirm quotas, billing, logs, database backups, rollback plan, and approved lab window.

### 13.2. Deploy and Test Connectivity

1. Deploy with Direct VPC egress `private-ranges-only`, internal ingress, and authentication required.
2. Bind non-sensitive variables and reference the DB password from Secret Manager.
3. Inspect Cloud Run revision logs. Use an **authorized caller inside the VPC** to test the DB `SELECT 1` endpoint and verify HTTP 200 when the DB is healthy.
4. Intentionally alter the **target DNS config in an isolated test environment** (never edit production subnets) to distinguish DNS/timeout errors from auth errors.
5. Test with a DB user lacking table privileges (never a superuser) to see how PostgreSQL errors differ from IAM 403s.
6. Restore lab settings; verify latency, SQL connections, logs, and zero secret leakage.

**Never shut down Cloud SQL, drop tables, or break production private networks** to test fault injection.

### 13.3. Internal Cloud Run → Cloud Run Test

1. Create `payments-internal` in the lab project with `ingress=internal` and authentication required.
2. Grant `roles/run.invoker` on the callee to the caller's exact runtime service account.
3. Set up the caller path via **VPC `all-traffic` + PGA**, or a supported **PSC/internal LB**.
4. Send a Google-signed **ID token** with `aud` set to the callee URL; confirm success.
5. Remove Invoker IAM from **one test caller** and demonstrate a 403 (never alter production permissions).
6. Keep ingress internal; never open anonymous invocation just to bypass errors.

### 13.4. Evidence to Submit

| Item | Evidence |
| --- | --- |
| Direct VPC egress | Cloud Run revision networking shows VPC/subnet/egress |
| SQL private connectivity | Cloud SQL private IP + confirmed route/PSA/PSC |
| IAM/runtime identity | Runtime SA has only needed roles, not Editor |
| DB authentication | Dedicated user with minimal privileges |
| Secret | Service references Secret Manager version, no plaintext |
| Test query | Safe output of `SELECT 1`, no logged passwords |
| Pool budget | `Max instances × maximumPoolSize` and DB headroom |
| Private service | ID token/Invoker IAM and permitted network path |
| Observability | Logs/metrics for latency, DB connections, and fault-test errors |
| Rollback | Previous revision remains available; config/data reconciled |

## 14. Case Study: Enterprise Orders API

An enterprise runs an ordering API with the following architecture:

- **Cloud Run `orders-api`** handles authenticated requests with controlled ingress.
- **Cloud SQL PostgreSQL** stores orders with private IP, HA, and backups.
- **Redis-compatible cache** on a private endpoint.
- **Cloud Run `payments-internal`** accepts requests only from internal sources and authorized service accounts.
- **Cloud Logging/Monitoring** tracks response latency, SQL errors, and saturation.

**Chosen design:** Direct VPC egress on `orders-api` to reach Cloud SQL and cache; Java Connector `PRIVATE`; DB password in Secret Manager; pool of 5 connections/container with max instances bounded by DB budget. Calls to payments use a path Cloud Run recognizes as internal plus ID tokens, never anonymous HTTP.

**Simulated incident:** On Black Friday, traffic spikes 8×. Autoscaling spins up many Cloud Run instances; the DB reports `too many connections`. Adding CPU to Cloud Run **does not solve** the DB connection budget. Operations should inspect DB connections, reduce pool size or set sensible max instances/concurrency, optimize queries, and introduce caching/queues where needed. During rollouts, account for **both old and new instances** to avoid connection spikes.

**Success criteria:** API meets SLOs, zero unexpected SQL auth errors, private endpoints stay private, IAM stays least-privilege, and recovery/rollback remain intact.

## 15. Review Questions and Short Answers

1. **If a Cloud Run service sets `ingress=internal`, can it automatically connect to Cloud SQL private IP?** No; ingress and egress are independent.
2. **How does Direct VPC egress differ from a connector?** Direct needs no connector VMs; both provide outbound access into a VPC.
3. **How does `private-ranges-only` differ from `all-traffic`?** Routing only private/internal ranges vs. routing all outbound traffic through the VPC.
4. **Does the Cloud SQL Java Connector create VPC routes automatically?** No; network reachability must already exist.
5. **How do you select private IP when using the Java Connector?** `ipTypes=PRIVATE`, along with required IAM roles/APIs.
6. **Does `roles/cloudsql.client` replace a PostgreSQL password/DB role?** No.
7. **With direct TCP to private IP, is TLS guaranteed by default?** No; configure and verify TLS per policy.
8. **Why does Java not use Cloud Run's Unix socket like Python?** Standard JDBC typically lacks native Unix socket support, so the Java Connector is preferred.
9. **When Cloud Run calls an internal service in the same project, is `run.invoker` alone enough?** No; requests must also traverse a path Cloud Run recognizes as internal.
10. **How does an ID token differ from an access token?** An ID token authenticates callers to Cloud Run; an access token is used for Google APIs.
11. **What should the token audience be when calling Cloud Run?** The service URL or a configured custom audience—not a custom domain by default.
12. **10 instances × pool of 5 creates roughly how many max connections for one revision?** Roughly 50, excluding other revisions and remaining DB connections.
13. **Does Cloud Run's built-in Cloud SQL limit of 100 connections per instance apply identically to every method?** No; docs note exceptions for language connectors, sidecar proxies, and direct IP.
14. **On a 403 error, should you open the firewall to `0.0.0.0/0`?** No; check IAM/Invoker/SQL connector permissions first.
15. **Does rolling back a Cloud Run revision roll back secrets or database schemas?** No; a separate plan is needed.

## 16. Production Checklist and Further Reading

- [ ] Identify whether Cloud Run is **caller or callee**; configure ingress and egress independently.
- [ ] Explicitly pick Cloud SQL **public/proxy** or **private IP via VPC/PSC**; never mix mechanisms.
- [ ] Cloud Run and subnet match regions, have sufficient IPs, and routes/firewalls/DNS are verified from the real source.
- [ ] Runtime SA has least-privilege IAM: Cloud SQL Client for connectors/proxies; Invoker on callees when invoking services.
- [ ] DB users/roles, TLS, secrets, and Secret Manager rotation are managed separately.
- [ ] Java Connector sets `ipTypes=PRIVATE` and serverless-appropriate refresh strategy.
- [ ] Connection pool, Cloud Run max instances, and concurrency are sized to the DB budget, including rollout overlap.
- [ ] Cloud SQL HA/backups, idempotency, retry/backoff, and failover testing are planned.
- [ ] Private ingress is never opened publicly just for testing; smoke tests run from authorized sources.
- [ ] Logs/metrics/alerts cover HTTP errors, SQL connections, VPC failures, and secret/Invoker denies.
- [ ] Change approvals, canary releases, revision rollbacks, and migration compatibility are in place.
- [ ] Costs for Cloud Run, Cloud SQL, NAT, egress, connectors, and Logging are monitored.

**Official Google Cloud documentation:**

- [Cloud SQL PostgreSQL: Connect from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run) — public IP, private IP, Java connector, Unix sockets, IAM, and pooling.
- [Cloud SQL Java Connector](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory) — JDBC Socket Factory, `ipTypes`, and lazy refresh.
- [Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc) — network/subnet/egress configuration.
- [VPC connector](https://docs.cloud.google.com/run/docs/configuring/vpc-connectors) — alternative connector mode.
- [Compare Direct VPC egress and connectors](https://docs.cloud.google.com/run/docs/configuring/connecting-vpc) — pros/cons and billing.
- [Cloud Run private networking](https://docs.cloud.google.com/run/docs/securing/private-networking) — internal paths via VPC, ILB, PSC, and PGA.
- [Cloud Run ingress](https://docs.cloud.google.com/run/docs/securing/ingress) — internal, load balancing, and all.
- [Cloud Run service-to-service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service) — Invoker IAM, ID tokens, audiences.
- [Cloud Run Secret Manager integration](https://docs.cloud.google.com/run/docs/configuring/services/secrets) — environment variables, secret volumes, versions.
- [Cloud SQL PostgreSQL: Connection management](https://docs.cloud.google.com/sql/docs/postgres/manage-connections) — pooling, retries, timeouts.
- [Cloud SQL PostgreSQL: Quotas](https://docs.cloud.google.com/sql/docs/postgres/quotas) — connection limits and built-in proxy.
- [Cloud SQL private IP](https://docs.cloud.google.com/sql/docs/postgres/configure-private-ip) — PSA, addressing, and network prerequisites.
- [Cloud SQL Private Service Connect](https://docs.cloud.google.com/sql/docs/postgres/about-private-service-connect) — private endpoints and DNS requirements.
- [Cloud Run pricing](https://cloud.google.com/run/pricing), [Cloud SQL pricing](https://cloud.google.com/sql/pricing) — cost estimation.

**Key takeaway:** Cloud Run connects reliably to private services only when **the network path is valid, the identity has the right permissions, the application uses the right protocol/authentication**, and connection counts stay within backend capacity. **VPC egress, Cloud SQL Client IAM, and PostgreSQL permissions are three distinct layers**; verify each layer before scaling up traffic.

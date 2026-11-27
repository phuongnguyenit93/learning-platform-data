# Integration Runtime and Connecting On-Premises Data Sources

An enterprise stores orders in SQL Server inside its private data center and CSV files on a Windows file share, and wants to transfer data nightly to Azure Data Lake Storage Gen2 (ADLS Gen2) for analytics. The sources have no public IP; security policy prohibits exposing SQL Server to the Internet. The team deploys **Azure Data Factory (ADF)** or **Azure Synapse Analytics pipelines**, yet pipelines can fail to connect even while Azure resources remain healthy.

**Integration Runtime (IR)** is the compute and connectivity infrastructure layer that ADF/Synapse uses to move data and run supported integration activities. For data sources inside private networks, the common solution is **Self-hosted Integration Runtime (SHIR)**: a service installed on a Windows host with access to internal sources that connects outbound to Azure to receive jobs, read source data, and send it to the destination.

This lesson belongs to the **Data Platforms and Analytics** chapter in the **CLOUD_PROVIDERS_AZURE** module. It connects subscriptions/resource groups, Microsoft Entra ID, VNets, Private Endpoints, SQL Server, Azure Storage, pipelines, monitoring, backups, and cost control when designing an Azure data platform.

> **Scope:** this lesson focuses on Azure Data Factory and Synapse pipelines, especially **Copy Activity**. IR capabilities per connector/activity, network endpoints, node limits, authentication permissions, Azure-SSIS IR, and pricing vary by service, region, and version. Examples use placeholders for illustration; before running in production, verify the support matrix, network prerequisites, and exact tool syntax.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **Azure IR**, **Self-hosted IR**, and **Azure-SSIS IR**, and know when to choose each.
2. Diagram the **control plane** and **data movement path** across on-premises systems, SHIR hosts, and Azure sinks.
3. Size Windows hosts and configure DNS, proxies, firewalls, VPN/ExpressRoute, and private endpoints properly.
4. Install, register, protect registration keys for, and operate SHIR under least-privilege principles.
5. Configure linked services/datasets using `connectVia` and run a Copy Activity from SQL Server → ADLS Gen2.
6. Design multi-node SHIR topologies for high availability and tune concurrency without overloading source systems.
7. Distinguish **network**, **TLS**, **authentication**, **authorization**, **driver**, and **query** failures.
8. Design incremental loads with watermarks/CDC, staging, and idempotent retries.
9. Configure metrics, logs, alerts, runbooks, and evaluate cost and data correctness.
10. Implement a lab connecting on-premises data to Azure and verify outcomes via row counts, checksums, and timings.

## 2. Where Integration Runtime Fits in a Pipeline

A pipeline is an orchestration blueprint: which activities run, in what order, and when to retry or branch on failure. **Integration Runtime** provides the execution and connectivity environment for the activities it supports.

~~~mermaid
flowchart LR
  T["Trigger / Schedule"] --> P["ADF / Synapse Pipeline"]
  P -.-> IR["Integration Runtime"]
  SQL["SQL Server on-prem"] --> SH["Self-hosted IR Windows host"]
  IR -.-> SH
  SH -->|Transfer data| DL["ADLS Gen2 landing zone"]
  DL --> X["Analytics / transformation"]
  M["Azure Monitor"] -.-> P
  M -.-> SH
~~~

Distinctions:

| Component | Function | Do Not Confuse With |
|---|---|---|
| Pipeline | Orchestrates activities and dependencies | A data-reading server |
| Trigger | Fires on schedule, events, or manually | A tool guaranteeing exactly-once |
| Activity | A single step such as Copy, Lookup, stored procedure | Data or a fixed execution server |
| Linked service | Endpoint, authentication, runtime reference | A table or file |
| Dataset | Describes table/file/path and structure | Network path or separate credentials |
| Integration Runtime | Execution and connectivity environment | SQL Server, data warehouse |
| Azure Monitor | Status, errors, metrics | Automated data-content validation system |

**Core takeaway:** pipeline orchestration runs in the Azure service, while **Copy Activity data movement can execute via a SHIR node** inside a private network. Not every payload byte flows through an ADF orchestration server.

## 3. The Three Types of Integration Runtime

| IR Type | Where It Runs | Suitable Workloads | Notes |
|---|---|---|---|
| **Azure Integration Runtime** | Azure-managed compute | Cloud-to-cloud Copy and supported transformation/dispatch activities | Network reachability, region, Managed VNet if supported |
| **Self-hosted Integration Runtime** | On-prem Windows host or Azure VM with route to sources | Copy from private-network SQL/Oracle/SMB and supported activities | Customer manages host, connector prerequisites, egress, HA |
| **Azure-SSIS Integration Runtime** | Azure compute for SSIS package execution | Lift-and-shift SQL Server Integration Services packages | Not a drop-in replacement for SHIR across all Copy Activities |

**Azure IR:** suitable when both source and sink are reachable from Azure-managed compute. Azure IR in a Managed VNet can connect via managed private endpoints **to supported Azure services**; it does not turn Azure IR into a machine with arbitrary access across an entire corporate LAN.

**SHIR:** installed on a Windows machine with network routes to on-premises databases/file servers. It proactively establishes outbound connections to Azure control endpoints per product design and opens data connections to sources/sinks.

**Azure-SSIS IR:** runs supported SSIS packages. Packages may require specific dependencies, drivers, and networking; specialized integrations exist between SSIS and SHIR in supported setups, but **the two runtimes are not synonymous**.

### Do Not Treat Mapping Data Flow Like Copy Activity

ADF Mapping Data Flows run on Azure-managed compute / Azure IR; **they do not run the Spark/data-flow engine directly on a SHIR host** merely because a data source connects via SHIR. When designing workflows, check which IR each activity supports and use intermediate staging when necessary.

## 4. Choosing an IR Based on the Real Network Path

| Source | Destination | First Option to Evaluate |
|---|---|---|
| Accessible Azure Blob | Accessible ADLS Gen2 | Azure IR |
| SQL Server on LAN | ADLS Gen2 | **SHIR** |
| Internal Windows file share | Azure Blob | **SHIR** |
| Private-network Oracle | Azure SQL Database | **SHIR** + compatible driver/connector |
| Azure SQL/Storage via managed private endpoints | Azure destinations | Azure IR in Managed VNet, if activity supports it |
| Cloud data | SQL Server on LAN | **SHIR** for writing to internal SQL |
| Legacy SSIS package | Data lake/Azure SQL | **Azure-SSIS IR** after compatibility assessment |
| Two disconnected datacenters | Cloud sink | Design networking/SHIR per hop; staging may be needed |

Decision questions:

1. Can the **machine running Copy Activity** reach the source via DNS/routing/firewall?
2. Can it reach the sink via appropriate networking and auth?
3. Does that connector/activity support this IR and its required drivers?
4. Does the data path satisfy privacy, residency, and cost requirements?
5. If one node fails, can another node meet the same source/sink reachability and SLA?

A single Copy Activity whose two linked services use **two separate, non-communicating SHIRs** may not execute directly as expected. Verify IR selection and connector support; if needed, split the flow via secure staging with batch checkpoints.

## 5. Control Plane and Data Plane Diagram

~~~mermaid
flowchart TD
  A["ADF / Synapse control plane"] -.->|Dispatch / status| H["SHIR Windows host"]
  H -.->|Outbound service channel| A
  H -->|SQL TCP in LAN| S["SQL Server ERP"]
  H -->|HTTPS / private route| L["ADLS Gen2"]
  S -.->|No inbound Internet required| H
  L --> O["Data processing / BI"]
~~~

**Control plane:** ADF holds definitions/triggers/pipeline state, dispatches jobs, and receives status from the runtime. **Data plane:** the SHIR host streams data directly from SQL to ADLS. Data traffic does not inherently route through a public SQL endpoint.

Security advantage: no need to create public inbound NAT rules for SQL Server. However, **the SHIR host still needs outbound service connectivity and network routes to both source and sink**. Not all traffic uses a single port or a single endpoint.

### Three Independent Checks

- **SHIR ↔ Azure control endpoints:** is the runtime Online and able to receive jobs?
- **SHIR → on-prem SQL:** do DNS, port, TLS, login, and SELECT work?
- **SHIR → ADLS sink:** do routing, TLS, Azure identity, and storage RBAC/ACLs allow uploads?

Seeing IR marked **Online** proves only part of the control path; **it does not guarantee** SQL queries or data lake uploads will succeed.

## 6. Choosing Where to Place SHIR

### Option A — SHIR on an On-Premises Machine

Fits when SQL Server and SMB shares reside on the same LAN, avoiding sending raw source connections across a WAN before reading. The node connects outbound to Azure service endpoints and uploads data to the Azure sink.

Operational responsibilities: Windows, proxies, corporate firewalls, EDR, domain credentials, local disk/temp space, and Internet/VPN link stability.

### Option B — SHIR on an Azure VM

Fits when **VPN/ExpressRoute** already connects on-premises sources to a VNet and the team prefers managing Windows hosts inside Azure.

Without VPN/ExpressRoute/routes, an Azure VM **cannot automatically see on-premises networks**. You also need proper VNets/subnets, private DNS, and NSGs/firewalls.

### Option C — Multiple Nodes in One Logical SHIR

Fits production workloads needing high availability or parallel processing capacity. Every node must reach the **same data endpoints** and carry identical supported drivers and credentials.

Never install SHIR on an end-user laptop that can sleep or shut down arbitrarily. For production, use managed servers with patch windows, resource monitoring, configuration backups, and clear ownership.

## 7. Windows Host Requirements and Sizing

Minimum specifications published by Microsoft depend on IR version. Before installing:

- Confirm a supported Windows OS and architecture.
- Obtain local administrator rights to install and register the agent per procedure.
- Allocate adequate CPU/RAM/disk for concurrency, encryption, compression, and logging.
- Ensure stable networking to SQL/file shares and cloud endpoints.
- Ensure EDR/antivirus does not block the service executable or working directories.
- Ensure proper clock/time synchronization and certificate trust stores.
- Install required dedicated drivers at the right version and bitness/architecture for each connector.
- Avoid running heavy data copy workloads on the same machine as a critical database engine unless tested.
- Maintain an inventory of OS, runtime version, drivers, hostname, subnet, and owner.

### CPU, RAM, and Network Are Interdependent

A host with many vCPUs will still be slow if the SQL query reads slowly or the WAN link is 200 Mbps. Conversely, a 1 Gbps link does not guarantee 1 Gbps effective throughput if VPN overhead, TLS, packet loss, sink throttling, or SQL blocking bottlenecks the flow.

### Capacity Is a Shared Budget

If 20 Copy Activities run simultaneously while SHIR only has enough memory for 4 large jobs, raising activity concurrency can **lower** total throughput. Enforce limits based on source type, time window, job size, and SLOs.

## 8. Firewalls, DNS, Proxies, and Ports

Build a **network connectivity matrix** before requesting firewall changes:

| From | To | Typical Protocol | Purpose |
|---|---|---|---|
| SHIR node | SQL Server | TCP to instance port, e.g., 1433 if configured | Reading ERP |
| SHIR node | Windows file server | SMB TCP 445 if using File System connector | Reading UNC shares |
| SHIR node | Microsoft control/relay endpoints | Outbound HTTPS and supported endpoints/ports | Registration, jobs, telemetry |
| SHIR node | ADLS/Blob | HTTPS 443, or private route to endpoint | Uploads |
| SHIR node | Internal DNS/AD | Ports per domain/network policy | Name resolution and auth |
| Admin workstation | SHIR host | RDP/VPN/Bastion per policy | Maintenance |

**TCP 443** is critical for Azure service connectivity, though requirements can also include Azure Relay endpoints/protocols and runtime-version specifics. Never claim **opening port 443 alone guarantees every mode works**. Obtain the current FQDN/port allowlist for the exact service; never open the entire Internet or inbound public SQL as a "quick test."

### SQL Server Ports

A default instance may use TCP 1433 when configured, whereas a **named instance** may use dynamic ports. Confirm the exact port with the DBA, configure listeners/FQDNs where appropriate, and avoid opening unnecessarily broad port ranges.

### Proxies

The SHIR Windows service may not inherit the proxy settings of an interactive RDP user session. Inspect proxy settings **at the service/process level** along with bypass rules for private endpoints. A proxy requiring interactive auth or breaking TLS inspection can leave SHIR Offline or cause handshake errors.

## 9. Testing Connectivity from the SHIR Host

PowerShell examples on a **Windows SHIR lab host**:

~~~powershell
# Internal FQDN and actual port
Resolve-DnsName sql01.corp.example
Test-NetConnection -ComputerName sql01.corp.example -Port 1433

# File share when using SMB
Test-NetConnection -ComputerName fileserver.corp.example -Port 445
Test-Path '\\fileserver.corp.example\exports\sales'

# Cloud storage endpoint; if using a Private Endpoint, verify the private IP
Resolve-DnsName datalakeaccount.dfs.core.windows.net
Test-NetConnection -ComputerName datalakeaccount.dfs.core.windows.net -Port 443
~~~

**Limitations of these checks:**

- A valid `Resolve-DnsName` does not prove routing or firewall allowance.
- `TcpTestSucceeded: True` does not prove SQL logins, certificates, or SQL permissions.
- `Test-Path` run under an RDP admin session does not prove the service account or linked service can read the UNC path.
- An HTTPS connection to ADLS succeeding does not prove Storage Blob Data Contributor rights or ADLS ACLs.
- If the Azure sink uses a Private Endpoint, the hostname must resolve to the private IP **and that private IP must be reachable** over VPN/ExpressRoute.
- Verify egress to control/relay endpoints against the current product documentation; never invent endpoint names.

### Test with the Real Identity

If the linked service uses Windows authentication or a file share requires an AD account, test under that exact authentication mechanism. Never use a full-access domain admin account to declare "connectivity works" when production pipelines will run under a least-privilege account.

## 10. Steps to Create a Self-Hosted Integration Runtime

Portal workflow (label names can vary by ADF/Synapse version):

1. Confirm subscription/resource group and Data Factory or Synapse workspace.
2. Navigate to **Manage → Integration runtimes** (or equivalent).
3. Click **New** and choose **Self-hosted**.
4. Assign a stable name, e.g., `IR_Corp_ERP_Prod`, recording owner and network scope.
5. On the Windows host, download the **SHIR installer from the official source** linked by Portal/Docs.
6. Verify publisher/signature, OS support, version, and security approval.
7. Install the application using authorized privileges.
8. In **Integration Runtime Configuration Manager**, register the runtime using the corresponding **authentication/registration key**.
9. Confirm the node shows **Online/Connected** on a supported version.
10. Inspect Windows service status, outbound connectivity, and Windows Event Logs.
11. Create the SQL Server linked service referencing that IR.
12. Run Test connection, then execute a small lab-data Copy Activity.
13. Establish alerts, HA, and a maintenance/rotation runbook prior to production.

### A Registration Key Is Not a SQL Password

A registration key authorizes a node to join a logical SHIR resource. It **does not** grant SQL `SELECT`, file-share read, or ADLS write permissions. Treat keys as secrets; never commit them to repos, pipeline parameters, public tickets, or screenshots.

If key compromise is suspected, rotate keys using the supported procedure. Multiple keys exist to allow seamless rotation—avoid regenerating both keys simultaneously before assessing the impact on currently registered nodes.

## 11. Linked Services and `connectVia`

A **Linked service** stores endpoints, authentication/config, and the Integration Runtime reference. For on-premises SQL Server, the linked service must point to the right SHIR.

**Structural illustration** of an ADF linked service; current connector versions may require different auth/connection fields:

~~~json
{
  "name": "LS_OnPremSql",
  "properties": {
    "type": "SqlServer",
    "typeProperties": {
      "connectionString": "Server=sql01.corp.example;Database=ERP;Encrypt=True;TrustServerCertificate=False",
      "password": {
        "type": "AzureKeyVaultSecret",
        "store": {
          "referenceName": "LS_KeyVault",
          "type": "LinkedServiceReference"
        },
        "secretName": "erp-etl-password"
      }
    },
    "connectVia": {
      "referenceName": "IR_Corp_ERP_Prod",
      "type": "IntegrationRuntimeReference"
    }
  }
}
~~~

**Do not treat the JSON above as a ready-to-deploy configuration**: SQL Server connector versions may require `userName`, `authenticationType`, or a different connection string structure. Author the linked service via UI or current schema and inspect the generated JSON. The key point is `connectVia.referenceName` pointing to SHIR.

### Datasets Only Describe Data Objects

Example dataset in a compatible connector/schema:

~~~json
{
  "name": "DS_ERP_Orders",
  "properties": {
    "type": "SqlServerTable",
    "linkedServiceName": {
      "referenceName": "LS_OnPremSql",
      "type": "LinkedServiceReference"
    },
    "typeProperties": {
      "schema": "dbo",
      "table": "Orders"
    }
  }
}
~~~

Datasets and linked services **do not copy data by themselves**. A pipeline still requires a Copy Activity (or equivalent), sink dataset, mapping, and schedule.

### Where Does Test Connection Execute?

Linked service Test connection executes through the configured connection/IR rather than from your laptop SQL client. Inspect error messages in Monitor/linked service UI in the context of the actual node and identity.

## 12. Connecting to an On-Premises SQL Server Source

A solid source setup includes:

- Stable FQDN (or AG listener) and exact port.
- Correct database name, connector version, and TLS settings.
- Least-privilege credentials: SQL login with `SELECT` only on ETL tables/views.
- Indexes/filters to avoid accidental full scans on massive tables.
- Firewall allowance restricted to exact SHIR hosts/subnets.
- Appropriate query timeouts and ETL schedules that do not disrupt OLTP traffic.
- Documented timestamp timezones and precision.
- DBA owner sign-off on extracted schemas.

### SQL Authentication

**SQL authentication:** use a read-only login with passwords managed in Key Vault/credential stores per connector support; never embed plaintext passwords in JSON.

**Windows/AD authentication:** requires matching domain, service identity/impersonation, and connector support. Never assume that because a SHIR host is domain-joined, the pipeline automatically runs as the DBA account currently logged in via RDP.

**Microsoft Entra identity:** some SQL Server versions/configurations may support Entra auth, yet never assume every on-premises SQL Server accepts ADF's managed identity by default.

### TLS

Ensure the host trusts the CA chain, the hostname matches the certificate's Subject Alternative Name, and never enable `TrustServerCertificate=True` just to bypass a production error. With an AG listener, certificate names must match the endpoint clients connect to.

## 13. Windows File Shares/SMB and Legacy Sources

Example UNC path:

~~~text
\\fileserver.corp.example\exports\sales\2026\11\
~~~

When using the File System connector with SHIR:

1. Verify hostname/port 445 and allowed SMB versions per policy.
2. Verify both Share permissions and NTFS ACLs for the identity used by the linked service.
3. Use a **UNC path** instead of a user-session mapped drive like `Z:`; Windows services generally lack interactive drive mappings.
4. Check file encodings, delimiters, quotes/escapes, file locks, and schemas.
5. Never copy files currently being written by a producer without a handoff marker or atomic rename.
6. Never log full paths or file contents containing PII in violation of policy.

### Oracle, PostgreSQL, or SAP

SHIR provides the network bridge, yet individual connectors may require specific drivers, client libraries, ports, certificates, or licenses. SHIR showing Online **does not mean** Oracle/SAP connectors will work out of the box. Verify the support matrix, prerequisites, and source-specific permissions.

## 14. Write Path to ADLS Gen2 or Blob

When SHIR reads SQL Server and uploads to ADLS Gen2, the host needs both network routes and write permissions on Storage.

If using a **Private Endpoint**:

1. Private Endpoints are created for the right Storage subresources (e.g., `dfs` and others as required).
2. DNS from SHIR resolves the Storage FQDN to the right private IP.
3. VPN/ExpressRoute or an approved route connects on-premises ↔ Azure VNet.
4. Firewalls/NSGs permit HTTPS to the endpoint.
5. Credentials/managed identity/service principal or another connector-supported auth method is configured.
6. Azure Storage RBAC and ADLS ACLs (when using hierarchical namespace) cover the target filesystem/path.

**Never confuse control-plane Azure Storage Contributor with data-plane write rights.** Permission to create storage accounts does not grant permission to write blobs or files.

If using a public endpoint with a policy-approved firewall allowlist, evaluate outbound NAT IPs, TLS, security posture, and IP-change risk. Never switch on `Allow access from all networks` arbitrarily just to make a pipeline run.

## 15. Copy Activity: Moving Real Data Through SHIR

Example workflow:

~~~text
Pipeline: PL_ERP_Orders_To_Lake
  Source linked service: LS_OnPremSql, connectVia=IR_Corp_ERP_Prod
  Source dataset:        DS_ERP_Orders
  Sink linked service:   LS_AdlsLanding
  Sink dataset:          DS_OrdersLanding
  Activity:              Copy_Orders
  Trigger:               01:00 nightly per approved schedule
~~~

Steps:

1. Select the SQL Server linked service routed through SHIR.
2. Select the table or filtered query, projecting only required columns.
3. Select the ADLS sink and CSV/Parquet format per activity capabilities.
4. Configure source-to-target mappings; verify decimal and datetime types.
5. Tune partitioning/parallelism within connector and source limits.
6. Configure activity timeouts, bounded retries, and failure handling.
7. Debug with a small row subset, avoiding real PII unless authorized.
8. Inspect output rows/bytes, duration, and throughput.
9. Validate data quality, keys, and row counts post-copy.
10. Publish the pipeline and enable the trigger after approval.

### Illustrative Time-Windowed Extraction SQL

~~~sql
SELECT
    OrderId,
    CustomerRef,
    CreatedUtc,
    ModifiedUtc,
    AmountMinor,
    CurrencyCode
FROM dbo.Orders
WHERE ModifiedUtc >= @WindowStart
  AND ModifiedUtc < @WindowEnd;
~~~

`@WindowStart` and `@WindowEnd` are **SQL parameters** that must be bound properly by the connector/pipeline; they are not automatically substituted from arbitrary ADF expression syntax. Never concatenate raw user input into SQL queries.

## 16. Full Load vs. Incremental Load

**Full load** reads the entire table, suited to initial loads or small tables. **Incremental load** extracts only new/changed data, reducing SQL load, network usage, storage, and cost.

Example control record:

~~~json
{
  "source": "ERP",
  "entity": "dbo.Orders",
  "lastCommittedWatermarkUtc": "2026-11-19T00:00:00Z",
  "lastSuccessfulBatchId": "erp-orders-20261119"
}
~~~

A new batch:

1. Read the committed watermark.
2. Determine a safe **upper bound** per source semantics.
3. Query the `[start, end)` interval with clear boundaries.
4. Write into a **staging folder/batchId**.
5. Validate row counts, schemas, checksums, and keys.
6. Publish outputs to downstream consumers using mechanisms supported by the data format.
7. **Only after publishing succeeds**, update the watermark.

### Why Not Update the Watermark First?

If the pipeline records a new watermark before Copy completes and Copy fails, the next run skips unpersisted records. Conversely, retrying the same window can duplicate records if the sink only appends unconditionally.

### Late Arrivals and Deletes

`ModifiedUtc` may miss hard deletes, late-committed transactions, or suffer from coarse timestamp precision. Consider an **overlap window + upsert/dedup** or SQL Server **CDC/Change Tracking** when appropriate and supported by DBAs. CDC carries its own retention, permissions, and jobs; SHIR does not enable CDC by itself.

## 17. Idempotency and Staging When Copy Activity Retries

A large copy can write 70% of data and then time out. If a retry writes a new file or appends unchecked, the data lake ends up with duplicates or partial outputs.

~~~mermaid
flowchart LR
  SRC["SQL ERP"] --> COPY["Copy batch B"]
  COPY --> ST["ADLS staging/runId"]
  ST --> V{"Validate count + schema + keys"}
  V -->|PASS| PUB["Publish partition / table commit"]
  V -->|FAIL| Q["Quarantine + alert"]
  PUB --> WM["Commit watermark B"]
~~~

Techniques:

- Use a **stable batchId and data window**.
- Write outputs to a staging path isolated from production views.
- Validate before publishing.
- Use overwrite/merge/upsert matching chosen semantics and tooling.
- Prevent downstream consumers from reading incomplete files lacking a marker or table commit.
- When using transactional lake table formats, rely on supported transaction protocols; **do not assume multi-file ADLS renames are atomic transactions**.
- Retrying the same batch must not alter business outcomes.
- Maintain runbooks for reprocessing and handling bad records.

**Technical "Copy Succeeded" status does not guarantee business data accuracy.** Add data quality tests.

## 18. Source Consistency and Avoiding ERP Bottlenecks

When copying from active OLTP tables undergoing writes:

- Multiple partitions/queries can read inconsistent point-in-time versions.
- Full scans can cause locking or I/O contention.
- Isolation levels like Snapshot/RCSI have trade-offs requiring DBA evaluation; **never enable them arbitrarily on production**.
- Using `NOLOCK` to "avoid blocking" risks dirty, missing, or duplicate reads—unsuitable for financial data requiring accuracy.
- Concurrent Copy Activities can spike SQL CPU and transaction log I/O.
- Backup/maintenance jobs and ETL can contend for resources.

### What to Measure?

| Category | Example Metrics |
|---|---|
| Source SQL | Query duration, CPU, waits, read IOPS, active sessions, blocking |
| SHIR | CPU/RAM, active copy jobs, node availability, temp disk |
| Network | Throughput, packet loss, VPN/ExpressRoute utilization |
| Sink | Write latency, throttling, upload failures |
| Pipeline | Rows/s, MiB/s, duration, queue time, retries |
| Business | Data freshness, duplicate rate, validation failures |

Increase parallel copies only when **source, network, SHIR, and sink all have headroom**.

## 19. Multiple Nodes: High Availability and Scale-Out

A single SHIR node can go down during Windows updates, VM reboots, or proxy failures. **Multiple nodes can be registered to the same logical SHIR** within product limits to improve HA and capacity.

~~~mermaid
flowchart TD
  ADF["ADF logical SHIR"] --> N1["SHIR node 1"]
  ADF --> N2["SHIR node 2"]
  N1 --> SQL["On-prem SQL"]
  N2 --> SQL
  N1 --> LAKE["ADLS"]
  N2 --> LAKE
  MON["Health / versions / concurrency"] -.-> ADF
~~~

### What Real HA Requires

1. Nodes belong to the same logical IR and are validly registered.
2. Every node sees the same SQL/SMB sources, cloud sinks, DNS, and proxies.
3. Driver versions and certificates are identical across nodes.
4. Credentials/service identities work from every node.
5. Nodes sit in distinct failure domains wherever possible.
6. Remaining capacity can carry the workload when one node stops.
7. Node-offline alerts, rolling patching, and failover drills are in place.
8. Never mistake Online state for proof that the data path works.

### Scale-Out Does Not Scale Infinitely Automatically

SHIR is not simply an elastic Azure serverless pool: you manage Windows host capacity and node counts within limits. To increase throughput, test parallel copy carefully; **if the bottleneck is SQL or WAN**, adding nodes will not scale throughput linearly.

## 20. Managed VNet Azure IR Does Not Replace VPN to On-Premises Sources

Azure IR inside a **Managed Virtual Network** can use **Managed Private Endpoints** to supported Azure PaaS destinations. This reaches private resources inside Azure, but **does not provide routing to arbitrary on-premises datacenters**.

Comparison:

| Path | Option to Evaluate |
|---|---|
| Azure IR → supported Azure resource with Managed Private Endpoint | Azure IR Managed VNet |
| On-prem SQL → Azure sink via on-prem SHIR | SHIR + outbound cloud access |
| On-prem SQL → Azure sink private endpoint | SHIR + VPN/ExpressRoute + private DNS/routes |
| SHIR on Azure VM → On-prem SQL | SHIR + VNet + VPN/ExpressRoute + firewall |
| SSIS package reading internal shares | Azure-SSIS IR + network/dependency assessment |

Managed private endpoints may require **approval** from the resource owner. Pending or Rejected states fail connections even though the endpoint appears in the Portal.

## 21. When Is Azure-SSIS IR Used?

If an enterprise runs hundreds of **SQL Server Integration Services** packages, Azure-SSIS IR can be evaluated to execute packages on Azure-managed compute under a fitting model.

Checklist:

- SQL Server/SSIS version compatibility and package deployment model.
- Custom components, drivers, licenses, and secret stores.
- SSISDB/catalog or supported package management model.
- Access to on-prem SQL/SMB over private networking.
- Compute sizing, startup/shutdown, run schedules, and cost.
- Environment configurations, package logging, and failure recovery.

**Do not convert `Execute SSIS package` into `Copy Activity` simply by picking SHIR.** They are distinct workload types. Certain architectures integrate SSIS IR and SHIR in specific ways, so follow official documentation rather than assuming they substitute for one another.

## 22. Authentication, Key Vault, and Least Privilege

There are at least four authentication boundaries:

1. **Data Factory ↔ SHIR:** runtime registration key/identity.
2. **SHIR ↔ on-prem sources:** SQL login, Windows integrated authentication, or connector-supported mechanisms.
3. **SHIR ↔ Azure sink:** managed identity/Entra token, service principal, SAS, or connector-supported auth.
4. **Operator ↔ management resources:** Azure RBAC, Key Vault permissions, pipeline authoring rights.

A Microsoft Entra managed identity **does not automatically** grant `SELECT` on on-premises SQL Server or SMB read rights. Control-plane Contributor does not equal Storage data-plane RBAC.

### Azure Key Vault

- Store database passwords/secrets with lifecycle and rotation policies.
- Reference secrets from linked services per connector support.
- Grant `get` permissions on Key Vault strictly to the required identity scope.
- Key Vault networking/private endpoints must also be reachable along the secret-retrieval path.
- Never embed secrets in pipeline JSON, run outputs, or source control.
- Users authorized to publish pipelines should not automatically gain read access to all production secrets.

### SQL Server

- Create a **read-only** principal scoped to required ETL views/tables.
- Avoid `sysadmin` or `db_owner` for linked services.
- Enable TLS/certificate validation matching the FQDN.
- Audit access and data classification.
- Open source ports strictly to SHIR subnets/hosts.

### ADLS Gen2

- Grant principals write rights strictly on required filesystems/folders.
- Verify **Storage Blob Data** roles and ADLS ACL/execute permissions when hierarchical namespace is enabled.
- Configure retention, encryption, and private networking per compliance.

## 23. Monitoring Runtime and Pipelines

| Layer | Telemetry to Inspect |
|---|---|
| Trigger | On-time firing, disabled state, trigger failures |
| Pipeline | Run ID, status, duration, safely logged parameters |
| Copy Activity | Source/sink, rows/bytes, throughput, elapsed time, retries |
| SHIR | Node online/offline, version, CPU/RAM, concurrency, queued work |
| Windows host | Windows service, Event Logs, proxy/DNS/firewall, disk space |
| SQL source | Query latency, locks, CPU, sessions, resource pressure |
| Storage sink | Upload success/failure, throttling, write latency |
| Data quality | Row counts, schema drift, watermark age, duplicates |
| Security | Auth failures, privilege changes, secret expiry |
| Cost | Activity charges, VM/host, network, storage, Log Analytics |

### Short Failure Runbook

1. Capture Pipeline Run ID / Activity Run ID and UTC timestamp.
2. Identify the runtime type and executing node.
3. If the node is Offline: inspect the Windows service, outbound endpoints, and proxy.
4. If the node is Online: verify source DNS/TCP/auth/TLS.
5. Verify sink DNS/routes/permissions/ACLs.
6. If connectivity succeeds: inspect SQL queries/drivers, memory, parallelism, and timeouts.
7. Reconcile rows/bytes and staging to ensure no partial data was promoted.
8. Fix the root cause, **retry the idempotent batch**, and never advance the watermark before completion.
9. Remeasure duration, business freshness, and source impact.
10. Document root cause and preventive actions.

## 24. Azure CLI: Reading Data Factory/IR Configuration

Bash examples in Azure Cloud Shell or CLI supporting `az datafactory` commands:

~~~bash
az account show \
  --query "{subscription:name,id:id,tenant:tenantId}" \
  --output table

RG="rg-data-lab"
FACTORY="adf-corp-lab"
IR="IR_Corp_ERP_Prod"

az datafactory integration-runtime list \
  --resource-group "$RG" \
  --factory-name "$FACTORY" \
  --output table

az datafactory integration-runtime show \
  --resource-group "$RG" \
  --factory-name "$FACTORY" \
  --name "$IR" \
  --output json
~~~

Inspect linked services/pipelines at the metadata level:

~~~bash
az datafactory linked-service list \
  --resource-group "$RG" \
  --factory-name "$FACTORY" \
  --query "[].name" \
  --output table

az datafactory pipeline list \
  --resource-group "$RG" \
  --factory-name "$FACTORY" \
  --query "[].name" \
  --output table
~~~

CLI/extension syntax, property names, and responses vary by version; check current `--help`. Use read-only operations only; **never list authentication keys or print credentials** for routine inspections.

### Diagnostic Settings

~~~bash
FACTORY_ID=$(az datafactory show \
  --resource-group "$RG" \
  --factory-name "$FACTORY" \
  --query id -o tsv)

az monitor diagnostic-settings list \
  --resource "$FACTORY_ID" \
  --output json
~~~

Reading diagnostic settings does not prove logs are flowing into the workspace. Verify enabled categories, destination, retention, and actual ingested records.

## 25. Log Analytics and KQL

ADF logs may land in **AzureDiagnostics** or resource-specific tables such as `ADFActivityRun`, `ADFPipelineRun`, and `ADFTriggerRun` depending on diagnostic export configuration. Table and column names depend on diagnostic mode; **do not assume one KQL query works across every workspace**.

Example on a workspace using AzureDiagnostics:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where ResourceProvider =~ "MICROSOFT.DATAFACTORY"
| where Category =~ "ActivityRuns"
| summarize ActivityLogEntries = count()
  by bin(TimeGenerated, 1h), Resource
| order by TimeGenerated asc
~~~

With resource-specific tables, start with schema discovery:

~~~kusto
ADFActivityRun
| where TimeGenerated >= ago(24h)
| take 20
~~~

After inspecting actual columns, add filters for Status, Activity, Pipeline, or IntegrationRuntime. Never invent column names or treat an empty table as proof a pipeline did not run when diagnostic categories are disabled.

### Avoid Logging Secrets

Activity outputs can expose queries, connection endpoints, file paths, error messages, and sensitive parameters. When sharing incident reports, provide **run IDs/error codes and sanitized excerpts** rather than raw JSON dumps.

## 26. Troubleshooting by Failure Category

| Symptom | Likely Cause | What to Check |
|---|---|---|
| SHIR Offline | Windows service, proxy/egress, host crash | Service status, network diagnostics, Event Logs |
| SHIR Online yet SQL times out | SQL TCP port/DNS/firewall, blocked query | Test-NetConnection, SQL health |
| SQL login failed | Wrong credentials, locked account, auth mode | DBA logs, linked service config |
| TLS certificate error | FQDN/SAN/CA mismatch, expired cert | Certificate validation, SQL TLS |
| UNC path unreachable | SMB 445, wrong path, service identity permissions | UNC Test-Path under the exact identity |
| Oracle connector fails | Missing driver/provider, architecture mismatch | Connector prerequisites |
| Sink 403 | Storage RBAC/ACL/SAS expiry, firewall policy | Identity and Storage diagnostics |
| Sink DNS returns public IP when private is needed | Misconfigured Private DNS/VPN | Resolve-DnsName from SHIR |
| Copy is slow | SQL scan, WAN, SHIR CPU/RAM, sink throttling | Copy metrics and source monitoring |
| Jobs queued too long | SHIR capacity/concurrency, nodes Offline | IR monitoring, active jobs |
| Duplicate data after retry | Appends without batch idempotency | Batch/partition staging, dedup |
| Missing rows | Watermark, snapshot consistency, late updates | SQL query bounds, data validation |
| Key registration fails | Wrong IR/key, proxy, or clock skew | IR config, rotation procedure |
| Activity Succeeded yet wrong numbers | Mapping, decimal/timezone, schema drift | Data quality checks |
| No logs visible | Diagnostics not enabled or wrong table | Diagnostic settings and table schema |
| Cost spikes | Full copies, retries, host/network/storage/logging | Cost Management + run history |

**Never fix errors by opening SQL Server 1433 publicly, disabling TLS validation, or granting sysadmin.** Isolate the technical failure at each hop and resolve the actual root cause.

## 27. Performance: Parallelism, Compression, and WAN

Actual speed is bounded by the slowest component among the SQL query, SHIR host, network, and sink.

~~~text
Source SQL → LAN → SHIR CPU/RAM → VPN/Internet → Azure Storage
                ↑                    ↑
            Driver/serialization   Bandwidth/latency
~~~

Example: 600 GiB of data at **80 MiB/s effective throughput**:

~~~text
Transfer lower bound ≈ 600 × 1024 / 80 seconds
                     ≈ 7,680 seconds
                     ≈ 2 hours 8 minutes
~~~

This excludes query execution, staging, retries, validation, sink commits, and setup overhead.

### How to Scale Parallel Copy Safely

- Measure a single-activity baseline first.
- Inspect SQL indexes, WHERE clauses/partition ranges, and actual source reads.
- Partition by sensible keys/dates without dropping or duplicating boundary rows.
- Increase concurrency incrementally while monitoring SQL CPU/locks and networking.
- Watch SHIR resource utilization and sink throttling.
- Avoid producing tiny output files if downstream analytics engines suffer metadata overhead.
- If daytime OLTP workloads are sensitive, cap concurrency and schedule outside peak hours.
- Choose compression deliberately: fewer bytes across the WAN at the expense of CPU on SHIR/source.

**Adding SHIR nodes or increasing `numberOfParallelCopies` does not always speed up loads** if the source SQL server is already saturated.

## 28. SHIR and Pipeline Costs

A common misconception: "Because SHIR runs in our datacenter, ADF is free." Review current pricing models for **ADF/Synapse activities, data movement, execution, and compute**, along with surrounding infrastructure costs.

| Item | Example |
|---|---|
| Pipeline/orchestration | Activity/trigger executions per meter |
| Copy/data movement | Execution duration and runtime type per rate card |
| Windows SHIR host | On-prem server or Azure VM compute/OS/storage |
| HA nodes | Standby hosts, patching, and administration |
| Networking | VPN/ExpressRoute, egress, Firewall/NAT, cross-region |
| Source DB | CPU/IOPS and OLTP impact |
| Azure sink | ADLS storage, write transactions, replication |
| Monitoring | Azure Monitor/Log Analytics ingestion/retention |
| Reliability | Retries, validation, staging, reprocessing |

Model:

~~~text
Cost per valid GiB =
  (Data integration charges
   + SHIR host/network cost
   + storage & monitoring
   + reprocessing overhead)
  / GiB of validated and published data
~~~

Prefer **incremental extraction** over nightly full scans when business logic allows; select only needed columns; track business outcomes and completion times. Looking solely at per-GB transfer rates while ignoring source impact and pipeline failures is incomplete.

## 29. End-to-End Security

A SHIR node can reach both on-premises networks and Azure destinations; if that host is compromised, its data access can be abused. Defense layers:

1. **Least privilege** for SQL logins, SMB accounts, and ADLS principals.
2. **Private endpoints/VPN** per policy—never open public inbound SQL.
3. **TLS/certificate validation** across all supported endpoints.
4. **Windows hardening**, EDR, patching, and restricted local admins.
5. **Key Vault/secrets lifecycle**, rotation, and auditing.
6. **IR registration key protection**, governing who can list or regenerate keys.
7. **Segregation** of prod/non-prod and network zones; avoid an overly privileged shared SHIR.
8. **Data minimization**: source ETL views masking unnecessary PII columns.
9. **Staging retention**: purge temporary data per policy, protect paths, and audit downloads.
10. **Pipeline changes** via code review/Git/IaC, never ad-hoc publishing.
11. **Monitoring** privilege changes, auth failures, offline nodes, and unusual exports.
12. **Incident runbook** to disable triggers, revoke credentials, and assess data impact.

A managed identity authorized to write to ADLS **does not** automatically gain read access on on-premises SQL. Every boundary requires separate authentication and authorization.

## 30. Managing Multiple Environments and CI/CD

Establish naming conventions:

~~~text
DEV:  IR_Corp_ERP_Dev
TEST: IR_Corp_ERP_Test
PROD: IR_Corp_ERP_Prod
~~~

Wherever possible, isolate hosts, credentials, and permissions per environment. Never let dev jobs read production ERP simply because an IR can be shared.

### Deployment Checklist

1. Pipeline/linked service definitions are versioned in Git/IaC per supported workflow.
2. Endpoints and IR names are parameterized by environment.
3. No secrets reside in repositories, templates, or build logs.
4. Runtime nodes and driver versions are inventoried like infrastructure.
5. Production triggers are not enabled prior to Test connection + data validation.
6. Patch SHIR via a rolling plan, validating in staging first.
7. Maintain rollback/forward-fix plans for schema or source credential changes.
8. Establish alerting and on-call processes to avoid silent failures.
9. Maintain configuration backups/recovery plans for supporting infrastructure.
10. Audit drift between Portal state and IaC.

**SHIR sharing** across data factories/workspaces can be supported under certain conditions; never use it to bypass security boundaries, quotas, or concurrency controls.

## 31. Case Study: On-Prem ERP → ADLS → Analytics

### Context

An enterprise runs an ERP SQL Server on its LAN, with an Orders table around 1 TiB growing by 15 GiB/day. Reports must be ready before 06:00; SQL cannot be exposed publicly; operations requires surviving the loss of one SHIR node.

### Proposed Design

- **SHIR:** two Windows nodes in the datacenter, each able to reach SQL/SMB and ADLS. For private sinks, use VPN/ExpressRoute/private DNS.
- **Source:** read-only SQL views, indexed on `ModifiedUtc`/primary key where appropriate.
- **Extraction:** scheduled initial full load; nightly incremental via watermark/CDC or overlap + dedup.
- **Sink:** ADLS staging keyed by run/batch; validate before publishing.
- **Reliability:** commit watermarks only after sink publish; idempotent retries; node failover drills.
- **Security:** Entra/RBAC/Key Vault per connector support, least-privileged SQL account, private networking, and PII minimization.
- **Monitoring:** IR health, pipeline freshness, SQL impact, ADLS write errors, and costs.

### Incident Simulation

At 02:00 node 1 reboots. Node 2 stays Online yet lacks a route to the ADLS Private Endpoint. The pipeline fails. The root cause is not "ADF in Azure broke," but rather that **the standby SHIR node was never tested end-to-end along the data path**. After fixing routing/DNS, retry the **same batch ID**, confirming the watermark stayed at the prior version and outputs are not duplicated.

## 32. Comprehensive Hands-On Lab

> **Safety:** execute only in an authorized lab environment; creating Azure resources and copying data can incur costs. Never run against production ERP, use real PII, or expose registration keys.

### Part A — Architecture and Networking

1. Diagram on-prem SQL Server, Windows SHIR, ADF, ADLS Gen2, and analytics compute.
2. Highlight where the control plane differs from the data plane.
3. Build a network matrix: SHIR → SQL, SHIR → control endpoints, SHIR → ADLS.
4. Test DNS/TCP directly from the SHIR machine.
5. If the sink uses a Private Endpoint, confirm private DNS routing.
6. List required SQL, Storage, and Key Vault permissions.
7. Define data freshness SLOs and batch windows.

### Part B — Creating the Runtime and Linked Services

1. Select the lab ADF/Synapse in the right resource group/subscription.
2. Create the logical SHIR resource.
3. Install the official installer on the Windows lab host.
4. Register the node via key over a secure channel and confirm Online status.
5. Create the SQL Server linked service referencing SHIR via `connectVia`.
6. Create the ADLS linked service/dataset with appropriate auth.
7. Run Test connection, resolving any driver/TLS/port issues.
8. Run a Copy Activity on a 1,000-row lab table.
9. Inspect rows/bytes and verify output counts, schema, and checksums in ADLS.

### Part C — Incremental Loads and Retries

1. Create a watermark control record.
2. Copy a `[start, end)` interval.
3. Insert additional rows and run the next incremental load.
4. Simulate a mid-run failure in the lab.
5. Verify the watermark **does not advance** when sink publish fails.
6. Retry the same batch and confirm zero duplicate outputs.
7. Alter a schema/nullable field to evaluate schema drift handling.
8. Record run IDs and validation metrics.

### Part D — Operations

1. Add a standby SHIR node (if lab permissions allow).
2. Confirm node 2 reaches all sources, sinks, drivers, and credentials.
3. Simulate node 1 Offline and measure recovery.
4. Run read-only CLI commands to list IR resources and linked service names.
5. Inspect diagnostic settings and actual log tables.
6. Configure alerts for SHIR offline or missed data freshness deadlines.
7. Evaluate source CPU/locks and network throughput under parallel runs.
8. Estimate costs across Copy Activity, hosts, networking, storage, and monitoring.
9. Clean up approved lab resources without deleting shared infrastructure.

### Self-Check Questions

**Question 1.** What is Integration Runtime, and how does it differ from pipelines, linked services, and datasets?

**Question 2.** When should you choose Azure IR, SHIR, and Azure-SSIS IR?

**Question 3.** Does an Azure IR inside a Managed VNet automatically reach every SQL Server on a corporate LAN? Why?

**Question 4.** Why doesn't SHIR require opening inbound SQL ports from the public Internet?

**Question 5.** Does SHIR showing Online prove it can `SELECT` from SQL and upload to ADLS?

**Question 6.** Which network and identity paths must be verified separately?

**Question 7.** Why doesn't TCP port 1433 apply to every SQL Server named instance?

**Question 8.** When the File System connector reads UNC paths, why can an RDP admin session and the service identity behave differently?

**Question 9.** What does `connectVia` in a linked service specify?

**Question 10.** Is a SHIR registration key equivalent to a SQL password or managed identity?

**Question 11.** When adding a second SHIR node, what must be verified to achieve real HA?

**Question 12.** Why can running more Copy Activities slow down the source ERP?

**Question 13.** Why must watermarks commit only after output validation and publishing?

**Question 14.** What data changes can `ModifiedUtc` miss, and how can CDC help?

**Question 15.** If Copy wrote 70% of a file before retrying, what prevents duplicate or partial data?

**Question 16.** Does an Azure Storage Private Endpoint automatically provide network routing from on-premises?

**Question 17.** Are AuthN/AuthZ mechanisms identical for SQL Server and ADLS?

**Question 18.** Can Azure-SSIS IR replace a Copy Activity running on SHIR?

**Question 19.** What telemetry distinguishes an Offline IR host from a SQL query timeout?

**Question 20.** If a KQL query on `AzureDiagnostics` returns empty, can you conclude no activity logs exist?

**Question 21.** What cost components exist beyond the SHIR Windows host itself?

**Question 22.** Why is `Copy Activity Succeeded` insufficient to prove data quality?

**Question 23.** How do you deploy prod/dev SHIR without sharing overly privileged credentials or networks?

**Question 24.** Why must a reprocess/replay plan be documented before going to production?

**Completion criteria:** learners can select the right IR by network path and activity type, explain the on-prem → SHIR → Azure data path, design linked services, install and monitor SHIR, troubleshoot auth/network errors, build incremental/idempotent copies, plan HA/SLOs, and analyze costs.

## Conclusion

**Integration Runtime** is the essential bridge moving data from source to destination in Azure Data Factory and Synapse pipelines. **Azure IR** handles cloud-accessible workloads; **Self-hosted IR** bridges through Windows hosts with access to on-premises/private networks; **Azure-SSIS IR** focuses on running SSIS packages. Selecting the right IR must be driven by **source/sink reachability and activity execution models**, not merely the service name.

A resilient production pipeline needs more than an Online SHIR node: it requires **correct routing/DNS/firewalls, source/sink authentication, credential protection, per-node HA validation, sizing aligned to SQL/WAN/storage, incremental watermarks/CDC, staging and idempotent retries, freshness/quality monitoring, and cost controls**. By clearly separating the control plane from the data plane, teams can migrate and integrate on-premises data into Azure without compromising network security or ERP reliability.

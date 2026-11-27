# Autonomous Database, Wallets, and Operational Responsibility Boundaries

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Extended Features  
> **Goal:** Understand the operational model of Oracle Autonomous Database; distinguish responsibilities between Oracle Cloud and the customer; configure secure connections using TLS/mTLS and client credentials wallets; manage TNS aliases, JDBC, and connection pools; distinguish database identities from OCI IAM; operate network access, wallet rotation, backup/restore, patching, monitoring, scaling, and incident response along clear responsibility boundaries.

## 1. What Is Autonomous Database?

Oracle Autonomous Database (ADB) is a managed database service on Oracle Cloud Infrastructure (OCI). The service automates many administrative tasks normally performed manually on self-managed databases, such as provisioning, certain patching activities, backups, tuning, and scaling according to service configuration.

The word autonomous does not mean the database decides every business policy on its own or that the customer no longer has operational responsibilities. Oracle manages the service platform under a cloud managed service model; the customer remains responsible for data, schemas, users, access permissions, applications, organizational network policies, client wallets, testing, and business workflows.

ADB is commonly used for workloads such as:

- **Autonomous Transaction Processing (ATP):** transactional workloads, OLTP applications, and concurrent processing.
- **Autonomous Data Warehouse (ADW):** analytical workloads, reporting, and data warehousing.
- Specialized Autonomous Database configurations or deployments on dedicated Exadata infrastructure depending on service selection and region.

Service names, options, service levels, and administration capabilities can vary by edition, deployment model, region, and time. When deploying, consult the configuration page and documentation for the exact service in use.

### 1.1. Autonomous Does Not Mean No DBA Needed

Automated infrastructure tasks let DBAs shift focus toward:

- Schema and data model design.
- Access control and data classification.
- SQL, index, partition, and workload design.
- Connection, wallet, and credential management.
- Application testing after patching/maintenance.
- Monitoring performance, SLAs, costs, and capacity.
- Designing backup/restore and disaster recovery to meet business requirements.
- Coordinating schema changes, releases, and incident response.

DBAs still need to understand transactions, SQL execution plans, locking, resource usage, security, and recovery. A managed service changes where some administrative actions are executed, not the accountability for ensuring the system meets business needs.

## 2. Service Layers and Management Boundaries

A useful perspective divides ADB into three layers:

1. **Cloud control plane:** OCI Console, API, IAM, networking, and service resource configuration.
2. **Database service plane:** database instance, database users, schemas, SQL, backup/restore, and workload services.
3. **Application/client plane:** application, JDBC driver, wallet, connection pool, secret management, and business transactions.

~~~text
Organization / Cloud tenancy
        |
        +---- OCI IAM, policies, compartments
        |
        +---- VCN, subnet, NSG, private endpoint
        |
        v
Autonomous Database service
        |
        +---- Managed database infrastructure
        +---- Database users, roles, schemas
        +---- Workload services
        +---- Backup / restore / monitoring
        |
        v
Application runtime
        |
        +---- JDBC driver and TNS alias
        +---- Wallet / TLS trust
        +---- Connection pool
        +---- Application authorization
~~~

OCI IAM controls who can manage cloud resources. Database users/roles control who can read or modify data inside the database. Wallets assist in establishing connections and authenticating under the configured mode. These three layers must be managed together, yet none can replace another.

## 3. Deployment Models: Serverless and Dedicated

ADB can be provisioned under different deployment models. Two common concepts are Serverless and Dedicated Infrastructure.

### 3.1. Autonomous Database Serverless

In the Serverless model, Oracle manages the Exadata infrastructure and most database platform operations. The customer creates a database in OCI, picks a workload, configures compute/storage, network access, and service options.

Common characteristics:

- Provision databases via OCI Console/API.
- Compute can adjust within service capabilities and policies.
- Oracle automates maintenance activities supported by the service.
- Backups and recovery options are built in.
- Customers focus on schemas, data, access policies, and applications.

Serverless does not mean the database has no compute/storage limits or incurs no quotas/costs. Customers must still pick appropriate sizing, monitor usage, and control scaling.

### 3.2. Autonomous Database Dedicated

Dedicated Infrastructure provides Exadata infrastructure dedicated to a tenancy/customer under the corresponding service model. Customers gain additional control options over dedicated database infrastructure, resource allocation, and isolation depending on the service.

Resources can be created and managed across layers such as:

- Exadata Infrastructure.
- Autonomous Container Database.
- Autonomous Database.

The dedicated model adds infrastructure-tier orchestration options and responsibilities compared to Serverless, while remaining a managed service. Clearly delineate customer-controlled operations from Oracle-managed components per contract, service description, and deployment configuration.

### 3.3. Choosing a Model by Requirements

| Criterion | Serverless | Dedicated |
|---|---|---|
| Goal | Simplify deployment and operations | Greater isolation and dedicated infrastructure control |
| Exadata management | Oracle manages the platform | Dedicated infrastructure per service model |
| Configuration | Within offered service options | Additional infrastructure/container-tier configuration depending on edition |
| Operations | Focus on database, security, and apps | Requires orchestrating dedicated infrastructure lifecycle |
| Best suited for | Many typical cloud-managed workloads | Specific isolation, capacity, or governance requirements |

Do not choose Dedicated solely because the name sounds safer. Evaluate workload, compliance, isolation, capacity, regional availability, operational model, and total cost.

## 4. ATP and ADW: Choosing the Right Workload Service

Autonomous Transaction Processing and Autonomous Data Warehouse are optimized for different workloads.

### 4.1. ATP

ATP fits:

- Short, frequent transactions.
- High concurrent session counts.
- Inserts/updates/deletes.
- Transactional business applications.
- Backend APIs and transaction processing.

Applications should design connection pools, transaction durations, indexes, and SQL around OLTP patterns.

### 4.2. ADW

ADW fits:

- Queries scanning/aggregating large volumes of data.
- Reporting and analytics.
- Data warehouse workloads.
- Batch transformations and analytical SQL.

Analytical workloads may use parallel execution and consume more compute. Control concurrency, service classes, query durations, and costs.

### 4.3. Do Not Use One Database/Service for Every Workload by Default

An OLTP application and a large-scan report can contend for resources. Consider separate workload services, read replicas/standbys, or separating analytical workloads per supported architectures.

Do not move a workload to ADW merely because a query is slow; inspect execution plans, data models, and access patterns first.

## 5. Wallets in Autonomous Database

A wallet is a set of security files used by clients in certain connection methods to ADB. A wallet can hold certificates, private keys, and connection configuration. With mTLS connections, the wallet supplies client identity so the database authenticates the client over TLS.

A wallet is not:

- A database schema.
- A database user password.
- An OCI IAM policy.
- A database backup.
- A file storing table data.
- A mechanism granting SELECT/INSERT/UPDATE privileges.

The wallet helps establish a secure connection; after connecting, the database still identifies the database user and enforces that user's privileges per the authentication mechanism used.

### 5.1. TLS and mTLS

**One-way TLS (server-authenticated TLS):**

- Client verifies the server's certificate.
- Server does not require a client certificate to authenticate the connection at the TLS layer.
- Application still needs database credentials or another database authentication method.

**Mutual TLS (mTLS):**

- Client verifies the server certificate.
- Server also requires a client certificate.
- Client presents its certificate and proves possession of the corresponding private key.
- ADB can use client credentials wallets for this method.

mTLS authenticates the client at the connection layer. It does not automatically grant access to every schema. Database users/roles still govern data privileges.

### 5.2. Client Credentials Wallets

Wallets are downloaded from the OCI Console or supported administrative mechanisms for Autonomous Database. The ZIP file commonly contains items such as:

- cwallet.sso: auto-login wallet in corresponding wallet configurations.
- ewallet.p12: password-protected wallet.
- tnsnames.ora: connection network aliases.
- sqlnet.ora: Oracle Net/wallet configuration.
- README or instruction files.

Exact contents can vary by wallet type and service. Inspect the ZIP contents and documentation for your ADB instance; do not assume every wallet has an identical layout.

### 5.3. Wallet Password

The wallet password protects wallet files such as ewallet.p12. It is not necessarily the database user's password.

Distinguish:

| Secret | Purpose |
|---|---|
| Wallet password | Opens or manages a password-protected wallet |
| Database user password | Authenticates a database user when using username/password |
| Client private key | Proves client identity in mTLS |
| OCI API key/private key | Authenticates a principal with OCI APIs per corresponding mechanism |
| OAuth/token/secret | Authenticates an application with another service |

Never reuse one password across all credential types and never store wallet passwords in source code.

### 5.4. Auto-Login Wallets

An auto-login wallet lets Oracle clients use the wallet without prompting for the wallet password on every connection, depending on configuration and platform.

This is convenient for server applications yet makes filesystem permissions critical: any process able to read the auto-login wallet can use its contents within client/tool capabilities.

Protect the wallet directory:

- Only the required service account may read it.
- Never place it in a web root or public directory.
- Never commit wallet ZIPs or files into Git.
- Never attach wallets to tickets/chats.
- Never bake wallets into shared container/image layers.
- Never leave wallets in temp directories with uncontrolled cleanup or backups.
- Encrypt and restrict access to wallet backups.

## 6. Downloading and Installing Wallets Safely

General procedure:

1. Identify the exact Autonomous Database and environment.
2. Select the wallet type/connection method approved by the organization.
3. Download the wallet via the OCI Console or authorized API.
4. Set a policy-compliant wallet password when prompted during download.
5. Extract into a dedicated directory on the application host.
6. Grant least-privilege filesystem permissions to the service account.
7. Configure Oracle client/JDBC to point to the wallet directory.
8. Connect using the appropriate alias.
9. Verify database user, service, TLS mode, and workload service.
10. Record owner, download date, version/rotation event, and secure storage location.

Never download wallets from unverified sources or use production wallets on unmanaged developer machines.

### 6.1. Example Directory Structure

Example on Linux:

~~~text
/opt/app/
  config/
    oracle/
      adb-prod/
        cwallet.sso
        ewallet.p12
        tnsnames.ora
        sqlnet.ora
~~~

This directory is an example on the application host. Client wallets do not reside on the database server filesystem the way DIRECTORY objects work; they are credentials/configurations read by Oracle clients.

### 6.2. Filesystem Permissions

Verification example:

~~~bash
ls -ld /opt/app/config/oracle/adb-prod
ls -l /opt/app/config/oracle/adb-prod
namei -l /opt/app/config/oracle/adb-prod
~~~

Grant read access only to the application service account and approved operations group. Never use chmod 777. On Windows, check NTFS ACLs for the service account; in containers, verify secret/volume mounts and actual UID/GID.

### 6.3. Do Not Confuse Client Wallets with DIRECTORY Objects

A DIRECTORY object maps a name inside Oracle Database to a path accessed by database server processes. A client wallet sits on the application host/container and is read by JDBC/Oracle Net clients.

If a JDBC app runs in Kubernetes, the wallet is typically mounted into pods via secrets/volumes or secret delivery mechanisms. If running on a VM, the wallet lives in a protected filesystem on the VM. Delivery differs, yet the principle stays the same: never expose private keys beyond the clients that need them.

## 7. TNS Aliases and Workload Services

The wallet ZIP usually contains `tnsnames.ora` with multiple connection aliases. Each alias has a connect descriptor and service name matching a workload service.

Conceptual example:

~~~text
myadb_high =
  (description =
    (retry_count = 20)
    (retry_delay = 3)
    (address =
      (protocol = tcps)
      (port = 1522)
      (host = adb.example.oraclecloud.com)
    )
    (connect_data =
      (service_name = example_high.adb.oraclecloud.com)
    )
    (security =
      (ssl_server_dn_match = yes)
    )
  )
~~~

This is a condensed illustrative example; use the aliases and descriptors provided in the wallet downloaded from your exact database rather than fabricating production hostnames/service names from a template.

### 7.1. Workload Service Aliases

Depending on ADB type and configuration, wallets may provide aliases with suffixes such as:

- high
- medium
- low
- tp
- tpurgent

Not every database has the exact same alias list. Check `tnsnames.ora` and service details in the specific database's documentation.

Different services can enforce different consumer groups, concurrency, parallelism, or resource management policies. Pick the service suited to your workload instead of always picking HIGH.

### 7.2. Service Selection Examples

| Workload | Service to Evaluate |
|---|---|
| Short, latency-sensitive transactions | Appropriate OLTP service, e.g. TP if available in configuration |
| High-priority transactions | TPURGENT if offered by service and entitled |
| Analytical/reporting queries | HIGH/MEDIUM/LOW per workload and policy |
| Long batch jobs, low concurrency | Service aligned with batch/resource policies |
| Standard applications | MEDIUM or service prescribed by architecture |

Service names are not arbitrary business priority labels. Each service has semantics and limits provided by ADB. Inspect actual configuration and benchmark before switching.

## 8. Configuring JDBC Thin with a Wallet

The Oracle JDBC Thin driver can use Oracle Net configuration and wallets. A common approach is setting `TNS_ADMIN` to the directory containing `tnsnames.ora`/`sqlnet.ora`/wallet, then connecting by alias.

### 8.1. JDBC URL with TNS Alias

Example:

~~~text
jdbc:oracle:thin:@myadb_medium?TNS_ADMIN=/opt/app/config/oracle/adb-prod
~~~

This is an illustrative pattern. The alias must exist in `tnsnames.ora` from the exact database's wallet; supported URL property syntax depends on the Oracle JDBC driver version.

Another approach is configuring `TNS_ADMIN` via JVM/system property or `OracleDataSource` property per driver documentation:

~~~text
-Doracle.net.tns_admin=/opt/app/config/oracle/adb-prod
~~~

Never configure multiple inconsistent wallet paths simultaneously. When using a connection pool, every connection in the pool should share the same target/service configuration and wallet lifecycle.

### 8.2. Spring Boot DataSource

Configuration example:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@myadb_medium?TNS_ADMIN=/opt/app/config/oracle/adb-prod
    username: APP_USER
    password: DB_PASSWORD_FROM_SECRET_STORE
    driver-class-name: oracle.jdbc.OracleDriver
~~~

`DB_PASSWORD_FROM_SECRET_STORE` is an illustrative placeholder for a secret injected from a secret manager or platform security mechanism. Never store plaintext passwords in committed `application.yml` files.

If connections use another database authentication method or an mTLS-only flow per supported configurations, username/password configuration may differ. Consult the authentication methods of ADB and the Oracle JDBC driver.

### 8.3. Verifying Connections

After connecting, confirm database/service/user:

~~~sql
SELECT
    sys_context('USERENV', 'DB_NAME') AS db_name,
    sys_context('USERENV', 'SERVICE_NAME') AS service_name,
    sys_context('USERENV', 'SESSION_USER') AS session_user,
    sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Do not test only with `SELECT 1`. A connection can succeed while pointing to the wrong database, PDB, schema, or workload service.

### 8.4. Driver Compatibility

Choose an Oracle JDBC driver compatible with your JDK, Spring Boot/Hibernate, and database deployment. TNS aliases, wallet handling, TLS protocols, and authentication options can change across driver releases.

Pin driver versions, test connections on the exact runtime, and read release notes before upgrading.

## 9. Connection Pools and Wallet Lifecycle

Applications typically use HikariCP, UCP, or application-server-managed pools. Pools hold physical database sessions and reuse them across requests.

Define:

- Which service alias the pool connects to.
- Maximum and minimum connection counts.
- Connection timeouts.
- Idle/max lifetimes.
- Validation/health checks.
- Retries during database failover/maintenance.
- Behavior when wallets change.
- How physical connections are recycled after credential rotation.

### 9.1. Replacing a Wallet Does Not Automatically Update Existing Connections

A pool may hold physical connections already opened using the old wallet. Swapping wallet files on the filesystem does not guarantee active connections immediately use new credentials.

A coordinated rotation workflow needs:

1. Issue/download the new wallet per ADB procedures.
2. Update the secret/volume or file location.
3. Verify the application can open new connections with the new wallet.
4. Recycle the pool or perform a planned rolling restart.
5. Confirm new connections work.
6. Monitor old connections and authentication errors.
7. Revoke/rotate old credentials per policy and verify actual status.

Never delete the old wallet before confirming all workloads have switched and a rollback option exists. At the same time, never keep old wallets longer than security policy permits.

### 9.2. Connection Pools After Maintenance/Failover

After maintenance, restarts, or role transitions, old connections can be severed. Pools must evict broken connections and establish new ones. Applications must implement bounded retries and handle indeterminate transaction outcomes.

Never blindly retry a write transaction when the client does not know whether COMMIT succeeded. Use idempotency keys or check business state.

## 10. Database Identity and OCI IAM Are Two Separate Layers

OCI IAM manages identities and permissions over cloud resources. Database authentication/authorization manages sessions and data access privileges.

### 10.1. OCI IAM

OCI IAM can manage:

- Users/groups.
- Dynamic groups.
- Policies.
- Compartments.
- Permissions to create/read/update Autonomous Database resources.
- Permissions to download wallets or perform administrative actions per policy.
- Access to Vault, Object Storage, and other cloud services.

Conceptual policy example:

~~~text
Allow group DatabaseOperators to read autonomous-databases in compartment Production
~~~

Policy syntax and scope must follow actual OCI IAM policy language, compartments, and resource types. The example above illustrates intent only, not a complete policy for every API.

### 10.2. Database Users and Roles

Database users can be granted:

- CREATE SESSION.
- SELECT/INSERT/UPDATE/DELETE on objects.
- EXECUTE on packages.
- Application roles.
- Quotas and schema privileges as needed.

Example:

~~~sql
CREATE USER app_user IDENTIFIED BY "<secret-managed-password>";
GRANT CREATE SESSION TO app_user;
GRANT SELECT, INSERT, UPDATE ON app_owner.orders TO app_user;
~~~

This is a lab example. In production, generate/rotate passwords through secret management workflows, restrict privileges, and apply appropriate roles/object grants.

### 10.3. OCI IAM Does Not Automatically Grant SELECT on Tables

A user authorized to manage an Autonomous Database resource in the OCI Console does not automatically have SELECT privilege on data inside the database.

Conversely, a database user with SELECT on tables does not automatically have permission to stop, scale, or reconfigure the Autonomous Database in OCI.

Review both permission matrices separately:

| Action | Permission Layer |
|---|---|
| Create/scale/stop ADB resource | OCI IAM policy |
| Download or rotate wallet | OCI IAM/ADB administrative permission |
| Open database connection | Network policy + TLS/mTLS + authentication |
| Log into schema | Database authentication |
| SELECT/UPDATE tables | Database grants/roles |
| Call packages | Database EXECUTE privilege |
| Read secrets in OCI Vault | OCI IAM policy and secret authorization |
| Read Object Storage data from database | Credential/resource principal mechanism and matching policy |

## 11. Resource Principals and Accessing OCI Services from the Database

Some ADB features allow database workloads to access OCI services without storing long-lived API keys in database code, using resource principals or supported credential mechanisms.

Workloads may need to:

- Read/write Object Storage.
- Access certain OCI resources.
- Use DBMS_CLOUD or cloud service integrations.
- Perform operations using the Autonomous Database resource's identity.

Distinguish:

- **Client wallet:** lets applications connect into the database.
- **Database credential:** authenticates database users.
- **Resource principal:** identity of the database resource when calling supported OCI services.
- **OCI IAM policy:** authorizes the resource principal to perform cloud actions.
- **Database package privilege:** permits schemas to invoke corresponding packages/features.

A resource principal does not grant default access to every bucket or secret. Configure dynamic groups/resource principal policies scoped to the right compartment/resource and grant only needed permissions.

Never hardcode OCI user API keys in PL/SQL when the service supports appropriate identity-based access.

## 12. Network Access: Public Endpoints vs. Private Endpoints

ADB can be configured with different network access options depending on deployment model and features:

- Public endpoint with configured access control/ACLs.
- Private endpoint inside a VCN.
- Network Security Groups and subnet/security policies.
- Private DNS/routing.
- Connectivity over VPN/FastConnect or organizational network paths.

### 12.1. Public Endpoint

A public endpoint does not mean opening the database to the entire Internet if access controls are configured properly. You must:

- Allow only required source IPs/networks.
- Avoid overly broad CIDRs.
- Manage egress/ingress policies.
- Control DNS and TLS.
- Monitor access list changes.
- Review OCI IAM permissions to edit network access.

### 12.2. Private Endpoint

A private endpoint provides database access over a private network within supported configurations. It does not solve every security concern on its own:

- Clients still require authentication.
- Database users still require appropriate privileges.
- Routes, subnets, NSGs, and DNS must be accurate.
- On-premises clients need VPN/FastConnect or appropriate network paths.
- Wallet/TLS configurations must still be valid if required by the connection method.

Private endpoints reduce public exposure, yet do not replace least privilege, auditing, or credential protection.

### 12.3. Database Network ACLs vs. OCI Network Policies

Distinguish:

- OCI VCN/subnet/NSG/security lists: control network paths in cloud networking.
- ADB access control list/private endpoint configuration: controls allowed inbound connection sources per service.
- Oracle database network ACLs: control outbound network calls from PL/SQL such as UTL_HTTP.
- Host firewalls/egress proxies: control traffic at host/application networks.

An inbound JDBC connection into ADB and an outbound UTL_HTTP call from the database are two separate flows. Configuring network access for one flow does not automatically allow the other.

## 13. TLS, mTLS, and Database Authentication

When a client connects to ADB, separate three steps:

1. **Network reachability:** DNS, routing, endpoint, firewalls, private/public access.
2. **TLS handshake:** verifying server certificate; mTLS may require client certificates.
3. **Database authentication/authorization:** identifying user/schema and privileges.

Failures can occur at each layer:

| Layer | Example Errors | What to Check |
|---|---|---|
| Network | Timeout, connection refused | DNS, routes, NSGs, access controls |
| TLS | Certificate validation/handshake failure | Wallet, trust chain, clocks, driver |
| Authentication | Invalid username/password or client identity | Credentials, wallet, auth mode |
| Authorization | Insufficient privileges | Database grants/roles |
| Workload | Query timeout/resource error | Service alias, SQL, concurrency |

Do not fix a TLS error by granting extra database privileges. Do not fix ORA-01017 by widening a network ACL.

## 14. Wallet Rotation and Credential Revocation

Wallets hold sensitive credentials and must be managed as lifecycle-controlled secrets.

### 14.1. When Is Rotation Needed?

- Per security policy schedule.
- When wallet compromise is suspected.
- When personnel/vendors lose access.
- When changing client certificates.
- When switching authentication modes.
- Upon compliance requirements or incident response.

### 14.2. General Rotation Workflow

1. Identify every consumer of the wallet: VMs, containers, CI/CD, developer workstations, batch jobs, and DR sites.
2. Confirm the operator holds appropriate OCI IAM permissions.
3. Generate/download the new wallet via ADB-supported mechanisms.
4. Store the new wallet in a secret manager or secure volume.
5. Deploy to a canary client.
6. Verify TLS/mTLS, database authentication, and service aliases.
7. Recycle pools or run a planned rolling restart.
8. Confirm all workloads use the new wallet.
9. Revoke old wallets/certificates per service policy and semantics.
10. Delete old copies per retention/security procedures.
11. Record audit trail and update inventory.

### 14.3. Handling a Compromised Wallet

If a wallet or private key is exposed:

- Trigger incident/security response.
- Identify affected wallet type, database, services, and clients.
- Restrict or revoke credentials using capabilities provided by ADB.
- Issue new wallets/certificates.
- Recycle connection pools and client runtimes.
- Inspect access/audit logs for anomalous access.
- Check secret replication, backups, container images, and developer copies.
- Verify old clients can no longer connect as required by the incident.
- Document timeline and root cause.

Merely deleting a file from one host does not revoke credentials. The wallet may have been copied across multiple hosts or backups.

## 15. Backup, Restore, and Data Responsibility

ADB automates backups per service configuration and offers supported restore/recovery features. Even so, customers must understand recovery objectives and verify procedures meet business needs.

### 15.1. Questions to Answer

- How long is current backup retention?
- Is point-in-time recovery available to the required granularity?
- What are business RPO/RTO targets?
- Are manual backups or supplementary exports needed?
- Which legal/compliance retention policies apply to the data?
- Who is authorized to restore/clone the database?
- Does restore require dual approval?
- Can applications connect to the restored database?
- Must wallets, service aliases, secrets, and network access be updated after restore?

Never assume Oracle-managed backups mean the customer does not need to test restores.

### 15.2. Backups Do Not Replace Logical Recovery

Backups protect whole-database recoverability. Yet when a user accidentally deletes specific rows, Flashback, point-in-time clone/restore, export/import, or logical recovery may be needed to recover the exact data.

A full-database restore can affect newer transactions. Pick a recovery method aligned with failure scope and business impact.

### 15.3. Testing Restores

Execute via supported procedures:

1. Define target time/SCN or recovery objective.
2. Select an appropriate restore/clone destination.
3. Verify OCI IAM permissions and network isolation.
4. Execute restore/clone via OCI Console/API.
5. Verify database open mode, schemas, and data.
6. Run application smoke tests.
7. Verify users/roles, wallets, connection aliases, and secrets.
8. Measure actual elapsed time.
9. Document RPO/RTO and evidence.

Menu names, retention periods, and restore options depend on service/region/configuration. Follow the interface and documentation for your exact ADB instance.

## 16. Patching, Maintenance, and Change Management

Oracle manages many patching/maintenance activities for ADB. Customers remain responsible for managing application-layer impact.

### 16.1. Customer Responsibilities Before Maintenance

- Monitor maintenance notices and scheduled windows.
- Identify impacted applications, batches, and integrations.
- Verify connection pool settings, retries, timeouts, and reconnect logic.
- Confirm backup/recovery posture.
- Verify driver/client compatibility if changes are planned.
- Prepare smoke tests and business validation.
- Notify stakeholders per change policy.

### 16.2. During and After Maintenance

- Monitor ADB status in OCI.
- Check connection errors and pool recovery.
- Verify service names, database users, and schemas.
- Run approved read/write smoke tests.
- Check latency, throughput, and error rates.
- Confirm scheduled jobs, replication, and integrations.
- Record incident/change evidence if impact occurred.

Never assume completed maintenance means every connection pool recovered automatically. Stale connections may require pool recycling.

### 16.3. Database Version and Client Compatibility

ADB may be patched/upgraded per service lifecycle. Customers must keep drivers, frameworks, SQL, and stored code compatible with supported service versions.

Do not run outdated drivers or rely on undocumented behavior. Pin dependencies and maintain a regression suite running against a test ADB environment.

## 17. Scaling and Workload Management

ADB offers compute/storage scaling capabilities based on service model and configuration. Scaling affects both cost and performance.

### 17.1. Scaling Compute

Before scaling compute up:

- Identify whether the bottleneck is CPU, I/O, memory, concurrency, or SQL plans.
- Inspect peak load timing and workload mix.
- Evaluate parallelism and service classes.
- Measure latency/throughput before and after.
- Check costs per service billing unit.

Scaling compute helps CPU-bound workloads, yet does not fix poor queries, lock contention, or network latency.

### 17.2. Auto Scaling

If the service supports auto scaling, determine:

- Scaling conditions and bounds.
- Behavior during peak workloads.
- Cost impact.
- Quotas/compartment budgets.
- Monitoring and alerts.
- Consequences for connection pools and concurrency.

Do not let auto scaling replace capacity governance. Configure budgets, alerts, and policies to prevent unexpected compute spikes.

### 17.3. Storage Scaling

Monitor storage usage, growth, retention, and backup footprint. Check storage expansion limits/options for your service model. Do not wait until storage is nearly full to plan.

## 18. Monitoring and Observability

Operating ADB requires observing both database metrics and cloud resource metrics.

### 18.1. Database-Level Metrics

Monitor:

- CPU/database time.
- Active sessions.
- SQL execution times.
- Buffer gets and physical reads.
- Wait events.
- Connection errors.
- Tablespace/storage usage.
- Transaction rates.
- Failed logins and privilege errors.
- Long-running SQL and blocking sessions.
- Workload service usage.

Use views/tools permitted by ADB. Some traditional DBA privileges may be restricted in a managed service; do not assume application users can access every V$ view.

### 18.2. OCI Monitoring

Track service-published metrics and events via OCI Monitoring/Events/Logging depending on configuration:

- CPU utilization.
- Storage utilization.
- Availability/lifecycle state.
- Maintenance events.
- Connection/network metrics if provided by the service.
- Alarms and notifications.

Exact metric names and namespaces must come from the specific ADB resource and current OCI documentation.

### 18.3. Alerts and Ownership

Every alert should include:

- Severity.
- Resource OCID or database identity.
- Metric/query.
- Threshold and duration.
- Business impact.
- Owner/on-call.
- Runbook.
- Escalation path.

A high-CPU alert should route to SQL/workload analysis; a wallet-expiry alert should route to the rotation owner; an OCI resource lifecycle alert should route to cloud operations.

## 19. High Availability and Disaster Recovery

ADB provides availability/recovery options depending on service model and configuration. Customers must choose topologies aligned with RTO/RPO.

Options may include:

- Platform-managed redundancy.
- Autonomous Data Guard/standby capabilities if provided and enabled.
- Cross-region disaster recovery per supported configurations/editions.
- Backups and point-in-time restores.
- Application retry/reconnect logic.
- Data exports/replication for specialized requirements.

### 19.1. HA Is Not Backup

HA keeps the service running when certain components fail. Backup/restore recovers data after logical errors, accidental deletes, or major disasters.

A standby replicates accidental deletes or bad data changes. Therefore, a standby never replaces backups.

### 19.2. Failover Testing

- Identify primary/standby roles.
- Check lag/protection state if exposed.
- Execute switchover/failover per ADB runbook.
- Verify service aliases and application reconnection.
- Verify transaction outcomes.
- Measure actual RTO/RPO.
- Verify backups after role transitions.
- Document any manual actions and follow-ups.

Do not run manual Data Guard commands meant for self-managed databases if the ADB service forbids or does not support them. Use operations/automation provided by the service.

## 20. Operational Responsibility Matrix

Exact boundaries depend on service model, contract, edition, and configuration. The table below serves as a shared-responsibility framework for building a RACI, not a replacement for Oracle's service description.

| Area | Oracle / Service Provider | Customer / Organization |
|---|---|---|
| Data center, hardware, Exadata platform | Managed per service | Chooses region/service model and requirements |
| Provisioning database service | Provides automation/control plane | Chooses configuration, compartment, workload |
| Database infrastructure patching | Executes per service lifecycle | Tracks maintenance, tests applications |
| Backup automation | Provides and operates per service policy | Defines requirements, retention options if any, tests restores |
| Database schemas and data models | Storage platform | Designs, evolves, and governs |
| Database users/roles/grants | Provides database engine | Creates, reviews, revokes, and audits |
| Application SQL/JDBC/ORM | Does not own application logic | Develops, tunes, and maintains compatibility |
| Wallets/client certificates | Provides service mechanism to create/download/rotate | Protects, distributes, rotates, and revokes across client estate |
| OCI IAM policies | Provides IAM platform | Designs least privilege and manages groups/policies |
| VCN/NSG/private connectivity | Provides networking platform | Designs routes, subnets, and access policies per ownership |
| Data classification/privacy | Provides baseline controls per service | Classifies, governs retention, lawful use, and access |
| Encryption at rest | Service provides baseline encryption per configuration | Manages customer-managed keys if used |
| Platform monitoring | Publishes metrics/events per service | Configures alerts, owners, and responses |
| Business continuity | Provides supported capabilities | Chooses RTO/RPO, topology, and conducts drills |
| Application recovery | Does not guarantee app business behavior | Tests, reconnects, reconciles, and validates business state |
| Cost governance | Provides usage/billing data | Manages budgets, tagging, alerts, and workload optimization |

### 20.1. Boundaries Are Not Always Static

Backup example: Oracle may run automated backups and manage backup infrastructure, yet the customer still needs to understand retention, restore options, restore permissions, and post-recovery data validation.

Patching example: Oracle may patch the database service, yet the customer must test applications, JDBC drivers, SQL plans, stored procedures, and integrations after maintenance.

Wallet example: OCI provides mechanisms to generate/download wallets, yet the customer must protect files on every host, container, CI/CD runner, and workstation that receives them.

## 21. Security Baseline

### 21.1. Least Privilege

- OCI IAM policies grant only required resource permissions.
- Separate cloud operators from database developers.
- Database application users hold privileges only on required objects.
- Never use the ADMIN account in application runtimes.
- Separate schema owners from runtime schemas where appropriate.
- Review EXECUTE grants on packages.
- Revoke access when workloads or personnel offboard.

### 21.2. Secret Management

- Store database passwords and wallet passwords in an approved secret manager.
- Never commit wallet ZIPs, private keys, or credentials.
- Never embed wallets into Docker image layers.
- Use secret volumes or appropriate secret injection.
- Restrict read access and audit secret reads.
- Maintain rotation schedules and incident revocation plans.
- Never log connection strings containing secrets.

### 21.3. Encryption

ADB typically provides encryption-at-rest and TLS capabilities per service. Customers must select connection modes, protect client wallets, and manage keys under their chosen model.

If using customer-managed keys via OCI Vault, define key owners, rotation, availability, policies, and recovery procedures. Losing key access can impact usability of protected data.

### 21.4. Auditing

Enable and configure auditing per requirements. Track:

- Failed/successful logins.
- Privilege changes.
- User/role changes.
- DDL/schema changes.
- Sensitive table access.
- Administrative operations.
- Wallet downloads/rotations via OCI audit trails if available.
- Network access configuration changes.

Retain logs for required periods and restrict who can modify/delete logs.

## 22. Runbook: Onboarding a New Application

### Step 1 — Classify Workload

Determine ATP/ADW, service alias, concurrency, latency, data classification, RTO/RPO, and network location.

### Step 2 — Set Up Cloud Access

Create appropriate compartments/groups/policies for operators. Do not grant tenancy-wide admin rights if only one database resource needs management.

### Step 3 — Create Database Identity

Create schemas/users, roles, and minimal object grants. Never use ADMIN for runtime connections.

### Step 4 — Configure Networking

Select public access with ACLs or a private endpoint per security design. Verify DNS, routes, NSGs, firewalls, and source networks.

### Step 5 — Issue Wallet

Download the wallet matching the selected mTLS/TLS mode, store it in secrets/secure filesystems, set owner/permissions, and update inventory.

### Step 6 — Configure JDBC

Use the right TNS alias/workload service, TNS_ADMIN, and compatible Oracle JDBC driver. Inject database credentials from the secret store if required by the auth method.

### Step 7 — Verify

- TLS handshake.
- Database login.
- SERVICE_NAME.
- SESSION_USER/CURRENT_SCHEMA.
- Read/write permissions.
- Connection pool behavior.
- Failover/reconnect.
- Query latency and workload service.

### Step 8 — Hand Over to Operations

Register owner/on-call, monitoring, backup/restore expectations, wallet rotation, maintenance notifications, and runbooks.

## 23. Runbook: Wallet Rotation

1. Open the inventory of all clients using the wallet.
2. Identify current wallet, database, environment, authentication mode, and issue date.
3. Confirm rotation behavior and revocation semantics in ADB documentation.
4. Download the new wallet using an approved OCI principal.
5. Store it in the secret manager/versioned secure path.
6. Deploy the new wallet to a canary client.
7. Open new connections and verify database/service/user.
8. Perform a rolling update across remaining app instances.
9. Recycle pools to drain old connections.
10. Monitor login/handshake failures and workload errors.
11. Revoke old credentials per policy.
12. Confirm old wallets are no longer in use and purge copies per retention rules.
13. Record audit evidence and update inventory.

If rotation fails, follow the approved rollback procedure and verify old credentials remain valid before reverting. Never assume an old wallet always remains active after rotation.

## 24. Runbook: Application Cannot Connect to ADB

### Step 1 — Check Service State

Verify ADB resource state and maintenance events in OCI Console/API.

### Step 2 — Check Network

- Proper DNS resolution.
- Routes and firewalls.
- Public access ACL or private endpoint.
- Subnets/NSGs/security lists.
- VPN/FastConnect if on-premises.
- Proxies if required by the environment.

### Step 3 — Check Wallet and TNS

- Wallet matches the exact database and environment.
- Files are complete and uncorrupted.
- TNS_ADMIN points to the right directory.
- Alias exists in `tnsnames.ora`.
- `sqlnet.ora` and wallet paths are valid.
- Service alias matches workload.

### Step 4 — Check Driver and Authentication

- Compatible Oracle JDBC version.
- Correct TLS/mTLS mode.
- Correct database username/password or identity mechanism.
- Wallet password used solely for wallet access.
- Valid certificates and trust chain.

### Step 5 — Check Database Authorization

A successful connection followed by ORA-01031 or rejected queries is a database privilege issue. Inspect grants/roles/schemas rather than altering network policies.

### Step 6 — Check Connection Pool

If fresh connections succeed while requests still fail, inspect pools holding stale connections, validation checks, timeouts, and pool recycling.

Capture the full error chain, timestamp, service alias, driver version, and client environment; redact passwords/tokens/wallet contents before sharing logs.

## 25. Runbook: After Maintenance or Restore

- Confirm ADB resource state.
- Check database services and roles if a standby exists.
- Verify connection pools open fresh physical connections.
- Confirm TNS aliases, wallets, and authentication.
- Run read/write smoke tests.
- Verify schema versions and invalid objects if relevant changes occurred.
- Check scheduled jobs, integrations, and data pipelines.
- Reconcile business data.
- Measure latency, throughput, and error rates.
- Verify backup/recovery settings after restore.
- Update incident/change records and notify owners.

Restoring a database may produce a different resource/endpoint/service identity depending on how it was executed. Never assume applications can reuse the exact old connection string unchanged; re-verify wallets, aliases, IAM/network access, and secrets.

## 26. Hands-On Exercises

Perform within an approved lab/tenancy.

### Exercise 1 — Identify Service Model

Open an ADB lab instance and record deployment model, workload type, region, compute/storage configuration, and network mode.

### Exercise 2 — Distinguish IAM and Database Users

Create an OCI group permitted to read resource metadata under a scoped policy, and a database user with only CREATE SESSION/SELECT on a test table. Demonstrate the two permission layers are independent.

### Exercise 3 — Download and Inspect Wallet

Download a wallet from the lab database, list its files, set least-privilege filesystem permissions, and inspect aliases in `tnsnames.ora`. Never commit wallet files to Git.

### Exercise 4 — TLS/mTLS Connections

Connect using a supported client. Verify TLS mode, database user, and service name. Compare network, TLS, and authentication error behaviors.

### Exercise 5 — JDBC TNS_ADMIN

Configure Oracle JDBC Thin using a TNS alias and TNS_ADMIN. Verify the connection pool creates new connections and queries session identity.

### Exercise 6 — Workload Services

Run the same query workload across provided service aliases. Compare concurrency, latency, execution behavior, and service policies.

### Exercise 7 — Wallet Rotation

Create a canary/rolling rotation procedure in the lab. Confirm new connections use the new wallet and old pools are recycled.

### Exercise 8 — Private Endpoint

If supported by the lab, configure private access, DNS, and routing. Confirm clients outside the allowed network cannot reach the database.

### Exercise 9 — Backup/Restore

Perform a clone/restore per lab service capabilities. Measure duration and verify database identity, users, schemas, and application reconnection.

### Exercise 10 — Maintenance Rehearsal

Track a maintenance event, prepare smoke tests, recycle pools, and record recovery times.

### Exercise 11 — Monitoring

Create an alarm for a service-published metric, assigning owner, severity, and runbook.

### Exercise 12 — Responsibility Matrix

Build a RACI across cloud operations, DBAs, application teams, security, and business owners covering wallets, IAM, database privileges, patching, backups, restores, and incident response.

## 27. Production Readiness Checklist

### Service and Workload

- [ ] Correct ATP/ADW and deployment model selected.
- [ ] Compute/storage sized for workload.
- [ ] Workload service alias intentionally chosen.
- [ ] Capacity/budget/auto-scaling policies established.
- [ ] Region, availability, and DR requirements defined.

### Identity and Access

- [ ] OCI IAM policies follow least privilege.
- [ ] Dedicated database users/roles per application.
- [ ] ADMIN account not used at runtime.
- [ ] Wallet download/rotation permissions have an owner.
- [ ] Database grants and OCI IAM reviewed separately.
- [ ] Secrets and wallets have inventory/owner/expiry tracking.

### Network and Wallets

- [ ] Public ACL or private endpoint matches design.
- [ ] DNS, routes, NSGs/firewalls verified.
- [ ] TLS/mTLS mode determined.
- [ ] Wallet matches exact database/environment.
- [ ] Wallet directory has minimal filesystem permissions.
- [ ] TNS_ADMIN and alias match workload service.
- [ ] Compatible JDBC driver verified.
- [ ] Wallet rotation and revocation rehearsed.

### Operations and Recovery

- [ ] Maintenance notifications have an owner.
- [ ] Application reconnect/retry logic tested.
- [ ] Backup retention and restore capabilities confirmed.
- [ ] RTO/RPO approved by business owner.
- [ ] Restore/clone test evidence recorded.
- [ ] Monitoring, alarms, and escalation active.
- [ ] Cost budgets and usage alerts configured.
- [ ] Auditing and log retention configured.
- [ ] RACI and runbooks have clear owners.

## 28. Core Takeaways

- Autonomous Database is a managed service automating many infrastructure/database tasks; customers remain accountable for data, schemas, privileges, applications, and business recovery.
- Serverless and Dedicated have different deployment/operational models; choose based on isolation, governance, capacity, and cost.
- ATP targets transaction processing; ADW targets analytical workloads; select the appropriate workload service.
- Wallets secure client connections and support mTLS; they are not database users, passwords, IAM policies, or backups.
- TLS authenticates the server; mTLS also authenticates the client at the certificate layer; database authentication/authorization remains a separate layer.
- Wallet ZIPs typically contain wallet files and Oracle Net configs such as `tnsnames.ora`/`sqlnet.ora`; confirm exact contents by wallet type.
- Wallet passwords differ from database passwords and OCI API credentials.
- Protect auto-login wallets with filesystem/secret management; never commit wallets or private keys to source control/images.
- `TNS_ADMIN` points to the client directory holding Oracle Net config/wallets; TNS aliases identify the target service.
- Suffixes like HIGH/MEDIUM/LOW/TP/TPURGENT are common service name examples; use actual aliases provided for your specific database.
- JDBC drivers, TNS aliases, and wallets must be compatible; verify `SERVICE_NAME`/`SESSION_USER` after connecting.
- OCI IAM governs cloud resources; database roles/grants govern data. Having ADB management rights does not mean having table SELECT rights.
- Resource principals and OCI IAM policies allow database resources to call cloud services under granted permissions; never by default.
- Public access ACLs, private endpoints, VCN/NSGs, database network ACLs, and host firewalls govern distinct network flows.
- Replacing wallet files does not automatically update existing pooled connections; follow canary, pool recycle, and credential revocation procedures.
- Oracle manages infrastructure operations per service contract; customers must still track maintenance, test applications, and validate business behavior.
- Automated backups do not replace restore drills; standby/HA does not replace backups against logical errors.
- Scaling can raise both capacity and costs; evaluate bottlenecks, service classes, and budgets.
- Monitoring must cover cloud resources, database workloads, connection pools, wallet lifecycles, and business services.
- Responsibility boundaries must be codified in RACI/runbooks across cloud operations, DBAs, security, application teams, and business owners.

### Oracle Documentation to Consult

- [Oracle Autonomous Database Documentation](https://docs.oracle.com/en/cloud/paas/autonomous-database/) — Service concepts, provisioning, connectivity, operations and lifecycle.
- [Oracle Autonomous Database Serverless Documentation](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/) — Serverless deployment, workload types and administration.
- [Oracle Autonomous Database Dedicated Documentation](https://docs.oracle.com/en/cloud/paas/autonomous-database/dedicated/) — Dedicated infrastructure and Autonomous Container Database concepts.
- [Oracle Autonomous Database Security Guide](https://docs.oracle.com/en/cloud/paas/autonomous-database/security/) — TLS/mTLS, client credentials wallets, network access and security controls.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — JDBC Thin connectivity, Oracle Net configuration and driver behavior.
- [Oracle Cloud Infrastructure IAM Documentation](https://docs.oracle.com/en-us/iaas/Content/Identity/home.htm) — Users, groups, dynamic groups and policies.
- [Oracle Cloud Infrastructure Networking Documentation](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/overview.htm) — VCN, subnet, NSG and private connectivity.
- [Oracle Cloud Infrastructure Monitoring Documentation](https://docs.oracle.com/en-us/iaas/Content/Monitoring/home.htm) — Metrics, alarms and monitoring concepts.

Service capabilities, wallet rotation semantics, service aliases, backup retention, patch windows, authentication modes and customer/provider responsibilities vary by ADB model, region, edition and contract. Confirm the exact database's OCI Console configuration, current service documentation and support terms; test wallet rotation, connection pool recovery, restore and application behavior in a representative non-production environment before production rollout.

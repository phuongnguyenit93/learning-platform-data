# Distinguishing Autonomous Database Management from JDBC Database Connectivity

Oracle Autonomous Database (OCI documentation now displays the name Autonomous AI Database on many newer console pages) is a managed database service. Oracle operates much of the underlying infrastructure, automates backups, patching, and some optimization; the application team still manages OCI permissions, database users, schemas, connections, transactions, and connection pools.

These two sets of tasks operate on two different planes:

- **Service management on the OCI control plane:** provisioning, workload selection, compartment/region, networking configuration, scaling compute/storage, enabling auto scaling, start/stop, backup/restore, cloning, encryption keys, and lifecycle.
- **Database connectivity on the data plane:** the application uses the Oracle JDBC Thin Driver, TNS service name, TLS or mTLS wallet, database username/password or configured database authentication mechanism, and executes SQL through a `DataSource`/connection pool.

OCI IAM policies permit an operator to manage Autonomous Database resources. They do not automatically grant `SELECT`/`INSERT` privileges to the application inside the database. Conversely, a database user with table read privileges cannot automatically scale, stop, restore, or terminate an Autonomous Database on OCI.

This lesson uses `document-service` as the running example. The Platform team provisions the Autonomous Database and configures networking/backups; the DBA creates schemas and users; Spring Boot connects via JDBC, managing `DataSource`, transactions, and pooling. The application receives only the credentials needed for its schema and never uses the `ADMIN` account for runtime business logic.

## 1. Learning Objectives and Architecture

After this lesson, you can:

1. Distinguish the OCI control plane from the database SQL/data plane.
2. Determine which tasks require OCI IAM policies and which require database users/roles/grants.
3. Describe the Autonomous Database lifecycle: provision, scale, auto scaling, stop/start, backup, restore, clone, and terminate.
4. Configure network access via public endpoint, ACLs, or private endpoints.
5. Choose the right workload type and predefined database service name.
6. Distinguish JDBC Thin, TLS, and mTLS; know when a wallet is required.
7. Download, distribute, protect, and rotate instance wallets.
8. Configure Oracle JDBC URLs, TNS aliases, and `TNS_ADMIN`.
9. Configure Spring Boot `DataSource` with HikariCP or Oracle UCP.
10. Size connection pools appropriately for replica counts, session budgets, and service concurrency.
11. Manage database users, passwords, secrets, schema migrations, and transactions.
12. Test connectivity, permissions, TLS, pool exhaustion, failover, and common errors.

~~~mermaid
flowchart TD
    subgraph CP["OCI Control Plane"]
        A["OCI Console / API / Terraform"]
        B["OCI IAM policy"]
        C["Autonomous Database lifecycle"]
        D["Network, ECPU, storage, backup, key"]
        A --> B
        B --> C
        C --> D
    end

    subgraph DP["Database Data Plane"]
        E["Spring Boot application"]
        F["Oracle JDBC Thin Driver"]
        G["TLS / mTLS + TNS service"]
        H["Autonomous Database"]
        I["DB user / role / schema / SQL grants"]
        E --> F --> G --> H
        I --> H
    end

    D -. "Provisioned endpoint and connection details" .-> G
    B -. "Does not grant SQL table privileges" .-> I
~~~

**OCI IAM governs who can manage the service. Database grants govern what a connected user can do inside the database. JDBC is the application's connection path to the database, not an OCI service management API.**

## 2. Two Management Planes to Keep Separate

### 2.1. OCI Control Plane

The control plane manages Autonomous Database resources within a tenancy/compartment. Typical operations:

- Provisioning or terminating a database.
- Changing display name, workload type, or compartment.
- Scaling ECPU and storage.
- Enabling/disabling compute auto scaling or storage auto scaling.
- Starting, stopping, restarting, and scheduling start/stop.
- Configuring network access, ACLs, private endpoints, and NSGs.
- Configuring customer-managed encryption keys.
- Viewing backups, performing point-in-time restores, and cloning databases.
- Configuring disaster recovery/Autonomous Data Guard.
- Viewing maintenance, lifecycle events, and service metrics.

These operations are executed via the OCI Console, OCI REST API, OCI SDK, OCI CLI, or Terraform. Operators need IAM policies for Autonomous Database and corresponding backup resources.

### 2.2. Database Data Plane

The data plane covers operations inside the database once a client connects successfully:

- Logging in with a database user or configured database authentication mechanism.
- Creating schemas, tables, indexes, sequences, views, and procedures.
- Granting roles and object privileges.
- Running `SELECT`/`INSERT`/`UPDATE`/`DELETE`.
- Managing transactions, isolation, and locking.
- Running migrations via Flyway/Liquibase.
- Monitoring sessions, SQL, execution plans, and database waits.
- Managing application connection pools.

These operations require database credentials and SQL privileges. A user permitted to connect over JDBC may have no permission to create users, change service configuration, or restore the database.

### 2.3. Comparing Permissions

| Task | Plane | Required Permission |
| --- | --- | --- |
| View Autonomous Database in Console | OCI control plane | OCI IAM `inspect` |
| Scale ECPU/storage | OCI control plane | OCI IAM `use` per policy |
| Stop/start database | OCI control plane | OCI IAM `use` per policy |
| Restore from backup | OCI control plane | OCI IAM `use` Autonomous Database and `read` backup |
| Terminate database | OCI control plane | OCI IAM `manage` Autonomous Database |
| Create schema/user | Database data plane | Database account with matching SQL privileges |
| `SELECT` contracts table | Database data plane | Database user with `SELECT` object privilege |
| Run Flyway migrations | Database data plane | Migration account with required DDL privileges |
| Open JDBC connection | Database data plane | Network reachability, TLS/mTLS, and database authentication |
| Modify IAM policies | OCI control plane | OCI IAM policy administration |

Reference OCI IAM policy for operators:

~~~text
Allow group DBOperators to inspect autonomous-databases in compartment Production
Allow group DBOperators to use autonomous-databases in compartment Production
Allow group DBOperators to read autonomous-backups in compartment Production
~~~

These statements illustrate view, operational, and backup-read permissions. Restoring requires `use` on Autonomous Databases alongside `read` on Autonomous Backups per the permission mapping. Terminating a database is destructive and requires `manage autonomous-databases`; never grant this to application teams.

### 2.4. Database `ADMIN` Is Not an OCI Administrator

`ADMIN` is a database user with database administrative privileges under the Autonomous Database model. `ADMIN` is not automatically an OCI tenancy administrator and does not replace OCI IAM users/groups.

Similarly, an OCI administrator cannot necessarily log in via SQL without database credentials or an appropriate database authentication mechanism.

Never use `ADMIN` as Spring Boot's runtime user. Create separate schema-owner and application users, granting each role only the privileges it needs.

## 3. Provisioning and Autonomous Database Lifecycle Management

### 3.1. Provisioning

When creating an Autonomous Database, the operator must specify:

- Compartment and region.
- Database display name and database name.
- Workload type, e.g., Transaction Processing or Data Warehouse.
- Compute model and ECPU count.
- Storage capacity.
- Compute auto scaling and storage auto scaling.
- Network access options.
- Encryption key options.
- Backup/retention options.
- License model and service options.

UI labels and certain options can vary by workload, region, and compute model. Follow the active provisioning page and documentation for the specific database edition being deployed.

### 3.2. ECPU and OCPU

Autonomous AI Database documentation currently uses ECPU as the standard compute model; OCPU is a legacy model that may still appear on older resources. Do not copy ECPU counts directly to OCPU or vice versa, as units, concurrency, and billing differ.

When scaling:

- Check current ECPU allocation and tenancy limits.
- Evaluate workload CPU, I/O, concurrency, and latency.
- Check which connection service is in use.
- Check connection pool sizes and total replica counts.
- Perform changes during an appropriate maintenance/change window.
- Monitor before/after metrics to verify improvement.

### 3.3. Compute Auto Scaling

Compute auto scaling allows the database to consume additional CPU/I/O when workload demand increases, within service limits. Current documentation states compute auto scaling can burst up to roughly three times the base CPU allocation under supported conditions.

Auto scaling does not replace capacity planning. It can increase consumption and cost during load spikes. Track allocated ECPU, utilization, latency, and concurrency to understand actual scaling behavior.

### 3.4. Storage Auto Scaling

Storage auto scaling allows the database to expand usable storage within configured limits. Current documentation states it can expand up to three times the reserved base storage when enabled.

Monitor storage usage and data growth rates. Auto scaling is not a retention policy: applications must still purge or archive data according to business lifecycle rules.

### 3.5. Stop, Start, and Restart

Stop/start are service lifecycle operations, not JDBC commands.

Before stopping:

1. Stop accepting new requests that require the database.
2. Drain background workers and active transactions.
3. Wait for transactions to complete or roll back per plan.
4. Close connection pools or place the application into maintenance mode.
5. Execute stop on OCI.
6. Verify service status and notify application teams.

When starting:

1. Wait until Autonomous Database status returns to `Available`.
2. Verify network endpoints and service names.
3. Confirm database users and wallets/certificates remain valid.
4. Start application instances or refill connection pools.
5. Run a lightweight query health check.
6. Monitor connection errors and request latency.

Applications should not retry connections indefinitely while the database is stopped. Use bounded backoff and proper readiness states.

### 3.6. Backup, Restore, and Clone

Autonomous Database includes automatic backups and optional long-term backups per service/workload. Oracle-managed backups are immutable according to current documentation.

Concepts:

- **Automatic backup:** supports recovery within the configured retention window.
- **Point-in-time recovery:** restores the database to a timestamp within the supported backup/recovery range.
- **Long-term backup:** retains backups according to chosen schedules and retention periods.
- **Clone:** creates a new database from the current source or a selected backup.
- **Restore:** recovers the database back to a chosen point in time.

Restoring alters current data state. Before executing, verify the target database, timestamp, business impact, backup availability, KMS key, and data verification plan. Use clones for drills/investigations when the existing database must remain intact.

Database backups do not automatically include files stored outside the database in Object Storage, such as external table files. If the system uses external data, back up and restore those files through a separate workflow.

### 3.7. Lifecycle Events

OCI emits lifecycle events for start, stop, restart, backup, restore, auto scaling, updates, wallet rotation, and termination. Use Events/Notifications to send alerts to operations.

Never treat a successful API request as proof the database is already ready. Watch operation/event status and verify real connections before returning traffic.

## 4. Network Access for Autonomous Database

### 4.1. Three Common Access Types

| Network Type | Characteristics | Use Case |
| --- | --- | --- |
| Secure access from everywhere | Public endpoint; unrestricted by IP if no ACL is set | Controlled dev/demo; evaluate risk carefully |
| Secure access from allowed IPs and VCNs only | Public endpoint restricted by source ACL | Workloads with known egress IPs/VCNs |
| Private endpoint access only | Private IP/hostname inside a VCN; no public internet access | Production private networks |

All three modes use TLS/certificate-secured connections. Network access controls govern which clients can reach the endpoint; they do not grant SQL privileges.

### 4.2. ACLs

ACLs restrict which IPs or VCNs may connect to the database public endpoint. If an application runs in a private subnet behind a NAT Gateway, the source seen by the database may be the NAT Gateway's public IP; configure the exact source CIDR accordingly.

After updating ACLs, verify:

- The workload's public egress IP.
- VCN/subnet CIDRs.
- NAT Gateway or Service Gateway paths.
- NSGs/security lists and route tables.
- DNS resolution and TCP connectivity to the port in the connection descriptor.

Never open `0.0.0.0/0` just to troubleshoot a production connectivity error.

### 4.3. Private Endpoints

A private endpoint places the database inside a designated VCN. The application must have a network path to the private endpoint via configured subnets/peering/on-premises connectivity.

Verify:

- Correct VCN and subnet.
- DNS hostname resolves to the private IP.
- NSG ingress/egress rules for the database listener.
- Security lists and route tables.
- VCN peering or DRG if the app resides in another VCN.
- Firewalls/Network Security Appliances.
- Port specified in the connection string.

A private endpoint does not replace TLS or database authentication.

### 4.4. Connectivity Testing

Before debugging JDBC, verify the network layer:

1. DNS lookup of the hostname from the exact container/pod/VM.
2. TCP connect test to the port in the descriptor.
3. Verify routes and firewalls.
4. Check ACLs or private endpoint rules.
5. Ensure the client is not routed through a misconfigured proxy.
6. Once network connectivity is clear, inspect TLS, wallets, and database login.

`ping` does not prove the Oracle listener is reachable. Use a TCP connection test on the exact host and port.

## 5. JDBC Thin Driver and Connection Strings

### 5.1. JDBC Thin

The Oracle JDBC Thin Driver is pure Java, speaks Oracle Net over TCP/TLS, and requires no native Oracle Client libraries for standard connections. It is the standard choice for Spring Boot.

Maven dependency:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc17</artifactId>
    <version>ORACLE_JDBC_VERSION_COMPATIBLE_WITH_JDK</version>
</dependency>
~~~

Replace the illustrative version with a JDBC driver version certified for your JDK, Spring Boot, and Oracle Database versions. Oracle publishes artifacts such as `ojdbc8`, `ojdbc11`, and `ojdbc17`; choose the artifact matching your JDK/JDBC API compatibility. Do not stick to an outdated driver just because an old blog sample still compiles.

If using Oracle UCP, add the UCP dependency from the matching compatible release family/version:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ucp</artifactId>
    <version>ORACLE_JDBC_VERSION_COMPATIBLE_WITH_JDK</version>
</dependency>
~~~

Manage versions via dependency management/version catalogs. Never arbitrarily mix `ojdbc`, `ucp`, and companion security jars from different releases.

### 5.2. Service Names and TNS Aliases

Every Autonomous Database provides predefined database service names. TNS aliases and connect descriptors appear in the OCI Console or inside `tnsnames.ora` in the wallet.

Aliases typically carry suffixes like:

~~~text
database_tpurgent
database_tp
database_high
database_medium
database_low
~~~

Exact names depend on the database. Do not guess aliases solely from the display name; use the connection strings generated for the instance.

### 5.3. Choosing a Database Service by Workload

| Service | General Purpose | Characteristics |
| --- | --- | --- |
| `TPURGENT` | Extremely time-sensitive transactions | Highest priority; supports manual parallelism |
| `TP` | Typical OLTP | No automatic parallelism by default for statements |
| `HIGH` | Low-concurrency reporting/analytics | Parallel execution, lower concurrent statement limit |
| `MEDIUM` | Analytics/batch | Parallel execution and configured concurrency |
| `LOW` | Low-priority reporting/batch | No parallelism by default |

For Spring Boot business APIs with short transactions, start by testing the `TP` service. Reserve `TPURGENT` for flows that genuinely demand top priority and have been resource-evaluated. `MEDIUM` suits batch/analytics; `HIGH` suits low-user analytical workloads; `LOW` suits low-priority background tasks.

Concurrency limits and degrees of parallelism depend on ECPU/OCPU, auto scaling, workload, and current configuration. Never copy fixed numbers from another environment. Monitor database service metrics and consult service-name documentation for your instance's compute model.

Do not merely alter a consumer group on one connection and assume it equals connecting to a different service. Service names may configure additional session/resource-manager attributes. Use the right service alias or `CS_SESSION.SWITCH_SERVICE` API when the use case and privileges permit.

### 5.4. JDBC URL with a TNS Alias

For wallet-based connections with a JDBC Thin Driver supporting `TNS_ADMIN` in the URL:

~~~text
jdbc:oracle:thin:@database_tp?TNS_ADMIN=/run/secrets/adb-wallet
~~~

Where:

- `database_tp` is an actual TNS alias present in `tnsnames.ora`.
- `TNS_ADMIN` points to the directory containing `tnsnames.ora`, `sqlnet.ora`, `ojdbc.properties`, and wallet files.
- The path must exist and be readable by the Spring Boot process.
- The alias must match the service selected on the database connection page.

JDBC driver 18.3 and later support passing `TNS_ADMIN` in the URL. Older drivers may require system properties or connection properties per driver documentation; prefer currently supported drivers.

### 5.5. Direct JDBC URL

For walletless TLS, the OCI Console provides a connect descriptor with `TCPS` protocol, host, port, `service_name`, and server DN matching. Place that descriptor after the prefix:

~~~text
jdbc:oracle:thin:@(description=(retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1521)(host=adb.example.oraclecloud.com))(connect_data=(service_name=database_tp.adb.oraclecloud.com))(security=(ssl_server_dn_match=yes)))
~~~

This is a structural example. Host, port, and `service_name` must come from the database's own TLS connection string. TLS may use port 1521 or 1522 depending on the issued descriptor; mTLS commonly uses port 1522. Never manually alter ports in connect descriptors.

## 6. TLS, mTLS, and Wallets

### 6.1. TLS

TLS encrypts the connection and verifies server identity via a certificate chain. With walletless TLS:

- The database must allow TLS connections.
- The JDBC Thin Driver/JDK must meet the service's TLS requirements.
- The application uses a database username/password or configured database authentication mechanism.
- The client verifies the server certificate/hostname.
- Downloading an Oracle wallet is not required for JDBC Thin in supported TLS configurations.

TLS does not mean the connection is public or bypasses ACLs/private endpoints. Network access must still be permitted.

### 6.2. Mutual TLS (mTLS)

mTLS performs two-way authentication: the client verifies the server and the database verifies the client certificate. For Autonomous Database, a wallet or JKS client credentials are used for mTLS.

mTLS requires:

- Wallet/client credentials downloaded for the database.
- TNS alias/connect descriptor.
- Compatible JDBC driver and security configuration.
- Database username/password or suitable database auth mechanism.
- Network path to the TCPS endpoint.

If the database enforces mTLS, walletless TLS will fail to connect. If the database permits both TLS and mTLS, the application can choose either via the connection descriptor.

### 6.3. When Is a Wallet Required?

| Database Configuration | JDBC Thin Wallet |
| --- | --- |
| mTLS Required | Mandatory |
| TLS allowed, JDBC Thin/JDK meet requirements | Walletless connection possible |
| Both mTLS and TLS allowed | Can choose wallet/mTLS or walletless/TLS |
| Older driver/JDK or specialized client mode | Check corresponding documentation |

Do not assume every Autonomous Database requires a wallet or that every TLS connection is walletless. mTLS enforcement, network setup, JDBC driver, and JDK determine the approach.

### 6.4. Wallet Contents

An instance wallet download typically includes:

| File | Role |
| --- | --- |
| `cwallet.sso` | Auto-login wallet |
| `ewallet.p12` | PKCS12 wallet protected by a wallet password |
| `tnsnames.ora` | TNS aliases and connect descriptors |
| `sqlnet.ora` | SQL*Net client configuration |
| `ojdbc.properties` | JDBC wallet connection properties |
| `keystore.jks` | Java keystore |
| `truststore.jks` | Java truststore |
| `README` | Wallet/expiration info and instructions |

A wallet is not a public configuration file. Anyone holding the wallet and valid database privileges can use the client certificate to connect. Protect the entire wallet directory like a credential:

- Store it in a secret manager or secret volume.
- Mount it read-only into application containers.
- Restrict file permissions, e.g., `600` on Linux for sensitive files.
- Never commit it to Git, build artifacts, Docker images, or logs.
- Never send it over unencrypted email/chat.
- Distribute wallet passwords over a separate channel if required.
- Use instance wallets for a single database; regional wallets span multiple databases in a region and should be reserved strictly for appropriate administrative tasks.

### 6.5. Wallet Rotation

Wallet rotation replaces client certificate keys, not database user passwords.

OCI supports:
- Immediate rotation: old client certificate keys are invalidated immediately; existing database connections/sessions may be terminated. Applications must download and apply the new wallet before reconnecting.
- Grace-period rotation: for 1 to 72 hours, both old and new wallets remain valid; once the period expires, the old wallet is invalidated. This supports planned cutovers. Some Always Free databases support only immediate rotation.

Recommended workflow:

1. Identify all applications, batch jobs, and tools using the instance wallet.
2. Schedule a rotation window and notify owners.
3. Load the new wallet into a new secret store/volume version.
4. Deploy a canary using the new wallet.
5. Verify JDBC connections and business queries.
6. Cut all instances/pods over to the new wallet.
7. Reload/restart pools so old sessions are dropped.
8. End the grace period or execute immediate rotation per incident plans.
9. Confirm the old wallet can no longer connect.
10. Record audit logs and delete old distributions per policy.

If a wallet is compromised, prioritize containment. Do not extend a grace period for deployment convenience when an attacker could still use the old certificate.

### 6.6. Wallet Rotation Differs from Password Rotation

There are two distinct secrets:

- Wallet/client certificate: authenticates the client in mTLS.
- Database user password: authenticates the database user via username/password.

Rotating the wallet does not change database user passwords. Changing a database user password does not rotate client certificates. Maintain separate schedules and procedures for each.

## 7. Database Users, Roles, and Schemas

### 7.1. Creating an Application User

Use `ADMIN` to create the initial schema owner/application user following DBA procedures, then grant least privilege. Illustrative example:

~~~sql
CREATE USER DOC_APP IDENTIFIED BY "REPLACE_WITH_SECRET_FROM_APPROVED_CHANNEL";

GRANT CREATE SESSION TO DOC_APP;

GRANT SELECT, INSERT, UPDATE, DELETE
ON DOC_OWNER.DOCUMENTS TO DOC_APP;

GRANT SELECT, INSERT, UPDATE, DELETE
ON DOC_OWNER.DOCUMENT_AUDIT TO DOC_APP;
~~~

Exact syntax and DDL privileges depend on schema ownership and application requirements. Never place real passwords into committed migrations. In production, use passwords generated and distributed via a secret manager or organization-approved database authentication mechanism.

### 7.2. Schema Owner vs. Runtime User

Good separation model:

- `DOC_OWNER` owns tables, indexes, sequences, and migration objects.
- `DOC_APP` holds business-operation privileges on granted objects.
- `DOC_MIGRATION` is a separate account used in migration pipelines when DDL is needed.
- `ADMIN` is reserved strictly for controlled administrative tasks.

Separating the migration user from the runtime user limits damage if the application is compromised.

### 7.3. OCI IAM and Database Users Are Not Automatically Linked

An OCI dynamic group or instance principal does not automatically become a database user. JDBC by default still authenticates a database user. If you want OCI IAM token database authentication or another external identity mechanism, configure it explicitly per Oracle documentation and database policies; never assume an OCI IAM policy grants SQL privileges directly.

## 8. Configuring Spring Boot `DataSource`

### 8.1. Dependencies

For Spring Boot JDBC/JPA, add the appropriate starters:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc17</artifactId>
    <version>ORACLE_JDBC_VERSION_COMPATIBLE_WITH_JDK</version>
</dependency>
~~~

If using Spring Data JPA, replace or supplement with `spring-boot-starter-data-jpa` per project architecture. Spring Boot auto-configures a `DataSource` when it finds a JDBC driver and compatible URL.

Spring Boot prefers HikariCP when present on the classpath; JDBC and JPA starters normally pull HikariCP in. Verify Spring Boot/JDK and driver compatibility before pinning versions.

### 8.2. `application.yml` Configuration for mTLS Wallet

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@database_tp?TNS_ADMIN=/run/secrets/adb-wallet
    username: DOC_APP
    password: INJECT_FROM_SECRET_MANAGER
    driver-class-name: oracle.jdbc.OracleDriver
    hikari:
      pool-name: document-db-pool
      minimum-idle: 2
      maximum-pool-size: 12
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1500000
      keepalive-time: 300000
~~~

Pool values are starting baselines for load testing, not universal defaults. Username/password must be injected from a secret manager or external configuration. Never store real credentials in `application.yml`.

The wallet path must be mounted into the runtime container/VM. Ensure the process has read permissions and `TNS_ADMIN` points to the directory containing `tnsnames.ora`.

### 8.3. Walletless TLS Configuration

If the database permits TLS and the client/JDK satisfy requirements, use the TLS connection string from the OCI Console:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@(description=(retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1521)(host=adb.example.oraclecloud.com))(connect_data=(service_name=database_tp.adb.oraclecloud.com))(security=(ssl_server_dn_match=yes)))
    username: DOC_APP
    password: INJECT_FROM_SECRET_MANAGER
    driver-class-name: oracle.jdbc.OracleDriver
~~~

This is an example; use the exact host/port/service/descriptor provided by the OCI Console. Never disable server DN matching to work around certificate errors. Fix the hostname, trust chain, JDK, or connection descriptor instead.

### 8.4. Driver Class and URL

Spring Boot normally infers the driver from the JDBC URL. For Oracle JDBC Thin:

- URL begins with `jdbc:oracle:thin:@`
- Driver class is `oracle.jdbc.OracleDriver`.
- Service name/TNS alias must be accurate.
- For wallets, `TNS_ADMIN` must point to the exact directory.
- For direct TLS descriptors, host, port, and service name must match.

Do not use a `jdbc:oracle:oci` URL unless intentionally using the OCI native driver with Oracle Client libraries installed.

### 8.5. Externalized Configuration

Production configuration should externalize:

- JDBC URL/service alias.
- Database username.
- Database password or token.
- Wallet directory/secret volume.
- Pool settings.
- Connection/read timeouts.
- Environment-specific profiles.

Inject values via environment variables, Kubernetes Secrets/CSI secret volumes, or OCI Vault integration. Never log `DataSourceProperties`, JDBC URLs containing tokens/secrets, sensitive wallet paths, or passwords.

## 9. HikariCP and Oracle UCP

### 9.1. What Does a Connection Pool Do?

Opening a TCP/TLS connection and database session on every request is expensive. A connection pool keeps a ready set of connections that the application borrows and returns over time.

Flow:

~~~mermaid
sequenceDiagram
    participant API as Spring request
    participant Pool as HikariCP / UCP
    participant DB as Autonomous Database
    API->>Pool: getConnection()
    Pool-->>API: borrow connection
    API->>DB: execute SQL / transaction
    DB-->>API: result
    API->>Pool: close() returns connection
    Note over Pool: Connection is retained for reuse
~~~

In Spring JDBC/JPA applications, never hold a global connection manually or share one `Connection` across multiple requests. The transaction manager and pool govern connection lifecycles.

### 9.2. HikariCP

HikariCP is a solid default for many Spring Boot applications:

- Lightweight pool with strong performance.
- Simple configuration.
- Direct Spring Boot auto-configuration support.
- Metrics for active, idle, pending, and timeouts.
- Fits standard JDBC `DataSource` requirements.

Example:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: document-db-pool
      minimum-idle: 2
      maximum-pool-size: 12
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1500000
~~~

Do not blindly copy `12` to every deployment. Compute total connections across all pods/replicas and jobs. With 10 pods at max 12 each, the application can open up to 120 connections before counting migrations, admin tools, or monitoring.

### 9.3. Oracle UCP

Universal Connection Pool (UCP) is Oracle's connection pool, offering Oracle-specific integrations such as connection labeling, Fast Connection Failover/ONS, runtime load balancing, and HA features when supported by the database/service/network.

Choose UCP when you need Oracle-specific capabilities and your operations team understands UCP configuration and monitoring. UCP does not grant database privileges on its own or fix an invalid JDBC URL.

Illustrative programmatic configuration example:

~~~java
import oracle.ucp.jdbc.PoolDataSource;
import oracle.ucp.jdbc.PoolDataSourceFactory;

public PoolDataSource createPool(
        String jdbcUrl,
        String username,
        String password) throws Exception {

    PoolDataSource pool =
            PoolDataSourceFactory.getPoolDataSource();

    pool.setConnectionFactoryClassName(
            "oracle.jdbc.pool.OracleDataSource");
    pool.setURL(jdbcUrl);
    pool.setUser(username);
    pool.setPassword(password);

    pool.setInitialPoolSize(2);
    pool.setMinPoolSize(2);
    pool.setMaxPoolSize(12);
    pool.setValidateConnectionOnBorrow(true);
    pool.setConnectionValidationTimeout(5);

    return pool;
}
~~~

This is a UCP API example. When integrating with Spring, register `PoolDataSource` as the `DataSource` bean and configure lifecycle/closing cleanly. Do not wrap UCP inside a Hikari pool unintentionally, as two stacked pool layers complicate sizing and diagnosis.

### 9.4. Hikari or UCP?

| Criterion | HikariCP | Oracle UCP |
| --- | --- | --- |
| Spring Boot default | Yes, when on classpath | Configurable explicitly |
| Target | General-purpose JDBC pool | Oracle-specific pool |
| Configuration | Simple | Rich Oracle features |
| HA integration | Depends on driver/network/pool | Supports Oracle features like FCF/RLB when environment supports them |
| When to choose | Most CRUD/OLTP services | Need Oracle HA/labeling or specific UCP capabilities |
| Caution | Must size and monitor carefully | Must understand UCP timeouts/validation/ONS/driver compatibility |

### 9.5. Pool Sizing and Database Service Concurrency

Pool max size is the maximum connections per process. It does not equal the number of SQL statements the database can execute concurrently.

Autonomous Database service names have distinct resource shares, concurrency limits, and parallelism settings. For example, `HIGH`/`MEDIUM` can queue statements once concurrency is reached; raising Hikari connections does not necessarily increase throughput.

Size pools based on:

- Maximum replica count under autoscaling.
- Connections per replica.
- Background workers, scheduled jobs, and migrations.
- Database session limits.
- Service concurrency and workload.
- Connections reserved for DBAs/monitoring.
- How long connections are held in transactions.

Sanity-check formula:

~~~text
Total application connections
  = max replicas x max pool size per replica
    + background workers
    + migration/admin clients
~~~

Keep the total below verified database limits and monitor pool pending threads and connection timeouts. Avoid long-running transactions or making HTTP calls while holding a JDBC connection.

## 10. Transactions, JPA, and Migrations

### 10.1. Spring Transactions

Use the Spring transaction manager to guarantee commit/rollback:

~~~java
@Service
public class DocumentRepositoryService {

    private final JdbcTemplate jdbcTemplate;

    public DocumentRepositoryService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void registerDocument(
            String documentId,
            String objectKey) {

        jdbcTemplate.update(
                "insert into DOC_OWNER.DOCUMENTS (DOCUMENT_ID, OBJECT_KEY) values (?, ?)",
                documentId,
                objectKey);
    }
}
~~~

Use bind parameters instead of concatenating SQL strings. Never hold connections manually across multiple requests. Long transactions can exhaust pools even at modest request rates.

### 10.2. Isolation and Locking

Oracle Database has specific transaction semantics. Choose isolation levels fitting the use case; do not raise isolation system-wide if only a few flows require strong locking.

- Use optimistic locking/version columns for concurrent updates.
- Use short-scoped `SELECT FOR UPDATE` when serialization is required.
- Design idempotency for request retries.
- Never keep a database transaction open while calling another cloud service.
- Use outbox/sagas when coordinating DB changes with Object Storage or messaging.

### 10.3. Flyway/Liquibase

Schema migration is a database data-plane operation, not an OCI resource update. Use a dedicated migration user with appropriate DDL privileges.

Recommendations:

- Run migrations in pipeline/release steps.
- Ensure the runtime user lacks `CREATE USER`/`CREATE TABLE` privileges unless needed.
- Commit migration scripts alongside source code.
- Back up or clone before high-risk changes.
- Test migrations on a clone or staging environment.
- Do not run DDL arbitrarily on startup of every application replica without lock/concurrency control.

## 11. Credential and Secret Management

### 11.1. Database Passwords

Never hard-code database passwords in source code, Dockerfiles, images, Helm charts, or logs. Store them in OCI Vault or an approved secret store and inject them at runtime.

Database password rotation requires coordination:

1. Create a new secret version.
2. Change the database user's password using DBA/secret-based credential procedures.
3. Update the secret version consumed by the application.
4. Refresh/restart the connection pool to open new connections.
5. Verify login with the new password.
6. Revoke the old password after any configured overlap/rollover window.
7. Monitor authentication failures.

Creating a new version in Vault alone does not change the database user's password. The database user password must be updated inside the database via the proper mechanism.

### 11.2. Wallets and Database Passwords

Wallet client credentials and database user passwords are two separate layers. When an mTLS wallet rotates, old client certificates are invalidated per policy; the database password does not change. When a database user password rotates, wallet certificates do not change.

Maintain an inventory tracking:
- Instance wallet version.
- Database username.
- Secret version/password expiry.
- JDBC service alias.
- Owner/consumer.
- Pool refresh/deployment procedure.
- Revocation/rotation dates.

### 11.3. Database Least Privilege

- Never use `ADMIN` for applications.
- Separate schema owner and runtime user.
- Grant object privileges specifically; never grant `DBA` roles.
- Restrict migration privileges to pipelines.
- Separate read-only users for reporting.
- Rotate passwords and wallets per policy.
- Revoke users/roles when services are decommissioned.

## 12. Observability and Connection Operations

### 12.1. What the Application Should Monitor

Monitor the pool:

- Active connections.
- Idle connections.
- Pending threads.
- Connection acquisition latency.
- Connection timeouts.
- Connection creation/validation failures.
- Usage duration and transaction duration.

Monitor the database:

- CPU/ECPU utilization.
- Session counts.
- SQL latency.
- Wait events.
- Service concurrency/queuing.
- Storage utilization.
- Backup/restore lifecycle.
- Network errors.

Never log usernames/passwords, wallet contents, connect descriptors containing secrets, or sensitive SQL bind values.

### 12.2. Health Checks

Liveness probes should only verify the process is alive; never restart every pod simply because the database is temporarily unreachable.

Readiness probes can run a lightweight query such as:

~~~sql
SELECT 1 FROM DUAL
~~~

Health checks must use short timeouts and avoid opening new connections continuously if the pool is already saturated. Separate readiness dependencies from liveness to prevent restart storms.

### 12.3. OCI Lifecycle Events and Application Alerts

Watch events for start/stop/restart/restore/backup/wallet rotation/maintenance. When the database transitions to `Updating` or `Stopping`, the application may encounter connection failures. Use alerts and runbooks to drain traffic or dial back retries.

### 12.4. Connection Pools After Maintenance/Failover

After restarts, wallet rotations, or network changes:

- Verify the endpoint remains accurate.
- Ensure the pool evicts stale/dead connections.
- Configure appropriate validation/retry settings.
- Prevent opening too many connections simultaneously (connection storms).
- Ramp traffic back up gradually after health checks pass.
- Monitor session counts and connection acquisition latency.

## 13. Troubleshooting Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `ORA-12154` | Cannot resolve TNS alias | Check `TNS_ADMIN`, `tnsnames.ora`, and alias |
| `ORA-12514` | Listener does not recognize service name | Use exact service from OCI Console/`tnsnames.ora` |
| `ORA-01017` | Wrong username/password or unrefreshed secret | Verify DB user, password, and secret version |
| `ORA-28000` | Database account is locked | DBA checks account status and lock policy |
| `ORA-29024` | Certificate validation failed | Check wallet/truststore, hostname, certificate chain, and system clock |
| Network Adapter / connect timeout | DNS, ACL, NSG, route, port, or private endpoint | Check network path from exact pod/VM to endpoint |
| 403 on stop/scale/restore | OCI IAM policy lacks permission | Check control-plane policy and compartment |
| SQL permission denied | Database user lacks object/system privilege | DBA grants exact SQL privilege |
| Hikari pool timeout | Pool exhausted, slow query/transaction, or DB rejecting connections | Check active/pending, SQL latency, pool size, and session limits |
| `ORA-03113`/`ORA-03135` | Connection dropped or database/network lifecycle event | Check events, network, stale pool connections, and server alerts |
| Connects fine yet queries are slow | Wrong service chosen or missing plan/index | Check `TP`/`HIGH`/`MEDIUM`/`LOW`, SQL Monitor, and execution plans |
| Old wallet fails after rotation | Old certificate invalidated | Download new wallet, update volume, and recycle pool |
| TLS JDBC URL hostname error | Host/service descriptor mismatch or DN match failure | Use exact descriptor from Console; do not disable DN matching |
| Pool opens excessive connections | Each pod has its own pool and autoscaling adds replicas | Calculate total max pool across replicas vs. database budget |

### 13.1. Diagnosing in Order

1. **Control plane:** Is the database `Available`, or is a lifecycle operation running?
2. **Network:** DNS, routes, ACL/private endpoint, NSG, and TCP port.
3. **TLS:** mTLS/TLS mode, wallet, certificate chain, hostname matching.
4. **JDBC:** driver version, URL, TNS alias, `TNS_ADMIN`, and service name.
5. **Authentication:** database username/password or token.
6. **Authorization:** SQL roles/grants.
7. **Pool:** max size, timeouts, stale connections, pending threads.
8. **SQL:** query plans, locks, waits, and service concurrency.

Never grant `ADMIN` privileges or open a public endpoint just to experiment with a fix. Isolate the failing layer and apply the smallest scoped fix.

## 14. Integration Testing

### 14.1. Verifying JDBC Configuration

- Does the URL match the right alias/descriptor?
- Is the driver compatible with the JDK?
- Does `TNS_ADMIN` point to the exact wallet directory?
- Are all wallet files present and readable by the process?
- Does TLS/mTLS mode match database settings?
- Does the service name match the workload?
- Are username/password injected properly?

### 14.2. Smoke Test

After connecting, verify the database and service:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME') AS DB_NAME,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS SERVICE_NAME,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS SESSION_USER
FROM DUAL
~~~

Confirm the session uses the intended database, service name, and database user. Never print sensitive info into production logs.

### 14.3. Integration Tests

Use a dedicated test/staging Autonomous Database or managed clone:

1. Initialize `DataSource`.
2. Borrow a connection from the pool.
3. Execute `SELECT 1 FROM DUAL`.
4. Insert/update/select/rollback inside a transaction.
5. Verify the runtime user cannot access out-of-scope schemas.
6. Verify the migration user can run migrations while the runtime user lacks unnecessary DDL privileges.
7. Test pool close/reconnect.
8. Test TLS or mTLS.
9. Test database restart/maintenance recovery.
10. Test pool sizing under concurrency.

### 14.4. Negative Tests

- Wrong password must fail authentication.
- Old wallet after immediate rotation must be rejected.
- User without `SELECT` grant must be denied table queries.
- App network outside ACL/private endpoint must fail to connect.
- OCI user without IAM policy must be unable to scale/stop the database.
- Nonexistent service name must fail with a clear error.
- Load exceeding pool max must wait/time out cleanly rather than opening unbounded connections.

### 14.5. Testing Restore and DR

- Create backups per policy.
- Restore/clone into a test environment.
- Verify database users, schemas, data, and connection services.
- Verify wallet/endpoint/network config against the new database.
- Verify the KMS key remains accessible.
- Confirm the application connects via `DataSource`.
- Verify external table/Object Storage data if the system uses it.

Never run a destructive restore on production solely to test a runbook.

## 15. Comprehensive Practice Exercise

You are tasked with deploying `document-service` on OCI. The Autonomous Database resides in compartment `AppData`, and the application runs on Compute/OKE in `AppRuntime`. The DBA team manages schemas, the Platform team manages lifecycle, and Spring Boot only reads/writes business tables.

**Tasks:**

1. Provision an Autonomous Database in the approved compartment/region.
2. Choose Transaction Processing workload and appropriate ECPU.
3. Configure a private endpoint or ACL matching the network architecture.
4. Enable backups/retention and define restore/clone procedures.
5. Create a dedicated OCI IAM policy for the `DBOperators` group.
6. Create a database schema owner and runtime user with least-privilege grants.
7. Select the `TP` service for OLTP flows and verify the alias from connection details.
8. Download the instance wallet if the database requires mTLS; protect the wallet in a secret volume.
9. Configure the JDBC Thin Driver and Spring Boot `DataSource`.
10. Configure HikariCP and calculate total connections across all replicas.
11. Implement health checks and a SQL smoke test.
12. Design independent password rotation and wallet rotation workflows.
13. Test control-plane 401/403, SQL grant errors, network failures, TLS errors, and pool exhaustion.
14. Drill stop/start or clone/restore in a test environment.
15. Write a runbook for DBAs, Platform engineers, and application owners.

**Self-Assessment Questions:**

- How do the OCI control plane and database data plane differ?
- Why doesn't an OCI IAM policy automatically grant `SELECT` on tables?
- Why shouldn't database `ADMIN` be used as the application user?
- How does stopping an Autonomous Database differ from closing a JDBC connection?
- Does ECPU auto scaling automatically scale the Hikari pool?
- How do backup/restore and clone differ?
- Why do external files in Object Storage require separate backups?
- When do you use public endpoint ACLs vs. private endpoints?
- How does wallet-based JDBC Thin mTLS differ from walletless TLS?
- Why are wallets and database passwords two distinct credentials?
- Which workloads fit `TP`, `TPURGENT`, `HIGH`, `MEDIUM`, and `LOW` services?
- Why doesn't increasing `maximumPoolSize` necessarily increase throughput?
- How do HikariCP and UCP differ?
- Why must total pool size be calculated across replicas?
- Which directory does `TNS_ADMIN` point to?
- How does wallet rotation differ from password rotation?
- Why doesn't creating a new secret version in Vault automatically change the database password?
- How do you distinguish `ORA-12514` from `ORA-01017`?
- Why shouldn't database health checks trigger a liveness restart storm?
- Why should you test negative IAM policy and SQL privilege cases?

**Guided Answers:** OCI control plane manages resources while JDBC data plane runs SQL; IAM policies grant Autonomous Database management rights while database grants control SQL privileges; `ADMIN` is for DBAs; `stop` is a lifecycle operation while closing a connection only returns/closes a session; compute auto scaling does not reconfigure application pools; restore recovers a database while clone creates a new database; external object files are not automatically included in DB backups; private endpoints keep traffic inside the VCN; mTLS requires a client wallet while TLS can be walletless when enabled; wallet certificates differ from DB passwords; `TP` serves OLTP, `TPURGENT` prioritizes urgent transactions, `HIGH`/`MEDIUM`/`LOW` serve reporting/analytics by concurrency; connection count differs from statement concurrency; Hikari is general-purpose while UCP provides Oracle-specific HA features; total pool = replicas x pool per replica plus workers/admin; `TNS_ADMIN` points to the wallet/TNS directory; wallet rotation swaps client certificates while password rotation changes DB user credentials; Vault secret updates do not alter DB passwords automatically; `ORA-12514` usually points to service names while `ORA-01017` points to credentials; readiness and liveness must be separated; negative tests verify least privilege.

## 16. Official References

### OCI Autonomous Database Management

- [Manage the Autonomous AI Database Service](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/manage-service.html): lifecycle, scaling, auto scaling, cloning, and moving compartments.
- [IAM Policies for Autonomous AI Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-database-iam-policies.html): inspect/use/manage permissions, stop/start, scaling, and restore.
- [Use Auto Scaling](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-auto-scale.html): compute and storage auto scaling.
- [Backup and Restore](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/backup-intro.html): automatic backups, immutability, and recovery.
- [Backup and Restore Notes](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/backup-restore-notes.html): limitations regarding external Object Storage files and restore.
- [Network Access Options](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/network-access-options.html): public endpoint, ACLs, and private endpoints.
- [Configure Private Endpoints](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/private-endpoints-autonomous.html): private endpoints inside a VCN.
- [Configure Access Control Lists](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/access-control-rules-autonomous.html): restricting connections by IP/VCN.
- [Autonomous AI Database Lifecycle Events](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-database-events.html): start/stop/backup/restore/wallet rotation events.

### JDBC, Wallets, and Service Names

- [Connect to Autonomous AI Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/connect-autonomous-database.html): connection methods and options.
- [JDBC Thin Connections with a Wallet (mTLS)](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/connect-jdbc-thin-wallet.html): wallets, TNS aliases, and `TNS_ADMIN`.
- [JDBC Thin Connections Without a Wallet (TLS)](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/connect-jdbc-thin-tls.html): walletless TLS and connection descriptors.
- [Download Database Connection Information](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/connect-download-wallet.html): instance/regional wallets, file contents, and wallet protection.
- [Rotate Wallets](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/wallet-rotate.html): immediate rotation and grace periods.
- [Database Service Names](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/predefined-database-services-names.html): `TPURGENT`, `TP`, `HIGH`, `MEDIUM`, `LOW`, and workloads.
- [Service Concurrency](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/manage-service-concurrency.html): concurrency by ECPU/OCPU and auto scaling.
- [Create and Manage Users](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/manage-users-create.html): database users, roles, and password management.

### Spring Boot and Oracle JDBC/UCP

- [Spring Boot SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): `DataSource` auto-configuration, HikariCP, and UCP.
- [Spring Boot Data Access](https://docs.spring.io/spring-boot/how-to/data-access.html): custom `DataSource` and pool properties configuration.
- [Oracle JDBC Getting Started](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/JDBC-getting-started.html): driver/JDK compatibility.
- [Oracle JDBC Maven Artifacts](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/introducing-JDBC.html): `ojdbc`, UCP, and companion artifacts.
- [Universal Connection Pool Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjucp/universal-connection-pool-developers-guide.pdf): pool sizing, validation, and connection management.
- [UCP PoolDataSource API](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjuar/oracle/ucp/jdbc/PoolDataSource.html): max/min pool size, validation timeout, and connection wait.

**Key Takeaways:** OCI IAM manages the Autonomous Database service; database users/roles/grants manage data inside; JDBC Thin connects applications via TLS or mTLS; a wallet is a client credential for mTLS and is not synonymous with a database password. In Spring Boot, use a `DataSource`/pool sized to total replicas and service concurrency, protect wallets and secrets, separate runtime users from `ADMIN`, and test both connectivity paths and permissions across both planes.

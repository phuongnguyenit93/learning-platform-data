# Connecting to MySQL from Applications and Managing Users

## 1. Objectives and Scope

In the **MySQL HeatWave and NoSQL** chapter of the Oracle Cloud Infrastructure (OCI) learning path, this lesson focuses on the connectivity path between applications and MySQL HeatWave, along with managing MySQL accounts under least privilege.

A connection usable in operations must simultaneously satisfy:

1. The application has a network path to the right endpoint and port.
2. The connection uses TLS with an appropriate verification level.
3. The account can authenticate from the actual connection source.
4. The account is permitted to perform only the necessary business operations.
5. The application properly manages connections, timeouts, secrets, and connection errors.

After this lesson, you will be able to configure Java/JDBC connections, create users and roles for applications, verify effective privileges, budget connection pools, and troubleshoot errors layer by layer.

The examples use the **MySQL classic protocol**, Connector/J, and password-authenticated accounts. HeatWave is still accessed by applications through the DB system's MySQL endpoint; you do not point JDBC at a separate HeatWave processing node. This lesson does not cover connecting to Oracle NoSQL Database because that service uses a different API and permission model.

Database names, addresses, timeout thresholds, and limits in this lesson are illustrative values. Driver versions, authentication methods, and certificates must match your actual DB system.

## 2. Distinguishing IAM, Networking, and Database Accounts

### 2.1. Three Independent Permission Layers

| Layer | Examples | What This Layer Controls |
| --- | --- | --- |
| OCI IAM | Users/groups, policies, secret read permissions | Managing or accessing cloud service resources per policy |
| Network | VCN, subnet, NSG, security list, routes, and firewalls | Whether packets can reach the endpoint |
| MySQL | Accounts, authentication, roles, `GRANT` | Who logs into the database and what they can do inside |

Someone with permission to view a DB system in the Console does not automatically have `SELECT` privileges on business tables. Conversely, knowing a MySQL password without a network path or matching account host still prevents login.

A workload authorized by IAM to read a secret does not automatically receive MySQL privileges either. The secret only supplies credentials; the database account and grants must still exist.

### 2.2. Explicitly Configured Exception: OCI-Integrated Authentication

MySQL HeatWave provides a mechanism to map MySQL users to OCI identities through a supported authentication component. This mechanism requires explicit mapping, plugins, and compatible clients; it does not happen merely because a user logged into the Console. [Connecting with a mapped MySQL user](https://docs.oracle.com/en-us/iaas/mysql-database/doc/connecting-mapped-mysql-user.html).

The JDBC examples in this lesson use passwords. Do not place an OCID, API signing key, or Console password into the JDBC password field expecting it to work like a standard MySQL account.

## 3. Preparing the Network Path to the DB System

### 3.1. Obtaining the Right Endpoint

Record from the DB system:

- Endpoint used for read/write traffic.
- Connection hostname or IP address.
- MySQL classic protocol port.
- Associated VCN, subnet, and security groups.
- Certificate configuration and the names protected by the certificate.

The typical port for the classic protocol is 3306; X Protocol typically uses 33060. If the service is configured with a different port, use the actual value. The `jdbc:mysql://...` URLs in this lesson use the classic protocol, not the X Protocol port.

For systems with read endpoints or read replicas, choose the endpoint based on purpose. Do not send write operations to a read-only endpoint. Endpoint semantics must be verified against the DB system configuration. [DB system endpoints](https://docs.oracle.com/en-us/iaas/mysql-database/doc/db-system-endpoints.html).

### 3.2. Private Endpoints Require Private Access Paths

A MySQL DB system endpoint in OCI is not a public address for any arbitrary laptop to connect to directly. Access options include applications inside the VCN, connectivity from properly routed networks, VPN, or a Bastion session for administration. [MySQL HeatWave networking overview](https://docs.oracle.com/en-us/iaas/mysql-database/doc/overview-networking.html).

A typical application topology:

~~~mermaid
flowchart LR
    USER["Users"]
    LB["Load balancer / API"]
    APP["Java application in app subnet"]
    DB["MySQL DB system: private endpoint"]
    SECRET["Secret management service"]

    USER --> LB
    LB --> APP
    APP -->|"MySQL classic protocol + TLS"| DB
    APP -->|"Read secret via IAM permissions"| SECRET
~~~

The secret retrieval path and the MySQL access path are two separate connections. Appropriate routes and permissions must exist for each path.

### 3.3. Expressing Network Rules Precisely

Design example:

| Component | Direction and Scope |
| --- | --- |
| Application | Allow egress to the DB endpoint on the actual classic port |
| DB system | Allow ingress from approved application sources on that port |
| DNS | Application can resolve the hostname used for connection |
| Admin access | Allow only approved admin sources via an appropriate access path |
| OS or external firewalls | Do not block the app-to-DB flow if present along the path |

If NSG-to-NSG fits the topology and is supported, it can be used to avoid depending on individual machine IPs. If using CIDRs, keep the scope minimal and document the actual path.

Evaluate all applicable rules together; do not assume adding a "restrictive" NSG automatically narrows permissions already granted more broadly by another rule.

Do not open the database port to the entire Internet to fix a connection error. Identify whether a route, security rule, or administrative access path is missing.

### 3.4. The Connection Source That MySQL Sees

The host in an account `'user'@'host'` is the client source address recognized by MySQL, not the DB server's address.

If NAT, proxies, tunnels, or Kubernetes topologies sit in between, the source address seen by MySQL may differ from the pod or laptop IP. Observe the actual source before creating host restrictions.

A Bastion/tunnel is a transport for a specific access path. Do not assume host restrictions intended for application servers should also permit tunnel traffic from admin workstations.

## 4. TLS: Encryption and Server Identity Verification

### 4.1. `sslMode` Levels in Connector/J

| Mode | Encryption | CA Check | Server Name/Address Check Against Certificate |
| --- | --- | --- | --- |
| DISABLED | No | No | No |
| PREFERRED | Yes if server supports it; may fall back | Not equivalent to CA verification | No |
| REQUIRED | Mandatory TLS | Not equivalent to VERIFY_CA | No |
| VERIFY_CA | Mandatory TLS | Yes | No |
| VERIFY_IDENTITY | Mandatory TLS | Yes | Yes |

Connector/J distinguishes these levels; defaults or an "enable SSL" flag alone do not prove server identity verification is active. [Connector/J security properties](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-security.html).

The application example in this lesson requires `VERIFY_IDENTITY`. Prerequisites for it to work:

- The client trusts the correct CA/certificate chain.
- The server certificate is valid and not expired.
- The hostname or address in the connection matches an identity protected by the certificate.
- The driver and JVM versions support the service's TLS configuration.

If these are not met, fix the certificate, DNS, or trust configuration appropriately. Disabling verification only makes the connection test succeed with weaker protection without addressing the root cause.

### 4.2. Service-Provided vs. Customer-Provided Certificates

MySQL HeatWave offers options for service-defined certificates or customer-provided certificates via supported mechanisms. [DB system certificate options](https://docs.oracle.com/en-us/iaas/mysql-database/doc/advanced-options.html).

Do not assume every service-generated certificate matches a custom DNS alias you invent. Nor should you change the host in the JDBC URL to an IP if that IP is not in the certificate's valid identities.

Before running the examples:

1. Confirm the endpoint and actual certificate type.
2. Obtain the CA/chain from a trusted administrative source.
3. Confirm the endpoint identity protected by the certificate.
4. Provide the truststore or CA file to the right runtime.
5. Test from the same network environment as the application.

Connecting via a tunnel to `localhost` can trigger identity errors because the certificate protects the DB endpoint name, not `localhost`. Design the connection path and server identity preservation properly rather than lowering the verification level.

### 4.3. Java Truststore

Connector/J can use a dedicated truststore or the JVM's trust mechanism depending on configuration. [Configuring server authentication with Connector/J](https://dev.mysql.com/doc/connector-j/en/connector-j-server-authentication.html).

Example of creating a dedicated PKCS12 truststore in a Linux application environment:

~~~bash
keytool -importcert -alias heatwave-root-ca -file /opt/app/certs/heatwave-ca.pem -keystore /opt/app/certs/heatwave-truststore.p12 -storetype PKCS12
~~~

The command prompts for a truststore password and certificate confirmation. Before trusting it, verify the CA/fingerprint against an approved source. If the chain requires multiple CAs, import all required certificates under distinct aliases.

The paths above illustrate a Linux runtime; on Windows, use corresponding paths and file URLs.

A truststore holds trusted certificates, not MySQL passwords. Do not confuse it with a keystore holding private keys for mTLS client authentication. The example in this lesson does not require a client certificate; if your environment mandates mTLS, add a keystore and corresponding configuration.

Certificate lifecycle management must also account for expiration dates, CA rotation, and application replicas that have not yet received the updated truststore.

## 5. Preparing the Schema and Accounts Under Least Privilege

### 5.1. Separating Admin, Migration, and Runtime

| Identity | Responsibility | Typical Scope |
| --- | --- | --- |
| Database admin | Create users/roles, manage privileges, and operate within service scope | Administrative privileges supported by the service |
| Migration/deployment | Create or alter schemas per release | Necessary DDL on assigned schemas |
| Application runtime | Execute business transactions | Necessary `SELECT`/`INSERT`/`UPDATE` on specific objects |
| Reporting | Read authorized data | `SELECT` on approved tables or views |

Do not use the DB system administrator account inside applications. Even a managed service administrator account does not necessarily hold every root privilege of a self-hosted MySQL instance; certain privileges and system schemas are restricted. [Default DB system administrator privileges](https://docs.oracle.com/en-us/iaas/mysql-database/doc/default-mysql-privileges.html).

### 5.2. Creating Sample Data

In a learning environment, an administrator or deployment identity with appropriate privileges prepares:

~~~sql
CREATE DATABASE orders CHARACTER SET utf8mb4;

CREATE TABLE orders.purchase_order (
    id BIGINT NOT NULL AUTO_INCREMENT,
    request_id VARCHAR(64) NOT NULL,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_purchase_order_request (request_id)
);

INSERT INTO orders.purchase_order
    (request_id, customer_id, total_amount, status)
VALUES
    ('LAB-ORDER-001', 101, 250000.00, 'CREATED');
~~~

These creation statements assume the schema does not already exist; do not run them as-is against an active production schema. Production migrations require project tooling and change-control workflows.

### 5.3. MySQL Accounts Include Both User and Host

These two accounts are two distinct identities:

~~~text
'orders_app'@'10.20.1.25'
'orders_app'@'10.20.1.26'
~~~

The same username with different hosts can have different passwords and grants. The host in these examples must be replaced with the actual connection source recognized by MySQL.

To serve multiple instances, you can create multiple host-specific accounts or use network ranges supported by the version. Do not default to `@'%'` for every application; scope selection must fit the topology. MySQL also has specific rules for netmasks/CIDRs and host wildcards. [MySQL account name syntax](https://dev.mysql.com/doc/refman/8.4/en/account-names.html).

### 5.4. Creating a Role and Assigning It to Runtime

Administrative example for an application server coming from `10.20.1.25`:

~~~sql
CREATE ROLE 'orders_runtime';

GRANT SELECT, INSERT, UPDATE
ON orders.purchase_order
TO 'orders_runtime';

CREATE USER 'orders_app'@'10.20.1.25'
IDENTIFIED BY 'REPLACE_WITH_GENERATED_SECRET'
REQUIRE SSL;

GRANT 'orders_runtime'
TO 'orders_app'@'10.20.1.25';

SET DEFAULT ROLE 'orders_runtime'
TO 'orders_app'@'10.20.1.25';
~~~

`REPLACE_WITH_GENERATED_SECRET` is a placeholder to be replaced with a secret generated and delivered through an approved management channel, not a shared lab password. Avoid leaving real passwords in repositories, terminal history, or pipeline SQL logs.

Here, runtime can read, insert, and update orders; it cannot `DELETE`, run DDL, or grant privileges to itself. If the business logic does not need `UPDATE`, omit that privilege. Least privilege derives from actual operations, not a fixed `GRANT` template.

An assigned role is not necessarily active in a session automatically; `SET DEFAULT ROLE` specifies the default active role for subsequent connections. Existing open sessions must be checked or re-established. [Using roles in MySQL](https://dev.mysql.com/doc/refman/8.4/en/roles.html).

The role name in the example omits a host; the default host in a role identifier does not carry connection-wildcard semantics like a login account. [MySQL role name syntax](https://dev.mysql.com/doc/refman/8.4/en/role-names.html).

`REQUIRE SSL` enforces an encrypted channel for the account on the server side. It does not substitute for client-side certificate verification, nor does it automatically require a client certificate like an mTLS setup.

## 6. Testing with a Client Before Connecting the Application

### 6.1. Testing from the Right Network Source

Run the client from the application server or an environment with an equivalent network path. Logging in successfully from an admin workstation does not prove an application container also has the right DNS, routes, CA, and account host.

Example with the MySQL client in a Linux shell, after setting `DB_HOST` and `DB_PORT`:

~~~bash
mysql --host="$DB_HOST" --port="$DB_PORT" --user=orders_app --password --ssl-mode=VERIFY_IDENTITY --ssl-ca=/opt/app/certs/heatwave-ca.pem orders
~~~

The client prompts interactively for the password. Never append the real password directly after `--password` or place it on the command line.

The hostname must meet the certificate requirements described earlier. The CA file path used by the MySQL CLI client does not automatically make the JVM trust the same CA; Java must be given an appropriate truststore.

### 6.2. Inspecting the Session Account and Privileges

After logging in:

~~~sql
SELECT
    USER() AS client_identity,
    CURRENT_USER() AS authenticated_account,
    CURRENT_ROLE() AS active_roles,
    DATABASE() AS current_database;

SHOW GRANTS;

SHOW SESSION STATUS LIKE 'Ssl_cipher';

SELECT id, status
FROM orders.purchase_order
ORDER BY id
LIMIT 5;
~~~

How to interpret:

- `USER()` reflects the client-provided username and connection source.
- `CURRENT_USER()` reports the MySQL account used to authenticate the session in this direct query context.
- `CURRENT_ROLE()` confirms active roles.
- `DATABASE()` confirms the default schema.
- A populated `Ssl_cipher` indicates the session is using a TLS cipher.

The cipher proves encryption is active, not that the client verified the right hostname. Evidence of identity verification also lies in the client configuration and confirming rejection against an invalid certificate/host in a test environment.

`SHOW GRANTS` displays direct grants/assigned roles; inspect the role's privileges as well when verifying effective permissions. Administrators can run:

~~~sql
SHOW GRANTS FOR 'orders_runtime';

SHOW GRANTS FOR 'orders_app'@'10.20.1.25'
USING 'orders_runtime';
~~~

Do not grant broad read access to system tables just so an application can self-inspect accounts. Auditing other accounts belongs to an appropriate administrative identity. [SHOW GRANTS reference](https://dev.mysql.com/doc/refman/8.4/en/show-grants.html).

### 6.3. Also Testing Forbidden Operations

In the learning schema, runtime must be able to read granted tables. You can verify the absence of DDL privileges using a dedicated test table:

~~~sql
CREATE TABLE orders.runtime_should_not_create (
    id BIGINT PRIMARY KEY
);
~~~

With the runtime role above and no extra grants, this statement must be denied. If it succeeds, stop testing and audit privileges; let an administrative identity clean up the test table after identifying the cause.

Never use `DROP` on a business table or delete real data as a "forbidden privilege" test. Test only on isolated dummy objects that cannot affect other data.

## 7. Connecting from Java with Connector/J

### 7.1. Dependency and Compatibility

Connector/J uses Maven coordinates `com.mysql:mysql-connector-j`. [Installing Connector/J with Maven](https://dev.mysql.com/doc/connector-j/en/connector-j-installing-maven.html).

Example dependency:

~~~xml
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <version>${mysql.connector.version}</version>
</dependency>
~~~

This is a sample configuration snippet: define `mysql.connector.version` to a concrete version verified compatible with your JDK and DB system. If your project's dependency management/BOM already manages a suitable version, use that mechanism and omit the explicit version tag where appropriate.

Do not use a "latest" version label as a reproducible production configuration. Nor should you force the server back to a legacy authentication plugin just to keep using an outdated driver.

### 7.2. Externalizing Configuration Outside Source Code

Example runtime configuration variables:

| Variable | Content |
| --- | --- |
| DB_HOST | Endpoint hostname matching DNS and certificate |
| DB_PORT | Actual classic protocol port |
| DB_USER | orders_app |
| DB_PASSWORD | MySQL secret retrieved via secret management |
| DB_TRUSTSTORE_URL | Truststore file URL, e.g., `file:/opt/app/certs/heatwave-truststore.p12` |
| DB_TRUSTSTORE_PASSWORD | Truststore password |

The sample schema is `orders`. In other deployments, supply the schema name through controlled configuration.

Configuration values must come from a trusted deployment environment. Never take hostname, JDBC URL, or driver properties directly from user requests.

### 7.3. Java Example Reading an Order

This example uses standard JDBC to make connection settings explicit without framework overhead. The code targets Java 17 or newer; Connector/J must still be present on the runtime classpath.

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Properties;

public final class OrderLookup {
    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing configuration: " + name);
        }
        return value;
    }

    public static void main(String[] args) {
        String host = requiredEnv("DB_HOST");
        int port = Integer.parseInt(requiredEnv("DB_PORT"));
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("Invalid DB_PORT");
        }

        long orderId = args.length == 0 ? 1L : Long.parseLong(args[0]);
        String url = "jdbc:mysql://" + host + ":" + port + "/orders";

        Properties properties = new Properties();
        properties.setProperty("user", requiredEnv("DB_USER"));
        properties.setProperty("password", requiredEnv("DB_PASSWORD"));
        properties.setProperty("sslMode", "VERIFY_IDENTITY");
        properties.setProperty("connectTimeout", "5000");
        properties.setProperty("socketTimeout", "15000");
        properties.setProperty(
            "trustCertificateKeyStoreUrl",
            requiredEnv("DB_TRUSTSTORE_URL")
        );
        properties.setProperty("trustCertificateKeyStoreType", "PKCS12");
        properties.setProperty(
            "trustCertificateKeyStorePassword",
            requiredEnv("DB_TRUSTSTORE_PASSWORD")
        );
        properties.setProperty("fallbackToSystemTrustStore", "false");

        String sql =
            "SELECT id, status FROM purchase_order WHERE id = ?";

        try (Connection connection =
                 DriverManager.getConnection(url, properties);
             PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setLong(1, orderId);
            statement.setQueryTimeout(5);

            try (ResultSet result = statement.executeQuery()) {
                if (result.next()) {
                    System.out.printf(
                        "orderId=%d, status=%s%n",
                        result.getLong("id"),
                        result.getString("status")
                    );
                } else {
                    System.out.println("Sample order not found");
                }
            }
        } catch (SQLException exception) {
            System.err.printf(
                "Database operation failed: SQLState=%s, code=%d%n",
                exception.getSQLState(),
                exception.getErrorCode()
            );
            throw new IllegalStateException(
                "Database connection or query failed"
            );
        }
    }
}
~~~

Key points to understand:

- The password is passed via `Properties`, not embedded in the JDBC URL.
- TLS and identity verification are explicitly required.
- A dedicated truststore is enforced; the example disables fallback to the system truststore.
- `PreparedStatement` binds parameter values rather than concatenating SQL strings from input.
- `try-with-resources` closes the result set, statement, and connection.
- Sample error logs record only `SQLState` and error code, never dumping full properties or secrets.

Sample data typically assigns `id = 1` to the first row in a newly created table; if your environment uses another ID, pass the actual ID. Finding no matching row is not a connection error.

Production applications should handle errors through the service's logging and error-handling framework rather than turning this console example into the sole error policy.

### 7.4. Avoid Adding Unsubstantiated "Fix" Flags

Avoid changes such as:

~~~text
sslMode=DISABLED
allowPublicKeyRetrieval=true
autoReconnect=true
~~~

Not every one of these properties is wrong in all circumstances, but they are not default switches for fixing arbitrary connection errors.

For example, an RSA public key retrieval error must be evaluated alongside the authentication plugin and TLS. Prioritize configuring TLS and server authentication properly rather than enabling key retrieval from an unverified server and treating the connection as equally protected.

Driver-level auto-reconnect does not automatically restore transaction state or resolve uncertain commit outcomes either. A new connection does not mean the previous transaction continued.

## 8. Timeouts and Connection Pools

### 8.1. Each Timeout Bounds a Different Stage

| Setting | What It Bounds | Should Not Be Inferred |
| --- | --- | --- |
| Driver `connectTimeout` | Socket establishment wait time per driver behavior | That the entire request is guaranteed to finish within that time |
| Driver `socketTimeout` | Socket I/O wait time per driver behavior | That the server rolled back the transaction |
| Statement query timeout | Request to cap statement execution time per JDBC/driver support | That every query cancels instantaneously with zero side effects |
| Pool acquisition timeout | Wait time to borrow a connection | SQL execution duration |
| Request deadline | Overall request budget | That downstream layers automatically know and obey it without integration |

Connector/J defines `connectTimeout` and `socketTimeout` in milliseconds. Values in the example are illustrative choices, not universal recommendations. [Connector/J networking properties](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-networking.html).

Choose timeouts based on business SLOs, network latency, and query type. A legitimate long-running reporting query may need different settings than an order-creation API.

Do not mechanically add timeouts together to claim an end-to-end guarantee. Design request deadlines and observe cancellation behavior at every layer.

### 8.2. Using a Pool for Multi-Request Applications

Opening TLS and authenticating on every request adds overhead and latency. In long-running applications, use a `DataSource` backed by a connection pool managed by an appropriate framework or library.

Access pattern:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             "SELECT status FROM orders.purchase_order WHERE id = ?"
         )) {
    statement.setLong(1, orderId);
    try (ResultSet result = statement.executeQuery()) {
        // Read results while holding the connection.
    }
}
~~~

Here `dataSource` is a pool initialized with the same endpoint, user, TLS, and truststore configuration. Calling `close()` on a pooled connection typically returns it to the pool; do not omit closing it simply because a pool is in use.

`MysqlDataSource` provides connection configuration, but using a `DataSource` alone does not prove physical pooling is active. Verify which component actually holds and reuses connections.

Never share a single `Connection` singleton across concurrent requests. Separate the application-wide pool lifecycle from the connection borrowed for a single unit of work.

### 8.3. Calculating Total Connections When Scaling Applications

Suppose:

~~~text
6 app replicas × max pool of 12 connections = 72
Migrations, observability, and other tasks   =  8
Projected total                              = 80
~~~

If the connection budget allocated for this application and tasks is 80 after reserving administrative headroom, the setup above leaves zero room for additional replicas.

When autoscaling to 10 replicas:

~~~text
10 × 12 + 8 = 128 connections
~~~

Increasing replica counts without adjusting connection budgets can trigger failures under load spikes.

Account for:

- Maximum replicas and surge replicas during rolling deployments.
- Batch workers, scheduled jobs, migrations, and monitoring tools.
- Connections across different endpoints.
- Headroom reserved for operations and incident response.
- Actual DB system resources able to serve load, not just configuration limits.

A larger pool does not automatically increase throughput. Too many concurrent transactions can increase lock contention, CPU, and memory pressure.

### 8.4. Per-Account Limits as an Additional Guardrail

Administrators can set an appropriate limit, for example:

~~~sql
ALTER USER 'orders_app'@'10.20.1.25'
WITH MAX_USER_CONNECTIONS 20;
~~~

The number 20 is illustrative and must align with the pool and all jobs using that account. This limit is enforced per MySQL account; if multiple sources match the same account, they share that budget.

When the limit is exceeded, the application receives an error rather than letting the DB system exhaust resources. Monitor active connections, pool wait queues, and failed requests together.

## 9. Transactions, Retries, and Uncertain Commit Outcomes

### 9.1. A Successful Connection Does Not Guarantee Correct Transactions

New JDBC connections typically default to autocommit depending on configuration. When business logic requires multiple statements in a single transaction, manage transaction boundaries consistently via the framework or JDBC.

Pattern:

1. Borrow a connection.
2. Begin the transaction scope.
3. Execute required statements.
4. Commit on completion or roll back while still possible.
5. Return the connection once transaction state is cleanly handled.

Do not hold a connection open while waiting on user input, slow HTTP calls, or file I/O unless the transaction genuinely spans them. Long connection hold times exhaust pools even when the database has spare CPU.

### 9.2. Do Not Blindly Retry on Connection Loss

Scenario:

~~~text
Application sends COMMIT
    -> server may have committed
    -> connection drops before application receives the response
~~~

The application cannot know the outcome with certainty. Re-running the entire operation could create duplicate orders.

The sample table includes a unique `request_id` to support idempotent design. Persist a stable request key for the same business action and define reconciliation logic on retry. A unique key is a foundational mechanism; you must still validate that duplicate requests carry identical payloads and handle external side effects properly.

Retries should use bounded attempts, backoff, and jitter for appropriate transient errors. Never retry indefinitely on bad passwords, invalid certificates, missing privileges, or SQL syntax errors.

### 9.3. Failover Does Not Preserve Existing Connections

During maintenance or instance switchover, existing connections can be severed. Applications must discard unusable connections, open new ones through the proper endpoint, and handle interrupted transactions according to business rules.

Do not pin applications to an internal backend address not designated by the service as an application endpoint. DB system HA does not automatically ensure in-flight requests finish without client-side handling.

## 10. Managing Application Secrets

### 10.1. Never Package Passwords into Artifacts

Do not store MySQL passwords in:

- Source code or committed configuration files.
- Container images.
- JDBC URLs written to logs.
- Command lines or pipeline outputs.
- Health-check pages or diagnostic endpoints.

In OCI, you can use the secret management service and least-privilege workload identities to retrieve the required secret. Choosing secret OCIDs, versions, and access policies belongs to deployment configuration; the MySQL runtime receives only the values needed for authentication.

Do not grant an application permission to list or read every secret in a tenancy when it needs only one secret.

### 10.2. Environment Variables Are Only One Delivery Mechanism

The Java example reads environment variables for brevity and to keep secrets out of code. That does not make environment variables an absolutely secret boundary.

Control:

- Who can inspect workload configuration or debug processes.
- Whether startup logs print configuration dumps.
- Whether secrets appear in crash dumps or support bundles.
- When the application reads secrets and how it picks up new versions.
- File permissions on truststores and config files when mounted via volumes.

You may use SDKs, secret volumes, or platform-native integrations. The choice must fit the application lifecycle and rotation workflow.

### 10.3. Do Not Confuse Reading a New Secret with Updating the Pool

If an application reads the password only during pool initialization, updating the secret value does not automatically update credentials inside that live pool.

Procedures must adopt one of the following approaches:

- Create a new pool with the new secret and shift traffic.
- Perform a rolling restart so each replica reinitializes.
- Use a credential refresh mechanism supported and verified in the pool library.

Already-authenticated connections can continue working after a password change. Thus, an application that "is still running fine" does not prove new connections will authenticate.

## 11. Password Rotation with a Transition Window

### 11.1. Using Dual Passwords When Supported

MySQL supports maintaining a primary and secondary password for an account under eligible conditions. `RETAIN CURRENT PASSWORD` keeps the current password as the secondary password during rotation, while `DISCARD OLD PASSWORD` removes the secondary password. This requires a compatible version, authentication plugin, and administrative privileges. [ALTER USER and dual passwords](https://dev.mysql.com/doc/refman/8.4/en/alter-user.html).

Example executed by an administrative identity:

~~~sql
ALTER USER 'orders_app'@'10.20.1.25'
IDENTIFIED BY 'REPLACE_WITH_NEW_GENERATED_SECRET'
RETAIN CURRENT PASSWORD;
~~~

Never use the placeholder string as a real password. When automating via scripts or pipelines, protect both inputs and SQL tool logs.

Transition sequence:

1. Verify the account, plugin, privileges, and status of application instances.
2. Rotate to the new password while retaining the old password for a bounded transition window.
3. Update the secret version following release procedures.
4. Roll each replica/pool over to the new password.
5. Open **new connections** from application sources and verify required queries.
6. Confirm no workload still relies on the old password.
7. Discard the secondary password:

~~~sql
ALTER USER 'orders_app'@'10.20.1.25'
DISCARD OLD PASSWORD;
~~~

After the final step, test opening a new connection with the new password; in a controlled test, the old password must no longer authenticate.

Do not bundle an authentication plugin change into the same procedure without evaluating it separately, as it can alter dual-password behavior and client compatibility.

### 11.2. When Dual Passwords Are Not Used

You can create a replacement account with the same verified privilege scope:

~~~text
orders_app_a -> currently serving
orders_app_b -> staged, verified, and gradually shifted
~~~

Each account must still enforce proper host restrictions and TLS. After cutover, lock/revoke the old account on schedule; do not leave both active indefinitely without an owner.

The two-account approach provides a transition window at the cost of managing extra grants, account hosts, and audits. Never copy full administrator privileges to the new account.

### 11.3. Password Expiration and Machine Accounts

An application account whose password expires during business hours can cause new connections to fail while existing pooled connections remain alive. Symptoms may therefore surface gradually as pools recycle.

Align expiration policies with rotation schedules, alerting, and secret update mechanisms. Do not disable all password policies by default as a blanket rule for applications.

## 12. Auditing, Modifying Privileges, and Revoking Accounts

### 12.1. Documenting Privileges by Business Need

Example privilege matrix:

| Identity | Object | Privilege | Reason |
| --- | --- | --- | --- |
| `orders_runtime` | `orders.purchase_order` | `SELECT` | Look up orders |
| `orders_runtime` | `orders.purchase_order` | `INSERT` | Create orders |
| `orders_runtime` | `orders.purchase_order` | `UPDATE` | Update status per business logic |
| `reporting_reader` | Approved reporting view | `SELECT` | Read scoped data |
| `migration` | Assigned schema objects | Planned DDL | Deploy releases |

When new requirements arise, add specific privileges and test them. Never switch to `GRANT ALL ON *.*` just because a migration failed.

DDL privileges and grant options should not exist on runtime accounts if the application does not perform those tasks. Nor should server admin privileges be granted to troubleshoot a failing `SELECT`.

### 12.2. Roles Do Not Replace End-User Authorization

`orders_app` is a shared backend technical identity in this example. MySQL sees that account and has no automatic awareness of which HTTP customer sent the request.

The application must authenticate end users, enforce business authorization, and scope queries appropriately. A query with `WHERE id = ?` in a `PreparedStatement` does not automatically guarantee the caller is authorized to view that order.

`PreparedStatement` handles value parameters; if the application allows dynamic column names, table names, or sort directions, validate them against an allowlist. Never concatenate arbitrary SQL fragments from requests.

### 12.3. Revoking Privileges While Accounting for Role Impact

Example in an evaluated change:

~~~sql
REVOKE UPDATE
ON orders.purchase_order
FROM 'orders_runtime';
~~~

This statement alters the role, affecting all accounts using that role. If you only want to remove the entire role from one account, use a different statement:

~~~sql
REVOKE 'orders_runtime'
FROM 'orders_app'@'10.20.1.25';
~~~

These two commands illustrate two different change scopes; do not run them back-to-back as a default routine. Check whether the account holds direct grants or other roles that still grant the same capability.

After making changes, verify with a fresh connection using the account from the proper source. When different privilege changes take effect on already-open sessions varies; do not treat checking an old session as sole proof.

`FLUSH PRIVILEGES` is not needed after standard account/grant statements such as `CREATE USER`, `GRANT`, and `REVOKE`. Never edit grant tables directly to bypass service management boundaries.

### 12.4. Locking Accounts and Handling Active Sessions

Example:

~~~sql
ALTER USER 'orders_app'@'10.20.1.25' ACCOUNT LOCK;
~~~

Account locking blocks new authentications but does not automatically terminate existing sessions. [Account locking in MySQL](https://dev.mysql.com/doc/refman/8.4/en/account-locking.html).

When decommissioning an application or responding to leaked credentials, procedures may also require stopping the workload, revoking secrets, and terminating related sessions using supported administrative privileges.

Do not rely on a lock statement alone as proof that all access is cut off. Verify both new connections and live sessions.

If unlocking is needed after resolving the root cause:

~~~sql
ALTER USER 'orders_app'@'10.20.1.25' ACCOUNT UNLOCK;
~~~

### 12.5. Dropping Accounts

Drop an account only after confirming it is no longer in use and reviewing dependencies:

~~~sql
DROP USER 'orders_app'@'10.20.1.25';
~~~

Check jobs, secrets, pools, deployment scripts, and any objects with a matching `DEFINER` if applicable. Do not assume dropping an account automatically cleans up objects or data it created.

For accounts sharing a username across different hosts, audit each account individually. Dropping one host entry does not remove all authentication paths for that username.

## 13. Troubleshooting Layer by Layer Without Random Privilege Escalation

### 13.1. Inspection Order

~~~text
Driver config and URL
    -> endpoint resolution
    -> network path and TCP port
    -> TLS and certificate
    -> authentication/account host
    -> schema, role, and privileges
    -> pool, transactions, and business behavior
~~~

This order narrows the investigation scope. For example, a certificate error occurring before any query runs cannot be fixed with `GRANT SELECT`.

### 13.2. Symptom Table

| Symptom | First Area to Check | Unsubstantiated Fix to Avoid |
| --- | --- | --- |
| Cannot resolve host | Endpoint, VM/container DNS, and private zone | Switching to an arbitrary IP and disabling identity verification |
| TCP timeout | Routes, NSGs/security lists, firewalls, VPN/Bastion, and port | Opening the database to the entire Internet |
| Connection refused | Right endpoint/port and service status | Resetting passwords repeatedly |
| PKIX/path validation failure | Truststore, CA chain, expiration, and file actually read by runtime | Disabling certificate verification |
| Hostname/identity mismatch | Whether URL host matches the certificate | Using `VERIFY_CA` as if identity verification were satisfied |
| Access denied at login | Password, account host, plugin, and account status | Running `GRANT ALL` on an account that may not even be matched |
| Login succeeds but schema inaccessible | Database name and schema/object privileges | Using the administrator account for runtime |
| `SELECT`/`INSERT` denied | Direct grants, assigned roles, and active roles | Granting server-wide privileges |
| Too many connections | Total pool sizing, leaks, hold times, and DB limits | Blindly increasing pool size across every replica |
| User connection limit exceeded | `MAX_USER_CONNECTIONS` and shared accounts | Creating unlimited new accounts to bypass limits |
| Long pool waits | Held connections, slow SQL, locks, and leaks | Increasing request timeouts indefinitely |
| Disconnects after maintenance | Endpoint, stale connections, retries, and transaction state | Blindly retrying all write operations |
| No suitable driver | Dependencies, runtime classpath, and URL scheme | Changing network rules |

Specific error messages also depend on driver, server, and configuration. Use `SQLState`, error codes, timestamps, endpoint identifiers, and correlation IDs as evidence; never paste passwords or full secret contents into support tickets.

### 13.3. Access Denied: Verifying the Exact Account Matched

When an administrator investigates:

1. Identify the actual connection source seen by the server.
2. Check accounts matching both username and host.
3. Verify the password/secret version currently used by the workload.
4. Check authentication plugin, lock state, and password expiration.
5. Once logged in, verify `CURRENT_USER`, `CURRENT_ROLE`, and grants.

A more specific host account may take precedence over a broader wildcard account with the same name. Do not edit only `@'%'` and assume every source uses those grants.

Never print passwords to logs to "compare" two configs. You can compare secret versions and deployment metadata without exposing secret values.

### 13.4. CLI Connects Successfully While Java Fails

Compare differences:

- Do the CLI and JVM run on the same network and DNS?
- Are they using the same endpoint, port, and account host?
- Which CA file does the CLI use, and which truststore does Java use?
- Is Java running an older container image or stale secret?
- Does the driver support the DB system's authentication plugin and TLS settings?
- Is Java overriding settings via a framework or JDBC URL parameters?

Tests must reproduce the application's actual conditions. Connecting from a laptop through a tunnel as an admin user does not represent a backend on Compute/OKE using a runtime account.

## 14. Monitoring Connections and Controlling Operational Overhead

### 14.1. Metrics to Track

| Layer | Useful Signals |
| --- | --- |
| Application | Request latency, error rate, timeouts, and retries |
| Pool | Active/idle connections, pending threads, acquisition time, creation failures |
| Database | Open/running threads, connection errors, slow queries, lock waits |
| Security | Failed logins, locked accounts, user/role/grant changes |
| Certificates | Expiration dates, trust errors, and CA update windows |
| Secrets | Deployed versions, secret read errors, and rotation outcomes |

Set up alerts with assigned owners and runbooks. Before scaling up compute or changing shapes for "slow database" issues, check for pool exhaustion, connection leaks, locks, or inefficient SQL.

Certain MySQL status metrics can be observed using an appropriately privileged identity:

~~~sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Connection_errors%';
~~~

Global counters reflect the entire server, not a single application. On a managed service, combine official service metrics with pool telemetry to isolate root causes.

Do not grant runtime accounts visibility into all sessions or SQL text from other applications just to build a dashboard.

### 14.2. Controlling Connection Storms

After deployments or network blips, many replicas may rebuild their pools simultaneously.

Mitigations:

- Stagger initialization and rollouts with controlled concurrency.
- Cap pools within the calculated connection budget.
- Use bounded retries with backoff and jitter.
- Reserve connection headroom for operational tasks.
- Monitor connection creation rates, not just total open connections.

Overly large idle pools also consume server resources. Size pools to meet measured load, then observe and tune rather than copying pool settings from another system.

## 15. Hands-On Walkthrough from Endpoint to Account Lifecycle

### 15.1. Prerequisites

Prepare a learning environment with:

- An active MySQL DB system.
- Network path from the application host to the endpoint.
- An administrative identity with required service-scoped privileges.
- Compatible MySQL client, JDK, and Connector/J.
- Certificates/CA and hostname satisfying identity verification.
- A secret delivery mechanism outside source repositories.

The database operations in this lesson are lab instructions. Without these prerequisites, you can read and draft configs, but do not report live connectivity as verified.

### 15.2. Sequence

1. Record the endpoint, port, application source, and certificate configuration.
2. Verify DNS, routes, and required network rules.
3. Create the sample schema/table using an appropriate deployment identity.
4. Create the runtime role, host-specific account, and default role.
5. Log in with the CLI client using identity verification.
6. Record `CURRENT_USER`, `CURRENT_ROLE`, TLS cipher, and `SELECT` output.
7. Run the Java example with the same endpoint, secret, and truststore.
8. In the test schema, verify runtime cannot create tables.
9. Calculate total connections at normal replicas, max autoscale, and rolling deployments.
10. Rehearse password rotation, force new connections, and verify old credentials fail after cutover.
11. Rehearse account locking, observing the difference between existing sessions and new logins.
12. Clean up test objects/accounts with an administrative identity once finished.

Do not leave demo accounts or temporary passwords around after the lab if no longer needed. When cleaning up, double-check the exact schema and host to avoid impacting accounts sharing the same username.

### 15.3. Verification Evidence

| Item | Verification Condition |
| --- | --- |
| Network path | Application reaches the right endpoint via approved source and port |
| TLS | Client enforces `VERIFY_IDENTITY`, valid CA, and matching endpoint identity |
| Account | `CURRENT_USER` matches the expected host-specific account |
| Role | Required role is active on new connections |
| Allowed privileges | Sample business operations succeed |
| Denied privileges | Test DDL is rejected for runtime |
| Java | Query succeeds, resources close cleanly, and no secrets are logged |
| Pool | Budget covers max replicas plus operational headroom |
| Rotation | New credentials establish connections; old credentials are rejected after transition |
| Revocation | Blocking new logins is distinguished from terminating active sessions |

Proving only that the TCP port is open does not complete TLS, authentication, and privilege verification. Logging in only as the administrator does not prove the runtime account operates properly.

## 16. Core Principles to Apply

Connecting to MySQL from an application is an end-to-end chain of controls: **right endpoint, right network path, right certificate, right account, and right privileges**.

Keep administrative accounts out of runtime, manage privileges around business needs and explicit roles. Separate secrets from code while designing for refresh, rotation, and revocation. Use bounded pools, purpose-driven timeouts, and transaction-aware retries.

When errors occur, rely on layer-by-layer evidence to fix them. An encrypted connection, an authenticating user, and a resilient production application are three distinct verification milestones.

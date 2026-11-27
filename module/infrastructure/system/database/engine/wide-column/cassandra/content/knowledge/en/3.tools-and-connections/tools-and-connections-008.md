# Authentication, Credentials, and TLS Connections

## 1. Why Being Able to Connect to Cassandra Does Not Mean Access Is Secure

Apache Cassandra is a **distributed wide-column database**. Java applications or `cqlsh` connect to a node over the **native protocol**, defaulting to TCP port **9042**; that node acts as coordinator and forwards requests to replicas based on the partition key, replication, and consistency. A working network path is only the first prerequisite. A real-world system also needs to know **which server the client is talking to, who the client is, and what the client is allowed to do**.

Three mechanisms answer three independent questions:

| Mechanism | Primary Question | Example |
| --- | --- | --- |
| **TLS (Transport Layer Security)** | Is data encrypted in transit? Does the client verify the genuine server? | Java Driver verifies the server certificate for `db.example.internal` issued by the organization's CA. |
| **Authentication** | What is the client's login identity? | `PasswordAuthenticator` verifies the username/password of role `report_reader`. |
| **Authorization** | Is the authenticated identity permitted to run a specific CQL statement? | Role `report_reader` is allowed only `SELECT` on one table, not `INSERT` or `DROP`. |

TCP connection, TLS handshake, and CQL login are **separate steps**. A connection may pass TLS yet fail authentication; or log in successfully yet receive `Unauthorized` due to missing permissions.

This lesson belongs to the **Tools and Connections** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module and connects directly to partition-key data access, keyspace replication, read/write consistency levels, and Java application operations. Understanding these security layers helps deploy, observe, and troubleshoot Cassandra without mistaking security issues for CQL or topology errors.

**After this lesson, you will be able to:**

1. Distinguish TLS, username/password, roles, and CQL permissions.
2. Understand configuration options for `authenticator`, `authorizer`, and `client_encryption_options` across Cassandra versions.
3. Create a read-only role, grant least-privilege permissions, and verify that disallowed operations are rejected as designed.
4. Connect cqlsh and Java Driver 4.x with TLS, a trusted CA, and credentials.
5. Diagnose failures from DNS/TCP and TLS handshake through authentication/authorization and post-login consistency errors.
6. Propose practices for protecting and rotating credentials/certificates and managing permissions in a multi-node cluster.

## 2. Connection Flow: Network → TLS → Authentication → Authorization → Query

~~~mermaid
sequenceDiagram
    participant App as cqlsh / Java Driver
    participant Node as Cassandra native endpoint
    participant Replica as Partition replica
    App->>Node: TCP to host:9042
    opt Native transport has TLS enabled
        App->>Node: TLS ClientHello / verify CA, hostname
        Node-->>App: TLS handshake and server certificate
    end
    App->>Node: Native protocol STARTUP
    opt Server requires login
        Node-->>App: AUTHENTICATE
        App->>Node: AUTH_RESPONSE with credentials
        Node-->>App: AUTH_SUCCESS or ERROR
    end
    App->>Node: QUERY/EXECUTE with CQL and consistency
    Node->>Node: Check role permissions
    alt Authorized
        Node->>Replica: Request to required replicas
        Replica-->>Node: Read/write responses
        Node-->>App: RESULT or execution error
    else Not authorized
        Node-->>App: Unauthorized
    end
~~~

This diagram shows a typical flow rather than a fixed number of round trips or every message type in every protocol version. TLS (when enabled) protects the **client ↔ node** connection; **node ↔ node** connections have their own TLS mechanism. Even after authentication succeeds, Cassandra must still authorize each operation.

**Critical distinctions:**

- **TLS server authentication** verifies the server via its certificate. It does not prove a Cassandra username/password is valid.
- **mTLS (mutual TLS)** adds a step where the server requests a client certificate. A client certificate becomes a CQL identity only when the system configures an **authenticator that supports mapping certificates to roles**; it does not automatically replace all password mechanisms.
- **CQL authentication** is separate from **JMX authentication**, which administrative tools like `nodetool` may use.
- **Native transport TLS** is configured separately from **internode TLS**. Securing 9042 does not automatically encrypt node-to-node communication on 7000.

## 3. Configuring Authentication and Authorization

In Cassandra, `cassandra.yaml` holds properties related to login and authorization. Basic example for versions supporting these components:

~~~yaml
# Conceptual excerpt, not a complete production file.
authenticator: PasswordAuthenticator
authorizer: CassandraAuthorizer
role_manager: CassandraRoleManager
~~~

| Component | Purpose |
| --- | --- |
| `AllowAllAuthenticator` | Does not require identity authentication with username/password. Suitable only for tightly controlled environments such as isolated labs. |
| `PasswordAuthenticator` | Authenticates Cassandra roles with username/password over the native protocol. |
| `AllowAllAuthorizer` | Does not enforce role-based CQL permission checks; unsuitable for systems requiring access control. |
| `CassandraAuthorizer` | Enforces CQL permissions such as `SELECT`, `MODIFY`, `CREATE`, and `ALTER`. |
| `CassandraRoleManager` | Manages roles, logins, and role relationships in Cassandra. |

**Do not enable `PasswordAuthenticator` while leaving `AllowAllAuthorizer` in a system needing permission restrictions**: authenticated users could then perform far more operations than intended. Conversely, enabling an authorizer without a proper role/grant strategy can easily lock out applications.

Changing `authenticator`, `authorizer`, or TLS involves node configuration and typically requires coordinated restarts/rolling restarts per your version. On clusters serving live applications, prepare roles, credentials, certificates/truststores, and verify administrative access before applying changes; never experiment with security settings directly in production as a lab exercise.

### 3.1. Roles, Logins, and Permissions Are Not the Same Thing

A **role** can represent a login identity, a permission group, or both. A role with `LOGIN = true` can be used to log in if supported by the authenticator; a role without `LOGIN` can be used to group permissions.

Example on a cluster with `PasswordAuthenticator` + `CassandraAuthorizer` enabled, where the current cqlsh session has role administration privileges:

~~~sql
-- Sample command: replace with a strong password, for lab environments only.
-- Avoid letting real passwords appear in shell history, logs, and CQL files.
CREATE ROLE IF NOT EXISTS report_reader
WITH PASSWORD = 'REPLACE_WITH_A_UNIQUE_LAB_SECRET'
AND LOGIN = true;

-- View roles that the current account is permitted to list.
LIST ROLES;
~~~

The string `REPLACE_WITH_A_UNIQUE_LAB_SECRET` **is only a placeholder**, not a password to actually use. Because `CREATE ROLE ... PASSWORD ...` contains a plaintext secret, real workflows should restrict/control command history, log visibility, TLS transport, script files, and audit logs. Use your organization's role provisioning or secret management tools when available.

**Note:** a role with `LOGIN = true` does not automatically mean it can read every table. CQL permissions are granted independently. In many systems, it is best practice to create a non-login permission role and then grant that role to login identities sharing those permissions.

### 3.2. Example: Granting Least Privilege on a Table

To keep the lab self-contained, assume an administrative session is connected to a **single-node** cluster. Create a keyspace and table for the query "read a device's events by day":

~~~sql
CREATE KEYSPACE IF NOT EXISTS security_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS security_lab.readings_by_device_day (
  device_id text,
  reading_day date,
  reading_time timestamp,
  reading_id uuid,
  value double,
  PRIMARY KEY ((device_id, reading_day), reading_time, reading_id)
) WITH CLUSTERING ORDER BY (reading_time DESC, reading_id ASC);

INSERT INTO security_lab.readings_by_device_day
  (device_id, reading_day, reading_time, reading_id, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 25.1);

INSERT INTO security_lab.readings_by_device_day
  (device_id, reading_day, reading_time, reading_id, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 25.3);

GRANT SELECT ON TABLE security_lab.readings_by_device_day
TO report_reader;
~~~

`SimpleStrategy`/RF = 1 is strictly for a single-node lab. In real clusters, evaluate `NetworkTopologyStrategy` with replica counts per actual datacenter; the replica count is unrelated to which permissions a role holds.

Using the read-only role, connect in a separate session and run:

~~~sql
SELECT reading_time, value
FROM security_lab.readings_by_device_day
WHERE device_id = 'sensor-01'
  AND reading_day = '2026-11-21'
LIMIT 10;
~~~

Expected result: two rows with valid readings, newest timestamp first due to clustering order. The `WHERE` clause includes the **composite partition key** `(device_id, reading_day)`, matching the query-driven table design.

Attempt an unpermitted operation:

~~~sql
-- Execute as report_reader, not an admin account.
INSERT INTO security_lab.readings_by_device_day
  (device_id, reading_day, reading_time, reading_id, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:10:00Z',
        33333333-3333-4333-8333-333333333333, 25.7);
~~~

When the role is granted only `SELECT`, the `INSERT` statement must be rejected (typically with `Unauthorized`). If it still succeeds, check the authorizer, superuser flag, role inheritance, and previously granted permissions. Do not draw conclusions from a single `GRANT` line while overlooking inherited permissions.

### 3.3. GRANT/REVOKE and Permission Verification

~~~sql
-- Run from an admin session when checking permissions.
LIST ALL PERMISSIONS OF report_reader;

-- Example command to revoke permission when business requirements change.
REVOKE SELECT ON TABLE security_lab.readings_by_device_day
FROM report_reader;

-- Restore permission for subsequent practice steps.
GRANT SELECT ON TABLE security_lab.readings_by_device_day
TO report_reader;
~~~

Some permission options and `LIST ... PERMISSIONS` output formats vary across versions. Right after a `GRANT`/`REVOKE`, the authorization cache may delay visibility of changes across nodes; adjust and verify according to cluster configuration. Do not assume `REVOKE` takes immediate effect on every active request.

### 3.4. Auth State and Distributed Systems

When using Cassandra's built-in providers, role/permission data is managed in **`system_auth`**. On multi-node clusters, evaluate the replication of this keyspace so a single-node outage does not disrupt logins or permission management. Configuring `system_auth` replication with an appropriate strategy/datacenter setting is a **separate cluster administration task** that may require repair afterward; never modify system tables directly with ad-hoc `INSERT` statements.

Plan how role/password changes propagate across nodes via caching and replication, and ensure recovery administrative accounts remain usable during configuration changes.

## 4. TLS for Client ↔ Cassandra Connections

TLS protects data (including credentials and query payloads) on the network between client and Cassandra. TLS also lets the client verify the server's genuine certificate; if verification is disabled, an "encrypted" connection can still be intercepted by a rogue server.

### 4.1. Cassandra Server: `client_encryption_options`

Example **illustrating structure only**, for Cassandra versions using JKS-style keystores:

~~~yaml
# cassandra.yaml - illustrative only; paths and secrets are placeholders.
client_encryption_options:
  enabled: true
  optional: false
  require_client_auth: false
  keystore: /secure/cassandra/server-keystore.jks
  keystore_password: "REPLACE_VIA_SECRET_MANAGEMENT"
~~~

Meaning:

- `enabled: true`: enables TLS for native client transport in supported version configurations.
- `optional: false`: requires client connections to use TLS; on versions allowing `optional: true`, both TLS and plaintext clients may be accepted during a controlled migration.
- `keystore`: holds the server's certificate and private key; enforce strict file permissions.
- `keystore_password`: secret supplied via the deployment's **secure secret management mechanism**. The string above is not a real password, and real passwords must never be committed to repositories.
- `require_client_auth: false`: does not require the client to present its own certificate at the TLS layer. Clients may still need to log in using a Cassandra role/password.

**Do not copy the example verbatim into production.** Syntax, option names, and keystore/PEM formats can vary by Cassandra/Java version. Some releases support additional certificate configurations or formats; check documentation for your exact version, secret delivery mechanism, and certificate setup.

### 4.2. Verifying the Server Certificate: CA, SAN, and Hostname

When connecting to `db.example.internal`:

1. The client opens TCP to the right native host/port.
2. If the server requires TLS, it sends its server certificate during the handshake.
3. The client verifies the **trusted CA chain**, validity period, key usage, and target destination name (typically via **SAN**, Subject Alternative Name).
4. Only if verification succeeds does the native protocol proceed with auth/CQL over the protected channel.

For example, if a certificate is issued for `db-a.example.internal`, a Java client connecting by IP `10.0.2.15` may fail hostname verification if the certificate lacks a matching **IP SAN**. Switching to another IP does not fix the certificate. Use a DNS name listed in the SAN or issue certificates matching the application endpoints.

In a multi-node cluster, the driver may connect to **discovered peer native endpoints**. Each node/endpoint's certificate must match the address used by the client, especially with DNS, NAT, Kubernetes, or proxies. Reaching the first contact point does not prove every peer will pass TLS.

### 4.3. mTLS: Mutual Certificates

If an organization requires clients to present their own certificates, server configuration may include:

~~~yaml
# Additions for configurations/versions supporting mTLS.
client_encryption_options:
  enabled: true
  optional: false
  require_client_auth: true
  keystore: /secure/cassandra/server-keystore.jks
  keystore_password: "REPLACE_VIA_SECRET_MANAGEMENT"
  truststore: /secure/cassandra/client-ca-truststore.jks
  truststore_password: "REPLACE_VIA_SECRET_MANAGEMENT"
~~~

`require_client_auth: true` requires the client to present a valid TLS certificate, and the server must trust the client's CA via the appropriate truststore. At that point, the Java Driver/cqlsh must provide a **client certificate + private key** using the SSL API/config supported by its version.

**mTLS does not by default map a certificate's Subject DN to a Cassandra role.** If Cassandra still uses `PasswordAuthenticator`, the client may have to supply **both a TLS certificate and a username/password**. If using a certificate-based authenticator supported by your version or environment, explicitly define certificate-to-role mapping and certificate revocation/management.

### 4.4. Which Port Does Native TLS Use?

Normally, native CQL uses `9042/TCP`, and Cassandra can configure TLS **directly on this port**. Some historical releases/configs offer an additional dedicated native TLS port commonly illustrated as **9142**, but a secondary port **is not guaranteed to exist**; in Cassandra 5.0, the `native_transport_port_ssl` option is marked deprecated.

Do not assume `9042 = plaintext` or `9142 = always TLS`. Confirm the listener and `client_encryption_options` on the running server, then test the TLS handshake.

**Internode TLS is a separate path:** `server_encryption_options` protects node-to-node communication, typically over `storage_port` (default 7000); legacy internode TLS port 7001 is used only if explicitly configured by the deployment. Enabling native TLS does not automatically encrypt the internode network.

## 5. cqlsh: Secure Connections and Credential Management

### 5.1. Connecting When Only Username/Password Is Required

From a machine with cqlsh:

~~~bash
# Server enables PasswordAuthenticator without requiring TLS: suitable only for isolated labs.
cqlsh 127.0.0.1 9042 -u report_reader
~~~

Depending on the version, cqlsh prompts for the password when `-p` is omitted, or uses an appropriate credentials file. **Avoid passing passwords directly on the command line**, as they can be exposed in shell history, process lists, or monitoring logs.

Never send plaintext password logins over untrusted networks: native protocol credentials should be protected by TLS.

### 5.2. Connecting with TLS and CA Verification

~~~bash
# Connect to native transport with TLS enabled.
cqlsh db.example.internal 9042 --ssl -u report_reader
~~~

In cqlsh versions supporting `cqlshrc`, the TLS section may look like:

~~~ini
# Example [ssl] section in cqlshrc (verify against your cqlsh version).
[ssl]
validate = true
certfile = /secure/ca/cassandra-ca.pem
~~~

`validate = true` requires server certificate validation according to the running cqlsh version's behavior; `certfile` specifies the trusted CA certificate in versions using this format. **Verify hostname/SAN handling and actual verification policy as well**: cqlsh's hostname checking can vary across TLS libraries/versions, so do not assume `--ssl` alone suffices to verify server identity. Never disable certificate verification as a permanent fix for CA errors.

Depending on the version, cqlsh supports configuring user/cert/key, protected credentials files, or other auth mechanisms. Consult `cqlsh --help` and the `cqlshrc` guide for your Cassandra version; avoid committing a `cqlshrc` containing plaintext passwords or private keys. In mTLS environments, also configure the client certificate and private key per your cqlsh version.

### 5.3. Verifying After Login

~~~sql
SHOW HOST;
SHOW VERSION;

-- Session verification query if the role has appropriate permissions.
SELECT reading_time, value
FROM security_lab.readings_by_device_day
WHERE device_id = 'sensor-01'
  AND reading_day = '2026-11-21';
~~~

A session without `CREATE`/`ALTER`/`MODIFY` can still query tables on which it holds `SELECT`. Logging in successfully does not mean you can view the entire keyspace; to catch missing permissions, test the **exact queries your application needs to run**.

## 6. Java Driver 4.x: TLS, Credentials, and Parameterized Queries

Suppose the organization has issued a CA and configured a JVM truststore containing the trusted CA certificate. The Java snippet below illustrates Java Driver 4.x with `PasswordAuthenticator`, TLS server authentication, and a prepared statement:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import javax.net.ssl.SSLContext;
import java.net.InetSocketAddress;
import java.time.LocalDate;

public final class CassandraTlsDemo {
    public static void main(String[] args) throws Exception {
        String host = System.getenv("CASSANDRA_HOST");
        String dc = System.getenv("CASSANDRA_DC");
        String username = System.getenv("CASSANDRA_USER");
        String password = System.getenv("CASSANDRA_PASSWORD");
        if (host == null || dc == null || username == null || password == null) {
            throw new IllegalStateException("Missing Cassandra connection configuration");
        }

        // Default SSLContext relies on the JVM truststore.
        // Configure a trusted CA and hostname verification for real environments.
        SSLContext tlsContext = SSLContext.getDefault();

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, 9042))
                .withLocalDatacenter(dc)
                .withAuthCredentials(username, password)
                .withSslContext(tlsContext)
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT reading_time, value " +
                "FROM security_lab.readings_by_device_day " +
                "WHERE device_id = ? AND reading_day = ?");

            for (Row row : session.execute(
                    query.bind("sensor-01", LocalDate.of(2026, 11, 21)))) {
                System.out.println(
                    row.getInstant("reading_time") + " : " +
                    row.getDouble("value"));
            }
        }
    }
}
~~~

**Prerequisites to run the example:**

- Created `security_lab.readings_by_device_day` and granted `SELECT` to `report_reader` as in Section 3.
- Cluster has TLS and role/password enabled; `CASSANDRA_HOST` is a **reachable native endpoint**, and `CASSANDRA_DC` matches the real datacenter name. You can check `SELECT data_center FROM system.local;` from a suitable admin/cqlsh session.
- The JVM is configured with a **truststore containing the right CA**; calling `SSLContext.getDefault()` alone does not automatically add an organization's internal CA to the JVM.
- Java Driver 4.x TLS config must explicitly enable **hostname verification** matching the driver config and endpoints in use. A default `SSLContext` **is not a guarantee of every hostname verification policy**; check driver documentation and run negative tests.
- If Cassandra requires **mTLS**, you must also load the client key/certificate into the `SSLContext`; a truststore for server verification alone is insufficient.

Environment variables clarify inputs but **are not a secret management system**: in production, retrieve passwords/tokens/certificates from your organization's secret manager, restrict read permissions on environment variables or mounted files, and never log secrets.

`CqlSession` should be long-lived and reused in a service; `try-with-resources` here closes the session when the demo program exits. The Java Driver may discover multiple peer native endpoints, so certificates, routing, and permissions must be consistent across **all nodes the client is permitted to connect to**. If the app connects to the contact point yet fails on peers, check `broadcast_rpc_address`, NAT, DNS, TLS certificates, and local datacenter.

### 6.1. Separating TLS Errors from Query, Replication, and Consistency Issues

When the Java Driver reports `AllNodesFailedException`, do not blame every failure on the password. Per-node causes may include DNS, port, TLS, native protocol mismatch, auth, or an unreachable endpoint. If the connection succeeds yet returns `ReadTimeout`, `WriteTimeout`, or `Unavailable`, inspect replicas, consistency, internode networking, and system load. Raising RF or changing CL will not fix certificate errors; changing a password will not fix a partition key.

## 7. Credential and Certificate Lifecycle Management

### 7.1. Principle of Least Privilege

In practice, separate roles:

| Role | Characteristics | Example Permissions |
| --- | --- | --- |
| **Controlled operational admin** | Manages schemas/roles via approved processes. | Permission to create roles, alter keyspaces/tables when genuinely needed. |
| **Application reader** | Login for read-only services. | `SELECT` on the tables the service reads. |
| **Application writer** | Login for write services. | `MODIFY`/`SELECT` per actual queries, restricted to required resources. |
| **Permission group role** | `LOGIN = false`, used as a permission bundle. | Granted CQL permissions and then granted to appropriate login roles. |

Do not share a single superuser account across all applications; avoid reusing passwords across environments. Grant permissions at the **TABLE** scope whenever possible, widening to KEYSPACE only when there is a clear business requirement.

### 7.2. Password Rotation

In username/password environments, role password changes can be managed with the appropriate CQL command (executed from an authorized account):

~~~sql
-- Syntax example only; placeholder is NOT a real password.
ALTER ROLE report_reader
WITH PASSWORD = 'REPLACE_WITH_NEW_UNIQUE_SECRET';
~~~

If a password is changed in place while applications are running, already-authenticated native connections may stay alive for some time while new connections using the old secret fail. Therefore, coordinate your secret manager with rollout/connection refresh procedures. For high availability, consider a **dual-identity rotation pattern**: grant equivalent permissions, deploy the new credential, verify traffic succeeds on the new credential, and then revoke the old one. Do not assume password rotation is atomic across all live connections.

**Never store real passwords in `.cql` files committed to Git**, shell histories, screenshots, tickets, or trace outputs. Also consider that system/monitoring logs might capture CQL statements containing secrets when creating roles.

### 7.3. Certificate and CA Rotation

A typical process includes:

1. Prepare the new CA/truststore and server/client certificates with SANs matching real endpoints.
2. Include a **trust overlap period** if changing CAs so clients trust both old and new certificates during a rolling rollout.
3. Deploy truststores/keystores/configs on servers and clients according to version, ensuring valid reload/restart management.
4. Test TLS against **multiple nodes**, including peers after driver discovery, not just a single contact point.
5. Once migration is verified complete, remove old CAs/certs and update issuance/revocation procedures.

Expired TLS certificates, missing SANs, or untrusted CAs usually cause **handshake** errors before Cassandra even checks the role/password. Clock skew on a node or client can make a certificate appear not-yet-valid or expired; check time synchronization when encountering validity-period errors.

## 8. Layer-by-Layer Troubleshooting

~~~mermaid
flowchart TD
    A["Java/cqlsh client connects to host:9042"] --> B{"Are DNS/IP and TCP reachable?"}
    B -->|"No"| C["Check hostname, listener, firewall, routing, container"]
    B -->|"Yes"| D{"Does server require TLS?"}
    D -->|"Yes"| E{"Do TLS handshake and verification succeed?"}
    E -->|"No"| F["Check CA, SAN/hostname, keystore, TLS mode, mTLS"]
    E -->|"Yes"| G{"Does Cassandra login succeed?"}
    D -->|"No"| G
    G -->|"No"| H["Check authenticator, role LOGIN, password, auth backend"]
    G -->|"Yes"| I{"Is CQL authorized?"}
    I -->|"No"| J["Check authorizer, GRANT/REVOKE, role inheritance"]
    I -->|"Yes"| K["Check query, partition key, RF, consistency, replicas"]
~~~

| Symptom | Likely Error Layer | What to Check |
| --- | --- | --- |
| `Connection refused` on 9042 | Native listener/TCP | Host/IP/port, `start_native_transport`, `rpc_address`, firewall reject. |
| TCP timeout | Routing/firewall/container/cloud security group | Test from **the client machine itself** to target IP and port. |
| `SSLHandshakeException` or `certificate verify failed` | TLS | Do client/server agree on TLS mode? CA, certificate chain, expiration, SAN/hostname, mTLS keypair. |
| `wrong version number` or equivalent | TLS mismatch/wrong port | One side speaks plaintext while the other speaks TLS; verify native TLS port. |
| `AuthenticationException` / bad credentials message | Authentication | `PasswordAuthenticator`, role `LOGIN`, current password, account state, auth keyspace. |
| `Unauthorized` on `SELECT` / `INSERT` | Authorization | `CassandraAuthorizer`, table/keyspace grants, role inheritance/cache, actual user in use. |
| Admin can log in but app cannot | App credentials/role/config | Compare endpoint, TLS, username, role privileges, and secrets deployed to the app. |
| Contact point connects but other peers fail | Topology/native endpoints | `broadcast_rpc_address`, DNS, routing, per-peer certs, local DC, and driver logs. |
| `ReadTimeout`, `WriteTimeout`, `Unavailable` | Replicas/CL/internode path | Replication factor, consistency, available replicas, load, compaction, port 7000 network. |
| Query missing partition key or filtering rejected | CQL and table design | `DESCRIBE TABLE`, primary key, query pattern; do not edit TLS/GRANT to fix this. |
| `nodetool` cannot connect while cqlsh works | JMX/administration | Separate JMX/7199 config and admin permissions; do not confuse with native 9042. |

### 8.1. Test TCP and TLS Before Changing Passwords

On Linux/macOS, from the client machine:

~~~bash
# TCP check only.
nc -vz db.example.internal 9042

# With a server actually running TLS: test handshake and specify trusted CA.
# Some OpenSSL builds support -verify_hostname; check openssl s_client -help.
openssl s_client \
  -connect db.example.internal:9042 \
  -servername db.example.internal \
  -CAfile /secure/ca/cassandra-ca.pem \
  -verify_return_error \
  -verify_hostname db.example.internal
~~~

On Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName db.example.internal -Port 9042
~~~

`nc` and `Test-NetConnection` prove only that TCP can open; they do not verify TLS, native handshake, CQL login, or permissions. `openssl s_client` tests TLS and verifies per the passed options, **without checking CQL permissions**. `-servername` sends SNI; it does not perform hostname verification unless an appropriate name-verification option is enabled.

### 8.2. Verify Permissions Using the Application Identity Itself

Suppose the app uses `report_reader`: run the exact `SELECT` query on the table the app needs, then test a disallowed write operation in the **lab**. If `SELECT` succeeds while `INSERT` raises `Unauthorized`, both authentication and authorization work as designed for read-only access.

For role/permission issues, inspect logs and auth/cache settings for your version. Never test with an admin account and conclude the application has the same permissions. After changing permissions or passwords, monitor cluster propagation/caching delays and differences between existing and new connections.

## 9. Self-Practice Exercises

1. Diagram the flow **TCP → TLS → PasswordAuthenticator → CassandraAuthorizer → coordinator/replica**. Indicate which step returns an error if the CA is untrusted, the password is wrong, or the role lacks `SELECT`.
2. Configure a lab with username/password enabled and create role `report_reader` with only `SELECT` on `security_lab.readings_by_device_day`. Verify the role cannot execute `INSERT`.
3. Use `cqlsh -u report_reader --ssl` with a trusted CA per your cqlsh version. Explain why `--ssl` and username/password serve distinct roles.
4. Suppose the server certificate only has SAN `db-a.example.internal` while the application connects by IP. Predict the error and propose a fix that preserves hostname verification.
5. On a multi-node cluster, `db-a` has a valid cert while `db-b`'s cert is expired. Why can the Java Driver connect to the contact point and then fail on a peer? Which endpoints must be checked?
6. Distinguish `client_encryption_options` and `server_encryption_options`. Why does client TLS on 9042 not automatically protect gossip/streaming on 7000?
7. With `require_client_auth: true` and `PasswordAuthenticator`, explain why a client may need both a client certificate and a username/password.
8. Describe a password rotation workflow that avoids disconnecting all clients simultaneously; outline using two transitional roles and verifying least-privilege permissions.
9. In the Java Driver, configure `SSLContext`, credentials, and a prepared statement; explain why both the truststore and local datacenter must be configured accurately.
10. Suppose login succeeds yet `SELECT` returns `ReadTimeout` at `LOCAL_QUORUM`. Why will changing the password not resolve the error? How should you inspect replication, replicas, and internode networking?

**Completion criteria:** distinguish TLS, authentication, and authorization; grant and verify least-privilege permissions; establish cqlsh/Java connections with a trusted CA; recognize handshake, credential, permission, and query errors; and explain why security configurations must be consistent across the cluster.

## References

- [Apache Cassandra — Security](https://cassandra.apache.org/doc/stable/cassandra/operating/security.html): authentication, authorization, and transport security mechanisms.
- [Apache Cassandra — cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `authenticator`, `authorizer`, `client_encryption_options`, `server_encryption_options`.
- [Apache Cassandra — Database Roles](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/security.html): creating roles, permissions, `GRANT`, `REVOKE`.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `--ssl`, username/password, cqlshrc, and inspection commands.
- [Apache Cassandra Java Driver 4.x — Authentication](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/authentication/index.html): auth providers and credentials.
- [Apache Cassandra Java Driver 4.x — SSL](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/ssl/index.html): SSL context, truststores, keystores, and client configuration.
- [OWASP — TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): chain/hostname verification, private keys, and TLS security practices.

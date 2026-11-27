# TLS for Client-to-Node and Internode Connections

> **Chapter:** Security  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra and the distributed wide-column model: partition keys, query-driven table design, read/write consistency, CQL, replication, compaction, repair, troubleshooting, and Java application connectivity.

Apache Cassandra communicates over two very different network paths: applications/drivers talk to nodes over the **native protocol**, while nodes exchange mutations, read responses, gossip/coordination, and streaming data over **internode connections**. If you only enable TLS for applications, traffic between replicas can still traverse the network unencrypted. Conversely, enabling TLS only between nodes does not protect passwords or CQL data sent from applications to the coordinator.

This lesson explains how to secure **both paths** with TLS, choose appropriate certificate-verification levels, execute safe rollouts, test connections from Java Driver/cqlsh, and manage certificate/key renewal and rotation lifecycles. The focus is understanding **actual protection boundaries**, rather than just setting `enabled: true` and assuming the cluster is secure.

> **Version note:** configuration keys are illustrated primarily for Apache Cassandra 4.x–5.x. Cassandra 3.11 and vendor distributions/managed services may differ in syntax, TLS ports, and certificate reloading. Inspect your `cassandra.yaml`, exact release docs, and running parameters, and test in a staging cluster before changing production. YAML snippets are conceptual examples, **not complete files to use verbatim**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **client-to-node TLS**, **internode TLS**, **mTLS**, and **CQL authentication/authorization**.
2. Understand server certificates, private keys, CA chains, keystores, truststores, Subject Alternative Names (SANs), expiration, and hostname verification.
3. Read `client_encryption_options` and `server_encryption_options`; choose `internode_encryption` levels that match security requirements.
4. Explain when `optional: true` is useful during transitions and why it **must not stay enabled long-term** when policy requires mandatory encryption.
5. Configure Java Driver 4.x and `cqlsh`, and verify TLS handshakes/certificates without exposing secrets.
6. Plan deployment/rotation/recovery with verification steps, rollback, and monitoring for latency, CPU, connection, and repair/streaming impacts.

## 2. Threat Model: What TLS Protects and What It Does Not

### 2.1. Two Independent Communication Paths

~~~mermaid
flowchart TB
    App["Java service / cqlsh"] -- "Native protocol: client-to-node TLS" --> C["Node A: coordinator"]
    C -- "Internode TLS" --> B["Node B: replica"]
    C -- "Internode TLS" --> D["Node C: replica"]
    B -. "Streaming / repair / replication" .- D
    K["CA / PKI + secret manager"] -. "Cert chain and key" .-> App
    K -. "Cert chain and key" .-> C
    K -. "Cert chain and key" .-> B
    K -. "Cert chain and key" .-> D
~~~

| Path | Purpose | Main Cassandra Config | What Needs Verification |
|---|---|---|---|
| **Client → node** | Applications send CQL, bind values, receive data | `client_encryption_options` | Client verifies server certificate; with mTLS, server also verifies client cert |
| **Node ↔ node** | Replica messaging, distributed reads/writes, internode operations | `server_encryption_options` | Peers establish TLS; identity verification depends on mTLS/endpoint verification |
| **JMX/admin** | Monitoring, running admin tools | Separate JMX/JVM config | Not automatically protected by enabling the two sections above |
| **SSH, backup object store, KMS, other apps** | Operations or backup transfers | Separate tools/mechanisms | Must be audited independently |

TLS **protects data in transit**, provides peer authentication per chain/trust policy, and preserves TLS record integrity. TLS does **not** replace:

- Cassandra **Authentication**: verifying which CQL user/role is logging in, e.g., via `PasswordAuthenticator`.
- **Authorization**: which user/role may run `SELECT`, `MODIFY`, `ALTER`, etc., e.g., via `CassandraAuthorizer`.
- **Encryption at rest**: encrypting SSTables, commit logs, backups, and secret stores; TLS only protects data **in transit**.
- **Firewalls/segmentation**: internode, native transport, and JMX networks must still restrict source access.
- **Backups/repair**: TLS does not turn a replica missing data into a synchronized replica.

### 2.2. Three Commonly Confused Verification Modes

1. **Encryption without peer identity verification:** data is encrypted, yet if the client trusts every certificate or disables hostname verification, connections can be spoofed in certain threat models. Avoid "trust-all" settings.
2. **Server-authenticated TLS:** the client only trusts certificates signed by a valid CA and checks that SAN matches the target name/IP. This is the baseline for most applications.
3. **Mutual TLS (mTLS):** the server also requires the client to present a certificate signed by a trusted CA; each peer proves its identity with its private key. Use mTLS for clients or internode when policy requires, though **mTLS does not grant CQL permissions by itself** unless certificate-to-identity/role mapping is configured and verified.

**Example:** Java Driver completing mTLS with a CQL account lacking `SELECT` must still have its query denied. Conversely, valid username/password credentials on a TLS connection that does not trust the node's CA will fail **before** CQL execution.

## 3. Certificates and Keys: Identity, Validity Window, and Access Permissions

### 3.1. Required Components

| Component | Contents | Used By | Protection |
|---|---|---|---|
| **Server certificate** | Public key, DNS/IP names in SAN, CA issuer, validity dates | Node serving TLS, verifying clients | Distributable to relying parties per PKI |
| **Server private key** | Secret key paired with the certificate | Node signing/proving identity | Secret manager, volume ACLs, never commit to Git |
| **CA certificate/chain** | Trust anchor/intermediates | Java, cqlsh, nodes | Controlled distribution; verify exact CA |
| **Truststore** | Trusted CAs/certificates | **Verifying** peer | Protect integrity; avoid adding unintended CAs |
| **Keystore** | Cert chain and usually private key | **Presenting** peer | Restrict read access; protect password/secret ref |
| **Passphrase** | Unlocks keystore/private key | Node/client process loading the key | Manage outside source code; never print to logs |

Java can use JKS or PKCS#12; modern Cassandra also supports PEM-based SSL context configuration via an appropriate factory. **File extensions do not decide** the format: `store_type`/factory, chain, and password must match. On Kubernetes, certs/keys may be mounted from Secrets or KMS/secret-manager integrations; still verify process file-read permissions.

**SAN matters more than display names:** if the driver connects to `db-1.internal.example`, the node cert must carry that DNS SAN—or the corresponding IP SAN if connecting by IP with hostname verification enabled. Relying solely on Common Name (CN) is unsuitable for modern TLS.

### 3.2. Inspecting Certificates Without Exposing Private Keys

In a lab with public certificate files:

~~~bash
# Check validity dates, issuer, subject, and Subject Alternative Names.
openssl x509 -in server-cert.pem \
  -noout -dates -issuer -subject -ext subjectAltName

# Inspect an authorized keystore; keytool prompts for the password.
keytool -list -v -keystore server-keystore.p12 -storetype PKCS12
~~~

Never put `-storepass <password>` in commands saved in shell history, CI logs, or documentation. In production, use secret injection/protected password files per your Cassandra release. **Never enable `-nodes` or export plaintext private keys** just for a quick experiment on a real cluster.

### 3.3. CAs and Certificates for Internode

In a multi-node/multi-DC cluster, each node typically has its **own PKI identity**, a truststore trusting the CA issuing valid node certificates, and SANs matching real connection endpoints. If multiple nodes share one private key, compromising one node enables impersonating others; understand your policy and avoid casual sharing.

Distinguish:

- **Per-node certificates**: easier revocation, lifecycle control, and per-node auditing.
- **Dedicated internode CA**: confines cluster trust boundaries, allowing a separate CA for client mTLS.
- **Outbound keystore** (on supporting releases): specifies the certificate a node presents when **acting as a client** in internode mTLS; verify defaults or unset behavior against your actual config docs.
- **Endpoint verification**: validates peer identity against the connected endpoint; ensure accurate SANs **before** enabling it to avoid splitting the cluster on hostname errors.

Simply trusting a CA does not guarantee only valid Cassandra nodes hold certificates: if a shared CA signs certs for many services, mTLS can accept unintended identities unless endpoint verification or additional authorization is configured properly. PKI and CA scoping are part of the threat model.

## 4. Application TLS: `client_encryption_options`

### 4.1. Differences Between `enabled`, `optional`, and `require_client_auth`

Client-to-node settings live in `cassandra.yaml`:

| Option | Role | Risk if Misunderstood |
|---|---|---|
| `enabled: true` | Enables TLS support for native transport | Not enough to **enforce** TLS if `optional: true` |
| `optional: false` | Once TLS is enabled, disallows plaintext on the protected port | Legacy clients without TLS configured will fail to connect |
| `optional: true` | Allows both TLS and plaintext during compatibility/transition phases | Fails "all CQL must be encrypted" policies if left enabled |
| `keystore`, keystore credentials | Source of cert/private key presented by the node | Wrong path/password/format breaks TLS handshakes or node startup |
| `require_client_auth: true` | Requires clients to present a trusted certificate (mTLS) | Any driver/cqlsh without a client cert is rejected |
| `truststore` when mTLS is enabled | CAs/certs trusted by the node to verify clients | Overly broad truststores accept unintended identities |

**Production target illustration enforcing TLS with server authentication:**

~~~yaml
# Illustrative block only. Secrets must be supplied via a supported mechanism
# for your exact Cassandra release. Never keep plaintext passwords in Git.
client_encryption_options:
  enabled: true
  optional: false
  keystore: /etc/cassandra/tls/native-server.p12
  # keystore_password: supplied securely, never printed here
  store_type: PKCS12
  require_client_auth: false
~~~

In this example, the server **does not require client certificates**, yet applications should still verify the server's CA/SAN. If mTLS is required, set `require_client_auth: true`, configure an appropriate truststore, and issue certs/keys to applications. Check release docs for `SSLContextFactory` fields and secret/password-file syntax; **never treat YAML comments as a runnable config**.

### 4.2. Native Transport Port

Native protocol typically uses **9042/TCP** (`native_transport_port`), though it can be configured differently. In many 4.x releases, `enabled: true` with `optional: true` serves both TLS and plaintext on the same port. Older releases had a separate `native_transport_port_ssl` option; Cassandra 5.0 docs mark that option **deprecated**. Never rely on 9142 or ports from old tutorials without verifying your actual setup.

**Never expose 9042 to the Internet** just because TLS is enabled. Restrict access via security groups, firewalls, private networks/VPNs, network policies, and least-privilege authentication/authorization.

### 4.3. Verifying from `cqlsh`

With a `cqlsh` version supporting SSL and proper CA config:

~~~bash
# Illustrative command: cert/trust config stored in a protected cqlshrc.
cqlsh db-1.internal.example 9042 --ssl
~~~

Check `cqlshrc` or `cqlsh` SSL flags for your release; with validation enabled, `cqlsh` must verify the certificate/trust chain. **Connecting with `--ssl` alone does not prove hostname validation is active and working**: inspect client validation settings and test against an endpoint with a mismatched certificate to verify rejection.

## 5. Internode TLS: `server_encryption_options`

### 5.1. Choosing Encryption Scope

`server_encryption_options.internode_encryption` controls **which peer types** use encrypted connections. Common values:

| Value | General Meaning | When Appropriate |
|---|---|---|
| `none` | Does not actively encrypt internode links | Isolated test environments only; fails full-encryption requirements |
| `dc` | Encrypts cross-datacenter connections; intra-DC may stay plaintext | When policy only requires protecting inter-DC traffic and intra-DC risk is accepted |
| `rack` | Encrypts cross-rack connections; intra-rack may stay plaintext | Depends on reliable topology/rack metadata; does not guarantee encrypting all nodes |
| `all` | Encrypts all internode connections | Clear choice when policy requires encrypting all peer traffic |

For instance, with RF=3 and all three replicas in `dc1`, setting `internode_encryption: dc` does **not** encrypt mutations among those three replicas because they share a DC. Likewise, `rack` relies on rack assignments; misconfigured snitches/racks leave security gaps. When the goal is zero plaintext on the internode network, use `all` alongside certificate/compatibility controls.

### 5.2. Mandatory Internode TLS Example

~~~yaml
# Illustrates target state of a lab cluster with certs issued for all nodes.
server_encryption_options:
  internode_encryption: all
  optional: false
  keystore: /etc/cassandra/tls/node-internode.p12
  # keystore_password: retrieved from secret manager/valid password file
  store_type: PKCS12
  require_client_auth: true
  truststore: /etc/cassandra/tls/internode-trust.p12
  # truststore_password: supplied securely outside source code
  require_endpoint_verification: true
~~~

This is a **target model**, not a snippet to paste straight into production: with `require_client_auth: true`, peers need client-capable certs when connecting to other nodes, with valid trust chains and endpoint SANs. Some releases have separate outbound keystore/`SSLContextFactory` settings. Check field names and support in your installed `cassandra.yaml`.

**Benefits:** eliminates plaintext peer traffic per policy. **Costs:** TLS handshakes, crypto CPU, certificate validation, cert/CA lifecycle overhead, and outages if certs expire. Never assume TLS explains every latency spike; measure CPU, p95/p99, network, and handshake counts.

### 5.3. Internode Ports and Legacy Differences

Internode traffic traditionally uses **7000/TCP** (`storage_port`); some older setups used a separate TLS port **7001/TCP** (`ssl_storage_port`). Since Cassandra 4.0, a separate internode SSL port is **legacy/deprecated**, and a single port can handle secure connections depending on supported features. Never assume "traffic on 7000 means plaintext" or "7001 closed means TLS is off." **Verify release docs, active configs, logs, and handshake/telemetry** instead of guessing by port number.

### 5.4. Does TLS Eliminate All Peer-Communication Risks?

No. Even with TLS:

- A node with a stolen private key remains a threat; revoke/rotate and isolate the node.
- If `require_endpoint_verification` is disabled, CA checks provide only partial identity assurance.
- A node compromised **after** TLS termination can still read and write data allowed to node operations.
- Firewalls, JMX/SSH admin rights, auditing, credential hygiene, and keyspace RF/repair still matter.
- Internode TLS does not automatically enable TLS on the native CQL or JMX ports.

## 6. Phased Rollout Plan to Avoid Splitting the Cluster

### 6.1. Why Not Enforce Everything Immediately?

Suppose nodes A/B/C are talking plaintext. Changing only A to `internode_encryption: all` with `optional: false` before B/C accept TLS leaves A **unable to connect to its legacy peers**. Simultaneously, application clients without TLS will be rejected if nodes switch to `client_encryption_options.optional: false`.

Modern Cassandra therefore supports **temporary mixed TLS/plaintext** during rollout stages; configuration docs describe a two-phase transition.

### 6.2. Preparation Phase

1. Inventory **Cassandra release/JVM**, node count, DCs/racks, seeds/routing, active ports, driver/cqlsh versions, and network ACLs.
2. Issue certificates via CA/PKI with unique node private keys; verify SANs, issuers, expirations, EKU/key usage, and chains; protect secrets from issuance onward.
3. Deliver keystore/truststore files to each node via secret manager/volume with proper ownership and permissions; verify the Cassandra process can read them.
4. Distribute truststores/CAs to all Java services, test driver TLS and hostname verification in staging; prepare client certs if using mTLS.
5. Configure alerts for cert expiration, handshake failures, native connection failures, internode dropped messages, and latency/CPU; prepare rollback and a maintenance window.
6. Check `nodetool status`, schema agreement, Up replicas, and baseline read/write throughput. Avoid simultaneously changing compaction, RF, or upgrading versions unnecessarily.

### 6.3. Temporary Compatibility Phase

Per Cassandra 4.x/5.x documentation, a common transition path is:

~~~yaml
# Transitional state, NOT a long-term security target.
client_encryption_options:
  enabled: true
  optional: true
  keystore: /etc/cassandra/tls/native-server.p12

server_encryption_options:
  internode_encryption: all
  optional: true
  keystore: /etc/cassandra/tls/node-internode.p12
~~~

Each block also requires passwords/SSL factories/trust stores and version-specific fields. **Note:** this illustrates a mixed deployment state, not a claim that all connections are already encrypted. After rolling out/restarting per release procedure, verify nodes/clients can transition to TLS without connection failures.

The `optional: true` phase weakens security guarantees: **plaintext is still accepted**. Set a deadline, measure remaining legacy clients, block plaintext ingress where appropriate, and switch to mandatory mode as soon as all components support it.

### 6.4. Switching to Mandatory Mode and mTLS

Once all nodes and clients are ready:

1. Switch clients to TLS with CA/SAN validation; monitor handshakes, connections, p99, errors, and reconnects.
2. Set `client_encryption_options.optional: false` once zero plaintext clients remain; for client mTLS, provision client certs/CAs and verify drivers before setting `require_client_auth: true`.
3. Once internode TLS compatibility is confirmed, set `server_encryption_options.optional: false` across nodes following the **rolling/restart runbook**. For mTLS, ensure peer truststores and outbound certs are ready.
4. Check `nodetool status` from different nodes, replica reachability, Java reads/writes at expected CL, repair/streaming in a test window, and network/CPU metrics.
5. Confirm **plaintext connections are rejected**, invalid certs are rejected, and valid certs succeed. Declare policy compliance only after these checks pass.

### 6.5. Before/After Criteria Table

| Evidence | Before Rollout | Target After Rollout |
|---|---|---|
| Client connections | May include plaintext | Mandatory TLS with hostname/CA validation |
| Internode connections | Varies (`dc`/`rack`/`none`) | If required by policy: `internode_encryption: all`, `optional: false` |
| Authentication | Valid CQL roles/permissions | Preserved or upgraded per policy without breaking access |
| Network | Properly scoped ACLs | Source restrictions intact; 9042/JMX not exposed |
| Cert inventory | Incomplete or unmonitored | Every endpoint has cert chain/SAN/expiry and rotation owner |
| Negative conditions | Legacy TLS clients unready | Plaintext/wrong CA/wrong hostname/missing mTLS cert rejected |
| Performance | p50/p95/p99, CPU, error baseline | SLOs do not degrade beyond acceptable thresholds |

Never cite an all-UN `nodetool status` as proof TLS is active: nodes stay Up even when clients are allowed plaintext. Verify **actual connection paths and configurations**.

## 7. Java Driver 4.x: Enabling TLS and Verifying the Server

### 7.1. Configuring Connections with a CA

Java Driver 4.x example via `application.conf`, loaded from a protected configuration area:

~~~hocon
datastax-java-driver {
  basic.contact-points = ["db-1.internal.example:9042"]
  basic.load-balancing-policy.local-datacenter = "dc1"

  advanced.ssl-engine-factory {
    class = DefaultSslEngineFactory
    truststore-path = "/run/secrets/cassandra/client-truststore.p12"
    truststore-password = "ONLY_FOR_DEMO_REPLACE_WITH_SECRET_SOURCE"
    hostname-validation = true
  }
}
~~~

**Warning:** `ONLY_FOR_DEMO_REPLACE_WITH_SECRET_SOURCE` is a placeholder, not a real password, and must never ship in deployment artifacts. In practice, use a config loader integrated with a secret manager/secure config injection; config key names and provider support may differ by driver 4.x patch release. For PKCS#12 files, verify your running JVM's default keystore type or JSSE configuration; standard 4.x `DefaultSslEngineFactory` does not expose a `truststore-type` option in regular driver config. **Always check the exact DataStax/Apache Java Driver documentation for your version** before running.

With mTLS, the client must also present a valid certificate/private key (e.g., keystore path/type and password from a secure source); providing only a truststore is **not** enough. CQL authentication (username/password/token) is configured separately—never conflate it with TLS certificates.

### 7.2. Building a `CqlSession` from Secure Config in Java

The snippet below assumes an external configuration file holds endpoints, local DC, and the TLS engine factory as above:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.io.File;
import java.util.UUID;

try (CqlSession session = CqlSession.builder()
        .withConfigLoader(
            DriverConfigLoader.fromFile(
                new File("/etc/myapp/cassandra-driver.conf")))
        .build()) {

    PreparedStatement ps = session.prepare(
        "SELECT event_time, event_id, payload " +
        "FROM security_lab.events_by_device WHERE device_id = ?");

    BoundStatement stmt = ps.bind(
        UUID.fromString("d654b0fe-7357-497f-8db4-59b165d58a0f"));

    session.execute(stmt).forEach(row -> {
        // Process only needed fields; never log secrets/sensitive payloads.
        row.getUuid("event_id");
    });
}
~~~

This is an integration snippet, not a standalone program: `security_lab.events_by_device` must exist, and the CQL user/role must hold `SELECT`. If the cluster requires authentication, add an auth provider retrieving credentials from a secure source—**never** write passwords in Java source code. The driver takes contact points, discovers topology, and connects to multiple nodes; therefore **every node endpoint the driver may pick must hold a valid cert** matching its name/IP.

### 7.3. Characteristic Java Connection Errors

| Symptom | Hypothesis to Check | Remediation |
|---|---|---|
| `PKIX path building failed` or untrusted server | Missing CA/intermediate, wrong truststore | Supply exact CA chain; inspect truststore and issuer |
| `No subject alternative names ...` | Host/IP contacted by driver is absent from SAN | Issue cert with matching SAN or fix DNS/endpoints; never disable validation |
| `handshake_failure` | No common TLS version/cipher, missing mTLS cert, bad keystore | Compare TLS/JVM options, cert chains, server/client logs |
| `bad_certificate` / `unknown_ca` | Peer rejects client cert or CA | Inspect mTLS truststore, EKU, and cert expiration |
| `Connection refused` | Port/listener/firewall, node not running | Check native transport, network policy, and port |
| `AuthenticationException` after TLS succeeds | Invalid CQL role/credentials | Check authenticator and credentials; do not alter TLS unnecessarily |
| `UnauthorizedException` | Authenticated, but lacks CQL permission | Check role grants; TLS does not grant SELECT |
| Timeouts when some nodes get new certs | Handshake fails on certain endpoints, driver hops nodes | Inspect certs/trust/hostnames on **all nodes**, not just seeds |

TLS failures **differ** from CL/replication failures: if the driver cannot open connections to most nodes due to invalid certs, the app may see Unavailable/timeouts while the root cause is **reachability/TLS**. Inspect error chains, cert expiration, and node logs.

## 8. Isolated Lab: Proving TLS Is Genuinely Enforced

### 8.1. Prerequisites

Prepare:

- A 3-node lab cluster if testing internode and RF=3; each node has its own cert, complete CA/truststore.
- Java Driver 4.x, `cqlsh`, and OpenSSL/TLS tools; use hostnames matching SANs.
- A simple CQL table with RF matching the real DC name, e.g., `dc1` with three nodes.
- Two test configs—**valid TLS** and **plaintext/invalid cert**—run only inside the test network.

Example CQL in `cqlsh` already connected via TLS:

~~~sql
CREATE KEYSPACE IF NOT EXISTS security_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS security_lab.events_by_device (
  device_id uuid,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO security_lab.events_by_device
  (device_id, event_time, event_id, payload)
VALUES (
  d654b0fe-7357-497f-8db4-59b165d58a0f,
  '2026-11-21T09:00:00Z',
  80aaeac3-1f11-4f66-877f-d9ccfca2216d,
  'tls-lab-event'
);

SELECT event_time, event_id, payload
FROM security_lab.events_by_device
WHERE device_id = d654b0fe-7357-497f-8db4-59b165d58a0f;
~~~

`IF NOT EXISTS` does not alter existing objects; use `DESCRIBE KEYSPACE`/`DESCRIBE TABLE` to inspect schema. Keep CL, data/driver, and conditions identical when comparing before and after TLS. **Never treat a single `SELECT` as an encryption benchmark.**

### 8.2. Testing the Client-to-Node Path

You can test the TLS handshake on the native protocol port:

~~~bash
# On a lab host with the public CA and DNS matching SAN:
openssl s_client \
  -connect db-1.internal.example:9042 \
  -servername db-1.internal.example \
  -CAfile ca-public.pem \
  -verify_return_error
~~~

To check **hostname** specifically, OpenSSL flags depend on release, e.g., `-verify_hostname db-1.internal.example` where supported. `s_client` inspects the cert chain and handshake; it does **not** perform native-protocol authentication/CQL. Check exit codes and verify output carefully—never conclude "secure" solely from seeing `CONNECTED`.

Test three cases:

| Attempt | Expected When TLS Is Mandatory and Validated |
|---|---|
| Client with right CA and matching hostname | TLS handshake succeeds; CQL succeeds only if auth/grants pass |
| Client with wrong CA or mismatched hostname | **Rejected when client validates the certificate** |
| Plaintext client connecting to TLS-only port | **Plaintext CQL is not served** |

If using mTLS, add tests with a missing client cert or a cert signed by an untrusted CA: the server must reject per policy. Under `optional: true`, plaintext **may succeed**, which must be treated as proof that rollout is unfinished, not a test error.

### 8.3. Testing Internode and Replicas

On nodes:

~~~bash
nodetool status
nodetool describecluster
nodetool netstats
nodetool tpstats
~~~

Monitor Cassandra logs along with handshake/internode connection failures, dropped messages, replica response latencies, and streaming/repair. An RF=3 cluster can still serve at `LOCAL_QUORUM` even if one replica fails connections; **one successful write does not prove all internode links are secure**.

Verify:

1. All nodes see each other in the right state, without splitting the cluster due to CA/SAN errors.
2. Required internode paths are configured with TLS per policy (`all` if all peer traffic must be encrypted); no `optional: true` remains in target state.
3. In the lab, verify with approved network telemetry/captures or release TLS observability tools. **Never interpret port 7000/7001 alone** as proof of encryption.
4. After rotating certs, test new connections and traffic-generating operations such as RF=3 reads/writes; compare latency/CPU against baseline.

Never simulate faults by deleting a private key in use on a production node or severing all peers simultaneously. Before fault-injection tests, ensure snapshots/rollbacks, management access, and bounded blast radius.

### 8.4. Results Table to Fill with Real Measurements

| Evidence | Before TLS | After Mandatory TLS | Pass? |
|---|---|---|---|
| Java connects with valid CA/SAN | _fill_ | _fill_ | _fill_ |
| Plaintext Java client rejected | _fill_ | _fill_ | _fill_ |
| Wrong hostname/CA rejected | _fill_ | _fill_ | _fill_ |
| Internode `all` + `optional: false` on all nodes | _fill_ | _fill_ | _fill_ |
| Client p50/p95/p99 (ms) | _fill_ | _fill_ | _fill_ |
| CPU %, TLS handshakes/s | _fill_ | _fill_ | _fill_ |
| Query errors/timeouts and dropped messages | _fill_ | _fill_ | _fill_ |
| Node status and streaming/repair | _fill_ | _fill_ | _fill_ |

Never fill in fabricated numbers. Keep RF/CL, connection counts, QPS, mutation sizes, background compaction, and JVM settings constant when measuring so TLS cost is isolated from workload changes.

## 9. Certificate Operations: Reload, Rotation, and Recovery

### 9.1. TLS Certificate Hot Reload Since Cassandra 4

Cassandra docs describe **hot reloading SSL certificates** starting in 4.x: when using compatible file-based key/trust material, nodes can detect updated files and reload periodically; supporting releases also provide:

~~~bash
# Only when nodetool help on the running release confirms this command:
nodetool reloadssl
~~~

**Do not equate "reload succeeded" with all existing connections switching certs**: existing TLS sessions may keep using prior handshake state; **new** connections verify the newly updated cert/CA. If keystore passwords also change, check reload mechanisms and config files; some setups require restarts or other workflows. Never base certificate renewal on an untested assumption about hot reload.

### 9.2. Order of CA/Certificate Rotation to Avoid Disconnection

When replacing an old CA with a new CA, a **two-stage overlapping-trust** procedure is usually safest:

1. **Inventory:** all nodes/clients, current certs, SANs, expirations, CAs, truststores, offline or low-frequency apps, mTLS certs, and outbound keystores.
2. **Expand trust:** update truststores on all peers/clients to temporarily trust **both old and new CAs** if policy permits.
3. **Verify new trust:** test clients/peers with certs signed by the new CA in staging; verify cert chains, SANs, EKUs, and connection paths.
4. **Rotate keypairs/certs:** update nodes/clients one by one using hot reload or rolling restarts per deployment capability, verifying fresh connections after each step.
5. **Narrow trust:** once every endpoint uses the new CA and no old certs remain, remove the old CA on schedule and re-run negative tests.
6. **Revoke and record:** revoke old certs/CAs as needed; update inventories, backup/DR secrets, expiry alerts, and audit logs.

In a **private key compromise** incident, never continue trusting or restoring an exposed key simply because the cert has not expired. Isolate the endpoint, revoke/rotate, review auth impact, and execute incident response; you may need to reissue node identities and audit the entire cluster.

### 9.3. Preventing Loss of Both Cluster and Secret Manager

Backups containing only SSTables/schemas **without recovery paths for CAs, private keys, KMS, and truststores** can leave a restored cluster unreachable. Security backups need:

- Encrypted secrets with strict access control; store **references** in normal manifests, never private keys in public docs/CI artifacts.
- Backup/DR plans for PKI/KMS, break-glass rights, and procedures to reissue certs if keys cannot be recovered.
- Tracked cert expirations, rotation owners, pre-expiry alerts, and clean-cluster/Java-driver recovery drills.
- Checks ensuring no node holds stale certs during CA rotation; never bypass hostname validation to "fix" an incident.
- Separation of TLS transport keys from **data-at-rest encryption keys**; they protect different things.

## 10. Diagnosing Common Issues

### 10.1. Investigation Flow Without Bypassing Security

~~~mermaid
flowchart TB
    A["Client/node cannot connect"] --> B{"TCP reachability?"}
    B -->|No| C["Check port, firewall, DNS, listen/broadcast"]
    B -->|Yes| D{"TLS handshake/CA/SAN valid?"}
    D -->|No| E["Cert expiry, CA chain, SAN, mTLS, keystore, JVM"]
    D -->|Yes| F{"CQL authentication/authorization?"}
    F -->|Wrong| G["Role credentials, grants, system_auth, CL"]
    F -->|Right| H["Measure timeouts, replicas, CL, CPU, GC, network"]
    C --> I["Re-verify against TLS policy"]
    E --> I
    G --> I
    H --> I
~~~

| Issue | Symptom | What to Check |
|---|---|---|
| Untrusted CA | `unknown_ca`, `PKIX path building failed` | Client/node truststore, intermediate chain, issuer |
| SAN mismatch | Hostname verification failure | Endpoint DNS/IP vs. actual cert SANs |
| Expired / not-yet-valid cert | TLS handshakes fail after a timestamp | `notBefore`/`notAfter`, NTP, renewal mechanism |
| Missing mTLS client cert | Server rejects handshake | `require_client_auth`, client keystore, EKU/chain |
| Internode split after rollout | Node Down/unreachable, dropped messages | `optional`, peer trust, outbound keystore, SANs, restart order |
| Elevated TLS CPU | Higher p99/handshake latency | New connection rate, connection pooling, codecs/GC/CPU |
| CQL Unauthorized | TLS succeeds, query denied | CQL grants/roles; do not disable TLS |
| Wrong port or network ACL | Connection refused/timed out | `storage_port`, `native_transport_port`, network policies |
| Client connects to only some nodes | Hostnames/CAs differ across endpoints | Per-node cert inventory and routing metadata |
| Cert reload had no effect | New sessions still see old cert | Release hot-reload support, file path/password, logs, restart policy |

Never put TLS secrets/private keys in bug reports, traces, chats, or public issues. **Public cert serial numbers/fingerprints**, SANs, issuers, expiration dates, error types, and timestamps usually suffice for initial triage.

## 11. Exercises and Applied Questions

### Exercise 1 — Native TLS with Plaintext Internode

A cluster enables `client_encryption_options.enabled: true` and `optional: false`, while `server_encryption_options.internode_encryption: none`. The security team claims all network data is protected. Is that claim accurate?

**Hint:** false. Application-to-node links are protected if clients validate server certs, but **internode encryption is off**. Choose an appropriate mode—typically `all` if all peer traffic must be encrypted.

### Exercise 2 — `optional` and Plaintext

During a rolling upgrade, `client_encryption_options.enabled: true` but `optional: true`. Legacy apps without TLS still connect. Is this a software bug or a configuration state?

**Hint:** it is an intentional **transitional state allowing both TLS and plaintext**. It does not satisfy a "mandatory TLS" policy. Finish migrating clients, set `optional: false`, and test that plaintext connections are rejected.

### Exercise 3 — Hostname Mismatch

A node cert has DNS SAN `db-1.internal.example`, and the Java Driver contacts an IP absent from the SAN. Handshakes fail when hostname validation is enabled. Should validation be disabled?

**Hint:** no. Update endpoints to use DNS matching the cert or reissue the cert with the proper IP SAN. Disabling checks weakens identity verification, especially when traffic might be redirected to a spoofed node.

### Exercise 4 — mTLS Works Yet `SELECT` Is Denied

An application presents a valid client cert and the TLS handshake succeeds, yet `SELECT` throws `UnauthorizedException`. Is TLS misconfigured?

**Hint:** not necessarily; mTLS authenticates the client certificate, whereas CQL authorization governs query permissions. Check the authenticator/role manager/authorizer and grants; never over-grant permissions just to bypass testing.

### Exercise 5 — Network Split When Enabling Internode TLS

Node A is set to `internode_encryption: all`, `optional: false`; B and C still speak plaintext without truststores. The cluster starts reporting peer connection failures. Propose how to redo this safely.

**Hint:** safely roll back per runbook to restore reachability, distribute proper certs/trust to all nodes, use a time-bounded `optional: true` compatibility phase, verify peer TLS, and finally switch to mandatory mode in the staging-tested order.

### Exercise 6 — CA Rotation

The CA signing internode certs expires in one month. Why shouldn't you switch all nodes to the new CA before updating truststores?

**Hint:** peers still trusting only the old CA will reject the new certs and partition the cluster. You need an overlap window where peers/clients trust both old and new CAs, then rotate node certs/keys, verify fresh connections, and finally remove and revoke the old CA per policy.

### Lab Completion Checklist

- [ ] Distinguished native TLS, internode TLS, mTLS, CQL auth/authz, and at-rest encryption.
- [ ] Verified SANs, CA chains, expirations, private keys/keystores/truststores, and file ACLs.
- [ ] Confirmed Cassandra/JVM/driver versions, DCs/racks, and actual native/internode ports.
- [ ] Explained `none/dc/rack/all` and why `dc` does not encrypt intra-DC traffic.
- [ ] Executed CQL over TLS with valid CA/hostname; verified wrong CA and plaintext are rejected in target state.
- [ ] If using mTLS, verified clients without certs are rejected and unprivileged roles still cannot query.
- [ ] Checked `nodetool status`, peer TLS, reads/writes, and CL at appropriate RF.
- [ ] Recorded p95/p99, CPU, handshake failures, and driver reconnects before/after rollout.
- [ ] Planned cert rotation/revocation and secret/KMS recovery on node/DC failure.
- [ ] Did not leave `optional: true` or hostname validation disabled when policy requires mandatory encryption/verification.

## 12. References

1. Apache Cassandra Documentation — [Security: TLS/SSL, client-to-node and inter-node encryption](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/security.html).
2. Apache Cassandra Documentation — [cassandra.yaml reference](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `client_encryption_options`, `server_encryption_options`, optional/endpoint verification, truststore/keystore.
3. Apache Cassandra Documentation — [Cassandra 4.0 cassandra.yaml](https://cassandra.apache.org/doc/4.0/cassandra/configuration/cass_yaml_file.html): configuration and port differences from older branches.
4. Apache Cassandra Documentation — [Cassandra 3.11 cassandra.yaml](https://cassandra.apache.org/doc/3.11/cassandra/configuration/cass_yaml_file.html): parameter comparison when upgrading.
5. Apache Cassandra Documentation — [nodetool reloadssl](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/reloadssl.html): verify certificate reload support per release.
6. Apache Cassandra Documentation — [CQL authentication and authorization](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/security.html): authorization distinct from TLS.
7. Apache Cassandra Java Driver — [SSL configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/ssl/): truststore, keystore, hostname validation, and SSL engine factory per driver version.

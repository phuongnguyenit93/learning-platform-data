# Authentication, Authorization, TLS, and Expired Certificate Failures in Apache Cassandra

## 1. Problem Statement and Troubleshooting Goals

A Java application can fail to connect to Apache Cassandra even when `nodetool status` reports all nodes as `UN`, disks have plenty of space, and CQL reads/writes show no performance issues. Security failures often occur **before or at the boundary of CQL execution**: an incomplete TLS handshake, an untrusted certificate, invalid credentials, insufficient role permissions, or an expired certificate.

Within the **Troubleshooting** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module, this lesson focuses on classifying and resolving issues involving:

1. **Authentication** — can the client prove it is a valid role/user?
2. **Authorization** — does the authenticated role have permission to execute that CQL statement?
3. **TLS** — can client and server establish an encrypted channel and verify peer identity?
4. **Certificate validity** — are the CA chain, hostnames, validity window, key usages, and system clocks valid?
5. **Java Driver 4.x** — driver-layer exceptions, root causes inside `AllNodesFailedException.getAllErrors()`, and safe logging.
6. **Incident scope** — one node, one DC, one pod group, one application version, or the entire cluster?
7. **Safe recovery** — rolling back/rotating certificates, updating truststores, and restoring roles/permissions under controlled change.
8. **Prevention** — certificate lifetimes, rotation dry-runs, failover testing, minimal logging, and runbooks.

Apache Cassandra is a wide-column distributed system; **partition keys**, query-driven table design, replication, consistency levels, compaction, and repair continue to govern service health after a security fix. However, **TLS/role failures must never be "fixed" by lowering consistency levels, adding `ALLOW FILTERING`, or enabling infinite retries**.

> **Priority principle:** preserve TLS verification and least-privilege access control. Never disable hostname verification, skip certificate checks, enable anonymous access, or share admin accounts just to "make the API work again".

### 1.1. A Typical Scenario

After a CA certificate rotation, half of newly deployed Java pods return HTTP 503 while older pods still read from Cassandra normally. Dashboards show `AllNodesFailedException`, yet `nodetool status` shows all nodes `UN`. The cause may be that **the new pods' truststore lacks the required CA** or the server chain is incomplete—not necessarily that Cassandra is down or missing replicas.

Another scenario: an application logs in, `SELECT` succeeds, yet `INSERT` is rejected. This is usually **authorization**, not TLS: the role has `SELECT` permission but lacks `MODIFY` on the target table.

### 1.2. Do Not Confuse Security with Consistency

| Issue Category | Core Question | Examples |
|---|---|---|
| TLS transport | Can peer identity be verified and an encrypted channel established? | `SSLHandshakeException`, PKIX |
| Authentication | Did the server accept the role/client identity? | Wrong password, `LOGIN=false` role |
| Authorization | Does the role have permissions on the resource/statement? | Missing `MODIFY` |
| Cassandra availability | Are enough replicas up for CL? | `UnavailableException` |
| Cassandra latency | Did coordinator/replicas respond before deadline? | `ReadTimeoutException` |
| Java driver/connectivity | Is any coordinator candidate usable? | `AllNodesFailedException` |
| Data modeling | Is the query valid and efficient by partition key? | Query missing partition key |

**Do not equate every failure inside `AllNodesFailedException` with "cluster DOWN".** Inspect the underlying cause for each coordinator candidate.

## 2. Map of Security Connection Paths

~~~mermaid
flowchart LR
    A["Java service / cqlsh"] -->|"Native CQL / TLS"| B["Cassandra coordinator"]
    B -->|"Internode messages / configured TLS"| C["Other replica nodes"]
    D["nodetool / operator"] -->|"Separate JMX auth/TLS"| B
    E["Monitoring/JMX exporter"] -->|"JMX or exporter endpoint"| B
    F["Secret manager/PKI"] -.->|"CA, cert, truststore, credentials"| A
    F -.->|"node certificates"| B
    F -.->|"node certificates"| C
~~~

Separate **at least three distinct planes**:

- **Client-to-node native transport:** Java Driver, `cqlsh`, and services executing CQL; commonly uses the configured native transport port such as `9042`, which may vary or use a separate TLS port depending on version.
- **Node-to-node internode transport:** Cassandra nodes exchanging replica messages, gossip, and streaming over dedicated ports and encryption settings.
- **JMX/management:** `nodetool` and operational agents connecting over JMX or management endpoints; uses **separate** authentication, TLS, ports, and privileges from CQL users.

**A passing `nodetool status` check does not prove Java Driver TLS/roles work.** Likewise, a working `cqlsh` CQL connection does not prove internode TLS across DCs is healthy.

### 2.1. Peer Verification Can Happen via Different Mechanisms

- **Server authentication in TLS:** the client verifies the server certificate against trust anchors and hostnames.
- **Cassandra CQL authentication:** configured username/password or auth provider; may run **inside the TLS channel** when TLS is enabled.
- **Mutual TLS (mTLS):** the server also verifies the client certificate when required.
- **JMX authentication:** can use separate credentials/SSL settings unrelated to Cassandra CQL roles.

Which authentication/authorization mechanisms are supported depends on the Cassandra release, distribution, and plugin configuration. Never assume "having a client certificate eliminates the need for CQL role/password" unless the server is explicitly configured for identity mapping.

### 2.2. States That Can Coexist

| Native TLS | CQL auth | CQL authorization | Outcome |
|---|---|---|---|
| Handshake fails | Not started / unreachable | Not evaluated | Client gets no CQL session |
| Succeeds | Invalid credentials | Not evaluated | Authentication failure |
| Succeeds | Succeeds | Missing `SELECT` | `SELECT` is denied |
| Succeeds | Succeeds | Sufficient permissions | CQL proceeds to query/schema/CL checks |
| Succeeds | Succeeds | Sufficient permissions | Can still time out or fail Unavailable due to replicas |

This table is a **diagnostic model**; it does not claim every driver or server version raises the exact same exception class or order.

## 3. First 5-Minute Triage Procedure

When alerted "Java service cannot reach Cassandra", do not immediately swap certificates or grant admin privileges. Gather minimum evidence:

1. **User impact:** reads, writes, or both? How many requests are failing, and since when?
2. **Client scope:** one pod, namespace, app version, region, or all services?
3. **Node scope:** one coordinator candidate, one rack/DC, or all contact points?
4. **Class and root cause:** TLS handshake, authentication, authorization, timeout, DNS, or network?
5. **Change timeline:** any recent certificate rotation, CA change, password/secret update, driver/JDK upgrade, DNS/firewall change, RBAC update, or server config change?
6. **Safe data:** query template ID, UTC timestamp, request correlation ID, shareable cert fingerprint/serial, node/DC.
7. **Cluster state:** `nodetool status`, native transport errors, authorized server logs, latency/CPU/GC/disk.
8. **Guardrails:** suppress retry storms; never weaken TLS/CL/permissions or paste secrets into tickets.

### 3.1. Initial Inference Matrix

| Signal | Leading Hypothesis | Next Step |
|---|---|---|
| All requests from new pods fail TLS | Different truststore/JDK/chain/hostname | Compare configs and certificate chains |
| Only node A causes handshake failures | Cert/key/chain/SAN on A wrong or expired | Inspect node A and network path to A |
| `AuthenticationException` while TLS connects | Credentials, role LOGIN, authenticator mismatch | Check role/secret/auth config |
| `UnauthorizedException` on INSERT | Role lacks MODIFY | Check per-table grants |
| Node status `UN` yet app cannot connect | Client→node network/TLS/auth | Test from the actual app network |
| `cqlsh` on node works, pod fails | Truststore/DNS/hostname/NAT/policy | Compare hostnames and client CA trust |
| Failures after JDK upgrade | Disabled algorithms/truststore/cipher/protocol | Compare JDK security policies |
| Cert unexpired yet PKIX error | Wrong CA chain/trust anchor | Inspect issuer/chain/intermediates |
| Fails only when IP replaced by DNS | SAN/hostname verification | Compare contact points and SANs |
| Breaks on exact cert expiration day | NotAfter/clock skew/unrolled secret | Prepare rotation/rollback plan |
| `Unavailable` when a node is down | RF/CL/replica availability | Investigate topology, do not edit certs |
| p99 spikes after TLS fix | Connection churn, handshake/GC/CPU, or backend load | Re-measure driver/node metrics |

**Order of operations:** fix the earliest failing layer in the connection/request lifecycle first. Do not tune CQL if the TLS handshake fails; do not edit grants if the role cannot authenticate.

## 4. Distinguishing Authentication from Authorization

### 4.1. Authentication: Who Are You?

Cassandra can be configured with `PasswordAuthenticator` and its corresponding role management. On clusters supporting CQL role authentication, a login role needs:

- An existing identity/role.
- The **`LOGIN=true`** attribute if the role is used to sign in.
- Matching credentials / auth mechanism.
- Connection to the right cluster/keyspace.
- Consistent authenticator configuration enabled on the server.

Authentication happens before query permissions are evaluated. Bad usernames/passwords typically cause both SELECT and INSERT to fail during session creation or authentication.

**Operational security:** never pass passwords on command lines that end up in shell history or process lists; never print passwords in logs, exception details, or traces.

### 4.2. Authorization: What Are You Allowed to Do?

Once a role authenticates, `CassandraAuthorizer` or a configured authorizer/plugin checks permissions on the target resource (keyspace/table/role). Common CQL permissions include:

| Permission | Example Operations | Notes |
|---|---|---|
| `SELECT` | Read table/rows | Can be granted at table/keyspace resource scope |
| `MODIFY` | INSERT/UPDATE/DELETE | Does not imply schema ALTER/DROP |
| `CREATE` | Create matching resources | Normally withheld from runtime app roles |
| `ALTER` | Modify schema/resources | Reserved for migration/admin roles |
| `DROP` | Delete resources | Sensitive privilege |
| `AUTHORIZE` | Manage grants | Never grant to normal apps |
| `DESCRIBE` and others | Version/resource dependent | Check release CQL reference |

Default authorizers or distributions vary; if `AllowAllAuthorizer` is active, role-based permissions are not enforced like `CassandraAuthorizer`. **Never treat a successful `GRANT` statement as proof of enforcement**—test negative (denied) operations too.

### 4.3. Never Fix Unauthorized Errors by Granting Broad Privileges

An application that only writes to one table should never receive `ALL PERMISSIONS ON ALL KEYSPACES`. Instead:

~~~cql
-- Illustrative CQL, executed by an authorized admin role.
GRANT SELECT ON TABLE telemetry_lab.readings_by_device_day
TO telemetry_reader;

GRANT MODIFY ON TABLE telemetry_lab.readings_by_device_day
TO telemetry_writer;

-- Inspect effective permissions per release/authorizer.
LIST ALL PERMISSIONS OF telemetry_reader;
LIST ALL PERMISSIONS OF telemetry_writer;
~~~

Roles `telemetry_reader` and `telemetry_writer` are assumed securely provisioned. Syntax and listing of inherited permissions depend on the Cassandra version and authorizer; verify against actual release output.

### 4.4. Role Hierarchy Does Not Replace Tenant Authorization

A Cassandra role granted `SELECT` on a table **does not restrict** which tenant's rows it can read. When multiple tenants share a table, the application must still:

- Authenticate the request principal.
- Verify tenant ownership/authorization.
- Include the tenant dimension in the partition key where appropriate.
- Bind tenant IDs from a trusted auth context rather than raw route/query parameters.
- Prevent data leaks through logs or metrics.

**CQL bind parameters prevent value injection, not business authorization bypasses.**

## 5. TLS Handshake: Which Step Failed?

~~~mermaid
sequenceDiagram
    participant C as Java Driver
    participant S as Cassandra native transport
    C->>S: TCP connection
    C->>S: TLS ClientHello (protocol/ciphers/SNI)
    S-->>C: ServerHello + certificate chain
    C->>C: Trust chain, validity, hostname, key usage
    opt mTLS required
        S->>C: CertificateRequest
        C->>S: Client certificate + proof
        S->>S: Verify client cert/chain
    end
    C-->>S: TLS handshake complete
    C->>S: CQL native protocol + authentication
    S-->>C: Auth success/failure
    C->>S: CQL statement
    S-->>C: Authorized result or Unauthorized
~~~

This is a simplified logical flow; exact message sequences differ across TLS 1.2 and 1.3, drivers, servers, and mTLS. Key diagnostic clues:

- **TCP refused/reset:** never reached TLS handshake; check network/firewall/listener.
- **Protocol/cipher mismatch:** no mutually acceptable TLS version/cipher; usually handshake failure.
- **Unknown CA/PKIX:** client cannot build a chain from the server cert to a trusted anchor.
- **Hostname mismatch:** certificate does not match the DNS/IP verified by the driver.
- **Expired/not-yet-valid:** validity interval fails against the verifying clock.
- **Client certificate required/invalid:** mTLS missing a valid client cert/key/chain.
- **Auth rejected:** TLS may have succeeded, but CQL credentials/role failed.
- **Unauthorized:** authentication succeeded, yet resource permission is missing.

### 5.1. TLS Does Not Automatically Guarantee Authorization

A TLS channel with valid certificates only confirms peer identity per policy. It does not grant a Java role `ALTER KEYSPACE` privileges, nor stop a valid app role from reading another tenant if business authorization is missing.

### 5.2. Errors May Be Wrapped

In the Java Driver, a handshake exception is often an **inner cause** inside `AllNodesFailedException` or a connection initialization failure. Do not stop investigating after reading the outer class name. Inspect per-node causes with bounded logging so secrets and internal topology are not leaked.

## 6. Understanding X.509 Certificates and Truststores

### 6.1. Fields to Inspect

| Field/Concept | Role | Typical Failure |
|---|---|---|
| `Subject` | Certificate subject info | Insufficient alone without SAN for hostname validation |
| `Subject Alternative Name (SAN)` | DNS/IP names protected by cert | Connecting by IP when cert only has DNS SAN |
| `Issuer` | Issuing CA | Missing intermediate or untrusted root |
| `NotBefore` | Validity start time | Cert not yet valid |
| `NotAfter` | Validity end time | Cert expired |
| `Extended Key Usage (EKU)` | E.g., TLS serverAuth/clientAuth | Cert used for wrong purpose |
| `Key Usage` | Permitted key operations | Incompatible key usage |
| `Public key / algorithm` | Algorithm and key size | Rejected by JDK policy |
| `Signature algorithm` | Certificate signing algorithm | Blocked by JDK/FIPS/security policy |
| `Certificate chain` | Leaf → intermediate → root CA | Missing intermediate or untrusted root |
| `Serial/fingerprint` | Cert identifier in incidents | Needed to confirm which cert rolled out |

The **truststore** holds public trust anchors/CAs trusted by the client; the **keystore** holds private keys and certificate chains for the client/node during TLS/mTLS. Never put private keys in a truststore "just in case", and never commit keystores containing secrets.

### 6.2. An Unexpired Certificate Can Still Be Untrusted

Example:

~~~text
Leaf:        cassandra-1.dc1.example.internal
Issuer:      Intermediate-CA-2026
NotAfter:    2027-02-01

Client truststore only contains:
    OldRoot-CA

Server sends:
    Leaf
    (missing Intermediate-CA-2026)

Result:
    Can throw PKIX path building failed
    even though Leaf has not expired.
~~~

Always verify **the full chain and trust anchors**, not just the expiration date.

### 6.3. Hostname Verification and IP SANs

If an application uses contact point `10.10.4.12` while the certificate only lists DNS SAN `cassandra-1.dc1.example.internal`, IP hostname verification can fail. Fixes:

- Use a DNS name **covered by the certificate** with stable DNS/routing; or
- Issue a certificate with an appropriate IP SAN if connecting by IP is genuinely required; and
- Check which addresses driver/node discovery uses after the initial contact point.

**Never** disable hostname verification as a production fix. In Cassandra, the driver discovers peer addresses beyond the initial contact points, so certificate/name policies must match **every endpoint the driver may connect to**.

## 7. Expired Certificates and Clock Skew

### 7.1. Two Time Bounds

For a certificate:

~~~text
NotBefore: 2026-10-01T00:00:00Z
NotAfter:  2026-11-30T00:00:00Z

At 2026-11-21:
  Valid with respect to time (if other checks pass).

At 2026-12-01:
  Expired.

If client/server clocks are heavily skewed:
  May report expired or not-yet-valid
  even while another host connects cleanly.
~~~

This covers only the time interval; certificates must still pass CA chain, name, EKU, algorithm policy, and other checks.

### 7.2. UTC Clocks vs. Display Timezones

Certificate validity uses absolute timestamps. On-call engineers may view local time, but comparisons must use **UTC** or verified conversions. Record incident timelines in UTC with explicit offsets; never alter a JVM timezone to "extend" a certificate.

### 7.3. Never Fix Certificate Expiry by Shifting the System Clock

**Never** turn back the OS clock on a Cassandra node or Java pod to bypass `NotAfter`. Clock skew corrupts:

- TLS validity, certificate rotation, and authentication.
- Cassandra write timestamps/reconciliation, TTL, and LWT.
- Hints, repair, and log timelines.
- Token and cluster maintenance diagnostics.
- Other services sharing the host.

Perform proper **certificate renewal/rotation** with valid chains and SANs, and synchronize clocks via NTP/chrony or approved time services.

## 8. Layer-by-Layer Exception Recognition in Java Driver 4.x

### 8.1. Outer Exceptions and Root Causes

| Java/Server Signal | Layer to Investigate | Do Not Infer |
|---|---|---|
| `SSLHandshakeException` | TLS negotiation/verification | Cassandra data loss |
| `CertificateExpiredException` | Cert past NotAfter during validation | Wrong password |
| `CertificateNotYetValidException` | Cert before NotBefore / clock skew | Definitely expired in local time |
| `ValidatorException`, `PKIX path building failed` | Trust chain/CA | Cert is necessarily expired |
| `SSLPeerUnverifiedException` / hostname mismatch | SAN/identity verification | Firewall down |
| `AuthenticationException` | CQL auth/role/credentials | Missing table SELECT |
| `UnauthorizedException` | CQL permissions/authorizer | TLS handshake broken |
| `AllNodesFailedException` | Driver exhausted coordinator candidates | All physical replicas DOWN |
| `DriverTimeoutException` | Driver request deadline | CQL permissions definitely failed |
| `ReadTimeoutException` / `UnavailableException` | Replica/CL/server path | Need to rotate TLS certs |

Exact class/package names and nesting depend on driver major/minor, JDK, and Cassandra versions. Handshake errors can also arrive wrapped in `CompletionException` under async APIs; unwrap Futures cleanly before classifying.

### 8.2. Exception Handling Principles

Never do this:

~~~java
// ANTI-PATTERN: silently turning all Cassandra failures into empty data.
try {
    return loadReadings();
} catch (RuntimeException error) {
    return java.util.List.of();
}
~~~

A successful query returning 0 rows is fundamentally different from a TLS, auth, or permission failure. Handlers must preserve explicit outcomes: `SUCCESS_EMPTY`, `AUTH_FAILURE`, `PERMISSION_DENIED`, `TRANSPORT_TLS_FAILURE`, `TIMEOUT`, and `UNAVAILABLE` per application error contracts.

### 8.3. Inspect Exception Types Rather Than Parsing Messages for Business Logic

JDK certificate errors vary in nested classes and localized messages across releases. Avoid:

~~~java
// ANTI-PATTERN: brittle across JDK/driver versions.
if (error.getMessage().contains("PKIX")) {
    retryForever();
}
~~~

Rely primarily on **exception types/cause chains** and structured logging. A TLS trust failure is usually **permanent for the running pod configuration**—infinite retries merely trigger a handshake storm.

## 9. `AllNodesFailedException.getAllErrors()`: Per-Coordinator Errors, Not Replica ACKs

### 9.1. Reading the Map Correctly

In Java Driver 4.x, `AllNodesFailedException.getAllErrors()` maps **coordinator candidates** to lists of Throwables recorded by the driver. It is **not** a map of which replicas applied a mutation or proof that all nodes are DOWN.

~~~text
AllNodesFailedException
  node A -> SSLHandshakeException
            -> PKIX path building failed
  node B -> SSLHandshakeException
            -> CertificateExpiredException
  node C -> connection initialization error

True: none of the attempted coordinator candidates could serve the request.
False: the whole cluster lost data or a prior write definitely rolled back.
~~~

### 9.2. Java Driver 4.x Example

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.metadata.Node;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public final class FailureInspector {
    private FailureInspector() {}

    public static Throwable unwrapFuture(Throwable throwable) {
        Throwable current = throwable;
        for (int i = 0; i < 8; i++) {
            if ((current instanceof CompletionException
                    || current instanceof ExecutionException)
                    && current.getCause() != null) {
                current = current.getCause();
            } else {
                return current;
            }
        }
        return current;
    }

    public static void inspect(Throwable failure) {
        Throwable root = unwrapFuture(failure);
        if (!(root instanceof AllNodesFailedException all)) {
            emit("failure", root.getClass().getSimpleName(),
                "no_per_node_map");
            return;
        }

        Map<Node, List<Throwable>> errors = all.getAllErrors();
        emit("all_nodes_failed", "AllNodesFailedException",
            "node_entries=" + errors.size());

        errors.forEach((node, causes) -> {
            String dc = node.getDatacenter();
            for (Throwable cause : causes) {
                emit("coordinator_candidate_failure",
                    unwrapFuture(cause).getClass().getSimpleName(),
                    dc == null ? "unknown_dc" : dc);
            }
        });
    }

    private static void emit(
            String event, String errorClass, String safeTag) {
        // Structured logging/metrics with sampling and rate limits.
        // Never log secrets, raw bind values, or private keys.
    }
}
~~~

This snippet uses pattern-matching `instanceof` and requires a compatible JDK. Verify the `Node` type and method signatures against your exact Java Driver artifact. `getAllErrors()` can hold **multiple Throwables per node**; do not treat the entry count as the number of replicas missing ACKs.

### 9.3. Walking the Cause Chain to Spot Certificate Errors

~~~java
import javax.net.ssl.SSLHandshakeException;
import java.security.cert.CertificateExpiredException;
import java.security.cert.CertificateNotYetValidException;
import java.util.IdentityHashMap;
import java.util.Map;

public static String classifyTls(Throwable failure) {
    Map<Throwable, Boolean> seen = new IdentityHashMap<>();
    boolean handshake = false;

    for (Throwable t = failure;
         t != null && !seen.containsKey(t);
         t = t.getCause()) {
        seen.put(t, Boolean.TRUE);

        if (t instanceof CertificateExpiredException)
            return "CERT_EXPIRED";
        if (t instanceof CertificateNotYetValidException)
            return "CERT_NOT_YET_VALID";
        if (t instanceof SSLHandshakeException)
            handshake = true;
    }
    return handshake ? "TLS_HANDSHAKE_FAILURE" : "OTHER";
}
~~~

This is an **illustrative classifier** and will not catch every PKIX, SAN, cipher, or JDK security error. Seeing `TLS_HANDSHAKE_FAILURE` still requires checking truststore, chain, EKU, hostname, mTLS, and protocol details. Never assume every `SSLHandshakeException` means an expired cert.

### 9.4. Retries and Correctness

Handshake failures due to CA, SAN, or expiry **rarely self-heal without a configuration change**. Retrying infinitely causes handshake storms, spikes CPU/network load, and hides root causes. Fail fast with classification; only perform bounded retries when there is evidence of transient network trouble, within explicit deadlines and retry budgets.

For CQL writes already dispatched, timeouts differ from pre-request TLS failures: mutation outcomes may be unknown. Never treat `AllNodesFailedException` on a request as proof that data was rolled back.

## 10. Diagnosing Certificates with `openssl`

### 10.1. Probe from the Same Network as the Failing Application

Using a non-existent placeholder endpoint for illustration, **apply only on authorized infrastructure**:

~~~bash
openssl s_client \
  -connect cassandra-1.example.invalid:9042 \
  -servername cassandra-1.example.invalid \
  -showcerts -verify_return_error \
  </dev/null
~~~

`-connect` is the TCP endpoint and `-servername` sets SNI. **SNI is not hostname verification**. If your OpenSSL version supports it, add:

~~~bash
openssl s_client \
  -connect cassandra-1.example.invalid:9042 \
  -servername cassandra-1.example.invalid \
  -verify_hostname cassandra-1.example.invalid \
  -verify_return_error \
  </dev/null
~~~

OpenSSL may use the **system CA store**, which differs from a Java truststore, so OpenSSL passing or failing does not guarantee identical Java Driver behavior. With a private CA, a `-CAfile` holding **approved public CA certificates** can reproduce trust policy—never pass private keys.

### 10.2. Inspect Validity, SANs, Issuer, and Fingerprint

~~~bash
# server-leaf.pem contains only the public leaf certificate.
openssl x509 -in server-leaf.pem -noout \
  -subject -issuer -dates \
  -ext subjectAltName \
  -fingerprint -sha256
~~~

Compare against what **the server actually serves on the native port**, not just the file on disk. A new secret/cert may be mounted on disk while the running process has not reloaded it or old pods/nodes remain active.

### 10.3. Verify the Chain Against a Trusted CA

~~~bash
# Public CA bundle/intermediates, containing no private keys.
openssl verify \
  -CAfile approved-root-ca.pem \
  -untrusted approved-intermediates.pem \
  server-leaf.pem
~~~

Check hostname as well if supported:

~~~bash
openssl verify \
  -verify_hostname cassandra-1.example.invalid \
  -CAfile approved-root-ca.pem \
  -untrusted approved-intermediates.pem \
  server-leaf.pem
~~~

| Signal | Hypothesis | Controlled Action |
|---|---|---|
| Expired | Leaf/intermediate/root has expired | Renew/rotate with full valid chain |
| Unable to get issuer | Missing intermediate/root CA | Fix server chain / client trust |
| Hostname mismatch | SAN does not match DNS/IP | Issue cert with right SAN or fix endpoint |
| Bad certificate in mTLS | Wrong client chain/key/EKU | Check client keystore / server trust |
| No shared protocol/cipher | Incompatible TLS/JDK policy | Compare protocol/cipher policies per release |
| Connection refused | Never reached TLS; listener/network | Check port/firewall/native transport |

**Never fix PKIX errors by lowering CL**; **never fix TCP refused by granting MODIFY**.

## 11. `keytool` and Java's Actual Trust Source

### 11.1. List Certificates in a Truststore

~~~bash
# keytool may prompt for password per CLI policy.
# Never pass -storepass on a command saved to shared shell history.
keytool -list -v \
  -keystore /secure/path/cassandra-truststore.p12 \
  -storetype PKCS12
~~~

Verify:

- Are the root/intermediate CAs present in the actual truststore of the failing pod?
- Do fingerprint, issuer, and validity match the new CA?
- Does runtime trust come from JDK `cacerts`, Java system properties, driver SSL engine factory, or a custom `SSLContext`?
- Do new and old pods have identical secret mounts, file permissions, and JDK images?
- Did the process reload its `SSLContext`/certs after secret rotation?

Finding a truststore file **on disk** does not prove the driver **is using it**. Java default CAs, OpenSSL system CAs, and container secret volumes are three separate sources.

### 11.2. Truststores and Keystores Serve Two Distinct Purposes

| Store | Contents | Used By |
|---|---|---|
| Client truststore | Public CA/trust anchors | Java verifying Cassandra servers |
| Server keystore | Server private key and cert chain | Cassandra native TLS endpoint |
| Server truststore | CAs trusting clients for mTLS | Cassandra verifying client certs |
| Client keystore | Client private key and cert chain | Java client in mTLS |
| Internode cert/trust | Node-to-node verification material | Cassandra internode transport |
| JMX TLS stores | Management TLS material | `nodetool`/monitoring |

**Never copy production private keys onto laptops or into tickets.** When reproducing cert bugs, build dedicated test PKI in an isolated environment.

### 11.3. Checking Hostnames Across Driver Node Discovery

The driver typically discovers **peer endpoints** beyond the initial contact points. If the client connects via IP while certs only have DNS SANs—or peers advertise addresses outside DNS—hostname validation can fail after bootstrap.

Fix this through proper SANs, endpoints, or address advertisement, never by disabling hostname verification. Behind TLS proxies or service meshes, identify where TLS terminates and which certificates protect each hop.

## 12. Cassandra Configuration: Authenticator, Authorizer, and Client TLS

Some Cassandra releases use configuration structured like:

~~~yaml
# Illustrates CONFIG KEYS ONLY, not a production file.
authenticator: PasswordAuthenticator
authorizer: CassandraAuthorizer
role_manager: CassandraRoleManager

client_encryption_options:
  enabled: true
  optional: false
  require_client_auth: false

# Keystore/truststore/secret/protocol/cipher settings must be
# matched to your release and configuration management tooling.
~~~

Always consult documentation for **your exact Cassandra 3.x/4.x/5.x release or distribution** before editing: config keys, `optional` flags, hot-reloading support, and SSL context options vary.

**Never switch to `AllowAllAuthenticator` or `AllowAllAuthorizer` to mitigate an incident.** Changing auth settings or keystores may require rolling restarts; maintain RF/CL availability and keep a rollback ready.

### 12.1. Bounded Server Log Inspection

Record timeline (UTC), node/DC, handshake/role error type, TLS/JDK versions, approved certificate fingerprints/serials, and change IDs. Avoid enabling `javax.net.debug=all` or verbose SSL logs across all production pods, as it triggers log storms, leaks metadata, and adds I/O load. When debugging is required, restrict it to specific nodes/pods, short windows, and restricted access.

### 12.2. Never Reconfigure the Entire Cluster at Once

When rotating server certs or CAs:

- Old and new clients need a trust overlap phase when changing CAs.
- Nodes may require restarts/reloads depending on version; never assume a newly mounted file takes effect automatically.
- Roll by DC/rack, verifying both native TLS **and** internode compatibility.
- Watch hints, streaming, compaction, GC, p99, and error rates.
- Keep rollback material valid throughout the change window.
- Never let a TLS rollout drop live replicas below the quorum required by CL.

## 13. Java Driver 4.x: Configuring `CqlSession` with TLS

### 13.1. Code Pattern with Clear Boundaries

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;
import javax.net.ssl.SSLContext;

public final class SecureSessionFactory {
    public static CqlSession open(
            String hostname,
            int nativePort,
            String localDc,
            String username,
            String secretFromApprovedProvider,
            SSLContext approvedSslContext) {

        return CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress(hostname, nativePort))
            .withLocalDatacenter(localDc)
            .withAuthCredentials(
                username, secretFromApprovedProvider)
            .withSslContext(approvedSslContext)
            .build();
    }
}
~~~

This uses common Java Driver 4.x APIs; check exact signatures and SSL engine factories for your **target artifact/version**. `approvedSslContext` must be built with proper CA/trust managers—**never trust-all**. Secret providers must enforce short lifecycles, rotation, and zero secret logging; note that passing `String` leaves secrets in heap memory.

Never construct a fresh `CqlSession` per request—reuse the session and pools for the lifetime of the application.

### 13.2. Never Disable Peer Verification

Anti-patterns like an empty `X509TrustManager.checkServerTrusted(...)` or an always-true hostname verifier expose clients to peer spoofing. Disabling verification in production undermines security even though traffic remains encrypted.

**Ensure hostname validation is explicitly configured** via the driver/SSL engine factory; do not assume every 4.x release shares identical defaults.

### 13.3. Repeat Checks from the Failing Pod's Exact Network

Running `cqlsh` locally on a Cassandra node may traverse loopback and use a different CA or role than a Kubernetes pod. To diagnose properly:

1. Compare DNS resolution and contact points between failing and healthy pods.
2. Compare advertised peer addresses discovered by the driver.
3. Compare truststores, JDK images, secret mounts, and SSL configurations.
4. Compare local DC, auth providers, and keyspaces.
5. Run a smoke-test query specifying the full partition key and `LIMIT`.
6. Inspect per-coordinator causes in `getAllErrors()`, without logging raw bind values.

## 14. Verifying Actual CQL Permissions and Roles

### 14.1. Least Privilege

~~~cql
-- Assumes roles were provisioned securely.
GRANT SELECT ON TABLE telemetry_lab.readings_by_device_day
TO telemetry_reader;

GRANT MODIFY ON TABLE telemetry_lab.readings_by_device_day
TO telemetry_writer;
~~~

A read-only role should not hold MODIFY/ALTER/DROP. A runtime app role should not have privileges to alter keyspaces, run repairs, or rotate admin credentials.

### 14.2. Checking Permissions and Role Hierarchy

~~~cql
-- Run with an appropriately authorized admin/observer role:
LIST ROLES;
LIST ALL PERMISSIONS OF telemetry_reader;
~~~

Cassandra supports role inheritance and permission caching per version and config. After a `GRANT`, test the query using the **actual Java runtime role**; do not assume new permissions apply instantaneously on every node/session before cache refresh. Never restart all nodes or grant ALL PERMISSIONS to bypass cache lag.

### 14.3. Permission Denied Differs from Invalid CQL

| Outcome | Diagnostic Direction |
|---|---|
| Unauthorized SELECT/INSERT | Role, grants, keyspace/table, authorizer |
| Authentication rejected | Password, role LOGIN, authenticator |
| Unconfigured table | Wrong schema/keyspace/migration |
| Invalid query / `ALLOW FILTERING` requested | Missing partition key / index / query shape |
| SSL handshake exception | Trust, SAN, expiry, TLS protocol/mTLS |
| ReadTimeout / Unavailable | RF, CL, replica liveness/performance |

**Never use `ALLOW FILTERING` to "fix" permissions**, and never escalate permissions when the real bug is a bad data model query.

### 14.4. Multi-Tenancy Still Requires Application-Level Authorization

Having `SELECT` on a table does not enforce row-level isolation across tenants sharing that table. Applications must verify principal/tenant ownership; typed UUID bind parameters do not replace authorization. Never use raw tenant IDs or partition keys as high-cardinality metric labels.

## 15. Native CQL, Internode TLS, and JMX Are Three Separate Failure Zones

| Symptom | Priority Direction |
|---|---|
| Java CQL fails, `nodetool status` works | Client TLS/auth/network; do not assume cluster is healthy for CQL |
| `nodetool` fails, Java CQL is healthy | Separate JMX auth/TLS/port |
| CQL to coordinator works, yet quorum fails | Internode link/TLS, replicas, RF/CL |
| After internode CA rotation, nodes lose peers | Trust overlap, internode certs/node config |
| Proxy TLS succeeds, backend CQL fails | TLS terminates at proxy; check proxy→Cassandra hop |
| Only clients from region A fail | Egress/firewall/DNS/TLS routes and client config |

Specifically, `nodetool` normally communicates over JMX; its success does not validate certificates on native transport port 9042. `netstats` reports SSTable streaming, not native CQL client traffic.

Internode TLS depends on Cassandra version and topology; failures there can break replica messaging, gossip, streaming, or repair even while a Java client completes a TLS handshake with one node.

## 16. Testing with `cqlsh` Without Leaking Secrets

`cqlsh` uses Python/OpenSSL trust paths and its own `cqlshrc`, which differ from Java Driver. When testing:

- Target the real Cassandra native endpoint/port and match TLS settings for your version.
- Test with a representative role like `telemetry_reader`, not solely an admin role.
- Use secure credential prompts or protected config files; never pass passwords in CLI arguments, shell history, or CI logs.
- Run a small `SELECT` with a full partition key.
- If testing `MODIFY`, use a **dedicated test table** in an authorized environment.
- Never run `SELECT *` over a huge table just to "test TLS".

Pattern to avoid:

~~~bash
# ANTI-PATTERN: password exposed in process list and shell history.
cqlsh -u telemetry_app -p "SENSITIVE_PASSWORD" host 9042
~~~

A working `cqlsh` connection does not prove the Java app shares the same CA, hostname verification, JDK cipher policy, or role.

## 17. Safe Certificate and CA Rotation Procedures

### 17.1. Leaf Renewal and CA Replacement Are Different Problems

**Renewing a leaf cert under the same CA** is usually simpler: client trust anchors need not change if the chain and SANs remain valid. Still, verify the running process actually reloaded the new keystore/certificate.

**Rotating a root/intermediate CA** requires coordinated planning across client truststores, Cassandra native TLS, mTLS, and internode TLS (if shared). Replacing server certs under a new CA **before** clients trust the new CA can break even healthy pods with `PKIX path building failed`.

### 17.2. CA Rotation Pattern with Trust Overlap

~~~mermaid
flowchart TD
    A["Inventory: clients, nodes, CAs, expiry, SANs"] --> B["Distribute trust bundle with old CA + new CA"]
    B --> C["Verify clients/nodes received updated trust"]
    C --> D["Rolling replace leaf/server certs to new CA"]
    D --> E["Smoke test native TLS + CQL auth + SELECT/MODIFY"]
    E --> F["Check internode/JMX/mTLS within scope"]
    F --> G["Wait until all consumers stop relying on old CA"]
    G --> H["Remove old CA via reversible change"]
~~~

This is a **sequencing pattern**, not direct commands. For mTLS, the server must also trust **both old and new client CAs** during the transition; internode TLS requires bidirectional coordination between old and new nodes.

### 17.3. Pre-Rotation Inventory

| Asset | Details Required |
|---|---|
| Node native endpoints | DNS/IP, SANs, leaf fingerprint/serial, NotAfter |
| Client pods | Truststore path, JDK image, CA version, SSL engine policy |
| Internode | Node certificates, trust roots, topology/ports |
| JMX/monitoring | Separate TLS/certs or shared? |
| mTLS clients | Client keystore, clientAuth EKU, chain, and server trust |
| Secret manager | Secret IDs/versions, rotation policy, rollout method |
| Load balancer/proxy | TLS termination points, SNI, backend validation |
| Dependencies | Other teams' clients, batch jobs, repair tooling, `cqlsh` |
| Rollback | Are old/new certs still unexpired; can images/configs revert? |

A certificate change can break **infrequently run jobs** (such as nightly backfills). The primary API passing does not prove every consumer has migrated.

### 17.4. Do Not Retire the Old CA Too Early

After servers switch to the new CA, older clients may keep already-established TCP/TLS connections alive and only fail on reconnect. Therefore:

- Test **new connections**, not just reused pool connections.
- Verify every application version, region, and DC.
- Test controlled reconnects/restarts in lab or canary environments.
- Allow caches, secret mounts, and rollouts to complete.
- Gather zero-error evidence across the old/new trust overlap window.

**A few error-free hours do not prove 100% of clients migrated** if weekly or monthly batch jobs haven't run yet. Rely on your inventory and concrete evidence.

## 18. Runbook A — `PKIX path building failed` After CA Rotation

**Scenario:** New Java pods throw `AllNodesFailedException`; candidate root causes show `SSLHandshakeException` with PKIX errors. Old pods still serve requests.

1. **Frame the incident:** pod version/namespace, JDK image, truststore secret version, local DC, UTC onset time.
2. **Inspect per-node map:** `getAllErrors()` shows which coordinator candidates fail; do not assume the cluster is DOWN.
3. **Check exact endpoints:** DNS/IP/native port actually dialed by the driver, not just the first contact point.
4. **Inspect served server chain:** `openssl s_client -showcerts` from an authorized network; compare leaf/intermediate/root and validity.
5. **Compare client trust:** `keytool -list -v` comparing CA fingerprints on healthy vs. failing pods; verify active `SSLContext`/JDK.
6. **Pinpoint exact flaw:** missing root CA, missing intermediate, expired intermediate, JDK algorithm rejection, or hostname mismatch.
7. **Remediate safely:** distribute valid trust bundle/chain or roll back the CA change per runbook; **never use a trust-all manager**.
8. **Canary:** open **new connections**, run a small CQL query with the app role; confirm TLS/auth and query success.
9. **Controlled rollout:** monitor driver handshake failures, API p99/errors, memory/CPU, and internode health if the CA is shared.
10. **Prevent:** CA trust overlap, cert chain linting, CI smoke tests, and expiration monitoring.

**Distinction:** if `openssl` validates the chain yet Java still throws PKIX, inspect the JDK truststore, algorithm constraints, and `SSLContext`. Never assume OpenSSL passing means the Java client is misbehaving without checking Java's trust path.

## 19. Runbook B — Expired Cassandra Server or Client Certificate

**Scenario:** Around `NotAfter`, handshake failures spike on certain nodes or pods while Cassandra CPU/disk stay normal.

### 19.1. Identify Which Certificate Expired

- **Server leaf certificate:** breaks every client verifying that node.
- **Intermediate CA:** invalidates the whole chain even if the leaf is unexpired.
- **Client certificate in mTLS:** rejects only apps/pods presenting that client cert.
- **Internode certificate:** disrupts node-to-node links, risking RF/CL failures.
- **JMX certificate:** breaks management tools without directly breaking native CQL.

Use your inventory, `openssl x509 -dates`, fingerprints, client/server logs, and UTC timeline to pinpoint it.

### 19.2. Remediation Steps

1. **Assess scope:** one node or all; one DC or multi-DC; clientAuth or serverAuth.
2. **Check clocks:** node/pod NTP offsets; distinguish `expired` from `not yet valid`.
3. **Renew cert per policy:** SANs, issuer chain, EKU, key usage, algorithms/ciphers.
4. **Stage trust overlap** if the CA changed; mTLS requires both directions.
5. **Canary and roll** by node/pod while preserving RF/CL.
6. **Ensure proper reload/restart:** a new cert on disk does not mean the listener is serving it yet.
7. **Verify served certificate:** check fingerprint/NotAfter directly over the native TLS endpoint.
8. **Smoke-test:** new connection, role login, and authorized `SELECT`/`MODIFY`.
9. **Monitor fallout:** handshake error rate, hints/streaming, replica health, p99, and timeouts.
10. **Document RCA:** why didn't monitoring, ownership, or the rotation pipeline catch it early?

**Never** roll back system clocks, install a trust manager accepting expired certs, or disable TLS in production.

## 20. Runbook C — Login Succeeds, Yet `UnauthorizedException` Occurs

**Scenario:** A Java service using the same TLS and username runs partition-key `SELECT` fine, yet `UPDATE` returns permission denied.

1. **Identify the statement:** CQL template, keyspace/table, and operation (SELECT/INSERT/UPDATE/DELETE/DDL).
2. **Identify effective role:** role used by the session, inherited roles, and target cluster environment.
3. **Check authorizer:** `CassandraAuthorizer`/plugin and version-specific role caches.
4. **Verify grants:** e.g., `LIST ALL PERMISSIONS OF telemetry_writer;` using an authorized role.
5. **Separate privileges:** `SELECT` for reads, `MODIFY` for writes; never grant `ALTER`/`DROP` casually.
6. **Diagnose cause:** migration created a new table without grants? Role renamed? Cache propagation lag? Secret swapped to another role?
7. **Remediate:** grant **least privilege on the exact resource** through audited change control.
8. **Test positive and negative cases:** allowed writes succeed; unauthorized resources remain denied.
9. **Measure:** Unauthorized error rate drops without spiking API/cluster errors.
10. **Prevent:** treat grants as reviewed migration artifacts tested by contract suites post-schema rollout.

### 20.1. Positive/Negative Permission Test

For a read-only role:

~~~text
Allowed:
    SELECT from telemetry_lab.readings_by_device_day

Denied:
    INSERT/UPDATE/DELETE on the same table
    ALTER TABLE
    DROP KEYSPACE
    GRANT permissions
~~~

Run tests on an **isolated test keyspace** with matching roles. Never run destructive DDL in production just to verify "deny works".

### 20.2. Auth Cache and Permission Propagation

After a `GRANT`, if a node/session briefly still reports Unauthorized, check release cache settings and confirm the target cluster/role. Never flush caches cluster-wide or mass-restart nodes without understanding impact. Verify across multiple coordinators in canary if needed.

## 21. Runbook D — Password/Secret Rotation Breaks Client Authentication

**Scenario:** New pods use secret version B while old pods use version A. TLS handshakes succeed, yet user authentication is rejected; errors may surface inside connection initialization / `AllNodesFailedException`.

1. **Never log secrets:** record only secret version ID, authorized role ID, and rollout UTC timestamp.
2. **Verify authenticator:** `PasswordAuthenticator` or custom provider? Does the role have `LOGIN=true`?
3. **Verify cluster/keyspace:** is the app accidentally pointing at another environment with different credentials?
4. **Compare role identity:** was the role renamed, locked/disabled (if supported), or has rotation not propagated?
5. **Check dependencies:** Vault/K8s secret mount, env var snapshot, config cache, and session lifecycle.
6. **Recover safely:** supply valid secret / roll back app version, or use phased rotation with **two overlapping identities** when supported.
7. **Never share a superuser:** do not switch the app user to admin to bypass errors.
8. **Canary:** new session logs in and runs a small SELECT; if WRITE testing is needed, target an authorized test table.
9. **Roll out in waves:** monitor authentication failures, connection churn, and API SLOs.
10. **Prevent:** rotation contracts, overlap/canary/expiry alerts, and stale-consumer checks.

### 21.1. Caution with Single-User Password Rotation

If a system uses **one role with a single active credential**, changing the password before older pods pick up the new secret can break new connections or reconnects. A safer pattern is **two roles with identical least-privilege grants**, rolling out the new role first and revoking the old role after cutover, where policy and architecture permit.

The goal is **safe identity transition**, not leaving old credentials active indefinitely.

## 22. Runbook E — Hostname Mismatch After Changing Contact Points/DNS

**Scenario:** A Java service switches its contact point from `cassandra-1.dc1.example.invalid` to an IP or load balancer alias. TLS fails on certain peers even though server certificates remain valid.

1. Inspect endpoints dialed by the driver: initial contact point and discovered peer addresses.
2. Inspect server cert SANs: do they include the DNS names or IPs actually used?
3. Inspect `-servername`/SNI and hostname validation rules in the driver SSL engine policy.
4. Inspect DNS records, NAT IPs, Kubernetes Services, proxies, and advertised native addresses.
5. Never disable hostname verification.
6. Fix the endpoint or issue certificates covering valid SANs per PKI policy.
7. With TLS-terminating proxies, inspect certificates on both client→proxy and proxy→Cassandra hops.
8. Test **new connections** to all peers in the local DC, not just one contact point.
9. Check p99, handshake failures, and native transport pool stability post-rollout.
10. Document naming rules before subsequent node joins, bootstraps, or replacements.

**Important:** When adding a new node, certificate naming rules must precede bootstrap; never bring up a node lacking proper SANs/CA and expect the driver to ignore validation.

## 23. Runbook F — Internode TLS Failures During Rolling Upgrade / CA Rotation

**Scenario:** Java pods still complete TLS with some nodes, yet a DC reports unavailable replicas and lagging hints/streaming after changing internode trust.

1. **Triage cluster safety:** RF, CL, node status, rack/DC, whether quorum still holds.
2. **Separate TLS paths:** Java→coordinator may be healthy while node→node internode TLS fails.
3. **Inspect each node:** cert chain, trust bundle, EKU/SAN, protocol/cipher, keystore reload.
4. **Check old/new trust overlap:** do upgraded nodes trust only the new CA while older nodes still present the old CA?
5. **Correlate internode logs:** handshake failures, gossip/streaming errors, connection resets.
6. **Never restart all nodes simultaneously:** roll safely per cluster topology to protect replica availability.
7. **If quorum is already lost:** prioritize restoring node-to-node connectivity/trust per SOP; never downgrade CL as a default workaround.
8. **Canary step-by-step:** confirm recovered nodes exchange replica traffic cleanly, not just `UN`.
9. **Watch downstream effects:** hints, streaming, repair, compaction/disk, read/write timeouts, and API p99.
10. **Prevent:** internode CA overlap, mixed-version/mixed-cert lab testing, and rehearsed rollbacks.

JMX auth/TLS can fail `nodetool` independently: if native CQL and internode traffic are healthy, check JMX credentials/SSL/ports before touching Cassandra cluster TLS.

## 24. Securing Logs, Metrics, and Incident Reports

### 24.1. Recommended Structured Event Format

~~~text
event=cassandra_security_connection_failure
timestamp_utc=2026-11-21T10:00:00Z
app_component=telemetry-reader
deployment_version=v42
query_template=latest20_by_device_day
outcome=tls_handshake_failure
error_family=cert_chain_validation
local_dc=dc1
candidate_nodes=3
cert_fingerprint=approved_digest_or_redacted
secret_version=approved_version_id_only
~~~

This is an **application-defined log schema**, not Cassandra's default log format. Log only approved node/cert/secret-version metadata per security policy; never log secrets, passwords, private keys, raw CQL bind values, or personal user data.

### 24.2. Appropriate Metrics

| Metric | Bounded Label Suggestions | Meaning |
|---|---|---|
| Auth failure rate | app, version, DC, error family | Secret/role mismatch |
| Unauthorized rate | query template, role class | Missing grants |
| TLS handshake failures | app, DC, failure family | CA/SAN/protocol/cert |
| AllNodesFailed rate | app, error family | Coordinator candidate failures |
| Connection pool | app instance/DC, in-flight, reconnect | Churn, handshake storms |
| Cert expiration | certificate group, days remaining | Early warning |
| API p99 / 5xx | endpoint/query template | User impact |
| Cassandra availability | DC/rack/node, RF/CL | Cluster safety |
| Internode errors | DC/rack/error family | Replica communication |

Never put raw error messages or arbitrary per-connection hostnames/IPs into unbounded metric labels. Never treat "days remaining" alone as sufficient: also verify **not-yet-valid, chain, SAN, EKU, and key rotation state**.

### 24.3. Information That Must Never Enter Tickets or Chat

- Full database usernames/passwords beyond need-to-know.
- Truststore/keystore passwords.
- PEM private keys or secrets from K8s/Vault.
- Raw TLS session keys, bearer tokens, or query bind values.
- Real customer/tenant IDs and record payloads.
- Multi-million-line repetitive stack traces or heap dumps containing secrets.

Use public fingerprints/serials and redacted log excerpts; store sensitive artifacts inside access-controlled systems.

### 24.4. Distinguishing Warnings from Actual Outages

A certificate with 20 days left is not itself an outage, yet it is a **risk** needing a rotation owner. An expired certificate on one node might not immediately cause a cluster-wide outage (if clients haven't routed there yet), yet it is an **urgent defect** requiring remediation before reconnects or rolling restarts.

Track app SLOs, availability, native TLS errors, and certificate expiry inventories together.

## 25. Regression Testing and Drills in an Isolated Cluster

### 25.1. Test Matrix for Authentication, Authorization, and TLS

| ID | Scenario | Expected Result | Evidence |
|---|---|---|---|
| T01 | Valid server cert, trusted CA, matching SAN | TLS handshake succeeds | Connection + CQL smoke test |
| T02 | Client missing root/intermediate CA | TLS handshake rejected | Classified PKIX/chain error |
| T03 | Expired server cert | Client rejects peer | Expired certificate cause/metadata |
| T04 | Not-yet-valid server cert | Client rejects peer | NotBefore/not-yet-valid |
| T05 | IP endpoint missing from SAN | Hostname verification fails | SAN vs. endpoint mismatch |
| T06 | TLS protocol/cipher mismatch | Handshake fails before CQL | Protocol negotiation evidence |
| T07 | mTLS requires client cert, client omits it | Server rejects client | Handshake/cert request logs |
| T08 | mTLS client cert has wrong EKU/chain | Handshake fails | Client cert chain metadata |
| T09 | Valid TLS, wrong CQL password | Auth failure | CQL authentication outcome |
| T10 | Role has `LOGIN=false` | Login denied for that role | Authentication outcome |
| T11 | Role has SELECT on target table | SELECT succeeds | Read one seeded row by full key |
| T12 | SELECT-only role attempts INSERT | Unauthorized | CQL permission denied |
| T13 | Role with MODIFY on target table | INSERT/UPDATE in test table succeeds | Read-back verification |
| T14 | Runtime role attempts ALTER/DROP | Unauthorized | Negative permission test |
| T15 | New GRANT and role/cache refresh | Query succeeds after propagation window | Actual timestamp, node, and role |
| T16 | Old + new CA both in trust bundle | Client connects under either trusted server chain | Test new connections |
| T17 | Remove old CA after all consumers migrate | Only new CA certs trusted | Inventory + canary reconnect |
| T18 | Same secret version across two JDK images | Detects disabled cipher/algorithm/truststore drift | JDK/SSL diagnostics |
| T19 | Single server node has bad cert | Per-node map pinpoints exact failing node | `getAllErrors()` |
| T20 | Java→coordinator OK, internode TLS broken | RF/CL errors clearly distinguished | Server/internode logs |
| T21 | Wrong JMX credentials, Java CQL healthy | Only management path fails | `nodetool` and Java outcomes |
| T22 | Clock skew in isolated lab | Certificate validity evaluated properly | UTC/NTP offset |
| T23 | Secret rotation across pod subset | Canary/rollback causes no wide outage | Connection + API metrics |
| T24 | TLS failure retried infinitely (negative test) | Guardrail/retry budget prevents storm | Retry attempts / CPU |
| T25 | Cross-tenant authorization test | Principal properly denied | Business authorization outcome |

**Never rehearse T02–T08, T20, or T22 in production.** Build test certs in lab/CI with dedicated PKI; never forge production private keys or alter clocks on real nodes.

### 25.2. Limitations of Single-Node Testcontainers

A single Cassandra Testcontainers instance can test:

- SSL/auth configuration in a supported environment.
- Role SELECT/MODIFY and negative grants.
- Java Driver truststore/keystore loading.
- Root-cause logging and query smoke tests.

However, a single RF=1 node **cannot represent** multi-DC internode failures, quorum behavior during node outages, cluster-wide role/permission caches, or rolling CA rotations across racks. Those scenarios require a **multi-node lab cluster** where network policies can be safely tested.

### 25.3. Test Correctness, Not Just Handshake Success

Successful TLS + successful authentication are only **necessary preconditions**. Next, verify:

1. SELECT by full partition key returns expected results.
2. INSERT/UPDATE succeeds only for authorized roles on test tables.
3. Unauthorized operations are rejected.
4. RF/CL succeed/fail as designed under lab fault injection.
5. Retries cause no duplicate write side effects.
6. No regressions in driver p95/p99 or connection churn.
7. No secrets/PII leak into logs even on failed connections.

## 26. Recovery Verification Workflow from App to Replica

### 26.1. Three-Layer Health Check

~~~text
Layer 1 — Transport & TLS
  [ ] TCP/native listener reachable from app namespace
  [ ] Certificate chain, validity, SAN, and TLS policy valid
  [ ] New connection from canary completes handshake

Layer 2 — Identity & Permissions
  [ ] CQL authentication succeeds with actual runtime role
  [ ] SELECT/MODIFY permitted on intended tables
  [ ] DDL/unapproved tables denied per least privilege

Layer 3 — Data & Distributed Availability
  [ ] Full-partition-key queries succeed at business CL
  [ ] Replica availability satisfies RF/CL
  [ ] Timeouts/errors/p99 within SLO
  [ ] Internode, hints, repair, streaming, compaction stable
~~~

A system can pass Layer 1 and fail Layer 2, or pass Layer 2 and fail Layer 3. **Never announce "fully resolved" the moment an `openssl` handshake succeeds.**

### 26.2. Verify the Runtime Role in the Actual Environment

In Spring Boot / Spring Data Cassandra apps, credentials may come from multiple profiles:

- Local development secrets.
- Kubernetes Secrets, mounted files, or environment variables.
- Vault/secret manager plugins.
- App-built driver profiles / session factories.
- Spring Boot / driver version auto-configuration.
- CI/staging test overrides.

Compare **effective configuration** per pod/version without printing secrets. A property in Git is not guaranteed to be the value in memory; likewise, updating a mounted secret does not mean the driver automatically reloads credentials.

### 26.3. Measure Performance Side Effects After Security Fixes

Following rotation, watch for:

- Temporary TLS handshake spikes during reconnects.
- Higher CPU from encryption and certificate validation.
- Slow driver connection pool rebuilds.
- Elevated read/write latency while nodes restart in rolling batches.
- Extended hints/streaming/compaction after rolling restarts.
- Connection errors clustered in a single rack or DC.

Recovery verification should confirm **healthy steady state**: API success rate, p99, driver exceptions, connection counts, node statuses, and replica resources.

### 26.4. Guard Against False Positives from Long-Lived Existing Connections

Pools opened prior to `NotAfter` or CA rotation can keep passing traffic over existing connections depending on implementation/policy until reconnect. Smoke tests must therefore include:

- **A new `CqlSession`/new connection** in lab/canary.
- Canaries running long enough to cover connection renewals.
- Checks across each relevant node/DC, not just one hostname.
- Rollout tracking across all batch jobs and client applications.

Never force a full production restart just to "test" without an approved change procedure.

## 27. Anti-Patterns That Cause Secondary Incidents

| Bad Action | Why It Is Dangerous | Right Approach |
|---|---|---|
| Disabling TLS when certs fail | Loses transport security | Renew/rotate with valid chain |
| Trust-all `X509TrustManager` | Skips peer identity check, risks MITM | Truststore with approved CAs |
| Disabling hostname verification | Permits endpoint spoofing | Proper SANs and hostname policy |
| Lowering CL from LOCAL_QUORUM to ONE for TLS errors | Alters correctness without fixing the fault | Investigate security/replica path |
| Granting superuser to app on Unauthorized | Excessive privileges, huge blast radius | Least-privilege GRANT on target resource |
| Enabling `AllowAllAuthorizer` | Disables Cassandra access control | Configure proper authorizer |
| Changing passwords via CLI `-p password` | Exposes secrets in shell history/process args | Secret provider / secure prompt |
| Logging full `getMessage()` on every request | Leaks metadata/secrets, causes log storm | Structured logs with redaction/sampling |
| Retrying `SSLHandshakeException` infinitely | Cannot conjure a missing CA; CPU/network storm | Fail fast and fix config/PKI |
| Treating `AllNodesFailed` as all nodes DOWN | Wrong scope, misdiagnoses replicas | Inspect per-coordinator `getAllErrors()` |
| Checking certs only on disk | Process may still serve old cert | Inspect live leaf over endpoint |
| Removing old CA before clients migrate | Older clients hit PKIX failures | Maintain trust overlap |
| Rotating all Cassandra nodes at once | Breaks RF/CL quorum | Roll per cluster topology |
| Using `nodetool status` to prove CQL TLS works | JMX differs from native transport | Java/`cqlsh` smoke tests |
| Using admin `cqlsh` to claim app role has grants | Different roles | Test with runtime role |
| Shifting node clocks when certs expire | Breaks distributed time assumptions | Renew certs and sync NTP |
| Reading local timezones without conversion | Misreads NotBefore/NotAfter | UTC-normalized timelines |
| Omitting intermediate CAs | Incomplete chain despite valid leaf | Verify full chain/trust |
| Ignoring discovered peer addresses | Contact point works, peers fail | SANs for all endpoints driver uses |
| Treating mTLS cert as SELECT permission | TLS identity differs from RBAC | Separate TLS from CQL authorization |
| Treating auth fix as data correctness proof | CL/partition errors may still exist | Verify all three layers |
| Reconnecting every service simultaneously | Connection/CPU/network storm | Canary and staggered rollout |
| Skipping negative permission tests | Authorizer might not be enforcing | Assert unauthorized ops are denied |
| Forgetting scheduled batch jobs | Old CA removed before batch jobs migrate | Full inventory and adequate window |

## 28. Practice Questions with Answers

### Question 1 — Authentication vs. Authorization

Client passes TLS, logs in, and runs SELECT successfully, yet INSERT returns denied. Which layer is most likely failing?

**Answer:** Authorization. The role likely has `SELECT` but lacks `MODIFY` on the table. Do not alter truststores or grant superuser.

### Question 2 — PKIX When Cert Is Unexpired

The server leaf cert has six months left, yet Java throws `PKIX path building failed`. Is the cert definitely expired?

**Answer:** No. The truststore may be missing a CA or the server failed to send an intermediate; also check JDK security policies.

### Question 3 — SANs and IPs

The driver connects by IP while the certificate only has a DNS SAN. Why can the handshake fail?

**Answer:** Hostname/IP validation fails to match any SAN. Use a matching endpoint or issue a cert with the appropriate IP SAN; never disable verification.

### Question 4 — NotBefore

A new certificate has `NotBefore` in the future relative to the client. What is the right action?

**Answer:** Verify UTC/NTP clocks and issuance timing, and reissue/roll out a valid cert if needed; never shift system clocks to bypass checks.

### Question 5 — NotAfter

A server cert just expired, yet pods still read over older open connections. Can rotation be treated as non-urgent?

**Answer:** No. New connections and reconnects will fail. Renew/rotate immediately and verify the listener actually serves the new cert.

### Question 6 — getAllErrors

`AllNodesFailedException.getAllErrors()` lists nodes A and B. Is this a map of replica ACKs?

**Answer:** No. These are coordinator candidates and driver-observed exceptions; never use it to infer replica write outcomes.

### Question 7 — Auth Failure vs. Unauthorized

Does a wrong username/password usually occur after `SELECT` begins executing?

**Answer:** Bad credentials normally fail session authentication before CQL permissions are checked; Unauthorized occurs during permission checks after authentication.

### Question 8 — JMX vs. CQL

`nodetool status` succeeds while Java CQL throws a handshake failure. Is the node guaranteed healthy for native TLS?

**Answer:** No. `nodetool` normally uses JMX, whereas Java uses native transport/TLS. Always test from the app network.

### Question 9 — mTLS

Cassandra requires a client certificate, and Java only has a CA truststore for the server. Is that enough?

**Answer:** No. The client needs an identity certificate, private key, and chain, and the server must trust the client CA. CQL auth/permissions may still be needed separately.

### Question 10 — CA Rotation Order

Which order is safer: roll out leaves signed by the new CA first and distribute trust later, or distribute old+new trust first?

**Answer:** Normally **expand trust first**, verify clients/nodes received it, then roll out new leaves; remove the old CA only after all consumers migrate.

### Question 11 — CqlSession Lifecycle

Does creating a new `CqlSession` per HTTP request prevent long-term TLS issues?

**Answer:** No. It causes connection/handshake storms, driving up CPU and latency. Reuse a shared session and fix the underlying trust/auth root cause.

### Question 12 — Password Rotation

New pods use secret B while old pods use A, and the single role allows only one active password. What is the risk?

**Answer:** Mixed pods fail authentication on reconnects. Use phased identity/credential rotation or overlap per policy.

### Question 13 — Least-Privilege Role

A service only reads one table. What grants are appropriate?

**Answer:** `SELECT` on the specific table/keyspace needed, never `ALL PERMISSIONS ON ALL KEYSPACES`.

### Question 14 — Invalid Query

Cassandra rejects a query for missing a partition key. Should you run `GRANT MODIFY` to fix it?

**Answer:** No. That is a query-shape/CQL restriction error, not a permission issue; fix the query or schema design.

### Question 15 — Tenant Security

A Cassandra role has table-wide SELECT; the app accepts a tenant ID from the URL without authorization checks. Are TLS and CQL bind parameters enough to protect data?

**Answer:** No. Authenticate the principal, enforce ownership/authorization in the application, and design proper tenant isolation.

### Question 16 — TLS Proxy

A client completes TLS to a proxy. Does that prove the proxy→Cassandra hop is also verified TLS?

**Answer:** No. Inspect architecture, trust/certs, and policies on each hop independently.

### Question 17 — Root/Intermediate Chain

The leaf is signed by Intermediate-CA; the client trusts only the valid root, and the server omits the intermediate. What happens?

**Answer:** The client cannot build the chain and throws a PKIX/issuer error. The server must serve the full chain (or the client must trust the intermediate per policy).

### Question 18 — Debug Logs

Should verbose SSL debug logging be left on across all production pods for days?

**Answer:** No. It causes I/O and log storms and risks leaking metadata; limit debugging by scope and time window with redaction and access controls.

### Question 19 — Rolling Internode CA

Half the cluster trusts only the new CA while the other half only presents leaves from the old CA. What breaks?

**Answer:** Internode handshake failures, disrupting replica messaging, streaming, and CL guarantees. Use trust overlap and rolling sequencing, never simultaneous restarts.

### Question 20 — Certificate Alerts

A leaf expires in 14 days, has an owner and renewal pipeline, but no canary test. Is prevention complete?

**Answer:** Not yet. Validate renewal, chains/SANs, rollout/reload, new connections, and monitoring ahead of deadline; tie alerts to actions and owners.

### Question 21 — TLS vs. CQL Timeouts

The driver reports `ReadTimeoutException` after the session authenticated cleanly. Can you conclude a certificate expired?

**Answer:** No. That is a read/replica/CL path signal; investigate latency/availability, not TLS expiry.

### Question 22 — Recovery Sign-Off

After renewing a cert, an OpenSSL handshake succeeds. Can the incident be closed immediately?

**Answer:** Not yet. Verify role authentication, permissions, full-partition-key queries, CL, success/error/p99 metrics, and new connections across client versions and DCs.

## 29. Production Checklists Before and After Rotation

### 29.1. Before Certificate/Secret Change

~~~text
[ ] Inventory all clients, batch jobs, nodes, DCs, proxies, mTLS/JMX paths.
[ ] Record NotBefore/NotAfter, SANs, issuer, chain, fingerprint/serial.
[ ] Prepare old+new CA bundle if rotating CA, with trust overlap window.
[ ] Test JDK/driver/server TLS compatibility in lab.
[ ] Confirm actual runtime SSLContext/truststore used by the driver.
[ ] Protect secrets/keystores/private keys in Vault/PKI.
[ ] Assign owner, change window, rollback plan, and RF/CL guardrails.
[ ] Prepare canary testing new connections, not just reused open pools.
[ ] Configure expiry alerts and verify the certificate actually served.
[ ] Never weaken TLS verification or grant temporary superuser.
~~~

### 29.2. During Rollout

~~~text
[ ] New canary pod completes TLS handshake + CQL auth cleanly.
[ ] Inspect per-candidate getAllErrors() on any failure.
[ ] Runtime role works for needed SELECT/MODIFY; DDL remains denied.
[ ] TLS SAN/chain/validity verified for every driver-discovered node/peer.
[ ] Internode/JMX paths verified independently per topology.
[ ] Rolling updates preserve replica quorum per RF/CL; no simultaneous restarts.
[ ] Retries/connection churn do not trigger CPU/handshake storms.
[ ] Monitor API p95/p99, errors, driver pools, and node metrics.
[ ] Zero secrets/passwords/raw bind values in logs.
[ ] Authority ready to roll back immediately if criteria fail.
~~~

### 29.3. After Rollout

~~~text
[ ] New connections to every local DC/peer succeed reliably.
[ ] Full-primary-key queries return accurate data within CL and timeout budgets.
[ ] Unauthorized and authentication failure rates return to baseline.
[ ] Served certificates reflect the new version with adequate expiry horizon.
[ ] Legacy clients/batch jobs migrated or explicitly scheduled.
[ ] Internode streaming, hints, compaction/repair, and p99 are stable.
[ ] Remove old CA only after proving every consumer is ready.
[ ] Complete RCA, update inventory/trust matrix, automate expiry alerts.
[ ] Never treat a security fix as a substitute for data correctness checks.
[ ] STEP 6 Content QA will be conducted separately per process.
~~~

## 30. Summary

Troubleshooting **authentication, authorization, TLS, and expired certificate failures** in Apache Cassandra requires tracking exact boundaries:

1. **TLS transport** verifies peers, chains, hostnames, and protocols; PKIX, SAN, or expiry failures happen before CQL permissions are evaluated.
2. **Authentication** confirms the role/identity can log in; passwords/secrets, `LOGIN`, and authenticators must match.
3. **Authorization** enforces resource privileges; missing `SELECT`/`MODIFY` cannot be solved by swapping certificates.
4. **Native CQL, internode, and JMX** are separate security planes; one working plane does not prove the others are healthy.
5. **`AllNodesFailedException.getAllErrors()`** must be read by coordinator candidates and cause chains, never as a replica ACK map or cluster-wide DOWN verdict.
6. **Certificates have multiple validity dimensions**: CA chain, NotBefore/NotAfter, SANs, EKU, algorithm policies, JDK truststores, and UTC clocks.
7. **Java Driver and OS tools may use different trust stores**; OpenSSL passing does not guarantee Java's `SSLContext` will succeed.
8. **Rotations require trust overlap, canaries, and rolling waves**; never remove an old CA before all clients and nodes migrate.
9. **Never take shortcuts that compromise security**: trust-all, disabled hostname validation, `AllowAllAuthorizer`, shared admin users, or shifting system clocks are all wrong.
10. **Fixes can trigger distributed side effects**: monitor node restarts, internode trust, replica availability, hints/repair/compaction, and p99.
11. **Recovery is complete only when all three layers pass**: TLS, role/permissions, and query correctness/CL/API SLOs.
12. **Prevent recurrence** with cert expiry alerts, CA/secret inventories, tested rollbacks, negative permission tests, and safe logging.

The core question is not **"Why won't Java connect to Cassandra?"** in the abstract, but **"At which step was the connection rejected, which peer/cert/role/resource mismatched, what is the node/DC/client scope, and which change restores identity and permissions while preserving the cluster's RF/CL guarantees?"** Answering with layer-by-layer evidence fixes the true root cause without turning a certificate incident into a broader data or security outage.

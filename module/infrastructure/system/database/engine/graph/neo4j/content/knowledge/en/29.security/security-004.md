# Connection Encryption, TLS Certificates, and Server Identity Verification in Neo4j

## 1. Security challenges when connecting to Neo4j

Applications use **Neo4j** to store data as a **property graph**, from `Customer` nodes and `PURCHASED` relationships to transaction properties or system dependency structures. Cypher requests sent over the network can carry identifiers, business data, and access credentials. If the transport channel is not properly protected, a third party can observe or tamper with the connection session.

Within the **Security** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module, this lesson focuses on **the Bolt protocol used by the Neo4j Java Driver, Spring Data Neo4j, and applications to communicate with Neo4j**. The goal is to protect **data in transit** and verify **which server actually receives the query**, rather than merely toggling an "encryption" option.

After this lesson, you will be able to:

1. Distinguish **data confidentiality**, **integrity verification**, and **server identity authentication** in TLS.
2. Choose `neo4j+s://` and `bolt+s://` URIs in the right context, and understand the risks of `+ssc` and unverified TLS URIs.
3. Read key components of a server certificate: CA, trust chain, SAN, DNS name, and validity period.
4. Configure secure connections in Java Driver and Spring Boot/Spring Data Neo4j without placing passwords in source code.
5. Verify cluster/routing connections, proxies, certificate renewal workflows, and common TLS errors.
6. Design tests so the application **rejects untrusted connections** instead of silently downgrading security.

> **Version scope:** Examples target Neo4j 5.x, Neo4j Java Driver 5.x, Spring Boot 3.x, and corresponding Spring Data Neo4j releases. Specific **server** setting names and trust-strategy details can vary by version and deployment type; always consult the documentation for the exact version in use. This content is technical guidance and does not replace your organization's security policy.

## 2. What does TLS protect?

**TLS (Transport Layer Security)** protects the communication channel between an application and a server. When properly configured, TLS provides related but distinct guarantees:

| Property | Meaning for Neo4j connections | Misconception to avoid |
| --- | --- | --- |
| **Confidentiality** | Network observers cannot read Bolt/Cypher traffic in transit | Does not mean data is encrypted at rest on disk |
| **Integrity** | Exchanged data is protected against undetected modification in transit | Does not prove business data contents are valid |
| **Server authentication** | The client verifies the certificate and target name of the connected server | Having any valid-looking certificate is **not** enough to prove the right server |

Illustration:

```mermaid
sequenceDiagram
    participant A as Java / Spring Boot
    participant M as Intermediate Network
    participant N as Neo4j Bolt
    A->>N: Request TLS connection setup
    N-->>A: Certificate and TLS handshake details
    Note over A: Verify CA/chain, SAN/DNS, validity, and policy
    A->>N: Complete TLS if verification succeeds
    A->>N: Bolt messages / authentication / Cypher over TLS
    N-->>A: Query results over TLS
```

An attacker positioned between the application and target address can present a certificate they generated themselves. **If the client accepts every certificate**, the attacker can establish an encrypted channel while still impersonating the server. Therefore, you must verify **who is on the other end of the connection**, rather than trusting a lock icon or knowing a port speaks TLS.

Three independent security layers must work together:

1. **TLS:** protects transport and endpoint identity.
2. **Neo4j authentication/authorization:** verifies users/tokens, databases, roles, and privileges (`MATCH`, `CREATE`, `MERGE`, procedures).
3. **Application controls:** enforces tenant checks, Cypher parameterization, endpoint authorization, logging, and data-handling policies.

TLS does **not** replace node/relationship authorization, query parameterization, or encryption at rest.

## 3. Choosing a URI: direct Bolt, routing, and TLS modes

The Neo4j Java Driver accepts URIs whose scheme specifies the connection mechanism. The table below describes common usage:

| URI | Routing | TLS security | Use case |
| --- | --- | --- | --- |
| `bolt://localhost:7687` | Direct connection | TLS not requested by this scheme | Only in isolated and authorized dev/test environments |
| `neo4j://db.example.com:7687` | Routing enabled | Does not guarantee TLS via `+s` suffix | Unsuitable when policy mandates verified TLS |
| `bolt+s://db.example.com:7687` | Direct connection | TLS with trusted certificate and hostname verification | Single server or direct endpoint configured with TLS |
| `neo4j+s://db.example.com:7687` | Routing enabled | TLS with trusted certificate and hostname verification | Clusters or routing services using standard TLS |
| `bolt+ssc://db.example.com:7687` | Direct connection | TLS for self-signed certificates under relaxed driver trust mode | Consider only in controlled test environments |
| `neo4j+ssc://db.example.com:7687` | Routing enabled | TLS accepting self-signed certificates / relaxed verification | Consider only in test environments |

In the table, `db.example.com` is an **illustrative domain name**. The common default Bolt port is `7687`, though infrastructure may expose a different port.

### 3.1. Two separate decision axes

**First axis: topology.**

- `bolt...` generally targets a single direct endpoint.
- `neo4j...` lets the driver use routing, suitable when a server or cluster advertises addresses for read and write operations.

**Second axis: TLS verification.**

- `+s` requires a TLS channel and server identity verification against trusted certificates.
- `+ssc` exists for working with self-signed certificates under a special trust mode; **it does not provide the same identity protection as `+s` against a properly configured trust chain**.
- Without `+s`/`+ssc`, do not assume traffic is safely encrypted; exact behavior depends on version and server configuration.

For production, the standard rule is **`neo4j+s://` or `bolt+s://` with a managed trust anchor**. Never switch from `+s` to `+ssc` merely to silence certificate errors.

### 3.2. Connection settings must not disable verification

A common mistake is configuring Java to "trust all certificates" or switching to `+ssc` in production when hitting `PKIX path building failed`. That defeats **server authentication**.

The right troubleshooting approach is to determine:

1. Which **hostname** is the application connecting to?
2. Which **certificate chain** does the server actually present?
3. Which **hostnames** was that certificate issued for?
4. Are the required root or intermediate CAs in the **client's trust store**?
5. Is the certificate within its validity window, unrevoked per policy, and properly configured on the server?

## 4. X.509 certificates and server verification

A server certificate typically contains a **public key**, server identity details, validity dates, and the signature of a Certificate Authority (**CA**).

To accept an endpoint under standard TLS policy, the client checks multiple conditions:

| Component | Verification question |
| --- | --- |
| **Certificate chain** | Does the server certificate chain through intermediate CAs to a trust anchor trusted by the client? |
| **SAN (Subject Alternative Name)** | Is the DNS name or IP address the app connects to present in a valid SAN? |
| **Validity period** | Is the current time between `Not Before` and `Not After`? |
| **Signature and algorithms** | Is the signature valid, and are the algorithms and key lengths permitted by policy? |
| **Key usage/EKU** | Is the certificate valid for server authentication? |
| **Server private key** | Can the server prove possession of the corresponding private key? |
| **Revocation policy** | Do OCSP/CRL checks or revocation governance meet system requirements? |

The **Common Name (CN)** in the Subject should not be treated as a default substitute for SAN when verifying hostnames. Modern TLS clients prioritize SAN; issue certificates with SAN entries matching the actual DNS names or IPs in use.

### 4.1. Valid and invalid hostname examples

Suppose the application is configured with:

```text
NEO4J_URI=neo4j+s://graph.prod.example.com:7687
```

The server certificate contains the DNS SANs:

```text
DNS:graph.prod.example.com
DNS:graph-router.prod.example.com
```

Here the **name matches** the illustrative URI, though CA chain, validity, and other TLS checks must still pass.

If the application changes the URI to:

```text
NEO4J_URI=neo4j+s://10.0.4.23:7687
```

then a certificate containing only those DNS SANs **cannot verify the IP address**. To connect via IP, the certificate must carry a matching **IP SAN** and the client must allow it per policy; the easier-to-operate choice is usually connecting via the certified DNS name.

Never work around this by arbitrarily editing hosts files or disabling hostname verification in production. Ensure the URI name, DNS/routing, and certificate match consistently.

### 4.2. Public CAs, internal CAs, and self-signed certificates

Three common scenarios occur:

1. **Trusted public CA:** fits endpoints exposed under organizational policy; clients may already have the trust anchor via Java/driver defaults.
2. **Organizational internal CA:** clients must be configured to trust the internal CA using a mechanism supported by the driver/JVM, with secure CA distribution and lifecycle control.
3. **Self-signed server certificate:** has no chain to a trusted CA unless explicitly provisioned as a trust anchor through a dedicated process. Using `+ssc` to accept it broadly carries risk and should not replace production CA trust processes.

**An internal CA does not mean weaker security.** When the CA is tightly governed, the server certificate carries the right SANs, and clients trust only the required CAs, `+s` still properly authenticates the server per policy.

### 4.3. Private keys differ from public certificates

The server certificate holds the **public key**; it is not a password and is routinely sent to clients during the TLS handshake. The corresponding **private key** must be protected on the server or in a secret manager with strict file permissions, and never placed in repositories, container images, or logs.

If a private key is compromised, execute an incident-response workflow: generate a new key, issue a new certificate, revoke the old certificate where applicable, and assess impact. Rotating the Neo4j application password **does not replace** a compromised TLS private key.

## 5. Neo4j server configuration and the administrator's role

For clients to use `+s`, the endpoint must **actually support TLS** and present a valid certificate. In self-managed deployments, operations teams typically need to:

1. Issue a server certificate with SANs matching the DNS names clients will use.
2. Store the certificate chain and private key in a secure location with minimal file permissions.
3. Configure the **Bolt TLS policy** appropriate to the Neo4j version.
4. Set Bolt to require TLS connections if policy mandates encryption.
5. Restart or reload per deployment procedures and test from **the client's network**, not only on the server itself.

Example **illustrating configuration setting groups**, not a complete copy-paste configuration:

```properties
# These names are common in self-managed Neo4j 5.
# Verify exact version, file paths, and cluster policy before applying.
server.bolt.enabled=true
server.bolt.tls_level=REQUIRED
dbms.ssl.policy.bolt.enabled=true
# public_certificate/private_key paths and trust settings
# must be configured per the structure supported by your Neo4j release.
```

This is a **server configuration decision**, not application Java code. Enabling TLS policies, certificate/key paths, optional client authentication, file permissions, and reload procedures must follow the **Neo4j Operations Manual for your exact version**.

### 5.1. Do not confuse Bolt TLS with HTTPS

Neo4j can expose multiple interfaces:

- **Bolt** for Neo4j Java Driver/Cypher clients, typically on port `7687`.
- **HTTP/HTTPS** for separately configured HTTP endpoints.
- **Internal cluster communication** with its own protection requirements.

Having a valid certificate on an HTTPS website or reverse proxy **does not prove** Bolt connections to the database use TLS. Verify the **exact endpoint and protocol** the application actually uses.

### 5.2. Managed deployments

In managed Neo4j services, users may not be allowed to directly edit server TLS policies or private keys. In that case, follow the TLS endpoints and URIs published by the provider; do not extrapolate certificate management steps from self-hosted examples.

## 6. Java Driver: configuring and verifying TLS connections

The Neo4j Java Driver takes a URI and authentication credentials. The Java 17+ example below enforces a `+s` scheme and runs only a minimal test query:

```java
import java.net.URI;
import java.util.Set;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class Neo4jTlsProbe {
    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "Missing required configuration: " + name
            );
        }
        return value;
    }

    public static void main(String[] args) {
        String uriText = requiredEnv("NEO4J_URI");
        String username = requiredEnv("NEO4J_USERNAME");
        String password = requiredEnv("NEO4J_PASSWORD");
        String database = requiredEnv("NEO4J_DATABASE");

        URI uri = URI.create(uriText);
        if (!Set.of("neo4j+s", "bolt+s")
                .contains(uri.getScheme())) {
            throw new IllegalArgumentException(
                "A TLS-verified Neo4j URI is required"
            );
        }
        if (uri.getUserInfo() != null) {
            throw new IllegalArgumentException(
                "Credentials must not be embedded in URI"
            );
        }

        try (Driver driver = GraphDatabase.driver(
                 uriText, AuthTokens.basic(username, password))) {
            driver.verifyConnectivity();

            try (Session session =
                     driver.session(SessionConfig.forDatabase(database))) {
                int answer = session.executeRead(tx ->
                    tx.run("RETURN 1 AS ok")
                      .single().get("ok").asInt()
                );
                if (answer != 1) {
                    throw new IllegalStateException(
                        "Unexpected connectivity test result"
                    );
                }
            }
            System.out.println("Neo4j connectivity verified");
        }
    }
}
```

Key takeaways:

- `Set.of("neo4j+s", "bolt+s")` is an **example application policy**: preventing deployment config from switching to an unverified TLS URI. In real products, dev/test exceptions can live in a **separate, controlled profile**.
- `verifyConnectivity()` tests server reachability and driver initialization; if the chain, hostname, or TLS fails, connection setup fails.
- `RETURN 1 AS ok` only confirms a trivial query succeeded; it **does not prove** the user holds privileges on all labels, relationships, indexes, or procedures.
- Passwords are read from the environment rather than hard-coded. Environment variables are **not an absolute vault**: privileged processes and diagnostics can read them; use a secret store or mounted secrets per organizational policy.
- In this example, never log passwords, AuthTokens, URIs containing userinfo, or stack traces with sensitive details to APIs. Log errors safely with correlation IDs.

Never create a new `Driver` per **HTTP request** in a web service; the driver manages a connection pool and should live for the application's lifetime, closing on shutdown.

### 6.1. Using an internal CA with Java

If certificates are signed by an **internal CA**, the application must trust that CA using a mechanism compatible with your Java Driver version. Evaluate two approaches:

- **Managed JVM/application trust store**, when the driver's TLS configuration and stack use that trust store.
- **Custom trust strategy supported by Neo4j Java Driver**, pointing to the verified, distributed CA certificate.

Do not assume simply copying `company-ca.pem` into a container makes the driver read it. Verify the **config path, certificate format, chain, trust strategy, and DNS name** via integration tests.

Never put the server's private key inside the Java app to "make the client trust the server." Clients only need the **public trust anchor**; the server's private key stays on the TLS-serving endpoint.

## 7. Spring Boot and Spring Data Neo4j

In Spring Boot, `spring-boot-starter-data-neo4j` integrates SDN and the Java Driver. You can configure:

```yaml
spring:
  application:
    name: graph-service
  neo4j:
    uri: ${NEO4J_URI}
    authentication:
      username: ${NEO4J_USERNAME}
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: ${NEO4J_DATABASE}
```

Example non-secret production values:

```text
NEO4J_URI=neo4j+s://graph.prod.example.com:7687
NEO4J_DATABASE=neo4j
```

`NEO4J_USERNAME` and `NEO4J_PASSWORD` must come from an organization-approved secret manager, never committed as real values in YAML.

Distinguish:

- `spring.neo4j.uri` defines the **driver** endpoint and connection scheme.
- `spring.neo4j.authentication.*` provides the Neo4j login account.
- `spring.data.neo4j.database` selects the **target database** for SDN.

Do not override security settings by defining a custom `Driver` bean with relaxed trust mode while overlooking Spring Boot's managed bean configuration. If customization is truly required, use the Boot/SDN-supported customizer/configuration hooks and verify behavior at runtime.

### 7.1. Tests distinguishing TLS errors from authorization errors

A service can:

1. Connect over **valid** TLS and authenticate the server.
2. Authenticate username/password **correctly**.
3. Still have a `MATCH` or `MERGE` query rejected due to **missing privileges**.

These are three separate steps. Never "fix" an authorization error by switching `neo4j+s://` to `neo4j://` or substituting an administrator account.

In a multi-tenant database, TLS alone does not isolate tenants: the backend must also bind tenant context from the authenticated user identity, parameterize Cypher queries, and ensure roles/privileges enforce policy.

## 8. Routing, clusters, proxies, and endpoint identity

An application using `neo4j+s://router.example.com:7687` may initially connect to a **seed/router**; the driver then fetches routing information and connects to other servers. This is a key difference from a direct `bolt+s://` URI.

Illustration:

```mermaid
flowchart LR
    A["Java Driver"] -->|TLS + hostname check| R["router.example.com"]
    R -.->|routing table| A
    A -->|TLS + hostname check| S1["reader-1.example.com"]
    A -->|TLS + hostname check| S2["writer-1.example.com"]
```

For routing:

- Not only must the seed's certificate be valid; **every endpoint the driver actually connects to** must present a certificate matching its hostname and trusted by the client.
- **Advertised** addresses must have DNS/ports reachable from the application's network. Internal-only addresses unreachable from external Kubernetes clusters or VMs will break routing even if the seed URI works.
- Do not assume every server in a cluster shares one certificate whose SAN covers all names; operations must maintain a proper certificate strategy.
- With load balancers or proxies, know **where TLS terminates**. If a proxy terminates TLS and opens unencrypted Bolt to Neo4j, the proxy-to-Neo4j hop is not protected by that TLS session.

### 8.1. Why a valid proxy certificate may still fall short

Consider:

```text
Application -- TLS --> Proxy -- plaintext Bolt --> Neo4j
```

The application verified the **proxy's** identity, not the backend Neo4j server. Such a setup may be permitted inside an isolated network by policy, but it must not be labeled **end-to-end TLS to the database**.

When end-to-end encryption is required, protect the proxy–Neo4j hop as well or use an appropriate TLS passthrough architecture and verify endpoints as designed.

### 8.2. DNS, SANs, and IPs in clusters

With `neo4j+s://`, both the initial hostname and all server-advertised hostnames must match the certificates served by their respective endpoints. If the routing table advertises IP addresses while certificates contain only DNS SANs, hostname verification can fail. Fix the **advertised addresses/certificates**—do not downgrade TLS.

## 9. Testing TLS and diagnosing failures

### 9.1. Check with Java Driver first

Recommended sequence:

1. Use the proper `+s` URI and application account in a test environment.
2. Run `driver.verifyConnectivity()`.
3. Execute `RETURN 1 AS ok` against the **target database**.
4. Perform a low-impact business operation to verify permissions.
5. With routing, test both read and write operations to exercise different endpoints.
6. Confirm logs contain no tokens, passwords, or private keys.

If the connection fails, isolate the **point of failure** rather than changing multiple settings at once.

### 9.2. Inspecting certificates with network tools

In operational environments where OpenSSL is permitted, you can **inspect the certificate chain** at the Bolt endpoint:

```bash
openssl s_client \
  -connect graph.prod.example.com:7687 \
  -servername graph.prod.example.com \
  -showcerts \
  -verify_hostname graph.prod.example.com \
  -verify_return_error </dev/null
```

This is a POSIX shell example assuming an OpenSSL build supporting these flags. It **does not send Neo4j username/password credentials**, and only checks certain TLS aspects; verification may also require your organization's internal CA bundle. On PowerShell or other tools, command-line syntax will differ.

Notes:

- `-servername` sends SNI when supported by the endpoint; critical when proxies host multiple domains.
- `-verify_hostname` enforces hostname matching; merely seeing a certificate printed is not enough.
- A passing OpenSSL check **does not replace** testing with the Java Driver, because trust stores and certificate handling can differ.
- With routing, inspect the actual endpoints returned by the driver, not just the seed.
- Never place secrets or passwords in command arguments or share screenshots containing sensitive details.

### 9.3. Common error table

| Symptom | Common root cause category | Resolution |
| --- | --- | --- |
| `PKIX path building failed` / untrusted certificate | Missing CA, missing intermediate, wrong trust store | Add approved chain/trust anchor; do not enable trust-all |
| `No subject alternative names matching` / hostname mismatch | URI or advertised address differs from SAN | Fix DNS/SAN/certificate or endpoint |
| `certificate has expired` / not yet valid | Expired certificate or clock skew | Renew certificate, check clocks, and roll out |
| TLS handshake failure | Protocol/cipher mismatch, TLS policy, or wrong server config | Compare settings on both sides, server logs, versions |
| `Connection refused` / timeout before handshake | Network, DNS, firewall, or server not listening | Check host/port and network policies |
| `Unable to retrieve routing information` | Advertised endpoint unreachable or member TLS error | Check routing table, DNS, and each server's certificate |
| Neo4j authentication failure | Wrong or expired username/password/token | Check secret store and account; do **not** disable TLS |
| Query rejected with `Forbidden` | Account lacks database/graph privileges | Adjust role under least privilege |
| Fails only after cert rotation | Pool/instance not refreshed, missing new CA, or incomplete chain | Check rollout stages and trust overlap |
| Changing to `+ssc` succeeds | Indicates identity verification under `+s` is failing | Find root chain/hostname issue; never treat `+ssc` as a production fix |

**Never paste raw secrets** into support tickets. You may include the URI scheme, publishable hostnames, versions, error codes, and scrubbed public certificate metadata.

## 10. Renewing and rotating certificates without dropping connections

Certificates expire. Waiting until expiration day to replace them can cause widespread connection failures. An operational workflow:

1. **Inventory:** Bolt endpoints, cluster members, proxies, active certificates, CN/SANs, issuing CAs, expiration dates, and private key locations.
2. **Prepare:** issue new certificates with accurate SANs; validate key usage and key size/algorithms against policy.
3. **Pre-trust:** when rotating a **CA**, distribute the new CA to required clients during a controlled **overlap** period while the old CA remains valid.
4. **Rotate server side:** deploy the new certificate/key via rolling updates or reload mechanisms supported by your version/infrastructure.
5. **Verify:** connect with `+s` from the application network, checking seed and routed addresses, reads/writes, and health.
6. **Retire old CA:** only after confirming no client relies on the old trust anchor, per cutover window and revocation policy.
7. **Monitor:** handshake failures, new connections, retry rates, and expiration alerts.

### 10.1. Certificates change while existing connections keep running

**Already established** connections can stay alive in a connection pool while **new** TLS connections fail verification. Thus a system can look healthy right after rollout and fail later when opening new connections, restarting pods, or routing to another node.

Test **creating new connections** after rotation, not merely sending queries over pre-existing pooled sockets. Some setups require restarting/reloading the driver or server to pick up new certificates; never assume replacing a file takes effect instantly.

### 10.2. Compromised private keys require a different workflow than expiration

If a server's private key leaks, do not just renew with the same key. Generate a new key pair, issue a new certificate, revoke or block the old certificate per policy, investigate blast radius, and secure backups containing the key.

Changing `NEO4J_PASSWORD` on database accounts **does not resolve** a leaked TLS private key; they are two distinct secret layers.

## 11. Secure connections still depend on credentials and privileges

Even with flawless TLS, an application using an `admin` account for everything or concatenating user input into Cypher strings remains vulnerable.

### 11.1. Never embed credentials in the URI

Never write:

```text
neo4j+s://user:password@graph.prod.example.com:7687
```

This is an **anti-pattern example**, not real credentials. URIs containing credentials can leak into HTTP logs, proxy logs, stack traces, monitoring, and diagnostic tools. Pass `AuthTokens.basic(...)` or another supported auth method to the Neo4j Java Driver **separately from the URI**.

With Spring Boot, supply `spring.neo4j.authentication.*` from a secret manager, environment variables, or secure mounted files. Never commit passwords to `application-prod.yml` or CI configs.

### 11.2. Least privilege

- Provision separate accounts per service, environment, and database as appropriate.
- Grant read-only privileges for read-only functions; do not grant index, node, or relationship creation/deletion unless needed.
- Separately govern execution privileges for procedures, APOC, and GDS when used.
- Keep administrative and schema changes inside an authorized migration/administration workflow.
- In multi-tenant setups, bind tenant context from authenticated identity and enforce checks on both nodes and relationships in queries.

TLS protects traffic **on the wire**, yet an over-privileged account can still query data beyond business boundaries once connected.

## 12. Security testing and acceptance criteria

Do not stop at "the connection returns UP." Test both **valid paths and paths that must fail**:

| Test scenario | Expected result |
| --- | --- |
| `neo4j+s://` with CA-trusted cert and valid SAN | Connection succeeds with valid account/database |
| Server has valid cert but client does not trust CA | TLS **rejected** |
| Trusted CA but SAN mismatches hostname | TLS **rejected** |
| Expired or not-yet-valid certificate | TLS **rejected** |
| Wrong username/password secret | TLS may succeed, **authentication rejected** |
| Valid TLS and login, missing write privilege | **Write query rejected**; no security downgrade |
| Router cert valid, one advertised server has bad cert | Query to bad server **must fail**; fix endpoint |
| Proxy terminates TLS, upstream unencrypted | Must not be claimed as "end-to-end TLS to Neo4j" |
| Certificate rotation in cluster | New clients connect to every endpoint without `+ssc` |
| Secret variable omitted in production environment | App does not fall back to default credentials |

### 12.1. Testing with Spring Boot / Neo4j Java Driver

An integration test can run against a dedicated TLS-configured Neo4j test environment using test certificates issued by a test CA. Minimum checks:

1. Successful connection using `+s` URI and valid test trust anchor.
2. Replace hostname with a name **absent from SAN** using the same CA; driver must reject.
3. Remove the test CA from the trust store; driver must reject.
4. Test expired/invalid certificates if the test environment supports it.
5. Verify API responses and logs include only proper error codes and correlation IDs—never passwords, tokens, or private keys.

If local tests run non-TLS Neo4j via `bolt://localhost`, that **only validates local query logic**, not that the production pipeline satisfies TLS security. Maintain a dedicated test for real security configuration.

### 12.2. Observability and operational metrics

Track certificate expiration dates, handshake failure counts, connection/reconnection rates, timeouts, routing errors, pods still on old configs, and application read/write health. Distinguish:

- **Readiness:** whether the app can serve requests requiring Neo4j.
- **Liveness:** whether the process is alive; avoid restart loops during brief DB blips.
- **Security check:** whether connections use approved URI schemes and trust policies.

A `RETURN 1` health check does **not** verify all security and authorization policies. TLS tests must be explicitly designed to verify **rejection of untrusted endpoints**.

## 13. Exercises with suggested answers

### Exercise 1 — Choosing the right URI

App A runs locally against an isolated test Neo4j instance. App B connects to a production cluster via routing, with certificates from a trusted CA. App C connects to a direct Bolt endpoint with a valid cert.

**Hint:** A may use `bolt://localhost:7687` only if test policy allows; B typically uses `neo4j+s://...`; C may use `bolt+s://...`. Never infer from domain names alone—verify that the server actually supports routing and TLS.

### Exercise 2 — Hostname mismatch

URI is `neo4j+s://db.internal.example:7687`, while the certificate only has `DNS:db-prod.example`. The CA is valid and the certificate is unexpired. Why must it be rejected?

**Answer:** the identity declared in SAN does not match the **hostname requested by the application**. Trusting the CA is not enough; issue a certificate with the right SAN or use an allowed matching hostname, adjusting routing/DNS as needed.

### Exercise 3 — Diagnosing internal CA failures

In staging, `neo4j+ssc://` connects while `neo4j+s://` fails with `PKIX path building failed`. A colleague wants to keep `+ssc` in production.

**Answer:** do not allow it. The symptom shows the client cannot build a valid trust chain. Inspect the chain, intermediate CAs, trust store/driver trust strategy, and SANs first; deploy a properly managed internal CA so `+s` verifies endpoints cleanly.

### Exercise 4 — TLS-terminating proxy

An infrastructure diagram shows: client uses TLS to a proxy, and the proxy opens non-TLS Bolt to Neo4j. The system documentation claims "end-to-end encryption to the database." Is that accurate?

**Answer:** no. TLS reaches only the **proxy**; the proxy–database segment has no TLS in the described design. To claim end-to-end encryption, evaluate and protect the backend segment or use an appropriate TLS passthrough model.

### Exercise 5 — Rotating certificates in a cluster

A new CA has been deployed to servers, while some Java pods still trust only the old CA. Pods with open connection pools still return query results. Can the rollout be declared complete?

**Answer:** not yet. Test **new connections** to all routed servers, verify each client's trust anchor, maintain CA overlap time, and monitor handshake errors; only then remove the old CA.

### Exercise 6 — Distinguishing TLS, authentication, and authorization

An app connects via `neo4j+s://` and runs `RETURN 1` successfully, but `MERGE (p:Product {...})` is denied. Should you switch to `neo4j://` to avoid the error?

**Answer:** no. The issue is **write privileges**, not TLS. Keep TLS enabled, inspect the application account's database/role privileges, and grant only what is needed.

## 14. Operational checklist

- [ ] Neo4j URI is approved per environment, preferring `neo4j+s://` or `bolt+s://` in production.
- [ ] Endpoint genuinely supports TLS; server Bolt TLS policy matches requirements.
- [ ] Certificates contain SANs matching all DNS/IP addresses used by the driver, including routed advertised addresses.
- [ ] Chain reaches a trusted CA, certificates are unexpired, and algorithms/key lengths meet policy.
- [ ] Clients do not enable trust-all or switch to `+ssc` to hide production errors.
- [ ] TLS termination points are documented; if proxied, the segment to Neo4j is also protected as required.
- [ ] Server private keys are protected; public CAs/certificates are distributed securely.
- [ ] Neo4j passwords are kept out of URIs, repositories, and logs, sourced from a secret manager or secure mount.
- [ ] Application accounts follow least privilege; read/write/APOC/GDS privileges are explicitly controlled.
- [ ] Both **passing and rejected** connection tests exist: wrong CA, wrong hostname, expired cert, wrong secret.
- [ ] Certificate renewal and CA rotation procedures include trust overlap and new-connection verification.
- [ ] Java Driver / Spring Data Neo4j are configured consistently without accidental relaxed-trust pools/drivers.
- [ ] Health checks, logs, and TLS alerts never expose secrets; handshake/routing errors and expiration dates are monitored.

## Conclusion

Encrypting Bolt with TLS is essential for protecting queries and data when Neo4j communicates over a network, but **encryption without server verification is not enough**. A sustainable approach uses `+s` URIs with a managed CA, certificates whose SANs match hostnames, strict Bolt TLS policies, and verification of every endpoint across routing or proxies. Once the channel is verified, you must still protect credentials, enforce least privilege, parameterize Cypher, and monitor operations. Renewing certificates and testing connections that **must fail** are just as important as testing connections that succeed.

### References

- [Neo4j Java Driver Manual — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver Manual — Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Operations Manual — SSL framework](https://neo4j.com/docs/operations-manual/current/security/ssl-framework/)
- [Neo4j Operations Manual — Security](https://neo4j.com/docs/operations-manual/current/security/)
- [Spring Boot Reference — Neo4j](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.neo4j)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)

# Securing the Transport Channel in Java Core Logging

## Learning Objectives

This lesson belongs to the **Logging Security** group, focusing on **Securing the Transport Channel**. A log event may contain service names, URLs, error codes, trace IDs, internal paths, access data, or business information. Even when an application does not intentionally log secrets, exception messages and metadata in logs can still expose architecture, accounts, or sensitive data. Therefore, the path of logs from Java to the storage system must be protected as a valuable data stream.

After this lesson, you will be able to:

- List the **hops** in a logging pipeline and identify which hops are vulnerable to eavesdropping, spoofing, or tampering.
- Explain the roles of **TLS**, **mTLS**, hostname verification, CA/truststores, client certificates, access control, and encryption in transit.
- Distinguish between HTTPS/OTLP over TLS, syslog over TLS, plain TCP connections, and unencrypted UDP.
- Apply Java 17 JSSE/HttpClient following server-authentication principles; recognize dangerous configurations such as "trust all certificates" or disabling hostname verification.
- Design a fault-tolerant log stream with timeouts, retries, buffering, backpressure, and policies for when a secure channel cannot be established.
- Test from the JVM to the collector, verify certificate rotation/revocation, and confirm there is no covert path sending logs over an unapproved channel.

**Key takeaway:** Having TLS on one connection does **not** mean the entire log transport path is protected. You must identify every connection, which parties are authenticated, where keys are stored, and what happens when a secure connection fails.

## 1. Where Does the Log Transport Channel Sit?

A common architecture:

```text
        Java application (Logback / Log4j 2 / JUL)
                           |
                    [A] stdout / file
                           |
                 container runtime / host
                           |
                    log agent / shipper
                           |
                    [B] TLS / mTLS
                           |
                    log collector
                           |
                    [C] TLS / mTLS
                           |
                gateway / broker / backend
                           |
                    [D] internal link
                           |
                    storage / index / query
```

Not every application goes through stdout, files, and an agent. Some applications send directly over HTTP/gRPC/TCP to a collector; others write to Kafka or use a host-level forwarder. Each architecture has its own set of hops.

| Hop | How data moves | Security questions |
| --- | --- | --- |
| **A. JVM → stdout/file** | Written to a stream, pipe, or local filesystem | Who can read the file/pipe? Does the runtime/host isolate processes and restrict permissions? |
| **B. Agent → collector** | Over internal network/VPC/Internet | Is TLS enabled? Does the agent authenticate the right collector? Does the collector authenticate the agent? |
| **C. Collector → backend** | HTTP, gRPC, TCP/TLS, or broker | Is encryption and endpoint verification enforced on the next hop, or does it just trust the internal network? |
| **D. Internal/storage** | Other services and storage repositories | Is there a protected channel when crossing trust boundaries? Are there separate access controls and encryption at rest? |

If Java writes directly to `https://collector...`, the Java application is responsible for configuring the HTTP client/TLS. If Java only writes to stdout and an agent sends it over the network, **TLS at the agent** is the encryption layer for the hop leaving the host. It makes no sense to say "enable TLS in Logback" if Logback does not actually make any network connections.

The log path must be mapped out for **every log type**: application, audit, security, access, exception, debug, and separately routed streams. A log may travel through multiple routes (fan-out), and each route must be inspected.

## 2. Threats and Protection Goals

An insecure log channel can face:

1. **Eavesdropping:** a party capable of observing the network reads messages, trace IDs, or incident details.
2. **Endpoint spoofing:** the application or agent sends logs to a rogue server due to DNS, proxy, endpoint configuration, or broken certificate validation.
3. **In-transit tampering:** events or metadata are altered before reaching the collector.
4. **Log source spoofing:** an unauthorized party sends events impersonating a real service, polluting investigations or forging audit trails.
5. **Replay:** valid events are re-sent, skewing counts or creating the false impression that a transaction occurred twice.
6. **Connection disruption:** TLS handshake failures, expired certificates, network partitions, or overloaded collectors delay, drop, or block the application.

Properly configured TLS provides **encryption, integrity protection for bytes in transit within the session, and server authentication**; mTLS also authenticates the client's identity via a certificate when both sides are properly configured. However, TLS alone does not solve every risk:

- It does not stop the application from **writing secrets into logs in the first place**.
- It does not protect logs once decrypted at a proxy/collector or while sitting in files/indexes.
- It does not prove an event reached the backend **exactly once**, was stored durably, or was not altered after storage.
- It does not replace **authorization**: a client with a valid certificate does not necessarily have permission to write to every tenant/index.
- It does not prevent abuse from a compromised endpoint or a legitimate client whose key was leaked.

Therefore, channel protection encompasses **TLS/identity**, **access and route control**, **key security**, **error handling**, and **testing**.

## 3. TLS, HTTPS, and mTLS: Accurate Distinctions

### 3.1. TLS Protects a Connection

TLS (Transport Layer Security) uses key exchange, endpoint authentication, and authenticated encryption with integrity checks to protect a transmission stream. For a Java → collector connection:

```text
Java client                   collector server
    |                              |
    |--- ClientHello ------------->|
    |<-- ServerHello / cert / ... -|
    | validate chain + hostname    |
    |<-- / --> handshake messages -|
    |========= encrypted data =====|
```

This is a simplified diagram, **not the exact sequence of every TLS 1.2/1.3 handshake**. Server authentication requires at least two types of checks:

- **Certificate chain/trust:** does the server certificate chain back to a trusted trust anchor/CA, and does it match the intended purpose and validation constraints?
- **Endpoint identity/hostname verification:** does the server name the client **intends to connect to** match a name in the certificate (typically a DNS Subject Alternative Name – SAN)?

A certificate signed by a trusted CA but issued to a **different server** is not valid for the expected collector. Similarly, connecting to an IP address when the certificate only contains a DNS name can fail hostname verification; use a stable hostname and proper SAN rather than disabling name checks.

Modern TLS typically uses TLS 1.3 or TLS 1.2 depending on policy and compatibility between parties. TLS 1.0/1.1 are deprecated and should never be enabled just to "make the connection work." Actual cipher suites, security providers, and protocol versions depend on the JVM, OS, server, and policy; do not assume every JDK 17 environment negotiates the same cipher suite.

### 3.2. HTTPS Does Not Mean mTLS

- **HTTPS** = HTTP over TLS. The client normally **authenticates the server**. The service may separately authenticate the client using a token/API key, cookie, or another mechanism over the encrypted channel.
- **mTLS (mutual TLS)** = both sides authenticate with certificates during the handshake: the server presents a certificate for the client to verify, and the client presents a certificate for the server to verify. mTLS can be used with HTTP/gRPC or protocols designed to run over TLS.
- **A bearer token over HTTPS** protects the token in transit, but if the token is leaked externally or logged, TLS cannot save it. mTLS does not mean the API no longer needs access control.

A collector may require **both mTLS and application-layer authorization**. For example, only service A's client identity is allowed to write to tenant A and must not send audit events to tenant B. A certificate is proof of identity; authorization logic is a separate decision.

### 3.3. Where TLS Terminates Also Matters

For example:

```text
Java --TLS--> load balancer --plaintext--> collector
```

The Java → load balancer segment is protected by TLS, but the load balancer → collector segment is still plaintext. If the latter segment crosses a trust boundary, separate TLS/mTLS or a clearly evaluated isolation measure is required. Connections through a service mesh must also identify which sidecar initiates and terminates TLS, peer authentication policies, passthrough paths, and bypass routes.

**TLS is hop-by-hop protection.** For especially sensitive data that needs end-to-end confidentiality even from intermediate processors, application-layer payload encryption with separate key management may be needed; this complicates searching/parsing and is not the default requirement for all logs.

## 4. Choosing the Right Log Transport Protocol

Not all "TCP logging" is encrypted. You must distinguish specific cases:

| Protocol / Transport | Transport protection | What to verify |
| --- | --- | --- |
| **HTTPS POST** to an ingest API | TLS if `https://` is genuinely used and the client verifies certificate + hostname | CA/truststore, auth, redirects, timeouts, payload schema, and retries |
| **OTLP/HTTP over HTTPS** | TLS between exporter and endpoint | Endpoint, trust, token or mTLS, Content-Type/schema, response codes |
| **OTLP/gRPC over TLS** | TLS for the HTTP/2 gRPC channel | Channel credentials, server name, client identity, deadline |
| **Syslog TCP without TLS** | No TLS security just from using TCP | Avoid sending across untrusted network boundaries |
| **Syslog UDP** | No encryption or delivery guarantees by default | Unsuitable for sensitive data on untrusted networks |
| **Syslog over TLS** | Standardized profiles exist, e.g., RFC 5425 | Trust chain, peer identity, framing, and certificate policy |
| **Host stdout/file** | Not a TLS connection from the JVM | Host/container permissions, agent, where it goes over the network next |
| **Message broker** | Depends on client and broker configuration | TLS/mTLS, SASL/token if any, topic ACLs, replication, and storage |

With OpenTelemetry, distinguish **OTLP exporter configuration** from **OpenTelemetry Collector configuration**. If the Java app exports OTLP, configure the exporter according to the Java/instrumentation stack in use; if the app only logs via SLF4J and an agent reads stdout, OTLP/TLS is usually configured on the agent/collector, not at `logger.info`.

Beyond encryption, check *protocol correctness*: using `https://` does not automatically make an endpoint support OTLP. An HTTP server that only accepts OTLP protobuf/JSON in the specified format will not understand an arbitrary JSON log just because it hits `/v1/logs`. The protocol specification and receiving system are the source of truth for exact payloads and headers.

**Do not assume "the internal network is completely safe."** Internal networks still carry risks of misconfiguration, lateral movement, compromised hosts, packet capture, or cross-namespace/tenant access.

## 5. Truststores, Keystores, Certificates, and Secrets in Java

### 5.1. How Java JSSE Verifies the Server

Java 17 provides JSSE via `javax.net.ssl`. Key components to understand:

- **`SSLContext`:** provides TLS settings for sockets/HTTP clients, including key managers and trust managers.
- **`TrustManagerFactory`:** creates trust managers based on a truststore or corresponding trust source.
- **`KeyManagerFactory`:** creates key managers containing the client identity and private key (needed when mTLS is configured).
- **`KeyStore`:** structure for storing certificates/keys, commonly in PKCS12 format; truststore and keystore files serve different purposes.
- **`SSLParameters`:** allows configuring TLS parameters, including the endpoint identification algorithm in some client APIs.
- **`HttpClient`:** the JDK 17 HTTP client supports HTTPS/TLS. Under normal configuration, certificate chain and server identity checks must remain enabled; do not enable internal flags that disable hostname verification.

A **truststore** holds CAs/certificates allowed to be trusted for verifying the **server**; a **client keystore** in mTLS holds the client certificate and its corresponding private key. Importing the server certificate is not enough if the client still skips hostname verification; conversely, a matching server name is not enough if the chain is untrusted.

In some enterprise environments, the collector uses a private CA. You must add the **appropriate CA** to the client or agent truststore—do not dump every certificate into an uncontrolled shared truststore. When changing CAs or rotating certificates, ensure clients and servers have a trust transition window and that reload/restart mechanisms are tested.

### 5.2. Insecure Configuration Patterns to Avoid

Never treat the following as production solutions:

- An `X509TrustManager` with an empty `checkServerTrusted(...)` or one that accepts any certificate.
- A `HostnameVerifier` that always returns `true`, or disabling endpoint identification via an internal property.
- Switching an endpoint from `https://` to `http://` to bypass certificate errors.
- Enabling all legacy protocols/ciphers to get past a handshake error without assessing risk.
- Logging private keys, truststore passwords, bearer tokens, or sensitive certificate contents.
- Installing certificates or trust anchors from unverified sources as a quick fix.

If a handshake fails, investigate the real cause: SAN mismatch, missing intermediate in the chain, untrusted CA, expired certificate, skewed system clock, missing mTLS client certificate, incompatible key/cipher, or misrouted proxy.

### 5.3. Provisioning, Storage, and Rotation

Server and client certificates should have a clear governance lifecycle: issuance, distribution, expiration monitoring, pre-expiry alerts, rotation, revocation/quarantine on key compromise, and removal of unused identities. Private keys must be protected with appropriate filesystem permissions, a secret manager, or a platform identity provider; never bake them into Git repositories or Docker images in plaintext.

When passwords must be passed at runtime, avoid hard-coding them in code/logs and avoid putting secrets in command-line arguments if the OS or monitoring tools can expose process arguments. Some environments use secret volumes, file descriptors, service identities, or platform-managed secret injection; choose an approach aligned with organizational policy and verify file permissions.

**Rotation tests** must cover the window when both certificate sets are accepted, when the old certificate expires, when instances still hold old connection pools, and when the app/agent reconnects. Replacing a certificate file on disk **does not guarantee** that a running JVM or collector has reloaded the trust/key material; hot-reload behavior depends on the implementation.

## 6. Standalone Java 17: HTTPS-Only Policy and TLS Configuration

The following program uses only JDK 17+, requiring no server, third-party libraries, or network access. It does three things:

1. Checks whether an ingest endpoint uses **HTTPS**, has a hostname, and contains no `userinfo`, query, or fragment per **the example's policy**.
2. Builds an `HttpClient` with the JVM's default `SSLContext`, requiring the `HTTPS` endpoint identification algorithm, a connect timeout, and **no automatic redirects**.
3. Prints status to verify configuration decisions, but **sends no requests**. Because no handshake occurs, the example **does not prove** a real server has a valid certificate; that requires an integration test.

Disallowing query strings is a conservative choice to prevent accidentally embedding credentials in URLs. A real API might use valid query parameters; in that case, strictly allowlist parameters and never put tokens/secrets in the URL. Similarly, non-HTTP endpoints such as syslog over TLS need their own validator.

Create the file **`SecureLogTransportPolicyDemo.java`**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;

public class SecureLogTransportPolicyDemo {
    private static boolean allowed(String endpoint) {
        try {
            URI uri = URI.create(endpoint);
            return !uri.isOpaque()
                    && "https".equalsIgnoreCase(uri.getScheme())
                    && uri.getHost() != null
                    && !uri.getHost().isBlank()
                    && uri.getRawUserInfo() == null
                    && uri.getRawQuery() == null
                    && uri.getRawFragment() == null;
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private static void check(String label,
                              String url,
                              boolean expected) {
        boolean actual = allowed(url);
        if (actual != expected) {
            throw new IllegalStateException(label + " failed");
        }
        System.out.println(label + "=" + actual);
    }

    public static void main(String[] args) throws Exception {
        check("https_allowed",
                "https://collector.example.test/ingest", true);
        check("http_allowed",
                "http://collector.example.test/ingest", false);
        check("userinfo_allowed",
                "https://user:fake-pass@collector.example.test/ingest",
                false);
        check("query_allowed",
                "https://collector.example.test/ingest?token=fake",
                false);

        SSLParameters tls = new SSLParameters();
        tls.setEndpointIdentificationAlgorithm("HTTPS");

        HttpClient client = HttpClient.newBuilder()
                .sslContext(SSLContext.getDefault())
                .sslParameters(tls)
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .version(HttpClient.Version.HTTP_1_1)
                .build();

        System.out.println("hostname_policy="
                + tls.getEndpointIdentificationAlgorithm());
        System.out.println("redirect_policy="
                + client.followRedirects());
        System.out.println("requests_sent=0");
    }
}
```

Compile and run:

```bash
javac SecureLogTransportPolicyDemo.java
java SecureLogTransportPolicyDemo
```

**Exact stdout:**

```text
https_allowed=true
http_allowed=false
userinfo_allowed=false
query_allowed=false
hostname_policy=HTTPS
redirect_policy=NEVER
requests_sent=0
```

Important notes:

- `URI.create(...)` only parses the URI; it **does not connect** or verify certificates. The scheme/hostname check is a policy layer before creating a connection, **not a replacement for the TLS handshake**.
- `SSLContext.getDefault()` retrieves the default trust settings currently active for the JVM. In enterprise setups, an application's truststore may differ from the OS truststore; verify which trust source is used.
- `SSLParameters#setEndpointIdentificationAlgorithm("HTTPS")` expresses the endpoint identity verification requirement for the client configuration. JDK `HttpClient` performs HTTPS verification by default; never use any "disable hostname verification" flag to bypass errors.
- `HttpClient.Redirect.NEVER` prevents automatically redirecting log requests to another endpoint. If the system has valid redirects, verify the new endpoint against the same policy instead of following redirects blindly.
- `connectTimeout` limits **connection establishment time**, not total request duration or queue wait time. Real requests also need an appropriate request timeout/deadline.

The name `collector.example.test` and fake token in the negative test URLs are strictly for policy verification; they do not represent real endpoints, and the program does not attempt to authenticate or transmit data externally.

**Safety boundary of the example:** Using a valid HTTPS URL **does not prove** the collector is trustworthy; you still need a real handshake, certificate chain/hostname validation, authorization, per-hop policies, and failure testing. The code also cannot detect all proxies/redirects or dangerously altered JVM configurations; that belongs to deployment environment auditing.

## 7. Integrating a Custom Truststore and mTLS in Java

When the collector uses an internal CA, the Java application can build an `SSLContext` with an organization-issued truststore. Below is an **integration snippet**, not a standalone program: it requires a PKCS12 file and a password obtained securely at runtime, along with verified file read permissions.

```java
// Snippet in a configuration class: trustStorePath and
// trustStorePassword are provided from runtime secret/config.
KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(trustStorePath)) {
    trustStore.load(input, trustStorePassword);
}

TrustManagerFactory trustManagers = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
trustManagers.init(trustStore);

SSLContext context = SSLContext.getInstance("TLS");
context.init(null, trustManagers.getTrustManagers(), null);

HttpClient client = HttpClient.newBuilder()
        .sslContext(context)
        .followRedirects(HttpClient.Redirect.NEVER)
        .connectTimeout(Duration.ofSeconds(5))
        .build();
```

Imports needed when placing this snippet in a real Java class include `java.security.KeyStore`, `java.nio.file.Files`, `java.io.InputStream`, `javax.net.ssl.TrustManagerFactory`, `javax.net.ssl.SSLContext`, `java.net.http.HttpClient`, and `java.time.Duration`. When using `HttpClient`, keep hostname verification enabled; if using `SSLSocket` directly, configure endpoint identification appropriate for the protocol and test that it is actually enforced. Never create an "accept all" trust manager just to get the program to connect.

**Custom truststore note:** When you supply a custom truststore as shown above, the JVM does not automatically merge all default trust anchors into that truststore. If the application must connect to multiple types of endpoints, design the trust scope deliberately—do not add every CA indiscriminately. Never log the truststore path or password.

For **mTLS**, the client also needs a `KeyManagerFactory` initialized from a keystore containing the client certificate/private key. Conceptually:

```java
// Additional snippet; requires keyStore and keyPassword variables
// created/retrieved from a secret manager and deployment configuration.
KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
keyManagers.init(keyStore, keyPassword);

SSLContext mutualTlsContext = SSLContext.getInstance("TLS");
mutualTlsContext.init(
        keyManagers.getKeyManagers(),
        trustManagers.getTrustManagers(),
        null);
```

In this snippet, `keyStore` is a properly loaded `KeyStore` and `keyPassword` is a securely managed `char[]`; it is an **integration snippet**, not standalone compilable code. Having a client certificate **does not** guarantee the server requires mTLS, nor does it guarantee the client is authorized to write to a specific tenant. You must test the mTLS handshake and verify authorization on the collector.

### What Else Does a Real Network Connection Need?

For a real HTTP collector, beyond `SSLContext` and endpoint validation, you need:

- Send a body matching the **ingest protocol/schema** supported by the collector, such as OTLP/HTTP protobuf or JSON per the OTLP spec—never send an arbitrary JSON object.
- Enforce timeouts/deadlines and a bounded retry policy to avoid uncontrolled duplicate replays.
- Authenticate with tokens or certificates per policy; never log the `Authorization` header.
- Limit batch size, payload size, concurrent connections, and buffering during slow networks.
- Check response status codes and sink acknowledgement semantics; HTTP 2xx does not automatically mean the event is indexed/searchable or durable.
- Continue using TLS for collector → backend if that hop crosses a trust boundary requiring protection.

## 8. Configuration in Logging Frameworks and Agents

Where TLS is configured depends on where the network connection is made. You cannot apply a generic `tls=true` property to every logger.

### 8.1. When the Application Only Writes to Stdout/File

If Logback or Log4j 2 writes to local stdout, the connection to the collector is typically handled by Fluent Bit, Vector, OpenTelemetry Collector, Filebeat, Promtail, or whichever agent the organization uses. In that case:

1. The JVM must keep logs structured and avoid writing sensitive data.
2. Files/stdout/host are protected via access permissions and container policies.
3. The **agent** must use TLS/mTLS, an appropriate trust bundle, and auth for outbound traffic.
4. The collector must authenticate the source, authorize writes per tenant/service, and route to the right backend.
5. Check the collector → storage segment as well; do not treat agent → collector protection as completing the entire pipeline.

The agent names above are examples of technologies you may encounter; TLS capabilities, config fields, certificate reload behavior, and retry policies depend on the version. Read the official documentation of **the tool actually deployed** rather than copying YAML from a different agent.

### 8.2. When an Appender/Exporter Sends Directly Over the Network

For Logback `SocketAppender`, Log4j 2 `SocketAppender`, HTTP appenders, or OpenTelemetry exporters, inspect the specific transport:

- A plain TCP socket appender has **no** TLS unless its corresponding TLS mode is enabled.
- An "SSL" or "TLS" appender must have proper trust/hostname verification configured; merely creating a TLS socket is insufficient if identity checks are skipped.
- An HTTP exporter needs `https://` or corresponding TLS settings; a gRPC exporter needs channel TLS credentials and peer name validation.
- With async network appenders, TLS/collector errors can fill the queue; define whether to block, drop, spool, or fall back.
- When using custom client libraries, verify redirects, proxies, DNS/SNI, certificate validation, and credential loading.

**Never send critical logs directly to an arbitrary IP** just because it sits inside a VPC. Use proper DNS/identity; if connecting by IP is required, the certificate must include an IP SAN and a corresponding verification policy.

### 8.3. Example Per-Hop Policy

Suppose a system has Java → stdout → collector agent → gateway → index:

```text
JVM / stdout:           host/container access control
Agent -> gateway:       TLS 1.2+/TLS 1.3, trusted CA, hostname check
Gateway -> collector:   mTLS, identity-based authorization
Collector -> backend:   TLS + service account permissions
Index / storage:        encryption at rest + access control + retention
```

This is a **target design template**, not a description of default infrastructure. If the gateway terminates TLS and forwards plaintext to the collector, explicitly document that hop's trust boundary; never check off "all TLS" on a checklist just because the external port is 443.

## 9. Identity Authentication and Authorization for Log Sources

A collector receiving logs from multiple services/tenants needs more than encrypted connections. If every client can write to every namespace, a compromised client can spoof or pollute another party's logs.

You can combine:

- **mTLS client identity** tied to a specific service/workload, certificate subject/SAN, and authentication policies at the gateway.
- **Least-privilege tokens/API keys** transmitted over HTTPS and rotated periodically.
- **ACL/routing policies** enforcing that service A's identity can only write to index/tenant A; never trust a self-declared `tenant_id` field from the client for authorization decisions.
- **Per-identity rate limits/quotas** to mitigate log spam or DoS against the collector.
- **Network policies/firewalls** restricting who can connect to the collector and opening only necessary ports.
- **Auditing of configuration changes** to TLS, truststores, tokens, routes, collectors, and index permissions.

If both mTLS and tokens are used, establish clear rules for each layer's role and revocation procedures. For instance, revoking a client certificate while the client's token still works over another route may leave an unintended access path open.

**Do not rely solely on source IP to authenticate a service.** NAT, proxies, dynamic workloads, and container infrastructure can change or share IPs. Network segmentation is a supplementary control, not a substitute for certificate identity and authorization when risk requires them.

## 10. Timeouts, Retries, and Reliability When TLS/Collector Fails

Even a protected channel can be disrupted. A TLS handshake can fail due to expired certificates, untrusted CAs, hostname mismatches, invalid mTLS client identities, or protocol mismatches. When that happens, **never silently downgrade to plaintext** to "keep logs flowing."

Choose failure policies explicitly:

| Incident | Desired safe behavior | Impact to measure |
| --- | --- | --- |
| Untrusted server certificate | Reject connection; alert on config/identity | Log delivery failure, growing queue/backlog |
| Hostname does not match SAN | Reject connection; do not skip verification | Connection failure |
| Expired client mTLS certificate | Reject handshake; trigger rotation/runbook | Exporter retries and log pipeline lag |
| Collector timeout/network partition | Bounded retry/backoff; buffer within budget | Delivery latency, memory, drops, disk spool |
| Queue full | Block or drop per approved policy; isolate critical events | Impact on request p99 or dropped log count |
| 4xx payload/authorization error | Treat as config/payload error; do not retry indefinitely | Rejected event count and root cause |
| Transient 5xx/429 error | Retry with backoff/jitter per receiver guidance | Throughput, retry volume, duplicate risk |
| Agent/host crash | In-RAM buffer may be lost; disk spool (if any) must be durable and protected | Event counts, recovery, local data risk |

**Not all 4xx or 5xx codes share the same semantics.** For example, an expired token, malformed payload, rate limit, and transient server error require different policies. Rely on the API/collector documentation and available retry guidance; avoid retrying requests that are guaranteed to fail.

### 10.1. Backpressure Can Slow Down the Entire Application

If the producer logs faster than the sink can send over TLS, bounded queues fill up. Once full, the logging framework may block business threads, drop events, or fall back to synchronous writes. This creates a tradeoff between **request latency** and **log completeness**.

A test should measure simultaneously:

- `logger_call_latency` p50/p95/p99 and endpoint latency.
- `queue_depth`, `enqueue_block_time`, and high-water mark.
- `sent_events`, `failed_events`, `dropped_events`, `retried_events`.
- `tls_handshake_failures` by error type, without logging key/token contents.
- `collector_ingest_lag` and event-to-searchable latency.

You cannot conclude "TLS slows down the app" simply from enabling HTTPS. Handshake overhead, connection reuse, batch size, encoding, downstream throttling, and network RTT all contribute; measure each stage under representative workloads. Connection pooling and batching can reduce overhead, but you must bound connection counts and how long logs stay in RAM.

### 10.2. Retries Can Create Duplicate Logs

When a client sends an event and times out before receiving an acknowledgement, it is uncertain whether the server received it. Retrying can produce two records. If deduplication is needed, use an `event_id` or mechanism supported by the protocol/sink, but do not assume every collector provides "exactly once" delivery. A trace ID can span multiple log events; it is not sufficient as a per-event deduplication key.

For audit or legal events requiring integrity guarantees, design a durable message path/transactional outbox or a dedicated audit store as required. An in-memory async queue plus TLS is **not** equivalent to a zero-data-loss guarantee.

### 10.3. Disk Spools Also Need Protection

When an agent buffers logs to disk while waiting for network recovery, sensitive data **exists at rest**. Apply least-privilege filesystem permissions, capacity limits, retention, encryption at rest where appropriate, and cleanup after successful delivery. A solution that encrypts outbound TLS but leaves plaintext spools containing tokens on a shared machine still fails comprehensive security requirements.

## 11. End-to-End Testing of TLS/mTLS and the Transport Path

Test in staging or an equivalent controlled environment using synthetic logs with no real secrets. Define the expected policy clearly before testing.

### 11.1. Mandatory Test Matrix

| ID | Scenario | Expectation |
| --- | --- | --- |
| T1 | Collector has valid cert, trusted chain, and matching SAN | TLS connects successfully; test event reaches the allowed sink |
| T2 | Self-signed/untrusted CA | Client rejects; no automatic HTTP fallback |
| T3 | Trusted cert but SAN differs from hostname | Client rejects due to endpoint identity mismatch |
| T4 | Expired or not-yet-valid certificate | Connection fails per validation policy |
| T5 | mTLS server requires client cert, client has none | Handshake/auth fails; no logs sent |
| T6 | Valid client cert but unauthorized for this tenant | Rejected by authorization even though TLS succeeds |
| T7 | Collector unreachable/timeouts | Retry/backoff/buffer/drop follows policy; app does not hang indefinitely beyond design |
| T8 | TLS termination at gateway | Verify gateway → collector hop also has protection where needed |
| T9 | Endpoint manually changed to HTTP | Config validation or policy blocks it; sensitive logs are not sent |
| T10 | Server CA/client certificate rotation | Transition period works; reconnect succeeds; trust-all is never enabled |
| T11 | Stdout/file → agent → backend path | Event appears at the right destination and does not leak into out-of-scope indexes |
| T12 | Log burst / full queue | Block/drop metrics are recorded; never reported as full success |

**How to measure accurately:** Generate a unique `test_event_id` for a test log and record its emission timestamp. Query the sink/collector/backend by that ID and by environment/tenant, verifying both expected content and **absence** in wrong sinks. If the pipeline is eventual-consistent, poll with a deadline before concluding rather than demanding instantaneous appearance.

### 11.2. Useful Tools and Signals

- `keytool -list -v -keystore ...` can inspect certificates/truststores; run with least privilege and never paste passwords into shared logs. `keytool` is bundled with the JDK, with syntax/output format varying by version.
- `openssl s_client -connect host:port -servername host -verify_return_error` is useful when OpenSSL is available to inspect handshakes, SNI, and chains. A successful connection with this tool **does not** prove the Java client's trust config matches OpenSSL, nor does it prove collector authorization.
- `curl` with an HTTPS URL and proper CA bundle can test authorized HTTP endpoints, but never expose bearer tokens in shell logs/verbose output and never use `-k`/`--insecure` to "make the test pass."
- JSSE/JVM debug logging can be enabled in controlled environments to inspect handshake/cert path failures, but TLS debug logs are verbose and may contain sensitive connection details. Use only under approved procedures and disable after investigation.
- JVM metrics, appender/agent status, collector receiver/exporter metrics, gateway logs, and index counters help pinpoint the failing hop rather than looking solely at application logs.

If the endpoint uses mTLS, the test client must have the proper identity and authorized certificate. Do not conclude "the server is down" because a test client without a certificate was rejected.

### 11.3. Checking Hostname and SNI

Many systems use virtual hosting, load balancers, or multiple certificates on one IP. **SNI (Server Name Indication)** lets the client specify the hostname during the TLS handshake so the server selects the right config/certificate; **hostname verification** is the client step verifying the server certificate matches the expected name. The two concepts are related but do not replace each other.

When connecting to an IP instead of a hostname, SNI and SAN may be incompatible with the certificate depending on the stack. The right fix is usually configuring the proper hostname, DNS, and SAN—not disabling hostname verification. When going through a proxy/load balancer, verify exactly which name the TLS client validates on each segment.

## 12. Symptom-Based Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `PKIX path building failed` | Missing CA/intermediate, or different truststore than expected | Verify the chain, loaded truststore, and correct CA |
| `No subject alternative DNS name matching` | Endpoint hostname does not match SAN | Fix DNS/SAN/certificate; do not disable hostname verification |
| TLS handshake fails after rotation | New cert not yet trusted, stale key/client cert, process not reloaded | Check rollout window, reload/restart, and expiry |
| Client reaches HTTP but not HTTPS | Wrong listener/port/certificate/proxy or protocol | Verify the right TLS endpoint; do not downgrade by default |
| Handshake succeeds but HTTP 401/403 | Token/ACL/tenant permission or client identity lacks authorization | Check auth and authorization; TLS does not replace ACLs |
| Logs reach gateway but not collector | Next hop blocked, TLS termination/routing misconfigured | Trace by event ID and gateway/collector metrics |
| App slows down when collector disconnects | Async queue full or synchronous network appender blocking | Measure caller latency, queue policy, retry/buffering |
| Logs in local file but missing in backend | Agent/network/ingest/index error or lag | Inspect each hop and eventual consistency |
| Duplicate events after retry | Timeout with unknown server receipt | Track event IDs, deduplicate per sink capabilities |
| Valid client cert writing to wrong tenant | Missing/broken authorization by client identity | Enforce collector-side policy, run negative tests |
| Frequent handshakes, high CPU | No connection reuse, reconnecting per log, or collector resets | Use batching/connection pooling and re-measure |
| Service cannot connect through proxy | Proxy/TLS inspection uses different trust policy, wrong SNI | Clarify trust boundary, check certificate and network path |
| Disk spool growing large | Prolonged collector outage, retries not draining | Alert on queue/spool, cap size, and execute recovery plan |
| TLS enabled but audit finds plaintext | Fallback/bypass path or unencrypted hop after termination | Redraw topology, enforce policy, and run negative tests |

**Never resolve a TLS incident in production with trust-all or temporary `http://`.** If a certificate expires, restore the certificate/trust properly, monitor the backlog, and confirm no logs leaked onto another route.

## 13. Protecting Data Inside Logs Alongside Channel Security

TLS prevents many threats in transit, but messages still need governance after decryption:

1. **Do not log secrets:** passwords, API keys, bearer tokens, private keys, session cookies, or full request/response bodies containing sensitive data. Check exception messages and HTTP interceptors as well.
2. **Structured logging and masking:** use encoders with proper escaping to reduce log injection; strip/redact personal data per policy before sending.
3. **Separate logs by sensitivity:** audit/security logs may need different sinks, retention, and access controls than debug logs. Enforce routing on the collector/index too.
4. **Backend RBAC/ACL:** who can read or export logs? An agent's TLS client identity does not automatically restrict dashboard user permissions.
5. **Retention and deletion:** stored data must be governed by separate at-rest, lifecycle, and access-audit policies.
6. **Do not leak diagnostics:** handshake error messages should suffice to diagnose the error category without printing tokens, private keys, or raw log payloads.

Whenever enabling HTTP/TLS debug in staging, use safe test data and a limited time window. Having a TLS transport channel does not make pushing secrets to the collector acceptable.

## 14. Production Deployment Checklist

Before approving a log transport channel, answer:

- [ ] Is the full log path mapped from Java, stdout/file/agent, collector to backend for each event type?
- [ ] Does every hop crossing a trust boundary have TLS/mTLS or an evaluated protection measure?
- [ ] Does the client verify both **certificate chain and hostname/SAN**, without trust-all or disabled verification?
- [ ] Are client identity, token/certificate, authorization, and per-tenant/service write permissions clearly defined?
- [ ] Are truststores/keystores and private keys distributed via a proper secrets manager, never committed to repositories?
- [ ] Is there monitoring for expiry, rotation, revocation, and unreloaded certificates?
- [ ] Does the collector/API have timeouts/deadlines, retry/backoff, bounded buffering, and payload limits?
- [ ] When a TLS handshake fails, does the system **refuse to downgrade** to plaintext or route to an unapproved sink?
- [ ] Are policy filtering, queue overflow, sink write failures, and ingest lag clearly distinguished?
- [ ] Are there negative tests for wrong CA/SAN certificates, missing mTLS client identity, wrong tenant, and unavailable collector?
- [ ] Is there an end-to-end event ID test confirming logs reach the right index and do not appear in unauthorized destinations?
- [ ] Have spool/temporary files, retention, access control, and encryption at rest been verified against requirements?
- [ ] Is there a rollback plan and runbook if certificate rotation or collector outage causes log loss or app slowdowns?

**Completion criteria:** You can explain which hops TLS protects, understand certificate and endpoint identity verification in Java, distinguish TLS/mTLS/auth, build a positive and negative test plan for the log path, and prove there is no fallback to plaintext when the secure channel fails.

## 15. Self-Check Questions

1. Java already uses `https://collector.example`; why do you still need to inspect the collector → backend path?
2. Would a certificate with a valid CA whose SAN does not include the collector's name be accepted? Why?
3. When using mTLS, does the collector automatically know which tenant is allowed to write from the client certificate?
4. Why might `SSLContext.getDefault()` use a different set of CAs than the OpenSSL tool on the machine?
5. A TLS channel breaks after a server certificate rotation: what should you investigate instead of using trust-all?
6. How does TLS configuration differ between sending logs directly with an HTTP client versus writing logs to stdout for an agent to ship?
7. Why can retrying after a timeout create duplicate log records even though the TLS connection is secure?
8. If the queue fills up when the collector goes down, what do you choose to balance request latency and log loss?
9. A client certificate is valid, yet writing to the audit index is denied: is the issue in TLS or authorization?
10. Why can a test with `requests_sent=0` never prove that a real server's certificate is valid?

## References

- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446) — TLS protocol version 1.3.
- [RFC 8996 — Deprecating TLS 1.0 and TLS 1.1](https://www.rfc-editor.org/rfc/rfc8996) — deprecating legacy TLS versions.
- [RFC 5425 — Transport Layer Security (TLS) Transport Mapping for Syslog](https://www.rfc-editor.org/rfc/rfc5425) — syslog over TLS.
- [Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html) — JSSE TLS configuration.
- [Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html) — TLS parameters and endpoint identification.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html) — HTTPS client, timeouts, and redirects.
- [Java SE 17 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html) — trust management.
- [OpenTelemetry Protocol (OTLP)](https://opentelemetry.io/docs/specs/otlp/) — telemetry transport and protocol requirements.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html) — TLS implementation recommendations.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — protecting logging content and processes.

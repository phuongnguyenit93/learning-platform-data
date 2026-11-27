# Securing Connections with TLS and Certificate Verification

Spring Data Redis applications frequently send keys, values, authentication passwords, and Redis commands over network connections. If unencrypted TCP is used, these bytes can be observed or altered by any actor controlling the network path. **TLS (Transport Layer Security)** protects data in transit and helps the client verify that it is communicating with the Redis Server of the expected identity.

Enabling TLS is only the first step. A secure connection simultaneously requires **transport encryption, certificate trust-chain verification, hostname verification, and appropriate authentication configuration**. Skipping certificate verification can leave the connection encrypted while the client has no certainty which server it is actually talking to.

This lesson covers how TLS works in the Redis connection lifecycle, how to configure it with Spring Boot and Spring Data Redis, the role of CAs/truststores, mutual TLS, verification steps, and troubleshooting across standalone, Sentinel, or Cluster environments.

## 1. Why Does Redis Need TLS?

Redis uses the RESP protocol over network connections. In typical deployments, connections can be plain TCP or TLS-protected TCP. With plain TCP, all RESP commands and payloads are transmitted without encryption from Redis itself.

Consider a command:

```redis
SET session:1001 abcdef
```

If a client uses a non-TLS TCP connection, the key and value contents can appear as readable bytes on the network. Furthermore, the `AUTH` command or ACL credentials do not by themselves create an encrypted channel.

TLS adds three important properties:

| Property | Meaning for Redis Connections |
|---|---|
| **Confidentiality** | Third parties on the network cannot read commands and responses when TLS is properly deployed. |
| **Integrity** | Data in transit is protected from unauthorized modification without detection. |
| **Server authentication** | The client can verify the certificate and hostname to reduce the risk of connecting to a rogue server. |

TLS **does not replace Redis ACLs**, access controls, firewalls, private networks, secret storage policies, data authorization, or key lifecycle management. A valid TLS connection can still be rejected if the Redis user lacks permission to run `GET` or `SET`.

### 1.1. Which Layers Do TCP, TLS, and Redis Occupy?

```text
Java application: RedisTemplate / StringRedisTemplate
             ↓
Spring Data Redis + Lettuce/Jedis
             ↓
Redis Serialization Protocol (RESP)
             ↓
TLS: handshake, certificate validation, encrypted records
             ↓
TCP / network
             ↓
Redis Server (TLS listener)
```

TLS establishes a protected channel before the application sends Redis commands in the usual way. Once the connection is established, RESP remains the request–response format carried inside the TLS channel; **TLS does not turn Redis into HTTP or HTTPS**.

Redis Open Source has supported TLS since **Redis 6.0**, provided the running Redis distribution was compiled/packaged with TLS support and TLS is enabled in configuration. A managed Redis service may expose a TLS endpoint by default or require TLS, depending on the provider.

## 2. Distinguishing Encryption, Certificate Verification, and mTLS

Three concepts are often conflated during configuration.

### 2.1. Encryption Without Identity Verification Is Not Enough

During the TLS handshake, the server presents an X.509 certificate along with handshake parameters. The client must decide whether to trust that server.

A configuration that skips verification can produce an encrypted stream, but **does not guarantee the endpoint is the intended server**. An intermediary could present another certificate to impersonate the server if the client accepts every certificate.

A properly protected connection must check at least:

1. **Trust chain:** the server certificate chains to a CA or trust anchor that the client trusts.
2. **Validity period:** the certificate is currently valid according to the system clock.
3. **Endpoint identity:** the hostname/IP the client connects to matches a certified name, normally in the **Subject Alternative Name (SAN)** field.
4. **Key usage and TLS policy:** the certificate chain, algorithms, and protocol parameters satisfy runtime policy.

If a client calls `redis.internal.example`, a certificate containing `DNS:redis.internal.example` is the typical case. A certificate issued only for `redis-public.example` is insufficient for that endpoint, even if both hostnames currently resolve to the same IP.

### 2.2. One-Way TLS and Mutual TLS (mTLS)

| Mechanism | Server presents cert? | Client presents cert? | Who verifies? |
|---|---|---|---|
| **Server-authenticated TLS** | Yes | Optional | Client verifies the Redis Server's certificate and identity. |
| **Mutual TLS (mTLS)** | Yes | Yes | Client verifies the server; server simultaneously verifies the client certificate. |
| **Redis ACL over TLS** | Yes | Not necessarily | Redis checks username/password/permissions after connection; not equivalent to mTLS. |

Connection-level relationship:

```mermaid
sequenceDiagram
    participant App as Spring Data Redis / Driver
    participant Redis as Redis TLS Listener
    App->>Redis: TCP connect
    App->>Redis: TLS ClientHello (may carry SNI)
    Redis-->>App: TLS ServerHello + server certificate
    Note over App: Verify CA, validity, SAN, TLS policy
    opt Server requires mTLS
        Redis-->>App: Client certificate request
        App->>Redis: Client certificate + proof of private key
        Note over Redis: Verify client cert chain and trust
    end
    Note over App,Redis: Handshake completes, TLS channel established
    App->>Redis: Redis commands (RESP inside TLS)
    Redis-->>App: Redis responses (RESP inside TLS)
```

When Redis Open Source is configured with TLS enabled, it **requires client certificates by default**, unless `tls-auth-clients no` is set. Consequently, an application configured with only a truststore sometimes still hits a handshake error: the server is demanding **mTLS**, not just server authentication.

## 3. Types of Certificates and Keystores to Know

### 3.1. CA, Certificate Chain, and SAN

- **CA certificate:** the certificate of the signing authority that the client chooses to trust. It can be a public CA, an internal CA, or a test CA.
- **Server certificate:** the certificate asserting the identity of the Redis Server or a TLS proxy in front of Redis. It is signed by a CA or belongs to a verifiable chain.
- **Intermediate CA:** an intermediate certificate linking the server certificate to the root CA.
- **SAN (Subject Alternative Name):** the field listing DNS names or IP addresses permitted to identify the endpoint.
- **Private key:** the secret key corresponding to a certificate. The server key must be kept secret by the server/proxy; the client key must be kept secret by the client when using mTLS.

The **CA** certificate can be distributed to applications to place in their truststore. You do not need and should not copy the **CA's private key** to applications merely to verify the server.

### 3.2. Are Truststores and Keystores Different?

In Java:

| Component | What does it contain? | Purpose |
|---|---|---|
| **Truststore** | Accepted CA certificates or trust anchors | Client verifies server certificates; a server may use its own truststore to verify clients in mTLS. |
| **Keystore** | Identity certificate and corresponding private key, optionally with certificate chain | Client presents its own certificate when server requires mTLS; or server presents the server certificate. |

A client needing only **one-way TLS** typically configures a truststore when an internal CA is not in the JDK's default truststore. A client **does not need a keystore containing a private key** if the Redis Server does not require a client certificate.

Java supports keystore formats such as **PKCS#12 (`.p12`, `.pfx`)** and **JKS**. Spring Boot also provides **SSL bundles** supporting PEM (`.crt`/`.pem` and `.key`), avoiding having to convert every certificate into a Java keystore.

### 3.3. Difference Between a “Valid Certificate” and the “Right Hostname”

Suppose the internal CA is already trusted by the application, yet the server presents a certificate whose only SAN is `DNS:cache-a.internal`. If Spring connects to `cache-b.internal`, CA chain verification can succeed while **hostname verification must fail**.

Do not solve this error by disabling hostname verification. Instead, use the hostname matching the certificate, or reissue a certificate whose SAN matches the actual endpoint.

**Note on IP addresses:** if connecting by IP address `10.0.0.15`, the certificate normally needs a SAN of type **IP:10.0.0.15**. A SAN `DNS:10.0.0.15` is not treated as equivalent to an IP SAN in every TLS client.

## 4. Configuring Redis Server to Accept TLS

On the Redis Server or Redis TLS proxy, administrators must expose a TLS-enabled endpoint. Typical Redis Open Source directives:

```conf
# Disable unencrypted Redis TCP
port 0

# Open TLS port
tls-port 6380

# Server identity and trusted CA
tls-cert-file /etc/redis/tls/server.crt
tls-key-file /etc/redis/tls/server.key
tls-ca-cert-file /etc/redis/tls/ca.crt

# Authenticate server only, do not require client certificates
tls-auth-clients no
```

The paths are examples only. Certificate and private key files must exist on the Redis machine/container, be readable by the Redis process, and be protected with appropriate file permissions.

The configuration above is **one-way TLS**. If you want Redis to enforce client certificates, use:

```conf
tls-auth-clients yes
```

In that mode, the server-side CA verifies client certificates, while the client still has to trust the CA that signed the server certificate. These two verifications are independent.

Some deployments expose multiple listeners, such as plain TCP on one port and TLS on another. Avoid pointing a Spring client at the plaintext port when transport protection is required; if policy permits TLS only, disable the plaintext listener and restrict network access.

### 4.1. TLS for Replication, Cluster, and Sentinel

TLS between an application and the Redis Server **does not automatically mean** all internal Redis traffic is encrypted:

- **Replication:** Redis has `tls-replication yes` to use TLS on replica replication connections.
- **Cluster:** `tls-cluster yes` applies TLS to the cluster bus and inter-node communication when configured appropriately.
- **Sentinel:** how Sentinel connects, communicates internally, or advertises endpoints depends on Sentinel's TLS configuration and version/platform; verify each connection type.

Applications using Redis Cluster can be redirected to multiple nodes. Every node or TLS proxy connected to must have an appropriate certificate and hostname, not just the first seed node.

## 5. Enabling TLS in Spring Boot with Spring Data Redis

### 5.1. Required Dependencies

In a typical Spring Boot application, declare the starter and let Boot manage Spring Data Redis and Lettuce versions:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Spring Boot typically uses **Lettuce** by default. Most TLS settings can be configured via `application.yml` without creating a `LettuceConnectionFactory` manually.

### 5.2. Using a Public CA Already Trusted by the JDK

If the server has a valid certificate signed by a CA present in Java's default truststore, you can configure:

```yaml
spring:
  data:
    redis:
      host: redis.example.com
      port: 6380
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      timeout: 3s
```

Here:

- `host` must be a DNS name confirmed by the TLS certificate.
- `port` must be the actual **TLS port** of Redis or the Redis proxy service.
- `ssl.enabled: true` enables TLS communication.
- Username/password are Redis ACL credentials, not private keys or truststores.
- `timeout` is the client-side operation time limit according to Boot's property semantics; **it is not a fix for certificate errors**.

**Enabling TLS does not mean skipping verification.** Lettuce normally enables peer verification when SSL is used, and can rely on the JDK's default trust anchors if no custom CA is configured. Do not call APIs like `disablePeerVerification()` to “quick-fix” connection errors.

### 5.3. The `rediss://` Syntax

Redis URIs commonly use:

- `redis://` for plain Redis connections.
- `rediss://` for Redis connections over TLS.

Example:

```yaml
spring:
  data:
    redis:
      url: ${REDIS_URL}
```

The environment value might look like:

```text
rediss://user:password@redis.example.com:6380/0
```

When using a URL, check the precedence rules of the running Spring Boot version; the URI typically overrides certain host/port/credentials/database fields. To avoid conflicts, choose one clear way of declaring the endpoint.

A URI containing a password is a **secret**: avoid committing it to Git, logs, issues, or shared command lines. Prefer a secret manager and injection via protected environment variables/volumes.

### 5.4. Configuring an Internal CA via a PEM Spring Boot SSL Bundle

An internal endpoint may be issued by an organization's CA that is not in the Java default truststore. In that case, configure an **SSL bundle** to define custom trust material for Redis.

Example `application.yml` using a CA file mounted at a path from an environment variable:

```yaml
spring:
  ssl:
    bundle:
      pem:
        redis-client:
          truststore:
            certificate: "file:${REDIS_CA_CERT_PATH}"

  data:
    redis:
      host: redis.internal.example
      port: 6380
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
        bundle: redis-client
```

Assuming the environment variable:

```text
REDIS_CA_CERT_PATH=/etc/app/redis-tls/ca.crt
```

Spring Boot loads the CA certificate via `file:/etc/app/redis-tls/ca.crt`, and the Redis connection factory uses the `redis-client` bundle.

Important points:

1. `spring.ssl.bundle.pem.redis-client.truststore.certificate` is the **trusted certificate for verifying the server**, not a client private key.
2. `spring.data.redis.ssl.bundle: redis-client` binds the bundle to the Redis connection.
3. The bundle name must match in both places.
4. The Redis endpoint still needs a valid hostname in its SAN and a proper certificate chain.
5. The CA file must exist, be readable, and be in a PEM format supported by Boot.

Spring Boot supports SSL bundle management in modern releases, including Boot 3.3. For applications on older Boot versions, verify property support in **that exact version's documentation** before copying.

If the CA involves a root and intermediate chain, package the trust material according to SSL bundle guidelines; depending on the case, the server must also send the full intermediate chain during the TLS handshake.

### 5.5. PKCS#12/JKS SSL Bundle

If your organization already provides a Java truststore, you can use:

```yaml
spring:
  ssl:
    bundle:
      jks:
        redis-client:
          truststore:
            location: "file:${REDIS_TRUSTSTORE_PATH}"
            password: ${REDIS_TRUSTSTORE_PASSWORD}
            type: PKCS12

  data:
    redis:
      host: redis.internal.example
      port: 6380
      ssl:
        enabled: true
        bundle: redis-client
```

Example creating a PKCS#12 truststore from a CA (run on a machine with `keytool`):

```bash
keytool -importcert \
  -alias redis-internal-ca \
  -file ca.crt \
  -keystore redis-truststore.p12 \
  -storetype PKCS12
```

`keytool` will prompt for a keystore password and certificate confirmation. Verify that **the imported CA is actually the CA that issued the intended server certificate**; do not blindly import an unknown certificate just to make a handshake error go away.

Per-application SSL bundles avoid modifying the JVM-wide default truststore, which could affect other TLS connections.

### 5.6. Traditional Java Truststore Configuration

Another option is supplying JVM system properties:

```text
-Djavax.net.ssl.trustStore=/etc/app/redis-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=***secret***
```

This illustrates the flags—**do not run it literally with asterisks**. Pass the password value from a secret management mechanism; note that JVM arguments may appear in process listings or observability tools depending on the OS.

The default JVM truststore has a broader scope than a dedicated bundle. With Spring Boot supporting SSL bundles, prefer binding a bundle specifically for Redis whenever possible.

## 6. When the Redis Server Requires Mutual TLS (mTLS)

### 6.1. What Else Does the Client Need?

If Redis requires a client certificate, Spring must have:

- **Trust material:** the CA to verify the **server certificate**.
- **Client certificate:** a client certificate signed by a CA trusted by the Redis Server.
- **Client private key:** the key matching the client certificate.
- **Password or mechanism to read the private key**, if the key is encrypted and supported by the runtime in that format.

Example PEM bundle:

```yaml
spring:
  ssl:
    bundle:
      pem:
        redis-mtls:
          truststore:
            certificate: "file:${REDIS_CA_CERT_PATH}"
          keystore:
            certificate: "file:${REDIS_CLIENT_CERT_PATH}"
            private-key: "file:${REDIS_CLIENT_KEY_PATH}"

  data:
    redis:
      host: redis.internal.example
      port: 6380
      ssl:
        enabled: true
        bundle: redis-mtls
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
```

Explanation:

- `truststore.certificate` serves to **verify the Redis Server certificate**.
- `keystore.certificate` and `keystore.private-key` allow **the application to present its certificate** when Redis requests it.
- Username/password are only required if Redis ACLs require them; mTLS and ACLs serve different purposes and can be used simultaneously.

The client certificate needs the proper **Extended Key Usage (client authentication)** if required by server policy. Never reuse the Redis Server's private key for the application.

### 6.2. How Does the Redis Server Verify the Client?

When `tls-auth-clients yes` is set, Redis can request a client certificate during the TLS handshake and verify it against its configured CA. If the client lacks a certificate, has a mismatched key, or presents an untrusted certificate, the TLS handshake can fail **before any Redis command is sent**.

When troubleshooting, check each side:

| Side to check | What to confirm |
|---|---|
| Spring client | Trusts the right Redis Server CA; matching SAN/hostname; has client keypair if needed. |
| Redis Server | Trusts the CA signing client certificates; intentionally requires mTLS; valid certificate/key. |
| Application/ACL | Username/password and Redis command permissions still meet business needs. |

### 6.3. Certificate Lifecycle

Server certificates or client certificates eventually expire. The system needs:

1. A reliable CA/certificate issuing source.
2. A process to issue and rotate certificates before expiration.
3. A secure mechanism to distribute certificates and private keys.
4. A way to update truststores/bundles and **recreate or refresh connections** when TLS material changes.
5. Monitoring for handshake failures and expiration dates.

Do not assume every client, every Spring Boot version, or every pool automatically reloads certificate files right after files change on disk. SSL bundle reloading and connection recreation depend on the version, driver, and configuration. When verified reload support is not in place, perform controlled restarts/rollouts and test fresh handshakes.

## 7. Hands-On: Testing CA and Hostname Verification Locally

This lab can be run on a machine with **OpenSSL, a TLS-capable redis-server, and redis-cli** installed. The commands below are for a lab environment; short-lived certificates and test keys must not be used in production.

### 7.1. Create a Test CA

```bash
mkdir -p certs

openssl genrsa -out certs/ca.key 4096
openssl req -x509 -new -sha256 -days 7 \
  -key certs/ca.key \
  -subj "/CN=Redis Lab Root CA" \
  -out certs/ca.crt
```

`ca.key` is the **CA private key**: keep it strictly in the lab and protect it. Client applications later need only `ca.crt` to trust the server certificate.

### 7.2. Issue a Server Certificate with SAN

```bash
openssl genrsa -out certs/server.key 2048

openssl req -new -sha256 \
  -key certs/server.key \
  -subj "/CN=localhost" \
  -out certs/server.csr
```

Create the file `certs/server.ext`:

```ini
subjectAltName=DNS:localhost,IP:127.0.0.1
extendedKeyUsage=serverAuth
```

Sign the CSR using the CA just created:

```bash
openssl x509 -req -sha256 -days 7 \
  -in certs/server.csr \
  -CA certs/ca.crt \
  -CAkey certs/ca.key \
  -CAcreateserial \
  -out certs/server.crt \
  -extfile certs/server.ext
```

The SAN in the example supports connecting via `localhost` or `127.0.0.1`. In production, the SAN must match the **actual DNS endpoint** of Redis or the TLS proxy.

### 7.3. Run TLS-Only Redis

Inside the lab directory containing `certs/`, start a Redis process serving on port 6380:

```bash
redis-server \
  --port 0 \
  --tls-port 6380 \
  --tls-cert-file ./certs/server.crt \
  --tls-key-file ./certs/server.key \
  --tls-ca-cert-file ./certs/ca.crt \
  --tls-auth-clients no
```

If the server reports that TLS is not supported, use a Redis distribution built with TLS enabled or an appropriate TLS environment. Not all Redis binaries are compiled identically.

### 7.4. Test with redis-cli

From another terminal:

```bash
redis-cli -h localhost -p 6380 \
  --tls --cacert certs/ca.crt \
  PING
```

Expected output: `PONG`. If `--tls` is omitted, a plain TCP client sends RESP to the TLS port and cannot perform normal Redis operations. If the client does not trust the self-signed CA, the TLS handshake is expected to fail.

**A successful `PING` only proves one connection path and basic command work.** To explicitly test hostname identity verification, use a tool with hostname verification flags such as `openssl s_client` below.

### 7.5. Explicitly Verify the CA Chain and Hostname

```bash
openssl s_client \
  -connect localhost:6380 \
  -servername localhost \
  -CAfile certs/ca.crt \
  -verify_hostname localhost \
  -verify_return_error
```

If the certificate was generated properly and the server is using the matching certificate, verification should succeed; a common indicator is `Verify return code: 0 (ok)`.

You can inspect the SAN of the certificate file:

```bash
openssl x509 -in certs/server.crt -noout -text
```

Look for `X509v3 Subject Alternative Name` and confirm it contains `DNS:localhost` and `IP Address:127.0.0.1`.

Try connecting to the server while requesting verification of a different hostname:

```bash
openssl s_client \
  -connect localhost:6380 \
  -servername not-the-server.example \
  -CAfile certs/ca.crt \
  -verify_hostname not-the-server.example \
  -verify_return_error
```

Because that hostname is not in the SAN, identity verification is expected to fail. This demonstrates that “having the right CA” is not enough if the endpoint name is wrong.

### 7.6. Connect Spring Boot to the Lab

Create a Spring configuration using the lab CA:

```yaml
spring:
  ssl:
    bundle:
      pem:
        redis-lab:
          truststore:
            certificate: "file:${REDIS_LAB_CA_PATH}"

  data:
    redis:
      host: localhost
      port: 6380
      ssl:
        enabled: true
        bundle: redis-lab
```

Set the `REDIS_LAB_CA_PATH` environment variable to the absolute path of `certs/ca.crt`; the Spring process must have read access to that file. No client keystore is needed because the Redis lab sets `tls-auth-clients no`.

To verify from the application, you can use `StringRedisTemplate`:

```java
import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisTlsProbe {

    private final StringRedisTemplate redis;

    public RedisTlsProbe(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String roundTrip() {
        String key = "lab:tls:ping";

        redis.opsForValue().set(key, "secure", Duration.ofSeconds(30));
        return redis.opsForValue().get(key);
    }
}
```

If the TLS handshake, certificate check, and Redis operations succeed, `roundTrip()` reads back the string `"secure"`. This shows the TLS channel is established and basic commands work; **it is not an automatic proof of every aspect of Redis security or functionality**.

## 8. Certificate Verification Across Deployment Environments

### 8.1. Containers and Kubernetes

CA files should be supplied via volumes or controlled certificate distribution mechanisms. The application needs stable file paths, read permissions, and matching passwords/keys.

Conceptual mapping example:

```text
Platform-managed Secret / volume
  ├── ca.crt               → Redis client trust material
  ├── client.crt           → only when using mTLS
  └── client.key           → only when using mTLS
            ↓ mount (read-only)
Spring Boot application
            ↓ TLS handshake + server verification
Redis TLS endpoint / proxy
```

Do not copy private keys into Docker images or commit them to Git. In Kubernetes, control Secret read access and pod identities; with external secret managers, use organization-approved mount/injection methods.

### 8.2. Managed Redis and TLS Terminators

Cloud Redis services may use a TLS terminator or proxy. In such cases, the certificate seen by the application is the certificate of the **TLS endpoint**, not necessarily an individual certificate per backend Redis process.

You should:

- Connect to the exact hostname issued by the provider and confirmed in the SAN.
- Use the service's TLS port/protocol.
- Trust the CA specified by the provider; do not blindly trust all certificates.
- Distinguish Redis ACL credentials from mTLS client certificates if the service requires both.
- Check service limits regarding TLS versions, ciphers, client certificates, and failover.

### 8.3. Redis Cluster and Node Redirections

Redis Cluster informs clients about nodes and hash slots. The driver may open TLS connections to other nodes after receiving topology information or `MOVED`/`ASK` redirections.

If a certificate is only valid for the seed hostname while nodes advertise internal IPs without IP SANs, the initial connection may succeed and then commands routed to other nodes fail. Do not disable hostname verification to hide this problem. Fix node addressing/advertised hostnames or issue certificates suitable for **all endpoints that may be connected to**.

### 8.4. Sentinel and Failover

In a Sentinel setup, the application may need to connect to Sentinel to discover the primary and then connect to Redis data nodes. These endpoints can have different certificates, hostnames, passwords, and TLS policies. Ensure the driver, version, and configuration properly support TLS over Sentinel and over data nodes. A TLS configuration that is only right for the Redis endpoint but wrong for Sentinel can prevent failover from working.

## 9. TLS Connections and Pools: When Does the Handshake Occur?

In Spring Data Redis, `RedisConnectionFactory` coordinates acquiring Redis connections. With Lettuce, some operations may use a shared connection; other types of operations may use dedicated connections or connection pooling depending on configuration.

**The TLS handshake happens when a new TLS connection is established**, not on every `GET` command over an already-open connection. Therefore:

- Connection reuse can reduce handshake overhead.
- When many new connections are created simultaneously, handshake CPU and latency can spike.
- When certificates expire or change, old connections and new connections may behave differently depending on TLS session policies and the driver.
- Too short a connect timeout can cause TLS connection setup to fail easily over slow networks.
- A pool does not perform identity verification on your behalf; each **new connection** must be verified according to TLS policy.

Model:

```mermaid
sequenceDiagram
    participant App as Application
    participant Pool as ConnectionFactory / Driver
    participant Redis as Redis TLS Server
    App->>Pool: Request connection
    alt Usable TLS connection available
        Pool-->>App: Return established connection
    else Need to create new connection
        Pool->>Redis: TCP + TLS handshake
        Redis-->>Pool: Certificate / handshake
        Note over Pool: Verify trust chain and hostname
        Pool-->>App: Return valid TLS connection
    end
    App->>Redis: GET / SET over TLS channel
    Redis-->>App: Redis response over TLS
```

When rotating a CA or server certificate, follow a process ensuring new connections load the updated trust material. Do not rely on “every pool automatically refreshing certificates” without verifying it for your Boot/driver version and deployment setup.

## 10. Diagnosing Handshake and Certificate Errors

### 10.1. Classification Table

| Typical Symptom or Message | Possible Cause | Right Direction to Fix |
|---|---|---|
| `PKIX path building failed` / `unable to find valid certification path` | Client does not trust the CA signing the server cert, or server omitted intermediate chain | Check CA/truststore and certificate chain; do not disable verification. |
| `No subject alternative DNS name matching ...` / `No name matching ...` | Connected hostname is not in the SAN | Fix the DNS endpoint or issue a certificate with a matching SAN. |
| `certificate expired` / `not yet valid` | Certificate is outside its validity window or system clock is wrong | Verify system time, rotate/reissue certificate. |
| `certificate required` / `bad certificate` | Server requires mTLS, but client is missing/has wrong keypair or CA | Configure valid client certificate and private key; verify server-side CA. |
| `SSLHandshakeException` | General handshake error category | Inspect root cause (CA, hostname, TLS version, cipher, mTLS). |
| `wrong version number` / `NotSslRecordException` | Sending TLS to a plaintext port or vice versa | Cross-check endpoint, port, protocol, and proxy. |
| `Connection refused` / timeout | Wrong host/port, firewall, server down, or network error | Check reachability and listeners before investigating certificates. |
| `NOAUTH` / `NOPERM` | Redis ACL, occurring after connection succeeds | Check username/password/permissions; do not confuse with CA errors. |
| Fails only after Cluster redirection | Certificate/topology on another node does not match | Check SAN, DNS, routing, and TLS on every node. |

Exact exception names depend on the driver, Java runtime, and Redis deployment. A high-level message like `RedisConnectionFailureException` can wrap an underlying `SSLHandshakeException`; inspect the **cause chain** to locate the failing layer.

### 10.2. Logical Investigation Order

1. **Endpoint:** are hostname, port, and TLS mode right? Which TLS listener is Redis Server listening on?
2. **Network connectivity:** can TCP be opened from the exact machine/pod running Spring?
3. **Handshake:** test connecting with `redis-cli --tls --cacert` or an appropriate TLS tool.
4. **Trust chain:** which CA signed the certificate, does the client have that trust anchor, and did the server send the full intermediate chain?
5. **Hostname/SAN:** does the hostname used by the client appear in the certificate?
6. **mTLS:** does the server require a client certificate, does the client have the right certificate/private key, and does the server CA trust the client?
7. **Redis ACL:** after the handshake, does the user have permission to execute commands?
8. **Topology/failover:** are certificates across all involved nodes/proxies valid?

Never use “trust all”, disabling hostname verification, or turning off TLS as a long-term fix. Those changes can make errors disappear in a lab while defeating server authentication.

### 10.3. Diagnostic TLS Logging in Java

When deep investigation is needed in a controlled environment, you can enable JSSE debug logging:

```text
-Djavax.net.debug=ssl,handshake
```

Logs can contain details about certificates, endpoints, hostnames, and handshakes. Enable only when needed, restrict log access, and turn it off after diagnosing. Never print private keys, passwords, or secret-bearing environment variables to logs for “debugging convenience”.

For Redis-side TLS, consult Redis Server logs and TLS proxy logs if present; correlate timestamps of failed handshakes between server and client. A wrong CA on the client and a missing client certificate in mTLS can both surface under a connection exception wrapper, yet have different fixes.

## 11. Safe Verification by Scenario

### 11.1. One-Way TLS with an Internal CA

**Goal:** Spring trusts only the authorized CA and verifies hostnames.

**Steps:**

1. Obtain the CA certificate from a trusted source.
2. Confirm the server certificate has a SAN for the real endpoint and is not expired.
3. Mount the CA into the application and configure a PEM/JKS SSL bundle.
4. Enable `spring.data.redis.ssl.enabled` and select the SSL bundle.
5. Run a minimal read/write operation via `StringRedisTemplate`.
6. Use a separate inspection tool to verify the certificate chain/hostname.

**Expected result:** the application connects with the right CA and hostname; connection fails if the CA is untrusted or the hostname is wrong.

### 11.2. Redis Requiring mTLS

**Goal:** both sides verify identity.

**Steps:**

1. Redis Server trusts the CA signing the client certificate and requires mTLS.
2. Spring trusts the CA signing the server certificate.
3. Spring has a matching, valid client certificate and private key.
4. Redis still uses ACLs if policy requires username/password.
5. Test connecting with valid material; confirm removing the client certificate causes the handshake to be rejected.

**Expected result:** the handshake completes only when both sides' certificate policies are satisfied.

### 11.3. Certificate Rotation

**Goal:** preserve trust when replacing a CA/server certificate.

**Steps:**

1. Prepare a trust bundle containing the new CA following a transition plan—if needed, allow a phase trusting both old and new CAs.
2. Distribute the trust material before replacing server certificates.
3. Replace the server certificate with a valid SAN and update all relevant nodes/proxies.
4. Ensure the driver establishes new connections using the updated trust configuration.
5. Verify the handshake and actual Redis commands.
6. After all sides have switched, remove the old CA per revocation policy.

**Expected result:** zero window during which the application must disable verification to stay connected.

## 12. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| “Having a Redis password means network data is secure.” | ACLs handle authentication/authorization; TLS protects data in transit. |
| “Having TLS means the server is definitely genuine.” | Trust chain and hostname must be checked; TLS does not authenticate properly if verification is bypassed. |
| “Truststore and keystore are the same thing.” | Truststore holds trusted certificates; keystore holds identity certificate and private key. |
| “All Redis TLS setups require mTLS.” | mTLS policy depends on server configuration; Redis Open Source requires client certs by default when TLS is enabled, but this can be disabled with `tls-auth-clients no`. |
| “A CA certificate must be kept secret like a private key.” | A CA certificate used for verification can be distributed; the **CA private key** must be strictly protected. |
| “A certificate signed by a trusted CA is enough.” | It must also be valid in time, policy, and **match the endpoint's SAN**. |
| “A successful `PING` proves every TLS setting is secure.” | It only confirms one connection and one command; verify/trust settings and topology still must be evaluated. |
| “Every Redis command repeats the TLS handshake.” | Handshakes normally happen when creating a connection; commands on open connections reuse the TLS channel. |
| “Restarting Redis automatically updates the client's truststore.” | Client trust material and new connections must be updated on their own lifecycle. |
| “Cluster only needs a certificate on the seed node.” | Clients can connect to multiple nodes after routing; every TLS endpoint needs a valid certificate. |

## 13. Technical Conclusion

To secure Spring Data Redis connections, look at the full chain:

```text
Correct endpoint (DNS + TLS port)
        ↓
Truststore containing trusted CA
        ↓
TLS handshake verifying certificate chain and hostname
        ↓
Client certificate/private key (if mTLS)
        ↓
Redis ACL / command execution permissions
        ↓
Spring Data Redis sends RESP over protected channel
        ↓
Maintain connections, monitor errors, and rotate certificates
```

A trustworthy configuration must ensure that **wrong certificates or wrong hostnames are rejected**, rather than forcing the application to “connect” at all costs. Use Spring Boot SSL bundles when an internal CA or mTLS is needed, keep peer verification intact, protect private keys, and validate certificates on the actual endpoints—including nodes discovered by clients via Redis Cluster/Sentinel.

### Official Documentation

- [Redis — TLS](https://redis.io/docs/latest/management/security/encryption/) — enabling TLS on server, `tls-port`, certificates, mTLS, replication, and Cluster.
- [Redis CLI — SSL/TLS](https://redis.io/docs/latest/develop/tools/cli/) — `redis-cli --tls`, `--cacert`, client certificates.
- [Spring Boot — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/reference/data/nosql.html) — Redis, `spring.data.redis.ssl.enabled`, and SSL bundles.
- [Spring Boot — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html) — SSL bundles using PEM, JKS/PKCS#12.
- [Spring Boot 3.3 — SSL](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html) — corresponding examples for projects using Boot 3.3.
- [Spring Data Redis — Connection Modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html) — standalone, master/replica, Sentinel, and Cluster.
- [Spring Data Redis — LettuceClientConfiguration API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/connection/lettuce/LettuceClientConfiguration.html) — SSL and peer verification.
- [Lettuce — SSL Connections](https://github.com/redis/lettuce/wiki/SSL-Connections) — TLS handshake, truststore, and hostname verification.

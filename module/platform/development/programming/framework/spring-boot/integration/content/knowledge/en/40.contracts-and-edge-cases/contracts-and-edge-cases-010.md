# Testing TLS Security, Invalid Secrets, and Missing Permissions

## Context and Objectives

In **Spring Boot Integration**, an application may call partner HTTP APIs, connect to PostgreSQL/Redis, produce and consume messages via Kafka, RabbitMQ, or Pulsar, and move data across systems through Spring Integration. Every connection carries a **security contract**: verify the right server, prove identity with valid credentials, and perform only authorized actions. A flow tested under admin accounts or overly permissive TLS setups can pass the happy path and then fail under least privilege in production.

This lesson in the **Contracts and Edge Cases** chapter focuses on three categories of deliberately negative tests:

1. **TLS/mTLS:** untrusted certificates, expired certificates, hostname mismatches, missing client certificates, or invalid truststore/keystore settings.
2. **Secrets/credentials:** empty, invalid, or expired tokens, rotated passwords, mispointed secret paths, or wrong keystore passwords.
3. **Authorization:** authenticated identity lacking the required role, scope, ACL, or privilege on the target resource and operation.

The ultimate goal is proving the system **fails closed**: blocking unauthorized actions, leaking zero secrets, never downgrading HTTPS to HTTP, avoiding infinite retries, and never recording business success before connection and permissions are verified.

> **Version scope:** Illustrative configs use Java 17+, Spring Boot **3.2+** with **SSL bundles**, and `RestClient`. On Spring Boot 3.0/3.1 or clients configured by third-party libraries, attaching SSL bundles can differ. Always check your Boot BOM, HTTP client type, and real drivers; never assume every Spring Integration adapter shares a single TLS context.

## 1. Pinpoint where failures actually occur

A connection can be rejected at three distinct boundaries:

```mermaid
flowchart TD
    A[Spring Boot outbound request] --> B{TLS handshake succeeded?}
    B -->|No| C[TLS / certificate / hostname / mTLS error]
    B -->|Yes| D{Credentials valid?}
    D -->|No| E[Authentication failure: e.g. HTTP 401]
    D -->|Yes| F{Authorized for operation?}
    F -->|No| G[Authorization failure: e.g. HTTP 403]
    F -->|Yes| H[Proceed with API / business contract]
```

HTTP `401` and `403` are **HTTP-layer responses** that appear only after the client reaches the HTTP application layer. When the TLS handshake fails, no HTTP response exists to inspect status codes; failures surface via `SSLHandshakeException`, `SSLPeerUnverifiedException`, or client-wrapped exceptions.

| Boundary | Error example | Diagnostic signals | Appropriate response |
|---|---|---|---|
| **TLS trust chain** | Server uses a CA absent from the truststore. | `PKIX path building failed`, `SunCertPathBuilderException`, `SSLHandshakeException`, or JSSE variants. | Abort connection; report trust misconfiguration. |
| **Hostname verification** | Client calls `api.partner.test` while SAN lists only `other.partner.test`. | Hostname/SAN verification failure during TLS handshake. | Never disable hostname checks; fix endpoint or certificate. |
| **Certificate validity** | Expired or not-yet-valid certificate. | Validity window or trust-chain verification error. | Alert/rotate certificate; verify system clock. |
| **mTLS client identity** | Server requires client cert, client omits it or uses untrusted CA. | Handshake rejected; exact error depends on TLS stack and server. | Provision proper key/cert and trust chain; never fall back to anonymous. |
| **Authentication** | Bad/expired bearer token or wrong DB password. | HTTP `401`, DB auth failure, broker auth failure. | Fix/rotate credentials per process; do not hammer retries with the same bad secret. |
| **Authorization** | Valid token missing `orders:write`; DB user lacks `INSERT`. | HTTP `403` (or `404` designed to hide existence), SQLState/ACL denial. | Request least-privilege permissions; never escalate privileges automatically. |
| **Availability** | Broker/DB down, wrong DNS, blocked route. | `ConnectException`, timeout, DNS error. | Handle as connectivity outage per timeout/retry budget; **never misclassify as TLS or bad password**. |

Exception examples in this table are **diagnostic clues**, not universal contracts across every JDK, JDBC driver, or HTTP SDK version. Tests should assert the **error category and security outcome**; only match exact JDK exception text when genuinely needed and stable.

### 1.1. TLS does not replace authentication or authorization

- **TLS server authentication** verifies the server the client connects to and encrypts transport when properly configured.
- **mTLS** adds certificates so the server authenticates the **client at the transport layer**. APIs may still demand separate tokens or scopes to authorize specific operations.
- **Bearer tokens, API keys, and usernames/passwords** are application- or protocol-layer credentials; they may authenticate cleanly even when the account holds read-only rights.
- **ACLs, roles, scopes, and database GRANTs** govern allowed actions on specific resources. “Login succeeded” never proves `publish`, `consume`, `INSERT`, or `DELETE` privileges.

Passing TLS checks must be followed by credential and permission tests rather than treating a successful TLS handshake as complete security coverage.

## 2. Designing negative security test contracts

Each test should explicitly state **the injected fault, what must be rejected, which side effects must not occur, and what may appear in logs/responses**.

| Group | Deliberately invalid input | Minimum passing condition |
|---|---|---|
| TLS-01 | Server certificate issued by an untrusted test CA. | Client receives no business response; never sends HTTP request; zero operations run. |
| TLS-02 | Certificate SAN does not match request hostname. | Handshake rejected even if issuer CA is trusted. |
| TLS-03 | Expired or not-yet-valid certificate. | Connection rejected; error classified as TLS validation. |
| TLS-04 | Server enforces mTLS, client omits client certificate. | Handshake fails; zero application requests sent. |
| TLS-05 | Client presents certificate from untrusted CA or missing matching key. | Connection rejected; never degrades to unauthenticated connection. |
| TLS-06 | Wrong truststore/keystore path or password. | Config/bundle fails to load; app/adapter reports clear error without disabling TLS checks. |
| AUTH-01 | Missing Bearer token / API key. | Auth failure per contract; zero resources created. |
| AUTH-02 | Bad/expired token or wrong DB/broker password. | Fails authentication; records zero business success; secrets masked in logs. |
| AUTHZ-01 | Valid token missing `orders:write` scope. | API denies write; allowed reads still work if permitted by scope. |
| AUTHZ-02 | DB user holds `SELECT` without `INSERT`. | Read queries succeed, writes fail; DB unchanged. |
| AUTHZ-03 | Cache user holds `GET` without `SET` or key pattern permission. | Commands denied by ACL; client never silently falls back to an admin user. |
| AUTHZ-04 | Broker producer lacks `produce` or consumer lacks `consume`/group rights. | Send/receive rejected per operation; messages not silently lost per ACK policy. |
| RECOVERY-01 | Secret rotated/fixed after testing auth failure. | Recovers only once client/config updates cleanly; no TLS or permission relaxation. |

**Never run tests by revoking permissions or rotating secrets in production.** Use isolated test environments, dedicated test principals, and short-lived test certificates/secrets. Testing “missing permissions” must use **an identity that genuinely lacks those permissions**, rather than mocking an HTTP 403 and assuming server ACL policies are right.

## 3. Configuring TLS properly for Spring Boot HTTP clients

### 3.1. SSL bundles centralize truststores, keystores, and TLS settings

Spring Boot **3.1+** introduced SSL bundles; for `RestClient` from Boot **3.2+**, bundles apply cleanly via `RestClientSsl`. The `truststore` controls which CAs/certificates the client trusts; the `keystore` and private key apply when endpoints require **mTLS**. Both can reside in one bundle, while server-authenticated HTTPS needs only a truststore.

```yaml
# application.yml — TLS example for partner API
spring:
  ssl:
    bundle:
      jks:
        partner:
          truststore:
            location: ${PARTNER_TRUSTSTORE_LOCATION}
            password: ${PARTNER_TRUSTSTORE_PASSWORD}
            type: PKCS12

integration:
  partner:
    base-url: ${PARTNER_BASE_URL}
    bearer-token: ${PARTNER_API_TOKEN}
```

Environment variables in the snippet should come from secret/config management. For mTLS, extend the same bundle:

```yaml
spring:
  ssl:
    bundle:
      jks:
        partner:
          keystore:
            location: ${PARTNER_KEYSTORE_LOCATION}
            password: ${PARTNER_KEYSTORE_PASSWORD}
            type: PKCS12
          # key.alias / key.password may be needed depending on key packaging.
```

These two YAML snippets show **sections to merge into one configuration** when enabling mTLS—not two standalone configs to paste back-to-back with duplicate `spring` keys. The client certificate must have appropriate key usage and be trusted by the **server**; placing a keystore on the client achieves nothing if the server rejects that CA or identity.

Building `RestClient` using Spring Boot configuration:

```java
import java.net.URI;

import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.web.client.RestClient;

@ConfigurationProperties(prefix = "integration.partner")
record PartnerProperties(URI baseUrl, String bearerToken) {}

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PartnerProperties.class)
class PartnerClientConfiguration {

    @Bean
    RestClient partnerRestClient(
            RestClient.Builder builder,
            RestClientSsl ssl,
            PartnerProperties properties) {

        return builder
                .baseUrl(properties.baseUrl().toString())
                .apply(ssl.fromBundle("partner"))
                .defaultHeader(HttpHeaders.AUTHORIZATION,
                        "Bearer " + properties.bearerToken())
                .build();
    }
}
```

`RestClientSsl` is auto-configured by Spring Boot for `RestClient`, and `RestClient.Builder` comes from the application context. This illustrates configuration inside an app with `spring-boot-starter-web` or matching REST client starters—not a standalone Java file. In production, **validate `baseUrl` uses HTTPS**, ensure `bearerToken` is non-blank, and design token rotation cleanly. Note that a `defaultHeader` evaluated when constructing the client retains the initial token even after external secrets rotate; never assume Spring refreshes a baked-in header string automatically.

### 3.2. TLS checks beyond the truststore

| Setting | Risk if misconfigured | How to test |
|---|---|---|
| **Root/intermediate CA** | `PKIX` failures from missing chains or trusting wrong CA. | Valid CA passes per test fixture; unknown CA fails. |
| **SAN hostname** | Valid CA accepted yet connects to wrong host. | Cert with SAN `wrong.test` served at `https://localhost` must fail. |
| **Validity (`notBefore`/`notAfter`)** | Expired or future-dated certificates. | Dedicated test certs with short lifetimes; check test clocks. |
| **SNI** | Multi-cert servers serve the wrong cert when SNI/hostname differs. | Hit real endpoint with intended hostname; avoid testing only by raw IP. |
| **TLS versions/ciphers** | Client/server lack common protocols/ciphers. | Allow organization-approved protocols; test disallowed protocol versions fail. |
| **mTLS client cert + private key** | Missing key, wrong alias, or untrusted client cert. | Server `clientAuth=REQUIRE`: missing cert fails, valid cert succeeds. |
| **Truststore/keystore secret** | Wrong password prevents opening store; unreadable file. | Test startup/config failure without confusing it with HTTP `401`. |

**Never use** `trustAll`, `InsecureTrustManagerFactory`, `NoopHostnameVerifier`, a `HostnameVerifier` always returning `true`, `curl -k`, or `spring.ssl` overrides skipping hostname verification to “fix” failing TLS tests. Doing so removes the exact protection tests must verify. Never commit real private keys, passwords, bearer tokens, or `.p12` files containing production keys to Git; use non-sensitive test-only fixtures with restricted permissions.

### 3.3. Generating isolated test certificate fixtures

You can use JDK `keytool` to generate **self-signed certificates strictly for test environments**. This creates a test endpoint with SAN `localhost` and a matching truststore:

```bash
# Run in a temporary test directory; never commit private-key files.
keytool -genkeypair -alias partner-local -keyalg RSA -keysize 3072 \
  -storetype PKCS12 -keystore partner-server.p12 -storepass test-only-pass \
  -keypass test-only-pass -validity 2 \
  -dname "CN=localhost, OU=IntegrationTests, O=Example, C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"

keytool -exportcert -alias partner-local \
  -keystore partner-server.p12 -storepass test-only-pass \
  -rfc -file partner-server.crt

keytool -importcert -noprompt -alias partner-local \
  -file partner-server.crt -storetype PKCS12 \
  -keystore partner-truststore.p12 -storepass test-only-pass
```

The password `test-only-pass` is a **public dummy value strictly for test fixtures**—never use it in real environments. To test hostname mismatch, generate a **trusted cert whose SAN names a different host** like `other.example.test` and call `https://localhost`; that isolates hostname validation from trust-chain errors. To test expiry, generate dedicated expired/future fixtures. Never edit the JVM's global `cacerts` truststore to bypass certificate checks.

## 4. Real TLS integration test without disabling verification

Client contract testing needs a real TLS endpoint. Use HTTPS WireMock, MockWebServer, or a test server configured with TLS. The JUnit 5 example below uses **OkHttp MockWebServer + okhttp-tls** to serve a self-signed certificate trusted only inside the test. It proves two facts: **the default JVM client rejects unknown certificates**, and **only a client configured with explicit trust connects successfully**.

Test dependencies (pick compatible versions, e.g., OkHttp 4.x):

```groovy
testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
testImplementation 'com.squareup.okhttp3:okhttp-tls:4.12.0'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
```

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.net.http.HttpClient;
import java.security.SecureRandom;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.tls.HandshakeCertificates;
import okhttp3.tls.HeldCertificate;
import org.junit.jupiter.api.Test;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

class TlsContractIT {

    @Test
    void rejectsUnknownCertificateButAcceptsExplicitTestTrust() throws Exception {
        HeldCertificate serverCert = new HeldCertificate.Builder()
                .commonName("localhost")
                .addSubjectAlternativeName("localhost")
                .build();
        HandshakeCertificates serverTls = new HandshakeCertificates.Builder()
                .heldCertificate(serverCert)
                .build();

        try (MockWebServer server = new MockWebServer()) {
            server.useHttps(serverTls.sslSocketFactory(), false);
            server.enqueue(new MockResponse().setResponseCode(200).setBody("ok"));
            server.start();

            String url = server.url("/health").toString();
            assertThrows(ResourceAccessException.class, () ->
                    RestClient.create().get().uri(url).retrieve().body(String.class));

            HandshakeCertificates clientTrust = new HandshakeCertificates.Builder()
                    .addTrustedCertificate(serverCert.certificate())
                    .build();
            SSLContext sslContext = SSLContext.getInstance("TLS");
            sslContext.init(null,
                    new TrustManager[]{clientTrust.trustManager()},
                    new SecureRandom());

            RestClient trustedClient = RestClient.builder()
                    .requestFactory(new JdkClientHttpRequestFactory(
                            HttpClient.newBuilder().sslContext(sslContext).build()))
                    .build();

            assertEquals("ok", trustedClient.get().uri(url)
                    .retrieve().body(String.class));
            assertEquals(1, server.getRequestCount());
        }
    }
}
```

This test uses a **dedicated test truststore inside `SSLContext`**, never trust-all. Depending on your framework/client version, the wrapper exception may vary; to verify exact certificate failures, walk the cause chain for `SSLHandshakeException`/certificate validation rather than asserting exact JDK message wording. `server.getRequestCount() == 1` proves the untrusted handshake never reached the HTTP application layer, whereas the trusted request did.

**Add three more independent cases** because this test only covers the trust chain:

1. **Hostname mismatch:** issue a trusted cert whose SAN omits the requested hostname; client must still reject it.
2. **mTLS:** configure MockWebServer/test server to demand client certs and trust a test client CA. Clients lacking a key/cert fail; valid client certs succeed.
3. **Expiry/rotation:** test expired certs alongside valid replacements, verifying errors and trust/cert reload behavior; never assume bundles auto-reload when files change on disk.

For real mTLS APIs, run final tests against **the exact ingress/endpoint and server TLS policy** used in your organization. MockWebServer proves JSSE/client wiring and config mapping, not production ingress mTLS or ACLs.

## 5. Testing wrong, missing, and expired secrets

### 5.1. Not every secret failure produces HTTP 401

| Secret | Failure example | Typical symptom | Notes |
|---|---|---|---|
| Bearer token / API key | Wrong, missing, expired, bad `aud`/issuer. | `401` or contracted auth failure. | Some APIs return other statuses—verify endpoint docs. |
| Database username/password | Wrong password, secret pointing to wrong env. | Driver/authentication error opening connections. | `DataSource` may connect eagerly at startup **or lazily** on first query. |
| Redis ACL user/password | `WRONGPASS`, `NOAUTH`, disabled user. | Redis auth error. | `NOPERM` is a **permission** error after authentication, not a bad password. |
| Broker SASL token/username | SASL auth failure, expired token. | Producer/consumer session fails; listener containers may not start. | TLS handshake may succeed before the broker rejects credentials. |
| TLS keystore/truststore password | Cannot open `.p12`/`.jks`. | SSL bundle/context initialization failure, often at startup. | No HTTP status exists because no app connection opened. |
| Client certificate secret/key | Key mismatches cert or unreadable file. | SSL context error or mTLS handshake failure. | Never fix by disabling client auth. |

**Missing environment variables:** when `${PARTNER_API_TOKEN}` is unset, Spring may fail during config binding or client creation depending on bean initialization timing. Validate non-null/non-blank at startup using `@Validated` plus `@NotBlank`, rather than sending literal `"Bearer null"` or `"Bearer "` to APIs and failing at runtime.

### 5.2. HTTP 401 and 403 responses must be kept distinct

Example contract for `POST /orders` with Bearer token:

```http
POST /orders HTTP/1.1
Host: api.partner.test
Authorization: Bearer <redacted>
Content-Type: application/json

{"orderId":"O-42"}
```

| Test | Token | Permission | Expectation |
|---|---|---|---|
| Valid, authorized | Valid signature/expiry/issuer/audience. | `orders:write` | Server accepts per contract; side effect occurs once. |
| Missing token | No header. | N/A | Usually HTTP `401`; zero new orders. |
| Bad/expired token | Invalid signature or expired. | N/A | Usually HTTP `401`; zero new orders; never log raw token. |
| Valid token, read-only scope | Valid. | `orders:read` only | Usually HTTP `403`; zero new orders. |
| Valid token, right scope, wrong tenant | Valid. | Lacks access to other tenant's resource. | Rejected, `403` or `404` per resource-hiding contract. |

**These status codes are common conventions, not universal mandates.** Some APIs return `404` to hide whether a resource exists; test for `404` **with zero side effects** if contracted that way. Never “fix” `401/403` by retrying endlessly or swapping in an admin token on failure.

### 5.3. Testing 401/403 handling in an HTTP adapter

With `RestClient.retrieve()` and default status handling, Spring throws on 4xx. The snippet below assumes the HTTPS `MockWebServer` fixture from section 4 with client trust enabled:

```java
server.enqueue(new MockResponse().setResponseCode(401));
assertThrows(HttpClientErrorException.Unauthorized.class,
        () -> client.get().uri("/orders").retrieve().toBodilessEntity());

server.enqueue(new MockResponse().setResponseCode(403));
assertThrows(HttpClientErrorException.Forbidden.class,
        () -> client.post().uri("/orders")
                .body("{\"orderId\":\"O-42\"}")
                .retrieve().toBodilessEntity());
```

This tests **how the client maps status codes**, not server-side authentication or authorization; `MockWebServer` returns scripted statuses. To truly test “valid token missing scope,” execute against a **real authorization/resource server or test API environment** enforcing your RBAC/ABAC rules, then check both HTTP responses and server state.

### 5.4. Rotation: does changing a secret let the client recover?

Test at least two cases:

1. Revoke the old credential once the new credential is active. When calls with the old credential fail, the app must **never record false success**, must alert, and must adopt the new credential properly.
2. Secret manager rotates a token/password. Confirm **clients, pools, caches, and connections** pick up the new credential via restart, refresh, or a supported hot-reload hook; never assume `${ENV_VAR}` or a `@Value` field updates dynamically in memory just because external secrets changed.

For refreshable bearer tokens, assign **a single refresh coordinator**; if 1,000 threads hit `401` simultaneously, avoid a thundering herd refreshing tokens and re-sending thousands of requests. Retry only after acquiring a **new valid credential** within your deadline rather than replaying the same invalid secret. For JDBC pools or broker clients, password rotation may require recreating connections or containers depending on driver/library support.

## 6. Testing least privilege for databases, caches, and brokers

### 6.1. Database: verify exact permissions on exact tables

A passing `SELECT 1` or `DataSource.getConnection()` **only proves basic connectivity/authentication**, not table-level privileges. On an **isolated test PostgreSQL database**:

```sql
-- Run as TEST DB admin using a test-only dummy password.
CREATE ROLE integration_reader LOGIN PASSWORD 'local-test-password';
GRANT CONNECT ON DATABASE integration_test TO integration_reader;
GRANT USAGE ON SCHEMA public TO integration_reader;
GRANT SELECT ON TABLE public.orders TO integration_reader;
-- Intentionally do NOT grant INSERT/UPDATE/DELETE on orders.
```

Open a second `DataSource` as `integration_reader` and test:

```sql
SELECT id, status FROM public.orders LIMIT 1;
-- Succeeds when data, schema, and privileges are right.

INSERT INTO public.orders(id, status) VALUES ('O-SECURITY-TEST', 'NEW');
-- Must fail: PostgreSQL typically returns SQLSTATE 42501 (insufficient_privilege).
```

Passing criteria: reads succeed; writes fail; no `O-SECURITY-TEST` row exists; the service **never falls back to an admin `DataSource`**. Verify schema and table grants belong to the **test role** rather than accidentally running tests as superuser. PostgreSQL `42501` is PostgreSQL-specific; MySQL and other engines emit different codes.

With JPA/Hibernate, run tests through actual repositories/services (including flush/commit), because permission errors may remain hidden until Hibernate flushes. Schema tools like Flyway/Liquibase should use a dedicated migration principal with DDL rights; never grant runtime app users DDL privileges just to pass tests.

### 6.2. Redis: authentication vs. ACLs

Redis ACLs restrict by **command** (`GET`, `SET`, `DEL`) and **key pattern**. Two separate tests:

- **Wrong password:** Redis rejects authentication (`WRONGPASS`/`NOAUTH` depending on case/version) before running commands.
- **Valid login with read-only ACL:** `GET cache:products:A1` succeeds; `SET cache:products:A1 ...` fails with `NOPERM`; accessing keys outside `cache:products:*` must also fail if restricted.

In Spring Data Redis, exceptions may wrap as `RedisConnectionFailureException`, `RedisSystemException`, or driver-specific types depending on driver and stage. Avoid asserting exact raw exception messages; verify **which commands executed or were blocked** and verify the ACL user configured on test Redis. If a cache read fails due to missing permissions, define whether the app **fails the request** or **bypasses cache safely** per contract—never treat ACL failures as silent cache misses returning wrong data.

### 6.3. Kafka, RabbitMQ, Pulsar: separate read and write permissions

| Broker / protocol | Privileges to verify | Negative scenario |
|---|---|---|
| **Kafka** | Principal permissions per topic, consumer group, and operation via ACLs; SASL/TLS is a separate auth layer. | Producer lacking `Write` fails to publish; consumer lacking `Read` on topic/group is rejected. |
| **RabbitMQ** | User `configure`, `write`, and `read` permissions per vhost regex. | Missing exchange publish or queue consume permissions trigger channel/permission errors; AMQP connect alone proves nothing. |
| **Pulsar** | Auth role and `produce`/`consume` rights on namespace/topic per policy. | Producer lacking `produce` or consumer lacking `consume` fails on creation or send/receive. |

Test against a **real broker with auth/ACL enabled** or an equivalent staging environment. A standalone/Testcontainers broker **with authorization disabled** proves nothing about roles or ACLs even when messages flow. In Kafka, look for `TopicAuthorizationException` or group authorization errors; in Pulsar/RabbitMQ, exact exceptions and failure timing vary by client and auth plugin. Also check whether producers/consumers **ACKed or committed offsets**: never acknowledge a message as handled when downstream side effects failed due to missing permissions.

### 6.4. Spring Integration and error-channel boundaries

Suppose an `IntegrationFlow` receives messages and invokes an outbound gateway. Outbound adapter TLS/auth failures must enter **your designed error path**: async paths route `ErrorMessage`s to `errorChannel`, whereas synchronous flows propagate exceptions to callers. Never catch everything and return “OK” when an outbound adapter failed to send. Classify errors cleanly:

```text
TLS certificate / hostname / wrong credentials / missing ACL
  -> Config or permission failure: fail fast, alert, isolate flow, fix config.

Timeout / 429 / 503 (conditionally)
  -> Bounded retry with backoff + jitter + deadline, if operation is safe/idempotent.

Contract-invalid payload / poison message
  -> Quarantine or dead-letter per policy; no infinite retries.
```

For message consumers, consider **pausing the consumer and preserving backlog** during widespread credential failures instead of dumping every healthy message to a DLT because a single rotated secret broke. Once secrets/permissions are fixed, restart or refresh listeners cleanly and verify redelivery and idempotency.

## 7. Retry, fallback, and data safety policies on security errors

| Error type | Retry? | Fallback? | What to preserve |
|---|---|---|---|
| Untrusted, expired, or hostname-mismatched cert | **Never blind-retry** same config. | No HTTP downgrade or trust-all. | Block side effects; keep unworked intents durable if needed. |
| Missing mTLS client cert | No retry until config is fixed. | Never strip mTLS. | Never ACK unprocessed business messages. |
| Wrong/missing Bearer token | Do not hammer with same secret; bounded refresh if supported. | Never swap in an admin token. | Block unauthorized actions; mask secrets. |
| HTTP 403 / DB permission denied / broker ACL deny | Normally **do not** retry with unchanged principal and policy. | Never self-escalate or switch to privileged account. | Keep tasks/events safe; alert on ACL misconfig. |
| HTTP 429/503, network timeout | Conditionally, within attempt/deadline/backoff limits. | Queue or outbox if supported. | Idempotency when remote outcome is unknown. |

**Never ACK a message merely because an HTTP request was attempted** if the request failed on TLS or permissions. If a consumer commits offsets before background work passes security checks, messages vanish while callers think they succeeded. Conversely, redelivery after DB commit risks duplicate side effects; use **inbox/outbox, idempotency keys, or proper transactions** per system contract.

On synchronous HTTP APIs, return classified errors without exposing truststore paths, certificate chains, passwords, tokens, or account details. For health/readiness probes, process `UP` does not guarantee downstream connectivity or permissions; decide carefully which probes check dependent endpoints without generating load or mutating state.

## 8. Layered integration test matrix by goal

| ID | Setup | Action | Observed proof required |
|---|---|---|---|
| **S01** | HTTPS server cert issued by CA in test truststore. | GET endpoint. | Valid TLS; HTTP succeeds with valid credentials/scopes. |
| **S02** | Unknown self-signed server cert. | GET endpoint. | TLS rejected; zero HTTP fallback calls. |
| **S03** | Trusted cert with wrong SAN. | GET real hostname. | Hostname verification blocks request. |
| **S04** | Server enforces mTLS; client has no cert. | GET endpoint. | Handshake rejected; never degrades to anonymous. |
| **S05** | Valid client cert from trusted CA and matching key. | GET mTLS endpoint. | TLS succeeds; app authorization still enforced separately. |
| **S06** | Wrong truststore/keystore password. | Boot context or build client. | Config error surfaced cleanly; never silently disables TLS. |
| **S07** | Missing or expired API token. | State-changing POST. | Auth failure per contract; zero new rows/resources. |
| **S08** | Valid API token lacking `orders:write`. | State-changing POST. | Denied per contract; zero side effects. |
| **S09** | Valid token for wrong tenant. | Read/write other tenant's resource. | Denied (`403`/`404` per contract); zero data leakage. |
| **S10** | PostgreSQL role with `SELECT` only. | Read then `INSERT` on same table. | Read works, write denied; row count unchanged. |
| **S11** | Read-only Redis ACL. | `GET` then `SET` on scoped key. | `GET` works, `SET` returns `NOPERM`; data unchanged. |
| **S12** | Kafka/RabbitMQ/Pulsar user lacking publish/consume rights. | Send/receive through real adapter. | Broker rejects operation; listener never reports success. |
| **S13** | Rotate token or DB password. | Fail first, then load valid secret. | Recovers via explicit refresh/restart without weakening security. |
| **S14** | Bad secret triggers batch of failing messages. | Inspect consumer retries and backlog. | Retries stay bounded; messages preserved/quarantined per policy. |
| **S15** | Enable debug HTTP/broker/DB logging. | Trigger 401, TLS, and DB auth failures. | Zero tokens, `Authorization` headers, passwords, private keys, or credentials in URLs logged. |

### 8.1. Mandatory observation criteria

A “fail as expected” test must provide **complete proof**:

1. Failure happens at the **right layer** (TLS handshake, authentication, authorization, or network) and is classified cleanly.
2. Zero **side effects** appear in DBs, HTTP APIs, caches, brokers, or adapters after rejected calls.
3. Zero **policy-weakening fallbacks**, such as HTTPS→HTTP downgrade, trust-all, or admin fallback accounts.
4. Zero infinite retry loops or load spikes; total attempts and timeouts stay bounded per recovery contract.
5. Responses, logs, traces, and metrics expose only **safe error codes and redacted diagnostics**, never raw secrets or private keys.
6. After correcting test config, a **control happy-path test** proves the exact same stack succeeds once trust, credentials, and permissions are valid.

Split real testing across **client unit/contract tests** (mocked statuses, exception mapping), **real TLS/auth/ACL integration tests** (Testcontainers or test services), and **end-to-end/staging** (real ingress, secret managers, network policies). Mocking 403 helps verify client behavior, while only testing against a **policy-enforcing resource server** proves server authorization works.

## 9. Observability, incident handling, and avoiding secret leaks

Integration services must make security observable without turning logs into a secret dump:

| Signal | Operational value | Safe logging practice |
|---|---|---|
| TLS handshake failures, certificate expiry | Catches misconfigurations or incomplete rotations. | Endpoint alias, error category, expiry date, or non-sensitive fingerprint; never dump private keys. |
| Auth failures (401/DB/broker) | Detects invalid tokens or revoked accounts. | Provider, credential type, error class; **never log tokens or passwords**. |
| Authorization denials (403/SQL/ACL) | Detects missing scopes/roles/grants on principals. | Technical principal and normalized resource; never log sensitive payloads. |
| Retry/reconnect attempts and backlog | Catches retry storms from bad configs or persistent denials. | Attempt counts, normalized exception class, adapter, queue depth. |
| `traceId`, `messageId`, `eventId` | Correlates faults across HTTP, brokers, and DBs. | Apply PII policies; keep high-cardinality IDs out of metric labels. |
| Readiness / dependency health probes | Detects live processes with broken mandatory connections. | Safe read/diagnostic probes that never mutate state. |

Never log `Authorization`, `Cookie`, `Set-Cookie`, secrets in query strings, Redis URLs (`redis://user:password@host`), JDBC URLs with embedded passwords, SSL keystore passwords, or raw HTTP bodies containing sensitive fields. HTTP error responses can return generic codes like `UPSTREAM_AUTH_CONFIGURATION_ERROR` or `DEPENDENCY_UNAVAILABLE`, keeping detailed diagnostics in access-controlled redacted internal logs.

### 9.1. Triage workflow when connections are rejected

```mermaid
flowchart TD
    A[Outbound operation failed] --> B{HTTP status / broker auth response present?}
    B -->|No| C{JSSE/TLS or network error?}
    C -->|TLS| D[Check CA, SAN, expiry, mTLS, store passwords]
    C -->|Network| E[Check DNS, port, routing, timeouts]
    B -->|Yes| F{Authentication or authorization?}
    F -->|Authentication| G[Check secret, issuer/audience, expiry, rotation]
    F -->|Authorization| H[Check principal, resource, scope/ACL/GRANT]
    D --> I[Fix config in test/staging and re-test]
    E --> I
    G --> I
    H --> I
    I --> J[Verify success with zero unauthorized side effects]
```

In multi-instance environments, roll out secret and certificate rotations gradually rather than leaving half of instances trusting only the new CA and half only the old CA. Depending on security policy, maintain an overlap window for certificates/keys during rotation. Always restore permissions under **least privilege**—never run `GRANT ALL` or assign admin roles as a quick fix for an undiagnosed `permission denied`.

## 10. Common pitfalls when writing integration security tests

| Mistake | Why it is wrong | Fix |
|---|---|---|
| Using `trustAll` / disabling hostname verification in integration tests. | Tests pass even against spoofed endpoints or mismatched SANs. | Build a test CA, issue proper certs, and add dedicated negative cases. |
| Mocking HTTP 401/403 and concluding server RBAC is verified. | Mocks do not run real authorization rules. | Test against resource servers/brokers/DBs with authz enabled. |
| Running every test as an admin user. | Misses missing or overly broad least-privilege permissions. | Provision read-only, producer-only, consumer-only, and tenant-scoped test principals. |
| Treating a bad keystore password as HTTP 401. | Failure occurs constructing the SSL context before HTTP. | Separate TLS/config, authentication, and authorization branches. |
| Running only `SELECT 1` to prove DB permissions. | Does not test table privileges or business operations. | Query business tables, attempt a denied write, and verify zero mutations. |
| Equating broker connection success with publish/consume rights. | Topic/group/namespace ACLs can deny actions post-handshake. | Test producing and consuming on real resources with authorized and unauthorized roles. |
| Retrying 401/403/TLS validation errors in a loop. | Misconfigurations do not self-heal quickly and cause request storms. | Fail fast, alert, fix config, and retry only after rotating credentials/policies. |
| Updating a secret in secret manager and assuming clients use it automatically. | Pools, beans, and long-lived clients often cache credentials. | Test reload/refresh/restart flows and verify with fresh connections. |
| Logging full HTTP headers or exceptions with secrets while debugging. | Leaks secrets into logs, traces, alerts, and CI artifacts. | Redact systematically; test with canary secrets to prove logs stay clean. |
| ACKing messages after merely queuing tasks in RAM. | Background TLS/permission failures drop already-ACKed messages. | ACK only after side effects or durable work persistence. |

## 11. Pre-production security checklist

1. **Define the connection contract:** HTTPS/TLS version, CAs, hostname/SAN, mTLS requirements, token/password mechanism, and exact scopes/ACLs.
2. **Separate credentials and permissions:** maintain read-only and under-privileged test principals to prove denials.
3. **Negative TLS tests:** unknown CA, hostname mismatch, expired cert, missing/wrong client cert, bad truststore/keystore password.
4. **Negative auth tests:** missing/bad/expired tokens, wrong DB/broker passwords, blank env-var secrets, and secret rotation.
5. **Authorization tests:** 401 vs. 403; DB `SELECT` vs. `INSERT`; broker `produce` vs. `consume`; Redis ACL key patterns.
6. **Block unsafe fallbacks:** zero trust-all, zero HTTP downgrades, zero hidden admin accounts, never swallow exceptions and ACK.
7. **Bound retries by error type:** never retry unfixed TLS/secret/permission failures; bound transient retries with deadlines and idempotency.
8. **Protect data:** verify zero side effects via repositories/brokers; keep work recoverable after fixing credentials.
9. **Safe observability:** categorize failure metrics/traces, redact headers/passwords, keep readiness tied to real mandatory dependencies.
10. **Control tests:** once certificates, secrets, and permissions are valid, verify the exact same use case succeeds on the real integration stack.

Good negative tests prove both **rejection at the right boundary** and **safety of business state**. That ensures a Spring Boot Integration flow runs reliably under least privilege, revoked credentials, certificate rotations, and post-incident recovery.

## References

- [Spring Boot – SSL bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html): configuring PEM/JKS bundles, truststores/keystores, and attaching them to supported clients.
- [Spring Boot – Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): `RestClient.Builder`, `RestClientSsl`, and Boot-configured HTTP clients.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, status handling, and exceptions.
- [JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): trust/key managers, TLS handshakes, and hostname/certificate validation.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS protocols, certificates, server verification, and safe settings.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): storage, rotation, and preventing secret exposure.
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): token validation, issuer/audience checks, and policy authorization.
- [PostgreSQL – GRANT](https://www.postgresql.org/docs/current/sql-grant.html): database, schema, and table privileges.
- [Redis – ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): command and key-pattern ACLs.
- [Apache Kafka – Authorization and ACLs](https://kafka.apache.org/documentation/#security_authz): permissions on topics, consumer groups, and principals.
- [Apache Pulsar – Authorization](https://pulsar.apache.org/docs/next/security-authorization/): produce/consume permissions by role and namespace/topic.

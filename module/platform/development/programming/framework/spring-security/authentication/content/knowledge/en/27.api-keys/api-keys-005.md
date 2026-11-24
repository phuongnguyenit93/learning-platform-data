# API Keys: Key Identification, Permission Scopes, and Environment Restrictions

## 1. Goal

An **API key** is a credential issued by a system to identify and control API callers—typically an application, service, automated job, or partner integration. An API key can look very simple in form, yet using it safely requires answering three questions simultaneously:

1. **Key identification:** *which key* is being used, which owner/service account does it belong to, and who manages its lifecycle?
2. **Permission scopes:** which APIs, operations, and resources is the key allowed to call?
3. **Usage environment:** was the key issued for `dev`, `staging`, or `prod`, and is it being used in the right permitted environment?

For example, a key intended solely for a report-sync app in `staging`, with scope `reports:read`, **must not** be permitted to create reports, modify production data, or call another tenant's APIs.

> **Principle:** An API key becomes an authorized identity *only after* the server verifies the secret and trusted metadata. Key names, prefixes, scopes, or environments self-declared by the client carry zero proof of authorization.

This lesson uses the **Spring Security Servlet stack** (Spring Boot 3.x, Spring Security 6.x, Java 17+) to demonstrate an API key authentication mechanism with a key ID, random secret, scoped permissions, and environment checks. This is a teaching model for self-managed API keys; if an organization has a dedicated API gateway/identity platform, use centralized key management and pass authentication results into the system across a well-defined trust boundary.

## 2. What does an API key authenticate?

In a bearer API key scheme, any party **holding a valid key** can present it to request that key's permissions. Do not interpret `keyId` or `ownerId` as proof that a human user is directly logged in.

~~~text
Client / service / batch job
    |
    | HTTPS
    | X-API-Key: ak_dev_<key-id>.<random-secret>
    v
API gateway or Spring Security
    |
    +--> Parse key ID (identifier to find record)
    +--> Lookup server-side key metadata
    +--> Match secret against stored hash/digest
    +--> Check revoked / expired / environment
    +--> Load trusted scopes, owner/service, tenant
    v
SecurityContext Authentication
    |
    +--> Endpoint-level authorization
    +--> Resource / tenant / object-level authorization
    v
Application returns authorized data
~~~

Two layers must be separated:

- **Authentication:** is the key secret valid, and is the key still active and valid in the current environment?
- **Authorization:** is the authenticated key permitted to perform this action on this resource/tenant?

Never replace authentication by checking client-sent `X-Key-ID` or `X-Environment` headers. Those headers can be forged freely.

### API keys, OAuth access tokens, and sessions

| Credential type | Typically represents | Key takeaways |
|---|---|---|
| API key | An application, service account, partner, or specific key | Often requires self-managing key ID, secret, scopes, revocation |
| OAuth 2.0 access token | Permissions granted by an Authorization Server to a client/subject | Can have audience, expiry, scopes; may also be bearer |
| OIDC ID Token | User authentication result for an OIDC Client | Not meant by default as an API access token |
| Browser session cookie | Logged-in application session | Has its own cookies, session, CSRF, logout mechanics |
| mTLS client certificate | Identity/possession of a client's private key | Provides proof-of-possession, yet still requires authorization |

API keys are better suited for **simple machine-to-machine** integrations with clear permission policies. For user logins, complex multi-party delegation, delegated access, or standardized token needs, typically consider OAuth2/OIDC and an identity platform.

## 3. Key ID and secret: completely different roles

### 3.1. Key identifier (key ID)

The **Key ID** is an identifier used to locate the exact key record in the database and support administration: display, auditing, revocation, and distinguishing multiple keys belonging to the same integration. An ID may be visible in controlled logs.

Example format:

~~~text
ak_dev_3zT5GkQK9_pRAwXt.rE5oDTKJ7C8jl1lC04GbVyiS_Xrtx42lJ7sTc_ZkaXA
└────────────────────────┘ └─────────────────────────────────────────┘
           key ID                    random secret
~~~

This is a **structural example string**; never use it as a real credential. In the implementation example, `ak_dev_<randomId>` is the **key ID** part, and the segment after the dot is the secret.

A Key ID should:
- be unique within the system or environment namespace;
- be hard enough to guess if reducing enumeration is desired, without relying on unpredictability for security;
- never be used directly as permission;
- have an easily recognizable administrative structure when useful (such as `ak_dev_`, `ak_prod_`);
- never contain PII, emails, passwords, confidential info, or tokens.

**There is no concept of "knowing the key ID means authenticated."** A key is valid only when the secret matches and all server-side policies are satisfied.

### 3.2. The secret is a credential requiring protection

The **Secret** must have sufficient entropy to resist guessing/brute force. A good practice is using `SecureRandom` to generate **at least 256 random bits** and Base64URL-encoding them (32 bytes → 43 unpadded Base64URL characters). Never use system names, timestamps, truncated UUIDs, sequential numbers, user-invented passwords, or `Math.random()` to generate secrets.

Illustrative administrative record:

~~~text
key_id:       ak_prod_Xb1qeM85mf4pwH0z
secret:       shown once at issuance (never stored in plaintext)
secret_hash:  SHA-256(256-bit random secret) or HMAC with pepper
environment:  prod
scopes:       ["reports:read"]
owner:        integration:partner-alpha
expires_at:   2026-12-31T00:00:00Z
revoked_at:   null
~~~

These values illustrate **metadata** only, not an issued key. `secret_hash` is stored server-side; when receiving a request, the server takes the presented secret, computes its digest, and compares. For a **truly random 256-bit** secret, SHA-256 is typically suitable for deterministic verification: an attacker obtaining the digest cannot feasibly brute-force the secret. If the secret has low entropy like a human password, proper password hashing (Argon2id/bcrypt/PBKDF2) must be used, and plain SHA-256 must never be assumed sufficient.

### 3.3. Why store a digest instead of the plaintext API key?

If the database or admin dashboard leaks, storing raw keys lets an attacker **log in immediately**. Storing a digest of the secret (with high random entropy) reduces the risk of exposing real credentials. Store the public key ID for lookup and the digest of the secret portion:

~~~text
Request: "ak_dev_<id>.<secret>"
         │                 │
         │                 └─ SHA-256 → compare with stored digest
         └─ DB lookup by ID
~~~

Never log raw keys in applications, reverse proxies, tracing, metrics, exceptions, or analytics. Never pass keys in URL queries because URLs can appear in access logs/history/referrers; for custom APIs, pass them over HTTPS in `X-API-Key` (or an `Authorization` scheme per system contract).

A stricter governance setup can use **HMAC-SHA-256(secret, server-side pepper)** or secret hashing with a pepper managed in KMS/secret manager; that adds operational complexity. Clearly specify the digest structure so algorithm changes are not made silently and break existing keys.

## 4. Metadata of an API key

Recommended data model:

| Field | Content | Purpose |
|---|---|---|
| `key_id` | Unique ID of each key | Lookup, safe logging, rotation/revocation |
| `secret_digest` | Digest of random secret | Credential verification without plaintext storage |
| `owner_type`, `owner_id` | Issued service account/partner/integration | Governs accountability and traceability |
| `environment` | `dev` / `staging` / `prod` | Prevents using keys in the wrong environment |
| `scopes` | E.g., `reports:read`, `reports:write` | Restricts operations on the API |
| `tenant_id` | Assigned tenant or organization | Prevents cross-tenant access |
| `resource_constraints` | Permitted resource groups, project/account IDs | Object-level checks |
| `created_at`, `expires_at` | Issuance/expiration timestamps | Lifecycle control |
| `revoked_at`, `status` | Revoked/disabled status | Immediate lockout when needed |
| `last_used_at` | Most recent successful usage timestamp | Cleaning up inactive keys |
| `allowed_networks` | Optional policy-based CIDRs | Defense in depth, does not replace secret |
| `description` / `rotation_parent` | Purpose and rotation group | Controlled key replacement |

Illustrative SQL schema (PostgreSQL):

~~~sql
CREATE TABLE api_keys (
    key_id         VARCHAR(100) PRIMARY KEY,
    secret_digest  BYTEA NOT NULL,
    owner_type     VARCHAR(32) NOT NULL,
    owner_id       VARCHAR(100) NOT NULL,
    environment    VARCHAR(16) NOT NULL
                   CHECK (environment IN ('dev', 'staging', 'prod')),
    tenant_id      VARCHAR(100),
    scopes         TEXT[] NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at     TIMESTAMPTZ NOT NULL,
    revoked_at     TIMESTAMPTZ,
    last_used_at   TIMESTAMPTZ,
    description    VARCHAR(300),
    CONSTRAINT ck_secret_digest_size
        CHECK (octet_length(secret_digest) = 32)
);
~~~

The schema only illustrates data types and policies; production requires DB access control, migrations, ownership checks, transactional issuance, and granting read access only to needed columns. Scopes/tenants should reference explicit policies; never let users edit JSON metadata to `admin`.

**Each integration should have a separate key per environment, purpose, or partner.** If all services share a single key, auditing, revocation, and damage containment become difficult.

## 5. Permission scopes: grant only what is necessary

### 5.1. Scopes do not come from the request

A key granted `reports:read` can read reports. The client **cannot** grant itself extra permissions with:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.org
X-API-Key: ak_prod_valid-key-and-secret
X-Scope: reports:write
X-Role: ADMIN
~~~

The `X-Scope` and `X-Role` headers are untrusted inputs and **never override** scopes stored with the key record. The server must read scopes **after the secret is verified**, then check them against the endpoint and object.

Example:

| Granted scope | GET /api/reports | POST /api/reports | DELETE /api/reports/{id} |
|---|---|---|---|
| `reports:read` | Allowed, if object-authorized | Denied | Denied |
| `reports:write` | Denied without read | Allowed per policy | Denied without delete |
| `reports:read` + `reports:write` | Allowed | Allowed | Denied |
| `reports:delete` | Does not imply read | Does not imply write | Allowed, if tenant/object match |

A system may structure scopes by resource (`orders.read`) or action (`reports:read`); what matters is a **consistent contract**, without assuming `read` implies `write` or vice versa.

### 5.2. Multi-level permissions

1. **Endpoint + HTTP method:** e.g., `GET /api/reports` requires `reports:read`, `POST` requires `reports:write`.
2. **Owner/tenant:** a key belonging to tenant A must not read tenant B's reports, even with a read scope.
3. **Resource:** a partner key works only within an authorized project/account.
4. **Operation sensitivity:** high-risk operations may require dedicated permissions, approvals, or additional authentication.

For example, tenant `acme`'s `reports:read` key must not access:

~~~http
GET /api/tenants/another-tenant/reports/42 HTTP/1.1
X-API-Key: ...
~~~

The backend must compare the requested tenant/resource against `tenant_id` in the **verified metadata**, never trusting a client-declared tenant ID. Policy-based authorization or `@PreAuthorize` with an object-level checking service can be used alongside `hasAuthority`.

### 5.3. Authorities in Spring Security

One way to represent scopes is `GrantedAuthority("SCOPE_reports:read")`; in configuration:

~~~java
.requestMatchers(HttpMethod.GET, "/api/reports")
    .hasAuthority("SCOPE_reports:read")
~~~

Spring Security checks the exact authority string. This is an **application-designed mapping convention** for custom API keys. Never automatically convert request `X-Scope` headers into `GrantedAuthority`, nor derive user roles solely from `ownerId`.

## 6. Environment restrictions: dev, staging, and prod

### 6.1. Why separate environments?

- `dev`: may use dummy data and integration experiments; keys leaked on developer machines must not call production.
- `staging`: near-production testing, yet must still have isolated accounts/data and permissions.
- `prod`: real data, strict monitoring, rotation, and stringent provisioning policies.

**Never use a single API key secret across dev, staging, and prod.** Separating keys prevents incidents in weaker environments from spilling into production, reduces operators hitting the wrong endpoint, and enables independent revocation.

An effective isolation strategy includes:
1. Key records carry a server-managed `environment`.
2. The runtime reads `app.environment` from trusted deployment configuration (never from header/query/body).
3. During authentication, require `key.environment == app.environment`.
4. Separate key stores, secrets, IAM roles, networks, and data across environments whenever possible.
5. API gateways enforce environment-specific policies so test routes cannot accidentally point to production.
6. Key issuance records the accurate environment and never auto-promotes test keys to live.

### 6.2. Prefixes are only for human recognition

For example, prefixes `ak_dev_` or `ak_prod_` are helpful when reading logs or redacted key IDs, yet **are insufficient to determine the environment**. An attacker can alter prefix text if they know/can craft requests. The authoritative source is the **looked-up and verified key record** paired with trusted runtime configuration.

Example:

~~~text
Client sends:
  key_id prefix: ak_prod_...
Server looks up in DB:
  key.environment = staging
Server running:
  app.environment = prod

Result: rejected — metadata mismatch, do not trust prefix.
~~~

If a key was created with the wrong prefix yet right metadata, fix the issuance process and audit the event; never let prefixes replace DB policies.

### 6.3. IP, origin, referrer, and API caller domains

Keys can be further restricted by **connection source or calling service**, but understand the limits:

- IP/CIDR allowlists are useful for server-to-server traffic when peer/network identity is known; IPs can change via NAT/egress.
- `X-Forwarded-For` and `X-Real-IP` can be forged by clients if the edge does not sanitize them. Use them only when the reverse proxy trust chain is properly configured.
- `Origin`, `Referer`, and HTTP `Host` do not prove which machine holds the secret in arbitrary HTTP clients; non-browser clients can set any value.
- API keys embedded in public website JavaScript or mobile bundles are not true secrets: users can extract them. In those cases, use mechanisms suited for public clients, provider quotas/restrictions, a BFF/delegation, or properly scoped tokens; never use API keys as sensitive administrative credentials.

Environment restriction is **defense in depth**, not a single prefix-matching expression.

## 7. Issuance, storage, rotation, and revocation

### 7.1. One-time key issuance

Standard workflow:

1. Authenticate the administrator or authorized issuance workflow.
2. Select owner/service account, environment, scopes, tenant, expiration date, and quota.
3. Generate a unique random key ID and a sufficiently strong random secret (`SecureRandom`).
4. Persist metadata + secret digest transactionally; log an issuance audit event.
5. **Display/deliver the full secret only once** over a secure channel to the receiving system.
6. The recipient places the secret into a secret manager / CI secret / OS secure store; never commit to source control, URLs, or screenshots.
7. Afterward, the admin portal shows only key ID, description, scopes, environment, expiry, and activity, **never showing the secret again**.

Secrets cannot be "recovered" from digests: if a secret is lost, issue a new key and replace it in the consumer.

### 7.2. Zero-downtime rotation

~~~text
Time T0: key A active
T1: issue key B with same owner/environment and approved scopes
T2: install B into consumer's secret manager
T3: consumer switches to B, monitor success/errors
T4: revoke A after approved overlap window
T5: clean up key A and verify no old requests remain
~~~

Never silently overwrite A's secret in the DB while the consumer still uses A. The new key gets a new key ID; `rotation_parent` or `key_family` can be used for traceability. For key leak incidents, **emergency revocation** may need to happen immediately, accepting disruption when risk outweighs uptime.

### 7.3. Revocation and caching

A key can be `revoked`, expired, disabled via its owner, or stripped of scopes. If the application caches key info, bound cache TTLs, implement invalidation, and define acceptable revocation latency. Never cache indefinitely, especially at gateways or across multiple replicas.

On every request or under an evaluated cache policy, check:
- secret;
- active/revoked status;
- `expires_at`;
- environment;
- whether owner/tenant remain valid;
- currently granted scopes.

Large systems may let an API gateway authenticate and pass identity down to backends via mTLS/trusted headers; backends then trust headers only from the gateway locked down by network policy, never trusting client-supplied headers.

## 8. Runnable example with Spring Boot 3.x, Spring Security 6.x, and Java 17+

The example below illustrates **a stateless API application** authenticating the `X-API-Key` header with standard Spring Security classes. It holds a single key record in memory, configured via test environment variables; **it is not a production key management store**. Production replaces `KeyRepository` with a DB/gateway, adding real revocation, auditing, rate limits, and a secret manager.

### 8.1. Project structure

~~~text
api-key-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/apikey/
    │   ├── ApiKeyDemoApplication.java
    │   ├── KeyIssuer.java
    │   ├── KeyRepository.java
    │   ├── DemoKeyRepositoryConfiguration.java
    │   ├── ApiKeyAuthentication.java
    │   ├── ApiKeyAuthenticationProvider.java
    │   ├── ApiKeyFilter.java
    │   ├── SecurityConfiguration.java
    │   └── ReportController.java
    └── resources/application.yml
~~~

### 8.2. Maven dependencies

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>api-key-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. Server environment and key record from deployment

File `src/main/resources/application.yml`:

~~~yaml
app:
  environment: ${APP_ENV}

demo:
  key:
    id: ${DEMO_KEY_ID}
    secret-sha256: ${DEMO_KEY_HASH}
    environment: ${DEMO_KEY_ENV}
    expires-at: ${DEMO_KEY_EXPIRES_AT}
~~~

Both `app.environment` and `demo.key.environment` come from deployment/secret configuration. In the demo, both can be set to `dev`; **in production**, the runtime environment must be controlled by the deployment platform, and key metadata must come from the DB/issuance policy rather than setting `environment=app.environment` for every loaded key.

All environment variables must be provided before startup. If missing, the application should fail startup due to missing configuration rather than falling back to a guessable default key.

### 8.4. Generating a random key ID and secret

File `src/main/java/com/example/apikey/KeyIssuer.java`:

~~~java
package com.example.apikey;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Set;

public final class KeyIssuer {

    public static void main(String[] args) throws Exception {
        if (args.length != 1 ||
                !Set.of("dev", "staging", "prod").contains(args[0])) {
            throw new IllegalArgumentException(
                    "Expected environment: dev, staging, or prod");
        }

        SecureRandom random = new SecureRandom();
        byte[] idBytes = new byte[12];
        byte[] secretBytes = new byte[32];
        random.nextBytes(idBytes);
        random.nextBytes(secretBytes);

        Base64.Encoder encoder =
                Base64.getUrlEncoder().withoutPadding();
        String id = "ak_" + args[0] + "_"
                + encoder.encodeToString(idBytes);
        String secret = encoder.encodeToString(secretBytes);

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(secret.getBytes(StandardCharsets.UTF_8));

        System.out.println("key_id=" + id);
        System.out.println("api_key=" + id + "." + secret);
        System.out.println("secret_sha256_hex="
                + HexFormat.of().formatHex(digest));
    }
}
~~~

This is a **standalone Java program**, compiled and run from the project directory without needing the Spring runtime:

~~~bash
javac -d out src/main/java/com/example/apikey/KeyIssuer.java
java -cp out com.example.apikey.KeyIssuer dev
~~~

Output consists of three lines `key_id=...`, `api_key=...`, `secret_sha256_hex=...`; **exact values change every run** because `SecureRandom` is used, so there is no fixed stdout to compare. The secret is shown once to demonstrate issuance; in production it must be displayed/delivered securely without pushing output into CI build logs or console-recording systems.

**Technical note:** the digest is computed from the **secret**, not from the entire `id.secret` string. The server must follow this rule to verify correctly. The key ID has 12 random bytes → 16 Base64URL chars; the secret has 32 bytes → 43 unpadded Base64URL chars.

### 8.5. Key metadata repository

File `src/main/java/com/example/apikey/KeyRepository.java`:

~~~java
package com.example.apikey;

import java.time.Instant;
import java.util.Optional;
import java.util.Set;

interface KeyRepository {
    Optional<StoredKey> findById(String keyId);
}

record StoredKey(
        String keyId,
        byte[] secretSha256,
        String environment,
        Set<String> scopes,
        Instant expiresAt,
        boolean revoked
) {}
~~~

The record fields are **server-side metadata**, not taken from HTTP requests. With a real DB, `findById` returns a unique key record, and scopes/owner/tenant are centrally managed.

File `src/main/java/com/example/apikey/DemoKeyRepositoryConfiguration.java`:

~~~java
package com.example.apikey;

import java.time.Instant;
import java.util.HexFormat;
import java.util.Optional;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DemoKeyRepositoryConfiguration {

    @Bean
    KeyRepository keyRepository(
            @Value("${demo.key.id}") String keyId,
            @Value("${demo.key.secret-sha256}") String hashHex,
            @Value("${demo.key.environment}") String keyEnvironment,
            @Value("${demo.key.expires-at}") String expiresAt) {

        byte[] digest = HexFormat.of().parseHex(hashHex);
        if (digest.length != 32) {
            throw new IllegalArgumentException(
                    "Expected a 32-byte SHA-256 digest");
        }

        StoredKey row = new StoredKey(
                keyId,
                digest,
                keyEnvironment,
                Set.of("reports:read"),
                Instant.parse(expiresAt),
                false);

        return candidateId ->
                keyId.equals(candidateId)
                        ? Optional.of(row) : Optional.empty();
    }
}
~~~

**For demo use only:** this record holds a single key with scope `reports:read`. It uses a digest passed via environment variables without storing the raw secret in Java source. Production must replace `DemoKeyRepositoryConfiguration` with a DB repository managing multiple keys/revocations, bound to real owners, tenants, and environments.

### 8.6. Authentication type for API keys

File `src/main/java/com/example/apikey/ApiKeyAuthentication.java`:

~~~java
package com.example.apikey;

import java.util.Collection;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class ApiKeyAuthentication
        extends AbstractAuthenticationToken {

    private final Object principal;
    private Object credentials;

    private ApiKeyAuthentication(
            Object principal,
            Object credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean verified) {
        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        super.setAuthenticated(verified);
    }

    static ApiKeyAuthentication presented(String rawKey) {
        return new ApiKeyAuthentication(null, rawKey, null, false);
    }

    static ApiKeyAuthentication verified(
            String keyId,
            Collection<? extends GrantedAuthority> authorities) {
        return new ApiKeyAuthentication(keyId, null, authorities, true);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return credentials;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        credentials = null;
    }
}
~~~

Before authentication, the token holds the raw key in `credentials` with `authenticated=false`. **Only the AuthenticationProvider**, after passing checks, creates an authenticated token with `principal=keyId`, authorities, and **no raw key retained in the result**.

### 8.7. AuthenticationProvider validating secret + environment + status

File `src/main/java/com/example/apikey/ApiKeyAuthenticationProvider.java`:

~~~java
package com.example.apikey;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.List;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class ApiKeyAuthenticationProvider
        implements AuthenticationProvider {

    private final KeyRepository repository;
    private final String runtimeEnvironment;

    public ApiKeyAuthenticationProvider(
            KeyRepository repository, String runtimeEnvironment) {
        this.repository = repository;
        this.runtimeEnvironment = runtimeEnvironment;
    }

    @Override
    public Authentication authenticate(Authentication authentication) {
        if (!(authentication instanceof ApiKeyAuthentication) ||
                !(authentication.getCredentials() instanceof String raw)) {
            return null;
        }

        int dot = raw.indexOf('.');
        if (dot <= 0 || dot != raw.lastIndexOf('.') ||
                dot == raw.length() - 1) {
            throw new BadCredentialsException("Invalid API key");
        }

        String id = raw.substring(0, dot);
        String secret = raw.substring(dot + 1);

        if (!id.matches("ak_(dev|staging|prod)_[A-Za-z0-9_-]{16}") ||
                !secret.matches("[A-Za-z0-9_-]{43}")) {
            throw new BadCredentialsException("Invalid API key");
        }

        StoredKey stored = repository.findById(id)
                .orElseThrow(() ->
                        new BadCredentialsException("Invalid API key"));

        byte[] candidate = sha256(secret);
        boolean correctSecret = MessageDigest.isEqual(
                stored.secretSha256(), candidate);
        boolean active = !stored.revoked()
                && Instant.now().isBefore(stored.expiresAt());
        boolean correctEnvironment = stored.environment()
                .equals(runtimeEnvironment);

        if (!correctSecret || !active || !correctEnvironment) {
            throw new BadCredentialsException("Invalid API key");
        }

        List<GrantedAuthority> authorities = stored.scopes()
                .stream()
                .map(scope ->
                        (GrantedAuthority) new SimpleGrantedAuthority(
                                "SCOPE_" + scope))
                .toList();

        return ApiKeyAuthentication.verified(
                stored.keyId(), authorities);
    }

    private static byte[] sha256(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 is required by the Java platform", ex);
        }
    }

    @Override
    public boolean supports(Class<?> authenticationType) {
        return ApiKeyAuthentication.class
                .isAssignableFrom(authenticationType);
    }
}
~~~

Explanation:
1. **Strict parsing:** accepts only a single dot between ID/secret and the system-issued key format. The ID regex permits `dev/staging/prod`; **regex does not replace environment validation**.
2. **Lookup by key ID:** the identifier is not a secret; no need to scan every key.
3. **Digest comparison:** `MessageDigest.isEqual` avoids early-exit byte-by-byte comparisons; 256-bit random secrets make SHA-256 digests appropriate for the example.
4. **Status and expiry:** revoked or expired keys are rejected. `Instant.now().isBefore(expiresAt)` means **at the exact expiration instant it is also no longer valid**.
5. **Environment:** server-stored metadata must match the runtime's own `app.environment`, never taken from the client.
6. **Authorities:** only after all checks pass do server-side scopes become `SCOPE_...`. The demo never reads `X-Scope`, `X-Role`, or `X-Environment`.
7. **Generic error:** wrong key ID, secret, environment, and revoked status all produce `BadCredentialsException("Invalid API key")`; avoid leaking whether a key exists in responses.

Production also needs lookup timeouts, audits traceable by key ID, rate limiting, owner/tenant checks, and revocation effective across all replicas. Never log raw keys in exceptions/debug tracing.

### 8.8. Filter reading the header without storing credentials in session

File `src/main/java/com/example/apikey/ApiKeyFilter.java`:

~~~java
package com.example.apikey;

import java.io.IOException;
import java.util.Enumeration;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ApiKeyFilter extends OncePerRequestFilter {

    private final AuthenticationManager authenticationManager;

    public ApiKeyFilter(AuthenticationManager authenticationManager) {
        this.authenticationManager = authenticationManager;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Enumeration<String> values = request.getHeaders("X-API-Key");

        if (!values.hasMoreElements()) {
            chain.doFilter(request, response);
            return;
        }

        String presented = values.nextElement();
        if (values.hasMoreElements() || presented.isBlank()
                || presented.length() > 256 || presented.contains(",")) {
            response.sendError(401, "Invalid API key");
            return;
        }

        Authentication verified;
        try {
            verified = authenticationManager.authenticate(
                    ApiKeyAuthentication.presented(presented));
        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            response.sendError(401, "Invalid API key");
            return;
        }

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);
        chain.doFilter(request, response);
    }
}
~~~

- The filter executes once per **single request** and expects `X-API-Key` per contract. Duplicate headers or ambiguous values are rejected.
- If **no header is present**, the filter does not create a principal; downstream Spring authorization rejects protected endpoints.
- If the header is invalid, the filter sends 401 without letting unhandled authentication errors leak out; never include the secret in messages.
- When valid, `SecurityContextHolder.createEmptyContext()` creates a fresh context to store the authentication. Spring Security manages/clears the context per request lifecycle; the demo is stateless and saves no session.
- Checking duplicates via the Servlet API is one defensive layer; edge/proxies must normalize and reject ambiguous request headers because header merging depends on each hop.
- The filter is instantiated **inside SecurityFilterChain**, not declared as another Servlet `@Bean Filter`, to avoid auto-registration/running twice.

### 8.9. SecurityFilterChain enforcing scopes by HTTP method

File `src/main/java/com/example/apikey/SecurityConfiguration.java`:

~~~java
package com.example.apikey;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            KeyRepository repository,
            @Value("${app.environment}") String environment)
            throws Exception {

        var provider = new ApiKeyAuthenticationProvider(
                repository, environment);
        var manager = new ProviderManager(provider);

        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/api/reports")
                            .hasAuthority("SCOPE_reports:read")
                        .requestMatchers(HttpMethod.POST, "/api/reports")
                            .hasAuthority("SCOPE_reports:write")
                        .anyRequest().denyAll())
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint((request, response, ex) ->
                                response.sendError(
                                        401, "API key required")))
                .addFilterBefore(
                        new ApiKeyFilter(manager),
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
~~~

- `anyRequest().denyAll()` locks down all undeclared endpoints; admin or health-check routes must have an explicitly approved policy if needed.
- `hasAuthority("SCOPE_reports:read")` matches the exact authority built by the Provider from the **key record's scopes**.
- `STATELESS` does not use HTTP sessions to store identity; every request must present a key or another explicitly designed mechanism.
- `csrf(...disable)` **fits only pure API examples that do not rely on browser cookies auto-sending credentials**. If the same app has web sessions/cookies or browser-handled endpoints, use a separate security chain/CSRF strategy; never copy disabling CSRF to every application.
- `httpBasic` and `formLogin` are disabled because the example accepts only API keys. Never open other fallback authentication methods that undermine the policy.
- This is **custom API key authentication**, not a complete built-in API key filter provided by Spring Security by default.

### 8.10. Illustrative endpoints and main class

File `src/main/java/com/example/apikey/ApiKeyDemoApplication.java`:

~~~java
package com.example.apikey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiKeyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyDemoApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/apikey/ReportController.java`:

~~~java
package com.example.apikey;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/api/reports")
    Map<String, String> read(Authentication authentication) {
        return Map.of(
                "status", "read granted",
                "keyId", authentication.getName());
    }

    @PostMapping("/api/reports")
    Map<String, String> write() {
        return Map.of("status", "write granted");
    }
}
~~~

`authentication.getName()` in this sample is the **key ID**; there is no raw secret in the verified `Authentication`. When building real systems, controllers do not necessarily return the key ID to clients; use the key ID for controlled audit logs, and retrieve `ownerId`/tenant from the server-side principal if data policies apply.

### 8.11. Running the demo with PowerShell (Windows)

Inside `api-key-demo`, generate a test key:

~~~powershell
javac -d out src/main/java/com/example/apikey/KeyIssuer.java
$issued = java -cp out com.example.apikey.KeyIssuer dev

$values = @{}
foreach ($line in $issued) {
    $pair = $line.Split('=', 2)
    $values[$pair[0]] = $pair[1]
}

$env:APP_ENV = "dev"
$env:DEMO_KEY_ENV = "dev"
$env:DEMO_KEY_ID = $values["key_id"]
$env:DEMO_KEY_HASH = $values["secret_sha256_hex"]
$env:DEMO_KEY_EXPIRES_AT = (Get-Date).ToUniversalTime()
    .AddHours(2).ToString("yyyy-MM-ddTHH:mm:ssZ")
$env:API_KEY = $values["api_key"]

mvn spring-boot:run
~~~

These variables are for the demo environment only. `mvn spring-boot:run` keeps the terminal running the app; open a second terminal to call the API, supplying the newly issued key securely. In production, do not keep keys in `$env:API_KEY` long-term or emit keys to logs.

**If PowerShell errors when copying the multiline expiration assignment**, write that assignment on one line:

~~~powershell
$env:DEMO_KEY_EXPIRES_AT = (Get-Date).ToUniversalTime().AddHours(2).ToString("yyyy-MM-ddTHH:mm:ssZ")
~~~

At runtime, both `APP_ENV` and `DEMO_KEY_ENV` are `dev`. The demo key's scope is **`reports:read` only**.

### 8.12. Testing requests and expectations

From a terminal with the `API_KEY` variable set:

~~~powershell
# Valid: read-only.
curl.exe -i -H "X-API-Key: $env:API_KEY" http://localhost:8080/api/reports

# Missing key: rejected.
curl.exe -i http://localhost:8080/api/reports

# Read-only key requesting write: rejected.
curl.exe -i -X POST -H "X-API-Key: $env:API_KEY" http://localhost:8080/api/reports
~~~

**Expected:**
- GET with valid key: HTTP `200` and JSON containing `status: "read granted"` and the key ID.
- GET without key: HTTP `401`.
- POST with read-only-scoped key: HTTP `403`.

These are the expected results when the application is built and run with the right configuration; **there is no fixed stdout from KeyIssuer** because keys are generated randomly. In real environments, replace `http://localhost` with HTTPS using trusted certificates and proper infrastructure policies.

### 8.13. Testing a key in the wrong environment

To prove the environment boundary, set the key record to `dev` while the runtime is `prod`:

~~~powershell
$env:APP_ENV = "prod"
$env:DEMO_KEY_ENV = "dev"
mvn spring-boot:run
~~~

With the same key generated for dev, the GET request gets HTTP `401` because `stored.environment != runtimeEnvironment`. In real production, separate databases/key stores, deployment configs, and IAM must still be maintained; the demo only proves the **application-level environment check**.

## 9. Where the demo differs from a production system

**The example has only one in-memory key.** Moving to production requires adding:

- **Real key management service/repository:** issuance, digest storage, lookup by ID, revocation, rotation, expiry, owner, tenant, scopes, auditing.
- **Centralized secret management:** human/app recipients see the secret only once; use a secret manager, never YAML with plaintext or source control.
- **Isolated environments:** separate key stores, databases, secret namespaces, IAM, API endpoints, and network policies for dev/staging/prod; server-side environment checks act as an additional safeguard.
- **Object access restrictions:** use owner/tenant/project metadata post-authentication to filter data. `SCOPE_reports:read` alone is not enough to read another organization's reports.
- **Rate limits/quotas:** per key ID, owner, tenant, client, and route, combined with key-guessing/abuse detection; never log raw keys.
- **Revocable caching:** short TTLs and explicit invalidation; revocation propagation latency must be measured.
- **Connection security:** HTTPS at the edge and internal hops, TLS peer verification, firewall/network policies, blocking spoofed headers from other proxies.
- **Issuance permissions:** granting scopes/env/tenants must be reviewed, preventing privilege self-escalation during key creation.
- **Error handling:** clients receive generic messages for invalid keys; the server audits enough detail for investigation without exposing secrets/hashes.
- **Distinguishing API keys from user identities:** if a key belongs to a partner, the principal should be a service account/key ID; user-level authorization requires a separate mechanism.
- **Key format/versioning:** if changing formats later, prepare `key_version` and a migration path, avoiding brittle parsing when multiple key generations coexist.
- **Key rotation and endpoint uptime:** provide a controlled overlap window, monitor old key usage, and revoke after cutover.

## 10. Test suite for key ID, scope, and environment

| Scenario | Expected result |
|---|---|
| Valid key ID, right secret, matching environment, active, right scope | Authentication succeeds, endpoint access granted |
| Existing key ID but wrong secret | 401 |
| Non-existent key ID | 401, does not confirm whether key exists |
| Knowing only key ID without secret | 401 |
| Secret off by one character | 401 |
| `revoked` key | 401, even with valid secret |
| Key past `expires_at` | 401 |
| Dev key sent to prod runtime | 401, even if prefix/header is altered |
| `reports:read` scope calling POST requiring `reports:write` | 403 |
| Adding `X-Scope: reports:write` manually | Still 403, as permissions come from the server |
| Changing `X-Environment: prod` on the request | Has no effect |
| Duplicate `X-API-Key` headers or ambiguous merged header | Rejected |
| API key sent in URL query, bypassing header contract | Not authenticated |
| Key has right scope but targets another tenant | Blocked by tenant/object policy |
| Valid key whose `owner` is disabled | Blocked per actual policy |
| Trying thousands of guessed keys | Secret cannot be guessed; throttled and alerted |
| Key revoked while multiple replicas cache | All replicas stop accepting within revocation SLA |
| Spoofed callback/HTTP host/Origin | Cannot escalate permissions or switch environments |
| Key leaked from public JS client | Enforces quota/restrictions, grants no sensitive privileges |

**Error classification note:** `401 Unauthorized` means missing/invalid credentials; `403 Forbidden` means authenticated but lacking required permission. At the API layer, the server may return 404 to avoid disclosing object existence per policy. Codes can be customized via `AuthenticationEntryPoint`/`AccessDeniedHandler`, but security semantics must remain consistent.

### Integration tests need middleware and network coverage

Provider unit tests check digests, revocation, expiry, env, and scopes. `MockMvc`/HTTP integration tests check the filter, duplicate header errors, 401/403 statuses, that other endpoints remain closed, and that DB roles/scopes cannot be self-elevated by clients. Test the **real path** through gateways/reverse proxies: IPs, header normalization, HTTPS, hop metadata, and backend ingress restrictions.

For the demo, the baseline cases to run before production deployment are valid GET 200, missing/wrong secret 401, wrong environment 401, and write missing scope 403. When tenant/object-level authorization exists, add cross-tenant tests at the repository/service layer.

## 11. Common pitfalls

1. **Treating key ID as a secret:** key IDs can be visible; permission is proven only when the secret is valid and policies pass.
2. **Treating the `ak_prod_` prefix as security:** prefixes aid administration; environments must be checked against server metadata and runtime configuration.
3. **Hardcoding keys in Git, mobile apps, or frontend JS:** secrets can be extracted; use mechanisms suited to client types, secret managers, and grant no sensitive privileges to public clients.
4. **Generating keys from timestamps/simple UUIDs:** lacks required secret entropy; use `SecureRandom`.
5. **Storing plaintext keys in DB or logs:** DB/log leaks become credential leaks; store secret digests and redact request headers.
6. **Using SHA-256 for user-chosen passwords:** plain SHA-256 fits here only because random secrets have high entropy; human passwords require password hashing.
7. **Trusting client-sent `X-Scope`/`X-Role`:** permissions must come from verified metadata or a trusted identity service.
8. **Issuing one `admin` key for all systems:** prevents independent auditing/revocation and expands blast radius; issue least-privilege keys per consumer/environment.
9. **Protecting only URLs without HTTP methods:** read/write scopes must bind to operations, object-level authorization, and tenants.
10. **Omitting expiry or revocation:** keys could live forever; implement emergency lockout, rotation, overlap, and cache invalidation.
11. **Using `Origin`/`Referer` as proof a key came from the right app:** HTTP clients can spoof them; never use as sole verification.
12. **Trusting `X-Forwarded-For` from the Internet:** requires edge sanitization and a proxy trust chain; IP is only a supplemental control.
13. **Allowing staging keys to access production data:** separate key stores/secrets/databases/IAM and verify environments.
14. **Filter works yet controller ignores tenant:** `authenticated()` and scope checks do not solve IDOR/BOLA.
15. **Registering the filter twice:** avoid `@Bean Filter` and `addFilterBefore` simultaneously without suppressing servlet auto-registration.
16. **Allowing auth fallback when API key fails:** if an endpoint is designated API-key-only, never silently fall back to anonymous or weaker auth.
17. **Over-logging during debugging:** never log raw `X-API-Key` or `Authorization`; audit key ID, owner/service, and sanitized outcomes.

## 12. Production API key design checklist

- [ ] Key ID is unique, stable, sufficient for lookup and auditing; contains no sensitive data.
- [ ] Secret generated from CSPRNG, at least 256 bits, delivered securely once, non-viewable afterward.
- [ ] DB stores digest/metadata; digest verified safely, zero plaintext stored.
- [ ] Each key belongs to a specific owner/service, tenant, and approved environment.
- [ ] `dev`, `staging`, `prod` have independent secrets and policies.
- [ ] Server rejects keys whose environment differs from the deployment environment.
- [ ] Scopes are attached to the key record, never taken from client headers/queries/bodies.
- [ ] Authorization enforced by HTTP method + resource + tenant/object, applying least privilege.
- [ ] Expiration, revocation, rotation, unused-key cleanup, and auditing in place.
- [ ] Rate limits/quotas, abuse detection, no raw key logging.
- [ ] Full HTTPS/TLS; backend/gateway trust boundary designed and tested.
- [ ] No sensitive API keys embedded in public clients; no query parameters used.
- [ ] Tests cover missing key/wrong secret/valid ID/invalid env/insufficient scope/cross-tenant.
- [ ] When using a gateway, backend trusts authentication results only over a protected gateway channel.
- [ ] Partner documentation covers key issuance, rotation, revocation, permission boundaries, and 401/403 handling.

## 13. Key takeaways

**The Key ID identifies which key it is; the secret proves the caller holds the credential; metadata determines what can be done and where it can be used.** After verifying the secret, Spring Security can place the key ID into `principal` and granted scopes into `GrantedAuthority`, enforcing `hasAuthority` rules across the API.

A secure API key system does not merely ask **"is the key valid?"**—it also asks **"is this key still active, who manages it, which tenant does it belong to, is the environment right, and is it authorized for this specific resource?"**.

## 14. References

1. [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider`, `SecurityContext`.
2. [Spring Security — Servlet Security Filter Chain](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `SecurityFilterChain`, placing authentication filters, `OncePerRequestFilter`.
3. [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `requestMatchers`, `hasAuthority`, `denyAll`.
4. [OWASP API Security Top 10 — Broken Object Level Authorization (API1:2023)](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): broad scopes do not replace per-object authorization checks.
5. [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): credential/secret management and rotation.
6. [Google Cloud — Best practices for managing API keys](https://docs.cloud.google.com/docs/authentication/api-keys-best-practices): key restrictions, protecting storage/transit, deleting unused keys.
7. [Oracle Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): generating strong random bytes.
8. [Oracle Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256 and `isEqual` for comparing digests.

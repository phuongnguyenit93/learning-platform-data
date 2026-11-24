# Managing Connection Passwords, Client Secrets, Signing Keys, and Application Secrets

## 1. Objectives and Scope

In a Spring Boot application, user login is only one part of security. The application itself must also prove its identity when connecting to PostgreSQL, LDAP, Redis, SMTP, an OAuth2 Authorization Server, partner systems, or a secret manager. If the system issues JWTs, it also holds a private signing key; if it only verifies JWTs, it must verify public keys and the issuing source. These credentials and keys have **different sensitivity levels, storage locations, access permissions, and rotation cycles**.

This topic belongs to the **Operations** section of the **Spring Security - authentication** module. It focuses on how to **provision, store, distribute, consume, rotate, revoke, and audit** secrets, rather than simply placing a password into a configuration file and assuming it is safe.

After this lesson, you will be able to:

1. Distinguish end-user passwords from service account passwords, OAuth2 client secrets, API keys, private signing keys, encryption keys, and public JWKs.
2. Choose the right storage option: secret manager, KMS/HSM, workload identity, mounted file, or environment variable under a specific threat model.
3. Use Spring Boot 3.5/Java 17+ externalized configuration, config trees, and standard OAuth2 client property names.
4. Understand how a resource server verifies JWTs using public JWKS without holding the private signing key.
5. Design zero-downtime rotation **when the dependent system supports it**, including key IDs, active versions, overlap, readiness checks, and revocation.
6. Handle password/key exposure incidents and prevent leaks through Git, CI/CD, containers, logs, tracing, Actuator, and HTTP.
7. Run a standalone Java 17 program simulating key rotation and a Spring Security example reading a password from external configuration.
8. Write tests and a verification checklist for **fail-closed behavior, least privilege, no secret logging, sessions/tokens, and operational readiness**.

This is security operations knowledge. The examples in this lesson are for a learning environment, not a security compliance certification or a complete IAM/JWT issuer system.

## 2. Classification: What Is Secret and What Is Not?

| Data Type | Needs to Be Kept Secret? | Purpose |
| --- | --- | --- |
| JDBC connection password | **Yes** | Service account connecting to the database |
| LDAP bind password | **Yes** | Service looking up/authenticating via directory |
| Redis/Kafka/SMTP credentials | **Yes** | Authenticating with infrastructure |
| OAuth2 client ID | Usually **no** | Identifying the client |
| OAuth2 client secret | **Yes** | Confidential client proving its identity to the authorization server |
| API key, webhook HMAC secret | **Yes** | Machine authentication or request integrity |
| JWT RSA/EC private signing key | **Highly sensitive** | Creating JWT signatures |
| JWT public verification key/JWKS | Usually **does not need hiding** | Verifying signatures, though source and algorithm must be verified |
| JWT symmetric HS256 key | **Yes** | Both signing and verifying MACs |
| Session signing/encryption key | **Yes** | Preventing cookie/session token tampering when the mechanism uses one |
| Encryption key/AES key | **Yes** | Decrypting/encrypting data |
| TLS private key | **Yes** | Proving certificate ownership |
| TLS public certificate | No, but must be trusted | Trusting and verifying the server/client |
| User-entered password | **Yes** | User authentication; store as a password hash, never plaintext |
| Secret name/version | Depends on security level | Metadata for routing and auditing |

**Do not confuse client ID with client secret.** A client ID is not a substitute password; for a confidential client, the secret is the shared credential. **Do not confuse public keys with private keys.** Public JWKS can be published to resource servers, but the signer's private key must never appear in public JWKS.

**Never reuse a single value** across JWT signing, API keys, database passwords, encryption, and OAuth2 client authentication. Independent secrets limit the damage if one integration is compromised.

## 3. How Do End-User Passwords Differ from Service Secrets?

An **end-user password** only needs to be **verified**, so the server should store a salted, slow password verifier via `PasswordEncoder`, such as Argon2id/bcrypt/PBKDF2 according to policy. There is no need to recover the original password. Never keep plaintext via reversible encryption in the users table just for emailing or debugging convenience.

A **service credential** often must be **actively used**: a JDBC driver sends a password to handshake with the DB, an OAuth2 client sends a client secret to the token endpoint, or a system signs a JWT using a private key. Therefore, storing only a hash is insufficient for the consumer side. Service secrets need a trusted source (managed secret store, dynamic credentials, KMS/HSM) and a secure delivery path.

| Criterion | User Password | Application Secret |
| --- | --- | --- |
| Recover plaintext after storage? | No | May be required, or must call KMS/HSM |
| Storage location | Salted password hash | Secrets manager, credential provider, KMS/HSM |
| Periodic rotation? | Not applied automatically; NIST recommends against forced rotation without cause | Per policy, TTL, risk, and provider limitations |
| When exposed | Reset password, protect account and sessions | Revoke/reissue, roll out to consumers, investigate dependent systems |
| Permissions | User identity and policy | Workload/service account identity, IAM, least privilege |

NIST SP 800-63B-4 advises **against forcing users to change passwords periodically** if there is no evidence of compromise. Do not apply that advice verbatim to application client secrets or signing keys: machine secrets have different threat models, leases, and lifecycles.

## 4. Threat Model: Through Which Paths Do Secrets Leak?

High-risk locations:

- Repository: `application-prod.yml`, `.env`, keystores, private key PEMs, backup files, test fixtures copied from production.
- Git history, pull request comments, forks, and source-code mirrors: deleting in a new commit **does not revoke** an exposed secret.
- Docker images/JARs, build caches, SBOMs, CI artifacts, Helm values; a secret may remain in an older layer.
- CI/CD logs: debug shells, `set -x`, job outputs, echoed variables, process arguments.
- Process: environment variables, command line, heap dumps, core dumps, live debugging, JMX, container exec.
- HTTP: Authorization headers, cookies, API keys, OAuth callbacks, refresh tokens, connection URLs with userinfo, URL query/referrer.
- Actuator: `/env`, `/configprops`, `/heapdump`, `/logfile`, custom error/health endpoints.
- Proxy/APM: raw headers/bodies, traces, structured logs, error reports, metrics tags.
- Kubernetes: overly broad ServiceAccount/RBAC, users permitted to read Secrets or create pods to mount them; etcd encryption not enabled.
- Secrets manager: hard-coded root/admin tokens, overly permissive workload identities, missing audits, or cross-environment access.
- Network: sending a password to a token endpoint/JWKS/DB host controlled by an attacker because TLS verification was disabled.

**Audit questions:** who generates the secret; who has read access; which storage/backups contain it; which path delivers it to the process; how long does it live; can it be revoked quickly; and who receives alerts on anomalous access?

## 5. Standard Lifecycle of an Application Secret

```text
Inventory / owner / classification
         |
         v
Generate or provision (CSPRNG, HSM, IdP, DB)
         |
         v
Store securely (version, TTL, IAM, audit)
         |
         v
Deliver to authorized workload (TLS, identity, mount)
         |
         v
Use only for intended purpose (least privilege)
         |
         v
Monitor access, expiry and failures
         |
         v
Issue version v2 -> controlled rollout -> validate v2
         |
         +-- overlap v1/v2 if backend supports it
         |
         v
Revoke v1 -> remove stale references -> audit cleanup
```

An inventory should include: secret ID/reference, environment, owner/on-call, permissions, consumers, creation time, version, last rotation, expiry/lease, dependent services, recovery steps, revocation endpoint, and incident runbook. **The inventory does not need to store the plaintext secret.**

A secret can exist in multiple **copies**: manager, secret projection volume, process heap, connection pool, cached configuration, backups, logs, and CI artifacts. Rotation is only truly complete once every consumer and copy that could still be used has been handled.

The OWASP Secrets Management Cheat Sheet emphasizes: generating sufficient randomness, least privilege, secure storage/transmission, rotation, revocation, expiration, and auditing. **Security at rest** must be paired with **control at use**.

## 6. Generating Secrets with Sufficient Entropy

For random machine credentials, use a **CSPRNG**. For example, generate 32 random bytes and hex-encode them:

```bash
# Lab command on the secrets management machine; protect terminal/stdout.
openssl rand -hex 32
```

32 bytes = 256 bits of entropy before encoding. The output has 64 hexadecimal characters, suitable as **a random token** when accepted by the protocol. Do not arbitrarily turn this value into an RSA/EC private key or certificate: asymmetric keys must be generated with a key generator/KMS/HSM matching the algorithm, key usage, key size, and policy.

**Do not use** `Math.random()`, dates, a secret written in a README, predictable strings, or a client ID as a signing key. Never commit generated values. In real production systems, prefer feeding output directly into a secret manager over a secure channel rather than copying manually via chat or an issue tracker.

For JWT HS256, the secret key must have entropy and length appropriate for the algorithm; a regular password is not a good HMAC key. For private signing keys, consider a **non-exportable** KMS/HSM key so the process never needs to hold raw private bytes.

## 7. Choosing Where to Store Secrets: Concrete Trade-offs

| Source | Strengths | Limitations |
| --- | --- | --- |
| Hard-code in Java/YAML and commit | Easy to test | **Never use for real values** |
| Uncommitted `.env` file | Convenient locally | Risks with backups, IDEs, file permissions, shared machines |
| Environment variables | Read naturally by Boot | Can leak via process inspection, debugging, dumps, and CI |
| Mounted secret file | No CLI arguments needed; clear file permissions | Pod/node access; replacing the file may not reload beans |
| Kubernetes Secret | Integrates with deployment/RBAC | Base64 is not encryption; RBAC, etcd, and exec access must be protected |
| Central secret manager | IAM, audit, versioning, leases, policies | Depends on bootstrap trust/availability |
| Dynamic DB credentials | Short TTL, easier revocation | Complex lease and connection pool management |
| KMS/HSM | Private key protected, clear key usage | Latency, authorization, SDK, and availability |
| Cloud workload identity | Reduces static secrets | Requires proper federation/trust configuration |

**Environment variables are not an absolute vault.** They are better than hard-coding in Git, but remain visible to tools and processes with appropriate privileges. **A Kubernetes Secret is not an encrypted secret vault by default** merely because it is named Secret.

Use **separate workload identities** for dev/staging/prod. A production worker reads only its own secrets and does not have permission to list all keys in a namespace or call Vault admin APIs.

## 8. Spring Boot 3.5: Externalized Configuration

Spring Boot provides PropertySources, environment variables, config imports, and configuration trees. **Illustrative** YAML example:

```yaml
spring:
  datasource:
    url: "${DB_JDBC_URL}"
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"

app:
  partner:
    client-id: "${PARTNER_CLIENT_ID}"
    client-secret: "${PARTNER_CLIENT_SECRET}"
```

This is a configuration fragment and **does not run standalone** without a JDBC driver, DB server, and client code. Do not store real passwords in these properties; `${...}` is a Spring placeholder resolved at runtime.

### 8.1. Fail-Closed Instead of Weak Defaults

Do not use:

```yaml
spring:
  datasource:
    password: "${DB_PASSWORD:password123}"
```

A production environment missing the variable would accidentally use the default password. Require the secret to be provided, validate permissions, and block startup when missing. If the app allows a feature to run without a secret, **that mode must be explicitly defined** rather than opening all endpoints automatically.

### 8.2. Mounted Config Trees

Spring Boot 3.5 officially supports:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/myapp/"
```

File tree mounted by the platform:

```text
/run/secrets/myapp/
    app.partner.client-id
    app.partner.client-secret
    spring.datasource.password
```

The file name becomes the property key, and the file content is the value. Mount read-only with appropriate filesystem permissions. `optional:configtree:/run/secrets/myapp/` is only appropriate when a missing secret directory is **valid by design**; for required secrets, fail-fast.

**Do not assume hot reload:** a secret file changing in Kubernetes or a secret manager does not mean active `@Value`, `ClientRegistration`, Hikari pool, and JWT signer beans are updated automatically. You must define the refresh mechanism, bean recreation, connection recycling, and rolling restart.

### 8.3. Property Precedence and Overrides

A value can come from application.yml, env, imported config, command-line args, and custom sources. If a production host allows untrusted users to modify command-line args or config overrides, the real secret could be replaced or redirected to another endpoint.

Do not only ask "is the secret in Vault?". Also ask "**which value is Spring actually using** and who has write access to that source?". Test configuration on a real deployment, not only in source code.

## 9. Kubernetes Secrets, Workload Identity, and Vault

A Deployment can mount a Secret via a volume:

```yaml
# Pod template excerpt, not a complete manifest.
spec:
  serviceAccountName: inventory-api
  containers:
    - name: app
      image: registry.example.com/inventory-api:stable
      volumeMounts:
        - name: secrets
          mountPath: /run/secrets/myapp
          readOnly: true
  volumes:
    - name: secrets
      secret:
        secretName: inventory-api-runtime
        defaultMode: 0400
```

**Do not** commit a manifest containing `stringData` with production values. Provision secrets through an appropriately authorized pipeline or a managed external secrets operator; restrict Secret read access, `exec` permissions, pod creation, and node access. Verify etcd encryption at rest according to your platform.

Spring Cloud Vault integrates via the Config Data API:

```yaml
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example"
```

This is only a skeleton. You need the Spring Cloud starter/BOM matching Spring Boot, Vault backend paths, CA trust, and authentication. **Do not** put a root token in YAML and call it secrets management. Use Kubernetes auth, cloud IAM, or a properly operated workload identity method; grant `read` only on the required paths, never broad `list/write/delete/admin`.

If Vault issues dynamic DB credentials with leases, design renewal/revocation and connection replacement near expiry. When Vault is unavailable, explicitly decide whether the app fails closed, uses an authorized cache, or enters a controlled degraded mode; never fall back to a hard-coded password.

## 10. DB, LDAP, SMTP, and Broker Passwords

### 10.1. Database Service Account and Connection Pool

```yaml
spring:
  datasource:
    url: "${DB_JDBC_URL}"
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"
    hikari:
      maximum-pool-size: 10
      connection-timeout: 5000
```

Each service needs a DB principal with least privilege. A read-only service does not need DDL, user creation, or server administration privileges. Protect TLS/trust certificates, network egress, and data in the connection URL; never log `jdbc:...user=...password=...`.

**Rotation is harder than changing one property**:

1. Provision v2: new user, new password, or dynamic DB lease depending on database capabilities.
2. Update consumers and establish new connections with v2.
3. Monitor active/idle pool metrics and authentication errors on new connections.
4. Wait until all instances have rolled out and scheduled jobs have switched over.
5. Revoke v1; in case of compromise, consider terminating old sessions/connections.
6. Remove old secret copies from CI, backups per policy, temporary files, and caches.

A DB may **not support two simultaneous passwords** for the same principal. Do not promise zero-downtime overlap when the backend does not allow it; two principals or a maintenance cutover may be required. Changing a password does not always close already-open connections.

### 10.2. LDAP Bind Credentials

The bind DN/password for directory lookup needs a read-only role, a narrow search base, and LDAPS/StartTLS with certificate verification. Separate **the logging-in user's password** from **the service's bind secret**. When rotating, account for directory replicas, replication delay, and every application sharing the bind account; a single company-wide shared bind account creates a large blast radius.

### 10.3. Redis, Kafka, SMTP, and Webhooks

- Dedicated Redis ACL user with restricted commands/key prefixes and network rules.
- Kafka SASL credentials with per-topic ACLs; never log `sasl.jaas.config`.
- SMTP credentials with rate limits/sending scope, never a shared admin account.
- Webhook HMAC secret to verify signatures over the raw body, timestamp, and replay window; kept separate from API authentication keys.
- Never embed secrets in URIs with userinfo/URL queries because they leak easily in access logs, metrics, HTTP redirects, and diagnostics.

## 11. OAuth2 Client Secret and Spring Security ClientRegistration

A Client ID usually only identifies the application; a client secret proves the identity of a **confidential client** at the token endpoint. A secret is **not** an access token, refresh token, or session cookie. **Never bundle a client secret into SPA JavaScript or a mobile app**: a public client cannot keep a shared secret hidden from users/attackers.

Spring Security `ClientRegistration` holds `clientId`, `clientSecret`, `clientAuthenticationMethod`, `authorizationGrantType`, and provider URLs. Spring Boot supports examples such as:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            provider: partner
            client-id: "${PARTNER_OAUTH_CLIENT_ID}"
            client-secret: "${PARTNER_OAUTH_CLIENT_SECRET}"
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope:
              - inventory.read
        provider:
          partner:
            token-uri: "${PARTNER_OAUTH_TOKEN_URI}"
```

This configuration snippet **is not enough to create a working client on its own**: it needs the OAuth2 Client dependency, token retrieval via `OAuth2AuthorizedClientManager` or a corresponding integration, a real IdP, and TLS trust. Never place a client secret in the browser.

### 11.1. Client Authentication Methods

- `client_secret_basic`: the server sends client ID/secret via HTTP Basic to the **token endpoint** over HTTPS.
- `client_secret_post`: secret in the POST body when supported by the provider; logging must be protected.
- `private_key_jwt`: the client signs an assertion with a private key; the authorization server verifies it with the registered public key.
- mTLS: the client uses a certificate/private key registered with the IdP.
- Workload identity/federation: some platforms allow avoiding long-lived client secrets.

**An OAuth client's `private_key_jwt` is not the access token signature issued by the authorization server.** The two have different subjects, audiences, keys, key owners, and flows. Switching client authentication mechanisms must be supported by the IdP and implemented compatibly, not merely by changing one line of YAML.

### 11.2. Rotating a Client Secret

If the IdP allows **two active secrets**, issue v2, update the secret store, roll out clients, verify token exchange, observe traffic, and revoke v1. If the IdP allows only **one secret**, a synchronized cutover, a new client registration, or a maintenance window is needed.

An `invalid_client` error can stem from an expired secret, mismatched client authentication method, or wrong credentials; do not retry infinitely. Rotating a client secret **does not automatically revoke already-issued access tokens**. When a client secret leaks, consider revoking tokens/refresh tokens and tightening TTLs according to IdP capabilities.

## 12. JWT Signing Keys: Private Signer vs. Public Verification

```text
Authorization Server / issuer
    |
    | private RSA/EC signing key in KMS/HSM
    | sign JWT, header kid=v2, alg=RS256/ES256
    v
Signed JWT  ----------------------> Resource Server
                                        |
                                        | Fetch public JWK from trusted issuer
                                        | Select public key by kid
                                        | Verify signature and allowed alg
                                        | Validate iss/aud/exp/nbf/scopes
                                        v
                                   Authorization
```

A Spring Security Resource Server using asymmetric JWTs **does not need the private signing key**; it uses trusted public JWK/JWKS. Public keys can be published over HTTPS, but never accept an arbitrary JWKS URL from attacker-supplied `jku`/`x5u` in the JWT header.

**Illustrative** resource server configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://idp.example.com/realms/inventory"
          jwk-set-uri: "https://idp.example.com/realms/inventory/protocol/openid-connect/certs"
```

This requires `spring-boot-starter-oauth2-resource-server`, TLS trust, and a JWT validator for API-specific audience/claims. Declaring `jwk-set-uri` alongside `issuer-uri` lets the resource server start up without waiting for the discovery endpoint to respond immediately while still checking `iss`. The JWKS URI is IdP-specific; there is no single standard path across all providers.

**Do not place the private key on a resource server just to verify.** Never publish a JWK containing an RSA private exponent, EC private scalar, or symmetric `k` in public JWKS.

### 12.1. Symmetric HS256 Keys vs. RSA/EC

HS256 is HMAC: any server that knows the secret to verify can also sign a valid MAC. If the secret is copied across many microservices, one compromised service can forge JWTs. With multiple verifiers, prefer asymmetric signatures so resource servers hold only the public key.

Do not trust the algorithm self-selected in the JWT header; explicitly configure allowed algorithms, issuer/audience, token type, and expiration. Never accept `alg=none` or algorithm-confusion fallbacks.

### 12.2. Key Rotation Using kid and JWKS Overlap

```text
T0: issuer signs with private v1, public JWKS contains v1.
T1: create private v2 in KMS/HSM, public JWKS contains v1 + v2.
T2: confirm resource servers have fetched public v2.
T3: issuer switches to signing new JWTs with kid=v2.
T4: continue accepting valid v1 tokens during overlap.
T5: after max token TTL + clock skew + JWKS cache margin,
    remove public v1, revoke/destroy private v1 per policy.
```

**If private v1 is exposed:** do not mechanically wait for tokens to expire. Handle it urgently: stop trusting v1, revoke sessions/tokens if feasible, require clients to re-authenticate, and perform an emergency JWKS update. `kid` is only a key selection identifier, not proof of trust.

Spring Security `NimbusJwtEncoder` can sign JWTs with a `JWKSource`, though a non-exportable KMS/HSM key may require a dedicated signer integration/issuer service. Never put a raw private PEM into application.yml or logs "for convenience".

### 12.3. A Signing Key Does Not Replace an Encryption Key

A JWT signature only protects authenticity/integrity; **it does not keep the payload confidential**. Encryption keys are used to decrypt data; when rotating, retain the ability to decrypt v1 ciphertext or re-encrypt data before revoking the old key. Do not delete encryption v1 while data still depends on it. Never use the same bytes for signing, encryption, TLS, and webhook MACs.

## 13. Standalone Java 17: Simulating Key Rotation Without Exposing Keys

This code uses the Java 17 JDK, generates two random 256-bit keys at runtime, signs a sample payload with HMAC-SHA256, and verifies while v1/v2 are both active and after revoking v1. **This is not JWT**; the goal is to understand trust registry/versioning/cutover. The program does not print raw keys.

Save as `KeyRotationDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class KeyRotationDemo {

    record Signature(String kid, byte[] value) {}

    static byte[] hmac(byte[] key, byte[] payload)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(payload);
    }

    static boolean verify(
            Map<String, byte[]> active,
            Signature signature,
            byte[] payload) throws GeneralSecurityException {
        byte[] key = active.get(signature.kid());
        return key != null && MessageDigest.isEqual(
            hmac(key, payload), signature.value());
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        SecureRandom rng = new SecureRandom();
        byte[] v1 = new byte[32];
        byte[] v2 = new byte[32];
        rng.nextBytes(v1);
        rng.nextBytes(v2);

        byte[] data = "example-event"
            .getBytes(StandardCharsets.UTF_8);

        Map<String, byte[]> trusted = new HashMap<>();
        trusted.put("v1", v1);
        trusted.put("v2", v2);

        Signature oldSig = new Signature("v1", hmac(v1, data));
        Signature newSig = new Signature("v2", hmac(v2, data));

        System.out.println("v1 during overlap: "
            + verify(trusted, oldSig, data));
        System.out.println("v2 during overlap: "
            + verify(trusted, newSig, data));

        trusted.remove("v1");

        System.out.println("v1 after revoke: "
            + verify(trusted, oldSig, data));
        System.out.println("v2 after revoke: "
            + verify(trusted, newSig, data));

        Arrays.fill(v1, (byte) 0);
        Arrays.fill(v2, (byte) 0);
    }
}
```

Compile and run:

```bash
javac --release 17 KeyRotationDemo.java
java KeyRotationDemo
```

Exact stdout even though the key bytes are randomly generated:

```text
v1 during overlap: true
v2 during overlap: true
v1 after revoke: false
v2 after revoke: true
```

**Explanation:** during overlap, the verifier accepts both v1 and v2; after revocation, v1 is rejected. In an asymmetrically signed JWT system, the issuer holds **private keys** and the verifier receives **public keys**, rather than sharing a secret byte array as in this HMAC example. `Arrays.fill` only clears the two arrays owned by the code; it does not guarantee that every copy in the JVM or native crypto provider has been wiped.

## 14. Spring Boot 3.5.16 and Java 17: Reading Secrets from the Environment

A small project demonstrating that the password **is not in source code**, startup **fails if a required password is missing**, and HTTP responses do not disclose secrets. It uses HTTP Basic for a **localhost lab**, not as a production IAM solution. Outside localhost, HTTP Basic must use proper TLS; Basic credentials are only base64-encoded, not encrypted.

### 14.1. Project Structure

```text
secret-injection-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/secret/SecretInjectionApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/demo/secret/SecretInjectionApplicationTests.java
```

### 14.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>secret-injection-demo</artifactId>
    <version>1.0.0</version>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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
```

### 14.3. application.yml

```yaml
server:
  port: 8080

app:
  demo:
    operator: "${DEMO_OPERATOR:operator}"
    password: "${DEMO_OPERATOR_PASSWORD}"
```

No weak default password. For a mounted-files variant, you can use configtree instead of env, but unprovided placeholders must be removed/adjusted and property precedence properly tested. Never mix two injection paths without knowing which source wins.

### 14.4. SecretInjectionApplication.java

```java
package demo.secret;

import java.security.Principal;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SecretInjectionApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecretInjectionApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${app.demo.operator}") String operator,
            @Value("${app.demo.password}") String password) {
        if (password == null || password.length() < 20) {
            throw new IllegalStateException(
                "Required demo operator secret is missing or short");
        }

        UserDetails operatorUser = User.withUsername(operator)
            .password(encoder.encode(password))
            .roles("OPERATOR")
            .build();
        return new InMemoryUserDetailsManager(operatorUser);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .requestMatchers("/private/**").hasRole("OPERATOR")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .build();
    }

    @GetMapping("/health")
    Map<String, String> health() {
        return Map.of("status", "up");
    }

    @GetMapping("/private/me")
    Map<String, String> me(Principal principal) {
        return Map.of("principal", principal.getName());
    }
}
```

**Intentional design choices:**

- The password value is injected from an external property; never printed to logs/JSON.
- The bean refuses startup if the password is missing or too short per the **demo** policy. That is not a rule for all user passwords in NIST.
- The demo password is BCrypt-hashed when building `UserDetails` to verify credentials, never stored in plaintext in the user store.
- `/private/**` still requires `ROLE_OPERATOR`; obtaining a secret should not automatically grant business permissions across all paths.
- Stateless Basic authentication checks credentials on every request; never use Basic outside TLS in a real environment.
- The code has no mutation endpoints. If adding a browser POST with Basic credentials, CSRF must still be evaluated because browsers may automatically send cached credentials.
- The bean is created at startup. **Rotating the password in the secret manager does not automatically update the active BCrypt verifier**; a refresh/recreate or rollout is required.
- A `String` secret can remain in the JVM heap; an application cannot guarantee absolute zeroization. For critical secrets, prefer managed credentials/KMS.

### 14.5. Running Locally

```bash
# Bash/Linux/macOS; use only a random secret for this lab.
export DEMO_OPERATOR='operator'
export DEMO_OPERATOR_PASSWORD="$(openssl rand -hex 24)"
mvn spring-boot:run
```

If using PowerShell, set environment variables via `$env:DEMO_OPERATOR` and `$env:DEMO_OPERATOR_PASSWORD` with the corresponding syntax. Never copy a production secret into a lab terminal.

In another terminal:

```bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/private/me
curl -i --user operator http://localhost:8080/private/me
```

The last command prompts interactively for the password; never pass a raw password as a command-line argument because process listings/shell history may retain it. Expect `/health` to return 200 with `{"status":"up"}`, anonymous `/private/me` to return 401, and correct Basic credentials to return 200 with `{"principal":"operator"}`. A wrong password returns 401. If the env secret is missing at startup, the application fails rather than enabling anonymous access.

## 15. MockMvc: Testing Fail-Closed and No-Leak Behavior

Create `src/test/java/demo/secret/SecretInjectionApplicationTests.java`:

```java
package demo.secret;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "app.demo.operator=operator",
    // Synthetic string for testing only, not a production secret.
    "app.demo.password=synthetic-test-only-credential-123456"
})
@AutoConfigureMockMvc
class SecretInjectionApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicHealthIsAvailable() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("up"));
    }

    @Test
    void anonymousCannotReadProtectedResource() throws Exception {
        mvc.perform(get("/private/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongCredentialIsRejected() throws Exception {
        mvc.perform(get("/private/me")
                .with(httpBasic("operator", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void correctCredentialReturnsOnlyIdentity() throws Exception {
        mvc.perform(get("/private/me")
                .with(httpBasic(
                    "operator",
                    "synthetic-test-only-credential-123456")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("operator"))
            .andExpect(jsonPath("$.password").doesNotExist());
    }
}
```

Run `mvn test`. Expect **4 passing tests** given matching dependencies and environment; this is a prediction from the code, not an actual Maven run result. The test fixture uses a **synthetic** value, with no production secret in source code.

Add separate tests for startup **missing the property**, deployment RBAC denying access to other workloads' secrets, Vault/token endpoint downtime, v1/v2 rotation, log redaction, and JWKS caching. MockMvc **does not prove** that Kubernetes Secret ACLs or KMS policies are secure.

## 16. Rotation and Downtime: No One-Size-Fits-All Approach

### 16.1. General Workflow

```text
Inventory dependencies, owner, TTL, and rollback constraints
   |
Create/provision v2
   |
Deploy v2 to consumers (secret manager, configs, pods)
   |
Test new DB connections / OAuth token exchange / JWT validation
   |
Overlap v1 and v2 if supported; monitor old-version use
   |
Revoke v1, terminate stale connections if required
   |
Audit, clean backups/caches, close change
```

**Do not revoke v1 before verifying that consumers have switched to v2**, except when secret exposure requires emergency containment and service impact is accepted.

| Secret | Rotation Specifics |
| --- | --- |
| DB password | May need a second user/dual passwords; Hikari pool retains old connections |
| LDAP bind password | Replication, account policies, apps sharing the bind account |
| OAuth client secret | Does the provider allow overlapping active secrets? Old access tokens may remain valid |
| JWT signing key | Publish public v2 first; signer switches kid; retain public v1 until v1 JWTs expire |
| JWT HS256 secret | All verifiers hold the shared secret; distribute v2 everywhere before signer switches |
| Encryption key | Must decrypt legacy data and re-encrypt before destroying v1 |
| TLS certificate/private key | Trust chain, SAN, expiry, OCSP/CRL/certificate policy |
| Webhook HMAC | Key version, signed raw body, and replay window |
| Session signing key | Existing cookies/session tokens may be invalidated immediately if key is removed |

### 16.2. Verifying Readiness Before Revocation

- All pods and batch jobs have loaded v2.
- Fresh DB connections use v2 credentials, not merely existing open connections.
- `invalid_client`, DB auth failures, JWKS kid misses, and 401/5xx errors do not spike abnormally.
- The JWT issuer mints tokens with `kid=v2`, and all resource servers verify v2 tokens.
- Public JWKS retains v1 during the overlap while v1 tokens remain valid.
- Rollback plans do not automatically revert the app to a revoked v1.
- Version/age/access metadata is reported, **without logging plaintext or sensitive fingerprints**.

## 17. When a Secret Is Exposed: Incident Response

**Revoking/rotating at the issuing source is the decisive step.** Deleting a line from Git does not invalidate an exposed secret.

Procedure:

1. Identify the secret type, version, permissions, and leak source (Git, logs, CI, dumps, Vault, device).
2. Contain the attacker: revoke the exposed credential/key, restrict network/IAM, issue a new secret if appropriate.
3. Determine blast radius: data, tokens/sessions, service accounts, downstream resources, and third parties.
4. Update consumers, measure auth failures, invalidate stale pools/caches/sessions per the threat model.
5. If a private signing key leaked, consider **stopping trust in all tokens signed with the old key**, logout/re-authentication, and an emergency JWKS update.
6. If a DB password leaked, evaluate existing connections and queries that occurred, not just changing the password.
7. Scan Git history, forks, artifacts, backups, central logs, and CI; handle copies and permissions per retention policy.
8. Preserve evidence under control; audit secret reads, the incident timeline, and suspicious behavior.
9. Add scanning, least privilege, shorter TTLs, workload identity, and runbooks.
10. Notify security owners/customers according to policy and applicable legal obligations.

**Never paste raw secrets into tickets or chat for investigation.** Use the secret reference/version, environment, timestamp, and a protected correlation ID.

## 18. Observability, Actuator, and CI/CD

Never log:

- full `System.getenv()` or `@ConfigurationProperties.toString()` containing secrets;
- `Authorization`, `Cookie`, `X-API-Key`, OAuth refresh/access tokens, CSRF tokens, private PEMs;
- SQL/JDBC connection URLs containing passwords, Kafka JAAS config, SMTP credentials;
- raw token endpoint requests/responses, redirect queries containing codes/tokens;
- session IDs, heap dumps, and config files via publicly exposed Actuator endpoints.

Actuator provides sanitization mechanisms for some endpoints, but **that is no excuse to expose `/actuator/env`, `/configprops`, `/heapdump`, or `/logfile` publicly**. Enforce authentication/authorization, egress, retention, and support access, and verify with real tests.

Safe logging prefers **metadata**:

```text
event=SECRET_ROTATION_COMPLETED
secret_ref=prod/inventory/oauth-client
version=v2
consumer=inventory-api
result=SUCCESS
correlation_id=rotate-4382
```

This is a sample log format, not default Spring output. A fingerprint of a weak password can enable offline guessing; if a version ID from the secret manager exists, prefer the version ID.

For CI/CD:

- Secret scanning on pre-commit/PR/pipeline and when auditing Git history.
- Never bake secrets into container images or build artifacts.
- Inject secrets only into the job that uses them, with a least-privileged, short-lived CI identity.
- Never pass passwords in command-line args, URLs, or shell traces.
- Never enable HTTP wire logging containing headers/tokens in production.
- Use workload identity/OIDC federation instead of static CI tokens whenever possible.
- Test rollback and emergency rotation runbooks.

## 19. Common Failure Matrix

| Symptom | Cause | Remediation |
| --- | --- | --- |
| App fails to resolve `DB_PASSWORD` | Secret not injected or wrong property precedence | Verify secret reference/identity, fail-closed; no weak defaults |
| DB login fails after deploy | App/DB version mismatch | Check pool and fresh connections, rotate in order |
| DB keeps working with revoked password | Old connections not closed | Recycle/terminate when required |
| OAuth token endpoint returns `invalid_client` | Wrong/expired secret or auth method mismatch | Reconcile IdP registration and v2 |
| Client secret changed but old access tokens still work | Token expiry/revocation is separate from client secret | Manage token lifecycle separately |
| JWT v2 rejected | JWKS cache lacks `kid=v2`, wrong issuer/aud/alg | Publish public v2 first, check validation |
| JWT v1 rejected too early | Removed public v1 before token TTL | Keep overlap if not compromised |
| Key appears in public JWKS | Accidentally published private JWK or symmetric key | Treat as incident, revoke/rotate immediately |
| Kubernetes Secret changed but app ignores it | Bean/pool read only at startup | Rolling restart/refresh the right resource |
| Actuator exposes connection password | Endpoint/config sanitization misconfigured | Restrict Actuator, revoke key, and audit |
| Password leaked via build logs | Shell echo/debug or tool printing env | Redact, restrict pipeline, revoke |
| Local fallback secret runs in prod | Weak default value used | Remove fallback, add startup validation |
| One service reads multiple teams' secrets | Overly broad IAM/RBAC | Workload-specific policy |
| Signing key leaked at resource server | Private key distributed to all verifiers | Use asymmetric public verification, rotate |
| Key v1 revoked but rollback needs v1 | Old release embeds old credential | Build v2-compatible rollback |
| Token URI taken from untrusted request | Credential exfiltration/SSRF | Pin endpoints and TLS trust |

**Diagnostic sequence:** secret source → workload permissions → version/expiry → TLS endpoint → app reload/pool → Spring Security client/JWT validation → redacted logs → incident policy.

## 20. Production Implementation Checklist

- [ ] Complete inventory of all DB/LDAP/broker/OAuth/JWT/TLS/API/webhook secrets with owners and rotation runbooks.
- [ ] Never share one secret across multiple environments or multiple purposes.
- [ ] No production secrets in Git, CI artifacts, images, logs, heap dumps, or Actuator responses.
- [ ] Secrets provisioned by CSPRNG/KMS/IdP with proper mechanism, entropy, and key usage.
- [ ] Workload IAM reads only its own secrets; no Vault root token in the app.
- [ ] Proper TLS verification and outbound endpoint allowlists.
- [ ] Spring Boot property sources controlled; missing secret → fail-closed.
- [ ] Mounted file/config tree not mistaken for automatic hot reload.
- [ ] DB/LDAP connections rotated alongside connection pools and job consumers.
- [ ] OAuth client secret kept distinct from access tokens, confidential server-side only.
- [ ] JWT issuer holds private signing keys; resource servers hold only public JWKS.
- [ ] JWT rotation includes kid, public-key overlap, TTL, cache margin, and emergency revocation.
- [ ] Encryption key rotation includes a plan to re-encrypt/decrypt legacy data.
- [ ] Incident response tested for exposed secrets, including Git history/backups.
- [ ] Telemetry tracks secret versions without disclosing secrets.
- [ ] Tested for wrong/expired/missing secrets, ACLs, key rotation, rollback, and KMS/Vault failures.

## 21. Self-Check Questions

1. Why is a **client ID** not a **client secret**?
2. Why are user passwords stored as hashes while service passwords may require a recoverable secret store?
3. Is Kubernetes Secret base64 encoding encryption?
4. Does replacing a secret file in Kubernetes automatically reload a `@Value` bean?
5. How does `private_key_jwt` for client authentication differ from a JWT access token signature?
6. Does a resource server need the private RSA signing key to verify JWTs?
7. Why must public v2 be published before the signer signs JWTs with v2?
8. Is `kid` enough to trust a JWT from an unverified issuer?
9. When can public v1 be removed after a normal rotation?
10. When private v1 is exposed, should you wait for JWT TTL expiration or perform an emergency revocation?
11. Why does changing a DB password not always close existing connections?
12. Does changing an OAuth client secret revoke already-issued access tokens?
13. Should a client secret ever be placed in an SPA/mobile bundle?
14. Why should you not share a single HMAC key across all microservices?
15. Does rotating an encryption key require handling legacy ciphertext?
16. If a required secret is missing at startup, what is the safe behavior?
17. Should you log the hash/fingerprint of every password for debugging?
18. Why does deleting a secret in a new commit not resolve a secret leak?
19. What makes workload identity better than long-lived static secrets in some environments?
20. Does a passing MockMvc test prove Vault RBAC or Kubernetes volume ACLs are secure?

## 22. Official References

- Spring Boot 3.5 – Externalized Configuration and Configuration Trees: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot – OAuth2 Client Configuration: https://docs.spring.io/spring-boot/reference/security/oauth2.html
- Spring Security 6.5 – OAuth2 ClientRegistration: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/core.html
- Spring Security – OAuth2 Resource Server JWT/JWKS: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security – NimbusJwtEncoder API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusJwtEncoder.html
- Spring Security – Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Cloud Vault – Quick Start: https://docs.spring.io/spring-cloud-vault/reference/quickstart.html
- Spring Cloud Vault – ConfigData API: https://docs.spring.io/spring-cloud-vault/reference/config-data.html
- OWASP – Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP – Key Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html
- OWASP – Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- NIST SP 800-63B-4 – Authentication and Passwords: https://pages.nist.gov/800-63-4/sp800-63b.html
- RFC 7517 – JSON Web Key (JWK): https://www.rfc-editor.org/rfc/rfc7517
- RFC 7518 – JSON Web Algorithms (JWA): https://www.rfc-editor.org/rfc/rfc7518
- RFC 8725 – JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725

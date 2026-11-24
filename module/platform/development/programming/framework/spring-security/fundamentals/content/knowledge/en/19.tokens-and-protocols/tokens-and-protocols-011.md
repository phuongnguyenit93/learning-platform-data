# API Keys and the Limits of Using One Key to Represent an Application or User

> **Module:** Spring Security – Fundamentals  
> **Knowledge group:** Tokens and Protocols  
> **Focus:** To what extent an API key is a credential identifying a client, integration, or workload; why it is usually **insufficient to represent an end user**; and how to design authentication, authorization, permission scopes, key management, and testing when integrating with Spring Security.

## 1. Learning Objectives

Upon completing this lesson, you will be able to:

1. Explain what an API key is and how it differs from session cookies, HTTP Basic passwords, OAuth2 access tokens, and JWTs.
2. Distinguish **credential**, **client identity**, **user identity**, **tenant**, **scope/authority**, and **per-resource permissions**.
3. Identify what a valid API key **can prove** and what it **cannot prove**.
4. Recognize the risks of sharing one key across multiple applications, employees, devices, or customers: loss of traceability, overly broad permissions, and difficult revocation.
5. Design high-entropy keys, separate secrets from key IDs, store hashes, set expirations, enforce least privilege, rate limit, audit, and rotate keys.
6. Understand how to integrate API keys into Spring Security with a **custom authentication filter**, building an `Authentication` with clear principal and authorities, then checking authorization at HTTP and domain layers.
7. Run a Java 17+ example and test valid keys, invalid keys, insufficient permissions, cross-tenant access, and missing keys.

## 2. What Is an API Key?

An **API key** is a secret string or credential issued by a service to an API caller. The caller presents the key on each request per an agreed protocol, typically via an HTTP header. The service matches the key against a configuration record or key store to determine **which client is calling**, which plan/quota applies, and which operations are permitted.

Example:

~~~http
GET /api/records/101 HTTP/1.1
Host: api.example.test
X-API-Key: <secret-api-key>
~~~

`<secret-api-key>` is an illustrative placeholder, not a real key. **Do not put keys in URL query strings**, because URLs are easily recorded in proxy logs, browser history, analytics, referers, or monitoring systems. Prefer headers or standard credential mechanisms specified by the API provider.

API keys can be used to:

- Identify a service-to-service integration, e.g., a reporting service calling an internal API.
- Associate customers/partners with quota tiers or commercial plans.
- Partition permissions by workload, project, environment, or tenant.
- Monitor traffic per client and proactively revoke if leaked.
- Provide simple machine-to-machine authentication when risk and scope are appropriate.

**An API key is not by itself a user login system.** A backend receiving a key can recognize "the request was sent with the credential issued to integration A"; it **does not inherently know** "an end user named Alice clicked this button" or "Alice consented for integration A to act on her behalf".

### Accurate Reasoning Model

~~~text
Request sends key K
    |
    v
Server verifies K is valid, unexpired, and unrevoked
    |
    v
Server looks up metadata:
  clientId    = reporting-job
  tenantId    = north
  authorities = [RECORD_READ]
    |
    v
Authentication: principal = client:reporting-job
    |
    v
Authorization: does client have RECORD_READ?
               does record belong to tenant north?
    |
    v
ALLOW or DENY
~~~

In this example, the principal is a **service account / client identity**, not a human being. Even if an employee generated the API key, using that key does not prove that employee initiated the current request.

## 3. What Can an API Key Prove, and What Can It Not Prove?

### What It Can Prove (If Designed Properly)

A request carrying a valid key shows that the sender **is able to present the credential** issued to a specific client or workload. After server-side lookup, the backend knows:

- `clientId` or `serviceAccountId` bound to the key;
- granted tenant/project/environment;
- key state: active, disabled, revoked, expired;
- permission scopes granted to the credential;
- quotas, rate limits, and related operational policies.

These depend on **the server storing metadata and actually checking it**. A random string with no associated policy does not automatically confer any of these capabilities.

### What Cannot Be Proven from the Key Alone

1. **Who is directly acting?** Many employees may know the same key.
2. **Which application is executing?** A copied key can be used by another program or an attacker.
3. **Has the end user authenticated?** A key issued to a backend carries no user login process.
4. **Did the user consent to delegation?** Holding a key does not prove user consent.
5. **Can it access every record in the organization?** A client with `RECORD_READ` can still be restricted by tenant, owner, classification, or processing purpose.
6. **Is the request integrity-protected or replay-resistant?** An API key sent raw is a bearer secret; anyone obtaining the key can try replaying it.
7. **Is the sender authorized to act on the user's behalf right now?** Locked accounts, revoked user permissions, or transactions requiring MFA are independent conditions.

**Question to ask during system reviews:** "Does this API key represent an **application**, a **service account**, or a **user**? What is the trusted source of that claim?" Without a clear answer, authorization easily goes wrong.

## 4. One Shared Key Erases Identity Boundaries

Suppose the "Sales Dashboard" app has one shared key stored in the code of 30 employees:

~~~text
Employee Alice --+
Employee Bob -----+--> X-API-Key: SALES_TEAM_KEY --> Data API
Employee Carol ---+
~~~

The backend receives the exact same credential. Without an independent user authentication mechanism, the API knows the key belongs to the Sales team, yet **cannot tell whether Alice, Bob, or Carol sent the request**.

Consequences:

- **No user-level action traceability.** Audit logs record `key_id=sales-team-key`, not who made the decision.
- **No individual revocation.** When Bob leaves, the team must rotate everyone's key or leave Bob able to use his old copy.
- **No per-user permission differences.** Alice may read all customers while Bob may read only his own, yet the shared key enforces one policy.
- **Large blast radius.** Leaking the key on one machine exposes all data within the key's scope.
- **Easily becomes "disguised admin access".** Broadly scoped API keys created for integration convenience get used in place of user authentication.
- **Hard to separate abuse from normal traffic.** Rate limits, quotas, and alerts per key mix traffic from many sources.

The fix is not simply "adding an `X-User-Id` header", because clients can fill in any user ID they want. You need **user authentication at a trusted boundary**, or delegation tokens issued by a valid identity/authorization system.

### Comparing Three Designs

| Design | Trusted Principal | Best Suited For |
| --- | --- | --- |
| One shared API key for an entire team | One client/team, **not individual employees** | Poor fit for per-user permissioned operations |
| Dedicated API key per integration/workload | Service account for each workload | Service-to-service, quotas, per-client auditing |
| User login + OAuth2 delegated access token | User subject and client identity from trusted issuer | Acting on a user's behalf with scopes, consent, expiry |

Some systems issue a **personal API key** per user. That maps back to the owning account in the database, yet still **does not prove the person holding the key is the user at call time**. Personal API keys are typically long-lived credentials that can be copied or shared; they should have dedicated permissions, lifetimes, and revocation, not be equated with MFA or recent interactive login.

## 5. Authentication Differs from Authorization

- **Authentication:** is the key valid? If so, **which client/service account** is the principal?
- **Authorization:** is that client permitted to invoke this action, on this resource/tenant, in its current state?

A common flaw:

~~~text
if (apiKeyExists(requestKey)) {
    return repository.findById(requestedId); // dangerous
}
~~~

A valid key does not mean reading every ID. If `requestedId` belongs to another tenant, missing owner/scope/tenant checks create a **Broken Object Level Authorization (BOLA/IDOR)** vulnerability.

Proper design:

~~~text
verified = credentialStore.verify(requestKey)
if verified invalid/expired/revoked -> deny
if REPORT_READ not in verified.scopes -> deny
record = repository.findByIdAndTenantId(requestedId, verified.tenantId)
if absent -> deny/not found per policy
return permitted projection
~~~

The pseudocode highlights checking **tenant from verified metadata**, never taking tenant from an HTTP header freely editable by clients. If a server permits one integration to access multiple tenants, that scope must also be explicitly bound and audited.

## 6. API Keys Compared to Other Authentication Mechanisms

| Mechanism | Credential Presented in Request | Typical Principal | Strengths | Limitations |
| --- | --- | --- | --- | --- |
| API key | Secret string, usually via custom header | Client/service account, occasionally key-owning user | Simple, easy to issue for integrations | Lacks built-in delegation, user consent, standard scopes/expiry |
| HTTP Basic | Username/password in `Authorization` | User or service account | Simple HTTP standard | Long-lived credentials sent every request; requires TLS |
| Cookie + server session | Session ID | User from server session | Browser-friendly, session revocation | Requires session management, cookie/CSRF defenses |
| OAuth2 client credentials | Access token from authorization server | Client application/service account | Token issuance, scopes, lifetimes, centralized policy | **No end user** in client credentials flow |
| OAuth2 delegated access token | Access token with user subject/client context per issuer | User + authorized client | Fits user consent, audience/scopes/expiry | Requires AS/resource server and standard validation |
| JWT | Signed/MACed JSON token format | Depends on claims/issuer | Can validate offline by design | JWT is a **format**, does not prove permissions/issuer/audience on its own |
| mTLS client certificate | Client certificate in TLS handshake | Client/workload holding certificate | Bound to private key/cert, machine identity management | PKI operations, rotation, proxy/trust-chain complexity |

**OAuth2 client credentials is not user delegation either.** It may suit static keys better when short-lived access tokens, issuer/audience/scopes, and rotation are needed. To act "on Alice's behalf", you need a proper user login and delegation flow, not simply issuing a key named Alice.

API keys are usually bearer credentials: anyone holding the key can use it within its scope. Do not label a custom string `Authorization: Bearer` and assume it satisfies all of OAuth2; define validators and semantics explicitly.

## 7. Design Principles for API Key Credentials

### 7.1. Generate High-Entropy Keys

Secrets must come from a **cryptographically secure random number generator** (CSPRNG), not usernames, timestamps, or predictable UUID schemes. For server-to-server keys, generate 32 random bytes (256 bits) and encode in hex or base64url.

Illustrative shell example:

~~~bash
openssl rand -hex 32
~~~

The command prints a random key to stdout. **Never copy real keys into documentation, chats, or source code.** Store them in an appropriate secret manager; when generating on a workstation, watch out for shell history, terminal recordings, and clipboard exposure.

### 7.2. Separate Public Key ID and Secret

Common design:

~~~text
ak_live_<public_key_id>_<random_secret>
~~~

This is a **conceptual format**, not a universal standard. `public_key_id` lets the server look up records quickly; `random_secret` is the portion that must stay secret. Never treat the key ID as a secret.

Example metadata store:

~~~text
key_id       = k_1042
client_id    = orders-worker
tenant_id    = north
environment  = production
scopes       = RECORD_READ
secret_hash  = <digest-or-keyed-digest>
created_at   = ...
expires_at   = ...
revoked_at   = null
last_used_at = ...
~~~

For high-entropy tokens, the server can store a SHA-256 digest of the secret for comparison, or a keyed HMAC digest with a server-side pepper per security design. Small/guessable keys do not become safe merely by hashing with SHA-256; increase entropy, enforce rate limits, and consider a KDF if the threat model demands it.

**Display the raw key once at issuance**, and do not provide a "view old secret again" endpoint unless strictly required. Rotation should generate a new key.

### 7.3. Dedicated Keys per Client, Environment, and Purpose

Never share one production key across staging, cron jobs, mobile apps, partner systems, and employees. Each workload should have an independent identity for revocation and auditing.

A naming convention:

~~~text
client:inventory-sync-prod
client:analytics-export-staging
client:crm-partner-42
~~~

Names are public metadata, not secrets. Use specific authorities like `INVENTORY_READ` or `REPORT_EXPORT`. Never default service-account keys to `ROLE_ADMIN`.

### 7.4. Scope, Tenant, Resource, Quota

Grant **least privilege** permissions:

~~~text
Key K1: client=report-bot, tenant=north, scopes=[RECORD_READ]
Key K2: client=inventory-sync, tenant=south, scopes=[STOCK_READ, STOCK_UPDATE]
Key K3: client=billing-reconcile, scopes=[INVOICE_RECONCILE], no human access
~~~

Beyond route-level permissions, enforce resource-level checks: if key K1 calls `/api/records/201` belonging to tenant `south`, deny it even though K1 has `RECORD_READ`.

Rate limits/quotas should be tracked per client/key and combined with IP, tenant, endpoint cost, and concurrency. They reduce abuse yet **do not replace authentication or authorization**. Over-limit requests can return `429 Too Many Requests` per policy, not `401` or `403`.

### 7.5. Expiration, Revocation, Rotation

Every key should have a lifecycle:

~~~text
CREATED -> ACTIVE -> ROTATING -> REVOKED / EXPIRED
~~~

Safe rotation process:

1. Issue a new key with equivalent/minimal scopes.
2. Distribute via secret manager or secure channel.
3. Deploy callers using the new key.
4. Monitor logs/metrics by key ID (never log the secret).
5. Revoke the old key after the necessary overlap window.
6. Verify the old key is rejected.

When compromise is suspected, support **immediate revocation** and investigate impact scope. Never expect that deleting a key from Git history alone invalidates an exposed credential. With cached verification, ensure invalidation/TTL is short enough for revocation to take effect per security targets.

### 7.6. Secure Storage and Transport

- TLS is mandatory; keys in plaintext HTTP can be intercepted in transit.
- Pass in `X-API-Key` or `Authorization` per contract, **never** in query strings.
- Never log headers containing keys, nor record them in APM traces, analytics, screenshots, or bug reports.
- Avoid hardcoding keys in mobile apps or SPAs distributed to end users: anyone holding the file/app can extract the key.
- Use secret managers, workload identities, environment injection, or suitable credential issuance mechanisms.
- Never trust `X-User-Id` or `X-Tenant-Id` from the Internet as authenticated proof. Trust only verified identities or headers signed/set by trusted proxies across clear trust boundaries.
- Consider mTLS, IP restrictions, signed requests with timestamps/nonces, or short-lived tokens when replay risk is high; each control carries its own operational requirements.

## 8. Common Design Mistakes Matrix

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| One shared key for the entire company | Cannot separate clients/users; hard to revoke | Separate key per workload/partner/tenant |
| Putting user ID in a header and trusting it | Callers can impersonate any user | Use trusted user authentication/delegation |
| Valid key means reading all resources | BOLA/IDOR, cross-tenant disclosure | Check scope + tenant + object-level authorization |
| Key in URL/query string | URLs are routinely logged/recorded in history | Use headers; mask secrets in logs |
| Key in browser JS/mobile app | Credentials can be extracted | Backend proxy or user-based auth flow |
| No expiry/revocation | Lost keys suffer prolonged abuse | Lifecycle, revocation, rotation |
| Short/guessable keys | Brute force / guessing | High-entropy CSPRNG |
| Hashing weak keys and calling it safe | Hashing adds no entropy to weak secrets | Generate strong keys, rate limit |
| Comparing secrets with naive string operations | Potential timing/logic leaks | Proper constant-time digest comparison |
| Logging raw keys | Increases account-takeover probability | Redact; log key ID and controlled metadata |
| No rate limits/quotas | Valid keys can exhaust resources | Limits per key, tenant, endpoint cost |
| Treating a key as MFA or human verification | Lacks proof-of-user | Login/step-up when needed |
| Returning overly detailed errors | Leaks key/username existence | Error contract revealing no secret details |
| Granting ADMIN everywhere | Large blast radius | Least privilege, explicit scopes |
| Caching revoked keys too long | Old tokens keep working | Revocation propagation / short TTL |
| Reading client ID from body instead of key | Trivial identity spoofing | Principal from verified credential |

## 9. Integrating with Spring Security: No "Magical User Permissions" from a Key

In Spring Security Servlet, authorization relies on `Authentication`, typically containing:

- `principal`: verified identity—here, a client/service account;
- `authorities`: permissions granted to the identity;
- `credentials`: secret received in the request; **do not retain the raw key after verification**;
- `isAuthenticated`: authentication state.

API key integration generally requires an explicit authentication mechanism, such as a custom filter or `AuthenticationFilter` + `AuthenticationConverter` + `AuthenticationProvider`, rather than assuming Spring Security automatically understands arbitrary `X-API-Key` headers.

Flow:

~~~text
HTTP GET /api/records/101
  X-API-Key: <secret>
      |
      v
ApiKeyAuthFilter (Servlet)
      |
      +-- missing --> no Authentication yet --> rule requires login --> 401
      |
      +-- invalid/expired/revoked --> 401, controller never runs
      |
      +-- valid --> ApiPrincipal(clientId, tenantId)
                   authorities=[RECORD_READ]
                         |
                         v
                SecurityContextHolder
                         |
                         v
                AuthorizationFilter:
                hasAuthority("RECORD_READ")?
                         |
                         v
                Controller / Service / Repository:
                record.tenantId == principal.tenantId?
                         |
                    allow / deny
~~~

**Note:** Authentication happens first, authorization second. `hasAuthority("RECORD_READ")` only checks action-level permission; actual tenant/owner boundaries must still be enforced at the domain/data layer.

## 10. Runnable Java 17+ Demo with Spring Boot 3.5.x

The demo application accepts **a single dedicated API key for service `client:reporting-job`** belonging to tenant `north`, with only `RECORD_READ`. It uses the `X-API-Key` HTTP header. The demo intentionally has no user login, making clear that the key identifies the **client**, not an employee.

Behavior:

- `GET /api/public`: accessible to anyone.
- `GET /api/whoami`: requires a valid key; returns the verified client ID + tenant.
- `GET /api/records/101`: valid key with `RECORD_READ` scope reads the `north` tenant record.
- `GET /api/records/201`: valid key, yet belongs to `south` tenant so not found within scope (404 per demo policy).
- `POST /api/records`: read-only key returns 403.
- Missing/invalid key: protected endpoints return 401.

**Warning:** This sample uses one environment-configured key to illustrate the authentication pipeline. It **is not a production key-management system**: there is no multi-key database, dynamic revocation, quota, audit, key-prefix rotation, or mTLS. Those aspects are covered in subsequent sections.

### 10.1. Project Structure

~~~text
api-key-demo/
  pom.xml
  src/main/java/com/example/apikey/
    ApiKeyDemoApplication.java
    ApiPrincipal.java
    ApiKeyRegistry.java
    ApiKeyAuthFilter.java
    SecurityConfig.java
    ApiRecordStore.java
    ApiController.java
  src/test/java/com/example/apikey/
    ApiKeySecurityTests.java
~~~

Requires **JDK 17+**, **Maven 3.9+**, Spring Boot **3.5.7** (Servlet/Spring MVC). Examples target the Spring Security 6.5 line; when upgrading Spring Boot/Spring Security, consult the target version's migration guide.

### 10.2. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
~~~

### 10.3. File `ApiKeyDemoApplication.java`

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

### 10.4. File `ApiPrincipal.java`

~~~java
package com.example.apikey;

import java.security.Principal;

public record ApiPrincipal(String clientId, String tenantId)
        implements Principal {

    @Override
    public String getName() {
        return clientId;
    }
}
~~~

Because `ApiPrincipal` implements `Principal`, `Authentication.getName()` reflects the client ID; it **is not a username**. Tenant ID here comes solely from the trusted key registry.

### 10.5. File `ApiKeyRegistry.java`

~~~java
package com.example.apikey;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Optional;
import java.util.Set;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ApiKeyRegistry {

    public record KeyIdentity(
        String clientId,
        String tenantId,
        Set<String> authorities
    ) {}

    private final byte[] expectedDigest;

    public ApiKeyRegistry(Environment environment) {
        String key = environment.getProperty("DEMO_API_KEY");

        if (key == null || key.length() < 24) {
            throw new IllegalStateException(
                "Set DEMO_API_KEY to a random 24+ character demo secret"
            );
        }
        this.expectedDigest = sha256(key);
    }

    public Optional<KeyIdentity> verify(String candidate) {
        if (candidate == null
                || candidate.isBlank()
                || candidate.length() > 512) {
            return Optional.empty();
        }

        byte[] receivedDigest = sha256(candidate);
        if (!MessageDigest.isEqual(expectedDigest, receivedDigest)) {
            return Optional.empty();
        }

        return Optional.of(new KeyIdentity(
            "client:reporting-job",
            "north",
            Set.of("RECORD_READ")
        ));
    }

    private static byte[] sha256(String input) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return digest.digest(input.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

**Design explanation:**

- Loads the key via Spring `Environment` from the `DEMO_API_KEY` environment variable; **never hardcodes secrets in source**.
- Retains only the SHA-256 digest for comparison. `MessageDigest.isEqual` compares byte arrays to reduce timing-difference risks from string comparison; it does not guarantee every branch in the verification flow is strictly constant-time.
- The demo holds **one key** with no dynamic revocation; key metadata is declared server-side. Production needs key IDs/public prefixes, durable registries, expirations, revocation, and per-key scopes.
- The `key.length() >= 24` check validates **length** only, not entropy. **Always generate with a CSPRNG**; a 24-character key of all `A`s is still weak.
- SHA-256 hashing is reasonable for **randomly generated high-entropy secrets**; for weak passwords, plain SHA-256 does not resist dictionary guessing effectively.
- The code intentionally avoids keeping the raw candidate in `Authentication`, responses, or logs.
- No code attaches a user ID to the key; the principal is a client identity.

### 10.6. File `ApiKeyAuthFilter.java`

~~~java
package com.example.apikey;

import java.io.IOException;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class ApiKeyAuthFilter extends OncePerRequestFilter {

    private final ApiKeyRegistry registry;

    public ApiKeyAuthFilter(ApiKeyRegistry registry) {
        this.registry = registry;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {

        String provided = request.getHeader("X-API-Key");

        if (provided == null) {
            // Do not grant permissions automatically. AuthorizationFilter will
            // require Authentication for protected endpoints.
            chain.doFilter(request, response);
            return;
        }

        var identity = registry.verify(provided);
        if (identity.isEmpty()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        var client = identity.get();
        var principal = new ApiPrincipal(
            client.clientId(),
            client.tenantId()
        );

        List<SimpleGrantedAuthority> authorities =
            client.authorities().stream()
                .map(SimpleGrantedAuthority::new)
                .toList();

        var authentication = new UsernamePasswordAuthenticationToken(
            principal,
            null,
            authorities
        );

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);

        chain.doFilter(request, response);
    }
}
~~~

This filter reads the key from the header, verifies it, and constructs an authenticated `Authentication` via the three-argument constructor with authorities. The principal is `ApiPrincipal(clientId, tenantId)`.

**Points to note:**

- The demo does not declare the filter as a `@Component` or `@Bean`; it is instantiated directly in the security chain in the next file. This prevents the filter from being registered twice—once in the Servlet container and once in the Spring Security chain.
- Do not assign `ROLE_USER` or a username just for presenting an API key. The credential represents a service account.
- When the key is invalid, the filter returns 401. When the key is missing, the filter lets the request continue so `authenticated`/`hasAuthority` policies handle it; public paths remain accessible.
- The Servlet security filter chain manages clearing `SecurityContextHolder` after the request. With custom integrations or separate threads/async execution, verify context propagation/cleanup to prevent principal leakage.
- This is an illustrative filter, **lacking duplicate-header defense, strict key format checks, replay protection, audit logging, key expiration, rate limiting, or a standardized error contract**. Production must add and test these controls.

### 10.7. File `SecurityConfig.java`

~~~java
package com.example.apikey;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            ApiKeyRegistry registry
    ) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, ex) ->
                    response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED))
                .accessDeniedHandler((request, response, ex) ->
                    response.sendError(
                        HttpServletResponse.SC_FORBIDDEN)))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/whoami")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/records/**")
                    .hasAuthority("RECORD_READ")
                .requestMatchers(HttpMethod.POST, "/api/records")
                    .hasAuthority("RECORD_WRITE")
                .anyRequest().denyAll());

        http.addFilterBefore(
            new ApiKeyAuthFilter(registry),
            UsernamePasswordAuthenticationFilter.class
        );

        return http.build();
    }
}
~~~

**Why is it written this way?**

- `securityMatcher("/api/**")` limits the illustrative chain to `/api/**`. In a real product with additional URLs, ensure **every sensitive endpoint matches a security chain**. Adding routes outside `/api/**` without another chain leaves them unprotected by this configuration.
- `SessionCreationPolicy.STATELESS`: Spring Security does not use server-side `HttpSession` to store/restore authentication. Every request with a key must be verified anew; keys do not spawn login sessions.
- CSRF is disabled **only in this demo API chain using client-attached header credentials without cookie-based login**. Never apply this advice to browser apps using session cookies, browser-auto-sent HTTP Basic, or ambient credentials. When combining multiple auth mechanisms, evaluate CSRF per chain.
- `httpBasic` and `formLogin` are disabled to keep test outcomes clear with no alternate authentication pathways.
- `AuthorizationFilter` enforces `RECORD_READ` or `RECORD_WRITE` per HTTP method, while tenant enforcement is the repository/service's responsibility.
- `authenticationEntryPoint` returns 401 when unauthenticated; `accessDeniedHandler` returns 403 when a valid principal lacks permission.
- Do not assume a key alone grants access to all documents, because route rules are **coarse-grained** only.

### 10.8. File `ApiRecordStore.java`

~~~java
package com.example.apikey;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class ApiRecordStore {

    public record ApiRecord(
        long id,
        String tenantId,
        String title
    ) {}

    private final Map<Long, ApiRecord> records = Map.of(
        101L, new ApiRecord(101L, "north", "North report"),
        201L, new ApiRecord(201L, "south", "South report")
    );

    public Optional<ApiRecord> findScoped(long id, String tenantId) {
        return Optional.ofNullable(records.get(id))
            .filter(record -> record.tenantId().equals(tenantId));
    }
}
~~~

The demo data store applies the tenant filter supplied by the verified principal. In production databases, prefer scoped queries like `WHERE id = :id AND tenant_id = :tenantId`; never read records across tenants and rely on frontend filtering to decide what to display.

### 10.9. File `ApiController.java`

~~~java
package com.example.apikey;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    private final ApiRecordStore store;

    public ApiController(ApiRecordStore store) {
        this.store = store;
    }

    @GetMapping("/api/public")
    public Map<String, String> publicInfo() {
        return Map.of("status", "public");
    }

    @GetMapping("/api/whoami")
    public Map<String, String> whoami(Authentication authentication) {
        ApiPrincipal principal =
            (ApiPrincipal) authentication.getPrincipal();

        return Map.of(
            "clientId", principal.clientId(),
            "tenantId", principal.tenantId()
        );
    }

    @GetMapping("/api/records/{id}")
    public ResponseEntity<Map<String, Object>> record(
            @PathVariable long id,
            Authentication authentication
    ) {
        ApiPrincipal principal =
            (ApiPrincipal) authentication.getPrincipal();

        return store.findScoped(id, principal.tenantId())
            .map(record -> ResponseEntity.ok(
                Map.<String, Object>of(
                    "id", record.id(),
                    "title", record.title()
                )
            ))
            .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping("/api/records")
    public ResponseEntity<Void> createPlaceholder() {
        // Demo simulates only an endpoint requiring WRITE permission.
        // Does not actually create records or update a database.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
~~~

Warning: `createPlaceholder` performs no mutation; it exists solely to illustrate the `RECORD_WRITE` rule. The demo key lacks that permission and therefore cannot invoke the endpoint. In real applications, mutations must be protected at service/domain boundaries and respect transaction/tenant policies.

### 10.10. Generating the Secret, Running, and Testing HTTP

**Bash/macOS/Linux** (example generating a key with OpenSSL):

~~~bash
export DEMO_API_KEY="$(openssl rand -hex 32)"
mvn spring-boot:run
~~~

If OpenSSL is unavailable, use a secret manager or another CSPRNG. To test requests in the same shell:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/whoami
curl -i -H "X-API-Key: invalid-secret" http://localhost:8080/api/whoami
curl -i -H "X-API-Key: $DEMO_API_KEY" http://localhost:8080/api/whoami
curl -i -H "X-API-Key: $DEMO_API_KEY" http://localhost:8080/api/records/101
curl -i -H "X-API-Key: $DEMO_API_KEY" http://localhost:8080/api/records/201
curl -i -X POST -H "X-API-Key: $DEMO_API_KEY" http://localhost:8080/api/records
~~~

**Windows PowerShell 5.1+** can generate 32 random bytes and pass them via environment for the Maven process:

~~~powershell
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$env:DEMO_API_KEY = -join ($bytes | ForEach-Object { $_.ToString("x2") })
mvn spring-boot:run
~~~

In PowerShell, use `curl.exe` instead of the `curl` alias if needed:

~~~powershell
curl.exe -i -H ("X-API-Key: " + $env:DEMO_API_KEY) http://localhost:8080/api/whoami
~~~

Never run `echo $DEMO_API_KEY` to paste raw keys into reports; verify key existence via length or secret-manager metadata, never by leaking credentials.

**Expected results from the code** (not execution logs from authoring this article):

| Request | HTTP | Content / Meaning |
| --- | --- | --- |
| No key → `GET /api/public` | 200 | JSON `{"status":"public"}` |
| No key → `GET /api/whoami` | 401 | Unauthenticated |
| Wrong key → `GET /api/whoami` | 401 | Invalid credential |
| Valid key → `GET /api/whoami` | 200 | `clientId=client:reporting-job`, `tenantId=north` |
| Valid key → `GET /api/records/101` | 200 | North-tenant record |
| Valid key → `GET /api/records/201` | 404 | South-tenant record outside scope |
| Valid key → `POST /api/records` | 403 | Has only `RECORD_READ`, missing `RECORD_WRITE` |

Returning 404 in the demo is a policy choice to avoid disclosing cross-tenant records, **not a mandatory rule for all systems**. A product may choose 403 or 404 per contract and privacy policy.

## 11. Testing with MockMvc

File `src/test/java/com/example/apikey/ApiKeySecurityTests.java`:

~~~java
package com.example.apikey;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "DEMO_API_KEY=example-test-secret-for-local-integration-only-123"
})
@AutoConfigureMockMvc
class ApiKeySecurityTests {

    private static final String KEY =
        "example-test-secret-for-local-integration-only-123";

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotRequireKey() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void missingKeyCannotUseProtectedApi() throws Exception {
        mvc.perform(get("/api/whoami"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidKeyIsRejected() throws Exception {
        mvc.perform(get("/api/whoami")
                .header("X-API-Key", "wrong-secret"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validKeyIdentifiesClientNotUser() throws Exception {
        mvc.perform(get("/api/whoami")
                .header("X-API-Key", KEY))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.clientId")
                .value("client:reporting-job"))
            .andExpect(jsonPath("$.tenantId").value("north"));
    }

    @Test
    void validKeyCanReadScopedRecord() throws Exception {
        mvc.perform(get("/api/records/101")
                .header("X-API-Key", KEY))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(101));
    }

    @Test
    void sameKeyCannotReadOtherTenant() throws Exception {
        mvc.perform(get("/api/records/201")
                .header("X-API-Key", KEY))
            .andExpect(status().isNotFound());
    }

    @Test
    void readOnlyKeyCannotWrite() throws Exception {
        mvc.perform(post("/api/records")
                .header("X-API-Key", KEY))
            .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn clean test
~~~

Tests supply the key via Spring Boot test properties, so **no real environment variable is needed** just to run tests. This is a fixed test string, not a production secret.

Key tests:

- **401:** missing/invalid key is rejected.
- **200:** valid key establishes client principal with read permission for the right tenant.
- **404:** valid key cannot view another tenant's record.
- **403:** valid key lacks write scope.

**Verification note:** This sample project presents the complete structure and code, yet a Maven build/test was not executed while authoring this document. Only treat `BUILD SUCCESS` as an outcome after running it yourself and verifying your environment/versions. If you modify the filter, security chain, or Servlet container config, update the integration tests accordingly.

## 12. Plain Java: Proving a Client Key Is Not a User

Without running Spring Boot, the following Java 17 program illustrates permissions by client and tenant; it **is not a real authentication program**.

Create file `ClientScopeDemo.java`:

~~~java
import java.util.Set;

public class ClientScopeDemo {

    record Client(String id, String tenant, Set<String> scopes) {}

    static boolean canRead(Client client, String resourceTenant) {
        return client.scopes().contains("RECORD_READ")
            && client.tenant().equals(resourceTenant);
    }

    public static void main(String[] args) {
        Client reporter = new Client(
            "client:reporting-job",
            "north",
            Set.of("RECORD_READ")
        );

        System.out.println(canRead(reporter, "north"));
        System.out.println(canRead(reporter, "south"));

        Client writerOnly = new Client(
            "client:writer",
            "north",
            Set.of("RECORD_WRITE")
        );
        System.out.println(canRead(writerOnly, "north"));
    }
}
~~~

Commands:

~~~bash
javac ClientScopeDemo.java
java ClientScopeDemo
~~~

Exact stdout:

~~~text
true
false
false
~~~

First line: matching scope and tenant. Second line: matching scope, wrong tenant. Third line: matching tenant, missing `RECORD_READ`. **No line proves Alice/Bob logged in**: both objects are client identities.

## 13. When an API Key Is Issued "to a User"

Some services allow users to create **personal API keys**. Metadata may include `owner_user_id` and scopes, so the backend knows which account issued the key. Even so:

- Someone else may steal or be shared the key; a request does not prove the account owner is driving it.
- The token can outlive a login session, even after the user logs out.
- If the user is disabled or scopes/memberships change, the key must be re-evaluated/revoked per policy.
- Never equate holding a personal key with the user **having just passed MFA** or having explicitly confirmed a transaction.
- Audits must distinguish **key ID**, **owning account**, **running entity**, and **acting user**. These fields can differ.

If your product requires a third-party application to act on a user's behalf, consider a properly designed OAuth2/OIDC delegated authorization flow with scopes, audience, expiry, user consent, and token revocation. If a system needs the current user in a server-to-server call, pass verified delegation proof, never an unverified self-declared user ID header.

### Do Not Confuse "Service Account" with "Human"

A **service account** is a machine/workload identity. An owner or team may operate it, yet the operational owner differs from an end-user principal. An integration holding `REPORT_READ` to aggregate permitted data still cannot arbitrarily change a user's password or access personal profiles outside scope.

## 14. From a Demo Key to a Production Key Registry

Minimum design for a registry:

~~~sql
-- Indicative schema only; adjust to your DB and threat model.
CREATE TABLE api_credentials (
    key_id          VARCHAR(80) PRIMARY KEY,
    client_id       VARCHAR(120) NOT NULL,
    tenant_id       VARCHAR(120),
    secret_digest   VARCHAR(128) NOT NULL,
    scopes          VARCHAR(1000) NOT NULL,
    environment     VARCHAR(40) NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    expires_at      TIMESTAMP,
    revoked_at      TIMESTAMP,
    last_used_at    TIMESTAMP
);
~~~

Never store raw keys in the table. Representing `scopes` as a single string is solely to keep the schema illustrative; production typically needs a normalized relation or validated JSON schema and explicit policy versioning. Prevent clients from altering `client_id`/`tenant_id` in requests.

Request pipeline:

~~~text
1. Parse format/key id; reject abnormal sizes/headers
2. Look up record by public key ID
3. Compare secret portion using proper constant-time digest/HMAC
4. Verify environment, expiration, revoked status, active account/client
5. Construct client ID/tenant principal + authorities from DB
6. Execute request authorization
7. Domain/service verifies resource owner/tenant
8. Update metrics/audits by key ID; never log raw secret
~~~

Design explicitly for concurrent rotation and caching: if cached metadata stays active after revocation, old keys can keep working longer than intended. Set appropriate cache TTLs or active invalidation. Distinguish **401 invalid credential**, **403 insufficient permissions**, **404 record not found**, and **429 rate limit exceeded** per API contract.

### Incident Response When a Key Leaks

1. Disable/revoke the suspected key as soon as possible.
2. Identify key ID, client, scopes, tenant, environment, and exposure window.
3. Inspect logs/metrics by ID without retrieving raw secrets into insecure places.
4. Issue a new key via a secure channel, update clients, and test requests.
5. Confirm the old key is revoked; assess what data was read/modified.
6. Fix the leak source: Git repository, CI logs, tracing, browser apps, config files, email, or tickets.
7. If unauthorized access is suspected, execute the appropriate incident response procedure.

Deleting a key line from source without server-side revocation is **not incident remediation**.

## 15. Rate Limiting, Quotas, and Abuse Prevention

API keys help tie traffic to clients and enforce quotas:

~~~text
key_id: k_1042
plan: basic
request_limit: 1000 requests / hour
concurrent_limit: 5
max_export_size: 1000 rows
allowed_http_methods: GET
~~~

This is an illustrative policy, not a fixed prescription for every API.

However:

- Without rate limits, a valid key can still exhaust resources or bulk-scrape data.
- A leaked key can burn through a legitimate customer's quota.
- IP-only rate limiting can be bypassed by botnets or penalize users sharing NAT.
- Combine per-key, per-tenant, per-user (when user identity exists), per-route, and cost-based limits.
- `429 Too Many Requests` means something different from authentication/authorization. Never use rate limiting as a substitute for access control.

Per OWASP, API keys help identify clients and limit abuse, yet **should not be the sole protection layer for sensitive or high-value resources**. For those resources, combine strong authentication, authorization, monitoring, and appropriate business context.

## 16. Architectural Questions and Mechanism Choices

| Context | Approach Worth Considering | Why |
| --- | --- | --- |
| Internal script reading reports without a user | Dedicated workload key with narrow scopes; or OAuth2 client credentials | Client identity and machine permissions |
| Partner integrating API under contract | Dedicated key per partner + quotas, expiry, and revocation; or OAuth2 | Accountability and per-client auditing |
| Web app acting on behalf of logged-in user | User session / OIDC / OAuth2 delegated access | Needs user subject and individual permissions |
| Publicly distributed mobile app | Never embed long-lived secrets in app; use user flows / backend mediation | Mobile secrets are easy to extract |
| Sensitive financial transactions | Strong authentication, user authorization, step-up/MFA; possibly mTLS/transaction proof | Key alone is insufficient |
| System needing per-session revocation and short lifetimes | Tokens with appropriate issuer/lifetime/revocation | Long-lived static keys have serious limits |
| Batch job running independently of humans | Service account with key or short-lived workload credentials | Avoid misassigning human permissions |

**No technology replaces understanding the principal.** If a user action requires "Alice consented", a service account token only proves "this service has permission to call the API", which is insufficient to establish Alice's consent.

## 17. What to Distinguish When Reading Logs

Example of a good audit line (containing no secrets):

~~~json
{
  "requestId": "req-xyz",
  "clientId": "client:reporting-job",
  "keyId": "k_1042",
  "tenantId": "north",
  "action": "RECORD_READ",
  "resourceId": 101,
  "outcome": "ALLOWED"
}
~~~

If a request genuinely executes on behalf of a user, audits should record a trusted end-user field **from delegated auth**, distinct from client ID. Never populate `userId` solely from an unverified header.

Logging hazards: key values, `Authorization` headers, query strings with tokens, request bodies with PII, session cookies, full JWTs, unnecessary raw usernames. Log the minimum required for investigation while complying with data retention and protection rules.

## 18. Self-Practice Questions

**Exercise 1.** A CRM application's API key is shared across 50 employees. The API knows the key belongs to CRM. Is that enough proof that Alice sent the request? Why?

**Exercise 2.** A key has `RECORD_READ` and tenant `north`. A caller sends `GET /api/records/201`, where record 201 belongs to `south`. If the server only checks authority and returns the record, what is the security flaw?

**Exercise 3.** Why can't storing an API key in a public SPA's JavaScript bundle be considered secret? Propose an appropriate user identification design.

**Exercise 4.** A backend trusts `X-User-Id: alice` alongside a service account's API key. What happens if a client changes `alice` to `admin`? Which mechanism should authenticate the user?

**Exercise 5.** When an employee leaves a team that shares one key, why might revoking the employee's permissions in the database fail to stop them from using the key? What is a better credential structure?

**Exercise 6.** For a key leaked via Git, why is a git commit deleting the file not enough? Write out a revocation/rotation procedure.

**Exercise 7.** Distinguish 401, 403, 404, and 429 in the demo and in production design.

**Exercise 8.** Why is an OAuth2 client credentials token not considered a "user login token"? When is a delegated access token needed?

**Exercise 9.** Why store a hash of a high-entropy key instead of the raw key? Why doesn't SHA-256 rescue a low-entropy key?

**Exercise 10.** Should CSRF be disabled on every security chain just because one API chain uses a custom header? Why?

### Suggested Answers

1. No; the key represents a credential/client, not automatically the human operating it.
2. BOLA / cross-tenant unauthorized access; filter resources by tenant/owner from trusted metadata.
3. JS bundles can be read by clients; use proper login/OIDC/delegated tokens or an intermediary backend.
4. User impersonation is possible; use subjects from signed, verified tokens or an authenticated user session.
5. Copies of the shared key still exist; issue keys per workload/user with separate revocation and scopes, or use delegation.
6. The credential has been copied; revoke server-side, issue a new one, update systems, and investigate.
7. 401 missing/invalid credentials; 403 valid credentials lacking permission; 404 outside visible resource scope per policy; 429 rate limit exceeded.
8. Client credentials represent an application; user delegation requires a token flow carrying user subject and consent.
9. Hashing limits raw secret exposure on DB compromise; weak keys remain guessable offline.
10. No. Evaluate CSRF per chain's authentication mechanism, especially browser sessions/cookies.

## 19. Summary

An API key is a useful credential for **identifying and managing clients/workloads**, yet does not automatically verify **end-user** identity or authorize access to all resources. Sharing one key across multiple apps/people destroys traceability, granular authorization, and independent revocation.

Sound design typically includes:

1. **Clear principal:** does the key represent a client or a key-owning user? Never conflate the two.
2. **Least privilege:** scope/action/tenant/resource checks, deny by default.
3. **Secure credentials:** high entropy, TLS, no raw key exposure, digest storage, and secret management.
4. **Lifecycle:** expiration, rotation, revocation, incident response, per-client/device management.
5. **Enforcement:** authentication in the Spring Security filter chain; authorization at routes and domain/service layers.
6. **Audit/limits:** key ID, client ID, tenant, quotas, rate limits, never logging secrets.
7. **When user consent is needed:** use proper user authentication and delegation flows, never unverified header spoofing.

### References

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [OWASP — API Security Top 10 (2023)](https://api-security.owasp.org/editions/2023/en/0x11-t10/)
- [OWASP — API1:2023 Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/)

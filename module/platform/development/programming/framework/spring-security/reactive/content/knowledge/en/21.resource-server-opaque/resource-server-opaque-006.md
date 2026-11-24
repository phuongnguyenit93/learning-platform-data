# Customizing the Introspector to Enrich User Data or Permissions

> **Module:** Spring Security – reactive  
> **Topic Group:** Resource Server Opaque  
> **Focus:** Customizing Spring WebFlux's `ReactiveOpaqueTokenIntrospector` using the pattern **delegate introspection -> verify valid token -> enrich directory/role info from a trusted source -> construct a new principal**, without breaking scopes or opening privilege escalation holes.  
> **Example Tech:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Reactor, WebTestClient.

## 1. Scenario: Valid Token, Incomplete Information

A WebFlux API protecting reports receives an opaque access token:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer opaque-access-token
```

The Authorization Server (AS) exposes an Introspection Endpoint per RFC 7662. The Resource Server validates the token through this endpoint, and the AS returns, for example:

```json
{
  "active": true,
  "sub": "alice",
  "client_id": "frontend-web",
  "scope": "reports.read profile.read",
  "aud": ["reports-api"],
  "exp": 1794003600
}
```

The response tells the API that the token is `active`, the subject is `alice`, which client was issued the token, the scopes, audience, and expiration. However, **it does not reveal** the display name, department, or business roles (`REPORT_READER`, `REPORT_ADMIN`) stored in the internal management system.

You want the API to:

- Display `display_name` and `department` in the user profile response.
- Evaluate `hasRole("REPORT_ADMIN")` from a **trusted internal directory**, not from a user-supplied `X-Role: ADMIN` header.
- **Preserve** the `SCOPE_reports.read` authorities that Spring Security already built from the AS response.
- Refuse to grant roles for an `active=false` token, wrong audience, missing `sub`, or a subject absent from the directory.
- Keep all processing **reactive** (`Mono`/`flatMap`), with no `.block()` on the Netty event loop.
- Test real tokens passing through the WebFlux Bearer filter using a **fake delegate in tests**, without needing a live IdP.

That is the exact purpose of a custom `ReactiveOpaqueTokenIntrospector`.

### 1.1. One Diagram to Remember

```text
API request: Authorization: Bearer <opaque-token>
        |
        v
WebFlux SecurityWebFilterChain / Opaque Token authentication
        |
        v
Custom ReactiveOpaqueTokenIntrospector
        |
        +--> delegate: SpringReactiveOpaqueTokenIntrospector
        |       |
        |       +--> POST Authorization Server /introspect
        |       |       client authentication + token
        |       +--> AS returns active=true and claims
        |       +--> active=false / invalid => AUTHENTICATION FAIL
        |
        +--> check aud/sub from validated introspection result
        |       |
        |       +--> wrong/missing => FAIL CLOSED
        |
        +--> UserDirectory.findBySubject(sub) (reactive, trusted)
        |       |
        |       +--> displayName, department, authorized roles
        |       +--> unknown subject => FAIL CLOSED per example policy
        |
        +--> DefaultOAuth2AuthenticatedPrincipal
                attributes = original + display_name + department
                authorities = original scopes + trusted roles
        |
        v
BearerTokenAuthentication / AuthorizationWebFilter
        |
        +--> SCOPE_reports.read? / ROLE_REPORT_ADMIN?
        +--> 403 if lacking permission; 200 if authorized
```

**Most important rule:** call `delegate.introspect(token)` **first**, and only enrich the `OAuth2AuthenticatedPrincipal` already confirmed by the delegate. Never write an introspector that skips the AS and grants `ROLE_ADMIN` just because a token starts with some prefix; that is an **authentication bypass**, not "custom claims."

### 1.2. Learning Outcomes

After this lesson, you can:

1. Distinguish `ReactiveOpaqueTokenIntrospector`, `SpringReactiveOpaqueTokenIntrospector`, `NimbusReactiveOpaqueTokenIntrospector` (older, deprecated), and Servlet `OpaqueTokenIntrospector`.
2. Understand RFC 7662 token introspection and `active`, `scope`, `sub`, `aud`, `client_id`, `exp`.
3. Use `delegate.introspect(token).flatMap(...)` to query a reactive data source.
4. Add attributes **without overwriting** standard AS claims; add `SimpleGrantedAuthority("ROLE_...")` **without losing** `SCOPE_...`.
5. Choose fail-closed behavior when `sub` is missing, unauthorized, or the permission source fails.
6. Integrate `ServerHttpSecurity.oauth2ResourceServer(...opaqueToken(...))` on WebFlux.
7. Write a runnable Java 17+ Maven project with offline tests: testing enrichment directly, 401/403, scopes, roles, audience, inactive tokens, and Reactor laziness.
8. Recognize test limitations: fake introspection lets you test business policy, but does not prove HTTP client credentials or RFC 7662 endpoints work against a live server.

## 2. Opaque Token Does Not Imply JWT

An **opaque access token** is typically a string the Resource Server **cannot verify on its own** or should not infer contents from. It may look random:

```text
q4g2aKxP...redacted...
```

The Resource Server asks the **Authorization Server**: "Is this token `active`, and what attributes does it carry?" via OAuth 2.0 Token Introspection (RFC 7662).

Conceptual request (no real secrets):

```http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Authorization: Basic <base64-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded

token=opaque-access-token
```

On a real network: use HTTPS, provider-compliant client authentication, and proper form URL encoding. The AS may return:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "reports.read",
  "aud": ["reports-api"],
  "client_id": "frontend-web"
}
```

If the token is invalid or revoked:

```json
{"active": false}
```

**Never turn `active=false` into a valid principal.** The default `SpringReactiveOpaqueTokenIntrospector` processes the introspection response and rejects inactive tokens; a custom wrapper must uphold that contract.

### 2.1. Introspection Can Apply to JWT-Shaped Strings

Spring Security Opaque Token support does not force tokens to be random strings; even when an access token is JWT-formatted, an API can still use **introspection** to check active/revocation status per policy. In that case, still use `ReactiveOpaqueTokenIntrospector` rather than switching to `ReactiveJwtDecoder` and inadvertently bypassing the AS status check.

Never "Base64-decode and trust claims" from an unverified JWT to add roles, especially if introspection only returns `active=true`. If a use case combines token claims with introspection, verify the claim source, signature, and `sub`/`aud`/`iss` bindings per an agreed profile.

### 2.2. Responses Do Not Always Carry the Same Claims

RFC 7662 requires `active` in the response; other fields depend on the provider, scopes, and contract. Never assume every AS returns `aud`, `sub`, `email`, or `roles`. If your API **needs** subject or audience to protect data, adopt an explicit missing-claim policy: **reject** the token, or configure the AS to supply equivalent data from a trusted source rather than guessing a default subject.

In this project, **the policy intentionally requires** `sub` to be a non-blank string and `aud` to contain `reports-api`. If a real AS uses a different `aud` shape, normalize according to the verified contract before deploying.

## 3. Interfaces and Classes to Use

| Component | Package | Responsibility |
| --- | --- | --- |
| `ReactiveOpaqueTokenIntrospector` | `org.springframework.security.oauth2.server.resource.introspection` | Interface `Mono<OAuth2AuthenticatedPrincipal> introspect(String)` |
| `SpringReactiveOpaqueTokenIntrospector` | Same introspection package | Delegate calling the AS endpoint and verifying `active` |
| `NimbusReactiveOpaqueTokenIntrospector` | Same introspection package | Older implementation **deprecated** in Spring Security 6.5 |
| `OAuth2AuthenticatedPrincipal` | `org.springframework.security.oauth2.core` | `getName()`, `getAttributes()`, `getAuthorities()` |
| `DefaultOAuth2AuthenticatedPrincipal` | `org.springframework.security.oauth2.core` | Constructs a principal with updated attributes and authorities |
| `GrantedAuthority` | `org.springframework.security.core` | Represents an authority, such as `SCOPE_reports.read` or `ROLE_REPORT_ADMIN` |
| `SimpleGrantedAuthority` | `org.springframework.security.core.authority` | Creates an authority from a backend-trusted name |
| `ServerHttpSecurity` | `org.springframework.security.config.web.server` | Configures reactive security filters |
| `SecurityWebFilterChain` | `org.springframework.security.web.server` | Filter chain for WebFlux |
| `OAuth2AuthenticationException` | `org.springframework.security.oauth2.core` | Authentication failure per OAuth2 policy |
| `Mono` | `reactor.core.publisher` | Emits a value, empty, or error signal |

Primary interface:

```java
@FunctionalInterface
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

This is the **API shape for reading comprehension**; do not redefine it when using the Spring Security dependency. In Servlet MVC, `OpaqueTokenIntrospector.introspect(...)` returns an object directly; **never copy** Servlet code into WebFlux and call `.block()`.

### 3.1. Principal and Authorities After Introspection

Spring Security creates default authorities from `scope` in the introspection result, prefixing each scope with `SCOPE_`:

```text
Introspection response:
    "scope": "reports.read profile.read"

Spring GrantedAuthorities:
    SCOPE_reports.read
    SCOPE_profile.read
```

If the internal directory confirms user `alice` has role `REPORT_READER`, the custom introspector should produce:

```text
SCOPE_reports.read       <-- preserved from trusted introspection
SCOPE_profile.read       <-- preserved from trusted introspection
ROLE_REPORT_READER       <-- added from trusted directory
```

**Do not confuse `ROLE_REPORT_READER` with `SCOPE_reports.read`**. By convention, `hasRole("REPORT_READER")` checks authority `ROLE_REPORT_READER`; `hasAuthority("SCOPE_reports.read")` checks the exact scope authority name. An internal role never grants an OAuth2 scope that the AS did not issue.

### 3.2. Do Not Blindly Cast scope

Some implementations convert `scope` into a **list of strings** instead of keeping the original space-separated string. If you call `principal.getAttribute("scope")` and immediately cast to `String`, your code may throw `ClassCastException` depending on the provider/converter. To **preserve scope authorities**, the safest and simplest approach is to copy `principal.getAuthorities()` **already constructed by the delegate** instead of re-parsing the claim.

When you genuinely need custom mapping for `groups` from the introspection response, check whether the runtime type is a collection/list/string and whether values belong to an allowlist, then unit-test missing/null/wrong-type cases. Never turn `roles` from a client JSON body into authorities.

## 4. The Right Way to Customize: Decorator Instead of Replacing Verification

A safe custom introspector is typically a **decorator**:

```java
public final class EnrichingOpaqueTokenIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final UserDirectory directory;

    public EnrichingOpaqueTokenIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            UserDirectory directory) {
        this.delegate = delegate;
        this.directory = directory;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .flatMap(this::enrichValidatedPrincipal);
    }

    private Mono<OAuth2AuthenticatedPrincipal> enrichValidatedPrincipal(
            OAuth2AuthenticatedPrincipal principal) {
        // See the complete project in Section 10.
        return directory.findBySubject(principal.getAttribute("sub"))
            .map(user -> new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(),
                principal.getAttributes(),
                principal.getAuthorities()));
    }
}
```

**This is only an architectural illustration, NOT a standalone runnable Java file.** The complete version in Section 10 handles null/wrong-type `sub`, audience, missing users, adding fields, adding roles, and `Collection<GrantedAuthority>` types.

The path must always be:

1. `delegate.introspect(token)` must succeed.
2. Enforce any extra Resource Server constraints.
3. Use only `sub`/tenant from the **trusted introspection result** as the user lookup key.
4. Fetch roles from a **trusted directory** and allow only roles permitted by API policy.
5. Copy attributes/authorities; **never mutate** delegate objects or global caches.
6. Return a **new principal**; on errors, propagate the error rather than producing anonymous/admin principals.

### 4.1. map or flatMap?

- Pure synchronous data transformation (no I/O), e.g., adding an authority from a verified claim: `.map(principal -> enriched)`.
- Calling a reactive repository, user directory, UserInfo HTTP endpoint, or another service returning `Mono<UserProfile>`: `.flatMap(principal -> directory.findBySubject(...).map(...))`.

```java
// Correct: chains two async operations in the same reactive chain.
return delegate.introspect(token)
    .flatMap(principal ->
        directory.findBySubject(principal.getName())
            .map(user -> enrich(principal, user)));
```

Wrong:

```java
// Wrong on the Netty event loop; may cause blocking:
UserProfile user = directory.findBySubject(subject).block();

// Wrong: subscribe detaches the lifecycle; the principal is not guaranteed to be enriched.
directory.findBySubject(subject).subscribe(user -> cacheUser(user));
return delegate.introspect(token);
```

`flatMap` ensures AS errors, directory errors, and cancellation propagate through the publisher; Spring Security will not complete authentication until enrichment finishes.

### 4.2. Why Fail-Closed?

Scenarios:

| Condition | Example Behavior | Reason |
| --- | --- | --- |
| Introspection `active=false` | **Reject** | Do not accept revoked/expired tokens |
| AS timeout/401/5xx | **Issue no authentication** | Cannot prove the token is active |
| Active token missing `sub` | **Reject** | No trusted identity to map local roles |
| Active token with wrong audience | **Reject** | Not intended for this Resource Server |
| Subject absent from trusted directory | **Reject** per project policy | Avoid granting default roles |
| Directory unavailable | **Grant no roles**, fail closed | Internal permissions could not be verified |
| Valid token, existing user, lacks role | **Authenticate without that role** | 403 on endpoints requiring the role |
| Valid token, user has matching role and scope | **Success** | Permissions from both sources verified |

Depending on architecture, a user missing from the directory could be treated as a principal holding only scopes and **no roles**, if your API only needs AS claims and explicitly designs that policy. This lesson intentionally chooses **require-known-user** to make the permission boundary explicit. Do not equate "fail closed" with converting every repository error into HTTP 401: internal infrastructure failures can map to 5xx or 503 per exception handling; **what is mandatory** is granting no permissions without sufficient verification.

## 5. Where Should User Data and Roles Come From?

Common sources:

| Source | What Is the Data Used For? | What Must Be Controlled? |
| --- | --- | --- |
| **Active-verified introspection response** | Subject, scopes, client ID, audience, expiration | Trusted AS endpoint, client authentication, TLS |
| **Internal user directory** (R2DBC/LDAP service) | Display name, department, current roles | Authorization source, subject/tenant mapping, caching |
| **OIDC UserInfo endpoint** | User profile claims when AS permits | Token audience/scopes, matching `sub`, trusted HTTPS |
| **Business authorization service** | Tenant roles, object-level permissions | Tenant/resource context, versioning/revocation, latency |
| **Introspected JWT access token** | Claims per token profile | Never trust unverified payloads directly |
| **Client HTTP `X-Role`, query `?role=ADMIN`** | **Must never be used** to grant permissions | Untrusted input |
| **Frontend `localStorage` data** | **Untrusted** for server authorization | User can tamper with it |

**Keying properly:** `sub` is typically unique only within a **specific issuer/tenant**. In multi-issuer/multi-tenant SaaS, use a composite key such as `issuerId + tenantId + sub` rather than mixing `alice` across two tenants. Display names and emails are unreliable identity keys for role mapping because they can change or collide.

### 5.1. Enrich Data Only, Never Overwrite Security-Critical Claims

If the delegate returns:

```json
{
  "sub": "alice",
  "scope": ["reports.read"],
  "aud": ["reports-api"]
}
```

The custom decorator can add:

```json
{
  "display_name": "Alice Tran",
  "department": "finance"
}
```

But it **must never** change `scope` to `admin`, `aud` to another API, `sub` to another user, or `active` to true. Add only necessary metadata; minimize sensitive employee profile data per endpoint and never return all principal/token attributes to browsers.

### 5.2. Grant Only Roles Within the Trust Policy

An explicit mapping:

```text
Directory role "REPORT_READER" -> ROLE_REPORT_READER
Directory role "REPORT_ADMIN"  -> ROLE_REPORT_ADMIN
Introspection scope "admin"    -> SCOPE_admin
```

For administrative endpoints, consider requiring **both `SCOPE_admin` and `ROLE_REPORT_ADMIN`**, not just one or the other. That way, a local role never allows a token issued only for `profile.read` by the AS to invoke admin functions. The demo project enforces **AND** for both conditions.

## 6. Configuring Spring Security WebFlux Reactive

When custom enrichment is not yet needed, Spring Boot can configure an opaque token Resource Server via:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: reports-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

This configures the app's **default delegate**. The Resource Server needs client credentials to call the introspection endpoint; those are credentials between the Resource Server and AS, **not** an end user's login password.

To enrich claims and roles, define your own `@Bean ReactiveOpaqueTokenIntrospector`:

```java
// Snippet in @Configuration; see the full version in Section 10.
@Bean
ReactiveOpaqueTokenIntrospector introspector(UserDirectory directory) {
    ReactiveOpaqueTokenIntrospector delegate =
        SpringReactiveOpaqueTokenIntrospector
            .withIntrospectionUri(introspectionUri)
            .clientId(clientId)
            .clientSecret(clientSecret)
            .build();

    return new EnrichingOpaqueTokenIntrospector(
        delegate, directory, "reports-api");
}
```

Spring Security 6.5 recommends the `SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri(...)` builder. The older three-string constructor is marked deprecated, and `NimbusReactiveOpaqueTokenIntrospector` is also deprecated; **do not copy old tutorials mechanically**.

Reactive DSL:

```java
@Bean
SecurityWebFilterChain security(
        ServerHttpSecurity http,
        ReactiveOpaqueTokenIntrospector introspector) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/health").permitAll()
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(opaque ->
                opaque.introspector(introspector)))
        .build();
}
```

**Note:** `ServerHttpSecurity` and `SecurityWebFilterChain` belong to WebFlux; `HttpSecurity` and `SecurityFilterChain` are Servlet. Calling `.opaqueToken(opaque -> opaque.introspector(custom))` **overrides** the auto-configured introspector for that security chain, so ensure the delegate inside your custom bean actually performs introspection or policy-compliant trust validation.

## 7. A Plain Java 17 Example on Preserving Scopes and Adding Roles

Before using Reactor/Spring, let's model the principle of combining authorities **without losing already-verified permissions**.

File `AuthorityMergeDemo.java`:

```java
import java.util.Set;
import java.util.TreeSet;

public final class AuthorityMergeDemo {

    static Set<String> merge(Set<String> introspectedScopes,
                             Set<String> trustedDirectoryRoles) {
        Set<String> authorities = new TreeSet<>();

        for (String scope : introspectedScopes) {
            authorities.add("SCOPE_" + scope);
        }
        for (String role : trustedDirectoryRoles) {
            authorities.add("ROLE_" + role);
        }
        return authorities;
    }

    public static void main(String[] args) {
        System.out.println(merge(
            Set.of("reports.read"), Set.of("REPORT_READER")));
        System.out.println(merge(
            Set.of("admin"), Set.of("REPORT_ADMIN")));
    }
}
```

Run with JDK 17+:

```bash
javac AuthorityMergeDemo.java
java AuthorityMergeDemo
```

**Exact stdout** (`TreeSet` sorts lexicographically):

```text
[ROLE_REPORT_READER, SCOPE_reports.read]
[ROLE_REPORT_ADMIN, SCOPE_admin]
```

**Limitation:** This is solely a set-union model; the program **does not introspect tokens** and is insufficient by itself to authenticate callers. In real WebFlux, input scopes must come from **successful delegate introspection**, roles from an **authoritative directory**, plus audience/subject checks. The next project implements those exact steps.

## 8. Runnable Project Design and Testing Strategy

We build a Spring Boot **3.5.16**, Java 17+, Spring Security 6.5.x API. This is a pinned-version learning baseline; new production systems should pick a supported Boot/Security branch per your organization's update policy.

### Endpoints

| Endpoint | Condition | Result |
| --- | --- | --- |
| `GET /health` | Public | 200 `OK` |
| `GET /api/profile` | Active token, valid aud, sub exists in directory | Returns sub/displayName/department |
| `GET /api/reports` | `SCOPE_reports.read` | 200 `reports OK`, or 403 |
| `GET /api/admin` | **`SCOPE_admin` AND `ROLE_REPORT_ADMIN`** | 200 `admin OK`, or 403 |
| Unknown path | Deny all | Usually 403 if authenticated |

On every protected endpoint, inactive tokens, wrong audiences, missing `sub`, unknown users, or delegate errors receive **no authentication**. The exact error HTTP status depends on the handler; tests use `OAuth2AuthenticationException` for negative cases to verify 401.

### What the Tests Prove

- **Unit `StepVerifier`**: the decorator calls the delegate first, never elevates privileges before introspection, preserves scopes, adds valid roles from the directory, validates audience and subject, never mutates the original principal, handles errors, and preserves Reactor laziness.
- **HTTP `WebTestClient`**: with a `Bearer` header, real Spring WebFlux security receives the enriched principal and enforces scopes/roles, returning 200/401/403 per policy.
- **What is not proved**: that real client credentials and a live introspection endpoint work. The HTTP suite uses a fake delegate and **does not** run an IdP. Production readiness requires adding a mock HTTP introspection server or IdP sandbox tests.

### File Structure

```text
reactive-opaque-enrichment/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/opaque/
    │   │   ├── Application.java
    │   │   ├── UserDirectory.java
    │   │   ├── InMemoryUserDirectory.java
    │   │   ├── EnrichingOpaqueTokenIntrospector.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── ApiController.java
    │   └── resources/application.yml
    └── test/java/demo/opaque/
        ├── DemoIntrospectionFixtures.java
        ├── EnrichingIntrospectorTests.java
        └── HttpOpaqueTokenTests.java
```

## 9. Maven and Application Setup

### 9.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-opaque-enrichment</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

`spring-boot-starter-webflux` selects the reactive stack; `spring-boot-starter-oauth2-resource-server` provides the opaque token Resource Server. No OAuth2 Client starter is needed if the service **only validates inbound Bearer tokens** without requesting downstream tokens itself.

### 9.2. src/main/resources/application.yml

```yaml
app:
  opaque:
    introspection-uri: https://id.example.test/oauth2/introspect
    client-id: reports-api-introspection
    client-secret: demo-secret-not-for-production
    audience: reports-api

server:
  port: 8080
```

**Important:** `id.example.test` and `demo-secret-not-for-production` are public dummy values. They let the project boot and run offline tests, but **cannot introspect tokens over the network**. For real execution, replace the URL, client authentication, and secret with an IdP sandbox/secret manager, HTTPS, and the right audience contract. Never store production secrets in YAML, source code, or container images.

### 9.3. src/main/java/demo/opaque/Application.java

```java
package demo.opaque;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

## 10. User/Role Source and Custom Introspector

### 10.1. src/main/java/demo/opaque/UserDirectory.java

```java
package demo.opaque;

import java.util.Set;
import reactor.core.publisher.Mono;

public interface UserDirectory {

    Mono<UserProfile> findBySubject(String subject);

    record UserProfile(
        String displayName,
        String department,
        Set<String> roles) {}
}
```

`UserDirectory` abstracts a database/R2DBC/LDAP gateway or trusted user-role service. The method returns `Mono<UserProfile>` without blocking. `UserProfile` uses a Java record (available in Java 17).

### 10.2. src/main/java/demo/opaque/InMemoryUserDirectory.java

```java
package demo.opaque;

import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public final class InMemoryUserDirectory implements UserDirectory {

    private static final Map<String, UserProfile> USERS = Map.of(
        "alice", new UserProfile(
            "Alice Tran", "finance", Set.of("REPORT_READER")),
        "bob", new UserProfile(
            "Bob Le", "sales", Set.of("REPORT_READER")),
        "admin", new UserProfile(
            "Admin Kim", "finance",
            Set.of("REPORT_READER", "REPORT_ADMIN"))
    );

    @Override
    public Mono<UserProfile> findBySubject(String subject) {
        return Mono.justOrEmpty(USERS.get(subject));
    }
}
```

This is a **demo** directory, not a production authorization mechanism. `REPORT_ADMIN` is determined from a backend-managed store, never from frontend-supplied parameters. Production needs tenant/issuer-aware subject keys, role lifecycle/revocation, auditing, and proper persistence. If using R2DBC, query by validated subject using parameterized queries rather than concatenating SQL strings.

### 10.3. src/main/java/demo/opaque/EnrichingOpaqueTokenIntrospector.java

```java
package demo.opaque;

import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class EnrichingOpaqueTokenIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private static final Set<String> PERMITTED_ROLES =
        Set.of("REPORT_READER", "REPORT_ADMIN");

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final UserDirectory directory;
    private final String expectedAudience;

    public EnrichingOpaqueTokenIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            UserDirectory directory,
            String expectedAudience) {
        this.delegate = delegate;
        this.directory = directory;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        // Delegate MUST verify active/valid before fetching internal permissions.
        return delegate.introspect(token)
            .flatMap(this::enrichValidatedPrincipal);
    }

    private Mono<OAuth2AuthenticatedPrincipal> enrichValidatedPrincipal(
            OAuth2AuthenticatedPrincipal principal) {

        Object rawSubject = principal.getAttribute("sub");
        if (!(rawSubject instanceof String)) {
            return Mono.error(invalid("Missing string subject"));
        }
        String subject = (String) rawSubject;
        if (subject.isBlank()) {
            return Mono.error(invalid("Blank subject"));
        }

        Object audience = principal.getAttribute("aud");
        if (!audienceMatches(audience)) {
            return Mono.error(invalid("Token audience is not this API"));
        }

        return directory.findBySubject(subject)
            .switchIfEmpty(Mono.error(
                invalid("Subject is unknown to local directory")))
            .map(profile -> {
                Map<String, Object> attributes =
                    new LinkedHashMap<>(principal.getAttributes());

                // Only ADD claims from the directory.
                // Do not overwrite sub, aud, scope, active, exp, client_id.
                attributes.put("display_name", profile.displayName());
                attributes.put("department", profile.department());

                Set<GrantedAuthority> authorities =
                    new LinkedHashSet<>(principal.getAuthorities());

                for (String role : profile.roles()) {
                    if (!PERMITTED_ROLES.contains(role)) {
                        throw new IllegalStateException(
                            "Directory contains an unexpected role");
                    }
                    authorities.add(new SimpleGrantedAuthority(
                        "ROLE_" + role));
                }

                return (OAuth2AuthenticatedPrincipal)
                    new DefaultOAuth2AuthenticatedPrincipal(
                        principal.getName(), attributes, authorities);
            });
    }

    private boolean audienceMatches(Object claim) {
        if (claim instanceof String) {
            return expectedAudience.equals(claim);
        }
        if (claim instanceof Collection<?>) {
            return ((Collection<?>) claim).contains(expectedAudience);
        }
        return false;
    }

    private static OAuth2AuthenticationException invalid(String reason) {
        return new OAuth2AuthenticationException(
            new OAuth2Error("invalid_token", reason, null));
    }
}
```

**Why does every detail matter?**

1. `delegate.introspect(token)` performs token verification against the AS or trusted delegate. If `active=false`, revoked, or the introspection request fails, `flatMap` **does not run**.
2. `sub` must be a non-blank `String`; avoid unconditionally falling back to `principal.getName()` if the AS does not guarantee identity keys. In tests, `sub` matches the directory.
3. `aud` must contain `reports-api`. Providers vary between string and list `aud`, so the helper supports both; missing `aud` is rejected per the demo API's policy.
4. `directory.findBySubject(subject)` runs **reactively**. `switchIfEmpty` rejects unknown subjects; directory errors are not swallowed to grant fake privileges.
5. `new LinkedHashMap<>(principal.getAttributes())` **copies** attributes without mutating the delegate's or another user's map.
6. `new LinkedHashSet<>(principal.getAuthorities())` **preserves `SCOPE_` authorities** while deduplicating.
7. Roles come solely from the directory and must be in `PERMITTED_ROLES`. Invalid roles fail instead of creating arbitrary `ROLE_...` authorities.
8. `DefaultOAuth2AuthenticatedPrincipal(principal.getName(), attributes, authorities)` preserves the original principal identity while adding controlled fields and roles.
9. Neither JWTs nor opaque tokens are cached in this class, nor are raw tokens logged or returned in profile responses.
10. Validation failures are signaled via `OAuth2AuthenticationException` with code `invalid_token`, allowing Spring Security to reject Bearer authentication properly.

**Production note:** A subject from another AS or tenant could also be named `alice`. Replace `findBySubject` with `findByIssuerTenantSubject` or an equivalent verified mapping before supporting multiple issuers. Add checks for disabled accounts, employment status, organization affiliation, and token audience/`client_id` policies as business requires.

## 11. SecurityWebFilterChain and API Configuration

### 11.1. src/main/java/demo/opaque/SecurityConfiguration.java

```java
package demo.opaque;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    ReactiveOpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${app.opaque.introspection-uri}") String uri,
            @Value("${app.opaque.client-id}") String clientId,
            @Value("${app.opaque.client-secret}") String clientSecret,
            @Value("${app.opaque.audience}") String audience,
            UserDirectory directory) {

        ReactiveOpaqueTokenIntrospector delegate =
            SpringReactiveOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(clientId)
                .clientSecret(clientSecret)
                .build();

        return new EnrichingOpaqueTokenIntrospector(
            delegate, directory, audience);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector introspector) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .pathMatchers("/api/profile").authenticated()
                .pathMatchers("/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers("/api/admin")
                    .access((authentication, context) ->
                        authentication.map(auth -> {
                            boolean hasScope = auth.getAuthorities().stream()
                                .anyMatch(a -> a.getAuthority()
                                    .equals("SCOPE_admin"));
                            boolean hasRole = auth.getAuthorities().stream()
                                .anyMatch(a -> a.getAuthority()
                                    .equals("ROLE_REPORT_ADMIN"));
                            return new AuthorizationDecision(
                                hasScope && hasRole);
                        }))
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(opaque ->
                    opaque.introspector(introspector)))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            // Demo API accepts explicit Bearer headers only, no browser cookies.
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
```

Highlights:

- `SpringReactiveOpaqueTokenIntrospector` itself calls the AS endpoint with client credentials.
- `EnrichingOpaqueTokenIntrospector` **wraps** the delegate rather than replacing token validation with an unconditional directory lookup.
- `.oauth2ResourceServer(...opaqueToken(...introspector(...)))` explicitly wires the custom introspector into the WebFlux chain. Do not confuse this with `.jwt()` for a JWT Resource Server.
- `/api/reports` requires the AS-issued OAuth2 scope (`SCOPE_reports.read`).
- `/api/admin` requires **both** `SCOPE_admin` and `ROLE_REPORT_ADMIN`: having a local role alone is insufficient if the AS did not grant the client the admin scope.
- The public `/health` rule reaches the controller **only when the request does not carry an invalid Bearer token**; requests with invalid Bearer headers may still be rejected by the authentication filter even on public paths.
- `httpBasic` and `formLogin` are disabled so this API does not use user passwords or browser redirects.
- `csrf.disable()` is **only valid in a stateless API model using explicit `Authorization: Bearer` headers**. If the same app uses session cookies, forms, or browser-auto-sent Basic auth, design CSRF protection separately rather than copying this setting verbatim.

### 11.2. src/main/java/demo/opaque/ApiController.java

```java
package demo.opaque;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    public record ProfileView(
        String sub,
        String displayName,
        String department) {}

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("OK");
    }

    @GetMapping("/api/profile")
    public Mono<ProfileView> profile(
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {
        return Mono.just(new ProfileView(
            principal.getAttribute("sub"),
            principal.getAttribute("display_name"),
            principal.getAttribute("department")));
    }

    @GetMapping("/api/reports")
    public Mono<String> reports() {
        return Mono.just("reports OK");
    }

    @GetMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin OK");
    }
}
```

The profile API returns only the three needed fields. It **does not expose** all attributes, the access token, the introspection response, client secrets, or unnecessary internal permissions. `@AuthenticationPrincipal` pulls the principal from the **Spring Security authentication context**, not from untrusted query parameters or headers. The new fields `display_name`/`department` are populated by the decorator.

## 12. Test Fixtures: Fake Delegate with the Same Contract

The project intentionally avoids depending on a real AS in tests. The test fixture class simulates **verified delegate results**, including tokens with matching or mismatched scopes/audiences and inactive tokens. This simulation **does not replace** HTTP introspection request/response tests against an AS.

### 12.1. src/test/java/demo/opaque/DemoIntrospectionFixtures.java

```java
package demo.opaque;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

final class DemoIntrospectionFixtures {

    private DemoIntrospectionFixtures() {}

    static OAuth2AuthenticatedPrincipal active(
            String sub, List<String> scopes, String audience) {
        Map<String, Object> attributes = new HashMap<>();
        attributes.put("sub", sub);
        attributes.put("scope", scopes);
        attributes.put("aud", List.of(audience));
        attributes.put("active", Boolean.TRUE);

        List<GrantedAuthority> authorities = new ArrayList<>();
        for (String scope : scopes) {
            authorities.add(new SimpleGrantedAuthority("SCOPE_" + scope));
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            sub, attributes, authorities);
    }

    static OAuth2AuthenticationException invalid(String detail) {
        return new OAuth2AuthenticationException(
            new OAuth2Error("invalid_token", detail, null));
    }

    static ReactiveOpaqueTokenIntrospector delegate() {
        return token -> Mono.defer(() -> {
            return switch (token) {
                case "alice-read" -> Mono.just(
                    active("alice", List.of("reports.read"), "reports-api"));
                case "alice-noscope" -> Mono.just(
                    active("alice", List.of(), "reports-api"));
                case "alice-admin-scope" -> Mono.just(
                    active("alice", List.of("admin"), "reports-api"));
                case "bob-profile" -> Mono.just(
                    active("bob", List.of("profile.read"), "reports-api"));
                case "admin-full" -> Mono.just(
                    active("admin", List.of("reports.read", "admin"),
                        "reports-api"));
                case "admin-profile-only" -> Mono.just(
                    active("admin", List.of("profile.read"), "reports-api"));
                case "wrong-audience" -> Mono.just(
                    active("alice", List.of("reports.read"), "payments-api"));
                case "unknown-user" -> Mono.just(
                    active("unknown", List.of("reports.read"), "reports-api"));
                case "missing-sub" -> Mono.just(
                    new DefaultOAuth2AuthenticatedPrincipal(
                        "anonymous-sub",
                        Map.of("aud", List.of("reports-api"),
                            "active", Boolean.TRUE),
                        List.of()));
                default -> Mono.error(invalid(
                    "Token is inactive or absent"));
            };
        });
    }
}
```

Note: `"alice-read"` and `"admin-full"` are merely **test token names** recognized by the fake delegate. In real applications, opaque tokens are random secrets issued by the AS; **never** build a production introspector with a `switch(token)` like this. Errors from the fake delegate simulate invalid tokens to test deny behavior and do not replace `SpringReactiveOpaqueTokenIntrospector`'s real `active=false` handling.

## 13. Unit Tests: Accurate Enrichment, No Privilege Escalation

### 13.1. src/test/java/demo/opaque/EnrichingIntrospectorTests.java

```java
package demo.opaque;

import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EnrichingIntrospectorTests {

    private final UserDirectory directory =
        new InMemoryUserDirectory();

    private ReactiveOpaqueTokenIntrospector subject() {
        return new EnrichingOpaqueTokenIntrospector(
            DemoIntrospectionFixtures.delegate(),
            directory, "reports-api");
    }

    private static Set<String> authorities(
            OAuth2AuthenticatedPrincipal principal) {
        return principal.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }

    @Test
    void activeAliceGetsDisplayNameAndDepartment() {
        StepVerifier.create(subject().introspect("alice-read"))
            .assertNext(principal -> {
                assertEquals("alice", principal.getName());
                assertEquals("Alice Tran",
                    principal.getAttribute("display_name"));
                assertEquals("finance",
                    principal.getAttribute("department"));
            })
            .verifyComplete();
    }

    @Test
    void scopeAuthorityIsPreservedWhenRoleIsAdded() {
        StepVerifier.create(subject().introspect("alice-read"))
            .assertNext(principal -> {
                Set<String> granted = authorities(principal);
                assertTrue(granted.contains("SCOPE_reports.read"));
                assertTrue(granted.contains("ROLE_REPORT_READER"));
                assertFalse(granted.contains("ROLE_REPORT_ADMIN"));
            })
            .verifyComplete();
    }

    @Test
    void trustedAdminGetsDirectoryRoleAndOriginalScopes() {
        StepVerifier.create(subject().introspect("admin-full"))
            .assertNext(principal -> {
                Set<String> granted = authorities(principal);
                assertTrue(granted.contains("SCOPE_admin"));
                assertTrue(granted.contains("SCOPE_reports.read"));
                assertTrue(granted.contains("ROLE_REPORT_ADMIN"));
                assertEquals("Admin Kim",
                    principal.getAttribute("display_name"));
            })
            .verifyComplete();
    }

    @Test
    void havingAdminScopeDoesNotInventAdminDirectoryRole() {
        StepVerifier.create(subject().introspect("alice-admin-scope"))
            .assertNext(principal -> {
                Set<String> granted = authorities(principal);
                assertTrue(granted.contains("SCOPE_admin"));
                assertFalse(granted.contains("ROLE_REPORT_ADMIN"));
            })
            .verifyComplete();
    }

    @Test
    void inactiveTokenNeverCallsUserDirectory() {
        AtomicBoolean called = new AtomicBoolean();
        UserDirectory spy = sub -> {
            called.set(true);
            return Mono.empty();
        };

        ReactiveOpaqueTokenIntrospector subject =
            new EnrichingOpaqueTokenIntrospector(
                token -> Mono.error(
                    DemoIntrospectionFixtures.invalid("inactive")),
                spy, "reports-api");

        StepVerifier.create(subject.introspect("invalid"))
            .expectError(OAuth2AuthenticationException.class)
            .verify();
        assertFalse(called.get());
    }

    @Test
    void wrongAudienceIsRejectedBeforeDirectoryLookup() {
        StepVerifier.create(subject().introspect("wrong-audience"))
            .expectError(OAuth2AuthenticationException.class)
            .verify();
    }

    @Test
    void missingSubjectIsRejected() {
        StepVerifier.create(subject().introspect("missing-sub"))
            .expectError(OAuth2AuthenticationException.class)
            .verify();
    }

    @Test
    void unknownDirectorySubjectFailsClosed() {
        StepVerifier.create(subject().introspect("unknown-user"))
            .expectError(OAuth2AuthenticationException.class)
            .verify();
    }

    @Test
    void delegateAttributesAreNotMutated() {
        OAuth2AuthenticatedPrincipal original =
            DemoIntrospectionFixtures.active(
                "alice", List.of("reports.read"), "reports-api");

        ReactiveOpaqueTokenIntrospector decorated =
            new EnrichingOpaqueTokenIntrospector(
                token -> Mono.just(original),
                directory, "reports-api");

        StepVerifier.create(decorated.introspect("opaque"))
            .assertNext(enriched -> {
                assertTrue(enriched.getAttributes()
                    .containsKey("display_name"));
                assertFalse(original.getAttributes()
                    .containsKey("display_name"));
                assertTrue(authorities(original)
                    .contains("SCOPE_reports.read"));
                assertFalse(authorities(original)
                    .contains("ROLE_REPORT_READER"));
            })
            .verifyComplete();
    }

    @Test
    void directoryFailurePropagatesWithoutGrantingRights() {
        UserDirectory failed = sub ->
            Mono.error(new IllegalStateException(
                "Directory is unavailable"));
        ReactiveOpaqueTokenIntrospector decorated =
            new EnrichingOpaqueTokenIntrospector(
                DemoIntrospectionFixtures.delegate(),
                failed, "reports-api");

        StepVerifier.create(decorated.introspect("alice-read"))
            .expectError(IllegalStateException.class)
            .verify();
    }

    @Test
    void delegateIsSubscribedOnlyWhenPipelineIsSubscribed() {
        AtomicInteger subscriptions = new AtomicInteger();
        ReactiveOpaqueTokenIntrospector lazyDelegate = token ->
            Mono.defer(() -> {
                subscriptions.incrementAndGet();
                return Mono.just(
                    DemoIntrospectionFixtures.active(
                        "alice", List.of("reports.read"),
                        "reports-api"));
            });
        ReactiveOpaqueTokenIntrospector decorated =
            new EnrichingOpaqueTokenIntrospector(
                lazyDelegate, directory, "reports-api");

        Mono<OAuth2AuthenticatedPrincipal> pipeline =
            decorated.introspect("alice-read");
        assertEquals(0, subscriptions.get());

        StepVerifier.create(pipeline)
            .expectNextCount(1)
            .verifyComplete();
        assertEquals(1, subscriptions.get());
    }
}
```

There are **11 unit tests**, executed via JUnit 5 + Reactor `StepVerifier` without needing a Spring `ApplicationContext`. They prove:

- Internal permissions are fetched only after the delegate succeeds.
- User Alice receives display name/department and `ROLE_REPORT_READER`.
- `SCOPE_reports.read` remains intact; `ROLE_REPORT_ADMIN` is not granted to Alice.
- Holding scope `admin` alone does not produce `ROLE_REPORT_ADMIN` unless the directory grants it.
- Wrong audience, missing subject, unknown subject, and directory errors all fail to yield an authorized principal.
- Original principal and authorities are **never mutated**.
- The publisher is lazy: before subscription, the lazy delegate does not execute, preventing side effects outside the reactive pipeline.

## 14. HTTP Tests: Bearer Authentication Through Real WebFlux

The HTTP test suite uses Spring's `ApplicationContext`, `WebTestClient`, and a **custom `@Primary` `ReactiveOpaqueTokenIntrospector` in tests**. That sends requests with `Authorization: Bearer alice-read` through **Spring Security's Bearer filter + custom decorator + authorization policies**, without calling an AS. Unlike `mockOpaqueToken()`, these tests actually execute our custom introspector code (with a fake delegate).

### 14.1. src/test/java/demo/opaque/HttpOpaqueTokenTests.java

```java
package demo.opaque;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
@Import(HttpOpaqueTokenTests.TestIntrospectionConfiguration.class)
class HttpOpaqueTokenTests {

    @TestConfiguration
    static class TestIntrospectionConfiguration {

        @Bean
        @Primary
        ReactiveOpaqueTokenIntrospector fakeForHttpTests(
                UserDirectory directory) {
            return new EnrichingOpaqueTokenIntrospector(
                DemoIntrospectionFixtures.delegate(),
                directory, "reports-api");
        }
    }

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec get(
            String path, String bearerToken) {
        return client.get().uri(path)
            .headers(headers -> {
                if (bearerToken != null) {
                    headers.setBearerAuth(bearerToken);
                }
            })
            .exchange();
    }

    @Test
    void healthIsPublic() {
        get("/health", null)
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void profileWithoutTokenIs401() {
        get("/api/profile", null)
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void invalidOpaqueTokenIs401() {
        get("/api/profile", "inactive")
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUserIs401UnderFailClosedPolicy() {
        get("/api/profile", "unknown-user")
            .expectStatus().isUnauthorized();
    }

    @Test
    void missingSubIs401() {
        get("/api/profile", "missing-sub")
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIs401() {
        get("/api/profile", "wrong-audience")
            .expectStatus().isUnauthorized();
    }

    @Test
    void aliceProfileIncludesTrustedDirectoryData() {
        get("/api/profile", "alice-read")
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.sub").isEqualTo("alice")
            .jsonPath("$.displayName").isEqualTo("Alice Tran")
            .jsonPath("$.department").isEqualTo("finance");
    }

    @Test
    void bobProfileIsIsolatedFromAlice() {
        get("/api/profile", "bob-profile")
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.sub").isEqualTo("bob")
            .jsonPath("$.displayName").isEqualTo("Bob Le")
            .jsonPath("$.department").isEqualTo("sales");
    }

    @Test
    void reportsReadScopeAllowsReports() {
        get("/api/reports", "alice-read")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports OK");
    }

    @Test
    void localRoleCannotReplaceMissingScope() {
        get("/api/reports", "alice-noscope")
            .expectStatus().isForbidden();
    }

    @Test
    void profileReadScopeCannotReadReports() {
        get("/api/reports", "bob-profile")
            .expectStatus().isForbidden();
    }

    @Test
    void onlyAdminScopeButNotAdminDirectoryRoleIs403() {
        get("/api/admin", "alice-admin-scope")
            .expectStatus().isForbidden();
    }

    @Test
    void adminRoleWithoutAdminScopeIs403() {
        get("/api/admin", "admin-profile-only")
            .expectStatus().isForbidden();
    }

    @Test
    void bothAdminScopeAndAdminDirectoryRoleAllowAccess() {
        get("/api/admin", "admin-full")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin OK");
    }

    @Test
    void httpBasicDoesNotReplaceOpaqueBearer() {
        client.get().uri("/api/profile")
            .headers(h -> h.setBasicAuth("alice", "password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownRouteIsDeniedEvenWithValidToken() {
        get("/api/private", "admin-full")
            .expectStatus().isForbidden();
    }
}
```

There are **16 HTTP tests**:

- Missing bearer, invalid token, unknown user, missing sub, and wrong audience are all rejected.
- Alice and Bob have **isolated** profile data, never seeing each other's user data.
- `SCOPE_reports.read` governs report read access and cannot be replaced by a local role.
- Admin requires **both** `SCOPE_admin` and `ROLE_REPORT_ADMIN`.
- Basic auth does not replace Bearer; unknown routes remain blocked by `denyAll`.

**Total suite: 27 tests** = 11 `StepVerifier` unit tests + 16 `WebTestClient` tests. That is the count of `@Test` methods across both test files, not a claim that Maven ran in the authoring environment.

### 14.2. Why Not Use Only mockOpaqueToken()?

Spring Security provides `SecurityMockServerConfigurers.mockOpaqueToken()`, which is suitable for testing authorization rules or controllers with a mock principal. However, it **bypasses** the introspector, so it cannot prove `EnrichingOpaqueTokenIntrospector` called the delegate or handled missing sub/audience. The suite here builds a **fake delegate** while still running the custom decorator, giving far better coverage of enrichment.

These tests **still do not prove** that HTTP client handling of AS `active=false`, TLS and Basic authentication for the introspection endpoint, or AS timeouts work properly. Those belong in separate integration tests against an AS sandbox or mock introspection HTTP server.

## 15. Running Maven and Practicing with curl

Requires JDK 17+, a compatible Maven installation, and files in the proper directories/packages.

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

**Expected** when example code and dependencies match: Maven Surefire runs **27 tests** with `BUILD SUCCESS`. That is an expected result by inspection, **not a claim of an observed Maven execution**. If errors occur, inspect `target/surefire-reports` and align versions/APIs rather than deleting tests.

After startup:

```bash
curl -i http://localhost:8080/health
```

Expected `HTTP 200`, body `OK`.

```bash
curl -i http://localhost:8080/api/profile
```

Expected HTTP **401** due to missing Bearer token.

Try a string not issued by a real IdP:

```bash
curl -i -H "Authorization: Bearer anything" \
  http://localhost:8080/api/profile
```

Because `id.example.test` is fake, introspection cannot verify the token. The request **must not** enter the API successfully; the exact status depends on failure handling when the AS is unreachable and may differ from the standard 401 for an invalid token.

To practice with real HTTP authentication:

1. Deploy/configure a sandbox AS with an HTTPS introspection endpoint and dedicated client credentials for the Resource Server.
2. Ensure the AS issues opaque access tokens and introspection returns `active=true`, `sub`, `aud` (or contract-equivalent claims), and `scope`.
3. Replace `app.opaque.introspection-uri`/client-id/client-secret/audience from a trusted source; never commit production secrets.
4. Use tokens issued by the real AS to call `/api/profile`, `/api/reports`, and `/api/admin`.
5. Observe 200/401/403 statuses; test revoked tokens, missing scopes, wrong audiences, and users absent from the directory.
6. Test changing a user's local role while they hold an active token to verify expected policy refresh/caching behavior.
7. If your organization uses multiple tenants/issuers, implement proper composite directory keys before shipping.

### 15.1. A Request Does Not Modify the Token at the AS

Enrichment modifies the **principal inside the Resource Server request**; it does not write claims back into the token or alter scopes/roles issued at the AS. An access token does not automatically gain `admin` just because the directory user is an admin. Changing scopes or token issuance requires updating registration/consent/grant policies at the AS and issuing a fresh token via the proper flow.

## 16. Optional UserInfo API Enrichment and Pitfalls

You can replace the local directory with a **trusted UserInfo endpoint** when the contract and scopes permit. The principle remains:

```text
AS introspection active=true
   |
   +--> verify sub/audience/client binding
   |
   +--> call trusted UserInfo with appropriate access token
   |
   +--> VERIFY UserInfo.sub == introspection.sub
   |
   +--> enrich profile fields only (name/email/...)
   |
   +--> take authorization roles only from an authoritative source
```

**Illustrative snippet, not a standalone runnable file**, inside a class with a trusted `WebClient userInfoClient`:

```java
return delegate.introspect(token)
    .flatMap(principal ->
        userInfoClient.get()
            .uri("/userinfo")
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .bodyToMono(UserInfo.class)
            .filter(info ->
                info.sub().equals(principal.getAttribute("sub")))
            .switchIfEmpty(Mono.error(
                new IllegalStateException("UserInfo sub mismatch")))
            .map(info -> addSafeProfileFields(principal, info)));
```

`UserInfo` and `addSafeProfileFields` are **illustrative** types/methods not defined in the project. You need a token with UserInfo-appropriate audience/scopes, a secure `WebClient` base URL, timeouts, TLS, error handling, and response validation. **Never use an arbitrary user-profile HTTP URL** supplied by the requester to fetch roles and grant `ROLE_ADMIN`.

If you only need a display name for a profile page, consider querying it post-authentication in the appropriate service instead of making a UserInfo call on every API request. If roles are needed for authorization, perform the lookup before access decisions, or use a domain-specific `ReactiveAuthorizationManager` with an explicit trust/latency contract.

### 16.1. Should You Trust Role Claims from Introspection?

If the AS is the **authoritative source for roles**, you can map them from the introspection response to authorities without a separate directory. However, verify the claim format, namespace, tenant, client ID, issuer contract, and role allowlist. If the AS only provides scopes while a local ERP manages up-to-date roles, let the directory decide roles. **Never merge roles from two sources with an OR rule that widens permissions** without clearly knowing which source is authoritative for each action.

### 16.2. Should You Use Method Security Instead of Mapping in the Introspector?

When permissions are checked **per resource object**—for example, "May Alice view report #381 in the finance department?"—mapping `ROLE_REPORT_READER` is only the first step. You also need business authorization in the service or a `ReactiveAuthorizationManager`/method security backed by database resource/tenant ownership. Never stuff permissions for millions of objects into the token principal; keep the principal small and stable, and check ownership at access time.

## 17. Operations and Security for Introspection + Enrichment

### 17.1. Latency and Availability

With default opaque tokens, **every request** may require an AS introspection call. Adding a `UserDirectory` means **two I/O calls** before the controller runs. That affects:

- End-to-end p95/p99 latency.
- Response times when the AS or directory slows down.
- HTTP connection/pool timeouts, retries, and backpressure.
- Load on the AS and directory during traffic spikes.
- Partial-failure behavior.

Design asynchronously with bounded timeouts and controlled retries. Never retry `invalid_token`, 401/403, or business errors endlessly; retry 5xx/timeouts with backoff and an appropriate budget. If the directory is down and local roles are mandatory, **never fall back to granting admin**.

### 17.2. Caching, Revocation, and Role Freshness

Caching introspection results or enriched principals lowers latency at the cost of delaying token revocation or role removal effects. You need:

- Non-guessable cache keys; never put raw tokens into logs, metrics, or analytics.
- TTLs not exceeding token `exp` or revocation/role-freshness policies; sometimes much shorter TTLs are required.
- Never key caches solely by `sub` when the same user holds multiple access tokens with different scopes/audiences.
- Multi-tenant cache isolation and versioning/invalidation when roles change.
- Never cache `active=true` forever; enforce fail-closed behavior when the AS is unavailable.
- Separate caches for introspection results and directory roles when their semantics differ.

Do not assume a JWT (if introspecting a JWT access token) automatically has "real-time revocation": every system has its own caching and propagation delays.

### 17.3. User Identity, Tenants, and Sensitive Data

Never map `sub` from issuer A onto a profile from issuer B. Email/username can change and are not tenant-aware identity keys. For multi-tenant APIs, construct `issuer + tenant + sub` keys and enforce row-level ownership. Put display name/department into the principal only when needed; **never auto-serialize the entire principal to JSON**.

Audit logs may record suitably anonymized subject/tenant IDs, outcomes, scope/role *permission names*, correlation IDs, and general reasons, **never recording Bearer tokens, `client_secret`, introspection Basic auth, or raw profile PII**.

### 17.4. Active Checks Cannot Be Replaced by Local Lookups

A user existing in the directory does not prove their Bearer token is still valid. Revoked tokens, wrong clients, wrong audiences, or missing scopes must still be rejected. Every flow must keep the delegate first. When a token is `active=false`, the AS may return minimal metadata; never try extracting a subject from a random token to look up the directory and "rescue" the request.

### 17.5. Error Mapping

- **Missing Bearer:** typically HTTP 401 with `WWW-Authenticate: Bearer`.
- **Introspection reports inactive/invalid:** authentication failure, typically HTTP 401.
- **Active token lacking `SCOPE_reports.read`:** authenticated, authorization failure, typically HTTP 403.
- **Active token where admin lacks local role or admin scope:** HTTP 403.
- **Directory/AS timeout or backend outage:** deny access; return 5xx/503 or standardized error per architecture/exception translation—do not claim every failure is 401.
- **Browser reports CORS error:** verify CORS headers on 401/403/5xx responses too; that is a separate layer.

In Spring Security, you can customize `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler`, and error mappings; always keep error payloads free of credentials and PII.

## 18. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Custom introspector returns DB principal without calling delegate | Authentication bypass / revoked tokens still work | Delegate introspection first; enrich only after active |
| Reading `X-Role` or `?role=ADMIN` to add `ROLE_ADMIN` | Privilege escalation | Take roles only from trusted AS/directory |
| `.map(principal -> directory.findBySubject(...))` | Produces `Mono<Mono<...>>`, never fetches user | Use `flatMap` when calling async sources |
| `.block()` inside introspector | Blocks Netty event loop | Compose `Mono`, non-blocking repository |
| `.subscribe()` and immediately returning principal | Race conditions, lost errors, undetermined permissions | Return one composed publisher for the whole chain |
| Replacing `principal.getAuthorities()` with local roles only | Loses `SCOPE_...` from AS | Copy original authorities before adding |
| Casting `scope` directly to `String` | Type mismatch depending on converter | Preserve delegate authorities or normalize types |
| Overwriting `sub`, `aud`, `exp`, `scope` | Alters identity/trust constraints | Add new metadata only; preserve original claims |
| User missing in directory defaults to `REPORT_READER` | Wrongful privilege grant | Fail-closed or explicit scopes-only policy |
| Using `sub` without issuer/tenant | Mixes users across issuers | Composite identity key per trust registry |
| Using `displayName`/email as user key | Renames, email collisions, takeover | Use validated stable subject ID |
| Checking active only, skipping aud/client binding | Accepts tokens meant for other APIs | Validate audience per AS contract |
| Catching directory error and falling back to admin | Privilege escalation | Deny and report infrastructure error |
| Using legacy `NimbusReactiveOpaqueTokenIntrospector` API | Deprecated and harder to maintain | `SpringReactiveOpaqueTokenIntrospector` builder |
| Using Servlet `OpaqueTokenIntrospector` in WebFlux | Wrong stack | `ReactiveOpaqueTokenIntrospector` |
| Enabling `.jwt()` when AS introspection is desired | Does not check revocation as required | Use `.opaqueToken(...)` |
| Using `mockOpaqueToken()` and claiming decorator is tested | Test bypasses introspector | Decorator unit tests + `WebTestClient` with fake delegate |
| Using local role instead of admin scope | Bypasses consent/scope | Check both `SCOPE_admin` and `ROLE_REPORT_ADMIN` |
| Caching by subject across all tokens | Scope/audience/token mix-up | Cache per token/policy, short TTL, tenant isolation |
| Raw opaque token in logs | Credential leak | Redact Authorization/secrets/tokens |
| UserInfo `WebClient` using URL from request | SSRF, token exfiltration | Trusted fixed base URI endpoints only |
| Not verifying `UserInfo.sub` | Merges another user's profile | Compare against trusted introspection `sub` |
| AS timeout returning stale principal indefinitely | Revoked tokens remain usable | Fail closed or bounded cache TTL policy |
| Enriched principal holds excessive PII | Privacy breach | Include only required attributes |

## 19. Self-Check Exercises

**Question 1.** What does `ReactiveOpaqueTokenIntrospector.introspect` return?  
**Answer:** `Mono<OAuth2AuthenticatedPrincipal>` for a verified valid token; emits an error if the token is invalid per contract.

**Question 2.** Why must the delegate be called before fetching roles?  
**Answer:** A user existing in the directory does not prove their token is still active. Delegation ensures the AS verified the token before local roles are granted.

**Question 3.** Alice's active token has `scope=reports.read`. The directory adds `ROLE_REPORT_READER`. Does `hasAuthority("SCOPE_reports.read")` still work?  
**Answer:** Yes, provided the custom principal **preserves the delegate's authorities**.

**Question 4.** Is `SCOPE_admin` the same as `ROLE_REPORT_ADMIN`?  
**Answer:** No. One comes from the AS via an OAuth2 scope, and the other from the trusted directory; sensitive endpoints can require both.

**Question 5.** The introspection result has `active=true` but no `sub`; how should the API respond?  
**Answer:** If the API needs user identity to map roles/identity, reject the token and require the AS to supply a stable subject per contract; never guess `sub` from email or headers.

**Question 6.** `active=false` while the directory lists Alice with `ROLE_REPORT_ADMIN`; should authentication succeed?  
**Answer:** No. The delegate rejects the token first, so enrichment never runs.

**Question 7.** Why use `flatMap` instead of `map` when calling an R2DBC directory?  
**Answer:** Because the directory returns `Mono<UserProfile>`; `flatMap` flattens the publisher instead of creating a nested `Mono`, preserving errors and cancellation.

**Question 8.** Why check audience even when introspection says active?  
**Answer:** A token can be active yet intended for another Resource Server; audience checks prevent token substitution.

**Question 9.** What is the role of `DefaultOAuth2AuthenticatedPrincipal`?  
**Answer:** It packages the principal name, attributes, and updated authorities cleanly after enrichment.

**Question 10.** Does `mockOpaqueToken()` verify real HTTP introspection and `active=false`?  
**Answer:** No. It creates a mock Authentication; to test the decorator, invoke your custom class or register a fake delegate in the WebFlux chain.

**Question 11.** Does a directory outage allow reusing cached permissions forever?  
**Answer:** No. You need TTL/role-revocation/failure policies; under this project's fail-closed policy, grant no roles when the directory is unavailable.

**Question 12.** What are introspection `client_credentials`?  
**Answer:** The Resource Server's credentials authorized by the AS to call the introspection endpoint, distinct from end-user access tokens and login passwords.

**Question 13.** Why preserve the original `sub` and `scope`?  
**Answer:** They are identity/authorization facts from the trusted AS; overwriting them from the directory could invalidly alter identity or permissions.

**Question 14.** Holding only local role `REPORT_ADMIN` without the admin scope, what happens at demo endpoint `/api/admin`?  
**Answer:** 403. The policy requires **AND** of `SCOPE_admin` + `ROLE_REPORT_ADMIN`.

**Question 15.** Can `ReactiveJwtDecoder` parse an opaque token?  
**Answer:** It does not satisfy introspection requirements. Opaque tokens are not guaranteed to be JWT-formatted and may require the AS to check active/revoked status.

**Question 16.** Why not cache solely by `sub`?  
**Answer:** The same subject can hold multiple tokens with different scopes, audiences, clients, and expirations; caching by subject alone mixes permissions.

**Question 17.** If a user profile holds sensitive info, should `/api/profile` return all attributes?  
**Answer:** No. Return only permitted fields, minimize PII, and check consent/privacy requirements.

**Question 18.** In a multi-issuer system, does `sub=alice` always refer to the same person?  
**Answer:** No. Use an issuer/tenant-qualified subject key and a trusted registry.

## 20. Implementation Checklist

- [ ] Use `ReactiveOpaqueTokenIntrospector` only in Spring WebFlux; never use the Servlet introspector.
- [ ] Delegate introspection to a trusted AS and check `active=true`.
- [ ] Keep introspection client credentials, TLS, and AS endpoint in secure configuration.
- [ ] Never grant permissions before the delegate succeeds.
- [ ] Validate `sub` identity and audience/client-binding matching the business API.
- [ ] Source roles from a trusted backend directory or trusted AS claims, never frontend-supplied data.
- [ ] Preserve original scopes/authorities when adding roles; never overwrite standard claims.
- [ ] Add only role names on the policy/allowlist; test against privilege escalation.
- [ ] Perform all enrichment I/O via `Mono.flatMap`, never `.block()` or ad-hoc `.subscribe()`.
- [ ] Handle empty/directory errors fail-closed or per an approved policy.
- [ ] Guard admin endpoints with AS scopes **and** local roles if required by the threat model.
- [ ] Include tests for active/inactive, missing-sub/audience, unknown subject, and role/scope differentiation.
- [ ] Run API tests for Bearer 200/401/403 and HTTP mock introspection integration tests before production.
- [ ] Never assume `mockOpaqueToken()` tests exercised the decorator.
- [ ] Keep secrets/tokens/PII out of logs, errors, and serialized principals.
- [ ] Ensure cache TTLs do not defeat rapid token/role revocation policies.
- [ ] Enforce tenant/issuer-aware subject identity, resource ownership checks, and least privilege.
- [ ] Design timeouts, retries/backoff, rate limits, observability, and fallbacks to fail closed.
- [ ] Run production on a supported Spring Boot/Security release.

## 21. Summary and Official Documentation

**Model to remember:**

```text
Resource Server opaque Bearer
  -> SpringReactiveOpaqueTokenIntrospector(delegate)
      -> AS introspection active=true
  -> validate sub/aud constraints
  -> trusted UserDirectory (reactive)
  -> DefaultOAuth2AuthenticatedPrincipal
      attrs = original + safe display metadata
      authorities = original scopes + trusted local roles
  -> AuthorizationWebFilter checks scopes AND/OR roles by endpoint policy
  -> HTTP 401 invalid token, HTTP 403 insufficient authority, HTTP 200 allowed
```

**Takeaway:** A custom introspector is a layer that **enriches identity/authorization data after token verification**—not a way to mint tokens, not a replacement for the OAuth2 Authorization Server, and never a place to derive permissions from untrusted data. In WebFlux, every step must stay in the same reactive chain so a request is authenticated only once the delegate, constraints, and directory lookup have all succeeded cleanly.

**References:**

- Spring Security 6.5 – Reactive OAuth2 Resource Server Opaque Token: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html
- Spring Security 6.5 – ReactiveOAuth2 introspection API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html
- Spring Security 6.5 – SpringReactiveOpaqueTokenIntrospector API/builder: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html
- Spring Security 6.5 – DefaultOAuth2AuthenticatedPrincipal: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html
- Spring Security – Reactive OAuth2 tests, mockOpaqueToken: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- IETF RFC 7662 – OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- IETF RFC 6750 – Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- IETF RFC 6749 – OAuth2 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP OAuth 2.0 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html

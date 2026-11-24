# Designing a Custom Principal with a Stable Identifier and Minimal Data

> **Scope:** Identity models in Spring Security (Servlet). This lesson explains how to design an application principal, choose a stable identifier, limit what goes into `SecurityContext`, and integrate the principal properly after authentication. Practical examples use Java 17+, Spring Boot, and HTTP Basic for easy observation; the same principles apply to sessions, JWTs, and OIDC with appropriate identity mapping.

## 1. The Practical Problem: Usernames and Emails Are Not Durable Identifiers

Suppose the `users` table has two rows:

| id | username | email | display_name |
| --- | --- | --- | --- |
| `550e8400-e29b-41d4-a716-446655440000` | `an` | `an@example.test` | An |
| `dc42f6ca-4e97-4d78-bbb3-a2720196e351` | `binh` | `binh@example.test` | Binh |

Today An changes their username from `an` to `an.nguyen` or updates their email. If orders store `owner_username = "an"`, the system must update related records or risk failing to find the owner after a rename. If an old username can later be re-registered, using username as an ownership/authorization key is even more dangerous: data from the old account could be mistakenly linked to the new account.

Meanwhile, `users.id` can be designed to stay **immutable** throughout the account lifecycle. Orders simply store `owner_user_id` pointing to that ID. Changing username/email leaves ownership intact.

**Core idea:** an application-layer principal should carry a **stable internal identifier**, accompanied by only the few attributes genuinely needed for the current request. Authentication may use username/email to look up the record, yet business logic identifies the user by the verified ID.

Note: `Principal.getName()` is a display/representation name for the subject; it is **not automatically** an immutable business key. For a custom principal, design an explicit API like `userId()` so ownership checks use the exact ID.

## 2. What Is a Principal and Where Does It Live in Spring Security?

`Principal` represents a subject within a security context. Java defines `java.security.Principal` with `getName()`. In Spring Security, `Authentication` carries the primary details:

- `getPrincipal()`: the object representing the subject; may be `UserDetails`, `Jwt`, `OidcUser`, a string, or a custom principal.
- `getCredentials()`: authentication proof, such as a password; usually needs to be erased after verification.
- `getAuthorities()`: rights the framework can use for authorization.
- `isAuthenticated()`: token state; never use this alone to conclude a real user is logged in because anonymous tokens exist.

Spring Security stores the request's `Authentication` in `SecurityContext`; in synchronous Servlet apps, the context is accessed via `SecurityContextHolder`, and the framework handles setting/clearing it across the request lifecycle.

```text
Client sends credentials (untrusted)
          |
          v
AuthenticationFilter / login mechanism
          |
          v
AuthenticationManager -> AuthenticationProvider
          |                  |
          |                  +-- verifies credentials, account, identity source
          v
Authenticated Authentication
    | principal = AppPrincipal(userId, username)
    | authorities = granted authority set
    | credentials = null / properly erased
          |
          v
SecurityContext of the request
          |
          +--> @AuthenticationPrincipal: retrieve trusted userId
          |
          +--> Authorization: check authorities and business rules
```

Where the custom principal is **issued** matters critically: it must be created by an authentication mechanism **after proof is validated**, or mapped from a verified token/identity provider. Creating `AppPrincipal(id)` straight from client-supplied query/body/headers and building an "authenticated" token breaks the trust boundary.

## 3. What Criteria Should a Stable Identifier Meet?

A good ID for an application principal typically satisfies these criteria:

1. **Unchanged when display attributes change:** username, email, phone number, profile name, and avatar can all change.
2. **Never reused for another subject:** locking/deleting an account must never allow its old ID to belong to someone else.
3. **Clear uniqueness scope:** globally unique ID or `(tenantId, userId)` pair if user IDs are unique only per tenant.
4. **Assigned by an authoritative source:** DB, identity service, or verified mapping from an authenticated provider.
5. **Grants no privileges merely by guessing the ID:** both UUIDs and sequential numbers are identifiers, not secrets for authentication.
6. **Passed across layers with an explicit type:** `UUID` or a value object such as `UserId` beats ad-hoc username strings in every service.
7. **Avoids coupling to mutable data:** resource ownership, audit actor IDs, and foreign keys should use the stable ID.

`UUID` is easy to illustrate, yet a system can use `long`, ULID, or another internal code provided immutability and scoped uniqueness hold. A UUID **does not replace authorization**; a user who knows Binh's UUID must still be denied reading Binh's data.

### Multi-Tenant Systems

If ID `42` can exist in both tenant A and tenant B, storing only `userId=42` in the principal is insufficient to distinguish them. You can use:

```java
record AppPrincipal(java.util.UUID tenantId, java.util.UUID userId, String username) {}
```

This is a **data sketch**, not a finished custom principal. Add `tenantId` only when it is part of the verified identity scope; never take tenant from an unverified self-asserted header. When accessing resources, verify both tenant and user/permissions. Even if user IDs are globally unique, tenant may still be needed as **authorization context** without necessarily being part of the identity key.

### Federated Identities from an Identity Provider

In OIDC, the `(issuer, subject)` pair is usually the meaningful identifier within a trusted issuer's scope. The subject `sub` must not be assumed unique across issuers; email is not a durable key, even when email verification status is present. An application can maintain a mapping table:

```text
identity_links:
  issuer           subject          internal_user_id
  https://idp-A    abc-123          550e8400-e29b-41d4-a716-446655440000
  https://idp-B    x-999            550e8400-e29b-41d4-a716-446655440000
```

Accounts from two providers **must only be linked** to the same ID when a trusted account-linking workflow genuinely proves/authorizes it. Never auto-merge accounts solely because emails match.

## 4. Principle of Minimal Data in the Principal

Do not place an entire `User` entity or account query result into `Authentication.getPrincipal()` just because the framework allows it.

| Data | Should it go into custom principal? | Reason |
| --- | --- | --- |
| Stable `userId` | **Yes** | Trusted reference key for business logic, audits, ownership |
| `tenantId` when part of identity scope | Conditionally | Needed to distinguish identity/permission scope in multi-tenant apps |
| Short, non-secret `username` | As needed | Useful for `getName()`, controlled logs; may go stale after rename |
| `displayName`, avatar | Usually **no** | Mutable UI data; load from profile service when rendering |
| Email, phone number, address | Usually **no** | PII, mutable, increases leak risk via serialization/logs |
| Raw password, password hash, API key, access token | **No** | Secrets or verification data; does not belong in a minimal identity model |
| JPA entity, lazy collections, bidirectional relations | **No** | Risk of lazy-loading errors, reference cycles, data leaks, mutable state |
| `authorities` | Usually stored on **Authentication** | Spring Security already provides `getAuthorities()`; avoid conflicting authority sources |
| Rarely used profile fields | **No** | Bloats memory/session and increases stale data |

There is no single fixed field list for every application. A service needing account type or region for policy enforcement may carry verified attributes, provided data origin and refresh rules are explicit. **The fewer non-essential fields, the less stale data and exposure surface.**

### Immutable Design

In Java 17+, a `record` fits a small identity snapshot well:

```java
import java.security.Principal;
import java.util.UUID;

record AppPrincipal(UUID userId, String username) implements Principal {
    @Override
    public String getName() {
        return username;
    }
}
```

This is an **illustrative snippet**; place it in the proper package and file/enclosing class to use. The record exposes `userId()` and `username()` accessors with no setters; it is not an entity and holds no password. `getName()` lets standard Java/Spring integrations read a name, while ownership checks use `userId()`.

If the app uses session serialization or clustered sessions, consider the `Serializable` contract, payload versioning, and refresh strategy; when needed, declare the record to implement `Principal, Serializable`. In the HTTP Basic demo below, we observe the principal per request.

## 5. Complete Example: Provider Verifies Credentials Then Builds a Minimal Principal

This example intentionally separates three structures:

- `StoredAccount`: persistence model, **holding the password hash** and source authorities; used only by the authentication layer.
- `AppPrincipal`: result identity, holding only `UUID userId` and `username`; **holds no password hash**.
- `Authentication`: Spring Security result, holding `AppPrincipal` and `GrantedAuthority` instances after verification.

To keep boundaries clear, the example uses a custom `AuthenticationProvider` for username/password and an in-memory account store. In real projects, prefer standard mechanisms like `DaoAuthenticationProvider`/`UserDetailsService` when suitable, or OAuth2 Resource Server converters for tokens; a custom provider is warranted when there is an explicit reason, such as separating a public principal from a credential-bearing record.

**Prerequisites:** Java 17+, a Spring Boot Servlet project with Spring Web and Spring Security starters, and a configured Gradle/Maven wrapper. With Spring Initializr, generate a project with **Spring Web** and **Spring Security**, keeping a Spring Boot version compatible with your Java version.

Create the single file `src/main/java/com/example/principaldemo/PrincipalDemoApplication.java`:

```java
package com.example.principaldemo;

import java.security.Principal;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PrincipalDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PrincipalDemoApplication.class, args);
    }
}

// Identity allowed to reach controllers/services.
// Contains no password hash, email, token, or JPA entity.
record AppPrincipal(UUID userId, String username) implements Principal {
    @Override
    public String getName() {
        return username;
    }
}

// Separate storage model, used only by the provider during authentication.
record StoredAccount(
        UUID id,
        String username,
        String passwordHash,
        boolean enabled,
        List<String> authorityNames) {
}

final class AccountStore {
    private final Map<String, StoredAccount> byUsername;

    AccountStore(StoredAccount account) {
        this.byUsername = Map.of(account.username(), account);
    }

    StoredAccount findByUsername(String username) {
        return byUsername.get(username);
    }
}

@Configuration(proxyBeanMethods = false)
class DemoSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AccountStore accountStore(PasswordEncoder encoder) {
        StoredAccount account = new StoredAccount(
                UUID.fromString("550e8400-e29b-41d4-a716-446655440000"),
                "an",
                encoder.encode("demo-password"),
                true,
                List.of("orders:read"));
        return new AccountStore(account);
    }

    @Bean
    AuthenticationProvider demoAuthenticationProvider(
            AccountStore accounts,
            PasswordEncoder encoder) {

        return new AuthenticationProvider() {
            @Override
            public Authentication authenticate(Authentication request)
                    throws AuthenticationException {

                if (!(request instanceof UsernamePasswordAuthenticationToken)) {
                    return null;
                }

                Object credential = request.getCredentials();
                if (!(credential instanceof String password)) {
                    throw new BadCredentialsException("Bad credentials");
                }

                StoredAccount account = accounts.findByUsername(
                        request.getName());

                // Only a successful verification yields a trusted principal.
                if (account == null
                        || !account.enabled()
                        || !encoder.matches(password, account.passwordHash())) {
                    throw new BadCredentialsException("Bad credentials");
                }

                AppPrincipal principal = new AppPrincipal(
                        account.id(), account.username());

                List<GrantedAuthority> authorities = account.authorityNames()
                        .stream()
                        .map(name -> (GrantedAuthority)
                                new SimpleGrantedAuthority(name))
                        .toList();

                return UsernamePasswordAuthenticationToken.authenticated(
                        principal,
                        null, // Do not carry password into result Authentication.
                        authorities);
            }

            @Override
            public boolean supports(Class<?> type) {
                return UsernamePasswordAuthenticationToken.class
                        .isAssignableFrom(type);
            }
        };
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            AuthenticationProvider demoAuthenticationProvider)
            throws Exception {

        return http
                .authenticationProvider(demoAuthenticationProvider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers("/orders/my")
                            .hasAuthority("orders:read")
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class IdentityController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/me")
    String me(@AuthenticationPrincipal AppPrincipal principal) {
        return "id=" + principal.userId()
                + "; username=" + principal.username();
    }

    @GetMapping("/orders/my")
    String myOrders(@AuthenticationPrincipal AppPrincipal principal) {
        return "ownerId=" + principal.userId();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin ok";
    }
}
```

### Why Does the Example Use a Custom Provider Instead of Cramming Everything into `UserDetails`?

`UserDetailsService` normally loads `UserDetails` containing the password hash, account flags, and authorities for `DaoAuthenticationProvider` to check. That is the standard choice and works well in many apps. Still, returning raw `UserDetails` as the principal can leave unnecessary fields or a password hash in `Authentication`, depending on the implementation and credential erasure. Putting a full JPA entity into `UserDetails` makes data control even harder.

In the example above, `AccountStore` holds authentication data; the provider verifies the password **before** creating `AppPrincipal`. `UsernamePasswordAuthenticationToken.authenticated(...)` is called only in the verified branch, with credentials set to `null`. The rest of the app never needs to know how passwords are stored.

In production, a custom provider must also address account locking, timing/user enumeration, MFA, rate limiting, login auditing, exception separation, session/token lifecycles, and synchronization with backing stores. This code is a **learning demo** for the credential-vs-principal boundary, not a complete production-ready login system.

### Running with a Build Tool

From the Gradle project root:

```bash
./gradlew bootRun
```

Or, for a Maven project:

```bash
./mvnw spring-boot:run
```

On PowerShell, use `.\gradlew.bat bootRun` or `.\mvnw.cmd spring-boot:run`. Because the file imports Spring types, **you cannot run `javac` alone** without Spring Boot's classpath/dependencies.

In another terminal:

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:demo-password http://localhost:8080/me
curl -s -u an:demo-password http://localhost:8080/orders/my
curl -i http://localhost:8080/me
curl -i -u an:wrong http://localhost:8080/me
curl -i -u an:demo-password http://localhost:8080/admin
curl -s -u an:demo-password "http://localhost:8080/me?userId=00000000-0000-0000-0000-000000000000"
```

On Windows PowerShell, if `curl` is aliased to another cmdlet, use `curl.exe` for the equivalent commands.

**Exact bodies of the first three commands in the demo:**

```text
pong
id=550e8400-e29b-41d4-a716-446655440000; username=an
ownerId=550e8400-e29b-41d4-a716-446655440000
```

**The three commands with `-i`:** return HTTP statuses **401**, **401**, and **403** respectively. Header details and error bodies depend on version/configuration. The last command receives the same body as a valid `/me` call: the `userId` query value is ignored for identity resolution, so it cannot override the principal's UUID. This assumes you are running the exact demo app without other security chains or filters interfering.

**Note:** HTTP Basic only Base64-encodes credentials and requires HTTPS in real use; never use demo passwords outside localhost/dev. Matching BCrypt password hashes in `StoredAccount` is the right direction, though not sufficient by itself to meet all account-protection needs.

## 6. Key Verification Checkpoints in the Code

Examine two distinct moments in sequence:

**Before authentication:** Spring Security builds a `UsernamePasswordAuthenticationToken` request holding the username/password from the Basic Authorization header; `request.getName()` is a self-asserted username, not yet trustworthy. `AccountStore.findByUsername` looks up the record by username yet **does not authenticate** the caller merely by finding an account.

**After authentication:** `PasswordEncoder.matches(password, account.passwordHash())` confirms the credential; only then does the provider build:

```java
AppPrincipal principal = new AppPrincipal(
        account.id(), account.username());

return UsernamePasswordAuthenticationToken.authenticated(
        principal, null, authorities);
```

This is a **snippet from the full provider** above. The trusted constructor/factory is called only after successful verification, never to mark client data as "logged in".

In the controller:

```java
@GetMapping("/me")
String me(@AuthenticationPrincipal AppPrincipal principal) {
    return "id=" + principal.userId()
            + "; username=" + principal.username();
}
```

`@AuthenticationPrincipal` extracts `Authentication.getPrincipal()` for the current request. The controller does not re-query login data, does not accept a caller-supplied `userId`, and never touches a password hash. With a custom principal, keep types and contracts aligned between the authentication mechanism and the web/controller layer.

**Authorities are distinct from the principal.** The principal answers "who"; `GrantedAuthority` on `Authentication` helps the framework answer part of "what is allowed". Someone holding `orders:read` still needs object/tenant checks when the application enforces resource-level access control.

## 7. Passing Minimal Identity to the Business Layer

In a larger application, controllers can pass only the needed ID and authority/context to services. Conceptual example:

```java
@GetMapping("/orders/mine")
List<OrderView> mine(@AuthenticationPrincipal AppPrincipal principal) {
    return orderService.findVisibleForOwner(principal.userId());
}
```

This is a **design snippet**, compiling only when `OrderView`, `orderService`, and matching imports/beans exist. Business queries should then use this server-verified ID as a parameter:

```sql
SELECT id, status, total
FROM orders
WHERE owner_user_id = :authenticatedUserId;
```

This is illustrative SQL; table/column names depend on schema. The essential point is that `authenticatedUserId` comes from the trusted principal.

When accessing a resource by ID, **object-level permission checks** are still required:

```text
GET /orders/987

1. Security filter authenticates request and produces AppPrincipal(userId=A).
2. Authorization checks matching API permission if applicable.
3. Service loads order 987.
4. Service/Policy verifies order's owner_user_id is A
   or subject has a special policy-permitted privilege.
5. Only when valid does it return the data.
```

Never take `ownerUserId` from a request body or query to decide who the logged-in owner is; on order creation endpoints, the server assigns the owner from the principal. If acting "on behalf of" another account is required, enforce an explicit delegation policy and record both the real actor and the target subject.

### Auditing and Logging

Record the **stable actor ID** as the trace key, alongside correlation/request ID, action type, target object, and timestamp. Username/display name can aid log UI readability, never as the sole key. Avoid logging full `Authentication` or `principal.toString()` because future principal fields could inadvertently leak PII/claims/secrets.

## 8. When Username/Email Changes, or an Account Is Locked

A principal is normally a **snapshot** of identity at authentication time. Distinguish immutable identifiers from data that must be refreshed.

### Changing Username or Email

- `userId` stays unchanged; foreign keys and audit actor IDs stay intact.
- `username` inside an existing session/token may retain the old value until the context refreshes or the user logs in again.
- UI profile info should be read from the profile service by `userId` when fresh data is needed.
- If login by email is supported, email is merely a **lookup key** at authentication time, never an owner ID or permission grant.

Before and after example:

| Time | `userId` | `username` | Order ownership |
| --- | --- | --- | --- |
| Before rename | `550e8400-...` | `an` | Keyed by `userId` |
| After rename | `550e8400-...` | `an.nguyen` | Still same `userId` key |
| Unrefreshed session | `550e8400-...` | May still be `an` | `userId` key unchanged |

### Locking Accounts, Revoking Rights, or Deleting Users

A principal holding a stable ID **does not mean the account stays valid forever**. If an account is locked after login, active sessions or unexpired tokens can still hold the old authentication. Operational policies must define:

- Invalidating active sessions or forcing re-login.
- Short TTLs and revocation/rotation mechanisms for tokens.
- Checking live account status/permissions at critical steps.
- Retaining audit reference keys even when an account is disabled or deleted under retention policy.

Do not copy `enabled` from the DB into the principal assuming it stays fresh forever. Privileged actions in particular may need live policy lookups rather than relying solely on an old snapshot.

## 9. Principal Design with JWT, OIDC, or Service Accounts

Using `AppPrincipal` in the demo works because the custom provider **deliberately constructs that exact type**. Never assume every `Authentication.getPrincipal()` across all protocols is `AppPrincipal`.

### JWT Resource Server

When verifying a JWT, Spring Security typically builds `JwtAuthenticationToken` with `Jwt` as the principal; declaring `record AppPrincipal` does not automatically convert tokens into it. To give business code a unified model, you can:

1. Verify signature, issuer, expiration, and audience via resource server configuration.
2. Map subject or trusted claims plus issuer to an internal user ID via a managed mapping.
3. Produce the application identity/context through a controlled converter/resolver instead of casting `Jwt` to `AppPrincipal`.
4. Keep scopes/authorities on `Authentication` or a well-defined trusted authority structure.
5. Never treat `sub` as globally unique across issuers; never trust self-asserted claims from JSON request bodies.

An easy-to-remember flow:

```text
Signed JWT --(signature/iss/aud/exp validation)--> Verified Jwt
       |
       +-- issuer + subject --> trusted account mapping --> internal userId
       |
       +-- verified scope/claims --> authorities
       |
       v
Application identity for business (userId, possibly tenantId)
```

This is a **design pattern**; Spring Security does not perform internal account mapping automatically unless configured.

### OIDC Login

When signing in via an Identity Provider, `OidcUser` carries provider-specific claims and identification details. The application should translate to an application identity when needed: internally an immutable `userId`, with IdP `issuer + sub` linking the account. Fields like `email`, `preferred_username`, and `name` are provider-contract identity/display attributes that can change and have their own verification rules.

### Service-to-Service

An authenticated client/service can have a **service principal** with no human `userId`. Forcing every principal into a human user record confuses "calling service" with "end user". Model actor kinds explicitly:

```java
sealed interface Actor permits UserActor, ServiceActor {}

record UserActor(java.util.UUID userId) implements Actor {}
record ServiceActor(String clientId) implements Actor {}
```

This is an **illustrative model** expressing the distinction; it does not integrate with Spring Security automatically without a converter/provider. If an API accepts both users and services, policies must distinguish which operations require a real user and which are for services. Never propagate end-user rights across services solely via a plain text header.

## 10. Design Choices That Look Convenient Yet Cause Bugs

| Common trap | Consequence | Fix |
| --- | --- | --- |
| Using username/email as owner key | Renaming, reuse, or normalization differences break ownership | Use an immutable internal user ID |
| Using `getName()` as an ID without checking contract | Depending on principal, name may be username, subject, or email | Use `userId()` accessor or typed actor ID |
| Putting an entire JPA entity in principal | Lazy loading, cycles, mutations, sensitive data in session | Use a minimal persistence-free DTO/record |
| Putting password hash/access token in principal | Credentials may leak via logs, serialization, or memory | Keep in verification layer, out of result principal |
| Calling `new AppPrincipal(request.userId)` and treating as logged in | Client impersonates another account | Construct only after trusted authentication |
| Treating UUID as "unguessable so secure enough" | IDs are not secrets; leaking IDs still enables IDOR without policy | Enforce resource and tenant authorization |
| Putting roles in principal and a separate list in `Authentication` | Two authority sources can drift | Put authorities under one unified contract |
| Assuming every `getPrincipal()` is `AppPrincipal` | JWT/OIDC/anonymous/service use different types | Use converters/resolvers or typed actors |
| Caching username, roles, enabled forever in session | Stale info after policy changes | Design refresh/revocation strategies |
| Letting public endpoints cast a non-null principal | Anonymous or missing application principal | Protect endpoints or handle null/anonymous cleanly |
| Using IDs without tenant isolation | User IDs collide across tenants; cross-tenant data leaks | Scope IDs clearly, composite keys, or trusted tenant mapping |
| Using principal `toString()` as primary log format | Leaks data or breaks stability when fields are added | Log controlled actor ID/operation fields |

One more detail: `record` gives **structural** immutability, yet if a record holds a mutable `List` or `Map`, its contents can still change. With a minimal principal holding only `UUID` and `String`, that issue is avoided; if collections are needed, use immutable copies like `List.copyOf(...)` and limit included fields.

## 11. Testing Key Invariants

Rather than testing only "did login succeed", verify identity-protection behaviors:

1. **Valid login:** with `an:demo-password`, `/me` returns the exact internal UUID, not just the username.
2. **Invalid login:** wrong password or unknown user produces no trusted `Authentication` and never returns a claimed account's principal.
3. **Spoofed `userId`:** using An's Basic credentials while adding `?userId=<Binh's ID>`; business logic must still see An as actor.
4. **Username/email change:** account keeps the same user ID; owner foreign keys and audits remain intact. Display info may require refreshing.
5. **Missing authority:** authenticated yet calling `/admin` without `ROLE_ADMIN` receives 403 in the demo.
6. **Object-level boundary:** holding `orders:read` yet requesting an order owned by another account/tenant must be denied by policy.
7. **Other principal types:** when integrating JWT/OIDC/service accounts, resolvers must emit the right application identity or reject cleanly—never silent `ClassCastException` in domain logic.
8. **Data leakage:** JSON responses, logs, sessions/tokens, and debug endpoints reveal no password hashes, raw credentials, or PII profiles.
9. **Revocation/disable:** after locking an account or changing roles, verify when existing requests are rejected per designed policy.
10. **Frontend independence:** changing client-submitted fields must never alter the identity received from `@AuthenticationPrincipal`.

For multi-tenant apps, add test cases where user IDs collide across two tenants if the schema allows it. For federated login, add cases with identical email across different `issuer + sub`, preventing unverified auto-linking.

### Self-Check Questions

**Question 1.** Why not use email as the `orders.owner` foreign key?  
**Answer:** Email can change, be revoked/reused, and is not always globally unique. An immutable internal ID keeps ownership relationships stable.

**Question 2.** Is adding `UUID userId` to a custom principal enough to replace authentication?  
**Answer:** No. An ID is merely identity data; only after valid proof verification may a trusted `Authentication` carrying that principal be issued.

**Question 3.** Why does the example separate `StoredAccount` and `AppPrincipal`?  
**Answer:** The storage record needs password hash/status/authorities for authentication, whereas controllers/services need only the ID and short name; separating them reduces bloat and credential exposure risk.

**Question 4.** Is a client knowing someone else's UUID enough to read that person's resources?  
**Answer:** No. A UUID is only an identifier. The server must still authenticate the actor and enforce policy on the specific resource.

**Question 5.** If we add `@AuthenticationPrincipal AppPrincipal` to an existing JWT API, will it definitely work immediately?  
**Answer:** No. JWT authentication typically uses `Jwt` as its principal. You need a configured mapping/converter or application abstraction to receive the expected type.

**Question 6.** An's username changed while the session still holds the old principal; should ownership rely on the ID or username?  
**Answer:** Rely on the immutable, verified `userId`. The username in the snapshot may be stale; reload from the profile source when fresh display data is needed.

## 12. Design Conclusion

A sound custom principal defines clearly **which trusted source maps the subject**, **how stable and unique the ID is within its scope**, **what data is genuinely needed for the request**, and **who refreshes or revokes identity/authorities on change**.

For typical user-facing applications, a record like `AppPrincipal(UUID userId, String username)` is a solid starting point. It is created **after** authentication, accessed via `@AuthenticationPrincipal`, and passes `userId` to business logic for object-level permission checks. `Authentication` still holds authorities and Spring Security still performs authorization; a custom principal does not replace those mechanisms.

**Rule of thumb:** Use an **immutable** identifier to know *who*, keep the principal **minimal** to avoid unnecessary data, and check **actual permissions** when deciding *what they may do*.

### Official References

- [Spring Security 7 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/architecture.html)
- [Spring Security — UsernamePasswordAuthenticationToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html)
- [Spring Security — Basic Authentication](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/basic.html)
- [Spring Security — Authentication Principal](https://docs.spring.io/spring-security/reference/7.0/servlet/integrations/servlet-api.html)
- [Spring Security — HTTP Authorization](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html)

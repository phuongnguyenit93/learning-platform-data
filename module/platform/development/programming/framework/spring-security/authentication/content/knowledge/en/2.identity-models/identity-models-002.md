# Principal and How It Differs from a Business Account in the Database

In Spring Security, a **principal** is the identity representation of the subject being authenticated or already authenticated. A **business account in the database** (business account / account entity) is the record owned by the application to store a durable identifier, account status, profile details, and business relationships. The two concepts are related, yet they are not the same object, do not always have a one-to-one mapping, and should not be used interchangeably.

This lesson belongs to the **Identity Models** group in Spring Security Authentication. After this lesson, you should be able to answer: "Who does Spring Security consider the caller of the request?", "Where do I get the internal account ID?", "Why shouldn't I return the raw entity as the principal?", and "If the login name, authorities, or account status changes, what happens to a principal already stored in a session/JWT?".

## 1. Understanding the Four Related Data Layers

| Concept | Nature | Example | What is it used for? |
|---|---|---|---|
| **Principal** | Object/identifier representing the accessing subject in the security context | `CurrentActor(accountId, loginName)`, `UserDetails`, `Jwt`, `OidcUser` | Identifying the caller to enforce security and application logic |
| **Authentication** | Spring Security object wrapping the principal, authentication details, state, and authorities | `UsernamePasswordAuthenticationToken`, `JwtAuthenticationToken` | Recording which mechanism authenticated the request and what authorities it holds |
| **Account entity / database row** | Persistent data managed by the business system | `Account(id, email, passwordHash, status, ...)` | Managing profile, credentials, status, data relationships, and change history |
| **Profile / response DTO** | Data permitted to be exposed to the user or API client | `MyProfileDto(id, displayName, avatarUrl)` | Returning appropriate data without leaking internal information |

**Principal is not synonymous with a password**, nor is it necessarily a login name, a `users` table row, or the user profile returned to a frontend. The principal identifies **who is calling**, whereas the account entity is part of a long-lived persistence model that the system can use to verify, link, and govern that identity.

For example: an employee is assigned `account_id = 9c...` in the `accounts` table and logs in with email `linh@company.example`. After authentication, Spring Security can hold a principal containing only `accountId`, `loginName`, and a few minimal attributes. The email can change; the `account_id` primary key used for data references stays the same. If the employee changes their display name in the database, an old principal in a session may still hold the old name until refreshed.

## 2. Where Does Principal Live in Spring Security?

In a Servlet application, Spring Security typically stores the request's `Authentication` in `SecurityContext`. It can be accessed via `SecurityContextHolder` or injected directly into a controller by Spring MVC:

~~~text
HTTP request
  -> SecurityFilterChain
  -> Reads and verifies credentials/cookie/bearer token (depending on mechanism)
  -> Authenticated Authentication
       |- principal: the subject just identified
       |- authorities: set of authorities bound to this authentication
       |- credentials: proof; usually erased/not retained after authentication
       '- authenticated: state of the authentication token
  -> SecurityContext of the request
  -> Authorization: checks permissions for the action/resource
  -> Controller / Service
~~~

`Authentication` belongs to `org.springframework.security.core.Authentication` and has these key methods:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

Object principal = authentication.getPrincipal();
String name = authentication.getName();
Collection<? extends GrantedAuthority> authorities =
        authentication.getAuthorities();
boolean authenticated = authentication.isAuthenticated();
~~~

The snippet above illustrates the API and is **not a standalone Java program**: it assumes an `Authentication` is present in the context along with the required imports. In real applications, let Spring inject the principal or authentication into controllers whenever possible; avoid accessing the context across every layer merely for convenience.

### 2.1. What Type Does `Authentication.getPrincipal()` Return?

There is no single Java type across all authentication mechanisms:

| Mechanism or configuration | Common principal | Things to note |
|---|---|---|
| Username/password with `DaoAuthenticationProvider` | Object implementing `UserDetails`, e.g., `org.springframework.security.core.userdetails.User` or a custom type | May carry username, flags, and authorities from load time |
| Application-created principal | `CurrentActor`, a record/class with only safe attributes | Easy to carry a stable internal account ID |
| JWT resource server | `Jwt` inside `JwtAuthenticationToken` by default | Claims come from the verified token; database changes do not automatically update the JWT |
| OAuth2 Login / OIDC | `OAuth2User` or `OidcUser` | Information comes from the identity provider; needs linking to an internal account |
| Incomplete / anonymous user authentication | May be a string, unauthenticated token, or `AnonymousAuthenticationToken` | Do not cast the principal before verifying a valid context |

With `UsernamePasswordAuthenticationToken`, the principal can sometimes be a `String`, especially in certain manually constructed tokens; **do not** assume every principal casts to `UserDetails` or `AccountEntity`.

### 2.2. Is `getName()` the Account ID?

Not by default. `Authentication.getName()` typically derives a name from the principal according to the token/provider's convention: with username/password it is usually the username, with JWT it is usually the `sub` claim (claim name is configurable), and with a custom principal it is whatever `getName()` the application defines. It is **not automatically** the primary key of the internal accounts table.

If you use email/username as a foreign key on orders, audit logs, or ownership conditions, changing the email/username can break links. A common design is to use a **stable** internal ID, such as `UUID accountId`, for business relationships, while keeping email/login name as mutable attributes.

### 2.3. Principal Is Distinct from Authorities

The principal identifies the subject; `GrantedAuthority` describes roles/permissions attached to the authentication. They can vary independently. Two people sharing `ROLE_USER` are still two different principals; one person changing roles does not become a different person. With sessions or JWTs, authorities may be a **snapshot** from login/token-issuance time. If immediate permission revocation is required, you need a mechanism to update, check current state, or limit lifetime.

## 3. What Is a Business Account in the Database?

An application may have a table similar to:

~~~sql
CREATE TABLE accounts (
    id UUID PRIMARY KEY,
    login_name VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(320) UNIQUE,
    display_name VARCHAR(200) NOT NULL,
    password_hash VARCHAR(255),
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

This is an **illustrative schema**, not a mandatory schema or copy-paste DDL for every RDBMS. Real systems also include versioning/locking, per-tenant uniqueness, auditing, identity provider links, and data deletion policies.

- `id`: stable internal identifier used as a foreign key for business data.
- `login_name` / `email`: attributes used for logging in or contact, mutable and requiring proper verification workflows.
- `password_hash`: credential stored securely when the system handles passwords itself; may be absent if users only sign in via federated IdPs.
- `status`: account management state such as active, suspended, or pending verification; exact rules are defined by the business domain.
- `created_at` and audit metadata: support traceability, governance, and applicable compliance requirements.

Beyond `accounts`, a system may have `person_profiles`, `memberships`, `roles`, `external_identities`, or `service_accounts` tables. Not every principal has a corresponding human user: a machine-to-machine token may identify a service; an anonymous request has no account; one person may own multiple accounts across tenants; one internal account may link multiple sign-in methods.

**Why not use the account entity itself as the principal?**

1. **Reduce data exposure:** An entity may hold a password hash, email, phone number, private status, and internal metadata. A principal travels through many application layers; `toString()`, debug logs, serialization, or error payloads can leak unnecessary details.
2. **Avoid ORM coupling:** JPA entities carry lazy-loading proxies, object graph relationships, and transaction/persistence context ties. Keeping them in a session can trigger lazy-loading errors, stale data, or serialization issues during deployment.
3. **Separate lifecycles:** An account row lives across many logins; the principal of a single authentication/request can be a bounded snapshot.
4. **Stabilize contracts:** Changing the DB schema does not force changes to the security principal type or API clients.
5. **Support multiple identity sources:** A principal from JWT/OIDC may not immediately match an internal row; it must go through a controlled linking or account-provisioning step.

This **does not prohibit** implementing `UserDetails` from account data; the key is putting only the necessary attributes into the security context and avoiding placing a heavy persistence entity with relationships directly into the session.

## 4. Mapping Principal ↔ Account Across Authentication Models

### 4.1. Internal Username/Password

~~~text
Login name + password
   -> UserDetailsService / AuthenticationProvider
   -> Look up account by login name in repository
   -> Verify password hash and whether status allows login
   -> Create authenticated Authentication
        principal = CurrentActor(accountId, loginName, ...)
   -> Controller receives accountId and queries business data by ID
~~~

`UserDetailsService` has the contract `loadUserByUsername(String)`, commonly used by `DaoAuthenticationProvider` to load `UserDetails` for password authentication. It is not a service for managing all business operations on an account. `UserDetails` is a **security projection** or adapter over stored data: the framework needs the name, password hash, authorities, and certain status flags; domain services remain responsible for creating, updating, verifying, and closing accounts.

When you want a principal containing only an ID and safe attributes, you can use a custom provider/token like the runnable example in section 6, or build a carefully designed custom `UserDetails` and strip credentials from the authentication result.

### 4.2. JWT Resource Server

~~~text
Authorization: Bearer <JWT>
   -> Decode and verify signature, issuer, audience, expiration, ...
   -> Create JwtAuthenticationToken (principal is typically Jwt)
   -> Read verified subject/scope
   -> Map (issuer, subject) -> internal accountId if business logic needs it
   -> Enforce authorization policies and current status as required
~~~

`sub` is only meaningful within the scope of its issuer; if multiple identity providers are accepted, using the **(issuer, subject)** pair as the lookup key is generally safer than using `sub` alone. Do not treat the email in a JWT as a unique key unless the IdP guarantees email stability and verification. Do not auto-create accounts simply because any valid JWT presents an email.

A JWT can include `account_id` if issued by a trusted party under a clear contract, yet the backend must still validate the token completely. If externally issued JWTs have no knowledge of internal IDs, account mapping is the application's responsibility.

### 4.3. OAuth2 Login / OIDC

With OIDC Login, users can sign in at an IdP and the application receives an `OidcUser` with claims from the ID token/UserInfo per protocol. The data model typically looks like:

~~~text
identity_provider + external_subject
               |
               v
         external_identities
               |
             account_id
               |
               v
           accounts
               |
         domain relations
       (orders, projects, ...)
~~~

One internal account can link multiple identities, such as an internal password and a corporate account, or multiple IdPs; the system must provide a secure **link/unlink** flow, prevent account takeover via matching emails, require re-authentication for sensitive link changes, and restrict who can create links. The OIDC `sub` claim identifies the subject per issuer; the `email` claim is an attribute, not a default global linking key.

### 4.4. Multi-Tenant and Service Accounts

In multi-tenant applications, `accountId` alone is sometimes insufficient: the same person may belong to multiple tenants with different roles. Distinguish global identity (account/user id), membership (account id + tenant id), and permissions within a tenant. A tenant sent by the client is only a scope request that must be checked against real membership; never trust a `tenantId` query parameter to grant access.

For machine-to-machine traffic, the principal may be `service-client-42` or `ClientPrincipal`, with no row in a human `accounts` table. Security code should therefore never cast every principal to `HumanUserEntity`.

## 5. Design Rule: Store Little in the Principal, Query Properly in the Domain

An application principal as an immutable Java record:

~~~java
package example.identity;

import java.security.Principal;
import java.util.UUID;

public record CurrentActor(UUID accountId,
                           String loginName,
                           String displayName)
        implements Principal {

    @Override
    public String getName() {
        return loginName;
    }
}
~~~

This is a **standalone compilable class** if saved at `example/identity/CurrentActor.java` and compiled with Java 17+. It is only a data type/contract and does not create authentication by itself. By design it omits password hashes, addresses, and JPA entities. `accountId` is used for internal relations, and `getName()` returns a readable name per the `Principal` convention.

In a controller:

~~~java
@GetMapping("/me")
MyProfileDto me(@AuthenticationPrincipal CurrentActor actor) {
    return profileService.loadByAccountId(actor.accountId());
}
~~~

This is an **illustrative integration snippet**, assuming `MyProfileDto`, `profileService`, and the corresponding Spring MVC annotations exist; it is **not a complete program**. `@AuthenticationPrincipal` reads `Authentication.getPrincipal()` from the security context and supports the principal type created by the authentication mechanism. If authentication is a default JWT, you cannot receive `CurrentActor` simply by changing the parameter type: an appropriate conversion/mapping mechanism is required.

At the domain layer:

- Use `actor.accountId()`, established by the server from a valid authentication, as the identity basis.
- Load the current account from the repository when business logic needs live status, the latest profile, or current permissions.
- Check ownership/tenant on **the actual resource**, not solely on the fact that the principal has an ID.
- Return minimal DTOs; never return the raw `AccountEntity` or `Authentication` from an API unless explicitly intended.
- For background services or async tasks, pass the needed actor/identity through an explicit context; `SecurityContextHolder` in Servlet apps uses `ThreadLocal` by default and is not guaranteed to appear on another thread automatically.

## 6. Runnable Example with Spring Boot 3.3 / Java 17+

We will build a small API to clearly observe:

1. An in-memory `AccountStore` **simulating** an accounts table; each row has an ID, login name, display name, password hash, and enabled flag.
2. A provider checking the password and whether the account is enabled. When valid, the provider creates a clean `CurrentActor` principal.
3. The `/me` controller endpoint reads the principal; `/me/live` uses the principal's account ID to look up the row again just as a business service would.
4. A disabled account still exists in the store, yet new login attempts are rejected. This proves that having a database row does not imply having a valid principal.

### 6.1. Project Structure and Dependencies

~~~text
identity-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/identity/IdentityDemoApplication.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'identity-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.7'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

The example requires JDK 17+, a Gradle version compatible with Spring Boot 3.3.x, and network access to download dependencies on the first run. No database/JPA is needed because the account repository here is simulated. A real application replaces `AccountStore` with persistence/repositories and matching policies.

### 6.2. Complete Java Code

Create `src/main/java/example/identity/IdentityDemoApplication.java`:

~~~java
package example.identity;

import java.security.Principal;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class IdentityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdentityDemoApplication.class, args);
    }
}

// A business row simulating the accounts table. Do not put this record
// into SecurityContext and do not return it directly over HTTP.
record AccountRow(UUID id, String loginName, String displayName,
                  String passwordHash, boolean enabled) {}

// Compact principal carrying no password hash or JPA relationships.
record CurrentActor(UUID accountId, String loginName,
                    String displayName) implements Principal {
    @Override
    public String getName() {
        return loginName;
    }
}

// In-memory demo store; real apps use a repository with constraints and transactions.
class AccountStore {
    private final Map<String, AccountRow> byLoginName;

    AccountStore(PasswordEncoder encoder) {
        byLoginName = Map.of(
            "linh", new AccountRow(
                UUID.fromString("00000000-0000-0000-0000-000000000001"),
                "linh", "Linh", encoder.encode("demo-pass"), true),
            "khoa", new AccountRow(
                UUID.fromString("00000000-0000-0000-0000-000000000002"),
                "khoa", "Khoa", encoder.encode("demo-pass"), false)
        );
    }

    Optional<AccountRow> findByLoginName(String loginName) {
        return Optional.ofNullable(byLoginName.get(loginName));
    }

    Optional<AccountRow> findById(UUID id) {
        return byLoginName.values().stream()
                .filter(account -> account.id().equals(id))
                .findFirst();
    }
}

@Configuration(proxyBeanMethods = false)
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AccountStore accountStore(PasswordEncoder encoder) {
        return new AccountStore(encoder);
    }

    @Bean
    AuthenticationProvider accountAuthenticationProvider(
            AccountStore store, PasswordEncoder encoder) {
        return new AuthenticationProvider() {
            @Override
            public Authentication authenticate(Authentication request)
                    throws AuthenticationException {
                AccountRow row = store.findByLoginName(request.getName())
                        .orElseThrow(() ->
                            new BadCredentialsException("Invalid credentials"));

                String password = String.valueOf(request.getCredentials());
                if (!encoder.matches(password, row.passwordHash())) {
                    throw new BadCredentialsException("Invalid credentials");
                }
                if (!row.enabled()) {
                    throw new DisabledException("Account disabled");
                }

                CurrentActor actor = new CurrentActor(
                        row.id(), row.loginName(), row.displayName());
                Collection<? extends GrantedAuthority> authorities =
                        List.of(new SimpleGrantedAuthority("profile:read"));

                return UsernamePasswordAuthenticationToken.authenticated(
                        actor, null, authorities);
            }

            @Override
            public boolean supports(Class<?> authenticationType) {
                return UsernamePasswordAuthenticationToken.class
                        .isAssignableFrom(authenticationType);
            }
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationProvider provider)
            throws Exception {
        return http
            .authenticationProvider(provider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/info").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}

@RestController
class IdentityController {
    private final AccountStore store;

    IdentityController(AccountStore store) {
        this.store = store;
    }

    @GetMapping("/public/info")
    String publicInfo() {
        return "PUBLIC";
    }

    @GetMapping("/me")
    Map<String, Object> me(@AuthenticationPrincipal CurrentActor actor) {
        return Map.of(
            "accountId", actor.accountId().toString(),
            "loginName", actor.loginName(),
            "displayName", actor.displayName()
        );
    }

    @GetMapping("/me/live")
    Map<String, Object> meFromAccount(
            @AuthenticationPrincipal CurrentActor actor) {
        // Use the stable accountId verified by the provider;
        // do not take an accountId self-declared by the client.
        AccountRow account = store.findById(actor.accountId())
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));

        return Map.of(
            "accountId", account.id().toString(),
            "loginName", account.loginName(),
            "displayName", account.displayName(),
            "enabled", account.enabled()
        );
    }
}
~~~

**Reading the code along its boundaries:**

- `AccountRow` holds persistence data, including the password hash and `enabled` flag. It does not implement `Principal` and is not a DTO to return over the network.
- `AccountStore` looks up an account by login name during **authentication**, then supports querying by UUID when **business logic** needs it. In a real system, ID lookups should use an index/primary key rather than scanning `values()` as in the demo.
- `AuthenticationProvider` receives an unauthenticated request, fetches the row, and checks the password with BCrypt; it rejects `khoa`'s login because the account is disabled. This is illustrative authentication logic, not a full account lifecycle workflow.
- After verification, the provider constructs `CurrentActor` containing only the UUID and safe fields; the resulting token stores that principal and the `profile:read` authority. The raw password is not copied into the new principal; the returned token's credentials are `null`.
- `@AuthenticationPrincipal CurrentActor actor` only works because the application's provider actually produces a `CurrentActor`. Switching to OAuth2/JWT requires updating the principal mapping step to match the new provider.
- `/me` returns values from the **snapshot inside the principal**; `/me/live` returns data reloaded from the **account store**. The outputs match in the demo but can diverge once the database is updated.
- `provider` is explicitly registered as a bean via `http.authenticationProvider(provider)`. HTTP Basic is used solely to demonstrate requests/responses and is not a default choice for production apps.

### 6.3. Run and Observe

In the `identity-demo` directory, if a compatible Gradle Wrapper has been created:

~~~bash
./gradlew bootRun
~~~

If you do not have a wrapper yet, you can run `gradle bootRun` with a compatible installed Gradle, or generate the wrapper first. Spring Boot listens on port 8080 by default when no other port is configured.

In another Bash terminal:

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/public/info

curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/me

curl -s -o /dev/null -w '%{http_code}\n' \
  -u linh:wrong-password http://localhost:8080/me

curl -s -o /dev/null -w '%{http_code}\n' \
  -u khoa:demo-pass http://localhost:8080/me

curl -s -o /dev/null -w '%{http_code}\n' \
  -u linh:demo-pass http://localhost:8080/me

curl -s -o /dev/null -w '%{http_code}\n' \
  -u linh:demo-pass http://localhost:8080/me/live
~~~

Expected HTTP status codes in order:

~~~text
200
401
401
401
200
200
~~~

Inspect the JSON to verify `linh`'s principal ID:

~~~bash
curl -s -u linh:demo-pass http://localhost:8080/me
~~~

The expected JSON has the following fields/values (key order may vary):

~~~json
{
  "accountId": "00000000-0000-0000-0000-000000000001",
  "loginName": "linh",
  "displayName": "Linh"
}
~~~

At this point the database row still holds `passwordHash` and the `enabled` flag; `/me` does not expose them. Calling `/me/live` also includes `"enabled": true` fetched from the account store by internal ID. `khoa`'s request receives 401 even though Khoa's account row still exists.

**Intentional limitations of the demo:** in-memory data and sample passwords; HTTP Basic has no browser-style login screen or user session; no account update endpoints, auditing, MFA, role/ownership checks, or token revocation. Do not use `demo-pass` over unencrypted HTTP on a real network; use localhost for learning only. If you add write APIs with cookies/sessions, review CSRF and other protections matching your authentication model.

## 7. Differences Between Live Data and the Snapshot in a Principal

An often overlooked point: a principal is not a "live" connection to the accounts table.

| Event | Database record | Existing principal/session/token | What the system must decide |
|---|---|---|---|
| Email/login name changed | New value | May retain old name | When to update the principal; use durable IDs for foreign keys |
| Display name changed | New profile | May show old name | Which APIs load fresh profile data, which accept snapshots |
| Role revoked | Permissions table changes | Authorities may retain old roles | Revoke/refresh session/token or check live permissions |
| Account locked | `enabled=false` or `status=SUSPENDED` | Existing session/JWT may still validate | Mechanism to block requests using old credentials |
| Account deleted/closed | Row may be deleted, soft-deleted, or anonymized | Old ID may remain in sessions/logs | Block access, handle orphaned data, auditing, and retention |

### 7.1. Server-Side Sessions

When using sessions, `SecurityContext` can be stored and restored across requests depending on configuration. You should not assume every request automatically calls `UserDetailsService` again or queries the account. You must design session updates/revocation or live status checks whenever business logic demands immediate reaction.

If sessions are serialized (e.g., distributed sessions), the principal must be compatible with the serialization mechanism and application version upgrades. Stuffing a raw JPA entity, lazy associations, or sensitive data into the session increases both cost and risk.

### 7.2. Self-Contained JWTs

A JWT with a valid signature and expiration is typically checked without automatically querying the account database on every request. If roles or account status change mid-flight, an existing JWT does not update itself. Options include short-lived access tokens, revocation/denylists, token introspection, a security version, or live account/permission lookups depending on requirements; each approach has its own cost and latency trade-offs.

### 7.3. Do Not Treat `isAuthenticated()` as Guaranteeing a Real User

Spring Security can assign an `AnonymousAuthenticationToken` to an unauthenticated request; some anonymous tokens still report `isAuthenticated() == true` by token state. Distinguish anonymous access from authenticated users using `authenticated()` policies and appropriate security components, rather than writing `authentication != null && authentication.isAuthenticated()` and assuming a real account exists. If the app requires a local account, check the account mapping explicitly.

## 8. Data Safety and Trust Boundaries

**The trust anchor lies on the server after authentication.** Values sent by a frontend such as `userId`, `role`, or `email` are not a principal merely because they match a DB record.

Practical rules:

1. Never let the client choose an `accountId` to prove "who I am" when acting on its own behalf. Take the ID from the verified principal; for actions on behalf of others, enforce explicit authorization checks.
2. Never use `@RequestParam("userId")` or a JSON body `{"ownerId": "..."}` as a substitute for identity. Those may indicate the **target subject being acted upon**, and still require authorization checks.
3. Avoid storing/serializing passwords, password hashes, raw access/refresh tokens, secrets, and unnecessary private data inside the principal. Minimize `toString()` output and logs; if a custom `UserDetails` must carry a password hash during authentication, apply a proper credential erasure policy and be careful with caching.
4. Never use email as an unconditional IdP linking key. The `(issuer, subject)` pair must be verified from a valid token; account-linking flows need uniqueness constraints and protection against account takeover.
5. Do not rely solely on authorities in the principal for resource access: enforce ownership, tenant, object state, and least-privilege checks on the server.
6. Never embed entities with JPA relationships directly in `SecurityContext` or API responses. Use dedicated security projections and DTOs; control stale data in caches/sessions.
7. Avoid calling `SecurityContextHolder` directly inside every domain service. Pass `accountId`/`CurrentActor` as parameters or through a security facade for easier testing; do not drag the security framework into every entity.

## 9. Typical Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
|---|---|---|
| `(AccountEntity) auth.getPrincipal()` across all providers | `ClassCastException` or deep JPA coupling | Determine the actual principal type; use a custom projection or mapping adapter |
| Storing `email` as a foreign key on orders | Changing email breaks references or ownership checks | Use a stable internal account ID |
| Returning `AccountEntity` directly from `/me` | May expose hashes/private status and trigger lazy associations | Return only an allowed DTO |
| Letting the frontend send `currentUserId` to fetch "my" data | Risk of accessing another user's account (IDOR) | Read the subject from the security context and verify object permissions |
| Checking only `ROLE_USER` without checking tenant | May read another tenant's data | Check membership and tenant filters in queries |
| Assuming updating DB roles/status mutates old JWTs | Revoked permissions linger or violate expectations | Define clear token lifetimes, refresh/revocation, or live lookups |
| Using `sub` without issuer across multiple IdPs | External identifier collisions | Enforce uniqueness on `(issuer, subject)`, map cleanly to account ID |
| Reading `SecurityContextHolder` in an async thread and seeing null | Missing security context on another thread | Propagate identity explicitly or use an appropriate propagation mechanism |
| Taking email from login to auto-create an unverified account | Identity confusion / account takeover | Verify token, `email_verified` where relevant, secure link flow, and provisioning policy |

## 10. Design Scenarios and Self-Check Questions

**Scenario A – An employee changes their email.** The system has 10,000 orders pointing to their creator. After the email change, do business relationships stay intact? If the tables use `accountId` as the foreign key, yes. If email was stored as the identifier, complex migrations/dependencies are required. This is why a mutable principal name must be separated from a stable account ID.

**Scenario B – A user signs in with OIDC.** The IdP returns an ID token with `iss`, `sub`, and `email`. To locate the internal profile and permissions, the system must verify the token with the appropriate library/protocol, extract the provider identifier, and look up `external_identities` to find `accountId`. Never treat an arbitrary email as proof of an existing internal account.

**Scenario C – A JWT remains valid after an account is locked.** The account row changed to `SUSPENDED`, yet the API accepts the previously issued JWT. Which one is true? Both facts can be true at the same time: the JWT still passes token validation while the database changed. The design must define how locks are enforced in real time or within an acceptable delay window.

**Scenario D – A service bot has no user row.** A `client_credentials` token represents a service. A controller casting the principal to a human `UserDetails` will fail. Actor classification and separate policies are needed for service identities.

### Review Questions

1. **How do `Authentication` and `principal` differ?**  
   `Authentication` is the framework's security object holding the principal, authorities, credentials/state; `principal` is solely the representation of the subject.
2. **If `authentication.getName()` returns `linh@example.com`, can it be used directly as the internal primary key?**  
   No. It is a name per the provider/token contract and can change; the internal ID must be mapped and verified.
3. **Is `UserDetailsService` responsible for creating accounts and resetting passwords?**  
   Under the authentication contract, it loads `UserDetails` by username; account creation/updates/recovery belong to dedicated business services.
4. **Why can `/me` and `/me/live` return different display names?**  
   The principal can be a snapshot from authentication time; `/me/live` queries the current account.
5. **Does locking an account in the DB automatically clear sessions and all JWTs?**  
   No. An explicit session/token revocation or live status-checking strategy is needed.
6. **Can a principal exist without a human `accounts` row?**  
   Yes: service accounts, anonymous requests, unlinked external identities, or other actor types.
7. **Should an order update API take the owner ID from the request body to decide permissions?**  
   Never trust the body as identity; determine the actor from authentication and verify order ownership/tenant in the domain.

## 11. Project Adoption Checklist

- Clearly define the **principal type** for each authentication method; APIs/controllers must never cast blindly.
- Choose an **immutable internal `accountId`** key for business data; design external identity mappings with issuer + subject and uniqueness constraints.
- Keep the principal minimal, avoiding JPA entities/credentials/secrets; use DTOs for responses.
- Explicitly design which data is a **snapshot** in the principal/token and which data must be **read live** from the account/permission store.
- On every sensitive operation, take the principal from the verified security context, then enforce resource/tenant permissions on the server.
- Test disabled accounts, role changes mid-session, old JWTs, email changes, multiple IdPs, service principals, and anonymous requests.
- Test consistency between account status changes and session/token revocation mechanisms; never rely on assumed automatic updates.

**Remember:** **Principal answers "who is calling the request according to authentication?"; the account entity answers "which record does the system manage long-term?"**. Connect the two sides via durable identifiers and explicit trust rules. Separating security identity from persistence ensures correct handling of logins, profile updates, authorization, multiple identity providers, and access revocation.

### Official References

- Spring Security – [Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `SecurityContextHolder`, `SecurityContext`, `Authentication`, principal, and authorities.
- Spring Security – [UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html): contract for loading authentication data by username/password.
- Spring Security – [Spring MVC Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/mvc.html): injecting the principal into controllers with `@AuthenticationPrincipal`.

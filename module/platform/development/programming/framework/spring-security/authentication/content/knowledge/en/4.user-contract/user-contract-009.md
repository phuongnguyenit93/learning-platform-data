# Do Not Habitually Return Full Business-Data Entities as the Principal

**Module:** Spring Security – authentication. **Knowledge group:** User Contract.

## 1. The Problem: A Principal Is a Security Identity, Not the Entire Business Profile

In Spring Security, the **`principal`** is the object representing the subject that submitted an authentication request or is currently recognized by the system. After authentication, `Authentication.getPrincipal()` is commonly accessed from `SecurityContext`, from controllers via `@AuthenticationPrincipal`, or from authorization and audit code.

What is very tempting to do when starting with Spring Boot + Spring Data JPA is:

1. Having an `Account` or `UserEntity` holding id, username, password hash, email, address, phone number, roles, order relationships, organization, and transaction history.
2. Writing `UserDetailsService.loadUserByUsername(...)` and making that entity itself implement `UserDetails`.
3. Returning the raw entity from `UserDetailsService`, letting the provider put it into `Authentication.principal`.
4. On every request, grabbing `SecurityContextHolder.getContext().getAuthentication().getPrincipal()` and treating that entity as "the current user", even returning it straight from an API.

This approach **can run** in small applications, yet creates unintended coupling between business data, persistence, and security. It can leak data, drag along proxies/lazy loading, break session serialization, and leave permission or account-status info stale.

**Recommended principle:** Keep the principal a **small, clearly scoped representation derived from a verified source**; hold only the fields truly needed to identify/authorize. When a use case needs business information, load it through a repository/service with proper authorization checks and transactions.

This is a design decision, **not a rule that Spring Security forbids every entity from acting as a principal**. The goal is to avoid turning full entities into principals out of habit without analyzing data, lifecycle, and trust boundaries.

## 2. Four Concepts Commonly Mixed Together

| Component | Purpose | Typical Data | Typical Lifecycle |
| --- | --- | --- | --- |
| **JPA entity** (`AccountEntity`) | Persisting/mutating business domain state | ID, PII, password hash, status, JPA relationships, auditing | Persistence context and transaction; may be managed/detached |
| **`UserDetails`** | Supplying data needed by username/password providers to verify login | username, **temporary password hash for verification**, authorities, status flags | Loaded at authentication/cached per config; may become principal |
| **`Authentication`** | Describing an authentication request or a trusted result | principal, credentials, authorities, details, `isAuthenticated()` | Lives in the request's security context; may be stored in session |
| **Minimal principal** (`AppPrincipal`, `SafePrincipal`) | Carrying verified identity through web/security layers | stable userId, display username, verified tenantId if needed | Request/session/token mapping; does not hold the entire entity graph |

A `UserDetails` does not have to be a JPA entity. It can be the built-in `org.springframework.security.core.userdetails.User` or an application-defined `UserDetails` adapter.

Likewise, the post-authentication principal **is not always `UserDetails`**: JWT, OAuth2/OIDC, SAML, X.509, or custom authentication providers may return other objects. Do not force every principal into `UserEntity` or assume every mechanism involves a password.

### Responsibility-Aligned Identity Flow

~~~text
                   DB / domain repository
                     |
                     v
              AccountEntity (full)
               id, email, phone,
               password hash, roles,
               order history, ...
                     |
                     | intentional mapping
                     v
            UserDetailsService
                     |
                     v
        UserDetails (needed auth data)
               username, hash,
               authorities, flags
                     |
                     v
         DaoAuthenticationProvider
            + PasswordEncoder
                     |
                     v
       Authenticated Authentication
            |
            +--> minimal principal
            |    or auth-focused UserDetails
            |
            +--> verified authorities
                     |
                     v
               SecurityContext
                     |
             Controller / service
                     |
            uses userId, tenantId
                     |
                     v
       Query entity/DTO per use case
        + check permissions on fresh data
~~~

This model separates **"who is sending the request?"** from **"what are that person's current profile, address, orders, or status?"**.

## 3. Why Do Full Entities as Principals Cause Risk?

### 3.1. Expanding the Exposure Footprint of Sensitive Data

An entity may hold a password hash, personal email, phone number, date of birth, billing address, internal notes, anti-fraud flags, or permission lists. Putting the entire entity into the principal means that data can travel into:

- `SecurityContext` sitting in request memory or HTTP sessions;
- distributed session stores and session replicas;
- caches and serialization/deserialization pipelines;
- log statements for `authentication.getPrincipal()` or auto-generated `toString()`;
- debug snapshots, traces, exception reporting, or object mapping;
- controllers accidentally returning `principal` in JSON.

**You do not have to leak a raw password to have an incident.** Password hashes are also sensitive data: if stolen, attackers can attempt offline cracking. PII and internal operational info carry their own risks. The less data a principal holds, the smaller the blast radius if it gets logged or stored in an unexpected place.

`@JsonIgnore` on a few entity fields is not an adequate security boundary: it only affects certain JSON serialization mechanisms, without hiding data from `toString`, reflection, binary serialization, custom serializers, or other object graphs.

**What to do:** Explicitly choose which fields may appear in the principal, audit periodically, and never return `Authentication`/entities directly from endpoints just to "get the current user".

### 3.2. JPA Entities Carry Proxies, Relationships, and Lazy Loading

Suppose an entity has:

~~~java
@OneToMany(mappedBy = "account", fetch = FetchType.LAZY)
private List<OrderEntity> orders;
~~~

After login, a controller or logger calls `principal.getOrders()` in another request. The entity may have detached from `EntityManager` and the association may be uninitialized: risking `LazyInitializationException`. If a persistence context stays open, unexpected queries may run in unintended places, causing N+1 queries and overfetching.

Bidirectional relationships like `account.orders -> order.account -> account...` also easily trigger infinite recursion during JSON serialization if unconfigured. Switching to `FetchType.EAGER` to "fix the principal bug" typically introduces overfetching without fixing the architectural boundary.

**What to do:** Map the needed authentication fields into a projection/`UserDetails` **while the query is still inside an appropriate transaction**. When orders are needed, call a business service to query them under authorization policies. The principal does not need to own an entity graph.

### 3.3. Principals Have a Different Lifecycle from Transactions

Entities are managed within a persistence context and become detached once the context closes. Yet `Authentication` can outlive a single transaction, especially when Spring Security stores `SecurityContext` in an HTTP session.

If you keep an entity in the principal and mutate its fields in a later request, it becomes hard to tell whether the change is managed/persisted, detached, or an accidental mutation on a shared object. Never use the principal as a unit of data updates.

**What to do:** The principal holds only a stable identifier; the service takes that identifier, loads a fresh entity inside a transaction, checks tenant/permissions/status, and only then updates.

### 3.4. Serialization and Distributed Systems

When sessions are stored in Redis/databases or replicated across nodes, serializers may need to encode `SecurityContext`, `Authentication`, and the principal. JPA entities with Hibernate proxies, lazy collections, serializer-incompatible types, or references to non-`Serializable` objects can make saving/restoring sessions fail or slow down.

Not every architecture uses Java serialization, and not every entity is strictly unserializable. The issue is that **the principal becomes a cross-layer/cross-node transfer object** that entity graphs were never designed to serve as.

A small principal `record`/class with explicit types and tested serialization policies is much easier to evolve. If sessions persist across application versions, consider principal versioning/migration.

### 3.5. Account Changes Do Not Automatically Update Issued Principals

A user logs in at 9 AM with `ROLE_ADMIN`. At 10 AM another admin revokes that role. If the old `Authentication` in the session still holds the authorities granted at 9 AM, updating the entity in the DB **does not automatically** update the authority list stored in the context.

Similarly, locking a user, changing a username, switching tenants, or changing a password does not automatically invalidate an old session or a signed JWT.

Keeping an entity directly in the principal does not guarantee "always reading fresh data" either; on the contrary, it usually creates a **hard-to-manage snapshot**.

**What to do:** Have a strategy for session refresh/revocation/timeout, session locking, short-lived tokens, or fresh status checks at sensitive points. Freshness requirements depend on the operation's risk.

### 3.6. Equality, hashCode, and Mutable State

An entity implementing `equals()/hashCode()` based on a mutable business key, Hibernate proxy, or pre-persist unassigned ID can cause hard-to-reproduce bugs if used as a principal in maps/sets/session registries when state changes after login.

Furthermore, if the domain entity doubles as the user identity across the app, refactoring the schema, renaming a field, or altering a relationship can break authentication, sessions, and security tests at the same time.

**What to do:** Use a stable ID as the identity key; avoid including mutable business state in identity comparisons or cache keys. Identity should not depend on address, phone number, display name, or order count.

### 3.7. Easily Turning Authorization into Misreading Entity Data

If a controller checks `principal.getRole()` and trusts it immediately, the system may rely on stale info or the wrong tenant. Especially in multi-tenancy, an unscoped `role=ADMIN` can easily be misinterpreted as admin of all tenants.

Real authorization must clearly separate:

- **Verified identity:** userId, authentication method, selected and verified tenant.
- **Authentication authorities:** high-level rights used by Spring Security at check time.
- **Permissions on a specific resource:** which tenant the record belongs to, whether the user may act on that record, and whether policies just changed.

A minimal principal reduces confusion between **business attributes** and **security decisions**.

## 4. Which Fields Should You Pick for the Principal?

There is no single mandatory structure for every system, though you can start with:

~~~java
// Identity contract only; contains no persistence data.
public record AppPrincipal(
        long userId,
        String username,
        String tenantId
) implements java.io.Serializable {}
~~~

This is an **illustrative declaration**: fields must be verified data from a trusted source; if the system is not multi-tenant, omit `tenantId`. In tenanted systems, include only a membership-verified `tenantId`, never copying client-sent values unconditionally.

Evaluating each kind of data:

| Field | Put in Principal? | Considerations |
| --- | --- | --- |
| Stable `userId` | Usually yes | Trusted identity key for services to query fresh data |
| `username` | Maybe | Useful for display/audit; can change, do not use as sole key if renames are supported |
| `tenantId` | Conditionally | Must verify user truly belongs to tenant; prevent client self-declaration |
| Authorities/roles | In `Authentication.getAuthorities()` | Do not duplicate into diverging lists; needs lifecycle when permissions change |
| Display email | Only if truly needed | Can be PII or mutable; prefer query DTOs for UI |
| Password hash | Only in temporary `UserDetails` **before** password check | Do not keep in long-lived session principals after login |
| Raw password, refresh token, API secret | No | These are credentials; never place inside principals |
| Address, phone, purchase history | No by default | Load in services when the use case is authorized |
| JPA `@OneToMany` / `@ManyToOne` | Avoid | Never attach entity graphs/proxies to context |
| `EntityManager`, service, repository | No | Those are dependencies, not identity |
| Account lock flags | Needed for login check; post-login principal depends on policy | State can change, so design revalidation or revocation |

**The minimalism principle does not mean keeping only a `String username`.** If business logic needs an immutable ID, a verified tenant, or authentication strength info for authorization, include that exact piece with clear justification. Trim useless fields and sensitive data.

## 5. Why Does UserDetails Still Hold a Password Hash While Long-Lived Principals Should Not?

This is an important point to avoid a broken "fix": if you strip the password hash **before** `DaoAuthenticationProvider` checks it, the username/password mechanism cannot authenticate.

Standard flow with `DaoAuthenticationProvider`:

1. `UsernamePasswordAuthenticationFilter` or equivalent filter creates an unauthenticated `UsernamePasswordAuthenticationToken` carrying the username and raw password sent by the client over HTTPS.
2. `ProviderManager` delegates the request to `DaoAuthenticationProvider`.
3. The provider calls `UserDetailsService.loadUserByUsername(username)`. Returned data must include a password hash verifiable by `PasswordEncoder`, authorities, and account status.
4. The provider checks the raw password against the hash, checks account locked/disabled/expired flags, and constructs an authenticated `Authentication`, usually with `UserDetails` as principal.
5. `ProviderManager` calls `eraseCredentials()` on the result by default if it implements `CredentialsContainer`. `org.springframework.security.core.userdetails.User` supports this interface and can clear its own password after authentication.

**The optimization goal is keeping the password hash only where genuinely needed for verification**, not removing it from the verification mechanism itself.

A simple approach is having `UserDetailsService` map the record/entity into a fresh `org.springframework.security.core.userdetails.User` on each load:

~~~java
// ILLUSTRATIVE CODE INSIDE UserDetailsService; "account" is data
// fetched by the repository by username inside an appropriate transaction.
return User.withUsername(account.getUsername())
        .password(account.getPasswordHash())
        .authorities("ROLE_READER")
        .disabled(!account.isEnabled())
        .accountLocked(account.isLocked())
        .build();
~~~

`User` holds only the required login fields; it **is not an entity** and carries no JPA relationships. After authentication, the password in this object can be erased **without mutating any JPA-managed entity**.

**Cache warning:** If `UserDetailsService` returns a shared cached `UserDetails` object, when `ProviderManager` erases credentials on the principal, that cached object may lose its password hash. Subsequent logins can then fail. Return a separate copy for results, decouple the cache from the `Authentication` principal, or design provider/caching per docs; never assume credential erasure leaves shared references untouched.

If you need `userId` in the principal while using default `DaoAuthenticationProvider`, you can write a **small custom `UserDetails`** holding `userId`, `username`, temporary password hash, and flags/authorities; it is still not a full entity. Ensure proper credential erasure, especially with caching. Another option is building a minimal session principal in a trusted component **after authentication succeeds**.

## 6. Three-Layer Design: AccountEntity → AuthDetails → SafePrincipal

Separate data by meaning:

~~~text
ACCOUNT ENTITY (domain/persistence)
  id, username, passwordHash, enabled,
  email, phone, address, orders, internalNotes,
  relationships, auditing, tenant mappings
                   |
                   | extract/map fields needed for login
                   v
AUTH DETAILS (input to DaoAuthenticationProvider)
  username, passwordHash, account flags,
  GrantedAuthority
                   |
                   | verify password + account status
                   v
TRUSTED Authentication
  safe principal, authorities, auth details
                   |
                   v
SECURITY CONTEXT / SESSION (if used)
  userId, username, minimal auth info
                   |
                   v
BUSINESS SERVICE
  receives userId -> fetches fresh entity/DTO
  -> enforces object-level authorization
~~~

Never store `AccountEntity` in `HttpSession` or the context "to avoid querying the DB next time". The system can **cache domain data in services/repositories** under separate rules, or pick proper TTLs/eviction without turning the entire entity graph into the principal.

### Applied Boundaries

- **Persistence:** repositories fetch entities/projections; control minimal fetching and transactions.
- **Identity mapping:** converts records into a clean authentication object without carrying entity graphs.
- **Authentication:** providers verify credentials with `PasswordEncoder`, evaluate account flags, and return `Authentication`.
- **Session/context:** stores minimal server-trusted identity; protects cookies/sessions per policy.
- **Application service:** uses userId/tenantId to check resource permissions and load fresh data when needed.
- **API response:** builds dedicated response DTOs; never uses `Authentication.getPrincipal()` as a default DTO.

## 7. Runnable Java 17 Demo: Contrasting Full Entities with a Safe Principal

The demo uses Spring Security Core **6.5.11** to illustrate a clear scenario:

1. A full account record holds password hash, personal email, address, and internal notes.
2. `UserDetailsService` maps only needed fields to an auth-dedicated `UserDetails`.
3. `DaoAuthenticationProvider` checks the password with BCrypt and produces an authenticated result.
4. From the **verified** result, trusted code constructs a `SafePrincipal` holding only `userId` and `username`, keeping the provider-granted authorities intact.
5. The demo proves the new principal **is not an entity**, contains no password, and still returns the right `getName()` and roles.

**Note:** `AccountRow` is a **record simulating persistence data**, not a real JPA entity, so the demo can run without a database or Hibernate. In an app with JPA, it corresponds to data fetched by a repository from an entity/projection. Building an authenticated token **must only happen inside trusted server code after authentication**, never as an API for clients to forge logins.

### 7.1. Project Structure

~~~text
principal-boundary-demo/
├── build.gradle
└── src/main/java/demo/PrincipalBoundaryDemo.java
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.PrincipalBoundaryDemo'
}
~~~

**File `src/main/java/demo/PrincipalBoundaryDemo.java`:**

~~~java
package demo;

import java.io.Serial;
import java.io.Serializable;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.AuthenticatedPrincipal;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PrincipalBoundaryDemo {

    // Simulates business data in storage, NOT a real JPA entity.
    record AccountRow(
            long id,
            String username,
            String passwordHash,
            String personalEmail,
            String billingAddress,
            String internalNote
    ) {}

    // Small, stable identity; no password or entity graph.
    record SafePrincipal(long userId, String username)
            implements AuthenticatedPrincipal, Serializable {

        @Serial
        private static final long serialVersionUID = 1L;

        @Override
        public String getName() {
            return username;
        }
    }

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();

        AccountRow account = new AccountRow(
                42L,
                "linh",
                encoder.encode("demo-password-only"),
                "private@example.test",
                "Private billing address",
                "Internal compliance note"
        );

        // Each call builds a fresh UserDetails; never returns AccountRow.
        UserDetailsService detailsService = username -> {
            if (!account.username().equals(username)) {
                throw new UsernameNotFoundException("Unknown user");
            }
            return User.withUsername(account.username())
                    .password(account.passwordHash())
                    .roles("READER")
                    .build();
        };

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(detailsService);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager manager = new ProviderManager(provider);

        // Client request: not yet trusted.
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "linh", "demo-password-only"
                );

        Authentication verified = manager.authenticate(request);
        UserDetails temporary = (UserDetails) verified.getPrincipal();

        System.out.println("verified.authenticated=" + verified.isAuthenticated());
        System.out.println("verified.name=" + verified.getName());
        System.out.println("verified.principalIsEntity="
                + (verified.getPrincipal() == account));
        System.out.println("verified.passwordErased="
                + (temporary.getPassword() == null));

        // In the demo there is one account and the ID belongs to the verified username.
        // Real apps must derive verified userId and check tenant accurately.
        SafePrincipal safePrincipal =
                new SafePrincipal(account.id(), verified.getName());

        // Only call authenticated factory after the manager succeeds.
        Authentication safeResult =
                UsernamePasswordAuthenticationToken.authenticated(
                        safePrincipal, null, verified.getAuthorities()
                );

        boolean reader = safeResult.getAuthorities().stream()
                .anyMatch(a -> "ROLE_READER".equals(a.getAuthority()));

        System.out.println("safe.type="
                + safeResult.getPrincipal().getClass().getSimpleName());
        System.out.println("safe.name=" + safeResult.getName());
        System.out.println("safe.id=" + safePrincipal.userId());
        System.out.println("safe.reader=" + reader);
        System.out.println("safe.credentialsAbsent="
                + (safeResult.getCredentials() == null));
        System.out.println("safe.principalIsEntity="
                + (safeResult.getPrincipal() == account));
    }
}
~~~

### 7.2. Running the Demo and Output

In the `principal-boundary-demo` directory, with JDK 17+ and compatible Gradle:

~~~bash
gradle -q run
~~~

Or if the project has a Gradle Wrapper, use `./gradlew -q run`; on Windows you can use `gradlew.bat -q run`. The first run needs to download dependencies from Maven Central.

**stdout produced by the `System.out.println` statements**, excluding separate Gradle/library logs if configured in the environment:

~~~text
verified.authenticated=true
verified.name=linh
verified.principalIsEntity=false
verified.passwordErased=true
safe.type=SafePrincipal
safe.name=linh
safe.id=42
safe.reader=true
safe.credentialsAbsent=true
safe.principalIsEntity=false
~~~

### 7.3. Explaining the Results

- `verified.authenticated=true`: the password was verified by `DaoAuthenticationProvider` against the hash returned by `UserDetailsService`.
- `verified.principalIsEntity=false`: the principal is a **freshly constructed** `UserDetails` from the service, not the `AccountRow` business record.
- `verified.passwordErased=true`: `ProviderManager` invokes credential erasure by default; `User` implements `CredentialsContainer`. This erasure **does not** erase the password hash from `AccountRow` in the demo.
- `safe.type=SafePrincipal` and `safe.id=42`: the principal represents the verified identity with a stable ID; no email, address, or internal notes.
- `safe.name=linh`: `SafePrincipal` implements `AuthenticatedPrincipal.getName()` so `Authentication.getName()` returns a predictable username; using a plain record with `toString()` might not yield the expected `getName()` result.
- `safe.reader=true`: authorities come from the trusted authentication result, not from the client body.
- `safe.credentialsAbsent=true` and `safe.principalIsEntity=false`: the identity-bearing token holds neither passwords nor entity graphs.

**Important note on integration:** The demo only builds and prints `Authentication` objects. It **does not** create a website, session, or put `safeResult` into `SecurityContextHolder`. In a real app, for the new principal to appear in the context/session, you must integrate this projection into the provider/filter handling authentication success, preserving full session, CSRF, success/failure handlers, and trust boundaries. Never copy `authenticated(...)` into a controller receiving unverified input.

### 7.4. Design Choice in the Demo

Both options are suitable:

- Use a **small `UserDetails`** directly as the post-authentication principal, provided it carries no full entity or unneeded credentials and credential erasure/caching policies are sound.
- Use a **`SafePrincipal`** built by a trusted component after the credential-check step, holding only long-lived identity. The provider input can still be a `UserDetails` carrying a temporary password hash for login.

The second option is useful when designing a shared session principal across multiple authentication mechanisms (password, OIDC, passkey), though care is needed to map authorities, `userId`, and `tenantId` based on verified identity.

## 8. Integrating with JPA in Spring Boot

### 8.1. Auth Data Projections Straight from the Repository

In real applications, `AccountEntity` can be huge. So login does not load orders, addresses, or relationships, design a query fetching only the needed authentication data.

Illustrative example—**not standalone compilable** because `AccountRepository`, `AccountAuthRow`, and entity/domain types are not fully declared in this snippet:

~~~java
@Service
public class DatabaseUserDetailsService implements UserDetailsService {

    private final AccountRepository accounts;

    public DatabaseUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username) {
        AccountAuthRow row = accounts.findAuthDataByUsername(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Account unavailable"));

        return User.withUsername(row.username())
                .password(row.passwordHash())
                .authorities(row.authorities().toArray(String[]::new))
                .disabled(!row.enabled())
                .accountLocked(row.locked())
                .build();
    }
}
~~~

`AccountAuthRow` should hold only the necessary auth fields: username, passwordHash, status, and authorities. The repository can return a DTO/projection; if querying roles separately, resolve joins or batching intentionally. In multi-tenant systems, the lookup key must ensure username is bound to a verified tenant.

Never return `AccountEntity` from the method above merely because the entity `implements UserDetails`. If an entity is loaded for mapping, **return a new object**; once the transaction closes, the principal holds no reference to managed entities or lazy collections.

Note: `User.withUsername(...).password(...)` here takes the **stored hash**. The code does not re-encode the password hash on load; the provider calls `PasswordEncoder.matches(rawPassword, storedHash)`. Only encode when creating/changing passwords per storage policy.

### 8.2. Business Services Take userId from Principal and Re-Query

With a safe principal configured in the authentication success path, controllers can receive the identity and pass it down to services:

~~~java
// Illustrative code in Spring MVC with security config and services present.
@GetMapping("/me")
public ProfileResponse myProfile(
        @AuthenticationPrincipal SafePrincipal principal) {
    return profileService.loadVisibleProfile(principal.userId());
}
~~~

This is **not** a standalone program; `ProfileResponse`, `profileService`, and annotations/dependencies belong to a specific Spring Boot project. In a real application, the service must also validate active account/tenant status and return only a field-selected response DTO to the client.

From there:

~~~text
@AuthenticationPrincipal SafePrincipal(userId=42)
        |
        v
ProfileService.loadVisibleProfile(42)
        |
        v
AccountRepository / ProfileRepository
        |
        +--> query fresh data
        +--> check account/tenant status
        +--> enforce object-level authorization
        |
        v
ProfileResponse DTO (only permitted response fields)
~~~

Choose querying and caching per use case. You can use `@Transactional(readOnly = true)` in the application service at the appropriate query boundary, instead of expecting a JPA entity from login time to stay attached across all requests.

### 8.3. Do Not Return the Principal Directly over HTTP

Common mistake:

~~~java
// DO NOT USE as an endpoint returning user info.
@GetMapping("/me")
public Object me(Authentication authentication) {
    return authentication.getPrincipal();
}
~~~

If the principal used to be a JPA entity, this can accidentally turn the entire entity into a JSON response, or trigger lazy-loading/serialization errors. Even a minimal principal should be treated as an internal security detail, **copying only appropriate fields** into a public DTO per the API contract.

Similarly, logging `authentication.getPrincipal().toString()` unconditionally can leak info; log only minimal identity ID/username per logging and data-protection policies.

## 9. Principals and Other Authentication Mechanisms

Not every `Authentication` in Spring Security is created by DAO username/password:

| Mechanism | Typical Principal | Entity-Avoidance Design |
| --- | --- | --- |
| Form login + DAO | `UserDetails`, typically `User` or custom UserDetails | Minimal mapping from repository, control hash/credential erasure |
| HTTP session | Stored/restored authenticated `Authentication` | Session holds minimal identity; avoid entities/proxies and sensitive data |
| JWT Resource Server | `Jwt` / JWT-related principal per config | Verify signature, issuer, audience; map subject to userId if needed, load domain data separately |
| OAuth2/OIDC login | `OAuth2User`/`OidcUser` | Map subject by issuer and account linking; never store full account entity in principal |
| mTLS/X.509 | Certificate identity after TLS verification | Map certificate identity to internal user/serviceId; authorize by actual permissions |
| Passkey/WebAuthn | Identity confirmed after challenge/assertion | Attach userId from trusted credential registry and build safe context/session |

For OIDC, **`sub` combined with `iss`** is the issuer's identifier; do not blindly equate `sub` with internal IDs across all systems. For JWTs, **decoding claims is not validating a token**; resource servers must verify tokens before trusting subjects or authorities.

For multi-tenancy, a `tenantId` claim or URL parameter is valid only after the system verifies the user has access to that tenant. When switching tenants, clearly define which identity/context must be reissued or reloaded.

## 10. When Business Data or Permissions Change Between Requests

A minimal principal creates cleaner boundaries, yet **does not solve permission refreshing on its own**. Systems still need identity lifecycle policies.

| Change | What Can Happen If Relying Only on Old Context | Handling Typically Needed |
| --- | --- | --- |
| Admin revokes role | Authorities in session/JWT remain prior snapshot | Session invalidation, token revocation/TTL, authority reload at sensitive points |
| Account locked | Old sessions may keep working depending on config | Block requests at proper policy layer, revoke sessions, or revalidate |
| User changes username | `authentication.getName()` may hold old name | Use stable userId for identity/DB, update display name per lifecycle |
| Email/address changes | Info in old principal may be stale | Load fresh profile in service when needed, avoid non-essential PII in session |
| Tenant membership revoked | Old context/claim may allow wrong tenant | Check membership/authorization and have refresh/revocation mechanisms |
| Password changed | Issued tokens/sessions may stay valid | Device logout policy, revoke refresh tokens, require re-login |

Re-check frequency depends on risk. An internal app with short sessions and rarely changing roles differs from a financial service requiring near-instant permission revocation. The core requirement is **knowing which snapshot you use, when it expires, and what events invalidate it**.

## 11. Real-World Failure Scenarios and Fixes

### Scenario A: Controller Hits LazyInitializationException

**Symptom:** After a successful login, a new request calls `((AccountEntity) principal).getOrders()` and fails on lazy loading.

**Cause:** The entity kept from authentication detached from the persistence context, leaving the association uninitialized. Switching `LAZY` to `EAGER` easily pulls in massive queries.

**Fix:** Keep only `userId` in the principal. The controller calls `orderService.findVisibleOrders(userId)`; the service opens a transaction/query fit for the use case and authorizes each required object.

### Scenario B: /me API Leaks Internal Fields

**Symptom:** `return authentication.getPrincipal()` accidentally outputs JSON containing phone, address, passwordHash, or internalFlags.

**Cause:** A full entity/object served as both security principal and HTTP DTO simultaneously.

**Fix:** Define a response DTO containing only public API fields; switch principal to a minimal identity; test JSON responses to ensure no sensitive data appears.

### Scenario C: Redis Session Fails to Serialize

**Symptom:** Login succeeds on the first request, yet session persistence fails when writing/restoring a principal holding proxies or collections.

**Cause:** The principal carries a JPA object graph with types incompatible with the serializer/schema version.

**Fix:** Use a small principal serializable by the chosen session mechanism, removing graphs/proxies; verify round-trip serialization in integration tests.

### Scenario D: User Role Revoked Yet Permissions Persist

**Symptom:** A DBA updates roles in `users`/`authorities` tables, yet active sessions continue operating under old roles.

**Cause:** `Authentication.getAuthorities()` reflects data at authentication or last refresh time.

**Fix:** Choose a context/token revocation policy and verify sensitive permissions against updated data. Never expect holding a JPA entity in the principal to auto-refresh authorities.

### Scenario E: Same User ID, Wrong Tenant

**Symptom:** An API reads `tenantId` from the query and `userId` from the principal, then accesses another tenant's records.

**Cause:** Internal identity was used without checking tenant membership and object-level permissions.

**Fix:** Use a verified tenant context, enforce in service/repository, and never let clients self-declare which tenant they belong to.

### Scenario F: Credential Erasure Corrupts the User Cache

**Symptom:** First login succeeds; the next time, the provider fetches cached `UserDetails` whose password is already `null`.

**Cause:** The cache and `Authentication.principal` reference the same `CredentialsContainer` object; `ProviderManager` erases credentials after success.

**Fix:** Return a separate copy for principal/result, and align cache/provider per contract. Never disable `eraseCredentialsAfterAuthentication` casually just to dodge the bug.

## 12. Design Smells to Spot During Code Review

| Code Sign | Question to Ask | Improvement |
| --- | --- | --- |
| `class UserEntity implements UserDetails` | Does the entity hold PII, relations, secrets, or mutable state? | Build a dedicated `UserDetails` adapter |
| `return userRepository.findByUsername(...)` inside `loadUserByUsername` | Is the service returning a raw entity or a mapped projection? | Return an authentication-dedicated object |
| `Authentication.getPrincipal()` cast to `AccountEntity` | Can services use an ID/typed principal instead of the entity? | Refactor to small principal; query domain data in service |
| `@AuthenticationPrincipal AccountEntity user` in controller | Is it dragging a JPA entity across requests/transactions? | Inject only userId or minimal principal |
| `return principal` in an API | Does the object have internal fields/secrets/lazy graphs? | Response DTO with allowlisted fields |
| `log.info("{}", principal)` | Does `toString` contain hashes/PII? | Log only minimal identifier, never secrets |
| `principal.getOrders()`/`getPayments()` | Does it trigger queries outside transactions or overfetching? | Use business repositories/services |
| `roles` stored in entity, principal, token, and session | When roles change, which source is truth? | Design clear refresh/revocation and mapping |
| Putting `@Entity` into distributed sessions | Have serializers, proxies, and schema/versioning been tested? | Shrink principal, test round-trip |
| Taking `userId` from request body to build authenticated token | Was that ID verified by a provider? | Only create trusted principals after authentication |
| `AuthUserDetails` holds every domain field | Is it really a minimal adapter? | Keep only required auth fields/ID |
| Mutable username used as immutable identifier | Are renames, case-insensitivity, and tenants supported? | Use stable internal ID and proper scope |

A small, immutable, tested entity without unnecessary sensitive data can work as a principal in limited systems. However, once JPA graphs, PII, sessions, or multiple auth mechanisms appear, **a dedicated projection is the safer, more maintainable default**.

## 13. Pre-Production Principal Checklist

1. **Trusted sources:** `userId`, `username`, `tenantId`, and authorities all come from an authenticated `AuthenticationManager`/IdP or verified server data.
2. **No long-lived secrets:** raw passwords, unneeded password hashes, refresh tokens, API keys, and internal notes are absent from session principals.
3. **No JPA graphs:** the principal holds no `EntityManager`, Hibernate proxies, lazy collections, or large entity references.
4. **Stable identifiers:** distinguish `userId`, display username, and tenant scope; never rely on email or `displayName` to look up permissions.
5. **Authority policy:** permissions come from trusted sources, with clear rules on when to refresh/revoke after role or account status changes.
6. **Never use principal as response:** APIs use dedicated DTOs with allowlisted fields; logs omit secrets and full objects.
7. **Transaction boundaries:** `UserDetailsService` maps while data is accessible; other use cases load fresh domain data in services.
8. **Safe session/caching:** verify serialization round-trips, expiration, credential erasure, session replication, and cache invalidation.
9. **Tenant and object-level checks:** having a `userId` does not mean permission to view data of another user or tenant.
10. **Authentication and leak tests:** test login success/failure, principal type, credentials erased, no PII, permission updates, and session restarts if applicable.
11. **Never build trusted tokens from raw input:** only providers/trusted components after verifying credentials may construct authenticated results.
12. **Migration plan:** if a system currently uses entity principals, migrate controllers/`@AuthenticationPrincipal` and session serialization gradually rather than swapping types mid-flight and breaking old sessions.

## 14. Self-Check Questions

**Question 1.** Why must `UserDetailsService` still supply the password hash to `DaoAuthenticationProvider` if principals should be minimal?  
**Answer:** Because the provider must match the raw password against the stored hash **during the authentication step**. It is temporary auth data; afterward, credentials should be erased from the result to avoid holding hashes long-term in the principal.

**Question 2.** Does turning `AccountEntity` into a small `UserDetails` automatically prevent all vulnerabilities?  
**Answer:** No. You still must verify credentials, grant trusted authorities, protect sessions, authorize resources, and manage state when permissions change.

**Question 3.** Why should you not rely on `@JsonIgnore` as the sole protection on an entity principal?  
**Answer:** Because JSON annotations do not guard logs, session serialization, caches, object graphs, or other serializers.

**Question 4.** A controller wants the current user's shipping addresses. Should the entire address list be added to the principal?  
**Answer:** Usually no. The controller receives `userId`, and a service queries visible addresses and returns a properly scoped response DTO.

**Question 5.** An entity has `@OneToMany(fetch = LAZY)`. If kept in the session and its collection is accessed on a later request, what can happen?  
**Answer:** The entity may be detached, throwing `LazyInitializationException`, or trigger unexpected/N+1 queries if a persistence context happens to be open.

**Question 6.** `ProviderManager` erases the password from a `UserDetails` shared with a cache. What happens?  
**Answer:** The next authentication may fail to find the right password hash. Decouple cached objects from result objects or design credential erasure/caching properly.

**Question 7.** A client sends JSON with `userId=42, roles=["ADMIN"]`. May the server immediately call `UsernamePasswordAuthenticationToken.authenticated(...)`?  
**Answer:** No. Identity and authorities must be verified by a provider and trusted sources. The `authenticated` factory does not validate inputs itself.

**Question 8.** A session still holds an old role after the DB revoked the permission; does making the principal smaller auto-update roles?  
**Answer:** No. You need session/token lifecycle management, refresh/revocation, or fresh permission checks at sensitive points.

## 15. Reference Documentation

- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `SecurityContext`, `ProviderManager`, and credential erasure.
- [Spring Security 6.5 – UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html): contract for returning `UserDetails` to username/password providers.
- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): path of `UserDetails` into the post-authentication principal.
- [Spring Security 6.5 – UserDetails](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details.html): identity data lifecycle and credential management.
- [Spring Security 6.5 – User API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.html): built-in `UserDetails`, `CredentialsContainer`, and password erasure.
- [Spring Security 6.5 – MVC Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/mvc.html): `@AuthenticationPrincipal`.
- [Spring Security 6.5 – Authentication API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/Authentication.html): principal, credentials, authorities, and `getName()`.
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): limiting session data and controlling lifecycles.

**Key takeaway:** Use entities to **persist and process business logic**; use `UserDetails`/providers to **verify**; use minimal principals to **identify within the security context**; use services to **fetch fresh business data and authorize specific resources**. Never force one full entity to shoulder all four responsibilities merely because casting the principal to an entity seems convenient.

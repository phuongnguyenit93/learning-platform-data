# Account Read Transactions and Avoiding ORM Session Dependencies After Authentication

## 1. Core Problem: Successful Authentication Does Not Mean the ORM Session Remains Open

In a Spring Boot + Spring Security + Spring Data JPA application, `UserDetailsService.loadUserByUsername(...)` usually queries an account from the database. The account record may have relationships to a list of roles (`roles`), permissions (`permissions`), organization, lock status, etc., mapped as a **JPA entity**. Many relationships are configured with **lazy loading**, meaning Hibernate may only fetch the data when code actually accesses that property.

This creates a trap: **the ORM session (Hibernate `Session` / JPA `EntityManager`) serving the user read transaction may close before Spring Security uses the principal and authorities in subsequent stages**. If `Authentication.getPrincipal()` holds an entity or `UserDetails.getAuthorities()` accesses a lazy collection on a detached entity, the application can throw `LazyInitializationException`, or silently emit SQL in layers that should never be querying the database.

**Design goals:**

1. Read the account and all information needed for authentication within **one clear read transaction boundary**.
2. Copy the necessary data into a **`UserDetails`/security principal independent of the JPA entity**, holding no proxies or lazy collections.
3. End the read transaction; `DaoAuthenticationProvider` and `SecurityContext` continue using the obtained principal/authorities **without requiring `EntityManager` to stay open**.
4. If business code needs fresh user data, query within a **separate business transaction**, using a stable user ID/identity; never use the principal as a live entity object spanning the entire login session.

**One sentence to remember:** *An ORM transaction is for loading and checking data at a point in time; `Authentication` is a security identity snapshot, not an ORM session stretched across requests.*

## 2. Distinguishing Concepts That Are Easily Conflated

| Concept | Function | Typical lifecycle |
| --- | --- | --- |
| HTTP request | A single API/web page call. | Starts when HTTP arrives, ends when response is sent. |
| Spring Security `SecurityContext` | Holds the current `Authentication` for authorization checks. | Scoped to the request and may be saved/restored by session/token mechanisms depending on configuration. |
| `Authentication` / principal | Authenticated identity along with authorities. | Can outlive a JPA transaction and even span multiple requests. |
| `UserDetailsService` | Looks up account data for `DaoAuthenticationProvider`. | Called when a username/password mechanism needs to load a user. |
| Spring `@Transactional` | Defines the boundary of a data-related unit of work. | Scoped to a call through a transaction proxy, not synonymous with HTTP session lifetime. |
| JPA `EntityManager` / Hibernate `Session` | Manages persistence context, entities, and lazy loading. | Bound to a transaction or a specific request-management mechanism. |
| Managed/detached JPA entity | ORM object currently managed or detached from the persistence context. | Can become detached as soon as the transaction/context ends. |
| `open-in-view` (OSIV) | Keeps `EntityManager` bound to part of the web lifecycle to support lazy loading outside service transactions. | Configuration-dependent; not a contract of `UserDetailsService` or the security principal. |

There is no fixed 1-to-1 relationship between an **HTTP request**, **`SecurityContext`**, **database transaction**, and **ORM Session**. One request can execute multiple transactions; one authentication can span multiple requests; one entity can detach immediately when its transaction finishes.

### Why Does This Problem Often Only Appear During Deployment or Testing?

- Tests run with `@Transactional` wrapping the entire test method so entities stay managed; production closes transactions earlier.
- Development environments have `spring.jpa.open-in-view=true` enabled so controllers or serializers can still lazy-load; when OSIV is turned off, the bug surfaces.
- Code uses `@EntityGraph` or `JOIN FETCH` on one code path, but omits it on another.
- The principal is stored in the session; a later request reads authorities when the old `EntityManager` has already closed.
- The `roles` field was previously `EAGER` and then switched to `LAZY` to optimize queries without updating the authentication adapter.

Do not "fix" this by forcing every entity relationship to `EAGER` or stretching a transaction across the entire user session. Design the right boundary instead.

## 3. Failure Scenario: Returning a JPA Entity (or a Wrapper Holding One) as UserDetails

Suppose `AccountEntity` has a `roles` association with `@ManyToMany(fetch = FetchType.LAZY)`.

**Problematic pattern — illustrative code only, not a complete class:**

```java
@Service
class UnsafeUserDetailsService implements UserDetailsService {

    private final AccountRepository accounts;

    UnsafeUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username) {
        AccountEntity entity = accounts.findByUsernameKey(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Account not found"));

        // CustomEntityUserDetails only holds a reference to the JPA entity.
        // It does NOT create an authorities snapshot here.
        return new CustomEntityUserDetails(entity);
    }
}
```

If `CustomEntityUserDetails.getAuthorities()` calls `entity.getRoles().stream()`, when the provider asks for authorities **after `loadUserByUsername` has returned**, there may no longer be a persistence context available to initialize the lazy collection:

```text
loadUserByUsername()  [@Transactional(readOnly = true)]
  |
  +-- query AccountEntity (roles not yet initialized)
  +-- return CustomEntityUserDetails(entity)
  |
  +-- transaction/EntityManager closes or entity becomes detached
  v
DaoAuthenticationProvider / AbstractUserDetailsAuthenticationProvider
  |
  +-- calls getAuthorities() to build Authentication
      |
      +-- wrapper requests entity.getRoles() [LAZY]
          |
          +-- LazyInitializationException (if no session remains)
```

**Note on timing:** `DaoAuthenticationProvider` may check account state and password before needing authorities; thus, a valid password is not enough to guarantee the full `Authentication` construction succeeds. Exact failure timing depends on how `UserDetails` is implemented, call order, and persistence context configuration.

Having no `LazyInitializationException` **does not mean** the design is safe: with OSIV or a pre-initialized collection, the code still runs but may emit unexpected SQL or leave the principal holding a reference to a mutable entity.

### Another Risky Pattern: A Lambda Inside `getAuthorities()`

```java
class DatabaseBackedPrincipal implements UserDetails {
    private final AccountEntity account;

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        // Dangerous: lazy collection and query may execute much later.
        return account.getRoles().stream()
                .map(role -> new SimpleGrantedAuthority(
                        "ROLE_" + role.getCode()))
                .toList();
    }

    // ... other UserDetails methods
}
```

The code above is an illustrative snippet, **not a standalone Java class**. The issue is not the `stream()` operator, but **exposing a proxy/lazy collection outside the transaction**. Similarly, `getUsername()`, `isEnabled()`, or `getPassword()` will fail if they read from an uninitialized proxy.

## 4. Desired Boundary: Read Transaction → Security Snapshot → Authenticate

A resilient design:

```text
HTTP login / Authentication filter
                |
                v
AuthenticationManager
                |
                v
DaoAuthenticationProvider
                |
                +--> UserDetailsService.loadUserByUsername(...)
                           |
                           | @Transactional(readOnly = true)
                           v
                    Repository looks up AccountEntity
                           |
                           +--> load required roles / status
                           +--> validate data invariants
                           +--> copy username, passwordHash,
                                enabled, locked, expired, authorities
                                into a PLAIN UserDetails, holding no entity
                           |
                           v
                    return immutable/snapshot UserDetails
                           |
                    [transaction ends]
                           |
                           v
          DaoAuthenticationProvider verifies password + state
                           |
                           v
          Authentication contains constructed principal/authorities
                           |
                           v
             SecurityContext / authorization
                (DOES NOT rely on the just-closed ORM Session)
```

Three steps are especially important:

1. **Load all needed data.** `roles`/`permissions` are fetched or queried within the same transaction, not left dangling in a lazy collection.
2. **Convert to independent data.** You can use Spring Security's `org.springframework.security.core.userdetails.User` or a custom `UserDetails` holding scalar fields/immutable collections. Never carry JPA entities, `PersistentBag`, proxies, or `EntityManager` into the principal.
3. **Place a short transaction around the read-and-map step.** The transaction finishes before the authentication outlives it; afterward, password verification uses the copied hash and authorities use the snapshot.

### Why Is a Snapshot Not an Entity?

- A snapshot cannot trigger SQL or invoke `EntityManager` inside `getAuthorities()`.
- Snapshots are easy to test outside a web container without depending on OSIV.
- A principal in session storage/serialization does not drag along an entire data graph, Hibernate proxies, or circular references.
- The security layer cannot accidentally mutate a managed entity via getters/setters.
- Subsequent business data queries use a separate transactional service/repository with a stable user ID.

Even so, **a snapshot is point-in-time**: if an admin revokes a role after a user logs in, the principal stored in the session does not automatically update. Section 11 analyzes how to refresh permissions.

## 5. What Does `@Transactional(readOnly = true)` Actually Guarantee?

Spring's `@Transactional` creates a transaction boundary when calls pass through a **configured Spring proxy or interception mechanism**. For `loadUserByUsername(...)`, place the annotation on a public method of a Spring-managed bean:

```java
@Service
class JpaUserDetailsService implements UserDetailsService {

    // ... constructor and repository

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username) {
        // Load and convert data into UserDetails right here.
    }
}
```

`readOnly = true` is a **transaction hint and optimization opportunity**, not a "security lock forbidding every INSERT/UPDATE statement". Depending on the driver, transaction manager, database, and JPA provider, it may adjust the flush mode or pass a hint down to JDBC. The RDBMS may enforce read-only behavior to some degree, yet you must never assume all writes are rejected in every environment.

**Four practical conditions for the annotation to work properly:**

- The class/service must be a **Spring bean** invoked through the right interceptor/proxy. Calling `new JpaUserDetailsService(...)` manually bypasses transaction management.
- The method must be called from **outside via the Spring proxy**; an internal call `this.loadUserByUsername(...)` usually bypasses the default Spring proxy.
- The application must have the right transaction manager for the JPA datasource; when using multiple datasources/transaction managers, specify the manager or qualifier explicitly if needed.
- Never pass lazy data out of the method hoping a caller service's transaction will stay open. Mapping must complete **before the method returns**.

### How Do Repository Transactions Differ from Service Transactions?

Spring Data JPA configures transactions for many inherited CRUD methods, but **custom-declared query methods** do not automatically get the same transaction policy in every case. Even when repository queries are transactional, placing a transaction at the **service** is more useful when multiple steps must run: reading the user, reading roles, checking status, and building the snapshot.

Example when two queries belong to one read unit:

```java
@Transactional(readOnly = true)
public UserDetails loadUserByUsername(String username) {
    AccountEntity account = accounts.findByUsernameKey(username)
            .orElseThrow(() -> new UsernameNotFoundException("Not found"));

    List<String> permissions = permissionRepo
            .findPermissionCodesByAccountId(account.getId());

    // Both queries and snapshot construction stay inside one service transaction.
    return buildSnapshot(account, permissions);
}
```

This snippet is **not standalone runnable**: `permissionRepo` and `buildSnapshot` are application components. A transaction coordinates the unit of work, yet **does not automatically guarantee a consistent point-in-time snapshot** if the isolation level lets queries observe concurrent changes. For security decisions requiring strict consistency, design queries, isolation, locking, and business boundaries to match requirements.

## 6. Loading Roles on Time with `@EntityGraph` / `JOIN FETCH`

Suppose the data model is:

```java
@Entity
@Table(name = "app_users")
class AccountEntity {
    @Id
    private Long id;

    @Column(name = "username_key", nullable = false, unique = true)
    private String usernameKey;

    @Column(name = "username_display", nullable = false)
    private String usernameDisplay;

    @Column(name = "password_hash", nullable = false)
    private String passwordHash;

    @Column(nullable = false)
    private boolean enabled;

    @Column(nullable = false)
    private boolean locked;

    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(
        name = "account_roles",
        joinColumns = @JoinColumn(name = "account_id"),
        inverseJoinColumns = @JoinColumn(name = "role_id"))
    private Set<RoleEntity> roles = new HashSet<>();

    // getters; full mapping and schema provided by the project.
}
```

`RoleEntity` holds `id` and `code` (for example `READER`, `EDITOR`). This entity snippet is **illustrative**, omitting constructors, schema, getters, and imports to focus on read strategy.

In the repository:

```java
public interface AccountRepository
        extends JpaRepository<AccountEntity, Long> {

    @EntityGraph(attributePaths = "roles")
    Optional<AccountEntity> findByUsernameKey(String usernameKey);
}
```

When using a JPA provider that supports entity graphs, this query requests loading `roles` under a fetch plan for **that specific call**. Depending on the provider and mapping, the ORM may use a SQL join or another query plan; never claim `@EntityGraph` *always* emits a single SQL statement.

Another option:

```java
@Query("""
    select distinct a
    from AccountEntity a
    left join fetch a.roles
    where a.usernameKey = :usernameKey
    """)
Optional<AccountEntity> findForAuthentication(
        @Param("usernameKey") String usernameKey);
```

`LEFT JOIN FETCH` preserves users without roles (letting subsequent logic decide whether to accept them); `DISTINCT` in JPQL expresses the intent not to duplicate the account when joining a collection. If the provider/SQL handles duplicates differently, still test with real data.

**Limitations of fetch joins:**

- Avoid fetching multiple bag collections in the same query; Hibernate can hit multiple-bag issues or produce heavily multiplied result rows.
- Avoid relying on collection fetch joins when paginating large datasets; loading **one user for authentication** differs from listing thousands of users.
- Do not rush to change every association to `FetchType.EAGER`. Fetch only the data needed for each use case.
- If permissions sit deeper in a role → permissions tree, explicitly fetch/project the final authority set; having `roles` loaded does not mean `role.getPermissions()` is also loaded.
- Read roles and copy them into a `List/Set<GrantedAuthority>` **inside the transaction**; this principle decouples code from the specific fetch strategy.

### Choosing Query Projections When Only a Few Fields Are Needed

Instead of hydrating the whole entity graph, query only the needed data:

```java
// In repository, illustrative code; entity/field syntax must match the project.
@Query("""
    select r.code
    from AccountEntity a
    join a.roles r
    where a.id = :accountId
    """)
List<String> findRoleCodes(@Param("accountId") Long accountId);
```

Inside the service transaction, query scalar user fields and role codes, building the snapshot from the materialized values. Projections can reduce complex graph-fetching overhead, though they may introduce multiple round-trips and require attention to isolation. No single option is "always fastest"; measure with SQL logs/metrics and test data.

## 7. Designing a Concrete `UserDetailsService`: Reading the Entity and Returning an ORM-Free Principal

Below is an **integration pattern** for Spring Data JPA + Spring Security. It intentionally separates the entity from the principal and puts `@Transactional(readOnly=true)` at the read boundary.

Assumptions:

- `AccountEntity` has `getId()`, `getUsernameKey()`, `getUsernameDisplay()`, `getPasswordHash()`, `isEnabled()`, `isLocked()`, and `getRoles()`.
- Each `RoleEntity` has `getCode()` formatted like `READER` (without prefix).
- `AccountRepository.findByUsernameKey(...)` is declared with `@EntityGraph(attributePaths="roles")`.
- `UsernamePolicy.toKey(...)` is the application's normalization function; apply it consistently across registration and lookup.
- The returned `UserDetails` in this example is Spring Security's `User`; if you need an internal ID in the principal, see section 8.

```java
@Service
public class JpaAccountUserDetailsService implements UserDetailsService {

    private final AccountRepository accounts;

    public JpaAccountUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String inputUsername) {
        String usernameKey = UsernamePolicy.toKey(inputUsername);

        AccountEntity account = accounts.findByUsernameKey(usernameKey)
                .orElseThrow(() -> new UsernameNotFoundException(
                        "Account not found"));

        String[] authorities = account.getRoles().stream()
                .map(role -> "ROLE_" + role.getCode())
                .distinct()
                .sorted()
                .toArray(String[]::new);

        // COPY data out of ORM while EntityManager is still active.
        return User.withUsername(account.getUsernameDisplay())
                .password(account.getPasswordHash())
                .disabled(!account.isEnabled())
                .accountLocked(account.isLocked())
                .authorities(authorities)
                .build();
    }
}
```

This requires imports for `Service`, `Transactional`, `UserDetailsService`, `UserDetails`, `User`, `UsernameNotFoundException`, and application-defined domain/repository types. This snippet is **not a standalone Java class** because full entities/schema/config are omitted. `accountLocked(...)` and `disabled(...)` belong to Spring Security's `User` builder. If the system also tracks account expiration or credential expiration, pass them fully into the builder instead of defaulting them all to valid.

### Why Does This Avoid Lazy Session Leaks?

1. The query reads the account inside the transaction.
2. `account.getRoles().stream()` executes **before the method returns**. With a graph or lazy fetch, roles are materialized while the persistence context is active.
3. `String[] authorities` holds plain Java role strings.
4. `User.withUsername(...).password(...).authorities(...).build()` constructs a `UserDetails` with no references to `AccountEntity`, `RoleEntity`, or Hibernate proxies.
5. Once the transaction closes, `DaoAuthenticationProvider` reads `passwordHash`, status, and authorities from the standalone `User`; no ORM queries run from `getAuthorities()`.

**Note:** the provider uses the configured `PasswordEncoder` to verify the raw password against the hash stored in `passwordHash`. `UserDetailsService` only loads data; it does not compare passwords or call `SecurityContextHolder.setContext` itself.

### What If There Are No Roles?

`UserDetailsService` and application policy must define the behavior. Never assume every record has authorities. Under some configurations, a user without any `GrantedAuthority` may be rejected during loading/authentication; if business logic permits roleless accounts, define an explicit auth policy. **Never auto-grant `ROLE_USER` just to avoid an error** when DB data is missing permissions.

### What If Username Casing Differs Between the Request and the DB?

`UserDetails.getUsername()` may carry a value from the DB with different casing than what was typed. The `UserDetailsService` API permits case-sensitive or case-insensitive implementations; never use the raw request spelling to assign ownership/authorities. Apply normalized keys at the domain layer and keep internal IDs stable.

## 8. Need an Internal ID in the Principal? Use an Immutable Snapshot Instead of an Entity

Spring Security's `User` is enough if business logic only needs username, password hash, flags, and authorities. However, many systems need a stable `accountId` for auditing and resource access. Do not stuff the entire `AccountEntity` into the principal just for that.

A custom design:

```java
public final class AccountPrincipal implements UserDetails {

    private final long accountId;
    private final String username;
    private String passwordHash;
    private final boolean enabled;
    private final boolean accountNonLocked;
    private final List<GrantedAuthority> authorities;

    public AccountPrincipal(
            long accountId,
            String username,
            String passwordHash,
            boolean enabled,
            boolean accountNonLocked,
            Collection<? extends GrantedAuthority> authorities) {

        this.accountId = accountId;
        this.username = Objects.requireNonNull(username);
        this.passwordHash = Objects.requireNonNull(passwordHash);
        this.enabled = enabled;
        this.accountNonLocked = accountNonLocked;
        this.authorities = List.copyOf(authorities);
    }

    public long getAccountId() { return accountId; }

    @Override public String getUsername() { return username; }
    @Override public String getPassword() { return passwordHash; }
    @Override public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }
    @Override public boolean isEnabled() { return enabled; }
    @Override public boolean isAccountNonLocked() { return accountNonLocked; }
}
```

This is a **model excerpt**, not a complete class for every version or scenario. In production, consider `Serializable` for session persistence, password hash lifecycle, `CredentialsContainer.eraseCredentials()`, account/credentials expired flags, `equals/hashCode` when needed, and authority mutability. `List.copyOf` prevents structural list modification, though it does not automatically make every element immutable; `SimpleGrantedAuthority` built from role strings is a convenient choice.

If the principal is stored in a session or cache, avoid keeping the password hash longer than necessary. `ProviderManager` attempts to erase credentials from the authenticated result by default, but **that does not mean every custom principal clears `passwordHash` automatically**. Check your provider/manager version, user caching, and sensitive-data erasure behavior. Never put an `AccountEntity` full of personal data into the principal for convenience.

**A helpful separation:**

- Principal: `accountId`, username, status, and authorities needed for authentication/authorization.
- Account entity: DB user record, ORM associations, and dedicated transactions.
- DTO response: allowed data subset exposed to clients, never leaking password hashes or proxies.
- Audit event: user ID, action, timestamp, outcome; never exposing raw credentials.

## 9. Standalone Java 17: Simulating the Session Boundary and Snapshot

To observe the boundary **without booting JPA/Hibernate**, the program below simulates a lazy collection: an object reading roles requires an open session, whereas an immutable snapshot created while the session is open works after the session closes.

**Important limitation:** `FakeSession` and `LazyRoles` **are not Hibernate APIs**. They only illustrate the condition "unmaterialized data + closed session". In a real application, the corresponding error may be `org.hibernate.LazyInitializationException`, and timing depends on ORM mappings.

Create `OrmBoundaryDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public final class OrmBoundaryDemo {

    static final class FakeSession implements AutoCloseable {
        private boolean open = true;
        boolean isOpen() { return open; }
        @Override public void close() { open = false; }
    }

    static final class LazyRoles {
        private final FakeSession session;
        private final List<String> stored;
        private List<String> loaded;

        LazyRoles(FakeSession session, List<String> stored) {
            this.session = session;
            this.stored = List.copyOf(stored);
        }

        List<String> get() {
            if (loaded == null) {
                if (!session.isOpen()) {
                    throw new IllegalStateException("Lazy data unavailable");
                }
                loaded = List.copyOf(stored);
            }
            return loaded;
        }
    }

    static final class AccountEntityLike {
        final long id;
        final String username;
        final String passwordHash;
        final boolean enabled;
        final LazyRoles roles;

        AccountEntityLike(FakeSession session) {
            id = 42L;
            username = "lan";
            passwordHash = "demo-encoded-value";
            enabled = true;
            roles = new LazyRoles(
                    session, List.of("ROLE_READER", "document:read"));
        }
    }

    record SecuritySnapshot(
            long accountId,
            String username,
            String passwordHash,
            boolean enabled,
            List<String> authorities) {

        SecuritySnapshot {
            Objects.requireNonNull(username);
            Objects.requireNonNull(passwordHash);
            authorities = List.copyOf(authorities);
        }
    }

    static SecuritySnapshot loadInsideTransaction(
            AccountEntityLike entity) {

        // Materialize data before the session closes.
        List<String> copiedAuthorities = entity.roles.get();
        return new SecuritySnapshot(
                entity.id, entity.username, entity.passwordHash,
                entity.enabled, copiedAuthorities);
    }

    public static void main(String[] args) {
        // WRONG: carry the entity-like object out, then query lazy roles later.
        AccountEntityLike unsafe;
        try (FakeSession session = new FakeSession()) {
            unsafe = new AccountEntityLike(session);
        }
        try {
            unsafe.roles.get();
            System.out.println("unsafe.afterClose=unexpected");
        } catch (IllegalStateException ex) {
            System.out.println("unsafe.afterClose=lazy-failed");
        }

        // RIGHT: map into a snapshot before the session closes.
        SecuritySnapshot principal;
        try (FakeSession session = new FakeSession()) {
            AccountEntityLike entity = new AccountEntityLike(session);
            principal = loadInsideTransaction(entity);
        }

        System.out.println("snapshot.user=" + principal.username());
        System.out.println("snapshot.id=" + principal.accountId());
        System.out.println("snapshot.enabled=" + principal.enabled());
        System.out.println("snapshot.authorities="
                + String.join(",", principal.authorities()));

        // Prove the snapshot list rejects arbitrary role additions.
        try {
            principal.authorities().add("ROLE_ADMIN");
            System.out.println("snapshot.mutable=true");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot.mutable=false");
        }

        System.out.println("snapshot.availableAfterClose=true");
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 OrmBoundaryDemo.java
java OrmBoundaryDemo
```

**Exact stdout printed by the program:**

```text
unsafe.afterClose=lazy-failed
snapshot.user=lan
snapshot.id=42
snapshot.enabled=true
snapshot.authorities=ROLE_READER,document:read
snapshot.mutable=false
snapshot.availableAfterClose=true
```

Explanation:

- In the **unsafe** branch, the session had closed before the first `LazyRoles.get()` call, simulating lazy-loading failure.
- In the **snapshot** branch, roles are loaded and copied inside `loadInsideTransaction` before the session closes. `SecuritySnapshot` holds no reference to `AccountEntityLike`, `LazyRoles`, or `FakeSession`.
- `List.copyOf` produces an unmodifiable list; attempting `add` throws `UnsupportedOperationException`. This protects principal data from accidental mutation by business code.
- The simulation does not verify passwords, use `DaoAuthenticationProvider`, or touch a real database. In a Spring Security system, the snapshot serves as `UserDetails` for the provider to check the password hash and issue authentication.

## 10. Spring Boot: Do Not Let OSIV Hide Authentication Design Flaws

In a Spring Boot JPA Servlet application, the property:

```properties
spring.jpa.open-in-view=false
```

can be used to **avoid relying on an `EntityManager` held open across parts of a web request**. When disabled, any lazy access outside a valid transaction/persistence context surfaces earlier. This is generally a beneficial architectural choice when using clear services/DTOs, though you should audit code currently relying on OSIV before enabling it in a running project.

**OSIV is not a security boundary.** Enabling OSIV may let lazy loading in controllers/serialization work in some flows, yet:

- It does not guarantee a persistence context exists **at every point in the security filter chain**, on every request, or in background jobs.
- It does not keep `EntityManager` alive across different requests in the same user session.
- It does not prevent serialization code from causing N+1 queries or unexpected SQL.
- It does not turn an entity into a safe/immutable security principal.
- It does not replace `@Transactional` for data read/write units of work.

If turning off OSIV causes controller errors because a serializer reads a lazy entity, **do not simply re-enable OSIV to "fix" everything**. Identify which endpoint/service should fetch the data and map it to a DTO before returning the response. Likewise, if login fails because `getAuthorities()` reads `roles` outside a transaction, the fix is building a complete `UserDetails` inside the read transaction, not relying on OSIV.

**A typical configuration snippet**:

```properties
# ORM boundaries must be managed by repository/service transactions.
spring.jpa.open-in-view=false

# Only enable bounded SQL debug in test environments, never exposing secrets.
# logging.level.org.hibernate.SQL=DEBUG
```

This property does not create a `UserDetailsService` or guarantee the repository fetches all required authorities; pair it with the proper adapter.

## 11. After Login, What Happens to the Snapshot If DB Roles Change?

Copying authorities into the principal eliminates dependency on the ORM session, yet creates an **authority snapshot at authentication time**. This must be designed alongside authority revocation requirements.

Example:

```text
T0: user "lan" logs in, role = ROLE_EDITOR.
T1: Spring Security keeps Authentication in the HTTP session.
T2: admin revokes ROLE_EDITOR from DB.
T3: "lan" continues sending requests with the old session.
```

At T3, the principal in the session **may still contain `ROLE_EDITOR`** unless the application has a refresh/revalidation mechanism. There is no universal Spring Security rule that every request must re-query `UserDetailsService`.

Options depending on needs:

| Approach | Benefit | Limitation |
| --- | --- | --- |
| Short-lived sessions + re-authentication | Simple, narrows the window of stale data. | Does not revoke immediately upon role change. |
| Invalidate/revoke sessions on permission-change events | Reduces risk of revoked authorities staying active. | Requires distributed session tracking and reliable events. |
| Version claim / authority version checked per request or as needed | Easy detection of stale snapshots. | May add cache/query overhead; must handle races and failure policies. |
| Business authorization reads fresh state on every sensitive operation | Decisions rely on up-to-date permission state inside the business transaction. | Query cost and consistency rules must be designed. |
| Short-lived tokens + refresh/revocation policy (JWT) | Bounds expiration window. | Self-contained JWTs can remain valid until expiry without a revocation mechanism. |

When updating roles/accounts, choose a **real revocation strategy**. Do not "solve" it by stuffing a JPA entity into the principal and hoping it auto-refreshes: a detached entity does not auto-sync, and keeping ORM sessions open causes worse problems.

A valuable practice: use `accountId` in the principal so business services query current resources/conditions. Never treat `username` or lazy data in the principal as a permanent source of truth.

## 12. Transaction Boundaries Do Not Replace Business Security Checks

There are two independent categories of work:

**Authentication-time read**

- Look up username/user ID.
- Fetch password hash, enabled/locked flags, and baseline authorities.
- Return materialized `UserDetails`.
- Provider verifies password.
- Establish initial principal and authorities.

**Business-time authorization/read**

- Fetch the requested object by ID.
- Verify owner, tenant, object status, and policy.
- Use an appropriate business transaction for reads/writes.
- Do not rely solely on a role snapshot if an operation requires up-to-date data-level permissions.

Example business code:

```java
// Code snippet - requires entity, repository, tenant policy, and
// AccountPrincipal defined by the project.
@Transactional(readOnly = true)
public DocumentDto findDocument(long documentId, long accountId) {
    DocumentEntity document = documents.findById(documentId)
            .orElseThrow(DocumentNotFoundException::new);

    if (!document.getOwnerAccountId().equals(accountId)) {
        throw new AccessDeniedException("Forbidden");
    }

    return DocumentDto.from(document);
}
```

This snippet is not a standalone runnable class. It illustrates **owner checking + DTO mapping inside a business transaction**, using the authenticated stable ID. In multi-tenant applications, also check tenant scope; if races can occur between permission checks and writes, design a transaction with locking or conditional writes meeting security requirements.

A security principal **never needs to hold an `EntityManager` open** for business logic to execute fresh queries in its own transactions.

## 13. Handling Performance: N+1, Oversized Graphs, and Caching

### Do Not Turn Every getAuthorities Call into a Query

If `getAuthorities()` accesses lazy roles on an entity, authorization checks can trigger unpredictable SQL, N+1 queries, or detached exceptions. With a snapshot, the authority list is materialized **once when loading the user**.

However, eagerly loading overly deep role/permission trees also causes harm:

- `JOIN FETCH` across multiple collections can multiply result rows.
- An account with thousands of permissions should not blindly load an entire domain graph into the principal.
- If permissions depend on tenant/resource, a global flat list can distort policy.
- Evaluate whether fine-grained permissions truly need to be loaded at login; dynamic permissions can be evaluated per use case.

**Practice:** define a "minimum authentication data set" consisting of user ID/username, hash, flags, and authorities needed for initial policy evaluation. Use targeted projections or entity graphs. Expand data only when needed and tested.

### UserDetails Caching Is a Separate Decision

`UserCache` or `CachingUserDetailsService` can avoid repeated queries, yet caching adds complexity:

- Password hashes may be erased on objects implementing `CredentialsContainer` after authentication; sharing the same cached instance can break subsequent authentications.
- Cached authorities/locked status can become stale after DB updates.
- TTL, invalidation, distributed caching, and permission updates must be explicitly designed.
- If a cache stores a principal holding an entity/lazy proxy, detached bugs persist and become harder to reproduce.

**Never enable caching just to mask unoptimized ORM queries.** Fix the snapshot boundary first, define freshness/revocation policies next, and only then evaluate caching.

### Auditing SQL and Query Counts

Enable appropriate SQL statistics/logging in test environments to verify:

1. The login path executes only the expected user/role queries.
2. `DaoAuthenticationProvider` does not trigger lazy queries outside the transaction via `getAuthorities()`.
3. After `loadUserByUsername` returns, calling `getAuthorities()`/`getUsername()` on the principal adds zero JPA queries.
4. Controllers/JSON serializers do not attempt to traverse an entity stored inside `Authentication`.

Avoid logging full request bodies, `Authorization` headers, raw passwords, or tokens while profiling authentication.

## 14. Testing Transaction Boundaries Properly

A test with `@Transactional` wrapping the entire test method **can hide lazy-loading bugs**. While the test method runs inside a transaction, code accessing collections after repository calls still has an `EntityManager`. Production—especially when handing a principal to security filters or sessions—does not necessarily keep such a transaction open.

### Recommended Test Suite

| Test | Scenario | Expected |
| --- | --- | --- |
| **Principal detached-safe** | Call `loadUserByUsername` through the Spring bean; after it returns, access `getAuthorities()`. | Reads cleanly with no JPA SQL or lazy exceptions. |
| **Provider success** | Log in with valid password via `AuthenticationManager` + `DaoAuthenticationProvider`. | Authenticated `Authentication` with accurate authorities. |
| **Wrong password** | Log in with valid username and wrong password. | Throws `BadCredentialsException`. |
| **Disabled user** | Account has `enabled=false` in DB. | Provider rejects, typically with `DisabledException`. |
| **Lazy roles** | Entity `roles` configured `LAZY`, fetch query/mapper runs properly. | Returned `UserDetails` still has complete roles. |
| **OSIV off** | Web test with `spring.jpa.open-in-view=false`. | Controllers/filters do not need an ORM Session from login to read the principal. |
| **Query count** | Repeated authority checks after login. | Zero extra queries emitted just from accessing principal fields. |
| **Role revocation** | Admin revokes a role on an account with an active session. | Behavior matches the defined refresh/revocation policy. |
| **Concurrency** | Two requests update roles/login concurrently. | Consistent outcome per transaction isolation/revocation policy. |

### Integration Test Pattern to Watch

```java
// Snippet in a @SpringBootTest test class with injected
// UserDetailsService, AuthenticationManager, repository, and seeded DB.
//
// Do not put @Transactional on the whole test method if the goal
// is to prove the principal works after the service transaction.
@Test
void userDetailsAreIndependentAfterReadTransaction() {
    UserDetails user = userDetailsService.loadUserByUsername("lan");

    // Outside loadUserByUsername, its transaction has ended
    // if there is no outer transaction and the Spring proxy works properly.
    assertEquals("lan", user.getUsername());
    assertTrue(user.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_READER")));
}
```

This is **not a complete test class**: it requires sample data, real DB integration setup, bean config, and static imports. If the test framework or caller opens an outer transaction, assertions may still run inside that context; isolate the boundary via proper test config or verify no transaction is active when inspecting the principal after loading.

A stronger complementary test can:

1. Call the service through the Spring proxy.
2. After it returns, assert `TransactionSynchronizationManager.isActualTransactionActive() == false` on the test thread (when no outer transaction exists).
3. Exercise `user.getAuthorities()` and every needed getter.
4. To be certain no ORM calls happen, assert query counts or run with `EntityManager` cleared/closed via valid test mechanisms.

**Never call `entityManager.close()` arbitrarily on a Spring-managed persistence context** to "force" a test; it can corrupt the test environment. Use boundaries, `TestTransaction`, transaction templates, or a proper query-counting framework.

### Why Is Authorization Testing with `@WithMockUser` Not Enough?

`@WithMockUser` injects a mock `Authentication` for permission tests, usually **bypassing `UserDetailsService` and the database**. Those tests can stay green even when `loadUserByUsername` returns a lazy entity that breaks real logins. Include at least one test going through the **real manager/provider** and one verifying `UserDetails` works independently of the session after loading.

## 15. When Is `@Transactional` on the Service Still Not Enough?

Even with the annotation present, errors still happen if:

1. **Self-invocation:** method A on the same object calls `this.loadUserByUsername()`; with proxy-based transactions, the interceptor may not run.
2. **Bean not managed by Spring:** instantiated via `new` instead of dependency injection; no transaction proxy exists.
3. **Mapping not materialized:** returning an entity/wrapper whose `getAuthorities()` reads lazy roles **after the method ends**.
4. **Nested lazy associations:** fetching only roles while permissions inside each role remain lazy.
5. **Wrong transaction manager:** user query uses a different datasource/EM than the active transaction.
6. **Async execution:** a new thread does not automatically inherit the caller thread's transaction/persistence context.
7. **Environment-dependent OSIV:** web tests keep a session open while production or background jobs do not.
8. **Concurrent data modifications:** a `readOnly` transaction alone does not guarantee snapshot consistency across multiple queries under every isolation level.
9. **Custom principal holding a `Supplier`/callback that calls a repository later:** turns `getAuthorities()` into DB/transaction-dependent I/O at authorization time.
10. **Custom password encoder/service also reading a lazy entity:** the provider does more than call `getAuthorities()`; every auth data access must be self-contained after the service returns.

**General fix:** decide the minimal dataset required, place an appropriate service transaction boundary, materialize the entire dataset, return an immutable or self-contained `UserDetails`, and test outside any transaction.

## 16. A Recommended Architecture You Can Apply

### Data Layer

- `AccountRepository` returns `AccountEntity` or a projection with username key, hash, status flags, and required authorities.
- When using entities, fetch only associations needed for authentication instead of switching every mapping to EAGER.
- Unique constraint on username/email key matching registration policy.
- Password hashes must use a proper storage algorithm, never plaintext.

### Authentication Adapter Layer

- `@Service` implementing `UserDetailsService`.
- `@Transactional(readOnly=true)` on the public method called through the Spring proxy.
- Shared normalization/lookup per policy.
- Map authorities directly inside the transaction.
- Return a `UserDetails` containing only plain Java values/collections and required status flags; hold no entities or ORM proxies.
- If the user is not found, throw `UsernameNotFoundException`. Never return `null` or a fake login token.

### Spring Security Layer

- `DaoAuthenticationProvider` uses `UserDetailsService` with a `PasswordEncoder` compatible with stored hashes.
- `ProviderManager`/`AuthenticationManager` handles success/failure.
- Standard filters populate `SecurityContext`; this is separate from the account read transaction.
- Authorization uses the authority snapshot and appropriate business policies; never invoke lazy entity getters from the principal.

### Business Layer

- Use the authenticated account ID, then open a dedicated transaction to read/update resources.
- Check owner/tenant/policy against fresh data when required.
- Return explicit DTOs; never expose entities or password hashes over JSON.
- Define an authority/account-lock invalidation strategy to handle stale principal data.

A configuration commonly valuable for catching hidden ORM dependencies in web layers:

```properties
spring.jpa.open-in-view=false
```

This is a **design recommendation to validate**, not a universal requirement for every app. Whether OSIV is on or off, the principal still must not hold an entity.

## 17. Common Mistakes

1. **Keeping `AccountEntity` directly in `Authentication.principal`.** Entities can detach, contain lazy proxies, or hold sensitive fields; they are not security snapshots.
2. **Letting `UserDetails.getAuthorities()` access `entity.getRoles()`.** Can cause `LazyInitializationException` or late SQL.
3. **Putting `@Transactional` on the method while returning a wrapper holding the entity.** The annotation does not keep the transaction alive after the method returns.
4. **Enabling OSIV to hide lazy errors during login.** OSIV does not span user sessions and does not guarantee context across every filter chain.
5. **Changing every association to EAGER.** Can increase cost, N+1, or graph size; prefer use-case-specific fetches.
6. **Using `@EntityGraph` and still returning the entity as the principal.** The graph helps fetch data, yet still fails to decouple the principal from persistence.
7. **Having only a short repository transaction and mapping roles in the controller.** Outside the transaction, lazy associations can break.
8. **Manually `new`-ing a service annotated with `@Transactional`.** Bypasses Spring's transaction proxy.
9. **Calling an annotated method via `this.` inside the same bean.** Self-invocation normally bypasses the proxy.
10. **Believing `readOnly=true` is security against DB writes.** It is a transaction hint/optimization, not an access-control rule.
11. **Treating a green `@Transactional` test as proof of production safety.** Test transactions can mask detached bugs.
12. **Using `@WithMockUser` to conclude DB login works.** Mocks bypass `UserDetailsService`/providers in many configurations.
13. **Stuffing all permissions/tenant objects into the principal.** Inflates session size, stale data, and leak risks.
14. **Caching principals containing JPA entities.** Caching does not make proxies safe and adds stale-data risks.
15. **Ignoring authority revocation mechanisms.** Snapshots are technically sound yet still require role/session refresh policies.
16. **Checking only `hasRole` without checking resource ownership.** Resource-level authorization is an independent responsibility.
17. **Logging full `Authentication`/entities.** Risks leaking hashes, PII, or data graphs.
18. **Equating `EntityManager` with the HTTP session.** They have different scopes and cannot be substituted for one another.
19. **Confusing the JPA read transaction with password verification.** The transaction only loads data; the provider compares raw passwords with hashes.
20. **Failing to check consistency across multiple queries.** A transaction does not guarantee a fully consistent snapshot under every isolation level.
21. **Catching `LazyInitializationException` and returning empty roles.** Can silently drop user permissions or mask data bugs; fix fetching/mapping instead.
22. **Querying roles when `getAuthorities()` is called post-login.** Turns authorization into uncontrolled DB I/O, prone to scope errors and hard to test.

## 18. Self-Check Knowledge Quiz

**Question 1.** `loadUserByUsername` is annotated with `@Transactional(readOnly=true)`, yet returns a `CustomUserDetails` holding `AccountEntity`. `getAuthorities()` accesses `entity.getRoles()` outside the method. Is this safe?

**Answer:** No. The transactional method has ended; the entity/lazy collection may be detached. Map authorities into a Java collection and build a self-contained `UserDetails` **inside the transaction**.

**Question 2.** Does using `@EntityGraph(attributePaths="roles")` automatically decouple the principal from Hibernate?

**Answer:** No. The graph fetches the relationship in the query, yet the entity remains an ORM object. Copy the needed fields and do not hold the entity in the principal.

**Question 3.** Does `readOnly=true` guarantee the driver/DB rejects all `UPDATE` statements?

**Answer:** No. It is a transaction hint/configuration that can optimize handling; it is not a universal security rule forbidding writes.

**Question 4.** Why does placing `@Transactional` on the entire test method often prevent lazy errors from surfacing?

**Answer:** The persistence context may remain open when assertions access lazy fields. Test the principal outside any transaction to reflect real boundaries.

**Question 5.** If `spring.jpa.open-in-view` is turned off, will login necessarily fail?

**Answer:** No. A properly designed login loads account/authorities and converts them into `UserDetails` inside the transaction, so it does not depend on OSIV.

**Question 6.** An admin deletes `ROLE_EDITOR` in the database after a user logs in. Does the principal in the session update automatically?

**Answer:** Never assume that. The principal is a snapshot; you need refresh/revocation policies or business authorization reading fresh state.

**Question 7.** Why should you not use `Authentication.getPrincipal()` returning a JPA entity to avoid re-querying in business services?

**Answer:** The entity may be detached, hold lazy proxies, stale/sensitive data, and lack an active transaction. Business services should query by stable user ID inside their own transactions.

**Question 8.** `UserDetailsService` just needs to return a `UserDetails` with the right username; why copy the password hash and flags?

**Answer:** `DaoAuthenticationProvider` needs the encoded password and account status to verify credentials. If getters read from a detached entity/proxy, authentication can fail right inside the provider.

**Question 9.** Is putting `@Transactional` on a private method or calling via `this.` in Spring proxy mode reliable?

**Answer:** No. Place the boundary on a public service method of a Spring bean invoked through the right proxy, and test actual transaction behavior.

**Question 10.** A query fetching roles and permissions runs very slowly due to multiple collections. Should you always stick with one giant `JOIN FETCH`?

**Answer:** Not necessarily. Consider projections, separate queries inside a service transaction, limiting principal data, and optimizing based on actual SQL.

## 19. Official References

- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): default transactions on repository methods, transactional query methods, service boundaries, and the meaning of `readOnly`.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation, proxies, annotation configuration, and transaction semantics.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): when interceptors/proxies handle transactions, self-invocation, and limitations.
- [Spring Data JPA — EntityGraph](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.entity-graph): controlling fetch plans for repository queries.
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html): role as the data source supplying `UserDetails`.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): how the provider uses user records, password encoders, and authorities.
- [Hibernate ORM — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching): lazy/eager, join fetch, and fetch strategies.
- [Spring Boot — JPA Configuration](https://docs.spring.io/spring-boot/reference/data/sql.html#data.sql.jpa-and-spring-data): JPA configuration in Spring Boot, including version-specific OSIV behavior.

**Conclusion:** the account read transaction should be a **short, self-contained unit of work**: look up the account, load required attributes/authorities, convert them into a standalone `UserDetails`, and close the transaction. Afterward, `Authentication`, `SecurityContext`, and authorization layers do not need to know whether the entity detached or the Hibernate Session closed. Avoid relying on OSIV and never use a JPA entity as the principal; separately design authority freshness and business transactions to stay safe as users continue acting after login.
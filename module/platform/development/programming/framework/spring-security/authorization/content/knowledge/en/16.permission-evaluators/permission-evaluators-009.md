# Avoiding Per-Item Queries When Checking Collections with `PermissionEvaluator`

## 1. Why can a 100-document page trigger 101 queries?

An API returns the list of documents the current user is allowed to read. A developer writes:

```java
@PostFilter("hasPermission(filterObject, 'read')")
public List<Document> listDocuments() {
    return documentRepository.findAll();
}
```

Here `@PostFilter` iterates through the results and evaluates the expression for **each element**; `filterObject` is the object currently being inspected. If `PermissionEvaluator.hasPermission(...)` calls the database once to check permission on each document, a single request can execute:

- 1 query to fetch the 100 documents;
- 100 more queries to check read permission for each document;
- about **101 queries** in total to return one list.

That is an **N+1 query** pattern in permission checking: it does not necessarily come from Hibernate lazy loading; the per-element authorization step itself can spawn N independent queries. On a page of 2,000 records, a single request might need around 2,001 SQL calls, not counting loading owners, tenants, ACLs, role hierarchies, or additional metadata.

The issue is even more serious for **security and pagination**: loading every document and filtering in memory causes the backend to touch data outside the caller's read scope; if pagination happens before filtering, the returned page may have fewer elements than requested, and total record/page counts will be wrong.

This Knowledge article belongs to **Spring Security – authorization**, focusing on **PermissionEvaluator**. After this lesson, you will:

1. Spot N+1 patterns when `@PostFilter`, `@PreFilter`, or loops invoke `hasPermission(...)`.
2. Understand when permissions are evaluated **per element**, across both small and large collections.
3. Know how to push permission predicates down into SQL with `WHERE`/`EXISTS`/`JOIN`, or query permissions **once over a batch of IDs**.
4. Design security boundaries so clients cannot spoof user/tenant values.
5. Use Java 17+ / Spring Boot, JDBC, and H2 to run an example comparing **7 DB calls vs. 1 call** for the same result.
6. Test DB call counts, exact permissions, missing-authority/anonymous cases, and cross-tenant data.
7. Understand the limits of caching, pagination, transactions, indexes, and re-checking permissions after data changes.

**Principle:** performance optimizations must never relax permissions. If a user lacks permission to read a record, every strategy—per-element, batch, or SQL—must equally deny it.

## 2. Mechanism: how many calls does `@PostFilter` + `hasPermission` make?

When `@EnableMethodSecurity` is enabled, Spring Security registers interceptors for `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter`. In the opening example:

```text
Caller
  |
  v
Spring-managed service proxy
  |
  v
listDocuments() -> repository.findAll()
  |                      |
  |                     1 SQL
  v
List<Document> of N elements
  |
  v
@PostFilter: for each filterObject
  |---- hasPermission(document 1, "read") -> ACL/DB lookup
  |---- hasPermission(document 2, "read") -> ACL/DB lookup
  |---- ...
  |---- hasPermission(document N, "read") -> ACL/DB lookup
  |
  v
Filtered list returned to caller
```

`hasPermission(filterObject, 'read')` invokes the signature:

```java
boolean hasPermission(
    Authentication authentication,
    Object targetDomainObject,
    Object permission
);
```

If the expression uses an ID:

```java
@PreAuthorize("hasPermission(#id, 'Document', 'read')")
```

then Spring invokes the other signature:

```java
boolean hasPermission(
    Authentication authentication,
    java.io.Serializable targetId,
    String targetType,
    Object permission
);
```

These two signatures are shown only as an API contract reminder. What causes N+1 **is not the interface itself** but its implementation—for instance, each call running `repository.existsBy...` or `aclService.readAclById(...)` individually for a single resource.

### Simple cost illustration

Suppose each database round-trip averages 3 ms in a given environment, ignoring other overhead just to see the scale:

| Elements evaluated (`N`) | SQL calls in N+1 strategy | Hypothetical round-trip time |
| ---: | ---: | ---: |
| 10 | 11 | 33 ms |
| 100 | 101 | 303 ms |
| 1,000 | 1,001 | 3,003 ms |
| 5,000 | 5,001 | 15,003 ms |

This is **not a benchmark**. Databases have connection pools, buffers, query planners, and variable latency; individual queries vary in speed. The table merely shows that network or JDBC round-trips grow linearly with `N`. In practice, a set-based query still consumes resources, yet typically eliminates many round-trips and can utilize indexes much better.

### Why not just “increase the connection pool”?

Growing the pool can overload the database even faster without reducing queries per request. The core fix is **reducing how many times you ask the same kind of decision item-by-item**, pushing predicates into the data layer or using a batch API. Before optimizing, measure **actual query counts** rather than just list lengths.

## 3. Solution approaches and selection priorities

| Approach | Typical permission lookups | Pros | Safety conditions |
| --- | --- | --- | --- |
| `@PostFilter` + evaluator querying per object | `N` lookups after list query | Easy to write, expressive | Suitable for small sets; avoid loading unnecessary sensitive data |
| SQL `WHERE`/`EXISTS` with owner/tenant/ACL predicates | Usually 1 query of already-filtered data | Fewer round-trips, accurate pagination | Tenant/user from authenticated source; query matches policy |
| Batch-read ACL/allowed IDs then filter in memory | 1 or a few permission queries for the whole set | Reusable across data sources; handles complex rules | Every ID verified; fail closed; avoid exposing data before filtering |
| Per-request permission cache | Reduces repeated lookups for the **same ID** | Useful when the same object appears multiple times | Keyed by user/tenant/action; does not turn N distinct IDs into 1 query |
| Shared permission cache (Redis/Caffeine) | Eliminates lookups on cache hit | Raises hit rate across requests | Invalidation on revoke/ACL change; never share `allowed=true` across users |
| Batch API from policy decision point (PDP) | Single call evaluating many resources | Cuts network hops to external authz services | Results must map accurately by ID, user, tenant, and action |

For endpoints returning large lists, the preferred choice is usually **pushing authorization policy down into the list query**, then using method security to guard the service boundary. When policy cannot be fully expressed in SQL, consider **batch authorization** over candidate IDs rather than invoking the evaluator sequentially by default.

## 4. Example permission rules: coarse authority, tenant, and ACL

The demo uses three layers of checks:

1. The caller must be authenticated, non-anonymous, and hold the `document:read` authority.
2. The caller's tenant is resolved via a **server-side directory**. That tenant must match `documents.tenant_id`.
3. The caller may read a document if they are `owner_name` or have a matching `'read'` grant record in `document_grants`.

Written as an expression:

```text
canRead(user, document) =
    authenticated(user)
    AND hasAuthority(user, "document:read")
    AND sameTenant(user, document)
    AND (
          document.ownerName == user.username
          OR grantExists(document.id, user.username, "read")
        )
```

Sample dataset:

| ID | Tenant | Owner | Document title | Share grant |
| ---: | --- | --- | --- | --- |
| 1 | T1 | alice | Alpha | None |
| 2 | T1 | bob | Beta | Grants `alice` `read` |
| 3 | T1 | owner3 | Gamma | None |
| 4 | T2 | owner4 | Delta | None |
| 5 | T1 | alice | Epsilon | None |
| 6 | T2 | owner6 | Zeta | None |

The server directory lists `alice` and `bob` in tenant `T1`, and `carol` in `T2`. With `document:read`, `alice` sees IDs **[1, 2, 5]**, and `bob` sees **[2]**. Read permission must never be inferred from client-declared owner/tenant fields. If the caller lacks a profile or authority, both list approaches must deny access.

### Permissions must come from server-side data

Never use the following check to grant permission:

```java
// Unsafe if document is a client-supplied DTO:
return authentication.getName().equals(document.owner());
```

A client can submit `{"id":4,"owner":"alice","tenant":"T1"}` even though the database actually stores ID 4 under tenant T2. When checking with SQL, use only the ID from input to look up the real record, taking `owner`, `tenant`, and `grant` from the database, and user/tenant from the verified identity.

## 5. Runnable example: N+1 vs. set-filtered SQL

The project uses **Java 17, Spring Boot 3.5.8, Spring Security 6.x, Spring JDBC, and H2**. This is a learning demo, not a recommendation to pin this exact patch version in production. We pin versions so the example is easy to reproduce.

The goal is two APIs over the same data:

- **Legacy:** `@PostFilter("hasPermission(filterObject, 'read')")`, querying the list once and having the evaluator issue one permission query per **each** document.
- **Optimized:** the same policy implemented in one SQL query `WHERE tenant_id = ? AND (owner = ? OR EXISTS (...))`.

For deterministic counting, the app increments `DbCalls` **before each JDBC call made by the repository**. This is a counter of *query calls issued by demo code*, not a profiler of all internal statements during H2 or Spring Boot startup. With a 6-document dataset, the legacy path makes 1 + 6 = **7** JDBC calls, while the optimized path makes **1**.

### 5.1. Project structure

```text
permission-batch-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── PermissionBatchApplication.java
    │   │   ├── Document.java
    │   │   ├── UserDirectory.java
    │   │   ├── DbCalls.java
    │   │   ├── DocumentRepository.java
    │   │   ├── DocumentPermissionEvaluator.java
    │   │   └── DocumentService.java
    │   └── resources/
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/demo/
        └── DocumentServiceTest.java
```

### 5.2. Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'permission-batch-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-jdbc` provides `JdbcTemplate` and a connection pool; `h2` is the in-memory database. Spring Boot auto-creates the H2 datasource and runs `schema.sql` then `data.sql` for embedded databases on context startup. No JPA/entity mapping is needed for this demo so we can directly count the queries executed by our code.

### 5.3. Schema and data

**`src/main/resources/schema.sql`:**

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(30) NOT NULL,
    owner_name VARCHAR(100) NOT NULL,
    title VARCHAR(150) NOT NULL
);

CREATE TABLE document_grants (
    document_id BIGINT NOT NULL,
    grantee VARCHAR(100) NOT NULL,
    permission VARCHAR(30) NOT NULL,
    PRIMARY KEY (document_id, grantee, permission),
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX idx_documents_tenant_owner
    ON documents(tenant_id, owner_name, id);

CREATE INDEX idx_grants_grantee_permission_document
    ON document_grants(grantee, permission, document_id);
```

**`src/main/resources/data.sql`:**

```sql
INSERT INTO documents (id, tenant_id, owner_name, title) VALUES
    (1, 'T1', 'alice', 'Alpha'),
    (2, 'T1', 'bob', 'Beta'),
    (3, 'T1', 'owner3', 'Gamma'),
    (4, 'T2', 'owner4', 'Delta'),
    (5, 'T1', 'alice', 'Epsilon'),
    (6, 'T2', 'owner6', 'Zeta');

INSERT INTO document_grants (document_id, grantee, permission) VALUES
    (2, 'alice', 'read');
```

The indexes above are just a starting point: with a real database, inspect query plans and table sizes. `document_grants` has a foreign key so grants cannot point to nonexistent documents. Production conventions may also include tenant inside the grant table and stricter tenant constraints.

### 5.4. Domain object

**`src/main/java/demo/Document.java`:**

```java
package demo;

public record Document(
        long id,
        String tenant,
        String owner,
        String title) {
}
```

The record holds owner/tenant for display, **not as proof of permission** if supplied by a caller. The evaluator in the demo takes only the ID and checks permissions against DB-stored data.

### 5.5. User directory and coarse-grained permission policy

**`src/main/java/demo/UserDirectory.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

record ViewerScope(String username, String tenant) {
}

@Component("userDirectory")
public class UserDirectory {

    private final Map<String, String> tenants = Map.of(
        "alice", "T1",
        "bob", "T1",
        "carol", "T2"
    );

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public ViewerScope scope(Authentication auth) {
        if (auth == null
                || !auth.isAuthenticated()
                || trustResolver.isAnonymous(auth)) {
            return null;
        }

        boolean canRead = auth.getAuthorities() != null
            && auth.getAuthorities().stream()
                .anyMatch(a -> "document:read".equals(a.getAuthority()));

        if (!canRead) {
            return null;
        }

        String tenant = tenants.get(auth.getName());
        if (tenant == null) {
            return null;
        }

        return new ViewerScope(auth.getName(), tenant);
    }

    public boolean canBrowse(Authentication auth) {
        return scope(auth) != null;
    }

    public ViewerScope requireScope(Authentication auth) {
        ViewerScope result = scope(auth);
        if (result == null) {
            throw new AccessDeniedException("No trusted document read scope");
        }
        return result;
    }
}
```

The small `ViewerScope` contract holds the user and tenant verified by the server directory. In a real system, `auth.getName()` might be a username, JWT `sub`, or another identifier; map it to a stable internal ID. In multi-tenant apps, obtain the tenant from a trusted identity/permission mapping, **never from an unverified query parameter**.

`canBrowse` is the **feature-level authorization** step on the service; the evaluator adds **object-level** conditions. If the user is absent from the directory, lacks the authority, or is anonymous, the policy returns false. In particular, `AnonymousAuthenticationToken` can have `isAuthenticated() == true`, so `AuthenticationTrustResolver` is required.

### 5.6. Counter of code-issued JDBC calls

**`src/main/java/demo/DbCalls.java`:**

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class DbCalls {

    private final AtomicInteger calls = new AtomicInteger();

    public void record() {
        calls.incrementAndGet();
    }

    public int value() {
        return calls.get();
    }

    public void reset() {
        calls.set(0);
    }
}
```

`DbCalls` is an application-wide counter intended only for this sequential demo program. Under concurrent requests, this counter **does not represent a single specific request**. In production, use request-correlated query metrics/tracing, a JDBC proxy, or real observability tooling; never use a global variable like this for per-user accounting.

### 5.7. Repository: three methods and two SQL strategies

**`src/main/java/demo/DocumentRepository.java`:**

```java
package demo;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {

    private static final RowMapper<Document> MAPPER = (rs, row) ->
        new Document(
            rs.getLong("id"),
            rs.getString("tenant_id"),
            rs.getString("owner_name"),
            rs.getString("title")
        );

    private final JdbcTemplate jdbc;
    private final DbCalls dbCalls;

    public DocumentRepository(JdbcTemplate jdbc, DbCalls dbCalls) {
        this.jdbc = jdbc;
        this.dbCalls = dbCalls;
    }

    // One query loading ALL records; this is the unoptimized path.
    public List<Document> loadAll() {
        dbCalls.record();
        return jdbc.query(
            "SELECT id, tenant_id, owner_name, title " +
            "FROM documents ORDER BY id",
            MAPPER
        );
    }

    // One permission lookup by ID; calling N times causes N DB round-trips.
    public boolean canRead(ViewerScope scope, long id) {
        dbCalls.record();

        Integer matches = jdbc.queryForObject(
            """
            SELECT COUNT(*)
            FROM documents d
            WHERE d.id = ?
              AND d.tenant_id = ?
              AND (
                    d.owner_name = ?
                    OR EXISTS (
                        SELECT 1
                        FROM document_grants g
                        WHERE g.document_id = d.id
                          AND g.grantee = ?
                          AND g.permission = 'read'
                    )
              )
            """,
            Integer.class,
            id,
            scope.tenant(),
            scope.username(),
            scope.username()
        );

        return matches != null && matches > 0;
    }

    // One query returning only the documents the caller is allowed to see.
    public List<Document> loadVisible(ViewerScope scope) {
        dbCalls.record();

        return jdbc.query(
            """
            SELECT d.id, d.tenant_id, d.owner_name, d.title
            FROM documents d
            WHERE d.tenant_id = ?
              AND (
                    d.owner_name = ?
                    OR EXISTS (
                        SELECT 1
                        FROM document_grants g
                        WHERE g.document_id = d.id
                          AND g.grantee = ?
                          AND g.permission = 'read'
                    )
              )
            ORDER BY d.id
            """,
            MAPPER,
            scope.tenant(),
            scope.username(),
            scope.username()
        );
    }
}
```

Points to read carefully:

- `loadAll()` runs one SQL statement yet fetches **records from other tenants too**. That is why real APIs should not call `findAll()` and filter in memory.
- `canRead(scope, id)` runs a `COUNT(*)` each time with the same tenant, user, and permission; if the evaluator invokes it per object, SQL executes N times.
- `loadVisible(scope)` puts the **exact same rules** into one SQL query: `tenant` matches and (`owner` matches or a `'read'` grant exists). The database can optimize the result set using indexes and the query planner.
- Every variable uses `JdbcTemplate` `?` bind parameters, **never concatenating SQL from client usernames or IDs**, preventing SQL injection.
- Because the query enforces `d.tenant_id = ?`, a record in T2 will not be returned to a T1 principal even if its ID is supplied or an invalid grant exists.
- `ORDER BY d.id` guarantees deterministic ordering in the demo. For production pagination, use a stable `ORDER BY` with a tie-breaker when needed.

**Distinguish call count from execution time:** optimized does not “compute permissions for free”; the database still evaluates owner/ACL predicates for candidate rows. The benefit is set-based filtering in a single SQL call, leveraging indexes and avoiding repeated round-trips.

### 5.8. `PermissionEvaluator` intentionally using the N+1 path for demonstration

**`src/main/java/demo/DocumentPermissionEvaluator.java`:**

```java
package demo;

import java.io.Serializable;

import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {

    private final UserDirectory directory;
    private final DocumentRepository repository;

    public DocumentPermissionEvaluator(
            UserDirectory directory,
            DocumentRepository repository) {
        this.directory = directory;
        this.repository = repository;
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Object targetDomainObject,
            Object permission) {

        if (!(targetDomainObject instanceof Document document)) {
            return false;
        }

        // Trust only the ID; never trust owner/tenant from the input object.
        return allowed(authentication, document.id(), permission);
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Serializable targetId,
            String targetType,
            Object permission) {

        if (!"Document".equals(targetType)
                || !(targetId instanceof Long id)) {
            return false;
        }

        return allowed(authentication, id, permission);
    }

    private boolean allowed(
            Authentication authentication,
            Long id,
            Object permission) {

        if (id == null || !"read".equals(permission)) {
            return false;
        }

        ViewerScope scope = directory.scope(authentication);
        if (scope == null) {
            return false;
        }

        // One JDBC query PER hasPermission call.
        return repository.canRead(scope, id);
    }
}
```

This evaluator is correct in terms of **permission outcomes** but suboptimal when iterating over large lists. Implementing both overloads ensures `hasPermission(object, 'read')` and `hasPermission(id, 'Document', 'read')` share the same policy. However, the overload is invoked **once per object**, producing `N` queries when attached to `@PostFilter`.

Do not add a singleton cache like `Map<Long, Boolean>` to “fix” N+1. Keys missing user/tenant/action can leak cached `true` decisions to other users. Moreover, a per-item cache does not eliminate N lookups for N completely distinct IDs on a cold cache; SQL/batching is usually more appropriate.

### 5.9. Service: slow method and optimized method

**`src/main/java/demo/DocumentService.java`:**

```java
package demo;

import java.util.List;

import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository repository;
    private final UserDirectory directory;

    public DocumentService(
            DocumentRepository repository,
            UserDirectory directory) {
        this.repository = repository;
        this.directory = directory;
    }

    @PreAuthorize("@userDirectory.canBrowse(authentication)")
    @PostFilter("hasPermission(filterObject, 'read')")
    public List<Document> listLegacy() {
        return repository.loadAll();
    }

    @PreAuthorize("@userDirectory.canBrowse(authentication)")
    public List<Document> listOptimized() {
        var authentication = SecurityContextHolder.getContext()
            .getAuthentication();
        ViewerScope scope = directory.requireScope(authentication);

        // DB returns only documents that already satisfy the permission rules.
        return repository.loadVisible(scope);
    }
}
```

`listLegacy` must go through a Spring proxy for `@PostFilter` to run; calling `new DocumentService(...)`, internal `this.listLegacy()`, or omitting `@EnableMethodSecurity` will bypass the interceptor. Therefore, the example **must not be used directly to expose endpoints** without ensuring proper call routing and permissions.

`@PreAuthorize("@userDirectory.canBrowse(authentication)")` protects **both** methods at the feature level: the caller must be a real user holding the authority and a directory tenant. Then:

- `listLegacy`: queries all, then runs `hasPermission` per document.
- `listOptimized`: `UserDirectory` resolves the trusted scope and the repository loads only visible rows.

Because the exact same owner/grant/tenant rule is encoded in `canRead` and `loadVisible`, both paths must return the exact same set of IDs. In a real codebase, prevent two policy implementations from **drifting apart** as new states, permission types, or tenants are added: write comparison integration/contract tests, share controlled query fragments/specifications, or design a unified authorization service.

### 5.10. Enabling Method Security and running the scenario

**`src/main/java/demo/PermissionBatchApplication.java`:**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class PermissionBatchApplication {

    public static void main(String[] args) {
        SpringApplication.run(PermissionBatchApplication.class, args);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    @Profile("!test")
    CommandLineRunner runDemo(DocumentService service, DbCalls calls) {
        return args -> {
            try {
                authenticateAs("alice", "document:read");

                calls.reset();
                System.out.println("ALICE_LEGACY_IDS: "
                    + ids(service.listLegacy()));
                System.out.println("ALICE_LEGACY_DB_CALLS: "
                    + calls.value());

                calls.reset();
                System.out.println("ALICE_OPTIMIZED_IDS: "
                    + ids(service.listOptimized()));
                System.out.println("ALICE_OPTIMIZED_DB_CALLS: "
                    + calls.value());

                authenticateAs("bob", "document:read");
                System.out.println("BOB_OPTIMIZED_IDS: "
                    + ids(service.listOptimized()));

                authenticateAs("bob", "unrelated:read");
                expectDenied("NO_AUTHORITY",
                    () -> service.listOptimized());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static List<Long> ids(List<Document> docs) {
        return docs.stream().map(Document::id).toList();
    }

    private static void authenticateAs(String username, String authority) {
        var token = new UsernamePasswordAuthenticationToken(
            username,
            "demo-only",
            List.of(new SimpleGrantedAuthority(authority))
        );
        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(token);
        SecurityContextHolder.setContext(context);
    }

    private static void expectDenied(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException denied) {
            System.out.println(label + ": DENIED");
        }
    }
}
```

`@EnableMethodSecurity` enables `@PreAuthorize` and `@PostFilter`. The `MethodSecurityExpressionHandler` bean is declared `static` and calls `setPermissionEvaluator(...)` so `hasPermission` uses the application's evaluator. This method **does not automatically pull in ACLs**: our evaluator uses JDBC, so the Spring Security ACL module is not needed.

Creating an already-authenticated `UsernamePasswordAuthenticationToken` is strictly for **this simulation program**. In real applications, tokens/contexts must come from a verified authentication provider, session, or bearer JWT; never build a trusted token from an arbitrary client-sent `username`. Every identity switch in the demo creates a fresh context and clears it in `finally`.

### 5.11. Running and comparing stdout

In the directory containing `build.gradle`, if the Gradle Wrapper is present:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```bash
.\gradlew.bat bootRun
```

If there is no Wrapper yet but a compatible Gradle version is installed, run `gradle bootRun` or generate the Gradle Wrapper first. Aside from Spring Boot startup logs, the lines **directly printed by the demo code** are:

```text
ALICE_LEGACY_IDS: [1, 2, 5]
ALICE_LEGACY_DB_CALLS: 7
ALICE_OPTIMIZED_IDS: [1, 2, 5]
ALICE_OPTIMIZED_DB_CALLS: 1
BOB_OPTIMIZED_IDS: [2]
NO_AUTHORITY: DENIED
```

**Exact explanation of the counts:**

1. Legacy runs `loadAll()` once, receiving 6 documents. `@PostFilter` runs the evaluator on all 6; each evaluator invokes `canRead()` for one query. Total `DbCalls.record()` calls = **1 + 6 = 7**.
2. Optimized runs `loadVisible(scope)` once. There is no `@PostFilter` on this method, so there are no 6 extra lookups. Total = **1**.
3. Both return `[1, 2, 5]` for `alice` (owned documents 1/5 and grant on 2). Document `3` is unauthorized and documents `4`, `6` in tenant T2 do not appear.
4. `bob` sees `[2]`. When authority changes to `unrelated:read`, `@PreAuthorize` denies the call without running the repository.

This counts **JDBC calls issued by our code**, not exact network packets, scanned rows, wall-clock time, or database CPU. Under different SQL optimizers, a single statement can still perform multiple internal operations. Proving production performance requires p50/p95/p99 latency, query plans, I/O, CPU, scanned rows, connections, and pagination measurements.

## 6. Testing: permissions stay identical while dropping from 7 queries to 1

**`src/test/java/demo/DocumentServiceTest.java`:**

```java
package demo;

import java.io.Serializable;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class DocumentServiceTest {

    @Autowired DocumentService service;
    @Autowired PermissionEvaluator evaluator;
    @Autowired DbCalls calls;

    @BeforeEach
    void resetCounter() {
        calls.reset();
    }

    private List<Long> ids(List<Document> documents) {
        return documents.stream().map(Document::id).toList();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void bothPathsReturnSameRowsButOneUsesFewerQueries() {
        List<Long> legacy = ids(service.listLegacy());
        assertEquals(List.of(1L, 2L, 5L), legacy);
        assertEquals(7, calls.value());

        calls.reset();
        List<Long> optimized = ids(service.listOptimized());
        assertEquals(legacy, optimized);
        assertEquals(1, calls.value());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void onlyBobsDocumentIsVisible() {
        assertEquals(List.of(2L), ids(service.listOptimized()));
        assertEquals(1, calls.value());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void forgedDtoCannotOverrideServerTenantOrOwner() {
        var auth =
            SecurityContextHolder.getContext().getAuthentication();

        // ID 4 actually belongs to tenant T2: a forged DTO claiming T1/alice
        // does not cause the evaluator to grant access.
        Document forged = new Document(4L, "T1", "alice", "Forged");
        assertFalse(evaluator.hasPermission(auth, forged, "read"));

        assertFalse(evaluator.hasPermission(
            auth, (Serializable) 4L, "Document", "read"
        ));

        // Document 2 has a read share granted to alice.
        assertTrue(evaluator.hasPermission(
            auth, (Serializable) 2L, "Document", "read"
        ));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "unrelated:read")
    void missingAuthorityDeniesBeforeDataQuery() {
        assertThrows(AccessDeniedException.class,
            () -> service.listLegacy());
        assertThrows(AccessDeniedException.class,
            () -> service.listOptimized());

        assertEquals(0, calls.value());
    }

    @Test
    @WithMockUser(username = "ghost", authorities = "document:read")
    void missingTrustedProfileFailsClosed() {
        assertThrows(AccessDeniedException.class,
            () -> service.listOptimized());
    }

    @Test
    @WithAnonymousUser
    void anonymousPrincipalIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> service.listOptimized());
    }
}
```

Run:

```bash
./gradlew test
```

`@SpringBootTest` loads a real context, and `@WithMockUser`/`@WithAnonymousUser` from `spring-security-test` configure `Authentication` for Method Security to evaluate. `@ActiveProfiles("test")` disables the CLI runner so the demo does not print stdout during tests.

Tests use `@Autowired DocumentService`: calls must go through the **Spring-managed proxy** for `@PostFilter` to actually run. A unit test instantiating `new DocumentService(...)` and comparing results **does not verify** Spring Method Security.

Note that `DbCalls` in the demo is a singleton and tests here assume sequential execution. If tests run in parallel or other tasks share the repository, replace it with per-test/per-request metrics/tracing. For JPA, you can use SQL statistics/`StatementInspector`; for JDBC, use a datasource proxy or tracing. Never rely on a single global counter in production.

## 7. Filtering datasets at the SQL layer: not just a performance issue

### 7.1. Why are `WHERE` + `EXISTS` usually better than post-read filtering?

An SQL query incorporating caller permissions looks like:

```sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = :trustedTenant
  AND (
      d.owner_name = :trustedUsername
      OR EXISTS (
          SELECT 1
          FROM document_grants g
          WHERE g.document_id = d.id
            AND g.grantee = :trustedUsername
            AND g.permission = 'read'
      )
  )
ORDER BY d.id;
```

The `:trustedTenant` and `:trustedUsername` syntax illustrates **named parameters**; use `NamedParameterJdbcTemplate`, JPA query parameters, or an appropriate adapter. Plain `JdbcTemplate` in section 5 uses `?`.

The database can use indexes, joins, or semi-joins to process rows in bulk. More importantly, the API only materializes valid rows. One pass to fetch the list plus one pass per item for policy checks is no longer needed.

**Caveat:** the SQL query must accurately mirror every constraint, such as `PUBLISHED` status, tenant, share expiration, roles, deny ACEs, and field-level redaction if the domain requires them. A fast query that forgets a tenant or revocation predicate is a far worse security bug than N+1.

### 7.2. Avoiding duplicates when using JOIN

An error-prone query:

```sql
SELECT d.*
FROM documents d
JOIN document_grants g ON g.document_id = d.id
WHERE g.grantee = :username;
```

It can exclude documents the owner is allowed to view (if no grant row exists), return duplicate rows when multiple grants exist, and omit tenant checks. `EXISTS` helps because we only need to test whether **at least one matching grant exists**, avoiding row multiplication from many-to-one joins. If using a join, properly handle owner, tenant, permission, duplicates, and pagination.

### 7.3. Pagination must happen **after permission predicates**

Example request `pageSize = 10`:

1. Initial query fetches 10 arbitrary documents.
2. `@PostFilter` drops 9 unauthorized documents.
3. Client receives only 1 document, even though hundreds of authorized documents exist further down.
4. `totalElements` (if computed before filtering) can include documents the user may not see, breaking the UI and sometimes leaking metadata.

The right approach places permission predicates in SQL **before** `LIMIT`/`OFFSET` or cursor/keyset pagination applies:

```sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = :tenant
  AND (
      d.owner_name = :username
      OR EXISTS (
          SELECT 1
          FROM document_grants g
          WHERE g.document_id = d.id
            AND g.grantee = :username
            AND g.permission = 'read'
      )
  )
ORDER BY d.id
LIMIT :pageSize OFFSET :offset;
```

This is illustrative SQL on databases supporting `LIMIT/OFFSET`; frameworks and DB dialects paginate differently. The `COUNT(*)` query for total elements must use the **exact same permission predicates**, never counting the whole tenant or whole table and filtering afterward. For very large datasets, consider keyset pagination on `(created_at, id)` or a stable sort key.

## 8. When policy cannot fit completely in SQL: batch permission lookup

Sometimes decisions depend on an external policy service outside the database, multiple resource types, complex ACLs, or distributed data. You do not have to cram everything into one giant SQL query; instead, design **bulk authorization**.

### 8.1. Batch workflow

```text
1. Authenticate caller -> trustedPrincipal, trustedTenant, action
2. Fetch a bounded set of candidate IDs from repository
3. Call authorizationService.allowedIds(user, tenant, action, ids)
4. Receive permitted Set<ID> and verify requested scope/completeness
5. Filter candidate data or re-query only permitted IDs
6. Apply data limits, sorting, pagination, and additional policies
```

Instead of:

```java
for (Document document : documents) {
    if (permissionEvaluator.hasPermission(
            authentication, document, "read")) {
        result.add(document);
    }
}
```

create a dedicated API:

```java
// Design signature; not a standalone runnable snippet.
Set<Long> allowedDocumentIds(
    ViewerScope viewer,
    String permission,
    Set<Long> candidateIds
);
```

This API can run a single SQL query:

```sql
SELECT d.id
FROM documents d
WHERE d.id IN (:ids)
  AND d.tenant_id = :tenant
  AND (
      d.owner_name = :username
      OR EXISTS (
          SELECT 1
          FROM document_grants g
          WHERE g.document_id = d.id
            AND g.grantee = :username
            AND g.permission = 'read'
      )
  );
```

`IN (:ids)` illustrates `NamedParameterJdbcTemplate`/ORM collection binding, **never** manually concatenating client IDs into SQL strings. When the ID set is large, chunk batches within DB parameter limits instead of sending hundreds of thousands of bind variables in one statement, or use temporary tables/table-valued parameters if the DB supports them.

### 8.2. Important note for multi-item write operations

If an API is `updateDocuments(List<Long> ids)`, silently dropping unauthorized items and updating the rest can violate the business contract. Decide explicitly:

- **All-or-nothing:** require `allowedIds` to contain **the entire requested ID set**; if any ID is unknown, nonexistent, cross-tenant, or denied, **update nothing**; use transactions and write-time constraints.
- **Intentional partial success:** return per-item `ALLOWED`/`DENIED` statuses under an explicit contract without leaking details about unauthorized resources.

`@PreFilter("hasPermission(filterObject, 'write')")` by default means filtering input elements. It **does not guarantee atomicity** or return per-item errors; the collection may be mutated/trimmed before the method body runs. Therefore, for financial operations, order approvals, or bulk deletes, clarify business expectations before using a filter.

### 8.3. Avoiding discrepancies from duplicate IDs and changing state

- Canonicalize ID lists, handle `null`, duplicate IDs, nonexistent IDs, and enforce input size limits.
- An `allowedIds` result missing a record could mean it **does not exist** or is **unauthorized**; endpoints do not necessarily need to reveal the difference.
- Avoid taking `viewerId`/`tenantId` directly from JSON as permission proof; derive them from the verified principal.
- If permissions can be revoked between prefetch and write, add constraints in the transaction/update or use an appropriate consistency mechanism.
- Never cache `allowedIds` indefinitely. Permission sets depend on principal, tenant, action, resources, and policy version.

## 9. Why doesn't caching solve N+1 by itself?

Suppose `PermissionEvaluator` has a cache:

```text
key = (userId, tenantId, documentId, permission, policyVersion)
```

This key is far better than keying solely on `documentId`, yet when a first request iterates over **1,000 distinct IDs**, a cold cache still triggers **1,000 lookups** before future hits can occur. Caching helps when:

- the same object is checked repeatedly within a request;
- consecutive requests inspect already-cached entries;
- ACLs change infrequently and a reliable invalidation strategy exists.

Caching also carries costs:

- **Revoke/ownership/tenant** changes make previously cached `allowed=true` results invalid.
- Cross-user/tenant leakage if keys omit identity scope.
- Memory growth proportional to `(users × resources × actions × policies)`.
- Distributed caches must coordinate invalidation across nodes.
- Policies must refresh whenever permission masks, group memberships, or role hierarchies change.

**Priority:** first eliminate unnecessary queries using SQL/batching, then apply controlled caching where it genuinely helps. For sensitive policies, avoid caching allow decisions altogether if freshness cannot be guaranteed.

### How does per-request caching differ from app-wide caching?

A `RequestScope` memoization can retain looked-up decisions for `(user, tenant, ID, action)` during a single request; it helps when the **same ID** is checked several times. Meanwhile, `PermissionEvaluator` is normally a singleton Spring bean: never store `Authentication currentUser` in a mutable field across concurrent requests. In async tasks or jobs with no HTTP request, a request scope may not exist at all.

## 10. Measuring and optimizing queries systematically

Do not optimize based on guesswork. A practical workflow:

1. **Measure baseline:** how many SQL statements run in a list request? How many fetch data vs. evaluator/ACL checks? How many candidate rows are touched?
2. **Analyze traces:** look for `SELECT ... FROM acl WHERE object_id = ?` repeated N times or repeated `existsBy...` calls with different IDs.
3. **Inspect query plans:** run `EXPLAIN`/`EXPLAIN ANALYZE` depending on your DB. Check tenant/owner indexes, grant lookups, scanned rows, nested loops, sorts, and join cardinalities.
4. **Optimize set-based:** replace per-object query loops with filtered queries or batch allowed-ID checks.
5. **Ensure semantic parity:** the same user, role, tenant, and ACL must yield identical outcomes in old and new versions; test deny and missing-ID cases too.
6. **Re-measure:** SQL counts, p50/p95/p99 latency, memory, DB CPU, rows read, connection-pool saturation, throughput, and payload size.
7. **Verify security:** no cross-tenant leaks, forged owners, expired grants, stale caches, or unauthorized total counts.
8. **Roll out carefully:** when changing major queries in production, monitor for regressions, plan stability, and prepare a rollback strategy.

### About indexes

For the demo SQL, indexes `documents(tenant_id, owner_name, id)` and `document_grants(grantee, permission, document_id)` can help. Yet good indexing depends on real data, selectivity, tenant sizes, and the query optimizer. `EXISTS` expresses semantics; it does not guarantee the DB picks the optimal plan by itself.

For permissions based on `group membership`, you can join/batch against group tables. If an ACL has deny-overrides-allow rules, the SQL query must faithfully reproduce precedence rather than simply using `EXISTS grant` as in the simplified owner/read case.

## 11. Security and consistency risks

### 11.1. Database filtering does not replace method protection

A controller or service may be invoked by jobs, other services, or message consumers. Even when the repository puts owner/tenant into the query, keep feature-level authority checks at the service boundary (`@PreAuthorize` or an appropriate `AuthorizationManager`). Likewise, **never** grant access solely because a client sent plausible ID/tenant values.

### 11.2. Reads and writes are two different problems

For read-only lists, returning visible documents from SQL is usually appropriate. For write operations, policy can change between calling `allowedIds()` and executing the update. That is **TOCTOU (time of check, time of use)**.

A write command may need permission predicates directly inside the `UPDATE`/`DELETE` statement, checking affected row counts, transactions, locking, or version columns. Never treat an `allowedIds` list cached minutes earlier as sufficient proof to update when policy may just have changed.

### 11.3. `@PostFilter` and sensitive data

When a method returns the full list and `@PostFilter` filters afterward, unauthorized records were already materialized **inside the server**. Even though the caller ultimately receives only permitted rows, transient data can still leak into debug logs, mis-configured serialization, or side processing if code is poorly structured. Querying only visible rows narrows the data handled in memory.

If an endpoint reveals data based on **field-level** permissions, row filtering alone is not enough. Build DTOs/redactions matching the policy, and never share cached responses across higher and lower privilege levels.

### 11.4. Evaluator errors and fail closed

If the database/ACL is temporarily unresponsive, never catch the exception and return `true` just to keep requests succeeding. Policy may return `false` for unsupported targets/permissions, while infrastructure errors should be safely logged/reported and translated into appropriate error responses; **never grant permission on a lookup failure**.

## 12. Common pitfalls table

| Symptom | Cause | Fix |
| --- | --- | --- |
| 100-item list triggers 101 SQL calls | `@PostFilter` invokes evaluator querying per item | Push predicates into SQL or batch allowed IDs |
| Larger pool still has high latency | Per-item round-trips unchanged | Reduce query count, inspect plans/rows |
| 20-item page shrinks to 3 after filtering | Pagination applied before authorization filtering | Filter permissions in SQL before paginating |
| `totalElements` leaks whole-tenant count | COUNT lacks the same permission predicates | Count using the visible predicate |
| T1 user sees T2 documents | Query checks only owner/grant or trusts client tenant | Enforce server-side tenant inside the SQL itself |
| Removing `@PostFilter` for speed leaks data | New query misses required permission predicates | Write parity contract tests and fail closed |
| Optimized query returns duplicate records | Joining multiple grants without `DISTINCT` or poor design | Use `EXISTS`/semi-joins when appropriate |
| Permission cache shared across users | Key contains only ID | Include principal/tenant/action/version and invalidation |
| Cold cache still causes N lookups | N distinct IDs miss cache | Use set-based SQL/batching instead of relying on cache |
| Wrong SQL count in parallel tests | Global counter or startup queries interfere | Trace per request/test, isolate workloads |
| `@PostFilter` never runs | Self-invocation, `new` instance, missing `@EnableMethodSecurity` | Call Spring proxy, write integration tests |
| Permission revoked yet write still runs | Stale check timing or stale ACL cache | Re-check / conditional UPDATE inside transaction |
| `IN` query too long or slow | ID batch exceeds DB parameter limit | Chunk batches, use temp tables or table-valued parameters |
| Complex ACL permissions evaluate wrongly | `EXISTS` query misses deny/inheritance/expiry | Specify policy fully, test thoroughly, or use policy service / batch PDP |

## 13. Self-check exercises

1. **There are 500 documents; `listAll()` runs one SQL query and the evaluator runs one SQL query per item. What is the total SQL count?**  
   Roughly `1 + 500 = 501` for that simple pattern, excluding any other queries.

2. **Why can `@PostFilter` break pagination?**  
   Because data is `LIMIT`ed before authorization filtering, dropping items and potentially skewing total statistics.

3. **If you use `EXISTS` in SQL, does authorization become zero-cost automatically?**  
   No. The DB still evaluates predicates; the benefit is set-based processing and fewer round-trips, so inspect the query plan.

4. **Why shouldn't you use `Map<DocumentId, Boolean>` as a shared permission cache?**  
   Because decisions also depend on user, tenant, permission, and current state/grants; an underscoped cache leaks permissions.

5. **Does a list of 1,000 completely distinct IDs improve much with per-request memoization?**  
   Not significantly when each ID appears only once; a batch query is usually much better.

6. **If the full policy cannot be expressed in SQL, what approach fits?**  
   A batch authorization API accepting candidate IDs and trusted principal/tenant/action, returning allowed IDs to filter with identical semantics.

7. **Does `@PreAuthorize("hasAuthority('document:read')")` alone ensure every record belongs to the viewer?**  
   No. It checks only the coarse capability; you still need tenant/owner/grant/ACL enforcement per resource.

8. **Why isn't `@PreFilter` automatically suitable for every batch update?**  
   Because disallowed elements can be silently dropped, producing a partial update instead of all-or-nothing semantics.

9. **Why is benchmarking runtime once insufficient?**  
   Caches, JIT, connection pools, warm-up, data distribution, and query planners all skew latency; measure query counts, plans, load tests, and correctness.

10. **Does optimizing from 7 queries down to 1 prove the system is secure?**  
    Not yet. Test cross-user/tenant access, missing permissions, forged principals, revocations, caching, pagination, and TOCTOU.

## 14. Summary and references

**Operating rules:**

- Per-item `PermissionEvaluator` checks can create N lookups, especially with `@PostFilter`/`@PreFilter` and service loops.
- For large lists, prefer **set-based SQL permission filtering** or **batch authorization**; you do not have to discard all Method Security.
- Coarse capabilities and per-record permissions are two distinct layers. Derive user/tenant from trusted identity; verify owner/grants against server-side data.
- Fast code with wrong permissions is a failure. Always verify parity between legacy and optimized paths for both allow and deny.
- Apply pagination and COUNT with the exact same permission predicates; for writes, handle concurrency and permission changes at update time.
- Monitor N+1 via query counts/tracing, never relying solely on latency or response item counts.

Official documentation:

1. [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PostFilter`, `filterObject`, `@PreAuthorize`, and the interceptor/proxy model.
2. [Spring Security — PermissionEvaluator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html): both overloads, `Authentication`, object/ID, and permission parameters.
3. [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser`.
4. [Spring Framework — Data Access with JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, SQL parameters, and row mapping.
5. [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): datasources, H2, and SQL schema/data initialization.
6. [Spring Framework — AOP Proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy boundaries and self-invocation.

**Key takeaway:** calling `hasPermission` per element is not inherently wrong, yet when each check queries the DB, an N-element list easily causes N+1 queries. The durable fix is **pushing permissions into data queries or checking permissions in batches**, preserving user/tenant/ACL constraints and testing both **permitted results** and **query counts**.
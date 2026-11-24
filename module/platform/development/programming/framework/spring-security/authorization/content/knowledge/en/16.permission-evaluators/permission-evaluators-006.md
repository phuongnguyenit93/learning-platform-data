# Separating Permission Checks from Resource Loading and Updating with PermissionEvaluator

## 1. The problem: one method carrying three responsibilities

Suppose a document management system needs to view and edit a document belonging to a tenant. A common way people write this:

```java
public void updateDocument(long id, String newContent) {
    Document document = repository.findById(id).orElseThrow();
    if (!currentUserCanEdit(document)) {
        throw new AccessDeniedException("Denied");
    }
    document.setContent(newContent);
    repository.save(document);
}
```

This is merely an illustrative snippet; the types and dependencies are application-defined. This code might work in one specific app, yet it tangles **data loading**, **permission decision**, and **data mutation**. If multiple services share the same rules, logic gets duplicated; if checks happen only after loading sensitive content, the app may already have done unnecessary work or accidentally processed/logged data before authorization.

Spring Security lets you separate these three responsibilities:

1. **Authorization:** answers “does the caller have *read/write* permission on this resource ID?”. `PermissionEvaluator` enables the `hasPermission(...)` expression to return a boolean decision.
2. **Resource loading:** the repository/service fetches the document and necessary business data.
3. **Mutation:** the service applies business rules, transactions, version checks, and persists changes.

A subtle distinction matters: to decide object-level permission, the evaluator **may have to read a minimal amount of data from a trusted source**, such as owner/tenant/state/ACL. “Separating from resource loading” **does not mean “permission checks cannot read the database”**. The true meaning is **do not load full unnecessary content, create no side effects, and never treat the evaluator as the place for business reads/writes**.

Target example:

```text
Caller
  |
  v
Spring AOP proxy / @PreAuthorize
  |
  v
PermissionEvaluator.hasPermission(auth, documentId, "Document", "read")
  |       \
  |        -> query permission metadata: tenant, owner, status
  v
GRANT or DENY
  |
  +-- DENY  -> service method is not invoked
  |
  +-- GRANT -> DocumentService.read(id)
                  |
                  v
             Repository loads content
                  |
                  v
             Re-check sensitive data if needed
                  |
                  v
             Return permitted data
```

For **write** operations, a pre-method check is usually a **necessary condition, not a sufficient one**. If owner/tenant/state changes between check and update, additional consistency enforcement inside the transaction is required.

## 2. Role of PermissionEvaluator in Spring Security

`PermissionEvaluator` is the strategy for evaluating permissions on domain objects; Spring Security uses it when method security expressions invoke `hasPermission`. Its two overloads:

```java
boolean hasPermission(
        Authentication authentication,
        Object targetDomainObject,
        Object permission);

boolean hasPermission(
        Authentication authentication,
        Serializable targetId,
        String targetType,
        Object permission);
```

Parameters:

| Parameter | Meaning |
| --- | --- |
| `authentication` | Identity and authorities of the caller verified by the framework |
| `targetDomainObject` | Domain object **already in hand** for evaluation |
| `targetId` | Serializable ID, typically `Long` or `UUID` |
| `targetType` | Resource type name per application contract, e.g., `"Document"` |
| `permission` | Action to check, e.g., `"read"`, `"write"` |
| Return value | `true` to allow, `false` to deny |

The official contract permits `targetDomainObject == null` in the first overload; implementations should return `false` for null.

Two distinct expressions:

```java
// Argument #p0 is long/Long: use the ID + resource type overload.
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public String read(long documentId) { /* ... */ }

// Argument #p0 is a Document object supplied by the caller.
@PreAuthorize("hasPermission(#p0, 'read')")
public void share(Document document) { /* ... */ }
```

**Common pitfall:** `hasPermission(#p0, 'read')` when `#p0` is a `Long` invokes the **Object** overload; it does not magically know that it is a document ID. If your evaluator only handles `Document` in the object overload, that expression will be denied. Deliberately choose the three-argument ID form for services taking an ID.

`PermissionEvaluator` is only a hook. Spring does not magically know your `documents` table, ACL tables, or owners. Developers must register the evaluator and implement the policy. Otherwise, default configuration will not provide the intended business-data permission decisions.

### Distinguishing three layers

| Component | Should do | Should not do |
| --- | --- | --- |
| `PermissionEvaluator` | Canonicalize action/type/ID, invoke policy, and return boolean | Call `save`, delete records, or publish business events |
| `DocumentAccessPolicy` | Express pure rules: action, tenant, owner, state, authorities | Build controller responses, open HTTP sessions, mutate resources |
| `DocumentService` + repository | Load data, validate current constraints, write in transaction, handle errors | Blindly trust stale pre-check results, skip transactions |

The policy can be reused by both the evaluator and the service. That way you separate **where permissions are decided** from **where data is fetched and mutated**, without duplicating owner/tenant rules.

## 3. Why not load and update resources directly inside the evaluator?

A flawed implementation:

```java
@Override
public boolean hasPermission(
        Authentication auth,
        Serializable targetId,
        String targetType,
        Object action) {

    Document doc = repository.findById((Long) targetId).orElseThrow();

    if ("write".equals(action) && isOwner(auth, doc)) {
        doc.setContent("updated"); // Wrong: authorization performed a mutation.
        repository.save(doc);
        return true;
    }
    return false;
}
```

This is a **production anti-pattern**. Problems:

- An expression merely asking “is this allowed?” **mutates data**, violating authorization's single responsibility.
- The evaluator may be invoked multiple times per request or by other advice; mutations may run repeatedly, breaking idempotency.
- The transaction when the evaluator runs might **not** be the intended business transaction. By default `@PreAuthorize` evaluates before entering the target method; never assume `@Transactional` on the target method is active yet.
- If the target method is blocked by another check or fails later, data changed by the evaluator may remain unintentionally mutated.
- Caller permissions may get conflated with client-supplied data; with the object overload, the passed object may not yet be the authoritative record from the database.
- Testing policy becomes painful because simply calling `hasPermission` triggers side effects.

**Principle:** permission checks should have **no business side effects** and should separate minimal permission metadata queries from content reads/updates. Reading metadata is valid, as long as query counts are measured and consistency is maintained.

## 4. Recommended separation pattern

### Step A: Define policy over minimal facts

For example, allow `read` or `write` when:

```text
authenticated
AND not anonymous
AND action is supported
AND holds matching authority DOC_READ or DOC_WRITE
AND belongs to the document's exact tenant
AND owner = Authentication.name
AND status = ACTIVE
```

A real application may add sharing permissions, groups, ACLs, or audited admin exceptions. The `tenant`, `owner`, and `status` fields must come from trusted server data, never from caller-declared headers/bodies.

### Step B: Evaluator fetches only AccessFacts

```text
PermissionEvaluator
   |
   +--> DocumentRepository.findAccessFacts(id)
              |
              +--> SELECT tenant, owner_name, state
                   FROM documents WHERE id = ?
   |
   +--> DocumentAccessPolicy.can(auth, facts, "write")
   |
   +--> boolean
```

There is no need to SELECT `body`, attachments, blobs, or document history, or load an entire object graph just to make an authorization decision.

### Step C: Service loads/updates within proper boundaries

- For `read`: after the pre-check, the service fetches content. If permissions/data may change, re-check facts on the freshly loaded data before returning; or use tenant/owner-conditioned queries.
- For `write`: after the pre-check, the service begins a transaction, acquires a locked record or checks version/conditional update, **re-checks** policy on current facts, and only then mutates.
- Authorization failures must block business execution; validation errors and version conflicts need explicit error contracts (e.g., 400/409/422 depending on API), rather than arbitrarily treating every error as 403.

## 5. Two check forms: ID and object

### Checking by ID before loading content

```java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public DocumentView read(long id) {
    Document document = repository.findById(id).orElseThrow();
    return toView(document);
}
```

This is an **integration snippet**; `DocumentView`, `toView`, and repository belong to the project. Benefit: blocks unauthorized callers **before** the method loads content. Cost: the evaluator may read metadata once and the service reads the resource a second time. You can optimize with projection queries, joins/conditional access, or safely scoped caches, but never “optimize” by turning the evaluator into a data writer.

### Checking on a loaded object

```java
@PostAuthorize("returnObject == null or hasPermission(returnObject, 'read')")
public Document get(long id) {
    return repository.findById(id).orElse(null);
}
```

This illustrates the object overload: the method loads the document first, and authorization evaluates once `returnObject` is available. This can fit some read-only APIs, but **does not prevent loading costs or side effects prior to the check**. For highly sensitive documents, use checks **before** the method plus data-layer constraints in queries/services; never use `@PostAuthorize` as the sole protection for updates/deletes.

### Client-supplied objects are not trusted permission sources

```java
@PreAuthorize("hasPermission(#request.document, 'write')")
public void update(UpdateRequest request) {
    // ...
}
```

If `request.document.owner` comes from client JSON, comparing owner inside the evaluator **does not prove** the caller actually owns the document in the database. Use only trusted fields or load canonical metadata on the server. `targetType` must also be allow-listed: never let a client-controlled string arbitrarily pick repositories or resource types.

## 6. Clean Java 17 responsibility design

In this section, we define a minimal model used by the complete Spring Boot implementation in section 8.

```java
record AccessFacts(String tenant, String owner, String state) {}

record Document(
        long id, String tenant, String owner,
        String state, String body) {

    AccessFacts facts() {
        return new AccessFacts(tenant, owner, state);
    }
}
```

`AccessFacts` carries no sensitive content (`body`). `Document` carries the content because the service needs it. `DocumentAccessPolicy` evaluates an `AccessFacts`. With Java 17, `record` is shallowly immutable via final fields; it suits permission snapshots and reduces accidental mutation risks.

**Important:** an immutable snapshot does not make permissions immutable in the database. If owner/state can change between check and write, locks, versions, or conditional updates are still needed.

## 7. Wiring PermissionEvaluator into MethodSecurityExpressionHandler

For Spring Security 6.x, one configuration approach is declaring a `MethodSecurityExpressionHandler` bean and setting the evaluator:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            DocumentRepository repository,
            DocumentAccessPolicy policy) {

        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();

        handler.setPermissionEvaluator(
                new DocumentPermissionEvaluator(repository, policy));

        return handler;
    }
}
```

This is an **integration snippet**; `DocumentRepository`, `DocumentAccessPolicy`, and `DocumentPermissionEvaluator` belong to the application. `@Bean static` is recommended by Spring Security docs to publish the handler before the framework initializes method security configuration. Do not create an extra competing handler bean if the application already has a custom handler configuring `RoleHierarchy` or other options: **configure the evaluator on that same handler**.

Key imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

Do not confuse this with HTTP's `SecurityFilterChain`. `@EnableMethodSecurity` applies to method calls through Spring AOP proxies. If callers instantiate `new Service()` directly or make internal `this.securedMethod()` calls in proxy mode, advice may be bypassed. Test through real Spring beans.

## 8. Complete example: Spring Boot + H2 + PermissionEvaluator

The example below uses **Java 17** and **Spring Boot 3.5.16 (Spring Security 6.x)** for stable, reproducible APIs. This version is available on Maven Central, though the Spring Boot 3.5.x line has reached end of OSS support; production projects should pick a currently supported line and verify APIs when upgrading.

The demo uses an in-memory H2 database. We **do not read `body` in the evaluator**; the evaluator only queries `tenant`, `owner_name`, and `state`. The service reads content after being permitted. For writes, the service uses `SELECT ... FOR UPDATE` and re-checks policy inside the transaction before updating.

Simple demo policy:

- `DOC_READ` is required for `read`; `DOC_WRITE` is required for `write`.
- The caller must hold an authority like `TENANT_A` or `TENANT_B` matching the document's tenant.
- `Authentication.name` equals owner, and state equals `ACTIVE`.
- Any other action or resource type: **deny**.
- H2 data, usernames, and authorities are simulated; this is not a production authentication system.

### 8.1. Layout

```text
permission-separation-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   └── PermissionSeparationApplication.java
    │   └── resources/
    │       ├── schema.sql
    │       └── data.sql
    └── test/
        └── java/demo/
            └── PermissionSeparationTest.java
```

To keep the example concise and avoid import errors across files, package-private classes are placed alongside the public application class in **one Java file**. In real projects, split them into separate files by responsibility.

### 8.2. `pom.xml`

```xml
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
  <artifactId>permission-separation-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
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

### 8.3. `src/main/resources/schema.sql`

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    tenant VARCHAR(32) NOT NULL,
    owner_name VARCHAR(64) NOT NULL,
    state VARCHAR(16) NOT NULL,
    body VARCHAR(500) NOT NULL
);
```

### 8.4. `src/main/resources/data.sql`

```sql
INSERT INTO documents (id, tenant, owner_name, state, body)
VALUES (1, 'A', 'alice', 'ACTIVE', 'alpha');

INSERT INTO documents (id, tenant, owner_name, state, body)
VALUES (2, 'B', 'bob', 'ACTIVE', 'beta');

INSERT INTO documents (id, tenant, owner_name, state, body)
VALUES (3, 'A', 'alice', 'LOCKED', 'gamma');
```

Document 1 belongs to alice, document 2 belongs to bob/tenant B, and document 3 belongs to alice but is locked. This is server data, not fields chosen by the caller.

### 8.5. `src/main/java/demo/PermissionSeparationApplication.java`

```java
package demo;

import java.io.Serializable;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@SpringBootApplication
@EnableMethodSecurity
public class PermissionSeparationApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(PermissionSeparationApplication.class);

        app.setDefaultProperties(Map.of(
                "spring.main.web-application-type", "none",
                "spring.main.banner-mode", "off",
                "logging.level.root", "OFF"));

        try (ConfigurableApplicationContext ignored = app.run(args)) {
            // CommandLineRunner already executed during SpringApplication.run.
        }
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            DocumentRepository repository, DocumentAccessPolicy policy) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(
                new DocumentPermissionEvaluator(repository, policy));
        return handler;
    }

    @Bean
    CommandLineRunner showSeparation(DocumentService service) {
        return args -> {
            try {
                authenticate("alice", "TENANT_A", "DOC_READ", "DOC_WRITE");

                printRead("alice read 1", service, 1L);
                printRead("alice read 2", service, 2L);

                printUpdate("alice update 1", service, 1L, "alpha-v2");
                printRead("alice read 1 after", service, 1L);
                printUpdate("alice update 3", service, 3L, "bad");

                authenticate("bob", "TENANT_B", "DOC_READ", "DOC_WRITE");
                printRead("bob read 2", service, 2L);
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void printRead(String label, DocumentService service, long id) {
        try {
            System.out.println(label + ": " + service.read(id));
        } catch (AccessDeniedException denied) {
            System.out.println(label + ": DENIED");
        }
    }

    private static void printUpdate(
            String label, DocumentService service, long id, String content) {
        try {
            service.update(id, content);
            System.out.println(label + ": OK");
        } catch (AccessDeniedException denied) {
            System.out.println(label + ": DENIED");
        }
    }

    private static void authenticate(String username, String... authorities) {
        List<SimpleGrantedAuthority> granted = Arrays.stream(authorities)
                .map(SimpleGrantedAuthority::new)
                .toList();

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                        username, "demo-only", granted));
        SecurityContextHolder.setContext(context);
    }
}

// Snapshot containing only the fields needed to decide permissions.
record AccessFacts(String tenant, String owner, String state) {}

record Document(
        long id, String tenant, String owner, String state, String body) {
    AccessFacts facts() {
        return new AccessFacts(tenant, owner, state);
    }
}

@Repository
class DocumentRepository {

    private final JdbcTemplate jdbc;

    DocumentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Evaluator uses metadata query, WITHOUT selecting body.
    Optional<AccessFacts> findAccessFacts(long id) {
        List<AccessFacts> rows = jdbc.query(
                "SELECT tenant, owner_name, state "
                        + "FROM documents WHERE id = ?",
                (rs, rowNumber) -> new AccessFacts(
                        rs.getString("tenant"),
                        rs.getString("owner_name"),
                        rs.getString("state")),
                id);
        return rows.stream().findFirst();
    }

    // Service reads body after pre-authorization grants access.
    Optional<Document> findById(long id) {
        return findOne(
                "SELECT id, tenant, owner_name, state, body "
                        + "FROM documents WHERE id = ?",
                id);
    }

    // Locks the record being modified until the end of the transaction.
    Optional<Document> findByIdForUpdate(long id) {
        return findOne(
                "SELECT id, tenant, owner_name, state, body "
                        + "FROM documents WHERE id = ? FOR UPDATE",
                id);
    }

    private Optional<Document> findOne(String sql, long id) {
        List<Document> rows = jdbc.query(
                sql,
                (rs, rowNumber) -> new Document(
                        rs.getLong("id"),
                        rs.getString("tenant"),
                        rs.getString("owner_name"),
                        rs.getString("state"),
                        rs.getString("body")),
                id);
        return rows.stream().findFirst();
    }

    void updateBody(long id, String body) {
        int count = jdbc.update(
                "UPDATE documents SET body = ? WHERE id = ?", body, id);
        if (count != 1) {
            throw new IllegalStateException("Unexpected document update count");
        }
    }
}

@Component
class DocumentAccessPolicy {

    boolean can(Authentication auth, AccessFacts facts, String action) {
        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken
                || facts == null) {
            return false;
        }

        String requiredAuthority = switch (action) {
            case "read" -> "DOC_READ";
            case "write" -> "DOC_WRITE";
            default -> null;
        };

        if (requiredAuthority == null || !"ACTIVE".equals(facts.state())) {
            return false;
        }

        return facts.owner().equals(auth.getName())
                && hasAuthority(auth, "TENANT_" + facts.tenant())
                && hasAuthority(auth, requiredAuthority);
    }

    private boolean hasAuthority(Authentication auth, String name) {
        return auth.getAuthorities().stream()
                .anyMatch(a -> name.equals(a.getAuthority()));
    }
}

final class DocumentPermissionEvaluator implements PermissionEvaluator {

    private final DocumentRepository repository;
    private final DocumentAccessPolicy policy;

    DocumentPermissionEvaluator(
            DocumentRepository repository, DocumentAccessPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    @Override
    public boolean hasPermission(
            Authentication auth, Object target, Object permission) {
        if (!(target instanceof Document document)
                || !(permission instanceof String action)) {
            return false;
        }
        return policy.can(auth, document.facts(), action);
    }

    @Override
    public boolean hasPermission(
            Authentication auth, Serializable targetId,
            String targetType, Object permission) {
        if (!"Document".equals(targetType)
                || !(targetId instanceof Long id)
                || id <= 0
                || !(permission instanceof String action)) {
            return false;
        }

        return repository.findAccessFacts(id)
                .map(facts -> policy.can(auth, facts, action))
                .orElse(false);
    }
}

@Service
class DocumentService {

    private final DocumentRepository repository;
    private final DocumentAccessPolicy policy;

    DocumentService(DocumentRepository repository, DocumentAccessPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    @Transactional(readOnly = true)
    @PreAuthorize("hasPermission(#p0, 'Document', 'read')")
    public String read(long id) {
        // Method is entered only after the evaluator allows this ID.
        Document document = repository.findById(id)
                .orElseThrow(() -> new AccessDeniedException("Denied"));

        // Re-check on the actual loaded record in case metadata changed.
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        if (!policy.can(auth, document.facts(), "read")) {
            throw new AccessDeniedException("Denied");
        }

        return document.body();
    }

    @Transactional
    @PreAuthorize("hasPermission(#p0, 'Document', 'write')")
    public void update(long id, String newBody) {
        if (newBody == null || newBody.isBlank()) {
            throw new IllegalArgumentException("Body must not be blank");
        }

        // Lock the record inside the transaction before updating.
        Document current = repository.findByIdForUpdate(id)
                .orElseThrow(() -> new AccessDeniedException("Denied"));

        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        if (!policy.can(auth, current.facts(), "write")) {
            throw new AccessDeniedException("Denied");
        }

        // Perform the write only after re-checking.
        repository.updateBody(id, newBody);
    }
}
```

Each component has a single job:

1. `DocumentRepository.findAccessFacts` selects only the three fields needed for authorization.
2. `DocumentAccessPolicy.can` computes allow/deny from facts and `Authentication`, without modifying the database.
3. `DocumentPermissionEvaluator` checks only type/ID/action, invokes the metadata query and policy, and returns boolean.
4. `DocumentService.read` runs after `@PreAuthorize`, loads the body, and re-checks facts on the freshly loaded record before returning it.
5. `DocumentService.update` opens a transaction, locks the record with `FOR UPDATE`, re-checks permission on the latest record, and only then runs UPDATE.
6. `@Bean static MethodSecurityExpressionHandler` wires the evaluator into `hasPermission` expressions.

**Demo limitations:** this assumes a relational database supporting row locking and a properly working transaction manager. H2 is great for illustration; production requires verifying transaction isolation/locking and behavior with the real database. `Authentication` in the demo is manually set via `SecurityContextHolder`; production must obtain it from a configured authentication mechanism and never trust client-asserted usernames/tenants.

### 8.6. Running the application

From the directory containing `pom.xml`, with Java 17+ and Maven installed:

```bash
mvn -q clean package
java -jar target/permission-separation-demo-1.0.0.jar
```

Lines printed by the application:

```text
alice read 1: alpha
alice read 2: DENIED
alice update 1: OK
alice read 1 after: alpha-v2
alice update 3: DENIED
bob read 2: beta
```

Why?

- **Alice reads 1:** the evaluator queries access facts and grants; the service loads body `alpha`, re-checks, and returns it.
- **Alice reads 2:** owner and tenant do not match; the evaluator returns false, and the method never loads `beta`.
- **Alice updates 1:** the evaluator permits; the transaction acquires the lock, re-checks current facts, and writes `alpha-v2`.
- **Alice reads 1 again:** the new body is returned.
- **Alice updates 3:** state `LOCKED` causes the evaluator to deny; no update command runs.
- **Bob reads 2:** Bob holds the tenant B authority and read permission, and owns document 2.

This is **stdout produced by the designed demo code**, not output from an execution performed in this environment. Running via Maven may also print framework logs depending on configuration/JVM.

## 9. Testing: the evaluator performs no business operations

Beyond allow/deny tests, you must test **responsibility boundaries**.

### 9.1. Integration tests with Spring proxy and H2

File `src/test/java/demo/PermissionSeparationTest.java`:

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class PermissionSeparationTest {

    @Autowired
    DocumentService service;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void restoreFixture() {
        jdbc.update("UPDATE documents SET body = 'alpha' WHERE id = 1");
    }

    @Test
    @WithMockUser(username = "alice",
            authorities = {"TENANT_A", "DOC_READ"})
    void readAllowedDocument() {
        assertEquals("alpha", service.read(1L));
    }

    @Test
    @WithMockUser(username = "alice",
            authorities = {"TENANT_A", "DOC_READ"})
    void cannotReadDocumentInAnotherTenant() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(2L));
    }

    @Test
    @WithMockUser(username = "alice",
            authorities = {"TENANT_A", "DOC_WRITE"})
    void writerUpdatesAfterRecheckingInTransaction() {
        service.update(1L, "alpha-updated");
        assertEquals("alpha-updated", jdbc.queryForObject(
                "SELECT body FROM documents WHERE id = 1",
                String.class));
    }

    @Test
    @WithMockUser(username = "alice",
            authorities = {"TENANT_A", "DOC_READ"})
    void deniedWriteDoesNotMutateResource() {
        assertThrows(AccessDeniedException.class,
                () -> service.update(1L, "unauthorized"));

        assertEquals("alpha", jdbc.queryForObject(
                "SELECT body FROM documents WHERE id = 1",
                String.class));
    }

    @Test
    @WithMockUser(username = "alice",
            authorities = {"TENANT_A", "DOC_WRITE"})
    void lockedResourceCannotBeUpdated() {
        assertThrows(AccessDeniedException.class,
                () -> service.update(3L, "bad"));

        assertEquals("gamma", jdbc.queryForObject(
                "SELECT body FROM documents WHERE id = 3",
                String.class));
    }
}
```

Run:

```bash
mvn -q test
```

These tests prove calls go through the Spring-managed `DocumentService` so `@PreAuthorize` executes; unauthorized callers are denied and the body remains unchanged. Because the tests read the DB directly to assert postconditions, they are not confused with tests that only assert HTTP status codes.

Note that the demo's runner also executes when the `@SpringBootTest` context starts and updates document 1; `@BeforeEach` resets the body for each test. That is solely for the example, not how test fixtures should be organized in large systems.

### 9.2. Unit testing the evaluator and policy

With a mocked repository, verify:

- `hasPermission(auth, null, "read")` → false.
- `hasPermission(auth, Long.valueOf(1), "Document", "read")` → true when facts are valid.
- Wrong `targetType` or unsupported `"delete"` action → false, without calling update.
- Negative ID, overflow from another input parser, or nonexistent ID → false.
- Anonymous / unauthenticated principal / missing required authority → false.
- Facts in another tenant, different owner, or `LOCKED` state → false.
- Repository calls only `findAccessFacts`, **never** `updateBody` or any business mutation.
- Exceptions from a failing DB/PDP do not turn into `true`; fail-closed behavior or operational error handling is explicitly defined.

Mockito helps assert boundaries, for example:

```java
verify(repository).findAccessFacts(1L);
verify(repository, never()).updateBody(anyLong(), anyString());
```

This is an **integration assertion snippet**, requiring imports for `org.mockito.Mockito.verify`, `never`, `anyLong`, `anyString` and proper mock setup. It is not a standalone file.

### 9.3. Testing race conditions

A more important problem than static allow/deny is:

```text
T1: @PreAuthorize -> evaluator sees owner = alice -> GRANT
T2: an administrator transfers owner to bob
T3: alice's service begins the update
```

If the service **neither re-checks inside the transaction nor uses a conditional update**, the T3 statement can modify a document Alice no longer has permission to touch. Real concurrency integration tests are needed on the production database or a DB matching its locking behavior: use latches to coordinate two transactions and verify the writer fails when permission was revoked prior to lock/re-check.

The demo uses `SELECT ... FOR UPDATE` to hold the snapshot after locking; concrete concurrency tests require independent threads and transactions. Do not claim the demo automatically proves correctness under every isolation level or database engine.

## 10. Why can pre-check and transaction occur at two different times?

With `@PreAuthorize`, the framework must decide whether to let the call proceed. By default in many Spring Security/Spring Transaction configurations, pre-authorization advice runs **outside or before** the target method's transaction; however, exact ordering depends on advisor order.

```text
@PreAuthorize on proxy
       |
       v
PermissionEvaluator queries facts (T1)
       |
       v
Transaction advice / @Transactional
       |
       v
SELECT ... FOR UPDATE (T2)
       |
       v
Re-check on locked record
       |
       v
UPDATE -> COMMIT or ROLLBACK
```

Therefore:

- `@PreAuthorize` is a good “early gate,” reducing unnecessary content loading/business method entry for unauthorized callers.
- `@Transactional` is a transaction management mechanism, **not an automatic cure for all TOCTOU bugs**.
- For sensitive mutations, re-check permissions on current state combined with locking or optimistic versioning/conditional writes.
- If a transaction fails to open due to self-invocation, `new Service()`, or a missing transaction manager, consistency protection may fail silently; integration tests must go through the Spring proxy.

### Fewer-query option: conditional update

Another option for applications that do not need to load the full document before writing is **a conditional UPDATE**:

```sql
UPDATE documents
SET body = ?
WHERE id = ?
  AND tenant = ?
  AND owner_name = ?
  AND state = 'ACTIVE';
```

The service counts the operation as “successful” only when the updated row count equals 1. With `tenant` and `owner` taken from a trusted `Authentication` source, the database evaluates those conditions atomically in the UPDATE statement, avoiding a gap between SELECT and UPDATE for those predicates.

However, **never take tenant/owner from client headers**, and SQL still does not replace checking the `DOC_WRITE` authority or other business rules. When business logic spans multiple tables or side effects, use appropriate transactions, locking, and versioning.

## 11. Performance: separating concerns while avoiding N+1 queries

A request reading 100 documents that calls `hasPermission(id,...)` 100 times can trigger 100 metadata queries, followed by the service loading 100 documents: that is **N+1** or more queries than necessary.

How to address it:

1. For lists, push tenant/owner/ACL filters into parameterized repository queries and return only permitted records.
2. If per-document permissions are needed, consider batch `findAccessFactsByIds` or a batch permission API; do not assume `PermissionEvaluator` has a built-in batch overload.
3. Bound collection sizes when using `@PostFilter`/`@PreFilter`; filtering in memory after fetching the entire DB is rarely appropriate.
4. Cache decisions by `subject + tenant + resource + action + policyVersion` only when the permission-update contract allows it. Require explicit TTL/invalidation; caching allow for too long delays revocation enforcement.
5. If a trusted canonical domain object is already in hand within the same transaction, you can use the object overload instead of issuing a second facts query—just never rely on a client-forged object.
6. Avoid reading blobs/attachments/unrelated fields inside the evaluator just to check owner or tenant.

**Never optimize by completely removing the re-check at a racy write boundary**, unless the persistence operation already enforces the policy another way (atomic conditional update, row-level security, version check...).

## 12. Tenant boundaries and object permissions

In multi-tenant applications, resource ID is only part of the identity. Someone holding `DOC_READ` must not implicitly read documents in another tenant.

A safe policy can look like:

```text
allow(user, document, "read") =
    document.exists
    AND user.authenticated
    AND user.has(DOC_READ)
    AND user.tenant ∈ document.allowedTenants
    AND (user.isOwner OR user.hasShareGrant)
    AND document.state ∈ readableStates
```

`PermissionEvaluator` only uses authorities/claims verified by the authentication infrastructure and authoritative server-side data. With JWTs, the `tenant` claim must have its signature/audience/issuer validated and mapped properly; never trust a raw base64-decoded payload or an `X-Tenant` header without verification.

Enforce both **vertical** access control (admin/editor/viewer) and **horizontal** access control (user A cannot read B's documents). Horizontal checks are easily overlooked when tests cover only one happy path with the right role.

Avoid making the API overly explicit about “ID exists but you lack permission” versus “ID does not exist” when that helps attackers enumerate resources. Some systems return `404` for both, but HTTP exception handling must be consistent and follow the contract rather than defaulting every request to 403.

## 13. Common mistakes and fixes

**Mistake 1 — Evaluator calling `repository.save(...)`.** Move mutations into a transactional service; the evaluator should only return allow/deny.

**Mistake 2 — Evaluator loading full body, attachments, and lazy relations.** Use an access projection `tenant/owner/state` whenever possible; reduce I/O and avoid touching unnecessary data before authorization.

**Mistake 3 — Only `@PostAuthorize` on an update method.** Side effects have already run before the check. Place pre-authorization at entry and guard state prior to writing.

**Mistake 4 — Thinking “since `@PreAuthorize` is present, no re-check is needed.”** Owner/tenant/state can change between check and write; use locks, versions, conditional updates, and consistency contracts.

**Mistake 5 — Checking owner from a client DTO.** Clients can spoof it; read owner from the server-side repository.

**Mistake 6 — Passing an ID to the object overload.** `hasPermission(#p0,'write')` when `#p0` is a Long calls the object overload; if the evaluator only handles `Document` objects, it will wrongly deny. Use `hasPermission(#p0,'Document','write')`.

**Mistake 7 — Implementing only one overload and letting the other return true.** An unsupported overload must return `false`, never grant. Test null targets and unknown types/actions.

**Mistake 8 — Forgetting to register the evaluator on MethodSecurityExpressionHandler.** Calling `hasPermission` will not automatically pick up your custom class if the handler uses another evaluator. Configure the bean early and test through a real method proxy.

**Mistake 9 — Unit-testing only with `new DocumentService(...)`.** Calling the plain Java object directly bypasses `@PreAuthorize`/`@Transactional` in proxy mode. Use `@SpringBootTest` and injected beans.

**Mistake 10 — Mixing authorization errors with business errors.** Editing an archived document might be a `409` business conflict or a `403` permission error depending on contract; not every state condition has to be an authorization error.

**Mistake 11 — Reading `SecurityContextHolder` from an async thread without propagating context.** Security is usually thread-bound; async code needs proper propagation. Never assume an Authentication on the main thread automatically exists on worker threads.

**Mistake 12 — Building a permission cache without distinguishing tenant/action.** A cache key of just `userId+documentId` can let `read` satisfy `write` or let an old tenant's grant apply to a new tenant. Include all policy keys, versioning, and invalidation.

**Mistake 13 — Catching `AccessDeniedException` and continuing to write.** In write services, denial must prevent mutation; if changes occurred before the exception, ensure the transaction rolls back properly. Never swallow the exception and report success.

**Mistake 14 — Ignoring database errors when the evaluator reads facts.** Never turn timeouts/exceptions into grants; define fail-closed behavior and API system-error mapping, monitor p95/p99 latency, and use retries/circuit-breakers for remote PDPs.

## 14. Comparing implementation patterns

| Pattern | Pros | Limitations / conditions |
| --- | --- | --- |
| `@PreAuthorize("hasAuthority('DOC_READ')")` | Very simple, fast | Knows nothing about per-resource owner/tenant |
| `@PreAuthorize("hasPermission(#p0,'Document','read')")` | Early gate by ID, reusable evaluator | May need metadata query; requires registering evaluator |
| `@PreAuthorize("@access.canRead(authentication,#p0)")` | Simple Java policy, no PermissionEvaluator needed | Does not use standard `hasPermission` vocabulary |
| `@PostAuthorize("hasPermission(returnObject,'read')")` | Uses already-loaded object, concise | Method/load already ran; unsuitable for guarding side effects |
| `Repository.findByIdAndTenantAndOwner(...)` | Enforces authorization in data query, reduces races and query count | Must guard every query path; complex policies may be hard to express |
| `UPDATE ... WHERE owner=? AND tenant=?` | Atomic check and write for those SQL predicates | Still must check authorities, row count, and transaction for related work |
| `@Transactional` + lock + re-check | Evaluates current policy right before write and reduces TOCTOU | Costs queries/locks; requires understanding DB isolation/deadlocks |
| Database RLS | Defense in depth at the storage layer | DB-dependent and needs accurate identity mapping; does not replace all app authorization |

Choose a pattern based on data requirements and your threat model, not because one annotation sounds “stronger” than another. In many applications, you can combine a **pre-check via evaluator** with a **conditional update** or **lock + re-check**.

## 15. Additional scenarios to consider

### 15.1. Bulk updates

Suppose a client sends IDs `[1, 2, 3]` for a batch update. If you merely filter out permitted IDs and write the rest, the API may **partially succeed** even when the user expected an atomic batch. Before implementing bulk mutations, pick an explicit contract:

- **All-or-nothing:** verify all IDs and permissions, then write inside a transaction; if any ID is denied, roll back the entire batch.
- **Partial success:** explicitly return per-ID success/failure instead of claiming full success.
- Maintain appropriate idempotency, retry, and audit semantics for batches.
- For large volumes, use batch queries/conditional updates and avoid one permission query per ID if it causes N+1.

`PermissionEvaluator` does not determine batch transaction semantics by itself. That is the application service's responsibility.

### 15.2. Permissions changing during a read

If a service checks permissions via metadata at T1 and loads the body at T2, permission could be revoked in between. Re-checking on the loaded record or using conditional queries reduces this window. Systems requiring strict consistency need transactions and locks/versions; **no single strategy fits every DB and isolation level**.

### 15.3. Auditing

Log the action name, resource type/ID, verified subject ID, tenant, allow/deny outcome, and policy version when needed. Never log full document bodies, tokens, passwords, or sensitive data just to debug an evaluator.

If policy requires auditing “who modified what,” emit the success event **after** the mutation succeeds (typically post-commit or via a transactional outbox). The evaluator should only record safe decision telemetry, never emit an “updated” domain event.

### 15.4. Admin privileges

Allowing admins to bypass owner checks may be valid in some organizations, but tenant/global scope, actions, and auditing must be explicit. Never sprinkle `hasRole('ADMIN') || hasPermission(...)` everywhere if admins must not cross tenant boundaries. Keep the exception inside a single policy and test cross-tenant admin cases too.

## 16. Implementation and testing checklist

- [ ] Clearly separated **authorization policy**, **resource loading**, and **business mutation** into distinct classes/responsibilities.
- [ ] `PermissionEvaluator` implements both overloads properly or safely denies the unused overload.
- [ ] `targetType`, actions, and IDs are allow-listed/validated; null targets or wrong types → false.
- [ ] Pre-checks use minimal metadata/projections without loading unnecessary bodies/attachments.
- [ ] No `save`/`delete`/domain events inside the evaluator.
- [ ] Identity/tenant come from a trusted authentication source; owner/state come from the repository, not client DTOs/headers.
- [ ] Evaluator is registered on the shared handler, `@EnableMethodSecurity` is enabled, and calls go through the Spring proxy.
- [ ] Read methods return content only after permission is granted, considering re-checks if data may change.
- [ ] Write methods use transactions and consistency mechanisms: lock + re-check, optimistic locking, or conditional updates.
- [ ] Denial exceptions are never swallowed; rollback rules and update row counts are verified.
- [ ] Tests cover allow/deny, cross-tenant, owner mismatch, locked state, nonexistent ID, and unknown actions.
- [ ] Tests verify **unauthorized writes do not mutate the DB** and the evaluator triggers no mutations.
- [ ] Concurrency tests cover permission revocation between pre-check and write when the business flow is sensitive.
- [ ] Query counts/latency are measured and batching/N+1/caching/invalidation are handled properly.
- [ ] Success domain events/audits are recorded after business commit, never emitted from the evaluator.
- [ ] Call paths via HTTP, jobs, and message consumers all pass through the protected service boundary.

**Core principle:** `PermissionEvaluator` answers **“is this allowed?”**, the repository answers **“what is the resource right now?”**, and the application service handles **“should and can this resource be modified consistently?”**. Separating these three questions makes code easier to test, easier to optimize, and prevents accidental data updates during permission checks.

## Official documentation

- [Spring Security — PermissionEvaluator JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html)
- [Spring Security — Method Security and hasPermission](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Framework — Declarative @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Boot 3.5.16 — Release and support announcement](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now)

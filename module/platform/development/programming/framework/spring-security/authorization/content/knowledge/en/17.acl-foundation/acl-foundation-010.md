# ACL Library, DataSource, and Required Configuration Components

## 1. What Problem Does This Solve?

In an application with many documents, projects, contracts, or records, `ROLE_EDITOR` is not enough to conclude that a user may edit **every** document. You need a mechanism binding permissions to **individual objects**: Alice can read Document #42, Bob is denied from reading Document #42, and members of the REVIEWER group can read it without deleting it.

**Spring Security Access Control List (ACL)** provides the infrastructure to persist and evaluate those rules. Running ACLs in Spring Boot requires more than a `@PreAuthorize` annotation: the `spring-security-acl` library, a JDBC `DataSource`, four database tables, `LookupStrategy`, `AclService`, `AclCache`, two control strategies, and `AclPermissionEvaluator` registered with the method-security expression handler.

After this **ACL Foundation** lesson, you will know:

1. Which library provides the ACL APIs and which dependency provides `DataSource`/transactions.
2. Why **all four tables** (`acl_sid`, `acl_class`, `acl_object_identity`, `acl_entry`) are required.
3. How to wire `JdbcMutableAclService`, `BasicLookupStrategy`, `SpringCacheBasedAclCache`, `AclAuthorizationStrategy`, and `PermissionGrantingStrategy`.
4. How to configure `AclPermissionEvaluator` for `hasPermission(...)` in `@PreAuthorize`.
5. Why generated-ID queries and schemas differ between HSQLDB and PostgreSQL.
6. How to test with Java 17+, HSQLDB, and real Spring Security through proxies—not merely checking that a bean was created.
7. Production risks: multiple datasources, ACL administration rights, N+1 queries, cache invalidation, and stale data when deleting resources.

**Illustrative versions:** Spring Boot 3.5.0, Spring Security 6.5.x, Java 17+, Gradle. The Java test examples below are complete code to run in a test project, though the reported results are **expected outcomes**, not captured execution logs.

## 2. Diagram of the Complete Call Path

**Permission read** flow when a service uses `@PreAuthorize`:

```text
Caller
  |
  v
Spring-managed bean via AOP proxy
  |
  v
@PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
  |
  v
PreAuthorizeAuthorizationManager
  |
  v
DefaultMethodSecurityExpressionHandler
  |
  v
AclPermissionEvaluator
  |
  v
AclService = JdbcMutableAclService or JdbcAclService
  |
  v
LookupStrategy = BasicLookupStrategy ----> AclCache
  |
  v
DataSource ---> SQL ---> acl_sid / acl_class
                      acl_object_identity / acl_entry
  |
  v
Acl + PermissionGrantingStrategy
  |
  +--> ALLOW: execute method body
  +--> DENY: skip method body; AccessDeniedException
```

**Permission write** flow:

```text
Authorization-checked ACL administration service
  |
  v
MutableAclService = JdbcMutableAclService
  |
  +-- createAcl(ObjectIdentity)
  +-- MutableAcl.insertAce(index, Permission, Sid, granting)
  +-- updateAcl(MutableAcl)
  +-- deleteAcl(ObjectIdentity, deleteChildren)
  |
  v
DataSource + transaction ---> ACL tables
  |
  v
Cache updated / evicted per implementation
```

Spring Security does not automatically create an ACL for every entity inserted into the database. **The lifecycle of creating, sharing, revoking, and deleting ACLs must be designed by the application**.

## 3. Components and Their Distinct Responsibilities

| Component | Common Implementation | Responsibility |
| --- | --- | --- |
| ACL model | `Acl`, `MutableAcl`, `ObjectIdentity`, `Sid`, `Permission`, `AccessControlEntry` | Represents resources, users/groups, and grant/deny ACEs |
| ACL read API | `AclService` | Loads ACLs for one or more `ObjectIdentity` instances |
| JDBC ACL read | `JdbcAclService` | Uses JDBC and `LookupStrategy` to read |
| ACL write API | `MutableAclService` | Creates, updates, and deletes ACLs/ACEs |
| JDBC ACL read/write | `JdbcMutableAclService` | Implements both `AclService` and `MutableAclService` |
| ACL lookup | `LookupStrategy`, `BasicLookupStrategy` | Loads, assembles, and batch-lookups ACLs from the DB |
| ACL cache | `AclCache`, `SpringCacheBasedAclCache` | Caches ACLs by ID to reduce DB queries |
| ACL edit strategy | `AclAuthorizationStrategy` | Controls who can administer/modify ACLs |
| ACE decision strategy | `PermissionGrantingStrategy` | Applies grant/deny evaluation rules |
| Expression integration | `AclPermissionEvaluator` | Evaluates `hasPermission` |
| Method Security | `MethodSecurityExpressionHandler` | Exposes evaluator in SpEL context |
| Connection | `javax.sql.DataSource` | Connects to the database holding ACL tables |

**Two strategies that must never be confused:** `AclAuthorizationStrategy` is not document `READ` permission. A user holding `ROLE_ACL_ADMIN` for managing ACLs might still **lack a READ ACE** to view document contents. Who may modify ACLs must be protected independently of what they can do on the resource.

`JdbcMutableAclService` extends `JdbcAclService`, so once you register the mutable JDBC service for a `DataSource`, you do not need to register a separate read-only `JdbcAclService`. Inject the `AclService` interface in read-only services; inject `MutableAclService` in administrative workflows.

## 4. Libraries and Dependencies

### 4.1. Gradle with Spring Boot

In a Spring Boot project with the appropriate BOM/plugin:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.security:spring-security-acl'

    // Production driver only when using PostgreSQL:
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.hsqldb:hsqldb'
}
```

This is a **`build.gradle` fragment**, not a complete project.

- `spring-security-acl`: provides `Acl`, `JdbcMutableAclService`, `BasicLookupStrategy`, strategies, and `AclPermissionEvaluator`.
- `spring-boot-starter-security`: provides authentication, authorization, and method-security config infrastructure. **Does not include the full ACL module by default**.
- `spring-boot-starter-jdbc`: Spring JDBC, `DataSource`, connection pool, and transaction infrastructure. JPA `EntityManager` is not required to use JDBC ACLs.
- `org.postgresql:postgresql`: for PostgreSQL only; substitute the appropriate driver for MySQL/MariaDB/SQL Server/Oracle.
- `spring-security-test`: provides `@WithMockUser` and security test utilities.
- `org.hsqldb:hsqldb`: embedded database for running tests matching default JDBC ACL SQL.

Without Spring Boot, you must configure `DataSource`, transaction manager, Spring JDBC/Context/Security dependencies, and versions manually. With Boot, keep **the same version line** across all Spring Security modules; never pin `spring-security-acl` to a different version than the `spring-security-config` managed by the BOM.

### 4.2. Maven Equivalent

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-acl</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
  </dependency>
  <dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
  </dependency>
</dependencies>
```

This fragment **assumes a Spring Boot parent or `dependencyManagement`/BOM**. Never copy it bare into an unmanaged POM expecting Maven to resolve compatible versions automatically.

## 5. `DataSource` and the Four Mandatory ACL Tables

Spring Security ACL uses **four standard JDBC tables**:

| Table | Role | Key Columns / Properties |
| --- | --- | --- |
| `acl_sid` | Principal or authority | `id`, `principal`, `sid`, unique on `(principal, sid)` |
| `acl_class` | Object type | `id`, `class`, unique on type name |
| `acl_object_identity` | A specific resource | `object_id_class`, `object_id_identity`, `owner_sid`, `parent_object`, `entries_inheriting` |
| `acl_entry` | ACEs for the object | `acl_object_identity`, `ace_order`, `sid`, `mask`, `granting`, `audit_success`, `audit_failure` |

Relationships:

```text
acl_class 1 ---- * acl_object_identity 1 ---- * acl_entry
                           |                       |
                     parent_object                 sid
                     owner_sid                     |
                           |                       v
                           +------------------> acl_sid
```

**Object ID differs from ACL row ID.** For a Document with primary key 42, an `acl_object_identity` row might have PK 100, reference type `demo.Document`, and hold `object_id_identity='42'`. SIDs Alice, Bob, and ROLE_REVIEWER are separate rows in `acl_sid`. Never use mask READ=1 to infer a document ID.

### 5.1. HSQLDB Schema to Run the Demo

Spring Security provides sample schemas per database. **HSQLDB** is chosen here because `JdbcMutableAclService`'s default generated-key queries use `call identity()`, matching HSQLDB. Create `src/test/resources/schema.sql`:

```sql
CREATE TABLE acl_sid (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    principal BOOLEAN NOT NULL,
    sid VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT uq_acl_sid UNIQUE (sid, principal)
);

CREATE TABLE acl_class (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    class VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT uq_acl_class UNIQUE (class)
);

CREATE TABLE acl_object_identity (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    object_id_class BIGINT NOT NULL,
    object_id_identity VARCHAR_IGNORECASE(36) NOT NULL,
    parent_object BIGINT,
    owner_sid BIGINT,
    entries_inheriting BOOLEAN NOT NULL,
    CONSTRAINT uq_acl_object UNIQUE (object_id_class, object_id_identity),
    CONSTRAINT fk_acl_object_class
        FOREIGN KEY (object_id_class) REFERENCES acl_class(id),
    CONSTRAINT fk_acl_object_parent
        FOREIGN KEY (parent_object) REFERENCES acl_object_identity(id),
    CONSTRAINT fk_acl_object_owner
        FOREIGN KEY (owner_sid) REFERENCES acl_sid(id)
);

CREATE TABLE acl_entry (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    acl_object_identity BIGINT NOT NULL,
    ace_order INTEGER NOT NULL,
    sid BIGINT NOT NULL,
    mask INTEGER NOT NULL,
    granting BOOLEAN NOT NULL,
    audit_success BOOLEAN NOT NULL,
    audit_failure BOOLEAN NOT NULL,
    CONSTRAINT uq_acl_entry UNIQUE (acl_object_identity, ace_order),
    CONSTRAINT fk_acl_entry_object
        FOREIGN KEY (acl_object_identity) REFERENCES acl_object_identity(id),
    CONSTRAINT fk_acl_entry_sid
        FOREIGN KEY (sid) REFERENCES acl_sid(id)
);
```

The schema retains all core columns and constraints per the **ACL Schema** section in Spring Security 6.5 docs. `VARCHAR_IGNORECASE` and the identity syntax above are **HSQLDB-specific**, not universal DDL for all databases.

**Practical notes:**

- Production uses Flyway/Liquibase/dedicated migrations; never configure schema re-initialization that wipes ACL data on every deploy.
- If the DB uses a dedicated schema/search path, qualify table names or align SQL/connection settings consistently.
- Enforce foreign keys, unique indexes, and `ace_order` so duplicate ACEs or mismatched objects cannot be written.
- ACL tables are **separate** from `JdbcUserDetailsManager`'s `users` and `authorities` tables; the two groups serve different functions.
- Plan ACL cleanup when deleting domain objects or transferring ownership; Spring Security does not automatically sync ACLs with your ORM/DAO lifecycle.

### 5.2. Generated-ID Queries Depend on Dialect

`JdbcMutableAclService` must fetch the newly generated ID after inserting into `acl_class` and `acl_sid`. Two properties:

- `classIdentityQuery`, defaulting to `call identity()`.
- `sidIdentityQuery`, defaulting to `call identity()`.

For **PostgreSQL**, Spring Security docs instruct:

```java
JdbcMutableAclService service =
    new JdbcMutableAclService(dataSource, lookupStrategy, aclCache);

service.setClassIdentityQuery(
    "select currval(pg_get_serial_sequence('acl_class', 'id'))"
);
service.setSidIdentityQuery(
    "select currval(pg_get_serial_sequence('acl_sid', 'id'))"
);
```

This is a **PostgreSQL-only illustrative snippet** and does not run standalone since `dataSource`/`lookupStrategy`/`aclCache` are not initialized here. On PostgreSQL, use the **PostgreSQL schema** instead of the HSQLDB SQL above. For MySQL/MariaDB/SQL Server/Oracle, consult the exact DDL/query for your target dialect and version.

Never substitute `SELECT MAX(id)`: under concurrent requests, it can return another row's ID and corrupt ACL/SID links. PostgreSQL's `currval(...)` is session-scoped; the insert and ID fetch must share the same connection.

## 6. Creating Beans Along the Dependency Chain

A standard Spring Boot configuration for JDBC ACL defines these beans:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.LookupStrategy;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class AclConfiguration {

    @Bean
    static MethodSecurityExpressionHandler expressionHandler(
            AclPermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler h =
            new DefaultMethodSecurityExpressionHandler();
        h.setPermissionEvaluator(evaluator);
        return h;
    }

    @Bean
    static AclPermissionEvaluator permissionEvaluator(
            AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    JdbcMutableAclService aclService(
            DataSource dataSource, LookupStrategy lookupStrategy,
            AclCache cache) {
        return new JdbcMutableAclService(
            dataSource, lookupStrategy, cache);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource, AclCache cache,
            AclAuthorizationStrategy aclAuthorizationStrategy,
            PermissionGrantingStrategy permissionGrantingStrategy) {
        return new BasicLookupStrategy(
            dataSource, cache,
            aclAuthorizationStrategy, permissionGrantingStrategy);
    }

    @Bean
    AclCache aclCache(
            PermissionGrantingStrategy permissionGrantingStrategy,
            AclAuthorizationStrategy aclAuthorizationStrategy) {
        Cache cache = new ConcurrentMapCache("aclCache");
        return new SpringCacheBasedAclCache(
            cache, permissionGrantingStrategy,
            aclAuthorizationStrategy);
    }

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_ADMIN"));
    }

    @Bean
    PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
            new ConsoleAuditLogger());
    }
}
```

This is a **complete configuration class**, yet not a self-contained runnable app: a `DataSource`/driver/schema and Spring Boot application context must be provided. This bean wiring matches the official Spring Security 6.5 documentation pattern.

### 6.1. Explaining the Choices

- **`@EnableMethodSecurity`** enables interceptors for `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` by default. Disabling pre/post stops `hasPermission` in `@PreAuthorize` from executing in this pattern.
- **`static @Bean MethodSecurityExpressionHandler`** publishes the handler early during Spring Security Method Security setup. `setPermissionEvaluator(evaluator)` is the critical link: without it, your evaluator bean may go unused.
- **`AclPermissionEvaluator(AclService)`** implements both `hasPermission(target, permission)` and `hasPermission(id, targetType, permission)`; it needs an `AclService` able to read ACL tables.
- **`JdbcMutableAclService`** handles both reading and updating ACLs, depending on `DataSource` + `LookupStrategy` + `AclCache`. For read-only apps, `JdbcAclService` is leaner.
- **`BasicLookupStrategy`** optimizes queries and assembles `Acl`s, supporting caching and batch retrieval. It also requires both ACL strategies.
- **`SpringCacheBasedAclCache`** uses `ConcurrentMapCache` in the example, which is JVM-local. Multi-pod/instance setups require an invalidation plan.
- **`AclAuthorizationStrategyImpl`** restricts ACL edits by authority, e.g., `ROLE_ACL_ADMIN`. Never grant this role to every user.
- **`DefaultPermissionGrantingStrategy`** evaluates grant/deny ACEs. `ConsoleAuditLogger` is simply an illustrative audit logger for demos.

### 6.2. Do Not Create Two Duplicate Read ACL Beans

`JdbcMutableAclService` implements both `AclService` and `MutableAclService`. Once registered, you can inject `AclService` into `AclPermissionEvaluator` without creating a separate `JdbcAclService`. If using multiple `DataSource`s, add explicit `@Qualifier`s on each bean; ambiguous candidates can crash Spring Boot startup or—worse—read the wrong ACL database.

### 6.3. Adjusting the Bean for PostgreSQL

Replace only the `aclService(...)` bean in the configuration above with:

```java
@Bean
JdbcMutableAclService aclService(
        DataSource dataSource, LookupStrategy lookupStrategy,
        AclCache cache) {
    JdbcMutableAclService service =
        new JdbcMutableAclService(dataSource, lookupStrategy, cache);
    service.setClassIdentityQuery(
        "select currval(pg_get_serial_sequence('acl_class', 'id'))");
    service.setSidIdentityQuery(
        "select currval(pg_get_serial_sequence('acl_sid', 'id'))");
    return service;
}
```

**Never declare two `@Bean aclService` methods with the same name simultaneously.** Keep the default bean in the HSQLDB test project below; the PostgreSQL variant is for PostgreSQL environments.

## 7. Self-Contained Java 17+ Project to Test ACL Infrastructure

The project below verifies:

- `DataSource` connects to all four tables.
- `JdbcMutableAclService` creates and reloads ACLs/ACEs.
- `AclPermissionEvaluator` is actually wired into the method-security expression handler.
- Alice gets READ, Bob is DENIED, REVIEWER members get READ, and someone with only `ACL_ADMIN` does not automatically get READ.
- Ungranted WRITE, different object types, and objects without ACLs are denied.
- Deleting an ACE and updating the ACL immediately revokes access, even after a cached read.

### 7.1. Project Files

```text
acl-infrastructure-demo/
├── settings.gradle
├── build.gradle
└── src/test/
    ├── java/demo/AclInfrastructureTest.java
    └── resources/schema.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'acl-infrastructure-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-acl'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.hsqldb:hsqldb'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**File `src/test/resources/schema.sql`:** copy the full SQL from section 5.1 verbatim. In this test-only project, HSQLDB runs in memory and Spring Boot executes the schema because `spring.sql.init.mode=always` and `schema-locations=classpath:schema.sql` are declared on the test class.

### 7.2. Complete Test Java File

Create `src/test/java/demo/AclInfrastructureTest.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import javax.sql.DataSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.LookupStrategy;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
    classes = AclInfrastructureTest.Config.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.sql.init.mode=always",
        "spring.sql.init.schema-locations=classpath:schema.sql"
    }
)
@WithMockUser(username = "alice", roles = "ACL_ADMIN")
public class AclInfrastructureTest {

    private static final AtomicLong IDS = new AtomicLong(10000L);

    @Autowired DataSource dataSource;
    @Autowired JdbcMutableAclService aclService;
    @Autowired AclCache cache;
    @Autowired DocumentService documents;
    @Autowired Probe probe;

    private Long id;
    private ObjectIdentity identity;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    public static class Config {

        @Bean
        static MethodSecurityExpressionHandler expressionHandler(
                AclPermissionEvaluator evaluator) {
            DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
            handler.setPermissionEvaluator(evaluator);
            return handler;
        }

        @Bean
        static AclPermissionEvaluator evaluator(
                JdbcMutableAclService service) {
            return new AclPermissionEvaluator(service);
        }

        @Bean
        JdbcMutableAclService aclService(
                DataSource source, LookupStrategy lookup,
                AclCache aclCache) {
            return new JdbcMutableAclService(source, lookup, aclCache);
        }

        @Bean
        LookupStrategy lookup(
                DataSource source, AclCache aclCache,
                AclAuthorizationStrategy authStrategy,
                PermissionGrantingStrategy permissionStrategy) {
            return new BasicLookupStrategy(
                source, aclCache, authStrategy, permissionStrategy);
        }

        @Bean
        AclCache aclCache(
                PermissionGrantingStrategy permissionStrategy,
                AclAuthorizationStrategy authStrategy) {
            Cache springCache = new ConcurrentMapCache("aclCache");
            return new SpringCacheBasedAclCache(
                springCache, permissionStrategy, authStrategy);
        }

        @Bean
        AclAuthorizationStrategy authStrategy() {
            return new AclAuthorizationStrategyImpl(
                new SimpleGrantedAuthority("ROLE_ACL_ADMIN"));
        }

        @Bean
        PermissionGrantingStrategy permissionStrategy() {
            return new DefaultPermissionGrantingStrategy(
                new ConsoleAuditLogger());
        }

        @Bean Probe probe() {
            return new Probe();
        }

        @Bean DocumentService documents(Probe probe) {
            return new DocumentService(probe);
        }
    }

    public static class Probe {
        private final AtomicInteger calls = new AtomicInteger();

        void mark() { calls.incrementAndGet(); }
        int count() { return calls.get(); }
        void reset() { calls.set(0); }
    }

    public static class DocumentService {
        private final Probe probe;

        public DocumentService(Probe probe) {
            this.probe = probe;
        }

        @PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
        public String read(@P("id") Long id) {
            probe.mark();
            return "DOC:" + id;
        }

        @PreAuthorize("hasPermission(#id, 'demo.Document', 'WRITE')")
        public String write(@P("id") Long id) {
            probe.mark();
            return "WRITTEN:" + id;
        }

        @PreAuthorize("hasPermission(#id, 'demo.Invoice', 'READ')")
        public String invoice(@P("id") Long id) {
            probe.mark();
            return "INVOICE:" + id;
        }
    }

    @BeforeEach
    void setUp() {
        id = IDS.incrementAndGet();
        identity = new ObjectIdentityImpl("demo.Document", id);
        probe.reset();

        MutableAcl acl = aclService.createAcl(identity);
        acl.insertAce(0, BasePermission.READ,
            new PrincipalSid("alice"), true);
        acl.insertAce(1, BasePermission.READ,
            new PrincipalSid("bob"), false);
        acl.insertAce(2, BasePermission.READ,
            new GrantedAuthoritySid("ROLE_REVIEWER"), true);
        aclService.updateAcl(acl);
    }

    @AfterEach
    void tearDown() {
        aclService.deleteAcl(identity, true);
    }

    @Test
    void infrastructureUsesSpringBeansAndProxy() {
        assertThat(dataSource).isNotNull();
        assertThat(aclService).isNotNull();
        assertThat(cache).isNotNull();
        assertThat(AopUtils.isAopProxy(documents)).isTrue();
    }

    @Test
    void schemaContainsFourQueryableAclTables() {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        assertThat(jdbc.queryForObject(
            "select count(*) from acl_sid", Long.class)).isNotNull();
        assertThat(jdbc.queryForObject(
            "select count(*) from acl_class", Long.class)).isNotNull();
        assertThat(jdbc.queryForObject(
            "select count(*) from acl_object_identity", Long.class))
            .isNotNull();
        assertThat(jdbc.queryForObject(
            "select count(*) from acl_entry", Long.class)).isNotNull();
    }

    @Test
    void aclIsPersistedWithThreeEntries() {
        Acl loaded = aclService.readAclById(identity);
        assertThat(loaded.getObjectIdentity()).isEqualTo(identity);
        assertThat(loaded.getEntries()).hasSize(3);
    }

    @Test
    void aliceCanReadHerGrantedDocument() {
        assertThat(documents.read(id)).isEqualTo("DOC:" + id);
        assertThat(probe.count()).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "bob", roles = "ACL_ADMIN")
    void bobIsExplicitlyDeniedBeforeMethodBody() {
        assertThatThrownBy(() -> documents.read(id))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
    }

    @Test
    @WithMockUser(username = "carol", roles = {"ACL_ADMIN", "REVIEWER"})
    void reviewerAuthorityMayRead() {
        assertThat(documents.read(id)).isEqualTo("DOC:" + id);
        assertThat(probe.count()).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "carol", roles = "ACL_ADMIN")
    void aclAdminRoleDoesNotAutomaticallyGrantDomainRead() {
        assertThatThrownBy(() -> documents.read(id))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
    }

    @Test
    void writeHasNoGrantAndIsDenied() {
        assertThatThrownBy(() -> documents.write(id))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
    }

    @Test
    void wrongObjectTypeCannotReuseSameIdAcl() {
        assertThatThrownBy(() -> documents.invoice(id))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
    }

    @Test
    void readForMissingAclDoesNotAllow() {
        assertThatThrownBy(() -> documents.read(id + 100000L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
    }

    @Test
    void revokeIsVisibleAfterUpdate() {
        assertThat(documents.read(id)).isEqualTo("DOC:" + id);

        MutableAcl mutable = (MutableAcl) aclService.readAclById(identity);
        mutable.deleteAce(0); // Remove Alice's READ grant.
        aclService.updateAcl(mutable);

        assertThatThrownBy(() -> documents.read(id))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isEqualTo(1);
    }
}
```

### 7.3. Key Points in the Test

**Real DataSource:** `@SpringBootTest` boots a Spring context with Boot auto-configuration for embedded HSQLDB. HSQLDB receives its schema from the SQL initializer before tests run. This is not merely `new JdbcMutableAclService(...)` returning mocks.

**SecurityContext:** `@WithMockUser(username = "alice", roles = "ACL_ADMIN")` creates principal Alice with `ROLE_ACL_ADMIN` to authorize creating/updating/deleting ACL fixtures. Bob/Carol tests override username and roles per case. In production, never grant ACL admin to everyone; the test uses this role to prepare and clean up the database.

**Real ACL data:** `setUp()` creates a fresh `ObjectIdentity` ID, inserts three ACEs, and calls `updateAcl`. `@AfterEach` deletes the ACL so leftover rows do not leak between tests. Each test receives a distinct ID, avoiding unique-key collisions in `acl_object_identity`.

**Separating admin rights from resource rights:** Carol holds `ROLE_ACL_ADMIN` yet has no SID granted READ, so she must be denied. Only when Carol also holds `ROLE_REVIEWER` does she gain READ via `GrantedAuthoritySid`.

**Verifying method security:** `DocumentService` is injected by Spring, and `AopUtils.isAopProxy` must be true. `@P("id")` preserves parameter name `#id` so SpEL does not depend on `-parameters`. `Probe` proves that when `@PreAuthorize` denies, the method body never executes.

**Testing cache/revocation:** the final test reads once to populate the ACL, deletes Alice's granting ACE, updates the ACL, and calls again. It must deny; this is far stronger than merely asserting that a cache bean exists.

### 7.4. Running and Expected Results

In `acl-infrastructure-demo` with Gradle and JDK 17+:

```bash
gradle test --tests demo.AclInfrastructureTest
```

If using the Gradle Wrapper, run `./gradlew test --tests demo.AclInfrastructureTest` (Linux/macOS) or `gradlew.bat test --tests demo.AclInfrastructureTest` (Windows).

When wiring and database are correct, all **11 tests** are expected to pass and Gradle finishes with `BUILD SUCCESSFUL`. This is the **expected outcome by design**, not output from an actual run. The HTML report is written to `build/reports/tests/test/index.html`.

| Test | What It Confirms |
| --- | --- |
| Infrastructure | Beans and Spring AOP proxy are real |
| Schema | All four ACL tables are queryable |
| Persistence | `ObjectIdentity` and three ACEs reload accurately |
| Alice READ | Allowed; body executes once |
| Bob READ | Explicitly denied; body does not run |
| Carol + REVIEWER | Allowed via authority SID |
| Carol with ACL_ADMIN only | Domain READ denied |
| Ungranted WRITE | Denied |
| Same numeric ID, different type | Denied |
| Nonexistent ObjectIdentity | Not permitted |
| Revoke READ | Call after `updateAcl` is denied |

For production testing, add PostgreSQL/MySQL Testcontainers, transaction commit/rollback tests, multi-tenant permissions, and concurrent execution across multiple application nodes.

## 8. Production `DataSource` and Transactions

### 8.1. PostgreSQL `DataSource` Configuration

Sample `application.yml` for a project that already uses migrations:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.example.internal:5432/appdb
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
  sql:
    init:
      mode: never
```

`DB_USER` and `DB_PASSWORD` are **illustrative environment variables**, not real credentials. Use a secret manager/env vars. Production DDL is managed by Flyway/Liquibase or controlled migrations. Never run the HSQLDB schema on PostgreSQL: `VARCHAR_IGNORECASE` is incompatible and generated-key queries differ.

If the application has **multiple `DataSource`s**, use explicit qualifiers for ACL; `JdbcMutableAclService` and `BasicLookupStrategy` must target the same ACL database/schema. If domain data and ACL data live in separate databases, a single `@Transactional` on one transaction manager is **not enough** to guarantee atomic commits across both.

### 8.2. Transactions for ACL Updates

Creating an ACL and adding ACEs can execute multiple SQL statements: inserting a new class/SID, creating the object identity, inserting entries, and updating owner/inheritance. Define clear transaction boundaries on administration services. Under Spring's default proxy model, `@Transactional` intercepts calls through the bean proxy, not internal `this.innerMethod()` calls.

Also establish the ordering between DB updates and ACL cache eviction. Some caches do not participate in DB transactions; in multi-instance deployments, revoked permissions must not keep succeeding because stale cache entries linger too long.

## 9. Caching, Performance, and Consistency

`BasicLookupStrategy` supports batch ACL reads from the database and `AclCache` reduces query cost. However, that does not mean `@PostFilter("hasPermission(filterObject, 'READ')")` across thousands of documents automatically turns into safe SQL pagination.

Scenarios to handle:

- **N+1 queries:** each item invokes the evaluator, triggering separate lookups unless batched/cached properly.
- **Pagination:** filtering in RAM after fetching a page produces underfilled pages, skewed `totalElements`, and metadata leaks. Prefer enforcing permission constraints directly in queries.
- **Permission revocation:** `updateAcl`, `deleteAcl`, or ACE edits must evict caches; test grant → revoke → deny.
- **Multiple pods:** `ConcurrentMapCache` is JVM-local; you may need distributed invalidation or TTLs matching consistency requirements.
- **SID/role changes:** if a user loses a role while an existing authentication still holds that authority, outcomes can be stale; align session/token lifecycles and caches.
- **ACL inheritance:** changing a parent or `entriesInheriting` can affect many child ACLs; test dependent invalidation.
- **Multi-tenancy:** matching business IDs across two tenants must never collide onto one `ObjectIdentity`; isolate type/identifier/schema properly and test cross-tenant access.

## 10. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Missing `Acl` or `JdbcMutableAclService` class | Missing `spring-security-acl` or version mismatch | Inspect dependency tree and BOM |
| No `DataSource` bean | Missing JDBC starter, driver, or config | Check connection URL, driver, credentials |
| `Table acl_sid not found` | Schema not applied or wrong `search_path` | Run migrations against right database/schema |
| DDL fails on `VARCHAR_IGNORECASE` | Running HSQLDB SQL on PostgreSQL | Use PostgreSQL schema |
| SQL fails on `call identity()` | Default HSQLDB query on another DB | Configure `classIdentityQuery`, `sidIdentityQuery` |
| `hasPermission` always denies | Evaluator not wired to method expression handler | `static @Bean`, `setPermissionEvaluator`, test via proxy |
| `@PreAuthorize` never runs | Missing `@EnableMethodSecurity`, self-invocation, `new` | Invoke Spring-managed bean externally |
| `#id` is `null` | Missing parameter metadata / `@P` | Use `@P("id")` or `-parameters` |
| ACE exists in DB yet denies | Wrong type/ID, SID, permission, or role string | Compare DB rows with `ObjectIdentity` and `Sid` |
| Has `ACL_ADMIN` yet cannot read document | Confused ACL admin rights with READ grant | Check ACEs on that specific resource |
| No ACE, expecting `Acl.isGranted` to return false | No-match may throw `NotFoundException` | Distinguish no-rule from explicit deny; fail closed |
| Grant/revoke not effective immediately | ACL cache or authentication not refreshed | Test eviction, multi-pod, token lifecycle |
| ACL exists yet write fails | Missing ACL admin rights, transaction, or FK | Check `AclAuthorizationStrategy` and SQL |
| Prod fails while HSQLDB tests pass | Different dialect, different generated-key query | Test with PostgreSQL Testcontainers |
| Stale ACL remains after deleting entity | Missing lifecycle hook | Implement cleanup via `MutableAclService` |
| Slow list filtering | Calling `hasPermission` per item | Batch lookup, cache, scoped queries |
| Data modified before final denial | `@PostAuthorize` runs after body | Guard before side effects with `@PreAuthorize` |

### Bottom-Up Debugging Workflow

1. **Connectivity:** Is `DataSource` pointing at the right database/schema with required SQL privileges?
2. **DDL:** Do all four tables exist with right column types, FKs/unique constraints, and generated-ID strategy?
3. **Read/write:** Do `createAcl`, `insertAce`, `updateAcl`, and `readAclById` work when called directly on the configured service?
4. **Strategy:** Does `Acl.isGranted(...)` with exact SIDs/permissions resolve as grant, explicit deny, or no-match?
5. **Evaluator:** Can `AclPermissionEvaluator.hasPermission` parse the exact object ID/type and permission?
6. **Expression handler:** Is the `MethodSecurityExpressionHandler` bean wired to that evaluator?
7. **Proxy:** Is the method called through a Spring bean with `@EnableMethodSecurity`, or bypassed via self-invocation?
8. **Freshness:** After grant/revoke, are caches and authentication tokens refreshed properly?
9. **Environment:** Are there differences in dialect, migrations, multiple instances, or transaction managers?

## 11. Exercises and Acceptance Checklist

**Exercise A — Add WRITE:** In the test, add a `BasePermission.WRITE` ACE for Alice, call `updateAcl`, and verify `documents.write(id)` flips from deny to allow.

**Exercise B — Separate admin and read:** Give Carol only `ROLE_ACL_ADMIN`, verify she is denied without a READ ACE. Then grant `ROLE_REVIEWER` and verify allow.

**Exercise C — Switch dialect:** Switch from HSQLDB to PostgreSQL, apply the right SQL schema, and update both generated-key queries. Run tests against PostgreSQL Testcontainers rather than merely checking app startup.

**Exercise D — Revocation:** Repeat grant → read → revoke → read across two instances and distinct caches. Verify the mechanism preventing revoked data from still being served.

**Exercise E — Fail closed:** Test an ID with no ACL, wrong type, unknown permission, unloaded SID, and DB failure; none may accidentally grant access.

Pre-deployment checklist:

- [ ] `spring-security-acl` matches the system-wide Spring Security version.
- [ ] `DataSource` and driver are present; transaction manager matches the datasource.
- [ ] All four ACL tables have required constraints, and identity/sequence queries match the dialect.
- [ ] `JdbcMutableAclService`, `BasicLookupStrategy`, `AclCache`, and strategies are wired properly.
- [ ] `AclPermissionEvaluator` is registered via `setPermissionEvaluator` on the method-security expression handler.
- [ ] `@EnableMethodSecurity` is enabled and services are invoked through Spring AOP proxies.
- [ ] Tests cover grant, deny, no-ACL, role SID, wrong type, ungranted WRITE, and revocation/cache.
- [ ] Mechanisms exist for ACL governance, auditing, migrations, entity-deletion cleanup, and multi-instance invalidation.
- [ ] HSQLDB tests are never treated as a substitute for testing PostgreSQL/MySQL matching production.

## 12. Key Takeaway

**Configuration order:** add ACL dependency → configure `DataSource` → migrate four ACL tables → wire `BasicLookupStrategy`/`JdbcMutableAclService`/`AclCache` → wire both authorization strategies → `AclPermissionEvaluator` → `DefaultMethodSecurityExpressionHandler` → `@EnableMethodSecurity` and test through Spring proxies.

ACLs are more than a single annotation. The entire chain must work and be tested **from SQL all the way to per-resource authorization decisions**, especially when permissions are revoked or the application runs across multiple instances.

## Official References

- Spring Security 6.5 — Domain Object Security (ACLs), bean configuration: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html
- Spring Security 6.5 — Security Database Schema, ACL DDL per database: https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html
- Spring Security 6.5 — Method Security, custom expression handler: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 API — `JdbcMutableAclService` generated-ID queries: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html
- Spring Security 6.5 API — `AclPermissionEvaluator`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/AclPermissionEvaluator.html
- Spring Security 6.5 API — `SpringCacheBasedAclCache`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/SpringCacheBasedAclCache.html

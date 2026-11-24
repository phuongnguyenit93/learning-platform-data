# AclService, MutableAclService, and JdbcMutableAclService

> **Context:** Spring Security – authorization → **ACL Implementation**. This lesson focuses on the read API `AclService`, the read/write API `MutableAclService`, and the JDBC persistence implementation `JdbcMutableAclService`. You will configure the ACL components, manage a resource's permission lifecycle, and test grant/revoke operations with Java 17+, Spring Boot 3.x, Spring Security 6.x, and in-memory HSQLDB.

## 1. Why Are These Three Components Needed?

Checking `hasAuthority('DOC_READ')` only evaluates the caller's general authority. A document-sharing application may need more granular rules:

- Alice is allowed to read `Document#101`.
- Bob is allowed to read `Document#202`.
- Anyone with `ROLE_REVIEWER` is allowed to read `Document#303`.
- Do not infer WRITE permission, or READ permission on another document, just because a single grant exists.

Spring Security ACL attaches an **Access Control Entry (ACE)** to the ACL of each **ObjectIdentity**:

~~~text
Document#101 / ACL
  ├── PrincipalSid("alice") → READ: grant
  └── PrincipalSid("bob")   → WRITE: deny

Document#303 / ACL
  └── GrantedAuthoritySid("ROLE_REVIEWER") → READ: grant
~~~

An ACL decision combines four factors: which resource (ObjectIdentity), who (Sid), what action (Permission), and allow or deny (granting). Having only the SID or only the permission is not enough.

At implementation time, the system needs to **read permissions to make decisions**, **grant/revoke permissions when business state changes**, and **persist permissions durably in the database**. That is the role of `AclService`, `MutableAclService`, and `JdbcMutableAclService`.

## 2. Relationship Between the Interfaces and the JDBC Implementation

~~~text
               AclService
               (interface)
                 ▲      ▲
                 │      │
    MutableAclService   JdbcAclService
        (interface)       (class)
                 ▲      ▲
                 │      │
                 └── JdbcMutableAclService
                       (class)
                         │
             DataSource / JDBC + LookupStrategy
                                    │
                            BasicLookupStrategy
                                    │
                                 AclCache
~~~

| Component | Role | Main operations |
| --- | --- | --- |
| `AclService` | **Read** contract for ACLs | `readAclById`, `readAclsById`, `findChildren` |
| `MutableAclService` | Interface **extending AclService** to manage permissions | `createAcl`, `updateAcl`, `deleteAcl`, plus all read operations |
| `JdbcAclService` | Read-only JDBC implementation | Uses `LookupStrategy` and `DataSource` |
| `JdbcMutableAclService` | **Read/write** JDBC service extending `JdbcAclService` | Creates/updates/deletes ACLs across the four tables |
| `BasicLookupStrategy` | Default `LookupStrategy` implementation | Reads ACLs efficiently, supporting batching and caching |
| `AclCache` | Speeds up ACL reads | Cache, evict, and clear |
| `AclPermissionEvaluator` | Connects `hasPermission` expressions to `AclService` | Uses ACLs when method security evaluates permissions |

A `JdbcMutableAclService` instance can be injected as either `AclService` **or** `MutableAclService`. Classes that only check permissions should take `AclService`; classes that administer ACEs take `MutableAclService`. This reduces the exposed API surface, though it **does not by itself replace** authorization checks on permission-granting endpoints.

### The Objects These Three APIs Operate On

~~~text
ObjectIdentity("demo.acl.Document", 101L)
             │
             ▼
            Acl
      ┌──────┴────────┐
      │               │
   owner SID       ACE list
                     │
                SID + Permission
                + grant/deny
                     │
                  parent ACL?
~~~

`ObjectIdentity` consists of a type and an ID. It is not the same as the auto-generated PK of the `acl_object_identity` table. `Acl` holds the ACEs and metadata; `MutableAcl` is an ACL that can be modified before persisting.

## 3. `AclService`: Reading and Evaluating an ACL

Interface:

~~~java
import org.springframework.security.acls.model.AclService;
~~~

| Method | Meaning |
| --- | --- |
| `readAclById(ObjectIdentity oid)` | Retrieves the ACL for a single ObjectIdentity |
| `readAclById(ObjectIdentity oid, List<Sid> sids)` | Reads the ACL for the list of SIDs the caller cares about |
| `readAclsById(List<ObjectIdentity> oids)` | Reads multiple ACLs |
| `readAclsById(List<ObjectIdentity> oids, List<Sid> sids)` | Reads multiple ACLs, supporting SID-based/batch lookup |
| `findChildren(ObjectIdentity parent)` | Finds objects whose parent ACL is this object; may return `null` |

`readAclById` returns an **`Acl`**, not a `boolean`. To decide access, use `Acl.isGranted(...)`:

~~~java
// ILLUSTRATION: aclService and authentication are already provided.
ObjectIdentity oid =
        new ObjectIdentityImpl("demo.acl.Document", 101L);

List<Sid> sids = new SidRetrievalStrategyImpl()
        .getSids(authentication);

Acl acl = aclService.readAclById(oid, sids);

boolean allowed = acl.isGranted(
        List.of(BasePermission.READ),
        sids,
        false);
~~~

`SidRetrievalStrategyImpl` creates the SIDs corresponding to the Authentication's principal and authorities. `Acl.isGranted` matches permission + SID against the actual ACEs, according to `PermissionGrantingStrategy` and parent inheritance when present.

**Do not use**:

~~~java
// WRONG: a grant ACE belonging to someone else also makes the result true.
boolean allowed = acl.getEntries().stream()
        .anyMatch(entry -> entry.isGranting());
~~~

Because that approach ignores the SID, permission, order, deny ACEs, and parent ACLs.

### Missing ACLs, Missing ACEs, and Unloaded SIDs

- `readAclById` may throw `NotFoundException` when no ACL exists for the ObjectIdentity.
- `Acl.isGranted` may also throw `NotFoundException` when the ACL exists but has no entry sufficient to reach a decision for the requested permission/SID.
- `UnloadedSidException` indicates querying a SID that is not present in a partially loaded ACL.

When verifying **permissions**, a missing ACL or ACE must lead to **deny by default**. If the database fails or an `UnloadedSidException` occurs due to a misconfigured lookup, do not return allow to "save" the system. Handle infrastructure errors separately and stay fail closed.

### Using Batch Reads Properly

When evaluating multiple ObjectIdentities:

~~~java
// ILLUSTRATION: variables already exist in the service.
Map<ObjectIdentity, Acl> aclByObject =
        aclService.readAclsById(objectIdentities, sids);
~~~

`BasicLookupStrategy` supports batch querying; for large numbers of objects, this typically reduces overhead compared to calling `readAclById` 100 times. However, you must check the permission for **each individual ACL** via `isGranted`; a batch read does not mean every object in the map is allowed.

## 4. `MutableAclService`: Creating, Updating, and Deleting ACLs

This interface extends `AclService` and adds:

| Method | Result | What to keep in mind |
| --- | --- | --- |
| `createAcl(oid)` | Creates an empty ACL and returns `MutableAcl` | Not an upsert; if it already exists, may throw `AlreadyExistsException` |
| `updateAcl(mutableAcl)` | Persists the modified ACL | ACL must already exist; may throw `NotFoundException` |
| `deleteAcl(oid, deleteChildren)` | Deletes the ACL and handles children per flag | `deleteChildren=false` may throw `ChildrenExistException` |
| Methods from `AclService` | Reads ACLs as usual | Should be used before modifying ACEs |

**Workflow for creating and granting READ:**

~~~java
// ILLUSTRATION in a service with ACL modification permissions and a transaction.
ObjectIdentity oid =
        new ObjectIdentityImpl("demo.acl.Document", 101L);

MutableAcl acl = mutableAclService.createAcl(oid);

acl.insertAce(
        acl.getEntries().size(),
        BasePermission.READ,
        new PrincipalSid("alice"),
        true
);

mutableAclService.updateAcl(acl);
~~~

`insertAce(index, permission, sid, granting)` **modifies the ACL in memory**; only `updateAcl` persists it. `granting=true` means allow, and `false` means deny. A newly created empty ACL does not automatically let the owner read the document; `Acl.getOwner()` governs ACL administration rights per the strategy, which is **not synonymous** with content READ/WRITE.

**Workflow for modifying an existing ACL:**

~~~java
MutableAcl acl = (MutableAcl) mutableAclService.readAclById(oid);

acl.insertAce(
        acl.getEntries().size(),
        BasePermission.WRITE,
        new GrantedAuthoritySid("ROLE_EDITOR"),
        true
);

mutableAclService.updateAcl(acl);
~~~

To revoke an ACE, find its exact index in `acl.getEntries()`, call `acl.deleteAce(index)`, and then call `updateAcl`. Do not accidentally delete all entries, because an object may have other grants, denies, group permissions, or parent inheritance.

### Idempotency and Concurrency

A document-sharing API may receive the same event twice. Before adding an ACE, check whether the corresponding permission/SID already exists so the operation is idempotent and avoids duplicate entries. However, checking before inserting **does not by itself eliminate race conditions**: two transactions reading and updating the same ACL concurrently can still cause lost updates or unique/order constraint errors. Use locking, optimistic versioning, or serialization per ObjectIdentity when needed.

## 5. `JdbcMutableAclService` and Its Minimum Dependencies

`JdbcMutableAclService` extends `JdbcAclService` and implements `MutableAclService`.

Key constructor:

~~~java
new JdbcMutableAclService(
        dataSource,
        lookupStrategy,
        aclCache);
~~~

Three dependencies:

- `DataSource`: connection to the database storing the ACLs.
- `LookupStrategy`: selects how ACLs are looked up, usually `BasicLookupStrategy`.
- `AclCache`: caches loaded ACLs.

A single instance does not automatically create the schema or enforce Method Security. You must configure the database, lookup strategy, permission strategy, ACL authorization strategy, and (if using annotations) the expression handler.

### The Four ACL Tables

| Table | Role | Columns to understand |
| --- | --- | --- |
| `acl_sid` | Principal/authority SIDs | `id`, `principal`, `sid` |
| `acl_class` | Domain object types | `id`, `class` |
| `acl_object_identity` | Identity of each ACL object, owner, parent | `object_id_class`, `object_id_identity`, `owner_sid`, `parent_object`, `entries_inheriting` |
| `acl_entry` | Individual ACEs | `acl_object_identity`, `ace_order`, `sid`, `mask`, `granting`, audit flags |

The PK of an ACL table is different from the domain object ID. A document with ID 101 can be referenced in the `object_id_identity` column, while the auto-generated ACL PK belongs to the `acl_object_identity` table.

### Choosing the Right Database Dialect

`JdbcMutableAclService` is designed by default with SQL/identity queries for **HSQLDB**. If using PostgreSQL, the Spring documentation specifies two queries to retrieve generated IDs after insert:

~~~sql
select currval(pg_get_serial_sequence('acl_class', 'id'));
select currval(pg_get_serial_sequence('acl_sid', 'id'));
~~~

In that case, configure:

~~~java
// POSTGRESQL ONLY; bean variables already exist.
JdbcMutableAclService jdbc =
        new JdbcMutableAclService(dataSource, lookupStrategy, aclCache);

jdbc.setClassIdentityQuery(
        "select currval(pg_get_serial_sequence('acl_class', 'id'))");
jdbc.setSidIdentityQuery(
        "select currval(pg_get_serial_sequence('acl_sid', 'id'))");
~~~

For H2, MySQL/MariaDB, SQL Server, or Oracle, verify the schema and identity SQL for that dialect. Do not simply change the JDBC URL and expect the HSQLDB defaults to work.

### Behavior of `updateAcl` over JDBC

The `JdbcMutableAclService.updateAcl` Javadoc notes that the JDBC implementation may **delete all ACE rows for the ACL and recreate them** from the current ACE list. Therefore:

- A transaction for updating ACLs is mandatory if atomicity is required.
- `ace_order` and ACE evaluation order must be clearly understood.
- Two concurrent writers can overwrite each other's changes.
- Do not rely on the PK of an individual ACE as a durable identifier across updates.
- Cache invalidation is needed, especially when multiple service instances share ACL data.

## 6. Runnable Example: Spring Boot + HSQLDB + JDBC ACL

The sample uses Java 17+, Spring Boot 3.x, and Spring Security 6.x. All Java files live in package `demo.acl`. HSQLDB is chosen because it matches the default identity queries and DDL documented by Spring Security, allowing the exercise to avoid PostgreSQL-specific configuration.

### 6.1. Gradle Dependencies

In a Spring Boot Gradle project already configured with the `java` plugin, `org.springframework.boot`, and compatible dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.security:spring-security-acl'
    runtimeOnly 'org.hsqldb:hsqldb'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-security-acl` is a separate module and is not automatically included by `spring-boot-starter-security`. No controller/web starter is needed for these service tests.

### 6.2. Datasource

**`src/main/resources/application.properties`**

~~~properties
spring.datasource.url=jdbc:hsqldb:mem:acl_demo
spring.datasource.driver-class-name=org.hsqldb.jdbc.JDBCDriver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

Spring Boot runs `schema.sql` when initializing the database. In-memory HSQLDB is for demos/tests; production should use migrations managed with Flyway/Liquibase to track schema changes and avoid running DDL repeatedly against a real database.

### 6.3. HSQLDB ACL Schema

**`src/main/resources/schema.sql`**

~~~sql
create table acl_sid (
    id bigint generated by default as identity(start with 100) not null primary key,
    principal boolean not null,
    sid varchar_ignorecase(100) not null,
    constraint uk_acl_sid unique (sid, principal)
);

create table acl_class (
    id bigint generated by default as identity(start with 100) not null primary key,
    class varchar_ignorecase(100) not null,
    constraint uk_acl_class unique (class)
);

create table acl_object_identity (
    id bigint generated by default as identity(start with 100) not null primary key,
    object_id_class bigint not null,
    object_id_identity varchar_ignorecase(36) not null,
    parent_object bigint,
    owner_sid bigint,
    entries_inheriting boolean not null,
    constraint uk_acl_identity unique (object_id_class, object_id_identity),
    constraint fk_acl_parent foreign key (parent_object)
        references acl_object_identity(id),
    constraint fk_acl_class foreign key (object_id_class)
        references acl_class(id),
    constraint fk_acl_owner foreign key (owner_sid)
        references acl_sid(id)
);

create table acl_entry (
    id bigint generated by default as identity(start with 100) not null primary key,
    acl_object_identity bigint not null,
    ace_order integer not null,
    sid bigint not null,
    mask integer not null,
    granting boolean not null,
    audit_success boolean not null,
    audit_failure boolean not null,
    constraint uk_acl_entry unique (acl_object_identity, ace_order),
    constraint fk_acl_entry_object foreign key (acl_object_identity)
        references acl_object_identity(id),
    constraint fk_acl_entry_sid foreign key (sid)
        references acl_sid(id)
);
~~~

The four tables along with their foreign keys and unique constraints form the core. With default `JdbcMutableAclService`, column names and generated ID retrieval must be compatible. Do not replace `varchar_ignorecase` with another database's type and assume it is still HSQLDB.

### 6.4. Spring Boot Application and Model

**`src/main/java/demo/acl/AclDemoApplication.java`**

~~~java
package demo.acl;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class AclDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AclDemoApplication.class, args);
    }
}
~~~

**`src/main/java/demo/acl/Document.java`**

~~~java
package demo.acl;

public record Document(long id, String title) {
}
~~~

`Document.class.getName()` will be `"demo.acl.Document"`. The example creates `ObjectIdentityImpl(Document.class.getName(), id)` to supply **type + ID** explicitly. Do not use the constructor taking a domain object on a Java record expecting a `getId()` accessor by default; the record here has an `id()` accessor.

### 6.5. Configuring the ACL Beans

**`src/main/java/demo/acl/AclInfrastructure.java`**

~~~java
package demo.acl;

import javax.sql.DataSource;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.jdbc.LookupStrategy;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration
public class AclInfrastructure {

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
                new SimpleGrantedAuthority("ACL_ADMIN"));
    }

    @Bean
    PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
                new ConsoleAuditLogger());
    }

    @Bean
    AclCache aclCache(
            PermissionGrantingStrategy permissionGrantingStrategy,
            AclAuthorizationStrategy aclAuthorizationStrategy) {

        return new SpringCacheBasedAclCache(
                new ConcurrentMapCache("aclCache"),
                permissionGrantingStrategy,
                aclAuthorizationStrategy);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache cache,
            AclAuthorizationStrategy authorizationStrategy,
            PermissionGrantingStrategy grantingStrategy) {

        return new BasicLookupStrategy(
                dataSource, cache, authorizationStrategy, grantingStrategy);
    }

    @Bean
    JdbcMutableAclService aclService(
            DataSource dataSource,
            LookupStrategy lookupStrategy,
            AclCache aclCache) {

        return new JdbcMutableAclService(
                dataSource, lookupStrategy, aclCache);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclService aclService) {

        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(new AclPermissionEvaluator(aclService));
        return handler;
    }
}
~~~

Each bean has a distinct responsibility:

- `aclAuthorizationStrategy`: decides who **is allowed to modify ACLs**. The `ACL_ADMIN` authority is only an illustrative choice and does not imply READ access on every domain object.
- `permissionGrantingStrategy`: how `Acl.isGranted` evaluates grant/deny ACEs.
- `aclCache`: cache within a single Spring Context, without distributed invalidation.
- `lookupStrategy`: reads ACLs over JDBC using the default strategy.
- `aclService`: `JdbcMutableAclService` instance for both reading and writing.
- `methodSecurityExpressionHandler`: wires `AclPermissionEvaluator` so SpEL `hasPermission` uses `AclService`; making the bean static ensures early handler configuration per Spring docs.

The imports here are deliberate: `AclPermissionEvaluator` is in package `org.springframework.security.acls`, whereas `AclAuthorizationStrategy` is in `org.springframework.security.acls.domain`. Both packages are **distinct from** `org.springframework.security.acls.model`.

### 6.6. Service to Create, Grant, Revoke, Check, and Delete ACLs

**`src/main/java/demo/acl/DocumentAclService.java`**

~~~java
package demo.acl;

import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.SidRetrievalStrategyImpl;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentAclService {
    private final AclService reader;
    private final MutableAclService writer;

    public DocumentAclService(AclService reader, MutableAclService writer) {
        this.reader = reader;
        this.writer = writer;
    }

    private ObjectIdentity documentId(long id) {
        return new ObjectIdentityImpl(Document.class.getName(), id);
    }

    @PreAuthorize("hasAuthority('ACL_ADMIN')")
    @Transactional
    public void grantReadToPrincipal(long id, String principal) {
        grantRead(id, new PrincipalSid(principal));
    }

    @PreAuthorize("hasAuthority('ACL_ADMIN')")
    @Transactional
    public void grantReadToAuthority(long id, String authority) {
        grantRead(id, new GrantedAuthoritySid(authority));
    }

    private void grantRead(long id, Sid sid) {
        ObjectIdentity oid = documentId(id);
        MutableAcl acl;

        try {
            acl = (MutableAcl) writer.readAclById(oid);
        }
        catch (NotFoundException missing) {
            acl = writer.createAcl(oid);
        }

        boolean alreadyGranted = acl.getEntries().stream().anyMatch(ace ->
                ace.getSid().equals(sid)
                && ace.getPermission().getMask() == BasePermission.READ.getMask()
                && ace.isGranting());

        if (!alreadyGranted) {
            acl.insertAce(
                    acl.getEntries().size(),
                    BasePermission.READ, sid, true);
            writer.updateAcl(acl);
        }
    }

    @PreAuthorize("hasAuthority('ACL_ADMIN')")
    @Transactional
    public void revokeReadFromPrincipal(long id, String principal) {
        MutableAcl acl;
        try {
            acl = (MutableAcl) writer.readAclById(documentId(id));
        }
        catch (NotFoundException missing) {
            return;
        }

        Sid sid = new PrincipalSid(principal);
        boolean changed = false;

        for (int i = acl.getEntries().size() - 1; i >= 0; i--) {
            var ace = acl.getEntries().get(i);
            if (ace.getSid().equals(sid)
                    && ace.getPermission().getMask() == BasePermission.READ.getMask()
                    && ace.isGranting()) {
                acl.deleteAce(i);
                changed = true;
            }
        }

        if (changed) {
            writer.updateAcl(acl);
        }
    }

    @PreAuthorize("hasAuthority('ACL_ADMIN')")
    @Transactional
    public void deleteAcl(long id) {
        writer.deleteAcl(documentId(id), false);
    }

    public boolean canRead(long id, Authentication authentication) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        List<Sid> sids =
                new SidRetrievalStrategyImpl().getSids(authentication);

        try {
            Acl acl = reader.readAclById(documentId(id), sids);
            return acl.isGranted(
                    List.of(BasePermission.READ), sids, false);
        }
        catch (NotFoundException noAclOrNoAce) {
            return false;
        }
    }
}
~~~

This service shows **both interfaces used in their proper roles**:

1. `writer` exposes `createAcl`/`updateAcl`/`deleteAcl`; `reader` is read-only.
2. Public grant/revoke methods carry `@PreAuthorize("hasAuthority('ACL_ADMIN')")`; callers without that authority cannot grant permissions.
3. The transaction wraps the mutation entry points, while the private helper only performs internal logic; do not expect annotations on a private method to be processed by Spring AOP.
4. `createAcl` is called when no ACL is found; `insertAce` mutates in memory; `updateAcl` persists.
5. When retrying the same grant, the example avoids adding a duplicate `READ:grant` ACE for the same SID. If a conflicting deny ACE exists, handling it must follow your own policy rather than automatically deleting the deny.
6. Revoking a principal's grant does not revoke grants from a role or parent ACL. To ensure a final deny decision, you must account for all grant sources.
7. `canRead` extracts SIDs from Authentication and queries `Acl.isGranted`; missing ACL/missing ACE is handled as false.

In a real application, obtain Authentication only from the verified security context; never let a request body construct an Authentication. Passing Authentication as a parameter in the sample is solely to make testing Alice and Bob separately straightforward.

### 6.7. Using ACLs via `hasPermission`

**`src/main/java/demo/acl/DocumentReader.java`**

~~~java
package demo.acl;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentReader {

    @PreAuthorize(
            "hasPermission(#id, 'demo.acl.Document', 'READ')")
    public String read(@P("id") long id) {
        // Illustration; production must load the real document and check tenant/state.
        return "document:" + id;
    }
}
~~~

The three-argument expression `hasPermission(#id, 'demo.acl.Document', 'READ')` uses the **ID + type** overload of `AclPermissionEvaluator`; the handler in section 6.5 wired the evaluator to the JDBC AclService. `@P("id")` avoids relying on compiler flags when reading parameter names.

The sample service does not yet have a business document repository, so it returns a string. **An ACL is an authorization boundary**, not a replacement for verifying that the document exists, belongs to the right tenant, and remains in a valid state at query/write time.

## 7. Integration Tests with a Real Spring Context and Database

The tests use HSQLDB with the initialized schema, Spring Method Security proxies, and `@WithMockUser`; they do not fake behavior with a hand-rolled `Map`.

**`src/test/java/demo/acl/DocumentAclIntegrationTest.java`**

~~~java
package demo.acl;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.AlreadyExistsException;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(classes = AclDemoApplication.class)
class DocumentAclIntegrationTest {

    @Autowired DocumentAclService documentAcl;
    @Autowired DocumentReader documentReader;
    @Autowired AclService reader;
    @Autowired MutableAclService writer;

    private Authentication user(String name, String... authorities) {
        List<SimpleGrantedAuthority> granted =
                java.util.Arrays.stream(authorities)
                        .map(SimpleGrantedAuthority::new)
                        .toList();
        return new UsernamePasswordAuthenticationToken(
                name, "demo-only", granted);
    }

    private ObjectIdentity oid(long id) {
        return new ObjectIdentityImpl(Document.class.getName(), id);
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void createReadAndRevokePrincipalGrant() {
        assertFalse(documentAcl.canRead(101L, user("alice")));

        documentAcl.grantReadToPrincipal(101L, "alice");
        assertTrue(documentAcl.canRead(101L, user("alice")));
        assertFalse(documentAcl.canRead(101L, user("bob")));

        // Re-running the same request does not create a duplicate grant ACE.
        documentAcl.grantReadToPrincipal(101L, "alice");
        Acl acl = reader.readAclById(oid(101L));
        assertEquals(1, acl.getEntries().size());

        documentAcl.revokeReadFromPrincipal(101L, "alice");
        assertFalse(documentAcl.canRead(101L, user("alice")));
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void grantToAuthorityAppliesToMultipleUsers() {
        documentAcl.grantReadToAuthority(202L, "ROLE_REVIEWER");

        assertTrue(documentAcl.canRead(
                202L, user("alice", "ROLE_REVIEWER")));
        assertTrue(documentAcl.canRead(
                202L, user("bob", "ROLE_REVIEWER")));
        assertFalse(documentAcl.canRead(
                202L, user("carol", "ROLE_VIEWER")));
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void createAclIsNotAnUpsert() {
        writer.createAcl(oid(303L));
        assertThrows(AlreadyExistsException.class,
                () -> writer.createAcl(oid(303L)));
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void deleteAclRemovesPersistedRecord() {
        documentAcl.grantReadToPrincipal(404L, "alice");
        assertTrue(documentAcl.canRead(404L, user("alice")));

        documentAcl.deleteAcl(404L);
        assertThrows(NotFoundException.class,
                () -> reader.readAclById(oid(404L)));
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void permissionEvaluatorProtectsMethod() {
        assertThrows(AccessDeniedException.class,
                () -> documentReader.read(505L));

        documentAcl.grantReadToPrincipal(505L, "acl-admin");
        assertEquals("document:505", documentReader.read(505L));
    }

    @Test
    @WithMockUser(username = "mallory", authorities = "DOC_READ")
    void userWithoutAclAdminCannotGrant() {
        assertThrows(AccessDeniedException.class,
                () -> documentAcl.grantReadToPrincipal(606L, "mallory"));

        assertThrows(NotFoundException.class,
                () -> reader.readAclById(oid(606L)));
    }
}
~~~

**Why are integration tests required?** A unit test of a policy class does not prove that the JDBC ACL schema, cache, expression handler, or AOP proxy are wired properly. With a Spring Context, these tests verify real grant/revoke persistence, object-scoped IDs, role/individual permissions, duplicate creation, deletion, and a real `@PreAuthorize` invocation.

The test methods use distinct IDs (101/202/303/404/505/606) so they do not accidentally depend on execution order. With a production DB, also test transaction isolation and revocation visibility across multiple nodes using caches.

### Running the Tests

On macOS/Linux:

~~~text
./gradlew test --tests demo.acl.DocumentAclIntegrationTest
~~~

On Windows:

~~~text
gradlew.bat test --tests demo.acl.DocumentAclIntegrationTest
~~~

The sample code does not print via `System.out.println`, so there is no fixed business stdout. Success means all assertions pass and Gradle completes the test task. Whenever changing Spring Boot/Security versions or the database dialect, recompile and re-run the tests before deploying the configuration to production.

## 8. Building the ACL Lifecycle Alongside the Resource Lifecycle

A real system should not create ACLs inside a controller through a loose sequence of non-transactional calls:

~~~text
Controller / Consumer (authenticated)
                  |
                  v
        DocumentApplicationService
                  |
              transaction
                  |
            +-----+------+
            |            |
     DocumentRepository  MutableAclService
            |            |
       domain tables   acl_sid, acl_class,
                       acl_object_identity,
                       acl_entry
~~~

**When creating a document:** verify the user is allowed to create, persist the Document to obtain its ID, construct the ObjectIdentity, call `createAcl`, add ACEs per policy, and call `updateAcl` within the appropriate transaction. If any step fails, roll back to avoid documents without ACLs or ACLs pointing to uncommitted objects.

**When sharing:** verify the actor has permission to share **that exact document** and the recipient is valid, read the current ACL, add the corresponding ACE, persist, audit, and handle cache updates.

**When revoking:** locate the exact ACE, delete it or add a deny per business rules, update the ACL, and check whether access remains via roles or parent inheritance. Removing a direct grant does not mean the user loses all access if a parent ACL still grants it.

**When deleting:** inspect child ACLs, choose `deleteChildren` intentionally, delete the ACL/document inside a transaction, and evict caches and remaining references.

## 9. Parent ACLs, ACE Order, and ACL Ownership

### Parent and Inheritance

An ACL can have a parent, such as a folder and its child documents:

~~~text
Folder#8 ACL
  ROLE_REVIEWER → READ:grant
       |
       | parent
       v
Document#202 ACL
  entriesInheriting = true
~~~

A child inherits entries from its parent only when the `entriesInheriting` flag and lookup strategy allow it. If the child already has a matching specific ACE, `PermissionGrantingStrategy` may reach a decision before checking the parent. Do not infer "an admin can read all children" from the fact that the admin can manage the parent ACL.

### Order and Deny

`DefaultPermissionGrantingStrategy` evaluates permissions and SIDs in order, examining grant/deny ACEs and optionally continuing to the parent if inconclusive. Do not oversimplify this to "at least one grant means allow" or "any deny wins regardless of order." When a principal has both a user SID and role SIDs, test overlapping ACE cases against the actual strategy.

### ACL Owner Is Not a READ Owner

`Acl.getOwner()` records the SID with ACL ownership/administration rights per the strategy. It does not automatically guarantee `Acl.isGranted(READ, ...)` returns true for the owner. If business requirements dictate that owners can read their documents, encode that in policy or grant the corresponding ACE.

## 10. Caching, Lookup, and Performance

### Why `BasicLookupStrategy` Is Needed

`JdbcAclService` delegates lookups to `LookupStrategy`. `BasicLookupStrategy` uses SQL queries, batching, and `AclCache` to avoid rebuilding full ACLs unnecessarily on every check.

When checking multiple ObjectIdentities:

~~~java
// Illustration when reader, objectIdentities, and sids already exist.
Map<ObjectIdentity, Acl> found =
        reader.readAclsById(objectIdentities, sids);
~~~

Even when batching, you must still call `isGranted` on the **exact** ObjectIdentity. For pagination and very large datasets, consider filtering permissions directly at the repository query level instead of loading tens of thousands of objects and post-filtering.

### Cache Invalidation

Suppose node A caches an ACL granting READ to Alice, and node B deletes that ACE in the database; if node A's cache is not invalidated, Alice may temporarily still be granted access. `JdbcMutableAclService` manages invalidation for the cache instance it knows about, but **does not automatically ensure** that other nodes or applications see the change.

A distributed system needs proper cache invalidation/versioning/TTL, as well as a strategy for refreshing auth sessions/JWTs when role memberships change. Do not confuse "the DB changed" with "every request immediately sees the new permissions."

### Transactions Alone Do Not Prevent Lost Updates

The JDBC implementation of `updateAcl` may delete and rewrite all ACEs. If two administrators concurrently read the old ACL and update from two different snapshots, one administrator's changes can overwrite the other's. `@Transactional` protects the atomicity of **a single** write, not serialization between two concurrent writers. Consider locking, versioning, and retry handling at the use-case layer.

## 11. Multi-Tenancy, Auditing, and Security Boundaries

### Multi-Tenancy

`ObjectIdentityImpl("demo.acl.Document", 101L)` contains only a type and an ID. If tenants A and B both have a document with ID 101 in separate databases or logical partitions, never share ACL tables without explicitly partitioning object identities. Likewise, `PrincipalSid("alice")` does not inherently carry a tenant. A user with the same username in another tenant could match the SID if principal naming does not guarantee uniqueness.

Use globally immutable user IDs, uniquely qualified resource IDs, or tenant-partitioned ACLs, and always derive the tenant from an authenticated source. Never trust a self-declared tenant in an HTTP header.

### ACL Administration Rights and Escalation

A user with `READ` on a document must not be able to call `grantReadToAuthority` to grant access to an entire group unless business rules permit it. `@PreAuthorize("hasAuthority('ACL_ADMIN')")` in the example illustrates only one gate; production may require the actor to be a tenant admin, hold share rights on that exact ObjectIdentity, and be restricted from granting excessive permissions.

Add auditing: who granted, to whom, which object, which permission, effective timestamp, transaction ID, and outcome. Do not log tokens or sensitive data in permission reports.

### ACL Permissions and Business Policies Can Differ

An ACL may have `READ:grant`, yet if the document is under legal hold, deleted, or in another tenant, the application may still need to deny access. `Acl.isGranted` answers based on ACEs and does not inherently know every document invariant. Conversely, `@PostAuthorize` checks after the method body executes, so it cannot prevent side effects that have already happened.

## 12. Common Pitfalls

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Error `Table not found: ACL_SID` | Schema not executed, wrong datasource | Check `schema.sql` and migrations |
| `call identity()` error on PostgreSQL/H2 | Using HSQLDB default query | Set identity queries matching dialect and schema |
| `AlreadyExistsException` when creating ACL | ObjectIdentity already has an ACL | Read and update instead, or handle races safely |
| `NotFoundException` on read | Missing ACL or wrong type/ID | Fail closed, inspect lifecycle |
| `NotFoundException` on `isGranted` | ACL exists but no matching ACE | Do not return allow; verify SID/mask |
| `UnloadedSidException` | Lookup loaded only a SID subset | Load required SIDs and check strategy |
| Granted but still no access | Forgot `updateAcl`, wrong SID or mask | Persist, read back, and test `isGranted` |
| Revoked user still has READ | Role grant or parent inheritance active | Account for all grant sources |
| `hasPermission` does not run | Method Security not enabled or missing handler | Configure `@EnableMethodSecurity` and `AclPermissionEvaluator` |
| Unauthorized user modifies ACL | Admin endpoint lacks guard or bypasses proxy | Secure public service method, test denial |
| Cache still holds old permissions | Missing invalidation across nodes | Evict/broadcast/version per architecture |
| Two writers drop each other's ACEs | Race/lost update in `updateAcl` | Transaction + locking/versioning |
| Deleting parent ACL fails | Child ACLs exist | Check `ChildrenExistException` and ACL tree |
| HSQLDB tests pass, production fails | Different dialect/SQL isolation | Run integration tests against target DB |
| User in another tenant gets access | SID/ObjectIdentity not tenant-scoped | Global IDs or tenant-partitioned ACLs |
| Document created without an ACL | Domain and ACL lifecycles not transactional | Use an application service with proper rollback |

## 13. Review Checklist and Exercises

Before completing the implementation:

1. Does the ACL schema have all four tables, FKs, unique constraints, indexes, and identity definitions matching the database?
2. Is `JdbcMutableAclService` configured with the right `DataSource`, `BasicLookupStrategy`, and `AclCache`?
3. Are `createAcl`/`updateAcl`/`deleteAcl` and `readAclById`/`readAclsById` tested?
4. Is `MutableAclService` injected only in administrative components, and is the actor authorized before changing permissions?
5. Are missing ACLs and missing ACEs handled as deny rather than allow?
6. Are `PrincipalSid` and `GrantedAuthoritySid` properly distinguished?
7. Are role prefixes, tenants, ObjectIdentity types, and IDs validated?
8. Are ACL inheritance, denies, parent deletion, and revocation tested?
9. Is `updateAcl` protected by a transaction and a concurrency strategy?
10. Does caching/invalidation work across multiple nodes?
11. Is `@PreAuthorize("hasPermission(...)")` tested with an unauthorized user through a real proxy?
12. Does the ACL policy coordinate properly with document state and real SQL transactions?

**Exercise 1:** Add `grantWriteToPrincipal` for `BasePermission.WRITE`. Test that Alice with only READ does not implicitly gain WRITE, and a user with WRITE does not implicitly gain DELETE.

**Exercise 2:** Give Bob `ROLE_REVIEWER` and add an authority-based READ ACE on Document#707. Prove that another reviewer can read that same object, but not Document#101.

**Exercise 3:** Add a deny ACE for Alice on an object that already has a role grant. Test with `Acl.isGranted` and vary SID/ACE ordering to observe the real strategy. Do not use `anyMatch` to fake the result.

**Exercise 4:** Create a parent ACL for Folder#8 and a child ACL for Document#808. Toggle `entriesInheriting`, try `deleteAcl(parent,false)`, and explain when `deleteChildren=true` is needed.

**Exercise 5:** Run the integration tests on PostgreSQL using Testcontainers, swapping `schema.sql` and identity queries. Specifically test create/update/revoke and rollback on SQL errors.

**Exercise 6:** Run two concurrent transactions updating the same ObjectIdentity. Add versioning or locking to ensure neither writer drops the other's ACEs.

**Exercise 7:** Design ACLs for two tenants sharing identical usernames and document IDs. Propose an ID/SID strategy preventing cross-tenant reads; test both individual and group permissions.

**Completion criteria:** explain the difference between the read contract, the mutation contract, and the JDBC implementation; wire `DataSource`/`LookupStrategy`/`AclCache` correctly; create, update, and read real ACLs; apply `Acl.isGranted` or `hasPermission` to make decisions; fail closed on missing ACLs/ACEs; and understand the limits of transactions, caching, multi-tenancy, and JDBC dialects.

## Official References

- Spring Security – Domain Object Security (ACLs), components and JDBC configuration: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html
- Spring Security – Database Schema, HSQLDB DDL and PostgreSQL SQL: https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html
- Spring Security – AclService API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/AclService.html
- Spring Security – MutableAclService API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/MutableAclService.html
- Spring Security – JdbcMutableAclService API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html
- Spring Security – BasicLookupStrategy API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/BasicLookupStrategy.html
- Spring Security – AclPermissionEvaluator API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/AclPermissionEvaluator.html

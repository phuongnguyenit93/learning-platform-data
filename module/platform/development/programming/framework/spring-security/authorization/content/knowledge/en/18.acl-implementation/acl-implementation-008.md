# Deleting Objects, Deleting ACLs, and Transactional Consistency in Spring Security

## 1. The Problem: Deleting a Document Does Not Guarantee Deleting Access Rights

Suppose an application has a `Document#101` in tenant `t1`, a `document` business row, an `acl_object_identity` row, and an ACE in `acl_entry` granting Bob READ access. When Alice requests to delete the document, what happens if only the business table row is deleted?

```java
documentRepository.deleteById(101L);
```

This line is an API illustration, not a standalone compilable program. **The ACL can still remain** because the default Spring Security ACL schema does not place a foreign key from `acl_object_identity.object_id_identity` to every domain table. Orphan ACL rows can pollute audits/caches and are especially dangerous if domain IDs are reused: a new document carrying the same `ObjectIdentity` could inherit old ACEs.

The reverse case is also dangerous:

```java
mutableAclService.deleteAcl(
    new ObjectIdentityImpl(Document.class, 101L), false
);
```

This deletes **ACL data** without running `DELETE FROM document`. If the subsequent domain delete fails and the two steps do not share a transaction, the business record stays alive while its ACL permissions vanish.

**Lesson objective:** delete the domain object and its ACL **together or roll them back together**, distinguishing child ACLs from child domain objects, authorizing the actor, and handling failures, caches, and external side effects. Content applies to Spring Security ACL 6.5.x, Java 17, and Spring Boot 3.5.x.

## 2. Two Separate Lifecycles

Spring Security ACL uses four tables:

| Table | What does it store? |
|---|---|
| `acl_sid` | SID of a principal or authority eligible to receive permissions |
| `acl_class` | Protected Java/domain object type |
| `acl_object_identity` | ACL for one `(type, domain ID)` instance; holds owner, parent, and inheritance flag |
| `acl_entry` | ACEs: SID, permission mask, granting/denying, order, and audit flags |

Example:

```text
document:
  id=101, tenant=t1, owner=alice, title=Leaf

acl_class:
  id=7, class=com.example.acldelete.Document

acl_object_identity:
  id=11, object_id_class=7, object_id_identity=101,
  parent_object=NULL, owner_sid=1, entries_inheriting=FALSE

acl_entry:
  id=101, acl_object_identity=11, ace_order=0,
  sid=2 (bob), mask=1 (READ), granting=TRUE
```

Distinguish the **ACL primary key** `acl_object_identity.id=11` from the **domain ID** `object_id_identity=101`. `acl_entry.acl_object_identity` references 11, not `document.id=101` directly. There is no default FK forcing a domain row and its ACL to appear or disappear together; the service must coordinate them.

### 2.1. Two Broken States

| State | Cause | Consequence |
|---|---|---|
| Domain gone, ACL remains | Deleted only `document` | Orphan ACL; old ACEs can affect reused IDs |
| Domain remains, ACL gone | Deleted ACL, then domain delete failed outside a transaction | `hasPermission` may deny due to missing ACL |
| Both remain | Deletion blocked or rolled back cleanly | Data/ACL remain consistent with initial state |
| Both gone | Authorized physical deletion committed cleanly | Desired outcome for complete physical deletion |

The default ACL schema does not automatically create or delete ACLs when a JPA/JDBC repository saves or deletes domain objects. Spring Security recommends integrating ACL lifecycle management at the service layer.

### 2.2. When Should an ACL Not Be Deleted?

**Soft delete** typically only sets `deleted_at`/`status=DELETED` for recovery or retention compliance. You may keep the ACL for history, yet every access path must reject soft-deleted content. `AclPermissionEvaluator` checks only ACLs; it does not inherently know a domain record is marked deleted. For documents under legal hold, hard deletion must typically be denied regardless of owner or ACL permissions.

## 3. MutableAclService.deleteAcl and the deleteChildren Flag

Spring Security 6.5 declares:

```java
void deleteAcl(
    ObjectIdentity objectIdentity,
    boolean deleteChildren
) throws ChildrenExistException;
```

This is an abbreviated API signature. `ObjectIdentityImpl(Document.class, id)` maps the full type and ID; it must match how ACLs were created and `acl_class.class`. Do not confuse `"Document"` with the FQCN if lookups are configured with the FQCN.

### 3.1. deleteChildren=false

```java
ObjectIdentity oid = new ObjectIdentityImpl(Document.class, 101L);
mutableAclService.deleteAcl(oid, false);
```

For an ACL with no children, the JDBC implementation deletes its ACEs and then deletes the `acl_object_identity` row. Shared `acl_class` or `acl_sid` metadata may remain; **do not delete SIDs/classes just because one object disappeared**.

If the ACL has children, the API throws `ChildrenExistException`. This protects ACL hierarchy integrity; inside a transaction, this unchecked exception can trigger rollback.

### 3.2. deleteChildren=true

```java
mutableAclService.deleteAcl(oid, true);
```

This allows deleting the **child ACL subtree**. It **does not** delete domain children, files, search indexes, emails, queue messages, or data in another database. If `Document#100` has child ACL `Document#102`, `deleteAcl(oid(100),true)` may delete ACLs for 100 and 102 while leaving both `document` rows intact. Always test this explicitly.

**Do not pass `true` just to "avoid `ChildrenExistException`."** A genuine subtree delete must collect all descendants, verify permissions on every object, check legal holds and tenant scope, delete domain rows in FK order (typically leaves before parents), and delete the ACL subtree in the same transaction.

### 3.3. Exceptions to Distinguish

| Exception | What it reflects | Handling |
|---|---|---|
| `ChildrenExistException` | Parent ACL still has child ACLs when called with `false` | Reject, reparent, or implement full subtree deletion |
| ACL `NotFoundException` | ObjectIdentity has no ACL | Fail closed; do not silently delete domain |
| `DataIntegrityViolationException` | DB FK/constraint blocks deletion | Check domain children, FKs, or DML order |
| `AccessDeniedException` | Actor lacks deletion rights | Do not execute target method |
| Runtime exception after DML steps | Transaction failure | Rolls back if exception reaches transaction interceptor before commit |

`AclAuthorizationStrategy` governs permission to modify `MutableAcl` instances. Never assume `MutableAclService.deleteAcl` enforces tenant, owner, retention, or business DELETE policies. **The application must verify domain deletion rights explicitly**.

## 4. Wrapping Both ACL and Domain in One Transaction

Architecturally safe pattern:

```java
@Transactional
@PreAuthorize("@deletePolicy.canDelete(authentication, #id)")
public void deleteDocument(@P("id") Long id) {
    Document document = repository.require(id);
    ObjectIdentity oid = new ObjectIdentityImpl(Document.class, id);

    aclService.readAclById(oid);
    aclService.deleteAcl(oid, false);

    int changed = repository.deleteMatching(document);
    if (changed != 1) {
        throw new IllegalStateException("Record changed");
    }
}
```

This is a **service pattern** needing beans, imports, and domain classes to run. How it works:
1. Authorize the caller before the target method runs.
2. Load the canonical domain record and verify the ACL exists.
3. Delete the ACL and ACEs.
4. Delete the domain row with trusted owner/tenant predicates.
5. Commit both; if an exception escapes before commit, roll back both.

`@Transactional` succeeds when **both `JdbcMutableAclService` and the domain repository share the same DataSource/transaction manager** without `REQUIRES_NEW` or independent auto-commit. If ACLs live in database A and domain records in database B, an annotation bound to manager A does not create an atomic transaction across both.

### 4.1. Why Not Delete Domain and Immediately Return HTTP 200?

An HTTP response is not proof of DB consistency. Verify after commit:
- The domain row is gone.
- The ACL object identity is gone.
- The ACL's ACEs are gone.
- Any child ACLs/domain children are handled per policy.
- Caches no longer return permissions for the deleted object.
- External side effects are coordinated separately.

### 4.2. Which Deletion Order Is Right?

For a simple leaf ACL, you can delete the ACL first and then the domain row in the **same transaction**. If `deleteAcl(false)` rejects due to child ACLs, the domain row remains untouched. If the domain DELETE fails after deleting the ACL, rollback restores the ACL.

However, specific FKs may dictate a different order; what matters is sharing the transaction. Never split into two transactions hoping a later exception will undo an earlier commit.

### 4.3. Rollback Rules and Catching Exceptions

In Spring Framework 6.x, rollback happens by default on `RuntimeException` and `Error` escaping to the transaction interceptor. Checked exceptions usually require `rollbackFor`:

```java
@Transactional(rollbackFor = Exception.class)
public void deleteWithCheckedFailure() throws Exception {
    // Checked Exception errors escaping also trigger rollback
}
```

If you catch an exception and return normally, the transaction advice may not know to roll back. Never write:

```java
@Transactional
public void unsafeDelete() {
    try {
        aclService.deleteAcl(oid, false);
    } catch (Exception ex) {
        logger.warn("ACL error", ex);
    }
    repository.deleteById(id);
}
```

This is an **anti-pattern** (non-standalone without beans/variables). It can delete the domain record even when ACL deletion fails. When errors occur, fail closed by letting the exception propagate out of the transaction or explicitly marking rollback-only if a structured error flow applies.

### 4.4. AOP, TOCTOU, and Concurrency

In Spring Security 6.x, `@PreAuthorize` typically runs outside the transaction advice under default ordering; policy may be checked before the transaction begins. If owner/tenant changes between authorization and DELETE, a **TOCTOU** race arises. The runnable example below rechecks inside the transaction and uses ID/tenant/owner predicates, while production may need row locks, versioning, higher isolation, or stricter conditional updates depending on risk.

`@Transactional` and `@PreAuthorize` will not run if callers bypass the Spring proxy via self-invocation. Never instantiate services with `new` and expect annotations to apply.

## 5. Child ACL Relationships Differ from Child Domain Relationships

```text
Business domain tree             ACL inheritance tree

Document#100                     ACL(Document#100)
   └── Document#102                 └── ACL(Document#102)
       parent_id=100                  parent_object=10
```

This lesson aligns both trees for clarity, yet Spring Security does not force them to match. `document.parent_id` has a business FK; `acl_object_identity.parent_object` has an ACL self-FK. Setting `entries_inheriting=true` on a child lets ACL policy consult parent ACEs, without creating a domain relationship.

When deleting a parent:
- `deleteAcl(parent,false)` throws `ChildrenExistException` if child ACLs remain.
- SQL `DELETE document(parent)` may throw `DataIntegrityViolationException` if domain children remain.
- `deleteAcl(parent,true)` cleans up the ACL subtree, **not** the domain subtree.
- To keep children while deleting a parent, consider controlled reparenting of both ACL and domain children, re-checking permissions after inheritance changes.

In multi-tenant systems, never delete a child ACL belonging to another tenant simply because you can access the parent ACL; verify every descendant resource before subtree deletion.

## 6. Java 17 + Spring Boot 3.5.6 + HSQLDB: Runnable Project

This example uses an in-memory HSQLDB database and real JDBC for **both domain tables and Spring Security ACL**. It tests successful deletion, intentional rollback, ACL/domain children, orphans, and caller authorization—requiring no web server or JWTs.

### 6.1. File Tree

```text
acl-delete-consistency/
  pom.xml
  src/main/java/com/example/acldelete/
    AclDeleteApplication.java
    Document.java
    DocumentRepository.java
    DeletePolicy.java
    AclConfig.java
    DocumentDeletionService.java
    DocumentReadService.java
  src/main/resources/
    schema.sql
    data.sql
  src/test/java/com/example/acldelete/
    AclDeletionIntegrationTest.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>acl-delete-consistency</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-aop</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-acl</artifactId>
    </dependency>
    <dependency>
      <groupId>org.hsqldb</groupId>
      <artifactId>hsqldb</artifactId>
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
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

Spring Boot 3.5.6 manages compatible Spring Security 6.5.x dependencies; do not force a separate version on `spring-security-acl`. The demo uses no Spring Security 7 features.

### 6.3. schema.sql

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE document (
  id BIGINT PRIMARY KEY,
  tenant_id VARCHAR(64) NOT NULL,
  owner_username VARCHAR(100) NOT NULL,
  parent_id BIGINT,
  title VARCHAR(255) NOT NULL,
  FOREIGN KEY(parent_id) REFERENCES document(id)
);

CREATE TABLE tenant_membership (
  tenant_id VARCHAR(64) NOT NULL,
  username VARCHAR(100) NOT NULL,
  PRIMARY KEY(tenant_id, username)
);

CREATE TABLE tenant_admin (
  tenant_id VARCHAR(64) NOT NULL,
  username VARCHAR(100) NOT NULL,
  PRIMARY KEY(tenant_id, username),
  FOREIGN KEY(tenant_id, username)
    REFERENCES tenant_membership(tenant_id, username)
);

CREATE TABLE acl_sid (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 5000)
    PRIMARY KEY,
  principal BOOLEAN NOT NULL,
  sid VARCHAR_IGNORECASE(100) NOT NULL,
  UNIQUE(sid, principal)
);

CREATE TABLE acl_class (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 5000)
    PRIMARY KEY,
  class VARCHAR_IGNORECASE(100) NOT NULL,
  UNIQUE(class)
);

CREATE TABLE acl_object_identity (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 5000)
    PRIMARY KEY,
  object_id_class BIGINT NOT NULL,
  object_id_identity VARCHAR_IGNORECASE(36) NOT NULL,
  parent_object BIGINT,
  owner_sid BIGINT,
  entries_inheriting BOOLEAN NOT NULL,
  UNIQUE(object_id_class, object_id_identity),
  FOREIGN KEY(object_id_class) REFERENCES acl_class(id),
  FOREIGN KEY(parent_object) REFERENCES acl_object_identity(id),
  FOREIGN KEY(owner_sid) REFERENCES acl_sid(id)
);

CREATE TABLE acl_entry (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 5000)
    PRIMARY KEY,
  acl_object_identity BIGINT NOT NULL,
  ace_order INTEGER NOT NULL,
  sid BIGINT NOT NULL,
  mask INTEGER NOT NULL,
  granting BOOLEAN NOT NULL,
  audit_success BOOLEAN NOT NULL,
  audit_failure BOOLEAN NOT NULL,
  UNIQUE(acl_object_identity, ace_order),
  FOREIGN KEY(acl_object_identity) REFERENCES acl_object_identity(id),
  FOREIGN KEY(sid) REFERENCES acl_sid(id)
);
```

This is an **HSQLDB** schema with default ACL columns/relationships. PostgreSQL, MySQL, SQL Server, and Oracle use different identity syntax and ID-query configuration. Production should use migrations and DDL matching your deployed ACL version. The HSQLDB schema is chosen to test the real Spring Security JDBC implementation rather than mocking ACLs with a map.

### 6.4. data.sql

**`src/main/resources/data.sql`**

```sql
INSERT INTO document VALUES (100,'t1','alice',NULL,'Root');
INSERT INTO document VALUES (101,'t1','alice',NULL,'Leaf');
INSERT INTO document VALUES (102,'t1','alice',100,'Child');
INSERT INTO document VALUES (200,'t2','carol',NULL,'Other tenant');
INSERT INTO document VALUES (300,'t1','alice',NULL,'Missing ACL');

INSERT INTO tenant_membership VALUES ('t1','alice');
INSERT INTO tenant_membership VALUES ('t1','bob');
INSERT INTO tenant_membership VALUES ('t1','manager1');
INSERT INTO tenant_membership VALUES ('t2','carol');
INSERT INTO tenant_membership VALUES ('t2','dave');

INSERT INTO tenant_admin VALUES ('t1','manager1');

INSERT INTO acl_sid(id,principal,sid) VALUES (1,TRUE,'alice');
INSERT INTO acl_sid(id,principal,sid) VALUES (2,TRUE,'bob');
INSERT INTO acl_sid(id,principal,sid) VALUES (3,TRUE,'carol');
INSERT INTO acl_sid(id,principal,sid) VALUES (4,TRUE,'manager1');

INSERT INTO acl_class(id,class)
VALUES (7,'com.example.acldelete.Document');

INSERT INTO acl_object_identity(
  id,object_id_class,object_id_identity,
  parent_object,owner_sid,entries_inheriting
) VALUES (10,7,'100',NULL,1,FALSE);
INSERT INTO acl_object_identity(
  id,object_id_class,object_id_identity,
  parent_object,owner_sid,entries_inheriting
) VALUES (11,7,'101',NULL,1,FALSE);
INSERT INTO acl_object_identity(
  id,object_id_class,object_id_identity,
  parent_object,owner_sid,entries_inheriting
) VALUES (12,7,'102',10,1,TRUE);
INSERT INTO acl_object_identity(
  id,object_id_class,object_id_identity,
  parent_object,owner_sid,entries_inheriting
) VALUES (20,7,'200',NULL,3,FALSE);

-- Bob reads leaf #101.
INSERT INTO acl_entry(
  id,acl_object_identity,ace_order,sid,
  mask,granting,audit_success,audit_failure
) VALUES (101,11,0,2,1,TRUE,FALSE,FALSE);

-- Alice reads root #100.
INSERT INTO acl_entry(
  id,acl_object_identity,ace_order,sid,
  mask,granting,audit_success,audit_failure
) VALUES (102,10,0,1,1,TRUE,FALSE,FALSE);

-- Bob reads child #102.
INSERT INTO acl_entry(
  id,acl_object_identity,ace_order,sid,
  mask,granting,audit_success,audit_failure
) VALUES (103,12,0,2,1,TRUE,FALSE,FALSE);

-- Carol reads document #200.
INSERT INTO acl_entry(
  id,acl_object_identity,ace_order,sid,
  mask,granting,audit_success,audit_failure
) VALUES (104,20,0,3,1,TRUE,FALSE,FALSE);
```

There are five domain rows yet only four ACLs: `Document#300` intentionally lacks an ACL to test fail-closed behavior. Document#102's ACL is a child of Document#100's ACL, not Document#101's. Seeded ACL IDs are below 5000, separate from auto-generated IDs.

### 6.5. Application and Domain

**`src/main/java/com/example/acldelete/AclDeleteApplication.java`**

```java
package com.example.acldelete;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AclDeleteApplication {
    public static void main(String[] args) {
        SpringApplication.run(AclDeleteApplication.class, args);
    }
}
```

**`src/main/java/com/example/acldelete/Document.java`**

```java
package com.example.acldelete;

public record Document(
        Long id,
        String tenantId,
        String owner,
        Long parentId,
        String title) {
    public Long getId() {
        return id;
    }
}
```

### 6.6. DocumentRepository

**`src/main/java/com/example/acldelete/DocumentRepository.java`**

```java
package com.example.acldelete;

import java.util.List;
import java.util.NoSuchElementException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {
    private final JdbcTemplate jdbc;

    public DocumentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Document find(Long id) {
        if (id == null) {
            return null;
        }
        List<Document> rows = jdbc.query(
            """
            SELECT id,tenant_id,owner_username,parent_id,title
            FROM document WHERE id = ?
            """,
            (rs, n) -> new Document(
                rs.getLong("id"),
                rs.getString("tenant_id"),
                rs.getString("owner_username"),
                rs.getObject("parent_id", Long.class),
                rs.getString("title")
            ),
            id
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Document require(Long id) {
        Document d = find(id);
        if (d == null) {
            throw new NoSuchElementException("Missing document");
        }
        return d;
    }

    public int deleteMatching(Document d) {
        return jdbc.update(
            """
            DELETE FROM document
            WHERE id=? AND tenant_id=? AND owner_username=?
            """,
            d.id(), d.tenantId(), d.owner()
        );
    }
}
```

`deleteMatching` applies tenant/owner predicates from the canonical record (never from headers/requests) and returns affected rows so the service detects concurrent record modifications. This does **not** yet replace row locks, versioning, or higher isolation when concurrent requests modify ACLs/owners.

### 6.7. DeletePolicy: Only the Real Owner or Tenant Admin May Delete

**`src/main/java/com/example/acldelete/DeletePolicy.java`**

```java
package com.example.acldelete;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component("deletePolicy")
public class DeletePolicy {
    private final JdbcTemplate jdbc;
    private final DocumentRepository docs;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public DeletePolicy(JdbcTemplate jdbc, DocumentRepository docs) {
        this.jdbc = jdbc;
        this.docs = docs;
    }

    public boolean inTenant(Authentication auth, Long id) {
        if (auth == null || !auth.isAuthenticated()
                || trust.isAnonymous(auth)) {
            return false;
        }
        Document d = docs.find(id);
        if (d == null) {
            return false;
        }
        String username = auth.getName();
        String tenant = d.tenantId();

        Integer count = jdbc.queryForObject(
            """
            SELECT COUNT(*) FROM tenant_membership
            WHERE tenant_id=? AND username=?
            """,
            Integer.class, tenant, username
        );

        return count != null && count > 0
            && hasAuthority(auth, "tenant:" + tenant);
    }

    public boolean canDelete(Authentication auth, Long id) {
        if (!inTenant(auth, id)) {
            return false;
        }

        Document d = docs.find(id);
        String username = auth.getName();

        if (username.equals(d.owner())) {
            return true;
        }

        Integer admins = jdbc.queryForObject(
            """
            SELECT COUNT(*) FROM tenant_admin
            WHERE tenant_id=? AND username=?
            """,
            Integer.class, d.tenantId(), username
        );

        return admins != null && admins > 0
            && hasAuthority(auth, "ROLE_TENANT_ADMIN");
    }

    private static boolean hasAuthority(
            Authentication auth, String required) {
        for (GrantedAuthority authority : auth.getAuthorities()) {
            if (required.equals(authority.getAuthority())) {
                return true;
            }
        }
        return false;
    }
}
```

The policy permits only:
- an owner who is an active tenant member with the matching tenant authority; or
- a tenant admin holding **both** `ROLE_TENANT_ADMIN` and a server-side binding in `tenant_admin` for the current tenant.

Thus, a user spoofing an authority in a test Authentication without database membership/binding is still denied. Production must ensure Authentication comes from a trusted provider and add retention/legal hold checks plus tenant/owner transfer handling.

### 6.8. ACL Configuration

**`src/main/java/com/example/acldelete/AclConfig.java`**

```java
package com.example.acldelete;

import javax.sql.DataSource;
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
import org.springframework.security.acls.jdbc.LookupStrategy;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration
@EnableMethodSecurity
public class AclConfig {
    @Bean
    static MethodSecurityExpressionHandler expressionHandler(
            AclPermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService service) {
        return new AclPermissionEvaluator(service);
    }

    @Bean
    MutableAclService mutableAclService(
            DataSource dataSource,
            LookupStrategy lookup,
            AclCache cache) {
        return new JdbcMutableAclService(dataSource, lookup, cache);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache cache,
            AclAuthorizationStrategy authorization,
            PermissionGrantingStrategy granting) {
        return new BasicLookupStrategy(
            dataSource, cache, authorization, granting
        );
    }

    @Bean
    AclCache aclCache(
            PermissionGrantingStrategy granting,
            AclAuthorizationStrategy authorization) {
        return new SpringCacheBasedAclCache(
            new ConcurrentMapCache("aclCache"),
            granting,
            authorization
        );
    }

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_SYSTEM_ADMIN")
        );
    }

    @Bean
    PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
            new ConsoleAuditLogger()
        );
    }
}
```

`@EnableMethodSecurity` enables `@PreAuthorize`; `AclPermissionEvaluator` evaluates `hasPermission(...)` on the read service. `BasicLookupStrategy` and `SpringCacheBasedAclCache` load and cache ACLs. `JdbcMutableAclService` uses the **same DataSource** as `JdbcTemplate` so a single transaction guards both ACL DML and domain DML.

`ROLE_ACL_SYSTEM_ADMIN` is only the system-wide authority of the ACL administration strategy here, not a replacement for tenant/owner policies. The demo grants this authority to no user.

### 6.9. DocumentDeletionService: Real Transaction

**`src/main/java/com/example/acldelete/DocumentDeletionService.java`**

```java
package com.example.acldelete;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentDeletionService {
    private final MutableAclService acls;
    private final DocumentRepository docs;
    private final DeletePolicy policy;

    public DocumentDeletionService(
            MutableAclService acls,
            DocumentRepository docs,
            DeletePolicy policy) {
        this.acls = acls;
        this.docs = docs;
        this.policy = policy;
    }

    @Transactional
    @PreAuthorize("@deletePolicy.canDelete(authentication, #id)")
    public void deleteDocument(
            @P("id") Long id, boolean simulateFailure) {

        Document d = docs.require(id);

        // Recheck inside transaction to reduce TOCTOU.
        if (!policy.canDelete(
                SecurityContextHolder.getContext().getAuthentication(),
                id)) {
            throw new AccessDeniedException("Permission changed");
        }

        ObjectIdentity identity =
            new ObjectIdentityImpl(Document.class, id);

        // Fail-closed if document exists without an ACL.
        acls.readAclById(identity);

        // Delete only a leaf ACL; do not delete descendant ACLs.
        acls.deleteAcl(identity, false);

        // Domain DELETE and ACL DELETE run in the same JDBC transaction.
        int affected = docs.deleteMatching(d);
        if (affected != 1) {
            throw new IllegalStateException("Document changed");
        }

        // Failure switch for testing rollback; remove in production.
        if (simulateFailure) {
            throw new IllegalStateException(
                "Simulated failure after both deletes"
            );
        }
    }
}
```

**Analysis:** `@PreAuthorize` denies before the body executes. `@Transactional` wraps both JDBC operations; an unchecked exception before commit triggers rollback. `readAclById` ensures the domain is not deleted if the ACL is missing. `deleteAcl(false)` rejects if child ACLs exist. `deleteMatching` requires exactly one domain row to be deleted. The `simulateFailure` flag is solely for testing and **must not exist in production APIs**.

Important: if `deleteAcl` were moved to a method with `REQUIRES_NEW`, the ACL could commit early and an outer rollback would not restore it. If two DataSources are used, inspect the transaction manager rather than assuming a single transaction can roll back across DBs.

### 6.10. DocumentReadService: ACL and Tenant Decide Together

**`src/main/java/com/example/acldelete/DocumentReadService.java`**

```java
package com.example.acldelete;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentReadService {
    private final DocumentRepository docs;

    public DocumentReadService(DocumentRepository docs) {
        this.docs = docs;
    }

    @PreAuthorize(
        "@deletePolicy.inTenant(authentication, #id) and " +
        "hasPermission(#id, 'com.example.acldelete.Document', " +
        "T(org.springframework.security.acls.domain.BasePermission).READ)"
    )
    public String read(@P("id") Long id) {
        return docs.require(id).title();
    }
}
```

`hasPermission` alone does not enforce tenant isolation; we combine `inTenant` first. `@P("id")` helps SpEL resolve `#id` even when Java parameter-name metadata is absent from bytecode.

## 7. Integration Tests: Rollback, Children, Orphans, and Denial

Each test starts a fresh embedded database via `@DirtiesContext(AFTER_EACH_TEST_METHOD)`. This is slower yet easy to verify because no test needs to clean up another test's ACL cache or rows. Do not put `@Transactional` on the test class, because an outer test transaction can mask the service's real commit and rollback behavior.

**`src/test/java/com/example/acldelete/AclDeletionIntegrationTest.java`**

```java
package com.example.acldelete;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.model.ChildrenExistException;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class AclDeletionIntegrationTest {
    @Autowired DocumentDeletionService deletion;
    @Autowired DocumentReadService reader;
    @Autowired MutableAclService acls;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager transactionManager;

    private static ObjectIdentity oid(long id) {
        return new ObjectIdentityImpl(Document.class, id);
    }

    private int domainRows(long id) {
        Integer n = jdbc.queryForObject(
            "SELECT COUNT(*) FROM document WHERE id = ?",
            Integer.class, id);
        return n.intValue();
    }

    private int aclRows(long id) {
        Integer n = jdbc.queryForObject(
            """
            SELECT COUNT(*)
            FROM acl_object_identity o
            JOIN acl_class c ON c.id=o.object_id_class
            WHERE c.class=? AND o.object_id_identity=?
            """,
            Integer.class,
            Document.class.getName(), String.valueOf(id));
        return n.intValue();
    }

    private int aceRows(long id) {
        Integer n = jdbc.queryForObject(
            """
            SELECT COUNT(*)
            FROM acl_entry e
            JOIN acl_object_identity o
              ON o.id=e.acl_object_identity
            JOIN acl_class c ON c.id=o.object_id_class
            WHERE c.class=? AND o.object_id_identity=?
            """,
            Integer.class,
            Document.class.getName(), String.valueOf(id));
        return n.intValue();
    }

    @Test
    @WithMockUser(username="alice", authorities="tenant:t1")
    void leafDeleteRemovesDomainAclAndAce() {
        assertEquals(1, domainRows(101));
        assertEquals(1, aclRows(101));
        assertEquals(1, aceRows(101));

        deletion.deleteDocument(101L, false);

        assertEquals(0, domainRows(101));
        assertEquals(0, aclRows(101));
        assertEquals(0, aceRows(101));
        assertThrows(NotFoundException.class,
            () -> acls.readAclById(oid(101)));
    }

    @Test
    @WithMockUser(username="alice", authorities="tenant:t1")
    void runtimeFailureRollsBackDomainAndAcl() {
        assertThrows(IllegalStateException.class,
            () -> deletion.deleteDocument(101L, true));

        assertEquals(1, domainRows(101));
        assertEquals(1, aclRows(101));
        assertEquals(1, aceRows(101));
        acls.readAclById(oid(101));
    }

    @Test
    @WithMockUser(username="alice", authorities="tenant:t1")
    void parentCannotBeDeletedWhileChildAclExists() {
        assertThrows(ChildrenExistException.class,
            () -> deletion.deleteDocument(100L, false));

        assertEquals(1, domainRows(100));
        assertEquals(1, domainRows(102));
        assertEquals(1, aclRows(100));
        assertEquals(1, aclRows(102));
    }

    @Test
    void aclCascadeDoesNotDeleteDomainObjects() {
        new TransactionTemplate(transactionManager)
            .executeWithoutResult(
                status -> acls.deleteAcl(oid(100), true));

        assertEquals(0, aclRows(100));
        assertEquals(0, aclRows(102));
        assertEquals(0, aceRows(100));
        assertEquals(0, aceRows(102));
        assertEquals(1, domainRows(100));
        assertEquals(1, domainRows(102));
    }

    @Test
    void directDomainDeleteLeavesOrphanAcl() {
        jdbc.update("DELETE FROM document WHERE id=?", 101L);
        assertEquals(0, domainRows(101));
        assertEquals(1, aclRows(101));
        assertEquals(1, aceRows(101));
    }

    @Test
    @WithMockUser(username="bob", authorities="tenant:t1")
    void readAceDoesNotAuthorizeDeletion() {
        assertEquals("Leaf", reader.read(101L));
        assertThrows(AccessDeniedException.class,
            () -> deletion.deleteDocument(101L, false));
        assertEquals(1, domainRows(101));
    }

    @Test
    @WithMockUser(username="manager1",
        authorities={"tenant:t1","ROLE_TENANT_ADMIN"})
    void tenantAdminDeletesLeafInOwnTenant() {
        deletion.deleteDocument(101L, false);
        assertEquals(0, domainRows(101));
        assertEquals(0, aclRows(101));
    }

    @Test
    @WithMockUser(username="manager1",
        authorities={"tenant:t1","ROLE_TENANT_ADMIN"})
    void tenantAdminCannotDeleteOtherTenant() {
        assertThrows(AccessDeniedException.class,
            () -> deletion.deleteDocument(200L, false));
        assertEquals(1, domainRows(200));
    }

    @Test
    @WithMockUser(username="carol", authorities="tenant:t2")
    void ownerMayDeleteFromOwnTenant() {
        deletion.deleteDocument(200L, false);
        assertEquals(0, domainRows(200));
        assertEquals(0, aclRows(200));
    }

    @Test
    @WithMockUser(username="alice")
    void missingTenantAuthorityDeniesDelete() {
        assertThrows(AccessDeniedException.class,
            () -> deletion.deleteDocument(101L, false));
        assertEquals(1, domainRows(101));
    }

    @Test
    @WithMockUser(username="mallory",
        authorities={"tenant:t1","ROLE_TENANT_ADMIN"})
    void forgedRoleWithoutMembershipIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> deletion.deleteDocument(101L, false));
        assertEquals(1, aclRows(101));
    }

    @Test
    @WithMockUser(username="manager1", authorities="tenant:t1")
    void tenantAdminBindingWithoutRoleIsInsufficient() {
        assertThrows(AccessDeniedException.class,
            () -> deletion.deleteDocument(101L, false));
    }

    @Test
    @WithMockUser(username="alice", authorities="tenant:t1")
    void nonexistentDocumentDeniesBeforeMutation() {
        assertThrows(AccessDeniedException.class,
            () -> deletion.deleteDocument(999L, false));
    }

    @Test
    @WithMockUser(username="alice", authorities="tenant:t1")
    void missingAclCannotSilentlyDeleteDomain() {
        assertEquals(1, domainRows(300));
        assertEquals(0, aclRows(300));
        assertThrows(NotFoundException.class,
            () -> deletion.deleteDocument(300L, false));
        assertEquals(1, domainRows(300));
    }

    @Test
    @WithMockUser(username="bob", authorities="tenant:t1")
    void bobCanReadBeforeAnyDeletion() {
        assertEquals("Leaf", reader.read(101L));
    }

    @Test
    @WithMockUser(username="alice", authorities="tenant:t1")
    void aclOwnerWithoutReadAceIsNotImplicitlyAllowed() {
        assertThrows(AccessDeniedException.class,
            () -> reader.read(101L));
    }

    @Test
    void domainForeignKeyAlsoBlocksParentDelete() {
        assertThrows(
            org.springframework.dao.DataIntegrityViolationException.class,
            () -> jdbc.update("DELETE FROM document WHERE id=?",100L));
        assertEquals(1, domainRows(100));
        assertEquals(1, domainRows(102));
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn test
```

**Expected by design:** 17 JUnit tests pass with zero failures/errors. This is an **expected** outcome, not a claim that Maven was executed here. The Spring context, HSQLDB schema, and cache reinitialize after every test via `@DirtiesContext`. Tests use `@WithMockUser` for authorization checks and do not replace real JWT/password verification tests.

### 7.1. Observation Matrix

| Test | Domain | ACL/ACE | Proves |
|---|---|---|---|
| Leaf delete succeeds | Deleted | Deleted | Both resources commit together |
| Intentional exception after both deletes | Remains | Remains | Atomic rollback within same JDBC transaction |
| Delete parent with `deleteChildren=false` | Parent/child remain | Both ACLs remain | Blocked by `ChildrenExistException` |
| Call only `deleteAcl(root,true)` | Parent/child remain | Entire ACL subtree gone | ACL cascade is not domain cascade |
| Delete domain via raw SQL only | Domain gone | ACL remains | Orphan ACL |
| Domain exists without ACL | Remains | Missing | Fail-closed |
| Bob only has READ ACE | Remains | Remains | READ does not equal DELETE |
| Cross-tenant admin | Remains | Remains | Admin rights never cross tenant scope |

Never conclude "rollback succeeded" solely from HTTP 403, exception logs, or checking a single table; inspect **domain rows, ACL identity rows, and ACE rows** after the transaction.

## 8. Production: Risks Beyond the Demo

### 8.1. External Side Effects Do Not Roll Back with JDBC

Deleting object-storage files, purging search indexes, sending emails, and publishing messages directly do not participate in a JDBC transaction. If the DB rolls back after a file is deleted, data becomes inconsistent. If the DB commits and the process crashes before emitting an event, downstream systems miss the deletion.

You can use a **transactional outbox**:

```text
BEGIN JDBC TRANSACTION
  ├── DELETE acl_entry + acl_object_identity
  ├── DELETE document
  └── INSERT outbox_event(DOCUMENT_DELETED, id=101)
COMMIT
      ↓
Worker reads committed outbox
      ↓
Delete file/index, send event, retry with idempotency key
```

An outbox persists the intent to emit an event within the same commit; it does not make networks and email atomic. For irreversible file deletions, consider tombstones and deferring physical erasure until after retention periods.

### 8.2. Transaction Manager and REQUIRES_NEW

If `aclService` uses DataSource A while the domain repository uses DataSource B, or if an ACL deletion helper uses `REQUIRES_NEW` and commits independently, rolling back the domain transaction will not restore the ACL. Use the **same DataSource/TX** or a coordinator / eventual-consistency design with reconciliation. Test on the exact production configuration rather than guessing from annotations alone.

### 8.3. Concurrent Deletes, New Children, and Mid-Flight Permission Changes

Common races:
- Owner/tenant changes between `@PreAuthorize` and DELETE.
- One request adds a child ACL while another deletes the parent ACL.
- One request adds an ACE to an ACL about to be deleted.
- Two requests delete the same ID concurrently and update caches simultaneously.

Use row locks, optimistic versioning, FKs, unique constraints, tenant-qualified DML, appropriate isolation, and affected-row checks. The demo only rechecks permissions inside the transaction and uses domain predicates; it does not guarantee serializable outcomes under all contention.

### 8.4. ACL Cache, Clusters, and Stale Permissions

JDBC ACL uses caching. Cache eviction in one JVM does not synchronize every node's cache, especially on deletes followed by rollbacks. Use event-driven invalidation or shared caches with bounded TTLs, and test permissions across nodes after revocation/deletion. An ACL cache hit never replaces verifying the domain record still exists and is not soft-deleted.

### 8.5. Soft Deletes, Legal Holds, and Auditing

If data is under retention or legal hold, never hard-delete immediately just because the owner asks. Use soft deletes/tombstones and read-blocking policies, preserving audits as required. ACL metadata and `acl_sid` may still be needed for historical investigations; purge per retention rules rather than blindly. Log deletions with actor, object identity, tenant, reason, timestamp, outcome, affected rows, and policy version; protect audit logs from tampering.

### 8.6. Batch Deletes and Lifecycle Management

Never invoke a `@Transactional` method on the same bean via `this.method()` expecting proxy management for each step. For batch deletions, define all-or-nothing vs. partial-success semantics, authorize **every individual record**, coordinate ACL/domain children, bound transaction sizes, and manage retries. Soft-deleting upfront followed by controlled background purging is often safer than one huge transaction locking many ACLs.

## 9. Code Review Checklist

- [ ] Deletion policy checks tenant, owner/admin binding, and record state.
- [ ] Caller is authorized through a Spring-managed proxy, not only at the UI or a single HTTP route.
- [ ] Distinguishes ACL owner, READ/WRITE ACEs, and business delete rights.
- [ ] Uses the exact `ObjectIdentity(type, ID)` stored by ACLs.
- [ ] Checks for child ACLs before choosing `deleteChildren`.
- [ ] Never uses `deleteChildren=true` thinking it deletes the domain subtree.
- [ ] ACL and domain share the same DataSource and transaction; no ACL commit in `REQUIRES_NEW`.
- [ ] Exceptions propagate to the transaction interceptor with proper rollback rules.
- [ ] When an ACL is missing, the domain is never silently deleted; an inconsistency repair plan exists.
- [ ] Domain deletion is conditional and verifies affected-row counts.
- [ ] Verifies domain and ACL FKs, DML ordering, and locking under concurrency.
- [ ] Caching and invalidation are tested after commits/rollbacks and across cluster nodes.
- [ ] Soft-deleted items remain blocked across all services and queries.
- [ ] Files, message brokers, emails, and search indexes use outbox/retry/compensation.
- [ ] Integration tests prove domain + ACL + ACE commit/rollback together, not just HTTP statuses.
- [ ] Auditing, retention, and orphan-ACL reconciliation workflows exist.

## 10. Knowledge Self-Check

**Question 1.** Does deleting from `document` automatically delete corresponding `acl_entry` rows?

**Answer:** Not under the default ACL schema; `acl_object_identity` stores type + domain ID without a direct FK to every domain table. The application must coordinate ACL deletion.

**Question 2.** What happens on `deleteAcl(root,false)` when child ACLs still exist?

**Answer:** It throws `ChildrenExistException`; if inside a transaction deleting the domain object and the exception escapes, the entire transaction can roll back.

**Question 3.** Does `deleteAcl(root,true)` automatically delete child `document` rows?

**Answer:** No. That is an ACL cascade. The domain subtree needs its own lifecycle and per-descendant authorization checks.

**Question 4.** Two DELETEs share the same DataSource/TX, and a runtime exception is thrown before commit. What happens?

**Answer:** Spring Framework 6.x rolls back by default on unchecked exceptions escaping through the transaction interceptor; both uncommitted domain and ACL/ACE changes are reverted.

**Question 5.** Why doesn't the owner in `acl_object_identity.owner_sid` automatically get business READ/DELETE?

**Answer:** The ACL owner is ACL administration metadata, not implicitly an ACE or business permission on the document. Policies must define allowed actions and tenant context explicitly.

## 11. Official Documentation

- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html) — the four ACL tables, lifecycle not auto-integrated with repositories, and `AclPermissionEvaluator`.
- [Spring Security 6.5 — MutableAclService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/MutableAclService.html) — `deleteAcl(ObjectIdentity,boolean)` and `ChildrenExistException`.
- [Spring Security 6.5 — JdbcMutableAclService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html) — JDBC deletion and schema/dialect configuration.
- [Spring Security 6.5 — AclService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/AclService.html) — reading ACLs and `findChildren`.
- [Spring Security 6.5 — Database Schema](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html) — DDL/foreign keys of the ACL module.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html) — proxies, propagation, and transaction boundaries.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html) — default rollback rules and `rollbackFor`.

**Remember:** Deleting a domain object **does not automatically delete its ACL**, and `MutableAclService.deleteAcl` **does not automatically delete the domain object**. A safe service checks permissions upfront, separates ACL children from domain children, executes both DELETEs in the **same JDBC transaction**, verifies rollbacks by inspecting both business and ACL tables, and handles caching and off-database side effects explicitly.
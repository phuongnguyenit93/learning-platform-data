# Adding, Updating, and Deleting ACEs and Controlling Who Can Share in Spring Security ACL

## 1. The Problem: Who Receives Permissions, and Who Is Allowed to Grant Them?

Suppose `Document#101` belongs to tenant `t1` and is owned by Alice. Alice wants to grant Bob read access first, then upgrade him to edit access, and later revoke it. Another employee who has `WRITE` on the document **must not be able to reshare it** to others. A tenant administrator may be authorized to manage ACLs within that tenant, yet **must not use an admin role to cross tenant boundaries**.

Spring Security ACL uses **Access Control Entries (ACEs)** to store individual permissions on an object. At the API level, the three core operations are:

```java
mutableAcl.insertAce(index, permission, sid, true);
mutableAcl.updateAce(index, newPermission);
mutableAcl.deleteAce(index);
aclService.updateAcl(mutableAcl);
```

This is an **API illustration**: it requires a valid `MutableAcl`, `Permission`, `Sid`, right index, and `MutableAclService`. These methods **do not by themselves prove the caller has business permission to share**. You must enforce all of the following together:

1. **Caller's business authorization**: owner or a user granted share-management rights within the tenant.
2. **Spring Security's ACL structure-modification rights**: `AclAuthorizationStrategy` governs who may call mutators on `MutableAcl`.
3. **Recipient validity**: does the recipient belong to the right tenant, are they eligible for this permission level, and are they active?
4. **Granted permission policy**: grant only allowed READ/WRITE levels; never let users pass arbitrary `ADMINISTRATION` bitmasks.
5. **Consistency of changes**: transactions, cache eviction, auditing, revocation, and concurrency handling.

This lesson focuses on **implementing adding/updating/deleting ACEs** and designing a safe sharing API on Spring Security ACL 6.5, Java 17, and Spring Boot 3.5.x.

## 2. ACEs and ACLs: Which Records Actually Change?

In the default ACL database:

```text
acl_sid
  id | principal | sid
  1  | true      | alice
  2  | true      | bob
  3  | true      | manager1

acl_class
  id | class
  7  | com.example.aclshare.Document

acl_object_identity
  id | object_id_class | object_id_identity | owner_sid | entries_inheriting
  10 | 7               | 101                | 1         | false

acl_entry
  id  | acl_object_identity | ace_order | sid | mask | granting
  100 | 10                  | 0         | 3   | 16   | true
```

This is illustrative data. Internal ACL `10` represents the domain object `Document#101`; `acl_entry.acl_object_identity=10` points to the **ACL PK**, not document ID 101.

`owner_sid=1` means Alice is the **ACL owner**. The first ACE grants `BasePermission.ADMINISTRATION` (mask 16) to `manager1`; it illustrates how a non-owner is granted ACL-management rights. **ADMINISTRATION on an ACL is different from business WRITE on a Document.**

Concepts to distinguish:

| Concept | Meaning | Example |
|---|---|---|
| `ObjectIdentity` | Identifier of type + domain ID | `(Document.class, 101L)` |
| `MutableAcl` | ACL that can have ACEs added/updated/deleted | ACL of `Document#101` |
| `Sid` | Target identity receiving permission | `PrincipalSid("bob")` |
| `Permission` | Permission level, typically a bitmask | `BasePermission.READ`, mask 1 |
| `AccessControlEntry` | Rule on one SID + permission + allow/deny | Bob has READ |
| `AclAuthorizationStrategy` | Checks **ACL administration** rights | Owner, admin authority, or ADMINISTRATION ACE |
| `MutableAclService` | Reads/creates/updates/deletes ACLs in persistence | `JdbcMutableAclService` |
| `AclPermissionEvaluator` | Evaluates **resource access** permissions | `hasPermission(#id, ..., READ)` |

Here, a user may hold `BasePermission.WRITE` yet still not be permitted to edit the sharing list. Separating **resource usage rights** from **permission-policy editing rights** is a core anti-privilege-escalation principle.

## 3. Three Methods for Modifying ACEs

### 3.1. Adding an ACE — insertAce

```java
Sid bob = new PrincipalSid("bob");
Permission read = BasePermission.READ;
acl.insertAce(acl.getEntries().size(), read, bob, true);
mutableAclService.updateAcl(acl);
```

This is a **sample snippet inside a service with all dependencies**. `insertAce` takes:
- `atIndexLocation`: insertion index in the ACE list; end of list is `acl.getEntries().size()`.
- `permission`: permission, such as `READ`.
- `sid`: principal or authority receiving the permission.
- `granting`: `true` to allow, `false` for a deny ACE.

**Do not use an ACE with `granting=false` to represent "revoking a share" if the goal is removing a grant**. A deny ACE remains in place and can interact with other ACEs per ordering/granting strategy; revoking a grant normally uses `deleteAce`. Use deny intentionally only when policy explicitly calls for an explicit denial.

Inserting an ACE changes `ace_order`. Never treat the database ID of an ACE as its list index in `MutableAcl`; `ace_order` and the list index track logical order managed by the framework, whereas PK `acl_entry.id` is a separate value.

### 3.2. Updating an ACE — updateAce

```java
int index = findGrantIndex(acl, new PrincipalSid("bob"));
acl.updateAce(index, BasePermission.WRITE);
mutableAclService.updateAcl(acl);
```

This is an **illustration**, requiring `findGrantIndex` to be defined by the application. `updateAce(int,Permission)` replaces the **permission mask** of an existing ACE. It **does not** change the SID, change `granting`, or serve as an "update all ACE properties" API.

Replacing `READ` with `WRITE` can cause Bob to **lose** READ, depending on the permission strategy. If `EDITOR` must include **both READ and WRITE**, do not simply switch to mask 2. Two ways to model it:

- Two separate ACEs, one READ and one WRITE, for the same SID.
- One ACE carrying a combined bitmask READ|WRITE (=3), e.g., `CumulativePermission`.

In the demo in section 6, we choose **one grant ACE per recipient** per document, at levels:
- `VIEWER` → READ (mask 1).
- `EDITOR` → READ|WRITE (mask 3).

`updateAce` replaces mask 1 with mask 3 when upgrading; downgrading from editor to viewer replaces mask 3 with 1. Spring Security ACL's `DefaultPermissionGrantingStrategy` supports matching ACE bits for **granting ACEs**; always test on your target version, since deny/multi-ACE semantics have their own rules.

```java
Permission editor = new CumulativePermission()
    .set(BasePermission.READ)
    .set(BasePermission.WRITE);
```

With `CumulativePermission`, `set` turns on the corresponding bits. This snippet can live inside a method and import `org.springframework.security.acls.domain.CumulativePermission`.

### 3.3. Deleting an ACE — deleteAce

```java
int index = findGrantIndex(acl, new PrincipalSid("bob"));
if (index >= 0) {
    acl.deleteAce(index);
    mutableAclService.updateAcl(acl);
}
```

Delete an ACE by its **current list position**. When deleting multiple ACEs, iterate **from back to front** so indices do not shift. After deletion, remaining indices change. Never store an old index across requests and reuse it directly later.

**Important point:** Deleting a direct ACE does not guarantee "Bob has no remaining path to read." Bob might still receive permission through a `GrantedAuthoritySid`, a parent ACL if `entries_inheriting=true`, or another policy. Revoking **one permission source** must be tested against the combination of all active permission sources.

### 3.4. Persistence and the JDBC updateAcl Mechanism

`MutableAcl` mutates in memory first; `mutableAclService.updateAcl(acl)` writes to the DB. Under `JdbcMutableAclService`, a single `updateAcl` call may **delete all existing ACE rows for that ACL and reinsert ACE rows** from the new list, rather than running an in-place SQL UPDATE on one row. This implies:

- Never treat `acl_entry.id` as a durable identifier for a share; it can change on every update.
- `ace_order` constraints must remain synchronized by the library.
- If another service is editing the ACL concurrently, there is a risk of **lost updates**.
- Writes should run inside an appropriate transaction, and permission caches must be invalidated.
- Business-level change audits should record actor, target, recipient, old level, and new level, rather than relying only on row IDs.

Never modify `acl_entry` directly via SQL in one path while forgetting to evict `AclCache`; cached ACL decisions can keep serving stale data.

## 4. Who Is Actually Allowed to Share?

### 4.1. Two Distinct Protection Layers

**Layer A — business policy** can be defined as:

```text
canManageShare(actor, document):
  actor is an authenticated and active user
  AND actor is a member of the document's tenant
  AND (
      actor is the owner of the document
      OR actor has a tenant-admin binding on that exact tenant
  )
```

**Layer B — `AclAuthorizationStrategy`** from the framework decides whether the actor is permitted to modify `MutableAcl`. By default `AclAuthorizationStrategyImpl` accepts the actor if they are the ACL owner, hold the configured system-wide authority, or hold `BasePermission.ADMINISTRATION` on the ACL. This is an **ACL administration mechanism**, not a tenant/business-owner check replacing Layer A.

Even if an actor passes Layer B, they must still pass Layer A. Granting `ROLE_ACL_SYSTEM_ADMIN` to every "support" staff member while skipping Layer A would let them edit ACEs on any resource. Avoid system-wide rights unless governed by strict break-glass procedures.

### 4.2. Grant/Revoke Rules by Recipient

In our example:

| Actor | Document | Recipient | Action | Decision |
|---|---|---|---|---|
| Alice (owner t1) | 101 / t1 | Bob (member t1) | VIEWER/EDITOR/revoke | Allow |
| Bob (shared EDITOR) | 101 / t1 | manager1 | Reshare | Deny |
| manager1 (tenant admin t1 + ACL ADMIN ACE) | 101 / t1 | Bob | VIEWER/EDITOR/revoke | Allow |
| manager1 (tenant admin t1) | 201 / t2 | Carol | Share | Deny |
| Alice (owner t1) | 101 / t1 | Carol (member t2) | Share | Deny |
| Mallory (outside tenant) | 101 / t1 | Bob | Share | Deny |
| Alice | 101 / t1 | Alice (owner) | Share as recipient ACE | Reject as invalid request |
| Alice | 101 / t1 | Bob | Grant `ADMINISTRATION` via basic share API | Unsupported operation |

Recipient tenant membership must be verified **at grant time**. Actor eligibility must also be checked at modification time, since permissions may have been revoked. In production, store role bindings per tenant; a bare `ROLE_TENANT_ADMIN` role in a token is insufficient to claim admin rights over all tenants.

### 4.3. Do Not Confuse WRITE with SHARE

`BasePermission.WRITE` permits editing **business content** if the API checks it. It does not grant permission to call `insertAce`, `updateAce`, or `deleteAce`. A sharing policy typically requires either:
- Modeling as a dedicated action (e.g., `document:share`), or
- ACL administration rights on that exact object combined with an owner/admin policy, as in this demo.

You can design "editors may share" if business rules allow it, but it must be declared explicitly, capped so editors cannot grant higher privileges than they hold, guarded against delegation loops, and audited.

### 4.4. Granting to PrincipalSid vs. GrantedAuthoritySid

```java
Sid user = new PrincipalSid("bob");
Sid groupRole = new GrantedAuthoritySid("ROLE_REVIEWER");
```

These are two different SID types:
- `PrincipalSid` targets a single username.
- `GrantedAuthoritySid` grants access to **every Authentication** holding that authority, which may be broader than intended.

The individual sharing API in the demo **accepts only a username**, never letting clients pick the SID type or pass `ROLE_ADMIN` directly. If group/role sharing is supported, build a separate endpoint and policy, validate that the group belongs to the right tenant, restrict allowed permission levels, and test which principals actually inherit the new access.

## 5. Demo Permission Matrix and Boundaries

The system has three documents:

| ID | Tenant | Owner | ACL owner |
|---:|---|---|---|
| 101 | t1 | alice | alice |
| 102 | t1 | bob | bob |
| 201 | t2 | carol | carol |

Members:
- `t1`: Alice, Bob, manager1.
- `t2`: Carol, Dave.
- Tenant-admin: manager1 is authorized to administer **t1**.

Document#101's ACL contains an ADMINISTRATION ACE for principal `manager1`, allowing `manager1` to modify the ACL at the framework layer. Document#201 does not grant that right to `manager1`. When sharing, code modifies only the **verified recipient's** ACE without altering the ACL owner or other ACEs.

Share levels:

| Level | ACL mask | Read | Write | Share/ACL admin |
|---|---:|---:|---:|---:|
| Unshared | No direct grant ACE | Deny if no other source | Deny if no other source | No |
| `VIEWER` | 1 (READ) | Allow | Deny | No |
| `EDITOR` | 3 (READ|WRITE) | Allow | Allow | No |

**Note on other permission sources:** An ACL may also have inherited or role-based ACEs. This table assumes no other READ/WRITE sources exist for the recipient and `entries_inheriting=false` in demo data. Never interpret "revoked = guaranteed deny" if roles, group shares, or inheritance still grant access in a real model.

## 6. Complete Example: Java 17, Spring Boot 3.5.6, Spring Security ACL, HSQLDB

The demo includes Maven, SQL schema, fixtures, Spring configuration, policies, and services; run `mvn test` to verify inserting, upgrading, downgrading, and deleting ACEs as well as all denial paths.

### 6.1. Project Structure

```text
acl-sharing-demo/
  pom.xml
  src/main/java/com/example/aclshare/
    AclSharingApplication.java
    Document.java
    ShareLevel.java
    TenantDirectory.java
    DocumentRepository.java
    SharePolicy.java
    AclConfig.java
    SharingService.java
    DocumentService.java
  src/main/resources/
    schema.sql
    data.sql
  src/test/java/com/example/aclshare/
    SharingIntegrationTest.java
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
    <artifactId>acl-sharing-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-acl</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
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

Do not override the `spring-security-acl` version in the demo; Spring Boot 3.5.6 manages compatible Security modules. Java 17 is the minimum for Spring Boot 3.x. If a project uses Spring Boot 4/Spring Security 7, consult the corresponding APIs and starters rather than forcing a new major library version into an older BOM.

### 6.3. HSQLDB Schema

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE document (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    owner_username VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL
);

CREATE TABLE tenant_member (
    tenant_id VARCHAR(50) NOT NULL,
    username VARCHAR(100) NOT NULL,
    PRIMARY KEY(tenant_id, username)
);

CREATE TABLE tenant_admin (
    tenant_id VARCHAR(50) NOT NULL,
    username VARCHAR(100) NOT NULL,
    PRIMARY KEY(tenant_id, username),
    FOREIGN KEY (tenant_id, username)
        REFERENCES tenant_member(tenant_id, username)
);

CREATE TABLE acl_sid (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000)
        PRIMARY KEY,
    principal BOOLEAN NOT NULL,
    sid VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT uq_sid UNIQUE(sid, principal)
);

CREATE TABLE acl_class (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000)
        PRIMARY KEY,
    class VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT uq_class UNIQUE(class)
);

CREATE TABLE acl_object_identity (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000)
        PRIMARY KEY,
    object_id_class BIGINT NOT NULL,
    object_id_identity VARCHAR_IGNORECASE(36) NOT NULL,
    parent_object BIGINT,
    owner_sid BIGINT,
    entries_inheriting BOOLEAN NOT NULL,
    CONSTRAINT uq_object UNIQUE(object_id_class, object_id_identity),
    FOREIGN KEY (object_id_class) REFERENCES acl_class(id),
    FOREIGN KEY (parent_object) REFERENCES acl_object_identity(id),
    FOREIGN KEY (owner_sid) REFERENCES acl_sid(id)
);

CREATE TABLE acl_entry (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000)
        PRIMARY KEY,
    acl_object_identity BIGINT NOT NULL,
    ace_order INTEGER NOT NULL,
    sid BIGINT NOT NULL,
    mask INTEGER NOT NULL,
    granting BOOLEAN NOT NULL,
    audit_success BOOLEAN NOT NULL,
    audit_failure BOOLEAN NOT NULL,
    CONSTRAINT uq_ace_order UNIQUE(acl_object_identity, ace_order),
    FOREIGN KEY (acl_object_identity) REFERENCES acl_object_identity(id),
    FOREIGN KEY (sid) REFERENCES acl_sid(id)
);
```

Four ACL tables following the HSQLDB layout provided by Spring Security, plus three business tables `document`, `tenant_member`, and `tenant_admin`. Seeded ACL IDs are below 1000 to distinguish manual fixture IDs from auto-generated IDs when new ACEs are inserted. Production schemas should use migrations, indexes, audit columns, and proper tenant policies; this is an embedded test database.

### 6.4. Initial Fixtures

**`src/main/resources/data.sql`**

```sql
INSERT INTO document VALUES (101, 't1', 'alice', 'Alice draft');
INSERT INTO document VALUES (102, 't1', 'bob', 'Bob notes');
INSERT INTO document VALUES (201, 't2', 'carol', 'Carol plan');

INSERT INTO tenant_member VALUES ('t1', 'alice');
INSERT INTO tenant_member VALUES ('t1', 'bob');
INSERT INTO tenant_member VALUES ('t1', 'manager1');
INSERT INTO tenant_member VALUES ('t2', 'carol');
INSERT INTO tenant_member VALUES ('t2', 'dave');

INSERT INTO tenant_admin VALUES ('t1', 'manager1');

INSERT INTO acl_sid(id, principal, sid) VALUES (1, TRUE, 'alice');
INSERT INTO acl_sid(id, principal, sid) VALUES (2, TRUE, 'bob');
INSERT INTO acl_sid(id, principal, sid) VALUES (3, TRUE, 'carol');
INSERT INTO acl_sid(id, principal, sid) VALUES (4, TRUE, 'manager1');

INSERT INTO acl_class(id, class)
VALUES (7, 'com.example.aclshare.Document');

INSERT INTO acl_object_identity(
    id, object_id_class, object_id_identity,
    parent_object, owner_sid, entries_inheriting
) VALUES (10, 7, '101', NULL, 1, FALSE);

INSERT INTO acl_object_identity(
    id, object_id_class, object_id_identity,
    parent_object, owner_sid, entries_inheriting
) VALUES (11, 7, '102', NULL, 2, FALSE);

INSERT INTO acl_object_identity(
    id, object_id_class, object_id_identity,
    parent_object, owner_sid, entries_inheriting
) VALUES (20, 7, '201', NULL, 3, FALSE);

-- Grant manager1 ADMINISTRATION permission on ACL #101.
INSERT INTO acl_entry(
    id, acl_object_identity, ace_order, sid,
    mask, granting, audit_success, audit_failure
) VALUES (100, 10, 0, 4, 16, TRUE, FALSE, FALSE);
```

`acl_entry.id=100` is the ACE for `manager1` on Document#101's ACL. It enables **ACL administration operations** under `AclAuthorizationStrategyImpl` without granting content READ or WRITE. Owner Alice can edit the ACL because `owner_sid=alice`. Document#102 has no admin ACE for `manager1`, even though `manager1` is a tenant admin in the business tables: this illustrates the two independent governance layers.

### 6.5. Spring Boot Application

**`src/main/java/com/example/aclshare/AclSharingApplication.java`**

```java
package com.example.aclshare;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AclSharingApplication {
    public static void main(String[] args) {
        SpringApplication.run(AclSharingApplication.class, args);
    }
}
```

### 6.6. Document and Share Levels

**`src/main/java/com/example/aclshare/Document.java`**

```java
package com.example.aclshare;

public record Document(Long id, String tenantId,
                       String owner, String title) {
    public Long getId() {
        return id;
    }
}
```

**`src/main/java/com/example/aclshare/ShareLevel.java`**

```java
package com.example.aclshare;

public enum ShareLevel {
    VIEWER,
    EDITOR
}
```

`ShareLevel` intentionally has only two levels. The API **does not accept arbitrary integer permission masks from clients**, nor does it allow creating `ADMINISTRATION`, `DELETE`, or `granting=false` ACEs through personal sharing. If business rules require more levels, expand the enum and test matrix deliberately.

### 6.7. Repository and Tenant Directory

**`src/main/java/com/example/aclshare/DocumentRepository.java`**

```java
package com.example.aclshare;

import java.util.List;
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
            SELECT id, tenant_id, owner_username, title
            FROM document WHERE id = ?
            """,
            (rs, rowNum) -> new Document(
                rs.getLong("id"),
                rs.getString("tenant_id"),
                rs.getString("owner_username"),
                rs.getString("title")
            ),
            id
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public void rename(Long id, String title) {
        int updated = jdbc.update(
            "UPDATE document SET title = ? WHERE id = ?",
            title, id
        );
        if (updated != 1) {
            throw new IllegalStateException("Document not found");
        }
    }
}
```

**`src/main/java/com/example/aclshare/TenantDirectory.java`**

```java
package com.example.aclshare;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class TenantDirectory {
    private final JdbcTemplate jdbc;

    public TenantDirectory(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean isMember(String tenant, String user) {
        if (tenant == null || user == null) {
            return false;
        }
        Integer count = jdbc.queryForObject(
            """
            SELECT COUNT(*) FROM tenant_member
            WHERE tenant_id = ? AND username = ?
            """,
            Integer.class, tenant, user
        );
        return count != null && count > 0;
    }

    public boolean isTenantAdmin(String tenant, String user) {
        if (tenant == null || user == null) {
            return false;
        }
        Integer count = jdbc.queryForObject(
            """
            SELECT COUNT(*) FROM tenant_admin
            WHERE tenant_id = ? AND username = ?
            """,
            Integer.class, tenant, user
        );
        return count != null && count > 0;
    }
}
```

The directory is queried from the server-side DB, never from JSON fields or client-supplied headers. In production, keep IAM, tenant memberships, and cache/revocation policies synchronized.

### 6.8. SharePolicy: Checking Who Can Manage Sharing

**`src/main/java/com/example/aclshare/SharePolicy.java`**

```java
package com.example.aclshare;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component("sharePolicy")
public class SharePolicy {
    private final DocumentRepository documents;
    private final TenantDirectory directory;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public SharePolicy(
            DocumentRepository documents,
            TenantDirectory directory) {
        this.documents = documents;
        this.directory = directory;
    }

    public boolean canManage(Authentication auth, Long id) {
        if (auth == null || !auth.isAuthenticated()
                || trust.isAnonymous(auth)) {
            return false;
        }

        Document document = documents.find(id);
        if (document == null) {
            return false;
        }

        String user = auth.getName();
        String tenant = document.tenantId();

        if (!directory.isMember(tenant, user)) {
            return false;
        }

        if (document.owner().equals(user)) {
            return true;
        }

        return directory.isTenantAdmin(tenant, user)
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

**Meaning:** the owner can share if they are still a member of the right tenant. A tenant admin needs **both** the role in Authentication and a binding in `tenant_admin`. This is a business rule; it **does not replace** the `AclAuthorizationStrategy` check when `MutableAcl.insertAce/updateAce/deleteAce` runs.

In particular, `ROLE_TENANT_ADMIN` is not `ROLE_ACL_SYSTEM_ADMIN`. The former takes effect only together with a tenant binding and an ACL administration grant; the latter is a system-wide framework privilege that the demo grants to no user.

### 6.9. ACL Framework and Method Security Configuration

**`src/main/java/com/example/aclshare/AclConfig.java`**

```java
package com.example.aclshare;

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
            AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    static JdbcMutableAclService aclService(
            DataSource dataSource,
            LookupStrategy lookup,
            AclCache cache) {
        return new JdbcMutableAclService(dataSource, lookup, cache);
    }

    @Bean
    static LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache cache,
            AclAuthorizationStrategy authorization,
            PermissionGrantingStrategy granting) {
        return new BasicLookupStrategy(
            dataSource, cache, authorization, granting
        );
    }

    @Bean
    static AclCache aclCache(
            PermissionGrantingStrategy granting,
            AclAuthorizationStrategy authorization) {
        return new SpringCacheBasedAclCache(
            new ConcurrentMapCache("aclCache"),
            granting,
            authorization
        );
    }

    @Bean
    static AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_SYSTEM_ADMIN")
        );
    }

    @Bean
    static PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
            new ConsoleAuditLogger()
        );
    }
}
```

The Spring Security ACL infrastructure here includes `JdbcMutableAclService`, `BasicLookupStrategy`, ACL cache, granting strategy, and authorization strategy. `@EnableMethodSecurity` activates `@PreAuthorize`; the expression handler wires `AclPermissionEvaluator` so `hasPermission` evaluates actual ACEs in the database.

**Emphasis:** `ROLE_ACL_SYSTEM_ADMIN` in the constructor is a **framework-level system-wide administrative override**. The demo does not grant this role; the tenant admin is allowed to edit Document#101 via an explicit `BasePermission.ADMINISTRATION` ACE. In production, avoid granting system-wide authorities broadly; this role requires tight controls and auditing.

### 6.10. SharingService: Adding, Updating, and Deleting the Right ACEs

**`src/main/java/com/example/aclshare/SharingService.java`**

```java
package com.example.aclshare;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.CumulativePermission;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.AccessControlEntry;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.Permission;
import org.springframework.security.acls.model.Sid;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SharingService {
    private final MutableAclService aclService;
    private final DocumentRepository documents;
    private final TenantDirectory directory;

    public SharingService(
            MutableAclService aclService,
            DocumentRepository documents,
            TenantDirectory directory) {
        this.aclService = aclService;
        this.documents = documents;
        this.directory = directory;
    }

    @Transactional
    @PreAuthorize("@sharePolicy.canManage(authentication, #id)")
    public void setShare(
            @P("id") Long id,
            String recipient,
            ShareLevel level) {

        Document document = documents.find(id);
        validateRecipient(document, recipient);

        if (level == null) {
            throw new IllegalArgumentException("Share level required");
        }

        MutableAcl acl = loadAcl(id);
        Sid sid = new PrincipalSid(recipient);
        int index = findSingleGrantIndex(acl, sid);
        Permission permission = permissionFor(level);

        if (index < 0) {
            acl.insertAce(acl.getEntries().size(), permission, sid, true);
        }
        else {
            // Only change the mask of the existing ACE; SID/granting remain unchanged.
            acl.updateAce(index, permission);
        }

        aclService.updateAcl(acl);
    }

    @Transactional
    @PreAuthorize("@sharePolicy.canManage(authentication, #id)")
    public void revokeShare(
            @P("id") Long id,
            String recipient) {

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException("Recipient required");
        }

        MutableAcl acl = loadAcl(id);
        int index = findSingleGrantIndex(
            acl, new PrincipalSid(recipient)
        );

        if (index >= 0) {
            acl.deleteAce(index);
            aclService.updateAcl(acl);
        }
        // No grant exists: idempotent no-op.
    }

    private void validateRecipient(
            Document document, String recipient) {

        if (document == null
                || recipient == null
                || recipient.isBlank()
                || recipient.equals(document.owner())
                || !directory.isMember(document.tenantId(), recipient)) {
            throw new IllegalArgumentException(
                "Recipient must be another member of the same tenant"
            );
        }
    }

    private MutableAcl loadAcl(Long id) {
        return (MutableAcl) aclService.readAclById(
            new ObjectIdentityImpl(Document.class, id)
        );
    }

    private static Permission permissionFor(ShareLevel level) {
        return switch (level) {
            case VIEWER -> BasePermission.READ;
            case EDITOR -> new CumulativePermission()
                .set(BasePermission.READ)
                .set(BasePermission.WRITE);
        };
    }

    private static int findSingleGrantIndex(
            MutableAcl acl, Sid recipient) {
        int result = -1;

        for (int i = 0; i < acl.getEntries().size(); i++) {
            AccessControlEntry ace = acl.getEntries().get(i);

            if (!recipient.equals(ace.getSid())) {
                continue;
            }

            // This is an individual sharing API: do not automatically handle
            // deny ACEs, ADMIN, or multiple ACEs for the same SID.
            int mask = ace.getPermission().getMask();
            if (!ace.isGranting() || (mask != 1 && mask != 3)) {
                throw new IllegalStateException(
                    "Recipient already has a non-share ACE"
                );
            }

            if (result >= 0) {
                throw new IllegalStateException(
                    "Multiple ACEs need explicit reconciliation"
                );
            }
            result = i;
        }

        return result;
    }
}
```

**Security details:**

- `@PreAuthorize` must pass through the Spring proxy and invoke `sharePolicy` to block unauthorized callers **before the method body executes**.
- `@Transactional` wraps the ACL read + mutation + persistence, though default advisor ordering usually runs preauthorization before the transaction starts. In production, if owner/tenant can change concurrently, use transactions/locking or conditional updates spanning the invariant checks too.
- `validateRecipient` checks that the recipient belongs to the tenant and is not the owner.
- `ShareLevel` is an enum preventing callers from specifying `ADMINISTRATION` or `granting=false`.
- `findSingleGrantIndex` edits only a known **individual ACE** with mask 1 or 3; if it encounters multiple ACEs, a deny ACE, or another permission type, it refuses to mutate rather than corrupting ACL data outside the API's scope.
- `insertAce` adds a new entry if no grant exists; `updateAce` switches VIEWER↔EDITOR; `deleteAce` removes that exact individual grant.
- `updateAcl` persists changes. With the default JDBC implementation, it may recreate `acl_entry` rows; therefore always look up by SID/mask on the current ACL rather than caching `acl_entry.id` or indices across requests.
- If the ACL does not yet exist, `readAclById` throws `NotFoundException`; the demo requires ACLs to be created with the resource. Production must initialize ACLs when creating documents; **never** silently create missing ACLs inside an insufficiently verified share request.

**Intentional limitations:** The demo omits grant expiration, group sharing, deny ACEs, parent ACL inheritance, admin UI, file downloads, and notifications. When encountering ACEs more complex than an individual grant, the code fails closed to avoid silently stripping another group's permissions.

### 6.11. DocumentService: Enforcing the Shared Permissions

**`src/main/java/com/example/aclshare/DocumentService.java`**

```java
package com.example.aclshare;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize(
        "hasPermission(#id, 'com.example.aclshare.Document', " +
        "T(org.springframework.security.acls.domain.BasePermission).READ)"
    )
    public String read(@P("id") Long id) {
        Document document = documents.find(id);
        if (document == null) {
            throw new IllegalStateException("Document not found");
        }
        return document.title();
    }

    @Transactional
    @PreAuthorize(
        "hasPermission(#id, 'com.example.aclshare.Document', " +
        "T(org.springframework.security.acls.domain.BasePermission).WRITE)"
    )
    public void rename(@P("id") Long id, String title) {
        documents.rename(id, title);
    }
}
```

This is the **resource-usage** layer, separate from `SharingService` which is the **ACL-management** layer. Users granted EDITOR pass `hasPermission(WRITE)` to edit content, yet `@sharePolicy.canManage(...)` still denies them if they are not the owner or a tenant admin.

**Tenant warning:** `AclPermissionEvaluator` here checks the ACL permission in the database, but **does not automatically enforce a tenant boundary**. The demo intentionally grants ACEs only to recipients already verified for the tenant at share time. Production applications must enforce tenant checks on **every read/write path**, covering role-based ACEs, ACL inheritance, users leaving tenants, and documents moving tenants. Never use this `DocumentService` snippet as-is as a production multi-tenant policy.

## 7. Integration Tests: Proving All Three Operations and Denial Paths

The tests spin up a real Spring context and HSQLDB database, using `@WithMockUser` to simulate identities. Because many tests mutate ACLs, `@DirtiesContext(AFTER_EACH_TEST_METHOD)` reinitializes the embedded context/DB for each test, reducing the risk of state leakage and cross-test cache pollution. This approach is **intentionally simple yet slow**; production test suites can use transaction rollbacks, fixture resets, and controlled cache eviction for speed.

**`src/test/java/com/example/aclshare/SharingIntegrationTest.java`**

```java
package com.example.aclshare;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SharingIntegrationTest {
    @Autowired SharingService sharing;
    @Autowired DocumentService documents;
    @Autowired AclPermissionEvaluator evaluator;
    @Autowired JdbcTemplate jdbc;

    private static Authentication bob() {
        return UsernamePasswordAuthenticationToken.authenticated(
            "bob", "n/a",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }

    private static Authentication alice() {
        return UsernamePasswordAuthenticationToken.authenticated(
            "alice", "n/a",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }

    private static int permissionMask(
            JdbcTemplate jdbc, long documentId, String username) {
        Integer mask = jdbc.queryForObject(
            """
            SELECT e.mask
            FROM acl_entry e
            JOIN acl_object_identity o
                ON o.id = e.acl_object_identity
            JOIN acl_sid s ON s.id = e.sid
            WHERE o.object_id_identity = ?
              AND s.principal = TRUE
              AND s.sid = ?
              AND e.granting = TRUE
            """,
            Integer.class,
            String.valueOf(documentId), username
        );
        return mask.intValue();
    }

    private int recipientAceCount(long documentId, String username) {
        Integer count = jdbc.queryForObject(
            """
            SELECT COUNT(*)
            FROM acl_entry e
            JOIN acl_object_identity o
                ON o.id = e.acl_object_identity
            JOIN acl_sid s ON s.id = e.sid
            WHERE o.object_id_identity = ?
              AND s.principal = TRUE
              AND s.sid = ?
            """,
            Integer.class,
            String.valueOf(documentId), username
        );
        return count.intValue();
    }

    private boolean bobCanRead(long id) {
        return evaluator.hasPermission(
            bob(), id, Document.class.getName(), BasePermission.READ
        );
    }

    private boolean bobCanWrite(long id) {
        return evaluator.hasPermission(
            bob(), id, Document.class.getName(), BasePermission.WRITE
        );
    }

    @Test
    @WithMockUser(username = "alice")
    void addingViewerAceAllowsReadButNotWrite() {
        assertFalse(bobCanRead(101L));
        sharing.setShare(101L, "bob", ShareLevel.VIEWER);
        assertEquals(1, permissionMask(jdbc, 101L, "bob"));
        assertEquals(1, recipientAceCount(101L, "bob"));
        assertTrue(bobCanRead(101L));
        assertFalse(bobCanWrite(101L));
    }

    @Test
    @WithMockUser(username = "alice")
    void upgradingAceToEditorKeepsReadAndAddsWrite() {
        sharing.setShare(101L, "bob", ShareLevel.VIEWER);
        sharing.setShare(101L, "bob", ShareLevel.EDITOR);

        assertEquals(3, permissionMask(jdbc, 101L, "bob"));
        assertEquals(1, recipientAceCount(101L, "bob"));
        assertTrue(bobCanRead(101L));
        assertTrue(bobCanWrite(101L));
    }

    @Test
    @WithMockUser(username = "alice")
    void downgradingEditorToViewerRemovesWrite() {
        sharing.setShare(101L, "bob", ShareLevel.EDITOR);
        sharing.setShare(101L, "bob", ShareLevel.VIEWER);

        assertEquals(1, permissionMask(jdbc, 101L, "bob"));
        assertTrue(bobCanRead(101L));
        assertFalse(bobCanWrite(101L));
    }

    @Test
    @WithMockUser(username = "alice")
    void revokingShareDeletesRecipientAce() {
        sharing.setShare(101L, "bob", ShareLevel.EDITOR);
        assertTrue(bobCanWrite(101L));

        sharing.revokeShare(101L, "bob");

        assertEquals(0, recipientAceCount(101L, "bob"));
        assertFalse(bobCanRead(101L));
        assertFalse(bobCanWrite(101L));
    }

    @Test
    @WithMockUser(username = "alice")
    void duplicateShareRequestDoesNotCreateSecondAce() {
        sharing.setShare(101L, "bob", ShareLevel.VIEWER);
        sharing.setShare(101L, "bob", ShareLevel.VIEWER);
        assertEquals(1, recipientAceCount(101L, "bob"));
    }

    @Test
    @WithMockUser(username = "alice")
    void repeatedRevokeIsIdempotent() {
        sharing.revokeShare(101L, "bob");
        sharing.revokeShare(101L, "bob");
        assertEquals(0, recipientAceCount(101L, "bob"));
    }

    @Test
    @WithMockUser(username = "alice")
    void granteeAccessUsesActualMethodSecurity() {
        sharing.setShare(101L, "bob", ShareLevel.EDITOR);

        SecurityContextHolder.getContext().setAuthentication(bob());
        assertEquals("Alice draft", documents.read(101L));
        documents.rename(101L, "Bob edit");
        assertEquals("Bob edit", documents.read(101L));
    }

    @Test
    @WithMockUser(username = "bob")
    void nonOwnerCannotShareSomebodyElsesDocument() {
        assertThrows(AccessDeniedException.class,
            () -> sharing.setShare(101L, "manager1", ShareLevel.VIEWER));
        assertEquals(0, recipientAceCount(101L, "manager1")
            - countInitialAdminAceForManager());
    }

    private int countInitialAdminAceForManager() {
        return 1;
    }

    @Test
    @WithMockUser(username = "alice")
    void anEditorStillCannotReshare() {
        sharing.setShare(101L, "bob", ShareLevel.EDITOR);
        SecurityContextHolder.getContext().setAuthentication(bob());

        assertThrows(AccessDeniedException.class,
            () -> sharing.setShare(101L, "manager1", ShareLevel.VIEWER));
        assertEquals(1, recipientAceCount(101L, "manager1"));
    }

    @Test
    @WithMockUser(username = "manager1", roles = "TENANT_ADMIN")
    void tenantAdminWithAclAdministrationAceMayShare() {
        sharing.setShare(101L, "bob", ShareLevel.VIEWER);
        assertTrue(bobCanRead(101L));
        assertEquals(1, recipientAceCount(101L, "bob"));
    }

    @Test
    @WithMockUser(username = "manager1", roles = "TENANT_ADMIN")
    void tenantAdminCannotShareAcrossTenants() {
        assertThrows(AccessDeniedException.class,
            () -> sharing.setShare(201L, "dave", ShareLevel.EDITOR));
        assertEquals(0, recipientAceCount(201L, "dave"));
    }

    @Test
    @WithMockUser(username = "manager1", roles = "TENANT_ADMIN")
    void tenantAdminWithoutObjectAclAdminAceCannotChangeAnotherAcl() {
        assertThrows(AccessDeniedException.class,
            () -> sharing.setShare(102L, "alice", ShareLevel.VIEWER));
        assertEquals(0, recipientAceCount(102L, "alice"));
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerCannotShareToUserInDifferentTenant() {
        assertThrows(IllegalArgumentException.class,
            () -> sharing.setShare(101L, "carol", ShareLevel.VIEWER));
        assertEquals(0, recipientAceCount(101L, "carol"));
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerCannotShareWithSelf() {
        assertThrows(IllegalArgumentException.class,
            () -> sharing.setShare(101L, "alice", ShareLevel.EDITOR));
        assertEquals(0, recipientAceCount(101L, "alice"));
    }

    @Test
    @WithMockUser(username = "alice")
    void nullShareLevelRejectedWithoutGrant() {
        assertThrows(IllegalArgumentException.class,
            () -> sharing.setShare(101L, "bob", null));
        assertEquals(0, recipientAceCount(101L, "bob"));
    }

    @Test
    @WithMockUser(username = "alice")
    void unknownDocumentIsDeniedBeforeAclMutation() {
        assertThrows(AccessDeniedException.class,
            () -> sharing.setShare(999L, "bob", ShareLevel.VIEWER));
    }

    @Test
    @WithMockUser(username = "carol", roles = "TENANT_ADMIN")
    void roleWithoutTenantAdminBindingCannotManageT1() {
        assertThrows(AccessDeniedException.class,
            () -> sharing.setShare(101L, "bob", ShareLevel.VIEWER));
    }

    @Test
    @WithMockUser(username = "alice")
    void aclOwnerNotAutomaticallyGrantedBusinessRead() {
        assertThrows(AccessDeniedException.class,
            () -> documents.read(101L));
    }
}
```

Run command:

```bash
mvn test
```

**Expected by design:** 18 JUnit tests, all passing. This is an **expected outcome**, not an executed test log. The tests use `@DirtiesContext` to avoid leftover shared state between tests; this is slow but easy to follow. They exercise real `AclPermissionEvaluator` and `@PreAuthorize`, while Authentication is simulated via `@WithMockUser` or in-memory tokens; they **do not test** passwords/JWTs or membership propagation from an external IAM.

### 7.1. Interpreting the Core Test Results

| Scenario | Bob's ACE mask on #101 | Bob READ | Bob WRITE | Consequence |
|---|---:|:---:|:---:|---|
| Not yet shared | None | ✗ | ✗ | Default deny if no other source |
| Alice grants VIEWER | 1 | ✓ | ✗ | `insertAce` |
| Alice upgrades to EDITOR | 3 | ✓ | ✓ | `updateAce` |
| Alice downgrades to VIEWER | 1 | ✓ | ✗ | `updateAce` |
| Alice revokes | None | ✗ | ✗ | `deleteAce` |

The "Editor cannot reshare" test shows Bob can edit content once granted EDITOR yet cannot grant permissions to others, because `SharePolicy` does not recognize Bob as owner or tenant admin and the framework never gave Bob an ADMINISTRATION ACE.

The "Tenant admin without object ACL admin ACE" test demonstrates two protection layers: the tenant admin passes `SharePolicy` yet **fails** `AclAuthorizationStrategy` on an ACL where they are not owner, hold no ADMINISTRATION ACE, and have no system-wide authority. Never assume passing one layer implies sufficient permissions across all layers.

## 8. Extension Points in Real Applications

### 8.1. Beware updateAcl Deleting and Recreating ACEs

Because `JdbcMutableAclService.updateAcl` recreates all `acl_entry` rows, a concurrent service that:
- reads the old ACL;
- edits one ACE;
- writes back the old ACE list;
can overwrite another service's newly added grant. This is the **lost update** problem. `@Transactional` protects one transaction, yet does not automatically provide optimistic locking on the ACL object to arbitrate two concurrent edit requests.

Ways to mitigate this risk:
- Lock `acl_object_identity` by object ID before modifying within the same transaction.
- Use an application-level version/optimistic concurrency mechanism.
- Funnel sharing operations for a document through a serialization boundary.
- Enforce unique business-level invariants for personal share ACEs and reconcile existing data explicitly.
- Test races when two requests share or revoke on the same document concurrently.

The default ACL schema provides no version column on `acl_object_identity`. If you add versioning, design persistence/queries and update strategies to match.

### 8.2. ACL Cache and Revocation Latency

`SpringCacheBasedAclCache` can serve previously loaded ACLs. Modifying ACLs through `JdbcMutableAclService` manages the cache per the implementation; however, direct SQL edits or running multiple nodes with per-JVM caches can delay revocation enforcement.

Test revocation across multi-instance environments, define appropriate invalidation events, TTLs, or shared caches, and address revoked permissions inside JWTs/Authentications. **Never treat a single-JVM test as proof of immediate cluster-wide revocation.**

### 8.3. Changing Owners, Moving Tenants, and Parent ACLs

`MutableAcl.setOwner(...)` changes the **ACL owner**; it is distinct from updating `document.owner_username` in the domain. Changing only one table leaves the two owners out of sync, causing inconsistent administrative decisions. Moving tenants also requires reviewing old grants, memberships, ACL inheritance, and role SIDs; implement a dedicated workflow rather than repurposing `setShare` as a shortcut to transfer ownership.

`setParent(...)` and `setEntriesInheriting(...)` can introduce inherited permissions. Revoking a child ACE while a parent ACL still grants access leaves the user with access. Test combined ACLs rather than inspecting only local `acl_entry` rows.

### 8.4. Group Sharing and Authority SIDs

`GrantedAuthoritySid("ROLE_TEAM_EDITOR")` grants permissions to everyone holding that authority. A group-sharing API endpoint must verify the group belongs to the right tenant and the caller is permitted to grant to the **entire group**. Never let clients pass an un-allowlisted SID string, which could grant access to `ROLE_EVERYONE` or a sensitive group.

Separate `share:principal` from `share:group` actions if their risk profiles differ. With dynamic groups, membership changes can expand who holds access without adding new ACEs; audit group memberships accordingly.

### 8.5. Granular Permissions and Anti-Escalation

If a sharer only has VIEWER, they must not be able to grant EDITOR. If policy permits EDITORs to share, at minimum require SHARE rights and forbid granting levels higher than their own. In particular, **never expose a public method accepting an arbitrary `Permission` or integer mask** and passing it straight to `acl.insertAce(index,mask,sid,true)`. Inputs must be constrained to a business allowlist and checked against the real resource.

### 8.6. Auditing Sharing Actions

A grant/revoke audit log should capture:
- actor and authenticated identity;
- tenant ID and document ID;
- recipient SID type + SID value;
- old permission mask / new mask;
- event type: GRANTED, CHANGED, REVOKED, DENIED;
- timestamp, request ID, reason, and policy version.

The two `audit_success`/`audit_failure` flags on an ACE do not automatically build an ACE change history. `ConsoleAuditLogger` in the example is a technical illustration, lacking durability and immutability for production. For compliance needs, use durable, tamper-evident audit logging with clear failure handling.

### 8.7. Transactions and Post-Commit Notifications

A request may both grant a share and send an invitation email. If the email is sent **before the transaction commits** and the DB rolls back, the recipient gets a broken link. If sent after commit and the process crashes beforehand, the notification is lost. For reliable delivery, use a transactional outbox or retry/idempotency mechanisms.

**Key takeaway:** Never use `@PostAuthorize` to decide who may share after already modifying the ACL. Enforce policy before calling mutators, and emit notifications only after the authorized change has committed successfully.

## 9. Common Mistakes and How to Fix Them

| Mistake | Outcome | Fix |
|---|---|---|
| Using `BasePermission.WRITE` as share permission | Editors can grant permissions to others | Separate share/ACL admin from business WRITE |
| Calling `insertAce` without checking actor | Sharing API gets abused | `@PreAuthorize` + `AclAuthorizationStrategy` |
| Treating `ROLE_TENANT_ADMIN` as enough to edit any ACL | Cross-tenant/object privilege expansion | Per-tenant role binding plus ADMINISTRATION ACE or proven ACL admin policy |
| Skipping `validateRecipient` | Sharing to users in other tenants or nonexistent users | Validate grantees against a trusted directory |
| Calling `updateAce(index, WRITE)` to upgrade to EDITOR | Recipient can lose READ | Use mask 3 or two explicit ACEs |
| Reusing an old `ace_order` to update | Edits the wrong ACE after insert/delete | Read fresh ACL, locate by SID and policy |
| Using a deny ACE to revoke a grant | Causes unintended precedence/inheritance effects | Use `deleteAce` when simply removing a grant |
| Deleting multiple ACEs front-to-back | Indices shift, wrong entries deleted | Iterate back-to-front |
| Calling `updateAcl` assuming it updates one row | ACE PKs change, lost updates | Understand JDBC persistence and add concurrency control |
| Writing directly to `acl_entry` without cache eviction | Revocations do not take effect immediately | Use service APIs and ensure cache eviction |
| Letting clients supply raw `Sid` or mask | Can grant ADMINISTRATION or broad groups | Allowlist recipient types and share levels |
| ACL owner and document owner out of sync | Surprising admin privileges | Use atomic owner/tenant transfer workflows |
| Ignoring inherited permissions | Revoked user still has access | Check parent/inheritance/role ACEs |
| Protecting only HTTP endpoints | Jobs calling services can bypass checks | Enforce checks at service boundaries |
| Self-invocation inside the same bean | Bypasses Spring AOP | Invoke through Spring-managed proxy |
| No ACL created when creating a document | Access fails or errors occur | Provision ACL intentionally on resource creation |
| Cache lacking scope/policy version | Serves stale or cross-tenant decisions | Design proper invalidation/versioning |
| Knowing username without tenant | Cross-organization sharing | Check canonical document and tenant directory |

## 10. Self-Check Questions

**Question 1.** Bob has a WRITE ACE on Document#101. Can Bob call the sharing API to grant WRITE to Mallory?

**Answer:** Not under this lesson's policy. WRITE grants content editing, whereas sharing requires the owner/tenant-admin policy and proper ACL modification rights. Never infer ACL administration rights from business WRITE.

**Question 2.** Can `updateAce(index, BasePermission.WRITE)` cause Bob to lose read permission?

**Answer:** Yes. It replaces the ACE's permission mask, so the READ bit may no longer be set. To represent EDITOR with both READ and WRITE, use two ACEs or `CumulativePermission` with mask 3 and test it.

**Question 3.** After `revokeShare(101L,"bob")`, can Bob still read if a parent ACL grants READ to a role Bob holds?

**Answer:** Possibly. Revoking removes only the individual grant; ACL inheritance or another authority SID can still grant access. Test all combined permission sources before claiming total denial.

**Question 4.** A tenant admin passes business policy, yet is neither ACL owner nor holder of an ADMINISTRATION ACE; will ACL updates always succeed?

**Answer:** No. `AclAuthorizationStrategyImpl` still performs its own check on ACL-mutation methods; the test suite demonstrates this exact case.

**Question 5.** Why shouldn't `acl_entry.id` be used as a stable share identifier?

**Answer:** Under `JdbcMutableAclService.updateAcl`, all ACEs may be deleted and recreated, changing PKs. Shares should be identified by object identity, SID, permission/action, and clear uniqueness policies.

## 11. Safe Implementation Checklist

- [ ] Clearly define which actors may manage ACLs; scope owners and tenant admins explicitly.
- [ ] Enable `@EnableMethodSecurity` and invoke services through Spring-managed proxies.
- [ ] Configure `AclAuthorizationStrategy` separately from business permissions; avoid overly broad system-wide authorities.
- [ ] Use accurate class + ID in `ObjectIdentity`; create/read ACLs via `MutableAclService`.
- [ ] Verify recipients belong to the right tenant; never trust client-declared roles/groups.
- [ ] Restrict the sharing API to allowlisted permission levels; reject raw masks or ADMINISTRATION on the same endpoint.
- [ ] Pass valid list indices to `insertAce`, use `updateAce` only for mask updates, and delete exact indices with `deleteAce`.
- [ ] Persist all changes via `updateAcl` inside an appropriate transaction.
- [ ] Define policies for duplicate ACEs/deny ACEs/inheritance; never silently corrupt unfamiliar entries.
- [ ] Add concurrency control when multiple requests edit the same ACL.
- [ ] Write real tests for allow/deny, viewer/editor, upgrade/downgrade, revoke, cross-tenant users, admins lacking ACEs, and owners without READ.
- [ ] Establish revocation and invalidation strategies for caches and clusters.
- [ ] Log durable audits for sharing actions with actor, recipient, old/new permission, target, and reason.
- [ ] Enforce tenant and business permissions on every data read/write flow; ACLs do not enforce tenant boundaries by default.

## 12. Official Documentation

- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): `insertAce` operations, `MutableAclService`, domain object permissions, and ACL configuration.
- [Spring Security 6.5 — MutableAcl API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/acls/model/MutableAcl.html): `insertAce`, `updateAce`, `deleteAce`, `setOwner`, `setParent`.
- [Spring Security 6.5 — AclAuthorizationStrategyImpl API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/acls/domain/AclAuthorizationStrategyImpl.html): owner, system-wide authority, and `BasePermission.ADMINISTRATION` when modifying ACLs.
- [Spring Security 6.5 — JdbcMutableAclService API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/acls/jdbc/JdbcMutableAclService.html): `createAcl`, `updateAcl`, `deleteAcl`, and persistence semantics.
- [Spring Security 6.5 — Security Database Schema](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html): the four ACL tables and HSQLDB DDL.
- [Spring Security 6.5 — CumulativePermission API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/acls/domain/CumulativePermission.html): representing multi-bit permissions.
- [Spring Security 6.5 — DefaultPermissionGrantingStrategy API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html): ACE order, grant/deny decisions, and permission matching.

**Remember:** `insertAce`, `updateAce`, and `deleteAce` are merely ACL data operations. A secure sharing system must verify **that the caller is allowed to share, the recipient is valid, granted levels stay within bounds, transactions/caches stay consistent, and revocations truly take effect**, alongside the framework's ACL administration checks. Content-editing rights do not imply ACE administration rights; a tenant admin must never cross tenant boundaries solely because of an admin role.
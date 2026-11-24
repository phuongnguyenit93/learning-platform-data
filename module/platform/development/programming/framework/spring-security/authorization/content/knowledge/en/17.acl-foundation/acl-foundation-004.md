# BasePermission, Permission Masks, and Custom Permissions in Spring Security ACL

## 1. Problem and Scope

In a document management system, Alice may view document 42 without deleting it; Bob may export document 42 to PDF without approving it. Checking `hasAuthority('EDITOR')` only indicates a general authority, whereas answering "who has what permission **on this exact document**" requires a resource-level authorization model.

**ACL (Access Control List)** in Spring Security attaches **ACEs (Access Control Entries)** to individual objects. Each ACE specifies whether a **SID** (user/authority) is *granted* or *denied* a **Permission** on a specific **ObjectIdentity**. `BasePermission` provides five standard permissions represented as bitmasks.

Learning objectives:

1. Understand Permission, BasePermission, permission mask, SID, ACL, and ACE.
2. Accurately recall READ=1, WRITE=2, CREATE=4, DELETE=8, ADMINISTRATION=16.
3. Practice bitwise OR/AND/NOT and bitmask checks without confusing them with authorization outcomes.
4. Create application permissions such as EXPORT=32, APPROVE=64 without bit collisions.
5. Know how to use `CumulativePermission`, `PermissionFactory`, `AclPermissionEvaluator`, and `hasPermission`.
6. Understand why grant/deny, ACL inheritance, permission/SID ordering, and granting strategies cannot be inferred from mask numbers alone.
7. Test the full lifecycle of saving ACEs, reloading ACLs, authorizing access, and revoking permissions.

This lesson covers **Spring Security ACL**, not OS file permissions, JWT scopes, or general `GrantedAuthority` lists. Applications that only need a few roles and tenant-scoped permissions may not need a full ACL system yet.

## 2. The ACL Model: Who, Which Resource, What Permission?

```text
Authentication:
  name = alice
  authorities = ROLE_EDITOR, DOC_READ
        |
        v
Sid (Security Identity):
  PrincipalSid("alice")
  GrantedAuthoritySid("ROLE_EDITOR")
        |
        v
ObjectIdentity:
  type = com.acme.Document
  id   = 42
        |
        v
ACL of Document 42:
  ACE Alice       READ   mask=1   granting=true
  ACE Alice       WRITE  mask=2   granting=false
  ACE ROLE_EDITOR EXPORT mask=32  granting=true
        |
        v
PermissionGrantingStrategy:
  evaluates ACEs/SIDs, grant/deny, parent ACL, permissions...
        |
        v
Allow / Deny decision
```

| Concept | Function |
| --- | --- |
| `Permission` | Object representing a permission via bitmask and display code |
| `BasePermission` | Standard ACL permissions |
| `Sid` | Identity of a principal or a granted authority |
| `ObjectIdentity` | Identity of a resource by type + ID |
| `Acl` | ACL info for an object, list of ACEs, owner, parent |
| `AccessControlEntry` | Which SID is granted/denied which permission |
| `AclService` | Reads ACLs |
| `MutableAclService` | Creates, updates, and deletes ACLs |
| `PermissionGrantingStrategy` | Computes decision across multiple ACEs/SIDs |
| `PermissionFactory` | Converts names or masks into Permission instances |

**Distinction:** `ROLE_EDITOR` is a user's authority information; `BasePermission.WRITE` is a permission on an ACL object. `hasRole('EDITOR')` and `hasPermission(#id, 'com.acme.Document', 'WRITE')` are not the same check.

The relevant classes live in `org.springframework.security.acls.domain` and `org.springframework.security.acls.model`. The Spring ACL library requires the dedicated dependency `org.springframework.security:spring-security-acl`; it is not all automatically included just by enabling `spring-boot-starter-security`.

## 3. The Five Default BasePermission Rights

| Permission | 0-Based Bit Index | Bit Shift | Decimal Mask | Binary (Lowest 8 Bits) |
| --- | ---: | --- | ---: | --- |
| `BasePermission.READ` | 0 | `1 << 0` | **1** | `0000 0001` |
| `BasePermission.WRITE` | 1 | `1 << 1` | **2** | `0000 0010` |
| `BasePermission.CREATE` | 2 | `1 << 2` | **4** | `0000 0100` |
| `BasePermission.DELETE` | 3 | `1 << 3` | **8** | `0000 1000` |
| `BasePermission.ADMINISTRATION` | 4 | `1 << 4` | **16** | `0001 0000` |

Reading values in Java:

```java
import org.springframework.security.acls.domain.BasePermission;

int read = BasePermission.READ.getMask();                // 1
int write = BasePermission.WRITE.getMask();              // 2
int create = BasePermission.CREATE.getMask();            // 4
int delete = BasePermission.DELETE.getMask();            // 8
int administration = BasePermission.ADMINISTRATION.getMask(); // 16
```

**Remember two things:**

- A larger mask number **does not mean higher privilege**. ADMINISTRATION=16 is simply a different bit from READ=1. It **does not automatically** imply READ/WRITE/DELETE. If an admin gets multiple actions, policies/ACEs must explicitly define and test them.
- "32-bit permission mask" **does not** mean you can only manage 32 documents. Each bit represents a permission type; the number of documents is represented by rows in `ObjectIdentity`/`ACL_OBJECT_IDENTITY`, which can be huge.

`CREATE` also does not automatically define permission to create a *not-yet-existing* document. You typically decide whether creation rights attach to a parent folder/project or a separate method-security policy.

## 4. Computing Masks with Bitwise Operators

### 4.1. Left Shift: `1 << n`

```java
int READ = 1 << 0;      // 1
int WRITE = 1 << 1;     // 2
int CREATE = 1 << 2;    // 4
int DELETE = 1 << 3;    // 8
int ADMIN = 1 << 4;     // 16
int EXPORT = 1 << 5;    // 32 (new permission)
int APPROVE = 1 << 6;   // 64 (new permission)
```

Individual bits do not overlap. Two business permissions must never share the same bit if both are interpreted within the same ACL namespace.

### 4.2. OR `|`: Combining Bits

```java
int combined = READ | WRITE | EXPORT; // 1 | 2 | 32 = 35
// binary: 0010 0011
```

The OR operation builds a **composite mask**. It does not create an ACE and does not grant permission to anyone yet.

### 4.3. AND `&`: Checking Bits

```java
boolean read = (combined & READ) == READ;            // true
boolean export = (combined & EXPORT) == EXPORT;      // true
boolean approve = (combined & APPROVE) == APPROVE;   // false
```

If **all** bits in a mask are required:

```java
static boolean includesAll(int granted, int required) {
    return required != 0 && (granted & required) == required;
}
```

If **at least one** bit is required:

```java
static boolean includesAny(int granted, int required) {
    return required != 0 && (granted & required) != 0;
}
```

For example, having only READ while requiring READ|EXPORT gives includesAll=false, includesAny=true. AND and OR are different policies and cannot be swapped arbitrarily.

**The `required=0` trap:** `(granted & 0) == 0` is always true. If mask 0 does not represent a valid permission, explicitly reject it.

### 4.4. Clearing Bits with `& ~`

```java
int withoutWrite = combined & ~WRITE; // 35 & ~2 = 33
```

Conversely, `combined ^ WRITE` is **XOR (toggle)**, which turns WRITE on if the bit was off. Never use XOR to revoke a permission because it can inadvertently grant it.

These operations only modify a Java `int` variable. In a real ACL, revoking a grant requires updating/deleting the ACE via `MutableAclService`; **changing a Java mask does not modify database tables**.

### 4.5. High Bits and Signed `int`

A mask is a 32-bit signed `int`. `1 << 31` sets the sign bit and displays as a negative number. Negative/positive sign **does not indicate grant or deny**: ACEs have a separate `granting` flag. Manage allocated bit positions carefully and test DB persistence/retrieval if high bits are needed.

## 5. Plain Java 17 Example Runnable with `javac`/`java`

File `PermissionMaskLab.java`:

```java
public final class PermissionMaskLab {

    private static final int READ = 1 << 0;
    private static final int WRITE = 1 << 1;
    private static final int CREATE = 1 << 2;
    private static final int DELETE = 1 << 3;
    private static final int ADMINISTRATION = 1 << 4;
    private static final int EXPORT = 1 << 5;
    private static final int APPROVE = 1 << 6;

    private PermissionMaskLab() {}

    private static boolean includesAll(int granted, int required) {
        return required != 0 && (granted & required) == required;
    }

    private static boolean includesAny(int granted, int required) {
        return required != 0 && (granted & required) != 0;
    }

    public static void main(String[] args) {
        System.out.println("Base: "
                + READ + "," + WRITE + "," + CREATE + ","
                + DELETE + "," + ADMINISTRATION);

        int mask = READ | WRITE | EXPORT;
        System.out.println("combined=" + mask);
        System.out.println("read=" + includesAll(mask, READ));
        System.out.println("approve=" + includesAll(mask, APPROVE));
        System.out.println("readAndExport="
                + includesAll(mask, READ | EXPORT));
        System.out.println("readOrApprove="
                + includesAny(mask, READ | APPROVE));

        mask = mask & ~WRITE;
        System.out.println("afterRevokeWrite=" + mask);
        System.out.println("writeAfterRevoke="
                + includesAll(mask, WRITE));
        System.out.println("maskZeroAllowed="
                + includesAll(mask, 0));
    }
}
```

In the directory containing the file, using JDK 17+:

```bash
javac PermissionMaskLab.java
java PermissionMaskLab
```

Exact stdout:

```text
Base: 1,2,4,8,16
combined=35
read=true
approve=false
readAndExport=true
readOrApprove=true
afterRevokeWrite=33
writeAfterRevoke=false
maskZeroAllowed=false
```

After ORing, the mask is 35 (READ+WRITE+EXPORT). Clearing WRITE leaves 33 (READ+EXPORT). `includesAll` explicitly blocks mask 0. This is pure Java bit arithmetic, **not** Spring's `Acl.isGranted` algorithm.

## 6. Creating Custom Permissions Using BasePermission

Suppose the business needs:

- EXPORT: generate PDF/CSV.
- APPROVE: approve document.
- PUBLISH: publish document.

Reserve bits 0–4 for `BasePermission`, assign bit 5 to EXPORT (32), and bit 6 to APPROVE (64). `BasePermission` exposes `protected BasePermission(int mask, char code)`, allowing subclassing.

`DocumentPermission.java`:

```java
package com.acme.security;

import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.model.Permission;

public final class DocumentPermission extends BasePermission {

    public static final Permission EXPORT =
            new DocumentPermission(1 << 5, 'E');

    public static final Permission APPROVE =
            new DocumentPermission(1 << 6, 'P');

    private DocumentPermission(int mask, char code) {
        super(mask, code);
    }
}
```

This code is for an application with the `spring-security-acl` dependency, not standalone `javac`. Characters `'E'`/`'P'` represent the bit when formatting `getPattern()`. **They are not the stored permission value in `ACL_ENTRY`**, nor do they automatically map the string `"EXPORT"` in expressions.

### The Permission Registry Must Stay Consistent

| Mask | Meaning |
| ---: | --- |
| 1 | READ |
| 2 | WRITE |
| 4 | CREATE |
| 8 | DELETE |
| 16 | ADMINISTRATION |
| 32 | EXPORT |
| 64 | APPROVE |
| 128 | PUBLISH, if allocated by the project |

Never assign the same mask to EXPORT and APPROVE. If both share mask 32, the DB has no way to distinguish them. Never arbitrarily change a mask after ACLs are persisted: if EXPORT moves from 32 to 128, existing ACEs still store 32 and require migration.

A good practice is centralizing permission constants in a shared module with a unit test that fails if two differently named permissions collide on the same mask. When multiple domain types share ACL infrastructure, clearly define whether permission bits are system-wide or per-domain rather than reusing them ambiguously.

## 7. CumulativePermission and Semantics of Composite Masks

Spring Security ACL provides `CumulativePermission` to toggle permission bits:

```java
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.CumulativePermission;

CumulativePermission permission = new CumulativePermission()
        .set(BasePermission.READ)
        .set(DocumentPermission.EXPORT);

int mask = permission.getMask();  // 33
permission.clear(BasePermission.READ);
int remaining = permission.getMask(); // 32
```

`set` turns bits on and `clear` turns bits off in the `Permission` object. It does not create or delete ACEs in the DB.

Distinguish between:

```java
// A single Permission with mask 33.
Permission combined = new CumulativePermission()
        .set(BasePermission.READ)
        .set(DocumentPermission.EXPORT);

// Two separate Permissions, in order.
List<Permission> separate =
        List.of(BasePermission.READ, DocumentPermission.EXPORT);
```

A mask of 33 **does not automatically mean** individual checks for READ or EXPORT will be granted; that depends on `PermissionGrantingStrategy`. Conversely, passing a list of two permissions **does not automatically mean both are required**: low-level `isGranted` logic evaluates permissions/SIDs according to the strategy and ordering.

If business rules require **both READ and EXPORT**, express that policy explicitly—for example, two independent checks combined with AND in the service/policy, or a custom ACL strategy with well-defined, tested semantics.

## 8. PermissionFactory: Linking Permission Names, Masks, and Objects

In an expression:

```java
@PreAuthorize("hasPermission(#p0, 'com.acme.Document', 'EXPORT')")
public byte[] export(long id) { /* ... */ }
```

`"EXPORT"` is a **permission name**. `PermissionFactory` must know it maps to `DocumentPermission.EXPORT`. `DefaultPermissionFactory()` registers the public constants on `BasePermission` by default; custom permissions must be registered.

```java
import java.util.Map;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.DefaultPermissionFactory;
import org.springframework.security.acls.domain.PermissionFactory;
import org.springframework.security.acls.model.Permission;

PermissionFactory factory = new DefaultPermissionFactory(
        Map.<String, Permission>of(
            "READ", BasePermission.READ,
            "WRITE", BasePermission.WRITE,
            "CREATE", BasePermission.CREATE,
            "DELETE", BasePermission.DELETE,
            "ADMINISTRATION", BasePermission.ADMINISTRATION,
            "EXPORT", DocumentPermission.EXPORT,
            "APPROVE", DocumentPermission.APPROVE
        ));

int exportMask = factory.buildFromName("EXPORT").getMask(); // 32
int restored = factory.buildFromMask(32).getMask();          // 32
```

This integration snippet assumes `DocumentPermission` is imported. Core APIs:

- `buildFromName(name)`: resolves a name to a `Permission`.
- `buildFromMask(mask)`: resolves a mask to a `Permission`.
- `buildFromNames(names)`: resolves a list of names to a list of `Permission`s.

In JDBC ACL setups, the factory can be used in **two places**:

1. `AclPermissionEvaluator.setPermissionFactory(factory)` when resolving permission names passed to `hasPermission`.
2. `BasicLookupStrategy.setPermissionFactory(factory)` to construct permission objects when reading rows from the DB.

Keep both synchronized if the application customizes permission mappings. Test after persisting and reloading to confirm custom permissions retain their identity across layers.

**Common mistake:** writing `"Export"` in SpEL when the registry only registers `"EXPORT"`. Do not assume case insensitivity.

## 9. The `granting` Flag and `mask` in `ACL_ENTRY` Are Separate Fields

One ACE might be:

```text
ObjectIdentity: com.acme.Document #42
SID: alice
MASK: 32
GRANTING: true
Meaning: Alice is allowed to EXPORT document 42
```

Another ACE:

```text
ObjectIdentity: com.acme.Document #42
SID: bob
MASK: 32
GRANTING: false
Meaning: Bob is denied EXPORT on document 42
```

Mask 32 is identical. It is `GRANTING` that distinguishes grant from deny. Never check `mask > 0` and allow access.

Spring ACL JDBC typically uses four tables:

| Table | Role |
| --- | --- |
| `ACL_CLASS` | Identifies domain object/class types |
| `ACL_SID` | User or authority SIDs |
| `ACL_OBJECT_IDENTITY` | A resource instance, owner, parent, and inheritance |
| `ACL_ENTRY` | Entries: object, SID, mask, granting, audit, order |

`PermissionGrantingStrategy` evaluates a requested permission against a SID's ACEs per framework rules. According to the `DefaultPermissionGrantingStrategy` Javadoc, the order of the permissions and SIDs lists matters; default mask matching compares the ACE's mask against the requested permission. Never replace it everywhere with `(aceMask & requested) != 0` while ignoring deny, inheritance, and ordering.

### Are Composite Masks Automatically Split into Individual Permissions?

**Never assume so.** A granting ACE with mask 33 (READ|EXPORT) is not automatically equivalent to two granting ACEs with masks 1 and 32 under `Acl.isGranted` in every configuration. Test with your actual configured `PermissionGrantingStrategy`. When checking individual rights separately, separate ACEs with single-bit masks are usually clearer.

### Having No ACE Does Not Mean Permitted

Three situations:

1. An explicit deny ACE for the matching SID/permission.
2. No matching ACE on the current object (parent ACL may still be consulted per policy).
3. No ACL exists for the object.

None of the three is a reason to grant access. Missing ACLs or DB errors may be handled with deny or an appropriate exception, but **never fail-open**.

## 10. ACL Inheritance and Custom Permissions

A resource's ACL can have a parent and `entriesInheriting`. A document can inherit policy from a parent folder when properly configured. Does EXPORT permission on the parent automatically apply to the child? Check:

- The `ObjectIdentity` of both parent and child.
- `Acl.isEntriesInheriting()` on the child.
- Which SID the ACE belongs to and whether `granting` is true or false.
- Whether `PermissionGrantingStrategy` is default or customized.
- Whether other permissions such as ADMINISTRATION or WRITE have separate ACEs.

Never conclude "deny always overrides every grant" or "child ACEs always override parent ACEs" without checking the actual strategy and ordering. With multiple SIDs (principal + roles), evaluation order is an essential part of the design.

When a resource moves folders, changes owners, or switches tenants, parent ACLs/caches may need updates. Document ID 42 in tenant A and document ID 42 in tenant B must never accidentally share an `ObjectIdentity`; the system must guarantee globally unambiguous identities.

## 11. Persisting Custom ACEs via MutableAclService

The following integration snippet illustrates granting EXPORT to Alice on document 42. It **cannot run on its own** without a `DataSource`, the four ACL tables, `LookupStrategy`, `AclCache`, and `MutableAclService`.

```java
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;

public final class DocumentAclWriter {

    private final MutableAclService aclService;

    public DocumentAclWriter(MutableAclService aclService) {
        this.aclService = aclService;
    }

    public void grantExport(long id, String user) {
        ObjectIdentity oid =
                new ObjectIdentityImpl("com.acme.Document", id);
        Sid sid = new PrincipalSid(user);

        MutableAcl acl;
        try {
            acl = (MutableAcl) aclService.readAclById(oid);
        } catch (NotFoundException notFound) {
            acl = aclService.createAcl(oid);
        }

        acl.insertAce(
                acl.getEntries().size(),
                DocumentPermission.EXPORT,
                sid,
                true);

        aclService.updateAcl(acl);
    }
}
```

Explanation:

- `ObjectIdentityImpl` pairs type `"com.acme.Document"` with the ID. The type must match `ACL_CLASS` and the type string in `hasPermission` expressions.
- `PrincipalSid(user)` grants the permission to a principal. For a group, use `GrantedAuthoritySid`.
- `insertAce(index, permission, sid, true)` creates a granting ACE; passing `false` creates a deny ACE, **not** a revocation/deletion.
- `acl.getEntries()` in current Spring Security APIs returns `List<AccessControlEntry>`, hence `.size()`.
- `aclService.updateAcl(acl)` persists changes. JDBC mutable ACL implementations may delete and re-insert entries on update, so use transactions, auditing, and concurrency locking where appropriate.

Never invoke this method from an unguarded public endpoint. **ACL management permissions** must be protected independently of read/view/download permissions on the document; never let a user with READ grant themselves EXPORT or ADMINISTRATION.

### Saving READ and EXPORT as Two Explicit ACEs

```java
acl.insertAce(acl.getEntries().size(),
        BasePermission.READ, new PrincipalSid("alice"), true);

acl.insertAce(acl.getEntries().size(),
        DocumentPermission.EXPORT, new PrincipalSid("alice"), true);

aclService.updateAcl(acl);
```

This assumes `acl` and `aclService` are already initialized. If your system uses permission lists or composite masks, test precisely how grants/denies are evaluated; two separate ACEs are usually easier to reason about when business logic checks individual rights.

## 12. Wiring AclPermissionEvaluator with @PreAuthorize

Execution flow:

```text
@PreAuthorize("hasPermission(#p0, 'com.acme.Document', 'EXPORT')")
        |
        v
Method security expression handler
        |
        v
AclPermissionEvaluator
  -> PermissionFactory: EXPORT -> mask 32
  -> Authentication -> principal/authority SIDs
  -> ObjectIdentity("com.acme.Document", id)
        |
        v
AclService / LookupStrategy / ACL_... database
        |
        v
Acl + PermissionGrantingStrategy
        |
        v
Allow or deny method invocation
```

Configuration directly related to permissions (**integration** example; excludes full JDBC ACL infrastructure):

```java
@Configuration
@EnableMethodSecurity
class AclSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    PermissionFactory permissionFactory() {
        return new DefaultPermissionFactory(
                Map.<String, Permission>of(
                    "READ", BasePermission.READ,
                    "WRITE", BasePermission.WRITE,
                    "CREATE", BasePermission.CREATE,
                    "DELETE", BasePermission.DELETE,
                    "ADMINISTRATION", BasePermission.ADMINISTRATION,
                    "EXPORT", DocumentPermission.EXPORT,
                    "APPROVE", DocumentPermission.APPROVE));
    }

    @Bean
    AclPermissionEvaluator aclPermissionEvaluator(
            AclService service, PermissionFactory factory) {
        AclPermissionEvaluator evaluator =
                new AclPermissionEvaluator(service);
        evaluator.setPermissionFactory(factory);
        return evaluator;
    }
}
```

Corresponding imports:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.DefaultPermissionFactory;
import org.springframework.security.acls.domain.PermissionFactory;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.Permission;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

You must import your application's `DocumentPermission`. `@Bean static` for the handler follows the Spring Security documentation pattern when providing a custom handler early. Do not register a second handler bean that inadvertently overrides `RoleHierarchy` or `PermissionEvaluator` configuration.

`BasicLookupStrategy` also has `setPermissionFactory(factory)`; applications with custom permissions need to ensure the factory is supplied when constructing the LookupStrategy so ACL loading and expressions stay consistent.

Usage:

```java
@PreAuthorize("hasPermission(#p0, 'com.acme.Document', 'EXPORT')")
public byte[] exportDocument(long id) {
    return documentExportService.buildExport(id);
}
```

this code is an **integration method**, where `documentExportService` is supplied by the project. The method must be invoked **through a Spring-managed proxy** under `@EnableMethodSecurity`, not via `new` instantiation or proxy-bypassing self-invocation.

The two-argument form `hasPermission(document, 'EXPORT')` is used with an **existing domain object**, while the three-argument form `hasPermission(id, type, permission)` is for IDs. Never use a target object whose owner/tenant fields are client-supplied as authorization input.

## 13. Java 17 Example Using Spring ACL API with Maven

The following project uses real `BasePermission`, `CumulativePermission`, and `DefaultPermissionFactory` with no DB required. Layout:

```text
spring-acl-mask-demo/
├── pom.xml
└── src/main/java/demo/
    ├── DocumentPermission.java
    └── AclMaskDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-acl-mask-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-acl</artifactId>
      <version>6.5.7</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
```

`src/main/java/demo/DocumentPermission.java`:

```java
package demo;

import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.model.Permission;

public final class DocumentPermission extends BasePermission {
    public static final Permission EXPORT =
            new DocumentPermission(1 << 5, 'E');
    public static final Permission APPROVE =
            new DocumentPermission(1 << 6, 'P');

    private DocumentPermission(int mask, char code) {
        super(mask, code);
    }
}
```

`src/main/java/demo/AclMaskDemo.java`:

```java
package demo;

import java.util.Map;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.CumulativePermission;
import org.springframework.security.acls.domain.DefaultPermissionFactory;
import org.springframework.security.acls.domain.PermissionFactory;
import org.springframework.security.acls.model.Permission;

public final class AclMaskDemo {

    public static void main(String[] args) {
        PermissionFactory factory =
                new DefaultPermissionFactory(
                    Map.<String, Permission>of(
                        "READ", BasePermission.READ,
                        "WRITE", BasePermission.WRITE,
                        "CREATE", BasePermission.CREATE,
                        "DELETE", BasePermission.DELETE,
                        "ADMINISTRATION", BasePermission.ADMINISTRATION,
                        "EXPORT", DocumentPermission.EXPORT,
                        "APPROVE", DocumentPermission.APPROVE));

        CumulativePermission combined = new CumulativePermission()
                .set(BasePermission.READ)
                .set(BasePermission.WRITE)
                .set(DocumentPermission.EXPORT);

        System.out.println("read=" + BasePermission.READ.getMask());
        System.out.println("write=" + BasePermission.WRITE.getMask());
        System.out.println("export=" + DocumentPermission.EXPORT.getMask());
        System.out.println("combined=" + combined.getMask());
        System.out.println("factoryExport="
                + factory.buildFromName("EXPORT").getMask());
        System.out.println("factoryMask="
                + factory.buildFromMask(combined.getMask()).getMask());

        combined.clear(BasePermission.WRITE);
        System.out.println("afterClearWrite=" + combined.getMask());
        System.out.println("patternLength=" + combined.getPattern().length());
    }
}
```

Commands to run with Maven and JDK 17+:

```bash
mvn -q compile
mvn -q exec:java -Dexec.mainClass=demo.AclMaskDemo
```

Lines the application is designed to output:

```text
read=1
write=2
export=32
combined=35
factoryExport=32
factoryMask=35
afterClearWrite=33
patternLength=32
```

These values have been cross-checked against the code logic and Spring Security ACL API. **The Maven build was not executed directly** while authoring this lesson; run it on a machine with Maven/JDK to verify end-to-end. This is an example of permission representation, **not** an integration test against DB ACLs/`PermissionGrantingStrategy`. The dependency version is pinned for API study; production apps should use a supported release branch with Spring Security modules aligned via BOM.

## 14. Real ACL Test Matrix

Do not stop at bitmask unit tests. Verify the system with `AclService`, database, and method security proxies.

| Scenario | Expectation |
| --- | --- |
| BasePermission.READ mask | 1 |
| BasePermission.WRITE mask | 2 |
| BasePermission.CREATE mask | 4 |
| BasePermission.DELETE mask | 8 |
| BasePermission.ADMINISTRATION mask | 16 |
| Custom EXPORT, APPROVE | 32, 64; no collisions |
| `CumulativePermission.set(READ).set(EXPORT)` | Mask 33 |
| `factory.buildFromName("EXPORT")` | Mask 32 |
| Alice has READ grant ACE on Document 42 | `hasPermission` READ allowed |
| Alice lacks EXPORT ACE | EXPORT denied |
| Add EXPORT grant ACE and reload | EXPORT allowed; cache updated properly |
| Bob has explicit deny EXPORT | EXPORT denied |
| ROLE_EDITOR has EXPORT ACE on Document 42 | Only subjects with matching SID granted |
| Parent ACL grants and child inheriting toggled on/off | Inheritance follows policy |
| Composite ACE 33, queried for 1/32/33 | Assert against real strategy, do not guess |
| Resource differs in ID/type/tenant | Does not use wrong ACL |
| Missing ACL, missing SID, or DB error | Never fail-open |
| Caller has READ and attempts to add ADMINISTRATION ACE for self | Rejected by ACL management API |
| Service invoked through proxy with `@PreAuthorize` | Denied when permission is missing |

When changing a persisted permission mask, run migrations and regression tests for both old and new permissions. If caching is enabled, revocation tests must demonstrate that the old grant disappears after update/invalidation.

### Multiple SIDs and Deny/Grant Scenarios

A user may have both `PrincipalSid("alice")` and `GrantedAuthoritySid("ROLE_EDITOR")`. A deny ACE for the principal and a grant ACE for the role may require specific resolution rules. `DefaultPermissionGrantingStrategy` evaluates permissions and SIDs in order; never jump to "deny always overrides every grant" or "role always overrides user" without checking your strategy/configuration and testing it.

## 15. Mistakes and How to Avoid Them

**1. Colliding new bits with existing permissions.** If EXPORT and APPROVE both equal 32, ACEs cannot distinguish them. Use a single permission registry.

**2. Changing bit meanings after data exists.** Masks stored in `ACL_ENTRY` do not migrate automatically; you need a data migration process.

**3. Thinking a positive mask means grant.** The mask identifies the permission; `granting` determines allow vs deny.

**4. Assuming ADMINISTRATION implies READ/WRITE/DELETE.** Bits are independent. Design an explicit admin override if business requires it.

**5. Treating `(aceMask & required) != 0` as Spring ACL's default rule.** That is just a bit operation. `PermissionGrantingStrategy` defines the semantics, including SIDs, denies, and parent ACLs.

**6. Using `List.of(READ, EXPORT)` as if it guarantees "both required."** Not by default. Define an explicit AND policy and test it.

**7. Using XOR to revoke.** XOR can add permissions. For persisted ACLs, operate on ACEs rather than flipping bits in a variable.

**8. Forgetting to register custom permission names in PermissionFactory.** `hasPermission(..., 'EXPORT')` will not recognize custom permissions automatically.

**9. Mismatched `targetType`.** `"Document"` differs from `"com.acme.Document"` if `ACL_CLASS` stores the latter. Keep them consistent.

**10. Reading `ACL_ENTRY.MASK` and deciding without checking SID/grant/inheritance.** Omits critical data and introduces vulnerabilities.

**11. Making decisions from client-supplied owner/tenant fields on objects.** Trust only server-verified identities and resource metadata.

**12. Letting document users modify ACLs.** Risks privilege escalation. Protect ACL admin/mutator services separately.

**13. Ignoring caches/transactions during ACL updates.** Can cause stale grants, lost updates, or ACLs out of sync with resources.

**14. Sharing the same ObjectIdentity across tenants with colliding IDs.** Make identities sufficiently unique so ACLs never leak across tenants.

**15. Assuming annotations run on `new Service()` or `this.method()`.** With Spring AOP proxy mode, calls must pass through a valid proxy.

## 16. Production Checklist

- [ ] Distinguish `Permission` from roles/`GrantedAuthority` and `Sid`.
- [ ] Five standard masks are strictly 1, 2, 4, 8, 16.
- [ ] Custom permissions use unused, non-overlapping bits and never change after ACEs are saved.
- [ ] Know how to combine/test bits with OR, AND, NOT without confusing them with grant/deny.
- [ ] Every ACE has accurate ObjectIdentity, SID, Permission, granting, and audit fields.
- [ ] `PermissionFactory` resolves custom names/masks; evaluator and lookup strategy share consistent mappings.
- [ ] `CumulativePermission` is used only with tested semantics.
- [ ] Dedicated tests exist for default/custom `PermissionGrantingStrategy`, SID ordering, deny, and inheritance.
- [ ] ACLs are created/updated/deleted in sync with resource lifecycles, transactions, and caches.
- [ ] ACE/ACL administration APIs are protected independently of document read/write APIs.
- [ ] No grant occurs when ACL, user, permission data is missing or backend fails.
- [ ] ObjectIdentity never collides across tenants.
- [ ] Method security and Spring-managed proxies are configured and tested.
- [ ] Unit tests cover masks/factory and integration tests cover real JDBC ACLs/`hasPermission`.

**Key takeaway:** `BasePermission` defines standard rights; **masks** are merely bit encodings; `CumulativePermission` represents combinations; `PermissionFactory` translates names and masks; and **Acl + ACE + PermissionGrantingStrategy** actually decide *who holds which permission on which resource*. Custom permissions must have stable, non-overlapping masks, be registered, and be tested as part of your security policy.

## Official Docs

- [Spring Security — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html)
- [Spring Security — BasePermission JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/BasePermission.html)
- [Spring Security — CumulativePermission JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/CumulativePermission.html)
- [Spring Security — DefaultPermissionFactory JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionFactory.html)
- [Spring Security — DefaultPermissionGrantingStrategy JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html)
- [Spring Security — AclPermissionEvaluator JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/AclPermissionEvaluator.html)

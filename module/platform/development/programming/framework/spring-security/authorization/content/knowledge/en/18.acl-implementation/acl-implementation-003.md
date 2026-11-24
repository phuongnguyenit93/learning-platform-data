# `AclAuthorizationStrategy` and `PermissionGrantingStrategy` in Spring Security ACL

## 1. Two Security Strategies Answering Two Different Questions

Consider the ACL for `Document#42`:

- `alice` is the **ACL owner** (`Acl.getOwner()`).
- `bob` has a `READ GRANT` ACE on the document.
- `carol` has a `READ DENY` ACE.
- `dave` has an `ADMINISTRATION GRANT` ACE.
- `root` has the system-wide `GrantedAuthority` `ROLE_ACL_ADMIN`.

Do not jump to the conclusion that `alice` can read the document or `bob` can modify the ACL. The system must answer **two independent questions**:

1. **Who is allowed to modify the permission list itself?** For example, adding ACEs, deleting ACEs, changing the ACL owner, or changing audit settings. This is the responsibility of `AclAuthorizationStrategy`.
2. **Who is allowed to perform an action on the protected object?** For example, `READ`, `WRITE`, or `DELETE` on the document. This is the responsibility of `PermissionGrantingStrategy`.

In Spring Security ACL, `AclImpl` holds both strategies. When an ACL mutator is called, it guards the change via the authorization strategy; when `Acl.isGranted(...)` is queried, it delegates evaluating ACEs/SIDs/permissions to the permission granting strategy.

Key points to remember from the start:

- **The ACL owner is not by default a domain object reader.**
- **A `READ` ACE does not by default grant permission to edit the ACL.**
- `BasePermission.ADMINISTRATION` can contribute to allowing ACL administration, but it is **not** `READ | WRITE | DELETE`.
- A user allowed to modify an ACL can **indirectly grant themselves data permissions** if business rules allow arbitrary grants. That is why service-level administrative policies are also required.
- Permission order, SID order, bitmasks, denies, parent ACLs, and audit mode can all affect outcomes. Never shortcut the algorithm with `anyMatch`.

This lesson belongs to the **ACL Implementation** topic in Spring Security authorization. Afterward, you will be able to explain the contracts, configure both strategies, run a Java 17+ example using **Spring Security's actual ACL classes**, write tests, and apply fail-closed mechanics in production.

## 2. Core Components of Spring ACL

An ACL is bound to an `ObjectIdentity` (object type + ID) and holds `AccessControlEntry` (ACE) items. Each ACE links a `Sid` with a `Permission` and a granting/denying flag.

```text
ObjectIdentity = demo.Document#42
      |
      v
   AclImpl
     ownerSid = PrincipalSid("alice")
     entriesInheriting = false
     parentAcl = null
      |
      +-- ACE 0: bob   READ             GRANT
      +-- ACE 1: carol READ             DENY
      +-- ACE 2: dave  ADMINISTRATION   GRANT
      +-- ACE 3: erin  WRITE            GRANT
      |
      +-- AclAuthorizationStrategy
      |     When modifying owner/ACE/audit
      |
      +-- PermissionGrantingStrategy
            When checking READ/WRITE/... by SID
```

| Component | API | Responsibility |
| --- | --- | --- |
| Object identifier | `ObjectIdentity`, `ObjectIdentityImpl` | Identifies the ACL for an object |
| Security identity | `Sid`, `PrincipalSid`, `GrantedAuthoritySid` | Represents a user or authority |
| Permission | `Permission`, `BasePermission` | Represents permissions as bitmasks |
| Access entry | `AccessControlEntry` | Grant/deny ACE for a SID + permission |
| Access control list | `Acl`, `MutableAcl`, `AclImpl` | Owner, parent, entries, mutators, and permission checks |
| ACL administration | `AclAuthorizationStrategy` | Can the caller modify the ACL? |
| Object permission | `PermissionGrantingStrategy` | Is the SID granted a specific permission? |
| ACL repository | `AclService`, `MutableAclService` | Reads, creates, and updates ACLs |
| Method Security | `AclPermissionEvaluator` | Powers `hasPermission(...)` in expressions |
| JDBC loader | `BasicLookupStrategy` | Loads ACEs/owner/SIDs and builds the ACL |
| Cache | `AclCache`, `SpringCacheBasedAclCache` | Caches loaded ACLs |

**Domain owner** (`document.ownerUserId`) is a business attribute, distinct from `Acl.getOwner()`, which is ACL metadata. Changing one owner does not automatically update the other or add a READ ACE.

### Standard Permission Bits

| `BasePermission` constant | Mask |
| --- | ---: |
| `READ` | 1 |
| `WRITE` | 2 |
| `CREATE` | 4 |
| `DELETE` | 8 |
| `ADMINISTRATION` | 16 |

These are distinct bits. Do not infer that `WRITE` includes `READ` or that `ADMINISTRATION` automatically includes the previous four bits. If the business requires a permission hierarchy, it must be explicitly defined, configured, and tested.

## 3. `AclAuthorizationStrategy`: Deciding Who Can Modify an ACL

The real interface resides in package:

```java
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
```

The contract defines the method:

```java
void securityCheck(Acl acl, int changeType);
```

This is an abbreviated signature, not a runnable standalone Java file. It **does not return a boolean**: the call completes normally when permitted, or throws an exception when denied. This API is invoked by mutating operations on `AclImpl`.

### 3.1. Three Types of Changes

The interface declares three constants:

| Constant | Change group | Examples |
| --- | --- | --- |
| `CHANGE_GENERAL` | Modifying general ACL details or ACEs | `insertAce`, `deleteAce`, `updateAce`, parent ACL |
| `CHANGE_OWNERSHIP` | Changing the ACL's owner SID | `setOwner(...)` |
| `CHANGE_AUDITING` | Changing audit flags on an ACE | `updateAuditing(...)` |

These constants are **not** domain permissions. `CHANGE_GENERAL` is not synonymous with `BasePermission.WRITE`; `CHANGE_OWNERSHIP` is not `BasePermission.ADMINISTRATION`.

### 3.2. On What Grounds Does the Default Strategy Grant Access?

`AclAuthorizationStrategyImpl` is the standard implementation. According to the Spring Security 6.5 Javadoc, at least one of the following conditions allows an ACL change:

1. The caller **is the ACL owner** per `Acl.getOwner()`.
2. The caller holds the **system-wide `GrantedAuthority`** corresponding to the change type, injected into the constructor.
3. The caller has **`BasePermission.ADMINISTRATION`** according to the ACL and permission strategy.

Because this governs permission to **modify the permission list**, you cannot infer that the ACL owner is automatically allowed to read the domain object's contents.

Configuring a single authority for all change groups:

```java
@Bean
AclAuthorizationStrategy aclAuthorizationStrategy() {
    return new AclAuthorizationStrategyImpl(
        new SimpleGrantedAuthority("ROLE_ACL_ADMIN")
    );
}
```

This is a **Spring configuration fragment**. The ACL classes above live in `org.springframework.security.acls.domain`, while `SimpleGrantedAuthority` is in `org.springframework.security.core.authority`. The role in the example is application-defined, not a mandatory role created by Spring ACL.

### 3.3. Passing Three Separate Authorities

The `AclAuthorizationStrategyImpl(GrantedAuthority... auths)` constructor accepts either one shared authority or three distinct authorities. When passing three, the parameter order **must be preserved exactly**:

```java
new AclAuthorizationStrategyImpl(
    new SimpleGrantedAuthority("ROLE_ACL_OWNER_ADMIN"),
    new SimpleGrantedAuthority("ROLE_ACL_AUDIT_ADMIN"),
    new SimpleGrantedAuthority("ROLE_ACL_ENTRY_ADMIN")
);
```

| Position | Change type |
| --- | --- |
| Index 0 | `CHANGE_OWNERSHIP` |
| Index 1 | `CHANGE_AUDITING` |
| Index 2 | `CHANGE_GENERAL` |

This is an **alternative** to configuring one authority. If you use three authorities, do not assume splitting them eliminates the rights of the ACL owner or an `ADMINISTRATION` ACE: the default implementation still checks those other grounds. If policy requires that **only** compliance officers may change ownership and the ACL owner may not, enforce that at the service layer or with a custom strategy—not just by renaming roles.

### 3.4. Identity in the Authorization Strategy

The default strategy retrieves authentication via `SecurityContextHolderStrategy`/`SecurityContextHolder`. In an HTTP request, authentication must be established by a trusted filter/provider; in a background job, it can be a service identity set up through a dedicated flow. Never take a client-supplied username and construct an authenticated token to grant ACL changes.

`AclAuthorizationStrategyImpl` also supports options like `SidRetrievalStrategy`, `RoleHierarchy`, and a security-context strategy. When an organization has overlapping usernames across tenants or complex role hierarchies, verify SID mapping carefully; never treat self-reported emails/usernames as global identifiers.

## 4. `PermissionGrantingStrategy`: Deciding Permissions on Domain Objects

This interface lives in a **different package**:

```java
import org.springframework.security.acls.model.PermissionGrantingStrategy;
```

Core signature:

```java
boolean isGranted(
    Acl acl,
    List<Permission> permissions,
    List<Sid> sids,
    boolean administrativeMode
);
```

Distinctions to note:

- `permissions`: list of permissions to check, such as `READ`, `WRITE`.
- `sids`: principals/roles under evaluation.
- `administrativeMode`: an audit-mode flag, **not** the `ADMINISTRATION` permission.
- The return value can be `true` or `false`.
- When unable to reach a decision, `DefaultPermissionGrantingStrategy` may throw `NotFoundException`; when the ACL has not loaded a required SID, `UnloadedSidException` may be thrown.

Common implementation:

```java
@Bean
PermissionGrantingStrategy permissionGrantingStrategy() {
    return new DefaultPermissionGrantingStrategy(
        new ConsoleAuditLogger()
    );
}
```

`ConsoleAuditLogger` is only a basic audit logger; production may require auditing integrated with structured logging, retention, and security monitoring.

### 4.1. `AclImpl.isGranted(...)` Is the Primary Entry Point

```java
boolean allowed = acl.isGranted(
    List.of(BasePermission.READ),
    List.of(new PrincipalSid("bob")),
    false
);
```

The snippet above is a fragment assuming `acl` is already loaded. When `isGranted` is called, `AclImpl` delegates to its configured `PermissionGrantingStrategy`. **Do not** substitute `acl.getEntries().stream().anyMatch(...)`: permission/SID ordering, grant/deny ACEs, parent ACLs, masks, and missing SIDs make the semantics far richer.

### 4.2. Permission and SID Ordering Truly Matters

In `DefaultPermissionGrantingStrategy`, the algorithm iterates through each permission **in list order**, and each SID in list order. For each pair evaluated, it looks for a matching ACE according to the strategy rules. A grant can allow access; a deny may cause the strategy to try the next permission before ultimately denying.

This implies:

- A list `[READ, WRITE]` means **one matching permission can suffice**, not an AND of both.
- If business rules require READ **and** WRITE, check each permission independently and combine with AND.
- Changing the order of permissions, SIDs, or ACEs can change the decision in setups mixing grants and denies.
- If inconclusive on the current ACL: it may check the parent ACL **if** `entriesInheriting=true`.
- Still inconclusive: `NotFoundException`.

**Example:** `READ DENY`, `WRITE GRANT` does not automatically make `isGranted([READ, WRITE], ...)` return `false`; it depends on the order and evaluation mechanism. Therefore, never pass multiple permissions and assume it checks all of them simultaneously.

### 4.3. Mask-Matching Details of the Default Implementation

The Javadoc notes that mask comparison between an ACE and a requested permission is **not always simple equality**:

- When the ACE is **GRANT** and the requested mask is non-zero, bitwise intersection may be treated as a match.
- On the **DENY** branch, the default implementation compares masks for equality.
- A combined-mask ACE can behave differently from multiple single-bit ACEs.

This is the behavior of `DefaultPermissionGrantingStrategy`, not a guarantee for every custom `PermissionGrantingStrategy`. If you use combined permission masks, write unit tests covering grants, denies, multiple SIDs, and inherited ACLs.

### 4.4. `administrativeMode` Is Different from `BasePermission.ADMINISTRATION`

Compare two calls:

```java
acl.isGranted(
    List.of(BasePermission.READ),
    List.of(new PrincipalSid("bob")),
    false
);
```

```java
acl.isGranted(
    List.of(BasePermission.ADMINISTRATION),
    List.of(new PrincipalSid("dave")),
    true
);
```

The first call checks **READ**. The second checks **ADMINISTRATION** because it is placed in the permission list. The boolean `true` in the second example only puts evaluation in a mode that **skips auditing** during administrative checks; it does not grant extra permissions.

## 5. How Both Strategies Collaborate Across an ACL Lifecycle

```text
Caller
  |
  +-- Wants to edit ACL ----------------+
  |                                     |
  |                                  AclImpl mutator
  |                                  insertAce/setOwner/update...
  |                                     |
  |                                  AclAuthorizationStrategy
  |                                  securityCheck(acl, changeType)
  |                                     |
  |                                 allow / deny
  |
  +-- Wants to READ document -----------+
                                        |
                                     Method Security
                                     hasPermission(...)
                                        |
                                     AclPermissionEvaluator
                                        |
                                     AclService / Acl
                                        |
                                     AclImpl.isGranted(...)
                                        |
                                     PermissionGrantingStrategy
                                        |
                                     grant / deny / exception
```

| Question | Strategy | Data used |
| --- | --- | --- |
| Can Alice change the ACL owner? | `AclAuthorizationStrategy` | Current authentication, ACL owner, authorities, admin ACE |
| Can Bob `READ` Document#42? | `PermissionGrantingStrategy` | ACL entries, requested permission, and SID |
| Does a role have `READ` via the parent ACL? | `PermissionGrantingStrategy` | Parent ACEs, `entriesInheriting`, SID |
| Can an editor add an ACE for a teammate in the same tenant? | `AclAuthorizationStrategy` **and service policy** | ACL admin rights + tenant/recipient |
| Can the owner read content after `setOwner`? | `PermissionGrantingStrategy` | Actual READ ACE, never inferred from owner |

**A word of caution:** permission to edit an ACL can indirectly create read access (for example, adding a `READ` ACE for oneself). Therefore, having two independent strategies **does not mean** any ACL owner should be allowed to grant arbitrary permissions. Service policies must restrict grants/recipients and enforce auditing.

## 6. Java 17 Example Using Spring Security's Actual `AclImpl`

We create an ACL in memory using the real `AclImpl` to experiment with both strategies, **without mocking the algorithm with a `Map`**. The program needs no Spring Boot server or database; Gradle manages `spring-security-acl` and Spring Security core.

Scenario:

- ACL owner = `alice`, but no READ ACE for `alice`.
- `bob` has READ GRANT, with no permission to edit the ACL.
- `carol` has READ DENY.
- `dave` has ADMINISTRATION GRANT, with no READ.
- `root` has the system authority `ROLE_ACL_ADMIN`, also with no READ.

### 6.1. Project Structure

```text
acl-strategies-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/AclStrategiesDemo.java
    └── test/java/demo/AclStrategiesDemoTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'acl-strategies-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'application'
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

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.5.8'
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-acl'
    implementation 'org.springframework.security:spring-security-core'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'demo.AclStrategiesDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Gradle Boot BOM resolves compatible dependency versions. This is a Gradle **`application`**, without `@SpringBootApplication`, an HTTP server, or a database. This setup focuses on verifying the ACL strategies.

### 6.2. Program Source Code

**`src/main/java/demo/AclStrategiesDemo.java`:**

```java
package demo;

import java.util.Arrays;
import java.util.List;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.AclImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.Permission;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.acls.model.UnloadedSidException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public final class AclStrategiesDemo {

    private static final AclAuthorizationStrategyImpl CHANGE_STRATEGY =
        new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_ADMIN")
        );

    private static final DefaultPermissionGrantingStrategy GRANT_STRATEGY =
        new DefaultPermissionGrantingStrategy(new ConsoleAuditLogger());

    private AclStrategiesDemo() {
    }

    static void login(String name, String... authorities) {
        var grants = Arrays.stream(authorities)
            .map(SimpleGrantedAuthority::new)
            .toList();

        Authentication authentication =
            new UsernamePasswordAuthenticationToken(
                name, "demo-only", grants
            );

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
    }

    static AclImpl buildSample() {
        AclImpl acl = new AclImpl(
            new ObjectIdentityImpl("demo.Document", 42L),
            1L,
            CHANGE_STRATEGY,
            GRANT_STRATEGY,
            null,  // Parent ACL
            null,  // Do not restrict subset of loaded SIDs
            false, // Do not inherit ACEs
            new PrincipalSid("alice")
        );

        // Demo seeding only: root is granted system authority.
        login("root", "ROLE_ACL_ADMIN");

        acl.insertAce(
            0, BasePermission.READ, new PrincipalSid("bob"), true);
        acl.insertAce(
            1, BasePermission.READ, new PrincipalSid("carol"), false);
        acl.insertAce(
            2, BasePermission.ADMINISTRATION,
            new PrincipalSid("dave"), true);
        acl.insertAce(
            3, BasePermission.WRITE, new PrincipalSid("erin"), true);

        return acl;
    }

    static boolean readAllowed(Acl acl) {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        try {
            return acl.isGranted(
                List.<Permission>of(BasePermission.READ),
                List.<Sid>of(new PrincipalSid(authentication)),
                false
            );
        } catch (NotFoundException | UnloadedSidException denied) {
            return false;
        }
    }

    static boolean canChangeAcl(Acl acl) {
        try {
            CHANGE_STRATEGY.securityCheck(
                acl, AclAuthorizationStrategy.CHANGE_GENERAL);
            return true;
        } catch (AccessDeniedException | NotFoundException denied) {
            return false;
        }
    }

    public static void main(String[] args) {
        try {
            AclImpl acl = buildSample();

            login("alice");
            System.out.println("ALICE_IS_OWNER: "
                + new PrincipalSid("alice").equals(acl.getOwner()));
            System.out.println("ALICE_READ: " + readAllowed(acl));
            System.out.println("ALICE_CHANGE_ACL: " + canChangeAcl(acl));

            login("bob");
            System.out.println("BOB_READ: " + readAllowed(acl));
            System.out.println("BOB_CHANGE_ACL: " + canChangeAcl(acl));

            login("carol");
            System.out.println("CAROL_READ_DENY: " + readAllowed(acl));

            login("dave");
            System.out.println("DAVE_READ: " + readAllowed(acl));
            System.out.println("DAVE_CHANGE_ACL: " + canChangeAcl(acl));

            login("root", "ROLE_ACL_ADMIN");
            System.out.println("ROOT_READ: " + readAllowed(acl));
            System.out.println("ROOT_CHANGE_ACL: " + canChangeAcl(acl));
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
```

### 6.3. Running and Comparing Output

Inside the directory containing `build.gradle`, run with the Gradle Wrapper:

```bash
./gradlew run
```

On Windows PowerShell:

```bash
.\gradlew.bat run
```

If there is no Gradle Wrapper yet, generate it with a compatible Gradle version, or use `gradle run` if installed. **The lines printed by the program's `System.out.println`** (excluding Gradle/logger output) are expected to be:

```text
ALICE_IS_OWNER: true
ALICE_READ: false
ALICE_CHANGE_ACL: true
BOB_READ: true
BOB_CHANGE_ACL: false
CAROL_READ_DENY: false
DAVE_READ: false
DAVE_CHANGE_ACL: true
ROOT_READ: false
ROOT_CHANGE_ACL: true
```

Interpretation:

1. The ACL owner is indeed `alice`.
2. `alice` can administer the ACL as owner, yet has no READ ACE so cannot automatically read.
3. `bob` has a READ GRANT ACE, yet has no permission to edit the ACL.
4. `carol` hits the READ DENY ACE.
5. `dave` has an ADMINISTRATION GRANT ACE, so he can administer the ACL; he has no READ.
6. `root` holds the system authority to edit ACLs, yet has no READ ACE.

**Note:** outcomes can depend on role hierarchy, SID retrieval, or custom strategies if you alter the example. With the default setup shown in the source, these boolean lines are the verification targets. Constructing an already-authenticated `UsernamePasswordAuthenticationToken` in the program is **purely a demo technique** and must never be used as a production login mechanism.

### 6.4. JUnit Tests for Both Strategies

**`src/test/java/demo/AclStrategiesDemoTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.acls.domain.AclImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.core.context.SecurityContextHolder;

class AclStrategiesDemoTest {

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void aclOwnerDoesNotAutomaticallyReadContent() {
        AclImpl acl = AclStrategiesDemo.buildSample();

        assertEquals(new PrincipalSid("alice"), acl.getOwner());
        AclStrategiesDemo.login("alice");
        assertFalse(AclStrategiesDemo.readAllowed(acl));
        assertTrue(AclStrategiesDemo.canChangeAcl(acl));
    }

    @Test
    void readAceDoesNotAllowAclMutation() {
        AclImpl acl = AclStrategiesDemo.buildSample();

        AclStrategiesDemo.login("bob");
        assertTrue(AclStrategiesDemo.readAllowed(acl));
        assertFalse(AclStrategiesDemo.canChangeAcl(acl));
    }

    @Test
    void administrationAceIsNotReadPermission() {
        AclImpl acl = AclStrategiesDemo.buildSample();

        AclStrategiesDemo.login("dave");
        assertFalse(AclStrategiesDemo.readAllowed(acl));
        assertTrue(AclStrategiesDemo.canChangeAcl(acl));
    }

    @Test
    void explicitDenyPreventsRead() {
        AclImpl acl = AclStrategiesDemo.buildSample();

        AclStrategiesDemo.login("carol");
        assertFalse(AclStrategiesDemo.readAllowed(acl));
    }

    @Test
    void systemRoleCanManageButDoesNotImplicitlyRead() {
        AclImpl acl = AclStrategiesDemo.buildSample();

        AclStrategiesDemo.login("root", "ROLE_ACL_ADMIN");
        assertFalse(AclStrategiesDemo.readAllowed(acl));
        assertTrue(AclStrategiesDemo.canChangeAcl(acl));
    }
}
```

Run:

```bash
./gradlew test
```

These tests invoke the real ACL implementation (`AclImpl`) directly to verify both strategies; Spring AOP is not needed here. If you move to `@PreAuthorize` on a Spring service, write separate tests with `@SpringBootTest` and `@WithMockUser` going through a **Spring-managed proxy** to confirm the Method Security interceptor takes effect.

## 7. Integrating Both Strategies into Spring ACL JDBC Configuration

The example above creates ACLs only in RAM. In a Spring Boot application persisting ACLs to a database, both strategies are typically wired into `BasicLookupStrategy` and `SpringCacheBasedAclCache` so loaded ACLs behave consistently.

Diagram:

```text
HTTP / service method / scheduler
          |
          +-- read object ---------------------+
          |                                    |
          |                             AclPermissionEvaluator
          |                                    |
          |                                 AclService
          |                                    |
          |                                    v
          |                             BasicLookupStrategy
          |                                    |
          |                           AclImpl + ACE/owner/parent
          |                                    |
          |                             PermissionGrantingStrategy
          |
          +-- update ACL ----------------------+
                                               |
                                        MutableAclService
                                               |
                                          AclImpl mutator
                                               |
                                        AclAuthorizationStrategy
                                               |
                                           updateAcl
```

### 7.1. Illustrative Configuration

The **`AclConfiguration.java`** file below is a Spring Boot configuration, **not a complete application** without a datasource, SQL schema, Spring ACL dependencies, and proper identity/policy setup:

```java
package demo;

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
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.LookupStrategy;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration
@EnableMethodSecurity
public class AclConfiguration {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator evaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService service) {
        return new AclPermissionEvaluator(service);
    }

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_ADMIN")
        );
    }

    @Bean
    PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
            new ConsoleAuditLogger()
        );
    }

    @Bean
    AclCache aclCache(
            PermissionGrantingStrategy grants,
            AclAuthorizationStrategy aclChanges) {
        return new SpringCacheBasedAclCache(
            new ConcurrentMapCache("aclCache"), grants, aclChanges);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache aclCache,
            AclAuthorizationStrategy aclChanges,
            PermissionGrantingStrategy grants) {
        return new BasicLookupStrategy(
            dataSource, aclCache, aclChanges, grants);
    }

    @Bean
    JdbcMutableAclService aclService(
            DataSource dataSource,
            LookupStrategy lookupStrategy,
            AclCache aclCache) {
        return new JdbcMutableAclService(
            dataSource, lookupStrategy, aclCache);
    }
}
```

**Why use `static @Bean` for the handler?** Method Security needs the expression handler early when initializing security configuration. `setPermissionEvaluator` wires `hasPermission(...)` expressions to `AclPermissionEvaluator`. Without this wiring, `@PreAuthorize("hasPermission(...)")` will not automatically know how to use your stored ACLs.

### 7.2. Dependencies and Schema

In a Spring Boot Gradle project that already has the Boot plugin/BOM, typical dependencies are:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.security:spring-security-acl'
    implementation 'org.springframework:spring-context-support'
    runtimeOnly 'com.h2database:h2'
}
```

This is a **Gradle snippet**; running it requires plugin versions, `repositories`, drivers, and project configuration. In production, use the driver/schema/SQL matching your real database rather than H2.

The core ACL tables:

| Table | Purpose |
| --- | --- |
| `acl_sid` | Stores principal SIDs and granted-authority SIDs |
| `acl_class` | Domain object types |
| `acl_object_identity` | Object ID, owner SID, parent ACL, inheritance |
| `acl_entry` | ACE order, SID, permission mask, granting, and audit flags |

`JdbcMutableAclService` handles ACL updates; `BasicLookupStrategy` handles ACL reads, optionally paired with `AclCache`. You must initialize the exact schema/sequences/identity queries expected by the library/dialect; merely creating tables with the same names does not guarantee all queries work.

### 7.3. Method Security Pattern

Once `AclPermissionEvaluator` and the expression handler are wired:

```java
@PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
public Document readDocument(Long id) {
    return documentRepository.findById(id).orElseThrow();
}
```

This is a **service snippet**; `Document`, the repository, and annotation imports must exist in your project. `demo.Document` must match the type used in the ACL `ObjectIdentity`, typically the class name or a configured mapping. `@PreAuthorize` must be enabled via `@EnableMethodSecurity`, and callers must invoke through the bean/proxy.

A user granted `ROLE_ACL_ADMIN` under the ACL-modification strategy **does not automatically get READ** in the expression above unless the ACL has a matching grant or read policy.

## 8. ACL Administration Services Need More Checks Than Just the Strategy

Never expose a `grantRead(documentId, recipientId)` API just because the mutator triggers `AclAuthorizationStrategy`. You must protect **feature-level access**, **resource scope**, **recipient eligibility**, and **granted permissions**.

A service structure:

```java
// Illustrative snippet inside a bean/service with dependencies already injected.

@PreAuthorize("hasAuthority('acl:manage')")
public void grantRead(Long documentId, String recipientId) {

    // 1. Real record from server; never trust client-declared owner/tenant.
    Document document = documentRepository.require(documentId);

    // 2. Caller must be allowed to manage the document in this tenant.
    tenantPolicy.requireCanManage(
        SecurityContextHolder.getContext().getAuthentication(),
        document
    );

    // 3. Only grant to a recipient eligible under policy.
    recipientPolicy.requireEligible(recipientId, document);

    ObjectIdentity identity =
        new ObjectIdentityImpl("demo.Document", documentId);

    MutableAcl acl = (MutableAcl)
        mutableAclService.readAclById(identity);

    int position = acl.getEntries() == null
        ? 0
        : acl.getEntries().size();

    // This mutator checks AclAuthorizationStrategy.
    acl.insertAce(
        position, BasePermission.READ,
        new PrincipalSid(recipientId), true
    );

    mutableAclService.updateAcl(acl);
}
```

This **is not a standalone code snippet**: it requires real `Document`, repository, `tenantPolicy`, `recipientPolicy`, `mutableAclService`, imports, and transaction boundaries. It illustrates responsibility boundaries:

- `@PreAuthorize` guards access **to the operation**.
- `tenantPolicy` guards **the exact resource and tenant**.
- `recipientPolicy` guards **who may receive the permission**.
- `AclAuthorizationStrategy` guards **the ACL mutation itself**.
- `MutableAclService.updateAcl` persists changes and interacts with the cache.

AOP method security still has the self-invocation limitation: if a protected method is called via `this.grantRead(...)` inside the same bean, the interceptor can be bypassed. Design services with clean boundaries and test through Spring proxies.

### ACL Admins Can Still Escalate Indirectly

Even though `BasePermission.ADMINISTRATION` does not equal READ, someone allowed to add ACEs can add one for themselves:

```text
PrincipalSid("admin") + READ GRANT
```

If the feature permits that operation, the user will have read access on subsequent checks. This is an **indirect capability**, not automatic behavior of `PermissionGrantingStrategy`. Apps handling sensitive data may need maker–checker workflows, prohibitions on self-granting, recipient allowlists, grant restrictions, and thorough auditing.

## 9. Edge Cases That Affect Permission Granting Outcomes

### 9.1. Parent ACLs and Inheritance

A folder grants READ to `ROLE_TEAM`, and a document has that folder as its parent ACL. If the document has `entriesInheriting=true` and no matching local decision, the permission strategy can evaluate the parent ACL's ACEs. If `entriesInheriting=false`, merely linking a parent does not cause ACEs to flow down.

The parent's ACL owner **does not automatically become** the child's ACL owner; permission to modify a child ACL must be checked against the child's administration policy.

### 9.2. Partially Loaded SIDs

`AclService.readAclById(identity, sids)` can return an ACL loaded only for the requested SIDs. Evaluating another SID via `Acl.isGranted(...)` may throw `UnloadedSidException`. This is not a harmless `false` to ignore; load the needed data properly and fail closed.

When building an ACE administration UI or updating an ACL, read the full relevant entries/SIDs so you do not overwrite or miss unloaded ACEs.

### 9.3. Deny, Masks, and Ordering

Do not treat every ACE with `granting=true` as a universal grant. The default strategy evaluates permissions/SIDs/ACEs by specific rules, with mask comparison differences between grant and deny branches. Test all cases:

- Only READ GRANT.
- Only READ DENY.
- Both grant and deny for the same user or across multiple SIDs.
- Permissions using combined masks.
- Parent ACL grant while local ACL is inconclusive.
- Parent ACL present with `entriesInheriting=false`.

### 9.4. Anonymous, Roles, and Tenants

`AnonymousAuthenticationToken` can report `isAuthenticated()=true`; if writing a custom strategy or guard, never rely on that check alone to allow access. `PrincipalSid("bob")` can also collide across tenants if the system uses non-unique usernames. Choose stable user IDs and a trusted tenant namespace consistent with how ACEs are stored.

Never accept actor/tenant/role values from the request body as a security identity. In practice, identity must come from an `Authentication` verified by your provider and server-side mapping.

## 10. Transactions, Caching, Auditing, and Consistency

### 10.1. Updating the ACL and the Domain Object Are Two Separate Operations

`acl.insertAce(...)` updates the ACL object in memory; only `mutableAclService.updateAcl(acl)` writes the change through the persistence layer. Changing the domain owner does not automatically update the ACL owner or ACEs.

When transferring ownership, define clearly:

1. Who is allowed to change the domain owner?
2. Should the ACL owner also change?
3. What new grants should the new owner receive?
4. Should the old owner's ACEs be revoked or kept as a share?
5. Must parent ACLs, tenants, or group memberships be updated?
6. How are transactions, rollbacks, auditing, and cache invalidation handled?

### 10.2. ACL Caching and Permission Revocation

`SpringCacheBasedAclCache` can retain loaded ACLs. After changing the owner, ACEs, or inheritance, the corresponding cache entry must be invalidated/updated. In a multi-node system, a local cache on node A does not automatically evict node B's cache.

Never cache a simple boolean `allowed=true` keyed only by `documentId`: decisions depend on principal/SIDs, tenant, permission, and ACL version. When permissions are revoked, a stale cache lets users continue unauthorized access.

### 10.3. TOCTOU and Transactions

When `@PreAuthorize` checks at time T1 and the database updates at T2, the ACL or owner may change in between. That is a **time of check, time of use** risk. For sensitive writes, consider locking, versioning, conditional UPDATEs, and consistent transactions so permissions are validated close to the write.

Do not assume `@Transactional` alone guarantees authorization cannot change between two points; isolation level and DB design govern that behavior.

### 10.4. N+1 ACL Lookups

`@PostFilter("hasPermission(filterObject, 'READ')")` on large lists may load ACLs one object at a time. Use `AclService.readAclsById(...)`, batch retrieval, or permission-filtered queries at the data layer when appropriate. Never skip denies, tenants, parents, or SID ordering in the name of optimization.

### 10.5. Auditing Must Distinguish Two Event Types

- **ACL administration audit:** who added/removed an ACE, changed the owner, changed audit flags, changed the parent, who was granted, and before/after states.
- **Permission decision audit:** who requested READ/WRITE, on which object, and whether the result was allow or deny.

`PermissionGrantingStrategy`'s `administrativeMode` relates to auditing permission checks; it does not replace dedicated logging for ACL-modification operations. Never log credentials or full sensitive payloads.

## 11. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `AclAuthorizationStrategy` to check READ | ACL owner gets unintended read access | Use `Acl.isGranted`/`AclPermissionEvaluator` |
| Using `PermissionGrantingStrategy` instead of ACL-edit policy | READ ACE could be confused with admin | Mutators go through `securityCheck(changeType)` |
| Treating ADMINISTRATION as data superuser | Grants READ/DELETE unexpectedly | Define permissions per action |
| Thinking `administrativeMode=true` grants admin permission | Wrong decisions/auditing | Put required permission in the permission list |
| Using `[READ, WRITE]` as an AND check | Allows access when only one is granted | Check separately and combine with AND |
| Ignoring `NotFoundException`/`UnloadedSidException` | Decisions made from missing data | Fail closed, load required SIDs |
| Forgetting parent ACLs | Allow/deny outcomes mismatch policy | Test inheritance |
| Scanning ACEs manually with `anyMatch` | Loses deny/mask/ordering semantics | Use the proper strategy |
| Granting `ROLE_ACL_ADMIN` too broadly | Allows managing across tenants | Scope system authorities and service policies |
| Admin granting themselves READ | Indirect privilege escalation | Restrict grants/recipients, maker–checker |
| Not wiring the same strategies to lookup and cache | ACLs loaded via different paths behave inconsistently | Wire beans consistently |
| Wrong `ObjectIdentity` | Missing ACLs or cross-object permission leaks | Standardize type + ID |
| Colliding SID usernames across tenants | Principals get mixed up | Stable scoped SIDs |
| Modifying ACLs directly via SQL | Bypasses mutator guards | Protect DB and APIs, add auditing |
| Skipping cache invalidation after revoke | Stale ACEs still allow access | Invalidate ACL cache / distributed cache |
| Self-invocation with Method Security | Bypasses `@PreAuthorize` | Split beans, test through proxy |
| Testing only admin-allow cases | Misses over-broad grants | Test owner, reader, deny, missing, anonymous |

## 12. Self-Assessment Exercises

1. **What question does `AclAuthorizationStrategy` answer?**  
   Who is allowed to modify the ACL itself—including owner, ACEs, and auditing—by change type.

2. **What question does `PermissionGrantingStrategy` answer?**  
   Whether the current ACL grants or denies the requested permission for a set of SIDs on a domain object.

3. **A user is the ACL owner but has no READ ACE: can they automatically READ?**  
   No. ACL administration rights and data read permissions are separate.

4. **Can a user with a READ ACE call `insertAce(...)`?**  
   Not by default; `AclAuthorizationStrategy` must permit the operation.

5. **Is `BasePermission.ADMINISTRATION` synonymous with `READ`?**  
   No. It is an independent mask that can authorize ACL administration under the default implementation.

6. **How do the one-authority and three-authority constructors differ?**  
   One authority grants system-wide rights for all three change groups; three authorities assign ownership, auditing, and general changes respectively.

7. **Does `administrativeMode=true` grant the ADMINISTRATION permission?**  
   No. That boolean primarily affects auditing; requested permissions belong in the permissions list.

8. **Is `isGranted([READ, WRITE], sids, false)` an OR or an AND?**  
   It must not be treated as AND; the strategy can allow access when a single permission is granted.

9. **If no matching ACE is found, does it always return `false`?**  
   No. `DefaultPermissionGrantingStrategy` may inspect the parent ACL or throw `NotFoundException`.

10. **Does changing the ACL owner automatically transfer the business owner?**  
    No. Domain owner and ACL owner come from two separate data sources.

11. **Why can a system ACL admin pose a risk even without READ?**  
    Because they could add a READ ACE for themselves if grant policies do not restrict them.

12. **What tests prove the two strategies are not conflated?**  
    Test that the ACL owner can edit the ACL but cannot READ; a reader can READ but cannot edit the ACL; an admin ACE can administer without READ; and a system admin role cannot implicitly READ.

## 13. Official Documentation

- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): ACL/JDBC components, wiring `BasicLookupStrategy`, caching, and Method Security.
- [Spring Security 6.5 — `AclAuthorizationStrategy`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclAuthorizationStrategy.html): `securityCheck` contract, `CHANGE_GENERAL`, `CHANGE_OWNERSHIP`, `CHANGE_AUDITING`.
- [Spring Security 6.5 — `AclAuthorizationStrategyImpl`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclAuthorizationStrategyImpl.html): ACL owner, system authority, ACE administration, and constructor authority order.
- [Spring Security 6.5 — `PermissionGrantingStrategy`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/PermissionGrantingStrategy.html): `isGranted` API.
- [Spring Security — `DefaultPermissionGrantingStrategy`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html): permission/SID order, bitmask matching, deny, and parent handling.
- [Spring Security 6.5 — `AclImpl`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclImpl.html): constructors, mutator methods, `isGranted`, SIDs, and owner.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `hasPermission`, and expression handler.

**Conclusion:** `AclAuthorizationStrategy` controls **who can modify an ACL**, whereas `PermissionGrantingStrategy` decides **who can access a resource based on ACEs/SIDs/permissions**. Both are used by `AclImpl`, yet the result of one never substitutes for the other. In real applications, add tenant policies, service guards, recipient validation, tests for deny/owner/admin cases, and proper transaction/cache/audit management.
# Creating an ACL When Creating a New Business Object

> **Scope:** Spring Security – authorization, **ACL Implementation** group. This lesson explains how to **initialize an Access Control List (ACL) immediately when creating a new business object** such as a Document, Project, or Invoice; from when the DB assigns an ID, creating `ObjectIdentity`, `MutableAclService.createAcl(...)`, adding ACEs, and calling `updateAcl(...)` to ensuring transactions, least privilege, and error handling. Spring examples target Spring Boot 3.x + Spring Security 6.x; the principles apply to other versions when checking the corresponding Javadoc/runtime. Standalone Java 17 examples are clearly distinguished from the real framework.

## 1. Objectives and Business Requirements

An API receives a request to create a document:

~~~http
POST /api/documents
Authorization: Bearer <token>
Content-Type: application/json

{"title":"November Plan"}
~~~

Suppose Alice is logged in, belongs to tenant alpha, and holds the `document:create` authority. The application must perform **two tightly coupled actions**:

1. Save a Document row with a real ID, a trusted creator/owner, and the appropriate tenant.
2. Create an ACL for that exact Document; grant Alice `READ` and `WRITE` permissions, without automatically granting `DELETE`, `ADMINISTRATION`, or access for all users.

The operation should not be considered complete just because the repository returned an ID. If the Document exists without an ACL, two bad outcomes can happen: the document becomes unintentionally locked out, or another endpoint falls back to unsafe logic and leaks data.

After this lesson, you will be able to:

- Explain **why an ACL does not appear automatically** after `repository.save(...)`.
- Pick the right point once an ID exists to create the `ObjectIdentity` and ACL.
- Use `MutableAclService.createAcl`, `MutableAcl.insertAce`, and `MutableAclService.updateAcl` properly, distinguishing the ACL owner from read/write ACEs.
- Place the domain save and ACL provisioning inside **one real transaction** when sharing the same DB/transaction manager; recognize when `@Transactional` is not enough.
- Design for fail closed, least privilege, idempotency/retry, tenant isolation, and intentional parent inheritance.
- Write tests for the happy path, ACL creation failures, duplicate ACLs, rollbacks, wrong owner/tenant, and reading permissions back after commit.

## 2. What Does Spring Security ACL Protect?

Spring Security ACL is a **per-object authorization** mechanism complementing URL/method authorities. A user may have `document:read` authority yet only be allowed to READ specific Documents. The components are:

| Component | Meaning when creating a new Document |
| --- | --- |
| `ObjectIdentity` | Pair of type + ID, e.g., `Document.class` and `101L` |
| `Acl` / `MutableAcl` | Policy for that exact object; mutable ACL is used to add/edit ACEs and parent |
| `Sid` | Identity affected by an ACE: `PrincipalSid` or `GrantedAuthoritySid` |
| `Permission` | Permission mask such as `BasePermission.READ`, `WRITE`, `DELETE` |
| `AccessControlEntry` (ACE) | A single rule for SID + permission + grant/deny |
| `MutableAclService` | Service to create/update/delete persistent ACLs |
| `AclService` | Service to read ACLs for permission decisions |
| `AclPermissionEvaluator` | Bridges `hasPermission(...)` expressions with ACL data |
| `AclAuthorizationStrategy` | Governs who can **modify the ACL**, not who can read the document |
| `parentAcl` / `entriesInheriting` | Parent ACL relationship and whether inherited permissions are consulted |

### 2.1. The Four Standard Spring JDBC ACL Tables

~~~text
acl_class            object type: com.example.domain.Document
acl_sid              SID: principal alice / authority ROLE_REVIEWER
acl_object_identity  ACL ID for Document 101, owner, parent, inheritance
acl_entry            ACE: READ/WRITE/DELETE... for SID on that ACL
~~~

In the standard JDBC schema, `acl_object_identity` stores the object identity, `owner_sid`, `parent_object`, and `entries_inheriting`. `acl_entry` stores `acl_object_identity`, `ace_order`, `sid`, `mask`, and `granting`.

**There is no default trigger in Spring Security that automatically creates an ACL when a JPA repository saves an entity.** The application service/workflow itself must perform provisioning or call a dedicated component. The Spring Security documentation states explicitly that ACLs are not automatically wired into every DAO/repository operation.

### 2.2. ACL Owner Is Not Default READ Permission

`Acl.getOwner()` denotes the SID that owns the ACL for ACL administration/modification purposes under the configured strategy. The fact that Alice is the ACL owner **is not synonymous** with having a `READ` or `WRITE` ACE so `hasPermission` evaluates to true.

Therefore, the creation flow must specify separately:
- **Who can create?** Method/web authorization `document:create`.
- **Who is the Document owner?** Verified principal/tenant in domain data.
- **Who is the ACL owner?** SID used for ACL administration, derived by default in JDBC from the security context at ACL creation time.
- **What are the initial ACEs?** For example, `READ` and `WRITE` for Alice, without granting extra permissions just because Alice is the creator.

Managing the ACL owner and business owner are related decisions that do not synchronize automatically. If an actor creates on someone else's behalf, establish an explicit policy for changing ownership so creators do not become able to edit arbitrary ACLs.

## 3. The Right Creation Order: ID → ACL → ACE → Commit

A clear flow:

~~~text
Client Alice: CreateDocument(title)
             |
             v
Spring Security checks document:create
             |
             v
@Service @Transactional
  1. Validate title and determine creator + tenant from trusted identity
  2. Create Document and save to obtain ID 101
  3. ObjectIdentity(Document.class, 101L)
  4. aclService.createAcl(objectIdentity)  -> new ACL, no ACEs yet
  5. Configure inheritance/parent (if intentional)
  6. insertAce(READ, PrincipalSid("alice"), grant=true)
  7. insertAce(WRITE, PrincipalSid("alice"), grant=true)
  8. aclService.updateAcl(acl)           -> save ACEs and metadata
             |
             +-- if any step fails: roll back BOTH domain + ACL
             |
             v
Transaction COMMIT
             |
             v
Return 201 Created + id=101
~~~

**Ordering dependency on an existing ID:** for DB-generated IDs, never create `ObjectIdentityImpl(Document.class, null)` before saving. If the ID comes from JPA `IDENTITY`, the ORM typically must execute the insert to assign the ID; with `SEQUENCE`, the ID may be available before the row is flushed. A safe pattern in the example is `saveAndFlush` followed by checking the ID is non-null; note that **flush is not commit**.

### 3.1. Two Phases of ACL Provisioning

Using the `MutableAclService` API according to its contract:

~~~java
ObjectIdentity oi =
        new ObjectIdentityImpl(Document.class, savedDocument.getId());

// Phase 1: create an empty ACL row for ObjectIdentity.
MutableAcl acl = aclService.createAcl(oi);

// Phase 2: add entries and update the persistent ACL.
Sid creatorSid = new PrincipalSid(creatorId);
acl.insertAce(acl.getEntries().size(),
              BasePermission.READ, creatorSid, true);
acl.insertAce(acl.getEntries().size(),
              BasePermission.WRITE, creatorSid, true);
aclService.updateAcl(acl);
~~~

This is a **snippet** requiring `savedDocument`, `creatorId`, and `aclService` inside a service; it is not a standalone Java file.

Points to remember:

1. `createAcl(oi)` creates an **ACL without ACEs**, saves the object identity, and returns a `MutableAcl` carrying the ACL's ID.
2. `insertAce(index, permission, sid, granting)` only modifies the mutable object's ACE list; you must call `updateAcl(acl)` to persist changes.
3. `acl.getEntries().size()` is the index to append **at the end of the direct ACE list**. ACE ordering matters to the permission-granting strategy; do not blindly append duplicates on retries.
4. `true` means GRANT. `false` means DENY, which is not the same as "creating no ACE."
5. `createAcl` may throw `AlreadyExistsException` when the ObjectIdentity already has an ACL. Do not catch it and broaden permissions on an existing ACL, as it may indicate a race or different policy.
6. `updateAcl` is not a create operation: it updates an existing ACL and can throw `NotFoundException` if the record has not been created yet.

### 3.2. Do Not Use new AclImpl Instead of createAcl

~~~java
// DO NOT use to create a new ACL row:
AclImpl localObject = new AclImpl(/* ... */);
aclService.updateAcl(localObject); // Does not automatically insert acl_object_identity.
~~~

The snippet above is a conceptual anti-pattern, omitting constructor arguments. With JDBC ACL, you must use `MutableAclService.createAcl(oi)` to allocate the ACL ID and store the object identity; only afterward call `updateAcl`. Instantiating `AclImpl` directly is useful for certain unit tests, but **does not replace** the persistence contract.

## 4. Designing Initial Permissions Under Least Privilege

Consider a newly created personal document:

| SID | Permission | Grant | Should it be granted on creation? |
| --- | --- | --- | --- |
| `PrincipalSid("alice")` | READ | true | Yes, per sample requirement |
| `PrincipalSid("alice")` | WRITE | true | Yes, if the creator may edit |
| `PrincipalSid("alice")` | DELETE | No ACE | Not automatically |
| `PrincipalSid("alice")` | ADMINISTRATION | No ACE | Not automatically |
| `GrantedAuthoritySid("ROLE_USER")` | READ | No ACE | Do not grant to all users |
| `GrantedAuthoritySid("ROLE_REVIEWER")` | READ | Business-dependent | Only when policy explicitly confirms |
| `PrincipalSid("bob")` | READ | No ACE | Cannot read unless shared |

**Having no matching ACE is not a GRANT ACE.** Under the standard strategy, `Acl.isGranted(...)` may throw `NotFoundException` when no decision is found; `AclPermissionEvaluator` and the security layer must treat missing evidence as denied.

### 4.1. Choosing the Right SID

- `PrincipalSid(String username)` uses a principal identifier. In real applications, pick a stable ID rather than a mutable username; stay consistent across login, ACL provisioning, and SID retrieval.
- `GrantedAuthoritySid("ROLE_REVIEWER")` targets a shared authority. Remember that granting READ to `ROLE_USER` allows **every user with that role** to read the newly created document.
- If tenant must be part of the SID, define a clear model (globally unique principal IDs or trusted namespaced composite IDs); avoid collisions between "alice" in tenant A and "alice" in tenant B.

Pick one consistent convention for `ObjectIdentity` type and SID. For example, `new ObjectIdentityImpl(Document.class, id)` uses the class name recognized by ACL persistence; if an expression check uses a different type name, lookup may fail or hit the wrong ACL.

### 4.2. BasePermission Does Not Infer Hierarchy Across Roles

`BasePermission.READ`, `WRITE`, `CREATE`, `DELETE`, and `ADMINISTRATION` are distinct masks. Do not assume granting WRITE includes READ, or granting READ suffices to update. If an API requires both READ and WRITE, add the corresponding ACEs per policy.

If a document has a `DRAFT` status and the creator may only edit before publishing, **do not expect ACL WRITE to automatically enforce "DRAFT only"**. You must add a business-state policy in the service/domain layer.

## 5. Spring Boot Service: Creating Document and ACL in One Transaction

The example below shows the **core service**. It requires a Spring Boot 3.x/Spring Security 6.x project already configured with JPA, Spring ACL JDBC, a transaction manager, schema, authentication, and the dependencies below. `Document`, `DocumentRepository`, and `TenantDirectory` are domain components supplied by the application; thus this is an **integration snippet ready to drop into a project**, not a complete standalone app in one file.

Create `src/main/java/example/documents/CreateDocumentService.java`:

~~~java
package example.documents;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CreateDocumentService {
    private final DocumentRepository repository;
    private final MutableAclService aclService;
    private final TenantDirectory tenantDirectory;

    public CreateDocumentService(DocumentRepository repository,
                                 MutableAclService aclService,
                                 TenantDirectory tenantDirectory) {
        this.repository = repository;
        this.aclService = aclService;
        this.tenantDirectory = tenantDirectory;
    }

    @Transactional
    @PreAuthorize("hasAuthority('document:create')")
    public Long create(NewDocument command) {
        Authentication actor =
                SecurityContextHolder.getContext().getAuthentication();
        if (actor == null || !actor.isAuthenticated()
                || actor instanceof AnonymousAuthenticationToken) {
            throw new AccessDeniedException("Authentication required");
        }

        // This is the authenticated ID, NOT a client-declared creatorId.
        String creatorId = actor.getName();

        // Tenant comes from a trusted server-side source, NOT from a request header.
        String tenantId = tenantDirectory.requireTenantFor(actor);

        Document entity = new Document(
                command.title(), tenantId, creatorId);
        Document saved = repository.saveAndFlush(entity);
        Long id = saved.getId();
        if (id == null) {
            throw new IllegalStateException("Document ID was not generated");
        }

        ObjectIdentity oid = new ObjectIdentityImpl(Document.class, id);
        MutableAcl acl = aclService.createAcl(oid);

        // Do not automatically inherit ACEs from another folder/tenant.
        acl.setEntriesInheriting(false);

        // JDBC createAcl sets owner from the security context.
        // ACL owner does not automatically generate READ/WRITE ACEs.
        Sid creator = new PrincipalSid(creatorId);
        acl.insertAce(acl.getEntries().size(),
                BasePermission.READ, creator, true);
        acl.insertAce(acl.getEntries().size(),
                BasePermission.WRITE, creator, true);

        aclService.updateAcl(acl);
        return id;
    }
}
~~~

Example `NewDocument` as a command/value object holding validated input:

~~~java
package example.documents;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record NewDocument(
        @NotBlank @Size(max = 180) String title) {
}
~~~

**Domain dependencies to define yourself:** `Document` is a JPA `@Entity` with a constructor taking `title, tenantId, creatorId` and a getter `Long getId()`; `DocumentRepository` is a `JpaRepository<Document, Long>`; `TenantDirectory.requireTenantFor(Authentication)` resolves the tenant from a trusted server identity source and throws if unverified. Never read tenant/creator from the request and assume it is trustworthy.

### 5.1. Why saveAndFlush Before createAcl?

- For DB-generated IDs, `ObjectIdentity` requires the **already-assigned** ID.
- `saveAndFlush` ensures JPA sends pending changes to the DB, while the **transaction remains open** and uncommitted.
- JDBC ACL may need to read/write in the same DB. With a shared DataSource and transaction configuration, both the domain write and ACL write participate in the same transaction for joint rollback.

Do not write:

~~~java
// Wrong order when ID does not exist yet:
Document draft = new Document(title, tenant, creator);
ObjectIdentity oi = new ObjectIdentityImpl(Document.class, draft.getId());
// draft.getId() may be null at this point.
MutableAcl acl = aclService.createAcl(oi);
~~~

Also never call `entityManager.persist(...)` in a non-transactional method and rely on JDBC ACL in another method as if the two were atomic.

### 5.2. Be Careful with ACL Owner and Identity

`JdbcMutableAclService.createAcl(...)` sets the owner SID from the caller's security context in the standard implementation. In the example, the calling principal is the creator. If a system job creates on behalf of someone else:
- Never assume the ACL owner is automatically the business owner.
- You may need a `Sid` representing the service identity and separate ACEs for the beneficiaries.
- To change the ACL owner via `MutableAcl.setOwner(...)`, the acting identity must be permitted by `AclAuthorizationStrategy`; appropriate admin rights are required.
- Never forge an `Authentication` with Alice's name just to bypass security checks and write data.
- Account/tenant state can change before an async job runs; re-verify identity and policy for long-lived tasks.

### 5.3. Why @PreAuthorize Does Not Replace Object READ Checks

`@PreAuthorize("hasAuthority('document:create')")` protects the **create action**. It creates no ACEs and does not guard any READ/WRITE methods. Other methods can use:

~~~java
@PreAuthorize("hasPermission(#p0, 'example.documents.Document', 'READ')")
public DocumentView readById(Long documentId) {
    return repository.loadView(documentId);
}
~~~

This is a **snippet** depending on repository/domain types. The type literal must match the stored `ObjectIdentity`, and `'READ'` must be understood by the evaluator/factory. You must enable `@EnableMethodSecurity` and wire `AclPermissionEvaluator` into `MethodSecurityExpressionHandler`; otherwise expressions may fall back to a deny-all default evaluator.

### 5.4. Proxies and @Transactional Must Actually Execute

Both `@PreAuthorize` and `@Transactional` in default Spring AOP require calls to **pass through a Spring-managed proxy**. If the same bean calls `this.create(command)`, the advice can be skipped. Split callers into a separate bean and test the `@Autowired` service bean to confirm active transactions and real rollbacks.

**Never use `@PostAuthorize` to guard a create operation**: by the time post-authorization runs, the domain row or external side effects may already have been created. Feature-level authorization must block upfront.

## 6. ACL Persistence Configuration Needed Before Using the Service

The ACL library is a separate module. Example `build.gradle` dependencies in a project already configured with the Spring Boot plugin, Java 17+, and dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.security:spring-security-acl'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

If production uses PostgreSQL/MySQL, swap out the H2 driver and adjust schema/SQL/dialect accordingly. The dependencies block **is not** a standalone build file; plugins/versions and DB config are still needed. The ACL schema should be created via controlled migrations (Flyway/Liquibase), not by expecting Hibernate `ddl-auto` to generate all four ACL tables.

### 6.1. Core ACL Beans

Typical Spring Security ACL configuration example:

~~~java
@Configuration
@EnableMethodSecurity
class AclConfiguration {

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
    JdbcMutableAclService mutableAclService(
            DataSource dataSource,
            LookupStrategy lookup,
            AclCache cache) {
        return new JdbcMutableAclService(dataSource, lookup, cache);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache cache,
            AclAuthorizationStrategy authStrategy,
            PermissionGrantingStrategy grantStrategy) {
        return new BasicLookupStrategy(
                dataSource, cache, authStrategy, grantStrategy);
    }

    @Bean
    AclCache aclCache(PermissionGrantingStrategy grantStrategy,
                      AclAuthorizationStrategy authStrategy) {
        return new SpringCacheBasedAclCache(
                new ConcurrentMapCache("aclCache"),
                grantStrategy, authStrategy);
    }

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
                new SimpleGrantedAuthority("ROLE_ACL_ADMIN"));
    }

    @Bean
    PermissionGrantingStrategy grantStrategy() {
        return new DefaultPermissionGrantingStrategy(
                new ConsoleAuditLogger());
    }
}
~~~

This is a **bean configuration snippet** with imports omitted for brevity; the corresponding classes come from `org.springframework.security.acls.*`, `org.springframework.security.access.expression.method.*`, `org.springframework.cache.concurrent.*`, `org.springframework.security.config.annotation.method.configuration.*`, and `javax.sql.DataSource`. The wiring follows the official ACL reference. It omits `SecurityFilterChain`, JPA entities, driver-specific JDBC SQL, migrations, and repositories, so it is **not a self-contained runnable Spring Boot project from this block alone**.

### 6.2. Schema and DB Dialect

Four tables are required:
- `acl_sid`
- `acl_class`
- `acl_object_identity`
- `acl_entry`

A new JDBC ACL setup can fail at `createAcl` due to missing tables, wrong dialect ID-generation queries, or key constraints. `JdbcMutableAclService` defaults to HSQLDB-style SQL; on other DBs you must configure `sidIdentityQuery`, `classIdentityQuery`, `objectIdentityPrimaryKeyQuery`, or matching SQL. Never copy HSQLDB DDL verbatim onto PostgreSQL/MySQL and assume it works.

Ensure proper unique constraints on class + object identity, foreign keys, and indexes for ACL lookups. Use versioned migrations and write tests creating multiple objects consecutively and reading permissions back after commit.

### 6.3. Can JPA and ACL JDBC Share the Same Transaction?

Yes, **if they truly share the same transaction resource**: for example, configuring `JpaTransactionManager` appropriately for the JPA `EntityManager` and JDBC access on the **same DataSource**. Never assume `@Transactional` alone places every connection across every bean into one transaction. Cases that break atomicity include:

- Entities stored in DB-A while ACLs live in DB-B.
- ACLs using a separate DataSource or non-transactional connection.
- `@Transactional(propagation = REQUIRES_NEW)` on an ACL helper committing before the domain transaction.
- Using `@Async` to write ACLs on another worker thread; the transaction context does not automatically propagate.
- Firing an `AFTER_COMMIT` event to create ACLs after domain creation without a pending state or compensation.
- Calling a transactional method via self-invocation so the advice never runs.

**Prove it with an integration test:** simulate an ACL write failure and verify in the DB afterward that **neither the Document nor any ACL/ACE remains**. If synchronous rollback is impossible, design an eventual provisioning architecture with a safe locked access state.

## 7. Create API and How to Respond

The controller accepts client input, while authorization and tenant come from security/services:

~~~java
@RestController
@RequestMapping("/api/documents")
class DocumentController {
    private final CreateDocumentService service;

    DocumentController(CreateDocumentService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    Map<String, Long> create(
            @Valid @RequestBody NewDocument request) {
        Long id = service.create(request);
        return Map.of("id", id);
    }
}
~~~

This snippet depends on the service/record from the previous section, importing from Spring Web, Jakarta Validation, and `java.util.Map`. A `Location: /api/documents/{id}` header can be added per your REST contract.

Expected outcomes:
- Authenticated caller with `document:create`, valid input, domain+ACL committed: **201** with ID.
- Missing authority: typically **403**, before saving.
- Unauthenticated: typically **401** with HTTP Basic/Bearer per entry point.
- Empty or oversized `title`: **400** via `@Valid` in Spring MVC.
- ACL database error: **never return fake success**; roll back and return a controlled server error without leaking SQL/tenant/ACL internals.
- Repeated request: handle per idempotency policy; do not accidentally create two Documents and two ACLs.

**CSRF:** With session/cookie auth, POST needs a valid token when CSRF protection is enabled; MockMvc tests may need `with(csrf())`. This is HTTP request protection, independent of ACL creation.

## 8. When to Use Parent ACLs and entriesInheriting?

A Document inside a Folder may need to inherit READ from the folder, but **that does not mean it should automatically inherit all permissions**. For newly created objects, inheritance must be chosen deliberately by policy.

### 8.1. Non-Inheriting by Default

In the service above:

~~~java
acl.setEntriesInheriting(false);
~~~

This makes clear that the Document relies solely on its local ACEs until a valid parent relationship is configured. Without a parent link and proper inheritance, Spring ACL never automatically looks up folders in domain tables.

### 8.2. Intentional Inheritance from a Folder

~~~java
// Snippet inside a transaction and after permissions are verified.
ObjectIdentity parentId =
        new ObjectIdentityImpl(Folder.class, trustedFolderId);
Acl parentAcl = aclService.readAclById(parentId);

MutableAcl childAcl = aclService.createAcl(documentId);
childAcl.setParent(parentAcl);
childAcl.setEntriesInheriting(true);
childAcl.insertAce(childAcl.getEntries().size(),
        BasePermission.READ, creatorSid, true);
aclService.updateAcl(childAcl);
~~~

Here `documentId` is an `ObjectIdentity`, not a raw Long; `trustedFolderId` comes from a verified domain/service lookup. Never take an arbitrary parent ID from the request and link a child ACL to another tenant's ACL.

**Two points to remember:**
1. `setParent(parentAcl)` only establishes the link; `entriesInheriting` controls whether parent permissions are consulted when no matching local ACE decides.
2. Spring ACL inheritance has no built-in "READ only, not WRITE" flag. If the parent has WRITE and the child inherits, WRITE can propagate when no local ACE overrides it. For sensitive documents, disable inheritance or add explicit policies/boundaries restricting WRITE.

### 8.3. Missing Parent ACL

If the Folder has no ACL yet, never synthesize an empty parent ACL from client input and grant unexpected permissions. Choose a policy:
- Reject Document creation until the Folder is properly provisioned.
- Or provision the Folder ACL via a separate administrative workflow in the same transaction.
- Or create the Document as private with inheritance false, attaching the parent only once validated.

**Never catch `NotFoundException` and grant broad permissions to "keep things working."** A missing ACL signals a need for provisioning/repair, never a reason to skip checks.

## 9. Idempotency, Retries, and Duplicate ACL Creation

### 9.1. Do Not Confuse Retries with createAcl on the Same ID

`MutableAclService.createAcl(oi)` throws `AlreadyExistsException` when an ACL already exists. On a create request that generates a new DB ID, an unguarded retry can create a **new Document** and a new ACL; not a duplicate ACL for the same ID, yet still a duplicate business object.

Common strategy:
- Client sends an `Idempotency-Key` when creating a Document.
- Server binds the key to the principal/tenant and payload fingerprint.
- Store the creation outcome (documentId, status) with a unique constraint on key/scope.
- Retries with the same key return the same documentId **once the transaction completes**, without creating again.
- A request reusing the key with a different payload is rejected cleanly (e.g., 409 per API contract).
- Persist the idempotency record atomically with domain/ACL when possible; otherwise provide reconciliation.

### 9.2. Should You Catch AlreadyExists and Continue?

Only if the use case is explicitly **ensure ACL exists**, not "create fresh ACL." A repair/migration service may read the existing ACL and adjust it per policy **after** verifying the ObjectIdentity belongs to the right domain/tenant. During a new-creation request, an existing ACL for a newly allocated ID is an **anomaly to investigate**; never append ACEs without knowing its origin or owner.

### 9.3. Concurrent Creation

A unique key on `acl_class + object_id_identity` prevents duplicate ACLs for the same object. If concurrent requests attempt to create an ACL for the same ID, one succeeds and the others hit a constraint or `AlreadyExistsException`. Never use a "check exists → create" pattern without a DB constraint: two threads can both observe it as absent.

Endpoint idempotency and ACL unique constraints solve **two different problems**: one prevents duplicate business creation on client retries, while the other prevents duplicate policies for the same ObjectIdentity.

## 10. Atomicity and Intermediate Failure States

| Failing step | In one true transaction | If sources commit separately |
| --- | --- | --- |
| `saveAndFlush` fails | Neither Domain nor ACL completes | Stop writing; handle DB error |
| `createAcl` fails | Rolls back Document | Can leave an "ACL-less orphan" Document |
| `insertAce` or `updateAcl` fails | Rolls back Document and created ACL | Can leave an empty/incomplete ACL |
| Transaction commit fails | Rolls back all participating resources | State across both sources is inconsistent |
| Response lost after commit | Client sees error, yet Document+ACL committed | Needs idempotency key to return same result |
| Delayed ACL job | Never expose object publicly before granting | Requires PENDING state and fail-closed read/write |

**Safety rule:** if the business rule is "a Document must not exist without its ACL," the transaction must span both writes. If that is impossible, model "incomplete provisioning" as a state that **cannot be read, shared, or written** until the ACL is active.

### 10.1. Is @TransactionalEventListener AFTER_COMMIT Appropriate?

If you create a Document and emit a `@TransactionalEventListener(phase = AFTER_COMMIT)` event to create the ACL, the listener runs **only after the Document has committed**. This can fit an eventual-consistency design with a `PENDING_ACL` status, but **provides no atomicity** between the Domain row and ACL row.

If the listener fails or the process crashes, a Document can be left without an ACL. For a resilient design:
- Commit the Domain in a PENDING state alongside an outbox record.
- A worker reads the outbox, provisions the ACL idempotently, verifies owner/tenant/ACEs, and transitions status to ACTIVE.
- Queries, reads, and writes block any non-ACTIVE Document, even if its ACL is missing.
- Use retry backoff, dead-letter/alerts, and reconciliation jobs; audit any manual repairs.
- Only report "created and ready to use" after provisioning finishes per the API contract.

### 10.2. When Two Databases Cannot Share a Transaction

Use orchestration/sagas or an outbox with compensating actions. Never wrap one local transaction and claim cross-database all-or-nothing guarantees. For sensitive workloads, consider keeping ACLs in the same database/schema as the domain to reduce complexity and prove consistency easily.

## 11. Reading ACLs Back After Commit and Verifying Real Permissions

A successful `createAcl` call does not prove ACEs were saved, because ACEs are persisted only by `updateAcl`. Integration tests should read back via `AclService` after the transaction finishes:

~~~java
// Inside an integration test with a real DB and appropriate principal.
ObjectIdentity oi = new ObjectIdentityImpl(Document.class, documentId);
Sid alice = new PrincipalSid("alice");

Acl acl = aclService.readAclById(oi, List.of(alice));

assertEquals(oi, acl.getObjectIdentity());
assertTrue(acl.isGranted(
        List.of(BasePermission.READ), List.of(alice), false));
assertTrue(acl.isGranted(
        List.of(BasePermission.WRITE), List.of(alice), false));
~~~

This is a JUnit snippet importing `Acl`, `Sid`, `ObjectIdentity`, `BasePermission`, and static assertions. Tests should prove:
- An ACL for the exact Document type + ID exists.
- `getEntries()` contains the intended ACEs (no accidental grants to ROLE_USER or other principals).
- The owner has READ/WRITE per policy; others are denied.
- READ/WRITE are verified through Spring method security/`AclPermissionEvaluator` on real service calls.
- After a simulated rollback, neither Document nor ACL exists in the DB.

`Acl.isGranted(...)` can throw `NotFoundException` when no matching ACE exists for another user; negative tests should assert according to contract rather than blindly asserting false directly. Some inspection tests should also call `AclService.readAclById(oi)` without a SID filter or pass the full relevant SID list to avoid incomplete ACLs.

### 11.1. Choosing the Right Test Transaction Setup

A `@SpringBootTest @Transactional` test method normally rolls back all fixtures when the test ends. That is useful, yet does not verify the **production commit path**. For post-commit verification:
- Invoke the service through its Spring bean/proxy outside a test transaction, or use `TestTransaction` to explicitly end and start transactions.
- After the service returns, read the ACL back from the DB using a fresh connection/transaction.
- Run a failure-injection scenario where `updateAcl` throws a runtime exception, and confirm neither the domain record nor the ACL remains.
- Test against the production dialect or Testcontainers to catch differences in identity queries, FKs, schema, and transaction enlistment.

Never replace an integration test with a mocked `MutableAclService` and conclude that DB rollback works.

## 12. Unit Testing the Workflow vs. Integration Testing: What to Check at Each Layer?

### 12.1. Unit Tests Verify Call Ordering

A unit test with Mockito can fake the repository and ACL service to prove:
1. Domain save runs before `createAcl`.
2. `ObjectIdentity` uses the newly allocated ID.
3. Creator SID comes from the trusted actor.
4. READ/WRITE are inserted, with no DELETE or public ACEs.
5. `updateAcl` is called only after ACEs are inserted.
6. A `createAcl` failure propagates instead of returning a success ID.

Example test skeleton (incomplete file without domain fixtures):

~~~java
// Inside a @ExtendWith(MockitoExtension.class) test.
InOrder order = inOrder(repository, aclService, mutableAcl);

order.verify(repository).saveAndFlush(any(Document.class));
order.verify(aclService).createAcl(any(ObjectIdentity.class));
order.verify(mutableAcl).setEntriesInheriting(false);
order.verify(mutableAcl).insertAce(
        eq(0), eq(BasePermission.READ),
        eq(new PrincipalSid("alice")), eq(true));
order.verify(mutableAcl).insertAce(
        eq(1), eq(BasePermission.WRITE),
        eq(new PrincipalSid("alice")), eq(true));
order.verify(aclService).updateAcl(mutableAcl);
~~~

**Note:** `InOrder` across multiple mocks must match actual calls in exact order; if the mock repository has extra internal calls or `getEntries().size()` is invoked on the mock ACL, you may need to stub `getEntries()` and/or verify only the key interactions. This example is purely illustrative and cannot be pasted and run without Mockito mocks and imports.

Unit tests **do not verify** `@Transactional`, `@PreAuthorize`, ACL schema, generated IDs, or caching. Those belong in integration tests.

### 12.2. Business + JDBC ACL Integration Tests

Essential cases:

| Case | Expectation |
| --- | --- |
| Alice has `document:create`, valid title | Document and ACL/READ/WRITE both appear |
| Alice lacks `document:create` | `AccessDeniedException`, no Document or ACL created |
| Empty/oversized title | HTTP 400/validation error per contract, nothing created |
| Repository fails to generate ID | Error, no ACL created with null ID |
| ACL create fails | Document rolls back; never returns 201 |
| ACL update fails after create | Both empty ACL and Document roll back |
| Duplicate ObjectIdentity | `AlreadyExistsException` or proper idempotency handling, no unintended permission widening |
| ACL owner differs from business actor | Requires clear policy, no accidental admin grant |
| Unverified tenant | DENY before saving |
| Creator is Alice | Only Alice gets READ/WRITE per ACEs; Bob is denied |
| Re-submit same Idempotency-Key | One Document and one ACL, returns same ID |
| Parent Folder in another tenant | Reject or keep private, never inherit across tenants |
| Multi-instance DB/caches | New permissions and revocations obey consistency contract |
| Concurrent create requests | Unique constraints/idempotency work, no duplicate ACLs |
| App restart, reload ACL | Permissions remain intact, not just in-memory state |

### 12.3. Testing @PreAuthorize and @Transactional Through Proxies

`@Autowired CreateDocumentService service` injects the Spring bean so Spring AOP intercepts calls. Include at least one grant test and one deny test; if you only test deny, a broken deny-all configuration can still pass. Use `@WithMockUser` or request tests with `httpBasic(...)`/`jwt()` depending on test level.

Never instantiate `new CreateDocumentService(...)` and assume annotations run. Self-invocation `this.create(...)` can also bypass the proxy. If a controller test mocks the entire service, it does not prove the ACL workflow is enforced.

## 13. Standalone Java 17: Simulating Single-Step Business Object and ACL Creation

The following program uses plain JDK with no Spring dependencies. It illustrates the principle: **prepare data and ACL in a staging area, and publish results only once both are ready**. In this example, a `Bundle` holding both Document and ACL is placed into **a single map** in one step. This is a learning model, **not a real transaction manager or JDBC ACL**.

Save as `ProvisioningDemo.java`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class ProvisioningDemo {
    record Document(long id, String owner, String title) {}
    record Acl(long documentId, String sid, Set<String> permissions) {}
    record Bundle(Document document, Acl acl) {}

    static final class Store {
        private final Map<Long, Bundle> committed = new LinkedHashMap<>();
        private long nextId = 1L;

        synchronized long create(String actor, String title,
                                 boolean failProvisioning) {
            if (actor == null || actor.isBlank()
                    || title == null || title.isBlank()) {
                throw new IllegalArgumentException("Invalid input");
            }

            long id = nextId++; // ID is obtained before ACL; sequence may have gaps.
            Document document = new Document(id, actor, title);
            Acl acl = new Acl(id, actor, Set.of("READ", "WRITE"));

            // Simulate failure before publishing bundle.
            if (failProvisioning) {
                throw new IllegalStateException("ACL provisioning failed");
            }

            committed.put(id, new Bundle(document, acl));
            return id;
        }

        boolean allowed(long id, String actor, String permission) {
            Bundle bundle = committed.get(id);
            return bundle != null
                    && bundle.acl().sid().equals(actor)
                    && bundle.acl().permissions().contains(permission);
        }

        int total() {
            return committed.size();
        }

        int incomplete() {
            int count = 0;
            for (Bundle bundle : committed.values()) {
                if (bundle.document() == null || bundle.acl() == null) {
                    count++;
                }
            }
            return count;
        }
    }

    public static void main(String[] args) {
        Store store = new Store();

        long id = store.create("alice", "Plan A", false);
        System.out.println("created-id=" + id);
        System.out.println("alice-read=" +
                store.allowed(id, "alice", "READ"));
        System.out.println("alice-write=" +
                store.allowed(id, "alice", "WRITE"));
        System.out.println("alice-delete=" +
                store.allowed(id, "alice", "DELETE"));
        System.out.println("bob-read=" +
                store.allowed(id, "bob", "READ"));

        try {
            store.create("bob", "Broken", true);
        } catch (IllegalStateException failed) {
            System.out.println("failed=" + failed.getMessage());
        }

        System.out.println("committed=" + store.total());
        System.out.println("incomplete=" + store.incomplete());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac --release 17 ProvisioningDemo.java
java ProvisioningDemo
~~~

**Exact stdout:**

~~~text
created-id=1
alice-read=true
alice-write=true
alice-delete=false
bob-read=false
failed=ACL provisioning failed
committed=1
incomplete=0
~~~

Analysis:
- ID 1 is allocated before attaching the ACL; Alice has READ/WRITE, not DELETE.
- Bob cannot read Document 1 because his SID differs.
- Bob's creation intentionally fails **before publishing**; `committed` holds one complete bundle, with zero ACL-less records.
- `nextId` can increment even when a task fails; gaps in sequences are not transaction bugs.
- In a real DB, two tables do not become atomic merely from two `put` calls or `synchronized` code. You must use transactions/constraints/outbox per your architecture.

## 14. Common Implementation Mistakes

### Mistake 1 — Saving Only the JPA Entity, Forgetting the ACL
`repository.save(...)` does not automatically insert `acl_object_identity`/`acl_entry`. The creator may be unable to read their own object, or another service may bypass ACLs to read it. Place provisioning in the creation workflow and test ACLs after commit.

### Mistake 2 — Creating the ACL Before the Generated ID Exists
`ObjectIdentityImpl(Document.class, entity.getId())` receives an ungenerated ID. With JPA generated IDs, save/flush first and verify non-null ID. Keep type + ID stable rather than inconsistently switching between Long and String.

### Mistake 3 — Calling createAcl and Forgetting insertAce/updateAcl
`createAcl` creates an empty ACL. The ACL owner does not automatically receive READ/WRITE. Add ACEs per policy, call `updateAcl`, and read back in an integration test.

### Mistake 4 — Granting ROLE_USER So "Any Creator Can Read"
A `GrantedAuthoritySid("ROLE_USER")` READ ACE on a Document grants access to **everyone** with `ROLE_USER`, not just the creator. Use `PrincipalSid(creator)` or an appropriately scoped group SID.

### Mistake 5 — Trusting Client-Supplied creatorId or tenantId
A client can spoof `creatorId=bob` or `tenant=other`. Accept only non-sensitive metadata from payloads; creator and tenant must come from verified authentication/identity services.

### Mistake 6 — Assuming @Transactional Covers Multiple DBs or Async Work
If the domain transaction and JDBC ACL use different DataSources or transaction managers, a rollback may undo only half. Test with failure injection and verify real transaction boundaries.

### Mistake 7 — Creating ACLs After Commit Yet Returning 201 as Ready
A worker may crash before creating the ACL. If using eventual provisioning, keep the object PENDING and block access until the ACL is complete; use outbox/retry/reconciliation.

### Mistake 8 — Catching AlreadyExists and Silently Opening Up ACEs
A race or config bug could lead to another object's or policy's ACL. In a new-creation workflow, distinguish duplicate requests/IDs and handle idempotency; modify existing ACLs only in authorized, audited management flows.

### Mistake 9 — Skipping Parent ACL Scope Checks
A child inheriting from a Folder in another tenant can inherit that tenant's grants. Verify the parent is trusted, both sides' owner/tenant match, and the actor is authorized to change the parent.

### Mistake 10 — Abusing ACL Admin Identity on Regular Requests
`AclAuthorizationStrategy` governs editing ACL owners/ACEs. Never grant `ROLE_ACL_ADMIN` to everyone just to stop `insertAce` errors. When a new ACL is created, a legitimate owner can typically add ACEs under the strategy; proxy jobs need a proper service identity and separate audit logs.

### Mistake 11 — Neglecting ACL Cleanup When Deleting Domain Objects
Deleting a Document while leaving its ACL causes orphans and risks if IDs are reused; deleting an ACL too eagerly can also break child ACLs. Use `MutableAclService.deleteAcl(oi, deleteChildren)` per policy and transaction, distinguishing hard vs. soft deletes. `deleteChildren` should not default to true when descendants must be kept.

### Mistake 12 — Not Controlling Cache When a New ACL Is Updated
Both the ACL cache and application decision caches can become stale. `updateAcl` must coordinate with version-aware invalidation; with multiple instances, design cache consistency. Never cache `"allowed=true"` without binding principal, tenant, object, permission, and policy version.

### Mistake 13 — Tests That Only Assert HTTP 201
201 does not prove the ACL, owner, or ACEs are right. Reload via `AclService`, inspect tables/permissions, test both Alice and Bob, failure rollbacks, duplicate requests, and restarts.

### Mistake 14 — Confusing Create Permission with Post-Create Read Permission
`document:create` only authorizes creation. All subsequent READ/WRITE operations must still enforce ACLs on the exact ObjectIdentity, alongside tenant scope and business-state policies.

### Mistake 15 — Mixing Controller Transactions with Service Proxies
`@Transactional` on a self-invoked method may never run; async events emitted by a controller may run outside the transaction. Place boundaries on a Spring-managed application service and test with real beans.

## 15. Operations and Security Checklist

| Stage | Check |
| --- | --- |
| Pre-create | Valid authenticated principal, `document:create` authority, server-sourced tenant |
| Domain input | Valid `title`/fields, never trust client owner/tenant |
| Identity | ID generated, non-null, canonical type, no ObjectIdentity collision |
| ACL init | Single `createAcl` for new object, right owner SID, no accidental public grant |
| ACE init | Exact READ/WRITE per policy, no unintended ADMIN/DELETE |
| Inheritance | False by default, or parent validated for tenant/permissions |
| Persistence | `updateAcl` after insertAce, valid DB schema/FKs/identity queries |
| Transaction | JPA and JDBC ACL share a real transaction; mid-way errors roll back both |
| API response | 201 only after valid provisioning; failures never return fake success |
| Retry | Idempotency-Key and unique constraints, no duplicate Document/ACL |
| Testing | Unit ordering, post-commit integration, grant/deny, rollback, proxies |
| Cache | ACL cache invalidation and multi-instance consistency |
| Lifecycle | Owner/tenant updates, parent moves, revocation, soft/hard delete, reconciliation |
| Monitoring | Metrics for ACL creation failures/orphans, safe auditing without leaking tokens/ACL secrets |

### Exercise 1 — What Order for Entity and ACL Creation?

A Document uses `IDENTITY` generation and `getId()==null` right after `new Document(...)`. Should you call `createAcl` immediately?

**Answer:** No. You must save the entity first to obtain a valid ID, typically via `repository.saveAndFlush(...)` inside the transaction before creating `ObjectIdentity`. Then call `createAcl`, add ACEs, call `updateAcl`, and commit.

### Exercise 2 — Can the ACL Owner Read?

Alice is the owner of a new ACL, yet has no READ ACE. Will `hasPermission(documentId, 'Document', 'READ')` definitely return true?

**Answer:** No. ACL ownership primarily governs ACL administration rights and does not automatically create a READ ACE. You must grant READ explicitly or apply an intentional policy.

### Exercise 3 — Missing updateAcl

A service calls `createAcl(oi)` and `insertAce(READ...)` but skips `updateAcl(acl)`. Can you be sure the ACE is persisted?

**Answer:** No. `insertAce` mutates the in-memory ACL object; `updateAcl` is the operation that persists changes to the database under the `MutableAclService` contract.

### Exercise 4 — ACL Fails While Document Remains

An application has two databases: DB-A stores Documents and DB-B stores ACLs. After A commits, B errors out. Does `@Transactional` on the service guarantee deleting the committed Document?

**Answer:** Not without distributed transactions/coordination. Design compensation or a saga/outbox with a PENDING state blocking access, and report errors per contract.

### Exercise 5 — Inheriting READ from Folder Without Propagating WRITE

A Document is created under a Folder whose ACL grants READ/WRITE to `ROLE_EDITOR`. The Document should inherit only READ. If you set `entriesInheriting=true`, does WRITE stay blocked by default?

**Answer:** No. Inheritance has no per-permission allow-list via a single flag. Disable inheritance, create a local READ ACE, or add an explicit policy restricting WRITE, and test across multiple SIDs/ACEs.

## 16. Summary

A proper ACL-enabled object creation flow **does not stop at saving the entity**. Once the DB assigns an ID:
1. Build `ObjectIdentity(type, id)` using a stable convention.
2. Call `MutableAclService.createAcl(oi)` to create a valid empty ACL.
3. Configure owner/inheritance **intentionally**, without over-granting.
4. Call `MutableAcl.insertAce(...)` to grant exact permissions to the required SIDs.
5. Call `MutableAclService.updateAcl(acl)` to persist ACEs.
6. Return success only after domain and ACL have committed **consistently**; if asynchronous, enforce a PENDING state and safe recovery mechanics.

**Core principle:** *Provisioning permissions for a new object is part of the object-creation use case, with its own identity, transaction, and idempotency rules—not an automatic side effect of `repository.save()`.*

## Official References

- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): ACL model, four tables, `ObjectIdentity`, `createAcl → insertAce → updateAcl` example, and note that Spring does not auto-create ACLs from DAOs.
- [MutableAclService Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAclService.html): `createAcl`, `updateAcl`, `deleteAcl`, `AlreadyExistsException`, `NotFoundException`.
- [MutableAcl Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAcl.html): `insertAce`, `setParent`, `setEntriesInheriting`, `setOwner`.
- [JdbcMutableAclService Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html): JDBC persistence, DB-specific identity queries, and configuration.
- [Spring Security – Security Database Schema](https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html): structure of `acl_sid`, `acl_class`, `acl_object_identity`, `acl_entry`.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, interception, and custom expressions.
- [Spring Framework – Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxies/`@Transactional` and transaction boundaries.

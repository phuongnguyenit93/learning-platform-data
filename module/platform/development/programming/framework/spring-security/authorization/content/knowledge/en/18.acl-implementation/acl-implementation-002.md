# BasicLookupStrategy and How ACLs Are Loaded in Spring Security

## 1. Why Is an ACL Lookup Strategy Needed?

In Spring Security, an **Access Control List (ACL)** is the set of permissions granted or denied on **a specific business object**. A document with ID 42, for example, can have multiple ACEs (Access Control Entries): Alice has READ, Bob is denied WRITE, and the audit group has READ. To evaluate `hasPermission(...)`, the system must **find the right ACL**, load its ACEs/SIDs/masks/parent relationship, and apply the granting policy.

For a few documents, a single query does not seem costly. But on a screen listing hundreds of documents, querying the ACL repeatedly for each object easily causes **N+1 queries**, reloads the same ACEs repeatedly, or exhausts connection pools. An ACL can also have a **parent ACL** with inherited permissions, making data loading more complex.

Spring Security splits this problem across several components:

- `AclService`: business interface for **reading** ACLs by `ObjectIdentity`.
- `JdbcAclService`: an `AclService` implementation using JDBC.
- `LookupStrategy`: strategy for **finding and assembling** ACLs from storage for multiple ObjectIdentities.
- `BasicLookupStrategy`: default implementation based on **ANSI SQL**, aiming to optimize via batch queries.
- `AclCache`: caches loaded ACLs, avoiding refetching unchanged data.
- `PermissionGrantingStrategy`: **evaluates** ACEs to decide grant/deny; it is not a query strategy.
- `AclPermissionEvaluator`: connects ACLs with Spring Security's `hasPermission(...)` expression.

**Core takeaway:** `BasicLookupStrategy` is responsible for **loading and constructing the ACL structure**, not deciding "Alice can read" under an arbitrary policy. The final decision belongs to `Acl.isGranted(...)`/`PermissionGrantingStrategy` and other business conditions.

## 2. Flow from @PreAuthorize to the Database

A request to read a document can follow this flow:

```text
HTTP GET /documents/42
        |
        v
Controller -> Spring-managed service proxy
        |
        v
@PreAuthorize("hasPermission(#id, 'Document', 'READ')")
        |
        v
AclPermissionEvaluator
        |
        v
AclService.readAclById(ObjectIdentity, sids)
        |
        v
JdbcAclService
        |
        v
LookupStrategy.readAclsById(List<ObjectIdentity>, List<Sid>)
        |
        +--> AclCache (loaded ACLs)
        |
        +--> SQL via DataSource (ACL/ACE/parent not yet in cache)
        |
        v
Acl with ObjectIdentity, owner, ACE, parent, inheritance
        |
        v
Acl.isGranted(...) / PermissionGrantingStrategy
        |
        +--> GRANT -> service method executes
        |
        +--> DENY/insufficient evidence -> method blocked
```

The flow above is a conceptual diagram for method security using ACLs. The actual execution path also depends on the version, cache hits, how the evaluator is configured, SID data, and other security layers. Even without an HTTP request, a service can be invoked from a batch/job; ACL is a domain-object protection mechanism and does not depend on Servlets.

### Clearly Separating the Three Responsibilities

| Question | Primary component | Result |
| --- | --- | --- |
| "I need the ACL for Document 42" | `AclService` | `Acl` or not-found error |
| "Which tables to query, in what batch size, and how to reconstruct ACEs and parents?" | `LookupStrategy` / `BasicLookupStrategy` | Map `ObjectIdentity -> Acl` |
| "Does Alice have READ on this ACL?" | `Acl.isGranted` / `PermissionGrantingStrategy` | Grant, deny, or insufficient data to decide |

Increasing batch size does not change grant/deny outcomes. Changing `PermissionGrantingStrategy` does not reduce query count. Optimization must be applied at the right layer.

## 3. What Data Does BasicLookupStrategy Reconstruct?

Standard Spring Security ACL uses four tables:

| Table | Relevant contents |
| --- | --- |
| `ACL_CLASS` | Domain object type identity, e.g., `com.example.Document` |
| `ACL_SID` | Principal or granted authority used as a SID |
| `ACL_OBJECT_IDENTITY` | Object identity, parent ACL, owner SID, `entries_inheriting` |
| `ACL_ENTRY` | The ACEs: SID, mask, granting, `ace_order`, and audit flags |

An `ObjectIdentity` is identified by **object type** and **ID**. Two objects with the same numeric ID 42 but different classes must have two distinct ACL identities.

```java
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.model.ObjectIdentity;

ObjectIdentity document42 =
    new ObjectIdentityImpl(Document.class, 42L);
```

This is an **in-application** snippet assuming a `Document` domain class and the `spring-security-acl` dependency; it is not a standalone Java program.

The loaded ACL result can include:

- The ObjectIdentity and the ACL owner's SID.
- The ACEs in the order stored in the data model.
- `Permission` from the bit mask and `Sid` for each ACE.
- Parent ACL information if present.
- The `entriesInheriting` flag, indicating whether ACEs inherited from the parent should be considered.
- Structures supporting `Acl.isGranted(...)`, including the granting strategy and audit logger.

Do not confuse the **ACL owner** with the **domain object owner**. The ACL owner typically governs ACL administration/modification rights and does not prove that a database record belongs to that principal. Business tenant/ownership must still be verified against trusted server-side data.

## 4. Contract of LookupStrategy.readAclsById

The `org.springframework.security.acls.jdbc.LookupStrategy` interface has one main method:

```java
Map<ObjectIdentity, Acl> readAclsById(
    List<ObjectIdentity> objects,
    List<Sid> sids
);
```

Here:

- `objects`: list of ObjectIdentities to load; this is a **required** input.
- `sids`: list of SIDs the caller is interested in. **The interface allows implementations to leverage SIDs for optimization**.
- The result is a map from `ObjectIdentity` to the `Acl`s found. Objects without an ACL may **have no key**.
- The `LookupStrategy` contract does not require throwing `NotFoundException` on missing ACLs: multiple LookupStrategies can be chained or supplemented.

**Important distinction:** `AclService.readAclById(...)` normally throws `NotFoundException` when the requested ACL is not found. You should therefore distinguish:
 
1. The result map at **LookupStrategy** may omit an ObjectIdentity.
2. The **AclService** API may turn missing data into a `NotFoundException` per its contract.
3. `Acl.isGranted(...)` on **an existing ACL** may still throw `NotFoundException` because it finds no ACE/SID/permission to reach a decision.
4. Whether the domain object itself exists is a separate business query.

Do not infer that an ACL-related `NotFoundException` means "Document #42 does not exist." And never treat a missing ACL as granted access.

### Example Calling via AclService

```java
import java.util.List;
import java.util.Map;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.GrantedAuthoritySid;

ObjectIdentity id42 = new ObjectIdentityImpl(Document.class, 42L);
ObjectIdentity id43 = new ObjectIdentityImpl(Document.class, 43L);

List<Sid> sids = List.of(
    new PrincipalSid("alice"),
    new GrantedAuthoritySid("ROLE_READER")
);

Map<ObjectIdentity, Acl> loaded =
    aclService.readAclsById(List.of(id42, id43), sids);
```

This snippet requires a Spring-injected `aclService`, the `Document` class, and real ACL records in the database. Depending on the ACL state and service contract, the operation may throw `NotFoundException`; never assume every key is always present. SIDs should be built from an authenticated Authentication via `SidRetrievalStrategy` or a trusted policy, **never from a client-supplied username**.

Using `readAclsById(...)` instead of calling `readAclById(...)` repeatedly in a loop gives an opportunity for **batch loading**. However, actual optimization must be measured with SQL counters and data sizes, not assumed just from switching the method name.

## 5. Crucial Detail: BasicLookupStrategy **Ignores** the sids Parameter

The `BasicLookupStrategy.readAclsById(...)` Javadoc states explicitly that this implementation **completely ignores the `sids` parameter**. This has practical consequences:

1. Passing `List.of(new PrincipalSid("alice"))` **does not make SQL fetch only Alice's ACEs**.
2. The ACL is loaded with full SID/ACE information for the object, not a per-user trimmed ACL.
3. BasicLookupStrategy's `AclCache` must store **SID-complete ACLs** by design.
4. If each object has tens of thousands of SIDs/ACEs, I/O, object allocation, and cache memory costs can be large.
5. If true SID filtering is needed due to massive ACE counts, you may need a **custom LookupStrategy**, with redesigned caching and unloaded-SID handling.

Correct understanding:

```text
aclService.readAclById(document42, [PrincipalSid("alice")])
                     |
                     v
              BasicLookupStrategy
                     |
                     +-- sids: NOT used to filter at lookup
                     |
                     +-- loads ACL/ACE with all SIDs per implementation
                     |
                     v
      Full Acl -> evaluate Alice's permission afterward
```

**Incorrect** assumption: "Just passing the current SID guarantees BasicLookupStrategy executes SQL `WHERE sid = current_user`." The Javadoc warns of the exact opposite.

This is also why you must distinguish **batch optimization by ObjectIdentity** from **filtering optimization by SID**. BasicLookupStrategy supports the first; it does not implement the second.

### Why Did the Framework Authors Choose This Design?

When an ACL is cached under an ObjectIdentity key, storing the **complete ACL** prevents this bug:

- Alice loads an ACL containing only Alice's ACEs and puts it in the cache.
- Bob uses the same cache key and reads an ACL missing Bob's ACEs.
- The system makes authorization decisions from incomplete data.

A complete ACL keeps the cached value independent of whichever caller populated the cache entry. If you build a custom SID-filtering lookup, you must address what goes into the cache key, how missing SIDs are fetched later, and when `UnloadedSidException` is thrown—not just add a SQL condition.

## 6. How Does BasicLookupStrategy Execute Queries?

`BasicLookupStrategy` is designed for ANSI SQL compatibility and aims to retrieve ACLs efficiently within a normalized relational schema. Its Javadoc describes two main internal query forms:

- `lookupPrimaryKeys`: finds internal primary keys for the ObjectIdentities to read.
- `lookupObjectIdentities`: fetches the related ObjectIdentities and assembles ACL data.

Both queries share a **common select clause and order-by clause**, but use **different where clauses**. Thus the class exposes customization setters:

- `setSelectClause(String)`
- `setLookupPrimaryKeysWhereClause(String)`
- `setLookupObjectIdentitiesWhereClause(String)`
- `setOrderByClause(String)`

**This does not mean every call takes exactly two SQL round-trips**. With cache hits, many objects, batching, parent ACL relationships, and data reconstruction steps, the actual round-trip count can vary. Measure with your application's datasource proxy or SQL metrics.

In particular, `ace_order` ordering must be preserved. Grant/deny outcomes can change if `ORDER BY` is altered incorrectly, even when the number of ACE rows stays the same.

### Data Diagram

```text
ObjectIdentity: Document 42
        |
        +--> ACL_CLASS: "com.example.Document"
        |
        +--> ACL_OBJECT_IDENTITY
        |       id, object_id_identity=42
        |       owner_sid, parent_object, entries_inheriting
        |
        +--> ACL_ENTRY
                ace_order=0, sid=alice, mask=READ, granting=true
                ace_order=1, sid=ROLE_AUDITOR, mask=READ, granting=true
                ace_order=2, sid=bob, mask=WRITE, granting=false
                         |
                         v
                    Acl / ACE objects
                         |
                         v
              PermissionGrantingStrategy
```

This is an illustrative model, not an exact SQL schema copy. Actual DB column names and aliases in select/where clauses must match your schema and version.

**Extension point:** if data volume is huge and the database offers hierarchical queries or materialized views, you can write a different `LookupStrategy`. Spring Security discourages directly subclassing `BasicLookupStrategy` because the class **does not support subclassing** per its Javadoc; **implement `LookupStrategy`** directly if you truly need a different algorithm.

## 7. Batch Loading: Grouping Multiple ObjectIdentities

`BasicLookupStrategy` supports `setBatchSize(int)`. It bounds the size of the ObjectIdentity groups processed during lookup.

For example, a list page has 125 documents. If the application looks up ACLs one object at a time, you can trigger many lookups. With a batch size of 50 and a single call passing 125 IDs, uncached objects are split into smaller chunks per BasicLookupStrategy's mechanism.

```text
125 ObjectIdentities to check
          |
          v
separate cached objects
          |
          v
remaining misses -> lookup with batchSize=50
          |
          +-- batch 1: up to 50 ObjectIdentities
          +-- batch 2: up to 50 ObjectIdentities
          +-- batch 3: remainder
          |
          v
Map<ObjectIdentity, Acl>
```

This diagram illustrates **how to think about batch size**, and does not guarantee exactly 3 SQL queries or 3 DB round-trips. Query count also depends on parent relationships, primary key lookups, cache state, and version.

Basic configuration:

```java
BasicLookupStrategy lookup = new BasicLookupStrategy(
    dataSource, aclCache, aclAuthorizationStrategy, permissionGrantingStrategy
);
lookup.setBatchSize(50);
```

This fragment requires the Spring bean dependencies; `50` is only an **example** value, not a universal optimum for every system. Do not assume larger batch sizes are always faster:

- Some DBs/drivers limit the number of bind parameters in a SQL `IN (...)` clause.
- ACLs with many ACEs produce huge row counts and memory pressure even with small batches.
- Parent ACLs can trigger additional lookups.
- Too small a batch causes many round-trips; too large a batch causes heavy SQL queries and hurts tail latency.
- Cache hit ratios differ between real traffic and benchmarks.

Tune after measuring ObjectIdentities/request, ACEs/object, batch queries, latency, heap usage, and cache hit ratio.

### Do Not Assume Batch Lookup Automatically Fixes N+1

Suppose a controller returns 100 documents and then runs:

```java
for (Document d : documents) {
    boolean canRead = permissionEvaluator.hasPermission(
        authentication, d.getId(), "Document", "READ");
    // ...
}
```

This is a **potential N+1 anti-pattern**, because the evaluator may invoke AclService separately for each ID; a batch size on a single-element list lookup does not magically merge 100 calls into one bulk lookup.

When you need to filter a large set:

1. First check whether you can filter directly in the **data query scoped by tenant/owner/ACL**.
2. If using the ACL module, collect `ObjectIdentity` instances and call `AclService.readAclsById(...)` **in bulk** before checking results.
3. Preserve return order if the UI requires it.
4. Do not return page counts or total counts that leak forbidden objects.
5. Do not handle private data by "loading everything and filtering in the controller" if it causes leaks or overload.

`@PostFilter("hasPermission(filterObject, 'READ')")` can be syntactically convenient, but still requires performance measurement on large lists and does not replace scoped data queries.

## 8. Cache: Must Store **Complete** ACLs and Refresh When Permissions Change

The library defines `AclCache` with common operations:

- `getFromCache(ObjectIdentity)` and `getFromCache(Serializable pk)`.
- `putInCache(MutableAcl)`.
- `evictFromCache(ObjectIdentity)` and `evictFromCache(pk)`.
- `clearCache()`.

One implementation is `SpringCacheBasedAclCache`, wrapping an `org.springframework.cache.Cache`. The documentation notes that it manages transient fields inside `AclImpl` and assumes ACLs share the same `PermissionGrantingStrategy` and `AclAuthorizationStrategy` instances.

Example local cache in a sample app:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.model.AclCache;

Cache springCache = new ConcurrentMapCache("aclCache");
AclCache aclCache = new SpringCacheBasedAclCache(
    springCache, permissionGrantingStrategy, aclAuthorizationStrategy);
```

This is a **configuration fragment**, not runnable standalone. `ConcurrentMapCache` stores data in a single JVM's memory; it is fine for demos/tests, but does not synchronize ACLs across multiple app instances. In production you can use a shared cache with appropriate invalidation, while still verifying transaction behavior and revocation.

### Why Is a Stale ACL a Security Bug?

Scenario:

1. Bob has an ACE granting READ on Document 42.
2. The ACL is cached, and the permission evaluator lets Bob read.
3. An admin revokes Bob's ACE in the DB.
4. The stale cache still holds the READ grant.
5. Bob continues reading in violation of the new policy.

The fix is not just lowering the TTL. When an ACL changes, you need proper **invalidation** (synchronized across all nodes), checks for parent-child relationships, transaction race handling, and safe cache failure behavior. `JdbcMutableAclService` manages updates and cache interaction, but the application must also check whether other mutation paths (direct SQL, migrations, admin tools, event replication) leave the cache stale.

**Principle:** caching accelerates a security decision; cache lifecycle management must be treated as part of authorization design, not merely a performance tweak.

## 9. Parent ACLs and entriesInheriting

An `Acl` can have `getParentAcl()` and the `isEntriesInheriting()` flag. The data model allows documents in a folder to inherit ACEs from the parent folder. `BasicLookupStrategy` must assemble enough of the related structure so the evaluation layer can use the parent when policy allows.

```text
Folder A (parent ACL)
    |  ACE: ROLE_EDITOR -> READ grant
    |
    +-- Document 42 (child ACL)
          entriesInheriting = true
          ACE: Alice -> WRITE grant
```

When checking READ on Document 42, if the child's ACEs are inconclusive, `Acl.isGranted` can walk up to the parent per the strategy and inheritance flag. When `entriesInheriting=false`, the parent does not grant permissions to the child.

**Distinguish clearly**:

- **Loading the parent ACL**: a `LookupStrategy`/database/cache concern.
- **Whether parent permissions are inherited**: the `entriesInheriting` flag and `Acl.isGranted` semantics.
- **Permission to read the entity**: still requires verifying tenant/owner/business ACLs; cross-tenant parent ACLs must be prevented.

Parent ACLs can increase lookup depth, cached object counts, and invalidation complexity. Avoid parent cycles or invalid references; when changing a parent or inheritance flag, check the impact on child ACLs.

## 10. Configuring BasicLookupStrategy with JdbcMutableAclService

Below is a **component configuration** following the Spring Security reference pattern, suitable for a Spring Boot project with `spring-security-acl`, `spring-jdbc`, Spring Cache, Spring Security Method Security, and a DataSource. It is not a standalone Java file runnable via `javac`; it requires the ACL schema and matching dependencies.

```java
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
import org.springframework.security.acls.jdbc.LookupStrategy;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration
@EnableMethodSecurity
public class AclConfiguration {

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ACL_ADMIN")
        );
    }

    @Bean
    PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(new ConsoleAuditLogger());
    }

    @Bean
    AclCache aclCache(
            PermissionGrantingStrategy permissionGrantingStrategy,
            AclAuthorizationStrategy aclAuthorizationStrategy) {
        Cache springCache = new ConcurrentMapCache("aclCache");
        return new SpringCacheBasedAclCache(
            springCache, permissionGrantingStrategy, aclAuthorizationStrategy);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource, AclCache cache,
            AclAuthorizationStrategy aclAuthorizationStrategy,
            PermissionGrantingStrategy permissionGrantingStrategy) {

        BasicLookupStrategy lookup = new BasicLookupStrategy(
            dataSource, cache, aclAuthorizationStrategy,
            permissionGrantingStrategy);
        lookup.setBatchSize(50);
        return lookup;
    }

    @Bean
    JdbcMutableAclService aclService(
            DataSource dataSource, LookupStrategy lookupStrategy,
            AclCache cache) {
        return new JdbcMutableAclService(dataSource, lookupStrategy, cache);
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    static MethodSecurityExpressionHandler expressionHandler(
            AclPermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }
}
```

Key points to understand:

1. **DataSource** is supplied by the application. The ACL tables must already exist with a matching schema (especially identity keys, SIDs, masks, and `ace_order`).
2. **AclCache** uses the same `PermissionGrantingStrategy` and `AclAuthorizationStrategy` instances as `BasicLookupStrategy`.
3. **LookupStrategy** takes the DataSource/cache/authorization strategy/granting strategy; `setBatchSize(50)` is an option to tune after measuring.
4. **JdbcMutableAclService** supports both reading and modifying ACLs. If only reads are needed, `JdbcAclService(dataSource, lookupStrategy)` is an alternative.
5. **AclPermissionEvaluator** uses `AclService`.
6. **Expression handler** plugs the evaluator into method-security SpEL. `@EnableMethodSecurity` activates the corresponding infrastructure.
7. The `AclAuthorizationStrategyImpl` bean with `ACL_ADMIN` illustrates permission to perform ACL administration operations; think carefully about who receives this authority. It does not imply automatic read access to all domain objects.
8. The example cache is in-memory and **must not be assumed safe for multi-instance production** when ACEs can change on another node.
9. If your app uses a different schema or column names, adjust the SQL or mapping per the Javadoc rather than copying the config and changing one clause arbitrarily.

### Wiring into a Service

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasPermission(#documentId, 'com.example.Document', 'READ')"
    )
    public Document readDocument(@P("documentId") Long documentId) {
        return repository.findById(documentId).orElseThrow();
    }
}
```

This is an **application class**, requiring `DocumentRepository`, the `Document` entity, and real ACL data. The string `'com.example.Document'` must match the `ObjectIdentity`/class name stored in `ACL_CLASS`. Projects with a different package namespace must update it accurately. `@P` names the parameter so SpEL can reference it.

Important note: `AclPermissionEvaluator` handles ACL permissions, but **does not replace** tenant, soft-delete, or business ownership query logic. For multi-tenant data, combine ACLs with resource access policies and trusted scoped queries. If the evaluator denies access, method security blocks before the method runs; whether the API returns HTTP 403 or 404 is an API-layer decision, not BasicLookupStrategy's.

## 11. Customizing SQL Without Breaking Ordering and Mapping

The Javadoc provides setters to change select, where, and order-by clauses:

```java
lookup.setSelectClause(customSelect);
lookup.setLookupPrimaryKeysWhereClause(customPrimaryWhere);
lookup.setLookupObjectIdentitiesWhereClause(customIdentityWhere);
lookup.setOrderByClause(customOrderBy);
```

This is an **illustrative** fragment; the variables must be defined with SQL strings matching your schema and result-set mapping and cannot be copied as standalone code. **Never modify a single clause in isolation** if it makes select/order/where inconsistent. Both `lookupPrimaryKeys` and `lookupObjectIdentities` must produce data using the same alias and key conventions.

Guidelines:

- Use the exact aliases/column names expected by BasicLookupStrategy's mapper.
- Never drop `ace_order` from `ORDER BY` carelessly: ACE ordering can affect grant/deny outcomes.
- Ensure `ACL_OBJECT_IDENTITY`, `ACL_CLASS`, and `ACL_SID` keys join properly; never mix object IDs across classes.
- Write real JDBC tests covering objects with many ACEs, many SIDs, parents, missing ACLs, and multiple domain classes.
- Never concatenate HTTP inputs into SQL clauses. These setters are for **application-controlled** SQL configuration, not user filter parameters.
- Upgrading Spring Security may alter how the mapper reads the result set; run regression tests before deep customization.

### Class ID, ObjectIdentityGenerator, and ConversionService

Some ACL schemas store `ACL_CLASS.ID` and resolve class identities differently from the default. `BasicLookupStrategy` offers extension points such as `setAclClassIdSupported(...)`, `setObjectIdentityGenerator(...)`, and `setConversionService(...)`. These settings align with **your database identity model and ID types**.

Do not enable `setAclClassIdSupported(true)` blindly: confirm that your schema and queries use `ACL_CLASS`'s ID column per your version's contract. If your project uses UUID/string IDs, inspect `ObjectIdentity` support carefully, as many defaults assume `Long`-friendly IDs; do not force casts that break correctness.

## 12. Changing Strategy When Data Grows Too Large

Per the Javadoc, BasicLookupStrategy:

- Attempts to optimize within **ANSI SQL** and a normalized schema.
- **Ignores `sids`**.
- Does not support subclassing.
- Allows tuning batch size and certain SQL fragments.

If you have millions of ACLs, a single object with huge ACE counts, or very deep ACL hierarchies, those constraints may not fit. Options include:

1. **Optimize queries and indexes**: index ObjectIdentity keys, `ACL_ENTRY` foreign keys, `ACL_SID`, and `ace_order` where appropriate; inspect execution plans first.
2. **Bulk prefetch**: collect ObjectIdentities per request to avoid N+1.
3. **Layered caching**: cache full ACLs and invalidate on revocation; measure memory and hit ratios.
4. **Custom LookupStrategy**: use DB-specific queries (materialized views, hierarchical queries), carefully designing parent handling, ACE/SID order, missing objects, and caching.
5. **Adjust the data model**: when many objects share a policy, consider parent ACLs, groups, or direct domain permissions to reduce individual ACEs.
6. **Scoped data-source queries**: for large lists, a SQL/JPA query constrained by tenant/owner/ACL is often more efficient than loading full ACLs into the application and filtering afterward.

**Warning:** customizing lookup to load *only a subset of SIDs* changes cache semantics. You must handle `Acl.isSidLoaded(...)` and `UnloadedSidException` properly; if the cache key is only ObjectIdentity while the cached payload varies by caller, you risk missing permissions or inconsistent results. In security, a flawed optimization can be more dangerous than being slow.

## 13. Standalone Java 17: Simulating Batching and Caching

The program below **does not use Spring Security**. It simulates the idea of batch-loading multiple objects and caching them. The code does not replicate BasicLookupStrategy's SQL, parent ACLs, or grant/deny rules; its purpose is to show why **many individual lookups differ from a bulk lookup**.

Create `AclBatchLoadingDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class AclBatchLoadingDemo {
    private final Map<Long, List<String>> database = Map.of(
        1L, List.of("alice:READ", "team:READ"),
        2L, List.of("bob:READ"),
        3L, List.of("alice:WRITE")
    );
    private final Map<Long, List<String>> cache = new LinkedHashMap<>();
    private int databaseBatches;

    Map<Long, List<String>> load(List<Long> requested, int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize must be positive");
        }

        Set<Long> uniqueIds = new LinkedHashSet<>(requested);
        List<Long> missingCache = new ArrayList<>();
        for (Long id : uniqueIds) {
            if (!cache.containsKey(id)) {
                missingCache.add(id);
            }
        }

        for (int start = 0; start < missingCache.size();
                start += batchSize) {
            int end = Math.min(start + batchSize, missingCache.size());
            List<Long> batch = missingCache.subList(start, end);
            databaseBatches++;
            for (Long id : batch) {
                List<String> aces = database.get(id);
                if (aces != null) {
                    cache.put(id, aces);
                }
            }
        }

        Map<Long, List<String>> result = new LinkedHashMap<>();
        for (Long id : uniqueIds) {
            if (cache.containsKey(id)) {
                result.put(id, cache.get(id));
            }
        }
        return result;
    }

    public static void main(String[] args) {
        AclBatchLoadingDemo demo = new AclBatchLoadingDemo();

        Map<Long, List<String>> first =
            demo.load(List.of(1L, 2L, 3L, 999L), 2);
        System.out.println("First: found=" + first.size()
            + ", batches=" + demo.databaseBatches);

        Map<Long, List<String>> second =
            demo.load(List.of(1L, 2L, 3L), 2);
        System.out.println("Second: found=" + second.size()
            + ", batches=" + demo.databaseBatches);

        demo.cache.remove(2L);
        Map<Long, List<String>> third = demo.load(List.of(2L), 2);
        System.out.println("After eviction: found=" + third.size()
            + ", batches=" + demo.databaseBatches);

        System.out.println("Cached IDs: " + demo.cache.keySet());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac AclBatchLoadingDemo.java
java AclBatchLoadingDemo
```

Stdout:

```text
First: found=3, batches=2
Second: found=3, batches=2
After eviction: found=1, batches=3
Cached IDs: [1, 3, 2]
```

Analysis:

- The first call has four IDs and batch size 2, simulating two batch queries; ID 999 has no data so it is omitted from the result.
- The second call requests only cached IDs → no new database batches are triggered.
- Evicting ID 2 and calling again triggers one new batch.
- The result contains only IDs with an ACL, rather than synthesizing an empty ACL for 999.

**Limitations:** real Spring ACL applications use `ObjectIdentity` rather than a bare `Long`, include primary-key queries, parent ACLs, ACE rows, internal cache keys, and much more. The `batches` counter in this program is only a **simulated loop count**, not a guaranteed number of SQL queries Spring Security executes. The program also does not handle DB/cache mutations between calls; production requires an explicit invalidation plan.

## 14. Required Tests for BasicLookupStrategy

### Correct Data-Loading Tests

| Scenario | What must be proven |
| --- | --- |
| Single ObjectIdentity with ACL | Reads owner, ACE/SID/mask/grant, and order accurately |
| Two classes sharing numeric ID | Never mixes ACLs across classes |
| ACL with ACEs for multiple SIDs | BasicLookupStrategy does not drop ACEs simply because input `sids` omits them |
| Null SIDs list | Lookup still operates per supported contract |
| ACL missing in database | `LookupStrategy` returns map without key; `AclService` handles not-found per API |
| ACL with parent | Parent reference is accurate and inheritance is evaluated properly |
| Parent grants, child has no match | Result follows `entriesInheriting` and strategy |
| Deny and grant on same permission/SID | ACE order after loading is never reversed |
| Custom mask | `PermissionFactory` converts mask accurately |
| Principal and granted-authority SIDs | `createSid` reconstructs the proper SID types |
| Long IDs and custom IDs | Mapping never mixes types or values |
| Cache-hit read | Returned data matches initial load with no missing SIDs |
| Update ACE then re-read | Cache refreshes and revocations take effect |
| Multiple objects in one read | Accurate data per object, no cross-contamination |
| Object with very many ACEs | Measure latency, row counts, heap, and cache size |
| Database outage | Never grants access; infrastructure errors are monitored |

### Performance Tests

- Enable datasource SQL statistics or use a datasource proxy / Hibernate statistics as appropriate.
- Compare **N calls to `readAclById`** against **one `readAclsById`** for the same ID set, both cold-cache and warm-cache.
- Test batch sizes 10, 50, 100 (exploratory values, not default optima), measuring DB round-trips, rows/query, and time/query.
- Benchmark on datasets with many ACEs/SIDs and parent hierarchies, not just one entry per ACL.
- Observe `AclCache` hit/miss/eviction rates and memory; test revocation across multiple nodes.
- Inspect SQL execution plans after customizing select/where/order-by.
- Measure p95/p99 latency on list endpoints rather than relying only on averages.
- Verify performance improvements **do not alter authorization outcomes**.

### Security Integration Tests

Enable `@EnableMethodSecurity` and invoke services **through Spring-managed beans** to ensure `@PreAuthorize` executes; `this.securedMethod()` calls inside the same bean can bypass the proxy. Test with authorized roles/authorities, cross-tenant users, anonymous users, revoked ACLs, missing ACLs, and parent inheritance on/off.

If a controller returns 403 after denial, do not treat the HTTP status alone as complete proof that no data leaked. Verify the service/repository never returned unauthorized documents, no side effects occurred, and the cache does not hold stale ACLs.

## 15. Implementation Mistakes and How to Fix Them

| Mistake | Impact | How to fix |
| --- | --- | --- |
| Assuming passing `sids` makes BasicLookupStrategy filter ACEs per caller | Wrong row, memory, and cache estimates | Read the Javadoc: implementation ignores `sids` |
| Caching an ACL containing only the first user's SIDs under the shared ObjectIdentity key | Other users receive incomplete ACLs | Cache full ACLs or design a safe custom strategy/cache key |
| Calling evaluator per item in a large list | N+1 queries, high latency | Bulk lookup or scoped data queries |
| Treating batch size as SQL query count | Misleading performance metrics | Use real SQL logging/counters |
| Picking a huge batch size without measuring | Bind parameter limits, heap pressure, DB bottlenecks | Tune per DB/driver and ACE distribution |
| Not loading parent or ignoring inheritance | Wrong permission decisions | Test parents and `entriesInheriting` |
| Modifying `ORDER BY` and dropping ACE order | Grant/deny flips | Preserve ordering and write regression tests |
| Building SQL from HTTP parameters | SQL injection and data exposure risk | Use static/server-controlled SQL config |
| Thinking no ACL means no business object | Confuses errors, may leak resource existence | Separate ACL not-found from domain not-found |
| Catching all exceptions and returning allow | Fail-open | Fail closed, classify infrastructure errors |
| Updating ACLs without cache invalidation | Revoked permissions remain usable | Evict/invalidate consistently |
| Using local cache in a cluster expecting instant node sync | Stale ACLs across nodes | Use distributed invalidation/consistency |
| Subclassing BasicLookupStrategy to change the algorithm | Unsupported per Javadoc | Implement a custom `LookupStrategy` |
| Treating ACL owner as domain owner | Cross-tenant data leaks | Separate domain policy from ACL administration |
| Only writing unit tests with mocked batching | Real API/SQL behavior unverified | Write integration tests against a real schema and DB |

## 16. Pre-Production Checklist

1. **Do ACL tables match the required schema?** `ACL_CLASS`, `ACL_SID`, `ACL_OBJECT_IDENTITY`, `ACL_ENTRY`, and appropriate indexes.
2. **Are ObjectIdentities stable?** Class + ID, inherited data, long vs. custom IDs.
3. **Is the right LookupStrategy used?** BasicLookupStrategy does not filter by `sids`.
4. **Is batch lookup in place?** Not relying on single-item lookups inside loops.
5. **Was batch size measured or guessed?** Benchmarked cold/warm cache, high ACE counts, and parents.
6. **Does the cache store full ACLs?** Never partial ACLs under a shared cache key.
7. **Does cache invalidation run on update/delete/revocation?** Especially across multiple nodes.
8. **Does custom SQL preserve mapping and ordering?** Tested with masks, classes, SIDs, and ACE order.
9. **Is parent ACL policy consistent?** Inheritance, cycles, cross-tenant guards, child eviction.
10. **Are missing ACLs/ACEs handled safely?** No grant evidence → deny access.
11. **Are infrastructure errors separated?** Timeouts never masked as empty/missing ACLs.
12. **Do other authorization layers remain active?** Roles, tenant, resource ownership, soft delete.
13. **Are real interceptors tested?** `@EnableMethodSecurity`, Spring proxies, HTTP and non-HTTP callers.
14. **Are performance and errors monitored?** DB metrics, cache hit ratio, revocations, latency.
15. **Is there a migration plan when changing strategies?** Tested before/after upgrading Spring Security, DB schema, or cache.

**Summary:** `BasicLookupStrategy` is the **JDBC/ANSI SQL ACL-loading strategy** used by `JdbcAclService`. It groups ObjectIdentities by batch size, uses the ACL cache, and assembles ACL/ACE/parent structures, while **ignoring the `sids` parameter to restrict loaded ACEs**. Once the full ACL is loaded, `PermissionGrantingStrategy` evaluates grant/deny. Building a correct and fast ACL system requires treating **batch lookup, cache integrity, parent inheritance, ACE ordering, invalidation, and trusted business data** as one unified design.

## Official References

- [Spring Security — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): ACL model, JDBC tables, `AclService`, `BasicLookupStrategy`, and bean configuration example.
- [Spring Security API — BasicLookupStrategy](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/jdbc/BasicLookupStrategy.html): constructor, `readAclsById`, warning on ignoring `sids`, batching, and SQL customization.
- [Spring Security API — LookupStrategy](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/jdbc/LookupStrategy.html): Map read contract and meaning of `sids`.
- [Spring Security API — JdbcAclService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/jdbc/JdbcAclService.html): `readAclById`, `readAclsById`, `findChildren`, and `NotFoundException`.
- [Spring Security API — AclCache](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/AclCache.html): cache operations by ObjectIdentity/primary key and eviction.
- [Spring Security API — SpringCacheBasedAclCache](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/SpringCacheBasedAclCache.html): using Spring Cache and `AclImpl` transient fields.
- [Spring Security — ACL database schema](https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html): ACL tables and columns.

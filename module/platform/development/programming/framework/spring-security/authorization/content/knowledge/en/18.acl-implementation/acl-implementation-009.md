# AclCache, Cache Invalidation, and Multiple Instances

> **Topic:** Spring Security – authorization → **ACL Implementation**. This lesson explains the `AclCache` API, the `SpringCacheBasedAclCache` class, how JDBC ACL reads and refreshes caches, and why revoked permissions can still be allowed on another instance. Examples use Java 17+, Spring Boot 3.x, Spring Security 6.x, and HSQLDB. Event brokers, transactional outboxes, and distributed caches are presented as complementary deployment designs, not automatic features of `AclCache`.

## 1. ACL Caching Improves Speed, Yet Can Retain Revoked Permissions

Suppose `Document#101` has an ACE:

~~~text
ObjectIdentity = demo.aclcache.Document / 101
PrincipalSid("alice") -> READ -> granting=true
~~~

On every permission check, Spring Security ACL may need to assemble an `Acl` from multiple tables. Caching lets the system reuse loaded ACLs and cut down SQL queries. However, if an admin deletes the READ grant ACE while an instance serving requests still holds the old snapshot in memory, Alice may still be allowed to read the document after her permission was revoked.

~~~text
T1: Node A reads ACL from DB, caches alice's READ=grant
T2: Node B performs revoke, updates DB
T3: Node B's cache is invalidated
T4: Node A is unaware and still uses the stale cached ACL
T5: Node A risks returning a false allow
~~~

The issue is **stale authorization**, not merely latency. When adopting a cache, you must answer: after a revoke commits, **how long** before every node stops using the old ACL? Without a clear commitment on that bound, caching becomes a security risk.

## 2. At Which Layer Are ACLs Cached?

~~~text
HTTP / Service call
       |
       v
AclPermissionEvaluator or authorization service
       |
       v
     AclService
       |
       v
   JdbcAclService
       |
       v
  LookupStrategy / BasicLookupStrategy
       |
       +--------- cache hit --------> AclCache
       |
       +--------- cache miss -------> SQL database
                                       |
                                     Acl/ACE
                                       |
                                     AclCache
       |
       v
Acl.isGranted(permission, applicableSids, false)
       |
    ALLOW or DENY
~~~

`AclCache` stores ACL data: ObjectIdentity, ACEs, SIDs, permissions, ACL owner, parent/inheritance. It is not an application-level `user+object+action → true/false` decision table. One cached ACL can evaluate multiple users with different SIDs.

| Data type | Example | What to handle on change |
| --- | --- | --- |
| **ACL cache** | ACE for `Document#101` | Grant/revoke ACE, change ACL owner/parent |
| **Authentication/JWT/session** | Alice carries `ROLE_EDITOR` | Revoke role, lock user, refresh token |
| **Custom decision cache**, if any | Alice has WRITE on `Document#101` | ACL change **or** authority, tenant, policy |

Invalidating the ACL cache does not strip `ROLE_EDITOR` from an old JWT. Conversely, refreshing a token does not update a stale ACL in cache. For ACEs targeting `GrantedAuthoritySid`, both data sources participate in the decision.

## 3. Exact `AclCache` API

Package:

~~~java
import org.springframework.security.acls.model.AclCache;
~~~

| Method | Role |
| --- | --- |
| `getFromCache(ObjectIdentity oid)` | Retrieves cached `MutableAcl` by type + domain ID |
| `getFromCache(Serializable aclPk)` | Retrieves ACL by internal ACL primary key |
| `putInCache(MutableAcl acl)` | Stores an assembled ACL in cache |
| `evictFromCache(ObjectIdentity oid)` | Invalidates ACL by ObjectIdentity |
| `evictFromCache(Serializable aclPk)` | Invalidates ACL by database PK |
| `clearCache()` | Clears all ACLs in this cache backend/instance |

### Distinguishing the Two Keys

~~~text
Document ID = 101
ObjectIdentity(type="demo.aclcache.Document", id=101)
                       |
                       v
                   ACL record
                       |
                       v
ACL primary key in acl_object_identity table = 1472 (example)
~~~

Document ID 101 is **not automatically** ACL primary key 1472. `SpringCacheBasedAclCache` supports lookup/eviction by both key forms. If you touch the underlying `org.springframework.cache.Cache` directly and evict only one alias, stale data can still be read via the other alias. Always prefer `AclCache.evictFromCache(...)` over guessing internal keys.

A cache miss (null value) only means the cache currently lacks the ACL; **it does not prove the ACL is absent from the DB**. Lookups must consult the authoritative data source.

### The ACL Cache Can Hold Mutable Objects

`AclCache` works with `MutableAcl`. Never mutate `getEntries()` on a cached object expecting the database to update or other threads to see a consistent view. To administer permissions, use `MutableAclService`, modify ACEs, and call `updateAcl`; to read permissions, use `AclService` and `Acl.isGranted`. Never turn the cache into a source-of-truth write store.

## 4. `SpringCacheBasedAclCache` and the Spring Cache Abstraction

Common adapter example:

~~~java
import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.model.AclCache;

// ILLUSTRATION: both strategy beans already exist.
Cache springCache = new ConcurrentMapCache("acl-cache");
AclCache aclCache = new SpringCacheBasedAclCache(
        springCache,
        permissionGrantingStrategy,
        aclAuthorizationStrategy);
~~~

`SpringCacheBasedAclCache`'s constructor takes a Spring `Cache`, `PermissionGrantingStrategy`, and `AclAuthorizationStrategy`. It restores runtime fields of `AclImpl` when loading from cache, and per Javadoc assumes ACLs share those same strategy instances consistently.

### The Backend Determines Whether the Cache Is Shared

- `ConcurrentMapCache`: **in-JVM** cache; other nodes cannot automatically see evictions.
- Local Caffeine cache: normally also scoped to the current JVM.
- Redis/Hazelcast backend via Spring Cache: can be shared, yet requires verifying serialization, eviction, key aliases, tenant scoping, and reload races.
- No cache: removes a stale-ACL layer at the cost of higher SQL load; you still must handle transactions/races and current Authentication state.

Never call `ConcurrentMapCache` a distributed cache just because the app runs on Kubernetes with multiple replicas.

## 5. When Must ACLs Be Refreshed or Invalidated?

| Operation | Direct ACL | Cascading impact |
| --- | --- | --- |
| `createAcl(oid)` | New ACL | Any custom negative cache may have remembered a missing ACL |
| `updateAcl(acl)` adding READ grant | This ACL | Stale cache may keep denying |
| `updateAcl(acl)` removing READ grant | This ACL | Stale cache may keep **allowing** |
| `updateAcl(acl)` adding DENY | This ACL | If stale, deny may not take effect |
| Changing `getOwner()` / parent / inheritance | This ACL | May also affect child ACLs |
| `deleteAcl(oid, false)` | This ACL | If children exist, may throw `ChildrenExistException` |
| `deleteAcl(oid, true)` | This ACL and related children | Never delete ACL subtrees without controls |
| Revoking a user's `ROLE_REVIEWER` | Does not necessarily change ACLs | Update Authentication/JWT/session |
| Changing shared granting/deny policy | Many cached ACLs | May require clearing or bumping cache namespace version |
| Updating ACL tables via direct SQL | Affected ACLs | Bypasses service-layer invalidation |

**Revocation is the top priority.** With an unpropagated grant, a user may be temporarily denied (availability). With an unpropagated revocation, a user may **continue being falsely allowed** (confidentiality/integrity).

### Not Every Domain Object Update Requires ACL Eviction

If a document merely updates its title and ACLs do not depend on titles, evicting the ACL is unnecessary. However, if policy also checks `tenantId`, `locked`, owner, legal hold status, or workflow state, business policy must read authoritative state too; a cached ACL never substitutes for non-ACL conditions.

## 6. How Far Does `JdbcMutableAclService` Handle Invalidation?

`JdbcMutableAclService` is constructed with:

~~~java
new JdbcMutableAclService(
        dataSource, lookupStrategy, aclCache);
~~~

When writing via `MutableAclService`, the JDBC implementation cleans up the cache instance injected into it. On `updateAcl`, the standard implementation also handles dependent child ACLs since permissions can inherit from parents. Verify specific/older versions with tests and source for your target release.

**Key limitation:** the evicted cache is **the cache instance held by the writer**. If Node A holds `ConcurrentMapCache("nodeA")` and Node B holds `ConcurrentMapCache("nodeB")`, updating an ACL on Node A never invokes Java methods on Node B's cache.

### Transaction and Cache Ordering Can Create a Stale Window

~~~text
T1: Transaction A updates ACL in DB (uncommitted)
T2: A evicts cache and may reload the new ACL inside A's transaction
T3: B cache-misses, reads from DB under B's isolation level
T4: B may still see the old ACL if A has not committed yet
T5: Transaction A commits
T6: B may still hold the stale snapshot
~~~

`@Transactional` supports DB atomicity within one transaction, yet **does not turn a cache into a transactional cache**. Therefore distributed event designs should publish invalidations **after commit**; even an after-commit async event does not provide strong consistency if instant revocation is required.

## 7. Complete Demo: Two Independent Caches, One Shared HSQLDB

The sample uses Java 17+, Spring Boot 3.x, and Spring Security 6.x. It creates **Node A's cache** in the Spring Context; the integration test creates **Node B's cache** via separate `SpringCacheBasedAclCache` and `JdbcMutableAclService` instances sharing the same DataSource.

Two caches inside one JVM is only a **two-node simulation**; it faithfully reproduces independent-cache staleness without requiring two servers. In production, real nodes/JVMs also involve networking and deployment mechanics.

### 7.1. Dependencies

In a Spring Boot Gradle project with compatible Java, Spring Boot, and dependency management plugins:

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

The example requires the separate `spring-security-acl` module; the Security starter alone does not provide JDBC ACLs. Keep the Spring Security version aligned with Boot.

### 7.2. DataSource and Schema

**`src/main/resources/application.properties`**

~~~properties
spring.datasource.url=jdbc:hsqldb:mem:acl_cache_demo
spring.datasource.driver-class-name=org.hsqldb.jdbc.JDBCDriver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

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

This is HSQLDB-style DDL for the demo; for PostgreSQL/H2/MySQL, adjust the schema and JDBC ACL generated-ID queries. Production should use migrations instead of re-running `schema.sql`.

### 7.3. Application and Model

**`src/main/java/demo/aclcache/AclCacheApplication.java`**

~~~java
package demo.aclcache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class AclCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(AclCacheApplication.class, args);
    }
}
~~~

**`src/main/java/demo/aclcache/Document.java`**

~~~java
package demo.aclcache;

public record Document(long id, String title) {
}
~~~

`ObjectIdentity` in the example is `new ObjectIdentityImpl(Document.class.getName(), id)`. With Java records, avoid assuming `ObjectIdentityImpl(object)` reads the `id()` accessor automatically.

### 7.4. Configuring Node A Cache and JDBC Service

**`src/main/java/demo/aclcache/AclInfrastructure.java`**

~~~java
package demo.aclcache;

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
                new ConcurrentMapCache("node-a-acls"),
                permissionGrantingStrategy,
                aclAuthorizationStrategy);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache aclCache,
            AclAuthorizationStrategy aclAuthorizationStrategy,
            PermissionGrantingStrategy permissionGrantingStrategy) {

        return new BasicLookupStrategy(
                dataSource, aclCache, aclAuthorizationStrategy,
                permissionGrantingStrategy);
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
        handler.setPermissionEvaluator(
                new AclPermissionEvaluator(aclService));
        return handler;
    }
}
~~~

`lookupStrategy` and `aclService` receive the **same `AclCache`**. If a writer and reader inside the same process accidentally use two different caches, the writer evicts cache A while requests continue reading from cache B.

The `MethodSecurityExpressionHandler` bean wires `AclPermissionEvaluator` for apps using `hasPermission`. The tests below observe `AclService` directly to expose stale data without depending on a controller.

### 7.5. Grant/Revoke Service with Admin Gate and Transaction

**`src/main/java/demo/aclcache/AclWriterService.java`**

~~~java
package demo.aclcache;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AclWriterService {

    private final MutableAclService writer;

    public AclWriterService(MutableAclService writer) {
        this.writer = writer;
    }

    private ObjectIdentity oid(long id) {
        return new ObjectIdentityImpl(Document.class.getName(), id);
    }

    @Transactional
    @PreAuthorize("hasAuthority('ACL_ADMIN')")
    public void grantRead(long id, String username) {
        ObjectIdentity object = oid(id);
        MutableAcl acl;

        try {
            acl = (MutableAcl) writer.readAclById(object);
        }
        catch (NotFoundException missing) {
            acl = writer.createAcl(object);
        }

        Sid sid = new PrincipalSid(username);
        boolean exists = acl.getEntries().stream().anyMatch(ace ->
                ace.getSid().equals(sid)
                && ace.getPermission().getMask()
                    == BasePermission.READ.getMask()
                && ace.isGranting());

        if (!exists) {
            acl.insertAce(
                    acl.getEntries().size(),
                    BasePermission.READ,
                    sid,
                    true);
            writer.updateAcl(acl);
        }
    }

    @Transactional
    @PreAuthorize("hasAuthority('ACL_ADMIN')")
    public void revokeRead(long id, String username) {
        MutableAcl acl;

        try {
            acl = (MutableAcl) writer.readAclById(oid(id));
        }
        catch (NotFoundException missing) {
            return;
        }

        Sid sid = new PrincipalSid(username);
        boolean changed = false;

        for (int i = acl.getEntries().size() - 1; i >= 0; i--) {
            var ace = acl.getEntries().get(i);
            if (ace.getSid().equals(sid)
                    && ace.getPermission().getMask()
                       == BasePermission.READ.getMask()
                    && ace.isGranting()) {
                acl.deleteAce(i);
                changed = true;
            }
        }

        if (changed) {
            writer.updateAcl(acl);
        }
    }

    @Transactional
    @PreAuthorize("hasAuthority('ACL_ADMIN')")
    public void deleteAcl(long id) {
        writer.deleteAcl(oid(id), false);
    }
}
~~~

`@Transactional` wraps the SQL updates; `@PreAuthorize` checks that the caller holds `ACL_ADMIN` at the public service boundary. Private helpers have no annotations requiring a proxy. Grants are idempotent by checking existing ACEs, though that **does not prevent two concurrent transactions from racing**. Revoking one user ACE does not revoke grants still present via roles or parent ACLs.

### 7.6. Test: One Database, Two Independent `AclCache` Instances

**`src/test/java/demo/aclcache/AclCacheIntegrationTest.java`**

~~~java
package demo.aclcache;

import java.util.List;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.jdbc.LookupStrategy;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(classes = AclCacheApplication.class)
class AclCacheIntegrationTest {

    @Autowired AclWriterService writer;
    @Autowired AclService nodeAReader;
    @Autowired AclCache nodeACache;
    @Autowired DataSource dataSource;
    @Autowired AclAuthorizationStrategy aclAuthorizationStrategy;
    @Autowired PermissionGrantingStrategy permissionGrantingStrategy;

    private ObjectIdentity oid(long id) {
        return new ObjectIdentityImpl(Document.class.getName(), id);
    }

    private boolean canRead(Acl acl, String username) {
        List<Sid> sids = List.of(new PrincipalSid(username));
        try {
            return acl.isGranted(List.of(BasePermission.READ), sids, false);
        } catch (NotFoundException noMatchingAce) {
            return false;
        }
    }

    private record Node(AclCache cache, AclService reader) {
    }

    private Node createNodeB() {
        // Node B's cache is completely separate from cache A.
        AclCache cacheB = new SpringCacheBasedAclCache(
                new ConcurrentMapCache("node-b-acls"),
                permissionGrantingStrategy,
                aclAuthorizationStrategy);

        LookupStrategy lookupB = new BasicLookupStrategy(
                dataSource,
                cacheB,
                aclAuthorizationStrategy,
                permissionGrantingStrategy);

        AclService readerB =
                new JdbcMutableAclService(dataSource, lookupB, cacheB);

        return new Node(cacheB, readerB);
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void localWriterInvalidatesLocalCachedAcl() {
        ObjectIdentity object = oid(1101L);

        writer.grantRead(1101L, "alice");
        assertTrue(canRead(nodeAReader.readAclById(object), "alice"));
        assertNotNull(nodeACache.getFromCache(object));

        writer.revokeRead(1101L, "alice");

        assertFalse(canRead(nodeAReader.readAclById(object), "alice"));
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void nodeBRemainsStaleUntilItEvictsItsOwnCache() {
        ObjectIdentity object = oid(1202L);
        Node nodeB = createNodeB();

        writer.grantRead(1202L, "alice");

        // Warm cache B by reading through reader B.
        assertTrue(canRead(nodeB.reader().readAclById(object), "alice"));
        assertNotNull(nodeB.cache().getFromCache(object));

        // Writer A revokes in DB and invalidates cache A.
        writer.revokeRead(1202L, "alice");

        // B has not received the event yet, so it still uses the old ACL.
        assertTrue(canRead(nodeB.reader().readAclById(object), "alice"));

        // Simulate AFTER_COMMIT event arriving at Node B:
        nodeB.cache().evictFromCache(object);

        // B must fetch the new ACL from DB: no READ ACE remains.
        assertFalse(canRead(nodeB.reader().readAclById(object), "alice"));
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void deletionNeedsInvalidationInTheOtherNode() {
        ObjectIdentity object = oid(1303L);
        Node nodeB = createNodeB();

        writer.grantRead(1303L, "alice");
        assertTrue(canRead(nodeB.reader().readAclById(object), "alice"));

        writer.deleteAcl(1303L);

        // ACL in B still exists due to stale cache:
        assertTrue(canRead(nodeB.reader().readAclById(object), "alice"));

        nodeB.cache().evictFromCache(object);

        assertThrows(NotFoundException.class,
                () -> nodeB.reader().readAclById(object));
    }
}
~~~

These tests **do not** spawn two JVMs, yet use two `JdbcMutableAclService` instances with separate caches and a shared DataSource, deliberately reproducing the cause of staleness. The second test observes an allow **before eviction** and a deny **after eviction**. The third test proves an ACL already deleted from the DB can remain present in another node's cache.

Run:

~~~text
./gradlew test --tests demo.aclcache.AclCacheIntegrationTest
~~~

Windows:

~~~text
gradlew.bat test --tests demo.aclcache.AclCacheIntegrationTest
~~~

The sample code contains no `System.out.println`; there is no fixed business stdout. Success means Gradle finishes with all assertions passing. When using a different JDBC dialect or updated Security version, re-run on the real stack before deploying.

## 8. How Does Invalidation Propagate to Every Instance?

A production design typically follows this flow:

~~~text
       Shared ACL Database
               ▲
         +-----+------+
         |            |
       Node A       Node B
       cache A      cache B
         |            |
         +-----+------+
               |
          Event broker
       (stream/pubsub/outbox)
~~~

A revoke flow proceeds as follows:

1. Node A checks that the actor may edit the ACL **for that exact object and tenant**.
2. Node A updates the ACL in a DB transaction, calling `MutableAclService.updateAcl(...)`.
3. The transaction commits cleanly.
4. Node A publishes an `ACL_CHANGED` event with ObjectIdentity and revision.
5. Node B receives the event and evicts the corresponding ACL (plus inheriting children if needed).
6. Subsequent requests on B cache-miss and load the fresh ACL from the source of truth.

Steps 4–5 **are not built into** `JdbcMutableAclService`. You must add the broker/consumer, retries, recovery, and lag monitoring.

### 8.1. Event Structure

~~~java
// Illustrative record; not a complete listener/broker.
public record AclChanged(
        String objectType,
        long objectId,
        String tenantId,
        long revision,
        String changeId) {
}
~~~

Events should carry the **ACL identifier**, never broadcasting full ACE contents, tokens, or sensitive data to every subscriber. `tenantId` must come from a trusted source; `revision` helps handle out-of-order events or fetch newer versions; `changeId` supports idempotency and tracing.

### 8.2. Why Publish After Commit?

If published before commit:

~~~text
T1: Node A updates ACL without committing yet.
T2: Node B receives event, evicts cache.
T3: Node B SELECTs data still at old version.
T4: Node B re-caches old data.
T5: Node A commits new ACL.
T6: Node B keeps holding wrong ACL.
~~~

With Spring, you can publish an application event inside the transaction and run a callback after commit:

~~~java
// ILLUSTRATION: call from a method with a real @Transactional.
applicationEventPublisher.publishEvent(
        new AclChanged(
                Document.class.getName(),
                documentId,
                trustedTenantId,
                revision,
                changeId));
~~~

~~~java
// ILLUSTRATION: externalBroker is an adapter to implement separately.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void publishAfterCommit(AclChanged event) {
    externalBroker.publish(event);
}
~~~

Imports:

~~~java
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.event.TransactionPhase;
~~~

`@TransactionalEventListener` only controls **when a callback runs inside one JVM**; it does not transmit across JVMs. If the process crashes after DB commit but before publishing, the event can be lost. For high reliability, use a **transactional outbox**: the same DB transaction writes the ACL change and an outbox row, a separate publisher retries to the broker, and consumers process idempotently.

### 8.3. Eviction Must Target the Right ObjectIdentity and Cache Instance

~~~java
// ILLUSTRATION in Node B's consumer:
ObjectIdentity object = new ObjectIdentityImpl(
        Document.class.getName(),
        event.objectId());

nodeBaclCache.evictFromCache(object);
~~~

`nodeBaclCache` here is Node B's `AclCache` bean, not Node A's serialized cache object. You do not copy ACEs into the event because the DB ACL remains the source of truth.

If the event encodes ObjectIdentity as a String while lookups use Long, convert types consistently; mismatched cache keys leave stale entries behind. In multi-tenant apps, object identities must also partition tenants consistently.

### 8.4. Parent and Child ACLs

~~~text
Folder#8 ACL: ROLE_REVIEWER -> READ:grant
  |
  +-- Document#101, entriesInheriting=true
  +-- Document#202, entriesInheriting=true
~~~

If Node B caches a child's ACL with an old parent snapshot, evicting only the folder may not be enough. The JDBC writer invalidates children in its own cache; in multi-node systems, consumers must evict the full affected subtree or perform a controlled `clearCache()`.

Two strategies exist:
- **Targeted:** look up descendant ObjectIdentities and evict each ACL; must handle deep trees, pagination, and cycle avoidance.
- **Conservative:** clear the node/tenant's entire ACL cache after major parent changes; simpler for correctness, though it can cause SQL bursts.

Never assume `AclCache.evictFromCache(parent)` automatically invalidates all children when called directly from a consumer.

## 9. Shared Redis Caches and Remaining Races

Replacing local caches with a shared backend:

~~~text
Node A -----+
            +-- SpringCacheBasedAclCache --> Shared cache --> ACL DB on miss
Node B -----+
~~~

When evicting the right key in a shared cache, both nodes see the deletion. However, you must still check: `AclImpl` serialization format, class/strategy versions, OID/PK key structure, parent inheritance, backend outages, tenant namespaces, eviction policies, and races.

**Post-evict refill race:**

~~~text
T1: B cache-misses and starts SELECTing old ACL.
T2: A commits ACL revocation.
T3: A evicts shared cache.
T4: B finishes old SELECT, puts old ACL into cache.
T5: C cache-hits old ACL and falsely ALLOWs.
~~~

A shared cache **does not automatically achieve strong consistency**. Strict enforcement may require per-ACL/tenant revisions, version checks on put, DB revision checks at decision time, or skipping caching on paths requiring instant revocation. A TTL only caps the maximum stale window under normal conditions; it does not eliminate it completely.

## 10. Comparing Multi-Node Caching Strategies

| Strategy | Benefits | Limitations |
| --- | --- | --- |
| No ACL cache | Closer to DB truth, avoids local stale ACLs | Higher SQL load; DB transactions still need care |
| Single JVM + ConcurrentMapCache | Easy to learn and configure | Unsuitable for multi-instance fast revocation |
| Local cache + pub/sub | Fast, no full-ACL serialization needed | Message drops, lag, and event ordering |
| Local cache + transactional outbox | More reliable retry/replay | Still eventual consistency with async events |
| Shared cache (Redis, etc.) | Eviction shared through backend | Serialization, alias keys, refill races, network |
| Versioned ACL cache | Detects/invalidates stale snapshots | Requires version source of truth and atomic checks |
| Short TTL + DB fallback | Caps stale duration | Does not guarantee instant revocation; higher SQL |
| Skip cache on sensitive endpoints | Reduces reliance on async invalidation | Slower; requires query tuning |

Choose based on revocation SLAs: for example, "after commit, no subsequent request may read the document" demands stronger guarantees than simple async events. Conversely, less sensitive workflows can adopt a **measured and accepted eventual-consistency window**.

## 11. Fail Closed When ACLs or Caches Cannot Be Verified

| Scenario | Interpretation | Recommended behavior |
| --- | --- | --- |
| `getFromCache(oid) == null` | Cache miss | Query DB |
| `AclService.readAclById` throws `NotFoundException` | Missing ACL | Deny |
| `Acl.isGranted` throws `NotFoundException` | No ACE produces a decision | Deny |
| `UnloadedSidException` | Required SID not loaded | Fix lookup loading; never allow |
| Cache backend timeout | Cache unavailable | Safe DB fallback or 503 error |
| DB unreadable | Cannot verify permissions | Deny/503; never trust stale grant cache |
| Broker disconnected | Missing invalidations possible | Run recovery/reconciliation, track lag |
| Event fails OID parsing | Unknown key to evict | Log/alert, retry or controlled clear |
| Stale role in auth token | ACL cache cannot fix this | Token revocation/refresh and auth lookup |

Never catch every exception and return `true` just to keep the service running. Inability to verify permissions should yield HTTP 503 (service unavailable) rather than 403 (known unauthorized); the goal is never leaking resources.

API check example:

~~~java
// ILLUSTRATION inside a service with aclService already injected.
public boolean canRead(
        ObjectIdentity object,
        Authentication authentication) {

    if (authentication == null || !authentication.isAuthenticated()) {
        return false;
    }

    List<Sid> sids =
            new SidRetrievalStrategyImpl().getSids(authentication);

    try {
        Acl acl = aclService.readAclById(object, sids);
        return acl.isGranted(
                List.of(BasePermission.READ), sids, false);
    } catch (NotFoundException noDecision) {
        return false;
    }
}
~~~

In production, distinguish anonymous tokens via `AuthenticationTrustResolver` or trusted authentication checks; this illustrative method focuses on handling ACL `NotFoundException`.

## 12. Monitoring and Post-Deploy Testing

A high cache hit rate does not prove security. Measure:

- Cache hits/misses, entry counts, evictions, clears, memory, and SQL query latency.
- Committed grant/revoke commands, revisions, and Change IDs.
- Lag from **ACL revoke commit** to **every node starting to deny**.
- Event broker backlog, retries, consumer lag, and dead-letter messages.
- Cache/DB failure counts, fallback counts, and deserialization errors.
- Rate of cached entries with revisions older than the DB.
- Number of child ACLs evicted on parent updates, plus SQL load spikes after clears.
- Stale grants caught by synthetic probes in pre-production/canary.

**Multi-node testing** must run with at least two genuinely independent caches, not a single bean wrapped in a Mockito spy. Scenarios: warm cache then revoke from another node; new grants, ACL deletion, parent inheritance changes, role changes in Authentication, dropped/delayed/out-of-order events, cache backend outages, DB timeouts, and rolling upgrades.

## 13. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Only Node A sees new permissions | Cache B was not evicted | Check events and Cache B addressing |
| Revoke committed yet Node B still allows | Stale ACL or stale role/token | Inspect both ACL cache and Authentication |
| Restarting a node fixes the issue | Stale local cache | Fix propagation; never rely on restarts |
| Still reads old ACL after `evictFromCache` | Wrong key, PK/OID alias, child/parent | Check type/ID, use `AclCache` API and subtrees |
| Direct SQL edit to `acl_entry` has no effect | Bypassed writer/invalidation | Use `MutableAclService` or clear/reconcile |
| High hit rate yet wrong permissions | Refill race, excessive TTL | Version gate, test revocation lag |
| Cache clear causes DB spike | Stampede | Batch loading, TTL jitter, concurrency limits |
| Redis fails to deserialize `AclImpl` | Incompatible serializer/class version | Versioned namespaces, flush cache on deploy |
| Only child documents are wrong | Stale parent ACL cached inside children | Evict child subtree or clear |
| User stripped of role can still read | JWT/session retains old role | Token revocation/refresh |
| Grants lost when admins edit concurrently | ACL lost update | Lock/version/serialize per ObjectIdentity |
| Events emitted yet nodes do not invalidate | Consumer error, wrong route, bad OID parse | Retries, alerts, monitor event lag |
| Cache outage allows everyone | Fail-open fallback | Deny/503 or controlled DB fallback |
| Tenant B receives Tenant A's ACL | Cache identity not tenant-scoped | Partition cache and ObjectIdentities cleanly |

## 14. Hands-On Exercises

**Exercise 1 – Two cache key types.** After warming `AclCache`, test both `getFromCache(oid)` and `getFromCache(acl.getId())`. Explain why a domain ID is not necessarily the database ACL PK.

**Exercise 2 – Revoking a grant across two nodes.** Run `AclCacheIntegrationTest`. Remove `nodeB.cache().evictFromCache(object)` in a practice copy; observe Node B retaining the grant. Add a simulated event consumer and verify staleness disappears after eviction.

**Exercise 3 – Parent/child.** Create a folder ACL with a READ grant and two inheriting child ACLs. Warm all three, update the parent, and design invalidation for the children on Node B.

**Exercise 4 – After commit.** Publish `AclChanged` inside a transaction and handle it with `@TransactionalEventListener(phase=AFTER_COMMIT)`. Test that a rollback emits nothing. Describe the post-commit crash scenario requiring an outbox.

**Exercise 5 – Shared backend.** Try Redis Spring Cache, inspect key aliases, test serialization, and simulate a stale ACL SELECT finishing after an eviction event. Propose a revision check.

**Exercise 6 – Revocation SLA.** Define a maximum acceptable delay when an admin revokes READ. Measure across multiple nodes under broker delay, node restarts, and DB/cache outages. If instant revocation is required, design a DB/revision-check path.

**Exercise 7 – Authentication.** Revoke a user's `ROLE_REVIEWER` while keeping an old JWT. Prove that evicting the ACL cache does not update the token, then add appropriate auth revocation.

**Completion criteria:** use `AclCache` properly, understand `SpringCacheBasedAclCache` and both key types, demonstrate local cache staleness after revocation, explain after-commit events and outboxes, design parent/child and multi-node invalidation, and never confuse cached ACLs with Authentication or the source of truth.

## Official References

- Spring Security – Domain Object Security (ACLs), `SpringCacheBasedAclCache` configuration: https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html
- Spring Security 6.5 – AclCache API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/AclCache.html
- Spring Security 6.5 – SpringCacheBasedAclCache API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/SpringCacheBasedAclCache.html
- Spring Security 6.5 – JdbcMutableAclService API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html
- Spring Security 6.5 – BasicLookupStrategy API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/BasicLookupStrategy.html
- Spring Framework – Transaction-bound Events, `@TransactionalEventListener`: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Security – ACL JDBC Schema: https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html

# Embedded LDAP for Testing and Its Limitations vs. Real Systems

## 1. Why Do We Need Embedded LDAP in Spring Boot Testing?

Many Spring Boot applications fetch user profiles, organizational units, or permission groups from **LDAP (Lightweight Directory Access Protocol)**. An integration flow might look up an account by employee ID, authenticate login credentials, read groups to authorize access, and then sync data to a database or cache. In real environments, LDAP is typically a shared server with access policies, multiple data partitions, TLS, service accounts, and distinct operational rules.

If every test connects directly to the corporate directory, tests become fragile due to network instability, shifting data, restricted permissions, maintenance windows, or the risk of mutating live data. **Embedded LDAP** provides an LDAP server running alongside tests or spun up per test run, loaded with a reproducible **LDIF** dataset.

Embedded LDAP verifies what the application actually sends over the LDAP protocol: DNs, search bases, scopes, filters, returning attributes, bind attempts, result mapping, and how Spring handles errors. It provides far more confidence than mocking all of **LdapTemplate** when verifying queries and data structures.

However, a green test suite on embedded LDAP **does not prove** full compatibility with Microsoft Active Directory (AD), OpenLDAP, or an organization's managed directory service. Real systems can differ in schemas, read permissions, group memberships, referrals, TLS, pagination, password policies, and multi-node behavior.

In the **SPRING_BOOT_INTEGRATION** module, this topic connects directly to integration config management, data contracts, network/auth errors, caching, transactions, testing, and observability of flows interacting with external systems.

### Expected Outcomes After This Lesson

1. Distinguish **unit tests**, **embedded LDAP integration tests**, and **real-server integration/contract tests**.
2. Build a small yet representative LDIF dataset and run a dedicated embedded LDAP server for Spring Boot tests.
3. Verify searches, binds, mapping, group lookups, and basic error scenarios.
4. Clearly identify what embedded LDAP does not simulate, and design complementary test layers accordingly.
5. Keep test configuration and test credentials strictly isolated from production.

## 2. LDAP Concepts Needed Before Creating Fixtures

LDAP organizes information into **entries**, each having a unique **Distinguished Name (DN)** in the directory tree. Entries hold attributes and **objectClass** values defining valid schema structure.

Example:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=alice
│   └── uid=bob
└── ou=groups
    └── cn=order-operators
~~~

Alice's full DN:

~~~text
uid=alice,ou=people,dc=example,dc=org
~~~

| Component | Role | Common Mistake |
| --- | --- | --- |
| **Base DN** | Search root, e.g., **dc=example,dc=org**. | Pointing to the wrong branch, finding 0 entries even though data exists. |
| **DN and RDN** | Entry path identifier; RDN such as **uid=alice**. | Concatenating DNs without escaping or assuming UID is a DN. |
| **objectClass/schema** | Defines allowed/required attributes. | Overly permissive fixtures hiding add/modify rejections in production. |
| **Bind** | Authenticates/establishes connection identity, typically via DN and password in simple bind. | Mistaking a service account finding a user for the user logging in successfully. |
| **Search filter** | Condition such as **(uid=alice)**. | Concatenating user input into filters, causing LDAP injection. |
| **Search scope** | **OBJECT**, **ONELEVEL**, **SUBTREE** per API. | Missing entries in child OUs or scanning too broadly. |
| **Attribute** | **cn**, **sn**, **mail**, **member**, etc. | Assuming attributes are always present, single-valued, or readable by everyone. |
| **Group membership** | Relationships via **member**, **uniqueMember**, **memberUid**, or server-specific attributes. | Assuming every server has **memberOf** or handles nested groups identically. |

**LDIF (LDAP Data Interchange Format)** is a text format representing entries and attributes. A good test LDIF models the entries and relationships real code depends on—not just one pristine account devoid of edge cases.

## 3. Distinguishing Testing Levels

| Test Level | Infrastructure | Best Verifies | Limitations |
| --- | --- | --- | --- |
| **Unit test** | Mock **LdapOperations**/**LdapTemplate**, fake directory gateway. | Mapping logic, error branches, permission rules, caching, retries without an LDAP server. | Does not verify filter syntax, DNs, binds, or server behavior. |
| **Embedded LDAP integration test** | Embedded LDAP server, static LDIF, usually inside the JVM/test context. | Spring wiring, real search/bind, query builders, mapping, OU/group structures, common LDAP errors. | Does not fully replicate schemas/ACLs/TLS/replication/AD-specific behavior. |
| **Server compatibility test** | Managed OpenLDAP/389 DS/AD or equivalent environment; containers where appropriate. | Real schema, auth, TLS, access policies, indexing, paging, referrals, and server query behavior. | More complex data setup, version management, and configuration. |
| **Staging/sandbox end-to-end** | Production-like environment, test accounts, and integrated systems. | Cross-cutting flows across HTTP/database/cache/broker/LDAP, real permissions, timeouts, failover, sync, and observability. | Slower, infra-dependent; unsuitable as a replacement for all fast tests. |

Testing layers complement one another. **Embedded LDAP is ideal for catching everyday LDAP integration bugs quickly and reliably**. Target-server quirks must still be verified against that target system.

## 4. Setting Up Embedded LDAP for Spring Boot Tests

A common approach in Spring Boot versions supporting embedded LDAP uses **UnboundID LDAP SDK** and `spring.ldap.embedded` properties in a test profile. Check the exact starter and property names for your project's **actual Spring Boot version**; the example below illustrates typical configuration, not full production directory simulation.

### 4.1. Library Dependencies

Maven example with core dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>

    <dependency>
        <groupId>com.unboundid</groupId>
        <artifactId>unboundid-ldapsdk</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This assumes the project uses Spring Boot dependency management. **unboundid-ldapsdk** belongs only in `test` scope if production connects to an external directory server. Never bundle an embedded LDAP server into production artifacts without an explicit reason.

### 4.2. Isolating Test Configuration from Production

Example **src/test/resources/application-test.yml**:

~~~yaml
spring:
  ldap:
    base: dc=example,dc=org
    embedded:
      base-dn: dc=example,dc=org
      ldif: classpath:ldap/test-directory.ldif
      port: 0
~~~

Here, **port: 0** requests a dynamically assigned available port when supported by your Boot version's embedded setup; this reduces port conflicts during parallel test runs. **spring.ldap.base** sets the LDAP client's search base, while **embedded.base-dn** sets the test server's naming context. Aligning both ensures relative queries like **ou=people** work as expected.

Activate the **test** profile strictly in tests. In production, the client must use real environment URLs, TLS, credentials, base DN, and timeouts. If the project defines a custom **LdapContextSource** or multiple LDAP servers, verify auto-configuration was not overridden and tests actually hit the embedded server rather than an external LDAP server.

**Never use a fixed port** unless necessary and concurrency is controlled. If running LDAP tests in parallel inside the same JVM, also check how Spring caches **ApplicationContext** and whether tests share or mutate data.

### 4.3. Crafting a Purposeful LDIF Dataset

Example **src/test/resources/ldap/test-directory.ldif**:

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Example
sn: Example
givenName: Alice
mail: alice@example.org
userPassword: alice-test-secret

dn: uid=bob,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: bob
cn: Bob Example
sn: Example
givenName: Bob
userPassword: bob-test-secret

dn: cn=order-operators,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: order-operators
member: uid=alice,ou=people,dc=example,dc=org
~~~

The fixture provides an account with an email (**alice**), an account missing an optional attribute (**bob**), and a group containing Alice. This tests mapping missing fields, password authentication, group membership lookup, and verifying a user does not belong to a group by default.

**LDIF passwords are fake data strictly for tests.** Real servers may store hashed passwords, enforce security policies, or use special attributes; this simplification is intentional. Never reuse real passwords, privileged DNs, or exported production user data.

LDIF files must obey standard encoding/line-folding rules for Unicode or special characters. For realistic entries, use minimal synthetic or generated data; never commit production PII into test repositories.

## 5. Writing Integration Tests That Actually Call LDAP

Example using Spring Boot's test context, **LdapTemplate**, and AssertJ. Both `application-test.yml` and the fixture above must load cleanly.

~~~java
import java.util.List;
import javax.naming.directory.Attributes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

@SpringBootTest
@ActiveProfiles("test")
class DirectoryLdapIntegrationTest {

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void findsUserByUidAndMapsCommonName() {
        List<String> names = ldapTemplate.search(
                query().base("ou=people").where("uid").is("alice"),
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get());

        assertThat(names).containsExactly("Alice Example");
    }

    @Test
    void authenticatesKnownUserAndRejectsWrongPassword() {
        var alice = query().base("ou=people")
                .where("uid").is("alice");

        assertThat(ldapTemplate.authenticate(
                alice, "alice-test-secret")).isTrue();
        assertThat(ldapTemplate.authenticate(
                alice, "wrong-password")).isFalse();
    }

    @Test
    void findsGroupByMemberDn() {
        String aliceDn =
                "uid=alice,ou=people,dc=example,dc=org";

        List<String> groups = ldapTemplate.search(
                query().base("ou=groups")
                        .where("member").is(aliceDn),
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get());

        assertThat(groups).containsExactly("order-operators");
    }

    @Test
    void unknownUserReturnsNoEntry() {
        List<String> names = ldapTemplate.search(
                query().base("ou=people").where("uid").is("nobody"),
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get());

        assertThat(names).isEmpty();
    }
}
~~~

The goal is verifying **queries actually executed by an LDAP server**, not just mocked Java method returns. Note:

- The search uses a **relative base** because `spring.ldap.base` is configured. If `ContextSource` has no base, pass the full DN or configure the base accordingly.
- **AttributesMapper** receives attributes that may be absent; the test reads **cn** from fixtures that define **cn**. Production code must handle optional and multi-valued attributes.
- The **authenticate** example exercises simple bind in the test setup. It does not replace testing production login with TLS, locked accounts, MFA, SASL/Kerberos, or password policies.
- Never run tests that mutate or delete entries directly against **the same shared embedded instance** without resetting the fixture; outcomes would depend on execution order.

### Testing Missing Fields and Multi-Valued Attributes

For Bob lacking **mail**, the mapper should express **no value** rather than throwing **NullPointerException**:

~~~java
List<String> mails = ldapTemplate.search(
        query().base("ou=people").where("uid").is("bob"),
        (AttributesMapper<String>) attrs -> {
            var mail = attrs.get("mail");
            return mail == null ? null : (String) mail.get();
        });
~~~

This merely illustrates checking **null**; production business code should use a DTO/Optional or an explicit representation. Because mapping APIs can return null elements, design assertions and collection handling transparently. For multi-valued attributes like **member**, never call **get()** once assuming it represents the full list; iterate through all attribute values.

## 6. Protecting LDAP Queries Against Untrusted Input

When an HTTP API accepts a **uid** parameter, manual string concatenation creates **LDAP filter injection** risks:

~~~java
// Never build filters by concatenating external input:
String filter = "(uid=" + userInput + ")";
~~~

Characters like **\***, **(**, **)**, backslashes, and NUL bytes have special meaning in LDAP filter syntax. Arbitrary input can break filters or expand the result set. Use a filter-building API that escapes values:

~~~java
var ldapQuery = query()
        .base("ou=people")
        .where("uid").is(userInput);

var users = ldapTemplate.search(
        ldapQuery,
        (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get());
~~~

**Filter escaping** and **DN escaping** are two separate concerns. If building a DN from user input, use a DN builder API like **LdapNameBuilder**, never concatenating **"uid=" + input + ",ou=people,..."**. Alongside escaping, enforce data contract validation: UID length bounds, character allowlists when applicable, fixed base/scope, and max result counts.

Test special strings and long inputs to confirm queries never return unintended users. An embedded server catches protocol-level filter issues but **does not replace** verifying production schemas and ACL policies.

## 7. Limitations of Embedded LDAP Compared to Production Directories

### 7.1. Schemas and Vendor-Specific Attributes

In the fixture above, **inetOrgPerson** and **groupOfNames** cover basic needs. Real systems may enforce custom objectClasses, required attributes, custom matching rules, DN syntaxes, and normalization mechanisms.

In particular, **Active Directory** has vendor-specific attributes and conventions like **sAMAccountName**, **userPrincipalName**, **objectGUID**, **userAccountControl**, and distinct representations for groups, locked accounts, and expired accounts. Computed or virtual attributes like **memberOf** do not behave identically by default on embedded LDAP.

A green test with **(uid=alice)** only proves the fixture has `uid`; it does not prove production lets you search users by `uid` or that every domain shares the same naming attribute. Group/role mappings must match the target server's schema and contract.

### 7.2. Authentication and Password Policies

Embedded LDAP can check valid/wrong bind passwords in a fixture. It usually does not faithfully emulate:

- Account lockouts after failed attempts, expired passwords, or disabled accounts.
- Password change rules, history, minimum length, or complexity.
- AD/Kerberos/SASL mechanisms, binds over TLS, or policies blocking unencrypted simple binds.
- Domain synchronization, replication states, and failures when a domain controller goes offline.

**Never use empty passwords to assert successful authentication**: depending on server and bind mechanism, anonymous or unauthenticated binds carry different semantics from user logins. Services must validate non-null/non-empty usernames and passwords before invoking LDAP.

### 7.3. Authorization, ACLs, and Data Permissions

An embedded LDAP server usually runs with minimal permission checks; many operations succeed by default in tests. Production directories separate service bind accounts, admin accounts, end users, and read/write rights by OU/attribute.

A test search returning **mail** does not prove the production service account is allowed to read it. Likewise, a successful modify on an embedded server does not prove the service account can edit attributes or move entries in production.

Tests against a production-equivalent server must use a **least-privileged account** and verify **insufficientAccessRights** cases, rather than running all tests as an admin and masking config errors.

### 7.4. TLS, Certificates, and Network Behavior

Embedded LDAP on **localhost** often runs unencrypted for test speed. Real environments require testing **LDAPS/StartTLS**, certificate chains, hostname verification, truststores, TLS protocols, and timeouts.

Additional tests needed include: expired certificates, untrusted CAs, mismatched hostnames, servers rejecting the chosen TLS mode, connections dropped mid-search/bind, and failover when only one endpoint in a list remains healthy.

Never disable certificate checks or install a trust-all manager in production code just to match embedded tests. A passing test over **ldap://localhost** says nothing about production transport security.

### 7.5. Search Behavior, Paging, and Referrals

Production servers may cap returned entries, search duration, filter types, indexing, and throughput. Large directories require **paged results** or server-supported pagination, along with proper cookie/continuation handling.

**Referrals** can direct clients to another naming context or server. A small single-tree embedded server does not represent multi-domain/forest setups, referral chains, or cross-referral authentication issues.

Testing with a handful of users will not expose unindexed queries or code assuming **a single search always returns everything**. Test volume, search caps, and paginated queries against the target server or a production-like container.

### 7.6. HA, Replication, and Eventual Consistency

Production may involve multiple LDAP servers/domain controllers, asynchronous replication, DNS/load balancers, and connection pooling. A write on node A might not appear immediately when reading node B.

A single-node embedded LDAP server does not model replication lag, split-brain, read-after-write divergence across nodes, connection failover, or pool exhaustion. Client design needs timeouts, bounded retries, and business-appropriate handling of **stale data**.

### Summary Comparison Table

| Capability | Embedded LDAP | Real Server or Production-Like Environment |
| --- | --- | --- |
| Load LDIF, query DN/filters, basic binds | Well suited for testing | Yes, governed by real schema/ACLs |
| Custom schemas/attributes | Partially configurable per implementation | Source of truth for the contract |
| ACLs, service accounts, account lockouts | Typically simplified | Must be tested directly |
| AD-specific attributes and nested groups | Do not assume full fidelity | Must test on AD when app depends on AD |
| TLS/certificates/StartTLS | Partially testable, not fully representative | Must verify the entire connection path |
| Paging, referrals, size/time limits | Basic testing possible, differs from prod | Must verify against target server |
| Performance, indexes, millions of entries | Fixtures are usually tiny | Requires real load/performance testing |
| Replication/failover/HA | Usually single instance | Must test multi-node operations |

## 8. Designing Valuable Fixtures: Testing Failure Cases Too

Having only one well-formed **alice** account produces easy green tests that catch few bugs. Build test data covering real contract edge cases:

| Fixture Scenario | Verification Question |
| --- | --- |
| Valid user in expected OU | Do search and mapping return the single expected entry? |
| Non-existent user | Does code express "not found" cleanly without mistaking it for a connection error? |
| Wrong/empty password or non-bindable account | Fails authentication cleanly without logging passwords? |
| Missing optional attributes | Do mapper/DTO handle nulls and fallbacks properly? |
| Multi-valued attributes or multi-member groups | Are all values read and permissions checked accurately? |
| UID with special characters, long input | Do filters/DNs escape, validate, and bound scope properly? |
| Two entries sharing a non-unique attribute value | Does code handle multiple search hits rather than picking arbitrarily? |
| User in a child OU | Are SUBTREE scope and base DN right? |
| Nested groups or mixed group schemas | Does the contract truly support them, or merely assume **memberOf**? |
| Timed-out search or unavailable LDAP | Does the service separate retryable errors from not-found/invalid-credentials? |

**Do not force an embedded server to fake faults it cannot faithfully model.** For network timeouts, TLS, referrals, and AD lockouts, use fault-injecting fakes at the right layer and add tests against a representative server/container. Above all, document the exact boundaries of each test suite.

### Isolating Data and Avoiding Test Coupling

- Prefer **read-only tests** against a fixed fixture. If tests add/modify/delete entries, restore data afterward or isolate each test in its own LDAP instance/context.
- Use **dynamic ports** or dedicated port allocation during parallel CI builds.
- Never use real user data or real credentials. Test accounts/passwords must be synthetic samples strictly inside test resources.
- Ensure tests shut down servers/sockets and Spring contexts cleanly. Watch out for stale cached state shared across tests in the same context.
- Never expect **@Transactional** in database tests to roll back LDAP mutations. LDAP directories sit outside standard JDBC/JPA transactions.

## 9. Integrating LDAP with Databases, Caches, HTTP, and Sync Flows

In real applications, LDAP is usually one of several data sources. For instance, an HTTP API receives **employeeId**, queries LDAP for name/groups, caches the result to offload the directory, and persists a snapshot in a database for fast querying.

~~~mermaid
flowchart LR
    A[HTTP API / scheduled sync] --> B[Spring Boot service]
    B --> C{Cache still valid?}
    C -->|Yes| D[Return cached data]
    C -->|No| E[LDAP adapter]
    E --> F[(Directory server)]
    E --> G[(Cache / database snapshot)]
    G --> D
~~~

Failures to anticipate:

**LDAP unavailable:** Never return **"user not found"** when the directory is actually unreachable. Separate "no entry" from network failures, timeouts, wrong bind credentials, and missing read rights. Retries need timeouts/backoff/jitter and limits; never blindly retry authentication or malformed-data errors.

**Stale cache:** Group memberships or account disablements can happen after caching. Tune TTL/invalidation to sensitivity; for critical authorization decisions, never treat expired snapshots as authoritative truth.

**No shared transaction between directory and database:** If a database snapshot write commits while an LDAP update fails (or vice versa), **@Transactional** on JPA/JDBC does not roll back LDAP. Establish explicit operation order, safe idempotent retries, and business-key reconciliation. Many systems treat LDAP as a read-only authority synced eventually into the database.

**Contract drift:** A renamed attribute, revoked read permission, or change to multi-valued fields can break the adapter in production even though embedded fixtures remain green. Version mappings/filters and run contract checks against the target directory whenever integrations change.

**Wrong identity key:** A DN can change when a user moves OUs or has their RDN renamed. Using DN as a durable database primary key causes duplicate records after entry moves. Pick a stable key suited to the target system—such as a directory-supplied immutable identifier—and explicitly test rename/move behavior.

## 10. Error Testing, Observability, and Data Protection

### Error Classification in the Adapter

| Error Category | Example | Handling |
| --- | --- | --- |
| **Entry not found** | Valid search returns 0 results. | Return not-found status per contract; do not retry repeatedly. |
| **Invalid credentials** | Simple bind with wrong password. | Reject login; avoid revealing user existence; never retry same password infinitely. |
| **Access denied** | Service account cannot read attribute/OU. | Raise operational/permission error; never fabricate an empty result set. |
| **Server unavailable/timeout** | DNS, TLS, network, busy server. | Bounded retries, circuit breaker if appropriate, pre-designed fallback. |
| **Invalid DN/filter/schema** | Malformed DN, objectClass violation. | Fix mapping/config/input; retries generally will not help. |
| **Too many results/partial results** | Size limit, time limit, referrals, or unhandled paging. | Paginate and tighten search base/filter; never treat data as complete. |

Common LDAP result codes include **32 (noSuchObject)**, **49 (invalidCredentials)**, **50 (insufficientAccessRights)**, and **52 (unavailable)**. Spring LDAP maps them to specific exceptions; base tests on the adapter's error contract rather than coupling all business logic to raw server error messages.

### What to Observe

- **Search/bind durations**, timeout rates, not-found counts, and authentication errors.
- Redacted **search base/filter templates**, returned entry counts, and result-limit warnings.
- Chosen **server endpoint**, active connection counts, failover events, and TLS errors.
- **Cache hit/miss**, cache entry age, and LDAP → database sync lag.
- **Correlation ID/traceId**, operation names, retry errors, and rate limits.

Never put **passwords, bind secrets, access tokens**, or snapshots of full sensitive attributes into logs/traces. DNs can also contain personal information; follow data-protection policies and minimize detail when logging.

## 11. Decision Checklist for Where to Run Each Test

1. **Unit tests:** verify mapping logic, fallbacks, and retries; use mocks/fakes to inject errors.
2. **Embedded LDAP:** verify Spring LDAP wiring, LDIF loading, search/filters, DNs, binds, basic groups, and missing/multi-valued mapping.
3. **Containers or equivalent LDAP servers:** verify real schemas/ACLs, TLS, search limits, paging, referrals, and larger datasets.
4. **AD/staging sandbox (if using AD):** verify `userPrincipalName`/`sAMAccountName`, nested groups, account state, password policies, and service account rights.
5. **End-to-end:** verify LDAP integrated with HTTP/database/cache/brokers, retries, eventual sync lag, and business outcomes.
6. **CI:** run embedded tests on every build; run contract/staging tests on schedule or on schema/config changes; isolate test data and accounts.

An important CI check is verifying **tests truly hit the embedded endpoint** rather than silently connecting to an external LDAP due to environment variables or overriding profiles. Never let a test suite depend unknowingly on a production directory.

## 12. Common Misconceptions

**"Embedded LDAP tests are green, so AD integration will work."** False. LDAP is the shared protocol, while AD differs in schemas, auth, groups, and policies.

**"Binding with the service account proves the user's password is right."** False. Service binds authenticate only the service account; user authentication requires its own bind/verification flow.

**"Having `memberOf` in my fixture means every directory supports it identically."** False. Computed attributes or server plugins vary; some directories store only **member** on groups.

**"`@Transactional` will undo LDAP changes if the database rolls back."** False. Database transactions do not cover LDAP operations.

**"With an LDAP cache, user permissions are always up to date."** False. Caches have TTLs and can retain stale permissions after group membership changes.

**"Localhost tests mean we don't need to worry about security."** Simplified setups are fine in isolated tests, yet production code still needs input validation/escaping, least privilege, secret protection, and certificate validation.

**"One test finding Alice is enough."** That single test misses missing attributes, multi-match queries, complex groups, denied rights, and unavailable servers.

## 13. Key Takeaways

**Embedded LDAP is a fast, data-controlled, reproducible integration testing tool**, well suited for verifying Spring wiring, search filters, DNs, binds, and mapping. Test quality depends on whether LDIF fixtures faithfully represent the data contract, how state is isolated, and how negative tests are designed.

When targeting a real enterprise directory, additionally verify **schemas, ACLs, authentication modes, TLS, paging, referrals, performance, replication, and failover**. For Spring Boot flows also involving HTTP, databases, caches, and brokers, verify transaction boundaries, external-system failures, and data freshness. A trustworthy test suite combines **unit tests + embedded LDAP + target-server verification**, explicitly documenting the scope and limits of each layer.

# Testing Access Control, Authentication, and Sensitive Data Protection in MongoDB

A system using MongoDB can pass an entire CRUD test suite and still have critical security flaws. For example, an API may return the right order when a user logs in, yet also return another **tenant's** order when the ID is swapped; a read-only database user might still be able to drop a collection; or card/account details and connection strings containing passwords might accidentally appear in logs when an integration test fails.

This lesson, **"Testing Access Control, Authentication, and Sensitive Data Protection,"** belongs to the **Testing** chapter of the **Database Engine Document MongoDB** module. Its goal is to build a repeatable security testing system across all layers — **network -> TLS -> authentication -> MongoDB RBAC -> application authorization -> data minimization -> audit/retention** — rather than merely checking "can we connect to the database?"

After this lesson, you will be able to:

1. Distinguish between **authentication (AuthN)** testing and **authorization (AuthZ)** testing.
2. Design a **permission matrix** for database users, collection actions, and application users.
3. Test scenarios for **valid credentials, invalid credentials, wrong authSource, missing roles, and missing tenant scope**.
4. Write integration tests with the MongoDB Java Sync Driver and Spring Data MongoDB using **real identities with different privileges**.
5. Verify TLS/network policies, IP Access Lists, or private connectivity without exposing the database to the Internet.
6. Detect PII/secret leaks across API responses, projections, logs, errors, backups, and test artifacts.
7. Define the boundaries of encryption in transit, encryption at rest, and client-side field-level encryption.
8. Integrate critical security tests into CI/CD with cleanup, evidence, negative assertions, and release gate criteria.

> **Safety boundary:** all addresses, users, databases, and data in the examples are hypothetical for lab purposes. Only run tests on systems where you have been granted administrative authorization, using isolated test databases and dedicated credentials. Do not run mass invalid-login attempts, do not scan the Internet, do not run `dropDatabase()` on real data, and do not put production PII into documentation or CI.

## 1. Map of Defense Layers

An order read request can pass through multiple gates:

```text
User / client
       |
       v
HTTPS API + user session/token
       |
       v
Application authorization
  - roles
  - tenantId/ownerId
  - business state
       |
       v
Backend service identity
       |
       v
DNS + network route + firewall / Atlas IP Access List
       |
       v
TLS handshake + server certificate validation
       |
       v
MongoDB authentication (SCRAM/x.509/... if supported)
       |
       v
MongoDB roles / privileges (RBAC)
       |
       v
MongoDB collection / document
       |
       v
Output projection + masking + logging/retention
```

No single test proves every layer is secure:

- A successful `ping` **does not prove** the database user has a read-only role.
- A DB user with `readWrite` on `ordersdb` **does not prove** HTTP user A can only view user A's orders.
- TLS being enabled **does not prove** passwords never appear in logs.
- An API returning only the allowed fields **does not prove** backups/snapshots are encrypted, properly authorized, and subject to retention policies.
- A narrow Atlas IP Access List **does not replace** database authentication or application authorization.

### Four Independent Questions

| Layer | Test Question | Example |
| --- | --- | --- |
| Network | Which sources can reach the database port? | App subnet allowed, unknown Internet blocked |
| AuthN | Does the client have the valid identity? | Valid SCRAM username/password |
| Database AuthZ | What is the database identity allowed to do? | `read` allowed, but not `insert`/`drop` |
| Application AuthZ | Which business data can the user view or modify? | Tenant A user cannot read Tenant B orders |

Different layers require **different test cases and evidence**. Do not collapse them into a single "login passed" conclusion.

## 2. Defining Security Requirements Before Writing Tests

Testing should be based on the **intended policy**, not merely a snapshot of current behavior.

Example requirements:

```text
REQ-AUTH-01   Client with wrong password cannot access data
REQ-AUTH-02   Read-only service cannot insert/update/delete
REQ-AUTH-03   Orders service has no permission to read payroll database
REQ-TENANT-01 Tenant A cannot view Tenant B's order
REQ-TENANT-02 Tenant A cannot modify Tenant B's order
REQ-DATA-01   Customer API response does not contain internalNotes
REQ-DATA-02   Secrets/tokens do not appear in error logs
REQ-TLS-01    Production connections only use valid TLS
REQ-BACKUP-01 Backups have restricted access and retention controls
REQ-AUDIT-01  Sensitive operations have audit correlation
```

Each requirement should define:

1. **Protected target**: database, collection, document, field, secret.
2. **Actor/identity**: anonymous, HTTP user, MongoDB service user, operator.
3. **Action**: connect, find, insert, update, delete, createIndex, export.
4. **Expected outcome**: allow/deny/masked/audited.
5. **Verification point**: network, API, DB command, log, backup platform.
6. **Evidence**: result/exception/error code/sanitized event, containing no sensitive data.

### How Do Security Tests Differ from Functional Tests?

Functional tests typically ask "can an authorized actor perform the task?" Security tests must also ask "is an **unauthorized actor** properly blocked?"

For example:

```text
Functional:
  reader can read order -> PASS

Security:
  reader can read order -> PASS
  reader insert order -> DENIED -> PASS
  reader drop collection -> DENIED -> PASS
  reader read payroll -> DENIED -> PASS
```

A test suite containing only positive cases is not enough to prove least privilege.

## 3. Threat Model for Sensitive Data

In a rental/e-commerce ordering application, data categories may include:

| Data Category | Hypothetical Examples | Impact if Exposed |
| --- | --- | --- |
| PII | Full name, email, phone number, address | Privacy violation |
| Financial data | Payment accounts, transactions | Fraud, financial loss |
| Authentication data | Access token, reset token, session secret | Account takeover |
| Location data | Address, stay history | Personal safety risk |
| Internal data | Negotiated pricing, internal notes | Commercial secret exposure |
| Operational secrets | MongoDB URI/password, TLS key | Database takeover |
| Audit metadata | User ID, IP, action | Can be PII or investigative data |

A threat model should consider these actors:

- A regular user attempting to access another user's resources.
- A service whose credentials are leaked and that holds overly broad roles.
- An operator or CI runner accidentally exporting real data.
- A network connection being eavesdropped on or misrouted.
- A log aggregator, backup store, or dashboard viewed by out-of-scope personnel.
- A background job using a raw MongoDB driver and bypassing application-level tenant filtering.

**Do not use real PII for testing when synthetic data is sufficient to reproduce the issue.** For production-like data, masking/tokenization and formal approval are required.

## 4. Preparing an Isolated Test Environment

A lab environment:

```text
Test runner (JUnit / CI)
      |
      v
MongoDB test deployment
  database: security_lab
  collections:
    orders
    customers
    audit_events
      |
      +--> User svc_orders_read
      +--> User svc_orders_write
      +--> User svc_customer_read
      +--> User admin_bootstrap  (fixture setup only)
```

Requirements:

1. A **dedicated** database/cluster for testing that can be deleted afterward.
2. **Separate** credentials for reader, writer, and test admin.
3. Synthetic seed data with test-specific business keys.
4. Network access restricted to the test runner/CI via a supported mechanism.
5. TLS and auth **enabled** in test suites verifying security properties.
6. Cleanup mechanisms and retention limits for fixtures, logs, and artifacts.
7. Never use production administrative accounts to run negative tests.

### Why Is Embedded/In-Memory MongoDB Not Enough?

Mock repositories or fake in-memory databases may work well for application logic, but they **cannot verify**:

- Real SCRAM handshakes.
- Real MongoDB authSource, users, and roles.
- Authorization denials enforced by the MongoDB server.
- TLS certificate validation and network paths.
- Real indexes and validators.
- Real audit, backup, and IP access lists.

Security requirements involving the **MongoDB server** need integration tests against a real MongoDB deployment, even if that deployment runs inside a test container. Controller/service-layer authorization can still be supplemented with unit tests for fast execution.

## 5. Safe Fixture Data

Example with two tenants and two orders:

```javascript
use security_lab

db.orders.insertMany([
  {
    _id: "order-a-001",
    tenantId: "tenant-a",
    ownerId: "user-a",
    total: NumberDecimal("120000.00"),
    currency: "VND",
    status: "NEW",
    internalNotes: "fixture only",
    contactEmail: "fake-a@example.invalid"
  },
  {
    _id: "order-b-001",
    tenantId: "tenant-b",
    ownerId: "user-b",
    total: NumberDecimal("99000.00"),
    currency: "VND",
    status: "PAID",
    internalNotes: "fixture only",
    contactEmail: "fake-b@example.invalid"
  }
]);
```

`example.invalid` is a reserved example domain; these values do not point to real users.

Test data must include **at least one document the actor is authorized to access** and **at least one document the actor is not authorized to access**. If fixtures only contain Tenant A orders, a query omitting the `tenantId` predicate will still return the expected result and cause a **false pass**.

### Tagging Test Runs for Easy Lookup and Cleanup

For example:

```text
testRunId: "security-it-20261114-001"
```

A test runner can attach `testRunId` to documents to delete only data belonging to that test run. However, for read/write privilege tests, cleanup should be performed by the **fixture admin identity** after the test, rather than granting collection-deletion privileges to a read-only user.

## 6. MongoDB Permission Matrix to Test

A sample policy:

| Database Identity | `find` orders | `insert/update` orders | `find` customers | `drop` collection | User Management |
| --- | --- | --- | --- | --- | --- |
| `svc_orders_read` | Allow | Deny | Deny | Deny | Deny |
| `svc_orders_write` | Allow | Allow | Deny | Deny | Deny |
| `svc_customer_read` | Deny | Deny | Allow | Deny | Deny |
| `fixture_admin` | Per fixture rights | Per fixture rights | Per fixture rights | Optional | Bootstrap only |

This table assumes **collection-scoped custom roles**. Granting the built-in `readWrite` role on the `security_lab` database typically grants broad privileges across multiple collections in that database, which **does not match an "orders-only" matrix**. Therefore, when collection-scoped privileges are needed, you must configure a custom role or split databases accordingly.

### Least Privilege Is a Testable Requirement

Tests should assert both:

- **Required permissions**: legitimate functionality is not blocked.
- **Forbidden permissions**: out-of-scope operations are not permitted.

If a test fails because a service was granted overly broad privileges, do not fix the test by changing the expectation to Allow. Cross-check the security requirement and tighten the role instead.

## 7. Built-in Roles and Custom Roles

MongoDB provides built-in roles such as `read`, `readWrite`, and administrative roles scoped at the database or cluster level as appropriate.

Lab example:

```javascript
use security_lab

// Illustrates a built-in role on a test database only.
db.createUser({
  user: "svc_read_db",
  pwd: passwordPrompt(),
  roles: [
    { role: "read", db: "security_lab" }
  ]
});
```

This user is a database-wide reader according to its role scope; it is **not** restricted solely to `orders` if other collections exist in the database.

### Creating a Collection-Scoped Custom Role

Example of a role that **only finds documents in orders**:

```javascript
use security_lab

db.createRole({
  role: "ordersReader",
  privileges: [
    {
      resource: {
        db: "security_lab",
        collection: "orders"
      },
      actions: ["find"]
    }
  ],
  roles: []
});
```

Assigning the role to a lab user:

```javascript
db.createUser({
  user: "svc_orders_read",
  pwd: passwordPrompt(),
  roles: [
    { role: "ordersReader", db: "security_lab" }
  ]
});
```

These administrative commands must be executed using a **sufficiently privileged bootstrap/admin identity**, strictly within an authorized test environment. Using `passwordPrompt()` in `mongosh` prompts for the password instead of hard-coding plaintext in scripts.

A user with a find-only role may be denied when invoking other commands such as listing collection metadata if the role lacks the required actions. That alone does not mean the role is broken; choose test APIs appropriate for the defined privileges.

## 8. Creating a Least-Privilege Writer Custom Role

Suppose a service should be allowed to read/insert/update/remove **only in the orders collection**:

```javascript
use security_lab

db.createRole({
  role: "ordersDataWriter",
  privileges: [
    {
      resource: {
        db: "security_lab",
        collection: "orders"
      },
      actions: ["find", "insert", "update", "remove"]
    }
  ],
  roles: []
});

db.createUser({
  user: "svc_orders_write",
  pwd: passwordPrompt(),
  roles: [
    { role: "ordersDataWriter", db: "security_lab" }
  ]
});
```

This role deliberately **omits** `dropCollection`, `createIndex`, `collMod`, and `createUser`. A data-writer service should not hold administrative privileges merely because the application needs to modify data.

### What If Real Operations Need More Actions Than the Example?

Some operations may require additional privileges depending on MongoDB version and command (e.g., metadata or index handling). Do not immediately grant full permissions when an operation errors out; instead:

1. Record the exact command that actually needs to run.
2. Look up the corresponding MongoDB privilege action.
3. Add the exact action/resource at the narrowest scope.
4. Rewrite both positive and negative tests.
5. Review the impact of the newly added privilege.

This turns the permission matrix into a **verifiable contract**, not a decorative reference table.

## 9. Authentication with SCRAM and authSource

MongoDB supports username/password mechanisms such as SCRAM. For a user created in `security_lab`, the application must authenticate against the corresponding **authentication database**.

Example URI using placeholders:

```text
mongodb://svc_orders_read:<password>@db.internal.example:27017/security_lab?authSource=security_lab&tls=true
```

This is a syntax illustration, **not a connectable URI**. In real deployments, passwords must come from an appropriate secret manager or environment injection, and special characters in URI credentials must be properly percent-encoded.

### Authentication Database vs. Target Database

`authSource` specifies the database where MongoDB looks up the **user identity for authentication**; the `/security_lab` path in the URI also relates to the connection's default database.

For example, a user created in `admin` working against `ordersdb` may require:

```text
mongodb://<user>:<password>@host:27017/ordersdb?authSource=admin
```

A wrong `authSource` can cause authentication failures even when the username and password look right.

### Positive/Negative Tests

| Case | Credentials/Source | Expectation |
| --- | --- | --- |
| AUTH-01 | Valid user/password/authSource | Appropriate authenticated command succeeds |
| AUTH-02 | Wrong password | Cannot access data |
| AUTH-03 | Non-existent user | Authentication fails |
| AUTH-04 | Valid password with wrong authSource | Authentication fails if user does not exist in that source |
| AUTH-05 | Rotated credential | Old credential rejected, new credential works |
| AUTH-06 | Credentials omitted when server requires auth | Cannot access protected data |

Do not design a test that merely checks `MongoClients.create()` throws no exception: the Java driver may **connect and authenticate upon executing the first command**, rather than when constructing the client object.

## 10. Avoiding Brute-Force Password Testing

Negative authentication tests only need a small set of **intentionally invalid fixture credentials** against an authorized deployment, not thousands of guessed passwords.

Guidelines:

- Never run credential stuffing against Atlas or real accounts.
- Never write invalid passwords into logs or test reports.
- Run tests against dedicated identities that can be reset immediately.
- Configure bounded timeouts and retries so tests do not trigger a connection storm.
- Monitor authentication-failure metrics if supported by the platform.
- Keep security tests separate from load tests; avoid accidentally triggering alerts or locking out legitimate access.

**The expected outcome of a negative test is a blocked request**, not an error-free tool run. When an exception is expected, the test must assert the specific exception type/result rather than treating the stack trace as a test failure.

## 11. Testing Authorization Independently from Authentication

Suppose `svc_orders_read` authenticates successfully. It must not be allowed to write.

```text
Authentication:
  svc_orders_read -> OK

Authorization:
  find security_lab.orders   -> ALLOW
  insert security_lab.orders -> DENY
  drop security_lab.orders   -> DENY
```

If a test only verifies that `ping` or `find` succeeds, it will miss cases where a user was mistakenly granted `readWrite` or administrative privileges.

### Signals That the Server Denied Authorization

MongoDB returns an `Unauthorized`-type error when a command/action is disallowed by the user's roles. In the Java Sync Driver, command failures may surface as `MongoCommandException`, though exact exception types can vary by operation, server, and driver version.

A negative test should:

1. Use a clearly identified database user.
2. Invoke the **actual forbidden command**.
3. Assert that the operation **failed due to authorization** (not merely a network timeout).
4. Assert that the data **did not change**.
5. Clean up using a sufficiently privileged identity when needed.

A `TimeoutException` must never be treated as proof that a database role is properly configured.

## 12. Test Matrix by Operation and Scope

Sample test cases:

| Test ID | Identity | Operation | Resource | Expectation |
| --- | --- | --- | --- | --- |
| RBAC-01 | `svc_orders_read` | `find` | `security_lab.orders` | Allow |
| RBAC-02 | `svc_orders_read` | `insert` | `security_lab.orders` | Deny |
| RBAC-03 | `svc_orders_read` | `update` | `security_lab.orders` | Deny |
| RBAC-04 | `svc_orders_read` | `delete` | `security_lab.orders` | Deny |
| RBAC-05 | `svc_orders_read` | `find` | `security_lab.customers` | Deny |
| RBAC-06 | `svc_orders_write` | `insert` | `security_lab.orders` | Allow |
| RBAC-07 | `svc_orders_write` | `drop` | `security_lab.orders` | Deny |
| RBAC-08 | `svc_orders_write` | `find` | `payroll.salaries` | Deny |
| RBAC-09 | `svc_customer_read` | `find` | `security_lab.customers` | Allow |
| RBAC-10 | `svc_customer_read` | `find` | `security_lab.orders` | Deny |

To test collection-level permissions as in the table, you must provision the corresponding **custom roles**; built-in `read` across the whole database would allow reading `customers`, changing the expectation.

### Testing Destructive Operations Without Corrupting Data

A test attempting `drop()` with a restricted user is safe **only if the role is actually denied**; if misconfigured, it can wipe the fixture collection. Always use a disposable database with automated setup/cleanup and an admin identity able to restore fixtures. Never run destructive negative tests against production.

## 13. Java Sync Driver: Integration Test Harness

Simple example:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class MongoTestConnection {

    public static MongoClient connectFromEnv(String envName) {
        String uri = System.getenv(envName);
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "Missing test environment variable: " + envName);
        }
        return MongoClients.create(uri);
    }

    public static MongoCollection<Document> orders(
            MongoClient client) {
        return client.getDatabase("security_lab")
            .getCollection("orders");
    }
}
```

The test runner reads environment variables supplied by the CI secret manager:

```text
MONGO_TEST_READER_URI
MONGO_TEST_WRITER_URI
MONGO_TEST_WRONG_AUTH_URI
MONGO_TEST_FIXTURE_ADMIN_URI
```

Specifically:

- Reader/writer users hold roles matching the policy.
- URIs use hostnames and TLS settings matching the target environment.
- The wrong-auth URI uses a **dummy credential** reserved for testing.
- The fixture admin URI must never be printed to the console or attached to test artifacts.

Do not use **a single admin URI** for every test and simulate permission checks using a mock flag in Java. Such a test does not verify MongoDB RBAC.

## 14. Java/JUnit: Testing Allowed Reads and Denied Writes

JUnit 5 example:

```java
import com.mongodb.MongoException;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class MongoRbacIntegrationTest {

    @Test
    void readerCanFindButCannotInsert() {
        try (MongoClient client =
                MongoTestConnection.connectFromEnv(
                    "MONGO_TEST_READER_URI")) {

            MongoCollection<Document> orders =
                MongoTestConnection.orders(client);

            // Positive: role includes the find action.
            Document sample = orders.find(
                new Document("_id", "order-a-001"))
                .first();
            assertNotNull(sample);

            // Negative: read-only user must not insert.
            MongoException ex = assertThrows(
                MongoException.class,
                () -> orders.insertOne(
                    new Document("_id", "negative-insert")
                        .append("tenantId", "tenant-a")
                )
            );

            assertNotNull(ex);
        }
    }
}
```

This test proves both properties at a basic level. To strengthen it further:

1. Verify the exception represents an **authorization failure**, not a connectivity error.
2. Query with the fixture admin afterward to confirm `negative-insert` **does not exist**.
3. Ensure fixture preconditions exist; if the positive find returns null due to a missing fixture, fail explicitly.
4. Attach unique test run IDs so parallel CI jobs do not collide.

**Never share a live user-serving collection** for denied-insert tests, because a misconfigured role could allow the write to succeed.

## 15. Asserting Negative Results Fail for the Right Reason

A test written like this:

```java
assertThrows(
    MongoException.class,
    () -> readerOrders.insertOne(forbiddenDocument)
);
```

can produce a **false pass** if MongoDB is unreachable, TLS fails, or the URI is malformed. Security tests should also assert the **error category/cause**.

Example with `MongoCommandException`:

```java
import com.mongodb.MongoCommandException;
import static org.junit.jupiter.api.Assertions.*;

MongoCommandException error = assertThrows(
    MongoCommandException.class,
    () -> readerOrders.insertOne(
        new Document("_id", "forbidden-test")
    )
);

assertEquals(13, error.getErrorCode());
```

In MongoDB, error code **13** typically corresponds to `Unauthorized`. Some driver/server operations may surface different errors or wrap exceptions; adjust assertions to your driver/server version and **do not confuse authorization errors with authentication failures**.

If a user cannot authenticate, the command may never reach the authorization stage. A "reader cannot insert" test must use a **successfully authenticated reader**.

### Verifying Data Remained Unchanged

After a negative test, read with the fixture admin:

```javascript
db.getSiblingDB("security_lab").orders.findOne({
  _id: "forbidden-test"
});
```

Expect no new document. Run this check only within an isolated test setup; integrating verification into the same test flow or cleanup must fit the environment design.

## 16. Java/JUnit: Invalid Credentials Must Not Grant Access

A test using invalid credentials:

```java
import com.mongodb.MongoException;
import com.mongodb.client.MongoClient;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class MongoAuthIntegrationTest {

    @Test
    void wrongPasswordCannotRead() {
        try (MongoClient client =
                MongoTestConnection.connectFromEnv(
                    "MONGO_TEST_WRONG_AUTH_URI")) {

            MongoException error = assertThrows(
                MongoException.class,
                () -> client
                    .getDatabase("security_lab")
                    .runCommand(new Document("ping", 1))
            );

            assertNotNull(error);
        }
    }
}
```

Note that drivers may report authentication failures via specific exception types (such as `MongoSecurityException`) or nested causes after server selection/connection handshake. Avoid asserting exact error message strings because wording can change across versions.

### Do Not Confuse Network Failure with Auth Failure

Before an invalid-credential test, establish a precondition:

```text
Correct credentials + same network path -> CONNECT PASS
Wrong credentials + same endpoint       -> AUTH DENY
```

If both valid and invalid credentials fail due to DNS/firewall issues, the test has not verified the auth policy.

## 17. Testing Authentication in Spring Data MongoDB

Spring Data repositories typically use credentials configured in `MongoClient`/the Spring Boot datasource context rather than creating a new MongoDB user per HTTP request.

Diagram:

```text
HTTP user Alice/Bob
      |
      v
Spring Security + application authorization
      |
      v
Spring Data MongoRepository
      |
      v
MongoDB service user "svc_orders_api"
```

This leads to two distinct test groups:

**A. Database identity tests:** does the service account have the exact required privileges? Run against a real MongoDB instance using that identity.

**B. API/user authorization tests:** Alice cannot view Bob's data even though both requests share the same MongoDB service account.

**A `readWrite` DB account cannot automatically enforce per-HTTP-user rules.** MongoDB sees the app service identity, not necessarily the end-user principal when the service uses a shared connection pool.

## 18. Multi-Tenant Authorization: IDOR/BOLA Vulnerabilities

A common risk is **Broken Object Level Authorization (BOLA)**, often referred to as IDOR in ID-based access scenarios.

Example endpoints:

```text
GET /api/orders/order-a-001
GET /api/orders/order-b-001
```

When a Tenant A user swaps the ID from `order-a-001` to `order-b-001`, the API **must not** return Tenant B's data just because the document ID exists.

### Vulnerable Code Pattern

```java
public OrderDto getOrder(String id) {
    Order order = repository.findById(id)
        .orElseThrow();
    return mapper.toDto(order);
}
```

This snippet checks only that the document exists, **not its tenant/owner**. You must include the scope condition from the **authenticated principal** in the query or perform an explicit authorization check.

### Only Trust `tenantId` Taken from the Security Context

```text
Authenticated principal:
  tenantId = tenant-a

Request query:
  orderId = order-b-001

Database filter:
  _id = order-b-001
  AND tenantId = tenant-a

No match -> Tenant B order is not returned
```

**Never take `tenantId` from query params/request body and trust it as the authorization source.** A client can send `tenantId=tenant-b`. Only accept a client-supplied tenantId if the API has an explicit delegation contract and verifies that the principal is authorized to act on behalf of that tenant.

## 19. Spring Data: Tenant-Scoped Queries

Simplified entity example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public class OrderEntity {
    @Id
    private String id;
    private String tenantId;
    private String ownerId;
    private String status;

    public OrderEntity() {}

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }
    public String getOwnerId() { return ownerId; }
    public void setOwnerId(String ownerId) {
        this.ownerId = ownerId;
    }
    public String getStatus() { return status; }
    public void setStatus(String status) {
        this.status = status;
    }
}
```

Repository with a scoped query:

```java
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderEntity, String> {

    Optional<OrderEntity> findByIdAndTenantId(
        String id,
        String tenantId
    );
}
```

Service:

```java
public OrderEntity findOrderForTenant(
        String orderId,
        String tenantIdFromAuthenticatedPrincipal) {

    return repository.findByIdAndTenantId(
        orderId,
        tenantIdFromAuthenticatedPrincipal
    ).orElseThrow(() ->
        new ResourceNotFoundException("Order not found"));
}
```

`ResourceNotFoundException` is an application-defined exception; returning HTTP 404 can be chosen to avoid revealing the existence of out-of-tenant resources, per API policy.

### Escalating Requirements to Owner Level

If not every user within a tenant should see all orders, the query must also include `ownerId` or role scopes:

```text
_id == request.orderId
AND tenantId == principal.tenantId
AND (ownerId == principal.userId OR principal has authorized role)
```

Actual scope is part of **business authorization**, not merely a field name.

## 20. Tenant Scoping Must Apply to UPDATE and DELETE

An application may protect GET properly yet forget to check PATCH or DELETE:

```java
// Missing tenant scope:
template.updateFirst(
    Query.query(Criteria.where("_id").is(orderId)),
    new Update().set("status", "CANCELLED"),
    OrderEntity.class
);
```

If the API lets Tenant A submit Tenant B's order ID, the statement above can modify Tenant B's document.

### Conditional Update with Tenant Scope

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query filter = Query.query(
    Criteria.where("_id").is(orderId)
        .and("tenantId").is(principalTenantId)
        .and("status").is("NEW")
);

Update change = new Update()
    .set("status", "CANCELLED");

UpdateResult result = template.updateFirst(
    filter, change, OrderEntity.class
);

if (result.getMatchedCount() == 0) {
    // No authorized and eligible document to update.
}
```

**Checking scope and business state in the same MongoDB update predicate** prevents race conditions between "check access" and "write".

When using `@Version` optimistic locking, you may also need `expectedVersion` in the same filter according to your versioning contract. AuthZ, optimistic locking, and domain invariants are three conditions that can be combined together.

## 21. Matrix of Tenant-Level Positive and Negative Tests

| Case | Principal | Action | Target | Expectation |
| --- | --- | --- | --- | --- |
| TENANT-01 | user-a/tenant-a | GET | order-a-001 | Allow |
| TENANT-02 | user-a/tenant-a | GET | order-b-001 | Deny/404 |
| TENANT-03 | user-a/tenant-a | PATCH | order-a-001 | Allow if state is valid |
| TENANT-04 | user-a/tenant-a | PATCH | order-b-001 | Deny, no data mutation |
| TENANT-05 | user-a/tenant-a | DELETE | order-b-001 | Deny |
| TENANT-06 | user-b/tenant-b | GET | order-b-001 | Allow |
| TENANT-07 | Anonymous | GET | order-a-001 | Unauthorized |
| TENANT-08 | tenant-a admin | GET | order-b-001 | Deny if lacking cross-tenant privilege |
| TENANT-09 | user-a/tenant-a | List orders | Sets A and B | Return only Tenant A orders |
| TENANT-10 | user-a/tenant-a | Aggregation/report | Multiple tenants | Authorized data only |

Testing GET by ID is **not enough**. Frequently overlooked paths include:

- Pagination/list/search/filter.
- CSV/PDF exports.
- Aggregation `$lookup`.
- Bulk update/delete.
- Change streams/notifications/WebSockets.
- Batch jobs/reports.
- File attachments/GridFS.
- Admin "impersonation" or support tools.

Tenant isolation must be verified across **every read and write path that can access data**.

## 22. JUnit: Testing Application Authorization

A simple service test using hypothetical fixtures:

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderAccessIntegrationTest {

    private OrderService service;

    @Test
    void tenantCannotReadForeignOrder() {
        OrderEntity own = service.findOrderForTenant(
            "order-a-001", "tenant-a");
        assertEquals("tenant-a", own.getTenantId());

        assertThrows(
            ResourceNotFoundException.class,
            () -> service.findOrderForTenant(
                "order-b-001", "tenant-a")
        );
    }
}
```

This is the **core test body**; actually running it requires configuring `OrderService`, repositories, application context, and seed data. In HTTP integration tests, the tenant ID must be derived from a real authenticated principal or controlled security context mock — **do not merely call the service with an arbitrary string and conclude the endpoint is secure**.

### Testing at the Controller Layer

Combine the appropriate Spring Security testing tools:

- Request with Tenant A principal and resource A.
- Request with Tenant A principal and resource B.
- Request without a token.
- Request with an expired or invalidly signed token.
- Request with insufficient roles.

After a negative PATCH/DELETE, read the document back using the fixture admin to verify the data **did not change**.

## 23. Testing Projections and Response Data Minimization

A database document may contain many fields:

```javascript
{
  _id: "customer-a-001",
  tenantId: "tenant-a",
  displayName: "Test Customer",
  contactEmail: "fixture@example.invalid",
  passwordHash: "fixture-not-a-real-hash",
  internalRiskScore: 7,
  paymentReference: "TEST-REF",
  internalNotes: "Internal support only"
}
```

The public endpoint only needs:

```json
{
  "id": "customer-a-001",
  "displayName": "Test Customer"
}
```

If an API serializes the raw MongoDB `Document` or entity directly, it can expose `passwordHash`, `internalRiskScore`, `internalNotes`, or sensitive fields added later.

### Using an Allowlist DTO

```java
public record CustomerPublicDto(
    String id,
    String displayName
) {}
```

The mapper extracts only allowed fields. Advantage: adding a sensitive field to the entity later will not automatically leak it into the API response.

### Using Projections to Reduce Retrieved Data

For example:

```java
Query query = Query.query(
    Criteria.where("_id").is(customerId)
        .and("tenantId").is(principalTenantId)
);

query.fields()
    .include("displayName")
    .exclude("_id");

CustomerPublicProjection projection =
    template.findOne(
        query, CustomerPublicProjection.class, "customers");
```

This illustrates the design pattern; `CustomerPublicProjection` requires a matching class/mapping. **Projections do not replace authorization**: if the filter lacks the tenant predicate, the endpoint can still expose an unauthorized user's `displayName`.

**Projections and DTOs should complement each other**, rather than relying solely on annotations to hide JSON fields, because sensitive data can still be logged or serialized along other code paths.

## 24. Negative Tests for Sensitive Data in Responses

An API test:

```text
GET /api/customers/customer-a-001
Principal tenant-a
Expected 200

Response MUST contain:
  id
  displayName

Response MUST NOT contain:
  passwordHash
  internalRiskScore
  paymentReference
  internalNotes
  mongoConnectionUri
```

A JSON response can be nested. Do not simply search for the substring `passwordHash` in the raw response text; parse the JSON, inspect JSON paths, and assert against an **allowlist schema**. If the API uses error envelopes, pagination wrappers, or GraphQL, inspect payloads for those response shapes too.

### "Must Not Leak" Tests Require Fixtures That Actually Populate Those Fields

If a fixture **omits** `internalNotes`, a test asserting "response does not contain internalNotes" can pass even when the mapper would serialize that field whenever present.

To verify redaction/projection effectively, fixtures must populate **fake values in sensitive fields**, then assert those values never make it into the response.

## 25. Preventing NoSQL Query Injection

Some vulnerabilities arise when an application accepts arbitrary JSON from a client and passes it straight into a MongoDB filter.

Example unintended payload:

```json
{
  "email": {
    "$ne": null
  }
}
```

If a login or lookup API expects `email` to be a string but accepts an object and evaluates it as a **MongoDB operator expression**, the query can behave completely differently from what was intended.

### Risky Pattern

```java
// Warning: never pass an arbitrary client-supplied Map
// into a filter or raw command without schema validation.
Document rawQuery = new Document(userSuppliedMap);
collection.find(rawQuery);
```

### Strongly Typed Pattern

```java
public record FindCustomerRequest(String email) {}

if (request.email() == null || request.email().isBlank()) {
    throw new IllegalArgumentException("email is required");
}

collection.find(
    Filters.eq("email", request.email())
);
```

When `email` is a Java `String`, the driver encodes it as a **BSON String value** in the equality filter, not a document containing client-controlled operators.

### Negative Tests

- Client sends a normal string email: processed according to contract.
- Client sends email as an object containing `$ne`: API returns a validation error without executing raw operators.
- Client sends JSON with `$where` or unexpected keys: rejected if disallowed by the schema.
- Client sends `tenantId` conflicting with the principal: filter must still use the principal's tenantId.

Never throw arbitrary dangerous expressions at production to "test injection." Run negative inputs against fixtures and verify **API validation**, without expanding into out-of-scope attacks.

## 26. Distinguishing Input Validation from Database Authorization

Input validation answers "does the payload match the API schema?" Authorization answers "is the actor permitted to perform the action?"

For example:

```text
Payload:
  status = "PAID"
  orderId = "order-b-001"

Input validation:
  status is a valid enum -> PASS

Authorization:
  tenant-a user does not own order-b-001 -> DENY
```

A type-valid payload can still violate **business/access rules**. Conversely, even an authorized user must not be permitted to inject unsupported raw MongoDB expressions into a REST API.

### What Does MongoDB Schema Validation Add?

A MongoDB collection validator can enforce:

- Required fields.
- BSON types.
- Enums/ranges/supported structural constraints.

However, a collection validator normally **has no awareness of the authenticated HTTP principal** or application tenant policy. Validators and tenant authorization must be tested independently.

## 27. TLS: Testing Encryption in Transit

MongoDB can require TLS. Test objectives:

1. Clients connect successfully using TLS and a valid certificate.
2. Clients are **not** allowed to connect over plaintext when policy specifies `requireTLS`.
3. Clients reject untrusted certificates or hostname mismatches.
4. No certificate-verification bypass is configured in production.
5. Certificate rotation does not break valid connections.

Conceptual self-managed configuration snippet:

```yaml
net:
  bindIp: "127.0.0.1,10.10.20.12"
  port: 27017
  tls:
    mode: requireTLS
    certificateKeyFile: "/etc/mongodb/tls/server.pem"
    CAFile: "/etc/mongodb/tls/ca.pem"
security:
  authorization: enabled
```

This is an **excerpt**, not a complete production configuration. Replica sets and sharded clusters require proper internal authentication as well as valid certificate SANs and trust chains.

### Positive TLS Test

```text
Trusted CA + correct hostname + tls=true
  -> TLS handshake succeeds
  -> proceeds to AuthN/AuthZ
```

### Negative TLS Test

```text
Wrong hostname / untrusted CA
  -> client rejects server identity
```

**Never fix a test using `tlsInsecure=true` or disabling hostname validation** when the real requirement is a secure connection. Insecure flags may only be considered in special lab cases, never as passing criteria for production security tests.

## 28. Testing Network Controls, Atlas IP Access Lists, and Private Connectivity

With an Atlas public endpoint, network reachability can be controlled by the **Project IP Access List**. However, an IP list is only a network layer control, not a database user.

Matrix:

| Test Source | Network Policy | Credential | Expectation |
| --- | --- | --- | --- |
| Allowed CI egress | Allow | Valid | Connects, then RBAC applies |
| Allowed CI egress | Allow | Invalid | AuthN deny |
| Disallowed test source | Deny | Valid | Cannot reach the endpoint |
| Private endpoint workload | Valid private path | Valid | Connects via private DNS/route |
| Private endpoint workload | Misconfigured private DNS | Irrelevant | Cannot use expected private path |

Do not generate uncontrolled Internet traffic. Network negative tests should run from an **approved test source** outside the access list without causing scans or abnormal traffic.

### What to Watch Out for with NAT

Over a public Atlas path, the source address Atlas sees is typically the **public egress IP behind NAT**, not the private IP of the Pod or VM.

For example:

```text
CI Pod: 10.2.1.5
Cloud NAT: 198.51.100.24
Atlas public endpoint
```

`198.51.100.24` is an example address. NAT changes can cause network-level test failures even when credentials are valid.

### A Private Endpoint Does Not Automatically Prove Traffic Flows Privately

Tests should verify DNS resolution, routing, endpoint state, and connection strings. An application may have provisioned a Private Endpoint yet still use a URI resolving to public endpoints. Checking only "connect succeeds" is insufficient.

## 29. TLS Testing vs. Authentication Testing

When a client fails certificate verification, the failure occurs **before the database user is authenticated**. If a test supplies a wrong password while TLS is also misconfigured, the returned error may be a TLS handshake failure rather than "password rejected."

Layer tests cleanly:

```text
TEST-TLS:
  valid server cert? yes/no

TEST-AUTHN:
  TLS already verified
  valid credentials? yes/no

TEST-AUTHZ:
  TLS already verified
  credentials already verified
  privilege for operation? yes/no
```

This prevents negative tests from passing falsely because a lower layer broke first.

## 30. Encryption at Rest, in Transit, and Field-Level Encryption

Three distinct protection mechanisms:

| Mechanism | Primary Protection Scope | What It Does Not Automatically Guarantee |
| --- | --- | --- |
| TLS in transit | Client-server network traffic | Does not encrypt data copies in app memory or logs |
| Encryption at rest | Storage files/backups per backend/platform | Authorized DB users still read plaintext via queries |
| Client-Side Field Level Encryption (CSFLE) | Selected fields encrypted **before reaching server** | Does not replace authorization or secret hygiene |
| Queryable Encryption (when supported) | Selected encrypted fields and supported query patterns | Not free in storage/index overhead; does not encrypt all fields by default |

**Note:** MongoDB Atlas/Enterprise, cloud disk encryption, and client-side encryption features have different capabilities and requirements. Do not assume Community self-managed includes every Enterprise/Atlas feature.

### How to Test Encryption at Rest

Do not SSH onto production disks to open WiredTiger files looking for plaintext. Appropriate verification methods include:

- Reviewing storage encryption and KMS policies/configurations.
- Inspecting encryption keys, rotation, and access policies according to granted permissions.
- Verifying backups/snapshots are also encrypted per policy.
- Auditing who can access volumes, snapshots, and key material.
- Reviewing compliance evidence and infrastructure-as-code controls.

Reading plaintext through an authorized MongoDB query **does not disprove encryption at rest**: the server decrypts data for authorized clients by design.

## 31. Testing Client-Side Encrypted Fields

Suppose the `customers` collection has an `identityNumber` field that policy requires to be client-side encrypted:

```text
Java Application
  plaintext identityNumber
       |
       v
  CSFLE / encryption library + KMS key
       |
       v
MongoDB stores ciphertext for the selected field
       |
       v
Client with key + proper privileges -> decrypts
Client without key -> cannot auto-decrypt
```

Tests should verify:

1. A client with the proper key and role writes and reads data accurately.
2. A client lacking the decryption key cannot obtain the plaintext field via automatic decryption.
3. Stored values are genuine encrypted BSON values for the configured feature, not merely base64-encoded strings.
4. KMS key policies are no broader than required.
5. Sensitive plaintext never appears in application logs or exception stack traces.
6. Key rotation and migration scenarios are planned and tested.
7. Queries/filters on encrypted fields only use supported operators and features.

**Base64 is not encryption.** Anyone can decode a base64 string without a key. Masking and hashing are not encryption either; they serve different purposes.

## 32. Testing Secrets and MongoDB URI Configuration

A connection URI can contain:

```text
mongodb://<username>:<password>@host:27017/<db>?authSource=...
```

If the full URI is logged, an attacker can harvest credentials without needing to bypass authentication at all.

### Common Places Secrets Leak

- `application.properties`/`application.yml` committed to the repository.
- Environment dumps attached to CI artifacts.
- Log messages like `"Connecting to " + mongoUri`.
- Exception handlers returning full stack traces or driver settings.
- Unit test snapshots containing URIs with passwords.
- Docker Compose files containing plaintext credentials.
- Metrics/tracing tags recording full connection strings.
- Shell history or process command lines when invoking CLI tools.

### Positive Configuration Checks

- Secrets are fetched from a secret manager or CI secret store.
- The application never logs plaintext passwords.
- Roles/service accounts adhere to least privilege.
- A credential rotation workflow exists and is tested in staging.
- TLS private keys are protected via proper file permissions or KMS.

### Negative Redaction Tests

Create a dedicated **fake secret marker** for fixtures, such as `TEST_SECRET_NEVER_LOG_001`. Trigger an expected error path and verify:

```text
Application log contains "TEST_SECRET_NEVER_LOG_001"?
  YES -> FAIL
  NO  -> PASS within the inspected log scope
```

Never place real secrets into test logs just to verify masking works. Use synthetic markers and make sure log capture covers real error paths.

## 33. Testing Logging and Exception Handling

A database exception can expose:

- Hostnames and ports.
- Database and collection names.
- Query or command details.
- Document fragments or sensitive fields logged by application code.
- Stack traces.

Never return raw exceptions directly over HTTP:

```java
// Avoid:
return ResponseEntity.status(500)
    .body(exception.toString());
```

A safer response:

```json
{
  "code": "INTERNAL_ERROR",
  "message": "Unable to process request",
  "correlationId": "test-correlation-001"
}
```

Server logs may retain additional diagnostic details per policy, but sensitive fields must be redacted/masked and log access restricted. Hiding details from the HTTP client is not enough if backend logs still persist full tokens or PII.

### What Scenarios Should Log Redaction Tests Cover?

1. Authentication failure.
2. Authorization denial.
3. Validation errors involving PII fields.
4. Duplicate key errors on sensitive fields.
5. Query timeouts or network disconnects.
6. Failed encryption or KMS access.
7. Unexpected exceptions in controllers.

Do not rely on a single regex for every type of secret; maintain an explicit catalog of sensitive fields and logging contracts.

## 34. Audit Logging and Sensitive Actions

**Auditing** needs to answer: who did what, when, on which resource, whether it was allowed or denied, and which request triggered the action.

An illustrative application audit event:

```json
{
  "eventType": "ORDER_ACCESS_DENIED",
  "actorId": "user-a",
  "tenantId": "tenant-a",
  "resourceType": "order",
  "resourceId": "order-b-001",
  "outcome": "DENIED",
  "correlationId": "req-test-001"
}
```

You do not need to log the **entire PII payload** of an order to record unauthorized access. Audit logs themselves can contain personal data, so they require access control and retention policies.

### Distinguishing MongoDB Audit vs. Application Audit

- MongoDB server/Atlas auditing (when supported by feature/tier) records security and database-level events.
- Application auditing knows the **HTTP user, tenant, business operation, and approval chain** — context the database server cannot infer when requests share a single MongoDB service user.

Therefore, multi-tenant applications often need **both levels** of auditing when policy requires it.

### Testing Auditing

| Operation | Audit Expectation |
| --- | --- |
| Successful sensitive read | Logs event per policy without excessive PII |
| Denied cross-tenant read | Records appropriate actor/target/outcome |
| Denied DB write privilege | Records database/auth event if platform supports it |
| Credential rotation | Records change/approval event |
| Export/backup/restore | Records actor, scope, purpose, and audit trail |
| Admin role change | Records event and triggers alert if required |

An audit test should verify **the event exists**, minimum fields are populated accurately, and secrets are omitted. If auditing is disabled or unsupported on the tier, do not assume a PASS.

## 35. Data Retention, TTL, and Privacy Deletion

Protecting sensitive data goes beyond blocking unauthorized reads; it also includes **not keeping data longer than necessary**.

A `temporary_tokens` collection might use TTL:

```javascript
db.temporary_tokens.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
```

However:

- TTL deletion **does not happen at the exact millisecond** of expiration.
- TTL does not guarantee data has vanished from all backups or snapshots.
- A token deleted from the collection but still lingering in logs remains exposed.
- A TTL index is neither an authorization mechanism nor encryption.

### Testing Retention

1. Documents with an eligible expiry are cleaned up by TTL within the permitted window.
2. Unexpired documents are not deleted prematurely.
3. Backup retention matches policy.
4. Logs and test artifacts have defined retention periods.
5. Deletion workflows handle dependencies, exports, and backups per legal/policy requirements.

**Do not call `Thread.sleep(1000)` and assert that a TTL document must already be gone**; the TTL monitor runs on its own schedule. Integration tests should use bounded polling/time tolerance in a lab environment.

## 36. Backups and Snapshots Also Contain Sensitive Data

A production database with strict RBAC still suffers a breach if a backup archive is uploaded to a public bucket.

Backup checklist/tests:

| Item | Expectation |
| --- | --- |
| Access control | Restricted solely to authorized backup/restore operators |
| Encryption | Appropriate at-rest and transport encryption |
| Retention | Sufficient for recovery without indefinite hoarding beyond policy |
| Isolation | Stored outside the production failure domain as appropriate |
| Restore destination | Staging environment matches the data sensitivity in network/RBAC |
| Temporary artifacts | Dump archives, logs, and CSV exports cleaned up on schedule |
| Audit | Backup/export/restore records actor and change log |
| Recovery test | Restore drills run without exposing broad PII into dev environments |

### Do Not Copy Production Data into Unprotected Test DBs

If production-like data is strictly necessary, you must:

- Mask or tokenize identifiers, emails, phone numbers, addresses, and accounts.
- Preserve cross-collection referential consistency after masking.
- Restrict operator and test-runner permissions.
- Enforce clear retention and cleanup rules.
- Prohibit re-identification unless explicitly authorized.

Encrypted backups do not automatically make a restore environment safe if the restore decrypts data into a broadly accessible collection.

## 37. Testing Role Changes and Credential Rotation

Service identities and roles evolve over time. Tests must cover those transitions.

### Credential Rotation

```text
Before rotation:
  credential V1 -> connect OK

After rotation/cutover:
  credential V2 -> connect OK
  credential V1 -> denied per policy
```

Applications maintain connection pools; when credentials rotate, existing pooled connections may not reflect the change immediately the way a brand-new connection does. Therefore, **separate new-connection tests from active-pool behavior tests**, plan connection draining/recreation, and allow temporary overlap when policy requires zero-downtime cutovers.

### Role Regression

If a release adds an order-export feature, a developer might ask to grant `readAnyDatabase` to the service. That privilege is usually far too broad.

Instead:

1. Identify the exact database and collection needed.
2. Add the minimal privilege.
3. Test the legitimate export functionality.
4. Test that out-of-scope collections/databases cannot be exported.
5. Review log paths and CSV artifacts since exports can contain PII.

## 38. Testing Atlas Admin Roles vs. Database RBAC

Atlas separates **project/organization access roles** for UI/API administration from **database users/roles** for MongoDB commands. These are two distinct permission systems.

Test questions:

- Can a project read-only viewer modify the Atlas IP Access List?
- Are operators allowed to create or delete database users?
- Can an application database user modify Atlas project configuration?
- Does an Atlas console user automatically gain database credentials to read collections?
- Are only authorized teams permitted to manage backups/restores/exports and private endpoint policies?

**A `readWrite` database role does not grant Atlas project administration rights.** Conversely, UI visibility on a cluster does not imply having MongoDB database credentials to query collections.

In CI, if no Atlas test project is available, verify these controls through **policy/configuration assertions** or approved staging checks rather than attempting administrative operations on production.

## 39. Protecting Access at Collection and Field Levels

MongoDB built-in roles control privileges at the database/collection/command level; they are **not an automatic mechanism to hide individual PII fields per HTTP user**. If a service holds `find` on a collection, it can read any documents and fields accessible at that scope unless additional mechanisms are designed and enabled.

Therefore:

- **Application projections** restrict fields exposed in APIs.
- **Application authorization** restricts documents by tenant/owner.
- **CSFLE/Queryable Encryption** protects encrypted fields based on key access.
- **Database roles** restrict resources and actions.
- **Views** can expose a narrowed read surface when properly designed and privileged, though view definitions and underlying permissions must be verified for your MongoDB version.

Never assume a `read` role on `customers` automatically hides `identityNumber` from the application.

## 40. Multi-Tenant: Authorization Must Cover Complex Queries

An aggregation report:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-a" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  }
]);
```

If a developer drops the tenant `$match`, the report aggregates counts across all tenants. That is an **aggregation leak**, even when no individual documents are returned.

### Operators Requiring Testing

- `$match`: scoped by tenant/owner.
- `$lookup`: does not join into another tenant's data when policy forbids it.
- `$facet`: every branch output enforces proper scoping.
- `$group`: aggregated counts/sums never mix tenants.
- `$unionWith` (if used): does not pull out-of-scope collections/documents.
- `$out`/`$merge`: restricted to authorized writers and approved destinations.

If a business requirement explicitly permits anonymized cross-tenant analytics, define a dedicated policy for it; never assume multi-tenant reports are universally allowed or forbidden.

### Testing Aggregations with Asymmetric Fixtures

Create 2 orders for Tenant A and 5 orders for Tenant B. When User A views the report:

```text
Expected count = 2
Not expected = 7
```

Distinct fixture counts make missing tenant filters immediately obvious. If both tenants happen to have identical counts or totals, tests may miss mixed results.

## 41. Sensitive Data in Search, Pagination, and Exports

Endpoints commonly overlooked:

```text
GET /orders?page=...
GET /orders/search?email=...
GET /reports/orders.csv
POST /orders/bulk-export
GET /customers/{id}/attachments
GET /audit/events
```

Verification steps:

1. Scope search by tenant and role, not only exact-ID lookups.
2. Ensure pagination totals/counts do not disclose record counts from other tenants.
3. Disallow sorting or filtering on out-of-policy sensitive fields.
4. Restrict CSV exports to approved columns with bounded row limits.
5. Protect generated files with scoped access tokens, expirations, and storage ACLs.
6. Verify document ownership before streaming attachment bytes.
7. Ensure error responses do not reveal the existence of another tenant's IDs when policy hides existence.

For CSV exports, also consider **spreadsheet formula injection** when user-supplied values start with formula characters. This is an **export-format** concern rather than MongoDB RBAC; test escaping according to supported formats and consumers.

## 42. Running Security Tests with Docker/Testcontainers

Running MongoDB in a container makes integration tests reproducible. However, a default MongoDB container **without authentication enabled** suffices for CRUD tests but **is not enough for RBAC/AuthN tests**.

A genuine authentication test environment should provision:

- A MongoDB server with authorization enabled.
- Test users/roles with distinct privileges.
- Fixture databases and collections.
- TLS certificates or test PKI when testing TLS.
- Network isolation.
- Automated cleanup/teardown.

### Separating Test Suites by Purpose

| Suite | Environment | Verifies |
| --- | --- | --- |
| Unit tests | Mocks/fakes | Policy decisions, tenant scope builders |
| Repository integration | MongoDB test instance | BSON mappings, query predicates, indexes |
| DB AuthN/RBAC integration | Auth-enabled MongoDB | Credentials, role allow/deny |
| TLS/network integration | TLS-enabled test deployment | Certificate validation, network allow/deny |
| API security E2E | App + auth + MongoDB test | BOLA/IDOR, projections, error responses, exports |
| Backup/restore/security config | Controlled staging | Backup encryption/access, restore privacy |

You do not have to run every heavyweight suite on every commit, but you should enforce **mandatory gates** for critical security requirements and scheduled runs for infrastructure checks.

### Avoid Exposing Test Databases Broadly

With Docker, avoid publishing port `27017` on all host interfaces unnecessarily. Restrict test networks, bind to host loopback if a host runner must connect, and check image/container settings. Even when a container sets `bindIpAll` inside its namespace, it must remain protected at the Docker publishing and network layers.

## 43. Using Spring Security in Authorization Tests

In a Spring Boot HTTP app, authentication may be handled by Spring Security while the MongoDB service user operates on the backend. Tests should cover:

```text
Anonymous -> 401 if endpoint requires login
Authenticated user lacking role -> 403 (or configured policy)
User with role in different tenant -> 403/404 per contract
User with role + matching tenant -> 200/expected result
```

### Never Accept and Trust `tenantId` from Request Parameters

Code such as:

```java
String tenantId = request.getParameter("tenantId");
```

to determine authorization is unsafe if a client can tamper with `tenantId`. The authoritative source must be a **verified authenticated principal/claim**, combined with explicit validation when a user belongs to multiple tenants and selects one.

### Be Careful with JWT Claims

A base64url-encoded JWT payload is not verified merely because it decodes. Security filters must validate signature, issuer, audience, expiration, and configured claims. Tests must confirm a self-signed token claiming `role=admin` cannot bypass authentication.

If tokens can be revoked prior to expiration, define explicit revocation/session/token lifecycle policies; MongoDB RBAC does not handle HTTP token revocation.

## 44. Testing Tenant Boundaries with Caching

An application may query MongoDB with proper tenant scoping yet use an unsafe cache key:

```text
cache key = "order:order-a-001"
```

If IDs are not globally unique or the cache returns objects without rechecking authorization, one tenant may observe another tenant's data.

Recommendation:

```text
Cache keys include appropriate identity/scope,
e.g. tenantId + resourceId,
and the caching layer enforces authorization policy.
```

Security tests should cover both **cache miss** and **cache hit**:

1. User A reads Order A, warming the cache.
2. User B requests the same resource ID or a crafted path.
3. Verify User B is still denied.

Testing only repositories while bypassing caching and controllers can miss this class of leak.

## 45. Error Handling: 401, 403, 404, and Information Disclosure

Different HTTP status codes serve distinct purposes:

| Status | Typical Meaning | When to Test |
| --- | --- | --- |
| 400 | Invalid input | Malformed JSON shape, unexpected operators |
| 401 | Unauthenticated / invalid API credentials | Missing or invalid HTTP token |
| 403 | Authenticated but unauthorized | Insufficient roles |
| 404 | Resource not found / hides existence | Cross-tenant access per policy |
| 409 | Conflicting state | CAS / business state conflict |
| 500 | Handled server error | No leaked stack traces or secrets |

**A MongoDB `Unauthorized` error should not automatically map to HTTP 403** in every service. It often signals a **service account provisioning bug**, in which case the API should return a generic error and alert operations rather than exposing database command details to clients.

### Enumeration Risk

If an API returns 404 for nonexistent IDs but 403 for existing IDs belonging to another tenant, an attacker can infer resource existence. A policy may choose to return 404 for both to minimize disclosure. Tests should assert **alignment with policy**, rather than forcing one HTTP status across every context.

## 46. Test Cases for Admin and Operational Commands

High-impact operations include:

- `dropCollection` / `dropDatabase`.
- `createUser` / `grantRolesToUser`.
- `createIndex` / `collMod`.
- `shutdown` / configuration commands depending on topology.
- Backup/export/restore.

An application service account rarely needs privileges for any of these operations.

### Separation of Duties

```text
App runtime user:
  business read/write privileges only

Migration/DBA identity:
  index/schema migrations via change request

Backup identity:
  required backup/export privileges

Atlas project admin:
  infrastructure/project management via dedicated role
```

Release tests should ensure runtime application credentials **cannot escalate privileges** simply because a migration job runs in the same pipeline.

### Do Not Use Root for Every Test

If all integration tests connect as the MongoDB root user, tests will fail to catch:

- New application code requiring an unapproved privilege.
- A read-only account mistakenly granted write privileges.
- Overly broad collection scopes.

Always include tests running under a **production-like service identity** in a non-production environment without real data.

## 47. Common Testing Pitfalls

| Symptom | Possible Cause | Diagnosis / Fix |
| --- | --- | --- |
| Wrong-password test passes, valid user also fails | DNS/TLS/firewall failure | Fix network preconditions first |
| Read-only user succeeds on insert | Effective role is too broad | Inspect `usersInfo`/role definitions and provisioning |
| Reader cannot list collections | Custom role grants `find` only | Test permitted actions rather than granting root |
| Cross-tenant GET returns data | Query omits tenant scope | Scope queries from authenticated principal |
| GET is safe but PATCH modifies another tenant | Update filter checks only `_id` | Add tenant/owner/state predicates |
| Response leaks internal fields | Entity serialized directly | Enforce DTO allowlists/projections |
| Logs contain MongoDB URI with password | Logging config or exception handler | Redact credentials and test with fake secret markers |
| CSFLE test fails | Misconfigured key/KMS/ciphertext setup | Verify feature availability and key access |
| TLS test succeeds with insecure option | Validation disabled | Restore defaults and enforce verification |
| Atlas UI user fails DB queries | Project roles differ from DB users | Provision appropriate database users |
| Auth test fails right after creating client | Command not yet executed | Run an actual authenticated command |
| Negative insert fails with duplicate key | Not an authorization denial | Use unique fixtures and assert error code |
| Test passes against empty fixture | No cross-tenant or sensitive targets | Seed contrasting fixture data |
| CI artifacts contain PII | Broad dump/log/report capture | Use synthetic fixtures and scrub artifacts |
| TTL test times out | TTL cleanup runs asynchronously | Poll with bounded timeout and account for monitor schedule |
| Background job reads cross-tenant | Job skips application auth scope | Enforce dedicated service/job scope policy |
| MongoDB backup publicly accessible | Storage ACL/encryption misconfigured | Audit backup platform and network controls |
| Parallel CI jobs overwrite fixtures | Hard-coded IDs / shared DB | Isolate namespaces/`testRunId` and clean up |

## 48. Pre-Release Testing Runbook

### Step 1 — Verify Requirements and Scope

```text
Release:
MongoDB server/version:
Application version:
Environment:
Approved security requirements:
Roles under test:
Tenant fixtures:
Test operator:
```

Determine which tests block every PR, which run nightly, and which require staging Atlas/PKI/network infrastructure.

### Step 2 — Provision Isolated Fixtures

1. Create a test database/cluster on the proper network.
2. Provision roles/users via bootstrap automation backed by a secret store.
3. Seed documents for Tenant A/B with synthetic PII.
4. Enable auth/TLS matching the target environment in the corresponding suites.
5. Ensure fixture admin can clean up while app users never hold admin credentials.

### Step 3 — Run Positive Cases

- Valid credentials/authSource connect cleanly.
- Reader reads authorized collections.
- Writer writes required fields/collections.
- Tenant A reads/writes Tenant A data accurately.
- Public APIs return only approved fields.

### Step 4 — Run Negative Cases

- Wrong password/authSource fails auth.
- Missing roles or insufficient privileges fail operations.
- Cross-database/collection access denied.
- Cross-tenant GET/PATCH/DELETE/list/export denied.
- Unsafe input shapes rejected by validation.
- Invalid TLS certificates rejected.
- Sensitive fields and secrets absent from responses/logs.

### Step 5 — Verify Evidence

```text
PASS requires:
  expected result
  actual result
  correct failure layer
  no unauthorized data mutation
  sanitized test logs
```

A request that failed due to a network timeout must never be marked PASS for authorization denial.

### Step 6 — Cleanup

- Delete fixtures matching the database/`testRunId`.
- Remove temporary test secrets and IP access list entries.
- Purge sensitive dumps, CSVs, and test artifacts per policy.
- Revoke temporary admin or CI runner privileges.
- Confirm cleanup did not affect out-of-scope data.

## 49. Release Gate Criteria

A system may define gates such as:

| Gate | Condition |
| --- | --- |
| AuthN | Valid logins pass; invalid logins fail at the right layer |
| Database RBAC | All allow/deny expectations in the role matrix pass |
| Tenant isolation | Zero cross-tenant reads/writes across key endpoints |
| Data minimization | Public API schemas expose no sensitive fields |
| Secret hygiene | No secrets found in scanned repositories, logs, or artifacts |
| TLS/network | Deployment complies with approved policy |
| Data encryption | Required at-rest/client-side controls configured with evidence |
| Backup | Access, encryption, retention, and restore policies verified |
| Audit | Sensitive operations emit compliant events |
| Cleanup | No expired temporary users, entries, or fixtures remain |

**Any failing security gate must follow severity triage and risk acceptance processes**, never silenced as "flaky" and ignored. At the same time, distinguish test-infrastructure errors from genuine control violations; do not raise false "unsafe production" alarms over a missing test fixture.

## 50. Common Misconceptions

| Statement | Why It Is Incorrect | Correct Understanding |
| --- | --- | --- |
| "Being able to ping MongoDB means read access works" | `ping` does not prove collection privileges | Test actual collection operations |
| "AuthN success means AuthZ is right" | The identity may hold overly broad roles | Run negative RBAC tests |
| "App uses MongoDB `readWrite` so Tenant A can't read B" | DB roles know nothing about HTTP tenants | Enforce app scoping/authorization |
| "Running all tests as root is good enough" | Does not verify least privilege | Test with realistic service identities |
| "A failed insert proves access denial" | Could be duplicate key or network failure | Assert authorization cause and zero mutation |
| "One wrong-password test proves brute-force protection" | Only tests a single negative auth attempt | Verify dedicated rate-limiting/monitoring policies |
| "Enabling TLS makes the connection secure" | Hostname verification might be disabled | Run negative certificate validation tests |
| "IP Access Lists replace passwords" | Network filtering differs from AuthN | Use defense in depth across layers |
| "A private endpoint means the API won't leak PII" | Network routing does not enforce output minimization | Use DTOs, projections, and masking |
| "Enabling storage encryption hides plaintext from readers" | Server decrypts for authorized queries | Combine RBAC with CSFLE where needed |
| "Base64 is encryption" | Provides zero cryptographic secrecy | Use real encryption |
| "CSFLE replaces tenant RBAC" | Key access and document ownership differ | Design and test both controls |
| "Collection validators enforce user permissions" | Schema validators don't know the HTTP principal | Implement separate authorization checks |
| "Search endpoints don't need tenant filters" | Can still leak lists and aggregates | Scope every data path |
| "Fields omitted from API responses are safe in logs" | Logging may dump raw entities | Add log redaction negative tests |
| "Backups aren't live data so they're less sensitive" | Backups can contain complete PII datasets | Enforce ACLs, encryption, and retention |
| "TTL deletes immediately and also wipes backups" | TTL is asynchronous and never edits existing backups | Build explicit deletion/retention workflows |
| "A project admin is a MongoDB database user" | Atlas project roles differ from DB users | Provision and test the right control |
| "Accepting `tenantId` from the client determines access" | Clients can forge `tenantId` | Derive tenant scope from the authenticated principal |
| "GET checks tenant so UPDATE by ID is safe" | Race window and unscoped updates expose cross-tenant writes | Include tenant and state in the write predicate |
| "Decoding a JWT payload means it is valid" | Must verify signatures and claims | Enforce Spring Security validation |
| "No PII in fixtures means redaction tests pass" | Never exercises redaction code paths | Seed synthetic sensitive fields |
| "Negative tests should run in production" | Misconfigured roles cause real mutations | Always use disposable environments |

## 51. Exercises with Answers

### Exercise 1. AuthN vs. AuthZ

A MongoDB user logs in successfully, then `insertOne()` fails with `Unauthorized`. What succeeded and what failed?

**Answer:** AuthN succeeded, and AuthZ denied the operation because the user lacks the required privilege. Never "fix" this by disabling auth or opening firewalls.

### Exercise 2. `authSource`

A user is created in `security_lab`. The URI uses `authSource=admin` with the right password, yet authentication fails. What should you check?

**Answer:** Which auth database holds the user identity. If the user only exists in `security_lab`, set `authSource=security_lab`.

### Exercise 3. Reader Privileges

A service only needs to read orders, yet holds `readWrite` across `security_lab`. An `insertOne()` test succeeds. Conclusion?

**Answer:** The role is broader than required; the least-privilege negative test failed. Narrow it to a properly scoped read-only role.

### Exercise 4. Database Role vs. Collection Scope

Does the `read` role on `security_lab` guarantee reading only the `orders` collection?

**Answer:** No. Built-in database roles grant read access across the database. Restricting access solely to `orders` requires a custom role or architectural separation.

### Exercise 5. False-Positive Negative Test

A denial test asserts any `MongoException`. When the database is unreachable, the test passes. What is wrong?

**Answer:** A network failure does not prove authorization denial. Add a positive connectivity precondition, assert the `Unauthorized` cause/code, and verify zero data mutation.

### Exercise 6. `MongoClient`

`MongoClients.create(uri)` throws no error when the password is wrong. Does that mean authentication succeeded?

**Answer:** No. Drivers may defer connection/authentication until the first command executes. Always run a real command.

### Exercise 7. Tenant ID

An API accepts `?tenantId=tenant-b` from a Tenant A user and uses it directly in a MongoDB filter. What is the risk?

**Answer:** The client can spoof the tenant scope. Always derive the tenant from the authenticated principal or explicitly verify cross-tenant delegation permissions.

### Exercise 8. Cross-Tenant GET

User A receives Order B when supplying B's ID. What vulnerability is this?

**Answer:** Broken Object Level Authorization (BOLA/IDOR). Enforce tenant/owner predicates in queries and principal-based authorization checks.

### Exercise 9. Cross-Tenant PATCH

The GET endpoint enforces tenant scope, but PATCH queries only by `_id`. Is the endpoint secure?

**Answer:** No. Updates must also include tenant, owner, and business-state predicates and verify the matched count.

### Exercise 10. Fixtures

A test asserts "response does not leak `internalNotes`" using fixtures that never contained `internalNotes`. Is this reliable?

**Answer:** No. Seed a synthetic sensitive value and verify the response actually strips that field and value.

### Exercise 11. MongoDB Roles vs. HTTP Roles

Spring Boot uses a single `readWrite` MongoDB service user for all HTTP requests. Does MongoDB automatically distinguish Alice from Bob?

**Answer:** Not by default. The database sees only the service identity. The application must enforce HTTP principal and tenant/owner authorization rules.

### Exercise 12. Projections

An API projects only `displayName` but omits the tenant filter from the query. Is it secure?

**Answer:** No. Projections restrict fields, not who can access which documents.

### Exercise 13. NoSQL Injection

An API expects an `email` string yet accepts a JSON object containing `$ne` and embeds it directly into a filter. How should this be fixed?

**Answer:** Validate DTO fields strictly as strings, build typed driver filters, and reject unexpected operator-shaped inputs.

### Exercise 14. TLS

A client disables certificate hostname validation so tests always pass. Is this a valid positive TLS security test?

**Answer:** No. You must validate certificates, CAs, and hostnames properly, and include negative tests rejecting invalid certificates.

### Exercise 15. Atlas Networking

A CI Pod with private IP `10.2.1.5` reaches the Internet via NAT IP `198.51.100.24`. Which IP should the public IP Access List use?

**Answer:** The public egress IP after NAT along that connection path — `198.51.100.24` in this example (for illustration only).

### Exercise 16. Private Endpoint

A private endpoint exists, yet the app still uses a public URI resolving to public hosts. Can you claim traffic is private?

**Answer:** No. Verify the URI, private DNS resolution, routing, and actual endpoint in use.

### Exercise 17. Encryption at Rest

An authorized MongoDB user queries plaintext documents. Does this prove the disk is unencrypted?

**Answer:** No. The server decrypts data for authorized reads; at-rest encryption must be verified via storage/KMS configuration and operational evidence.

### Exercise 18. CSFLE

A field is base64-encoded before writing. Is that valid CSFLE?

**Answer:** No. Base64 is encoding, not encryption. Proper CSFLE requires real cryptography, key management, and encrypted BSON representations.

### Exercise 19. Secrets in Logs

The application never returns passwords in HTTP responses, yet logs the full `MongoDB URI` containing the password on error. Does it pass data protection tests?

**Answer:** No. Secrets leaked through logs; enforce masking/redaction, secret managers, and negative log checks.

### Exercise 20. HTTP 404/403

An API returns 403 for Order B and 404 for nonexistent IDs. What information could leak?

**Answer:** Attackers can enumerate whether resources exist. Depending on policy, return 404 consistently for cross-tenant resources.

### Exercise 21. TTL

A token expires at 12:00. Must the TTL monitor delete it at 12:00:00.000 sharp?

**Answer:** No. TTL cleanup is asynchronous; tests must include time tolerance and align with retention requirements.

### Exercise 22. Backups

MongoDB RBAC is strict, yet a `mongodump` archive is uploaded to a public bucket. Is there still a vulnerability?

**Answer:** Yes. Backups hold sensitive data and require strict ACLs, encryption, retention policies, and dedicated monitoring.

### Exercise 23. Auditing

MongoDB logs record only the `orders-api` service user. How do you know which HTTP user viewed Order B?

**Answer:** Implement application-level audit logging with `actorId`, tenant, operation, resource, and `correlationId`; the MongoDB service identity does not automatically propagate HTTP principals.

### Exercise 24. Caching

Repository queries enforce tenant scope, yet the cache key uses only `orderId` and is shared across users. What is the risk?

**Answer:** Cross-tenant leaks through the cache due to missing scope or skipped authorization rechecks. Test both cache misses and cache hits with different principals.

### Exercise 25. CI

A CRUD suite passes on a MongoDB container running without authentication. Does that prove production MongoDB RBAC is correct?

**Answer:** No. You need a dedicated suite running against an auth-enabled MongoDB deployment with real users, roles, and negative assertions.

### Exercise 26. Admin Commands

The orders service can execute `dropCollection` because it was granted an admin role for easier migrations. Does this follow least privilege?

**Answer:** Usually not. Separate migration/DBA identities from runtime service accounts, and verify tests prove runtime accounts cannot drop collections.

### Exercise 27. Aggregation

Tenant A's report counts 7 orders because the pipeline omits `$match`; fixtures have 2 for Tenant A and 5 for Tenant B. What bug is this?

**Answer:** An aggregation/tenant-scoping leak. Add the proper authorization filter and assert the expected count of 2.

### Exercise 28. Credential Rotation

After password rotation, new clients succeed with V2 while an existing connection pool continues operating. Can you conclude V1 is completely revoked?

**Answer:** Not yet. Test fresh connections, pool lifecycle draining, and cutover/revocation policies rather than relying on an already-established session.

### Exercise 29. Negative Query Tests

An insert attempt by a reader throws a duplicate key error. Does this prove the reader lacks write privileges?

**Answer:** No. If execution reaches duplicate key detection, authorization denial did not behave as expected. Use unique fixtures and assert server `Unauthorized`.

### Exercise 30. Release Gates

Functional tests pass, yet a cross-tenant PATCH test updates Tenant B's resource. Can the release ship normally?

**Answer:** No. This is a critical authorization violation; handle it through severity triage/release gates and verify denial plus zero mutation before shipping.

## 52. Practical Checklist

### Authentication and Network

- [ ] Real test MongoDB deployment has authentication enabled.
- [ ] Valid credentials/authSource connect cleanly.
- [ ] Invalid/missing credentials cannot access protected data.
- [ ] Auth tests do not false-pass due to DNS/TLS/network failures.
- [ ] TLS certificate chain and hostname verification are validated.
- [ ] No `tlsInsecure` or verification bypasses exist in production configs.
- [ ] Atlas public egress / private endpoint routing matches approved paths.

### Database Authorization

- [ ] Dedicated service users exist with minimal privileges.
- [ ] Allow/deny matrix covers operations and resources.
- [ ] Tests use **real users**, never running every test as root.
- [ ] Readers cannot insert/update/delete/drop.
- [ ] Writers cannot manage users or schemas unnecessarily.
- [ ] Cross-database/collection access is denied per scope.
- [ ] Negative tests assert the `Unauthorized` cause, not just any exception.
- [ ] Data remains unchanged after denied writes.

### Application Authorization

- [ ] HTTP principals, roles, and tenants are authenticated.
- [ ] Queries use principal tenant/owner rather than trusting arbitrary client `tenantId`.
- [ ] GET/list/search/pagination/reports/exports all enforce scoping.
- [ ] PATCH/DELETE/bulk ops include authorization predicates in write filters.
- [ ] Tests cover cross-tenant, owner mismatch, anonymous, and role mismatch cases.
- [ ] Caches, files, notifications, and background jobs honor access policies.
- [ ] Error statuses do not disclose resource existence against policy.

### Sensitive Data

- [ ] Public APIs use DTO allowlists and projections.
- [ ] Fixtures include synthetic sensitive fields to test redaction.
- [ ] Logs, metrics, and traces omit passwords, tokens, raw URIs, and out-of-policy PII.
- [ ] Secrets come from secret managers and are rotated.
- [ ] Encryption in transit, at rest, and field-level controls are verified per requirements.
- [ ] Backups, restores, and exports enforce ACLs, encryption, and retention.
- [ ] Audit logs record required events without excessive sensitive data.
- [ ] TTL/deletion workflows and test-artifact cleanup are verified.

### Test Operations

- [ ] Security tests run in isolated environments with synthetic data.
- [ ] Each test uses unique IDs, scoped fixtures, and explicit cleanup.
- [ ] CI never exposes credentials or production dumps.
- [ ] Positive preconditions precede negative assertions.
- [ ] Sanitized evidence is reviewed and approved by owners.
- [ ] Critical security gates are never bypassed as "flaky infra."

## 53. Summary

MongoDB security testing goes far beyond creating a `MongoClient` and running `ping`. A sound system must verify **valid network/TLS connectivity**, **accurate identity authentication**, **MongoDB RBAC enforcing granted-only actions**, and **application authorization bounding tenant/owner/business scope**. On every write path, negative tests must also confirm **zero data mutation**.

In Java/Spring Data MongoDB applications, realistic testing should use **dedicated service identities** against an auth-enabled MongoDB deployment, DTOs/projections for sensitive data minimization, strongly typed filters to prevent operator injection, and authenticated-principal scoping across GET, PATCH, DELETE, aggregations, and exports. A collection read/write DB role alone neither isolates tenants nor strips sensitive fields from APIs.

For data protection, **TLS, encryption at rest, CSFLE, secret management, auditing, backup retention, and log redaction** are complementary controls rather than substitutes for one another. A negative test is only meaningful when it fails **for the right reason**, not due to broken connectivity or missing fixtures.

An effective workflow follows **security requirements -> permission matrix -> contrasting fixtures -> positive/negative integration tests -> data/log verification -> cleanup -> release gate**. Only by explicitly testing what **must not be permitted** can engineering teams confidently demonstrate that MongoDB data is protected according to policy.

### Official References

- [MongoDB Manual — Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/)
- [MongoDB Manual — Authentication](https://www.mongodb.com/docs/manual/core/authentication/)
- [MongoDB Manual — Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- [MongoDB Manual — User-Defined Roles](https://www.mongodb.com/docs/manual/core/authorization/#user-defined-roles)
- [MongoDB Manual — createRole](https://www.mongodb.com/docs/manual/reference/method/db.createRole/)
- [MongoDB Manual — createUser](https://www.mongodb.com/docs/manual/reference/method/db.createUser/)
- [MongoDB Manual — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/)
- [MongoDB Atlas — IP Access List](https://www.mongodb.com/docs/atlas/security/ip-access-list/)
- [MongoDB Manual — TLS/SSL](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/)
- [MongoDB Manual — Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/csfle/)
- [MongoDB Atlas — Back Up and Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)

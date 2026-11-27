# Auditing Least Privilege and Testing Denied Access Scenarios

In Neo4j, a service may need to read `:Order` nodes and `:PLACED` relationships, yet it **must not** thereby gain permission to read employee salaries, delete the entire graph, or administer accounts. The **principle of least privilege** requires each identity to hold only the privileges needed for the right task, database, graph objects, and timeframe.

This lesson belongs to the **Security** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The module uses Neo4j to model property graphs, run Cypher queries, define indexes/constraints, import data, and connect via Java Driver or Spring Data Neo4j (SDN). Security must be verified against the **actual queries and transactions executed by those applications**: data read privileges, write privileges, procedure execution privileges, and visibility of sensitive labels/properties.

Merely reading a permission table is not enough. Testing must simultaneously prove:

- **Allowed:** valid business operations still read/write expected results.
- **Denied:** ungranted operations cannot execute.
- **No data leakage:** hidden properties or nodes never appear in results, even when the query throws no error.
- **No side effects:** after a denied access attempt, critical data remains intact.

> **Scope:** Fine-grained privilege examples in this lesson target **Neo4j Enterprise Edition 5.x** supporting role-based access control (RBAC) and fine-grained graph privileges. Neo4j Community Edition does not provide the full equivalent role/privilege mechanism; Neo4j Aura also depends on service tier and governance policies. Verify documentation for your **exact version, edition, and environment** before deploying. Run user-administration commands and intentional negative tests only on an **isolated practice database**.

## 1. Learning objectives

After this lesson, you will be able to:

1. Enumerate the privileges required along a business path from **API → Java Driver/SDN → Cypher → graph**.
2. Distinguish database `ACCESS`, node/relationship `TRAVERSE`, property `READ`, `MATCH`, write privileges, and procedure execution privileges.
3. Audit **effective privileges** across multiple roles, the `PUBLIC` role, and `GRANT`/`DENY` rules.
4. Distinguish a **permission error** from an **empty/`null` result caused by hidden data**.
5. Build a matrix of **positive tests** and **negative tests**, checking data before and after denied write attempts.
6. Test against real Neo4j via Java Driver using **two distinct identities**, and identify risks around accounts, logs, Cypher parameters, APOC, and privilege drift over time.

## 2. Least privilege is a property of the *executing identity*

A Spring Data Neo4j application may name a repository `OrderRepository`, yet Neo4j **does not decide permissions based on class names**. Access decisions depend on the **authenticated identity**, the selected database, and that identity's effective roles/privileges.

~~~mermaid
flowchart LR
    API["REST API / Scheduled job"] --> APP["Service + Java Driver / SDN"]
    APP --> CRED["Neo4j identity"]
    CRED --> ROLES["Assigned roles<br/>including PUBLIC"]
    ROLES --> POLICY["GRANT / DENY<br/>by DB, node, relationship, property"]
    POLICY --> Q["Cypher / procedure"]
    Q --> DATA["Visible data<br/>or allowed operation"]
~~~

**Questions to answer before granting privileges:**

| Question | Example |
|---|---|
| **Who** executes the query? | `order-api-reader`, `order-api-writer`, `schema-migrator` |
| **On which database?** | Only the test environment's `neo4j` database, not every database |
| **Which objects?** | `:SecCustomer`, `:SecOrder` nodes, `:PLACED` relationship |
| **Which properties?** | `customerId`, `orderId`, `amount`; excluding `email`, `internalNote` |
| **Which actions?** | Traverse links, read a few properties, or update order status? |
| **Need procedures/admin?** | An order-reading service normally needs no user creation, DB drop, or file-access plugins |
| **When to revoke?** | When the feature retires, the service moves, or the deployment window ends |

Never share a `neo4j`/admin account across all microservices. With an overly broad account, an app bug, Cypher injection, or leaked credential can impact data far outside business boundaries.

### Defense layers do not replace one another

- **Authentication:** verifies who is connecting; wrong passwords/tokens/certificates fail before running Cypher.
- **Authorization:** decides what that identity may read, write, or administer. Successful login **does not mean** every command is allowed.
- **Schema constraints:** enforce uniqueness or data types, **not** which users may view a property.
- **Application validation:** decides whether an operation is valid in business terms, **not** a substitute for Neo4j database privileges.
- **Encrypted connections/TLS:** protects traffic in transit; does not replace RBAC.

## 3. Neo4j privilege types to distinguish

Neo4j defines privileges at multiple scopes. Examples below use **Enterprise RBAC** and a database named `neo4j`.

| Group | Practical meaning | What happens if missing? |
|---|---|---|
| `ACCESS ON DATABASE` | Permits identity to access the selected database | Cannot select or run queries on that DB |
| `TRAVERSE ON GRAPH ... NODES ...` | Permits traversing/seeing nodes by label | Nodes may **not appear** in results |
| `TRAVERSE ON GRAPH ... RELATIONSHIPS ...` | Permits traversing relationships by type | `MATCH` patterns may find no path |
| `READ {property} ON GRAPH ...` | Permits reading granted properties | Hidden properties may return `null` |
| `MATCH {property} ON GRAPH ...` | Shorthand for `TRAVERSE` plus matching `READ` | Sees only permitted nodes/relationships and properties |
| `WRITE` or fine-grained write rights | Permits creating/deleting nodes/relationships or setting properties in scope | Disallowed writes are rejected |
| `EXECUTE PROCEDURE` / `EXECUTE FUNCTION` | Permits calling DBMS-level functions/procedures | Calls requiring execution rights are denied |
| `EXECUTE BOOSTED PROCEDURE` | Permits running procedures with elevated privileges per config | Never grant broadly; expands blast radius beyond task scope |
| DBMS/database admin rights | Creating users, roles, databases, managing privileges, etc. | Business services normally **do not need** these |

`GRANT MATCH {orderId, amount} ON GRAPH neo4j NODES SecOrder TO some_role` grants **read and traversal** on `SecOrder` nodes for those specific properties. It **grants no write privileges**.

A crucial testing rule:

> **Missing read privilege ≠ always throwing an exception.** Without `TRAVERSE`, `MATCH` can return **0 rows** even though an admin sees the node. Without `READ` on a property, `n.secret` can return **`null`**. Conversely, disallowed writes, database access, or procedure calls typically raise a security error. Tests must assert the **actual runtime semantics** for each case.

### Roles, `PUBLIC`, and `DENY`

A user can hold **multiple roles**. `GRANT`s from roles combine; an applicable `DENY` generally **takes precedence** over a conflicting `GRANT` under Neo4j authorization rules. The **`PUBLIC`** role applies to every user and can carry default grants; **never inspect only your team's custom role** and conclude the user holds no other privileges.

For example, if `order_reader` only grants reading `orderId` while another role on the same user grants reading all properties, tests using that user will see more data than expected. Audit **effective user privileges** rather than reading a single `GRANT` line in a deployment script.

## 4. Defining the test scenario

Suppose an **Order API** uses two identities:

- `qa_order_reader`: reads customer ID, order ID, and amount; must **not** read email/internal notes, update orders, or view payroll data.
- `qa_order_writer`: a separate identity for scoped business writes; holds no default schema or user-admin rights.

In this exercise, we focus on verifying `qa_order_reader`. Expected graph data:

~~~mermaid
flowchart LR
    C["SecCustomer<br/>customerId=C01<br/>email=an@example.test"]
    O["SecOrder<br/>orderId=O01<br/>amount=120000<br/>internalNote=VIP"]
    P["SecPayroll<br/>payrollId=P01<br/>salary=45000000"]
    C -->|PLACED| O
    P -.->|"Outside Order API scope"| P
~~~

Run the setup below **only with an admin account on the test database**:

~~~cypher
// Run on the neo4j database of the test environment.
MERGE (c:SecCustomer {customerId: 'C01'})
SET c.email = 'an@example.test',
    c.name = 'An'
MERGE (o:SecOrder {orderId: 'O01'})
SET o.amount = 120000,
    o.internalNote = 'VIP'
MERGE (c)-[:PLACED]->(o)
MERGE (p:SecPayroll {payrollId: 'P01'})
SET p.salary = 45000000;
~~~

Verify with the **admin** account to confirm the fixture genuinely exists:

~~~cypher
MATCH (c:SecCustomer {customerId: 'C01'})-[:PLACED]->
      (o:SecOrder {orderId: 'O01'})
MATCH (p:SecPayroll {payrollId: 'P01'})
RETURN c.email AS email,
       o.amount AS amount,
       o.internalNote AS internalNote,
       p.salary AS salary;
~~~

Expected result: email `an@example.test`, amount `120000`, note `VIP`, and salary `45000000`.

**Why require an admin verification step?** If the reader test returns `null` for email or 0 payroll nodes, it could simply be **because the source data is absent**, rather than RBAC working. A positive fixture check with a privileged identity prevents "false-green tests."

## 5. Designing a role that reads only the required data

This section uses **Neo4j Enterprise**. `CREATE USER`/`CREATE ROLE`/`GRANT` require appropriate admin privileges and run on the **system database**; `MATCH` data queries run on the **business database**.

### 5.1. Creating the test role and user

On the `system` database, an authorized account runs:

~~~cypher
// SYSTEM DATABASE - run with appropriate admin privileges.
CREATE ROLE qa_order_reader_role IF NOT EXISTS;
~~~

~~~cypher
// PASSWORD supplied from a secure variable/parameter of the test environment.
CREATE USER qa_order_reader IF NOT EXISTS
SET PASSWORD $testPassword
CHANGE NOT REQUIRED;
~~~

~~~cypher
GRANT ROLE qa_order_reader_role TO qa_order_reader;
~~~

**Never use example passwords in production.** In real applications, inject credentials from a secret manager or secure environment, enable proper TLS, and govern query/parameter logging. Parameterizing user creation here avoids hard-coding passwords in Cypher strings; still verify logging policies.

### 5.2. Granting database and graph object privileges

These statements also run on the **system database**:

~~~cypher
GRANT ACCESS ON DATABASE neo4j TO qa_order_reader_role;

GRANT MATCH {customerId}
ON GRAPH neo4j NODES SecCustomer
TO qa_order_reader_role;

GRANT MATCH {orderId, amount}
ON GRAPH neo4j NODES SecOrder
TO qa_order_reader_role;

GRANT TRAVERSE
ON GRAPH neo4j RELATIONSHIPS PLACED
TO qa_order_reader_role;
~~~

Intent:

1. The user can access the **`neo4j` database**.
2. Can read **`customerId`** on `SecCustomer` nodes, but not `email` or `name` via this role.
3. Can read **`orderId` and `amount`** on `SecOrder`, but not `internalNote` via this role.
4. Can traverse `PLACED` relationships to determine which customer placed which order.
5. Receives no read access on `SecPayroll`, no `WRITE`, and no admin privileges via this role.

**Do not confuse "not granted" with "guaranteed denied":** **another** role (including inherited rights) could still grant the privilege. Tests must use a real account with its **combined effective privileges** and confirm the user holds no unintended roles.

### 5.3. When to use an explicit `DENY`?

An explicit `DENY` helps when a shared role grants broad reads yet a sensitive property must be blocked:

~~~cypher
// Run on system; example when policy requires explicit blocking.
DENY READ {email}
ON GRAPH neo4j NODES SecCustomer
TO qa_order_reader_role;
~~~

Crucial point: **a deny policy applies only to its defined privilege scope and semantics**; it does not replace auditing all roles and indirect paths. For greenfield roles, **granting only the needed properties** is usually simpler to maintain than granting broadly and stacking `DENY`s. When applying a deny, test its impact on real queries and procedures before rollout.

## 6. Auditing effective privileges before testing

On the **system database**, an appropriately privileged administrator checks:

~~~cypher
SHOW USERS
YIELD user, roles, suspended
WHERE user = 'qa_order_reader'
RETURN user, roles, suspended;
~~~

~~~cypher
SHOW ROLE qa_order_reader_role PRIVILEGES AS COMMANDS;
~~~

~~~cypher
SHOW USER qa_order_reader PRIVILEGES AS COMMANDS;
~~~

When reading the output, verify:

- The user is **not suspended** and holds **only the intended roles**.
- `ACCESS` targets only the right database, not an accidental `ACCESS ON DATABASE *` if the service needs just one.
- Read privileges match the exact labels/types/properties, with no unintended `SecPayroll` reads.
- Zero unnecessary `WRITE`, admin, or out-of-scope sensitive procedure execution rights.
- Neither `PUBLIC`, built-in roles, nor extra roles **widen effective privileges** beyond plan.
- Any `DENY` blocks the exact target without breaking valid statements.

`SHOW ROLE ... PRIVILEGES` describes a **single role**; `SHOW USER ... PRIVILEGES` inspects effective privileges for a **user**. Never cite a single role's privilege list as proof of a real user's effective rights.

## 7. Allowed / denied test matrix

To evaluate least privilege, define **expected outcomes** before running tests. Here is the matrix for `qa_order_reader` after configuring privileges and ensuring no excess rights exist.

| Scenario | Tested by | Expectation | How to verify |
|---|---|---|---|
| Read `SecOrder.orderId` and `amount` | Reader | **Allowed**, returns one order | Compare against admin data |
| Traverse `SecCustomer-[:PLACED]->SecOrder` | Reader | **Allowed**, returns `C01/O01` pair | Verify keys and edge direction |
| Read `SecCustomer.email` | Reader | Hidden; typically `null` | Admin confirms email exists |
| Read `SecOrder.internalNote` | Reader | Hidden; typically `null` | Admin confirms note exists |
| `MATCH` `SecPayroll` nodes | Reader | **Invisible**, typically 0 rows | Admin confirms 1 node |
| `SET o.amount = ...` | Reader | **Rejected** with authorization error | Admin verifies amount unchanged |
| `DELETE` order node | Reader | **Rejected** without write/delete rights | Admin confirms node/edge remain |
| Create role/user or administer DB | Reader | **Rejected** due to missing admin rights | No new role/user exists |
| Call sensitive procedure | Reader | Per granted `EXECUTE` list; denied if unpermitted | Check server procedure/privilege list |

**Never write a single blanket assertion like "every unauthorized access must throw `ClientException`."** A `MATCH` blocked from traversing returns **fewer rows**, while a restricted property can return **`null`**. Set expectations per privilege semantic.

## 8. Test 1 — Valid queries must succeed

Connect to database `neo4j` using **`qa_order_reader` credentials**, not admin:

~~~cypher
MATCH (c:SecCustomer {customerId: 'C01'})
      -[:PLACED]->(o:SecOrder)
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       o.amount AS amount
ORDER BY orderId;
~~~

With Section 4's fixture, expected output:

| customerId | orderId | amount |
|---|---|---:|
| C01 | O01 | 120000 |

If the query returns no rows, do not immediately blame "missing `READ`." Check database `ACCESS`, `TRAVERSE` on **both node labels and the relationship**, inherited roles, and fixture data. When any hop is blocked from traversal, the entire pattern may fail to match even though nodes exist.

## 9. Test 2 — A hidden property is not a deleted property

Still using the reader account:

~~~cypher
MATCH (c:SecCustomer {customerId: 'C01'})
RETURN c.customerId AS customerId,
       c.email AS email;
~~~

Expectation: `C01` is returned, while `email` is `null` or unreadable per version privilege policy, whereas an admin query:

~~~cypher
MATCH (c:SecCustomer {customerId: 'C01'})
RETURN c.email AS email;
// Admin expects 'an@example.test'
~~~

**Assert both facts simultaneously:**

1. Admin confirms the sensitive value **genuinely exists**.
2. Reader **cannot retrieve the sensitive value**, even though it can read the public ID.

In Cypher, `null` can also indicate an absent property. Thus checking `email IS NULL` solely in a reader session **does not prove** the policy protected the data.

Beyond dot-property access, test `properties(c)`, map projections, and SDN-generated queries. A sound policy protects data at Neo4j's authorization layer rather than merely hiding a UI column.

## 10. Test 3 — Blocked nodes/relationships can yield empty results

With the reader account:

~~~cypher
MATCH (p:SecPayroll)
RETURN count(p) AS payrollNodes;
~~~

Expectation: `payrollNodes = 0` when the identity cannot traverse `SecPayroll` and no other role permits it. With admin:

~~~cypher
MATCH (p:SecPayroll)
RETURN count(p) AS payrollNodes;
// Admin expects 1 per fixture.
~~~

This is **privilege-based filtering**, not necessarily an exception. If an application confuses "does not exist" with "not visible," the API can return misleading messages. In many systems, returning "not found or unauthorized" is also chosen intentionally to **avoid leaking resource existence**.

Similarly, if `SecCustomer` and `SecOrder` are visible while `PLACED` lacks `TRAVERSE`, `MATCH (c)-[:PLACED]->(o)` may return zero rows. Never grant access to all relationships just to pass a test; revisit business needs and the access model.

## 11. Test 4 — Denied writes must leave zero side effects

First, admin reads the initial state:

~~~cypher
MATCH (o:SecOrder {orderId: 'O01'})
RETURN o.amount AS amount;
// 120000
~~~

Reader attempts a write:

~~~cypher
MATCH (o:SecOrder {orderId: 'O01'})
SET o.amount = 999999
RETURN o.orderId AS orderId;
~~~

Because the reader role has no write privileges, this transaction must **fail to modify `amount`**. In standard Neo4j RBAC configs, the write is rejected with a security error, such as under `Neo.ClientError.Security.*`.

Then admin queries again:

~~~cypher
MATCH (o:SecOrder {orderId: 'O01'})
RETURN o.amount AS amount;
// Must still be 120000.
~~~

Checking only "reader threw an exception" without **re-reading graph state** can miss transaction-boundary bugs or concurrent writes. When a test involves multiple statements, verify they execute within **one transaction** before claiming full rollback.

### Denied access vs. constraint errors

If an authorized writer tries to create two `SecOrder` nodes sharing the same `orderId` under a uniqueness constraint, the error is a **schema violation**, not an authorization failure. Keep **authorization negative tests** separate from **constraint negative tests** rather than treating every `ClientException` as `FORBIDDEN`.

## 12. Test 5 — Disallowing privilege escalation via admin/procedures

An order-reading app account **never needs** `CREATE USER`, `CREATE ROLE`, `GRANT`/`DENY`, database management, or sensitive admin procedures.

With the reader user on an isolated Enterprise environment, try running a benign-intent admin query:

~~~cypher
SHOW USERS;
~~~

What this returns depends on **SHOW USER** privileges, Neo4j version, and database context. If the reader can enumerate unnecessary admin metadata, audit granted privileges; if denied, the app must handle the error cleanly rather than falling back to an admin account.

**Never run destructive statements like `CREATE USER` or `DROP DATABASE` in default negative tests** just to test permissions. If an environment is misconfigured and the user accidentally has rights, the test mutates real state. Use controlled `SHOW` queries or inspect effective privileges from an admin account instead.

### Procedures and plugins

Inspect installed procedure names/privileges using an admin or view-privileged account:

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'apoc.'
RETURN name
ORDER BY name
LIMIT 30;
~~~

Evaluate procedures capable of:

- Reading/writing files or calling URLs (`apoc.load.*`, exports, etc.).
- Executing dynamic Cypher with sensitive settings.
- Performing admin actions or running with elevated privileges.
- Accessing other databases or data outside the API's scope.

**Holding `EXECUTE PROCEDURE` does not mean every procedure can bypass graph boundaries.** You must also check **graph privileges**, allowlists, unrestricted/boosted procedures, and server security settings. Still, granting broad procedure rights and relying on "the app won't call it" is weak—**restrict directly inside Neo4j**.

## 13. Testing two identities with the Java Driver

To prove authorization, tests must **actually connect using the restricted account**. Running all queries as admin makes tests green without proving application-account safety.

### 13.1. Test environment setup

Consider **JUnit 5 + Testcontainers + Neo4j Enterprise Edition** under appropriate license terms. Provision privileges, users, roles, and fixtures in an isolated setup step. Then open two `Driver`s:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

// URI and password loaded from test/secret config; never hard-code production credentials.
Driver adminDriver = GraphDatabase.driver(
    boltUri, AuthTokens.basic("neo4j", adminPassword));

Driver readerDriver = GraphDatabase.driver(
    boltUri, AuthTokens.basic("qa_order_reader", readerPassword));

// Specify an explicit database to avoid home-database dependency.
SessionConfig graphDb = SessionConfig.forDatabase("neo4j");
~~~

This is an **illustrative setup snippet**, not a standalone Java file. Provisioning roles/users must complete **before opening reader sessions or running tests**; with Testcontainers, this typically happens in bootstrap setup or `@BeforeAll`.

### 13.2. Positive test: reader reads public summary info

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

@Test
void readerCanReadOrderSummary() {
    try (Session session = readerDriver.session(graphDb)) {
        var record = session.executeRead(tx -> tx.run("""
            MATCH (c:SecCustomer {customerId: 'C01'})
                  -[:PLACED]->(o:SecOrder)
            RETURN c.customerId AS customerId,
                   o.orderId AS orderId,
                   o.amount AS amount
            """).single());

        assertEquals("C01", record.get("customerId").asString());
        assertEquals("O01", record.get("orderId").asString());
        assertEquals(120000L, record.get("amount").asLong());
    }
}
~~~

This test confirms the reader **has sufficient** privileges for business functionality. Negative tests without positive tests can pass trivially when an account **cannot read anything at all**.

### 13.3. Negative test: hidden property

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

@Test
void readerCannotSeeCustomerEmail() {
    // Admin confirms the real fixture has email.
    try (Session admin = adminDriver.session(graphDb)) {
        var row = admin.executeRead(tx -> tx.run("""
            MATCH (c:SecCustomer {customerId: 'C01'})
            RETURN c.email AS email
            """).single());
        assertEquals("an@example.test", row.get("email").asString());
    }

    // Reader still sees C01, yet cannot read email.
    try (Session reader = readerDriver.session(graphDb)) {
        var row = reader.executeRead(tx -> tx.run("""
            MATCH (c:SecCustomer {customerId: 'C01'})
            RETURN c.customerId AS id, c.email AS email
            """).single());
        assertEquals("C01", row.get("id").asString());
        assertTrue(row.get("email").isNull());
    }
}
~~~

If a particular Neo4j version/config returns an error instead of `null` for that check, verify the authorization semantics of **that version** before adjusting the assertion. The invariant is **the sensitive value never reaches the reader account**.

### 13.4. Negative test: write denied and data unchanged

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.neo4j.driver.exceptions.Neo4jException;

@Test
void readerCannotModifyOrderAmount() {
    try (Session reader = readerDriver.session(graphDb)) {
        Neo4jException error = assertThrows(
            Neo4jException.class,
            () -> reader.executeWrite(tx -> {
                tx.run("""
                    MATCH (o:SecOrder {orderId: 'O01'})
                    SET o.amount = 999999
                    """).consume();
                return null;
            }));

        // Classify precisely via error.code() and exception type
        // per active server/driver; do not match getMessage() strings.
        System.out.println("Expected authorization failure: " + error.code());
    }

    try (Session admin = adminDriver.session(graphDb)) {
        long amount = admin.executeRead(tx -> tx.run("""
            MATCH (o:SecOrder {orderId: 'O01'})
            RETURN o.amount AS amount
            """).single().get("amount").asLong());
        assertEquals(120000L, amount);
    }
}
~~~

**In production-grade tests**, replace `System.out.println` with safe logs/metrics and assert **Security error codes** or matching classifications; the snippet emphasizes reading codes rather than message text. If the test runs with an account holding unintended write privileges, `SET` succeeds and `assertThrows` fails—which is precisely the bug the test exists to catch.

### 13.5. Negative test: hidden label

~~~java
@Test
void readerCannotTraversePayrollNodes() {
    try (Session admin = adminDriver.session(graphDb)) {
        long existing = admin.executeRead(tx -> tx.run("""
            MATCH (p:SecPayroll)
            RETURN count(p) AS n
            """).single().get("n").asLong());
        assertEquals(1L, existing);
    }

    try (Session reader = readerDriver.session(graphDb)) {
        long visible = reader.executeRead(tx -> tx.run("""
            MATCH (p:SecPayroll)
            RETURN count(p) AS n
            """).single().get("n").asLong());
        assertEquals(0L, visible);
    }
}
~~~

Here `visible = 0` is not proof the node is absent; **only the admin check** confirms the source data has one node while reader policy restricts visibility.

### 13.6. Never use admin privileges for every assertion

A system may have `schema-migrator` for indexes/constraints and `order-api-reader` for reads. Tests for `schema-migrator` must stay separate from tests for `order-api-reader`. If a test seeds with admin and then calls repositories with admin too, it **fails to test least privilege** on the application account.

With **Spring Data Neo4j**, point the test configuration to the service's real credential/database, invoke the **actual repository/service**, and then verify graph state via a separate admin connection **after the service transaction has committed or rolled back as intended**.

## 14. Writing automated tests without unintended side effects

Even for intentional denied-access scenarios, tests themselves need isolation and minimal privileges:

| Rule | Reason |
|---|---|
| Use a **dedicated database/container** for privilege tests | Prevents accidentally deleting live users, roles, or production data |
| Provision as admin; execute business paths as restricted user | Separates setup from privilege verification |
| Pair positive and negative tests | Catches both missing privileges and excess privileges |
| Seed fixtures with explicit non-null values | Prevents confusing `null`/0 rows with missing test data |
| Use test-specific user/role/label names | Avoids colliding with production roles |
| Negative write tests assert **before/after state** | Proves zero unintended mutations occurred |
| Never mutate roles mid-run across parallel tests | Prevents flaky results from role updates during live queries |
| Keep real passwords out of source/CI logs | Reduces credential-leakage risk |
| Clean up users/roles/test data only inside test-owned environments | Avoids breaking shared workloads |

**Transaction note:** an admin read in a separate transaction **cannot see uncommitted fixture data**. Commit fixtures before running reader tests; otherwise a "0 rows read" result might reflect **transaction isolation**, not authorization.

### Reliable test execution sequence

~~~mermaid
flowchart TD
    A["Start Enterprise test DB/container"] --> B["Seed fixtures as admin<br/>and COMMIT"]
    B --> C["Provision user/role/grants<br/>on system"]
    C --> D["SHOW USER ... PRIVILEGES<br/>verify effective privileges"]
    D --> E["Positive tests as reader"]
    E --> F["Negative tests: hidden data,<br/>write denied, missing traversal"]
    F --> G["Admin re-reads DB state"]
    G --> H["Report PASS/FAIL + clean up test resources"]
~~~

## 15. Do not configure database privileges cleanly yet leak data in the app

Neo4j RBAC is one defense layer, not a substitute for secure application design. Coordinate checks on these risks:

### 15.1. Never concatenate input directly into Cypher

**Wrong:**

~~~java
String cypher =
    "MATCH (o:SecOrder {orderId: '" + userInput + "'}) RETURN o";
~~~

**Right:** use parameters:

~~~java
var record = session.executeRead(tx -> tx.run("""
        MATCH (o:SecOrder {orderId: $orderId})
        RETURN o.orderId AS id, o.amount AS amount
        """,
        java.util.Map.of("orderId", userInput)
    ).single());
~~~

Parameters separate **values** from Cypher structure. However, labels/types and dynamic structural query clauses may have version-dependent parameter limits; when dynamic structure is needed, use a **server-side allowlist** and test thoroughly—never concatenate arbitrary user strings.

### 15.2. Do not return whole nodes when the API needs only a few fields

If an endpoint only needs `orderId` and `amount`, prefer:

~~~cypher
MATCH (o:SecOrder {orderId: $orderId})
RETURN o.orderId AS orderId, o.amount AS amount;
~~~

instead of returning the entire node `o` and relying solely on a Java DTO to "hide" sensitive fields. Neo4j privileges should prevent the app from reading unneeded properties, while the API serializes only explicitly designed fields.

### 15.3. Separate service identities from migration identities

An order-reading service must not hold privileges to create indexes, constraints, or manage roles just because deployment used one shared account. Separate:

- **Runtime reader:** reads only nodes, relationships, and properties needed by the API.
- **Runtime writer:** scoped write privileges for business operations, never admin.
- **Schema migrator:** creates/alters indexes and constraints within controlled deployment workflows.
- **Security administrator:** creates users/roles and grants/revokes privileges via approval flows.

If a Spring Data Neo4j service runs migrations automatically on startup, weigh the risk of granting long-lived schema privileges to the **runtime identity**; consider moving migrations into a dedicated job.

### 15.4. Protect credentials and logs

The Neo4j Java Driver can connect with URIs like `neo4j+s://` or `bolt+s://` for appropriate TLS verification. Choose the scheme matching your deployment and certificates. Never disable certificate verification just to get past a connection error.

Common data-leak sources:

- Printing `password`/`token` in logs when building `AuthTokens.basic(...)`.
- Capturing PII-bearing Cypher parameters verbatim in query logs or traces.
- Returning raw `Neo4jException.getMessage()` and Cypher text in HTTP responses.
- Putting production credentials into `application.yml` and committing to Git.
- Storing secrets inside transaction metadata or correlation IDs.

Log **error codes, operation names, non-sensitive request IDs**, and latencies; keep secrets in a secret manager, restrict log readers, and enforce log retention.

## 16. Auditing privileges over time and detecting *privilege drift*

A test that passes today can fail later after a migration, a new role, or a `PUBLIC` change alters effective privileges. Least privilege is therefore a **recurring practice**, not a one-time setup.

### Review checklist

1. **Inventory real queries** sent by Java Driver/SDN: which endpoints need which labels/types/properties, and which procedures are actually called?
2. **Map role–identity–database:** users and service accounts, target databases, inherited roles, including `PUBLIC`.
3. **Snapshot effective privileges** via `SHOW USER ... PRIVILEGES AS COMMANDS` from an authorized admin account.
4. **Flag privileges lacking business justification:** `ACCESS ON DATABASE *`, broad `MATCH {*}`, graph-wide write/delete, user/schema admin, boosted procedures.
5. **Run positive/negative test matrices** against a near-production privilege replica using each service's real identity.
6. **Audit new changes:** migrations, plugins/APOC, new labels/properties, new APIs, or accounts granted additional roles.
7. **Revoke unused privileges** through a rollback-ready process, measure impact, and re-run business tests.
8. **Document owner, justification, expiry, and test evidence** for every exceptional privilege.

### Sample audit record template

| Item | Result to record |
|---|---|
| Timestamp, Neo4j version/edition, database | Which environment was audited |
| Identity/role | `qa_order_reader` + effective roles |
| Business query/endpoint | Tested query and sample parameters |
| Required privileges | `ACCESS`, `MATCH/READ/TRAVERSE` matching exact labels/properties |
| Excess rights or conflicting DENY | Evidence from `SHOW PRIVILEGES` |
| Positive test | Did it read C01/O01/120000 accurately? |
| Negative read/traverse tests | Email/note hidden, `SecPayroll` invisible |
| Negative write test | Security error thrown and original amount still 120000? |
| Procedure/admin test | No privileges beyond requirements |
| Conclusion/owner | PASS/FAIL, remediation items, and accountable owner |

**Never mark "PASS" based solely on a list of `GRANT` statements.** Require empirical privilege test data, including the empty/`null` outputs Neo4j uses to conceal restricted objects.

## 17. Practice exercises

### Exercise 1 — Distinguishing three restricted outcomes

Reader runs three queries:

~~~cypher
MATCH (o:SecOrder {orderId: 'O01'})
RETURN o.amount AS amount;
~~~

~~~cypher
MATCH (o:SecOrder {orderId: 'O01'})
RETURN o.internalNote AS note;
~~~

~~~cypher
MATCH (p:SecPayroll)
RETURN count(p) AS total;
~~~

**Question:** If privileges are configured as in Section 5 and the fixture is intact, what are the three expected outputs? Why must you not assert that all three throw exceptions?

**Suggested answer:** The first query returns `120000`; the second hides `internalNote` (typically `null`); the third returns `count = 0` because traversing that label is disallowed. Neo4j filters results by privilege; only certain disallowed operations raise exceptions. Always cross-check real data as admin to distinguish privilege filtering from missing data.

### Exercise 2 — Detecting excess privileges

`SHOW ROLE order_reader PRIVILEGES` shows the role can only read `SecOrder.orderId` and `amount`. Yet the actual user can still read `SecCustomer.email`. Why?

**Suggested answer:** The user likely holds another role (or privileges from `PUBLIC` / another policy) granting broader `TRAVERSE` and `READ`. Run `SHOW USER ... PRIVILEGES`, inspect all roles on the user and relevant `DENY` rules—never rely on one isolated role.

### Exercise 3 — Checking rollback after a denied operation

Reader tries `SET o.amount = 1`. A test only asserts `assertThrows(Neo4jException.class, ...)`. Add two critical assertions.

**Suggested answer:** (1) Assert the **security error type/code**, rather than accidentally catching a syntax or connection error; (2) re-read `o.amount` as admin **after the failed transaction** and verify it remains `120000`. If a job spans multiple steps, verify transaction boundaries before assuming everything rolled back.

### Exercise 4 — Designing two runtime accounts

An application has a `GET /orders/{id}` endpoint and a job updating `Order.status`. Propose a least-privilege split.

**Suggested answer:** Create a reader identity with only `ACCESS` and read privileges on the display labels/properties/paths; create a writer identity permitted to create/update the target objects and properties without default email-read or schema-admin rights. Keep migration and security-admin jobs separate. Write separate positive/negative tests for each identity and ensure the read endpoint never uses writer credentials.

### Exercise 5 — Does zero exceptions mean secure?

`MATCH (p:SecPayroll) RETURN p.salary` succeeds with 0 rows. Has restriction on `SecPayroll` been proven?

**Suggested answer:** Not yet. You must verify via admin that `SecPayroll` actually holds data, that the reader connected to the right database, and that the fixture transaction committed. Then cross-check effective privileges to confirm nodes were hidden due to missing `TRAVERSE`.

### Exercise 6 — Granting procedure privileges

A team wants to grant `EXECUTE BOOSTED PROCEDURE *` to all services "to avoid permission errors." Why should this be rejected?

**Suggested answer:** Boosted procedure privileges can exceed intended access boundaries and create a broad attack surface, especially for procedures handling files, URLs, or dynamic Cypher. Identify actually used procedures, required privileges, and execution limits, then test each service under its own credentials.

## 18. References

- [Neo4j Operations Manual — Authentication & authorization](https://neo4j.com/docs/operations-manual/current/authentication-authorization/)
- [Neo4j Operations Manual — Managing privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-privileges/)
- [Neo4j Operations Manual — Role-based access control](https://neo4j.com/docs/operations-manual/current/authentication-authorization/)
- [Neo4j Cypher Manual — SHOW commands and graph privileges](https://neo4j.com/docs/cypher-manual/current/clauses/)
- [Neo4j Java Driver Manual — Connectivity and sessions](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver Manual — Managed transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Security Guide](https://neo4j.com/developer/guide-neo4j-security/)

`current` documentation links track the latest release. When deploying Neo4j 5.x, Aura, or newer releases, verify **edition, role/privilege syntax, default grants, and denied-operation behavior** against the documentation for your actual installation.

## 19. Key takeaways

- **Least privilege** means exact identity, database, label/type, property, and operation needed—never an admin account as a runtime identity.
- **Audit effective privileges**, including multiple roles and `PUBLIC`; `DENY` can override conflicting `GRANT`s within matching scope.
- **Missing read privileges do not always throw exceptions**: blocked nodes/relationships can vanish from `MATCH`, and hidden properties can return `null`.
- **Every negative test needs a positive control** with an appropriately privileged identity, plus post-failure state checks on denied writes.
- **Java Driver/SDN must run under genuinely restricted credentials**; running tests only as admin proves nothing about application-account safety.
- **Pair RBAC with Cypher parameterization, credential protection, TLS, minimal procedure rights, and periodic drift checks** to prevent data leaks and unauthorized mutations.

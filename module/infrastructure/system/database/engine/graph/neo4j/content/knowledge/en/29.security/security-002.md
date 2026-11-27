# Role-Based Access Control and Edition or Service Tier Capabilities in Neo4j

## 1. Why must authorization be designed alongside the graph model?

Neo4j stores data as a **property graph**: nodes, relationships, and properties. An application can use Cypher to read customer lists, traverse from orders to products, update relationships, or manage indexes. These actions carry **different risk levels and permission scopes**.

For example, a B2B commerce system has three user groups:

- Customer support staff may only view orders and statuses, not sensitive financial information.
- The ordering service needs to create orders and purchase relationships, but must not manage users or alter the schema.
- Infrastructure administrators need to manage accounts, roles, constraints, indexes, and operational configuration.

If all three share the `neo4j` account with administrative privileges, a leaked credential or a buggy Cypher query in the application can impact the **entire graph**. That is why the principle of **least privilege** applies: each identity holds only the permissions it truly needs.

This lesson in the **Security** chapter explains:

1. How does **authentication** (verifying identity) differ from **authorization** (deciding access permissions)?
2. How does Neo4j's **role-based access control (RBAC)** organize users, roles, and privileges?
3. When are `CREATE ROLE`, `GRANT`, `DENY`, `REVOKE`, and `SHOW PRIVILEGES` used?
4. Are these capabilities available on **Community, Enterprise, AuraDB Free, Professional, Business Critical, or Virtual Dedicated Cloud**?
5. How must Java Driver and Spring Data Neo4j handle connections, testing, and privilege separation?

> **Version scope:** Illustrative syntax targets current Neo4j 5.x releases and the `2025.MM`/`2026.MM` release cadence. Features and limits by edition or AuraDB tier are subject to change; before deploying, verify against the feature matrix for your **specific version and service**.

## 2. First, distinguish authentication, authorization, and application access control

| Concept | Question | Example |
| --- | --- | --- |
| **Authentication** | Who is connecting? | Native username/password, LDAP, OIDC/SSO depending on edition |
| **Authorization** | What can that identity do? | `MATCH` only on `Order` nodes; cannot `CREATE` or manage roles |
| **Database/graph access** | Which scope can be accessed? | Database `neo4j`, `Customer` nodes, `status` property |
| **Application authorization** | Which APIs and records can an end user access? | Customer A only views orders belonging to them and their tenant |
| **Operational security** | Are credentials, network, logs, and backups secure? | TLS, secret manager, firewall, audit, rotation |

Do not confuse them: logging in successfully **does not mean** being able to read every node. Conversely, having `@PreAuthorize` in Spring **does not turn into RBAC inside the database**. If the Bolt connection account holds broad privileges, any query sent directly with those credentials still runs under that broad scope.

Check flow diagram:

```text
HTTP request / background job
         |
         v
Authenticate user at application / IdP
         |
         v
Check tenant, business rules, route, input
         |
         v
Java Driver / Spring Data Neo4j
         |  database credentials
         v
Neo4j authenticates connection
         |
         v
DBMS evaluates roles + privileges + scope
         |
         +-- Allowed: execute Cypher on visible graph
         |
         +-- Not allowed: hide data on reads or reject write operations
```

Defense in depth applies: RBAC in Neo4j **complements** business-level checks in the application; it does not absolve the application from verifying order ownership or tenant boundaries.

## 3. Support matrix by edition and AuraDB tier

### 3.1. Self-managed Neo4j

| Distribution | Authentication | Custom RBAC & fine-grained privileges | Notes |
| --- | --- | --- | --- |
| **Community Edition** | Native accounts and passwords | **No RBAC** | Basic user management exists, but **every user has implicit admin privileges**; cannot create a true reader role |
| **Enterprise Edition** | Native, LDAP/OIDC, and other configurable options | **Yes** | Custom roles, `GRANT`/`DENY`/`REVOKE`, database/graph/property and admin privileges |
| **Infinigraph** | Enterprise capabilities and related deployment mechanisms | **Yes** | Large-scale graph offering incorporating Enterprise capabilities; verify shard/feature boundaries |
| **Enterprise for Developers** | Enterprise features for development where licensed | **Yes in licensed environments** | Do not assume a developer license permits production deployment |

**Common pitfall in Community Edition:** You can run `CREATE USER` with a native password, but you **cannot enforce a "user A read-only, user B read-write" model via RBAC**. Per current Neo4j documentation, Community has no roles and every user implicitly has administrative privileges. Creating multiple accounts on Community separates credentials, **not least-privilege enforcement at the Neo4j layer**.

### 3.2. Neo4j AuraDB — managed service

| AuraDB tier | RBAC & fine-grained database privileges | Key characteristics to note |
| --- | --- | --- |
| **Free** | **No** | Suitable for learning/testing; has authentication without fine-grained RBAC policies |
| **Professional** | **No** | Being a paid tier with operational conveniences does not imply `CREATE ROLE` or fine-grained graph privileges |
| **Business Critical** | **Yes** | Supports RBAC/fine-grained access control and property-based access control; enterprise capabilities |
| **Virtual Dedicated Cloud** | **Yes** | Supports RBAC like Business Critical, combined with the tier's dedicated infrastructure capabilities |

Information verified against **Neo4j Pricing — Security / RBAC and Fine-Grained Access Control** at the time of writing (11/2026). Tier names and features may change.

**Note the two authorization systems in Aura:**

1. **Aura Console / Organization / Project roles:** who can create, view, manage, or pay for instances in the console.
2. **Neo4j DBMS roles/privileges:** who can `MATCH`, `WRITE`, access databases, or alter schemas via Bolt/Cypher.

Being an **organization admin in the Aura Console does not automatically grant full data privileges**, and Console permissions do not mean Free/Professional supports Cypher RBAC. Always verify the **database tier** and the identity model used for connections.

Additionally, on AuraDB many infrastructure administration commands such as `CREATE DATABASE`, `DROP DATABASE`, or server controls are restricted and must be performed through the service console/API, **even on tiers that support RBAC**. DBMS admin privileges do not override managed-service platform boundaries.

### 3.3. Choosing an environment for real requirements

- **Learning Cypher, simple prototypes:** Community or AuraDB Free may suffice when distinct database roles are not needed.
- **Production on Aura with sensitive data requiring native RBAC:** evaluate Business Critical or Virtual Dedicated Cloud.
- **Self-hosted with multiple user groups, SSO, label/property-level authorization:** evaluate Enterprise along with licensing and operational requirements.
- **Constrained to Community/Professional:** enforce strict authorization in the backend, never give Bolt credentials directly to end users, and isolate instances when strong data boundaries are needed; **do not represent these workarounds as equivalent to DBMS RBAC**.

## 4. Neo4j's RBAC mechanism: user → role → privilege

Neo4j Enterprise organizes privileges into a clear model:

```text
Users / service accounts
    |                 |
    v                 v
  role A            role B            (a user can have multiple roles)
    |                 |
    +--------+--------+
             |
             v
       Effective privileges
         /      |      \
    DATABASE   GRAPH   DBMS
     ACCESS    MATCH   USER/ROLE
               WRITE   PROCEDURE
```

### 4.1. Principles of `GRANT`, `DENY`, and `REVOKE`

- **`GRANT`:** permits an action for a role within the specified scope.
- **`DENY`:** forbids the specified action. When both `GRANT` and `DENY` apply, **`DENY` takes precedence** for that privilege.
- **No matching `GRANT`:** by default, the action is **not permitted**.
- **`REVOKE GRANT`:** removes a previously granted privilege; this is different from creating a `DENY`.
- **`REVOKE DENY`:** removes a deny rule; if there is still no `GRANT`, the privilege remains absent.
- **`REVOKE`** without `GRANT`/`DENY` can revoke both forms for the specified privilege.

When a user holds multiple roles, effective `GRANT`s combine; **a matching `DENY` in any role** can block a privilege granted by another role. Never inspect only a newly created role while forgetting the user also has `reader`, `editor`, `admin`, or other custom roles.

### 4.2. Independent privilege layers

| Layer | Example privileges | Meaning |
| --- | --- | --- |
| **Database** | `ACCESS`, `START`, `STOP` | Which databases can be accessed; operational actions per privilege |
| **Graph data** | `TRAVERSE`, `READ`, `MATCH`, `CREATE`, `DELETE`, `SET PROPERTY`, `WRITE` | Traverse nodes/relationships, read properties, mutate the graph |
| **Schema** | `SHOW INDEX`, `INDEX MANAGEMENT`, `CONSTRAINT MANAGEMENT` | View, create, or manage indexes/constraints |
| **DBMS** | `CREATE USER`, `ROLE MANAGEMENT`, `SHOW PRIVILEGE` | Administer identities, roles, and privileges |
| **Procedures/functions** | `EXECUTE PROCEDURE`, `EXECUTE USER DEFINED FUNCTION`, `EXECUTE BOOSTED...` | Permit calling procedures/UDFs and scope execution privileges |
| **Data loading** | `LOAD` and corresponding file/URL policies | Control data ingestion from external sources |

**`GRANT ACCESS ON DATABASE neo4j` does not automatically grant `MATCH` on data.** Reading data requires both database access **and** the appropriate graph privileges. Likewise, having `MATCH` on a label does not permit `CREATE` on that label.

### 4.3. How `TRAVERSE` differs from `READ` and `MATCH`

| Read privilege | Capability granted | Example |
| --- | --- | --- |
| `TRAVERSE` | Discover/traverse nodes or relationships within the granted scope | Can check existence/traverse to nodes, not necessarily read properties |
| `READ {prop}` | Read one or more properties on elements **already reachable** | Read `status`, but cannot automatically traverse to every node |
| `MATCH {prop}` | Combines `TRAVERSE` and `READ` for the corresponding elements/properties | Allows finding `Order` nodes and reading `orderId`, `status` |

A graph query may require privileges on **the start node, the relationship, and the end node**. If a user is allowed to read `Order` nodes but the `PLACED` relationship is hidden, a query traversing from `Customer` via `PLACED` may see no path.

For restricted reads, Neo4j typically **hides the invisible parts of the graph**, causing queries to return fewer or zero rows; for writes lacking privileges, queries are typically **rejected with an error**. This matters when writing tests: a query returning `[]` is not proof that the data does not exist.

## 5. Built-in roles and the special role of `PUBLIC`

On Enterprise and supporting tiers, Neo4j provides built-in roles:

| Role | Default capabilities, brief explanation | When to use |
| --- | --- | --- |
| `PUBLIC` | Held by every user; default access to home database, executing procedures/UDFs and `LOAD` within defined scope; **no graph read privileges** | Baseline privileges; must be audited carefully |
| `reader` | Read and traverse graphs across databases, view some schema info | Users needing broad read access, only when truly appropriate |
| `editor` | Read and modify graphs, **cannot create new label/type/property-key names** | Updating data within an existing schema |
| `publisher` | Like `editor`, plus creating new label/relationship-type/property-key names | Business apps needing to introduce new schema tokens |
| `architect` | Like `publisher`, plus managing indexes/constraints | Migrations or schema design |
| `admin` | Administer DBMS, users, roles, privileges, and most administrative tasks | Tightly controlled operational accounts |

**Do not assign `admin` or `architect` to a web service account just to "avoid errors."** A CRUD application normally does not need to manage databases, users, indexes, or schemas.

`PUBLIC` is a default role that **cannot be removed from users**, though its privileges can be adjusted by an authorized administrator. By default `PUBLIC` includes certain procedure/function/`LOAD` privileges, so a **"narrow custom role" may not actually be narrow in practice** without inspecting privileges inherited from `PUBLIC`. When hardening production, evaluate whether applications depend on privileged procedures; do not revoke `PUBLIC` privileges wholesale without testing.

## 6. Hands-on: creating a role that reads only part of the graph

### 6.1. Prerequisites for running the examples

**Use only Neo4j Enterprise or AuraDB Business Critical/Virtual Dedicated Cloud (where supported by the service).** In Community or AuraDB Free/Professional, the custom role and fine-grained privilege commands below are **not supported**.

The example uses the database named `neo4j` and two dedicated labels:
- `SecDemoCustomer {tenantId, customerId, name}`.
- `SecDemoOrder {tenantId, orderId, status, internalNote}`.
- Relationship `(:SecDemoCustomer)-[:SEC_DEMO_PLACED]->(:SecDemoOrder)`.

For simplicity, data creation steps run under an **admin account on a test database**, while RBAC commands run on **`system`**. Never run directly on production or in a database containing real data with matching labels without evaluation.

### 6.2. Creating demo data with appropriate write privileges

On database `neo4j`:

```cypher
UNWIND [
  {tenantId: 't1', customerId: 'c1', name: 'An'},
  {tenantId: 't2', customerId: 'c2', name: 'Binh'}
] AS row
MERGE (c:SecDemoCustomer {
  tenantId: row.tenantId,
  customerId: row.customerId
})
SET c.name = row.name;
```

```cypher
UNWIND [
  {tenantId: 't1', customerId: 'c1', orderId: 'o101',
   status: 'PAID', note: 'Sensitive data A'},
  {tenantId: 't2', customerId: 'c2', orderId: 'o201',
   status: 'NEW', note: 'Sensitive data B'}
] AS row
MATCH (c:SecDemoCustomer {
  tenantId: row.tenantId,
  customerId: row.customerId
})
MERGE (o:SecDemoOrder {
  tenantId: row.tenantId,
  orderId: row.orderId
})
SET o.status = row.status,
    o.internalNote = row.note
MERGE (c)-[:SEC_DEMO_PLACED]->(o);
```

If creating sample data in a shared environment, add uniqueness constraints on `(tenantId, customerId)` and `(tenantId, orderId)` before concurrent writes. In this sequential learning example, `MERGE` allows reruns without creating duplicate relationships.

### 6.3. Creating the role and granting least privileges

Connect to `system` with an account authorized to manage roles and privileges. Run **each statement independently**:

```cypher
CREATE ROLE sec_demo_order_reader IF NOT EXISTS;
```

```cypher
GRANT ACCESS ON DATABASE neo4j
TO sec_demo_order_reader;
```

```cypher
GRANT MATCH {tenantId, customerId}
ON GRAPH neo4j NODES SecDemoCustomer
TO sec_demo_order_reader;
```

```cypher
GRANT MATCH {tenantId, orderId, status}
ON GRAPH neo4j NODES SecDemoOrder
TO sec_demo_order_reader;
```

```cypher
GRANT TRAVERSE
ON GRAPH neo4j RELATIONSHIPS SEC_DEMO_PLACED
TO sec_demo_order_reader;
```

This role is designed to:
- Access database `neo4j`.
- Find both node types and read **only the listed properties**, unable to read `name` on customer or `internalNote` on order.
- Traverse the `SEC_DEMO_PLACED` relationship without reading relationship properties.
- **Be unable to write to the graph**, since no write privileges were granted.

Do not also assign the built-in `reader` role to the same demo user, because `reader` grants broad read access by default and would defeat testing property restrictions.

### 6.4. Assigning the role to a test account

On `system`, using a password **randomly generated and passed as a parameter from an admin tool or secret manager**, create the native user:

```cypher
CREATE USER sec_demo_app IF NOT EXISTS
SET PASSWORD $initialPassword CHANGE NOT REQUIRED;
```

```cypher
GRANT ROLE sec_demo_order_reader TO sec_demo_app;
```

For a service account, `CHANGE NOT REQUIRED` lets the service connect automatically; you still need a **password rotation process and secret storage** outside code/repositories. `IF NOT EXISTS` does not update the password of an existing user. On Aura, native user creation and privilege assignment also depend on tier and service workflows; verify currently supported syntax.

**Never put real passwords into examples, source control, logs, or shell commands visible in terminal history.** Parameters only partially mitigate query-string leakage; credential provisioning and storage systems must still be secure.

### 6.5. Verifying privileges with the least-privileged account

Log in as `sec_demo_app` and run against database `neo4j`:

```cypher
MATCH (c:SecDemoCustomer)-[:SEC_DEMO_PLACED]->(o:SecDemoOrder)
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       o.status AS status
ORDER BY orderId;
```

The role has `MATCH` on the nodes and `TRAVERSE` on the relationship; the query only requests granted properties, so it is expected to return both orders in the sample dataset.

Attempt to read a sensitive property:

```cypher
MATCH (o:SecDemoOrder {orderId: 'o101'})
RETURN o.internalNote AS internalNote;
```

Do not interpret `null` or unreadable values as "the data was deleted." Cross-check against an appropriately privileged account and inspect effective privileges. This query **must not expose sensitive information** to the demo role under the intended policy.

Attempt a write (expected to be rejected):

```cypher
MATCH (o:SecDemoOrder {orderId: 'o101'})
SET o.status = 'CANCELLED';
```

When tested with a read-only user, the `SET` operation must be blocked by policy. Run negative tests like this on a **dedicated database** or disposable test data, in case you accidentally log in as an admin.

### 6.6. Inspecting effective privileges

On `system` with appropriate administrative privileges:

```cypher
SHOW ROLES;
```

```cypher
SHOW ROLE sec_demo_order_reader PRIVILEGES AS COMMANDS;
```

```cypher
SHOW USER sec_demo_app PRIVILEGES;
```

```cypher
SHOW ROLES WITH USERS;
```

`SHOW ROLE ... PRIVILEGES` inspects a role, while `SHOW USER ... PRIVILEGES` inspects the **combined privileges of a user assigned multiple roles**. Results depend on native vs. external authentication and the privileges of the caller. With LDAP/OIDC, some details about external users cannot be listed for other users the same way as native accounts.

## 7. Narrowing reads with `GRANT` and blocking with `DENY`

### 7.1. When reading is not needed, do not grant it

A secure design typically starts with:
- `GRANT ACCESS` only for required databases.
- `GRANT MATCH` only for needed labels/relationships/properties.
- **No `WRITE`**, `INDEX MANAGEMENT`, or `ROLE MANAGEMENT` unless required by the workload.

This has a major advantage over granting `MATCH {*} ON GRAPH *` and trying to write numerous `DENY` exclusions: any new label or property introduced later will **not automatically become accessible** if it does not match an existing grant.

### 7.2. `DENY` overrides `GRANT` but does not replace `REVOKE`

Suppose a test environment has a broad read role:

```cypher
CREATE ROLE sec_demo_broad_reader IF NOT EXISTS;
```

```cypher
GRANT ACCESS ON DATABASE neo4j TO sec_demo_broad_reader;
```

```cypher
GRANT MATCH {*} ON GRAPH neo4j TO sec_demo_broad_reader;
```

To temporarily block a special label:

```cypher
DENY MATCH {*} ON GRAPH neo4j NODES SecDemoSecret
TO sec_demo_broad_reader;
```

`DENY` blocks matching privileges **even if another role granted a broad `GRANT`**. However, the broad grant remains intact. To **remove the DENY rule**, use:

```cypher
REVOKE DENY MATCH {*} ON GRAPH neo4j NODES SecDemoSecret
FROM sec_demo_broad_reader;
```

To remove the **broad grant**:

```cypher
REVOKE GRANT MATCH {*} ON GRAPH neo4j
FROM sec_demo_broad_reader;
```

These four operations have distinct meanings: grant, deny, revoke grant, and revoke deny. In production, prefer **narrow grants** over keeping broad grants paired with a hard-to-audit list of denies.

### 7.3. Granting and revoking privileges on specific properties

The initial demo role could read three properties on `SecDemoOrder`. If requirements change to allow reading only `tenantId` and `orderId`:

```cypher
REVOKE GRANT MATCH {tenantId, orderId, status}
ON GRAPH neo4j NODES SecDemoOrder
FROM sec_demo_order_reader;
```

```cypher
GRANT MATCH {tenantId, orderId}
ON GRAPH neo4j NODES SecDemoOrder
TO sec_demo_order_reader;
```

This is a **policy migration**, not a mandatory part of the earlier demo. Afterward, queries needing `status` must be retested. Never drop a privilege arbitrarily and leave production apps throwing errors or returning incomplete results.

## 8. Property-based and tenant-based authorization: what works and what does not?

### 8.1. Restricting by label/relationship/property

Neo4j Enterprise and supporting AuraDB tiers can authorize reads on:
- Nodes by **label**.
- Relationships by **type**.
- **Specific properties** on those elements.

This is **fine-grained graph authorization**, distinct from the database-wide `reader` role. However, property-level read privileges **do not by themselves ensure** a user sees only nodes with a given `tenantId`. Multi-tenancy requires property-value rules or database/instance boundaries.

### 8.2. Property-based access control (PBAC)

In supported environments, Neo4j can attach property conditions to privileges. For example, **a fixed role that sees only order nodes with `tenantId = 't1'`**:

```cypher
CREATE ROLE sec_demo_t1_reader IF NOT EXISTS;
```

```cypher
GRANT ACCESS ON DATABASE neo4j TO sec_demo_t1_reader;
```

```cypher
GRANT MATCH {tenantId, orderId, status}
ON GRAPH neo4j FOR (o:SecDemoOrder)
WHERE o.tenantId = 't1'
TO sec_demo_t1_reader;
```

Notes:
- The `'t1'` condition is a **value baked into the privilege**, not a dynamic `$tenantId` passed per request by the application.
- The role only grants access to `SecDemoOrder` nodes; traversing from `Customer` through `SEC_DEMO_PLACED` requires appropriate conditional privileges on the related nodes and relationships.
- If the user also holds another role with a broad `MATCH {*}` grant and **no matching deny**, effective access may be wider than intended.
- **Properties used for PBAC evaluation must be protected from unauthorized modification.** If a user can edit `tenantId`, they can alter how access conditions apply.
- Property-based privileges allow only one property condition per privilege; expressing complex logic requires careful design and testing.

**Important warning:** with PBAC, some `DENY` rules based on property comparisons can **fail open** if the condition cannot be evaluated (e.g., when a property is `null` or missing). Therefore, a **conditional allowlist `GRANT`** design is usually safer and easier to reason about than broad `GRANT` + `DENY tenantId <> 't1'`.

### 8.3. RBAC, PBAC, and ABAC are not one single feature

- **RBAC**: roles receive privileges and are assigned to users.
- **PBAC**: privileges include conditions on **graph property values**, within supported versions.
- **ABAC**: roles/privileges can be determined via **identity attributes or auth rules** in newer Neo4j versions that support them.

For example, starting in Neo4j **2026.06**, user tags support certain ABAC-related capabilities; newer auth-rule and Cypher 25 capabilities are added across releases. **Do not assume ABAC configurations work on older Neo4j 5.x releases or every Aura tier**, and never copy experimental ABAC policies into production without verifying the documentation for your exact running version.

### 8.4. Multi-tenancy and application architecture

| Approach | Advantages | Conditions/risks |
| --- | --- | --- |
| Single database, app always filters `tenantId` | Simpler when native RBAC is unavailable | Relies on every code path enforcing checks; DB credential often has broad access |
| Custom role/PBAC per tenant | Policy partially enforced by DBMS | Large role counts, complex conditions, consistent traversal grants, edition limits |
| Separate databases per tenant group | Clearer database boundaries | Requires edition/tier supporting multiple databases; operational overhead |
| Dedicated instance for sensitive tenants | Clear infrastructure and credential isolation | Higher cost; distributed operations and backups |
| RBAC/PBAC + app authorization | Defense in depth | Must test full policies and effective privileges |

A query `MATCH (o:Order {tenantId: $tenantId})` is a useful business filter, **not a substitute for database-level access control** if users can open direct Bolt connections with overly permissive credentials.

## 9. Procedures, APOC, GDS, and boosted privileges

### 9.1. Executing procedures does not mean read-only

Neo4j applications may use:
- `CALL db.index.fulltext.queryNodes(...)` for search.
- APOC procedures for import/export, batching, or HTTP calls.
- GDS `gds.*` to project graphs and run algorithms.
- Custom Java procedures/UDFs.

User privileges extend beyond `MATCH`/`WRITE`. Always check:
- Which name scopes have `EXECUTE PROCEDURE` or `EXECUTE USER DEFINED FUNCTION`.
- Whether **boosted** privileges exist, meaning execution in an elevated privilege context; treat carefully as it can expose data beyond normal read permissions.
- DBMS `allowlist`/`unrestricted` settings in self-managed deployments, along with file/network policies and edition rules.
- Availability of APOC Core/Extended or GDS on the tier in use.

### 9.2. The `PUBLIC` role must be audited

Under current defaults, `PUBLIC` may allow calling many procedures/UDFs and `LOAD`. Do not conclude "a custom role only has MATCH so all other APIs are disabled." If an application does not need procedures or data loading, evaluate **narrowing `PUBLIC` privileges** per security policy, after testing the impact on applications, drivers, and operational tooling.

**Do not blindly copy `DENY EXECUTE PROCEDURE *` or revoke all `PUBLIC` privileges on a live system.** That can break core platform functionality or legitimate workflows. Measure actual usage, file a change request, keep backup/rollback policies ready, and test on staging first.

## 10. Testing authorization: test both allowed and forbidden paths

A reliable test matrix uses **real accounts mapped to roles**, not just reading `SHOW ROLE ... PRIVILEGES`:

| Scenario | Expectation for `sec_demo_order_reader` | Test type |
| --- | --- | --- |
| Log in and read `SecDemoOrder.orderId`/`status` | Succeeds | Positive |
| Traverse `Customer-[:SEC_DEMO_PLACED]->Order` | Succeeds with granted properties | Positive |
| Read `SecDemoOrder.internalNote` | Sensitive value not exposed | Negative |
| `SET o.status = 'CANCELLED'` | Write rejected | Negative |
| `CREATE (:SecDemoOrder {...})` | Write rejected | Negative |
| `CREATE INDEX`/`DROP CONSTRAINT` | Schema management rejected | Negative |
| `CREATE USER`/`GRANT ROLE` | RBAC administration rejected | Negative |
| Read nodes with ungranted labels | Corresponding graph content hidden | Negative |
| Also assign `reader` role to test user | May widen read access | Regression/hardening |
| Add a new `internalNote2` property | Not readable automatically when grant lists specific properties | Regression |

**Note:** Never run `DELETE`, `DROP`, or `CREATE` to test privileges against production data. Use a copy or test environment. If accidentally run with an admin user, the mutation will succeed and cause real damage.

### 10.1. Diagnosing `[]` results and missing-privilege errors

- **Read query returning 0 rows** may be due to missing data, inability to traverse nodes/relationships, wrong `WHERE` conditions, or data belonging to another tenant.
- **Unreadable property** may be a privilege restriction or a genuinely absent property; verify the same data with a privileged account.
- **Write query failing with missing privilege** indicates the relevant privilege needs review, not that you should grant `admin`.
- **Administration command not found** may reflect an unsupported edition/tier, not only a missing privilege.
- **`SHOW ROLE` only shows a single role**; multiple assigned roles, `PUBLIC`, and external auth can make effective privileges differ from expectations.

## 11. Java Driver: applications must connect with appropriately scoped identities

### 11.1. Never use admin credentials for normal requests

Neo4j Java Driver 6.x example reading a list of orders:

```java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String uri = System.getenv("NEO4J_URI");
String username = System.getenv("NEO4J_READ_USER");
String password = System.getenv("NEO4J_READ_PASSWORD");

// NEO4J_URI should be neo4j+s://... or bolt+s://...
// matching the actual server certificate and configuration.
try (Driver driver = GraphDatabase.driver(
        uri, AuthTokens.basic(username, password));
     Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {

    var orders = session.executeRead(tx ->
        tx.run(
            """
            MATCH (o:SecDemoOrder)
            WHERE o.tenantId = $tenantId
            RETURN o.orderId AS id, o.status AS status
            ORDER BY id
            """,
            Map.of("tenantId", "t1")
        ).list(record -> Map.of(
            "id", record.get("id").asString(),
            "status", record.get("status").asString()
        ))
    );

    System.out.println(orders);
}
```

In real systems, **create and share a single `Driver`** over the application lifecycle; the `try (Driver ...)` block here illustrates a standalone program. Each operation opens its own session and closes it after consuming results.

The `NEO4J_READ_USER` account must be configured **beforehand** with the appropriate RBAC in a supporting environment; environment variables **do not create roles**. Java code must obtain and validate `tenantId` from the authenticated context rather than trusting arbitrary caller-supplied values. Even with PBAC in place, keeping business filters helps query selectivity and defense in depth.

### 11.2. When an application needs both reads and writes

One authorization pattern is using **two separate credentials**:
- A reader credential for reporting APIs and UI screens.
- A writer credential for the service responsible for mutating the graph, with write roles scoped to the **right schema**.

However, do not create two `Driver` instances per request; manage each configured Driver/pool as a shared resource. Each secret has its own lifecycle, provisioned from a secret manager, rotated regularly, and never logged or dumped.

When the writer credential uses `executeWrite(...)`, the callback can be retried by the driver after a transient failure. Ensure write operations are idempotent and backed by business constraints. **RBAC does not prevent duplicate writes caused by retries**, just as transactions do not replace tenant/ownership checks.

### 11.3. Impersonation and end users

In deployments supporting Java Driver **impersonation**, a connection can execute queries under a specified target identity if the base account holds the required impersonation privilege. This feature depends on edition, privileges, and security policy; you cannot simply set an arbitrary username on the client and expect impersonation to work.

Do not use impersonation as a substitute for end-user authentication, and do not casually grant `IMPERSONATE` to application accounts. In multi-tenant systems, the user → role → DBMS privilege mapping must be carefully designed, tested, and audited.

## 12. Spring Data Neo4j and Spring Security: two layers of responsibility

With Spring Data Neo4j, repositories and `Neo4jClient`/`ReactiveNeo4jClient` typically use the credentials configured on the datasource/driver. Spring Security enforces request and method authorization at the application layer; it **does not dynamically grant or revoke Neo4j roles when calling a repository**.

Example illustrating the application flow:

```java
@PreAuthorize("hasAuthority('order:read')")
public List<OrderSummary> findOrdersForCurrentCustomer(
        String tenantId, String customerId) {
    // In practice: tenantId/customerId must be obtained and verified
    // from the authenticated principal / authorization context.
    return orderReadRepository.findSummaries(tenantId, customerId);
}
```

The snippet above illustrates **an API-level check**; it requires real repository/interface definitions and security configuration to compile, and does not replace tenant/ownership verification. A user holding `order:read` is not automatically permitted to view every order in the database.

Key points to remember:

1. The DB credential in Spring is usually a **service identity**, not the HTTP end user's identity.
2. `@PreAuthorize` restricts execution paths in the service but does not change the Bolt privileges of the DB credential.
3. If the service uses an admin credential, an injection flaw or misbehaving query can bypass service-layer authorization assumptions.
4. Prefer custom Cypher/DTO projections to read only granted properties; when a repository hydrates an entity that includes hidden properties, mapping may receive missing or unexpected values.
5. Test both **DB roles** and **service authorization**, including cross-tenant, wrong-owner, and wrong-role access attempts.
6. Deploy `reader`, `writer`, or `reporter` using distinct accounts/roles instead of sharing one `admin` account across every bean and job.

## 13. LDAP, OIDC/SSO, Aura, and effective privileges

### 13.1. External authentication does not automatically define graph privileges

Neo4j Enterprise offers LDAP/OIDC integration depending on configuration and version. The identity provider verifies identity or supplies attributes/groups; Neo4j still determines privileges from mapped roles/privileges.

Common issues:
- Valid token but missing role mapping, allowing login with no data access.
- An IdP group mapped to an overly broad role, exposing the graph to every group member.
- Group/user changes in the IdP not immediately reflected in active login sessions or cached tokens.
- Multiple configured auth providers producing unexpected effective privileges; always test with real accounts.

### 13.2. Aura organization and database accounts are not the same

In Aura, accounts managing organizations, projects, and instances are **distinct** from DBMS users connecting over Bolt. When designing access:

- Define who can manage the **Aura Console**.
- Define which DBMS users or SSO methods can **connect to and query the graph**.
- Verify whether the tier supports database RBAC/SSO rather than assuming console membership lists imply DBMS RBAC.
- When on Free/Professional, do not write `CREATE ROLE` migrations expecting them to run; redesign or upgrade tiers if DBMS-enforced RBAC is mandatory.

## 14. Operating RBAC safely: configuration, changes, and monitoring

### 14.1. Policy as code

Even though privileges are administered with Cypher, keep role definitions in reviewed migrations containing:

- Business-clear role names: `order_reader`, `order_writer`, `schema_migrator`.
- The list of required databases, labels, relationships, and properties.
- Owner/approver and justification for each privilege.
- Assigned accounts and review schedules.
- Positive/negative tests run after every schema change.
- A rollback plan using `REVOKE` or restoring prior grants.

Avoid casual use of `CREATE OR REPLACE ROLE`: replacing an existing role can wipe out prior privileges. When you want idempotent creation without overwriting existing configuration, use `CREATE ROLE ... IF NOT EXISTS` and then **reconcile privileges**, rather than assuming the existing role is already correct.

### 14.2. Password and secret management

- Never commit high-privilege usernames/passwords into repositories.
- Use a secret manager with rotation, and revoke unused credentials.
- Use TLS for network connections; verify certificates and URIs properly.
- Restrict network access to Bolt, especially on self-managed databases.
- Log administrative/audit actions as supported by the edition/tier; never log passwords, sensitive data, or access tokens.

### 14.3. Read/write operations during role changes

If you modify a user's privileges while they have open sessions, transactions, or pooled connections, check version-specific behavior for how privilege changes take effect on active transactions. **Dropping a user does not necessarily terminate running sessions or transactions immediately.** During a credential-leak incident, do not merely alter a role and assume malicious connections are invalidated; follow credential revocation, terminate sessions/transactions where needed, and review audit logs.

## 15. Common limitations and misconceptions

| Misconception | Reality |
| --- | --- |
| "Community has multiple native users, so it has RBAC." | Community has no roles and every user has implicit admin privileges; it cannot enforce least privilege in the DBMS |
| "Aura Professional is a paid tier, so it has fine-grained graph authorization." | RBAC/fine-grained access control is listed for Business Critical and Virtual Dedicated Cloud, not Professional |
| "An Aura Console Admin is also admin of all Neo4j data." | Console permissions and DBMS privileges are two separate layers |
| "`GRANT ACCESS` lets you read the graph." | Appropriate `TRAVERSE`/`READ`/`MATCH` privileges are also required |
| "`READ` on a property automatically finds the node." | `TRAVERSE` is required; `MATCH` combines both |
| "If role A has `GRANT`, role B's `DENY` does not matter." | Effective privileges merge roles; `DENY` takes precedence |
| "`DENY` deletes `GRANT`." | Both remain stored; you must `REVOKE` to remove them |
| "Not seeing a node means the node does not exist." | Nodes or relationships may be hidden by read privileges |
| "`MATCH {*}` reads every node so it is always right." | Too broad; newly added labels/properties can unintentionally become readable |
| "PBAC using `DENY tenantId <> x` is always airtight." | Missing/null properties can cause **fail-open** behavior when a broad grant exists |
| "Grant `reader` and then restrict it with a custom role." | `reader` is broad; restricting it requires explicit `DENY` rules or avoiding `reader` altogether |
| "Having `@PreAuthorize` means you already have Neo4j RBAC." | Spring permissions do not change the privileges of the Bolt credential |
| "If a procedure runs, it is safe." | Check `EXECUTE`, boosted privileges, file/network permissions, and side effects |
| "A read-only role can ignore `PUBLIC`." | `PUBLIC` is inherited by every user and carries baseline privileges that must be audited |
| "RBAC alone solves per-order authorization per HTTP session." | Requires identity mapping, property-based privileges, or application authorization—never inferred automatically from HTTP requests |
| "Any admin command works on Aura." | Managed services restrict infrastructure-level operations by tier |
| "Creating a new role and granting privileges is enough." | Must test with the actual user, inspect other groups/roles, and review logs |

## 16. Authorization design checklist for a Neo4j service

1. **Edition/tier:** Community, Enterprise, Aura Free/Professional/Business Critical/Virtual Dedicated Cloud? Exactly which capabilities exist in the running release?
2. **Identity:** native user/service account or LDAP/OIDC? Who owns and rotates the secret?
3. **Business roles:** separate read-only, writer, migration, and admin; avoid shared high-privilege accounts.
4. **Database scope:** which databases must the user access? Grant `ACCESS` only as needed.
5. **Graph scope:** which labels/types/properties? Is `TRAVERSE`, `READ`, or `MATCH` required?
6. **Write scope:** are `CREATE`, `DELETE`, `SET PROPERTY`, or `WRITE` needed? Is creating new property keys allowed?
7. **Schema/DBMS:** who may manage indexes, constraints, users, roles, `LOAD`, and procedures?
8. **Combined roles:** does the user also carry `reader`, `editor`, `PUBLIC`, or external group roles?
9. **Tenancy:** database-level, PBAC/ABAC, or application authorization? Are cross-tenant traversal paths possible?
10. **Testing:** positive and negative tests with real least-privileged credentials; verify hidden data and rejected writes.
11. **Java/Spring:** avoid admin credentials for APIs; manage Driver, transactions, secrets, and inputs properly.
12. **Monitoring:** audit privileges, role changes, anomalous logins, procedure usage, and credential revocation.
13. **Upgrades:** verify Cypher version, Neo4j edition, Aura feature matrix, and any changed admin APIs.

## 17. Self-study exercises

1. A team uses Community Edition and creates three native users. They want one read-only user and one write-only user. Can this be achieved with RBAC? State alternative options and security limitations.
2. Build a comparison table of AuraDB Free, Professional, Business Critical, and Virtual Dedicated Cloud covering RBAC, database management capabilities, and graph privilege control.
3. Explain why `GRANT ACCESS ON DATABASE neo4j` is not enough to run `MATCH (n) RETURN n`.
4. Create a role `report_reader` allowed only to read `Order(orderId, status)` and traverse the `PLACED` relationship from `Customer`. Write the required `GRANT` statements in a supporting environment.
5. A user holds both `reader` and a custom role restricting `Order`. Is the user guaranteed to read only `Order`? Analyze how privileges combine.
6. What is the difference between `REVOKE GRANT` and `REVOKE DENY`? Write a statement to revoke a previously granted `MATCH` privilege.
7. Why can `DENY MATCH {*} FOR (n:Order) WHERE n.tenantId <> 't1'` be dangerous if `tenantId` is missing?
8. Test a `SecDemoOrder` with `internalNote`. Describe how to prove the order-reader role cannot read that sensitive value while still reading `status`.
9. In Spring Boot, a service uses `@PreAuthorize` but connects with the Neo4j `admin` credential. Name at least three risks and how to mitigate them.
10. An application uses APOC to import JSON, GDS for graph analytics, and Java Driver to read orders. Propose how to grant procedure/function privileges and separate analytics jobs from the API.
11. Writer credential leak incident: why does `DROP USER` alone not guarantee immediate termination of all running transactions? Propose an incident-response checklist.
12. Design a migration plan from AuraDB Professional to a tier supporting DBMS RBAC, covering role migrations, privilege tests, secret management, and rollback.

## 18. Key takeaways

- Neo4j RBAC governs **user → role → privilege** across **DBMS, database, graph, label/type, and property** scopes.
- **`GRANT` permits, `DENY` blocks, `REVOKE` removes**. `DENY` takes precedence when applicable; users can hold multiple roles and always inherit `PUBLIC`.
- **`TRAVERSE`, `READ`, and `MATCH` differ**. Database access is not graph read permission; reading a property does not automatically allow traversing to the node.
- **Community Edition lacks roles/fine-grained RBAC**; **Enterprise Edition provides them**. On AuraDB, **Business Critical and Virtual Dedicated Cloud support RBAC**, whereas **Free and Professional do not** per the current feature matrix.
- Built-in `reader` grants broad read access, `editor` writes data, `architect` manages schema, and `admin` administers the DBMS; never assign them to a service merely for convenience.
- **PBAC/ABAC depend on edition, version, policy, and thorough testing**; avoid property-based `DENY` rules that can fail open on missing data.
- **Spring Security and Aura Console roles do not replace Neo4j DBMS RBAC**. The Java Driver runs with the connecting identity's privileges; separate credentials and test with real accounts.
- **Least privilege + negative testing + secret management + TLS + auditing** form a continuous process, not a one-time `GRANT` script.

### Official references

- [Neo4j Operations Manual — Authentication and authorization](https://neo4j.com/docs/operations-manual/current/authentication-authorization/)
- [Neo4j Operations Manual — Role-based access control](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-privileges/)
- [Neo4j Operations Manual — Built-in roles and privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/built-in-roles/)
- [Neo4j Operations Manual — Manage roles](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-roles/)
- [Neo4j Operations Manual — Manage users](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-users/)
- [Neo4j Operations Manual — Read privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/privileges-reads/)
- [Neo4j Operations Manual — Write privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/privileges-writes/)
- [Neo4j Operations Manual — Database privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/database-administration/)
- [Neo4j Operations Manual — Property-based access control](https://neo4j.com/docs/operations-manual/current/authentication-authorization/property-based-access-control/)
- [Neo4j Operations Manual — RBAC limitations](https://neo4j.com/docs/operations-manual/current/authentication-authorization/limitations/)
- [Neo4j Operations Manual — Procedure and function privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-execute-permissions/)
- [Neo4j Aura — Cypher and Aura](https://neo4j.com/docs/cypher-manual/current/introduction/cypher-aura/)
- [Neo4j — Pricing and edition feature comparison](https://neo4j.com/pricing/)
- [Neo4j Java Driver Manual — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
- [Spring Data Neo4j — Reference](https://docs.spring.io/spring-data/neo4j/reference/)

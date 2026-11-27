# Creating, Listing, Deploying, and Dropping Constraints

In Neo4j, data is organized according to the **property graph** model: nodes carry labels and properties; relationships carry types and properties, connecting nodes. Applications typically use Cypher to create customers, orders, and relationships between them. When multiple processes write data concurrently, validating only at the Java, Spring Data Neo4j, or API layer is not enough. **Constraints** allow the database itself to reject certain invalid data states directly.

This lesson belongs to the **Data Constraints** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The focus is the full constraint lifecycle: **creating with `CREATE CONSTRAINT`, listing and verifying with `SHOW CONSTRAINTS`, deploying via migrations, and removing with `DROP CONSTRAINT`**. Examples use modern Cypher syntax from Neo4j 5.x; when operating a different version/edition, verify the availability of each constraint type and its corresponding syntax.

After this lesson, you will be able to:

- Create clearly named constraints using `IF NOT EXISTS` for repeatable deployments.
- Read constraint metadata and distinguish constraints from indexes.
- Detect duplicate data or missing properties before applying constraints.
- Build a controlled workflow for deploying, verifying, and dropping constraints.
- Combine constraints with `MERGE` and Java application layers.

## 1. What Do Constraints Protect?

Suppose we have this graph:

~~~text
(:Customer {customerId, email, name})
     |
     | [:PLACED {eventId, placedAt}]
     v
(:Order {tenantId, orderNo, createdAt, total})
~~~

Business requirements might include: a `customerId` must not belong to two different customer nodes; every order must have `createdAt`; no two `PLACED` relationships may use the same `eventId`. Neo4j supports several constraint types to express these requirements.

| Type | Meaning | Cypher Example (`REQUIRE` clause) |
| --- | --- | --- |
| Node uniqueness | Nodes with the same label cannot duplicate the constrained property value when present. | `c.email IS UNIQUE` |
| Composite uniqueness | No duplicate **combination** of property values. | `(o.tenantId, o.orderNo) IS UNIQUE` |
| Relationship uniqueness | Relationships of the same type cannot duplicate the constrained property value. | `r.eventId IS UNIQUE` |
| Node key | Requires the node to have the key property **and** the key to be unique. | `c.customerId IS NODE KEY` |
| Relationship key | Requires the relationship to have the key property **and** the key to be unique. | `r.eventId IS RELATIONSHIP KEY` |
| Property existence | Requires the property to exist on nodes/relationships within the constraint scope. | `o.createdAt IS NOT NULL` |
| Property type | The property, if present, must have the declared data type. | `o.total IS :: FLOAT` |

**Note two key distinctions:**

1. `IS UNIQUE` **does not automatically require the property to exist**. Multiple `Customer` nodes missing `email` do not violate uniqueness on `email`. If a value must be both present and non-duplicate, use a key constraint where supported by your edition, or combine uniqueness with an existence constraint.
2. `IS :: FLOAT` restricts the type when the property exists, **does not forbid missing properties**, and does not forbid negative numbers. Rules such as `total >= 0`, email formatting, or requiring a relationship to connect to a valid customer belong in business/model validation if no corresponding constraint covers them.

Not every edition or version of Neo4j supports every type. In particular, **key, existence, and property type constraints** require checking Neo4j Enterprise feature availability and the running version. The property type syntax shown here targets Neo4j 5 releases that support that feature. Never push the entire set of illustrative commands straight to production without checking support.

## 2. Standard Syntax for Creating Constraints

Template:

~~~cypher
CREATE CONSTRAINT constraint_name IF NOT EXISTS
FOR (n:Label)
REQUIRE n.property IS UNIQUE;
~~~

Where:

- `constraint_name` is the name used to track, search, migrate schemas across environments, and drop the exact object.
- `FOR` defines the scope of nodes with a label or relationships with a type. Constraints apply to **that specific label/type**, not automatically across all nodes or all relationship types.
- `REQUIRE` specifies the condition Neo4j checks when creating the constraint and on subsequent writes/updates.
- `IF NOT EXISTS` allows re-running deployment commands when an equivalent constraint already exists. It **does not replace** verifying the name, type, and structure of the constraint after deployment.

Consistent naming makes operations easier to audit—for example, `customer_email_unique`, `order_tenant_no_unique`, or `order_created_required`. Avoid auto-generated names that are hard to identify when a rollback is needed.

### 2.1. Single-Property Uniqueness Constraint

~~~cypher
CREATE CONSTRAINT customer_email_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.email IS UNIQUE;
~~~

This statement prevents two nodes carrying label `Customer` from having **the same non-null email**. If email must always be present on every customer, add an existence constraint or choose another key design. Email values are case-sensitive under standard string comparison; if `AN@example.com` and `an@example.com` should be treated as duplicates, normalize data before writing and before creating the constraint.

### 2.2. Composite-Property Uniqueness Constraint

A multi-tenant system may allow different tenants to use the same `orderNo`, while forbidding duplicate `orderNo` within the **same tenant**:

~~~cypher
CREATE CONSTRAINT order_tenant_no_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE (o.tenantId, o.orderNo) IS UNIQUE;
~~~

This condition checks the `(tenantId, orderNo)` **pair**, without requiring `tenantId` or `orderNo` individually to be unique. If part of the pair is missing, uniqueness does not enforce presence of each property; evaluate key/existence constraints if required by the domain.

### 2.3. Relationship Uniqueness Constraint

~~~cypher
CREATE CONSTRAINT placed_event_unique IF NOT EXISTS
FOR ()-[r:PLACED]-()
REQUIRE r.eventId IS UNIQUE;
~~~

This example is useful when order-placement events carry their own identifier. Other relationship types are unaffected by constraints on `:PLACED`. Depending on edition/version, verify that relationship uniqueness is supported.

### 2.4. Node Keys and Relationship Keys

If every customer **must have a `customerId` and it must be unique**, a node key expresses both rules:

~~~cypher
CREATE CONSTRAINT customer_id_key IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS NODE KEY;
~~~

A composite key can also be defined:

~~~cypher
CREATE CONSTRAINT order_business_key IF NOT EXISTS
FOR (o:Order)
REQUIRE (o.tenantId, o.orderNo) IS NODE KEY;
~~~

For relationships, if `eventId` must be present and never duplicated:

~~~cypher
CREATE CONSTRAINT placed_event_key IF NOT EXISTS
FOR ()-[r:PLACED]-()
REQUIRE r.eventId IS RELATIONSHIP KEY;
~~~

The key statements above demonstrate capabilities on versions/editions that support them. Do not mechanically deploy both uniqueness and key constraints on the same schema: decide on one structure that meets business requirements, inspect existing constraints, and plan changes if needed.

### 2.5. Property Existence and Property Type

Require every `Order` node to have `createdAt`:

~~~cypher
CREATE CONSTRAINT order_created_required IF NOT EXISTS
FOR (o:Order)
REQUIRE o.createdAt IS NOT NULL;
~~~

Require `total`, when present, to be a `FLOAT`:

~~~cypher
CREATE CONSTRAINT order_total_float IF NOT EXISTS
FOR (o:Order)
REQUIRE o.total IS :: FLOAT;
~~~

Before creating a type constraint, inspect the actual value types stored in the database: `total` values stored as `INTEGER` or `STRING` will not be converted to `FLOAT` automatically. Pick the type according to domain rules and how the application writes data; Neo4j does not treat integers as `FLOAT` values when checking a `FLOAT` type constraint.

For data requiring both existence and type checks, define both corresponding conditions (or use an appropriate key type for identifiers). Never treat a single constraint as a full record-validity system.

## 3. Listing and Inspecting Existing Constraints

General command:

~~~cypher
SHOW CONSTRAINTS;
~~~

To display the columns most useful for operations:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

Meaning of commonly used columns:

| Column | How It Is Used |
| --- | --- |
| `name` | Identifies the constraint for inspection and calling `DROP CONSTRAINT`. |
| `type` | Distinguishes uniqueness, key, existence, property type, etc.; exact values depend on version. |
| `entityType` | Indicates whether scope is node or relationship. |
| `labelsOrTypes` | Node label or relationship type governed by the constraint. |
| `properties` | List of properties participating in the constraint; may contain multiple properties. |

You can filter by naming convention:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
WHERE name STARTS WITH 'customer_'
RETURN name, type, labelsOrTypes, properties
ORDER BY name;
~~~

Uniqueness and key constraints have a Neo4j-managed **backing index used for uniqueness enforcement**. You can also inspect indexes via:

~~~cypher
SHOW INDEXES;
~~~

Indexes and constraints serve different purposes: indexes primarily accelerate data lookup/access, while constraints define data validity. Never try to delete a constraint-owned index to "remove a constraint"; drop the constraint properly by name. Existence/type constraints do not imply a query-serving index exists.

**Verify after creation:** never assume success merely because `CREATE ... IF NOT EXISTS` returned no error. Compare `name`, `type`, `labelsOrTypes`, and `properties` against the target schema. A matching name with an unexpected definition must be addressed via an explicit migration.

## 4. Auditing Data Before Deployment

Neo4j checks **existing data** when creating a constraint. If violations exist, creation fails; data is never silently edited, deleted, or skipped. Therefore, audit data and choose appropriate remediation before running DDL in a live environment.

### 4.1. Finding Duplicate Emails Before Creating Uniqueness

~~~cypher
MATCH (c:Customer)
WHERE c.email IS NOT NULL
WITH c.email AS email, count(*) AS soKhach
WHERE soKhach > 1
RETURN email, soKhach
ORDER BY soKhach DESC, email ASC
LIMIT 20;
~~~

If the query returns rows, resolve duplicates per business rules: merge customer records, change email keys, or designate a canonical record. Never delete duplicate nodes automatically, as they may still hold relationships, orders, and related history.

### 4.2. Finding Missing Mandatory Properties

~~~cypher
MATCH (o:Order)
WHERE o.createdAt IS NULL
RETURN count(o) AS soDonThieuNgayTao;
~~~

In Cypher, accessing a non-existent property returns `null`. Distinguish "missing creation timestamp" from a malformed timestamp written with the wrong type by an application. When preparing to apply a node key on `customerId`, separately check for customers missing the key:

~~~cypher
MATCH (c:Customer)
WHERE c.customerId IS NULL
RETURN count(c) AS soKhachThieuMa;
~~~

### 4.3. Finding Duplicate Order Key Combinations

~~~cypher
MATCH (o:Order)
WHERE o.tenantId IS NOT NULL AND o.orderNo IS NOT NULL
WITH o.tenantId AS tenantId, o.orderNo AS orderNo, count(*) AS soDon
WHERE soDon > 1
RETURN tenantId, orderNo, soDon
ORDER BY soDon DESC, tenantId ASC, orderNo ASC
LIMIT 20;
~~~

If using a **composite node key**, also check for nodes missing `tenantId` or `orderNo`, because keys require every component to exist. With composite uniqueness, finding duplicates across rows that have both properties is the right preflight check.

### 4.4. Checking Actual Data Types and Edition

Before applying a type constraint, summarize stored types using queries/checks compatible with your system's Neo4j release. Converting strings to numbers, integers to floats, or changing date/time representations requires explicit data rules and a separate migration. Also verify that your edition supports the target constraint type and that the deployment account holds schema management privileges on the right database.

## 5. Deploying Constraints via Migrations

Schema changes are stateful operations on the database and must be **repeatable, verifiable, and have a rollback plan**. A practical six-step process:

1. **Lock the specification:** define label/type, properties, constraint type, naming convention, edition, and Cypher version.
2. **Audit data:** check for duplicates, missing values, and data types as in Section 4; complete cleanup migrations if violations are found.
3. **Test in a comparable environment:** run the statements, observe duration and write impact, and test application node/relationship create/update flows.
4. **Prepare operations:** store versioned schema scripts in the project's migration tool; back up or establish a restore point per organizational policy, and pick a deployment window suited to data volume.
5. **Apply and verify:** use an account with sufficient privileges on the **right database**, check `SHOW CONSTRAINTS`, and verify write functionality.
6. **Record results:** log the applied migration version, cross-check against the target environment, and document error handling and rollback steps.

Example of a SQL-like migration stored as Cypher statements using constraint types confirmed to be available:

~~~cypher
// Migration example: 001_customer_order_constraints.cypher
CREATE CONSTRAINT customer_email_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.email IS UNIQUE;

CREATE CONSTRAINT order_tenant_no_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE (o.tenantId, o.orderNo) IS UNIQUE;
~~~

When deploying via the command line, `cypher-shell` can execute the script against a designated database:

~~~bash
cypher-shell -a neo4j://localhost:7687 -u neo4j -d neo4j -f 001_customer_order_constraints.cypher
~~~

The host, address, username, and database are **examples**; the tool can prompt securely for the password at runtime. In production environments, use encrypted endpoints, deployment accounts governed by least privilege, and your organization's approved secrets management.

**Why run versioned migrations?** Suppose environment A has constraint `customer_email_unique`, environment B lacks it, and environment C has a different constraint sharing the same name. A script relying solely on `IF NOT EXISTS` cannot confirm that all three share an identical schema. The migration process must verify actual structure and flag discrepancies when needed.

### 5.1. Deploying with the Neo4j Java Driver

A Java system can execute schema statements via the Neo4j Java Driver—for example, inside a migration runner or dedicated admin tool:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class SchemaMigration {
    public static void apply(Driver driver) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.run("""
                CREATE CONSTRAINT customer_email_unique IF NOT EXISTS
                FOR (c:Customer)
                REQUIRE c.email IS UNIQUE
                """).consume();
        }
    }
}
~~~

`Driver` is configured and lifecycle-managed at the application layer; this example assumes a valid `Driver` already exists. `consume()` waits for execution to complete and surfaces errors if the database rejects the operation. The command targets database `neo4j` in the example; replace it with your actual deployment database name.

With **Spring Data Neo4j**, constraints should still be managed as part of a controlled migration/schema deployment. Entity mappings, annotations, and repositories are not proof that all desired constraints exist with the right types in the running database. Whether executed via the Java Driver, CLI, or a migration tool, the preflight and metadata-verification steps remain the same.

### 5.2. Operational Impact and Concurrency

Creating uniqueness/key constraints may require scanning existing data and building an index for key enforcement. On large graphs, build duration and resource impact can be significant; benchmark on representative data. If other processes write concurrently during deployment, resource contention or incoming invalid data can cause waits or failures. Prepare a deployment plan, monitoring, and error handling suited to your system.

Once created, the constraint governs subsequent writes. It does not automatically enforce complex rules such as positive monetary amounts, relationship direction, or limiting a customer to one order in a given status.

## 6. Dropping Constraints and Rollback

When email uniqueness must be retired:

~~~cypher
DROP CONSTRAINT customer_email_unique IF EXISTS;
~~~

`DROP CONSTRAINT` takes the **constraint name**, not the label/property specification. `IF EXISTS` avoids errors when the name is absent, though you should still check the state afterward:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
WHERE name = 'customer_email_unique'
RETURN name, type, labelsOrTypes, properties;
~~~

If zero rows are returned, that constraint is no longer listed. Dropping a constraint **does not delete existing nodes, relationships, or property values**, though new records can now violate the former rule. For constraints with a Neo4j-owned backing index, dropping the constraint also drops its associated index, which can affect query plans.

Before dropping, confirm whether applications, ingestion jobs, or sync processes still rely on the constraint. If dropping a constraint to perform a migration, avoid leaving an unprotected write window. When re-creating the constraint, Neo4j must re-verify existing data; duplicates introduced during that gap can cause re-creation to fail.

**Changing a constraint type is not just renaming.** For example, moving from `customer_email_unique` to `customer_id_key` can alter both the business key field and mandatory existence rules. Audit data first, create the new constraint when appropriate, update applications, and drop the old constraint only after all write paths have switched over. If structural conflicts prevent creating the new constraint first, plan a dedicated cutover that minimizes unprotected downtime.

## 7. Combining Constraints with `MERGE` on Writes

In applications, `MERGE` is commonly used to find or create a node by business key:

~~~cypher
MERGE (c:Customer {customerId: $customerId})
ON CREATE SET c.createdAt = datetime()
SET c.name = $name, c.email = $email
RETURN c;
~~~

Once a uniqueness constraint (or node key) is active on `Customer.customerId`, the database has a mechanism to prevent two records with the same code, even under concurrent requests. However:

- `MERGE` does not replace constraints. Without the right key constraint, concurrent requests still risk creating duplicate records.
- `MERGE` can throw errors when values conflict with constraints; the application must handle exceptions and apply an appropriate retry policy.
- Avoid `MERGE` across multiple mutable properties—such as both customer ID and email—when each property has its own constraint. Designate one stable identifying key and update remaining properties via `SET`.
- When emails must remain unique, keep the separate `customer_email_unique` constraint if `customerId` alone does not guard emails.

To illustrate the difference: `customer_id_key` prevents two nodes from sharing `customerId`; it **does not** prevent two customers from sharing the same `email`. Constraint design must flow from business invariants, not just from the `MERGE` statement currently in use.

## 8. Common Errors When Managing Constraints

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| Uniqueness creation fails due to duplicate values | Two nodes/relationships in the same label/type already share the key. | Run duplicate-detection queries, resolve per business rules, then retry creation. |
| Node key/existence creation fails | Nodes/relationships are missing mandatory properties. | Count missing records and backfill or fix data before migration. |
| Type constraint creation fails | Data holds a different type than declared, or version/edition lacks support. | Audit stored types and feature support, then fix or convert in a controlled step. |
| Constraint creation query unauthorized | Account lacks schema management privileges on the target database. | Verify role privileges and database target; use an appropriate migration account. |
| `IF NOT EXISTS` succeeds, yet schema differs from expectations | A constraint already existed under another name/structure, or was not created as intended. | Compare `SHOW CONSTRAINTS` against the migration spec and resolve discrepancies explicitly. |
| Requests write duplicate data after dropping constraint | Uniqueness is no longer enforced by the database. | Plan cutover timing, throttle writes, or apply alternate safeguards during migration. |
| Queries slow down after dropping a constraint | The constraint-owned index was dropped; query plan changed. | Inspect `PROFILE` and standalone index needs rather than guessing indexes. |
| Using `ASSERT` syntax on a newer system | Script was written for an older Neo4j release. | Standardize migrations on `FOR ... REQUIRE ...` syntax matching the target version. |

**Compatibility note:** older Neo4j documentation may use `CREATE CONSTRAINT ... ASSERT ...`. Examples in this lesson use `FOR ... REQUIRE ...` syntax from the Neo4j 5 line. When upgrading from legacy systems, reconcile syntax, constraint names, and constraint types rather than mixing two DDL styles in the same migration.

## 9. Verification Scenario in a Test Database

Run the write and delete commands in this section **only in a test database**, after confirming the example codes do not affect live data.

**Step 1 — Create uniqueness for an isolated test label:**

~~~cypher
CREATE CONSTRAINT demo_customer_code_unique IF NOT EXISTS
FOR (c:DemoCustomer)
REQUIRE c.code IS UNIQUE;
~~~

**Step 2 — Create a node with a key:**

~~~cypher
CREATE (:DemoCustomer {code: 'DEMO-001', name: 'An'});
~~~

**Step 3 — Attempt a duplicate record to observe the expected error:**

~~~cypher
CREATE (:DemoCustomer {code: 'DEMO-001', name: 'Binh'});
~~~

The third statement must be rejected if the constraint in Step 1 succeeded. When it fails, do not assume every other constraint type works too; test the exact target type and entity.

**Step 4 — Inspect status, then remove the test node and constraint:**

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
WHERE name = 'demo_customer_code_unique'
RETURN name, type, labelsOrTypes, properties;
~~~

~~~cypher
MATCH (c:DemoCustomer {code: 'DEMO-001'})
DELETE c;
~~~

~~~cypher
DROP CONSTRAINT demo_customer_code_unique IF EXISTS;
~~~

In this scenario, `DemoCustomer` was created without relationships, so `DELETE` suffices. If a node has relationships, evaluate consequences before running `DETACH DELETE`, because it deletes connected relationships as well. Never run `MATCH (n) DETACH DELETE n` to clean up exercises on a database containing other data.

## 10. Practice Exercises

1. A system has `(:User {tenantId, username})`. Different tenants may reuse the same username, but usernames must not duplicate within the same tenant. Write the constraint and a query to find violating pairs before creation.
2. Every `:Order` must have an `orderNo` that is unique **within a tenant**. Compare a composite uniqueness solution with a composite node key. In an edition that does not support node keys, what additional checks are needed?
3. A migration ran `CREATE CONSTRAINT IF NOT EXISTS` and printed "OK". Explain why `SHOW CONSTRAINTS` is still needed and which metadata fields to verify.
4. The operations team wants to drop the email constraint. Describe what can change for data integrity and query performance, and how to verify post-deployment.

Hint for Exercise 1:

~~~cypher
MATCH (u:User)
WHERE u.tenantId IS NOT NULL AND u.username IS NOT NULL
WITH u.tenantId AS tenantId, u.username AS username, count(*) AS soLuong
WHERE soLuong > 1
RETURN tenantId, username, soLuong
ORDER BY soLuong DESC, tenantId ASC, username ASC;
~~~

~~~cypher
CREATE CONSTRAINT user_tenant_username_unique IF NOT EXISTS
FOR (u:User)
REQUIRE (u.tenantId, u.username) IS UNIQUE;
~~~

When managing Neo4j constraints, always answer four questions: **which data invariant does the constraint protect, does existing data satisfy it yet, does the running version/edition support it, and how will we verify/roll back after deployment?** That workflow turns constraints into a controllable part of your property graph schema alongside indexes, Cypher queries, the Java Driver, and Spring Data Neo4j.

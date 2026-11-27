# Testing Constraints, Duplicate Data, and Missing Properties

Neo4j stores data in a **property graph** model: nodes carry labels and properties, while relationships have types, directions, and their own properties. In real systems, data may be written concurrently via the Java Driver, Spring Data Neo4j, raw Cypher, or CSV ingestion pipelines. Consequently, having a Java method "validate input" is not enough to guarantee the database remains free of **duplicate identifiers, missing required properties, mistyped values, or unintended duplicate relationships**.

This lesson belongs to the **Testing** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module and focuses on three questions: **which constraints is Neo4j actually enforcing, what anomalous data can still slip through, and which tests prove it?** Examples use Neo4j 5.x Cypher, with explicit notes for Enterprise Edition features. The Java section uses the Neo4j Java Driver, JUnit 5, and Testcontainers to test against a real database.

> **Rule:** Run data creation/deletion statements, constraint creation, and intentional failure tests **only in a dedicated test database**. Never test duplicate record creation in production, because data can be corrupted if an expected constraint is missing.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **property uniqueness**, **property existence**, **key constraints**, and **property type constraints**, and identify which require Neo4j Enterprise Edition.
2. Write queries to detect **duplicate key values**, post-normalization duplicates, duplicate relationships, and missing properties.
3. Test both **valid and invalid** cases, verifying that failed transactions leave no partial writes behind.
4. Explain why a **uniqueness constraint** does not imply the property is mandatory.
5. Use `MERGE` properly during data ingestion while understanding why `MERGE` does not replace integrity constraint enforcement.
6. Build integration tests with the Java Driver and Testcontainers, and verify **actual database state** after each operation.

## 2. Understanding constraint types accurately

Suppose the model has customers `:QaCustomer` with properties `customerId`, `email`, `name`, and orders `:QaOrder` with `orderId`, `amount`:

~~~text
(:QaCustomer {customerId: 'C01', email: 'an@example.test'})
        |
        | [:PLACED]
        v
(:QaOrder {orderId: 'O01', amount: 120000})
~~~

At the business level, rules might state "every customer must have an ID", "no two customers may share an ID", and "each order belongs to exactly one customer". **Not every rule is enforced by a single built-in constraint.**

| Constraint type | Guarantees | Requires property to exist? | Edition |
|---|---|---|---|
| **Property uniqueness** | Value, or **tuple of values**, is unique within a label/type | **No**; records missing the property do not violate uniqueness | Community and Enterprise |
| **Property existence** | Property must exist on every node/relationship with that label/type | **Yes** | Enterprise |
| **Node/relationship key** | Property must exist **and** its value/tuple must be unique | **Yes** | Enterprise |
| **Property type** | Property has the declared type when present | **Does not automatically** make the property mandatory | Enterprise |

**The most important takeaway:** if only a unique constraint exists on `customerId`, a node without `customerId` can still be created. To require every `:QaCustomer` node to carry an ID, combine application validation with an **existence/key constraint** where supported by your edition.

Newer Neo4j versions may introduce additional constraint types (such as label/type constraints in newer schema models). When designing tests for Neo4j 5.x, rely only on the types supported by your installed version.

### 2.1. Creating uniqueness constraints

~~~cypher
CREATE CONSTRAINT qa_customer_id_unique IF NOT EXISTS
FOR (c:QaCustomer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT qa_order_id_unique IF NOT EXISTS
FOR (o:QaOrder)
REQUIRE o.orderId IS UNIQUE;
~~~

These are property-based constraints. They also create a **backing index** that helps `MATCH`/`MERGE` look up nodes by key. `IF NOT EXISTS` makes the statement safer to re-run, but it does not prove the database already has **all expected business constraints**.

If existing data already violates uniqueness, creating the constraint **cannot succeed**. Therefore, on legacy data, run duplicate-detection queries **before executing the constraint migration**.

### 2.2. Property existence and node key (Enterprise)

The following statements are alternative or supplementary design options depending on version/edition; **do not run all of them blindly**:

~~~cypher
// Neo4j Enterprise: every QaRequiredCustomer node must have customerId.
CREATE CONSTRAINT qa_required_customer_id_exists IF NOT EXISTS
FOR (c:QaRequiredCustomer)
REQUIRE c.customerId IS NOT NULL;
~~~

~~~cypher
// Neo4j Enterprise: customerId is mandatory and must be unique.
CREATE CONSTRAINT qa_required_customer_id_key IF NOT EXISTS
FOR (c:QaRequiredCustomer)
REQUIRE c.customerId IS NODE KEY;
~~~

A **node key** combines **existence + uniqueness**. Depending on your version and existing schema, avoid creating redundant constraints. A failed constraint creation on legacy data does not automatically fix records with missing properties.

### 2.3. Multi-property uniqueness

If an `externalId` only needs to be unique **within each tenant**, the following model fits better than system-wide uniqueness:

~~~cypher
CREATE CONSTRAINT qa_tenant_customer_unique IF NOT EXISTS
FOR (c:QaTenantCustomer)
REQUIRE (c.tenantId, c.externalId) IS UNIQUE;
~~~

Two nodes sharing `externalId = 'U01'` across different tenants `T01` and `T02` **do not violate** this constraint. Two nodes sharing **both** values will violate it. However, if either property **is missing**, composite uniqueness **does not require** the node to possess the full key. On Enterprise, you can use a **composite node key** if both properties are mandatory:

~~~cypher
// Neo4j Enterprise, used when both keys are required.
CREATE CONSTRAINT qa_tenant_customer_key IF NOT EXISTS
FOR (c:QaTenantCustomer)
REQUIRE (c.tenantId, c.externalId) IS NODE KEY;
~~~

In a real system, choose **one consistent constraint strategy** rather than applying both statements to the same schema without reviewing existing constraints and indexes.

### 2.4. Relationships and property types

Neo4j also supports constraints on **relationship properties** in supporting versions:

~~~cypher
CREATE CONSTRAINT qa_payment_id_unique IF NOT EXISTS
FOR ()-[r:QA_PAYMENT]-()
REQUIRE r.paymentId IS UNIQUE;
~~~

This guarantees each present `paymentId` value is unique among `QA_PAYMENT` relationships, yet it does **not** mean a pair of nodes can only be connected by a single `QA_PAYMENT` relationship. Checking for "multiple edges of the same type between the same pair of nodes" is a separate rule.

With Enterprise and Neo4j versions supporting property type constraints, for example:

~~~cypher
CREATE CONSTRAINT qa_order_amount_integer IF NOT EXISTS
FOR (o:QaOrder)
REQUIRE o.amount IS :: INTEGER;
~~~

A type constraint guards data type when `amount` **is present**; if business rules also forbid missing `amount`, add an **existence** check or separate validation. An `INTEGER` type constraint also **does not guarantee non-negativity**; a rule like `amount >= 0` must be verified separately.

## 3. Understanding `null` and nonexistent properties in Neo4j

In Cypher, accessing a property absent from a node returns `null`:

~~~cypher
MATCH (c:QaCustomer)
WHERE c.customerId IS NULL
RETURN elementId(c) AS nodeId, c.name AS name;
~~~

Neo4j does not store a `null` property like a regular value: **running `SET c.customerId = null` removes that property** from the node. Example on a node without an existence constraint:

~~~cypher
CREATE (c:QaCustomer {customerId: 'C-TEMP', name: 'Temp'})
SET c.customerId = null
RETURN c.name AS name, c.customerId AS id;
// id = null because the customerId property was removed.
~~~

If `:QaCustomer` only has a uniqueness constraint, the snippet above succeeds (because a node lacking the key does not violate uniqueness); if the label has an existence or key constraint, attempting to remove the required property is rejected.

**Never use `= null` or `<> null` to check for missing data.** In Cypher, use `IS NULL` and `IS NOT NULL`:

~~~cypher
MATCH (c:QaCustomer)
WHERE c.email IS NULL
RETURN elementId(c) AS nodeId;
~~~

An **empty** property and a **missing** property are also different:

| Data | `c.email IS NULL` | `c.email = ''` | Can violate uniqueness on email? |
|---|---|---|---|
| Missing `email` | `true` | `null` | No, not merely for lacking email |
| `email = ''` | `false` | `true` | Yes, if another node already has an empty string |
| `email = 'a@example.test'` | `false` | `false` | Yes, if another node has the same value |
| `email = ' A@Example.test '` | `false` | `false` | Not automatically equal to `'a@example.test'` under raw comparison |

If business logic treats emails as case-insensitive or trims whitespace, normalize into a **consistent business key** before creating a constraint. Uniqueness on raw `email` **does not perform normalization automatically**.

## 4. Preparing test data on an isolated database

In a fresh test database, after creating constraints `qa_customer_id_unique` and `qa_order_id_unique` from Section 2, run:

~~~cypher
CREATE (a:QaCustomer {
    customerId: 'C01',
    name: 'An',
    email: 'An@Example.test'
})
CREATE (b:QaCustomer {
    customerId: 'C02',
    name: 'Bình',
    email: ' binh@example.test '
})
CREATE (o1:QaOrder {orderId: 'O01', amount: 120000})
CREATE (o2:QaOrder {orderId: 'O02', amount: 180000})
CREATE (a)-[:PLACED]->(o1)
CREATE (a)-[:PLACED]->(o2)
RETURN a.customerId AS firstCustomer,
       b.customerId AS secondCustomer;
~~~

Expected graph:

~~~mermaid
flowchart LR
    C1["QaCustomer C01<br/>An"]
    C2["QaCustomer C02<br/>Bình"]
    O1["QaOrder O01<br/>120000"]
    O2["QaOrder O02<br/>180000"]
    C1 -->|PLACED| O1
    C1 -->|PLACED| O2
~~~

When only this data exists:

~~~cypher
MATCH (c:QaCustomer)
WITH count(c) AS customerCount
MATCH (o:QaOrder)
RETURN customerCount, count(o) AS orderCount;
// customerCount = 2, orderCount = 2
~~~

**Do not re-run the `CREATE` fixture script repeatedly** or it will hit uniqueness constraints; tests needing a fresh setup should clear the fixture in the test database, roll back transactions, or start a new database/container. Explicitly state the initial state assumed by every example.

## 5. Testing a constraint with valid and invalid cases

### 5.1. Valid case: two distinct keys

On a test database with the uniqueness constraint where `C03` does not yet exist:

~~~cypher
CREATE (c:QaCustomer {customerId: 'C03', name: 'Chi'})
RETURN c.customerId AS id;
~~~

**Expected:** successfully creates one `C03` node. This is a **positive test**; if it fails, either `C03` already existed in baseline data or another constraint intervened.

### 5.2. Invalid case: duplicate identifier

Assuming `C01` already exists:

~~~cypher
CREATE (:QaCustomer {customerId: 'C01', name: 'Duplicate ID'});
~~~

**Expected:** Neo4j rejects the statement due to a uniqueness constraint violation. After the error, verify:

~~~cypher
MATCH (c:QaCustomer {customerId: 'C01'})
RETURN count(c) AS occurrences;
// occurrences = 1 if the initial fixture was valid.
~~~

**What must be asserted:** not only "an exception was thrown", but also "**the node count for that ID remains 1**". Exact error codes/messages may vary across versions (e.g., `Neo.ClientError.Schema.*`); do not write tests tightly coupled to exact `getMessage()` wording.

### 5.3. Surprising case: omitting the unique property

On a database that only has **uniqueness** and **no existence/key constraint** for `:QaCustomer(customerId)`:

~~~cypher
CREATE (:QaCustomer {name: 'Customer without ID'});
CREATE (:QaCustomer {name: 'Another customer without ID'});
~~~

Both statements can **succeed** even with a uniqueness constraint on `customerId`. This test prevents the false conclusion that "unique means the ID cannot be missing".

### 5.4. Mandatory ID case: existence/key constraint

On **Neo4j Enterprise** with a dedicated label `:QaRequiredCustomer` carrying a key constraint:

~~~cypher
CREATE (:QaRequiredCustomer {name: 'Missing ID'});
~~~

**Expected:** the transaction is rejected because `customerId` is required. On Community Edition, this constraint type does not exist; you must test application-level validation or another mechanism rather than falsely asserting "the database blocks missing IDs" when no constraint is present.

## 6. Detecting duplicates **before** creating constraints

In a legacy system, data may have been ingested before constraints existed. Creating a uniqueness constraint right away will fail the migration while leaving duplicate records unresolved. Before adding constraints, audit using the exact **business key**.

### 6.1. Nodes with the same ID

~~~cypher
MATCH (c:QaCustomer)
WHERE c.customerId IS NOT NULL
WITH c.customerId AS customerId, count(*) AS occurrences
WHERE occurrences > 1
RETURN customerId, occurrences
ORDER BY occurrences DESC, customerId;
~~~

If no constraint exists and two nodes share `C01`, the result includes `C01 | 2`. This query does not modify data; it only reports keys occurring more than once.

### 6.2. Duplicates after value normalization

Two emails `'An@Example.test'` and `' an@example.test '` are not byte-identical. If business rules treat them as the same email after `trim` and `toLower`:

~~~cypher
MATCH (c:QaCustomer)
WHERE c.email IS NOT NULL
WITH toLower(trim(c.email)) AS normalizedEmail,
     count(*) AS occurrences
WHERE normalizedEmail <> '' AND occurrences > 1
RETURN normalizedEmail, occurrences
ORDER BY occurrences DESC, normalizedEmail;
~~~

**Note:** this query assumes `email` is a **string**. If ingestion produced mistyped properties, sanitize or type-check before calling string functions. Real-world email normalization has nuances beyond lowercasing; never strip dots, plus-tags, or alter the local-part unless confirmed by business rules.

If uniqueness must hold on normalized emails, store a dedicated property such as `emailNormalized`, keep it updated via the same rule, and create a constraint on that property:

~~~cypher
CREATE CONSTRAINT qa_email_normalized_unique IF NOT EXISTS
FOR (c:QaCustomer)
REQUIRE c.emailNormalized IS UNIQUE;
~~~

Before creating this constraint on legacy data, backfill the normalized property and **resolve all duplicate groups**. Never place a constraint on a property that write paths do not maintain consistently.

### 6.3. Missing properties and whitespace-only strings

~~~cypher
MATCH (c:QaCustomer)
WHERE c.customerId IS NULL
RETURN elementId(c) AS nodeId, c.name AS name;
~~~

~~~cypher
MATCH (c:QaCustomer)
WHERE c.email IS NOT NULL
  AND trim(c.email) = ''
RETURN elementId(c) AS nodeId, c.customerId AS customerId;
~~~

The first query finds missing properties. The second finds emails that are empty or whitespace-only. Their record counts are **not necessarily equal**, and you should never use `count(c.email)` to count missing nodes because `count(expression)` ignores `null` values.

### 6.4. Multi-tenant duplicates

~~~cypher
MATCH (c:QaTenantCustomer)
WHERE c.tenantId IS NOT NULL
  AND c.externalId IS NOT NULL
WITH c.tenantId AS tenantId,
     c.externalId AS externalId,
     count(*) AS occurrences
WHERE occurrences > 1
RETURN tenantId, externalId, occurrences
ORDER BY occurrences DESC, tenantId, externalId;
~~~

If the same `externalId` appears in two different tenants, this query **does not flag a duplicate**; that is the intended behavior for a uniqueness constraint on `(tenantId, externalId)`.

## 7. Detecting duplicate relationships and anomalous references

Neo4j permits multiple relationships of the same type between the same pair of nodes when allowed by data/schema. A uniqueness constraint on a **relationship property** does not stop two `PLACED` edges if they lack a relationship ID or carry different IDs.

Suppose the graph has two `PLACED` edges from customer `C01` to order `O01`:

~~~cypher
MATCH (c:QaCustomer {customerId: 'C01'}),
      (o:QaOrder {orderId: 'O01'})
CREATE (c)-[:PLACED]->(o);
// Run only on a test database to intentionally create a duplicate edge.
~~~

Check edge counts per node pair:

~~~cypher
MATCH (c:QaCustomer)-[r:PLACED]->(o:QaOrder)
WITH c.customerId AS customerId,
     o.orderId AS orderId,
     count(r) AS edgeCount
WHERE edgeCount > 1
RETURN customerId, orderId, edgeCount
ORDER BY edgeCount DESC;
~~~

With the sample data and duplicate-edge command above, the expected result is `C01 | O01 | 2`.

**Important:** define "duplicate" accurately according to the domain. Two repeat purchases of the same product may represent **two distinct actions**, not duplicate edges to delete. Only treat two relationships as invalid when the model requires **at most one relationship per node pair/type** or per identical event ID.

### Orders with no customer

~~~cypher
MATCH (o:QaOrder)
WHERE NOT EXISTS {
    MATCH (:QaCustomer)-[:PLACED]->(o)
}
RETURN o.orderId AS orderWithoutCustomer;
~~~

### Orders owned by multiple customers

~~~cypher
MATCH (c:QaCustomer)-[:PLACED]->(o:QaOrder)
WITH o.orderId AS orderId, count(DISTINCT c) AS owners
WHERE owners > 1
RETURN orderId, owners;
~~~

These two checks express **cardinality** rules of the model (when each order must belong to exactly one customer). A uniqueness constraint on `orderId` alone cannot replace them. In Neo4j 5, enforce and check them with Cypher and the business layer; in newer versions, advanced schema constraints may offer different capabilities—consult the version documentation.

## 8. `MERGE` enables safe re-ingestion, but must be tested

When importing from CSV or the Java Driver, use `MERGE` on an identifier protected by a unique constraint:

~~~cypher
MERGE (c:QaCustomer {customerId: $customerId})
ON CREATE SET c.createdAt = datetime()
SET c.name = $name
RETURN c.customerId AS id, c.name AS name;
~~~

With the same `customerId`, re-running the query typically **matches the existing node** instead of creating a new one. However:

- `MERGE` on multiple properties at once, such as `{customerId, name}`, treats two different name versions as distinct patterns and can create duplicates or fail on constraints. Always `MERGE` on a **stable key**, then `SET` mutable properties.
- If the `customerId` key is **empty/missing**, `MERGE` may fail to construct a valid pattern. Validate input before calling.
- `MERGE` does not replace constraints when concurrent transactions write simultaneously. Uniqueness constraints protect database-level uniqueness.
- For relationships, `MERGE (c)-[:PLACED]->(o)` when both `c` and `o` are properly **bound** prevents recreating the same relationship pattern on retries. Still, verify whether business rules allow multiple edges of the same type between the same nodes.
- Re-running transactions with additive updates like `SET c.balance = c.balance + $amount` can be **non-idempotent**, even when `MERGE` is used on the node.

A useful import test runs the same snapshot **twice** and compares:

| Metric | After run 1 | Expected after run 2 |
|---|---:|---:|
| Node count for `C01` | 1 | 1 |
| Node count for `O01` | 1 | 1 |
| Edge count for `C01 -[:PLACED]-> O01` | 1 | 1 |
| Total revenue | Matches source data | Unchanged if no new additive business event |

Never treat a `MERGE` statement succeeding without error as proof that the entire source loaded cleanly: a `MATCH` missing a target node can cause an input row to **skip creating a relationship** without throwing an exception.

## 9. Testing transaction rollback when one statement fails

Neo4j supports ACID transactions. If **one transaction** contains multiple operations and a later operation violates a constraint causing failure, **all uncommitted changes in that transaction must roll back**. Previously committed transactions are unaffected.

Logical example:

~~~text
Transaction A:
  1. CREATE QaCustomer {customerId: 'C-NEW'}   // valid
  2. CREATE QaCustomer {customerId: 'C01'}     // duplicates existing key
  3. COMMIT                                   // cannot commit successfully

Result to verify:
  - Existing node C01 still has exactly one copy.
  - Node C-NEW does not exist after rollback.
~~~

**Warning:** if you run each `CREATE` above as two separate auto-commit transactions, the first statement will already have committed before the second fails. To test **atomic** rollback, place both inside a single transaction (via the Java Driver's `executeWrite` or an explicit transaction in tests).

When testing, do not stop at `assertThrows(...)`. Re-query the counts of `C-NEW` and `C01` **after the failing transaction has rolled back**, using a new read transaction/session.

## 10. Java Driver integration testing with Testcontainers

A unit test with a mocked `Session` can verify Java error handling, but it cannot validate real Neo4j constraints. For duplicate-data and rollback tests, run **integration tests against a real database**.

### 10.1. Test dependencies

Gradle example (Java 17+, JUnit 5; versions managed via your project's BOM):

~~~groovy
dependencies {
    implementation 'org.neo4j.driver:neo4j-java-driver'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:neo4j'
}

test {
    useJUnitPlatform()
}
~~~

The example below uses **Testcontainers 1.x** (package `org.testcontainers.containers.Neo4jContainer`) and **Neo4j Java Driver 5.x/6.x**. If your project uses Testcontainers 2.x, the Neo4j container package may differ; adjust to your chosen version and confirm dependency resolution. Never assume code compiles/runs without verifying your BOM.

### 10.2. Complete integration test class

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.exceptions.ClientException;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class CustomerConstraintsIT {
    private static final String PASSWORD = "local-test-only";

    @Container
    static final Neo4jContainer<?> neo4j =
            new Neo4jContainer<>("neo4j:5.26")
                    .withAdminPassword(PASSWORD);

    private static Driver driver;

    @BeforeAll
    static void prepareSchema() {
        driver = GraphDatabase.driver(
                neo4j.getBoltUrl(),
                AuthTokens.basic("neo4j", PASSWORD));
        driver.verifyConnectivity();

        try (Session session = driver.session()) {
            session.run("""
                    CREATE CONSTRAINT qa_customer_id_unique IF NOT EXISTS
                    FOR (c:QaCustomer)
                    REQUIRE c.customerId IS UNIQUE
                    """).consume();
        }
    }

    @BeforeEach
    void clearTestNodes() {
        try (Session session = driver.session()) {
            session.executeWrite(tx -> {
                tx.run("""
                        MATCH (c:QaCustomer)
                        DETACH DELETE c
                        """).consume();
                return null;
            });
        }
    }

    @Test
    void rejectsDuplicateAndPreservesOriginal() {
        try (Session session = driver.session()) {
            session.executeWrite(tx -> {
                tx.run("""
                        CREATE (:QaCustomer {
                            customerId: 'C01', name: 'An'
                        })
                        """).consume();
                return null;
            });

            ClientException error = assertThrows(
                    ClientException.class,
                    () -> session.executeWrite(tx -> {
                        tx.run("""
                                CREATE (:QaCustomer {
                                    customerId: 'C01',
                                    name: 'Duplicate'
                                })
                                """).consume();
                        return null;
                    }));

            assertTrue(error.code().startsWith("Neo.ClientError."));

            long count = session.executeRead(tx -> tx.run("""
                    MATCH (c:QaCustomer {customerId: 'C01'})
                    RETURN count(c) AS n
                    """).single().get("n").asLong());

            assertEquals(1L, count);
        }
    }

    @Test
    void uniquenessDoesNotRequirePropertyToExist() {
        try (Session session = driver.session()) {
            session.executeWrite(tx -> {
                tx.run("""
                        CREATE (:QaCustomer {name: 'No ID 1'})
                        CREATE (:QaCustomer {name: 'No ID 2'})
                        """).consume();
                return null;
            });

            long missing = session.executeRead(tx -> tx.run("""
                    MATCH (c:QaCustomer)
                    WHERE c.customerId IS NULL
                    RETURN count(c) AS n
                    """).single().get("n").asLong());

            assertEquals(2L, missing);
        }
    }

    @Test
    void failureRollsBackWholeTransaction() {
        try (Session session = driver.session()) {
            session.executeWrite(tx -> {
                tx.run("""
                        CREATE (:QaCustomer {
                            customerId: 'C01'
                        })
                        """).consume();
                return null;
            });

            assertThrows(ClientException.class,
                    () -> session.executeWrite(tx -> {
                        tx.run("""
                                CREATE (:QaCustomer {
                                    customerId: 'C-NEW'
                                })
                                """).consume();
                        tx.run("""
                                CREATE (:QaCustomer {
                                    customerId: 'C01'
                                })
                                """).consume();
                        return null;
                    }));

            Map<String, Object> counts = session.executeRead(tx -> {
                var record = tx.run("""
                        MATCH (c:QaCustomer)
                        RETURN
                          count(CASE WHEN c.customerId = 'C01'
                                THEN 1 END) AS oldCount,
                          count(CASE WHEN c.customerId = 'C-NEW'
                                THEN 1 END) AS newCount
                        """).single();
                return Map.of(
                        "old", record.get("oldCount").asLong(),
                        "new", record.get("newCount").asLong());
            });

            assertEquals(1L, counts.get("old"));
            assertEquals(0L, counts.get("new"));
        }
    }

    @AfterAll
    static void closeDriver() {
        if (driver != null) {
            driver.close();
        }
    }
}
~~~

In the class above, test data is cleared before each test and the container is dedicated to the class. **Every write query calls `consume()`** so query errors surface before the callback finishes. With managed transaction `executeWrite`, the driver may retry **transient errors** per policy, whereas constraint validation errors cannot succeed on retry.

**Meaning of the assertions:**

| Test | Input condition | Required outcome |
|---|---|---|
| `rejectsDuplicateAndPreservesOriginal` | `C01` already exists, attempt `CREATE` another `C01` | Exception; exactly 1 `C01` node remains |
| `uniquenessDoesNotRequirePropertyToExist` | Uniqueness only, create two nodes without ID | Succeeds; 2 nodes with missing property exist |
| `failureRollsBackWholeTransaction` | Same transaction creates `C-NEW` then duplicate `C01` | Exception; `C-NEW` gone; `C01` count remains 1 |

**Do not run this sample test class on a shared DB:** `clearTestNodes` deletes all nodes carrying the `QaCustomer` label in the current database. That is appropriate only in an **isolated Neo4j Testcontainer** owned by the test suite. On shared environments, tests must use isolated namespaces/fixtures and clean up by their own test IDs.

## 11. Testing mandatory properties in Enterprise

If using Enterprise Edition with this constraint created:

~~~cypher
CREATE CONSTRAINT qa_required_customer_key IF NOT EXISTS
FOR (c:QaRequiredCustomer)
REQUIRE c.customerId IS NODE KEY;
~~~

Include two cases:

~~~cypher
// Valid: has ID and is not duplicated.
CREATE (:QaRequiredCustomer {customerId: 'R01', name: 'An'});
~~~

~~~cypher
// Invalid: missing customerId property.
CREATE (:QaRequiredCustomer {name: 'No ID'});
~~~

In Java, the basic assertion looks like:

~~~java
assertThrows(ClientException.class, () ->
    session.executeWrite(tx -> {
        tx.run("""
            CREATE (:QaRequiredCustomer {name: 'No ID'})
            """).consume();
        return null;
    })
);
~~~

This Java snippet assumes `session` is connected to an **Enterprise test** database where the constraint exists. On Community Edition, tag or skip this test deliberately based on edition rather than reporting an unsupported feature as an application logic failure.

Beyond inserting a node without an ID, also test:

1. Setting `SET c.customerId = null` on an existing node, expecting rejection.
2. Changing `customerId` to a value already held by another node, expecting rejection.
3. Writing a valid node, expecting success.
4. Re-querying database state after each failed transaction.

### Property types and blank values

If `QaOrder.amount` must be `INTEGER` and `>= 0`:

- A property type constraint (Enterprise, supported versions) checks value **type**, not **domain range**.
- An existence/key constraint enforces mandatory presence where applicable.
- Java/Spring Data Neo4j validation must reject `amount < 0` when forbidden by business rules, even without a database-level numeric range constraint.

A thorough test checks not only the **right type** but also boundary values `0`, negative numbers, very large numbers, and null/missing cases.

## 12. Testing duplicates in batch imports

A CSV source might contain three rows:

~~~csv
customerId,name
C01,An
C02,Bình
C01,An updated
~~~

If using `CREATE` for every row against a database with a uniqueness constraint, the transaction containing the third row will fail. If importing in **multiple transactions/batches**, earlier committed batches will **not automatically roll back**. If using `MERGE` on `customerId`, data may be updated according to the `SET` policy.

Define **the exact goal**:

| Import policy | Expectation for repeated `C01` |
|---|---|
| Reject source with duplicate keys | Fail before writing or quarantine duplicate rows |
| Upsert, keeping the latest record by business order | One `C01` node, fields reflect the **explicitly defined** latest record |
| Write-once only | One `C01` node, later rows do not overwrite key attributes |
| Store multi-version history | Create entities/versions with distinct IDs; do not use `customerId` alone as unique key per history record |

Do not rely on "the last CSV row wins" during concurrent processing or when rows are batched with `UNWIND`/optimizations where **application order is not guaranteed**. If business rules require the newest record, data should carry a timestamp/version and the selection logic must be explicitly designed and tested.

### Verification checklist after an import run

1. **Source row counts:** how many rows, duplicate keys, missing keys, and mistyped fields?
2. **Node count by key:** does each valid ID map to exactly one node?
3. **Relationship count per node pair:** are there duplicate edges or relationships missing a target node?
4. **Aggregate reconciliation:** do node counts, order counts, and total amounts match business rules without row multiplication?
5. **Re-run the same source snapshot:** do node and edge counts remain stable without unintended growth?
6. **Inject a batch failure:** committed batches remain intact; the failed batch rolls back; pipeline resumes cleanly from checkpoint if required.

Import summary metrics like **rows read** or **transactions committed** do not equal newly created nodes. Tests must verify **actual graph state**, not just job exit codes.

## 13. Spring Data Neo4j: testing schema and real data

In Spring Data Neo4j, annotations like `@Node`, `@Id`, and `@Relationship` map Java entities, yet they **do not prove Neo4j has the expected uniqueness/existence constraints**. A repository can appear to work normally even when the database lacks business constraints.

Example:

~~~java
@Node("QaCustomer")
public class Customer {
    @Id
    private String customerId;
    private String email;
    // getters, constructor, and other mappings...
}
~~~

`@Id` identifies the entity in SDN mapping; it does not replace the schema migration step that creates:

~~~cypher
CREATE CONSTRAINT qa_customer_id_unique IF NOT EXISTS
FOR (c:QaCustomer)
REQUIRE c.customerId IS UNIQUE;
~~~

When using `@DataNeo4jTest` with Testcontainers, include separate tests for:

- **Schema test:** run `SHOW CONSTRAINTS` to confirm the constraint actually exists in the test database.
- **Negative write test:** attempt to write a duplicate ID or missing mandatory field; assert exception and post-rollback graph state.
- **Mapping test:** save/load entities and relationships to verify field mappings.
- **Repository query test:** invoke real repository methods against a fixture containing duplicates, missing properties, and nulls.

Tests that only mock `Neo4jRepository` cannot catch missing database constraints. Furthermore, if `@DataNeo4jTest` wraps tests in a Spring-managed transaction that rolls back at test end, understand which transactions can see uncommitted data if you query from an external driver.

## 14. Inspecting existing schema with `SHOW CONSTRAINTS`

Before concluding that the system protects data integrity, inspect schema status with a privileged account:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

In module schema tests, filter for a specific constraint:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
WHERE name = 'qa_customer_id_unique'
RETURN name, type, labelsOrTypes, properties;
~~~

**What to verify:** exact **label/type**, exact properties, and exact **constraint type**—not merely a matching name. Constraint names may evolve across migrations, while schema semantics must hold.

`SHOW CONSTRAINTS` requires appropriate privileges. If a test is rejected for lacking schema permissions, that is an **environment or privilege configuration issue**, not proof that the constraint is absent.

### Duplicate data can break migrations

If a legacy system lacks a constraint, run this before applying the migration:

~~~cypher
MATCH (c:QaCustomer)
WHERE c.customerId IS NOT NULL
WITH c.customerId AS id, count(*) AS occurrences
WHERE occurrences > 1
RETURN id, occurrences;
~~~

When duplicates are discovered, **never blindly delete "extra nodes"** with `LIMIT 1` without inspecting relationships, ownership, and business history. Two duplicate-key nodes may hold different relationships; merging requires rules for edges, conflicting properties, and a rollback plan. This lesson covers **detection and verification**, not speculative production data merging.

## 15. Matrix of test cases to maintain in CI

| Category | Fixture | Expected behavior | Verification method |
|---|---|---|---|
| **Unique – valid** | Two customers with different IDs | Write succeeds | `count` by ID |
| **Unique – duplicate** | Two customers with same ID | Second write rejected | Exception + 1 node remains |
| **Unique – missing** | Two nodes without ID | With **uniqueness only**, both can exist | `IS NULL` + node count |
| **Existence/key – missing** | Node lacking mandatory property | Rejected on Enterprise when constraint exists | Exception + no node created |
| **Composite unique** | Same externalId, different tenant | Succeeds | Count per key pair |
| **Composite unique – duplicate pair** | Same tenant and externalId | Rejected | Exception + pair count |
| **Empty property** | `email = ''` or whitespace | Handled per business validation | Empty/trim check |
| **Wrong type** | `amount = '1000'` under integer constraint | Rejected if type constraint exists | Exception or validation |
| **Negative value** | `amount = -1` | Rejected per business rule | Service validation/test |
| **Duplicate relationship** | Two `PLACED` edges on same node pair | Detected/forbidden per model | `count(r)` per pair |
| **Missing relationship** | Order with no customer | Detected if required by domain | `NOT EXISTS { MATCH ... }` |
| **Rollback** | Create valid node then violate constraint in same tx | No partial write left | Query after rollback |
| **Retry import** | Re-import same snapshot | No extra nodes/edges added | Before/after comparison |

**Never cram every test into one transaction expecting the database to keep partial data after an error.** Tests must explicitly define which transaction rolls back, which commits, and which tests need a clean graph.

## 16. Testing pitfalls that lead to false conclusions

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| Checking only `@Id` in Java | Does not prove DB has a unique constraint | Inspect `SHOW CONSTRAINTS` and test duplicate writes |
| Assuming uniqueness makes a property mandatory | Nodes missing the property remain valid | Add existence/key constraint where supported |
| Treating `null` as a stored property value | `SET property = null` removes the property | Use `IS NULL`; check migrations and validation |
| Checking only `assertThrows` | Partial writes may have committed across transactions | Re-query the graph and commit state |
| Asserting exact `getMessage()` text | Error wording changes across versions | Assert stable exception class or error code prefix |
| Creating constraints after importing duplicates | Migration fails | Detect and resolve duplicates first |
| Using `MERGE` on an entire property map | One changed field creates a new pattern | Merge on stable keys, `SET` mutable fields |
| Assuming different-case emails match | Constraints compare raw values | Normalize into a dedicated property before adding uniqueness |
| Treating two same-type edges as always duplicate | May represent distinct business events | Define the intended relationship key/granularity |
| Testing on a DB with unknown background data | Counts and constraints fail randomly | Use isolated Testcontainers/DB fixtures |
| Using the same repository to seed and verify | Both paths can share the same mapping bug | Cross-check via independent Cypher queries |
| Deleting an entire label in a shared DB | Wipes out other users' or tests' data | Clean up only inside test-owned DBs |

## 17. Practice exercises

### Exercise 1 — Uniqueness and missing properties

Given:

~~~cypher
CREATE CONSTRAINT qa_user_id_unique IF NOT EXISTS
FOR (u:QaUser)
REQUIRE u.userId IS UNIQUE;
~~~

Predict whether the two statements below violate the constraint on an empty database:

~~~cypher
CREATE (:QaUser {name: 'A'});
CREATE (:QaUser {name: 'B'});
~~~

<details>
<summary>Reference answer</summary>

Neither statement violates **uniqueness** because `userId` is absent. If business rules require `userId`, enforce it in application validation and consider an existence/key constraint on Enterprise. Never conclude uniqueness automatically blocks missing properties.

</details>

### Exercise 2 — Per-tenant uniqueness

Design a constraint for this dataset:

| tenantId | externalId |
|---|---|
| T01 | U01 |
| T02 | U01 |
| T01 | U02 |

Then describe what happens if `(T01, U01)` is inserted next.

<details>
<summary>Reference answer</summary>

~~~cypher
CREATE CONSTRAINT qa_user_tenant_ext_unique IF NOT EXISTS
FOR (u:QaTenantUser)
REQUIRE (u.tenantId, u.externalId) IS UNIQUE;
~~~

The first three rows are valid because each key **pair** is distinct. A duplicate `(T01, U01)` row will be rejected if written with the same label and properties once the constraint is active. Also test missing properties because composite uniqueness does not enforce presence of both fields.

</details>

### Exercise 3 — Distinguishing `null` and empty strings

Given three `:QaUser` nodes: one missing `email`, one with `email = ''`, and one with `email = '  '`. Write a Cypher query finding all records with missing or whitespace-only emails.

<details>
<summary>Reference answer</summary>

~~~cypher
MATCH (u:QaUser)
WHERE u.email IS NULL
   OR (u.email IS NOT NULL AND trim(u.email) = '')
RETURN elementId(u) AS nodeId, u.email AS email;
~~~

This query assumes any present `email` is a string. If data may be mistyped, validate or normalize types before calling `trim`.

</details>

### Exercise 4 — Rollback on constraint failure

Customer `C01` already exists. A new transaction creates `C03` and then attempts to create another `C01`. After the error, which nodes do you expect to exist? If the two statements run in two separate transactions, does the answer change?

<details>
<summary>Reference answer</summary>

Within the **same transaction**, the unique error rolls back the entire transaction; the original `C01` remains, while the new `C03` does not exist. If creating `C03` already committed in a **separate transaction**, `C03` persists even though the subsequent transaction creating `C01` fails.

</details>

### Exercise 5 — Duplicate node vs. duplicate relationship?

Order `O01` has a single `QaOrder` node, yet receives two `PLACED` edges from the same customer `C01`. Does uniqueness on `orderId` prevent these two edges? Write a detection query.

<details>
<summary>Reference answer</summary>

No. Uniqueness on `QaOrder.orderId` prevents two **order nodes** from sharing the same ID, not two **relationships** of the same type between two nodes.

~~~cypher
MATCH (c:QaCustomer)-[r:PLACED]->(o:QaOrder)
WITH c.customerId AS customerId,
     o.orderId AS orderId,
     count(r) AS edges
WHERE edges > 1
RETURN customerId, orderId, edges;
~~~

Only clean up pairs classified as duplicates after confirming the business rule.

</details>

### Exercise 6 — Designing an import test

A CSV file contains two rows for `C01`, one row missing an ID, and one valid row for `C02`. Propose three pre-import checks, three post-import reconciliation metrics, and one re-run test.

<details>
<summary>Suggested answer</summary>

Pre-import: detect duplicate keys, missing keys, and invalid types/values; decide whether to reject or upsert. Post-import: count of unique valid keys, actual persisted node count per key, and relationship counts / business totals. Re-run the same snapshot and verify node/edge counts do not increase if idempotency is required. Distinguish source row count from newly created record count.

</details>

## 18. Official documentation

- [Neo4j Cypher — Constraints overview](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Neo4j Cypher — Creating constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Neo4j Cypher — Schema syntax](https://neo4j.com/docs/cypher-manual/current/schema/syntax/)
- [Neo4j Cypher — Listing constraints with SHOW CONSTRAINTS](https://neo4j.com/docs/cypher-manual/current/schema/constraints/list-constraints/)
- [Neo4j Cypher — Working with null](https://neo4j.com/docs/cypher-manual/current/values-and-types/working-with-null/)
- [Neo4j Java Driver — Managed and explicit transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver — Queries and error handling](https://neo4j.com/docs/java-manual/current/query-simple/)
- [Testcontainers — Neo4j module](https://java.testcontainers.org/modules/databases/neo4j/)

The `current` URLs reflect the latest documentation at the time of reading. When studying or deploying, match **your exact Neo4j version/edition** and Java/Testcontainers library versions; certain constraint types are available only in Enterprise.

## 19. Key takeaways

- **Uniqueness protects against duplicate values; it does not make properties mandatory.** Existence/key constraints enforce required properties where supported by your edition.
- **`IS NULL` detects missing properties; empty strings and whitespace-only values must be checked separately.**
- **Test both directions:** valid data is accepted, invalid data is rejected, and post-error graph state remains consistent.
- **Duplicates happen at multiple levels:** nodes by business key, post-normalization keys, multi-tenant tuples, relationships per node pair/type, and dangling references.
- **`MERGE` supports idempotent imports when keyed stably**, yet it never replaces constraints, validation, and conflict-resolution policies.
- **Transactions define the rollback boundary.** When a transaction fails, verify both previously committed data and uncommitted writes from the failed transaction.
- **Integration tests on real Neo4j** paired with independent verification queries validate constraints, duplicates, and missing properties far better than mocks alone.

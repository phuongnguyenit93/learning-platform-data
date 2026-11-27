# Combining Constraints with MERGE to Prevent Duplicates Under Concurrent Writes

## 1. The Problem: Two Requests Creating the Same Entity

Neo4j stores data as a **property graph**: nodes represent entities, relationships represent connections, and properties hold information for each object. In multi-threaded or distributed systems, a single business entity can be written concurrently by multiple HTTP requests, queue workers, or ingestion jobs.

For example, a customer sync service receives two messages with the same **externalId = 'crm-2048'**. The goal is **only one Customer node** for this code, even if the two messages are processed almost simultaneously.

Cypher provides **MERGE** to match an existing graph pattern or create it if it does not yet exist:

~~~cypher
MERGE (c:Customer {externalId: $externalId})
RETURN c;
~~~

MERGE is well suited for **upsert** (find-or-create) operations. However, writing MERGE alone **does not replace** data integrity rules when multiple concurrent transactions simultaneously search for and create a non-existent key.

A practical solution combines:

1. **Choose a stable business key** to identify the node.
2. **Create a uniqueness constraint** on the exact label and property of that key.
3. **MERGE on the constrained key**, and only then write mutable properties.
4. **Design transactions and error/retry policies** for contention scenarios.
5. **Verify outcomes with queries and concurrency load tests**, rather than inferring correctness from a single sequential run.

This lesson focuses on the data model, Cypher, constraints, and concurrent write flows in Neo4j; the Java Driver example illustrates how to apply them in an application.

## 2. What Does MERGE Do, and What Does It Not Guarantee?

### 2.1. Match the Full Pattern, Create If Not Found

~~~cypher
MERGE (c:Customer {externalId: 'crm-2048'})
RETURN c.externalId AS externalId;
~~~

In a single execution:

- If a **Customer** node matching the pattern is found, MERGE uses that node.
- If not found, MERGE creates a **Customer** node with the corresponding **externalId** property.

Re-running the same statement sequentially normally returns the newly created node. This is convenient for idempotent writes. Yet the statement itself does not tell the database to **forbid all Customer nodes with duplicate externalId values**.

Do not think of MERGE as a constraint. **MERGE decides how a query handles a pattern; a constraint decides what data states are allowed to exist.**

### 2.2. Why Does Duplicate Risk Remain Under Concurrent Writes?

Suppose initially no Customer exists with **crm-2048**. Two transactions **T1** and **T2** both attempt to MERGE on the same key.

| Illustrative Step | Transaction T1 | Transaction T2 |
|---|---|---|
| 1 | Search Customer by externalId | Search Customer by externalId |
| 2 | No matching record found | No matching record found |
| 3 | Prepare to create Customer | Prepare to create Customer |
| 4 | Contend on writing data | Contend on writing data |

When there is **no uniqueness constraint**, there is no database-level integrity rule forcing the count of nodes sharing that key to equal one. Depending on the execution plan and how transactions interleave, multiple nodes with the same key can appear. Running a single operation inside a transaction does not automatically enforce business-key uniqueness across all concurrent transactions.

When a **uniqueness constraint exists**, Neo4j must maintain the invariant: **no two nodes with label Customer may share the same non-null externalId value**. Write coordination may cause one transaction to wait and then find the created node; in certain conflict scenarios, a transaction may fail with an error and require handling/retry. What is guaranteed here is that **two nodes violating the constraint cannot both commit**, not that every competing request is guaranteed to succeed on the first attempt.

## 3. Declaring a Uniqueness Constraint Before Deploying MERGE

### 3.1. Creating the Constraint for the Business Key

For example, a customer is uniquely identified by **externalId**:

~~~cypher
CREATE CONSTRAINT customer_external_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.externalId IS UNIQUE;
~~~

The constraint specifies that no two nodes carrying label **Customer** may share the same **externalId** property value when that property exists.

To inspect existing constraints:

~~~cypher
SHOW CONSTRAINTS;
~~~

Create constraints through a controlled migration or schema administration step before allowing multiple workers to write concurrently. **IF NOT EXISTS** supports re-running schema creation scripts when appropriate, but does not replace checking that the actual constraint has the exact type, label, and property the application needs.

### 3.2. What If Data Already Has Duplicates?

If the database already contains multiple Customer nodes with the same externalId, adding the uniqueness constraint will fail. Check first:

~~~cypher
MATCH (c:Customer)
WHERE c.externalId IS NOT NULL
WITH c.externalId AS externalId, count(c) AS soLuong
WHERE soLuong > 1
RETURN externalId, soLuong
ORDER BY soLuong DESC, externalId
LIMIT 20;
~~~

Finding duplicate records is the **detection** step. How records are merged must follow business rules: a node may hold relationships, transaction history, or metadata that must not be lost. Never automatically run DETACH DELETE on duplicate nodes without evaluating the impact on relationships.

### 3.3. Uniqueness Does Not Mean the Property Is Mandatory

With a standard uniqueness constraint, nodes **missing the externalId property** are not considered key duplicates merely because they all lack the property. This separates two distinct rules:

- **Uniqueness:** when externalId is present, it cannot duplicate another Customer node's value.
- **Mandatory presence:** every Customer must have an externalId.

If the problem requires both simultaneously, consider a **node key constraint** or combining a property existence constraint depending on Neo4j version and edition; those constraint types have their own support requirements and syntax. In addition, the application should still validate inputs before calling MERGE.

A **null** key parameter is not a "valid empty key" for a MERGE pattern: MERGE with a null property in the pattern will raise an error. Data missing an identifier must be rejected or routed for separate handling before constructing the write query.

## 4. Writing MERGE Properly Around the Identifying Key

### 4.1. MERGE on the Key, Update Remaining Properties

~~~cypher
MERGE (c:Customer {externalId: $externalId})
ON CREATE SET
    c.name = $name,
    c.createdAt = datetime(),
    c.source = 'crm'
ON MATCH SET
    c.name = $name,
    c.lastSyncedAt = datetime()
RETURN c.externalId AS externalId,
       c.name AS name,
       c.createdAt AS createdAt;
~~~

With the constraint from the previous section, the **Customer + externalId** pattern expresses the exact identity while being protected against duplicate keys under write contention.

- **ON CREATE** runs only when MERGE creates a new node.
- **ON MATCH** runs only when MERGE matches an existing node.
- **createdAt** is set on creation, avoiding overwriting the creation timestamp on every sync.
- **name** is mutable information, updated when matching an existing customer.

Mutable fields are written with SET; they do not participate in MERGE's matching pattern.

### 4.2. Anti-Pattern: Putting Mutable Data Into MERGE

~~~cypher
MERGE (c:Customer {
    externalId: $externalId,
    name: $name
})
RETURN c;
~~~

Suppose Customer **externalId = 'crm-2048', name = 'Lan'** already exists, and a new request brings **name = 'Lan Nguyễn'**. The MERGE pattern across **both properties** fails to match the old node, so it attempts to create another node.

- **Without a constraint:** easily creates two nodes with the same externalId and different names.
- **With a uniqueness constraint on externalId:** the creation violates the constraint and fails; MERGE does not automatically infer that **name** is merely an attribute to update.

Properly written:

~~~cypher
MERGE (c:Customer {externalId: $externalId})
SET c.name = $name
RETURN c;
~~~

The difference is that **the identifying key stays constant**, while descriptive data is updated.

### 4.3. Normalizing Keys Before MERGE

Two strings **'User@Example.com'** and **'user@example.com'** differ under exact string comparison. A constraint on a normal property protects **the stored value**, without automatically inferring that those two spellings denote the same identity.

If business rules treat emails as case-insensitive, store a dedicated normalized key:

~~~cypher
MERGE (u:AppUser {emailNormalized: toLower(trim($email))})
ON CREATE SET u.emailOriginal = $email,
              u.createdAt = datetime()
RETURN u.emailNormalized AS emailKey;
~~~

Create the matching uniqueness constraint on **AppUser.emailNormalized**, and apply the same normalization rule across all writing services. A normalization rule suited for emails does not automatically suit phone numbers, order codes, or case-sensitive identifiers.

## 5. Multi-Tenant Model: Composite Keys

In a multi-tenant organization system, **externalId = '001'** can validly appear in two different tenants. Then the proper identity is the **(tenantId, externalId)** pair rather than externalId alone.

~~~cypher
CREATE CONSTRAINT customer_tenant_external_unique IF NOT EXISTS
FOR (c:TenantCustomer)
REQUIRE (c.tenantId, c.externalId) IS UNIQUE;
~~~

MERGE uses the exact key pair:

~~~cypher
MERGE (c:TenantCustomer {
    tenantId: $tenantId,
    externalId: $externalId
})
ON CREATE SET c.createdAt = datetime()
SET c.name = $name
RETURN c.tenantId AS tenantId,
       c.externalId AS externalId;
~~~

**tenantId** must always be present and trustworthy in the request. If you MERGE on externalId alone, the application may conflate customers from two tenants into one entity.

**Note on composite uniqueness:** if one component of the key is absent, a composite uniqueness constraint does not automatically ensure the node has all components. Validate inputs and consider adding property existence constraints according to your version/edition capabilities.

Do not simultaneously create a **globally unique externalId** constraint on the same label if business rules allow externalId to repeat across tenants: the two rules will conflict.

## 6. Coordinating Node MERGE with Relationship MERGE

In a property graph, preventing duplicate nodes does not automatically handle all duplicate relationship risks. For example, recording that a user belongs to a team:

~~~cypher
CREATE CONSTRAINT app_user_id_unique IF NOT EXISTS
FOR (u:AppUser)
REQUIRE u.userId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT team_id_unique IF NOT EXISTS
FOR (t:Team)
REQUIRE t.teamId IS UNIQUE;
~~~

Once the schema is ready, within a single transaction:

~~~cypher
MERGE (u:AppUser {userId: $userId})
MERGE (t:Team {teamId: $teamId})
MERGE (u)-[m:MEMBER_OF]->(t)
ON CREATE SET m.joinedAt = datetime()
RETURN u.userId AS userId,
       t.teamId AS teamId,
       m.joinedAt AS joinedAt;
~~~

This ordering is intentional:

1. MERGE each **node on its constrained key**.
2. Once variables **u** and **t** point to two concrete nodes, MERGE the relationship between them.
3. Set **joinedAt** on creation so the join timestamp is not overwritten by repeated events.

Avoid a single MERGE for **the entire path** when the identities of both endpoints must be controlled individually:

~~~cypher
// NOT the idiomatic way to upsert two nodes that already have distinct identities.
MERGE (u:AppUser {userId: $userId})
      -[:MEMBER_OF]->
      (t:Team {teamId: $teamId});
~~~

MERGE matches or creates **the entire pattern**. When the connecting edge does not yet exist, it may attempt to create unintended components; constraints can cause the statement to fail instead of attaching cleanly to existing nodes. Merging the nodes separately first expresses intent clearly.

**Relationship concurrency caveat:** uniqueness constraints on **AppUser.userId** and **Team.teamId** only protect the nodes; they do not imply a uniqueness rule per endpoint pair and relationship type. If business rules require **never having two MEMBER_OF relationships for the same pair**, design an appropriate safeguard: such as a distinct membership identity, relationship property constraints where supported by your Neo4j version, and/or transaction coordination. Never conclude that parallel relationship MERGE patterns guarantee uniqueness without a corresponding constraint.

## 7. Concurrent Writes: Valid Data Can Still Produce Transient Errors

### 7.1. Distinguishing Data Invariants from Per-Request Outcomes

Suppose a uniqueness constraint exists on **Customer.externalId**, and two threads both run:

~~~cypher
MERGE (c:Customer {externalId: 'crm-2048'})
ON CREATE SET c.name = 'Lan'
RETURN c.externalId;
~~~

Multiple valid execution outcomes exist depending on contention and locking:

- The first thread creates the node; the second finds the same node.
- One thread waits on a resource, or a transaction is asked to retry.
- One transaction returns a conflict/constraint error; the application handles the error and re-checks by key.

In every scenario **while the constraint is active**, two Customer nodes with **externalId = 'crm-2048'** cannot both commit. That is the data guarantee to prioritize.

Never promise that two concurrent requests will always succeed on the first try. In particular, if a MERGE statement references multiple properties governed by different uniqueness constraints, partial matches can produce constraint errors that must be handled as data conflicts.

### 7.2. Avoiding Ambiguity Across Multiple Constraints

Suppose two separate constraints exist:

~~~cypher
CREATE CONSTRAINT employee_id_unique IF NOT EXISTS
FOR (e:Employee)
REQUIRE e.employeeId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT employee_email_unique IF NOT EXISTS
FOR (e:Employee)
REQUIRE e.emailNormalized IS UNIQUE;
~~~

The following statement can be troublesome:

~~~cypher
MERGE (e:Employee {
    employeeId: $employeeId,
    emailNormalized: $emailNormalized
});
~~~

For example, a node already exists with **employeeId = 'E-7'**, and the employee just changed email. MERGE fails to match **the entire pattern**, then attempts to create a node carrying an already-existing ID, causing a constraint violation. Or the new email already belongs to another employee.

Choose one identifier as the primary key for MERGE, then update email per business policy:

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
ON CREATE SET e.createdAt = datetime()
SET e.emailNormalized = toLower(trim($email))
RETURN e.employeeId;
~~~

If the new email is already used by another node, the **email uniqueness constraint** signals a violation. That is a business conflict needing resolution; **do not** retry the same conflicting data infinitely.

### 7.3. Every Request Needs State Reconciliation After an Error

An error-handling strategy can be organized by outcome:

| Outcome Category | Recommended Action |
|---|---|
| Commit succeeded | Return the business key and needed data to the caller |
| Temporary lock/transaction error recognized by the driver as transient | Retry the whole transaction with bounded attempts/time and appropriate backoff |
| Uniqueness error because another process wrote the same identity | Re-read by **the exact business key**, inspect the current node, and treat as success or handle conflict |
| Uniqueness error on **another** key, e.g., email belongs to someone else | Return a business error or route into conflict resolution |
| Null/invalid key value | Reject input without running MERGE |

**Retries must be safe to re-execute**: a previous attempt or another worker may already have created the node. Therefore, MERGE on a durable key and intentional updates matter more than blind CREATEs.

If a transaction both creates a node and calls an external service, do not perform non-database side effects inside the callback that the driver may re-run; doing so can trigger duplicate emails, charges, or API calls. Separate external side effects and use idempotency/outbox patterns when needed.

## 8. Example from the Java Driver

The Java Driver runs Cypher inside managed transactions. The snippet below demonstrates using **MERGE** consistently with the pre-created **customer_external_id_unique** constraint:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public final class CustomerWriter {
    private final Driver driver;

    public CustomerWriter(Driver driver) {
        this.driver = driver;
    }

    public String upsertCustomer(String externalId, String name) {
        if (externalId == null || externalId.isBlank()) {
            throw new IllegalArgumentException("externalId is required");
        }

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {

            return session.executeWrite(tx -> {
                var result = tx.run(
                    """
                    MERGE (c:Customer {externalId: $externalId})
                    ON CREATE SET c.createdAt = datetime()
                    SET c.name = $name
                    RETURN c.externalId AS externalId
                    """,
                    Values.parameters(
                        "externalId", externalId,
                        "name", name
                    )
                );
                return result.single().get("externalId").asString();
            });
        }
    }
}
~~~

Key points to note:

- **Driver** is typically managed and reused at the application level; **Session** should be short-lived and not shared arbitrarily across threads.
- **executeWrite** uses a driver-managed transaction and automatically retries errors classified by the driver as transient/retryable per configuration. Not all constraint errors are automatically retried.
- **Values.parameters** passes values as parameters, avoiding Cypher string concatenation from input.
- **RETURN c.externalId** returns the business key, keeping callers decoupled from internal graph IDs.
- **SET c.name = $name** lets later write requests update the name; if update races occur, the application must define source-of-truth precedence, versioning, or timestamp rules.

In Spring Data Neo4j applications, repository or transaction operations must likewise respect database data constraints. Method names like **save** or Java entity structure do not replace uniqueness constraints under concurrent writes.

## 9. Repeated Ingestion and Batch Processing

CSV feeds, message broker events, or CRM syncs typically exhibit **at-least-once delivery**. The same record can arrive multiple times, even concurrently across workers.

A Cypher pattern using UNWIND to update multiple customers:

~~~cypher
UNWIND $rows AS row
MERGE (c:Customer {externalId: row.externalId})
ON CREATE SET c.createdAt = datetime()
SET c.name = row.name,
    c.lastSyncedAt = datetime()
RETURN count(c) AS soDongDaXuLy;
~~~

Meaning of the output: **soDongDaXuLy** counts the number of input rows processed by the query, **not** the number of newly created Customer nodes. If the list has 100 rows containing 20 duplicate keys, this count does not represent distinct nodes.

For batch ingestion:

1. Check that **externalId** is non-null/non-blank and normalize key format before ingesting.
2. When multiple rows share a key with different values, define a deterministic rule (by version or event timestamp) to pick the latest state; never rely on arbitrary processing order.
3. Write in reasonable batch sizes to bound transaction duration and reduce contention on hot keys.
4. Never drop uniqueness constraints merely to speed up ingestion: that trades data invariants for temporary throughput.
5. Under heavy load, tune batch size and parallelism based on key overlap, contention, write throughput, and resource limits.

If business rules require **updating only when the event is newer**, an unconditional SET as in the example is not enough. Store a version/timestamp and implement a conditional update inside the transaction, handling out-of-order event conflicts.

## 10. Verifying Constraints and Actual Outcomes

### 10.1. Inspecting Schema

~~~cypher
SHOW CONSTRAINTS;
~~~

Confirm the constraint targets the exact **Customer label**, **externalId property**, and **UNIQUE** type. Development, staging, and production environments must share the same schema migrations required by the application.

### 10.2. Inspecting the Query Plan

~~~cypher
EXPLAIN
MERGE (c:Customer {externalId: $externalId})
RETURN c.externalId;
~~~

EXPLAIN displays the plan without executing the write. When the key has an appropriate index/constraint, the plan can leverage the unique lookup structure; exact operator names and plan shapes vary across Neo4j versions.

Do not use **PROFILE** as a harmless preview for write queries on real data, because PROFILE **executes** the query.

### 10.3. Verifying Node Count for the Same Key

After two or more workers concurrently upsert the same code:

~~~cypher
MATCH (c:Customer {externalId: 'crm-2048'})
RETURN count(c) AS soNodeCungKhoa,
       collect(c.name) AS tenHienCo;
~~~

With a valid key, proper constraint, and at least one successful write, the expected result is **soNodeCungKhoa = 1**. A count of 0 means all writes failed or have not committed. If greater than 1, re-check the schema/label/property and data state.

On a dedicated test database, open two Neo4j sessions or run parallel Java tasks issuing MERGE on the same **externalId**, then inspect node counts and log errors or retries. **One successful sequential run does not prove correctness under concurrency**; concurrency testing exposes workflow flaws while the constraint enforces uniqueness at the database layer.

### 10.4. Auditing Duplicates Across the Entire Label

~~~cypher
MATCH (c:Customer)
WHERE c.externalId IS NOT NULL
WITH c.externalId AS externalId, count(*) AS n
WHERE n > 1
RETURN externalId, n
ORDER BY n DESC
LIMIT 20;
~~~

If the query detects duplicate groups, check which database and constraints are actually deployed. Also audit Customer nodes **missing externalId**, since a plain uniqueness constraint does not block missing keys.

## 11. Common Design Mistakes

| Mistake | Consequence | Prevention |
|---|---|---|
| Using CREATE for redeliverable events | Each delivery can create a new node | MERGE on the business key and create a constraint |
| Using MERGE alone without a uniqueness constraint | Concurrent writes can create duplicate nodes | Database uniqueness constraint on the right key |
| Merging on name, status, or mutable properties | Descriptive changes break pattern matching, causing duplicates or errors | MERGE on stable key, SET mutable data |
| Inconsistent key normalization | Different spellings become distinct values | Normalize before writing and constrain the normalized key |
| Composite key missing tenantId | Conflates entities across tenants | Constrain and MERGE on the full tenantId + externalId pair |
| Assuming UNIQUE means NOT NULL | Nodes missing the key can still exist | Validate input and consider existence/node key constraints |
| Assuming node constraints prevent duplicate relationships | Multiple relationships with the same meaning can still exist | Design separate relationship identity and safeguards |
| Infinite retries on every error | Business conflicts persist forever while load spikes | Classify errors, bound retries, and inspect state after conflicts |
| Updating name with SET across two requests assuming fixed order | Later writes can overwrite intended values | Apply version/updatedAt rules or conditional updates |
| Creating constraints after dirty duplicates already exist | Migration fails | Detect and merge duplicates before creating constraints |

## 12. Practice Scenarios

**Scenario A — Syncing the same customer code.** Two workers concurrently receive messages for **externalId = 'crm-2048'**, both running MERGE on externalId. The database has the matching uniqueness constraint. Can two committed nodes share the same key?

**Answer:** No. One or both requests may wait, retry, or handle an error, but the constraint prevents a committed state with two Customer nodes sharing the same non-null key.

**Scenario B — Renaming a customer.** A Customer already has name "Mai", and a new sync carries "Mai Phạm". Should **name** be placed in the MERGE map?

**Answer:** No, if name is mutable data. MERGE on the stable key (such as externalId) and then SET name.

**Scenario C — Two tenants with the same external code.** Tenant A and Tenant B both have a customer coded **007**. Which property constraint fits?

**Answer:** Composite uniqueness on **(tenantId, externalId)** for the target label; MERGE must supply both fields.

**Scenario D — Uniqueness error when updating email.** Employee E-7 changes email to an address already belonging to E-9. Should the same query be retried infinitely?

**Answer:** No. This is a business conflict on email, unlike a recoverable transient error. The application must return an error or execute the email-transfer business rule.

**Scenario E — Membership relationships.** User and Team nodes both have uniqueness constraints on their IDs. Is that enough to prove two MEMBER_OF relationships cannot appear between the same pair of nodes under all concurrent write schedules?

**Answer:** Not yet. Node ID uniqueness does not automatically define relationship uniqueness. Design dedicated safeguards if business rules require that invariant.

## 13. Key Takeaways

**MERGE** expresses pattern-based find-or-create operations; a **uniqueness constraint** enforces the rule against duplicate keys. Under concurrent writes, combine both with **a stable business key**, **transactions with sensible error/retry handling**, and **schema verification** to protect Neo4j data. Constraints guarantee valid committed data states; request outcomes and update ordering still depend on application design, monitoring, and handling.

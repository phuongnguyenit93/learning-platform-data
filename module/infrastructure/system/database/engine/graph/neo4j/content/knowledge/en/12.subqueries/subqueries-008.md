# Batch Execution with `CALL { ... } IN TRANSACTIONS` and Usage Requirements

## 1. Why Split a Cypher Query into Multiple Transactions?

Neo4j stores data as a **property graph**: nodes represent entities, relationships represent links, and both can carry properties. When importing millions of users, companies, or relationships between them, a single write query can hold many changes, locks, and transaction state for a long time. If the entire operation runs inside **a single transaction**, a failure near the end can force the system to roll back all changes from that transaction.

`CALL { ... } IN TRANSACTIONS` is the Cypher mechanism for **splitting a subquery's input rows into smaller batches and executing each batch in a separate transaction**. This mechanism is useful when:

- Importing data from `LOAD CSV` into nodes and relationships.
- Updating or normalizing a large graph dataset.
- Processing groups of records independently where partially committed results are acceptable.

For example, with 2,500 input rows and a batch size of 1,000:

```text
2,500 input rows
  ├── Rows    1–1,000 → Transaction 1 → COMMIT
  ├── Rows 1,001–2,000 → Transaction 2 → COMMIT
  └── Rows 2,001–2,500 → Transaction 3 → COMMIT
```

**Core point:** `OF 1000 ROWS` counts **input rows passed into the subquery**, not the number of nodes, relationships, or `MERGE` statements executed. One row can modify multiple graph entities.

## 2. Syntax and Execution

### 2.1. Recommended Syntax on Cypher 5.23 and Later

```cypher
UNWIND range(1, 2500) AS itemId
CALL (itemId) {
  MERGE (:ImportedItem {id: itemId})
} IN TRANSACTIONS OF 1000 ROWS;
```

Execution sequence:

1. `UNWIND` generates 2,500 rows; each row has variable `itemId`.
2. `CALL (itemId)` explicitly declares the outer-query variable passed into the subquery.
3. The body `{ MERGE ... }` runs for each row in the batch.
4. Neo4j commits changes in batches of 1,000 rows; the final batch has 500 rows.

From Cypher 5.23, the **variable scope clause** `CALL (itemId)` is the preferred way to import variables. Use `CALL ()` when no variables from the outer query are needed; `CALL (*)` imports all variables currently in scope, so use it only when truly needed.

### 2.2. Legacy `CALL { ... }` Syntax on Older Versions

Before the variable scope clause, variables were passed into the subquery via a `WITH` at the start of the subquery:

```cypher
UNWIND range(1, 2500) AS itemId
CALL {
  WITH itemId
  MERGE (:ImportedItem {id: itemId})
} IN TRANSACTIONS OF 1000 ROWS;
```

Both forms illustrate the same batching principle. **Importing `WITH` is legacy syntax and has been deprecated since Cypher 5.23**; when writing new queries for supported versions, prefer `CALL (itemId) { ... }`.

If `OF n ROWS` is omitted, the default batch size is **1,000 rows**. You can write `IN TRANSACTIONS OF 500 ROWS` or `IN TRANSACTIONS OF 2000 ROWS` explicitly so readers and operators see the intended batch size.

### 2.3. Differences from Regular Subqueries

| Syntax | Transaction boundary | Suitable for |
| --- | --- | --- |
| `CALL { ... }` or `CALL (x) { ... }` without `IN TRANSACTIONS` | Executes within the enclosing query's transaction | Subqueries used for computation, filtering, aggregation, or writes requiring shared atomicity |
| `CALL { ... } IN TRANSACTIONS` or `CALL (x) { ... } IN TRANSACTIONS` | Each input batch runs in its own transaction | Large data imports/updates where partial commits are acceptable |
| `UNWIND` combined with `MERGE` without `IN TRANSACTIONS` | Does not create transaction boundaries between rows | Small/medium tasks requiring a single transaction |

Simply using `UNWIND` or `WITH ... LIMIT` **does not mean** Neo4j automatically commits in batches.

## 3. Practical Example: Importing Users and Company Memberships

Suppose the file `users-companies.csv` contains:

```csv
userId,userName,companyId,companyName
u001,An,c001,Acme
u002,Binh,c001,Acme
u003,Chi,c002,Northwind
```

Goal: create `User` nodes, `Company` nodes, and `MEMBER_OF` relationships between them. Before importing, create constraints to enforce unique identifier keys and accelerate key lookups:

```cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;

CREATE CONSTRAINT company_id_unique IF NOT EXISTS
FOR (c:Company) REQUIRE c.id IS UNIQUE;
```

Constraint creation statements are executed separately prior to the data import statement. On Cypher 5.23 and later:

```cypher
LOAD CSV WITH HEADERS FROM 'file:///users-companies.csv' AS row
WITH row
WHERE row.userId IS NOT NULL
  AND trim(row.userId) <> ''
  AND row.companyId IS NOT NULL
  AND trim(row.companyId) <> ''
CALL (row) {
  MERGE (u:User {id: row.userId})
  SET u.name = row.userName

  MERGE (c:Company {id: row.companyId})
  SET c.name = row.companyName

  MERGE (u)-[:MEMBER_OF]->(c)
} IN TRANSACTIONS OF 1000 ROWS;
```

Explanation:

- `LOAD CSV WITH HEADERS` binds each CSV row to variable `row`; `WHERE` drops rows missing primary keys before batching.
- `MERGE` looks up nodes by `id` key; if absent, it creates them. Uniqueness constraints prevent creating multiple nodes with the same `id`, even across re-imports.
- `SET` updates names when source data changes. `MERGE (u)-[:MEMBER_OF]->(c)` avoids creating duplicate relationships of the same type between the same two endpoints in this model.
- `IN TRANSACTIONS OF 1000 ROWS` places up to 1,000 valid rows into each transaction. This is the batch size of **filtered CSV rows**, not 1,000 nodes.

The `file:///` path typically points to the import directory that the Neo4j server is allowed to read, **not a path on the machine running the Java application**. For managed services that disallow local file reads, use an accessible, configured data URL.

After importing, you can verify:

```cypher
MATCH (u:User)-[:MEMBER_OF]->(c:Company)
RETURN c.id AS companyId, c.name AS companyName, count(u) AS members
ORDER BY members DESC;
```

With the sample CSV, `Acme` has 2 users and `Northwind` has 1 user.

## 4. Example: Updating a Large Set of Nodes

You do not have to use `LOAD CSV`. The outer query can select existing nodes and pass identifier keys into the subquery:

```cypher
MATCH (u:User)
WHERE u.needsReview = true
WITH u.id AS userId
CALL (userId) {
  MATCH (u:User {id: userId})
  SET u.reviewStatus = 'PENDING',
      u.needsReview = false
} IN TRANSACTIONS OF 500 ROWS;
```

Here, the outer query selects users needing updates; the subquery looks up each node by key and writes in groups of 500 rows. An appropriate index/constraint on `User.id` is needed to avoid scanning the whole graph on every node lookup.

Do not build a massive list using `collect(...)` before `CALL` just to split into batches: `collect` increases memory usage and forfeits streaming over input rows.

## 5. Error Handling, Rollback, and Re-running

### 5.1. What Does a Failed Batch Affect?

Each batch is a transaction. If batch 3 encounters an error, changes belonging to **batch 3 are rolled back**; previously committed batches **are not automatically rolled back**. This is the decisive difference compared to writing all data in a single transaction.

By default, an error halts the query and reports the failure. On Neo4j versions supporting these options, behavior can be adjusted with `ON ERROR`:

| Mode | When a batch fails | Impact to note |
| --- | --- | --- |
| `ON ERROR FAIL` (default) | Halts and raises an error | Previously committed batches remain persisted |
| `ON ERROR CONTINUE` | Rolls back the failed batch and attempts remaining batches | Can also skip valid rows that happened to share the failed batch |
| `ON ERROR BREAK` | Rolls back the failed batch and skips remaining batches | Allows stopping further writes at the failed batch |

Example illustrating per-batch status reporting:

```cypher
UNWIND [
  {id: 'u101'},
  {id: null},
  {id: 'u103'},
  {id: 'u104'}
] AS row
CALL (row) {
  MERGE (:ImportDemo {id: row.id})
} IN TRANSACTIONS OF 2 ROWS
  ON ERROR CONTINUE
  REPORT STATUS AS batchStatus
RETURN row.id AS inputId, batchStatus;
```

In this example, `MERGE` cannot use `id: null`. Because the first two rows belong to the same batch, **the entire first batch rolls back**, including the change for `u101`. `CONTINUE` mode allows the next batch (`u103`, `u104`) to proceed. `REPORT STATUS AS batchStatus` returns status metadata so applications can inspect succeeded/failed batches; exact syntax and status fields may vary by version.

**Do not use `ON ERROR CONTINUE` to hide data errors.** Log outcomes, reconcile valid row counts, processed rows, and skipped rows. If an error affects only one row, retrying with a smaller batch or fixing the CSV prevents losing the whole batch.

### 5.2. Designing for Safe Re-runs

Because data may be partially committed, subsequent runs must consider **idempotency** (re-running without creating duplicate data):

- Use `MERGE` on a stable business key; create corresponding uniqueness constraints.
- Clearly define which relationships count as duplicates; unconditional `CREATE` for relationships can duplicate links on retry.
- Distinguish source data errors (missing keys, wrong types) from operational errors (timeouts, lock contention, dropped connections).
- Verify results after each run with count queries and source reconciliation, rather than relying solely on the query completing.

If the business requirement is **all succeed or all roll back**, use a standard single transaction with an appropriate volume, or design a separate staging/approval workflow. Do not choose `IN TRANSACTIONS` when global atomicity is required.

## 6. Execution Requirements and Java Integration

### 6.1. Must Run in an Implicit Transaction

Queries using `CALL { ... } IN TRANSACTIONS` must be submitted as an **implicit transaction (auto-commit)**. Do not place them inside a previously opened explicit/managed transaction.

| Environment | How to use |
| --- | --- |
| Neo4j Browser | Prepend `:auto` when Browser requires auto-commit mode |
| Neo4j Java Driver | Use `Session.run(query)` and consume results to ensure the query completes |
| Java Driver `session.executeWrite(...)` / `Transaction.run(...)` | Unsuitable because it wraps the query inside a managed/explicit transaction |
| Spring Data Neo4j with `@Transactional` | Do not invoke batched queries inside a Spring-managed transaction; choose an appropriate auto-commit execution path and review application transaction boundaries |

Java Driver example (assuming an initialized `driver` instance and CSV access from the Neo4j server):

```java
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String cypher = """
    LOAD CSV WITH HEADERS FROM 'file:///users-companies.csv' AS row
    WITH row
    WHERE row.userId IS NOT NULL AND trim(row.userId) <> ''
    CALL (row) {
      MERGE (u:User {id: row.userId})
      SET u.name = row.userName
    } IN TRANSACTIONS OF 1000 ROWS
    """;

try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    session.run(cypher).consume();
}
```

`Session.run(...)` sends the query as an implicit transaction. Calling `consume()` ensures the driver receives all results and the execution summary, surfacing any errors before leaving the `try` block. Do not wrap this code in `executeWrite` just because the query contains `MERGE`: the batched operation manages its inner transactions itself.

### 6.2. Choosing Batch Size

There is no single optimal batch size for every graph:

| Batch size | Benefits | Risks |
| --- | --- | --- |
| Small (e.g., 100–500 rows) | Less data to roll back, lower per-transaction resource footprint | Overhead of opening/committing many transactions |
| Medium (e.g., 1,000 rows) | Reasonable starting point for many data import tasks | Still depends on actual operations performed per row |
| Large (e.g., 5,000–10,000 rows) | Fewer commits | Can increase memory, lock hold duration, rollback cost, and contention |

Start with a moderate batch size and measure processing time, memory load, lock wait time, and stability. When each row creates many nodes/relationships or writes to hot nodes shared by many rows, the batch size may need to be smaller. Do not enlarge batch size merely to reduce transaction count.

### 6.3. Pre-Run Checklist

1. **Independence:** batches can commit independently and completion order aligns with business logic.
2. **Retryability:** identifier keys and `MERGE` rules are in place to avoid duplicate data.
3. **Input data:** filter/null-check mandatory keys, cast data types if needed, and verify the server can access the source.
4. **Indexes/constraints:** lookups or `MERGE` operations by key have matching indexes/uniqueness constraints.
5. **Transaction context:** the client genuinely runs an implicit transaction; no outer `@Transactional` or `executeWrite` wrapper.
6. **Observability:** counts of succeeded/failed rows, logging, and post-load reconciliation are in place.

## 7. Common Mistakes

**Confusing batching with global atomicity.** Transactions committed in earlier batches are not undone when a later batch fails. All-or-nothing workflows do not fit this execution model.

**Running the query inside a managed transaction.** `CALL ... IN TRANSACTIONS` creates transactions for each batch; having Java Driver or Spring open an outer explicit transaction causes an error. Run in auto-commit mode.

**Failing to declare imported variables for the subquery.** With modern syntax, specify `CALL (row) { ... }` to use `row` in the body. With legacy syntax, use `WITH row` at the top of `CALL { ... }`.

**Missing constraints and retrying with `CREATE`.** When the final batch fails, previously committed data remains. Retrying with `CREATE` risks duplicating nodes/relationships; design keys and `MERGE` from the outset.

**Assuming 1,000 rows means 1,000 write operations.** One row can create/update multiple nodes and relationships; transaction size depends on the actual work inside the subquery.

**Confusing `LIMIT` with commits.** Limiting or grouping rows at the query level does not create new transactions; only `IN TRANSACTIONS` creates commit boundaries as shown here.

## 8. Key Takeaways

`CALL { ... } IN TRANSACTIONS` enables Neo4j to process large volumes of connected data across **multiple small transactions**, reducing the change footprint of each commit. In exchange, the system can leave **partial results** when errors occur, requiring proper error handling, reconciliation, and safe retries. On Cypher 5.23+, prefer `CALL (var) { ... } IN TRANSACTIONS OF n ROWS`; when integrating via Java Driver or Spring Data Neo4j, a critical requirement is **submitting the query in an implicit transaction**.

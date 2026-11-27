# Using index, Using where, and Using index condition

## Objectives

After this lesson, you will be able to:

- Read three common indicators in the `Extra` column of `EXPLAIN`: `Using index`, `Using where`, and `Using index condition`.
- Distinguish a covering index from using an index to look up only a subset of data.
- Understand which conditions are evaluated in the server layer versus pushed down to the storage engine.
- Explain Index Condition Pushdown (ICP) and its benefit in reducing row lookups from the clustered index.
- Recognize why `Using where` does not mean a query is slow or failing to use an index.
- Analyze cases where these indicators appear individually or in combination.
- Inspect access paths using `EXPLAIN`, `EXPLAIN FORMAT=JSON`, `EXPLAIN ANALYZE`, and `optimizer_switch`.
- Design indexes tailored to filter conditions and queried columns.

These examples target MySQL 8.0/8.4 with InnoDB. The contents of `Extra` depend on the execution plan, data, indexes, and version; illustrative outputs are not guaranteed across every environment.

## 1. What does the Extra column in EXPLAIN tell you?

`EXPLAIN` shows how MySQL intends to execute a query. In the traditional tabular format, the `Extra` column provides additional details on how data is accessed and processed.

Example:

```sql
EXPLAIN
SELECT employee_id, dept_id, last_name
FROM employees
WHERE dept_id = 10;
```

Common `Extra` values include:

| Extra | Primary meaning |
|---|---|
| `Using index` | The query can retrieve all needed columns directly from the index; this is covering/index-only access |
| `Using where` | MySQL applies a `WHERE` condition to filter rows returned by the access path; does not mean the query lacks an index |
| `Using index condition` | Predicates evaluable from the index are pushed down to the storage engine via Index Condition Pushdown before fetching full rows |

These three indicators describe different aspects of execution. They are not three quality grades and are not mutually exclusive across plans.

### 1.1. Extra is not a performance score

You cannot conclude a query is good solely from `Using index`, or bad solely from `Using where`. Also inspect:

- `type`: access method such as `const`, `eq_ref`, `ref`, `range`, `index`, `ALL`.
- `possible_keys` and `key`: candidate indexes and the index actually selected.
- `key_len`: byte length of the index portion used for access.
- `rows`: estimated rows to examine.
- `filtered`: estimated percentage of rows remaining after filter conditions.
- `Extra`: how MySQL handles predicates, indexes, and extra operations.
- Actual rows, loops, and timing from `EXPLAIN ANALYZE` when actual measurement is needed.

A query using an index that still scans millions of entries can be slow. A query showing `Using where` over a few hundred rows can be very fast.

## 2. Preparing the example table

Use an employees table with a composite index on department and last name:

```sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    dept_id INT NOT NULL,
    last_name VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    salary DECIMAL(12,2) NOT NULL,
    hire_date DATE NOT NULL,
    PRIMARY KEY (employee_id),
    KEY idx_dept_lastname (dept_id, last_name)
) ENGINE = InnoDB;
```

In InnoDB, secondary indexes store the indexed columns along with the corresponding row's primary key. Thus `idx_dept_lastname` can provide `dept_id`, `last_name`, and `employee_id` without reading rows from the clustered index.

Load a sufficiently large dataset with varied distributions across departments, last names, and statuses so the optimizer has a meaningful basis for selecting access paths. If the table holds only a few rows, the optimizer may pick a table scan despite having an index; that does not invalidate the example, it simply reflects real cost on tiny tables.

Check the index structure:

```sql
SHOW INDEX FROM employees;
```

## 3. Using index: covering index

`Using index` in `Extra` indicates MySQL can satisfy the columns required by the query directly from the index without reading full rows from the clustered index/table row. This access pattern is commonly called a covering index or index-only access.

### 3.1. Example of a query covered by an index

```sql
EXPLAIN
SELECT employee_id, dept_id, last_name
FROM employees
WHERE dept_id = 10;
```

Index `idx_dept_lastname (dept_id, last_name)` contains:

- `dept_id` and `last_name` because they are declared in the index.
- `employee_id` because InnoDB stores the primary key in every secondary index entry.

Consequently, the query can retrieve all SELECTed columns directly from the secondary index. In `Extra`, MySQL typically displays `Using index` if the optimizer chooses this access path.

### 3.2. A covering index does not mean zero index reads

MySQL still must read index pages and traverse matching entries. `Using index` only means no extra clustered record lookups are needed to fetch missing columns.

If the filter matches huge numbers of entries, the query can still incur significant I/O and CPU. If the optimizer chooses `type = index`, it may be scanning the entire index; that is still a full index scan, not a selective lookup.

### 3.3. Covering depends on queried columns

Add the `salary` column to the SELECT:

```sql
EXPLAIN
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10;
```

`salary` is neither in `idx_dept_lastname` nor part of the primary key. InnoDB must read the clustered record to fetch salary. Hence the existing index no longer covers the query, and `Using index` can disappear.

You could create a wider covering index:

```sql
CREATE INDEX idx_dept_lastname_salary
ON employees (dept_id, last_name, salary);
```

However, do not add columns to indexes just to force `Using index`. Wide indexes increase storage footprint, write cost, buffer pool pressure, and maintenance overhead. Only create one when the read workload is significant enough and the benefit has been measured.

### 3.4. Using index can appear alongside Using where

Example:

```sql
EXPLAIN
SELECT employee_id, dept_id, last_name
FROM employees
WHERE dept_id = 10
  AND last_name LIKE 'Ng%';
```

All columns needed for reading are in the index. MySQL can use the index to find the range and retrieve results without reading clustered records (`Using index`). At the same time, `WHERE` conditions are still evaluated on accessed entries, so depending on the plan `Extra` may also display `Using where`.

`Using index` answers "must full rows be read to obtain the columns?". `Using where` answers "is a filter condition applied to rows/entries?". These two meanings do not conflict.

## 4. Using where: the server still filters results

`Using where` indicates MySQL applies a `WHERE` condition to discard non-matching rows from the access path's output. Part of the condition may be used for index positioning, while the remainder is evaluated afterward.

`Using where` alone does not tell you whether a condition is checked in the server layer or pushed down to the storage engine via ICP. Read it alongside other indicators in `Extra` and the execution plan.

### 4.1. Filtering after using an index for partial lookup

With index `(dept_id, last_name)`, run:

```sql
EXPLAIN
SELECT employee_id, dept_id, last_name, status, salary
FROM employees FORCE INDEX (idx_dept_lastname)
WHERE dept_id = 10
  AND status = 'ACTIVE';
```

The index helps locate employees in department 10. However, `status` is not in the index. MySQL must fetch the corresponding rows and then evaluate `status = 'ACTIVE'` in the server layer. `Extra` typically shows `Using where`.

`FORCE INDEX` here is solely to demonstrate a clear access path. Do not add `FORCE INDEX` in production merely to see a particular Extra value; let the optimizer choose and only intervene when measured evidence proves a benefit.

### 4.2. Filtering after a table scan

```sql
EXPLAIN
SELECT employee_id, dept_id, status, salary
FROM employees
WHERE status = 'ACTIVE';
```

If there is no suitable index on `status` and the optimizer chooses a table scan (`type = ALL`), the server still must check `status = 'ACTIVE'` across the rows read. `Extra` can display `Using where`.

This is not necessarily a problem if the table is small or most rows have status ACTIVE. If the table is large and the predicate is highly selective, evaluate an index on `status` or a composite index matching the real workload.

### 4.3. Using where does not mean no index is used

Example of a query using an index for part of the predicates and filtering the rest:

```sql
SELECT employee_id, dept_id, status
FROM employees
WHERE dept_id = 10
  AND status = 'ACTIVE';
```

The optimizer can use `idx_dept_lastname` to narrow by `dept_id`, then apply the status filter to each row read. The plan still uses an index, while retaining a residual predicate.

Whenever you see `Using where`, inspect `key`, `rows`, `filtered`, and indexed columns before drawing conclusions.

## 5. Using index condition: Index Condition Pushdown (ICP)

Index Condition Pushdown is an optimization allowing MySQL to push part of a `WHERE` condition down to the storage engine. The storage engine can evaluate predicates using columns stored in the index before reading full rows from the clustered index.

If the condition fails, InnoDB skips reading the clustered record for that entry. Only when the condition passes does the engine proceed to fetch the full row if the query needs columns absent from the secondary index.

In `EXPLAIN`, the typical indicator is:

```text
Using index condition
```

### 5.1. ICP example with a composite index

The query requests salary, while the index only holds department and last name:

```sql
EXPLAIN
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10
  AND last_name LIKE '%son';
```

Analysis:

1. `dept_id = 10` uses the leading portion of `idx_dept_lastname` to locate entries in department 10.
2. `last_name LIKE '%son'` has a leading wildcard, so it cannot form a normal B-tree range on `last_name`.
3. Nonetheless, `last_name` is stored in the index. InnoDB can evaluate this predicate directly on index entries using ICP.
4. Only entries with matching last names require reading the clustered record to fetch `salary`.

If the optimizer chooses the index and ICP, `Extra` can display `Using index condition`.

### 5.2. ICP reduces row lookups, not necessarily index entries scanned

In the example above, the engine still must traverse index entries within the `dept_id = 10` slice to check the suffix of `last_name`. ICP does not convert `LIKE '%son'` into a B-tree prefix seek.

The win is that entries failing `LIKE` are rejected before reading clustered records. If most entries fail the filter and clustered index lookups are costly, ICP can cut I/O substantially.

If nearly every entry matches, the benefit is small. If the `dept_id = 10` slice is already tiny, ICP overhead/savings may be negligible.

### 5.3. ICP differs from a covering index

These two concepts are often confused:

| Characteristic | Using index | Using index condition |
|---|---|---|
| Meaning | The index holds enough columns for the query | The storage engine checks predicates on indexed columns before fetching full rows |
| Must read clustered record? | Not needed if the access path is truly covering | Needed for entries passing the condition if SELECT needs non-indexed columns |
| Goal | Avoid reading full rows altogether | Reduce how many full rows must be read |
| Extra indicator | `Using index` | `Using index condition` |

In the ICP example, the query needs `salary`, which is missing from the index, so entries surviving ICP still require full row lookups. `Using index condition` does not mean the query is covered by the index.

### 5.4. ICP does not apply to every access path

ICP is helpful only when MySQL uses index access and has predicates evaluable on indexed columns before fetching full rows. Common conditions include:

- An eligible access method such as `range`, `ref`, `eq_ref`, or `ref_or_null`.
- Pushed-down predicates reference only columns contained in the index.
- The query must fetch additional columns from the full row to return results or process further.
- The storage engine and index type support ICP.

In InnoDB, ICP applies to secondary indexes; it provides no comparable benefit on a clustered index directly because the full row already resides there. If the query is already satisfied by a covering index, ICP is unnecessary because no full-row lookups occur.

Predicates containing subqueries or stored functions cannot be pushed down this way. The optimizer can also skip ICP if cost evaluation shows no advantage.

## 6. Comparing three scenarios on the same index

Suppose we have the index:

```sql
KEY idx_dept_lastname (dept_id, last_name)
```

The following three queries illustrate three distinct cases:

### Case A: Covering index

```sql
SELECT employee_id, dept_id, last_name
FROM employees
WHERE dept_id = 10;
```

- All needed columns reside in the secondary index (primary key is stored in the entry).
- No clustered record lookup is needed.
- `Extra` can display `Using index`.

### Case B: Residual filter in the server

```sql
SELECT employee_id, dept_id, last_name, status, salary
FROM employees FORCE INDEX (idx_dept_lastname)
WHERE dept_id = 10
  AND status = 'ACTIVE';
```

- `dept_id` is used for index lookup.
- `status` is not in the index, so it cannot be checked via ICP on this index.
- Full rows are read to fetch `status` and `salary`; the server applies the remaining filter.
- `Extra` typically shows `Using where`.

### Case C: ICP

```sql
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10
  AND last_name LIKE '%son';
```

- `dept_id` locates the index slice.
- `last_name` is in the index, so the LIKE predicate can be checked inside the storage engine.
- Only matching entries fetch `salary` from the clustered record.
- `Extra` can display `Using index condition`.

### 6.1. Extra values can combine

An execution plan may involve multiple processing steps, so Extra can contain multiple tokens, such as `Using index condition; Using where` or `Using where; Using index`, depending on the query and version.

Do not insist a query must display one single Extra string. Understand each component and cross-reference it with `key`, `type`, `rows`, and the execution tree.

## 7. Toggling Index Condition Pushdown for testing

ICP is controlled by the `index_condition_pushdown` flag in `optimizer_switch`. In MySQL 8.0/8.4, this flag is generally enabled by default.

Check it:

```sql
SELECT @@SESSION.optimizer_switch;
```

Disable ICP in the current session to compare plans:

```sql
SET SESSION optimizer_switch = 'index_condition_pushdown=off';

EXPLAIN
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10
  AND last_name LIKE '%son';
```

Re-enable it:

```sql
SET SESSION optimizer_switch = 'index_condition_pushdown=on';
```

When ICP is off, the storage engine does not evaluate the secondary predicate on the index via ICP; MySQL may have to fetch more clustered records and filter them in the server layer. In `Extra`, `Using index condition` may disappear and be replaced by another indicator such as `Using where`.

Exact behavior depends on the optimizer, data, and indexes. If the table is tiny or the optimizer picks a table scan, toggling ICP may show no observable difference.

Never disable ICP globally to work around a single query. Use session-level settings in a test or benchmark environment to compare, then restore the original configuration.

## 8. Reading EXPLAIN in different formats

### 8.1. Traditional EXPLAIN

```sql
EXPLAIN
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10
  AND last_name LIKE '%son';
```

Traditional format is ideal for quickly reading `type`, `key`, `rows`, `filtered`, and `Extra`.

### 8.2. EXPLAIN FORMAT=JSON

```sql
EXPLAIN FORMAT=JSON
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10
  AND last_name LIKE '%son';
```

JSON provides a more detailed structure. Depending on version and plan, look for fields such as:

- `used_key_parts`: index columns used for access.
- `index_condition`: condition pushed down to the index/storage engine.
- `attached_condition`: condition attached to the access step or handled at the server layer.
- `using_index`: indicator of covering index usage when applicable.

Not every node contains all of these properties. Read them within the corresponding node/table context, rather than just searching for property names across the entire JSON document.

### 8.3. EXPLAIN FORMAT=TREE

```sql
EXPLAIN FORMAT=TREE
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10
  AND last_name LIKE '%son';
```

TREE presents iterators in execution structure. It helps visualize the order of access, filtering, and joins, though it does not always print the exact same `Extra` wording as the traditional format.

### 8.4. EXPLAIN ANALYZE

```sql
EXPLAIN ANALYZE
SELECT employee_id, dept_id, last_name, salary
FROM employees
WHERE dept_id = 10
  AND last_name LIKE '%son';
```

`EXPLAIN ANALYZE` genuinely executes the query and reports actual row counts and timings per iterator. Use it to verify whether estimated rows match reality and how many rows the filters eliminate.

This command generates real load. Run it only on appropriate datasets and environments; avoid arbitrary execution on heavy queries or queries with unintended side effects.

## 9. Designing indexes to support ICP and covering access

Indexes should be designed from the workload, encompassing filter predicates, JOINs, sort order, and returned columns.

### 9.1. Put the primary selective filter column first

For the query:

```sql
WHERE dept_id = 10
  AND last_name LIKE '%son'
```

Index `(dept_id, last_name)` allows narrowing by `dept_id` first, then checking `last_name` via ICP if the optimizer deems it helpful.

Reversing the order to `(last_name, dept_id)` prevents a leading-wildcard LIKE predicate from forming a normal range on `last_name`; the optimizer then cannot effectively exploit `dept_id` in the second position due to the leftmost prefix rule.

### 9.2. Weigh the cost of adding columns for covering

If a query frequently reads `salary`, you might consider `(dept_id, last_name, salary)` to cover it. However:

- The index grows larger and consumes more pages.
- INSERT/UPDATE operations modifying `salary` must update the index.
- Fewer entries fit per page in the buffer pool.
- Backup, rebuild, and index maintenance costs increase.

Create a covering index only if eliminating clustered lookups yields benefits outweighing write and storage costs.

### 9.3. Do not add unnecessary columns just to remove Using where

`Using where` is not an error to scrub from every plan at any cost. If the residual filter is cheap and applies to only a few rows, adding columns to an index can slow the system down through write amplification.

The goal is reducing total workload cost, not making the Extra column look "pretty".

## 10. Workflow for analyzing a query with Extra

When encountering `Using index`, `Using where`, or `Using index condition`, follow this sequence:

1. **Read the SQL:** identify SELECTed columns, JOINs, WHERE, and ORDER BY.
2. **Inspect indexes:** check column order, unique vs. non-unique, primary key, and which columns actually reside in the index.
3. **Read the access method:** inspect `type`, `key`, `key_len`, `rows`, and `filtered`.
4. **Interpret Extra:** determine whether it reflects covering, residual filtering, or ICP.
5. **Check row counts:** compare estimated rows with actual rows via `EXPLAIN ANALYZE` when appropriate.
6. **Pinpoint the bottleneck:** are too many index entries scanned, too many clustered lookups performed, few rows filtered out, or is a large sort occurring?
7. **Propose changes:** adjust indexes, predicates, or SELECTed columns if beneficial to the overall workload.
8. **Re-measure:** compare latency, rows examined, I/O, and write overhead after the change.

## 11. Common mistakes

| Misconception | Reality | How to handle |
|---|---|---|
| `Using index` means the query reads no data | MySQL still reads index entries; it only avoids clustered record lookups for missing columns | Check entries scanned and access type |
| `Using where` means no index is used | An index may handle part of the predicates while the rest is filtered afterward | Read `key`, `rows`, `filtered`, and predicates |
| `Using index condition` means covering index | ICP can still require reading full rows after entries pass the condition | Verify whether SELECTed columns are in the index |
| ICP turns LIKE '%x' into an index range | ICP only evaluates conditions on entries; it does not turn a leading wildcard into a B-tree range | Check range access and index entries scanned |
| Adding more columns to an index is always good | Wide indexes increase size and write cost | Add columns only when workload and metrics justify it |
| Extra can only have one value | Multiple processing attributes can appear together | Read each component in plan context |
| `EXPLAIN ANALYZE` only estimates | It actually executes the query | Assess load before running |
| Not picking an index on a tiny table is an optimizer bug | A table scan can be cheaper on small tables or unselective filters | Inspect data and measure actual performance |

## 12. Checklist before optimizing production

- [ ] Understood `Using index` as covering access and verified all needed SELECT/JOIN/WHERE columns are present.
- [ ] Understood `Using where` merely indicates filtering, not automatically a slow query.
- [ ] Identified which predicates bound the index range and which act as residual filters.
- [ ] Verified whether `Using index condition` is genuinely applying ICP on a secondary index.
- [ ] Distinguished ICP from a covering index.
- [ ] Inspected `type`, `key`, `key_len`, `rows`, `filtered`, and Extra.
- [ ] Checked how many index entries and clustered row lookups are executed.
- [ ] Evaluated ICP benefit on production-like data distributions.
- [ ] Weighed wide-index cost, write amplification, and buffer pool impact.
- [ ] Safely used `EXPLAIN ANALYZE` to cross-check actual rows when needed.
- [ ] Measured latency and resource usage before and after changes.
- [ ] Avoided adding `FORCE INDEX` or disabling ICP just to alter Extra text.

## 13. Conclusion

`Using index` indicates the query can be covered by the index, avoiding full-row reads for required columns. `Using where` indicates MySQL applies a filter condition to accessed rows/entries; this still occurs even when an index is used. `Using index condition` denotes Index Condition Pushdown: the storage engine checks predicates against indexed columns before reading the clustered record, cutting full-row reads when many entries are filtered out.

These three indicators describe distinct stages and can appear together. Examine the SQL, indexes, access method, estimated/actual rows, and complete execution plan before optimizing. Design indexes to reduce total read/write workload cost, not to remove a particular `Extra` string from the output.

## References

- [MySQL 8.4 Reference Manual: EXPLAIN Output Format](https://dev.mysql.com/doc/refman/8.4/en/explain-output.html)
- [MySQL 8.4 Reference Manual: Index Condition Pushdown Optimization](https://dev.mysql.com/doc/refman/8.4/en/index-condition-pushdown-optimization.html)
- [MySQL 8.4 Reference Manual: Optimizer Switch](https://dev.mysql.com/doc/refman/8.4/en/switchable-optimizations.html)

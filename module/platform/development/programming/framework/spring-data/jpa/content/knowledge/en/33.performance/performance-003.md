# Reading Execution Plans and Designing Indexes for Actual Queries

In Spring Data JPA, repository methods can generate SQL containing WHERE, JOIN, ORDER BY, and secondary queries. Performance depends on the actual SQL, data distribution, statistics, existing indexes, and the plan chosen by the optimizer. Index design must start from **actual queries and execution plans**. Indexes reduce data read, but consume storage and slow down INSERT, UPDATE, and DELETE.

## 1. Repository to SQL

Spring Data builds queries from derived methods, @Query, Criteria, or Specification; Hibernate translates them into dialect-specific SQL. Example:

~~~java
List<RecentOrderView>
findTop20ByTenantIdAndStatusOrderByCreatedAtDesc(
        Long tenantId, OrderStatus status);
~~~

Equivalent SQL:

~~~sql
SELECT id, created_at, total_amount FROM purchase_order
WHERE tenant_id = ? AND status = ?
ORDER BY created_at DESC LIMIT 20;
~~~

Capture the real SQL and bound parameters using Hibernate loggers: Hibernate 6 uses org.hibernate.SQL and org.hibernate.orm.jdbc.bind; Hibernate 5 commonly uses org.hibernate.type.descriptor.sql.BasicBinder. Check projections, lazy loading, and N+1; protect parameters in logs.

## 2. Access Paths and Plans

- **Sequential/table scan:** reads the entire table; can be good for small tables or queries retrieving many rows.
- **Index scan / index-only scan:** looks up via an index; index-only also depends on the visibility map and heap fetches.
- **Bitmap scan:** PostgreSQL combines index locations and then reads the heap in batches.
- **Nested loop join:** good when the outer side is small and the inner side has an index; expensive if repeated many times.
- **Hash/merge join:** alternative choices depending on row count, memory, and data ordering.
- **Sort, hash/group aggregate:** handles ORDER BY/GROUP BY, potentially consuming memory.

MySQL EXPLAIN types include const, eq_ref, ref, range, index, ALL. ALL is a table scan; index scans the entire index rather than doing a selective lookup. Inspect possible_keys, key, rows, filtered, and Extra. Using filesort does not necessarily mean spilling to disk.

## 3. PostgreSQL/MySQL EXPLAIN

PostgreSQL uses EXPLAIN for the estimated plan and EXPLAIN (ANALYZE, BUFFERS) for the actual plan. MySQL uses EXPLAIN/FORMAT=JSON; MySQL 8.0.18+ has EXPLAIN ANALYZE for SELECT. **ANALYZE executes the query**; DML can modify data. Only test in a safe environment; rollback does not undo all sequences, triggers, or external effects.

Compare estimated rows with actual rows. Large discrepancies can cause the optimizer to pick poor join/sort strategies. PostgreSQL cost is an internal unit, not milliseconds; inspect actual time, loops, buffers, and Rows Removed by Filter. Actual time is typically an average per loop. MySQL reports rows, filtered, and actual rows/loops.

## 4. Cardinality, Selectivity, and Statistics

Cardinality is the number of distinct values; selectivity is the fraction of rows matching a condition—smaller means more selective. A single index on status is less helpful if each status accounts for many rows; tenant_id may be more selective. Combining multiple columns can outperform a single column.

PostgreSQL uses ANALYZE/autoanalyze and extended statistics; MySQL uses ANALYZE TABLE and histograms depending on version. ANALYZE updates planner statistics; VACUUM handles dead tuples. Check statistics before adding indexes.

## 5. Composite, Covering, Partial, and Expression Indexes

Example composite B-tree:

~~~sql
CREATE INDEX idx_order_tenant_status_created
ON purchase_order (tenant_id, status, created_at DESC);
~~~

Equality predicates typically precede range/sort columns. The leftmost prefixes of (tenant_id, status, created_at) are tenant_id; tenant_id + status; and all three. Queries filtering only on status typically cannot use this index effectively. PostgreSQL B-trees can scan backward; MySQL 8 supports descending indexes.

A covering index includes filter/returned columns; PostgreSQL supports INCLUDE, while MySQL typically appends columns to the index. A partial index contains only rows matching a predicate; PostgreSQL supports it, while MySQL has no direct equivalent. Expression/functional indexes support lower(email); PostgreSQL supports expression indexes, and MySQL 8.0.13+ supports functional key parts.

## 6. Sargability, JOIN, GROUP BY, and ORDER BY

Sargable predicates allow index lookups. Functions or casts on columns can prevent index usage. Replacing DATE(created_at) = ... with a range from the start of the day to before the start of the next day is usually friendlier to B-trees. Avoid implicit casts. LIKE '%text%' generally cannot use a B-tree for substring search; consider trigram or full-text search.

Check indexes on JOIN/foreign key columns; databases do not necessarily create indexes automatically for every foreign key. Nested loop joins work well when the outer side is small; hash/merge joins depend on cardinality. ORDER BY may require a sort; GROUP BY may require sort/hash aggregate. Read Sort, HashAggregate, GroupAggregate, Using filesort, and Using temporary alongside actual rows/time/buffers.

## 7. Costs, Workflow, and Verification

INSERT adds index entries; UPDATE on indexed columns can modify entries; DELETE updates indexes. Wide indexes consume pages, I/O, and cache; redundant indexes increase write overhead. Inspect primary keys, unique constraints, and existing indexes; evaluate both read and write workloads.

Workflow: entity PurchaseOrder has tenantId, status, createdAt, totalAmount, id; OrderStatus is an enum. Create projection RecentOrderView with getters for id/createdAt/totalAmount; the repository uses the method from section 1; the service calls the method inside @Transactional(readOnly = true). Place each class/interface in a Spring Boot project with spring-boot-starter-data-jpa and a driver. Invoke via an endpoint or integration test with representative data; capture the SQL/bind values, replace placeholders with real values, and run EXPLAIN on actual PostgreSQL/MySQL.

If the plan reads many rows before LIMIT, try an index on tenant/status/createdAt via Flyway/Liquibase; re-run the same query/parameters and compare plan, duration, and buffers/reads. JPA @Index fits simple indexes; migrations fit covering/partial/expression indexes. PostgreSQL CREATE INDEX CONCURRENTLY has limitations and cannot run inside a regular transaction block; MySQL algorithm/lock options depend on engine/version.

Large OFFSET values skip many rows; keyset pagination by createdAt/id can perform better. Indexes do not solve N+1; consider projections, fetch joins, EntityGraph, or batch fetching.

Validate with production-like data and varied bind values; update statistics; run EXPLAIN first; only use EXPLAIN ANALYZE when executing the query is acceptable. Do not run DML ANALYZE on real data without a safe environment. Compare estimated/actual rows, loops, joins/sorts, and buffers; benchmark both endpoints and INSERT/UPDATE/DELETE; protect bound values in logs.

Execution plans turn database optimization from guesswork into evidence-based decisions. Extract the SQL Hibernate generates, read PostgreSQL/MySQL plans, design indexes for query patterns, and re-measure.
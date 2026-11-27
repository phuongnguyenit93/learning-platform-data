# Deploying Constraints in Stages with `NOT VALID` and `VALIDATE`

When a PostgreSQL table already contains substantial data, adding a constraint may require inspecting every existing row. For `CHECK` constraints and foreign keys (`FOREIGN KEY`), PostgreSQL allows splitting this work into two stages: creating the constraint with `NOT VALID`, and then checking historical data with `VALIDATE CONSTRAINT`. This approach puts the new rule into effect early while letting you control when historical data is scanned and cleaned up.

## 1. Why Deploy Constraints in Stages?

Suppose the `orders` table already stores tens of millions of orders. The system needs to enforce two rules:

- Every non-`NULL` `customer_id` must reference an existing customer in `customers`.
- `amount` must be greater than `0`.

If you add constraints the standard way, PostgreSQL must verify that existing data satisfies the rules. On large tables, this check can run long, generate heavy read load, and prolong the lock duration of the DDL operation.

With `NOT VALID`, PostgreSQL registers the constraint without scanning all historical rows at creation time. From that moment onward, new writes must obey the constraint. After resolving violating historical rows, you can run `VALIDATE CONSTRAINT` so PostgreSQL verifies existing data and marks the constraint valid.

## 2. Meaning of `NOT VALID` and `VALIDATE CONSTRAINT`

`NOT VALID` is an option when adding certain constraint types via `ALTER TABLE ... ADD CONSTRAINT`. It means PostgreSQL has not yet verified all existing rows in the table. It does not mean the constraint is disabled.

`VALIDATE CONSTRAINT constraint_name` instructs PostgreSQL to check existing data against the registered constraint. If all data complies, PostgreSQL marks the constraint as validated. If any violating data remains, the command fails and the constraint remains unvalidated; the rule still applies to new write operations.

| State | Data existing before adding constraint | Rows inserted or updated after adding constraint |
|---|---|---|
| No constraint yet | Not checked against the new rule | Not governed by the new constraint |
| Added with `NOT VALID` | Not yet scanned and fully verified | Must satisfy the constraint |
| Successfully `VALIDATE`d | Verified | Must satisfy the constraint |

Thus, the interval between the two commands is the historical-data remediation phase. During this window, new data is already enforced, preventing new violations from accumulating through normal writes.

## 3. Which Constraint Types Support `NOT VALID`?

PostgreSQL supports `NOT VALID` when adding two types of constraints:

- `CHECK`: checks an expression on each row, such as `amount > 0`.
- `FOREIGN KEY`: checks whether foreign key values reference a valid key in the referenced table.

`PRIMARY KEY`, `UNIQUE`, and `EXCLUDE` constraints do not support adding with `NOT VALID`. For uniqueness on large tables, a common deployment strategy is building a unique index via `CREATE UNIQUE INDEX CONCURRENTLY`, then attaching that index to a constraint using `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX`. That approach has its own workflow and limitations, not `NOT VALID`.

A foreign key still requires the referenced column or column group to have an eligible unique key, typically a `PRIMARY KEY` or `UNIQUE` constraint. Adding a foreign key with `NOT VALID` only defers verifying existing rows in the referencing table; it does not bypass structural requirements for foreign keys.

## 4. Standard Deployment Workflow

A rollout should be broken into independently trackable steps:

1. **Prepare application and data.** Define business rules, audit existing write paths, and ensure the upcoming application version produces valid data.
2. **Add the constraint with `NOT VALID`.** Register the rule so subsequent writes are immediately enforced while historical data is not yet scanned.
3. **Locate and remediate violating historical data.** Run targeted queries to identify bad rows; fix, reassign reference keys, or handle rows per business policy.
4. **Validate the constraint.** Run `VALIDATE CONSTRAINT` after historical data is cleaned up.
5. **Verify status.** Read PostgreSQL metadata to confirm the constraint is marked valid.

Separate adding the constraint and validating it into distinct deployment steps. Once added successfully, the constraint already guards new data; operations teams can monitor and clean up old data before triggering the validation scan.

## 5. Example: Adding a Foreign Key and `CHECK` to an Orders Table

Suppose two tables exist with the following general structure:

```sql
CREATE TABLE public.customers (
    id bigint PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE public.orders (
    id bigint PRIMARY KEY,
    customer_id bigint,
    amount numeric(12, 2)
);
```

In a real system, these tables already exist and contain substantial data. We want to ensure every order has a valid `customer_id` when present, and that the amount is positive.

### Step 1: add constraints with `NOT VALID`

```sql
ALTER TABLE public.orders
    ADD CONSTRAINT orders_customer_id_fkey
    FOREIGN KEY (customer_id)
    REFERENCES public.customers (id)
    NOT VALID;

ALTER TABLE public.orders
    ADD CONSTRAINT orders_amount_positive_check
    CHECK (amount > 0)
    NOT VALID;
```

These two commands register the constraints without scanning all historical rows immediately. Once they complete, newly inserted rows or new row versions created by updates must obey the respective rules.

For the foreign key, writes to `orders` are checked against the referenced key. The foreign key mechanism also protects the relationship on related changes in `customers`, according to the declared referential action such as `NO ACTION`, `RESTRICT`, `CASCADE`, or `SET NULL`.

### Step 2: find rows violating the foreign key

You can use a `LEFT JOIN` to find orders with a non-`NULL` `customer_id` that have no matching customer:

```sql
SELECT
    o.id AS order_id,
    o.customer_id
FROM public.orders AS o
LEFT JOIN public.customers AS c
    ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL
ORDER BY o.id;
```

The result lists the rows that must be resolved before validating the foreign key. Depending on business rules, you can reassign `customer_id` to the right customer, restore missing customer records, or archive/delete orders following an approved process. Never fabricate dummy customer keys solely to make validation pass.

If a foreign key spans multiple columns, the violation query must match all columns according to the foreign key's `MATCH` rule. With the default `MATCH SIMPLE`, a row with at least one `NULL` foreign key component does not require a matching referenced row. With `MATCH FULL`, all components must be either all `NULL` or all non-`NULL`.

### Step 3: find rows violating `CHECK`

For `CHECK (amount > 0)`, query non-positive amounts as follows:

```sql
SELECT
    id,
    amount
FROM public.orders
WHERE amount <= 0
ORDER BY id;
```

Matching rows must be corrected from authoritative sources or business rules. If `amount` can be `NULL`, `CHECK (amount > 0)` still permits `NULL`: in PostgreSQL, a `CHECK` constraint passes when the expression evaluates to `TRUE` or `NULL`. If business rules require a non-null amount, add a separate `NOT NULL` constraint or check `amount IS NOT NULL` as well.

For more complex `CHECK` expressions, you can find violations by negating the condition, e.g., `WHERE NOT (check_expression)`. Keep SQL's three-valued logic (`TRUE`, `FALSE`, `NULL`) in mind so your search query accurately reflects the declared rule.

### Step 4: remediate historical data

Perform data fixes in batches if the table is large. For example, update by primary key or key ranges to bound duration and the number of rows touched per transaction. For foreign keys, determine the correct referenced customer. For `CHECK`, pull valid values from reliable data sources or apply agreed business rules.

After each batch, re-run violation queries to verify the count of failing rows decreases. Updating an existing violating row must also produce a new row version satisfying active constraints. For instance, updating an unrelated column on a row that still has `amount <= 0` will fail because the updated row still violates `CHECK`.

### Step 5: validate each constraint

Once historical data complies, run:

```sql
ALTER TABLE public.orders
    VALIDATE CONSTRAINT orders_customer_id_fkey;

ALTER TABLE public.orders
    VALIDATE CONSTRAINT orders_amount_positive_check;
```

PostgreSQL scans the data requiring verification. If no violations remain, the constraint transitions to the validated state. You can validate each constraint individually to make diagnosing failures easier.

If a `VALIDATE CONSTRAINT` command encounters a violation, it fails and the constraint remains unvalidated. It continues enforcing new writes. Read the error, find remaining violating rows, fix the data, and re-run validation.

### Step 6: verify metadata

Check status via the `pg_constraint` catalog:

```sql
SELECT
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.orders'::regclass
  AND conname IN (
      'orders_customer_id_fkey',
      'orders_amount_positive_check'
  )
ORDER BY conname;
```

In the results:

- `conname` is the constraint name.
- `contype` indicates the constraint type, such as `f` for foreign key and `c` for `CHECK`.
- `convalidated = false` indicates existing data has not yet been fully validated.
- `convalidated = true` indicates PostgreSQL has successfully validated the constraint.
- `pg_get_constraintdef` displays the constraint definition to verify against requirements.

Consider the rollout complete only when all intended constraints exist and show `convalidated = true`.

## 6. Impact on Writes and Operations

### Constraints take effect immediately upon creation

Right after a successful `NOT VALID` addition, PostgreSQL checks all subsequent writes. For `CHECK`, new rows must satisfy the expression. For foreign keys, new reference key values must be valid per the foreign key definition. Therefore, before adding constraints, audit application versions, background jobs, ingestion pipelines, and external integrations writing to the table.

If an application still generates violating data, those write statements will receive errors from PostgreSQL. Consequently, the usual rollout order is deploying application code that writes valid data first, then adding the `NOT VALID` constraint.

### Validation still consumes resources

`NOT VALID` avoids scanning old data during constraint creation, but `VALIDATE CONSTRAINT` still reads all data to verify it. On large tables, this scan can generate significant I/O load and run long depending on table size, storage speed, cache hit ratio, and system load.

PostgreSQL designs validation to allow normal read and write operations to continue in many cases. Still, validation acquires appropriate table locks; it can conflict with certain other DDL or maintenance operations. The `ADD CONSTRAINT` command itself also takes DDL locks whose exact level depends on constraint type and operation. Never treat `NOT VALID` as completely lock-free or `VALIDATE` as zero-cost.

On large tables, pick a lower-traffic window, monitor runtime and I/O usage, and avoid stacking multiple DDL operations that could contend on locks. Fixing historical data in small batches also keeps transaction sizes and WAL generation under control.

### Consistency during validation

From the moment the `NOT VALID` constraint is added, new writes are already enforced. Thus, while PostgreSQL scans historical data during validation, ordinary writes cannot introduce new violating rows under that constraint. This is what makes splitting the process into two stages safe while preserving integrity for all data created after constraint creation.

## 7. Limitations and Special Cases

### `NOT VALID` does not apply to all constraints

`PRIMARY KEY`, `UNIQUE`, and `EXCLUDE` cannot be added with `NOT VALID`. To enforce uniqueness on a large table, consider an index-based workflow—typically `CREATE UNIQUE INDEX CONCURRENTLY`, then attaching the index to the constraint with `USING INDEX` when PostgreSQL's prerequisites are met.

### `NOT NULL` has its own workflow

You cannot declare a `NOT NULL` constraint directly with `NOT VALID` syntax. A staged rollout approach is adding `CHECK (column IS NOT NULL) NOT VALID`, fixing `NULL` values, validating the `CHECK`, and then setting the column attribute to `NOT NULL`:

```sql
ALTER TABLE public.users
    ADD CONSTRAINT users_email_not_null_check
    CHECK (email IS NOT NULL)
    NOT VALID;

-- Remediate rows with email IS NULL according to business rules.

ALTER TABLE public.users
    VALIDATE CONSTRAINT users_email_not_null_check;

ALTER TABLE public.users
    ALTER COLUMN email SET NOT NULL;

ALTER TABLE public.users
    DROP CONSTRAINT users_email_not_null_check;
```

In PostgreSQL versions that optimize `SET NOT NULL` by using a valid `CHECK` constraint proving no `NULL`s exist, the `SET NOT NULL` step can skip re-scanning the entire table. That step still requires a DDL lock; test the behavior on your running PostgreSQL version before putting it into deployment pipelines.

### `VALIDATE` does not fix data automatically

The validation command only checks data and updates the constraint's validation flag. It does not pick replacement customers, fix amounts, delete bad rows, or alter business data. Determining how to remediate data belongs to the application and data pipelines.

### Constraint names must be managed explicitly

Use stable, descriptive names that are unique within the table. These names are referenced in `VALIDATE CONSTRAINT`, catalog queries, deployment logs, and recovery procedures. Avoid relying on auto-generated names when automating across multiple environments.

## 8. Troubleshooting and Recovery

When `ADD CONSTRAINT ... NOT VALID` fails, first check syntax errors, duplicate names, data types, referenced keys, and execution permissions. If creation did not succeed, there is no new constraint to validate.

When `VALIDATE CONSTRAINT` fails:

1. Leave the constraint in place and record the error returned by PostgreSQL.
2. Run the corresponding violation query for `CHECK` or `FOREIGN KEY`.
3. Check whether any rows written during historical cleanup need attention; new violating writes would have been blocked by the constraint, yet historical rows still must be found and fixed.
4. Fix data per business rules and re-run the violation query.
5. Re-run `VALIDATE CONSTRAINT`.

If the change must be reverted, you can drop the constraint using `ALTER TABLE ... DROP CONSTRAINT constraint_name`. This removes the corresponding protection, so execute it only as a deliberate deployment decision and assess the impact on subsequent writes. Never drop a constraint merely to make the validation step appear successful.

## 9. Pre-Completion Deployment Checklist

- [ ] Verified the exact table, column, `CHECK` expression, or foreign key relationship to protect.
- [ ] Application and all write paths are ready to comply with the new rule.
- [ ] Constraint was added successfully with `NOT VALID`.
- [ ] Queried and remediated violating historical rows.
- [ ] Evaluated I/O load, runtime, and lock contention risk during validation.
- [ ] `VALIDATE CONSTRAINT` succeeded for every constraint.
- [ ] `pg_constraint.convalidated` returns `true` for all deployed constraints.

Staged deployment enables enforcing data integrity rules early, guarding new data immediately upon constraint creation, and proactively remediating historical data before scanning the whole table. It is a practical technique for `CHECK` and `FOREIGN KEY` changes on large PostgreSQL tables, provided data remediation plans and validation timing are properly prepared.

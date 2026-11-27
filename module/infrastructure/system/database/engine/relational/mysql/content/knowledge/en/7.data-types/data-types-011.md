# ENUM, SET, and Trade-Offs When Changing Value Sets

## Lesson Objectives

After this lesson, you will be able to:

- Explain how MySQL stores and represents `ENUM` and `SET` values.
- Choose between `ENUM`, `SET`, and relational lookup tables based on data domain characteristics.
- Avoid common pitfalls involving invalid values, element ordering, and numeric casting.
- Design value-set changes safely while an application is running.
- Plan adding, renaming, replacing, or removing values without corrupting data.
- Evaluate the impact of DDL, migrations, indexes, applications, and running versions.

In MySQL, `ENUM` and `SET` are two string data types whose value domain is declared directly in the column definition. `ENUM` represents a single choice from a fixed list; `SET` represents a set of zero or more choices from a fixed list. They help constrain data inside the database, yet each type carries its own storage, sorting, and schema-change rules.

The key consideration is not just the initial declaration. A value set can evolve with the business: adding a new status, retiring a channel, renaming an option, or splitting one status into several. Choosing an unsuitable type or changing definitions carelessly can leave old applications, existing data, and new schemas incompatible.

## 1. ENUM: A Single Value from a Fixed List

### 1.1. Declaration and Usage

`ENUM` (enumeration) allows a column to accept one value from a declared list. For example, a ticket has only one status at a time:

~~~sql
CREATE TABLE support_ticket (
    ticket_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    subject VARCHAR(200) NOT NULL,
    status ENUM(
        'new',
        'in_progress',
        'waiting_customer',
        'resolved',
        'closed'
    ) NOT NULL DEFAULT 'new',
    PRIMARY KEY (ticket_id)
) ENGINE = InnoDB;
~~~

Values in `status` must belong to the list. Typical operations:

~~~sql
INSERT INTO support_ticket (subject, status)
VALUES ('Cannot log in', 'new');

UPDATE support_ticket
SET status = 'in_progress'
WHERE ticket_id = 1;

SELECT ticket_id, subject, status
FROM support_ticket
WHERE status = 'in_progress';
~~~

When queried normally, MySQL returns the string label such as `'new'` or `'in_progress'`. Applications usually handle values by their declared labels without needing to know the internal storage index.

`ENUM` is suitable when most or all of the following hold:

- Each row holds only one value from the choice domain.
- The list is relatively small and changes infrequently.
- Values have clear, self-contained meaning in the data model.
- Individual values do not need separate attributes such as descriptions, owners, effective dates, or configuration.
- The engineering team controls schema change procedures and application deployments.

### 1.2. How Is ENUM Stored?

MySQL stores `ENUM` using an internal integer index corresponding to the element's position in the declared list. The first element has index 1, the second has index 2, and so on. Index 0 is a special error value, displayed as an empty string in certain cases where invalid values are accepted in non-strict mode.

Example:

~~~sql
CREATE TABLE enum_demo (
    state ENUM('draft', 'published', 'archived') NOT NULL
);

INSERT INTO enum_demo (state)
VALUES ('draft'), ('published'), ('archived');

SELECT state, state + 0 AS internal_index
FROM enum_demo;
~~~

Illustrative output:

| state | internal_index |
|---|---:|
| draft | 1 |
| published | 2 |
| archived | 3 |

The fact that MySQL maintains an internal index does not mean applications should use that index as a business code. If the list order changes, index meanings shift. Store and exchange stable string labels like `'published'` rather than persisting ordinals in code under the assumption that ordinals never change.

`ENUM` uses 1 byte when the number of elements fits within a single byte and 2 bytes when more are needed. The list can contain up to 65,535 distinct elements; each label is subject to MySQL's length rules. This is a technical limit, not a design target. An `ENUM` with hundreds of choices is usually a sign that you should consider a lookup table.

### 1.3. ENUM Ordering

An important characteristic: `ENUM` sorts by its declared index order, not by lexicographical string order.

~~~sql
SELECT state
FROM enum_demo
ORDER BY state;
~~~

With the declared list `'draft'`, `'published'`, `'archived'`, results sort in that exact order, even though alphabetically `'archived'` would precede `'draft'`.

If the business requires an order different from the definition order, specify the order explicitly in the query:

~~~sql
SELECT ticket_id, status
FROM support_ticket
ORDER BY FIELD(
    status,
    'new',
    'in_progress',
    'waiting_customer',
    'resolved',
    'closed'
);
~~~

Do not reorder the declared list merely to fix one report screen. Reordering affects sorting across all other queries and alters internal integer indexes. Presentation ordering belongs in the query or application layer when it is a display requirement.

### 1.4. Invalid Values and SQL Mode

If you assign a string missing from the `ENUM` list, the result depends on SQL mode. In strict mode, MySQL typically rejects the statement with an error. In non-strict mode, MySQL may convert the invalid value to the special empty-string error value at index 0 and emit a warning.

~~~sql
INSERT INTO enum_demo (state)
VALUES ('under_review');

SHOW WARNINGS;

SELECT state, state + 0
FROM enum_demo
WHERE state = '';
~~~

Index 0 differs from a legitimately declared empty-string member in an `ENUM`. To detect the special error value, compare against the empty string together with the integer index; do not rely on string display alone to distinguish all cases.

Keep an appropriate strict SQL mode enabled for your application and check warnings after data loads. Never let invalid data silently turn into empty values and propagate into reports or business workflows.

Another subtle pitfall is assigning numbers to an `ENUM`. MySQL may interpret integers as element indexes rather than string labels. If the list contains numeric-looking labels or the application passes numeric parameters, outcomes can be surprising. Always pass explicit string labels and avoid using numeric values as the storage interface for `ENUM`.

## 2. SET: Zero or More Values from a Fixed List

### 2.1. Declaration and Usage

`SET` allows a column to contain zero, one, or multiple members from a declared list. For example, an article can be distributed across multiple channels:

~~~sql
CREATE TABLE article (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    channels SET('web', 'mobile', 'email') NOT NULL DEFAULT 'web',
    PRIMARY KEY (article_id)
) ENGINE = InnoDB;
~~~

A row can select one member or multiple members:

~~~sql
INSERT INTO article (title, channels)
VALUES
    ('Maintenance notice', 'web'),
    ('Weekly newsletter', 'web,email'),
    ('App notification', 'mobile,email');

SELECT article_id, title, channels
FROM article;
~~~

Returned values are formatted as a comma-separated string of selected members. MySQL outputs members in the order they were declared in the `SET` definition, regardless of the input string order.

`SET` can hold up to 64 distinct members. Each member has length constraints per MySQL rules. This type suits a small, stable set of options that behave like independent flags and only need storage in a single column.

### 2.2. How Is SET Stored?

MySQL stores `SET` as a bitmask. Each member is assigned a bit according to its declaration position. A `SET` value is the combination of bits enabled for the selected members. Storage size depends on member count, ranging from 1 to 8 bytes.

Example:

~~~sql
CREATE TABLE set_demo (
    features SET('search', 'export', 'share', 'comment') NOT NULL
);

INSERT INTO set_demo (features)
VALUES ('search,share'), ('export'), ('search,export,comment');

SELECT features, features + 0 AS bitmask
FROM set_demo;
~~~

Each member corresponds to one bit; combining multiple members forms a numeric value. Like `ENUM`, the internal number is an implementation detail. Do not use the bitmask as a business code persisted in external systems unless there is a strict, stable contract on member ordering.

Reordering members in the declaration changes the mapping between names and bits. Therefore, never arbitrarily reorder a `SET` list once existing data or applications depend on numeric values.

### 2.3. Searching for SET Members

You can use `FIND_IN_SET` to test whether a member is present in a `SET` value:

~~~sql
SELECT article_id, title, channels
FROM article
WHERE FIND_IN_SET('email', channels) > 0;
~~~

MySQL has a specific optimization when the first argument is a constant and the second is a `SET` column. Still, that does not make `SET` a general-purpose many-to-many relational model. When you need flexible member queries, joins, foreign key constraints, or per-member aggregations, a junction table is usually better.

Do not use `LIKE '%email%'` to search for members. `LIKE` can accidentally match substrings and does not accurately express set-membership semantics.

A `SET` member cannot contain a comma because commas separate members in values. Assigning a nonexistent member is also affected by SQL mode: strict mode typically rejects the statement; in non-strict mode, MySQL may drop invalid members and emit a warning. Example:

~~~sql
INSERT INTO article (title, channels)
VALUES ('Testing nonexistent channel', 'web,fax');

SHOW WARNINGS;
~~~

In non-strict mode, the row may retain only the valid member `'web'`. Check warnings immediately after write statements to prevent partial input loss going unnoticed by the application.

### 2.4. When Is SET Unsuitable?

`SET` becomes hard to manage when:

- The member list changes frequently.
- Individual members need their own metadata, such as display name, sort order, active flag, or permissions.
- A foreign key is required to guarantee selected members exist in a lookup table.
- Rich filtering, joining, counting, pagination, or authorization per member is needed.
- The option set could exceed 64 members.
- Choices are not independent flags but participate in complex business relationships.

For instance, user permissions typically relate to roles, resource scopes, expiration, and grantors. Using a single `SET` column to hold all permissions makes checking and evolving permissions hard to scale. A `user_role`, `role_permission`, or junction table model is far more suitable.

## 3. Choosing ENUM, SET, or a Lookup Table?

`ENUM` and `SET` are useful when the value domain is small and stable. If the list of values has its own lifecycle or needs frequent expansion, model the list as relational data.

| Need | Typically Suitable Option | Reason |
|---|---|---|
| One small, stable status per row | `ENUM` | Enforces a single value at the database level with a simple definition |
| A small, stable set of flags without joins | `SET` | Represents multiple selections in one column |
| Categories with descriptions, ordering, active flags, or effective dates | Lookup table + foreign key | Values become independently manageable data |
| A record linked to multiple categories | Many-to-many junction table | Normalizes relationships and supports foreign keys |
| Value list changing frequently via business configuration | Lookup table | Add/edit/retire values without altering schema |
| Independent flag attributes with fixed semantics | Separate `BOOLEAN` columns or suitable types | Clear queries without unwieldy string sets |

### 3.1. Example: Migrating ENUM to a Lookup Table

Suppose order status initially has only fixed values:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    status ENUM('pending', 'paid', 'shipped', 'cancelled')
        NOT NULL DEFAULT 'pending',
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;
~~~

Later, the business needs descriptions, display order, terminal flags, and whether cancellation is allowed. Rather than extending the `ENUM` further, you can introduce a lookup table:

~~~sql
CREATE TABLE order_status (
    status_code VARCHAR(32) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    sort_order SMALLINT NOT NULL,
    is_terminal BOOLEAN NOT NULL DEFAULT FALSE,
    allows_cancel BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (status_code),
    UNIQUE KEY uq_order_status_sort (sort_order)
) ENGINE = InnoDB;

INSERT INTO order_status
    (status_code, display_name, sort_order, is_terminal, allows_cancel)
VALUES
    ('pending', 'Pending payment', 10, FALSE, TRUE),
    ('paid', 'Paid', 20, FALSE, TRUE),
    ('shipped', 'Shipped', 30, TRUE, FALSE),
    ('cancelled', 'Cancelled', 40, TRUE, FALSE);
~~~

When migrating, add a new column, backfill from the status code, verify no unmapped values exist, and then add the foreign key once data is valid:

~~~sql
ALTER TABLE orders
    ADD COLUMN status_code VARCHAR(32) NULL;

UPDATE orders
SET status_code = CAST(status AS CHAR);

SELECT status, COUNT(*) AS row_count
FROM orders
GROUP BY status;

SELECT COUNT(*) AS missing_status
FROM orders
WHERE status_code IS NULL;
~~~

The snippet above illustrates the backfill step; a real migration must verify the full value set and clean any invalid rows before switching applications. Once the new column is populated and applications use it, add constraints:

~~~sql
ALTER TABLE orders
    MODIFY status_code VARCHAR(32) NOT NULL,
    ADD CONSTRAINT fk_orders_status
        FOREIGN KEY (status_code)
        REFERENCES order_status(status_code);
~~~

Renaming or dropping the old `ENUM` column is a separate step, performed only after no application version reads or writes the old column and a rollback/roll-forward plan is ready.

## 4. Risks When Changing Value Sets

Changing an `ENUM` or `SET` definition is a schema change, not just editing a string in application code. You must evaluate existing data, element ordering, default values, `NULL`s, indexes, queries, ORMs, running application versions, and DDL cost.

### 4.1. Adding an ENUM Value

Suppose you need to add the `'refunded'` status. Modify the definition:

~~~sql
ALTER TABLE support_ticket
    MODIFY COLUMN status ENUM(
        'new',
        'in_progress',
        'waiting_customer',
        'resolved',
        'closed',
        'refunded'
    ) NOT NULL DEFAULT 'new';
~~~

When using `MODIFY COLUMN`, re-declare all column attributes you want to keep, such as `NULL`/`NOT NULL`, `DEFAULT`, `COMMENT`, `CHARACTER SET`/`COLLATE`, and other options. Omitting an attribute can unintentionally alter the column definition.

Appending new values to the end of the list is usually safer because it preserves the ordering of existing values. Still, verify your MySQL version and DDL conditions: some changes execute quickly as metadata-only operations, whereas others may rebuild the table or hold metadata locks. Never assume every `ALTER ENUM` is instant or risk-free.

### 4.2. Adding a SET Member

Suppose you need to add the `'push'` channel:

~~~sql
ALTER TABLE article
    MODIFY COLUMN channels
        SET('web', 'mobile', 'email', 'push')
        NOT NULL DEFAULT 'web';
~~~

Appending members at the end preserves the bit positions of existing members. Adding a member can increase storage size when the member count crosses a byte boundary. Online/instant DDL availability depends on MySQL version and the exact change; test on the target version with representative data.

### 4.3. Renaming a Value

`ENUM` and `SET` have no standalone rename-member operation. Renaming is typically done by modifying the column definition and migrating data.

For example, renaming `'waiting_customer'` to `'waiting_user'`. First add the new label to the schema, then update existing rows:

~~~sql
ALTER TABLE support_ticket
    MODIFY COLUMN status ENUM(
        'new',
        'in_progress',
        'waiting_customer',
        'waiting_user',
        'resolved',
        'closed',
        'refunded'
    ) NOT NULL DEFAULT 'new';

UPDATE support_ticket
SET status = 'waiting_user'
WHERE status = 'waiting_customer';
~~~

After backfilling, applications must read and write the new label. Only remove the old label from the `ENUM` in a later migration after confirming no legacy rows remain and no older application version writes the old label.

Never rename in a single step while multiple application versions are running concurrently. Older versions could keep writing the old label after the schema removed it.

### 4.4. Removing a Value Currently in Use

Before removing a value, count how many rows currently use it:

~~~sql
SELECT status, COUNT(*) AS row_count
FROM support_ticket
GROUP BY status
ORDER BY status;
~~~

If rows carry the value to be removed, decide on the business mapping. For example, you might migrate an old status to a replacement status once approved by business stakeholders:

~~~sql
UPDATE support_ticket
SET status = 'closed'
WHERE status = 'resolved';
~~~

Do not treat the mapping example above as a universal rule; the replacement status must match business semantics. Only after data is migrated and verified should you alter the `ENUM` definition to remove the old value.

If the new definition no longer includes a value present in existing rows, the alteration may produce the special error value or fail depending on SQL mode and how the DDL runs. Never rely on type coercion to silently discard data.

For `SET`, before removing a member, find all rows containing that member, decide whether to keep or strip it from each row, and only then modify the definition. Example:

~~~sql
SELECT article_id, channels
FROM article
WHERE FIND_IN_SET('mobile', channels) > 0;
~~~

MySQL does not have a simple built-in function to remove a `SET` member by name. For small lists, you can map each known combination to its new combination using `CASE`; the example below covers the four combinations containing `'mobile'` in this lesson's three-member list:

~~~sql
UPDATE article
SET channels = CASE channels
    WHEN 'mobile' THEN ''
    WHEN 'web,mobile' THEN 'web'
    WHEN 'mobile,email' THEN 'email'
    WHEN 'web,mobile,email' THEN 'web,email'
    ELSE channels
END
WHERE FIND_IN_SET('mobile', channels) > 0;
~~~

In real systems, cover every possible combination or migrate data via tested application logic. Afterward, verify that zero rows still contain the member before removing it from the definition.

### 4.5. Reordering Elements

Element order is not a harmless cosmetic detail:

- `ENUM` sorts by declared index; reordering changes `ORDER BY` results and internal index mappings.
- `SET` assigns bits by member position; reordering changes internal bitmasks.
- Applications or reports relying on numeric values may misinterpret data after a reorder.

Keep existing element ordering intact and only append new values to the end when expanding. If reordering is truly unavoidable, treat it as a controlled data migration, test thoroughly, and verify no system depends on ordinals or bitmasks.

## 5. Safe Migration Workflow While Applications Are Running

A schema change must account for multiple application versions coexisting during deployment. For instance, a new version might write `'refunded'` while an older worker only recognizes earlier statuses.

An expand-and-contract workflow is generally safer:

~~~mermaid
flowchart TD
    A[Assess change and existing data] --> B[Expand schema: add new values]
    B --> C[Deploy code compatible with old and new]
    C --> D[Backfill / migrate data if needed]
    D --> E[Verify data and logs]
    E --> F[Switch all read/write flows to new values]
    F --> G[Wait for old application versions to drain]
    G --> H[Contract: remove old values/columns]
    H --> I[Monitor post-migration]
~~~

### Step 1: Pre-Change Inventory

Before editing the schema, record:

- Full column definition via `SHOW CREATE TABLE`.
- Row counts per value and any anomalous values.
- `DEFAULT`, `NULL`/`NOT NULL`, charset/collation, and related indexes.
- Queries, views, triggers, stored procedures, and jobs referencing the column.
- Application versions, ORMs, APIs, and consumers reading/writing the values.
- Table size, write rate, metadata lock risk, and deployment window limits.

Capture definitions and data distribution:

~~~sql
SHOW CREATE TABLE support_ticket;

SELECT status, COUNT(*) AS row_count
FROM support_ticket
GROUP BY status
ORDER BY status;
~~~

### Step 2: Expand Schema

Append new labels to the end of the list while preserving existing labels, `DEFAULT`, and nullability. Confirm the DDL can execute within the planned deployment window. If online schema change is needed, evaluate tooling, locking, triggers, foreign keys, and operational limits beforehand.

### Step 3: Deploy Compatible Application Code

Deploy code capable of reading both old and new values. Only begin writing new values after all critical readers understand them, including APIs, consumers, reports, batch jobs, and background workers.

In multi-service architectures, define the deployment sequence. An un-updated service could reject new data or display statuses incorrectly.

### Step 4: Migrate and Verify Data

If the change requires renaming or replacing values, backfill in batches with explicit predicates. On large tables, avoid one massive `UPDATE` that holds locks long, bloats undo logs, or spikes replication lag. Track progress and make backfills safely resumable.

After backfilling, verify:

- No unexpected rows still use old values.
- No special `ENUM` error values exist.
- Pre- and post-migration row counts match business expectations.
- Replicas stay caught up with no apply errors.
- Queries, reports, and write paths behave properly.

### Step 5: Contract Schema

Remove old values only after all application versions capable of writing them are retired, un-updated consumers are gone, and data migration is complete. Contraction can be a separate `ALTER TABLE`. For high-risk changes, retain a roll-forward migration path and appropriate backups.

Do not treat SQL `ROLLBACK` as a general recovery mechanism for DDL. Many DDL statements in MySQL trigger an implicit commit. Design a safe forward-moving path with verified data recovery procedures.

## 6. Impact on Indexes, Queries, and Applications

### 6.1. Indexing ENUM and SET

You can create indexes on `ENUM` or `SET` columns:

~~~sql
CREATE INDEX idx_ticket_status
ON support_ticket (status);
~~~

An index can help status-filter queries, though its benefit depends on selectivity, data distribution, and actual queries. If most rows share a single status, a single-column index may provide little benefit. Inspect plans with `EXPLAIN` and benchmark on representative data.

~~~sql
EXPLAIN
SELECT ticket_id, subject
FROM support_ticket
WHERE status = 'in_progress';
~~~

When changing an `ENUM`/`SET` set, re-evaluate indexes, statistics, and queries using numeric comparisons or column sorting. In particular, `ORDER BY ENUM` follows definition order; altering the list can change report orderings even when string values appear unchanged.

### 6.2. Applications and ORMs

Some ORMs map language enums to string names, ordinals, or native types depending on configuration. Verify the actual mapping behavior.

In Java, when applications use enums, prefer storing stable string names or codes via explicit mapping. JPA `EnumType.STRING` stores `Enum.name()`, so it fits directly only when Java enum constant names match database labels. If Java names differ from database labels or require independent stable storage codes, use an `AttributeConverter`. Avoid `EnumType.ORDINAL` because source-code enum declaration order can change and silently shift the meaning of stored numbers.

A Java enum can be written as:

~~~java
public enum TicketStatus {
    NEW("new"),
    IN_PROGRESS("in_progress"),
    WAITING_CUSTOMER("waiting_customer"),
    RESOLVED("resolved"),
    CLOSED("closed");

    private final String databaseValue;

    TicketStatus(String databaseValue) {
        this.databaseValue = databaseValue;
    }

    public String databaseValue() {
        return databaseValue;
    }
}
~~~

This illustrates an explicit storage code. You still need to configure a converter or mapping so JDBC/ORM actually uses `databaseValue`; merely adding a method does not change JPA's default behavior.

When receiving data from APIs, do not assume every client upgrades simultaneously. APIs should handle unknown values deliberately: reject with a clear error, preserve the string if the contract permits, or map to an appropriate fallback state. Never silently coerce a new value into another business status.

## 7. Operational Checks Before and After DDL

Before making changes:

~~~sql
SELECT VERSION() AS mysql_version,
       @@sql_mode AS sql_mode,
       @@autocommit AS autocommit_mode;

SHOW CREATE TABLE support_ticket;

SELECT status, COUNT(*) AS row_count
FROM support_ticket
GROUP BY status;
~~~

Check column type and definition in metadata:

~~~sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'support_ticket'
  AND COLUMN_NAME = 'status';
~~~

Immediately after `ALTER`, inspect warnings before running another SQL statement; `SHOW WARNINGS` shows warnings for the most recent statement:

~~~sql
SHOW WARNINGS;

SHOW CREATE TABLE support_ticket;

SELECT status, status + 0 AS enum_index, COUNT(*) AS row_count
FROM support_ticket
GROUP BY status, status + 0
ORDER BY enum_index;
~~~

For `SET`, you can count each existing combination. If you need counts per individual member, split members via queries or appropriate data processing; do not count `SET` strings as if each combination were a single independent member.

In production, monitor metadata locks, `ALTER` duration, temporary disk usage, I/O, replica lag, and application error rates. Avoid running definition-changing migrations on large tables during peak traffic without testing on representative data.

## 8. Data Type Decision Checklist

Before choosing `ENUM` or `SET`, ask yourself:

- [ ] Is the value domain small and stable over the system's lifecycle?
- [ ] Does each row need a single choice (`ENUM`) or a small set of independent flags (`SET`)?
- [ ] Do values need descriptions, translations, sort orders, effective dates, or separate metadata?
- [ ] Is a foreign key needed to validate individual values?
- [ ] Can multiple services or clients evolve independently?
- [ ] Can adding/removing values be rolled out via controlled migrations?
- [ ] Do filtering, sorting, and aggregation queries align with `ENUM`/`SET` semantics?
- [ ] Does any application rely on ordinals or bitmasks?

If the value domain changes frequently, requires separate metadata, or needs foreign key relationships, prefer a lookup table or junction table. If the list is small, stable, and tightly controlled, `ENUM`/`SET` can be a simple and effective choice.

## 9. Practice Exercises

### Exercise 1: Exploring ENUM

Create a ticket table with an `ENUM` `status`. Insert several rows, query `status` and `status + 0`, then test `ORDER BY status` vs. `ORDER BY FIELD`. Record the differing orders.

### Exercise 2: Observing SQL Mode

Try inserting a value missing from the `ENUM` list in both strict and non-strict mode in a dedicated practice database. Run `SHOW WARNINGS` and observe index 0. Restore SQL mode after the exercise.

### Exercise 3: Exploring SET

Create a `SET` column containing `web`, `mobile`, and `email`. Insert rows with single and multiple members, query using `FIND_IN_SET`, and inspect numeric values by adding 0. Try inserting an invalid member and observe the result per SQL mode.

### Exercise 4: Adding a New Value Without Breaking Old Code

Append a new member to the end of an `ENUM` or `SET`. Write tests proving old data remains readable, `DEFAULT` is unchanged, and legacy application code does not write the new value. Plan the application rollout before enabling writes of the new value.

### Exercise 5: Replacing ENUM with a Lookup Table

Create `order_status`, add `status_code` to `orders`, backfill data, verify distribution, and add the foreign key. Outline compatible application deployment steps before dropping the old `ENUM` column.

### Exercise 6: Writing a Value-Removal Plan

Pick an old value currently in use. Draft a plan covering data inventory, business mapping, batched backfill, verifying all consumers are updated, and finally removing the value from the definition. Specify how to handle failures at each step.

## Conclusion

`ENUM` suits a single choice from a small, stable value domain. `SET` suits a small set of independent choices. Both carry internal storage and ordering rules that must be understood clearly; modifying the list is a schema change that must be coordinated with data, applications, and downstream consumers.

When a list has its own lifecycle, rich metadata, foreign key relationships, or frequent changes, switch to a lookup table or junction table. A sound design preserves data meaning across many releases, even when old and new application versions operate side by side.

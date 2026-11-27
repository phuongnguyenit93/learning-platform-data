# Table/Column Comments and Naming Conventions for Oracle Documentation

A database may run smoothly from a technical standpoint yet still be hard to maintain if others do not know what kind of customers the `CUSTOMER` table stores, which values are valid in `STATUS`, or which currency `AMOUNT` uses. After a few months, object names and data types alone are no longer enough to explain business semantics. Therefore, schema documentation should be written **alongside DDL**, stored in Oracle metadata where appropriate, and version-controlled just like source code.

In Oracle Database, two foundational tools for this are:

- **`COMMENT ON TABLE` / `COMMENT ON COLUMN`:** stores table and column comments in the database's data dictionary.
- **Naming conventions:** names tables, columns, keys, constraints, and indexes following consistent rules so someone unfamiliar with the project can still deduce the structure accurately.

This lesson shows how to combine those two tools, query metadata to generate a data dictionary, and keep documentation synchronized as the schema evolves. Examples use Oracle SQL inside an application schema of a practice PDB.

## 1. How does database documentation differ from source code comments?

In a Java/Oracle project, information about a table can live in multiple places:

| Storage location | Example | Typical reader | Limitation |
|---|---|---|---|
| **Object names** | `LAB_ORDER.TOTAL_AMOUNT` | SQL developers, DBAs, applications, ERD tools | Concise; cannot express full business rules |
| **Oracle metadata** | `COMMENT ON COLUMN LAB_ORDER.TOTAL_AMOUNT IS '...'` | Dictionary query users, DB tools, doc generators | Textual description; does not enforce logic itself |
| **DDL and constraints** | `NOT NULL`, `PRIMARY KEY`, `CHECK`, `FOREIGN KEY` | Oracle optimizer, developers, DBAs | Expresses enforceable rules, not the full business intent |
| **Versioned migrations** | `V002__document_lab_order.sql` | Developers, CI/CD, operators | Must be applied in order to the database |
| **External business docs** | Data dictionary, ERD, glossary, ADR | Developers, analysts, product, auditors | Can go stale if not synced with the real schema |

Good design typically has **three complementary layers**:

1. **Clear names** so readers immediately recognize which domain an object belongs to.
2. **Constraints and data types** so Oracle enforces verifiable rules.
3. **Comments and business docs** to explain provenance, units, meaning, and data lifecycle.

For example, `ORDER_STATUS` has type `VARCHAR2(20)` and a `CHECK` constraint limiting codes to `NEW`, `PAID`, and `CANCELLED`. The constraint prevents writing codes outside the list; the comment explains **when** an order transitions to `PAID`, what `CANCELLED` means, and whether canceled orders can be restored.

> **Key principle:** Comments are descriptions for humans and metadata-reading tools. If a rule must be enforced by the database, express it via constraints, keys, privileges, or an appropriate enforcement mechanism; never leave it only in a comment.

## 2. Where comments live in the schema and data dictionary

Oracle organizes objects inside a **schema**, the collection of objects belonging to a database user. In multitenant architecture, schemas reside inside a **PDB**. A table is uniquely identified by `SCHEMA.TABLE_NAME`, and a column by `SCHEMA.TABLE_NAME.COLUMN_NAME`.

~~~text
Oracle CDB
└── PDB: SALES_PDB
    ├── Schema: SALES_APP
    │   ├── Table: LAB_CUSTOMER
    │   │   ├── CUSTOMER_ID          ── column comment
    │   │   └── CUSTOMER_CODE        ── column comment
    │   └── Table: LAB_ORDER         ── table comment
    │       ├── ORDER_ID             ── column comment
    │       ├── CUSTOMER_ID          ── column comment
    │       ├── ORDER_STATUS         ── column comment
    │       ├── TOTAL_AMOUNT         ── column comment
    │       └── CURRENCY_CODE        ── column comment
    └── Schema: REPORT_APP
        └── View: V_ORDER_SUMMARY    ── report description
~~~

When a `COMMENT ON` statement succeeds, Oracle stores the comment inside the **data dictionary**. Common views for reading them:

- `USER_TAB_COMMENTS`: table/view comments owned by the current user.
- `USER_COL_COMMENTS`: column comments on objects owned by the current user.
- `ALL_TAB_COMMENTS` and `ALL_COL_COMMENTS`: metadata for objects visible to the user, including `OWNER`.
- `DBA_TAB_COMMENTS` and `DBA_COL_COMMENTS`: broader administrative scope, requiring appropriate catalog privileges.

`USER_*` views are convenient for developers because no `OWNER` filter is needed when logged in as the schema owner.

**PDB note:** Metadata output depends on the container your session is connected to and your active privileges. Seeing the same table name in two PDBs does not mean they are the same object. Before building or exporting a data dictionary, confirm the right PDB/service first.

## 3. Syntax of COMMENT ON TABLE and COMMENT ON COLUMN

### 3.1. Table comments

Basic syntax:

~~~sql
COMMENT ON TABLE lab_order IS
  'Stores customer orders; each row represents one order.';
~~~

A comment should answer: what the table is for, what one row represents, when data is created, who consumes it, and any notable business boundaries. The example above defines the table's **grain**: **one row = one order**. That adds far more value than writing "Orders table," which the table name already conveys.

### 3.2. Column comments

~~~sql
COMMENT ON COLUMN lab_order.total_amount IS
  'Total order amount in the currency specified by CURRENCY_CODE; non-negative.';
~~~

A column comment should cover **meaning**, **units**, **valid domain**, **null semantics**, **data source**, or relationships with other columns as needed. There is no need to mechanically repeat `NUMBER(15,2)` or `NOT NULL` because the data dictionary already records those.

### 3.3. Can you comment on objects in another schema?

Fully qualified names can be written as:

~~~sql
COMMENT ON TABLE sales_app.lab_order IS
  'Stores one record per order in the sales system.';

COMMENT ON COLUMN sales_app.lab_order.order_status IS
  'Business status: NEW, PAID, or CANCELLED.';
~~~

To comment on a table or column, the user must own the object or hold the appropriate system privilege, such as the privilege to comment on any table per Oracle policy. In development practice, the safest and cleanest approach is to **run migrations using the schema-owning account** or a deployment account with explicitly granted privileges.

### 3.4. Comment strings containing single quotes

In Oracle SQL, a literal single quote inside a string is escaped as **two single quotes**:

~~~sql
COMMENT ON COLUMN lab_customer.display_name IS
  'Customer-provided display name; never use as an identifier key.';

COMMENT ON COLUMN lab_order.order_status IS
  'NEW means ''newly created'', PAID means ''paid''.';
~~~

For longer text containing multiple quotes, Oracle supports alternative quoting syntax such as `q'[ ... ]'`:

~~~sql
COMMENT ON COLUMN lab_order.order_status IS
  q'[NEW = 'newly created'; PAID = 'paid';
CANCELLED = 'cancelled'. Do not infer status from display name.]';
~~~

Keep comments clear and concise enough for metadata tools to display comfortably; very long descriptions, multi-branch business flows, or diagrams generally belong in dedicated documentation referenced by document title or stable ID.

### 3.5. Updating or removing a comment

Running `COMMENT ON` again on the same table or column **replaces** the previous comment:

~~~sql
COMMENT ON COLUMN lab_order.total_amount IS
  'Receivable order amount in the ISO 4217 currency in CURRENCY_CODE.';
~~~

When you no longer want to keep a comment, in Oracle you can set it to an empty string:

~~~sql
COMMENT ON COLUMN lab_order.total_amount IS '';
~~~

Oracle treats empty character literals as `NULL` in standard string context; query `USER_COL_COMMENTS` to confirm the result. In real projects, deleting comments can lose business context: remove them only deliberately after relocating the documentation appropriately.

**`COMMENT` is a DDL statement.** In Oracle, DDL generally triggers an implicit commit per database rules; never expect `ROLLBACK` after `COMMENT ON` to restore an old description. Place comment changes inside versioned migrations and treat them as formal schema changes.

## 4. Creating an example schema with clear names and comments

The following examples use two tables in an application schema:

- `LAB_CUSTOMER`: one row represents one business customer.
- `LAB_ORDER`: one row represents one order; references the customer via a foreign key.

Assume you are connected to a **practice PDB** and the user has table creation privileges. Create these tables **only once** in a clean schema or inside a controlled migration.

~~~sql
CREATE TABLE lab_customer (
    customer_id    NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_code  VARCHAR2(32 CHAR) NOT NULL,
    display_name   VARCHAR2(200 CHAR) NOT NULL,
    created_at     TIMESTAMP WITH TIME ZONE
                     DEFAULT SYSTIMESTAMP NOT NULL,

    CONSTRAINT pk_lab_customer
      PRIMARY KEY (customer_id),

    CONSTRAINT uq_lab_customer_code
      UNIQUE (customer_code)
);

CREATE TABLE lab_order (
    order_id       NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_id    NUMBER NOT NULL,
    order_status   VARCHAR2(20 CHAR) DEFAULT 'NEW' NOT NULL,
    total_amount   NUMBER(15,2) NOT NULL,
    currency_code  VARCHAR2(3 CHAR) DEFAULT 'VND' NOT NULL,
    ordered_at     TIMESTAMP WITH TIME ZONE
                     DEFAULT SYSTIMESTAMP NOT NULL,

    CONSTRAINT pk_lab_order
      PRIMARY KEY (order_id),

    CONSTRAINT fk_lab_order_customer
      FOREIGN KEY (customer_id)
      REFERENCES lab_customer (customer_id),

    CONSTRAINT ck_lab_order_status
      CHECK (order_status IN ('NEW', 'PAID', 'CANCELLED')),

    CONSTRAINT ck_lab_order_amount
      CHECK (total_amount >= 0)
);
~~~

This example uses **identity columns** (Oracle 12c and later) so the database generates keys instead of the application. `PK`, `FK`, `UQ`, and `CK` constraints enforce machine-checkable rules. Monetary amounts use `NUMBER(15,2)` for exact decimal representation within declared precision/scale, while `CURRENCY_CODE` makes the unit explicit. `TIMESTAMP WITH TIME ZONE` stores timestamps with timezone/offset information; applications should follow a consistent display conversion convention.

### 4.1. Commenting on both tables

~~~sql
COMMENT ON TABLE lab_customer IS
  'Customer master list for orders; each row represents one business customer.';

COMMENT ON TABLE lab_order IS
  'Customer orders; each row represents one order, not an order line item.';
~~~

These two comments establish scope and **grain**. If a `LAB_ORDER_ITEM` table is added later, its grain will be "one product within an order" or "one order line item" per actual design, distinct from `LAB_ORDER`.

### 4.2. Commenting on every customer column

~~~sql
COMMENT ON COLUMN lab_customer.customer_id IS
  'Internal surrogate key for the customer; generated by Oracle identity.';

COMMENT ON COLUMN lab_customer.customer_code IS
  'Unique business code for the customer; used for integration reconciliation.';

COMMENT ON COLUMN lab_customer.display_name IS
  'Customer display name; mutable and must not be used as a key.';

COMMENT ON COLUMN lab_customer.created_at IS
  'Timestamp when the customer record was created; assigned via SYSTIMESTAMP.';
~~~

`CUSTOMER_ID` and `CUSTOMER_CODE` need separate comments because they serve **different roles**. `CUSTOMER_ID` is a stable internal surrogate key; `CUSTOMER_CODE` is a business key exchanged across systems. Even if both happen to share formatting or numeric/string types in another project, they must never be treated as interchangeable.

### 4.3. Commenting on every order column

~~~sql
COMMENT ON COLUMN lab_order.order_id IS
  'Surrogate key for the order; generated by Oracle identity.';

COMMENT ON COLUMN lab_order.customer_id IS
  'Customer owning the order; references LAB_CUSTOMER.CUSTOMER_ID.';

COMMENT ON COLUMN lab_order.order_status IS
  'Status: NEW = newly created; PAID = paid; CANCELLED = cancelled.';

COMMENT ON COLUMN lab_order.total_amount IS
  'Total order amount, non-negative; currency unit is in CURRENCY_CODE.';

COMMENT ON COLUMN lab_order.currency_code IS
  '3-character ISO 4217 currency code, e.g., VND or USD.';

COMMENT ON COLUMN lab_order.ordered_at IS
  'Timestamp when the order occurred; stored as TIMESTAMP WITH TIME ZONE.';
~~~

What comments **cannot** replace:

- `ORDER_STATUS` has a comment listing valid codes, yet the **`CHECK`** constraint is what blocks values outside the list.
- `CUSTOMER_ID` has a comment describing the relationship, yet the **foreign key** is what protects referential integrity when enabled and validated per configuration.
- `TOTAL_AMOUNT` has a comment saying "non-negative," yet the **check constraint** enforces that rule.
- `CURRENCY_CODE` mentions ISO 4217 in its comment, yet DDL only enforces a three-character max; rejecting codes outside the official ISO list requires a reference lookup table/constraint or business validation.

## 5. Reading comments from USER_TAB_COMMENTS and USER_COL_COMMENTS

After running `COMMENT ON`, you do not need to reopen individual migration files to read descriptions. Oracle lets you query metadata directly.

### 5.1. Viewing table comments

~~~sql
SELECT
    table_name,
    table_type,
    comments
FROM user_tab_comments
WHERE table_name IN ('LAB_CUSTOMER', 'LAB_ORDER')
ORDER BY table_name;
~~~

In the dictionary, `TABLE_NAME` holds the object name; `TABLE_TYPE` distinguishes the object type represented; `COMMENTS` holds the text written by administrators/developers. If a table exists without a comment yet, `COMMENTS` is typically `NULL`.

To view comments on all tables and views owned by the schema:

~~~sql
SELECT table_name, table_type, comments
FROM user_tab_comments
ORDER BY table_name;
~~~

### 5.2. Viewing column comments in definition order

~~~sql
SELECT
    c.table_name,
    c.column_id,
    c.column_name,
    c.data_type,
    c.nullable,
    cc.comments AS column_comment
FROM user_tab_columns c
LEFT JOIN user_col_comments cc
  ON cc.table_name = c.table_name
 AND cc.column_name = c.column_name
WHERE c.table_name IN ('LAB_CUSTOMER', 'LAB_ORDER')
ORDER BY c.table_name, c.column_id;
~~~

`USER_TAB_COLUMNS` supplies structural metadata; `USER_COL_COMMENTS` supplies descriptions. Joining both automatically produces a data dictionary table: column name, position, type, nullability, and meaning. Columns without comments still appear thanks to the `LEFT JOIN`.

In Oracle, unquoted object names are stored in **uppercase** in the dictionary. Thus `WHERE TABLE_NAME = 'LAB_ORDER'` uses uppercase even though `CREATE TABLE lab_order` earlier used lowercase.

### 5.3. Generating a table's data dictionary

~~~sql
SELECT
    c.column_id                      AS ordinal_position,
    c.column_name,
    CASE
      WHEN c.data_type IN ('VARCHAR2', 'CHAR') THEN
        c.data_type || '(' || c.char_length || ' CHAR)'
      WHEN c.data_type = 'NUMBER'
           AND c.data_precision IS NOT NULL THEN
        'NUMBER(' || c.data_precision || ',' ||
        NVL(c.data_scale, 0) || ')'
      ELSE c.data_type
    END                              AS display_type,
    c.nullable,
    cc.comments                      AS business_meaning
FROM user_tab_columns c
LEFT JOIN user_col_comments cc
  ON cc.table_name = c.table_name
 AND cc.column_name = c.column_name
WHERE c.table_name = 'LAB_ORDER'
ORDER BY c.column_id;
~~~

`DISPLAY_TYPE` here is a **simplified display string**, not a complete DDL generator: Oracle has many more data types, byte/char length semantics, and specialized attributes. When exact DDL is required, use dedicated metadata APIs such as `DBMS_METADATA.GET_DDL` or appropriate administrative tools.

For `LAB_ORDER`, a rendered data dictionary can look like:

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| `ORDER_ID` | `NUMBER` (identity) | No | Surrogate key of the order |
| `CUSTOMER_ID` | `NUMBER` | No | Customer reference |
| `ORDER_STATUS` | `VARCHAR2(20 CHAR)` | No | NEW / PAID / CANCELLED |
| `TOTAL_AMOUNT` | `NUMBER(15,2)` | No | Amount in `CURRENCY_CODE` |
| `CURRENCY_CODE` | `VARCHAR2(3 CHAR)` | No | ISO 4217 code |
| `ORDERED_AT` | `TIMESTAMP WITH TIME ZONE` | No | Order creation timestamp |

Do not use this summary table as a complete substitute for constraints, indexes, and relationships, which are vital structural traits retrieved from other dictionary views.

## 6. Querying comments across schemas and in CDB/PDB

### 6.1. When the user is not the owner

If your account has privileges to view objects in `SALES_APP`, you can query:

~~~sql
SELECT owner, table_name, comments
FROM all_tab_comments
WHERE owner = 'SALES_APP'
  AND table_name = 'LAB_ORDER';

SELECT owner, table_name, column_name, comments
FROM all_col_comments
WHERE owner = 'SALES_APP'
  AND table_name = 'LAB_ORDER'
ORDER BY column_name;
~~~

`ALL_*` views reflect **objects the user can access/see**, not every table in every schema. Reading metadata from `DBA_*` may require catalog privileges granted by a DBA.

### 6.2. When a database has multiple PDBs

Before exporting a data dictionary, confirm the container:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS database_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

For example, the session might be in `SALES_PDB` with `CURRENT_SCHEMA = SALES_APP`, while `SESSION_USER = REPORT_APP`. That **does not turn `REPORT_APP` into the owner**. `USER_*` views follow the dictionary's user/schema definition; when targeting a specific owner explicitly, use `ALL_*` filtered by `OWNER`.

In a CDB, an administrative account can use appropriate `CDB_*` views to inspect multi-container metadata and distinguish `CON_ID`, provided privileges and container-data settings allow it. Still, for exercises and applications, the simplest and least error-prone path is to **connect to the right service/PDB and query metadata inside that PDB**.

## 7. Naming conventions: making names self-documenting

Before adding comments, name objects so anyone reading SQL immediately infers the right meaning. A consistent convention streamlines search, migration reviews, doc generation, and communication between developers and DBAs.

### 7.1. Foundational rules for Oracle identifiers

- **Avoid double quotes for standard identifiers.** Oracle stores unquoted names in uppercase and allows case-insensitive references.
- **Pick one convention**, such as unaccented English words separated by underscores (`SNAKE_CASE`). DDL can write `lab_order`; the dictionary displays `LAB_ORDER`.
- **Avoid keywords or confusing names**, such as `ORDER`, `DATE`, or `USER`, which collide with reserved keywords or widespread identifiers.
- **Do not encode data types in names** if types might change, like `STR_CUSTOMER_NAME` or `NUM_AMOUNT`; names should express semantics.
- **Use standardized abbreviations.** `ID` and `URL` are universally familiar; `DT`, `CD`, and `FLG` should only be used if defined consistently in a glossary.
- **Respect name length limits.** Modern Oracle versions (12.2 and above, depending on compatibility settings and identifier type) generally support up to **128 bytes** for many object names; older systems and specialized name types may enforce **30 bytes** or custom limits. Keep names concise, clear, and verify your project's version/compatibility setting.

Example:

~~~sql
-- Unquoted names are normalized by Oracle:
CREATE TABLE lab_note (
    note_id NUMBER PRIMARY KEY
);

-- Both references point to the same table:
SELECT note_id FROM lab_note;
SELECT NOTE_ID FROM LAB_NOTE;
~~~

Conversely, quoted identifiers preserve exact case sensitivity:

~~~sql
CREATE TABLE "LabNote" (
    "NoteId" NUMBER PRIMARY KEY
);

-- With a quoted table, this is the exact valid reference:
SELECT "NoteId" FROM "LabNote";
~~~

Frequent use of quoted names causes friction because every tool, SQL query, and migration must preserve exact casing. Avoid them unless a specific integration requirement mandates them under an agreed convention.

### 7.2. Singular vs. plural table names

A team may choose `CUSTOMER` / `ORDER_ITEM` (singular) or `CUSTOMERS` / `ORDER_ITEMS` (plural). Oracle enforces no rule preferring one over the other. What matters is **consistency within the same schema**.

Example of a project choosing **singular nouns**:

| Object | Suggested name | Rationale |
|---|---|---|
| Customer table | `CUSTOMER` | One row represents one customer |
| Order table | `SALES_ORDER` | Avoids `ORDER` keyword collision; clarifies domain |
| Order line item | `SALES_ORDER_ITEM` | One row represents one item of an order |
| Currency lookup table | `CURRENCY` | Each row is one currency unit |
| Event log table | `ORDER_EVENT` | One row is one event; not confused with current state |

There is no need to prefix every table name if the schema already cleanly separates domains. Conversely, in a shared schema spanning multiple domains, prefixes such as `SALES_` or `HR_` can help group objects. Document that choice explicitly in the project's convention.

### 7.3. Column naming conventions

| Role | Suggested name | Interpretation |
|---|---|---|
| Surrogate primary key | `CUSTOMER_ID`, `ORDER_ID` | Stable object identifier |
| Foreign key | `CUSTOMER_ID` in the order table | Name indicates the referenced entity |
| Business key | `CUSTOMER_CODE`, `ORDER_NUMBER` | Business identifier, distinct from surrogate key |
| Quantity | `QUANTITY`, `ITEM_COUNT` | Comment clearly on unit of measure when needed |
| Monetary amount | `UNIT_PRICE`, `TOTAL_AMOUNT` | Pair with currency unit or `CURRENCY_CODE` |
| Status | `ORDER_STATUS`, `PAYMENT_STATUS` | Document valid values and state machine |
| Creation timestamp | `CREATED_AT`, `ORDERED_AT` | Specify timezone, event moment, and source |
| Effective dates | `EFFECTIVE_FROM`, `EFFECTIVE_TO` | Define inclusive/exclusive range bounds |
| Boolean flag | `IS_ACTIVE` or `ACTIVE_FLAG` | Pick one convention and document allowed values |

Names like `CREATED_AT` or `PAID_AT` signal full timestamps; `CREATED_DATE` suggests date-only semantics. In Oracle, the `DATE` data type actually stores both date and time down to seconds; thus **column names and comments must clarify semantics**, rather than guessing from the word `DATE` in the type.

Avoid ambiguous column names:

| Ambiguous name | Clearer name | Benefit |
|---|---|---|
| `ID` | `ORDER_ID` | Immediately recognizable in SQL joins and reports |
| `CODE` | `CURRENCY_CODE` | Clarifies which entity the code belongs to |
| `DATE` | `ORDERED_AT` | Specifies the exact event timestamp |
| `VALUE` | `TOTAL_AMOUNT` | Clarifies what the numeric value represents |
| `STATUS` | `PAYMENT_STATUS` | Avoids mixing up multiple status dimensions |
| `TYPE` | `CUSTOMER_TYPE` | Identifies which entity is being typed |

Depending on team conventions, primary keys may simply be named `ID` to avoid repetition in ORMs, provided all developers follow the convention and SQL joins always use clear column aliases. This lesson uses `<ENTITY>_ID` for clarity in direct SQL.

### 7.4. Naming constraints, indexes, and sequences

Oracle auto-generates constraint names like `SYS_C...` if unnamed. Such names are hard to recognize in error messages or DDL reviews. A common convention:

| Type | Suggested prefix | Example |
|---|---|---|
| Primary key | `PK_` | `PK_LAB_ORDER` |
| Foreign key | `FK_` | `FK_LAB_ORDER_CUSTOMER` |
| Unique constraint | `UQ_` | `UQ_LAB_CUSTOMER_CODE` |
| Check constraint | `CK_` | `CK_LAB_ORDER_STATUS` |
| Regular index | `IX_` | `IX_LAB_ORDER_ORDERED_AT` |
| Dedicated sequence | `SEQ_` | `SEQ_LAB_ORDER` |
| View | `V_` | `V_ORDER_SUMMARY` |

These are team-chosen conventions, **not mandatory Oracle rules**. Account for identifier length limits and avoid name collisions within the same Oracle namespace. An index auto-created by Oracle to enforce a unique or primary key may share a constraint-related name; do not assume every index requires an independent name.

Example of a query-supporting index:

~~~sql
CREATE INDEX ix_lab_order_customer_status
ON lab_order (customer_id, order_status);
~~~

The index name states the entity and leading columns, yet **cannot replace explaining why the index exists**. For major tuning decisions, document the rationale in migrations, tuning notes, or design records.

## 8. What should a good comment contain?

A useful comment answers the question **the reader actually has**, rather than repeating the column name.

| Aspect | Uninformative comment | More useful comment |
|---|---|---|
| Units | "Order amount" | "Total amount in CURRENCY_CODE currency; NUMBER(15,2)" |
| Status | "Order status" | "NEW = newly created; PAID = paid; CANCELLED = cancelled" |
| Timestamp | "Created date" | "Timestamp when Oracle created the record, via SYSTIMESTAMP" |
| Relationship | "Customer ID" | "Foreign key to LAB_CUSTOMER.CUSTOMER_ID" |
| Computed data | "Final value" | "Total before/after discount, including/excluding tax" |
| Null semantics | "End date" | "NULL while record is active; when set, exclusive end timestamp" |
| Scope | "Payments table" | "One row per payment transaction attempt; multiple rows possible per order" |

Notable categories of information:

1. **Business definition:** what does one row or one value actually represent?
2. **Grain and cardinality:** how many orders can a customer have; does a row represent an event or a snapshot?
3. **Domain/enum:** valid status set, code interpretations, default values.
4. **Unit/currency/timezone:** measurement units, rounding rules, timezone reference.
5. **Null semantics:** does `NULL` mean "unknown," "not applicable," or "event has not occurred yet"?
6. **Source of truth:** which system originates the data, which process updates it, which fields are replicas.
7. **Privacy and retention:** whether data is sensitive and any retention/deletion policy; describe classification generally without ever putting real data or secrets inside comments.

For example, in an order system, if `TOTAL_AMOUNT` includes tax, the comment must state that explicitly. Never assume "total amount" defaults to pre-tax or post-tax. Conflicting assumptions silently skew reports even when SQL never raises an error.

### What should comments never contain?

- Passwords, API keys, tokens, real customer data, or operational secrets.
- Multi-page essays unreadable in catalog tools.
- Unenforced promises such as "always unique" when no matching constraint or control exists.
- Facts true only in a test environment without stating scope.
- Generic filler such as "ID column," "Data table," or "Used by system."

## 9. How constraint names and comments work together

Documenting relationships between tables requires both **structural metadata** and **semantic meaning**. For example, `FK_LAB_ORDER_CUSTOMER` proves `LAB_ORDER.CUSTOMER_ID` references the customer table; a comment can clarify that this is the **ordering** customer rather than the **billing** customer if those two roles can differ.

Reading constraints on a table:

~~~sql
SELECT
    c.constraint_name,
    c.constraint_type,
    c.table_name,
    cc.column_name,
    cc.position,
    c.status,
    c.validated
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.table_name = 'LAB_ORDER'
ORDER BY c.constraint_name, cc.position;
~~~

Common `CONSTRAINT_TYPE` codes:

| Code | Meaning |
|---|---|
| `P` | Primary key |
| `R` | Foreign key (referential integrity) |
| `U` | Unique |
| `C` | Check constraint, including NOT NULL constraints represented in the catalog |

`STATUS` and `VALIDATED` show whether a constraint is enabled and verified against existing data. A constraint present in metadata yet disabled or unvalidated does not provide the same data integrity guarantee as an enabled, validated constraint.

Foreign key reference details also live in `R_OWNER` and `R_CONSTRAINT_NAME` in `USER_CONSTRAINTS`; to build an accurate ERD, join to the parent constraint and match column positions for composite keys. Never conclude a database-enforced foreign key exists merely because two columns share the name `CUSTOMER_ID`.

## 10. Generating a data dictionary from metadata

A data dictionary document usually has two levels:

**Table level:** schema, PDB, table name, grain, business description, data source, business owner, retention policy, key relationships.

**Column level:** column name, data type, nullability, default, PK/FK, description, value domain, units, data source, and **synthetic** format examples if helpful.

Oracle supplies abundant technical details directly via its data dictionary, while business metadata such as owners, retention policies, or glossaries are typically maintained in a dedicated catalog/repository. Combine both rather than cramming everything into a single SQL comment.

Example query to find tables or columns still missing comments:

~~~sql
-- Tables missing descriptions
SELECT table_name
FROM user_tab_comments
WHERE table_type = 'TABLE'
  AND comments IS NULL
ORDER BY table_name;

-- Columns missing descriptions in the two example tables
SELECT c.table_name, c.column_name
FROM user_tab_columns c
LEFT JOIN user_col_comments cc
  ON cc.table_name = c.table_name
 AND cc.column_name = c.column_name
WHERE c.table_name IN ('LAB_CUSTOMER', 'LAB_ORDER')
  AND cc.comments IS NULL
ORDER BY c.table_name, c.column_id;
~~~

These results only detect **missing comments**; they do not evaluate whether existing comments are accurate. A schema with 100% comment coverage can still hold wrong or outdated descriptions. Documentation quality must be reviewed by people who understand the data and operational workflows.

### Example exporting metadata with comments via SQL*Plus

~~~sql
SET PAGESIZE 1000
SET LINESIZE 200
SET LONG 2000

SELECT c.table_name,
       c.column_id,
       c.column_name,
       c.data_type,
       c.nullable,
       cc.comments
FROM user_tab_columns c
LEFT JOIN user_col_comments cc
  ON cc.table_name = c.table_name
 AND cc.column_name = c.column_name
WHERE c.table_name = 'LAB_ORDER'
ORDER BY c.column_id;
~~~

In SQLcl, SQL Developer, or catalog tools, similar queries can export CSV, generate Markdown/HTML, or feed documentation portals. Those `SET` commands are SQL*Plus/SQLcl client commands, not standard SQL to submit via `PreparedStatement`.

**Documentation generation principle:** pick one source of truth for technical metadata (the database deployed from migrations), and record **PDB, schema, release version, and extraction timestamp** on the generated doc. Never pull staging metadata and publish it as production structure when the two environments run different versions.

## 11. Managing comments and naming conventions in migrations

A sound schema-change workflow updates DDL and comments **within the same reviewed change**.

Example repository structure:

~~~text
database/
├── migrations/
│   ├── V001__create_customer_and_order.sql
│   ├── V002__add_table_and_column_comments.sql
│   └── V003__add_order_payment_reference.sql
├── conventions/
│   └── naming-and-documentation.md
└── docs/
    ├── data-dictionary.md
    ├── erd.md
    └── business-glossary.md
~~~

These filenames follow a Flyway-style migration convention; specific tools may use different naming patterns. When a migration changes `TOTAL_AMOUNT` from tax-exclusive to tax-inclusive, the team should:

1. Identify the business change and impact on applications/reports.
2. Update DDL, constraints, or data if actually required.
3. Update `COMMENT ON COLUMN` to describe the **new semantics**.
4. Update related data dictionary, glossary, and ERD artifacts.
5. Review impact on JDBC mappings, SQL, APIs, and existing rows.
6. Deploy the migration in order and record the applied version.

Updating a comment alone **does not transform existing data**. If a business rule changes, plan an appropriate data migration. Conversely, fixing a typo in a comment does not require rebuilding the table.

### Example migration updating a column description

~~~sql
-- V003__clarify_total_amount.sql
COMMENT ON COLUMN lab_order.total_amount IS
  'Total customer payable amount, tax-inclusive and post-discount; currency in CURRENCY_CODE.';
~~~

This comment is only accurate once **calculation code, stored data, and business logic actually follow that definition**. If the system still stores pre-tax amounts, updating the comment this way corrupts the data dictionary; comments cannot enforce calculation formulas.

### Naming conventions should not change arbitrarily

Renaming tables or columns after applications use them in SQL, JPA, or PL/SQL breaks queries, views, procedures, and migrations. Therefore:

- Establish conventions before creating the first tables.
- Rename only when the benefit clearly outweighs cost and after auditing all dependents.
- For legacy schemas, keep existing names and use comments/glossaries to clarify meaning instead of mass-renaming.
- When renaming is unavoidable, plan backward-compatible phased rollouts rather than editing only the original DDL file.

## 12. Distinguishing Oracle metadata from extended business documentation

Not every piece of information belongs inside `COMMENT ON`.

| Information type | Recommended storage | Example |
|---|---|---|
| Concise table/column description | `COMMENT ON TABLE/COLUMN` | "Each row represents one order" |
| Data types, nullability | Data dictionary | `NUMBER(15,2) NOT NULL` |
| PK/FK/UQ/CK | Constraint metadata | `FK_LAB_ORDER_CUSTOMER` |
| Enum values and meanings | Comments + glossary/lookup table | `NEW`, `PAID`, `CANCELLED` |
| Data lineage flows | Data catalog / lineage docs | Data originates from the sales service |
| Update SLA | Business/operational docs | Synced every 15 minutes |
| Data owner | Catalog/governance process | Team responsible for data definition |
| Sensitivity classification | Catalog/security policy | Personal data, public data |
| Change history | Git + migration history | Why `PAYMENT_REFERENCE` was added |

In Java applications, JPA annotations such as `@Table(name = "LAB_ORDER")` and `@Column(name = "ORDER_STATUS")` describe application-side mappings, not database comments. Other consumers running direct SQL still rely on clear metadata inside Oracle itself.

## 13. Common mistakes when documenting tables and columns

| Symptom | Common cause | Fix |
|---|---|---|
| Querying `USER_TAB_COMMENTS` misses the table | Logged in as another user or PDB | Check `SESSION_USER`, `CON_NAME`; use `ALL_TAB_COMMENTS` when needed |
| Table exists in catalog yet `COMMENTS` is `NULL` | Comment was never added or was cleared | Add `COMMENT ON TABLE` via migration |
| Comment says "unique" yet duplicate rows exist | Only documented without an active unique constraint | Create the appropriate constraint after cleaning data |
| `AMOUNT` column has values without known unit | Ambiguous name, missing currency/unit | Add `CURRENCY_CODE`/unit and clear description |
| SQL fails due to case-sensitive identifiers | Table/column created with double quotes and mixed/lowercase | Use exact quoted identifiers or standardize conventions |
| Column renamed and application breaks | SQL/JPA/views/procedures depended on old name | Plan a migration and update all consumers |
| `ROLLBACK` does not revert a comment | `COMMENT ON` is DDL with implicit commit | Manage corrections via a subsequent migration |
| Data dictionary export misses tables in other schemas | Account lacks catalog visibility privileges | Use appropriate views and least-privilege access |
| Every table has comments, yet descriptions are stale | Business migrations skipped documentation updates | Review comments and glossary alongside schema changes |
| Generator produces wrong DDL from a single simple query | Omitted full types, length semantics, defaults, identity, constraints | Use `DBMS_METADATA` or proper DDL tooling |

## 14. Hands-on exercises

### Exercise 1 — Reading an undocumented schema

Suppose you inherit these columns:

~~~text
ORDER_ID        NUMBER
CUSTOMER_ID     NUMBER
STATUS          VARCHAR2(20)
AMOUNT          NUMBER(15,2)
DATE_CREATED    DATE
~~~

Propose clearer names for `STATUS`, `AMOUNT`, and `DATE_CREATED`. Write a one-sentence comment for each column clarifying **status type**, **currency**, and **timezone/event moment**. If business context is unknown, list the questions you would ask the domain owner before finalizing definitions.

**Hint:** `ORDER_STATUS`, `TOTAL_AMOUNT`, and `CREATED_AT` are strong candidates; final names depend on actual data semantics.

### Exercise 2 — Adding comments and querying metadata back

In the lab schema, run:

~~~sql
COMMENT ON TABLE lab_order IS
  'Each row represents one customer order.';

COMMENT ON COLUMN lab_order.order_status IS
  'NEW = newly created; PAID = paid; CANCELLED = cancelled.';

SELECT table_name, comments
FROM user_tab_comments
WHERE table_name = 'LAB_ORDER';

SELECT column_name, comments
FROM user_col_comments
WHERE table_name = 'LAB_ORDER'
  AND column_name = 'ORDER_STATUS';
~~~

**Expected result:** the written comment text appears in the `COMMENTS` column for the exact target object.

### Exercise 3 — Checking key naming consistency

`LAB_ORDER` contains `CUSTOMER_ID`. Use `USER_CONSTRAINTS` and `USER_CONS_COLUMNS` to verify whether a foreign key referencing customer actually exists. Explain why merely having a column named `CUSTOMER_ID` is not enough to assert the database enforces that relationship.

**Answer guidance:** names imply semantics; an enabled foreign key constraint provides database-level enforcement. Comments describe roles without replacing constraints.

### Exercise 4 — Currency ambiguity

Suppose `TOTAL_AMOUNT = 1000` and `CURRENCY_CODE = 'VND'`, yet an external application interprets `1000` as USD. Can this bug occur even though the `NUMBER` type and constraints are valid?

**Answer:** Yes. This is a semantic/unit mismatch at a system boundary. The data dictionary and API contract must explicitly specify units, currency codes, and conversion rules.

### Exercise 5 — Updating a schema with comments

The application adds column `PAID_AT TIMESTAMP WITH TIME ZONE`. Propose the DDL, a comment explaining `NULL` semantics, and how to include the change in a versioned migration.

Example:

~~~sql
ALTER TABLE lab_order
  ADD paid_at TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN lab_order.paid_at IS
  'Timestamp of successful payment; NULL if payment has not been recorded yet.';
~~~

If business rules actually allow reversing payments or multiple partial payments, revisit the model: a single `PAID_AT` column cannot represent full payment history and may require a separate payment events table. Comments clarify model boundaries without solving modeling limits.

### Exercise 6 — Reviewing a poor comment

Old comment:

~~~sql
COMMENT ON COLUMN lab_order.order_status IS
  'Status';
~~~

Rewrite it to clarify all values and the distinction between "newly created," "paid," and "cancelled." Next, verify whether the current `CHECK` constraint matches that list of codes. If Java enum code also includes `REFUNDED` while the database does not permit it yet, log the mismatch to design the schema change before updating the comment.

## 15. Checklist map when adding a new table

~~~text
Business requirements
       |
       v
Define data semantics
  - What is one row? Who owns the data?
  - What are keys and relationships?
  - What do units, statuses, timestamps, and NULL mean?
       |
       v
Name consistently
  TABLE / COLUMN / PK / FK / UQ / CK / INDEX
       |
       v
Write DDL
  DATA TYPE + NULLABILITY + CONSTRAINT + DEFAULT
       |
       v
Write COMMENT ON TABLE / COMMENT ON COLUMN
  Explain semantics not expressed by names or DDL
       |
       v
Include in migration and review with application changes
       |
       v
Deploy to the right PDB/schema
       |
       v
Query USER_TAB_COMMENTS / USER_COL_COMMENTS
and combine with catalog to export data dictionary
       |
       v
Maintain descriptions as business rules and schema evolve
~~~

An understandable schema begins with **clear object names**, followed by **accurate data types and constraints**, and completed with **business-meaningful comments**. Oracle lets you store comments directly in table/column metadata and provides `USER_*`, `ALL_*`, and `DBA_*` views to extract them. Put comments in versioned migrations, keep them aligned with your glossary when business rules evolve, and enforce one consistent naming convention across tables, columns, keys, and indexes: documentation can then be generated straight from the database while staying accurate for every reader.

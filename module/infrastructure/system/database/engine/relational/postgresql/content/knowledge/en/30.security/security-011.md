# SQL Injection, Parameterization, and Dynamic Object Names in PostgreSQL

## 1. How Can an Input String Become a SQL Statement?

Suppose an API lets callers search orders by customer code:

```text
GET /orders?customer_code=O'Reilly
```

If the application builds SQL using string concatenation:

```java
String sql =
    "SELECT order_id, amount FROM app.orders " +
    "WHERE customer_code = '" + userInput + "'";
```

the `'` character in `O'Reilly` breaks the string literal structure. Worse, a value crafted to contain extra SQL syntax can alter the `WHERE` predicate, expressions, queried tables, or executed operations depending on the input path and connection privileges.

**SQL injection** occurs when data controlled by an untrusted party is placed into a **SQL syntactic position** without proper binding. The root flaw is not merely failing to escape quotes; it is mixing **executable code** and **data values**.

```text
Input from user / file / request / database
                       |
                       v
              Build SQL statement
                       |
            +----------+-----------+
            |                      |
     Concatenate raw text     Bind parameter
            |                      |
    Data can become          Data remains a
      SQL syntax               data value
            |                      |
  Injection / wrong query   Fixed SQL, easy to audit
            |
            v
    Can bypass WHERE, expose or modify data
```

However, parameter binding **cannot represent table, column, or schema names or SQL keywords**. If an application needs dynamic object selection, you must use an **allowlist**, proper identifier quoting, and separate authorization checks.

> **Core principle:** use fixed SQL statements and parameter binding for **values**; only construct dynamic SQL when structure genuinely must vary; for **dynamic identifiers**, pick from a trusted allowlist and quote with `format('%I', ...)` or `quote_ident(...)`. Quoting never replaces authorization checks.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Identify SQL injection caused by concatenating input into SQL, even when input originates from the database or configuration.
2. Distinguish between a SQL **value**, an **identifier**, and a **syntax fragment**.
3. Use PostgreSQL `PREPARE`/`EXECUTE` to pass parameters rather than building string literals.
4. Use JDBC `PreparedStatement` with `setString`, `setInt`, `setBigDecimal`, and `setArray`.
5. Write type-safe PostgreSQL PL/pgSQL `EXECUTE ... USING`.
6. Explain why placeholders cannot substitute for table/column names, `ASC`/`DESC` sort directions, or SQL expressions.
7. Use `quote_ident`, `quote_literal`, `quote_nullable`, and `format('%I')`/`format('%L')`.
8. Understand the danger of passing raw input to `format('%s')`.
9. Quote **schema** and **table** separately using `%I.%I`.
10. Implement allowlists for table names, columns, sort directions, and filter types.
11. Prevent logic injection via `OR`, dynamic WHERE concatenation, and optional filters.
12. Handle `NULL` properly in dynamic SQL and with `IS NOT DISTINCT FROM`.
13. Distinguish SQL injection from `LIKE`/`ILIKE` wildcard injection and regex abuse.
14. Use full-text search with `websearch_to_tsquery` without raw syntax concatenation.
15. Design multi-tenant queries whose authorization does not rely on self-reported caller parameters.
16. Understand how `SECURITY DEFINER`, RLS, and `search_path` affect blast radius.
17. Explain why allowing multiple statements or utility DDL from requests is riskier than single read-only queries.
18. Separate safe SQL syntax from sound business authorization.
19. Test quotes, Unicode, `NULL`, unusual identifiers, schema shadowing, and least-privilege roles.
20. Evaluate plan/index costs, logging, and operations once injection is mitigated.

## 3. Threat Model: Where Does Untrusted Input Come From?

HTTP query strings are far from the only source of injection. Sources susceptible to manipulation or unexpected data include:

- Request bodies, URL parameters, headers, or cookies.
- Input forms for names, search keywords, and order descriptions.
- CSV/Excel/import job payloads or external partner integrations.
- Queue messages, webhooks, and log-derived data.
- Text previously stored inside the database from an earlier step.
- User-configured report columns, sort rules, or filter definitions.
- Schema or table names supplied by another service.
- Custom session variables if callers can `SET` them arbitrarily.

### 3.1. First-Order and Second-Order Injection

**First-order:** input is concatenated into SQL immediately within the current request.

**Second-order:** data is initially saved safely, then later read back and concatenated into SQL text inside a migration, report, or background routine.

For example, a customer display name is stored via prepared statement; later, a reporting job concatenates that name into SQL without binding. The fact that data "is already stored in the database" **does not make a string trustworthy**.

### 3.2. Impact Depends on the Database Role's Privileges

An injection flaw can lead to:

- Returning extra rows because `WHERE` predicates were altered.
- Reading another tenant's data.
- Inferring record existence or non-existence via errors or timing differences.
- Invoking unintended SQL functions.
- Modifying or deleting data if permissions and execution paths allow it.
- Accessing sensitive objects via a `SECURITY DEFINER` routine.
- Crafting expensive queries causing latency spikes or denial of service.

Not every malicious input can execute multiple statements or mutate data; that depends on how SQL is submitted, driver/protocol behavior, query type, and role privileges. **Never rely on "single-statement only" as an injection defense.**

### 3.3. Injection Differs from Authorization Flaws

A SQL query with **perfectly bound parameters** can still return out-of-scope data if the application lets a user supply another organization's `tenant_id`. That is an **authorization flaw**, not SQL syntax injection.

## 4. Three Categories Requiring Different Handling

| Category | Examples | Safe Approach |
| --- | --- | --- |
| Data value | Customer code, amount, date, status | Bind parameter: `$1`, JDBC `?`, PL/pgSQL `USING` |
| Identifier | Schema, table, or column name | Allowlist/mapping + `%I` or `quote_ident` |
| SQL fragment | `ASC`, `DESC`, `NULLS LAST`, operator, JOIN shape | Fixed selection in code; never accept raw fragments |
| Unbindable DDL literal | Comments, utility command literals | `%L`/`quote_nullable` when SQL text must be built |
| Search pattern | `LIKE`, regex, FTS input | Bind data **and** enforce pattern semantics/limits |
| Authorization scope | Tenant, principal, role, object rights | Verified context + proper privilege/RLS checks |

### 4.1. A Column Is Not a Value

```sql
SELECT status FROM some_table;
```

reads values from the `status` column.

```sql
SELECT 'status' FROM some_table;
```

returns the literal text `'status'` for every row. They are not equivalent.

### 4.2. Two Types of Quotes

- `'O''Reilly'` is a **string literal** containing a single quote.
- `"Order Details"` is a **quoted identifier** containing a space.
- `"status"` is an identifier, whereas `'status'` is a literal.
- `quote_ident` and `%I` are for identifiers; `quote_literal` and `%L` are for literals.

## 5. Multi-Tenant PostgreSQL Lab

Practice only in a dedicated learning database; never create tables or run example DDL in production.

### 5.1. Create Schema and Table

```sql
CREATE SCHEMA IF NOT EXISTS sqli388;

CREATE TABLE sqli388.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    customer_code text NOT NULL,
    status text NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    description text NOT NULL,
    note text,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL
);

CREATE INDEX orders_tenant_customer_idx
ON sqli388.orders (tenant_id, customer_code);

CREATE INDEX orders_tenant_status_created_idx
ON sqli388.orders (tenant_id, status, created_at DESC);
```

### 5.2. Sample Data

```sql
INSERT INTO sqli388.orders (
    tenant_id, customer_code, status,
    description, note, amount, created_at
)
VALUES
    (10, 'ALICE', 'NEW',
        'PostgreSQL beginner handbook', 'First order',
        150.00, timestamptz '2026-01-02 09:00:00+00'),
    (10, 'O''Reilly', 'PAID',
        'SQL performance workshop', 'Customer''s request',
        330.00, timestamptz '2026-01-03 10:00:00+00'),
    (10, 'A%_B', 'NEW',
        'Search syntax class', NULL,
        35.00, timestamptz '2026-01-04 11:00:00+00'),
    (10, 'VN-ĐỎ', 'PAID',
        'Unicode and collation', 'Paid',
        90.00, timestamptz '2026-01-05 12:00:00+00'),
    (10, 'x'' OR TRUE --', 'NEW',
        'Untrusted input as plain data',
        'Safe when bound', 20.00,
        timestamptz '2026-01-06 13:00:00+00'),
    (20, 'ALICE', 'PAID',
        'Another tenant''s order', 'Private scope',
        999.00, timestamptz '2026-01-07 14:00:00+00'),
    (20, 'O''Reilly', 'CANCELLED',
        'Cancelled order', NULL,
        10.00, timestamptz '2026-01-08 15:00:00+00'),
    (20, 'BOB', 'NEW',
        'Database indexing', 'Private scope',
        80.00, timestamptz '2026-01-09 16:00:00+00');
```

Both tenants share overlapping `customer_code` values. The code `x' OR TRUE --` is **plain text data in the table**, not SQL syntax.

### 5.3. Archive Table for Practicing Dynamic Table Selection

```sql
CREATE TABLE sqli388.orders_archive (
    order_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    customer_code text NOT NULL,
    status text NOT NULL,
    description text NOT NULL,
    note text,
    amount numeric(12,2) NOT NULL,
    created_at timestamptz NOT NULL
);

INSERT INTO sqli388.orders_archive (
    order_id, tenant_id, customer_code,
    status, description, note, amount, created_at
)
VALUES
    (1001, 10, 'ALICE', 'PAID',
        'Old order', NULL, 10.00,
        timestamptz '2025-01-01 00:00:00+00'),
    (1002, 20, 'BOB', 'PAID',
        'Old order', NULL, 20.00,
        timestamptz '2025-01-02 00:00:00+00');

ANALYZE sqli388.orders;
ANALYZE sqli388.orders_archive;
```

### 5.4. Inspecting the Dataset

```sql
SELECT tenant_id, COUNT(*) AS orders_count
FROM sqli388.orders
GROUP BY tenant_id
ORDER BY tenant_id;

SELECT
    order_id, tenant_id, customer_code, amount
FROM sqli388.orders
ORDER BY order_id;
```

In the lab, tenant 10 has **5** orders in `orders` and tenant 20 has **3** orders. Codes containing quotes, Unicode, and `%`/`_` help test edge cases.

## 6. Dangerous Pattern: Concatenating Input into SQL Literals

An application might construct:

```java
String sql =
    "SELECT order_id FROM sqli388.orders " +
    "WHERE customer_code = '" + customerCode + "'";
```

If `customerCode = "O'Reilly"`, the resulting SQL text has malformed quotes.

If the input contains tokens resembling SQL conditions, subsequent text may be interpreted by the SQL parser as **syntax** instead of a customer code.

### 6.1. Do Not Execute Malformed Queries Just to Prove Damage

Inspecting the generated string already demonstrates that the code/data boundary was broken. There is no need to run destructive or privilege-escalating payloads.

### 6.2. Manual Quote Replacement Is Not an Architectural Fix

A hasty patch looks like:

```java
String escaped = customerCode.replace("'", "''");
```

In a trivial string literal case this might format a quoted literal, yet systems still break easily when:

- Code later accepts table or column names.
- Input enters `ORDER BY` or a SQL expression.
- Multiple escaping layers exist: Java → SQL → LIKE/regex.
- Statements are assembled across varying encodings or strings.
- A single code branch forgets to escape.
- Input involves `NULL`, binary/typed values, or complex timestamps.

Never invent a general-purpose "SQL sanitizer". **Bound parameters** must be the default for values.

## 7. Safe SQL with PostgreSQL `PREPARE`

PostgreSQL supports parameter placeholders in prepared statements.

```sql
PREPARE find_orders(integer, text) AS
SELECT
    order_id,
    tenant_id,
    customer_code,
    status,
    amount
FROM sqli388.orders
WHERE tenant_id = $1
  AND customer_code = $2
ORDER BY order_id;

EXECUTE find_orders(10, 'O''Reilly');

DEALLOCATE find_orders;
```

Here:

- `$1` is an `integer`.
- `$2` is a `text`.
- The SQL structure is pre-declared; values cannot alter that structure.
- `EXECUTE find_orders(...)` is SQL syntax for executing a **named prepared statement** in the session.

### 7.1. Why Do Two Single Quotes Still Appear in the SQL Script?

The line `EXECUTE find_orders(10, 'O''Reilly')` is **a SQL statement typed manually**, so literals inside the script must follow SQL syntax. Production applications do not construct parameter strings that way.

In JDBC, the application calls `ps.setString(2, customerCode)` without escaping `O'Reilly`.

### 7.2. Tenant Scope Still Must Be Checked Separately

The query binds both `$1` and `$2`, yet if an API allows callers to change `$1` from 10 to 20 freely, they can still access tenant 20 if the DB role permits it.

**Parameter binding stops injection; it does not authorize tenant IDs.**

### 7.3. Prepared Statement Syntax Is Just One Representation

Under the hood, the extended query protocol and JDBC driver manage preparation and binding differently from explicit SQL `PREPARE`. You do not need to issue manual SQL `PREPARE` statements before every JDBC query.

## 8. JDBC PreparedStatement: The Standard Java Choice

Java 17+ example:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderSearch {
    private final DataSource dataSource;

    public OrderSearch(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void findByCustomer(
        int authenticatedTenantId,
        String customerCode
    ) throws SQLException {

        String sql = """
            SELECT order_id, customer_code, status, amount
            FROM sqli388.orders
            WHERE tenant_id = ?
              AND customer_code = ?
            ORDER BY order_id
            LIMIT 100
            """;

        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {

            ps.setInt(1, authenticatedTenantId);
            ps.setString(2, customerCode);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    System.out.println(
                        rs.getLong("order_id")
                        + " | " + rs.getString("customer_code")
                    );
                }
            }
        }
    }
}
```

### 8.1. Authorization Prerequisite

`authenticatedTenantId` must be derived server-side from verified authentication/authorization state. Never do:

```java
int authenticatedTenantId =
    Integer.parseInt(request.getParameter("tenant_id"));
```

and trust that value as the permitted scope.

### 8.2. `PreparedStatement` Is Not String Concatenation

Wrong:

```java
String sql = "SELECT * FROM sqli388.orders " +
             "WHERE customer_code = '" + userInput + "'";
Statement s = conn.createStatement();
ResultSet rs = s.executeQuery(sql);
```

Better:

```java
String sql = "SELECT * FROM sqli388.orders " +
             "WHERE customer_code = ?";
PreparedStatement ps = conn.prepareStatement(sql);
ps.setString(1, userInput);
```

### 8.3. Java Parameter Indexes Start at 1

`setString(1, ...)` binds the first `?` placeholder; indexing is 1-based, not 0-based.

### 8.4. Close Resources

`try-with-resources` releases statements, result sets, and connections promptly according to your application's connection pool lifecycle.

### 8.5. Never Execute Raw SQL Sent by Clients

Never design endpoints like:

```text
POST /query
{"sql": "SELECT ..."}
```

and run that string under a privileged role. SQL templates must live on the server, never supplied by callers.

## 9. Parameterization Preserves Data Types

Another advantage beyond security is passing values with explicit types.

| Type | PostgreSQL | JDBC |
| --- | --- | --- |
| ID | `bigint` | `setLong(...)` |
| Tenant ID | `integer` | `setInt(...)` |
| Customer code | `text` | `setString(...)` |
| Amount | `numeric` | `setBigDecimal(...)` |
| Boolean flag | `boolean` | `setBoolean(...)` |
| Date/time | `timestamptz` | Driver-supported timestamp/time binding |
| NULL | Matching column/parameter type | `setNull(..., Types.XXX)` or typed binding |

### 9.1. Do Not Convert Money via Strings

```java
String sql = "... WHERE amount >= " + userAmount;
```

risks locale/rounding errors and puts raw text into SQL syntax. Use `BigDecimal` and bind it.

### 9.2. NULL Requires an Appropriate Type

In JDBC:

```java
ps.setNull(2, java.sql.Types.VARCHAR);
```

when a parameter is a nullable string. PostgreSQL needs unambiguous type resolution; sometimes SQL requires an explicit cast like `?::text` to avoid ambiguity.

### 9.3. Parameterized Does Not Mean Unbounded Resource Usage

`LIMIT ?` can still bind a huge number. Validate parameters such as page size, regex complexity, time range, and tag counts to prevent expensive queries.

## 10. Multiple Values in `IN`: Never Concatenate Raw Lists

A common mistake:

```java
String sql =
    "SELECT * FROM sqli388.orders " +
    "WHERE status IN (" + csvStatuses + ")";
```

If `csvStatuses` comes from input, it can introduce raw SQL syntax.

### 10.1. Use ANY With a PostgreSQL Array

```sql
PREPARE find_by_status(integer, text[]) AS
SELECT order_id, status
FROM sqli388.orders
WHERE tenant_id = $1
  AND status = ANY($2)
ORDER BY order_id;

EXECUTE find_by_status(
    10,
    ARRAY['NEW', 'PAID']::text[]
);

DEALLOCATE find_by_status;
```

### 10.2. Java JDBC Array

```java
String sql = """
    SELECT order_id, status
    FROM sqli388.orders
    WHERE tenant_id = ?
      AND status = ANY(?)
    ORDER BY order_id
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, authenticatedTenantId);

    java.sql.Array sqlArray = conn.createArrayOf(
        "text",
        new String[] {"NEW", "PAID"}
    );

    try {
        ps.setArray(2, sqlArray);
        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                System.out.println(rs.getLong(1));
            }
        }
    } finally {
        sqlArray.free();
    }
}
```

The JDBC snippet assumes `conn` is managed externally. Exact API/type details vary by driver, but the principle is **pass arrays as typed data, never concatenate SQL from elements**.

### 10.3. Empty Array vs NULL

- `status = ANY(ARRAY[]::text[])` matches no rows.
- `NULL::text[]` does not share the same semantics.
- "No filter selected" is a distinct application policy and should not be conflated with "no statuses permitted".

### 10.4. Dynamic Placeholders as an Alternative

Applications can also generate an exact count of `?` placeholders matching a validated list length and bind each element individually. When doing so, generate only placeholder tokens from a **validated count**, never concatenating raw items.

## 11. Parameters for Dates, Amount Ranges, and Pagination

Example:

```sql
PREPARE list_orders(
    integer, numeric, numeric, timestamptz, integer
) AS
SELECT
    order_id,
    amount,
    created_at
FROM sqli388.orders
WHERE tenant_id = $1
  AND amount >= $2
  AND amount <= $3
  AND created_at >= $4
ORDER BY created_at DESC, order_id DESC
LIMIT $5;

EXECUTE list_orders(
    10,
    20.00,
    400.00,
    timestamptz '2026-01-01 00:00:00+00',
    20
);

DEALLOCATE list_orders;
```

### 11.1. Binding Does Not Replace Input Validation

- Ensure `min_amount <= max_amount`.
- Ensure amounts match expected currency/unit rules.
- Keep `page_size` within allowed bounds.
- Handle timestamps with consistent timezone semantics.
- Obtain the tenant ID from a trusted context.

### 11.2. Never Interpolate Raw Strings into ORDER BY Even If "Numeric"

Some developers think integers cannot inject SQL and interpolate raw strings directly. An unparsed **string** that merely looks numeric is still raw SQL text. Parse, validate, and bind values.

### 11.3. `ORDER BY` Needs a Deterministic Total Order

Two rows with identical `created_at` timestamps can swap order without a tie-breaker. Adding `order_id DESC` provides deterministic ordering within a snapshot.

## 12. Logic Flaws in `AND`/`OR` Also Leak Data

Not every query-based data leak is SQL injection.

Wrong:

```sql
SELECT order_id, tenant_id, customer_code
FROM sqli388.orders
WHERE tenant_id = 10
  AND status = 'PAID'
   OR customer_code = 'ALICE';
```

Because `AND` binds tighter than `OR`, this evaluates as:

```text
(tenant_id = 10 AND status = 'PAID')
OR customer_code = 'ALICE'
```

It can return tenant 20's `ALICE` order.

Correct:

```sql
SELECT order_id, tenant_id, customer_code
FROM sqli388.orders
WHERE tenant_id = 10
  AND (
      status = 'PAID'
      OR customer_code = 'ALICE'
  );
```

### 12.1. Parameterization Does Not Fix Missing Parentheses

Even with `tenant_id = $1` and `customer_code = $2`, an ungrouped `OR` breaks tenant scoping.

### 12.2. Mandatory Predicates Must Wrap Every Branch

A dynamic query builder should maintain the structure:

```sql
WHERE tenant_id = $1
  AND (
      status = $2
      OR customer_code = $3
  )
```

Never let an optional filter append `OR ...` at the top level and bypass authorization.

### 12.3. Do Not Apply Top-N Before Access Filters

Applying `LIMIT 20` inside an unfiltered CTE before filtering by tenant in the outer query can return fewer than 20 authorized rows or skew results. That is a business/search logic defect rather than injection, yet it still impacts correctness and security.

## 13. When Is Dynamic SQL Actually Needed?

Fixed queries:

```sql
SELECT order_id
FROM sqli388.orders
WHERE tenant_id = $1
  AND customer_code = $2;
```

do not need dynamic SQL.

Legitimate scenarios for dynamic SQL include:

- Choosing between live and archive tables via a controlled enum.
- Internal tooling generating DDL inside authorized schemas.
- Dashboards selecting from a strict allowlist of **columns**.
- Reports whose grouping/sorting fields vary by preset options.
- Migrations targeting partitions verified against system metadata.

### 13.1. Do Not Use Dynamic SQL Just to Look "Flexible"

It increases:

- Review and testing effort.
- Risk of omitting a mandatory filter.
- Planning overhead and plan variance.
- SQL injection and object-authorization exposure.
- Logging and observability complexity.

### 13.2. Dynamic SQL Can Be Made Safe

Apply:

1. Fixed SQL templates.
2. Allowlisted identifiers quoted with `%I`.
3. Bound data values via parameters / `USING`.
4. Least-privilege DB roles.
5. Input validation and business authorization.

## 14. PL/pgSQL `EXECUTE ... USING`

In PostgreSQL PL/pgSQL:

```sql
EXECUTE command_string
    [INTO [STRICT] target]
    [USING expression [, ...]];
```

Safe example inside a function body:

```sql
EXECUTE
    'SELECT COUNT(*)
     FROM sqli388.orders
     WHERE tenant_id = $1
       AND customer_code = $2'
INTO v_count
USING p_tenant_id, p_customer_code;
```

### 14.1. Two Distinct Meanings of `EXECUTE`

- SQL `EXECUTE prepared_name(arguments)`: runs a previously `PREPARE`d statement.
- PL/pgSQL `EXECUTE command_string USING ...`: executes SQL **constructed as text**.

Do not copy `INTO local_variable USING ...` outside PL/pgSQL expecting plain SQL prepared statement execution.

### 14.2. Parameters Stay Data Values

`$1` and `$2` inside the dynamic command stand for data values in permitted positions. Single quotes inside `p_customer_code` never turn into SQL syntax.

### 14.3. NULL Values Do Not Nullify the Command String

`USING NULL::text` is a valid parameter value—unlike concatenating `quote_literal(NULL)`, which turns the entire command string into SQL `NULL`.

### 14.4. Applicability

Data parameters in PL/pgSQL dynamic SQL are supported for **optimizable SQL commands** such as `SELECT`, `INSERT`, `UPDATE`, `DELETE`, and `MERGE` (in supported versions).

Certain **utility statements** do not support parameter placeholders at value slots; in those cases, build SQL text with `format` and proper quoting.

## 15. Running a Complete Function With USING

```sql
CREATE OR REPLACE FUNCTION sqli388.count_by_customer(
    p_tenant_id integer,
    p_customer_code text
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, sqli388, pg_temp
AS $fn$
DECLARE
    v_count bigint;
BEGIN
    IF p_tenant_id IS NULL OR p_tenant_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant id'
            USING ERRCODE = '22023';
    END IF;

    EXECUTE
        'SELECT COUNT(*)
         FROM sqli388.orders
         WHERE tenant_id = $1
           AND customer_code = $2'
    INTO v_count
    USING p_tenant_id, p_customer_code;

    RETURN v_count;
END;
$fn$;
```

Test it:

```sql
SELECT sqli388.count_by_customer(10, 'O''Reilly');
SELECT sqli388.count_by_customer(10, 'A%_B');
SELECT sqli388.count_by_customer(10, 'x'' OR TRUE --');
SELECT sqli388.count_by_customer(20, 'O''Reilly');
```

All inputs are evaluated strictly as **exact text value comparisons**. No `OR TRUE` fragment ever becomes SQL logic.

### 15.1. Why SECURITY INVOKER?

The function needs no privileges beyond the caller's own rights. The caller must hold standard PostgreSQL table access privileges.

### 15.2. Why Does It Still Accept a Tenant Parameter?

This is a **lab demonstrating parameter binding**. In a real public endpoint, `p_tenant_id` must come from or be verified against trusted auth state or enforced via RLS, not arbitrarily chosen by callers.

### 15.3. When Static SQL Suffices

We used `EXECUTE` here to demonstrate the technique. In production, when table and column names never change, simply write:

```sql
SELECT COUNT(*)
INTO v_count
FROM sqli388.orders
WHERE tenant_id = p_tenant_id
  AND customer_code = p_customer_code;
```

which is simpler and lets PL/pgSQL cache plans appropriately.

## 16. Table Names Cannot Be Replaced With `$1`

An invalid attempt:

```sql
EXECUTE
    'SELECT COUNT(*) FROM $1'
INTO v_count
USING p_table_name;
```

`$1` denotes a data value in expression slots, **not a table identifier** inside `FROM`.

Similarly, in JDBC:

```java
PreparedStatement ps =
    conn.prepareStatement("SELECT * FROM ?");
ps.setString(1, tableName);
```

does not turn `?` into a table name; this is not valid identifier binding.

### 16.1. Why Can't Object Names Be Bound as Data?

The SQL parser must resolve query structure, relations, columns, and operators to construct a plan. Identifiers belong to SQL grammar; parameter binding applies to **values** within that fixed structure.

### 16.2. Column Names Cannot Be Bound Either

```sql
SELECT $1 FROM sqli388.orders;
```

with `$1='status'`, if typed cleanly, returns the constant text `'status'` for every row rather than reading the `status` column.

### 16.3. Dynamic Objects Must Use Quoted Identifiers

Use `format('%I', ...)`, `quote_ident(...)`, or an equivalent mapping **paired with an allowlist**.

## 17. `quote_ident`: Syntactically Valid Identifier Representation

```sql
SELECT
    quote_ident('orders') AS simple_name,
    quote_ident('Order Details') AS spaced_name,
    quote_ident('select') AS keyword_name,
    quote_ident('MixedCase') AS mixed_case_name,
    quote_ident('has"quote') AS quoted_quote;
```

`quote_ident(text)` formats text properly for embedding **an identifier** into SQL.

### 17.1. Results Do Not Always Contain Double Quotes

`quote_ident('orders')` returns `orders` because lowercase unquoted identifiers are already valid.

`quote_ident('MixedCase')` adds double quotes to preserve case because PostgreSQL folds unquoted identifiers to lowercase.

### 17.2. Identifiers Containing Double Quotes

`quote_ident` escapes embedded double quotes by doubling them so data characters cannot terminate the identifier prematurely.

### 17.3. `quote_ident` Does Not Check Existence

Quoting `'missing_table'` does not verify or create the table. Dynamic execution can still raise `relation does not exist`.

### 17.4. `quote_ident` Does Not Check Privileges

A syntactically valid identifier may point to a table or column the user is **not authorized** to view. Quoting ensures syntax safety, not authorization.

## 18. `quote_literal` and `quote_nullable`

When you **must** construct SQL literal text, PostgreSQL provides:

```sql
SELECT
    quote_literal('O''Reilly') AS safe_literal,
    quote_literal(42) AS number_literal,
    quote_nullable(NULL::text) AS null_token,
    quote_nullable('O''Reilly') AS safe_nullable_literal;
```

### 18.1. `quote_literal`

Produces a properly formatted SQL literal string—for example, `O'Reilly` with escaped single quotes per PostgreSQL rules.

However, `quote_literal` is **STRICT**: when given SQL `NULL`, it returns SQL `NULL`.

### 18.2. `quote_nullable`

Formats non-null values as literals; for SQL `NULL`, it returns **the text `'NULL'`** (the SQL keyword token, not `'NULL'` in quotes).

### 18.3. Concatenation Trap With NULL Data

```sql
SELECT
    'SELECT ' || quote_literal(NULL::text)
        AS whole_command;
```

`whole_command` becomes SQL `NULL`. In PL/pgSQL, `EXECUTE` with a `NULL` command string raises an error.

### 18.4. `quote_nullable` Preserves the Command String

```sql
SELECT
    'SELECT ' || quote_nullable(NULL::text)
        AS whole_command;
```

Now the output is the SQL text `SELECT NULL`.

### 18.5. NULL in WHERE Remains a Separate Issue

`WHERE note = NULL` evaluates to `UNKNOWN`, matching no `NULL` rows. `quote_nullable` only formats SQL text; **it does not fix NULL comparison logic**.

## 19. `format('%I')`, `format('%L')`, and `format('%s')`

These are the three specifiers commonly seen when formatting SQL text:

| Specifier | Meaning | Auto-Quotes for SQL? |
| --- | --- | --- |
| `%I` | SQL identifier | Yes, per identifier rules |
| `%L` | SQL literal, including NULL | Yes, per literal rules |
| `%s` | Plain string interpolation | **No** |
| `%%` | Literal `%` in format string | Unrelated to SQL escaping |

### 19.1. Quoting Identifiers

```sql
SELECT format(
    'SELECT %I FROM sqli388.orders',
    'customer_code'
);
```

Generates SQL text referencing a **column**.

### 19.2. Quoting Literals

```sql
SELECT format(
    'SELECT * FROM sqli388.orders
     WHERE customer_code = %L',
    'O''Reilly'
);
```

Generates SQL text containing a properly quoted literal value.

### 19.3. %L Handles NULL

```sql
SELECT format(
    'SELECT %L',
    NULL::text
);
```

Generates text containing the SQL token `NULL`. Meanwhile, `%I` has no concept of a "NULL identifier": passing `NULL` raises an error.

### 19.4. %s Is Not an Injection Defense

Wrong when raw user input enters a syntactic slot:

```sql
format(
    'SELECT * FROM sqli388.orders ORDER BY %s',
    p_sort_expression
)
```

`%s` performs no quoting like `%I` or `%L`, allowing raw text to inject arbitrary SQL expressions or fragments.

Use `%s` strictly for **fixed fragments selected in code from an allowlist**, such as `'ASC'` or `'DESC'`.

### 19.5. Positional Format Arguments

```sql
SELECT format(
    'SELECT %1$I FROM %2$I.%3$I ORDER BY %1$I',
    'order_id',
    'sqli388',
    'orders'
);
```

`%1$I` reuses the first argument in two positions.

## 20. A `schema.table` Reference Consists of Two Identifiers

Wrong:

```sql
SELECT format(
    'SELECT COUNT(*) FROM %I',
    'sqli388.orders'
);
```

This produces **a single** identifier containing a dot (`"sqli388.orders"`), not the `orders` relation inside schema `sqli388`.

Correct:

```sql
SELECT format(
    'SELECT COUNT(*) FROM %I.%I',
    'sqli388',
    'orders'
);
```

### 20.1. Why Separate Them?

The dot between schema and relation is a **syntax separator**. Each component is an independent identifier with its own quoting rules.

### 20.2. Columns Can Also Be Alias/Table Qualified

In SQL:

```sql
SELECT o.customer_code
FROM sqli388.orders AS o;
```

`o.customer_code` is a column qualified by alias `o`, not a single identifier with a dot in its name. If generating dynamic aliases or column qualifiers, quote each component separately.

### 20.3. Dots Inside Identifiers Are Legal Syntax With Different Meaning

A table can legitimately be named `"a.b"` inside a schema. Never naively split or strip dots using string replacement and assume the result represents a qualified path.

## 21. Allowlists: Mandatory Defense for Dynamic Object Names

Suppose a reporting API offers two choices:

- `current` maps to `sqli388.orders`.
- `archive` maps to `sqli388.orders_archive`.

If clients could pass arbitrary `schema_name`/`table_name` values, `%I.%I` would still allow querying any **valid yet unauthorized** table accessible to a privileged routine.

### 21.1. Mapping Business Options to Table Names

In PL/pgSQL:

```sql
IF p_source IS NULL
   OR p_source NOT IN ('current', 'archive')
THEN
    RAISE EXCEPTION 'Unsupported source'
        USING ERRCODE = '22023';
END IF;

v_table_name := CASE p_source
    WHEN 'current' THEN 'orders'
    WHEN 'archive' THEN 'orders_archive'
END;
```

### 21.2. Then Quote Each Identifier Individually

```sql
EXECUTE format(
    'SELECT COUNT(*)
     FROM %I.%I
     WHERE tenant_id = $1',
    'sqli388',
    v_table_name
)
INTO v_count
USING p_tenant_id;
```

### 21.3. Two Defensive Layers

- The allowlist determines **which objects are permitted**.
- `%I` ensures **object names are formatted safely in SQL syntax**.

Missing either layer breaks defense-in-depth: an allowlist without quoting risks errors on special identifiers; quoting without an allowlist risks privilege bypass under broad owners.

## 22. A Syntactically Safe Dynamic Table-Selection Function

```sql
CREATE OR REPLACE FUNCTION sqli388.count_from_source(
    p_source text,
    p_tenant_id integer
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, sqli388, pg_temp
AS $fn$
DECLARE
    v_table text;
    v_count bigint;
BEGIN
    IF p_source IS NULL
       OR p_source NOT IN ('current', 'archive')
    THEN
        RAISE EXCEPTION 'Unsupported source'
            USING ERRCODE = '22023';
    END IF;

    IF p_tenant_id IS NULL OR p_tenant_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant id'
            USING ERRCODE = '22023';
    END IF;

    v_table := CASE p_source
        WHEN 'current' THEN 'orders'
        WHEN 'archive' THEN 'orders_archive'
    END;

    EXECUTE format(
        'SELECT COUNT(*)
         FROM %I.%I
         WHERE tenant_id = $1',
        'sqli388',
        v_table
    )
    INTO v_count
    USING p_tenant_id;

    RETURN v_count;
END;
$fn$;
```

Test it:

```sql
SELECT sqli388.count_from_source('current', 10);
SELECT sqli388.count_from_source('archive', 10);
SELECT sqli388.count_from_source('current', 20);
```

Expected results are `5`, `1`, and `3`.

### 22.1. Testing an Unauthorized Table Name

```sql
-- Expect error Unsupported source:
SELECT sqli388.count_from_source('pg_catalog.pg_authid', 10);
```

The function never passes that input as an object name; it rejects it immediately at the allowlist check.

### 22.2. Why Is This Still Not a Public Multi-Tenant API?

Because `p_tenant_id` is still passed by the caller. Under `SECURITY INVOKER`, DB privileges and RLS may restrict rows; however, if the role has broad SELECT rights and the API fails to validate tenant ownership, a caller could still count another tenant's rows.

## 23. Dynamic Column Selection Using Allowlist and `%I`

Suppose a report allows filtering strictly by:

- `status`.
- `customer_code`.

Example:

```sql
CREATE OR REPLACE FUNCTION sqli388.count_by_field(
    p_tenant_id integer,
    p_field text,
    p_value text
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, sqli388, pg_temp
AS $fn$
DECLARE
    v_count bigint;
BEGIN
    IF p_tenant_id IS NULL OR p_tenant_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant id'
            USING ERRCODE = '22023';
    END IF;

    IF p_field IS NULL
       OR p_field NOT IN ('status', 'customer_code')
    THEN
        RAISE EXCEPTION 'Unsupported field'
            USING ERRCODE = '22023';
    END IF;

    EXECUTE format(
        'SELECT COUNT(*)
         FROM sqli388.orders
         WHERE tenant_id = $1
           AND %I = $2',
        p_field
    )
    INTO v_count
    USING p_tenant_id, p_value;

    RETURN v_count;
END;
$fn$;
```

```sql
SELECT sqli388.count_by_field(10, 'status', 'NEW');

SELECT sqli388.count_by_field(
    10, 'customer_code', 'O''Reilly'
);
```

### 23.1. Why Isn't p_field Passed via USING?

`p_field` is a **column identifier**, whereas `p_value` is a data value. The two require distinct handling.

### 23.2. Why Is an Allowlist Still Essential?

Without an allowlist, callers could filter on unintended sensitive columns or trigger type/syntax errors. `%I` only guarantees valid identifier quoting.

### 23.3. What If Columns Have Non-Text Types?

In the lab both `status` and `customer_code` are `text`. If you add a numeric `amount` column, do not pass a single `text` parameter hoping operators and implicit casts always behave properly. Split query variants per type or bind properly typed values.

### 23.4. What About NULL Values?

`column = $2` matches nothing when `$2` is SQL `NULL`. Use a dedicated predicate or `IS NOT DISTINCT FROM` when null-safe matching is desired.

## 24. Dynamic ORDER BY: Where Binding Is Commonly Misunderstood

Suppose users can sort by:

- Newest first.
- Price ascending.
- Price descending.

Wrong:

```java
String sql = "SELECT * FROM sqli388.orders " +
             "ORDER BY " + requestSort;
```

If `requestSort` is raw text, the application injects arbitrary user SQL syntax into the query.

### 24.1. Allowlist in Java

```java
String orderBy = switch (requestedSort) {
    case "newest" -> "created_at DESC, order_id DESC";
    case "price_asc" -> "amount ASC, order_id DESC";
    case "price_desc" -> "amount DESC, order_id DESC";
    default -> throw new IllegalArgumentException(
        "Unsupported sort"
    );
};

String sql = """
    SELECT order_id, customer_code, amount, created_at
    FROM sqli388.orders
    WHERE tenant_id = ?
    ORDER BY
    """ + orderBy + "\nLIMIT ?";
```

Here `orderBy` is **never copied verbatim from the client**; it can only be one of three fixed SQL literal fragments defined in code.

### 24.2. Bind Everything Else

```java
try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, authenticatedTenantId);
    ps.setInt(2, validatedPageSize);
    // ps.executeQuery(), process ResultSet, close...
}
```

### 24.3. Why Can't ORDER BY Simply Use `?`?

Parameters represent **data values**, not SQL column identifiers or `ASC`/`DESC` keywords. Writing `ORDER BY ?` with the string `"amount DESC"` will not sort by amount as intended.

### 24.4. Dynamic Sort Direction in PL/pgSQL

```sql
v_direction := CASE
    WHEN p_descending IS TRUE THEN 'DESC'
    ELSE 'ASC'
END;

EXECUTE format(
    'SELECT COUNT(*)
     FROM (
         SELECT order_id FROM sqli388.orders
         WHERE tenant_id = $1
         ORDER BY %I %s, order_id DESC
         LIMIT $2
     ) AS page',
    v_sort_column,
    v_direction
)
INTO v_count
USING p_tenant_id, p_page_size;
```

This is safe only because `v_sort_column` passes an allowlist and `v_direction` is strictly derived in code as `'ASC'` or `'DESC'`. This snippet only illustrates dynamic sorting; to count **total matched rows**, never count after `LIMIT`.

### 24.5. NULLS FIRST/LAST Are Also Syntax

If users can select NULL placement, map an enum strictly to `'NULLS FIRST'` or `'NULLS LAST'` fixed fragments rather than accepting raw SQL text.

## 25. Dynamic WHERE and Optional Filters

Suppose an optional filter set allows:

- Filtering by status.
- Filtering by min/max amount.
- Filtering by customer.
- Always enforcing tenant scope.

### 25.1. Static Approach When Filter Count Is Small

```sql
WHERE tenant_id = $1
  AND ($2::text IS NULL OR status = $2)
  AND ($3::numeric IS NULL OR amount >= $3)
  AND ($4::numeric IS NULL OR amount <= $4)
```

This has clear semantics when `NULL` means "do not filter". However, it can degrade query plans, particularly with generic prepared plans.

### 25.2. Query Builder With Code-Controlled Clauses

Another option builds conditions strictly from **fixed code-controlled clauses**:

```text
mandatory := "tenant_id = ?"
if status present:
    add "AND status = ?"
if minAmount present:
    add "AND amount >= ?"
if maxAmount present:
    add "AND amount <= ?"
bind values in exactly that order
```

Never append raw field names, operators, or values directly from the request into `WHERE`.

### 25.3. What If Users Choose Operators?

Instead of accepting a raw `operator` string and concatenating it into SQL, map validated options:

- `eq` → `=`.
- `gte` → `>=`.
- `lte` → `<=`.

Also verify which operators are valid for each column's data type and business semantics. An operator allowlist alone is insufficient if callers can target unauthorized columns or break scope.

### 25.4. Wrap OR Branches in Parentheses

Ensure:

```sql
AND (
    customer_code = $2
    OR status = $3
)
```

is never mistakenly assembled as `... AND customer_code = $2 OR status = $3`, which would weaken the tenant condition.

## 26. SQL NULL, `quote_nullable`, and Equality

In SQL, `NULL` means "unknown / missing value". Thus:

```sql
SELECT NULL::text = NULL::text;
```

evaluates to SQL `NULL` (`UNKNOWN`), not `TRUE`.

### 26.1. Finding Rows Where note IS NULL

```sql
SELECT order_id
FROM sqli388.orders
WHERE tenant_id = 10
  AND note IS NULL;
```

### 26.2. Null-Safe Parameter Comparison

```sql
PREPARE by_note(integer, text) AS
SELECT order_id
FROM sqli388.orders
WHERE tenant_id = $1
  AND note IS NOT DISTINCT FROM $2;

EXECUTE by_note(10, NULL);
DEALLOCATE by_note;
```

`IS NOT DISTINCT FROM` treats two `NULL` sides as equal, returning a definite boolean.

### 26.3. Dynamic PL/pgSQL With NULL

```sql
EXECUTE
    'SELECT COUNT(*)
     FROM sqli388.orders
     WHERE tenant_id = $1
       AND note IS NOT DISTINCT FROM $2'
INTO v_count
USING p_tenant_id, p_note;
```

There is no need for `quote_nullable` when binding via `USING`.

### 26.4. When Generating Literal SQL Text Is Unavoidable

```sql
v_sql := format(
    'SELECT COUNT(*)
     FROM sqli388.orders
     WHERE note IS NOT DISTINCT FROM %L',
    p_note
);
```

`%L` emits the `NULL` token when `p_note` is SQL `NULL`, keeping the SQL string valid. Still, `USING` remains the preferred option for supported queries.

## 27. SQL Injection vs LIKE Wildcard Injection

Suppose a user enters:

```text
A%_B
```

If the query runs:

```sql
WHERE customer_code LIKE $1
```

and binds `'%A%_B%'`, the `%` and `_` characters **inside** the input are still interpreted by `LIKE` as wildcards.

**This is not SQL syntax injection**: the SQL structure remains unchanged. However, it can broaden matching beyond intent—often called **pattern injection** or **semantic abuse**.

### 27.1. When Exact Substring Matching Is Required

Pick an escape character such as `!`:

- `!` → `!!`.
- `%` → `!%`.
- `_` → `!_`.

In PL/pgSQL:

```sql
v_escaped := replace(
    replace(
        replace(p_text, '!', '!!'),
        '%', '!%'
    ),
    '_', '!_'
);

v_pattern := '%' || v_escaped || '%';

EXECUTE $query$
    SELECT COUNT(*)
    FROM sqli388.orders
    WHERE tenant_id = $1
      AND customer_code LIKE $2 ESCAPE '!'
$query$
INTO v_count
USING p_tenant_id, v_pattern;
```

### 27.2. Escaping Order Matters

First escape the escape character `!` itself, then `%` and `_`. Doing it in reverse can accidentally double-escape newly inserted `!` characters.

### 27.3. ILIKE Also Needs Escaping for Literal Searches

`ILIKE` only changes case-matching sensitivity under the relevant collation/locale; it does not turn `%` and `_` into plain text.

### 27.4. SQL Parameters Do Not Alter LIKE Semantics

`PreparedStatement`/`USING` protects SQL syntax, yet **does not neutralize** `LIKE` wildcards. Define pattern-matching policies explicitly.

## 28. Regex and Full-Text Search Are Still Sub-Languages

### 28.1. Regex

```sql
WHERE description ~ $1
```

Even though SQL is parameterized, `$1` is parsed by the regex engine as a **regular expression**. Metacharacters, anchors, quantifiers, and alternation all take effect.

If users expect literal text matching, never feed raw input directly into regex matching without escaping or policy controls.

### 28.2. Resource-Intensive Queries

Complex regular expressions can consume heavy CPU across large datasets. Protect with input limits, restrictions on regex usage, `statement_timeout`, and realistic workload tests.

### 28.3. PostgreSQL Full-Text Search

```sql
PREPARE fts_find(integer, text) AS
SELECT order_id, description
FROM sqli388.orders
WHERE tenant_id = $1
  AND to_tsvector(
      'simple', coalesce(description, '')
  ) @@ websearch_to_tsquery('simple', $2)
ORDER BY order_id;

EXECUTE fts_find(10, 'PostgreSQL');
DEALLOCATE fts_find;
```

`$2` is a bound value; raw text is never concatenated into SQL syntax.

### 28.4. FTS Query Syntax Is Not SQL Syntax

`websearch_to_tsquery` parses input as web-style search terms per PostgreSQL's FTS rules. You still need length bounds, an appropriate text search configuration, and cost/quality testing, yet the input itself cannot make the SQL parser run new SQL statements.

### 28.5. Never Confuse Search With Access Control

No matter how safely regex, FTS, or `LIKE` is bound, always enforce mandatory tenant, status, ACL predicates, and RLS policies.

## 29. SQL Text From format() and String Escaping

In utility commands that do not support bind parameters in the needed position, you may have to build SQL text.

### 29.1. `format('%L')` for DDL Literals

For example, an administrator updating the comment of an **allowlisted** table:

```sql
EXECUTE format(
    'COMMENT ON TABLE %I.%I IS %L',
    'sqli388',
    'orders',
    p_comment
);
```

`%L` safely quotes the comment literal or emits `NULL`.

### 29.2. Run Only Under Authorized Admin Privileges

`COMMENT ON` is a DDL/utility statement governed by object ownership/privileges. If callers can pass arbitrary table names or invoke a high-privilege definer, authorization risk remains even when SQL text is properly quoted.

### 29.3. Backslash Escaping Is Not a Universal Fix

Writing ad-hoc `replace(input, "'", "\\'")` before concatenating SQL breaks easily due to PostgreSQL string-literal rules, `standard_conforming_strings`, and nested escape layers.

### 29.4. Dollar Quoting Fits Static Code Blocks

```sql
DO $body$
BEGIN
    RAISE NOTICE 'Hello from a fixed PL/pgSQL body';
END;
$body$;
```

However, **never splice arbitrary user input between `$tag$ ... $tag$`** as a runtime escaping trick. User input could contain that exact closing tag.

### 29.5. Identifiers Also Have Length Limits

PostgreSQL truncates or limits identifier length per build configuration (commonly 63 bytes by default). `quote_ident` does not eliminate truncation or collision risks when deriving object names from arbitrary data.

## 30. Do Not Trust Relation Names Simply Because `regclass` Resolves Them

`regclass` resolves text to a relation OID:

```sql
SELECT
    'sqli388.orders'::regclass AS active_relation,
    'sqli388.orders_archive'::regclass AS archive_relation;
```

While helpful in database tooling:

- `regclass` does not verify the caller **is permitted** to select that relation.
- Unqualified names remain sensitive to `search_path`.
- Objects can be renamed, dropped, or recreated after an initial lookup.
- A definer function taking an arbitrary relation OID and running as its owner can still bypass authorization.

### 30.1. Catalog Lookup Is Not an Allowlist

Checking "does this table exist?" is weaker than "is this table in the permitted set and allowed for this caller by policy?".

### 30.2. Static Mapping Is Usually Simpler

For two tables `orders` and `orders_archive`, mapping an enum `'current'`/`'archive'` to hardcoded identifiers is far easier to audit than an API accepting arbitrary `regclass` inputs.

## 31. SECURITY DEFINER: Same Injection, Larger Blast Radius

A routine declared as:

```sql
CREATE FUNCTION trusted.some_api(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
AS $fn$
...
$fn$;
```

executes with the privileges of the **routine owner** during execution.

If that owner can read many tables unavailable to the caller, unsafe dynamic SQL lets the caller control what the owner accesses.

### 31.1. Proper Quoting Is Not Sufficient

The code:

```sql
EXECUTE format(
    'SELECT COUNT(*) FROM %I.%I',
    p_schema, p_table
)
INTO v_count;
```

can be **100% syntactically valid** with zero syntax injection, yet still expose an API capable of counting any table the owner can read. Object-level allowlists and authorization checks remain mandatory.

### 31.2. Least-Privilege Function Owner

Prefer a dedicated `NOLOGIN` owner role holding only the required `SELECT`/`UPDATE`/`INSERT` grants—never superuser or `BYPASSRLS` unless strictly justified.

### 31.3. `CURRENT_USER` Inside a Definer

Inside a definer context, `CURRENT_USER` returns the routine owner, not the end user invoking it. `SESSION_USER` reflects the database login; when multiple HTTP users share a connection pool, it cannot distinguish web users.

### 31.4. Tenant Identity Needs a Trusted Source

A definer function taking an unverified `p_tenant_id` and reading another tenant's rows with owner privileges is an authorization bug, even when all parameters are bound.

## 32. `search_path`: Protecting Object Name Resolution

PostgreSQL searches `search_path` to resolve unqualified object names per lookup rules.

```sql
SHOW search_path;

SELECT
    current_schema(),
    current_schemas(true);
```

A query like:

```sql
SELECT * FROM orders;
```

can resolve to different `orders` tables depending on the path.

### 32.1. Risk of Writable Schemas

If a schema where an attacker holds `CREATE` appears ahead of a trusted schema, unqualified function, table, operator, or type names may be shadowed under matching resolution conditions.

### 32.2. `pg_catalog` and `pg_temp`

- `pg_catalog` stores built-in objects. When listed explicitly, its position determines lookup priority; keep it ahead of untrusted application schemas.
- The temporary schema has special priority: when omitted from the path, it may be searched first for **relation and type names**; function and operator lookup do not follow that temp-first table rule.

### 32.3. Safe Path Pattern for Privileged Routines

```sql
SECURITY DEFINER
SET search_path = pg_catalog, trusted_schema, pg_temp
```

Where `trusted_schema` genuinely **forbids untrusted callers from running CREATE/ALTER**.

Always use schema-qualified references for sensitive tables and functions:

```sql
SELECT *
FROM trusted_schema.some_table;
```

### 32.4. Never Deploy Incomplete Definer Stubs

```sql
-- Configuration pseudocode, not complete DDL:
-- CREATE FUNCTION trusted_schema.api(...) RETURNS ...
-- LANGUAGE plpgsql SECURITY DEFINER
-- SET search_path = pg_catalog, trusted_schema, pg_temp
-- AS $fn$ ... $fn$;
```

Real definer routines require full review of grants, inputs, tenant scoping, helper routines, and body logic. Merely adding `SET search_path` does not make an API secure.

### 32.5. Avoid `public` Unless Explicitly Trusted

`CREATE` privileges on `public` vary by database, PostgreSQL version, upgrade history, and manual grants. Never assume every existing `public` schema is safe.

## 33. RLS and Multi-Tenancy: Safe SQL Can Still Leak Rows

Row-Level Security (RLS) restricts row visibility and modification according to PostgreSQL policies.

### 33.1. RLS Does Not Apply If the Role Bypasses It

Superusers and `BYPASSRLS` roles bypass RLS. Table owners also bypass policies by default unless `FORCE ROW LEVEL SECURITY` is enabled.

### 33.2. Calling Through SECURITY DEFINER

Tables are accessed under the effective privileges of the definer owner rather than the caller's RLS context (unlike `SECURITY INVOKER`). If the owner bypasses RLS, enforce explicit trusted authorization inside the routine to avoid tenant leakage.

### 33.3. Custom GUCs Do Not Authenticate Users on Their Own

A policy such as:

```sql
USING (
    tenant_id =
    current_setting('app.tenant_id')::integer
)
```

is safe only if the system **protects the session context value**. If an untrusted caller can execute `SET app.tenant_id`, that value cannot be trusted.

### 33.4. Tenant Predicates Apply to Counts, Facets, and Exports Too

Authorization belongs not just on list endpoints, but equally on total counts, autocomplete suggestions, file exports, and reports.

### 33.5. Test SQL Injection and Authorization Separately

Verify both:

- Inputs containing SQL-like syntax never become executable SQL code.
- Callers cannot access unauthorized tenants **even when inputs contain no special characters at all**.

## 34. GRANT, Roles, and Least-Privilege Blast-Radius Control

Even when an application uses prepared statements everywhere, enforce strict database privileges:

- Runtime DB roles should not own tables unnecessarily.
- Grant no `CREATE` privileges inside sensitive schemas.
- Grant only task-specific `SELECT`/`INSERT`/`UPDATE` rights.
- Never assign superuser, `CREATEROLE`, or `BYPASSRLS` by default.
- Avoid allowing arbitrary SQL execution from clients.
- Use dedicated migration roles for DDL.
- Give definer owners the minimum privileges required to operate.

### 34.1. Prepared Statements Are Not a SQL Firewall

A role allowed to submit arbitrary SQL can execute **arbitrary valid SQL statements**. Parameterization only prevents data inputs from breaking out of fixed SQL templates.

### 34.2. Minimize Blast Radius

If application code has a bug, tight database privileges limit damage. A runtime role restricted to `SELECT` on a narrow non-sensitive schema carries far less risk than superuser.

### 34.3. `PUBLIC EXECUTE` on Privileged Functions

Newly created PostgreSQL functions typically grant `EXECUTE` to `PUBLIC` by default unless altered. For `SECURITY DEFINER` routines:

```sql
BEGIN;

-- CREATE FUNCTION ... SECURITY DEFINER ...;

-- Once the routine is created:
-- REVOKE ALL ON FUNCTION schema.api(types...) FROM PUBLIC;
-- GRANT EXECUTE ON FUNCTION schema.api(types...) TO trusted_role;

COMMIT;
```

This is a **migration skeleton**, not standalone runnable SQL since the statements are commented out. The key is executing CREATE, REVOKE, and GRANT **within the same transaction** to avoid an open exposure window.

### 34.4. Separate Function Privilege From Object Authorization

Holding permission to invoke `api()` does not imply permission to query **every customer ID** accepted by that API. Row/object-level authorization checks must still run inside the API.

## 35. Dynamic DDL: Higher Risk Than Dynamic SELECT

A migration tool might generate tables dynamically from configuration:

```sql
EXECUTE format(
    'CREATE TABLE %I.%I (
         id bigint PRIMARY KEY,
         payload text
     )',
    v_schema,
    v_table
);
```

### 35.1. Quoting Is Necessary but Insufficient

- `v_schema` must be a schema authorized for management.
- `v_table` must follow naming and quota rules.
- The caller must hold appropriate creation rights.
- Prevent name collisions and system-object clashes.
- Never allow untrusted roles to create tables inside schemas trusted by `SECURITY DEFINER` code.

### 35.2. Utility DDL Cannot Bind Every Position

Many utility statements reject parameter placeholders where optimizable DML commands accept them. Use `%I` for identifiers and `%L` for literals when generating DDL text.

### 35.3. Never Accept Raw DDL Fragments

Taking `p_columns_sql text` from an HTTP request and splicing it into `CREATE TABLE` is unsafe even if the table name is quoted. When dynamic DDL is needed, generate column definitions strictly from **validated schemas or structured models**, never raw user SQL text.

### 35.4. Avoid Unbounded CREATE Privileges

Automated creation of thousands of tables or schemas can inflate catalog overhead, maintenance/backup costs, and operational failures even without injection.

## 36. Never Confuse Valid Query Syntax With Sound Business Policy

Consider an already-parameterized query:

```sql
SELECT order_id, amount
FROM sqli388.orders
WHERE tenant_id = $1
  AND amount >= $2
ORDER BY amount ASC
LIMIT $3;
```

It can still suffer from **non-injection flaws**:

- Unverified tenant ID.
- Negative, absurdly large, or currency-mismatched amounts.
- `LIMIT` exceeding allowed quotas.
- Missing required time-window or permission filters.
- Missing tie-breaker when multiple orders share the same amount.
- Missing statement timeout.
- Overly broad DB role reading unrelated schemas.

**Parameterized SQL is one defensive layer**, not the entire security design.

## 37. Execution Plans and Parameterization

`PREPARE` and JDBC prepared statements may run under a **custom plan** or a **generic plan** depending on caching rules, planner heuristics, PostgreSQL version, and query shape.

### 37.1. Skewed Data Across Parameters

A tenant with 10 rows versus one with 10 million rows may favor different access paths. Parameterization preserves semantic correctness, yet performance can vary.

### 37.2. Dynamic PL/pgSQL EXECUTE Re-Plans

Unlike static PL/pgSQL queries, `EXECUTE command_string USING ...` does not cache plans in the same manner; it re-plans dynamic commands upon execution. That can help with highly skewed parameters, at the cost of higher planning CPU.

### 37.3. Never Revert to String Concatenation to "Force an Index"

If a generic prepared plan performs poorly, inspect statistics, indexes, `plan_cache_mode`, and cleanly split parameterized query variants—never sacrifice security by interpolating raw values.

### 37.4. `EXPLAIN (ANALYZE, BUFFERS)`

```sql
PREPARE perf_orders(integer, text) AS
SELECT order_id, amount
FROM sqli388.orders
WHERE tenant_id = $1
  AND customer_code = $2;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE perf_orders(10, 'O''Reilly');

DEALLOCATE perf_orders;
```

Use this to inspect actual row counts, buffer hits/reads, and index usage. Remember `EXPLAIN ANALYZE` actually executes the statement, so wrap or handle DML cautiously since it mutates data.

### 37.5. Security and Performance Are Not Opposites

Proper parameterization produces clearer, type-safe, auditable code. Conduct performance tuning **after ensuring strict code/data separation and authorization boundaries**.

## 38. Logging, Error Handling, and Attack Detection

In production, monitor:

- Error rates: syntax errors, permission denied, statement timeouts.
- Sort/table/column selections rejected by allowlists.
- Query duration and p95/p99 latency.
- Spikes in requests carrying oversized inputs or anomalous patterns.
- Concurrent query volume.
- Invocations of definer APIs and verified role contexts.
- Changes to grants, schema objects, and migrations.

### 38.1. Never Log Raw Sensitive Payloads Carelessly

Search terms, customer names, and notes often hold PII. Logging every bound parameter verbatim creates a secondary data-leak channel.

Prefer structured logs with template ID, error category, input length, outcome, correlation ID, and proper masking.

### 38.2. Syntax Errors Are Not the Only Signal

An injection exploit need not trigger SQL syntax errors, and syntax errors often stem from ordinary application bugs rather than attacks. Build detection combining behavior, privilege events, and metrics.

### 38.3. Never Expose Internal SQL Through API Errors

Driver exceptions often leak table names, SQL fragments, or schema layout. Log details internally at appropriate levels and return sanitized error messages externally.

### 38.4. Query Timeouts and Rate Limits

Safe parameter binding will not stop expensive regex searches, FTS queries, or overly broad legitimate reports from exhausting resources. Enforce timeouts, page-size limits, rate limiting, and workload quotas.

## 39. SQL Injection Testing Strategy

Include at least these test categories:

| Category | Test Input | Expected Outcome |
| --- | --- | --- |
| Normal text | `ALICE` | Exact expected record |
| Single quote | `O'Reilly` | No parse error; exact value match |
| Syntax-like string | `x' OR TRUE --` | Does not alter WHERE semantics |
| Unicode | `VN-ĐỎ` | No encoding or normalization errors |
| Literal wildcards | `A%_B` | Exact `=` match; `LIKE` escapes via `ESCAPE` when needed |
| Empty string | `''` | Follows API policy |
| SQL NULL | `NULL` | Proper `IS NULL`/null-safe comparison |
| Double quote | `a"b` | Does not break identifier quoting |
| Dot in string | `schema.table` | Not mistakenly treated as qualified path |
| Reserved keyword identifier | `select` | Properly quoted if permitted |
| Disallowed identifier | `pg_catalog.pg_authid` | Rejected before SQL construction |
| Invalid sort | `unknown_sort` | Rejected |
| Huge page size | `999999999` | Rejected or clamped per policy |
| Unauthorized tenant | Another tenant | Returns no unauthorized data |
| Complex regex | Invalid / CPU-heavy regex | Validated/bounded/timed out |
| Empty/unmatched FTS | Empty or rare term | Follows UX without accidental full scan |
| Schema shadowing | Shadow table in `pg_temp` | Definer targets the right relation |
| Restricted role | EXECUTE-only / no SELECT role | Honors privilege contract strictly |

### 39.1. Assert Exact Query Results, Not Just Absence of Errors

Never stop at asserting "no SQL syntax error occurred". Check exact returned rows and counts to catch silent logic flaws.

### 39.2. Verify No Unintended State Mutations

For read-only endpoints, verify that row counts and schema state remain untouched regardless of input.

### 39.3. Test Using Realistic Least-Privilege Roles

Superuser test connections mask grant and RLS bugs. Test under actual application runtime roles or accurately modeled ACLs.

### 39.4. Use Explicit Transactions for Lab Tests Where Appropriate

`BEGIN`/`ROLLBACK` keeps lab DML controlled, though rolling back a transaction does not prove a production endpoint is read-only.

## 40. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Escaping quotes is enough" | Bind values; use distinct defenses for identifiers and syntax |
| "`PreparedStatement` makes everything safe" | Only bound slots are protected; authorization/logic bugs remain |
| "`?` can substitute a table name" | No; parameters represent values, not identifiers |
| "`ORDER BY ?` accepts `'amount DESC'`" | Cannot supply SQL sort syntax via parameters |
| "`quote_ident` checks table permissions" | No |
| "`quote_literal` works for table names" | Wrong category: literals differ from identifiers |
| "`format('%I','a.b')` means `schema.table`" | It quotes one identifier containing a dot |
| "`%s` equals `%I`" | `%s` performs no SQL quoting |
| "`%L` is needed even with `USING`" | No; prefer `USING` for values |
| "`quote_literal(NULL)` returns `'NULL'` text" | It returns SQL `NULL` |
| "`quote_nullable` makes `= NULL` match" | No; use a null-safe predicate |
| "Binding `LIKE` makes `%`/`_` literal" | Pattern wildcards remain active |
| "Binding regex forces literal matching" | The regex engine still evaluates patterns |
| "Data already in DB is always safe" | Second-order injection can still occur |
| "Allowlists are only for SQL injection" | They also enforce object authorization |
| "Any properly quoted table is safe to select" | No; a privileged owner could expose sensitive tables |
| "Running APIs as superuser improves stability" | Creates a massive blast radius |
| "Caller RLS always applies inside definer functions" | Owner context may bypass RLS |
| "Binding tenant ID guarantees tenant isolation" | Requires a trusted tenant identity source |
| "Caller's `SET search_path` suffices for definers" | Pin a safe path inside the routine itself |
| "`pg_temp` cannot shadow regular tables" | It has special lookup priority rules |
| "Having GIN/B-tree indexes removes need for limits" | Wildcards, regexes, and large sorts remain costly |
| "Single statements cannot be injected" | Injection alters logic within one statement |
| "SQL builders automatically secure raw fragments" | Verify whether APIs bind values or append raw SQL |
| "No SQL error means no injection" | Many logic injections succeed without errors |
| "SQL injection and access control are identical" | Distinct issues requiring separate testing |

## 41. Exercises With Answers

These exercises use schema `sqli388`. To run `EXECUTE ... INTO ... USING` snippets directly, place them inside a PL/pgSQL function or `DO` block with local variables declared. Patterns labeled "wrong/dangerous" are for analysis only—never run them in production.

### Exercise 1. What is SQL injection?

**Answer:** Untrusted data entering SQL syntactic positions, causing the parser to treat part of the input as query structure rather than a data value.

### Exercise 2. Why does `'O''Reilly'` break manual literal concatenation?

**Answer:** The embedded single quote terminates the string literal prematurely. Parameter binding avoids constructing string literals from input.

### Exercise 3. What does PreparedStatement protect?

**Answer:** Placeholders representing **data values** within a fixed SQL template. It neither binds table names nor fixes authorization logic.

### Exercise 4. Which placeholder syntax does JDBC use?

**Answer:** `?`, bound via `ps.setX(index, value)` using 1-based indexes.

### Exercise 5. Which placeholder syntax does PostgreSQL PREPARE use?

**Answer:** `$1`, `$2`, etc., matching declared parameter types and positions.

### Exercise 6. Write SQL to look up a customer scoped to a specific tenant

```sql
PREPARE q(integer, text) AS
SELECT order_id FROM sqli388.orders
WHERE tenant_id = $1
  AND customer_code = $2;
```

**Answer:** Bind both values cleanly with no input concatenation.

### Exercise 7. Why can a properly bound tenant ID still leak data?

**Answer:** A caller might choose another tenant ID if the API or DB does not verify permission for that tenant. Binding is not authorization.

### Exercise 8. Is text previously stored in a database automatically safe when read back?

**Answer:** No. Concatenating stored text into dynamic SQL later creates second-order injection.

### Exercise 9. How does a data value differ from an identifier?

**Answer:** A value is data evaluated in an expression; an identifier names a SQL object or column in query syntax.

### Exercise 10. What is `quote_ident` used for?

**Answer:** Formatting a valid SQL identifier representation, such as a table or column name.

### Exercise 11. What is `quote_literal` used for?

**Answer:** Formatting a data value as SQL literal text when building SQL source is unavoidable; for optimizable dynamic SQL, prefer `USING`.

### Exercise 12. How does `quote_nullable` differ from `quote_literal` on NULL input?

**Answer:** `quote_nullable(NULL)` returns the text `'NULL'`, whereas `quote_literal(NULL)` returns SQL `NULL`.

### Exercise 13. Why can a constructed command string become NULL?

**Answer:** Concatenating `'prefix' || quote_literal(NULL)` yields SQL `NULL`, causing `EXECUTE` to fail with a null command string.

### Exercise 14. How do `%I` and `%L` differ?

**Answer:** `%I` formats identifiers, while `%L` formats literal values (including SQL `NULL`).

### Exercise 15. Can `%s` safely interpolate raw user sort expressions?

**Answer:** No. `%s` inserts text without SQL quoting; use it only for fixed allowlisted fragments.

### Exercise 16. How do you quote `schema.table`?

```sql
SELECT format('%I.%I', 'sqli388', 'orders');
```

**Answer:** Quote schema and table separately.

### Exercise 17. Why is quoting `'sqli388.orders'` with a single `%I` wrong?

**Answer:** It creates one identifier containing a dot, not a schema-qualified object reference.

### Exercise 18. Can you bind a table name via `USING p_table`?

**Answer:** No; `USING` binds values, not `FROM table_identifier` grammar nodes.

### Exercise 19. Does `SELECT $1 FROM orders` read the column named in `$1`?

**Answer:** No; `$1` evaluates as a bound parameter value, not a column reference.

### Exercise 20. How do you safely toggle between current and archive tables?

**Answer:** Validate the `'current'`/`'archive'` enum, map to fixed table names, quote with `%I.%I`, and bind the tenant ID.

### Exercise 21. Does properly quoting a table name ensure the caller is allowed to query it?

**Answer:** No. Object allowlists, DB privileges, and business authorization are still required.

### Exercise 22. How do you filter dynamically on `status` or `customer_code`?

**Answer:** Allowlist both column names, use `%I` for the column identifier, and use `$1`/`USING` for data values.

### Exercise 23. Identify the flaw in `tenant=10 AND status='PAID' OR customer='ALICE'`

**Answer:** The `OR` branch matches rows across other tenants. Group `OR` branches inside parentheses.

### Exercise 24. Does parameterization fix missing parentheses around AND/OR?

**Answer:** No. Correct boolean grouping is still required.

### Exercise 25. How should user-selected ORDER BY column and direction be handled?

**Answer:** Map enum values to fixed SQL fragments, or allowlist and quote column identifiers paired with code-selected `'ASC'`/`'DESC'`; never embed raw input.

### Exercise 26. Does a bound LIMIT still need validation?

**Answer:** Yes. Enforce page-size caps and quotas to prevent excessive resource consumption.

### Exercise 27. Does `IN ($1)` expand a CSV string into multiple values?

**Answer:** No. Use `= ANY($1::text[])` with a SQL array value, or generate placeholders from a validated element count.

### Exercise 28. Why does `status = ANY(ARRAY[]::text[])` differ from omitting the filter?

**Answer:** An empty array matches zero rows, whereas omitting the filter matches all allowed statuses.

### Exercise 29. Is `NULL = NULL` evaluated as TRUE?

**Answer:** No; it evaluates to SQL `NULL` (`UNKNOWN`).

### Exercise 30. Write a null-safe equality predicate

```sql
WHERE note IS NOT DISTINCT FROM $1
```

**Answer:** Returns true when both sides are `NULL`.

### Exercise 31. Does `quote_nullable` make `note = NULL` match null rows?

**Answer:** No. It only builds literal text; the comparison predicate itself must handle `NULL` properly.

### Exercise 32. Does binding a LIKE pattern treat `%` and `_` literally?

**Answer:** No. For literal substring matching, escape `%` and `_` with a chosen escape character and specify `ESCAPE`.

### Exercise 33. Escape `A%_B` for literal substring matching

**Answer:** With `ESCAPE '!'`, escape the literal payload to `A!%!_B` and wrap with outer wildcards for contains matching: `%A!%!_B%`.

### Exercise 34. Does binding a regex treat it as literal text?

**Answer:** No. Regex metacharacters remain active in the regex engine; apply validation or literal-escaping rules separately.

### Exercise 35. Does binding FTS keywords allow arbitrary SQL execution?

**Answer:** No. `websearch_to_tsquery('simple', $1)` parses `$1` according to FTS query syntax, not as SQL statements.

### Exercise 36. Is there any benefit to using dynamic SQL when static SQL works?

**Answer:** Usually no. Static SQL is simpler, easier to audit, and benefits from plan caching.

### Exercise 37. Does PL/pgSQL EXECUTE re-plan dynamic queries?

**Answer:** Dynamic commands are typically parsed and planned on execution, unlike static PL/pgSQL SQL statements which cache plans.

### Exercise 38. Can utility DDL bind every input via parameters?

**Answer:** No. Identifiers belong to syntax, and many DDL value positions require `%L` formatting rather than parameter placeholders.

### Exercise 39. How can `COMMENT ON TABLE` be built safely?

**Answer:** `format('COMMENT ON TABLE %I.%I IS %L', schema, table, comment)` against an allowlisted object under authorized privileges.

### Exercise 40. Why shouldn't raw column definitions from a request be appended into CREATE TABLE?

**Answer:** Column definitions are SQL syntax fragments capable of embedding unexpected clauses or expressions; construct DDL strictly from validated structured models.

### Exercise 41. Does `regclass` replace authorization?

**Answer:** No. It resolves relation names/OIDs, not whether the caller is authorized to access them.

### Exercise 42. Why does `SECURITY DEFINER` heighten dynamic SQL risk?

**Answer:** Dynamic SQL runs under the owner's elevated privileges, widening potential access if identifiers or inputs are insufficiently controlled.

### Exercise 43. What owner should a definer function use?

**Answer:** A least-privilege role, ideally a dedicated `NOLOGIN` role; avoid superusers and `BYPASSRLS` roles unless rigorously justified and reviewed.

### Exercise 44. Why does `search_path` matter?

**Answer:** Unqualified names can resolve to objects in unintended schemas; attacker-writable schemas or `pg_temp` can shadow expected objects depending on object type.

### Exercise 45. What is a sound search_path pattern for definer functions?

**Answer:** `pg_catalog, trusted_schema, pg_temp` where untrusted users cannot `CREATE`/`ALTER` inside `trusted_schema`, combined with fully qualified references.

### Exercise 46. Inside a definer function, is `CURRENT_USER` the web end user?

**Answer:** No; it is normally the function owner, and `SESSION_USER` is often just the shared DB pool login.

### Exercise 47. Does RLS always enforce caller permissions inside a definer function?

**Answer:** No. Owner privileges and RLS bypass behavior must be evaluated explicitly.

### Exercise 48. Why can a syntactically safe PreparedStatement still return the wrong tenant's data?

**Answer:** Broken application authorization, missing row filters, or misconfigured RLS—an authorization defect rather than injection.

### Exercise 49. Why avoid logging every query parameter?

**Answer:** Parameters frequently contain PII or secrets; use sanitized structured logs, correlation IDs, and retention policies.

### Exercise 50. Build a security checklist for a search endpoint

**Suggested answer:**

1. Keep SQL templates server-controlled; never accept raw SQL from clients.
2. Bind all data values via JDBC parameters / `USING`.
3. Allowlist all dynamic tables, columns, operators, and sort fragments.
4. Quote identifiers with `%I` and schema/table pairs with `%I.%I`.
5. Never pass raw user input to `%s`.
6. Enforce mandatory tenant/ACL/status predicates across every query variant.
7. Audit RLS, DB role grants, and definer owners/`search_path`.
8. Handle `NULL` and `LIKE`/regex/FTS semantics explicitly.
9. Validate page sizes, input lengths, array sizes, and time ranges.
10. Test quotes, Unicode, wildcards, SQL-like payloads, and negative authorization cases.
11. Review query plans, timeouts, logging hygiene, and concurrent load.
12. Set up alerts and runbooks for anomalous syntax or permission failures.

## 42. Practical Implementation Checklist

| Question | Standard |
| --- | --- |
| Is raw input concatenated into SQL? | Never for data values |
| Are parameters bound via prepared statements? | `?` / `$n` / `USING` |
| Are table/schema/column names dynamic? | Allowlist + `%I` |
| Are string literals and identifiers distinguished? | `%L` vs `%I` |
| Are `schema.table` names quoted cleanly? | `%I.%I` |
| Are `%s` fragments used? | Strictly code-controlled fixed fragments |
| Is `ORDER BY` dynamic? | Enum mapping plus deterministic tie-breaker |
| Is an `IN`-list dynamic? | SQL array / validated placeholder count |
| Are `NULL` values possible? | Typed parameters and null-safe predicates |
| Are `LIKE` wildcards handled? | Explicit literal/pattern policy |
| Are regexes used? | Length/complexity limits, separate from injection |
| Is FTS used? | Bind query text; bound search cost |
| Is utility DDL dynamic? | Strict object/privilege policy plus `%L` if needed |
| Are DB roles overly broad? | Least privilege |
| Are `SECURITY DEFINER` routines present? | Audited owner, `search_path`, allowlist, ACLs |
| Are schemas protected? | No untrusted `CREATE` in trusted schemas |
| Is RLS enabled? | Tested under effective runtime roles |
| Are DB logins pooled/shared? | User identity never inferred from `SESSION_USER` |
| Is tenant authorization enforced? | Verified context, never raw input alone |
| Are `OR` conditions complex? | Proper parentheses |
| Do counts/exports apply the same scope? | Consistent authorization predicates |
| Does an ORM generate custom SQL? | Audit raw fragments and native query paths |
| Is stored DB data concatenated later? | Prevent second-order injection |
| Are resource quotas enforced? | Bounded queries, pages, and searches |
| Are edge-case inputs tested? | Quotes, Unicode, `NULL`, long strings |
| Are tests run as low-privilege roles? | Never test solely as superuser |
| Is cross-tenant leakage tested? | Explicit negative assertions |
| Is raw PII logged? | Redacted with retention policies |
| Are syntax/permission errors monitored? | Alerts and runbooks configured |
| Are plans evaluated for performance? | `EXPLAIN (ANALYZE, BUFFERS)` |
| Are migrations and grants reviewed? | Yes |

## 43. Review Workflow for a Dynamic Reporting SQL Endpoint

Suppose product needs an API:

```text
GET /reports/orders
?source=archive
&sort=amount_desc
&customer=O'Reilly
&limit=50
```

Proper workflow:

### Step 1. Authenticate Caller and Derive Tenant

The server verifies from trusted identity/context that the caller is authorized for tenant 10. Never blindly trust a client-supplied `tenant_id`.

### Step 2. Map Source

`source=archive` → fixed identifier `sqli388.orders_archive`. Reject anything outside the allowlist.

### Step 3. Map Sort

`sort=amount_desc` → fixed fragment `ORDER BY amount DESC, order_id DESC`.

### Step 4. Validate Limit

Confirm `limit` lies within 1–100 or your defined policy cap.

### Step 5. Bind Customer

Bind `'O''Reilly'` as `$2` / JDBC `?` without building a manual SQL literal.

### Step 6. Execute Scoped Query

```sql
-- Illustrative template after code-side mapping:
SELECT order_id, customer_code, amount
FROM sqli388.orders_archive
WHERE tenant_id = $1
  AND customer_code = $2
ORDER BY amount DESC, order_id DESC
LIMIT $3;
```

If the table name genuinely varies inside PL/pgSQL at runtime, format it with `format('%I.%I')` and bind data with `EXECUTE ... USING`.

### Step 7. Verify Output and Telemetry

- No rows belonging to other tenants.
- No duplicate or out-of-scope records.
- No raw parameter leakage into logs.
- Query executes within timeouts and budgets.
- Only authorized fields appear in the API response.

**A sound API preserves both the syntax/data boundary and the authorization boundary.**

## 44. Summary

Preventing SQL injection in PostgreSQL goes beyond escaping quotes properly; it is about **designing clear boundaries across SQL code, input data, and access privileges**.

Key rules to remember:

1. **Never concatenate untrusted input into SQL source**. Always bind data values with `?`, `$n`, or `EXECUTE ... USING`.
2. **JDBC `PreparedStatement`** is the Java default for structurally fixed queries.
3. **PL/pgSQL `EXECUTE ... USING`** keeps values separate from SQL text even inside dynamic statements.
4. **Identifiers cannot be bound as values**. For dynamic tables or columns, apply an allowlist/mapping and quote with `%I` or `quote_ident`.
5. **`%L`/`quote_literal` format SQL literals**, especially when utility DDL requires building text.
6. **`%s` performs no SQL escaping**. Restrict it strictly to fixed fragments controlled by application code.
7. **Schema and table names must be quoted separately as `%I.%I`**.
8. **`quote_literal(NULL)` yields SQL `NULL`**, whereas `quote_nullable`/`%L` produce the token `'NULL'`; proper quoting still requires proper `NULL` comparison predicates.
9. **Quoting does not replace authorization**. A safely quoted table name may still point to sensitive data; a safely bound tenant ID may still be unauthorized.
10. **`LIKE`/regex/FTS carry their own sub-language semantics**. Parameterization secures SQL grammar without neutralizing wildcards or regex metacharacters.
11. **`SECURITY DEFINER` routines require least-privilege owners, trusted `search_path`, and explicit RLS/tenant verification**.
12. **Never rely on custom escaping parsers** or accept raw SQL/`ORDER BY`/DDL fragments from clients.
13. **Test negative cases thoroughly**: quotes, Unicode, `NULL`, invalid identifiers, cross-tenant requests, low-privilege roles, and oversized queries.
14. **Tune performance only after securing boundaries**: indexes, plans, quotas, timeouts, and sanitized logging.

Safe template when dynamic table and column selection is truly necessary:

```sql
-- Assumes v_schema, v_table, and v_column passed
-- allowlist/authorization checks and reside in a trusted schema.
EXECUTE format(
    'SELECT COUNT(*)
     FROM %I.%I
     WHERE tenant_id = $1
       AND %I = $2',
    v_schema,
    v_table,
    v_column
)
INTO v_count
USING authenticated_tenant_id, p_value;
```

**Final review checklist question:** "Which values come from the caller, which parts are parsed as SQL syntax, which objects is the caller permitted to select, and which role's privileges execute the statement?" Answering all four clearly gives you the solid foundation needed to eliminate SQL injection and prevent data exposure across dynamic queries in PostgreSQL.

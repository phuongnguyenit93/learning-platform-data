# Function Dependencies, Signature Changes, and Versioning in PostgreSQL

In PostgreSQL, a function is more than a named block of SQL or PL/pgSQL. A function also has an **identity based on its name, schema, and input parameter types**, a result type, execution privileges, execution attributes, and dependent objects. As a result, a seemingly small change — adding a parameter, changing the return type, renaming the function, or modifying default parameters — can break views, triggers, SQL statements in applications, or calls from JDBC.

Suppose an application is currently calling:

~~~sql
SELECT api_lab.order_total(1001);
~~~

You want to add discount support:

~~~sql
SELECT api_lab.order_total_v2(1001, 10);
~~~

This change raises several questions:

- Can `CREATE OR REPLACE FUNCTION` be used to add a parameter?
- If another overload is created, will existing calls and calls passing `NULL` or untyped literals become ambiguous?
- Will a view calling the old function be dropped if `DROP FUNCTION ... CASCADE` is executed?
- Are tables or other functions referenced by an SQL or PL/pgSQL function always fully recorded as dependencies in `pg_depend`?
- When the return type changes, how do we keep the old API working while migrating applications to the new API?
- When replacing the body of a `SECURITY DEFINER` function, how should privileges and `search_path` be verified?
- If a deployment fails, can we roll back without breaking active older application sessions?

This lesson focuses on **the lifecycle of a function as a database interface contract**, covering: identity/signature, overloading, default parameters, dependencies, catalogs, `REPLACE` vs. `DROP/CREATE`, safe migrations, versioning, security, and compatibility testing.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the **signature** and **identity** of a PostgreSQL function.
2. Understand the roles of `IN`, `OUT`, `INOUT`, `VARIADIC`, and default values in overload resolution.
3. Reference the exact overload using the function name together with its parameter types, such as `api_lab.order_total(bigint)`.
4. Distinguish changes that can be made with `CREATE OR REPLACE FUNCTION` from changes that require creating a new function.
5. Explain why changing a result type or `RETURNS TABLE` can break APIs and dependent objects.
6. Use `pg_proc`, `pg_namespace`, `pg_depend`, `pg_get_functiondef`, and `pg_get_function_identity_arguments` to inspect functions.
7. Recognize the difference between dependencies recorded by PostgreSQL in the catalog and dependencies that appear only inside string-based SQL bodies, PL/pgSQL, or dynamic SQL.
8. Use `DROP FUNCTION ... RESTRICT` carefully and avoid overusing `CASCADE`.
9. Design an **expand–migrate–contract** versioning workflow, keeping the old function intact and migrating clients step by step.
10. Configure `EXECUTE` privileges properly, distinguish `SECURITY INVOKER` from `SECURITY DEFINER`, and avoid `search_path` vulnerabilities.
11. Build a PostgreSQL lab containing source tables, a v1 function, a v2 function, a dependent view, and migration examples.
12. Plan an appropriate rollback strategy when multiple application versions and multiple overloads coexist.

## 2. A Function as a Database API

A function can be called by many different objects:

~~~text
     Java / JDBC Application
               |
               v
    api_lab.order_total(bigint) <----- View / SQL report
               |
               +----> Another SQL function
               |
               +----> Trigger function / procedure
               |
               v
         Source table orders
               |
               v
             products
~~~

If an interface is changed without checking all call sites, the application may encounter:

- `function ... does not exist` because the name or parameter types no longer match.
- `function ... is not unique` because overloading or default parameters introduce ambiguity.
- `cannot change return type of existing function` when `CREATE OR REPLACE` is used improperly.
- `DROP FUNCTION` errors due to dependent objects.
- `permission denied for function ...` errors after recreating a function.
- Incorrect results because the new body changed logic or data types.

Therefore, functions should be managed as **versioned public APIs**, not merely as utility scripts inside the database.

## 3. Function Signature: Name, Schema, and Input Parameter Types

Consider two functions:

~~~sql
CREATE FUNCTION api_lab.label_value(p_value integer)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'int:' || p_value::text
$$;

CREATE FUNCTION api_lab.label_value(p_value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'text:' || p_value
$$;
~~~

Both functions can coexist because their input types differ:

~~~text
api_lab.label_value(integer)
api_lab.label_value(text)
~~~

### 3.1. Not Just the Function Name

When querying the catalog or dropping a function, writing only `label_value` is not enough if multiple overloads exist. PostgreSQL distinguishes them by parameter types, for example:

~~~sql
DROP FUNCTION api_lab.label_value(integer);
~~~

This command targets only the `integer` overload, leaving `label_value(text)` untouched.

### 3.2. Parameter Names Do Not Create Separate Overloads

The following declarations **do not create two different signatures**:

~~~sql
-- Same signature by input type: integer.
CREATE FUNCTION api_lab.calculate(p_amount integer) ...
CREATE FUNCTION api_lab.calculate(p_value integer)  ...
~~~

The names `p_amount` and `p_value` matter when calling with **named notation**, but they do not make two functions with the same name and input types into distinct overloads.

### 3.3. Return Type Does Not Distinguish Overloads

Two functions in the same schema with the same name and the same input types cannot exist simultaneously if they differ only in return type:

~~~sql
-- Cannot coexist simultaneously:
-- api_lab.convert(integer) RETURNS text
-- api_lab.convert(integer) RETURNS numeric
~~~

PostgreSQL does not select overloads based on the expected return type of the surrounding SQL expression.

### 3.4. A Default Value Is Not a New Parameter Type

`p_rate numeric DEFAULT 0` is still a `numeric` parameter. A default value only allows omitting the argument at the call site; it does not turn `numeric` into a different type in the signature.

## 4. Parameter Modes: IN, OUT, INOUT, VARIADIC

PostgreSQL supports several parameter modes, and they affect the function contract differently.

| Mode | Purpose | Key Impact |
| --- | --- | --- |
| `IN` | Receives an input value | Part of the input type list that identifies the function |
| `OUT` | Returns a column/result field | Not used as an input parameter to distinguish function overloads |
| `INOUT` | Receives input and returns output | Plays both input and output roles |
| `VARIADIC` | Accepts a variable number of arguments of the same type | Participates in call resolution; must evaluate ambiguity risks |
| `TABLE` | Defines output columns for a set-returning function | Part of the result contract; output names do not create overloads |

### 4.1. Functions with OUT

~~~sql
CREATE FUNCTION api_lab.parse_ref(
    IN p_ref text,
    OUT prefix text,
    OUT suffix text
)
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT split_part(p_ref, '-', 1),
           split_part(p_ref, '-', 2)
$$;
~~~

The identifying input is `text`, while the two `OUT` parameters define the **result shape**. Calling:

~~~sql
SELECT * FROM api_lab.parse_ref('AB-123');
~~~

returns two columns: `prefix` and `suffix`.

### 4.2. Do Not Rely on OUT to Simulate Identity Differences

Changing `OUT suffix text` to `OUT suffix integer` changes the **result contract**; it does not create a separate overload simply because the `OUT` parameter type changed. Existing functions and their dependents require an explicit migration.

### 4.3. INOUT

With `INOUT`, the argument supplies a value at call time and also participates in the returned result. When identifying a routine by input types, an `INOUT` parameter counts as an input.

### 4.4. VARIADIC and Call Resolution

`VARIADIC` handles calls with variable numbers of arguments; same-named overloads can become harder to predict if exact-match functions also exist. Do not convert widely used API functions to `VARIADIC` without testing real call patterns.

## 5. Overloading: Flexible but Risky

Consider the `label_value` function with two overloads:

~~~sql
SELECT api_lab.label_value(42::integer);
SELECT api_lab.label_value('hello'::text);
~~~

When argument types are explicit, PostgreSQL selects the exact overload.

### 5.1. Untyped Literals

~~~sql
SELECT api_lab.label_value('42');
~~~

An uncast string literal initially has type `unknown`, allowing PostgreSQL to infer a type from context. PostgreSQL applies overload resolution rules, including type categories and preferred types. You should not rely on intuition that the literal `'42'` will always resolve to the integer overload.

### 5.2. Bind Parameters from JDBC

If a driver sends a parameter with an unspecified type or SQL passes an uncast `NULL`, overload selection may produce unexpected results.

~~~sql
SELECT api_lab.label_value(NULL::integer);
SELECT api_lab.label_value(NULL::text);
~~~

These two calls have unambiguous target signatures.

### 5.3. Explicit Casts When Overloads Have Different Business Semantics

~~~sql
SELECT api_lab.label_value($1::integer);
~~~

Using an explicit cast in a prepared statement clarifies the expected overload in the API contract. However, bind and cast to the actual domain data type—do not cast every argument to `text` just to "make errors go away".

### 5.4. Schema Matters Too

If multiple schemas contain same-named overloads and `search_path` differs across sessions, resolution can change. For critical APIs, always use schema-qualified names:

~~~sql
SELECT api_lab.label_value(42::integer);
~~~

## 6. Default Arguments and Ambiguity

Default parameters let you add options without requiring every call site to pass them:

~~~sql
CREATE FUNCTION api_lab.apply_rate(
    p_amount numeric,
    p_rate numeric DEFAULT 10
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT round(p_amount * (1 + p_rate / 100), 2)
$$;
~~~

~~~sql
SELECT api_lab.apply_rate(100::numeric);
SELECT api_lab.apply_rate(100::numeric, 5::numeric);
~~~

### 6.1. Default Parameters Still Belong to the Input Type List

The function's identity is:

~~~text
api_lab.apply_rate(numeric, numeric)
~~~

not `api_lab.apply_rate(numeric)` merely because `p_rate` can be omitted at call time.

### 6.2. Default Arguments Can Cause Ambiguity

Suppose the following function already exists:

~~~sql
CREATE FUNCTION api_lab.tax(p_amount numeric)
RETURNS numeric
LANGUAGE sql IMMUTABLE
AS $$ SELECT p_amount * 1.1 $$;
~~~

Later, another overload is added:

~~~sql
-- Illustrates an ambiguity-prone design.
CREATE FUNCTION api_lab.tax(
    p_amount numeric,
    p_rate numeric DEFAULT 10
)
RETURNS numeric
LANGUAGE sql IMMUTABLE
AS $$ SELECT p_amount * (1 + p_rate / 100) $$;
~~~

The call:

~~~sql
SELECT api_lab.tax(100::numeric);
~~~

now matches both the one-parameter overload and the two-parameter overload with a default, leading to resolution and migration issues. In particular, when **functions in the same schema both match because a default parameter is omitted**, PostgreSQL raises `function ... is not unique` in such cases rather than automatically choosing the "older function".

### 6.3. Rollout Rules

Before adding a default parameter to a public API:

1. List all existing overloads.
2. List every call form (positional, named, omitted arguments, `NULL`).
3. Test each call form using the actual parameter types sent by the application driver.
4. If ambiguity is possible, consider a **distinct v2 function name** or a wrapper with a clear contract.

### 6.4. Do Not Treat Default Parameters as In-Place Compatibility

Adding a default parameter **is not equivalent to modifying the same function in place**. The new signature is a different routine; existing call behavior must be verified under the updated set of overloads.

## 7. Named Notation and Parameter Names

PostgreSQL supports named parameter calls:

~~~sql
SELECT api_lab.apply_rate(
    p_rate => 7::numeric,
    p_amount => 100::numeric
);
~~~

Parameter names become **part of the contract for callers using named notation**.

### 7.1. Positional vs. Named Order

Positional calls depend on argument order. Named notation explicitly specifies parameter names, and PostgreSQL enforces rules for mixing positional and named arguments.

### 7.2. Renaming Parameters Can Break the API

Suppose an application executes:

~~~sql
SELECT api_lab.apply_rate(
    p_amount => 100,
    p_rate => 8
);
~~~

If `p_rate` is renamed to `rate_pct`, applications using the old name will not automatically update.

### 7.3. CREATE OR REPLACE and Named IN Parameters

PostgreSQL restricts **renaming already-named input parameters** via `CREATE OR REPLACE FUNCTION` on an existing function because doing so alters the named-call contract. To change parameter names, evaluate creating a new API or maintaining a wrapper rather than treating it as a cosmetic edit.

### 7.4. Naming Conventions

Teams often standardize on a `p_` prefix for inputs such as `p_order_id` or `p_discount_pct` and keep them stable once the public API is released. Even if current callers use positional arguments, future clients may adopt named notation.

## 8. CREATE OR REPLACE FUNCTION: What Is Preserved?

Syntax:

~~~sql
CREATE OR REPLACE FUNCTION api_lab.some_function(
    p_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT ...
$$;
~~~

When a function **already exists with the same identity and a compatible result type**, `CREATE OR REPLACE` updates its definition **without dropping the function first**.

### 8.1. Biggest Benefit: Preserving Object Identity

For an existing overload, `CREATE OR REPLACE` generally preserves the function's OID, ownership, and previously granted privileges; dependent objects bound to the existing function do not need to be dropped just to replace the body.

### 8.2. Modifying the Function Body

For example, changing the internal calculation formula while still accepting `bigint` and returning `numeric`, or updating the inner query:

~~~sql
CREATE OR REPLACE FUNCTION api_lab.order_total(
    p_order_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT round(
        o.quantity * p.unit_price,
        2
    )
    FROM api_lab.orders AS o
    JOIN api_lab.products AS p
      ON p.product_id = o.product_id
    WHERE o.order_id = p_order_id
$$;
~~~

This keeps the exact signature `order_total(bigint)` and the same result type.

### 8.3. Do Not Assume Semantic Changes Are Safe

A new body can change `NULL` handling, exceptions, rounding, timezones, or which tables are accessed. Even if PostgreSQL accepts `REPLACE` as valid DDL, the **application contract** may still break.

### 8.4. Modify Function Attributes Carefully

`VOLATILE`/`STABLE`/`IMMUTABLE`, `STRICT`, `SECURITY DEFINER`, and function-level `SET search_path` settings affect query plans, privileges, and runtime results. Never change them purely for "optimization" without verifying the exact semantics.

## 9. CREATE OR REPLACE Does Not Change Identity

Suppose the original function is:

~~~sql
api_lab.order_total(bigint) RETURNS numeric
~~~

You write:

~~~sql
CREATE OR REPLACE FUNCTION api_lab.order_total(
    p_order_id bigint,
    p_discount_pct numeric
)
RETURNS numeric
...
~~~

This statement **does not update the existing function object** for `order_total(bigint)`. Because the input type list differs, PostgreSQL treats it as a new function (a separate overload) if the declaration is valid.

### 9.1. The Old Function Still Remains

After the migration, the catalog may contain both:

~~~text
api_lab.order_total(bigint)
api_lab.order_total(bigint, numeric)
~~~

Applications passing one argument do not automatically switch to the two-argument function unless default arguments and overload resolution rules cause ambiguity or redirect resolution.

### 9.2. Do Not Expect to "Alter Returned Columns" In Place

Changing `RETURNS numeric` to `RETURNS TABLE(...)` changes the **result contract** and cannot be treated as a routine `REPLACE` of the same function.

### 9.3. RETURNS Is Not Part of Identity

The signature required for `DROP FUNCTION` and `ALTER FUNCTION` normally consists only of the identifying input parameter types. A different return type never creates a second overload with the same input types.

## 10. Changing the Return Type: Migrations Must Be Planned

A function declared as `RETURNS numeric` cannot be changed directly to `RETURNS text` using `CREATE OR REPLACE` for the same signature:

~~~sql
-- INTENTIONALLY INVALID example for a function already returning numeric:
--
-- CREATE OR REPLACE FUNCTION api_lab.order_total(bigint)
-- RETURNS text ...
~~~

PostgreSQL rejects changing the return type in this manner.

### 10.1. Multi-Column Return Types Are Also Contracts

~~~sql
CREATE FUNCTION api_lab.order_summary(
    p_order_id bigint
)
RETURNS TABLE (
    order_id bigint,
    total numeric
)
LANGUAGE sql
STABLE
AS $$
    SELECT o.order_id, (o.quantity * p.unit_price)::numeric
    FROM api_lab.orders AS o
    JOIN api_lab.products AS p
      ON p.product_id = o.product_id
    WHERE o.order_id = p_order_id
$$;
~~~

Changing `RETURNS TABLE(order_id bigint, total numeric)` to add a `currency text` column alters the output contract and can break views, client mappings, or calling functions.

### 10.2. A More Compatible Approach

Keep v1 `order_summary(bigint)` and create:

~~~text
api_lab.order_summary_v2(bigint)
    -> (order_id bigint, total numeric, currency text)
~~~

Applications migrate gradually to v2. Only after confirming no v1 callers or dependencies remain should v1 cleanup be considered.

### 10.3. Same-Family Type Changes Still Require Review

Changing `numeric` to `numeric(12,2)`, `integer` to `bigint`, or `jsonb` to `text` requires inspecting exact function declarations, casts, and output records; never assume similar-looking types leave the contract unaffected.

### 10.4. Do Not Rush into DROP/CREATE

`DROP FUNCTION` may be blocked by dependencies or, with `CASCADE`, delete objects you intended to keep. Moreover, recreating a function assigns a new OID and requires reassessing privileges, ownership, and defaults.

## 11. Dependencies: Why Does the Database Track Them?

PostgreSQL stores dependency metadata for many objects in system catalogs to:

- Prevent dropping an object while another object still depends on it.
- Determine which objects would be dropped transitively under `CASCADE`.
- Protect data types, schemas, functions used in expressions, views/rules, and other recorded relationships.

For example:

~~~text
VIEW v_order_totals
    |
    +---- depends on function order_total(bigint)
                  |
                  +---- references tables orders, products in SQL body
~~~

However, **the second arrow is not always fully recorded in the catalog**, depending on how the function body is written and its language. This is a critical point.

### 11.1. What Is a Dependent Object?

Examples include a view calling the function, an expression index using the function, a constraint or generated expression calling the function, or an object type used in the signature.

### 11.2. Not Every Call Is a Catalog Dependency

An SQL query inside Java source code, migration files, job schedulers, or stored text/dynamic SQL is not tracked by PostgreSQL as a "dependent object" that can be enumerated completely via `pg_depend`.

### 11.3. Never Conclude All Callers Are Known Just by Checking pg_depend

`pg_depend` is a strong tool for inspecting catalog-recorded dependencies, but real migrations must **also** check other functions, application code, dynamically generated SQL, jobs/reports, and permissions.

## 12. Building a Reproducible Dependency Lab

The following examples use a fresh lab schema on a test database. Never run `DROP ... CASCADE` against production objects.

### 12.1. Create Schema and Tables

~~~sql
CREATE SCHEMA api_lab;

CREATE TABLE api_lab.products (
    product_id bigint PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    unit_price numeric(12,2) NOT NULL
        CHECK (unit_price >= 0)
);

CREATE TABLE api_lab.orders (
    order_id bigint PRIMARY KEY,
    product_id bigint NOT NULL
        REFERENCES api_lab.products(product_id),
    quantity integer NOT NULL
        CHECK (quantity > 0),
    order_status text NOT NULL
        CHECK (order_status IN ('new', 'paid', 'cancelled'))
);
~~~

### 12.2. Insert Sample Data

~~~sql
INSERT INTO api_lab.products (product_id, sku, unit_price)
VALUES
    (10, 'SKU-A', 100.00),
    (20, 'SKU-B',  50.00),
    (30, 'SKU-C',  20.00);

INSERT INTO api_lab.orders (
    order_id, product_id, quantity, order_status
)
VALUES
    (1001, 10, 2, 'paid'),
    (1002, 20, 3, 'paid'),
    (1003, 30, 1, 'new'),
    (1004, 10, 1, 'cancelled');
~~~

### 12.3. Create the v1 Function

~~~sql
CREATE FUNCTION api_lab.order_total(
    p_order_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT (o.quantity * p.unit_price)::numeric
    FROM api_lab.orders AS o
    JOIN api_lab.products AS p
      ON p.product_id = o.product_id
    WHERE o.order_id = p_order_id
$$;
~~~

Notes:

- `STABLE` is appropriate here because the query reads tables using the statement snapshot and has no side effects.
- This function is not `IMMUTABLE` because its result depends on mutable table data.
- If no matching order exists, a scalar SQL function returning no rows returns SQL `NULL` in this case.
- Schema-qualified table names are used inside the function body so it does not depend on `search_path` for the two source tables.

### 12.4. Test the v1 Function

~~~sql
SELECT
    api_lab.order_total(1001::bigint) AS order_1001,
    api_lab.order_total(1002::bigint) AS order_1002,
    api_lab.order_total(1003::bigint) AS order_1003;
~~~

Expected output:

| order_id | total |
| ---: | ---: |
| 1001 | 200.00 |
| 1002 | 150.00 |
| 1003 | 20.00 |

### 12.5. Create a View Calling the Function

~~~sql
CREATE VIEW api_lab.v_order_totals AS
SELECT
    o.order_id,
    o.order_status,
    api_lab.order_total(o.order_id) AS order_total
FROM api_lab.orders AS o;
~~~

~~~sql
SELECT *
FROM api_lab.v_order_totals
ORDER BY order_id;
~~~

This view serves as an important **dependent object** when testing `DROP FUNCTION`.

## 13. Identifying Functions Precisely with regprocedure

PostgreSQL provides the OID alias type `regprocedure` to distinguish functions by name and input type list.

~~~sql
SELECT
    'api_lab.order_total(bigint)'::regprocedure
        AS function_identity;
~~~

### 13.1. to_regprocedure Avoids Exceptions When Missing

~~~sql
SELECT
    to_regprocedure(
        'api_lab.order_total(bigint)'
    ) AS existing_function;
~~~

When no matching routine is found, `to_regprocedure` returns SQL `NULL` for valid lookup inputs, which is convenient for pre-migration verification scripts.

### 13.2. Difference from regproc

`regproc` represents a function name without distinguishing overloads by argument types. For APIs with multiple overloads, `regprocedure` is usually more appropriate.

### 13.3. Full Type List

Referencing an overload with `numeric` instead of `integer`:

~~~sql
SELECT
    to_regprocedure('api_lab.apply_rate(numeric,numeric)');
~~~

For a function with default parameters, still specify the **full input type list** in its identity.

## 14. Listing Functions in pg_proc

`pg_proc` stores metadata for functions, procedures, and related routine kinds.

~~~sql
SELECT
    p.oid::regprocedure AS routine,
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind,
    pg_get_function_identity_arguments(p.oid)
        AS identity_arguments,
    pg_get_function_result(p.oid)
        AS result_type
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'api_lab'
ORDER BY p.proname,
         pg_get_function_identity_arguments(p.oid);
~~~

### 14.1. Key Columns to Know

| Attribute | Meaning |
| --- | --- |
| `oid` | Catalog identifier of the routine |
| `pronamespace` | Schema containing the routine |
| `proname` | Routine name |
| `prokind` | Catalog code distinguishing function/procedure/aggregate/window |
| `proargtypes` | Input argument types stored in catalog |
| `proallargtypes` | All argument types when needed (including output) |
| `proargmodes` | Argument modes, if present |
| `proargnames` | Argument names |
| `proargdefaults` | Default value expressions for input arguments |
| `prorettype` | Result type |
| `provolatile` | Volatility classification |
| `prosecdef` | Whether `SECURITY DEFINER` is enabled |
| `proparallel` | Declared parallel safety |

### 14.2. prokind

Common `prokind` values used to classify routines:

~~~text
f = function
p = procedure
a = aggregate
w = window function
~~~

In this lesson, filter with `prokind = 'f'` when listing only functions.

### 14.3. Do Not Infer Contracts from Name Alone

If multiple `order_total` routines exist, display `oid::regprocedure` or `pg_get_function_identity_arguments`, never just `proname`.

## 15. pg_get_function_identity_arguments vs. pg_get_function_arguments

These two catalog functions serve slightly different purposes:

~~~sql
SELECT
    p.oid::regprocedure AS routine,
    pg_get_function_identity_arguments(p.oid)
        AS identity_args,
    pg_get_function_arguments(p.oid)
        AS declaration_args,
    pg_get_function_result(p.oid)
        AS return_type
FROM pg_proc AS p
WHERE p.oid = 'api_lab.order_total(bigint)'::regprocedure;
~~~

### 15.1. Identity Arguments

`pg_get_function_identity_arguments` formats the argument list suitable for commands such as `ALTER FUNCTION` or `DROP FUNCTION`, excluding default expressions.

### 15.2. Declaration Arguments

`pg_get_function_arguments` formats the parameter declaration list including names, modes, and defaults — useful for reviewing the **complete API contract**.

### 15.3. Function Result

`pg_get_function_result` returns the declared result type (for example `numeric` or `TABLE(...)`).

### 15.4. Why Check Both?

A migration might compare only identity arguments and miss changes to:

- Parameter names used by named notation.
- Default values.
- Output columns/fields.

These changes can still affect clients even when the input type list stays identical.

## 16. Extracting Function DDL with pg_get_functiondef

~~~sql
SELECT pg_get_functiondef(
    'api_lab.order_total(bigint)'::regprocedure
);
~~~

This function reconstructs the SQL definition matching the catalog object.

### 16.1. Reviewing the Contract Before Migration

Keep a snapshot of the DDL from source control or the catalog so you can verify:

- Current function body.
- Return type.
- Volatility, strictness, and security attributes.
- Function-level `SET` configuration parameters.
- Language (`sql`, `plpgsql`, etc.).

### 16.2. pg_get_functiondef Is Not Source Control

The catalog reflects the live state in the database, not why a change was made, which ticket approved it, or which applications depend on it. Version-controlled migration scripts remain essential.

### 16.3. Privileges and Ownership Are Separate Metadata

The DDL of the function body does not replace checking `ALTER OWNER`, `GRANT/REVOKE`, and default privileges. When creating a replacement function, plan how those attributes will be reapplied.

## 17. pg_depend: Inspecting Recorded Dependencies

`pg_depend` stores dependency relationships among PostgreSQL-managed objects.

### 17.1. Finding Objects That a Function Depends On

~~~sql
SELECT
    d.deptype,
    d.refclassid::regclass AS referenced_catalog,
    pg_describe_object(
        d.refclassid,
        d.refobjid,
        d.refobjsubid
    ) AS referenced_object
FROM pg_depend AS d
WHERE d.classid = 'pg_proc'::regclass
  AND d.objid =
      'api_lab.order_total(bigint)'::regprocedure
ORDER BY referenced_catalog::text, referenced_object;
~~~

For example, you may see dependencies on the schema, parameter/result types, and related catalog objects.

### 17.2. Why Aren't orders and products Fully Listed?

A string-based SQL function body:

~~~sql
LANGUAGE sql
AS $$
    SELECT ... FROM api_lab.orders ...
$$;
~~~

has limitations regarding dependency tracking for tables and functions referenced **inside the string body**. Not seeing a table in the query output above **does not prove** the function does not use that table.

### 17.3. Dependency Types

`deptype` indicates the kind of dependency (normal, automatic, internal, extension-related, etc.). Do not assume every entry represents a relationship that can simply be dropped; `DROP` behavior depends on the object types and dependency kinds.

### 17.4. The Catalog Is a Starting Point, Not a Complete Caller List

Java applications, external reports, dynamic SQL, trigger/procedure bodies without full dependency tracking, and configuration tables containing SQL strings must all be audited separately through change management.

## 18. View Dependencies on Functions

Views rely on rewrite rules; references to functions inside a view expression are typically recorded via `pg_rewrite` and `pg_depend`.

~~~sql
SELECT
    c.oid::regclass AS dependent_view,
    r.rulename AS rewrite_rule,
    d.deptype,
    pg_describe_object(
        d.refclassid,
        d.refobjid,
        d.refobjsubid
    ) AS referenced
FROM pg_depend AS d
JOIN pg_rewrite AS r
  ON r.oid = d.objid
JOIN pg_class AS c
  ON c.oid = r.ev_class
WHERE d.classid = 'pg_rewrite'::regclass
  AND d.refclassid = 'pg_proc'::regclass
  AND d.refobjid =
      'api_lab.order_total(bigint)'::regprocedure
ORDER BY dependent_view::text;
~~~

You should see a dependency from the rewrite rule of `api_lab.v_order_totals` to the function.

### 18.1. Dependencies Are Typically Bound by OID

A view stores a reference to the function's OID inside its parsed expression tree, so `CREATE OR REPLACE FUNCTION` with the same identity keeps the reference working.

### 18.2. Renaming a Function and OIDs

`ALTER FUNCTION ... RENAME TO` changes the **name** without creating a new routine. Objects bound by OID continue to be tracked by PostgreSQL, whereas application SQL calling the **old name** will fail after the rename.

### 18.3. Not Every Dependent Object Is a View

Expression indexes, generated columns, check constraints, default expressions, RLS policies, and other objects can reference functions. When investigating a risky change, inspect dependencies across all `classid` types, not only `pg_rewrite`.

## 19. SQL Function Bodies: Two Syntaxes and Dependency Tracking

PostgreSQL supports declaring SQL functions with a **string literal** body and (in supported versions) a **SQL-standard body** parsed at definition time.

### 19.1. String-Literal Body

~~~sql
CREATE FUNCTION api_lab.product_price_string(
    p_product_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT unit_price
    FROM api_lab.products
    WHERE product_id = p_product_id
$$;
~~~

With this syntax, direct dependency tracking to tables referenced in the SQL body can be incomplete. PostgreSQL does not automatically record catalog dependencies for every table named inside a string literal.

### 19.2. SQL-Standard Function Body

In PostgreSQL versions that support SQL-standard function bodies:

~~~sql
CREATE FUNCTION api_lab.product_price_sql_body(
    p_product_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
BEGIN ATOMIC
    SELECT unit_price
    FROM api_lab.products
    WHERE product_id = p_product_id;
END;
~~~

The body is parsed at creation time and can record direct dependencies on referenced objects such as the `api_lab.products` table.

### 19.3. When to Use SQL-Standard Bodies

They are helpful when stricter dependency tracking is desired and when you want invalid object references caught immediately at function creation time. However, syntax rules, limitations, and target PostgreSQL version compatibility must be verified in your deployment pipeline.

### 19.4. Do Not Assume PL/pgSQL Tracks Dependencies Like SQL-Standard Bodies

PL/pgSQL bodies are stored and executed differently, supporting both static and dynamic SQL. Never rely solely on `pg_depend` to assume you have found every table or function referenced inside PL/pgSQL statements.

### 19.5. Dynamic SQL Almost Always Requires Extra Review

For example:

~~~sql
EXECUTE format(
    'SELECT count(*) FROM %I.%I',
    v_schema, v_table
);
~~~

Because table names are constructed at runtime, the catalog cannot enumerate a fixed set of targets from the routine definition alone.

## 20. Checking Dependencies Before Modifying a Function

An audit plan should include two layers:

**Layer 1 — catalog dependencies:**

- `pg_depend`, `pg_rewrite`, `pg_proc`, `pg_class`, and related system catalogs.
- `to_regprocedure` for specific signatures.
- `pg_get_functiondef` to capture the current state.

**Layer 2 — callers outside catalog metadata:**

- Java/JDBC, ORM layers, and SQL stored in repositories.
- Migration and seed scripts.
- Scheduled jobs and BI dashboards/reports.
- Dynamic SQL and indirect call strings.
- Named-argument calls, overload resolution, and type casts.

### 20.1. Do Not Search Only by Routine Name

Searching for `order_total` may match the wrong overload or miss calls qualified under another schema name. You must map the **full set of exposed signatures**, not just a name string.

### 20.2. Avoid Blind Search-and-Replace

Blindly renaming strings in source code can alter UI text, non-SQL literals, or unrelated overloads. Migrations must verify call sites by argument types and context and coordinate application releases.

### 20.3. When External Clients Are Outside Your Control

If a function is a public API used by external services or partners, retiring v1 requires a deprecation period plus metrics from connection and statement logs, because catalogs cannot tell which external clients still call the legacy routine.

## 21. DROP FUNCTION and RESTRICT

Common syntax:

~~~sql
DROP FUNCTION api_lab.order_total(bigint) RESTRICT;
~~~

`RESTRICT` is the safe default so PostgreSQL refuses to delete dependent objects it tracks.

### 21.1. Lab with a Dependent View

Because `api_lab.v_order_totals` calls `api_lab.order_total(bigint)`, PostgreSQL blocks dropping the function when `RESTRICT` detects that dependency.

### 21.2. RESTRICT Does Not Protect External Callers

Even if `DROP ... RESTRICT` succeeds, a Java client calling that function name will fail at runtime because application calls are not `pg_depend` entries.

### 21.3. IF EXISTS Does Not Bypass Dependencies

~~~sql
DROP FUNCTION IF EXISTS api_lab.order_total(bigint)
RESTRICT;
~~~

`IF EXISTS` suppresses an error when the routine is absent, **it does not override dependency checks**.

### 21.4. Lab Environment

To observe the error safely, run a test drop inside a transaction or sandbox without risking shared objects. Never execute `DROP` in production just to "discover dependencies" when safer inspection workflows exist.

## 22. DROP FUNCTION CASCADE: Cascading Risks

~~~sql
-- Illustration ONLY; do not run this to force through a production migration.
DROP FUNCTION api_lab.order_total(bigint) CASCADE;
~~~

`CASCADE` instructs PostgreSQL to also drop all dependent objects identified by catalog dependency rules.

### 22.1. It Drops More Than One Function

In the lab, `v_order_totals` would be dropped because it depends on the function. Any objects that depend on that view would also be dropped in turn.

### 22.2. It Does Not Drop the Underlying Source Tables Read by the Function

If a function only reads `orders` and `products`, `DROP FUNCTION ... CASCADE` does not drop those source tables. Dependency direction and dependency type matter.

### 22.3. Trace the Full Impact Chain

For production objects, inventory:

- Dependent views, materialized views, and rules.
- Related expression indexes, constraints, and triggers.
- Other routines calling this interface.
- External clients.

Never use `CASCADE` as a shortcut to "fix a dependency error", because doing so can silently strip critical functionality from the system.

### 22.4. RESTRICT First, Explicit Migration Afterward

If an incompatible signature must change, it is usually far safer to **create v2 first**, migrate consumers, and then drop v1 with `RESTRICT` once no dependencies remain.

## 23. ALTER FUNCTION: Changing Attributes Without Changing Signature

`ALTER FUNCTION` modifies selected attributes of an existing function.

For example:

~~~sql
ALTER FUNCTION api_lab.order_total(bigint)
STABLE;
~~~

Or:

~~~sql
ALTER FUNCTION api_lab.order_total(bigint)
RENAME TO order_total_legacy;
~~~

**Note:** The `RENAME` example is shown for illustration only and **should not be run in the current lab** while subsequent steps still call `order_total`.

### 23.1. Renaming Does Not Create a New Overload

When renamed via `ALTER FUNCTION ... RENAME TO`, the routine keeps the same OID. However, applications calling the old name will not automatically follow the rename, making it a breaking change for callers.

### 23.2. Moving Between Schemas

~~~sql
-- Illustration only: target schema must exist.
ALTER FUNCTION api_lab.order_total(bigint)
SET SCHEMA another_schema;
~~~

This changes the qualified name used by callers; `search_path` and privileges on the target schema must also be checked.

### 23.3. Owner and Security

~~~sql
-- Illustration only; role must exist and have required privileges:
ALTER FUNCTION api_lab.order_total(bigint)
OWNER TO db_owner_role;
~~~

Changing the owner can alter effective privileges in `SECURITY DEFINER` routines or management permissions; never treat ownership changes as cosmetic.

### 23.4. ALTER FUNCTION Cannot Arbitrarily Change Input or Return Types

`ALTER FUNCTION` is not a general in-place mechanism to turn `order_total(bigint)` into `order_total(text)` or `RETURNS TABLE(...)`. That requires an API migration.

## 24. VOLATILE, STABLE, IMMUTABLE: The Planner Contract

PostgreSQL uses volatility categories to understand the guarantees a function provides.

| Attribute | Simple Meaning | Example |
| --- | --- | --- |
| `VOLATILE` | May return different results across calls and may have side effects | Reads wall-clock time, writes data |
| `STABLE` | Returns consistent results for the same arguments within a single statement under appropriate conditions | `SELECT` function reading tables under statement snapshot |
| `IMMUTABLE` | Result depends solely on inputs; never changes with database state, session, or time | Pure mathematical function |

### 24.1. Functions That Read Tables Are Not IMMUTABLE

~~~sql
api_lab.order_total(p_order_id bigint)
~~~

reads `orders` and `products`, so if table rows change, the total changes. Marking it `IMMUTABLE` just to "enable an index" violates the contract and can produce stale results due to planner assumptions, caching, or index corruption.

### 24.2. More Than Just Performance

Changing a function body from pure computation to reading tables may require updating its volatility. That change affects where the function is permitted (such as expression indexes or generated columns) and how the optimizer plans queries.

### 24.3. PARALLEL, STRICT, and Other Flags

- `STRICT` / `RETURNS NULL ON NULL INPUT` skips calling the body when any input is SQL `NULL`.
- `CALLED ON NULL INPUT` (default) lets the body handle `NULL` explicitly.
- `PARALLEL SAFE/RESTRICTED/UNSAFE` declares parallel execution constraints.
- `COST` and `ROWS` help the planner estimate execution cost where appropriate.

Changing these flags requires understanding the exact behavior of the body rather than copying annotations from another function.

## 25. EXECUTE Privileges and DROP/CREATE Risks

Function execution privileges are part of the contract.

~~~sql
-- Illustration only; application role must exist.
GRANT EXECUTE
ON FUNCTION api_lab.order_total(bigint)
TO app_reader;
~~~

### 25.1. CREATE OR REPLACE vs. DROP Followed by CREATE

With the same function identity, `CREATE OR REPLACE` normally preserves the existing routine's privileges and ownership. If you `DROP` and then `CREATE`, the new routine gets a new OID, owner, and default privileges — it does not automatically inherit previous grants.

### 25.2. Default PUBLIC EXECUTE Behavior

By default, PostgreSQL grants `EXECUTE` on newly created functions to `PUBLIC` unless default privileges have been configured otherwise. A sensitive routine can become exposed if deployed first and revoked only later.

### 25.3. Create and Revoke Privileges in the Same Transaction

A safer deployment pattern for sensitive functions:

~~~sql
BEGIN;

-- CREATE FUNCTION ... here.

-- Revoke public execution on the new function.
-- REVOKE EXECUTE ON FUNCTION schema.func(types) FROM PUBLIC;

-- Grant only to authorized roles once created.
-- GRANT EXECUTE ON FUNCTION schema.func(types) TO app_role;

COMMIT;
~~~

Running these steps in a single transaction avoids exposing an unintended access window.

### 25.4. Schema Privileges Matter Too

To call a function inside a schema, a role typically needs `USAGE` on the schema in addition to `EXECUTE` on the function. Verify effective permissions end-to-end rather than checking only `GRANT EXECUTE`.

### 25.5. Default Privileges Require an Explicit Strategy

`ALTER DEFAULT PRIVILEGES` affects **future objects** created by the specified role according to PostgreSQL rules. Do not assume a schema-level setting automatically clears existing global defaults; design global and per-schema defaults explicitly.

## 26. SECURITY INVOKER vs. SECURITY DEFINER

By default, a function executes with the privileges of the caller (**SECURITY INVOKER**).

With `SECURITY DEFINER`, the function executes with the privileges of the **function owner** according to PostgreSQL rules. This is useful for encapsulating controlled operations, but it increases security risks if the function body or namespace resolution is unsafe.

### 26.1. A Safer Skeleton Example

~~~sql
CREATE FUNCTION api_lab.read_product_price(
    p_product_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, api_lab, pg_temp
AS $$
    SELECT p.unit_price
    FROM api_lab.products AS p
    WHERE p.product_id = p_product_id
$$;
~~~

This illustrates **pinning `search_path` to trusted schemas** and using schema-qualified table names; you must still audit the owner, grants, callers, RLS policies, and underlying data privileges.

### 26.2. Why Is search_path Dangerous?

If a `SECURITY DEFINER` function uses unqualified object names and a schema on `search_path` allows untrusted users to create objects, an attacker can hijack name resolution to redirect execution to a malicious object.

### 26.3. pg_temp and Function Lookup

The temporary schema requires careful placement in the `search_path` of `SECURITY DEFINER` functions. Placing `pg_temp` after trusted schemas is an important defensive pattern, though it **does not replace using schema-qualified names and auditing privileges**.

### 26.4. Dynamic SQL Inside Definer Functions

If a body constructs SQL from user input, use parameter binding (`EXECUTE ... USING`) and safe identifier quoting (such as `format('%I', ...)` when genuinely needed) to prevent SQL injection or identifier manipulation.

### 26.5. Changing Owner or Body Can Shift the Security Boundary

A `CREATE OR REPLACE` keeping the same signature while adding `SECURITY DEFINER`, removing `SET search_path`, or changing ownership to a high-privilege role can create a major security change even though SQL clients still call the same name.

## 27. Choosing the Right Change Strategy

When asked to "update a function", evaluate the request carefully:

| Change Request | Typical Appropriate Approach |
| --- | --- |
| Fix a body bug, same input/return contract | `CREATE OR REPLACE` with the same signature |
| Change volatility or supported attributes | `ALTER FUNCTION` / `CREATE OR REPLACE` with verification |
| Rename routine | `ALTER FUNCTION ... RENAME` and update callers, or keep a legacy wrapper |
| Add input parameter | New function/overload; evaluate defaults and ambiguity |
| Change input type | New function or new overload; migrate callers |
| Change return type | New v2 API, cutover, then retire v1 |
| Change column count/types in `RETURNS TABLE` | v2 API and dependent migration |
| Rename named input parameter | Treat as breaking change; introduce new API if needed |
| Contract change while many clients still call old version | Expand–migrate–contract |
| Remove unused function | Verify callers/dependencies, then `DROP ... RESTRICT` |

### 27.1. Do Not Measure Safety by Whether DDL Succeeds

A `CREATE OR REPLACE` succeeding **does not prove** client behavior and data contracts remain compatible.

### 27.2. Do Not Change Return Shapes Just to Add One Field

Adding a column can affect JDBC mappings, `SELECT * FROM function(...)`, record types, and dependent views. Introducing a v2 routine is usually much cleaner.

### 27.3. Preserve a Rollback Path

When multiple application versions run concurrently, never delete the old interface immediately after one service deploys successfully; workers, cron jobs, and older instances may still rely on it.

## 28. Versioning: Expand–Migrate–Contract

A proven rollout pattern:

~~~text
EXPAND
  - Create independent v2 function.
  - Keep v1 function running unchanged.
  - Grant privileges and create related indexes/objects.
         |
         v
MIGRATE
  - Roll out clients calling v2 in stages.
  - Monitor errors and behavior.
  - Allow v1 and v2 to coexist in parallel.
         |
         v
CONTRACT
  - Verify no clients still depend on v1.
  - Audit catalog, code, and job dependencies.
  - DROP v1 with RESTRICT once confirmed safe.
~~~

### 28.1. Why Not Change In Place?

In production environments, you may simultaneously have:

- An API server newly deployed on v2.
- Batch workers not yet restarted still calling v1.
- Mobile or partner clients calling SQL through an older gateway.
- Nightly scheduled reports.

Keeping v1 during the transition allows components to upgrade asynchronously.

### 28.2. Name-Based Versioning

~~~text
api_lab.order_total(bigint)                -- v1
api_lab.order_total_v2(bigint, numeric)    -- v2
~~~

Clear, easy to route, and straightforward to roll back.

### 28.3. Schema-Based Versioning

Another approach:

~~~text
api_v1.order_total(bigint)
api_v2.order_total(bigint, numeric)
~~~

Suitable when versioning an entire suite of routines together. However, schema grants, `search_path`, and deployment steps must be managed explicitly.

### 28.4. Overloading Is Not Inherently Versioning

Same-named overloads can make sense when representing **the same semantic operation** across different input types. When the contract changes substantially, an explicit `_v2` name is easier to observe and reduces ambiguity.

## 29. Creating order_total_v2 in the Lab

New requirement: compute order total with a percentage discount between 0 and 100.

### 29.1. Create an Independent v2 Function

~~~sql
CREATE FUNCTION api_lab.order_total_v2(
    p_order_id bigint,
    p_discount_pct numeric
)
RETURNS numeric
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_base numeric;
BEGIN
    IF p_discount_pct IS NULL
       OR p_discount_pct < 0
       OR p_discount_pct > 100 THEN
        RAISE EXCEPTION
            'Invalid discount percentage: %',
            p_discount_pct
            USING ERRCODE = '22023';
    END IF;

    SELECT
        (o.quantity * p.unit_price)::numeric
    INTO v_base
    FROM api_lab.orders AS o
    JOIN api_lab.products AS p
      ON p.product_id = o.product_id
    WHERE o.order_id = p_order_id;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    RETURN round(
        v_base * (1 - p_discount_pct / 100),
        2
    );
END;
$$;
~~~

Function v2 **does not call v1**; it reads directly from the source tables. This allows v1 to be refactored later into a wrapper calling v2 **without creating an infinite recursion loop**.

### 29.2. Test the Result

~~~sql
SELECT
    api_lab.order_total(1001::bigint)
        AS v1_full_price,
    api_lab.order_total_v2(
        1001::bigint,
        10::numeric
    ) AS v2_ten_percent_discount;
~~~

With the sample data:

~~~text
v1_full_price              = 200.00
v2_ten_percent_discount    = 180.00
~~~

### 29.3. Leave v1 Unchanged While Introducing v2

All views and clients calling `api_lab.order_total(bigint)` continue using v1 exactly as before.

### 29.4. Not-Found Handling

For a non-existent ID such as `999999`, the lab design returns SQL `NULL`. This contract choice must be documented explicitly: another system might require raising an exception or returning a composite result with a `found` flag.

### 29.5. Reject Invalid Inputs

`p_discount_pct < 0`, `> 100`, or SQL `NULL` raises an error. Never silently accept a 120% discount or turn a missing discount into a nullified amount.

## 30. Wrapping the Old Signature

Once v2 has been deployed and tested, the v1 signature can be preserved while delegating calculation to the new core logic with a 0% discount.

~~~sql
CREATE OR REPLACE FUNCTION api_lab.order_total(
    p_order_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT api_lab.order_total_v2(
        p_order_id,
        0::numeric
    )
$$;
~~~

### 30.1. Why Doesn't This Wrapper Recurse?

`order_total_v2` reads the source tables directly and **never calls `order_total`**. The call flow is:

~~~text
order_total(bigint)
        |
        v
order_total_v2(bigint,numeric)
        |
        v
orders JOIN products
~~~

If v2 called v1 to get the base amount, turning v1 into a wrapper around v2 would cause infinite recursion. This is a common refactoring trap.

### 30.2. The v1 Signature Is Preserved

The view `v_order_totals` and application SQL calling `order_total(bigint)` require no name changes.

### 30.3. Results Must Remain Compatible

With `p_discount_pct = 0`, v2 must return semantically identical results to v1. If v2 changes rounding, validation, or timezone handling, even a wrapper can introduce a breaking change without altering input/return types. **Semantic versioning** matters just as much as signature types.

### 30.4. Maintenance Overhead of Wrappers

Keeping legacy wrappers can add a small execution overhead and increase routine count. Even so, that cost is usually far smaller than breaking live clients with an abrupt contract change.

## 31. When to Use an Overload Instead of a _v2 Name?

If the new API simply adds another call form with the same meaning, you can define:

~~~sql
CREATE FUNCTION api_lab.order_total(
    p_order_id bigint,
    p_discount_pct numeric
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT api_lab.order_total_v2(
        p_order_id,
        p_discount_pct
    )
$$;
~~~

Now:

~~~sql
SELECT api_lab.order_total(1001::bigint);
SELECT api_lab.order_total(
    1001::bigint,
    10::numeric
);
~~~

provide two distinct signatures.

### 31.1. Avoid Adding DEFAULT to a New Overload Unnecessarily

If the two-argument overload declared `DEFAULT 0`, it would compete with the one-argument overload. In the lab, we **omit DEFAULT** so the two call forms remain unambiguous.

### 31.2. Risk Remains with Unknown and NULL Literals

Whenever additional overloads exist, uncast literals and SQL `NULL` can still produce unexpected resolution. Bind and cast parameters explicitly when calling from JDBC/ORM code.

### 31.3. Overloading Fits Best When Semantics Match

`order_total(bigint)` and `order_total(bigint, numeric)` represent two ways to request the same kind of result. If v2 returns `jsonb` or a multi-column table instead, a distinct `_v2` name is usually better.

### 31.4. Do Not Hide Breaking Changes Behind Overloading

If v2 changes how parameters are interpreted, adding an overload can mislead reviewers into thinking it is merely a convenience API. Document the contract and deprecation timeline clearly.

## 32. Renaming, Aliases, and Cutover

Suppose you want to rename `order_total` to `calculate_order_total`.

### 32.1. Direct Rename

~~~sql
-- Illustration only; do not run while lab examples still call the old name.
ALTER FUNCTION api_lab.order_total(bigint)
RENAME TO calculate_order_total;
~~~

Views bound by OID may continue working, but application SQL referencing `api_lab.order_total(1001)` will fail immediately because the old name no longer exists.

### 32.2. A Safer Path

1. Create `calculate_order_total(...)` with the target contract.
2. Keep `order_total(...)` delegating to the matching implementation.
3. Migrate applications in stages to the new name.
4. Remove the old name only after no callers or dependencies remain.

### 32.3. Avoid Surprise Schema Moves

Moving `api_lab.order_total` to `api_v2.order_total` breaks every caller using the old schema-qualified name. If callers use unqualified names, differences in `search_path` make cutover even harder to predict.

## 33. Removing v1 After Deprecation

Once you are confident no callers remain, a safe retirement procedure is:

1. Confirm v2 is actively serving traffic.
2. Verify application logs show v1 calls have stopped over a sufficiently long window.
3. Check database dependencies.
4. Update or remove any views, triggers, or scheduled jobs still referencing v1.
5. Run `DROP FUNCTION ... RESTRICT` with the exact signature.
6. If blocked, **stop and inspect the dependency**—never add `CASCADE` to force past it.
7. After dropping, monitor for `function ... does not exist` errors from any overlooked clients.

### 33.1. The Current Lab Still Has a Dependent View

`api_lab.v_order_totals` still calls v1. Before dropping v1, you must decide whether to update the view (to call v2 with 0 discount) or keep v1 as a compatibility wrapper.

### 33.2. CREATE OR REPLACE VIEW Cannot Solve Every Type Change

If the updated view query changes column names or types in ways disallowed by `CREATE OR REPLACE VIEW`, the view itself requires a versioned migration. Never assume every dependency can be swapped with a single statement.

### 33.3. Updating the View Without Changing Its Output Shape

~~~sql
CREATE OR REPLACE VIEW api_lab.v_order_totals AS
SELECT
    o.order_id,
    o.order_status,
    api_lab.order_total_v2(
        o.order_id,
        0::numeric
    ) AS order_total
FROM api_lab.orders AS o;
~~~

This preserves the existing columns and types while moving the dependency to v2. Keep in mind this is only **one step**; all other callers must still be audited.

### 33.4. Retrying DROP RESTRICT

Once all recorded dependents and external callers have been migrated, `DROP FUNCTION api_lab.order_total(bigint) RESTRICT` can succeed. Do not drop it while other lab exercises still use v1.

## 34. Versioning and Rollback in Migrations

A well-designed rollout defines both the forward path and the reverse path.

### 34.1. Deployment Sequence

~~~text
Database migration A:
  - CREATE order_total_v2
  - GRANT required privileges
  - Verify v2

Application deploy B:
  - Route a small percentage of clients to v2
  - Monitor errors, latency, and outputs

Application deploy C:
  - Migrate remaining clients
  - Keep v1 throughout the rollback window

Database migration D:
  - Deprecate and drop v1 once verified
~~~

### 34.2. Application Rollback

If deploy B fails, roll the application back to calling v1. This is only safe if you **have not dropped or incompatibly altered** the v1 function.

### 34.3. Database Rollback

If v2 contains a logic bug, you can use `CREATE OR REPLACE` on v2 with the same signature and return contract to fix it, or roll back DDL/definitions via your migration process. However, if v2 introduced side effects or modified table data, rolling back function code alone does not automatically undo data changes.

### 34.4. Long-Lived Older Application Sessions

Even after deployment completes, older workers, connection pools, or long-running jobs may continue calling v1. Allow a compatibility window long enough for your system's real lifecycle.

### 34.5. Down Migrations Are Not Always Safe

A schema migration that altered data types/structures or dropped columns may not be cleanly reversible. A rollback plan must state explicitly what is reversible and what requires backup restoration or data backfill.

## 35. Dependencies with Expression Indexes and Immutability

Suppose we create a pure function:

~~~sql
CREATE FUNCTION api_lab.normalize_sku(
    p_sku text
)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT lower(btrim(p_sku))
$$;
~~~

And create an index:

~~~sql
CREATE INDEX idx_products_normalized_sku
ON api_lab.products (
    api_lab.normalize_sku(sku)
);
~~~

### 35.1. Indexes Depend on Functions

Because the index expression calls the function, PostgreSQL records a dependency on the function. Attempting `DROP FUNCTION ... RESTRICT` will be blocked by that index.

### 35.2. CREATE OR REPLACE Still Carries Risk

Suppose `normalize_sku` is modified to strip accents, change normalization rules, or adjust formatting. Even though the signature and return type stay the same, existing **index entries** were computed using the prior logic. You must plan a `REINDEX` (and document it in the migration) so index data reflects the new logic.

### 35.3. Stored Generated Columns May Need Backfill

If a stored generated column uses a function whose logic changes, updating the function definition alone does not automatically recompute **already stored column values**. Plan how stored values will be recomputed from source columns.

### 35.4. IMMUTABLE Is a Strict Promise

Never mark a function `IMMUTABLE` if it depends on tables or mutable configuration settings. Violating this contract can cause indexes or query plans to return stale or incorrect results.

## 36. Functions Used in Constraints and Generated Expressions

Some constraints invoke user-defined functions:

~~~sql
-- Illustration of validating SKU with a pure function.
-- CHECK (api_lab.valid_sku(sku))
~~~

### 36.1. Changing CHECK Function Logic Can Leave Old Rows "Invalid"

If `valid_sku` is tightened, rows accepted earlier may violate the new logic, yet PostgreSQL does not automatically rescan and revalidate the entire table simply because the function body changed.

### 36.2. Do Not Arbitrarily Read Other Tables Inside CHECK Functions

CHECK constraints are designed for row-level invariants. If a CHECK function reads another table, values can change without PostgreSQL knowing to recheck the constraint, causing logical inconsistencies and dump/restore failures. Use foreign keys or proper relational constraints instead.

### 36.3. Migrations Should Revalidate Data Explicitly

After tightening business rules, inspect existing rows and run explicit validation, backfill, or constraint migrations—do not rely solely on `CREATE OR REPLACE FUNCTION`.

### 36.4. Triggers Also Require Dependency Checks

Triggers are bound to trigger functions; dropping or altering the return contract or semantics of a trigger function can break `INSERT`/`UPDATE`/`DELETE` operations. Review trigger definitions as well as downstream systems such as CDC pipelines or background jobs.

## 37. Functions Used in VIEW and MATERIALIZED VIEW

Views commonly call functions and inherit column types from the declared output signature:

~~~sql
CREATE VIEW api_lab.v_order_totals AS
SELECT
    o.order_id,
    o.order_status,
    api_lab.order_total(o.order_id) AS order_total
FROM api_lab.orders AS o;
~~~

### 37.1. Regular Views Do Not Materialize Results

When a function body is updated with `REPLACE` while keeping the same contract, subsequent queries against a regular view use the updated logic.

### 37.2. Materialized Views Store Computed Rows

If a materialized view calls a function, replacing the function body does not update **already materialized rows**. Run `REFRESH MATERIALIZED VIEW` according to your operational schedule so stored results reflect the new logic.

### 37.3. Return Type Changes May Require Rebuilding Views

A view is parsed with the column type produced by the function. When changing a return type, update dependent views and contracts explicitly rather than expecting rewrite rules to adjust automatically.

### 37.4. Dependency Graphs Can Have Multiple Layers

~~~text
Function
   ^
   |
View A
   ^
   |
View B
   ^
   |
Materialized View C
~~~

Dropping a routine can cascade across multiple layers of views. Never run `DROP ... CASCADE` without understanding the full downstream impact.

## 38. Functions vs. Procedures: FUNCTION and PROCEDURE

PostgreSQL distinguishes between:

~~~sql
SELECT api_lab.order_total(1001::bigint);
~~~

and:

~~~sql
CALL api_lab.some_procedure(...);
~~~

### 38.1. FUNCTION

A function returns a value or result set and can be invoked as an expression in many SQL contexts.

### 38.2. PROCEDURE

A procedure is invoked with `CALL`. Under supported conditions and PostgreSQL versions, procedures can manage transactions within PostgreSQL limits. Do not treat `CALL` as mere syntactic sugar for `SELECT function(...)`.

### 38.3. Signatures and Versioning for Procedures

Procedures also have names, argument contracts, overloading, and DDL management, using `CREATE OR REPLACE PROCEDURE`, `ALTER PROCEDURE`, and `DROP PROCEDURE`. Always match the routine kind—never try to drop a procedure with `DROP FUNCTION`.

### 38.4. Shared Catalog pg_proc

`pg_proc.prokind` distinguishes functions (`f`) from procedures (`p`) when inspecting routine names that have multiple variants.

## 39. JDBC/Java: SQL Signatures as a Runtime Contract

In Java, you might use a `PreparedStatement`:

~~~java
String sql = "SELECT api_lab.order_total(?::bigint)";

try (PreparedStatement ps =
         connection.prepareStatement(sql)) {
    ps.setLong(1, orderId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal total = rs.getBigDecimal(1);
            // May be null if orderId does not exist.
        }
    }
}
~~~

### 39.1. Why Use an Explicit Cast?

`?::bigint` clearly identifies the expected overload on the PostgreSQL side. When multiple overloads exist, this avoids ambiguity caused by untyped bindings or driver parameter type variations.

### 39.2. BigDecimal for numeric

`numeric` should map to `BigDecimal` rather than `double` for monetary calculations. If v2 changes the return type to `jsonb` or a record, Java code calling `getBigDecimal` must be updated.

### 39.3. Parameter Metadata and Prepared Statements

Applications often cache prepared statements or use connection pooling. After DDL alters a signature or return shape, cached prepared statements may need re-preparation and can trigger cached-plan or result-type errors depending on the scenario.

### 39.4. Named Notation in Java SQL

If a query uses named notation:

~~~sql
SELECT api_lab.apply_rate(
    p_amount => ?::numeric,
    p_rate => ?::numeric
);
~~~

renaming `p_rate` immediately breaks that SQL statement even though the input types remain unchanged.

### 39.5. Track Caller Versions

When multiple application versions share the same database, record endpoint metrics or query names/versions in logs to determine whether v1 is still being called. System catalogs cannot tell you which Java services still depend on a function.

## 40. Default Values, NULLs, Errors, and Business Contracts

When incrementing versions, matching input and output types is not enough; edge cases must also be preserved or explicitly documented.

### 40.1. NULL Inputs

For a `STRICT` function:

~~~sql
CREATE FUNCTION api_lab.is_nonblank(
    p_text text
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT length(btrim(p_text)) > 0
$$;
~~~

PostgreSQL skips invoking the body when `p_text` is SQL `NULL` and returns `NULL`.

### 40.2. Non-STRICT Functions Can Handle NULL Explicitly

~~~sql
CREATE FUNCTION api_lab.is_nonblank_or_false(
    p_text text
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT coalesce(
        length(btrim(p_text)) > 0,
        false
    )
$$;
~~~

For SQL `NULL`, this returns `false`, which differs from the contract of `is_nonblank`.

### 40.3. Do Not Equate "Not Found" with "Zero"

In the lab, `order_total(9999)` returns SQL `NULL` when no order exists. Changing a new version to return `0` for a missing ID is a **semantic change** that can mask business bugs.

### 40.4. Exceptions Are Also Part of the Contract

V2 raises an exception with `SQLSTATE` `22023` for discounts outside `0..100`. A Java caller may catch that error code to return HTTP 400. If v3 changes it to return `NULL` or a different error, error-handling logic must be updated.

### 40.5. Maintain Stable Contract Documentation

API documentation should specify:

- Behavior when records are not found.
- Numeric types and precision/scale.
- Rounding rules.
- Timezone assumptions.
- SQL `NULL` handling.
- Exceptions and `SQLSTATE` codes.
- Whether side effects occur.

## 41. Dependencies Do Not Guarantee Visibility Into All Callers

Even when `pg_depend` shows zero dependent objects for a function, any of the following may still invoke it:

~~~text
Java source code
Spring Data native queries
jOOQ/ORM-generated SQL
Scheduled jobs / BI dashboards
Stored procedure dynamic EXECUTE statements
SQL literals stored in application configuration
ETL / CDC transformations
CLI scripts and notebooks
External partner integrations
~~~

### 41.1. Why Database Checks Alone Are Insufficient

No catalog relationship is automatically created simply because an external program *might* call a function later.

### 41.2. Even Database Functions Are Not Always Simple

PL/pgSQL bodies or string-based SQL bodies may not record dependencies for every object referenced inside the code. Dynamic SQL is especially hard to inventory automatically.

### 41.3. Combine Source-Level and Runtime Evidence

A reliable audit combines:

- Repository and migration script searches.
- Catalog queries.
- Controlled API/SQL query logging within security and overhead limits.
- Function/endpoint tracing.
- Canary deployments to detect incompatible call patterns early.

**Never conclude "safe to drop" solely from a zero row count in `pg_depend`.**

## 42. Transactional DDL and Rollback Limits

PostgreSQL supports executing many DDL statements inside transactions:

~~~sql
BEGIN;

-- CREATE OR REPLACE FUNCTION ...
-- GRANT / REVOKE ...
-- CREATE OR REPLACE VIEW ...

COMMIT;
~~~

### 42.1. Benefits

When related changes belong to the same group of objects and can run within a transaction, an error on any step lets you roll back uncommitted changes cleanly.

### 42.2. Transactions Do Not Solve Every Migration Challenge

Multi-service deployments, side effects modifying data, external caches, or background jobs are not automatically rolled back just because an SQL migration rolls back.

### 42.3. Long-Running Transactions

Holding a migration transaction open too long acquires locks that block other queries and DDL, degrading availability. Split slow steps into separate compatible phases.

### 42.4. Advisory or Migration Locks

Concurrent deployment workers attempting to run migrations can conflict. Your migration tool should coordinate locking so only one migration runner executes at a time.

## 43. CI/CD and Managing Function History

For systems relying heavily on functions, store function definitions and SQL migrations in version control.

Example logical layout:

~~~text
database/
  migrations/
    V001__create_orders.sql
    V012__create_order_total_v1.sql
    V025__add_order_total_v2.sql
    V030__switch_view_to_v2.sql
    V041__deprecate_order_total_v1.sql
  routines/
    order_total_v1.sql
    order_total_v2.sql
~~~

This structure is illustrative; actual migration frameworks may enforce different naming and ordering rules.

### 43.1. Split Migrations Into Independent Steps When Needed

Never combine adding v2, migrating every client, and dropping v1 in a single rollout if components cannot upgrade atomically.

### 43.2. Use Idempotent DDL Carefully

`CREATE OR REPLACE` makes certain migrations repeatable for the same signature, but it cannot change return types without breaking dependencies. `DROP IF EXISTS` prevents errors on missing objects, yet it does not guarantee safety for active clients or data.

### 43.3. Compare Signatures Before and After

Capturing `regprocedure` lists along with `pg_get_function_identity_arguments` and `pg_get_function_result` outputs before and after deployment helps catch unintended overloads or signature drift.

### 43.4. Privileges Are Part of the Migration

Always test using the actual application role (or a role with matching privileges), not just a superuser. A function that runs for a DBA but fails for the application role is a deployment bug.

### 43.5. Backward-Compatibility Tests

While v1 and v2 coexist, CI should verify:

- v1 queries still return expected data and column shapes.
- v2 queries handle new inputs and edge cases.
- Dependent views and procedures still run.
- Permissions suffice for the application role.
- Function-based indexes and constraints remain valid.

## 44. Observing Function Usage

Beyond source searches and `pg_depend`, PostgreSQL runtime statistics can help gauge function usage when configured appropriately.

### 44.1. pg_stat_user_functions

~~~sql
SELECT
    schemaname,
    funcname,
    calls,
    total_time,
    self_time
FROM pg_stat_user_functions
WHERE schemaname = 'api_lab'
ORDER BY calls DESC;
~~~

### 44.2. Do Not Assume Statistics Are Complete

Function tracking depends on settings such as `track_functions` and execution context; some functions (especially SQL functions inlined by the planner) may not increment counters as expected. Observing `calls = 0` **does not prove** no client depends on the function.

### 44.3. Observation Window Length

Counters can be reset and do not capture full historical usage. Before deprecating v1, observe metrics over a window long enough to cover infrequent jobs such as weekly or monthly reports.

### 44.4. Protect Sensitive Parameters in Logs

SQL logs may contain PII or financial data. Configure logging carefully to avoid capturing unnecessary sensitive values and enforce strict access and retention controls.

## 45. Common Design Mistakes

### Mistake 1. Thinking CREATE OR REPLACE Changes Parameter Types on the Same Function

Different input types create a new overload rather than replacing the old routine.

### Mistake 2. Thinking Return Types Distinguish Overloads

PostgreSQL does not permit two functions with the same input signature differing only by return type.

### Mistake 3. Renaming Input Parameters and Assuming It Is Non-Breaking

Named-argument callers depend on parameter names; `CREATE OR REPLACE` also restricts renaming existing named input parameters.

### Mistake 4. Adding DEFAULT to a New Overload Without Checking Ambiguity

Calls with fewer arguments may match multiple routines, especially when clients pass `unknown` literals or `NULL`.

### Mistake 5. Leaving JDBC Parameters Uncast

Ambiguous parameter types can pick the wrong overload or fail call resolution. Always bind and cast according to the contract.

### Mistake 6. Running DROP FUNCTION Without Input Types

When overloads exist, the name alone is insufficient; specify `function_name(type, ...)`.

### Mistake 7. Adding CASCADE to Silence Dependency Errors

`CASCADE` can silently destroy critical views, indexes, constraints, or other dependent objects.

### Mistake 8. Assuming pg_depend Shows Every Application Caller

Catalogs only track recorded database dependencies. Java/JDBC queries, dynamic SQL, and string bodies may not appear.

### Mistake 9. Assuming String SQL Bodies Track Dependencies Like SQL-Standard Bodies

Dependency parsing differs significantly. Never rely on a catalog query alone to assume you see every table a function reads.

### Mistake 10. Forgetting View Rewrite Dependencies

Views calling a function will cause `DROP ... RESTRICT` to fail; that failure is a safety guard, not something to bypass with `CASCADE`.

### Mistake 11. Renaming with ALTER and Forgetting Callers Using the Old Name

OID references remain valid, yet SQL strings in applications still use the routine name and will break.

### Mistake 12. Changing Schemas Without Updating Qualified Names

`api_lab.func` does not magically become `api_v2.func` inside Java queries or migration scripts.

### Mistake 13. Replacing the Body While Changing Semantics

`NULL` handling, rounding, timezones, and exceptions are part of the contract; skipping tests can cause subtle wrong results.

### Mistake 14. Marking Table-Reading Functions as IMMUTABLE

Table data can change; an inaccurate volatility label lets indexes or query plans rely on false assumptions.

### Mistake 15. Modifying an Index-Used IMMUTABLE Function Without REINDEX

Existing index entries were built with the old logic and are not automatically recomputed when the function body changes.

### Mistake 16. Forgetting Stored Generated Columns

Persisted values are not automatically recalculated when a referenced function's logic changes; backfill or recomputation is required.

### Mistake 17. Modifying SECURITY DEFINER Without Auditing search_path

An untrusted schema in name resolution can introduce privilege escalation or invoke unintended objects.

### Mistake 18. Losing Grants Through DROP/CREATE

Recreated functions receive new OIDs and default owner/ACLs; the app role may lose `EXECUTE` or `PUBLIC` may regain access unintentionally.

### Mistake 19. Assuming REPLACE Updates Privileges

`CREATE OR REPLACE` typically retains old ownership and grants; explicit `GRANT/REVOKE` or ownership changes are required to alter permissions.

### Mistake 20. Assuming Materialized Views Refresh Automatically After Function Updates

Materialized views persist rows from their last refresh; an explicit refresh is needed to apply updated function logic.

### Mistake 21. Making v1 Wrap v2 While v2 Calls Back Into v1

This creates unintended infinite recursion. Extract shared core logic or enforce an acyclic call graph.

### Mistake 22. Dropping v1 Immediately After One Deployment Wave

Older workers, scheduled jobs, or external clients may still rely on v1.

### Mistake 23. Dropping Based on pg_stat_user_functions calls = 0

Tracking configuration and observation windows have blind spots; zero recorded calls do not guarantee zero dependencies.

### Mistake 24. Running Migrations Only as Superuser

Doing so misses missing schema `USAGE`, function `EXECUTE`, or `SECURITY INVOKER` privileges required by the application role.

### Mistake 25. Labeling Functions with Side Effects as STABLE or IMMUTABLE

Incorrect volatility misleads the planner and violates execution semantics, causing surprising results in queries.

### Mistake 26. Assuming RESTRICT Catches External Dependencies

`RESTRICT` only guards against catalog-recorded dependencies, not external applications calling the routine.

### Mistake 27. Rolling Back DDL While Ignoring Data Side Effects

If v2 modified data or called external services, rolling back the function definition does not revert those effects.

### Mistake 28. Switching Scalar Returns to RETURNS TABLE Without Updating Clients

Changing return shapes breaks JDBC mappers, dependent views/functions, and SQL call sites.

### Mistake 29. Updating a CHECK-Constraint Function Without Revalidating Existing Rows

Existing rows may violate the updated rule; PostgreSQL does not rescan every row automatically when the function body changes.

### Mistake 30. Adding Overloads with Defaults Without Compatibility Tests

Positional, named, `NULL`, and `unknown` literal calls may resolve unexpectedly or fail with ambiguity errors.

## 46. Hands-On Exercises

These exercises build on `api_lab`. Exercises involving `DROP`, `RENAME`, or contract-breaking changes should be run in a separate copy of the lab database or written as illustrative SQL so you do not break later examples.

### Exercise 1. Function Identity

On what basis does PostgreSQL distinguish the two overloads `label_value(integer)` and `label_value(text)`?

### Exercise 2. Return Types

Can you create two `convert(integer)` functions in the same schema differing only by `RETURNS text` vs. `RETURNS numeric`?

### Exercise 3. IN and OUT

Why is an `OUT` parameter not sufficient to create two overloads with the same input parameters?

### Exercise 4. Default Arguments

How many input types belong to the identity of `apply_rate(numeric, numeric DEFAULT 10)`?

### Exercise 5. Named Arguments

Write a call to `apply_rate` using named notation with `amount = 100` and `rate = 7`.

### Exercise 6. Ambiguity

Explain the risk when the same schema contains both `tax(numeric)` and `tax(numeric, numeric DEFAULT 10)`.

### Exercise 7. Exact Overload

Write two calls to `label_value` using explicit `integer` and `text` casts.

### Exercise 8. regprocedure

Write an SQL query to retrieve the OID/identity of `api_lab.order_total(bigint)` without ambiguity across overloads.

### Exercise 9. to_regprocedure

Write a query checking whether a routine exists without raising an exception if it does not.

### Exercise 10. Catalog

Write an SQL query listing the name, identity arguments, and return type of all functions in `api_lab`.

### Exercise 11. Retrieving Function Definition

Write an SQL query to inspect the current DDL definition of `api_lab.order_total(bigint)`.

### Exercise 12. CREATE OR REPLACE

If only the rounding logic inside the body changes while input and return types stay identical, which approach should you use?

### Exercise 13. Adding an Input

If you add `p_discount_pct numeric` to `order_total(bigint)`, does PostgreSQL automatically replace the existing function?

### Exercise 14. Return Type

Can you run `CREATE OR REPLACE FUNCTION order_total(bigint) RETURNS text` directly on a function returning `numeric`?

### Exercise 15. Dependent Views

Write a query to find views using `api_lab.order_total(bigint)` via `pg_depend` and `pg_rewrite`.

### Exercise 16. SQL Bodies

Why can catalog dependencies differ between a string-based `AS $$ ... $$` SQL body and an SQL-standard `BEGIN ATOMIC ... END` body?

### Exercise 17. RESTRICT

What happens when running `DROP FUNCTION api_lab.order_total(bigint) RESTRICT` while `v_order_totals` still depends on it?

### Exercise 18. CASCADE

Explain why `DROP FUNCTION ... CASCADE` should not be used just to bypass dependency errors.

### Exercise 19. ALTER FUNCTION RENAME

Does renaming a function via `ALTER FUNCTION` automatically update Java application SQL strings calling the old name?

### Exercise 20. Privileges

What is the key difference regarding owner and `EXECUTE` privileges between `CREATE OR REPLACE` and `DROP + CREATE` on the same function?

### Exercise 21. SECURITY DEFINER

List two important practices to reduce risk when creating a `SECURITY DEFINER` function.

### Exercise 22. VOLATILITY

Why is `api_lab.order_total(bigint)`, which reads source tables, not `IMMUTABLE`?

### Exercise 23. v2 Function

Write a call computing order `1001` with a `10%` discount using `order_total_v2` and state the expected result.

### Exercise 24. Wrapper

Why must you ensure `order_total_v2` does not call back into v1 if v1 is rewritten as a wrapper around v2?

### Exercise 25. New Overload

Write an overload `order_total(bigint, numeric)` without default values that delegates to `order_total_v2`.

### Exercise 26. Expand–Migrate–Contract

Outline the deployment sequence when Java service A uses v1 and service B is about to adopt v2.

### Exercise 27. Index Expressions

If you modify the logic of `normalize_sku` used in an expression index, what action is required for the index?

### Exercise 28. Stored Generated Columns

Why does running `REINDEX` alone not necessarily update stored generated column values when function logic changes?

### Exercise 29. Materialized Views

Does a materialized view calling `order_total` automatically reflect an updated function body immediately after `CREATE OR REPLACE`?

### Exercise 30. PL/pgSQL Dynamic SQL

Why cannot `pg_depend` completely capture every table accessed through `EXECUTE format(...)`?

### Exercise 31. JDBC

Write a parameterized `SELECT` statement casting to `bigint` so a Java application resolves the intended overload reliably.

### Exercise 32. NULL Contract

What does `order_total(999999)` return in the lab? Why would changing it to return `0` be a breaking change?

### Exercise 33. pg_stat_user_functions

Does `calls = 0` prove no client still calls a function? Why or why not?

### Exercise 34. Procedures

What is the fundamental difference between `SELECT function(...)` and `CALL procedure(...)`?

### Exercise 35. Migration Rollback

If a v2 rollout fails, what conditions allow safely rolling the application back to v1?

### Exercise 36. Retiring a Function

Provide a concise checklist to verify before running `DROP FUNCTION ... RESTRICT` to retire v1.

## 47. Reference Solutions

### Exercises 1–4. Identity and Modes

Identity depends on schema, name, and input argument types. Return types do not distinguish overloads. `OUT` defines the result contract and does not create a distinct overload with identical input types. `apply_rate(numeric, numeric DEFAULT 10)` has two input types in its identity.

### Exercise 5. Named Notation

~~~sql
SELECT api_lab.apply_rate(
    p_rate => 7::numeric,
    p_amount => 100::numeric
);
~~~

### Exercise 6. Defaults and Overloads

Both the one-parameter function and the two-parameter function with a default can match a single-argument call. This is an ambiguity-prone design; use a new name or remove the competing overload after checking compatibility.

### Exercise 7. Explicit Casts

~~~sql
SELECT api_lab.label_value(42::integer);
SELECT api_lab.label_value('42'::text);
~~~

### Exercises 8–9. regprocedure

~~~sql
SELECT 'api_lab.order_total(bigint)'::regprocedure;

SELECT to_regprocedure(
    'api_lab.order_total(bigint)'
);
~~~

### Exercise 10. pg_proc

~~~sql
SELECT
    p.oid::regprocedure AS function_name,
    pg_get_function_identity_arguments(p.oid)
        AS input_identity,
    pg_get_function_result(p.oid) AS return_type
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'api_lab'
  AND p.prokind = 'f'
ORDER BY function_name::text;
~~~

### Exercise 11. Function DDL

~~~sql
SELECT pg_get_functiondef(
    'api_lab.order_total(bigint)'::regprocedure
);
~~~

### Exercises 12–14. REPLACE and Breaking Changes

When keeping identity and return type identical, use `CREATE OR REPLACE` to update the body. Adding an input type creates a new signature/overload. Changing return type from `numeric` to `text` is not directly supported by `CREATE OR REPLACE` for the same signature; introduce a new API and migrate callers and dependencies.

### Exercise 15. View Dependency

~~~sql
SELECT
    c.oid::regclass AS view_name
FROM pg_depend AS d
JOIN pg_rewrite AS r
  ON r.oid = d.objid
JOIN pg_class AS c
  ON c.oid = r.ev_class
WHERE d.classid = 'pg_rewrite'::regclass
  AND d.refclassid = 'pg_proc'::regclass
  AND d.refobjid =
      'api_lab.order_total(bigint)'::regprocedure;
~~~

### Exercise 16. Dependency Tracking

An SQL-standard body is parsed at definition time and can record direct dependencies. String-literal bodies, PL/pgSQL bodies, and dynamic SQL do not guarantee recording all referenced objects inside `pg_depend`.

### Exercises 17–18. DROP Behavior

`RESTRICT` refuses the drop while `v_order_totals` depends on the function. `CASCADE` can drop the view and other dependent objects; it should never be used just to force past an error.

### Exercise 19. Rename

No. SQL strings inside Java code are not automatically updated by PostgreSQL; you must keep a wrapper or deploy client updates using the new name.

### Exercise 20. Permissions

`CREATE OR REPLACE` normally preserves the existing function's OID, owner, and ACLs. `DROP/CREATE` creates a new object with ownership and permissions derived from the new creation statement and defaults; grants must be verified and reapplied.

### Exercise 21. Security

Use trusted schemas with a safe `SET search_path`, use schema-qualified object names, audit owner/privileges and inputs, and review dynamic SQL and security boundaries.

### Exercise 22. STABLE

Because results depend on mutable data in `api_lab.orders` and `api_lab.products`. `STABLE` is appropriate for reading under a statement snapshot; `IMMUTABLE` promises the result never changes for the same inputs under any circumstance.

### Exercise 23. v2

~~~sql
SELECT api_lab.order_total_v2(
    1001::bigint,
    10::numeric
);
~~~

Result with sample data: `180.00`.

### Exercise 24. Recursion

If v1 calls v2 and v2 calls v1, unintended infinite recursion occurs. V2 must contain independent core logic or call a third implementation that never loops back to the wrapper.

### Exercise 25. Overload Without Default

~~~sql
CREATE FUNCTION api_lab.order_total(
    p_order_id bigint,
    p_discount_pct numeric
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT api_lab.order_total_v2(
        p_order_id,
        p_discount_pct
    )
$$;
~~~

### Exercise 26. Migration

Create and grant privileges on v2 first; keep v1 running; deploy B calling v2; monitor metrics and errors; migrate A; inspect legacy jobs; only drop v1 after all callers have migrated and the dependency graph is cleared.

### Exercises 27–28. Indexes and Stored Values

Expression indexes containing previous function outputs may require `REINDEX` after logic changes. Stored generated columns contain **persisted physical values**: `REINDEX` on those columns does not recompute expressions from source columns; explicit backfill/recomputation is required.

### Exercise 29. Materialized Views

No. Materialized views persist data as of the last refresh; updating function logic does not update existing stored rows. Run `REFRESH MATERIALIZED VIEW` per operational policy.

### Exercise 30. Dynamic SQL

Table names are constructed at runtime, so there is no static set of target objects for the dependency tracker to record at routine creation time.

### Exercise 31. JDBC

~~~sql
SELECT api_lab.order_total(?::bigint);
~~~

The driver binds a value compatible with `bigint`.

### Exercise 32. NULL Contract

The v1 scalar SQL function returns SQL `NULL` for a missing order ID. Changing it to `0` can cause the application to mistake "order does not exist" for "order total is zero".

### Exercise 33. Statistics

No. `track_functions` may be disabled, functions can be inlined, statistics may have been reset, and infrequent callers may not have executed during the observation window. Combine code search, catalog checks, logs/metrics, and a deprecation window.

### Exercise 34. Procedures

Functions are invoked via `SELECT` or expressions and return values; procedures are invoked via `CALL` and support different semantics and transaction control under supported conditions.

### Exercise 35. Rollback

v1 still exists with unchanged privileges and compatible behavior; data and schemas were not modified in ways v1 cannot handle; and callers were not forced exclusively onto v2.

### Exercise 36. Checklist for Retiring v1

Confirm: callers in application code and jobs have migrated, metrics/logs cover a sufficiently long window, views/indexes/constraints/procedures no longer depend on v1, v2 is healthy with a rollback plan, and backups/DDL changes are controlled. Then run `DROP FUNCTION ... RESTRICT` with the exact signature; if blocked, investigate rather than adding `CASCADE`.

## 48. Quick Reference

| Task | Syntax / Tool |
| --- | --- |
| Call explicit overload | `api_lab.func(1::bigint)` |
| Identify routine by signature | `'schema.func(bigint)'::regprocedure` |
| Non-throwing lookup | `to_regprocedure('schema.func(bigint)')` |
| Get input identity | `pg_get_function_identity_arguments(oid)` |
| Get declared parameters | `pg_get_function_arguments(oid)` |
| Get return type | `pg_get_function_result(oid)` |
| Extract DDL | `pg_get_functiondef(oid)` |
| List routines | `pg_proc` + `pg_namespace` |
| Inspect catalog dependencies | `pg_depend`, `pg_rewrite` |
| Update body with same signature/return | `CREATE OR REPLACE FUNCTION` |
| Rename routine | `ALTER FUNCTION f(types) RENAME TO name` |
| Move schema | `ALTER FUNCTION f(types) SET SCHEMA schema` |
| Change owner | `ALTER FUNCTION f(types) OWNER TO role` |
| Safe drop checking dependents | `DROP FUNCTION f(types) RESTRICT` |
| Cascading drop (dangerous) | `DROP FUNCTION f(types) CASCADE` |
| Introduce new version | `CREATE FUNCTION ..._v2(...)` |
| Preserve legacy API | Compatibility wrapper with old signature |
| Avoid overload ambiguity | Avoid competing defaults; cast/bind explicitly |
| Revoke public execution | `REVOKE EXECUTE ON FUNCTION ... FROM PUBLIC` |
| Grant execution to app role | `GRANT EXECUTE ON FUNCTION ... TO role` |
| Security boundary | `SECURITY DEFINER` with safe `SET search_path` |
| Read-only table function | Usually consider `STABLE`, not `IMMUTABLE` |
| Function-based expression index | Plan `REINDEX` when body semantics change |
| Stored generated values | Backfill/recompute when referenced logic changes |
| Function-dependent MV | Refresh materialized data when needed |
| Procedure | `CALL` and `ALTER/DROP PROCEDURE` |
| Runtime function statistics | `pg_stat_user_functions` when tracking is enabled |

## 49. Production Function Change Checklist

1. **Have you verified the exact schema, name, and input types** of the routine to modify?
2. Have you reviewed `pg_get_functiondef`, return type, defaults, parameter names, and modes?
3. Are you modifying the **body**, **signature**, **return shape**, or **semantics**?
4. Do competing overloads exist because of defaults, `unknown` literals, or `NULL`?
5. Will renaming parameters affect callers using named notation?
6. Does `CREATE OR REPLACE` preserve the required OID, ACLs, and attributes?
7. Does the change affect volatility, `STRICT`, parallel safety, cost, or security?
8. Does `SECURITY DEFINER` have a safe owner, `search_path`, and schema-qualified names?
9. Have you listed catalog-recorded dependencies from `pg_depend` and view rewrite rules?
10. Have you audited source-level callers and dynamic SQL outside the catalog?
11. Have you checked triggers, indexes, constraints, and generated columns using the function?
12. If the function is used in an index, is `REINDEX` needed?
13. If the function feeds stored generated values or materialized views, is recomputation/refresh needed?
14. If the return type changes, is there a v2 API and caller migration plan?
15. Have schema `USAGE` and function `EXECUTE` grants been verified for each role?
16. Is there an overlap window where both v1 and v2 operate for rollback?
17. How long can older services or batch jobs continue running?
18. Are metrics and logs tracking resolution errors, query timeouts, and `SQLSTATE` codes?
19. Has CI tested positional, named, `NULL`, `unknown` literal, and default-argument calls?
20. Can the DDL migration execute inside a short, safe transaction?
21. Is rollback behavior clear if v2 mutates data?
22. Are a v1 deprecation schedule and consumer owners established?
23. Is `DROP ... RESTRICT` executed only after dependencies are resolved?
24. Is there a strict policy **never to add CASCADE** automatically when a migration errors?
25. Have you confirmed the target PostgreSQL version supports all planned syntax?

## 50. Summary

In PostgreSQL, a **function signature** is a core piece of the database interface: schema, name, and input parameter types identify overloads, while parameter names, defaults, modes, and return types can still affect callers even when they do not alter routine identity.

Remember five core principles:

1. **`CREATE OR REPLACE FUNCTION` is not a signature-changing command.** Different input types create a new overload. For the same identity, you cannot arbitrarily change the return type; a proper migration is required.
2. **Dependencies are directional and incomplete across external call sites.** `pg_depend` protects catalog-recorded objects, but string SQL bodies, PL/pgSQL dynamic SQL, Java/JDBC code, and external jobs are not fully cataloged.
3. **`DROP FUNCTION ... RESTRICT` is the default safety guard.** `CASCADE` can transitively destroy views, indexes, and constraints; never use it to bypass errors without understanding the full impact.
4. **Expand–migrate–contract versioning minimizes disruption.** Create v2, keep v1 or a wrapper running, migrate clients step by step, monitor for errors, and drop v1 only when no dependencies remain.
5. **The contract extends beyond data types.** Preserve or explicitly communicate changes to SQL `NULL` handling, exceptions, rounding, volatility, privileges, `SECURITY DEFINER`, index-derived values, and stored/materialized outputs.

Whenever asked to "just add a parameter" or "just change the return type", start with three questions: **"Will this still have the same PostgreSQL identity?", "Which dependent objects and callers require compatibility?", and "If deployment fails, can we safely fall back to the previous API?"**. Answering those three questions clearly before running DDL keeps function versioning safe, verifiable, and reversible.

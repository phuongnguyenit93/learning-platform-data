# Comparing SQL/PLSQL Scope Between 19c Systems and Newer Oracle Releases

Oracle Database 19c remains an important platform for production systems, yet the scope of SQL and PL/SQL has continued to expand across the 21c, 23ai, and 26ai releases. The differences go beyond just the number of new statements. Newer releases add data types, DDL/DML syntax, JSON representations, SQL-PL/SQL integration capabilities, optimizer features, and new application models.

When comparing, you must distinguish the **base release** from the **Release Update (RU)**. Several features have been backported to Oracle 19c in newer RUs. For example, SQL table macros have been available since 19c RU 19.7; IF EXISTS/IF NOT EXISTS syntax and schema annotations have been supported since 19c RU 19.28. Therefore, the statement "19c does not have IF NOT EXISTS" is only true for RUs prior to 19.28, not for every system running 19c.

This lesson uses Oracle Database 19c, 21c, 23ai, and Oracle AI Database 26ai documentation as benchmarks. The content focuses on:
- How to accurately read the version, RU, COMPATIBLE, and actual system capabilities.
- Differences between the SQL engine, PL/SQL engine, and cross-engine communication features.
- Evolution of SQL data types, especially BOOLEAN, JSON, and VECTOR.
- New DDL/DML: IF EXISTS, multivalue INSERT, VALUES constructor, JOIN in UPDATE/DELETE, and RETURNING.
- SQL macros, SQL Transpiler, extended PL/SQL CASE, and JSON aggregate mapping.
- SQL Domains, annotations, JSON-Relational Duality, and SQL Property Graph.
- Aggregation FILTER, GROUP BY ALL, GROUP BY alias/position, and 26ai enhancements.
- Impact on legacy applications, JDBC/clients, migration, testing, and compatibility strategies.

Examples are illustrative for Oracle Database 19c and later. Exact syntax, limitations, required RUs, and deployment feasibility also depend on the platform, configuration, COMPATIBLE, driver/client, edition, and licensing conditions. Before introducing new syntax into production, verify against the documentation for the exact installed release and RU.

## 1. Understanding Release Scope

### 1.1. 19c, 21c, 23ai, and 26ai

| Release Line | Role in Comparison | Notable Highlights |
| --- | --- | --- |
| Oracle Database 19c | Common baseline for existing systems | Stable SQL/PLSQL; many features added via RUs |
| Oracle Database 21c | Innovation release between 19c and 23ai | Scalar SQL macros, binary SQL JSON type, and many developer extensions |
| Oracle Database 23ai | Innovation release focused on developers and AI | SQL BOOLEAN, SQL Domains, multivalue INSERT, VALUES, JSON-Relational Duality, VECTOR, and many new SQL syntaxes |
| Oracle AI Database 26ai | Next Long Term Support release per 2026 Oracle documentation | Expands SQL/PLSQL, JSON, vector, SQL Transpiler, aggregation, and application integration |

Product names evolve over time. 23ai documentation may still appear under the name Oracle Database 23ai; 26ai documentation uses the name Oracle AI Database 26ai. When reading documentation, verify the release and document date, not just the marketing name.

### 1.2. Base Release Is Not the Whole Story

Oracle releases RUs periodically. A database may report 19c yet already include many syntaxes added in later RUs. Conversely, a system referred to as 23ai or 26ai might not yet have the RU required for a specific feature installed.

Important milestones in the 19c branch:
- From 19c RU 19.7: supports SQL table macros.
- From 19c RU 19.28: supports IF [NOT] EXISTS for documented DDL statements and schema annotations.
- RU 19.28 also adds the DBMS_DEVELOPER package to retrieve object metadata as a JSON CLOB.

When writing architecture documents or migration plans, record the full form: Oracle Database 19c RU 19.xx, 21c release, 23ai release/RU, or specific 26ai RU.

### 1.3. SQL and PL/SQL Have Different Scopes

SQL is a query and data manipulation language. PL/SQL is Oracle's procedural language, supporting variables, conditionals, loops, exceptions, packages, procedures, functions, and triggers.

A data type may exist in PL/SQL without being usable as a SQL column type. This is a classic example with BOOLEAN:
- In 19c, PL/SQL has BOOLEAN, but SQL does not yet have a native BOOLEAN column.
- Starting in 23ai, SQL has a native BOOLEAN type.
- In 26ai, interoperability between SQL BOOLEAN and PL/SQL BOOLEAN is expanded further.

Therefore, when reading feature documentation, ask: does the feature belong to SQL, PL/SQL, both, or is it solely a client/driver API?

## 2. Checking Version and RU on the System

### 2.1. Checking Version

~~~sql
SELECT banner
FROM v$version
ORDER BY banner;
~~~

You can view component information:

~~~sql
SELECT product, version, status
FROM product_component_version
ORDER BY product;
~~~

Some systems display different banners depending on deployment. Do not rely on the banner string alone to infer that all features are installed.

### 2.2. Checking RU/SQL Patches

DBAs can inspect SQL patch history:

~~~sql
SELECT
    patch_id,
    patch_type,
    action,
    status,
    action_time,
    description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
~~~

To determine the full RU and binary patches, combine SQL patch information with the Oracle Home inventory, such as OPatch lsinventory output collected by the DBA/OS administrator. Some patches are applied to the Oracle Home without completing datapatch; in that case, the binary state and SQL registry may be inconsistent.

### 2.3. Checking COMPATIBLE

~~~sql
SHOW PARAMETER compatible;
~~~

Or:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'compatible';
~~~

COMPATIBLE is a constraint on database format and capability compatibility. Some data types/features require a minimum COMPATIBLE value. For example, the native SQL JSON type in 21c requires an appropriate COMPATIBLE setting per the 21c documentation. Do not raise COMPATIBLE just to test syntax without evaluating downgrade capability, backups, and upgrade procedures.

### 2.4. Verify Capabilities Instead of Guessing by Release Name

The procedure for determining feature availability should be:
1. Confirm the database release.
2. Confirm the RU/patches.
3. Confirm COMPATIBLE.
4. Check feature documentation explicitly stating the supported release/RU.
5. Check privileges and configuration requirements.
6. Test the statement in a lab schema.
7. Verify whether clients, drivers, and frameworks recognize the new data type/syntax.

Do not rely on a statement like "running Oracle 19c" to conclude all 19c syntaxes are identical.

## 3. High-Level SQL/PLSQL Comparison Table

| Capability | Base 19c | Newer 19c RU | 21c | 23ai | 26ai |
| --- | --- | --- | --- | --- | --- |
| PL/SQL BOOLEAN | Yes | Yes | Yes | Yes | Yes, broader SQL interoperability |
| SQL BOOLEAN column | No | No | No | Yes | Yes, additional PL/SQL interoperability |
| SQL table macro | From RU 19.7 | Yes | Yes | Yes | Yes |
| SQL scalar macro | Not a base 19c capability | Check RU/docs | Yes | Yes | Yes |
| IF [NOT] EXISTS DDL | No in older RUs | From RU 19.28 for supported DDL | Yes per release | Yes | Yes |
| Schema annotations | No in older RUs | From RU 19.28 | Release-dependent | Yes | Yes, additional integration |
| Native SQL JSON data type | No | No | Yes | Yes | Yes, additional JSON features |
| SQL Domains | No | No | No | Yes | Yes, additional data use case domains |
| Multivalue INSERT | No | No | No | Yes | Yes |
| VALUES table constructor | Not with new syntax | No | No | Yes | Yes |
| SELECT omitting FROM | No | No | No | Yes | Yes |
| Alias in GROUP BY | No | No | Not with 23ai syntax | Yes | Yes plus position, HAVING, and GROUP BY ALL |
| RETURNING in static UPDATE/MERGE | Limited per older syntax | Limited per older syntax | Check release | Yes | Yes plus OLD/NEW capabilities on DML |
| Direct JOIN in UPDATE/DELETE | No | No | Not with 23ai syntax | Yes | Yes |
| SQL VECTOR | No | No | No | Yes | Yes; extended PL/SQL vector |
| JSON-Relational Duality View | No | No | No | Yes | Yes with many added features |
| PL/SQL-to-SQL SQL Transpiler | No | No | No | Not a baseline feature | Yes |
| Aggregate FILTER | No | No | No | No per 26ai docs | Yes |
| GROUP BY ALL | No | No | No | No | Yes |
| SUM/AVG for INTERVAL | Not in 19c scope | No | No | SQL docs note support from release 23 | Yes |

This table is a directional map, not a replacement for the SQL Language Reference. Some capabilities are backported via RUs or have deployment conditions. Rows marked "check release" must be verified for the specific patch.

## 4. BOOLEAN: From PL/SQL to SQL

### 4.1. Oracle 19c

PL/SQL 19c has a BOOLEAN type with three logical states: TRUE, FALSE, and NULL (unknown).

Valid PL/SQL example:

~~~sql
DECLARE
    l_enabled BOOLEAN := TRUE;
BEGIN
    IF l_enabled THEN
        DBMS_OUTPUT.PUT_LINE('Enabled');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Disabled or unknown');
    END IF;
END;
/
~~~

However, SQL 19c does not have a native BOOLEAN type for table columns. You cannot create a BOOLEAN column or use arbitrary BOOLEAN expressions in SQL. Applications typically simulate it with NUMBER(1), CHAR(1), or VARCHAR2 with a CHECK constraint.

~~~sql
CREATE TABLE feature_flags (
    flag_id NUMBER PRIMARY KEY,
    enabled NUMBER(1) NOT NULL,
    CONSTRAINT feature_flags_enabled_ck
        CHECK (enabled IN (0, 1))
);
~~~

### 4.2. Oracle 23ai

SQL has native BOOLEAN:

~~~sql
CREATE TABLE feature_flags (
    flag_id NUMBER PRIMARY KEY,
    enabled BOOLEAN DEFAULT FALSE NOT NULL
);

INSERT INTO feature_flags (flag_id, enabled)
VALUES (1, TRUE);

SELECT flag_id
FROM feature_flags
WHERE enabled = TRUE;
~~~

This allows the schema to clearly express logical meaning instead of having to standardize 0/1 or Y/N conventions across multiple applications.

BOOLEAN still uses three-valued logic. NULL is not FALSE; conditions can evaluate to UNKNOWN. Therefore, design NOT NULL/defaults carefully and test predicates in WHERE, CASE, JOIN, and constraints.

### 4.3. Oracle 26ai and PL/SQL Interoperability

26ai expands how BOOLEAN is used between SQL and PL/SQL:
- Stored PL/SQL functions with BOOLEAN parameters can be called directly from SQL with BOOLEAN expressions/literals per documented capabilities.
- BOOLEAN is supported in SELECT INTO and BULK COLLECT INTO cases in PL/SQL.
- Conversions exist between BOOLEAN and number/character along with related conversion functions.
- BOOLEAN is supported in binds, triggers, and certain interfaces such as OCI, dynamic SQL, and DBMS_SQL.
- PL/SQL can use BOOLEAN as a standalone scalar type in supported contexts.

26ai example:

~~~sql
CREATE OR REPLACE FUNCTION is_large_order(
    p_amount NUMBER
) RETURN BOOLEAN
IS
BEGIN
    RETURN p_amount >= 10000;
END;
/

SELECT is_large_order(15000) AS large_order
FROM dual;
~~~

In 23ai/26ai environments, verify SQL BOOLEAN and BOOLEAN PL/SQL interoperability by release. A function with a BOOLEAN return type or parameter may not run on 19c as written above.

### 4.4. 19c Compatibility Strategy

If the same application must run on both 19c and 23ai:
- Use NUMBER(1) or CHAR(1) as a shared data contract if a common schema is required.
- Or split schema migrations by version and convert at the repository layer.
- Do not put BOOLEAN columns into shared DDL if older 19c targets must parse that DDL.
- Use consistent API mapping in Java/.NET to avoid scattering 0/1/Y/N rules.
- Verify driver versions and metadata mapping when migrating to native BOOLEAN.

## 5. JSON: From Text to Data Type and Relational-Document Model

### 5.1. 19c

Oracle 19c can store JSON in VARCHAR2, CLOB, or BLOB, accompanied by an IS JSON constraint and SQL/JSON functions such as JSON_VALUE, JSON_QUERY, JSON_EXISTS, and JSON_TABLE.

Example:

~~~sql
CREATE TABLE api_events (
    event_id NUMBER PRIMARY KEY,
    payload CLOB CHECK (payload IS JSON)
);

SELECT
    JSON_VALUE(payload, '$.eventType') AS event_type
FROM api_events;
~~~

JSON is stored as text/serialized data in these column types. 19c has extensive JSON processing capabilities, but lacks the native SQL JSON data type introduced in 21c.

### 5.2. 21c

21c introduces a dedicated SQL JSON data type that stores data in a binary JSON format. This type processes nested JSON more efficiently and reduces repeated text parsing.

Illustrative example:

~~~sql
CREATE TABLE event_documents (
    event_id NUMBER PRIMARY KEY,
    payload JSON
);
~~~

Usability of the JSON type depends on COMPATIBLE per the release requirements. When upgrading from 19c, check whether applications, drivers, and export/import tools support the native JSON type.

### 5.3. 23ai and JSON-Relational Duality

JSON-Relational Duality Views allow applications to read/update relational data as JSON documents. The data remains stored in normalized relational tables; the duality view provides an updatable document view.

Benefits:
- Document-oriented applications can work with JSON.
- SQL applications still access relational data.
- Both views share a single source of truth.
- Reduces the need to hand-write multiple JSON-to-relational translation layers.

A duality view does not mean the database turns every table into a document store. You must design mappings, keys, relationships, update semantics, and access privileges according to the documentation.

### 5.4. 26ai and JSON/PLSQL Extensions

26ai extends the JSON constructor and JSON_VALUE to work with PL/SQL aggregate types such as records and collections. The JSON constructor can create JSON objects/arrays from aggregates; JSON_VALUE can map JSON back to aggregate types via RETURNING.

This enables data exchange between PL/SQL and JSON-consuming applications without manually serializing field by field with boilerplate code.

Conceptual example:

~~~sql
DECLARE
    TYPE employee_rec IS RECORD (
        employee_id NUMBER,
        employee_name VARCHAR2(100)
    );

    l_employee employee_rec;
    l_json JSON;
BEGIN
    l_employee.employee_id := 10;
    l_employee.employee_name := 'Lan';

    l_json := JSON(l_employee);
END;
/
~~~

This illustrates the direction of aggregate-to-JSON support; check specific overloads and JSON types in the 26ai PL/SQL Language Reference.

## 6. VECTOR and AI Vector Search

### 6.1. 19c/21c Scope

Oracle 19c and 21c do not have the SQL VECTOR data type following the AI Vector Search model of newer releases. To store embeddings in 19c, applications typically have to use BLOB, RAW, or a numeric/JSON representation and manage indexing/search logic themselves.

These workarounds are not equivalent to native vector indexing and similarity search.

### 6.2. 23ai

23ai introduces the VECTOR data type and AI Vector Search capabilities. Vectors store multi-dimensional numeric representations, typically embeddings of text, images, or other data. SQL can use vector distance/similarity and vector indexes per release capabilities.

Conceptual example:

~~~sql
CREATE TABLE document_embeddings (
    document_id NUMBER PRIMARY KEY,
    embedding VECTOR(3, FLOAT32)
);
~~~

The dimensions and format in the example are illustrative only. Choose dimensions, formats, and indexes based on your actual embedding model.

### 6.3. 26ai and PL/SQL VECTOR

26ai adds VECTOR support in PL/SQL as a distinct scalar type family. Subsequent 26ai RUs continue to expand:
- Support for BINARY vectors and Jaccard distance in corresponding RUs.
- Dimension-wise arithmetic in PL/SQL.
- SPARSE vectors in corresponding RUs.
- Vector operations and capabilities related to AI Vector Search.

For RAC or environments with specific patches, read RU notes and patch requirements. For example, 26ai documentation notes additional patch requirements for certain SPARSE vector cases in RAC.

## 7. DDL: IF [NOT] EXISTS and Annotations

### 7.1. IF NOT EXISTS in 19c RU 19.28

Older 19c RUs lacked this syntax for common DDL. Starting in RU 19.28, Oracle supports IF NOT EXISTS on documented CREATE statements, and IF EXISTS on supported ALTER/DROP statements.

Example:

~~~sql
CREATE TABLE IF NOT EXISTS migration_log (
    log_id NUMBER PRIMARY KEY,
    message VARCHAR2(200)
);
~~~

Drop example:

~~~sql
DROP TABLE IF EXISTS migration_log;
~~~

Do not assume every CREATE/ALTER/DROP statement supports it. Read the list of supported object types and restrictions in the SQL Language Reference for the exact RU. IF NOT EXISTS also cannot be arbitrarily combined with OR REPLACE in the same CREATE statement.

### 7.2. 23ai

23ai expands the DDL experience with IF [NOT] EXISTS as a developer productivity feature. Scripts can be written more idempotently and avoid some branches checking object existence before creating/dropping.

However, IF NOT EXISTS does not check whether the existing object has the desired structure. If the table already exists with wrong columns/constraints, the statement may leave it unchanged. Migrations still need metadata checks and schema drift detection.

### 7.3. Schema Annotations

Annotations are free-form metadata attached to objects or columns. They can be used to store display labels, descriptions, business owners, or metadata for developer tools.

Annotations are present in 23ai, but were also backported to 19c RU 19.28. Therefore, verify the RU when using them on 19c systems.

Example:

~~~sql
CREATE TABLE employee_notes (
    employee_id NUMBER,
    employee_name VARCHAR2(100)
)
ANNOTATIONS (purpose 'Employee master data');
~~~

Example attaching an annotation to a column:

~~~sql
ALTER TABLE employee_notes
MODIFY (employee_name ANNOTATIONS (display 'Employee name'));
~~~

Metadata can be read via views such as USER_ANNOTATIONS or USER_ANNOTATIONS_USAGE depending on the object and privileges. Annotations are metadata; they do not enforce validation or data security on their own.

### 7.4. SQL Domains

SQL Domains are data dictionary objects defining reusable domains with a data type and attributes/constraints. Starting in 23ai, domains help describe a shared business value type, such as email, postal code, or birth year.

Example:

~~~sql
CREATE DOMAIN email_address AS VARCHAR2(254)
    CONSTRAINT email_address_ck
    CHECK (REGEXP_LIKE(VALUE, '^[^@]+@[^@]+[.][^@]+$'));

CREATE TABLE application_users (
    user_id NUMBER PRIMARY KEY,
    email email_address
);
~~~

Domains reduce duplicate constraints across tables. However, verify domain behavior, metadata, Data Pump, and target compatibility when migrating back to 19c. Domain objects do not exist in standard 19c releases.

## 8. SELECT Without FROM and VALUES Constructor

### 8.1. SELECT in 19c

In 19c, queries returning only expressions commonly use DUAL:

~~~sql
SELECT SYSDATE FROM dual;
SELECT 10 * 20 AS result FROM dual;
SELECT SYS_CONTEXT('USERENV', 'CURRENT_USER') FROM dual;
~~~

### 8.2. SELECT in 23ai

23ai allows omitting FROM when no table needs to be read:

~~~sql
SELECT SYSDATE;
SELECT 10 * 20 AS result;
SELECT SYS_CONTEXT('USERENV', 'CURRENT_USER');
~~~

This is a small syntax change, yet it affects parsers and SQL generators in ORMs, query builders, reporting tools, and SQL-generating applications.

### 8.3. VALUES Constructor

23ai allows using a table value constructor to generate a small set of rows directly in SQL:

~~~sql
SELECT *
FROM (VALUES
    (10, 'HR'),
    (20, 'IT'),
    (30, 'FINANCE')
) departments(department_id, department_name);
~~~

This is useful for temporary lookups, ad-hoc queries, or small datasets embedded in a statement. Do not use a VALUES constructor in place of staging tables or bulk loads for large datasets.

### 8.4. Multivalue INSERT

Before 23ai, multiple INSERTs or INSERT ALL might have been required. 23ai allows multiple tuples in a single INSERT:

~~~sql
INSERT INTO departments (department_id, department_name)
VALUES
    (10, 'HR'),
    (20, 'IT'),
    (30, 'FINANCE');
~~~

The benefit is a single statement and a clearer transaction boundary for a group of tuples. For large loads, still evaluate array binding, direct path, external tables, or bulk loading instead of generating an oversized statement.

## 9. GROUP BY Alias, Position, and GROUP BY ALL

### 9.1. 19c

In 19c, you often had to repeat expressions:

~~~sql
SELECT
    TO_CHAR(order_date, 'YYYY') AS order_year,
    COUNT(*) AS order_count
FROM orders
GROUP BY TO_CHAR(order_date, 'YYYY');
~~~

### 9.2. 23ai

23ai allows referencing aliases in GROUP BY:

~~~sql
SELECT
    TO_CHAR(order_date, 'YYYY') AS order_year,
    COUNT(*) AS order_count
FROM orders
GROUP BY order_year;
~~~

This reduces expression duplication and makes queries easier to read. Watch out for aliases colliding with column names and alias scope within query blocks.

### 9.3. 26ai

26ai extends GROUP BY to support aliases or SELECT item positions in GROUP BY, GROUP BY CUBE, ROLLUP, GROUPING SETS, and alias support in HAVING. Additionally, GROUP BY ALL automatically groups by all non-aggregate expressions in the select list.

GROUP BY ALL example:

~~~sql
SELECT
    department_id,
    job_id,
    COUNT(*) AS employee_count,
    AVG(salary) AS average_salary
FROM employees
GROUP BY ALL;
~~~

GROUP BY ALL is convenient for ad-hoc queries and prototypes. For complex production queries, keep explicit grouping keys when you want a stable SQL contract that is easy to review and less affected when the select list changes.

## 10. DML: UPDATE/DELETE with JOIN

### 10.1. 19c

In 19c, updating based on conditions from another table usually used subqueries or MERGE:

~~~sql
UPDATE employees e
SET e.salary = e.salary * 1.05
WHERE e.department_id IN (
    SELECT d.department_id
    FROM departments d
    WHERE d.department_name = 'RESEARCH'
);
~~~

### 10.2. 23ai and Later

23ai supports direct JOINs in UPDATE/DELETE with a FROM clause:

~~~sql
UPDATE employees e
SET e.salary = e.salary * 1.05
FROM departments d
WHERE e.department_id = d.department_id
  AND d.department_name = 'RESEARCH';
~~~

This makes statements closer to the style used in many other RDBMSs and can improve query readability. Check supported JOIN syntax, aliases, cardinality, and the possibility of one target row matching multiple source rows. Do not mechanically convert MERGE to JOIN UPDATE if match/insert logic differs.

### 10.3. Backward Compatibility

If an application must run on both 19c and 23ai:
- Keep subqueries or MERGE for shared SQL.
- Use release-specific SQL based on capability when the benefit is significant.
- Do not send the new JOIN UPDATE syntax to older 19c servers.
- Test row counts, duplicate source matches, and execution plans before changing.

## 11. RETURNING: From Legacy DML to OLD/NEW

### 11.1. 19c

Oracle 19c already supports RETURNING INTO for INSERT, UPDATE, and DELETE within documented scopes. PL/SQL can use variables or BULK COLLECT for multi-row cases. Dynamic SQL also has its own RETURNING INTO form.

Single-row UPDATE example:

~~~sql
DECLARE
    l_new_salary NUMBER;
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE employee_id = 100
    RETURNING salary INTO l_new_salary;

    DBMS_OUTPUT.PUT_LINE(l_new_salary);
END;
/
~~~

### 11.2. 23ai

23ai adds RETURNING for UPDATE and MERGE in static DML, including ways to retrieve OLD and NEW values in supported cases.

~~~sql
DECLARE
    l_old_salary NUMBER;
    l_new_salary NUMBER;
BEGIN
    UPDATE employees
    SET salary = salary + 1000
    WHERE employee_id = 100
    RETURNING OLD salary, NEW salary
    INTO l_old_salary, l_new_salary;
END;
/
~~~

MERGE can also use RETURNING according to the syntax and conditions supported in the release.

### 11.3. 26ai

26ai continues expanding RETURNING to retrieve OLD/NEW values more uniformly across INSERT, UPDATE, DELETE, and MERGE:
- UPDATE can return before and after values.
- INSERT has NEW values; no OLD row.
- DELETE has OLD values; no NEW row.
- MERGE can return values per branch and supported semantics.

General examples must be written for the exact DML statement and release. Do not use 26ai OLD/NEW syntax in SQL source that must compile on 19c.

### 11.4. RETURNING and Multiple Rows

If a statement affects multiple rows, consider BULK COLLECT INTO or the corresponding mechanism. Do not assume a scalar variable will hold results from multiple rows. Check affected row counts, collection cardinality, and zero-row behavior.

## 12. SQL Macros: 19c Table Macros and 21c Scalar Macros

### 12.1. 19c RU 19.7

SQL table macros have been supported since 19c RU 19.7. A table macro is a PL/SQL function used as a query-generating expression in FROM. It lets you reuse SQL logic without repeating query text.

Conceptual example:

~~~sql
CREATE OR REPLACE FUNCTION employees_by_department(
    p_department_id NUMBER
) RETURN VARCHAR2 SQL_MACRO(TABLE)
IS
BEGIN
    RETURN q'[
        SELECT employee_id, employee_name, department_id
        FROM employees
        WHERE department_id = p_department_id
    ]';
END;
/
~~~

Usage:

~~~sql
SELECT *
FROM employees_by_department(10);
~~~

Exact macro syntax depends on version and macro type. This example illustrates the table macro pattern; verify the SQL_MACRO clause and restrictions for your 19c RU.

### 12.2. 21c and Scalar Macros

21c adds SQL scalar macros for reusing expressions in the SELECT list, WHERE, GROUP BY, or HAVING. It encapsulates expression logic while still letting the SQL optimizer see the expanded SQL.

Conceptual example:

~~~sql
CREATE OR REPLACE FUNCTION normalized_email(
    p_email VARCHAR2
) RETURN VARCHAR2 SQL_MACRO(SCALAR)
IS
BEGIN
    RETURN q'[LOWER(TRIM(p_email))]';
END;
/
~~~

Usage:

~~~sql
SELECT employee_id
FROM employees
WHERE normalized_email(email) = 'user@example.com';
~~~

Verify macro syntax and capabilities for your specific release. Do not treat a macro as a procedure called row-by-row like a normal function; an SQL macro returns SQL text for the database to expand at parse time.

### 12.3. Macros vs. Traditional PL/SQL Functions

| Criterion | Traditional PL/SQL Function | SQL Macro |
| --- | --- | --- |
| Result | Runtime value | Expanded SQL expression/query |
| SQL engine calls PL/SQL runtime | Possible context switch | Macro expands into SQL |
| Reusability | Yes | Yes |
| SQL optimization | Depends on optimizer and function capabilities | Optimizer sees expanded SQL |
| Compatibility | Broader | Depends on RU/release and macro type |

SQL macros are not a replacement for every PL/SQL function. Use them when the logic can be expressed in SQL and you need to reuse query expression/table logic.

## 13. SQL Transpiler in 26ai

The SQL Transpiler automatically converts PL/SQL functions invoked inside SQL into SQL expressions when possible. The goal is to reduce context-switching overhead between the SQL runtime and the PL/SQL runtime.

Conceptual example:

~~~sql
CREATE OR REPLACE FUNCTION tax_amount(
    p_net NUMBER
) RETURN NUMBER
IS
BEGIN
    RETURN p_net * 0.10;
END;
/
~~~

Query:

~~~sql
SELECT order_id, tax_amount(net_amount)
FROM orders;
~~~

In 26ai, the SQL Transpiler can convert simple functions into SQL expressions when the function meets transpilation criteria. Not every function is transpilation-eligible; functions with side effects, package state, non-pure SQL operations, or unsupported constructs may be ineligible.

Do not assume that merely running 26ai means every PL/SQL function in SQL will automatically match inline expression performance. Check execution plans, traces, and the SQL Tuning Guide. Where performance matters, measure before and after with real data and binds.

## 14. Extended PL/SQL CASE in 26ai

The PL/SQL simple CASE statement is extended with:
- Choice lists: multiple choices in a single WHEN.
- Dangling predicates: selector-based comparisons with a shortened predicate.

Choice list example:

~~~sql
DECLARE
    l_status VARCHAR2(20) := 'PENDING';
    l_message VARCHAR2(100);
BEGIN
    CASE l_status
        WHEN 'NEW', 'PENDING' THEN
            l_message := 'Waiting';
        WHEN 'DONE', 'CLOSED' THEN
            l_message := 'Completed';
        ELSE
            l_message := 'Unknown';
    END CASE;

    DBMS_OUTPUT.PUT_LINE(l_message);
END;
/
~~~

Dangling predicate example per supported syntax:

~~~sql
DECLARE
    l_score NUMBER := 82;
    l_grade VARCHAR2(2);
BEGIN
    CASE l_score
        WHEN >= 90 THEN l_grade := 'A';
        WHEN >= 80 THEN l_grade := 'B';
        WHEN >= 70 THEN l_grade := 'C';
        ELSE l_grade := 'F';
    END CASE;
END;
/
~~~

Verify the illustrated syntax on the exact 26ai RU; documentation explicitly notes that some dangling predicates such as IS JSON and IS OF are not yet supported. For code that must run on 19c, use traditional searched CASE to ensure compatibility.

## 15. Aggregation FILTER and INTERVAL

### 15.1. Conditional Aggregates in 19c

Before the FILTER clause, CASE inside an aggregate was commonly used:

~~~sql
SELECT
    department_id,
    COUNT(CASE WHEN status = 'ACTIVE' THEN 1 END) AS active_count,
    SUM(CASE WHEN status = 'ACTIVE' THEN salary ELSE 0 END) AS active_salary
FROM employees
GROUP BY department_id;
~~~

### 15.2. FILTER in 26ai

26ai supports the FILTER clause on aggregate functions:

~~~sql
SELECT
    department_id,
    COUNT(*) FILTER (WHERE status = 'ACTIVE') AS active_count,
    SUM(salary) FILTER (WHERE status = 'ACTIVE') AS active_salary,
    SUM(salary) FILTER (WHERE status = 'INACTIVE') AS inactive_salary
FROM employees
GROUP BY department_id;
~~~

FILTER only affects the aggregate immediately preceding it. It does not replace a query-wide WHERE clause. Multiple aggregates with different filters can be used in the same SELECT.

### 15.3. SUM/AVG with INTERVAL

Current SQL documentation notes support for SUM and AVG aggregates with INTERVAL starting in release 23. This allows calculating total/average durations without manually converting to seconds or days.

~~~sql
SELECT
    project_id,
    SUM(duration_interval) AS total_duration,
    AVG(duration_interval) AS average_duration
FROM task_durations
GROUP BY project_id;
~~~

The resulting INTERVAL type preserves units matching the input. Check precision, conversion, and formatting rules when displaying results.

## 16. GROUP BY ALL and GROUP BY Extensions in 26ai

26ai includes GROUP BY ALL to automatically group by all non-aggregate expressions in the select list.

~~~sql
SELECT
    department_id,
    job_id,
    COUNT(*) AS employee_count,
    AVG(salary) AS average_salary
FROM employees
GROUP BY ALL;
~~~

This syntax reduces having to repeat grouping columns in GROUP BY. It is convenient for exploratory queries, but watch out when the query's select list changes: adding a non-aggregate column can change grouping semantics.

26ai also extends alias/position support in GROUP BY, ROLLUP, CUBE, GROUPING SETS, and HAVING per documentation. If a query must also run on 19c, use explicit grouping expressions/columns or create an intermediate view.

## 17. SQL Domains and Data Use Case Domains

### 17.1. SQL Domains in 23ai

A domain is a reusable object describing types and constraints for a group of values—for example, email, country code, account number, or birth date. A domain can be applied across multiple columns to standardize definitions.

~~~sql
CREATE DOMAIN country_code AS VARCHAR2(2)
    CONSTRAINT country_code_ck
    CHECK (LENGTH(VALUE) = 2);

CREATE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    country country_code
);
~~~

Domains do not replace all table-level constraints, foreign keys, or complex business validations. They help reuse rules for values of the same nature.

### 17.2. Data Use Case Domains in 26ai

26ai adds Data Use Case Domain metadata for use cases such as email or credit card numbers. Domains can encapsulate purpose-specific attributes/constraints and attach to columns.

When using domains in migrations:
- Verify whether domain objects are exported/imported in your specific workflow.
- Verify whether the target release supports domains.
- Verify that constraints are preserved.
- Check driver/tool metadata handling.
- Do not assume domain objects are automatically converted into simple CHECK constraints.

## 18. JSON-Relational Duality and SQL Property Graph

### 18.1. JSON-Relational Duality

23ai introduces JSON-Relational Duality Views. Applications can read and update relational data via a JSON document view. The data still resides in relational tables, while exposing a document interface to applications.

Usage examples:
- A REST API returns a JSON order containing header and line items.
- Document-centric applications update part of the JSON.
- SQL/BI systems still query the relational tables.
- Multiple applications share a single source data model.

26ai continues extending duality views, such as validation directives, hidden/generated fields, array limits, custom keys, and integration/replication capabilities. Check these features against your exact RU and the JSON Developer's Guide.

### 18.2. SQL Property Graph Queries

Newer releases support SQL/PGQ to query graphs directly over relational data. This enables representing vertices/edges and querying multi-hop relationships without moving all data into a separate graph store.

Applications can use graph queries for:
- Path discovery between entities.
- Customer/account/transaction relationships.
- Dependencies and network topology.
- Link-chain analysis.

Do not confuse SQL/PGQ with creating a separate graph table for every query. Check graph views, syntax, privileges, and release support.

## 19. Extended PL/SQL Packages and APIs

PL/SQL scope goes beyond block syntax. Oracle continues adding packages and APIs for developers to manage JSON, vectors, metadata, performance, and application integration.

Examples in 26ai:
- DBMS_VECTOR supports AI Vector Search operations such as chunking, embedding, and vector indexes.
- DBMS_DEVELOPER provides APIs to retrieve object metadata; this package was also added in 19c RU 19.28.
- DBMS_SPM provides APIs for managing SQL plan management.
- In-Memory and vector packages are expanded by release.

When calling a new package:
1. Check if the package exists on the target.
2. Check EXECUTE privilege.
3. Check package status and dependencies.
4. Confirm license/options if the package is tied to a conditional feature.
5. Check whether input/output types are supported by the client.
6. Test in the exact PDB where it will be deployed.

Do not rely on a package name in 26ai documentation to assume it exists in 19c.

## 20. New Features Are More Than SQL Syntax

Several 26ai capabilities affect how applications interact with SQL/PLSQL rather than just adding a new statement:
- JDBC supports the native BOOLEAN data type and metadata.
- Drivers have properties controlling how booleans are sent for legacy application compatibility.
- Clients/drivers may need upgrades to bind/fetch new types.
- SQL Firewall controls which SQL statements are allowed to execute.
- Driver APIs may extend for annotations, pipelining, or application security context.

Therefore, when upgrading the database, you must also upgrade and test the client tier. The server accepting a data type does not mean every driver, ORM, ETL, or GUI tool can read/write it.

## 21. Differences to Watch When Porting SQL Between 19c and Newer Releases

| Item | Porting Risk | How to Handle |
| --- | --- | --- |
| BOOLEAN column | Older 19c cannot parse/lacks SQL BOOLEAN | Use shared representation or schema migration |
| Native JSON | 19c lacks 21c SQL JSON type | Use CLOB/BLOB + IS JSON or keep an adapter |
| VECTOR | 19c lacks native VECTOR | Keep embeddings in external/alternate representation or split code paths |
| IF NOT EXISTS | 19c RUs before 19.28 fail with syntax error | Check RU; use dynamic DDL or PL/SQL dictionary check |
| Annotations | Older 19c RUs do not support | Use only from supported RU; keep metadata external if needed |
| SQL Domains | 19c target lacks domains | Materialize constraints at table/column level for older targets |
| SELECT omitting FROM | 19c requires DUAL | Keep FROM DUAL in shared SQL |
| Multivalue INSERT | 19c cannot parse new tuple list | Use INSERT ALL, array binding, or multiple INSERTs |
| VALUES constructor | 19c does not support new form | Use SELECT FROM DUAL/CTE/temporary table |
| GROUP BY alias | 19c requires repeating expression/column | Use inline view or repeat expression |
| JOIN UPDATE/DELETE | 19c cannot parse new syntax | Use subquery or MERGE |
| New UPDATE/MERGE RETURNING | Syntax/semantics vary by release | Use PL/SQL wrapper or separate code paths |
| SQL Transpiler | 19c lacks 26ai auto-transpilation | Optimize functions and SQL in a compatible way |
| FILTER aggregate | 19c lacks new syntax | Use CASE inside aggregate |
| GROUP BY ALL | 19c lacks new syntax | List grouping columns explicitly |
| VECTOR in PL/SQL | Requires 26ai and appropriate RU | Use separate package/SQL path for newer releases |

## 22. Example of the Same Business Logic on 19c and 23ai+

Suppose we need to count orders by status while summing the total value of paid orders.

### 22.1. SQL That Works on 19c

~~~sql
SELECT
    customer_id,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count,
    SUM(CASE WHEN status = 'PAID' THEN total_amount ELSE 0 END)
        AS paid_amount
FROM orders
GROUP BY customer_id;
~~~

### 22.2. SQL Using FILTER on Supported Releases

~~~sql
SELECT
    customer_id,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_count,
    SUM(total_amount) FILTER (WHERE status = 'PAID') AS paid_amount
FROM orders
GROUP BY customer_id;
~~~

Both statements express the same intent, but the second requires a release supporting FILTER. If the application must run on 19c, keep the first statement or create a compatible view/package.

## 23. Writing Safe Multi-Version SQL

### 23.1. Prefer Intersecting SQL

If a single codebase must run across multiple releases:
- Use the lowest common denominator syntax.
- Encapsulate differences in repositories/views/packages.
- Avoid scattering version checks across every query.
- Split migration scripts by release.
- Never send new syntax to an older server's parser.

### 23.2. Dynamic SQL for Conditional Syntax

A PL/SQL block can hold newer SQL as strings and execute it only when capability is confirmed. Older servers can compile the block because the new syntax is not in static SQL; the string is only parsed at runtime.

Conceptual example:

~~~sql
DECLARE
    l_supports_new_ddl BOOLEAN := FALSE;
BEGIN
    -- Capability must be determined from a verified release/RU.
    IF l_supports_new_ddl THEN
        EXECUTE IMMEDIATE
            'CREATE TABLE IF NOT EXISTS app_log (id NUMBER)';
    ELSE
        BEGIN
            EXECUTE IMMEDIATE
                'CREATE TABLE app_log (id NUMBER)';
        EXCEPTION
            WHEN OTHERS THEN
                IF SQLCODE != -955 THEN
                    RAISE;
                END IF;
        END;
    END IF;
END;
/
~~~

The example above only illustrates syntax isolation; production must perform real capability checks and ignore only the exact object-already-exists error. Do not use WHEN OTHERS to swallow arbitrary DDL errors.

### 23.3. Do Not Check Versions with Arbitrary Strings

Some features are backported via RUs, so comparing VERSION alone is insufficient. You must determine:
- Release.
- RU/patch.
- COMPATIBLE.
- Feature options.
- Client/driver capabilities.

If runtime capability detection is needed, build a centralized check module with logging and tests for each environment.

### 23.4. Split DDL Migrations by Target

Schema migrations can include:
- Baseline 19c scripts.
- Extension scripts for newer 19c RUs.
- 21c upgrade scripts.
- Scripts dedicated to 23ai/26ai.
- Backfill and validation scripts.
- Rollback or forward-fix scripts.

Do not put every syntax into a single SQL file and hope older databases skip what they do not understand. The SQL parser must parse the statement before runtime conditions can decide to skip it.

## 24. Testing When Upgrading 19c to 23ai/26ai

### 24.1. Syntax and Object Testing

- Recompile packages, procedures, functions, and triggers.
- Check invalid objects and dependencies.
- Run migration DDL in the proper order.
- Verify domains, annotations, identities, and JSON metadata.
- Check synonyms, views, and materialized views.

### 24.2. Data Testing

- Cross-check row counts.
- Verify NULLs and defaults.
- Verify JSON validity and JSON type conversions.
- Verify BOOLEAN mappings.
- Verify VECTOR dimensions/formats and null handling.
- Verify constraints and indexes.

### 24.3. Execution Plan Testing

New SQL can make queries shorter, but not faster by default. Compare:
- Execution plans.
- Estimated/actual rows.
- Buffer gets and physical reads.
- CPU and elapsed time.
- Wait events.
- Bind peeking/adaptive behavior.
- SQL plan baselines if using SPM.

SQL Transpiler, FILTER, new GROUP BY features, and JOIN DML all require benchmarking with realistic workloads.

### 24.4. Client and Framework Testing

- JDBC/ODP.NET/OCI versions.
- ORM dialects and schema generators.
- BI/reporting tools.
- ETL and Data Pump.
- SQL Developer/SQLcl/SQL*Plus.
- Monitoring/observability.
- Application server connection pools.

Especially for BOOLEAN, JSON, and VECTOR, test metadata discovery, binding, fetching, serialization, and null handling.

## 25. Decision Matrix for Adopting New Features

| Question | If Yes | Recommended Action |
| --- | --- | --- |
| Does the app only run on older 19c RUs? | Yes | Do not use new syntax; pick a fallback |
| Does the app run on 19c RU 19.28+? | Yes | Verify IF EXISTS/annotations per object support |
| Must code be shared across 19c and 23ai? | Yes | Use intersecting SQL or adapters |
| Is a native boolean column needed? | Yes | Use only when all targets/drivers support it |
| Is a document API over relational data needed? | Yes | Evaluate JSON-Relational Duality |
| Is there an embedding/vector workload? | Yes | Evaluate VECTOR, indexes, models, and RU |
| Are heavy PL/SQL functions called in SQL? | Yes | Review SQL Transpiler or SQL macros, benchmark performance |
| Are there multi-condition aggregate queries? | Yes | Evaluate FILTER on supported releases |
| Are idempotent DDL scripts needed? | Yes | Verify RU 19.28 or newer releases |
| Is there cross-platform migration? | Yes | Test dumps, drivers, data types, and client compatibility |

## 26. Syntax Comparison Labs

Perform these on two separate environments or two database containers with different releases. Never run experimental DDL on production schemas.

### 26.1. BOOLEAN Lab

On 19c:

~~~sql
CREATE TABLE lab_flag_19c (
    id NUMBER PRIMARY KEY,
    enabled NUMBER(1) NOT NULL CHECK (enabled IN (0, 1))
);
~~~

On 23ai/26ai:

~~~sql
CREATE TABLE lab_flag_new (
    id NUMBER PRIMARY KEY,
    enabled BOOLEAN DEFAULT FALSE NOT NULL
);

INSERT INTO lab_flag_new VALUES (1, TRUE);
SELECT * FROM lab_flag_new WHERE enabled = TRUE;
~~~

Compare schema metadata, driver fetching, and how the application represents values.

### 26.2. DDL IF EXISTS Lab

On a 19c RU prior to 19.28, try the new statement in a lab schema to observe the parse error. On RU 19.28+ or 23ai/26ai, test supported object types:

~~~sql
CREATE TABLE IF NOT EXISTS lab_idempotent (
    id NUMBER PRIMARY KEY
);

DROP TABLE IF EXISTS lab_idempotent;
~~~

Do not conclude from a single CREATE TABLE statement that all DDL supports IF EXISTS.

### 26.3. VALUES and Multivalue INSERT Lab

~~~sql
SELECT *
FROM (VALUES
    (1, 'A'),
    (2, 'B'),
    (3, 'C')
) sample_rows(id, label);
~~~

~~~sql
INSERT INTO lab_items (item_id, item_name)
VALUES
    (1, 'A'),
    (2, 'B'),
    (3, 'C');
~~~

Run on 23ai/26ai. On 19c, use INSERT ALL or multiple INSERT statements accordingly.

### 26.4. GROUP BY Alias Lab

~~~sql
SELECT
    TO_CHAR(created_at, 'YYYY-MM') AS month_key,
    COUNT(*) AS item_count
FROM lab_items
GROUP BY month_key;
~~~

Compare with repeating the TO_CHAR expression on 19c.

### 26.5. RETURNING Lab

Create a lab table and test UPDATE RETURNING OLD/NEW on 23ai/26ai per supported syntax. On 19c, test traditional RETURNING and compare the returned data.

### 26.6. SQL Macro Lab

Create a table macro on 19c RU 19.7+ or a newer release. Create a scalar macro on a supported release. Inspect execution plans to understand how macros expand into SQL.

### 26.7. SQL Transpiler Lab

On 26ai:
- Create a simple PL/SQL function with no side effects.
- Call the function in SQL.
- Check transpilation criteria in the documentation.
- View the execution plan and measure CPU/elapsed time.
- Modify the function to add an unsupported construct and compare.

Do not use the results of one small lab to claim every function will transpile.

## 27. Common Errors When Using New Features

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| ORA-00902 invalid datatype with BOOLEAN | Server lacks SQL BOOLEAN support or wrong client metadata | Verify 23ai+ and driver |
| ORA-00933/ORA-00905 with new syntax | Release/RU does not support the statement yet | Check SQL Reference and RU |
| IF NOT EXISTS fails on 19c | RU lower than 19.28 or object type not in list | Verify patch and supported statements |
| Annotations not recognized | RU/release unsupported or invalid syntax | Verify 19.28+ and CREATE/ALTER grammar |
| JSON type unusable on 21c | Incorrect COMPATIBLE or release conditions | Check parameters and migration guide |
| VECTOR fails to bind from application | Driver/client lacks support for new type | Upgrade driver and check API mapping |
| Calling PL/SQL BOOLEAN from SQL fails | Release/argument expression unsupported | Check 26ai BOOLEAN interop capabilities |
| SQL macro fails to compile | Unsupported RU/release or macro type | Distinguish table macro vs. scalar macro |
| SQL Transpiler not applied | Function contains ineligible construct | Check documentation and execution plan |
| UPDATE JOIN affects unexpected rows | Non-unique source join | Check cardinality and source keys |
| Ambiguous GROUP BY alias | Alias matches column name or different scope | Rename alias and qualify columns |
| FILTER aggregate differs from CASE | Different NULL/ELSE conditions | Compare semantics and NULL data |
| Schema import loses domain/annotation | Older target or unsupported export/import path | Check Data Pump compatibility and metadata |
| Tools display wrong types | Older client does not understand type metadata | Upgrade SQL Developer/driver/ORM |

## 28. Design Principles for Multi-Release Systems

1. Choose a common SQL baseline if the same source must run across multiple versions.
2. Explicitly record database version, RU, and COMPATIBLE in deployment manifests.
3. Use adapters for differences in BOOLEAN, JSON, and VECTOR.
4. Separate migration scripts by release and capability.
5. Never send new syntax in static SQL to older databases.
6. Verify clients/drivers/ORMs alongside the server.
7. Use controlled dynamic SQL when multiple parsers must be supported.
8. Test rollback and data conversion before changing column types.
9. Benchmark new SQL instead of assuming shorter syntax is faster.
10. Keep a fallback path for systems still on older 19c RUs.
11. Verify licensing, deployment restrictions, and patch requirements.
12. Read RU documentation before patching production.

## Summary

Oracle's SQL/PLSQL scope has expanded significantly from 19c through 21c, 23ai, and 26ai. 19c still has many modern capabilities, especially when recent RUs are installed: table SQL macros have been available since 19.7, and IF [NOT] EXISTS and annotations since 19.28. 21c adds the native JSON SQL data type and scalar SQL macros. 23ai expands SQL with BOOLEAN, Domains, multivalue INSERT, VALUES constructors, optional FROM, GROUP BY aliases, UPDATE/MERGE RETURNING, JOIN DML, VECTOR, and JSON-Relational Duality. 26ai further expands PL/SQL BOOLEAN/VECTOR, JSON aggregate mapping, SQL Transpiler, CASE controls, aggregation FILTER, GROUP BY ALL, and many other SQL capabilities.

Do not treat version differences merely as a list of new syntax. What matters is identifying whether a feature lies in SQL or PL/SQL, which release/RU supports it, whether COMPATIBLE and client drivers meet requirements, and how applications fall back when running across multiple releases. A good migration documents capabilities, tests schemas/data/clients, measures performance, and rolls out incrementally to avoid sending new syntax to unsupported systems.

## Oracle Reference Documentation

- [Oracle Database 19c SQL Language Reference — Changes in This Release](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Changes-in-This-Release-for-Oracle-Database-SQL-Language-Reference.html) — SQL macros, RU 19.28 IF [NOT] EXISTS, and schema annotations.
- [Oracle Database 19c PL/SQL Language Reference — Changes in This Release](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/release-changes.html) — SQL table macros from 19c RU 19.7 and IF [NOT] EXISTS from RU 19.28.
- [Oracle Database 19c Release Update 19.28](https://docs.oracle.com/en/database/oracle/oracle-database/19/newft/ru-19-28.html) — DBMS_DEVELOPER, annotations, and RU changes.
- [Oracle Database 21c SQL Language Reference — Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/Data-Types.html) — native JSON data type.
- [Oracle Database 21c SQL Language Reference — Changes in This Release](https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/Changes-in-This-Release-for-Oracle-Database-SQL-Language-Reference.html) — scalar/table SQL macros and 21c SQL changes.
- [Explore SQL Features in Oracle Database 23ai](https://docs.oracle.com/en/learn/db23ai-sql-features/index.html) — BOOLEAN, IF EXISTS, multivalue INSERT, VALUES, GROUP BY alias, RETURNING, JOIN DML, annotations, and domains.
- [Oracle AI Database 26ai New Features](https://docs.oracle.com/en/database/oracle/oracle-database/26/nfcoa/all-nfg.html) — overview of 26ai SQL/PLSQL, JSON, vector, and developer productivity features.
- [Oracle AI Database 26ai PL/SQL Language Reference — Changes in This Release](https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/release-changes.html) — SQL BOOLEAN, VECTOR, IF [NOT] EXISTS, extended CASE, JSON aggregate mapping, and SQL Transpiler.
- [Oracle AI Database 26ai SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/) — current SQL syntax.
- [Oracle AI Database 26ai PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/) — current PL/SQL syntax.

When applying these features, read the SQL Language Reference, PL/SQL Language Reference, New Features, and RU notes for the exact release. In particular, confirm the 19c RU, COMPATIBLE, driver/client, feature options, and restrictions before introducing new syntax into shared source code.

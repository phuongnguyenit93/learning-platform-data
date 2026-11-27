# RECORD and Multi-Field Data Modeling in PL/SQL

An employee is not just a single value. An employee record typically consists of an employee ID, full name, department, email, status, and hire date. If a PL/SQL procedure must process these values as a single unit, declaring a swarm of separate variables makes code verbose, hard to pass as parameters, and prone to parameter-order mix-ups. PL/SQL provides the **RECORD** composite data type to group multiple named fields into a meaningful structure.

A RECORD can represent a data row, an application-level business object, or a multi-column query result. Each field inside a record has its own name and datatype. You can declare a record explicitly, anchor field types to columns with %TYPE, derive a row structure with %ROWTYPE, use a cursor's record type, pass records through package APIs, or store multiple records in a collection.

This lesson belongs to the **PL/SQL Basics** section of Database Engine Relational Oracle. It focuses on RECORD and modeling multi-field data in PL/SQL memory. It also distinguishes records from collections, object types, and SQL table rows; and covers SELECT INTO, FETCH, DML RETURNING, package interfaces, and BULK COLLECT.

After this lesson, you will be able to:

- Explain that RECORD is a composite data type consisting of multiple named fields.
- Declare TYPE ... IS RECORD and record variables.
- Anchor field datatypes using %TYPE.
- Use table%ROWTYPE and cursor%ROWTYPE to match result structures closely.
- Read and write individual fields using dot notation.
- Initialize, assign, and pass records between procedures.
- Use SELECT INTO, FETCH, and RETURNING INTO with records or record fields.
- Publish record types in a package specification to build PL/SQL APIs.
- Create collections holding multiple records and process them with BULK COLLECT.
- Understand the limitations of PL/SQL RECORD when interacting with the SQL engine.
- Choose among RECORD, %ROWTYPE, collections, and SQL object types based on requirements.

> **Example scope:** Syntax is illustrated for Oracle Database 19c. Examples use tables with a _LAB suffix in a practice schema. Some qualified expression syntax for initializing records was introduced in Oracle Database 18c; the lesson notes where version support is needed and always shows field-by-field assignment as an alternative.

## 1. What Is a RECORD?

A RECORD is a PL/SQL data type composed of multiple fields. Each field has a name, a datatype, and optionally a default value. Fields can have different datatypes.

For example, an employee has:

| Field | Illustrative Datatype |
| --- | --- |
| employee_id | NUMBER |
| full_name | VARCHAR2 |
| department_id | NUMBER |
| work_email | VARCHAR2 |
| hire_date | DATE |
| active_flag | BOOLEAN |

We can model an employee as a single record instead of declaring six separate variables.

~~~text
EMPLOYEE_RECORD
+-----------------------------+
| employee_id   : NUMBER      |
| full_name     : VARCHAR2    |
| department_id : NUMBER      |
| work_email    : VARCHAR2    |
| hire_date     : DATE        |
| active_flag   : BOOLEAN     |
+-----------------------------+
~~~

### 1.1. RECORD Represents a Multi-Field Data Unit

A record commonly represents one of these concepts:

- An employee row.
- A customer along with contact information.
- An order header.
- A cursor result row.
- A business message parsed into multiple attributes.
- An input/output structure between procedures within the same PL/SQL application.

A RECORD exists only as data in PL/SQL memory. By itself, it does not create a table, does not persist data durably, and does not automatically enforce transactions or constraints. When persistence is needed, code must INSERT/UPDATE into tables or call an appropriate persistence mechanism.

### 1.2. Contrast with Individual Variables

Without a record:

~~~sql
DECLARE
    v_employee_id   NUMBER;
    v_full_name     VARCHAR2(80);
    v_department_id NUMBER;
    v_work_email    VARCHAR2(120);
BEGIN
    SELECT employee_id, full_name, department_id, work_email
    INTO v_employee_id, v_full_name, v_department_id, v_work_email
    FROM employee_data_lab
    WHERE employee_id = 101;
END;
/
~~~

Using a record:

~~~sql
DECLARE
    TYPE employee_rec IS RECORD (
        employee_id   NUMBER,
        full_name     VARCHAR2(80),
        department_id NUMBER,
        work_email    VARCHAR2(120)
    );

    l_employee employee_rec;
BEGIN
    SELECT employee_id, full_name, department_id, work_email
    INTO l_employee
    FROM employee_data_lab
    WHERE employee_id = 101;

    DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
END;
/
~~~

A record groups related values into a single structured variable. When passing data to another procedure, you can pass one record instead of many separate parameters, provided the API is designed with a compatible record type.

## 2. Explicit RECORD Declarations

### 2.1. TYPE ... IS RECORD Syntax

Basic pattern:

~~~sql
TYPE record_type_name IS RECORD (
    field_name_1 datatype [ [NOT NULL] { := | DEFAULT } expression ],
    field_name_2 datatype [ [NOT NULL] { := | DEFAULT } expression ],
    ...
);
~~~

After declaring the type, declare one or more variables of that type:

~~~sql
DECLARE
    TYPE address_rec IS RECORD (
        street       VARCHAR2(120),
        district     VARCHAR2(60),
        city         VARCHAR2(60),
        postal_code  VARCHAR2(20)
    );

    l_address address_rec;
BEGIN
    l_address.street := '12 Nguyen Hue';
    l_address.district := 'District 1';
    l_address.city := 'Ho Chi Minh City';
    l_address.postal_code := '700000';

    DBMS_OUTPUT.PUT_LINE(
        l_address.street || ', ' ||
        l_address.district || ', ' ||
        l_address.city
    );
END;
/
~~~

TYPE defines the structure, while l_address is a variable holding a specific record value. Multiple variables can share the same record type:

~~~sql
DECLARE
    TYPE point_rec IS RECORD (
        x NUMBER,
        y NUMBER
    );

    l_origin point_rec;
    l_target point_rec;
BEGIN
    l_origin.x := 0;
    l_origin.y := 0;

    l_target.x := 10;
    l_target.y := 20;
END;
/
~~~

### 2.2. Accessing Fields with Dot Notation

Each field is accessed with the syntax:

~~~sql
record_variable.field_name
~~~

Example:

~~~sql
l_employee.employee_id := 101;
l_employee.full_name := 'Nguyen An';
l_employee.department_id := 10;
~~~

Field names must match the declaration. A record does not access fields by index like an array; it uses field names to convey data meaning.

### 2.3. Datatypes of Individual Fields

Record fields can use appropriate PL/SQL datatypes such as NUMBER, VARCHAR2, DATE, TIMESTAMP, BOOLEAN, subtypes, %TYPE, or another supported record/collection type within scope.

Example:

~~~sql
DECLARE
    TYPE contact_rec IS RECORD (
        contact_id NUMBER,
        display_name VARCHAR2(100),
        preferred_contact VARCHAR2(10),
        verified BOOLEAN,
        last_contact_at TIMESTAMP
    );

    l_contact contact_rec;
BEGIN
    l_contact.contact_id := 501;
    l_contact.display_name := 'Customer A';
    l_contact.preferred_contact := 'EMAIL';
    l_contact.verified := TRUE;
    l_contact.last_contact_at := SYSTIMESTAMP;
END;
/
~~~

BOOLEAN is a PL/SQL datatype; not every PL/SQL datatype can be used as a SQL column. This is an important difference between PL/SQL records and data structures declared in a SQL schema.

### 2.4. Default Values for Fields

Default values can be declared:

~~~sql
DECLARE
    TYPE order_rec IS RECORD (
        order_id NUMBER,
        status VARCHAR2(12) := 'NEW',
        priority NUMBER := 0,
        created_at TIMESTAMP := SYSTIMESTAMP
    );

    l_order order_rec;
BEGIN
    l_order.order_id := 9001;

    DBMS_OUTPUT.PUT_LINE(l_order.status);
END;
/
~~~

When the record variable is created, fields with defaults receive their corresponding values. Fields without defaults generally start as NULL.

If a field is declared NOT NULL, a valid default value must be provided in the record declaration. Example:

~~~sql
TYPE employee_key_rec IS RECORD (
    employee_id NUMBER NOT NULL := 0,
    full_name VARCHAR2(80)
);
~~~

Do not confuse a record field's NOT NULL with a table column's NOT NULL constraint. It is a PL/SQL datatype rule and only protects field assignment within that record.

## 3. Assigning and Initializing RECORDs

### 3.1. Field-by-Field Assignment

This is the clearest approach and works across all common PL/SQL versions:

~~~sql
DECLARE
    TYPE product_rec IS RECORD (
        product_id NUMBER,
        product_name VARCHAR2(80),
        unit_price NUMBER(12,2)
    );

    l_product product_rec;
BEGIN
    l_product.product_id := 1001;
    l_product.product_name := 'Keyboard';
    l_product.unit_price := 49.90;
END;
/
~~~

Field-by-field assignment is useful when data comes from multiple sources or only certain fields are populated at each step. However, ensure required fields are assigned before use.

### 3.2. Whole-Record Assignment

One record can be assigned to another when both variables share a compatible record type:

~~~sql
DECLARE
    TYPE point_rec IS RECORD (
        x NUMBER,
        y NUMBER
    );

    l_a point_rec;
    l_b point_rec;
BEGIN
    l_a.x := 10;
    l_a.y := 20;

    l_b := l_a;
END;
/
~~~

Whole-record assignment copies fields from the source record to the target record. If a record contains fields with collections or complex structures, understand the component type semantics and corresponding copy behavior.

Do not assume two independently declared record types are always assignable to each other merely because their field names and datatypes look alike. API design should use a single shared type declared in a package specification when multiple subprograms need to exchange the same structure.

### 3.3. Qualified Expressions in Oracle 18c+

Oracle Database 18c and later support qualified expressions to construct values for a record type:

~~~sql
DECLARE
    TYPE point_rec IS RECORD (
        x NUMBER,
        y NUMBER
    );

    l_point point_rec;
BEGIN
    l_point := point_rec(10, 20);
END;
/
~~~

Named association can be used to state fields more clearly:

~~~sql
l_point := point_rec(y => 20, x => 10);
~~~

Qualified expressions are convenient syntax, but if code must run on older versions, assign field by field or use SELECT INTO.

### 3.4. No General Whole-Record Comparison

Do not write:

~~~sql
IF l_old_record = l_new_record THEN
    ...
END IF;
~~~

PL/SQL does not provide general equality comparison for whole records the way it does for scalars. Compare the necessary fields instead:

~~~sql
IF l_old_record.employee_id = l_new_record.employee_id
   AND l_old_record.department_id = l_new_record.department_id
THEN
    ...
END IF;
~~~

If many fields need comparing, write a dedicated function or compare by business key and meaningful attributes. Handle NULL explicitly because comparisons involving NULL yield UNKNOWN.

### 3.5. Do Not Check Whole Records for NULL Like Scalars

Do not use:

~~~sql
IF l_employee IS NULL THEN
    ...
END IF;
~~~

Use a status flag or check an identifying field:

~~~sql
IF l_employee.employee_id IS NULL THEN
    ...
END IF;
~~~

If employee_id can legitimately be NULL in an incomplete state, use an additional BOOLEAN flag like l_loaded to distinguish "record not loaded" from "record loaded but this field is NULL."

## 4. Anchoring Field Datatypes with %TYPE

When a record represents table data, hard-coding lengths and precision can cause PL/SQL types to drift from the schema. The %TYPE attribute lets a field inherit the datatype of an existing column or variable.

### 4.1. column%TYPE Syntax

~~~sql
DECLARE
    TYPE employee_rec IS RECORD (
        employee_id employee_data_lab.employee_id%TYPE,
        full_name employee_data_lab.full_name%TYPE,
        department_id employee_data_lab.department_id%TYPE,
        work_email employee_data_lab.work_email%TYPE
    );

    l_employee employee_rec;
BEGIN
    ...
END;
/
~~~

If a column's datatype changes, the recompiled record follows the new type without editing individual length/precision declarations.

### 4.2. %TYPE Does Not Copy Every Constraint

%TYPE retrieves the datatype and certain type-related attributes from the referenced column/variable, but it does not turn a record field into a table column with full constraints. For example, declaring from a NOT NULL column does not automatically protect the record field with a NOT NULL constraint like the source column.

Validate required data in PL/SQL logic or declare NOT NULL/defaults on the record where appropriate.

### 4.3. Anchoring to a PL/SQL Variable

%TYPE can also reference a variable:

~~~sql
DECLARE
    v_default_amount NUMBER(12,2);

    TYPE payment_rec IS RECORD (
        payment_id NUMBER,
        amount v_default_amount%TYPE
    );

    l_payment payment_rec;
BEGIN
    ...
END;
/
~~~

In many applications, anchoring to a table column is clearer because it shows which schema object the record is tied to.

## 5. Using %ROWTYPE for an Entire Row

If a record needs the exact structure of a table or view row, %ROWTYPE avoids re-declaring every field.

### 5.1. table%ROWTYPE

~~~sql
DECLARE
    l_employee employee_data_lab%ROWTYPE;
BEGIN
    SELECT *
    INTO l_employee
    FROM employee_data_lab
    WHERE employee_id = 101;

    DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
    DBMS_OUTPUT.PUT_LINE(l_employee.monthly_salary);
END;
/
~~~

EMPLOYEE_DATA_LAB%ROWTYPE creates a record with one field per column of the table. Field names match column names, and datatypes track the columns.

### 5.2. view%ROWTYPE

You can anchor to a view:

~~~sql
DECLARE
    l_directory_row v_employee_directory_lab%ROWTYPE;
BEGIN
    SELECT *
    INTO l_directory_row
    FROM v_employee_directory_lab
    WHERE employee_id = 101;

    DBMS_OUTPUT.PUT_LINE(l_directory_row.full_name);
END;
/
~~~

The record only contains the columns exposed by the view. This is useful when a procedure should work only with a specific projection rather than the entire base table row.

### 5.3. Advantages and Trade-Offs of %ROWTYPE

Advantages:

- Concise declaration.
- Tracks table/view structure.
- Suitable when processing nearly a full row.
- Reduces risk of datatype mismatch.

Trade-offs:

- The procedure depends on the table/view structure.
- If the table has many unneeded columns, the record carries more fields as well.
- SELECT * makes code sensitive to schema changes.
- Not every field is appropriate to expose in an API.

If only 3 out of 30 columns are needed, an explicit RECORD or a view projection usually makes dependencies clearer.

### 5.4. %ROWTYPE Does Not Inherit Table Constraints/Defaults

%ROWTYPE provides the field structure and corresponding datatypes, but it does not copy NOT NULL, defaults, check constraints, or foreign key constraints into automatic rules on the record variable.

For example, a NOT NULL table column can correspond to a record field that code might leave unassigned. Constraints are enforced when DML writes to the table, not on every PL/SQL field assignment.

### 5.5. SELECT * Matches When Using %ROWTYPE on the Right Object

~~~sql
SELECT *
INTO l_employee
FROM employee_data_lab
WHERE employee_id = 101;
~~~

Here SELECT * matches the rowtype structure of the same table. If selecting only a subset of columns, use a matching record type or INTO individual fields. Do not select an arbitrary subset of columns INTO a %ROWTYPE with a different structure.

## 6. Cursor%ROWTYPE for Query Results

A SELECT result does not have to match a single table. Cursor%ROWTYPE produces a record matching the cursor's column list.

### 6.1. Declaring an Explicit Cursor

~~~sql
DECLARE
    CURSOR c_active_employee IS
        SELECT
            employee_id,
            full_name,
            department_id,
            work_email
        FROM employee_data_lab
        WHERE employment_status = 'ACTIVE';

    l_employee c_active_employee%ROWTYPE;
BEGIN
    OPEN c_active_employee;

    FETCH c_active_employee INTO l_employee;

    IF c_active_employee%FOUND THEN
        DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
    END IF;

    CLOSE c_active_employee;
END;
/
~~~

The cursor record contains the columns/expressions selected in the cursor, not all table columns.

### 6.2. Cursor FOR LOOP Creates an Implicit Record

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, full_name, department_id
        FROM employee_data_lab
        WHERE employment_status = 'ACTIVE';
BEGIN
    FOR r_employee IN c_employee LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_employee.employee_id || ': ' ||
            r_employee.full_name
        );
    END LOOP;
END;
/
~~~

The variable r_employee is implicitly declared by the cursor FOR LOOP and matches the cursor's select list. Oracle automatically opens the cursor, fetches each row, and closes the cursor when the loop ends or exits scope.

### 6.3. Inline Cursor FOR LOOP

~~~sql
BEGIN
    FOR r_order IN (
        SELECT order_id, customer_id, order_date
        FROM orders_lab
        WHERE order_date >= DATE '2026-01-01'
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_order.order_id || ' / ' ||
            r_order.customer_id
        );
    END LOOP;
END;
/
~~~

This is a concise way to do sequential processing. If you need to pass the record outward or reuse the type across subprograms, declare the cursor/type explicitly in a package.

## 7. SELECT INTO a RECORD

### 7.1. SELECT Column List into an Explicit Record

~~~sql
DECLARE
    TYPE employee_summary_rec IS RECORD (
        employee_id NUMBER,
        full_name VARCHAR2(80),
        department_id NUMBER
    );

    l_employee employee_summary_rec;
BEGIN
    SELECT employee_id, full_name, department_id
    INTO l_employee
    FROM employee_data_lab
    WHERE employee_id = 101;

    DBMS_OUTPUT.PUT_LINE(
        l_employee.employee_id || ' - ' ||
        l_employee.full_name
    );
END;
/
~~~

The SELECT list must match the record fields in count, order, and compatible datatypes. Write an explicit column list instead of relying on implicit ordering.

### 7.2. SELECT INTO Must Return Exactly One Row

SELECT INTO is a single-row query:

- No rows: raises NO_DATA_FOUND.
- More than one row: raises TOO_MANY_ROWS.
- Exactly one row: assigns values into the record.

Handling example:

~~~sql
DECLARE
    l_employee employee_data_lab%ROWTYPE;
BEGIN
    BEGIN
        SELECT *
        INTO l_employee
        FROM employee_data_lab
        WHERE employee_id = 999999;

        DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_OUTPUT.PUT_LINE('Employee not found');
        WHEN TOO_MANY_ROWS THEN
            DBMS_OUTPUT.PUT_LINE('Query returned more than one row');
    END;
END;
/
~~~

If the predicate is expected to be unique, enforce that assumption with a primary key/unique constraint. Do not use ROWNUM = 1 to hide duplicate rows when business rules require uniqueness.

### 7.3. Using Aggregate SELECT INTO a Record

~~~sql
DECLARE
    TYPE department_stats_rec IS RECORD (
        department_id NUMBER,
        employee_count NUMBER,
        average_salary NUMBER
    );

    l_stats department_stats_rec;
BEGIN
    SELECT
        10,
        COUNT(*),
        AVG(monthly_salary)
    INTO l_stats
    FROM employee_data_lab
    WHERE department_id = 10
      AND employment_status = 'ACTIVE';

    DBMS_OUTPUT.PUT_LINE(l_stats.employee_count);
END;
/
~~~

Aggregates without GROUP BY generally return one row, even when no source rows match; COUNT(*) returns 0, while other aggregates like AVG return NULL when there are no values. Design the record and handle NULL according to those semantics.

## 8. DML RETURNING INTO and Record Fields

An INSERT/UPDATE/DELETE statement can return affected column values into PL/SQL variables using RETURNING INTO. Values can be returned into individual fields of a record:

~~~sql
DECLARE
    TYPE created_order_rec IS RECORD (
        order_id NUMBER,
        status VARCHAR2(12)
    );

    l_created created_order_rec;
BEGIN
    INSERT INTO orders_lab (
        order_id,
        customer_id,
        order_date,
        status,
        total_amount
    )
    VALUES (
        9001,
        501,
        DATE '2026-04-10',
        'NEW',
        125
    )
    RETURNING order_id, status
    INTO l_created.order_id, l_created.status;

    DBMS_OUTPUT.PUT_LINE(
        'Created order ' || l_created.order_id ||
        ' status=' || l_created.status
    );

    ROLLBACK;
END;
/
~~~

RETURNING INTO takes a list of target variables. Using individual record fields helps express the returned data clearly. The statement still obeys transactions; ROLLBACK in the example undoes the INSERT.

## 9. Nested RECORDs for Multi-Level Data Modeling

A business entity can contain nested attribute groups. For instance, a customer has identity info and an address; the address in turn consists of street, district, city, and postal code.

### 9.1. Declaring a Nested Record

~~~sql
DECLARE
    TYPE address_rec IS RECORD (
        street VARCHAR2(120),
        district VARCHAR2(60),
        city VARCHAR2(60),
        postal_code VARCHAR2(20)
    );

    TYPE customer_rec IS RECORD (
        customer_id NUMBER,
        full_name VARCHAR2(100),
        email VARCHAR2(120),
        address address_rec
    );

    l_customer customer_rec;
BEGIN
    l_customer.customer_id := 501;
    l_customer.full_name := 'Tran Minh';
    l_customer.email := 'minh@example.test';
    l_customer.address.street := '25 Le Loi';
    l_customer.address.district := 'District 1';
    l_customer.address.city := 'Ho Chi Minh City';
    l_customer.address.postal_code := '700000';

    DBMS_OUTPUT.PUT_LINE(
        l_customer.full_name || ' lives in ' ||
        l_customer.address.city
    );
END;
/
~~~

Nested records group attributes semantically. They avoid a flat record with dozens of fields having repetitive prefixes like BILLING_CITY, SHIPPING_CITY, BILLING_POSTAL_CODE, SHIPPING_POSTAL_CODE.

### 9.2. Two Addresses Sharing One Type

~~~sql
DECLARE
    TYPE address_rec IS RECORD (
        street VARCHAR2(120),
        city VARCHAR2(60),
        postal_code VARCHAR2(20)
    );

    TYPE customer_rec IS RECORD (
        customer_id NUMBER,
        billing_address address_rec,
        shipping_address address_rec
    );

    l_customer customer_rec;
BEGIN
    l_customer.customer_id := 501;
    l_customer.billing_address.city := 'Ho Chi Minh City';
    l_customer.shipping_address.city := 'Da Nang';
END;
/
~~~

The two address fields share one type, yet hold two independent values. Modifying billing_address does not modify shipping_address.

### 9.3. Choosing a Reasonable Depth

Nested records are helpful when attribute groups have distinct meaning and are processed together. Do not nest too deeply just to mirror every relationship in the database. In-memory structures serve code; the relational model in the database serves storage, constraints, querying, and integrity.

## 10. RECORDs in Package Specifications: Building PL/SQL APIs

When multiple procedures/functions need to exchange the same structure, publish the record type in a package specification. Consumers can declare variables using that public type.

### 10.1. Declaring a Public Record Type

~~~sql
CREATE OR REPLACE PACKAGE employee_api_lab AS
    TYPE employee_info_rec IS RECORD (
        employee_id employee_data_lab.employee_id%TYPE,
        full_name employee_data_lab.full_name%TYPE,
        department_id employee_data_lab.department_id%TYPE,
        work_email employee_data_lab.work_email%TYPE
    );

    PROCEDURE get_employee (
        p_employee_id IN employee_data_lab.employee_id%TYPE,
        p_employee OUT employee_info_rec
    );
END employee_api_lab;
/
~~~

The package specification publishes the type and procedure signature. Callers can reference it:

~~~sql
DECLARE
    l_employee employee_api_lab.employee_info_rec;
BEGIN
    employee_api_lab.get_employee(
        p_employee_id => 101,
        p_employee => l_employee
    );

    DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
END;
/
~~~

### 10.2. Implementing the Package Body

~~~sql
CREATE OR REPLACE PACKAGE BODY employee_api_lab AS
    PROCEDURE get_employee (
        p_employee_id IN employee_data_lab.employee_id%TYPE,
        p_employee OUT employee_info_rec
    ) IS
    BEGIN
        SELECT
            employee_id,
            full_name,
            department_id,
            work_email
        INTO p_employee
        FROM employee_data_lab
        WHERE employee_id = p_employee_id;
    END get_employee;
END employee_api_lab;
/
~~~

A package type establishes a shared contract between producer and consumer. Whenever a public record needs to change, treat it as an API change that may impact all callers and dependent PL/SQL units.

### 10.3. IN, OUT, and IN OUT

Records can be passed as parameters:

- IN: procedure reads the record value passed by the caller.
- OUT: procedure constructs the result and returns the record to the caller.
- IN OUT: procedure reads and then modifies the record.

Example:

~~~sql
CREATE OR REPLACE PACKAGE employee_rules_lab AS
    TYPE employee_rec IS RECORD (
        employee_id NUMBER,
        full_name VARCHAR2(80),
        department_id NUMBER
    );

    PROCEDURE normalize_employee (
        p_employee IN OUT employee_rec
    );
END employee_rules_lab;
/

CREATE OR REPLACE PACKAGE BODY employee_rules_lab AS
    PROCEDURE normalize_employee (
        p_employee IN OUT employee_rec
    ) IS
    BEGIN
        p_employee.full_name := TRIM(p_employee.full_name);
    END normalize_employee;
END employee_rules_lab;
/
~~~

An OUT/IN OUT record is data passed within PL/SQL calls. Do not confuse it with returning a record directly from a SQL query to an external client outside the database.

### 10.4. Placing Types in the Right Scope

| Where Declared | Usage Scope |
| --- | --- |
| DECLARE block | That block and nested sub-blocks |
| Declarative part of procedure/function | That subprogram and its body |
| Package specification | Public API for consumers with execute privileges on the package |
| Package body | Internal to the package body |

If a type serves only one procedure, declare it locally. If multiple subprograms share it and callers need to create variables of that type, declare it in the package specification.

## 11. Collections Holding Multiple RECORDs

A RECORD represents a single multi-field structure. When multiple rows are needed, you can use a collection of records.

### 11.1. Declaring an Associative Array of Records

~~~sql
DECLARE
    TYPE employee_rec IS RECORD (
        employee_id employee_data_lab.employee_id%TYPE,
        full_name employee_data_lab.full_name%TYPE,
        department_id employee_data_lab.department_id%TYPE
    );

    TYPE employee_tab IS TABLE OF employee_rec
        INDEX BY PLS_INTEGER;

    l_employees employee_tab;
BEGIN
    l_employees(1).employee_id := 101;
    l_employees(1).full_name := 'Nguyen An';
    l_employees(1).department_id := 10;

    l_employees(2).employee_id := 102;
    l_employees(2).full_name := 'Tran Binh';
    l_employees(2).department_id := 10;

    DBMS_OUTPUT.PUT_LINE(l_employees(2).full_name);
END;
/
~~~

An associative array uses keys to access elements. In this example, each element is an employee_rec. Collections and records are two different structural levels: a collection holds multiple elements, and each element has multiple fields.

### 11.2. BULK COLLECT into a Collection of Records

~~~sql
DECLARE
    TYPE employee_tab IS TABLE OF employee_data_lab%ROWTYPE
        INDEX BY PLS_INTEGER;

    l_employees employee_tab;
BEGIN
    SELECT *
    BULK COLLECT INTO l_employees
    FROM employee_data_lab
    WHERE department_id = 10
    ORDER BY employee_id;

    FOR i IN 1 .. l_employees.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            l_employees(i).employee_id || ' - ' ||
            l_employees(i).full_name
        );
    END LOOP;
END;
/
~~~

BULK COLLECT retrieves multiple rows into a collection in a single PL/SQL/SQL boundary crossing. It can reduce context switching compared to row-by-row fetching in a loop, though holding all results in memory can consume substantial PGA if the dataset is large.

### 11.3. BULK COLLECT with LIMIT

For large datasets, use a cursor and FETCH BULK COLLECT LIMIT to process in batches:

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT *
        FROM employee_data_lab
        ORDER BY employee_id;

    TYPE employee_tab IS TABLE OF c_employee%ROWTYPE
        INDEX BY PLS_INTEGER;

    l_batch employee_tab;
BEGIN
    OPEN c_employee;

    LOOP
        FETCH c_employee
        BULK COLLECT INTO l_batch
        LIMIT 500;

        EXIT WHEN l_batch.COUNT = 0;

        FOR i IN 1 .. l_batch.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(l_batch(i).full_name);
        END LOOP;
    END LOOP;

    CLOSE c_employee;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employee%ISOPEN THEN
            CLOSE c_employee;
        END IF;
        RAISE;
END;
/
~~~

LIMIT bounds the number of rows fetched per batch, helping control memory usage. In real applications, processing inside the loop should have a clear purpose and should not use DBMS_OUTPUT for large data volumes.

### 11.4. Empty Collections and COUNT

For an associative array with no elements, COUNT returns 0. Thus:

~~~sql
IF l_employees.COUNT = 0 THEN
    DBMS_OUTPUT.PUT_LINE('No employees');
END IF;
~~~

Do not access unassigned elements. For associative arrays with non-contiguous keys, do not assume indices always run from 1 to COUNT; use FIRST/NEXT or appropriate collection methods.

### 11.5. FORALL and Record Collections

FORALL executes bulk DML with collections, reducing context switching. You can design a collection of records to keep grouped data together; when referencing collection fields in DML, follow supported bulk binding syntax and test on your target release.

Simple example using scalar collections:

~~~sql
DECLARE
    TYPE id_tab IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE salary_tab IS TABLE OF NUMBER INDEX BY PLS_INTEGER;

    l_ids id_tab;
    l_salaries salary_tab;
BEGIN
    l_ids(1) := 101;
    l_ids(2) := 102;
    l_salaries(1) := 2600;
    l_salaries(2) := 3300;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employee_data_lab
        SET monthly_salary = l_salaries(i)
        WHERE employee_id = l_ids(i);
END;
/
~~~

This example uses two parallel scalar collections with matching indices. If using a collection of records in FORALL, verify record-field reference syntax in DML and index contiguity; do not force data into a record collection just to shorten code.

## 12. RECORDs and the SQL Engine: Boundaries to Remember

PL/SQL and SQL are two engines with different datatypes and scopes. RECORD is a PL/SQL datatype; it cannot be treated like a regular SQL column type.

### 12.1. PL/SQL RECORD Is Not a SQL Object Type

| Characteristic | PL/SQL RECORD | SQL Object Type |
| --- | --- | --- |
| Declaration | TYPE ... IS RECORD in PL/SQL | CREATE TYPE ... AS OBJECT in schema |
| Scope | PL/SQL block/subprogram/package | SQL schema object |
| Usable as a table column | Not directly | Yes, subject to SQL type rules |
| Can have methods | Not like object types | Can define methods |
| Usable in PL/SQL | Yes | Yes |
| Usable directly in SQL | Limited; not a SQL datatype | Supported by the SQL engine |

If you need to store a multi-attribute structure as an object column, pass it through SQL/clients, or use it in SQL expressions, study SQL object types and nested table/varray types. If you only need to group data inside PL/SQL, RECORD is usually simpler.

### 12.2. Cannot Declare Table Columns with a Local RECORD Type

You cannot use a type declared in DECLARE to create a SQL column:

~~~sql
DECLARE
    TYPE address_rec IS RECORD (
        city VARCHAR2(60),
        postal_code VARCHAR2(20)
    );
BEGIN
    -- address_rec is not a SQL datatype for declaring table columns.
    NULL;
END;
/
~~~

To store the data, create separate scalar columns or define a SQL object type:

~~~sql
CREATE TYPE address_obj_lab AS OBJECT (
    city VARCHAR2(60),
    postal_code VARCHAR2(20)
);
/

CREATE TABLE customer_object_lab (
    customer_id NUMBER PRIMARY KEY,
    address_info address_obj_lab
);
~~~

SQL object types have a different schema lifecycle and semantics than local record types.

### 12.3. Cannot Return a PL/SQL RECORD as an Arbitrary SQL Column

A PL/SQL procedure can accept/return a record parameter to a compatible PL/SQL caller. However, do not assume a pure SQL SELECT statement can call a function returning a local PL/SQL RECORD like a scalar SQL value. The SQL engine needs datatypes that SQL understands.

If an API must be callable from SQL or clients over a SQL interface, consider:

- SQL object types.
- Scalar columns.
- REF CURSOR for result sets.
- JSON/XML per contract and version.
- A package procedure returning OUT scalars or a cursor.

### 12.4. RECORD Does Not Replace the Relational Model

An in-memory customer record can hold a nested address record, yet a relational database may still store CUSTOMER and ADDRESS in separate tables to support:

- Integrity constraints.
- Queries and joins.
- Address reuse.
- Change history.
- Transactions and concurrency.

Records are a way to organize data in PL/SQL, not a directive to merge tables into a single storage structure.

## 13. Designing Multi-Field Models by Business Domain

### 13.1. Order Model

An order typically has a header and multiple lines:

~~~text
ORDER
  order_id
  customer_id
  order_date
  status
  shipping_address
      street
      city
      postal_code
  lines[]
      line_id
      product_id
      quantity
      unit_price
~~~

In PL/SQL, this can be modeled as:

~~~sql
DECLARE
    TYPE address_rec IS RECORD (
        street VARCHAR2(120),
        city VARCHAR2(60),
        postal_code VARCHAR2(20)
    );

    TYPE order_header_rec IS RECORD (
        order_id NUMBER,
        customer_id NUMBER,
        order_date DATE,
        status VARCHAR2(12),
        shipping_address address_rec
    );

    TYPE order_line_rec IS RECORD (
        line_id NUMBER,
        product_id NUMBER,
        quantity NUMBER(10,2),
        unit_price NUMBER(12,2)
    );

    TYPE order_line_tab IS TABLE OF order_line_rec
        INDEX BY PLS_INTEGER;

    l_order order_header_rec;
    l_lines order_line_tab;
BEGIN
    l_order.order_id := 9001;
    l_order.customer_id := 501;
    l_order.order_date := SYSDATE;
    l_order.status := 'NEW';
    l_order.shipping_address.city := 'Ho Chi Minh City';

    l_lines(1).line_id := 1;
    l_lines(1).product_id := 100;
    l_lines(1).quantity := 2;
    l_lines(1).unit_price := 25;

    l_lines(2).line_id := 2;
    l_lines(2).product_id := 200;
    l_lines(2).quantity := 1;
    l_lines(2).unit_price := 80;
END;
/
~~~

Here the order header is a record, the address is a nested record, and the order lines are a collection of records. This model represents a one-order-to-many-lines relationship in memory.

### 13.2. Separating Required and Optional Data

When designing a record, distinguish:

- Identifier fields: usually required to identify the entity.
- Required business fields: need validation before persistence.
- Optional fields: can be NULL.
- Computed fields: derivable from other fields.
- Status fields: reflect lifecycle state.

Do not leave a record in a half-initialized state where downstream code does not know which fields were assigned. You can use a factory procedure, validation function, or initialized flag for control.

### 13.3. Creating a Record Validation Procedure

~~~sql
DECLARE
    TYPE payment_rec IS RECORD (
        payment_id NUMBER,
        customer_id NUMBER,
        amount NUMBER(12,2),
        currency_code VARCHAR2(3)
    );

    l_payment payment_rec;

    PROCEDURE validate_payment(p_payment IN payment_rec) IS
    BEGIN
        IF p_payment.payment_id IS NULL THEN
            RAISE_APPLICATION_ERROR(-20001, 'Payment ID is required');
        END IF;

        IF p_payment.customer_id IS NULL THEN
            RAISE_APPLICATION_ERROR(-20002, 'Customer ID is required');
        END IF;

        IF p_payment.amount IS NULL OR p_payment.amount <= 0 THEN
            RAISE_APPLICATION_ERROR(-20003, 'Amount must be positive');
        END IF;

        IF p_payment.currency_code IS NULL
           OR LENGTH(p_payment.currency_code) <> 3
        THEN
            RAISE_APPLICATION_ERROR(-20004, 'Invalid currency code');
        END IF;
    END validate_payment;
BEGIN
    l_payment.payment_id := 7001;
    l_payment.customer_id := 501;
    l_payment.amount := 125.50;
    l_payment.currency_code := 'VND';

    validate_payment(l_payment);
END;
/
~~~

Validation in PL/SQL provides clear business errors. Table constraints are still necessary to protect data when other write paths exist, such as batch jobs, SQL clients, or other services.

## 14. Error Handling When Working with RECORDs

### 14.1. NO_DATA_FOUND

SELECT INTO finding no rows raises NO_DATA_FOUND. If "not found" is a valid state, handle it explicitly:

~~~sql
DECLARE
    l_employee employee_data_lab%ROWTYPE;
BEGIN
    BEGIN
        SELECT *
        INTO l_employee
        FROM employee_data_lab
        WHERE employee_id = 999;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_OUTPUT.PUT_LINE('No matching employee');
            RETURN;
    END;

    DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
END;
/
~~~

### 14.2. TOO_MANY_ROWS

If a query can return multiple rows, use a cursor or collection instead of SELECT INTO a single record. Do not catch TOO_MANY_ROWS and pick an arbitrary result unless business logic defines a selection rule.

### 14.3. NULL Fields

A record field can be NULL. Comparison:

~~~sql
IF l_employee.work_email IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('No work email');
END IF;
~~~

Do not use equality comparison against NULL. If two nullable values must be compared, define the semantics clearly:

~~~sql
IF l_old_email = l_new_email
   OR (l_old_email IS NULL AND l_new_email IS NULL)
THEN
    -- Values are considered equal under this convention.
    NULL;
END IF;
~~~

### 14.4. OUT Records on Exception

If a procedure has an OUT record and raises an exception before populating it completely, callers should not assume the record holds a complete result. You should:

- Assign the output only after reading/validating all required data.
- Use a status code or exception to signal failure.
- Avoid swallowing exceptions and returning a half-populated record.
- Document when an OUT record is guaranteed to be populated.

## 15. Performance and Best Practices

### 15.1. Records Do Not Automatically Make SQL Faster

RECORD mainly improves how data is organized in PL/SQL. It does not replace indexes, reduce block reads, or automatically convert row-by-row SQL into bulk SQL.

Performance depends on how data is fetched:

- SELECT INTO a record: single row.
- Cursor FOR LOOP: row-by-row fetching via the cursor loop mechanism.
- BULK COLLECT: multi-row fetching in batches.
- FORALL: bulk DML with collections.

### 15.2. Use %ROWTYPE When You Truly Need the Full Row

If only a few fields are needed, an explicit record or cursor record with a minimal select list helps:

- Reduce unnecessary data transfer.
- Make dependencies clear.
- Limit coupling to wide schemas.
- Avoid reading sensitive columns unnecessarily.

### 15.3. Use %TYPE to Avoid Hard-Coding Datatypes

Column-anchored datatypes help code stay aligned with schema precision/length on recompile. Still, column changes can impact APIs and require regression testing.

### 15.4. Use Package Types for Shared Contracts

If a record crosses multiple procedures or is constructed directly by callers, place the type in the package specification. Avoid duplicating identical record types across multiple locations, which increases maintenance burden and structural drift.

### 15.5. Do Not Fetch an Entire Table into a Collection Unnecessarily

Unbounded BULK COLLECT can consume large amounts of PGA. Use LIMIT, proper predicates, or key-range processing when data volume is large.

### 15.6. Keep Records Focused on Clear Responsibilities

A record should represent one coherent concept. Avoid stuffing data from many unrelated tables into one giant record just for convenience. Use nested records or separate record types for headers, details, addresses, and payments.

### 15.7. Do Not Use Records to Bypass Constraints

Validating data in PL/SQL is important, but it does not replace database constraints. If two sessions or two applications write data concurrently, constraints act as the shared defense layer in the database.

## 16. Comprehensive Practice Lab

This lab uses an employee table in the lab schema. If the table does not exist yet, create it:

~~~sql
CREATE TABLE employee_data_lab (
    employee_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER NOT NULL,
    work_email VARCHAR2(120 CHAR),
    monthly_salary NUMBER(12,2) NOT NULL,
    employment_status VARCHAR2(12 CHAR) NOT NULL
);

INSERT INTO employee_data_lab VALUES
    (101, 'Nguyen An', 10, 'an@example.test', 2500, 'ACTIVE');
INSERT INTO employee_data_lab VALUES
    (102, 'Tran Binh', 10, 'binh@example.test', 3200, 'ACTIVE');
INSERT INTO employee_data_lab VALUES
    (103, 'Le Chi', 20, 'chi@example.test', 2800, 'ACTIVE');
COMMIT;
~~~

### Step 1 — Declare a Record with %TYPE

~~~sql
DECLARE
    TYPE employee_rec IS RECORD (
        employee_id employee_data_lab.employee_id%TYPE,
        full_name employee_data_lab.full_name%TYPE,
        department_id employee_data_lab.department_id%TYPE,
        work_email employee_data_lab.work_email%TYPE
    );

    l_employee employee_rec;
BEGIN
    SELECT employee_id, full_name, department_id, work_email
    INTO l_employee
    FROM employee_data_lab
    WHERE employee_id = 101;

    DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
END;
/
~~~

### Step 2 — Use %ROWTYPE

~~~sql
DECLARE
    l_employee employee_data_lab%ROWTYPE;
BEGIN
    SELECT *
    INTO l_employee
    FROM employee_data_lab
    WHERE employee_id = 102;

    DBMS_OUTPUT.PUT_LINE(
        l_employee.employee_id || ' ' ||
        l_employee.full_name || ' ' ||
        l_employee.monthly_salary
    );
END;
/
~~~

### Step 3 — Cursor Record

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, full_name, department_id
        FROM employee_data_lab
        WHERE employment_status = 'ACTIVE';
BEGIN
    FOR r IN c_employee LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.employee_id || ': ' || r.full_name
        );
    END LOOP;
END;
/
~~~

### Step 4 — Package API Returning a Record

~~~sql
CREATE OR REPLACE PACKAGE employee_record_api_lab AS
    TYPE employee_rec IS RECORD (
        employee_id employee_data_lab.employee_id%TYPE,
        full_name employee_data_lab.full_name%TYPE,
        department_id employee_data_lab.department_id%TYPE
    );

    PROCEDURE find_employee (
        p_employee_id IN employee_data_lab.employee_id%TYPE,
        p_employee OUT employee_rec
    );
END employee_record_api_lab;
/

CREATE OR REPLACE PACKAGE BODY employee_record_api_lab AS
    PROCEDURE find_employee (
        p_employee_id IN employee_data_lab.employee_id%TYPE,
        p_employee OUT employee_rec
    ) IS
    BEGIN
        SELECT employee_id, full_name, department_id
        INTO p_employee
        FROM employee_data_lab
        WHERE employee_id = p_employee_id;
    END find_employee;
END employee_record_api_lab;
/
~~~

Call the API:

~~~sql
DECLARE
    l_employee employee_record_api_lab.employee_rec;
BEGIN
    employee_record_api_lab.find_employee(103, l_employee);
    DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
END;
/
~~~

### Step 5 — BULK COLLECT Multiple Records

~~~sql
DECLARE
    TYPE employee_tab IS TABLE OF employee_data_lab%ROWTYPE
        INDEX BY PLS_INTEGER;

    l_employees employee_tab;
BEGIN
    SELECT *
    BULK COLLECT INTO l_employees
    FROM employee_data_lab
    WHERE department_id = 10
    ORDER BY employee_id;

    FOR i IN 1 .. l_employees.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            l_employees(i).employee_id || ': ' ||
            l_employees(i).full_name
        );
    END LOOP;
END;
/
~~~

### Step 6 — Lab Cleanup (Optional)

Run only if you are sure these are the lab table/package you created and no longer need the data:

~~~sql
DROP PACKAGE employee_record_api_lab;
DROP TABLE employee_data_lab PURGE;
~~~

DROP PACKAGE and DROP TABLE are DDL statements, which issue implicit commits under Oracle rules. Do not run them on real business objects.

## 17. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| RECORD is a temporary table | RECORD is a PL/SQL datatype in memory |
| RECORD and collection are the same | RECORD groups multiple fields; collection holds multiple elements |
| %ROWTYPE inherits all table constraints/defaults | It follows structure and datatypes, not turning PL/SQL variables into constrained rows |
| %TYPE creates a completely independent datatype | It anchors the datatype to the referenced column/variable |
| Two records with the same fields can always be assigned | They need the same/compatible type; use a shared type in a package API |
| SELECT INTO a record can return multiple rows | SELECT INTO requires exactly one row |
| Cursor%ROWTYPE always holds all table columns | It holds the cursor's select list |
| Whole records can be compared with = | Compare fields or write custom comparison logic |
| An entire record can be checked with IS NULL | Check an identifier field or an initialized flag |
| PL/SQL RECORD can be used directly as a SQL column | Needs an appropriate SQL datatype/object type |
| BULK COLLECT is always better than a cursor loop | It can consume substantial PGA; use LIMIT when needed |
| RECORD automatically guarantees valid data | Constraints/validation are still needed at appropriate layers |

## 18. Self-Check Questions

1. What is a RECORD and what does a record typically represent?
2. How does TYPE ... IS RECORD differ from a record variable?
3. What syntax accesses a record field?
4. Can a record field declare a default value?
5. What must you keep in mind if a record field is declared NOT NULL?
6. What is %TYPE used for?
7. Does %TYPE automatically inherit all column constraints?
8. How does %ROWTYPE differ from an explicit RECORD?
9. Why can't %ROWTYPE replace every explicit record?
10. Which fields does Cursor%ROWTYPE contain?
11. How many rows does SELECT INTO a record require?
12. When do NO_DATA_FOUND and TOO_MANY_ROWS occur?
13. When can you assign an entire record?
14. Which Oracle version introduced qualified expressions?
15. Why shouldn't two records be compared with the = operator?
16. What kind of data do nested records help model?
17. Why declare record types in a package specification?
18. How do IN, OUT, and IN OUT apply to record parameters?
19. How do RECORDs and collections differ?
20. What does BULK COLLECT LIMIT help control?
21. Why can't a PL/SQL RECORD be used directly as a SQL table column?
22. When should you use a SQL object type?
23. Does RECORD replace transactions or constraints?
24. Why shouldn't you BULK COLLECT an entire very large table into PGA?
25. After changing a public record type in a package, what should be reviewed?

**Answer hints:**

1. A PL/SQL type with multiple named fields; usually represents a row or a business structure.
2. TYPE defines the structure; a record variable holds a value conforming to that structure.
3. record_variable.field_name.
4. Yes.
5. It must have a valid default and must not be assigned NULL.
6. Anchoring a datatype to an existing column or variable.
7. No.
8. %ROWTYPE derives its structure from a table/view/cursor; explicit RECORD lets you choose and name fields per contract.
9. It can be too wide or create coupling to the entire table.
10. The columns/expressions in the cursor's select list.
11. Exactly one row.
12. Zero rows or more than one row.
13. When two variables share the same compatible record type.
14. Oracle Database 18c and later.
15. PL/SQL does not provide general equality for whole records.
16. Subgroups of attributes such as an address in a customer or shipping address in an order.
17. So multiple subprograms and callers share the same type contract.
18. IN reads, OUT returns a result, IN OUT reads and modifies the record.
19. RECORD holds multiple fields in one item; a collection holds multiple items.
20. The number of rows kept in memory per batch.
21. RECORD is a PL/SQL datatype, not a SQL schema datatype.
22. When a datatype understood by the SQL engine is needed for storage in columns or use in SQL expressions.
23. No; records only organize data in memory.
24. It can consume excessive PGA and cause memory pressure.
25. Callers, dependencies, datatypes, semantics, and API compatibility.

## Oracle Reference Documentation

- [Oracle Database PL/SQL Language Reference — Record Types](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/record-types.html): declaring, using, and manipulating records.
- [Oracle Database PL/SQL Language Reference — %ROWTYPE Attribute](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/ROWTYPE-attribute.html): records based on table/view/cursor rows.
- [Oracle Database PL/SQL Language Reference — %TYPE Attribute](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/TYPE-attribute.html): anchoring datatypes to columns or variables.
- [Oracle Database PL/SQL Language Reference — Assigning Values to Records](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/assigning-values-records.html): assigning values to records.
- [Oracle Database PL/SQL Language Reference — Cursor Variables and Explicit Cursors](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/cursors-overview.html): cursors, fetching, and cursor row types.
- [Oracle Database PL/SQL Language Reference — BULK COLLECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/bulk-sql-and-bulk-binding.html): bulk SQL, collections, and fetch limits.
- [Oracle Database SQL Language Reference — Object Types](https://docs.oracle.com/en/database/oracle/oracle-database/19/adobj/): SQL object types and SQL usage.

**Rule to remember:** RECORD groups related fields into a single structured PL/SQL value. Use an explicit RECORD when defining a minimal contract; use %TYPE to anchor datatypes; use %ROWTYPE when you need the full row structure; use cursor%ROWTYPE for query results; and use a collection of records when multiple rows are needed. Remember that RECORD is an in-memory PL/SQL type, not a SQL object type or storage table.

# JSON_OBJECT, JSON_ARRAY, and JSON Aggregate Functions in Oracle Database

Oracle provides a group of SQL/JSON generation functions to create JSON directly from relational data. Instead of manually concatenating strings and escaping quotes, slashes, and control characters yourself, you can use **JSON_OBJECT**, **JSON_ARRAY**, **JSON_OBJECTAGG**, and **JSON_ARRAYAGG** to produce valid JSON structures directly in a SELECT statement.

The four functions serve two distinct roles:

- **JSON_OBJECT** creates a JSON object from key/value pairs or the columns of a single row.
- **JSON_ARRAY** creates a JSON array from a list of expressions.
- **JSON_ARRAYAGG** aggregates the results of multiple rows into a single JSON array.
- **JSON_OBJECTAGG** aggregates key/value pairs from multiple rows into a single JSON object.

These functions can be nested to build hierarchical documents—for example, a department with a list of employees, an order with a list of line items, or a product with a set of attributes. In Oracle 19c, the default return type is VARCHAR2(4000); when the JSON may be larger, you need to choose an appropriate return type such as CLOB.

This lesson focuses on the syntax and usage of the four functions, SQL-to-JSON type conversion, NULL handling, FORMAT JSON, RETURNING, STRICT, WITH UNIQUE KEYS, grouped aggregation, element ordering, nested JSON, storing JSON, and performance considerations.

## 1. Overview of the Four JSON Generation Functions

### 1.1. Creating an Object per Row

JSON_OBJECT creates one object for each row returned by the SELECT statement:

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE employee_id,
           'firstName'  VALUE first_name,
           'salary'     VALUE salary
       ) AS employee_json
FROM   employees;
~~~

If the query returns 20 rows, the result has 20 JSON object values. The function does not automatically combine the 20 rows into an array.

### 1.2. Creating an Array from Expressions

JSON_ARRAY creates an array from its arguments in the exact order they are written:

~~~sql
SELECT JSON_ARRAY(
           employee_id,
           first_name,
           salary
       ) AS employee_values
FROM   employees;
~~~

Each row produces its own array. The first element corresponds to employee_id, the second element is first_name, and the third element is salary.

### 1.3. Aggregating Multiple Rows into an Array

JSON_ARRAYAGG is an aggregate function. It turns values from multiple rows into a single JSON array:

~~~sql
SELECT JSON_ARRAYAGG(
           employee_id
           ORDER BY employee_id
           RETURNING CLOB
       ) AS employee_ids
FROM   employees;
~~~

The query above returns a single array value containing the IDs of the selected employees.

### 1.4. Aggregating Multiple Rows into an Object

JSON_OBJECTAGG is an aggregate function that creates a single object from key/value pairs across multiple rows:

~~~sql
SELECT JSON_OBJECTAGG(
           department_name VALUE department_id
           RETURNING CLOB
       ) AS department_map
FROM   departments;
~~~

Each row contributes one member to the object. For example, department name is the key, and department ID is the value.

### 1.5. Comparison Table

| Function | Primary Input | Result | Typical Output Row Count |
| --- | --- | --- | --- |
| JSON_OBJECT | Key/value pairs or columns | A JSON object | One object per source row |
| JSON_ARRAY | List of expressions | A JSON array | One array per source row |
| JSON_ARRAYAGG | Expression from multiple rows | A JSON array | One array per group |
| JSON_OBJECTAGG | Key/value pairs from multiple rows | A JSON object | One object per group |

The two functions without the AGG suffix are typically used to build structures from a single row or an argument list. The two functions with the AGG suffix aggregate data across multiple rows following SQL aggregation rules.

## 2. Preparing Practice Data

The following examples use two small custom tables that do not depend on the HR sample schema.

### 2.1. Creating the Department Table

~~~sql
CREATE TABLE json_demo_dept (
    department_id   NUMBER PRIMARY KEY,
    department_name VARCHAR2(100) NOT NULL,
    location        VARCHAR2(100)
);
~~~

### 2.2. Creating the Employee Table

~~~sql
CREATE TABLE json_demo_emp (
    employee_id   NUMBER PRIMARY KEY,
    department_id NUMBER,
    first_name    VARCHAR2(50) NOT NULL,
    last_name     VARCHAR2(50) NOT NULL,
    salary        NUMBER(10,2),
    commission    NUMBER(5,2),
    hire_date     DATE,
    CONSTRAINT fk_json_demo_emp_dept
        FOREIGN KEY (department_id)
        REFERENCES json_demo_dept(department_id)
);
~~~

### 2.3. Loading Sample Data

~~~sql
INSERT INTO json_demo_dept VALUES (10, 'Engineering', 'Ho Chi Minh City');
INSERT INTO json_demo_dept VALUES (20, 'Finance', 'Ha Noi');
INSERT INTO json_demo_dept VALUES (30, 'Operations', 'Da Nang');
INSERT INTO json_demo_dept VALUES (40, 'Research', NULL);

INSERT INTO json_demo_emp VALUES
    (101, 10, 'An', 'Nguyen', 2500,  NULL, DATE '2022-01-10');

INSERT INTO json_demo_emp VALUES
    (102, 10, 'Binh', 'Tran', 3200, 5, DATE '2021-06-15');

INSERT INTO json_demo_emp VALUES
    (103, 10, 'Chi', 'Le', 2800, NULL, DATE '2023-03-20');

INSERT INTO json_demo_emp VALUES
    (201, 20, 'Dung', 'Pham', 4100, 10, DATE '2020-09-01');

INSERT INTO json_demo_emp VALUES
    (301, 30, 'Giang', 'Vo', 2300, NULL, DATE '2024-02-12');

COMMIT;
~~~

Department 40 does not have any employees yet. This dataset helps observe cases where a subquery returns no rows and how to construct an empty array.

## 3. JSON_OBJECT — Creating a JSON Object

### 3.1. The key VALUE expression Syntax

Clear syntax:

~~~sql
SELECT JSON_OBJECT(
           'id'         VALUE employee_id,
           'firstName'  VALUE first_name,
           'lastName'   VALUE last_name,
           'salary'     VALUE salary
       ) AS employee_json
FROM   json_demo_emp
ORDER  BY employee_id;
~~~

The key name is a string enclosed in single quotes. The VALUE keyword separates the key from the value-generating expression.

You can use a colon instead of the VALUE keyword:

~~~sql
JSON_OBJECT('id' : employee_id)
~~~

However, some client drivers scan for colons to detect bind variables and may misinterpret this separator. Using VALUE is usually clearer and less prone to confusion in SQL tools.

### 3.2. Key Names Are Case-Sensitive

The explicitly provided key name becomes the JSON property name. For example:

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE employee_id,
           'EmployeeName' VALUE first_name
       )
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

The returned JSON has the exact two keys employeeId and EmployeeName. Key naming conventions are part of the JSON API; you should consistently use camelCase, snake_case, or your chosen convention.

### 3.3. Using Column Names as Keys

You can pass column names directly into JSON_OBJECT:

~~~sql
SELECT JSON_OBJECT(
           first_name,
           last_name,
           salary
       )
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

The column name is used as the member name and the column value as the value. This approach is concise, but the key names depend on the column names and how Oracle interprets them. For public APIs, specifying keys explicitly is generally more stable.

### 3.4. Using Wildcards

Oracle supports JSON_OBJECT(*) to include all columns of a row:

~~~sql
SELECT JSON_OBJECT(*)
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

Keys are generated from column names, typically in uppercase. You can use aliases according to supported syntax to restrict the column scope.

Wildcards are convenient for prototyping or generating internal JSON. For APIs requiring a stable schema, wildcards carry risk: when a column is added to the table, the JSON output changes without modifying the SQL statement. Additionally, internal columns or sensitive data may be accidentally exposed in the response.

### 3.5. Nested Objects

You can call JSON_OBJECT inside another JSON_OBJECT:

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE e.employee_id,
           'name' VALUE JSON_OBJECT(
               'first' VALUE e.first_name,
               'last'  VALUE e.last_name
           ),
           'job' VALUE JSON_OBJECT(
               'departmentId' VALUE e.department_id,
               'salary' VALUE e.salary
           )
       ) AS employee_json
FROM   json_demo_emp e
WHERE  e.employee_id = 101;
~~~

The result has a nested object structure. Oracle recognizes the result of the inner JSON generation function as JSON and nests it as an object rather than converting it into a quoted string.

### 3.6. One Row Creates One Object, Multiple Rows Create Multiple Objects

~~~sql
SELECT JSON_OBJECT(
           'id' VALUE employee_id,
           'name' VALUE first_name || ' ' || last_name
       ) AS employee_json
FROM   json_demo_emp;
~~~

Each source row produces a separate object. If you need a single document containing all employees, you must wrap JSON_OBJECT inside JSON_ARRAYAGG.

## 4. JSON_ARRAY — Creating a JSON Array

### 4.1. Array from an Argument List

~~~sql
SELECT JSON_ARRAY(
           employee_id,
           first_name,
           salary
       ) AS employee_values
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

The array preserves the order of arguments: ID, name, salary. Unlike an object, an array does not have key names for individual elements.

### 4.2. Array Containing Multiple Data Types

~~~sql
SELECT JSON_ARRAY(
           101,
           'An Nguyen',
           2500,
           DATE '2022-01-10'
       ) AS sample_json
FROM   dual;
~~~

Oracle converts SQL types to their corresponding JSON types. NUMBER becomes a JSON number; strings become JSON strings; DATE/TIMESTAMP values are represented as date-time strings in ISO 8601 format.

### 4.3. Array Containing Objects and Sub-arrays

~~~sql
SELECT JSON_ARRAY(
           JSON_OBJECT(
               'id' VALUE 101,
               'name' VALUE 'An'
           ),
           JSON_OBJECT(
               'id' VALUE 102,
               'name' VALUE 'Binh'
           )
       ) AS employees_json
FROM   dual;
~~~

The result is an array consisting of two objects. Multiple levels can be nested to represent complex data structures.

### 4.4. Element Ordering

With JSON_ARRAY, element order is simply the order of expressions in the argument list:

~~~sql
SELECT JSON_ARRAY('A', 'B', 'C')
FROM dual;
~~~

The result has the order A, B, C. If fetching data from multiple rows, use JSON_ARRAYAGG with ORDER BY inside the function.

## 5. Converting SQL Types to JSON Types

Generation functions convert SQL values into JSON values based on the input data type.

| SQL Type | Typical JSON Output |
| --- | --- |
| NUMBER | JSON number, without quotes |
| VARCHAR2/NVARCHAR2 | JSON string, special characters escaped |
| DATE/TIMESTAMP | JSON string in ISO 8601 date-time format |
| RAW/BLOB | JSON string representing bytes in hexadecimal |
| NULL | JSON null or omitted based on the NULL clause |
| CLOB | JSON string, unless marked with FORMAT JSON |

Example:

~~~sql
SELECT JSON_OBJECT(
           'numberValue' VALUE 125,
           'textValue'   VALUE '125',
           'dateValue'   VALUE DATE '2025-04-30',
           'nullValue'   VALUE CAST(NULL AS VARCHAR2(10))
       )
FROM dual;
~~~

numberValue is the JSON number 125, whereas textValue is the JSON string "125". The two values look similar but have different types.

### 5.1. Boolean in Oracle 19c

Oracle 19c does not have a standard SQL BOOLEAN column type. To generate a JSON boolean from a condition, you can produce the literal true or false and use FORMAT JSON:

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE employee_id,
           'isHighSalary' VALUE
               CASE
                   WHEN salary >= 3000 THEN 'true'
                   ELSE 'false'
               END FORMAT JSON
       )
FROM   json_demo_emp;
~~~

If FORMAT JSON is omitted, the text values true and false become the JSON strings "true" and "false", not boolean true and false.

### 5.2. Automatic Character Escaping

When a value is a normal SQL string, Oracle automatically escapes characters as required by JSON. For example, double quotes, newline characters, and backslashes are handled so the output JSON is valid.

Do not manually concatenate quotes or pre-escape strings before passing them to JSON_OBJECT/JSON_ARRAY. Double-escaping can alter the content received by the client.

## 6. NULL ON NULL and ABSENT ON NULL

The two NULL handling behaviors have different meanings:

- **NULL ON NULL:** keeps the property/element and emits a JSON null value.
- **ABSENT ON NULL:** omits the property or element whose value is SQL NULL.

### 6.1. Default for JSON_OBJECT

For JSON_OBJECT and JSON_OBJECTAGG, the default is NULL ON NULL.

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE employee_id,
           'commission' VALUE commission
       )
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

If commission is SQL NULL, the output still includes the commission key with a JSON null value.

To omit the key:

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE employee_id,
           'commission' VALUE commission
           ABSENT ON NULL
       )
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

When commission is NULL, that member does not appear in the object.

### 6.2. Default for JSON_ARRAY

For JSON_ARRAY and JSON_ARRAYAGG, the default is ABSENT ON NULL.

~~~sql
SELECT JSON_ARRAY(
           employee_id,
           commission
       )
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

Because commission is NULL, that element is omitted by default. If you need to preserve positions and represent NULL explicitly:

~~~sql
SELECT JSON_ARRAY(
           employee_id,
           commission
           NULL ON NULL
       )
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

The result retains the second element as JSON null.

### 6.3. Differences That Can Affect API Contracts

Suppose a client expects an array to always have three elements in the order ID, commission, salary. If the default ABSENT ON NULL is used, a NULL element is removed and the positions of subsequent elements shift.

For arrays with a fixed positional structure, consider NULL ON NULL. For objects, ABSENT ON NULL may be appropriate if you want to distinguish between an unprovided property and a property with a null value.

### 6.4. Empty Strings in Oracle

Oracle SQL treats an empty VARCHAR2 string as NULL. Therefore, you cannot expect an empty string to always be serialized as an empty JSON string "" when the input is VARCHAR2. An empty CLOB is distinguished from NULL in certain JSON generation contexts. If an API contract needs to distinguish between an empty string and null, design the storage/representation type explicitly.

## 7. FORMAT JSON — Embedding a JSON Fragment as a Value

### 7.1. Normal JSON Strings Are Quoted

If you pass a JSON string into a generation function without FORMAT JSON, Oracle treats it as string data:

~~~sql
SELECT JSON_OBJECT(
           'payload' VALUE '{"active":true}'
       )
FROM dual;
~~~

The payload value becomes a JSON string containing the text {"active":true}, not a nested object.

### 7.2. Using FORMAT JSON

If the input string is actually valid JSON and you want to embed it as a JSON fragment:

~~~sql
SELECT JSON_OBJECT(
           'payload' VALUE '{"active":true}' FORMAT JSON
       )
FROM dual;
~~~

Now payload is a JSON object.

### 7.3. No Need for FORMAT JSON on Nested Generation Functions

When the value expression is JSON_OBJECT, JSON_ARRAY, or a SQL/JSON function returning JSON, Oracle can recognize it as JSON:

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE employee_id,
           'profile' VALUE JSON_OBJECT(
               'firstName' VALUE first_name,
               'lastName' VALUE last_name
           )
       )
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

There is no need to append FORMAT JSON after the inner JSON_OBJECT.

### 7.4. FORMAT JSON Is a Guarantee About the Input Data

FORMAT JSON tells Oracle that the input string already represents JSON. Do not use it on arbitrary user text or unvalidated data.

If you need to accept JSON from external sources:
- Validate the data using an IS JSON condition or appropriate API validation.
- Only mark FORMAT JSON after verifying the fragment is valid.
- Use STRICT to require validation of the final generated JSON.
- Do not use FORMAT JSON as a way to bypass escaping.

## 8. RETURNING — Controlling Output Type and Size

### 8.1. Default VARCHAR2(4000)

In Oracle 19c, JSON generation functions return VARCHAR2(4000) by default. If the JSON exceeds the limit, the statement may fail because the result is too large.

For documents with many elements or large text fields, proactively specify CLOB as the return type.

### 8.2. RETURNING CLOB

JSON_OBJECT example:

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE employee_id,
           'firstName' VALUE first_name,
           'lastName' VALUE last_name,
           'salary' VALUE salary
           RETURNING CLOB
       )
FROM   json_demo_emp;
~~~

JSON_ARRAYAGG example:

~~~sql
SELECT JSON_ARRAYAGG(
           JSON_OBJECT(
               'id' VALUE employee_id,
               'name' VALUE first_name || ' ' || last_name
           )
           ORDER BY employee_id
           RETURNING CLOB
       )
FROM   json_demo_emp;
~~~

CLOB is suitable for JSON documents larger than the default VARCHAR2 limit.

### 8.3. RETURNING VARCHAR2 with Explicit Size

If you know the output is small, you can specify a size:

~~~sql
SELECT JSON_OBJECT(
           'id' VALUE employee_id,
           'name' VALUE first_name
           RETURNING VARCHAR2(1000)
       )
FROM   json_demo_emp;
~~~

The size is measured in BYTE or CHAR depending on the declaration. When Unicode is involved, make sure you understand length semantics and character sets.

### 8.4. RETURNING BLOB

Some JSON generation functions support BLOB output using the AL32UTF8 character set. BLOB is useful when the application needs JSON as UTF-8 bytes for transmission or writing to a file. Check the RETURNING syntax for each specific function and release; do not assume every aggregate function supports the exact same set of return types.

### 8.5. Native JSON Type and Versions

Oracle 19c typically represents JSON generation results using VARCHAR2, CLOB, or BLOB. The native JSON data type is supported in newer releases and has its own compatibility requirements. Do not use RETURNING JSON in a 19c environment if the database does not support the native JSON type.

## 9. STRICT and WITH UNIQUE KEYS

### 9.1. STRICT

STRICT instructs Oracle to verify that the result of the generation function is well-formed JSON. For example:

~~~sql
SELECT JSON_OBJECT(
           'id' VALUE employee_id,
           'name' VALUE first_name
           RETURNING CLOB
           STRICT
       )
FROM   json_demo_emp;
~~~

If an input marked with FORMAT JSON is not valid JSON, STRICT helps detect the error in the final output.

Generation functions are inherently designed to build valid JSON from SQL values. STRICT is especially useful when incorporating existing JSON fragments into the result.

### 9.2. WITH UNIQUE KEYS

JSON objects should have unique keys. For objects generated from dynamic data or JSON_OBJECTAGG, two rows might produce the same key.

For example, mapping department name to ID:

~~~sql
SELECT JSON_OBJECTAGG(
           department_name VALUE department_id
           RETURNING CLOB
           WITH UNIQUE KEYS
       )
FROM   json_demo_dept;
~~~

WITH UNIQUE KEYS requires that keys in the resulting object be unique. If the data generates duplicate keys, Oracle raises an error instead of returning an object with repeated keys.

### 9.3. Handling Duplicate Keys from Data

If keys are not unique, resolve them before aggregating:
- Select a representative row using ROW_NUMBER.
- Aggregate the data by key first.
- Use a truly unique key such as an identifier.
- Split the data group into multiple objects if business logic permits.

Do not rely on client behavior when parsing JSON with duplicate keys. Different parsers may keep the first key, the last key, or represent multiple keys.

## 10. JSON_ARRAYAGG — Aggregating Multiple Rows into an Array

### 10.1. Basic Syntax

~~~sql
SELECT JSON_ARRAYAGG(employee_id RETURNING CLOB) AS employee_ids
FROM   json_demo_emp;
~~~

The aggregate function takes the employee_id value from each row and creates a single array.

### 10.2. Array of Objects

A common pattern is creating an object per row and aggregating those objects into an array:

~~~sql
SELECT JSON_ARRAYAGG(
           JSON_OBJECT(
               'employeeId' VALUE employee_id,
               'firstName' VALUE first_name,
               'lastName' VALUE last_name,
               'salary' VALUE salary
           )
           ORDER BY employee_id
           RETURNING CLOB
       ) AS employees_json
FROM   json_demo_emp;
~~~

The result is an array containing multiple employee objects.

### 10.3. ORDER BY Must Be Inside JSON_ARRAYAGG

To determine element order, place ORDER BY inside the JSON_ARRAYAGG call:

~~~sql
SELECT JSON_ARRAYAGG(
           employee_id
           ORDER BY employee_id DESC
           RETURNING CLOB
       )
FROM   json_demo_emp;
~~~

An ORDER BY on the outer SELECT does not replace the ORDER BY inside the aggregate. With JSON_ARRAYAGG, ordering must reference columns/expressions; do not use column position numbers like ORDER BY 1 inside the function.

If the sort column is not unique, add a secondary sort key for deterministic results:

~~~sql
JSON_ARRAYAGG(
    employee_id
    ORDER BY department_id, employee_id
    RETURNING CLOB
)
~~~

### 10.4. JSON_ARRAYAGG with GROUP BY

Each group produces its own array:

~~~sql
SELECT department_id,
       JSON_ARRAYAGG(
           employee_id
           ORDER BY employee_id
           RETURNING CLOB
       ) AS employee_ids
FROM   json_demo_emp
GROUP  BY department_id
ORDER  BY department_id;
~~~

Departments 10, 20, and 30 have corresponding arrays. Department 40 does not appear because there are no employee rows for it in the source set.

### 10.5. NULL in JSON_ARRAYAGG

Default is ABSENT ON NULL:

~~~sql
SELECT JSON_ARRAYAGG(
           commission
           ORDER BY employee_id
           RETURNING CLOB
       )
FROM   json_demo_emp;
~~~

NULL commissions are omitted from the array. If you need to keep null elements:

~~~sql
SELECT JSON_ARRAYAGG(
           commission
           ORDER BY employee_id
           NULL ON NULL
           RETURNING CLOB
       )
FROM   json_demo_emp;
~~~

Choose the behavior based on the consumer's data contract.

### 10.6. Aggregate with Zero Rows

If there are no input rows, the aggregate result may be SQL NULL. If the API requires an empty array [], you can use COALESCE:

~~~sql
SELECT COALESCE(
           (
               SELECT JSON_ARRAYAGG(
                          employee_id
                          ORDER BY employee_id
                          RETURNING CLOB
                      )
               FROM   json_demo_emp
               WHERE  department_id = -1
           ),
           TO_CLOB('[]')
       ) AS employee_ids
FROM dual;
~~~

Here the empty result is replaced with []. If you pass this value into a larger JSON_OBJECT, mark it with FORMAT JSON so Oracle embeds it as an array rather than a string.

## 11. JSON_OBJECTAGG — Aggregating Multiple Rows into an Object

### 11.1. Basic Syntax

JSON_OBJECTAGG takes key/value pairs from multiple rows:

~~~sql
SELECT JSON_OBJECTAGG(
           department_name VALUE department_id
           RETURNING CLOB
       ) AS department_map
FROM   json_demo_dept;
~~~

The result is an object whose keys are department names and values are IDs.

### 11.2. Using KEY for Clarity

~~~sql
SELECT JSON_OBJECTAGG(
           KEY department_name VALUE department_id
           RETURNING CLOB
       )
FROM   json_demo_dept;
~~~

KEY is an optional keyword that makes the statement easier to read.

### 11.3. Object per Group

~~~sql
SELECT location,
       JSON_OBJECTAGG(
           department_name VALUE department_id
           RETURNING CLOB
       ) AS departments_by_location
FROM   json_demo_dept
GROUP  BY location;
~~~

Each location generates its own object. Rows with a NULL location also form a NULL group according to Oracle's GROUP BY rules.

### 11.4. Keys Should Be Unique Within an Object

If multiple rows produce the same key, the object may contain duplicate keys. This causes ambiguity for consumers and may be rejected by parsers or validators.

If business logic requires a key/value map, ensure keys are unique within each group or use WITH UNIQUE KEYS so Oracle enforces it.

Example using department_id as the key:

~~~sql
SELECT JSON_OBJECTAGG(
           TO_CHAR(department_id) VALUE department_name
           RETURNING CLOB
           WITH UNIQUE KEYS
       )
FROM   json_demo_dept;
~~~

JSON object keys are strings. For numeric keys, use a stable text representation; avoid NLS-dependent formatting when generating keys.

### 11.5. Object Member Order Is Not Guaranteed

A JSON object is an unordered collection of key/value pairs; do not rely on member order in the output string. If the consumer requires ordering, use an array and JSON_ARRAYAGG with ORDER BY.

## 12. Combining Functions to Build Hierarchical JSON

### 12.1. A Department and Its List of Employees

You can use a correlated subquery to build an employee array for each department:

~~~sql
SELECT JSON_OBJECT(
           'departmentId' VALUE d.department_id,
           'departmentName' VALUE d.department_name,
           'location' VALUE d.location,
           'employees' VALUE (
               SELECT JSON_ARRAYAGG(
                          JSON_OBJECT(
                              'employeeId' VALUE e.employee_id,
                              'name' VALUE e.first_name || ' ' || e.last_name,
                              'salary' VALUE e.salary
                          )
                          ORDER BY e.employee_id
                          RETURNING CLOB
                      )
               FROM   json_demo_emp e
               WHERE  e.department_id = d.department_id
           )
           RETURNING CLOB
       ) AS department_json
FROM   json_demo_dept d
ORDER  BY d.department_id;
~~~

Each department row creates one object. The employees field is an array of employee objects. Oracle optimizes SQL/JSON queries and subqueries; this approach often avoids fetching relational rows into the application just to assemble the structure.

### 12.2. Empty Array for Departments Without Employees

In the previous example, department 40 has an aggregate subquery with zero matching rows, so the subquery evaluates to SQL NULL. Since JSON_OBJECT defaults to NULL ON NULL, the employees field becomes JSON null.

If the API contract requires an empty array:

~~~sql
SELECT JSON_OBJECT(
           'departmentId' VALUE d.department_id,
           'departmentName' VALUE d.department_name,
           'employees' VALUE
               COALESCE(
                   (
                       SELECT JSON_ARRAYAGG(
                                  JSON_OBJECT(
                                      'employeeId' VALUE e.employee_id,
                                      'name' VALUE e.first_name || ' ' || e.last_name
                                  )
                                  ORDER BY e.employee_id
                                  RETURNING CLOB
                              )
                       FROM json_demo_emp e
                       WHERE e.department_id = d.department_id
                   ),
                   TO_CLOB('[]')
               ) FORMAT JSON
           RETURNING CLOB
       )
FROM   json_demo_dept d
ORDER  BY d.department_id;
~~~

COALESCE returns [] when there are no employees. FORMAT JSON ensures the string [] is embedded as an array. Only use FORMAT JSON with programmatically generated or validated fragments.

### 12.3. Entire Department List as a Single Document

~~~sql
SELECT JSON_ARRAYAGG(
           JSON_OBJECT(
               'departmentId' VALUE d.department_id,
               'departmentName' VALUE d.department_name,
               'employeeCount' VALUE (
                   SELECT COUNT(*)
                   FROM json_demo_emp e
                   WHERE e.department_id = d.department_id
               )
           )
           ORDER BY d.department_id
           RETURNING CLOB
       ) AS departments_json
FROM   json_demo_dept d;
~~~

This produces a single JSON array containing each department's object. A scalar subquery supplies the employee count for each object.

### 12.4. Multi-Level Nesting

The pattern can be extended to structures like:

~~~text
[
  {
    "departmentId": 10,
    "employees": [
      {
        "employeeId": 101,
        "projects": [
          {"projectId": 1},
          {"projectId": 2}
        ]
      }
    ]
  }
]
~~~

Each one-to-many relationship can be generated with an aggregate subquery nested inside the parent row's object. When nesting multiple levels, keep in mind:
- Each subquery must be correlated by the proper keys.
- Use ORDER BY inside each JSON_ARRAYAGG if order matters.
- Define the NULL/empty-array policy for each level.
- Use RETURNING CLOB at levels that can produce large output.
- Avoid duplicating data by joining multiple one-to-many relationships simultaneously.

## 13. GROUP BY, HAVING, and JSON Aggregates

### 13.1. One Array per Department

~~~sql
SELECT department_id,
       JSON_ARRAYAGG(
           JSON_OBJECT(
               'id' VALUE employee_id,
               'name' VALUE first_name || ' ' || last_name
           )
           ORDER BY employee_id
           RETURNING CLOB
       ) AS employees
FROM   json_demo_emp
GROUP  BY department_id;
~~~

GROUP BY determines that each group produces a separate JSON array.

### 13.2. Filtering Groups That Meet a Condition

~~~sql
SELECT department_id,
       JSON_ARRAYAGG(
           employee_id
           ORDER BY employee_id
           RETURNING CLOB
       ) AS employee_ids
FROM   json_demo_emp
GROUP  BY department_id
HAVING COUNT(*) >= 2;
~~~

HAVING filters groups after aggregation. JSON_ARRAYAGG does not replace COUNT or other SQL aggregates; they can be used together in the same SELECT.

### 13.3. Multiple Aggregates in One Query

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count,
       AVG(salary) AS average_salary,
       JSON_ARRAYAGG(
           JSON_OBJECT(
               'id' VALUE employee_id,
               'salary' VALUE salary
           )
           ORDER BY employee_id
           RETURNING CLOB
       ) AS employees_json
FROM   json_demo_emp
GROUP  BY department_id;
~~~

You can return aggregated relational data and JSON in the same query. Treat JSON as an additional representation of the data, not a reason to ignore GROUP BY or cardinality rules.

## 14. JSON Generation and Existing JSON Data

### 14.1. VARCHAR2/CLOB Columns Containing JSON

In Oracle 19c, applications often store JSON text in VARCHAR2, CLOB, or BLOB with a JSON validation constraint:

~~~sql
CREATE TABLE json_demo_payload (
    payload_id NUMBER PRIMARY KEY,
    payload    CLOB,
    CONSTRAINT ck_json_demo_payload
        CHECK (payload IS JSON)
);
~~~

IS JSON validates the column content against JSON rules. You can use STRICT depending on syntax and version validation requirements.

### 14.2. Embedding Stored JSON Columns

If a CLOB column contains valid JSON, you can use FORMAT JSON:

~~~sql
SELECT JSON_OBJECT(
           'id' VALUE payload_id,
           'document' VALUE payload FORMAT JSON
           RETURNING CLOB
       )
FROM   json_demo_payload;
~~~

Without FORMAT JSON, payload is treated as a string and quoted as a JSON string.

### 14.3. Automatic Recognition of SQL/JSON Function Results

If the value expression is JSON_OBJECT, JSON_ARRAY, or certain other SQL/JSON functions, Oracle can recognize the result as JSON. You do not need to mechanically append FORMAT JSON after every function call.

### 14.4. JSON_QUERY and FORMAT JSON

JSON_QUERY is typically used to extract an object/array from existing JSON. When passing its result into JSON_OBJECT or JSON_ARRAY, Oracle can recognize it as JSON. Distinguish between:
- JSON_QUERY: queries a fragment from a JSON document.
- JSON_OBJECT/JSON_ARRAY: creates a new JSON structure.
- FORMAT JSON: declares that a text expression is already a JSON fragment.

## 15. Comparing JSON_ARRAYAGG and JSON_OBJECTAGG

| Criterion | JSON_ARRAYAGG | JSON_OBJECTAGG |
| --- | --- | --- |
| Structure | Array | Object |
| Input | One expression per row | One key and one value per row |
| Ordering | ORDER BY can be specified inside the function | Member order is not guaranteed |
| Default NULL | ABSENT ON NULL | NULL ON NULL |
| Duplicates | Duplicate elements are kept | Duplicate keys must be controlled |
| Use case | Lists, collections, child rows | Key/value maps, dictionaries, lookups |
| Result with GROUP BY | One array per group | One object per group |

Choose an array when you need to preserve multiple elements, even when values repeat. Choose an object when you need lookup by key and keys can be kept unique.

## 16. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Output has quotes around nested JSON | JSON string treated as plain text | Use FORMAT JSON after validating the fragment |
| Output exceeds limit | Default VARCHAR2(4000) | Use RETURNING CLOB as appropriate |
| Field disappears when NULL | ABSENT ON NULL is active | Use NULL ON NULL if the field must be kept |
| Array missing NULL elements | Default ABSENT ON NULL | Use NULL ON NULL to preserve positions |
| JSON_ARRAYAGG out of order | ORDER BY placed outside aggregate or missing sort | Place ORDER BY inside JSON_ARRAYAGG |
| JSON_OBJECTAGG has duplicate keys | Source data is not unique by key | Deduplicate/group or use WITH UNIQUE KEYS |
| JSON returns string "true" | Boolean text without FORMAT JSON | Use literal true/false with FORMAT JSON |
| Nested JSON is escaped | Text fragment not marked as JSON | Use FORMAT JSON for validated fragments |
| No rows but API expects [] | Aggregate returns SQL NULL | COALESCE with CLOB '[]' and FORMAT JSON when nesting |
| Driver reports invalid bind variable | Colon used as key/value separator | Use the VALUE keyword |

### 16.1. Double-Quoted JSON Output

Example:

~~~sql
SELECT JSON_OBJECT(
           'child' VALUE '{"x":1}'
       )
FROM dual;
~~~

The result has child containing a JSON string. If you want a nested object, use:

~~~sql
SELECT JSON_OBJECT(
           'child' VALUE '{"x":1}' FORMAT JSON
       )
FROM dual;
~~~

Only use the second approach if the fragment is genuinely valid JSON.

### 16.2. ORA-40478 or Output Too Large

If the result exceeds the return type size, specify CLOB instead of the default VARCHAR2. Check the return type of each function, especially when multiple JSON levels are nested.

### 16.3. Unclear Duplicate Keys

If JSON_OBJECTAGG generates keys from a non-unique column, query for duplicate data first:

~~~sql
SELECT department_name,
       COUNT(*)
FROM   json_demo_dept
GROUP  BY department_name
HAVING COUNT(*) > 1;
~~~

Fix the data or define an appropriate key before building the map.

## 17. Performance and API Design

### 17.1. Generating JSON in the Database

SQL/JSON generation helps to:
- Reduce round-trips between the application and database.
- Avoid fetching multiple result sets to the application just to build JSON structures.
- Leverage the SQL optimizer and aggregation engine.
- Generate nested objects/arrays in a single query.

For parent-child structures, a JSON_ARRAYAGG subquery can build the child collection for each parent directly inside the database.

### 17.2. Choose CLOB Deliberately

CLOB avoids the default VARCHAR2(4000) limit but carries overhead when creating, transferring, and consuming large payloads. Do not assume every JSON output needs CLOB. If the response is small, VARCHAR2 can be simpler.

### 17.3. Do Not Use JSON_OBJECT(*) for Long-Lived APIs

Wildcards depend on table structure. When a DBA adds a new column, the API may change unexpectedly. Specify the keys to expose explicitly to maintain a stable data contract and avoid accidentally leaking internal columns.

### 17.4. Place ORDER BY in the Right Spot

A JSON array can be part of an API contract. If clients depend on order, place ORDER BY inside JSON_ARRAYAGG and include a unique tie-breaker key for deterministic results.

### 17.5. Avoid Joins That Multiply Rows

If a parent has multiple children across two one-to-many relationships, joining both child tables simultaneously can create a Cartesian product and duplicate JSON elements. Build each collection using a separate aggregate subquery, or aggregate each relationship before joining.

### 17.6. Do Not Concatenate JSON Manually

Manual JSON string concatenation easily breaks when data contains quotes, newlines, control characters, or Unicode. Use JSON_OBJECT/JSON_ARRAY so Oracle handles serialization and escaping.

## 18. Workflow for Building JSON from Relational Data

1. Define the desired JSON schema: objects, arrays, keys, value types.
2. Identify the data granularity: single row, multiple rows, or grouped.
3. Use JSON_OBJECT for objects and JSON_ARRAY for positional arrays.
4. Use JSON_ARRAYAGG or JSON_OBJECTAGG when aggregating multiple rows.
5. Decide between NULL ON NULL and ABSENT ON NULL at each level.
6. Place ORDER BY inside JSON_ARRAYAGG if order matters.
7. Use FORMAT JSON only for fragments that are already valid JSON.
8. Choose RETURNING CLOB if the output may exceed VARCHAR2(4000).
9. Use STRICT and WITH UNIQUE KEYS when stricter validation is needed.
10. Test empty datasets, duplicate keys, NULLs, Unicode, and large payloads.
11. Validate the final JSON using the consumer's parser/validator.
12. Keep key names and data types stable as an API contract.

## 19. Comprehensive Practice Exercises

Use the two tables JSON_DEMO_DEPT and JSON_DEMO_EMP from section 2.

### Exercise 1 — Basic JSON_OBJECT

Create an object for each employee with employeeId, firstName, lastName, and salary. Check the JSON type of salary.

### Exercise 2 — JSON_OBJECT with Custom Keys

Use camelCase for key names. Compare with passing column names directly.

### Exercise 3 — JSON_OBJECT(*)

Generate objects using a wildcard. Add a demo column to the table and observe how the JSON output changes.

### Exercise 4 — JSON_ARRAY

Create an array with employee ID, name, and salary. Change the argument order and observe the element order.

### Exercise 5 — Data Types

Create an object containing NUMBER, VARCHAR2, DATE, and NULL. Identify which fields become JSON number, JSON string, and JSON null.

### Exercise 6 — NULL ON NULL and ABSENT ON NULL

Create two objects and two arrays from a row with NULL commission. Compare the number of members/elements.

### Exercise 7 — FORMAT JSON

Pass the string {"active":true} into JSON_OBJECT with and without FORMAT JSON. Explain the difference between a nested object and a string.

### Exercise 8 — JSON_ARRAYAGG

Create an array of employee IDs in ascending and descending order. Place ORDER BY inside the aggregate.

### Exercise 9 — JSON_OBJECTAGG

Create a map from department name to department ID. Test duplicate key data in a test table and verify WITH UNIQUE KEYS.

### Exercise 10 — GROUP BY

Create a JSON array of employees for each department_id. Use HAVING to return only departments with two or more employees.

### Exercise 11 — Nested JSON

Create a department object with an employees field containing an array of employee objects. Ensure departments with no employees return [] instead of null.

### Exercise 12 — RETURNING CLOB

Generate a large JSON array using many demo rows. Compare the default return type with RETURNING CLOB.

### Exercise 13 — STRICT and JSON Constraint

Store JSON in a CLOB column with CHECK (payload IS JSON). Try inserting valid JSON strings and malformed strings.

### Exercise 14 — API Design

Design a JSON response for an order containing orderId, customer, orderDate, and an items array. Each item has productId, quantity, unitPrice, and lineTotal. Define the NULL policy, items ordering, and return type.

## 20. Oracle Reference Documentation

- [Oracle Database 19c JSON Developer's Guide — Generation of JSON Data](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/generation.html): overview of JSON_OBJECT, JSON_ARRAY, JSON_OBJECTAGG, JSON_ARRAYAGG, input types, NULL handling, and nested JSON.
- [Oracle Database 19c SQL Language Reference — JSON_OBJECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_OBJECT.html): object syntax, key/value, wildcard, RETURNING, STRICT, and unique keys.
- [Oracle Database 19c SQL Language Reference — JSON_ARRAY](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_ARRAY.html): array syntax and NULL handling.
- [Oracle Database 19c SQL Language Reference — JSON_ARRAYAGG](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_ARRAYAGG.html): array aggregation and ORDER BY inside the function.
- [Oracle Database 19c SQL Language Reference — JSON_OBJECTAGG](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_OBJECTAGG.html): object aggregation, key/value, and WITH UNIQUE KEYS.

JSON_OBJECT and JSON_ARRAY build structures from expressions; JSON_ARRAYAGG and JSON_OBJECTAGG aggregate data from multiple rows. When building hierarchical JSON, nest generation functions and aggregate subqueries according to parent-child relationships. Explicitly define NULL handling, place ORDER BY inside JSON_ARRAYAGG, choose RETURNING CLOB for large documents, and use FORMAT JSON only with validated fragments. **Use SQL/JSON functions to generate JSON structurally from data rather than concatenating strings manually.**

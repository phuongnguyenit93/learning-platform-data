# Pipelined Table Functions and Streaming Data Consumption

In Oracle Database, a **pipelined table function** is a PL/SQL function that returns rows to the SQL engine one by one via the `PIPE ROW` statement. The function does not have to build and return an entire collection before the query can begin consuming it. The SQL engine can retrieve rows already emitted while the function continues generating subsequent rows.

This characteristic is useful when transforming data in PL/SQL, combining data from multiple sources, or producing a large result set without holding the entire output in PL/SQL memory. Consumers still query the output like a normal SQL row source: using `TABLE(function(...))` in the `FROM` clause, filtering, joining, aggregating, or feeding the result into a DML statement.

## 1. Table Functions and the Meaning of Pipelining

A table function is a function returning a collection so SQL can treat that collection as a row source. There are two common implementation patterns:

- **Regular table function:** allocates a collection, appends elements to it, and returns the entire collection. SQL receives results only after the function finishes populating the collection.
- **Pipelined table function:** emits each element via `PIPE ROW`. The SQL engine can consume emitted rows without waiting for the function to produce the entire result set.

For example, if a function generates one million numbers, the regular approach may have to hold one million elements in a collection before returning. With a pipelined function, the function can compute one number, pipe it out, and proceed to the next. This typically reduces intermediate memory usage and improves time to first row.

Pipelining is a row-passing mechanism between a function and the SQL engine. It does not turn a query into an asynchronous job, does not create a separate transaction per row, and does not guarantee that all downstream operators stream data without buffering.

## 2. Required Components

A pipelined table function requires:

1. A collection type as the return type, typically a nested table or VARRAY.
2. An element type corresponding to one output row. The element can be a scalar type such as NUMBER or an object type with multiple attributes.
3. Declaring the function with the `PIPELINED` keyword.
4. Using `PIPE ROW(expression)` to emit each element.
5. Ending the function with a bare `RETURN;` without a return collection expression.

When calling the function from SQL, use collection and element types visible to the SQL engine. Types declared at the schema level with `CREATE TYPE` provide a clear and reusable pattern.

## 3. Basic Example: Generating a Number Sequence

First, create a nested table of NUMBER values:

~~~sql
CREATE TYPE number_nt AS TABLE OF NUMBER;
/
~~~

Next, create a function that emits numbers from 1 up to the input limit:

~~~sql
CREATE OR REPLACE FUNCTION generate_numbers(
  p_max IN PLS_INTEGER
)
RETURN number_nt PIPELINED
IS
BEGIN
  IF p_max IS NULL OR p_max < 1 THEN
    RETURN;
  END IF;

  FOR i IN 1 .. p_max LOOP
    PIPE ROW(i);
  END LOOP;

  RETURN;
END;
/
~~~

Key points in the function:

- `RETURN number_nt PIPELINED` declares that the function returns a collection and emits elements in pipelined fashion.
- `PIPE ROW(i)` sends a single NUMBER element to the SQL engine.
- After emitting a row, the function can pause there until the consumer requests more rows.
- `RETURN;` finishes emission. No collection variable needs to be allocated to hold all numbers.

Calling the function in SQL:

~~~sql
SELECT n.COLUMN_VALUE AS generated_number
FROM TABLE(generate_numbers(5)) n
ORDER BY n.COLUMN_VALUE;
~~~

Result:

| GENERATED_NUMBER |
|---:|
| 1 |
| 2 |
| 3 |
| 4 |
| 5 |

Because the collection holds scalar NUMBER values, SQL uses the `COLUMN_VALUE` pseudocolumn/attribute to reference each element. If the collection holds an object type, each attribute of the object can be referenced directly.

## 4. Emitting Multi-Column Rows

In real applications, a row usually has multiple attributes. You can define an object type for the row structure and a nested table of those objects.

The following example uses the `EMPLOYEES` table in the sample `HR` schema:

~~~sql
CREATE TYPE employee_stream_ot AS OBJECT (
  employee_id NUMBER,
  full_name   VARCHAR2(200),
  salary      NUMBER
);
/

CREATE TYPE employee_stream_nt AS TABLE OF employee_stream_ot;
/
~~~

Create a function returning employees for a department:

~~~sql
CREATE OR REPLACE FUNCTION employees_for_department(
  p_department_id IN employees.department_id%TYPE
)
RETURN employee_stream_nt PIPELINED
IS
BEGIN
  FOR r IN (
    SELECT employee_id,
           first_name || ' ' || last_name AS full_name,
           salary
      FROM employees
     WHERE department_id = p_department_id
  ) LOOP
    PIPE ROW(
      employee_stream_ot(
        r.employee_id,
        r.full_name,
        r.salary
      )
    );
  END LOOP;

  RETURN;
END;
/
~~~

On each iteration, the function constructs an `employee_stream_ot` object and emits it with `PIPE ROW`. There is no need to declare an output collection, call `EXTEND`, and assign each slot.

Consuming the result:

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.salary
  FROM TABLE(employees_for_department(50)) e
 ORDER BY e.employee_id;
~~~

Result columns correspond to the object type's attributes. Filtering and sorting can be placed in the outer SQL statement just like querying a table.

Note: this example assumes the `HR` schema has the `EMPLOYEES` table and listed columns. If using another schema, adjust table names, column names, and grants accordingly.

## 5. Consuming Data with TABLE()

The `TABLE()` operator lets SQL treat the collection returned by the function as a row source in the `FROM` clause. This is the standard way to invoke a table function.

### Filtering Rows

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.salary
  FROM TABLE(employees_for_department(50)) e
 WHERE e.salary >= 5000
 ORDER BY e.salary DESC;
~~~

### Aggregating Data

~~~sql
SELECT COUNT(*) AS employee_count,
       AVG(e.salary) AS average_salary,
       MAX(e.salary) AS highest_salary
  FROM TABLE(employees_for_department(50)) e;
~~~

### Joining with Other Tables

When the table function's argument references a row from a preceding row source, use `CROSS APPLY` or `OUTER APPLY` syntax to express the correlation clearly. Example:

~~~sql
SELECT d.department_id,
       e.employee_id,
       e.full_name,
       e.salary
  FROM departments d
 CROSS APPLY TABLE(
   employees_for_department(d.department_id)
 ) e
 ORDER BY d.department_id, e.employee_id;
~~~

`CROSS APPLY` keeps only departments for which the function returns rows. If you want to keep departments with no matching employees as well, use `OUTER APPLY`:

~~~sql
SELECT d.department_id,
       e.employee_id,
       e.full_name
  FROM departments d
 OUTER APPLY TABLE(
   employees_for_department(d.department_id)
 ) e
 ORDER BY d.department_id, e.employee_id;
~~~

`CROSS APPLY` and `OUTER APPLY` are supported starting in Oracle Database 12c. When a function is invoked per row of the left table, consider how many times it executes and the cost per call. With many departments, inspect the execution plan and compare against a direct JOIN if the business logic can be written entirely in SQL.

## 6. Row-by-Row Consumption in PL/SQL

Pipelined table functions are invoked from SQL. Do not call them directly as a PL/SQL expression to assign a collection:

~~~sql
-- Do not use this way:
-- l_rows := generate_numbers(1000);
~~~

A pipelined table function cannot be invoked directly inside a PL/SQL expression that way; Oracle can raise `PLS-00653`. If a PL/SQL program needs to process rows one by one, open a cursor over a SELECT using `TABLE()` or use a cursor FOR loop:

~~~sql
BEGIN
  FOR r IN (
    SELECT n.COLUMN_VALUE AS generated_number
      FROM TABLE(generate_numbers(1000)) n
  ) LOOP
    -- Process each r.generated_number value here.
    NULL;
  END LOOP;
END;
/
~~~

A cursor FOR loop retrieves rows as it iterates. The program does not need to load the function's entire output into a PL/SQL collection before starting processing.

You can use an explicit cursor if you need control over open, fetch, and close timing:

~~~sql
DECLARE
  CURSOR c_numbers IS
    SELECT n.COLUMN_VALUE AS generated_number
      FROM TABLE(generate_numbers(1000)) n;

  l_number NUMBER;
BEGIN
  OPEN c_numbers;

  LOOP
    FETCH c_numbers INTO l_number;
    EXIT WHEN c_numbers%NOTFOUND;

    -- Process l_number.
    NULL;
  END LOOP;

  CLOSE c_numbers;
EXCEPTION
  WHEN OTHERS THEN
    IF c_numbers%ISOPEN THEN
      CLOSE c_numbers;
    END IF;
    RAISE;
END;
/
~~~

## 7. Receiving Input Data via REF CURSOR

An important application of pipelined table functions is transforming data coming from a caller-supplied query. Instead of querying a fixed table inside the function, the function accepts a `REF CURSOR`, fetches rows from that cursor, and emits transformed results.

For example, create a function accepting a cursor of salaries and emitting doubled salaries:

~~~sql
CREATE OR REPLACE FUNCTION double_salary_rows(
  p_rows IN SYS_REFCURSOR
)
RETURN number_nt PIPELINED
IS
  l_salary NUMBER;
BEGIN
  LOOP
    FETCH p_rows INTO l_salary;
    EXIT WHEN p_rows%NOTFOUND;

    PIPE ROW(l_salary * 2);
  END LOOP;

  CLOSE p_rows;
  RETURN;

EXCEPTION
  WHEN NO_DATA_NEEDED THEN
    IF p_rows%ISOPEN THEN
      CLOSE p_rows;
    END IF;
    RAISE;
  WHEN OTHERS THEN
    IF p_rows%ISOPEN THEN
      CLOSE p_rows;
    END IF;
    RAISE;
END;
/
~~~

Call the function with a cursor expression:

~~~sql
SELECT x.COLUMN_VALUE AS doubled_salary
  FROM TABLE(
    double_salary_rows(
      CURSOR(
        SELECT salary
          FROM employees
         WHERE department_id = 50
      )
    )
  ) x
 ORDER BY x.COLUMN_VALUE;
~~~

Execution flow:

1. SQL opens a cursor for the subquery inside the `CURSOR(...)` expression.
2. The cursor is passed into the function's `SYS_REFCURSOR` parameter.
3. The function FETCHes a salary value, transforms it, and emits it via `PIPE ROW`.
4. The SQL engine receives the output row and can request the next row.
5. When data is exhausted, the function closes the cursor and ends with `RETURN;`.

This example uses a weak `SYS_REFCURSOR` and assumes the cursor returns a single column convertible to NUMBER. If the query returns multiple columns, the FETCH must target the exact matching number and types of variables.

## 8. Data Flow and Consumption Timing

You can picture a pipelined table function as a producer and the SQL engine as a consumer:

~~~text
Data source / REF CURSOR
          |
          v
  Pipelined function
          |
      PIPE ROW
          |
          v
       SQL engine
          |
   +------+------+---------+
   |             |         |
  WHERE          JOIN    Aggregate
   |             |         |
   +-------------+---------+
                 |
                 v
           Query result
~~~

When the SQL engine needs data, the function resumes running until the next `PIPE ROW`. When the function emits a row, control can return to the consumer. This mechanism allows incremental result processing and reduces the need to hold an entire collection in memory.

However, distinguish **pipelining at the function's output** from **streaming across the entire execution plan**:

- A simple filter can consume each row as it is emitted.
- An `ORDER BY` sort usually must collect its inputs before determining final order.
- `GROUP BY`, `DISTINCT`, hash joins, or certain analytic operations may need to buffer state or large volumes of rows.
- Parallel execution can alter ordering and how data moves between processes.

Therefore, a pipelined function can reduce memory on the function side, but it does not guarantee the entire query needs no intermediate memory. Inspect the execution plan to see the actual SQL operators involved.

## 9. Early Termination and the NO_DATA_NEEDED Exception

The caller does not always need to consume every row. For example:

~~~sql
SELECT n.COLUMN_VALUE
  FROM TABLE(generate_numbers(1000000)) n
 WHERE ROWNUM <= 10;
~~~

Once the SQL engine has enough rows for the query result, it can stop requesting more rows from the function. In that situation, Oracle may raise the `NO_DATA_NEEDED` exception inside the pipelined function to signal that the consumer needs no further rows.

If the function has no custom resource cleanup, Oracle handles this signal as part of terminating the pipeline. If the function has a catch-all `WHEN OTHERS` exception handler, take care not to turn `NO_DATA_NEEDED` into an ordinary application error. Handle it explicitly to close cursors or release resources and re-raise:

~~~sql
EXCEPTION
  WHEN NO_DATA_NEEDED THEN
    -- Release resources if still open.
    RAISE;
  WHEN OTHERS THEN
    -- Clean up resources and preserve the actual error.
    RAISE;
END;
~~~

The `double_salary_rows` example earlier demonstrates closing the REF CURSOR when the pipeline stops early or fails. This is critical for functions reading files, cursors, or external resources.

## 10. Row Ordering and Result Correctness

Do not rely on `PIPE ROW` emission order to assume final SQL query result order. SQL guarantees output order only when the outermost query includes `ORDER BY`.

For instance, even if a function emits employees in a specific order, the consuming query should specify it explicitly:

~~~sql
SELECT e.employee_id, e.full_name
  FROM TABLE(employees_for_department(50)) e
 ORDER BY e.employee_id;
~~~

If the function executes in parallel, emission order is even less fixed. Whenever order is part of the business requirement, include the sort column(s) in the output data and apply `ORDER BY` on the consuming SQL query.

## 11. Parallel Execution

A pipelined table function can be enabled for parallel execution using the `PARALLEL_ENABLE` clause. When enabled and supported by the execution plan, Oracle can distribute work across parallel execution processes.

Enable parallelism only when the function is truly safe to run across multiple worker processes. Consider:

- Whether each partition of data can be processed independently.
- Whether the function depends on package variables, session state, or row ordering.
- Whether input data is partitioned in a way that fits the transformation.
- Whether parallel execution would excessively increase CPU load, I/O, or data-source accesses.
- Whether output requires deterministic ordering; if so, the outer SQL still needs `ORDER BY`.

For functions accepting a `REF CURSOR`, input partitioning configuration must match how data is split across processes. `PARALLEL_ENABLE` does not guarantee the query will run in parallel in all cases. Verify with the execution plan and measure performance on real data.

## 12. When Should You Use a Pipelined Table Function?

A pipelined table function fits well when:

- You must perform complex transformations in PL/SQL that pure SQL struggles to express.
- You need to convert data from a `REF CURSOR` or another source into a SQL-queryable row set.
- Result sets are large and building an entire collection before returning creates memory pressure.
- You want to combine PL/SQL logic with SQL operations like `JOIN`, `WHERE`, `GROUP BY`, or `INSERT ... SELECT`.
- You want callers to be able to stop consuming once enough rows are received.

Consider alternatives when:

- The transformation can be written clearly and efficiently in pure SQL.
- The result set is small and returning a standard collection is simpler.
- The overhead of PL/SQL calls and row-by-row piping outweighs the memory savings.
- The function needs to perform extensive data or transaction side effects.

Pipelined is not automatically faster. Every piped row still incurs control and data transfer overhead between the PL/SQL runtime and the SQL engine. Pure SQL generally gives the optimizer far more room to push predicates, pick join orders, and optimize the whole operation.

## 13. Implementation Considerations

**Keep return types stable:** collection and element types form the contract between the function and SQL queries. When changing an object type, review all functions, views, and applications depending on it.

**Do not accumulate the entire output:** if the goal is reducing memory, avoid building another large collection inside the function before piping rows out. Keep only the state genuinely required for the transformation.

**Manage cursors and resources:** if the function receives a `REF CURSOR` or opens other resources, close and release them on normal completion, errors, and early termination.

**Avoid side effects inside SELECT:** do not use a pipelined function to update business data or commit transactions. Keep emission predictable and place write operations in appropriate DML statements or procedures.

**Verify row counts and datatypes:** values passed to `PIPE ROW` must be compatible with the collection element type. When piping objects, constructor argument order and types must match the object type definition.

**Inspect the execution plan:** sort, group, join, or parallel operators can change how much data is buffered and when rows are returned. Never judge performance solely from the presence of `PIPELINED`.

**Handle early termination:** if using a `WHEN OTHERS` handler, handle `NO_DATA_NEEDED` separately to clean up cleanly and avoid false error reporting when the caller stops requesting rows.

## 14. How to Test a Pipelined Table Function

Before shipping the function into an application, test how it is called and consumed:

1. Call the function with small, empty, NULL, and boundary inputs.
2. Verify row counts, values, and output datatypes.
3. Use `TABLE(function(...))` in SELECT with WHERE, ORDER BY, and aggregations.
4. Join output with other tables; verify cases where the left source has no matching rows when using `OUTER APPLY`.
5. Consume via a cursor FOR loop in PL/SQL.
6. Test limiting results to confirm early termination does not leak cursors or resources.
7. Test exception paths and confirm underlying errors propagate to the caller.
8. Read the execution plan and measure time to first row, total time, PGA, and I/O on representative data.
9. If using parallel execution, verify results, ordering, partition independence, and resource consumption.

## 15. Summary

Pipelined table functions allow PL/SQL to emit rows to the SQL engine incrementally via `PIPE ROW`. SQL consumes the data via `TABLE(function(...))`, enabling filtering, joining, aggregating, or feeding into DML. When row-by-row processing in PL/SQL is needed, iterate over a cursor based on that SELECT statement.

The core pattern is declaring a collection type, defining a function with `RETURN collection_type PIPELINED`, piping each element, and ending with `RETURN;`. For caller-provided data sources, accept a `SYS_REFCURSOR`, FETCH row by row, and pipe transformed rows.

Pipelining avoids materializing an entire collection in PL/SQL and lets callers stop early. Real-world performance still depends on the execution plan, downstream consuming operators, per-row processing cost, resource management, and parallel execution setup. Prefer pure SQL whenever business logic can be clearly expressed in SQL; use pipelined table functions when procedural transformation is needed while still exposing results as a SQL row source.

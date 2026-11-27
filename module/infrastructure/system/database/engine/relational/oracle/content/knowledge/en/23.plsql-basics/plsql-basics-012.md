# DBMS_OUTPUT, Bind Variables, and Running Blocks from Tools in Oracle Database

When learning and developing PL/SQL, you often need to print information to trace execution flow, pass values from a SQL tool into an anonymous block, receive results back from the block, and execute blocks properly in SQL Developer, SQL*Plus, or SQLcl. These three parts are related yet serve distinct roles:

- **DBMS_OUTPUT** lets PL/SQL write messages into a buffer for the client to read and display after the block finishes.
- **Bind variables** are placeholders that receive values from the client/driver, referenced in SQL or PL/SQL with a leading colon, such as `:p_employee_id`.
- **How a block is run** depends on the tool and execution mode. A block can be sent as a single statement or run as a script containing client control commands such as SET SERVEROUTPUT ON, VARIABLE, PRINT, and the forward slash.

DBMS_OUTPUT aids debugging; bind variables pass typed data; and the script runner governs how statements are dispatched to the database. Understanding all three helps avoid situations where a block succeeds yet shows no output, or where bind variables are confused with text substitution variables.

## 1. What Is DBMS_OUTPUT?

### 1.1. A Package for Emitting Messages from PL/SQL

DBMS_OUTPUT is an Oracle-supplied package. A PL/SQL program calls the package to write text into an output buffer:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from PL/SQL');
END;
/
```

PUT_LINE appends a line to the buffer. A client that supports DBMS_OUTPUT reads the buffer after the block completes and displays the contents.

DBMS_OUTPUT is commonly used to:
- Learn PL/SQL syntax and inspect variable values.
- Debug anonymous blocks or stored procedures.
- Print verification details in administrative scripts.
- Track row counts, states, or logic branches during a test run.

### 1.2. Output Is Buffered, Not a Real-Time Console

DBMS_OUTPUT.PUT_LINE does not immediately send each line to the screen like a print function in an application. Content is stored in a buffer; the client reads the buffer after the PL/SQL unit completes.

Example:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Step 1');
    DBMS_OUTPUT.PUT_LINE('Step 2');

    DBMS_LOCK.SLEEP(5);

    DBMS_OUTPUT.PUT_LINE('Step 3');
END;
/
```

While the block is still running, clients normally do not display the lines already written. Only after the block finishes does the client fetch and display the output. Therefore, DBMS_OUTPUT is not suited for monitoring real-time progress of a long-running task.

### 1.3. Not a Replacement for a Logging System

DBMS_OUTPUT is suitable for debugging and interactive scripts, not a durable logging system:
- The output buffer is not a persistent history table.
- Messages are not automatically written to application log files.
- If the client has not enabled or read output, users will not see the messages.
- Output should not be used as an audit trail or long-term traceability store.

For production logging, consider a controlled log table, unified auditing, application logging, or appropriate monitoring tools. Avoid printing passwords, tokens, connection strings, or unnecessary personal data.

## 2. Commonly Used DBMS_OUTPUT Procedures

### 2.1. PUT_LINE

PUT_LINE writes a line and automatically appends a newline character:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Employee report');
    DBMS_OUTPUT.PUT_LINE('Total employees: 25');
END;
/
```

This is the most frequently used procedure when debugging.

### 2.2. PUT and NEW_LINE

PUT writes content without ending the line. NEW_LINE terminates the current line:

```sql
BEGIN
    DBMS_OUTPUT.PUT('Processing ');
    DBMS_OUTPUT.PUT('employees');
    DBMS_OUTPUT.NEW_LINE;
    DBMS_OUTPUT.PUT_LINE('Finished');
END;
/
```

They can be used to assemble multiple parts onto a single line. In practice, PUT_LINE is usually easier to read.

### 2.3. Printing Variable Values

Use the concatenation operator || to include values in a message:

```sql
DECLARE
    v_employee_id NUMBER := 100;
    v_salary      NUMBER := 25000;
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Employee ID = ' || v_employee_id
    );

    DBMS_OUTPUT.PUT_LINE(
        'Salary = ' || TO_CHAR(v_salary)
    );
END;
/
```

Use TO_CHAR with a format mask when consistent number/date formatting is needed:

```sql
DECLARE
    v_amount NUMBER := 1234567.5;
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Amount = ' || TO_CHAR(v_amount, 'FM999G999G990D00')
    );
END;
/
```

Separators depend on NLS settings. If the output is used for comparison or automated processing, specify the format explicitly.

### 2.4. ENABLE and DISABLE

The package provides procedures to control the buffer:

```sql
BEGIN
    DBMS_OUTPUT.ENABLE;
    DBMS_OUTPUT.PUT_LINE('Output is enabled');
END;
/
```

DBMS_OUTPUT.ENABLE turns on the output buffer on the database session side. DBMS_OUTPUT.DISABLE turns output off:

```sql
BEGIN
    DBMS_OUTPUT.DISABLE;
END;
/
```

In SQL Developer, SQL*Plus, or SQLcl, it is usually best to use the client command SET SERVEROUTPUT ON, which both enables output and tells the client to fetch its contents. Calling ENABLE in PL/SQL alone will not cause the tool window to display the buffer if the client does not read it.

### 2.5. GET_LINE and GET_LINES

Clients can read the output buffer via API:
- GET_LINE retrieves a single line.
- GET_LINES retrieves multiple lines in a single call.

This is the mechanism many tools use to fetch output after running PL/SQL. In a plain JDBC application, the driver does not automatically display DBMS_OUTPUT merely because the block calls PUT_LINE; the application must enable and read the buffer via the corresponding package calls or a framework utility.

You do not need to call GET_LINE/GET_LINES manually in regular SQL*Plus scripts when using SET SERVEROUTPUT ON.

## 3. Enabling and Viewing DBMS_OUTPUT in Tools

### 3.1. SQL*Plus and SQLcl

In SQL*Plus or SQLcl, run:

```sql
SET SERVEROUTPUT ON
```

You can request a larger buffer:

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED
```

Then run the block:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from SQL*Plus or SQLcl');
END;
/
```

The client fetches the output after the block completes. SET SERVEROUTPUT is a client command, not a SQL statement sent directly to the database.

### 3.2. SQL Developer

SQL Developer has two common worksheet execution modes:

- **Run Statement** (typically Ctrl+Enter or F9): executes the selected statement/PLSQL block or the one at the cursor position.
- **Run Script** (F5): executes the worksheet as a script, supporting SQL*Plus commands emulated by SQL Developer such as SET SERVEROUTPUT ON, VARIABLE, PRINT, and the forward slash.

To view DBMS_OUTPUT:
1. Open the DBMS Output panel via the View menu if it is not visible.
2. Click the plus icon in the panel and select the right connection.
3. Enable output for that connection.
4. Run the PL/SQL block.
5. View the contents in the DBMS Output panel after the block completes.

The UI may vary slightly across SQL Developer versions. In a script you can write:

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED

BEGIN
    DBMS_OUTPUT.PUT_LINE('Running from SQL Developer');
END;
/
```

If running the block with Run Statement, verify that the DBMS Output panel is enabled for the right connection. Do not confuse successful block execution with the client being configured to fetch output.

### 3.3. Differences Between Run Statement and Run Script

Example block:

```sql
DECLARE
    v_message VARCHAR2(100) := 'Statement mode';
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_message);
END;
```

When running as a PL/SQL statement, select the whole block or place the cursor inside the block and use Run Statement. In this mode, the forward slash is a script runner command and generally should not be included in the submitted statement.

When running via Run Script, place a forward slash on its own line to instruct the script runner to execute the block ending with END;.

If you encounter errors like invalid SQL statement or the block gets split into fragments, check whether you are using Run Statement or Run Script and how the forward slash is placed.

### 3.4. DBeaver and Other Tools

Tools like DBeaver, DataGrip, or database IDEs may have their own output tabs/panels and different ways to enable DBMS_OUTPUT. Check:
- Does the tool support DBMS_OUTPUT?
- Is there an Enable/Start DBMS Output button for the connection?
- Does the tool automatically read the buffer after the block completes?
- Does the script runner support SET SERVEROUTPUT, VARIABLE, PRINT, or the forward slash?
- When using JDBC, does the tool call DBMS_OUTPUT.GET_LINES?

Do not assume every SQL editor automatically displays DBMS_OUTPUT the same way as SQL*Plus.

## 4. Buffer and Output Limits

### 4.1. Buffer Size

DBMS_OUTPUT writes content to a buffer. If a program generates a lot of output, the buffer is subject to limits depending on configuration and Oracle/client version. You can request a large buffer with:

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED
```

Or call ENABLE with a buffer size per your version's documentation. When the buffer overflows, the program can encounter a buffer overflow error, such as ORU-10027. Avoid printing hundreds of thousands of lines just for debugging.

### 4.2. Single-Line Length

An output line has a length limit, typically up to 32,767 bytes in modern releases. Unicode strings can take more bytes than visible characters. If a message is too long, split it into multiple lines or print only the portion needed for investigation.

```sql
DECLARE
    v_text VARCHAR2(1000) := RPAD('A', 1000, 'A');
BEGIN
    FOR i IN 0 .. 4 LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Chunk ' || i || ': ' || SUBSTR(v_text, i * 200 + 1, 200)
        );
    END LOOP;
END;
/
```

### 4.3. Printing Many Lines Affects Performance

Every PUT_LINE call generates more data to buffer and for the client to fetch. Printing too much content can:
- Increase block execution time.
- Increase data transferred from the database to the client.
- Make the output window hard to use.
- Bury important messages.

Print meaningful checkpoints, row counts, and specific values under investigation. For large batches, print per batch rather than per row.

### 4.4. No Mid-Block Flushing

DBMS_OUTPUT does not provide a public flush mechanism to push individual lines immediately to the client while a block is still running. PUT_LINE only appends to the buffer; the client reads after the unit finishes. If real-time progress tracking is needed, use another logging/monitoring mechanism or design a job with observable status.

## 5. What Is a Bind Variable?

### 5.1. Client-Supplied Placeholders

A bind variable is a placeholder whose value is transmitted separately from the SQL/PLSQL statement. In Oracle SQL, binds are usually written with a colon:

```sql
SELECT employee_id,
       first_name,
       salary
FROM   employees
WHERE  department_id = :p_department_id;
```

P_DEPARTMENT_ID is a bind variable. The SQL statement is parsed with the placeholder, while the value is sent separately at execution time.

In a PL/SQL anonymous block:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Department = ' || :p_department_id
    );
END;
/
```

Here :p_department_id is a client-supplied bind, not a variable declared in the block's DECLARE section.

### 5.2. Contrast with Local PL/SQL Variables

A PL/SQL variable is declared inside DECLARE:

```sql
DECLARE
    v_department_id NUMBER := 10;
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_department_id);
END;
/
```

The variable v_department_id is scoped only to the block. It does not use a colon when referenced inside PL/SQL.

A host/client-supplied bind variable is referenced with a colon:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(:p_department_id);
END;
/
```

Do not declare bind variables inside DECLARE. Declare them using client/driver commands or pass them via the execution API.

### 5.3. Benefits of Bind Variables

Bind variables typically provide:
- SQL cursor reuse when the SQL text is identical and only values change.
- Reduced hard-parse overhead in repetitive workloads.
- Separation of data from SQL statement structure.
- Reduced risk of SQL injection when values are bound properly.
- Explicit datatype transmission through the driver.

Bind variables do not guarantee every query always gets the same optimal execution plan. Bind peeking and adaptive cursor sharing can affect plans depending on data skew and bind values.

### 5.4. Bind Values, Not Column Names or Table Names

Binds are for expression values:
- WHERE employee_id = :p_id
- SET salary = :p_salary
- WHERE created_at >= :p_from_date

You cannot use binds in place of table names, column names, or SQL keywords:

```sql
-- Does not work as a way to bind a table name:
SELECT * FROM :p_table_name;
```

If you need to choose table/column names dynamically, build controlled dynamic SQL using an allowlist of valid names and appropriate validation measures such as DBMS_ASSERT. Never concatenate raw user strings into SQL.

## 6. Bind Variables in SQL*Plus and SQLcl

### 6.1. Declaring with VARIABLE

In SQL*Plus/SQLcl, use the client command VARIABLE (abbreviated VAR) to declare a bind:

```sql
VARIABLE b_department_id NUMBER
```

Assign a value using EXECUTE:

```sql
EXEC :b_department_id := 10;
```

Use in a SELECT statement:

```sql
SELECT department_id,
       department_name
FROM   departments
WHERE  department_id = :b_department_id;
```

VARIABLE and EXEC here are client commands. They are not variable declaration syntax inside an anonymous block.

### 6.2. Bind Variables with an Anonymous Block

```sql
VARIABLE b_department_id NUMBER
VARIABLE b_employee_count NUMBER

EXEC :b_department_id := 10;

BEGIN
    SELECT COUNT(*)
    INTO   :b_employee_count
    FROM   employees
    WHERE  department_id = :b_department_id;

    DBMS_OUTPUT.PUT_LINE(
        'Employees in department ' ||
        :b_department_id ||
        ': ' ||
        :b_employee_count
    );
END;
/

PRINT b_employee_count
```

Inside the block, the colon indicates a client-owned variable. PRINT displays the bind value after the block finishes.

### 6.3. OUT Bind Variables

A bind can receive a value from PL/SQL:

```sql
VARIABLE b_message VARCHAR2(200)

BEGIN
    :b_message := 'Completed successfully';
END;
/

PRINT b_message
```

This is how data is returned from an anonymous block to SQL*Plus/SQLcl. In applications, drivers register and read OUT parameters through their respective APIs.

### 6.4. IN, OUT, and IN OUT in Procedures

A procedure can accept parameters:

```sql
CREATE OR REPLACE PROCEDURE get_employee_salary (
    p_employee_id IN  employees.employee_id%TYPE,
    p_salary      OUT employees.salary%TYPE
)
AS
BEGIN
    SELECT salary
    INTO   p_salary
    FROM   employees
    WHERE  employee_id = p_employee_id;
END;
/
```

Calling the procedure from SQL*Plus/SQLcl:

```sql
VARIABLE b_salary NUMBER

EXEC get_employee_salary(100, :b_salary);

PRINT b_salary
```

- IN: data passed into the procedure.
- OUT: the procedure assigns a value to return.
- IN OUT: a value is passed in and may be modified and returned.

Bind variables exist on the client side; formal parameters are part of the procedure declaration. The two connect when the client passes a bind to a procedure parameter.

## 7. Bind Variables and Substitution Variables Are Not the Same

### 7.1. Substitution Variables Replace Text Before Sending SQL

In SQL*Plus/SQLcl, substitution variables use & or &&:

```sql
DEFINE department_id = 10

SELECT department_id,
       department_name
FROM   departments
WHERE  department_id = &department_id;
```

The client replaces &department_id with the literal text 10 before sending the SQL statement to the database. This is text substitution, not binding.

### 7.2. Comparison

| Feature | Bind Variable :name | Substitution Variable &name |
| --- | --- | --- |
| Processing | Value passed separately at execute time | Text replaced before sending SQL |
| Data type | Typed by bind/driver | Plain text substituted inline |
| Cursor reuse | Supports cursor sharing for identical SQL | Changing values produce different SQL text |
| Safety | Separates values from SQL structure | Dangerous if untrusted text is injected |
| Usable for object names | No | Can substitute text, but must be strictly controlled |

### 7.3. Example

Bind:

```sql
VARIABLE b_dept NUMBER
EXEC :b_dept := 20;

SELECT *
FROM employees
WHERE department_id = :b_dept;
```

Substitution:

```sql
DEFINE dept = 20

SELECT *
FROM employees
WHERE department_id = &dept;
```

In the bind example, the SQL sent to Oracle still contains the placeholder. In the substitution example, the client replaces &dept with 20 and sends the expanded SQL statement.

### 7.4. When to Use Substitution?

Substitution is useful in scripts to:
- Select an environment-specific schema/table from controlled values.
- Substitute a SQL fragment or script option.
- Accept text parameters when running scripts.

Because substitution modifies the SQL text prior to parsing, never use it in place of binds for untrusted user data. For normal filter values, prefer bind variables.

## 8. Bind Variables in SQL Developer

### 8.1. Declaring Binds in Run Script

In a SQL Developer worksheet:

```sql
VARIABLE b_emp_id NUMBER
VARIABLE b_salary NUMBER

EXEC :b_emp_id := 100;

BEGIN
    SELECT salary
    INTO   :b_salary
    FROM   employees
    WHERE  employee_id = :b_emp_id;

    DBMS_OUTPUT.PUT_LINE('Salary = ' || :b_salary);
END;
/

PRINT b_salary
```

Execute with Run Script (F5) so SQL*Plus commands like VARIABLE, EXEC, PRINT, and the forward slash are processed by the script runner.

### 8.2. Running a Standalone Block

If you only need to run:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Test block');
END;
```

Select the block or place the cursor inside the block and use Run Statement. Ensure the DBMS Output panel is enabled for the right connection to see output.

If the block uses bind variables, make sure the binds have been created/assigned in the same connection/session where the block executes. VARIABLE/PRINT commands should be run in script mode if the worksheet needs to handle them as client commands.

### 8.3. Bind Variables Panel

Some versions of SQL Developer provide a panel or dialog to enter bind values when running a statement. When the tool prompts for binds:
1. Verify the bind name in the SQL/block.
2. Enter a value of the right type.
3. Execute the statement.
4. Inspect the results or OUT binds via the tool UI.

The UI may vary across versions. For multi-step examples, VARIABLE + EXEC + block + PRINT run with F5 is usually easier to repeat and save as a script.

### 8.4. Connection/Session Matters Greatly

Bind variables in SQL*Plus/SQLcl or SQL Developer are tied to a specific session/connection. If you switch worksheet connections or open another session, do not assume old binds are still available.

When encountering a "bind variable not declared" error, check:
- Was VARIABLE declared?
- Did the declaration run in the same connection?
- Are you using Run Script or Run Statement?
- Does the bind name match?
- Is the colon present where needed?

## 9. Running Anonymous Blocks from Tools

### 9.1. Anonymous Block Structure

```sql
DECLARE
    -- Declare local variables, cursors, types, and exceptions
BEGIN
    -- Executable statements
EXCEPTION
    -- Exception handling
END;
/
```

DECLARE is optional. BEGIN and END are mandatory. Statements inside end with a semicolon.

### 9.2. Semicolons and Forward Slashes

In SQL*Plus/SQLcl scripts:
- Semicolons terminate PL/SQL statements inside the block.
- A forward slash on its own line tells the client to execute the block currently in the SQL buffer.

Example:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello');
END;
/
```

The forward slash is not part of the PL/SQL block syntax sent directly to the database. It is a client script runner command. Therefore, whether to include the forward slash depends on execution mode.

### 9.3. EXECUTE/EXEC

SQL*Plus/SQLcl supports the shorthand command:

```sql
EXEC DBMS_OUTPUT.PUT_LINE('One PL/SQL statement');
```

EXEC/EXECUTE is a client command for executing a single PL/SQL statement. For multi-statement logic, local variables, or exception handling, writing a full anonymous block is clearer.

### 9.4. Running a Stored Procedure

If a procedure already exists:

```sql
BEGIN
    get_employee_salary(
        p_employee_id => 100,
        p_salary      => :b_salary
    );
END;
/
```

When a procedure has an OUT parameter, use a bind to receive the result on the client.

### 9.5. Displaying Compilation Errors

If an anonymous block fails, the client typically reports ORA-06550 along with the PL/SQL line/column position. Read the first error and the indicated location before fixing.

For an existing stored procedure/function/package, you can use:

```sql
SHOW ERRORS PROCEDURE get_employee_salary;
```

Or inspect errors in the data dictionary:

```sql
SELECT line,
       position,
       text
FROM   user_errors
WHERE  name = 'GET_EMPLOYEE_SALARY'
ORDER  BY sequence;
```

SHOW ERRORS is a SQL*Plus/SQLcl client command emulated by some script runners. It is not a standard SQL statement.

## 10. Receiving Data Returned from a Block

### 10.1. DBMS_OUTPUT Is a Display Channel

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Result = 42');
END;
/
```

The message is displayed if the client has enabled and read DBMS_OUTPUT. This is a text channel for debugging, not the best way for an application to retrieve typed data values.

### 10.2. Use OUT Binds for Structured Values

If an application needs numbers, strings, dates, or ref cursors, use OUT/IN OUT parameters or appropriate output binds rather than parsing DBMS_OUTPUT text.

```sql
VARIABLE b_total NUMBER

BEGIN
    SELECT COUNT(*)
    INTO   :b_total
    FROM   employees;
END;
/

PRINT b_total
```

The value b_total is returned as a typed NUMBER bind, not a string requiring parsing from text output.

### 10.3. RETURNING INTO for DML

For INSERT/UPDATE/DELETE operations that need affected column values back, consider RETURNING INTO:

```sql
VARIABLE b_new_id NUMBER

BEGIN
    INSERT INTO departments (department_name)
    VALUES ('Research')
    RETURNING department_id INTO :b_new_id;
END;
/

PRINT b_new_id
```

If DEPARTMENT_ID is an identity column, Oracle generates the ID and RETURNING retrieves the exact value of the newly inserted row. Do not run SELECT MAX(id) to find the new ID because another session could insert concurrently.

### 10.4. REF CURSOR and Multi-Row Results

If an application needs a set of rows, a procedure can return a SYS_REFCURSOR via an OUT parameter. How it is read depends on the driver/tool. Do not print an entire result set to DBMS_OUTPUT just to pass data to an application.

## 11. JDBC and Applications Calling PL/SQL

### 11.1. Binds in PreparedStatement

A Java application can use PreparedStatement:

```java
String sql =
    "SELECT salary FROM employees WHERE employee_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 100L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            System.out.println(rs.getBigDecimal(1));
        }
    }
}
```

The ? is a JDBC placeholder. The driver sends the value separately, enabling SQL reuse and avoiding concatenating user input into statements.

### 11.2. Calling a PL/SQL Block with CallableStatement

```java
String plsql =
    "BEGIN " +
    "  get_employee_salary(?, ?); " +
    "END;";

try (CallableStatement cs = connection.prepareCall(plsql)) {
    cs.setLong(1, 100L);
    cs.registerOutParameter(2, Types.NUMERIC);
    cs.execute();

    BigDecimal salary = cs.getBigDecimal(2);
}
```

The example uses the first parameter as IN and the second as OUT. JDBC types must align with Oracle types and the driver. For complex types such as REF CURSOR, use the corresponding Oracle JDBC APIs.

### 11.3. DBMS_OUTPUT in JDBC Does Not Appear Automatically

When Java invokes a block containing DBMS_OUTPUT.PUT_LINE, the text remains inside the DBMS_OUTPUT buffer. JDBC does not automatically route that buffer to System.out.

To retrieve the output, the application must:
1. Call DBMS_OUTPUT.ENABLE on the connection/session.
2. Execute the PL/SQL block.
3. Call DBMS_OUTPUT.GET_LINES or GET_LINE to fetch the contents.
4. Display or log the text at the application layer.
5. Disable/clean up configuration if the application follows a specific convention.

In production systems, avoid enabling DBMS_OUTPUT for every request unless debugging is needed; heavy output increases overhead and generates unnecessary data.

### 11.4. Stay on the Same Connection

OUT binds and the DBMS_OUTPUT buffer belong to the executing session/connection. If an application uses a connection pool, read the output on the exact same connection that ran the block before returning it to the pool. Do not run the block on connection A and call GET_LINES on connection B.

## 12. Methodical PL/SQL Debugging

### 12.1. Printing Checkpoints

```sql
DECLARE
    v_count NUMBER;
BEGIN
    DBMS_OUTPUT.PUT_LINE('Step 1: start');

    SELECT COUNT(*)
    INTO   v_count
    FROM   employees;

    DBMS_OUTPUT.PUT_LINE('Step 2: count=' || v_count);

    IF v_count = 0 THEN
        DBMS_OUTPUT.PUT_LINE('No employees found');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Employees exist');
    END IF;

    DBMS_OUTPUT.PUT_LINE('Step 3: finish');
END;
/
```

The output shows how far the block progressed and variable values at a given point.

### 12.2. Printing Exceptions

```sql
DECLARE
    v_salary NUMBER;
BEGIN
    SELECT salary
    INTO   v_salary
    FROM   employees
    WHERE  employee_id = -1;

    DBMS_OUTPUT.PUT_LINE('Salary=' || v_salary);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('No employee found');

    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('More than one employee found');

    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Unexpected error: ' || SQLERRM
        );
        RAISE;
END;
/
```

SQLERRM returns the current error message inside a handler. When catching WHEN OTHERS, consider re-raising with RAISE so unexpected errors are not masked. Do not merely print an error and continue as if the block succeeded.

### 12.3. Avoid Printing Every Row for Large Data

On large tables, looping PUT_LINE per row can generate massive output. Instead, print total row counts, a few samples, or batch checkpoints:

```sql
DBMS_OUTPUT.PUT_LINE('Processed batch: ' || v_batch_no);
```

To monitor long-running job progress, persist batch status in a job table or use monitoring tools instead of waiting on DBMS_OUTPUT.

### 12.4. Do Not Log Sensitive Information

Do not print passwords, access tokens, connection strings containing credentials, or unnecessary personal data. Output can be saved in script history, screenshots, or client logs.

## 13. Common Errors and How to Troubleshoot Them

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Block succeeds but no output appears | DBMS_OUTPUT disabled or client not reading buffer | Enable DBMS Output panel / SET SERVEROUTPUT ON |
| Output appears only after block finishes | DBMS_OUTPUT is buffered, not flushed real-time | This is normal behavior |
| SP2 error running SET/VARIABLE/PRINT | Sending client command as SQL statement or unsupported tool | Run in script mode or use driver API |
| Bind variable not declared | Bind undeclared, wrong connection, or misspelled name | Check VARIABLE/Bind panel and colon usage |
| ORA-06550 | Syntax error or PL/SQL error in block | Read line/position and subsequent PL/SQL error |
| ORA-01403 | SELECT INTO found no rows | Handle NO_DATA_FOUND |
| ORA-01422 | SELECT INTO returned multiple rows | Fix predicate or use cursor/collection |
| Output buffer overflow | Too much output or buffer too small | Reduce output or configure larger buffer |
| Output line too long | Exceeded line length limit | Split across multiple lines |
| CURRVAL not yet defined | Session has not called NEXTVAL | Call NEXTVAL first in the same session |

### 13.1. Block Runs but Panel Is Empty

Check in order:
1. Did the block actually execute successfully?
2. Is PUT_LINE on the logic branch that executed?
3. Did the client enable DBMS_OUTPUT?
4. Is the panel attached to the right connection?
5. Did the client fetch output after block completion?
6. Did a buffer error or another error occur before PUT_LINE?

Do not scatter dozens of PUT_LINE calls before determining whether the issue is that the block did not run or the client did not read the output.

### 13.2. Bind Variable Receives No Value

Check:
- Does the bind name in the block match the declared name?
- Is there a colon before the bind?
- Is the bind type compatible with the column/parameter?
- Was a value assigned before execution?
- Was the bind declared in the same session?
- Is the tool executing VARIABLE as a client command in script mode?

### 13.3. Binds in Dynamic SQL

In dynamic SQL, bind values should be passed via USING:

```sql
DECLARE
    v_count NUMBER;
    v_dept_id NUMBER := 10;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM employees WHERE department_id = :x'
        INTO v_count
        USING v_dept_id;

    DBMS_OUTPUT.PUT_LINE('Count=' || v_count);
END;
/
```

The value v_dept_id is bound via USING without concatenating into the SQL string. USING argument order must match the placeholders according to native dynamic SQL rules.

## 14. Comprehensive Practice Exercises

### Exercise 1 — Enable DBMS_OUTPUT

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED

BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello Oracle');
END;
/
```

Observe the output after the block completes.

### Exercise 2 — Print Local Variables

```sql
DECLARE
    v_name VARCHAR2(50) := 'An';
    v_age  NUMBER := 25;
BEGIN
    DBMS_OUTPUT.PUT_LINE('Name=' || v_name);
    DBMS_OUTPUT.PUT_LINE('Age=' || v_age);
END;
/
```

Distinguish local variables from bind variables.

### Exercise 3 — Use PUT and NEW_LINE

```sql
BEGIN
    DBMS_OUTPUT.PUT('Oracle ');
    DBMS_OUTPUT.PUT('PL/SQL');
    DBMS_OUTPUT.NEW_LINE;
END;
/
```

Observe assembling content on a single line.

### Exercise 4 — IN Bind

```sql
VARIABLE b_dept NUMBER
EXEC :b_dept := 10;

BEGIN
    DBMS_OUTPUT.PUT_LINE('Department=' || :b_dept);
END;
/

PRINT b_dept
```

Change the bind value and re-run.

### Exercise 5 — OUT Bind

```sql
VARIABLE b_count NUMBER

BEGIN
    SELECT COUNT(*)
    INTO :b_count
    FROM employees;
END;
/

PRINT b_count
```

Explain why the OUT bind has type NUMBER whereas DBMS_OUTPUT is plain text.

### Exercise 6 — Binds and SELECT INTO

Use an employee ID bind to query salary into an output bind. Test a nonexistent ID and handle NO_DATA_FOUND.

### Exercise 7 — Substitution Variables

Use DEFINE and & to substitute a value in a script. Compare the SQL text after substitution with a SQL statement using a :name bind.

### Exercise 8 — Running in SQL Developer

Run a block using Run Statement, then run a script with SET SERVEROUTPUT ON and a forward slash using Run Script. Note the differences.

### Exercise 9 — Stored Procedure with OUT

Create a procedure taking employee ID as IN and salary as OUT. Call it with a bind and PRINT the result.

### Exercise 10 — Dynamic SQL with USING

Use EXECUTE IMMEDIATE and USING to pass a filter value. Explain why you should not concatenate user values directly into a SQL string.

### Exercise 11 — Exception Handling

Create a SELECT INTO returning no rows and print a message in NO_DATA_FOUND. Add WHEN OTHERS with RAISE and observe the returned error.

### Exercise 12 — Batch Debugging

Write a batch-processing block that prints only the batch number, processed row count, and final status. Avoid printing individual rows for large data.

## 15. Safe and Repeatable Block Execution Workflow

Before running a PL/SQL script:
1. Verify the target database, service, schema, and connection.
2. Identify the tool in use: SQL*Plus, SQLcl, SQL Developer, or JDBC.
3. If DBMS_OUTPUT is needed, enable output on the right session/connection.
4. Declare bind variables and assign values before calling the block.
5. Use the right mode: Run Statement or Run Script.
6. Put a forward slash on its own line when required by the script runner.
7. Inspect output, errors, and OUT binds after the block finishes.
8. Verify transaction handling: does COMMIT/ROLLBACK match business requirements?
9. Ensure output contains no credentials or sensitive data.
10. Keep scripts repeatable and avoid unintended destructive DDL/DML.

For multi-step scripts, you can structure them as:

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED

VARIABLE b_result NUMBER

DECLARE
    v_local_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO   v_local_count
    FROM   employees;

    :b_result := v_local_count;

    DBMS_OUTPUT.PUT_LINE(
        'Employee count = ' || v_local_count
    );
END;
/

PRINT b_result
```

The script demonstrates three scopes:
- v_local_count: local variable inside the PL/SQL block.
- :b_result: client-side bind variable receiving the result.
- DBMS_OUTPUT: debug message displayed by the client after the block ends.

## 16. Oracle Reference Documentation

- [Oracle Database PL/SQL Packages and Types Reference — DBMS_OUTPUT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_OUTPUT.html): PUT_LINE, PUT, NEW_LINE, ENABLE, DISABLE, GET_LINE, and GET_LINES.
- [Oracle Database SQL*Plus User's Guide and Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqpug/): SET SERVEROUTPUT, VARIABLE, PRINT, EXECUTE, and script execution.
- [Oracle SQL Developer User's Guide](https://docs.oracle.com/en/database/oracle/sql-developer/): worksheets, Run Statement, Run Script, and the DBMS Output panel.
- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/): anonymous blocks, PL/SQL variables, procedures, and parameter modes.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/): SQL syntax and using binds in statements.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/): SQL injection and secure practices when building dynamic SQL.

DBMS_OUTPUT lets PL/SQL send debug messages through a buffer for the client to read after a block finishes. Bind variables pass typed values from the client into SQL/PLSQL or receive results via OUT binds; they differ from substitution variables, which replace text prior to parsing. When running blocks, identify the right tool and Run Statement/Run Script mode, enable DBMS_OUTPUT for the right connection, declare binds in the right session, and include a forward slash when the script runner requires it.

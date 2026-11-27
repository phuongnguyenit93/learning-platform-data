# Managing Bind Variables, Substitution Variables, and SQL/PLSQL Terminators in Scripts

## 1. Why Are These Three Concepts Important?

When writing an Oracle script, lines that look similar may be handled by **two different places**: the script runner tool such as SQL\*Plus/SQLcl and Oracle Database itself. This explains why the same `&`, `:`, or `/` character can make a script succeed in SQL\*Plus yet fail when sent over JDBC.

Example:

```sql
SELECT &p_id AS id_from_substitution FROM dual;
SELECT :b_id AS id_from_bind FROM dual;

BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello, Oracle');
END;
/
```

Three differences appear in this example:

1. `&p_id` is a **substitution variable**: SQL\*Plus/SQLcl replaces the text `&p_id` before sending the SQL statement to Oracle.
2. `:b_id` is a **bind variable**: a value passed separately from the SQL text, typed and requiring declaration/assignment in the execution tool.
3. `/` on **its own line** is a script-tool command to execute the PL/SQL block currently held in the buffer; it is neither a division operator nor part of PL/SQL syntax.

Confusing these mechanisms leads to unexpected prompts for input, undeclared-bind errors, PL/SQL blocks failing to execute, or the same SQL statement running twice.

**Goal after this lesson:** you will be able to choose the right variable type for each purpose, manage variable lifecycles within a script session, distinguish `;` from `/`, write a `.sql` file that executes sequentially in SQL\*Plus/SQLcl, and recognize differences when running statements from Java/JDBC or a GUI tool.

## 2. Understanding How a Statement Travels Through an Oracle Script

Picture two processing layers:

```text
.sql file or command typed in terminal
                  |
                  v
       SQL*Plus / SQLcl / script tool
       - Reads DEFINE, ACCEPT, VARIABLE, SET
       - Expands &name and &&name
       - Recognizes ;, /, and client commands
       - Attaches :name bind values if present
                  |
                  v
            Oracle Database
       - Parses SQL or PL/SQL
       - Executes with bind values
       - Returns results / errors / output
                  |
                  v
       Tool displays results
```

In this lesson, examples are written primarily for **Oracle SQL\*Plus** and **Oracle SQLcl**. Both tools support script commands such as `DEFINE`, `VARIABLE`, `PROMPT`, `SET`, `@`, and `/`. SQL Developer in **Run Script** mode (commonly `F5`) supports much of the same syntax, though display formatting, prompting behavior, and support for certain commands may differ. **Run Statement** mode (commonly `Ctrl+Enter`) is not equivalent to running an entire file through SQL\*Plus.

**Distinguish these command groups:**

| Group | Examples | Who Processes It? |
|---|---|---|
| SQL | `SELECT`, `INSERT`, `UPDATE`, `CREATE TABLE` | Oracle Database |
| PL/SQL | `DECLARE ... BEGIN ... END;`, procedures, functions | Oracle Database |
| Client commands | `DEFINE`, `ACCEPT`, `VARIABLE`, `PRINT`, `SET`, `PROMPT`, `@` | SQL\*Plus/SQLcl |
| Script control tokens | `&`, `&&`, standalone `/` line | Script tool before or during submission |

Syntax handled by SQL\*Plus may be **invalid** if sent verbatim over JDBC. Always identify which tool will run a script before writing it.

## 3. Substitution Variables `&name`: Text Replacement Before Oracle Sees SQL

Substitution variables are a feature of SQL\*Plus/SQLcl, not PL/SQL variables. The common syntax is `&variable_name`.

Example in SQL\*Plus:

```sql
SELECT &p_number AS so_duoc_nhap FROM dual;
```

If `p_number` is not yet defined, the tool may display a prompt such as:

```text
Enter value for p_number: 25
```

After the user enters `25`, the tool essentially sends this statement to Oracle:

```sql
SELECT 25 AS so_duoc_nhap FROM dual;
```

Oracle **never knows** the user originally wrote `&p_number`; it only receives the substituted SQL. Because replacement occurs at the **text** level, the supplied input must form valid SQL syntax once inserted.

### 3.1. `DEFINE`: Pre-Setting a Substitution Value

Instead of typing interactively on every run, you can define a value in the session:

```sql
DEFINE p_number = 25

SELECT &p_number AS so_duoc_chon FROM dual;

UNDEFINE p_number
```

`DEFINE` creates or assigns a substitution variable. `UNDEFINE` removes the definition to prevent values from leaking into subsequent scripts run in **the same session**. `DEFINE` with no arguments lists currently defined variables, though for sensitive data you should avoid printing values to screens or logs.

`DEFINE` and `UNDEFINE` are client commands; normally **do not append `;`** as you would for SQL statements.

### 3.2. How `&name` and `&&name` Differ

| Syntax | Behavior When Undefined | Subsequent Uses |
|---|---|---|
| `&name` | Prompts for a value to substitute at the current position | May prompt again if the variable has not been `DEFINE`d |
| `&&name` | Prompts and **defines the variable to persist in the session** | Reuses the stored value without re-prompting until `UNDEFINE` |
| `DEFINE name = value` | Pre-assigns a value without prompting | Both `&name` and `&&name` can use that value |

Example:

```sql
SELECT '&&p_city' AS thanh_pho_lan_1 FROM dual;
SELECT '&&p_city' AS thanh_pho_lan_2 FROM dual;

UNDEFINE p_city
```

On the first occurrence, the tool prompts for `p_city` if undefined; on the second, it reuses the saved value. The single quotes around `&&p_city` are **SQL string-literal quotes**, not part of the substitution variable's value. If the user enters a string containing unhandled quotes, the SQL statement can fail or change meaning.

Conversely, if you write:

```sql
SELECT &p_city AS gia_tri FROM dual;
```

and enter `Ha Noi` without quotes, Oracle receives an invalid expression. Wrapping `&p_city` in quotes fixes string formation in a toy example, **yet still does not produce a safe parameter**. For user-supplied data, bind variables are far better suited.

### 3.3. `ACCEPT`: Prompting with Text and Basic Type Checking

`ACCEPT` is a SQL\*Plus/SQLcl command for collecting input interactively into a **substitution variable**. Example:

```sql
ACCEPT p_limit NUMBER PROMPT 'Enter numeric limit: '

SELECT &p_limit AS gioi_han FROM dual;

UNDEFINE p_limit
```

`ACCEPT ... NUMBER` validates basic numeric input format per client rules. This is not binding: once accepted, `&p_limit` is still **replaced as text**. `ACCEPT` is useful for interactive admin/diagnostic scripts, whereas Java applications collect data at the API layer and send binds through the driver.

### 3.4. Inspecting Substituted SQL

SQL\*Plus can show the SQL before and after substitution using `SET VERIFY ON`:

```sql
SET VERIFY ON
DEFINE p_number = 7

SELECT &p_number AS n FROM dual;

UNDEFINE p_number
SET VERIFY OFF
```

In the output, you will see `old` and `new` lines showing which text was substituted. `SET VERIFY OFF` hides those lines; it **does not disable variable substitution**. `SET ECHO ON/OFF` is a separate option controlling whether script commands themselves are printed during execution where supported; do not confuse it with `SET VERIFY`.

When scripts involve secret values, echo, verify, spool, and related tool logs must all be controlled. Hiding `old/new` lines alone does not guarantee secrets stay out of other output channels.

## 4. Literal `&` in Real Data: Avoiding Unexpected Prompts

A classic mistake is writing:

```sql
SELECT 'R&D' AS ten_bo_phan FROM dual;
```

In a SQL\*Plus session with substitution enabled, `&` makes the tool interpret what follows as a variable name and prompt for input, even though the developer simply wanted the literal `'R&D'`.

The usual workaround is **disabling substitution** around sections containing literal `&`:

```sql
SET DEFINE OFF

SELECT 'R&D' AS ten_bo_phan FROM dual;
SELECT 'A&B' AS nhan_hieu FROM dual;

SET DEFINE ON
```

`SET DEFINE OFF` affects the **client tool session**, not Oracle Database configuration. Once re-enabled with `SET DEFINE ON`, `&name` expressions are processed again. If another script is called later in the same session, forgetting to turn it back on can prevent expected substitutions.

Some environments support changing the substitution prefix character via `SET DEFINE` with an alternate character; that requires all related scripts to share the convention. To handle strings containing `&` cleanly, you can **initialize a bind variable** inside a `SET DEFINE OFF` block and use the bind in subsequent SQL:

```sql
VARIABLE b_brand VARCHAR2(100)

SET DEFINE OFF
BEGIN
    :b_brand := 'R&D';
END;
/
SET DEFINE ON

SELECT :b_brand AS brand FROM dual;
PRINT b_brand
```

Key point: when the literal `'R&D'` is written directly inside a script file, SQL\*Plus still has to **parse that text**. Bind variables let later SQL use the stored value, while `SET DEFINE OFF` around the initialization prevents SQL\*Plus from touching `&` inside the literal.

## 5. Bind Variables `:name`: Passing Typed Values into SQL/PLSQL

A **bind variable** is a parameter/variable supplied by the tool to Oracle at execution time. Unlike `&name`, Oracle receives the SQL statement with a placeholder and receives the value separately; it never splices value text into the SQL syntax itself.

In SQL\*Plus/SQLcl, bind variables are declared using `VARIABLE` (abbreviated `VAR`):

```sql
VARIABLE b_customer_id NUMBER
VARIABLE b_customer_name VARCHAR2(100)
```

Assign values via a PL/SQL block:

```sql
BEGIN
    :b_customer_id := 101;
    :b_customer_name := 'Nguyen Lan';
END;
/
```

Use the bind variables in a query:

```sql
SELECT :b_customer_id AS customer_id,
       :b_customer_name AS customer_name
FROM dual;
```

Print bind variables using the client command:

```sql
PRINT b_customer_id
PRINT b_customer_name
```

Key points:

- The leading `:` inside SQL/PLSQL (such as `:b_customer_id`) references a tool-supplied bind value. `VARIABLE` and `PRINT`, by contrast, take the **variable name without `:`**.
- `VARIABLE` declarations in SQL\*Plus/SQLcl must occur **before** the variable is used in SQL/PLSQL. Otherwise, you hit errors like `SP2-0552: Bind variable ... not declared`.
- Bind variables persist for the client tool session. `UNDEFINE` removes only **substitution variables**, not bind variables. You can redeclare/reassign as needed or end the session.
- Oracle performs data-type checking and conversions when binding values. For monetary amounts or IDs, choose matching types rather than turning everything into strings.

### 5.1. Quick Assignment with `EXEC`

SQL\*Plus offers `EXEC` (short for `EXECUTE`) to run a single-line PL/SQL statement. Example:

```sql
VARIABLE b_rate NUMBER
EXEC :b_rate := 0.15

SELECT 1000 * :b_rate AS thue FROM dual;
```

`EXEC` is a client-supported shorthand. The semantically equivalent block here is:

```sql
BEGIN
    :b_rate := 0.15;
END;
/
```

When translating to JDBC code, never send literal `EXEC :b_rate := ...` as a SQL statement; use the driver API or a syntactically valid PL/SQL block.

### 5.2. Capturing Data from PL/SQL into a Bind Variable

Bind variables allow passing PL/SQL results outside the block scope:

```sql
VARIABLE b_table_count NUMBER

BEGIN
    SELECT COUNT(*)
    INTO :b_table_count
    FROM user_tables;
END;
/

PRINT b_table_count
```

`USER_TABLES` is a dictionary view listing tables in the connected schema, so this example requires no pre-created `EMPLOYEES` table or app data. `:b_table_count` acts as an output variable here. Conversely, a local PL/SQL variable declared with `DECLARE v_count NUMBER;` exists only inside that block; you cannot run `PRINT v_count` after the block ends unless you assign its value to a client bind variable.

### 5.3. Using Bind Values with `WHERE`, DML, and `RETURNING`

In an application with an `app_customers` table, a parameterized query looks like:

```sql
SELECT customer_id, full_name
FROM app_customers
WHERE customer_id = :b_customer_id;
```

When writing data, binds also work in `INSERT`, `UPDATE`, and `DELETE`. Several Oracle tools support capturing `RETURNING ... INTO` values into bind variables, as illustrated below (run only if you have matching table/columns):

```sql
VARIABLE b_new_id NUMBER
VARIABLE b_email VARCHAR2(200)

BEGIN
    :b_email := 'lan@example.com';
END;
/

INSERT INTO app_customers (email, full_name)
VALUES (:b_email, 'Nguyen Lan')
RETURNING customer_id INTO :b_new_id;

PRINT b_new_id
```

With write examples, you must explicitly manage the transaction: `COMMIT` to confirm, or `ROLLBACK` to undo uncommitted changes. Never assume `PRINT` commits for you. This snippet demonstrates input vs. output binds, not a migration script meant to run blindly on any database.

### 5.4. Binds Cannot Replace Table or Column Names

Binds represent **expression values**; they cannot substitute for SQL syntactic identifiers:

```sql
-- Illustrating the WRONG approach: a table name cannot come from a bind variable like data
SELECT * FROM :b_table_name;
```

When table/column names must vary dynamically, validate against an allowed identifier list (*allowlist*) and construct controlled dynamic SQL; filter values should still be bound. `&table_name` can substitute text to form a table name in a trusted script, yet feeding unvalidated user input into a substitution variable still creates SQL injection risk.

## 6. Comparison Table: `&name`, `&&name`, `:name`, and PL/SQL Variables

| Aspect | `&name` | `&&name` | `:name` in SQL\*Plus | `v_name` declared in PL/SQL |
|---|---|---|---|---|
| Nature | Text substitution variable | Text substitution + persisted value | Bind variable | Local/program PL/SQL variable |
| Where primarily processed? | Script client | Script client | Client passes value to database | PL/SQL engine |
| Typical declaration | `DEFINE`, `ACCEPT`, or prompt | `DEFINE`, first prompt | `VARIABLE` | `DECLARE`, procedure/function parameters |
| How value enters SQL | Text spliced before sending | Text spliced before sending | Bound separately from SQL | Used directly within PL/SQL scope |
| Typed? | Basically text; `ACCEPT` validates input | Same as `&` | Yes, per declaration and driver | Yes |
| Injection risk if splicing input into SQL | High if unvalidated | High if unvalidated | Greatly reduced when properly bound | Depends on usage; concatenated dynamic SQL remains risky |
| Reusable after a PL/SQL block? | If still in client session | Yes until `UNDEFINE` | Yes in client session | No, if merely a block-local variable |

**Practical rule:** for **data values**, prefer binds. For **operator-controlled script structure choices**, substitution variables can be useful, provided input is validated. For **internal PL/SQL computation**, use PL/SQL variables and copy to binds only when results must return to the client.

### 6.1. Two Similar-Looking Examples with Different Mechanics

Substitution variable:

```sql
DEFINE p_id = 42
SELECT &p_id AS customer_id FROM dual;
UNDEFINE p_id
```

The client produces SQL equivalent to `SELECT 42 AS customer_id FROM dual` before Oracle processes it.

Bind variable:

```sql
VARIABLE b_id NUMBER
BEGIN
    :b_id := 42;
END;
/
SELECT :b_id AS customer_id FROM dual;
```

The client passes numeric value `42` for placeholder `:b_id`. The SQL retains its parameterized form. Parameterized statements can help cursor sharing and reduce parsing when used properly, though real impact depends on execution patterns and environment; either way, it is never a reason to concatenate SQL text arbitrarily.

## 7. Terminators: `;` and `/` Have Different Jobs

In SQL\*Plus/SQLcl, distinguish **ending a SQL statement**, **ending a statement inside PL/SQL**, and **telling the tool to execute its buffer**.

### 7.1. Regular SQL Statements End with `;`

```sql
SELECT 'Hello' AS greeting FROM dual;
```

Under common defaults, a trailing semicolon `;` is the **SQL terminator** that SQL\*Plus recognizes to send the SQL statement for execution. `;` ends input inside the tool; it is not a required part of a SQL string passed over every API.

A multi-line SQL statement still needs only one terminator:

```sql
SELECT employee_id,
       first_name,
       last_name
FROM employees
WHERE department_id = 10
ORDER BY employee_id;
```

This example assumes a schema with an `EMPLOYEES` table (such as the HR practice schema); it illustrates SQL termination, not a guarantee that the table exists in every environment.

### 7.2. PL/SQL Blocks Have `;` Inside and Usually Need `/` on Its Own Line

```sql
SET SERVEROUTPUT ON

BEGIN
    DBMS_OUTPUT.PUT_LINE('First line');
    DBMS_OUTPUT.PUT_LINE('Second line');
END;
/
```

- `;` after each `DBMS_OUTPUT.PUT_LINE(...)` call **terminates that PL/SQL statement inside the block**.
- `END;` **syntactically closes the PL/SQL block**.
- `/` **alone on its own line** tells SQL\*Plus/SQLcl to execute the block in the buffer.
- `SET SERVEROUTPUT ON` tells the client to display output produced by `DBMS_OUTPUT.PUT_LINE`; if disabled, the block may still run while showing none of the expected lines.

Do not write `END; /` on the same line when following the SQL\*Plus script model; put `/` on its own line.

In a `DECLARE` block, the structure is identical:

```sql
DECLARE
    v_x NUMBER := 10;
    v_y NUMBER := 20;
BEGIN
    DBMS_OUTPUT.PUT_LINE('Sum = ' || (v_x + v_y));
END;
/
```

### 7.3. Creating Procedures/Functions Also Typically Uses `/`

With `CREATE PROCEDURE` privilege, a script defining a procedure is written as:

```sql
CREATE OR REPLACE PROCEDURE demo_hello
AS
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from procedure');
END;
/
```

Here `END;` completes the PL/SQL definition, while `/` tells the client to submit `CREATE OR REPLACE PROCEDURE` to Oracle to compile/create the object. `CREATE OR REPLACE` modifies database objects; run it only in a practice schema or when authorized. This differs from an anonymous `BEGIN ... END; /` block, which persists no object.

### 7.4. A `/` After an Already-Executed SQL Statement Can Run It Twice

In SQL\*Plus, `/` re-executes whatever SQL or PL/SQL statement is currently in the SQL buffer. Therefore:

```sql
SELECT 'Run 1' AS nhan FROM dual;
/
```

can cause **the `SELECT` statement to execute twice**: once on `;`, and once again on `/`. With `INSERT`, `UPDATE`, or `DELETE`, double execution is far more dangerous: duplicate writes, double increments, or constraint violations.

In normal SQL\*Plus/SQLcl usage, **SQL uses `;`**, while **PL/SQL blocks and stored-program definitions use `END;` followed by a standalone `/` line**. Note that a `;` *inside a string literal* (such as `'A;B'`) is not a SQL statement terminator.

### 7.5. Client Commands Normally Need No `;`

These lines illustrate SQL\*Plus client commands:

```sql
SET SERVEROUTPUT ON
SET VERIFY OFF
DEFINE p_flag = Y
VARIABLE b_value NUMBER
PROMPT Preparing to execute script

UNDEFINE p_flag
```

They are recognized by the tool as its own commands; do not write `SET SERVEROUTPUT ON;` or `DEFINE p_flag = Y;` assuming the Oracle server handles them as SQL. SQL\*Plus allows changing the terminator via settings like `SET SQLTERMINATOR`, so in non-default setups verify the tool's convention. Even if the SQL terminator changes, `;` **inside PL/SQL** remains part of the PL/SQL language syntax with its own role.

### 7.6. Terminator Summary Table

| Content in Script File | Common Termination Style | Reason |
|---|---|---|
| `SELECT`, `INSERT`, `UPDATE`, `DELETE` | `;` | Client sends the SQL statement to execute |
| `CREATE TABLE`, `ALTER TABLE` | `;` | DDL is a SQL statement |
| `BEGIN ... END;` | `END;` then `/` on its own line | `;` belongs to PL/SQL; `/` triggers buffer execution |
| `DECLARE ... BEGIN ... END;` | `END;` then `/` on its own line | Same for anonymous blocks |
| `CREATE OR REPLACE PROCEDURE/FUNCTION/PACKAGE/TRIGGER` | Close PL/SQL syntactically, then `/` on its own line | Tells client to send definition to Oracle |
| `SET`, `DEFINE`, `VARIABLE`, `PRINT`, `PROMPT`, `@file.sql` | Ends at newline | Client-only command |

## 8. Running a `.sql` File from the Right Tool

### 8.1. SQL\*Plus and SQLcl

In a connected tool session, you can execute a script file:

```text
SQL> @demo_variables.sql
```

`@` is SQL\*Plus/SQLcl's script-reading/execution command. When organizing multiple scripts, `@@` is typically used to invoke a related file relative to the currently running script's directory where supported. Exact paths and current working directory behavior depend on the tool version.

Example `demo_variables.sql` file that **reads data only**:

```sql
-- demo_variables.sql: run in SQL*Plus or SQLcl
SET ECHO ON
SET VERIFY OFF
SET SERVEROUTPUT ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

PROMPT === Starting Oracle variables demonstration ===

-- Substitution variable, text-replaced on client
DEFINE p_label = Oracle

-- Bind variable, typed and assigned in PL/SQL
VARIABLE b_table_count NUMBER

BEGIN
    SELECT COUNT(*) INTO :b_table_count FROM user_tables;
    DBMS_OUTPUT.PUT_LINE('Read table count in current schema.');
END;
/

PRINT b_table_count

SELECT '&p_label' AS nhan_script,
       :b_table_count AS so_bang
FROM dual;

UNDEFINE p_label
PROMPT === Completed ===
```

Save this as UTF-8 `demo_variables.sql`, open SQL\*Plus/SQLcl connected to Oracle, and run `@demo_variables.sql` (or specify the file path). The script relies only on `DUAL` and `USER_TABLES`, requiring no application tables or data writes. `WHENEVER SQLERROR` tells the tool to exit on SQL/PLSQL errors per configured rules; it **does not guarantee catching every SQL\*Plus client syntax error**. Production scripts should also add OS error handling and logging where appropriate.

### 8.2. SQL Developer: Run Statement or Run Script?

| Scenario | Usually Suitable Choice | Remember |
|---|---|---|
| Running a single `SELECT` to view grid results | Run Statement (commonly `Ctrl+Enter`) | Tool may handle terminators and bind prompt dialogs automatically |
| Running a file with `SET`, `PROMPT`, `VARIABLE`, multiple SQL and PL/SQL statements | Run Script (commonly `F5`) | Behavior is much closer to SQL\*Plus scripts |
| Initializing bind variables via `VARIABLE`/`PRINT` | Script mode when supported | Does not default to statement mode's bind dialog |
| Running procedures with `/` | Script mode | `/` is a client command, not SQL sent straight to the database |

Not every SQL client fully supports SQL\*Plus syntax. When moving scripts across SQL\*Plus, SQLcl, SQL Developer, JDBC, migration tools, or other IDEs, verify how each tool splits and submits statements.

## 9. Using Variables in Multi-File Scripts

Substitution and bind variables managed by SQL\*Plus/SQLcl generally live at the **tool-session level**, rather than automatically disappearing after one `@file.sql`. This helps scripts share configuration, yet can cause unintended side effects if a later script picks up an old variable.

Example caller `main.sql`:

```sql
DEFINE p_env = DEV
PROMPT Environment: &p_env

@child.sql

UNDEFINE p_env
```

Inside `child.sql`:

```sql
SELECT '&p_env' AS current_env FROM dual;
```

When running `main.sql`, `p_env` is visible in the child file because both share the session. Once the child finishes, `UNDEFINE p_env` cleans up the variable. For nested scripts, avoid overly generic names like `x`, `id`, or `status` that might collide across files.

### 9.1. Positional Parameters `&1`, `&2`

SQL\*Plus/SQLcl also supports passing arguments to script files as positional substitution variables. Example `report_period.sql`:

```sql
SELECT '&1' AS report_period FROM dual;
```

It can be run as:

```text
SQL> @report_period.sql 2026-11
```

Here `&1` is replaced by the first argument. This is still **text replacement**, so it is only appropriate for trusted, validated input. For values originating from application users or external systems, having Java/the driver use binds is far safer than concatenating strings to generate SQL files.

### 9.2. `COLUMN ... NEW_VALUE`: Turning a SQL Result into a Substitution Variable

A reporting script may need the current date as a label:

```sql
COLUMN report_day NEW_VALUE p_report_day NOPRINT

SELECT TO_CHAR(SYSDATE, 'YYYY-MM-DD') AS report_day
FROM dual;

PROMPT Report date: &p_report_day

COLUMN report_day CLEAR
UNDEFINE p_report_day
```

SQL\*Plus captures the selected column's value and stores it in substitution variable `p_report_day`. This is handy for generating report titles or script-controlled filenames. Since the value remains substitution text, be careful never to feed untrusted data into SQL or OS commands this way.

## 10. Java/JDBC Handles Binds and Terminators Differently from SQL\*Plus

In a Java application, you typically **do not** send an entire file containing `DEFINE`, `VARIABLE`, and `/` through a `PreparedStatement`. JDBC sends a SQL statement or PL/SQL block to the database via the driver; the application manages parameters through Java APIs.

Illustrative example when `app_customers` exists:

```java
String sql = "SELECT customer_id, full_name "
           + "FROM app_customers WHERE customer_id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);

    try (ResultSet rows = statement.executeQuery()) {
        while (rows.next()) {
            long id = rows.getLong("customer_id");
            String name = rows.getString("full_name");
            System.out.println(id + " - " + name);
        }
    }
}
```

Key differences to remember:

- With standard `PreparedStatement`, parameters are written using **`?`** and bound positionally via `setLong`, `setString`, `setBigDecimal`, etc. Other Oracle APIs and tools may support named binds, yet never assume every driver interprets `:name` identically.
- SQL strings sent over JDBC **normally omit SQL\*Plus's trailing `;` terminator**. Copying a SQL statement with `;` into Java verbatim can trigger syntax errors like `ORA-00911` or statement-parsing failures.
- A standalone `/` line is a script-tool command, **not** a token Oracle JDBC sends to close a PL/SQL block. A `CallableStatement` or `BEGIN ... END;` block sent via the driver does not use `/` to execute.
- `&p_id` is not a JDBC placeholder: it only means anything if you run SQL\*Plus-style preprocessing beforehand. Never build manual string replacement with `String.replace` to fake binding.

Example PL/SQL call sent via JDBC:

```java
String plsql = "BEGIN DBMS_OUTPUT.PUT_LINE(?); END;";

try (CallableStatement call = connection.prepareCall(plsql)) {
    call.setString(1, "Hello from Java");
    call.execute();
}
```

This illustrates passing a parameter to a PL/SQL block; Oracle `DBMS_OUTPUT` does not automatically print to the Java console unless the application explicitly fetches it. In real applications, Java logging and API responses are far better channels for reporting results.

### Migration Tools Have Their Own Statement Delimiters

Migration and deployment tools such as Flyway, Liquibase, or custom frameworks parse statement boundaries according to their own formats, versions, and configs. Some support `/` for Oracle in specific modes, while others forbid `/` or use custom delimiters. Therefore, **never copy an entire SQL\*Plus script straight into a migration assuming it behaves identically**. Read the parser rules of the actual tool deploying your schema.

## 11. Risks of Choosing the Wrong Variable Type: From Syntax Errors to SQL Injection

Suppose you want to look up a customer by email address. Text substitution like the following is unsafe for untrusted input:

```sql
-- Illustrating what NOT to do with user-supplied data
SELECT customer_id FROM app_customers
WHERE email = '&p_email';
```

If a user supplies an address containing a single quote or crafted SQL fragment, the substituted query can break or change meaning. **Quotes around `&p_email` do not provide bind-level protection.**

In SQL\*Plus, declare and assign a bind variable in a controlled manner:

```sql
VARIABLE b_email VARCHAR2(200)

BEGIN
    :b_email := 'lan@example.com';
END;
/

SELECT customer_id FROM app_customers
WHERE email = :b_email;
```

In Java applications, `PreparedStatement` with `setString(...)` is the right mechanism for input values. The SQL\*Plus example above intentionally uses a safe literal to illustrate binding; when collecting real user input, assignment to binds must still go through appropriate APIs/tools without rebuilding SQL via unsafe string concatenation.

**Distinguish two cases:**

1. **Filter/write values** (`customer_id`, email, amounts, dates...): use binds; perform validation/business checks at the proper layer.
2. **Table names, column names, sort order, optional clauses**: binds cannot replace SQL syntax; select from an allowlisted structure or build safe dynamic SQL with appropriate tools.

Even for internal DBA-only scripts, maintaining a clear habit of separating **value parameters** from **syntactic substitution** prevents operational errors.

## 12. Common Errors and How to Trace Their Causes

| Symptom | Possible Cause | How to Resolve |
|---|---|---|
| Unexpected `Enter value for ...` prompt | `&` was treated as a substitution variable | Check text containing `&`; scope `DEFINE OFF` around literal data |
| `SP2-0552: Bind variable ... not declared` | Used `:b_id` without declaring `VARIABLE b_id ...` in SQL\*Plus | Declare first; check exact spelling and client session |
| `ORA-01008: not all variables bound` | Driver/tool sent SQL with an unbound placeholder | Check bind count, positions, names, and all parameter-binding branches |
| SQL/PLSQL waits for more input or produces no output | Missing terminator or missing standalone `/` to run block in script mode | Distinguish `;` vs. `/`; terminate PL/SQL per client expectations |
| An `INSERT` or `SELECT` runs twice | Used both `;` and `/` right after the same SQL statement in the buffer | Remove unnecessary `/` after already-executed SQL |
| `ORA-00911` or syntax error from JDBC | Sent `;`, `/`, or a client command through the driver | Send pure SQL/PLSQL only; strip script terminators |
| `SET` or `DEFINE` flagged as syntax error in editor/JDBC | Tool is not running in SQL\*Plus-compatible mode | Pick script mode or use APIs supported by that tool |
| Child script picks up wrong `&name` value | Stale substitution variable remained in session | Use clear names; `DEFINE` at start, `UNDEFINE` at end of file |
| `PRINT b_x` shows unexpected/empty value | Bind unassigned, or assigned in a different session/tool | Check `VARIABLE`, `BEGIN...END;/`, and active connection |
| Lots of `old`/`new` lines in logs | `SET VERIFY ON` | Switch to `SET VERIFY OFF` when substitution output isn't needed |

### Quick Diagnostic Checklist

When a script fails, ask in order:

1. **Where is the command running?** SQL\*Plus, SQLcl, SQL Developer Run Script, JDBC, or a migration tool?
2. **Is this SQL/PLSQL or a client command?** `SET`, `DEFINE`, `VARIABLE`, and `PRINT` must be understood by the client.
3. **How are values passed in?** `&`/`&&` is text substitution; `:` or `?` is client/driver binding.
4. **Is the statement terminated properly?** Regular SQL uses `;` in scripts; PL/SQL uses `END;` plus a standalone `/` when needed.
5. **Is state left over from a previous script?** Check `DEFINE`s, bind variables, and `SET` flags in the current session.

## 13. Guided Practice Exercises

Examples in this section can be run in SQL\*Plus/SQLcl after connecting with an account allowed to `SELECT FROM DUAL` and `USER_TABLES`; no table creation or data writes are required.

### Exercise 1: Observing Substitution vs. Bind Variables

```sql
SET VERIFY ON

DEFINE p_score = 90
SELECT &p_score AS score_from_text FROM dual;

VARIABLE b_score NUMBER
BEGIN
    :b_score := 90;
END;
/
SELECT :b_score AS score_from_bind FROM dual;

UNDEFINE p_score
SET VERIFY OFF
```

Observe: for `&p_score`, with `VERIFY` enabled, the client displays `old`/`new` text lines; for `:b_score`, the bind variable is not text-spliced into the SQL line as `90`. Although the query outputs match, the value-passing mechanisms differ.

### Exercise 2: Handling `&` Inside Strings

```sql
SET DEFINE OFF
SELECT 'Sales & Marketing' AS team_name FROM dual;
SET DEFINE ON
```

Explain in your own words why changing the client's preprocessing mode suffices without inventing an Oracle SQL function. Remember to turn `DEFINE` back on if later script sections use `&name`.

### Exercise 3: Understanding PL/SQL vs. Bind Scope

```sql
SET SERVEROUTPUT ON
VARIABLE b_total NUMBER

DECLARE
    v_first NUMBER := 12;
    v_second NUMBER := 30;
BEGIN
    :b_total := v_first + v_second;
    DBMS_OUTPUT.PUT_LINE('Result inside block: ' || :b_total);
END;
/

PRINT b_total
SELECT :b_total AS result_after_block FROM dual;
```

`v_first` and `v_second` exist only inside the block; `:b_total` is a session bind variable that remains usable after the block finishes. `DBMS_OUTPUT` and `PRINT` are **two different mechanisms** for displaying output.

### Exercise 4: Choosing the Right Terminator

Classify each snippet before running it:

```sql
-- A. SQL
SELECT 1 AS n FROM dual;

-- B. PL/SQL
BEGIN
    NULL;
END;
/

-- C. Client command
PROMPT Script done
```

Answer: A uses `;` for the client to run SQL; B uses `;` inside PL/SQL plus a standalone `/` to execute the block; C is a client command completed by a newline. Do not add `/` after A merely because B has `/`.

### Exercise 5: Writing a Script Re-Runnable in the Same Session

Goal: set a report label with `DEFINE`, count schema tables using a bind variable, print the result, and clean up state afterward. You may follow this structure:

```sql
SET VERIFY OFF
DEFINE p_report_name = SCHEMA_REPORT
VARIABLE b_count NUMBER

BEGIN
    SELECT COUNT(*) INTO :b_count FROM user_tables;
END;
/

SELECT '&p_report_name' AS report_name,
       :b_count AS table_count
FROM dual;

UNDEFINE p_report_name
```

Run it a second time in the same session and verify the script cleanly sets its label without prompting for `p_report_name` or carrying over stale values.

## 14. Conventions for Maintainable Scripts

- **Document the target tool** at the top of the file, e.g., `-- Run with SQL*Plus/SQLcl`, because client commands and terminators are tool-dependent.
- **Name variables distinctly**: `p_...` for substitution parameters, `b_...` for binds, `v_...` for local PL/SQL variables. This is a helpful convention, not mandatory Oracle syntax.
- **Prefer binds for data**, even when scripts query repeatedly with different values.
- **Clean up substitution variables with `UNDEFINE`**, and restore modified `SET` options to minimize side effects on later scripts.
- **Place `/` only where needed** for PL/SQL blocks. Double-check DML scripts before adding `/` to avoid accidental double execution.
- **Use `SET SERVEROUTPUT ON` when inspecting `DBMS_OUTPUT`**, without assuming Java app logs automatically capture it.
- **Never put passwords, tokens, or secrets into `DEFINE`, `PROMPT`, logs, or script files**. Use secrets managers and secure input mechanisms appropriate for the tool.
- **Separate inspection scripts from data-changing scripts**; in write scripts, clearly define privileges, transaction boundaries, error handling, and commit/rollback behavior.

## 15. Conclusion

Across the Oracle tool ecosystem, these three rules help you read and write scripts accurately:

1. **`&name` and `&&name` are client-tool text substitutions**: handy for operational parameters, yet no substitute for safe data binding.
2. **`:name` is a bind variable when supported and supplied by the tool**: data travels alongside the statement with type safety and can be used by SQL/PLSQL without manual text concatenation. In standard Java/JDBC, the counterpart is `PreparedStatement` with `?`.
3. **`;` and `/` operate at different syntax layers**: SQL statements normally end with `;` in SQL\*Plus/SQLcl; PL/SQL contains internal `;` terminators and typically needs a standalone `/` line for the client to execute the full block or program definition.

Once you know **who handles each variable**, **when values are injected**, and **which terminator triggers execution**, you can run `.sql` files confidently, move smoothly between SQL\*Plus/SQLcl and Java applications, and avoid the many bugs caused by copying statements across tools with different execution models.

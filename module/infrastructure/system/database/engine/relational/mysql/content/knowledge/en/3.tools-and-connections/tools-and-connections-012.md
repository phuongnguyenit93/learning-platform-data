# DELIMITER in Command-Line Tools and Stored Program Terminators

When running an ordinary SQL statement in the MySQL client, a semicolon (`;`) normally tells the client the statement has ended. However, a stored program such as a procedure, function, or trigger can contain multiple SQL statements, each ending with `;`. If the client stops at the first semicolon, it sends an incomplete definition to the server and triggers a syntax error.

The `DELIMITER` command solves this on the client tool side. It changes the string that the MySQL command-line client uses to recognize the end of the entire statement being entered. As a result, `;` is preserved inside the stored program body, while another string such as `$$` or `//` marks the end of the `CREATE PROCEDURE`, `CREATE FUNCTION`, or `CREATE TRIGGER` statement.

This lesson belongs to the `DATABASE_MYSQL` module, where you practice table design, data types, keys, SQL, indexes, transactions, concurrency control, and relational database operations. Understanding `DELIMITER` helps you create, execute, and maintain stored programs in command-line environments while avoiding confusion between server-side SQL syntax and client control directives.

After this lesson, you will be able to:

- Explain the difference between the statement terminator recognized by the client and the SQL statement separator inside a stored program.
- Change the delimiter in the MySQL command-line client and restore it to `;`.
- Create procedures, functions, and triggers with multiple statements in their body.
- Execute SQL files containing stored programs using the MySQL client.
- Recognize errors caused by an incorrect delimiter and recover when the client is still buffering an incomplete statement.

## 1. Two Processing Layers to Distinguish

When you type SQL into the classic MySQL client (`mysql`), there are two separate steps:

1. **Client reads input:** the client accumulates what you enter. When it encounters the current delimiter, it treats the accumulated text as a complete statement and sends that SQL content to the server.
2. **Server parses SQL:** MySQL receives the statement over the connection protocol and parses the SQL syntax. The server understands `CREATE PROCEDURE`, `BEGIN ... END`, `IF ... END IF`, and the inner statements.

In default mode, the MySQL client's delimiter is `;`. Example:

```sql
SELECT VERSION();
SHOW DATABASES;
```

Each `;` ends a separate statement for the client to send. The `;` is not a standalone SQL statement; it is the statement-termination marker in normal SQL entry.

`DELIMITER` is a command processed by the MySQL client. It is **not an SQL statement sent to the server** and does not alter MySQL's SQL grammar. When the client uses `$$` as its delimiter, `$$` tells the client where the entire `CREATE` statement ends; the `;` characters inside the routine body remain intact inside the text sent to the server.

## 2. Syntax and How to Change the Delimiter

In the MySQL command-line client, the general syntax is:

```text
DELIMITER new_string
```

Example:

```sql
DELIMITER $$
```

From this point onward, the client waits for `$$` before sending the current statement. Semicolons `;` no longer terminate statements on the client side until the delimiter is changed back.

After creating the stored program, restore the default:

```sql
DELIMITER ;
```

You can also choose `//`, `%%`, or another string. Pick a string that is easy to spot and does not appear inside the routine body. `$$` and `//` are two common choices in MySQL examples and documentation.

The `DELIMITER` command is entered on its own line in the MySQL client. Do not append `;` at the end of this directive as though it were SQL. The command name is case-insensitive in the MySQL client.

## 3. Creating a Procedure with Multiple Statements

Suppose you want to create a procedure named `greet_user`. This procedure declares a local variable, normalizes the input parameter, and returns a message. All inner statements end with `;`.

```sql
DROP PROCEDURE IF EXISTS greet_user;

DELIMITER $$

CREATE PROCEDURE greet_user(IN p_name VARCHAR(80))
BEGIN
    DECLARE v_name VARCHAR(80);

    SET v_name = COALESCE(NULLIF(TRIM(p_name), ''), 'friend');

    SELECT CONCAT('Hello, ', v_name, '!') AS message;
END$$

DELIMITER ;

CALL greet_user('MySQL');
CALL greet_user(NULL);
```

Read the example step by step:

- `DROP PROCEDURE ...;` runs while the delimiter is still `;`, since it is a simple SQL statement.
- `DELIMITER $$` tells the client to wait for `$$` before sending the current statement.
- `CREATE PROCEDURE ... BEGIN ... END` is a single procedure-creation statement. The inner `;` characters terminate `DECLARE`, `SET`, and `SELECT` per compound-statement syntax.
- `END$$` ends the definition for the client. The client sends the entire `CREATE PROCEDURE` statement to the server.
- `DELIMITER ;` restores standard SQL input mode.
- `CALL` executes the newly created procedure.

`DELIMITER $$` and `DELIMITER ;` are not stored inside the procedure definition. They only control how the client splits input into statements. The server stores the SQL definition of the procedure, including its necessary internal separators.

## 4. Why Stored Programs Need a Custom Delimiter

Procedures, functions, and triggers can use compound statements with `BEGIN ... END`. Inside this block, multiple SQL statements are separated by `;`. Control-flow blocks can also contain multiple closing clauses such as `END IF;`, `END LOOP;`, or nested `BEGIN ... END` blocks.

Example of a procedure body with conditionals:

```sql
DELIMITER //

CREATE PROCEDURE classify_amount(IN p_amount DECIMAL(10, 2))
BEGIN
    IF p_amount IS NULL THEN
        SELECT 'No value' AS result;
    ELSEIF p_amount < 0 THEN
        SELECT 'Negative value' AS result;
    ELSEIF p_amount = 0 THEN
        SELECT 'Zero' AS result;
    ELSE
        SELECT 'Positive value' AS result;
    END IF;
END//

DELIMITER ;

CALL classify_amount(NULL);
CALL classify_amount(-10);
CALL classify_amount(25.50);
```

In this example, `END IF;` closes the `IF` construct, whereas `END//` closes the procedure definition on the client side. Do not replace the `;` of `END IF;` with `//`; the two markers serve different roles.

If you use loops or nested blocks, the same rule applies: keep the internal syntax of the stored program intact and use a separate delimiter so the client recognizes where the overall `CREATE` statement ends.

## 5. Creating Functions and Triggers

### 5.1. Stored Function

A function returns a value and can be used in SQL expressions when it satisfies MySQL's rules. The example below computes a price after a 10% discount:

```sql
DROP FUNCTION IF EXISTS discounted_amount;

DELIMITER $$

CREATE FUNCTION discounted_amount(p_amount DECIMAL(10, 2))
RETURNS DECIMAL(10, 2)
DETERMINISTIC
NO SQL
BEGIN
    IF p_amount IS NULL OR p_amount < 0 THEN
        RETURN 0;
    END IF;

    RETURN p_amount * 0.90;
END$$

DELIMITER ;

SELECT discounted_amount(100.00) AS amount_after_discount;
```

In a function, `RETURN` passes the result back to the calling expression. Statements and control structures inside the body still use `;`. The `END$$` portion is solely the client-side boundary ending the `CREATE FUNCTION` statement.

### 5.2. Trigger

A trigger typically contains one or more statements to execute when an `INSERT`, `UPDATE`, or `DELETE` occurs on a table. The following example records a log entry after each row insertion:

```sql
CREATE TABLE IF NOT EXISTS audit_demo (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    note VARCHAR(100) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS audit_demo_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    audit_demo_id BIGINT NOT NULL,
    action_name VARCHAR(10) NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB;

DROP TRIGGER IF EXISTS trg_audit_demo_after_insert;

DELIMITER $$

CREATE TRIGGER trg_audit_demo_after_insert
AFTER INSERT ON audit_demo
FOR EACH ROW
BEGIN
    INSERT INTO audit_demo_log (audit_demo_id, action_name)
    VALUES (NEW.id, 'INSERT');
END$$

DELIMITER ;

INSERT INTO audit_demo (note) VALUES ('Test record');
SELECT * FROM audit_demo_log;
```

The initial `CREATE TABLE` and `DROP TRIGGER` statements still use the default delimiter. When beginning the trigger definition, the client switches to `$$`; the `INSERT` inside the trigger body ends with `;`, while `END$$` terminates the entire trigger definition.

## 6. Running an SQL File Containing Stored Programs

You can save routine creation statements in a file, such as `routines.sql`. The file must include both the `DELIMITER` directive and the delimiter restoration:

```sql
DROP PROCEDURE IF EXISTS greet_user;

DELIMITER $$

CREATE PROCEDURE greet_user(IN p_name VARCHAR(80))
BEGIN
    DECLARE v_name VARCHAR(80);
    SET v_name = COALESCE(NULLIF(TRIM(p_name), ''), 'friend');
    SELECT CONCAT('Hello, ', v_name, '!') AS message;
END$$

DELIMITER ;
```

There are two ways to run it with the classic MySQL command-line client.

**Method 1: redirect the file into the client from the shell.** Example:

```bash
mysql --user=labuser --password --database=labdb < routines.sql
```

The client prompts for the password. Even in batch mode, `mysql` reads and processes `DELIMITER` directives in the input file.

**Method 2: use the `source` command inside a client session.** After connecting to the target database, run:

```text
source ./routines.sql
```

The `source` command is a MySQL client command that reads and executes a file. Relative paths resolve from the client process's working directory.

After running, verify the stored definition:

```sql
SHOW CREATE PROCEDURE greet_user\G
```

`SHOW CREATE PROCEDURE` displays the definition stored by the server. Its output does not contain `DELIMITER` directives because they are not part of the server-stored SQL definition.

## 7. When Using a GUI, Migration Tool, or Application Driver

`DELIMITER` is a directive specific to the classic MySQL command-line client. Therefore, never send a raw `DELIMITER $$` line to the server as an SQL statement. If sent directly, the server returns a syntax error because it does not recognize client control directives.

When creating a stored program from a Java, Python, or other application, you normally send the entire `CREATE PROCEDURE` or `CREATE TRIGGER` statement as a single execution unit through the driver. The SQL string may contain `;` inside the routine body, without `DELIMITER` lines and without a trailing `$$`.

Illustrative example in Java JDBC:

```java
String sql = """
    CREATE PROCEDURE greet_user(IN p_name VARCHAR(80))
    BEGIN
        DECLARE v_name VARCHAR(80);
        SET v_name = COALESCE(NULLIF(TRIM(p_name), ''), 'friend');
        SELECT CONCAT('Hello, ', v_name, '!') AS message;
    END
    """;

try (Statement statement = connection.createStatement()) {
    statement.execute(sql);
}
```

This is a single `execute` call carrying the entire `CREATE PROCEDURE` statement. The driver transmits the statement over the connection protocol; `DELIMITER` is unnecessary. When invoking the procedure, you can use `CallableStatement` or a `CALL` SQL statement depending on application needs.

Some GUI editors, migration frameworks, or script runners have their own file parsers. Some recognize `DELIMITER` syntax, while others require configuring the delimiter separately or submitting each statement via API. Check the rules of the tool you are using. If a tool naively splits files on every `;`, it may split a `CREATE` statement in half even when both server and procedure are completely valid.

## 8. Common Errors and How to Fix Them

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Syntax error right at `DECLARE`, `SET`, or `IF` when creating a procedure | Client is still using `;` and sent the first part of the routine body before reaching `END` | Change the delimiter before `CREATE`, then re-run the entire definition from the start |
| Lines after `BEGIN` execute as standalone statements | Internal `;` terminated client input prematurely | Choose a different delimiter such as `$$` or `//` for the entire `CREATE` statement |
| Server reports a syntax error on `DELIMITER` | Client directive was sent to the server via a driver or tool that does not support it | Remove `DELIMITER` lines; configure the script runner or send the full `CREATE` in a single execution |
| Subsequent SQL statements do not execute as expected | Client is still holding the custom delimiter | Run `DELIMITER ;` to restore the default delimiter |
| Client keeps waiting for more input after a typo | Current statement has not encountered its closing delimiter | Use `\c` in the MySQL client to clear pending input, then reset the delimiter |
| Script runs on one tool/machine but fails on another | Each tool has its own script parser and delimiter rules | Check tool documentation; separate client directives from SQL sent via drivers if needed |

A very common mistake is forgetting to restore the delimiter. For instance, after running `DELIMITER $$`, you type `SELECT VERSION();` and it sits waiting because the client is still looking for `$$`. Simply enter:

```sql
DELIMITER ;
```

If the client is currently holding an incomplete statement, clear the pending input with `\c` first and then reset the delimiter.

## 9. Recommended Workflow

When writing a script that creates stored programs, follow this sequence:

1. Run preparatory statements such as `DROP ... IF EXISTS` or dependent table creation while the delimiter is still `;`.
2. Switch to a delimiter unlikely to appear in the body, such as `$$`.
3. Write the full `CREATE` statement with `BEGIN ... END`; keep `;` for every inner statement and control structure.
4. End the definition with `END$$` (or `END//` if you chose `//`).
5. Switch the delimiter back to `;` immediately after the definition.
6. Call the procedure, test the function, or perform the action that fires the trigger.
7. Use `SHOW CREATE PROCEDURE`, `SHOW CREATE FUNCTION`, or `SHOW CREATE TRIGGER` to verify the stored definition.

Formatting stored program creation as a clear block in SQL files makes it obvious to readers when the delimiter changes. If a file creates multiple routines consecutively, you may keep the custom delimiter across the group, as long as you restore `;` right after the group.

## 10. Practice Exercises

1. Open the MySQL command-line client and run two simple statements using the default `;` delimiter.
2. Create the `greet_user` procedure from Section 3. Call it with a normal string, an empty string, and `NULL`.
3. Create the `classify_amount` procedure. Explain the distinct roles of `END IF;` and `END//`.
4. Create the `discounted_amount` function, invoke it in a `SELECT` query, and inspect it with `SHOW CREATE FUNCTION`.
5. Create the `audit_demo` and `audit_demo_log` tables, install the trigger, and insert a record. Confirm the trigger creates a log row.
6. Save a routine into `routines.sql` and run it using `source`. Then re-run the file from the shell with `mysql` in batch mode.
7. Intentionally omit the delimiter change step, observe the error or how the client splits the statement, then fix the script and re-run it.
8. Make a `Statement.execute()` call in JDBC with the full `CREATE PROCEDURE` statement. Explain why `DELIMITER` is omitted from the SQL string sent through the driver.

## 11. Completion Criteria

You have completed this lesson when you can explain that `DELIMITER` controls how the MySQL client splits input while the server parses stored program syntax; create multi-statement procedures, functions, and triggers; run SQL files in interactive or batch mode; restore the delimiter to `;`; and handle tools or script runners that do not support the `DELIMITER` directive.

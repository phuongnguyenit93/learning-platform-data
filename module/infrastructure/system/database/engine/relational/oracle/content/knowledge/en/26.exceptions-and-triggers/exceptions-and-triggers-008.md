# Mutating Tables and Choosing Compound Triggers

In Oracle Database, **ORA-04091: table is mutating, trigger/function may not see it** commonly occurs when a row-level trigger reads or modifies the same table currently being modified by a DML statement. This is Oracle's consistency protection mechanism: while a statement updating multiple rows is executing, the intermediate state of the table is not yet the final state of the statement.

When business logic needs per-row data via `:OLD`/`:NEW` while also querying the entire table after all rows have been processed, a **compound trigger** is an appropriate choice. It allows collecting data during row-level processing and using that collected data in the `AFTER STATEMENT` section, where the DML statement has finished modifying rows.

## 1. What Is a Mutating Table?

A table is considered *mutating* in a trigger context when a DML statement is actively modifying that table and Oracle has not finished processing all rows. For a row-level trigger, Oracle disallows querying or modifying the mutating table itself in ways that would make results depend on row-processing order.

For example, suppose the `EMPLOYEES` table stores employees, departments, and salaries. We want to check whether an employee's new salary exceeds twice the department's average salary. The following straightforward approach is problematic:

~~~sql
CREATE OR REPLACE TRIGGER trg_check_emp_salary
BEFORE INSERT OR UPDATE OF salary ON employees
FOR EACH ROW
DECLARE
  l_avg_salary NUMBER;
BEGIN
  SELECT AVG(salary)
    INTO l_avg_salary
    FROM employees
   WHERE department_id = :NEW.department_id;

  IF :NEW.salary > 2 * l_avg_salary THEN
    RAISE_APPLICATION_ERROR(
      -20001,
      'Salary exceeds twice the department average'
    );
  END IF;
END;
/
~~~

This trigger runs once per row. While the trigger is executing, the outer `INSERT` or `UPDATE` statement is still modifying `EMPLOYEES`. Therefore, the `SELECT` inside the trigger reading `EMPLOYEES` can raise `ORA-04091`. Moving the `SELECT` into a procedure or function called by the trigger does not solve the problem: Oracle still treats it as reading a mutating table within the same row-level trigger context.

The issue is not limited to `SELECT`. A row-level trigger also should not `UPDATE` or `DELETE` the table that fired it. If you need to process data in that table itself, consider shifting processing to the statement-level timing point or redesigning the business logic.

### Why Does Oracle Restrict Querying a Mutating Table?

A statement like `UPDATE` can affect hundreds or thousands of records. Oracle does not guarantee a row-processing order that business logic can rely on. If the trigger for the first row reads the table while only part of the rows have been updated, the result can differ from the result after the full statement completes.

For example, when updating multiple employees' salaries concurrently in one statement, a trigger computing an average mid-statement sees an incomplete set of values. If business decisions depend on that intermediate set, outcomes can vary with how Oracle executes the statement. The mutating-table restriction prevents this kind of order dependency.

## 2. Choosing the Right Approach

Not every `ORA-04091` requires a compound trigger. First, identify what data the trigger needs and at which timing point it is needed.

| Requirement | Commonly Appropriate Approach |
|---|---|
| Rule can be expressed as a data constraint | Prefer `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, or `CHECK` where suitable |
| Only needs table state before the statement starts | Can use a `BEFORE STATEMENT` trigger |
| Only needs state after the entire statement finishes, without per-row `:OLD`/`:NEW` | Can use an `AFTER STATEMENT` trigger |
| Needs to collect per-row `:OLD`/`:NEW` and then query the table after DML finishes | Use a compound trigger |
| Legacy system cannot use compound triggers | Can use package state combining row-level and statement-level triggers, with careful state management |

A standard statement-level trigger has no `:OLD` and `:NEW` because it does not run per row. If business logic needs the old and new departments of each updated employee, a compound trigger can save those values in `AFTER EACH ROW` and process them in `AFTER STATEMENT`.

## 3. Structure of a Compound Trigger

A compound trigger is a DML trigger that can contain multiple timing sections within a single declaration. Available sections are:

| Timing Section | Execution Time | Common Tasks |
|---|---|---|
| `BEFORE STATEMENT` | Once before processing rows | Initialize state or check statement-level preconditions |
| `BEFORE EACH ROW` | Before each row | Validate or adjust `:NEW` values |
| `AFTER EACH ROW` | After each row | Collect `:OLD`/`:NEW` or record data for post-statement processing |
| `AFTER STATEMENT` | Once after all rows are processed | Query final state, aggregate, or perform batch processing |

You do not have to declare all four sections—declare only the sections you need. Variables and subprograms placed in the shared declarative section after `COMPOUND TRIGGER` are shared across sections within a single statement execution. This state is created when the statement starts and released when the trigger execution finishes.

General syntax skeleton:

~~~sql
CREATE OR REPLACE TRIGGER trigger_name
FOR INSERT OR UPDATE OR DELETE ON table_name
COMPOUND TRIGGER

  -- Shared variables, types, and subprogram declarations.

  BEFORE STATEMENT IS
  BEGIN
    -- Runs once before the DML statement.
  END BEFORE STATEMENT;

  AFTER EACH ROW IS
  BEGIN
    -- Runs after each row; can access :OLD and :NEW.
  END AFTER EACH ROW;

  AFTER STATEMENT IS
  BEGIN
    -- Runs once after the DML statement finishes processing rows.
  END AFTER STATEMENT;

END trigger_name;
/
~~~

In row-level sections, `:OLD` and `:NEW` are available depending on the DML event. For `INSERT`, `:NEW` holds the inserted row values; for `DELETE`, `:OLD` holds the deleted row values; for `UPDATE`, both are available. Statement-level sections have no per-row `:OLD`/`:NEW` data.

## 4. Example: Checking Department Total Salary After DML Completes

Suppose we have two tables:

- `DEPARTMENTS(department_id, salary_budget)`: stores each department's salary budget.
- `EMPLOYEES(employee_id, department_id, salary)`: stores employees, departments, and salaries.

Business rule: after every `INSERT`, `UPDATE`, or `DELETE` statement on `EMPLOYEES`, the total salary of each affected department must not exceed that department's `salary_budget`.

If we check total salary inside a row-level trigger via `SELECT SUM(salary) FROM EMPLOYEES`, the trigger may hit `ORA-04091`. We use a two-phase compound trigger instead:

1. In `AFTER EACH ROW`, record only the old and new `department_id` values of affected rows. Do not query `EMPLOYEES` here.
2. In `AFTER STATEMENT`, iterate over the recorded departments, query each department's current total salary, and compare it against the budget.

~~~sql
CREATE OR REPLACE TRIGGER trg_check_dept_salary_budget
FOR INSERT OR UPDATE OR DELETE ON employees
COMPOUND TRIGGER

  TYPE t_department_ids IS TABLE OF departments.department_id%TYPE
    INDEX BY PLS_INTEGER;

  g_department_ids   t_department_ids;
  g_department_count PLS_INTEGER := 0;

  PROCEDURE remember_department(
    p_department_id IN departments.department_id%TYPE
  ) IS
  BEGIN
    IF p_department_id IS NULL THEN
      RETURN;
    END IF;

    -- Store each department_id only once to avoid redundant queries.
    IF g_department_count > 0 THEN
      FOR i IN 1 .. g_department_count LOOP
        IF g_department_ids(i) = p_department_id THEN
          RETURN;
        END IF;
      END LOOP;
    END IF;

    g_department_count := g_department_count + 1;
    g_department_ids(g_department_count) := p_department_id;
  END remember_department;

  AFTER EACH ROW IS
  BEGIN
    IF INSERTING THEN
      remember_department(:NEW.department_id);

    ELSIF DELETING THEN
      remember_department(:OLD.department_id);

    ELSIF UPDATING('SALARY') OR UPDATING('DEPARTMENT_ID') THEN
      -- When an employee transfers departments, check both source and target.
      remember_department(:OLD.department_id);
      remember_department(:NEW.department_id);
    END IF;
  END AFTER EACH ROW;

  AFTER STATEMENT IS
    l_total_salary NUMBER;
    l_budget       departments.salary_budget%TYPE;
  BEGIN
    IF g_department_count > 0 THEN
      FOR i IN 1 .. g_department_count LOOP
        SELECT d.salary_budget
          INTO l_budget
          FROM departments d
         WHERE d.department_id = g_department_ids(i);

        SELECT NVL(SUM(e.salary), 0)
          INTO l_total_salary
          FROM employees e
         WHERE e.department_id = g_department_ids(i);

        IF l_total_salary > l_budget THEN
          RAISE_APPLICATION_ERROR(
            -20041,
            'Total salary exceeds budget for department '
              || TO_CHAR(g_department_ids(i))
          );
        END IF;
      END LOOP;
    END IF;
  END AFTER STATEMENT;

END trg_check_dept_salary_budget;
/
~~~

This example assumes `DEPARTMENTS.department_id` is the primary key, `EMPLOYEES.department_id` references that key, `salary_budget` is `NOT NULL`, and `salary` is stored in a consistent currency unit. If the system allows employees without a department, the code skips `NULL` `department_id` values.

### Execution Flow Analysis

**On INSERT:** `AFTER EACH ROW` reads `:NEW.department_id`. If a single `INSERT` adds multiple employees to the same department, `remember_department` stores that `department_id` only once.

**On DELETE:** `AFTER EACH ROW` reads `:OLD.department_id`. The old department should be recorded (e.g., its total salary decreased).

**On salary UPDATE:** the trigger records the row's department before and after the update. If the employee stays in the same department, `remember_department` deduplicates the value.

**On department UPDATE:** the trigger records both `:OLD.department_id` and `:NEW.department_id`. The old department's total salary may drop while the new department's rises; both must be checked.

**In AFTER STATEMENT:** all rows of the DML statement have been processed. Therefore, `SELECT SUM(salary) FROM EMPLOYEES` can read the post-statement state without encountering row-level trigger mutating-table restrictions. If total salary exceeds the budget, `RAISE_APPLICATION_ERROR` fails the DML statement, and its changes are rolled back under Oracle's transaction mechanism.

This example focuses on splitting work between `AFTER EACH ROW` and `AFTER STATEMENT`. For a budget rule that must hold strictly under concurrent sessions modifying data simultaneously, additional synchronization is needed. Two sessions could concurrently read a total salary excluding the other's uncommitted changes and both pass validation. A common solution locks the corresponding `DEPARTMENTS` rows before summing, locking multiple departments in a consistent order to reduce deadlock risk. Test locking designs under realistic application transaction concurrency.

## 5. How Compound Triggers Solve Mutating Table Errors

The deciding factor is **when the table is queried**:

- `AFTER EACH ROW` only collects required values from `:OLD` and `:NEW`. It does not query `EMPLOYEES`.
- `AFTER STATEMENT` queries `EMPLOYEES`. By then, the DML statement has finished processing all rows, so the table is no longer mutating for that statement.

Compound triggers also keep intermediate data scoped to a single statement execution. You do not need package globals to pass data from a separate row-level trigger to a separate statement-level trigger.

## 6. When Should You Choose a Compound Trigger?

Compound triggers are especially useful when both requirements apply:

1. You need per-row data via `:OLD` or `:NEW`.
2. You need an aggregate operation or a query back against the table after the entire statement completes.

Common scenarios include:

- Collecting keys of modified rows, then validating multi-row rules.
- Gathering changed data to write audit logs or update summary tables in bulk.
- Validating the final state of row groups after a multi-row DML statement.
- Avoiding querying a mutating table inside a row-level trigger.

If you only need to run once after a statement without per-row data, a simple `AFTER STATEMENT` trigger suffices. If you only need to validate values of the row currently changing, a row-level trigger fits as long as it does not query or modify the mutating table. If a rule can be expressed as a constraint, prefer the constraint because Oracle enforces integrity directly at the data layer.

## 7. Package State: The Legacy Approach and What to Watch Out For

Before compound triggers were supported, a common workaround used a package holding shared collections:

1. A row-level trigger writes keys or `:OLD`/`:NEW` values into a package collection.
2. A statement-level trigger reads the collection, queries the table after DML finishes, and processes it.
3. The package must clear the collection after every statement and handle both success and exception paths cleanly.

This works in legacy systems, but package state persists across the session. If you forget to reset state on error, leftover state from a previous statement can corrupt subsequent statements. Recursive DML, multiple triggers sharing the package, or exception paths further complicate state management. Compound triggers bundle declaration, collection, and processing into one trigger and bound state lifetime to the DML statement.

Compound triggers have been supported since Oracle Database 11g Release 1. For older releases, consider the package-state approach or an alternative design.

## 8. Error-Prone Workarounds

**Wrapping SELECT in a function:** if a function is called from a row-level trigger and queries the mutating table, `ORA-04091` can still occur. Moving the `SELECT` into another call frame does not change its execution timing.

**Using an autonomous transaction to dodge the error:** an autonomous transaction does not make the main table's state safe to validate. It runs in an independent transaction, sees a different snapshot from the calling transaction, and can commit side effects detached from the main statement. This is not a valid fix for mutating tables.

**Catching and ignoring all exceptions:** `WHEN OTHERS THEN NULL` merely hides failures and prevents business rules from being enforced. Handle the root cause properly or raise a clear error so invalid DML fails.

**Re-querying on every row:** if `AFTER EACH ROW` only needs to record a key, store that key and process once in `AFTER STATEMENT`. Deduplicating keys avoids querying the same group repeatedly during large statements.

**Forgetting rows in the old department:** when an `UPDATE` moves a row from group A to group B, checking only group B is insufficient. Aggregate rules can be affected in both the old and new groups.

## 9. How to Test a Compound Trigger

When deploying, test cases matching how the application actually uses the table:

1. `INSERT` one row and `INSERT` multiple rows into the same department.
2. `UPDATE` one employee's salary and `UPDATE` multiple rows in a single statement.
3. Transfer an employee from one department to another; confirm both departments are checked.
4. `DELETE` one row and `DELETE` multiple rows.
5. DML that does not change relevant columns; confirm the trigger performs no unexpected extra work.
6. A statement violating the rule; confirm the error is returned and the entire statement rolls back.
7. `NULL` cases, departments with zero employees, and boundary data per real constraints.
8. Two sessions modifying data in the same department concurrently; confirm locking or synchronization protects the business rule.

When encountering `ORA-04091`, read the error message to identify the mutating table and trigger involved. Then inspect all procedures, functions, and dynamic SQL called indirectly from row-level triggers. If you need final post-statement data across multiple rows, move the query to `AFTER STATEMENT` and keep only the minimal data collection inside `AFTER EACH ROW`.

## 10. Selection Conclusion

Use a compound trigger when business logic requires combining per-row processing with post-statement processing. The standard implementation pattern is: declare collections in the shared section, collect keys or values in `AFTER EACH ROW`, deduplicate elements, and query or process data in `AFTER STATEMENT`. This directly addresses the common cause of `ORA-04091` and scopes intermediate state to a single DML statement.

Compound triggers do not automatically solve every data integrity problem. For rules spanning multiple rows and concurrent sessions, you must still consider locking, transaction isolation levels, deadlocks, and how the application executes DML. Choosing solutions based on when data is needed and the scope of the rule keeps triggers clear, maintainable, and safe.

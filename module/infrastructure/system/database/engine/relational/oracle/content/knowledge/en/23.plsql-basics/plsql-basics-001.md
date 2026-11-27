# The Role of PL/SQL and Its Boundaries with SQL and Application Code

PL/SQL is a procedural language integrated by Oracle into the database. It combines SQL with variables, conditionals, loops, exceptions, procedures, functions, packages, and triggers. PL/SQL helps place processing logic close to the data, reduces the number of commands the application sends over the network, and creates reusable database APIs.

PL/SQL does not replace SQL, nor does it replace all application code. SQL describes the data to be read or modified declaratively; PL/SQL orchestrates multi-step processing on the database side; application code manages the UI, requests, authentication, service integration, and system-level workflows.

Key boundaries:

- **SQL:** querying, filtering, joining, aggregating, and modifying data in sets.
- **PL/SQL:** encapsulating logic close to the data, coordinating multiple SQL statements, controlling execution flow, and handling errors inside Oracle.
- **Application code:** receiving requests, authenticating users, orchestrating services, managing sessions, UI, external integrations, and use-case-level transactions.

## 1. What is PL/SQL?

PL/SQL (Procedural Language extensions to SQL) is Oracle's procedural programming language. A PL/SQL block can declare variables, execute SQL, branch, loop, handle exceptions, and call subprograms.

~~~sql
DECLARE
    v_employee_id NUMBER := 101;
    v_salary      NUMBER;
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE employee_id = v_employee_id;

    DBMS_OUTPUT.PUT_LINE('Salary = ' || v_salary);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee not found');
END;
/
~~~

A block has an optional declarative section, a mandatory executable section, and an optional exception-handling section. The forward slash on its own line is a symbol used by some clients such as SQL*Plus/SQLcl to submit the block to the database; it is not a statement inside the PL/SQL block.

PL/SQL appears in many forms: anonymous blocks, stored procedures, functions, packages, triggers, and programs invoked by schedulers or administrative tools.

## 2. Distinguishing SQL, PL/SQL, and Application Code

| Component | Nature | Suitable Work |
|---|---|---|
| SQL | Declarative query and data manipulation language | SELECT, INSERT, UPDATE, DELETE, MERGE, join, aggregate |
| PL/SQL | Procedural language running inside Oracle Database | Orchestrating multiple SQL statements, data validation, encapsulating database-side processing |
| Application code | Languages and runtimes outside the database | APIs, UI, authentication, service integration, workflows, use-case transactions |

### 2.1. SQL describes the desired result

Example of calculating total revenue by customer:

~~~sql
SELECT customer_id,
       SUM(amount) AS total_amount
FROM orders
WHERE order_date >= DATE '2026-01-01'
GROUP BY customer_id;
~~~

SQL describes the desired result set. The optimizer determines the execution plan. The author does not need to manually loop over each customer and add up rows one by one when a single aggregate query expresses the requirement directly.

### 2.2. PL/SQL orchestrates processing steps

~~~sql
CREATE OR REPLACE PROCEDURE mark_order_ready (
    p_order_id IN orders.order_id%TYPE
) AS
    v_status orders.status%TYPE;
BEGIN
    SELECT status
    INTO v_status
    FROM orders
    WHERE order_id = p_order_id
    FOR UPDATE;

    IF v_status = 'PAID' THEN
        UPDATE orders
        SET status = 'READY'
        WHERE order_id = p_order_id;
    ELSE
        RAISE_APPLICATION_ERROR(-20001, 'Order is not paid');
    END IF;
END;
/
~~~

The procedure uses SQL to read, lock, and update data; PL/SQL controls the execution flow. The example does not commit on its own, leaving transaction management to the caller.

### 2.3. Application code orchestrates requests

~~~text
User / API caller
            |
            v
       Application
  - Authentication / Authorization
  - Validate request
  - Orchestrate use case
            |
            v
       Repository / DAO
  - Bind parameters
  - Call SQL or PL/SQL
  - Manage connection
            |
            v
      Oracle Database
  - SQL engine
  - PL/SQL engine
  - Tables / indexes / constraints
            |
            v
       Application
  - Mapping response
  - Logging / tracing
  - Return API response
~~~

The database should not have to render UI, manage login sessions, or directly send emails for each operation. Those tasks belong to the application layer or dedicated services.

## 3. SQL is the Center of Data Manipulation

SQL is designed to process data in sets (set-based). A single statement can process thousands or millions of rows without the application sending each operation individually.

### 3.1. Prefer set-based SQL whenever possible

Example of row-by-row processing using a cursor:

~~~sql
BEGIN
    FOR r IN (
        SELECT order_id
        FROM orders
        WHERE status = 'NEW'
    ) LOOP
        UPDATE orders
        SET status = 'REVIEW'
        WHERE order_id = r.order_id;
    END LOOP;
END;
/
~~~

If the goal is simply to change the status for every row matching a condition, a single SQL statement is simpler:

~~~sql
UPDATE orders
SET status = 'REVIEW'
WHERE status = 'NEW';
~~~

The second UPDATE statement expresses the goal directly as a set operation, typically avoiding unnecessary PL/SQL loops.

### 3.2. Let SQL handle joins and aggregates

~~~sql
SELECT o.order_id,
       c.customer_name,
       SUM(oi.quantity * oi.unit_price) AS order_total
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
JOIN order_items oi
  ON oi.order_id = o.order_id
GROUP BY o.order_id, c.customer_name;
~~~

The SQL engine is designed to optimize joins, filters, and aggregates. Writing manual loops to combine data can generate many queries and logic that is hard to optimize.

### 3.3. MERGE for set-based upserts

~~~sql
MERGE INTO customer_summary t
USING (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.order_count = s.order_count,
        t.total_amount = s.total_amount
WHEN NOT MATCHED THEN
    INSERT (customer_id, order_count, total_amount)
    VALUES (s.customer_id, s.order_count, s.total_amount);
~~~

MERGE expresses updating existing rows and inserting non-existing rows from a source set. PL/SQL can wrap the MERGE statement if business rules require multiple steps or additional error handling.

## 4. PL/SQL Adds Procedural Capabilities to SQL

SQL focuses on describing data operations; PL/SQL adds control structures and program organization.

### 4.1. Variables and data types

PL/SQL supports numeric, character, date/time, boolean, record, collection, cursor, and user-defined types.

~~~sql
DECLARE
    v_order_id orders.order_id%TYPE;
    v_status   orders.status%TYPE;
BEGIN
    v_order_id := 1001;
    v_status := 'NEW';
END;
/
~~~

`%TYPE` declares a variable with the same type as a column. `%ROWTYPE` creates a record with a structure matching a row of a table or cursor. These attributes help reduce the risk of declaring variables whose data types drift from the schema.

### 4.2. Branching and loops

~~~sql
DECLARE
    v_amount NUMBER := 1500;
BEGIN
    IF v_amount >= 1000 THEN
        DBMS_OUTPUT.PUT_LINE('Large order');
    ELSIF v_amount > 0 THEN
        DBMS_OUTPUT.PUT_LINE('Small order');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Invalid amount');
    END IF;
END;
/
~~~

PL/SQL supports IF, CASE, LOOP, WHILE, FOR, and cursor FOR LOOP. They are useful when conditional logic or sequential processing is genuinely needed. Loops should not be used to replace a simple set-based SQL statement.

### 4.3. Procedures and functions

A procedure represents an action; a function returns a value.

~~~sql
CREATE OR REPLACE FUNCTION calculate_discount (
    p_amount IN NUMBER
) RETURN NUMBER
IS
BEGIN
    IF p_amount >= 10000000 THEN
        RETURN p_amount * 0.10;
    ELSIF p_amount >= 5000000 THEN
        RETURN p_amount * 0.05;
    END IF;

    RETURN 0;
END;
/
~~~

The function above only performs a calculation. If the discount rule needs to be shared by multiple programs inside the database, the function can be placed in a package. If the policy changes frequently with business strategy or depends on external services, consider managing it in the application layer or data configuration rather than hard-coding it into the function.

### 4.4. Packages

A package groups related declarations and subprograms:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE mark_paid(
        p_order_id IN orders.order_id%TYPE
    );

    FUNCTION get_order_total(
        p_order_id IN orders.order_id%TYPE
    ) RETURN NUMBER;
END order_api;
/
~~~

The package body contains the implementation:

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS

    PROCEDURE mark_paid(
        p_order_id IN orders.order_id%TYPE
    ) IS
    BEGIN
        UPDATE orders
        SET status = 'PAID'
        WHERE order_id = p_order_id
          AND status = 'PENDING';

        IF SQL%ROWCOUNT <> 1 THEN
            RAISE_APPLICATION_ERROR(-20002, 'Order cannot be marked paid');
        END IF;
    END mark_paid;

    FUNCTION get_order_total(
        p_order_id IN orders.order_id%TYPE
    ) RETURN NUMBER IS
        v_total NUMBER;
    BEGIN
        SELECT NVL(SUM(quantity * unit_price), 0)
        INTO v_total
        FROM order_items
        WHERE order_id = p_order_id;

        RETURN v_total;
    END get_order_total;

END order_api;
/
~~~

Packages create clearly named database APIs, allowing multiple clients to invoke shared logic. However, packages also introduce dependencies on the schema and database version; versioning, deployment, and testing processes are required.

## 5. How the SQL Engine and PL/SQL Engine Collaborate

Oracle has separate execution components for SQL and PL/SQL. When a PL/SQL block executes a SQL statement, the PL/SQL side controls the flow and passes the SQL statement to the SQL engine for processing. The results are returned to PL/SQL to continue execution.

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 1;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = 2;
END;
/
~~~

PL/SQL orchestrates the two statements; each DML statement is executed by the SQL engine.

### 5.1. Context switches

Switching execution control between the PL/SQL engine and the SQL engine is commonly called a context switch. Each switch has a certain cost. If code executes a SQL statement for each row in a large loop, the number of switches can increase significantly.

~~~sql
BEGIN
    FOR r IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 10
    ) LOOP
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/
~~~

With 50,000 employees, this logic can cause tens of thousands of SQL calls from PL/SQL. If you only need to raise salaries for the entire department, a single UPDATE statement is more appropriate:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;
~~~

### 5.2. A context switch is not a network round-trip

It is important to distinguish:

- **PL/SQL ↔ SQL context switch:** switching execution between engines inside Oracle Database.
- **Application ↔ Database round-trip:** the application sending a request over the network to the database and receiving the result.

A stored procedure can reduce network round-trips by bundling multiple operations into a single database call, yet inside the procedure it can still generate many context switches if it loops over individual SQL statements.

Conversely, a large SQL statement sent from the application requires only one round-trip, though the SQL engine may still execute a complex execution plan.

### 5.3. Bulk processing

When all logic cannot be expressed in a single SQL statement, PL/SQL supports bulk SQL:

- **BULK COLLECT:** fetches multiple rows into a collection in a single fetch.
- **FORALL:** sends multiple DML operations based on a collection, reducing the number of switches between the PL/SQL and SQL engines.

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_employee_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM employees
    WHERE department_id = 10;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = l_ids(i);
END;
/
~~~

If the operation can be written as a single conditional UPDATE statement, the set-based UPDATE is still usually simpler and avoids loading the ID list into PL/SQL memory.

### 5.4. LIMIT to control collection size

For large datasets, a full BULK COLLECT can consume a lot of PGA. You can fetch in batches:

~~~sql
DECLARE
    CURSOR c_emp IS
        SELECT employee_id
        FROM employees
        WHERE department_id = 10;

    TYPE t_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_ids;
BEGIN
    OPEN c_emp;

    LOOP
        FETCH c_emp BULK COLLECT INTO l_ids LIMIT 500;
        EXIT WHEN l_ids.COUNT = 0;

        FORALL i IN 1 .. l_ids.COUNT
            UPDATE employees
            SET salary = salary * 1.05
            WHERE employee_id = l_ids(i);
    END LOOP;

    CLOSE c_emp;
END;
/
~~~

Batch size needs to be measured. Too small a batch increases the number of fetch/DML batches; too large a batch increases memory usage and can prolong transactions.

## 6. Put Logic in PL/SQL or in the Application?

There is no rule that all logic must live in the database or all logic must live in the application. The decision depends on data, transactions, reusability, security, operations, and deployment requirements.

### 6.1. Logic suited for SQL

- Filtering, joining, aggregating, and sorting data.
- Modifying multiple rows based on conditions.
- Set-based upserts and data synchronization.
- Checking constraints and data relationships.
- Calculations based on data within the same database.

~~~sql
UPDATE inventory
SET reserved_qty = reserved_qty + :quantity
WHERE product_id = :product_id
  AND available_qty - reserved_qty >= :quantity;
~~~

The check condition and the update are executed in the same statement, avoiding the pattern of reading the quantity in the application and updating later without a protective condition.

### 6.2. Logic suited for PL/SQL

- Processes with multiple SQL steps that need to run close to the data.
- Checking and updating data within the same database session/transaction.
- Database APIs shared across multiple applications.
- Batch processing or data requiring bulk processing.
- Schema administration logic or scheduled database jobs.
- Rules that must enforce database invariants and should not be implemented differently by each client.

~~~sql
CREATE OR REPLACE PROCEDURE approve_order (
    p_order_id IN orders.order_id%TYPE
) AS
    v_status orders.status%TYPE;
BEGIN
    SELECT status
    INTO v_status
    FROM orders
    WHERE order_id = p_order_id
    FOR UPDATE;

    IF v_status <> 'PENDING' THEN
        RAISE_APPLICATION_ERROR(-20010, 'Only pending orders can be approved');
    END IF;

    UPDATE orders
    SET status = 'APPROVED'
    WHERE order_id = p_order_id;
END;
/
~~~

### 6.3. Logic suited for application code

- HTTP/API protocols and request/response mapping.
- Authentication and authorization by user/session/token.
- UI, localization, and display formatting.
- Sending email, SMS, or push notifications via dedicated services.
- Calling REST/gRPC endpoints or message brokers.
- Orchestrating multiple databases or microservices.
- Workflows requiring human approval or long-running interactions.
- Configuration that changes frequently by tenant or feature flag.
- Logic that must run across multiple database types or environments.

The application can call a procedure to update data, then emit an event via an outbox/worker. The database does not need to call an email provider directly inside the order-update transaction.

### 6.4. Decision matrix

| Criterion | SQL | PL/SQL | Application code |
|---|---|---|---|
| Set-based data processing | Very suitable | Orchestrates SQL/bulk | Should avoid fetching row-by-row unless necessary |
| Multiple steps close to data | Limited control flow | Suitable | Can orchestrate via APIs |
| UI and HTTP | Not suitable | Not suitable | Suitable |
| External service integration | Not its primary role | Limited and creates coupling | Suitable |
| Logic shared across clients | Queries/views can be shared | Procedures/packages can be shared | APIs/services can be shared |
| Multi-SQL transactions | Single SQL statement has its own atomicity | Can encapsulate database steps | Can own transactions via connection/transaction manager |
| Database portability | SQL dialects still differ | Tightly coupled to Oracle | Can be abstracted via repositories, depending on design |
| Deployment | SQL migrations/schema | Database object deployment | Application release |

## 7. Keep Transaction Boundaries at the Right Layer

A key decision is determining who owns the transaction.

Two common patterns:

1. **Application-owned transaction:** the application opens a connection, disables auto-commit, calls multiple SQL statements/procedures, and then commits or rolls back.
2. **Database API-owned transaction:** the procedure is designed as a complete business unit and has its own transaction contract.

Both can be reasonable. Problems arise when both layers think they own the transaction, or when a procedure commits without the caller knowing.

### 7.1. Procedures usually should not COMMIT arbitrarily

A poor example for a shared procedure:

~~~sql
CREATE OR REPLACE PROCEDURE update_customer_status (
    p_customer_id IN customers.customer_id%TYPE
) AS
BEGIN
    UPDATE customers
    SET status = 'ACTIVE'
    WHERE customer_id = p_customer_id;

    COMMIT;
END;
/
~~~

If the application wants to perform additional audit operations or update related tables in the same transaction, a COMMIT inside the procedure will commit all other uncommitted changes in the same session. The caller can no longer roll them back.

### 7.2. Procedures that let the caller manage the transaction

~~~sql
CREATE OR REPLACE PROCEDURE update_customer_status (
    p_customer_id IN customers.customer_id%TYPE
) AS
BEGIN
    UPDATE customers
    SET status = 'ACTIVE'
    WHERE customer_id = p_customer_id;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20020, 'Customer not found or status not updated');
    END IF;
END;
/
~~~

The caller decides whether to commit or roll back after all business steps complete.

### 7.3. Application managing transactions via JDBC

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        orderRepository.insert(connection, order);
        orderRepository.insertItems(connection, items);
        inventoryRepository.reserve(connection, items);
        auditRepository.insert(connection, order);

        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
~~~

Repositories must use the same connection passed into them. If each repository opens a new connection, the SQL statements may belong to independent transactions.

### 7.4. When should a procedure own the transaction?

A procedure can own the transaction if its contract is clearly designed: it performs an independent task, commits or rolls back on its own, and callers do not expect to compose it into a larger transaction. This behavior must be documented, and calling that procedure from flows that require a shared transaction should be avoided.

An autonomous transaction is an independent transaction in Oracle with different semantics from the main transaction. Do not use this mechanism in place of a business transaction that requires atomicity.

## 8. Exception Handling: Dividing Error Responsibilities

PL/SQL has an EXCEPTION section to handle errors raised within a block. The application also has its own exception mechanisms. You must decide which errors are handled in the database, which are propagated to the caller, and which are mapped to responses.

### 8.1. Handling meaningful errors in the database

~~~sql
CREATE OR REPLACE PROCEDURE reserve_product (
    p_product_id IN inventory.product_id%TYPE,
    p_quantity   IN NUMBER
) AS
BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE_APPLICATION_ERROR(-20030, 'Quantity must be positive');
    END IF;

    UPDATE inventory
    SET reserved_qty = reserved_qty + p_quantity
    WHERE product_id = p_product_id
      AND available_qty - reserved_qty >= p_quantity;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20031, 'Product not found or insufficient inventory');
    END IF;
END;
/
~~~

The procedure uses a single conditional UPDATE to avoid splitting the quantity check and the update into two steps that could race.

### 8.2. Do not swallow exceptions

Avoid writing:

~~~sql
BEGIN
    UPDATE orders
    SET status = 'APPROVED'
    WHERE order_id = 1001;
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END;
/
~~~

This hides all errors. The caller may assume the procedure succeeded when the data was never updated.

If you need to log and then propagate the error:

~~~sql
BEGIN
    UPDATE orders
    SET status = 'APPROVED'
    WHERE order_id = 1001;
EXCEPTION
    WHEN OTHERS THEN
        -- Record error details through the designed logging mechanism.
        RAISE;
END;
/
~~~

`RAISE` re-raises the current exception. When logging in an independent transaction, clearly understand autonomous transactions and the consequence that the log entry remains even if the business transaction rolls back.

### 8.3. Mapping errors in the application layer

The application can receive Oracle error codes/SQLState and map them to appropriate business errors or responses. The database should not expose internal stack traces, sensitive SQL statements, or schema details to public APIs.

~~~java
try {
    orderService.approve(orderId);
} catch (SQLException ex) {
    if (isKnownBusinessError(ex)) {
        throw new OrderConflictException("Order cannot be approved", ex);
    }
    throw new DataAccessException("Database operation failed", ex);
}
~~~

Business error codes must be agreed upon between PL/SQL packages and the application; do not classify every database error under the same HTTP status.

## 9. Security: Database Privileges and Application Permissions

Placing logic in PL/SQL can create a database API with explicit privileges. Oracle supports two key privilege models for stored program units:

- **AUTHID DEFINER:** the program executes under the owner/definer's privileges within Oracle's privilege rules.
- **AUTHID CURRENT_USER:** the program executes under the invoker/current user's privileges within invoker-rights semantics.

### 9.1. Definer rights

~~~sql
CREATE OR REPLACE PROCEDURE app_api.read_customer (
    p_customer_id IN NUMBER
)
AUTHID DEFINER
AS
    v_name customers.customer_name%TYPE;
BEGIN
    SELECT customer_name
    INTO v_name
    FROM customers
    WHERE customer_id = p_customer_id;

    DBMS_OUTPUT.PUT_LINE(v_name);
END;
/
~~~

With definer rights, the caller can be granted EXECUTE privilege on the procedure without needing direct read privileges on every underlying table inside the procedure, depending on how privileges and object references are granted.

This model is useful when exposing a restricted database API, but dynamic SQL, object resolution, and owner privileges must be tightly controlled.

### 9.2. Invoker rights

~~~sql
CREATE OR REPLACE PROCEDURE shared_api.process_data
AUTHID CURRENT_USER
AS
BEGIN
    NULL;
END;
/
~~~

Invoker rights can suit utilities used across multiple schemas that need to behave according to the caller's privileges. You need to understand name resolution, role privileges, and runtime privileges under Oracle PL/SQL rules.

### 9.3. Dynamic SQL and injection

Never concatenate user data directly into a SQL string:

~~~sql
-- Unsafe:
l_sql := 'SELECT * FROM customers WHERE customer_name = '''
         || p_name || '''';
~~~

Use bind variables:

~~~sql
l_sql := 'SELECT customer_id FROM customers WHERE customer_name = :name';

EXECUTE IMMEDIATE l_sql
    INTO v_customer_id
    USING p_name;
~~~

Bind variables protect data values from being interpreted as SQL syntax and support cursor reuse. For table names, column names, or keywords that cannot be bound as values, whitelist and validate identifiers; `DBMS_ASSERT` can be considered where appropriate.

### 9.4. The application layer still needs authorization

Data-checking procedures do not replace authentication. The connection pool's database user is typically a shared service account used on behalf of many end users. The database does not automatically know the end user's identity unless the application passes context through a designed and controlled mechanism.

The application must still authenticate the user/service caller, check resource/tenant permissions, distrust user-supplied data, grant only necessary privileges to the database account, and avoid returning sensitive internal errors externally.

## 10. Transactions Across Multiple Databases or External Services

An Oracle transaction only manages changes within supported transactional resources. If a procedure needs to call a REST API, send an email, or write a message to another system, the Oracle transaction will not automatically roll back actions that already occurred in the external system.

Do not send emails or call payment services directly from a trigger/procedure while the main transaction is open unless the external system participates in a clearly designed distributed transaction.

### 10.1. Outbox pattern

A common pattern is writing business data and an outbox event within the same Oracle transaction:

~~~sql
INSERT INTO orders (
    order_id, status, total_amount
) VALUES (
    :order_id, 'CREATED', :total_amount
);

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload, status
) VALUES (
    :event_id, :order_id, 'ORDER_CREATED', :payload, 'PENDING'
);

COMMIT;
~~~

An application-layer worker reads committed outbox rows and sends messages/emails/API requests. If the worker sends successfully but crashes before marking the event as sent, the event may be re-sent; consumers require idempotency.

### 10.2. Sagas and compensating actions

A multi-service workflow can consist of multiple short transactions. If a later step fails, the system executes compensating actions to bring the business state to an acceptable state. This is a saga/compensation, distinct from rolling back a single Oracle transaction.

### 10.3. Autonomous transactions are not distributed transactions

`PRAGMA AUTONOMOUS_TRANSACTION` creates an independent transaction inside Oracle. It does not automatically participate in transactions with an HTTP service or message broker. Independently committed logs can remain even if the main business transaction rolls back. Use it only when well-defined independent semantics are required, such as certain types of audit/logging.

## 11. Triggers: Automatic Logic Requiring Clear Boundaries

A trigger is PL/SQL invoked by Oracle when an event occurs on a table, view, schema, or database depending on the trigger type. Triggers can validate/normalize data, log audit changes within the same transaction, perform technical table-bound logic, or maintain invariants that every client must obey.

However, triggers can make logic less visible to the application. A single INSERT statement can fire multiple triggers and cause cascading changes.

### 11.1. Triggers should not hide large workflows

A trigger that sends an email directly when an order is inserted couples the database transaction to an external service. If the email succeeds but the transaction rolls back, the recipient has received a notification for a nonexistent order. If the email fails, the DML may be unintentionally affected.

A more controllable approach is having a trigger or procedure write an outbox event within the same transaction, while a worker sends the notification after commit.

### 11.2. Triggers vs. application logic

If a rule only applies to one UI or one use case, placing it in the application is usually clearer. If the rule protects data regardless of which client writes to the table, consider constraints, triggers, or database APIs. Prefer declarative constraints such as NOT NULL, CHECK, UNIQUE, and foreign keys whenever expressible as constraints.

## 12. Calling PL/SQL Functions from SQL and Its Limits

PL/SQL functions can be called in SQL when they satisfy Oracle's rules:

~~~sql
SELECT employee_id,
       calculate_discount(salary) AS discount_amount
FROM employees;
~~~

However, functions called from SQL have restrictions on side effects and transactions. Do not use functions that perform arbitrary DML inside a SELECT. Functions called from SQL must adhere to Oracle's purity/SQL-callable rules; certain operations that modify database state can cause runtime errors or unpredictable behavior.

### 12.1. Do not use functions to replace joins or aggregates

If a function queries a lookup table for each row:

~~~sql
SELECT order_id,
       get_customer_name(customer_id)
FROM orders;
~~~

With hundreds of thousands of orders, the function may be invoked many times. A join is usually clearer and can be optimized better:

~~~sql
SELECT o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id;
~~~

A function in the SELECT list can be convenient when the logic is small, stable, and low-cost; however, it should not hide large repeated queries.

### 12.2. DETERMINISTIC is not a promise to cache results forever

The `DETERMINISTIC` keyword is a programmer's guarantee that the same inputs will produce the same output under the function's conditions. Do not declare a function deterministic if it depends on mutable tables, session context, time, or external state without guaranteeing determinism.

Do not use `DETERMINISTIC` merely hoping Oracle will automatically cache every result. Optimization and caching depend on the function type, features, and usage context.

## 13. Dynamic SQL: When Statement Structure Must Vary

PL/SQL can execute dynamic SQL using `EXECUTE IMMEDIATE` or `DBMS_SQL`. Dynamic SQL is needed when table/column names or statement structure are only known at runtime.

Example of binding values:

~~~sql
DECLARE
    l_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM orders WHERE status = :status'
        INTO l_count
        USING 'PENDING';

    DBMS_OUTPUT.PUT_LINE(l_count);
END;
/
~~~

### 13.1. Bind values, whitelist identifiers

You cannot bind a table name with a placeholder like a regular value. If a table name is chosen by the user, map it through a whitelist:

~~~sql
DECLARE
    l_table_name VARCHAR2(30);
    l_count      NUMBER;
BEGIN
    IF :requested_type = 'ORDERS' THEN
        l_table_name := 'ORDERS';
    ELSIF :requested_type = 'CUSTOMERS' THEN
        l_table_name := 'CUSTOMERS';
    ELSE
        RAISE_APPLICATION_ERROR(-20040, 'Unsupported object');
    END IF;

    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM ' || l_table_name
        INTO l_count;
END;
/
~~~

Identifier names are selected from an allowed list; data values should still use bind variables. Never concatenate strings directly from untrusted input.

### 13.2. When should static SQL be used?

Static SQL is checked earlier by the PL/SQL compiler for syntax, objects, and data types in many situations, is easier to read, and makes dependency management easier. Use dynamic SQL only when you genuinely need to vary the statement structure or referenced objects.

## 14. Performance: Put Logic Near Data or in the Application?

Placing logic in the database can reduce round-trips, but it is not always faster. You must measure database, network, and application costs together.

### 14.1. Many round-trips from the application

~~~java
for (Long orderId : orderIds) {
    Order order = repository.findById(orderId);
    repository.updateStatus(orderId, "REVIEW");
}
~~~

With 10,000 orders, the application can generate tens of thousands of network round-trips and query executions. If the operation is uniform across a condition, a set-based SQL UPDATE or a batch-processing procedure can be more efficient.

### 14.2. Stored procedures are not automatically faster

A procedure containing a loop with row-by-row SELECT/UPDATE still generates many context switches. A single SQL statement from the application can be faster than a procedure doing the same work row by row.

Performance depends on:
- Number of network round-trips.
- Number of PL/SQL/SQL context switches.
- Execution plans and statistics.
- Data volume and selectivity.
- Indexes, partitioning, and locking.
- PGA/SGA, CPU, I/O, redo/undo.
- Application processing workload and network latency.

### 14.3. Bulk processing and batch size

If logic must process records individually because each record has distinct rules, you can use BULK COLLECT/FORALL or JDBC batching. Choose the batch size based on measurements, memory, transaction duration, and rollback requirements.

Do not hold transactions open while waiting for user input, calling slow network services, downloading large files, waiting for queue messages, or running long computations that do not need data locks. Separate preparation outside the transaction when safe, then open a short transaction for the checks and updates requiring atomicity.

## 15. Testing PL/SQL and Application Code

Logic in the database must be tested just like application code. It can be tested using:
- PL/SQL unit tests, such as the utPLSQL framework if used by the project.
- Integration tests from JDBC/the application.
- Boundary, null, duplicate, and constraint data tests.
- Transaction rollback tests when a step fails.
- Definer/invoker rights and SQL injection tests.
- Concurrency tests for conflicting updates.
- Performance tests with representative data.

### 15.1. Testing procedures in a SQL client

~~~sql
SET SERVEROUTPUT ON;

BEGIN
    order_api.mark_paid(1001);
    DBMS_OUTPUT.PUT_LINE('Procedure completed');
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Error ' || SQLCODE || ': ' || SQLERRM
        );
        RAISE;
END;
/
~~~

When testing DML in a lab environment and the procedure does not commit on its own, the operator must decide whether to commit or roll back after inspecting the results. Do not assume that finishing a PL/SQL block means the database has committed.

### 15.2. Testing transaction rollback

~~~sql
BEGIN
    UPDATE orders
    SET status = 'PROCESSING'
    WHERE order_id = 1001;

    RAISE_APPLICATION_ERROR(-20050, 'Simulated failure');
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

After the error is propagated, uncommitted changes in the transaction are rolled back. When designing real tests, you must account for whether called inner procedures self-commit, trigger implicit DDL commits, or use autonomous transactions.

### 15.3. Testing the application contract

Integration tests should verify:
- Procedures/functions have the exact expected names and signatures.
- Input/output data types and null semantics.
- Business error codes are mapped accurately.
- Connections are returned to the pool after commit/rollback.
- Multiple repositories participate in the same transaction when needed.
- No dynamic SQL is vulnerable to injection.
- Behavior after timeout/connection loss and retries is idempotent.

## 16. Deploying and Versioning PL/SQL Logic

PL/SQL stored objects are part of the schema. Changes to packages, procedures, functions, views, or triggers must be deployed in sync with dependent application code.

### 16.1. Database migrations

~~~sql
CREATE OR REPLACE PACKAGE app_order_api AS
    PROCEDURE approve_order(p_order_id NUMBER);
END app_order_api;
/
~~~

Migrations must be managed by the project's versioning tool, not edited manually in production without history.

### 16.2. Backward compatibility

If old and new application versions run simultaneously during a rolling deployment, changing a procedure signature can break the old version. Some principles:
- Prefer adding parameters with defaults when compatibility allows.
- Do not immediately drop or rename database APIs still used by clients.
- You can create a new API version and gradually migrate callers.
- Deploy database objects in a compatible order.
- Run integration tests against existing live application versions.

### 16.3. Invalid objects and dependencies

When a referenced object changes, dependent stored program units can become INVALID and require recompilation. You can check with:

~~~sql
SELECT object_name,
       object_type,
       status
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;
~~~

Recompile affected objects using `ALTER ... COMPILE` or standard schema administration procedures. Do not arbitrarily recompile an entire schema in production without understanding dependencies and workload.

### 16.4. Do not embed secrets in PL/SQL source

Never hard-code passwords, API keys, tokens, or connection details inside a package body. Secrets should be managed by an appropriate secret manager/credential store. Database code should only receive the privileges and data it needs, without storing plaintext secrets in source.

## 17. Choosing an Architecture by Scenario

### Scenario A: Calculating total revenue by customer

Use a SQL aggregate:

~~~sql
SELECT customer_id, SUM(amount)
FROM orders
GROUP BY customer_id;
~~~

No PL/SQL loop over each order is needed.

### Scenario B: Updating multiple tables in one transaction

You can use a procedure to encapsulate DML close to the data, or an application transaction calling multiple repositories. Choose one layer to own the transaction and ensure all steps share the same connection/session.

### Scenario C: Sending an email after an order is created

The application/worker should send the email after commit. The database can write an outbox event in the same transaction; do not let a trigger send emails directly.

### Scenario D: Multiple applications need the same data validation rule

You can place the invariant in a constraint or database API. If the rule is a global data truth that must always hold, a database constraint is usually the stronger choice. If it is a policy specific to one application, the service layer may be more appropriate.

### Scenario E: Importing millions of rows

Use set-based SQL or direct/bulk load as required. If batched logic is needed, PL/SQL bulk processing or application batching can work. Design checkpoints, commit chunks, and idempotency so the job can be rerun.

### Scenario F: Workflows requiring human approval

An application/workflow engine should orchestrate long-lived state and user interactions. The database stores state and enforces invariants via constraints/APIs. Never hold a transaction open while waiting for approval.

## 18. Common Design Mistakes

| Symptom | Cause | Remediation |
|---|---|---|
| Procedure runs slowly when processing many rows | Row-by-row SQL in a loop | Use set-based SQL or bulk processing |
| Application cannot roll back the entire business operation | Procedure self-COMMITs or uses a different connection | Define the transaction owner and remove unnecessary commits |
| A SELECT calling a function is very slow | Function repeatedly queries tables per row | Use joins/aggregates or reduce call frequency |
| DML finishes but application falsely reports success | Not checking SQL%ROWCOUNT | Verify affected row count against the contract |
| Database errors are hidden | WHEN OTHERS followed by NULL | Log in a controlled manner and re-raise with RAISE |
| SQL injection in PL/SQL | Concatenating input into dynamic SQL | Bind values, whitelist identifiers, use DBMS_ASSERT where appropriate |
| Stored procedures are difficult to deploy | Schema objects are not versioned | Use migrations and compatibility testing |
| Triggers cause unpredictable side effects | Workflow logic hidden inside triggers | Keep triggers small; use outbox/services for side effects |
| Slow commits or long-held locks | Long transactions, network calls inside transactions | Shorten transactions and move external steps outside |
| Rules diverge between app and database | Multiple clients re-implementing the same invariant | Put invariants in constraints or a shared API |
| Database depends on external services | PL/SQL calls services directly during DML flow | Outbox, workers, or sagas |
| Using PL/SQL for simple calculations | Proceduralizing a SQL expression | Let SQL perform set-based calculations |

## 19. Checklist for Defining Boundaries Between SQL, PL/SQL, and Application

Before deciding where to place logic, ask:

1. Can the logic be expressed in a single set-based SQL statement?
2. Is there a need to orchestrate multiple SQL statements close to the data within one database session?
3. Do multiple applications need to share this logic?
4. Is the rule a data invariant or simply the behavior of a single use case?
5. Does it need to call APIs, send messages, send emails, or interact with users?
6. Who owns the transaction and who is responsible for commit/rollback?
7. Do all statements share the same connection/session?
8. Is there dynamic SQL, untrusted input, or definer/invoker rights involved?
9. Is there a risk of excessive context switches or network round-trips?
10. Does the logic need to run on other databases or be deployed independently of the schema?
11. Are versioning, backward compatibility, and integration tests needed?
12. On mid-flight errors or retries, do data and side effects remain correct?

## 20. Controlled Practice Exercises

The exercises below use the lab table `LAB_PL_SQL_ORDERS`. Only create objects in authorized DEV/TEST schemas and confirm the correct PDB/service. Do not run sample DDL or DML on production business tables.

### 20.1. Create lab data

~~~sql
CREATE TABLE lab_plsql_orders (
    order_id    NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    amount      NUMBER(12, 2) NOT NULL,
    status      VARCHAR2(20 CHAR) NOT NULL
);

INSERT ALL
    INTO lab_plsql_orders VALUES (1, 101, 1000, 'NEW')
    INTO lab_plsql_orders VALUES (2, 101, 2000, 'NEW')
    INTO lab_plsql_orders VALUES (3, 102, 1500, 'PAID')
    INTO lab_plsql_orders VALUES (4, 103, 3000, 'NEW')
SELECT 1 FROM dual;

COMMIT;
~~~

### Exercise 1 — Set-based SQL vs. row-by-row PL/SQL

Write a cursor FOR LOOP block to change all `NEW` orders to `REVIEW`. Then write an equivalent single `UPDATE` statement. Compare code length and how the database processes each.

~~~sql
UPDATE lab_plsql_orders
SET status = 'REVIEW'
WHERE status = 'NEW';

ROLLBACK;
~~~

### Exercise 2 — Create a status-checking procedure

Write procedure `mark_order_paid(p_order_id)`:
- Read the order status.
- Only allow transitioning from `NEW` to `PAID`.
- If it does not exist, raise an appropriate business error.
- If the status is invalid, raise a different error.
- Do not commit inside; let the caller decide the transaction outcome.

### Exercise 3 — Checking SQL%ROWCOUNT

Write a procedure that updates status conditionally:

~~~sql
UPDATE lab_plsql_orders
SET status = 'REVIEW'
WHERE order_id = p_order_id
  AND status = 'NEW';
~~~

Use `SQL%ROWCOUNT` to distinguish updating exactly one row, order not found, or status no longer `NEW`.

### Exercise 4 — Comparing a function and a join

Create a function that returns a customer name by customer ID (you may create a lab customers table). Call the function in a `SELECT` over multiple orders. Then write the equivalent `JOIN` query. Observe the number of calls and the execution plan; explain when a function is convenient and when a join is more suitable.

### Exercise 5 — JDBC transaction

Write a Java method that accepts a `Connection` and calls two repository operations on the same connection. Disable auto-commit at the transaction-owning layer. Intentionally cause the second step to fail and verify that the first step is rolled back. Verify that any called procedure does not self-commit.

### Exercise 6 — SQL injection and bind variables

Write an unsafe dynamic SQL example that concatenates input into `WHERE`. Then fix it using `EXECUTE IMMEDIATE ... USING`. If the input is a table name, use an identifier whitelist and explain why a table name cannot be bound as a value.

### Exercise 7 — Outbox

Create a lab outbox table. Write a procedure that creates an order and inserts an outbox event within the same transaction. Do not send emails in the procedure. Describe how an application worker reads committed events, sends notifications, and marks status idempotently.

### Exercise 8 — Testing exceptions

Create a procedure that raises `RAISE_APPLICATION_ERROR` after DML. Call it from a SQL client with an uncommitted transaction. Observe whether the DML remains in the transaction or was rolled back, then decide on rollback yourself. Retry with a procedure containing `COMMIT` to see the difference in transaction contract.

### Cleaning up lab data

Only after confirming the exact objects you created in DEV/TEST and that no one else is using them:

~~~sql
DROP TABLE lab_plsql_orders PURGE;
~~~

If you created additional tables or packages during the exercises, drop the corresponding lab objects in dependency order. DDL performs an implicit commit in Oracle; do not run it on production or objects outside the practice scope.

## 21. Review Questions

**Question 1.** What is the core difference between SQL and PL/SQL?

**Answer:** SQL describes data operations declaratively; PL/SQL adds variables, conditionals, loops, exceptions, and subprograms to orchestrate processing.

**Question 2.** Why should set-based SQL be preferred over looping row by row?

**Answer:** The SQL engine is optimized for set processing; row-by-row processing can cause many switches between the PL/SQL and SQL engines and excessive repeated work.

**Question 3.** Is a stored procedure automatically faster than SQL sent from the application?

**Answer:** No. A procedure can reduce network round-trips, but it can still be written row by row and generate many context switches. You must measure the execution plan and workload.

**Question 4.** Is a context switch between the PL/SQL engine and the SQL engine the same as a network round-trip?

**Answer:** No. A context switch happens inside the database; a network round-trip is communication between the application and the database over a connection.

**Question 5.** When should BULK COLLECT and FORALL be used?

**Answer:** When you need to process a multi-row collection and cannot reasonably express the operation as a single set-based SQL statement; bulk processing reduces switches between the PL/SQL and SQL engines.

**Question 6.** Who should own the transaction?

**Answer:** Either the application or a database API with a clearly designed contract. Do not let multiple layers commit arbitrarily; all steps requiring atomicity must share the same transaction/session.

**Question 7.** Why should shared procedures usually not COMMIT?

**Answer:** An internal COMMIT can commit other uncommitted changes belonging to the caller in the same session, stripping the caller of the ability to roll back the whole use case.

**Question 8.** When should an invariant be placed in a constraint?

**Answer:** When the rule can be expressed via constraints such as NOT NULL, CHECK, UNIQUE, or foreign keys and must hold true regardless of which client writes the data.

**Question 9.** Why should emails not be sent inside a trigger?

**Answer:** Sending an email is a side effect outside the Oracle transaction; the email could be sent even if the transaction rolls back, or an email failure could unexpectedly break DML. Outbox/workers decouple side effects until after commit.

**Question 10.** What do bind variables protect against in dynamic SQL?

**Answer:** Input values are passed as data rather than SQL syntax, helping reduce SQL injection and supporting cursor reuse. Identifiers require separate whitelisting/validation.

**Question 11.** How do definer rights and invoker rights differ?

**Answer:** Definer rights execute under the owner/definer's privileges; invoker rights use the caller's privileges according to Oracle rules. Choose based on the API and security model.

**Question 12.** What is the risk of `WHEN OTHERS THEN NULL`?

**Answer:** It swallows errors and makes the caller think the operation succeeded. Errors should be handled deliberately, logged appropriately, and usually re-raised with RAISE.

**Question 13.** Should a function called from SQL perform arbitrary DML?

**Answer:** No. SQL-callable functions have restrictions regarding side effects and transactions; keep functions purely computational or appropriately read-only, and do not use them to replace joins or aggregates.

**Question 14.** What does the outbox pattern solve?

**Answer:** It writes business data and an event within the same database transaction; a worker delivers the event after commit. Consumers still need idempotency because events may be redelivered.

## Conclusion

**SQL, PL/SQL, and application code have complementary roles.** SQL should handle set-based querying and data modifications; PL/SQL should orchestrate steps close to the data, encapsulate database APIs, and handle logic shared inside Oracle; the application should own user interaction, APIs, authentication, service integration, and system-level workflows.

When designing, prefer set-based SQL statements over row-by-row loops; use bulk processing when manipulating many rows via collections. Clearly establish which layer owns the transaction, avoid procedures that commit outside their contract, and ensure atomic steps share the same connection/session. Keep external side effects like emails or messages in the application/worker layer, using an outbox to record events in the same database transaction when appropriate. Finally, test performance, privileges, exceptions, concurrency, and version compatibility before deploying PL/SQL logic alongside application releases.

## Oracle Reference Documentation

- [Oracle Database 19c PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/index.html): block structure, variables, control flow, procedures, functions, packages, and exceptions.
- [Oracle Database 19c SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/index.html): SQL statements, queries, DML, and dynamic SQL.
- [Oracle Database 19c PL/SQL Optimization and Tuning](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-optimization-and-tuning.html): bulk SQL, context switching, and PL/SQL optimization.
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_ASSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ASSERT.html): validating SQL identifiers in appropriate dynamic SQL scenarios.
- [Oracle Database 19c PL/SQL Language Reference — Invoker's Rights and Definer's Rights](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights-authid-property.html): AUTHID DEFINER and AUTHID CURRENT_USER.

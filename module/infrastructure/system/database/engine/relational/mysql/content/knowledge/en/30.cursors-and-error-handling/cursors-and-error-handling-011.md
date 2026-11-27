# Designing Errors with Stable Error Codes and Testing from JDBC

A stored procedure can raise errors due to invalid input data, missing records, disallowed business states, unique key violations, or infrastructure failures. If an application merely reads the error message string and guesses the cause, the contract between MySQL and Java becomes fragile whenever wording changes, the server is upgraded, or messages are localized.

Good error design requires **stable error codes**, **meaningful SQLSTATE values**, diagnostic messages, and clear transaction rules. On the JDBC side, integration tests must assert those stable properties directly via `SQLException`, while verifying that data is never left half-modified when a routine fails.

In the DATABASE_MYSQL module, this lesson bridges stored program error handling with a Java application's API contract. You will use SIGNAL, RESIGNAL, GET DIAGNOSTICS, MYSQL_ERRNO, SQLSTATE, CallableStatement, and integration tests to design, detect, and maintain business errors in a verifiable manner.

## 1. The Error Contract Between MySQL and the Application

An error sent from a stored procedure to an application typically has three key components:

| Component | Role | Should It Be Used as a Business Classification Key? |
|---|---|---|
| MYSQL_ERRNO | Numeric error code returned by MySQL/driver; custom codes can be set for application errors. | Yes. This is the primary stable code in this lesson's example contract. |
| RETURNED_SQLSTATE | 5-character SQL state code indicating the error category. | Yes, for category classification and SQL-standard handling. |
| MESSAGE_TEXT | Descriptive text for human reading and diagnostics. | No. Wording can change; do not parse messages to drive business flow. |

Example of a business error:

~~~sql
SIGNAL SQLSTATE '45000'
    SET MYSQL_ERRNO = 31004,
        MESSAGE_TEXT = 'Insufficient inventory';
~~~

The application can receive:

~~~text
SQLState:   45000
Error code: 31004
Message:    Insufficient inventory
~~~

SQLSTATE 45000 is the standard SQLSTATE for user-defined exceptions in MySQL. `MYSQL_ERRNO = 31004` is a detailed code defined by application convention. Message provides explanatory context only.

### Why Not Classify by Message?

Do not write logic like:

~~~java
if (exception.getMessage().contains("Insufficient inventory")) {
    // Handle insufficient inventory error.
}
~~~

Wording may change from "Insufficient inventory" to "Not enough stock", include a product ID, or be wrapped by a driver or framework. Business logic then breaks even though the error code never changed.

Instead, check:

~~~java
if (exception.getErrorCode() == 31004) {
    // Handle insufficient inventory error.
}
~~~

In JDBC, `SQLException.getErrorCode()` returns the vendor-specific error code; `getSQLState()` returns SQLSTATE. With MySQL Connector/J, the server's numeric code is retrieved via `getErrorCode()`.

## 2. SQLSTATE and MYSQL_ERRNO

SQLSTATE has 5 characters. The first two characters indicate the state class; the last three describe the specific state within that class.

| SQLSTATE Class | General Meaning | Common Example |
|---|---|---|
| 00 | Successful completion | 00000 |
| 01 | Warning | Warning condition |
| 02 | No data | NOT FOUND in certain read operations |
| 22 | Data exception | Invalid data value |
| 23 | Integrity constraint violation | Unique/foreign key violation |
| 40 | Transaction rollback | Deadlock or rolled-back transaction |
| 45 | User-defined exception | 45000 |

There is no need to invent a separate SQLSTATE for every business error. You can use `45000` for errors proactively raised by routines and distinguish specifics using `MYSQL_ERRNO`.

### Business Error Codes Need a Namespace

Reserve a dedicated range agreed upon by routines and the Java application. For example:

| MYSQL_ERRNO | Stable Name | Meaning |
|---:|---|---|
| 31001 | INVALID_REQUEST | Missing or invalid input data. |
| 31002 | PRODUCT_NOT_FOUND | Target product for operation not found. |
| 31003 | DUPLICATE_REQUEST | Request ID has already been used. |
| 31004 | INSUFFICIENT_INVENTORY | Available stock cannot satisfy the request. |
| 31005 | INVENTORY_CONFLICT | Update condition no longer held at write time. |

The numbers above are example conventions, not default MySQL error codes. In a real project:

- Choose a range managed by the database/application teams and verify it does not collide with active server codes.
- Never repurpose a published code for a different meaning.
- Store the `code ↔ error name ↔ application action` mapping in source control.
- Version changes or maintain backward compatibility when evolving the contract.
- Never put sensitive information, SQL text, tokens, or personal data into `MESSAGE_TEXT`.

## 3. Proactively Raising Errors with SIGNAL

SIGNAL terminates the current flow with a condition. For business errors, use SQLSTATE 45000 and assign a clear numeric code and message.

Example validating quantity:

~~~sql
IF p_quantity IS NULL OR p_quantity = 0 THEN
    SIGNAL SQLSTATE '45000'
        SET MYSQL_ERRNO = 31001,
            MESSAGE_TEXT = 'Quantity must be greater than zero';
END IF;
~~~

If the condition fails, subsequent statements in the current block do not continue running in normal flow. The error passes to a matching handler or returns to the caller.

### Named Conditions Can Be Used

MySQL supports declaring named conditions for readability:

~~~sql
DECLARE invalid_request CONDITION FOR SQLSTATE '45000';
~~~

A condition name binds to a single SQLSTATE or MySQL error code per its declaration; if multiple business codes share SQLSTATE 45000, the application still reads `MYSQL_ERRNO` to tell each error apart.

### MESSAGE_TEXT Is Not an API Key

Keep messages short, loggable, and helpful to operators. If the application needs parameter details like `product_id`, log them at the application layer with request context or design controlled diagnostic output. Never parse messages to extract IDs or decide retries.

## 4. Translating Original Errors with RESIGNAL

RESIGNAL is used inside a handler to re-raise the caught condition. Without changing attributes, it preserves the original error; if needed, it can alter SQLSTATE, MYSQL_ERRNO, or MESSAGE_TEXT.

Example translating a MySQL duplicate key error into a stable business error:

~~~sql
DECLARE v_mysql_errno INT DEFAULT 0;

DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    GET DIAGNOSTICS CONDITION 1
        v_mysql_errno = MYSQL_ERRNO;

    IF v_mysql_errno = 1062 THEN
        RESIGNAL SQLSTATE '45000'
            SET MYSQL_ERRNO = 31003,
                MESSAGE_TEXT = 'Request identifier already exists';
    ELSE
        RESIGNAL;
    END IF;
END;
~~~

`1062` is the standard MySQL error code for duplicate key. The handler reads the original code from the diagnostics area. If it is a duplicate error, the routine returns business code `31003`; all other errors are RESIGNALed as-is.

Do not translate every error into the same generic business code. Doing so hides deadlocks, connection failures, permission errors, or data errors that the application needs to handle differently.

## 5. GET DIAGNOSTICS for Reading Conditions

In stored programs, GET DIAGNOSTICS reads information from the diagnostics area. Commonly used items include:

- `RETURNED_SQLSTATE`: SQLSTATE of the condition.
- `MYSQL_ERRNO`: numeric error code.
- `MESSAGE_TEXT`: message text.
- `NUMBER`: number of conditions in the diagnostics area.
- `ROW_COUNT`: number of rows affected by the most recent statement in diagnostics context.

Example reading the first condition inside a handler:

~~~sql
DECLARE v_state CHAR(5) DEFAULT '00000';
DECLARE v_errno INT DEFAULT 0;
DECLARE v_message VARCHAR(128) DEFAULT '';

DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    GET DIAGNOSTICS CONDITION 1
        v_state = RETURNED_SQLSTATE,
        v_errno = MYSQL_ERRNO,
        v_message = MESSAGE_TEXT;

    -- These variables can be used for mapping or diagnostic decisions.
    RESIGNAL;
END;
~~~

If the handler executes additional statements for logging, read diagnostics before running other statements because subsequent statements can alter the diagnostics area. Also consider transactions: logs written inside the same transaction can be rolled back with the business work. In many systems, logging the final error in the Java/application layer is more reliable for preserving trails after rollback.

### The Diagnostics Area Does Not Replace the Error Contract

GET DIAGNOSTICS is helpful for handlers and logging, yet the JDBC caller should still receive a stable SQLSTATE and numeric code. Do not force the application to run an extra query reading session variables just to guess what error occurred.

## 6. Handlers and Transaction Boundaries

Handlers define how a stored program reacts to a condition. Two commonly used types:

- CONTINUE: handles the condition and continues at the next statement in the block.
- EXIT: exits the block declaring the handler after the handler completes.

Example of NOT FOUND when reading a row:

~~~sql
DECLARE v_product_found BOOLEAN DEFAULT TRUE;
DECLARE v_available BIGINT UNSIGNED DEFAULT NULL;

DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_product_found = FALSE;
~~~

After `SELECT ... INTO`, the routine checks the flag and actively SIGNALs `PRODUCT_NOT_FOUND` if no row existed.

### Handlers Do Not Automatically Roll Back Transactions

This is a critical rule when integrating with JDBC. Catching an exception with `EXIT HANDLER` or raising `SIGNAL` does not automatically roll back prior changes. Transaction boundaries must be clearly defined:

1. Either the routine owns the transaction and executes START TRANSACTION/COMMIT/ROLLBACK itself; or
2. The caller owns the transaction, and the routine joins the current transaction without committing or rolling back on its own.

Do not mix both contracts. The hands-on example below uses the caller-owned transaction model: Java sets `autoCommit=false`, invokes the procedure, commits on success, and rolls back on `SQLException`.

If a procedure executes SIGNAL after already updating a row, the application must roll back the transaction so earlier changes are not left partially committed. Never assume RESIGNAL triggers rollback.

## 7. Example Schema for an Inventory Reservation Routine

Create two InnoDB tables:

~~~sql
CREATE TABLE inventory (
    product_id BIGINT UNSIGNED NOT NULL,
    available_qty BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (product_id),
    CONSTRAINT chk_inventory_nonnegative
        CHECK (available_qty >= 0)
) ENGINE=InnoDB;

CREATE TABLE stock_reservations (
    request_id VARCHAR(64) NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (request_id),
    KEY idx_stock_reservations_product (product_id),
    CONSTRAINT fk_stock_reservations_product
        FOREIGN KEY (product_id) REFERENCES inventory(product_id),
    CONSTRAINT chk_stock_reservations_quantity
        CHECK (quantity > 0)
) ENGINE=InnoDB;

INSERT INTO inventory (product_id, available_qty)
VALUES (1001, 20), (1002, 0);
~~~

MySQL enforces CHECK constraints starting in version 8.0.16. On older environments, do not rely on CHECK to protect invariants; validate inside the routine and verify server version before deploying the schema.

`request_id` is a unique key preventing duplicate request processing. If a request is re-sent, the routine returns `DUPLICATE_REQUEST`; the system can alternatively implement idempotency by reading the existing reservation and verifying whether the payload matches the initial request.

## 8. Stored Procedure with Stable Error Codes

The procedure below validates input, locks the inventory row, raises business errors, and maps duplicate keys to a stable code. The procedure **does not manage transactions itself**; the caller must invoke it inside an InnoDB transaction and commit/roll back.

~~~sql
DELIMITER //

CREATE PROCEDURE reserve_inventory(
    IN p_request_id VARCHAR(64),
    IN p_product_id BIGINT UNSIGNED,
    IN p_quantity BIGINT UNSIGNED
)
BEGIN
    DECLARE v_available BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;
    DECLARE v_mysql_errno INT DEFAULT 0;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_not_found = TRUE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            v_mysql_errno = MYSQL_ERRNO;

        IF v_mysql_errno = 1062 THEN
            RESIGNAL SQLSTATE '45000'
                SET MYSQL_ERRNO = 31003,
                    MESSAGE_TEXT = 'Request identifier already exists';
        ELSE
            RESIGNAL;
        END IF;
    END;

    IF p_request_id IS NULL
       OR CHAR_LENGTH(TRIM(p_request_id)) = 0
       OR p_product_id IS NULL
       OR p_quantity IS NULL
       OR p_quantity = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MYSQL_ERRNO = 31001,
                MESSAGE_TEXT = 'Invalid reservation request';
    END IF;

    SET v_not_found = FALSE;

    SELECT available_qty
      INTO v_available
      FROM inventory
     WHERE product_id = p_product_id
     FOR UPDATE;

    IF v_not_found THEN
        SIGNAL SQLSTATE '45000'
            SET MYSQL_ERRNO = 31002,
                MESSAGE_TEXT = 'Product does not exist';
    END IF;

    IF v_available < p_quantity THEN
        SIGNAL SQLSTATE '45000'
            SET MYSQL_ERRNO = 31004,
                MESSAGE_TEXT = 'Insufficient inventory';
    END IF;

    UPDATE inventory
       SET available_qty = available_qty - p_quantity
     WHERE product_id = p_product_id
       AND available_qty >= p_quantity;

    IF ROW_COUNT() <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MYSQL_ERRNO = 31005,
                MESSAGE_TEXT = 'Inventory changed before reservation';
    END IF;

    INSERT INTO stock_reservations (
        request_id,
        product_id,
        quantity
    )
    VALUES (
        p_request_id,
        p_product_id,
        p_quantity
    );
END//

DELIMITER ;
~~~

### Why Does the Procedure Use SELECT ... FOR UPDATE?

`SELECT ... FOR UPDATE` locks the found inventory record until the transaction ends. Two transactions reserving the same product cannot concurrently read and then write based on the same stale value. The later transaction waits for the lock and then re-reads the current quantity.

### Why Does the UPDATE Still Include available_qty >= p_quantity?

The condition on UPDATE is an extra layer of protection. If the state is no longer valid, affected rows will not equal 1 and the routine raises `INVENTORY_CONFLICT`. `ROW_COUNT()` must be checked right after UPDATE because any subsequent statement can overwrite this count.

### Why Are Duplicate Errors Translated with RESIGNAL?

`request_id` is the primary key. If the request already exists, InnoDB raises duplicate-key error 1062. The handler translates that constraint error into business code 31003 so Java does not have to depend on index names or default server messages.

## 9. Error Catalog Conventions in Java

Java should centralize error codes in one place instead of scattering numeric literals across services and controllers.

~~~java
public enum DatabaseErrorCode {
    INVALID_REQUEST(31001),
    PRODUCT_NOT_FOUND(31002),
    DUPLICATE_REQUEST(31003),
    INSUFFICIENT_INVENTORY(31004),
    INVENTORY_CONFLICT(31005);

    private final int vendorCode;

    DatabaseErrorCode(int vendorCode) {
        this.vendorCode = vendorCode;
    }

    public int vendorCode() {
        return vendorCode;
    }

    public static Optional<DatabaseErrorCode> from(SQLException exception) {
        return Arrays.stream(values())
            .filter(code -> code.vendorCode == exception.getErrorCode())
            .findFirst();
    }
}
~~~

This snippet requires imports for `java.sql.SQLException`, `java.util.Arrays`, and `java.util.Optional`. In real projects, consider walking the `SQLException.getNextException()` chain if drivers/frameworks attach multiple related errors.

### Mapping Errors to Application Behavior

| Code | Typically Appropriate Application Behavior |
|---:|---|
| 31001 | Return validation error to caller; do not auto-retry. |
| 31002 | Return not found; do not retry unless data is created first. |
| 31003 | Handle idempotency or conflict by request ID; do not blindly retry the same payload. |
| 31004 | Return business conflict/insufficient stock; do not retry immediately. |
| 31005 | May re-read state and decide retry per policy. |
| 1213 / SQLSTATE class 40 | Deadlock/transaction rollback; typically retry the whole transaction with cap and backoff. |

Application error codes should not collide with native MySQL error codes that the application also handles. If routines only raise 45000 for business errors and preserve other native errors, Java can cleanly separate the two groups.

## 10. Calling Stored Procedures from JDBC

JDBC uses `CallableStatement` to invoke procedures:

~~~java
String sql = "{call reserve_inventory(?, ?, ?)}";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (CallableStatement statement = connection.prepareCall(sql)) {
        statement.setString(1, requestId);
        statement.setLong(2, productId);
        statement.setLong(3, quantity);

        statement.execute();
        connection.commit();
    } catch (SQLException exception) {
        connection.rollback();
        throw exception;
    }
}
~~~

Java owns the transaction:

1. `setAutoCommit(false)` places multiple statements inside the procedure within the caller's transaction.
2. `CallableStatement.execute()` invokes the routine.
3. On success, Java calls `commit()`.
4. If the procedure raises an error, JDBC throws `SQLException`; Java calls `rollback()`.
5. The connection returns to the pool after the transaction has ended.

Do not leave autocommit enabled for this example. If each statement commits individually, `SELECT ... FOR UPDATE`, inventory UPDATE, and reservation INSERT are no longer protected as an atomic unit of work.

### Do Not Leave Connections in an Unfinished Transaction State

In production code, restore connection state before returning it to the pool. A helper can record `originalAutoCommit`, roll back on errors, and restore state in `finally`. Never call `setAutoCommit(true)` before rolling back because JDBC can commit the current transaction when switching autocommit from false to true.

## 11. Testing Error Codes from JDBC

Integration tests must verify both numeric code and SQLSTATE, not merely that an exception occurred. Example using JUnit 5:

~~~java
@Test
void insufficientInventoryReturnsStableDatabaseError() throws Exception {
    try (Connection connection = dataSource.getConnection()) {
        boolean originalAutoCommit = connection.getAutoCommit();
        connection.setAutoCommit(false);

        try {
            SQLException exception;

            try (CallableStatement statement = connection.prepareCall(
                    "{call reserve_inventory(?, ?, ?)}")) {
                statement.setString(1, "req-insufficient-001");
                statement.setLong(2, 1002L); // available_qty = 0
                statement.setLong(3, 1L);

                exception = assertThrows(
                    SQLException.class,
                    () -> statement.execute()
                );
            }

            assertEquals(31004, exception.getErrorCode());
            assertEquals("45000", exception.getSQLState());
        } finally {
            connection.rollback();
            connection.setAutoCommit(originalAutoCommit);
        }
    }
}
~~~

This test verifies:

- The procedure raises exact code 31004.
- Returned SQLSTATE is 45000.
- JDBC receives the error via `SQLException`.
- The transaction rolls back in `finally`, even if an assertion fails.

Do not assert the full `getMessage()` string because wording can change as diagnostics improve. If a message is part of user-facing display contracts, test it separately in the API mapping layer rather than relying on server wording.

## 12. Testing Duplicate Errors and Verifying Rollback

A crucial failure case is a duplicate request occurring after the routine has already updated inventory. The test must prove that caller rollback undoes the inventory modification.

Test example:

~~~java
@Test
void duplicateRequestRollsBackInventoryChange() throws Exception {
    String requestId = "req-duplicate-001";
    long productId = 1001L;
    long quantity = 2L;

    try (Connection connection = dataSource.getConnection()) {
        boolean originalAutoCommit = connection.getAutoCommit();
        connection.setAutoCommit(false);

        try {
            try (CallableStatement first = connection.prepareCall(
                    "{call reserve_inventory(?, ?, ?)}")) {
                first.setString(1, requestId);
                first.setLong(2, productId);
                first.setLong(3, quantity);
                first.execute();
            }
            connection.commit();

            long beforeRetry = readAvailableQuantity(connection, productId);

            SQLException exception;
            try (CallableStatement retry = connection.prepareCall(
                    "{call reserve_inventory(?, ?, ?)}")) {
                retry.setString(1, requestId);
                retry.setLong(2, productId);
                retry.setLong(3, quantity);

                exception = assertThrows(
                    SQLException.class,
                    () -> retry.execute()
                );
            }

            assertEquals(31003, exception.getErrorCode());
            assertEquals("45000", exception.getSQLState());

            connection.rollback();
            assertEquals(beforeRetry, readAvailableQuantity(connection, productId));
        } finally {
            connection.rollback();
            connection.setAutoCommit(originalAutoCommit);
        }
    }
}
~~~

`readAvailableQuantity` is a test helper executing `SELECT available_qty FROM inventory WHERE product_id = ?` on the same connection. Because the transaction rolled back before reading, the value must equal the state after the first reservation. This test proves a duplicate error does not leave a partial inventory UPDATE when the caller honors the rollback contract.

If retrying the same request ID is normal behavior, an idempotent design can return the prior reservation instead of reporting a duplicate. In that case, verify whether old and new payloads match; the same request ID with a different product/quantity must be treated as a conflict.

## 13. Testing the Success Path and Data State

Do not test only failures. The success path must verify both outcomes and side effects:

~~~java
@Test
void reservationDecreasesInventoryAndCreatesReservation() throws Exception {
    String requestId = "req-success-001";
    long productId = 1001L;
    long quantity = 3L;

    try (Connection connection = dataSource.getConnection()) {
        boolean originalAutoCommit = connection.getAutoCommit();
        connection.setAutoCommit(false);

        try {
            long before = readAvailableQuantity(connection, productId);

            try (CallableStatement statement = connection.prepareCall(
                    "{call reserve_inventory(?, ?, ?)}")) {
                statement.setString(1, requestId);
                statement.setLong(2, productId);
                statement.setLong(3, quantity);
                statement.execute();
            }

            long after = readAvailableQuantity(connection, productId);
            assertEquals(before - quantity, after);
            assertEquals(1, countReservations(connection, requestId));

            connection.commit();
        } finally {
            connection.rollback();
            connection.setAutoCommit(originalAutoCommit);
        }
    }
}
~~~

In tests using a dedicated database, deciding whether to commit or roll back depends on fixture strategy. The example above shows the success path with commit; `finally` rollback is safe cleanup if assertions or statements fail before commit. After a successful commit, rollback does not undo committed data.

The `countReservations` helper checks the reservation count for the request ID. Do not verify inventory balance alone because the balance might match while the reservation row is missing or duplicated.

## 14. Test Matrix for the Error Contract

A test suite should cover input errors, data errors, concurrency errors, and native errors:

| Scenario | Trigger | Expected Outcome |
|---|---|---|
| Empty request ID | Pass empty string | `MYSQL_ERRNO=31001`, SQLSTATE `45000`, no data modified. |
| Nonexistent product ID | Pass ID missing from inventory | `31002`, no reservation created. |
| Duplicate request ID | Re-invoke with already-committed request ID | `31003`; caller rolls back and inventory does not decrease a second time. |
| Insufficient inventory | Request more than available quantity | `31004`, no reservation created. |
| Conflict on UPDATE | Update condition no longer holds | `31005`. |
| Success | Valid quantity and new request | Exactly one reservation exists; inventory decreases by exact quantity. |
| Deadlock | Two transactions lock multiple products in opposite orders in a dedicated test | Native deadlock error / SQLSTATE class `40`; retry full transaction per policy. |
| Connection failure | Drop connection mid-call | Do not assume transaction committed; check state by request ID before retrying. |

Every test must start from a deterministic fixture. Clean up data in foreign-key order and never share request IDs across parallel tests.

## 15. Concurrency Testing with Two Connections

Single-threaded tests do not prove a routine is safe against race conditions. For inventory, spin up two connections concurrently requesting amounts exceeding the remaining total.

Example scenario:

~~~text
Initial inventory: product 1001 has 5 units

Connection A                         Connection B
-------------                         -------------
BEGIN                                 BEGIN
CALL reserve(..., 4)                  CALL reserve(..., 4)
SELECT ... FOR UPDATE                 waits for row lock
UPDATE available_qty = 1
INSERT reservation
COMMIT
                                      obtains lock
                                      reads available_qty = 1
                                      SIGNAL 31004
                                      ROLLBACK

Expected final state:
- One committed reservation for 4 units
- available_qty = 1
- The other call returns error 31004
~~~

Tests must use two separate connections and a barrier/latch to coordinate start timing. Never share a single connection across two threads because transactions and session state belong to the connection.

Beyond error codes, assert the final invariant:

~~~text
initial_quantity
= final_available_quantity
  + SUM(committed reservation quantity)
~~~

The invariant must hold once all transactions finish. If both requests succeed and drive the balance negative or total reservations exceed the initial quantity, the routine or transaction contract is unsafe.

## 16. Distinguishing Business, Data, and Infrastructure Errors

Not every error should be translated into a custom business code.

| Category | Examples | Recommended Handling |
|---|---|---|
| Validation/business | Quantity is 0, insufficient inventory | Stable business code; do not auto-retry. |
| Missing resource | Product does not exist | Not-found code; respond appropriately in API. |
| Conflict/idempotency | Duplicate request ID, state changed | Conflict code or return prior result per idempotency policy. |
| Constraint/data integrity | Unmapped foreign key or unique key | Preserve native code or map deliberately if meaning is stable. |
| Concurrency | Deadlock, lock wait timeout | Distinguish deadlock from timeout; bounded retry if transaction can re-run safely. |
| Infrastructure | Connection lost, server unavailable, disk full | Preserve original error details; do not turn into validation error. |
| Programming/schema | Unknown column, syntax error, missing table | Alert deployment/code; do not return as user input error. |

In particular, connection loss during COMMIT can leave an ambiguous state on the client side: the server may have committed while the response was lost. Never blindly retry a write operation. Use the request ID / idempotency key to query persisted state before deciding to re-execute.

## 17. JDBC Testing: Details to Watch

### getErrorCode and getSQLState

With `SQLException`:

~~~java
int vendorCode = exception.getErrorCode();
String sqlState = exception.getSQLState();
String diagnosticMessage = exception.getMessage();
~~~

- `vendorCode` is the database/driver error code, matched against the error catalog.
- `sqlState` is the 5-character SQLSTATE code.
- `diagnosticMessage` is for logs/diagnostics; never parse it to drive business logic.

### SQLException Can Be Chained or Wrapped

JDBC allows an `SQLException` to link follow-up errors via `getNextException()`. Frameworks can also wrap exceptions in higher-level exceptions. When testing raw JDBC, assert directly on the exception from `CallableStatement`. When testing through a framework, traverse the cause chain or exception translation API to locate the underlying SQL exception.

Example traversing the cause chain:

~~~java
static SQLException findSqlException(Throwable error) {
    Throwable current = error;

    while (current != null) {
        if (current instanceof SQLException sqlException) {
            return sqlException;
        }
        current = current.getCause();
    }

    return null;
}
~~~

If the driver populates `getNextException()`, traverse that chain too. Do not assume the exception always sits in the first `getCause()`.

### Do Not Assert Exception Subclasses Unnecessarily

Drivers may map SQLSTATE classes to JDBC subclasses like `SQLIntegrityConstraintViolationException` or `SQLTransactionRollbackException`. For SQLSTATE 45000, the exact exception class depends on the driver. The stable contract in this lesson is vendor code and SQLSTATE; only assert subclasses when the application intentionally relies on that mapping and pins the driver version.

### CallableStatement and Result Sets

If a procedure returns a result set before raising an error in a later statement, the driver may have already received partial results before the exception. APIs should clearly define whether a routine returns result sets or only executes commands. Tests must handle `execute()`, `getResultSet()`, and `getMoreResults()` if a procedure produces multiple result sets; never assume every CALL yields only an update count.

## 18. Managing Transactions in Tests

With caller-owned transactions:

- Start with `connection.setAutoCommit(false)`.
- Invoke the procedure on the same connection.
- Commit when the whole business operation succeeds.
- Roll back on exceptions or assertion failures.
- Restore connection state before returning it to the pool.

Never reuse a connection with an unfinished transaction for another test. In parallel tests, each test should have its own connection and isolated fixture.

### Error Tests Must Verify Post-Rollback State

A test that only asserts `SQLException` is insufficient. Verify:

1. Correct vendor error code.
2. Correct SQLSTATE.
3. Caller rollback succeeds.
4. Balances and reservations did not change unexpectedly.
5. No dangling open transaction or leaked connection remains.

### Deadlock Tests and Retries

Deadlock is a transaction-level error, not a business error like insufficient inventory. When retrying, re-run the entire transaction from the beginning with an attempt limit and backoff. Never re-run only the final statement because earlier statements may have already been rolled back with the transaction.

## 19. Versioning and Operating an Error Catalog

Error codes are part of the contract between the database and the application. When adding or modifying codes:

1. Register the new code in the error catalog.
2. Keep the meaning of already-published codes unchanged.
3. Update stored procedures and Java enums in the same release or in a backward-compatible sequence.
4. Write integration tests verifying code and SQLSTATE.
5. Document mappings to HTTP/API errors if the application has a REST layer.
6. Log error code, routine name, request/correlation ID, and transaction outcome.
7. Never log sensitive data or raw SQL strings containing user information.

If Java deploys before the database, Java must handle both old codes and newly introduced codes not yet emitted. If the database deploys before Java, routines should not emit new codes that older applications misinterpret if that breaks behavior. Use a two-phase compatible rollout when needed.

## 20. Common Mistakes

| Mistake | Consequence | Correct Approach |
|---|---|---|
| Parsing MESSAGE_TEXT | Wording changes break logic | Classify using MYSQL_ERRNO and SQLSTATE. |
| Using one code for every exception | Loses ability to distinguish validation, conflict, and infrastructure | Maintain a namespaced error catalog. |
| Changing the meaning of a published code | Old clients mishandle new errors | Never reuse codes; version the contract. |
| Swallowing exceptions inside handlers | Caller assumes routine succeeded | Use RESIGNAL when errors must reach the caller. |
| Assuming handlers roll back automatically | Data may be partially committed | Define transaction owner and roll back in the right place. |
| Asserting only that an exception occurred | Unknown which code the routine returned | Assert `getErrorCode()` and `getSQLState()`. |
| Asserting exact message strings | Tests break whenever wording is adjusted | Assert message text only if required for specific UI display. |
| Retrying every SQLException | Repeats validation errors or non-idempotent operations | Retry by error code/SQLSTATE and transaction semantics. |
| Retrying after connection loss without checking | May create duplicate transactions if commit succeeded | Use request ID and query state before retrying. |
| Testing concurrency on one connection | Fails to create real race conditions | Use at least two independent connections. |
| Checking only balance after success | Misses missing or duplicate reservation rows | Verify both row sets and total invariants. |

## 21. Error Design and Testing Workflow

1. List business and technical errors the routine can emit.
2. Categorize which errors are validation, not-found, conflict, concurrency, or infrastructure.
3. Assign stable `MYSQL_ERRNO` values and choose appropriate `SQLSTATE` values.
4. Raise business errors with `SIGNAL SQLSTATE '45000'`.
5. Use `GET DIAGNOSTICS` to read original errors inside handlers when mapping is needed.
6. Use `RESIGNAL` to preserve original errors or intentionally translate native errors.
7. Define the transaction owner; never let handlers mistakenly roll back the caller's transaction.
8. Write a Java error catalog mapping vendor codes.
9. Invoke the procedure via `CallableStatement` with explicit transaction boundaries.
10. Assert vendor code and SQLSTATE in integration tests.
11. Roll back and verify data state after failures.
12. Test success, duplicate, not-found, invalid input, insufficient inventory, and concurrency.
13. Test connection loss/deadlocks according to separate retry policies.
14. Version the catalog and deploy database/application in compatible order.

## 22. Practice Exercises

### Exercise A — Designing an Error Catalog

1. List at least five business errors for an order placement routine.
2. Assign each error a unique `MYSQL_ERRNO`.
3. Use SQLSTATE 45000 for errors proactively raised by the routine.
4. Write the corresponding Java enum.
5. Define retry behavior for each code.

### Exercise B — SIGNAL and RESIGNAL

1. Write a procedure that raises an error when quantity equals 0.
2. Use SIGNAL with code 31001.
3. Create a unique constraint so error 1062 can be triggered.
4. Use GET DIAGNOSTICS to read `MYSQL_ERRNO`.
5. Use RESIGNAL to translate 1062 into 31003.

### Exercise C — Catching Errors via JDBC

1. Call the procedure using `CallableStatement`.
2. Catch `SQLException`.
3. Assert `getErrorCode()` and `getSQLState()`.
4. Do not assert exact message text.
5. Log the error code and request ID in test logs.

### Exercise D — Transaction Rollback

1. Set `autoCommit=false`.
2. Call a procedure that executes an UPDATE before a duplicate INSERT fails.
3. Catch the exception and roll back.
4. Re-read inventory and reservations.
5. Prove no partial changes remain.

### Exercise E — Concurrency

1. Create a fixture with 5 units of inventory.
2. Open two JDBC connections.
3. Concurrently place requests for 4 units each.
4. Confirm only one transaction succeeds.
5. Confirm the other transaction receives the insufficient inventory code and the total invariant still holds.

### Exercise F — Compatibility Testing

1. Add a new error code to the routine and Java enum.
2. Run tests with older and newer application versions in staging.
3. Verify old clients do not misinterpret the unknown code.
4. Verify logs include correlation ID and error code.
5. Write migration/release notes for the error contract change.

You have completed this lesson when you can design error codes independent of message text, raise and translate errors using SIGNAL/RESIGNAL, read diagnostics, call procedures from JDBC, verify vendor codes/SQLSTATE, and prove transactions leave no partial data after failures.

## 23. Principles to Remember

- `MYSQL_ERRNO` is the right numeric code for stable business error classification; manage it like an API contract.
- `SQLSTATE` classifies error categories; `45000` is commonly used for routine-raised exceptions.
- `MESSAGE_TEXT` serves diagnostics, never as a key controlling business logic.
- Use `SIGNAL` to raise errors with explicit codes; use `RESIGNAL` to preserve or translate errors inside handlers.
- `GET DIAGNOSTICS` reads SQLSTATE, MYSQL_ERRNO, and MESSAGE_TEXT of a condition.
- Handlers do not automatically roll back transactions; clearly define whether caller or routine owns the transaction.
- With caller-owned transactions, JDBC must roll back when a procedure raises an error.
- Test via `CallableStatement` and assert both `SQLException.getErrorCode()` and `getSQLState()`.
- Never retry every `SQLException`; classify validation, conflict, deadlock, and connection failures.
- Verify data state after rollback, not just the exception itself.
- Use request IDs / idempotency keys to handle retries safely when responses are lost.
- Test concurrency with multiple connections and verify business invariants.
- Never repurpose published error codes; version the contract between stored programs and Java.

When error codes, SQLSTATE, transaction boundaries, and JDBC tests are designed as a unified contract, stored procedures can return clear and stable errors. The Java application will handle the right root cause, control retries, and prove data remains consistent after both success and failure.

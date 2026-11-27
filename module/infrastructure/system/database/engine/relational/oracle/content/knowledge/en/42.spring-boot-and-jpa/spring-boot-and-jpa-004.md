# Initializing and Resetting NLS/Application Context on Connection Reuse in Spring Boot and JPA

## 1. Why Manage Session State When Using a Connection Pool?

In a Spring Boot application, Hibernate/JPA typically borrows connections from a connection pool instead of creating a new physical connection for every request. The pool keeps open connections for reuse, reducing TCP handshake, Oracle session authentication, and driver initialization overhead.

A connection returned to the pool usually remains attached to the same Oracle session. Session-level state can persist when the next request borrows that connection, such as:

- NLS settings like `NLS_DATE_FORMAT`, `NLS_NUMERIC_CHARACTERS`, `NLS_DATE_LANGUAGE`, `NLS_SORT`.
- Application context used for VPD/row-level security.
- `CLIENT_IDENTIFIER`, `MODULE`, `ACTION` for auditing and tracing.
- `CURRENT_SCHEMA`, time zone, and isolation-related session settings.
- Package state, global temporary table state, and other session settings.

If tenant A's request sets `TENANT_ID = 10` and returns the connection to the pool without clearing context, tenant B's request may receive the exact same Oracle session. When a VPD policy reads the stale context, B might see A's data or be unexpectedly denied.

NLS state can also cause subtle bugs. One request sets a custom `NLS_DATE_FORMAT` and returns the connection to the pool; the next request may parse date or number strings under rules different from what the application expects.

Therefore, the lifecycle of a connection borrow needs three steps:

1. **Initialize:** apply the NLS baseline and set the application context matching the authenticated identity.
2. **Use:** execute all SQL/JPA work on that same connection/session.
3. **Reset:** clear the context and restore the session to baseline state before the connection is reused.

This lesson belongs to the **Database Engine Relational Oracle** module, **Spring Boot and JPA** chapter, focusing on **initializing and resetting NLS/application context on connection reuse**.

## 2. Connection, Oracle Session, and Persistence Context Are Three Distinct Concepts

Distinguish these state layers:

| Component | Lifetime Scope | Example State |
|---|---|---|
| JDBC logical connection | Duration the application borrows the connection from the pool | `close()` typically returns the connection to the pool |
| Physical connection | Network connection managed by the pool | Socket, driver state, Oracle session |
| Oracle database session | Database-side session maintained by the physical connection | NLS, application context, module/action, package state |
| JPA persistence context | `EntityManager`/transaction lifecycle per configuration | Managed entities, dirty checking, first-level cache |
| HTTP request | A single request at the web layer | Principal, tenant, correlation ID |

An HTTP request does not necessarily correspond to a new physical connection. Nor should an `EntityManager` be assumed to always mean a fresh Oracle session. The Spring transaction manager can bind one connection to a transaction so repositories and JdbcTemplate share that same connection.

### 2.1. `Connection.close()` in a Pool Does Not Necessarily Close the Oracle Session

When code calls:

```java
connection.close();
```

on a pooled connection, typically only the logical connection is closed and returned to the pool. The physical connection and Oracle session can remain alive.

That is why session state can leak into the next borrow. Rolling back a transaction or closing an `EntityManager` does not automatically restore all NLS parameters and application contexts to baseline.

### 2.2. Transaction State Differs from Session State

`COMMIT` and `ROLLBACK` end a transaction. They do not automatically clear:
- Application context set in the session.
- `ALTER SESSION` settings.
- `CLIENT_IDENTIFIER`.
- `MODULE`/`ACTION`.
- Certain package states or other session settings.

Thus, you cannot rely on `finally { connection.rollback(); }` as a complete session reset solution.

## 3. How Do NLS Settings Affect Applications?

NLS (National Language Support) controls language, formatting, and comparison rules inside an Oracle session.

Common parameters:

| Parameter | Effect |
|---|---|
| `NLS_DATE_FORMAT` | Default format when converting DATE to string and vice versa |
| `NLS_TIMESTAMP_FORMAT` | Default format for TIMESTAMP |
| `NLS_TIMESTAMP_TZ_FORMAT` | Format for TIMESTAMP WITH TIME ZONE |
| `NLS_DATE_LANGUAGE` | Month/day names and certain language rules |
| `NLS_NUMERIC_CHARACTERS` | Decimal point and grouping separator |
| `NLS_CURRENCY` | Default currency symbol |
| `NLS_TERRITORY` | Regional rules such as first day of week and default formats |
| `NLS_SORT` | String sorting rules |
| `NLS_COMP` | How NLS comparison rules are applied |

NLS can affect SQL relying on implicit conversions, `TO_CHAR`/`TO_DATE` calls without format models, string sorting/filtering, and outputs from certain APIs.

### 3.1. Example Bug Caused by NLS_DATE_FORMAT

Suppose a session has:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';
```

The following SQL is session-dependent:

```sql
SELECT *
FROM app.orders
WHERE order_date >= '04/05/2026';
```

The date string can be interpreted under different month/day orders if the session has a different NLS setting. This causes errors or wrong row sets.

Use DATE/TIMESTAMP bind parameters or explicit format models:

```sql
SELECT *
FROM app.orders
WHERE order_date >= DATE '2026-05-04';
```

If parsing a string is needed:

```sql
SELECT TO_DATE(
    '2026-05-04',
    'YYYY-MM-DD'
)
FROM dual;
```

Setting an NLS baseline provides consistent behavior for legacy SQL, but does not replace typed bind variables and explicit format models.

### 3.2. Example Bug Caused by NLS_NUMERIC_CHARACTERS

A session might use a comma as the decimal separator:

```sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';
```

If an application constructs SQL with numeric strings, the value `1234.56` may be interpreted differently depending on NLS.

Use JDBC numeric binds:

```java
preparedStatement.setBigDecimal(1, new BigDecimal("1234.56"));
```

Binding `BigDecimal` avoids converting numbers through locale-dependent SQL strings.

### 3.3. Do Not Use Display Formats as Data Contracts

NLS should be treated as session state affecting SQL and formatting, not as business data definitions. APIs should pass dates/times and numbers using typed data or invariant formats. The UI layer should format according to user locale.

## 4. Defining an Application NLS Baseline

An application should choose a consistent baseline tested against real SQL, reports, and data. Example:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';
ALTER SESSION SET NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF';
ALTER SESSION SET NLS_TIMESTAMP_TZ_FORMAT =
    'YYYY-MM-DD HH24:MI:SS.FF TZH:TZM';
ALTER SESSION SET NLS_DATE_LANGUAGE = 'AMERICAN';
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
ALTER SESSION SET NLS_SORT = 'BINARY';
ALTER SESSION SET NLS_COMP = 'BINARY';
ALTER SESSION SET TIME_ZONE = 'UTC';
```

These values are examples only. Choose time zone, language, sort, and numeric characters based on your application contract. Do not apply `NLS_SORT=BINARY` or `UTC` mechanically if business logic requires different rules.

### 4.1. The NLS Baseline Must Be Applied Consistently

If some connections use baseline A and others use baseline B, the same SQL query can yield different results depending on which connection the pool hands out. This is especially dangerous when bugs only surface sporadically under load.

A single component should manage the baseline:
- Version-controlled configuration constants.
- One service/helper executing `ALTER SESSION`.
- Tests verifying session state after initialize/reset.
- Monitoring to detect misconfigurations.

### 4.2. Only Pass Trusted Values into ALTER SESSION

Never concatenate request-supplied locales, format models, or time zones directly into SQL:

```java
// Unsafe if format comes from untrusted input.
statement.execute("ALTER SESSION SET NLS_DATE_FORMAT = '" + userValue + "'");
```

`ALTER SESSION` does not accept bind variables for all configuration clauses. Use an allowlist of values defined in application configuration and never let clients choose SQL fragments.

### 4.3. Reading Current NLS Settings

You can inspect session parameters:

```sql
SELECT parameter, value
FROM nls_session_parameters
ORDER BY parameter;
```

Compare with database defaults:

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_NUMERIC_CHARACTERS',
    'NLS_DATE_LANGUAGE',
    'NLS_SORT',
    'NLS_COMP'
)
ORDER BY parameter;
```

`NLS_SESSION_PARAMETERS` reflects the current session state. Do not assume it always matches `NLS_DATABASE_PARAMETERS` or client configuration.

## 5. Application Context and Session-Level Security

An application context is a set of attributes attached to an Oracle session, read via `SYS_CONTEXT`. Applications can use contexts to pass security or business metadata to VPD policies, auditing, and stored procedures.

Example namespace `APP_CTX`:
- `TENANT_ID`
- `APP_USER_ID`
- `REGION_ID`
- `BUSINESS_UNIT`

Reading context:

```sql
SELECT SYS_CONTEXT('APP_CTX', 'TENANT_ID') AS tenant_id,
       SYS_CONTEXT('APP_CTX', 'APP_USER_ID') AS app_user_id
FROM dual;
```

If a context is used by a VPD policy, an incorrect value or leftover value from a previous request can leak data across tenants.

### 5.1. Secure Application Context

Create a secure application context using `CREATE CONTEXT ... USING package`:

```sql
CREATE CONTEXT app_ctx USING sec.app_session_context_pkg;
```

The specified package is the trusted package authorized to set context via `DBMS_SESSION.SET_CONTEXT`.

Example package specification:

```sql
CREATE OR REPLACE PACKAGE sec.app_session_context_pkg
AUTHID DEFINER
AS
    PROCEDURE initialize_for_session;
    PROCEDURE clear_for_session;
END;
/
```

The package body must resolve identity from a trusted source before setting context. Example model where each database principal maps to a tenant:

```sql
CREATE OR REPLACE PACKAGE BODY sec.app_session_context_pkg
AS
    PROCEDURE initialize_for_session
    IS
        l_tenant_id NUMBER;
    BEGIN
        SELECT tenant_id
        INTO l_tenant_id
        FROM sec.db_principal_tenant
        WHERE db_username =
              SYS_CONTEXT('USERENV', 'SESSION_USER');

        DBMS_SESSION.SET_CONTEXT(
            'APP_CTX',
            'TENANT_ID',
            TO_CHAR(l_tenant_id)
        );
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_SESSION.CLEAR_CONTEXT('APP_CTX', NULL, NULL);
            RAISE_APPLICATION_ERROR(-20001, 'No tenant mapping');
    END initialize_for_session;

    PROCEDURE clear_for_session
    IS
    BEGIN
        DBMS_SESSION.CLEAR_CONTEXT('APP_CTX', NULL, NULL);
    END clear_for_session;
END;
/
```

This is an example for an architecture with explicitly mapped database principals. Depending on the version and context mechanism, the DBA must confirm the appropriate namespace-clearing call; the trusted package can invoke the corresponding clear-context API for all session attributes.

### 5.2. Do Not Trust Client-Supplied Tenant IDs

If all requests share one database account, `SESSION_USER` only identifies the service account. You cannot infer the end user or tenant from that value alone.

In a shared-account architecture, a trusted identity mechanism such as proxy authentication or an assertion verified at a trusted tier/package is needed. Never use `CLIENT_IDENTIFIER` or a caller-supplied `tenant_id` parameter as authorization proof if the caller can set that value arbitrarily.

A secure context restricts which package may set the context; it does not automatically prove the logic inside that package is sound.

### 5.3. Fail Closed

If identity cannot be authenticated or no tenant mapping is found:
- Do not set a fallback/assumed context.
- Clear any existing context if present.
- Raise an error and stop the request.
- VPD policies should return a predicate allowing zero rows when context is missing, such as `1=0`.

Never let a request proceed with a stale context or a default predicate allowing all data.

## 6. Why Does Connection Pooling Make Session Context Dangerous?

Suppose a pool has one physical connection:

```text
Request A (tenant 10)
    |
    v
Borrow connection C1
    |
    v
Set APP_CTX.TENANT_ID = 10
    |
    v
Query VPD-protected tables
    |
    v
Return C1 without clearing context
    |
    v
Request B (tenant 20) borrows C1
    |
    v
Context still says TENANT_ID = 10
```

If B does not set context before querying, VPD may filter data for tenant 10. If the application sets tenant context insecurely, B might accidentally or maliciously switch to another tenant.

### 6.1. Two Mandatory Principles

- **Re-initialize context on every borrow/transaction request:** never rely on values left over from a previous connection use.
- **Clear/reset before returning the connection:** ensure subsequent requests do not inherit prior security state.

Initializing every time prevents stale context if a prior cleanup failed. Clearing at completion reduces risk and surfaces bugs early. If either initialize or reset fails, the connection must not continue to be used normally.

### 6.2. NLS Also Needs Resetting

NLS settings typically do not vary by tenant, but may change per request, report, or legacy code path. If a request runs `ALTER SESSION`, restore the baseline before the connection is reused.

Do not rely on `ROLLBACK` to reset NLS. `ALTER SESSION` mutates session state.

## 7. Distinguishing connectionInitSql from Per-Borrow Reset

Some pools let you execute SQL when a new physical connection is created. In HikariCP, `connectionInitSql` runs when a new connection is created before it enters the pool.

Spring Boot configuration example:

```yaml
spring:
  datasource:
    hikari:
      connection-init-sql: >
        ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'
```

This can establish an initial baseline for physical connections. However, it **does not re-run every time a request borrows a connection from the pool**.

If a request alters NLS or application context, subsequent requests can still receive the modified session. Therefore:
- `connectionInitSql` is useful for an initial baseline.
- It does not replace checkout initialization.
- It does not replace reset when the connection is returned.
- Tenant-specific context must not be placed here because physical connections are reused across tenants.

### 7.1. Pools Do Not Automatically Reset All Oracle Session State

Pools can typically reset standard JDBC states such as auto-commit, read-only, or transaction isolation depending on implementation. Changes made via `ALTER SESSION`, `DBMS_SESSION.SET_CONTEXT`, package state, `CLIENT_IDENTIFIER`, or `DBMS_APPLICATION_INFO` are not necessarily detected and reset automatically by the pool.

Do not assume `Connection.close()` clears application context or NLS state.

### 7.2. Validation Queries Are Not Reset Hooks

A validation query such as:

```sql
SELECT 1 FROM dual
```

only checks whether the connection can execute a query. It does not reset NLS, clear context, or prove the session is clean.

## 8. Designing the Session State Lifecycle

A request using Oracle should follow this sequence:

```text
Borrow connection
      |
      v
Apply NLS baseline
      |
      v
Clear stale context and client metadata
      |
      v
Authenticate/resolve trusted application identity
      |
      v
Set secure application context
      |
      v
Execute JPA/JDBC work in same transaction connection
      |
      v
Flush pending JPA changes
      |
      v
Clear application context and request metadata
      |
      v
Restore NLS baseline
      |
      v
Return healthy connection to pool
```

If any initialization step fails, do not execute business SQL. If cleanup fails, the connection may still carry sensitive state; mark it as failed and evict/discard it from the pool.

### 8.1. Initialize Before the First Query

VPD policies may be evaluated at SQL parse or execution time depending on policy type. Context must be ready before any repository query runs.

Never initialize context after calling a repository. Never set context solely in a web controller if other services, scheduled jobs, or message consumers access the same repositories while bypassing controllers.

### 8.2. Stay on the Same Physical Connection

Context-setting commands and JPA queries must run on the same Oracle session. If context is set on connection C1 while Hibernate queries on connection C2, the policy will not see the intended context.

In a Spring-managed transaction, use the connection bound by the transaction manager to the persistence context rather than opening an independent connection via `DriverManager` or a separate `DataSource`.

### 8.3. Reset After All Business SQL Completes

With JPA, entities may be flushed to the database upon transaction commit. If context is cleared too early, late flushes or generated SQL may execute after the context is gone.

You can call `entityManager.flush()` before resetting inside a synchronous wrapper. With transaction-lifecycle management, cleanup should run after the transaction finishes but before the connection returns to the pool. Verify the exact lifecycle ordering of your transaction manager and pool implementation.

## 9. Spring Boot and HikariCP Configuration

Spring Boot typically configures the `DataSource` from `spring.datasource.*`. With HikariCP, you can configure the pool:

```yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//db-host:1521/orders_service
    username: app_runtime
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1800000
      connection-init-sql: >
        ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'
```

These numbers are examples. `connection-timeout` is the wait time to borrow a connection from the pool, not the Oracle network connect timeout. `connection-init-sql` runs at physical connection creation, not as a per-borrow hook.

Never store real passwords in committed configuration files. Use environment variables/secret providers and manage access permissions.

### 9.1. Do Not Put Tenant Application Context in connection-init-sql

Physical connections may be created at startup and reused across many requests/tenants. If init SQL binds tenant 10, every request using that session risks running under the wrong tenant.

Tenant/application context must be set per the current request/transaction's identity.

### 9.2. Do Not Use connectionTestQuery as a Substitute for Initialization

HikariCP/drivers can use JDBC `Connection.isValid()` or a validation query. Its purpose is verifying connection liveness, not scrubbing session state.

### 9.3. A Single DataSource for the Transaction

`JpaTransactionManager`, `EntityManagerFactory`, and `JdbcTemplate` must reference the same datasource to share a transaction and session. When multiple datasources are configured, specify the corresponding transaction manager and persistence unit explicitly.

## 10. Setting Context in Spring Boot/JPA via Hibernate doWork

With Hibernate, `Session.doWork()` lets you execute JDBC work on the connection currently used by Hibernate. Inside an active JPA transaction, this is an appropriate way to invoke Oracle packages on the same session.

Helper example:

```java
@Component
public class OracleSessionStateManager {

    @PersistenceContext
    private EntityManager entityManager;

    public void initializeForRequest() {
        Session session = entityManager.unwrap(Session.class);

        session.doWork(connection -> {
            applyNlsBaseline(connection);
            clearRequestState(connection);
            callTrustedContextInitializer(connection);
        });
    }

    public void resetAfterRequest() {
        Session session = entityManager.unwrap(Session.class);

        session.doWork(connection -> {
            clearRequestState(connection);
            applyNlsBaseline(connection);
        });
    }

    private void applyNlsBaseline(Connection connection)
            throws SQLException {

        try (Statement statement = connection.createStatement()) {
            statement.execute(
                "ALTER SESSION SET NLS_DATE_FORMAT = " +
                "'YYYY-MM-DD HH24:MI:SS'"
            );
            statement.execute(
                "ALTER SESSION SET NLS_TIMESTAMP_FORMAT = " +
                "'YYYY-MM-DD HH24:MI:SS.FF'"
            );
            statement.execute(
                "ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'"
            );
            statement.execute(
                "ALTER SESSION SET NLS_DATE_LANGUAGE = 'AMERICAN'"
            );
            statement.execute(
                "ALTER SESSION SET TIME_ZONE = 'UTC'"
            );
        }
    }

    private void clearRequestState(Connection connection)
            throws SQLException {

        try (CallableStatement call = connection.prepareCall(
                "{ call SEC.APP_SESSION_CONTEXT_PKG.CLEAR_FOR_SESSION }")) {
            call.execute();
        }

        try (CallableStatement call = connection.prepareCall(
                "{ call DBMS_SESSION.CLEAR_IDENTIFIER }")) {
            call.execute();
        }

        try (CallableStatement call = connection.prepareCall(
                "{ call DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL) }")) {
            call.execute();
        }
    }

    private void callTrustedContextInitializer(Connection connection)
            throws SQLException {

        try (CallableStatement call = connection.prepareCall(
                "{ call SEC.APP_SESSION_CONTEXT_PKG.INITIALIZE_FOR_SESSION }")) {
            call.execute();
        }
    }
}
```

This is an illustrative skeleton. Adjust package names, privileges, NLS baseline, and context-clearing calls according to your actual schema/version. The `INITIALIZE_FOR_SESSION` package must obtain identity from a trusted source; never pass arbitrary client-supplied tenant parameters.

### 10.1. Why Use doWork?

`doWork()` receives the connection of the current Hibernate session. As a result, `ALTER SESSION` commands and context stored procedures run on the exact same Oracle session as subsequent JPA queries in the transaction.

Do not do the following inside a JPA service:

```java
try (Connection connection = dataSource.getConnection()) {
    // Set context on this connection...
}
```

If the transaction manager/Hibernate is using a different connection, the context just set does not apply to JPA queries. Moreover, manually fetching connections makes transaction management and lifecycles unpredictable.

### 10.2. Use doReturningWork When a Result Is Needed

If you need to return a JDBC value:

```java
String tenant = session.doReturningWork(connection -> {
    try (PreparedStatement statement = connection.prepareStatement(
            "SELECT SYS_CONTEXT('APP_CTX', 'TENANT_ID') FROM dual");
         ResultSet resultSet = statement.executeQuery()) {

        return resultSet.next() ? resultSet.getString(1) : null;
    }
});
```

Use only for necessary state/diagnostic reads. Never log sensitive context values.

## 11. Wrapping Service Transactions with Initialize/Reset

Synchronous service example:

```java
@Service
public class OrderService {

    private final OracleSessionStateManager sessionStateManager;
    private final OrderRepository orderRepository;
    private final EntityManager entityManager;

    public OrderService(
            OracleSessionStateManager sessionStateManager,
            OrderRepository orderRepository,
            EntityManager entityManager) {
        this.sessionStateManager = sessionStateManager;
        this.orderRepository = orderRepository;
        this.entityManager = entityManager;
    }

    @Transactional
    public OrderSummary findOrdersForCurrentTenant() {
        sessionStateManager.initializeForRequest();

        try {
            List<Order> orders = orderRepository.findOpenOrders();

            // Ensure pending JPA changes are flushed before reset.
            entityManager.flush();

            return OrderSummary.from(orders);
        } finally {
            sessionStateManager.resetAfterRequest();
        }
    }
}
```

The example demonstrates initializing before queries and resetting in `finally`. Production implementations must handle exceptions thrown during reset: cleanup errors must be logged/recorded, the transaction must not proceed as successful if the connection might retain stale context, and the connection must be evicted from the pool using the pool's API.

If a method is read-only, `flush()` is generally unnecessary; for write transactions, flushing before reset prevents Hibernate from deferring DML until after the context has been cleared. Evaluate any queries/lazy loading triggered after the method returns; never allow database access to continue after session context has been reset.

### 11.1. Never Swallow Cleanup Exceptions

Do not write:

```java
try {
    sessionStateManager.resetAfterRequest();
} catch (Exception ignored) {
    // Unsafe: the session may still retain the old tenant context.
}
```

If reset fails, the connection could return to the pool in an indeterminate security state. Always:
- Mark the request/transaction as failed.
- Record metrics and technical logs free of secrets.
- Mark the connection for eviction.
- Use pool-specific eviction or a wrapper mechanism so the physical connection is never reused.

### 11.2. Note on Spring Proxies and @Transactional

`@Transactional` is typically applied via a Spring proxy. Calling another transactional method via self-invocation on the same object can bypass the proxy, leaving the transaction unopened as expected.

Place transaction boundaries on appropriate service beans and verify an active transaction exists before calling `Session.doWork()`.

### 11.3. Lazy Loading

If you return an entity with uninitialized lazy associations and access them after the service has reset context or the transaction has ended, generated SQL may execute outside the intended context scope.

Prefer fetching required data inside the transaction and returning DTOs/projections. Do not rely on Open Session in View to extend a session carrying unmanaged tenant context.

## 12. Using JdbcTemplate in the Same Transaction

Spring's `JdbcTemplate` uses Spring's connection management. When it and JPA share the datasource managed by `JpaTransactionManager`, operations can participate in the same transaction-bound connection per configuration.

Package invocation example:

```java
@Repository
public class OracleSessionContextDao {

    private final JdbcTemplate jdbcTemplate;

    public OracleSessionContextDao(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void initialize() {
        jdbcTemplate.execute(
            "{ call SEC.APP_SESSION_CONTEXT_PKG.INITIALIZE_FOR_SESSION }"
        );
    }

    public void clear() {
        jdbcTemplate.execute(
            "{ call SEC.APP_SESSION_CONTEXT_PKG.CLEAR_FOR_SESSION }"
        );
    }
}
```

Call the DAO inside the same `@Transactional` service before calling JPA repositories. Verify that `JdbcTemplate`, `EntityManagerFactory`, and the transaction manager actually share the same datasource.

### 12.1. Do Not Open a Separate Connection Inside the DAO

Using `DriverManager.getConnection()` or a different datasource creates a separate session and may not join the current transaction. For operations requiring the same session, use `JdbcTemplate`, `DataSourceUtils`, or Hibernate `doWork()`.

### 12.2. Choose One Consistent Access Mechanism

You can use:
- Hibernate `Session.doWork()` for session-level commands needing the current connection.
- `JdbcTemplate` for stored procedures and SQL in the same transaction.
- A DataSource wrapper to automatically reset when the logical connection returns to the pool.

Avoid mixing multiple datasources/transaction managers without clearly tracking which connection holds the context.

## 13. Resetting via Transaction Lifecycle or DataSource Wrapper

A `try/finally` block in a service is straightforward and useful when each transaction has a clear entry point. In large applications with many services, scheduled jobs, and message listeners, scattered per-method resets are easy to miss.

Management can be centralized in one of two layers:

### 13.1. Transaction Synchronization

Spring provides transaction synchronization callbacks. Cleanup can be registered to run after transaction completion, before the transaction manager releases resources according to the active configuration's lifecycle order.

Principles:
- Initialize on the connection bound to the transaction.
- Cleanup must run after JPA flush/commit or rollback completes.
- Cleanup must run before the connection is returned to the pool.
- If the callback cannot access the right connection or cleanup fails, the connection must be evicted.
- Do not register duplicate callbacks for the same transaction.

Do not copy sample callbacks without verifying the ordering of `beforeCommit`, `afterCompletion`, Hibernate connection release, and your Spring transaction manager version. Exact ordering must be tested against your actual stack.

### 13.2. DataSource/Connection Wrapper

A wrapper around the datasource can:
1. When `getConnection()` issues a logical connection, perform baseline/reset and initialize request context as designed.
2. When logical `close()` is called, run cleanup/reset before delegating back to the pool.
3. If cleanup fails, evict the physical connection rather than returning it to the pool.

The wrapper must coordinate with the transaction manager so it does not reset prematurely before transaction flush/commit. It must also distinguish checkouts for web requests, background jobs, and tenantless operations.

### 13.3. Choosing Where to Place Responsibility

| Approach | Best Fit | Risks to Manage |
|---|---|---|
| `try/finally` in service | Few entry points, clear transactions | Easy to forget in new services/jobs |
| Transaction synchronization | Coupling cleanup to transaction lifecycle | Depends on callback and connection-release ordering |
| DataSource wrapper/proxy | Centralizing all borrow/return operations | Complex with transactions, nested connections, and pools |
| Pool connectionInitSql | Only sets baseline on physical connection creation | Does not reset on each borrow |

Never treat `connectionInitSql` as if it were a checkout/return wrapper.

## 14. Background Jobs, Schedulers, and Message Consumers

HTTP requests are not the only workload needing context. Other paths also reuse pooled connections:
- `@Scheduled` jobs.
- Spring Batch.
- Kafka/RabbitMQ message listeners.
- Async executors.
- ETL workers.
- Admin/reporting tasks.

Each workload type must define its context:
- Jobs run with a dedicated service identity.
- Message tenant is authenticated from an envelope/trusted producer.
- Scheduled tasks may run cross-tenant with an approved role or iterate tenant by tenant.
- Admin jobs require a dedicated privileged identity and auditing.

Never let a background worker inherit context from a previous request merely by sharing a pool.

### 14.1. Message Context Is Not Inherently Trustworthy

A message body containing `tenantId` does not prove the sender is authorized for that tenant. Verify the producer, signature, or mapping to queue/consumer identity before invoking the context-setting package.

### 14.2. Separate Service Accounts and Workloads When Appropriate

Using separate accounts/pools for batch, reporting, and OLTP reduces blast radius and simplifies context policies. Even so, each pool still needs an initialize/reset procedure.

## 15. NLS and Application Context Across Multiple DataSources

An application may connect to multiple Oracle services or PDBs. Do not assume all datasources share the same:
- NLS baseline.
- Package/context namespace.
- Schema mapping.
- Time zone.
- VPD policy.
- Transaction manager.

Each datasource requires its own session-state configuration and a manager bound to the matching `EntityManagerFactory`/transaction manager.

Example:
- `ordersDataSource` uses `APP_CTX` and service `ORDERS`.
- `reportingDataSource` uses a read-only context/identity and service `REPORTING`.

Never run datasource A's session initializer on a connection from datasource B.

## 16. Verifying Session State in Oracle

### 16.1. Checking NLS

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_NUMERIC_CHARACTERS',
    'NLS_DATE_LANGUAGE',
    'NLS_SORT',
    'NLS_COMP'
)
ORDER BY parameter;
```

### 16.2. Checking Application Context

```sql
SELECT SYS_CONTEXT('APP_CTX', 'TENANT_ID') AS tenant_id,
       SYS_CONTEXT('APP_CTX', 'APP_USER_ID') AS app_user_id
FROM dual;
```

Right after a connection is reset, context should be empty or at the defined baseline state. Once initialized for a request, context must match the authenticated identity.

### 16.3. Checking Module/Action/Client Identifier

Session metadata can be viewed via dynamic performance views if privileged, or checked via package/application instrumentation. `CLIENT_IDENTIFIER` is useful for tying a session to a request/user in audit trails, but is not proof of authentication if callers can set it themselves.

### 16.4. Do Not Arbitrarily Log Sensitive Context

Tenant IDs or user IDs may be sensitive data under organizational policy. Log request IDs, module/action, and approved identifiers; never log raw tokens or assertions.

## 17. Testing Connection Reuse

The most important test proves that the same physical connection is reused without leaking prior request state into the next request.

### 17.1. Sequential Two-Tenant Test

With a single-connection pool:
1. Request A borrows connection C1.
2. Initialize tenant 10 context.
3. Query a VPD-protected table; see only tenant 10.
4. Reset context and NLS baseline.
5. Return C1 to the pool.
6. Request B borrows C1 again.
7. Initialize tenant 20 context.
8. Query; see only tenant 20.
9. Verify `TENANT_ID=10` is no longer present.

If a test does not guarantee both requests use the same physical connection, it can miss leakage bugs. Use pool size 1 in tests or instrument connection/session identity in the test environment.

### 17.2. Missing-Context Test

After reset, run a query on a VPD-protected table before initializing. The result must fail closed or return zero rows per the designed policy.

### 17.3. Exception and Rollback Test

- Request A sets context and throws an exception.
- Transaction rolls back.
- Cleanup still runs.
- Request B borrows the same connection again.
- A's context is gone.

### 17.4. Cleanup Failure Test

Simulate a package reset error or dropped connection during cleanup:
- The request must be marked failed.
- The connection must not return to the pool as healthy.
- The pool creates a replacement physical connection.
- The next request does not receive stale context.

### 17.5. NLS Test

Have one request intentionally change `NLS_DATE_FORMAT` or `NLS_NUMERIC_CHARACTERS`, then return the connection. The next request checks `NLS_SESSION_PARAMETERS` and must observe the standard baseline.

### 17.6. Concurrency Test

Run concurrent requests across different tenants. Each transaction must see only the context for its active connection. Never share a connection or JPA EntityManager across threads.

## 18. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Setting context only when physical connection is created | First tenant may be reused by later requests | Set per request/transaction |
| Relying on `connectionInitSql` to reset every borrow | Old session state remains intact | Implement dedicated checkout/return lifecycle |
| Assuming rollback clears NLS/context | Next request inherits state | Reset session explicitly |
| Setting context on a separate connection | JPA queries run on a different session | Use `Session.doWork()`/transaction-bound connection |
| Trusting tenant ID from HTTP body | Caller can spoof tenants | Resolve identity from a trusted source |
| Using `CLIENT_IDENTIFIER` for authorization | Caller may overwrite value | Use only for tracing/audit unless authenticated |
| Running cleanup only on the success path | Exceptions leave old context behind | Use `finally` or transaction cleanup callbacks |
| Swallowing reset errors | Sensitive connection returns to pool | Evict/discard connection |
| Resetting before JPA flush | Late DML executes without context | Flush before reset or clean up after transaction completion |
| Testing only across multiple connections | Misses session leakage | Test with pool size 1 and same physical session |
| Applying only in HTTP controllers | Jobs/message consumers bypass context | Centralize at transaction/session boundary |
| Picking arbitrary NLS baseline | Changes application semantics | Align baseline with data contract and test |
| Opening connections via DriverManager in JPA services | Outside transaction/session | Use transaction-bound connection |
| Using Open Session in View to lazy-load after reset | Queries run outside intended context | Fetch inside transaction and return DTOs |

## 19. Implementation Checklist

### NLS
- Baseline is centrally defined.
- Date, timestamp, number, and timezone formats are explicit.
- NLS settings are never concatenated from untrusted input.
- New SQL does not rely on implicit conversions.
- NLS is verified after initialize/reset.

### Application Context
- Uses a secure application context.
- Trusted package validates identity before setting attributes.
- Client-supplied arbitrary tenant IDs are never trusted.
- Context is set before the first query.
- Context is cleared when the request/transaction finishes.
- Missing context fails closed.

### Spring Boot/JPA
- `EntityManagerFactory`, transaction manager, and `JdbcTemplate` use the right datasource.
- Context is set on the connection Hibernate is using.
- Transaction boundaries are explicit.
- JPA flush completes before reset.
- Lazy loading never runs after context is cleared.
- Scheduled jobs/message consumers have dedicated context handling.

### Connection Pool
- Understands `connectionInitSql` runs only on physical connection creation.
- Resets at checkout/return or in transaction lifecycle.
- Does not assume the pool auto-clears Oracle session state.
- Cleanup failure triggers eviction.
- Faulty connections or indeterminate session state are never returned to the pool.

### Testing and Operations
- Tests two tenants on the same physical connection.
- Tests missing context and exceptions/rollbacks.
- Tests NLS leakage.
- Tests cleanup failures and eviction.
- Exposes metrics for initialize/reset failures.
- Logs contain no secrets or sensitive assertions.
- Runbook exists for handling session-state-contaminated connections.

## 20. Comprehensive Lab Exercise

This lab requires a dedicated Oracle database, test schema, Spring Boot/JPA, Oracle JDBC driver, and HikariCP. Never run DDL or alter NLS/context on a production pool for testing.

### Step 1. Create the Tenant Mapping Table

```sql
CREATE TABLE sec.db_principal_tenant (
    db_username VARCHAR2(128) PRIMARY KEY,
    tenant_id NUMBER NOT NULL
);
```

Populate mappings matching your lab database principals. If the lab uses a shared account, simulate an approved trusted identity mechanism; never take arbitrary tenants from the request.

### Step 2. Create Secure Context and Trusted Package

```sql
CREATE CONTEXT app_ctx USING sec.app_session_context_pkg;
```

Create a package with two procedures:
- `INITIALIZE_FOR_SESSION`: validates identity and sets tenant/application attributes.
- `CLEAR_FOR_SESSION`: clears all relevant context for the current session.

Grant minimal `EXECUTE` privilege to the runtime account.

### Step 3. Create Business Table and Policy

Create a table with `TENANT_ID` and a VPD policy reading `SYS_CONTEXT('APP_CTX','TENANT_ID')`. When context is null, the policy returns `1=0`.

### Step 4. Configure HikariCP

Set pool size to 1 to force two requests to reuse the same physical connection. Configure `connectionInitSql` only for the initial NLS baseline, never for tenant context.

### Step 5. Create OracleSessionStateManager

Use Hibernate `Session.doWork()` to:
- Apply the NLS baseline.
- Clear stale context/identifiers.
- Call the trusted initializer.
- Reset context and NLS upon completion.

If reset fails, flag the connection for pool eviction per the pool implementation in use.

### Step 6. Create a Transactional Service

Inside a `@Transactional` method:
1. Initialize the session.
2. Execute repository queries.
3. Verify results belong only to the current tenant.
4. Flush if DML occurred.
5. Reset before the connection returns according to the chosen lifecycle.

### Step 7. Send Two Different Tenant Requests

Execute request A followed by request B and verify the pool reuses the same connection while context switches properly. Verify `SYS_CONTEXT` and VPD query results.

### Step 8. Test the Exception Path

Cause request A to throw an exception after initialize. Verify rollback, cleanup, and that request B does not inherit A's context.

### Step 9. Test NLS

In request A, change an NLS parameter in a controlled way. After cleanup, request B reads `NLS_SESSION_PARAMETERS` and confirms the baseline.

### Step 10. Test Cleanup Failure

Simulate a package reset failure in the lab environment. Verify the connection is evicted and the pool creates a new connection.

### Step 11. Record Results

Record:
- Physical connection/session identity used per request.
- NLS before and after reset.
- Context before and after initialize/clear.
- Transaction status.
- Cleanup result.
- Number of evicted connections.
- VPD query results.

### Step 12. Clean Up Lab Objects

Drop only objects created by the lab once no longer needed. Never drop packages/contexts or policies shared by other applications.

## 21. Self-Check Questions

**Question 1.** Why can application context leak between two requests?

**Answer:** Because context is attached to the Oracle session, and the connection pool can reuse the same physical connection/session for the next request.

**Question 2.** Does `Connection.close()` always close the Oracle session?

**Answer:** No. With a pool, it typically returns the logical connection to the pool while the physical session stays open.

**Question 3.** Does rollback reset NLS?

**Answer:** No. NLS is session state and must be reset separately.

**Question 4.** When does HikariCP's `connectionInitSql` run?

**Answer:** When a new physical connection is created before being added to the pool; it does not re-run on each borrow.

**Question 5.** Why shouldn't tenant context be set in `connectionInitSql`?

**Answer:** Physical connections can be reused across multiple tenants; context must match the current request/transaction identity.

**Question 6.** How is a secure application context created?

**Answer:** Using `CREATE CONTEXT namespace USING trusted_package`; the trusted package sets attributes via `DBMS_SESSION.SET_CONTEXT`.

**Question 7.** Why shouldn't tenant ID from an HTTP body be trusted?

**Answer:** Clients can modify the value to spoof tenants and bypass data boundaries.

**Question 8.** Does `CLIENT_IDENTIFIER` replace authentication?

**Answer:** No. It is useful for auditing/tracing, but does not prove identity if callers can set it themselves.

**Question 9.** Why use Hibernate `Session.doWork()`?

**Answer:** It executes JDBC work on the current Hibernate session's connection, ensuring context commands and JPA queries share the same Oracle session.

**Question 10.** Why reset in `finally` or transaction cleanup?

**Answer:** So cleanup still runs whether the request succeeds, throws an exception, or rolls back.

**Question 11.** Why must JPA be flushed before resetting in some designs?

**Answer:** Hibernate may defer DML until flush/commit; resetting context too early can cause late SQL to run without the expected context.

**Question 12.** What happens if cleanup fails?

**Answer:** The connection may still retain sensitive state; it must be marked failed and evicted/discarded rather than returned to the pool as clean.

**Question 13.** Does a validation query reset context?

**Answer:** No. It only tests whether the connection can execute a query.

**Question 14.** Do background jobs need context?

**Answer:** Yes, if they access protected data; jobs need their own workload identity and initialize/reset workflow.

**Question 15.** Why test with pool size 1?

**Answer:** To force consecutive requests to reuse the same physical connection and uncover session-state leakage.

**Question 16.** Can one NLS baseline be used across every datasource?

**Answer:** Only if every database/service shares the same business contract; otherwise each datasource needs its own session-state configuration.

## 22. Conclusion

Connection pools reuse physical connections and Oracle sessions to cut connection overhead. That means session state can persist across multiple requests. NLS settings, application contexts, `CLIENT_IDENTIFIER`, module/action, and other session settings must be managed as part of the connection lifecycle.

Define a clear NLS baseline, use typed binds and explicit format models, and apply the baseline whenever a connection is used. Secure application contexts must be populated from verified identity by a trusted package; never trust client-supplied tenant IDs or `CLIENT_IDENTIFIER` values. Context must be set before the first query and cleared once all business SQL finishes.

In Spring Boot/JPA, context-setting statements must execute on the exact connection Hibernate uses. `Session.doWork()` or `JdbcTemplate` joining the same transaction are suitable approaches when datasources and transaction managers are configured consistently. `connectionInitSql` only runs when physical connections are created and does not replace per-borrow resets. If cleanup fails, the connection must be evicted from the pool because its security state is no longer deterministic.

Test by forcing two different tenant requests to reuse the same physical connection, verifying NLS/context before and after reset, and simulating exceptions/rollbacks and cleanup failures. Connection reuse is only safe for Spring Boot and JPA applications when a subsequent request can never inherit session state from a prior request.

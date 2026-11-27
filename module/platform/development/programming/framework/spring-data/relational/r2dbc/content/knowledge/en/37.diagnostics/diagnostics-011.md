# Checklist for Verifying Configuration, SQL, and Execution Flow Before Concluding a Bug

When a Spring Data R2DBC operation fails, the root cause can reside in any of several layers: Spring wired the wrong bean, a repository bound to the wrong template, generated SQL mismatched the schema, parameters were bound with wrong types, a publisher was never subscribed, the transaction manager does not manage the right `ConnectionFactory`, or the database/driver returned an error misinterpreted by the Service layer.

An error message at the end of a pipeline does not by itself identify the failing layer. For example, `DataAccessResourceFailureException` may originate from an unreachable database, an exhausted pool failing to grant a connection, TLS/authentication failure, or a network timeout. An empty result may be valid `Mono.empty()` behavior, a wrong predicate, missing tenant context, or a repository querying the wrong database. A write failing to roll back may be caused by the wrong transaction manager, or by detaching a publisher via `subscribe()` or turning an error into completion before the transaction boundary.

Therefore, before drawing conclusions, verify in an evidence-backed sequence: actual configuration → repository and template → final SQL → bind values and data types → subscription/reactive context → transaction/resource → database/driver behavior → reproducing test. This lesson provides a systematic diagnostic checklist, safe evidence-collection practices, and guidance to distinguish configuration errors from query or data errors.

## 1. Diagnostic Principle: Move from Evidence to Conclusion

Do not start by randomly tweaking repositories, enlarging pool sizes, or slapping on `onErrorResume`. First describe a reproducible symptom:

- Which operation fails, and with what input?
- Does the error occur at startup, on subscription, when acquiring a connection, while executing SQL, or when reading results?
- Does it affect every request or only one tenant, data type, or specific record?
- Did it appear after a configuration change, migration, driver version bump, or code release?
- Can it be reproduced on a test database of the same version?
- What is the final state of data in the database?

A technical conclusion should cite the supporting evidence. Example:

```text
Symptom:
  OrderRepository.findById(42) returns data from the billing database.

Evidence:
  - Repository belongs to package orders.repository.
  - Package is scanned by BillingR2dbcConfiguration.
  - entityOperationsRef = billingEntityTemplate.
  - billingEntityTemplate uses billingConnectionFactory.
  - Fixture ID 42 exists only in the billing database.

Conclusion:
  Repository is bound to the wrong R2dbcEntityOperations.
```

Such a conclusion can be verified and fixed accurately. Conversely, "R2DBC is broken" or "the pool is too small" is not a diagnosis.

### 1.1. Distinguishing Error Layers

| Layer | Core Question | Example Evidence |
|---|---|---|
| Spring configuration | Which beans are created and injected? | Bean names, qualifiers, condition report |
| Repository wiring | Which operations/template does the repository use? | `basePackages`, `entityOperationsRef` |
| SQL generation | What is the actual SQL executed? | SQL logs, query instrumentation |
| Parameter binding | Are bind values and types accurate? | Bind metadata, database error codes |
| Reactive execution | Is the publisher subscribed and preserving context? | `StepVerifier`, operator traces |
| Transaction | Do manager and connection resource match? | Transaction manager, rollback test |
| Database/driver | How did server and driver behave? | SQLState, vendor code, server logs |
| Data/schema | Are schema and data in the expected state? | Migration version, `information_schema`, fixtures |
| Performance | Is the bottleneck in query, pool, or database? | Query plan, latency, pool metrics |

A single request crosses multiple layers, so locate the first layer with falsified evidence rather than reacting only to the final exception.

## 2. Initial Checklist Before Changing Code

Before editing code, record:

- [ ] When the error started and which release/build is running.
- [ ] Failing endpoint, Service method, or Repository method.
- [ ] Minimal input to reproduce, with sensitive data stripped.
- [ ] Connected database product/version and environment.
- [ ] R2DBC driver, Spring Boot, Spring Data, and R2DBC SPI versions.
- [ ] Active Spring profiles and actual configuration sources.
- [ ] Bean names for `ConnectionFactory`, `R2dbcEntityOperations`, and `ReactiveTransactionManager`.
- [ ] Final SQL and database error type if SQL executed.
- [ ] Data state before and after the operation.
- [ ] Presence of transactions, retries, fallbacks, cancellation, or nested subscriptions.
- [ ] Whether it reproduces in a standalone integration test.

Never write passwords, tokens, URLs with credentials, personal info, or raw sensitive bind values into issues/logs. Use synthetic IDs, fixture data, and redacted configs.

## 3. Confirming Which Spring Configuration Is Active

Properties in a YAML file are not guaranteed to be the final resolved values. Environment variables, command-line arguments, profiles, config servers, or test overrides can replace them.

### 3.1. Confirming the Active Profile

Check startup logs and `spring.profiles.active`. Verify R2DBC properties load from the right profile. If local runs `dev` while CI runs `test`, never compare environments without knowing their configuration differences.

Example configuration:

```yaml
spring:
  profiles:
    active: dev
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/store
    username: store_app
    password: ${DB_PASSWORD}
```

In production, profiles are usually supplied by the deployment environment. Do not hardcode profiles or secrets in code just to make tests run.

### 3.2. Checking Auto-Configuration Conditions

Start Spring Boot with `--debug` to view the condition evaluation report. The report shows which auto-configurations matched, were excluded, or backed off due to specific beans/properties. This is valuable when default R2DBC beans are missing due to custom beans or missing dependencies.

If Actuator is enabled, the `conditions` and `beans` endpoints aid investigation. Secure these endpoints and expose them only per operational policy; bean metadata can reveal internal structure.

### 3.3. Confirming Actual Dependencies

After upgrading Spring Boot or drivers, inspect the dependency tree:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Or with Maven:

```bash
mvn dependency:tree
```

Look for:

- R2DBC driver for the database in use.
- R2DBC SPI.
- Spring Data Relational/R2DBC.
- Spring Framework.
- R2DBC Pool if pooling is used.
- JDBC driver if migration tools or other modules require JDBC.

Prefer Spring Boot dependency management/BOM. Do not override a core component solely because a newer version exists; verify compatibility across SPI, driver, and Spring Data.

### 3.4. Checking URLs and Connection Types

R2DBC URLs must use the driver scheme, for example:

```text
r2dbc:postgresql://host:5432/database
r2dbc:mysql://host:3306/database
```

JDBC URLs like `jdbc:postgresql://...` are not R2DBC URLs. If the application uses both JDBC and R2DBC, verify each bean uses the right URL/driver kind. Targeting the same database server does not make two connection paths a single transaction resource.

### 3.5. Do Not Print the Entire Environment or URLs with Secrets

During diagnostics, log only profile names, driver metadata, masked host/database, and bean names. Never log passwords, tokens, or URIs containing credentials. When comparing configs, create redacted copies before sharing.

## 4. Verifying Beans and Repository Groups

For a single database, auto-configuration is usually enough. With multiple databases, verify every repository is bound to the right `R2dbcEntityOperations`.

### 4.1. Listing Beans by Type

You can use a debugger breakpoint, secured Actuator, or a temporary diagnostic component:

```java
@Component
class R2dbcBeanDiagnostics implements ApplicationRunner {

    private final ApplicationContext context;

    R2dbcBeanDiagnostics(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        context.getBeansOfType(ConnectionFactory.class)
                .forEach((name, factory) ->
                        log.info("ConnectionFactory bean={} driver={}",
                                name, factory.getMetadata().getName()));

        context.getBeansOfType(R2dbcEntityOperations.class)
                .forEach((name, operations) ->
                        log.info("EntityOperations bean={} type={}",
                                name, operations.getClass().getName()));

        context.getBeansOfType(ReactiveTransactionManager.class)
                .forEach((name, manager) ->
                        log.info("Reactive transaction manager={} type={}",
                                name, manager.getClass().getName()));
    }
}
```

Ensure logger and imports match your project. Log only non-sensitive metadata. Do not log `toString()` on connection factories if implementations may include URLs or credentials.

### 4.2. Reading `@EnableR2dbcRepositories`

Check:

- Do `basePackages` or `basePackageClasses` cover the failing repository?
- Are two configurations scanning the same package?
- Which bean does `entityOperationsRef` point to?
- Which manager does `transactionManagerRef` point to?
- Should a base repository carry `@NoRepositoryBean`?
- Was `@NoRepositoryBean` accidentally placed on a concrete repository interface?

Multi-database configuration example:

```java
@Configuration
@EnableR2dbcRepositories(
        basePackages = "com.example.orders.repository",
        entityOperationsRef = "ordersEntityTemplate",
        transactionManagerRef = "ordersTransactionManager")
class OrdersR2dbcConfiguration {
}
```

The `orders` package must not simultaneously be scanned by a billing configuration using `billingEntityTemplate`.

### 4.3. Tracing Templates to ConnectionFactories

```java
@Bean
R2dbcEntityOperations ordersEntityTemplate(
        @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
    return new R2dbcEntityTemplate(factory);
}
```

Verify which factory constructs each template. A common mistake is having the template and transaction manager instantiate two separate `ConnectionFactory` objects even with the same URL. Declare the factory once and inject the same bean into both.

### 4.4. Using Qualifiers When Multiple Beans of the Same Type Exist

With multiple `ConnectionFactory` or `DatabaseClient` beans, injections require `@Qualifier` or a clear `@Primary` rule. `@Primary` only selects a default candidate; it does not assign repositories to the right group.

### 4.5. Proving Database Target with Marker Fixtures

To prove which database a repository actually queries, insert distinct marker rows in each database:

- Orders database: `ORD-MARKER-ONLY-ORDERS`.
- Billing database: `INV-MARKER-ONLY-BILLING`.

Invoke each repository and verify only its designated database's marker appears. This provides stronger execution proof than checking bean names alone.

## 5. Verifying Dialect and Mapping Metadata

Spring Data R2DBC selects a dialect based on database/driver to generate bind markers and handle SQL differences. A wrong dialect or mapping metadata can yield invalid SQL.

### 5.1. Checking the Resolved Dialect

You can verify the dialect in a diagnostic test:

```java
R2dbcDialect dialect = DialectResolver.getDialect(connectionFactory);
assertThat(dialect).isNotNull();
```

Resolving cleanly only proves the framework recognizes a dialect. It does not guarantee every vendor-specific SQL construct is supported.

### 5.2. Checking Entity Annotations

For the failing entity, inspect:

- `@Table` points to the right table/schema.
- `@Column` points to the right column name.
- `@Id` marks the right primary key.
- `@Version` has compatible type and semantics when using optimistic locking.
- `@ReadOnlyProperty`, `@InsertOnlyProperty`, `@Transient` match intended behavior.
- Constructors/persistence constructors match properties.
- Projection aliases match property names or mapping callbacks.

Example:

```java
@Table("orders")
public record OrderEntity(
        @Id Long id,
        @Column("order_code") String orderCode,
        @Column("created_at") Instant createdAt,
        @Version Long version
) {
}
```

A Java property named `createdAt` does not prove the database actually has column `created_at`; check schema and mapping together.

### 5.3. Distinguishing Entity Mapping from Projection Mapping

Queries can return full entities, interface projections, DTOs, or manually mapped rows. Their mapping mechanics differ. If an entity reads properly while a DTO has null fields, check aliases, constructor parameters, and `Row.get(...)` types before modifying the schema.

## 6. Collecting Actual SQL Before Changing Queries

A repository method name does not tell you the exact final SQL. Derived queries, query annotations, `R2dbcEntityTemplate`, and `DatabaseClient` generate SQL differently.

### 6.1. Identifying the SQL Source

Classify the operation:

- Derived repository method such as `findByStatusAndCreatedAtAfter`.
- `@Query` declaring explicit SQL.
- `R2dbcEntityTemplate` query/update DSL.
- `DatabaseClient` with manual SQL.
- Custom repository implementation.
- Bulk update/delete or stored procedure/function.

Each path has different mapping, conversion, and lifecycle behavior. Do not assume custom SQL triggers all entity callbacks the way `repository.save(entity)` does.

### 6.2. Enabling Selective Logging

In debug/test profiles, raise log levels for Spring Data R2DBC or driver packages per library version. Exact logger names and bind-logging behavior vary across versions; consult docs for your running versions.

Illustrative configuration:

```yaml
logging:
  level:
    org.springframework.data.r2dbc: DEBUG
    io.r2dbc.postgresql.QUERY: DEBUG
```

Exact loggers depend on the driver. Never enable broad bind-value logging in production if parameters carry personal info, tokens, financial data, or secrets. Prefer logging only SQL templates, query names, correlation IDs, and durations.

### 6.3. Checking SQL on the Database Server

Database servers offer query logs, statement statistics, or slow query logs. These confirm what SQL actually reached the server, execution duration, and plans. Enable selectively because query logging can generate high volume or expose sensitive data.

### 6.4. Do Not Conclude Solely from SQL Strings in Source

Source code may show `@Query`, yet the framework still processes bind markers, mapping metadata, pagination, or dialect rules. For critical queries, capture actual SQL or test on the target database to verify semantics.

## 7. Checklist for Checking SQL and Bind Parameters

When SQL errors or returns wrong data, check in order:

### 7.1. Tables, Schemas, and Columns

- [ ] Table exists in the right database/schema.
- [ ] Column names match the real schema.
- [ ] Case sensitivity/identifier quoting fits the database.
- [ ] `SELECT` aliases match projections.
- [ ] Migrations ran against the right database.
- [ ] Search path/default schema does not route queries to another table.

### 7.2. Predicates and Semantics

- [ ] Tenant/authorization predicates are included.
- [ ] `AND`/`OR` precedence is grouped properly with parentheses.
- [ ] Null semantics are accurate (`IS NULL` instead of `= NULL`).
- [ ] Date/time ranges use right inclusive/exclusive boundaries.
- [ ] Collation/case sensitivity matches requirements.
- [ ] Empty collections have defined behavior.
- [ ] Sorts include tie-breakers for stable paging.
- [ ] Count queries count distinct logical entities across joins/groups.

### 7.3. Bind Markers and Parameter Types

- [ ] Bind marker names/positions match the API/driver.
- [ ] Parameter count matches the SQL statement.
- [ ] Positional bind order is right.
- [ ] Nulls use `bindNull(name, type)` where required by the API.
- [ ] Java types are compatible with SQL types.
- [ ] Decimal precision/scale is preserved.
- [ ] Timestamps/offsets/time zones convert properly.
- [ ] UUID, JSON, arrays, and enums have matching codecs/converters.
- [ ] Large lists stay within bind parameter limits.

Typed null binding example:

```java
databaseClient.sql("""
        SELECT id
        FROM customers
        WHERE optional_code IS NOT DISTINCT FROM :code
        """)
        .bindNull("code", String.class)
        .map((row, metadata) -> row.get("id", Long.class))
        .all();
```

`IS NOT DISTINCT FROM` is PostgreSQL-supported syntax; other engines may need an equivalent expression. This example emphasizes typed null binding, not universal syntax.

### 7.4. Generated Values and Defaults

- [ ] Does the driver return database-generated IDs?
- [ ] Do `DEFAULT` columns get overwritten by explicit `NULL` inserts?
- [ ] Is the application trying to write generated columns?
- [ ] Do triggers modify values after insert/update?
- [ ] Do immutable entities use the instance returned by `save`?
- [ ] If the driver does not return generated fields, is the entity re-read?

Never assume Java `null` causes the database to apply a column `DEFAULT`. When a column is included in `INSERT` and bound as `NULL`, the database normally stores null or rejects it per constraints.

## 8. Comparing SQL Against Real Schema and Data

When SQL is valid yet returns unexpected results, check schema and data rather than guessing query edits.

### 8.1. Verifying Schema Version

If using Flyway/Liquibase or another migration tool, confirm applied versions on the target database. Migrations passing locally do not prove production or test containers ran them.

Check:

- Migration history table.
- Schemas/tables created in the target database.
- Column types, nullability, and defaults.
- Primary keys, foreign keys, and unique/check constraints.
- Indexes and generated/identity configurations.
- Triggers/functions if present.

### 8.2. Checking Data Before and After Operations

For write operations, capture relevant state before calling the service, then re-read via an independent query afterward. This distinguishes:

- No write command executed.
- Write command failed.
- Write succeeded, yet response mapping failed.
- Write committed partially.
- Transaction rolled back properly, yet the test read from a cache or another snapshot connection.

Do not rely solely on returned Java objects to verify database state. With immutable entities or generated fields, the returned object and stored row can diverge if the driver does not populate every field.

### 8.3. Using Natural-Key Fixtures

Create easily identifiable fixtures like `ORD-DIAG-001` or `customer@example.test`. Avoid assuming identity ID is always `1`. Include both matching and non-matching rows to expose overly broad or missing predicates.

### 8.4. Verifying Tenant Isolation

Create two tenants with parallel data. Run tenant A's query and assert zero tenant B rows appear. If using tenant Reactor Context or PostgreSQL RLS, verify both context propagation in the app and database policy enforcement inside transactions.

## 9. Verifying Reactive Execution and Subscriptions

R2DBC APIs return `Mono`/`Flux`; creating a publisher does not mean SQL ran. SQL executes upon subscription.

### 9.1. Confirming Publishers Are Subscribed

Incorrect example:

```java
public Mono<Void> createCustomer(CustomerEntity customer) {
    customerRepository.save(customer);
    return Mono.empty();
}
```

The `save` publisher is built yet never composed into the returned result, so no write executes along this path.

Correct example:

```java
public Mono<Void> createCustomer(CustomerEntity customer) {
    return customerRepository.save(customer).then();
}
```

### 9.2. Avoid Nested Subscriptions

Incorrect example:

```java
public Mono<Void> placeOrder(OrderEntity order) {
    orderRepository.save(order).subscribe();
    return Mono.empty();
}
```

The independent subscription exits the caller-managed pipeline. Errors, cancellation, transactions, and Reactor Context can detach from the main flow.

Compose publishers:

```java
public Mono<Void> placeOrder(OrderEntity order) {
    return orderRepository.save(order).then();
}
```

### 9.3. Avoid `block` in Reactive Services

`block()` stalls threads and disrupts context/transaction propagation. Never use it in reactive controllers/services. In tests, prefer `StepVerifier`; if imperative setup needs `.block()`, invoke it only on regular test threads, never on event-loop threads.

### 9.4. Verifying Whether Errors Propagate or Get Swallowed

Operators like `onErrorResume` and `onErrorReturn` convert error signals into completions or fallback values. If a write fails yet an operator turns the error into a fallback object, the caller may assume the write succeeded.

Check operator chains before transaction boundaries and response generation. Only fall back when a valid business fallback exists; preserve errors when rollback or failure reporting is required.

### 9.5. Verifying Reactor Context

When services need tenant, actor, or correlation IDs, read them via `deferContextual` at subscription time. Verify `contextWrite` placement; it supplies context to upstream operators.

Do not assume every subscription starts in WebFlux. Schedulers, message consumers, and tests may need to populate context explicitly. If tenant context is missing, fail closed with a clear error rather than querying without a tenant predicate.

## 10. Verifying Transaction Managers and Resources

When an operation fails to roll back or commits partially, verify the manager and connection factory before changing business logic.

### 10.1. Confirming the Right Transaction Manager Type

R2DBC needs `ReactiveTransactionManager`, normally `R2dbcTransactionManager`. `DataSourceTransactionManager` and `JpaTransactionManager` manage JDBC/JPA resources, not R2DBC connections.

### 10.2. Confirming the Same `ConnectionFactory`

Repositories/templates and the transaction manager must reference the same `ConnectionFactory` bean. Two factories sharing a URL yet backed by different pools/instances may not share transaction resources.

### 10.3. Specifying the Manager When Multiple Managers Exist

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<OrderEntity> createOrder(OrderEntity order) {
    return orderRepository.save(order);
}
```

If using `TransactionalOperator`, build it from the right reactive manager:

```java
TransactionalOperator operator =
        TransactionalOperator.create(ordersTransactionManager);

return orderRepository.save(order).as(operator::transactional);
```

### 10.4. Transaction Boundary Checklist

- [ ] Transactional method returns `Mono`/`Flux`, and that publisher reaches the caller.
- [ ] No `subscribe()` or `block()` spawns a separate execution.
- [ ] Repositories share the transaction manager's `ConnectionFactory`.
- [ ] No operator swallows errors before the transaction completes.
- [ ] Operations requiring atomicity actually target the same database/resource.
- [ ] Tests inspect final state through an independent connection/transaction.

### 10.5. Inducing Controlled Failures to Prove Rollback

An integration test should:

1. Start a transaction.
2. Execute a valid write.
3. Deliberately trigger an error in the next step.
4. Confirm the publisher emits the error.
5. Re-read data from an independent transaction.
6. Confirm the first write rolled back.

Seeing an exception alone does not prove rollback. Final database state is the proof.

### 10.6. Do Not Assume One Transaction Spans Multiple Databases

One `R2dbcTransactionManager` manages one `ConnectionFactory`. If a service writes to an orders database and a billing database, the orders transaction does not roll back billing. Decide explicitly whether you need sagas, outbox, compensation, or a supported distributed transaction mechanism.

## 11. Checking Pools, Timeouts, and Connectivity

When errors happen before the database executes SQL, inspect connection acquisition and pooling.

### 11.1. Distinguishing Acquire Timeouts from Query Timeouts

- **Acquire timeout:** application waited too long to borrow a connection from the pool.
- **Connect timeout:** failed to establish a connection to the server.
- **Statement/query timeout:** SQL was sent yet did not complete within the limit.
- **Lock timeout:** query waited too long for a lock.

These timeouts have distinct causes and fixes. Never raise every timeout blindly at once.

### 11.2. Observing Pool Metrics

Track:

- Active/allocated connections.
- Idle connections.
- Pending borrowers.
- Acquire latency and timeout counts.
- Connection creation/validation failures.
- Connection hold durations inside transactions.

If pending borrowers rise while database query latency stays low, connections may be held too long or the pool may be too small. If database CPU/locks are saturated, enlarging the pool can worsen performance.

### 11.3. Checking Connection Leaks and Cancellation

Discarded publishers, nested subscriptions, or unconsumed streams can hold resources longer than expected. Verify connections close/return to the pool on complete, error, and cancel. For LOBs or large result streams, confirm cancellation cleanup with your specific driver.

### 11.4. Checking TLS and Authentication

If connections fail to open, verify hostname, port, DNS, certificate chains, TLS mode, authentication method, and credential rotation. Never disable certificate verification to "see if it works" in production. Use dedicated test configs and proper certificates.

## 12. Reading Exceptions and Database Error Codes

Spring exceptions wrap driver errors. For deep diagnostics, capture:

- Spring exception type.
- Cause chain.
- SQLState or vendor error code when provided by the driver.
- Constraint/table/column name if safe to log.
- Query name or operation name.
- Correlation/trace ID.

Do not build business logic on error message text when stable error codes exist. Messages can change across driver versions or server locales.

### 12.1. Common Error Groups

| Group | Examples | Where to Check |
|---|---|---|
| Connection | refused, reset, timeout | Network, DNS, TLS, credentials, pool |
| Syntax | syntax error, missing relation/column | Final SQL, dialect, schema version |
| Constraint | unique, foreign key, check, not-null | Fixtures, race conditions, constraint semantics |
| Conversion | cannot decode/bind type | Java/SQL types, codecs, converters |
| Transaction | deadlock, serialization failure | Isolation, lock order, retry policy |
| Resource | too many connections, pool acquire timeout | Pool metrics, concurrency, transaction duration |
| Cancellation | statement cancelled, subscriber cancelled | Timeout/cancel paths, driver cleanup |

### 12.2. Preserving Cause When Translating Errors

When translating persistence exceptions to domain exceptions, retain the cause:

```java
return repository.save(entity)
        .onErrorMap(DuplicateKeyException.class,
                error -> new CustomerConflictException(
                        entity.email(), error));
```

Do not drop the cause when SQLState or vendor codes are needed for investigation. At the same time, never expose internal database details directly to clients.

## 13. Checking Query Plans and Performance

If a query returns right results slowly, do not blame R2DBC merely because the API is reactive. The database still parses, plans, scans, joins, sorts, and reads rows.

### 13.1. Running `EXPLAIN` on the Target Database

With PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_code, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

Inspect actual rows, estimated rows, buffers, sort spills, join strategies, and timings. `EXPLAIN ANALYZE` executes the query; run it only on safe queries and appropriate data/environments.

### 13.2. Do Not Force Every Query onto Indexes

Sequential scans can be appropriate on small tables or low-selectivity predicates. Evaluate costs and workloads rather than asserting a fixed scan type.

### 13.3. Detecting N+1 Queries

Count queries executed per use case. Fetching 100 orders and calling a repository per order to fetch customers scales query counts with row count. Use joins/projections or batch lookups where suitable.

### 13.4. Separating Slow Queries from Pool Waiting

Measure connection acquire time, SQL execution time, and mapping/streaming time separately. A slow request may wait in the pool before the query even starts; looking only at total HTTP latency hides that distinction.

## 14. Reproducing with the Smallest Integration Test

Once you have a hypothesis, write a minimal test on the target database. Use small, deterministic fixtures proving one specific layer.

### 14.1. Testing Repositories with `StepVerifier`

```java
@Test
void findsOrderByCode() {
    StepVerifier.create(orderRepository.findByOrderCode("ORD-DIAG-001"))
            .assertNext(order -> {
                assertThat(order.orderCode()).isEqualTo("ORD-DIAG-001");
                assertThat(order.status()).isEqualTo("PAID");
            })
            .verifyComplete();
}
```

This test requires the schema/fixture in a real database or Testcontainers. It verifies query and mapping at the repository layer.

### 14.2. Testing Empty vs Error

```java
StepVerifier.create(customerRepository.findById(999999L))
        .verifyComplete();
```

When a repository finds no matching record, `Mono.empty()` completes normally. Do not confuse this with a connection error. If the Service turns empty into not-found, test the Service's `switchIfEmpty` separately.

### 14.3. Testing Null Binding and Data Types

Create nullable columns and test explicit null binding, then test `DEFAULT` via inserts omitting the column. Separate tests distinguish mapping errors from database semantics.

### 14.4. Testing Transaction Rollback

Create a transactional service, deliberately fail a later step, and re-read state from an independent transaction. Do not mock the repository alone, as mocks cannot verify database rollback.

### 14.5. Testing Multiple Repository Groups

With multiple databases, seed distinct marker fixtures in each database. Call each repository and confirm it sees only its assigned database's marker. This catches misconfigured `entityOperationsRef` or package scanning.

## 15. Gathering Production Evidence Safely

In production, gather enough information to diagnose without leaking data or overloading the system.

### 15.1. Attaching Correlation IDs

Log correlation/trace IDs alongside operation names to connect logs across WebFilters, Services, repositories, and downstream calls. Never use correlation IDs as identities or auth tokens.

### 15.2. Logging Operation Metadata Instead of Payloads

Log:

- Repository/query name.
- Logical database group/bean name.
- Duration and row count.
- Exception class, SQLState/vendor code if safe.
- Correlation/trace ID.
- Tenant ID only if permitted by policy, optionally hashed/pseudonymized.

Avoid logging raw SQL parameters containing PII, secrets, or financial data. To debug a specific value, use synthetic fixtures or redacted values.

### 15.3. Enabling Diagnostic Logging for Limited Windows

SQL/driver debug logs can be huge. Enable selectively, for short windows, on a single instance or staging environment first. Record start/stop times and verify logs contain no secrets.

### 15.4. Do Not Run Heavy Diagnostic Queries During Peak Traffic

`EXPLAIN ANALYZE`, full table counts, or table-wide data checks can strain production. Use replicas/staging or narrowed scopes when possible. Assess impact before running in production.

## 16. Quick Symptom Decision Table

| Symptom | First Check | Required Evidence |
|---|---|---|
| `ApplicationContext` fails to start | Beans, profiles, dependencies, condition report | Missing/ambiguous bean and config source |
| Repository not created | Package scan and repository factory | Base packages, `entityOperationsRef` |
| Query hits wrong database | Template → `ConnectionFactory` | Bean chain and marker fixtures |
| SQL reports missing table/column | Schema version and actual SQL | Migration history, schema metadata |
| Query returns too many/few rows | Predicates, tenant, joins, null semantics | Fixtures with matching and non-matching rows |
| Projection has null fields | Aliases, constructors, conversions | SQL result metadata and DTO mapping |
| Wrong null/default values | Explicit `NULL` vs omitted column | Insert SQL and stored row state |
| Publisher does not write data | Subscription and composition | No nested or missing subscriptions |
| Transaction does not roll back | Manager, factory, pipeline | Rollback test and final state |
| One database commits partially | Multiple factories/managers | Resource boundaries and transaction design |
| Pool acquire timeout | Pool metrics and connection lifecycle | Active/pending/acquire latency |
| Slow query | Query plan and phase timings | `EXPLAIN`, DB metrics, acquire time |
| Fails only in CI | Profiles, dependencies, database images | Version/configuration diff |

## 17. End-to-End Diagnostic Procedure

Use this sequence for an incident or bug report:

1. Record symptom, minimal input, release, and start time.
2. Classify whether the failure occurs at startup, connection, SQL execution, mapping, transaction, or response.
3. Confirm active profiles, property sources, redacted database URLs, and dependency versions.
4. List `ConnectionFactory`, `R2dbcEntityOperations`, and `ReactiveTransactionManager` beans.
5. Trace from repository package through `@EnableR2dbcRepositories` and `entityOperationsRef` to template/factory.
6. Confirm the transaction manager shares the factory and is selected properly.
7. Capture final SQL, bind markers, and parameter types safely.
8. Verify table/column names, schema version, constraints, defaults, and generated columns.
9. Confirm publishers are subscribed, free of nested subscriptions, and retain context.
10. For transactions, induce a controlled error and read final state from an independent connection.
11. Inspect driver/database error codes, pool metrics, timeouts, and query plans as symptoms warrant.
12. Create a minimal reproducing integration test on the target database.
13. Fix the first layer with falsified evidence; avoid editing multiple layers at once.
14. Run relevant tests and verify the symptom disappears under identical conditions.
15. Document conclusion, root cause, evidence, impact scope, and prevention measures.

## 18. Investigation Summary Template

A concise, verifiable report can follow this template:

```text
Symptom:
  Describe the observed failure and minimal request.

Environment:
  Spring Boot / Spring Data / driver / R2DBC SPI
  Database product + version
  Active profile (without secrets)

Evidence:
  Repository package and operations bean
  ConnectionFactory logical name/driver metadata
  Selected transaction manager
  SQL/query name and SQLState/vendor code
  Schema/migration version
  Test results or final database state

Root cause:
  Failing layer and specific reason.

Fix:
  Minimal change and why it fixes the cause.

Verification:
  Before/after reproducing test
  Relevant integration/transaction/performance checks

Residual risk:
  Unverified conditions or uncovered scope.
```

Never mark an issue "fixed" just because one manual request succeeded. Repeat tests under identical conditions and verify final state.

## 19. Premature Conclusions to Avoid

### "R2DBC Does Not Support Transactions"

First verify the reactive transaction manager, shared `ConnectionFactory`, un-detached publishers, and database support for required transaction semantics.

### "The Repository Is Buggy"

Check which template created the repository, what final SQL ran, and what bind values the driver received.

### "The Database Has No Data"

Verify database/schema, tenant predicates, active profile, and marker fixtures before concluding.

### "The Pool Is Too Small Because Queries Time Out"

Distinguish acquire timeout, connect timeout, statement timeout, and lock wait. Inspect metrics before resizing pools.

### "Publishers Don't Run Because of WebFlux"

Check subscriptions, operator composition, cancellation, and nested `subscribe` calls. Reactive means publishers do not execute merely upon construction.

### "Adding `onErrorResume` Fixes the Error"

Fallbacks can mask the true error, cause unexpected transaction commits, or return bogus data. Use them only for valid recovery policies.

### "Mock Tests Passed So the SQL Is Valid"

Mocks do not execute against a database. Run integration tests on the target engine/driver to verify SQL and mapping.

## 20. Pre-Conclusion Verification Checklist

- [ ] Reproduced failure with minimal input and know the exact failure stage.
- [ ] Confirmed active profile and resolved configuration, not just YAML files.
- [ ] Confirmed database product/version and driver/framework versions.
- [ ] Inspected condition report and created persistence beans.
- [ ] Identified which package scan covers the repository.
- [ ] Traced `entityOperationsRef` to template and `ConnectionFactory`.
- [ ] Confirmed the transaction manager uses the same `ConnectionFactory` where needed.
- [ ] Captured final SQL or equivalent evidence.
- [ ] Checked bind markers, parameter types, null handling, and collections.
- [ ] Verified SQL against real schema/migrations/constraints.
- [ ] Confirmed publisher subscription and absence of detached `subscribe()`/`block()`.
- [ ] Checked Reactor Context/tenant/actor if queries depend on them.
- [ ] Checked whether errors are swallowed/fallback-handled before transaction boundaries.
- [ ] Verified database state after both success and failure.
- [ ] Distinguished pool acquire, connect, statement, and lock timeouts.
- [ ] Inspected driver/database error codes and query plans if applicable.
- [ ] Built a minimal reproducing integration test on the target database.
- [ ] Fixed the first layer with falsified evidence and re-ran relevant tests.
- [ ] Documented root cause, evidence, and unverified boundaries.

Effective Spring Data R2DBC diagnostics is a process of verifying each system boundary. Confirm Spring creates the right beans, repositories use the right templates, templates and transaction managers share the right connection factories, SQL and bind values align with the schema, and publishers execute inside the intended context—before blaming the database or driver. Backed by a reproducing integration test and final database state as proof, fixes become precise and avoid unnecessary collateral changes.

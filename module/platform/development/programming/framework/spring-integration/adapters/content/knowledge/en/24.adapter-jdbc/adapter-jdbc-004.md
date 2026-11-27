# JDBC Outbound Stored Procedure Adapter in Spring Integration

## 1. Problem Statement: Receiving a Message and Executing a Write Procedure

An integration application receives an `order.paid` event from Kafka, JMS, AMQP, or HTTP. Instead of letting the application run multiple `INSERT`/`UPDATE` statements directly against the ERP schema, the database only grants permission to call a stored procedure `apply_order_status`. Upon receiving an event, the flow must extract order details from the `Message<?>`, bind them to the stored procedure parameters, and **execute a side effect in the database**.

The **JDBC outbound stored procedure adapter** is the one-way Spring Integration endpoint for this job. When a message arrives on its input `MessageChannel`, the adapter calls the stored procedure over JDBC; it **does not send procedure results as a reply message**. The handler class is `StoredProcMessageHandler`, and the JDBC invocation uses `StoredProcExecutor`, built on Spring JDBC `SimpleJdbcCall`.

This article belongs to the **Adapter JDBC** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`, covering sources/targets such as files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. Beyond configuration syntax, what matters most are the **message → procedure parameter → transaction** boundaries, error handling, and connection lifecycle.

~~~mermaid
flowchart LR
    A["Kafka / JMS / HTTP / File"] --> B["Validate + transform"]
    B --> C["Message<ChangeStatus>"]
    C --> D["orderStatusCommands"]
    D --> E["StoredProcMessageHandler"]
    E --> F["StoredProcExecutor"]
    F --> G["SimpleJdbcCall / JDBC"]
    G -->|"EXEC procedure"| H[("Relational DB")]
    G -.->|"SQL/transaction error"| I["Error handling / retry / DLQ"]
~~~

**Outbound** means calling **out to the database** from the message flow, not making an external HTTP call. **Channel adapter** means one-way: `RETURN`, `OUT`, or `ResultSet` outputs from the procedure may be read internally by JDBC, but `StoredProcMessageHandler` **discards them** in its messaging contract. If downstream needs to act on those results, choose the **stored procedure outbound gateway**.

## 2. Comparing Four JDBC/Stored Procedure Options

| Component | Who triggers it? | Primary behavior | Reply to the flow? |
|---|---|---|---|
| JDBC inbound channel adapter | Poller | `SELECT` reads rows, emits messages | No request-reply |
| Stored procedure inbound channel adapter | Poller | Calls procedure/function on schedule, emits results | No request-reply |
| **Stored procedure outbound channel adapter** | **Message on input channel** | **Calls procedure to mutate data** | **No** |
| Stored procedure outbound gateway | Message on request channel | Calls procedure and returns OUT/return/result set to flow | **Yes** |
| JDBC outbound DML adapter | Message on input channel | Runs `INSERT`, `UPDATE`, `DELETE` directly | No |

Choose the outbound stored procedure adapter when the application **does not need to inspect results** to decide the next step, or when success is defined as **the procedure completing without error inside the appropriate transaction**. If business logic needs the updated row count, a domain error code in an `OUT` parameter, a generated ID, or a result set to route messages, do not expect this adapter to return a reply.

**Stored procedures and SQL functions differ:** `StoredProcMessageHandler` is designed to **call procedures for update purposes**. Per Spring Integration's API, this handler **does not support calling SQL functions**; when you need a function or business-meaningful output parameters, use `StoredProcOutboundGateway`.

## 3. Message Processing Flow

~~~mermaid
sequenceDiagram
    participant Producer as Message producer
    participant Ch as DirectChannel
    participant Handler as StoredProcMessageHandler
    participant Exec as StoredProcExecutor
    participant DB as Database
    Producer->>Ch: send(Message<ChangeStatus>)
    Ch->>Handler: handleMessage
    Handler->>Exec: executeStoredProcedure(message)
    Exec->>DB: CALL procedure(IN parameters)
    alt Procedure succeeds
        DB-->>Exec: Complete / OUT data (if any)
        Exec-->>Handler: Result map
        Note over Handler: Adapter discards result map, creates no reply
        Handler-->>Ch: Return
        Ch-->>Producer: send() returns
    else JDBC or procedure error
        DB-->>Exec: SQLException
        Exec-->>Handler: DataAccessException or related exception
        Handler-->>Producer: Exception per channel mechanics
    end
~~~

The sequence above illustrates `DirectChannel`, which dispatches synchronously on the sender's thread. With `ExecutorChannel` or `QueueChannel` and a poller, processing occurs on another worker/thread or at a later time; a successful `send()` **does not guarantee** the database has committed. Even with `DirectChannel`, an **outer transaction** may only commit after `send()` returns.

## 4. End-to-End SQL Server Example: Applying Order Status

The example uses **Microsoft SQL Server** so the procedure definition has concrete syntax and can be tested on a real DB. PostgreSQL, Oracle, MySQL, and others support stored procedures with different syntax/drivers; **do not** run the T-SQL below verbatim on H2 or PostgreSQL.

### 4.1. Creating the Business Table and Deduplication Table

~~~sql
CREATE TABLE dbo.order_state (
    order_id      VARCHAR(64) NOT NULL PRIMARY KEY,
    status        VARCHAR(32) NOT NULL,
    updated_at    DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

CREATE TABLE dbo.processed_order_event (
    event_id      VARCHAR(64) NOT NULL PRIMARY KEY,
    order_id      VARCHAR(64) NOT NULL,
    new_status    VARCHAR(32) NOT NULL,
    processed_at  DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

INSERT INTO dbo.order_state (order_id, status)
VALUES ('ORD-1001', 'RECEIVED');
GO
~~~

`processed_order_event.event_id` serves as the **idempotency key**: the same event redelivered by a broker can be recognized. An event ID reused with different data must raise a conflict, **not** be treated as a successful duplicate.

### 4.2. Procedure Updating in the Same Transaction as the Idempotency Record

~~~sql
CREATE OR ALTER PROCEDURE dbo.apply_order_status
    @order_id    VARCHAR(64),
    @new_status  VARCHAR(32),
    @event_id    VARCHAR(64)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        DECLARE @old_order_id VARCHAR(64);
        DECLARE @old_status   VARCHAR(32);

        SELECT
            @old_order_id = order_id,
            @old_status = new_status
        FROM dbo.processed_order_event WITH (UPDLOCK, HOLDLOCK)
        WHERE event_id = @event_id;

        IF @old_order_id IS NOT NULL
        BEGIN
            IF @old_order_id <> @order_id OR @old_status <> @new_status
                THROW 51001, 'event_id reused with different data', 1;

            -- Same event + same data: do not overwrite status again.
            COMMIT TRANSACTION;
            RETURN;
        END;

        UPDATE dbo.order_state
        SET status = @new_status,
            updated_at = SYSUTCDATETIME()
        WHERE order_id = @order_id;

        IF @@ROWCOUNT <> 1
            THROW 51002, 'Order not found', 1;

        INSERT INTO dbo.processed_order_event (
            event_id, order_id, new_status
        ) VALUES (
            @event_id, @order_id, @new_status
        );

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO
~~~

**What this procedure guarantees within the example's scope:** it updates `order_state` and writes `processed_order_event` within the same DB transaction; receiving the exact same `event_id` + data again will not re-apply the update. The primary key combined with `UPDLOCK, HOLDLOCK` coordinates concurrent requests contending on the same key.

**What it does not yet guarantee:** a `PAID` event arriving after `SHIPPED` could still regress status if they carry two different event IDs. Production systems must validate **allowed state transitions, ordering/versioning, and event-source authorization**. Depending on how it is invoked, the procedure has an internal transaction and may join an outer Spring JDBC transaction: nested transaction/rollback semantics depend on the DB and must be tested.

A manual invocation using a SQL Server client:

~~~sql
EXEC dbo.apply_order_status
    @order_id = 'ORD-1001',
    @new_status = 'PAID',
    @event_id = 'evt-order-1001-paid-v1';

SELECT * FROM dbo.order_state WHERE order_id = 'ORD-1001';
SELECT * FROM dbo.processed_order_event
WHERE event_id = 'evt-order-1001-paid-v1';
~~~

Expect `order_state.status = 'PAID'` and **one** `processed_order_event` row. Calling `EXEC` again with the exact same parameters creates no second record. If you change `@new_status` while keeping `@event_id`, the procedure throws an error.

## 5. Dependencies and DataSource Configuration

With Spring Boot and Spring Integration JDBC:

~~~groovy
// build.gradle - dependencies section
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'
    runtimeOnly 'com.microsoft.sqlserver:mssql-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Do not pin arbitrary library versions when the Spring Boot BOM already manages them; avoid mixing incompatible Spring Framework/Spring Integration versions.

~~~yaml
# application.yml example; real environments use a secret manager
spring:
  datasource:
    url: "jdbc:sqlserver://db.internal.example:1433;databaseName=integration;encrypt=true"
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"
~~~

This is an illustrative address, not an immediately reachable database. You need a test SQL Server, schema, and `EXECUTE` permission on the procedure. For real connections, configure **TLS certificate trust/hostname validation** properly for the environment; do not disable certificate validation to silence errors.

### 5.1. API Notes Between Spring Integration 6.x and 7.x

| Version | Recommended implementation |
|---|---|
| **7.0 and later** | Java DSL `Jdbc.storedProcOutboundAdapter(dataSource)`, `JdbcStoredProcOutboundChannelAdapterSpec`, and `StoredProcExecutorSpec` |
| **6.x** | `StoredProcExecutor` + `StoredProcMessageHandler` wired with `@ServiceActivator` or XML namespace |
| **7.x manual wiring** | `StoredProcMessageHandler` resides in `org.springframework.integration.jdbc.outbound` |
| **6.x manual wiring** | `StoredProcMessageHandler` resides in `org.springframework.integration.jdbc` |

The JDBC module's Java DSL factory was introduced in **7.0**. Accordingly, section 6 examples target 7.x; section 8 demonstrates 6.x usage. Do not copy imports from both versions into the same class.

## 6. Java DSL 7.x: Configuring the Outbound Stored Procedure Adapter

### 6.1. Defining Payload and Channel

~~~java
package com.example.orders;

public record ChangeStatus(String orderId, String newStatus) {
}
~~~

In the flow, `eventId` is placed in a **message header** as the idempotency key. The example intentionally separates the business payload from delivery metadata.

### 6.2. Configuring IntegrationFlow

~~~java
package com.example.orders;

import java.sql.Types;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;
import org.springframework.integration.jdbc.storedproc.ProcedureParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderStatusProcedureFlow {

    @Bean
    public MessageChannel orderStatusCommands() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow callStatusProcedure(
            DataSource dataSource,
            @Qualifier("orderStatusCommands") MessageChannel commands) {

        return IntegrationFlow.from(commands)
            .handle(Jdbc.storedProcOutboundAdapter(dataSource)
                .configurerStoredProcExecutor(executor -> executor
                    .storedProcedureName("apply_order_status")
                    .ignoreColumnMetaData(true)
                    .sqlParameter(new SqlParameter(
                        "order_id", Types.VARCHAR))
                    .sqlParameter(new SqlParameter(
                        "new_status", Types.VARCHAR))
                    .sqlParameter(new SqlParameter(
                        "event_id", Types.VARCHAR))
                    .procedureParameter(new ProcedureParameter(
                        "order_id", null, "payload.orderId"))
                    .procedureParameter(new ProcedureParameter(
                        "new_status", null, "payload.newStatus"))
                    .procedureParameter(new ProcedureParameter(
                        "event_id", null, "headers['eventId']"))))
            .get();
    }
}
~~~

**Explanation:**

1. `IntegrationFlow.from(commands)` creates a flow triggered by messages sent to `DirectChannel`; this is **not** an inbound poller.
2. `Jdbc.storedProcOutboundAdapter(dataSource)` builds an endpoint backed by `StoredProcMessageHandler`; it runs the procedure **one-way**.
3. `configurerStoredProcExecutor(...)` configures `StoredProcExecutor` via the DSL spec. The procedure name is **static**, never read from untrusted input.
4. `ignoreColumnMetaData(true)` disables automatic JDBC parameter metadata discovery. Consequently, the example declares every `SqlParameter` with its name and SQL type.
5. `ProcedureParameter(name, null, expression)` defines a parameter resolved via **SpEL**, rather than a static value. For outbound adapters, SpEL can access the **entire message**.
6. `payload.orderId` and `payload.newStatus` read from the Java record; `headers['eventId']` reads from the source header. All three are bound as **SQL values**, never concatenated into SQL strings.
7. There is no `.channel("reply")` after the adapter: `StoredProcMessageHandler` discards the return map and does not emit `OUT`/result sets as reply messages.

Regarding the SQL Server schema, `apply_order_status` has the full name `dbo.apply_order_status`. The Java example uses the short name assuming the JDBC account resolves the right schema; otherwise, configure schema/default schema compatible with `SimpleJdbcCall` or deploy the procedure in the appropriate schema. Test against real SQL Server to avoid “Could not find stored procedure” errors.

### 6.3. Sending Messages

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class OrderStatusPublisher {

    private final MessageChannel commands;

    public OrderStatusPublisher(
            @Qualifier("orderStatusCommands") MessageChannel commands) {
        this.commands = commands;
    }

    public void markPaid(String orderId, String eventId) {
        boolean accepted = commands.send(
            MessageBuilder
                .withPayload(new ChangeStatus(orderId, "PAID"))
                .setHeader("eventId", eventId)
                .build());
        if (!accepted) {
            throw new IllegalStateException(
                "orderStatusCommands did not accept the message");
        }
    }
}
~~~

Invocation:

~~~java
publisher.markPaid("ORD-1001", "evt-order-1001-paid-v1");
~~~

When `DirectChannel` uses a synchronous handler without an outer transaction, JDBC errors normally propagate back to the thread calling `send()`; meanwhile, `send() == true` only indicates the handler did not fail per the dispatch contract, **not a receipt containing OUT parameter values**. If there is an outer transaction, commit may happen later.

## 7. Parameter Binding: Default, SpEL, and SqlParameterSourceFactory

Stored procedure components use `StoredProcExecutor` and Spring JDBC `SimpleJdbcCall`. Parameter values can be mapped automatically from the payload or declared explicitly.

| Mechanism | Data source | When to use |
|---|---|---|
| **Default**, no `ProcedureParameter` declared | Bean properties of payload, or map keys as supported by version | Simple procedures with matching input names |
| `ProcedureParameter` with `value` | Fixed static value | Fixed tenant/execution channel config values |
| `ProcedureParameter` with `expression` | SpEL accessing payload, headers, message info | Mismatched field names, needing correlation/event IDs |
| `SqlParameter`/`SqlOutParameter` | Explicit SQL type and IN/OUT direction | Unreliable or complex JDBC metadata |
| Custom `SqlParameterSourceFactory` | Custom mapping rules | Special data/type conversions, covered by tests |

### 7.1. Default Does Not Always Use SpEL

When **no** `ProcedureParameter` is supplied, `StoredProcExecutor` defaults to `BeanPropertySqlParameterSourceFactory` using the **payload** as the parameter source. If bean property names match procedure parameter names in metadata, configuration may only need the procedure name.

Spring Integration documentation warns that Spring JDBC `CallMetaDataContext` may lowercase parameter names when matching. Thus a camelCase bean property such as `lastName` might fail to match. If you encounter this, use **explicit `ProcedureParameter`** with SpEL or a tested mapping instead of assuming every DTO field matches automatically.

When explicit `ProcedureParameter` entries are configured, the executor defaults to using the **entire `Message`** as the expression source, granting access to both `payload` and `headers`. When none are declared, the default is the **payload**. This difference is why the section 6 DSL snippet can use `headers['eventId']`.

### 7.2. Example of Static and Expression Parameters

~~~java
// DSL fragment inside configurerStoredProcExecutor:
.procedureParameter(
    new ProcedureParameter("source_system", "SPRING_INTEGRATION", null))
.procedureParameter(
    new ProcedureParameter("order_id", null, "payload.orderId"))
.procedureParameter(
    new ProcedureParameter("event_id", null, "headers['eventId']"))
~~~

Note: in the main example, the procedure **does not have** a `source_system` parameter, so this snippet only illustrates syntax. To use it for real, add the corresponding parameter to the procedure and declare its `SqlParameter` when `ignoreColumnMetaData(true)` is enabled.

### 7.3. OUT/INOUT and Result Sets

Stored procedures can have `IN`, `OUT`, `INOUT`, return codes, and result sets. Parameter names/types/directions must match the driver and database. You can declare `SqlOutParameter`/`SqlInOutParameter` and result-set `RowMapper`s on `StoredProcExecutor`.

**However, with the outbound channel adapter, results are still ignored by `StoredProcMessageHandler`.** If you need OUT values to drive business transactions, send replies, or write to another system, **use the outbound gateway**. Do not try adding `.channel("results")` after the adapter expecting to receive a map that the endpoint never emits.

### 7.4. Avoid Selecting Procedure Names from Untrusted Messages

`StoredProcExecutor` supports dynamic routine names via SpEL and caches `SimpleJdbcCall` by name. While useful for trusted routers, this is **not SQL parameter binding**: choosing routine names dynamically can make the application invoke the wrong stored procedure or unintentionally expand DB privileges.

Prefer a fixed list of procedures, mapping business command types to approved names, a DB account with minimal `EXECUTE` rights, and a bounded cache size. Never read `headers['procedureName']` directly from a webhook.

## 8. Spring Integration 6.x: StoredProcExecutor and StoredProcMessageHandler

In 6.x, the 7.x Java DSL factory `Jdbc.storedProcOutboundAdapter(...)` **does not exist yet**. You can create a `StoredProcExecutor` and attach `StoredProcMessageHandler` with `@ServiceActivator`.

~~~java
package com.example.orders;

import java.sql.Types;
import java.util.List;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.jdbc.StoredProcExecutor;
import org.springframework.integration.jdbc.StoredProcMessageHandler;
import org.springframework.integration.jdbc.storedproc.ProcedureParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.messaging.MessageHandler;

@Configuration
public class LegacyProcedureAdapterConfiguration {

    @Bean
    public StoredProcExecutor statusExecutor6(DataSource dataSource) {
        StoredProcExecutor executor = new StoredProcExecutor(dataSource);
        executor.setStoredProcedureName("apply_order_status");
        executor.setIgnoreColumnMetaData(true);
        executor.setSqlParameters(List.of(
            new SqlParameter("order_id", Types.VARCHAR),
            new SqlParameter("new_status", Types.VARCHAR),
            new SqlParameter("event_id", Types.VARCHAR)));
        executor.setProcedureParameters(List.of(
            new ProcedureParameter("order_id", null, "payload.orderId"),
            new ProcedureParameter("new_status", null, "payload.newStatus"),
            new ProcedureParameter("event_id", null, "headers['eventId']")));
        return executor;
    }

    @Bean
    @ServiceActivator(inputChannel = "legacyStatusCommands")
    public MessageHandler statusHandler6(StoredProcExecutor statusExecutor6) {
        return new StoredProcMessageHandler(statusExecutor6);
    }
}
~~~

In this configuration, `StoredProcExecutor` is a Spring bean so the container manages initialization, including the `afterPropertiesSet()` lifecycle callback. There is no need to invoke that callback manually here; only when constructing objects manually **outside** the Spring container must you explicitly ensure full initialization.

**7.x projects:** if wiring manually instead of using DSL, the package of `StoredProcMessageHandler` is `org.springframework.integration.jdbc.outbound`, not `org.springframework.integration.jdbc` as in 6.x. Always use imports matching your active dependency version.

### 8.1. XML Configuration Is Another Option

~~~xml
<!-- Fragment; requires int and int-jdbc namespaces declared in Spring XML. -->
<int:channel id="xmlStatusCommands"/>

<int-jdbc:stored-proc-outbound-channel-adapter
    id="orderStatusProcedureAdapter"
    data-source="dataSource"
    channel="xmlStatusCommands"
    stored-procedure-name="apply_order_status"
    ignore-column-meta-data="true">

    <int-jdbc:sql-parameter-definition
        name="order_id" direction="IN" type="VARCHAR"/>
    <int-jdbc:sql-parameter-definition
        name="new_status" direction="IN" type="VARCHAR"/>
    <int-jdbc:sql-parameter-definition
        name="event_id" direction="IN" type="VARCHAR"/>

    <int-jdbc:parameter name="order_id"
        expression="payload.orderId"/>
    <int-jdbc:parameter name="new_status"
        expression="payload.newStatus"/>
    <int-jdbc:parameter name="event_id"
        expression="headers['eventId']"/>
</int-jdbc:stored-proc-outbound-channel-adapter>
~~~

This is an **alternative** to Java DSL and 6.x Java beans, not something to enable concurrently. If all three endpoints listen to the same message via different channels, you may invoke the procedure multiple times.

**Pollers in XML:** when an endpoint consumes from a `SubscribableChannel` like `DirectChannel`, it is an event-driven consumer and needs no poller. If it consumes from a `PollableChannel` like `QueueChannel`, the framework uses a `PollingConsumer` and an appropriate poller must be declared. The name “outbound adapter” does **not** mean it actively polls the database.

## 9. Channels Determine Threads, Transactions, and Errors

| Input channel | How handler receives messages | Consequences for transactions and latency |
|---|---|---|
| `DirectChannel` | Subscriber runs synchronously on caller thread | Can participate in the sender's active Spring transaction |
| `ExecutorChannel` | Submitted to a task executor | Different thread; does not carry the sender's thread-bound transaction |
| `QueueChannel` + poller | Message queued, then consumed by polling consumer | Needs a transaction on the poller/handler and clear ACK boundaries |
| Broker inbound adapter → channel | Per the broker's listener container/adapter | Must design ACK/offset commit timing and redelivery handling |

~~~mermaid
flowchart TD
    A["Message producer"] --> B{"Channel type"}
    B -->|"DirectChannel"| C["Same thread: JDBC handler"]
    B -->|"ExecutorChannel"| D["Worker thread: JDBC handler"]
    B -->|"QueueChannel"| E["Poller thread: JDBC handler"]
    C --> F["Transaction can be shared with caller"]
    D --> G["Different transaction boundary"]
    E --> G
~~~

**JDBC is blocking I/O.** An application with a WebFlux endpoint should not invoke a JDBC stored procedure directly on the Reactor Netty event loop and assume it is non-blocking. If called from reactive HTTP, use a bounded worker/executor with controlled concurrency, or enqueue messages to a broker/queue and return `202 Accepted` per your API contract. Switching schedulers does not turn JDBC into R2DBC; the database still requires a connection pool and transactions.

## 10. Transactions: What Does a Successful Call Mean?

### 10.1. DirectChannel and Spring Transactions

Example of a service marked `@Transactional`:

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderStatusCommandService {

    private final MessageChannel commands;

    public OrderStatusCommandService(
            @Qualifier("orderStatusCommands") MessageChannel commands) {
        this.commands = commands;
    }

    @Transactional
    public void acceptStatus(
            String orderId, String newStatus, String eventId) {

        boolean sent = commands.send(
            MessageBuilder
                .withPayload(new ChangeStatus(orderId, newStatus))
                .setHeader("eventId", eventId)
                .build());

        if (!sent) {
            throw new IllegalStateException("No subscriber");
        }
        // Outer transaction commits after the method completes.
    }
}
~~~

With `DirectChannel`, no async boundary, and the same `DataSourceTransactionManager`, the JDBC call can participate in the caller's Spring transaction. **`@Transactional` only takes effect if the method is invoked through the Spring proxy/transaction interceptor**. If the procedure also runs its own `BEGIN TRANSACTION/COMMIT` as in the SQL Server example, how nested transactions interact with Spring transactions must be tested; do not assume a “procedure commit” is always independent of an outer transaction.

When the sender observes `send()` returning true, that **does not prove the outer transaction has committed**. If subsequent code throws an exception triggering rollback, the DB update may roll back according to actual transaction semantics.

### 10.2. Executor/Queue and Kafka/JMS Sources

When switching to `ExecutorChannel` or `QueueChannel`, the producer's active transaction generally does not propagate to the worker thread. With Kafka/JMS listeners, you must choose the ACK/commit point:

- ACK **before** JDBC commit: the application can lose work on crash.
- ACK **after** JDBC commit: the message can be redelivered if a crash happens before ACK.
- With redelivery, the procedure/idempotency record ensures repeated commands cause no duplicate side effects.

A local JDBC transaction **does not** automatically create an atomic transaction with Kafka, JMS, SFTP, or HTTP. If you need to publish an event after DB commit, consider a transactional outbox; you still must handle possible duplicate sends by the publisher.

## 11. OUT Parameters, Return Values, and When You Need a Gateway

`StoredProcExecutor.executeStoredProcedure(message)` can return a `Map<String, Object>` containing `OUT` parameters, return codes, and result sets. However, `StoredProcMessageHandler.handleMessageInternal(...)` executes the procedure and **ignores return values**, at most logging at debug level.

Example procedure meant to return a business code:

~~~sql
-- SQL Server extension idea, does not replace the section 4 procedure:
CREATE OR ALTER PROCEDURE dbo.check_order_state
    @order_id VARCHAR(64),
    @current_status VARCHAR(32) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT @current_status = status
    FROM dbo.order_state
    WHERE order_id = @order_id;
END;
GO
~~~

With a one-way adapter, `@current_status` **does not become a reply message**. So that downstream handlers can route based on `current_status`, choose the **stored procedure outbound gateway** and declare the corresponding `SqlOutParameter`:

~~~java
// Spring Integration 7.x - DSL fragment illustrating a gateway
.handle(Jdbc.storedProcOutboundGateway(dataSource)
    .configurerStoredProcExecutor(executor -> executor
        .storedProcedureName("check_order_state")
        .ignoreColumnMetaData(true)
        .sqlParameter(new SqlParameter("order_id", Types.VARCHAR))
        .sqlParameter(new SqlOutParameter(
            "current_status", Types.VARCHAR))
        .procedureParameter(new ProcedureParameter(
            "order_id", null, "payload.orderId"))))
~~~

This is a DSL fragment; a real Java file needs imports for `Jdbc`, `SqlParameter`, `SqlOutParameter`, `ProcedureParameter`, `Types`, and flow classes. The gateway has a reply contract, while **payload shape** may be a map or single element depending on gateway/executor configuration and the database. Verify with an integration test before casting.

**Likewise, SQL functions:** `StoredProcMessageHandler` does not call functions; use the stored procedure outbound gateway if you want to call a function or receive a return value. Do not just set `isFunction(true)` on an outbound adapter and expect it to work.

## 12. SQL Errors, Retries, and Idempotency

Spring JDBC usually translates `SQLException`s into subtypes of `DataAccessException`; Spring Integration may wrap errors further depending on the endpoint/channel. Different error classes require different handling policies:

| Category | Example | Retry? | Action |
|---|---|---|---|
| Temporary connection loss | Network, connection pool/DB outage | Conditional | Backoff, cap retries, monitor, and retry the entire unit of work |
| Deadlock/serialization | Transient concurrency failure | Conditional | Roll back, then retry the entire transaction |
| Missing procedure/bad EXECUTE privilege | Invalid object, permission denied | No | Fix migration/privileges/configuration |
| Parameter name/type mismatch | Metadata, conversion failure | No | Fix SQL/DTO contract |
| Reused event ID with different data | Procedure `THROW 51001` | No | Conflict; record for investigation |
| Order not found | Procedure `THROW 51002` | Domain-dependent, usually no | Report not-found or route to DLQ |
| Query/lock timeout | JDBC timeout or driver exception | Conditional | Review DB and transactions, determine outcome |
| Duplicate event with identical data | Procedure returns normally | No retry needed | Idempotency success per contract |

**A connection error or timeout does not prove the DB did not commit.** For example, the client may lose connection after the procedure commits but before receiving the response. When resending the same `eventId`, the procedure must reliably detect the duplicate. Without an idempotency table, retries can overwrite status incorrectly, increment counters, or write duplicate audit rows.

### 12.1. Avoiding Multi-Layer Retry Amplification

A system might retry at:

1. JDBC advice/service layer.
2. Kafka/JMS listener or poller.
3. Outbox/DLQ replay scheduler.
4. External client resending the same business command.

If each layer retries multiple times, total procedure invocations can amplify rapidly. Pick clear retry boundaries, cap attempts, apply backoff/jitter, and terminate with a dead-letter/reconciliation path. A `DuplicateKeyException` or static parameter mismatch must never be retried infinitely.

### 12.2. Do Not Swallow Exceptions and Wrongly ACK

~~~java
// Bad: data may not be persisted while upstream treats it as successful.
try {
    commands.send(message);
} catch (Exception error) {
    log.warn("DB error ignored", error);
}

// Right approach: classify errors and route to retry/DLQ per contract.
// Only ACK the source after the outcome is persisted/reconciled properly.
~~~

The code is an illustrative snippet; `commands`, `message`, and `log` must be provided in a real application. With asynchronous channels, the caller may also **not receive an exception at `send` time**, so the error flow must be attached to the worker/endpoint in the right place.

## 13. Stored Procedure Security and Trust Boundaries

1. **Least privilege:** grant `EXECUTE` only on required routines; do not grant DDL privileges or read/write access to all tables unnecessarily.
2. **Parameterization:** bind values with `ProcedureParameter`/JDBC; never concatenate input into SQL inside the procedure. Internal dynamic SQL must also be parameterized and allowlist-checked.
3. **Fixed routine names:** do not let untrusted message headers pick the procedure; if dynamic routing is needed, map through a predefined allowlist.
4. **Data validation:** validate `orderId`, `newStatus`, and `eventId` before calling; the procedure also validates state/duplicates in the DB.
5. **Tenant authorization:** a client-supplied `tenantId` header does not prove the caller is authorized to update that tenant.
6. **Credentials/TLS:** use a secret manager and verify DB certificates; avoid logging JDBC URLs with passwords or sensitive bind parameters.
7. **Error sanitization:** SQL errors can leak table/schema names, constraints, or data; never return raw stack traces to public HTTP APIs.

## 14. Performance: Pools, Locks, and Load Shaping

Each stored procedure call uses a connection from the `DataSource` pool. Procedures hold transactions and locks, so a slow procedure can tie up connections and cause backlogs in Kafka/JMS/queues.

| Metric | What it indicates |
|---|---|
| JDBC pool active/idle/pending | Whether connections are being exhausted |
| Procedure call latency p50/p95/p99 | Whether database and procedure logic are slowing down |
| Lock waits, deadlocks, transaction duration | Level of contention and rollback risk |
| Message ingress/processing rate | Whether ingress outpaces write capacity |
| Queue depth, listener lag, redeliveries | Backlog and recovery health |
| Unique/idempotent duplicates | Whether retries/duplicates are spiking |
| Failed messages / DLQ / pending outbox | Work requiring reconciliation or durable retry |

**Do not increase concurrency indefinitely** just to chase higher throughput. If the procedure updates a hot table, more threads will contend on locks and degrade performance. Measure throughput, bound executors/queues, tune indexes and transaction length, and choose batching/chunking when compatible with the DB contract.

### 14.1. DataSource Connection Timeout vs. Query Timeout

Waiting to acquire a connection from the pool is distinct from `CallableStatement` execution time and waiting on database locks. Configure timeouts at each layer and set a sensible business deadline. A timeout exception does not prove a transaction rolled back if the connection dropped around commit time with an ambiguous outcome.

### 14.2. Procedure Name Cache

`StoredProcExecutor` caches `SimpleJdbcCallOperations` by procedure name; by default the number of cached instances is bounded and configurable via `jdbcCallOperationsCacheSize`. If using dynamic routine names, bound distinct names to avoid resource growth and unintended routine invocations. With a fixed procedure as in the example, configuration is simpler and easier to observe.

## 15. End-to-End Testing with a Real Database

H2 or JDBC mocks do not always faithfully reproduce `CallableStatement`, metadata, OUT parameters, locks, and SQL Server `THROW`. For the T-SQL example, use a **SQL Server test instance or Testcontainers SQL Server** (respecting environment configuration/licensing), rather than extrapolating from H2.

### 15.1. Integration Test for Stored Procedure Side Effects

Assuming the test app has initialized the schema/procedure and configured the beans from section 6:

~~~java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest
class StoredProcedureAdapterTest {

    @Autowired
    @Qualifier("orderStatusCommands")
    MessageChannel commands;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void appliesEventOnlyOnce() {
        String orderId = "ORD-" + UUID.randomUUID();
        String eventId = "evt-" + UUID.randomUUID();

        jdbc.update(
            "INSERT INTO dbo.order_state (order_id, status) "
                + "VALUES (?, ?)",
            orderId, "RECEIVED");

        var message = MessageBuilder
            .withPayload(new ChangeStatus(orderId, "PAID"))
            .setHeader("eventId", eventId)
            .build();

        commands.send(message);
        commands.send(message); // Duplicate delivery with the same eventId.

        String actual = jdbc.queryForObject(
            "SELECT status FROM dbo.order_state WHERE order_id = ?",
            String.class, orderId);
        Integer processed = jdbc.queryForObject(
            "SELECT COUNT(*) FROM dbo.processed_order_event "
                + "WHERE event_id = ?",
            Integer.class, eventId);

        assertEquals("PAID", actual);
        assertEquals(1, processed);
    }
}
~~~

The test relies on a **synchronous `DirectChannel`** with no test-level `@Transactional` rollback; if switched to `ExecutorChannel`/`QueueChannel`, wait for asynchronous completion using an appropriate test synchronization mechanism before querying the DB. This test checks the **committed side effect per the test configuration**, not the existence of a reply message — outbound adapters have no reply.

### 15.2. Test Matrix

| Scenario | What to verify |
|---|---|
| Valid event | DB status updated, one event record |
| Resend same eventId and payload | No duplicated side effect |
| Same eventId, different payload | Procedure signals conflict |
| Order does not exist | Procedure errors, transaction rolls back |
| Wrong parameter name/type | Metadata/binding exception, not silently ignored |
| Stored procedure missing | Configuration error, no infinite retry |
| DB connection lost | Error flow, bounded retry, and no improper ACK |
| Crash after DB commit before broker ACK | Redelivery creates no duplicate side effect |
| DirectChannel → ExecutorChannel | Thread boundary, transactions, and test timing change |
| Stored procedure returns OUT/result set | Adapter emits no reply |
| Gateway receives OUT/result set | Reply payload matches gateway contract |
| Multiple events arrive out of order | Business version/state transition does not regress |

### 15.3. Testing Complex Transaction Scenarios

In production settings, test both cases where Spring `@Transactional` wraps the adapter call and the procedure executes its own `BEGIN TRANSACTION`. In SQL Server, nested transaction commit/rollback has specific semantics; do not draw conclusions solely from seeing a `COMMIT` statement inside the procedure. Test errors after `send()`, outer rollbacks, lock timeouts, and disconnects near commit time to understand **uncertain outcomes** and reconciliation.

## 16. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| “Outbound stored procedure adapter polls the database itself” | It **receives messages** from a channel; a poller is only used when the input is a `PollableChannel` |
| “StoredProcMessageHandler sends OUT params to a reply channel” | The handler **discards** return values; use a gateway when a reply is needed |
| “Having a stored procedure means using `isFunction(true)`” | Procedures differ from functions; the adapter does not support SQL functions |
| “`Jdbc.storedProcOutboundAdapter` exists in all 6.x releases” | The Java DSL JDBC factory starts in 7.0 |
| “camelCase records always bind automatically via JDBC metadata” | Metadata may lowercase names; use explicit `ProcedureParameter` |
| “Declared `ProcedureParameter` but SpEL cannot see headers” | When using expressions, know that the parameter source is the whole message |
| “`send() == true` confirms commit in every flow” | Depends on channel type and transactions |
| “A JDBC transaction automatically commits Kafka/JMS too” | Requires separate outbox/ACK/idempotency design |
| “Retrying a POST-like procedure after a timeout is always harmless” | The DB may already have committed; idempotency keys must be enforced |
| “Adding more executor threads always increases throughput” | DB locks/pool often become the bottleneck |
| “JDBC inside a WebFlux app is non-blocking” | JDBC is blocking I/O |
| “Duplicate event ID always means identical data” | Must check and raise conflict if data differs |

## 17. Practice Exercises

1. Set up a test SQL Server, create `order_state`, `processed_order_event`, and `apply_order_status`. Call `EXEC` directly to verify transactions/idempotency.
2. Write a Spring Integration 7.x flow with `Jdbc.storedProcOutboundAdapter`, passing `orderId/newStatus` from payload and `eventId` from header.
3. Remove `ProcedureParameter` and test automatic binding. Observe camelCase field names, SQL metadata, and explain the difference.
4. Enable `ignoreColumnMetaData(true)` then omit one `SqlParameter`. Observe how the driver/`SimpleJdbcCall` responds.
5. Port the same flow to Spring Integration 6.x using `StoredProcExecutor` + `StoredProcMessageHandler`; compare imports with 7.x.
6. Write an XML configuration for the outbound stored procedure adapter and explain why there is no poller with `DirectChannel`.
7. Add an OUT parameter `old_status` to the procedure; confirm the adapter emits no reply. Switch to a stored procedure outbound gateway to receive the result.
8. Send the message twice with the same eventId and identical data; verify only one event is recorded.
9. Resend the same eventId with a different newStatus; verify the exception and transaction rollback.
10. Switch `DirectChannel` to `ExecutorChannel`/`QueueChannel` and trace threads, transaction boundaries, and ACK timing.
11. Simulate deadlocks, DB outages, and query timeouts; classify retryable vs. non-retryable errors and add backoff with bounded attempts.
12. Add a Kafka/JMS source and simulate a crash after DB commit before ACK; demonstrate that idempotency preserves correct state.
13. Build a transactional outbox to emit `order.status.changed` events after commit; handle redelivery if the publisher crashes.
14. Generate two out-of-order status transition events; add a version/optimistic check in the procedure to prevent backward transitions.

**Comprehensive scenario:** Kafka delivers an `order.paid` event, Spring Integration calls a stored procedure, the database commits successfully, but the JDBC connection drops before the client receives the response; the broker will redeliver. Explain how the procedure recognizes the same event, how to handle the uncertain outcome, where ACK/commit happens, when the next event should be published, and why the outbound adapter is not the right API if downstream needs an `OUT` return code.

## 18. References

- [Spring Integration — Stored Procedures](https://docs.spring.io/spring-integration/reference/jdbc/stored-procedures.html): outbound stored procedure adapters/gateways, parameter sources, metadata, and XML.
- [Spring Integration — Java DSL for JDBC Components](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): JDBC Java DSL from 7.0, `Jdbc.storedProcOutboundAdapter`, and component specs.
- [Spring Integration API — JdbcStoredProcOutboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/JdbcStoredProcOutboundChannelAdapterSpec.html): `configurerStoredProcExecutor` and handler spec.
- [Spring Integration API — StoredProcExecutorSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/StoredProcExecutorSpec.html): `sqlParameter`, `procedureParameter`, procedure name, and metadata.
- [Spring Integration API — StoredProcMessageHandler 7.x](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/outbound/StoredProcMessageHandler.html): one-way behavior, ignored return values, and function support limitations.
- [Spring Integration API — StoredProcExecutor 6.x](https://docs.spring.io/spring-integration/docs/6.5.0-SNAPSHOT/api/org/springframework/integration/jdbc/StoredProcExecutor.html): execution with `Message<?>`, parameter sources, and lifecycle.
- [Spring Framework — SimpleJdbcCall](https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html): stored procedure metadata, IN/OUT parameters, and JDBC support.
- [Spring Framework — Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): proxies, transaction boundaries, commit, and rollback.

> **Remember:** The JDBC outbound stored procedure adapter is **a `MessageHandler` that invokes a procedure for side effects**, not a polling source, and **does not return a business result reply**. To use it correctly, safely bind payload/headers to parameters, choose APIs matching Spring Integration 6.x/7.x, and understand transactions, errors, retries, idempotency, and source ACKs. If you need `OUT` parameters, result sets, or SQL functions, use the **stored procedure outbound gateway**.

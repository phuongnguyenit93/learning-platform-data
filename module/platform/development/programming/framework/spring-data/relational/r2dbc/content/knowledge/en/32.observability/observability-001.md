# Logging SQL and Parameters by Environment

## 1. Purpose of SQL Logging

When a repository operation fails or runs slowly, service-layer logs are sometimes not enough to find the root cause. Developers need to know which SQL statement was sent to the database, how long the operation took, what error the driver returned, and which request triggered that query.

In Spring Data R2DBC, it is important to distinguish between different types of information:

- **SQL statement:** the statement sent to the database, usually still containing bind markers.
- **Bind parameter:** the actual values bound to the markers, such as an ID, status, or timestamp.
- **Execution metadata:** execution duration, number of affected rows, completion or error status.
- **Request context:** trace ID, correlation ID, tenant alias, or business code to correlate logs.
- **Database error:** exception type, SQL state, and vendor error code if provided by the driver.

Not every logger can capture all of these types of information. Spring can log SQL statements at the DEBUG level; logging bind values usually requires driver-specific instrumentation or a proxy. Logging configuration must match the environment because SQL and parameters may contain sensitive data.

## 2. How SQL Logging and Parameter Logging Differ

Suppose the application runs:

```java
databaseClient.sql("""
        SELECT id, email_address
        FROM customer
        WHERE email_address = :email
        """)
        .bind("email", email)
        .fetch()
        .one();
```

An SQL log might display:

```text
Executing SQL statement [
    SELECT id, email_address
    FROM customer
    WHERE email_address = ?
]
```

This log shows the SQL statement and the markers used by the driver. It does not necessarily show the actual email value.

Parameter logging might record additional details such as:

```text
parameter[0]: type=String, value=lan@example.com
```

Bind values can help reproduce data-related issues, but they can also contain email addresses, phone numbers, street addresses, tokens, or financial information. Parameter logging should not be broadly enabled in production.

SQL logs with markers are useful for finding syntax errors and inspecting query shapes. Parameter logs must be managed like application data, with appropriate access control, retention, and masking policies.

## 3. Spring Framework SQL Loggers

Spring Framework `DatabaseClient` logs SQL statements at the DEBUG level through the R2DBC core logging package. You can enable the logger:

```yaml
logging:
  level:
    org.springframework.r2dbc.core: DEBUG
```

When the logger is enabled, the logs usually show the SQL statement being executed. The specific logger class name may vary by implementation/version, but the `org.springframework.r2dbc.core` package is the appropriate configuration point for Spring `DatabaseClient` SQL logs.

You can also enable the Spring Data logger when you need to observe repository/mapping activity:

```yaml
logging:
  level:
    org.springframework.data.r2dbc: DEBUG
```

The Spring Data logger helps diagnose activity at the Spring Data layer. Do not assume that enabling this logger will log every bind value or all SQL executed by the driver.

### 3.1. Do Not Enable TRACE by Default

Some libraries and drivers emit more detailed logs at TRACE. The TRACE level can generate a very large volume of logs, especially when the application runs many queries or maintains many connections.

Only enable TRACE for a short period after identifying the exact logger you need to inspect. Before enabling it, check whether that logger might output parameters, payloads, or sensitive connection details.

### 3.2. Spring Has No Single Flag to Print All Bind Values

Do not assume that setting `org.springframework.r2dbc.core=DEBUG` will print all bind values. `DatabaseClient` logs the SQL statement at the Spring layer; bind values are passed through the R2DBC `Statement` API to the driver.

The R2DBC SPI does not define a common logging property for all drivers to automatically print all parameters in the same format. To observe bind values, you need to check the driver's logging capabilities or use an R2DBC-compatible proxy/instrumentation.

## 4. Configuring Logging by Spring Boot Profile

A clear approach is to set logging levels by profile. The base configuration keeps log levels moderate; the dev profile can enable SQL DEBUG; the production profile keeps SQL at INFO or higher according to operational policy.

Example structure:

```text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-prod.yml
```

### 4.1. Default Configuration

application.yml:

```yaml
logging:
  level:
    root: INFO
    org.springframework.r2dbc.core: INFO
    org.springframework.data.r2dbc: INFO
```

The INFO level is the baseline. The application still logs business events, warnings, and errors according to the project's logger configuration.

### 4.2. Development Profile

application-dev.yml:

```yaml
logging:
  level:
    org.springframework.r2dbc.core: DEBUG
    org.springframework.data.r2dbc: DEBUG
```

Run the application with the dev profile:

```bash
SPRING_PROFILES_ACTIVE=dev ./mvnw spring-boot:run
```

On PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
.\mvnw spring-boot:run
```

In local development, SQL DEBUG helps you see the queries sent by repositories or `DatabaseClient`. Prefer using a local database with synthetic data instead of copying production data to a personal machine.

### 4.3. Test Profile

application-test.yml:

```yaml
logging:
  level:
    root: WARN
    org.springframework.r2dbc.core: DEBUG
    org.springframework.data.r2dbc: INFO
```

In tests, you can enable SQL DEBUG when diagnosing integration failures. If the suite runs many tests or runs tests in parallel, SQL logs can become very verbose; limit the loggers and keep enough output to identify the failing test.

### 4.4. Production Profile

application-prod.yml:

```yaml
logging:
  level:
    root: INFO
    org.springframework.r2dbc.core: INFO
    org.springframework.data.r2dbc: INFO
```

Production typically does not enable parameter logging. When diagnostics are needed, prefer trace IDs, operation names, durations, affected row counts, SQL states, and error codes. Only enable SQL DEBUG or detailed instrumentation under a controlled procedure for a limited duration.

### 4.5. Overriding via Environment Variables

Spring Boot supports overriding logging configuration via environment variables:

```text
LOGGING_LEVEL_ORG_SPRINGFRAMEWORK_R2DBC_CORE=DEBUG
```

This approach is useful when you need to temporarily enable SQL logs for a single instance without modifying configuration files. After completing the investigation, restore the original log level.

## 5. Configuring Driver-Specific Loggers

Each R2DBC driver may use its own loggers for protocol, queries, connections, or errors. Package names and log levels depend on the driver and its version.

There is no universal driver logger name guaranteed to work across PostgreSQL, MySQL, SQL Server, and H2. Before enabling one:

1. Identify the actual driver running from dependencies and `ConnectionFactory`.
2. Read the logging documentation for that exact driver version.
3. Identify which logger records SQL, protocol details, or bind data.
4. Enable it in a local or test environment first.
5. Test a query with synthetic values and inspect the actual log output.
6. Evaluate log volume, sensitive data exposure, and performance overhead.

Avoid enabling the entire `io.r2dbc` package or protocol logging at TRACE without knowing what content will be logged. It may produce excessive connection lifecycle logs, protocol frames, or unnecessary data.

## 6. Logging SQL Statements with DatabaseClient

When using `DatabaseClient`, SQL can be placed in a named variable or constant:

```java
private static final String FIND_CUSTOMER_SQL = """
        SELECT id, display_name, status
        FROM customer
        WHERE id = :id
        """;

public Mono<CustomerSummary> findSummary(UUID id) {
    return databaseClient.sql(FIND_CUSTOMER_SQL)
            .bind("id", id)
            .map((row, metadata) -> new CustomerSummary(
                    row.get("id", UUID.class),
                    row.get("display_name", String.class),
                    row.get("status", String.class)))
            .one();
}
```

If you want to record an event at the application layer, log the operation name instead of printing the entire object:

```java
log.debug("Starting database operation: operation={}", "customer.findSummary");
```

Spring loggers can record the SQL statement. Application logs add business context such as the operation name or request ID. Avoid logging the same SQL statement across multiple layers unless there is a clear diagnostic benefit.

## 7. Parameter Logging with an R2DBC Proxy

The R2DBC SPI does not have a portable parameter logging mechanism across all drivers. One option is to use an R2DBC-specific proxy library, such as `r2dbc-proxy`.

The proxy wraps the real `ConnectionFactory` and observes operations such as:

- Statement creation.
- Parameter binding.
- Query execution.
- Execution duration.
- Results or errors.

Depending on the library version, listener and formatter APIs may vary. General integration pattern:

```java
ConnectionFactory observedFactory =
        ProxyConnectionFactory.builder(realConnectionFactory)
                .onAfterQuery(queryExecutionInfo -> {
                    // Only log allowed metadata.
                    // Do not print all bind values without masking.
                })
                .build();
```

This code snippet illustrates the integration point; verify the exact API for the chosen `r2dbc-proxy` version. Register this proxy factory as the `ConnectionFactory` used by Spring Data R2DBC.

### 7.1. What Can the Proxy Observe?

A query execution event can typically provide information about:

- The SQL/query string.
- Batches or bind groups.
- Parameter metadata and bind values depending on proxy/driver capabilities.
- Start time, end time, and duration.
- Number of affected rows or execution result.
- Exception if the query fails.

Exact capabilities depend on the proxy version and driver. Do not assume the proxy can read every parameter type or all batch data identically.

### 7.2. Applying Masking in the Listener

Do not log the entire `QueryExecutionInfo` directly if the default formatter can print parameter values. Convert the event into a safe record:

```json
{
  "operation": "customer.findByEmail",
  "sql": "SELECT ... WHERE email_address = ?",
  "parameters": [
    {"index": 0, "type": "String", "value": "[REDACTED]"}
  ],
  "durationMs": 12,
  "rowsUpdated": 0
}
```

This is an illustrative structure. In production code, read the metadata provided by your proxy version and retain only the required fields.

### 7.3. Wrapping the Right ConnectionFactory

If the application has multiple `ConnectionFactory` instances, decide where the proxy belongs:

- Wrap each target factory if you need to observe each database individually.
- Wrap the routing factory if you need to see operations from the application side after routing has been chosen, depending on how the proxy interacts with the routing implementation.
- Name log sources to distinguish databases or pools without logging connection URLs/passwords.

If the proxy is wrapped outside a routing factory, verify that the listener can receive the desired routing metadata. If you need to know the tenant, pass a controlled tenant identifier into the logging context; do not infer the tenant by logging the full connection string.

## 8. Do Not Confuse r2dbc-proxy with P6Spy

P6Spy is commonly used to observe JDBC statements. It does not automatically become a proxy for an R2DBC `ConnectionFactory`.

Applications using Spring Data R2DBC require R2DBC-compatible instrumentation, such as `r2dbc-proxy`, or loggers/instrumentation provided by the driver. Do not add P6Spy to an application and expect it to log reactive queries.

Similarly, Hibernate/JPA SQL logs do not reflect statements executed by Spring Data R2DBC if the application uses two different persistence stacks.

## 9. Masking Sensitive Data in Parameter Logs

Parameters can contain:

- Emails, phone numbers, and street addresses.
- Names, dates of birth, or personal information.
- Access tokens, refresh tokens, or API keys.
- Passwords or authentication credentials.
- Account numbers, payment data, and financial information.
- Message contents or confidential business data.

Even internal IDs can be sensitive data if they can be linked to an individual or account.

Before logging bind values, classify parameters:

| Category | Example | Recommended Logging Approach |
| --- | --- | --- |
| Non-sensitive | Small limit, technical status | May be logged per policy |
| Internal identifier | Customer/order UUID | Prefer correlation ID or approved shortened form |
| Personal data | Email, phone, address | Mask or do not log |
| Auth secrets | Password, token, API key | Do not log value |
| Financial | Account number, payment info | Do not log full value |
| Free-form content | Message, JSON payload, notes | Do not log in full; choose safe metadata |

### 9.1. Allowlist-Based Masking

A safe strategy is to only log parameters explicitly identified as non-sensitive. Parameters not in the allowlist are masked by default:

```java
String safeValue(String parameterName, Object value) {
    if (Set.of("status", "pageSize").contains(parameterName)) {
        return String.valueOf(value);
    }
    return "[REDACTED]";
}
```

This example only illustrates the policy. Parameter names may not be reliably provided by the proxy with native positional binding; in that case, use operation metadata or schema mapping to determine the data type. If it cannot be safely determined, do not log the value.

### 9.2. Do Not Log Entire Objects or DTOs

Avoid:

```java
log.debug("Saving customer: {}", customer);
```

`toString()` can print emails, phone numbers, addresses, or secret fields. Instead, log the operation and approved metadata:

```java
log.debug("Saving customer: operation={}, customerType={}",
        "customer.save",
        customer.getClass().getSimpleName());
```

If an identifier is needed for investigation, use a correlation code or an ID evaluated as safe under the application's data policy.

### 9.3. SQL Literals Can Also Leak Data

Bind parameters are not the only source of sensitive data. Native SQL built via string concatenation can embed values directly into the query string:

```java
String sql = "SELECT * FROM customer WHERE email_address = '" + email + "'";
```

When SQL is logged, the email is already in the statement. Therefore, always use bind parameters for input data and do not rely on bind-value masking to compensate for SQL string concatenation.

## 10. Choosing Detail Levels by Environment

A sample policy:

| Environment | SQL statement | Bind values | Duration/error |
| --- | --- | --- | --- |
| Local dev | DEBUG when needed | Synthetic data or masked only | Yes |
| Automated test | Selective DEBUG | Do not log sensitive values | Yes |
| Staging | INFO default; temporary DEBUG during investigation | Mask/allowlist, usually disabled | Yes |
| Production | INFO/WARN/ERROR per logger | Disabled or approved masked metadata only | Yes, prefer structured logs/metrics |

This is a baseline, not a mandatory log level for every application. The final decision depends on operational requirements, data protection policies, and log platform capabilities.

## 11. Correlation ID and Trace ID

A single request often generates multiple queries and logs across controllers, services, repositories, the connection pool, and the driver. Without correlation, stitching those logs together is very difficult.

Include an end-to-end identifier in structured logs:

- Trace ID from distributed tracing.
- Span ID for the current operation.
- Correlation ID generated by the application or gateway.
- Operation name such as `order.create` or `customer.find`.
- Allowed tenant identifier, if permitted by policy.

Example:

```text
timestamp=2026-11-15T10:00:00Z
level=DEBUG
traceId=8f...
spanId=31...
operation=customer.find
db.system=postgresql
durationMs=18
rowsReturned=1
```

There is no need to put emails or full SQL parameters into logs to find a request when the trace ID is sufficient to link events.

## 12. Reactor Context and MDC

In a reactive application, do not assume a request always runs on the same thread. Many logging frameworks' MDCs rely on `ThreadLocal`, so setting MDC directly in a callback and expecting it to follow the publisher can cause lost correlation or value leakage across requests.

Reactor Context is well-suited for carrying metadata along a subscription. With Spring Boot and Micrometer Tracing/Context Propagation, use the supported integration mechanism to propagate trace context into log MDC.

Principles:

- Keep trace/correlation metadata in the reactive context.
- Do not use a mutable `ThreadLocal` tenant holder to route or identify requests.
- If MDC is needed, enable and configure context propagation properly for your Spring/Reactor stack.
- Do not call `MDC.put()` manually without clearing it in a thread-reusing pipeline.
- Test log correlation when the pipeline switches schedulers and when two requests run concurrently.

A route key and a trace ID can coexist in Reactor Context, but they serve two different purposes: the route key selects the database; the trace ID links logs. Do not put secrets in either.

## 13. Logging Query Execution Duration

SQL statements tell you which query ran; duration tells you which query is slow. Duration can be captured in a proxy listener or metrics instrumentation.

One way to measure at the application layer using Reactor:

```java
public Mono<Customer> findCustomer(UUID id) {
    return Mono.defer(() -> {
        long startedAt = System.nanoTime();

        return customerRepository.findById(id)
                .doFinally(signal -> {
                    long elapsedNanos = System.nanoTime() - startedAt;
                    long durationMs = elapsedNanos / 1_000_000;

                    log.debug(
                            "Database operation completed: operation={}, durationMs={}, signal={}",
                            "customer.findById",
                            durationMs,
                            signal);
                });
    });
}
```

`Mono.defer` creates a timestamp per subscription. `doFinally` is invoked when the publisher completes, errors, or is cancelled. This is the duration observed at the publisher layer, which may include connection wait time and other steps; it is not necessarily equal to the database statement execution time.

If you need query-specific duration, use a query execution listener/proxy or driver-level instrumentation. Do not tag metrics with raw SQL containing dynamic values, as that creates very high cardinality.

### 13.1. Slow Query Threshold

You can log a warning when an operation exceeds a threshold:

```java
if (durationMs >= slowQueryThresholdMs) {
    log.warn(
            "Slow database operation: operation={}, durationMs={}",
            "customer.findById",
            durationMs);
}
```

Thresholds must be based on SLAs, query types, and real measurements. Do not apply the same threshold to every query; a reporting query may have a different profile than a single-record lookup.

### 13.2. Metrics Instead of Logging Every Query

For long-term observation, metrics are usually more suitable than writing a log entry for every query:

- Query count by operation.
- Duration histogram.
- Error count by error category.
- Timeout count.
- Connection acquire latency.
- Pool pending acquire and active connection counts.

Use Micrometer/Observation or instrumentation appropriate for Spring Boot and the driver. Metric tags should have low cardinality such as operation, database system, and outcome; avoid tagging with IDs, full SQL, or parameter values.

## 14. Logging Database Errors

When a query fails, record enough information to categorize the error:

- Operation name.
- Trace/correlation ID.
- SQL state or vendor error code if available.
- Exception type.
- Duration.
- Allowed database system/target alias.
- Retry count if applicable.

Example:

```java
return customerRepository.findById(id)
        .doOnError(error -> log.error(
                "Database operation failed: operation={}, customerId={}, errorType={}",
                "customer.findById",
                safeIdentifier(id),
                error.getClass().getSimpleName(),
                error));
```

Only log `safeIdentifier` after confirming that ID is permitted to be logged. Do not print the entire request or entity. Driver exceptions may contain SQL or server details; evaluate the log output in a test environment before sending it to a centralized log platform.

Do not log the same exception at every layer and produce duplicate stack traces. Choose the layer responsible for error handling to log once with full context.

## 15. Avoiding Excessive SQL Logging

A single endpoint can execute many queries. When SQL DEBUG is enabled across all instances, log volume can grow rapidly and cause:

- CPU overhead for formatting logs.
- Increased storage volume and log transmission costs.
- Difficulty finding critical errors in large log volumes.
- Data leakage from unclassified queries.
- Latency impact if appenders are synchronous or the log sink is slow.

Ways to control this:

- Enable loggers by profile or per instance.
- Enable only for the package/operation under investigation.
- Limit the duration debug logging stays enabled.
- Use sampling for high-volume successful queries.
- Always log errors, timeouts, and slow queries per policy.
- Set shorter retention for detailed diagnostic logs.
- Keep bind value logging disabled by default in production.

## 16. Dynamically Enabling Log Levels via Actuator

Spring Boot Actuator provides an endpoint to manage loggers in appropriate configurations. It can allow viewing or changing log levels without restarting the application.

Because this endpoint can alter logging behavior:

- Only expose it on a trusted administrative network.
- Protect it with authentication/authorization.
- Never expose the loggers endpoint publicly to the Internet.
- Audit who changed the log level and when.
- Restore the log level after the investigation.
- Do not use the dynamic endpoint to enable unauthorized parameter logging.

If the organization does not need runtime log level changes, do not expose this endpoint. Changes can be made via deployment configuration or environment variables instead.

## 17. Environment-Specific Logback Configuration

Besides application YAML, applications can use `logback-spring.xml` to configure appenders, formats, and rolling policies. Spring Boot supports profile sections in the Logback Spring file.

Abbreviated example:

```xml
<configuration>
    <springProfile name="dev">
        <logger name="org.springframework.r2dbc.core" level="DEBUG"/>
        <logger name="org.springframework.data.r2dbc" level="DEBUG"/>
    </springProfile>

    <springProfile name="prod">
        <logger name="org.springframework.r2dbc.core" level="INFO"/>
        <logger name="org.springframework.data.r2dbc" level="INFO"/>
    </springProfile>
</configuration>
```

This is only the logger configuration section; appenders, encoders, rolling, and retention must be defined according to the project's logging standards. Do not configure conflicting settings in two places without understanding the precedence between YAML and Logback.

If using `logback-spring.xml`, keep the exact filename so Spring Boot processes extensions such as `springProfile`.

## 18. Logging SQL Across Multiple Databases or Tenants

An application may have multiple `ConnectionFactory` instances, tenant databases, or read replicas. Logs need to distinguish targets safely:

```text
operation=order.find
db.system=postgresql
db.target=tenant-cluster-a
db.role=primary
durationMs=24
```

`db.target` should be a configured alias, not a connection URL. Do not log usernames/passwords, sensitive internal hostnames, or query parameters containing secrets.

With tenant routing, only log tenant IDs if data policy permits. You can log a route group or obfuscated alias to investigate pools and databases without exposing customer identifiers.

A query may run on a different database due to routing context. Ensure route metadata is attached to the right subscription and do not use `ThreadLocal` to infer the tenant.

## 19. Testing Logging Configuration

Logging is part of operational readiness, so verify profile configurations in automated or smoke tests:

- The dev profile enables SQL loggers on the expected packages.
- The prod profile does not accidentally enable SQL DEBUG or parameter logging.
- Sensitive parameters are masked or omitted.
- Log records include trace/correlation IDs when a request context is present.
- Two concurrent reactive requests do not mix up their contexts.
- Database errors log SQL state/error type without leaking credentials.
- Slow query events include the operation name and duration.
- Driver loggers are enabled only on the required packages.

Do not test by comparing full log strings if the format may change across framework versions. You can use a test appender or log event capture to check log levels, message templates, and sensitive fields.

## 20. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| No SQL appears in logs | R2DBC core logger is not at DEBUG or appender filters out DEBUG | Check `org.springframework.r2dbc.core` and appenders |
| SQL appears without bind values | Spring SQL logger logs statements, not all bind values | Use proxy/driver instrumentation if genuinely needed |
| No logs from driver | Wrong logger package or driver does not emit logs at that level | Check documentation for the exact driver/version |
| Too many logs | DEBUG/TRACE enabled on a broad package or all instances | Restrict package, profile, duration, and sampling |
| Email/token appears in logs | Unmasked parameter or object logged | Disable parameter logging, add allowlist/masking, and check retention |
| Trace ID lost across threads | MDC/ThreadLocal not propagated across reactive context | Use Reactor Context and Micrometer context propagation |
| Query logged without knowing caller request | Missing trace/correlation ID and operation name | Add structured context |
| Logged duration higher than DB time | Measuring entire publisher, including pool acquire and other processing | Use query-level instrumentation if statement duration is needed |
| P6Spy does not capture R2DBC queries | P6Spy targets JDBC | Use an R2DBC-compatible proxy/instrumentation |
| Production unexpectedly enables DEBUG | Profile or environment variable overrides config | Check active profiles and effective configuration |
| SQL log exposes literals | Data concatenated directly into SQL | Use bind parameters and review native queries |

## 21. Workflow for Investigating a Failing or Slow Query

When diagnosing an R2DBC issue:

1. Identify the environment and active Spring profile.
2. Retrieve the trace ID/correlation ID of the request or job.
3. Identify the operation name and relevant repository/`DatabaseClient` method.
4. Enable SQL DEBUG on a narrow package for the necessary duration.
5. Inspect the query shape, bind markers, and dialect.
6. If parameters are needed, use proxy/driver instrumentation with masking; do not enable printing all bind values.
7. Record duration, outcome, row count, and SQL state if available.
8. Check connection pool acquire latency to distinguish pool waiting from slow queries.
9. Use the database execution plan or database slow query log for server-side analysis.
10. Turn off diagnostic log levels once done and verify production configuration returns to baseline.

Application logs show what happened from the service/driver perspective. Database slow query logs and execution plans help determine how much time the server actually spent planning and executing. Both sources complement each other.

## 22. Recommended Logging Policy

An easy-to-adopt policy:

| Data | Local Dev | Test | Production |
| --- | --- | --- | --- |
| SQL statement with markers | DEBUG when needed | Selective DEBUG | INFO default; controlled temporary DEBUG |
| Normal bind values | Synthetic fixtures only | Restricted | Disabled by default |
| Sensitive bind values | Do not log | Do not log | Do not log |
| Parameter type/index | May log | May log | May log if useful |
| Query duration | DEBUG or metrics | May log | Metrics and slow query events |
| SQL state/error type | Yes | Yes | Yes |
| Password/credential | Do not log | Do not log | Do not log |
| Trace/correlation ID | Yes | Yes | Yes |

It is important to distinguish diagnostic logs from operational telemetry. SQL DEBUG can be useful briefly; structured metrics and traces are usually better suited for continuous observation.

## 23. Environment Configuration Checklist

When implementing logging for Spring Data R2DBC, verify:

1. Is the Spring R2DBC core logger set to the right level in the necessary profiles?
2. Is the Spring Data R2DBC logger needed to track repository/mapping behavior?
3. Does the driver have its own loggers and specific documentation for the version in use?
4. Is parameter logging genuinely required, or are SQL statements sufficient?
5. If parameter logging is required, does the proxy support the driver and bind style in use?
6. Is masking/allowlisting applied before writing values?
7. Are passwords, tokens, PII, and sensitive payloads excluded?
8. Do logs include trace/correlation IDs and operation names?
9. Is duration measured at the publisher layer or query execution layer?
10. Do metrics avoid high-cardinality tags like raw SQL and IDs?
11. Does production keep SQL DEBUG and TRACE disabled as a baseline?
12. Is there a mechanism to disable diagnostic log levels after incident resolution?

Logging SQL and parameters helps observe persistence behavior, but the two types of logs carry different risk levels. Spring `DatabaseClient` can log SQL statements at DEBUG; bind values require driver-specific capabilities or a proxy like `r2dbc-proxy`. Configure loggers by profile, prioritize structured trace IDs, operations, durations, and errors, and mask sensitive data. In production, keep parameter logging off by default and only enable detailed instrumentation with a clear reason, scope, and expiration.

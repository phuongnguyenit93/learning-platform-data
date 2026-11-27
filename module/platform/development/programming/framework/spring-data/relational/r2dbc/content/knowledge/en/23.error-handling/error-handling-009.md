# Preserving Error Causes and Avoiding Logging Sensitive Information

In Spring Data Relational R2DBC, errors from the database and driver pass through several layers before reaching an API or worker: the R2DBC driver emits an exception, Spring may translate it into the `DataAccessException` hierarchy, the service may map it into a business exception, and then a controller or message handler decides how to respond. When transforming errors, the application must preserve the original root cause for diagnostics. At the same time, logging must be controlled because exceptions, SQL statements, bind parameters, and request payloads can contain personal or secret data.

These two requirements reinforce each other: **preserve `cause` in the exception chain so technical context is never lost, yet log only selected fields sanitized under security policies**. Preserving the cause does not mean dumping full exceptions, messages, SQL, or payloads into logs everywhere.

## 1. Error Flow in R2DBC Applications

A reactive database operation can emit errors from several sources:

- Connection failures or timeouts while opening a connection.
- SQL syntax errors or data type mismatches.
- Unique, foreign key, `NOT NULL`, or `CHECK` constraint violations.
- Deadlocks, serialization failures, or transaction errors.
- Mapping/conversion failures between SQL types and Java types.
- Application-initiated cancellations or processing timeouts.

For example, an `INSERT` executed through a repository:

```java
Mono<Customer> saveCustomer(Customer customer) {
    return customerRepository.save(customer);
}
```

When the database rejects the operation, the driver emits an error through the reactive publisher. Depending on the data access path and exception translation mechanism, Spring may translate the driver failure into an exception in the `DataAccessException` hierarchy. The service can propagate that exception or map it to a business exception.

Overall flow:

```text
Database / R2DBC driver
          |
          v
R2dbcException or other driver error
          |
          v
Spring exception translation (when applicable)
          |
          v
DataAccessException / mapping error
          |
          v
Service translates to business error
          |
          v
API handler / worker boundary
          |
          +----> safe response to caller
          |
          +----> selective logs without leaking sensitive data
```

Not every failure is a SQL error. An HTTP client timeout, serialization failure, or validation error can enter the same reactive pipeline. Classify by error type and origin instead of treating every exception as a database failure.

## 2. What Is the Root Cause?

Java exceptions can wrap another exception. The outer exception describes meaning at the current layer; `cause` retains the lower-level failure that led to it.

Example:

```text
CustomerRegistrationException
    caused by DataIntegrityViolationException
        caused by R2dbcDataIntegrityViolationException
            caused by R2dbcException (SQLSTATE / vendor code)
```

In this chain:

- `CustomerRegistrationException` expresses the error in customer registration business terms.
- `DataIntegrityViolationException` indicates a data integrity violation at the data access layer.
- The R2DBC exception retains more specific driver/database details.
- `R2dbcException` can supply SQL state, vendor error codes, and driver-specific details.

Preserving the cause helps developers separate business failures from technical causes and diagnose database behavior without exposing internals through the API.

## 3. Creating New Exceptions While Preserving Cause

When translating technical errors into service-layer errors, use constructors accepting `Throwable cause`:

```java
public class CustomerRegistrationException extends RuntimeException {

    public CustomerRegistrationException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Map errors inside reactive pipelines with `onErrorMap`:

```java
public Mono<Customer> register(Customer customer) {
    return customerRepository.save(customer)
        .onErrorMap(DataIntegrityViolationException.class,
            error -> new CustomerRegistrationException(
                "Could not complete customer registration",
                error
            ));
}
```

`onErrorMap` replaces the error signal with the new exception. The new exception keeps the prior exception as its cause, keeping the causal chain traceable wherever authorized.

Write the new message in business terms without embedding emails, phone numbers, SQL statements, or parameter values. If you need to display a conflicting email to the user, handle it under an explicit response policy; never embed it into exception messages by default because messages are frequently logged across layers.

### 3.1. Never create new exceptions with only a message

Avoid:

```java
return customerRepository.save(customer)
    .onErrorMap(error -> new CustomerRegistrationException(
        "Registration failed: " + error.getMessage(),
        null
    ));
```

This snippet has two flaws:

- The original cause is lost because `null` is passed.
- Driver or database messages may expose SQL, table/column names, bound data, or infrastructure details.

Prefer:

```java
return customerRepository.save(customer)
    .onErrorMap(error -> new CustomerRegistrationException(
        "Could not complete customer registration",
        error
    ));
```

### 3.2. Never substitute `getMessage()` for `cause`

`error.getMessage()` returns only a descriptive string. It drops the exception type, stack trace, and cause chain. Concatenating the message into a new exception is not equivalent to:

```java
new CustomerRegistrationException("Registration failed", error);
```

When extra context is needed, add a safe operation code or business identifier to the new exception while passing the original exception to the constructor.

### 3.3. Avoid wrapping errors repeatedly without adding meaning

Every layer should not invent a new exception just to rename and re-wrap the error. Overly deep cause chains full of redundant messages make diagnosis harder.

Translate only across clear semantic boundaries, such as:

- Driver error to data access error.
- Data error to business error understood by callers.
- Business error to HTTP status or API error code.

If there is no reason to change the exception type, let the original exception propagate upward.

## 4. Distinguishing `onErrorMap`, `onErrorResume`, and `doOnError`

Reactor operators handle errors for different purposes:

| Operator | Effect | Downstream signal |
|---|---|---|
| `onErrorMap` | Transforms an exception into another exception | Remains `onError`, though exception type may change |
| `onErrorResume` | Swaps an error for a fallback Publisher | May emit values, complete empty, or emit another error |
| `doOnError` | Observes an error for logging/metrics | Preserves the error untouched; does not handle or replace it |
| `onErrorReturn` | Replaces an error with a default value | Completes successfully with that value |
| `doFinally` | Observes completion/error/cancellation | Leaves the emitted signal unchanged |

### 4.1. Using `onErrorMap` to retain the original error

```java
return repository.save(entity)
    .onErrorMap(DataAccessException.class,
        error -> new EntityWriteException(
            "Could not save entity",
            error
        ));
```

The signal stays `onError`; only the exception is wrapped. Callers can match `EntityWriteException` while `cause` preserves Spring/driver details.

### 4.2. Using `doOnError` to observe without swallowing

```java
return repository.save(entity)
    .doOnError(error -> log.warn(
        "Entity write failed; operation={}",
        "customer.create"
    ));
```

`doOnError` executes a side-effect callback as the error passes through, leaving the error flowing downstream. It is well suited for emitting metrics or writing a sanitized log event.

Never turn `doOnError` into a place that invokes another `Publisher` and calls `subscribe()` independently. The callback does not wait for reactive work started inside it. If asynchronous audit/logging is part of the use case, compose it via reactive operators or write to an outbox.

### 4.3. `onErrorResume` can make errors disappear

```java
return repository.findById(id)
    .onErrorResume(error -> Mono.empty());
```

This turns every error into empty. Callers cannot distinguish "record not found" from "database failure." Only fall back for identified error types where the replacement value has clear business validity.

If you only want to change the exception class, use `onErrorMap`; never use `onErrorResume` solely to wrap errors.

## 5. Preserving Cause Does Not Mean Logging the Entire Cause Chain

Keep three surfaces distinct:

- **In-memory exception chain:** retains `cause` so layers can classify and diagnose failures.
- **Log events:** durable records shipped to log stores accessible by multiple people or tools.
- **API responses:** data returned to external clients or callers.

Each surface has different audiences and access controls. An exception may contain SQL, schema names, constraint names, file paths, hostnames, database usernames, emails, or partial values. Logging full exceptions via `log.error("...", error)` prints messages and cause chains, potentially leaking that data.

You can preserve `cause` in the exception while logging only curated fields:

```java
return repository.save(customer)
    .onErrorMap(error -> new CustomerRegistrationException(
        "Could not complete customer registration",
        error
    ));
```

At the boundary, log safe fields:

```java
log.error(
    "Customer registration failed; operation={}, correlationId={}, errorType={}",
    "customer.register",
    correlationId,
    error.getClass().getSimpleName()
);
```

This example omits the trailing `Throwable` argument from the logger call, preventing automatic printing of full messages and stack traces. When stack traces are required for debugging, route them to an access-controlled sink where exceptions and messages are reviewed or scrubbed per system policy.

Never strip `cause` merely to make logs safe. Separate keeping error causes in memory from deciding which fields belong in logs.

## 6. Data That Should Never Be Logged

In R2DBC applications, sensitive data appears in more places than HTTP bodies. Avoid logging:

| Data category | Examples | Handling |
|---|---|---|
| Authentication secrets | Passwords, API keys, client secrets, private keys | Never log; log only credential/config key names if needed |
| Tokens | Access tokens, refresh tokens, JWTs, session cookies | Never log tokens; use dedicated correlation/trace IDs |
| Personal data | Emails, phone numbers, addresses, birthdates, national IDs | Avoid logging; link using internal IDs or proper tokenization |
| Payment data | Card numbers, CVVs, bank accounts, sensitive transaction details | Never log full contents; follow payment data policies |
| Request/response payloads | JSON containing profiles, passwords, or personal info | Never log full bodies; log allowlisted metadata |
| R2DBC bind values | Emails, customer codes, query text, LOB payloads | Never enable bind-value logging in production |
| Embedded-literal SQL | String-concatenated SQL holding user input | Use bind parameters and never log interpolated SQL |
| Exception messages | Driver messages containing SQL, values, or connection details | Log selected error types/codes; protect detailed logs if needed |
| HTTP headers | `Authorization`, `Cookie`, `Set-Cookie` | Strip or completely redact sensitive headers |

Not every ID is public data. Account, tenant, or order IDs can still correlate user activity. Classify identifiers under your data policy and log only the minimum required.

## 7. Preventing Accidental SQL and Bind-Value Logging

An R2DBC operation may be logged by multiple layers:

- Application loggers.
- Spring Framework / Spring Data.
- The R2DBC driver.
- The connection pool.
- Database audit or query logs.
- APM/tracing agents.

Even if application code never logs entities, `DEBUG`/`TRACE` settings on drivers or data access libraries can print SQL and bind parameters. In production, never turn on verbose logging solely to debug an issue without assessing what data could leak.

Bind-safe query example:

```java
databaseClient.sql("""
        SELECT id, email
        FROM app_user
        WHERE email = :email
        """)
    .bind("email", email)
    .map((row, metadata) -> new UserSummary(
        row.get("id", Long.class),
        row.get("email", String.class)
    ))
    .one();
```

Bind parameters separate data from SQL structure and prevent SQL injection when used properly. However, bind parameters alone do not prevent driver loggers from printing values; manage logging levels separately.

Never concatenate values into SQL just to make logs easier to read:

```java
// Avoid: email value is interpolated directly into SQL text.
String sql = "SELECT id FROM app_user WHERE email = '" + email + "'";
```

Beyond SQL injection risks, interpolated SQL strings can surface in exceptions or logs. Keep SQL static and bind parameters.

## 8. Structured Logging and Field Allowlists

A good log event answers:

- Which operation failed?
- Which service or component failed?
- Which request or job was involved?
- What error type or category occurred?
- When did it happen and at what severity?
- Which trace or correlation ID links the event?

Safe fields might look like:

```text
event=customer.register.failed
operation=customer.register
correlation_id=7b2...
error_type=DataIntegrityViolationException
error_category=DATA_INTEGRITY
duration_ms=42
```

This is illustrative data. Exclude raw emails, tokens, passwords, request bodies, SQL bind values, and full exception messages from events.

### 8.1. Prefer allowlists over denylists

An allowlist logs only pre-approved fields. A denylist logs everything and tries to scrub known sensitive field names. Denylists easily miss newly added fields, aliases, or deeply nested properties.

Example allowlist for creating a customer:

- Fixed operation name: `customer.register`.
- System-generated or validated/normalized correlation ID.
- Error category: `DATA_INTEGRITY`, `CONNECTION`, `TIMEOUT`, or `UNKNOWN`.
- Simple exception class name.
- Elapsed duration and outcome.
- Classified constraint code if it reveals no sensitive schema details.

Never serialize entire entities or request DTOs to JSON for logging. When schemas evolve, whole-object serialization can silently leak newly added sensitive fields into logs.

### 8.2. Use parameterized logging

With SLF4J:

```java
log.warn(
    "Database operation failed; operation={}, errorType={}",
    operation,
    errorType
);
```

Parameterized logging avoids manual string concatenation and skips formatting overhead when the log level is disabled. However, it does not sanitize values automatically. If `operation` or another field comes from untrusted input, validate/sanitize it before logging.

## 9. Preventing Log Injection and Log Forging

Users can submit strings containing newlines or control characters. Writing those strings verbatim into plain-text logs allows attackers to forge fake log lines or break log parsers.

Example input:

```text
guest
level=ERROR event=login.success user=admin
```

If written raw into logs, the second line can look like an independent event. Defenses:

- Avoid logging raw user input unnecessarily.
- Use structured loggers that properly encode values as JSON.
- Bound maximum text field lengths.
- Strip or escape CR, LF, and control characters when logging text fields.
- Never let clients supply arbitrary event names, severities, or log keys.
- Use fixed, application-controlled operation names and error codes.

A simple sanitizer for non-sensitive text fields:

```java
static String safeLogText(String value) {
    if (value == null) {
        return "";
    }

    String normalized = value
        .replace('\r', ' ')
        .replace('\n', ' ')
        .replace('\t', ' ');

    return normalized.length() <= 120
        ? normalized
        : normalized.substring(0, 120);
}
```

This helper demonstrates only control-character and length normalization. It does **not** make sensitive data safe to log. Never call `safeLogText(email)` and assume logging the email is now allowed; policy remains not to log emails without explicit justification and approval.

## 10. Masking, Redaction, and Pseudonymization

Three distinct concepts are often confused:

- **Masking:** hiding part of a value, e.g., displaying only the last four characters.
- **Redaction:** removing a value from logs or replacing it with a marker such as `[REDACTED]`.
- **Pseudonymization:** replacing a value with an alternate token to correlate events without exposing the original value.

For example, if policy allows partial display of a transaction reference:

```text
transaction_ref=********4821
```

Do not apply masking indiscriminately across all data types. Passwords, access tokens, refresh tokens, private keys, and CVVs should never be partially logged; remove them completely.

When you need to correlate the same customer across logs, use an internal non-identifying ID or an HMAC pseudonym computed with a protected key. Unkeyed hashes are vulnerable to brute-force reversal over small input spaces such as phone numbers or emails. Never treat bare `SHA-256(email)` as strong anonymization.

Masking and redaction should happen before data reaches the logger or inside a controlled logging layer. Do not rely on deleting sensitive data after logs have already shipped to centralized stores, replicas, archives, or alerts.

## 11. Logging Exceptions Safely While Preserving Investigability

A sound strategy separates safe business-boundary logs from detailed technical diagnostics.

### 11.1. Safe event logging at the application boundary

```java
public Mono<Customer> register(Customer customer, String correlationId) {
    return customerRepository.save(customer)
        .onErrorMap(error -> new CustomerWriteException(
            "Could not save customer",
            error
        ))
        .doOnError(error -> log.error(
            "Customer write failed; operation={}, correlationId={}, errorType={}",
            "customer.register",
            safeCorrelationId(correlationId),
            error.getClass().getSimpleName()
        ));
}
```

This keeps `cause` inside `CustomerWriteException`, while the log records only the operation, normalized correlation ID, and exception type. Passing no `Throwable` to the logger prevents printing the cause chain.

In larger applications, avoid logging the same failure at every layer. Services can translate exceptions silently, while controller advice, message listeners, or worker boundaries emit a single event as the error leaves the use case.

### 11.2. Selecting safe technical metadata

For R2DBC failures, safe diagnostic metadata can include:

- Exception class.
- Classified SQLSTATE or vendor error code.
- Fixed operation code.
- Constraint category or constraint name if policy permits.
- Elapsed duration.
- Correlation/trace ID.

Example extracting SQLSTATE without logging the message:

```java
static Optional<String> findSqlState(Throwable error) {
    for (Throwable current = error;
         current != null;
         current = current.getCause()) {

        if (current instanceof R2dbcException r2dbcException) {
            return Optional.ofNullable(r2dbcException.getSqlState());
        }
    }

    return Optional.empty();
}
```

You can then map SQLSTATE to a known category:

```java
static String classifySqlState(String sqlState) {
    if (sqlState == null) {
        return "UNKNOWN";
    }

    if (sqlState.startsWith("08")) {
        return "CONNECTION";
    }

    if (sqlState.startsWith("23")) {
        return "DATA_INTEGRITY";
    }

    if (sqlState.startsWith("40")) {
        return "TRANSACTION_ROLLBACK";
    }

    return "DATABASE_ERROR";
}
```

These SQLSTATE classes follow common SQLSTATE conventions, though final classification still depends on the database and driver. Never assume SQLSTATE alone is always sufficient to identify business causes; treat it as supporting technical metadata.

### 11.3. When full stack traces are needed

For hard-to-reproduce issues, full stack traces are valuable. However, loggers normally print exception messages and cause chains too. Before logging full traces:

- Check whether exception messages can contain SQL, bind values, or PII.
- Check whether the driver embeds connection URLs, usernames, or schema names in messages.
- Ship only to log sinks with strict access controls and appropriate retention.
- Apply masking/redaction prior to writing if needed.
- Never send detailed traces to public consoles, client responses, or unauthorized chat channels.

If stack trace safety cannot be guaranteed, log curated metadata and keep `cause` on the exception so debuggers or controlled diagnostic environments can inspect it when needed.

## 12. Returning Safe Errors to HTTP Clients

Never return `exception.getMessage()`, stack traces, or `cause.toString()` directly in HTTP responses:

```java
// Avoid.
return ResponseEntity.internalServerError()
    .body(error.getMessage());
```

Messages can expose:

- Internal table, schema, or column names.
- SQL queries and predicates.
- Hostnames, ports, or database names.
- Credentials or connection URLs.
- Another user's data.
- Constraint or implementation internals that should remain private.

Instead, return a stable error code and generic message:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(CustomerWriteException.class)
    ResponseEntity<ProblemDetail> handleCustomerWrite(
            CustomerWriteException error) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "Unable to process the request at this time"
        );
        problem.setTitle("Data processing error");
        problem.setProperty("code", "CUSTOMER_WRITE_FAILED");

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(problem);
    }
}
```

For known business errors, return specific statuses like 400, 404, 409, or 422 alongside stable error codes. For unexpected infrastructure errors, return a generic message and correlation ID so support can trace it via protected channels.

Never place `cause` or stack traces into `ProblemDetail`.

## 13. Correlation IDs and Tracing in Reactive Pipelines

Correlation IDs link log events belonging to the same request or workflow without logging full request payloads.

Example log:

```text
event=order.write.failed
correlation_id=7b2f...
operation=order.create
error_category=DATA_INTEGRITY
```

In reactive applications, never assume `ThreadLocal` always preserves request context because pipelines switch threads. Reactor Context propagates metadata along subscriptions; Micrometer Tracing/Observation integrations can bridge trace context and MDC depending on configuration.

Example reading a correlation ID from Reactor Context:

```java
Mono<Order> createOrder(Order order) {
    return Mono.deferContextual(contextView -> {
        String correlationId = contextView.getOrDefault(
            "correlationId", "unknown"
        );

        return orderRepository.save(order)
            .doOnError(error -> log.error(
                "Order write failed; operation={}, correlationId={}, errorType={}",
                "order.create",
                safeCorrelationId(correlationId),
                error.getClass().getSimpleName()
            ));
    });
}
```

This uses a custom `correlationId` key. In production systems, prefer your stack's standard tracing and context propagation instead of inventing a parallel mechanism. Never put tokens, emails, or request bodies into Reactor Context just for logging convenience.

If correlation IDs arrive from external HTTP headers, validate their length and allowed characters before use. Never trust arbitrary client values to name events or alter log structure.

## 14. Log Errors at a Single Responsible Boundary

An error can pass through repositories, services, controller advice, and global WebFlux error handlers. If every layer logs the stack trace, a single failure produces duplicate logs and multiplies data-leak exposure.

Assign clear roles:

| Layer | Appropriate responsibility |
|---|---|
| Repository | Return publishers and preserve errors; typically do not log and rethrow |
| Service | Translate errors to business semantics when needed; log only if unique operational context exists without duplicating boundaries |
| Controller advice / message boundary | Map errors to responses or acknowledgements; emit the final event per policy |
| Global error handler | Handle uncategorized errors, attach correlation ID, and emit one safe event |
| Worker/consumer boundary | Log retry, dead-letter, or job failure states using safe job identifiers |

Not every architecture has these exact layers. The core principle is choosing one boundary responsible for final error logging while intermediate layers propagate or translate exceptions without duplicating logs.

### 14.1. Avoid logging and rethrowing at every layer

Avoid:

```java
public Mono<Customer> save(Customer customer) {
    return repository.save(customer)
        .doOnError(error -> log.error("Repository failed", error));
}
```

followed by the service and controller advice logging full stack traces again. This creates noisy duplicate logs and risks logging sensitive data repeatedly.

If the repository lacks context to handle the error, let it propagate. Let the final boundary emit one clean event:

```java
public Mono<Customer> save(Customer customer) {
    return repository.save(customer);
}
```

## 15. SQL Logging, Bind Values, and Production Configuration

When investigating R2DBC bugs, developers sometimes turn on `DEBUG`/`TRACE` for driver or Spring packages to inspect SQL. While helpful locally or in tests with fake data, doing so in production carries risk.

Configuration checklist:

- Disable bind parameter logging by default in production.
- Never log `Authorization`, `Cookie`, `Set-Cookie`, or credential headers.
- Never log full request/response bodies containing personal data.
- Never log un-allowlisted entities, DTOs, or `Map`s.
- Audit APM agents, SQL instrumentation, and connection pool loggers for parameter capture.
- Keep `TRACE`/`DEBUG` enabled only briefly, with approval and narrow scope during active investigations.
- Use synthetic or anonymized data in development environments.
- Mask or suppress sensitive values in database audit/query logs per policy.

Never assume that using bind parameters prevents values from appearing in logs. Loggers can still be configured to record them.

## 16. Protecting Log Storage After Ingestion

Safely written logs still require protection throughout their lifecycle:

- Enforce role-based and need-to-know access controls.
- Encrypt in transit and at rest where supported.
- Configure appropriate retention and policy-driven deletion.
- Never ship production logs to personal accounts or unapproved services.
- Control log exports, downloads, and sharing.
- Monitor for anomalous access to log systems.
- Avoid putting sensitive data into alert titles, chat notifications, or public dashboards.

Logs are an operational data store that can be replicated, indexed, and retained longer than source databases. Preventing leaks at log creation time is far more reliable than trying to purge logs later.

## 17. Testing Cause Preservation and Data Leakage Prevention

Error tests should verify both goals: root causes remain intact, and logs/responses contain no sensitive data.

### 17.1. Testing the cause chain

```java
@Test
void preservesOriginalCause() {
    RuntimeException rootCause = new RuntimeException("driver failure");

    CustomerRegistrationException wrapped =
        new CustomerRegistrationException("Registration failed", rootCause);

    assertSame(rootCause, wrapped.getCause());
}
```

This verifies the constructor retains the cause object. For reactive mapping, assert on the emitted exception:

```java
StepVerifier.create(customerService.register(customer))
    .expectErrorSatisfies(error -> {
        assertInstanceOf(CustomerRegistrationException.class, error);
        assertInstanceOf(DataIntegrityViolationException.class,
            error.getCause());
    })
    .verify();
```

This assumes the repository emits `DataIntegrityViolationException`. Real tests should inject deliberate failures or run against an integrated database to verify exception translation.

### 17.2. Testing that logs exclude secrets

Use a test appender or log capture to verify events exclude sensitive values:

```java
assertThat(capturedLogs)
    .doesNotContain("secret-token-value")
    .doesNotContain("customer-private-email@example.com")
    .contains("customer.register")
    .contains("correlationId");
```

This illustrates string assertions. In real projects, use your logging framework's test appender and inspect formatted messages, structured fields, and attached throwables.

### 17.3. Testing API responses

Verify responses contain only defined error codes and public messages, excluding:

- SQL or bind values.
- Internal exception classes unless intentionally public.
- Stack traces.
- Database hostnames, usernames, or connection URLs.
- Tokens, passwords, or PII.

### 17.4. Testing log injection

Send input containing CR/LF and confirm it neither creates extra log records nor alters event keys/severities. With structured logging, verify JSON output encodes properly so input fields cannot break out of their value fields.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Creating new exceptions without passing `cause` | Loses original exception, stack trace, and driver metadata | Use `(message, cause)` constructors |
| Appending `getMessage()` to a new exception | Can leak SQL/PII while still losing the cause chain | Use safe messages and pass `Throwable` as cause |
| Logging `error.getMessage()` unchecked | Driver messages can include sensitive values | Log error type/category and allowlisted metadata |
| Calling `log.error("...", error)` at every layer | Prints multiple cause chains, risks SQL/PII leaks, duplicates logs | Choose one final logging boundary |
| Logging full entities or request bodies | Can record passwords, tokens, PII, and payment details | Log approved allowlisted fields only |
| Enabling `TRACE` for R2DBC drivers in production | Can expose SQL and bind values | Use safe log levels; enable diagnostics under strict control |
| Returning `exception.getMessage()` to clients | Exposes schema, SQL, or infrastructure | Return error codes and generic messages |
| Using `onErrorResume` to hide all errors | Callers cannot tell technical errors from empty | Only fall back for identified error types |
| Logging untrusted input verbatim | Enables log injection/forging | Use structured logging, escape CR/LF, and bound length |
| Hashing emails with SHA-256 and calling it anonymous | Easily reversed due to small input space | Use internal IDs or keyed HMAC when appropriate |
| Redacting after logs have already shipped | Replicas, archives, or alerts may still hold raw data | Sanitize before writing or shipping |
| Putting tokens in Reactor Context/MDC | Tokens may be logged automatically by instrumentation | Carry only safe correlation/trace metadata |
| Parsing exception messages to classify errors | Fragile across driver/version/locale changes | Use SQLSTATE, vendor codes, and structured metadata |

## 19. Safe Database Error Handling Workflow

When an R2DBC operation fails, follow this sequence:

1. **Preserve the root error:** never drop `cause` when wrapping exceptions.
2. **Classify:** distinguish connection, timeout, data integrity, transaction, mapping, and other failures.
3. **Translate semantics:** when needed, map to business exceptions with messages free of sensitive data.
4. **Route errors to the right boundary:** never swallow errors before the transaction manager or caller when the use case must fail.
5. **Select log metadata:** operation code, correlation ID, error category, exception type, and permitted error codes.
6. **Strip sensitive data:** never log payloads, tokens, passwords, raw bind values, or unvetted messages.
7. **Log once at the boundary:** avoid printing the same stack trace at every layer.
8. **Respond safely:** return public HTTP statuses/error codes without causes or stack traces.
9. **Protect log sinks:** enforce access control, retention, and encryption per policy.
10. **Test:** verify the cause chain stays intact and logs/responses contain no secrets or PII.

## 20. Key Principles to Remember

- New exceptions should retain prior exceptions as `cause` via `(message, cause)` constructors.
- Never replace `cause` with `getMessage()`; strings lose exception types and can contain SQL or sensitive data.
- Use `onErrorMap` to change error types while preserving `onError`; use `onErrorResume` only when a real fallback exists.
- `doOnError` observes errors without handling or swallowing them.
- Keeping `cause` in memory does not mean dumping the entire cause chain into logs.
- Never log passwords, API keys, access/refresh tokens, private keys, session cookies, CVVs, or similar secrets.
- Never log whole entities, request/response bodies, SQL bind values, or unvetted exception messages.
- Prefer structured logging and allowlisted safe fields: operation, correlation ID, error category, exception type, and timing.
- Use structured SQLSTATE/vendor codes for classification when appropriate; avoid brittle message parsing.
- Avoid logging the same exception at every layer; designate an application boundary to emit the event.
- Structured logging and parameterized logging do not automatically sanitize data; still validate inputs.
- Defend against log injection with encoding, CR/LF removal, length caps, and disallowing input-controlled event structure.
- Never return exception messages, SQL, stack traces, or causes to API clients.
- Propagate safe correlation/trace IDs via Reactor Context; never store secrets in context just for logging.
- Protect log sinks via access control, encryption, retention, and sharing controls.
- Test both cause preservation and absence of secrets/PII in logs and responses.

Preserving error causes enables diagnosing R2DBC failures without losing Spring or driver context. Yet logs are outputs with their own lifecycle and access boundaries, so everything inside an exception must not be dumped blindly. By chaining causes cleanly, classifying errors with structured metadata, logging via allowlists, and returning controlled public responses, applications stay both debuggable and resilient against sensitive data leaks.

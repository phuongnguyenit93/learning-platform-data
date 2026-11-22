# Avoid Logging Secrets or Personal Data in Messages and Logs When Handling Exceptions in Java

## 1. Purpose of Secure Error Diagnostics

Exceptions and logs help answer **which operation failed, when, where, what type of error occurred, and how to proceed**. However, if an error is constructed from input data or dependency information, its message and stack trace can inadvertently contain passwords, tokens, cookies, customer records, request contents, or private data. When errors are written to files, stdout, monitoring platforms, crash reports, or returned over HTTP, that data can exist in multiple copies with different access permissions and retention periods.

**Principle:** only log information that is **necessary, safe, and permitted**. A good error record typically includes an event code, an allowlisted operation, a stable error code, a timestamp, a non-sensitive correlation ID, and a business status. It does not need to contain raw payloads or any credentials.

Key concepts:

- **Secret:** information used for authentication or authorization, such as passwords, API keys, access tokens, refresh tokens, JWTs, session cookies, OTPs, and private keys.
- **PII / personal data:** information relating to an identifiable person, directly or when combined with other data; for example, email, phone number, address, identifier, and activity history.
- **Exception message:** `Throwable.getMessage()` and messages attached to a `Throwable`.
- **Log sink:** any destination that receives log data, such as the console, files, cloud collectors, APM, tracing agents, audit stores, and alerting services.
- **Data minimization:** collecting and storing only the fields required for a defined purpose.

It is important to distinguish between **excluding data from logs** and **masking data in the user interface**. Both controls are necessary, and one does not replace the other.

## 2. Data Categories Especially Prone to Exposure

| Data Category | Examples | Common Risks |
| --- | --- | --- |
| Credentials | Password, token, API key, cookie, OTP | Account takeover, request spoofing |
| Identifying data | Full name, email, phone number, address | Identity exposure, unauthorized contact, profile linking |
| Context-sensitive data | Health, financial, order, or location information | Violation of privacy and trade secrets |
| Free-form request/response | JSON body, file upload, HTTP headers | Contains unpredictable values or third-party data |
| Internal information | Connection string, configuration, file paths, full SQL | Exposure of infrastructure, endpoints, and sometimes credentials |
| Correlation IDs | Request ID, trace ID, entity ID | Can link activities if not designed properly |

You cannot determine whether a field is safe just by looking at its **field name**. For example, `userId` might be a personal identifier, `requestId` sent by a client might contain an email, and `url` might have query parameters containing a token. Each field must be classified by its **source and purpose**.

The lowest-risk approach is usually **not collecting sensitive values** at all, rather than collecting them and trying to scrub them after they have already been sent to multiple places.

## 3. Exception Messages Should Not Directly Concatenate Input Data

The following patterns are **dangerous examples**, not recommended code:

```java
throw new IllegalArgumentException("Invalid password: " + password);
throw new IllegalStateException("Unexpected bearer token: " + token);
throw new IOException("Remote request failed, body=" + requestBody);
```

The variables `password`, `token`, and `requestBody` are assumed to be defined by the application. A message can pass through multiple layers as follows:

```text
User input or dependency
    -> exception message
    -> cause / suppressed exception
    -> logger / APM / console / HTTP error handler
    -> log collector, index, alert, export, backup
```

Even if a controller ultimately returns a safe response, an intermediate layer or an auto-instrumentation agent may already have recorded the raw `Throwable`.

Instead of embedding values, use an appropriate exception type and an **error classification code**:

```java
throw new IllegalArgumentException("INVALID_CREDENTIALS");
```

This is a snippet inside a method, not a standalone program. In large systems, an exception class with an `errorCode` enum can be clearer than a free-form string. Even so, whether to return the code `"INVALID_CREDENTIALS"` to the client depends on your policy against revealing account existence.

Do not assume library/SDK messages are safe. An HTTP client may include URLs, headers, or response bodies in errors; a JDBC driver may include SQL and data; many external APIs may echo user input verbatim. **Exception contents from dependencies must be treated as untrusted regarding data safety.**

## 4. Logging Calls That Can Inadvertently Disclose Data

### `getMessage()` and `toString()`

`ex.getMessage()` returns the message from the error source; `ex.toString()` typically includes the class name and localized message. Both ways of logging can output secrets:

```java
logger.error("Failed: {}", ex.getMessage());
System.err.println(ex);
```

The first line is an **SLF4J-style logging API snippet**, and the second is Java SE inside a method that has `ex`. Both are safe only if the `Throwable` data is already permitted for output through that specific sink.

### Stack traces, causes, and suppressed exceptions

`ex.printStackTrace()` or many frameworks when calling:

```java
logger.error("Operation failed", ex);
```

will log the exception type, message, stack frames, **cause chain**, and often **suppressed exceptions**. The message of `ex.getCause()` or `ex.getSuppressed()` may carry sensitive data even if the outermost exception's message has been replaced with a safe string.

Do not assume that `throw new ServiceException("Safe message", original)` sanitizes the entire exception tree. If the logger prints the cause, the message of `original` can still leak. However, you should not unconditionally strip every cause either, as that destroys diagnostic capability; instead, classify where full `Throwable` objects may be retained and where only safe events may be logged.

### DTO `toString()`

A Java `record`'s default `toString()` typically includes the values of its components. Therefore:

```java
logger.debug("request={}", request);
```

is a **framework code snippet that needs evaluation**, even when `getMessage()` is not called. If `request` contains a password or token, its string representation may print all of it. It is safer not to log whole objects containing private information, and instead build log events from allowlisted fields.

## 5. Separating Internal Errors from Public Messages

A failed request typically has at least two channels:

**Client channel:** report a stable error code, an understandable message that does not reveal system internals, and a non-sensitive request ID when needed for support.

```json
{
  "error": "SERVICE_UNAVAILABLE",
  "message": "The service is temporarily unavailable",
  "requestId": "req-7"
}
```

This is an **illustrative JSON response**; it is not a default format of Java or any framework.

**Operations channel:** record an event such as `event=OPERATION_FAILED`, `operation=FETCH_PROFILE`, `reason=UPSTREAM_UNAVAILABLE`, `request_id=req-7`, timestamp, and retry count if needed. There is no need to copy exception text from dependencies.

Do not return `ex.toString()` or a full stack trace in an HTTP 500 response. Doing so can expose tokens, input contents, class names, and internal paths. A **Request ID** used for error correlation must not act as a bearer token or grant permission to query data.

If deep troubleshooting of an incident is needed, use an access-controlled, time-bounded internal diagnostic process, rather than logging full raw exceptions by default where support teams, vendors, or clients can view them.

## 6. Field Allowlists Instead of Logging Everything and Masking Later

A typical event schema:

| Field | Appropriate Source | Requirement |
| --- | --- | --- |
| `event` | Constant/enum | Do not accept from request |
| `operation` | Enum `FETCH_PROFILE` or `CREATE_ACCOUNT` | Do not concatenate user-supplied URLs |
| `reason` | Enum `INVALID_INPUT` or `UPSTREAM_UNAVAILABLE` | Do not turn raw exception messages into codes |
| `request_id` | Opaque ID generated/controlled by infrastructure | Do not use tokens/emails as IDs |
| `duration_ms` | Runtime measurement | Do not embed payloads |
| `outcome` | Enum `SUCCESS`, `FAILURE`, `CANCELLED` | Distinguish actual outcomes |
| `dependency` | Service name from known configuration | Do not use free-form endpoints with query strings |

This is an **allowlist**: code only permits fields that have been evaluated as sufficiently safe. Structured logging with JSON or placeholders does not create security by itself. The statement:

```java
logger.warn("email={} token={}", email, token);
```

still leaks data, even though placeholders are used. The logger snippets here assume SLF4J or a similar API.

A safer approach:

```java
logger.warn("event={} operation={} reason={} request_id={}",
        "AUTH_FAILED", "SIGN_IN", "INVALID_CREDENTIALS", requestId);
```

Here, `requestId` is controlled by a trusted system. Even when using a whitelist, verify where enum/ID fields receive their values. An ID matching a valid pattern is not guaranteed to be free of personal data if it is specified by the client.

## 7. Standalone, Compilable, and Runnable Java 17+ Example

This example simulates **two exceptions containing data that must not appear in logs**: an `IOException` with an `Authorization` header in its message and an `IllegalArgumentException` with an email in its message. The handler does not log those two exceptions directly; instead, it creates **events and responses from fixed enums**.

File **`SafeExceptionLoggingDemo.java`**:

```java
import java.io.IOException;

public class SafeExceptionLoggingDemo {
    enum Operation { FETCH_PROFILE, CREATE_ACCOUNT }
    enum FailureCode { UPSTREAM_UNAVAILABLE, INVALID_INPUT }

    record ApiError(int status, String code, String message) {}

    static void fetchProfile(String authorizationHeader) throws IOException {
        // A dependency may put request content in its exception message.
        throw new IOException("remote echoed " + authorizationHeader);
    }

    static void validateEmail(String email) {
        throw new IllegalArgumentException("Rejected email: " + email);
    }

    static void audit(String requestId, Operation operation, FailureCode code) {
        if (!requestId.matches("req-[0-9]{1,6}")) {
            throw new IllegalArgumentException("invalid internal request ID");
        }
        System.out.println("event=OPERATION_FAILED request_id=" + requestId
                + " operation=" + operation + " code=" + code);
    }

    static ApiError clientError(FailureCode code) {
        return switch (code) {
            case UPSTREAM_UNAVAILABLE ->
                    new ApiError(503, "SERVICE_UNAVAILABLE",
                            "The service is temporarily unavailable");
            case INVALID_INPUT ->
                    new ApiError(400, "INVALID_INPUT",
                            "The submitted data is invalid");
        };
    }

    public static void main(String[] args) {
        String demoToken = "demo-token-not-real";
        try {
            fetchProfile("Bearer " + demoToken);
        } catch (IOException ex) {
            // Never log ex, ex.getMessage(), or the token here.
            audit("req-7", Operation.FETCH_PROFILE,
                    FailureCode.UPSTREAM_UNAVAILABLE);
            ApiError error = clientError(FailureCode.UPSTREAM_UNAVAILABLE);
            System.out.println("client_status=" + error.status()
                    + " client_code=" + error.code());
        }

        try {
            validateEmail("user@example.invalid");
        } catch (IllegalArgumentException ex) {
            audit("req-8", Operation.CREATE_ACCOUNT, FailureCode.INVALID_INPUT);
            ApiError error = clientError(FailureCode.INVALID_INPUT);
            System.out.println("client_status=" + error.status()
                    + " client_code=" + error.code());
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 SafeExceptionLoggingDemo.java
java SafeExceptionLoggingDemo
```

Verified standard output:

```text
event=OPERATION_FAILED request_id=req-7 operation=FETCH_PROFILE code=UPSTREAM_UNAVAILABLE
client_status=503 client_code=SERVICE_UNAVAILABLE
event=OPERATION_FAILED request_id=req-8 operation=CREATE_ACCOUNT code=INVALID_INPUT
client_status=400 client_code=INVALID_INPUT
```

Explanation:

1. `demoToken` is a dummy string, **not a real credential**. `fetchProfile` intentionally simulates an insecure dependency that leaks data in its exception message.
2. The `catch` block does not print the `Throwable`, message, stack trace, or header. It selects `Operation`/`FailureCode` enum values.
3. `ApiError` constructs a safe response from the error code rather than taking arbitrary content from the exception.
4. `audit` only prints controlled values. In production, use a logger configured with sinks, access controls, schemas, and retention; `System.out.println` is only used to keep the Java SE demo library-free.
5. The regex on the request ID validates **format**, and does not replace generating non-sensitive IDs from trusted infrastructure.
6. Both `record` and `switch` expressions are supported in Java 17.

Important limitation: because the simulated exception still **contains** raw data in memory, an auto-capture SDK, crash dump, or logger elsewhere could still collect it. Do not use this example as justification to allow code to create exceptions containing tokens; in real applications, you must **minimize data at the source** and inspect sinks outside the handler block.

## 8. Why Regex Filtering Alone Is Not Enough

Some applications allow logging arbitrary strings and then apply regexes to replace email patterns, `password=...`, `Bearer ...`, or card numbers with `[REDACTED]`. This can be a **supplementary defense layer**, but it is insufficient as the sole policy:

- Credentials take many forms: headers, query strings, JSON, base64, URL-encoded strings, or SDK-specific formats.
- A token may appear **without a prefix** such as `Bearer`.
- Personal data is not limited to emails/phone numbers; conversation content, addresses, or case IDs are hard to detect with regexes.
- Strings may be escaped, truncated, or contain multiple lines and control characters.
- A collector may store a copy **before** the filter is applied.
- Overly broad regexes strip useful diagnostic information; overly narrow regexes let data slip through.
- Vendors changing message formats can render old filters ineffective.

Prioritize in order: **do not collect → do not create exceptions containing secrets → choose an allowlist of fields → mask/redact at the source if truly needed → apply supplementary filtering at the collector → test all sinks**.

**Hashing does not automatically make a value anonymous.** Email hashes are vulnerable to lookup/dictionary attacks when the value domain is predictable; even pseudonymous IDs can be linked back to individuals when combined with other data. If pseudonymization/tokenization is needed, you must have a threat model, protect keys/mapping tables, and enforce appropriate access policies.

## 9. Do Not Dump Raw HTTP Requests, Responses, or SQL on Error

This is a framework code snippet that **should not be applied directly**:

```java
catch (Exception ex) {
    logger.error("headers={} body={}", headers, requestBody, ex);
}
```

`headers` may contain `Authorization`, `Cookie`, `Set-Cookie`, credentials, or user-agents containing private details. `requestBody` may be customer records or financial data. If the exception also prints its cause, the risk multiplies.

Similarly:

- Full URLs may contain sensitive query parameters; prefer operation names or **route templates**, such as `/customers/{id}`, instead of URLs with real IDs.
- SQL statements with literal values or JDBC bind parameters may contain personal data; only log statement IDs/query groups and controlled error codes when permitted.
- Response bodies from dependencies are not safe messages to broadcast in logs.
- Enabling HTTP wire logging, JDBC trace/bind logging, or APM "capture all headers" in production can cause unintended data exposure.

With client/server frameworks, the policy must cover **filters, interceptors, exception resolvers, access loggers, and HTTP clients**. Fixing only one service's `catch` block is not enough if another middleware component logs the raw request on its own.

## 10. Cause Chains, Suppressed Exceptions, and Async Worker Errors

Java has multiple paths for propagating error information:

- `throw new ServiceException("safe", cause)` retains `cause`; if the logger prints the stack trace, sensitive messages in the cause can still leak.
- `try-with-resources` can attach errors from `close()` as suppressed exceptions; secondary messages must also be evaluated.
- `Future.get()` can throw `ExecutionException` wrapping a cause from a worker.
- `CompletableFuture.join()` typically throws `CompletionException` with a cause.
- Uncaught exception handlers can print a `Throwable` without going through a controller.
- Framework schedulers can store exceptions from background tasks and report them to monitoring.

This means once a dependency puts a secret into a `Throwable`, **every observation point along the cause chain** can become a leak point. Do not check only `getMessage()` on the outermost wrapper.

If you must retain a `Throwable` for internal handling, clearly distinguish between **keeping the cause in memory** and **permission to output the full cause to a sink**. You can keep error codes/correlation IDs in regular logs and use a restricted, approved diagnostic path when detailed investigation is required. Do not automatically strip causes at every layer, as that makes root-cause identification impossible; equally, do not store raw exceptions by default in places accessible to many people.

With async work, a task can fail after the initial request has already finished. You must define ownership for observing the `Future` or stage, set a safe logging policy for workers, and avoid logging the same exception multiple times at each dependent stage.

## 11. Correlation IDs, Tracing, and MDC

Correlation IDs help link logs across multiple services to trace a request **without printing the original payload**. IDs must be generated or verified by a trusted component; never use emails, tokens, passwords, or privileged access codes as IDs.

An `X-Request-ID` sent by a client is **not inherently safe**: clients can inject personal data or control characters into it. Systems should validate length/syntax, or generate an internal ID and store a safe mapping if truly needed.

Many Java applications use `MDC` to attach request IDs to logs. This is an **illustrative SLF4J snippet** inside a class with `service` and `safeRequestId`:

```java
MDC.put("request_id", safeRequestId);
try {
    service.process();
} finally {
    MDC.remove("request_id");
}
```

You must import `org.slf4j.MDC` and have an appropriate logging configuration; this snippet is **not standalone** in Java SE. Thread pools can reuse workers; if context is not cleared, one request can be tagged with another request's metadata. `CompletableFuture` and async callbacks do not automatically inherit thread-local/MDC state from the parent context; use your framework's context propagation mechanism if available.

Do not put raw JWT claims, request headers, emails, or entire user profiles into MDC/baggage. Baggage can propagate across multiple services and downstream logs, widening the blast radius of a leak far beyond where the data originated.

## 12. Log Injection from Untrusted Input

Beyond privacy risks, attackers can inject newlines, tabs, JSON fragments, or control characters into input. If logged directly:

```java
logger.warn("Login failed for " + suppliedName);
```

a user-supplied value can forge fake log lines or deceive parsers/alerts. This is a **dangerous code snippet to recognize**, not a recommended pattern.

Ways to reduce risk:

1. Avoid placing user-supplied strings into logs unless there is an explicit need.
2. Use event names and reason codes taken from enums.
3. For free-form fields that are genuinely required, enforce length limits and normalize/encode control characters appropriate for the log format.
4. Use a standard JSON encoder rather than building JSON strings via string concatenation.
5. Verify that log readers, dashboards, and alerts do not treat log contents as trusted commands or HTML.

Parameterized logging makes working with templates more convenient, but it **does not automatically redact data** and does not completely prevent log injection if values contain control characters.

## 13. Both Application Logs and Audit Logs Must Control Data

**Application logs** serve operational diagnostics. **Security audit logs** prove the action, timestamp, and outcome of a critical event. Audit logs may have special requirements for integrity and retention, but that **does not justify logging credentials**.

Failed login events should prefer event codes and outcomes, for example:

```text
event=AUTHENTICATION_FAILURE
operation=SIGN_IN
outcome=DENIED
reason=INVALID_CREDENTIALS
request_id=req-7
```

Do not log the wrong password entered by a user "for investigation." If you must attach a principal ID, verify its necessity and read permissions; it may still be personal data. Avoid distinguishing between "account does not exist" and "wrong password" in public responses if that creates an account enumeration risk.

For both security logs and diagnostic logs, avoid using a single broadly accessible data store to save all details. If special incident troubleshooting is needed, use a tightly controlled, time-limited diagnostic environment.

## 14. DEBUG/TRACE Levels Do Not Exempt Data Protection Requirements

A common anti-pattern during production investigations: temporarily enabling DEBUG/TRACE or HTTP wire logging to "see all the data." This can cause multiple sinks to collect headers, bodies, or exception messages that do not normally appear.

Log levels are only a **condition on frequency and verbosity**, not a license to collect sensitive data.

- `ERROR`: event code, operation, request ID, and safe context.
- `WARN`: degraded state, abnormal retries, reason code.
- `INFO`: necessary operational milestones.
- `DEBUG/TRACE`: only add classified, permitted data; never include raw passwords/tokens/bodies.

If verbose logging must be enabled temporarily, there must be an owner, service scope, automatic expiration, volume monitoring, and verification of redaction/collector configuration. A check like `logger.isDebugEnabled()` only avoids computing data when DEBUG is off; **it does not prove the content will be safe when DEBUG is on**.

## 15. Protecting the Log Lifecycle After Writing

Even an event without obvious secrets can reveal activity history. You must manage:

- **Collection:** drop unnecessary fields right at the source.
- **Transport:** secure connections from appenders/agents to collectors.
- **Storage:** enforce access controls, encryption where needed, and environment separation.
- **Access:** restrict search, file export, dashboard downloads, and log-reading APIs.
- **Retention:** keep logs only for the duration required for operational/compliance purposes.
- **Replication:** be aware of backups, indexes, data warehouses, and alerts/chatops that store copies.
- **Deletion and incident response:** have a plan to assess data scope when a leak is detected.

If a **real token** is accidentally written to logs, deleting a single line may not be enough: copies may already have reached collectors, indexes, email alerts, or backups. Remediation may require revoking/rotating credentials, auditing access, purging copies where possible, and evaluating applicable notification obligations. Never use real secrets to "test whether they get logged."

## 16. Common Mistakes

| Practice | Why It Is Unsafe | Better Approach |
| --- | --- | --- |
| `throw new Exception("token=" + token)` | Token enters the message and cause | Non-sensitive error code |
| `logger.error("{}", ex.getMessage())` | Dependency content is uncontrolled | Reason code and allowlisted context |
| `logger.error("failed", ex)` without data evaluation | Stack trace/cause/suppressed may leak secrets | Per-sink policy for `Throwable` |
| `logger.debug("dto={}", dto)` | `toString()` may print password/email | Selected and classified fields |
| Logging full headers/body/SQL bind values | May contain authentication/personal data | Route template, status, statement ID |
| Returning `ex.toString()` in HTTP 500 | Exposes class names, messages, and internals | Safe public code/message |
| Filtering all strings with a single regex | Fails to detect new or encoded data | Prevent at source, allowlist, supplementary filter |
| Hashing emails and treating them as anonymous | Can be guessed and matched | Threat model, proper pseudonymization |
| Using JWT/session as request ID | Spreads credentials across services | Server-generated opaque ID |
| Logging the same exception at every async stage | Multiple log copies and wider exposure | Single owner responsible for observing errors |
| Disabling controls at DEBUG/TRACE | Leaks when incidents occur | Every level must follow policy |
| Fixing leaks only in app logs | Collectors, APM, proxies still capture data | Audit the entire log pipeline |

## 17. Testing Safe Logs and Messages

In addition to unit tests for logic, you should have integration tests that pass **easily recognizable dummy data** through real or simulated error paths, and then check all critical sinks.

| Scenario | Result to Verify |
| --- | --- |
| SDK throws exception with dummy token | Logs and client responses do not contain the token |
| Validation exception with dummy email | Email is not leaked through error responses or appenders |
| `Throwable` cause/suppressed contains dummy secret | Logger/collector does not print the raw exception |
| Request with `Authorization`/`Cookie` | Access/wire logs do not contain sensitive headers |
| DTO `toString()` contains a password field | Whole object is not dumped |
| Input contains newlines/control chars | Fake events cannot be injected |
| `Future`/`CompletableFuture` fails | Async observation path does not log raw messages |
| HTTP 4xx/5xx | Has safe error code and ID, no stack trace |
| DEBUG/TRACE enabled in tests | Data policy is still enforced |
| Logs sent to APM/collector | No raw copies exist outside the application |

Use canary strings that are **not real secrets**, such as `demo-token-not-real` or `user@example.invalid`. Tests should assert that they **do not appear** in output captured from test loggers, responses, trace events, and controlled sinks, while also asserting that safe reason codes and correlation IDs **do appear** so diagnostics remain useful.

Testing only a single `catch` block is insufficient if middleware or agents also capture `Throwable` objects automatically; tests must simulate the entire data path matching your architecture. Do not search only for `Bearer`, because tokens can appear on their own. Do not rely entirely on text snapshots of externally generated exception messages.

## 18. Checklist for Reviewing Java Exceptions/Logging

1. Every newly created exception message avoids concatenating passwords, tokens, request bodies, or PII.
2. `Throwable.getMessage()`/`toString()` is never automatically turned into an HTTP response.
3. Raw `Throwable` objects are not printed to broadly accessible sinks before their source/cause is evaluated.
4. Logs use event/operation/reason codes and allowlisted fields.
5. Correlation IDs do not contain credentials or unnecessary identifiers; data from external headers must be validated.
6. Logging does not pass whole `record`/DTO objects containing secrets through `toString()`.
7. Causes, suppressed exceptions, `CompletionException`, and `ExecutionException` are all included in safety evaluations.
8. Wire logs, SQL bind logs, APM, stderr, job schedulers, and cloud collectors are appropriately configured.
9. Redaction is a supplementary layer; regex or hashing is not treated as comprehensive protection by default.
10. Access controls, retention, encryption, backups, and incident response procedures are defined.
11. Tests using **dummy** tokens/emails confirm that logs and responses contain no raw values.
12. Operational information is still preserved: error code, operation, request ID, status, and timestamp.

**Conclusion:** to handle exceptions safely, treat messages and logs as **outputs that can be copied outside your security boundary**. Select permitted data right at the source, separate internal errors from public responses, manage the cause chain, and protect the entire logging pipeline. Good debuggability comes from clear events and safe correlation, not from storing all the data an exception happens to contain.

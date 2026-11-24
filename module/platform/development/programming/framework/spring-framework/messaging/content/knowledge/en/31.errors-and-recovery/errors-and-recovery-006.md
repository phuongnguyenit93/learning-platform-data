# Public Error Codes and Internal Diagnostic Information in Spring RSocket

## Objectives

When a request fails, the client needs to know what happened and what to do next. The operations team needs additional data to locate the real root cause inside the system. These two needs are related yet distinct: the public response must be stable, easy to handle, and avoid exposing internal structure; internal diagnostic records must be detailed enough to investigate, yet restricted to authorized systems and personnel.

In a Spring Messaging application using RSocket, design three distinct layers of information clearly:

1. **Public application error code**: a stable code such as `ORDER_ALREADY_EXISTS` or `VALIDATION_FAILED`, used by clients for branching logic.
2. **RSocket protocol error code**: numeric code in the ERROR frame, describing the protocol-layer error category.
3. **Internal diagnostic information**: exception, stack trace, root cause, trace/span ID, route, and operational context written to logs or observability systems.

Never use a single field to replace all three layers. In particular, never send internal exception messages or stack traces as if they were an API contract.

## 1. Designing a Public Error Contract

A public error should answer the questions a client can act upon:

- What is the stable error code?
- What message can a user or program understand?
- Is the error retryable or not?
- If input data is invalid, which fields need fixing?
- Is there a correlation ID to look up the issue with support/operations?

An illustrative JSON structure:

~~~json
{
  "status": "ERROR",
  "error": {
    "code": "ORDER_ALREADY_EXISTS",
    "message": "An order with this reference already exists.",
    "correlationId": "01J9Q4V8M5R6T7Y2",
    "retryable": false,
    "details": [
      {
        "field": "reference",
        "code": "DUPLICATE",
        "message": "This reference is already in use."
      }
    ]
  }
}
~~~

Each field serves a dedicated purpose:

| Field | Convention |
| --- | --- |
| `status` | Envelope status, e.g., `OK` or `ERROR` |
| `code` | Machine-readable code, stable across versions |
| `message` | Short, safe-to-display message; not used as a logic key |
| `correlationId` | Opaque ID users can give to support to locate related logs |
| `retryable` | Hint whether the failure might clear on retry |
| `details` | List of publicly allowed details, commonly used for validation errors |

Not every error requires `details`. Include only data genuinely helpful to the client. Do not put Java class names, table names, SQL statements, file paths, internal hostnames, or credentials in the envelope.

### Error Codes Must Be Stable

Clients should rely on `code`, not parse `message` text. Messages may be revised, translated, or personalized; the error code is part of the compatibility contract.

A common set of application codes:

| Public code | Meaning | Retry? |
| --- | --- | --- |
| `VALIDATION_FAILED` | Input data violates rules | No, input must be fixed |
| `AUTHENTICATION_REQUIRED` | Missing or invalid credentials | After re-authenticating |
| `ACCESS_DENIED` | Current identity lacks permission | No, unless permissions change |
| `RESOURCE_NOT_FOUND` | Resource not found per contract | Usually no |
| `STATE_CONFLICT` | Current state disallows the operation | After reloading state or resolving conflict |
| `ORDER_ALREADY_EXISTS` | Order reference is already in use | No with the same data |
| `RATE_LIMITED` | Rate limit exceeded | Yes, after waiting |
| `DEPENDENCY_UNAVAILABLE` | Dependent service temporarily unavailable | Possibly, if the operation is safe to retry |
| `INTERNAL_ERROR` | Unexpected failure, no public details | Not automatically, unless retry policy permits |

Do not return a generic code like `ERROR` for every situation. Conversely, do not create a separate code for every Java exception. Public codes describe scenarios in the application contract, not implementation class names.

When releasing new versions:

- Preserve the meaning of published codes.
- You may add new codes; clients must have a fallback branch for unknown codes.
- Do not rename or repurpose old codes for different meanings.
- Add optional fields only when compatible with older clients.
- If major structural changes are needed, version the message contract explicitly.
- You may refine message wording without forcing clients to change logic.

## 2. Distinguishing Application Error Codes from RSocket Error Codes

RSocket uses the ERROR frame (frame type `0x0B`) to convey connection-level or stream-level errors. An ERROR frame contains a Stream ID, a protocol error code, and Error Data. Error Data is specified as UTF-8 text; it is not the place to serialize entire Java exception objects.

Standard protocol codes include:

| Protocol code | Value | Meaning |
| --- | --- | --- |
| `INVALID_SETUP` | `0x00000001` | Invalid SETUP frame |
| `UNSUPPORTED_SETUP` | `0x00000002` | Unsupported SETUP parameters |
| `REJECTED_SETUP` | `0x00000003` | Responder rejected connection setup |
| `REJECTED_RESUME` | `0x00000004` | Resume rejected |
| `CONNECTION_ERROR` | `0x00000101` | Connection terminated immediately |
| `CONNECTION_CLOSE` | `0x00000102` | Connection will close after active streams complete |
| `APPLICATION_ERROR` | `0x00000201` | Application-layer error generating Reactive Streams `onError` |
| `REJECTED` | `0x00000202` | Valid request rejected by responder with guarantee it was not processed |
| `CANCELED` | `0x00000203` | Responder canceled request; processing may have started with side effects |
| `INVALID` | `0x00000204` | Invalid request |

Distinguish the `CANCEL` frame from the `CANCELED` error code:

- `CANCEL` is a frame sent by the requester to cancel a pending stream.
- `CANCELED` is a code inside an ERROR frame when the responder cancels a request; it does not guarantee side effects did not occur.

`REJECTED` carries a strong guarantee: the responder guarantees the request was not processed. Use this semantic only if the application can truly guarantee that. Do not use `REJECTED` for an error occurring after writing data or calling downstream dependencies. `CANCELED` likewise does not mean a transaction rolled back.

The protocol reserves the range `0x00000301` to `0xFFFFFFFE` for application-defined application-layer error codes. Standard protocol values should not be repurposed for custom business codes.

For example:

- `APPLICATION_ERROR` describes the protocol error category.
- `ORDER_ALREADY_EXISTS` describes the business situation understood by the client.
- `correlationId` links the response to logs.
- `errorId` or trace ID helps operators find diagnostic records.

These are distinct identifiers. If using custom numeric protocol codes, maintain a registry, document their meanings, and preserve stability across versions. If using string codes in an error envelope, define those codes at the application contract layer and do not confuse them with numeric ERROR frame codes.

## 3. Choosing How to Represent Errors in RSocket

There are two common design approaches. Pick one consistent convention per API.

### Approach A: Return an Error Envelope as Payload

With this approach, both success and failure are payloads sharing the same schema. For instance, a successful handler returns `ApiResult`; `@MessageExceptionHandler` also returns `ApiResult` with `status = ERROR`.

The advantage is that the client always decodes one response type and reads structured error codes and details. The drawback is that the protocol stream completes normally; the client must inspect `status` to detect failure. If the client skips this check, a business failure could be mistaken for success.

### Approach B: Use the RSocket Error Signal

With this approach, the handler emits an error and it travels via reactive `onError` / an RSocket ERROR frame. The client receives the error in the reactive pipeline rather than as a normal response payload. This fits well when preserving Reactive Streams semantics, especially for streams and channels.

The advantage is that errors terminate the interaction per protocol and are handled via `onError`. The drawback is that public details depend on how exceptions map to protocol errors and how the client driver decodes Error Data. Verify the exact behavior on the specific Spring and RSocket client versions used by the application.

Never return an unexpected `ApiError` type when the client expects a different success type without defining a clear envelope/union. Also never convert every exception into a default value or ignore `onError`; doing so hides errors and breaks stream semantics.

### Relationship with @MessageExceptionHandler

Spring Messaging supports `@MessageExceptionHandler` to handle exceptions thrown from `@MessageMapping` methods. Handlers can live inside the same controller or in `@ControllerAdvice` to apply across multiple controllers. These methods support parameter types and return values just like message handler methods.

Example using an envelope:

~~~java
public record FieldIssue(
        String field,
        String code,
        String message) {}

public record ApiError(
        String code,
        String message,
        String correlationId,
        boolean retryable,
        List<FieldIssue> details) {}

public record ApiResult(
        String status,
        Object data,
        ApiError error) {

    public static ApiResult success(Object data) {
        return new ApiResult("OK", data, null);
    }

    public static ApiResult failure(ApiError error) {
        return new ApiResult("ERROR", null, error);
    }
}
~~~

The handler returns the same envelope for both branches:

~~~java
@Controller
public class OrderResponder {

    private final OrderService orderService;
    private final CorrelationContext correlationContext;

    public OrderResponder(
            OrderService orderService,
            CorrelationContext correlationContext) {
        this.orderService = orderService;
        this.correlationContext = correlationContext;
    }

    @MessageMapping("orders.create")
    public Mono<ApiResult> create(CreateOrder command) {
        return orderService.create(command)
                .map(ApiResult::success);
    }

    @MessageExceptionHandler(OrderAlreadyExistsException.class)
    public Mono<ApiResult> handleDuplicate(
            OrderAlreadyExistsException exception) {

        ApiError error = new ApiError(
                "ORDER_ALREADY_EXISTS",
                "An order with this reference already exists.",
                correlationContext.currentId(),
                false,
                List.of());

        return Mono.just(ApiResult.failure(error));
    }
}
~~~

`CorrelationContext` in this example is an application-provided component; it reads a validated/normalized correlation ID from metadata or tracing context. It is not a built-in Spring class. In real applications, ensure `ApiResult` is the agreed response contract for the route: the client decodes `ApiResult` for both success and failure and checks `status`.

This example turns the exception into a normal payload. If you want the client to receive a reactive error signal, do not return `ApiResult.failure(...)`; let the error propagate via the chosen RSocket mechanism and map it at the appropriate protocol layer. `@MessageExceptionHandler` does not automatically turn a returned object into an HTTP status or a custom RSocket protocol code.

## 4. Mapping Exceptions to Public Codes

Do not let every controller decide error codes ad hoc. Centralize classification rules in an explicit layer, such as an error mapper or shared exception advice.

Example classification:

| Internal error group | Public code | Information safe to return |
| --- | --- | --- |
| Constraint violation | `VALIDATION_FAILED` | Field, constraint code, and standardized message |
| Missing credentials | `AUTHENTICATION_REQUIRED` | Prompt to re-authenticate |
| Insufficient permissions | `ACCESS_DENIED` | Generic message, without revealing internal permissions/roles |
| Entity not found | `RESOURCE_NOT_FOUND` | Resource type and public identifier if safe |
| Duplicate key or wrong state | `STATE_CONFLICT` | Next step such as reloading state |
| Rate limit | `RATE_LIMITED` | Wait interval if accurately available |
| Backend timeout/unavailable | `DEPENDENCY_UNAVAILABLE` | Notice that the service is temporarily unavailable |
| Unexpected exception | `INTERNAL_ERROR` | Generic message and correlation ID |

An important rule: classify by the semantics the client needs, not by package or exception class name. For example, several different database exceptions may all map to `STATE_CONFLICT`; the client does not need to know whether the system uses PostgreSQL, MongoDB, or another service.

Recommended processing order:

1. Catch known business errors and map them to the corresponding public code.
2. Convert validation errors into a filtered list of field issues.
3. Identify transient dependency errors and mark retryable only when justified.
4. For unexpected exceptions, return `INTERNAL_ERROR` with a correlation ID.
5. Write detailed causes to internal logs with appropriate access control.

Never use `exception.getMessage()` as the public `message`. Exception messages are written for developers and may contain input data, table names, internal URLs, or system details. Use predefined messages for each public code.

## 5. Retries, Idempotency, and Client Behavior

The `retryable` field is only a policy hint, not a promise that retrying will succeed. Clients should combine the error code, interaction type, idempotency, and retry limits.

- **Validation or authorization errors:** fix input or permissions before resending; do not retry infinitely.
- **Conflict:** reload state or ask the user to resolve the conflict; retrying the exact old request usually does not help.
- **Rate limit or dependency unavailable:** may retry after a wait, using exponential backoff and jitter.
- **Internal error:** do not auto-retry by default unless the operation is confirmed safe and covered by a retry policy.
- **Timeout or connection loss:** the processing outcome may be unknown. Never assume the server did not execute side effects.

For order creation, payment, or state-update commands, use an idempotency key or unique request ID so the server recognizes duplicate sends. Record the idempotency key and outcome within an appropriate transaction boundary. If the client retries after a timeout, the server can return the prior result instead of executing the operation again.

In RSocket:

- Request-Response can return one response or terminate with an error.
- Request-Stream and Channel may have emitted several payloads before an error terminates the stream; those payloads are not automatically retracted.
- Fire-and-Forget has no response payload for the client to receive synchronous business errors. If the client needs to know the request was accepted, use Request-Response or design an explicit acknowledgement/receipt.
- Canceling a subscription does not mean business work rolled back. Design transactions and idempotency independently of stream lifecycles.

A Spring client can observe errors in the reactive pipeline:

~~~java
return requester.route("orders.create")
        .data(command)
        .retrieveMono(OrderAccepted.class)
        .doOnError(error ->
                log.warn("RSocket request failed; route=orders.create"));
~~~

This snippet only illustrates the `onError` observation point; in practice, log the correlation/trace ID and classify errors by the exceptions the client driver actually emits. Do not log raw payloads or access tokens. If the API uses an envelope, the client must read the agreed envelope type and check `status` before accessing success data.

## 6. Recording Internal Diagnostic Information

Internal diagnostics help answer: on which route did the error occur, when, in which trace, which exception was the root cause, which dependency was involved, and which step had the request reached.

A structured log record typically includes:

| Internal field | Purpose |
| --- | --- |
| `timestamp` | Event time |
| `level` | Severity level |
| `event` | Stable event name, e.g., `rsocket_request_failed` |
| `route` | RSocket route handled |
| `interactionType` | Request-Response, Stream, Channel, or Fire-and-Forget |
| `correlationId` | Links logs across components |
| `traceId`, `spanId` | Distributed trace tracking |
| `errorId` | Incident or error record ID if tracked separately |
| `exceptionType` | Internal exception class |
| `causeChain` | Root cause and exception wrappers |
| `dependency` | Dependent service name if applicable |
| `durationMs` | Processing duration |
| `outcome` | Success, error, timeout, cancellation, or rejection |

Use structured logging instead of free-form string concatenation. Example with SLF4J:

~~~java
log.error(
        "rsocket_request_failed errorId={} route={} publicCode={} traceId={}",
        errorId,
        route,
        "INTERNAL_ERROR",
        traceId,
        exception);
~~~

Passing the exception as the final argument tells the logger to write the stack trace to internal logs. Write it only to sinks protected by appropriate access controls, retention limits, and data-protection procedures. For expected business errors like duplicates or validation failures, log at an appropriate level without per-request stack traces to avoid log noise.

Do not log raw payloads by default. Payloads can contain passwords, tokens, personal data, payment details, or user-controlled content. When data is needed for diagnosis, log normalized allow-listed attributes, masking or hashing identifiers appropriately. Strip secrets, access tokens, session IDs, connection strings, encryption keys, and sensitive fields. Sanitize control characters like CR/LF to prevent log injection.

Never write stack traces or internal exception messages into the error envelope, RSocket Error Data, or user-facing messages. Expose only an opaque correlation ID and vetted messages. Users provide the correlation ID to support; authorized staff use it to look up the corresponding logs, traces, and errorId.

## 7. Correlation IDs and Distributed Tracing

A correlation ID links one operation from the client across multiple components. Trace IDs and span IDs belong to the distributed tracing model; they can complement a correlation ID without necessarily replacing it.

An implementation flow:

1. Client creates or receives a unique request ID for the operation.
2. Client sends the ID in metadata per application convention; if using W3C Trace Context, propagate trace context via compatible instrumentation.
3. Server validates format, length bounds, and allowed characters. Client-supplied metadata is untrusted data; never use it for authentication or authorization.
4. If missing or malformed, server generates a fresh correlation ID.
5. Put the ID into context propagated across reactive pipelines and downstream calls.
6. Attach the ID to logs, traces, and the public error envelope.
7. Client provides this ID to support for lookup.

Do not use an arbitrary `ThreadLocal` to propagate context across Reactor; execution can switch threads. Prefer context propagation/tracing mechanisms supported by the framework and instrumentation. Never let clients pick arbitrary values as trusted trace identities or overwrite trusted trace data.

A correlation ID is neither a secret nor a credential. Knowing the ID must not grant extra permission to read logs or access resources. Observability systems must still enforce access controls independently.

## 8. Security and Privacy When Returning Errors

Public errors are part of the attack surface. Overly detailed messages can help callers enumerate resources, infrastructure topology, table names, or implementation details.

Apply these principles:

- Return the same safe message for scenarios where distinguishing them would reveal the existence of a resource or identity.
- Never return stack traces, exception classes, SQL, internal commands, file paths, hostnames, private IP addresses, or configurations.
- Never echo raw untrusted input back into responses or logs.
- Cap the count of field errors and message lengths to prevent oversized responses/logs.
- Never put tokens, passwords, cookies, session identifiers, or secrets into logs.
- Enforce access control, retention periods, and export restrictions on logs/tracing.
- Record authentication, authorization, deserialization, and anomalous failures under monitoring policy.
- Ensure error content can be localized without changing error codes.

For validation, return only field names from the public contract and standardized constraint codes. Avoid returning default messages generated by validators or frameworks unless they have been reviewed.

## 9. Testing the Error Contract

Test both the returned content and interaction behavior:

1. **Mapping unit test:** every business exception maps to the right public code, message, retryable flag, and details.
2. **Fallback test:** unexpected exceptions always return `INTERNAL_ERROR`; the response contains no exception message, stack trace, or sensitive data.
3. **Controller test:** `@MessageExceptionHandler` or `@ControllerAdvice` is invoked and builds the expected envelope.
4. **RSocket integration test:** a client using `RSocketRequester` sends requests over real routes and verifies the payload envelope or error signal per the chosen contract.
5. **Stream test:** mid-stream errors terminate the stream per convention; the client does not assume already-received items are retracted.
6. **Retry test:** retries happen only for errors marked eligible; non-idempotent commands do not produce duplicate side effects.
7. **Observability test:** correlation ID appears in related logs/traces and can be looked up; secret payloads never appear in logs.
8. **Compatibility test:** older clients handle unknown error codes and new optional fields gracefully.

Do not check merely that the client received an exception. Verify the exact public code, schema, information exposure level, retry behavior, and that internal diagnostics still locate the root cause.

## 10. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using exception message as error code | Codes change across code edits or library versions | Use stable public codes |
| Returning stack traces to clients | Leaks internal structure and data | Log stack traces only to protected internal sinks |
| Using RSocket protocol codes as business codes | Mixes transport and domain layers | Separate protocol codes from application codes |
| Using `REJECTED` after partial processing | Client mistakenly believes no side effects occurred | Use REJECTED only when non-processing is guaranteed |
| Retrying every `onError` | Generates repeat load or duplicate side effects | Classify errors and use idempotency keys |
| Turning errors into payloads without client checking `status` | Failures are treated as successes | Use a consistent envelope and check status |
| Logging entire requests | Leaks tokens, PII, and confidential data | Structured logging with allow-lists and redaction |
| Using correlation ID as a security mechanism | Can be spoofed or abused | Use dedicated authentication/authorization |
| Using one `INTERNAL_ERROR` code for everything without saving context | Hard to locate the real cause | Attach errorId, traceId, route, and cause in internal logs |

## 11. Implementation Checklist

- [ ] Public error codes have stable names, documented meanings, and are never repurposed.
- [ ] Protocol error codes are kept distinct from application/domain codes.
- [ ] Error envelope has a consistent schema for success and failure if using payload envelopes.
- [ ] `@MessageExceptionHandler` or `@ControllerAdvice` maps errors at the Spring Messaging layer.
- [ ] Unexpected exceptions are converted to generic, safe messages.
- [ ] Retryable accurately reflects transience and operation idempotency.
- [ ] Correlation ID is validated, generated when needed, and propagated across reactive context.
- [ ] Trace/span IDs and errorId are recorded in appropriate logs/tracing.
- [ ] Stack traces and root causes remain exclusively in protected internal diagnostic systems.
- [ ] Payloads, tokens, PII, and secrets are not logged by default.
- [ ] Request-Response, Stream, Channel, and Fire-and-Forget are tested against the contract.
- [ ] Clients handle unknown error codes and do not depend on message text.

## References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models and Spring Messaging RSocket support.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): auto-configuration of `RSocketMessageHandler`, `@ControllerAdvice`, and `RSocketRequester`.
- [Spring Framework — Annotated Controllers: @MessageExceptionHandler](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): exception handler scope, return values, and `@ControllerAdvice` in Spring Messaging.
- [RSocket Protocol — ERROR frame](https://rsocket.io/about/protocol/): error frames, standard protocol codes, Error Data, and semantics of REJECTED/CANCELED/INVALID.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data to omit, mask, or protect in logs.


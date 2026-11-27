# Safe Error Messages

A GraphQL API needs error messages clear enough for clients to know what to do, yet must never leak internal details such as SQL queries, table names, hostnames, stack traces, tokens, or sensitive data. **Safe error messages** are messages designed for the right audience: clients receive public error codes and actionable guidance; operations teams keep technical details in controlled logs.

In Spring for GraphQL, exceptions can arise during argument binding, data validation, resolver execution, or downstream service calls. Applications need to distinguish these stages, standardize the GraphQL error contract, and include only approved data in responses. Do not return raw exception messages to clients merely because they are convenient for debugging.

## 1. Why are safe error messages needed?

Suppose a user registration mutation calls a service to save data. The database might throw an exception containing a constraint name, schema name, or SQL statement. If the resolver returns that message directly, the client may receive unnecessary information about database internals.

Unsafe message example:

~~~text
duplicate key value violates unique constraint "uk_users_email"
Detail: Key (email)=(person@example.com) already exists.
SQL: insert into internal_schema.users ...
~~~

Clients do not need to know constraint names, SQL statements, or internal schemas. The API can return a designed message:

~~~json
{
  "errors": [
    {
      "message": "An account with this email already exists",
      "extensions": {
        "code": "EMAIL_ALREADY_REGISTERED"
      }
    }
  ]
}
~~~

This message informs the client of the next step without revealing how the database stores data. The original exception details can still be written to internal logs with appropriate access controls.

Safe messages should achieve three goals:

- **Useful:** the client understands which category the error belongs to and can handle it via a stable code.
- **Minimal:** return only information necessary for the caller, without putting internal data into the response.
- **Consistent:** the same business error is represented with the same contract across resolvers and entry points.

## 2. Distinguishing error stages

Not every GraphQL error goes through the same mechanism. Identify whether an error occurs before execution, inside a DataFetcher, or at the HTTP layer:

| Stage | Example | Appropriate handling place |
| --- | --- | --- |
| HTTP/transport | Malformed request body, invalid headers | Web/transport layer |
| Pre-GraphQL authentication | Missing or expired token in security filter | Spring Security |
| Parse | Syntactically invalid GraphQL document | GraphQL engine |
| Validation | Non-existent field, wrong argument type | GraphQL validation |
| Variable coercion | Missing non-null variable or value incompatible with scalar | GraphQL execution preparation |
| Argument binding | Unable to bind input to target Java type | Spring for GraphQL argument binding |
| Bean/domain validation | Malformed email, quantity exceeding business limit | Validation/application service |
| DataFetcher execution | Service throws exception when resolving a field | DataFetcherExceptionResolver or @GraphQlExceptionHandler |
| Async completion | CompletableFuture/Mono completes exceptionally | GraphQL execution exception handling mechanism |

**DataFetcherExceptionResolver** handles exceptions raised during DataFetcher execution. It is not the place to handle document syntax errors, schema validation errors, or HTTP errors occurring before the GraphQL handler is called.

Distinguishing stages helps place messages at the right layer. For example, GraphQL can report on its own that a required argument is missing before the controller is called; whereas the rule that an email must belong to a valid domain usually needs to be checked at the application layer.

## 3. Structure of a GraphQL error response

A GraphQL response can contain both data and errors. An error on one field does not necessarily fail the entire operation:

~~~json
{
  "data": {
    "profile": {
      "displayName": "An"
    },
    "orders": null
  },
  "errors": [
    {
      "message": "Orders are temporarily unavailable",
      "path": ["orders"],
      "extensions": {
        "code": "ORDERS_UNAVAILABLE"
      }
    }
  ]
}
~~~

Key components:

- **message:** message intended for the client. This is content that must be strictly controlled.
- **locations:** line/column position of the field in the GraphQL document if the error is associated with a location.
- **path:** response path to the field that produced the error. Path uses aliases if the client supplied aliases and may contain list indices.
- **extensions:** additional metadata, commonly containing error codes, error categories, or a filtered list of input violations.

Path is not the path to a property inside an input object. For example, if an error occurs when the register field resolver processes input.email, the GraphQL path typically points to the response field register. If the client needs to know which input property is invalid, put a safe list of field violations into extensions according to a separate contract.

HTTP status is not the only way to determine the outcome of a GraphQL operation. An execution can return a successful HTTP response at the transport layer while still having entries in errors. Clients need to inspect both data and errors, then use extensions.code to decide how to handle them.

## 4. Designing a stable error contract

Do not force clients to parse messages to determine the error type. Messages can be edited, translated into other languages, or reworded. Use stable error codes in extensions:

~~~json
{
  "message": "The requested book could not be found",
  "extensions": {
    "code": "BOOK_NOT_FOUND",
    "category": "NOT_FOUND"
  }
}
~~~

A simple contract can include:

| Field | Meaning | Rule |
| --- | --- | --- |
| message | Message for display or client support | Contains no internal details or sensitive values |
| extensions.code | Machine-readable error code | Stable, unique within the API scope |
| extensions.category | High-level error category | Chosen from a published set of values |
| extensions.violations | List of per-field input errors | Includes only public field names, codes, and safe messages |
| extensions.correlationId | Reference ID to help look up logs if policy allows | Never used as authentication info |

You do not need to include all of these fields in every error. Send only the metadata needed for the corresponding error type. In particular, never put exception classes, stack traces, SQL, internal hosts, raw requests, or rejected values into extensions.

Maintain a catalog of error codes in the application and API documentation. When messages change, clients still rely on the existing codes. If a code needs to be retired, manage it as a versioned contract change or with a compatibility deprecation path.

## 5. Per-field validation messages

With input objects, a single request can have multiple errors at once. Instead of returning only one generic message, the API can return a list of violations so the client can highlight each field on a form.

Example schema:

~~~graphql
input RegisterInput {
    email: String!
    password: String!
    displayName: String!
}

type Mutation {
    register(input: RegisterInput!): User!
}
~~~

A safe validation response:

~~~json
{
  "errors": [
    {
      "message": "Input validation failed",
      "path": ["register"],
      "extensions": {
        "code": "VALIDATION_FAILED",
        "violations": [
          {
            "field": "email",
            "code": "INVALID_FORMAT",
            "message": "Enter a valid email address"
          },
          {
            "field": "password",
            "code": "TOO_SHORT",
            "message": "Password does not meet the minimum length"
          }
        ]
      }
    }
  ]
}
~~~

Here the API does not echo the password, submitted email, or rejected value. The client still knows which fields need fixing. Field names in violations must be public GraphQL input names, not database column names or internal property names if the two differ.

With nested inputs, field paths can look like address.postalCode or items[0].quantity. Standardize the path format so clients can map to the corresponding control. Do not include erroneous values in violations unless the data is non-sensitive and there is a clear reason.

## 6. Creating a safe validation error model

You can represent a violation with a dedicated data type:

~~~java
public record FieldViolation(
        String field,
        String code,
        String message) {
}

public class InputValidationException extends RuntimeException {

    private final List<FieldViolation> violations;

    public InputValidationException(List<FieldViolation> violations) {
        super("Input validation failed");
        this.violations = List.copyOf(violations);
    }

    public List<FieldViolation> getViolations() {
        return violations;
    }
}
~~~

This exception carries only normalized data meant for public disclosure. Do not store rejected values or the entire input object inside the exception if the input might contain passwords, tokens, or personal data.

The service can check inputs and construct violations according to defined rules:

~~~java
public void validate(RegisterInput input) {
    List<FieldViolation> violations = new ArrayList<>();

    if (input.email() == null || !EMAIL_PATTERN.matcher(input.email()).matches()) {
        violations.add(new FieldViolation(
            "email", "INVALID_FORMAT", "Enter a valid email address"));
    }

    if (input.password() == null || input.password().length() < 12) {
        violations.add(new FieldViolation(
            "password", "TOO_SHORT",
            "Password does not meet the minimum length"));
    }

    if (input.displayName() == null || input.displayName().isBlank()) {
        violations.add(new FieldViolation(
            "displayName", "REQUIRED", "Display name is required"));
    }

    if (!violations.isEmpty()) {
        throw new InputValidationException(violations);
    }
}
~~~

This example illustrates controlling messages and codes at the application layer. In a real project, use Bean Validation for appropriate constraints and convert results into public violations through a centralized mapper.

## 7. Using Bean Validation without leaking rejected values

Spring applications can use Jakarta Bean Validation with constraints like **@NotBlank**, **@Email**, **@Size**, **@Min**, and **@Max**. The GraphQL schema checks types and nullability; Bean Validation checks deeper data rules.

Example input DTO:

~~~java
public record RegisterInput(
        @NotBlank
        @Email
        String email,

        @NotBlank
        @Size(min = 12, max = 128)
        String password,

        @NotBlank
        @Size(max = 80)
        String displayName) {
}
~~~

When receiving validation violations, do not serialize the raw ConstraintViolation or BindingResult directly to the client. Those objects may contain invalid values, root objects, internal property paths, and message templates unsuitable for a public API.

Instead, a mapper should:

1. Extract the necessary property path and translate it to the public GraphQL field name.
2. Determine the constraint/code from an allowlist.
3. Choose an approved safe message.
4. Strip rejected values and all internal object metadata.
5. Cap the number of violations so the response cannot bloat.

Example mapping by constraint name:

~~~java
private FieldViolation toPublicViolation(ConstraintViolation<?> violation) {
    String field = violation.getPropertyPath().toString();
    String annotationName = violation.getConstraintDescriptor()
        .getAnnotation().annotationType().getSimpleName();

    return switch (annotationName) {
        case "NotBlank" -> new FieldViolation(
            field, "REQUIRED", "This field is required");
        case "Email" -> new FieldViolation(
            field, "INVALID_FORMAT", "Enter a valid email address");
        case "Size" -> new FieldViolation(
            field, "INVALID_LENGTH", "The value has an invalid length");
        default -> new FieldViolation(
            field, "INVALID_VALUE", "The value is invalid");
    };
}
~~~

This is a simplified example; a real mapper needs to consider constraint groups, nested paths, class-level constraints, and public field names. Do not send violation.getMessage() directly if message bundles might contain interpolated values or developer-oriented text. If using controlled message templates without rejected values, you can use them as the message source after review.

## 8. Mapping exceptions to GraphQL errors in Spring

For exceptions raised from a DataFetcher, Spring for GraphQL provides **DataFetcherExceptionResolver** and **DataFetcherExceptionResolverAdapter**. You can map InputValidationException into a GraphQLError with a stable code:

~~~java
@Component
public class SafeValidationExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable ex, DataFetchingEnvironment environment) {

        if (ex instanceof InputValidationException validationException) {
            List<Map<String, String>> violations =
                validationException.getViolations().stream()
                    .map(v -> Map.of(
                        "field", v.field(),
                        "code", v.code(),
                        "message", v.message()))
                    .toList();

            return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.BAD_REQUEST)
                .message("Input validation failed")
                .extensions(Map.of(
                    "code", "VALIDATION_FAILED",
                    "violations", violations))
                .build();
        }

        return null;
    }
}
~~~

**GraphqlErrorBuilder.newError(environment)** binds the error to the executing field, so GraphQL preserves the appropriate path and location. The resolver handles only known exception types; for other exceptions, it returns null so the next resolver or default handler processes them.

You can use **@GraphQlExceptionHandler** in a controller or **@ControllerAdvice** to organize mappings by exception type. Whichever mechanism you choose, share a common mapper and error contract so the same error does not have different messages or codes depending on the controller.

Do not write a catch-all resolver returning ex.getMessage() for every exception. Database exceptions, HTTP client exceptions, or programming bugs can contain data not meant for clients.

## 9. Handling unexpected exceptions

For unrecognized exceptions, responses should use a generic message:

~~~json
{
  "errors": [
    {
      "message": "An unexpected error occurred",
      "path": ["register"],
      "extensions": {
        "code": "INTERNAL_ERROR"
      }
    }
  ]
}
~~~

Original exception details are recorded in server logs with a correlation ID for operations teams to investigate. Spring for GraphQL has default handling for exceptions not handled by custom resolvers; keep the behavior that hides internal details in production and do not replace it with raw exception messages.

Key principles:

- Do not return stack traces, exception classes, or cause chains.
- Do not return SQL statements, table names, constraints, connection strings, or hostnames.
- Do not return tokens, cookies, passwords, API keys, or authentication headers.
- Do not return raw requests, variables, or rejected values.
- Do not return file paths, source directories, or internal package names.
- Do not turn system errors into successes with empty data unless there is an explicit business fallback.

In development environments, detailed logging can be enabled on the server to aid debugging. Do not enable displaying stack traces or exception details to production clients. Using a development profile does not mean every external request is permitted to see internal information.

## 10. Prevent error messages from leaking data existence

Error messages can create an **enumeration side channel**: callers probe whether an email, account, order, or resource exists.

For example, a password reset API returns:

- "Email does not exist" when the address is unregistered.
- "Reset email sent" when the address is registered.

Callers can use the responses to harvest a list of accounts. For this use case, return the same generic message in both cases, such as "If the account is eligible, instructions will be sent".

Similarly, if distinguishing NOT_FOUND from FORBIDDEN reveals resource existence, use a generic message and unified policy. Not every API needs to hide NOT_FOUND; the decision depends on the resource's sensitivity and threat model.

Beyond messages, pay attention to:

- Response shapes and extensions should not accidentally vary based on secret state.
- Processing times should not exhibit noticeable differences if exploitable.
- Authorization must be checked on the server, not based on whether the client selected a field.
- DataLoaders/batch queries must enforce tenant and access permissions per key.

Never use Correlation IDs, request IDs, or error codes as proof of authentication. They are strictly observability metadata.

## 11. Designing error messages by environment and language

User-facing messages may need localization; machine-facing error codes should remain stable. For example, the same VALIDATION_FAILED code can have a Vietnamese or English message depending on the locale, while clients still process by code and field path.

Do not let clients depend on specific wording. You can define:

~~~json
{
  "message": "Input data is invalid",
  "extensions": {
    "code": "VALIDATION_FAILED",
    "violations": [
      {
        "field": "email",
        "code": "INVALID_FORMAT",
        "message": "Please enter a valid email address"
      }
    ]
  }
}
~~~

If the application uses MessageSource, choose message keys from a controlled list of codes and resolve them by Locale in the GraphQLContext or request context. Do not use arbitrary exception messages as message keys.

Limit message length, violation count, and extensions size. A huge input object could generate thousands of errors; returning all errors would bloat the response and could be abused. You can cap the returned violations and add safe metadata indicating the list was truncated.

## 12. Logging, Correlation IDs, and protecting logs

Clients need safe messages; operators need sufficient detail to investigate. These two goals should be met on two separate channels:

| Channel | Appropriate content |
| --- | --- |
| GraphQL response | Public message, stable error code, filtered field violations |
| Application log | Original exception, stack trace when needed, operation/field name, and correlation ID |
| Trace/metrics | Latency, dependencies, error category, and trace/span context |

Structured log example:

~~~java
log.error(
    "GraphQL field failed: correlationId={}, field={}, errorCode={}",
    correlationId, fieldName, "INTERNAL_ERROR", exception);
~~~

Do not log full GraphQL variables by default. Variables may contain passwords, emails, addresses, tokens, or payment data. If logging inputs is necessary for investigation, filter by an allowlist, mask sensitive data, and restrict log access permissions.

A Correlation ID helps locate related logs, but does not replace a trace ID. If the application uses Micrometer Tracing or OpenTelemetry, let the framework manage distributed trace propagation and add correlation IDs only according to the system's observability policy.

Logs are also an attack surface. Do not write unvalidated strings containing CR/LF or control characters into logs in ways that could forge log entries. Use structured logging and cap sizes of client-controlled values.

## 13. Partial data, nullability, and error messages

When a field encounters an exception, GraphQL creates an error and handles the field's value according to nullability:

- If the field is nullable, that field can become null while other fields still return data.
- If the field is non-null, null bubbles up to the nearest nullable parent.
- The error path still points to the original field that caused the error, even though the null position in data propagated up to a parent.

Example:

~~~graphql
type Query {
    book: Book
}

type Book {
    title: String!
    reviews: [Review!]!
}
~~~

If the reviews resolver fails, the non-null reviews field causes the Book value to become null since Query.book is nullable. If Query.book were also non-null, null could propagate all the way to the root data.

Do not replace exceptions with null just to avoid showing errors. Doing so can hide system failures and mislead clients into thinking no data exists. Return null only when null is a valid outcome under business rules and the schema.

## 14. Testing safe error messages with GraphQlTester

Tests should not only verify that an error is present, but also verify that the response **contains no sensitive data**. Example with a validation error:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        mutation {
            register(input: {
                email: "not-an-email"
                password: "short-secret"
                displayName: ""
            }) {
                id
            }
        }
        """)
    .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).anySatisfy(error ->
        assertThat(error.getExtensions().get("code"))
            .isEqualTo("VALIDATION_FAILED"));

    assertThat(errors).allSatisfy(error -> {
        assertThat(error.getMessage()).doesNotContain("short-secret");
        assertThat(error.getMessage()).doesNotContain("not-an-email");
        assertThat(error.getExtensions().toString())
            .doesNotContain("short-secret", "not-an-email");
    });
});
~~~

This is an illustrative example; specific assertion APIs may be adjusted according to your GraphQlTester version. In real tests, read message and extensions from the error response and assert each field.

Scenarios to test:

1. Validation errors have the expected code and field path.
2. Sensitive rejected values do not appear in message or extensions.
3. Unknown exceptions return a generic message without stack traces or causes.
4. Database exceptions do not leak SQL, table names, or constraints.
5. Error paths are accurate when using aliases and nested fields.
6. Partial data remains present when another field fails and nullability permits.
7. Sensitive account/resource existence is not disclosed.
8. Correlation IDs can be found in logs but are not used as access credentials.
9. Logs do not contain passwords, tokens, or raw variables.
10. The count and size of field violations are bounded.

Include integration tests over HTTP/WebGraphQlTester to verify the actual configuration of Spring Security, interceptors, exception resolvers, and GraphQL responses. Mapper unit tests only prove the conversion function works; they do not prove the entire request path is safe.

## 15. Common mistakes

| Anti-pattern | Risk | Fix |
| --- | --- | --- |
| Returning ex.getMessage() directly | Leaks SQL, hostnames, constraints, or sensitive data | Use defined public messages and error codes |
| Serializing ConstraintViolation directly | May leak rejected values and internal objects | Map to an allowlisted FieldViolation |
| Client parses messages to branch logic | Messages change across languages or versions | Use stable extensions.code |
| Putting exception class/stack trace into extensions | Reveals implementation structure | Keep details in internal logs |
| Returning distinct messages for existing/non-existing accounts | Enables account enumeration | Use a shared response if the resource is sensitive |
| Turning every error into null | Masks errors and misleads clients | Use null only for valid nullable outcomes |
| Using resolvers to handle parse/validation errors | Wrong lifecycle; resolver is never called | Handle at the GraphQL validation/request layer |
| Logging all variables | Leaks passwords, tokens, PII | Allowlist/mask and use structured logging |
| Returning too many violations | Bloated responses, easy to abuse | Cap count and size |
| Using correlation ID as security identity | Can be forged or guessed | Use authenticated principals and real authorization |

## 16. Public error design checklist

Before releasing a new error type, answer:

- Does the client need to know this exact reason, or is a generic message safer?
- Does the message contain client-submitted data, rejected values, or internal details?
- Is there a stable code so clients can handle it without parsing the message?
- If it is a validation error, does the field path match the public input name?
- Do extensions contain only allowlisted data?
- Are error path/locations preserved with DataFetchingEnvironment when the error ties to a field?
- Does nullability produce the expected partial response?
- Do internal logs contain the necessary correlation/trace ID and original exception?
- Is there any enumeration or timing side-channel risk?
- Do tests prove sensitive data never appears in responses or logs?

## 17. Design principles

Design a unified error contract for the entire Spring for GraphQL API. Use safe messages and stable codes; put only filtered field violations into extensions; never serialize exceptions, BindingResult, or ConstraintViolation directly. Distinguish parse/validation, argument binding, domain validation, DataFetcher execution, and transport errors so each is handled at the right layer.

For known exceptions, map them via DataFetcherExceptionResolver or @GraphQlExceptionHandler. For unexpected exceptions, keep messages generic for clients and log details in controlled server logs. Protect sensitive data in both responses and logs, while paying attention to account enumeration, null propagation, and partial data.

A good error message is not the one with the most details. It is a contract that helps clients understand and handle the situation while revealing only the exact information the caller is permitted to know.

# Input Validation and Injection Prevention in Functions

Serverless functions often receive data from HTTP requests, message queues, event buses, webhooks, object storage, or another function. Even when the data source is inside the same cloud account or arrives through an authenticated gateway, the content can still be malformed, stale, spoofed, or intentionally crafted to alter the statements or commands the function executes.

**Input validation** checks whether data conforms to the expected structure, bounds, and business rules. **Injection prevention** ensures untrusted data is treated strictly as data, rather than interpreted as SQL statements, query expressions, OS commands, paths, templates, or executable content. The two are related but not interchangeable: a string may be valid according to a schema yet still dangerous if concatenated directly into a SQL statement or shell command.

In Java serverless applications, every trigger is a data-ingestion boundary. API Gateway can enforce request size limits or validate tokens, but the function must still verify the input contract and permissions on specific resources. Messages from queues also need validation because producers can have bugs, old events can be replayed, and payloads can evolve in schema. The goal is to ensure all data entering business logic is strongly typed, clearly bounded, and used safely in each context.

## 1. Identifying trust boundaries and data sources

Start by listing every data source entering the function. Do not treat only the HTTP body as untrusted input; data can come from path parameters, query strings, headers, cookies, file uploads, event metadata, message bodies, object keys, or responses from external services.

| Source | Examples | Risks to check |
|---|---|---|
| HTTP path/query | orderId, limit, sort, filter | IDOR, injection, oversized values, arbitrary filter expressions |
| HTTP body | Order creation JSON | Invalid schema, extra fields, unexpected types, out-of-bounds values |
| HTTP header/cookie | Authorization, forwarded headers, custom headers | Spoofed headers, CRLF injection, wrong-audience tokens |
| Message queue | OrderCreated event | Duplicates, old schemas, mismatched tenant, malicious payloads |
| Event bus | ObjectCreated or domain events | Spoofed events, unexpected sources, replays |
| Webhook | Payment or partner systems | Invalid signatures, replays, schema-invalid payloads |
| Object storage | File uploads, object keys | Malicious files, path traversal, ZIP Slip, mismatched content types |
| External services | URLs, filenames, API data | SSRF, oversized responses, untrusted data |

A trust boundary exists whenever data crosses from a user, tenant, account, organization, or system with a different security policy into the function. Clearly mark where identity is authenticated, where permissions are checked, and where content is validated.

In particular, **authenticating the sender does not prove the payload is valid**. A message published by a valid IAM principal can still contain a nonexistent orderId, a wrong tenantId, or a value crafted from malicious input. Similarly, a valid JWT only proves identity and verified claims; the function still must check which resources the user is permitted to operate on.

## 2. Three layers of validation: syntax, semantics, and authorization

Safe input must pass multiple layers of checks:

1. **Syntax and structure:** JSON parses cleanly, fields have the right types, enums are valid, and path parameters match expected formats.
2. **Bounds and semantics:** strings are not overly long, numbers fall within valid ranges, collections have allowed sizes, dates are reasonable, and business state permits the operation.
3. **Access authorization:** the caller is allowed to read or modify the specific resource, tenant, and attributes.

For example, a request might contain a positive integer quantity yet still not be allowed to purchase that product. An orderId might have a valid UUID format yet belong to another tenant. A filter might be syntactically valid JSON yet trigger an overly broad query that exhausts resources.

Gateway validation rejects malformed requests early and reduces load. Function validation protects business logic when a function is invoked from multiple triggers or called directly. The domain layer must protect invariants before writing to the database. Database constraints and conditional writes protect against race conditions under concurrent invocations.

Do not rely on a single layer. If a gateway validates schemas while a queue trigger invokes the same domain service, the domain service must still enforce business rules.

## 3. Using allowlists and explicit bounds

Prefer allowlists: define precisely which values are accepted. Blocklists that try to enumerate dangerous strings are easily bypassed because of different encodings, syntaxes, and representations.

Examples:

- Order status accepts only published enum values.
- Sort field accepts only one of the supported fields.
- Page size lies between 1 and a maximum limit.
- Currency is drawn from the set of currencies supported by the system.
- Filenames, extensions, and object prefixes follow defined rules.
- Target URLs belong only to allowed hosts.
- Custom headers accept only published formats and lengths.

Do not use an overly broad regex to replace schemas and business rules. Keep regexes short, bound input length, and avoid patterns prone to catastrophic backtracking. For identifiers, use dedicated parsers or specialized data types when available.

Example of validating page size:

~~~java
public int validatePageSize(Integer requested) {
    if (requested == null) {
        return 25;
    }

    if (requested < 1 || requested > 100) {
        throw new ValidationException(
                "pageSize must be between 1 and 100"
        );
    }

    return requested;
}
~~~

Do not silently clamp an invalid value to the limit if doing so hides client bugs or alters business meaning. Choose a consistent contract: apply a default when a field is omitted, but return an error when the caller supplies an out-of-range value.

For monetary amounts, use BigDecimal or integer types in minor units instead of float/double. Check scale, precision, sign, and business bounds. For arithmetic with overflow risk, use exact operations such as Math.addExact when appropriate or check bounds before computing.

## 4. Validating JSON and DTOs in Java

Do not pass raw JSON maps throughout the application. Parse into typed DTOs, validate fields, and convert into internal commands before calling domain services. DTOs should contain only the fields the API permits; avoid binding requests directly to database entities because clients could supply extra fields such as role, ownerId, status, or tenantId.

Example using Jakarta Bean Validation:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank
        @Size(max = 64)
        String customerReference,

        @NotEmpty
        @Size(max = 50)
        java.util.List<@Valid OrderLineRequest> items
) {}

public record OrderLineRequest(
        @NotBlank
        @Size(max = 40)
        String productId,

        @Positive
        int quantity
) {}
~~~

The function can use a Validator to check the DTO:

~~~java
public <T> void validate(T input, Validator validator) {
    Set<ConstraintViolation<T>> violations =
            validator.validate(input);

    if (!violations.isEmpty()) {
        throw new ValidationException(
                "Request does not satisfy the input contract"
        );
    }
}
~~~

This is an illustrative example; configure a Jakarta Validation implementation appropriate for your runtime or framework. When returning errors, you may return an error code and list of invalid fields, but never include stack traces, sensitive values, or the full payload in the response.

Set limits before and during parsing:

- Maximum HTTP body size at the gateway and adapter.
- Maximum nesting depth and collection element count.
- Limits on string length, field count, and array length.
- Strict numeric types; reject out-of-range values or unexpected formats.
- Processing time limits and avoiding parsing huge payloads in memory.
- Do not enable broad polymorphic deserialization for untrusted data.

Schema validation only checks shape. After parsing, you still need to check cross-field relationships, access permissions, and business state.

## 5. Canonicalizing data before validation

Some inputs have multiple representations of the same value: URL encoding, Unicode normalization, path separators, percent-encoded characters, or letter casing. If one layer validates one representation while a downstream layer decodes or normalizes differently, an attacker can bypass checks.

Principles:

- Define one consistent canonicalization workflow for each input type.
- Decode according to the contract and only once at the appropriate boundary.
- Validate on the exact representation used by the next step.
- Avoid decoding again inside repositories or services.
- Normalize Unicode when business logic requires string equivalence comparisons.
- For hostnames, handle IDNs and casing according to URL rules.
- For paths, use the Path API instead of manually replacing slashes or concatenating strings.

Do not normalize every string the same way. For example, Unicode normalization may suit usernames but should not silently alter free-form content or signed data. If a webhook signature is computed over the raw body, verify the signature on the exact byte representation signed by the partner before parsing or transforming the payload.

## 6. Preventing SQL injection

SQL injection occurs when input is concatenated directly into a SQL statement and interpreted by the database as syntax. Unsafe example:

~~~java
String sql = "SELECT * FROM orders WHERE customer_id = '"
        + customerId + "'";
Statement statement = connection.createStatement();
ResultSet result = statement.executeQuery(sql);
~~~

If customerId contains quotes and SQL syntax, the query can be altered. Do not try to strip a few characters such as quotes or semicolons; that approach does not cover all syntaxes and encodings.

Use parameterized queries:

~~~java
String sql =
        "SELECT id, status, total_amount "
        + "FROM orders "
        + "WHERE customer_id = ? AND tenant_id = ?";

try (PreparedStatement statement =
             connection.prepareStatement(sql)) {

    statement.setString(1, customerId);
    statement.setString(2, verifiedTenantId);

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            // Map allowed columns to a DTO.
        }
    }
}
~~~

PreparedStatement separates SQL structure from data values. Values are not interpreted as SQL syntax. At the same time, queries must include tenant predicates and proper authorization; parameterization prevents injection but does not by itself prevent unauthorized access to another tenant's data.

### Table names, column names, and ORDER BY

Parameter placeholders generally cannot be used for table names, column names, or SQL keywords. Never concatenate sort fields from a query string directly into SQL.

Instead, map input to a fixed list of identifiers:

~~~java
Map<String, String> allowedSortColumns = Map.of(
        "createdAt", "created_at",
        "total", "total_amount",
        "status", "status"
);

String sortColumn = allowedSortColumns.get(requestedSort);

if (sortColumn == null) {
    throw new ValidationException("Unsupported sort field");
}

String direction = switch (requestedDirection) {
    case "asc" -> "ASC";
    case "desc" -> "DESC";
    default -> throw new ValidationException(
            "Unsupported sort direction");
};

String sql = "SELECT id, status FROM orders ORDER BY "
        + sortColumn + " " + direction + " LIMIT ?";
~~~

Only concatenate tokens taken from a server-defined allowlist; filter values must still use bind parameters. ORMs such as JPA are not automatically safe if you use native queries or concatenate JPQL/SQL from input strings. Use Criteria API, typed query builders with parameter binding, or parameterized repository methods.

## 7. Preventing NoSQL and query-language injection

NoSQL does not mean immune to injection. Some databases accept document queries, filter expressions, aggregation pipelines, or operators such as $ne, $gt, and $where. If an application accepts an arbitrary JSON object and passes it straight into a query, a user can inject operators or alter query structure.

Never use raw request maps as database filters. Convert DTOs into server-constructed structured queries:

~~~java
public List<Order> findOrders(
        String verifiedTenantId,
        OrderSearchRequest request) {

    Criteria criteria = new Criteria()
            .and("tenantId").is(verifiedTenantId);

    if (request.status() != null) {
        criteria.and("status").is(request.status());
    }

    if (request.createdAfter() != null) {
        criteria.and("createdAt").gte(request.createdAfter());
    }

    Query query = new Query(criteria)
            .limit(validatePageSize(request.pageSize()));

    return mongoTemplate.find(query, Order.class);
}
~~~

This example uses Spring Data MongoDB; request types and repositories should be adapted to your project. Construct only the operators the server allows. Do not let clients supply raw aggregation pipelines, MongoDB operators, DynamoDB expressions, or arbitrary index names unless there is a strictly controlled use case.

For DynamoDB, use ExpressionAttributeValues and proper expression name/value binding APIs. Never concatenate input into condition or projection expressions. For Elasticsearch or other search engines, use typed query builders and cap fields, operators, depth, result counts, and query timeouts.

## 8. Preventing OS command injection

OS command injection occurs when input is concatenated into a shell command. A string that looks like a filename or argument may contain metacharacters causing the shell to execute additional commands.

Avoid:

~~~java
Runtime.getRuntime().exec(
        "convert " + inputFile + " " + outputFile
);
~~~

A safer approach is to avoid a shell and invoke a fixed executable using ProcessBuilder with separate arguments:

~~~java
ProcessBuilder processBuilder = new ProcessBuilder(
        "/usr/bin/convert",
        validatedInputPath.toString(),
        validatedOutputPath.toString()
);

processBuilder.redirectOutput(ProcessBuilder.Redirect.DISCARD);
processBuilder.redirectError(ProcessBuilder.Redirect.DISCARD);
Process process = processBuilder.start();

if (!process.waitFor(5, TimeUnit.SECONDS)) {
    process.destroyForcibly();
    throw new ProcessingTimeoutException();
}

if (process.exitValue() != 0) {
    throw new ProcessingException("Image conversion failed");
}
~~~

ProcessBuilder does not invoke a shell when passed an executable and arguments this way, so shell metacharacters are not interpreted as shell syntax. However, arguments can still be interpreted by the target program as options or special inputs. Validate paths, use a fixed executable, place options before inputs, use the -- delimiter when the tool supports it, and restrict filesystem permissions.

If a Java library directly provides the required functionality, prefer the library over spawning an external process. In serverless environments, child processes also consume CPU, memory, file descriptors, and invocation time; enforce timeouts, output limits, and cleanup on errors.

## 9. Path traversal, file access, and ZIP Slip

Path traversal occurs when input controls a path and causes the application to access files outside the permitted directory. For example, a filename containing ../ can escape the root directory if the application simply concatenates strings.

Use the Path API and check the normalized path:

~~~java
Path root = Paths.get("/tmp/uploads").toAbsolutePath().normalize();
Path candidate = root.resolve(userSuppliedName).normalize();

if (!candidate.startsWith(root)) {
    throw new ValidationException("Invalid file path");
}
~~~

This is a baseline check for paths without malicious symbolic links. For existing files or environments where symbolic links can be created, resolve the real path and verify it remains under the real root. For new files, verify the resolved parent directory, restrict write permissions, and avoid races between checking and opening the file.

When extracting ZIP archives, never write entries directly by concatenating the entry name onto the destination directory. This is the ZIP Slip vulnerability:

~~~java
Path destination = Paths.get("/tmp/extracted")
        .toAbsolutePath().normalize();

Path output = destination.resolve(zipEntry.getName())
        .normalize();

if (!output.startsWith(destination)) {
    throw new SecurityException("ZIP entry escapes destination");
}
~~~

After the check, create parent directories safely and handle symbolic links, duplicate entries, absolute paths, unusual filenames, and decompressed size limits. Limit total entry count, uncompressed size, and compression ratio to defend against archive bombs. Never trust file extensions or filenames as proof of safe content.

## 10. Preventing Server-Side Request Forgery (SSRF)

SSRF occurs when a function takes a caller-controlled URL and sends a request to an address reachable from the server. Attackers may attempt to reach cloud metadata endpoints, loopback addresses, private networks, admin services, or internal hosts.

The safest design is not to accept arbitrary URLs. If business logic must call a partner, accept a partner ID or resource ID and map it to a fixed endpoint in server configuration.

If accepting URLs is unavoidable:

- Allow only required schemes, typically HTTPS.
- Use an allowlist of hostnames or registered domains; do not rely on superficial suffix checks.
- Resolve DNS and inspect all returned IP addresses; block loopback, private, link-local, multicast, reserved, and metadata addresses.
- Prevent DNS rebinding by pinning connections to the verified IP or using a policy-enforcing egress proxy.
- Disable automatic redirects or re-verify every redirect target.
- Disallow userinfo or arbitrary ports unless required by the business case.
- Set connect/read/overall timeouts, limit response body size, and cap redirect counts.
- Restrict egress at the network layer so the function can reach only required destinations.

Validating URLs with regex alone is insufficient. A hostname can resolve to an internal IP after validation, redirects can switch to another host, and various IPv6/encoding forms can trick string filters. Combine application-level validation with network egress controls.

## 11. Template injection, XSS, and output encoding

Template injection occurs when untrusted input is interpreted as template source or expressions. Never concatenate input into template source and pass it to a template engine for execution. Use fixed templates and pass input as model data. If the product lets users author templates, sandbox them with restricted privileges, CPU/time limits, and no access to unnecessary classes, files, or networks.

Cross-site scripting (XSS) typically occurs where responses are rendered in a browser. A JSON API does not automatically cause XSS, but data returned by the API may be inserted unsafely into HTML by a frontend. Apply context-appropriate output encoding:

- HTML text requires HTML escaping.
- HTML attributes require attribute escaping and attribute allowlists.
- JavaScript strings require JavaScript-safe encoding; better yet, avoid embedding data directly into inline scripts.
- URLs require parsing, scheme validation, and proper component encoding.
- SQL requires parameter binding, not HTML escaping.
- Shell commands require avoiding shells and passing safe arguments.

Never use one generic escape function across every context. Encoding must be applied at the sink where data enters, based on the final interpretation context. Double-encoding or encoding for the wrong context can still leave vulnerabilities or corrupt content.

### LDAP, XPath, GraphQL, and expression languages

Other query languages are also vulnerable to injection if the application concatenates input into filters or expressions. For LDAP, use library APIs that build filters with proper escaping/parameter binding; never concatenate usernames directly into filter strings. For XPath, use variable resolvers rather than concatenating values into expressions. For GraphQL, use fixed queries with variables and limit depth, complexity, fields, and resolver cost. For SpEL, EL, or other expression engines, never evaluate caller-supplied expressions; use only application-defined expressions and pass data through controlled variables.

The general rule is to separate query syntax from input values and allow only the set of operations the application genuinely needs. If users need to build advanced filters, provide a schema-constrained DSL and translate it into safe queries; never pass raw filters as source expressions.

## 12. XML, YAML, and untrusted deserialization

XML parsers can be exploited via external entities (XXE) if permitted to read local files or call external URLs. If a function must parse XML, disable external general entities, parameter entities, and external DTDs; enable secure processing and bound size, depth, and node counts.

Example of configuring DocumentBuilderFactory securely:

~~~java
DocumentBuilderFactory factory =
        DocumentBuilderFactory.newInstance();

factory.setFeature(
        "http://apache.org/xml/features/disallow-doctype-decl",
        true
);
factory.setFeature(
        "http://xml.org/sax/features/external-general-entities",
        false
);
factory.setFeature(
        "http://xml.org/sax/features/external-parameter-entities",
        false
);
factory.setXIncludeAware(false);
factory.setExpandEntityReferences(false);
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
~~~

Supported features depend on the parser; if a security configuration is rejected, do not silently ignore it and continue parsing untrusted XML. Use parsers with secure defaults and verify behavior with tests.

For JSON deserialization, avoid enabling broad polymorphic default typing where input can specify which class to instantiate. Use concrete DTOs, subtype allowlists, nesting limits, and size limits. Avoid Java native serialization for data from networks or untrusted queues. For YAML, choose a safe constructor and disallow tags that instantiate arbitrary objects.

## 13. Headers, logs, and regular expressions

Inputs do not only attack databases or shells. Strings reflected into HTTP headers, logs, or regular expressions can also introduce vulnerabilities.

### HTTP response header injection

Never place caller data directly into headers. CR/LF characters can inject new headers or corrupt response structure if the framework does not block them. Use framework header APIs, check lengths, and strip control characters per the contract. Never let users arbitrarily set Location, Set-Cookie, or security headers.

### Log injection

If strings containing newlines or control characters are written to plain-text logs, an attacker can forge log entries or break log parsing. Use structured logging, encode/sanitize untrusted values, and bound lengths. Never log passwords, access tokens, session cookies, secrets, or entire request bodies.

### Regular expression denial of service

Regexes with complex backtracking can consume heavy CPU on crafted inputs. Bound input length before matching, use simple patterns, and avoid nested quantifiers. Java's java.util.regex does not provide a direct timeout for a single match; if strict time control is needed, use an engine with appropriate complexity guarantees or isolate execution. For identifiers and common formats, prefer dedicated parsers.

## 14. File uploads and malicious content

Functions accepting file uploads must validate both metadata and content. Client-supplied Content-Type headers can be spoofed; file extensions do not prove a file actually matches that format.

A secure pipeline can include:

1. Limit request size at API Gateway and object size after upload.
2. Write uploaded files to a quarantine bucket/prefix with restricted permissions.
3. Check extensions against an allowlist and MIME-sniff actual content.
4. Inspect magic bytes, parsers, and file structure.
5. Limit page counts, entry counts, uncompressed size, and archive depth.
6. Scan for malware using an appropriate service when required by the data type.
7. Rename objects using a server-generated ID instead of client-supplied path names.
8. Move validated files to the processing or canonical storage zone.
9. Record inspection status and clean up failed files via TTL.

For images, PDFs, Office documents, or archives, the parser itself is an attack surface. Use up-to-date libraries, bound resources, and run with least privilege. Prevent parsers from accessing networks or filesystems outside temporary areas when unnecessary.

If using presigned URLs for direct uploads to object storage, the backend must still verify the object after upload. A validly signed upload does not mean the content is safe or belongs to the right tenant.

## 15. Validating webhooks and event payloads

Webhooks must have their signatures verified before trusting their contents. Typically, partners sign the raw request body along with a timestamp or metadata per their contract. Make sure to:

- Read the raw body without altering bytes prior to verification.
- Verify the signature using the exact algorithm and headers specified in partner documentation.
- Compare MACs using constant-time comparison when implementing verification directly.
- Validate timestamps and anti-replay windows.
- Deduplicate using event IDs.
- Parse the payload into a DTO and validate its schema only after verification.
- Persist acceptance durably before returning a success response.
- Offload long processing to a queue after verifying and recording the event.

For internal queues or event buses, validate event type, schema version, producer, tenant, event ID, and timestamp. Metadata such as producer name or tenant ID inside the payload only aids routing and auditing; it does not prove identity on its own. Publish permissions must be enforced at the broker/IAM layer, while the consumer enforces its own authorization and business rules.

Events can be stale, out of order, or replayed. Use aggregate version/sequence numbers and conditional updates to prevent stale events from overwriting newer state.

## 16. Authorization checks and preventing mass assignment

Mass assignment occurs when an application binds all caller-supplied fields directly onto a domain entity or database record. Attackers can add fields hidden from the UI, such as ownerId, tenantId, role, status, approved, or price.

Never use entities directly as request DTOs. Create DTOs containing only fields the caller is permitted to supply, then map explicitly:

~~~java
public CreateOrderCommand toCommand(
        CreateOrderRequest request,
        VerifiedIdentity identity) {

    return new CreateOrderCommand(
            identity.tenantId(),
            identity.subject(),
            request.customerReference(),
            request.items()
    );
}
~~~

Extract tenant and subject from verified identity, never from the body. Pricing, payment status, ownership, and approvals are typically determined by the server or domain workflow. After mapping, the domain service verifies resource authorization and business invariants before writing.

For multi-tenant applications, every query and update must enforce tenant scope server-side. Do not check only whether a user may call an endpoint; verify whether the user is authorized for that specific resource ID. Conditional updates can require tenantId, ownerId, and expected version to match simultaneously to prevent TOCTOU/race conditions.

## 17. Error handling without information disclosure

When validation fails, return clear errors without leaking implementation details. A response can include a stable error code, invalid field, and correlation ID.

Example:

~~~json
{
  "type": "https://api.example.com/problems/invalid-input",
  "title": "Invalid request",
  "status": 422,
  "code": "INVALID_PAGE_SIZE",
  "detail": "pageSize must be between 1 and 100",
  "traceId": "req-91ac"
}
~~~

Never return stack traces, SQL queries, filesystem paths, class names, secrets, tokens, or internal network details. For authorization errors, consider returning 404 instead of 403 if disclosing resource existence poses a risk; keep behavior consistent.

Internal logs may record exceptions and necessary context, but must redact sensitive data. Do not write raw attacker input verbatim into logs without bounding and sanitizing it. Record error type, field, trigger source, and trace ID instead of storing entire payloads.

## 18. Resource limits and protecting functions from overload inputs

An input may contain no injection syntax yet still exhaust CPU, memory, connections, or invocation duration. This falls under resource exhaustion and denial of service risks.

Set limits on:

- Request bodies and file uploads.
- Array element counts, field counts, and JSON depth.
- Page size, filter count, sort fields, and query complexity.
- Regex input length and parsing duration.
- Archive entry count, uncompressed size, and compression ratio.
- HTTP response bodies from dependencies.
- URL redirect counts and total outbound request duration.
- Batch sizes, concurrent tasks, and queue depth.
- Database query timeouts and maximum result rows.

Use rate limits and quotas at the gateway; cap function concurrency to protect databases and partner services. For heavy or long-running tasks, move work to queues or workflows with backpressure. Avoid immediate retries when a dependency is overloaded, as that can trigger retry storms.

## 19. Safe input-handling workflow in a Java function

A typical HTTP pipeline:

~~~mermaid
flowchart TD
    A["HTTP / message / event"] --> B["Bound size and rate"]
    B --> C["Authenticate source and identity"]
    C --> D["Parse against fixed schema"]
    D --> E["Canonicalize per contract"]
    E --> F["Validate types, bounds, and semantics"]
    F --> G["Authorize tenant and resource"]
    G --> H["Build typed internal command"]
    H --> I["Use parameter binding / safe APIs"]
    I --> J["Commit state and controlled side effects"]
    J --> K["Response / acknowledgment"]
~~~

An HTTP handler can be structured as follows:

~~~java
public final class CreateOrderHandler
        implements RequestHandler<ApiRequest, ApiResponse> {

    private final Validator validator;
    private final AuthorizationService authorization;
    private final OrderService orderService;

    @Override
    public ApiResponse handleRequest(
            ApiRequest request,
            Context context) {

        VerifiedIdentity identity =
                identityProvider.fromVerifiedContext(request);

        CreateOrderRequest dto =
                jsonMapper.readValue(
                        enforceBodyLimit(request.body()),
                        CreateOrderRequest.class
                );

        validate(dto, validator);

        authorization.requireCanCreateOrder(identity);

        CreateOrderCommand command =
                toCommand(dto, identity);

        OrderResult result = orderService.create(command);

        return ApiResponse.created(result);
    }
}
~~~

This example uses abstractions such as ApiRequest, VerifiedIdentity, identityProvider, jsonMapper, and OrderService; replace them with your API Gateway/runtime adapters. Never read identity from arbitrary bodies or headers. Body limits must be enforced before parsing; even if the gateway enforces a limit, the function should still defend itself when other invocation paths exist.

For message triggers, replace the identity-extraction step with checking producer/source context and event-handling authorization; the payload must still undergo schema, tenant, version, and state validation. Acknowledge only after business results are durably persisted per the broker contract.

## 20. Testing input validation and injection controls

Unit tests covering only a standalone validator are not enough. Test at the exact sink where data is used: database queries, process invocations, file access, URL fetches, template rendering, and logging.

Test matrix:

| Category | Test case | Expected result |
|---|---|---|
| Schema | Missing field, wrong type, unknown field | Rejected per contract; domain service not invoked |
| Bounds | Oversized body, oversized array, negative or huge numbers | Rejected early, resources not exhausted |
| SQL | Values containing quotes and SQL syntax | Query preserves structure; values are bound |
| NoSQL | JSON containing operators or unknown filters | Not converted into query operators |
| Command | Input with shell metacharacters or option prefixes | No shell spawned; executable/arguments controlled |
| Path | ../, absolute paths, encoded traversal, symlinks | No access outside root |
| ZIP | Entry escaping directory or archive bomb | Rejected without writing files outside zone |
| SSRF | Loopback, private IPs, metadata IP, redirects to blocked hosts | Outbound request blocked |
| XML | DOCTYPE and external entities | Parser rejects or does not resolve external entities |
| XSS/template | HTML/script/template expressions in data | Data is not executed during rendering |
| Header/log | CRLF, newlines, and very long strings | No forged headers/logs or oversized log lines |
| Authorization | Valid ID belonging to another tenant | Rejected without disclosing data |
| Webhook/event | Invalid signature, stale event, duplicate, old schema | Rejected or deduplicated per policy |

Use test fixtures containing known malicious payloads, but never execute them in production environments. Integration tests must verify actual query parameterization, filesystem boundaries, egress policies, and parser configurations. Fuzz testing can uncover edge-case inputs; property-based testing helps verify invariants such as every normalized path remaining under root.

## 21. Observing and responding to malicious input

Track validation failure counts, auth failures, rate limits, parser errors, blocked outbound requests, and query timeouts. Break metrics down by trigger, route, error code, and controlled tenant reference.

Useful metrics:

- Rejected requests by reason and route.
- Schema validation failures by version.
- SQL/database errors and query latency.
- SSRF/egress policy denials.
- Quarantined or failed file upload scans.
- Webhook signature failures and duplicate event counts.
- Rate limits, throttling, and invocation concurrency.
- Parser timeouts, body sizes, and archive expansion ratios.

Never use raw user input as a metric label, as cardinality can grow unbounded and leak data. Do not log full malicious payloads; store a hash, event ID, request ID, or a redacted sample if policy permits. Alert on sudden spikes in error rates, while avoiding turning ordinary validation errors into high-severity incidents.

When abuse is detected, reduce quotas, block principals or routes, disable affected triggers, quarantine messages/files, and investigate related traces. If input already caused side effects, use audit trails and idempotency records to determine state; never blindly replay messages.

## 22. Production input-protection checklist

Before deploying a function, verify:

1. Are all input sources listed: HTTP, messages, events, webhooks, files, and dependencies?
2. Are limits enforced on body size, files, collections, nesting, queries, and parse time?
3. Do DTOs include only fields callers are permitted to send?
4. Are schema and semantic validation applied at the function/domain layer?
5. Are canonicalization and decoding performed consistently without repeated decoding?
6. Are identity and tenant extracted from verified context?
7. Is authorization checked per resource, not just per endpoint?
8. Does SQL use PreparedStatement or parameterized queries?
9. Are table/column/sort/filter names mapped via allowlists?
10. Are NoSQL and search queries built with typed query builders rather than raw client objects?
11. Is input kept out of shell commands; if processes are required, are fixed executables and separate arguments used?
12. Are paths normalized/resolved and kept inside the allowed root?
13. Is SSRF controlled via host allowlists and egress policies?
14. Are XML/JSON/YAML deserializers securely configured?
15. Are templates and outputs handled with context-appropriate encoding?
16. Are file uploads size-limited, content-inspected, and quarantined?
17. Do webhooks have signature verification and replay protection?
18. Do logs and error responses avoid leaking secrets or allowing log injection?
19. Are concurrency, timeouts, retries, and result sizes bounded?
20. Are sink-level tests in place alongside metrics/alerts for anomalous behavior?

## Conclusion

Input validation ensures data conforms to expected structure, bounds, and business rules; injection prevention ensures data is never interpreted as unintended commands or expressions. A serverless function must apply both across every trigger, including internal messages and cloud service events.

In Java, parse into typed DTOs, enforce explicit allowlists and bounds, extract identity from verified context, check resource-level authorization, and use safe APIs at every sink: PreparedStatement for SQL, typed query builders for NoSQL, shell-free ProcessBuilder for processes, the Path API for files, and egress policies for URLs. Combine sink-level tests, timeouts, quotas, structured logging, and safe cleanup to protect functions when receiving malformed or deliberately crafted attack data.

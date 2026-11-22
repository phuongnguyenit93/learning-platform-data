# Avoiding Sensitive Data and Internal Paths in Public Messages in Java I/O

## 1. Goal and Scenarios

Java applications frequently read and write files via `Files`, `FileChannel`, `InputStream`, and `OutputStream`, handling uploads/downloads, temporary files, ZIP/JAR archives, and user resources. When an operation fails, exceptions can contain **absolute server paths**, OS usernames, document names, storage keys, infrastructure endpoints, or even part of the input data. If raw `exception.getMessage()` or a stack trace is used as the content of an HTTP response, UI, email, webhook, or customer-facing message, unnecessary sensitive details can leak.

Example response that **should not be exposed publicly**:

```text
Could not read /srv/apps/prod/private/customers/42/tax-record.pdf
java.nio.file.AccessDeniedException:
    /srv/apps/prod/private/customers/42/tax-record.pdf
```

Safer response:

```text
status=404
code=RESOURCE_UNAVAILABLE
message=Unable to access the requested resource.
requestId=REQ-DEMO-001
```

This lesson helps you:

1. Identify sensitive information in paths, exceptions, requests, and logs.
2. Build public errors from an **allowlist** of status, error code, stable message, and correlation ID.
3. Handle `NoSuchFileException`, `AccessDeniedException`, and `IOException` without exposing filesystem details.
4. Separate public responses from internal diagnostics/logs, which must also be protected.
5. Avoid reflecting uploaded filenames, private URLs, tokens, personal data, or raw payloads.
6. Inspect indirect leak paths through framework error pages, serializers, and log/trace exporters.
7. Write Java 17+ programs and tests with deterministic stdout.

Important principle: **the goal is not to hide every error**, but to give users useful information within what they are permitted to know, while operators can still investigate incidents through a controlled channel.

## 2. What Counts as a Public Message?

Anything readable by people without internal operator privileges must be treated as a public or semi-public surface:

- HTTP API response bodies/headers, GraphQL errors, WebSocket messages.
- Error messages on web, mobile, or CLIs distributed to customers.
- Emails, SMS, notifications, and webhooks sent to third parties.
- Exported error files and customer support pages.
- Browser consoles, client analytics SDKs, and trace/event exporters with broad access.
- Log or stack-trace excerpts pasted into shared issues/tickets.
- Default error pages from reverse proxies or web frameworks.

**Internal logs are not automatically safe.** Logs may be aggregated into SaaS platforms, backed up for years, exported to partners, or exposed on public dashboards via misconfiguration. Therefore, control access permissions, retention periods, encryption where appropriate, and minimize data at log creation time.

## 3. Data Easily Leaked Through I/O

| Category | Example | Risk |
| --- | --- | --- |
| Internal path | `/srv/prod/private/payroll/2026.csv` | Exposes server layout, business data |
| Windows path | `C:\Users\svc\AppData\Local\...` | Exposes system account, environment |
| UNC/network path | `\\fileserver\finance\salary.csv` | Exposes private host/share names |
| Storage URI | Private bucket/key, object-store URL with token | Exposes infrastructure or access credentials |
| Secret | `Authorization`, API key, refresh token, password | Can be reused for unauthorized access |
| PII | Email, phone, ID, full name embedded in filename | Exposes personal data |
| File content | CSV/JSON/XML line causing a parse error | May contain sensitive payload data |
| Stack trace | Package, class, source line, cause | Reveals implementation details and fault location |
| Query string/filename | Uploaded filename, client parameters | May contain secrets and adversary-controlled data |
| Provider diagnostics | Disk/mount name, endpoint, reason | Reveals operational configuration |

A filename being just a **basename** does not make it harmless: `hospital-result_Alice.pdf` can still contain personal data. Do not display `Path.getFileName()` unless a display-name attribute has been approved for that exact subject and context.

## 4. Java I/O Exceptions Are Not Safe to Echo

Examples of types to understand:

- `NoSuchFileException` when a `Path` is not found.
- `AccessDeniedException` when permissions are insufficient.
- `FileAlreadyExistsException` if the destination entry already exists.
- `FileSystemException` with `getFile()`, `getOtherFile()`, and `getReason()`.
- `FileNotFoundException` whose message typically includes the file/system path.
- `InvalidPathException` which may contain the offending input string; this is an unchecked exception.
- General `IOException` from files, sockets, ZIPs, filesystem providers, or cloud storage adapters.
- Parser errors when reading files, which may embed snippets of malformed content.

There is no contract claiming `Throwable.getMessage()` strips secrets or paths. The exact same operation can produce different messages across OSes, providers, and JDKs.

Anti-pattern (non-standalone illustrative snippet):

```java
try {
    return Files.readString(path);
} catch (IOException ex) {
    // WRONG if this string is sent to an unauthorized user:
    return "Cannot read file " + path + ": " + ex.getMessage();
}
```

Indirect forms can leak as well:

```java
exception.toString()
exception.getLocalizedMessage()
Arrays.toString(exception.getStackTrace())
path.toAbsolutePath().toString()
exception.printStackTrace(new PrintWriter(responseWriter))
```

These are illustrative expressions to **avoid at information egress boundaries**, not standalone code. Stack traces can contain nested causes and suppressed exceptions; far more data can leak than just the top message.

## 5. Separating Public Responses From Diagnostic Information

Design pattern:

```text
Files / Channel / FileStore / Parser
                |
             Exception
                |
       +--------+---------+
       |                  |
       v                  v
 Public Error Mapper   Internal Diagnostics
       |                  |
       v                  v
 PublicError DTO       Structured event
 status, code, msg      code, requestId,
 requestId              category, duration
       |                  |
       v                  v
 HTTP/UI/webhook         Access-controlled log
 No Throwable            Do not log raw secrets
```

Public DTOs should contain **only allowlisted fields**. Never include fields like `Throwable cause`, `Path internalPath`, raw requests, or `StackTraceElement[]` for a serializer to output automatically.

A typical contract looks like:

```text
status:     500
code:       STORAGE_ERROR
message:    Unable to complete the operation. Please try again.
requestId:  e.g. a per-request UUID
```

Public messages guide the user without confirming details outside their authorization. Error codes serve UIs and support; `requestId` enables correlating with access-controlled logs. **A request ID is not an access token**, and knowing an ID must not grant access to view the corresponding logs.

## 6. Choosing Status and Error Codes Deliberately

| Condition | Example HTTP status | Public code | Display message |
| --- | --- | --- | --- |
| Resource absent/inaccessible per policy | 404 | `RESOURCE_UNAVAILABLE` | Unable to access the resource. |
| Forbidden and policy permits disclosing denial | 403 | `ACCESS_DENIED` | You do not have permission to perform this action. |
| Request fails schema/input validation | 400 | `INVALID_REQUEST` | Invalid request data. |
| Upload exceeds limit | 413 | `UPLOAD_TOO_LARGE` | File exceeds the allowed limit. |
| Unsupported file format | 415/400 | `UNSUPPORTED_FILE_TYPE` | Unsupported file format. |
| Unexpected internal I/O error | 500 | `STORAGE_ERROR` | Unable to complete the operation. |
| Storage service temporarily down | 503 if appropriate | `STORAGE_UNAVAILABLE` | Service is temporarily unavailable. |

This is an **illustrative table**, not a universal status rule for every API.

In private-resource systems, both "does not exist" and "no permission to view" sometimes must return **404 with the exact same schema and message** to avoid creating an existence-probing oracle. Conversely, an API for authenticated users may intentionally return 403. The choice must follow authorization policy and be applied consistently, not merely for wording polish.

Watch for **non-text side channels**: large differences in status, body size, or latency can still reveal whether a resource exists. Never promise complete concealment solely from changing the message text.

## 7. Runnable Example: Mapping Exceptions to `PublicError` (Java 17+)

Save as **`SafePublicErrorDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.NoSuchFileException;

public class SafePublicErrorDemo {
    record PublicError(
            int status, String code, String message, String requestId) {
    }

    static PublicError map(Throwable error, String requestId) {
        if (error instanceof NoSuchFileException
                || error instanceof AccessDeniedException) {
            // Demo: private resource, do not confirm existence.
            return new PublicError(
                    404,
                    "RESOURCE_UNAVAILABLE",
                    "Unable to access the requested resource.",
                    requestId);
        }

        if (error instanceof IllegalArgumentException) {
            return new PublicError(
                    400,
                    "INVALID_REQUEST",
                    "Invalid request data.",
                    requestId);
        }

        return new PublicError(
                500,
                "STORAGE_ERROR",
                "Unable to complete the operation.",
                requestId);
    }

    private static void printSafe(Throwable error, String requestId) {
        PublicError result = map(error, requestId);
        System.out.println(result.status() + " | "
                + result.code() + " | "
                + result.message() + " | "
                + result.requestId());
    }

    public static void main(String[] args) {
        String id = "REQ-DEMO-001"; // fixed ONLY for the example

        printSafe(new NoSuchFileException(
                "/srv/private/clients/42/contract.pdf"), id);

        printSafe(new AccessDeniedException(
                "/mnt/secure/reports/finance.csv"), id);

        printSafe(new IOException(
                "storage failed; token=DEMO_SECRET_DO_NOT_DISCLOSE"), id);

        printSafe(new IllegalArgumentException(
                "raw input=/internal/tmp/name.txt"), id);
    }
}
```

Run with JDK 17+ and a UTF-8-capable terminal:

```bash
javac -encoding UTF-8 SafePublicErrorDemo.java
java SafePublicErrorDemo
```

Stdout on success:

```text
404 | RESOURCE_UNAVAILABLE | Unable to access the requested resource. | REQ-DEMO-001
404 | RESOURCE_UNAVAILABLE | Unable to access the requested resource. | REQ-DEMO-001
500 | STORAGE_ERROR | Unable to complete the operation. | REQ-DEMO-001
400 | INVALID_REQUEST | Invalid request data. | REQ-DEMO-001
```

**Explanation:**

1. Exceptions containing paths/tokens remain **purely internal** inside the object. The mapper never calls `getMessage()` or `toString()`.
2. Both private-file errors `NoSuchFileException` and `AccessDeniedException` map identically, reducing the risk of leaking existence state.
3. Unexpected `IOException` receives code `STORAGE_ERROR` without broadcasting raw causes.
4. `record PublicError` has fixed fields and holds no `Throwable`.
5. `IllegalArgumentException` is used here solely to illustrate bad input. In real applications, do not map **every** `IllegalArgumentException` to a client error; internal programming bugs can throw it too. Classify at the business layer with dedicated exceptions.
6. The fixed ID in the demo yields deterministic stdout; in real systems, generate a server-side ID per request.

This example is pure Java **error mapping**, not an HTTP server. It does not replace authorization checks before reading files.

## 8. Runnable Example: Real I/O Handling and Separating stdout/stderr

Save **`SafeFileReadDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class SafeFileReadDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("safe-file-");
        String requestId = "REQ-DEMO-002";

        try {
            Path internalPath = directory.resolve("private-record.txt");

            try {
                Files.readString(internalPath);
                System.out.println("status=200");
            } catch (NoSuchFileException ex) {
                // Diagnostic: allowlisted fields only,
                // do not print ex, ex.getMessage(), or ex.getFile().
                System.err.println(
                        "event=FILE_READ_FAILED"
                        + " type=NoSuchFileException"
                        + " requestId=" + requestId);

                // Simulated public response.
                System.out.println("status=404");
                System.out.println("code=RESOURCE_UNAVAILABLE");
                System.out.println(
                        "message=Unable to access the requested resource.");
                System.out.println("requestId=" + requestId);
            }
        } finally {
            Files.deleteIfExists(directory);
        }
    }
}
```

```bash
javac -encoding UTF-8 SafeFileReadDemo.java
java SafeFileReadDemo
```

**Stdout** when reading a non-existent file:

```text
status=404
code=RESOURCE_UNAVAILABLE
message=Unable to access the requested resource.
requestId=REQ-DEMO-002
```

**Stderr** on the same failure:

```text
event=FILE_READ_FAILED type=NoSuchFileException requestId=REQ-DEMO-002
```

The two outputs reside on two separate streams; an IDE/terminal may interleave them in different orders when displayed together. If `stderr` is forwarded externally, it is **also a public channel**; use a logging system with protective policies rather than relying merely on stdout/stderr stream names.

Here, the program creates a fresh directory and deliberately reads an uncreated file, so `NoSuchFileException` is the expected normal-environment result. Absolute paths and filenames do not appear because the code never prints `internalPath` or the exception object. If I/O hits another uncaught error, `main` could still print a stack trace: **a real server must have an error boundary** converting unknown errors into safe public responses instead of letting the runtime emit stack traces to HTTP.

## 9. Diagnostic Logs Also Need an Allowlist Design

Internal logs aid technical support, but that does not permit logging arbitrary data.

**Pattern that easily leaks:**

```java
logger.log(Level.SEVERE,
        "Read failed: " + path + " / " + exception.getMessage(),
        exception);
```

This snippet is an **anti-pattern in broadly accessible logging systems**. It can send the path, message, cause, and stack trace to every sink configured on the logger. That does not mean logging stack traces is forbidden in every environment; logs must be tiered and governed by data classification policies.

**More controlled log-field approach:**

```java
logger.log(Level.WARNING,
        "event={0} requestId={1} errorCategory={2}",
        new Object[] {
                "FILE_READ_FAILED",
                requestId,
                "NOT_FOUND_OR_DENIED"
        });
```

This snippet assumes variables and `logger` are initialized. Fields come from fixed catalogs, not `exception.getMessage()`. If stack traces are required in a separate protected channel, enforce restricted access, retention limits, and secret/PII checks. Calling a logger "internal" does not change the sensitivity of its data if it exports to a broadly accessible dashboard.

| Allowlistable field | Example | Caveat |
| --- | --- | --- |
| `eventCode` | `FILE_READ_FAILED` | Use a fixed catalog |
| `requestId` | Validated UUID | Do not encode customer IDs or paths |
| `operation` | `READ_RESOURCE` | Do not log raw queries or paths |
| `errorCategory` | `NOT_FOUND_OR_DENIED` | Do not expose fine-grained private permissions |
| `serviceCode` | `DOCUMENT_SERVICE` | Use approved names only |
| `durationBucket` | `under_100ms` | Avoid unnecessary granularity |
| `publicErrorCode` | `RESOURCE_UNAVAILABLE` | Match response code |

Never place file paths, emails, tokens, or raw filenames into metric labels. That risks data leaks, explodes label *cardinality*, and degrades monitoring operability.

## 10. `requestId`: Tracing Without Disclosing Secrets

Request IDs let support staff look up the exact incident in logs without asking users to screenshot stack traces.

Principles:

1. Generate the ID on the server, e.g., `UUID.randomUUID().toString()`, or use a trace ID from a controlled mechanism.
2. Never concatenate `userId + path + token` into the ID, and do not output a hash of a low-entropy secret as if it were guaranteed harmless.
3. Never treat a request ID as proof that a user has permission to read all logs.
4. If accepting `X-Request-ID` from clients, validate length, charset, control characters, and trust policy; if untrusted, generate a new ID.
5. Protect log lookup systems with authentication and authorization; knowing a request ID is **insufficient** to view internal diagnostics.
6. Do not use fixed demo IDs in production.

Snippet:

```java
String requestId = java.util.UUID.randomUUID().toString();
```

Because real IDs are random, deterministic stdout cannot be specified for a program generating a fresh ID on each run. The two earlier examples used `REQ-DEMO-...` purely for output comparison convenience.

## 11. Uploaded Filenames Are Untrusted Data

Client-submitted filenames can contain local paths or PII:

```text
C:\Users\Alice\Documents\medical-result.pdf
customer-123456789-bank-statement.pdf
../private/secret.txt
```

Never use this string directly as the server storage path or print it into public error logs. Risks include:

- Path traversal, differing separators between Windows and Unix.
- Filename collisions, deliberate overwrites.
- Very long strings or control characters used for log/header injection.
- Personal information embedded in the filename by the user.
- File content spoofing extensions or MIME types.

A pragmatic policy:

- Server generates a sufficiently unique **storage key** independent of the original name.
- Enforce upload byte limits, actual file-type validation, and resource ownership.
- Store the **display name** separately only when business logic genuinely needs it; display it only to authorized users.
- Never place storage file paths into HTTP responses or internal file-style URLs.
- Handle download `Content-Disposition` headers using a library with proper encoding/validation, never concatenating raw strings containing CR/LF.

Illustrative snippet, not a complete upload handler:

```java
String storageKey = java.util.UUID.randomUUID().toString();
Path destination = controlledUploadRoot.resolve(storageKey);
```

`controlledUploadRoot` must be server-owned with proper filesystem/sandbox permissions. You also need strategies for symlink race prevention, size/quota limits, policy-required scanning, and error/partial-write cleanup.

## 12. Do Not Assume `normalize()` Solves Path Security

In Java NIO, `Path.normalize()` removes syntactic path components like `.` and `..`; `toAbsolutePath()` creates an environment-based absolute form. Neither call **verifies authorization**, prevents all symbolic-link/race cases, or proves a file resides inside an allowed real root.

Example when serving downloads by resource ID:

```text
request resourceId
        |
        v
authenticate user
        |
        v
authorize resourceId (domain policy)
        |
        v
map ID to server-owned storage key/path
        |
        v
open/read with controlled filesystem permissions
        |
        v
return bytes or safe public error DTO
```

Never use a client-supplied raw path as evidence of access rights. If the application handles paths in a directory an adversary could modify, consider directory-handle mechanisms and proper permissions; use `SecureDirectoryStream` only when supported by the provider and paired with matching race-mitigation design.

Hiding paths from errors is part of **reducing information disclosure**, not a substitute for real file access protection.

## 13. Indirect Leak Sources

Even when a service stops returning `ex.getMessage()`, another layer can still leak:

- Default debug error pages enabled with `trace` or `exception`.
- JSON serializers encountering a DTO with a `Throwable` field.
- HTTP filters adding an `X-Error-Detail` header with the failure cause.
- Middleware echoing query strings or upload filenames.
- Tracing SDKs sending raw requests/exceptions to third parties.
- UIs displaying raw error bodies returned by an HTTP client.
- Support emails attaching full server logs.
- Structured log exporters sending raw `path` fields into broadly accessible dashboards.

Maintain a **centralized error boundary** for all unclassified exceptions. Use allowlisted response schemas, inspect HTTP headers, disable debug pages outside development, verify framework error handlers, and restrict logging/tracing payloads. A `500` status does not by itself protect the body contents.

## 14. Redaction Helps, but Is Not the Sole Shield

**Redaction** strips or masks fields such as `Authorization`, tokens, or PII. When raw objects must be handled, schema-based fields can be redacted before logging.

However, regex over arbitrary messages is not a complete security policy:

```java
String sanitized = message.replaceAll(
        "token=[^ ]+", "token=[REDACTED]");
```

This snippet is **insufficiently safe** when tokens span newlines, encodings, other delimiters, or reside inside `cause`; Windows/Unix paths, JSON/XML, and personal data have no single reliable universal pattern.

Priority order:

1. Avoid populating public fields from raw exceptions in the first place.
2. Select status/code/message from a fixed table.
3. Minimize log fields via an allowlist.
4. Redact unavoidable fields in a dedicated layer, accompanied by tests.
5. Control log access, retention, encryption, and export sinks.
6. Re-verify after library/framework upgrades because an error serializer may add new fields.

Even if a helper named `sanitize()` is called everywhere, it must still be audited against its inputs and egress paths; **a function name is not proof against leakage**.

## 15. Log Injection From Client Content

An unvalidated filename or request ID can contain newline characters:

```text
report.pdf
ERROR admin access granted
```

If the system concatenates strings directly into logs, an attacker can forge fake log entries. Countermeasures:

- Do not log unnecessary raw inputs.
- Prefer structured logging with format-appropriate escaping/encoding.
- Limit length and strip or validate control characters per policy.
- Reject arbitrary client-supplied request IDs unless validated by strict rules.
- Separate server-generated fields from user-provided fields.
- Rate-limit events/logs and apply backpressure to prevent log flooding.

A fixed/validated `requestId` and an enum-backed `eventCode` are far easier to protect than concatenating arbitrary request details.

## 16. Testing Public Errors With Canary Sensitive Data

A good test proactively constructs exceptions containing fake paths/tokens, then asserts those strings **do not appear in public output**. Never test only the happy path.

Create **`PublicErrorContractTest.java`**:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.NoSuchFileException;
import java.util.List;

public class PublicErrorContractTest {
    record PublicError(int status, String code, String message) {
        @Override
        public String toString() {
            return status + "|" + code + "|" + message;
        }
    }

    static PublicError map(Throwable error) {
        if (error instanceof NoSuchFileException
                || error instanceof AccessDeniedException) {
            return new PublicError(404, "RESOURCE_UNAVAILABLE",
                    "Resource unavailable.");
        }
        return new PublicError(500, "STORAGE_ERROR",
                "Unable to complete the operation.");
    }

    public static void main(String[] args) {
        String privatePath = "/var/private/billing/customer-42.csv";
        String secretToken = "API_TOKEN_TEST_ONLY_123";

        List<Throwable> errors = List.of(
                new NoSuchFileException(privatePath),
                new AccessDeniedException(privatePath),
                new IOException("token=" + secretToken),
                new IllegalStateException(
                        "source path=" + privatePath));

        int passed = 0;
        for (Throwable error : errors) {
            String text = map(error).toString();
            if (text.contains(privatePath)
                    || text.contains(secretToken)
                    || text.contains("/var/private")
                    || text.contains(error.getClass().getName())) {
                throw new AssertionError("Sensitive detail leaked");
            }
            passed++;
        }

        System.out.println("passed=" + passed);
    }
}
```

```bash
javac -encoding UTF-8 PublicErrorContractTest.java
java PublicErrorContractTest
```

Stdout on success:

```text
passed=4
```

This test is a **minimal contract check** and does not prove the entire server is safe. In practice, test actual JSON responses/headers/bodies emitted by the framework, telemetry/log sinks, nested causes, Windows/Unix paths, URIs, tokens, Unicode, control characters, user content inside archives, and unexpected middleware failures.

### Test Checklist by Error Type

| Scenario | Canary input | Verification condition |
| --- | --- | --- |
| File does not exist | Private path | No path in response |
| Access denied | `AccessDeniedException` with path | No filename/internal permissions leaked |
| Unexpected I/O | `IOException` with canary token | Token absent from public responses/logs |
| Invalid input | Filename with `../` | Raw name not reflected |
| Upload too large | Filename containing email | Only code/appropriate limit shown |
| Parser error | CSV line containing fake PII | No file contents displayed |
| Nested cause | Exception chain containing path | Serializer does not expose cause/stack |
| Header injection | ID containing CR/LF | ID rejected or replaced |
| Logging | Token in request body | Not written to broadly accessible sinks |

## 17. Separation of Responsibilities

An auditable architecture includes:

**File adapter / repository:** knows `Path`, `Files`, `FileChannel`, and real I/O causes. Does not decide public messages.

**Business service:** classifies errors by user permissions, resources, and semantics. Decides when to return 403 versus 404 to curb enumeration.

**API boundary:** catches classified and unknown errors, builds `PublicError` with only allowlisted status/code/message/requestId. Never feeds `Throwable` directly to a serializer.

**Diagnostic logging:** records controlled events and IDs; separate audit log if needed, with access control and retention. Detailed information is permitted only under explicit protection policies.

**Security tests and monitoring:** test real error paths, logging/exporter pipelines, and post-deploy framework configuration. Do not test only a single isolated exception mapper.

## 18. Common Design Mistakes

1. Returning `IOException.getMessage()` directly to users.
2. Appending `Path.toAbsolutePath()` to a 404 message.
3. Serializing `Throwable` or `StackTraceElement[]` inside DTOs.
4. Showing 500 debug error pages in production.
5. Logging entire request bodies or `Authorization` headers on parser errors.
6. Letting raw uploaded filenames become server paths or public logs.
7. Assuming `getFileName()` removes all PII.
8. Distinguishing 403/404 inconsistently on confidential resources, enabling enumeration.
9. Using error codes that embed internal paths or storage keys.
10. Deriving request IDs from user identifiers, filenames, or secrets.
11. Letting anyone who knows a request ID view logs without authorization.
12. Applying a single regex redaction and considering everything safe.
13. Failing to handle CR/LF and log injection from inputs.
14. Checking only controllers while ignoring middleware, headers, and serializers.
15. Treating `stderr`, tracing dashboards, or support tickets as never-public channels.
16. Recording emails/PII as metric labels, causing leaks and high cardinality.
17. Relying on `Path.normalize()` instead of authorization/symlink safety.
18. Failing to check unexpected errors and automatic framework stack traces.

## 19. Practice Exercises

**Exercise A — Fix the anti-pattern.** Replace the code below with a public DTO containing no path or message:

```java
catch (IOException ex) {
    return "Failed: " + path + " / " + ex.getMessage();
}
```

**Exercise B — Secret resources.** Design responses for two cases with the same ID: non-existent and unauthorized. When do you choose the same 404? How do you ensure authorization checks still execute?

**Exercise C — Filenames containing PII.** A customer uploads a file whose name contains their full name and medical details. Why should this name not appear in public logs? Create a server-side storage key and a display name governed by its own policy.

**Exercise D — Error serializer.** A framework returns JSON with `message` and `trace` from an exception. Build a DTO containing only `status`, `code`, `message`, and `requestId`; test against the real response.

**Exercise E — Preventing log injection.** A client sends a request ID containing newlines and forged log text. Describe how to restrict length/charset or replace it with a server-generated ID.

**Exercise F — Cross-platform testing.** Add Windows paths, Linux paths, UNC paths, private URLs, tokens, and Unicode filenames as canaries in tests; verify none appear in responses.

## 20. References

- [Java SE 17 — FileSystemException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemException.html): `getFile()`, `getOtherFile()`, `getReason()`.
- [Java SE 17 — NoSuchFileException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/NoSuchFileException.html).
- [Java SE 17 — AccessDeniedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/AccessDeniedException.html).
- [Java SE 17 — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html).
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html).
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

## 21. Remember

Public messages should answer **what the user can do next**, not reflect where the system stores files, whether a private resource exists, or which token or request payload caused an exception. `NoSuchFileException`, `AccessDeniedException`, `FileSystemException`, and `IOException` can contain paths, OS messages, and nested causes; never pass raw exceptions to UI/HTTP/email/webhooks.

The right pattern is **I/O error → classify and check permissions → map allowlisted status/code/message → attach safe `requestId` → write controlled diagnostics → test failure branches**. Logs, telemetry, and support notifications also need protection. Hiding paths in one catch block is just one step; practical safety requires authorization, output control, anti-injection, logging policies, and system-level testing.

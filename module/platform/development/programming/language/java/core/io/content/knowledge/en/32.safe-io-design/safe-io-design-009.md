# Avoiding Sensitive Data and Internal Paths in Public Messages in Java I/O

## 1. Objectives and Scenarios

Java applications routinely read/write files using `Files`, `FileChannel`, `InputStream`, and `OutputStream`, handling uploads/downloads, temporary files, ZIP/JAR archives, and user resources. When an operation fails, the exception may contain **absolute server paths**, OS usernames, document names, storage keys, infrastructure endpoints, or even parts of the input data. If you use raw `exception.getMessage()` or a stack trace in HTTP responses, UI, emails, webhooks, or customer-facing messages, unnecessary information can be leaked.

Example of a response that **should not be made public**:

```text
Could not read /srv/apps/prod/private/customers/42/tax-record.pdf
java.nio.file.AccessDeniedException:
    /srv/apps/prod/private/customers/42/tax-record.pdf
```

Safer response:

```text
status=404
code=RESOURCE_UNAVAILABLE
message=The requested resource cannot be accessed.
requestId=REQ-DEMO-001
```

This lesson helps you:

1. Identify sensitive information in paths, exceptions, requests, and logs.
2. Construct public errors from an **allowlist** of status, error code, stable message, and correlation ID.
3. Handle `NoSuchFileException`, `AccessDeniedException`, and `IOException` without exposing filesystem details.
4. Separate public responses from internal diagnostics/logs, which must also be protected.
5. Avoid reflecting uploaded filenames, private URLs, tokens, personal data, or raw payloads.
6. Audit indirect leak paths through framework error pages, serializers, and log/trace exporters.
7. Write Java 17+ programs and tests with deterministic stdout.

Key principle: **the goal is not hiding every error**, but giving users useful information within what they are permitted to know, while operators can still investigate incidents through a controlled channel.

## 2. What Counts as a Public Message?

Anything readable by someone without internal operational privileges must be treated as a public or semi-public surface:

- HTTP API response bodies/headers, GraphQL errors, WebSocket messages.
- Error messages on web, mobile, and CLI clients distributed to customers.
- Emails, SMS, notifications, and webhooks sent to third parties.
- Exported error files and technical support pages.
- Browser consoles, client analytics SDKs, and trace/event exporters with broad access.
- Log excerpts or stack traces pasted into shared issues/tickets.
- Default error pages of reverse proxies or web frameworks.

**Internal logs are not automatically safe.** Logs may be centralized in a SaaS service, backed up for years, exported to partners, or exposed in a public dashboard due to misconfiguration. Therefore, control access permissions, retention periods, encryption where appropriate, and minimize data right at log-creation time.

## 3. Data Easily Leaked via I/O

| Category | Example | Risk |
| --- | --- | --- |
| Internal path | `/srv/prod/private/payroll/2026.csv` | Reveals server layout and business data |
| Windows path | `C:\Users\svc\AppData\Local\...` | Reveals system account and environment |
| UNC/network path | `\\fileserver\finance\salary.csv` | Reveals private hostname/share |
| Storage URI | Private bucket/key, object-store URL containing token | Exposes infrastructure or access credentials |
| Secret | `Authorization`, API key, refresh token, password | Can be abused for unauthorized access |
| PII | Email, phone, ID, full name embedded in filename | Exposes personal data |
| File content | CSV/JSON/XML line causing a parse error | May contain sensitive data |
| Stack trace | Package, class, source line, cause | Reveals implementation details and fault location |
| Query string/filename | Uploaded filename, client parameter | May contain secrets and adversary-controlled data |
| Provider diagnostics | Disk/mount name, endpoint, reason | Reveals operational configuration |

A filename being just a **basename** does not make it harmless: `hospital-result_Alice.pdf` can still contain personal data. Never display `Path.getFileName()` unless a display-name attribute has been approved for the right subject and right context.

## 4. Java I/O Exceptions Are Not Safe Data to Echo

Examples of types to understand:

- `NoSuchFileException` when a `Path` is not found.
- `AccessDeniedException` when access permissions are insufficient.
- `FileAlreadyExistsException` when the target entry already exists.
- `FileSystemException` with `getFile()`, `getOtherFile()`, and `getReason()`.
- `FileNotFoundException` whose message typically includes the file/system path.
- `InvalidPathException` which may contain the offending input string; this is an unchecked exception.
- General `IOException` from files, sockets, ZIP, filesystem providers, and cloud storage adapters.
- Parser errors when reading files may include snippets of malformed content.

There is no contract guaranteeing that `Throwable.getMessage()` has stripped secrets or paths. The same operation can also produce different messages across OSes/providers/JDKs.

Anti-pattern (non-standalone illustrative snippet):

```java
try {
    return Files.readString(path);
} catch (IOException ex) {
    // WRONG if this string is sent to an unauthorized user:
    return "Không đọc được file " + path + ": " + ex.getMessage();
}
```

Other indirect ways can also leak:

```java
exception.toString()
exception.getLocalizedMessage()
Arrays.toString(exception.getStackTrace())
path.toAbsolutePath().toString()
exception.printStackTrace(new PrintWriter(responseWriter))
```

These are illustrative expressions to **avoid at output boundaries**, not standalone code. Stack traces can contain nested causes and suppressed exceptions; far more data is exposed than just the first message.

## 5. Separating Public Responses from Diagnostic Information

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
 HTTP/UI/webhook       Access-controlled logs
 No Throwable          Do not log raw secrets
```

A public DTO should contain **only allowlisted fields**. Do not add fields like `Throwable cause`, `Path internalPath`, raw request, or `StackTraceElement[]` for a serializer to process automatically.

A typical contract has:

```text
status:     500
code:       STORAGE_ERROR
message:    Unable to complete the operation. Please try again.
requestId:  e.g. a per-request UUID
```

The public message provides guidance without confirming information outside the user's authorization. Error codes serve the UI and support; `requestId` serves correlation with access-controlled logs. **A request ID is not an access token**, and knowing the ID must not automatically grant access to related logs.

## 6. Choosing Status and Error Codes Intentionally

| Condition | Example HTTP Status | Public Code | Displayed Message |
| --- | --- | --- | --- |
| Resource absent/inaccessible per policy | 404 | `RESOURCE_UNAVAILABLE` | Unable to access resource. |
| Forbidden and policy allows disclosing denial | 403 | `ACCESS_DENIED` | You do not have permission to perform this operation. |
| Request violates schema/input values | 400 | `INVALID_REQUEST` | Request data is invalid. |
| Upload exceeds limit | 413 | `UPLOAD_TOO_LARGE` | File exceeds the allowed limit. |
| Unsupported file format | 415/400 | `UNSUPPORTED_FILE_TYPE` | File format is not supported. |
| Unexpected internal I/O error | 500 | `STORAGE_ERROR` | Unable to complete the operation. |
| Storage service temporarily down | 503 if appropriate | `STORAGE_UNAVAILABLE` | Service is temporarily unavailable. |

This is an **illustrative table**, not a status rule mandated for every API.

In private-resource systems, sometimes both “does not exist” and “no permission to view” must return **404 with the exact same schema/message** so as not to create an existence-probing oracle. Conversely, an API serving authenticated users may deliberately use 403. The choice must follow authorization policy and be applied consistently, not merely to polish text.

Watch out for **non-text side channels**: large differences in status, body size, or latency can reveal whether a resource exists. Never promise complete concealment solely by changing the message text.

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
                    "Không thể truy cập tài nguyên được yêu cầu.",
                    requestId);
        }

        if (error instanceof IllegalArgumentException) {
            return new PublicError(
                    400,
                    "INVALID_REQUEST",
                    "Dữ liệu yêu cầu không hợp lệ.",
                    requestId);
        }

        return new PublicError(
                500,
                "STORAGE_ERROR",
                "Không thể hoàn tất thao tác.",
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
        String id = "REQ-DEMO-001"; // fixed ONLY for example

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

Run with JDK 17+ and a UTF-8 capable terminal:

```bash
javac -encoding UTF-8 SafePublicErrorDemo.java
java SafePublicErrorDemo
```

Stdout on success:

```text
404 | RESOURCE_UNAVAILABLE | Không thể truy cập tài nguyên được yêu cầu. | REQ-DEMO-001
404 | RESOURCE_UNAVAILABLE | Không thể truy cập tài nguyên được yêu cầu. | REQ-DEMO-001
500 | STORAGE_ERROR | Không thể hoàn tất thao tác. | REQ-DEMO-001
400 | INVALID_REQUEST | Dữ liệu yêu cầu không hợp lệ. | REQ-DEMO-001
```

**Explanation:**

1. Exceptions containing paths/tokens remain **strictly internal** inside the object. The mapper never calls `getMessage()` or `toString()`.
2. The two private file errors `NoSuchFileException` and `AccessDeniedException` map identically, reducing the risk of leaking existence state.
3. Unexpected `IOException` receives code `STORAGE_ERROR`, without broadcasting the raw cause.
4. `record PublicError` has fixed fields and does not retain `Throwable`.
5. `IllegalArgumentException` is used only to illustrate invalid input. In real applications, do not map **every** `IllegalArgumentException` to a client error; internal programming bugs can also throw it. Classify at the business layer with dedicated exceptions.
6. The fixed ID in the demo yields deterministic stdout; in real systems, use a server-generated ID per request.

The example is pure-Java **error mapping**, not an HTTP server. It does not replace authorization checks before reading files.

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
                // Diagnostic: only allowed fields,
                // do not print ex, ex.getMessage(), ex.getFile().
                System.err.println(
                        "event=FILE_READ_FAILED"
                        + " type=NoSuchFileException"
                        + " requestId=" + requestId);

                // Simulated public response.
                System.out.println("status=404");
                System.out.println("code=RESOURCE_UNAVAILABLE");
                System.out.println(
                        "message=Không thể truy cập tài nguyên được yêu cầu.");
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
message=Không thể truy cập tài nguyên được yêu cầu.
requestId=REQ-DEMO-002
```

**Stderr** when the same operation fails:

```text
event=FILE_READ_FAILED type=NoSuchFileException requestId=REQ-DEMO-002
```

The two outputs reside on two different streams; IDEs/terminals may interleave them in different orders when displayed together. If `stderr` is forwarded externally, it **is also a public channel**; use a logging system with protection policies rather than relying solely on the names stdout/stderr.

Here the program creates a fresh directory and intentionally reads a file not yet created, so `NoSuchFileException` is the expected outcome in normal environments. Absolute paths and filenames do not appear because the code prints neither `internalPath` nor the exception. If another uncaught I/O error occurs, `main` can still print a stack trace: **real servers must have an error boundary** translating unknown errors into safe public responses, instead of letting the runtime emit stack traces over HTTP.

## 9. Diagnostic Logs Also Need Allowlist Design

Internal logs help technical support, but that does not permit logging arbitrary data.

**Pattern that easily leaks:**

```java
logger.log(Level.SEVERE,
        "Read failed: " + path + " / " + exception.getMessage(),
        exception);
```

This snippet is an **anti-pattern in broadly accessible logging systems**. It can send the path, message, cause, and stack trace to every sink configured on the logger. That does not mean stack-trace logging is forbidden in all environments; tier logs and evaluate information policies.

**More controlled log-field pattern:**

```java
logger.log(Level.WARNING,
        "event={0} requestId={1} errorCategory={2}",
        new Object[] {
                "FILE_READ_FAILED",
                requestId,
                "NOT_FOUND_OR_DENIED"
        });
```

This snippet assumes variables/logger are initialized. Fields come from a fixed catalog, not from `exception.getMessage()`. If stack traces are needed in a dedicated protected channel, enforce restricted access, retention limits, and secret/PII inspection policies. Calling a logger “internal” does not change the sensitivity of its data if it outputs to a broad-access dashboard.

| Allowlisted Field | Example | Caution |
| --- | --- | --- |
| `eventCode` | `FILE_READ_FAILED` | Use a fixed catalog |
| `requestId` | Validated UUID | Do not encode customer IDs/paths |
| `operation` | `READ_RESOURCE` | Do not log raw queries/paths |
| `errorCategory` | `NOT_FOUND_OR_DENIED` | Do not expose fine-grained private permissions |
| `serviceCode` | `DOCUMENT_SERVICE` | Use only approved names |
| `durationBucket` | `under_100ms` | Avoid unnecessary granularity |
| `publicErrorCode` | `RESOURCE_UNAVAILABLE` | Match the response code |

Never place file paths, emails, tokens, or raw filenames into metrics labels. That creates data-leakage risk, explodes label *cardinality*, and makes monitoring systems hard to operate.

## 10. `requestId`: Tracing Without Exposing Secrets

A request ID lets support engineers look up the exact incident in logs without asking users for screenshots of stack traces.

Principles:

1. Generate the ID on the server, e.g., `UUID.randomUUID().toString()`, or use a trace ID from a controlled mechanism.
2. Never concatenate `userId + path + token` into an ID, and never emit hashes of low-entropy secrets assuming they are harmless.
3. Never treat a request ID as proof that the user is authorized to read full logs.
4. If accepting `X-Request-ID` from a client, validate length, charset, control characters, and trust policy; if untrusted, generate a new ID.
5. Protect log-query tools with authentication/authorization; knowing a request ID is **not enough** to view internal diagnostics.
6. Never use the fixed demo IDs in production.

Snippet:

```java
String requestId = java.util.UUID.randomUUID().toString();
```

Because real IDs are random, fixed stdout cannot be written for a program generating a fresh ID on each run. The two earlier examples used `REQ-DEMO-...` solely for convenient output verification.

## 11. Uploaded Filenames Are Not Trusted Data

Client-submitted filenames can contain local paths or PII:

```text
C:\Users\Alice\Documents\medical-result.pdf
customer-123456789-bank-statement.pdf
../private/secret.txt
```

Never use this string directly as a server storage path or print it into public error logs. Issues include:

- Path traversal and separator differences between Windows and Unix.
- Filename collisions and intentional overwrites.
- Very long strings or control characters used for log/header injection.
- Personal information embedded by users in filenames.
- File content spoofing extensions or MIME types.

A pragmatic policy:

- Server generates a **storage key** independent of the original name, with sufficient uniqueness.
- Enforce upload byte limits, actual file types, and resource ownership.
- Store the **display name** separately only when business logic requires it; display it only to authorized users.
- Never place the storage file path in HTTP responses or internal file-style URLs.
- Build download `Content-Disposition` headers using a library with proper encoding/validation; never concatenate raw strings containing CR/LF.

Illustrative snippet, not a complete upload handler:

```java
String storageKey = java.util.UUID.randomUUID().toString();
Path destination = controlledUploadRoot.resolve(storageKey);
```

`controlledUploadRoot` must be server-owned with proper filesystem/sandbox permissions. You also need strategies against symlink races, capacity/quota control, policy-based scanning, and error/partial-write cleanup.

## 12. Do Not Assume `normalize()` Solves Path Security

In Java NIO, `Path.normalize()` removes syntactic path components such as `.` and `..`; `toAbsolutePath()` produces an environment-dependent absolute form. Neither call **verifies authorization**, prevents all symbolic-link/race cases, or proves the file lies inside the real permitted root.

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

Never use a raw client-supplied path as proof of access rights. If the application handles paths inside a directory an adversary can mutate, use directory-handle mechanisms and proper permissions; use `SecureDirectoryStream` only when supported by the provider and paired with proper anti-race design.

Hiding paths from errors is one part of **reducing information disclosure**, not a substitute for real file access protection.

## 13. Indirect Leak Sources

Even when a service stops returning `ex.getMessage()`, another layer can still leak:

- Default debug error pages enabled with `trace` or `exception`.
- A JSON serializer encountering a DTO containing a `Throwable` field.
- An HTTP filter adding `X-Error-Detail` with the raw error cause.
- Middleware echoing query strings or uploaded filenames.
- Tracing SDKs sending raw requests/exceptions to third parties.
- UI displaying raw error bodies from an HTTP client.
- Support emails attaching full server logs.
- Structured log exporters sending raw `path` fields to broad-access dashboards.

You need a **centralized error boundary** for all unclassified exceptions. Use allowlisted response schemas, audit HTTP headers, disable debug pages outside development, inspect framework error handlers, and restrict logging/tracing data. A 500 status code does not protect the body's contents by itself.

## 14. Redaction Helps, but Is Not the Sole Shield

**Redaction** removes or masks fields such as `Authorization`, tokens, or PII. When forced to handle a raw object, you can redact schema-defined fields before logging.

However, a regex over an arbitrary message is not a complete security policy:

```java
String sanitized = message.replaceAll(
        "token=[^ ]+", "token=[REDACTED]");
```

The snippet above **is insufficient** when tokens span newlines, use encoding, use different delimiters, or live inside `cause`; Windows/Unix paths, JSON/XML, and personal data have no single reliable catch-all pattern.

Priority order:

1. Never construct public fields from raw exceptions in the first place.
2. Select status/code/message from a fixed table.
3. Minimize log fields using an allowlist.
4. Redact fields that must be processed at a dedicated layer, backed by tests.
5. Control log access, retention, encryption, and export destinations.
6. Re-verify after library/framework upgrades because an error serializer may introduce new fields.

Even if a function named `sanitize()` is called everywhere, it must still be evaluated against its inputs and output paths; **a function name is not proof against leakage**.

## 15. Log Injection from Client Content

An unvalidated filename or request ID can contain newline characters:

```text
report.pdf
ERROR admin access granted
```

If the system concatenates strings directly into logs, an attacker can forge log entries. Countermeasures:

- Do not log unnecessary raw inputs.
- Prefer structured logging with format-appropriate escaping/encoding.
- Enforce length limits and strip/reject control characters per policy.
- Do not accept arbitrary client-supplied request IDs without validation rules.
- Distinguish server-generated fields from user-provided fields.
- Rate-limit events/logs and apply backpressure to prevent log flooding.

Fixed/validated `requestId` values and enum `eventCode` values are far easier to protect than concatenating every request detail.

## 16. Testing Public Errors with Sensitive Canary Data

A good test proactively constructs exceptions containing fake paths/tokens, then asserts those strings **never appear in public output**. Never test only the happy path.

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
                    "Tài nguyên không khả dụng.");
        }
        return new PublicError(500, "STORAGE_ERROR",
                "Không thể hoàn tất thao tác.");
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

This test is a **minimum contract check**; it does not prove the entire server is safe. In practice, test actual JSON responses/headers/bodies emitted by the framework, telemetry/log sinks, nested causes, Windows/Unix paths, URIs, tokens, Unicode, control characters, user content inside archives, and unexpected middleware failures.

### Testing Checklist by Error Type

| Scenario | Canary Data | Verification Condition |
| --- | --- | --- |
| File does not exist | Private path | No path in response |
| File access denied | `AccessDeniedException` with path | No filename/internal permission leaked |
| Unexpected I/O error | `IOException` with canary token | Token absent from public responses/logs |
| Invalid input | Filename with `../` | Raw name is not echoed |
| Upload too large | Filename containing email | Only appropriate code/limit shown |
| Parser error | CSV line containing fake PII | File content not shown |
| Nested cause | Exception chain containing path | Serializer does not expose cause/stack |
| Header injection | ID containing CR/LF | ID rejected or replaced |
| Logging | Token inside request body | Not written to broad-access sinks |

## 17. Layering Responsibilities

An easily auditable architecture separates:

**File adapter / repository:** knows `Path`, `Files`, `FileChannel`, and the real I/O cause. Never decides public messages.

**Business service:** classifies errors by user permissions, resource, and semantics. Decides which cases return 403 and which return 404 to curb enumeration.

**API boundary:** catches classified and unknown errors, builds `PublicError` with only allowlisted status/code/message/requestId. Never feeds `Throwable` directly to a serializer.

**Diagnostic logging:** records controlled events and IDs; uses separate audit logs when needed with access control and retention. Detailed information is permitted only under explicit protection policies.

**Security tests and monitoring:** verifies real error paths, log/exporter systems, and post-deploy framework configuration. Never tests only a single isolated exception-handler function.

## 18. Common Design Mistakes

1. Returning `IOException.getMessage()` directly to users.
2. Appending `Path.toAbsolutePath()` to 404 messages.
3. Serializing `Throwable` or `StackTraceElement[]` inside DTOs.
4. Showing 500 debug error pages in production.
5. Logging full request bodies or `Authorization` headers on parser failures.
6. Letting raw uploaded filenames become server paths or public log entries.
7. Believing `getFileName()` strips all PII.
8. Distinguishing 403/404 inconsistently on confidential resources, enabling enumeration.
9. Using error codes that embed internal paths/storage keys.
10. Constructing request IDs from user identifiers, filenames, or secrets.
11. Letting anyone who knows a request ID view logs without authorization.
12. Applying one regex redaction and assuming everything is safe.
13. Failing to handle CR/LF and log injection from inputs.
14. Auditing only controllers while ignoring middleware, headers, and serializers.
15. Treating `stderr`, tracing dashboards, or support tickets as never-public channels.
16. Putting emails/PII into metrics labels, causing leaks and high cardinality.
17. Relying on `Path.normalize()` instead of authorization/symlink safety.
18. Failing to test unexpected errors and automatic framework stack traces.

## 19. Practice Exercises

**Exercise A — Fix the anti-pattern.** Replace the following code with a public DTO containing no path/message:

```java
catch (IOException ex) {
    return "Failed: " + path + " / " + ex.getMessage();
}
```

**Exercise B — Confidential resources.** Design responses for two cases on the same ID: not found vs. no permission to view. When do you return 404 for both? How do you ensure authorization checks still execute?

**Exercise C — Filenames containing PII.** A customer uploads a file whose name contains their full name and medical details. Why should this name not appear in public logs? Create a server-side storage key and a display name governed by its own policy.

**Exercise D — Error serializer.** A framework returns JSON containing `message` and `trace` from an exception. Build a DTO containing only `status`, `code`, `message`, and `requestId`; test against the real response.

**Exercise E — Preventing log injection.** A client sends a request ID containing newlines and forged log lines. Describe how to bound length/charset or substitute a server-generated ID.

**Exercise F — Cross-platform testing.** Add canary Windows paths, Linux paths, UNC paths, private URLs, tokens, and Unicode filenames to tests; verify none of those strings appear in responses.

## 20. References

- [Java SE 17 — FileSystemException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemException.html): `getFile()`, `getOtherFile()`, `getReason()`.
- [Java SE 17 — NoSuchFileException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/NoSuchFileException.html).
- [Java SE 17 — AccessDeniedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/AccessDeniedException.html).
- [Java SE 17 — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html).
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html).
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

## 21. Key Takeaways

Public messages must answer **what the user can do next**, never reflect where the system stores files, whether a private resource exists, or which token/request payload triggered an exception. `NoSuchFileException`, `AccessDeniedException`, `FileSystemException`, and `IOException` can carry paths, OS messages, and nested causes; never send raw exceptions to UI/HTTP/email/webhooks.

The right pattern is **I/O error → classify and authorize → map status/code/message from an allowlist → attach a safe `requestId` → log controlled diagnostics → test failure branches**. Logs, telemetry, and support notifications must also be protected. Hiding a path inside one catch block is only a single step; practical security requires authorization, output control, anti-injection, log policies, and system-level testing.
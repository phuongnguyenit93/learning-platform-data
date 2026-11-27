# Handling Test Logs and Failure Reports Safely

## 1. Why Do REST Docs Test Logs Need Protection?

In the **SPRING_REST_DOCS** module, HTTP tests using MockMvc, WebTestClient, or REST Assured both verify the API and generate snippets. When a test fails, the test framework, HTTP client, assertion library, and build tool may record request/response bodies, headers, exception messages, stack traces, test parameters, and snippets.

This data can contain Authorization headers, cookies, session IDs, API keys, access/refresh tokens, passwords, PII, query tokens, connection strings, or internal hostnames. Spring REST Docs preprocessors process only the recorded operation used to generate snippets; they do not automatically mask HTTP client logs, assertion failures, JUnit reports, console output, or CI artifacts.

The goal is to retain enough information to identify the test, operation, status, and failing assertion location without printing credentials or sensitive payloads.

## 2. Channels That Can Leak Data

| Channel | Example | Risk |
| --- | --- | --- |
| Test framework | Exceptions and stack traces | Exception message contains sensitive input |
| HTTP client logging | Request/response headers, bodies | Raw Authorization or payloads |
| Assertion failure | Expected/actual values | Prints the entire response body |
| JUnit XML/HTML | Failure messages, captured output | CI stores reports long-term |
| Build console | Gradle/Maven output | Plugins print raw data |
| REST Docs snippets | http-request/http-response | Missing preprocessor or faulty masking |
| Application logs | Controller/service/security logs | Logs request bodies or cookies |
| CI artifacts | Reports, snippets, dumps | Broad access permissions, long retention |

No single configuration protects every channel. Identify where raw exchanges can be recorded and set dedicated policies for each.

## 3. Log Only Necessary Metadata

When a test fails, metadata is usually sufficient to locate the issue:

- Test class and method.
- REST Docs operation identifier.
- HTTP method and route template.
- Expected status and actual status.
- Content-Type and processing duration.
- Synthetic test correlation ID.
- Specific failing assertion or path.

Avoid logging Authorization, Cookie, Set-Cookie, query tokens, raw bodies, passwords, secrets, customer data, or full environment variables.

Example safe failure summary:

```text
Test: OrderDocumentationTest.getOrder_whenMissing_returns404
Operation: orders-get-not-found
Request: GET /api/orders/{id}
Expected status: 404
Actual status: 500
Content-Type: application/problem+json
Test correlation ID: test-req-42
Failed assertion: $.code expected ORDER_NOT_FOUND
```

This information helps trace the test and operation without printing tokens or full bodies.

## 4. Avoid Wire Logging in Regular Tests

HTTP clients may have wire/debug logging modes that print headers and bodies. This mode is useful during local investigation but dangerous in CI or environments using near-production data.

- Do not enable raw request/response logging in the default pipeline.
- If debugging is needed, restrict it to a specific test and synthetic fixtures.
- Do not log Authorization, Cookie, or Set-Cookie.
- Do not dump bodies if they contain tokens or PII.
- Review logging configurations and CI variables so debug mode is never enabled unintentionally.
- Disable debug logging after investigation and inspect generated reports/artifacts.

With Spring Boot, DEBUG-level logging for HTTP clients can print raw exchanges. Do not assume DEBUG is always safe.

## 5. Assertion Failures Should Not Print Raw Payloads

Some convenient assertions display full expected/actual values on failure. For sensitive bodies, failure messages can end up saved in JUnit XML.

Instead of comparing the entire body in every case:

```java
.andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
.andExpect(jsonPath("$.status").value(400))
.andExpect(jsonPath("$.correlationId").value("test-req-42"));
```

Assert only the needed fields. If you must compare a full body, use synthetic fixtures and ensure reporters do not print credentials. Never append raw bodies to custom assertion messages.

Example:

```java
assertEquals("VALIDATION_ERROR", actualCode,
        "Error code mismatch for operation orders-create");
```

The message indicates the operation and field to check without exposing the full response.

## 6. Redact Before Logging

If you need to log part of a request/response, create a helper that logs only allowlisted fields. Do not log the entire object and try to strip secrets with regex afterward.

```java
Map<String, Object> safeSummary = Map.of(
        "operation", "orders-get-not-found",
        "status", 404,
        "contentType", "application/problem+json",
        "correlationId", "test-req-42"
);
logger.info("REST Docs test failure: {}", safeSummary);
```

For headers, the allowlist might include Content-Type, Accept, or a dummy request ID. Exclude Authorization and cookies. If you need to know whether authentication was sent, log authorizationPresent=true rather than the value.

## 7. REST Docs Preprocessors Do Not Protect All Logs

You can mask tokens in the recorded operation before generating snippets:

```java
.andDo(document("token-get",
    preprocessRequest(
        modifyHeaders().set("Authorization", "Bearer [REDACTED]")
    ),
    preprocessResponse(
        replacePattern(
            Pattern.compile(
                "\"accessToken\"\\s*:\\s*\"[^\"]+\""),
            "\"accessToken\":\"[REDACTED]\"")
    )
))
```

This configuration protects snippets generated from the preprocessed operation. It does not automatically mask:
- HTTP client wire logs already written earlier.
- Assertion failures containing the original body.
- Application logs recording Authorization.
- JUnit reports or captured stdout/stderr.
- Custom reporters reading the original response.
- Debug dumps created by other tests or plugins.

Preprocessing is a protective layer for documentation; logging requires its own policy.

## 8. Keep Stack Traces While Excluding Secrets

Stack traces are useful for locating programming errors, yet exception messages may contain SQL, URLs with credentials, request bodies, or user data.

- Keep exception types, classes/methods, and internal stack traces under appropriate access control.
- Return a generic message to clients.
- Do not concatenate raw payloads/tokens into exception messages.
- Do not expose unvetted exception messages in error responses.
- Use a correlation ID to link public responses to internal logs.
- Control access and retention for logs containing stack traces.

Example:

```java
catch (Exception exception) {
    String correlationId = requestCorrelation.currentId();
    logger.error("Unexpected API failure, correlationId={}",
            correlationId, exception);
    throw new InternalApiException(
            "An internal system error occurred", correlationId);
}
```

The example keeps the stack trace in internal logs while sending a generic message over HTTP. Choose a single layer to own exception logging to avoid duplicate noise.

## 9. Managing Test Fixtures and Secrets

Use dummy data with easily recognizable markers:

```text
test-secret-marker-987
test-user@example.test
test-session-id-42
```

Do not use production tokens, personal credentials, database snapshots with real PII, or environment variables containing secrets as expected responses. If tests require authentication, generate dummy tokens or credentials usable only within the test environment.

Dummy markers allow the pipeline to scan artifacts to detect unintended leaks.

## 10. Configuring JUnit and Build Reports

JUnit XML and HTML reports can contain failure messages and captured output. With Gradle Groovy DSL, you can limit console output:

```groovy
tasks.test {
    testLogging {
        events "failed", "skipped"
        showStandardStreams = false
        exceptionFormat = "short"
    }
}
```

This configuration reduces console output; short exceptionFormat is not redaction. JUnit XML can still contain failure messages, so inspect reports and artifact access permissions.

With Maven Surefire/Failsafe, choose appropriate console/report settings and avoid plugins that dump raw exchanges. Do not disable all failure details if the team needs diagnostics; instead, make failure messages safe at the source.

## 11. Scanning Artifacts Before Publishing

After documentation tests run, the pipeline can scan:
- build/generated-snippets or target/generated-snippets.
- JUnit XML and HTML reports.
- Captured stdout/stderr.
- Asciidoctor output.
- Debug dumps or HTTP exchange files created by plugins.

Scan for dummy markers from fixtures:

```text
test-secret-marker-987
test-session-id-42
```

If a marker appears in a public artifact, the pipeline must fail. Avoid overly broad regexes that cause false positives; prefer distinctive dummy markers combined with checks for known sensitive headers/fields.

Do not upload reports/snippets to a public artifact store before scanning completes. Set appropriate retention and access controls.

## 12. Safe Failure Reporters

You can build a helper containing only allowlisted metadata:

```java
record RestDocsFailureSummary(
        String testName,
        String operation,
        String method,
        String route,
        int expectedStatus,
        int actualStatus,
        String contentType,
        String correlationId,
        String failedPath) {}

logger.error("REST Docs failure: {}", new RestDocsFailureSummary(
        "getOrder_whenMissing_returns404",
        "orders-get-not-found",
        "GET",
        "/api/orders/{id}",
        404,
        500,
        "application/problem+json",
        "test-req-42",
        "$.code"
));
```

Do not put raw requests/responses, Authorization, or cookies into the summary. If attaching the summary to reports via a JUnit extension/listener, the listener should receive only filtered data. If a listener reads the raw response, it must redact before writing.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Token appears in JUnit XML | Assertion printed raw body/header | Assert safe fields and metadata messages |
| Console prints HTTP exchange | Wire logging set to DEBUG | Disable by default, enable locally with controls |
| Snippet masked yet report still leaks | Mistakenly assumed preprocessor covers all channels | Separate logging/report policies |
| Stack trace contains SQL/secrets | Exception message concatenated sensitive data | Use safe messages, controlled logs |
| Report contains stdout | showStandardStreams enabled | Disable if unnecessary and review reports |
| Public CI artifact contains PII | Uploaded before scan step | Scan before publishing, restrict access |
| Debug dump left behind | Plugin/test created temporary file | Clean up debug artifacts per policy |
| Failure message lacks useful info | Hid all details | Allowlist metadata and correlation IDs |
| Test uses real token | Fixture depends on production | Use dummy tokens/test-only credentials |
| Scan produces false positives | Generic regex lacks context | Use dummy markers and per-file/type rules |

## 14. Safety Checklist for Logs and Reports

- [ ] Raw wire logging is disabled in default CI.
- [ ] Authorization, Cookie, Set-Cookie, and tokens are never logged.
- [ ] Raw bodies are not printed in assertion failures if they contain sensitive data.
- [ ] Exception messages contain no credentials or payloads.
- [ ] Internal stack traces have appropriate access control and retention.
- [ ] REST Docs preprocessors mask data in snippets intended for publication.
- [ ] JUnit XML/HTML reports are treated as artifacts that may contain sensitive data.
- [ ] Captured stdout/stderr is controlled.
- [ ] Tests use dummy fixtures and distinctive markers.
- [ ] CI scans snippets, reports, and rendered docs before publishing.
- [ ] Failure summaries contain only allowlisted metadata.
- [ ] Debug logging is enabled only temporarily and disabled after investigation.

## 15. Practice Exercise

Use tests for POST /api/auth/token and GET /api/orders/{id}:

1. Create fixtures with marker test-secret-marker-987, using no real tokens.
2. Create an error response containing a dummy correlation ID.
3. Assert status, error code, and correlation ID without printing the full body.
4. Configure REST Docs preprocessors to mask tokens in request/response snippets.
5. Disable HTTP wire logging in the default test configuration.
6. Configure Gradle test logging to show only failed/skipped events and disable standard streams.
7. Run an intentionally failing test; verify the console and JUnit report do not contain the marker.
8. Verify generated snippets and Asciidoctor output also do not contain the marker.
9. Add an artifact scan after test/report generation and before upload.
10. Create a failure summary containing test name, operation, status, Content-Type, correlation ID, and JSON path.
11. Verify access permissions and retention of reports/artifacts in CI.
12. Enable debug logging locally with dummy fixtures, then disable it and confirm the default pipeline remains safe.

**Completion criteria:** you can identify channels that may record raw HTTP data; design failure messages using allowlisted metadata; distinguish REST Docs preprocessing from logging redaction; protect stack traces, JUnit reports, and CI artifacts; and verify pipeline scanning before publishing.

## References

- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessing.html): processing recorded requests/responses before generating snippets.
- [JUnit 5 User Guide — Test Execution and Reporting](https://junit.org/junit5/docs/current/user-guide/#running-tests): running and reporting tests.
- [Gradle — Java testing](https://docs.gradle.org/current/userguide/java_testing.html): configuring test logging and test reports.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): what to log/not log and protecting logs.

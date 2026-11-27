# Limiting Sensitive Data in Reports and Logs

CI/CD generates a wide range of evidence throughout the software lifecycle: build logs, test reports, security scans, deployment events, traces, metrics, crash dumps, and diagnostic artifacts. This data helps explain why a change was accepted, why a pipeline failed, or which version is running. However, it can also contain passwords, tokens, private keys, personal data, payment details, authentication headers, SQL statements, and user request payloads.

Reports and logs must be detailed enough for investigation while limiting sensitive data right at collection time. The safe approach is to **record only necessary fields, transform or strip sensitive data before distribution, and restrict who can view it and for how long**. Redaction at the display layer is only a supplementary control; if a secret has already entered raw logs, artifacts, or traces elsewhere, the risk remains.

## 1. Why Can Logs and Reports Become Data Leak Vectors?

A pipeline may handle secrets and sensitive data across many steps:

- Repository checkout contains config files or test fixtures with real credentials.
- Builds read credentials to download dependencies or sign artifacts.
- Tests use tokens, connection strings, customer data, or responses from integrated systems.
- Scanners print file contents, URLs, or code snippets containing secrets.
- Deploy scripts pass credentials to clouds, clusters, or registries.
- Applications log requests, responses, exceptions, or SQL parameters.
- Crash dumps and heap dumps can retain data that existed in memory.
- Test reports can store names, emails, addresses, payloads, or stack traces.
- Artifacts and caches can bundle config files, home directories, or temporary credentials.

A sensitive value does not have to be logged explicitly to cause a leak. For example, a connection URL formatted as username:password@host; an Authorization header written in debug logs; an exception containing the full query string; or a report saving the raw request body. A value masked in the CI UI can still exist in downloadable artifacts or log archives.

Therefore, treat logs, reports, traces, metric labels, and diagnostic artifacts as controlled data channels. They are not automatically safe simply because they are produced by internal systems.

## 2. Classifying Data Before Logging

Before designing a logging policy, classify data fields by sensitivity level and intended use.

| Category | Examples | Handling |
|---|---|---|
| Public | Commit SHA, job name, published application version | Can be logged as needed for traceability |
| Internal | Service name, cluster alias, internal package name | Share only within authorized scope |
| Sensitive | Email, user ID, IP, tenant ID, order ID | Minimize, pseudonymize, or restrict access |
| Authentication secrets | Password, API token, cookie, private key | Never log values; strip or mask prior to logging |
| High-sensitivity/personal data | Personal profiles, payment details, identity records | Avoid collecting in telemetry; process only in approved systems |
| Potentially sensitive operational data | SQL, request body, internal hostname, topology | Log only necessary parts and enforce access control |

Names or identifiers are not always harmless. A user ID can link back to an individual when joined with another system. An IP, tenant ID, or order ID can reveal an individual's or organization's activity. Evaluate joinability risk, not just each field in isolation.

Classification must apply to both success logs and error logs. Exceptions, debug outputs, and test reports often contain more detail than normal logs and require corresponding policies.

## 3. Data Minimization Principles

Data minimization means collecting only the data needed for a specific operational, security, or investigative purpose.

Before adding a field to logs, ask:

- Which operational question does this field help answer?
- Can a status, error code, or aggregate count replace the raw value?
- Can a correlation ID replace the user or request payload?
- Who needs to view this field?
- Could this field be combined with other data to identify an individual?
- How long does it need to be retained?
- If this field leaks, what is the impact?

For example, investigating a login failure usually requires timestamp, outcome, error code, client type, and correlation ID. There is no need to log passwords, cookies, or the entire request body.

Instead of logging:

~~~json
{
  "event": "login_failed",
  "email": "customer@example.com",
  "password": "P@ssw0rd",
  "authorization": "Bearer eyJhbGciOi...",
  "requestBody": {
    "email": "customer@example.com",
    "password": "P@ssw0rd"
  }
}
~~~

Log the minimal event:

~~~json
{
  "event": "login_failed",
  "reason_code": "INVALID_CREDENTIALS",
  "subject_ref": "usr_7f21a9",
  "correlation_id": "req_01J9K...",
  "client_type": "web"
}
~~~

The subject_ref value in the example is a pseudonymized identifier. The system must still protect the mapping between this identifier and the real account. Do not put the raw data in another field of the same log.

## 4. Never Log Secrets

Treat the following data types as secrets or credentials:

- Passwords and database connection strings containing passwords.
- Access tokens, refresh tokens, API keys, and webhook secrets.
- Authorization headers, cookies, and session IDs.
- Private keys, signing keys, and certificate material.
- Cloud access keys, temporary credentials, and OIDC tokens.
- Registry credentials and deploy tokens.
- Secrets in query parameters or URLs.
- Configuration file contents with secret values.

Do not use logs to verify that a secret was provisioned properly. Instead, log statuses like “credential retrieved,” “authentication succeeded,” or standardized error codes. If identifying the secret version is needed, log an approved secret resource/version identifier, not the value.

Keep secrets out of:

- Console output or debug prints.
- Shell command lines and process arguments.
- Exception messages.
- Test assertion messages.
- JUnit XML, HTML reports, or coverage metadata.
- Artifacts, caches, and build scans.
- Trace attributes, span events, or baggage.
- URLs, query strings, or filenames.
- Screenshots/videos of terminals or admin UIs.

If a secret has appeared in a log, treat that credential as potentially compromised: revoke or rotate it per procedure, identify all copies, and remediate logs/artifacts per incident policy. Simply deleting a log line from the UI does not make the old credential safe again.

## 5. Allowlist-Based Logging Design

A safe pattern is defining a log schema with an explicit allowlist of permitted fields. The application logs only approved fields rather than dumping entire objects or serializing raw requests.

Example event schema:

~~~json
{
  "timestamp": "2026-11-18T10:20:30Z",
  "level": "ERROR",
  "service": "payments-api",
  "environment": "production",
  "event": "payment_authorization_failed",
  "error_code": "PROVIDER_TIMEOUT",
  "correlation_id": "req_01J9K...",
  "duration_ms": 1200
}
~~~

An allowlisted schema makes it clear during review which fields are logged and which data types are prohibited. For structured logs, avoid stuffing an entire request object into a JSON string field because redaction pipelines struggle to control nested fields and key variations.

Standardize sensitive field names to block, for example:

- password, passwd, secret, token, api_key.
- authorization, proxy_authorization, cookie, set_cookie.
- private_key, client_secret, access_token, refresh_token.
- card_number, cvv, security_code.
- email, phone, address, or personal fields per organizational data classification.

This list cannot cover every field name. Schema-level allowlisting remains more reliable than solely scanning for a handful of banned keywords.

## 6. Safe Logging in Java Applications

In Java, avoid logging raw requests, entities, or objects containing authentication data. Construct dedicated log events with selected fields.

Example with SLF4J:

~~~java
log.warn(
    "Payment authorization failed: service={}, errorCode={}, correlationId={}, durationMs={}",
    "payments-api",
    errorCode,
    correlationId,
    durationMs
);
~~~

When using structured logging, build a controlled log object:

~~~java
Map<String, Object> event = Map.of(
    "event", "payment_authorization_failed",
    "service", "payments-api",
    "error_code", errorCode,
    "correlation_id", correlationId,
    "duration_ms", durationMs
);

logger.atWarn().addKeyValue("event", event).log("Payment authorization failed");
~~~

Structured logging syntax depends on the backend and library version. What matters is that the event object contains only approved fields, without serializing full requests or domain entities.

Pay special attention to exceptions. Stack traces can be helpful, yet exception messages sometimes contain JDBC URLs, SQL parameters, HTTP URLs, or response bodies. Log the exception type, error code, and correlation ID; send full stack traces only to tightly access-controlled diagnostic stores when genuinely needed. Never concatenate secrets into exception messages.

## 7. Multi-Layer Redaction and Masking

Redaction removes or replaces sensitive data before writing or sharing. It can be implemented across multiple layers:

1. **Application layer:** avoid emitting sensitive fields in logs from the start.
2. **Logging library/appender:** filter or rewrite events before writing.
3. **Agent/collector:** strip or replace attributes prior to shipping.
4. **Backend ingestion:** enforce policies upon ingestion.
5. **Report/export layer:** produce redacted copies for sharing.
6. **Access layer:** restrict who can view any raw data that must still be kept.

Prefer handling this at the source. If an application writes secrets to a local log file and the collector masks them later, the secret can still persist on disk, in backups, or in uploaded files before the collector processes it.

Masking—such as replacing part of an email or token with asterisks—can aid operational support, but never leave more characters visible than necessary. For credentials, the safest approach is logging no portion of the value at all.

Example:

~~~text
Authorization: Bearer [REDACTED]
email: u***@example.com
payment_card: [REMOVED]
password: [REMOVED]
~~~

Do not apply masking arbitrarily to every field. Some values can be pseudonymized with HMAC to correlate events within a controlled scope, whereas authentication secrets must be removed entirely.

## 8. Be Cautious with Regex Redaction

Regular expressions can catch certain patterns such as emails, tokens, or headers, but cannot guarantee finding every sensitive data format.

Common pitfalls:

- Tokens in a new format do not match the regex.
- Secrets are encoded, split, or escaped.
- JSON uses varying field-naming conventions.
- Values appear inside exceptions or nested objects.
- Regex accidentally masks legitimate data, hurting investigation.
- Complex patterns consume high CPU or cause ReDoS on untrusted input.

If you use regex, treat it as a supplementary defense layer. Test against synthetic realistic data, encoding variants, and false-positive cases. Never rely on a single regex to prove logs are secret-free.

A stronger approach combines schema allowlists, field-level policies, and redaction filters for harder-to-control sources. Any new fields should be reviewed before release.

## 9. Protecting Traces, Spans, Baggage, and Metric Labels

Observability is not limited to logs. Distributed tracing and metrics can also contain sensitive data.

For traces:

- Do not record raw HTTP headers, cookies, or Authorization values.
- Do not attach request/response bodies to spans by default.
- Do not put emails, phone numbers, tokens, or transaction contents into span attributes.
- Do not record URLs with query strings containing personal data.
- Control baggage because it may propagate across multiple services.
- Keep trace IDs and span IDs to correlate events without raw payloads.

For metrics:

- Do not use emails, user IDs, order IDs, or tokens as labels.
- Avoid high-cardinality labels like request paths containing dynamic IDs.
- Use route templates, error classes, or status groups.
- Do not attach personal data to metric exemplars or annotations.

Unsafe label example:

~~~text
http_requests_total{user_email="customer@example.com",order_id="ORD-938271"}
~~~

Better example:

~~~text
http_requests_total{route="/payments/{id}",status_class="5xx",region="ap-southeast-1"}
~~~

Metric labels can be replicated into dashboards, alerts, time-series storage, and export systems. Even a small field with high cardinality can increase costs and degrade backend performance.

## 10. Controlling Data in the OpenTelemetry Collector

The OpenTelemetry Collector can process logs, traces, and metrics before sending them to backends. Processors allow filtering, deleting, or transforming attributes according to policy. Exact configuration depends on the Collector version and bundled components.

Illustrative configuration removing certain sensitive attributes from spans:

~~~yaml
processors:
  attributes/sanitize:
    actions:
      - key: http.request.header.authorization
        action: delete
      - key: http.request.header.cookie
        action: delete
      - key: user.email
        action: delete
      - key: db.statement
        action: delete

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [attributes/sanitize, batch]
      exporters: [otlp]
~~~

This configuration only illustrates specific attribute names. Semantic conventions may change across instrumentation libraries and versions; verify the exact keys in use. The processor must be placed in pipelines covering every export path needing protection. If another exporter sends directly, data may bypass this processor.

Do not treat the collector as the sole data-protection layer. Applications must avoid emitting sensitive attributes in the first place, and backends require proper access controls and retention.

## 11. Limiting Data in CI Logs and Test Reports

CI reports are often shared more broadly than production logs because developers can download them directly from pull requests or build runs. Define what data is allowed inside reports.

Sources to audit:

- JUnit XML and test failure messages.
- Surefire/Failsafe reports.
- HTML reports, coverage reports, and screenshots.
- Build scans or dependency reports.
- Static analysis and secret scan outputs.
- Docker build outputs.
- Environment dumps and debug traces.
- Artifacts uploaded after job failures.

Avoid putting real customer data in test fixtures unless strictly necessary. Prefer synthetic or mock data. If tests must access a shared environment, use dedicated test accounts and test data.

GitHub Actions report upload example:

~~~yaml
- name: Run tests
  run: ./mvnw --batch-mode verify

- name: Sanitize test reports
  if: ${{ always() }}
  run: ./scripts/redact-test-reports.sh target/surefire-reports

- name: Upload sanitized reports
  if: ${{ always() }}
  uses: actions/upload-artifact@v4
  with:
    name: sanitized-test-reports
    path: target/surefire-reports/
    if-no-files-found: warn
    retention-days: 7
~~~

The redaction script must handle XML formatting properly and upload only the verified copy. Do not use naive string replacement that could break XML or miss nested elements. For high-risk reports, upload only filtered summaries instead of full raw output.

Do not upload the entire workspace or home directory merely for debugging convenience. Specify explicit paths and inspect contents before saving artifacts.

## 12. GitHub Actions Masking Is Not the Only Control

GitHub Actions supports storing secrets in secure configuration and masking certain values from logs. Dynamic values can also be registered via the add-mask command before commands that might print them run.

Example:

~~~yaml
- name: Use deployment credential
  env:
    DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}
  shell: bash
  run: |
    set +x
    ./scripts/deploy.sh
~~~

Do not echo a token to output just to verify it exists. Check that the variable is set via a boolean check or verify that an authentication command succeeds.

If masking a dynamic value is necessary:

~~~bash
echo "::add-mask::$VALUE"
~~~

This command only masks the registered value in the platform's own logs. It does not protect values inside artifacts, process arguments, temporary files, traces, or external logging systems. Encoded, transformed, or split values may not be recognized. Registering a mask after a secret has already appeared in logs is too late.

Do not enable shell tracing when handling secrets. Do not pass credentials via URLs or command-line arguments when restricted-permission environment variables or temporary files can be used instead. Control every step that receives an environment containing secrets.

## 13. Protecting Artifacts and Diagnostic Files

CI artifacts can contain far more data than their filenames suggest. A build bundle or report may inadvertently include:

- `.env` or `application-local.yml` files.
- Credential caches inside the home directory.
- Private keys or certificates.
- Database dumps.
- Test fixtures containing real data.
- Browser storage or cookies.
- Crash dumps, heap dumps, and thread dumps.
- Rendered configuration files containing secrets.

Before uploading, use a path allowlist and strip unnecessary files. Avoid overly broad patterns such as uploading the entire repository or workspace.

A verification step can:

- List the exact files to be uploaded.
- Scan that file set for secrets.
- Check for unusual filenames and file sizes.
- Inspect configuration files and dumps.
- Confirm reports have passed redaction.
- Apply appropriate retention and access permissions.

Artifacts can be downloaded by anyone with read access to the workflow run. Treat artifact permissions as equivalent to access to the data inside them, not merely permission to view pipeline status.

## 14. Pseudonymization and Identifier Hashing

Sometimes teams need to correlate multiple events for the same user or tenant without logging the real identifier. Pseudonymization can be used, such as HMAC with a secret key dedicated to the logging system.

~~~text
subject_ref = HMAC-SHA256(logging_key, internal_subject_id)
~~~

This produces a stable identifier within the key's scope, enabling correlation without exposing the original ID in logs. However:

- HMAC does not make data strictly anonymous.
- Anyone possessing the key and source data can reconstruct the mapping.
- Sharing one key across multiple systems increases cross-system linkability.
- The HMAC key must be protected and rotated per policy.
- Do not use plain hashing for emails or phone numbers with small value spaces; attackers can dictionary-attack them.

If only grouping is required, use buckets or cohorts instead of individual identifiers. If only short-term correlation is needed, use time-bound pseudonyms or environment-scoped keys.

## 15. Access Control for Logs, Reports, and Telemetry

Redaction does not eliminate the need for access control. Certain operational data remains sensitive even after secrets are stripped.

Recommended controls:

- Role-based access control by team and environment.
- Separating production log access from routine CI report access.
- Restricting export and download permissions.
- Auditing searches, views, and downloads of sensitive data.
- Granting temporary access when needed for investigation.
- Break-glass access with justification, expiration, and auditing.
- Separating restricted raw data from redacted data meant for wider teams.

Do not grant every developer access to all production logs simply because they need to debug. Provide aggregated dashboards, correlation IDs, and an access-request workflow for detailed data when needed.

CI artifact read permissions also warrant review. A report produced in a pull request might contain sensitive data from a failed test. Never assume every contributor or fork should be allowed to view every artifact.

## 16. Retention, Deletion, and Storage Location

Data should not be kept indefinitely simply because storage is cheap. Retention must align with operational purpose, legal obligations, and investigative needs.

Define retention separately by data type:

| Data | Retention considerations |
|---|---|
| Short-term debug logs | Long enough to investigate issues near occurrence |
| Audit/security events | Per audit and security policies |
| CI test reports | Per review and bug-fix cycle |
| Build artifacts | Per release lifecycle and rollback needs |
| Detailed traces | Potentially shorter than aggregated metrics due to volume and sensitivity |
| Crash/heap dumps | Highly restricted, tight access control, and time-bound deletion |
| Raw request samples | Only when justified by a clear, authorized purpose |

Deleting from a dashboard does not mean data is deleted from backends, archives, backups, or exports. Policies must specify deletion timelines at every layer and how copies are handled.

If data is stored across regions or providers, verify storage residency, cross-border access, and organizational requirements. Never transfer logs containing personal data to unapproved external services.

## 17. Detecting and Responding When Sensitive Data Is Logged by Mistake

Have a clear response procedure when secrets or sensitive data appear in logs or reports:

1. Identify the data type, timestamp, pipeline run, and storage locations.
2. Restrict access or remove the artifact from shared visibility per procedure.
3. If it is a credential, immediately revoke or rotate it based on risk.
4. Locate copies across log backends, artifacts, caches, exports, and backups.
5. Determine who accessed or downloaded the data if audit logs exist.
6. Delete or restrict copies according to retention and incident-response policies.
7. Fix the logging or report source causing the leak.
8. Add tests to prevent recurrence.
9. Document the incident and remediation evidence.

Do not alter raw logs in ways that destroy investigative trails if policy requires evidence preservation. You can restrict access to the raw original and generate a redacted version for broader users. For exposed credentials, deleting the log record never replaces revoking the credential.

## 18. Testing Anti-Leak Policies

Logging policies must be tested like code. Synthetic canary data can verify secrets do not appear in logs or reports.

Example test:

~~~java
@Test
void doesNotLogAuthorizationToken() {
    String fakeToken = "test-token-never-use-in-production";

    String output = captureLogs(() -> {
        paymentClient.callWithAuthorization(fakeToken);
    });

    assertThat(output).doesNotContain(fakeToken);
}
~~~

This test is illustrative only. In a well-designed system, the application should never pass the token to the logger in the first place; there is no requirement that every log contain the literal `[REDACTED]`. What matters is that the secret never appears in any inspected sink.

Additional test cases to cover:

- Passwords in exception messages.
- Cookies and Authorization headers.
- URLs with sensitive query parameters.
- Request bodies and SQL bind parameters.
- Nested JSON/XML fields.
- Stack traces and test assertions.
- OpenTelemetry span attributes and baggage.
- JUnit XML, HTML reports, and artifact ZIPs.
- Commonly encoded or transformed values.
- Artifact download permissions from other workflows.

Secret scanners help catch certain patterns, but cannot replace schema reviews and output tests. Test data should use recognizable fake tokens rather than real credentials as canaries.

## 19. Designing a Secure Evidence Pipeline for CI/CD

A flow can be organized as follows:

~~~mermaid
flowchart TD
    A[Applications and pipelines emit events] --> B[Schema allowlist at source]
    B --> C[Redaction and data minimization]
    C --> D[Collector validation]
    D --> E[Log/trace/metric backend]
    E --> F[Access control and audit]
    F --> G[Filtered dashboard or report]
    E --> H[Retention and deletion policy]
    C --> I[Secret/data leak scanning]
    I --> J{Prohibited data present?}
    J -- Yes --> K[Block export and handle incident]
    J -- No --> D
~~~

Control points:

- Applications emit only approved fields.
- Collectors strip any remaining sensitive attributes.
- Scanners inspect reports/artifacts before sharing.
- Backends enforce permissions and write audit logs.
- Dashboards display aggregated or redacted data.
- Retention policies purge logs, artifacts, and copies.
- When a leak is detected, incident workflows revoke credentials and restrict access.

If data is written to raw logs before the collector filters it, also control where raw logs are stored. Never configure a dashboard merely to hide sensitive fields in the UI while the raw data remains accessible via API or export.

## 20. Checklist for Limiting Sensitive Data in Reports and Logs

Before putting a pipeline or service into operation, verify:

- [ ] Public, internal, sensitive, and authentication-secret data are classified.
- [ ] Log schemas use allowlists and undergo owner review.
- [ ] Passwords, tokens, cookies, private keys, and Authorization headers are never logged.
- [ ] Full request/response bodies are not logged by default.
- [ ] Exceptions and stack traces are reviewed for sensitive data risk.
- [ ] Java application logs record only selected fields without arbitrary object serialization.
- [ ] Redaction occurs at the source with supplementary filtering layers.
- [ ] Regex is not the sole control for detecting sensitive data.
- [ ] Traces, spans, baggage, and metric labels contain no unnecessary personal data.
- [ ] Test reports and artifacts are sanitized before upload.
- [ ] CI uploads only allowlisted files, never the entire workspace.
- [ ] Secret masking is not treated as a substitute for keeping secrets out of logs.
- [ ] Pseudonymization uses HMAC/appropriate keys when event correlation is needed.
- [ ] Read, export, and download permissions are restricted and audited.
- [ ] Retention and deletion apply across backends, archives, artifacts, and backups.
- [ ] An incident procedure exists for exposed secrets or sensitive data.
- [ ] Canary tests verify logs, traces, and reports contain no secrets.

CI/CD evidence must help teams understand what happened without collecting more data than necessary. When log schemas are controlled, secrets are excluded at the source, traces and reports are filtered, and access and retention are bounded, teams can still trace releases via commits, artifact digests, run IDs, and correlation IDs without leaking credentials or user data.

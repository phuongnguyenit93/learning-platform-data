# Masking sensitive SQL parameters in database observability

## 1. Objective and context

When investigating slow queries or database errors, SQL and bind parameters help reproduce the issue. However, bind values often contain emails, phone numbers, addresses, tokens, payment information, personal identifiers, or private business content. Writing raw values into logs, APM tools, or tracing backends replicates that data into multiple systems, retains it longer than the database, and exposes it to broader access.

**Masking SQL parameters** is the practice of removing, replacing, or transforming bind parameter values before data is written to telemetry. The goal is to preserve enough technical context to diagnose query shape, data types, parameter positions, and performance without leaking actual values.

This lesson belongs to the **Database observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; covering context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in real environments.

After this lesson, you will be able to:
1. Identify the sources that can record SQL and bind values.
2. Distinguish SQL templates from parameter values.
3. Choose strategies for not logging, redacting, tokenizing, or allowlisting data.
4. Configure logging for Hibernate/JDBC proxies without enabling bind-value logging in production.
5. Understand why masking only at the appender/backend is often too late.
6. Design structured logs, trace attributes, and metrics free of PII/secrets.
7. Test standard logs, exceptions, tracing, and diagnostic tools.
8. Manage retention, access control, and incident response when data exposure occurs.

**Baseline:** Spring Boot 3.5.x, Java 17+, Hibernate/JPA, and Micrometer Observation. Exact logger/property names depend on Hibernate/JDBC proxy versions. Verify your actual logging backend and libraries before applying.

## 2. SQL templates and bind parameters

Prepared statements separate SQL structure from data values:

```sql
SELECT id, email, status
FROM customer
WHERE email = ?
  AND status = ?
```

The bind values might be:
- Parameter 1: `alice@example.com`
- Parameter 2: `ACTIVE`

The SQL template describes the query structure; bind values are runtime data. Database observability usually only needs the template, execution duration, row counts, DataSource, and outcome. You do not always need actual parameter values.

Avoid concatenating parameters directly into SQL strings for logging:

```java
String sql = "SELECT * FROM customer WHERE email = '" + email + "'";
log.debug("SQL: {}", sql);
```

This creates both SQL injection risk if executed and embeds PII in log messages that are hard to redact accurately.

Use prepared statements:

```java
String sql = "SELECT * FROM customer WHERE email = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    try (ResultSet result = statement.executeQuery()) {
        // Read result.
    }
}
```

Prepared statements separate SQL structure and data; however, a JDBC proxy or ORM logger can still record bind values if enabled.

## 3. Where SQL parameters can leak

| Source | Example | Risk |
| --- | --- | --- |
| Hibernate SQL logging | SQL statement | Usually template only, but verify |
| Hibernate bind logging | Parameter index/type/value | Can expose PII/secrets |
| JDBC proxy | SQL + bind values | Can render SQL with real values |
| DataSource/APM agent | DB spans and statement attributes | Can capture statements/parameters |
| Application logs | Logging request/entity/repository input | Exposes values before query runs |
| Exceptions | Constraint violations, SQL errors, custom messages | Driver/database may embed values in messages |
| Audit/debug tooling | Query console, profiler, support dumps | May store copies outside the log pipeline |
| Trace exporters | Span attributes/events | Data travels to telemetry backends |

Disabling one Hibernate logger does not guarantee a JDBC proxy or APM agent stops capturing. Audit the entire path from application to telemetry storage.

### 3.1. Data to treat as sensitive

By default, never log:
- Passwords, API keys, access/refresh tokens, session cookies.
- Card numbers, bank accounts, CVVs, or payment credentials.
- Emails, phone numbers, addresses, and personal identifiers.
- Dates of birth, health records, HR data.
- Unclassified free-form user input.
- Secrets, encryption keys, or system credentials.

Even internal identifiers like customer ID/order ID can become personal data when linked to a user. Classify data according to organizational policy; never assume data is harmless just because it is not a password.

## 4. Preferred strategy: do not log bind values

The safest approach is keeping bind parameter value logging disabled in production unless there is an approved use case.

In Hibernate 6, bind parameter logging is typically controlled by logger categories:
- `org.hibernate.SQL`: SQL statements.
- `org.hibernate.orm.jdbc.bind`: JDBC bind parameter values.
- `org.hibernate.orm.jdbc.extract`: values extracted from `ResultSet`.

Production configuration can keep SQL templates at WARN or DEBUG as needed while disabling bind/extract values:

```yaml
logging:
  level:
    org.hibernate.SQL: WARN
    org.hibernate.orm.jdbc.bind: OFF
    org.hibernate.orm.jdbc.extract: OFF
```

Verify logger names and valid levels against your Hibernate version. Some Hibernate 5 versions use different categories. Do not copy Hibernate 6 config to Hibernate 5 without verifying.

When ongoing query visibility is needed, prefer:
- SQL templates or normalized statements.
- Query fingerprints.
- DataSource/database names.
- Execution duration and outcome.
- Rows affected/returned if safely measurable.
- Trace ID/Span ID.
- Sanitized error classes/codes.

You do not need bind values to diagnose most query plan, latency, lock wait, or connection pool problems.

## 5. Environment-specific configuration

Do not enable bind logging in default configuration hoping a production profile remembers to turn it off. Put safe defaults in base configuration:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        format_sql: false

logging:
  level:
    org.hibernate.SQL: WARN
    org.hibernate.orm.jdbc.bind: OFF
    org.hibernate.orm.jdbc.extract: OFF
```

In local development, if bind values are truly needed, enable them narrowly via a dedicated profile:

```yaml
# application-local.yml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
    org.hibernate.orm.jdbc.extract: OFF
```

Rules:
- Local data must be synthetic/anonymized.
- Never use production database snapshots containing PII on developer machines without approval and safeguards.
- Never enable TRACE bind logging in production for "temporary debugging" without an expiry, owner, and change record.
- After investigating, disable the configuration and verify no other logger/appender/agent is capturing parameter values.

The `show-sql` property writes SQL directly to the console and bypasses normal logging framework routing. Production should keep it `false` and manage SQL diagnostics through controlled logging configuration.

## 6. Masking at the telemetry source

### 6.1. Why appender masking can be too late

Once a bind value has been formatted into a log event, it may already pass through:
- Async logging queues.
- File appenders.
- Console/stdout collectors.
- APM agents or sidecars.
- Remote log forwarders.

Masking in just one appender does not guarantee other sinks do not receive raw values. Once an event is serialized or sent over the network, another appender may already store the real data.

Prefer preventing values from entering telemetry at the source. If capture cannot be turned off, use instrumentation capable of redacting before events/spans are published; test all exporters and sinks.

### 6.2. JDBC proxies and DataSource instrumentation

Some JDBC proxy libraries can log SQL with bind values to show the effective query. DataSource proxies, P6Spy, or agent instrumentation can be configured to:
- Omit parameter values.
- Replace values with placeholders.
- Use custom formatters/filters.
- Log only normalized SQL.
- Exclude sensitive queries/tables/fields.

Exact property names and hooks depend on library versions. Do not guess configuration from examples for a different version. Check docs for your version and validate with sentinel-value tests.

If a library only redacts after building a log message containing raw SQL, evaluate where that happens and which other sinks see it. A better solution is disabling parameter capture or using a formatter that never serializes sensitive values.

## 7. Redaction, masking, and tokenization

These three data transformations are not identical:

| Approach | Example | Characteristics |
| --- | --- | --- |
| Redaction | `[REDACTED]` | Completely removes the value |
| Masking | `****1234` | Preserves part of the value per policy |
| Tokenization | `tok_8fa...` | Replaces with a reference token; requires a token management system |

### 7.1. Redaction

This is the safe default for passwords, tokens, CVVs, and data not needed for diagnosis:

```text
bind[1] type=VARCHAR value=[REDACTED]
bind[2] type=INTEGER value=42
```

If you do not need to know whether parameter 1 is an email, omit the value or replace it with a generic placeholder.

### 7.2. Partial masking

Use only when the remaining portion serves an approved diagnostic purpose. For example, a phone number might keep only the last two digits; an email might strip the local part. However, partially masked data can still be linkable to users, so it still requires policy, access controls, and retention rules.

Do not rely on a generic regex across full SQL text as a foolproof solution. SQL has many dialects, quoting rules, escapes, and binary values; regexes easily miss edge cases or break syntax.

### 7.3. Hashing/tokenization

Hashing does not automatically anonymize data. Unsalted hashes of emails/phone numbers are vulnerable to dictionary attacks. When correlation on stable values is needed, use keyed HMAC with securely managed keys and dedicated policy; never log the key or raw value. Tokenization suits controlled mapping requirements, though the token store must also be protected.

For most database logs, `[REDACTED]` placeholders or omitting values entirely is simpler and safer.

## 8. Allowlist instead of blocklist

A dangerous pattern is logging all parameters and trying to block a few sensitive field names like `password`, `email`, and `phone`. Schema changes or new queries can introduce different column names and leak data.

Prefer an allowlist:
- Log only approved metadata types.
- Log only parameter values explicitly classified as non-sensitive.
- Redact unknown parameters by default.
- Never infer safety solely from column names.

| Parameter classification | Log value? | Output |
| --- | --- | --- |
| Secret/credential | No | `[REDACTED]` |
| Personal data | No, unless specifically approved | `[REDACTED]` |
| Business identifier | Per policy | Redacted/tokenized |
| Safe bounded enum | Possible | `ACTIVE` |
| Unknown/unclassified | No | `[REDACTED]` |

Even enums/statuses should be checked to ensure they cannot expose sensitive account or business states.

## 9. Never put parameters into metrics or span attributes

Metrics require low cardinality. Never put bind values into tags:

```java
// Unsafe: value could be an email or unique ID.
Counter.builder("db.query.executions")
        .tag("customerEmail", email)
        .register(registry)
        .increment();
```

Use bounded tags:

```java
Counter.builder("db.query.executions")
        .tag("operation", "customer.lookup")
        .tag("outcome", "success")
        .register(registry)
        .increment();
```

With tracing, span attributes/events can also be exported and retained long term. Do not attach raw SQL parameters to span attributes just because the tracing backend supports search. Keep:
- DB system/operation.
- Policy-approved normalized query summaries or fingerprints.
- Duration, rows/counts when safe.
- Sanitized error categories/codes.
- Service/resource attributes and trace context.

Do not store full SQL text if it contains literal values. Prepared statement templates are usually safer, though identifiers/table names should still be reviewed to ensure they do not leak architecture or private data.

## 10. Exceptions and database error messages

Driver/database exceptions can embed SQL statements, constraint values, table names, or portions of input data. Masking bind loggers alone is therefore insufficient.

Avoid:

```java
catch (DataAccessException ex) {
    log.error("Database failure for customer {}", email, ex);
    throw ex;
}
```

Better:

```java
catch (DataAccessException ex) {
    log.error("Customer lookup failed; operation=customer.lookup", ex);
    throw ex;
}
```

Even so, the throwable message/cause can still carry raw SQL or parameter values from the driver. When error messages may contain sensitive data:
- Use sanitized error codes/classes and operation context.
- Never log throwables directly to sinks lacking proper protection.
- Log sanitized exception summaries at boundaries and restrict full diagnostics to access-controlled systems if permitted by policy.
- Avoid passing raw exception messages into API responses.

Do not mechanically strip cause chains everywhere: preserve diagnostic capability in properly secured channels. Just never assume stack traces are automatically safe.

## 11. Testing masking

A test checking only that a logger does not throw an exception is insufficient. Use recognizable sentinel values to detect leaks across every sink.

Example sentinels:
- Email: `sensitive-user-987@example.test`
- Token: `SECRET_SENTINEL_7F3A`
- Phone: `+84987654321`

Tests:
1. Execute queries containing sentinel values through ORM/JDBC.
2. Enable production-like logging configuration.
3. Capture output from console/file/test appenders.
4. Verify raw sentinels do not appear.
5. Verify SQL template, operation name, duration, and error class remain observable.
6. Trigger an SQL constraint exception to check messages/causes do not leak sentinels.
7. Inspect trace span attributes/events and exporter payloads.
8. Inspect JDBC proxy/P6Spy/APM agent outputs if present in deployment.
9. Run tests across profiles (local, test, staging, production).
10. Confirm masking does not apply only to one appender while another sink receives raw values.

Example assertions:

```java
assertThat(capturedLogs)
        .doesNotContain("sensitive-user-987@example.test")
        .doesNotContain("SECRET_SENTINEL_7F3A")
        .doesNotContain("+84987654321")
        .contains("[REDACTED]");
```

Integration tests should collect outputs across all relevant logging appenders and telemetry exporters, not just a mocked logger.

## 12. Operations and incident response

- Set safe defaults in base config and inspect effective config per environment.
- Restrict access to database logs, traces, APM, and support bundles.
- Use the shortest retention meeting operational needs.
- Never copy raw production logs into tickets/chat or onto developer machines.
- Use synthetic/anonymized data when reproducing bugs.
- Manage logging/agent configuration changes via review and audit trails.
- When enabling temporary diagnostics, record an owner, scope, expiry, data classification, and storage location.
- After investigating, disable capture and verify with sentinel tests.
- If raw sensitive values are discovered in telemetry, handle as data exposure: restrict access, identify affected sinks/retention/replicas, follow incident procedures, and rotate credentials if needed.

## 13. Troubleshooting

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Hibernate SQL has no values yet logs still leak | JDBC proxy or APM agent captures bind parameters | Inspect all instrumentation and exporters |
| Bind logger disabled yet parameters still appear | Different logger category/version or separate proxy | Verify Hibernate version and JDBC proxy config |
| One log redacted yet another file has raw values | Masking attached to only one appender | Redact/disable at source; check all sinks |
| Exception messages expose SQL/values | Driver or ORM puts statements in cause | Sanitize error summaries and restrict throwable sinks |
| Duplicate SQL logs | Hibernate logger and JDBC proxy both logging | Pick a single SQL logging source |
| Local profile exposes production data | Unanonymized production snapshot used locally | Use only synthetic/anonymized data |
| Trace backend contains parameters | Span attributes/events record raw SQL or payloads | Disable capture or sanitize before export |
| Metric cardinality spikes | Parameter values used as tags | Remove dynamic tags; use bounded operation/outcome |
| Regex masking misses values | Different SQL dialects/escaping/binary formats | Use source-level redaction or disable capture |
| Hashes still leak underlying values | Unsalted hashes vulnerable to dictionary guessing | Do not hash PII; use keyed HMAC/tokenization if correlation needed |
| Masking breaks debugging | Over-redacted safe metadata | Keep SQL templates, parameter index/type, query fingerprints, and timings |
| Production accidentally enables TRACE | Profile/environment override | Inspect effective config and deployment policy |

## 14. Production checklist

- [ ] Bind parameter values are not logged by default in production.
- [ ] Hibernate bind/extract loggers are disabled for the exact version in use.
- [ ] JDBC proxies, P6Spy, and APM agents are audited separately.
- [ ] SQL templates are parameterized; never concatenate raw values into SQL/log messages.
- [ ] Unknown data is redacted by default.
- [ ] Allowlists cover only metadata/values classified as safe.
- [ ] Exception messages and stack traces are evaluated for PII/secrets.
- [ ] Logs and span attributes contain no raw bind values.
- [ ] Metrics use only low-cardinality tags.
- [ ] Masking happens before data reaches sinks that could store raw events.
- [ ] All appenders/exporters/sidecars are tested with sentinel values.
- [ ] Retention, access controls, and incident response are defined.
- [ ] Temporary diagnostics have an owner, scope, expiry, and review.
- [ ] After debugging, production config is verified back at safe defaults.

## 15. Self-study questions

1. How do SQL templates differ from bind parameter values?
2. Why do prepared statements not automatically guarantee parameter values stay out of logs?
3. Which logger categories does Hibernate 6 bind logging typically use?
4. Why is disabling one Hibernate logger insufficient when a JDBC proxy/APM agent is present?
5. How does redaction differ from masking and tokenization?
6. Why is an allowlist safer than a blocklist as schemas evolve?
7. Can unsalted email hashes still be reversed to reveal data?
8. Why can masking at the appender be too late?
9. How can exception messages/causes expose parameters?
10. Which metadata remains useful once bind values are redacted?
11. Why must bind values never go into metric tags or span attributes?
12. Which sinks must sentinel tests verify?

## References

- [Hibernate ORM 6 — Logging](https://docs.jboss.org/hibernate/orm/6.6/logging/logging.html)
- [Hibernate ORM 6 — User Guide](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Framework — Data Access](https://docs.spring.io/spring-framework/reference/data-access.html)
- [P6Spy — Documentation](https://p6spy.readthedocs.io/en/latest/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Database Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Database_Security_Cheat_Sheet.html)
- [OpenTelemetry — Database Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/db/)

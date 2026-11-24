# Never Log Passwords or Tokens

In a Spring Kafka system, logs are essential for investigating broker connection errors, tracking producers and consumers, analyzing latency, and resolving production incidents. However, logs can also become a leak vector for authentication data if the application writes passwords, access tokens, refresh tokens, or secret keys to log output.

The operational rule is **never write secrets to logs at any level**: `TRACE`, `DEBUG`, `INFO`, `WARN`, or `ERROR`. Secrets must not appear in log messages, parameters, stack traces, Kafka headers, message payloads, startup logs, configuration dumps, or deployment pipeline logs. When diagnostics are needed, record selective, safe operational context such as operation name, topic, partition, offset, consumer group, and non-sensitive correlation IDs.

## Why Must Passwords and Tokens Never Appear in Logs?

Passwords and tokens allow an individual or process to prove identity and execute authorized actions. Anyone obtaining a secret can use it to log in, call APIs, read or write Kafka data, or access other services depending on that credential's permission scope.

Logs are commonly copied and stored in many places: application hosts, container runtimes, centralized logging systems, SIEM platforms, monitoring tools, backups, and support systems. Far more teams have read access to logs than are allowed to read secrets. Logs may also be retained longer than a credential's intended lifetime. Therefore, a single log line accidentally containing a token creates a copy of the secret across multiple systems that is hard to purge completely.

Consequences can include:

- **Impersonation:** someone holding a valid token can send requests under the identity of the service or user owning the token.
- **Unauthorized data access:** a Kafka credential may allow reading topics, writing messages, or administering the cluster beyond intended boundaries.
- **Lateral movement:** reused or overly broad credentials can open access to other services.
- **Complex incident response:** secrets scattered across multiple log copies complicate scoping exposure and purging data.

The fact that logs are internal-only, inside a private network, or behind login authentication does not make logging secrets safe. Permission to read logs and permission to use credentials are two separate privileges; you should not grant credential usage rights to everyone who needs to inspect logs.

## Common Secrets in Spring Kafka Applications

Fields named `password` are not the only secrets. When operating Kafka, identify all data capable of authenticating or decrypting:

| Data | Example | Log Handling |
|---|---|---|
| SASL password | Password in `sasl.jaas.config` | Do not log value; do not log full JAAS string |
| Username or principal | Service account name | Classify per policy; if sensitive, use a substitute identifier |
| OAuth client secret | `client-secret` used to acquire tokens | Do not log value or config blocks containing it |
| Access token / bearer token | JWT or opaque token in `Authorization` | Do not log full tokens, partial tokens, or headers carrying tokens |
| Refresh token | Token used to mint new access tokens | Never log; protect like long-lived credentials |
| Private key | Private key used for TLS or signing | Do not log key material or dumps containing keys |
| Keystore / truststore password | `spring.kafka.ssl.key-store-password` | Do not log config values |
| API key or secret manager credential | Access key for external services | Do not log in application logs or deployment logs |

Properties such as `security.protocol` or `sasl.mechanism` are typically not secrets. They can be helpful when diagnosing configuration, though organizational data classification policies still apply. Do not infer that every value sitting next to a non-sensitive property is safe to log.

For example, configuration may contain SASL login details:

```properties
spring.kafka.properties.security.protocol=SASL_SSL
spring.kafka.properties.sasl.mechanism=PLAIN
spring.kafka.properties.sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";
```

In this configuration, `KAFKA_PASSWORD` and its resolved value are secrets. Do not log the raw `sasl.jaas.config` line, do not log the entire `KafkaProperties` object, and do not print the entire `Environment` to inspect configuration. Environment variable names may be noted if policy allows, but their values must remain confidential.

## Places Where Secrets Easily Leak into Logs

### Startup configuration logs

A dangerous debugging habit is printing the entire configuration object:

```java
// Unsafe: object may contain passwords or tokens.
log.debug("Kafka properties: {}", kafkaProperties);
```

Similarly, do not dump all environment variables, system properties, command-line arguments, or bean-bound configurations. Those sources can hold secrets injected from Kubernetes Secrets, environment variables, CI/CD, or secret managers.

Instead, log an allowlist of diagnostic fields that contain no credentials:

```java
log.info(
    "Kafka client configured: clientId={}, bootstrapServers={}, securityProtocol={}, saslMechanism={}",
    clientId,
    bootstrapServers,
    securityProtocol,
    saslMechanism
);
```

Include `bootstrapServers`, `clientId`, and similar fields in logs only when they are not classified as sensitive under internal policy. Never add usernames, passwords, JAAS configs, tokens, private keys, or unclassified config values to this log statement.

### Kafka message and header logs

Producer records and consumer records can carry business data, personal information, or credentials passed through headers. In particular, some applications place bearer tokens, API keys, or identity claims into headers for application-layer authentication.

Do not directly log entire `ProducerRecord`, `ConsumerRecord`, `Message<?>`, payloads, or header maps:

```java
// Unsafe: record may contain sensitive payloads and headers.
log.debug("Sending Kafka record: {}", record);

// Unsafe: headers may contain Authorization or API keys.
log.debug("Received headers: {}", record.headers());
```

If you need to trace message flow, select approved technical fields:

```java
log.info(
    "Kafka message received: topic={}, partition={}, offset={}, keyPresent={}",
    record.topic(),
    record.partition(),
    record.offset(),
    record.key() != null
);
```

This example logs no key values, payloads, or headers. If keys contain sensitive data, do not log keys; even when a key is not a secret, it may still contain customer IDs, emails, or business identifiers. Log only `keyPresent` when that suffices for diagnostics.

When tracing messages across multiple services, prefer standardized system-managed correlation IDs or trace IDs. Never use access tokens, session IDs, cookies, or existing secrets as correlation IDs.

### Exception and stack trace logs

Stack traces help locate failures, yet you cannot assume every exception is safe to log verbatim. Exception messages or causes can contain URLs with credentials, request bodies, headers, authentication configs, or externally controlled input data.

The following risks logging sensitive data embedded inside an exception:

```java
// Use only when verified that the exception and full cause chain contain no secrets.
log.error("Kafka operation failed", exception);
```

In code paths that may carry credentials, classify errors and log controlled details. Keep error codes, exception types, and safe technical context; do not concatenate raw requests, headers, configs, or auth material into log messages.

```java
try {
    kafkaTemplate.send(topic, payload).get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    log.error(
        "Kafka send interrupted: topic={}, errorType={}",
        topic,
        ex.getClass().getSimpleName()
    );
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    log.error(
        "Kafka send failed: topic={}, causeType={}",
        topic,
        cause == null ? "unknown" : cause.getClass().getSimpleName()
    );
}
```

This is a cautious pattern for cases where exceptions might carry sensitive data. In other flows, stack traces may still be logged once operations have verified that messages and cause chains expose no secrets and logging policy permits it. If stack traces are needed for investigation, apply verified filters or normalization before ingesting into log systems.

### Library loggers and DEBUG / TRACE levels

Spring Kafka and the Kafka client have their own loggers. Increasing log levels to `DEBUG` or `TRACE` can dramatically increase internal output. Depending on library version and execution path, logs may include configuration details, metadata, requests, or protocol-level data.

Do not enable broad DEBUG/TRACE logging in production just to chase an authentication error. Before raising log levels:

1. Specify the exact logger to observe, active duration, and responsible owner.
2. Inspect actual log output in a test environment using dummy data.
3. Confirm the logger prints no credentials, payloads, or sensitive headers.
4. Limit duration and scope; restore normal log levels immediately after gathering evidence.

Do not rely on an assumption that libraries always mask passwords or tokens automatically. Logging behavior varies across versions, configs, and failure types.

## Designing Safe Logs with an Allowlist

The most reliable approach is deciding upfront which fields are allowed in each log event. An allowlist approach reduces the risk of missing a newly added secret name or custom header in the application.

For Kafka operations, useful fields to consider include:

- Operation name: `publish`, `consume`, `retry`, `commit`, or `dead-letter`.
- Topic name, partition, and offset, if such metadata is not classified as sensitive.
- Consumer group or client ID approved for logging.
- Trace ID or correlation ID containing no credentials.
- Duration, retry count, outcome, and normalized error code.
- Exception type, if the class name leaks no sensitive details.

Fields to exclude from logs include passwords, tokens, authorization headers, cookies, API keys, private keys, JAAS contents, resolved secrets, entire config objects, unclassified payloads, and unapproved headers. Never log partial tokens "for easier identification"; a token fragment is still authentication material that could be abused or combined with other data.

A structured log event might look like:

```json
{
  "event": "kafka_consume_failed",
  "topic": "orders",
  "partition": 3,
  "offset": 18420,
  "consumerGroup": "order-projection",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "errorCode": "BROKER_UNAVAILABLE",
  "durationMs": 1200
}
```

This example illustrates operational metadata only. Topic names, consumer groups, and trace IDs must still comply with organizational classification, access control, and log retention policies. If a field could reveal customer identities, business workflows, or internal structure, reduce granularity or substitute controlled identifiers.

## Redaction and Log Filtering

Redaction is an additional safeguard when parts of a system must process inputs containing sensitive information. For example, a filter can strip `Authorization` or `Cookie` headers, or fields named `password`, `access_token`, `refresh_token`, and `client_secret` before emitting logs.

However, redaction based on field names or regular expressions can miss secrets if:

- A new field name is not on the known list.
- A secret sits inside nested strings, JSON, URLs, exception messages, or binary payloads.
- A token is passed in a custom header.
- Credential formats vary by provider or library.

Therefore, design logging flows not to receive secrets in the first place; treat redaction as defense-in-depth. If a shared filter is necessary, test it against diverse dummy inputs including mixed-case headers, nested JSON, URL strings, and chained exceptions. Never log raw data if the filter errors; safe behavior is dropping unprocessable fields or refusing to emit the log event containing them.

## Managing Secrets Outside Source Code and Logs

Secrets should be supplied to the application through an environment-appropriate secret management mechanism, such as a secret manager or secured Kubernetes Secrets. Never commit real secrets to Git, sample config files, Docker images, deployment scripts, shell commands saved to history, or CI/CD logs.

In configuration examples, use placeholders:

```yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: PLAIN
      sasl.jaas.config: ${KAFKA_SASL_JAAS_CONFIG}
```

The value of `KAFKA_SASL_JAAS_CONFIG` is provided from a secure environment when the application runs. Never print this variable to logs to prove it was loaded. You can verify configuration state by confirming beans or clients initialized cleanly, logging non-sensitive status codes, or running an access-restricted health check.

For OAuth, never log token requests, client secrets, access tokens, or refresh tokens. Log only high-level outcomes like `authentication_succeeded`, `authentication_failed`, normalized error codes, and processing time. For TLS, never log private keys or keystore passwords. If you need to identify the active certificate, log its public fingerprint or serial number per policy—never the private key.

## Protecting the Logging System

Keeping secrets out of logs is the primary control. The logging system itself still needs protection because operational metadata can reveal architecture, service names, topics, consumer groups, or user activity.

Operational measures should include:

- **Least privilege:** grant log read access strictly by role and job need; control production log query access separately.
- **Retention limits:** set retention to match investigative and legal requirements; avoid indefinite storage.
- **Protection in transit and at rest:** use encrypted connections and appropriate storage encryption controls.
- **Access auditing:** maintain audit logs for queries, downloads, and sharing of sensitive logs.
- **Copy control:** watch logs forwarded to SIEMs, alerting systems, tickets, chats, attachments, and backups.
- **Separation of duties:** people who read logs for operational support must not implicitly hold permissions to retrieve secrets from the secret manager.

Never paste log lines containing secrets into tickets, emails, screenshots, or support chats. Cross-team log sharing must also follow data classification policies.

## Verifying That the Application Does Not Log Secrets

Verification should inspect actual log output, because reading source code alone cannot catch every case where a library or exception logs data. Use a clearly marked dummy secret in a test environment, exercise startup, authentication, send, receive, retry, and error paths, and inspect collected logs.

Example verification approach:

1. Create dummy passwords and tokens like `TEST_ONLY_SECRET_7f31`.
2. Configure the test Kafka client with those dummy values.
3. Run the application with production log levels and one controlled check at DEBUG if needed.
4. Trigger both success and failure scenarios, including authentication failures and message send errors.
5. Search for the dummy secret marker across application logs, client logs, container logs, and pipeline logs.
6. Confirm logs still retain enough safe metadata to diagnose incidents.

In automated tests, use a log-capturing appender to assert that dummy secret strings do not appear in logged messages or throwables. Tests should cover both application loggers and relevant library logger configs. Use only dummy credentials in tests; never copy production passwords or tokens into test fixtures.

Beyond tests, review logging configuration after every Spring Kafka or Kafka client upgrade, authentication mechanism change, interceptor addition, header change, or observability integration. Such changes can introduce new log paths.

## When a Password or Token Is Found in Logs

Treat any secret that appeared in logs as potentially compromised, even without signs of unauthorized use. Response should begin by:

1. **Revoking or rotating the credential:** invalidate tokens, change passwords, or issue new credentials per the issuing system's procedures.
2. **Scoping copies:** locate copies that might contain the secret in centralized logs, containers, SIEMs, alerts, tickets, chats, attachments, and backups.
3. **Restricting access:** tighten read and sharing permissions on affected records during remediation.
4. **Purging data per procedure:** delete or scrub records and copies where supported by the platform, compliant with retention requirements and incident response procedures.
5. **Investigating usage:** inspect audit logs of Kafka, identity providers, API gateways, or credential issuers for anomalous activity.
6. **Fixing the source:** remove unsafe log statements, add allowlists or redaction, and add regression tests.

Deleting one log line on an application host is insufficient if logs were already forwarded or backed up. Likewise, merely masking the secret in log displays while leaving the old credential active is not enough. Revoking or rotating the credential is essential to block continued misuse of exposed data.

## Practical Rules When Writing Logs for Spring Kafka

Before adding a log statement, ask yourself:

- Could this value be used to authenticate, authorize, or decrypt?
- Could the printed object contain headers, payloads, configs, or nested exceptions?
- Can this value be replaced with approved metadata, error codes, or non-sensitive correlation IDs?
- Is this log statement safe to ship to centralized logging and share with operations teams?
- Would DEBUG/TRACE level expose extra data in production?

A good log line answers **what happened, where, and when** without revealing **credentials used to access the system**. In Spring Kafka operations, log authentication status and required metadata; keep passwords, tokens, private keys, and all secrets out of logs at every level.

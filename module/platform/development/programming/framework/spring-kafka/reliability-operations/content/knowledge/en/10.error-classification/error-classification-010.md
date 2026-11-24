# Errors caused by malicious data in Spring Kafka

In a Kafka system, input data can come from buggy producers, incompatible application versions, external integration systems, or a compromised source. An invalid record can cause a listener to throw exceptions, making the consumer re-read the same offset repeatedly, stalling the partition, or increasing load across the entire system. Data intentionally crafted to exploit consumer weaknesses can also trigger security vulnerabilities such as injection, sensitive data exposure, or excessive resource consumption.

In Spring Kafka's error classification chapter, **errors caused by malicious data** must be recognized as an input-error group that can recur on every read. Typical handling involves validating data, classifying unrecoverable errors, routing records to a dead-letter topic (DLT) or quarantine zone, recording sufficient details for investigation, and protecting consumers from unbounded processing.

A malicious or malformed record rarely turns valid on its own after a few retries. Therefore, retries should be reserved for transient errors; structural, data-type, or fixed business rule failures must follow a dedicated recovery flow.

## 1. What is malicious data in a Kafka stream?

Kafka brokers store records consisting of key, value, timestamp, and headers. Brokers do not fully understand the business semantics of payloads. Decoding, type conversion, validation, and business execution typically take place in the consumer.

A record can cause harm in many ways:

| Data group | Examples | Potential impact |
|---|---|---|
| Malformed payload | Truncated JSON, missing brackets, wrong encoding | Deserialization exception |
| Incompatible schema | Missing required fields, changed field types | Conversion or validation failure |
| Out-of-domain values | Negative amounts, invalid expiration dates, non-existent states | Business errors or corrupted data |
| Oversized payload | Strings, arrays, or blobs exceeding limits | High memory consumption, latency spikes, or exceeding broker/client limits |
| Deeply nested or complex data | Multi-level JSON/XML structures, excessive element counts | High CPU/memory usage, slow parsers |
| Untrusted headers | Spoofed type headers, tenant IDs, or routing headers | Wrong deserialization type or misrouting |
| Strings with dangerous content | Content concatenated into SQL, shell, logs, or HTML | Injection, log forging, or XSS in downstream systems |
| Source-supplied URLs or paths | Internal URLs, disallowed paths | SSRF or path traversal if used directly by the consumer |
| Sensitive data | Tokens, passwords, personal data | Data leaks via logs, DLT, or replay tools |

Not every bad record is an attack. An older producer may emit an outdated schema, or a buggy service may publish invalid data. Nonetheless, consumers must treat data from Kafka as untrusted input requiring validation, even when the topic is written only by internal producers.

## 2. Poison pills and why partitions can stall

A **poison pill** is a record that a consumer repeatedly fails to process successfully—for example, an undeserializable payload or a value that always violates validation. If a consumer retries the same record without recovery, the offset may fail to advance.

~~~text
Consumer poll()
      |
      v
Record offset 120
      |
      v
Deserialize / validate
      |
      +--> failure
              |
              v
        Error handler
              |
              +--> retry record 120
              |       |
              |       v
              |   still failing
              |       |
              |       +----> keep retrying
              |
              +--> retries exhausted
                      |
                      v
                 DLT / quarantine
                      |
                      v
              recovery succeeds
                      |
                      v
             commit offset per policy
                      |
                      v
               continue to next record
~~~

With blocking retries, a failing record can hold the partition until retries or recovery finish. This preserves ordering within the partition but can block subsequent records.

If the error stems from a static payload, additional retries will not alter the data. The consumer may burn CPU continuously, flood logs, and inflate consumer lag. When multiple partitions contain poison pills simultaneously, the entire consumer group can degrade significantly.

Distinguish poison pills from temporary dependency failures. A database losing connectivity for a few seconds can recover on retry. Syntactically invalid JSON will still fail when resending the same bytes.

## 3. Stages where consumers can encounter data errors

Data can fail before, during, or after the listener is invoked.

~~~text
Kafka record bytes
      |
      v
Key/value deserializer
      |
      +--> deserialization error
      |       |
      |       v
      |  ErrorHandlingDeserializer
      |
      v
Message conversion / type mapping
      |
      +--> conversion or method argument resolution error
      |
      v
Bean validation / domain validation
      |
      +--> invalid data
      |
      v
Business logic
      |
      +--> business rule or dependency error
      |
      v
Database / HTTP / downstream system
~~~

Different error layers require different handling:

- **Deserialization:** bytes cannot be converted into a key/value or object.
- **Message conversion:** an object may have deserialized, but cannot convert to the listener parameter type.
- **Validation:** the object is syntactically valid, yet violates constraints or business schemas.
- **Business rule:** the object is structurally valid, yet invalid given current business state.
- **Downstream failure:** the data is valid, yet the database or external service is failing.

Do not lump everything into a single generic exception and retry on the same schedule. Preserve the root cause and clearly separate recoverable from unrecoverable errors.

## 4. ErrorHandlingDeserializer for handling deserialization errors

An important issue is that standard deserializers can throw exceptions right inside the consumer poll. In that case, the listener has not been invoked yet, and try/catch logic inside the `@KafkaListener` method cannot handle that record.

Spring Kafka provides **ErrorHandlingDeserializer** to wrap the real deserializer. When the delegate deserializer fails, the wrapper stores exception details in record headers and allows the container error handler to process it.

Example JSON consumer configuration in Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.events.OrderCreated
        "[spring.json.trusted.packages]": com.example.events
~~~

In this example:

- ErrorHandlingDeserializer wraps deserializers for key and value.
- StringDeserializer handles keys.
- JsonDeserializer converts values to OrderCreated.
- Default type and trusted packages must match the application's actual models.
- Trusted packages should be restricted to packages of permitted event types.

If using application.properties:

~~~properties
spring.kafka.consumer.key-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
spring.kafka.consumer.properties[spring.deserializer.key.delegate.class]=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.properties[spring.deserializer.value.delegate.class]=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties[spring.json.value.default.type]=com.example.events.OrderCreated
spring.kafka.consumer.properties[spring.json.trusted.packages]=com.example.events
~~~

Property names and binding syntax should be verified against your Spring Boot/Spring Kafka versions. If the application handles multiple event types, use explicit type mappings or configure consumers per concrete contract instead of trusting arbitrary class names in headers.

### Handling deserialization-failed records

When deserialization fails, the listener may not receive a valid object. ErrorHandlingDeserializer places exception metadata in headers; error handlers and recoverers can use this information to route the record to a DLT.

Keep in mind:

- A failing record's value may not be a domain object; depending on the case, original data may be kept as raw bytes in metadata or headers.
- The DLT publisher needs serializers compatible with both deserialized payloads and raw `byte[]` payloads.
- Do not assume the listener can read a broken object or invoke getters on a null payload.
- During investigation, retain topic, partition, offset, timestamp, key, and exception type.
- Do not log full raw payloads if they might contain secrets or personal data.

## 5. Validating schemas and business rules

Successful deserialization only proves that bytes can convert into an object type. It does not prove the record is valid for business processing.

For example, an OrderCreated event might require:

- Non-empty eventId matching an accepted format.
- Valid orderId.
- Amount greater than or equal to 0 per business rules.
- Currency within the supported list.
- Reasonable createdAt format and time window.
- Presence of required fields.
- String lengths and collection sizes within bounds.

Jakarta Bean Validation can be used in a listener service:

~~~java
@Service
public class OrderEventValidator {

    private final Validator validator;

    public OrderEventValidator(Validator validator) {
        this.validator = validator;
    }

    public void validate(OrderCreated event) {
        Set<ConstraintViolation<OrderCreated>> violations =
                validator.validate(event);

        if (!violations.isEmpty()) {
            throw new InvalidEventException(
                    "OrderCreated violates event constraints"
            );
        }
    }
}
~~~

`InvalidEventException` represents a static data error and should not be retried repeatedly on the same payload. In production systems, you can record field names and validation error codes into quarantine metadata. Avoid placing sensitive field values in exception messages.

If using a schema registry with Avro, Protobuf, or JSON Schema, configure appropriate schema compatibility between producers and consumers. Schema compatibility controls structural evolution, but it does not replace business validation such as amounts, ownership, or order states.

### Distinguishing schema validation from business validation

| Check | Example | Error detected |
|---|---|---|
| Syntax | Valid JSON, properly encoded bytes | Unreadable payload |
| Schema | Fields have expected types and presence | Incompatible contract |
| Domain validation | Amount within limits, valid currency | Values outside business domain |
| Authorization | Event belongs to permitted tenant or source | Sender lacks authority to act |
| State transition | Order can transition from current state to new state | Event incompatible with system state |

An event with a valid schema can still be malicious data if it deliberately sends someone else's tenant ID, an internal URL, or an unauthorized state. Consumers must validate both source identity and action authorization.

## 6. Never trust producer type headers and control data

Spring Kafka's JsonDeserializer can use type information from headers to determine the target class. Headers sent by a producer can be spoofed if a producer has write access to the topic or an untrusted data source enters the pipeline.

Safety principles:

- Allow only event packages/classes explicitly defined by the application.
- Use explicit type mappings for supported event contracts.
- Do not use broad wildcard trusted packages in production unless necessary.
- Consider disabling type header usage and configuring a specific default type when a topic carries only one event type.
- Never deserialize native Java objects from untrusted sources.
- Never let payloads dictate arbitrary classes to instantiate.
- Version event contracts and govern schema evolution.

If a topic carries multiple event types, use a discriminator with an allowlist, mapping each value to a concrete domain type. Never use arbitrary class names from payloads as a type-selection mechanism.

## 7. Injection and data that can impact downstream systems

A payload may pass deserialization and structural validation yet still contain dangerous strings for target systems. Risk depends on how the consumer uses each field.

| Where data is used | Risk | Defensive measure |
|---|---|---|
| SQL queries | SQL injection | Prepared statements / parameterized queries |
| Shell/process invocation | Command injection | Avoid invoking shells; use parameterized APIs and allowlists |
| Logs | Log forging, secret exposure | Sanitize CR/LF, structured logging, never log secrets |
| HTML/UI | Cross-site scripting in dashboards or portals | Output encoding at rendering time |
| URL fetch | SSRF | Allowlist schemes/hosts, block internal addresses, control redirects and DNS |
| File paths | Path traversal | Normalize paths, confine to base directory, never trust filenames |
| Regex/parsers | ReDoS or parser overload | Cap input size/complexity, use safe parsers |
| Tenant/account routing | Cross-tenant access | Authorize using verified identity; never trust payload tenant IDs |

Database query example using parameter binding:

~~~java
jdbcTemplate.update(
        "update orders set status = ? where order_id = ?",
        event.status(),
        event.orderId()
);
~~~

Never concatenate strings from events into SQL queries:

~~~java
// Unsafe: data from the event is concatenated directly into the query.
String sql = "update orders set status = '" + event.status()
        + "' where order_id = '" + event.orderId() + "'";
statement.execute(sql);
~~~

If a consumer takes a URL from an event to call a service, validate host and scheme against an allowlist, block access to metadata endpoints or unauthorized internal networks, control redirects, and avoid relying on a single DNS lookup. Best practice is for events to carry only a business identifier while the application looks up trusted endpoints from configuration.

## 8. Limiting payload size and complexity

Oversized payloads or overly complex structures can make consumers burn excessive heap, CPU, and deserialization time. A source sending many heavy records can inflate consumer lag or trigger OutOfMemoryError.

Apply limits across multiple layers:

1. **Producer contract:** specify maximum payload size and element counts.
2. **Broker/topic:** configure appropriate message sizes and quotas per principal if needed.
3. **Consumer fetch:** configure fetch limits compatible with valid message sizes.
4. **Deserializer/parser:** cap nesting depth, token counts, string lengths, and processing time if supported by the library.
5. **Domain validation:** reject element counts, quantities, or field lengths exceeding business thresholds.
6. **Concurrency/backpressure:** cap the number of records/batches processed concurrently.

Broker and client limits must align. For example, a record valid for the broker yet larger than what the consumer can process can still destabilize the consumer. Conversely, arbitrarily lowering fetch limits can prevent the consumer from reading valid maximum-size messages.

Do not simply raise heap or message size limits to make errors vanish. Measure actual sizes, set limits by use case, and offload large payloads to access-controlled object storage while sending references over Kafka when appropriate.

## 9. Classifying errors: retry or not?

Errors from malicious or invalid data are usually **non-retryable** for the same payload. Infrastructure errors can be retried.

| Scenario | Typical classification | Action |
|---|---|---|
| Malformed JSON syntax | Non-retryable | DLT/quarantine and record metadata |
| Missing required field | Non-retryable | DLT; fix producer/contract |
| Value exceeds fixed limits | Non-retryable | DLT or reject per business rules |
| Type header not on allowlist | Non-retryable/security event | Quarantine, alert |
| Tenant or actor unauthorized | Non-retryable/security event | Reject, audit, alert |
| Temporary database disconnect | Retryable | Bounded backoff |
| Temporary broker/network error during DLT publish | Retryable | Retry recovery per policy; do not commit source record prematurely |
| Schema registry temporarily unreachable | Retryable | Cap retries and deadline |
| Consumer missing static configuration | Needs configuration fix | Alert; avoid infinite record retries |

Do not classify solely by exception class if the same class is used for both temporary and data errors. Use clear domain exceptions or stable error codes.

## 10. Configuring DefaultErrorHandler to route bad data to a DLT

For record listeners, DefaultErrorHandler can retry permitted errors and invoke a recoverer once retries are exhausted. For invalid data, mark domain exceptions as non-retryable to route straight to the DLT.

~~~java
@Configuration
public class KafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> dltTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(dltTemplate);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(1000L, 2L)
                );

        handler.addNotRetryableExceptions(
                InvalidEventException.class,
                UnauthorizedEventException.class
        );

        return handler;
    }
}
~~~

This example allows two retries with a one-second backoff for retryable errors. InvalidEventException and UnauthorizedEventException move to recovery without repetitive retries. Register the handler on the actual listener container factory.

Spring Kafka defines default non-retryable classifications for certain errors, including common deserialization/conversion errors. Check default classification for your version and explicitly add application domain exceptions.

### Selecting DLT topic and partition

By default, DeadLetterPublishingRecoverer commonly routes records to the source topic with a `.DLT` suffix, preserving the partition when appropriately configured. When preserving partition numbers, the DLT needs enough partitions to match the source topic. Destination resolvers can route different error categories to distinct quarantine topics.

~~~text
orders
   |
   +--> Invalid JSON ----------> orders.DLT
   |
   +--> Unauthorized event ----> security-quarantine
   |
   +--> Temporary error
             |
             +--> bounded retry
~~~

If DLT publishing fails, recovery is incomplete. Configure and test the recoverer's error behavior so the container does not commit the source offset while the record has not been safely persisted to the DLT. Monitor DLT publish results, exceptions, and recovery failure counts.

### Serializers for the DLT

A DLT can receive records deserialized into objects or records that failed deserialization. For deserialization failures, original data may be held as `byte[]`. Consequently, the DLT producer needs serializers capable of handling corresponding payload types, such as `byte[]` and domain objects, or separate templates per type. Never assume a single-object JsonSerializer will always handle raw bytes cleanly.

Also preserve error metadata in headers, while controlling header size and contents. Avoid stuffing huge stack traces or secrets into headers arbitrarily.

## 11. DLTs and quarantine zones must be operated safely

A DLT is not a trash bin where every bad record is dumped and forgotten. It is a staging area for data requiring investigation or recovery.

An operational procedure should include:

- **Retention:** storage duration matching investigation timelines and legal requirements.
- **Access control:** only authorized services/operators may read and replay.
- **Encryption:** protect data at rest and in transit.
- **Monitoring:** alert when the DLT grows rapidly or receives security-violation records.
- **Metadata:** store source topic, partition, offset, timestamp, exception class, error code, and event ID.
- **Replay approval:** verify and fix the root cause before replaying.
- **Idempotency:** consumers receiving replayed events must tolerate replays.
- **Audit:** record who viewed, edited, or replayed records when data is sensitive.

If records contain tokens, passwords, personal data, or secrets, the DLT may store sensitive data longer than the main topic. Restrict access, avoid logging raw payloads, and enforce appropriate retention/deletion policies.

Never automatically replay all records from a DLT back into the original topic. An invalid record can turn into a poison pill again; an unauthorized event can re-trigger a forbidden action.

## 12. Protecting logs and diagnostic information

When logging errors, do not log raw payloads or full headers by default. Malicious data can contain control characters, newlines, personal data, or secrets.

Log structured fields instead:

~~~text
event_id=evt-123
topic=orders
partition=2
offset=12045
error_code=INVALID_ORDER_AMOUNT
exception=InvalidEventException
action=QUARANTINE
~~~

Principles:

- Sanitize CR/LF and control characters if your log sink does not handle them automatically.
- Cap log field lengths.
- Never log tokens, passwords, authorization headers, or unnecessary personal data.
- Log event ID and Kafka coordinates for record traceability.
- Record exception class and error code; include stack traces only as needed.
- Separate security event logs from business logs if operational workflows require it.

Never use record data as logger names, filenames, or unbounded-cardinality metric labels/tags. A malicious producer can generate countless unique event IDs and overwhelm your monitoring system.

## 13. Schema evolution and event contracts

A substantial share of data errors arises from producers and consumers drifting out of version sync. For example, a producer adds a required field unknown to older consumers, or changes a field type from numeric to string.

To reduce errors:

- Version event contracts.
- Define required, optional, and default fields explicitly.
- Choose schema compatibility policies matching producer/consumer deployment practices.
- Add fields in backward/forward-compatible ways when possible.
- Never change a field's meaning while keeping the same name.
- Test new producers against old consumers and vice versa.
- Maintain a deprecation and removal process for fields.
- Attach schema version or event type under a governed contract.

A schema registry governs schemas and compatibility, but does not verify actor permissions, tenant ownership, or business state validity. Those checks remain the consumer/domain layer's responsibility.

## 14. Controlling sending sources and topic access

Malicious data can originate from a principal authorized to write to a topic that has been compromised or misconfigured. Using TLS or SASL alone does not make payloads trustworthy.

Defensive measures:

- Grant least-privilege ACLs: producers write only to required topics.
- Separate principals across producers, consumers, operators, and replay services.
- Use TLS to protect data in transit.
- Use SASL or appropriate authentication to verify principals.
- Apply quotas and send-rate limits per principal/topic if needed.
- Monitor ACL changes, credentials, and abnormal publishing sources.
- Never grant all services write access to all topics.
- Authorize event actions in the domain service; never treat Kafka ACLs as authorization for individual business actions.

If an event carries a tenant ID or actor ID, do not trust that value merely because it is in the payload. Verify that it matches the authenticated principal, signature, or trusted source per your security architecture.

## 15. Batch listeners and malicious data

With batch listeners, a single poll can return multiple records. One malicious record can fail the entire callback if the listener does not identify the failing record's position.

When the failing index is known, throw BatchListenerFailedException so the error handler targets the exact record:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-batch",
        containerFactory = "batchListenerFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int index = 0; index < records.size(); index++) {
        try {
            orderValidator.validate(records.get(index).value());
            orderService.process(records.get(index).value());
        }
        catch (InvalidEventException ex) {
            throw new BatchListenerFailedException(
                    "Invalid event in batch",
                    ex,
                    index
            );
        }
    }
}
~~~

If the listener fails to identify the failing record, the error handler may have to retry the whole batch or apply recovery to more records than necessary. Previously processed valid records may be reprocessed. Design batches for idempotency and verify error handler behavior for your Spring Kafka version.

If many records fail together due to a schema change, consider pausing/stopping the consumer in a controlled manner and alerting rather than letting every partition dump records into the DLT without an action plan.

## 16. Backpressure and protecting consumers from overload data

A source sending oversized records or excessive rates can overwhelm consumers. Excessive retries and logging amplify the load.

Measures:

- Cap payload sizes, array lengths, string lengths, and nesting depths.
- Cap records per poll/batch according to memory and processing budgets.
- Cap concurrency based on CPU, heap, and downstream capacity.
- Pause/resume or throttle intake when downstream systems overload.
- Apply quotas/rate limits at producers or gateways.
- Set deadlines for validation and downstream calls.
- Use bounded executors/queues instead of unbounded queues.
- Monitor heap, GC pauses, listener latency, and consumer lag.
- Alert when a single error code spikes sharply.

If a listener spends too long on one record, the consumer can exceed max.poll.interval.ms and trigger a rebalance. Raising the poll interval helps legitimate long workloads in some cases, yet cannot fix parsers burning unbounded CPU or payloads designed to exhaust memory.

## 17. Common operational scenarios

### Invalid JSON prevents the listener from being invoked

Check whether the consumer uses ErrorHandlingDeserializer. If using JsonDeserializer directly, exceptions can occur inside poll before the listener runs. Wrap the delegate deserializer with ErrorHandlingDeserializer so the container error handler can process errors.

### Same offset retried continuously

Inspect the root exception and DefaultErrorHandler classification. If the error stems from a static payload, mark it non-retryable and route to DLT/quarantine. Confirm recovery succeeds before the source offset commits.

### DLT publish fails

Check brokers, ACLs, serializers, topic existence, partition counts, and send results. Never mark a source record recovered unless the DLT record was durably saved. Set dedicated alerts for DLT publish failures.

### Oversized payload exhausts consumer memory

Measure record sizes and heap usage. Enforce limits at producer, broker, and consumer; consider storing large files/objects in object storage and passing access-controlled references via Kafka.

### Consumer parses JSON but data causes SQL errors

Check validation and query construction. Use parameterized queries, never string concatenation from payloads. Classify data errors as non-retryable and retain metadata needed to fix the producer/contract.

### DLT contains sensitive data

Restrict ACLs, encryption, retention, and replay permissions. Never log raw payloads or headers. Enforce data deletion procedures per retention policy.

### One tenant sends events belonging to another tenant

Never trust tenant IDs inside payloads. Verify source identity and actor/tenant permissions before executing side effects. Log a security event with event ID and Kafka coordinates without putting sensitive data in logs.

## 18. Monitoring data errors and alerting

Signals to observe:

| Metric/signal | Meaning |
|---|---|
| Deserialization failure count | Records that failed decoding |
| Validation failure count | Records violating contract/domain rules |
| Non-retryable exception count | Errors classified as non-retryable |
| DLT publish rate | Rate at which records route to DLT |
| DLT backlog/oldest age | Failed records lingering unaddressed |
| Retry count by error class | Distinguishes temporary vs. static errors |
| Consumer lag | Partition slowed down or blocked by poison pills |
| Listener processing latency | Detects payloads causing slow processing |
| Record size distribution | Detects abnormal payloads |
| Heap/GC/CPU | Detects resource pressure |
| Security rejection count | Events rejected due to invalid source/actor/tenant |

Avoid using event ID, raw key, or arbitrary tenant ID as metric labels if cardinality can grow unboundedly. Use error code, topic, consumer group, and bounded-value dimensions.

Useful alerts:

- Deserialization failures spike right after a producer deployment.
- One partition shows growing lag while others remain normal.
- DLT publish fails.
- A principal sends records exceeding normal size or frequency.
- Validation failure rate crosses threshold.
- Consumer heap/GC spikes alongside payload size.
- Security rejections rise or many events arrive from unauthorized tenants.

## 19. Handling procedure for a malicious record

When detecting a failing record, follow this workflow:

1. **Locate the record:** topic, partition, offset, timestamp, key, and event ID.
2. **Classify the error:** deserialization, conversion, schema, domain validation, authorization, or downstream.
3. **Decide on retry:** retry only if the error can change over time and stays within deadline.
4. **Quarantine:** route non-retryable records to a DLT or isolation topic.
5. **Protect data:** keep raw payloads out of logs and enforce DLT access controls.
6. **Investigate source:** identify producer version, principal, schema version, and deployment history.
7. **Remediate:** fix producer/contract or update data through an approved workflow.
8. **Controlled replay:** revalidate records, preserve event IDs, and ensure consumer idempotency.
9. **Post-recovery monitoring:** check whether lag, DLT backlog, and error rates drop.

Never manually advance offsets to skip a record without a business decision and audit trail. Skipping can lose a critical event and prevent downstream systems from reconstructing state.

## 20. Checklist for protecting Spring Kafka consumers

- Consumers use ErrorHandlingDeserializer when deserialization errors must be handled by the container error handler.
- Delegate deserializers support only permitted data types and schemas.
- Trusted packages/type mappings are tightly restricted.
- Native Java objects are never deserialized from untrusted sources.
- Schema contracts include versioning and compatibility policies.
- Validation checks syntax, schema, domain rules, and authorization.
- Static data errors are classified as non-retryable.
- Retries have finite attempts, backoff, and deadlines.
- DLTs/quarantines are protected with ACLs, encryption, and suitable retention.
- DLT serializers support both valid payloads and raw bytes from failed deserialization.
- Failed recovery publishing never advances source offsets as if persisted.
- SQL uses parameterized queries; URL/path/shell/log inputs are handled safely.
- Payload sizes, string lengths, collection sizes, and nesting depths are capped.
- Raw payloads, secrets, and sensitive headers are not logged.
- Consumers are idempotent to tolerate redeliveries and replays.
- Metrics exist for deserialization/validation failures, DLT, lag, payload sizes, and resources.
- DLT replays have verification, authorization, and audit processes.
- Malformed records, old schemas, oversized payloads, and validation failures are covered in tests.

Malicious data must be treated as a repeatable input error that can also pose security risks. Spring Kafka provides ErrorHandlingDeserializer, error handlers, and DLTs to move failing records out of the main stream. Applications must add schema/domain validation, resource limits, authorization, idempotency, and quarantine/replay workflows so consumers keep progressing while preserving investigation and recovery capabilities.

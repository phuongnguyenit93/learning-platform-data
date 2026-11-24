# Unknown Fields and Missing Fields

In Spring Kafka systems, producers and consumers are usually deployed independently and are not necessarily on the same version. A producer may add a new field to JSON before older consumers are upgraded; conversely, a new consumer may expect a field that older records already in Kafka never contained. These two scenarios lead to the concepts of **unknown fields** and **missing fields** in deserialization and schema evolution.

- **Unknown field:** the payload contains a field that the consumer's data type or schema does not know about.
- **Missing field:** the payload omits a field that the consumer's data type or schema expects to be present.

Both relate to version compatibility, yet their handling differs. Unknown fields can often be ignored if the consumer does not need them. Missing fields must be evaluated by business meaning: defaults can be used when a field is optional, whereas records must be rejected if required data is missing. This lesson focuses on Spring Kafka with JSON/Jackson, while comparing related rules in Avro and Protobuf.

## 1. Example of an event structure change

Suppose topic `orders.created` holds version 1 events:

~~~json
{
  "eventId": "evt-001",
  "orderId": "ord-100",
  "amount": 125000
}
~~~

After the producer upgrades to version 2, events include a `currency` field:

~~~json
{
  "eventId": "evt-002",
  "orderId": "ord-101",
  "amount": 125000,
  "currency": "VND"
}
~~~

Problems arise in two directions:

1. **Consumer v1 reads event v2:** `currency` is an unknown field because model v1 does not declare it.
2. **Consumer v2 reads event v1:** `currency` is a missing field because older JSON does not contain it.

If `currency` is display-only, the old consumer can ignore it. If the new consumer uses `currency` to compute amounts, silently defaulting every old event to `VND` may be wrong when historical data includes multiple currencies. Fallback decisions must rest on the event contract, not merely on preventing code from throwing exceptions.

## 2. Distinguishing unknown, missing, null, and type mismatch

Four cases are frequently conflated:

| Scenario | Input JSON | Expected model | Cause |
|---|---|---|---|
| Unknown field | Has `couponCode` | Model lacks `couponCode` | Producer sends new data |
| Missing field | Lacks `currency` | Model has `currency` | Old producer or omitted field |
| Explicit null | `"currency": null` | Model has `currency` | Producer explicitly sends null |
| Type mismatch | `"amount": "abc"` | Model expects number | Data cannot convert to expected type |

Missing differs from explicit null: omitting a field means the field is absent; sending `null` means the field is present with a JSON null value. For many Java types, Jackson maps both to `null`, yet business requirements may still differ.

Other causes to distinguish:

- **Field renamed:** producer sends `customerId` while consumer still reads `buyerId`.
- **Field type changed:** integer becomes an object or string.
- **New enum value:** producer sends `SHIPPED_BACK` not yet declared in consumer's enum.
- **Nested fields:** `address` object gains a field unknown to the nested DTO.
- **Payload is not valid JSON:** syntax error, encoding error, or truncated data.

Do not assume every deserialization error is an unknown/missing field. Diagnosis must examine the exception type and actual payload.

## 3. How does Jackson handle unknown fields?

Jackson uses `ObjectMapper` to map JSON into Java classes or records. Depending on configuration, unknown fields can either be ignored or fail deserialization.

Model v1:

~~~java
public record OrderCreatedV1(
        String eventId,
        String orderId,
        BigDecimal amount) {
}
~~~

If JSON also contains `currency`, and the mapper enables `FAIL_ON_UNKNOWN_PROPERTIES`, Jackson may throw `UnrecognizedPropertyException`.

Strict configuration example:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();

OrderCreatedV1 event = strictMapper.readValue(
        jsonWithCurrency,
        OrderCreatedV1.class
);
~~~

Conversely, unknown fields can be permitted:

~~~java
ObjectMapper tolerantMapper = JsonMapper.builder()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();
~~~

Then the undeclared `currency` field is skipped during mapping. `OrderCreatedV1` receives `eventId`, `orderId`, and `amount` without `currency`.

**Default note:** a plain Jackson `ObjectMapper` has different defaults than mappers preconfigured by Spring Boot or Spring Kafka. Many Spring Boot configurations and Spring Kafka's enhanced mapper disable `FAIL_ON_UNKNOWN_PROPERTIES`. Do not guess which mode is active; inspect the `ObjectMapper` `JsonDeserializer` actually uses.

## 4. Ignoring unknown fields at the DTO level

If only one DTO should accept new fields, use `@JsonIgnoreProperties(ignoreUnknown = true)`:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderCreatedV1(
        String eventId,
        String orderId,
        BigDecimal amount) {
}
~~~

This option is useful when keeping the mapper strict for most payloads while letting a specific event evolve incrementally.

There are three main decision levels:

| Config location | Scope | Pros | Risks |
|---|---|---|---|
| Shared `ObjectMapper` | Many DTOs handled by mapper | Consistent, easy to roll out | Masks field typos across many events |
| `@JsonIgnoreProperties` | Specific DTO/class | Policy aligned per event contract | Can miss nested DTOs needing separate config |
| Schema/validator checks | By schema or business rule | Tight control over structural errors | Requires additional schema and versioning workflow |

If a consumer acts as an intermediary reading and re-emitting records, ignoring unknown fields can **drop information** when serializing the new object. For instance, a service receives `currency` whose DTO does not declare it; when that service re-emits the event from DTO v1, `currency` vanishes. Do not use `ignoreUnknown` as a payload-preservation strategy.

If unknown fields must be preserved, consider storing the raw payload, an extension map via `@JsonAnySetter`, or an appropriate schema-aware forwarding mechanism.

## 5. Missing fields in Java DTOs and records

With ordinary DTOs, Jackson does not automatically treat a missing property as an error. For reference fields like `String` or `BigDecimal`, an absent value normally becomes `null`. For Java primitives, defaults are typically `0`, `false`, or another default depending on initialization and mapper configuration.

Example:

~~~java
public record OrderCreatedV2(
        String eventId,
        String orderId,
        BigDecimal amount,
        String currency) {
}
~~~

Reading v1 JSON without `currency` produces:

~~~text
OrderCreatedV2[
  eventId=evt-001,
  orderId=ord-100,
  amount=125000,
  currency=null
]
~~~

If the listener assumes `currency` is always non-null:

~~~java
String normalized = event.currency().toUpperCase();
~~~

the program can hit a `NullPointerException` **after** deserialization. Here, the issue is validation or business logic rather than a JSON parser bug.

Primitive fields are especially treacherous:

~~~java
public record InventoryAdjusted(
        String itemId,
        int quantity,
        boolean confirmed) {
}
~~~

When `quantity` or `confirmed` is missing, `0` or `false` can be populated without any error. The consumer cannot tell "producer sent quantity zero" apart from "producer omitted the field", unless using nullable types, creator validation, or schema rules.

## 6. Should explicit null be handled differently from missing?

Example:

~~~json
{"orderId":"ord-100"}
~~~

and:

~~~json
{"orderId":"ord-100","currency":null}
~~~

The two payloads carry different meanings if the contract forbids omitting `currency` while allowing explicit null to clear a value, or vice versa.

Strategies:

- Truly optional field: allow both absent and null, using explicit fallback logic.
- Required field: reject both absent and null.
- Partial-update field (patch semantics): absent means "unchanged", null means "clear value"; requires data types or parsers that preserve this distinction.
- Nullable but non-omissible field: check presence in JSON or schema before binding.

Do not use `Optional<T>` in every DTO merely to avoid nulls. With Jackson and supporting modules, `Optional` mapping depends on configuration; more importantly, the event contract must define what field absence means.

## 7. Requiring fields via creator properties

You can use `@JsonCreator` and `@JsonProperty(required = true)` to specify required constructor/creator parameters:

~~~java
public final class PaymentRequested {

    private final String paymentId;
    private final BigDecimal amount;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public PaymentRequested(
            @JsonProperty(value = "paymentId", required = true)
            String paymentId,
            @JsonProperty(value = "amount", required = true)
            BigDecimal amount) {

        this.paymentId = Objects.requireNonNull(
                paymentId, "paymentId is required");
        this.amount = Objects.requireNonNull(
                amount, "amount is required");
    }

    public String getPaymentId() {
        return paymentId;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
~~~

In creator-based deserialization, `required = true` causes Jackson to reject an **absent** parameter. However, `required` is not a general validator across every Java field or setter. Also, "required" and "non-null" are not identical: the constructor above uses `requireNonNull` to enforce value presence.

Jackson features to know:

- `FAIL_ON_MISSING_CREATOR_PROPERTIES`: rejects missing creator properties per mapper policy, even without `required`.
- `FAIL_ON_NULL_CREATOR_PROPERTIES`: rejects null values for creator properties.
- `FAIL_ON_NULL_FOR_PRIMITIVES`: controls mapping JSON null onto Java primitives.
- `FAIL_ON_UNKNOWN_PROPERTIES`: independent of the three options above; controls fields outside the model.

Strict mapper example for a payment contract:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .build();
~~~

Do not enable all of these globally just because one event needs strict mode. DTOs with optional fields or creator properties with valid defaults may be unexpectedly rejected. Match mappers, schemas, and DTOs to each contract.

## 8. Business validation after deserialization

Even when JSON is valid and Jackson builds the object, the event can still be business-invalid: negative amount, blank orderId, unsupported currency, or values inconsistent with order state.

Jakarta Bean Validation can be used:

~~~java
public record OrderCreated(
        @NotBlank String eventId,
        @NotBlank String orderId,
        @NotNull @DecimalMin("0.01") BigDecimal amount,
        @NotBlank String currency) {
}
~~~

When invoking the validator explicitly in a service:

~~~java
public void process(OrderCreated event) {
    Set<ConstraintViolation<OrderCreated>> violations =
            validator.validate(event);

    if (!violations.isEmpty()) {
        throw new InvalidOrderEventException(
                "Invalid order event: " + violations.size() + " violations");
    }

    orderService.handle(event);
}
~~~

The snippet assumes `validator` is `jakarta.validation.Validator` and `InvalidOrderEventException` is application-defined. Avoid logging personal data details from violation messages.

Spring Kafka listeners can integrate validation via `@Valid` or Kafka listener validators depending on configuration/version, though do not assume annotations work automatically across every listener type and message converter. Here, explicit validation shows a clear boundary: JSON deserialized cleanly, and only then is business validity checked.

## 9. Choosing safe defaults for missing fields

A new field often needs a default value so new consumers can read older records still stored in Kafka.

Example where version 2 adds `priority`:

~~~json
{
  "eventId": "evt-003",
  "orderId": "ord-102",
  "amount": 99000,
  "priority": "NORMAL"
}
~~~

If the contract specifies all historical orders had `NORMAL` priority, consumer v2 can apply default `NORMAL` when the field is absent. This preserves historical data semantics.

By contrast, for `currency`, do not default to `VND` just because most orders use `VND` unless you can prove all historical records used `VND`. A wrong default causes miscalculated money without raising an exception—harder to catch than a clear deserialization error.

Decision checklist:

1. Is the new field required for business logic?
2. Can the true value for historical records be inferred?
3. Does the default alter money, permissions, or state?
4. How long do records remain in retention/backlog?
5. Is a version marker or historical data migration needed?
6. In what order must producers and consumers be deployed?

Defaults should express business domain rules, not act as a technical workaround to avoid `NullPointerException`.

## 10. Field renames and aliases

A common issue is a producer renaming `buyerId` to `customerId`. A new consumer reading older events misses `customerId`, even though the information exists in `buyerId`.

Jackson supports `@JsonAlias` to accept old names during deserialization:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        @JsonAlias("buyerId") String customerId,
        BigDecimal amount) {
}
~~~

The consumer can read both:

~~~json
{"eventId":"evt-1","orderId":"ord-1","buyerId":"cus-1","amount":100}
~~~

and:

~~~json
{"eventId":"evt-2","orderId":"ord-2","customerId":"cus-2","amount":200}
~~~

`@JsonAlias` applies primarily to **reading**; when serializing, the primary property name remains `customerId` unless configured otherwise. This matters if the app both consumes and republishes events: downstream producers may emit only the new name.

When both `buyerId` and `customerId` appear with conflicting values, establish an explicit policy; do not rely on JSON property order to pick a winner randomly.

## 11. Schema compatibility: backward and forward

Schema evolution has two directions:

- **Backward compatibility:** new consumers read data produced by old producers. Missing fields are the central case; new fields usually need defaults or to be optional.
- **Forward compatibility:** old consumers read data produced by new producers. Unknown fields are the central case; old consumers must be able to ignore or handle new values.
- **Full compatibility:** both directions satisfy compatibility rules.

This is an intuitive explanation for events; specific Schema Registry compatibility modes (`BACKWARD`, `FORWARD`, `FULL`, and transitive variants) carry their own schema-checking rules. You cannot declare an arbitrary JSON change compatible merely because Jackson ignores unknown fields.

Summary table:

| Change | Old consumer reads new producer | New consumer reads old producer | Condition |
|---|---|---|---|
| Add optional field | Possible if ignoring unknown | Possible if valid default/null exists | Define default |
| Add required field without default | Possible if ignoring unknown | Usually fails or lacks data | Needs migration/version |
| Remove field | Old consumer may lack field | New consumer can ignore old field | Verify contract |
| Rename field | Usually causes unknown and missing | Usually causes missing | Alias or versioning |
| Change field type | May fail type conversion | May fail type conversion | Needs schema conversion |
| Add enum value | Old consumer may not recognize | New consumer usually understands old values | Set intentional fallback |

In systems with long backlogs or frequent replays, new consumers must still read old records months after deployment. Compatibility applies beyond the rolling deployment window.

## 12. How Spring Kafka deserializes JSON

Common flow:

    Broker record bytes
             |
             v
       Kafka Consumer poll()
             |
             v
       JsonDeserializer
             |
       +-----+----------------+
       |                      |
       v                      v
    Succeeded             Exception
       |                      |
       v                      v
    OrderCreated        Pre-listener error
       |                      |
       v                      |
    @KafkaListener            |
       |                      |
       +--- validation --------+
                  |
                  v
        CommonErrorHandler / recovery

The two failures take different paths:

1. **Deserialization error:** invalid JSON syntax, unknown field in strict mode, type mismatch, missing required creator property. Exceptions can occur before the listener is invoked.
2. **Business validation error:** deserialization succeeded, yet the listener or validator finds a required business field missing or invalid.

If `JsonDeserializer` throws right inside `poll()`, error handling must be configured so the container recognizes the failed record and can continue. That is a core purpose of `ErrorHandlingDeserializer`.

## 13. Configuring ErrorHandlingDeserializer

Spring Kafka provides `ErrorHandlingDeserializer` to wrap the actual deserializer and write deserialization error details into headers for the container to process, rather than letting one structurally invalid record repeatedly break the poll loop.

YAML example with JSON values:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
        spring.json.use.type.headers: false
    listener:
      ack-mode: record
~~~

In this example:

- `ErrorHandlingDeserializer` wraps `JsonDeserializer`.
- `spring.json.value.default.type` defines the default payload type when not relying on type headers.
- `spring.json.trusted.packages` restricts trusted packages for type mapping.
- `spring.json.use.type.headers=false` fits topics with one known event type when avoiding producer type-header coupling.
- `enable-auto-commit=false` lets the container control offset commits according to `AckMode`.

`JsonDeserializer` properties may vary by version or programmatic bean setup. If a consumer uses a custom `ObjectMapper`, enabling strict mode for unknown fields must be configured directly on the mapper passed into `JsonDeserializer`; do not assume any random YAML property toggles `FAIL_ON_UNKNOWN_PROPERTIES`.

Never open `spring.json.trusted.packages=*` arbitrarily for events from untrusted sources. Trusted packages and unknown-field policies solve two different problems: restricting instantiable types vs. deciding whether to ignore unfamiliar JSON properties.

## 14. Configuring a strict ObjectMapper in ConsumerFactory

When JSON unknown fields should throw exceptions and route to a DLT, provide a dedicated `ObjectMapper` to `JsonDeserializer`:

~~~java
@Bean
ConsumerFactory<String, OrderCreated> orderConsumerFactory(
        KafkaProperties kafkaProperties) {

    ObjectMapper mapper = JsonMapper.builder()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    JsonDeserializer<OrderCreated> json =
            new JsonDeserializer<>(OrderCreated.class, mapper, false);

    ErrorHandlingDeserializer<OrderCreated> valueDeserializer =
            new ErrorHandlingDeserializer<>(json);

    return new DefaultKafkaConsumerFactory<>(
            kafkaProperties.buildConsumerProperties(),
            new StringDeserializer(),
            valueDeserializer
    );
}
~~~

This example targets Spring Kafka 3.x and Spring Boot versions with the matching `KafkaProperties.buildConsumerProperties()` API; signatures may change across versions. The `false` argument in `JsonDeserializer` indicates disabling type headers per that version's constructor. If the project defines a custom `ConsumerFactory`, attach that exact instance to the listener container factory.

When `JsonDeserializer` is instantiated programmatically in Spring Kafka, certain `spring.json.*` property-map settings may not apply as expected when mixing setter APIs and property-based config. Pick one consistent configuration style and verify behavior in integration tests.

Strict mappers fit events with tight contracts, yet can prevent old consumers from reading new events simply because producers added harmless fields. Coordinate strict policies with versioning plans.

## 15. DefaultErrorHandler and DLT for schema-failed records

With `ErrorHandlingDeserializer`, the Spring Kafka container handles deserialization failures and routes records to the recoverer/DLT after applying error handler policies.

~~~java
@Bean
CommonErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(
            InvalidOrderEventException.class
    );

    return handler;
}
~~~

For permanent structural errors (strict unknown field, missing required creator field, unconvertible type), retrying the exact same record repeatedly rarely helps. Classify errors properly and route to DLT promptly. `DefaultErrorHandler` includes default non-retryable exceptions depending on version; check actual exceptions and current policies before adding classifications.

When `ErrorHandlingDeserializer` fails to build a value, the recoverer may receive original `byte[]` or fallback data depending on error type and version. **The DLT producer must be able to serialize the actual runtime value type**; you cannot assume every failing record is `OrderCreated`. You may need `DelegatingByTypeSerializer` or a `KafkaTemplate` whose serializer handles both normal objects and raw bytes.

Do not commit source offsets as handled if DLT publishing actually failed. Recovery design must monitor send results, producer timeouts, and retry behavior when brokers/DLT topics are unavailable.

## 16. Example listener checking missing fields

A listener may allow optional fields while rejecting required ones:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service"
)
public void consume(OrderCreated event) {

    if (event.orderId() == null || event.orderId().isBlank()) {
        throw new InvalidOrderEventException(
                "Missing required orderId");
    }

    if (event.currency() == null || event.currency().isBlank()) {
        throw new InvalidOrderEventException(
                "Missing required currency");
    }

    billingService.createInvoice(event);
}
~~~

In this example, a JSON event missing `currency` still deserializes into `OrderCreated`, yet the listener intentionally rejects it before creating an invoice. The exception goes to `DefaultErrorHandler` to route to DLT per configured classification.

If the contract states `currency` is optional on v1 events and a valid default can be determined from historical data, put fallback logic in a dedicated normalization/adapter step with tests and metrics. Never silently accept null when it corrupts monetary amounts.

If `billingService.createInvoice` has side effects, make it idempotent by `eventId`. A record can be redelivered after an offset commit failure even when validation and deserialization both succeeded.

## 17. JSON Schema and validation before binding

Jackson reflects Java type and mapper constraints, but does not necessarily capture the entire event contract. JSON Schema can describe:

- Required fields via `required`.
- Data types via `type`.
- Value constraints via `enum`, `minimum`, `pattern`.
- Whether undeclared fields are allowed via `additionalProperties`.
- Nested object formats and structures.

Simplified JSON Schema example:

~~~json
{
  "type": "object",
  "required": ["eventId", "orderId", "amount"],
  "properties": {
    "eventId": {"type": "string"},
    "orderId": {"type": "string"},
    "amount": {"type": "number", "minimum": 0},
    "currency": {"type": "string"}
  },
  "additionalProperties": true
}
~~~

In this schema, `currency` is optional and new fields may appear. Changing `additionalProperties` to `false` causes a new field like `couponCode` to be rejected by a schema validator.

JSON Schema `required` checks property presence; to disallow JSON null, the schema must declare a type that rejects null. This differs from merely placing `@JsonProperty(required=true)` on a Java class.

Use JSON Schema when a contract outside Java is needed, especially when producers and consumers span multiple languages. Yet having a schema does not automatically enforce producer-side checks before publishing or consumer-side checks before processing; validation must be wired into workflows.

## 18. Differences with Avro

In Avro, schema resolution relies on writer and reader schemas. Both change directions behave differently from JSON/Jackson.

**New producer adds field, old consumer lacks it:** the old reader schema generally skips fields present in the writer schema but absent from the reader schema. This resembles ignoring unknown fields.

**New consumer requires field that old writer omitted:** if the reader schema adds a new field, Avro needs a valid default for that field when reading data written under the old writer schema. Without a default and without the field in the writer, schema resolution can fail.

Example new Avro schema with default:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "example.events",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "amount", "type": "long"},
    {"name": "currency", "type": "string", "default": "VND"}
  ]
}
~~~

The `VND` default here is valid only if that reflects historical data convention. Avro lets you declare schema defaults, but does not guarantee defaults are business-accurate.

With nullable unions, schemas can declare e.g. `["null","string"]` with a `null` default per Avro rules. Never assume a field that is merely nullable can automatically read old data when lacking a default; verify schema resolution and registry compatibility.

Schema Registry validates compatibility when registering new schemas per subject policy, though that policy must be configured and governed. Never replace integration testing with merely verifying schema registration succeeded.

## 19. Differences with Protobuf

Protobuf assigns each field a **field number** on the wire format. An old consumer reading a new message may encounter an unknown field number. Many Protobuf runtimes retain unknown fields in an unknown-field set when parsing binary, though retention, re-serialization, and JSON conversion differ by runtime or configuration.

An absent field in proto3 may read as the type's default: `0` for numbers, `false` for booleans, empty string. Thus, missing fields and fields explicitly holding default values are not always distinguishable without presence semantics.

With `optional` or message fields supporting presence, the application can test whether a field was actually set. When designing schemas, decide which fields need presence tracking and which can accept defaults.

When retiring a Protobuf field, mark the retired field number/name `reserved` to prevent accidentally reusing old field numbers with new meanings. Reusing a field number can cause silent data corruption worse than an explicit deserialization exception.

For Protobuf JSON mapping, parsers may have separate policies for unknown JSON fields. Do not equate unknown-field handling in Protobuf binary with how Jackson handles JSON.

## 20. New enum values and compatibility

Suppose the producer adds status `ON_HOLD`:

~~~json
{
  "eventId": "evt-007",
  "orderId": "ord-105",
  "status": "ON_HOLD"
}
~~~

The old consumer only has:

~~~java
enum OrderStatus {
    CREATED,
    CONFIRMED,
    CANCELLED
}
~~~

Even though field name `status` is known, value `ON_HOLD` is an **unknown enum value**, not an unknown property. Jackson can throw an exception if it cannot map the enum.

Jackson settings like `READ_UNKNOWN_ENUM_VALUES_AS_NULL` or `READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE` can enable fallbacks. If using a default enum, define a safe `UNKNOWN` state:

~~~java
enum OrderStatus {
    CREATED,
    CONFIRMED,
    CANCELLED,

    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

Do not map every new status to `CREATED` just so old consumers keep running. Doing so can trigger wrong workflows. For statuses affecting permissions, payments, or refunds, rejecting or quarantining the event is usually safer than guessing.

## 21. Deployment incident: adding a new field during a rolling deployment

A change considered safe usually requires preparing both producers and consumers.

For example, adding an optional `couponCode` field:

1. Define the contract: absent `couponCode` means no discount code.
2. New consumers accept old records lacking `couponCode`.
3. Old consumers accept new records carrying `couponCode` if business-neutral.
4. Deploy consumers able to read both forms.
5. Then producers start emitting `couponCode`.
6. Monitor deserialization errors, validation errors, and DLT.
7. Remove old compatibility logic only when retention/backlog and replay policies allow.

If adding a required field with no safe default, you may need a new topic/schema version, historical record migration, or a transition step. A change might work smoothly on live traffic yet still fail when replaying older records from DLT or backups.

Never assume "producer and consumer deploy at the exact same moment" as a compatibility premise. In distributed systems, some instances can run older versions longer than planned.

## 22. Unknown fields can mask data bugs

Tolerant reader is a helpful strategy, yet ignoring every unknown property can let producer typos go unnoticed.

For instance, a producer accidentally sends `amunt` instead of `amount`:

~~~json
{
  "eventId": "evt-008",
  "orderId": "ord-106",
  "amunt": 150000
}
~~~

If the consumer ignores unknown fields, it drops `amunt` and sees `amount` missing. If missing fields are not checked, `amount` can become `null` or `0`, causing business errors.

Reduce this risk by:

- Checking required fields right at deserialization or validation.
- Allowing unknown fields only on events designed for extensibility.
- Monitoring schema/version mismatches on producers/consumers.
- Running schema contract tests in CI.
- Recording metrics by producer version if events carry version markers.
- Separating malformed payload failures from downstream business errors.

If you want to know how often unknown fields arrive while the mapper ignores them, instrument the parser, validator, or schema diffing. Do not assume Jackson emits metrics for ignored fields automatically.

## 23. Testing in Spring Kafka

Tests should cover both directions of schema evolution, not just one "happy" JSON sample.

| Case | Payload | Expected outcome |
|---|---|---|
| Unknown field, tolerant reader | Has new `couponCode` | Deserializes cleanly; unused field ignored |
| Unknown field, strict reader | Has new `couponCode` | Deserialization failure |
| Missing optional field | Lacks `couponCode` | Defined default or null |
| Missing required creator property | Missing `orderId` | Deserialization failure |
| Missing required business field | Missing `currency` | Validation/recovery per policy |
| Explicit null | `"currency":null` | Follows explicit null rule |
| Wrong type | `"amount":"abc"` | Type conversion error |
| Property typo | `amunt` | Does not silently construct a valid amount |
| Unknown enum | `"status":"ON_HOLD"` | Intentional fallback or DLT |
| Malformed JSON | Missing brace, bad encoding | `ErrorHandlingDeserializer`/recovery |
| DLT re-drive | v1 data replayed into consumer v2 | No lost events; valid policy |

Mapper unit tests can verify basic compatibility:

~~~java
@Test
void ignoresNewOptionalPropertyWhenConfigured() throws Exception {
    String json = """
        {"eventId":"evt-1","orderId":"ord-1",
         "amount":100,"couponCode":"SAVE10"}
        """;

    ObjectMapper mapper = JsonMapper.builder()
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    OrderCreatedV1 event =
            mapper.readValue(json, OrderCreatedV1.class);

    assertThat(event.orderId()).isEqualTo("ord-1");
}
~~~

This uses a Java text block (Java 15+). `OrderCreatedV1` is the record defined above. JUnit/AssertJ imports depend on your test stack.

Integration tests with Embedded Kafka or Testcontainers must verify real behavior of `JsonDeserializer`, `ErrorHandlingDeserializer`, the listener container, `DefaultErrorHandler`, and the DLT. In particular, records failing before the listener runs may require a different value serializer when the recoverer publishes to the DLT.

## 24. Observing unknown/missing fields in production

A system with solid schema evolution should distinguish errors across categories:

**Deserialization**

- Counts of JSON parse errors, type mismatches, and strict unknown fields.
- Counts of missing creator properties or unsupported enums.
- Error rates by topic, event type, producer version, and consumer version.
- Counts of records with deserialization headers sent to DLT.

**Validation**

- Counts of records missing required business fields.
- Counts of records with invalid explicit nulls.
- Error rates by field code, without logging full payloads.
- Counts of events needing default value fallbacks.

**Operations**

- Consumer lag, retry counts, and DLT growth.
- Time from event emission to successful processing.
- Counts of successful/failed re-drive records.
- Producer serializer failures and CI compatibility check failures.

Logs should include `eventId`, topic, partition, offset, schema/version markers, exception class, and concise error codes. Avoid logging full payloads containing personal data; log the failing field name when safe.

Never auto-retry a record with a permanently missing field infinitely. When data cannot heal itself, route to DLT and investigate producer/schema. For transient errors like Schema Registry temporarily unreachable, apply a separate retry policy; distinguish them from genuinely invalid payloads.

## 25. Incident resolution workflow

When a newly deployed consumer sees rising deserialization errors:

1. Identify the failing topic, partition, offset, and event type.
2. Distinguish unknown field, missing field, explicit null, type mismatch, and malformed JSON.
3. Check producer version/schema ID and consumer version.
4. Inspect the actual `ObjectMapper`/`JsonDeserializer`: strict vs. tolerant, type headers, and trusted packages.
5. If errors happen before the listener, inspect `ErrorHandlingDeserializer` and the DLT producer.
6. If deserialization succeeds yet business logic fails, inspect validation and default policies.
7. Assess whether a tolerant reader can roll out safely or producers must fix events.
8. Preserve `eventId` and original metadata for controlled re-drive.
9. After fixing the schema/logic, replay a small batch of failed records before scaling up.
10. Add contract tests to prevent recurring errors of the same kind.

Never fix DLT data by mechanically deleting fields without understanding their meaning. For required fields, inserting an inaccurate default can cause irreversible business errors.

## 26. Principles to apply

- Treat unknown fields and missing fields as two distinct compatibility directions.
- Use tolerant readers for new fields that do not affect business logic; use strict readers when contracts require rejecting unfamiliar fields.
- Never assume Jackson always ignores unknown fields: verify the actual `ObjectMapper`.
- For missing fields, explicitly define optional/default/required per business rules.
- Distinguish absence from explicit null when their meanings differ.
- Never rely on primitive defaults `0`/`false` if you need to know whether the producer sent the field.
- Use creator validation, Bean Validation, or schema rules for required fields.
- Clarify backward/forward compatibility direction and rollout order.
- Use `ErrorHandlingDeserializer` so pre-listener errors enter the recovery flow.
- Route permanent schema errors to DLT instead of infinite retries.
- Equip the DLT producer to handle failing payloads that may be raw bytes.
- For Avro, check reader/writer schemas and defaults; for Protobuf, check field numbers and presence.
- Keep `eventId` and design idempotent consumers for retries/replays.
- Test both old and new records, missing data, nulls, new enums, malformed payloads, and DLT re-drives.

Unknown fields are not necessarily errors if consumers are designed to accept newer producer versions. Missing fields are not necessarily errors if the contract defines a valid default. Spring Kafka reliability depends on distinguishing these two cases, protecting required business data, managing schema evolution intentionally, and ensuring records that fail deserialization or validation enter an observable recovery flow.

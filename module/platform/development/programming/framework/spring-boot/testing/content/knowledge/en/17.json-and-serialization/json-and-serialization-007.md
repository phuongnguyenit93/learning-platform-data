# Round-Trip Serialization and the Limits of Testing Only Two-Way Conversion in Spring Boot

## 1. The problem: an object returning unchanged does not prove the JSON matches the contract

In Spring Boot, a REST API typically converts **Java objects to JSON** when responding to clients (`serialization`) and **JSON to Java objects** when receiving data (`deserialization`). A very natural test is:

```text
       serialize                  deserialize
Java DTO ----------> JSON ----------------------> Java DTO'
   |                                                 |
   +------------------ assert DTO' == DTO -----------+
```

If reading back yields the original object, it is called a **round-trip test**. It has value: it catches some dropped fields, changed data types, asymmetric custom serializers/deserializers, Unicode issues, or constructor binding failures.

However, this test has a **major limitation**: both directions usually use the **same mapper configuration, the same annotations, and the same schema assumptions**. Thus, both sides can be **consistently wrong**. For instance, a Java DTO has property `paymentId`; the partner expects JSON key `payment_id`, yet the serializer emits `paymant_id` and the deserializer reads `paymant_id`. The round-trip still passes while external clients cannot read it.

That is why you should never write only:

```java
assertEquals(original, mapper.readValue(
        mapper.writeValueAsString(original), PaymentResponse.class));
```

and conclude the JSON API is correct. You must verify **at least three distinct relationships**:

1. **Java → externally defined standard JSON**: field names, JSON types, required fields, null/absence, date/money formats, nested structures, and no leaked sensitive data.
2. **Sample JSON from client/partner → Java**: parses valid input, handles present/absent fields, and reacts to invalid data per contract.
3. **Java → JSON → Java**: preserves contract-required properties and semantics across both directions.

These three checks **complement one another; they do not replace one another**.

## 2. Concepts to distinguish

| Concept | Question tested | Example |
|---|---|---|
| Serialization | What JSON shape is emitted from the DTO? | `paymentId` to `"payment_id"` |
| Deserialization | Is valid JSON parsed into the right DTO? | `"amount": 19.90` to `BigDecimal("19.90")` |
| Object round-trip | Does reading back JSON written by the same mapper preserve the object? | `read(write(x)) == x` |
| JSON round-trip | Does re-writing parsed JSON preserve the JSON content? | `write(read(j))` vs `j` |
| Wire contract | What does an independent partner/client see over the wire? | `"payment_id"` key, status, content type |
| Equality | Which rule determines two objects are equivalent? | `record.equals`, `BigDecimal.equals`, domain comparison |
| Canonicalization | Does formatting get normalized across read/write? | whitespace stripped, key ordering, number/date format |
| Validation | Does the data satisfy business rules? | amount must be positive, ID non-empty |

Two objects being equal after a round-trip **does not prove** validation ran, JSON is compatible with older clients, HTTP delivery has the right content type, or Jackson is using production configuration.

### 2.1. Expressed as functions

Let `S` be the serialize function from DTO `D` to JSON `J`; let `P` be the deserialize function from JSON back to DTO.

- Object-oriented round-trip tests `P(S(d)) ≈ d`.
- JSON-oriented round-trip tests `S(P(j)) ≈ j`.
- Independent contract tests verify `S(d) ≈ j_expected` and `P(j_external) ≈ d_expected`.

The symbol `≈` must be defined: for DTOs, it may mean business-value equality; for JSON, it may mean **structural equality** (ignoring object field order) rather than raw string equality. If the interface spec mandates preserving numeric representation, timezone, or array element order, assertions must reflect those exact rules.

**Never infer from `P(S(d)) = d` that `S` and `P` are both right for independent clients**: composing two functions can succeed on selected test inputs even while each function violates the external contract.

## 3. When is a round-trip genuinely useful?

Round-trips help catch:

- A non-`null` field dropped by `@JsonIgnore` or a custom serializer and never restored.
- An enum/record/nested DTO that fails to read back due to missing constructors/creators or type mapping config.
- A custom date/time serializer losing timezone offset or precision if DTO equality detects it.
- A collection losing order or duplicates when converted to another collection type.
- Unicode strings or escape characters decoded incorrectly.
- A polymorphic DTO losing subtype info when the payload format must preserve subtypes.
- Jackson module changes making both directions incompatible, e.g., temporal or sealed types.

Yet the level of protection still depends on **chosen test data**. If you only test a DTO where every field is `null`, field-dropping logic can still pass. If you only test integer amounts, rounding bugs with `19.90` stay hidden. If you test an empty list, order/duplicate bugs go undetected.

Therefore, prepare representative fixtures: typical values, boundaries, `null`, empty, Unicode, nested objects, exact numbers, dates/offsets when relevant, collections with duplicate elements, and exception paths.

## 4. Why can two-way checks create false confidence?

### 4.1. Same misspelled field name in both directions

The partner requires:

```json
{"payment_id":"p-42","amount":19.90}
```

Yet the DTO has a misspelled annotation:

```java
record BrokenPayment(
        @JsonProperty("paymant_id") String paymentId,
        BigDecimal amount) {}
```

This is an illustrative snippet in a file with Jackson and `BigDecimal` imports. The mapper emits `"paymant_id"` and reads `"paymant_id"` right back into `paymentId`. **Object round-trip passes; client contract fails.** An independent assertion like `assertThat(tree.has("payment_id")).isTrue()` catches the defect.

This is a **symmetric defect**: the exact same wrong mapping is used in both `S` and `P`, so a two-way test cannot see it.

### 4.2. Missing a field that was already dropped

Suppose `internalNote` is not serialized due to `@JsonIgnore`. If a test constructs an object with `internalNote == null`, reading it back still gives `null`, so it passes. If the business needed that field on the wire, the test missed it. Conversely, some internal fields **must intentionally be excluded from JSON** (passwords, internal tokens); in that case a full object round-trip is not the right expectation—separate public DTOs from internal entities.

### 4.3. Misconfigured mapper that is self-compatible

Both directions might accidentally enable `SNAKE_CASE` for an API publishing `camelCase`; an object round-trip still succeeds. Similarly, a custom enum serializer and deserializer could agree on the wrong wire name. Assertions must compare against **golden JSON from the API spec**, not just JSON generated by the current mapper.

### 4.4. Valid JSON is not necessarily client-accepted JSON

An object can serialize to syntactically valid JSON that violates the semantic contract:
- Required field omitted (`"name"` missing).
- `"balance"` written as JSON string `"100.00"` instead of JSON number.
- UUID string turned into a nested object.
- Enum `"PAID"` changed to `"paid"`.
- Response includes `"secret"` even though clients never asked for it—worse, a data leak.
- Timestamp normalized to an offset/timezone rejected downstream.

Round-trips will not necessarily catch these discrepancies if both directions accept or silently convert them.

## 5. Choosing the right test environment and mapper

For Spring Boot 3.5 and Jackson 2, `@JsonTest` tests JSON mapping without booting the web server or database. `@JsonTest` configures Jackson within the JSON slice and provides helpers like `JacksonTester<T>`. It is the right tool for narrow unit/integration testing of serialization.

Three testing levels:

| Test level | Tools | What it can prove |
|---|---|---|
| Pure Jackson test | `new ObjectMapper()` + JUnit | Behavior of **that manually created mapper** with its declared modules/features |
| Boot JSON slice | `@JsonTest`, inject `JacksonTester<T>`/`ObjectMapper` | DTO with the mapper and JSON-related auto-config actually loaded by the slice |
| Web integration | `@WebMvcTest` + `MockMvc`, `@WebFluxTest` + `WebTestClient`, or `@SpringBootTest` | HTTP codecs, content types, controller advice, headers/statuses on the tested web path |

**Note:** `new ObjectMapper()` may lack `JavaTimeModule`, naming strategies, custom serializers, inclusion rules, or modules used in production by Spring Boot. When testing the application's HTTP JSON contract, use the **appropriate Spring context mapper**, or test through the real web pipeline. If the app customizes `ObjectMapper` inside a `@Configuration` outside the slice, `@JsonTest` does not automatically load all such configs; import/configure them explicitly and verify actual JSON.

In the runnable sections below, we use **Spring Boot 3.5.x / Jackson 2 / Java 17+**, so imports `com.fasterxml.jackson.databind.ObjectMapper`, `org.springframework.boot.test.autoconfigure.json.JsonTest`, and `JacksonTester` align with that line. **Do not copy these imports verbatim into Spring Boot 4 / Jackson 3**; see section 13 for migration details.

## 6. Java 17+ example with `@JsonTest`: round-trip and independent contract

### 6.1. Public payment contract

The application publishes payment JSON:

```json
{
  "payment_id": "pay-7",
  "amount": 19.90,
  "note": "quà tặng"
}
```

Minimum specification:
- JSON key **`payment_id`**, not `paymentId` or `paymant_id`.
- `amount` is a JSON number, not a string; Java uses `BigDecimal`.
- `note` is optional; in **this example**, when `null`, **omit the field** rather than emitting `"note":null`.
- When receiving data from an independent JSON fixture, the mapper must produce the right `PaymentResponse`.
- No internal fields or sensitive data may appear automatically in JSON.

We deliberately separate **object values** from the **JSON specification** so that a broken mapping is caught by an independent test.

### 6.2. Source layout and dependencies

Assumes the project already uses Spring Boot **3.5.x**, JDK 17+, and Gradle/Maven with Boot dependency management. Example `build.gradle` fragment (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-json'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is **not a complete `build.gradle`**: the project must provide the Spring Boot plugin, Java plugin/toolchain, and Maven Central repository. If the project already includes `spring-boot-starter-web`, Jackson JSON is normally included via the web starter, so `starter-json` is not separately needed.

Structure:

```text
src/main/java/com/example/jsoncontract/
    JsonContractApplication.java
    PaymentResponse.java

src/test/java/com/example/jsoncontract/
    PaymentResponseJsonTest.java
```

File `src/main/java/com/example/jsoncontract/JsonContractApplication.java`:

```java
package com.example.jsoncontract;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonContractApplication {
}
```

The `@SpringBootApplication` class helps Boot's test bootstrap locate the application configuration; `@JsonTest` still loads only the **JSON slice**, without starting an HTTP listener, datasource, or full application context.

### 6.3. DTO with Jackson annotations

File `src/main/java/com/example/jsoncontract/PaymentResponse.java`:

```java
package com.example.jsoncontract;

import java.math.BigDecimal;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record PaymentResponse(
        @JsonProperty("payment_id") String paymentId,
        @JsonProperty("amount") BigDecimal amount,
        String note) {
}
```

Notes on the DTO:
- `@JsonProperty("payment_id")` declares the wire key independently of Java component name `paymentId`.
- `@JsonInclude(NON_NULL)` omits `null` properties **when serializing**; it does not validate whether an input field is present.
- `BigDecimal` fits decimals requiring precision better than `double`, though **`BigDecimal.equals` is scale-sensitive**: `19.90` and `19.9` have equal numeric value yet `equals` can return `false`.
- `record` generates `equals`, `hashCode`, accessors, and constructor, making DTO comparisons convenient after round-trips.
- This is an illustrative response DTO; never use a JPA entity with lazy associations directly as a public JSON payload just to test round-trips.

### 6.4. Complete test: two-way + independent fixture + negative cases

File `src/test/java/com/example/jsoncontract/PaymentResponseJsonTest.java`:

```java
package com.example.jsoncontract;

import java.io.IOException;
import java.math.BigDecimal;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException;
import com.fasterxml.jackson.databind.JsonNode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

@JsonTest
class PaymentResponseJsonTest {

    @Autowired
    JacksonTester<PaymentResponse> json;

    @Autowired
    ObjectMapper mapper;

    private static PaymentResponse sample() {
        return new PaymentResponse(
                "pay-7",
                new BigDecimal("19.90"),
                "quà tặng");
    }

    @Test
    void objectRoundTripPreservesValues() throws IOException {
        PaymentResponse original = sample();

        String outgoing = json.write(original).getJson();
        PaymentResponse decoded = json.parseObject(outgoing);

        assertThat(decoded).isEqualTo(original);
    }

    @Test
    void outgoingJsonMatchesExternalContract() throws IOException {
        PaymentResponse original = sample();

        assertThat(json.write(original))
                .isStrictlyEqualToJson("""
                        {
                          "payment_id": "pay-7",
                          "amount": 19.90,
                          "note": "quà tặng"
                        }
                        """);

        JsonNode tree = mapper.readTree(json.write(original).getJson());
        assertThat(tree.get("payment_id").asText())
                .isEqualTo("pay-7");
        assertThat(tree.get("amount").isNumber()).isTrue();
        assertThat(tree.has("paymentId")).isFalse();
        assertThat(tree.has("paymant_id")).isFalse();
        assertThat(tree.size()).isEqualTo(3);
    }

    @Test
    void externalFixtureDeserializesCorrectly() throws IOException {
        String fromClient = """
                {
                  "payment_id": "client-8",
                  "amount": 12.50,
                  "note": "Nội dung"
                }
                """;

        PaymentResponse decoded = json.parseObject(fromClient);

        assertThat(decoded).isEqualTo(
                new PaymentResponse(
                        "client-8",
                        new BigDecimal("12.50"),
                        "Nội dung"));
    }

    @Test
    void nullNoteIsAbsentByPublicContract() throws IOException {
        PaymentResponse value = new PaymentResponse(
                "pay-9",
                new BigDecimal("0.01"),
                null);

        JsonNode tree = mapper.readTree(json.write(value).getJson());

        assertThat(tree.has("payment_id")).isTrue();
        assertThat(tree.has("amount")).isTrue();
        assertThat(tree.has("note")).isFalse();
    }

    @Test
    void malformedAmountDoesNotSilentlyBecomeValid() {
        String invalid = """
                {
                  "payment_id": "pay-10",
                  "amount": "not-a-number",
                  "note": "gift"
                }
                """;

        assertThrows(IOException.class, () -> json.parseObject(invalid));
    }

    @Test
    void unknownFieldCanBeRejectedWhenPolicyIsStrict() {
        ObjectMapper strictMapper = mapper.copy()
                .configure(
                        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
                        true);

        String fromClient = """
                {
                  "payment_id": "pay-11",
                  "amount": 4.00,
                  "debug_role": "admin"
                }
                """;

        assertThrows(
                UnrecognizedPropertyException.class,
                () -> strictMapper.readValue(
                        fromClient, PaymentResponse.class));
    }

    // INTENTIONALLY WRONG mapping: external contract requires "payment_id".
    private record BrokenPayment(
            @JsonProperty("paymant_id") String paymentId,
            BigDecimal amount) {
    }

    @Test
    void roundTripCanPassDespiteWrongExternalFieldName()
            throws IOException {

        BrokenPayment input = new BrokenPayment(
                "pay-12", new BigDecimal("10.00"));

        String outgoing = mapper.writeValueAsString(input);
        BrokenPayment decoded =
                mapper.readValue(outgoing, BrokenPayment.class);

        // Even with the wrong wire field name, both directions still match each other.
        assertThat(decoded).isEqualTo(input);

        JsonNode tree = mapper.readTree(outgoing);
        assertThat(tree.has("paymant_id")).isTrue();
        assertThat(tree.has("payment_id")).isFalse();
    }
}
```

**Important note:** `roundTripCanPassDespiteWrongExternalFieldName` **intentionally introduces a contract-breaking DTO example**, while its assertions remain sound: it proves a round-trip can pass even while the expected wire key is missing. Never put `BrokenPayment` into production as a real DTO.

In `outgoingJsonMatchesExternalContract`, `isStrictlyEqualToJson` checks JSON structure with the required fields, not byte-by-byte key ordering or whitespace. We add `JsonNode` assertions for the **JSON number type**, field count, and absence of wrong names. If the wire protocol mandates exact **lexical representation** (e.g., timestamp format, enum casing, monetary formatting), add explicit string/format assertions too.

`unknownFieldCanBeRejectedWhenPolicyIsStrict` demonstrates a **test-configured policy**. Do not assume Boot rejects unknown JSON properties by default; that depends on `ObjectMapper`/Jackson settings. If production requires strict mode, enable it on the **real HTTP endpoint mapper**, not merely on `mapper.copy()` in a test.

### 6.5. Reading the right conclusions from each test

| Test method | What it proves | Insufficient to conclude |
|---|---|---|
| `objectRoundTripPreservesValues` | DTO can be written and read back by this mapper while preserving `equals` | JSON conforms to the public schema |
| `outgoingJsonMatchesExternalContract` | Keys, JSON types, and field set of the sample response are right | All data variants/HTTP pipeline are right |
| `externalFixtureDeserializesCorrectly` | Independent JSON is parsed into the expected DTO | Invalid inputs are blocked at all layers |
| `nullNoteIsAbsentByPublicContract` | `null` is omitted during serialization | Server distinguishes missing/null on deserialization |
| `malformedAmountDoesNotSilentlyBecomeValid` | Non-numeric `amount` triggers a parse error | Negative or oversized numbers are domain-rejected |
| `unknownFieldCanBeRejectedWhenPolicyIsStrict` | Mapper **configured strictly in test** rejects unknown fields | Production mapper enforces the same policy |
| `roundTripCanPassDespiteWrongExternalFieldName` | Broken mapping example can still pass round-trip | Client-expected key is actually present |

All seven cases are **designed with specific assertions**; this Knowledge article does not pretend they were executed on your project. When Boot/Jackson dependencies or configurations differ, run tests and inspect reports to confirm. In principle, assertions pass on the **stated version line and configuration**.

## 7. Running the examples and inspecting real reports

Using the Gradle wrapper on Linux/macOS:

```bash
./gradlew test --tests "com.example.jsoncontract.PaymentResponseJsonTest"
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.jsoncontract.PaymentResponseJsonTest"
```

With the Maven wrapper on Linux/macOS:

```bash
./mvnw -Dtest=PaymentResponseJsonTest test
```

On Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=PaymentResponseJsonTest test
```

Prerequisites: project includes a wrapper, Java 17+, Spring Boot 3.5.x, Jackson 2/`JacksonTester`, and JUnit Jupiter. Gradle typically requires `useJUnitPlatform()`. If your source set uses Boot 4/Jackson 3 instead of Boot 3.5, adjust imports/configuration accordingly rather than forcing two major Spring versions together.

Check Gradle's report at `build/reports/tests/test/index.html` (in the module with the `test` task) or Maven Surefire's `target/surefire-reports/`. Confirm the test class was **discovered and executed**, not merely reported `UP-TO-DATE` or skipped. The test contains no `System.out.println`; there is no fixed business stdout to record.

## 8. JSON → Java → JSON round-trips have even more traps

Teams sometimes write tests that **take JSON and re-serialize it**, comparing both strings:

```java
String outgoing =
        mapper.writeValueAsString(
                mapper.readValue(incoming, PaymentResponse.class));
assertEquals(incoming, outgoing);
```

This is an **illustrative** snippet given an existing mapper and `incoming` variable. Raw string comparisons like this easily produce **false negatives** because JSON objects usually do not guarantee key order, whitespace, or equivalent escaping. For example:

```json
{"a":1,"b":2}
```

and:

```json
{
  "b": 2,
  "a": 1
}
```

have the exact same JSON object structure despite completely different strings. When key ordering is not contracted, parse both into `JsonNode` and compare **trees**, or use structural JSON assertions with intentionally chosen strict/lenient modes.

Even **tree equality** does not automatically prove a round-trip preserves every semantic detail:
- `1`, `1.0`, and `1.00` can represent the same mathematical value with different lexical precision; `JsonNode.equals` compares node representations in its own way.
- `"2026-03-01T10:00:00Z"` and `"2026-03-01T17:00:00+07:00"` represent the same instant yet have **different strings/offsets**.
- `null` and a **missing field** differ in JSON structure even if DTO mapping collapses both to `null`.
- Arrays have **order** and **element counts**; duplicates must not be ignored unless order/uniqueness is explicitly unordered in business semantics.
- Objects with **duplicate keys** like `{"id":1,"id":2}` should not be silently accepted or normalized; many parsers pick the last value, and stricter duplicate detection is a separate policy.

**The comparison rule must derive from the contract**, not from whichever `assertEquals` helper happens to be convenient.

## 9. Data corners to test independently

### 9.1. Missing fields and explicit null

These three JSON inputs are not identical:

```json
{}
```

```json
{"note":null}
```

```json
{"note":""}
```

Jackson can map both missing and explicit `null` to Java `null` for a reference-type record component, while empty string becomes `""`. If the contract uses JSON Merge Patch or "field omitted = keep unchanged" vs "null sent = clear data," a **plain DTO cannot preserve presence information**. Use a presence-tracking type, `JsonNode`, or an appropriate request schema.

A round-trip starting from `note == null` cannot tell `{}` apart from `{"note":null}` if the DTO and inclusion rule discard that information; test the wire contract directly.

### 9.2. Integers, decimals, and rounding

For money:
- Use `BigDecimal` or integer values in the smallest currency unit per domain contract when appropriate.
- Do not assume `double` preserves all decimal values accurately.
- `BigDecimal("19.90").equals(BigDecimal("19.9"))` is normally `false` due to different scale, whereas `compareTo(...) == 0` checks numeric equality. Determine whether the contract requires preserving **scale** or only numeric value.
- If the API specifies a JSON number, a JSON string `"19.90"` may still be **coerced** by Jackson into `BigDecimal` when configuration permits; an object round-trip can still pass even when input violates the JSON type.
- Very large numbers exceeding `long`/`int` ranges can cause overflow or parse errors; test boundaries and 400 handling.
- `NaN`, `Infinity`, or numeric precision beyond standard JSON requires explicit policy; do not allow them through with a permissive mapper without understanding clients.

### 9.3. Date/time, timezone, and precision

`Instant`, `OffsetDateTime`, `ZonedDateTime`, and `LocalDateTime` carry different semantics:
- `Instant`: an absolute point in time, typically formatted with `Z`/UTC or timestamp per config.
- `OffsetDateTime`: has an offset, though serializer/deserializer settings may normalize or strip offsets.
- `ZonedDateTime`: a zone ID carries richer meaning than an offset under seasonal rules.
- `LocalDateTime`: **carries no timezone/offset**, and cannot resolve a global instant on its own.

For example, `2026-03-01T10:00:00Z` and `2026-03-01T17:00:00+07:00` represent the same instant; `Instant.equals` can pass after conversion even if clients require **preserving the original offset string**. If the contract mandates ISO-8601 and nano/milli precision, check exact JSON strings or published normalization rules.

With Jackson 2, `java.time` support typically requires `JavaTimeModule` or a module auto-configured by Boot via dependencies. A plain `new ObjectMapper()` differs from Boot's mapper and may fail or emit different timestamps. Never change `WRITE_DATES_AS_TIMESTAMPS` or timezone settings just to make a test pass if production HTTP contracts disallow it.

### 9.4. Enums and version evolution

If the system emits:

```json
{"status":"AUTHORIZED"}
```

while old clients only understand `"APPROVED"`, a round-trip using the new Java enum still passes because both serialization and deserialization recognize the new value. Test consumer contracts or fixtures from **older versions**, fallback rules for unknown enums, `@JsonCreator`/`@JsonValue` where appropriate, and migration strategies.

Likewise, renaming `"user_id"` to `"userId"` leaves round-trips green while breaking backward compatibility. Golden files and contract tests detect wire schema changes much faster.

### 9.5. Collections, Maps, and generic types

If a DTO contains `List<T>`, tests must guard ordering and element counts when contracted. If it contains `Set<T>`, duplicates in input JSON are dropped—an object round-trip on a set **cannot prove duplicates in the original JSON were preserved**.

When deserializing `List<PaymentResponse>` directly with Jackson, do not pass `List.class` and cast as if generic types were preserved:

```java
List<PaymentResponse> values = mapper.readValue(
        inputJson,
        new TypeReference<List<PaymentResponse>>() {});
```

This is an illustrative snippet requiring `import com.fasterxml.jackson.core.type.TypeReference`, `List`, and a Boot 3/Jackson 2 mapper plus `inputJson` declared. Reading `List.class` turns elements into `LinkedHashMap` instead of `PaymentResponse`; a test that never accesses elements can miss it.

Maps with non-String keys or polymorphic values require custom mapping; JSON object keys are inherently strings. Do not expect `Map<SomeComplexKey, Value>` to round-trip cleanly in all cases without designing a custom serializer/deserializer.

### 9.6. Polymorphism and subtypes

A DTO typed as a base class or interface may serialize to readable JSON yet fail to deserialize back into the right subtype due to a missing type discriminator. Conversely, enabling overly broad default typing widens attack surface on untrusted input.

Do not casually enable Jackson default typing just so round-trips can deserialize any subtype. Use an **explicit public schema/discriminator with a bounded subtype allowlist**, safe polymorphic mapping, and tests using real partner JSON. If an API does not commit to dynamic polymorphism, prefer concrete DTOs instead of allowing arbitrary Java class names in JSON.

## 10. Security and privacy: round-trips do not prevent field leaks

An entity may hold `passwordHash`, `apiKey`, `internalRiskScore`, `tenantId`, or sensitive data. A round-trip checking object equality will **happily confirm** those fields serialized and deserialized successfully—when exposing them in JSON is itself a security vulnerability.

**Practical safeguards:**
- Use **separate response DTOs** distinct from JPA entities or internal models.
- Enforce a **public field allowlist** with structural JSON assertions, not only blacklisting one secret field.
- When data depends on permissions, test different users/tenants through the HTTP/security chain, not just a standalone `ObjectMapper`.
- Verify custom serializers/`@JsonView` are actually applied on the endpoint, not only on another mapper.
- Ensure test failure logs never dump secrets when using snapshot JSON.

For example, `assertThat(tree.size()).isEqualTo(3)` alongside per-key checks on the sample response in section 6 enforces a basic allowlist; in production, add dedicated tests for complex responses or OpenAPI/schema contract tests checking allowed fields.

## 11. Validation does not equal deserialization

JSON that is syntactically valid and parsed into an object by Jackson **is not necessarily business-valid**. Given a request DTO:

```java
public record NewPaymentRequest(
        @NotBlank String paymentId,
        @Positive BigDecimal amount) {}
```

This is an illustrative snippet requiring `jakarta.validation.constraints.NotBlank`, `Positive`, a validator dependency, and a test environment. Constraint annotations are Bean Validation metadata; **calling `ObjectMapper.readValue` directly does not run Bean Validation**.

In Spring MVC, controllers normally use `@Valid @RequestBody` with a suitable validation provider; in WebFlux, the corresponding argument validation mechanism runs when configured. Without `@Valid`, an object with a negative amount deserializes cleanly and enters the controller.

To guard the request contract, include at least:
1. Tests verifying JSON parsing/field binding.
2. Tests verifying validation constraints with `Validator` or a web test.
3. Tests verifying HTTP 400 + error schema on invalid requests.
4. Tests verifying the service is not called when invalid input is blocked at the web layer (when contracted).

A round-trip of `NewPaymentRequest(-1)` succeeds even though a negative amount is forbidden. **Never treat a round-trip as a validation test.**

## 12. How should direct JSON tests and HTTP response tests be combined?

### 12.1. `@JsonTest`: fast, focused on the mapper

Prefer when changing:
- DTO records/POJOs, `@JsonProperty`, `@JsonInclude`, `@JsonFormat`.
- Jackson modules, naming strategies, custom serializers/deserializers.
- Nested JSON structures, enums, dates, exact fields.
- Client fixtures from an agreed contract.

Cover all 3 branches—**outgoing**, **incoming**, and **round-trip**—rather than just one branch for coverage metrics.

### 12.2. `@WebMvcTest` / `@WebFluxTest`: testing the HTTP contract

A JSON mapper can be right while the endpoint still:
- Lacks the right URI/HTTP method mapping.
- Returns 200 instead of 201/404.
- Omits `Content-Type: application/json` or writes the body via a different converter.
- Uses a different DTO than the one tested with `@JsonTest`.
- Has JSON or HTTP status altered by `@ControllerAdvice`/filters/security.
- Outputs a different Jackson view/property filter than the mapper test.

`@WebMvcTest` + `MockMvc` checks MVC mappings, Jackson responses, content types, and advice in the slice. `@WebFluxTest` + `WebTestClient` checks the analogous WebFlux pipeline in its slice. When real HTTP sockets and multi-layer integration are needed, use `@SpringBootTest(webEnvironment=RANDOM_PORT)` with an appropriately configured HTTP test client.

**Never use a Web slice test with mocked services to claim production repositories, transactions, or SQL are verified.** An HTTP JSON contract test can be excellent while still testing only the controller against stubbed data.

### 12.3. Snapshot/golden JSON: keep it independent of the serializer under test

Golden JSON should come from an **approved API contract or partner fixture**, never auto-regenerated on every test run via `ObjectMapper.writeValueAsString`. If snapshots update automatically after code changes, tests merely "approve" bugs.

Review every schema change that could break clients:
- Added/removed/renamed fields, mandatory/optional changes.
- Enum values, union discriminators.
- Null/absence semantics.
- Date formats, timezones, and precision.
- Numeric vs string types and rounding rules.
- Nested object/array ordering and duplicates.
- Error response JSON, versioning, and backward compatibility.
- Whether any sensitive/internal fields appeared.

Structural snapshots should use a parser/strict JSON assertion instead of raw text when key order is not contracted; raw snapshots fit when exact bytes/lexical formatting are required.

## 13. Version notes: Spring Boot 3.5/Jackson 2 and Boot 4/Jackson 3

**The runnable code in this lesson targets Boot 3.5/Jackson 2.** When upgrading to Spring Boot 4.x, do not assume all imports and default mapper features stay the same.

Key migration points:
- Spring Boot 4 prioritizes **Jackson 3**; many classes move from `com.fasterxml.jackson.databind` into the `tools.jackson` namespace. **Important exception:** Jackson annotations such as `@JsonProperty` remain in `com.fasterxml.jackson.annotation`.
- Boot 4 provides Jackson 3's `JsonMapper` and updated auto-configuration; a Jackson 2 `new ObjectMapper()` cannot be treated as equivalent to Boot 4's mapper.
- `@JsonTest` still exists, though it auto-configures JSON mappers based on classpath libraries/versions. Tests should inject and use **the mapper the application actually uses**.
- Boot/Jackson 2 `@JsonComponent` migrates to `@JacksonComponent` for Jackson 3; review the migration guide and custom module registration.
- Boot 4 changes default module detection and some JSON property settings; external JSON fixtures can catch schema shifts that object round-trips miss.
- Do not mix `jackson-databind` 2.x and 3.x dependencies expecting identical mappings; follow a BOM/Boot-supported migration strategy.

To verify compatibility after upgrading, **keep the external fixtures/golden JSON from Boot 3.5 unchanged** and run them against Boot 4's mapper alongside internal round-trips. This exposes changes in field naming, null inclusion, date formatting, coercion, or module registration that two compatible new serialize/deserialize implementations might otherwise agree on.

No single claim like "Jackson 3 always serializes differently from Jackson 2" holds for all DTOs; differences depend on classes, annotations, defaults, and modules. **Assert actual JSON** in your project.

## 14. Common testing mistakes and how to fix them

| Anti-pattern | Why it is unreliable | Better verification |
|---|---|---|
| Only `assertEquals(dto, read(write(dto)))` | Both directions can share the same schema bug and still pass | Add external JSON fixtures and exact field contracts |
| Golden JSON auto-generated from the mapper on every run | Test no longer has an independent oracle | Commit fixed, reviewed fixtures |
| Sample DTO has all fields empty/null | Fails to catch omitted/lost fields | Include non-null, nested, boundary, and Unicode values |
| Asserting object equality when `equals` omits important fields | Equality may be too weak | Assert specific fields and wire structure |
| Comparing raw JSON strings only | Whitespace/key order causes false negatives | Structural JSON assertions when ordering is uncontracted |
| Always using lenient JSON assertions | Can ignore extra fields or wrong types | Strict structural assertions, type and field-count checks |
| Treating `BigDecimal.equals` as numeric comparison | Scale differences fail tests despite equal numeric value | Pick `equals` or `compareTo` per domain rules |
| Testing amounts with `double` and claiming monetary accuracy | Floating-point introduces rounding errors | Use `BigDecimal` or integer minor units |
| Ignoring missing vs `null` | PATCH/optional field semantics can break | Test missing, null, and empty string separately |
| Manually built `ObjectMapper` differs from Boot's mapper | Modules/naming/date/format configs diverge | Inject the mapper from the JSON slice/HTTP path |
| Directly serializing JPA entities | Risks lazy loading/recursive graphs/secret leaks | Use separate response DTOs, test field allowlists |
| Passing `List.class` to parse a generic list | Elements may become maps | Use `TypeReference<List<T>>` |
| Assuming successful deserialization means validated data | Jackson does not run Bean Validation | Test `@Valid`/Validator and HTTP 400 |
| Unconditionally hiding unknown JSON fields | Can mask client typos or break versioning policy | Choose FAIL/IGNORE per contract and test explicitly |
| Enabling default typing for all subtypes | Unsafe for untrusted input | Restrict polymorphic types via schema/discriminator |
| Testing only `@JsonTest` and concluding HTTP API is right | Skips status codes, headers, filters, chosen DTO | Add MockMvc/WebTestClient/HTTP integration tests |
| Same code generates both expected and actual JSON fixtures | No independent oracle | Use external fixtures governed by clients/schema |
| Migrating Boot/Jackson and running only round-trips | New mapper can agree with itself on a wrong new schema | Run golden JSON and request samples across versions |

## 15. Checklist to make round-trips genuinely valuable

- [ ] Defined an **independent wire contract** (OpenAPI/JSON Schema/partner fixture): field names, types, presence, null, formats.
- [ ] Tested DTO → expected JSON using **strict structural assertions** and key JSON types.
- [ ] Tested external JSON → expected DTO without reusing JSON produced by the serializer.
- [ ] Object round-trips use representative fixtures: non-null, empty, `null`, Unicode, nested, boundaries, precision.
- [ ] Defined **equality**: `record.equals`, `BigDecimal` scale, date offset/instant, order/duplicates.
- [ ] Tested unknown fields, missing required fields, type coercion, and malformed JSON per policy.
- [ ] Tested enums, timezone/date formats, generic collections, and polymorphic DTOs if used by the contract.
- [ ] No internal/secret fields serialized; allowlists or schema assertions in place.
- [ ] With Boot, tests use mappers/configurations reflecting the real app, not just default `new ObjectMapper()`.
- [ ] If validation is needed, tested `@Valid`/Validator and HTTP 400 separately.
- [ ] If protecting an HTTP contract, included web tests checking status, content type, headers, and body/error schemas.
- [ ] When upgrading Spring Boot/Jackson, ran external fixtures across versions to detect behavioral drift.
- [ ] Executed the proper test task, verified executed test counts, and inspected test reports before declaring PASS.

## 16. Official Documentation to Continue

- [Spring Boot 3.5 – Auto-configured JSON Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@JsonTest`, `JacksonTester`, JSON comparisons via helpers.
- [Spring Boot 4 – JSON Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): JSON test scope and supported mappers.
- [Spring Boot 4.0 Migration Guide – Upgrading Jackson](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): Jackson 3 namespaces, modules, and default changes.
- [Spring Boot 3.5 – JacksonTester API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/json/JacksonTester.html): `write`, `parse`, `parseObject`.
- [Jackson 2 Annotations](https://github.com/FasterXML/jackson-annotations/wiki/Jackson-Annotations): `@JsonProperty`, `@JsonIgnore`, `@JsonInclude`, `@JsonCreator`, and related annotations.

**Conclusion:** Round-trip serialization is a useful check, yet **insufficient to prove a JSON contract**. Both directions using the same mapper can share the same bug and still reconstruct the original object; `null` handling, naming, numbers, dates/times, unknown fields, security, or validation can all slip through. A reliable test suite combines **semantic round-trips**, **independent golden JSON for serialization**, **independent input JSON for deserialization**, and **HTTP contract tests** whenever JSON crosses a live API.
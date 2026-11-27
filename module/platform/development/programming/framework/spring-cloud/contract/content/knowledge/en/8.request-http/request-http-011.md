# Distinguishing Missing Fields from Null-Valued Fields in HTTP Requests

When two services exchange JSON data, an **absent field** and a **field present with value `null`** are two different states. Confusing them can cause serious bugs: a consumer intends to update a single property while the producer wipes out an existing value; or a consumer wants to clear a property while the producer ignores the operation. In **Spring Cloud Contract**, this distinction must be expressed clearly in the **HTTP request contract**, verified on producer code, and simulated accurately by stubs for the consumer.

This lesson belongs to the **Request HTTP** chapter of module **SPRING_CLOUD_CONTRACT**. Spring Cloud Contract lets you define HTTP or messaging behavior using **Groovy/YAML DSL**, generate producer verification tests, package stubs, and run **Stub Runner** for consumers in CI pipelines. The focus here is the JSON request: when a property *does not exist*, when it *exists with value null*, how to avoid losing that information in Java/Jackson, and how to catch cases where both get conflated during contract testing.

## 1. Four Easily Confused States When Receiving JSON

Consider the `phone` field in a customer-update request. The following bodies carry different meanings:

| JSON Request Body | State of `phone` | Meaning That Can Be Specified in the API |
| --- | --- | --- |
| `{}` | **Field `phone` is absent** | Leave the current phone number unchanged. |
| `{"phone":null}` | **Field `phone` is present, JSON null value** | Explicitly clear the current phone number. |
| `{"phone":""}` | Field `phone` is present, empty string | Request setting phone number to empty string or raise a validation error. |
| `{"phone":"null"}` | Field `phone` is present, literal string `null` | Regular string, not JSON null. |
| `{"phone":"+84901234567"}` | Field `phone` is present, non-empty string | Request updating to a specific phone number. |

This example uses the **business convention of a hypothetical API**: **absent = keep unchanged**, **null = clear**. HTTP itself does not impose this rule from the method or `application/json` alone. Producer and consumer teams must **agree on it, document it in the API spec, and write it into contracts**. With `application/merge-patch+json` under JSON Merge Patch, `null` has member-removal semantics by specification; with plain JSON, you must define and enforce its meaning yourself.

At the data level, the following two structures are **not equal**:

```json
{}
```

```json
{"phone": null}
```

In the second case, the `phone` key actually exists in the object; only the **value** of that key is `null`. When a tool or DTO class collapses both into a Java `null` without tracking key presence, information has been lost.

## 2. Why Is This a Producer–Consumer Contract Issue?

Suppose **Customer Service** is the producer of the endpoint:

```http
PATCH /api/customers/42
Content-Type: application/json
```

**Billing Service** is the consumer calling the endpoint to update customer details during invoicing. Prior to the update, customer `42` has `+84901234567`. Two scenarios are agreed upon by both teams:

**Scenario A — `phone` omitted, keep unchanged:**

```http
PATCH /api/customers/42
Content-Type: application/json

{}
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"customerId":42,"phone":"+84901234567"}
```

**Scenario B — `phone: null` sent, clear number:**

```http
PATCH /api/customers/42
Content-Type: application/json

{"phone":null}
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"customerId":42,"phone":null}
```

Different responses allow **generated producer tests** to observe whether the producer code truly distinguishes the two requests. For stubs, the two mappings must also distinguish `{}` from `{"phone":null}`, even though both share the same method, path, and `Content-Type`.

This example illustrates two **independent behaviors on sample data**; it does not mean the HTTP stub automatically persists customer state across multiple calls. In a real application, `PATCH` mutates data on the producer side; a stub normally returns fixed responses based on request matchers and **does not automatically simulate the full state lifecycle**.

## 3. Conventions for Expressing This in Spring Cloud Contract

In Groovy and YAML DSL, when representing JSON, distinguish three things:

1. **Key appears in the body**: represents the field sent by the request.
2. **Value of the key**: `null`, `""`, `false`, `0`, or a concrete value.
3. **Request matching rules generated for the stub**: must be tight enough not to accidentally match requests from the other scenario.

If a contract only describes `{"customerId":42}`, that means **the sample body omits the `phone` field**. However, **omitting `phone` from the example does not automatically guarantee** the generated stub will *reject any request adding `phone`*; that depends on the actual matcher generated and JSON matching configuration. Therefore, when **field absence is a business condition**, inspect the actual mapping and add a **negative** test to verify requests containing the field do not cross-match.

Similarly, when a contract contains `phone: null`, verify that the tooling preserves **JSON null** in requests sent to the producer and in stub request matchers, instead of stripping the field or turning it into the string `"null"`.

### 3.1. YAML `null` Differs from String `"null"`

In YAML, the following notations do not have the same data type:

```yaml
phone: null      # YAML null -> null value
phone2: ~        # YAML null
phone3: "null"    # Four-character string n-u-l-l
phone4: ""        # Empty string
```

When using YAML as the Spring Cloud Contract DSL, pick one **consistent** style such as `phone: null` so reviewers can spot it easily. Confirm that the parser/serializer in your **Spring Cloud Contract version** preserves null-valued fields in JSON requests. A parseable YAML file does not automatically mean a request matcher satisfies absent vs. null conditions.

### 3.2. Groovy `null` Differs from String `"null"`

In Groovy:

```groovy
def withoutPhone = [:]
def withExplicitNull = [phone: null]
def withStringNull = [phone: 'null']

assert !withoutPhone.containsKey('phone')
assert withExplicitNull.containsKey('phone')
assert withExplicitNull.phone == null
assert withStringNull.phone == 'null'
```

Both of the first two maps return `null` when accessing `map.phone`, yet `containsKey` tells whether the map actually contains the `phone` key. This same principle applies when the producer reads requests using `Map<String, Object>` or Jackson `JsonNode`.

## 4. Groovy DSL Example: Two Contracts for Two Distinct Bodies

Sample file `src/test/resources/contracts/customers/patch_phone.groovy` defines two scenarios in one `Contract.make` list:

```groovy
import org.springframework.cloud.contract.spec.Contract

[
    Contract.make {
        name 'shouldKeepPhoneWhenFieldMissing'
        description 'Keep existing phone number when phone is omitted'

        request {
            method 'PATCH'
            url '/api/customers/42'
            headers {
                contentType(applicationJson())
            }
            body('{}')
        }

        response {
            status 200
            headers {
                contentType(applicationJson())
            }
            body('{"customerId":42,"phone":"+84901234567"}')
        }
    },
    Contract.make {
        name 'shouldClearPhoneWhenExplicitNull'
        description 'Clear phone number when phone is JSON null'

        request {
            method 'PATCH'
            url '/api/customers/42'
            headers {
                contentType(applicationJson())
            }
            body('{"phone":null}')
        }

        response {
            status 200
            headers {
                contentType(applicationJson())
            }
            body('{"customerId":42,"phone":null}')
        }
    }
]
```

Two `Contract.make` calls sit inside **one Groovy list returned at the end of the script**. Each contract has its own `name`, `request`, and `response`. Using **raw JSON strings** inside `body(...)` makes the difference between `{}` and `{"phone":null}` explicit and avoids any map-conversion step accidentally stripping null fields during data preparation.

**Note on matchers:** the example describes **inputs and expected outputs**, but you should not blindly conclude the two generated stub mappings are mutually exclusive just by reading the Groovy code. Inspect the generated JSON mappings inside the `stubs` artifact and run a test intentionally sending the other scenario's request. If body-matching configuration does not enforce presence/absence as desired, use an appropriate request-matching mechanism **supported by your tool version**, then re-verify both producer tests and stub tests. Never rely on mapping order to decide responses for two requests with potentially overlapping match conditions.

## 5. YAML DSL Example: Splitting into Two Readable Files

Teams choosing YAML can put each scenario in its own file. For `patch_phone_missing.yml`:

```yaml
description: Keep existing phone number when phone is omitted
request:
  method: PATCH
  url: /api/customers/42
  headers:
    Content-Type: application/json
  body: '{}'
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    customerId: 42
    phone: "+84901234567"
```

And `patch_phone_null.yml`:

```yaml
description: Clear phone number when JSON null is sent
request:
  method: PATCH
  url: /api/customers/42
  headers:
    Content-Type: application/json
  body:
    phone: null
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    customerId: 42
    phone: null
```

The two `body` forms here are chosen to show an **empty JSON body** and a **body with a null key**. The null case can also be written as a JSON string:

```yaml
body: '{"phone":null}'
```

However, not every YAML/Groovy syntax produces the **exact same stub request matcher** across all plugin versions. For this lesson, verify through the build that:

- The generated producer test for the absent case **sends a JSON object without `phone`**.
- The generated producer test for the null case **sends a JSON object with `phone` set to JSON null**.
- The stub server distinguishes the two requests without returning the other scenario's response.
- When the consumer sends `{"phone":""}` or `{"phone":"null"}`, they **do not accidentally trigger phone deletion** if the API does not specify that behavior.

A safe convention is **keeping only one DSL active per scenario set** in the repository. Do not place both the YAML files from this section and the Groovy file from the previous section in the scanned build path if they represent the same request group; doing so creates duplicate, hard-to-control tests and mappings.

## 6. Reading HTTP Requests in Java Without Losing Information

This is the most important part on the producer side: if Java code conflates both states before business logic runs, even an accurate contract will not make the API behave properly. Consider three common ways of reading requests.

### 6.1. A DTO with Nullable Properties May Not Suffice

Suppose the controller uses:

```java
public record PhonePatch(String phone) {}
```

Under standard Jackson configuration, both bodies:

```json
{}
```

and:

```json
{"phone":null}
```

produce a `PhonePatch` with `phone() == null`. Then the check `phone() == null` **cannot distinguish** whether the consumer omitted the field or explicitly sent null. Mapping behavior can differ if a project uses custom deserializers/validation, yet a DTO with a plain `String` should not be treated as a default three-state solution.

When you need to distinguish them, use a mechanism that preserves **field presence**, such as `JsonNode`, `Map` with `containsKey`, or a dedicated three-state wrapper/custom deserializer.

### 6.2. Using Jackson `JsonNode`: `has` vs. `hasNonNull`

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

JsonNode missing = mapper.readTree("{}");
JsonNode explicitNull = mapper.readTree("{\"phone\":null}");
JsonNode emptyString = mapper.readTree("{\"phone\":\"\"}");

assert !missing.has("phone");
assert missing.get("phone") == null;

assert explicitNull.has("phone");
assert explicitNull.get("phone").isNull();

assert emptyString.has("phone");
assert emptyString.get("phone").isTextual();
assert emptyString.get("phone").asText().isEmpty();
```

Jackson methods to distinguish:

| Method | For `{}` | For `{"phone":null}` | Meaning |
| --- | --- | --- | --- |
| `node.has("phone")` | `false` | `true` | Checks whether the **key** exists. |
| `node.get("phone")` | Java `null` | Jackson `NullNode` | Returns the node, or Java null when key is missing. |
| `node.hasNonNull("phone")` | `false` | `false` | True only when key exists and its value is not JSON null. |
| `node.path("phone")` | `MissingNode` | `NullNode` | Never throws on missing key; can use `isMissingNode()` or `isNull()`. |

**Common mistake:** using `!node.hasNonNull("phone")` to infer a field is **absent**. That expression evaluates to true for **both missing and explicit null**. To check absence, use `!node.has("phone")`; to check present-and-null, use `node.has("phone") && node.get("phone").isNull()`.

### 6.3. Using `Map`: `containsKey` vs. `get`

```java
Map<String, Object> missing = new HashMap<>();
Map<String, Object> explicitNull = new HashMap<>();
explicitNull.put("phone", null);

assert !missing.containsKey("phone");
assert explicitNull.containsKey("phone");
assert missing.get("phone") == null;
assert explicitNull.get("phone") == null;
```

`map.get("phone") == null` still conflates both states. Only `containsKey` detects key existence. Note that `Map.of("phone", null)` in Java is **invalid** because `Map.of` forbids null values; the example uses `HashMap`.

## 7. Implementing a Producer That Properly Handles Both States

The following Spring MVC controller simulates the behavior defined in the two contracts. It does not use a database; the sample phone number acts as the initial state for customer `42`, and each request's response is computed **independently**.

```java
package com.acme.customers;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final ObjectMapper mapper;

    public CustomerController(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @PatchMapping(
        value = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<JsonNode> patchCustomer(
            @PathVariable long id, @RequestBody JsonNode input) {

        if (id != 42L) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).build();
        }
        if (!input.isObject()) {
            return ResponseEntity.badRequest().build();
        }

        ObjectNode result = mapper.createObjectNode();
        result.put("customerId", 42);

        if (!input.has("phone")) {
            // Field absent: keep the assumed stored value.
            result.put("phone", "+84901234567");
        } else if (input.get("phone").isNull()) {
            // Field present and JSON null: clear value.
            result.putNull("phone");
        } else if (input.get("phone").isTextual()) {
            // Field contains a string: replace with requested string.
            result.put("phone", input.get("phone").asText());
        } else {
            return ResponseEntity.badRequest().build();
        }

        return ResponseEntity.ok(result);
    }
}
```

**Key behavior:** `input.has("phone")` confirms property presence; `input.get("phone").isNull()` confirms JSON null type. `result.putNull("phone")` explicitly writes a JSON `null` into the response, preventing key omission if a DTO or serializer is configured to drop Java null values.

This code is purely a **fixture for learning contract testing**. In a real service, update logic must access persisted data, verify authorization, validate inputs, manage transactions, and save changes. For update APIs, ensuring responses reflect real post-write state is a separate business requirement needing its own tests.

Generated producer tests from Groovy/YAML DSL prove their worth when real behavior diverges from the contract. For example, if the implementation swaps `if (!input.has("phone"))` for `if (!input.hasNonNull("phone"))`, `{"phone":null}` gets mistaken for absent, producing a response with the old phone number. When both contracts are loaded and run, the null-case test catches this mismatch.

## 8. Checking Whether Generated Producer Tests Truly Distinguish Both Cases

In a producer configured with Spring Cloud Contract Verifier, run the appropriate build step, e.g. Maven:

```shell
mvn clean verify
```

What to inspect after the build:

1. The plugin **loaded both contracts** and generated the corresponding test cases.
2. The generated test for `shouldKeepPhoneWhenFieldMissing` sends a JSON object **without `phone`** and asserts `phone: "+84901234567"`.
3. The generated test for `shouldClearPhoneWhenExplicitNull` sends `phone: null` and asserts the response **has** the `phone` key with JSON null.
4. If you change producer code to conflate both states, **at least one relevant test must fail**.

Generated class and method names depend on plugin version and base test configuration; do not infer case counts solely from Groovy/YAML file counts. When a Groovy file returns a list of two contracts, make sure **both Contract objects** are loaded by the plugin rather than checking only for `BUILD SUCCESS`.

### 8.1. Adding Negative Tests to Verify Missing/Null Semantics

Alongside generated producer tests, a small manual test helps catch deserialization or serialization bugs. Example sending two requests to the controller:

```java
mockMvc.perform(patch("/api/customers/42")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{}"))
    .andExpect(status().isOk())
    .andExpect(content().json(
        "{\"customerId\":42,\"phone\":\"+84901234567\"}", true));

mockMvc.perform(patch("/api/customers/42")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"phone\":null}"))
    .andExpect(status().isOk())
    .andExpect(content().json(
        "{\"customerId\":42,\"phone\":null}", true));
```

This is an **illustrative test body**, assuming `MockMvc`, static imports from `MockMvcRequestBuilders` and `MockMvcResultMatchers`, and Spring Test/JUnit. The `true` argument in `content().json(..., true)` enforces strict JSON comparison, revealing differences between a null field and an omitted field. In larger suites, share the same fixtures so contract tests and dedicated tests do not silently rely on different initial states.

## 9. Verifying Stubs and Real Consumer Calling Code

Once producer verification passes, the build creates a versioned `stubs` artifact, e.g. `com.acme:customer-service:1.0.0:stubs`. Stub Runner locates and runs mappings inside that artifact. The consumer must verify the **exact body it actually sends**, because JSON libraries can alter the request before it reaches the stub.

### 9.1. Building Consumer Bodies Without Dropping Nulls

Jackson's `ObjectNode` makes the two operations explicit:

```java
ObjectNode omitted = objectMapper.createObjectNode();
ObjectNode explicitNull = objectMapper.createObjectNode().putNull("phone");

assert !omitted.has("phone");
assert explicitNull.has("phone");
assert explicitNull.get("phone").isNull();
```

If a consumer builds a DTO with `phone == null` and a serializer is configured with `@JsonInclude(Include.NON_NULL)`, the null field **can be stripped from the JSON completely**. Then the consumer thinks it sent a delete request, while on the wire it sent `{}`. For APIs distinguishing three states, use `ObjectNode`, a dedicated patch type, or a serializer preserving field presence.

### 9.2. Real Client Code and Testing via Stub Runner

The example below uses Spring Framework 6.1+'s `RestClient`. `JdkClientHttpRequestFactory` is explicitly configured to send HTTP `PATCH` via the JDK's `java.net.http.HttpClient`; request factory setup may differ in apps already using an HTTP client with native PATCH support.

```java
package com.acme.billing;

import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CustomerClient {

    private final RestClient http;

    public CustomerClient(RestClient.Builder builder,
                          @Value("${customers.base-url}") String baseUrl) {
        this.http = builder
                .baseUrl(baseUrl)
                .requestFactory(new JdkClientHttpRequestFactory())
                .build();
    }

    public String patchPhone(long id, ObjectNode patchBody) {
        return http.method(HttpMethod.PATCH)
                .uri("/api/customers/{id}", id)
                .contentType(MediaType.APPLICATION_JSON)
                .body(patchBody)
                .retrieve()
                .body(String.class);
    }
}
```

Assume the consumer application has Spring Boot configured to inject `ObjectMapper` and `CustomerClient`, and declares the test dependency `spring-cloud-starter-contract-stub-runner`. Test class:

```java
package com.acme.billing;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = "customers.base-url=http://localhost:8089")
@AutoConfigureStubRunner(
    ids = "com.acme:customer-service:1.0.0:stubs:8089",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CustomerClientContractTest {

    @Autowired CustomerClient customerClient;
    @Autowired ObjectMapper mapper;

    @Test
    void missingPhoneLeavesExistingValue() throws Exception {
        ObjectNode request = mapper.createObjectNode();
        String json = customerClient.patchPhone(42L, request);
        JsonNode response = mapper.readTree(json);

        assertThat(response.get("phone").asText())
            .isEqualTo("+84901234567");
    }

    @Test
    void explicitNullClearsPhone() throws Exception {
        ObjectNode request = mapper.createObjectNode();
        request.putNull("phone");
        String json = customerClient.patchPhone(42L, request);
        JsonNode response = mapper.readTree(json);

        assertThat(response.has("phone")).isTrue();
        assertThat(response.get("phone").isNull()).isTrue();
    }
}
```

The example uses `LOCAL` because the artifact must have been installed into local Maven by the producer build. When using an artifact **published** to a shared Maven repository, switch to `REMOTE` and configure `repositoryRoot` with appropriate read credentials. Version, classifier, and port in `ids` must match the artifact and HTTP client address.

**Important:** both tests pass or fail according to the mappings actually generated. Never feel confident merely because a test receives `200`: both scenarios return `200`, so you must assert **different values** and confirm `phone` is present when the response specifies JSON null. Try swapping bodies between the two tests or sending `{"phone":""}` to verify the stub does not cross-match a broad mapping.

## 10. Controlling Request Matchers and the Risk of Overlapping Mappings

Both contracts above share the same:

```text
method = PATCH
url = /api/customers/42
Content-Type = application/json
```

Only the **body** distinguishes them. If a generated mapping skips body checks or is configured to ignore extra JSON properties, `{"phone":null}` can also match the mapping meant for `{}`. Mapping order/priority then decides the response, which is not an intentional business distinction.

When inspecting the `stubs` artifact, examine the request body matcher generated by Spring Cloud Contract for **each** case. In WireMock, one JSON comparison construct is `equalToJson`; an example illustrating a strict matcher:

```json
{
  "request": {
    "method": "PATCH",
    "url": "/api/customers/42",
    "bodyPatterns": [
      {
        "equalToJson": "{}",
        "ignoreExtraElements": false
      }
    ]
  }
}
```

Here `ignoreExtraElements: false` indicates the JSON matcher does not intentionally ignore extra properties. This is **an illustrative JSON snippet showing WireMock request matching**, **not a guarantee** that Spring Cloud Contract generates this exact mapping from the Groovy/YAML snippets above. You must inspect the generated files and actual Stub Runner behavior in your project's version; if you need a specialized matcher to enforce field absence, pick a DSL/request-matching capability supported by your version and test cases that must not match.

A matcher verification plan should cover:

| Request Sent to Stub | Expected per Sample API | What Is Checked? |
| --- | --- | --- |
| `{}` | Keep existing `phone` | Returns `200` and the existing phone number. |
| `{"phone":null}` | Clear `phone` | Returns `200`, with `phone` field set to JSON null. |
| `{"phone":""}` | Does not match either case above if no contract exists | Must not silently trigger "keep" or "clear" due to overly broad matching. |
| `{"phone":"null"}` | String, not null | Must not accidentally match the null case. |
| Non-JSON body | Per API rules | Must not be accepted merely because method/path match. |

For **unmatched** cases, WireMock normally returns `404`. That is a **404 due to an unmatched stub request**, not necessarily a producer business error. If you want to test a business `404` error, write a contract describing that `404` with its specific error body/code to avoid false passes.

## 11. Common Confusions When Using Matchers, JSONPath, and Schemas

APIs checking path existence and value checks often carry different semantics:

- **Key presence**: was `phone` sent?
- **Non-null value**: does `phone` hold concrete data?
- **JSONPath match**: does the expression return a matching node/value? A library's JSONPath matcher may treat a null result as non-matching depending on invocation and version.
- **Schema match**: must the field exist, or is null merely permitted? Those are two separate constraints.

In JSON Schema, for example:

```json
{
  "type": "object",
  "properties": {
    "phone": { "type": ["string", "null"] }
  },
  "additionalProperties": false
}
```

`phone` may be **absent** or have type `string`/`null` because it is not listed under `required`. Adding:

```json
"required": ["phone"]
```

to the object schema forces the field to be **present**, even though its value can still be `null`. This is a general JSON Schema rule, **not** a claim that Spring Cloud Contract automatically uses this schema as a request matcher; schema checking requires integrating an appropriate validation mechanism.

In OpenAPI, **optional** (whether presence is required) and **nullable** (whether JSON null is accepted) must likewise be specified independently. Never read `nullable` and infer the field is always present, or read `required` and infer the value cannot be null. Nullable syntax depends on specification version: OpenAPI 3.0 typically uses `nullable`, while OpenAPI 3.1 follows JSON Schema and can use a type union including `null`.

## 12. Common Errors and Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `{}` and `{"phone":null}` are handled identically. | `String phone` DTO, checking `== null`, or using `hasNonNull` instead of `has`. | Inspect deserialized request object; use `JsonNode.has`/`isNull` or `Map.containsKey`. |
| Consumer tries to clear phone yet server keeps old number. | Serializer strips null properties (`NON_NULL`); wire request becomes `{}`. | Log/test the **serialized JSON**, not just the DTO before the HTTP call. |
| Producer test only checks missing case, skips null case. | Only one contract exists or plugin didn't load all contracts. | Check generated test count, test names, test report, and contract paths. |
| Stub always returns the same response for both bodies. | Overly broad body matcher, overlapping mappings, or missing distinguishing condition. | Inspect mappings inside `stubs` JAR and run the request matrix from section 10. |
| YAML `phone: "null"` causes producer to receive a string. | Quotes were placed around `null`. | Use unquoted `phone: null` or JSON with unquoted `null`. |
| `Map.of("phone", null)` throws in consumer test. | `Map.of` forbids null values. | Use `ObjectNode.putNull` or `HashMap` with `containsKey`. |
| Response `phone: null` turns into a body lacking `phone`. | Serializer strips Java null values. | Use `NullNode`/proper serialization config and assert field presence. |
| Consumer test passes locally yet fails in CI. | CI uses a different stub version, unpublished artifact, or wrong repo/credentials. | Pin version, check `stubs` classifier, repo access, and generated mapping. |
| Editing only the stub to make tests pass after a change. | Contract, producer, and stub diverge from a single source of truth. | Put changes in the contract, re-run generated producer tests, then publish new stubs. |

When an error occurs, trace step by step: **actual JSON sent → post-deserialization representation in producer → contract loaded by plugin → generated producer test → stub mapping → consumer assertions**. This path pinpoints where the missing/null distinction was lost.

## 13. Bringing Missing/Null Cases into CI Without Breaking Compatibility

A helpful pipeline should ensure:

1. **Producer CI** loads all contracts for absent and null cases, generates tests, runs them against producer code, and verifies status and bodies containing null fields as committed.
2. Only when producer verification passes does the build **package and publish** the `stubs` artifact with a traceable version.
3. **Consumer CI** runs Stub Runner with the chosen stub version, invokes real client code, and asserts both cases; include negative tests for `""`, string `"null"`, or extra fields when strict separation is needed.
4. Treat an API change from "null means keep" to "null means clear" as a **potentially breaking** behavioral change. Identify consumers relying on the old rule and plan a migration instead of merely updating contracts to match the new producer.
5. Never treat green generated producer tests against a **brand-new rewritten contract suite** as automatic proof of backward compatibility with older consumers; keep verifying active contracts or supported consumers.

If a project uses messaging instead of HTTP, the principle **missing key differs from JSON null key** still applies to JSON message payloads, yet trigger/verification setup, brokers, and messaging Stub Runner differ from HTTP WireMock; do not blindly copy `PATCH` setup into messaging flows.

## 14. Hands-On Exercise: Catching a Bug That Appears Only When Sending Null

On a Spring Boot project configured with Spring Cloud Contract Verifier and a consumer with Stub Runner:

1. **Create two contracts** as in section 4 (or two YAML files as in section 5) for the same endpoint `PATCH /api/customers/42`, with bodies `{}` and `{"phone":null}` respectively.
2. **Write the producer controller** using `JsonNode.has` and `isNull`; run generated producer tests and confirm **both scenarios actually execute** and PASS.
3. **Introduce an intentional bug:** change `!input.has("phone")` to `!input.hasNonNull("phone")` in the controller. Re-run producer tests and record which test fails and how the actual response differs from expectations.
4. **Revert** the controller, build the stub artifact, and use Stub Runner to run consumer tests with `ObjectNode.createObjectNode()` and `putNull("phone")`.
5. **Test negative cases:** send `{"phone":""}` and `{"phone":"null"}`; observe whether the stub matches any mapping unexpectedly. If so, inspect the generated body matcher, refine the contract/matcher config, and re-verify both sides.
6. **Test consumer serializer:** use a DTO with `phone=null` and enable null-stripping mode, then inspect the actual body sent. Explain why `putNull` or a three-state type is required if null means "clear."
7. **Harden CI:** pin stub versions, run producer tests before publishing, and run consumer tests with both requests; describe the impact if the team changes the meaning of `null` in a new API version.

The expected outcome is more than a green build. You should **demonstrate using JSON on the wire** which field is absent and which truly carries `null`; **point out in producer code** the distinguishing condition; and **prove through tests** that neither the stub nor the consumer conflates the two requests.

## 15. Self-Check Questions

- Given `{}` and `{"phone":null}`, can `node.get("phone") == null` distinguish them? Why or why not?
- With Jackson `JsonNode`, how does `has` differ from `hasNonNull`?
- If a consumer uses `@JsonInclude(NON_NULL)`, what might an intended `{"phone":null}` request turn into on the wire?
- Why must two contracts sharing method, URL, and `Content-Type` have tight enough request body matchers to tell them apart?
- In YAML, how does `phone: null` differ from `phone: "null"`?
- If producer tests pass yet the consumer stub returns the same response for both bodies, which artifact should you inspect first?
- Why is a test asserting only HTTP 200 in both scenarios insufficient?
- If a new contract defines `null` as "clear," what must you do to protect consumers interpreting `null` under the old rule?

**Remember:** **an absent field** and **a field present with JSON null** differ in both data and business meaning. In Spring Cloud Contract, write request contracts expressing both scenarios clearly, use producer code that preserves key presence, verify generated producer tests, inspect stub body matchers, and run consumer tests through Stub Runner. Whenever any step drops the missing/null distinction, CI must have enough scenarios and assertions to catch it before an API change is released.

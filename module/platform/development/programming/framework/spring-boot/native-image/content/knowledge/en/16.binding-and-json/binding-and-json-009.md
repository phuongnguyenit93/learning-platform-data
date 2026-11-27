# Testing JSON, Validation, and Configuration with Identical Data on JVM and Native

## 1. Goal: Comparing the Same Contract Across Two Runtimes

When migrating a Spring Boot application to GraalVM Native Image, an HTTP request can pass through multiple layers: receiving JSON, deserializing into a DTO, binding configuration, validating data, executing business logic, and serializing the response. On the JVM, reflection and metadata can be discovered dynamically at runtime. With Native Image, Spring AOT and reachability analysis prepare part of the required structure and metadata ahead of time.

Therefore, an endpoint returning correct results on the JVM is not enough to prove it behaves identically in a native executable. Differences can emerge in constructor binding, Jackson creator/property discovery, polymorphic JSON, custom serializers, validation providers, message interpolation, or configuration loaded from the environment.

In the **SPRING_BOOT_NATIVE_IMAGE** module, this lesson establishes a testing methodology to run **the same dataset and the same contract** on both builds:

- JVM build: executable Spring Boot JAR run via `java -jar`.
- Native build: executable created via Spring AOT and GraalVM Native Image.

The objective is reproducible functional and data comparison. Startup/RSS metrics can be measured afterward, but first both builds must process identical inputs and produce equivalent results according to the defined contract.

## 2. What Must Be Kept Identical in the Test?

For results to be meaningful, fix the following factors:

| Factor | Requirement Between JVM and Native |
|---|---|
| Source code | Same recorded Git commit or revision |
| Spring Boot/dependencies | Same versions and dependency graph |
| Test fixtures | Same valid JSON, invalid JSON, and configuration files |
| Spring profiles | Same logical profiles; record any structural profile used during AOT |
| Runtime properties | Same endpoints, timeouts, limits, and feature flags |
| External files | Same file contents, equivalent mount paths |
| Locale/timezone | Same settings if affecting JSON, dates, or messages |
| Database/fixtures | Same schema and test data if endpoints involve persistence |
| HTTP contract | Same method, URL, headers, body, and expected status |
| Resource limits | Same CPU/RAM/container constraints when measuring performance |

You do not need the exact same process startup command, since one runs on the JVM and the other runs as a native executable. What must stay identical are **the inputs and observation conditions**. Document any mandatory differences such as JVM flags, native build args, and runtime images.

## 3. Defining the JSON Contract Before Writing Tests

Suppose an order creation endpoint accepts the request:

```json
{
  "customerId": "C-1001",
  "quantity": 2,
  "unitPrice": 125000,
  "delivery": {
    "city": "Da Nang",
    "express": true
  }
}
```

Response contract:

```json
{
  "orderId": "ORD-1001",
  "total": 250000,
  "status": "ACCEPTED"
}
```

The contract should clearly specify:

- Required fields and optional fields.
- Data types, numeric bounds, and null/blank rules.
- How unknown fields (unknown properties) are handled.
- Enums, dates/times, decimals, and timezones.
- Status codes and error response structures.
- Whether response fields are deterministic or contain randomly generated values.

Do not compare raw JSON text verbatim if key order is not part of the contract. Parse JSON and compare structures/values instead. If fields contain timestamps or auto-generated IDs, use a controllable clock/ID provider or compare according to defined rules.

## 4. Creating Unified DTOs and Validation

DTO example using records and Jakarta Bean Validation:

```java
public record CreateOrderRequest(
        @NotBlank String customerId,
        @Min(1) @Max(100) int quantity,
        @Positive BigDecimal unitPrice,
        @Valid @NotNull Delivery delivery) {

    public record Delivery(
            @NotBlank String city,
            boolean express) {
    }
}
```

Controller:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {

        BigDecimal total = request.unitPrice()
                .multiply(BigDecimal.valueOf(request.quantity()));

        return ResponseEntity.ok(
                new OrderResponse("ORD-1001", total, "ACCEPTED"));
    }
}
```

The example needs imports from `jakarta.validation.constraints`, `jakarta.validation.Valid`, `BigDecimal`, and Spring Web APIs. The project must include a validation implementation, typically via `spring-boot-starter-validation`. Without a provider, annotations may not be enforced as expected.

`@Valid` on the nested property cascades validation into `Delivery`. `@NotNull` ensures the child object is non-null; `@NotBlank` checks that the string is not null, not empty, and not whitespace-only.

Response definition:

```java
public record OrderResponse(
        String orderId,
        BigDecimal total,
        String status) {
}
```

When testing both runtimes, use the same DTOs, converters, validation provider, and Jackson configuration. If the application uses a custom `ObjectMapper` or custom modules, ensure that configuration applies to both.

## 5. Designing a Shared Test Dataset

Fixtures should be stored in the repository, for example:

```text
src/test/resources/contract/orders/
├── valid-order.json
├── invalid-blank-customer.json
├── invalid-zero-quantity.json
├── invalid-null-delivery.json
├── invalid-negative-price.json
├── unknown-field.json
└── malformed-json.json
```

Each file is an independent input used by both JVM tests and native tests. Do not maintain two nearly identical fixture copies per runtime, as they can drift over time.

Example `valid-order.json`:

```json
{
  "customerId": "C-1001",
  "quantity": 2,
  "unitPrice": 125000.00,
  "delivery": {
    "city": "Da Nang",
    "express": true
  }
}
```

Example `invalid-zero-quantity.json`:

```json
{
  "customerId": "C-1001",
  "quantity": 0,
  "unitPrice": 125000,
  "delivery": {
    "city": "Da Nang",
    "express": false
  }
}
```

Alongside fixtures, record expected outcomes: HTTP status, JSON response, or error category. You can use JSON snapshots or test assertions; avoid depending on stack traces or internal messages outside the public contract.

## 6. Testing JSON Binding in JVM Tests

With Spring MVC, `MockMvc` verifies request mapping, JSON conversion, and validation inside a test ApplicationContext:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderContractTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsValidOrder() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerId": "C-1001",
                      "quantity": 2,
                      "unitPrice": 125000,
                      "delivery": {
                        "city": "Da Nang",
                        "express": true
                      }
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orderId").value("ORD-1001"))
            .andExpect(jsonPath("$.total").value(250000))
            .andExpect(jsonPath("$.status").value("ACCEPTED"));
    }
}
```

The example requires static imports for `MockMvc` request/result matchers and Spring test APIs. If using a Java version without text blocks, substitute appropriate string literals.

`MockMvc` runs the MVC pipeline in a test context without opening a real HTTP server. It is very useful for checking binding and validation; to verify the packaged executable runs properly, add black-box HTTP tests against the real JVM and native processes.

## 7. Testing Validation and the Error Contract

Do not test only valid requests. Test each error category:

| Fixture | What to Verify |
|---|---|
| Blank customer ID | `@NotBlank` is enforced |
| Quantity equal to 0 | `@Min(1)` is enforced |
| Quantity over 100 | `@Max(100)` is enforced |
| Null delivery | `@NotNull` is enforced |
| Whitespace-only city | Nested validation via `@Valid` works |
| Malformed JSON | HTTP 400 per error contract |
| Wrong data type | Deserialization fails per contract |
| Unknown field | Outcome matches unknown-property configuration |

Status check example:

```java
@Test
void rejectsZeroQuantity() throws Exception {
    mvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "customerId": "C-1001",
                  "quantity": 0,
                  "unitPrice": 1000,
                  "delivery": {
                    "city": "Da Nang",
                    "express": false
                  }
                }
                """))
        .andExpect(status().isBadRequest());
}
```

Error body formats may vary depending on the Spring Boot version, Problem Details configuration, and exception handlers. If error bodies are part of the public API, standardize them via `@ControllerAdvice` or Problem Details and assert key schemas/fields. Avoid verbatim comparisons of validation messages when messages depend on locale or provider.

## 8. Verifying Configuration with Identical Property Sources

JSON binding might succeed while the application still behaves differently due to differing configuration. For example:

```yaml
orders:
  max-items: 100
  default-currency: VND
  client:
    timeout: 2s
```

Properties class:

```java
@ConfigurationProperties(prefix = "orders")
@Validated
public record OrdersProperties(
        @Min(1) int maxItems,
        @NotBlank String defaultCurrency,
        @Valid Client client) {

    public record Client(
            @NotNull Duration timeout) {
    }
}
```

Register via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. Both JVM and native need identical configuration values. You can place shared config fixtures in test resources or pass identical environment variables when launching processes.

Distinguish structural properties from runtime values. If `orders.max-items` is only read by a service when processing requests, it can be changed at runtime. If a property is used in `@ConditionalOnProperty` to decide bean registration, the value used during AOT at build time may already have fixed the context structure. You cannot simply change container environment variables and expect a bean excluded at build time to appear.

## 9. Testing Runtime Configuration with Environment Variables and Files

You can launch the process with the same set of environment variables:

```bash
ORDERS_MAX_ITEMS=100 \
ORDERS_DEFAULT_CURRENCY=VND \
ORDERS_CLIENT_TIMEOUT=2s \
java -jar target/orders-service.jar
```

And native:

```bash
ORDERS_MAX_ITEMS=100 \
ORDERS_DEFAULT_CURRENCY=VND \
ORDERS_CLIENT_TIMEOUT=2s \
./orders-service
```

Both commands must run in environments with the same property sources and external dependencies. If using configuration files, mount identical contents at identical paths or pass them via `SPRING_CONFIG_ADDITIONAL_LOCATION` for both processes.

To avoid shell discrepancies, use a shared launch script or a controlled environment file. Do not put real credentials in test fixtures. Use dummy test secrets and keep the secret-provisioning mechanism consistent across both runtimes.

## 10. Testing Special Serialization and Deserialization

Advanced JSON cases easily expose native differences:

- Records and constructor-based DTOs.
- Immutable objects with custom creators.
- Polymorphic types via `@JsonTypeInfo`.
- Enums and custom enum deserializers.
- `LocalDate`, `Instant`, `OffsetDateTime`, and timezones.
- `BigDecimal`, precision/scale, and very large numbers.
- `Optional`, nested collections, and generic wrappers.
- Custom serializers/deserializers, mix-ins, and naming strategies.
- Private fields accessed by the mapper via reflection.

Polymorphic DTO example:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        property = "kind")
@JsonSubTypes({
        @JsonSubTypes.Type(
                value = CardPayment.class,
                name = "card"),
        @JsonSubTypes.Type(
                value = BankTransfer.class,
                name = "bank")
})
public sealed interface PaymentMethod
        permits CardPayment, BankTransfer {
}
```

In a native image, required subtypes and members must be recognized by the framework or metadata. Spring AOT and Jackson integrations handle many common cases, yet custom polymorphic types or custom reflection must be tested specifically. Do not add broad hints before pinpointing the exact missing path.

## 11. Comparing JSON Structurally, Not by Arbitrary Strings

JSON objects do not assign meaning based on key order. Thus, responses:

```json
{"orderId":"ORD-1001","status":"ACCEPTED","total":250000}
```

and:

```json
{"total":250000,"orderId":"ORD-1001","status":"ACCEPTED"}
```

have identical data structures. Verbatim string comparison can cause false failures due to field ordering, whitespace, or number formatting.

Prefer:

- JSONPath assertions for key fields.
- Parsing JSON into a tree and comparing structures.
- JSON schema validation if the contract is defined by a schema.
- Comparing numeric values according to required semantics, noting `250000` and `250000.00` may be formatted differently.
- Normalizing timestamps/IDs using a controllable clock or generator in tests.

If array order is significant, preserve order and compare strictly. If an array represents an unordered set per contract, normalize before comparing.

## 12. Running Identical Fixtures on JVM and Native with HTTP Contract Tests

`MockMvc` does not replace testing a real process. One approach is building a test runner that sends identical fixtures to a base URL. Shell example:

```bash
curl -sS -i \
  -H "Content-Type: application/json" \
  --data-binary @src/test/resources/contract/orders/valid-order.json \
  http://localhost:8080/api/orders
```

Start the JVM process first, send the fixtures, save responses; stop the process, then start the native executable with the same configuration and resend the fixtures. Use a shared test script to avoid diverging copy/pasted requests.

In CI, you can:

1. Build the executable JAR and start the JVM process.
2. Wait for the readiness endpoint or test endpoint to respond.
3. Run all HTTP contract fixtures.
4. Stop the JVM process.
5. Build and start the native executable.
6. Wait for readiness using the same timeout policy.
7. Re-run the exact same fixtures and compare status/JSON contracts.
8. Stop the process and archive logs/artifacts on failure.

If using an Actuator readiness endpoint, add the dependency and expose the corresponding endpoint. Otherwise, use a dedicated health/test endpoint. Do not use a fixed sleep interval as proof that a process is ready.

## 13. Native Tests in Maven/Gradle and Limitations of Each Test Layer

Depending on plugins and versions, a project may support a native test task or native integration test workflow. For example, the task may be `nativeTest` in a GraalVM Native Build Tools Gradle setup, though you must verify the task exists in your project.

Testing layers complement one another:

| Test Layer | What It Verifies | Limitation |
|---|---|---|
| DTO/mapper unit test | Isolated mapping and conversion logic | Does not boot the full Spring context |
| Spring Boot integration test on JVM | Binding, MVC, validation, bean wiring | Runs on the JVM |
| RuntimeHints test | Registrar declares expected metadata | Does not prove the final binary works |
| Native test task | Tests executed in native mode per plugin support | Scope depends on task/configuration |
| Black-box HTTP test on executable | Native process, HTTP stack, and contract | Requires an environment capable of running the binary |
| Container integration test | Runtime image, config mounts, user, libraries | Slower and requires image build |

Never treat a successful build as a substitute for black-box testing. An executable may compile cleanly yet fail when deserializing an infrequent subtype or reading a resource/configuration inside a runtime container.

## 14. Ensuring the Exact Same Data Is Actually Used

A common mistake is JVM tests reading fixtures from `src/test/resources`, while native tests accidentally use different hardcoded payloads. To prevent this:

- Store fixtures in one canonical location in the repository.
- Read fixtures using the same helper or script.
- Do not create separate payloads inside an `if (native)` branch.
- Record fixture checksums in reports if traceability is needed.
- Explicitly record config files, profiles, and environment variables.
- Use deterministic clocks, IDs, or seeds when responses include generated values.
- Reset database and test state between runs.

If the application produces side effects such as creating orders, publishing messages, or calling external services, use test doubles or sandboxes with resettable state. Ensure test ordering does not make one run's results depend on a previous run.

## 15. Recommended Test Matrix

| Category | Data | Expectation |
|---|---|---|
| Valid JSON | Complete request | HTTP 2xx, matching response schema |
| Optional fields | Omit optional fields | Contract-defined defaults |
| Required fields | Omit `customerId` | HTTP 400 |
| Null nested object | `delivery = null` | HTTP 400 |
| Nested validation | Blank `city` | HTTP 400 |
| Numeric boundaries | `quantity = 1` and `100` | Accepted |
| Numeric out of range | `quantity = 0` and `101` | HTTP 400 |
| JSON syntax | Invalid comma/quotes | HTTP 400 |
| Type mismatch | `quantity` as an unconvertible string | HTTP 400 |
| Unknown field | Add undeclared field | Matches Jackson configuration |
| Polymorphic JSON | Each valid subtype | Deserializes to right subtype |
| Date/time | Timestamp with offset | Identical semantics/timezone |
| Configuration | Timeout, currency, max-items | Identical bound values |
| External config | Identical mounted file | Identical behavior |
| Validation messages | Identical locale | Identical normalized error contract |

Run the matrix on both JVM and native. For cases requiring different structural profiles, identify the corresponding native artifact for each profile before running.

## 16. Analyzing Discrepancies Between JVM and Native

When a test fails only on native, investigate in order:

1. **Compare actual requests:** confirm identical body, headers, content type, and properties.
2. **Compare configuration:** active profiles, property sources, locale, timezone, mounted files, and environment.
3. **Identify failing layer:** JSON parsing, object instantiation, validation, service logic, or response serialization.
4. **Read root exception:** distinguish Jackson mapping errors, validation errors, missing reflection metadata, missing resources, and configuration errors.
5. **Inspect AOT/native metadata:** check whether subtypes, constructors, methods, fields, or resources were recognized.
6. **Minimal reproduction:** isolate one fixture and one failing path, then add metadata or adjust configuration.
7. **Re-run all fixtures:** verify fixing one case does not break another.

Do not conclude every native JSON failure is caused by reflection. Causes can include differing properties, locale, dependency versions, custom serializers, date/time formats, or non-equivalent test data.

## 17. Reporting Results and Measuring Performance After Contracts Pass

Once functional parity is established, you can measure startup/readiness and memory. Do not mix functional failures with performance metrics.

Sample report table:

| Metric | JVM | Native |
|---|---|---|
| Commit and dependency versions | Record | Same revision |
| Test fixtures pass/total | Record | Record |
| JSON response contract | PASS/FAIL | PASS/FAIL |
| Validation outcomes | PASS/FAIL | PASS/FAIL |
| Configuration values | Record | Record |
| Startup to readiness | Measure multiple runs | Measure multiple runs |
| Idle RSS | Measure | Measure |
| Loaded RSS | Measure | Measure |
| Throughput/latency | Measure if needed | Measure if needed |

Measure under identical CPU/RAM limits, datasets, concurrency, request rates, and measurement methodology. For the JVM, record heap flags and warm-up duration; native does not share the same JIT warm-up behavior. Report run counts, medians/distributions, and timestamps so others can reproduce results.

A native image that consumes less RAM because it dropped a subtype or skipped loading a required resource is a functional defect, not a valid optimization.

## 18. Lab Exercise: One Contract Suite for Both Runtimes

**Context:** an Order API service accepts JSON, validates nested `Delivery`, binds order-limit configuration, and returns a JSON response.

**Step 1 — Standardize DTOs.** Create request/response records and nested validation annotations.

**Step 2 — Standardize configuration.** Create `OrdersProperties` with `@ConfigurationProperties`, constructor binding, and validation; register it in the ApplicationContext.

**Step 3 — Create fixtures.** Store valid, invalid, malformed, unknown-field, and boundary JSON cases in one shared test directory.

**Step 4 — Write JVM integration tests.** Use `MockMvc` to verify JSON binding, validation, and the response contract.

**Step 5 — Run the JVM process.** Send the same fixtures over HTTP to the executable JAR; save status codes and JSON responses.

**Step 6 — Build native.** Run Spring AOT and Native Image; run registrar/hints tests if the app has custom JSON or reflection behavior.

**Step 7 — Run the native process.** Send the exact same fixtures and runtime properties; compare status codes, JSON trees, and error contracts.

**Step 8 — Run in a container.** Mount identical external config, configure equivalent locale/timezone and user; repeat contract tests.

**Step 9 — Record results.** Document revision, toolchain, fixture checksums, test pass/fail, startup/readiness, and RSS.

Completion criteria: the identical fixture suite runs on both runtimes; JSON binding, validation, nested data, and configuration produce contract-equivalent results; all discrepancies have identified root causes; and the native executable is verified inside the target runtime container.

## 19. Conclusion

Testing Spring Boot Native Image requires **identical data, identical contracts, and equivalent configuration** across JVM and native. The test suite must cover JSON serialization/deserialization, nested DTOs, constructor binding, validation, runtime configuration, external files, and boundary data cases. `MockMvc` and unit tests are useful for validating logic; black-box HTTP tests on executables and containers verify actual deployment behavior.

When discrepancies appear, pinpoint the failing layer before adding `RuntimeHints` or changing configuration. Only after both builds satisfy the same contract should you compare startup, RSS, and throughput. This approach evaluates Native Image based on functional equivalence rather than relying solely on a successful build or a few smoke requests.

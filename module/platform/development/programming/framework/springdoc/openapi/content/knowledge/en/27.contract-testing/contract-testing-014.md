# Limits of Contract Testing Without Business-Rule Verification

Contract testing confirms that two components communicate according to an agreed interface: requests have the structure the provider accepts, and responses have the status codes, headers, media types, and bodies consumers expect. With Spring Boot, springdoc-openapi generates OpenAPI contracts from controllers, DTOs, and annotations; `MockMvc` or `WebTestClient` tests HTTP endpoints; and Pact or Spring Cloud Contract verify expectations between consumers and providers.

However, an API can return the right HTTP `201`, the right JSON schema, and the right field names while still miscalculating totals, deducting inventory twice, allowing illegal state transitions, or processing duplicate transactions. Those defects live in business rules. With contract tests alone, pipelines can stay green while the system makes wrong business decisions.

This lesson distinguishes the scopes of contract tests and business-rule tests, highlights common blind spots, and outlines a layered testing strategy that keeps API contracts stable while safeguarding domain behavior.

## 1. What Questions Does an API Contract Answer?

A contract describes how one component communicates with another. For HTTP APIs, contracts typically define:

- Paths and HTTP methods.
- Path parameters, query parameters, headers, and request bodies.
- Data types, formats, `required`, `nullable`, ranges, and patterns.
- Status codes, response headers, media types, and response bodies.
- Published authentication schemes, scopes, and access requirements.
- Error shapes consumers must handle.

For example, the contract for `POST /api/orders` might specify:

| Element | Contract |
| --- | --- |
| Method/path | `POST /api/orders` |
| Request | `productId` is a string; `quantity` is an integer greater than `0` |
| Success | `201 Created` with `OrderResponse` body |
| Missing or invalid data | `400 Bad Request` |
| Insufficient stock | `409 Conflict` |
| Media type | `application/json` |

springdoc-openapi generates this description from controllers, DTOs, validation annotations, and OpenAPI annotations. It keeps documentation aligned with declared mappings, yet generating a valid spec does not prove the implementation enforces business rules correctly.

## 2. Three Test Types Often Grouped as "Contract Testing"

In practice, "contract testing" is used for distinct goals. Distinguish them to understand what a green build proves.

| Check Type | What It Confirms | What It Leaves Unproven |
| --- | --- | --- |
| OpenAPI document validation | JSON/YAML is valid for the OpenAPI version, with parseable schemas and operations | Whether the live app returns accurate responses or executes business logic properly |
| Provider contract tests | Live provider endpoints match published statuses, headers, and bodies | Whether all business rules, data states, and multi-step workflows are correct |
| Consumer-driven contract tests | Provider satisfies specific requests that a consumer depends on | Whether all business behavior or other consumers' expectations hold |
| Business-rule tests | Business decision logic and data transformations meet domain requirements | Whether HTTP, proxies, and external systems integrate properly |

Pact describes integration-level contract testing as verifying each application independently to ensure messages sent/received match agreements between consumer and provider. A Pact typically captures concrete requests/responses a consumer needs. Spring Cloud Contract likewise focuses on inter-application contracts and explicitly notes contracts are not meant to model complete business logic.

Before trusting a CI pass, always ask which layer the test actually covers.

## 3. An Example: Right Response Shape, Wrong Total Amount

Suppose an API accepts:

~~~json
{
  "productId": "SKU-100",
  "quantity": 2,
  "couponCode": "SAVE10"
}
~~~

The contract specifies the response:

~~~json
{
  "orderId": "ORD-10482",
  "status": "CONFIRMED",
  "total": 180.00,
  "currency": "VND"
}
~~~

A `MockMvc` test might check only:

- Request accepted with valid JSON.
- Server returns `201 Created`.
- Body includes `orderId`, `status`, `total`, and `currency`.
- `total` is a number and `currency` is a string.

If the implementation computes `200.00` instead of `180.00`, a test checking only field existence and types stays green. The JSON satisfies the schema completely while the business outcome is wrong.

Similar examples:

| Faulty Behavior | Why Basic Contract Tests Still Pass |
| --- | --- |
| 10% coupon applied as 0% | Response still has numeric `total` |
| Inventory deducted twice | Response is still `201` matching the schema |
| Delivered order allowed to cancel | Status and body still match expected structure |
| Shipping fee calculated for wrong region | `shippingFee` is still a valid decimal |
| Duplicate idempotency key creates two orders | Both responses match the schema |
| User reads another tenant's order | Response has a valid shape yet leaks data |
| Status saved as `PAID` before payment succeeds | Response shape is fine while persisted state is wrong |

Schemas express types and structural constraints. They do not capture pricing formulas, temporal rules, data ownership, or transaction ordering.

## 4. What Do springdoc and OpenAPI Verify?

With springdoc-openapi, you can verify:

1. Expected controllers and functional routes appear in the OpenAPI document.
2. HTTP methods, paths, `operationId`, and tags are accurate.
3. Request/response schemas have expected types, fields, formats, and `required` flags.
4. Response statuses and media types are thoroughly documented.
5. Security schemes and scopes appear on protected operations.
6. Examples conform to schemas without leaking real data.
7. The OpenAPI document is valid for its configured specification version.

You can test generated docs at `/v3/api-docs` or the YAML endpoint, archive artifacts, and run contract diffs in CI.

Document check via `MockMvc`:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiDocumentTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesCreateOrderOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/orders'].post").exists());
    }
}
~~~

This test confirms the docs endpoint works and the expected operation appears. It does not prove an actual create-order request returns a schema-compliant response; add a dedicated HTTP contract test for that operation. Also note that checking a single path/method will not catch other missing operations.

## 5. Checking HTTP Contracts with `MockMvc`

`MockMvc` suits Spring MVC when testing requests/responses at the web layer without opening an HTTP port. Spring Boot supports `@WebMvcTest` for web-layer slices or `@SpringBootTest` with `@AutoConfigureMockMvc` for wider application contexts.

Controller example:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse response = orderService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
~~~

Request DTO example:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateOrderRequest(
    @NotBlank String productId,
    @Min(1) @Max(100) int quantity,
    String couponCode
) {
}
~~~

HTTP-layer contract test:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderControllerContractTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void createsOrderUsingExpectedHttpContract() throws Exception {
        given(orderService.create(any()))
            .willReturn(new OrderResponse(
                "ORD-10482",
                "CONFIRMED",
                new BigDecimal("180.00"),
                "VND"
            ));

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "productId": "SKU-100",
                      "quantity": 2,
                      "couponCode": "SAVE10"
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.orderId").value("ORD-10482"))
            .andExpect(jsonPath("$.status").value("CONFIRMED"))
            .andExpect(jsonPath("$.total").value(180.00))
            .andExpect(jsonPath("$.currency").value("VND"));
    }
}
~~~

This test verifies the controller calls the service and maps the response to the HTTP contract. Because `OrderService` is mocked, it does not prove the service calculates coupons, prices, or inventory accurately. That is an intentional boundary of web-layer tests.

The `jsonPath` assertions here manually check selected fields; they are not an exhaustive OpenAPI schema validator. To validate full responses against the document, integrate an OpenAPI response validator into the test client using the application's matching document version. Even then, schema conformance still does not prove pricing formulas or workflows are right.

On newer Spring Boot versions that migrated to `@MockitoBean`, replace `@MockBean` accordingly. Pick annotations matching your project's Spring Boot release.

## 6. Request Validation Is Also Not Full Business Validation

Bean Validation enforces simple constraints such as:

- Required fields must not be blank.
- Quantities fall within bounds.
- Email syntax is valid.
- Strings stay within max length.
- Dates match valid formats.

Example:

~~~java
@Test
void rejectsQuantityOutsideDeclaredRange() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "productId": "SKU-100",
                  "quantity": 0
                }
                """))
        .andExpect(status().isBadRequest());
}
~~~

This test confirms `quantity >= 1` is enforced at the HTTP boundary. Yet it cannot verify cross-field or stateful rules:

- Is the product currently on sale at order time?
- Does the customer have sufficient credit limit?
- Is the coupon still active and applicable to this product?
- Does the order total exceed transaction limits?
- Does requested quantity exceed available stock after reservations for other orders?

Those rules require service/domain tests or integration tests with appropriate persisted state.

## 7. Writing Business-Rule Tests for Services and Domains

Business rules belong under test wherever decisions are made. Pure logic like pricing can use fast unit tests without a Spring context.

Pricing service example:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

class OrderPricing {

    BigDecimal calculate(
            BigDecimal unitPrice,
            int quantity,
            BigDecimal discountPercent) {

        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid unit price");
        }
        if (discountPercent.signum() < 0
                || discountPercent.compareTo(new BigDecimal("100")) > 0) {
            throw new IllegalArgumentException("Invalid discount");
        }

        BigDecimal subtotal = unitPrice.multiply(
            BigDecimal.valueOf(quantity));
        BigDecimal discount = subtotal
            .multiply(discountPercent)
            .divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);

        return subtotal.subtract(discount)
            .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

Rule tests:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderPricingTest {

    private final OrderPricing pricing = new OrderPricing();

    @Test
    void appliesTenPercentDiscountToSubtotal() {
        BigDecimal total = pricing.calculate(
            new BigDecimal("100.00"),
            2,
            new BigDecimal("10")
        );

        assertThat(total).isEqualByComparingTo("180.00");
    }

    @Test
    void rejectsQuantityAboveBusinessLimit() {
        assertThatThrownBy(() -> pricing.calculate(
            new BigDecimal("100.00"),
            101,
            new BigDecimal("0")
        )).isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

These unit tests verify the formula and business limits. They complement `MockMvc` tests: one checks HTTP responses, the other checks pricing decisions.

Never test only one happy example. Cover boundary values: min/max quantities, 0%/100% discounts, fractional amounts, rounding, negative prices, unsupported currencies, and expired coupons.

## 8. Testing State Transition Rules

A schema may declare `status` as enum `PENDING`, `CONFIRMED`, `SHIPPED`, `CANCELLED`. That schema cannot express which transitions are legal.

Example transition rules:

| Current State | Command | New State | Outcome |
| --- | --- | --- | --- |
| `PENDING` | `confirm` | `CONFIRMED` | Allowed |
| `CONFIRMED` | `ship` | `SHIPPED` | Allowed when stock is reserved |
| `PENDING` | `cancel` | `CANCELLED` | Allowed |
| `SHIPPED` | `cancel` | `CANCELLED` | Rejected |
| `CANCELLED` | `confirm` | `CONFIRMED` | Rejected |

Domain tests should verify both valid and invalid transitions:

~~~java
@Test
void cannotCancelShippedOrder() {
    Order order = Order.shipped("ORD-10482");

    assertThatThrownBy(order::cancel)
        .isInstanceOf(InvalidOrderTransitionException.class);

    assertThat(order.getStatus()).isEqualTo(OrderStatus.SHIPPED);
}
~~~

Contract tests can verify that rejections return `409 Conflict` with a stable error schema. Business-rule tests verify `cancel` leaves state unchanged and avoids erroneously restocking inventory.

## 9. Database-Dependent Rules Require Integration Tests

Not every rule can be checked by pure unit tests. Some decisions depend on transactions, database constraints, locks, or concurrent state.

Inventory reservation example:

1. Current stock is `5`.
2. Two concurrent requests each order `4` items.
3. Only one request succeeds in reserving stock.
4. Remaining stock never goes negative.
5. The second request receives a business error mapped to the published error response.

Unit tests with mocked repositories can verify the service calls `reserve(4)`, yet cannot prove atomic SQL updates or transaction isolation behave properly. You need integration tests against a real database, typically via Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class InventoryReservationIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    // Boot the application with datasource pointing to the container,
    // seed inventory = 5, then send two concurrent reserve(4)
    // calls and verify only one succeeds.
}
~~~

This snippet sketches the test setup; datasource wiring and thread synchronization must be filled in for your application. What matters is using the same database engine deployed in production to verify constraints, locks, and transactions.

## 10. Testing Idempotency and Side Effects

An API may declare an `Idempotency-Key` header in OpenAPI. Neither the schema nor the response guarantees the server enforces idempotency.

Business/integration tests should verify:

- Repeating the same key and payload does not create extra orders or charges.
- Repeating the same key with a different payload is rejected per policy.
- Retrying after a timeout returns the stored outcome instead of duplicating side effects.
- Outbox/event records are written once per transaction.
- When downstream services fail, state and retryability follow policy.

Contract tests can verify the header is accepted and duplicate responses match agreed statuses/bodies. Integration tests confirm database row counts, payment gateway call counts, and emitted events.

## 11. Consumer-Driven Contract Tests Verify Consumer Expectations

Pact and Spring Cloud Contract shine when separate teams build multiple services. Consumers record the interactions they actually rely on; providers run verification to prove responses satisfy those interactions.

For example, `shipping-service` might only need:

~~~http
GET /api/orders/ORD-10482
Accept: application/json
~~~

And minimally expect:

~~~json
{
  "orderId": "ORD-10482",
  "status": "CONFIRMED"
}
~~~

Pact provider verification replays the request and checks that the response satisfies the contract. This catches providers renaming fields or changing statuses a consumer uses.

Because the consumer does not use `total`, it never asserts pricing math. The provider could miscalculate totals while Pact stays green. That is not a Pact flaw—it is the intentional scope of the contract.

Provider states prepare preconditions before each interaction, such as ensuring order `ORD-10482` exists in `CONFIRMED` status. Provider states are not a test suite for all state transition rules.

## 12. Spring Cloud Contract Does Not Replace Business Tests Either

Spring Cloud Contract supports producer-driven and consumer-driven contracts, stub generation, and provider testing. Use it to verify:

- Requests conform to contracts.
- Responses carry agreed statuses, headers, and bodies.
- Consumer stubs match provider responses.
- Provider edits do not break published consumer contracts.

Spring Cloud Contract documentation explicitly notes contract tests are not meant to encode full business behavior. For instance, a fraud use case may have many rejection reasons; the contract may cover just one acceptance and one rejection case, while detailed fraud rules live in business tests.

Do not bloat contracts with hundreds of business permutations when the goal is verifying inter-service communication. Keep contracts focused on real integration boundaries.

## 13. Using `WebTestClient` for Spring WebFlux

For WebFlux, `WebTestClient` tests reactive endpoints against either a mock web environment or a live server.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OrderWebFluxContractTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void returnsOrderUsingJsonContract() {
        webTestClient.get()
            .uri("/api/orders/ORD-10482")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.orderId").isEqualTo("ORD-10482")
            .jsonPath("$.status").isEqualTo("CONFIRMED");
    }
}
~~~

This test verifies WebFlux HTTP responses. It still needs separate business tests confirming why the order was confirmed, whether stock was reserved, and whether payment requirements passed.

The `AutoConfigureWebTestClient` import above reflects Spring Boot 3.x packaging. In Spring Boot 4.x, the annotation moved to `org.springframework.boot.webtestclient.autoconfigure`; use the package matching your project's Boot version.

Spring Boot distinguishes mock web environments from `RANDOM_PORT` embedded servers. Mock-based `MockMvc`/`WebTestClient` tests run faster yet miss server/container or proxy behavior. Add live server and infrastructure tests when verifying TLS, compression, servlet containers, network timeouts, or reverse proxies.

## 14. Rules That Schemas Struggle to Express Completely

OpenAPI can describe constraints like `minimum`, `maximum`, `pattern`, `enum`, `required`, `format`, and composition. Yet many rules depend on state or history:

| Rule | Why Business Tests Are Needed |
| --- | --- |
| Coupon usable once per customer | Depends on usage history and transactions |
| Buyer can cancel within 15 minutes | Depends on elapsed time and current status |
| Total equals line items plus tax and fees | Depends on formulas and rounding |
| Users see only their own tenant's data | Depends on identity and ownership |
| Only one concurrent request reserves last stock | Depends on concurrency and database locks |
| Refunds cannot exceed captured amount | Depends on cumulative payment state |
| State transitions follow workflow | Depends on prior state and events |
| Shipping fees vary by region and weight | Depends on rate tables and input data |

You can document parts of these rules in schemas or descriptions, yet descriptions do not enforce rules. You must run tests invoking logic or endpoints with realistic state.

## 15. Test Matrix for an Order-Creation API

A balanced suite can be structured as follows:

| Scenario | OpenAPI/Contract | Business Unit Test | Integration Test |
| --- | --- | --- | --- |
| Missing `productId` | Verify `400` and error schema | Unneeded if handled purely by validation framework | Only if error handler touches DB |
| `quantity < 1` | Verify `400` | Verify bounds if domain also guards it | Optional |
| Valid 10% coupon | Verify request/response shapes | Verify discount formula | Optionally check DB pricing lookup |
| Expired coupon | Verify `422`/`409` and error body | Verify validity window logic | Verify coupon DB data and clock |
| Insufficient stock | Verify `409` and error body | Verify rejection branch | Verify DB update/locking |
| Illegal state transition | Verify error response | Verify state machine | Verify persisted state stays unchanged |
| Replayed idempotency key | Verify retry status/body | Verify key logic | Verify no duplicate rows/events |
| Tenant A user reads Tenant B order | Verify `403`/`404` per policy | Verify authorization rule | Verify tenant-filtered query |
| Two concurrent stock reservations | Verify one success, one conflict | Test contention logic where appropriate | Verify real DB transactions/constraints |

This matrix highlights coverage gaps. You do not have to repeat every scenario at every layer; place each test at the layer that reliably verifies cause and effect.

## 16. Signs a Test Suite Only Checks Surface Form

Review your suite if you notice these symptoms:

- Every controller test mocks all services and only asserts `status().isOk()`.
- No tests cover boundary values or rejection branches.
- No tests verify persisted data state after operations.
- Tests check only that JSON fields exist without asserting meaningful values.
- All database tests mock repositories, even for transaction-sensitive logic.
- No tests verify ownership- or tenant-based authorization.
- No tests cover retries, idempotency, or concurrency on financial/order APIs.
- Contracts are generated from controllers without tests validating runtime responses.
- Consumer contracts cover one consumer yet pipelines treat them as proof for all consumers.

A green test only proves what its assertions actually checked. Never extrapolate coverage from one test layer to another.

## 17. Using Mutation Testing to Catch Weak Assertions

Mutation testing intentionally perturbs implementation code, such as:

- Removing discount subtraction.
- Changing `>` to `>=` in boundary checks.
- Removing ownership checks.
- Always returning `CONFIRMED` regardless of payment status.
- Skipping idempotency key checks.

If tests still pass after a mutation, the suite likely failed to observe that rule or set up the needed state.

Mutation testing does not replace requirements analysis. It measures whether existing tests catch the bugs your team cares about. Target mutations at high-risk business decisions first instead of mutating the entire codebase upfront.

## 18. CI Pipelines Should Verify Multiple Layers

A Spring Boot API pipeline can run in this order:

1. Compile and run unit tests for domain/service rules.
2. Test validation and controller mappings with `MockMvc` or `WebTestClient`.
3. Generate OpenAPI with springdoc and validate the document.
4. Verify key operations, schemas, security metadata, and response definitions.
5. Run provider contract tests or consumer-driven verification.
6. Run integration tests against real databases/brokers or Testcontainers for infrastructure-dependent rules.
7. Run authorization, idempotency, and concurrency tests proportional to risk.
8. Diff the OpenAPI contract against the previous release and review breaking changes.
9. Package artifacts only after all appropriate layers pass.

Not every project needs Pact, Spring Cloud Contract, Testcontainers, and mutation testing simultaneously. Pick tools matching your architecture and risk. A simple internal service may need only OpenAPI validation, `MockMvc`, and domain tests; multi-consumer systems or financial workflows need provider/consumer verification and deeper integration tests.

## 19. Diagnosing Failures When Contract Tests Pass Yet Users Hit Bugs

| Symptom | Where to Investigate Next |
| --- | --- |
| Client parses JSON cleanly yet displays wrong totals | Pricing, tax, discount, and rounding formulas |
| API returns `201` yet order cannot ship | Workflow, inventory, and payment state |
| Consumer contract passes yet production integration fails | Provider states, contract versions, auth, networking, and downstream services |
| Schema matches yet fields are always blank/null | DTO mapping, queries, serialization, and business state |
| User receives another tenant's data | Authorization, repository queries, and isolation |
| Retries create duplicate transactions | Idempotency storage, transactions, and race conditions |
| Mock tests pass yet production DB fails | Constraints, transaction isolation, locking, and migrations |
| `MockMvc` passes yet proxy fails | Embedded server, forwarded headers, TLS, CORS, and timeouts |

Trace layer by layer: did the request hit the right handler, did validation run, what did the service decide, what did the repository persist, and how did the response mapper serialize the result? Use correlation IDs in logs and traces; never log tokens or sensitive personal data just for debugging.

## 20. Test Suite Review Checklist

- [ ] OpenAPI document parses cleanly and includes expected operations.
- [ ] Request/response statuses, media types, headers, and schemas are verified.
- [ ] Malformed requests and validation failures are tested.
- [ ] Controller tests with mocked services are not mistaken for business tests.
- [ ] Every key business rule has dedicated domain/service tests.
- [ ] Boundary values, rejection branches, and state transitions are tested.
- [ ] Database-dependent rules are covered by appropriate integration tests.
- [ ] Access control and tenant isolation have negative tests.
- [ ] Retries, idempotency, and concurrency are tested where business requires.
- [ ] Consumer contracts are verified on the provider.
- [ ] Contract tests are not stretched to replace all business behavior testing.
- [ ] CI clearly distinguishes document errors, HTTP contract errors, and business errors.

A solid API contract keeps services communicating reliably. A strong test suite also proves services make accurate decisions against real data and state. Keep contract tests focused on communication boundaries while protecting critical rules with unit, integration, and scenario tests.

## References

- [Spring Boot – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Cloud Contract – Introducing Spring Cloud Contract](https://docs.spring.io/spring-cloud-contract/reference/getting-started/introducing-spring-cloud-contract.html)
- [Spring Cloud Contract – Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/index.html)
- [Pact – Introduction to Contract Testing](https://docs.pact.io/)
- [Pact – How Pact Works and Provider States](https://docs.pact.io/getting_started/how_pact_works)
- [Pact – Verifying Pacts](https://docs.pact.io/getting_started/verifying_pacts)
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [springdoc-openapi – Documentation](https://springdoc.org/)

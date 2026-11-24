# Isolating External Integrations Behind Adapters for Testability

A business service often has to communicate with systems outside its core logic boundary: payment gateways, inventory APIs, databases, message brokers, email providers, filesystems, object storage, or the system clock. If the service calls each vendor's concrete API directly, business logic becomes tightly coupled to that integration's library, protocol, and configuration. When writing tests, you end up spinning up heavy infrastructure or mocking classes with complex fluent APIs; when switching providers, changes ripple across multiple layers.

A practical design is placing an **adapter** between the application and external integrations. Business code depends on a small contract defined by the application; the adapter implements that contract using an HTTP client, repository, SDK, or concrete technology. In tests, you can replace the adapter with a fake or mock without calling the real external system.

```text
                Application / Business logic
                           │
                           ▼
                 Outbound port (interface)
                           ▲
                           │ implements
                           │
                    External adapter
                           │
               ┌───────────┼────────────┐
               ▼           ▼            ▼
           HTTP API      Database    Message broker
```

This lesson belongs to the **Application Design** chapter of **Spring Boot Fundamentals**. We will explore ports-and-adapters (hexagonal architecture), how to design interfaces for external integrations, how to write adapters in Spring Boot, how to swap adapters in unit tests, and how to test the connection itself separately against real systems or test servers.

## 1. The Problem When Business Logic Calls External Systems Directly

Suppose an application has a currency conversion service:

```java
@Service
public class CurrencyConversionService {

    private final RestClient restClient;

    public CurrencyConversionService(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("https://rates.example.com")
                .build();
    }

    public BigDecimal convert(
            BigDecimal amount,
            String from,
            String to
    ) {
        RateResponse response = restClient.get()
                .uri("/rates/{from}/{to}", from, to)
                .retrieve()
                .body(RateResponse.class);

        return amount.multiply(response.rate());
    }
}
```

This code works, yet the business class is doing too many things at once: knowing the provider's URL and endpoint, knowing how to make HTTP calls, knowing the provider's response DTO, knowing JSON deserialization details, performing business arithmetic, and depending on `RestClient`.

To test conversion, you may have to mock multi-level fluent HTTP client calls or start an HTTP server. Tests become brittle because they depend on how the service invokes HTTP. Switching to another provider with a different schema or authentication forces changes to the business service too.

### 1.1. The Responsibility Problem

A business service should focus on answering:

> Given an amount, source currency, and target currency, what rules govern the conversion calculation?

It should not have to know:

> Which HTTP headers, endpoint paths, or JSON field names does the rate provider expect?

Those are two distinct responsibilities. Adapters establish the boundary between them.

### 1.2. The Testing Problem

Without a boundary, tests may need to mock multiple HTTP client methods, mirror exact call order across builder/URI/headers/retrieve/body, configure test credentials or endpoints, and depend on network availability or an online provider. Separating the port and adapter lets unit tests pass a known rate directly to the business service, while HTTP mechanics are tested separately in adapter tests.

## 2. What Is an Adapter?

An **adapter** is a component that translates between the contract an application expects and the API/protocol provided by an external system.

Example:

- The application wants to ask: "what is the current price of this SKU?"
- The provider exposes an HTTP endpoint `/v2/catalog/items/{id}` returning JSON with a `current_amount` field.
- The adapter calls the endpoint, handles the HTTP response, translates the JSON into internal data types, and fulfills the contract the application understands.

```text
Application asks:
  getPrice(productId)
          │
          ▼
     CatalogPort
          ▲
          │
  HttpCatalogAdapter
          │
          ├── Build HTTP request
          ├── Add authentication
          ├── Call provider endpoint
          ├── Decode provider response
          ├── Map errors
          └── Convert to application model
          │
          ▼
   External Catalog API
```

An adapter acts as a **translator** at the boundary. It keeps provider-specific details from leaking deep into business code.

### 2.1. Adapters Are Not Just for HTTP

| External System | What Can an Adapter Do? |
|---|---|
| Payment gateway | Call payment API, map provider statuses to internal statuses |
| Database | Map domain objects to entities and call Spring Data repositories |
| Message broker | Publish/consume messages and map event schemas |
| Email provider | Translate email requests to a specific SDK/API |
| Filesystem | Read/write files behind a storage contract |
| Cloud object storage | Map object keys and streams to the cloud SDK |
| Clock | Provide current time via a replaceable abstraction |
| Identity provider | Translate tokens/provider responses into the application identity model |

You do not need an adapter for every method or class. Use one when there is a technical or vendor boundary you want to isolate.

## 3. Ports and Adapters (Hexagonal Architecture)

The **Ports and Adapters** pattern, also known as **Hexagonal Architecture**, places the application core at the center. External components connect to the core through ports (contracts) and adapters (implementations).

```text
                 Web Controller
                (Inbound Adapter)
                       │
                       ▼
              Inbound Port / Use Case
                       │
                       ▼
              ┌───────────────────┐
              │  Application Core │
              └───────────────────┘
                       │
             ┌─────────┴──────────┐
             ▼                    ▼
       Outbound Port         Outbound Port
             ▲                    ▲
             │ implements         │ implements
       HTTP Adapter          Persistence Adapter
             │                    │
             ▼                    ▼
       Payment API             Database
```

### 3.1. Inbound Ports

An inbound port describes an action the application permits outsiders to invoke.

```java
public interface PlaceOrderUseCase {
    OrderReceipt placeOrder(PlaceOrderCommand command);
}
```

A controller is an inbound adapter: it receives an HTTP request, turns it into a command, and calls the use case.

### 3.2. Outbound Ports

An outbound port describes a capability the application core needs from the outside world.

```java
public interface PaymentPort {
    PaymentResult charge(PaymentCommand command);
}
```

The application service calls `PaymentPort`. It does not need to know which SDK the implementation uses.

### 3.3. Dependency Direction

A core principle is that **the business/application layer defines the contract it needs**. External adapters depend on that contract.

```text
          Application Core
                 │
                 ▼
            PaymentPort
                 ▲
                 │ implements
          VendorPaymentAdapter
                 │
                 ▼
           Vendor SDK/API
```

This keeps business code independent of specific SDKs, allows adapters to change without editing business rules, lets tests supply fake implementations, and confines provider-specific DTOs/exceptions to the boundary.

### 3.4. Interfaces Should Belong to the Side That Needs Them

If `CheckoutService` needs price lookup functionality, the contract should reflect the checkout application's language:

```java
public interface ProductPricingPort {
    Money priceOf(ProductId productId);
}
```

Avoid copying an interface verbatim from a vendor SDK and forcing the application core to depend on it. Provider contracts are designed around the provider's protocol or product, not your application's needs.

Avoid:

```java
public interface PaymentPort {
    com.vendor.sdk.PaymentResponse charge(
            com.vendor.sdk.PaymentRequest request
    );
}
```

Better:

```java
public interface PaymentPort {
    PaymentResult charge(PaymentCommand command);
}
```

Types like `PaymentCommand` and `PaymentResult` belong to the application/domain model controlled by your project.

## 4. Designing Small, Business-Expressive Ports

A port is a contract, so method names should describe the capability the application needs rather than how the provider implements it.

Example with a blurry boundary:

```java
public interface ExternalApiClient {
    ResponseEntity<String> get(String url);
    ResponseEntity<String> post(String url, Object body);
}
```

This interface merely wraps an HTTP client. It forces business services to know URLs, HTTP statuses, and response parsing.

Better:

```java
public interface InventoryPort {
    Availability checkAvailability(
            ProductId productId,
            Quantity requested
    );

    Reservation reserve(
            ProductId productId,
            Quantity quantity,
            ReservationId reservationId
    );
}
```

The contract speaks in inventory terms. The adapter can implement it over REST, gRPC, or another inventory system.

Do not create an overly generic interface like `Object execute(String action, Map<String, Object> data)` because untyped contracts obscure meaning and complicate testing. Conversely, do not create an abstraction for every class. Create ports where an external boundary needs isolation, may vary, or must be swapped in tests.

## 5. End-to-End Example: Payment Gateway Integration

Let's build a simple payment flow. A checkout service receives an order ID and amount, invokes a payment port, the adapter converts the request to the provider's API, provider responses are mapped into internal results, and unit tests verify checkout without network calls.

### 5.1. Domain/Application Types

```java
package com.example.checkout;

import java.math.BigDecimal;

public record PaymentCommand(
        String orderId,
        BigDecimal amount,
        String currency
) {
}
```

```java
package com.example.checkout;

public record PaymentResult(
        String transactionId,
        PaymentStatus status
) {
}
```

```java
package com.example.checkout;

public enum PaymentStatus {
    APPROVED,
    DECLINED,
    PENDING
}
```

These types belong to the application model. They do not depend on JSON schemas or provider classes.

### 5.2. Defining the Outbound Port

```java
package com.example.checkout;

public interface PaymentPort {
    PaymentResult charge(PaymentCommand command);
}
```

The port expresses only the action checkout needs. It mentions no HTTP methods, endpoints, SDKs, or authentication headers.

### 5.3. Business Service Depending on the Port

```java
package com.example.checkout;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PaymentPort paymentPort;

    public CheckoutService(PaymentPort paymentPort) {
        this.paymentPort = paymentPort;
    }

    public PaymentResult checkout(PaymentCommand command) {
        validate(command);
        return paymentPort.charge(command);
    }

    private void validate(PaymentCommand command) {
        if (command.orderId() == null
                || command.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        if (command.amount() == null
                || command.amount().signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        if (command.currency() == null
                || command.currency().isBlank()) {
            throw new IllegalArgumentException("currency is required");
        }
    }
}
```

`CheckoutService` knows only `PaymentPort`. It does not care whether the adapter uses `RestClient` or another SDK.

### 5.4. Provider DTOs Live Inside the Adapter

Suppose the provider expects JSON:

```json
{
  "merchant_order": "ORD-100",
  "amount_value": 125000,
  "currency_code": "VND"
}
```

and returns:

```json
{
  "payment_reference": "pay-abc",
  "result_code": "SUCCESS"
}
```

Create dedicated DTOs for the protocol:

```java
package com.example.checkout.adapter.payment;

import java.math.BigDecimal;

public record ProviderChargeRequest(
        String merchant_order,
        BigDecimal amount_value,
        String currency_code
) {
}
```

```java
package com.example.checkout.adapter.payment;

public record ProviderChargeResponse(
        String payment_reference,
        String result_code
) {
}
```

The field names in these DTOs reflect the provider's JSON. Using a Jackson naming strategy or annotations, you can also name Java fields in camelCase while mapping to the JSON keys. What matters is keeping these DTOs strictly at the integration boundary.

### 5.5. Adapter Implementing the Port

```java
package com.example.checkout.adapter.payment;

import com.example.checkout.PaymentCommand;
import com.example.checkout.PaymentPort;
import com.example.checkout.PaymentResult;
import com.example.checkout.PaymentStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class HttpPaymentAdapter implements PaymentPort {

    private final RestClient restClient;

    public HttpPaymentAdapter(RestClient paymentRestClient) {
        this.restClient = paymentRestClient;
    }

    @Override
    public PaymentResult charge(PaymentCommand command) {
        ProviderChargeRequest request =
                new ProviderChargeRequest(
                        command.orderId(),
                        command.amount(),
                        command.currency()
                );

        ProviderChargeResponse response = restClient.post()
                .uri("/v1/payments")
                .body(request)
                .retrieve()
                .body(ProviderChargeResponse.class);

        if (response == null) {
            throw new PaymentProviderException(
                    "Payment provider returned an empty response"
            );
        }

        PaymentStatus status = switch (response.result_code()) {
            case "SUCCESS" -> PaymentStatus.APPROVED;
            case "DECLINED" -> PaymentStatus.DECLINED;
            case "PROCESSING" -> PaymentStatus.PENDING;
            default -> throw new PaymentProviderException(
                    "Unknown payment result code: " + response.result_code()
            );
        };

        return new PaymentResult(
                response.payment_reference(),
                status
        );
    }
}
```

The adapter maps the application command to a provider request, calls the endpoint, decodes the response, translates result codes into internal enums, and prevents provider response types from escaping past the port.

In production, the adapter must also handle authentication, timeouts, retry policies, correlation IDs, and network errors.

### 5.6. Exceptions at the Integration Boundary

```java
package com.example.checkout.adapter.payment;

public class PaymentProviderException extends RuntimeException {

    public PaymentProviderException(String message) {
        super(message);
    }

    public PaymentProviderException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Depending on your design, you can place a shared exception contract in the application layer, such as `PaymentUnavailableException`, and have the adapter map provider-specific errors into that type. That way the application service never has to catch vendor exceptions.

## 6. Configuring Adapters with Spring Dependency Injection

The adapter is a Spring bean injected through the port.

```java
package com.example.checkout.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class PaymentClientConfiguration {

    @Bean
    RestClient paymentRestClient(
            RestClient.Builder builder,
            @Value("https://payments.example.com") String baseUrl
    ) {
        return builder
                .baseUrl(baseUrl)
                .build();
    }
}
```

In a real project, the URL should come from externalized configuration or a `@ConfigurationProperties` object rather than being hardcoded in a business service. Example configuration:

```yaml
payment:
  api:
    base-url: https://payments.example.com
    connect-timeout: 2s
    read-timeout: 5s
```

Spring Boot provides an auto-configured builder when appropriate web client support is present. If the project defines multiple `RestClient` beans, use explicit names/qualifiers so the adapter receives the intended client.

### 6.1. Constructor Injection Makes Dependencies Explicit

```java
@Component
public class HttpPaymentAdapter implements PaymentPort {

    private final RestClient restClient;

    public HttpPaymentAdapter(RestClient paymentRestClient) {
        this.restClient = paymentRestClient;
    }
}
```

And:

```java
@Service
public class CheckoutService {

    private final PaymentPort paymentPort;

    public CheckoutService(PaymentPort paymentPort) {
        this.paymentPort = paymentPort;
    }
}
```

Spring finds the bean implementing `PaymentPort` and injects it into the service. If multiple adapters implement the same port, use `@Qualifier`, `@Primary`, or an explicit selection configuration.

### 6.2. Do Not Inject Concrete Adapters into Application Services

Avoid:

```java
@Service
public class CheckoutService {

    private final HttpPaymentAdapter adapter;

    public CheckoutService(HttpPaymentAdapter adapter) {
        this.adapter = adapter;
    }
}
```

This couples the service to the concrete implementation. Depend on the port:

```java
private final PaymentPort paymentPort;
```

Now you can replace `HttpPaymentAdapter` with a fake, sandbox adapter, or different provider without editing the business service.

## 7. Unit Testing Services with Fake Adapters

One of the biggest benefits of ports is writing fake implementations in tests.

```java
class FakePaymentAdapter implements PaymentPort {

    private PaymentCommand lastCommand;

    private PaymentResult nextResult =
            new PaymentResult(
                    "fake-transaction",
                    PaymentStatus.APPROVED
            );

    @Override
    public PaymentResult charge(PaymentCommand command) {
        this.lastCommand = command;
        return nextResult;
    }

    PaymentCommand lastCommand() {
        return lastCommand;
    }

    void setNextResult(PaymentResult result) {
        this.nextResult = result;
    }
}
```

Unit test:

```java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CheckoutServiceTest {

    @Test
    void sendsPaymentCommandAndReturnsProviderResult() {
        FakePaymentAdapter fake = new FakePaymentAdapter();
        CheckoutService service = new CheckoutService(fake);

        PaymentCommand command = new PaymentCommand(
                "ORD-100",
                new BigDecimal("125000"),
                "VND"
        );

        PaymentResult result = service.checkout(command);

        assertThat(result.status())
                .isEqualTo(PaymentStatus.APPROVED);

        assertThat(fake.lastCommand())
                .isEqualTo(command);
    }
}
```

This test starts no Spring context, makes no HTTP calls, requires no provider credentials, and has no network dependency. It verifies that the application service invokes the port with the right data.

### 7.1. How Do Fakes Differ from Mocks?

A **fake** is a lightweight implementation with real working behavior scoped to tests, such as an in-memory store or fake payment port.

A **mock** is a test double configured to return canned values and/or verify interactions.

Both are useful. Fakes fit well when simulating a stateful contract simply; mocks fit well when verifying a specific interaction.

### 7.2. Unit Test Business Rules, Not HTTP Details

In `CheckoutServiceTest`, do not assert URLs, JSON fields, or HTTP headers. That is the responsibility of adapter tests.

If a service unit test knows about `/v1/payments`, integration details have leaked into the business layer.

## 8. Using Mockito to Test Port Interactions

If you prefer not to write a fake class:

```java
@ExtendWith(MockitoExtension.class)
class CheckoutServiceMockitoTest {

    @Mock
    PaymentPort paymentPort;

    @InjectMocks
    CheckoutService checkoutService;

    @Test
    void delegatesChargeToPaymentPort() {
        PaymentCommand command = new PaymentCommand(
                "ORD-100",
                new BigDecimal("125000"),
                "VND"
        );

        PaymentResult expected = new PaymentResult(
                "txn-100",
                PaymentStatus.APPROVED
        );

        given(paymentPort.charge(command))
                .willReturn(expected);

        PaymentResult actual = checkoutService.checkout(command);

        assertThat(actual).isEqualTo(expected);
        verify(paymentPort).charge(command);
    }
}
```

This Mockito test proves the service invokes the right contract. It does not prove the HTTP adapter sends the right request or that the provider actually processes the payment.

If the application service must translate integration failures into business outcomes, test that mapping with behavior tests. Never let the service silently swallow exceptions.

## 9. Testing Adapters Separately with MockRestServiceServer

Service unit tests do not verify HTTP requests. To verify that the adapter calls the right endpoint, HTTP method, headers, and payload, write adapter tests.

Spring provides `MockRestServiceServer` to test HTTP clients without real network calls. From Spring Framework 6.1 onward, it supports `RestClient.Builder`.

Example:

```java
import com.example.checkout.PaymentCommand;
import com.example.checkout.PaymentStatus;
import com.example.checkout.adapter.payment.HttpPaymentAdapter;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.http.HttpMethod.POST;
import static org.springframework.http.MediaType.APPLICATION_JSON;

class HttpPaymentAdapterTest {

    private MockRestServiceServer server;
    private HttpPaymentAdapter adapter;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://payments.test");

        server = MockRestServiceServer.bindTo(builder).build();
        adapter = new HttpPaymentAdapter(builder.build());
    }

    @Test
    void postsPaymentAndMapsProviderResponse() {
        server.expect(requestTo(
                        "https://payments.test/v1/payments"
                ))
                .andExpect(method(POST))
                .andRespond(withSuccess(
                        """
                        {
                          "payment_reference": "pay-100",
                          "result_code": "SUCCESS"
                        }
                        """,
                        APPLICATION_JSON
                ));

        PaymentCommand command = new PaymentCommand(
                "ORD-100",
                new BigDecimal("125000"),
                "VND"
        );

        var result = adapter.charge(command);

        assertThat(result.transactionId()).isEqualTo("pay-100");
        assertThat(result.status()).isEqualTo(PaymentStatus.APPROVED);

        server.verify();
    }
}
```

This example assumes an appropriate Jackson JSON converter is on the classpath so `RestClient` can deserialize the response record. In Spring Boot applications with a matching web starter, converters are normally auto-configured when using Boot's builder; in tests building a plain builder, ensure converter dependencies are present or configure message converters explicitly.

### 9.1. Asserting Request Bodies and Headers

You can add matchers to verify JSON payloads:

```java
.andExpect(content().json(
        """
        {
          "merchant_order": "ORD-100",
          "amount_value": 125000,
          "currency_code": "VND"
        }
        """
))
```

Also assert authentication headers or correlation IDs. In tests, use dummy keys. Never put production secrets into source code or test fixtures.

## 10. @RestClientTest in Spring Boot

Spring Boot provides the `@RestClientTest` slice for applications using `RestClient`, `RestTemplate`, and related components.

```java
@RestClientTest(HttpPaymentAdapter.class)
class HttpPaymentAdapterSliceTest {

    @Autowired
    HttpPaymentAdapter adapter;

    @Autowired
    MockRestServiceServer server;
}
```

This test slice focuses on client-side components and appropriate converter configuration without loading the full application context. Exact setup details depend on your Spring Boot version, HTTP client type, and `RestClient.Builder` bean used by the adapter. Verify APIs against your project's version.

Use it to verify JSON serialization/deserialization, request method/URI/headers, mapping provider responses to the application model, status code mapping, and provider errors. Do not use it to prove an entire business workflow or database integration works.

## 11. Adapters for Databases

The database is also an external system relative to the application core. You can define a persistence port in domain terms.

```java
package com.example.orders;

import java.util.Optional;

public interface OrderStore {
    void save(Order order);
    Optional<Order> findById(OrderId id);
}
```

Application service:

```java
@Service
public class OrderApplicationService {

    private final OrderStore orderStore;

    public OrderApplicationService(OrderStore orderStore) {
        this.orderStore = orderStore;
    }

    public Order load(OrderId id) {
        return orderStore.findById(id)
                .orElseThrow(() ->
                        new OrderNotFoundException(id)
                );
    }
}
```

The Spring Data repository lives in the adapter:

```java
interface SpringDataOrderRepository
        extends JpaRepository<OrderEntity, Long> {
}
```

Adapter:

```java
@Repository
public class JpaOrderStoreAdapter implements OrderStore {

    private final SpringDataOrderRepository repository;
    private final OrderMapper mapper;

    public JpaOrderStoreAdapter(
            SpringDataOrderRepository repository,
            OrderMapper mapper
    ) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Override
    public void save(Order order) {
        repository.save(mapper.toEntity(order));
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return repository.findById(id.value())
                .map(mapper::toDomain);
    }
}
```

The application core never needs to know about JPA entities, `JpaRepository`, table mappings, or SQL dialects.

### 11.1. Should You Always Create a Repository Port?

Not necessarily. A simple Spring Data application can use repository interfaces directly in services if the domain/application boundary needs no extra isolation.

Ports/adapters become more valuable when the domain model differs from the persistence model, when keeping JPA annotations out of the domain, when supporting multiple persistence implementations, when business logic must be tested without loading JPA, or when database technology needs to vary independently.

### 11.2. Testing Database Adapters

Use `@DataJpaTest` or integration tests against a compatible database to verify entity mapping, query behavior, constraints, transaction semantics, and entity-to-domain translation.

An application service unit test only needs a fake `OrderStore`; it does not prove SQL queries are correct.

## 12. Adapters for Message Brokers

Suppose the application must emit an event when an order is confirmed.

```java
public interface OrderEventPublisher {
    void publish(OrderConfirmed event);
}
```

Application service:

```java
@Service
public class ConfirmOrderService {

    private final OrderStore orderStore;
    private final OrderEventPublisher eventPublisher;

    public ConfirmOrderService(
            OrderStore orderStore,
            OrderEventPublisher eventPublisher
    ) {
        this.orderStore = orderStore;
        this.eventPublisher = eventPublisher;
    }

    public void confirm(OrderId id) {
        Order order = orderStore.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        order.confirm();
        orderStore.save(order);

        eventPublisher.publish(
                new OrderConfirmed(order.id().value())
        );
    }
}
```

An adapter can use Kafka:

```java
@Component
public class KafkaOrderEventAdapter
        implements OrderEventPublisher {

    private final KafkaTemplate<String, OrderConfirmedMessage> kafka;

    public KafkaOrderEventAdapter(
            KafkaTemplate<String, OrderConfirmedMessage> kafka
    ) {
        this.kafka = kafka;
    }

    @Override
    public void publish(OrderConfirmed event) {
        OrderConfirmedMessage message =
                new OrderConfirmedMessage(event.orderId());

        kafka.send("orders.confirmed", event.orderId(), message);
    }
}
```

The application core does not depend on `KafkaTemplate` or topic names.

### 12.1. What Does Publish Success Mean?

Calling `kafka.send(...)` may return a future; never assume the broker has acknowledged the message simply because the method returned.

The adapter must define whether the contract waits synchronously for a broker ack, returns an async result, or reports failures via callback/future. The port should reflect the semantics the application requires.

### 12.2. Database and Broker Are Not Automatically Atomic Together

If a service writes to a database and then publishes a message, a failure between the two steps can leave the database committed while the message was never sent. Ports and adapters do not solve distributed consistency by themselves. For durable delivery guarantees, consider a transactional outbox, CDC, or an appropriate messaging mechanism.

### 12.3. Consumers Are Adapters Too

A message listener receiving a DTO from a broker is an inbound adapter:

```java
@Component
public class OrderMessageListener {

    private final ProcessOrderUseCase useCase;

    public OrderMessageListener(ProcessOrderUseCase useCase) {
        this.useCase = useCase;
    }

    @KafkaListener(topics = "orders.created")
    public void onMessage(OrderCreatedMessage message) {
        useCase.process(
                new ProcessOrderCommand(message.orderId())
        );
    }
}
```

The listener translates the broker schema into an application command. The business use case does not need to import `@KafkaListener` or know Kafka record metadata.

## 13. Adapters for Filesystem, Object Storage, and Clock

An application storing documents can define a port:

```java
public interface DocumentStoragePort {
    StoredDocument store(DocumentContent content);
    Optional<DocumentContent> load(DocumentId id);
}
```

A filesystem adapter or S3 adapter can implement the same contract if semantics align. A filesystem adapter must prevent path traversal, check permissions, stream large files safely, and address write atomicity. A cloud storage adapter must manage credentials, bucket policies, timeouts, retries, and provider errors.

An in-memory fake can store a `Map<DocumentId, DocumentContent>` to test business behavior without touching real files. The filesystem adapter still needs integration tests against a temporary directory to verify paths, encodings, and I/O behavior.

The system clock is another external dependency that is hard to control if code calls `LocalDateTime.now()` directly in many places. Java already provides the `java.time.Clock` abstraction:

```java
@Service
public class CouponService {

    private final Clock clock;

    public CouponService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return Instant.now(clock).isAfter(expiresAt);
    }
}
```

Spring configuration:

```java
@Configuration
public class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Unit test:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-15T00:00:00Z"),
        ZoneOffset.UTC
);
CouponService service = new CouponService(fixedClock);
```

Tests can control the exact timestamp without relying on the machine's wall clock. `Clock` is a built-in abstraction; you do not necessarily need to wrap it in another interface.

## 14. Error Mapping at the Adapter Boundary

External systems can return many failure modes: HTTP 400/401/403/404/409/429/5xx, timeouts, connection refused, malformed schemas, provider business errors, SDK exceptions, broker rejections, or database constraint violations.

Do not force business services to depend on every vendor's exception classes.

Example application exception:

```java
public class PaymentUnavailableException extends RuntimeException {

    public PaymentUnavailableException(
            String message,
            Throwable cause
    ) {
        super(message, cause);
    }
}
```

The adapter can catch transport errors:

```java
try {
    return callProvider(command);
} catch (ResourceAccessException ex) {
    throw new PaymentUnavailableException(
            "Payment provider is unavailable",
            ex
    );
}
```

The application service only needs to understand `PaymentUnavailableException` if it has specific behavior when the provider is unavailable.

### 14.1. Do Not Collapse Every Error into One Generic Outcome

If an adapter catches every exception and returns `PaymentStatus.DECLINED`, the application cannot distinguish a declined customer payment, a provider timeout, expired credentials, a provider server error, or a malformed request.

These cases carry different business semantics. Map error categories explicitly.

### 14.2. Preserve the Cause for Investigation

When wrapping exceptions, pass the original cause:

```java
throw new PaymentUnavailableException(
        "Payment provider timed out",
        ex
);
```

This keeps the root exception in the cause chain in logs. Never include raw provider responses containing secrets or sensitive data in exception messages.

## 15. Timeouts, Retries, Circuit Breakers, and Idempotency

An adapter calling an external system needs an appropriate resilience policy.

### 15.1. Timeouts

Never let HTTP requests wait indefinitely. Configure connect/read/response timeouts according to the HTTP client in use and the application's latency goals.

Timeouts must align with the caller's API deadline, total retry duration, thread pool capacity, provider baseline latency, and reverse proxy/load balancer timeouts.

### 15.2. Retries

Retry only errors likely to be transient and operations safe to retry.

- Connection resets may be retryable.
- HTTP 429 may need backoff and honoring `Retry-After`.
- HTTP 400 caused by an invalid request usually should not be retried.
- Payment charges have side effects and require an idempotency key before retrying.

Do not retry every exception in a fixed loop. That can amplify a provider outage.

### 15.3. Circuit Breakers

A circuit breaker stops the application from repeatedly calling a consistently failing dependency. The adapter is the right place to apply outbound call policies, while the business service must understand any fallback semantics.

For example, a fallback might be "price unavailable, return unavailable" rather than silently using a stale price if business rules forbid it.

### 15.4. Idempotency

For side-effecting operations such as charging a payment or creating a shipment, retries can trigger duplicate actions. The adapter can send a stable idempotency key to the provider, while the key should be generated/defined per business operation and preserved across retries.

A port can carry `PaymentCommand` containing `paymentAttemptId` or `idempotencyKey` if that is part of the contract the application must control.

## 16. Provider Configuration Should Not Live in Business Services

Do not instantiate clients and hardcode endpoints or credentials inside a service constructor. Doing so makes the service hard to test, hard to switch between sandbox and production, and risks leaking secrets.

Place settings in application configuration:

```yaml
payment:
  api:
    base-url: https://payments.example.com
    connect-timeout: 2s
    read-timeout: 5s
```

Use `@ConfigurationProperties` for structured settings:

```java
@ConfigurationProperties(prefix = "payment.api")
public record PaymentApiProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout
) {
}
```

Adapter configuration accepts the properties and builds the appropriate HTTP client.

### 16.1. Secret Management

API keys and passwords should come from a secret store or protected environment-specific configuration. Never commit real credentials into `application.yml`, never log tokens, and never put secrets into test fixtures.

### 16.2. Profiles Should Not Be the Only Way to Choose Providers

Profiles can configure endpoints or test adapters, yet provider choice should be clear in dependency wiring. Never let the application core inspect `spring.profiles.active` to decide whether to call Vendor A or Vendor B.

## 17. Multiple Adapters for the Same Port

Multiple valid implementations can exist:

```java
public interface PaymentPort {
    PaymentResult charge(PaymentCommand command);
}
```

```java
@Component
@Qualifier("providerA")
public class ProviderAPaymentAdapter implements PaymentPort {
    // ...
}
```

```java
@Component
@Qualifier("providerB")
public class ProviderBPaymentAdapter implements PaymentPort {
    // ...
}
```

If the application selects by configuration, you can use a routing adapter or bean conditions.

`@Primary` chooses the preferred bean when multiple candidates exist. `@Qualifier` lets you specify the exact implementation:

```java
@Service
public class CheckoutService {

    private final PaymentPort paymentPort;

    public CheckoutService(
            @Qualifier("providerA") PaymentPort paymentPort
    ) {
        this.paymentPort = paymentPort;
    }
}
```

The qualifier name is a wiring detail. The business service still depends on the `PaymentPort` interface, not on a provider class.

If selecting providers by property, use `@ConditionalOnProperty` on configuration or adapter beans. Ensure only one implementation matches in a given environment and that invalid configurations fail clearly at startup.

## 18. How Do Adapter Tests and Contract Tests Differ?

| Test | What Does It Verify? | Uses Real Provider? |
|---|---|---|
| Application service unit test | Business rules and port usage | No |
| Adapter unit/slice test | Request/response mapping, headers, error mapping | No; uses mock server |
| Contract test | Application and provider agree on the API contract | Usually uses stub/provider contract |
| Integration test | Connectivity with test instance or sandbox | Possibly |
| End-to-end test | Full system flow across boundaries | Usually uses an integrated environment |

### 18.1. Mock Server Tests

Use `MockRestServiceServer`, WireMock, or MockWebServer to verify HTTP behavior without calling the internet.

### 18.2. Contract Tests

If a provider supplies an OpenAPI schema or Pact contract, verify that the adapter sends requests and parses responses matching the agreed contract. Contract tests catch breaking API changes at the boundary.

### 18.3. Sandbox Integration Tests

Some payment, email, or cloud providers offer sandboxes. You can run tests less frequently against sandbox credentials, provided tests have timeouts, isolated test data, and cleanup. Never perform real-money transactions in routine automated tests.

## 19. WireMock for HTTP Adapter Integration Tests

WireMock can run an HTTP server simulating a provider.

```java
stubFor(post(urlEqualTo("/v1/payments"))
        .willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                    {
                      "payment_reference": "pay-100",
                      "result_code": "SUCCESS"
                    }
                    """)));
```

Then configure `RestClient` to point at the WireMock server and invoke the adapter.

You can verify request method/path, authentication headers (with dummy tokens), body schema, response mapping, error status codes, timeouts/connection failures, and retry behavior if retries are configured on the adapter.

Each test should reset WireMock mappings and request journals or use an isolated server instance. If server state is shared across tests, tests may pass individually yet fail when run in parallel.

## 20. Testing Persistence and Messaging Adapters

Just like HTTP adapters, database adapters need dedicated tests. `@DataJpaTest` can test Spring Data repositories. If extra mappers or adapters exist, inject them in the test slice or use a fuller integration test configuration.

H2 can suit simple persistence tests. Testcontainers with PostgreSQL/MySQL suits cases requiring production-compatible SQL dialects and constraints. In-memory fakes suit business-logic unit tests, not as replacements for database integration tests.

For Kafka/RabbitMQ or other brokers, separately test: the business service calling the outbound port, the adapter mapping events to message schemas, broker integration confirming publish/consume behavior, and the consumer adapter mapping messages into application commands/events. Application service unit tests can fake `OrderEventPublisher`; adapter integration tests can use a broker test container.

## 21. Mapping DTOs and Domain Models at the Adapter Boundary

External APIs rarely match your domain model's schema.

For example, the provider returns:

```json
{
  "payment_reference": "p-100",
  "result_code": "SUCCESS",
  "provider_timestamp": "2026-02-01T10:15:30Z"
}
```

The application may only need:

```java
public record PaymentResult(
        TransactionId transactionId,
        PaymentStatus status
) {
}
```

Adapter mapping:

```java
private PaymentResult toApplicationResult(
        ProviderChargeResponse response
) {
    return new PaymentResult(
            new TransactionId(response.payment_reference()),
            mapStatus(response.result_code())
    );
}
```

If the provider renames `payment_reference` to `transaction_ref`, only the adapter DTO/mapper needs updating, while the application contract remains unchanged.

Never return a raw `Map<String, Object>` or provider DTO across a port out of convenience. That creates hidden coupling: consumers can start depending on provider-specific fields, negating the adapter's value.

Keep only fields genuinely needed for business logic, auditing, or support. If a provider reference is needed for tracing, model it as an application value object like `ProviderTransactionId` rather than letting the full vendor response leak into the core.

## 22. Anti-Corruption Layer and Adapters

In larger systems, an adapter sometimes acts as an **anti-corruption layer**: protecting the internal model from an external system's terminology and assumptions.

Examples:

- Provider uses status codes `S`, `F`, `P`.
- Domain uses `APPROVED`, `DECLINED`, `PENDING`.
- Provider represents amounts as integer minor units.
- Domain uses `Money` with an explicit currency.
- Provider sends UTC timestamps as strings.
- Domain uses `Instant`.
- Provider calls the customer `account_holder`.
- Domain uses `CustomerId`.

The adapter translates both schema and semantics, not merely field names.

If a provider sends amounts in cents, conversion must follow explicit currency rules. Never assume every currency has two decimal places. For money, use domain money types and proper currency metadata instead of hardcoded global conversions.

If Provider A supports separate authorize/capture steps while Provider B only supports immediate charges, the adapter should not pretend both have identical semantics if they cannot deliver equivalent behavior. Ports must describe real capabilities the application can rely on.

## 23. Adapters Do Not Automatically Make Distributed Transactions Atomic

A service might write an order to a database, charge a payment provider, and publish an event to a message broker. Even if all three operations are wrapped behind adapters, they do not automatically form a single atomic transaction.

If step 2 succeeds and step 3 fails, system state can become inconsistent.

### 23.1. Saga/Compensation

A workflow may need to record a pending order, charge payment, confirm the order, and if a later step fails, perform a refund/compensation according to business policy. Adapters isolate individual integrations, while sagas/workflows manage distributed state.

### 23.2. Outbox

When database updates and event publication must not drift apart, a transactional outbox is a common choice:

```text
Database transaction:
  - update order
  - insert outbox record
          │
          ▼
Outbox publisher reads pending records
          │
          ▼
Publish to broker
          │
          ▼
Mark record as published
```

An outbox adapter can encapsulate persistence/publishing details. The application workflow still needs proper idempotency and retries.

## 24. Testing Configuration and Adapter Selection

A common failure mode is having an interface and adapters yet Spring failing to wire the right implementation.

```java
@Component
@Profile("sandbox")
public class SandboxPaymentAdapter implements PaymentPort {
    // ...
}
```

```java
@Component
@Profile("production")
public class ProductionPaymentAdapter implements PaymentPort {
    // ...
}
```

When running with the `test` profile and no matching adapter, `CheckoutService` fails injection.

You can declare a fake bean in test configuration:

```java
@TestConfiguration
class PaymentTestConfiguration {

    @Bean
    @Primary
    PaymentPort paymentPort() {
        return command -> new PaymentResult(
                "test-transaction",
                PaymentStatus.APPROVED
        );
    }
}
```

And import it into the test:

```java
@SpringBootTest
@Import(PaymentTestConfiguration.class)
class CheckoutIntegrationTest {
}
```

If the production adapter is still scanned and shares the type, `@Primary` can select the fake for injection; however, avoid instantiating production adapters with side effects in tests. Using profiles, conditional configuration, or explicit bean overrides is cleaner.

A context test verifies Spring resolves a `PaymentPort` bean. A behavior test verifies checkout handles approved/declined/unavailable outcomes properly. An adapter test verifies HTTP requests/responses. All three goals should be tested separately or intentionally combined.

## 25. Suggested Package Structure

For a small application:

```text
com.example.shop
├── checkout
│   ├── CheckoutService.java
│   ├── PaymentPort.java
│   ├── PaymentCommand.java
│   └── PaymentResult.java
└── adapter
    └── payment
        ├── HttpPaymentAdapter.java
        ├── ProviderChargeRequest.java
        ├── ProviderChargeResponse.java
        └── PaymentClientConfiguration.java
```

For larger applications, organize by feature:

```text
com.example.shop
├── order
│   ├── application
│   ├── domain
│   └── adapter
│       ├── in
│       │   └── web
│       └── out
│           ├── persistence
│           └── messaging
└── shared
```

No single package layout is mandatory. What must be preserved is dependency direction: the core does not import vendor types, and adapters depend on appropriate port/domain contracts.

Avoid dumping HTTP clients, repositories, mappers, payment SDKs, and message publishers into a `utils` package that erases boundaries. Package names should express capabilities or boundaries: `adapter.payment`, `adapter.persistence`, `adapter.messaging`.

## 26. Common Pitfalls When Designing Adapters

| Symptom | Cause | Remedy |
|---|---|---|
| Service still imports vendor SDK | Port contains vendor types or service injects implementation | Move contract to application model and inject interface |
| Unit tests must mock RestClient fluent chains | Business service calls HTTP directly | Extract outbound port and adapter |
| Service tests hit the internet | Real adapter used in unit tests | Use fake/mock port |
| Adapter is not injected | Missing bean, wrong component scan/profile | Check bean registration and active profiles |
| Two beans implement the same port | Multiple adapters registered simultaneously | Use qualifier/primary/condition |
| Provider JSON change breaks many services | Provider DTO leaked out of adapter | Map responses at the boundary |
| Provider 500 treated as payment declined | Error mapping too simplistic | Distinguish declined, unavailable, and technical failure |
| Retries create duplicate charges | Missing idempotency | Use a stable idempotency key |
| Adapter test only asserts output, ignoring request | Missing request matchers | Assert method, URI, headers, and body |
| Fake tests pass yet database fails | Fakes do not verify SQL/JPA | Add repository integration tests |
| App publishes event yet broker misses it | Adapter async/ack semantics untested | Test future/ack and broker integration |
| Test profile missing port bean | Production adapter active only in other profiles | Register test adapter/configuration |
| Adapter grows too large | Single class handles multiple providers/capabilities | Split by port or responsibility |
| Interface for every class without reducing coupling | Abstractions lack real boundaries | Create ports only where substitutability/isolation is needed |
| Business service inspects HTTP status codes | Transport details leaked into core | Map statuses/errors inside the adapter |

## 27. Workflow for Refactoring Direct Integrations into Adapters

Suppose a service currently calls a provider directly.

1. **Identify the business service's needs:** list the exact operations the application requires from the provider, such as `charge`, `refund`, `lookupTransaction`.
2. **Define the port in application terms:** use application/domain types; avoid `ResponseEntity`, vendor DTOs, and SDK classes.
3. **Move protocol code into the adapter:** relocate URLs, headers, authentication, serialization, status mapping, and provider error handling.
4. **Inject the port into the service:** use constructor injection; never instantiate adapters with `new` in business services.
5. **Register the adapter with Spring:** use `@Component`/`@Repository`, `@Bean`, `@Configuration`, profiles, or conditions as appropriate.
6. **Write application service unit tests:** use a fake/mock port to verify business rules, outputs, error handling, and side effects.
7. **Write adapter tests:** use a mock HTTP server, test broker, or temporary filesystem directory to verify protocol mapping.
8. **Write integration tests for key risks:** use sandbox/provider test environments, Testcontainers, or contract tests where needed.
9. **Check dependency direction:** the application core must not import provider SDKs or HTTP DTOs; adapters may depend on ports and concrete technologies.
10. **Verify operational concerns:** timeouts, retries, idempotency, authentication, logging, metrics, secrets, and failure semantics must be explicit.

## 28. When to Use a Fake, Mock, or Adapter Integration Test?

| Goal | Suitable Choice |
|---|---|
| Test business rules quickly | Fake/mock port in unit tests |
| Verify service passes the right command | Mock port or recording fake |
| Verify JSON requests/responses | MockRestServiceServer/WireMock |
| Verify SQL and JPA mapping | `@DataJpaTest`/Testcontainers |
| Verify message schemas and broker behavior | Broker test container or contract tests |
| Verify provider sandbox | Controlled integration test |
| Verify full request flow | `@SpringBootTest`/HTTP integration test |
| Verify bean wiring | Context test with proper profiles/config |

You do not need to run every test type for every change. Choose tests based on the code and risks modified.

## 29. Practice Exercises

### Exercise 1 — Extract HTTP Calls from a Service

Create a `CurrencyConversionService` that currently uses `RestClient` directly. Define `ExchangeRatePort`, move HTTP logic to `HttpExchangeRateAdapter`, and update the service to inject only the port.

### Exercise 2 — Write a Fake Adapter

Create `FakeExchangeRateAdapter` returning fixed rates. Write unit tests verifying converted amounts without starting Spring or making network calls.

### Exercise 3 — Verify Error Behavior

Have the fake adapter throw `ExchangeRateUnavailableException`. Verify the service propagates or translates the error according to business contracts.

### Exercise 4 — Map Provider DTOs

Create a provider response whose field names differ from the domain model. Write a mapper in the adapter and verify the application receives only `ExchangeRate`.

### Exercise 5 — MockRestServiceServer

Write an adapter test asserting HTTP method, URI, request JSON, response JSON, and headers. Use test URLs, not a real provider.

### Exercise 6 — Test HTTP Error Mapping

Simulate provider responses 400, 401, 429, and 503. Design distinct mappings for invalid requests, credential issues, rate limits, and service unavailability.

### Exercise 7 — Persistence Port

Define `OrderStore` and write `JpaOrderStoreAdapter` backed by a Spring Data repository. Test the service with a fake and the adapter with `@DataJpaTest`.

### Exercise 8 — Message Publisher Port

Define `OrderEventPublisher` and write a Kafka adapter. Unit test the service with a fake publisher and integration test the adapter with a broker test environment.

### Exercise 9 — Clock Injection

Inject `Clock` into `CouponService`. Write tests using `Clock.fixed` for before, at, and after the expiration timestamp.

### Exercise 10 — Multiple Payment Providers

Create two `PaymentPort` implementations selected via qualifiers or conditional configuration. Write context tests for each configuration to verify only the intended adapter is injected.

### Exercise 11 — Idempotency

Add an idempotency key to `PaymentCommand`. Verify the adapter sends the key in the HTTP header/request per the provider contract and that retries do not create duplicate transactions in sandbox tests.

### Exercise 12 — Timeouts and Retries

Configure timeouts on the HTTP client, simulate timeouts via a mock server, and verify the application receives a consistent internal error. Verify retries apply only to retryable errors.

### Exercise 13 — Vendor-Independent Tests

Locate vendor SDK imports inside application/domain packages. Move them into adapters, then run unit tests using only fake implementations.

### Exercise 14 — Contract Tests

Describe a provider's contract via OpenAPI/Pact or fixtures. Write tests confirming the adapter's request/response mapping matches the contract.

### Exercise 15 — Split an Oversized Adapter

Create an adapter handling payments, refunds, and customer lookups. Split the port by capability if responsibilities can evolve independently, then evaluate dependencies and test setup.

### Exercise 16 — Verify Dependency Direction

Draw the dependency graph of the application core and adapters. Ensure the core depends only on internal contracts/models and adapters depend on concrete technologies/providers.

## 30. Official References

- [Spring Framework Reference — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, `WebClient`, and HTTP client abstractions.
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): test slices, application integration tests, and test support.
- [Spring Boot Reference — @RestClientTest](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): testing support for REST clients by version.
- [Spring Framework Reference — MockRestServiceServer](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): testing HTTP clients with a mock server.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/): repository abstractions and persistence integration.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): producer/consumer integration and testing.
- [Martin Fowler — Ports and Adapters](https://martinfowler.com/articles/hexagonal-architecture.html): the ports-and-adapters architectural pattern.
- [Testcontainers Documentation](https://java.testcontainers.org/): integration testing with databases and services running in containers.
- [Java API — java.time.Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): replaceable time abstraction for tests.

**Key Principle:** an application service should depend on a contract expressing what it needs; an adapter implements that contract using concrete HTTP, database, broker, or SDK technologies. This lets business tests use fakes/mocks to verify rules quickly and reliably, while adapter tests focus on protocols, serialization, error mapping, and integration. Adapters do not make distributed systems atomic by themselves, do not replace timeout/idempotency/retry policies, and are not a reason to create interfaces for every class. Place boundaries where external details must be isolated, keep provider-specific data inside adapters, and test each boundary with the right kind of test.

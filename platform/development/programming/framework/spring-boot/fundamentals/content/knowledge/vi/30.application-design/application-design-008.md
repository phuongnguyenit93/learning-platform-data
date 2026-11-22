# Đưa tích hợp bên ngoài qua adapter để dễ kiểm thử

Một service nghiệp vụ thường phải trao đổi với các hệ thống nằm ngoài phạm vi logic của nó: payment gateway, inventory API, database, message broker, email provider, filesystem, object storage hoặc đồng hồ hệ thống. Nếu service gọi trực tiếp API cụ thể của từng nhà cung cấp, business logic sẽ bị gắn chặt với thư viện, giao thức và cách cấu hình của integration đó. Khi viết test, bạn phải dựng nhiều hạ tầng hoặc mock những class có API phức tạp; khi đổi nhà cung cấp, thay đổi có thể lan qua nhiều tầng.

Một cách thiết kế hữu ích là đặt một **adapter** giữa ứng dụng và tích hợp bên ngoài. Phần nghiệp vụ phụ thuộc vào một contract nhỏ do ứng dụng định nghĩa; adapter hiện thực contract đó bằng HTTP client, repository, SDK hoặc công nghệ cụ thể. Trong test, bạn có thể thay adapter bằng fake hoặc mock mà không cần gọi hệ thống thật.

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

Bài học thuộc chương **Thiết kế ứng dụng** của **Spring Boot Fundamentals**. Chúng ta sẽ tìm hiểu ports-and-adapters (hexagonal architecture), cách thiết kế interface cho tích hợp bên ngoài, cách viết adapter trong Spring Boot, cách thay thế adapter trong unit test và cách kiểm thử riêng phần kết nối với hệ thống thật hoặc test server.

## 1. Vấn đề khi business logic gọi thẳng hệ thống bên ngoài

Giả sử ứng dụng có service đổi tiền:

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

Đoạn code có thể chạy, nhưng class nghiệp vụ đang làm nhiều việc cùng lúc: biết URL và endpoint của provider, biết cách gọi HTTP, biết response DTO của nhà cung cấp, biết cơ chế deserialize JSON, thực hiện công thức nghiệp vụ và phụ thuộc vào `RestClient`.

Nếu test conversion, bạn có thể phải mock fluent API nhiều tầng của HTTP client hoặc dựng HTTP server. Test có thể trở nên mong manh vì phụ thuộc chi tiết cách service gọi HTTP. Nếu chuyển sang provider khác có schema hoặc authentication khác, business service cũng phải sửa.

### 1.1. Vấn đề về trách nhiệm

Một service nghiệp vụ nên tập trung trả lời:

> Với số tiền, loại tiền nguồn và loại tiền đích, ứng dụng cần tính kết quả theo quy tắc nào?

Nó không nên phải biết:

> Nhà cung cấp rate yêu cầu HTTP header nào, endpoint nào, response JSON có tên field gì?

Đó là hai trách nhiệm khác nhau. Adapter giúp đặt ranh giới giữa chúng.

### 1.2. Vấn đề khi kiểm thử

Nếu không có ranh giới, test có thể cần mock nhiều method của HTTP client, biết thứ tự gọi builder/URI/headers/retrieve/body, cấu hình credential hoặc endpoint test, phụ thuộc mạng và provider đang online. Khi tách port và adapter, unit test chỉ cần cung cấp một kết quả rate đã biết cho business service. Phần HTTP được kiểm tra riêng ở adapter test.

## 2. Adapter là gì?

**Adapter** là thành phần chuyển đổi giữa contract mà ứng dụng mong muốn và API/giao thức mà một hệ thống khác cung cấp.

Ví dụ:

- Ứng dụng muốn hỏi “giá hiện tại của SKU là bao nhiêu?”.
- Provider cung cấp HTTP endpoint `/v2/catalog/items/{id}` với JSON có field `current_amount`.
- Adapter gọi endpoint, xử lý HTTP response, chuyển JSON thành kiểu dữ liệu nội bộ rồi trả về contract mà ứng dụng hiểu.

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

Adapter là một **translator** ở ranh giới. Nó giữ cho chi tiết của provider không lan sâu vào business code.

### 2.1. Adapter không chỉ dành cho HTTP

| Hệ thống bên ngoài | Adapter có thể làm gì? |
|---|---|
| Payment gateway | Gọi API thanh toán, map trạng thái provider sang trạng thái nội bộ |
| Database | Chuyển domain object sang entity và gọi Spring Data repository |
| Message broker | Publish/consume message và map event schema |
| Email provider | Chuyển yêu cầu gửi email sang SDK/API cụ thể |
| Filesystem | Đọc/ghi file theo contract storage |
| Cloud object storage | Chuyển object key và stream sang SDK của cloud |
| Clock | Cung cấp thời gian hiện tại thông qua abstraction có thể thay thế |
| Identity provider | Đổi token/provider response thành identity model của ứng dụng |

Không cần tạo adapter cho mọi method hoặc mọi class. Hãy dùng khi có ranh giới kỹ thuật/nhà cung cấp mà bạn muốn cô lập.

## 3. Ports and Adapters (Hexagonal Architecture)

Mô hình **Ports and Adapters**, còn gọi là **Hexagonal Architecture**, đặt application core ở trung tâm. Các thành phần bên ngoài kết nối với core qua những port (contract) và adapter (implementation).

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

### 3.1. Inbound port

Inbound port mô tả hành động mà ứng dụng cho phép bên ngoài yêu cầu.

```java
public interface PlaceOrderUseCase {
    OrderReceipt placeOrder(PlaceOrderCommand command);
}
```

Controller là inbound adapter: nó nhận HTTP request, chuyển thành command rồi gọi use case.

### 3.2. Outbound port

Outbound port mô tả khả năng mà application core cần từ bên ngoài.

```java
public interface PaymentPort {
    PaymentResult charge(PaymentCommand command);
}
```

Application service gọi `PaymentPort`. Nó không cần biết implementation dùng SDK nào.

### 3.3. Dependency direction

Một nguyên tắc quan trọng là **business/application layer định nghĩa contract mà nó cần**. Adapter bên ngoài phụ thuộc vào contract đó.

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

Điều này giúp business code không phụ thuộc SDK cụ thể, adapter có thể thay đổi mà không sửa business rule, test có thể cung cấp fake implementation và provider-specific DTO/exceptions được giữ ở ranh giới.

### 3.4. Interface nên thuộc về phía cần nó

Nếu `CheckoutService` cần chức năng lấy giá, contract nên phản ánh ngôn ngữ của checkout application:

```java
public interface ProductPricingPort {
    Money priceOf(ProductId productId);
}
```

Tránh lấy nguyên interface từ vendor SDK rồi bắt application core phụ thuộc vào nó. Contract của provider thường được thiết kế theo giao thức hoặc sản phẩm của provider, không nhất thiết theo nhu cầu của ứng dụng.

Không nên:

```java
public interface PaymentPort {
    com.vendor.sdk.PaymentResponse charge(
            com.vendor.sdk.PaymentRequest request
    );
}
```

Tốt hơn:

```java
public interface PaymentPort {
    PaymentResult charge(PaymentCommand command);
}
```

Các kiểu `PaymentCommand` và `PaymentResult` thuộc application/domain model do project kiểm soát.

## 4. Thiết kế port nhỏ, diễn đạt theo nghiệp vụ

Port là contract, vì vậy method name nên diễn tả khả năng ứng dụng cần thay vì cách provider triển khai.

Ví dụ không rõ ranh giới:

```java
public interface ExternalApiClient {
    ResponseEntity<String> get(String url);
    ResponseEntity<String> post(String url, Object body);
}
```

Interface này chỉ bọc HTTP client. Nó buộc business service biết URL, HTTP status và response parsing.

Tốt hơn:

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

Contract diễn đạt nghiệp vụ inventory. Adapter có thể hiện thực bằng REST, gRPC hoặc một hệ thống inventory khác.

Không nên tạo một interface quá rộng kiểu `Object execute(String action, Map<String, Object> data)` vì contract quá chung làm mất kiểu dữ liệu, khó hiểu và khó test. Ngược lại, cũng không cần tạo abstraction cho mọi class. Hãy tạo port khi có ranh giới bên ngoài cần cô lập, có thể thay đổi hoặc cần thay thế trong test.

## 5. Ví dụ xuyên suốt: tích hợp payment gateway

Ta xây một luồng thanh toán đơn giản. Checkout service nhận order ID và amount, gọi payment port, adapter chuyển request sang API provider, provider response được map thành kết quả nội bộ và unit test có thể kiểm tra checkout mà không gọi mạng.

### 5.1. Domain/application types

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

Các kiểu này thuộc application model. Chúng không phụ thuộc JSON schema hoặc class của provider.

### 5.2. Định nghĩa outbound port

```java
package com.example.checkout;

public interface PaymentPort {
    PaymentResult charge(PaymentCommand command);
}
```

Port chỉ thể hiện hành động mà checkout cần. Nó không nhắc tới HTTP method, endpoint, SDK hay authentication header.

### 5.3. Business service phụ thuộc port

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

`CheckoutService` chỉ biết `PaymentPort`. Nó không cần biết adapter sử dụng `RestClient` hay một SDK khác.

### 5.4. Provider DTO nằm trong adapter

Giả sử provider nhận JSON:

```json
{
  "merchant_order": "ORD-100",
  "amount_value": 125000,
  "currency_code": "VND"
}
```

và trả:

```json
{
  "payment_reference": "pay-abc",
  "result_code": "SUCCESS"
}
```

Tạo DTO riêng cho giao thức:

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

Tên field trong DTO này phản ánh JSON provider. Nếu dùng Jackson naming strategy hoặc annotation, có thể viết Java field theo camelCase nhưng map sang tên JSON. Điều quan trọng là các DTO này chỉ nằm ở integration boundary.

### 5.5. Adapter hiện thực port

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

Adapter chịu trách nhiệm map application command sang provider request, gọi endpoint, decode response, chuyển result code thành enum nội bộ và không để provider response type lọt ra ngoài port.

Trong production, adapter còn cần xử lý authentication, timeout, retry policy, correlation IDs và lỗi mạng.

### 5.6. Exception tại integration boundary

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

Tùy thiết kế, bạn có thể đặt một exception contract chung trong application layer, ví dụ `PaymentUnavailableException`, rồi adapter map provider-specific errors thành loại đó. Như vậy application service không cần bắt exception của vendor.

## 6. Cấu hình adapter bằng Spring dependency injection

Adapter là Spring bean và được inject qua port.

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

Trong project thực tế, URL nên đến từ externalized configuration hoặc một `@ConfigurationProperties` object, không hard-code vào business service. Ví dụ cấu hình:

```yaml
payment:
  api:
    base-url: https://payments.example.com
    connect-timeout: 2s
    read-timeout: 5s
```

Spring Boot cung cấp builder được auto-configure khi có web client support phù hợp. Nếu project tự tạo nhiều `RestClient` beans, nên đặt tên/qualifier rõ ràng để adapter nhận đúng client.

### 6.1. Constructor injection làm dependency rõ ràng

```java
@Component
public class HttpPaymentAdapter implements PaymentPort {

    private final RestClient restClient;

    public HttpPaymentAdapter(RestClient paymentRestClient) {
        this.restClient = paymentRestClient;
    }
}
```

Và:

```java
@Service
public class CheckoutService {

    private final PaymentPort paymentPort;

    public CheckoutService(PaymentPort paymentPort) {
        this.paymentPort = paymentPort;
    }
}
```

Spring tìm bean implement `PaymentPort` rồi inject vào service. Nếu có nhiều adapter cùng implement port, cần dùng `@Qualifier`, `@Primary` hoặc một cấu hình lựa chọn rõ ràng.

### 6.2. Đừng inject adapter cụ thể vào application service

Không nên:

```java
@Service
public class CheckoutService {

    private final HttpPaymentAdapter adapter;

    public CheckoutService(HttpPaymentAdapter adapter) {
        this.adapter = adapter;
    }
}
```

Cách này làm service phụ thuộc vào implementation. Dùng port:

```java
private final PaymentPort paymentPort;
```

Giờ bạn có thể thay `HttpPaymentAdapter` bằng fake, sandbox adapter hoặc một provider khác mà không sửa business service.

## 7. Unit test service bằng fake adapter

Một lợi ích lớn nhất của port là có thể tạo một fake implementation trong test.

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

Test này không khởi động Spring, không gọi HTTP, không cần provider credentials và không phụ thuộc mạng. Nó kiểm tra application service gọi port với dữ liệu đúng.

### 7.1. Fake khác mock thế nào?

**Fake** là implementation đơn giản có behavior thật trong phạm vi test, ví dụ in-memory store hoặc fake payment port.

**Mock** là test double được cấu hình để trả giá trị và/hoặc xác nhận tương tác.

Cả hai đều có ích. Fake phù hợp khi muốn mô phỏng một contract với trạng thái dễ hiểu; mock phù hợp khi cần kiểm tra một interaction cụ thể.

### 7.2. Unit test business rule, không test chi tiết HTTP

Trong `CheckoutServiceTest`, không cần assert URL, JSON field hoặc HTTP header. Đó là trách nhiệm của adapter test.

Nếu unit test service biết `/v1/payments`, nghĩa là chi tiết integration đã rò vào business layer.

## 8. Dùng Mockito để test port interaction

Nếu không muốn tạo fake class:

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

Mockito test này chứng minh service gọi đúng contract. Nó không chứng minh HTTP adapter có gửi request đúng, cũng không chứng minh provider thực sự xử lý payment.

Nếu application service cần chuyển lỗi integration thành business outcome, hãy kiểm tra mapping đó bằng behavior test. Đừng để service âm thầm nuốt mọi exception.

## 9. Kiểm thử adapter riêng với MockRestServiceServer

Unit test của service không kiểm tra HTTP request. Muốn xác nhận adapter gọi đúng endpoint, method, headers và payload, hãy viết adapter test.

Spring cung cấp `MockRestServiceServer` hỗ trợ kiểm tra HTTP client mà không cần gọi mạng thật. Với Spring Framework 6.1 trở lên, nó hỗ trợ `RestClient.Builder`.

Ví dụ:

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

Ví dụ này giả định Jackson JSON converter phù hợp có trên classpath để `RestClient` deserialize response record. Với ứng dụng Spring Boot có web starter phù hợp, converter thường được auto-configure khi dùng Boot builder; trong test tạo builder thuần, cần bảo đảm dependency converter có mặt hoặc cấu hình message converters tương ứng.

### 9.1. Kiểm tra request body và header

Bạn có thể thêm matcher để kiểm tra JSON body:

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

Và kiểm tra header authentication hoặc correlation ID. Trong test, dùng key giả. Không đưa secret production vào source hoặc test fixture.

## 10. @RestClientTest trong Spring Boot

Spring Boot có test slice `@RestClientTest` cho một số ứng dụng dùng `RestClient`, `RestTemplate` và các thành phần liên quan.

```java
@RestClientTest(HttpPaymentAdapter.class)
class HttpPaymentAdapterSliceTest {

    @Autowired
    HttpPaymentAdapter adapter;

    @Autowired
    MockRestServiceServer server;
}
```

Test slice này tập trung vào client-side components và cấu hình converter phù hợp, giúp không cần load full application context. Cách cấu hình chi tiết phụ thuộc version Spring Boot, loại HTTP client và bean `RestClient.Builder` mà adapter sử dụng. Hãy đối chiếu API với version trong project.

Dùng nó để kiểm tra JSON serialization/deserialization, request method/URL/headers, mapping response provider sang application model, mapping status code và provider error. Không dùng nó để chứng minh toàn bộ business workflow hoặc database integration hoạt động.

## 11. Adapter cho database

Database cũng là một hệ thống bên ngoài đối với application core. Bạn có thể định nghĩa persistence port theo ngôn ngữ domain.

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

Spring Data repository nằm ở adapter:

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

Application core không cần biết JPA entity, `JpaRepository`, table mapping hoặc SQL dialect.

### 11.1. Có nên luôn tạo repository port?

Không bắt buộc. Một ứng dụng Spring Data đơn giản có thể dùng repository interface trực tiếp ở service nếu ranh giới domain/application không cần cô lập thêm.

Port/adapter hữu ích hơn khi domain model khác persistence model, muốn giữ JPA annotations ngoài domain, có nhiều persistence implementations, business logic cần test không tải JPA hoặc database technology là chi tiết cần thay đổi độc lập.

### 11.2. Kiểm thử database adapter

Dùng `@DataJpaTest` hoặc integration test với database tương thích để xác nhận entity mapping, query behavior, constraints, transaction semantics và mapping giữa entity với domain object.

Unit test của application service chỉ cần fake `OrderStore`; nó không chứng minh SQL query đúng.

## 12. Adapter cho message broker

Giả sử application cần phát một event khi order được xác nhận.

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

Adapter có thể dùng Kafka:

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

Application core không phụ thuộc `KafkaTemplate` hoặc topic name.

### 12.1. Publish thành công có nghĩa gì?

Lời gọi `kafka.send(...)` có thể trả về future; không nên mặc định message đã được broker xác nhận chỉ vì method trả về.

Adapter cần quyết định contract có đồng bộ chờ broker ack, trả kết quả async hay báo lỗi qua callback/future. Port nên phản ánh semantics mà application cần.

### 12.2. Database và broker có thể không atomic

Nếu service ghi database rồi publish message, một lỗi giữa hai bước có thể khiến database đã commit nhưng message chưa được gửi. Port/adapter không tự giải quyết vấn đề consistency phân tán. Với yêu cầu delivery bền vững, cân nhắc transactional outbox, CDC hoặc cơ chế messaging phù hợp.

### 12.3. Consumer cũng là adapter

Một message listener nhận DTO từ broker là inbound adapter:

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

Listener chuyển broker schema sang application command. Business use case không cần import `@KafkaListener` hoặc biết Kafka record metadata.

## 13. Adapter cho filesystem, object storage và Clock

Một ứng dụng lưu tài liệu có thể định nghĩa port:

```java
public interface DocumentStoragePort {
    StoredDocument store(DocumentContent content);
    Optional<DocumentContent> load(DocumentId id);
}
```

Adapter filesystem hoặc S3 có thể hiện thực cùng contract nếu semantics phù hợp. Adapter filesystem cần chống path traversal, kiểm tra permissions, xử lý file lớn theo stream và xác định atomicity của write. Adapter cloud storage cần quản lý credentials, bucket policy, timeout, retry và lỗi provider.

Một fake in-memory storage có thể lưu `Map<DocumentId, DocumentContent>` để test business behavior mà không tạo file thật. Adapter filesystem vẫn cần integration tests trên temporary directory để kiểm tra path, encoding và IO behavior.

Đồng hồ hệ thống là một dependency bên ngoài khó kiểm soát nếu code gọi trực tiếp `LocalDateTime.now()` ở nhiều nơi. Java đã có abstraction `java.time.Clock`:

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

Cấu hình Spring:

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

Test có thể kiểm soát thời điểm, không phụ thuộc giờ chạy máy. `Clock` là abstraction có sẵn; bạn không nhất thiết phải bọc nó trong một interface riêng nữa.

## 14. Mapping lỗi tại adapter boundary

External systems có thể trả nhiều dạng lỗi: HTTP 400/401/403/404/409/429/5xx, timeout, connection refused, response sai schema, provider business error, SDK exception, broker rejection hoặc database constraint violation.

Không nên để business service phụ thuộc mọi exception class của từng vendor.

Ví dụ application exception:

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

Adapter có thể bắt lỗi transport:

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

Application service chỉ cần hiểu `PaymentUnavailableException` nếu nó có behavior cụ thể khi provider không khả dụng.

### 14.1. Không biến mọi lỗi thành một kết quả chung

Nếu adapter bắt tất cả exception và trả `PaymentStatus.DECLINED`, ứng dụng sẽ không phân biệt được khách hàng bị từ chối thanh toán, provider timeout, credential hết hạn, provider lỗi server hoặc request bị gửi sai.

Các trường hợp này có business semantics khác nhau. Hãy map error categories rõ ràng.

### 14.2. Giữ cause để điều tra

Khi wrap exception, truyền original cause:

```java
throw new PaymentUnavailableException(
        "Payment provider timed out",
        ex
);
```

Nhờ vậy, logs có thể hiển thị exception gốc trong cause chain. Không đưa raw provider response chứa secrets hoặc dữ liệu nhạy cảm vào exception message.

## 15. Timeout, retry, circuit breaker và idempotency

Một adapter gọi hệ thống ngoài nên có chính sách resilience phù hợp.

### 15.1. Timeout

Không nên để HTTP request chờ vô hạn. Cấu hình connect/read/response timeout theo HTTP client đang dùng và mục tiêu latency của ứng dụng.

Timeout cần phù hợp với API deadline của caller, tổng thời gian retry, thread pool capacity, provider latency baseline và timeout của reverse proxy/load balancer.

### 15.2. Retry

Chỉ retry lỗi có khả năng tạm thời và operation an toàn để retry.

- Connection reset có thể retry.
- HTTP 429 có thể cần backoff và tôn trọng Retry-After.
- HTTP 400 do request invalid thường không nên retry.
- Payment charge có side effect nên cần idempotency key trước khi retry.

Đừng retry mọi exception theo một vòng lặp cố định. Nó có thể khuếch đại sự cố của provider.

### 15.3. Circuit breaker

Circuit breaker có thể ngăn ứng dụng tiếp tục gọi một dependency đang thất bại liên tục. Adapter là nơi hợp lý để áp dụng policy cho outbound call, nhưng business service cần hiểu fallback semantics nếu có.

Ví dụ fallback có thể là “giá chưa có, trả về unavailable” chứ không được tự ý dùng một giá cũ nếu nghiệp vụ không cho phép.

### 15.4. Idempotency

Với operation có side effect như charge payment hoặc tạo shipment, retry có thể tạo thao tác trùng. Adapter có thể chuyển một idempotency key ổn định tới provider, nhưng key nên được tạo/định nghĩa theo business operation và được duy trì xuyên retry.

Port có thể mang `PaymentCommand` chứa `paymentAttemptId` hoặc `idempotencyKey` nếu đây là một phần contract ứng dụng cần kiểm soát.

## 16. Cấu hình provider không nên nằm trong business service

Không nên tự tạo client và hard-code endpoint/credential trong constructor của service. Cách đó làm service khó test, khó đổi sandbox/production và có nguy cơ lộ secret.

Đặt cấu hình tại application configuration:

```yaml
payment:
  api:
    base-url: https://payments.example.com
    connect-timeout: 2s
    read-timeout: 5s
```

Có thể dùng `@ConfigurationProperties` cho cấu hình có cấu trúc:

```java
@ConfigurationProperties(prefix = "payment.api")
public record PaymentApiProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout
) {
}
```

Adapter configuration nhận properties và tạo HTTP client phù hợp.

### 16.1. Secret management

API key/password nên lấy từ secret store hoặc environment-specific configuration được bảo vệ. Không commit credential thật vào `application.yml`, không ghi token vào logs và không đưa secrets vào test fixtures.

### 16.2. Profiles không nên là cách duy nhất để chọn provider

Có thể dùng profiles để cấu hình endpoint/test adapter, nhưng lựa chọn provider nên rõ ràng trong dependency wiring. Đừng để application core đọc `spring.profiles.active` để tự quyết định gọi vendor A hay vendor B.

## 17. Nhiều adapter cho cùng một port

Có thể có nhiều implementation hợp lệ:

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

Nếu application cần chọn theo cấu hình, có thể dùng một routing adapter hoặc bean condition.

`@Primary` chọn bean ưu tiên khi có nhiều candidates. `@Qualifier` giúp chỉ rõ implementation:

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

Tên qualifier là chi tiết wiring. Business service vẫn phụ thuộc interface `PaymentPort`, không phụ thuộc class provider.

Nếu chọn provider theo property, có thể dùng `@ConditionalOnProperty` ở configuration/adapter bean. Hãy bảo đảm chỉ có một implementation phù hợp cho môi trường đó và có lỗi startup rõ ràng khi cấu hình không hợp lệ.

## 18. Adapter test và contract test khác nhau thế nào?

| Test | Kiểm tra điều gì? | Có provider thật? |
|---|---|---|
| Unit test application service | Business rule và port usage | Không |
| Adapter unit/slice test | Request/response mapping, headers, error mapping | Không; dùng mock server |
| Contract test | Application và provider cùng hiểu API contract | Thường dùng stub/provider contract |
| Integration test | Kết nối với test instance hoặc sandbox | Có thể có |
| End-to-end test | Luồng toàn hệ thống qua các boundary | Thường có một môi trường tích hợp |

### 18.1. Mock server test

Dùng `MockRestServiceServer`, WireMock hoặc MockWebServer để kiểm tra HTTP behavior mà không gọi internet.

### 18.2. Contract test

Nếu provider có OpenAPI schema hoặc Pact contract, kiểm tra adapter gửi request/đọc response đúng contract đã thỏa thuận. Contract test giúp phát hiện breaking change ở ranh giới API.

### 18.3. Sandbox integration test

Một số payment/email/cloud providers có sandbox. Có thể chạy test ít thường xuyên hơn với credentials sandbox, nhưng test phải có timeout, dữ liệu riêng và cleanup. Không dùng giao dịch tiền thật trong test tự động thông thường.

## 19. WireMock cho HTTP adapter integration test

WireMock có thể chạy một HTTP server giả lập provider.

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

Sau đó tạo `RestClient` trỏ về WireMock server và gọi adapter.

Bạn có thể kiểm tra request method/path, header authentication (dùng token giả), body schema, response mapping, status code error, timeout/connection failure và retry behavior nếu adapter được cấu hình retry.

Mỗi test nên reset WireMock mappings/request journal hoặc dùng instance riêng. Nếu state server bị chia sẻ giữa tests, test chạy riêng có thể xanh nhưng suite chạy song song lại thất bại.

## 20. Kiểm thử persistence và message adapter

Tương tự HTTP adapter, database adapter cần test riêng. Một `@DataJpaTest` có thể kiểm tra Spring Data repository. Nếu có mapper/adapter bổ sung, inject chúng trong test slice hoặc dùng integration test cấu hình đầy đủ hơn.

H2 có thể phù hợp cho test persistence đơn giản. Testcontainers với PostgreSQL/MySQL phù hợp khi cần dialect và constraint tương thích production. In-memory fake phù hợp cho unit tests của business logic, không thay thế database integration tests.

Với Kafka/RabbitMQ hoặc broker khác, tách test business service gọi outbound port, adapter map event sang message schema, broker integration xác nhận publish/consume behavior và consumer adapter map message thành application command/event. Unit test application service có thể fake `OrderEventPublisher`; integration test adapter có thể dùng broker test container.

## 21. Mapping DTO và domain model tại adapter boundary

External API thường có schema không trùng domain model.

Ví dụ provider trả:

```json
{
  "payment_reference": "p-100",
  "result_code": "SUCCESS",
  "provider_timestamp": "2026-02-01T10:15:30Z"
}
```

Application có thể chỉ cần:

```java
public record PaymentResult(
        TransactionId transactionId,
        PaymentStatus status
) {
}
```

Adapter map:

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

Nếu provider đổi `payment_reference` thành `transaction_ref`, chỉ adapter DTO/mapper cần cập nhật, miễn application contract không đổi.

Không nên trả nguyên `Map<String, Object>` hoặc provider DTO qua port chỉ vì nó tiện. Điều này tạo coupling ngầm: consumer có thể bắt đầu phụ thuộc field provider-specific và làm mất giá trị của adapter.

Chỉ giữ field thực sự cần cho nghiệp vụ, audit hoặc support. Nếu cần provider reference để tra soát, biểu diễn nó thành application value object như `ProviderTransactionId`, không để toàn bộ vendor response trôi vào core.

## 22. Anti-corruption layer và adapter

Trong hệ thống lớn, adapter đôi khi đóng vai trò **anti-corruption layer**: bảo vệ mô hình nội bộ khỏi cách diễn đạt và assumptions của hệ thống ngoài.

Ví dụ:

- Provider dùng status `S`, `F`, `P`.
- Domain dùng `APPROVED`, `DECLINED`, `PENDING`.
- Provider biểu diễn amount bằng integer minor units.
- Domain dùng `Money` với currency rõ ràng.
- Provider dùng UTC timestamp dạng string.
- Domain dùng `Instant`.
- Provider gọi customer là `account_holder`.
- Domain dùng `CustomerId`.

Adapter chuyển đổi cả schema lẫn semantics, không chỉ đổi tên field.

Nếu provider gửi amount bằng cents, chuyển đổi cần dựa vào quy tắc currency rõ ràng. Đừng giả định mọi currency đều có hai chữ số thập phân. Với tiền tệ, dùng domain money type và currency metadata phù hợp thay vì hard-code conversion chung.

Nếu provider A hỗ trợ authorization/capture riêng, còn provider B chỉ charge ngay, adapter không nên giả vờ cả hai có cùng semantics nếu không thể thực hiện tương đương. Port phải mô tả capability thật sự mà application có thể dựa vào.

## 23. Adapter không tự giải quyết transaction phân tán

Một service có thể gọi database lưu order, payment provider charge và message broker publish event. Dù ba thao tác đều được bọc bằng adapter, chúng vẫn không tự trở thành một transaction atomic duy nhất.

Nếu bước 2 thành công nhưng bước 3 thất bại, trạng thái hệ thống có thể không nhất quán.

### 23.1. Saga/compensation

Một workflow có thể cần ghi order pending, charge payment, xác nhận order và nếu bước sau thất bại thì thực hiện refund/compensation theo business policy. Adapter giúp cô lập từng integration, còn saga/workflow quản lý trạng thái phân tán.

### 23.2. Outbox

Nếu cần bảo đảm database update và event publication không bị tách rời, transactional outbox thường là một lựa chọn:

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

Outbox adapter có thể hiện thực persistence/publishing details. Application workflow vẫn cần idempotency và retry phù hợp.

## 24. Kiểm thử configuration và chọn adapter

Một lỗi thường gặp là có interface và adapter nhưng Spring không tạo được đúng implementation.

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

Nếu chạy với profile `test` mà không có adapter nào, `CheckoutService` có thể không được inject.

Có thể khai báo fake bean trong test configuration:

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

Và import vào test:

```java
@SpringBootTest
@Import(PaymentTestConfiguration.class)
class CheckoutIntegrationTest {
}
```

Nếu production adapter vẫn được scan và cùng type, `@Primary` có thể chọn fake cho injection; tuy nhiên, cần tránh khởi tạo production adapter có side effects trong test. Có thể dùng profile/conditional configuration hoặc bean override rõ ràng hơn.

Một context test xác nhận Spring tìm được `PaymentPort` bean. Một behavior test xác nhận checkout xử lý approved/declined/unavailable đúng. Adapter test xác nhận HTTP request/response đúng. Ba mục tiêu cần được kiểm tra riêng hoặc kết hợp có chủ đích.

## 25. Cấu trúc package gợi ý

Với một ứng dụng nhỏ:

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

Với application lớn hơn, có thể tổ chức theo feature:

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

Không có một cấu trúc package duy nhất bắt buộc. Điều cần giữ là dependency direction: core không import vendor types và adapter phụ thuộc vào port/domain contract phù hợp.

Tránh đưa HTTP client, repository, mapper, payment SDK và message publisher vào một package `utils` làm mất ranh giới. Tên package nên thể hiện capability hoặc boundary: `adapter.payment`, `adapter.persistence`, `adapter.messaging`.

## 26. Những lỗi thường gặp khi thiết kế adapter

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Service vẫn import vendor SDK | Port chứa vendor types hoặc service inject implementation | Đưa contract về application model và inject interface |
| Unit test cần mock RestClient fluent chain | Business service gọi HTTP trực tiếp | Tách outbound port và adapter |
| Test service gọi internet | Adapter thật được dùng trong unit test | Dùng fake/mock port |
| Adapter không được inject | Không có bean, sai component scan/profile | Kiểm tra registration và active profile |
| Có hai bean cùng implement port | Nhiều adapter được đăng ký đồng thời | Dùng qualifier/primary/condition |
| Provider đổi JSON làm nhiều service phải sửa | Provider DTO rò khỏi adapter | Map response tại boundary |
| Provider 500 bị hiểu là payment declined | Error mapping quá đơn giản | Phân biệt decline, unavailable và technical failure |
| Retry tạo charge trùng | Không có idempotency | Dùng idempotency key ổn định |
| Test adapter chỉ assert output, không kiểm tra request | Thiếu request matchers | Assert method, URI, headers và body |
| Fake test xanh nhưng database lỗi | Fake không kiểm tra SQL/JPA | Bổ sung repository integration test |
| App publish event nhưng broker không nhận | Adapter async/ack semantics chưa được kiểm tra | Test future/ack và broker integration |
| Profile test thiếu port bean | Adapter production chỉ active profile khác | Đăng ký test adapter/configuration |
| Adapter quá lớn | Một class quản lý nhiều provider/capability | Chia theo port hoặc responsibility |
| Có interface cho mọi class nhưng không giảm coupling | Abstraction không có boundary rõ | Chỉ tạo port nơi cần thay thế/kiểm soát dependency |
| Business service xử lý HTTP status | Transport detail rò vào core | Map status/error trong adapter |

## 27. Quy trình refactor tích hợp trực tiếp thành adapter

Giả sử một service hiện đang gọi provider trực tiếp.

1. **Xác định nhu cầu của business service:** liệt kê đúng các thao tác ứng dụng cần từ provider, ví dụ `charge`, `refund`, `lookupTransaction`.
2. **Định nghĩa port theo ngôn ngữ application:** dùng application/domain types; tránh `ResponseEntity`, vendor DTO và SDK classes.
3. **Chuyển code giao thức vào adapter:** di chuyển URL, headers, authentication, serialization, status mapping và provider error handling.
4. **Inject port vào service:** dùng constructor injection; không tự tạo adapter bằng `new` trong business service.
5. **Đăng ký adapter bằng Spring:** dùng `@Component`/`@Repository`, `@Bean`, `@Configuration`, profiles hoặc conditions tùy nhu cầu.
6. **Viết unit tests cho application service:** dùng fake/mock port, kiểm tra business rules, output, error handling và side effects.
7. **Viết adapter tests:** dùng mock HTTP server, broker test hoặc filesystem temporary directory để xác nhận protocol mapping.
8. **Viết integration tests cho các rủi ro quan trọng:** dùng sandbox/provider test environment, Testcontainers hoặc contract tests nếu cần.
9. **Kiểm tra dependency direction:** application core không được import provider SDK/HTTP DTO; adapter được phép phụ thuộc vào port và công nghệ cụ thể.
10. **Kiểm tra vận hành:** timeout, retries, idempotency, authentication, logging, metrics, secrets và failure semantics phải rõ ràng.

## 28. Khi nào nên dùng fake, mock hay adapter integration test?

| Mục tiêu | Lựa chọn phù hợp |
|---|---|
| Kiểm tra business rules nhanh | Fake/mock port trong unit test |
| Kiểm tra service truyền command đúng | Mock port hoặc recording fake |
| Kiểm tra JSON request/response | MockRestServiceServer/WireMock |
| Kiểm tra SQL và mapping JPA | `@DataJpaTest`/Testcontainers |
| Kiểm tra message schema và broker behavior | Broker test container hoặc contract test |
| Kiểm tra provider sandbox | Integration test có kiểm soát |
| Kiểm tra toàn bộ request flow | `@SpringBootTest`/HTTP integration test |
| Kiểm tra bean wiring | Context test với đúng profiles/config |

Không cần chạy mọi loại test cho mỗi thay đổi. Chọn test dựa vào phần code và rủi ro đã thay đổi.

## 29. Bài thực hành

### Bài 1 — Tách HTTP call khỏi service

Tạo `CurrencyConversionService` đang dùng `RestClient` trực tiếp. Định nghĩa `ExchangeRatePort`, chuyển HTTP logic sang `HttpExchangeRateAdapter` và sửa service chỉ inject port.

### Bài 2 — Viết fake adapter

Tạo `FakeExchangeRateAdapter` trả về rate cố định. Viết unit test xác nhận số tiền sau quy đổi đúng mà không khởi động Spring hoặc gọi mạng.

### Bài 3 — Kiểm tra error behavior

Cho fake adapter ném `ExchangeRateUnavailableException`. Kiểm tra service propagate hoặc chuyển lỗi theo business contract.

### Bài 4 — Mapping provider DTO

Tạo provider response có field tên khác domain model. Viết mapper trong adapter và kiểm tra application chỉ nhận `ExchangeRate`.

### Bài 5 — MockRestServiceServer

Viết test adapter xác nhận HTTP method, URI, request JSON, response JSON và header. Dùng URL test, không dùng provider thật.

### Bài 6 — Test HTTP error mapping

Giả lập provider trả 400, 401, 429 và 503. Thiết kế mapping khác nhau cho invalid request, credential issue, rate limit và unavailable.

### Bài 7 — Persistence port

Định nghĩa `OrderStore`, viết `JpaOrderStoreAdapter` dựa trên Spring Data repository. Kiểm tra service bằng fake và adapter bằng `@DataJpaTest`.

### Bài 8 — Message publisher port

Định nghĩa `OrderEventPublisher`, viết Kafka adapter. Unit test service bằng fake publisher và integration test adapter với broker test environment.

### Bài 9 — Clock injection

Inject `Clock` vào `CouponService`. Viết tests bằng `Clock.fixed` cho trước, đúng và sau thời điểm hết hạn.

### Bài 10 — Nhiều payment providers

Tạo hai implementation `PaymentPort`, chọn bằng qualifier hoặc conditional configuration. Viết context test cho từng cấu hình để xác nhận chỉ một adapter phù hợp được inject.

### Bài 11 — Idempotency

Thêm idempotency key vào `PaymentCommand`. Xác nhận adapter gửi key trong HTTP header/request theo provider contract và retry không tạo giao dịch trùng trong sandbox test.

### Bài 12 — Timeout và retry

Cấu hình timeout cho HTTP client, mô phỏng timeout bằng mock server và kiểm tra application nhận lỗi nội bộ ổn định. Xác nhận retry chỉ áp dụng với lỗi retryable.

### Bài 13 — Test không phụ thuộc vendor

Tìm các import vendor SDK trong application/domain packages. Chuyển chúng về adapter, sau đó chạy unit tests chỉ với fake implementations.

### Bài 14 — Contract test

Mô tả contract của provider bằng OpenAPI/Pact hoặc fixture. Viết test xác nhận request/response mapping của adapter khớp contract.

### Bài 15 — Tách một adapter quá lớn

Tạo một adapter có cả payment, refund và customer lookup. Chia port theo capability nếu các trách nhiệm có thể thay đổi độc lập, rồi đánh giá dependency và test setup.

### Bài 16 — Kiểm tra dependency direction

Vẽ dependency graph của application core và adapters. Đảm bảo core chỉ phụ thuộc các contract/model nội bộ và adapter phụ thuộc vào technology/provider cụ thể.

## 30. Tài liệu tham khảo chính thức

- [Spring Framework Reference — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, `WebClient` và các HTTP client abstraction.
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): test slices, application integration tests và test support.
- [Spring Boot Reference — @RestClientTest](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): hỗ trợ test REST clients theo version.
- [Spring Framework Reference — MockRestServiceServer](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): kiểm thử client HTTP với mock server.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/): repository abstraction và persistence integration.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): producer/consumer integration và testing.
- [Martin Fowler — Ports and Adapters](https://martinfowler.com/articles/hexagonal-architecture.html): mô hình kiến trúc ports-and-adapters.
- [Testcontainers Documentation](https://java.testcontainers.org/): kiểm thử integration với database và dịch vụ chạy trong containers.
- [Java API — java.time.Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): abstraction thời gian có thể thay thế trong tests.

**Nguyên tắc quan trọng:** application service nên phụ thuộc vào contract diễn đạt điều nó cần; adapter hiện thực contract bằng HTTP, database, broker hoặc SDK cụ thể. Nhờ vậy, business tests dùng fake/mock để kiểm tra quy tắc nhanh và ổn định, còn adapter tests tập trung vào protocol, serialization, error mapping và integration. Adapter không tự làm hệ thống phân tán trở nên atomic, không thay thế timeout/idempotency/retry policy và cũng không phải lý do để tạo interface cho mọi class. Hãy đặt ranh giới ở nơi chi tiết bên ngoài cần được cô lập, giữ provider-specific data trong adapter, và kiểm thử từng ranh giới bằng loại test phù hợp.

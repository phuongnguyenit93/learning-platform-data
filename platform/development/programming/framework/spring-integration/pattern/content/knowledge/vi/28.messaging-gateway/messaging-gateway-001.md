# Messaging Gateway che giấu MessageChannel phía sau API

Khi xây dựng luồng tích hợp với Spring Integration, một chương trình có thể trực tiếp tạo `Message<?>`, chọn `MessageChannel`, gọi `send()`, chuẩn bị `replyChannel` rồi tự đợi phản hồi. Cách làm này khiến **mã nghiệp vụ phụ thuộc vào hạ tầng messaging**: đổi từ xử lý đồng bộ sang queue, thêm Router hay Transformer có thể buộc nhiều service phải sửa code.

**Messaging Gateway** là một Enterprise Integration Pattern (EIP) tạo **giao diện gọi hàm quen thuộc** ở phía application và ẩn cách chuyển lời gọi đó thành message ở phía integration flow. Với Spring Integration, `@MessagingGateway` kết hợp với `@Gateway`, `GatewayProxyFactoryBean` và các message endpoints cho phép một bean client gọi:

~~~java
OrderQuote result = quoteGateway.quote(request, trustedTenant);
~~~

thay vì:

~~~java
Message<OrderQuoteRequest> message = MessageBuilder
        .withPayload(request)
        .setHeader("trustedTenant", trustedTenant)
        .build();

requestChannel.send(message);
// ... tự quản lý replyChannel, timeout, correlation và convert kết quả ...
~~~

Bài **Messaging Gateway che giấu MessageChannel phía sau API** thuộc chương **Messaging gateway** của module **SPRING_INTEGRATION_PATTERN**. Module hướng đến triển khai Enterprise Integration Patterns với Spring Integration để tạo luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, cùng kiểm thử và theo dõi các nhánh xử lý.

**Điểm cần nhớ:** Gateway giấu **API messaging** khỏi code nghiệp vụ, **không giấu được ngữ nghĩa** của request-reply, timeout, lỗi, retry, transaction, ACK hoặc thiếu phản hồi. Một method có chữ ký trả `OrderQuote` vẫn phải có một **reply message phù hợp** ở downstream; nếu flow chỉ drop message hoặc không hoàn tất, lời gọi method có thể timeout hoặc nhận `null` tùy cấu hình và phiên bản.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích Messaging Gateway EIP và vai trò của `GatewayProxyFactoryBean`.
2. So sánh gọi `MessageChannel.send()` trực tiếp với gọi Java interface được proxy.
3. Hiểu luồng **method invocation → Message → request channel → handler → reply channel → Java return value**.
4. Phân biệt **gateway proxy**, **inbound HTTP/JMS gateway**, **outbound gateway** và service activator.
5. Định nghĩa `@MessagingGateway`/`@Gateway`, `@Header` và cấu hình `@IntegrationComponentScan`.
6. Viết Spring Integration Java DSL flow request-reply với `DirectChannel`.
7. Test một gateway hoàn chỉnh mà mã caller không import `Message<?>` hoặc `MessageChannel`.
8. Nhận diện khác biệt `requestTimeout` và `replyTimeout`, nhất là khi downstream đồng bộ bị chặn.
9. Thiết kế hành vi khi Filter drop, Router không có route hoặc handler trả `null`.
10. Phân biệt method trả giá trị, method `void` và API bất đồng bộ `CompletableFuture<T>`.
11. Giữ correlation/reply metadata khi có Router, Transformer, Splitter/Aggregator và broker.
12. Phân loại validation error, timeout, infrastructure failure và unknown business outcome.
13. Đặt retry, idempotency, broker ACK và transaction theo đúng phạm vi.
14. Phân biệt Gateway API sync nội bộ với giao thức request-reply qua nhiều JVM.
15. Theo dõi latency, timeout, queue backlog và trace mà không tạo metric cardinality vô hạn.

## 2. Bài toán: tầng nghiệp vụ đang biết quá nhiều về message

Một service báo giá gọi message channel trực tiếp:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public final class DirectChannelQuoteCaller {

    private final MessageChannel channel;

    public DirectChannelQuoteCaller(MessageChannel channel) {
        this.channel = channel;
    }

    public void submit(
            OrderQuoteRequest request,
            String trustedTenant) {

        Message<OrderQuoteRequest> message =
                MessageBuilder.withPayload(request)
                        .setHeader(
                                "trustedTenant", trustedTenant)
                        .build();

        boolean sent = channel.send(message);
        if (!sent) {
            throw new IllegalStateException("SEND_FAILED");
        }
        // Chỉ xác nhận send; CHƯA có business reply ở ví dụ này.
    }
}
~~~

Code trên không hẳn sai, nhưng caller phải biết `MessageChannel`, `MessageBuilder` và tên header. Nếu API thực sự cần **trả giá báo thành công hoặc lý do từ chối**, method `void submit(...)` chưa đủ; caller còn phải tự thiết kế nhận reply và correlation.

Với Messaging Gateway, caller chỉ nhìn thấy:

~~~java
OrderQuote quote = quoteGateway.quote(
        new OrderQuoteRequest(
                "quote-1001", "tenant-a", "BOOK", 2),
        "tenant-a");
~~~

Caller không biết yêu cầu đi qua:

- `DirectChannel` hay `ExecutorChannel`.
- Transformer, Router, Filter hay Service Activator.
- Reply channel tạm và `MessageHeaders.REPLY_CHANNEL`.
- Những header nội bộ dùng theo dõi flow.

~~~mermaid
flowchart LR
    A["Application Service"] -->|"quote(request)"| G["Gateway Java Proxy"]
    G -->|"Message<OrderQuoteRequest>"| C["quote.requests"]
    C --> H["Validation / Quote Handler"]
    H -->|"OrderQuote reply"| R["Temporary replyChannel"]
    R --> G
    G -->|"OrderQuote"| A
~~~

**Gateway là boundary của abstraction**, không phải một business handler thần kỳ. Nó tạo/gửi message, quản lý cơ chế đợi phản hồi và biến reply thành giá trị method; **xử lý nghiệp vụ thực sự** vẫn nằm ở downstream flow.

## 3. Messaging Gateway EIP hoạt động ra sao?

### 3.1. Đầu vào là một method invocation

Ví dụ:

~~~java
OrderQuote quote(OrderQuoteRequest request, String tenantContext);
~~~

Gateway proxy lấy arguments từ lời gọi method, tạo payload và headers theo mapping contract. Method parameter có `@Header` trở thành message header; payload parameter trở thành payload.

### 3.2. Gửi qua request channel

Proxy gửi message vào `requestChannel` đã cấu hình, ví dụ `quote.requests`. Đầu nhận có thể là Transformer, Filter, Router, Service Activator hoặc flow đầy đủ.

### 3.3. Reply channel thường được tạo tạm

Đối với lời gọi **request-reply**, Spring Integration gateway thường tự tạo **một reply channel tạm, vô danh, point-to-point** và gắn nó vào header `replyChannel`. Endpoint downstream tạo một reply message; framework định tuyến reply đó về gateway để trả kết quả Java. Vì vậy **không cần** tạo một `QueueChannel` cố định cho mọi lời gọi để đợi reply, trừ khi topology có lý do cụ thể.

### 3.4. Trả về giá trị hoặc lỗi

- Reply payload tương thích return type → gateway trả về Java object.
- Handler ném exception → gateway thường truyền exception về caller theo error semantics (có thể unwrap một số wrapper).
- Không có reply → tùy topology/timeouts, method có thể chờ, trả `null` hoặc ném timeout khi bật policy tương ứng ở phiên bản hỗ trợ.
- Method `void` → không đợi business reply theo contract method, nhưng **không** có nghĩa send đã được broker persist hoặc mọi xử lý downstream đã hoàn thành.

### 3.5. Không đồng nhất send với xử lý thành công

~~~text
Gateway sent message successfully
     != Business DB transaction committed
     != Remote API completed
     != Broker ACK received
     != User received confirmed receipt
~~~

Một call thành công ở `MessageChannel.send()` chỉ có ngữ nghĩa của endpoint/channel cụ thể, không mặc nhiên là đảm bảo về business side effects.

## 4. Gateway che giấu cái gì và không che giấu cái gì?

| Nội dung | Gateway có thể che giấu? | Giải thích |
|---|---|---|
| Tạo `Message<?>` | Có | Proxy tạo message từ method args |
| Gọi `MessageChannel.send()` | Có | Application gọi Java interface |
| Tên request channel trong caller | Có | Nằm trong annotation/config |
| Cơ chế temporary reply channel | Có | Proxy quản lý request-reply |
| Chuyển reply thành method return | Có | Theo return type/converters |
| Nhiều endpoints Router/Filter/Transformer | Có ở API boundary | Flow vẫn cần cấu hình đúng |
| Có phản hồi hay không | **Không** | Downstream phải tạo reply đúng |
| Sự kiện được lưu bền | **Không** | Phụ thuộc transport/transaction |
| Exactly-once business side effect | **Không** | Cần idempotency/transaction |
| Network timeout và partition | **Không** | API vẫn có uncertainty |
| Data contract/schema | **Không** | Payload/reply cần typed contract |
| Authorization và tenant isolation | **Không** | Phải xác thực ở trust boundary |
| Concurrency/ordering/backpressure | **Không** | Phụ thuộc channel/adapter |
| Retry/late reply | **Không** | Cần policy riêng |

### 4.1. Không phải "sửa mỗi annotation là đổi hệ thống đồng bộ thành async an toàn"

Chuyển `DirectChannel` thành `ExecutorChannel` hoặc broker queue thay đổi thread boundary và failure model. Dù chữ ký `OrderQuote quote(...)` không đổi, **độ trễ, thứ tự, timeout, retry, ACK và late reply** đều có thể đổi. Abstraction giúp giảm coupling ở mã caller nhưng không miễn thiết kế hệ thống.

## 5. Các loại Gateway dễ bị nhầm

| Tên | Vai trò | Ví dụ |
|---|---|---|
| **Messaging Gateway EIP** | Ẩn messaging API sau một interface/hợp đồng | `OrderQuoteGateway.quote(...)` |
| **Gateway proxy (`@MessagingGateway`)** | Tạo implementation cho Java interface | `GatewayProxyFactoryBean` |
| **HTTP inbound gateway** | Nhận HTTP request, chuyển vào flow và trả HTTP response | `HttpRequestHandlingMessagingGateway` |
| **HTTP outbound gateway** | Flow gửi HTTP request và nhận response | REST client adapter |
| **JMS/AMQP inbound gateway** | Định nghĩa request-reply với broker | Queue request + reply |
| **Service Activator** | Thực thi logic xử lý một message | `QuoteCalculator.quote(...)` |
| **Message Endpoint** | Consumer/producer nội bộ trong flow | Router, Filter, Transformer |

Một gateway proxy Java **không tự tạo HTTP endpoint**. Nếu cần REST API, vẫn phải có web controller/HTTP inbound gateway. Tương tự, một HTTP outbound gateway là adapter tương tác với hệ thống bên ngoài, không giống bean proxy che `MessageChannel` cho application service.

## 6. Domain model: yêu cầu báo giá và kết quả

Ví dụ dùng Java 17 records, không truy cập DB và không tạo side effects để tập trung vào request-reply.

### 6.1. Request

~~~java
public record OrderQuoteRequest(
        String quoteId,
        String tenantId,
        String sku,
        int quantity
) {}
~~~

### 6.2. Reply

~~~java
public record OrderQuote(
        String quoteId,
        String tenantId,
        String sku,
        int quantity,
        long totalMinorUnits,
        String currency
) {}
~~~

Tất cả top-level `public` types trong các khối code phải đặt vào **source file Java riêng cùng tên** khi chạy trong project.

### 6.3. Exception có reason code

~~~java
public final class QuoteValidationException
        extends IllegalArgumentException {

    private final String reasonCode;

    public QuoteValidationException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public String reasonCode() {
        return reasonCode;
    }
}
~~~

### 6.4. Pure business handler

~~~java
public final class QuoteCalculator {

    public OrderQuote quote(
            OrderQuoteRequest input,
            String authenticatedTenant) {

        if (input == null) {
            throw new QuoteValidationException(
                    "REQUEST_REQUIRED");
        }

        if (blank(input.quoteId())) {
            throw new QuoteValidationException(
                    "QUOTE_ID_REQUIRED");
        }
        if (blank(input.tenantId())) {
            throw new QuoteValidationException(
                    "TENANT_ID_REQUIRED");
        }
        if (blank(authenticatedTenant)
                || !input.tenantId().equals(
                        authenticatedTenant)) {
            throw new QuoteValidationException(
                    "TENANT_NOT_AUTHORIZED");
        }
        if (blank(input.sku())) {
            throw new QuoteValidationException(
                    "SKU_REQUIRED");
        }
        if (input.quantity() <= 0) {
            throw new QuoteValidationException(
                    "QUANTITY_MUST_BE_POSITIVE");
        }

        long unitMinorUnits = switch (input.sku()) {
            case "BOOK" -> 120_000L;
            case "PEN" -> 15_000L;
            default -> throw new QuoteValidationException(
                    "SKU_UNSUPPORTED");
        };

        final long totalMinorUnits;
        try {
            totalMinorUnits = Math.multiplyExact(
                    unitMinorUnits,
                    input.quantity());
        }
        catch (ArithmeticException ex) {
            throw new QuoteValidationException(
                    "QUOTE_AMOUNT_OVERFLOW");
        }

        return new OrderQuote(
                input.quoteId(),
                input.tenantId(),
                input.sku(),
                input.quantity(),
                totalMinorUnits,
                "VND");
    }

    private static boolean blank(String text) {
        return text == null || text.isBlank();
    }
}
~~~

**Ý nghĩa ví dụ:** handler tạo một **báo giá thuần** từ bảng giá giả định, không ghi nhận đặt hàng hoặc thanh toán. Method trả `OrderQuote` chứng minh API request-reply, **không** chứng minh thao tác đặt hàng đã được commit.

### 6.5. Header `authenticatedTenant` đến từ đâu?

Trong demo, caller truyền một chuỗi vào Gateway để minh họa mapping method arg → header. Production không được coi chuỗi do client tự khai là bằng chứng được xác thực. HTTP Controller/security adapter phải lấy tenant từ principal/claims đã xác thực rồi truyền vào application service; Gateway chỉ **mang thông tin qua flow**, không tự kiểm tra JWT/mTLS.

## 7. Định nghĩa interface với `@MessagingGateway`

### 7.1. Contract kiểu Java

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;

@MessagingGateway(
        name = "orderQuoteGateway",
        defaultRequestChannel = "quote.requests",
        defaultRequestTimeout = "2000",
        defaultReplyTimeout = "3000")
public interface OrderQuoteGateway {

    @Gateway
    OrderQuote quote(
            OrderQuoteRequest request,
            @Header("authenticatedTenant") String tenant);
}
~~~

Ở đây:

- `@MessagingGateway` đặt trên **interface**, không cần tự viết implementation class.
- `name` định danh bean proxy.
- `defaultRequestChannel` là nơi gateway gửi message.
- `defaultRequestTimeout` và `defaultReplyTimeout` (đơn vị **milliseconds**, cấu hình nhận chuỗi) là các giới hạn riêng.
- `@Gateway` có thể ghi đè channel, timeout, headers ở **mỗi method**.
- `@Header` map một argument thành header `authenticatedTenant`.
- Return type `OrderQuote` khiến method có **hợp đồng phải nhận reply**, nếu flow trả lời đúng.

### 7.2. Vì sao client không cần import `MessageChannel`?

Client application chỉ thấy interface:

~~~java
public final class QuoteApplicationService {

    private final OrderQuoteGateway gateway;

    public QuoteApplicationService(
            OrderQuoteGateway gateway) {
        this.gateway = gateway;
    }

    public OrderQuote prepareQuote(
            OrderQuoteRequest request,
            String authenticatedTenant) {

        return gateway.quote(
                request,
                authenticatedTenant);
    }
}
~~~

Service này không biết `MessageBuilder`, `replyChannel`, `ServiceActivator` hay tên channel. Nếu muốn giảm cả dependency annotation trong core domain, có thể định nghĩa một **plain Java port interface** (ví dụ `QuotePort`) ở domain layer và dùng gateway/proxy làm adapter ở integration layer.

### 7.3. Đăng ký gateway interface không chỉ là `@ComponentScan`

Spring Integration dùng `@IntegrationComponentScan` để tìm các interface `@MessagingGateway` và tạo bean proxy. Một `@ComponentScan` thường không đủ để phát hiện/đăng ký đúng loại interface này. Với Spring Integration 6.0+ có thể có lựa chọn đăng ký thông qua `@Import`; ví dụ bài dùng component scan rõ ràng để dễ hiểu.

## 8. Java DSL: route request vào handler trả reply

### 8.1. Cấu hình đầy đủ

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan(
        basePackageClasses = OrderQuoteGateway.class)
public class QuoteGatewayConfiguration {

    @Bean(name = "quote.requests")
    public MessageChannel quoteRequests() {
        return new DirectChannel();
    }

    @Bean
    public QuoteCalculator quoteCalculator() {
        return new QuoteCalculator();
    }

    @Bean
    public IntegrationFlow quoteRequestFlow(
            QuoteCalculator calculator) {

        return IntegrationFlow
                .from("quote.requests")
                .handle(
                        OrderQuoteRequest.class,
                        (request, headers) -> calculator.quote(
                                request,
                                (String) headers.get(
                                        "authenticatedTenant")))
                .get();
    }
}
~~~

Cần đặt interface, model, processor và configuration trong các package có thể scan phù hợp; nếu project có nhiều gateway interfaces, giới hạn scope của `@IntegrationComponentScan` để không vô tình tạo các beans thuộc test/module khác.

**Luồng thực hiện:**

1. Bean proxy `OrderQuoteGateway` nhận `quote(request,tenant)`.
2. Proxy tạo message có payload `OrderQuoteRequest` và header `authenticatedTenant`.
3. Gateway gửi message tới `quote.requests`.
4. `DirectChannel` gọi handler `QuoteCalculator.quote(...)` trong caller thread.
5. Handler trả `OrderQuote`.
6. Spring Integration gửi kết quả về **replyChannel của gateway** (header được mang qua flow).
7. Proxy chuyển reply thành giá trị `OrderQuote` trả về caller.

~~~mermaid
sequenceDiagram
    participant A as QuoteApplicationService
    participant G as OrderQuoteGateway Proxy
    participant C as quote.requests DirectChannel
    participant H as QuoteCalculator

    A->>G: quote(request, tenant)
    G->>C: Message(payload, headers, replyChannel)
    C->>H: handle(request)
    H-->>C: OrderQuote
    C-->>G: Reply qua replyChannel
    G-->>A: OrderQuote
~~~

### 8.2. Không cần tạo explicit reply channel trong flow đơn giản

Gateway tự tạo reply channel cho request-reply. Đừng thêm một `QueueChannel` cố định làm output rồi mong gateway tự đọc nó nếu chưa có bridge/routing. Đối với flow `.handle(...)` tạo reply, cơ chế header replyChannel đã đủ.

### 8.3. Một handler trả `null` thì sao?

Nếu calculator trả `null` hoặc một endpoint không tạo reply, Gateway không thể biến "không có Message" thành `OrderQuote` hợp lệ. Tùy thread boundary và timeout, caller có thể chờ, nhận `null` hoặc một lỗi. Một application API không cho phép null reply phải định nghĩa **error/timeout mapping** rõ và tránh các đường xử lý không có reply.

### 8.4. Vì sao không đặt `.channel("quote.requests")` hai lần?

Trong cấu hình trên, Gateway đã gửi vào `quote.requests`; `IntegrationFlow.from("quote.requests")` là điểm **đọc** channel. Nếu lại tạo một flow vòng sang chính channel này, message có thể loop hoặc bị phân phối sai. Mỗi channel/endpoint có vai trò rõ: input, branch hoặc output.

## 9. Gateway method và header mapping

### 9.1. Phân biệt payload và header argument

~~~java
@Gateway(requestChannel = "quote.requests")
OrderQuote quote(
        OrderQuoteRequest request,
        @Header("authenticatedTenant") String tenant);
~~~

`OrderQuoteRequest` là payload. `tenant` được đưa vào header, không tự trở thành một field mới trong record.

### 9.2. Method-level override

~~~java
@MessagingGateway(
        defaultRequestChannel = "quote.requests")
public interface MultiOperationGateway {

    @Gateway(requestChannel = "quote.requests")
    OrderQuote quote(OrderQuoteRequest request);

    @Gateway(requestChannel = "audit.events")
    void audit(AuditEvent event);
}
~~~

Đây là ví dụ **minh họa các method dùng channel khác nhau**, không phải một cấu hình chạy độc lập: cần khai báo `AuditEvent`, channel `audit.events` và endpoint handler phù hợp. Không cho một method vô tình dùng default request channel nếu payload và contract của nó thuộc flow khác.

### 9.3. Không đặt raw secrets vào gateway headers rồi forward vô tội vạ

Một method `@Header("Authorization") String token` có thể giúp một hop HTTP adapter trong tình huống cụ thể, nhưng không nên chuyển bearer token qua toàn bộ broker/canonical channel. Dùng security context tại ingress, token exchange cho downstream hoặc credential scope phù hợp. Header từ Gateway phải qua **header mapper/allowlist** khi ra ngoài JVM.

## 10. Gateway khác service activator trực tiếp như thế nào?

Một business caller có thể gọi `QuoteCalculator.quote(...)` trực tiếp mà không cần Spring Integration. Nếu chỉ có một lời gọi pure Java và không cần pipeline, **đừng thêm Gateway cho có**.

Gateway hữu ích khi cần che đi một pipeline thật:

~~~text
Java caller
 -> Gateway proxy
 -> input validation
 -> Transformer
 -> Router theo tenant/product
 -> Handler A/B
 -> Aggregator hoặc response assembly
 -> reply to gateway
~~~

Lúc này application giữ một API đơn giản dù integration flow có nhiều endpoints. Nhưng khi topology phức tạp, **mỗi route phải có reply semantics**; Filter drop hoặc Aggregator không release sẽ ảnh hưởng trực tiếp đến Gateway method.

### 10.1. Ports and adapters

Một kiến trúc tách biệt có thể là:

~~~text
Domain application code
  -> QuotePort (plain Java interface)
       -> MessagingGateway adapter
            -> Spring Integration channels/endpoints
~~~

Mục tiêu không nhất thiết là mọi domain interface phải mang Spring annotations. Sự khác biệt cốt lõi là **domain caller không phụ thuộc trực tiếp MessageChannel**.

## 11. Unit test: kiểm tra business handler độc lập messaging

Trước khi khởi động Spring context, test thuật toán báo giá:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class QuoteCalculatorTest {

    private final QuoteCalculator calculator =
            new QuoteCalculator();

    @Test
    void quoteBookQuantityTwo() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-1001",
                        "tenant-a",
                        "BOOK",
                        2);

        OrderQuote quote =
                calculator.quote(request, "tenant-a");

        assertEquals("quote-1001", quote.quoteId());
        assertEquals("tenant-a", quote.tenantId());
        assertEquals("BOOK", quote.sku());
        assertEquals(2, quote.quantity());
        assertEquals(240_000L, quote.totalMinorUnits());
        assertEquals("VND", quote.currency());
    }

    @Test
    void unknownSkuIsValidationError() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-1002", "tenant-a", "BAD", 1);

        QuoteValidationException error =
                assertThrows(
                        QuoteValidationException.class,
                        () -> calculator.quote(
                                request, "tenant-a"));

        assertEquals(
                "SKU_UNSUPPORTED", error.reasonCode());
    }

    @Test
    void tenantMismatchIsRejected() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-1003", "tenant-b", "PEN", 1);

        QuoteValidationException error =
                assertThrows(
                        QuoteValidationException.class,
                        () -> calculator.quote(
                                request, "tenant-a"));

        assertEquals(
                "TENANT_NOT_AUTHORIZED",
                error.reasonCode());
    }

    @Test
    void invalidQuantityIsRejected() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-1004", "tenant-a", "PEN", 0);

        assertThrows(
                QuoteValidationException.class,
                () -> calculator.quote(
                        request, "tenant-a"));
    }
}
~~~

Đây chỉ là **unit test của handler**, chưa chứng minh Gateway proxy được tạo hoặc reply channel được dùng đúng. Cần thêm một integration test gọi interface bean thật.
## 12. Integration test: gọi Gateway interface như một API bình thường

Một kiểm thử có giá trị phải khởi tạo Spring context, để `@IntegrationComponentScan` đăng ký Gateway proxy, rồi gọi method trên interface:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = QuoteGatewayConfiguration.class)
class OrderQuoteGatewayIntegrationTest {

    @Autowired
    OrderQuoteGateway gateway;

    @Test
    void gatewayCallsMessagingFlowAndReturnsTypedReply() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-2001", "tenant-a", "BOOK", 2);

        OrderQuote reply =
                gateway.quote(request, "tenant-a");

        assertNotNull(reply);
        assertEquals("quote-2001", reply.quoteId());
        assertEquals("tenant-a", reply.tenantId());
        assertEquals("BOOK", reply.sku());
        assertEquals(2, reply.quantity());
        assertEquals(240_000L, reply.totalMinorUnits());
        assertEquals("VND", reply.currency());
    }

    @Test
    void methodArgumentAnnotatedAsHeaderReachesHandler() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-2002", "tenant-b", "PEN", 3);

        // Header tenant-b khớp payload tenant-b.
        OrderQuote reply =
                gateway.quote(request, "tenant-b");

        assertEquals(45_000L, reply.totalMinorUnits());
        assertEquals("tenant-b", reply.tenantId());
    }

    @Test
    void tenantMismatchIsNotTurnedIntoSuccess() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-2003", "tenant-b", "PEN", 2);

        RuntimeException thrown = assertThrows(
                RuntimeException.class,
                () -> gateway.quote(request, "tenant-a"));

        assertTrue(GatewayCauseChecks.contains(
                thrown, QuoteValidationException.class));
    }

    @Test
    void invalidQuantityDoesNotProduceQuote() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-2004", "tenant-a", "PEN", -1);

        RuntimeException thrown = assertThrows(
                RuntimeException.class,
                () -> gateway.quote(request, "tenant-a"));

        assertTrue(GatewayCauseChecks.contains(
                thrown, QuoteValidationException.class));
    }
}
~~~

Helper để kiểm tra cause chain khi framework/version bọc exception:

~~~java
public final class GatewayCauseChecks {

    private GatewayCauseChecks() {}

    public static boolean contains(
            Throwable exception,
            Class<? extends Throwable> expected) {

        Throwable current = exception;
        while (current != null) {
            if (expected.isInstance(current)) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }
}
~~~

Đặt `GatewayCauseChecks` trong file Java test riêng. Tùy phiên bản, Gateway có thể **unwrap** exception từ handler trước khi ném cho caller hoặc gửi wrapper; test kiểm tra **loại lỗi nghiệp vụ trong chuỗi cause**, không phụ thuộc hình dạng wrapper cụ thể.

### 12.1. Vì sao đây là integration test?

Nó kiểm tra đồng thời:

- Interface `OrderQuoteGateway` đã được Spring Integration đăng ký thành bean proxy.
- Method invocation được chuyển thành message ở `quote.requests`.
- `@Header("authenticatedTenant")` được đưa tới handler.
- Handler trả đúng typed `OrderQuote`.
- Reply được gửi về Gateway, method trả kết quả.
- Exception từ handler không bị biến thành quote giả.

Test không dùng trực tiếp `MessageChannel.send()` để gọi flow; nó xác minh **mục tiêu che giấu messaging API** của Gateway.

### 12.2. Test này chưa kiểm chứng điều gì?

- HTTP/AMQP/Kafka transport thật.
- Transaction/database commit hoặc idempotency của command tạo đơn.
- Timeout khi handler chậm hoặc kẹt.
- Dữ liệu bị serialization mất trường khi qua hai JVM.
- ACK/NACK hoặc retry policy của broker.
- Authorization từ token mTLS/JWT — demo chỉ đối chiếu hai tenant strings.

Cần những bài test riêng cho boundary đã triển khai, không gọi một in-memory integration test là chứng minh reliability production.

### 12.3. Unit test client dùng fake gateway

Nếu chỉ muốn kiểm thử lớp `QuoteApplicationService`, có thể dùng fake implementation của `OrderQuoteGateway` hoặc mock. Ứng dụng không cần khởi động Spring context và không cần biết channel:

~~~java
OrderQuoteGateway fake = (request, tenant) ->
        new OrderQuote(
                request.quoteId(),
                tenant,
                request.sku(),
                request.quantity(),
                100L,
                "VND");

QuoteApplicationService service =
        new QuoteApplicationService(fake);

OrderQuote result = service.prepareQuote(
        new OrderQuoteRequest(
                "quote-9001", "tenant-a", "PEN", 1),
        "tenant-a");
~~~

Ở đây interface chỉ có một abstract method, nên có thể dùng lambda Java. Fake không kiểm thử Spring Gateway wiring; nó giúp giữ **tầng business caller** dễ unit test.

## 13. Hai timeout khác nhau: `requestTimeout` và `replyTimeout`

Một Gateway request-reply có ít nhất hai giai đoạn:

~~~mermaid
flowchart LR
    A["Gateway method call"] -->|"requestTimeout"| SEND["Send vào request channel"]
    SEND -->|"Downstream processing"| HANDLER["Handler/flow"]
    HANDLER -->|"replyTimeout"| REPLY["Receive reply"]
    REPLY --> RET["Return method result"]
~~~

| Timeout | Áp dụng ở đâu? | Ví dụ |
|---|---|---|
| `requestTimeout` | Chờ **gửi message** khi channel send có thể block | `QueueChannel` bounded đã đầy |
| `replyTimeout` | Chờ **reply message** khi Gateway đã đến giai đoạn nhận reply | Worker chạy async nhưng reply tới muộn |
| HTTP socket/connect timeout | Ở outbound HTTP client | Remote API chậm/không kết nối |
| Broker publish timeout | Ở broker adapter | Chưa rõ broker đã lưu record |
| Business SLA deadline | Ở cấp nghiệp vụ | Báo giá phải phản hồi trong SLA |
| Transaction timeout | Ở transaction manager | Transaction không được kéo dài |

**Không đồng nhất các giá trị này.** Đặt `replyTimeout="3000"` không tự giới hạn mọi downstream Java method trong 3 giây.

### 13.1. `DirectChannel` đồng bộ không bị cắt ngang bởi replyTimeout

Trong cấu hình mục 8, `DirectChannel` gọi handler ngay trên **caller thread**. Nếu `QuoteCalculator` kẹt trong một cuộc gọi blocking 60 giây, Gateway không thể chạy bộ đếm đợi reply trong khi `send()` chưa trả về. Thời gian gọi method có thể vượt `replyTimeout`.

~~~text
Gateway method invoked
  -> DirectChannel.send(...)
      -> handler blocks 60 seconds
      -> handler returns
  -> Gateway can observe the reply
~~~

Vì vậy `replyTimeout` là **thời gian đợi phản hồi ở receive phase**, không phải một bộ ngắt xử lý đồng bộ. Với remote I/O phải cấu hình **timeout ở chính client I/O** hoặc chuyển sang cơ chế async có cancellation/deadline policy riêng.

### 13.2. Khi có ExecutorChannel hoặc poller

Nếu flow chuyển request cho worker thread rồi `send()` trả về, Gateway có thể bắt đầu **đợi reply**. Khi worker không trả đúng thời hạn, timeout có thể xảy ra trước khi business processing kết thúc. Worker có thể vẫn tiếp tục và tạo **late reply**.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant E as ExecutorChannel
    participant H as Slow handler

    C->>G: quote(request)
    G->>E: send(Message)
    E-->>G: Dispatch accepted
    G->>G: Wait for reply
    E->>H: Process asynchronously
    Note over G: replyTimeout elapsed
    G-->>C: null/timeout outcome theo config
    H-->>G: Late reply sau deadline
~~~

Một timeout **không chứng minh** business action chưa xảy ra, đặc biệt khi downstream gọi remote API hoặc commit DB.

### 13.3. Timeout default có thể khác theo phiên bản/loại gateway

Các bản Spring Integration và các loại gateway có default timeout khác nhau trong tài liệu lịch sử. **Không dựa vào default không rõ**: đặt explicit request/reply timeout phù hợp SLA, đọc reference đúng dependency version và kiểm thử thực tế.

### 13.4. Không trả `null` im lặng trong domain API

Một API trả `OrderQuote` có thể không cho phép null. Caller nên được bảo vệ bởi:

- Downstream **luôn tạo reply** cho mọi accepted request.
- Validation thất bại → typed exception hoặc explicit error reply.
- Các branch Filter/Router có lỗi hoặc kết quả SKIPPED rõ ràng.
- Bật **timeout exception policy** khi phiên bản hỗ trợ, hoặc wrapper biến null/timeout thành domain error.
- Với flow kéo dài, dùng async result/tracking ID thay vì chờ vô hạn.

Trong Spring Integration **6.2+**, `@MessagingGateway`/GatewayEndpointSpec có tùy chọn `errorOnTimeout` giúp phát sinh `MessageTimeoutException` khi **receive timeout** hết thay vì trả null. Tùy chọn này **không** biến `DirectChannel` thành một thread có thể cưỡng chế ngắt và không thay I/O timeouts.

## 14. Khi reply không bao giờ đến

Một synchronous Gateway method có contract **request → reply**, nhưng luồng messaging có thể có nhiều nhánh không tạo reply.

### 14.1. Filter drop

~~~text
Gateway.quote(...)
   -> Filter predicate=false
   -> Message bị drop
   -> Không tạo reply
   -> Gateway đợi đến timeout
~~~

Nếu `Filter` đại diện cho điều kiện "không đủ điều kiện báo giá", một response `QuoteRejected` rõ ràng thường tốt hơn silent discard. Nếu rejection thật sự là lỗi contract, cấu hình Filter throw `MessageRejectedException` hoặc validate trước để lỗi tới caller.

### 14.2. Router không tìm được route

Một Router dựa trên SKU, tenant hoặc channel header có thể không resolve được output. Nếu Router im lặng bỏ message, Gateway không có reply. Trong các luồng request-reply, cần:

- Route hợp lệ cho tất cả supported inputs.
- Default error/rejection route hoặc resolution-required policy.
- Test cả unknown input, không chỉ happy path.
- Tránh redirect unknown messages tới `nullChannel` nếu API mong reply.

### 14.3. Handler trả null/void

Nếu một service activator được cấu hình trả null hoặc `void`, nó có thể hoàn thành mà không phát reply. Với Gateway method trả object, đó là **vi phạm contract** nếu không có endpoint khác tạo reply. Cấu hình `requiresReply` ở handler khi phù hợp để báo lỗi sớm, và test hành vi phiên bản tương ứng.

### 14.4. Aggregator không release

Gateway gửi một request nhưng downstream Splitter tạo nhiều parts và Aggregator chờ đủ nhóm. Nếu Filter bỏ một part hoặc correlation headers bị mất, Aggregator có thể không release, khiến Gateway timeout.

### 14.5. Error flow không gửi reply

Một lỗi đi vào `errorChannel` không mặc nhiên được chuyển thành business error response. Nếu error flow chỉ log và dừng, Gateway có thể chờ. Cần định nghĩa rõ error handling: **rethrow**, tạo typed error reply, hay trả một tracking ID.

## 15. Một-way method `void` và fire-and-forget

Không phải method Gateway nào cũng cần reply:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface AuditGateway {

    @Gateway(requestChannel = "audit.commands")
    void record(AuditEvent event);
}
~~~

Ở đây `AuditEvent` là DTO ứng dụng cần tự khai báo. Gateway method `void` phù hợp với **one-way message contract** khi caller không cần business reply. Tuy nhiên:

- Với `DirectChannel` đồng bộ, `void` vẫn có thể **block** cho tới khi downstream handler hoàn tất.
- Với async channel, `void` có thể trả sau khi request được dispatch, **chưa chắc xử lý xong**.
- Với broker, trả `void` không tự chứng minh broker đã persist.
- Exception trong worker thread sau khi caller `void` trả về không thể đơn giản ném ngược trên call stack cũ.
- Nếu nghiệp vụ cần xác nhận, hãy dùng typed receipt/ack contract hoặc async completion thay vì giả rằng `void` là "thành công".

Từ Spring Integration 5.4, với Gateway method `void` và không có explicit reply channel, framework có thể đặt `nullChannel` làm reply destination để loại phản hồi không cần thiết. Không nên suy rộng điều này thành đảm bảo không có side effects.

### 15.1. Đặt tên method không tạo semantics

~~~java
void sendAndForget(OrderCommand command);
~~~

Tên method `sendAndForget` chỉ là tên. Độ bền, mức ACK, retry, duplicate và timeout vẫn phụ thuộc integration flow và transport thật. Nếu cần **at-least-once delivery**, thiết kế broker/persistent queue/transaction; đừng coi tên method là delivery guarantee.

## 16. Async Gateway: `Future`, `CompletableFuture` và `Mono`

Khi báo giá phải gọi một dịch vụ chậm, async Gateway có thể giúp caller **không chặn thread** trong khi đợi kết quả.

### 16.1. Interface trả `CompletableFuture<OrderQuote>`

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;

@MessagingGateway(
        name = "asyncOrderQuoteGateway",
        asyncExecutor = "quoteExecutor")
public interface AsyncOrderQuoteGateway {

    @Gateway(requestChannel = "quote.requests")
    CompletableFuture<OrderQuote> quoteAsync(
            OrderQuoteRequest request,
            @Header("authenticatedTenant") String tenant);
}
~~~

Với executor đã cấu hình, Gateway có thể chạy flow trong executor rồi trả `CompletableFuture` về caller. Ứng dụng có thể compose:

~~~java
CompletableFuture<OrderQuote> future =
        asyncGateway.quoteAsync(request, "tenant-a");

future.thenApply(OrderQuote::totalMinorUnits)
      .thenAccept(total -> recordTotal(total));
~~~

**Không gọi `future.join()` ngay trên request thread** rồi coi đó là async end-to-end; nó chỉ chuyển blocking sang vị trí khác.

### 16.2. Executor có giới hạn

Một cấu hình `ThreadPoolTaskExecutor` minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import java.util.concurrent.Executor;

@Bean(name = "quoteExecutor")
public Executor quoteExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("quote-gateway-");
    executor.initialize();

    return executor;
}
~~~

Method trên cần được đặt trong một `@Configuration` class. Giá trị thread/queue chỉ là **ví dụ**, phải điều chỉnh theo CPU/I/O capacity, reject policy, downstream SLA và load tests.

### 16.3. Future khác send-only

Một `CompletableFuture<OrderQuote>` có thể hoàn tất **bằng giá trị hoặc exception**. Nó không chỉ là "đã nhận vào queue". Khi flow thực sự bất đồng bộ qua broker khác hệ thống, cần callback/correlation để hoàn thành future đúng request và giải quyết mất reply/late reply.

### 16.4. `asyncExecutor = NULL` là mode khác

Spring Integration hỗ trợ trường hợp **downstream đã trả một Future/Mono** và gateway chỉ cần chuyển đối tượng async đó cho caller. Khi ấy có thể tắt internal async executor bằng `AnnotationConstants.NULL` (tùy phiên bản/config). Đây là **mode khác** với việc gateway tự đưa một handler sync lên executor; không dùng hai mode lẫn lộn.

### 16.5. Reactor `Mono<T>`

Một Gateway có thể trả `Mono<OrderQuote>` khi project dùng Project Reactor. Với reactive composition, flow có thể được kích hoạt khi subscribe, phụ thuộc đường triển khai/version. Không nói `Mono` luôn là một message đã được gửi ngay lúc gọi method; cần hiểu lifecycle subscription, cancellation, context propagation và error signal.

### 16.6. Async vẫn cần deadline và idempotency

Khi future timeout ở caller, downstream business operation có thể vẫn chạy. Hủy `CompletableFuture` không đảm bảo hủy một payment API hoặc broker task đã dispatch. Nếu tác vụ có side effect, stable command ID và reconciliation quan trọng hơn việc caller có một async type.

## 17. Explicit reply channel: khi nào cần?

Trong nhiều request-reply flows, Gateway tạo temporary reply channel là đủ:

~~~text
Gateway request:
  headers.replyChannel = temporary point-to-point channel
~~~

Có thể đặt `defaultReplyChannel`/`replyChannel` khi cần monitor/bridge kết quả qua một named channel. Tuy nhiên:

- Một reply channel chung cho nhiều in-flight requests **không thể** tùy tiện nhận message và trả sai caller.
- Khi cấu hình explicit reply channel, Spring Integration có cơ chế bridge về temporary gateway reply channel; đọc behavior đúng framework version.
- Nếu muốn nhiều subscribers quan sát reply, có thể dùng một `PublishSubscribeChannel` có kiểm soát.
- Với `DirectChannel` point-to-point nhiều competing subscribers, message có thể đi sai consumer nếu thiết kế không đúng.
- Với flow chỉ có một handler trả payload, **không cần** tạo explicit reply channel để làm code "đủ thành phần".

**Khuyến nghị:** bắt đầu với reply channel tạm do Gateway quản lý; chỉ thêm named reply channel khi có nhu cầu quan sát, bridge hoặc contract đặc biệt đã được test.

## 18. Gateway phối hợp với Router, Filter và Transformer

Gateway mở đầu flow, nhưng flow có thể định tuyến theo payload/headers trước khi tạo reply:

~~~mermaid
flowchart TD
    C["Gateway.quote(request)"] --> V["Validate request"]
    V --> R{"Router by SKU"}
    R -->|"BOOK"| B["Quote book handler"]
    R -->|"PEN"| P["Quote pen handler"]
    R -->|"Unsupported"| E["Typed rejection"]
    B --> A["OrderQuote reply"]
    P --> A
    A --> G["Gateway returns"]
    E --> G
~~~

### 18.1. Mọi branch phải có outcome

Nếu một SKU không được hỗ trợ:

- Nên trả typed error hoặc business reply `UNSUPPORTED_SKU`.
- Không silent drop input rồi để Gateway chờ đến reply timeout.
- Nếu dùng `Filter`, kiểm tra `throwExceptionOnRejection` và `discardChannel` theo semantic contract.
- Nếu dùng `Router`, có explicit fallback/error route hoặc resolution-required behavior.

### 18.2. Transformer không nên làm mất reply metadata

Một Transformer trả payload mới thường được Spring Integration hỗ trợ header propagation trong flow, nhưng khi tự tạo một `Message<?>` mới hoặc qua serialization boundary, code có thể làm mất `replyChannel`, `errorChannel`, correlation headers. Nếu mất reply channel, Gateway có thể không nhận được kết quả ngay cả khi business handler đã trả object.

### 18.3. Gateway và Aggregator

Nếu method cần tổng hợp nhiều báo giá:

~~~text
Gateway.getBestQuote(request)
  -> Split request tới nhiều providers
  -> Aggregate replies theo business request ID
  -> Select best
  -> Return one QuoteResult
~~~

Cần định nghĩa:

- Correlation key `quoteRequestId` ổn định.
- Release strategy: đủ tất cả responses hay đủ quorum?
- Group timeout và incomplete result policy.
- Duplicate replies từ broker.
- Một output **duy nhất** khớp return type.
- Reply channel về đúng Gateway invocation.

Nếu group không release, Gateway timeout; nếu cùng request ID bị tái sử dụng bất cẩn, các calls có thể trộn replies.

## 19. Error handling: exception từ flow tới caller

### 19.1. Downstream handler ném exception

Trong flow đồng bộ `DirectChannel`, `QuoteCalculator.quote(...)` ném `QuoteValidationException` cho một payload không hợp lệ. Spring Integration messaging infrastructure có thể bọc nó trong `MessagingException` kèm `failedMessage`, rồi Gateway thường unwrap/propagate nguyên nhân cho caller. **Không** nên nói tất cả phiên bản/topology luôn ném đúng một wrapper.

### 19.2. `errorChannel` là đường xử lý lỗi, không phải normal reply

Một Gateway có thể được cấu hình error channel, ví dụ error flow nhận `ErrorMessage` và thực hiện logging/classification hoặc trả một error result. Tuy nhiên:

- Một error flow chỉ log có thể **không cung cấp reply** cho Gateway.
- Error flow có thể **rethrow** hoặc tạo typed response theo hợp đồng.
- `ErrorMessage` thường có Throwable payload, **khác** `OrderQuote`.
- Nếu dùng Gateway có return type `OrderQuote`, không nên trả một `String` lỗi rồi mong proxy tự hiểu.
- Không chuyển mọi lỗi thành `null` để làm test xanh.

### 19.3. Phân loại lỗi theo khả năng retry

| Lỗi | Ví dụ | Policy gợi ý |
|---|---|---|
| Input không hợp lệ | `quantity=0` | Non-retryable validation error |
| Quyền tenant sai | Authenticated tenant khác payload | Deny/audit, không tự retry |
| SKU chưa hỗ trợ | `sku=BAD` | Explicit business rejection |
| DB deadlock | Transaction transient failure | Bounded retry/backoff |
| Remote HTTP 503 | Service unavailable | Retry có deadline |
| Remote payment timeout | Không rõ payment đã commit chưa | Idempotency/reconciliation |
| Gateway reply timeout | Không thấy response đúng hạn | Unknown business outcome nếu có side effect |
| Filter silent drop | Không có reply | Sửa flow contract, không coi là success |
| Unexpected exception | Bug/invariant violation | Alert, lỗi phù hợp, không silent discard |

### 19.4. Timeout exception là transport/application outcome, không phải business rollback

Một `MessageTimeoutException` (khi cấu hình) nói rằng Gateway **không nhận được reply trước deadline**, không chứng minh DB transaction downstream đã rollback. Với tác vụ không idempotent, retry sau timeout có thể tạo duplicate side effects. Cần stable request/command ID và một cách tra trạng thái.

## 20. Gateway và transaction boundary

Một Gateway ở cùng JVM có thể gửi qua `DirectChannel` đồng bộ, nhưng transaction guarantee vẫn phụ thuộc nơi mở transaction và nơi ghi dữ liệu.

~~~text
Application method
  -> Gateway
  -> DirectChannel
  -> @Transactional business handler
  -> database commit
  -> reply
~~~

Nếu handler được gọi đúng qua Spring transaction proxy và commit thành công trước khi trả reply, một receipt có thể phản ánh business state đã commit. Nhưng nếu handler gửi reply **trước** khi transaction thực sự commit hoặc flow tách async boundary, return value có thể đến trước outcome bền vững.

### 20.1. Không giả rằng Gateway tạo transaction

`@MessagingGateway` không tự mở một transaction có hiệu lực trên DB, broker và remote API. Transaction manager/adapter/handler phải được cấu hình riêng.

### 20.2. Không trộn "accepted" và "completed"

Với tác vụ kéo dài, API có thể trả:

~~~java
public record SubmissionAccepted(
        String commandId,
        String trackingId,
        String status
) {}
~~~

Một reply `ACCEPTED` có thể chỉ chứng minh task đã được lưu vào một inbox/outbox/queue bền vững, **không** có nghĩa thanh toán/shipment đã hoàn tất. Hãy tách API `submit(...) -> AcceptedReceipt` và API `getStatus(trackingId)` hoặc sự kiện hoàn tất sau đó.

### 20.3. Exactly-once không đến từ Gateway

Nếu broker redeliver cùng command do ACK mất, Gateway/handler có thể chạy lại. Cần Idempotent Receiver/unique business key và transaction marker + side effects phù hợp. Nếu nghiệp vụ gọi remote API, dùng remote idempotency key hoặc reconciliation; Gateway method không tự giải quyết crash windows.
## 21. Gateway request-reply qua nhiều JVM hoặc broker

Gateway proxy được đăng ký trong **Spring ApplicationContext của ứng dụng gọi**. Nếu flow ở phía sau đi sang Kafka, JMS, AMQP hoặc HTTP service khác, bạn đang vượt qua một **transport boundary**.

~~~mermaid
sequenceDiagram
    participant A as Application Caller
    participant G as Local Gateway Proxy
    participant P as Request Publisher
    participant B as Broker
    participant W as Remote Worker
    participant R as Reply Consumer

    A->>G: submit(command)
    G->>P: Message + correlation
    P->>B: Publish request with reply destination
    B->>W: Deliver request
    W->>W: Process / commit
    W->>B: Publish reply with correlation ID
    B->>R: Deliver reply
    R-->>G: Resolve waiting request
    G-->>A: Typed result
~~~

### 21.1. Java `replyChannel` không phải remote reply destination

Trong cùng JVM, Gateway có thể gắn `replyChannel` là một **MessageChannel object** vào headers. Khi đi qua broker/HTTP, Java object này không tự tồn tại ở tiến trình bên kia. Adapter cần một **giao thức reply address** phù hợp:

- JMS: reply-to destination/correlation ID theo adapter/hợp đồng.
- AMQP: reply-to / direct reply-to / reply queue theo RabbitMQ adapter.
- Kafka: reply topic/partition và correlation headers theo Spring Integration Kafka adapter hoặc custom protocol.
- HTTP: response gắn với request connection, hoặc callback/polling nếu async.

Không serialize một `DirectChannel` object vào JSON envelope rồi kỳ vọng remote service gửi reply vào đó.

### 21.2. Correlation phải ánh xạ đúng một invocation

Hai callers có thể gửi báo giá đồng thời:

~~~text
Invocation A: quoteId=quote-1001
Invocation B: quoteId=quote-1002

Both requests -> same broker
Replies can arrive B before A
~~~

Để trả đúng caller, adapter cần correlation token độc nhất cho **request attempt/in-flight exchange** theo quy tắc của nó. Business `quoteId` có thể giúp audit/idempotency, nhưng không mặc nhiên là correlation token đủ an toàn cho tất cả concurrent invocations nếu một business request có thể được gọi lại.

### 21.3. Reply đến muộn sau Gateway timeout

~~~text
t0: Gateway gửi request.
t1: Caller hết replyTimeout, nhận timeout.
t2: Worker commit business transaction.
t3: Reply đến topic, không còn caller đang đợi.
~~~

Late reply cần policy: discard có metric, lưu outcome trong result store hoặc chuyển tới reconciliation handler. **Không** coi timeout nghĩa rằng worker chưa làm gì và tự gửi một command mới với event ID khác.

### 21.4. Broker không tạo "RPC exactly-once"

Một request/reply qua broker có thể bị duplicate:

- Request publish đã thành công nhưng sender mất ACK.
- Consumer commit business action rồi crash trước commit offset.
- Reply publish thành công rồi worker retry.
- Caller retry sau timeout.

Vì vậy cần stable command ID, idempotent receiver và khả năng trả lại **cached result/receipt** cho request duplicate. Gateway giúp biểu diễn thao tác như method, nhưng không làm mất at-least-once semantics của broker.

### 21.5. Khi nào nên tránh synchronous remote Gateway?

Nếu một tác vụ mất vài phút, ví dụ tạo shipment, đối soát payment hoặc import hàng nghìn items, giữ một Java/HTTP request chờ reply có thể tốn thread/connection và tạo late-reply problem.

Thường nên dùng:

~~~text
submit(command) -> AcceptedReceipt(commandId, trackingId)
getStatus(trackingId) -> ProcessingStatus
event completed -> Notification / Callback
~~~

Tách **nhận yêu cầu** và **hoàn tất nghiệp vụ** phù hợp hơn với asynchronous workflows.

## 22. Messaging Gateway so với inbound/outbound HTTP Gateway

Tên "Gateway" xuất hiện trong nhiều thành phần Spring Integration:

~~~mermaid
flowchart LR
    HTTP["HTTP Caller"] --> I["HTTP Inbound Gateway"]
    I --> F["IntegrationFlow"]
    J["Java Application"] --> M["@MessagingGateway Proxy"]
    M --> F
    F --> H["HTTP Outbound Gateway"]
    H --> REM["Remote API"]
~~~

### 22.1. `@MessagingGateway`

Định nghĩa một **interface** trong JVM:

~~~java
OrderQuote quote(OrderQuoteRequest request, String tenant);
~~~

Caller được inject proxy bean và gọi method. Không phải HTTP server endpoint.

### 22.2. HTTP inbound gateway

Nhận HTTP request, map body/headers vào Spring Message, chuyển tới request channel, đợi reply và map thành HTTP response. Cần cấu hình path/method/content type/security/timeouts.

### 22.3. HTTP outbound gateway

Một endpoint trong integration flow gọi HTTP service bên ngoài rồi nhận HTTP response, thường có HTTP client timeout và error handling riêng. Nó không phải interface proxy cho business application.

### 22.4. Ghép nhiều lớp Gateway

Có thể tổ chức:

~~~text
HTTP Inbound Gateway
  -> validation
  -> Java business/integration flow
  -> HTTP Outbound Gateway
  -> reply
  -> HTTP Inbound Gateway response
~~~

Hoặc một Spring MVC Controller gọi `OrderQuoteGateway`. Không nên vô tình tạo **hai lần request-reply bridge với các reply channels không nhất quán**. Chọn một boundary rõ và test end-to-end.

### 22.5. Java Gateway không thay thế authentication

Dù caller gọi một Java interface, request từ HTTP trước đó vẫn cần authentication, authorization, rate limiting và validation ở ingress. `@Header("authenticatedTenant")` chỉ là **kênh vận chuyển dữ liệu trong JVM**, không phải cơ chế xác minh danh tính.

## 23. XML gateway và những cấu hình nâng cao

Java annotations/DSL không phải cách duy nhất. Một gateway proxy có thể được cấu hình với Spring Integration XML namespace:

~~~xml
<int:gateway
    id="orderQuoteGateway"
    service-interface="com.example.integration.OrderQuoteGateway"
    default-request-channel="quote.requests"
    default-request-timeout="2000"
    default-reply-timeout="3000"/>
~~~

Ví dụ XML giả định đã khai báo namespace `int`/Spring beans và interface theo package tương ứng. Không đăng ký **đồng thời** proxy qua XML và `@IntegrationComponentScan` với cùng bean ID nếu không cố tình cấu hình một registration duy nhất.

### 23.1. Method-level request channel override

~~~xml
<int:gateway
    id="operationGateway"
    service-interface="com.example.integration.OperationGateway"
    default-request-channel="operations.default">
    <int:method
        name="quote"
        request-channel="quote.requests"
        request-timeout="2000"
        reply-timeout="3000"/>
</int:gateway>
~~~

Cần khai báo thực tế method `quote` trên interface và các channels. Annotation `@Gateway` có thể ghi đè một số cấu hình XML tương ứng; tránh nhiều nguồn cấu hình mâu thuẫn.

### 23.2. Gateway method không có argument

Không nên nghĩ một method không tham số luôn gửi một message rỗng:

~~~java
OrderStatus getStatus();
~~~

Theo cơ chế Gateway, một no-argument method có thể được hiểu là **receive từ PollableChannel** nếu không có payload để send. Để thực hiện một request-reply operation không có argument, chỉ định **payload expression** trên `@Gateway` hoặc `@Payload` theo contract:

~~~java
@Gateway(
        requestChannel = "status.commands",
        payloadExpression = "'QUERY_CURRENT_STATUS'")
String queryCurrentStatus();
~~~

Giá trị `"QUERY_CURRENT_STATUS"` là một **command payload có ý nghĩa**. Cần endpoint handler cho `status.commands` và reply tương thích `String`. Đây là ví dụ method trong interface gateway, không phải một chương trình chạy độc lập.

### 23.3. Các overload và generic return types

Một interface nhiều overloaded methods, SpEL payload expressions và generic return types có thể gây mapping khó theo dõi. Chọn method names/DTOs rõ ràng, test từng method-level requestChannel và return conversion. Không dựa vào reflection generic types để tự map một envelope không có schema/version contract.

## 24. Security và data contract khi Gateway giấu hạ tầng

Che `MessageChannel` không có nghĩa che **trách nhiệm an toàn dữ liệu**.

### 24.1. Validation ở cả API và business boundary

Caller gửi `OrderQuoteRequest` là Java record, nhưng record vẫn có thể chứa quantity âm, tenantId sai hoặc SKU không hợp lệ. Gateway không tự biến record thành một validated domain command. Handler/validator cần kiểm tra trước tính toán và side effects.

### 24.2. Không tin header từ caller tùy ý

Nếu untrusted client tự chọn `authenticatedTenant`, việc service so sánh nó với `tenantId` trên payload chỉ chứng minh **hai chuỗi bằng nhau**, không chứng minh quyền truy cập. Authentication adapter phải cấp tenant context từ trusted principal. Trong demo, test dùng chuỗi để tập trung vào messaging API, không thay security integration test.

### 24.3. Header allowlist khi ra khỏi JVM

Một Gateway message có thể chứa:

~~~text
headers:
  replyChannel = temporary in-JVM channel
  errorChannel = in-JVM error destination
  authenticatedTenant = tenant-a
  traceparent = W3C tracing context
  Authorization = bearer token (nếu caller thêm sai)
~~~

Khi publish ra broker hoặc HTTP endpoint khác, adapter phải có header mapper/allowlist:

- Không export Java `replyChannel` object.
- Không forward Authorization token trừ khi có cơ chế token exchange có chủ đích.
- Không đưa secrets/PII vào shared topic.
- Trace context được chuyển theo instrumentation và trust policy.
- Tenant/source phải được xác minh đúng boundary.
- Content type/schema version phản ánh payload **hiện tại**, không dùng header cũ khi đã transform.

### 24.4. Gateway interface là application contract

Đổi method `OrderQuote quote(...)` thành `void quote(...)` phá **semantic compatibility** dù compilation phía adapter thành công. Thay `OrderQuote` thành một DTO version mới có thể phá callers. Version hóa interface/payload như một API, test consumer contracts và định nghĩa lỗi/timeout rõ.

## 25. Observability: nhìn thấy method, channel và business outcome

Gateway tạo một lớp abstraction. Nếu chỉ quan sát Java method duration, bạn có thể không biết chậm ở send, handler, broker hay reply waiting.

| Metric | Nội dung | Labels nên dùng |
|---|---|---|
| `gateway_invocations_total` | Số method calls | method, outcome |
| `gateway_request_send_seconds` | Độ trễ gửi request channel | channel/flow |
| `gateway_reply_wait_seconds` | Thời gian đợi reply | method |
| `gateway_timeout_total` | Số timeout | phase (send/reply) |
| `gateway_reply_null_total` | Không có reply payload theo contract | method |
| `gateway_validation_error_total` | Input không hợp lệ | reasonCode |
| `gateway_handler_error_total` | Lỗi business handler | error class |
| `gateway_async_inflight` | Số futures/requests chưa hoàn tất | flow |
| `gateway_late_reply_total` | Reply sau deadline | flow |
| `gateway_aggregate_expired_total` | Group không release kịp | flow |
| `gateway_duplicate_command_total` | Duplicate command theo stable ID | flow |
| `gateway_broker_publish_error_total` | Publish failure | adapter |
| `gateway_total_duration_seconds` | End-to-end method duration | method |

Ví dụ log:

~~~text
service=quote-service
flow=quote-requests
gatewayMethod=quote
quoteId=quote-1001
tenant=tenant-a
outcome=SUCCESS
durationMs=16
traceId=trace-1001
~~~

### 25.1. Không dùng high-cardinality IDs làm metric labels

`quoteId`, `orderId`, `tenantId` của một số hệ thống lớn và `traceId` có thể có cardinality rất cao. Không nhét chúng vào labels cho mỗi time series. Dùng logs/traces có quyền truy cập, sampling và retention, hoặc aggregate metrics theo method/outcome/reasonCode.

### 25.2. Correlation giữa Gateway và downstream

Sử dụng tracing context để liên kết caller span, Gateway send, service activator, broker publish/consume và reply. Business request ID phục vụ idempotency/reconciliation; trace ID phục vụ quan sát. Không dùng trace ID thay business ID khi caller retry sau một trace mới.

### 25.3. Các cảnh báo đáng có

- Gateway reply timeout tăng sau thay đổi Router/Filter.
- Method duration cao dù request send nhanh.
- Async in-flight tăng và worker pool hết capacity.
- `null` reply tăng sau release Handler/Normalizer.
- Broker publish timeout tăng nhưng business side effects vẫn chạy.
- Late replies tăng sau network partition.
- Aggregator nhóm thiếu sequence part.
- Caller retry làm duplicate commands tăng.
- `TENANT_NOT_AUTHORIZED` xuất hiện bất thường.

## 26. Anti-pattern thường gặp

| Sai lầm | Hậu quả | Khắc phục |
|---|---|---|
| Business service inject `MessageChannel` khắp nơi | Coupling vào hạ tầng | Expose Java Gateway/port |
| Nghĩ `@MessagingGateway` tự tạo HTTP endpoint | Không có listener HTTP | Cấu hình HTTP inbound gateway/controller |
| Quên `@IntegrationComponentScan`/registration | Không có gateway proxy bean | Bật scan/import đúng package/version |
| Gateway method trả DTO nhưng handler không reply | Timeout/null | Bảo đảm reply hoặc typed rejection |
| Filter default-drop trong request-reply | Caller đợi vô ích | Explicit outcome/throw |
| Router unknown route không có fallback | Không có reply | Required resolution/error route |
| Nghĩ `replyTimeout` ngắt DirectChannel handler | Method vẫn block lâu | I/O deadline/async design |
| Nghĩ `requestTimeout` là business timeout | Hiểu sai SLA | Phân biệt send/reply/business |
| Một named QueueChannel làm reply chung sai cách | Reply bị lẫn callers | Gateway temporary reply + đúng correlation |
| Copy raw `replyChannel` sang Kafka | Remote JVM không có channel object | Broker reply destination/correlation protocol |
| Method `void` đồng nghĩa đã commit | Lost work/false success | Typed durable acceptance receipt |
| Caller retry sau timeout với command ID mới | Duplicate side effects | Stable ID + idempotency/reconciliation |
| Async Gateway dùng executor không giới hạn | Thread/memory pressure | Bounded executor/backpressure |
| Gọi `future.join()` ngay rồi coi là async | Vẫn block caller | Compose async result |
| Error channel chỉ log nhưng Gateway cần reply | Caller timeout | Typed error reply/rethrow |
| Gateway trả `null` như báo giá hợp lệ | Lỗi lan sang nghiệp vụ | Timeout/error contract |
| Coi Gateway tạo DB/broker transaction | Commit không nguyên tử | Transaction/outbox/ACK policy |
| Dùng trace ID làm idempotency key | Retry trace khác → duplicate | Business command/event ID |
| Dùng header do client khai như auth | Cross-tenant access | Verify principal ở ingress |
| Chỉ unit test handler, không test Gateway proxy | Wiring lỗi không phát hiện | Spring integration tests |
| Chỉ test happy path không timeout | Production timeout bất ngờ | Fault injection/late reply tests |
| Tạo duplicate gateway beans từ XML+scan | Bean conflict/routing sai | Một registration source |
| Đổi interface return type nhưng không version | Client break | API contract/consumer tests |

## 27. Bài tập thực hành và ma trận kiểm thử

### 27.1. Bài tập

**Bài 1 — Refactor caller.** Chuyển `DirectChannelQuoteCaller` dùng `MessageBuilder/send()` sang `QuoteApplicationService` chỉ gọi `OrderQuoteGateway.quote(...)`.

**Bài 2 — Interface Gateway.** Tạo `@MessagingGateway(defaultRequestChannel="quote.requests")` với request và typed reply.

**Bài 3 — Header mapping.** Dùng `@Header("authenticatedTenant")`; test header đến QuoteCalculator qua Java DSL.

**Bài 4 — Wiring.** Đặt `@EnableIntegration` và `@IntegrationComponentScan` đúng package. Test Spring context có bean `OrderQuoteGateway`.

**Bài 5 — Unit vs integration.** Viết `QuoteCalculatorTest` và `OrderQuoteGatewayIntegrationTest`; giải thích test nào bắt lỗi channel.

**Bài 6 — Filter drop.** Thêm Filter `quantity>0` nhưng không throw; quan sát no-reply path trong một flow có timeout an toàn, sau đó sửa bằng validation error/typed reply.

**Bài 7 — Router unknown.** Route theo `sku`, gửi SKU ngoài mapping; tránh silent discard.

**Bài 8 — DirectChannel timeout.** Chèn một handler sleep có giới hạn trong flow sync; so sánh thời gian method với `replyTimeout` và giải thích vì sao nó không cắt ngang handler.

**Bài 9 — ExecutorChannel.** Chuyển một stage sang executor, cấu hình replyTimeout ngắn; mô phỏng late reply và ghi metric.

**Bài 10 — Async future.** Thêm `AsyncOrderQuoteGateway` với executor bounded; compose kết quả qua CompletableFuture, test exception propagation.

**Bài 11 — One-way.** Tạo `AuditGateway.record(AuditEvent)` trả void; phân biệt dispatch success và durability.

**Bài 12 — Header leakage.** Đảm bảo outbound HTTP/Kafka adapter không serialize `replyChannel`, token hoặc Java object nội bộ.

**Bài 13 — Broker request-reply.** Thiết kế request/reply topics với correlation ID và reply-to contract; test hai requests trả reply ngược thứ tự.

**Bài 14 — Gateway/API timeout.** Khi caller timeout nhưng worker commit sau đó, truy trạng thái theo stable command ID, không tạo command mới.

**Bài 15 — Aggregator.** Split request đến ba providers, aggregate theo request ID, hoàn tất khi đủ/quorum/expiry và trả một typed reply.

**Bài 16 — Validation/security.** Gửi tenantId khác principal đã xác thực, đảm bảo handler reject; kiểm tra không tin header do client khai.

**Bài 17 — Contract version.** Đổi reply DTO, tạo consumer contract test để phát hiện API break.

**Bài 18 — Observability.** Đo request send, handler time, reply waiting, timeout, late reply và duplicate business commands.

**Bài 19 — No-arg method.** Tạo `@Gateway(payloadExpression="'PING'")` để chủ động gửi request từ method không tham số.

**Bài 20 — Fault injection.** Đưa vào các lỗi Filter drop, database timeout, broker ACK loss và reply delay; lập ma trận outcome theo caller/worker.

### 27.2. Test matrix tối thiểu

| Test case | Mong đợi |
|---|---|
| Interface bean được scan | Autowire `OrderQuoteGateway` thành công |
| Quote BOOK x2 | Typed reply, amount 240000 |
| Quote PEN x3 | Typed reply, amount 45000 |
| Tenant từ header khớp payload | Handler nhận đúng context |
| Tenant header không khớp | Validation exception |
| Quantity âm | Non-retryable validation error |
| SKU unknown | Typed rejection/error |
| Reply đúng type | Gateway trả DTO |
| Handler trả null | Có timeout/error contract rõ |
| Filter drop | Không chờ vô hạn |
| Router không có route | Error/fallback có kiểm chứng |
| DirectChannel handler chậm | Reply timeout không preempt handler |
| ExecutorChannel reply trễ | Timeout/late reply policy |
| Method void | Không hứa business complete |
| CompletableFuture | Hoàn tất với result hoặc exception |
| Broker request-reply A/B | Reply không cross-wire |
| Broker redelivery | Stable command ID, downstream idempotent |
| Gateway caller timeout | Không tự kết luận worker rollback |
| Async worker failure | Error được ghi và chuyển đúng channel |
| Aggregator incomplete | Group expiry/partial outcome rõ |
| Authenticated tenant mismatch | Deny trước side effect |
| Header có secret | Không leak sang transport |
| Schema/reply DTO version change | Contract test bắt break |
| Trace propagation | Không thay business request ID |
| Metrics labels | Không chứa unbounded IDs |

### 27.3. Câu hỏi tự kiểm tra

1. Messaging Gateway EIP giải quyết loại coupling nào?
2. `GatewayProxyFactoryBean` tạo điều gì?
3. Caller business có cần import `MessageChannel` không?
4. `@MessagingGateway` khác HTTP inbound gateway như thế nào?
5. Vai trò `@Gateway` trên từng method?
6. `@Header` map argument vào đâu?
7. Vì sao cần `@IntegrationComponentScan` cho interface?
8. Gateway có tự tạo temporary reply channel không?
9. Khi nào nên cấu hình named reply channel?
10. `requestTimeout` khác `replyTimeout` ra sao?
11. Vì sao replyTimeout không ngắt một DirectChannel handler đang block?
12. Nếu Filter trả false và drop thì Gateway gặp gì?
13. Nếu Router không có route thì cần policy gì?
14. Handler trả null có phải OrderQuote hợp lệ không?
15. `requiresReply` giúp phát hiện lỗi nào?
16. Method `void` có đồng nghĩa fire-and-forget durable không?
17. `CompletableFuture<OrderQuote>` có khác void ở điểm nào?
18. Tại sao cần bounded async executor?
19. ReplyChannel object có gửi xuyên broker/JVM được không?
20. Cách broker ghép reply đúng caller là gì?
21. Late reply sau timeout phải xử lý thế nào?
22. Vì sao timeout không chứng minh business operation đã rollback?
23. Gateway có tự tạo transaction không?
24. Vì sao cần stable command ID khi retry?
25. `ErrorMessage` khác typed business reply ở điểm nào?
26. Gateway API có thay authentication/authorization không?
27. Làm thế nào test Gateway proxy chứ không chỉ handler?
28. Khi nào nên trả AcceptedReceipt + trackingId thay vì chờ hoàn tất?
29. Aggregator không release ảnh hưởng gì tới Gateway?
30. Vì sao tracing ID không nên dùng làm idempotency key?

## 28. Checklist triển khai Messaging Gateway

- [ ] Interface Gateway có tên method/DTO/return type biểu đạt business contract.
- [ ] Business caller không cần tạo Spring Message hoặc gửi vào MessageChannel.
- [ ] `@MessagingGateway` được scan/import đúng và không tạo proxy bean trùng.
- [ ] `defaultRequestChannel` và method-level overrides trỏ tới channel tồn tại.
- [ ] `@Header` arguments có nguồn tin cậy và semantics rõ.
- [ ] Request/response DTO được validation và version khi cần.
- [ ] Có handler/service activator thực sự trả reply cho method non-void.
- [ ] Mọi Router/Filter branches có reply hoặc error outcome rõ.
- [ ] Không dùng default discard/nullChannel cho request cần reply.
- [ ] `requestTimeout` và `replyTimeout` explicit theo SLA.
- [ ] Có timeout của HTTP client, DB và remote dependencies riêng.
- [ ] Hiểu rằng DirectChannel handler sync không bị replyTimeout preempt.
- [ ] Async flow có late reply, cancellation/deadline và backpressure policy.
- [ ] Không dùng unbounded executor/queue trong production mà thiếu giới hạn.
- [ ] Method `void` không bị hiểu là "đã commit thành công".
- [ ] Nếu request dài, cân nhắc durable acceptance receipt + status API.
- [ ] Temporary gateway replyChannel được giữ trong in-JVM reply path.
- [ ] Qua broker/HTTP có reply destination/correlation protocol riêng.
- [ ] Không serialize replyChannel/errorChannel object xuyên JVM.
- [ ] Business idempotency key ổn định qua retry/redelivery.
- [ ] Có transaction/ACK/outbox policy khi business effects cần durability.
- [ ] Error flow phân loại validation, security, transient, timeout và unknown.
- [ ] Không trả `null` như kết quả nghiệp vụ hợp lệ nếu API contract cấm.
- [ ] Authentication/authorization đặt ở trust boundary, không tin header mù.
- [ ] Header mapper/allowlist chặn credential và PII.
- [ ] Correlation/tracing headers phục vụ đúng vai trò, không thay business IDs.
- [ ] Có unit test handler và integration test gọi Gateway interface thật.
- [ ] Test error/timeout, Filter drop, Router no-route, late reply và concurrency.
- [ ] Test Aggregator group release/incomplete nếu có Splitter/Aggregator.
- [ ] Contract test cho caller khi thay method/reply DTO/schema version.
- [ ] Logs/metrics có method/outcome/latency/timeout với bounded labels.
- [ ] Không dùng event/quote/trace IDs làm metric labels cardinality cao.
- [ ] Có runbook khôi phục từ DLQ/replay và đối soát sau timeout.

## 29. Tổng kết

**Messaging Gateway che giấu MessageChannel phía sau API** là một ứng dụng rất rõ của nguyên tắc tách **nghiệp vụ** khỏi **hạ tầng tích hợp**. Với `@MessagingGateway`, Spring Integration tạo proxy bean cho Java interface: caller gọi method bằng DTO nghiệp vụ, proxy chuyển arguments thành message, gửi qua request channel, quản lý temporary reply channel và trả về typed result hoặc lỗi theo contract.

Nhưng **ẩn messaging API không có nghĩa ẩn được messaging semantics**. Một method non-void cần reply thật; Filter drop, Router không resolve, handler trả null hoặc Aggregator không release đều có thể làm Gateway đợi, timeout hoặc không có kết quả. `requestTimeout` chủ yếu liên quan tới send có thể block, còn `replyTimeout` liên quan tới giai đoạn chờ reply; nó không cưỡng chế ngắt một handler đang chạy đồng bộ trên `DirectChannel`. Với `ExecutorChannel`/broker, timeout có thể đến trước business commit và late reply là tình huống phải thiết kế.

Trong **SPRING_INTEGRATION_PATTERN**, hãy dùng Gateway như một **application-facing port** cho Router, Filter, Transformer, Splitter, Aggregator, retry và error-channel flows; đồng thời định nghĩa typed errors, caller deadline, business idempotency, authentication, transaction/ACK và tracing rõ ràng. Khi làm đúng, code nghiệp vụ dễ đọc, dễ mock/test và có thể thay đổi implementation messaging mà không làm mất tính đúng đắn của request-reply contract.

### Tài liệu tham khảo

- Enterprise Integration Patterns — Messaging Gateway: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html
- Spring Integration Reference — Messaging Gateways: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message Channels: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference — Message: https://docs.spring.io/spring-integration/reference/message.html
- Spring Integration Reference — Error Handling: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference — Filter: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Gateway API: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Gateway.html
- Spring Integration Reference — MessagingGateway API: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/MessagingGateway.html
- Spring Integration Reference — IntegrationComponentScan API: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/IntegrationComponentScan.html
- Spring Framework Reference — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/




# Kiểm thử gateway theo hợp đồng công khai

**Messaging Gateway** trong Spring Integration che giấu việc tạo `Message<?>`, gửi vào `MessageChannel`, quản lý `replyChannel` và chuyển reply thành giá trị trả về của một **Java interface**. Khi ứng dụng khác phụ thuộc vào interface đó, điều quan trọng nhất không phải endpoint phía sau dùng `DirectChannel`, `Router` hay `Transformer` nào, mà là **hợp đồng công khai** mà caller thực sự thấy: gọi phương thức nào, truyền gì, nhận gì, khi nào có lỗi, và điều gì được bảo đảm khi lời gọi trả về.

Bài **Kiểm thử gateway theo hợp đồng công khai** thuộc chương **Messaging gateway** của module **SPRING_INTEGRATION_PATTERN**. Mục tiêu của module là học triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và quan sát các nhánh xử lý.

**Trọng tâm:** Kiểm thử gateway bằng cách **gọi interface như một consumer thật**, quan sát kiểu dữ liệu và ngữ nghĩa kết quả/lỗi ở API boundary, rồi bổ sung các bài kiểm thử kênh/adapter ở tầng thích hợp. Một test `inputChannel.send(message)` thành công **không chứng minh** gateway proxy đã được đăng ký, method argument đã map đúng header, reply được trả về đúng caller hay API không bị thay đổi.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích sự khác nhau giữa **gateway public contract**, **messaging implementation** và **transport contract**.
2. Định nghĩa một hợp đồng Java interface có request, reply, business rejection và exception rõ ràng.
3. Phân biệt unit test business handler, contract test với fake, Spring gateway integration test và end-to-end adapter test.
4. Viết `@MessagingGateway`/`@Gateway` và dùng `@Header` truyền caller context có kiểm soát.
5. Khởi tạo gateway proxy bằng `@IntegrationComponentScan` và xác minh có thể inject interface.
6. Gọi **đúng method công khai** trong JUnit 5 để kiểm tra kết quả request–reply.
7. Test giá trị reply, trường bắt buộc, business rejection, lỗi access control và hành vi khi handler không sinh reply.
8. Phân biệt `requestTimeout`, `replyTimeout` và timeout ở client/broker; không coi timeout là rollback.
9. Kiểm thử correlation khi nhiều lời gọi gateway chạy đồng thời.
10. Kiểm thử sự tương thích của method signature, DTO, null policy và error taxonomy.
11. Không kiểm thử dựa trên tên bean nội bộ, số lần Router/Transformer được gọi hoặc `MessageHeaders.ID` nếu chúng không thuộc contract.
12. Dùng fake/mock một cách phù hợp và hiểu vì sao fake pass **không chứng minh Spring proxy wiring**.
13. Định nghĩa tests cho async `CompletableFuture<T>`, one-way `void` và gateway request–reply qua broker.
14. Kiểm thử retry, idempotency và duplicate messages tại đúng tầng, không gán guarantee cho Java gateway.
15. Lập ma trận contract tests và checklist triển khai có thể dùng khi nâng cấp Spring Integration hoặc refactor flow.

## 2. "Hợp đồng công khai" là gì?

Hợp đồng công khai là tập kỳ vọng một **consumer có quyền dựa vào**, không phải mô tả của mọi class bên trong flow.

~~~mermaid
flowchart LR
    C["Consumer / Application"] -->|"Java method"| G["Public Gateway Interface"]
    G -->|"Message & headers"| F["Private IntegrationFlow"]
    F --> H["Handlers / Router / Filter"]
    H -->|"Reply or error"| G
    G -->|"Typed result / exception"| C
~~~

Ví dụ interface:

~~~java
QuoteReply quote(
        QuoteRequest request,
        String trustedTenant);
~~~

Một consumer có thể cần biết:

- Phương thức tên `quote`, nhận `QuoteRequest` và tenant context.
- Nếu hợp lệ, trả `QuoteReply` với `decision=ACCEPTED` và amount/currency.
- Nếu business rule không chấp nhận, trả `decision=REJECTED` cùng reason code ổn định.
- Nếu caller/tenant không được phép, phải fail closed theo chính sách authorization.
- Nếu không có reply hoặc dependency hỏng, **không** được trả một quotation giả trông như thành công.
- Mã `requestId` trong reply phải liên hệ đúng request được gửi.
- Lời gọi không cam kết thanh toán, tạo order hoặc gửi hàng.

Consumer **không nên cần biết**:

- Gateway sử dụng `DirectChannel` hay `ExecutorChannel`.
- Handler nào được gọi và gọi bao nhiêu lần.
- Proxy tạo temporary `replyChannel` kiểu nào.
- Java `MessageHeaders.ID` có giá trị UUID nào.
- Số lượng Transformer/Filter/Router.
- Tên một bean nội bộ đã được refactor.
- Broker offset/partition của một triển khai khác (trừ khi trở thành một transport-facing contract riêng).

### 2.1. Một API có hai lớp hợp đồng

| Lớp | Consumer dựa vào | Ví dụ |
|---|---|---|
| **Public/API contract** | Types, reply semantics, error taxonomy, latency/SLA, idempotency expectations | `QuoteGateway.quote(...)` |
| **Implementation contract** | Channel names, bean IDs, handler wiring, advice, deserializer | `quote.requests`, `.handle(...)` |
| **Transport contract** | Serialization, topic, reply-to/correlation, ACK/NACK, headers được map | HTTP/JMS/Kafka adapter |

Trong code, public gateway có thể không tự expose API HTTP; nó là **Java interface** cho cùng JVM. Nếu gateway đứng sau HTTP controller, HTTP status, headers và response JSON thuộc **hợp đồng khác** của controller/adapter, cần test riêng.

### 2.2. API contract không phải chỉ là chữ ký Java

Một method:

~~~java
QuoteReply quote(QuoteRequest request);
~~~

vẫn có thể phá contract mà không thay signature nếu:

- Trước đây trả `REJECTED` khi SKU không hỗ trợ, giờ trả `null`.
- Trước đây dùng minor units, giờ trả major units.
- Trước đây giữ `requestId`, giờ sinh UUID khác.
- Trước đây từ chối tenant sai, giờ cho phép.
- Trước đây có kết quả xác định, giờ âm thầm drop request.
- Trước đây trạng thái `ACCEPTED` nghĩa "đã báo giá", giờ bị dùng như "đã thanh toán".

Kiểm thử hợp đồng phải xét **ý nghĩa** chứ không chỉ compiler.

## 3. Chọn mức kiểm thử đúng mục tiêu

| Test | Đối tượng được gọi | Bắt được lỗi gì? | Không chứng minh điều gì? |
|---|---|---|---|
| **Unit test domain handler** | `QuoteService.calculate(...)` | Validation/price/business decision | Gateway proxy/headers/replyChannel |
| **Consumer test với fake gateway** | Caller dùng fake `QuoteGateway` | Caller xử lý reply/error đúng | Spring Integration wiring |
| **Gateway integration test** | Interface `@MessagingGateway` do Spring inject | Proxy registration, request mapping, typed reply, handler errors | Broker/HTTP serialization hoặc ACK |
| **Flow integration test** | Message vào channel cụ thể | Router/Filter/Transformer/channel topology | Public method contract nếu không gọi Gateway |
| **Adapter contract test** | HTTP/broker boundary | JSON/schema/reply-to/header mapping, ACL | Toàn business workflow nếu mock handler |
| **End-to-end test** | Caller/broker/service thực | Các boundary phối hợp và một số failure modes | Toàn bộ không gian lỗi phân tán |

### 3.1. Quy tắc đầu tiên

**Để kiểm thử contract của Gateway, hãy gọi Gateway.**

~~~java
// Đúng mục tiêu gateway contract:
QuoteReply result = quoteGateway.quote(request, tenant);
~~~

~~~java
// Cần thiết khi test flow nội bộ, nhưng CHƯA test proxy:
quoteRequests.send(
        MessageBuilder.withPayload(request).build());
~~~

Một test gọi channel trực tiếp có thể xanh dù:

- Không có bean `QuoteGateway` trong ApplicationContext.
- Method route tới sai `requestChannel`.
- `@Header` chưa map.
- Return type không convert được.
- Default timeout thay đổi.
- Public API đã bị xóa/đổi.

### 3.2. Refactor-resistant tests

Nếu một contract test assert "bean X đã gọi bean Y đúng 1 lần", refactor một Handler thành hai Handler có thể làm test đỏ **dù API vẫn đúng**. Contract tests nên ưu tiên **observable outcomes**. Những thứ nội bộ như advice invocation count, wiring graph và bean IDs có thể được test riêng khi chúng chính là đối tượng cần bảo đảm.

## 4. Thiết kế hợp đồng báo giá mẫu

Để tập trung vào kiểm thử gateway, ta tạo một **quotation flow thuần**, không ghi database và không thực hiện thanh toán.

### 4.1. DTO request

~~~java
public record QuoteRequest(
        String requestId,
        String tenantId,
        String sku,
        int quantity
) {}
~~~

### 4.2. Kiểu quyết định công khai

~~~java
public enum QuoteDecision {
    ACCEPTED,
    REJECTED
}
~~~

### 4.3. DTO reply có hai outcome

~~~java
public record QuoteReply(
        String requestId,
        QuoteDecision decision,
        Long totalMinorUnits,
        String currency,
        String reasonCode
) {
    public static QuoteReply accepted(
            String requestId,
            long amount,
            String currency) {

        return new QuoteReply(
                requestId,
                QuoteDecision.ACCEPTED,
                amount,
                currency,
                null);
    }

    public static QuoteReply rejected(
            String requestId,
            String reasonCode) {

        return new QuoteReply(
                requestId,
                QuoteDecision.REJECTED,
                null,
                null,
                reasonCode);
    }
}
~~~

Hợp đồng ví dụ:

| Điều kiện | Public outcome |
|---|---|
| Request có SKU `BOOK`, quantity hợp lệ | `ACCEPTED` + amount VND ở minor units |
| SKU `PEN` hợp lệ | `ACCEPTED` + amount VND |
| Quantity `<= 0` | `REJECTED` + `INVALID_QUANTITY` |
| SKU không hỗ trợ | `REJECTED` + `SKU_UNSUPPORTED` |
| Request ID thiếu | Exception `QuoteContractException("REQUEST_ID_REQUIRED")` |
| Tenant từ request khác authenticated context | Exception `QuoteContractException("TENANT_MISMATCH")` |
| Reply bị mất | Gateway timeout/no-reply error theo adapter policy; **không được coi thành công** |
| Infrastructure failure | Error riêng, có retry policy; **không giả `REJECTED` business** |

`QuoteReply` với factory methods giữ ngữ nghĩa rõ, nhưng record này vẫn có public constructor cho phép tạo reply không nhất quán; nếu dùng thật, nên thêm constructor validation hoặc factory-only type design để cấm `ACCEPTED` thiếu amount và `REJECTED` không reason.

### 4.4. Tại sao dùng boxed `Long`?

Khi `REJECTED`, không có số tiền báo giá. `Long` có thể null để phân biệt **chưa có quotation** với **báo giá 0 đồng**. Không dùng amount `0` như sentinel tùy tiện vì có thể mâu thuẫn domain.

### 4.5. Không nhầm ACCEPTED với đã tạo order

Method `quote(...)` chỉ tạo **quotation**. Reply `ACCEPTED` là **đã tính báo giá hợp lệ**, không có nghĩa:

- Thanh toán đã thành công.
- Đơn hàng đã được commit.
- Inventory đã reserve.
- Broker đã ACK.
- Một external side effect đã hoàn thành.

Contract test phải kiểm tra đúng guarantee của operation, không gán thêm thuộc tính transaction.

## 5. Lỗi công khai: business rejection hay exception?

Một Gateway có thể trả **typed business reply** hoặc ném **exception**. Hai hình thức có ý nghĩa khác nhau.

| Loại | Ví dụ | Trong bài |
|---|---|---|
| Expected business outcome | Quantity không hợp lệ; SKU không support | `QuoteReply.REJECTED` |
| Contract violation không thể gọi an toàn | Request ID thiếu | `QuoteContractException` |
| Security/tenant scope conflict | Tenant context khác request | `QuoteContractException` trong demo; production dùng security layer |
| Transient infrastructure failure | Database/remote timeout | Exception/retry policy riêng |
| No-reply timeout | Handler không phản hồi | Timeout/no-reply outcome, không nhận như quote |
| Programming defect | NullPointerException trong Handler | Fail/alert, không tạo giả một quote |

### 5.1. Typed exception cho lỗi hợp đồng

~~~java
public final class QuoteContractException
        extends RuntimeException {

    private final String reasonCode;

    public QuoteContractException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public String reasonCode() {
        return reasonCode;
    }
}
~~~

Trong Spring Integration, exception có thể được bọc trong `MessagingException` tùy endpoint/channel. Gateway proxy cũng có thể unwrap một số exception. Contract test có thể **duyệt cause chain** để tìm typed reason code mà không phụ thuộc quá mức vào framework wrapper.

Nếu API public thật sự cam kết **ném chính xác một exception type, không wrapper**, cần thêm một adapter ở boundary để chuẩn hóa lỗi trước khi expose interface; lúc đó test exact class của adapter theo contract.

### 5.2. Vì sao không chỉ return null?

`null` không phân biệt:

- Business rejection có reason code.
- Message bị Filter drop.
- Handler lỗi.
- Gateway reply timeout.
- Reply không convert được.
- Không có subscriber.

Một public contract tốt không dùng `null` như kênh lỗi đa nghĩa, trừ khi documented rõ và mọi caller xử lý được.

## 6. Domain service thực thi chính sách

~~~java
public final class QuoteService {

    public QuoteReply calculate(
            QuoteRequest request,
            String authenticatedTenant) {

        if (request == null) {
            throw new QuoteContractException(
                    "REQUEST_REQUIRED");
        }

        if (blank(request.requestId())) {
            throw new QuoteContractException(
                    "REQUEST_ID_REQUIRED");
        }

        if (blank(request.tenantId())) {
            throw new QuoteContractException(
                    "TENANT_ID_REQUIRED");
        }

        if (blank(authenticatedTenant)
                || !request.tenantId().equals(
                        authenticatedTenant)) {
            throw new QuoteContractException(
                    "TENANT_MISMATCH");
        }

        if (request.quantity() <= 0) {
            return QuoteReply.rejected(
                    request.requestId(),
                    "INVALID_QUANTITY");
        }

        if (blank(request.sku())) {
            return QuoteReply.rejected(
                    request.requestId(),
                    "SKU_REQUIRED");
        }

        long unitPrice = switch (request.sku()) {
            case "BOOK" -> 120_000L;
            case "PEN" -> 15_000L;
            default -> -1L;
        };

        if (unitPrice < 0) {
            return QuoteReply.rejected(
                    request.requestId(),
                    "SKU_UNSUPPORTED");
        }

        final long total;
        try {
            total = Math.multiplyExact(
                    unitPrice,
                    request.quantity());
        }
        catch (ArithmeticException exception) {
            throw new QuoteContractException(
                    "TOTAL_OVERFLOW");
        }

        return QuoteReply.accepted(
                request.requestId(),
                total,
                "VND");
    }

    private static boolean blank(String text) {
        return text == null || text.isBlank();
    }
}
~~~

**Lưu ý bảo mật:** Trong ví dụ, `authenticatedTenant` được truyền bằng một tham số Java để kiểm tra mapping tới header. Đó **không phải** authentication thật. Production phải lấy tenant từ principal/claims đã xác thực tại HTTP/broker ingress, rồi truyền trusted context qua interface; không tin một chuỗi do client tự điền.

### 6.1. Vì sao service không nhận `Message<?>`?

`QuoteService` chỉ nhận DTO và context, trả DTO. Nhờ vậy:

- Unit test chạy không cần Spring.
- Business logic không phụ thuộc `MessageChannel`.
- Có thể tái sử dụng qua HTTP Controller, Gateway hoặc một adapter khác.
- Gateway integration test tập trung vào wiring/contract, không cần kiểm tra từng method private.

## 7. Public Gateway interface

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;

@MessagingGateway(
        name = "quoteContractGateway",
        defaultRequestChannel = "contract.quote.requests",
        defaultRequestTimeout = "2000",
        defaultReplyTimeout = "2000")
public interface QuoteContractGateway {

    @Gateway
    QuoteReply quote(
            QuoteRequest request,
            @Header("authenticatedTenant") String trustedTenant);
}
~~~

Những điều **công khai**:

- Method `quote(...)` được application code gọi.
- Request/reply là DTO do module công bố.
- `trustedTenant` phải đến từ context đã xác thực.
- Method có hợp đồng request-reply, không phải fire-and-forget.

Những điều **cấu hình triển khai**:

- Channel `contract.quote.requests`.
- Timeout values (có thể trở thành SLA contract khi được công bố).
- Hình thức proxy bean.
- Các service activators/filters/routers phía sau.

### 7.1. Vì sao interface không triển khai thủ công?

Spring Integration tạo proxy nhờ `GatewayProxyFactoryBean`/annotation infrastructure, biến call thành message và đợi reply. Không cần application code tự viết `send()`/`receive()`. Để đăng ký annotated gateway interfaces, cấu hình `@IntegrationComponentScan` hoặc cơ chế tương đương được hỗ trợ ở framework version sử dụng.

### 7.2. Đừng chỉ kiểm tra có interface class trên classpath

Một class/interface tồn tại **không chứng minh** ApplicationContext có gateway bean. Test phải inject interface qua Spring và **gọi method thành công**.

## 8. Java DSL và ApplicationContext cho contract test

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
        basePackageClasses = QuoteContractGateway.class)
public class QuoteContractFlowConfiguration {

    @Bean(name = "contract.quote.requests")
    public MessageChannel requests() {
        return new DirectChannel();
    }

    @Bean
    public QuoteService quoteService() {
        return new QuoteService();
    }

    @Bean
    public IntegrationFlow quoteFlow(
            QuoteService service) {

        return IntegrationFlow.from("contract.quote.requests")
                .handle(
                        QuoteRequest.class,
                        (request, headers) -> service.calculate(
                                request,
                                (String) headers.get(
                                        "authenticatedTenant")))
                .get();
    }
}
~~~

Flow dùng `DirectChannel` **đồng bộ** để kiểm tra contract trong một Spring context nhỏ:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as QuoteContractGateway
    participant D as DirectChannel
    participant S as QuoteService

    C->>G: quote(request, trustedTenant)
    G->>D: Message(payload, authenticatedTenant, replyChannel)
    D->>S: calculate(request, header)
    S-->>D: QuoteReply ACCEPTED/REJECTED
    D-->>G: Reply to temporary replyChannel
    G-->>C: QuoteReply
~~~

### 8.1. Vì sao không khai báo explicit reply channel?

Với Gateway request-reply, framework thường tự quản lý **temporary reply channel** bằng `replyChannel` header. Khi handler trả `QuoteReply` và response được gửi về gateway đúng cách, method trả typed result. Một named `QueueChannel` không cần thiết ở flow mẫu này.

### 8.2. Nếu thay `DirectChannel` bằng `ExecutorChannel`?

Public method có thể vẫn là `QuoteReply quote(...)`, nhưng error propagation, threading, ordering, timeout và late reply **thay đổi**. Bởi vậy cần chạy lại cùng contract tests và thêm fault/timeout tests; không đổi thread boundary rồi kết luận mọi semantics không đổi.

### 8.3. Ví dụ code không bao gồm network hoặc database

Không có Kafka/JMS/AMQP, HTTP adapter, persistence, transaction hay ACK. **Đây là contract integration test trong JVM**, không phải end-to-end test production. Các thuộc tính của broker và external systems cần kiểm thử ở đúng adapter.

## 9. Test contract ở góc nhìn consumer

Một consumer có thể dùng interface trong application service:

~~~java
public final class CheckoutQuoteClient {

    private final QuoteContractGateway gateway;

    public CheckoutQuoteClient(
            QuoteContractGateway gateway) {
        this.gateway = gateway;
    }

    public QuoteReply getQuote(
            QuoteRequest request,
            String authenticatedTenant) {

        return gateway.quote(request, authenticatedTenant);
    }
}
~~~

Code này không biết `Message<?>`, channel name hoặc replyChannel. Vậy test API đúng phải chứng minh:

1. Gateway bean có thể được inject.
2. Method tồn tại với typed signature đã công bố.
3. Header mapping làm handler nhận đúng context.
4. Happy path trả typed reply đủ field.
5. Business rejection trả **reply không phải exception** theo policy.
6. Contract/security validation fail đúng category.
7. Không có trường hợp trả accepted giả khi không có business reply.
8. Caller có thể test với fake mà không cần messaging infrastructure.

## 10. Unit test business service (không khởi động Spring)

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class QuoteServiceTest {

    private final QuoteService service = new QuoteService();

    @Test
    void acceptedBookQuoteHasExpectedAmount() {
        QuoteRequest request = new QuoteRequest(
                "request-1001", "tenant-a", "BOOK", 2);

        QuoteReply reply =
                service.calculate(request, "tenant-a");

        assertEquals("request-1001", reply.requestId());
        assertEquals(
                QuoteDecision.ACCEPTED, reply.decision());
        assertEquals(
                Long.valueOf(240_000L), reply.totalMinorUnits());
        assertEquals("VND", reply.currency());
        assertNull(reply.reasonCode());
    }

    @Test
    void unknownSkuIsBusinessRejection() {
        QuoteReply reply = service.calculate(
                new QuoteRequest(
                    "request-1002", "tenant-a", "UNKNOWN", 1),
                "tenant-a");

        assertEquals(
                QuoteDecision.REJECTED, reply.decision());
        assertNull(reply.totalMinorUnits());
        assertEquals(
                "SKU_UNSUPPORTED", reply.reasonCode());
    }

    @Test
    void invalidQuantityHasStableReasonCode() {
        QuoteReply reply = service.calculate(
                new QuoteRequest(
                    "request-1003", "tenant-a", "BOOK", 0),
                "tenant-a");

        assertEquals(
                QuoteDecision.REJECTED, reply.decision());
        assertEquals(
                "INVALID_QUANTITY", reply.reasonCode());
    }

    @Test
    void tenantMismatchIsNotAnAcceptedQuote() {
        QuoteContractException exception =
                assertThrows(
                        QuoteContractException.class,
                        () -> service.calculate(
                            new QuoteRequest(
                                "request-1004",
                                "tenant-b", "BOOK", 1),
                            "tenant-a"));

        assertEquals(
                "TENANT_MISMATCH",
                exception.reasonCode());
    }
}
~~~

Đây là unit tests để chứng minh logic. Chúng sẽ **vẫn pass** nếu `@MessagingGateway` bị cấu hình sai channel; phải bổ sung integration tests gọi Gateway bean thật.
## 11. Integration test: gọi Gateway proxy thực

Đây là phần quan trọng nhất. Ta dùng `@SpringJUnitConfig` khởi tạo Spring context từ `QuoteContractFlowConfiguration`, inject **chính interface** và gọi như một consumer.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(
        classes = QuoteContractFlowConfiguration.class)
class QuoteContractGatewayIntegrationTest {

    @Autowired
    QuoteContractGateway gateway;

    @Test
    void gatewayBeanExistsAndReturnsTypedQuote() {
        assertNotNull(gateway);

        QuoteReply reply = gateway.quote(
                new QuoteRequest(
                    "request-2001", "tenant-a", "BOOK", 2),
                "tenant-a");

        assertNotNull(reply);
        assertEquals("request-2001", reply.requestId());
        assertEquals(
                QuoteDecision.ACCEPTED, reply.decision());
        assertEquals(
                Long.valueOf(240_000L),
                reply.totalMinorUnits());
        assertEquals("VND", reply.currency());
        assertNull(reply.reasonCode());
    }

    @Test
    void penQuoteReturnsExpectedAmount() {
        QuoteReply reply = gateway.quote(
                new QuoteRequest(
                    "request-2002", "tenant-a", "PEN", 3),
                "tenant-a");

        assertEquals(
                QuoteDecision.ACCEPTED, reply.decision());
        assertEquals(
                Long.valueOf(45_000L),
                reply.totalMinorUnits());
    }

    @Test
    void invalidQuantityReturnsBusinessRejection() {
        QuoteReply reply = gateway.quote(
                new QuoteRequest(
                    "request-2003", "tenant-a", "BOOK", 0),
                "tenant-a");

        assertNotNull(reply);
        assertEquals(
                QuoteDecision.REJECTED, reply.decision());
        assertEquals("request-2003", reply.requestId());
        assertEquals(
                "INVALID_QUANTITY", reply.reasonCode());
        assertNull(reply.totalMinorUnits());
        assertNull(reply.currency());
    }

    @Test
    void unknownSkuDoesNotBecomeAcceptedQuote() {
        QuoteReply reply = gateway.quote(
                new QuoteRequest(
                    "request-2004", "tenant-a", "UNKNOWN", 1),
                "tenant-a");

        assertNotNull(reply);
        assertEquals(
                QuoteDecision.REJECTED, reply.decision());
        assertEquals(
                "SKU_UNSUPPORTED", reply.reasonCode());
        assertNull(reply.totalMinorUnits());
    }

    @Test
    void tenantHeaderReachesHandler() {
        QuoteReply reply = gateway.quote(
                new QuoteRequest(
                    "request-2005", "tenant-b", "PEN", 1),
                "tenant-b");

        assertEquals(
                QuoteDecision.ACCEPTED, reply.decision());
        assertEquals(
                Long.valueOf(15_000L),
                reply.totalMinorUnits());
    }

    @Test
    void conflictingTenantFailsContract() {
        RuntimeException failure = assertThrows(
                RuntimeException.class,
                () -> gateway.quote(
                    new QuoteRequest(
                        "request-2006", "tenant-b", "BOOK", 1),
                    "tenant-a"));

        assertEquals(
                "TENANT_MISMATCH",
                QuoteExceptionChecks.findReasonCode(failure));
    }

    @Test
    void missingRequestIdFailsContract() {
        RuntimeException failure = assertThrows(
                RuntimeException.class,
                () -> gateway.quote(
                    new QuoteRequest(
                        "", "tenant-a", "BOOK", 1),
                    "tenant-a"));

        assertEquals(
                "REQUEST_ID_REQUIRED",
                QuoteExceptionChecks.findReasonCode(failure));
    }
}
~~~

Vì Spring Integration có thể bọc exception qua `MessagingException` hoặc Gateway proxy có thể unwrap chúng, test **reason code trong cause chain** thay vì một wrapper implementation detail.

~~~java
public final class QuoteExceptionChecks {

    private QuoteExceptionChecks() {}

    public static String findReasonCode(Throwable error) {
        Throwable current = error;

        while (current != null) {
            if (current instanceof QuoteContractException contract) {
                return contract.reasonCode();
            }
            current = current.getCause();
        }

        throw new AssertionError(
                "QuoteContractException not found", error);
    }
}
~~~

### 11.1. Những điều test chứng minh

- Gateway bean được tạo bằng `@IntegrationComponentScan`.
- Annotation `defaultRequestChannel` dẫn tới flow thật.
- Proxy map method arguments thành payload và header.
- Reply handler tới đúng method caller với DTO phù hợp.
- Business rejection là một **typed reply**, không bị drop.
- Lỗi contract/tenant không bị đổi thành ACCEPTED giả.
- Test không cần biết temporary reply channel class hoặc proxy class.

### 11.2. Những điều test chưa chứng minh

- HTTP/JMS/AMQP/Kafka serialization hoặc ACK.
- Database commit/transaction/remote API.
- Nhiều JVM và reply correlation qua broker.
- Late reply, worker crash hoặc network partition.
- Authentication thật: test chỉ kiểm tra sự chuyển **trusted context string** trong JVM; ingress bảo mật phải được test riêng.

### 11.3. Đừng assert class của proxy hoặc số lượng handler gọi

Một refactor có thể đổi số endpoint, tên bean, proxy implementation hoặc tạo thêm Transformer mà không đổi API. Hợp đồng công khai chỉ cần kết quả/lỗi quan sát từ interface. Khi muốn test Router hay Handler riêng, hãy tạo **flow integration test** khác, đừng nhét assertions về implementation details vào contract suite.

## 12. Header mapping: test theo public behavior

Method:

~~~java
QuoteReply quote(
        QuoteRequest request,
        @Header("authenticatedTenant") String trustedTenant);
~~~

có hai đầu vào thực tế: `request` thành **message payload**, `trustedTenant` thành **message header**. Nếu annotation bị đổi sai thành `@Header("tenant")` nhưng handler vẫn đọc `authenticatedTenant`, unit test `QuoteService` không phát hiện; gateway integration test tenant-b ở mục 11 sẽ bắt mismatch.

### 12.1. Không đọc internal MessageHeaders chỉ để test API

Nếu tên header không nằm trong public Java contract, nên assert output sau khi handler dùng đúng value. Không cần inject `contract.quote.requests` vào test rồi đặt một spy để kiểm tra raw message. Những raw-header tests có thể được viết riêng khi **header mapping qua transport** mới chính là hợp đồng.

### 12.2. Trusted tenant phải được chứng thực từ ingress

Trong demo, caller truyền chuỗi `tenant-a`. Production HTTP Controller/broker adapter cần derive tenant context từ principal/JWT/mTLS/broker ACL được xác minh, không dùng payload `tenantId` làm bằng chứng. Một test bảo mật phải cố tình gửi payload tenant-b dưới authenticated tenant-a và assert **không có business side effect**.

## 13. Fake gateway: consumer-side tests

Một Java interface còn hữu ích vì callers có thể test bằng fake **không khởi động Spring context**.

~~~java
public final class CheckoutQuoteClient {

    private final QuoteContractGateway gateway;

    public CheckoutQuoteClient(QuoteContractGateway gateway) {
        this.gateway = gateway;
    }

    public String decide(
            QuoteRequest request,
            String trustedTenant) {

        QuoteReply reply = gateway.quote(
                request, trustedTenant);

        if (reply == null) {
            throw new IllegalStateException(
                    "QUOTE_REPLY_REQUIRED");
        }

        return switch (reply.decision()) {
            case ACCEPTED -> "READY";
            case REJECTED ->
                    "REJECTED:" + reply.reasonCode();
        };
    }
}
~~~

Fake test có thể dùng lambda vì interface chỉ có một abstract method:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class CheckoutQuoteClientTest {

    @Test
    void consumerHandlesRejectionWithoutChannel() {
        QuoteContractGateway fake = (request, tenant) ->
                QuoteReply.rejected(
                    request.requestId(),
                    "INVALID_QUANTITY");

        String result = new CheckoutQuoteClient(fake)
                .decide(
                    new QuoteRequest(
                        "request-3001", "tenant-a", "BOOK", 0),
                    "tenant-a");

        assertEquals(
                "REJECTED:INVALID_QUANTITY", result);
    }

    @Test
    void consumerHandlesAcceptedQuote() {
        QuoteContractGateway fake = (request, tenant) ->
                QuoteReply.accepted(
                    request.requestId(), 120_000L, "VND");

        String result = new CheckoutQuoteClient(fake)
                .decide(
                    new QuoteRequest(
                        "request-3002", "tenant-a", "BOOK", 1),
                    "tenant-a");

        assertEquals("READY", result);
    }

    @Test
    void nullReplyMustNotBecomeSuccess() {
        QuoteContractGateway noReply = (request, tenant) ->
                null;

        assertThrows(
                IllegalStateException.class,
                () -> new CheckoutQuoteClient(noReply).decide(
                    new QuoteRequest(
                        "request-3003", "tenant-a", "BOOK", 1),
                    "tenant-a"));
    }
}
~~~

### 13.1. Fake không chứng minh Gateway proxy hoạt động

Một fake chỉ test **consumer cách sử dụng contract**; nó không bắt được:

- Gateway bean không được scan.
- Sai request channel.
- `@Header` sai tên.
- Handler không reply.
- Return type mapping bị lỗi.

Nên duy trì **cả** gateway integration tests và consumer unit tests. Không cần biến mọi consumer test thành Spring context test.

### 13.2. Đừng làm fake hứa quá mức

Fake trả kết quả ngay lập tức không chứng minh deadline, broker durability hay exactly-once. Nên thêm fake cho rejection/error/no-reply ở những nhánh caller xử lý, nhưng chỉ assert guarantees thực sự thuộc public API.

## 14. Contract tests giúp refactor Flow an toàn

Ban đầu:

~~~text
Implementation V1:
  Gateway -> DirectChannel -> QuoteService
~~~

Sau refactor:

~~~text
Implementation V2:
  Gateway -> Transformer -> Router -> Book/Pen handlers
~~~

Hoặc:

~~~text
Implementation V3:
  Gateway -> ExecutorChannel -> Aggregator
~~~

Nếu API contract được giữ, **cùng một test suite** nên pass với các implementations. Tên bean hoặc số Handler có thể đổi nhưng output semantics vẫn giữ.

| Public input | Public expected | Regression mà contract test bắt |
|---|---|---|
| BOOK x2 | ACCEPTED 240000 VND | Sai route/price |
| PEN x3 | ACCEPTED 45000 VND | Header/handler bug |
| Quantity=0 | REJECTED INVALID_QUANTITY | Filter drop |
| Unknown SKU | REJECTED SKU_UNSUPPORTED | Router no-route |
| Missing requestId | Typed contract error | Validator bị bỏ |
| Tenant mismatch | Deny/contract error | Header mapping sai |
| Hai requests chạy đồng thời | Reply đúng request | Correlation lỗi |
| Handler không sinh reply | Timeout/error outcome | Silent success |
| Downstream failure | Propagated/mapped error | Error flow chỉ log |

Một test `assertThat(handler).wasCalledOnce()` ràng buộc implementation và có thể đỏ khi refactor hợp lệ. Test giao diện nên assert **hành vi quan sát được**.

### 14.1. Test semantics, không chỉ Java type

Giữ kiểu `QuoteReply` mà đổi ý nghĩa `ACCEPTED` hoặc đơn vị amount vẫn có thể phá contract. Nếu amount được công bố là **VND minor units**, một triển khai trả 240 thay cho 240000 là sai contract dù Java type vẫn là `Long`.

### 14.2. Public API version và wire format version khác nhau

Đổi record constructor/return type có thể gây source/binary compatibility break cho Java callers. Khi Gateway được bọc bởi HTTP/Kafka adapter, JSON/schema changes là một **hợp đồng transport riêng**. Java Gateway test không tự bảo đảm consumer ngoài JVM vẫn deserialize được.

## 15. Null/no-reply: có policy và test cụ thể

Một method trả `QuoteReply` không nên làm caller nhầm `null` là thành công. Các nguồn mất reply:

- Filter predicate false và drop.
- Router không resolve route.
- Service Activator trả null.
- Aggregator chưa release group.
- Reply channel header bị mất khi Transformer tự tạo Message.
- Worker async chưa hoàn thành trước timeout.
- Error flow chỉ log, không tạo public reply.

### 15.1. Boundary adapter ép non-null

~~~java
public final class StrictQuotePort {

    private final QuoteContractGateway gateway;

    public StrictQuotePort(QuoteContractGateway gateway) {
        this.gateway = gateway;
    }

    public QuoteReply quote(
            QuoteRequest request,
            String tenant) {

        QuoteReply reply = gateway.quote(request, tenant);
        if (reply == null) {
            throw new IllegalStateException(
                    "QUOTE_REPLY_MISSING");
        }
        return reply;
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class StrictQuotePortTest {

    @Test
    void noReplyIsNeverAcceptedSilently() {
        QuoteContractGateway fake =
                (request, tenant) -> null;

        StrictQuotePort port = new StrictQuotePort(fake);

        IllegalStateException failure =
                assertThrows(
                    IllegalStateException.class,
                    () -> port.quote(
                        new QuoteRequest(
                            "request-3101",
                            "tenant-a", "BOOK", 1),
                        "tenant-a"));

        assertEquals(
                "QUOTE_REPLY_MISSING", failure.getMessage());
    }
}
~~~

Đây là **unit test null policy của adapter**, không phải test Spring Gateway receive timeout. Một Gateway có thể ném timeout exception hoặc trả null tùy phiên bản/config; API cần chuẩn hóa tại boundary nếu consumer dựa vào một kiểu kết quả duy nhất.

### 15.2. Đừng tạo test timeout sai với DirectChannel

Với `DirectChannel`, handler chạy đồng bộ trong caller thread. `replyTimeout` không cưỡng chế ngắt handler đang block trong `send()`. Nếu muốn test timeout thật, dùng async boundary có điều khiển và đặt deadline cho cả remote I/O.
## 16. Kiểm thử timeout theo đúng giai đoạn

Một Messaging Gateway có nhiều loại timeout; test phải xác định đang đo giai đoạn nào.

| Giới hạn | Phạm vi | Cách kiểm thử |
|---|---|---|
| `requestTimeout` | Chờ gửi request khi channel send có thể block | QueueChannel bounded/full, send behavior |
| `replyTimeout` | Chờ nhận reply trong request-reply | Executor/poller với worker chưa trả |
| HTTP connect/read timeout | Outbound HTTP client | Mock server trì hoãn kết nối/response |
| Broker publish timeout | Producer/adapter | Fault injection broker/publisher |
| Business deadline | Toàn bộ thao tác của application | Boundary policy/monitoring |
| DB transaction timeout | Transaction manager | Test integration transaction thật |

### 16.1. DirectChannel có thể vượt replyTimeout

Trong ví dụ flow chính, `DirectChannel` chạy handler đồng bộ trên caller thread. Nếu handler block 5 giây trong `send()`, Gateway có thể chưa tới bước đợi reply. Đặt `replyTimeout=100ms` **không bảo đảm method kết thúc trong 100ms**.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant D as DirectChannel
    participant H as Blocking handler

    C->>G: quote(request)
    G->>D: send(message)
    D->>H: invoke handler
    Note over H: Blocking remote call
    H-->>D: returns after slow processing
    D-->>G: reply through handler
    G-->>C: result
~~~

Vì thế nếu operation có remote I/O, **cấu hình timeout tại HTTP/DB client** hoặc dùng async boundary/deadline phù hợp; không test theo một giả định sai về `replyTimeout`.

### 16.2. Async boundary có thể tạo late reply

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant E as ExecutorChannel
    participant W as Worker

    C->>G: request
    G->>E: send
    E-->>G: dispatch accepted
    G->>G: await reply
    E->>W: process
    Note over G: replyTimeout reached
    G-->>C: null/error per policy
    W-->>G: late reply
~~~

Test nên chứng minh:

- Không nhận reply trước deadline **không** tạo result `ACCEPTED`.
- Late reply không bị deliver nhầm cho invocation khác.
- Worker có thể đã commit business side effect dù caller timeout.
- Retry cùng command ID hoặc reconciliation được áp dụng khi operation có side effects.

### 16.3. Dùng latch thay sleep khi test

Trong một test riêng cho async flow, cho worker chờ `CountDownLatch` do test điều khiển. Caller gọi gateway từ một executor bounded, test xác minh pending state rồi release latch. Khi cần assert timeout, dùng `Future.get(timeout, TimeUnit.SECONDS)` bao ngoài để test không treo; timeout nội bộ Gateway phải được cấu hình riêng.

Không dùng hàng chục `Thread.sleep` với thời gian chính xác 10ms để assert concurrency; CI scheduling khác máy local.

### 16.4. API chính thức có thể chuẩn hóa timeout

Nếu consumer yêu cầu không-null và một exception contract cố định, có thể bọc Gateway bằng adapter map `null`/timeout-specific exceptions thành `QuoteUnavailableException` của application. Spring Integration có option timeout-exception ở một số phiên bản, nhưng không nên giả default giống nhau qua mọi dependency version. **Contract test public adapter** nên assert category đã công bố.

## 17. Kiểm thử exception và error channel

Một lỗi có thể xuất hiện ở các vị trí khác nhau:

~~~text
Gateway -> DirectChannel -> handler throws
  -> Exception may propagate to Gateway caller.

Gateway -> ExecutorChannel -> handler throws on worker
  -> Error handler / ErrorMessage path if configured.

Gateway -> Broker request -> remote worker throws
  -> Need explicit error reply, retry/dead-letter protocol.
~~~

### 17.1. ErrorMessage không phải QuoteReply

`errorChannel` thường nhận `ErrorMessage` có Throwable payload. Nếu error flow chỉ ghi log rồi dừng, public Gateway method có thể **không có reply**. Một Gateway return type `QuoteReply` không tự chuyển mọi Throwable thành `QuoteReply.rejected(...)`.

### 17.2. Public error taxonomy

| Failure | Public outcome | Retry policy |
|---|---|---|
| Quantity=0 | `REJECTED/INVALID_QUANTITY` | Không |
| SKU unsupported | `REJECTED/SKU_UNSUPPORTED` | Không |
| Request ID thiếu | Contract exception | Sửa request |
| Tenant mismatch | Contract/security denial | Không tự retry |
| DB deadlock | Transient error | Bounded retry |
| Remote HTTP 503 | Dependency error | Bounded retry/backoff |
| Handler exception bất ngờ | Internal error | Alert/fix |
| No reply | Timeout/no-reply | Điều tra outcome |
| Broker reply correlation sai | Protocol error | Quarantine/alert |
| Duplicate command | Cached reply/no-op theo contract | Idempotent |

### 17.3. Đừng khẳng định mọi exception có cùng wrapper

Trong integration test, test `QuoteExceptionChecks.findReasonCode` cố ý tìm **typed cause**. Nếu public API chính thức yêu cầu một exact exception class, nên có **adapter chuẩn hóa exception** tại boundary; lúc đó assert class chính xác trên adapter, không phụ thuộc các wrapper của endpoint.

### 17.4. Error flow phải có outcome

Nếu Handler A throw exception còn Gateway chờ, một error flow có thể:

- Propagate exception về caller (sync).
- Tạo typed error reply có correlation đúng.
- Ghi vào DLQ/quarantine và trả tracking receipt.
- Cho timeout rồi reconciliation theo một async contract.

Chọn cách nào phải **được tài liệu hóa và test**. "Lỗi đã được log" không phải kết quả công khai cho method non-void.

## 18. Contract giữ nguyên khi refactor Router/Filter/Aggregator

Một thay đổi từ một Handler sang nhiều branches không được phá caller:

~~~mermaid
flowchart TD
    G["QuoteContractGateway.quote()"] --> V["Validation"]
    V --> R{"Router SKU"}
    R -->|"BOOK"| B["Book quote handler"]
    R -->|"PEN"| P["Pen quote handler"]
    R -->|"Other"| X["REJECTED reply"]
    B --> Y["QuoteReply ACCEPTED"]
    P --> Y
    X --> G
    Y --> G
~~~

### 18.1. Filter có thể âm thầm phá contract

~~~java
.filter(
        QuoteRequest.class,
        request -> request.quantity() > 0)
~~~

Khi predicate false và Filter không có rejection policy phù hợp, message có thể bị drop: caller không nhận `REJECTED/INVALID_QUANTITY`. Contract test `invalidQuantityReturnsBusinessRejection` sẽ bắt regression này.

### 18.2. Router không resolve được SKU

Một Router có thể route thành công BOOK/PEN nhưng không có fallback cho SKU khác. Nếu nó discard hoặc không phát reply, `unknownSkuDoesNotBecomeAcceptedQuote` sẽ không nhận typed REJECTED đúng như contract.

### 18.3. Aggregator không release

Nếu request được Splitter gửi tới ba providers và Aggregator đợi ba replies, một provider missing/timeout có thể khiến không có reply trong deadline. Public API phải định nghĩa xử lý **partial quote, error, timeout hoặc asynchronous result**, không để behavior ngẫu nhiên theo timing.

### 18.4. Transformer mất replyChannel

Một Transformer trả `Message<?>` mới có thể làm mất metadata `replyChannel`/`errorChannel` nếu không giữ đúng header contract. Business handler có thể chạy nhưng reply không về được Gateway. Contract integration tests giúp phát hiện no-reply regression, dù không assert trực tiếp tên header.

## 19. Kiểm thử correlation khi nhiều lời gọi đồng thời

Hai lời gọi Gateway có thể cùng chạy và reply về **ngược thứ tự**:

~~~text
Request A:
  requestId = req-A, SKU=BOOK

Request B:
  requestId = req-B, SKU=PEN

Replies arrive:
  B before A
~~~

Hợp đồng:

\[
\forall r:\quad reply.requestId = request.requestId
\]

và reply amount/decision phải đúng **cùng request**.

### 19.1. Concurrency test trên Gateway public interface

Ví dụ dưới đây chạy trong Spring context và dùng bounded executor của **test**. Nó kiểm tra hai caller threads nhận đúng reply; flow hiện tại xử lý đồng bộ nên chưa mô phỏng broker reply đảo thứ tự.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(
        classes = QuoteContractFlowConfiguration.class)
class ParallelQuoteGatewayContractTest {

    @Autowired
    QuoteContractGateway gateway;

    @Test
    void simultaneousCallsKeepTheirReplies() throws Exception {
        ExecutorService executor =
                Executors.newFixedThreadPool(2);

        try {
            Future<QuoteReply> a = executor.submit(() ->
                    gateway.quote(
                        new QuoteRequest(
                            "req-A", "tenant-a", "BOOK", 1),
                        "tenant-a"));

            Future<QuoteReply> b = executor.submit(() ->
                    gateway.quote(
                        new QuoteRequest(
                            "req-B", "tenant-a", "PEN", 1),
                        "tenant-a"));

            QuoteReply replyA =
                    a.get(5, TimeUnit.SECONDS);
            QuoteReply replyB =
                    b.get(5, TimeUnit.SECONDS);

            assertEquals("req-A", replyA.requestId());
            assertEquals(
                    Long.valueOf(120_000L),
                    replyA.totalMinorUnits());

            assertEquals("req-B", replyB.requestId());
            assertEquals(
                    Long.valueOf(15_000L),
                    replyB.totalMinorUnits());
        }
        finally {
            executor.shutdownNow();
        }
    }
}
~~~

### 19.2. Những điều test chưa chứng minh

- Reply B thật sự được publish trước A.
- Broker request/reply correlation hoạt động giữa hai JVM.
- Late reply A không bị nhầm với request C.
- Redistributed consumer có durability.
- Cùng requestId được gọi hai lần có policy idempotency đúng.

Các vấn đề đó phải test bằng adapter/broker thực hoặc một fake broker có controlled reordering.

### 19.3. In-JVM và remote correlation khác nhau

Gateway proxy thường dùng temporary reply channel riêng cho request-reply trong JVM. Qua broker, cần reply destination và correlation metadata được adapter chuyển đúng. Không serialize `replyChannel` Java object ra Kafka/HTTP rồi kỳ vọng remote system gọi lại object đó.

Business `requestId` có thể giúp audit/idempotency nhưng không mặc định là **duy nhất cho mỗi in-flight RPC** nếu caller cố ý retry cùng request ID; adapter có thể cần một correlation token riêng.

## 20. Idempotency: public contract và các test đúng tầng

Messaging Gateway không hứa exactly-once. Một command qua broker có thể được giao lại sau khi worker commit nhưng trước ACK.

~~~text
Caller submit(commandId=C-1001)
  -> Worker applies action
  -> Reply/ACK lost
  -> Caller retries C-1001
  -> Same command delivered again
~~~

Nếu Gateway public API là **side-effecting command**, contract có thể yêu cầu:

- Stable `commandId`.
- Cùng commandId + same payload → trả cached result/receipt, không apply side effect hai lần.
- Cùng commandId + different payload → conflict.
- Error/timeout không tự chứng minh command chưa commit.
- Dedup record tồn tại đủ lâu cho retry/replay window.
- Remote idempotency keys hoặc reconciliation khi side effect đi ra ngoài DB.

### 20.1. Không assert transport handler chỉ chạy một lần

At-least-once delivery có thể gọi Handler hai lần một cách hợp lệ. Test nên assert **business mutation chỉ được apply một lần**, không ép số lần handler invocation = 1 trong mọi topology.

### 20.2. Ma trận idempotent command minh họa

| Invocation | Payload | Public outcome | Business store |
|---|---|---|---|
| C-1001 lần 1 | X | ACCEPTED, receipt R | Một mutation |
| C-1001 lần 2 | X | Cùng effective receipt R | Vẫn một mutation |
| C-1001 lần 3 | Y | IDEMPOTENCY_CONFLICT | Không mutation mới |
| C-1002 | X | Request mới theo domain contract | Tùy unique business key |

Đây là **contract test của một command gateway khác**, không suy ra từ `QuoteService` thuần. Muốn chứng minh phải có store/transaction và integration test side effects.

## 21. Async public Gateway contract

Gateway có thể trả `CompletableFuture<QuoteReply>` hoặc `Future<QuoteReply>` thay vì chặn thread cho tới reply:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;

@MessagingGateway(
        name = "asyncQuoteGateway",
        asyncExecutor = "quoteAsyncExecutor")
public interface AsyncQuoteGateway {

    @Gateway(requestChannel = "contract.quote.requests")
    CompletableFuture<QuoteReply> quoteAsync(
            QuoteRequest request,
            @Header("authenticatedTenant") String tenant);
}
~~~

Để chạy ví dụ cần một `Executor` bean tên `quoteAsyncExecutor` và gateway registration trong một ApplicationContext được kiểm soát, chẳng hạn:

~~~java
import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean(name = "quoteAsyncExecutor")
public Executor quoteAsyncExecutor() {
    ThreadPoolTaskExecutor pool =
            new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(2);
    pool.setMaxPoolSize(4);
    pool.setQueueCapacity(50);
    pool.setThreadNamePrefix("gateway-contract-");
    pool.initialize();
    return pool;
}
~~~

Đặt method bean trên vào một `@Configuration` class; không có nghĩa mọi @MessagingGateway trong package phải có executor riêng.

### 21.1. Contract async phải nêu rõ hoàn tất gì

- Future hoàn tất thành công bằng **typed QuoteReply**.
- Rejection hợp lệ vẫn là `QuoteReply.REJECTED` theo contract.
- Validation/handler errors làm future complete exceptionally.
- Timeout của caller không tự hủy downstream business action.
- Cancel future không bảo đảm remote worker đã bị ngắt.
- Context propagation/tracing có thể cần instrumentation riêng.

### 21.2. Integration test cho async method

Ví dụ phần lõi của một test có ApplicationContext đăng ký `AsyncQuoteGateway`, `quoteAsyncExecutor` và flow `contract.quote.requests`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

class AsyncQuoteGatewayContractTest {

    @Autowired
    AsyncQuoteGateway gateway;

    @Test
    void futureCompletesWithTypedResult() throws Exception {
        QuoteReply reply = gateway.quoteAsync(
                new QuoteRequest(
                    "async-1001", "tenant-a", "PEN", 2),
                "tenant-a")
                .get(5, TimeUnit.SECONDS);

        assertNotNull(reply);
        assertEquals(
                QuoteDecision.ACCEPTED, reply.decision());
        assertEquals(
                Long.valueOf(30_000L),
                reply.totalMinorUnits());
    }
}
~~~

**Đây là test method minh họa**, không phải class test độc lập: để chạy thật hãy thêm `@SpringJUnitConfig(classes=...)` trỏ tới configuration có gateway scan, executor và flow beans. Bounded `get(timeout,unit)` là giới hạn **của test**; không tự thay thế replyTimeout/remote deadline policy của production.

### 21.3. Đừng dùng `join()` trên request thread và gọi đó là non-blocking

Nếu caller lập tức gọi `future.join()` và chờ hoàn tất, ứng dụng vẫn block. Async public contract nên được sử dụng bằng composition/callback phù hợp, có error handling và executor capacity được kiểm soát.

## 22. One-way Gateway và `void` contract

Một Gateway method:

~~~java
@Gateway(requestChannel = "audit.events")
void record(AuditEvent event);
~~~

không có Java reply. Nhưng `void` **không đồng nghĩa**:

- Broker đã persist.
- Database transaction đã commit.
- Audit handler sẽ chạy đúng một lần.
- Không có exception.
- Caller thread luôn trở về ngay.

Với `DirectChannel`, handler có thể chạy đồng bộ và ném exception trên caller thread; với async channel, method có thể trả sau dispatch trong khi worker còn xử lý. Nếu API cần durable acceptance, expose **receipt/tracking ID** thay vì dùng `void` như một bảo đảm thành công.

### 22.1. Test void gateway như thế nào?

Contract test một operation `void` phải xác định rõ guarantee được hứa:

- Chỉ **dispatch attempt**: test call không throw đối với channel sẵn sàng, thêm riêng adapter failure tests.
- **Persisted acceptance**: test record thực sự được ghi bền trước khi return.
- **Business complete**: phải có receipt/result hoặc quan sát state; `void` thường không biểu đạt đủ.
- **At-least-once**: test redelivery và idempotency của downstream.

Không dùng `void` test để khẳng định exactly-once chỉ từ việc method trả về.

## 23. Adapter contract test: Java API khác wire protocol

Nếu Gateway được bọc bởi HTTP Controller hoặc phía sau là Kafka/JMS/AMQP, có **hợp đồng thứ hai** ở transport boundary.

| Thuộc tính | Java Gateway test | Adapter/wire test |
|---|---|---|
| Method `quote(...)` tồn tại | Có | Không liên quan |
| Java return type `QuoteReply` | Có | Có thể chỉ verify serialized schema |
| `@Header` mapping nội bộ | Có | Header mapper ở ingress/egress |
| JSON field names/types | Không | Có |
| Content-Type / encoding | Không | Có |
| Authentication/JWT/mTLS | Chưa trong demo | Có |
| Broker correlation/reply-to | Chưa trong demo | Có |
| Offset/ACK/DLQ | Không | Có |
| End-to-end tracing | Không | Có |
| Cross-JVM reply timeout | Không | Có |

### 23.1. Ví dụ wire contract

Java reply:

~~~java
new QuoteReply(
    "request-1001",
    QuoteDecision.ACCEPTED,
    240_000L,
    "VND",
    null);
~~~

JSON response có thể được hợp đồng ngoài định nghĩa:

~~~json
{
  "requestId": "request-1001",
  "decision": "ACCEPTED",
  "totalMinorUnits": 240000,
  "currency": "VND",
  "reasonCode": null
}
~~~

Một `Jackson ObjectMapper` có policy bỏ null properties có thể không xuất field `reasonCode`. Public **wire** contract phải nói field null có bắt buộc xuất hay không. Java Gateway test vẫn pass nếu serializer làm thay đổi JSON; cần serialization/consumer-driven contract tests riêng.

### 23.2. Không kiểm tra một transport khác qua in-memory DirectChannel

Để test Kafka reply correlation, phải dùng Kafka test container/embedded broker hoặc kiểm soát adapter tương ứng trong môi trường test. Không gắn header `replyChannel` trong cùng JVM rồi kết luận đã chứng minh Kafka request/reply qua nhiều JVM.
## 24. Security contract ở Gateway boundary

Ẩn `MessageChannel` không có nghĩa đã có authentication và authorization. Gateway chỉ vận chuyển method arguments thành payload/headers; **caller context phải có nguồn tin cậy**.

### 24.1. Public contract về tenant isolation

Giả sử API hứa rằng một tenant chỉ được báo giá cho request thuộc chính tenant đó.

~~~text
Authenticated principal: tenant-a
QuoteRequest.tenantId: tenant-b

Expected:
  Contract/security denial
  No business side effect
  No cross-tenant data in reply or logs
~~~

Bộ test nên dùng hai lớp:

1. **Gateway integration test**: kiểm tra `@Header("authenticatedTenant")` đến đúng handler và tenant mismatch bị từ chối.
2. **Ingress security test**: xác nhận Spring Security/HTTP/JMS/Kafka adapter lấy tenant từ principal đáng tin, không từ một header hoặc JSON field do client có thể tự khai.

Một test chỉ truyền hai chuỗi `"tenant-a"` bằng nhau **không chứng minh** có authentication.

### 24.2. Không lộ nội bộ qua error reply

Một lỗi public nên có stable reason code. Không trả cho client:

- Full Java stack trace.
- Tên channel/bean nội bộ.
- DB credentials/tokens.
- Nội dung message của tenant khác.
- Broker topic/partition nếu không thuộc contract.
- Raw `MessageHeaders` hoặc security context object.

Gateway exception có thể chứa `failedMessage` trong cause chain. Khi map sang HTTP API/public log, phải scrub/redact, không serialize nguyên exception object.

### 24.3. Headers và trust boundaries

Trong JVM, `replyChannel`/`errorChannel` có thể là runtime channel objects. Qua broker, header mapper phải dùng allowlist; không xuất Authorization token, internal proxy details hoặc dữ liệu nhạy cảm. Tracing context có thể được propagate theo instrumentation, nhưng `traceId` không thay business `requestId`/idempotency key.

## 25. Consumer-driven contract tests và fixtures

Khi nhiều modules/teams cùng dùng gateway, một **consumer-driven contract** xác định behavior mà các consumer thật sự cần.

Ví dụ contract specification có thể biểu đạt bằng bảng:

| Consumer cần | Provider hứa | Test fixture |
|---|---|---|
| Hiển thị tổng báo giá | ACCEPTED + VND minor units | BOOK x2 → 240000 |
| Hiển thị lý do không được báo giá | REJECTED + stable reason | Quantity 0 → INVALID_QUANTITY |
| Không hiển thị sai tiền khi SKU lạ | REJECTED, amount=null | SKU UNKNOWN |
| Ghép kết quả đúng request | requestId được giữ | request-2001 |
| Không dùng quote của tenant khác | Tenant mismatch denied | tenant-a vs tenant-b |
| Không nhận false success khi worker không reply | Explicit timeout/no-reply policy | Delayed/no-reply fixture |

### 25.1. Provider verification

Provider triển khai Gateway phải chạy contract suite trên chính Spring ApplicationContext của nó. Nếu một refactor từ DirectChannel sang Router làm business error thành no-reply, verification fail trước deploy.

### 25.2. Test fixture phải thể hiện semantics

Một fixture `amount=240000` cần ghi rõ đơn vị **VND minor units**. Nếu chỉ assert số mà không giữ currency/unit contract, đổi schema từ minor sang major có thể tạo bug tài chính.

### 25.3. Không snapshot tùy tiện toàn bộ Spring Message

Nếu snapshot raw headers, nhiều trường runtime như `id`, `timestamp`, temporary reply channel hoặc trace IDs sẽ đổi hợp lệ giữa runs. Snapshot tests có thể trở nên flaky. Snapshot **public reply DTO/serialized wire contract** sau khi normalize dynamic fields sẽ bền vững hơn.

### 25.4. Chọn phạm vi compatibility

| Thay đổi | Public contract impact |
|---|---|
| Đổi private channel name | Không nếu method behavior giữ |
| Thêm Transformer nội bộ | Không nếu reply giữ semantics |
| Đổi BOOK x2 từ 240000 sang 250000 | Có nếu price là contract của scenario |
| Đổi reasonCode `INVALID_QUANTITY` thành `BAD_REQUEST` | Có nếu consumer sử dụng code |
| Đổi `QuoteReply` field type | Có |
| Biến `REJECTED` thành exception | Có |
| Đổi reply timeout public SLA | Có nếu SLA đã công bố |
| Đổi broker/serializer phía sau | Không ở Java API nếu adapter che hoàn toàn; cần test wire |
| Đổi authentication policy | Có thể ảnh hưởng behavior; security review |
| Thêm nullable field mới | Có thể tương thích tùy reader/serialization policy |

## 26. Observability phục vụ contract, không thay thế contract test

Contract tests cho biết **kịch bản cụ thể có pass hay không**; monitoring cho biết behavior ngoài production có đang drift không.

| Metric | Ý nghĩa | Labels thích hợp |
|---|---|---|
| `gateway_invocation_total` | Số method calls | method, outcome |
| `gateway_reply_total` | Typed replies | decision, method |
| `gateway_contract_error_total` | Input/API violations | reasonCode |
| `gateway_reply_timeout_total` | Không nhận reply đúng deadline | method, flow |
| `gateway_send_timeout_total` | Không gửi vào request channel kịp | flow |
| `gateway_late_reply_total` | Reply sau khi caller đã timeout | flow |
| `gateway_reply_type_mismatch_total` | Reply không convert/đúng type | flow |
| `gateway_correlation_mismatch_total` | Reply ghép sai request | flow |
| `gateway_idempotent_replay_total` | Duplicate đã được nhận diện | operation |
| `gateway_business_duration_seconds` | Duration của operation | method, decision |
| `gateway_inflight_requests` | Số request đang chờ | flow |
| `gateway_async_failure_total` | Future hoàn tất lỗi | errorClass |

### 26.1. Log có cấu trúc

~~~text
flow=quote-contract
gatewayMethod=quote
requestId=request-2001
decision=ACCEPTED
currency=VND
durationMs=16
traceId=trace-example-1001
~~~

Không dùng `requestId`, `quoteId`, `eventId`, `tenantId` hoặc `traceId` làm **metric labels với cardinality cao**. Giữ trong logs/traces có quyền phù hợp, retention, redaction/sampling. Log `reasonCode` theo taxonomy hữu hạn, không đưa raw exception chứa PII.

### 26.2. Alerts có liên hệ với contract

- Tỷ lệ reply null/no-reply tăng sau deploy Router/Filter.
- Timeout tăng sau chuyển DirectChannel sang ExecutorChannel.
- Business REJECTED bất ngờ giảm về 0 dù invalid requests vẫn có.
- ErrorChannel nhận exceptions nhưng caller chỉ thấy timeout.
- Correlation mismatch tăng khi broker replies tới sai destination.
- Async in-flight tăng và bounded executor đạt ngưỡng.
- Tenant mismatch bị ACCEPTED sau thay security mapping.
- Reply schema cũ bị consumer mới deserialize thất bại.

### 26.3. Không dùng metrics thay test failure semantics

Một dashboard không thể chứng minh "mọi invalid quantity đều trả INVALID_QUANTITY" với đầy đủ boundary cases. Contract test phải chủ động gửi fixtures; monitoring bắt những distribution changes ngoài dữ liệu test.

## 27. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ test `MessageChannel.send()` | Không phát hiện gateway proxy lỗi | Gọi interface bean trong Spring test |
| Chỉ test business handler | Sai `@Header`/requestChannel vẫn lọt | Gateway integration test |
| Chỉ test fake Gateway | Không xác minh proxy registration | Có provider verification thật |
| Assert tên proxy class | Fragile theo framework version | Assert interface behavior |
| Assert mỗi Handler chỉ gọi một lần | Refactor hợp lệ làm test đỏ | Kiểm tra business outcome |
| Chỉ test happy path BOOK | REJECTED/exception bị phá không phát hiện | Outcome/error matrix |
| Quantity 0 thành Filter drop | Gateway timeout | Explicit REJECTED reply |
| Router unknown SKU không fallback | Không có reply | Default rejection/error route |
| Handler trả null được coi là SUCCESS | Caller có thể xử lý sai | Strict non-null public adapter |
| Dùng replyTimeout để ngắt DirectChannel | Handler vẫn block | Timeout ở I/O client hoặc async boundary |
| Test timeout bằng sleep chính xác 10ms | Flaky CI | Latch, bounded futures, margin |
| Gọi `join()` và coi là nonblocking | Caller vẫn chờ | Compose async result |
| Trả `void` và hứa task đã commit | False success | Receipt/tracking state |
| Dùng shared reply queue không correlation | Reply lẫn callers | Correlation protocol/temporary channel |
| Dùng Spring Message ID làm business ID | Redelivery đổi ID | Stable request/command ID |
| Retry sau timeout với ID mới | Duplicate side effects | Idempotency/reconciliation |
| Mock authentication bằng payload header | Cross-tenant bug | Trusted principal/claims test |
| Copy `replyChannel` object qua Kafka | Remote JVM không có object | Reply destination/correlation |
| Chỉ test Java DTO, không test JSON | Wire contract vỡ | Adapter serialization fixtures |
| Chỉ assert HTTP 200 cho valid reply | Status đúng nhưng amount sai | Assert field semantics |
| Dùng `assertTrue(duration<5ms)` trên CI | Flaky | Tách SLA/load tests |
| Không test no-reply khi có Aggregator | Hang/timeout production | Partial/expiry contract |
| Error flow chỉ log nhưng API cần reply | Caller thiếu outcome | Error mapping/rethrow |
| Dùng metric labels là requestId | Cardinality tăng | Bounded dimensions |
| Thay public reason code không báo consumers | Breaking change | Version/consumer-driven tests |
| Gọi in-memory test là exactly-once | Sai reliability guarantee | Broker/DB side effect tests |

## 28. Bài tập thực hành

**Bài 1 — Public contract.** Từ `QuoteContractGateway.quote`, viết rõ accepted/rejected/exception/null semantics, amount unit, requestId propagation.

**Bài 2 — Unit handler.** Chạy `QuoteServiceTest`; test BOOK x2, PEN x3, quantity=0, SKU lạ và tenant mismatch.

**Bài 3 — Gateway bean.** Dựng `QuoteContractFlowConfiguration`. Dùng `@SpringJUnitConfig` và `@Autowired` để gọi Gateway method thật.

**Bài 4 — Header regression.** Đổi `@Header("authenticatedTenant")` thành `@Header("tenant")` mà không đổi handler; xác nhận contract test thất bại rồi sửa.

**Bài 5 — Typed rejection.** Thêm Filter quantity > 0 mà không tạo reply; quan sát contract regression và sửa bằng explicit REJECTED outcome.

**Bài 6 — Router fallback.** Chia handlers theo SKU. Gửi SKU lạ và kiểm chứng reply `SKU_UNSUPPORTED`.

**Bài 7 — No-reply.** Viết `StrictQuotePortTest`: fake gateway trả null, public adapter phải ném `QUOTE_REPLY_MISSING`.

**Bài 8 — Exception wrapper.** Thay một handler throw `QuoteContractException`, dùng `QuoteExceptionChecks` tìm typed cause.

**Bài 9 — Refactor flow.** Đổi DirectChannel handler thành Transformer + Router + Handler; chạy lại nguyên contract suite.

**Bài 10 — Parallel requests.** Chạy `ParallelQuoteGatewayContractTest`, kiểm tra requestId/amount không bị tráo giữa hai callers.

**Bài 11 — Async API.** Định nghĩa `AsyncQuoteGateway` trả CompletableFuture, test thành công và exceptional completion với bounded timeout.

**Bài 12 — Timeout.** So sánh DirectChannel slow handler và ExecutorChannel reply timeout. Giải thích vì sao replyTimeout không preempt code đồng bộ.

**Bài 13 — Fault injection.** Cho Handler không trả reply, Router thiếu route, Aggregator thiếu một part; định nghĩa explicit timeout/error contract.

**Bài 14 — Error channel.** Cấu hình error handler cho ExecutorChannel, xác nhận ErrorMessage không tự tương đương QuoteReply.

**Bài 15 — Void Gateway.** Viết one-way audit Gateway và test sự khác nhau giữa dispatch acceptance với durable business commit.

**Bài 16 — Broker request/reply.** Thiết kế reply-to/correlation; đưa hai requests A/B qua broker giả có đảo thứ tự reply, assert không cross-wire.

**Bài 17 — Idempotent command.** Tạo commandId, gửi duplicate và assert business state chỉ thay đổi một lần, dù Handler nhận nhiều deliveries.

**Bài 18 — Tenant isolation.** Tạo ingress test principal tenant-a với payload tenant-b; assert bị từ chối trước side effect.

**Bài 19 — Wire schema.** Serialize `QuoteReply` thành JSON, test field names, enum value, null policy, amount unit.

**Bài 20 — Consumer-driven contract.** Viết fixtures do consumer cung cấp; provider verification chạy trên Gateway bean thật.

**Bài 21 — Logging.** Thiết kế metrics cho success/rejected/timeout/no-reply theo method/reason, không dùng requestId làm label.

**Bài 22 — CI strategy.** Phân loại unit, gateway contract, adapter, E2E và fault-injection tests theo chi phí và mục tiêu.

## 29. Ma trận kiểm thử công khai tối thiểu

| # | Dữ liệu/điều kiện | Kỳ vọng ở public boundary | Tầng test |
|---|---|---|---|
| 1 | BOOK x2, tenant-a | ACCEPTED, 240000 VND | Gateway integration |
| 2 | PEN x3, tenant-a | ACCEPTED, 45000 VND | Gateway integration |
| 3 | Quantity=0 | REJECTED INVALID_QUANTITY | Gateway integration |
| 4 | Quantity âm | REJECTED INVALID_QUANTITY | Gateway integration |
| 5 | SKU UNKNOWN | REJECTED SKU_UNSUPPORTED | Gateway integration |
| 6 | requestId thiếu | Typed contract error | Gateway integration |
| 7 | tenantId trống | Typed contract error | Gateway integration |
| 8 | Header tenant-b, payload tenant-a | Typed conflict | Gateway integration |
| 9 | Header tenant-b, payload tenant-b | Accepted, correct context | Gateway integration |
| 10 | Gateway bean không được scan | Test context/injection fails | Gateway integration |
| 11 | Handler trả sai reply type | Conversion/mapping error | Gateway integration |
| 12 | Handler trả null | No-reply policy | Gateway/adapter |
| 13 | Filter drops invalid request | Must not return success | Gateway integration |
| 14 | Router unknown SKU | Must return explicit rejection | Gateway integration |
| 15 | Aggregator không release | Timeout/partial reply policy | Flow + Gateway |
| 16 | DirectChannel slow handler | No false timeout assumption | Controlled integration |
| 17 | Async late reply | No cross-request reply | Controlled integration |
| 18 | Two concurrent requests | Correct requestId/amount | Gateway integration |
| 19 | CompletableFuture success | Typed completion | Async Gateway integration |
| 20 | CompletableFuture failure | Exceptional completion | Async Gateway integration |
| 21 | Broker reply out of order | Correct correlation | Adapter integration |
| 22 | Broker redelivery | Idempotent state/receipt | E2E/DB/broker |
| 23 | HTTP JSON field renamed | Schema contract failure | Adapter/CDC |
| 24 | HTTP principal tenant mismatch | Forbidden/no side effect | Security adapter |
| 25 | Header Authorization leak | No secret outbound | Adapter integration |
| 26 | No-reply error routed only to log | Not acceptable as quote | Gateway/error flow |
| 27 | Stable reason code changed | Consumer contract regression | CDC |
| 28 | SLA exceeded | Deadline policy | SLA/performance tests |

### 29.1. Thứ tự chạy trong CI

Một pipeline thực dụng:

1. **Unit tests nhanh**: QuoteService và consumer fake tests.
2. **Gateway contract integration tests**: ApplicationContext nhỏ gọi interface thực.
3. **Adapter/schema tests**: JSON serializer, Spring Security ingress, broker correlation.
4. **End-to-end/fault injection**: broker, database, timeout, redelivery, late reply.
5. **SLA/load tests**: môi trường đủ ổn định để kiểm tra latency/thông lượng.

Không bắt mọi pull request chạy một cluster thật nếu unit/gateway contract tests đã bắt được phần lớn regression; tuy nhiên không bỏ các tầng test cao khi chúng là guarantee đã hứa với consumer.

## 30. Checklist trước khi công bố Gateway API

- [ ] Public Java interface có request/reply/error contract rõ.
- [ ] `requestId`, `tenantId`, currency và amount units được định nghĩa.
- [ ] BUSINESS REJECTED được phân biệt với technical exception.
- [ ] Reason codes cần ổn định được liệt kê và test.
- [ ] Không trả null như thành công nếu API contract cấm.
- [ ] `@MessagingGateway` và `@IntegrationComponentScan` đăng ký bean đúng.
- [ ] `@Gateway` request channel và method overrides được test.
- [ ] `@Header` mapping được kiểm tra qua behavior của Gateway.
- [ ] Mọi non-void method có reply path hoàn chỉnh.
- [ ] Filter/Router fallback không silently drop request cần reply.
- [ ] Aggregator release/expiry và partial result policy rõ.
- [ ] `requestTimeout`/`replyTimeout` explicit, không hiểu nhầm là deadline tổng.
- [ ] Remote I/O clients có timeout riêng.
- [ ] Async Gateway có bounded executor, failure/timeout/cancellation policy.
- [ ] One-way `void` không bị hiểu là durable business commit.
- [ ] ErrorChannel errors có public mapping khi cần.
- [ ] Cause chain/wrapper không được hardcode nếu không thuộc contract.
- [ ] Public exception class/typed reply được chuẩn hóa khi cần.
- [ ] Reply đúng request khi concurrent calls/out-of-order replies.
- [ ] Cross-JVM reply-to/correlation headers có adapter contract.
- [ ] Không serialize `replyChannel` hoặc security context object ra broker.
- [ ] Stable command ID và idempotent receiver nếu method có side effects.
- [ ] Retry timeout không tự tạo command ID mới cho cùng business action.
- [ ] Có transaction/ACK/outbox policy phù hợp.
- [ ] Authenticating principal/tenant nằm ở ingress.
- [ ] Header allowlist không lộ token/PII.
- [ ] Java DTO changes và JSON/wire schema changes có version policy riêng.
- [ ] Unit tests handler không thay gateway integration tests.
- [ ] Consumer fake tests không thay provider verification.
- [ ] Gateway integration tests gọi **interface bean thực**.
- [ ] Test happy path, rejection, exception, no-reply và concurrency.
- [ ] Adapter tests kiểm tra HTTP/broker/serializer khi có external boundary.
- [ ] Logs/metrics theo method/outcome/reason, không dùng high-cardinality IDs.
- [ ] CI phân tầng unit/contract/adapter/E2E/SLA.
- [ ] Contract suite chạy lại khi refactor Router/Filter/Transformer/Gateway.
- [ ] Có runbook cho late reply, DLQ, replay, reconciliation và rollback.

## 31. Tổng kết

**Kiểm thử gateway theo hợp đồng công khai** nghĩa là kiểm tra **điều caller thật sự thấy khi gọi Java interface**, không chỉ kiểm tra một channel nội bộ nhận message. Với Spring Integration, `@MessagingGateway` tạo proxy chuyển method invocation thành message rồi ghép reply/error về return type. Bởi vậy contract tests cần gọi **bean interface thật** qua Spring context, xác minh input/header mapping, typed success, business rejection, lỗi contract, non-null policy, correlation và các edge cases do Filter/Router/Aggregator gây ra.

Hãy phân tầng kiểm thử: **unit tests** cho domain handler; **consumer fake tests** cho logic của caller; **gateway integration tests** cho proxy/request-reply wiring; **adapter/schema tests** cho HTTP/broker/serialization; **E2E/fault tests** cho transaction, retry, late reply và idempotency. Một fake test xanh không chứng minh Gateway được scan; một DirectChannel test xanh không chứng minh ACK broker; một reply timeout không chứng minh remote side effect đã rollback.

Trong module **SPRING_INTEGRATION_PATTERN**, cách tiếp cận này cho phép refactor Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry và error channel mà vẫn duy trì **API ít phụ thuộc, có ngữ nghĩa rõ và được kiểm chứng**. Public contract phải trung thực về những gì Gateway bảo đảm — và những gì nó **không** bảo đảm.

### Tài liệu tham khảo

- Enterprise Integration Patterns — Messaging Gateway: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html
- Spring Integration Reference — Messaging Gateways: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message: https://docs.spring.io/spring-integration/reference/message.html
- Spring Integration Reference — Message Channels: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference — Error Handling: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference — Filter: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration API — MessagingGateway: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/MessagingGateway.html
- Spring Integration API — Gateway: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Gateway.html
- Spring Integration API — IntegrationComponentScan: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/IntegrationComponentScan.html
- Spring Framework Reference — Testing: https://docs.spring.io/spring-framework/reference/testing.html
- Spring Framework Reference — Task Execution: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/








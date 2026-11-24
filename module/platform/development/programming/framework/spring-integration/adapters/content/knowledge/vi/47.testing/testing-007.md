# Test gateway request-reply trong Spring Integration

Trong một hệ thống tích hợp, luồng **gửi message một chiều** khác căn bản với luồng **gửi yêu cầu rồi chờ phản hồi**. Một outbound adapter có thể phát thông điệp tới broker mà không chờ kết quả nghiệp vụ; ngược lại, gateway thường phải liên kết một request với đúng reply, xử lý lỗi và timeout theo hợp đồng. Nếu kiểm thử chỉ xác nhận `MessageChannel.send() == true`, ta có thể bỏ sót việc gateway không nhận reply, nhận sai response, trả lời nhầm request, hết hạn chờ hoặc đánh dấu thành công khi hệ thống ngoài mới chỉ xác nhận đã tiếp nhận yêu cầu.

**Test gateway request-reply** là kiểm thử hành vi **yêu cầu → kênh truyền → xử lý → phản hồi**, gồm cả *happy path*, request không hợp lệ, lỗi bên xử lý, không có reply, reply đến muộn, concurrency và hành vi khi kết nối với hệ thống ngoài. Bài học này thuộc chương **Testing** của module `SPRING_INTEGRATION_ADAPTERS`, nơi Spring Integration kết nối File, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu bằng inbound/outbound adapter, gateway, poller và `MessageChannel`.

Điểm cần phân biệt xuyên suốt bài: **gateway nội bộ Spring Integration có thể được kiểm thử hoàn toàn trong bộ nhớ**, nhưng **gateway kết nối HTTP hoặc broker thật** còn cần kiểm thử giao thức và trạng thái thực tế ở đầu kia.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **gateway**, **inbound/outbound adapter**, **request-reply** và **fire-and-forget**.
2. Giải thích vai trò `@MessagingGateway`, `@Gateway`, `MessageChannel`, `replyChannel`, `errorChannel` và thời gian chờ gửi/nhận.
3. Viết flow test với JUnit Jupiter và Spring Test, gọi gateway interface như một API Java.
4. Test reply payload/type, business headers, correlation và tính đúng của routing.
5. Dùng `GenericMessagingTemplate` để kiểm tra channel request-reply trực tiếp, không cần proxy gateway.
6. Cô lập outbound boundary bằng `@SpringIntegrationTest`, `MockIntegrationContext` hoặc fake handler **có reply**, tránh tạo timeout giả do dùng Mockito mock một chiều.
7. Thiết kế test timeout, exception, reply chậm, concurrency, cancellation và recovery có điểm quan sát rõ.
8. Áp dụng kiểm thử request-reply cho HTTP, JMS/AMQP, Kafka hoặc các hệ thống không hỗ trợ RPC tự nhiên.
9. Phân tầng unit, flow isolation, contract, transport integration và end-to-end; không nhầm mock pass với kết nối thật thành công.
10. Lập test matrix, fixture, checklist CI và bài tập để vận hành gateway ổn định.

## 2. Gateway request-reply là gì?

Gateway là điểm kết nối giữa **ngữ nghĩa gọi một thao tác có phản hồi** và **thế giới message** của Spring Integration.

~~~mermaid
sequenceDiagram
    participant Caller as Java caller / HTTP client
    participant Gateway as Messaging Gateway
    participant Channel as Request Channel
    participant Handler as Service / Outbound Gateway
    participant Reply as Reply Channel
    Caller->>Gateway: submit(request)
    Gateway->>Channel: Message(payload, headers)
    Channel->>Handler: request message
    Handler->>Reply: response message
    Reply->>Gateway: matched reply
    Gateway-->>Caller: response object
~~~

Gateway có thể là **proxy Java interface** được tạo bởi `@MessagingGateway`, HTTP inbound gateway chuyển HTTP request thành message và trả HTTP response, hoặc outbound gateway thực hiện request/reply với HTTP/JMS/AMQP đích.

| Thành phần | Ngữ nghĩa | Ví dụ |
|---|---|---|
| **Inbound channel adapter** | Nhận dữ liệu rồi phát message vào flow, thường không có reply cho nguồn. | File inbound polling adapter. |
| **Outbound channel adapter** | Nhận message rồi gửi một chiều tới đích. | Gửi sự kiện tới Kafka topic. |
| **Inbound gateway** | Nhận request từ bên ngoài, thực hiện flow, trả reply. | HTTP POST trả HTTP 200 kèm body. |
| **Outbound gateway** | Gửi request từ flow tới hệ thống ngoài, chờ response. | HTTP GET/POST gọi dịch vụ đối tác. |
| **Messaging gateway proxy** | Cho Java code gọi flow bằng method có kiểu rõ ràng. | `OrderReply submit(OrderRequest request)`. |

**Không phải mọi transport đều tự có RPC.** HTTP có request/response ở giao thức. JMS/AMQP có thể hiện thực request/reply bằng reply destination và correlation. Kafka chủ yếu là event log; request/reply cần quy ước topic, key, correlation và trạng thái chờ riêng nếu nghiệp vụ thực sự cần.

## 3. Hợp đồng kiểm thử của gateway

Trước khi viết test, phải định nghĩa gateway hứa điều gì:

| Nhóm hợp đồng | Câu hỏi kiểm thử | Ví dụ |
|---|---|---|
| **Request payload** | Gateway nhận kiểu gì, trường nào bắt buộc? | `OrderRequest(orderId, tenantId)`. |
| **Request headers** | Header nào có giá trị nghiệp vụ hoặc tracing? | `traceId`, `schemaVersion`. |
| **Reply payload** | Kết quả có kiểu, nội dung và status đúng? | `OrderReply("PO-1", "ACCEPTED")`. |
| **Reply correlation** | Phản hồi có trở về đúng request khi concurrency? | Request A không nhận response B. |
| **Reply cardinality** | Một request mong đợi một reply hay một chuỗi? | Truy vấn trạng thái đơn hàng trả đúng một snapshot. |
| **Timeout** | Nếu không có reply đúng hạn thì làm gì? | Trả lỗi hoặc kết quả timeout theo contract. |
| **Error mapping** | Lỗi validation/network/5xx được thể hiện thế nào? | `INVALID_REQUEST`, `UPSTREAM_TIMEOUT`. |
| **No reply** | Missing reply có bị nhận nhầm là thành công? | Không báo `ACCEPTED` khi target im lặng. |
| **Late reply** | Reply đến sau timeout được xử lý ra sao? | Không ghép nhầm sang request mới. |
| **Security** | Tenant/identity được lấy từ nguồn đáng tin? | Không tin header `role=admin` do client tự gửi. |
| **Side effect** | Đã gửi yêu cầu hay đã hoàn tất nghiệp vụ? | HTTP 202 khác xác nhận công việc đã xong. |

**Từ vựng kết quả phải nhất quán.** `REQUESTED`/`SENT` khác `ACKNOWLEDGED`, khác `COMPLETED` đã được chứng minh. Nếu dịch vụ đối tác trả `202 Accepted`, thông thường điều đó chỉ nói yêu cầu được chấp nhận để xử lý, không mặc nhiên có nghĩa dữ liệu đã lưu xong.

## 4. Bản đồ các đối tượng Spring Integration liên quan

| API/khái niệm | Mục đích | Rủi ro khi test |
|---|---|---|
| `@MessagingGateway` | Khai báo Java interface cho message flow. | Không đăng ký proxy hoặc dùng sai request channel. |
| `@Gateway` | Cấu hình một method gateway (request/reply channel, timeout...). | Annotation bị đặt sai chỗ hoặc timeout không áp dụng như mong đợi. |
| `GatewayProxyFactoryBean` | Thành phần nền tạo gateway proxy. | Không phải mọi flow test cần cấu hình trực tiếp class này. |
| `MessageChannel` | Đưa request tới handler/flow. | Send được chấp nhận nhưng không có reply. |
| `MessageHeaders.REPLY_CHANNEL` | Địa chỉ nhận reply khi message cần phản hồi. | Handler không trả reply hoặc tự ghi đè sai header. |
| `MessageHeaders.ERROR_CHANNEL` | Địa chỉ xử lý lỗi khi flow dùng cơ chế tương ứng. | Ngộ nhận mọi exception luôn được gửi vào error channel. |
| `MessagingTemplate` / `GenericMessagingTemplate` | Gửi và nhận message trực tiếp bằng template. | Nhầm response `null` do timeout với business result. |
| `DirectChannel` | Gửi đồng bộ tới subscriber. | Exception có thể quay về caller ngay. |
| `ExecutorChannel` | Chuyển xử lý sang executor. | `send()` trả về trước khi handler hoàn tất. |
| `QueueChannel` | Channel có thể `receive(timeout)`. | Message cũ/test khác gây sai assertion. |
| `@SpringIntegrationTest` | Hỗ trợ Spring Integration test context. | Không tự mock mọi external endpoint. |
| `MockIntegrationContext` | Thay tạm handler/source của endpoint phù hợp. | Mock handler không phát reply gây gateway timeout. |

### Reply channel mặc định không phải luôn là một bean có tên cố định

Gateway proxy có thể thiết lập một **reply channel tạm thời cho request đang chờ** thông qua header. Trong những flow không cấu hình output channel tường minh, reply-producing handler có thể đưa phản hồi trở lại channel này. Một số gateway được cấu hình reply channel riêng. Test phải hiểu **đường đi thực tế trong application context** thay vì suy luận “mọi reply đều đến bean `replyChannel`”.

Không gán hoặc chuyển `replyChannel` thành một chuỗi hay một `QueueChannel` tùy ý trong business code. Khi cần làm fake handler, phải xử lý đúng kiểu và cơ chế mà endpoint đang sử dụng.

## 5. Chọn tầng kiểm thử đúng

| Tầng test | Có gateway proxy? | Có transport thật? | Điều được chứng minh |
|---|---|---|---|
| **Unit test** | Không bắt buộc | Không | Validator, mapper, business rule. |
| **Flow test** | Có thể có | Không | Request đi vào flow, handler trả reply, proxy map kiểu dữ liệu. |
| **Mock boundary test** | Có | Không | Message đến đúng outbound handler và fake tạo reply tương ứng. |
| **Contract test** | Có thể có | Stub/mock server | Request/response schema, header, status/error, version. |
| **Transport integration** | Có | Có | HTTP/SFTP/JMS/AMQP/Kafka/DB behavior thực tế. |
| **End-to-end** | Có | Có nhiều hệ thống | Kết quả cuối và khả năng recovery qua nhiều ranh giới. |

Một bộ kiểm thử tốt có nhiều test nhanh cho **payload, routing, correlation và failure mapping**, cùng số lượng vừa đủ test chậm cho **TLS, broker acknowledgment, transaction và network recovery**.

~~~mermaid
flowchart TB
    U["Unit tests<br/>DTO / validation / mapping"] --> F["Flow tests<br/>Gateway + channels"]
    F --> M["Mock boundary tests<br/>Fake reply / timeout / error"]
    M --> T["Transport tests<br/>HTTP server / broker / DB"]
    T --> E["End-to-end tests<br/>Verified business outcome"]
~~~

## 6. Dependency cho bộ test

Với dự án đã dùng Spring Boot BOM/dependency management tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.integration:spring-integration-core")
    testImplementation("org.springframework.integration:spring-integration-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Khi kiểm thử adapter cụ thể, thêm module tương ứng như `spring-integration-http`, `spring-integration-jms`, `spring-integration-amqp`, `spring-integration-kafka`, `spring-integration-sftp` hoặc `spring-integration-jdbc` theo khả năng dự án. Stub HTTP, Testcontainers hay broker nhúng là **thư viện/cơ chế riêng**, không tự xuất hiện chỉ nhờ `spring-integration-test`.

**Tính tương thích:** cách Java DSL, annotation, default timeout và mapping lỗi có thể khác theo dòng phiên bản Spring Framework/Spring Integration. Ví dụ dưới đây minh họa mô hình API thông dụng, không tự áp đặt version cho dự án dùng BOM khác. Khi tích hợp production, kiểm tra chữ ký overload, transport adapter và error contract của phiên bản đang chạy.

## 7. Ví dụ 1 — Test @MessagingGateway với Java DSL và JUnit

Tạo một dịch vụ nội bộ nhận yêu cầu đơn hàng, kiểm tra `orderId` và trả `OrderReply`. **Không có HTTP hoặc broker thật**: mục tiêu là xác minh Java gateway proxy, channel wiring và reply mapping.

### 7.1. DTO và interface

~~~java
package example.gateway;

public record OrderRequest(String orderId, String tenantId) {}

public record OrderReply(String orderId, String status) {}
~~~

~~~java
package example.gateway;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
        defaultRequestChannel = "orderRequests",
        defaultReplyTimeout = 2_000)
public interface OrderGateway {
    OrderReply submit(OrderRequest request);
}
~~~

Lưu ý `@MessagingGateway` trên **interface**, còn implementation được Spring Integration tạo. Dự án cần bật cơ chế đăng ký/scan gateway phù hợp.

### 7.2. Cấu hình IntegrationFlow

~~~java
package example.gateway;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
@IntegrationComponentScan(basePackageClasses = OrderGateway.class)
public class OrderGatewayTestConfig {

    @Bean
    DirectChannel orderRequests() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderFlow(DirectChannel orderRequests) {
        return IntegrationFlow.from(orderRequests)
                .handle(OrderRequest.class, (request, headers) -> {
                    if (request.orderId() == null
                            || request.orderId().isBlank()) {
                        throw new IllegalArgumentException(
                                "orderId is required");
                    }
                    if (request.tenantId() == null
                            || request.tenantId().isBlank()) {
                        throw new IllegalArgumentException(
                                "tenantId is required");
                    }
                    return new OrderReply(
                            request.orderId().strip(), "ACCEPTED");
                })
                .get();
    }
}
~~~

Flow có **reply-producing handler** trả `OrderReply`. Không gắn output channel cố định trong ví dụ; trong request/reply flow, phản hồi được đưa về reply channel do gateway thiết lập. Ở code thực tế, khi chuyển sang outbound HTTP/JMS gateway, reply của remote adapter sẽ đi qua handler/flow và mapping tương ứng trước khi về proxy.

### 7.3. Bài kiểm thử

~~~java
package example.gateway;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OrderGatewayTestConfig.class)
class OrderGatewayFlowTest {

    @Autowired
    OrderGateway gateway;

    @Test
    void returnsTypedReplyForValidRequest() {
        OrderReply reply = gateway.submit(
                new OrderRequest("  PO-2048  ", "VN"));

        assertNotNull(reply);
        assertEquals("PO-2048", reply.orderId());
        assertEquals("ACCEPTED", reply.status());
    }

    @Test
    void rejectsMissingOrderId() {
        RuntimeException exception = assertThrows(
                RuntimeException.class,
                () -> gateway.submit(
                        new OrderRequest("  ", "VN")));

        assertNotNull(exception);
        // Tùy phiên bản/flow, nguyên nhân có thể được wrap
        // trong MessagingException hoặc chuyển về caller.
    }
}
~~~

**Điều đã kiểm tra:** proxy gateway được đăng ký, request đi vào `orderRequests`, handler biến đổi dữ liệu và reply được map về `OrderReply`. **Điều chưa kiểm tra:** HTTP, JDBC, broker, TLS hay hệ thống đích đã thực sự làm gì.

**Lưu ý test lỗi:** nếu phải kiểm tra loại exception/`cause` cụ thể, hãy đặc tả và kiểm thử error contract của gateway trong dự án. Không nên khẳng định mọi exception luôn truyền nguyên dạng qua proxy; việc wrap, xử lý error channel và kiểu trả về có thể khác theo configuration.

## 8. Ví dụ 2 — Test request-reply trực tiếp bằng GenericMessagingTemplate

Có lúc ta muốn kiểm tra **channel và handler** mà không phụ thuộc interface proxy. `GenericMessagingTemplate` hỗ trợ gửi một `Message<?>` rồi chờ reply.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.core.GenericMessagingTemplate;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OrderGatewayTestConfig.class)
class DirectRequestReplyChannelTest {

    @Autowired
    @Qualifier("orderRequests")
    MessageChannel requestChannel;

    @Test
    void sendsMessageAndReceivesReply() {
        GenericMessagingTemplate template =
                new GenericMessagingTemplate();
        template.setReceiveTimeout(1_000);

        Message<OrderRequest> request = MessageBuilder
                .withPayload(new OrderRequest("PO-77", "VN"))
                .setHeader("traceId", "trace-77")
                .build();

        Message<?> reply = template.sendAndReceive(
                requestChannel, request);

        assertNotNull(reply);
        assertInstanceOf(OrderReply.class, reply.getPayload());
        OrderReply body = (OrderReply) reply.getPayload();
        assertEquals("PO-77", body.orderId());
        assertEquals("ACCEPTED", body.status());
    }
}
~~~

Test này đi thẳng qua `MessageChannel` và **không kiểm tra các annotation mapping/conversion trên method của `@MessagingGateway`**. Vì vậy nên duy trì ít nhất một test gọi **proxy thật** nếu ứng dụng sử dụng proxy đó cho production.

### 8.1. Message ID và business correlation

Mỗi `Message<?>` có header metadata do framework quản lý, nhưng **`MessageHeaders.ID` không nên mặc định được dùng như business event ID xuyên transport**. Khi flow có transformer, serializer, reply hoặc kết nối broker, message ID có thể thay đổi. Truy vết nghiệp vụ nên dùng một `requestId`/`traceId` được tạo và quản trị theo hợp đồng.

Không dùng assertion bắt buộc `request.getHeaders().getId() == reply.getHeaders().getId()` nếu đây không phải cam kết thực tế của flow. Điều quan trọng là **reply đúng request/nghiệp vụ**.

## 9. Kiểm thử request/reply headers và correlation

Một gateway nhiều người dùng cần giữ đúng dữ kiện bảo mật, định tuyến và truy vết:

| Header/tham chiếu | Vai trò | Kiểm thử |
|---|---|---|
| `requestId` hoặc `correlationId` | Định danh yêu cầu nghiệp vụ | Trả lời đúng request sau chuyển đổi/routing. |
| `traceId` | Liên kết log/tracing | Không bị mất tại outbound boundary; response logging liên kết được. |
| `tenantId` | Ngữ cảnh tenant | Được xác minh từ nguồn tin cậy, không điều hướng chéo tenant. |
| `schemaVersion` | Chọn hợp đồng payload | Response đúng version hoặc reject có kiểm soát. |
| `replyChannel` | Địa chỉ reply trong Spring Messaging | Không bị transformer ghi đè sai; handler trả reply đúng. |
| `errorChannel` | Đường lỗi được cấu hình | Exception/lỗi nghiệp vụ được xử lý theo policy, không bị nuốt. |
| `contentType` | Quy ước tuần tự hóa | HTTP/JMS/AMQP/Kafka mapping không làm sai kiểu dữ liệu. |

### 9.1. Không tự sao chép mọi header vào reply

Khi tạo reply, chỉ **bảo toàn những metadata cần theo hợp đồng**. Đặc biệt:

- `replyChannel` và `errorChannel` là metadata điều khiển của Spring; xử lý sai có thể làm vòng lặp reply hoặc lộ channel.
- `id`/`timestamp` của message có semantics riêng.
- Header do client gửi không có nghĩa là đã xác thực.
- Một số transport có header riêng như JMS correlation, HTTP status hoặc Kafka topic/key; **không có một bảng ánh xạ cố định cho mọi adapter**.

### 9.2. Correlation dưới tải đồng thời

~~~mermaid
sequenceDiagram
    participant A as Caller A
    participant B as Caller B
    participant G as Gateway
    participant H as Handler / Partner
    A->>G: req A, requestId=A
    B->>G: req B, requestId=B
    G->>H: req A
    G->>H: req B
    H-->>G: reply B trước
    G-->>B: response B
    H-->>G: reply A sau
    G-->>A: response A
~~~

Trong test concurrency, làm cho **reply B đến trước reply A** bằng latch/barrier rồi kiểm tra hai caller nhận đúng kết quả. Không dùng **thứ tự thời gian phản hồi** làm quy tắc ghép request; các channel, gateway hoặc transport cần correlation đúng semantics.

## 10. Mock outbound gateway boundary: phải tạo reply

`MockIntegrationContext` có thể thay handler của endpoint tương thích để test **đường đi nội bộ** mà không gọi đối tác. Nhưng với gateway request-reply, một Mockito mock handler mặc định không trả reply. Kết quả thường là **caller tiếp tục chờ**, không phải flow thành công.

### 10.1. Vấn đề của mock một chiều

~~~java
MessageHandler noReply = message -> {
    // Ghi nhận request nhưng KHÔNG trả reply.
};

mockContext.substituteMessageHandlerFor(
        "partnerBoundaryEndpoint", noReply);
~~~

Nếu gateway đang đợi response, đoạn trên chỉ phù hợp cho test **no-reply/timeout**, không phải happy path.

### 10.2. Fake handler trả reply qua replyChannel

Với **một flow đồng bộ có reply channel được đặt trong header** và endpoint thích hợp để substitute, test có thể dùng fake:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

MessageHandler fakePartner = requestMessage -> {
    Object replyDestination = requestMessage
            .getHeaders().get(MessageHeaders.REPLY_CHANNEL);

    if (!(replyDestination instanceof MessageChannel replyChannel)) {
        throw new IllegalStateException(
                "Test request does not contain a MessageChannel reply");
    }

    OrderRequest request = (OrderRequest) requestMessage.getPayload();
    OrderReply reply = new OrderReply(
            request.orderId(), "PARTNER_CONFIRMED");

    replyChannel.send(MessageBuilder.withPayload(reply)
            .setHeader("traceId",
                    requestMessage.getHeaders().get("traceId"))
            .build());
};

mockContext.substituteMessageHandlerFor(
        "partnerBoundaryEndpoint", fakePartner);
~~~

**Giới hạn:** đây là kỹ thuật fake ở một **MessageHandler boundary** có `MessageChannel` reply destination rõ ràng. Một outbound gateway cụ thể có thể sử dụng cơ chế reply khác, cần cơ chế mock/fake phù hợp với endpoint và phiên bản. Không giả định mọi outbound adapter đều có `MessageHeaders.REPLY_CHANNEL` kiểu `MessageChannel` hoặc có thể thay bằng handler tự viết như vậy.

### 10.3. Test không được bypass logic cần kiểm tra

Nếu mục tiêu là kiểm tra transformer → router → outbound gateway, hãy substitute **tại outbound boundary** và giữ transformer/router thật. Nếu substitute quá sớm ở input channel, bài test có thể pass dù wiring của flow sai.

~~~mermaid
flowchart LR
    JAVA["Gateway proxy"] --> IN["Request channel"]
    IN --> VALID["Validation"]
    VALID --> TRANSFORM["Transformer"]
    TRANSFORM --> BOUND["Outbound gateway boundary<br/>Fake handler + reply"]
    BOUND --> RESP["Reply to caller"]
    MC["MockIntegrationContext"] -. "Thay ở boundary" .-> BOUND
~~~

## 11. Test @SpringIntegrationTest và lifecycle của mock

Một mẫu test có `MockIntegrationContext`:

~~~java
import org.junit.jupiter.api.AfterEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PartnerGatewayFlowTestConfig.class)
@SpringIntegrationTest
class PartnerGatewayFlowTest {

    @Autowired
    MockIntegrationContext mockContext;

    @Autowired
    PartnerGateway gateway;

    @AfterEach
    void restore() {
        mockContext.resetBeans();
    }

    // Trong từng @Test:
    // 1. Tạo fake handler có reply.
    // 2. Substitute đúng endpoint ID.
    // 3. Gọi gateway và assert response/correlation.
    // 4. Không sử dụng network thật ở isolation test.
}
~~~

Ví dụ là **khung tổ chức test**: `PartnerGateway` và `PartnerGatewayFlowTestConfig` đại diện cho interface/config của flow dự án. Điều cốt lõi là endpoint được đặt ID rõ, substitution diễn ra trước request và `resetBeans()` luôn chạy.

`resetBeans()` khôi phục endpoint substitution nhưng **không tự xóa message trong QueueChannel, xóa request pending, đóng thread/executor do test tạo hoặc dọn dữ liệu ở server ngoài**. Khi có flow async, cần đợi in-flight work được xử lý hoặc chủ động cô lập context/fixture trước teardown.

## 12. Timeout: có nhiều loại khác nhau

Một gateway có thể timeout ở nhiều điểm và test cần xác định chính xác **mốc bắt đầu – mốc kết thúc – hành vi trả về**.

| Loại timeout | Xảy ra khi | Kết quả test nên kiểm tra |
|---|---|---|
| **Request send timeout** | Không gửi được request vào channel/queue trong giới hạn. | Fail/timeout theo gateway/channel policy, không gửi trùng. |
| **Reply receive timeout** | Request đã gửi nhưng không có reply đúng hạn. | Caller không chờ vô hạn; kết quả/null/error theo hợp đồng. |
| **Outbound HTTP timeout** | Connect/read tới HTTP server quá hạn. | Exception/mapping, retry/backoff, correlation. |
| **JMS/AMQP reply timeout** | Broker nhận request nhưng reply destination không có message phù hợp. | Timeout và cleanup pending correlation. |
| **Business deadline** | Thời hạn nghiệp vụ của request đã qua. | Không tạo side effect sau deadline nếu policy yêu cầu. |
| **Test harness timeout** | Bài test chờ quá lâu do deadlock/lỗi. | Fail test có thông tin chẩn đoán, không làm CI treo. |

**Phân biệt `defaultRequestTimeout` và `defaultReplyTimeout`** trong cấu hình gateway: mốc đầu gắn với việc gửi request, mốc sau gắn với việc đợi reply. Chi tiết xử lý từng timeout phụ thuộc loại channel, gateway proxy, return type và cấu hình phiên bản. Test nên assert **hợp đồng đã quy định**, không suy rằng mọi timeout luôn throw cùng một exception.

### 12.1. Kịch bản no-reply

~~~text
Given:
  gateway method cần OrderReply
  reply timeout cấu hình là một giá trị hữu hạn
  fake handler nhận request nhưng không gửi reply
When:
  caller gọi gateway
Then:
  request đã tới đúng boundary
  caller hoàn tất theo timeout/error contract đã xác định
  không đánh dấu đối tác đã xử lý thành công
  tài nguyên chờ reply/correlation được giải phóng
~~~

Trong một số cấu hình gateway, method có thể nhận `null` khi hết reply timeout; cấu hình khác có thể biến missing reply thành exception hoặc error result. Hãy **định nghĩa một chính sách ở lớp ứng dụng**, test theo chính sách đó và ghi nhận hành vi thư viện đang dùng.

### 12.2. Test timeout không dùng sleep làm tín hiệu chính

Nếu test cần chờ một reply bị thiếu, dùng **timeout đã cấu hình nhỏ nhưng hợp lý** và deadline bảo vệ test. Có thể dùng fake handler có latch để biết request đã được nhận trước khi bắt đầu đo reply timeout. Không viết `Thread.sleep(2_000)` rồi mặc định gateway đã timeout; sleep không chứng minh request thực sự tới boundary.

## 13. Ví dụ 3 — Test một PartnerGateway có outbound boundary thay được

Ví dụ trước dùng service activator xử lý hoàn toàn trong bộ nhớ. Bây giờ ta muốn kiểm tra một gateway **đi đến ranh giới gọi đối tác**, nhưng chưa gọi HTTP/JMS thật. Tạo một endpoint có ID cố định để `MockIntegrationContext` thay handler.

### 13.1. Interface proxy

~~~java
package example.gateway;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
        defaultRequestChannel = "partnerRequests",
        defaultReplyTimeout = 1_000)
public interface PartnerGateway {
    OrderReply submit(OrderRequest request);
}
~~~

### 13.2. Cấu hình flow dùng sentinel handler

~~~java
package example.gateway;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
@IntegrationComponentScan(basePackageClasses = PartnerGateway.class)
public class PartnerGatewayFlowTestConfig {

    @Bean
    DirectChannel partnerRequests() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow partnerFlow(DirectChannel partnerRequests) {
        MessageHandler sentinel = message -> {
            throw new IllegalStateException(
                    "Unexpected invocation of real partner boundary");
        };

        return IntegrationFlow.from(partnerRequests)
                .handle(sentinel,
                        endpoint -> endpoint.id("partnerBoundaryEndpoint"))
                .get();
    }
}
~~~

Trong test context này, **sentinel handler** đại diện cho boundary sẽ được thay. Với production, boundary có thể là `HttpRequestExecutingMessageHandler`, JMS/AMQP outbound gateway hoặc một handler tùy chỉnh. Cách thay cụ thể phải phù hợp loại endpoint đang dùng.

### 13.3. Test happy path với fake reply

~~~java
package example.gateway;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PartnerGatewayFlowTestConfig.class)
@SpringIntegrationTest
class PartnerGatewayReplyTest {

    @Autowired
    MockIntegrationContext mocks;

    @Autowired
    PartnerGateway gateway;

    @AfterEach
    void cleanup() {
        mocks.resetBeans();
    }

    @Test
    void gatewayReturnsReplyFromFakePartner() {
        MessageHandler fake = requestMessage -> {
            Object destination = requestMessage.getHeaders()
                    .get(MessageHeaders.REPLY_CHANNEL);
            assertInstanceOf(MessageChannel.class, destination);

            MessageChannel replyChannel =
                    (MessageChannel) destination;
            OrderRequest request =
                    (OrderRequest) requestMessage.getPayload();

            boolean delivered = replyChannel.send(
                    MessageBuilder.withPayload(new OrderReply(
                            request.orderId(), "PARTNER_CONFIRMED"))
                            .build());
            assertTrue(delivered);
        };

        mocks.substituteMessageHandlerFor(
                "partnerBoundaryEndpoint", fake);

        OrderReply reply = gateway.submit(
                new OrderRequest("PO-123", "VN"));

        assertNotNull(reply);
        assertEquals("PO-123", reply.orderId());
        assertEquals("PARTNER_CONFIRMED", reply.status());
    }
}
~~~

Mục tiêu của ví dụ là **mô phỏng reply tại boundary của một flow đồng bộ**. Nếu gateway trong ứng dụng dùng cơ chế reply phức tạp, payload conversion hoặc transport-specific reply destination, fake phải phù hợp hợp đồng đó. Test chỉ xác nhận proxy/flow có thể đưa request đến boundary và trả reply về caller; nó **không** kiểm tra request thực qua network.

### 13.4. Điểm yếu cần nhận biết của mẫu này

Flow test không có HTTP client, JMS session, serializer hoặc remote endpoint. Nếu đổi sentinel thành adapter thật và bài test vẫn mock handler, các vấn đề ở transport vẫn chưa được đo. Điều này **không làm test vô giá trị**; nó chỉ xác định giới hạn trách nhiệm của test.

## 14. Kiểm thử no-reply/timeout có thể tái hiện

Muốn test gateway không nhận response, điều quan trọng là xác định mock **đã nhận yêu cầu** rồi mới quan sát kết quả của caller.

### 14.1. Kịch bản được kiểm soát

~~~java
import java.util.concurrent.CountDownLatch;

CountDownLatch received = new CountDownLatch(1);
MessageHandler noReply = requestMessage -> {
    received.countDown();
    // Chủ động KHÔNG gửi reply để kiểm tra timeout.
};

mocks.substituteMessageHandlerFor(
        "partnerBoundaryEndpoint", noReply);
~~~

Với gateway có timeout 1 giây ở `defaultReplyTimeout`, test nên xác minh:

1. Boundary đã nhận request (latch/bộ đếm).
2. Caller không chờ vô hạn.
3. Kết quả là `null`, exception hoặc lỗi nghiệp vụ được ánh xạ đúng **theo hợp đồng đã chọn**, không mặc định một kết quả.
4. Không đánh dấu đối tác đã hoàn tất request.
5. Không còn pending request/correlation hoặc thread chờ vô hạn sau timeout.

**Lưu ý:** `CountDownLatch` chỉ giúp xác nhận boundary đã chạy, **không điều khiển thời gian trôi qua của chính gateway**. Nếu cần test quy tắc time business (ví dụ deadline của event), hãy tách thành unit test dùng `Clock`. Một số gateway nhận reply timeout bằng cấu hình riêng; kiểm tra mốc đo và hành vi thực trong phiên bản đang dùng.

### 14.2. Không đồng nhất timeout với chắc chắn thất bại ở đích

Nếu HTTP client timeout sau khi gửi POST, dịch vụ đối tác **có thể đã xử lý thành công** nhưng response bị mất. Tương tự, JMS/AMQP reply có thể bị trễ dù request đã được consume.

Do đó:

- **Gateway timeout** là kết quả của việc **caller chưa nhận được xác nhận đúng hạn**.
- **Business failure** là trạng thái có bằng chứng bên đích không thực hiện yêu cầu.
- **Unknown outcome** là trạng thái cần tra cứu/readback, đặc biệt với tác vụ không idempotent.

Không tự retry vô hạn một lệnh chuyển tiền, tạo hóa đơn hoặc cấp quyền nếu không có idempotency key và cơ chế xác minh trạng thái.

## 15. Error handling: lỗi kỹ thuật, lỗi nghiệp vụ và errorChannel

Lỗi có thể xuất hiện tại nhiều lớp:

| Lớp lỗi | Ví dụ | Cách test |
|---|---|---|
| **Validation/domain** | Thiếu `orderId` hoặc tenant | Unit + flow test, không gọi outbound boundary. |
| **Synchronous handler exception** | Service activator throw | Caller nhận exception hoặc kết quả mapping theo policy. |
| **Async handler failure** | Handler chạy trên executor rồi throw | Quan sát error channel/callback/future. |
| **HTTP transport** | 4xx/5xx, connect/read timeout | HTTP stub/test server. |
| **JMS/AMQP transport** | Broker unavailable, reply destination lỗi | Broker integration test. |
| **Serialization** | Không chuyển được response JSON/DTO | Contract + transport test. |
| **Protocol-level negative response** | HTTP 409, business reject code | Verify mapping không biến thành success. |
| **Late/misrouted reply** | Reply đến khi request không còn chờ | Không ghép nhầm request mới, có log/metric tương ứng. |

### 15.1. Không mặc định mọi exception đều qua errorChannel

Với `DirectChannel` và handler chạy đồng bộ, exception có thể propagate về caller. Với `ExecutorChannel` hoặc listener bất đồng bộ, lỗi có thể đi qua `ErrorMessage`/error handler nếu được cấu hình. Với outbound gateway, ngoại lệ từ client hoặc từ response error mapping có thể chuyển thành error message hoặc exception.

Test phải xác định **đường lỗi thật sự của flow**. Không viết assertion chỉ chờ `errorChannel` nếu cấu hình không publish lỗi vào đó, và cũng không kỳ vọng `assertThrows` trên thread người gọi khi lỗi xảy ra trong executor.

### 15.2. Kiểm tra nguyên nhân gốc thay vì chỉ lớp wrapper

Khi một handler throw `IllegalArgumentException`, Spring Messaging có thể bọc nguyên nhân trong exception liên quan tới xử lý message. Nên kiểm tra:

- Error type/cause đúng hoặc map thành application error code.
- `requestId`/`traceId` còn được ghi nhận ở error path.
- Không gửi response `ACCEPTED` sau khi handler thất bại.
- Error payload không lộ token, mật khẩu, stack trace không cần thiết hoặc dữ liệu khách hàng.

Nếu ứng dụng public API quy định trả mã `INVALID_REQUEST`, test **hợp đồng public** quan trọng hơn chi tiết wrapper nội bộ có thể thay đổi khi nâng cấp framework.

## 16. Test reply đến chậm hoặc đến sau timeout

Reply chậm tạo nhiều vấn đề hơn thiếu reply hoàn toàn:

1. Gateway timeout và caller đã xử lý lỗi, nhưng worker vẫn xử lý request.
2. Partner gửi reply A sau khi request A đã hết hạn.
3. Một request B mới có cùng business key hoặc correlation ID nếu hệ thống tái sử dụng sai khóa.
4. Reply cũ được consumer đọc và ghép nhầm vào request mới.

### 16.1. Kịch bản cần dựng

~~~mermaid
sequenceDiagram
    participant A as Caller A
    participant G as Gateway
    participant P as Partner
    A->>G: request A (correlation A)
    G->>P: request A
    Note over G: Reply timeout hết hạn
    G-->>A: Timeout / Unknown outcome
    P-->>G: Late reply A
    Note over G: Không ghép vào request B
~~~

### 16.2. Assertion có ý nghĩa

- Pending correlation A đã được giải phóng hoặc được quản lý theo retention policy.
- Late reply A được bỏ, ghi nhận hoặc chuyển vào hàng xử lý trễ theo thiết kế.
- Không có reply sai cho request B.
- Có bằng chứng theo `requestId` để đối soát trạng thái nếu request đã gây side effect.
- Retry có idempotency và giới hạn nếu caller tiếp tục sau timeout.

Không cần dựng một fake bằng `Thread.sleep` dài; có thể dùng latch/barrier để giữ reply ở partner rồi chủ động phát sau mốc timeout đã cấu hình, trong một integration test có deadline hữu hạn.

## 17. Kiểm thử nhiều request đồng thời

Nếu gateway nhận 100 request song song, một lỗi thường gặp là dùng **shared mutable state** để lưu “request gần nhất” hoặc “reply đang chờ”, dẫn đến caller A nhận response của caller B.

### 17.1. Kịch bản đảo thứ tự phản hồi

~~~text
Caller A gửi order PO-A
Caller B gửi order PO-B
Partner nhận cả hai
Partner trả PO-B trước
Partner trả PO-A sau

Expected:
  Caller A → reply orderId PO-A
  Caller B → reply orderId PO-B
~~~

Trong test:

1. Dùng hai request có `requestId`/`orderId` riêng.
2. Tạo hai task/future, dùng barrier cho biết cả hai request đã gửi.
3. Cho fake hoặc server test giữ reply A, phát reply B trước.
4. Xác nhận từng caller nhận reply đúng business key.
5. Kiểm tra không mất/nhân bản response, không còn pending request sau hoàn tất.
6. Đặt timeout và cleanup để test không treo khi có lỗi.

### 17.2. Tránh test concurrency giả

Nếu flow dùng `DirectChannel` và fake handler trả reply ngay, gọi hai lần trong cùng thread **không kiểm tra concurrency**. Cần đồng thời thật ở boundary đã kiểm soát hoặc dùng server/broker phản hồi out-of-order.

Với JMS/AMQP, correlation thường cần liên kết request ID, reply destination và message ID theo hợp đồng; với HTTP mỗi connection/request có ngữ nghĩa request/response riêng, nhưng application vẫn có thể mapping nhầm khi dùng shared state. **Cơ chế match reply phải được kiểm tra đúng transport.**

## 18. Request-reply trên HTTP outbound gateway

HTTP là trường hợp dễ hình dung: gateway gửi request tới server, đợi status, headers, body rồi ánh xạ thành reply.

~~~mermaid
sequenceDiagram
    participant Flow as Integration Flow
    participant GW as HTTP Outbound Gateway
    participant S as Partner HTTP Server
    Flow->>GW: Message<OrderRequest>
    GW->>S: HTTP POST /orders
    S-->>GW: HTTP status + JSON body
    GW-->>Flow: Message<OrderReply> hoặc lỗi
~~~

### 18.1. Ma trận HTTP contract

| Trường hợp | Server test trả | Điều cần kiểm tra |
|---|---|---|
| Thành công đồng bộ | 200 + JSON | Payload đúng, status/header mapping, reply về caller. |
| Tạo mới | 201 + body/location | Không nhầm với 200; schema phản hồi đúng. |
| Chấp nhận xử lý nền | 202 + tracking ID | Trạng thái `ACCEPTED`, không tự gán `COMPLETED`. |
| Dữ liệu sai | 400 + error JSON | Error mapping có cấu trúc, không retry không cần thiết. |
| Không được ủy quyền | 401/403 | Không log credential; đúng public error contract. |
| Xung đột | 409 | Có policy xử lý trùng và business key. |
| Rate limit | 429 + retry metadata | Backoff theo chính sách, không flood partner. |
| Lỗi server | 500/503 | Retry có giới hạn, circuit breaker/alert nếu được cấu hình. |
| Không nhận response | Read timeout | Kết quả unknown/timeout; tra cứu trước khi retry side effect. |
| HTTP response chậm | Delay có kiểm soát | Reply timeout, cleanup và late completion. |
| Schema sai | 200 nhưng JSON thiếu trường | Không coi transport 200 là business success. |

### 18.2. Chọn công cụ kiểm thử HTTP

- **Flow isolation:** mock outbound handler với fake reply, không mở socket.
- **Mock HTTP client/server:** dùng `MockRestServiceServer` khi client kiểu `RestTemplate` và cấu hình cho phép; với stack khác chọn công cụ phù hợp.
- **HTTP stub test server:** WireMock, MockWebServer hoặc server tạm thời có thể xác minh method, path, headers, JSON body, status và timeout ở HTTP boundary.
- **End-to-end:** với hệ thống đích sandbox thực, kiểm tra side effect và recovery, không chỉ status code.

**Không tự coi `MockRestServiceServer` là một server socket thật**. Nó kiểm tra tầng client được cấu hình; test TLS, proxy và connection pooling cần môi trường kết nối phù hợp.

### 18.3. HTTP inbound gateway

Với inbound HTTP gateway, **caller là HTTP client**, không phải Java method:

~~~text
Given: POST /orders với request JSON hợp lệ
When:  request đi vào Spring Integration HTTP inbound gateway
Then:  request được map thành message đúng channel
And:   flow tạo reply đúng type
And:   HTTP status/body/headers theo contract
And:   timeout/validation/error được map thành response nhất quán
~~~

Nếu dùng Spring MVC, có thể dùng `MockMvc` trong context phù hợp. Cần kiểm tra **HTTP status**, không chỉ payload của message. Nếu inbound adapter chạy trên stack khác, dùng client/test server tương ứng; không ép mọi gateway vào MockMvc.

## 19. JMS và AMQP request-reply

JMS/AMQP là môi trường nơi request và reply có thể đi qua **hai queue/destination** hoặc reply destination tạm thời. Đường phản hồi có thể đến muộn, bị redeliver hoặc không tới nếu broker không sẵn sàng.

### 19.1. Các yếu tố test

| Khía cạnh | JMS | AMQP (ví dụ RabbitMQ) |
|---|---|---|
| Request destination | JMS queue/topic theo cấu hình | Exchange/routing key/queue theo binding |
| Reply destination | `JMSReplyTo` hoặc quy ước request-reply | Reply-to/queue hoặc cơ chế direct reply-to tùy setup |
| Correlation | `JMSCorrelationID` / message ID theo contract | Correlation ID và reply-to theo convention |
| Reply timeout | Thời gian đợi reply trong gateway | Thời gian đợi reply theo template/gateway |
| Failure semantics | Session, transaction, acknowledge | Consumer ACK/NACK, requeue và publisher confirms |
| Duplicate handling | Provider redelivery/transaction | Requeue/redelivery/retry |

Không đồng nhất **ACK của broker** với **reply nghiệp vụ**. Broker ACK có thể chỉ xác nhận message được chấp nhận hoặc consume, còn partner có thể vẫn chưa tính toán xong response.

### 19.2. Broker integration test cần bao phủ

1. Request được publish tới destination đúng.
2. Worker nhận request và tạo reply với correlation đúng.
3. Gateway trả đúng reply dưới concurrency.
4. Worker không trả reply, caller timeout đúng.
5. Worker trả reply quá muộn, pending correlation được xử lý an toàn.
6. Broker mất kết nối trước/giữa request và reply, recovery đúng.
7. Reply payload sai schema, không bị coi là thành công.
8. Worker redelivery request, side effect nghiệp vụ idempotent.
9. Shutdown/restart khi đang có request chờ, không gây leak.
10. Reply đến từ sai tenant hoặc sai destination bị từ chối.

Test cần dùng broker thử nghiệm hoặc container tương thích để xác nhận **queue, reply-to, TTL, ack và redelivery**. Mockito mock một handler không thể chứng minh các semantics này.

### 19.3. Reply destination và bảo mật

Reply destination không nên được xây từ dữ liệu client chưa kiểm chứng khiến phản hồi chứa thông tin nhạy cảm đi sang queue/tenant của người khác. Kiểm thử tenant isolation, authorization và logging có redaction.

## 20. Kafka: request-reply là giao thức ứng dụng tự định nghĩa

Kafka thường dùng cho **event streaming**, không phải RPC ngắn hạn theo mặc định. Nếu tổ chức chọn request/reply qua Kafka, cần xác định:

- Request topic và reply topic; topic/key/partition phù hợp.
- `requestId`/`correlationId` ổn định.
- Consumer/group nào nhận reply và cách ghép vào pending request.
- Timeout và retention khi response đến trễ.
- Duplicate/redelivery và business idempotency.
- Serializer/schema version và phân quyền topic.
- Hành vi khi caller restart còn request pending.

### 20.1. Tại sao không nên mặc định Kafka reply giống HTTP?

HTTP response thường gắn với một request/connection; Kafka lưu record trong topic và consumer nhận độc lập theo partition/offset. Cần **cơ chế correlation ở tầng ứng dụng** nếu muốn trả lời chính xác từng caller.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant A as Gateway application
    participant R as Kafka request topic
    participant W as Worker
    participant P as Kafka reply topic
    C->>A: requestId=R-41
    A->>R: event R-41
    R->>W: event R-41
    W->>P: response correlation R-41
    P->>A: response R-41
    A-->>C: matched response
~~~

### 20.2. Test tối thiểu

1. Correlation A/B khi replies đến ngược thứ tự.
2. Không có reply trước timeout.
3. Reply đến sau timeout, không ghép nhầm request khác.
4. Consumer restart/rebalance và request pending.
5. Duplicate reply không trả hai lần cho một caller.
6. Offset commit/redelivery và consumer idempotency.
7. Schema không hợp lệ và reply từ sai tenant.

Không khẳng định end-to-end exactly-once chỉ vì Kafka hỗ trợ transaction ở một phần pipeline. Một worker ghi DB hoặc gọi HTTP bên ngoài Kafka vẫn cần idempotency, outbox/inbox hoặc readback theo thiết kế.

## 21. File, SFTP và JDBC: không phải mọi inbound đều có reply trực tiếp

File và SFTP inbound adapter thường **phát message theo poll**, không tồn tại một caller đang đợi reply giống HTTP. JDBC inbound cũng thường đọc hàng đến hạn rồi đưa vào flow.

| Nguồn | Mẫu thường gặp | Nên test |
|---|---|---|
| **File inbound** | Poll file rồi phát `Message<File>` | File readiness, filter, retry, metadata, không chờ reply từ file producer. |
| **SFTP inbound** | Đồng bộ remote file rồi phát message | Download, host key, duplicate, reconnect, không tự tạo reply RPC. |
| **JDBC polling inbound** | Query record pending rồi phát message | Due time, transaction, claim/lock, rollback. |
| **JDBC outbound gateway** | Request trả kết quả query/update từ database theo cấu hình | SQL, mapping, transaction và reply payload. |
| **File/SFTP outbound gateway đặc thù** | Một số flow trả metadata/result từ thao tác I/O | Kiểm tra gateway thật sự tạo reply nào; không giả định mọi adapter có kết quả. |

Nếu business workflow muốn gửi kết quả lại người đưa file, phải thiết kế **kênh phản hồi riêng** như file kết quả, API callback hoặc event; đó là một hợp đồng mới, không phải reply channel mặc định của file inbound.

## 22. Test nghiệp vụ có side effect và idempotency

Một request-reply không bảo đảm exactly-once side effect. Ví dụ:

~~~text
T0 caller gửi requestId=R-9 "tạo hóa đơn"
T1 worker ghi invoice vào database thành công
T2 reply bị mất trên mạng
T3 caller timeout và retry R-9
T4 worker nhận lại request R-9
~~~

Không có idempotency, invoice có thể bị tạo hai lần. Test gateway phải đi cùng bài kiểm thử business side effect:

| Scenario | Kết quả mong đợi |
|---|---|
| Request mới R-9 | Tạo đúng một invoice và trả ID. |
| Retry cùng R-9 sau timeout | Trả kết quả đã có hoặc trạng thái phù hợp; không tạo invoice khác. |
| Hai caller đồng thời cùng idempotency key | Một kết quả cuối phù hợp chính sách; không race duplicate. |
| Cùng key nhưng payload khác | Xử lý xung đột theo contract; không ghi đè lặng lẽ. |
| Reply được nhận nhưng caller crash trước ghi nhận | Khả năng tra cứu theo request ID và retry an toàn. |

### Mẫu request contract

~~~json
{
  "requestId": "req-invoice-009",
  "operation": "CREATE_INVOICE",
  "schemaVersion": 2,
  "tenantId": "VN",
  "invoiceSourceId": "order-2048",
  "requestedAt": "2026-11-23T09:20:00Z"
}
~~~

Không mặc định ID của message framework hoặc JMS/Kafka là idempotency key nghiệp vụ. Quy ước nghiệp vụ nên xác định rõ **scope tenant + operation + requestId** hoặc khóa tương đương để tránh trùng/collision.

## 23. Synchronous và asynchronous gateway

### 23.1. Gateway đồng bộ

Method `OrderReply submit(OrderRequest)` thường khiến caller chờ response hoặc timeout. Với flow `DirectChannel` và handler trả reply ngay, test có thể assert trực tiếp sau lời gọi.

### 23.2. Gateway bất đồng bộ

Tùy phiên bản và cách cấu hình, ứng dụng có thể dùng `Future`/`CompletableFuture`, reactive type hoặc pattern event-driven callback. Khi đó cần:

- Kiểm tra khi nào result/future hoàn tất, không chỉ lúc message được gửi.
- Xác định error/timeout propagation tới future/callback.
- Kiểm tra cancellation có hủy được xử lý hay chỉ hủy việc caller đợi.
- Tránh shared mutable state làm reply bị trộn giữa request.
- Bảo đảm executor và pending task được cleanup.

**Hủy một Future không đương nhiên undo side effect tại HTTP/DB/broker đích.** Nếu nghiệp vụ có quyền hủy thật, cần một cancellation protocol hoặc compensating action riêng, có test.

### 23.3. Dùng latch/barrier thay vì sleep

Một test out-of-order reply có thể dùng:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

CountDownLatch bothRequestsReceived = new CountDownLatch(2);
CountDownLatch allowReplyA = new CountDownLatch(1);

// Fake handler A:
//   bothRequestsReceived.countDown()
//   allowReplyA.await(timeout, TimeUnit.SECONDS)
//   send reply A
//
// Fake handler B:
//   bothRequestsReceived.countDown()
//   send reply B trước
//
// Test:
//   start caller A và B
//   assert bothRequestsReceived.await(...)
//   assert reply B về đúng caller B
//   allowReplyA.countDown()
//   assert reply A về đúng caller A
~~~

Đây là **kịch bản/pseudocode Java** cho fixture đồng thời, không phải chương trình đầy đủ. Cần triển khai fake thread-safe, timeout hữu hạn và cleanup trong `finally`/`@AfterEach`. Nếu flow vẫn đồng bộ trên một thread duy nhất, fake B có thể không chạy trong khi A đang giữ thread; phải bố trí executor hoặc song song caller phù hợp.

## 24. Định nghĩa điểm hoàn tất và cách đo thời gian

Gateway có nhiều mốc quan sát:

~~~mermaid
flowchart LR
    START["callerAt<br/>Caller bắt đầu"] --> SENT["sentAt<br/>Gửi request vào channel"]
    SENT --> OUT["outboundAt<br/>Gửi request đến transport"]
    OUT --> ACK["ackAt<br/>Transport phản hồi"]
    ACK --> REPLY["replyAt<br/>Gateway nhận reply"]
    REPLY --> DONE["businessVerifiedAt<br/>Kết quả đích xác minh"]
~~~

| Metric | Công thức gợi ý | Cần phân biệt |
|---|---|---|
| **Gateway response latency** | `replyAt − callerAt` | Thời gian caller nhận kết quả, không hẳn đã hoàn thành nghiệp vụ. |
| **Channel dispatch latency** | `sentAt − callerAt` | Có bị queue/backpressure trước handler không? |
| **Transport round-trip time** | Thời gian từ outbound send đến transport response | Không có nghĩa business result đã lưu xong. |
| **Gateway timeout rate** | Request hết thời hạn reply / request thuộc cohort | Có thể có outcome unknown ở đích. |
| **Late reply rate** | Reply đến sau khi pending request hết hạn / tổng reply quan sát | Cần xác định cách phát hiện và mẫu số. |
| **Correlation mismatch count** | Reply không ghép được với pending request hợp lệ | KRI về mất dữ liệu hoặc lộ response sai caller. |
| **Business confirmation latency** | `businessVerifiedAt − callerAt` | Cần bằng chứng side effect ở hệ thống đích. |
| **Pending request age** | Độ tuổi request chưa có kết luận | Quan trọng khi external partner tạm ngừng. |

**Đo đúng đồng hồ:** trong một tiến trình, `System.nanoTime()` phù hợp đo khoảng thời gian đã trôi; timestamp dùng trong log/tracing nên có UTC hoặc offset rõ ràng. Khi ghép thời gian từ nhiều máy cần xử lý clock skew, không khẳng định độ chính xác mili-giây nếu đồng hồ không được đồng bộ.

Với percentile (P50/P95/P99), đừng chỉ đo những request đã hoàn tất: phải hiển thị **pending count, overdue count, timeout count**. Nếu 5% request bị treo và loại khỏi phân phối, P99 của các request thành công có thể trông rất đẹp.

## 25. Đảm bảo reply hợp lệ, bảo mật và độc lập tenant

Gateway là ranh giới xử lý thông tin của người gọi. Các lỗi routing/serialization có thể làm phản hồi rơi vào tenant khác.

### Các trường hợp cần kiểm tra

| Nhóm rủi ro | Test phải chứng minh |
|---|---|
| **Tenant isolation** | Request tenant A không nhận response từ tenant B dù cùng `orderId`. |
| **Authorization** | Chỉ dữ liệu caller có quyền xem được đưa vào reply. |
| **Untrusted headers** | `role`, `tenantId` từ client không được xem là đã xác thực khi chưa kiểm tra. |
| **Response redaction** | HTTP/broker error không trả secret, bearer token hoặc thông tin hệ thống nhạy cảm. |
| **Replay attack** | Request ID/key lặp không làm side effect nhạy cảm bị tái thực thi ngoài policy. |
| **Payload validation** | Response không đúng schema/version bị từ chối hoặc quarantine. |
| **Message size** | Payload quá lớn bị xử lý theo giới hạn, không làm cạn bộ nhớ. |
| **TLS/certificate** | Transport thật xác thực server, không disable verification để test pass. |
| **Reply spoofing** | Worker/reply sender không có quyền không được mạo danh response. |
| **Correlation collision** | Cùng request ID ở hai tenant không bị ghép sai. |

Không nên log toàn bộ message khi timeout chỉ để dễ debug nếu payload chứa dữ liệu cá nhân, token hoặc credential. Dùng `requestId`, `traceId`, status, điểm thời gian và các trường đã được redaction.

### Error contract ra ngoài khác error nội bộ

Ví dụ handler nội bộ có thể throw `NullPointerException`; HTTP gateway không nên trả stack trace cho client. Hãy map thành mã lỗi không tiết lộ chi tiết, ghi log theo quyền phù hợp và giữ correlation để điều tra. Test phải assert **public response contract** cùng với **audit/tracing** bên trong.

## 26. MockIntegrationContext: quy tắc an toàn và giới hạn

Sử dụng `MockIntegrationContext` hiệu quả cần tuân thủ:

1. **Endpoint ID chính xác.** Tên `MessageChannel` hoặc `IntegrationFlow` không mặc nhiên là endpoint ID.
2. **Substitute trước khi flow chạy.** Nếu inbound poller/listener đang chạy, có thể phát side effect trước khi mock.
3. **Handler phù hợp semantics.** Một gateway cần reply, mock một chiều có thể gây timeout giả.
4. **Không mock quá sâu.** Giữ lại transformer, validator, router và correlation logic muốn kiểm tra.
5. **Không spy adapter có network side effect** nếu không chủ động chặn lời gọi thật.
6. **Reset sau test.** `resetBeans()` không thay thế cleanup của queue/executor/broker.
7. **Tránh context dùng chung chạy song song.** Hai test không nên đồng thời thay cùng endpoint trong một Spring context.
8. **Kiểm tra giới hạn bằng chứng.** Mock pass không chứng minh HTTP/TLS, JMS transaction hay Kafka offset.

### 26.1. Test inbound gateway không giống outbound gateway

Khi mô phỏng **HTTP inbound gateway**, HTTP request/response mapping và status cần được kiểm tra ở cổng HTTP. Thay một handler bên trong flow chỉ kiểm tra phần message processing; không tự chứng minh đường web endpoint nhận và trả response đúng.

Khi mô phỏng **outbound gateway**, fake phải đáp ứng reply semantics; nếu có transport-specific mapping thì cần contract test riêng.

### 26.2. Không để pending reply sang test sau

Trong `@AfterEach`:

- Chờ/cancel task theo test contract và bảo đảm in-flight work được quản lý.
- Stop endpoint/lifecycle do test khởi động nếu cần.
- `resetBeans()` cho endpoint đã substitute.
- Dọn message ở channel kiểm thử và state trong fake.
- Đóng client/server/broker container và tài nguyên được test sở hữu.

Một context cache có thể làm test sau nhìn thấy handler đã bị thay hoặc reply đến từ test trước. Nếu cleanup không thể thực hiện an toàn, xem xét xây context riêng hoặc `@DirtiesContext`, nhưng không dùng cách này để che lỗi thiết kế fixture.

## 27. Ma trận kiểm thử request-reply toàn diện

| # | Kịch bản | Tầng phù hợp | Bằng chứng pass |
|---:|---|---|---|
| 1 | Proxy `@MessagingGateway` được đăng ký | Flow | Autowire được interface và gọi method. |
| 2 | Request hợp lệ | Flow | Reply đúng kiểu và giá trị. |
| 3 | Request thiếu business key | Unit + flow | Reject trước khi gọi outbound. |
| 4 | Request thiếu tenant | Unit + flow | Không route tới tenant mặc định ngoài policy. |
| 5 | Header `traceId` | Flow | Có thể liên kết request và reply/audit. |
| 6 | Gateway method mapping | Flow | Request vào đúng channel, type conversion đúng. |
| 7 | GenericMessagingTemplate request-reply | Flow | Có reply qua channel; không cần proxy. |
| 8 | Handler trả `null` hoặc không reply | Flow | Hành vi timeout/no-result đúng contract. |
| 9 | Request send timeout | Channel/backpressure | Không gửi được trong ngưỡng, lỗi rõ ràng. |
| 10 | Reply receive timeout | Gateway + fake | Caller không chờ vô hạn. |
| 11 | Synchronous handler throw | Flow | Exception/error mapping phù hợp. |
| 12 | Async handler throw | Flow async | Lỗi ở error path/future, không false success. |
| 13 | Mock handler có reply | Isolation | Reply đến đúng gateway, không gọi network. |
| 14 | Mock handler không reply | Isolation | Timeout được kích hoạt có chủ đích. |
| 15 | Response DTO sai kiểu | Contract | Lỗi conversion rõ, không phát success sai. |
| 16 | Reply thiếu business field | Contract | Reject/map theo schema. |
| 17 | Reply đến trễ | Async/transport | Không ghép vào request khác. |
| 18 | Hai reply đảo thứ tự | Concurrency | Caller A/B nhận đúng dữ liệu tương ứng. |
| 19 | Duplicate reply | Broker integration | Caller nhận theo policy, không double completion. |
| 20 | Reply từ sai tenant | Security | Bị từ chối và audit đúng. |
| 21 | HTTP 200 với JSON hợp lệ | HTTP server test | Method/path/status/body/header đúng. |
| 22 | HTTP 202 Accepted | HTTP server test | Không báo business completed nếu chưa xác minh. |
| 23 | HTTP 400 validation error | HTTP contract | Error code/mapping rõ, không retry sai. |
| 24 | HTTP 401/403 | HTTP security | Không lộ credential, response phù hợp. |
| 25 | HTTP 429/503 | HTTP resilience | Backoff/retry/alert có giới hạn. |
| 26 | HTTP connect/read timeout | HTTP transport | Kết quả unknown xử lý an toàn. |
| 27 | JMS reply-to và correlation | JMS broker | Nhận đúng reply destination và request ID. |
| 28 | AMQP publisher confirm và reply | AMQP broker | Không nhầm confirm với business reply. |
| 29 | Kafka reply topic | Kafka broker | Consumer ghép đúng correlation; offset đúng. |
| 30 | Broker reply sau restart | Broker/recovery | Không gây memory leak hoặc response sai. |
| 31 | Duplicate request ID | DB/broker integration | Side effect idempotent. |
| 32 | Cùng ID khác payload | Domain + transport | Conflict theo chính sách, không ghi đè lặng lẽ. |
| 33 | Gateway bị cancel | Async | Trạng thái pending và side effect được giải thích. |
| 34 | Outbound handler backpressure | Async/transport | Không mất reply âm thầm, queue có giới hạn. |
| 35 | Schema version thay đổi | Contract | Version hỗ trợ/không hỗ trợ được xử lý rõ. |
| 36 | Lỗi serialization Unicode | Contract | Tiếng Việt/UTF-8 nguyên vẹn. |
| 37 | Teardown sau timeout | Lifecycle | Pending task/mock/queue không rò sang test sau. |
| 38 | Parallel tests | Fixture isolation | Không dùng chung request ID, port, broker queue. |
| 39 | Downstream đã ghi dữ liệu nhưng reply mất | End-to-end | Readback và retry không tạo duplicate. |
| 40 | Logging/metrics | Observability | Correlation có, secret không lọt log. |

Không cần chạy mọi ca trên mọi transport; chọn theo **risk, adapter thực tế, tính chất request/reply và khả năng lỗi**. Một ca chỉ mock handler sẽ không chứng minh broker transaction; một ca dùng server HTTP thật lại không chứng minh role/authorization khi test đã bypass policy.

## 28. Case study: gateway kiểm tra trạng thái đơn hàng với HTTP đối tác

### 28.1. Yêu cầu nghiệp vụ

Một ứng dụng nhận yêu cầu `lookup(orderId, tenantId)`, gọi API đối tác rồi trả trạng thái đơn hàng. Đối tác có thể trả `200`, `404`, `429`, `503` hoặc mất kết nối. Ứng dụng yêu cầu:

- Mỗi caller nhận dữ liệu **đúng order và tenant**.
- Phản hồi hợp lệ có DTO với `requestId`/`orderId`, trạng thái và thời điểm quan sát.
- Mất reply không được biến thành trạng thái `ORDER_NOT_FOUND`.
- Retry có giới hạn, tránh làm quá tải đối tác.
- Thông tin lỗi không tiết lộ API token.

~~~mermaid
flowchart LR
    CALLER["Caller"] --> GW["OrderStatusGateway"]
    GW --> VALID["Validate tenant / requestId"]
    VALID --> REQ["Build HTTP request"]
    REQ --> HTTP["HTTP outbound gateway"]
    HTTP --> MAP["Map partner response"]
    MAP --> GW
    HTTP --> ERR["Timeout / HTTP error mapping"]
    ERR --> GW
~~~

### 28.2. Lớp A — Unit test

Kiểm thử request validation, tenant authorization, mapping `PartnerStatusDto` thành `OrderStatusReply`, và rule phân biệt `NOT_FOUND` với `UNKNOWN_UPSTREAM`.

Đầu ra: DTO đúng, error code đúng, không cần Spring context hoặc HTTP.

### 28.3. Lớp B — Flow isolation

Đăng ký `@MessagingGateway` và request channel thật; thay HTTP outbound boundary bằng fake reply-capable handler.

Đầu ra: business headers còn tồn tại, request đã qua transformer/router, reply đúng Java method, không gọi mạng.

### 28.4. Lớp C — HTTP transport test

Dùng HTTP test server phát các response:

| Response | Mong đợi |
|---|---|
| 200 + JSON hợp lệ | Trả trạng thái đối tác và trace. |
| 404 + error body hợp lệ | Map thành `ORDER_NOT_FOUND` nếu hợp đồng cho phép. |
| 429 + Retry-After | Backoff theo policy, không retry vô hạn. |
| 503 | Lỗi tạm thời hoặc recovery path; không báo order absent. |
| Timeout sau khi server nhận request | Unknown outcome; kết luận phụ thuộc API operation. |
| 200 + JSON sai schema | Báo lỗi contract, không tạo reply giả. |

Đầu ra: xác minh method, URL, body, response mapping và lỗi ở tầng HTTP client.

### 28.5. Lớp D — Concurrency và E2E

Gửi đồng thời hai request có order khác nhau, làm server trả lời ngược thứ tự. Kiểm tra không trộn kết quả. Thử restart/gateway timeout và kiểm tra pending/metric. Nếu API chỉ tra cứu (read-only), retry thường có rủi ro side effect thấp hơn API tạo đối tượng; nhưng vẫn phải có giới hạn tải và xử lý response đúng.

### 28.6. Bằng chứng nghiệm thu

- Có test pass tại từng lớp và tên test phản ánh đúng phạm vi.
- Có dữ liệu nguồn/đích tách biệt theo tenant.
- Có `requestId`, `traceId` trong log/test evidence đã redaction.
- Có test lỗi/timeout/late reply/concurrency.
- Có mô tả rõ điều đã được chứng minh và điều chưa thể khẳng định.

## 29. Mẫu test plan có thể sử dụng lại

~~~yaml
# Mẫu kế hoạch kiểm thử, không phải cấu hình Spring Integration trực tiếp.
gatewayTestPlan:
  id: order-status-request-reply
  ownerTeam: integration-platform
  gateway:
    interface: OrderStatusGateway
    requestChannel: orderStatusRequests
    replyContract: OrderStatusReplyV2
    requestTimeoutPolicy: bounded
    replyTimeoutPolicy: bounded
  requiredContext:
    - requestId
    - orderId
    - tenantId
    - traceId
    - schemaVersion
  flowIsolation:
    mockBoundaryEndpointId: partnerHttpBoundary
    requireReplyCapableFake: true
    preserve:
      - validation
      - routing
      - responseMapping
  transportTests:
    server: isolated-http-stub
    scenarios:
      - success-200
      - not-found-404
      - too-many-requests-429
      - server-unavailable-503
      - timeout
      - schema-mismatch
  concurrency:
    distinctRequestIds: true
    reverseReplyOrder: true
    duplicateReply: true
    lateReplyAfterTimeout: true
  resilience:
    idempotencyRequiredForWrites: true
    retryPolicy: bounded-and-observable
    unknownOutcome: reconcile-before-unsafe-retry
  evidence:
    - gatewayRequest
    - outboundRequest
    - responseOrError
    - correlationTrace
    - targetStateWhenRequired
  cleanup:
    - reset-mock-endpoints
    - close-client-and-test-server
    - drain-test-channels
    - release-pending-tasks
~~~

**Không sao chép các key YAML trên vào application.yml và kỳ vọng Spring tự nhận.** Đây là cấu trúc lập kế hoạch kiểm thử minh họa; cấu hình chính thức phụ thuộc flow và adapter thực tế.

## 30. Tổ chức test suite và CI/CD

Đề xuất bố trí:

~~~text
src/test/java/...
  gateway/
    OrderGatewayFlowTest.java
    OrderGatewayValidationTest.java
    PartnerGatewayBoundaryTest.java
    GatewayTimeoutTest.java
    GatewayConcurrencyTest.java
  transport/
    HttpPartnerGatewayIntegrationTest.java
    JmsRequestReplyIntegrationTest.java
    AmqpRequestReplyIntegrationTest.java
    KafkaCorrelationIntegrationTest.java
  e2e/
    OrderStatusWorkflowTest.java
~~~

### Chạy và cô lập

1. **Unit/flow tests chạy thường xuyên** trong mọi pull request.
2. **HTTP/broker integration tests** chạy trên môi trường isolated hoặc ephemeral, có thể theo thay đổi adapter hoặc trước release.
3. **Concurrency/timeout tests** dùng latch, barrier, test server có điều khiển và bounded timeouts.
4. **End-to-end tests** chứng minh kết quả ở đích cho những workflow quan trọng.
5. Mỗi test dùng **requestId, tenant, queue/topic và dữ liệu riêng**, tránh trộn kết quả.
6. Test không chia sẻ Mockito mock/static pending map giữa các ca chạy parallel.
7. Sau mỗi test, stop endpoint do test sở hữu, reset substitutions và đóng tài nguyên.
8. Dùng test reports/log có correlation nhưng không chứa password, token hoặc dữ liệu riêng tư không cần thiết.

### Nhận diện lỗi hạ tầng

Nếu broker/server test không lên, đó có thể là **test infrastructure failure** chứ không phải logic gateway sai. Test report cần giúp phân biệt:

- context bean không khởi tạo được;
- request không tới channel;
- mock không phát reply;
- response map sai;
- timeout do logic;
- transport endpoint unavailable;
- target side effect sai.

Không tự đánh dấu test pass khi transport không khả dụng. Nếu suite được phép skip test do môi trường CI thiếu container, báo rõ **coverage gap**, không gọi mock-only suite là transport verified.

## 31. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ assert `send() == true` | Không biết caller có reply đúng không. | Gọi gateway và assert payload/error. |
| Dùng Mockito mock một chiều cho gateway | Gateway timeout dù flow trước boundary đúng. | Fake có reply theo contract. |
| Mock toàn bộ flow | Không phát hiện wiring/router sai. | Mock đúng external boundary. |
| Coi HTTP 202 là completed | Thực tế bên đích còn xử lý nền. | Theo tracking ID và xác nhận cuối. |
| Coi broker ACK là business reply | Không biết worker đã xử lý. | Reply message/correlation riêng. |
| Không kiểm tra correlation | Caller nhận nhầm reply khi concurrency. | Test phản hồi đảo thứ tự. |
| Test chỉ một request tuần tự | Bỏ sót shared mutable state. | Chạy nhiều caller có barrier/latch. |
| Không thử missing/late reply | Pending request bị treo/leak. | Test timeout và cleanup. |
| Sleep cứng 2 giây | Flaky trên CI, không chứng minh boundary. | Bounded wait và quan sát. |
| Retry write request sau timeout không kiểm tra | Side effect tạo trùng. | Idempotency key và readback. |
| Bắt tất cả exception rồi trả SUCCESS | Che lỗi mapping/transport. | Error contract rõ, không false success. |
| Ghép reply bằng thứ tự đến | Reply chậm/ngược thứ tự gây sai caller. | Correlation key phù hợp transport. |
| Dùng Spring message ID như business ID duy nhất | ID đổi sau transform/replay. | Business request ID ổn định. |
| Không tách send/reply timeout | Khó chẩn đoán backpressure vs downstream. | Metric theo từng mốc. |
| Bỏ qua tenant/security headers | Rò dữ liệu cross-tenant. | Validate nguồn tin cậy, test authorization. |
| Không reset `MockIntegrationContext` | Mock rò sang test sau. | `resetBeans()` và cleanup task. |
| Không test server/broker thật | Không phát hiện lỗi protocol/serialization. | Transport integration test. |

## 32. Bài tập thực hành

### Bài tập 1 — Gateway nội bộ bằng Java DSL

Tạo `@MessagingGateway` có method `OrderReply submit(OrderRequest)`, một `DirectChannel` và handler trả trạng thái.

Yêu cầu:

1. Tạo DTO request/reply rõ kiểu và business key.
2. Gọi gateway proxy từ JUnit, assert response.
3. Test request thiếu `orderId` và tenant.
4. Dùng `GenericMessagingTemplate` test riêng channel request/reply.
5. Nêu sự khác biệt về coverage giữa test proxy và test template.

### Bài tập 2 — Mock outbound boundary có reply

Tạo flow `PartnerGateway → transformer → outbound endpoint`.

Yêu cầu:

1. Gán endpoint ID tường minh.
2. Dùng `@SpringIntegrationTest` và `MockIntegrationContext`.
3. Thay outbound handler bằng fake tạo reply theo contract.
4. Assert body, trace ID, correlation và số lượt gọi.
5. Có test no-reply để quan sát timeout.
6. Gọi `resetBeans()` và dọn task/queue sau test.

### Bài tập 3 — Timeout và reply đến muộn

Tạo fake server/handler có thể giữ reply bằng latch.

Yêu cầu:

1. Định nghĩa request send timeout và reply timeout.
2. Làm request A hết hạn chờ rồi mới phát reply A.
3. Gửi request B trong lúc A đang chờ hoặc ngay sau timeout.
4. Xác minh B không nhận reply A.
5. Phân biệt **unknown business outcome** với **confirmed failure**.

### Bài tập 4 — HTTP outbound gateway

Dùng HTTP stub/test server với các ca 200, 202, 400, 404, 429, 503, timeout và JSON sai schema. Kiểm tra HTTP method, path, header, request body và response mapping; không đưa token vào log; chọn retry/backoff phù hợp cho từng loại lỗi.

### Bài tập 5 — Broker request/reply

Chọn JMS, AMQP hoặc Kafka:

1. Thiết kế request destination và reply destination/topic.
2. Xác định correlation key và semantics acknowledgment.
3. Chạy broker isolated và kiểm tra happy path.
4. Gửi hai request, trả reply đảo thứ tự.
5. Giả lập timeout, duplicate và worker restart.
6. Giải thích vì sao ACK/offset không chứng minh business completed.

### Bài tập 6 — Gateway với side effect

Thiết kế `CreateInvoiceGateway` gửi yêu cầu tạo hóa đơn. Worker ghi database rồi trả invoice ID.

1. Chọn khóa idempotency và phạm vi tenant.
2. Làm reply bị mất sau DB commit.
3. Retry cùng request ID và kiểm tra không tạo invoice mới.
4. Cho hai caller gửi cùng request ID đồng thời.
5. Đo pending/timeout, ghi nhận kết quả không xác định.
6. Nêu test nào chỉ dùng mock và test nào phải dùng database/broker thật.

### Bài tập 7 — Test plan và dashboard

Lập bảng tối thiểu 12 ca bao gồm happy path, validation, timeout, late reply, error mapping, concurrency, tenant isolation và recovery. Với mỗi ca, ghi **input, setup, endpoint, trigger, expected reply/error, timeout, evidence, cleanup và giới hạn coverage**. Đề xuất metric response latency, pending requests, timeout rate và correlation mismatch.

## 33. Checklist nghiệm thu

- [ ] **Gateway đã được phân loại đúng**: inbound, outbound hay Java messaging proxy.
- [ ] **Request/reply contract rõ ràng**: payload, type, headers, correlation, kết quả, timeout.
- [ ] **Có test gọi proxy thật `@MessagingGateway`** nếu production dùng proxy.
- [ ] **Có test channel/request-reply** để kiểm tra wiring độc lập khi cần.
- [ ] **Reply payload và type được assert**, không chỉ kiểm tra gửi request.
- [ ] **Header nghiệp vụ và bảo mật được xác minh**, không tin client-supplied role/tenant.
- [ ] **Fake outbound gateway có reply phù hợp**, không dùng mock một chiều cho happy path.
- [ ] **Reply missing, timeout và reply đến muộn** có kịch bản riêng.
- [ ] **Có test concurrency/out-of-order reply**, không ghép theo thứ tự đến.
- [ ] **Lỗi sync/async được quan sát đúng** qua exception, error path hoặc future.
- [ ] **Có retry/idempotency và reconciliation** khi side effect có thể hoàn tất trước khi mất reply.
- [ ] **HTTP/JMS/AMQP/Kafka được test theo semantics riêng**, không coi ACK là reply nghiệp vụ.
- [ ] **Test transport thật trên môi trường isolated** đối với giao thức trong scope.
- [ ] **Có timeouts hữu hạn, fixture cô lập, resetBeans và cleanup**.
- [ ] **Không lộ credential/PII trong logs hay test fixtures**.
- [ ] **Kết quả test có bằng chứng đúng ranh giới**, biết điểm nào chưa chứng minh.

## 34. Tổng kết

**Test gateway request-reply** trong Spring Integration không dừng ở việc gọi `send()` thành công. Một gateway đúng phải **nhận request, gửi tới handler/đích thích hợp, trả reply có kiểu và nội dung đúng, giữ correlation cho từng caller, xử lý timeout và lỗi theo hợp đồng, đồng thời tránh trộn response hoặc tạo side effect trùng khi retry**.

`@MessagingGateway` và Java DSL giúp viết **flow tests** nhanh ngay trong bộ nhớ; `GenericMessagingTemplate` kiểm tra trực tiếp message channel; `MockIntegrationContext` có thể thay outbound boundary bằng **fake có reply** để quan sát điều phối mà không gọi mạng. Tuy nhiên, **HTTP status/TLS, JMS/AMQP reply-to và acknowledgment, Kafka correlation/offset, transaction, timeout mạng và kết quả nghiệp vụ ở đích** vẫn phải được kiểm chứng qua test transport hoặc end-to-end khi phù hợp.

Một bộ test đáng tin cho gateway luôn trả lời được: **request nào đã đi đâu, reply nào thuộc caller nào, khi nào hết hạn chờ, lỗi xảy ra tại ranh giới nào, side effect nào đã được xác minh và phần kết quả nào vẫn chưa biết**. Đó là nền tảng để các adapter và gateway hoạt động có thể dự đoán, dễ chẩn đoán và an toàn khi kết nối hệ thống ngoài.



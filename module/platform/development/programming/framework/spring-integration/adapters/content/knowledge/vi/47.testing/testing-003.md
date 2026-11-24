# MockIntegrationContext: cô lập endpoint khi kiểm thử Spring Integration

Trong **Spring Integration**, một luồng nhận dữ liệu từ hệ thống ngoài thường đi qua `MessageChannel`, transformer, router, filter và một hoặc nhiều adapter/gateway. Thử nghiệm toàn bộ luồng với SFTP server, HTTP service, JMS/AMQP broker, Kafka hoặc database thật có thể chậm và khó chẩn đoán. Tuy nhiên, nếu chỉ kiểm thử các hàm Java thuần túy, ta lại chưa biết **các endpoint đã được Spring nối vào đúng channel hay chưa, message header có được giữ lại không và luồng có gửi tới đúng ranh giới hệ thống ngoài không**.

**`MockIntegrationContext`** là một tiện ích của **Spring Integration Test** cho phép thay tạm **message handler** hoặc **message source** trong endpoint của ứng dụng đã khởi tạo Spring context. Nhờ vậy, bài kiểm thử giữ được cấu trúc phần lớn integration flow nhưng có thể chủ động chặn side effect tại ranh giới hoặc giả lập dữ liệu đi vào luồng.

Bài học thuộc chương **Testing** của module `SPRING_INTEGRATION_ADAPTERS`, hướng tới việc kết nối hệ thống ngoài qua **inbound/outbound adapter, gateway, poller và MessageChannel**. Các ví dụ tập trung vào sử dụng `MockIntegrationContext` an toàn, cách kiểm tra hợp đồng message và lỗi, cũng như giới hạn của mock khi hệ thống có File, SFTP, HTTP, JMS, AMQP, Kafka hay JDBC.

> **Ý tưởng cần nhớ:** thay một handler bằng mock chứng minh message đã tới *điểm tích hợp được mô phỏng*, chứ không chứng minh hệ thống đích thực sự nhận, lưu hoặc xác nhận xử lý message. Muốn chứng minh side effect bên ngoài, cần bài kiểm thử adapter với transport phù hợp.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao `MockIntegrationContext` thích hợp cho **integration flow isolation test**, không phải công cụ giả lập toàn bộ server/broker.
2. Phân biệt **`MessageHandler`**, **`MessageSource`**, **`MessageChannel`** và **endpoint lifecycle**.
3. Khởi tạo test context bằng `@SpringIntegrationTest` và truy cập bean `MockIntegrationContext`.
4. Dùng `substituteMessageHandlerFor(endpointId, handler)` để thay tạm outbound hoặc service-activator handler.
5. Dùng `substituteMessageSourceFor(endpointId, source)` để điều khiển dữ liệu của inbound polling endpoint.
6. Quản lý `noAutoStartup`, `start()`, `stop()` và `resetBeans()` để các test không ảnh hưởng lẫn nhau.
7. Kiểm tra payload, header, routing, retry, lỗi đồng bộ/bất đồng bộ và số lần gọi bằng JUnit/Mockito hoặc message probe.
8. Nhận diện lỗi endpoint ID, thiếu reply, vòng lặp poller, shared state, mock sai ranh giới và các trường hợp phải dùng server/broker thật.

## 2. MockIntegrationContext đứng ở đâu trong kiến trúc test?

~~~mermaid
flowchart LR
    EXT["Nguồn ngoài<br/>SFTP / File / Kafka / HTTP"] --> IN["Inbound endpoint<br/>MessageSource hoặc handler"]
    IN --> C1["Input MessageChannel"]
    C1 --> LOGIC["Filter / Transform / Route / Service"]
    LOGIC --> C2["Output MessageChannel"]
    C2 --> OUT["Outbound endpoint<br/>MessageHandler"]
    OUT --> TARGET["Server / Broker / Database"]
    MOCK["MockIntegrationContext"] -. "Thay source" .-> IN
    MOCK -. "Thay handler" .-> OUT
~~~

Khi **mock inbound source**, bài test chủ động cấp message vào flow, thay vì tải file SFTP hoặc polling database thật. Khi **mock outbound handler**, bài test nhận/kiểm tra message gửi ra và không kết nối API/broker thật.

**Điểm quan trọng:** `MockIntegrationContext` không “xóa sạch” cấu hình Spring. Các channel, transformer, router và endpoint còn lại vẫn nằm trong application context. Vì vậy nó thích hợp để kiểm chứng **wiring của integration flow** trong phạm vi đã cô lập.

### 2.1. Phân biệt các đối tượng

| Đối tượng | Vai trò | Có thể thay bằng API nào? |
|---|---|---|
| `Message<?>` | Chứa payload và headers | Tạo message kiểm thử bằng `MessageBuilder`. |
| `MessageChannel` | Vận chuyển message tới subscriber hoặc queue | Không phải đối tượng `substituteMessageHandlerFor` trực tiếp. |
| `MessageHandler` | Nhận và xử lý một message | `substituteMessageHandlerFor(...)` tại endpoint tương thích. |
| `MessageSource<?>` | Cung cấp message khi được poll | `substituteMessageSourceFor(...)` cho inbound polling endpoint tương thích. |
| `EventDrivenConsumer` | Endpoint tiêu thụ message từ subscribable channel | Có thể là nơi gắn message handler được thay thế. |
| `PollingConsumer` | Endpoint poll một pollable channel rồi gọi handler | Có thể là nơi gắn message handler; cần xét poller lifecycle. |
| `SourcePollingChannelAdapter` | Endpoint poll message source rồi gửi vào channel | Có thể thay message source được cấu hình trong endpoint. |
| `IntegrationFlow` | Mô tả chuỗi endpoint và channel | Không thay toàn bộ flow chỉ bằng một lời gọi substitute. |

Ký hiệu `endpointId` là **ID của integration endpoint** mà Spring Integration đăng ký, không nhất thiết là tên channel, tên adapter factory hoặc tên biến Java. Đây là nguồn lỗi phổ biến nhất khi mới dùng `MockIntegrationContext`.

## 3. Lựa chọn đúng giữa unit test, flow test và transport test

| Loại test | Tạo Spring context? | Dùng MockIntegrationContext? | Điều được chứng minh |
|---|---|---|---|
| **Unit test** | Thường không | Không cần | Transformer, validator, router thuần Java đúng. |
| **Flow isolation test** | Có context nhỏ | Rất phù hợp | Channel wiring, message contract, nhánh routing, gửi đến endpoint. |
| **Mock outbound boundary** | Có | Có | Flow tạo message đúng trước khi gửi ra ngoài. |
| **Controlled inbound source** | Có | Có | Flow phản ứng đúng với message giả lập từ source. |
| **Transport integration test** | Có | Thường không mock chính transport cần test | HTTP request thật, SFTP transfer, broker commit/ack, JDBC transaction. |
| **End-to-end test** | Có | Tránh mock đường cần chứng minh | Hiệu ứng qua nhiều hệ thống và trạng thái cuối. |

Ví dụ: kiểm tra event `ORDER_CREATED` được biến thành JSON đúng với header `tenantId` và gửi tới outbound Kafka handler nên có **flow isolation test**. Nhưng kiểm tra Kafka topic, key, partition, serializer, acknowledgment và delivery thực sự phải có **Kafka integration test** trên broker thử nghiệm.

Không nên coi test cô lập là “test giả”. Nó kiểm chứng ranh giới có giá trị — **luồng tạo lệnh gì, tới đâu, với dữ liệu nào** — nhưng phải công bố chính xác phạm vi đã và chưa được kiểm thử.

## 4. Thư viện và dependency

`MockIntegrationContext` thuộc module `spring-integration-test`, package thường dùng:

~~~java
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
~~~

Các tiện ích test đi kèm thường được phối hợp với:

- **JUnit Jupiter**: `@Test`, `@BeforeEach`, `@AfterEach`, `@TempDir`, assertions.
- **Spring Test**: `@SpringJUnitConfig`, context caching và dependency injection cho test.
- **Mockito**: tạo `MessageHandler` giả, verify số lần gọi, lấy argument.
- **Spring Messaging**: `Message`, `MessageHandler`, `MessageBuilder`.
- **Spring Integration Core**: `DirectChannel`, `QueueChannel`, `IntegrationFlow` và poller.

### 4.1. Maven

Nếu dự án dùng Spring Boot dependency management/BOM phù hợp:

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

### 4.2. Gradle Kotlin DSL

~~~kotlin
dependencies {
    implementation("org.springframework.integration:spring-integration-core")
    testImplementation("org.springframework.integration:spring-integration-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Các ví dụ dependency giả định **BOM hoặc cơ chế quản lý phiên bản đã được cấu hình**. Nếu không có, dự án phải khai báo phiên bản tương thích với dòng Spring Framework/Spring Integration đang dùng. API và import có thể khác theo phiên bản; khi nâng cấp cần kiểm tra compatibility tại source của dự án.

**Không cần thêm `spring-integration-sftp`, `spring-integration-kafka` hay `spring-integration-jms` chỉ để dùng `MockIntegrationContext`**. Chỉ thêm module adapter mà flow thực tế sử dụng; test kết nối thật cần thêm công cụ server/broker phù hợp.

## 5. Khởi tạo MockIntegrationContext

Trong test có Spring context, dùng `@SpringIntegrationTest` để bật hỗ trợ riêng cho Spring Integration và inject bean `MockIntegrationContext`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(MyIntegrationConfig.class)
@SpringIntegrationTest
class MyIntegrationFlowTest {

    @Autowired
    MockIntegrationContext mockIntegrationContext;

    @Test
    void canUseMockIntegrationContext() {
        org.junit.jupiter.api.Assertions.assertNotNull(
                mockIntegrationContext);
    }
}
~~~

`@SpringIntegrationTest` không tự biến mọi external adapter thành mock. Chỉ khi test **chủ động substitute** tại endpoint phù hợp thì hành vi của handler/source mới được thay. Những endpoint khác vẫn có thể start hoặc gọi hệ thống ngoài theo cấu hình.

### 5.1. Lý do nên dùng context nhỏ

Một dự án production có thể khởi động hàng chục inbound polling adapter hoặc listener khi nạp toàn bộ application context. Đối với flow isolation test:

1. Chỉ import bean cần cho flow và các dependency của chúng.
2. Tránh tự động start endpoint có thể đọc dữ liệu/ghi tới bên ngoài.
3. Gán **endpoint ID rõ ràng** cho điểm cần substitute.
4. Chuẩn bị mock, input và output trước khi kích hoạt luồng.
5. Dọn trạng thái sau mỗi test.

Nếu test bắt buộc nạp toàn bộ app context, cần kiểm soát bằng test profile, cấu hình lifecycle, resource isolation và quyền truy cập để không kết nối nhầm production.

## 6. Hai API trung tâm

| API | Ý nghĩa | Tình huống |
|---|---|---|
| `substituteMessageHandlerFor(String endpointId, MessageHandler handler)` | Thay handler của một endpoint phù hợp bằng đối tượng test. | Chặn outbound HTTP/Kafka/SFTP hoặc kiểm tra message sau transformer. |
| `substituteMessageSourceFor(String endpointId, MessageSource<?> source)` | Thay message source mà một polling inbound endpoint dùng để lấy dữ liệu. | Thay nguồn đọc File/DB/SFTP bằng nguồn tạo dữ liệu xác định. |
| `resetBeans()` | Khôi phục các bean/endpoint được thay trong test context theo cơ chế của tiện ích. | Gọi trong teardown để tránh test kế tiếp sử dụng substitution cũ. |

**Không gán giả định rằng substitute luôn “thay mọi thứ cùng ID”.** Cơ chế này thao tác vào **endpoint cụ thể** với loại handler/source được framework hỗ trợ. Nếu chọn sai ID hoặc endpoint không hỗ trợ thay theo cách này, test phải fail rõ ràng; không nên bắt exception rồi tiếp tục coi flow đã được cô lập.

### 6.1. Về `MockIntegration`

Spring Integration Test còn có tiện ích `MockIntegration` để tạo mock/spy phục vụ message handler/source theo các khả năng mà phiên bản đang dùng cung cấp. Tuy nhiên **`MockIntegrationContext` không bắt buộc chỉ dùng mock do `MockIntegration` tạo**: đối tượng triển khai interface `MessageHandler` hoặc `MessageSource<?>` phù hợp cũng có thể dùng trong bài test.

Mockito thường đủ khi muốn verify số lần gọi và payload. Một handler tự viết phù hợp hơn khi muốn thu message vào hàng đợi test; một nguồn tự viết hữu ích khi muốn phát lần lượt một chuỗi message rồi trả `null`. Chọn cách rõ ràng nhất với điều kiện test.

## 7. Endpoint ID: điều kiện tiên quyết để substitute đúng

Giả sử một flow đi từ channel `ordersInput` đến outbound endpoint:

~~~java
@Bean
IntegrationFlow outboundFlow(DirectChannel ordersInput) {
    MessageHandler realHandler = message -> {
        throw new IllegalStateException(
                "Không được gọi outbound thật trong test");
    };

    return IntegrationFlow.from(ordersInput)
            .transform(String.class, String::trim)
            .handle(realHandler,
                    endpoint -> endpoint.id("orderOutboundEndpoint"))
            .get();
}
~~~

Trong đoạn trên, `orderOutboundEndpoint` là **endpoint ID** cho phép test chọn nơi thay handler; `ordersInput` là channel. Các DSL overload cho handler hoặc cách định danh component có thể thay đổi theo phiên bản; điều cần giữ là **đặt ID rõ ràng cho endpoint được phép thay**.

### 7.1. Bảng định danh dễ nhầm

| Tên | Đối tượng | Dùng khi nào? |
|---|---|---|
| `ordersInput` | `DirectChannel` bean | Gửi message vào flow. |
| `orderOutboundEndpoint` | Consumer endpoint ID | Truyền cho `substituteMessageHandlerFor`. |
| `orderOutboundHandler` | Tên bean handler nếu được đặt riêng | Dùng cho bean wiring/inspection, **không mặc nhiên là endpoint ID**. |
| `ordersOutput` | `QueueChannel` test | Nhận message để assertion. |
| `orderOutboundFlow` | Tên `IntegrationFlow` bean | Định danh flow, **không mặc nhiên là ID endpoint con**. |

Nếu một adapter được đăng ký qua annotation, XML hoặc Java DSL, quy tắc ID mặc định có thể khác nhau. Trong các test dùng substitution, nên **định nghĩa và kiểm tra ID rõ ràng** thay vì đoán một tên được framework tự sinh.

## 8. Ví dụ đầy đủ: mock outbound MessageHandler

Hãy xây dựng một flow nhận chuỗi mã đơn hàng, loại khoảng trắng thừa rồi chuyển tới outbound boundary. Test phải chứng minh đúng payload và header được gửi, nhưng tuyệt đối không thực thi side effect thật.

### 8.1. Cấu hình test flow

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
class OutboundTestConfig {

    @Bean
    DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderOutboundFlow(DirectChannel ordersInput) {
        MessageHandler externalBoundary = message -> {
            throw new IllegalStateException(
                    "Unexpected invocation of real outbound boundary");
        };

        return IntegrationFlow.from(ordersInput)
                .transform(String.class, String::trim)
                .handle(externalBoundary,
                        endpoint -> endpoint.id("orderOutboundEndpoint"))
                .get();
    }
}
~~~

Đây là **cấu hình flow thử nghiệm**: handler thật được thay bằng một sentinel sẽ throw nếu chạy. Trong ứng dụng thực, endpoint có thể bọc HTTP outbound adapter, Kafka sender, JMS sender hoặc một `MessageHandler` bên ngoài đã cấu hình.

### 8.2. Test với Mockito

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OutboundTestConfig.class)
@SpringIntegrationTest
class OutboundBoundaryTest {

    @Autowired
    MockIntegrationContext mockContext;

    @Autowired
    @Qualifier("ordersInput")
    DirectChannel input;

    @AfterEach
    void restoreEndpoints() {
        mockContext.resetBeans();
    }

    @Test
    void shouldDeliverTransformedMessageToBoundary() {
        MessageHandler outboundMock = mock(MessageHandler.class);
        mockContext.substituteMessageHandlerFor(
                "orderOutboundEndpoint", outboundMock);

        boolean accepted = input.send(
                MessageBuilder.withPayload("  PO-2048  ")
                        .setHeader("tenantId", "VN")
                        .setHeader("traceId", "test-trace-2048")
                        .build());

        assertTrue(accepted);
        verify(outboundMock, times(1)).handleMessage(
                argThat(message ->
                        "PO-2048".equals(message.getPayload())
                        && "VN".equals(
                                message.getHeaders().get("tenantId"))
                        && "test-trace-2048".equals(
                                message.getHeaders().get("traceId"))));
    }
}
~~~

### 8.3. Diễn giải kết quả

Test này xác nhận:

1. `ordersInput` được nối tới flow.
2. Transformer chuẩn hóa payload.
3. Header nghiệp vụ `tenantId` và `traceId` còn tồn tại ở boundary.
4. Outbound endpoint nhận **đúng một lời gọi** trong tình huống đơn giản.
5. Side effect của handler thật không được thực hiện trong phạm vi substitution.

Test **không** xác nhận:

- HTTP endpoint phía đối tác trả 200 hay 503;
- Broker JMS/AMQP/Kafka đã persist message hay commit offset;
- File/SFTP thật được tạo đúng bytes;
- Connection pool và TLS/host-key verification đúng;
- Transaction hoặc retry của connector production đã hoạt động.

Vì `DirectChannel` gửi đồng bộ khi subscriber được xử lý trên cùng thread, assertion bằng Mockito có thể kiểm tra ngay sau `send()` trong flow này. Nếu có executor/async boundary, cần đợi quan sát bằng timeout/latch thay vì verify tức thì.

## 9. Alternative: dùng handler tự viết để thu message

Không phải lúc nào cũng cần Mockito. Một handler đơn giản có thể giữ bản ghi để test kiểm tra:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

class RecordingMessageHandler implements MessageHandler {

    private final BlockingQueue<Message<?>> received =
            new LinkedBlockingQueue<>();

    @Override
    public void handleMessage(Message<?> message) {
        received.add(message);
    }

    Message<?> awaitMessage(long timeoutMillis)
            throws InterruptedException {
        return received.poll(timeoutMillis,
                java.util.concurrent.TimeUnit.MILLISECONDS);
    }
}
~~~

Trong test:

~~~java
RecordingMessageHandler recorder = new RecordingMessageHandler();
mockContext.substituteMessageHandlerFor(
        "orderOutboundEndpoint", recorder);

input.send(MessageBuilder.withPayload(" PO-99 ").build());
Message<?> observed = recorder.awaitMessage(1_000);
assertNotNull(observed);
assertEquals("PO-99", observed.getPayload());
~~~

Ưu điểm của `BlockingQueue` là có thể kiểm tra flow **bất đồng bộ** bằng bounded wait. Đừng dùng hàng đợi static dùng chung giữa test; test nên tạo recorder mới mỗi lần và xác minh không có message dư từ kịch bản trước.

### 9.1. Verify số lần gọi và duplicate

Muốn xác minh handler không nhận message thứ hai:

- Với flow đồng bộ, verify `times(1)` sau khi mọi thao tác đã hoàn tất là hợp lý.
- Với flow async, cần biết **điều kiện hoàn thành của cả luồng**; verify ngay có thể cho false pass.
- Trong poller, source có thể phát nhiều message nếu không trả `null` sau lần đầu.
- Nếu thiết kế chấp nhận at-least-once delivery, số lần nhận vật lý có thể nhiều hơn một; điều cần kiểm chứng là **side effect nghiệp vụ không bị lặp ngoài policy**, không phải luôn đòi đúng một delivery.

## 10. Kiểm thử trường hợp outbound không được gọi

`MockIntegrationContext` hữu ích cả với test âm tính. Giả sử một filter từ chối message thiếu `tenantId`, ta muốn chứng minh nó **không tới outbound boundary**.

~~~text
Given: message thiếu tenantId
When:  gửi vào input channel
Then:  filter reject hoặc route tới error path theo policy
And:   outbound mock không nhận message
And:   có bằng chứng xử lý lỗi nếu luồng yêu cầu
~~~

Không chỉ viết:

~~~java
// Không đủ nếu xử lý async vẫn còn đang chạy!
verify(outboundMock, times(0)).handleMessage(
        org.mockito.ArgumentMatchers.any());
~~~

Assertion “không nhận” đòi hỏi **mốc quan sát đủ chặt**. Với flow đồng bộ có filter, việc `send()` trả về/hoàn tất có thể là mốc phù hợp. Với flow async, cần đợi terminal signal, error event, event queue đã drain theo điều kiện kiểm thử hoặc một khoảng bounded observation được lý giải.

## 11. Substituting MessageSource cho inbound poller

`MessageSource<?>` đại diện **nguồn cấp message** cho polling adapter. `MockIntegrationContext.substituteMessageSourceFor(...)` đặc biệt hữu ích khi muốn giữ nguyên phần xử lý phía sau mà không thực sự đọc file hoặc truy vấn DB.

### 11.1. Một nguồn thử nghiệm có thể kiểm soát

~~~java
import java.util.ArrayDeque;
import java.util.Queue;
import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.Message;

final class QueueBackedMessageSource<T>
        implements MessageSource<T> {

    private final Queue<Message<T>> messages =
            new ArrayDeque<>();

    void add(Message<T> message) {
        messages.add(message);
    }

    @Override
    public Message<T> receive() {
        return messages.poll(); // null = tạm thời không có dữ liệu
    }
}
~~~

Trong test:

~~~java
QueueBackedMessageSource<String> source =
        new QueueBackedMessageSource<>();

source.add(MessageBuilder.withPayload("orders-001.csv")
        .setHeader("sourceSystem", "SFTP")
        .build());

mockContext.substituteMessageSourceFor(
        "filePollingEndpoint", source);
~~~

Ở đây `filePollingEndpoint` phải là ID của **inbound polling adapter** hỗ trợ thay source. Nếu endpoint đang mong đợi payload `File`, việc cung cấp `String` có thể làm transformer phía sau thất bại. **Mock phải tuân thủ hợp đồng payload/header của adapter thật**, hoặc test phải cố ý kiểm tra nhánh dữ liệu sai.

### 11.2. Vì sao source phải trả null khi hết dữ liệu?

Một fake source viết như sau sẽ phát **cùng một message mỗi lượt poll**:

~~~java
MessageSource<String> badSource = () ->
        MessageBuilder.withPayload("orders-001.csv").build();
~~~

Đây có thể là chủ đích nếu đang test **duplicate delivery**, nhưng thông thường nó gây message lặp vô hạn theo scheduler, khiến assertion về số lần xử lý trở nên flaky. Fake theo kịch bản nên phát lần lượt message rồi trả `null`.

### 11.3. Poller ID và control startup

Một cấu hình polling source có thể được mô tả bằng Java DSL:

~~~java
@Bean
IntegrationFlow controlledInboundFlow() {
    MessageSource<String> realSource = () -> null;

    return IntegrationFlow
            .from(realSource, endpoint -> endpoint
                    .id("filePollingEndpoint")
                    .poller(
                            org.springframework.integration.dsl.Pollers
                                    .fixedDelay(500)))
            .channel("fileInput")
            .get();
}
~~~

Ví dụ thể hiện **vị trí endpoint ID và poller** trong DSL. Dòng phiên bản Spring Integration có thể khác về overload hoặc kiểu builder; khi áp dụng, xác minh signature thực tế trong dự án. `fileInput` là channel cần được đăng ký hoặc tạo theo cấu hình flow.

Trong test, sử dụng:

~~~java
@SpringJUnitConfig(PollingTestConfig.class)
@SpringIntegrationTest(noAutoStartup = "filePollingEndpoint")
class SourceSubstitutionTest {
    // Chuẩn bị fake source và output trước.
    // Substitute đúng endpoint ID.
    // Chủ động start endpoint rồi chờ output.
}
~~~

`noAutoStartup` làm endpoint được chỉ định **không chạy tự động khi context khởi tạo**, tránh poll nguồn thật trước khi test kịp gắn fake. Đó là điều kiện quan trọng với File, SFTP, JDBC hoặc các source có side effect, watermark/filter state.

## 12. Thứ tự an toàn cho một test polling endpoint

~~~mermaid
flowchart TD
    A["Load test context<br/>poller không auto-start"] --> B["Chuẩn bị fixture / output channel"]
    B --> C["Tạo MessageSource hữu hạn"]
    C --> D["substituteMessageSourceFor(endpointId, source)"]
    D --> E["Start đúng endpoint"]
    E --> F["Đợi message hoặc error<br/>bounded timeout"]
    F --> G["Assert payload/header/correlation"]
    G --> H["Stop endpoint"]
    H --> I["resetBeans + cleanup"]
~~~

Một quy trình tốt:

1. Đặt endpoint vào `noAutoStartup` hoặc giữ nó stopped trước substitution.
2. Tạo dữ liệu test sạch; với filesystem/DB cần namespace riêng.
3. Tạo `MessageSource` phát hữu hạn và không chia sẻ state giữa test.
4. Gọi `substituteMessageSourceFor` với ID chính xác.
5. Start **bean endpoint đã đăng ký**, không start channel hoặc bean handler bằng suy đoán.
6. Nhận output trên `QueueChannel` hoặc điểm quan sát tương đương.
7. Assert dữ liệu và số lần xử lý kỳ vọng; ghi lỗi khi hết timeout.
8. Stop endpoint, xét race với một poll đang chạy.
9. Gọi `resetBeans()` và dọn dữ liệu/hạ tầng sau test.

### 12.1. Lấy endpoint lifecycle

Ví dụ minh họa cách quản lý vòng đời nếu endpoint bean được expose với ID:

~~~java
import org.springframework.context.SmartLifecycle;

@Autowired
org.springframework.context.ApplicationContext applicationContext;

void startPollingEndpoint() {
    SmartLifecycle endpoint = applicationContext.getBean(
            "filePollingEndpoint", SmartLifecycle.class);
    endpoint.start();
}

void stopPollingEndpoint() {
    SmartLifecycle endpoint = applicationContext.getBean(
            "filePollingEndpoint", SmartLifecycle.class);
    endpoint.stop();
}
~~~

Trong một số kiểu khai báo, tên endpoint thực tế hoặc bean được xuất ra có thể khác. Hãy xác minh **ID của endpoint được tạo** trong cấu hình/bean graph của phiên bản sử dụng, không giả định mọi bean có cùng tên với factory method.

### 12.2. Test poller không có message

Nếu fake source luôn trả `null`:

- Flow không nên phát business message.
- Không nên ghi nhận “đã xử lý thành công một file”.
- Lỗi không có dữ liệu thông thường không phải một exception.
- Endpoint vẫn có thể tiếp tục poll theo lịch cho đến khi stop.

Để chứng minh “không có message”, định nghĩa điều kiện kết thúc/quan sát rõ ràng; một `QueueChannel.receive(0) == null` ngay sau startup **không chứng minh** scheduler sẽ không phát message muộn hơn.

## 13. Kỹ thuật snapshot/restore và lý do phải resetBeans()

Một Spring Test `ApplicationContext` có thể được **cache và tái sử dụng** giữa nhiều test. Nếu một test thay handler rồi không reset, test sau có thể tiếp tục nhận mock đó thay vì adapter thật, gây **false pass** hoặc lỗi khó tái hiện.

### 13.1. Teardown đơn giản

~~~java
@AfterEach
void afterEach() {
    mockContext.resetBeans();
}
~~~

Đây là bước khôi phục substitution, **không phải công cụ dọn mọi loại state**. Nó không tự:

- xóa message còn trong `QueueChannel`;
- xóa file trên SFTP/file system;
- xóa record database, Kafka topic hoặc JMS queue;
- reset state trong transformer singleton của ứng dụng;
- stop một task executor bên ngoài;
- khôi phục mọi static variable;
- đảm bảo một thread async đã kết thúc.

Test nên tự quản lý state và lifecycle. Với poller, dừng endpoint **trước** khi reset nếu điều kiện test yêu cầu tránh nó gọi handler/source đang thay đổi. Với flow không đồng bộ, đợi in-flight work được xử lý hoặc cách ly context/fixture.

### 13.2. Không dùng chung mock qua các test

Không nên:

~~~java
static MessageHandler sharedHandler = mock(MessageHandler.class);
~~~

Nếu nhiều test chạy song song, verify trên mock dùng chung có thể trộn lời gọi. Hãy tạo mock/recorder mới cho từng test, hoặc dùng fixture cô lập và bảo đảm các test không cùng thay một endpoint trong context được chia sẻ.

### 13.3. Cần `@DirtiesContext` không?

`@DirtiesContext` đánh dấu Spring test context cần được xây dựng lại. Nó có thể hữu ích nếu test thay đổi trạng thái ứng dụng không thể khôi phục an toàn bằng reset/cleanup. Tuy nhiên tạo lại context có chi phí lớn hơn và **không nên dùng như cách che giấu việc quên `resetBeans()`**. Với substitution bình thường, ưu tiên reset và fixture sạch.

## 14. Khác biệt giữa handler mock, spy và fake

| Loại | Hành vi | Khi phù hợp |
|---|---|---|
| **Mock** | Không thực thi side effect thật; verify invocation | Cần xác minh flow gửi message và header. |
| **Spy** | Có thể gọi logic thật, chỉ can thiệp một phần | Muốn quan sát handler nội bộ không nguy hiểm; cẩn trọng side effect. |
| **Fake** | Triển khai đơn giản trong bộ nhớ | Thay MessageSource hoặc recorder với kịch bản xác định. |
| **Stub** | Trả dữ liệu/phản hồi cố định theo kịch bản | Request/reply test, lỗi giả lập, timeouts có điều khiển. |

**Đừng spy một outbound handler thật có network side effect** rồi ngạc nhiên khi test gửi email, publish Kafka hoặc upload SFTP. Với boundary nguy hiểm, dùng mock/fake thật sự cô lập; spy chỉ nên gọi delegate khi tác dụng đã được kiểm soát.

### 14.1. Giả lập exception

~~~java
MessageHandler failingHandler = message -> {
    throw new IllegalStateException("simulated outbound failure");
};

mockContext.substituteMessageHandlerFor(
        "orderOutboundEndpoint", failingHandler);
~~~

Nếu flow đồng bộ trên `DirectChannel`, exception có thể truyền về `send()` dưới dạng wrapper của Spring Messaging. Với poller, listener hoặc executor, lỗi có thể được chuyển sang error handling của endpoint. **Assertion phải dựa trên ngữ nghĩa cụ thể của flow**; không mặc định mọi exception sẽ đi qua một channel tên `errorChannel`.

## 15. Những trường hợp không nên thay handler tùy ý

### 15.1. Outbound gateway cần reply

Một **outbound gateway** nhận request và tạo reply. Nếu thay gateway handler bằng Mockito `MessageHandler` không phát reply, caller có thể **timeout** dù logic phía trước hoạt động đúng.

Khi kiểm thử request/reply:

1. Xác định handler gốc có nhiệm vụ tạo reply, nơi gửi reply và kiểu phản hồi.
2. Chọn fake phù hợp với request/reply semantics của endpoint.
3. Tạo reply có payload/header đúng hợp đồng hoặc dùng công cụ mock hỗ trợ reply của phiên bản đang dùng.
4. Test nhánh timeout và error một cách riêng biệt.
5. Không dùng mock một chiều để kết luận gateway request/reply hoạt động.

Ví dụ giả mã về ý định của fake:

~~~text
fakeGatewayHandler(request):
    assert request.payload and request.headers
    reply = buildReply(
        payload = {"status": "ACCEPTED"},
        correlation = request.correlation
    )
    sendReplyThroughConfiguredReplyMechanism(reply)
~~~

Mỗi endpoint/gateway có cơ chế reply riêng; code thật phải dùng API của handler/gateway được Spring Integration hỗ trợ. Không tự giả định `replyChannel` là chuỗi tên channel hoặc có thể tùy tiện cast để gửi.

### 15.2. Polling handler có transaction

Nếu một `PollingConsumer` dùng transaction và message handler thật cập nhật DB, thay handler bằng mock sẽ **không chứng minh transaction commit/rollback của nghiệp vụ thật**. Test đó chỉ kiểm tra message được lấy và chuyển tới handler boundary; cần integration test riêng để xác nhận transaction với database/broker.

### 15.3. Endpoint có connection lifecycle riêng

Không nên dùng substitution rồi khẳng định:

- SFTP session tự reconnect sau đứt kết nối;
- HTTP TLS handshake và certificate validation đúng;
- Kafka producer/consumer được cấu hình transaction/offset chuẩn;
- JMS session rollback/redelivery đúng;
- AMQP ack/nack và publisher confirm hoạt động;
- JDBC lock/row claim bảo vệ khỏi duplicate khi hai instance cùng poll.

Những hành vi này thuộc về **transport/endpoint thật**, phải có integration tests riêng.

## 16. Kiểm thử các MessageChannel liên quan

`MockIntegrationContext` thay handler/source tại endpoint; để kiểm tra đầu vào hoặc đầu ra còn dùng các channel thực:

### DirectChannel

- Gửi đồng bộ tới subscriber được chọn.
- Dễ verify mock sau `send()` trong flow thuần synchronous.
- Lỗi handler có thể được truyền về caller.
- Nếu nhiều subscriber, cần hiểu cơ chế dispatcher; không mặc định mỗi subscriber đều nhận bản sao.

### QueueChannel

- Chứa message để test chủ động gọi `receive(timeout)`.
- Hữu ích để quan sát output hoặc các nhánh error/test.
- Message có thể còn lại giữa test nếu dùng chung context và không drain.
- `receive(timeout)` trả `null` nếu không nhận message trong khoảng chờ.

### ExecutorChannel

- Có ranh giới bất đồng bộ; `send()` không chứng minh handler đã xong.
- Mockito verify phải phối hợp latch/await có timeout; test cần đảm bảo executor cleanup.
- Exception ở thread khác có thể không quay lại caller.

### PublishSubscribeChannel

- Có thể gửi message tới nhiều subscriber, tùy executor và cấu hình.
- Test cần verify mỗi nhánh dự kiến; không mặc định thứ tự nếu chạy bất đồng bộ.
- Khi một subscriber lỗi, semantics ảnh hưởng nhánh khác tùy dispatcher/error handling.

**Chọn channel cho production vì semantics nghiệp vụ**, không chỉ vì dễ test. Nếu test đổi `ExecutorChannel` thành `DirectChannel` để tránh concurrency, nó có thể mất khả năng phát hiện lỗi thật của hệ thống.

## 17. MockIntegrationContext với File, SFTP, HTTP, Kafka và database

### 17.1. Ma trận ranh giới phù hợp

| Adapter/nguồn | Có thể substitute để test gì? | Điều vẫn cần transport test |
|---|---|---|
| **File inbound** | Fake `MessageSource<File>` hoặc message theo contract để test xử lý file. | File filter, quyền đọc, atomic rename, restart metadata store. |
| **SFTP inbound polling** | Fake source để gửi `Message<File>` hoặc payload phù hợp vào flow. | Authentication, host key, remote directory, streaming/download, reconnect. |
| **SFTP outbound** | Mock handler để verify remote filename/path header và content. | Upload thực tế, partial file, permission, retry, session. |
| **HTTP outbound adapter** | Mock handler để verify URI/header/body mapping trước boundary. | HTTP status/error mapping, TLS, timeout, connection pooling. |
| **HTTP outbound gateway** | Fake reply-capable boundary phù hợp để test response flow. | Response thực từ server, redirect, 4xx/5xx, timeout, error body. |
| **JMS outbound** | Mock handler để kiểm tra payload/correlation trước khi gửi. | Broker destination, session transaction, redelivery. |
| **AMQP outbound** | Mock handler để kiểm tra exchange/routing/business headers. | Publisher confirms, returns, ack/nack, DLX. |
| **Kafka outbound** | Mock handler để verify topic/key/event payload. | Serializer, partition, broker durability, producer ACK. |
| **JDBC polling inbound** | Fake `MessageSource` thay hàng từ DB để test flow. | Query thực, transaction, lock, isolation và concurrency. |
| **JDBC outbound** | Mock handler để verify lệnh nghiệp vụ trước DB boundary. | SQL dialect, commit/rollback và affected rows. |

### 17.2. File/SFTP payload contract

Nếu adapter production phát `Message<File>`, fake cũng nên phát `File` từ thư mục tạm:

~~~java
@TempDir
java.nio.file.Path workDir;

void prepareSource(QueueBackedMessageSource<java.io.File> source)
        throws Exception {
    java.nio.file.Path csv =
            workDir.resolve("orders-001.csv");
    java.nio.file.Files.writeString(csv, "orderId,amount\nPO-1,100\n");

    source.add(MessageBuilder.withPayload(csv.toFile())
            .setHeader("file_name", "orders-001.csv")
            .build());
}
~~~

Header `file_name` trong ví dụ là **giá trị hợp đồng minh họa**, không có nghĩa mọi adapter dùng chính xác tên này. Với dự án thật, dùng các hằng header và mapping của module File/SFTP phù hợp phiên bản. Fake nên mô phỏng đúng kiểu payload và header mà flow production chờ đợi.

### 17.3. HTTP/SFTP/JMS/AMQP/Kafka outbound

Với outbound handler được thay, assert những phần **trước ranh giới**:

- `payload`, schema version, content type, event/business ID;
- route/destination/topic/routing key hoặc remote path nếu đã được tính từ flow;
- header bảo mật và tenant mapping từ nguồn đáng tin cậy;
- correlation/tracing để quan sát lỗi;
- số lượt xử lý theo semantics flow.

Với transport thật, bổ sung test xác nhận **remote file/HTTP request/broker message/database row** đã thực sự tồn tại hoặc được xử lý.

## 18. Kiểm thử router, filter và splitter với mock boundary

Một flow có thể chia message thành nhiều nhánh rồi gửi tới các endpoint khác nhau:

~~~mermaid
flowchart TD
    IN["InputChannel"] --> VALID["Validate payload"]
    VALID --> R{"Route by eventType"}
    R -- "ORDER_CREATED" --> C["createdEndpoint<br/>mock handler"]
    R -- "ORDER_CANCELLED" --> X["cancelledEndpoint<br/>mock handler"]
    R -- "UNKNOWN" --> ERR["error/unsupported event"]
~~~

Test mẫu:

1. Thay handler của cả hai endpoint bằng **hai mock riêng**.
2. Gửi `ORDER_CREATED`, verify chỉ created handler nhận message.
3. Gửi `ORDER_CANCELLED`, verify chỉ cancelled handler nhận message.
4. Gửi loại không hỗ trợ, verify error hoặc drop theo policy; không có outbound side effect.
5. Gửi message thiếu header hoặc header kiểu sai, verify cách flow xử lý.

Đối với **splitter/aggregator**:

- Gắn business `correlationId` nếu nghiệp vụ cần trace qua nhiều transport.
- Kiểm tra `sequenceSize`, `sequenceNumber` hoặc group hoàn tất theo hợp đồng.
- Không assume framework message ID luôn là business identity ổn định qua transformer.
- Khi một phần message bị mất, test timeout/release/expire của aggregator theo cấu hình.

`MockIntegrationContext` hữu ích ở các **đầu ra của các nhánh**; nó không tự thay routing/splitting logic. Logic vẫn thực thi trong Spring flow, cho phép test phát hiện wiring sai hoặc mất header.

## 19. Cách kiểm thử lỗi đồng bộ và bất đồng bộ

### 19.1. Lỗi handler đồng bộ

~~~java
MessageHandler failure = message -> {
    throw new IllegalStateException("simulated failure");
};

mockContext.substituteMessageHandlerFor(
        "orderOutboundEndpoint", failure);

// Khi flow chạy đồng bộ và không có error handler bắt lỗi:
org.junit.jupiter.api.Assertions.assertThrows(
        org.springframework.messaging.MessagingException.class,
        () -> input.send(
                MessageBuilder.withPayload("PO-1").build()));
~~~

Trong thực tế exception có thể là `MessageHandlingException`, `MessagingException` hoặc wrapper tùy handler và điểm phát lỗi. Test nên assertion theo **contract của flow thực tế**, không cứng nhắc nếu tầng framework thay cách wrap.

### 19.2. Lỗi từ poller hoặc async flow

Một inbound poller gọi source/handler trên scheduler thread; lỗi có thể đi tới error handler/error channel, được log hoặc kích hoạt retry. Test không nên đặt `assertThrows` quanh lời gọi `start()` rồi chờ bắt lỗi từ một poll xảy ra sau đó.

Thay vào đó:

1. Tạo fake source phát một message gây lỗi.
2. Thay outbound handler bằng handler throw exception.
3. Start poller.
4. Đợi **error event** hoặc trạng thái recovery được cấu hình.
5. Assert payload/correlation, số lần retry hoặc quyết định DLQ theo policy.
6. Stop endpoint và cleanup.

### 19.3. Khi không có errorChannel

Đừng giả định mọi flow Spring Integration tự động publish exception vào `errorChannel`. Semantics phụ thuộc điểm bắt lỗi, cấu hình endpoint, poller, executor, transaction và error handler. Khi không có error path phù hợp, exception có thể được đưa về caller hoặc logged tại scheduler. Test cần biết rõ **điểm quan sát lỗi đã được thiết kế**.

## 20. Idempotency và retry: mock ở đâu để không nhầm ngữ nghĩa?

Một outbound handler mock ghi nhận **số lời gọi của flow**, không xác nhận provider đã commit message. Với các môi trường có at-least-once delivery hoặc retry, cần tách:

| Cấp | Điều có thể test bằng mock | Điều cần test ở đích |
|---|---|---|
| **Flow invocation** | Handler nhận bao nhiêu message và business key nào. | Không có side effect trùng sau retry. |
| **Retry advice/logic** | Một handler giả lập fail rồi success, đếm attempt theo policy. | Transport có tự retry/requeue/commit đúng không. |
| **Business idempotency** | Bộ xử lý nghiệp vụ bỏ qua event ID đã được lưu trong fake store. | Đồng thời/transaction trên store thật không sinh duplicate. |
| **Transaction** | Handler được gọi trong kịch bản thành công/lỗi. | DB/broker rollback/commit đúng ở transaction boundary. |
| **Recovery** | Flow chuyển message tới nhánh lỗi mong muốn. | Message thực có trong DLQ hoặc dữ liệu đích đúng. |

### 20.1. Test handler fail một lần rồi thành công

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger attempts = new AtomicInteger();

MessageHandler flaky = message -> {
    if (attempts.incrementAndGet() == 1) {
        throw new IllegalStateException("transient failure");
    }
};

mockContext.substituteMessageHandlerFor(
        "orderOutboundEndpoint", flaky);
~~~

Việc thay handler như trên **chỉ tạo lỗi giả lập**. Để flow tự retry cần có advice/retry interceptor hoặc cơ chế retry được cấu hình trong endpoint. Nếu flow không có retry, lần gọi đầu sẽ thất bại và `attempts` có thể chỉ bằng 1. **Đừng kỳ vọng mock tự cung cấp retry.**

### 20.2. Business key khác framework message ID

Message headers có thể có `id` riêng do Spring tạo; qua transformer hoặc gateway, ID này có thể thay đổi. Chống trùng nghiệp vụ thường cần khóa ổn định, chẳng hạn:

~~~json
{
  "eventId": "evt-order-2048",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 2,
  "orderId": "PO-2048",
  "tenantId": "VN"
}
~~~

Mock có thể verify `eventId` không đổi tại outbound boundary; adapter test với broker/database mới chứng minh được idempotency **trong điều kiện redelivery, ACK bị mất hoặc hai consumer cùng xử lý**.

## 21. Sai lầm thường gặp khi dùng MockIntegrationContext

| Sai lầm | Biểu hiện | Cách xử lý |
|---|---|---|
| **Truyền tên channel thay endpoint ID** | Substitute không tìm thấy component hoặc tác động sai. | Đặt ID endpoint rõ ràng, kiểm tra bean graph. |
| **Quên `@SpringIntegrationTest`** | Không inject được `MockIntegrationContext` trong cấu hình test dự kiến. | Bật extension và dùng Spring Test context đúng. |
| **Poller chạy trước substitution** | File thật được đọc, message bất ngờ xuất hiện. | `noAutoStartup` và start có chủ đích. |
| **Không `resetBeans()`** | Test sau tiếp tục dùng mock cũ. | Reset trong teardown và kiểm soát in-flight work. |
| **Mock một chiều cho gateway cần reply** | Gateway timeout, test treo hoặc báo lỗi giả. | Dùng fake/reply handler phù hợp với request/reply. |
| **Fake source luôn phát message** | Duplicate vô hạn hoặc assertion flaky. | Phát hữu hạn rồi trả `null`, trừ test duplicate có chủ đích. |
| **Chỉ verify `send() == true`** | Không biết handler/target đã xử lý hay chưa. | Verify mock, output, error hoặc readback phù hợp. |
| **Dùng Mockito verify tức thì với async channel** | Lỗi race trên CI. | Đợi bounded event/latch/recording handler. |
| **Nhầm mock pass với kết nối production pass** | Thiếu test TLS, broker ack, transaction. | Bổ sung test adapter thật. |
| **Mock sai chỗ, bỏ qua logic cần kiểm tra** | Test pass vì transformer/router cũng bị thay. | Substitute tại ranh giới ngoài, giữ logic trong scope. |
| **Chạy test song song trên shared context** | Các test thay handler của nhau. | Cô lập context hoặc không parallel trên cùng endpoint. |
| **Kiểm tra thông tin nhạy cảm trong log** | Secret/test credential rò qua CI. | Redact, dùng fixture giả, phân quyền log. |
| **Không kiểm tra cleanup** | Poller/queue/topic/DB row còn sau test. | Stop, reset, xóa tài nguyên test theo ownership. |

## 22. Test matrix khuyến nghị cho MockIntegrationContext

| # | Kịch bản | Cách cô lập | Điểm xác nhận |
|---:|---|---|---|
| 1 | Payload hợp lệ | Mock outbound handler | Đúng payload/header, một lời gọi trong flow đồng bộ. |
| 2 | Header bắt buộc thiếu | Mock outbound handler | Không gọi outbound; nhánh reject/error đúng. |
| 3 | Router chọn đúng nhánh | Mock hai handler | Chỉ endpoint tương ứng nhận message. |
| 4 | Transformer thay đổi kiểu payload | Mock outbound handler | Kiểu dữ liệu, giá trị và header đúng. |
| 5 | Polling source không có dữ liệu | Fake source trả `null` | Không có business output. |
| 6 | Polling source một message | Fake source phát một lần | Một lần nhận hợp lệ, không lặp vô hạn. |
| 7 | Poller start/stop | `noAutoStartup` + controlled lifecycle | Không poll trước start và dừng poll mới sau stop. |
| 8 | Handler throw trong DirectChannel | Failing handler | Exception đúng theo error contract sync. |
| 9 | Handler throw trong poller | Failing handler + fake source | Error/retry path, không false success. |
| 10 | Retry fail rồi success | Handler có `AtomicInteger` | Số attempt và state theo advice thực sự cấu hình. |
| 11 | Duplicate event ID | Fake source phát trùng | Chính sách dedupe/idempotency phía business. |
| 12 | Gateway reply | Reply-capable fake | Reply mapping/correlation/timeout đúng. |
| 13 | Kafka/JMS boundary | Mock handler | Topic/destination, payload, headers đúng trước adapter. |
| 14 | SFTP/File boundary | Mock source/handler | File payload, remote path, metadata contract. |
| 15 | JDBC inbound logic | Fake source với DTO đúng | Mapping và xử lý row thành message đúng. |
| 16 | Target unavailable thật | Không mock transport | Thất bại/recovery/ACK theo server/broker thật. |
| 17 | Shared context qua hai test | Reset + fixture riêng | Test hai không nhận message/mock của test một. |
| 18 | Concurrent execution | Controlled executor/latch | Không trộn message, không shared mock state. |
| 19 | Header tenant giả mạo | Mock outbound boundary | Policy chặn trước side effect. |
| 20 | Adapter contract sau nâng cấp | Test với endpoint mới có ID ổn định | Mapping và substitution vẫn hoạt động hoặc fail rõ. |

Mỗi ca nên ghi **đầu vào, trạng thái initial, endpoint ID, expected event, timeout, cleanup và phạm vi bằng chứng**. Một test chỉ gọi substitute thành công mà không gửi message hoặc không assert output là chưa đủ.

## 23. Mẫu tổ chức test suite và lifecycle

Một cấu trúc dễ bảo trì:

~~~text
src/test/java/...
  flow/
    OrderTransformFlowTest.java
    OrderRoutingFlowTest.java
    OrderErrorFlowTest.java
  polling/
    FileSourceIsolationTest.java
    DatabasePollingFlowTest.java
  adapter/
    SftpTransferIntegrationTest.java
    HttpOutboundIntegrationTest.java
    KafkaOutboundIntegrationTest.java
  e2e/
    FileToKafkaWorkflowTest.java
~~~

Trong đó:

- **flow/**: chạy nhanh, không gọi hệ thống ngoài; dùng `MockIntegrationContext` và handler/source giả.
- **polling/**: quản lý lifecycle, fixture, metadata/filter và chỉ mock nguồn khi mục tiêu không phải kết nối thật.
- **adapter/**: dùng HTTP test server, SFTP server, broker hoặc DB thật/isolated để xác nhận giao thức.
- **e2e/**: thực thi đường đi từ nguồn tới kết quả cuối với bằng chứng.

### 23.1. Teardown gợi ý

~~~java
@AfterEach
void cleanup() {
    // Nếu có poller được start trong test, stop nó trước
    // và bảo đảm không còn công việc đang xử lý theo contract.
    mockContext.resetBeans();
    // Dọn QueueChannel, file, broker topic, database row, mock state
    // do chính test tạo ra.
}
~~~

Với endpoint lifecycle, đảm bảo thứ tự stop/reset phù hợp và cơ chế cleanup **luôn chạy ngay cả khi assertion thất bại**. Đừng dùng test chung địa chỉ production hoặc các topic/file không có namespace test.

## 24. Case study: File/SFTP inbound → validate → outbound Kafka

Giả sử một ứng dụng nhận file CSV đơn hàng từ SFTP, chuyển thành event rồi phát Kafka. Mục tiêu của test là xác nhận logic từ **message đã đọc thành công** tới **event sẵn sàng gửi**.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound polling source"] --> C["fileInput channel"]
    C --> V["Validate file<br/>tenant, format, size"]
    V --> T["Transform CSV → OrderEvent"]
    T --> O["Kafka outbound handler"]
    M["MockIntegrationContext"] -. "fake MessageSource" .-> SFTP
    M -. "mock MessageHandler" .-> O
    V --> ERR["error/invalid channel"]
~~~

### 24.1. Test flow không cần SFTP/Kafka thật

1. Tạo file CSV trong `@TempDir`.
2. Dùng `QueueBackedMessageSource<File>` phát `Message<File>` có metadata phù hợp.
3. Substitute nguồn tại `sftpInboundEndpoint` khi poller chưa start.
4. Substitute Kafka outbound handler tại `kafkaOutboundEndpoint`.
5. Start poller, đợi mock nhận `OrderEvent` bằng recorder/latch.
6. Assert `eventId`, `orderId`, `tenantId`, loại event và content.
7. Kiểm tra file sai schema đi tới error path, không tới Kafka boundary.
8. Stop poller, reset substitutions, dọn file và state.

**Điểm đã chứng minh:** validator/transformer/router và channel wiring tạo message đúng. **Chưa chứng minh:** SFTP có tải file thật, Kafka đã persist hoặc consumer downstream đã commit.

### 24.2. Test riêng với transport thật

| Transport test | Fixture | Bằng chứng pass |
|---|---|---|
| SFTP inbound | SFTP server thử nghiệm, host key/credential test, remote CSV | Đã download file đúng bytes, filter hoạt động, session đóng/mở đúng. |
| Kafka outbound | Broker thử nghiệm và topic riêng | Consumer test thấy event đúng key/topic/partition theo contract. |
| End-to-end | SFTP + Kafka + database downstream nếu cần | File nguồn tạo kết quả cuối, có retry/idempotency theo chính sách. |

Nếu một test case chỉ dùng mocks, không nên đặt tên `shouldPublishToRealKafka`. Tên phản ánh điều thật sự được chứng minh, ví dụ `shouldBuildKafkaOutboundMessage`.

### 24.3. Tình huống lỗi bắt buộc

- **SFTP source không có file:** poll không phát message.
- **Payload sai định dạng:** không publish, có reason/error phù hợp.
- **Cùng event ID được phát hai lần:** business layer xử lý theo chính sách dedupe.
- **Kafka boundary throw:** retry/error flow đúng, không tự gán thành công.
- **Poller chạy trước substitute:** phải bị ngăn bằng noAutoStartup và fixture isolation.
- **Context cache giữa hai test:** resetBeans bảo đảm không ảnh hưởng lẫn nhau.

## 25. Bài tập thực hành

### Bài tập 1 — Handler substitution

Tạo Spring Integration flow `inputChannel → trim String → outboundEndpoint`.

Yêu cầu:

1. Đặt endpoint ID `trimOutboundEndpoint`.
2. Inject `MockIntegrationContext` bằng `@SpringIntegrationTest` và `@SpringJUnitConfig`.
3. Thay handler bằng Mockito mock.
4. Gửi payload `"  invoice-001  "` với header `traceId`.
5. Assert payload đã chuẩn hóa, header được bảo toàn và mock nhận đúng số lần gọi.
6. Reset substitution sau test; giải thích tại sao test chưa chứng minh HTTP/Kafka side effect.

### Bài tập 2 — Controlled MessageSource

Tạo polling adapter phát message tới `QueueChannel`.

Yêu cầu:

1. Cấu hình endpoint ID và `noAutoStartup`.
2. Tạo `QueueBackedMessageSource<String>` chứa hai message, sau đó trả `null`.
3. Substitute source và chủ động start endpoint.
4. Assert đúng hai message theo contract, không có message dư.
5. Stop endpoint, `resetBeans()`, dọn queue và nguồn.
6. Thêm ca source rỗng và ca source throw exception.

### Bài tập 3 — Error behavior

Xây dựng flow có outbound handler được thay bằng handler fail một lần.

Yêu cầu:

1. Test khi **không có retry advice**: exception/error event tương ứng.
2. Thêm retry theo cấu hình dự án và test lại số attempt.
3. Kiểm tra correlation và side effect nghiệp vụ có bị lặp không.
4. Làm phiên bản async và đổi assertion từ `assertThrows` sang bounded observation.
5. Giải thích vì sao lỗi broker thật cần transport integration test.

### Bài tập 4 — Gateway request/reply

Tạo một HTTP hoặc messaging outbound gateway đơn giản.

Yêu cầu:

1. Ghi rõ request/reply contract và timeout.
2. Thiết kế fake handler **có reply**, không chỉ Mockito mock một chiều.
3. Gửi request, xác minh response và correlation.
4. Test nhánh không trả reply và nhánh trả lỗi.
5. Viết thêm integration test dùng server/broker thử nghiệm để xác nhận protocol.

### Bài tập 5 — Test plan đa adapter

Thiết kế bộ kiểm thử cho luồng **File/SFTP → transformer → Kafka/JMS → database**.

Với mỗi bài test, trình bày:

- Mục tiêu và boundary nào được mock.
- Endpoint ID của `MessageSource` hoặc `MessageHandler`.
- Dữ liệu mẫu, payload type, header và business ID.
- Điều kiện initial, cách start/stop poller và cleanup.
- Kết quả cần assert, timeout và bằng chứng pass/fail.
- Hành vi cần chứng minh thêm trên server/broker/database thật.

## 26. Checklist nghiệm thu

Một bài kiểm thử dựa trên `MockIntegrationContext` đạt chất lượng khi:

- [ ] **Đã chọn đúng tầng test:** flow isolation hay transport integration.
- [ ] **Có `@SpringIntegrationTest` và context cấu hình phù hợp**.
- [ ] **Endpoint ID được khai báo hoặc xác minh rõ**, không nhầm channel/flow/handler bean.
- [ ] **Mock đúng `MessageHandler` hoặc `MessageSource`** theo khả năng endpoint.
- [ ] **Thay tại ranh giới cần cô lập**, giữ transformer/router/filter thật trong phạm vi kiểm tra.
- [ ] **Assertion kiểm tra payload, header, correlation và số lần xử lý**.
- [ ] **Gateway request/reply được test với fake tạo reply phù hợp** khi cần.
- [ ] **Poller không chạy trước setup**, source hữu hạn và lifecycle được kiểm soát.
- [ ] **Đã xử lý sync/async bằng phương pháp quan sát thích hợp**.
- [ ] **Có kiểm thử negative path:** dữ liệu sai, filter, exception, retry và duplicate.
- [ ] **Đã gọi `resetBeans()` và dọn state**, không phụ thuộc thứ tự hoặc song song của test.
- [ ] **Không gửi side effect đến production** và không ghi secret/PII không cần thiết.
- [ ] **Không dùng mock làm bằng chứng giao thức thật**, có adapter tests bổ sung cho các transport trong scope.
- [ ] **Test có timeout hữu hạn và điểm quan sát tin cậy**, giảm flaky behavior trên CI.

## 27. Tổng kết

**`MockIntegrationContext` giải quyết bài toán cô lập các điểm tích hợp trong khi vẫn kiểm tra wiring và xử lý message của Spring Integration.** Bằng `substituteMessageHandlerFor`, ta có thể quan sát thông điệp chuẩn bị đi ra HTTP/SFTP/JMS/AMQP/Kafka/JDBC mà không tạo side effect. Bằng `substituteMessageSourceFor`, ta có thể điều khiển đầu vào của inbound polling adapter, kiểm tra parser, transformer, router và error flow không cần phụ thuộc file, SFTP hay database thật.

Hiệu quả của công cụ phụ thuộc vào **đúng endpoint ID, đúng kiểu handler/source, quản lý start/stop/noAutoStartup, assertion phù hợp với sync/async và cleanup qua `resetBeans()`**. Khi kết hợp test flow cô lập với những integration tests có server/broker thật và bằng chứng trạng thái cuối, đội phát triển có thể vừa giữ bộ test nhanh, đáng tin cậy, vừa tránh nhầm lẫn rằng “mock đã nhận message” đồng nghĩa “hệ thống ngoài đã xử lý thành công”.

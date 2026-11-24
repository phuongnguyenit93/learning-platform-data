# Spring Integration test utilities: kiểm thử adapter, gateway, channel và poller

Một luồng **Spring Integration** kết nối với file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu thường có vẻ đơn giản khi chạy thử bằng tay: nhận thông điệp, chuyển đổi payload, gửi qua `MessageChannel` rồi chuyển sang hệ thống ngoài. Nhưng khi có retry, timeout, phản hồi trễ, file được đọc hai lần hoặc broker khởi động chậm, kiểm thử thủ công khó trả lời được **lỗi nằm ở business logic, hợp đồng message, cấu hình Spring Integration hay hệ thống bên ngoài**.

Bài học **Spring Integration test utilities** thuộc chương **Testing** của module `SPRING_INTEGRATION_ADAPTERS`. Nội dung hướng dẫn kiểm thử luồng inbound/outbound adapter, gateway, poller và `MessageChannel`; phân biệt test thuần trong bộ nhớ với test tích hợp giao thức thật; kiểm tra hợp đồng message, lỗi, trạng thái kết nối và khả năng phục hồi của adapter.

**Nguyên tắc cốt lõi:** kiểm thử càng gần phần logic thì càng nên nhanh, quyết định được và không phụ thuộc mạng; càng gần ranh giới adapter thì càng phải kiểm tra đúng hành vi giao thức, vòng đời kết nối, xác nhận/acknowledgment và khôi phục sau lỗi. Không có một loại test duy nhất chứng minh được tất cả.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **unit test**, **Spring Integration flow test**, **adapter integration test**, **contract test** và **end-to-end test**.
2. Sử dụng thư viện `spring-integration-test`, `@SpringIntegrationTest`, `MockIntegrationContext` và các công cụ JUnit/Mockito để cô lập endpoint.
3. Thử một luồng `MessageChannel` bằng `DirectChannel`, `QueueChannel` và `MessageBuilder` mà không cần chạy broker.
4. Kiểm tra request/reply gateway, header, payload, transformation, routing, filtering, correlation và xử lý lỗi.
5. Thiết kế kiểm thử inbound/outbound adapter với **File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC** theo khả năng thực tế của từng transport.
6. Kiểm soát poller, thời gian, concurrency, thread, duplicate message, retry và idempotency để tránh flaky test.
7. Xác định những tình huống phải dùng hệ thống đích thật hoặc môi trường thử nghiệm gần thật, và những điều mock **không thể chứng minh**.
8. Xây dựng test matrix, bằng chứng kiểm thử và checklist CI cho adapter có khả năng bảo trì.

## 2. Bản đồ kiểm thử Spring Integration

Một flow có thể được mô tả như sau:

~~~mermaid
flowchart LR
    EXT["External system<br/>File / SFTP / HTTP / Broker / DB"] --> IN["Inbound adapter<br/>hoặc inbound gateway"]
    IN --> CH["MessageChannel"]
    CH --> LOGIC["Filter / Router / Transform<br/>Service activator"]
    LOGIC --> OUT["Outbound adapter<br/>hoặc outbound gateway"]
    OUT --> TARGET["External target"]
    LOGIC --> ERR["Error handling<br/>Error channel / recovery"]
~~~

Các thành phần trong sơ đồ có trách nhiệm khác nhau:

| Thành phần | Điều cần kiểm thử | Ví dụ |
|---|---|---|
| **Inbound adapter** | Khi nào nhận nguồn ngoài, tạo payload/header gì, có đọc trùng không? | File poller phát `Message<File>`. |
| **Inbound gateway** | Request vào được ánh xạ và response/HTTP status có đúng không? | HTTP endpoint trả dữ liệu sau xử lý. |
| **Channel** | Message được chuyển tới ai, sync/async, thứ tự, backpressure/queue ra sao? | `DirectChannel` so với `ExecutorChannel`. |
| **Transformer / filter / router** | Dữ liệu, header, nhánh điều kiện có đúng không? | Chỉ nhận file CSV và chuyển thành DTO. |
| **Outbound adapter** | Lệnh gửi một chiều đến hệ thống đích đúng không? | Ghi file hoặc gửi JMS event. |
| **Outbound gateway** | Có chờ và xử lý reply/timeout đúng không? | Gọi HTTP API rồi chuyển response. |
| **Poller** | Chu kỳ, thời điểm kích hoạt, max messages, stop/start và lỗi poll? | Đọc DB theo lịch. |
| **Error handling** | Exception được throw, publish, retry, đưa vào DLQ hoặc ghi nhận ở đâu? | Broker tạm thời không khả dụng. |

**Adapter khác gateway:** adapter thường là kết nối một chiều giữa message flow và hệ thống ngoài; gateway có ngữ nghĩa request/reply. Kiểm thử outbound adapter không nên mặc định đợi reply nghiệp vụ nếu endpoint không tạo reply.

## 3. Chọn tầng kiểm thử phù hợp

| Tầng kiểm thử | Có khởi động Spring context? | Phụ thuộc hệ thống ngoài? | Mục đích |
|---|---|---|---|
| **Unit test** | Không | Không | Kiểm tra hàm chuyển đổi, validator, router thuần Java. |
| **Flow test trong bộ nhớ** | Thường có context nhỏ | Không | Kiểm tra wiring channel, headers, payload, route, handler. |
| **Endpoint isolation test** | Có | Không hoặc được mock | Thay adapter/handler bằng mock, kiểm tra điều phối. |
| **Adapter integration test** | Có | Có: server/broker/DB thử nghiệm | Kiểm tra protocol mapping, transaction, ack, retry và network. |
| **Contract test** | Tùy mô hình | Stub hoặc đích tương thích | Kiểm tra schema, header, phiên bản API, quy ước lỗi. |
| **End-to-end test** | Có | Có nhiều đích | Chứng minh đường đi từ đầu đến cuối, recovery và trạng thái thực tế. |

### Quy tắc phân bổ

- Logic chuyển đổi JSON, đặt correlation ID hoặc quyết định route nên có **unit test nhanh**.
- Cấu hình message flow nên có **test với Spring context tối thiểu**.
- Lỗi handshake SFTP, confirm AMQP, Kafka offset/commit hay transaction JDBC cần **test với transport gần thật**.
- Một end-to-end test thành công không thay thế những test âm tính cho header thiếu, timeout, duplicate và dữ liệu sai.

~~~mermaid
flowchart TD
    U["Nhiều unit tests<br/>Không broker / không mạng"] --> F["Flow tests<br/>Channels + mock endpoints"]
    F --> A["Adapter integration tests<br/>Server/broker/DB tạm thời"]
    A --> E["Ít end-to-end tests<br/>Nhiều ranh giới thật"]
~~~

## 4. Các tiện ích kiểm thử chính

Spring Integration cung cấp module kiểm thử riêng, kết hợp với thư viện Spring Test, JUnit Jupiter và Mockito:

| Tiện ích | Vai trò |
|---|---|
| `spring-integration-test` | Các tiện ích và tích hợp kiểm thử riêng của Spring Integration. |
| `@SpringIntegrationTest` | Bật hỗ trợ kiểm thử Spring Integration trong Spring test context; có thể chỉ định endpoint không tự khởi động. |
| `MockIntegrationContext` | Thay tạm handler hoặc message source của endpoint bằng đối tượng kiểm thử. |
| `MockIntegration` | Factory/helper tạo một số mock/spy hướng tới endpoint Integration. |
| `TestUtils` | Truy cập thuộc tính nội bộ của bean phục vụ chẩn đoán/config test khi thật sự cần. |
| `MessageBuilder` | Tạo `Message<?>` với payload và header để gửi thử. |
| `DirectChannel` | Kênh gửi đồng bộ, giúp test logic có tính quyết định cao. |
| `QueueChannel` | Kênh pollable để đọc output bằng timeout trong test. |
| `@SpringJUnitConfig` | Khởi tạo context bằng Spring Test trên JUnit Jupiter. |
| **Mockito** | Tạo mock/spy và kiểm tra handler nhận message nào. |
| **JUnit Jupiter** | Assertions, setup/teardown, `@TempDir`, parameterized tests. |

**Phân biệt nguồn gốc công cụ:** `QueueChannel`, `DirectChannel`, `MessageBuilder` và `IntegrationFlow` thuộc Spring Integration/Spring Messaging; JUnit và Mockito là thư viện test bên ngoài. `MockIntegrationContext` và `@SpringIntegrationTest` thuộc bộ test utilities của Spring Integration. Không nên gọi mọi thứ là API của `spring-integration-test`.

## 5. Cấu hình dependency cho dự án

Ví dụ Maven khi dự án dùng Spring Boot và BOM/dependency management tương thích:

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

Ví dụ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.integration:spring-integration-core")
    testImplementation("org.springframework.integration:spring-integration-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Trong ví dụ này giả định **dự án có plugin/dependency management của Spring Boot** để quản lý các phiên bản tương thích. Nếu không dùng BOM, phải khai báo phiên bản phù hợp cho Spring Framework, Spring Integration, JUnit và Mockito theo build thực tế.

Những adapter cụ thể cần module phù hợp, ví dụ `spring-integration-file`, `spring-integration-sftp`, `spring-integration-http`, `spring-integration-jms`, `spring-integration-amqp`, `spring-integration-kafka` hoặc `spring-integration-jdbc`. Chỉ thêm module được dùng; **cài test utilities không tự tạo server SFTP, broker hay database**.

**Lưu ý tương thích:** tên package, API DSL hoặc cấu hình khởi tạo có thể khác giữa các dòng phiên bản. Các ví dụ dưới đây nhắm mô hình Java DSL/Spring Test phổ biến; khi đưa vào dự án thật, đối chiếu API của phiên bản đang dùng. Không sao chép version ngẫu nhiên từ một snippet vào dự án đã quản lý dependencies bằng BOM.

## 6. Ví dụ đầu tiên: kiểm thử flow chỉ dùng channel trong bộ nhớ

Hãy kiểm thử flow nhận chuỗi đơn hàng, chuẩn hóa khoảng trắng và chuyển tới channel kết quả. Không cần Kafka, JMS hay HTTP.

### 6.1. Cấu hình flow

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class NormalizationTestConfig {

    @Bean
    DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel ordersOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow normalizeOrders(DirectChannel ordersInput,
                                    QueueChannel ordersOutput) {
        return IntegrationFlow.from(ordersInput)
                .transform(String.class, String::trim)
                .channel(ordersOutput)
                .get();
    }
}
~~~

`DirectChannel` gọi handler đồng bộ trên thread người gửi. `QueueChannel` giữ output để test chủ động nhận với timeout; đây là mẫu phổ biến để kiểm tra payload và header mà không dựa vào `Thread.sleep`.

### 6.2. Test với JUnit Jupiter

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(NormalizationTestConfig.class)
class NormalizationFlowTest {

    @Autowired
    @Qualifier("ordersInput")
    DirectChannel input;

    @Autowired
    @Qualifier("ordersOutput")
    QueueChannel output;

    @Test
    void shouldNormalizePayloadAndPreserveBusinessHeader() {
        Message<String> request = MessageBuilder.withPayload("  PO-42  ")
                .setHeader("traceId", "trace-test-42")
                .build();

        assertTrue(input.send(request));

        Message<?> result = output.receive(1_000);
        assertNotNull(result, "Flow phải phát một thông điệp");
        assertEquals("PO-42", result.getPayload());
        assertEquals("trace-test-42",
                result.getHeaders().get("traceId"));
    }
}
~~~

**Điều test này chứng minh:** bean wiring hoạt động; chuỗi được `trim`; header nghiệp vụ đã đi qua; một message đi tới output. **Điều chưa chứng minh:** outbound HTTP/JMS/SFTP sẽ thành công, target đã lưu dữ liệu hay retry trong trường hợp lỗi mạng.

Lưu ý `id` và `timestamp` thuộc message framework có thể được tạo mới khi biến đổi message. Không nên viết assertion dựa trên việc message ID phải giống nhau giữa mọi handler, trừ khi đó là hợp đồng cụ thể cần được duy trì.

## 7. Kiểm thử message contract: payload, header và routing

Message trong Spring Integration chứa **payload** và **headers**; nội dung header có thể ảnh hưởng nghiêm trọng tới request/reply hoặc định tuyến:

| Thành phần | Ví dụ cần test | Lỗi thường gặp |
|---|---|---|
| **Payload type** | `String`, `byte[]`, `File`, DTO hoặc domain event | Adapter trả `File` nhưng transformer lại ép `String`. |
| **Business headers** | `tenantId`, `traceId`, `schemaVersion` | Mất header khi chuyển đổi hoặc map sang transport. |
| **Correlation** | `correlationId`, `sequenceNumber`, `sequenceSize` | Aggregator không ghép được các message cùng nhóm. |
| **Reply metadata** | `replyChannel`, timeout, response type | Gateway không nhận reply hoặc nhận sai channel. |
| **Error metadata** | `errorChannel` hoặc cấu hình xử lý lỗi | Exception không tới đường mà test kỳ vọng. |
| **Transport headers** | HTTP status/content type; JMS correlation; Kafka topic/key | Map nhầm header hoặc trông đợi mọi transport giống nhau. |
| **Security context** | Tenant, principal, resource scope | Tin header do client tự cung cấp mà không xác minh. |

### Ví dụ kiểm thử routing

Một router chọn channel theo `eventType`:

~~~java
IntegrationFlow routingFlow(MessageChannel input) {
    return IntegrationFlow.from(input)
            .route(
                org.springframework.messaging.Message.class,
                message -> message.getHeaders().get("eventType"),
                mapping -> mapping
                    .channelMapping("CREATED", "createdChannel")
                    .channelMapping("CANCELLED", "cancelledChannel")
            )
            .get();
}
~~~

Đoạn trên minh họa **ý tưởng route theo header**; cấu hình `createdChannel` và `cancelledChannel` phải tồn tại trong context, và kiểu generic/overload DSL cần phù hợp phiên bản. Test tương ứng nên gửi hai message có header khác nhau rồi xác minh **đúng channel nhận**, **channel còn lại không nhận**, và **trường hợp eventType không hợp lệ** được xử lý theo chính sách (reject, default route hoặc error flow), không âm thầm biến mất.

### Một test contract tốt nên hỏi

1. Payload hợp lệ có đúng **kiểu và nội dung**?
2. Header nghiệp vụ bắt buộc có được bảo toàn?
3. Header được tạo ở đâu, lấy từ nguồn nào, có thể bị giả mạo không?
4. Message không hợp lệ được từ chối, đưa tới error channel hay DLQ?
5. Có gì thay đổi khi message đến từ transport khác với producer nội bộ?

## 8. Cô lập endpoint bằng @SpringIntegrationTest và MockIntegrationContext

Khi muốn kiểm tra phần giữa của flow nhưng không muốn gửi ra hệ thống thật, có thể **thay handler của endpoint** ở Spring Integration test context.

### 8.1. Ý nghĩa của các API

- `@SpringIntegrationTest` hỗ trợ setup test context riêng cho Spring Integration.
- `MockIntegrationContext` cho phép thay **message handler** hoặc **message source** gắn với endpoint phù hợp để tránh gọi hệ thống ngoài.
- `MockIntegration` có helper tạo mock/spy hỗ trợ các tình huống message handler/source.
- Sau test cần **khôi phục endpoint và dữ liệu test**, tránh mock từ test trước ảnh hưởng test sau.

Đây là **thay component trong flow**, không phải thay mọi bean cùng tên hay giả lập đầy đủ giao thức. Endpoint ID phải được khai báo và dùng đúng ID mà cấu hình Integration đã đăng ký.

### 8.2. Ví dụ thay outbound handler bằng Mockito

~~~java
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@SpringJUnitConfig(OutboundIsolationTest.TestConfig.class)
@SpringIntegrationTest
class OutboundIsolationTest {

    @Autowired
    MockIntegrationContext mockIntegrationContext;

    @Autowired
    @Qualifier("toPartner")
    DirectChannel input;

    @AfterEach
    void restoreEndpoints() {
        mockIntegrationContext.resetBeans();
    }

    @Test
    void shouldSendOneMessageToOutboundEndpoint() {
        MessageHandler fakeSender = mock(MessageHandler.class);

        mockIntegrationContext.substituteMessageHandlerFor(
                "partnerOutboundEndpoint", fakeSender);

        input.send(MessageBuilder.withPayload("order-900")
                .setHeader("partner", "partner-A")
                .build());

        verify(fakeSender).handleMessage(argThat(message ->
                "order-900".equals(message.getPayload())
                        && "partner-A".equals(
                                message.getHeaders().get("partner"))));
    }

    @Configuration
    @EnableIntegration
    static class TestConfig {

        @Bean
        DirectChannel toPartner() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow partnerOutboundFlow(DirectChannel toPartner) {
            MessageHandler realAdapterBoundary = message -> {
                throw new IllegalStateException(
                        "Không được gọi endpoint thật trong isolation test");
            };

            return IntegrationFlow.from(toPartner)
                    .handle(realAdapterBoundary,
                            endpoint -> endpoint.id("partnerOutboundEndpoint"))
                    .get();
        }
    }
}
~~~

Mẫu này kiểm tra **message đến đúng outbound boundary** và nội dung message đáp ứng hợp đồng. Nó không kiểm tra việc partner nhận dữ liệu. Ở test adapter integration thật, phải dùng HTTP/SFTP/broker đích để xác minh request và trạng thái của transport.

**Ghi chú về phiên bản:** nếu phiên bản đang dùng có khác biệt ở DSL `handle(...)` hoặc API mock endpoint, chọn overload tương đương theo tài liệu API của phiên bản đó; mục tiêu không đổi là **endpoint có ID ổn định và được thay thế ở ranh giới external side effect**.

### 8.3. Thay inbound MessageSource khi kiểm thử poller

Đối với polling endpoint, có thể thay `MessageSource<?>` để kiểm soát khi nào message xuất hiện:

~~~java
import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.support.MessageBuilder;

MessageSource<String> fakeSource = () ->
        MessageBuilder.withPayload("file-ready.csv").build();

mockIntegrationContext.substituteMessageSourceFor(
        "fileInboundEndpoint", fakeSource);
~~~

Đoạn minh họa giả định context đã đăng ký endpoint `fileInboundEndpoint` tương thích với loại source. Trong bài test thực tế, fake nên trả **message theo kịch bản rồi trả null** để poller không phát cùng một message vô hạn mỗi tick; đồng thời cấu hình stop/start cho endpoint để test không phụ thuộc timing khởi động.

## 9. Kiểm soát poller và lifecycle endpoint

Một poller có thể dùng `fixedDelay`, `fixedRate`, cron, `maxMessagesPerPoll`, executor hoặc transaction manager. Các nguồn gây flaky test thường là:

- Poller chạy trước khi test gắn mock.
- Poller đọc file cũ hoặc hàng dữ liệu còn lại từ test trước.
- Hai scheduler tick trong lúc assertion đang chạy.
- Source trả message liên tục, khiến QueueChannel chứa nhiều bản.
- Transaction rollback hoặc filter trạng thái khiến message bị đọc lại.
- Endpoint được stop nhưng test vẫn còn một poll đang thực thi.

### Dùng noAutoStartup có chủ đích

~~~java
@SpringIntegrationTest(noAutoStartup = "inboundPollerEndpoint")
@SpringJUnitConfig(PollingTestConfig.class)
class PollerLifecycleTest {
    // Gắn mock source, chuẩn bị dữ liệu và output trước.
    // Sau đó lấy đúng endpoint lifecycle bean để chủ động start().
    // Cuối test stop() và khôi phục mock/context.
}
~~~

Mẫu `noAutoStartup` làm test kiểm soát **thời điểm bắt đầu endpoint**. Phải dùng đúng endpoint ID đã khai báo; đó không nhất thiết trùng tên input channel. Kiểm tra phiên bản và cách đăng ký endpoint trước khi áp dụng.

### Test poller nên tách các điều kiện

| Điều kiện | Cách test có giá trị |
|---|---|
| **Source rỗng** | `MessageSource.receive()` trả `null`, không có message ở output. |
| **Có một message** | Source phát đúng một message rồi hết, handler nhận một lần. |
| **Max messages per poll** | Chuẩn bị nhiều bản và chứng minh số lượt xử lý theo cấu hình, không suy từ sleep. |
| **Lỗi nguồn** | Source throw exception, xác minh error handling/rollback/alert đúng cấu hình. |
| **Stop/start** | Chủ động kích hoạt lifecycle; đảm bảo không còn poll mới sau stop, xét race với poll đang chạy. |
| **Tính idempotent** | Retry hoặc lần poll kế tiếp không tạo side effect trùng ngoài chính sách. |
| **Transaction** | Source/handler lỗi dẫn tới commit/rollback theo cấu hình thực tế. |

Ưu tiên **điều kiện quan sát** (latch, message nhận qua channel, trạng thái readback, event được ghi) hơn là `Thread.sleep(2_000)` rồi đoán scheduler đã làm việc. Khi test cần timing thật, dùng timeout có giới hạn và công bố đây là test concurrency/timing.

## 10. Test đồng bộ, bất đồng bộ và request/reply

### DirectChannel: logic cùng thread

Với `DirectChannel`, gửi message thường gọi subscriber đồng bộ. Exception từ handler có thể được ném về thread gửi dưới dạng `MessagingException` hoặc wrapper tương ứng.

~~~java
assertThrows(
        org.springframework.messaging.MessagingException.class,
        () -> input.send(MessageBuilder
                .withPayload("invalid")
                .build()));
~~~

Chỉ dùng assertion như trên khi flow thật sự **throw exception đồng bộ**. Nếu có filter drop message hoặc error handler nuốt lỗi, kỳ vọng phải khác; không thể coi mọi dữ liệu sai đều phải throw tại `send()`.

### ExecutorChannel: xử lý trên thread khác

Với `ExecutorChannel` hoặc endpoint chạy qua task executor, `send()` trả về không có nghĩa business handler đã xong. Test nên:

- Dùng output `QueueChannel`, `CountDownLatch` hoặc future để đợi bằng chứng.
- Đặt timeout rõ ràng, đủ phù hợp môi trường CI.
- Đảm bảo cleanup executor và endpoint sau mỗi bài.
- Kiểm tra lỗi được publish vào nơi nào theo cấu hình error handling; đừng đợi exception xuất hiện ở thread người gửi.

### Gateway request/reply

Đối với gateway, cần thêm các tình huống:

1. Request được ánh xạ thành message đúng channel, payload và headers.
2. Reply được tạo đúng kiểu dữ liệu, đúng correlation/response mapping.
3. Không có reply trong hạn: gateway xử lý timeout như hợp đồng.
4. Handler throw exception: lỗi được phản ánh theo cơ chế gateway.
5. Message một chiều không bị nhầm thành một lời gọi buộc phải có response.
6. Một request không bị ghép nhầm với reply của request khác khi concurrency cao.

Khi dùng `@MessagingGateway`, test có thể autowire interface gateway trong context và gọi như API thông thường. **Đó là kiểm thử contract request/reply của gateway**, không phải xác nhận HTTP/JMS bên ngoài hoạt động nếu outbound endpoint đã được mock.

## 11. Unit test trước, Spring context sau

Không phải lớp nào cũng cần `@SpringJUnitConfig`. Một transformer thuần Java nên được thử như một hàm:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class FileNameNormalizer {
    String normalize(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing name");
        }
        return value.strip().toLowerCase(java.util.Locale.ROOT);
    }
}

class FileNameNormalizerTest {
    private final FileNameNormalizer normalizer =
            new FileNameNormalizer();

    @Test
    void normalizesFileName() {
        assertEquals("orders.csv",
                normalizer.normalize(" ORDERS.CSV "));
    }

    @Test
    void rejectsBlankInput() {
        assertThrows(IllegalArgumentException.class,
                () -> normalizer.normalize("  "));
    }
}
~~~

Lợi ích: test rất nhanh, không phụ thuộc bean graph, broker, scheduler hoặc môi trường. Sau đó, **một flow test nhỏ** chứng minh transformer được nối vào đúng channel. Tách các tầng giúp thông báo lỗi rõ hơn.

## 12. Kiểm thử File inbound/outbound adapter

Adapter File có trạng thái thực tế: thư mục, tên file, quyền đọc/ghi, bộ lọc, pattern, file chưa ghi xong và xóa/lưu file sau khi xử lý.

### @TempDir cho filesystem test

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FileContractTest {

    @TempDir
    Path root;

    @Test
    void preparesAnInputFileAndChecksItsBytes() throws Exception {
        Path inbox = Files.createDirectory(root.resolve("inbox"));
        Path input = inbox.resolve("orders-001.csv");
        Files.writeString(input, "id,amount\n1,120\n");

        assertTrue(Files.isRegularFile(input));
        assertEquals("id,amount\n1,120\n",
                Files.readString(input));

        // Trong adapter test, cấu hình inbound directory = inbox.
        // Start poller; đọc output channel và kiểm tra Message<File>.
    }
}
~~~

`@TempDir` do JUnit Jupiter quản lý, tạo thư mục riêng cho từng test, tránh dùng thư mục production hoặc dùng chung thư mục từ lần chạy trước.

### Những ca cần có

| Ca | Mong đợi |
|---|---|
| File hợp lệ | Được phát đúng một message với payload/header theo contract. |
| File sai pattern/extension | Không được xử lý nếu filter loại bỏ. |
| File rỗng | Có phản hồi rõ: hợp lệ, rejected hay error theo policy. |
| File đang được ghi | Không xử lý file chưa hoàn chỉnh; dùng quy ước atomic rename/marker nếu hệ thống yêu cầu. |
| File trùng tên nhưng nội dung mới | Filter/key có quy tắc phù hợp; không tự coi đó là bản cũ một cách sai lệch. |
| Không có quyền đọc/ghi | Lỗi được ghi nhận, retry/alert theo policy; không đánh dấu xử lý thành công. |
| Outbound tên file xung đột | Thực thi quy tắc replace/append/fail theo cấu hình rõ ràng. |
| Restart adapter | Không đọc mất hoặc xử lý lại tùy ý; kiểm tra metadata store/filter state. |

**Chú ý bộ lọc:** một số filter chống trùng như `AcceptOnceFileListFilter` có trạng thái trong bộ nhớ hoặc metadata store, tùy loại cấu hình. Khi test restart và durability, phải dùng đúng loại store của production; test chỉ trong một process không chứng minh được hành vi sau khởi động lại.

## 13. Kiểm thử SFTP adapter

SFTP đòi hỏi test cả **hành vi kết nối** lẫn **file transfer semantics**. Mock handler chỉ kiểm tra message đã tới outbound endpoint; nó không chứng minh server SFTP sẽ chấp nhận authentication, đường dẫn, permission hoặc upload.

### Ma trận ca kiểm thử SFTP

| Trường hợp | Loại test phù hợp | Điều cần xác minh |
|---|---|---|
| Mapping local/remote path | Unit hoặc flow | Đường dẫn được xây từ dữ liệu đáng tin, không lộ đường dẫn cấm. |
| Upload thành công | SFTP server thử nghiệm | Remote file thực sự tồn tại và byte đúng. |
| Download thành công | SFTP server thử nghiệm | Local file hoàn chỉnh, đúng tên và metadata cần thiết. |
| Wrong credentials | SFTP server thử nghiệm | Kết nối bị từ chối, thông báo lỗi không lộ secret. |
| Host key sai | SFTP server thử nghiệm | Chính sách host-key verification từ chối endpoint không tin cậy. |
| Remote directory không tồn tại | SFTP server thử nghiệm | Fail/retry hoặc tạo directory theo quy ước đã duyệt. |
| Đứt mạng giữa transfer | Integration/fault injection | Không coi file chưa hoàn chỉnh là hoàn tất. |
| File được cập nhật sau lần poll | Server thử nghiệm | File filter và metadata store có ngữ nghĩa đúng. |
| Restart/reconnect | Server thử nghiệm | Session/connection lifecycle, retry và idempotency đúng. |

### Thiết kế môi trường test SFTP

- Dùng SFTP server **tạm thời/isolated** hoặc container thử nghiệm, không dùng máy chủ production.
- Tạo người dùng, remote directory và dữ liệu riêng cho từng test.
- Dùng host key test và kiểm tra hành vi xác minh host key; **không làm yếu xác minh khóa máy chủ chỉ để test dễ chạy**.
- Credential lấy từ cấu hình test hoặc secret store phù hợp, không commit password thật.
- Dọn remote file, session và context sau test; kiểm tra side effect ở cả phía local và remote.

Một số thư viện test có thể cung cấp **embedded SFTP server**, nhưng API và tương thích tùy phiên bản. Đừng xem class embedded của một thư viện ngoài là tiện ích mặc định có sẵn từ `spring-integration-test`.

## 14. Kiểm thử HTTP inbound và outbound

### Outbound HTTP

Một flow outbound HTTP có hai tầng kiểm thử:

1. **Flow test**: biến message nội bộ thành URI, method, body, headers và đưa đến outbound gateway/adapter đúng cách.
2. **HTTP integration test**: server test thực sự nhận request, trả status/body/header và mô phỏng timeout, 4xx, 5xx.

Với adapter dựa trên HTTP client có hỗ trợ công cụ mock tương ứng, có thể dùng HTTP stub hoặc mock server. Ví dụ `MockRestServiceServer` phù hợp với HTTP client kiểu `RestTemplate` trong phạm vi cấu hình tương thích; nếu sử dụng client khác hoặc reactive stack, cần công cụ tương ứng. Không xem một mock HTTP client là bằng chứng socket/TLS thật đã hoạt động.

### Inbound HTTP

| Case | Điều nên kiểm tra |
|---|---|
| Request hợp lệ | HTTP status, content type, body, header mapping, message vào channel. |
| Validation fail | 4xx có schema lỗi rõ, không chuyển message không hợp lệ vào nghiệp vụ. |
| Không được xác thực/ủy quyền | 401/403 tùy contract, không tin header identity do client tự viết. |
| Request gateway không có reply | Timeout/error response theo cấu hình; không treo request. |
| Service downstream lỗi | Mapping lỗi đúng, correlation và audit không lộ stack trace/secret. |
| Payload quá lớn/sai media type | Bị từ chối an toàn, không tiêu thụ tài nguyên vô hạn. |
| Concurrent requests | Reply đúng request, không trộn correlation giữa các luồng. |

`MockMvc` có thể phù hợp nếu HTTP inbound adapter/gateway đang chạy qua **Spring MVC/servlet context** và request được xử lý qua cấu hình tương thích. Nếu adapter dùng môi trường HTTP khác, kiểm tra tại endpoint thật hoặc dùng client/server test phù hợp.

**Một HTTP 200 không có nghĩa message đã được broker downstream commit hoặc file đã ghi xong.** Khi thiết kế request/reply, phải định nghĩa response biểu diễn *đã nhận*, *đã xử lý*, hay *đã hoàn tất với bằng chứng*.

## 15. Kiểm thử JMS, AMQP và Kafka: phân biệt broker semantics

JMS, AMQP và Kafka cùng vận chuyển message nhưng **không có cùng mô hình acknowledgment, offset và thứ tự**. Test phải bám giao thức và cấu hình listener cụ thể.

| Vấn đề | JMS | AMQP (ví dụ RabbitMQ) | Kafka |
|---|---|---|---|
| Đơn vị consume | Destination/queue/topic theo provider | Queue + exchange/binding/routing | Topic/partition/consumer group |
| Khái niệm xác nhận | Acknowledge/commit theo session/transaction mode | Consumer acknowledgment, reject/nack và requeue | Offset commit, position và poll |
| Retry/redelivery | Provider/session/container | Nack/requeue, retry/DLX theo setup | Consumer retry/topic lỗi/offset strategy |
| Thứ tự | Tùy destination, consumer, priority/provider | Tùy queue và concurrency | Bảo đảm thứ tự trong **partition**, không toàn topic |
| Test quan trọng | Session/transaction rollback | Requeue/DLX, confirm/return khi dùng publisher | Key/partition, offset, consumer group, rebalance |

### Các ca tối thiểu với broker thật

1. **Publish/consume success:** payload và các header vận chuyển đúng.
2. **Serialization:** schema/version/content type khớp producer và consumer.
3. **Consumer throws:** hành vi retry/redelivery/ack đúng cấu hình.
4. **Duplicate delivery:** consumer idempotent, side effect không bị nhân bản ngoài chính sách.
5. **Broker unavailable:** connection/recovery có giới hạn, cảnh báo và retry.
6. **Message không thể xử lý:** đi đến DLQ/DLT hoặc lỗi theo contract, không mất im lặng.
7. **Concurrency/order:** đảm bảo theo phạm vi được transport hứa hẹn.
8. **Application restart:** message chưa hoàn tất được xử lý theo transaction/ack policy.

**Không khẳng định “exactly once” đầu-cuối** chỉ vì Kafka hoặc broker có tính năng transaction/deduplication trong một phạm vi nhất định. Khi message kích hoạt ghi database, gọi HTTP hoặc upload file, những side effect bên ngoài vẫn cần thiết kế idempotency/transactional outbox hoặc reconciliation phù hợp.

### Khi nào dùng Testcontainers?

Testcontainers hữu ích để tạo môi trường broker/DB tạm thời cho test tích hợp:

- Kafka broker container cho topic, partition, consumer group, offset.
- RabbitMQ container cho exchange, queue, DLX, publisher confirm.
- Database container cho transaction, locking, query, poller và JDBC.
- Các broker JMS hoặc SFTP server container tương thích môi trường mục tiêu.

**Testcontainers không thuộc `spring-integration-test`**; đây là thư viện riêng và cần runtime container có sẵn. Khi CI không hỗ trợ container, có thể chạy test adapter trên hạ tầng thử nghiệm riêng có quản lý, nhưng phải tách rõ test mock và test transport thật.

## 16. Kiểm thử JDBC/database inbound/outbound adapter

JDBC polling thường có câu hỏi khác file và broker: **đã chọn record nào, khi nào đánh dấu xử lý, transaction bao gồm những bước gì, nhiều poller có đụng nhau không?**

| Tình huống | Điều cần kiểm tra |
|---|---|
| DB chưa có hàng | Poll trả null/không phát message; không lỗi. |
| Hàng mới hợp lệ | Query lấy đúng row, map payload/header đúng. |
| Hàng không hợp lệ | Validation reject; chính sách cách ly hoặc retry rõ ràng. |
| Handler lỗi trước commit | Transaction rollback theo cấu hình, row không bị mất dấu. |
| Cập nhật trạng thái row | Chỉ đánh dấu processed khi điều kiện cần hoàn tất đã đạt. |
| Hai instance cùng poll | Không xử lý trùng ngoài ngữ nghĩa được chấp nhận, khóa/claim record phù hợp. |
| DB mất kết nối | Retry/backoff, quan sát lỗi và recovery sau khi kết nối trở lại. |
| Batch và pagination | Không bỏ sót record khi đang xử lý batch và dữ liệu biến động. |

### Tại sao test với DB thật cần thiết?

H2 hoặc fake repository có thể giúp chạy nhanh nhưng không luôn phản ánh đúng transaction isolation, locking, SQL dialect hoặc hành vi `SELECT ... FOR UPDATE` của PostgreSQL/MySQL/SQL Server. Với logic chống trùng hoặc cập nhật trạng thái theo transaction, nên có test trên **DB engine tương đương production**.

**Ranh giới transaction:** commit database không tự nhiên đồng bộ nguyên tử với gửi Kafka/JMS/HTTP/SFTP. Nếu workflow cần đảm bảo không mất message khi ứng dụng chết giữa hai bước, test phải bao phủ cơ chế outbox/inbox, retry và recovery đã thiết kế.

## 17. Error channel, exception và quy trình recovery

Một message không thành công có thể được xử lý rất khác tùy flow:

| Ngữ cảnh | Điều có thể xảy ra | Hướng test |
|---|---|---|
| `DirectChannel` đồng bộ, không có handler nuốt lỗi | Exception quay về người gọi | `assertThrows` và kiểm tra type/cause. |
| Inbound poller | Lỗi có thể được error handler publish thành `ErrorMessage` hoặc log theo cấu hình | Kiểm tra đúng error flow, không chỉ caller. |
| `ExecutorChannel` / async | Lỗi xuất hiện ở thread khác | Nhận từ error path, latch hoặc bounded observation. |
| JMS/AMQP/Kafka listener | Container quyết định ack, rollback, requeue, offset | Test trên broker thật theo policy listener. |
| Outbound HTTP gateway | 4xx/5xx/timeout có thể được convert thành exception/reply lỗi | Test mapping trạng thái và recoverability. |
| File/SFTP upload | Có thể có partial side effect trước exception | Kiểm tra file thực tế, retry và cleanup. |

### ErrorMessage và dữ liệu lỗi

Spring Messaging/Spring Integration có `ErrorMessage` dùng payload chứa `Throwable`. Tuy nhiên không phải **mọi exception** đều tự động chuyển đến một channel tên `errorChannel`. Điều đó tùy endpoint, error handler và bối cảnh async/sync đã được cấu hình.

Một test lỗi tốt cần trả lời:

1. Lỗi được **ném ra**, **gửi qua error channel**, hay **broker retry**?
2. Đường lỗi có giữ correlation với message gốc không?
3. Message có thể xử lý lại hay phải cách ly/quarantine?
4. Có giới hạn số retry, backoff và cơ chế báo động không?
5. Có tình huống partial side effect cần kiểm tra trước retry không?
6. Khi khắc phục xong, có bằng chứng message đã xử lý và không còn lỗi tồn dư không?

Không nên test bằng một assertion “không thấy exception” rồi coi là flow thành công; với async flow, lỗi có thể đã xảy ra ở thread khác sau khi test kết thúc.

## 18. Retry, idempotency, duplicate, ordering và recovery

Các transport nhiều khi có semantics **at-least-once**, đặc biệt khi ACK hoặc kết quả trả về bị mất. Một thiết kế kiểm thử nên dùng **message ID nghiệp vụ ổn định** thay vì kỳ vọng framework-generated `MessageHeaders.ID` sẽ tồn tại không đổi qua mọi hop.

### Hợp đồng idempotency

~~~json
{
  "eventId": "evt-order-991",
  "eventType": "ORDER_CONFIRMED",
  "schemaVersion": 2,
  "source": "checkout",
  "occurredAt": "2026-11-23T09:20:00Z",
  "orderId": "PO-991",
  "tenantId": "VN"
}
~~~

Ví dụ nếu cùng `eventId` được broker giao lại hai lần:

- Consumer có thể nhận hai message vật lý.
- Business handler nên kiểm tra `eventId` hoặc business key/operation key trong store phù hợp.
- Side effect như tạo hóa đơn phải đúng chính sách idempotency: không tạo hóa đơn trùng.
- Audit có thể ghi hai lần delivery nhưng chỉ một business operation thành công.

### Ma trận trạng thái lỗi

| Lỗi giả lập | Kết quả cần quan sát |
|---|---|
| Handler lỗi trước khi lưu trạng thái | Retry phù hợp, không đánh dấu business event hoàn tất. |
| Ghi DB thành công rồi mất ACK broker | Redelivery không sinh side effect trùng. |
| HTTP target nhận request nhưng client timeout | Retry idempotent hoặc readback để biết trạng thái. |
| SFTP upload đã xong nhưng response bị mất | Kiểm tra file đích/định danh trước khi upload lại. |
| Kafka consumer rebalance giữa xử lý | Offset/commit và side effect theo policy. |
| File poller restart | Filter/metadata store không đánh dấu nhầm file đã xử lý. |
| Event version thấp hơn đến muộn | Xử lý stale theo contract, không ghi đè trạng thái mới. |
| DLQ redrive | Message được xử lý lại có kiểm soát, không gây duplicate. |

**Test concurrency** cần chạy đủ nhiều lần hoặc dùng barrier/latch để tạo giao tranh có chủ đích, nhưng không nên khẳng định “không bao giờ có race condition” chỉ vì một lần test đi qua.

## 19. Quản lý thời gian để test không flaky

Hãy phân biệt **thời gian nghiệp vụ** với **thời gian chờ hệ thống**:

- Thời gian nghiệp vụ có thể inject `Clock`, dùng fake clock cho logic expiry, due time hoặc timeout nghiệp vụ.
- Poller/scheduler có vòng đời riêng; có thể cần test bằng scheduler được điều khiển hoặc chạy integration test có timeout hữu hạn.
- Broker/network có độ trễ biến động; cần bounded wait và tiêu chí quan sát thay vì đếm số mili-giây tùy ý.

### Các quy tắc thực dụng

1. **Không dùng sleep như cơ chế đồng bộ chính.** `Thread.sleep` chỉ làm test chậm, không bảo đảm event đã được xử lý.
2. **Không assert thời gian thực chính xác tuyệt đối** trừ khi chính tiêu chí yêu cầu và môi trường đã được kiểm soát.
3. **Không dùng timeout quá nhỏ** khiến CI thất bại theo tải máy.
4. **Không dùng timeout vô hạn** làm pipeline bị treo.
5. **Khởi tạo trạng thái mới** cho mỗi test: channel, broker topic/queue, file directory, database row, metadata store.
6. **Stop endpoint/executor và đóng connection** ở teardown, tránh test sau nhận message cũ.
7. **Đặt ID riêng cho test run** để dễ nhận diện dữ liệu, cleanup và xem log.
8. **Truy vết correlation** để biết chờ message nào, không lấy một message bất kỳ trong queue.

`QueueChannel.receive(timeout)` trả `null` nếu không có message trong khoảng chờ theo hợp đồng. Dùng `assertNotNull` sau khi nhận, nhưng khi kiểm tra “không có message”, cần một timeout hữu hạn đủ để quan sát hành vi; một lần `receive(0)` không chứng minh message sẽ không đến sau đó.

## 20. Test hợp đồng giữa các adapter và schema message

Khi một hệ thống phát JSON qua Kafka còn hệ thống khác nhận qua HTTP hoặc JMS, adapter không chỉ chuyển bytes; nó có thể thay đổi:

- Payload type và encoding (UTF-8, binary, object serialized).
- Header names, content type, Kafka key, JMS correlation, AMQP routing.
- Semantics timestamp, event ID và schema version.
- Trạng thái reply/error và retry.
- Quy tắc bảo mật, trust boundary và tenant mapping.

### Mẫu contract test

| Hạng mục | Ca kiểm thử |
|---|---|
| **Schema hợp lệ** | Payload JSON chứa đầy đủ `eventId`, `eventType`, `schemaVersion`, business key. |
| **Schema thiếu trường** | Bị từ chối/quarantine, không ghi side effect. |
| **Schema version mới** | Consumer hỗ trợ version theo hợp đồng hoặc reject có thông báo rõ. |
| **UTF-8** | Tiếng Việt và ký tự Unicode không bị biến đổi. |
| **Transport header** | Key/routing/correlation được map chính xác, không nhầm namespace. |
| **Security header** | Tenant/principal bắt nguồn từ thành phần đáng tin; không chỉ từ input do client tự khai. |
| **Replay** | Cùng event ID nhiều lần không tạo nghiệp vụ trùng. |
| **Reply/error contract** | Code lỗi, timeout, correlation và data redaction nhất quán. |

Contract test có thể chạy với stub để nhanh, nhưng khi giao thức/serializer/provider thực tế có hành vi riêng, phải có integration test xác thực trên transport thật. Đặc biệt JMS, AMQP và Kafka không có một “hợp đồng header chung” cho mọi thuộc tính.

## 21. Quan sát luồng trong test: channel, interceptor và message history

Khi flow dài, test cần nhìn vào các **điểm quan sát** mà không làm thay đổi quá nhiều production flow:

| Công cụ/cách tiếp cận | Dùng khi nào | Cẩn trọng |
|---|---|---|
| `QueueChannel` ở đầu ra thử nghiệm | Muốn assert payload/header cuối flow | Không biến mọi production channel thành QueueChannel. |
| `MockIntegrationContext` | Muốn thay inbound source hoặc outbound handler trong test | Phải reset và dùng endpoint ID đúng. |
| Mockito mock/spy handler | Muốn verify message được gửi tới boundary | Không chứng minh external side effect. |
| Channel interceptor / wire tap | Muốn quan sát message đi qua một channel | Tránh thay đổi latency, thứ tự và gây side effect phụ. |
| Message history | Muốn biết message qua các component nào khi đã bật hỗ trợ | Ghi lịch sử có overhead; không thay bằng chứng trạng thái target. |
| Integration graph/actuator khi cấu hình | Muốn chẩn đoán bean graph, endpoint và wiring | Phải phân quyền endpoint quan sát, không expose bí mật. |
| Metrics/logging/tracing | Muốn theo dõi throughput, delay, correlation | Không log password, token hoặc toàn bộ PII. |

`TestUtils` có thể hỗ trợ đọc thuộc tính nội bộ để kiểm tra cấu hình endpoint, nhưng test phụ thuộc reflection/private field rất dễ vỡ khi nâng cấp framework. Ưu tiên kiểm tra **hành vi công khai**; chỉ dùng nội quan khi cần xác minh cấu hình khó quan sát theo cách khác.

## 22. Kiểm thử cấu hình error flow có bằng chứng

Một lỗi thường gặp là viết test:

~~~java
input.send(MessageBuilder.withPayload("broken").build());
// Không throw => coi như thành công. Đây là kết luận không đủ!
~~~

Thay vào đó, xác định rõ:

~~~text
Scenario: outbound HTTP trả 503
Given: request hợp lệ với eventId=evt-42
When:  adapter gửi request tới stub HTTP server
Then:
  - Retry/backoff theo cấu hình
  - Không ghi thành công trước khi có response/bằng chứng đúng
  - Lỗi cuối cùng chuyển đến kênh xử lý hoặc trạng thái lỗi đã quy định
  - Correlation eventId được giữ trong audit
  - Không có side effect trùng ngoài chính sách
  - Khi server phục hồi, message được xử lý lại theo quy tắc recovery
~~~

Mỗi kết quả phải được quan sát tại **điểm có thẩm quyền**. Nếu hệ thống báo HTTP accepted nhưng task downstream xử lý bất đồng bộ, cần một cơ chế đọc kết quả cuối khác; không mặc định phản hồi đã xác nhận nghiệp vụ hoàn tất.

## 23. Test bảo mật cho integration adapters

Các adapter là ranh giới với hệ thống ngoài, nên có ca test an toàn riêng:

| Vấn đề | Test nên có |
|---|---|
| **Credential** | Không log password, client secret, key, bearer token khi kết nối lỗi. |
| **TLS/host verification** | HTTP/TLS hoặc SFTP host key không bị bỏ qua trong cấu hình thật. |
| **Path traversal** | File/SFTP path được xác thực, không cho `../` hoặc đường dẫn ngoài scope. |
| **Tenant isolation** | Message tenant VN không được định tuyến sang tài nguyên tenant khác. |
| **Untrusted headers** | Không cho client tự nhận vai trò admin chỉ bằng header. |
| **Oversized payload** | Có giới hạn kích thước và handling rõ, không cạn bộ nhớ dễ dàng. |
| **Deserialization** | Không chấp nhận kiểu dữ liệu không tin cậy ngoài allowlist/schema. |
| **Sensitive error output** | Response/log không trả stack trace, token hay cấu trúc bí mật. |
| **Idempotency abuse** | Duplicate/collision key không làm thao tác nhạy cảm bị ghi đè tùy ý. |

Không dùng credential, private key hoặc message dữ liệu khách hàng thật trong bài test; tạo dữ liệu giả và lưu secret thử nghiệm theo chính sách CI.

## 24. Ví dụ dự án thực hành: File inbound → validation → Kafka outbound

Giả sử hệ thống nhận file CSV từ thư mục nội bộ, mỗi file chứa đơn hàng, chuyển đổi sang sự kiện JSON và phát Kafka để dịch vụ khác xử lý.

~~~mermaid
flowchart LR
    FILE["File inbound poller"] --> VF["Validate name/content"]
    VF --> MAP["Transform CSV → OrderEvent"]
    MAP --> CHANNEL["MessageChannel"]
    CHANNEL --> KAFKA["Kafka outbound adapter"]
    VF --> ERR["Invalid file handling"]
    KAFKA --> RETRY["Retry / DLQ / alert"]
~~~

### 24.1. Hợp đồng đầu vào và đầu ra

**Đầu vào:** chỉ file `orders-*.csv` đã ghi xong; mỗi dòng có `orderId, amount, tenantId`; cấm file quá kích thước được chính sách quy định.

**Đầu ra:** sự kiện có `eventId, eventType, schemaVersion, orderId, amount, tenantId, occurredAt`. Kafka key nên phản ánh nhu cầu partition/ordering theo đơn hàng; nội dung/encoding theo contract.

### 24.2. Chiến lược test theo tầng

| Tầng | Test | Không cần |
|---|---|---|
| Unit | CSV parser hợp lệ/sai; validator, mapper, event ID logic | Spring context, broker |
| Flow | File-like message → transformer → mock Kafka boundary; assert payload/header | Kafka thật |
| File adapter | @TempDir, file filter, poller, restart, read once | Kafka nếu outbound được mock |
| Kafka adapter | Broker thử nghiệm, key/topic/partition, serializer, retry | File poller nếu message được đẩy trực tiếp |
| End-to-end | Tạo file → poll → Kafka → consume bằng test client → xác minh event | Mock boundary |

### 24.3. Test matrix tối thiểu

1. **Một file hợp lệ:** đúng một event, nội dung chính xác.
2. **CSV thiếu cột:** không publish Kafka; record lỗi có nguyên nhân.
3. **File chưa hoàn tất:** chưa đọc trước khi hoàn thành.
4. **Hai file cùng order ID:** xác định là hai event hợp lệ hay duplicate theo contract; không suy đoán.
5. **Kafka unavailable:** retry/backoff và trạng thái file được giữ an toàn, không tuyên bố hoàn tất.
6. **Publish được nhưng mất ACK:** kiểm tra chống duplicate hoặc reconciliation.
7. **Application restart:** file nào được xử lý lại theo metadata và cơ chế commit.
8. **Hai instance poller:** tránh xử lý trùng ngoài chính sách.
9. **Header tenant không hợp lệ:** từ chối, không publish sang tenant/topic sai.
10. **Recovery:** broker trở lại và các file pending được xử lý, có bằng chứng.

### 24.4. Bằng chứng để kết luận thành công

Việc mock outbound handler nhận event chứng minh **flow đã chuyển message tới boundary**, nhưng **không chứng minh Kafka đã lưu event**. Test tích hợp phải xác minh broker/consumer đã quan sát được event; nếu ứng dụng downstream còn thao tác cơ sở dữ liệu, end-to-end test riêng phải xác nhận trạng thái đích cuối.

## 25. Mẫu test plan dùng lại cho mỗi adapter

~~~yaml
# Ví dụ đặc tả test, không phải cấu hình Spring Integration trực tiếp.
adapterTestPlan:
  id: file-to-kafka-order-events
  owner: integration-team
  inbound:
    type: FILE
    source: isolated-test-directory
    poller:
      controlledStartup: true
      sourceExhaustion: true
  flow:
    inputPayload: File
    outputPayload: OrderEvent
    requiredHeaders: [tenantId, traceId]
    correlationKey: eventId
  outbound:
    type: KAFKA
    target: ephemeral-test-broker
    testTopicPrefix: it-orders-
  isolation:
    unitTestsWithoutSpring: true
    flowTestsWithMockEndpoint: true
    transportTestsWithRealBroker: true
  scenarios:
    - happy-path
    - invalid-csv
    - duplicate-event
    - broker-unavailable
    - retry-after-ack-lost
    - restart-poller
    - wrong-tenant
  evidence:
    - sentMessage
    - targetObservedEvent
    - errorEvent
    - retryCount
    - correlationId
  cleanup:
    - stop-pollers
    - reset-mock-endpoints
    - delete-test-files
    - delete-test-topics
~~~

Với HTTP, SFTP, JMS, AMQP hoặc JDBC, thay phần outbound/inbound và bổ sung semantics giao thức, nhưng **giữ ý tưởng tách test flow, transport và bằng chứng**.

## 26. Tối ưu test suite trong CI/CD

### Đề xuất cách chạy

- **Unit + flow isolation**: chạy ở mọi pull request, nhanh và có tính quyết định.
- **Adapter integration**: chạy khi thay adapter/config/contract, có thể chạy thường xuyên nếu CI đủ khả năng.
- **End-to-end đa hệ thống**: chạy theo lịch hoặc trước release quan trọng, ưu tiên kịch bản tác động cao.
- **Resilience/fault injection**: chạy có kiểm soát để kiểm chứng retry, recovery, restart và broker unavailable.

### Điều kiện môi trường

1. Mỗi test có directory, topic, queue, schema/record hoặc namespace riêng.
2. Dọn cleanup ngay cả khi assertion thất bại.
3. Không phụ thuộc thời gian máy cục bộ hoặc múi giờ mặc định khi xử lý timestamp.
4. Dùng version dependency tương thích và khóa cấu hình broker/DB trong CI.
5. Giới hạn timeout cho startup, test và teardown; log đủ để chẩn đoán.
6. Nếu hệ thống ngoài unavailable, báo **test infrastructure failure** khác với logic assertion failure khi có thể.
7. Chỉ bật parallel execution khi fixture, channel, broker và state được cô lập.
8. Lưu report dễ truy tìm: test name, adapter type, correlation/event ID, expected/actual, bằng chứng.

## 27. Các anti-pattern khi kiểm thử Spring Integration

| Anti-pattern | Hậu quả | Cách cải thiện |
|---|---|---|
| **Dùng broker thật cho mọi test** | Suite chậm, lỗi hạ tầng che lỗi logic | Unit/flow test trước, integration test có chọn lọc. |
| **Mock tất cả và tuyên bố adapter đã hoạt động** | Không kiểm tra giao thức và side effect thực | Có adapter test với server/broker thật. |
| **Dùng `Thread.sleep` cố định** | Test flaky khi CI có tải khác nhau | Dùng bounded wait + quan sát message/readback. |
| **Không reset `MockIntegrationContext`** | Mock test trước ảnh hưởng test sau | Cleanup/reset đúng vòng đời. |
| **Không cô lập directory/topic/queue** | Test đụng dữ liệu cũ hoặc chạy song song sai | Fixture/namespace riêng mỗi test. |
| **Giả định async `send()` là xử lý xong** | Bỏ qua lỗi thread khác | Đợi tín hiệu/bằng chứng output. |
| **Cho mọi exception vào errorChannel theo giả định** | Test không đúng semantics sync/async | Kiểm tra endpoint và error handler thật. |
| **Dựa vào framework message ID để dedupe nghiệp vụ** | Retry/transform tạo ID mới, mất idempotency | Dùng event/business key ổn định. |
| **Không test rollback/ack/offset** | Mất hoặc xử lý trùng message sau lỗi | Test giao thức và transaction trên broker/DB thật. |
| **HTTP 200/Kafka send future complete = end-to-end success** | Downstream còn lỗi hoặc chưa xử lý | Đọc trạng thái/consume ở đích cần chứng minh. |
| **Lộ secret trong log test** | Credential bị phát tán qua CI | Redact và dùng secrets/fixture giả. |
| **Test chỉ một happy path** | Không bắt lỗi schema, timeout, duplicate, security | Tạo test matrix âm tính theo rủi ro. |

## 28. Bài tập thực hành

### Bài tập 1 — Flow trong bộ nhớ

Tạo `DirectChannel` nhận payload `String`, transformer chuẩn hóa chữ hoa và `QueueChannel` nhận kết quả.

Yêu cầu:

1. Dùng `@SpringJUnitConfig` và context nhỏ.
2. Gửi hai message khác `traceId`.
3. Assert payload, header, thứ tự theo semantics channel đã chọn.
4. Thêm input rỗng để kiểm tra validation/filter.
5. Giải thích vì sao bài này chưa chứng minh kết nối SFTP/Kafka.

### Bài tập 2 — Mock outbound boundary

Xây dựng flow `inputChannel → transformer → HTTP outbound endpoint`.

Yêu cầu:

1. Đặt endpoint ID ổn định cho outbound handler.
2. Dùng `@SpringIntegrationTest` và `MockIntegrationContext` để thay handler.
3. Verify HTTP request message có body, destination/reference và header tương ứng.
4. Reset mock sau test; có ca kiểm tra dữ liệu không hợp lệ không được gửi ra boundary.
5. Nêu test bổ sung cần một HTTP test server để kiểm tra status, timeout và retry.

### Bài tập 3 — Poller và File adapter

Dùng `@TempDir` tạo thư mục nguồn, inbound file adapter và `QueueChannel` output.

Yêu cầu:

1. Khởi động poller có kiểm soát, tránh đọc file trước khi setup xong.
2. Tạo file hợp lệ, file sai pattern và file mới ghi một phần.
3. Assert một file hợp lệ được nhận đúng một lần theo policy đã đặt.
4. Stop/restart endpoint và kiểm tra filter/metadata store.
5. Dọn toàn bộ file và khôi phục endpoint.

### Bài tập 4 — Test transport thật

Chọn một trong **SFTP, HTTP, JMS, AMQP, Kafka hoặc JDBC**.

Yêu cầu:

1. Tạo môi trường thử nghiệm riêng cho giao thức.
2. Viết happy path và tối thiểu ba ca lỗi: authentication/authorization fail, timeout/unavailable, duplicate/redelivery hoặc transaction rollback.
3. Kiểm tra side effect tại hệ thống đích, không chỉ verify mock.
4. Ghi rõ semantics acknowledge/commit/offset/session phù hợp giao thức.
5. Thêm cleanup và cách chạy ổn định trong CI.

### Bài tập 5 — Thiết kế test matrix tổng thể

Một pipeline nhận file CSV, gửi Kafka và tạo bản ghi trong database. Hãy thiết kế:

- **Unit tests** cho parser và validator.
- **Flow tests** với mock Kafka boundary.
- **Kafka integration tests** trên broker thử nghiệm.
- **Database transaction/idempotency tests** trên database phù hợp.
- **End-to-end tests** từ file đến bản ghi cuối cùng.
- **Failure/recovery tests** khi broker, database hoặc ứng dụng restart.
- **Security tests** với tenant sai, file traversal, secret trong lỗi.

Với mỗi test, nêu **đầu vào, điều kiện, điểm quan sát, timeout, bằng chứng pass/fail và phạm vi chưa được chứng minh**.

## 29. Checklist nghiệm thu

Một bộ kiểm thử Spring Integration adapter có chất lượng cần đạt:

- [ ] **Đã tách tầng kiểm thử**: unit, flow, adapter integration và end-to-end.
- [ ] **Có test Spring context nhỏ** cho wiring channel, payload, headers và route.
- [ ] **Dùng test utilities đúng phạm vi**: `@SpringIntegrationTest`/`MockIntegrationContext` để thay endpoint; mock không thay thế giao thức thật.
- [ ] **Poller có lifecycle kiểm soát**; test không phụ thuộc sleep cố định.
- [ ] **Phân biệt sync/async và adapter/gateway** trong assertion.
- [ ] **Có test hợp đồng message**: payload, schema, headers, correlation và lỗi.
- [ ] **Có test từng transport thực sự dùng**: File, SFTP, HTTP, JMS, AMQP, Kafka hoặc JDBC.
- [ ] **Có test lỗi, retry, duplicate, ordering và recovery** theo ngữ nghĩa hệ thống đích.
- [ ] **Có cơ chế idempotency và kiểm tra side effect** đối với workflow có thể redeliver.
- [ ] **Có timeout hữu hạn, cleanup và isolation** cho filesystem, broker, DB, context và endpoint.
- [ ] **Không chứa secret hoặc dữ liệu thật** trong test source, error log hoặc báo cáo CI.
- [ ] **Kết quả pass có bằng chứng ở đúng ranh giới**, không đồng nhất gửi message thành xử lý hoàn tất.
- [ ] **Có test matrix và cơ chế chẩn đoán** khi test fail do dữ liệu, cấu hình, môi trường hoặc protocol.

## 30. Tổng kết

**Spring Integration test utilities** giúp kiểm thử message flow có cấu trúc mà không phải khởi động tất cả hệ thống ngoài. `MessageBuilder`, `DirectChannel`, `QueueChannel`, `@SpringIntegrationTest`, `MockIntegrationContext` và Mockito đặc biệt hữu ích để cô lập handler, message source, poller và xác minh payload/header tại các ranh giới của flow.

Tuy nhiên, **mock endpoint chỉ chứng minh message đã tới ranh giới được mô phỏng**. Để khẳng định File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC hoạt động đúng trong điều kiện thực tế, cần integration tests có giao thức phù hợp, kiểm tra acknowledgment, transaction, retry, idempotency, connection lifecycle và trạng thái đích. Khi tổ chức duy trì được cả hai loại bằng chứng — **đúng logic trong flow** và **đúng side effect ở hệ thống ngoài** — bộ test mới thực sự hỗ trợ kết nối Spring Integration an toàn, ổn định và dễ bảo trì.

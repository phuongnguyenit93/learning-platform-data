# Testing outbound adapter bằng mock client trong Spring Integration

## 1. Mục tiêu học tập

Trong **Spring Integration**, *outbound adapter* là endpoint nhận `Message<?>` từ **MessageChannel** và thực hiện thao tác lên hệ thống ngoài: gửi HTTP request, upload file qua SFTP, publish JMS/AMQP/Kafka, ghi file hoặc cập nhật database. Khi có *outbound gateway*, hệ thống còn nhận response để đưa trở lại message flow. **Testing outbound adapter bằng mock client** là cô lập phần client giao tiếp với hệ thống ngoài rồi xác minh **message nào được gửi, lời gọi nào đã xảy ra, xử lý thành công hoặc lỗi ra sao** mà không cần phụ thuộc vào một dịch vụ bên ngoài trong mọi lần chạy test.

Bài học thuộc chương **Testing** của module **Spring Integration Adapters** (inbound/outbound adapter, gateway, poller và MessageChannel, kết nối file, SFTP, HTTP, JMS, AMQP, Kafka và database; quản lý hợp đồng message, lỗi và vòng đời kết nối).

Sau bài này, bạn có thể:

- Chọn đúng **ranh giới mock** giữa message flow, outbound handler, protocol client và hệ thống đích.
- Viết **JUnit 5 + Mockito** để kiểm tra một outbound MessageHandler được gọi từ `DirectChannel`.
- Kiểm tra payload, headers, routing, số lần gọi, thứ tự cần thiết và thông điệp lỗi; tránh assert những chi tiết ngẫu nhiên.
- Dùng `MockRestServiceServer` hoặc mock HTTP server khi outbound adapter gọi HTTP.
- Dùng test double cho SFTP, JMS, RabbitMQ, Kafka và JDBC với mức bảo đảm phù hợp.
- Hiểu `MockIntegrationContext` để **thay chính endpoint** trong flow khi không muốn chạy client thật.
- Kiểm thử retry, timeout, idempotency, async completion, transaction, shutdown/reconnect và bảo vệ secret.
- Biết khi nào mock **không đủ** và phải có integration test với SFTP server, broker, database hay HTTP server cô lập.

**Điểm cần nhớ:** Mock client có thể chứng minh ứng dụng **đã yêu cầu gửi** dữ liệu đến transport đúng kiểu, nhưng **không chứng minh** một server hay broker thật đã nhận hoặc xử lý kết quả. Do đó bài sẽ phân biệt rõ *behavior verified at mock boundary* và *side effect verified at target*.

## 2. Bản đồ ranh giới kiểm thử outbound

~~~mermaid
flowchart LR
    SRC["Inbound: file/SFTP/HTTP/broker/DB"] --> IN["inputChannel"]
    IN --> LOGIC["Filter / transform / route"]
    LOGIC --> OUTCH["outboundChannel"]
    OUTCH --> HANDLER["Outbound MessageHandler"]
    HANDLER --> CLIENT["HTTP/SFTP/JMS/AMQP/Kafka/JDBC client"]
    CLIENT --> TARGET["External target"]
    OUTCH -. "mock endpoint" .-> M1["Captured Message<?>"]
    CLIENT -. "mock client" .-> M2["Mockito verify / captor"]
    TARGET -. "integration test" .-> M3["Real side-effect assertion"]
~~~

Chọn vị trí mock theo câu hỏi cần trả lời:

| Vị trí thay thế | Cái gì còn chạy thật? | Cái gì được chứng minh? | Cái gì **chưa** được chứng minh? |
|---|---|---|---|
| **Mock outbound handler** | Transformer, router, channel, dispatcher | Message trước adapter đúng hợp đồng | Mapping protocol và client thật |
| **Mock protocol client** | Channel, outbound handler, logic mapping payload/header | Handler đã gọi client với đối số đúng, xử lý lỗi của client | Socket, auth, serialization cấp transport và server thật |
| **Mock HTTP server / broker test / SFTP server** | Cả handler và client network thực | Đường giao tiếp protocol, request, phản hồi/sự cố giả lập | Hệ thống production và toàn bộ hạ tầng của nó |
| **Staging end-to-end** | Hệ thống tích hợp gần thực tế | Business flow và side effect xuyên nhiều hệ thống | Mọi tình huống hiếm, race và outage production |

**Định nghĩa “đủ” phụ thuộc contract**. Nếu chỉ cần bảo đảm handler dùng đúng `partnerId` và `orderId` để gọi client, mock client rất phù hợp. Nếu cần bảo đảm TCP reconnect, TLS, SFTP host key, broker acknowledgments hoặc transaction semantics, mock Java method là chưa đủ.

## 3. Outbound adapter, outbound gateway và MessageChannel khác nhau

| Thành phần | Hợp đồng | Test quan trọng |
|---|---|---|
| **Outbound channel adapter** | One-way: nhận message và tạo side effect; không phát reply nghiệp vụ | Client đã được gọi đúng, lỗi/side effect phù hợp |
| **Outbound gateway** | Request–reply: gửi request, nhận response làm message | Request mapping, response payload/header, timeout |
| **DirectChannel** | Dispatch đồng bộ tới một handler được chọn | Mock client thường được gọi trước khi `send()` trả về |
| **ExecutorChannel** | Giao cho thread pool | Dùng verify có thời hạn hoặc chờ completion |
| **QueueChannel** | Consumer poll lấy message | Gửi vào queue không đảm bảo handler đã nhận |
| **PublishSubscribeChannel** | Một message đến nhiều subscriber | Không đếm tương tác mock như thể một consumer duy nhất |
| **Poller** | Chủ động lấy từ source hoặc pollable channel | Phải khởi động/điều khiển lifecycle để handler thực sự chạy |

**Sai lầm:** Assert `outboundChannel.send(message) == true` rồi kết luận HTTP upload thành công. Với nhiều channel, `send()` chỉ thể hiện phần giao nhận trong **channel/endpoint hiện tại**; nó không phải xác nhận ứng dụng phía ngoài đã commit.

Với một `DirectChannel` chạy handler đồng bộ, ngoại lệ có thể quay về thread gửi. Nếu xử lý nằm trong executor, listener hoặc poller, ngoại lệ và retry có đường khác; **test phải theo đúng topology**.

## 4. Hợp đồng message trước khi dựng mock

Giả sử hệ thống nhận một file đơn hàng và gọi dịch vụ fulfillment:

~~~text
Input to outbound handler:
  payload: OrderCommand(orderId="42", amount=100)
  header: correlationId="corr-42"
  header: sourceSystem="sftp"
  header: eventId="order-42"

Expected client call:
  partnerClient.submit(
      OrderCommand("42", 100),
      "corr-42"
  )

Expected failure behavior:
  invalid payload/correlation -> reject before calling client
  temporary client outage -> retry/recover per policy
  permanent business error -> fail/reject without blind retry
~~~

Contract phải nói rõ:

- **Payload type** và schema được outbound handler chấp nhận.
- **Header bắt buộc** và cách map sang URI/header/record key/remote path/DB column.
- **Destination** và phạm vi truy cập; không để input không tin cậy điều khiển đích tùy ý.
- **Số lần gửi được mong đợi**; có policy retry thì số call có thể lớn hơn một.
- **Result semantics**: client method trả thành công nghĩa là gì? Có nhận ack, future hay chỉ enqueue?
- **Timeout và error**: khi nào báo lỗi, retry/recover, chặn side effect thứ hai.
- **Idempotency**: duplicate business ID xử lý thế nào khi timeout sau khi phía đích đã thành công.
- **Security**: không capture và in token/secret nguyên văn khi test fail.

Không nên mock trước rồi mới tự suy ra contract từ `Mockito.verify(...)`. Bắt đầu bằng hành vi nghiệp vụ, sau đó chọn assertion đủ chứng minh hành vi ấy.

## 5. Dependencies và phạm vi phiên bản

Một test Java/Spring Integration thông dụng có:

| Nhóm | Thành phần | Mục đích |
|---|---|---|
| Spring Integration Core | `spring-integration-core` | `IntegrationFlow`, `MessageChannel`, `MessageHandler` |
| Spring Test | `spring-test` | `@SpringJUnitConfig`, Spring context test |
| JUnit 5 | `junit-jupiter` | Test lifecycle và assertions |
| Mockito | `mockito-core` / support từ `spring-boot-starter-test` | Mock client, `verify`, `ArgumentCaptor` |
| Spring Integration Test | `spring-integration-test` | `@SpringIntegrationTest`, `MockIntegrationContext` |
| HTTP | `spring-integration-http`, `spring-test` | HTTP outbound, `MockRestServiceServer` |
| Transport thật (tùy bài) | SFTP/JMS/AMQP/Kafka/JDBC modules | Test giao tiếp thật với test infrastructure |

Ví dụ **dependency minh họa** trong Maven (dự án dùng BOM để quản lý version):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đoạn này **không phải POM đầy đủ**; những artifact cần có version nếu dự án không dùng dependency management. Với HTTP/SFTP/JMS/AMQP/Kafka/DB, thêm module thích hợp theo phần đang học, không import mọi adapter chỉ để test một luồng.

**Lưu ý phiên bản HTTP:** Từ Spring Integration **7.1**, HTTP outbound hỗ trợ `RestClient` và cấu hình dựa trên `RestTemplate` được đánh dấu deprecated để chuyển đổi dần. Ví dụ `RestTemplate` trong bài dùng để minh họa một cách kiểm thử phổ biến trong hệ thống đang duy trì; dự án mới phải dùng lựa chọn phù hợp đúng phiên bản/framework và kiểm tra migration. Mock HTTP server hoạt động ở biên network sẽ giúp giữ semantics của HTTP client gần production hơn so với chỉ mock một phương thức.

## 6. Thiết kế testable outbound handler: Dependency Injection

Muốn mock client, cần **điểm tiêm phụ thuộc (dependency injection seam)**: MessageHandler không tự khởi tạo một client không thể thay.

**Thiết kế khó kiểm thử:**

~~~java
// Anti-pattern: client được tạo ngay trong handler.
class HardToTestOutbound {
    void send(OrderCommand command) {
        PartnerSdkClient sdk = new PartnerSdkClient("https://partner.example");
        sdk.submit(command); // Không thể inject mock bằng cách thông thường.
    }
}
~~~

Một hướng dễ test hơn:

~~~java
interface PartnerClient {
    void submit(OrderCommand order, String correlationId);
}

record OrderCommand(String orderId, int amount) {}

final class OrderOutboundHandler implements MessageHandler {

    private final PartnerClient client;

    OrderOutboundHandler(PartnerClient client) {
        this.client = client;
    }

    @Override
    public void handleMessage(Message<?> message) {
        if (!(message.getPayload() instanceof OrderCommand order)) {
            throw new MessageHandlingException(
                    message, "Expected OrderCommand payload");
        }

        Object correlation = message.getHeaders().get("correlationId");
        if (!(correlation instanceof String id) || id.isBlank()) {
            throw new MessageHandlingException(
                    message, "Missing correlationId");
        }

        client.submit(order, id);
    }
}
~~~

Các import cần có cho ví dụ trên là `org.springframework.messaging.Message`, `org.springframework.messaging.MessageHandler` và `org.springframework.messaging.MessageHandlingException`. `PartnerClient` là **giao diện do ứng dụng định nghĩa**, có implementation production gọi HTTP/SFTP/...; `OrderCommand` là DTO minh họa. Java record và pattern matching dùng cú pháp Java hiện đại (ít nhất Java 17 cho tổ hợp cú pháp trên). Không đặt endpoint URL, password hoặc token production vào ví dụ.

**Lợi ích:** có thể test logic kiểm tra payload/header và việc gọi client mà không cần network. Đồng thời giữ implementation client thật ở nơi riêng để test serialization, HTTP headers, TLS hay credentials ở tầng adapter/transport.

### 6.1. Cái gì nên mock, cái gì không?

| Thành phần | Khuyến nghị |
|---|---|
| PartnerClient interface | Mock trong test handler, kiểm tra method/arguments |
| Mapper/validator thuần | Thường để thật để kiểm tra hợp đồng nội bộ |
| MessageChannel + IntegrationFlow | Để thật trong flow test để kiểm chứng wiring |
| HTTP client/SDK thấp tầng | Mock ở unit test; có thêm mock server test |
| Network/broker/database | Dùng test infrastructure cho integration test |
| Clock/ID generator | Fake hoặc inject nếu quyết định timeout/idempotency |
| Retry scheduler | Giữ deterministic trong test, dùng thời gian/backoff nhỏ nếu cần |
| Logger/metrics | Kiểm tra event/metadata quan trọng, tránh quá phụ thuộc câu chữ log |

**Không mock `MessageChannel` nếu mục tiêu là xác minh chính wiring channel và endpoint.** Gửi message qua channel thật rồi verify mock client phía sau.

## 7. Bài test JUnit 5 + Mockito qua DirectChannel thực

Ví dụ dưới đây dùng một **outbound MessageHandler thật** và một **PartnerClient mock**. Các bean được khai báo trong Spring test context nhỏ; không cần chạy server ngoài.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OutboundHandlerTest.Config.class)
class OutboundHandlerTest {

    @Configuration
    @EnableIntegration
    static class Config {
        @Bean
        PartnerClient partnerClient() {
            return mock(PartnerClient.class);
        }

        @Bean("outboundOrders")
        MessageChannel outboundOrders() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow outboundFlow(PartnerClient client) {
            return IntegrationFlow.from("outboundOrders")
                    .handle(new OrderOutboundHandler(client))
                    .get();
        }
    }

    @Autowired
    @Qualifier("outboundOrders")
    MessageChannel outboundOrders;

    @Autowired
    PartnerClient partnerClient;

    @BeforeEach
    void clearMockInteractions() {
        reset(partnerClient);
    }

    @Test
    void sendsTheExpectedOrderWithCorrelation() {
        OrderCommand command = new OrderCommand("42", 100);

        boolean accepted = outboundOrders.send(
                MessageBuilder.withPayload(command)
                        .setHeader("correlationId", "corr-42")
                        .build()
        );

        assertTrue(accepted);
        verify(partnerClient, times(1))
                .submit(eq(command), eq("corr-42"));
        verifyNoMoreInteractions(partnerClient);
    }

    @Test
    void missingCorrelationDoesNotInvokeClient() {
        OrderCommand command = new OrderCommand("42", 100);

        assertThrows(RuntimeException.class, () ->
                outboundOrders.send(
                        MessageBuilder.withPayload(command).build()
                )
        );

        verifyNoInteractions(partnerClient);
    }
}
~~~

**Để chạy hai đoạn code ở mục 6 và 7 cùng nhau**, đặt `PartnerClient`, `OrderCommand`, `OrderOutboundHandler` vào các tệp Java hoặc cùng package test theo quy tắc truy cập của Java; dùng các import Spring Messaging đã nêu ở mục 6. Ví dụ test cố ý tham chiếu lại các kiểu đã định nghĩa, **không tạo bản thứ hai khác kiểu**. Cấu hình test dùng Mockito mock `PartnerClient`, còn message handler và channel là thành phần thật.

**Điều đã chứng minh:** Message qua `DirectChannel`, handler được dispatch, payload/correlation được kiểm tra, client nhận đúng arguments, message thiếu correlation bị chặn **trước khi** client được gọi.

**Điều chưa chứng minh:** HTTP POST có headers đúng, SFTP file thật đã upload, broker xác nhận publish, database transaction commit hoặc retry khi network mất.

### 7.1. Tránh assertion chỉ dựa vào send()

Ở `DirectChannel` đồng bộ, lời gọi mock có thể hoàn tất trước khi `send()` trả về; vì vậy `verify(...)` ngay sau `send()` là hợp lý ở topology này. Nếu chuyển sang `ExecutorChannel` hoặc pollable channel, phải chờ có giới hạn thay vì `verify(...)` tức thì.

### 7.2. Lỗi kiểu exception có thể bị framework bọc

Một handler có thể ném `MessageHandlingException` nhưng tầng dispatch của Spring Integration có thể ném exception đã được bọc tùy context/advice. Ví dụ dùng `assertThrows(RuntimeException.class)` để tập trung vào hành vi “reject trước khi gửi”; bài test cần chặt hơn có thể kiểm tra **cause chain** và mã lỗi nghiệp vụ được chuẩn hóa. Tránh assert nguyên văn stack trace hoặc class wrapper không phải contract.

### 7.3. Khi nào không cần Spring context?

Nếu chỉ test input validation của `OrderOutboundHandler`, có thể tạo thẳng handler:

~~~java
PartnerClient client = mock(PartnerClient.class);
OrderOutboundHandler handler = new OrderOutboundHandler(client);

Message<?> msg = MessageBuilder
        .withPayload(new OrderCommand("42", 100))
        .setHeader("correlationId", "corr-42")
        .build();

handler.handleMessage(msg);
verify(client).submit(new OrderCommand("42", 100), "corr-42");
~~~

Đây là **unit test handler**, không phải test wiring `IntegrationFlow`. Giữ cả hai loại test nếu quy trình cần chứng minh kết nối channel.

## 8. Dùng ArgumentCaptor để kiểm tra payload/header mapping

Nhiều client nhận DTO khác với payload đầu vào, chẳng hạn HTTP client nhận `ShipmentRequest` được tạo từ `OrderCommand`. Khi đó, dùng `ArgumentCaptor` để kiểm tra **đối số được tạo thật**, không chỉ kiểm tra một call xảy ra.

~~~java
ArgumentCaptor<ShipmentRequest> requestCaptor =
        ArgumentCaptor.forClass(ShipmentRequest.class);

verify(client).submit(
        requestCaptor.capture(),
        eq("corr-42")
);

ShipmentRequest sent = requestCaptor.getValue();
assertEquals("42", sent.orderId());
assertEquals(100, sent.amount());
assertEquals("v1", sent.schemaVersion());
~~~

Đây là snippet dùng với **giao diện/DTO phù hợp của ứng dụng**, không phải phần mở rộng trực tiếp của `PartnerClient` ở mục 7 (nơi `submit` nhận `OrderCommand`). Muốn áp dụng, định nghĩa rõ `ShipmentRequest` và client method tương ứng.

Với nhiều lần gọi:

~~~java
ArgumentCaptor<ShipmentRequest> requests =
        ArgumentCaptor.forClass(ShipmentRequest.class);

verify(client, times(3)).submit(requests.capture(), anyString());

List<ShipmentRequest> all = requests.getAllValues();
assertEquals(3, all.size());
assertEquals(Set.of("41", "42", "43"),
        all.stream().map(ShipmentRequest::orderId)
                .collect(Collectors.toSet()));
~~~

Cần xét **có cho phép thứ tự bất kỳ không**. Nếu flow chạy song song, so sánh tập business IDs thay vì giả định thứ tự gọi; nếu một message có thể được retry, phân biệt **3 message nghiệp vụ** với **3 attempts** của một message.

### 8.1. Dùng verifyNoInteractions đúng chỗ

`verifyNoInteractions(client)` thích hợp cho case đầu vào bị chặn **trước** biên outbound. Nhưng nếu policy định nghĩa retry/recovery hoặc gửi metrics thông qua cùng mock client, assertion “không tương tác” có thể quá mạnh. Hãy kiểm tra **không gọi hành vi gửi nguy hiểm** thay vì cấm mọi interaction không liên quan.

### 8.2. Không assert chi tiết triển khai vô nghĩa

Nếu business contract chỉ yêu cầu một request hợp lệ đến partner, không nhất thiết assert thứ tự gọi logger, mapper và metrics. Nhưng bắt buộc kiểm tra destination, payload, correlation/idempotency key và số lần side effect nếu chúng ảnh hưởng dữ liệu.

## 9. HTTP outbound adapter: mock client HTTP thay vì mock mọi thứ

HTTP là ví dụ rõ nhất về sự khác biệt giữa mock **Java interface** và mock **HTTP exchange**. Có hai cách phổ biến:

1. **Mockito mock `PartnerClient` hoặc `RestOperations`:** phù hợp khi chỉ cần xác minh phần code truyền đúng method/arguments; không chạy serialization và interceptor thật.
2. **`MockRestServiceServer` hoặc mock HTTP server:** giữ phần lớn đường HTTP client trong ứng dụng, kiểm tra method/URI/body/header và trả response mô phỏng. Mock server thật qua socket như WireMock/MockWebServer còn phù hợp để kiểm tra timeout/network behavior.

### 9.1. Dùng MockRestServiceServer cho HTTP outbound channel adapter

Ví dụ dưới đây dùng Spring Integration Java DSL với `RestTemplate` **cho các dòng phiên bản hỗ trợ cách cấu hình này**. Chọn `MockRestServiceServer` để chặn HTTP request không đi ra Internet.

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.http.dsl.Http;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

@SpringJUnitConfig(HttpOutboundAdapterTest.TestConfig.class)
class HttpOutboundAdapterTest {

    @Configuration
    @EnableIntegration
    static class TestConfig {
        @Bean
        RestTemplate partnerRestTemplate() {
            return new RestTemplate();
        }

        @Bean("ordersHttpOut")
        MessageChannel ordersHttpOut() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow httpOutboundFlow(RestTemplate partnerRestTemplate) {
            return IntegrationFlow.from("ordersHttpOut")
                    .handle(Http.outboundChannelAdapter(
                            "https://partner.example/api/orders",
                            partnerRestTemplate)
                            .httpMethod(HttpMethod.POST))
                    .get();
        }
    }

    @Autowired
    RestTemplate partnerRestTemplate;

    @Autowired
    @Qualifier("ordersHttpOut")
    MessageChannel ordersHttpOut;

    @Test
    void outboundAdapterPostsJsonToExpectedUri() {
        MockRestServiceServer server =
                MockRestServiceServer
                        .bindTo(partnerRestTemplate)
                        .build();

        server.expect(requestTo(
                    "https://partner.example/api/orders"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().json(
                    "{\"orderId\":\"42\",\"amount\":100}"))
                .andRespond(withSuccess(
                    "", MediaType.APPLICATION_JSON));

        assertTrue(ordersHttpOut.send(
                MessageBuilder
                        .withPayload(
                            "{\"orderId\":\"42\",\"amount\":100}")
                        .setHeader(
                            MessageHeaders.CONTENT_TYPE,
                            MediaType.APPLICATION_JSON_VALUE)
                        .build()));

        server.verify();
    }
}
~~~

**Điểm quan trọng:** `MockRestServiceServer` được bind vào **đúng instance `RestTemplate`** mà outbound handler sử dụng. Nếu ứng dụng tạo một `RestTemplate` khác bên trong handler, mock server này sẽ không bắt được request. Do đó **dependency injection của client là điều kiện để test có giá trị**.

Ở Spring Integration dòng mới, `RestClient` được ưu tiên. Có thể bind `MockRestServiceServer` vào builder/client thích hợp theo Spring Framework version, hoặc dùng mock HTTP server; giữ hợp đồng request/response tương tự. Tránh sao chép overload `RestTemplate` đã bị deprecated vào dự án mới mà không xem version.

**Ý nghĩa `server.verify()`:** yêu cầu đã khớp kỳ vọng của mock server Spring Test; **chưa chứng minh** TLS thực, DNS, proxy, load balancer hoặc API production thành công.

### 9.2. Nếu cần kiểm tra custom headers

Một message header tên `correlationId` **không mặc nhiên** trở thành HTTP header `X-Correlation-Id`. Cần cấu hình header mapper hoặc transformer trong flow và kiểm tra request thật được gửi tới mock server:

~~~java
// Thêm sau .andExpect(method(HttpMethod.POST))
// khi outbound handler đã được cấu hình map header đúng:
.andExpect(header("X-Correlation-Id", "corr-42"))
~~~

Nếu code chỉ đặt `correlationId` trong Spring message mà không cấu hình HTTP mapping, assertion này có thể thất bại hợp lý. **Test giúp phát hiện thiếu mapping**, không nên sửa bằng cách bỏ assertion của contract.

### 9.3. Negative test HTTP 4xx, 5xx và timeout

Một HTTP handler dùng client có thể nhận:

| Kết quả | Hành vi mong đợi |
|---|---|
| 201/204 theo contract | Thành công; one-way adapter không nhất thiết phát reply |
| 400 do payload sai | Lỗi nghiệp vụ, không retry vô hạn |
| 401/403 | Lỗi xác thực/ủy quyền, không log nguyên token |
| 409 | Xử lý conflict/idempotency theo API bên ngoài |
| 429/503 | Có thể retry có backoff nếu chính sách cho phép |
| Timeout sau khi gửi request | **Kết quả không chắc chắn**; server có thể đã xử lý |

Với `MockRestServiceServer`, dùng `andRespond(withServerError())` hoặc response status khác để kiểm tra exception mapping. Để tái hiện một kết nối bị reset, server đóng socket, TLS handshake hoặc delay ở tầng mạng, một **mock server chạy qua socket** thường phù hợp hơn vì nó giữ đường HTTP network/client gần thực tế.

### 9.4. Outbound adapter và gateway không cùng contract reply

`Http.outboundChannelAdapter(...)` mang semantics one-way; test chủ yếu xác minh **request đã được thực hiện** và lỗi phù hợp.

`Http.outboundGateway(...)` dùng khi muốn nhận **HTTP response thành reply message**, sau đó cần kiểm tra:

- Body/status/headers của response được đưa về channel phù hợp.
- Reply có correlation đúng với request.
- No reply/timeout/response không hợp lệ đi đường lỗi được quy định.
- Khi gửi nhiều request đồng thời, reply không bị ghép sai người gửi.

Không viết `outputChannel.receive(...)` cho một outbound adapter one-way rồi mong có phản hồi trừ khi flow được thiết kế thêm endpoint riêng.

## 10. Mockito mock client ở biên protocol và object mapping

Nếu outbound implementation dùng một SDK riêng có interface:

~~~java
interface ShippingApi {
    ShipmentReceipt createShipment(ShipmentRequest request);
}

record ShipmentRequest(String orderId, int amount) {}
record ShipmentReceipt(String shipmentId) {}
~~~

Test có thể stub:

~~~java
ShippingApi api = mock(ShippingApi.class);

when(api.createShipment(
        eq(new ShipmentRequest("42", 100))))
        .thenReturn(new ShipmentReceipt("sh-42"));

// Kích hoạt outbound gateway/service activator dùng api...
verify(api).createShipment(
        eq(new ShipmentRequest("42", 100)));
~~~

Đoạn trên là **mẫu phần client boundary**, chưa khai báo cả gateway/flow. Trong một test hoàn chỉnh, một handler thực nhận `Message<ShipmentRequest>`, gọi `api.createShipment(...)` và trả `ShipmentReceipt` để gateway/flow tạo reply message.

Nếu client dùng callback hoặc `CompletableFuture` thay vì trả trực tiếp, test cần hoàn tất future có kiểm soát rồi mới kiểm tra output. Mockito `verify(api)` chỉ chứng minh client method được gọi; **future hoàn thành thành công** là bằng chứng bổ sung độc lập.

### 10.1. Không mock chính mapper khi muốn test mapping

Giả sử handler nhận `OrderCommand` rồi tạo `ShipmentRequest`. Nếu bạn mock cả `ShipmentRequestMapper` để trả một object dựng sẵn, test chỉ chứng minh handler gọi mapper, **không chứng minh** đúng giá trị `orderId`/`amount` đã được tạo. Với phần mapping cốt lõi, giữ mapper thật hoặc có unit test riêng.

### 10.2. Captor và đối số nguy hiểm

Một số outbound adapters chọn remote path hoặc URI theo header. Test nên xác minh path/URI không thể bị dữ liệu không đáng tin đưa ra ngoài whitelist:

~~~text
Expected:
  bucket/path thuộc namespace được phép
  không nhận "../" để thoát thư mục
  không nhận URL do người dùng tự chỉ tới mạng nội bộ
  tenantId được ràng buộc với chủ thể
~~~

Không chỉ verify `client.send(any())`: đối số destination có thể sai dù method đã gọi. Với dữ liệu nhạy cảm, **capture metadata** như resource ID và checksum thay vì lưu secret nguyên văn vào failure report.

## 11. Dùng MockIntegrationContext để thay outbound handler

Có tình huống bạn không muốn mock client bên trong adapter, mà muốn **thay toàn bộ handler ở endpoint outbound** để test luồng mapping phía trước. Spring Integration cung cấp `@SpringIntegrationTest` và `MockIntegrationContext` cho mục đích này.

~~~mermaid
flowchart LR
    INPUT["inputChannel"] --> MAP["Mapper / filter / router"]
    MAP --> OUT["outboundChannel"]
    OUT --> REAL["Real outbound handler"]
    OUT -. "thay trong test" .-> MOCK["MockMessageHandler / captor"]
    MOCK --> ASSERT["Kiểm tra Message<?>"]
~~~

Ví dụ minh họa test với endpoint có ID `partnerOutboundEndpoint`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.integration.test.mock.MockIntegration.*;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.GenericMessage;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ProductionLikeFlowConfig.class)
@SpringIntegrationTest
class OutboundEndpointReplacementTest {

    @Autowired
    MockIntegrationContext mockIntegrationContext;

    @Autowired
    MessageChannel outboundInput;

    @AfterEach
    void restoreOriginalHandler() {
        mockIntegrationContext.resetBeans();
    }

    @Test
    void observesMessageBeforeRealTransport() {
        ArgumentCaptor<Message<?>> captor =
                ArgumentCaptor.forClass(Message.class);

        MessageHandler mockHandler = mockMessageHandler(captor);

        mockIntegrationContext.substituteMessageHandlerFor(
                "partnerOutboundEndpoint", mockHandler);

        outboundInput.send(new GenericMessage<>("order-42"));

        Message<?> captured = captor.getValue();
        assertEquals("order-42", captured.getPayload());
    }
}
~~~

**Giả định:** `ProductionLikeFlowConfig` là cấu hình riêng được cung cấp bởi ứng dụng/test, `outboundInput` là channel mà flow dùng và `partnerOutboundEndpoint` là **ID của consumer endpoint** bao bọc handler cần thay. ID này phải chính xác; **không dùng tên channel thay cho endpoint ID**. Với đầu ra bất đồng bộ, chờ/verify trong thời hạn trước khi đọc captor. API Mockito generic có thể cần suppress warning tương ứng compiler.

`MockIntegrationContext.resetBeans()` khôi phục trạng thái endpoint bị thay sau test. Nếu bỏ cleanup, bài test tiếp theo có thể âm thầm dùng mock handler thay vì adapter thật.

**So sánh quan trọng:**

- **Mock client**: handler thật vẫn chạy, kiểm tra chuyển message thành lời gọi client.
- **Mock handler**: handler thật không chạy, chỉ kiểm tra message tới đúng điểm cuối của flow.
- **Mock server**: handler và client thật chạy qua HTTP, kiểm tra protocol request/response ở biên network.

Không gọi ba cách này là tương đương.

## 12. SFTP outbound: mock SessionFactory hay mock RemoteUploader?

SFTP outbound thường phải xử lý **SSH session**, remote directory, rename, temporary file, write stream, retry và kết nối bị cắt. Có hai tầng mock:

1. **Mock façade do ứng dụng định nghĩa**, chẳng hạn `RemoteUploader.upload(InputStream, remotePath)`: đơn giản, ổn định, phù hợp test MessageHandler chọn path/content.
2. **Mock Spring Integration `SessionFactory`/`Session`**: gần protocol hơn, nhưng phải hiểu rõ adapter mở/đóng session và thứ tự `write/rename/exists`; dễ khiến test phụ thuộc chi tiết framework.
3. **SFTP server cô lập**: kiểm tra host key, auth, file write, connection reset và readback từ remote.

Ví dụ façade:

~~~java
interface RemoteUploader {
    void upload(byte[] content, String remotePath);
}

record TransferRequest(String fileName, byte[] content) {}

final class ExportOutboundHandler implements MessageHandler {

    private final RemoteUploader uploader;

    ExportOutboundHandler(RemoteUploader uploader) {
        this.uploader = uploader;
    }

    @Override
    public void handleMessage(Message<?> message) {
        TransferRequest request =
                (TransferRequest) message.getPayload();

        if (!request.fileName().matches("[a-zA-Z0-9_-]+\\.csv")) {
            throw new IllegalArgumentException("Invalid file name");
        }

        uploader.upload(
                request.content(),
                "/partners/orders/" + request.fileName());
    }
}
~~~

Test mock façade:

~~~java
RemoteUploader remoteUploader = mock(RemoteUploader.class);
ExportOutboundHandler handler =
        new ExportOutboundHandler(remoteUploader);

byte[] bytes = "orderId\n42\n"
        .getBytes(StandardCharsets.UTF_8);
handler.handleMessage(MessageBuilder
        .withPayload(new TransferRequest("orders_42.csv", bytes))
        .build());

ArgumentCaptor<byte[]> capturedBytes =
        ArgumentCaptor.forClass(byte[].class);

verify(remoteUploader, times(1)).upload(
        capturedBytes.capture(),
        eq("/partners/orders/orders_42.csv"));

assertArrayEquals(bytes, capturedBytes.getValue());
~~~

Các import JUnit/Mockito/Spring Messaging được lược bớt ở snippet; `RemoteUploader` và `TransferRequest` là interface/record ví dụ của ứng dụng. **Không dùng `byte[].toString()` để assert nội dung file**. Nếu production cần SFTP atomic upload bằng temporary name rồi rename, phải có test thấp hơn (façade implementation hoặc SFTP server) để chứng minh chuỗi thao tác ấy.

### 12.1. Không làm yếu bảo mật trong test SFTP

Nếu client thật kiểm tra SSH host key, mock façade **không chứng minh host key validation**. Một integration test với test SFTP server phải cung cấp host key theo cấu hình tin cậy và kiểm tra trường hợp host key sai bị từ chối; không tắt kiểm tra để tránh lỗi test.

### 12.2. Mô phỏng disconnect và partial upload

Mock client có thể ném exception sau lời gọi `upload`, nhưng việc đó không phân biệt **“chưa ghi gì”** và **“đã ghi một phần”**. Với logic khôi phục phụ thuộc hai trạng thái này, test cần SFTP test server hoặc fake stateful mô phỏng partial file, temporary suffix và rename, sau đó xác minh cleanup/idempotency.

## 13. File outbound adapter: khi nào nên dùng temp directory thay mock

Với file local, **filesystem thật trên thư mục tạm** thường rẻ và đáng tin hơn mock NIO/`Files` static. Test outbound file adapter có thể:

1. Tạo `@TempDir` làm output directory.
2. Cấu hình outbound handler với directory này.
3. Gửi message qua channel như production.
4. Kiểm tra file xuất hiện, đúng tên, nội dung/encoding và policy ghi đè.
5. Đảm bảo không có file tạm chưa hoàn tất, rồi teardown.

~~~java
@TempDir
Path outputDir;

// Sau khi fixture cấu hình file outbound adapter thật:
Message<String> msg = MessageBuilder
        .withPayload("orderId,total\n42,100\n")
        .setHeader("targetFileName", "orders-42.csv")
        .build();

assertTrue(outboundInput.send(msg));

Path file = outputDir.resolve("orders-42.csv");
assertTrue(Files.exists(file));
assertEquals(
        "orderId,total\n42,100\n",
        Files.readString(file, StandardCharsets.UTF_8));
~~~

Đoạn trên minh họa **assertion trong test có fixture**: `outboundInput` và cấu hình filename mapping là thành phần được test khai báo, không tự xuất hiện từ snippet. Nếu handler chạy trên executor, chờ file tồn tại với timeout.

Với adapter file, **đọc lại filesystem** có giá trị hơn `verify(mockFileWriter).write(...)` vì nhiều lỗi xảy ra ở path, quyền ghi, temporary filename, flush/rename hoặc encoding. Vẫn có thể mock wrapper file writer trong unit test business mapping để chạy nhanh.

## 14. JMS outbound: Mockito trên JmsTemplate và khoảng trống ack

Một outbound adapter JMS có thể delegate đến `JmsTemplate` hoặc đối tượng tương đương. Với custom sender façade:

~~~java
interface QueuePublisher {
    void publish(String destination, String body);
}

// Bài unit test cho handler của ứng dụng:
QueuePublisher publisher = mock(QueuePublisher.class);
OrderOutboundHandler handler = /* handler gọi publisher */;
handler.handleMessage(/* OrderCommand trong Message<?> */);
verify(publisher).publish(
        eq("orders.outbound"),
        eq("{\"orderId\":\"42\"}"));
~~~

Ví dụ trên **lược triển khai handler** để tập trung vào seam. Nếu mock trực tiếp `JmsTemplate`, tùy cấu hình có thể verify `convertAndSend(destination, payload)`, nhưng phải nhớ Spring Integration JMS adapter thực có thể dùng converter, session/connection factory và headers riêng; **verify phương thức mock không chứng minh JMS provider đã nhận hoặc commit**.

Integration test cần JMS broker thử nghiệm để kiểm tra queue/topic, message conversion, properties, ack/transaction, broker outage và redelivery. Với JMS transaction, xác minh rollback/retry thực tế theo provider và listener container đang dùng.

## 15. RabbitMQ/AMQP outbound: mock RabbitTemplate không thay confirms

Đối với RabbitMQ, có thể mock **publisher abstraction** của ứng dụng hoặc `RabbitTemplate` khi mục tiêu là kiểm tra exchange và routing key:

~~~java
RabbitTemplate rabbitTemplate = mock(RabbitTemplate.class);

MessageHandler handler = /* adapter/handler được inject template */;
handler.handleMessage(/* order event */);

// Khi handler thực sự chọn method này:
verify(rabbitTemplate).convertAndSend(
        eq("orders.events"),
        eq("order.created"),
        any());
~~~

Đoạn code minh họa **hình thức assertion**, không phải test class độc lập. API thực tế có nhiều overload; nếu handler sử dụng `MessagePostProcessor` hoặc confirmation callback, phải verify đúng overload và trường mapped message. Không lạm dụng `any()` khi exchange/routing key là một phần business contract.

**Publisher confirms/returns, binding, durability, nack, DLX/DLQ** cần broker test; mock `RabbitTemplate` không thể tái hiện đầy đủ. Một client method trả thành công chưa luôn đồng nghĩa message đã được route tới queue có consumer.

## 16. Kafka outbound: mock KafkaTemplate và kiểm tra kết quả bất đồng bộ

Kafka producer thường trả về một kết quả **bất đồng bộ**. Tùy phiên bản Spring Kafka, `KafkaTemplate.send(...)` trả một `CompletableFuture<SendResult<...>>`; ở các phiên bản cũ chữ ký async có thể khác. Test phải tách ba câu hỏi:

1. **Đối số publish:** topic, partition/key, payload và headers đã đúng chưa?
2. **Kết quả producer:** future được hoàn tất thành công/thất bại như thế nào; adapter quan sát failure ra sao?
3. **Kết quả consumer:** một consumer thật có đọc và xử lý record hay chưa?

Ví dụ ở **biên KafkaTemplate** nếu handler gửi topic/key/value:

~~~java
// Giả định handler thực sự dùng send(topic, key, value).
KafkaTemplate<String, OrderEvent> template =
        mock(KafkaTemplate.class);

OrderEvent event = new OrderEvent("42", 100);

// Stub future theo chữ ký của Spring Kafka version đang dùng.
when(template.send(eq("orders.events"),
                   eq("42"), eq(event)))
        .thenReturn(CompletableFuture.completedFuture(
                mockedSendResult));

// Kích hoạt outbound handler...
verify(template, times(1)).send(
        "orders.events", "42", event);
~~~

`mockedSendResult` là fixture có kiểu `SendResult<String, OrderEvent>`; cần tạo/stub hợp lệ theo phiên bản. Đây là **đoạn test minh họa**, không phải mã copy-paste độc lập. Nếu implementation gửi `ProducerRecord` hoặc dùng `send(Message<?>)`, hãy verify **đúng overload**.

### 16.1. Failure sau khi client method được gọi

Một `send(...)` trả future thất bại không tương đương method ném exception đồng bộ. Test nên tạo một `CompletableFuture` bị completeExceptionally, rồi chứng minh:

- Handler/advice/callback hoặc error flow **quan sát được failure**, không “quên” future.
- Retry/recovery có số lần và giới hạn theo thiết kế.
- Không báo business success khi producer chưa nhận confirmation cần thiết.
- Có đủ business ID để đối soát lần gửi và kết quả.

**Không đếm `verify(template).send(...)` là xác nhận Kafka broker đã ghi message.** Với yêu cầu broker semantics, dùng Kafka test infrastructure, đọc từ topic bằng consumer test có group/topic riêng và kiểm tra record key/schema/headers. Với side effect downstream, cần chạy consumer hoặc đo sink tương ứng.

### 16.2. Idempotency và Kafka

Kafka có các cơ chế giúp tăng độ tin cậy producer và xử lý transaction trong phạm vi cấu hình thích hợp, nhưng không nên tự khẳng định **exactly once từ Kafka đến HTTP/database ngoài transaction đó**. Test phải mô phỏng consumer crash, retry và duplicate event ID để chứng minh side effect của ứng dụng an toàn.

## 17. Database outbound: mock JdbcTemplate hay dùng database test?

Với outbound JDBC adapter hoặc service activator ghi DB, mock `JdbcTemplate` có thể xác minh SQL/parameters:

~~~java
JdbcTemplate jdbc = mock(JdbcTemplate.class);

// Bài test của handler ứng dụng gọi:
jdbc.update(
        "UPDATE orders SET status=? WHERE id=?",
        "SENT", "42");

// Assertion thường dùng khi thực hiện qua handler:
verify(jdbc).update(
        eq("UPDATE orders SET status=? WHERE id=?"),
        eq("SENT"),
        eq("42"));
~~~

Trong snippet này, lệnh `jdbc.update(...)` là ví dụ **lời gọi mà handler phải thực hiện**, không phải hành động nên tự gọi trước `verify` trong một unit test thực tế. Test đúng phải kích hoạt handler rồi mới verify mock. Hãy dùng tham số hóa SQL, tránh nối dữ liệu người dùng trực tiếp vào chuỗi truy vấn.

Một mock JDBC không kiểm tra:

- SQL có hợp lệ với loại database đang chạy hay không.
- Ràng buộc schema, index, transaction và isolation.
- DB row thật sự đổi hoặc commit.
- Hai instance cùng ghi thì lock/unique constraint có đúng không.
- Rollback/retry khi driver mất kết nối.

Vì vậy nếu logic phụ thuộc constraint, transaction và row count thực tế, dùng **database cô lập** (ví dụ PostgreSQL test container cùng version tương thích), chạy outbound flow và kiểm tra row sau commit. Đối với file/database adapters, một test **gần thực tế nhưng rẻ** thường đáng tin hơn việc mock toàn bộ I/O.

### 17.1. Kiểm tra số hàng được cập nhật

Nếu handler xử lý `JdbcTemplate.update(...)` trả về số row, việc trả 0 hoặc nhiều hơn một có thể là lỗi nghiệp vụ. Mock các giá trị 0, 1, nhiều row và exception để xác minh handler quyết định đúng:

~~~text
0 rows updated -> not found hoặc stale state
1 row updated  -> thành công theo contract
>1 rows        -> lỗi dữ liệu nếu chỉ được cập nhật một order
DB outage     -> retry hoặc recovery tùy policy
~~~

Nhưng khẳng định “update chính xác một record” cuối cùng cần kiểm tra **DB thật**, không chỉ Mockito stub `thenReturn(1)`.

## 18. Gateway và request–reply: mock client trả kết quả có ý nghĩa

Với outbound gateway, trả response là một phần contract. Giả sử client có method:

~~~java
interface ShippingGatewayClient {
    ShipmentReceipt create(ShipmentRequest request);
}

record ShipmentReceipt(String shipmentId, String status) {}
~~~

Bài test cần kiểm tra cả chiều đi và chiều về:

1. Message input chứa request hợp lệ.
2. Handler/gateway gọi client với đúng payload, correlation và destination.
3. Client mock trả response hợp lệ.
4. Gateway tạo reply message đúng kiểu, đưa về **reply channel** hoặc kết quả method caller.
5. Timeout/exception không bị chuyển nhầm thành thành công.

Ví dụ ý tưởng:

~~~text
Input gateway:
  shipment-request(orderId=42), correlationId=corr-42

Mock client:
  create(42) -> ShipmentReceipt(sh-42, ACCEPTED)

Expected reply:
  payload: ShipmentReceipt(sh-42, ACCEPTED)
  correlationId: corr-42
~~~

Không phải adapter/gateway nào cũng giữ nguyên tất cả message headers mặc định; nếu cần correlation ở reply, phải cấu hình và test header propagation cụ thể.

### 18.1. Client trả null, thiếu reply hoặc response sai schema

Kiểm tra khi mock client trả `null` hoặc response sai schema; tùy contract, gateway có thể timeout, trả null hoặc phát error. **Không viết assertion dựa trên giả định chung** rằng mọi gateway đều ném cùng exception. Dùng hành vi nghiệp vụ đã quy định và công cụ có timeout.

### 18.2. Từ request–reply sang async callback

Nếu client trả `CompletableFuture`, `Mono` hoặc callback, test phải điều khiển việc hoàn thành:

- Future thành công → output/reply đúng.
- Future thất bại → error flow/recoverer đúng.
- Future không hoàn tất → timeout không treo suite.
- Hủy request hoặc dừng adapter → không dùng connection sau shutdown.

Mock client trả future thành công tức thì **không kiểm tra** logic xử lý bất đồng bộ dưới race; cần thêm test với future được hoàn thành sau khi flow đã chạy.

## 19. Lỗi đồng bộ và bất đồng bộ: test đúng điểm bắt lỗi

Với `DirectChannel` và handler đồng bộ, client mock ném exception có thể làm `send()` ném exception:

~~~java
doThrow(new IllegalStateException("simulated transport failure"))
        .when(partnerClient)
        .submit(any(), anyString());

RuntimeException failure = assertThrows(
        RuntimeException.class,
        () -> outboundOrders.send(
                MessageBuilder
                    .withPayload(new OrderCommand("42", 100))
                    .setHeader("correlationId", "corr-42")
                    .build()));

assertNotNull(failure);
verify(partnerClient).submit(any(), eq("corr-42"));
~~~

**Các tên `partnerClient`, `outboundOrders`, `OrderCommand` là fixture của ví dụ mục 7.** Đây là test lỗi đồng bộ minh họa. Lớp exception bên ngoài có thể khác theo cơ chế wrap/advice; test nên assert nguyên nhân cần thiết và sự kiện nghiệp vụ, không khóa vào câu chữ một stack trace.

Với inbound poller, listener broker hoặc `ExecutorChannel`, exception không thể tự quay về caller đã trả về. Nó có thể được xử lý bởi:

- Error handler của polling endpoint hoặc listener container.
- `errorChannel`, kể cả channel chỉ định ở header khi thành phần hỗ trợ.
- `RequestHandlerRetryAdvice`/retry template hoặc cơ chế broker retry.
- Recoverer/DLQ/DLT hoặc outbox retry record.

**Không mặc định cứ tạo bean tên `errorChannel` là mọi lỗi đều được gửi đến đó.** Cần xác minh kiểu endpoint và cách cấu hình error handler thật.

### 19.1. Test error output

Nếu error flow đã được chủ động nối tới `PollableChannel errors`, hãy assert:

~~~java
Message<?> error = errors.receive(2000);
assertNotNull(error);
assertInstanceOf(ErrorMessage.class, error);

Throwable cause = (Throwable) error.getPayload();
assertNotNull(cause);
~~~

Snippet cần import `org.springframework.messaging.support.ErrorMessage`; `errors` do test config khai báo. Nếu một handler đồng bộ không có bridge sang error channel, hãy dùng `assertThrows` trên caller thay vì chờ `errors.receive(...)` rồi timeout.

### 19.2. Bẫy khi mock chỉ ném exception một lần

Nếu retry advice chưa được gắn vào endpoint, code:

~~~java
doThrow(new RuntimeException("temporary"))
    .doNothing()
    .when(client).submit(any(), anyString());
~~~

**không khiến Spring Integration tự retry**. Nó chỉ thiết lập mock thất bại ở lần gọi đầu và thành công ở lần thứ hai **nếu có ai đó gọi lần thứ hai**. Muốn kiểm tra retry, cấu hình retry policy thực trong handler/advice và assert `verify(client, times(2))` sau khi luồng đã hoàn tất.

## 20. Test retry/backoff bằng mock client có kiểm soát

Một test retry đúng phải quy định:

| Loại lỗi | Policy đề nghị (minh họa) | Assertion |
|---|---|---|
| Network timeout/503 tạm | Retry giới hạn, backoff | Số attempts, outcome/recovery |
| 400 invalid payload | Không retry | Chỉ 1 call, vào reject branch |
| 401/403 | Không retry mù quáng; xử lý credential/policy | Không in token, alert theo risk |
| DB deadlock tạm | Retry có giới hạn nếu operation an toàn | Không nhân đôi transaction side effect |
| SFTP partial upload | Tùy hỗ trợ atomic rename và cleanup | Không phát file hoàn tất sai |
| Broker send failure | Xử lý async ack/future đúng | Không báo delivered khi chưa có ack |

**Giữ production retry semantics trong test nhưng kiểm soát thời gian.** Nếu production có exponential backoff hàng phút, tạo cấu hình test để rút ngắn delay mà không bỏ qua số attempts, loại exception, recovery và điều kiện dừng.

Một mẫu assertion (chỉ dùng khi retry đã được cấu hình trong endpoint):

~~~java
doThrow(new TransientPartnerException("connection lost"))
        .doNothing()
        .when(client).submit(any(), anyString());

inputChannel.send(validMessage);

// Với flow đồng bộ, assert ngay; bất đồng bộ cần await.
verify(client, times(2)).submit(any(), eq("corr-42"));
verifyNoMoreInteractions(client);
~~~

`TransientPartnerException`, `inputChannel` và `validMessage` là fixture minh họa. **Không dán đoạn này vào test không có retry advice rồi kỳ vọng PASS**.

### 20.1. Retry không đồng nghĩa gửi hai nghiệp vụ

Một call có thể timeout **sau khi server đã xử lý**. Lúc retry, request có thể tạo lại đơn hàng nếu API không hỗ trợ idempotency. Test mock client không thể chứng minh server không bị nhân đôi khi response bị mất. Cần tích hợp thêm test fake server **stateful** hoặc database để theo dõi số side effects theo `eventId`/idempotency key.

### 20.2. Retry exhausted và DLQ/recoverer

Nếu tất cả attempts thất bại, kiểm tra:
 
- Có message lỗi/correlation đúng tới recoverer hoặc queue riêng.
- Trạng thái nghiệp vụ không bị đánh dấu `SENT`/`COMPLETED` giả.
- Không retry vô hạn làm dồn backlog.
- Có đủ metadata để operator điều tra, nhưng không chứa bearer token/secret nguyên văn.
- Khi replay, xử lý có idempotency và dấu vết attempts.

### 20.3. Phân biệt số attempts và số messages

Nếu một input được gửi một lần nhưng retry gọi `client.submit(...)` ba lần, `times(3)` là **số attempts**, không phải ba message nghiệp vụ khác nhau. Ghi rõ trong tên test và báo cáo. Nếu cần kiểm tra 3 messages khác nhau, dùng business ID riêng và `ArgumentCaptor`.

## 21. Async Mockito.verify và điểm hoàn tất đáng tin

Ở luồng có `ExecutorChannel`, task executor, Kafka future hoặc callback, việc verify ngay sau `send()` có thể race. Có thể dùng:

~~~java
input.send(validMessage);

verify(partnerClient, timeout(2000).times(1))
        .submit(any(), eq("corr-42"));
~~~

`Mockito.timeout(...)` chỉ đợi **tương tác với mock**; nó không bảo đảm remote operation đã hoàn tất, và nếu lời gọi tiếp tục retry sau đó, việc “đã thấy một call” không chứng minh “chỉ có một call”.

Để có kết luận mạnh hơn:

- Dùng `CountDownLatch` hoặc `CompletableFuture` để xác nhận endpoint đã hoàn tất theo contract.
- Chờ side effect đến mock server/DB với deadline rõ ràng.
- Nếu test cần “không có call thứ hai”, bảo đảm retry scheduler/flow đã kết thúc hoặc quan sát trong cửa sổ được định nghĩa.
- Không dùng `Thread.sleep(...)` cố định như biện pháp duy nhất.

### 21.1. Tương tác không theo thứ tự

Nếu các message được gửi song song, sử dụng captor để so sánh **tập key** thay vì giả định order, trừ khi contract có ordering guarantee (ví dụ theo partition key). `InOrder` của Mockito chỉ phù hợp khi thứ tự client calls là một phần contract và channel/executor thực sự bảo đảm.

### 21.2. Backpressure và channel capacity

Mock client thường phản hồi cực nhanh; như vậy nó **che giấu** hiện tượng downstream chậm làm đầy queue. Test có thể dùng fake client có barrier/latch để giữ một lời gọi và quan sát queue capacity, timeout, rejected task và hệ thống phục hồi. Không mô phỏng việc nghẽn thực tế chỉ bằng `Thread.sleep` không có đồng bộ.

## 22. Transaction boundary: điều mock client không thể kết luận

Một flow có thể ghi database, gọi HTTP và publish Kafka. Dù mock `JdbcTemplate`/`PartnerClient`/`KafkaTemplate` đều trả thành công, không có nghĩa ba tài nguyên thuộc **một transaction ACID**.

~~~mermaid
flowchart LR
    M["Message"] --> DB["Local DB transaction"]
    DB --> HTTP["HTTP outbound"]
    HTTP --> KAFKA["Kafka publish"]
    HTTP -. "timeout nhưng remote đã ghi" .-> RETRY["Retry"]
    RETRY -. "risk" .-> DUP["Duplicate side effect"]
~~~

Các failure boundary phải kiểm tra riêng:

1. DB ghi thành công nhưng HTTP fail → trạng thái nào được lưu, có outbox/compensation?
2. HTTP thành công nhưng DB rollback → retry sau đó có tạo side effect trùng?
3. Kafka publish future fail sau khi handler trả về → ai nhận biết và retry?
4. Quá trình bị kill giữa ghi output và ack nguồn → khả năng redelivery?
5. Endpoint bị stop trong khi đang gửi → drain/in-flight message/connection cleanup?

**Mock client** tốt để ép từng error branch, nhưng **integration test với DB/broker/HTTP mock server stateful** là nơi chứng minh tính nhất quán qua transaction boundary. Khi yêu cầu độ tin cậy cao, cân nhắc transactional outbox, idempotency key và reconciliation thay vì giả định rollback xuyên mọi giao thức.

## 23. Vòng đời kết nối: start, stop, restart, reconnect

Outbound adapter không chỉ có một lần `send()`. Với SFTP/AMQP/JMS/Kafka, client có thể sở hữu thread, connection pool, session cache hoặc producer resources.

| Tình huống | Test mock client chứng minh | Integration test bổ sung |
|---|---|---|
| Context start | Bean được inject, endpoint được subscribe | Kết nối tới server/broker thật |
| Stop | Gọi lifecycle method đúng (nếu contract) | Connection/session/threads được đóng hợp lệ |
| Restart | Handler có thể gửi lại sau start | Reconnect/metadata store/producer state |
| Client mất kết nối | Error/retry path được gọi | TCP/SSH/broker recovery thật |
| Credentials hết hạn | Handler xử lý lỗi auth đúng | Xác thực thật và rotation |
| Shutdown khi in-flight | Logic không đánh dấu success sai | Drain/requeue/ack thực tế |
| Backpressure | Queue/timeout policy khi mock bị giữ | Latency/capacity với target phù hợp |

**Không tự khẳng định `MockIntegrationContext` hoặc mock client đã test reconnect.** Một mock `client.send()` thành công không có socket để mất kết nối. Dùng integration test bên ngoài cho reconnect và resource leak; trong unit test, chỉ assert handler/recoverer phản ứng với các lỗi đã mô phỏng.

### 23.1. Timeout ở đúng lớp

Có nhiều timeout: channel send timeout, poller receive timeout, HTTP connect/read timeout, SFTP session timeout, broker ack timeout, gateway reply timeout. Test phải biết timeout nào đang tác động. Một timeout ở `receive(1000)` của test collector **không chứng minh** outbound client đã cấu hình network read timeout 1 giây.

## 24. Bảo mật khi mock outbound client

Outbound adapters thường mang credential, secret, filename, đường dẫn remote và dữ liệu cá nhân. Mocking giúp tránh dùng tài khoản production, nhưng bản thân test/report có thể làm rò dữ liệu nếu capture quá nhiều.

Nguyên tắc:

- Chỉ dùng **credential giả/không hoạt động** hoặc secret test do CI cấp an toàn.
- Không ghi `Authorization` header, cookie, API key, SSH private key vào report/stack trace để chứng minh call đúng. Có thể kiểm tra **header tồn tại** hoặc redacted fingerprint tùy hợp đồng.
- SFTP test thật phải kiểm tra host key, không disable verification vì tiện chạy.
- Với HTTP outbound, chặn URI không nằm trong whitelist, tránh SSRF và không cho input tự chọn host tùy ý.
- Với file/SFTP path, validate tên/đường dẫn, không cho `../` hoặc absolute path bất hợp lệ nếu không được phép.
- Khi mock client nhận DTO nhạy cảm, không in `ArgumentCaptor.getValue().toString()` trong assertion failure report một cách tự động nếu DTO chứa PII.
- Test nhánh thiếu auth, thiếu scope hoặc token hết hạn để chắc adapter/flow không biến lỗi thành success.

**Cách test hữu ích:** xác nhận request tới `partner.example`/topic/remote directory đúng, nhưng tránh đưa một secret production thật vào stub chỉ để so sánh ký tự.

## 25. Test matrix theo giao thức và tầng mock

| Adapter | Mock client phù hợp | Assertion quan trọng | Test cần chạy thêm để xác minh protocol |
|---|---|---|---|
| **HTTP outbound one-way** | Client façade / `RestTemplate` / `RestClient` với mock server | Method, URI, body, headers, status/error | HTTP mock server qua socket, timeout, TLS khi cần |
| **HTTP outbound gateway** | Mock client trả response | Request và reply/correlation/status | Mock server, response mapping, timeout |
| **SFTP outbound** | `RemoteUploader` hoặc `SessionFactory` | Remote path, bytes, temporary name, error | SFTP server cô lập, auth/host key, upload/rename |
| **File outbound** | FileWriter façade nếu cần | Filename, nội dung, policy | `@TempDir` + file thật, permission, atomic write |
| **JMS outbound** | `JmsTemplate` hoặc publisher port | Destination, payload, properties | Broker, ack, transaction, redelivery |
| **AMQP/RabbitMQ outbound** | `RabbitTemplate` hoặc publisher port | Exchange, routing key, headers | Broker binding, confirms/returns, DLQ |
| **Kafka outbound** | `KafkaTemplate` hoặc producer port | Topic, key, record, future success/failure | Broker, serialize/schema, offset, consumer |
| **JDBC/JPA outbound** | `JdbcTemplate`/Repository port | SQL/parameters, rows updated, exception | DB test, schema, transaction/constraints |
| **MessageChannel outbound** | Mock handler tại endpoint | Message cuối luồng đúng contract | Adapter thật nếu có side effect ngoài |
| **Custom SDK adapter** | Interface injected vào handler | DTO mapping, scope, retry classification | Test SDK client ở mock server/sandbox |

Với mục tiêu *Testing outbound adapter bằng mock client*, nên ưu tiên **một test sát handler** cho mỗi contract, rồi bổ sung **test transport tối thiểu** ở những trường hợp dễ xảy ra lỗi tích hợp. Đừng dùng một suite mock client để tuyên bố đã kiểm thử tất cả đặc tính protocol.

## 26. Case study: SFTP inbound → transform → HTTP outbound với mock client

### 26.1. Bối cảnh

Ứng dụng nhận đơn hàng CSV từ đối tác qua SFTP. File inbound adapter tạo message, parser chuyển dữ liệu thành `OrderCommand`, validation kiểm tra bắt buộc, sau đó outbound handler gọi API giao hàng. Mục tiêu là kiểm thử **đúng điểm outbound** mà không cần truy cập API production.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound / local file"] --> PARSER["CSV parser"]
    PARSER --> VAL["Order validator"]
    VAL --> CH["ordersOutboundChannel"]
    CH --> HANDLER["OrderOutboundHandler"]
    HANDLER --> CLIENT["PartnerClient interface"]
    CLIENT --> API["Shipping API"]
    CLIENT -. "Mockito mock in unit/slice test" .-> MOCK["verify / captor / exception stub"]
    API -. "mock server in integration test" .-> HTTP["HTTP request assertions"]
    HANDLER -. "failure" .-> REC["Retry / Error flow"]
~~~

### 26.2. Hợp đồng đầu vào và kết quả mong đợi

~~~text
Source:
  remote file: /incoming/orders-42.csv
  CSV: orderId,total
       42,100

Before outbound:
  payload: OrderCommand(orderId=42, amount=100)
  correlationId: order-42
  sourceFileName: orders-42.csv
  eventId: order-42-v1

Expected client call:
  submit(OrderCommand("42", 100), "order-42")

Expected HTTP with real client:
  POST /api/orders
  body {"orderId":"42","amount":100}
  X-Correlation-Id: order-42

Expected failure policy:
  invalid order -> reject before client
  HTTP 503 -> retry at most configured attempts
  timeout after server saved -> idempotency prevents duplicate order
~~~

### 26.3. Tầng 1 — Unit test parser và validator

Kiểm tra CSV hợp lệ, thiếu cột, mã đơn hàng trùng, amount âm/không hợp lệ, encoding và kích thước. Không mock parser nếu nó tạo dữ liệu đầu vào cho handler trong cùng bài test contract; unit riêng sẽ giúp định vị lỗi nhanh.

### 26.4. Tầng 2 — Flow test với mock client

Dùng `@SpringJUnitConfig` với `DirectChannel` và handler thật. Gửi một `OrderCommand` đã được chuẩn hóa vào `ordersOutboundChannel`, sau đó:

- `verify(client).submit(eq(command), eq("order-42"))`.
- Dữ liệu thiếu correlation → `verifyNoInteractions(client)`.
- DTO sai kiểu → không gửi.
- Hai lệnh khác nhau → nhận đúng hai calls, không trộn business ID.
- Với routing nhiều hệ thống, xác minh chọn đúng client/destination theo tenant/project.

**Điểm đã chứng minh:** message flow và outbound boundary. Không cần SFTP/HTTP thật để kiểm tra logic này.

### 26.5. Tầng 3 — HTTP adapter test bằng mock server

Cấu hình HTTP outbound handler/client **thật** với địa chỉ mock server:

- Assert `POST /api/orders`, body, content type, correlation header.
- Trả 201 và 400/503/timeout mô phỏng.
- Kiểm tra error mapping/retry theo endpoint production.
- Kiểm tra destination host không thể được lấy tùy ý từ payload user.
- Không in API token thật trong log test.

**Điểm đã chứng minh:** mapping HTTP và cách client tương tác với mock server. Chưa chứng minh API production còn hoạt động.

### 26.6. Tầng 4 — SFTP adapter test

Với SFTP server test, upload file vào remote folder, kích hoạt inbound poller, kiểm tra parser và downstream. Bài test này bổ sung những phần mà mock PartnerClient không bao phủ: remote sync, file filter, restart, host key và kết nối.

### 26.7. Tầng 5 — Recovery và idempotency

Mô phỏng:

1. Mock server ghi order rồi cố ý làm mất response.
2. HTTP client timeout.
3. Retry cùng `eventId` hoặc idempotency key.
4. Server kiểm tra key và không tạo order thứ hai.
5. Application ghi trạng thái cuối đúng và có audit attempts.

Đây là test **stateful** ở mock server/sandbox, không thể kết luận chỉ bằng `Mockito.verify(times(2))`.

### 26.8. Bảng kết quả mẫu

| Test case | Mock client thấy gì? | Hệ thống giả lập đích có gì? | Kết luận |
|---|---|---|---|
| Valid order | Một `submit(42)` | Một HTTP POST hợp lệ trong tầng protocol | PASS theo từng tầng |
| Missing correlation | Không có `submit` | Không có HTTP call | PASS |
| HTTP 400 | Một request, reject branch | Không có đơn hàng được tạo | PASS |
| HTTP 503 rồi 201 | Hai attempts theo policy | Một kết quả nghiệp vụ hợp lệ | PASS nếu đã định nghĩa retry |
| Timeout sau commit | Có retry | Chỉ một order theo idempotency | PASS |
| SFTP disconnect | Mock client HTTP có thể chưa được gọi | Không có dữ liệu giả hoặc xử lý sai | PASS nếu recovery theo hợp đồng |
| Duplicate CSV | Có thể nhiều input | Một side effect theo business key | PASS nếu contract idempotent |
| Không reset mock/context | Interaction từ test trước | Kết quả không đáng tin | FAIL test isolation |

## 27. Mẫu kế hoạch kiểm thử cho dự án thực tế

Một ticket phát triển outbound adapter nên có phần test plan rõ ràng:

~~~yaml
outboundAdapterTestPlan:
  component: "shipping-orders-http-outbound"
  flowEntry: "ordersOutboundChannel"
  endpointId: "shippingOrdersOutboundEndpoint"
  clientAbstraction: "PartnerClient"
  messageContract:
    payloadType: "OrderCommand"
    requiredHeaders:
      - "correlationId"
      - "eventId"
    destination: "shipping-service"
  cases:
    - "HAPPY_PATH"
    - "MISSING_HEADER_REJECTED"
    - "INVALID_PAYLOAD_REJECTED"
    - "TRANSIENT_FAILURE_RETRY"
    - "PERMANENT_FAILURE_NOT_RETRIED"
    - "TIMEOUT_UNKNOWN_OUTCOME"
    - "DUPLICATE_EVENT_ID"
    - "ASYNC_COMPLETION"
  fixtures:
    - "Mockito mock PartnerClient"
    - "HTTP mock server"
  requiredEvidence:
    - "Mock interaction args"
    - "HTTP request/response assertion"
    - "Side-effect count/idempotency"
    - "Error and recovery"
  isolation:
    - "unique correlationId per test"
    - "reset mock and stop endpoints"
~~~

Đây là **mẫu quản trị test plan**, không phải cấu hình Spring Integration có thể chạy trực tiếp. Mục tiêu là buộc test xác định rõ điểm quan sát, sự kiện lỗi và mức bằng chứng, tránh viết xong chỉ có một assertion `send() == true`.

### 27.1. Cách chia suite theo tốc độ

- **Fast unit suite:** test validator/mapper/handler và mock client; nên độc lập network, chạy thường xuyên.
- **Spring flow suite:** context nhỏ, adapter endpoint mock hoặc client mock; kiểm tra wiring, channel và exception propagation.
- **Protocol contract suite:** HTTP mock server, SFTP test server, broker/database container; chạy thường xuyên trong CI có hạ tầng.
- **Pre-release/staging suite:** kết nối các dịch vụ sandbox có auth/TLS và cấu hình gần production, chạy theo lịch phù hợp.

Không coi một test nhanh là “kém chất lượng”; nó có giá trị nếu **đúng phạm vi được công bố**. Vấn đề là dùng kết quả ở phạm vi hẹp để kết luận khả năng vận hành rộng hơn.

## 28. Những lỗi phổ biến trong chính bài test

| Anti-pattern testing | Vì sao sai | Cách thay |
|---|---|---|
| Mock toàn bộ `IntegrationFlow` rồi verify client | Không chạy wiring, routing thật | Giữ flow thật trong Spring test context |
| Handler tự tạo client bằng `new` | Không inject mock dễ dàng | Constructor injection/factory có kiểm soát |
| Chỉ assert `send() == true` | Không xác minh client đã nhận | `verify`/captor và test side effect |
| `verify(client).send(any())` | Che giấu destination và payload sai | Assert đích, business key, content/header |
| Mock client trả success cho mọi lỗi | Không test retry/recovery | Stub 4xx/5xx, timeout, exception, async failure |
| Coi mock method return là broker ACK | Không có broker thực | Integration test với confirm/offset/ack |
| Test retry bằng `doThrow().doNothing()` nhưng không gắn advice | Không có lần gọi thứ hai | Cấu hình retry thật và assert số attempts |
| Assert Mockito ngay trên async flow | Race, flaky | `timeout`/latch và completion signal |
| Thay adapter bằng mock rồi test serialization | Serialization thật bị bỏ qua | Mock HTTP server hoặc broker test |
| Không reset `MockIntegrationContext` | Handler thật không được khôi phục | `resetBeans()` ở teardown |
| Dùng chung mock giữa các test không reset | `verify(times(...))` thấy calls cũ | Reset/context isolation |
| Kiểm response gateway cho adapter one-way | Sai semantics của endpoint | Test side effect thay reply |
| Mock SFTP rồi tuyên bố host key an toàn | Không có SSH handshake thật | SFTP server test và negative host key |
| So sánh mọi header/message ID | Coupling với chi tiết framework | Assert header thuộc business contract |
| Chỉ test happy path | Bỏ qua outage, duplicate, partial failure | Ma trận negative tests có deadline |
| Log toàn bộ Authorization header trong failure report | Nguy cơ lộ secret | Redact, assert tên/mức hiện diện |
| Timeout bằng `Thread.sleep` cố định | Flaky và chậm | Chờ condition/event có giới hạn |
| Không tách test data | File/broker record cũ gây xanh giả | Temp dir, queue/topic/schema riêng |
| Mọi lỗi đều retry | Có thể nhân đôi side effect hoặc retry vô hạn | Phân loại transient/permanent và idempotency |

## 29. Checklist nghiệm thu và tình huống tự kiểm tra

### 29.1. Checklist

- [ ] Xác định endpoint là **outbound adapter one-way** hay **outbound gateway request–reply**.
- [ ] Có ranh giới mock rõ: outbound handler, injected protocol client hay mock server.
- [ ] Flow test giữ đúng channel topology ở phạm vi tuyên bố.
- [ ] Có contract payload, headers, destination, timeout, delivery và failure.
- [ ] Test mock client kiểm tra **đúng method và arguments**, không chỉ `any()`.
- [ ] Với HTTP, có test method/URI/body/header bằng client/mock server phù hợp.
- [ ] Với file, SFTP, JMS, AMQP, Kafka, DB, biết điều nào phải có protocol integration test.
- [ ] Có case invalid payload/header không được gọi external client.
- [ ] Retry được cấu hình thật trong test, số attempts và recovery đúng.
- [ ] Với async client, test cả future success/failure và completion deadline.
- [ ] Có kiểm tra duplicate/idempotency khi message có thể được gửi lại.
- [ ] Có kiểm tra side effect ở đích nếu contract yêu cầu.
- [ ] Test không dùng credential hoặc dữ liệu production.
- [ ] Có setup/teardown cho mock, endpoint, listener, queue/topic/file và dữ liệu test.
- [ ] Không dùng `Thread.sleep` dài thay cho kiểm soát timing.
- [ ] Test report ghi rõ **đã chứng minh điều gì, chưa chứng minh điều gì**.
- [ ] Với hệ thống quan trọng, có negative test lifecycle, reconnect, timeout và partial failure.

### 29.2. Câu hỏi tình huống

**Tình huống A.** Một test mock `PartnerClient` và verify đúng payload, nhưng code production gửi HTTP với sai `Content-Type`. Test có phát hiện không?

**Trả lời:** Thường không, nếu serialization/header mapping nằm **bên trong implementation client đã bị mock**. Phải thêm test với HTTP client thật và mock HTTP server để quan sát request.

**Tình huống B.** `DirectChannel.send(message)` trả `true`, Mockito verify một client call. Có thể công bố SFTP upload đã thành công?

**Trả lời:** Chưa. Chỉ chứng minh handler đã gọi client. Phải dùng SFTP test server và kiểm tra remote file, rename/temp policy, lỗi mạng, auth/host key.

**Tình huống C.** Test giả lập Kafka `send(...)` trả future chưa hoàn tất nhưng handler vẫn báo thành công nghiệp vụ. Rủi ro?

**Trả lời:** Đánh đồng việc **khởi tạo thao tác gửi** với **kết quả async**. Cần kiểm tra future/callback, producer failure và trạng thái nghiệp vụ.

**Tình huống D.** Đã mock RabbitTemplate, verify gọi đúng exchange/routing key. Message không có consumer vì broker binding sai. Mock test có thể bắt lỗi?

**Trả lời:** Không. Cần RabbitMQ integration test để xác minh exchange/binding, publisher confirm/return và message nhận ở queue đúng.

**Tình huống E.** Mock client được cấu hình lần đầu ném exception, lần hai trả success. Tuy nhiên handler chỉ gọi một lần. Có thể kết luận retry của Spring Integration bị lỗi?

**Trả lời:** Phải kiểm tra handler có được gắn retry advice/policy chưa. Mockito không tự tạo retry. Nếu policy thật đã được cấu hình thì đây là lỗi cần điều tra theo endpoint/thread/error handler.

**Tình huống F.** Test thay outbound handler bằng `MockIntegrationContext` rồi verify payload đúng. Có thể coi adapter HTTP thật đã được test?

**Trả lời:** Không. Endpoint thật bị thay, chỉ kiểm tra flow trước adapter; phải có test khác giữ handler/client để xác minh HTTP request.

**Tình huống G.** Hai test dùng chung mock bean và chạy song song; `verify(times(1))` đôi khi fail. Nguyên nhân có thể là gì?

**Trả lời:** Interactions từ nhiều test dùng chung mock/context bị trộn, hoặc async handler của test trước còn chạy. Dùng isolation, correlation ID riêng, cleanup và không chạy song song trên cùng mock/queue nếu thiếu cơ chế phân tách.

**Tình huống H.** Client mock ném timeout, handler retry một lần rồi thành công. Server thật có thể đã xử lý request đầu tiên. Điều gì còn thiếu để an toàn?

**Trả lời:** Idempotency key, logic kiểm tra/đối soát kết quả không chắc chắn và test stateful để chứng minh không tạo hai side effects.

**Tình huống I.** Outbound HTTP gateway trả 201, nhưng tester chỉ verify mock client call. Phần nào còn thiếu?

**Trả lời:** Reply mapping/status/correlation và thời điểm/đường lỗi; một gateway có hợp đồng request–reply cần test **phản hồi quay về flow/caller**, không chỉ chiều gửi.

**Tình huống J.** DB outbound unit test mock `JdbcTemplate.update(...)` trả 1. Có thể kết luận transaction thực đã commit một row?

**Trả lời:** Không. Mock chỉ trả một giá trị; cần database test để kiểm tra schema, SQL, transaction, constraints và dữ liệu sau commit.

## 30. Tài liệu tham khảo và lưu ý sử dụng ví dụ

Các trang tài liệu chính thức hữu ích để đối chiếu **đúng phiên bản** khi triển khai:

- Spring Integration — Testing support: https://docs.spring.io/spring-integration/reference/testing.html
- Spring Integration — HTTP Outbound Components: https://docs.spring.io/spring-integration/reference/http/outbound.html
- Spring Integration — HTTP Java Configuration: https://docs.spring.io/spring-integration/reference/http/java-config.html
- Spring Framework — Testing Client Applications: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html

Chú ý:

1. Ví dụ **mã Java tự chứa** có thể ghép vào test context của dự án khi import, bean và DTO trùng với định nghĩa được cung cấp.
2. Những snippet có `/* handler */`, `mockedSendResult`, `fixture`, hoặc `...` là **mẫu minh họa một phần**, không phải test hoàn chỉnh; không nên sao chép rồi khẳng định build được ngay.
3. Với Spring Integration **7.1 trở lên**, cấu hình HTTP dựa `RestTemplate` đang được thay thế dần bằng `RestClient`. Hãy đối chiếu signature đúng version và cân nhắc mock server để test không phụ thuộc overload cũ.
4. `@SpringIntegrationTest`/`MockIntegrationContext` hữu ích để thay endpoint trong test, nhưng không thay thế việc test client thật ở mức protocol.
5. **Mỗi assertion cần có mục đích rõ:** đối số đã gửi, exception đã xử lý, broker đã ack, file đã lưu hay database đã commit — đây là các mức kết quả khác nhau.

## Kết luận

**Testing outbound adapter bằng mock client** giúp kiểm tra nhanh, xác định và an toàn cách Spring Integration biến `Message<?>` thành yêu cầu tới hệ thống ngoài. Khi giữ **MessageChannel và handler thật** rồi inject **mock client**, ta kiểm chứng được payload, headers, destination, số lần gọi, validation, exception và retry ở ranh giới outbound. Khi thay **outbound handler bằng `MockIntegrationContext`**, ta kiểm tra được flow phía trước adapter. Khi dùng **HTTP mock server, SFTP server, JMS/AMQP/Kafka broker hoặc database test**, ta mới có thêm bằng chứng về protocol và side effect. Sự kết hợp đúng các tầng — cùng timeout hữu hạn, idempotency, cleanup, kiểm toán lỗi và kiểm soát lifecycle — làm cho luồng file, SFTP, HTTP, JMS, AMQP, Kafka và database đáng tin cậy hơn mà không đánh đồng một lời gọi mock thành công với kết quả nghiệp vụ hoàn tất.

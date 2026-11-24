# MessageCollector và kiểm tra output trong Spring Integration Adapters

## 1. Tại sao cần thu thập output khi kiểm thử adapter?

Một luồng **Spring Integration** thường kết nối hệ thống ngoài vào xử lý nội bộ bằng **inbound adapter**, **outbound adapter**, **gateway**, **poller** và **MessageChannel**. Khi nhận file, lấy dữ liệu qua SFTP, đọc record từ cơ sở dữ liệu hoặc tiêu thụ message từ JMS/AMQP/Kafka, câu hỏi quan trọng không chỉ là *“đoạn code có chạy?”* mà còn là: **message nào đã đi ra, đi tới đâu, nội dung ra sao và có thực sự tạo kết quả ở hệ thống đích hay chưa?**

Trong chương **Testing** của module **Spring Integration Adapters**, chủ đề **MessageCollector và kiểm tra output** giới thiệu cách gom thông điệp ở ranh giới luồng và đưa ra assertion đáng tin cậy cho:

- **Payload:** kiểu dữ liệu, nội dung, encoding, schema và phép biến đổi.
- **Headers:** correlation ID, tên file, khóa định tuyến, content type, metadata vận chuyển.
- **Số lượng và thứ tự:** một hoặc nhiều message, kết quả phân nhánh, xử lý trùng.
- **Thời điểm:** đầu ra đồng bộ, đầu ra đến sau poller hoặc consumer bất đồng bộ.
- **Đường lỗi:** lỗi chuyển vào error flow, retry, dead-letter queue hoặc được trả cho gateway.
- **Tác động ngoài hệ thống:** file đã được tạo, HTTP request đã tới server, message được publish, bản ghi database đã được ghi.
- **Vòng đời:** start/stop/restart adapter, backlog, session, connection và cleanup sau test.

Bài học dùng Java, JUnit 5, Spring Test và các công cụ kiểm thử có liên quan. Code minh họa hướng tới Spring Integration hiện đại; những ví dụ **Spring Cloud Stream đời cũ** được dán nhãn rõ vì không được sử dụng như API mặc định trong dự án mới.

**Nguyên tắc cốt lõi:** *Message đã xuất hiện trong collector* chỉ chứng minh message đến **điểm thu thập**. Nó **không tự chứng minh** rằng outbound adapter đã hoàn tất I/O hoặc hệ thống nhận đã xử lý xong nghiệp vụ.

## 2. Phân biệt ba khái niệm dễ bị gọi chung là “MessageCollector”

Tên gọi `MessageCollector` dễ gây nhầm vì **Spring Integration** và **Spring Cloud Stream** cùng dùng `Message<?>` và các channel nhưng có mô hình test khác nhau.

| Bối cảnh | Công cụ | Ý nghĩa chính | Khuyến nghị |
|---|---|---|---|
| **Spring Integration thuần** | `QueueChannel`, `PollableChannel`, `MessageHandler`, `MockIntegrationContext`, `WireTap` | Thu message ở channel/endpoint trong flow | Cách phù hợp khi module sử dụng Java DSL, adapter và gateway trực tiếp |
| **Spring Cloud Stream test support cũ** | `org.springframework.cloud.stream.test.binder.MessageCollector` | Test binder giữ message từ outbound binding để test lấy ra qua `forChannel(...)` | **Legacy**; chỉ dùng để hiểu hoặc duy trì codebase cũ tương thích |
| **Spring Cloud Stream test binder hiện đại** | `InputDestination`, `OutputDestination` | Giả lập các binding đầu vào/đầu ra trong JVM, không cần broker bên ngoài | Dùng cho ứng dụng Spring Cloud Stream theo phiên bản tương thích |

**Điểm quan trọng:** Không nên thêm `spring-cloud-stream-test-support` vào một dự án Spring Integration thuần chỉ để dùng tên lớp `MessageCollector`. Bộ API cũ này thuộc **Spring Cloud Stream**, không phải là thành phần thu output mặc định của `spring-integration-test`.

Spring Cloud Stream cũng dựa trên Spring Integration ở lớp messaging, nên một số tài liệu dùng cụm “Spring Integration test binder”; điều đó **không đồng nghĩa** lớp legacy `MessageCollector` là một phần của core Spring Integration.

### 2.1. Chọn cách nào trong bài tập thực tế?

- Có **`IntegrationFlow` + `MessageChannel`** trực tiếp: dùng `QueueChannel` hoặc terminal handler riêng trong Spring Integration test context.
- Cần **thay outbound endpoint** để cô lập kết nối: dùng `MockIntegrationContext` và mock/spy handler có ID được chỉ định.
- Cần **quan sát nhánh giữa luồng mà không lấy mất message của consumer**: dùng wire tap hoặc kênh quan sát được thiết kế riêng.
- Viết ứng dụng **Spring Cloud Stream cũ** với `@EnableBinding`: hiểu `MessageCollector` nhưng lập kế hoạch chuyển test binder.
- Viết ứng dụng **Spring Cloud Stream theo function binding**: dùng `InputDestination`/`OutputDestination`.
- Cần chứng minh **Kafka/RabbitMQ/SFTP/HTTP thật sự hoạt động**: dùng test infrastructure phù hợp và assert ở **đích**, không chỉ collector in-memory.

## 3. Collector nằm ở đâu trong kiến trúc test?

~~~mermaid
flowchart LR
    E["External source: file/SFTP/HTTP/broker/DB"] --> IN["Inbound adapter/gateway"]
    IN --> C1["inputChannel"]
    C1 --> F["Filter/Transform/Route/Handle"]
    F --> C2["outputChannel"]
    C2 --> OUT["Outbound adapter/gateway"]
    OUT --> T["External target"]

    C1 -. "quan sát nếu cần" .-> O1["Test observer"]
    F -. "test terminal output" .-> COL["QueueChannel / collector"]
    T -. "assert side effect" .-> CHECK["Test verification"]
    F -. "failure" .-> ERR["errorChannel / retry / DLQ"]
~~~

Ta có ít nhất ba vị trí đo output:

1. **Trước outbound adapter:** kiểm tra message mà adapter sắp nhận, ví dụ JSON DTO, routing key hoặc header file name.
2. **Sau một gateway có reply:** kiểm tra response message, status hoặc đối tượng kết quả.
3. **Tại hệ thống đích:** kiểm tra side effect như file, message broker record, HTTP request hoặc database row.

Một bài test ở vị trí (1) không thay được bài test ở vị trí (3). Chọn đúng vị trí theo câu hỏi nghiệp vụ.

## 4. Hợp đồng output phải được viết trước assertion

Ví dụ luồng nhận một đơn hàng từ file:

~~~text
Input:
  file orders-42.csv
  body: "orderId,total\n42,100\n"
  header: sourceSystem=sftp
  header: correlationId=corr-42

Expected internal output:
  payload: OrderEvent(orderId=42, total=100)
  header: eventId=order-42
  header: correlationId=corr-42

Expected external output:
  HTTP POST /orders với orderId=42
  HTTP 201 và externalId=ext-42

Failure behavior:
  CSV sai schema -> rejectedOrders
  HTTP 503 -> retry hữu hạn
  HTTP 400 -> lỗi nghiệp vụ, không retry mù quáng
~~~

Từ contract, xác định rõ:

| Thuộc tính | Điều cần khẳng định | Cạm bẫy |
|---|---|---|
| `payload.getClass()` | Kiểu Java đúng sau transformer | Dữ liệu là `byte[]` nhưng test so với `String` |
| Nội dung | Chuẩn hóa, schema, số tiền, encoding | So sánh JSON nguyên văn dù thứ tự field không quan trọng |
| Correlation | Giữ business ID xuyên flow | Nhầm `MessageHeaders.ID` do framework sinh với ID nghiệp vụ |
| Transport metadata | Filename, remote path, Kafka key, HTTP status | Assert header vốn không được cấu hình chuyển tiếp |
| Số lượng | Đúng N message tại đúng nhánh | Chỉ lấy message đầu, bỏ qua message thừa |
| Thứ tự | Có bảo đảm ở phạm vi nào? | Khẳng định thứ tự toàn cục trên nhiều thread/partition |
| Lỗi | Lỗi nằm ở caller, error flow hay broker? | Mọi exception đều được mặc định gửi tới `errorChannel` |
| Kết quả đích | Side effect hoàn tất hay chỉ queued/acknowledged? | Coi `send() == true` là business success |

Nếu nội dung có timestamp động hoặc UUID, hãy cố định clock/ID trong test hoặc chỉ kiểm tra format và quan hệ nghiệp vụ; đừng dùng một giá trị thay đổi không kiểm soát trong snapshot assertion.

## 5. Nhận biết channel trước khi thu message

Các loại channel có semantics khác nhau:

| Channel | Đặc điểm | Cách test output |
|---|---|---|
| `DirectChannel` | Dispatch đồng bộ tới một subscriber được chọn; exception có thể quay về caller | Gắn terminal handler/flow và assert kết quả; không coi là fan-out |
| `QueueChannel` | `PollableChannel`, giữ message để `receive(timeout)` | Điểm thu output đơn giản trong test |
| `PublishSubscribeChannel` | Phát cho các subscriber; có thể chuyển sang executor | Collector là một subscriber riêng; phải xử lý cleanup |
| `ExecutorChannel` | Consumer có thể chạy bất đồng bộ | Đợi message với timeout, không assert tức thì |
| `RendezvousChannel` | Ghép sender và receiver đồng bộ | Kiểm tra send/receive timeout |
| `PriorityChannel` | Dựa trên độ ưu tiên | Kiểm tra thứ tự theo priority thực sự cấu hình |
| Kênh từ broker | Có ack, transaction, redelivery, partition/consumer group | Integration test với transport thích hợp |

**Không đăng ký collector như một subscriber mới vào `DirectChannel` của production rồi mong nó nhận bản sao message.** `DirectChannel` có semantics lựa chọn một subscriber; observer có thể trở thành **consumer cạnh tranh** và làm hỏng bài test hoặc thay đổi hành vi thật. Khi muốn nhân bản để quan sát, sử dụng `WireTap`/`PublishSubscribeChannel` đúng cấu hình hoặc đặt terminal output riêng trong test.

### 5.1. Timeout và receiver

`PollableChannel.receive(timeoutMillis)` chờ tối đa thời gian được cung cấp. Đối với `QueueChannel`, `receive(0)` không đợi; `receive(1000)` chờ có giới hạn; **tránh `receive()` không timeout trong test** vì có thể treo khi flow lỗi.

Một call `receive(0) == null` chỉ nói rằng **tại thời điểm này** queue trống; nó chưa chứng minh không có message đến muộn. Muốn test “không bao giờ có output” trong khoảng hạn định, phải dùng cửa sổ quan sát, đếm các message và đảm bảo flow đã kết thúc/đang ổn định.

## 6. MessageCollector trong Spring Cloud Stream test support cũ

Ở một số dự án dùng mô hình annotation-based của Spring Cloud Stream, test binder cũ cung cấp `MessageCollector` và API:

~~~java
// Dành cho Spring Cloud Stream phiên bản cũ có test-support:
@Autowired
private org.springframework.cloud.stream.test.binder.MessageCollector collector;

@Autowired
private org.springframework.cloud.stream.messaging.Processor processor;

@Test
void collectsLegacyOutput() throws InterruptedException {
    processor.input().send(new GenericMessage<>("hello"));

    Message<?> result = collector
            .forChannel(processor.output())
            .poll(2, TimeUnit.SECONDS);

    assertNotNull(result);
    assertEquals("HELLO", result.getPayload());
}
~~~

Đoạn trên minh họa **thân bài test**. Để chạy trong dự án legacy phải có cấu hình `@EnableBinding(Processor.class)`, flow xử lý input→output và dependency test binder phiên bản tương ứng, chẳng hạn `spring-cloud-stream-test-support`. Các import khác gồm `Message`, `GenericMessage`, `TimeUnit`, `@Autowired` và `@Test`.

Ý tưởng của `forChannel(channel)`: trả về queue lưu các message phát ra ở **outbound binding** đang được test binder quản lý. Nó **không tự động quan sát mọi `MessageChannel` bất kỳ** trong một ứng dụng Spring Integration.

**Cảnh báo phiên bản:** mô hình `@EnableBinding`/`@StreamListener` và test binder cũ với `MessageCollector` đã bị thay thế trong Spring Cloud Stream hiện đại. Không nên sao chép đoạn ví dụ legacy vào ứng dụng Spring Integration Java DSL mới rồi cố tìm lớp `MessageCollector` trên classpath.

### 6.1. Điều test legacy có thể và không thể chứng minh

- **Có thể:** message đi qua function/processor và xuất hiện ở outbound binding do test binder quản lý.
- **Có thể:** payload/header mong đợi, một hoặc nhiều output, các branch do binder giả lập hỗ trợ.
- **Không thể chỉ từ collector:** Kafka record được commit, RabbitMQ exchange đã route, filesystem/SFTP có file, ứng dụng downstream đã xử lý.
- **Không nên:** dùng output queue của collector chung giữa các test nhưng không dọn, rồi lấy message cũ làm kết quả.

## 7. Cách tương ứng trong Spring Cloud Stream hiện đại: OutputDestination

Khi ứng dụng dùng Spring Cloud Stream function bindings, **Spring Integration Test Binder** mô phỏng các destination bằng channel trong JVM. Hai API thường dùng:

- `InputDestination.send(message, destinationName)` để gửi đầu vào giả lập.
- `OutputDestination.receive(timeoutMillis, destinationName)` để nhận message được publish qua binding.

Dependency test điển hình:

~~~xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-stream-test-binder</artifactId>
  <scope>test</scope>
</dependency>
~~~

Ở những dòng Spring Cloud Stream, có thể phải dùng `@Import(TestChannelBinderConfiguration.class)`; những tài liệu/phát hành mới hơn có `@EnableTestBinder`. **Dùng cơ chế kích hoạt tương ứng phiên bản đang chạy**, không trộn cấu hình test binder đời cũ và mới.

Ví dụ test với function `uppercase`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

@SpringBootTest(classes = StreamOutputTest.StreamTestApp.class)
@Import(TestChannelBinderConfiguration.class)
class StreamOutputTest {

    @Autowired InputDestination input;
    @Autowired OutputDestination output;

    @Test
    void receivesTheExpectedOutboundBindingMessage() {
        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);

        input.send(new GenericMessage<>(bytes), "uppercase-in-0");

        Message<byte[]> result = output.receive(2000, "uppercase-out-0");
        assertNotNull(result);
        assertEquals("HELLO",
                new String(result.getPayload(), StandardCharsets.UTF_8));
    }

    @SpringBootApplication
    static class StreamTestApp {
        @Bean
        Function<String, String> uppercase() {
            return value -> value.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

Ví dụ mang tính hướng dẫn cho dòng Spring Cloud Stream hỗ trợ `TestChannelBinderConfiguration`; với phiên bản yêu cầu `@EnableTestBinder`, điều chỉnh annotation theo tài liệu phiên bản đó. Nếu tự đặt `destination` khác tên binding, dùng **tên destination thực** trong `send`/`receive`, không mặc nhiên dùng `uppercase-in-0` và `uppercase-out-0`.

**Quan trọng:** đây là test cho **Spring Cloud Stream binding**, không phải cách thay thế tự động mọi outbound adapter/gateway của Spring Integration. Test binder in-memory không mô phỏng tất cả behavior của Kafka/JMS/AMQP thật (ack, partition, rebalance, broker transaction).

## 8. Spring Integration thuần: QueueChannel là collector đơn giản nhất

Với `IntegrationFlow` và `MessageChannel`, cách dễ kiểm soát nhất là cho flow trong **test context** ghi kết quả vào một `QueueChannel`. Đây là collector về mặt **khái niệm**; không cần lớp `MessageCollector` của Spring Cloud Stream.

Ví dụ **tự chứa** về luồng normalize payload:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OutputChannelTest.FlowConfig.class)
class OutputChannelTest {

    @Configuration
    @EnableIntegration
    static class FlowConfig {

        @Bean("inputChannel")
        MessageChannel inputChannel() {
            return new DirectChannel();
        }

        @Bean("observedOutput")
        PollableChannel observedOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow normalizeFlow() {
            return IntegrationFlow.from("inputChannel")
                    .<String, String>transform(String::trim)
                    .channel("observedOutput")
                    .get();
        }
    }

    @Autowired
    @Qualifier("inputChannel")
    MessageChannel input;

    @Autowired
    @Qualifier("observedOutput")
    PollableChannel output;

    @Test
    void collectsPayloadAndBusinessHeaders() {
        Message<String> request = MessageBuilder
                .withPayload("  order-42  ")
                .setHeader("correlationId", "corr-42")
                .setHeader("sourceSystem", "file")
                .build();

        assertTrue(input.send(request));

        Message<?> actual = output.receive(1000);
        assertNotNull(actual);
        assertEquals("order-42", actual.getPayload());
        assertEquals("corr-42", actual.getHeaders().get("correlationId"));
        assertEquals("file", actual.getHeaders().get("sourceSystem"));
        assertNull(output.receive(0));
    }
}
~~~

**Bài test chứng minh** message được gửi vào channel, transformer chạy và output thu được có nội dung cùng header đúng. Vì đây là `QueueChannel` ở **cuối flow test**, việc test nhận message không làm một consumer thật khác bị mất message.

**Bài test chưa chứng minh** một inbound adapter đã đọc file/SFTP đúng, hay outbound adapter đã gửi tới server/broker/database. Nếu module yêu cầu kiểm thử toàn ranh giới adapter, cần bổ sung test giao thức và kiểm tra side effect.

### 8.1. Khi nào không thay flow output bằng QueueChannel?

Nếu flow production có `DirectChannel` nối trực tiếp outbound handler trong cùng transaction, việc thay đích thành queue có thể làm khác thời điểm exception, commit/rollback và side effect. Giữ test ở trên cho **logic và wiring**; làm thêm integration test giữ đường production để xác minh các semantics quan trọng.

### 8.2. Vì sao test có thể treo hoặc nhận nhầm message?

- `receive()` không timeout trên queue trống có thể chờ vô hạn.
- Một poller/consumer khác đọc cùng queue trước test sẽ làm kết quả `null`.
- Queue sống qua nhiều test method nhưng không được dọn có thể giữ output từ lượt trước.
- Bài test thứ hai chạy song song với bài thứ nhất trên cùng channel có thể nhận nhầm correlation ID.

Cách khắc phục: dùng test context/queue riêng hoặc isolation rõ, đặt timeout hữu hạn, gắn business ID duy nhất và cleanup đúng lifecycle.

## 9. Tự viết collector cho test: MessageHandler và BlockingQueue

Không phải dự án nào cũng cần phụ thuộc test binder. Một collector nhỏ là `MessageHandler` nhận message và cất vào `BlockingQueue`. Nó hữu ích khi test cần tự kiểm soát danh sách kết quả, số lượng, thứ tự và thời hạn nhận.

~~~java
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

final class CapturedOutput implements MessageHandler {

    private final BlockingQueue<Message<?>> messages =
            new LinkedBlockingQueue<>();

    @Override
    public void handleMessage(Message<?> message) {
        messages.add(message);
    }

    Message<?> next(Duration timeout) throws InterruptedException {
        return messages.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    List<Message<?>> drain() {
        List<Message<?>> result = new ArrayList<>();
        messages.drainTo(result);
        return result;
    }

    void clear() {
        messages.clear();
    }
}
~~~

Để collector hoạt động, phải **kết nối nó tới đúng điểm nhận message** trong test. Ví dụ khi có một `PublishSubscribeChannel` dành cho output:

~~~java
CapturedOutput collector = new CapturedOutput();

// fixture đã khai báo PublishSubscribeChannel resultEvents
resultEvents.subscribe(collector);
try {
    // Kích hoạt flow rồi chờ kết quả.
    Message<?> first = collector.next(Duration.ofSeconds(2));
    assertNotNull(first);
    assertEquals("processed", first.getHeaders().get("processingStatus"));
}
finally {
    resultEvents.unsubscribe(collector);
}
~~~

Ví dụ này minh họa phần kiểm tra/cleanup; `resultEvents` là bean/fixture thuộc test context. Việc dùng `BlockingQueue` **không làm kết quả bền vững qua restart**; đây chỉ là công cụ in-memory dành cho test.

**Không gắn collector mới vào `DirectChannel` vốn đã có consumer nghiệp vụ** vì nó có thể lấy mất message. Với `PublishSubscribeChannel`, collector nhận message trên nhánh fan-out, nhưng việc collector đã nhận không chứng minh subscriber outbound cũng xử lý xong. Nếu collector được gắn vào luồng có payload mutable, cần tránh giữ tham chiếu tới object bị sửa bởi subscriber khác.

### 9.1. Vì sao không dùng ArrayList thường để thu message bất đồng bộ?

Nếu producer ghi trên executor thread nhưng test thread đọc `ArrayList` không có đồng bộ, sẽ có data race, visibility lỗi hoặc kết quả flakiness. `BlockingQueue`, `ConcurrentLinkedQueue` kết hợp latch hoặc công cụ đồng bộ khác thích hợp hơn. Vẫn phải định nghĩa **điều kiện đã xử lý xong**; queue có message chỉ là một phần của kết quả.

### 9.2. Lưu ý khi nhận nhiều output

`drain()` lấy những message **đã xuất hiện tới thời điểm gọi**; với luồng bất đồng bộ, vẫn có thể có message đến sau. Muốn chờ đúng N kết quả, gọi `next(timeout)` N lần hoặc dùng latch/await cho đến khi điều kiện nghiệp vụ được thỏa. Sau khi có đủ N, kiểm tra cửa sổ ổn định hoặc signal hoàn tất nếu yêu cầu bảo đảm không có message thừa.

## 10. Dùng MockIntegrationContext để kiểm tra output trước adapter thật

`spring-integration-test` hỗ trợ `@SpringIntegrationTest` và `MockIntegrationContext`. Khi cần test flow mà không gọi SFTP/HTTP/broker thật, có thể **thay handler của endpoint outbound bằng mock** để bắt message ở ranh giới trước khi đi ra ngoài.

Sơ đồ:

~~~mermaid
flowchart LR
    IN["Input MessageChannel"] --> F["Parser / Transformer / Router"]
    F --> C["outboundChannel"]
    C --> M["MockMessageHandler trong test"]
    C -. "production" .-> R["Real outbound adapter"]
    M --> A["ArgumentCaptor và assertions"]
~~~

Ví dụ ý tưởng từ API test support:

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

import static org.springframework.integration.test.mock.MockIntegration
        .mockMessageHandler;

// Trong test có @SpringJUnitConfig và @SpringIntegrationTest:
@Autowired
MockIntegrationContext mockIntegrationContext;

@AfterEach
void restoreEndpoint() {
    mockIntegrationContext.resetBeans();
}

@Test
void capturesTheMessageBeforeExternalSend() {
    ArgumentCaptor<Message<?>> captor =
            ArgumentCaptor.forClass(Message.class);

    MessageHandler mockHandler =
            mockMessageHandler(captor);

    mockIntegrationContext.substituteMessageHandlerFor(
            "partnerOutboundEndpoint", mockHandler);

    // fixture cung cấp inputChannel; kích hoạt flow.
    inputChannel.send(new GenericMessage<>("order-42"));

    Message<?> captured = captor.getValue();
    assertEquals("order-42", captured.getPayload());
}
~~~

**Các giả định bắt buộc:** `partnerOutboundEndpoint` là **ID của consumer endpoint** có thể được thay, không phải tên bất kỳ của channel; test được cấu hình `@SpringIntegrationTest`; flow đồng bộ đủ để kết quả có sẵn ngay, nếu không phải chờ. Cú pháp overload của mock factory và việc captor loại `Message<?>` có thể cần điều chỉnh theo version Mockito/Spring Integration cụ thể. Khi không cần capture nguyên message, có thể dùng mock handler kết hợp `Mockito.verify(...)`.

Lợi ích: không cần kết nối thật để kiểm tra **thông điệp ngay trước outbound adapter**. Giới hạn: vì adapter thật đã bị thay, test **chưa kiểm tra** serialization đặc thù adapter, HTTP status, SFTP upload, Kafka publish ack hoặc database transaction. Cần một integration test khác giữ adapter thật.

**Không quên `resetBeans()`** sau test; nếu không mock có thể tồn tại qua các test dùng chung Spring context, tạo kết quả không đáng tin.

## 11. WireTap: quan sát mà không tiêu thụ message chính

`WireTap` có thể chuyển **bản message quan sát** tới một channel phụ trong khi đường chính tiếp tục. Đây là lựa chọn khi muốn giữ flow gần production hơn thay vì lấy message từ một channel mà consumer đang dùng.

~~~mermaid
flowchart TD
    A["Inbound adapter"] --> C["DirectChannel chính"]
    C --> H["Business handler"]
    C -. "WireTap interceptor" .-> Q["Probe QueueChannel"]
    H --> O["Outbound adapter"]
    Q --> T["Test assertions"]
~~~

Một cấu hình ý tưởng trong Java DSL có thể đặt wire tap vào đúng điểm cần quan sát, đưa bản sao sang `probeChannel`, rồi test dùng `receive(timeout)` trên probe. Kiểm tra API cấu hình cụ thể theo phiên bản Spring Integration và **không gắn wire tap nhiều lần** nếu context được tái sử dụng.

Phân biệt:

- `WireTap` **quan sát** message khi đi qua một channel, không chứng minh handler sau nó hoàn tất.
- `PublishSubscribeChannel` có **fan-out như một phần semantics của flow**; test thêm subscriber có thể ảnh hưởng latency/lỗi nếu đồng bộ.
- `QueueChannel` trên **nhánh chính** có thể thay đổi thứ tự và transaction nếu thêm vào topology.
- `MockIntegrationContext` **thay** endpoint thật, tiện test nội bộ nhưng bỏ qua side effect ngoài.

Với dữ liệu nhạy cảm, chỉ ghi/kiểm tra metadata cần thiết; không đổ toàn bộ token, mật khẩu hoặc payload cá nhân vào collector rồi in ra report khi test fail.

## 12. Assertion payload: String, byte[], JSON và DTO

Không phải mọi adapter trả về `String`. Ví dụ file inbound có thể trả `File` hoặc `byte[]`, HTTP/JMS/Kafka có thể chuyển kiểu qua message converter, database inbound có thể tạo `Map` hoặc DTO.

### 12.1. Với String

~~~java
Message<?> message = output.receive(1000);
assertNotNull(message);
assertInstanceOf(String.class, message.getPayload());
assertEquals("order-42", message.getPayload());
~~~

### 12.2. Với byte[]

~~~java
Message<?> message = output.receive(1000);
assertNotNull(message);
assertInstanceOf(byte[].class, message.getPayload());

byte[] bytes = (byte[]) message.getPayload();
assertArrayEquals("HELLO".getBytes(StandardCharsets.UTF_8), bytes);
~~~

Nếu contract cho phép những cách encode khác nhau, không so sánh byte bằng cách gọi `toString()` trên mảng (kết quả không phải nội dung). Giải mã bằng charset đã được quy định hoặc so sánh byte chính xác.

### 12.3. Với JSON

Ví dụ output có body:

~~~json
{"orderId":"42","status":"ACCEPTED","amount":100}
~~~

Nếu business contract không yêu cầu thứ tự field, nên parse JSON và so sánh trường:

~~~java
JsonNode json = objectMapper.readTree(
        (String) message.getPayload());

assertEquals("42", json.path("orderId").asText());
assertEquals("ACCEPTED", json.path("status").asText());
assertEquals(100, json.path("amount").asInt());
~~~

Đoạn trên giả định `objectMapper` thuộc test fixture và payload là `String`; nếu output là `byte[]`, dùng overload parse byte[]. Đừng so sánh hai chuỗi JSON nguyên văn khi thứ tự field không có ý nghĩa. Với schema nghiêm ngặt, test thêm các trường bắt buộc, null/missing, enum, số tiền và version schema.

### 12.4. Với DTO

~~~java
OrderEvent order = assertInstanceOf(
        OrderEvent.class, message.getPayload());

assertEquals("42", order.orderId());
assertEquals(100, order.amount());
~~~

`OrderEvent` là kiểu DTO minh họa của ứng dụng (ví dụ Java record); hãy tách kiểm thử mapper khỏi kiểm thử truyền message để khi lỗi có thể định vị đúng tầng.

## 13. Assertion header: provenance, correlation và metadata transport

Payload đúng nhưng header sai vẫn có thể làm router, gateway, broker hoặc handler downstream thất bại.

~~~java
Message<?> actual = output.receive(1500);
assertNotNull(actual);

assertEquals("corr-42",
        actual.getHeaders().get("correlationId"));
assertEquals("sftp",
        actual.getHeaders().get("sourceSystem"));
assertEquals("order.created",
        actual.getHeaders().get("eventType"));
~~~

Các header đặc biệt đáng kiểm tra:

| Header/metadata | Bài test |
|---|---|
| Business ID/correlation | Liên kết đúng request ↔ output, error ↔ request |
| Source filename/path | File nhận đúng từ folder hoặc remote path |
| Routing key/partition key | Message đi đúng destination/topic/partition theo policy |
| Content type | Converter áp dụng schema/encoding phù hợp |
| Reply/error channel | Có reply/error ở đúng nơi khi cấu hình yêu cầu |
| Timestamp | Thứ tự tương đối hoặc format, không snapshot cố định không kiểm soát |
| Security context | Không để token bí mật bị copy vào output/log không cần thiết |

**Không nên assert mọi header đều bằng message đầu vào**: transformer, gateway hoặc adapter có thể thêm, thay hoặc không chuyển tiếp một số header. Dùng những header được hợp đồng hoặc cấu hình adapter **bảo đảm**. `MessageHeaders.ID` và `TIMESTAMP` có thể được tái tạo khi xây message mới, vì vậy không nên coi ID do framework sinh là khóa business bền vững.

## 14. MessageCollector và kiểm tra nhiều output

Một input có thể sinh:

- Một output duy nhất sau transformer.
- Nhiều output sau splitter.
- Một output ở một trong nhiều nhánh sau router.
- Nhiều bản sao đến subscriber của `PublishSubscribeChannel`.
- Một output nghiệp vụ **và** một event audit/notification.
- Không có output vì filter từ chối, nhưng có metric hoặc error event.

### 14.1. Splitter: không chỉ kiểm message đầu

Giả sử một CSV gồm ba record, splitter tạo ba message. Bài test nên:

1. Gửi một input có `batchId`.
2. Nhận đủ **ba message** bằng timeout hữu hạn.
3. So sánh **tập business IDs** nếu thứ tự không được cam kết, hoặc so sánh theo thứ tự khi cấu hình bảo đảm.
4. Kiểm tra correlation/sequence headers được ứng dụng sử dụng.
5. Xác minh batch completion và chính sách xử lý record sai, nếu có.

Ví dụ khung kiểm tra:

~~~java
Set<String> receivedIds = new HashSet<>();

for (int i = 0; i < 3; i++) {
    Message<?> message = output.receive(2000);
    assertNotNull(message);
    receivedIds.add((String) message.getHeaders().get("orderId"));
}

assertEquals(Set.of("41", "42", "43"), receivedIds);
~~~

Đoạn minh họa giả định flow có đặt `orderId` vào header. Kiểm tra thêm `receivedIds.size() == 3` chưa đủ nếu cùng ID gửi hai lần và một ID bị thiếu: so sánh **tập kỳ vọng** và số message gốc.

### 14.2. Router: mỗi nhánh dùng collector riêng

Ví dụ:

~~~text
eventType=ORDER_CREATED -> ordersOutput
eventType=ORDER_FAILED  -> failuresOutput
eventType không hợp lệ -> error/reject policy
~~~

Dùng ba output channel riêng trong test; không thu chung rồi đoán theo thứ tự đến. Assert event đúng nhánh, các nhánh khác không nhận message ngoài hợp đồng. Trong luồng bất đồng bộ, đặt cửa sổ quan sát hoặc chờ tất cả endpoint hoàn tất trước khi kết luận “không có message”.

### 14.3. Publish-subscribe: cần phân biệt fan-out và competing consumer

Nếu contract yêu cầu hai handler **cùng** nhận event, dùng publish-subscribe thật và xác minh từng subscriber riêng. Nếu dùng queue point-to-point, một message chỉ nên được **một consumer** lấy. Kỳ vọng “collector và outbound đều lấy cùng message từ QueueChannel” là nhầm semantics.

## 15. Kiểm thử bất đồng bộ: chờ có kiểm soát, không sleep tùy tiện

Với `ExecutorChannel`, inbound poller, JMS/Kafka listener hoặc HTTP async, đầu ra có thể xuất hiện **sau khi hàm gửi trả về**. Viết:

~~~java
input.send(message);
assertNotNull(output.receive(0)); // dễ flaky nếu output đến sau
~~~

là không an toàn về timing.

Thay bằng:

~~~java
assertTrue(input.send(message));

Message<?> actual = output.receive(2000);
assertNotNull(actual, "Không nhận output trong thời hạn test");
assertEquals("order-42", actual.getPayload());
~~~

Nếu cần chờ **side effect không nằm trên QueueChannel**, dùng các công cụ chờ điều kiện như latch, Awaitility hoặc polling có deadline:

~~~java
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertEquals(1, repository.countByOrderId("42")));
~~~

Ví dụ giả định đã cấu hình Awaitility, `repository` thuộc test fixture và bài test kiểm tra DB test riêng. Tránh `Thread.sleep(5000)` rồi assert một lần; thời gian chạy CI hoặc scheduler có thể dao động.

### 15.1. Test output không xuất hiện

Khi filter được phép bỏ message, có thể kiểm tra:

~~~java
input.send(invalidMessage);
assertNull(rejectedOutput.receive(300));
~~~

Nhưng assertion này chỉ chứng minh không có message **trong 300 ms** ở channel đó, không bảo đảm sẽ không bao giờ có output. Kết luận mạnh hơn cần điều kiện hoàn tất của flow, signal xử lý xong hoặc test endpoint đồng bộ với quy trình đã xác định.

### 15.2. Bài test không nên chờ mãi

Đặt timeout hữu hạn và thông báo lỗi có correlation ID/destination; không log payload chứa secret. Khi một test có nhiều đoạn bất đồng bộ, phân bổ deadline hợp lý theo độ trễ hạ tầng test, không thêm hàng loạt timeout lớn làm suite chậm vô nghĩa.

## 16. Kiểm tra output của File inbound và File outbound

### 16.1. Inbound File: message nhận được không nhất thiết là nội dung file

Một **File inbound adapter** thường phát thông điệp có payload là đối tượng `File`; nội dung thành `String` hoặc `byte[]` thường do bước transformer sau đó xử lý. Test nên tách hai lớp:

- **Source/filter test:** thư mục được quét, file khớp pattern, tên file đúng, file đang ghi dở được xử lý theo quy ước.
- **Output collector test:** message sau transformer có đúng payload/header/correlation không; không phát sai thêm message.

Ví dụ contract:

~~~text
Filesystem:
  inbox/orders-42.csv
  inbox/ignore.tmp

Adapter source:
  chỉ nhận *.csv

Collector tại parsedOrders:
  payload OrderEvent(orderId=42, amount=100)
  headers sourceFileName=orders-42.csv, correlationId=corr-42
~~~

Cần biết chính xác adapter và transformer nào đặt header `sourceFileName`; đây là header **nghiệp vụ trong ví dụ**, không khẳng định File adapter luôn tự tạo cùng tên header.

Test một đường nhận:
 
1. Tạo thư mục tạm riêng bằng `@TempDir`, không sử dụng thư mục sản xuất.
2. Đặt đúng file test và file không phù hợp filter.
3. Khởi động poller có lịch ngắn riêng cho test.
4. Đọc từ collector bằng `receive(timeout)`.
5. Assert payload, metadata, số lần nhận.
6. Dừng poller, dọn trạng thái file/metadata store.

**Lưu ý:** pattern filter như `*.csv` **không tự bảo đảm accept-once**. Nếu điều kiện nghiệp vụ yêu cầu file chỉ được xử lý một lần, cần cấu hình filter/metadata store thích hợp và kiểm tra lại qua hai lần poll/restart.

### 16.2. Outbound File: collector chỉ là điểm trước khi ghi

Với File outbound adapter, có hai assertion độc lập:

~~~text
Trước outbound:
  outputCollector nhận message chứa nội dung mong đợi
  header targetFileName phù hợp chính sách

Tại đích:
  file output/orders-42.csv thật sự tồn tại
  nội dung file đúng byte/encoding
  không có file tạm còn sót nếu contract yêu cầu atomic move
~~~

Nếu test chỉ nhận message ở collector và **thay outbound handler bằng mock**, chưa thể chứng minh ghi file thành công. Một integration test dùng `@TempDir` làm output directory, gửi message qua **adapter thật**, rồi kiểm tra bằng `Files.exists` và `Files.readString` mới có bằng chứng side effect.

Các ca âm tính: đường dẫn không hợp lệ, thiếu quyền ghi, file cùng tên, append vs overwrite, file lớn, một phần nội dung bị ghi trước crash và quy tắc dọn file tạm.

## 17. SFTP: thu output sau bước đồng bộ và sau bước xử lý

SFTP inbound có thể thực hiện hai giai đoạn:

~~~mermaid
flowchart LR
    R["SFTP remote files"] --> SYNC["Remote synchronizer"]
    SYNC --> LOCAL["Local staging directory"]
    LOCAL --> SOURCE["File inbound source"]
    SOURCE --> CHANNEL["MessageChannel"]
    CHANNEL --> COL["Collector"]
    CHANNEL --> PARSER["Parser/validator"]
~~~

**Collector tại channel chỉ chứng minh file đã được đưa vào message flow**, không chứng minh:

- Remote file đã được tải đủ byte.
- Filter tránh nhận lại file sau restart.
- File chưa hoàn tất upload đã được nhận hay chưa.
- Quy trình downstream đã xử lý thành công.
- Remote file được xóa/đổi tên theo policy.

Muốn test SFTP inbound thực tế, dùng SFTP server cô lập/container với tài khoản và host key riêng; đặt file remote, chờ local sync rồi kiểm tra collector và kết quả downstream. Không dùng credential thật, không tắt SSH host-key validation để test xanh.

Với SFTP outbound, collector trước adapter chỉ cho biết message chuẩn bị gửi; test end-to-end phải **đọc lại file ở remote path**, so sánh nội dung/hash phù hợp và kiểm tra trạng thái khi connection timeout/partial upload. Một request upload trả success có thể cần thêm kiểm tra rename/temporary suffix theo contract.

Các tình huống cần thêm:

| Tình huống | Điều cần kiểm tra |
|---|---|
| File remote chưa hoàn tất | Không phát output xử lý nhầm dữ liệu nửa chừng |
| Mất kết nối khi tải | Lỗi có đường recovery, không phát message “đã hoàn tất” giả |
| Poll lại | Không nhân đôi output ngoài chính sách |
| Restart ứng dụng | Metadata store/remote filter hoạt động như thiết kế |
| Sai host key | Kết nối bị từ chối, log không lộ secret |
| Upload trùng tên | Overwrite/rename/skip theo hợp đồng được kiểm tra tại server |

## 18. HTTP gateway: collector có thể nhận request hay reply

HTTP có hai hướng test khác nhau.

### 18.1. Inbound HTTP gateway

Lời gọi HTTP đi vào ứng dụng, gateway tạo message đưa tới flow và chờ reply. Kiểm thử phải gửi **HTTP request thật tới endpoint test**, không chỉ tạo `GenericMessage`, nếu mục tiêu là kiểm tra mapping HTTP.

Ví dụ:

~~~text
POST /api/orders
Content-Type: application/json
X-Correlation-Id: corr-42
Body: {"orderId":"42","amount":100}

Collector sau inbound gateway:
  payload tương ứng dữ liệu order
  correlationId được map theo cấu hình

HTTP response:
  status=201
  body={"accepted":true}
~~~

Test cần kiểm tra payload/header ở channel và status/body ở HTTP response. Trường hợp thiếu header/bad JSON/timeout/no reply phải có hành vi xác định. **Collector nhận một message không tự bảo đảm HTTP response đã được trả đúng.**

### 18.2. Outbound HTTP gateway

Một flow gửi message tới gateway; gateway gọi service bên ngoài rồi trả reply message về flow.

- **Mock server** (WireMock/MockWebServer) cho biết server nhận HTTP method, URI, headers và body gì.
- **Output collector sau gateway** cho biết reply đã được transform thành message đúng không.
- **Negative test** với 4xx/5xx/timeout chứng minh error mapping, retry/backoff và xử lý khi không có reply.

Ví dụ contract:

~~~text
Input message:
  payload orderId=42
  header correlationId=corr-42

Outbound HTTP:
  POST /shipments
  X-Correlation-Id: corr-42

Mock response:
  HTTP 201 {"shipmentId":"sh-42"}

Collector reply:
  payload shipmentId=sh-42
  correlationId=corr-42
~~~

**Không khẳng định gateway tự chuyển tiếp mọi header**. Nếu cần correlation qua HTTP, phải cấu hình header mapper hoặc transformer tương ứng và assert đúng contract.

### 18.3. Outbound HTTP adapter one-way

Nếu adapter là **one-way**, không có reply application-level như gateway. Muốn kiểm tra output, dùng collector trước adapter **và** xác minh mock HTTP server đã nhận request. Đợi reply từ một adapter không trả lời là sai hợp đồng.

## 19. JMS và AMQP: kiểm tra output cùng acknowledgement

JMS và AMQP (ví dụ RabbitMQ) có broker/session/container riêng. Collector in-memory có thể chứng minh **message nội bộ trước publish** hoặc **message đã vào flow sau consume**, nhưng không mô phỏng đầy đủ:

- Destination queue/topic hoặc exchange/routing key/binding.
- Publish confirm/return (AMQP) và tình trạng message không route được.
- Consumer acknowledgement, nack, reject, requeue, redelivery.
- Transaction commit/rollback và dead-letter routing.
- Ordering và cạnh tranh giữa nhiều consumer.

| Điểm test | Cần kiểm tra |
|---|---|
| Producer output collector | Payload, routing key, header cần publish |
| Broker test | Message có mặt ở destination thật đúng topology |
| Consumer input collector | Message được adapter chuyển vào đúng channel |
| Consumer business output | Kết quả nghiệp vụ hoặc side effect thành công |
| Error/retry collector | Lỗi có correlation, retry hữu hạn và DLQ/recovery phù hợp |

Ví dụ sự cố: Consumer nhận message, ghi database thành công rồi crash trước ack. Broker có thể redeliver; **collector nhận hai message không tự nghĩa là dữ liệu đã được nhân đôi**, nhưng consumer phải có idempotency để side effect không bị lặp ngoài ý định.

Với RabbitMQ, test publisher confirms/returns tại broker nếu chúng là một phần hợp đồng; một collector trước outbound không thể thay thế publisher confirm. Với JMS, dùng provider thử nghiệm phù hợp khi cần xác minh acknowledgement và redelivery.

## 20. Kafka: OutputDestination không thay Kafka broker thật

Spring Cloud Stream test binder hiện đại cung cấp `OutputDestination` để thu output của **binding**, nhưng nó chạy **trong JVM**, không phải cluster Kafka. Khi một ứng dụng có hai function output, test binder giúp kiểm tra payload/binding nhanh; khi nghiệp vụ phụ thuộc Kafka, cần kiểm tra riêng với broker thử nghiệm.

Các assertion quan trọng ở Kafka:

| Thuộc tính | Vì sao cần test? |
|---|---|
| Topic | Message phải tới topic đúng; tránh trộn tenant/môi trường |
| Record key | Ảnh hưởng partition và ordering cho cùng business key |
| Serializer/schema | Producer và consumer phải hiểu dữ liệu tương thích |
| Headers | Correlation, event type, version và dữ liệu cần thiết |
| Consumer group | Không lấy nhầm record cũ từ nhóm test khác |
| Offset/commit | Khi xử lý lỗi có replay/redelivery theo semantics |
| DLT/retry topic | Poison message không chặn consumer vô hạn |
| Sink result | Broker nhận record chưa đồng nghĩa nghiệp vụ đã xong |

Khi test output dùng `OutputDestination.receive(timeout, destination)`, **không khẳng định** rằng Kafka record đã được lưu/replicate hay consumer group production xử lý. Đó là test binding/flow. Bổ sung integration test với Kafka test container/embedded broker theo cấu hình gần ứng dụng, topic/group riêng và xác minh side effect.

Với nhiều partition, nếu không có điều kiện ordering toàn cục, **so sánh tập kết quả hoặc thứ tự theo một key/partition**, không assume thứ tự tuyệt đối toàn topic.

## 21. Database adapter: output collector và trạng thái bảng phải khớp

Một JDBC/JPA inbound polling adapter có thể:

1. Tìm record có `status=NEW`.
2. Biến record thành message, gửi vào channel.
3. Đánh dấu đã lấy/đang xử lý theo transaction.
4. Consumer tạo side effect ở hệ thống khác.

Collector tại output channel chứng minh record đã được đưa vào flow; **không bảo đảm transaction nguồn đã commit** hoặc đích đã xử lý.

Ví dụ test:

~~~text
Before:
  orders_outbox(id=42, status=NEW)

After poll:
  outputCollector: message(eventId=42, payload đúng)
  database: trạng thái NEW/IN_PROGRESS/PROCESSED đúng policy

After consumer:
  sink table: đúng một bản ghi/side effect
  audit: tương quan với eventId=42
~~~

Các negative test:

- Row bị lỗi schema → không đánh dấu đã xử lý thành công.
- Hai poller/instance song song → không cùng gây side effect trùng ngoài ý định.
- Downstream timeout → retry/rollback/compensation theo transaction boundary.
- Database connection mất → error/backoff; không phát output giả.
- Restart sau crash → có thể đọc lại row nhưng idempotent consumer tránh nhân đôi kết quả.

Nếu kiến trúc dùng transactional outbox, kiểm tra riêng **transaction ghi business data + outbox**, rồi kiểm tra publisher/consumer. Không giả định DB transaction có thể rollback HTTP hoặc SFTP đã thành công.

## 22. Poller, gateway, service activator và nơi thu message

| Thành phần | Điểm thu hợp lý | Điều chưa chứng minh nếu chỉ thu ở đó |
|---|---|---|
| File/DB inbound poller | Channel sau inbound adapter hoặc sau transformer | Trạng thái xử lý hoàn tất ở đích |
| SFTP synchronizer | Channel sau local file source, kèm trạng thái file | File remote đã được xóa/ack đúng |
| HTTP inbound gateway | Channel trong flow và HTTP response thực | Consumer bên ngoài response đã xử lý |
| HTTP outbound gateway | Reply channel sau gateway | Mọi side effect bên remote đã commit |
| Service activator | Channel sau activator hoặc mock handler ở endpoint | Adapter downstream đã giao thành công |
| Router | Collector từng nhánh | Mọi handler của nhánh đều hoàn tất |
| Splitter | Collector output, kiểm số lượng/sequence | Có aggregate/commit hoàn chỉnh |
| Aggregator | Output sau khi nhóm hoàn tất | Các message gốc đều độc lập thành công nếu không kiểm tra |

### 22.1. Điều khiển thời gian poller

Poller production có thể chạy mỗi phút hoặc mỗi giờ; không nên khiến test chờ nguyên lịch. Ở **test context**, có thể dùng lịch nhanh riêng, điều khiển `start()/stop()` của endpoint hoặc các test trigger khi phiên bản hỗ trợ.

Tài liệu Spring Integration có `@SpringIntegrationTest(noAutoStartup=...)` và `MockIntegrationContext` để kiểm soát endpoint. Một số phiên bản mới hỗ trợ thay trigger trong test. Khi sử dụng, **phải đặt đúng endpoint ID** và reset cấu hình sau test.

Đừng coi `maxMessagesPerPoll(1)` là “chỉ phát một message trong suốt test”; nó giới hạn số lần nhận **trên mỗi poll**, chứ poller có thể chạy nhiều lần.

### 22.2. Gateway và reply timeout

Với request–reply, test cả:

- Có reply đúng kiểu và đúng correlation.
- Không có reply trong thời gian giới hạn.
- Remote/gateway ném exception hoặc trả trạng thái lỗi.
- Reply đi sai channel hoặc reply mapping không phù hợp.
- Nhiều request đồng thời không lấy nhầm reply của nhau.

Để xác minh request–reply end-to-end, đừng chỉ thu message trên input channel của gateway; **assert giá trị trả về cho caller** hoặc response HTTP/JMS thực theo giao thức.

## 23. Error output, retry và kết quả thất bại

Một flow không chỉ có “success output”. Khi adapter hoặc handler gặp lỗi, message có thể:

- Khiến **caller đồng bộ** nhận exception.
- Được gửi tới **error channel** tùy loại endpoint/error handler.
- Được retry bởi advice/retry template hoặc middleware.
- Bị reject/nack/redeliver bởi broker listener.
- Được chuyển tới **DLQ/DLT** hoặc recoverer.
- Bị giữ trong một trạng thái chờ xử lý thủ công.

**Không giả định có bean `errorChannel` thì mọi exception trong mọi loại adapter sẽ tự tới đó.** Phải kiểm tra thread, adapter, poller, listener container và advice được cấu hình.

Ví dụ hợp đồng cho dữ liệu sai:

~~~text
Input message:
  payload="malformed-csv"
  correlationId="corr-err-42"

Expected:
  không có OrderEvent hợp lệ ở successOutput
  errorOutput có thông tin nhận diện lỗi
  correlationId/failedMessage còn truy xuất được khi có hỗ trợ
  không có HTTP POST gửi tới partner
  không retry vô hạn nếu lỗi do dữ liệu đầu vào
~~~

### 23.1. Test message trên error channel

Với một error flow được cấu hình chủ động và output test là `PollableChannel`:

~~~java
Message<?> error = errors.receive(2000);
assertNotNull(error);
assertInstanceOf(
        org.springframework.messaging.support.ErrorMessage.class,
        error);

// Tùy phiên bản/endpoint, payload là Throwable hoặc subclass.
Throwable failure = (Throwable) error.getPayload();
assertNotNull(failure.getMessage());
~~~

Đoạn code giả định `errors` đã được cấu hình để nhận `ErrorMessage` từ **đúng** endpoint bất đồng bộ. Với lỗi ở `DirectChannel` đồng bộ, một test phù hợp hơn có thể là `assertThrows(...)` trên caller.

Với `MessagingException`, một số trường hợp có thể truy cập `getFailedMessage()` để xác định input gây lỗi; không nên assume mọi Throwable luôn có thuộc tính này. Khi log hoặc assert, không in secret/token của input.

### 23.2. Một thành công và một thất bại không được nhầm nhau

Khi một bản ghi bị từ chối, test nên chứng minh **không có side effect ở đích**. Một collector error nhận message là hữu ích, nhưng nếu outbound adapter vẫn gửi dữ liệu lỗi, bài test phải thất bại. Điều này đặc biệt quan trọng với dữ liệu thanh toán, email thông báo hoặc webhook đối tác.

## 24. Xử lý message trùng, retry và idempotency

Các transport thực tế có thể giao message lại; một collector nhận hai message không nhất thiết là lỗi, nhưng **hai side effect nghiệp vụ không mong muốn** mới là điều cần ngăn.

Phân biệt:

| Hiện tượng | Mô tả | Test nên kiểm gì? |
|---|---|---|
| Retry | Thực hiện lại cùng operation sau lỗi tạm | Số lần, backoff, deadline và outcome |
| Redelivery | Broker gửi lại vì chưa ack/commit | Idempotent consumer và trạng thái ack |
| Duplicate input | Cùng business event đến từ nguồn nhiều lần | Business ID không bị xử lý sai hai lần |
| Replay | Dùng lại message từ DLQ/outbox/offset | Kết quả được khôi phục an toàn |
| Partial failure | Ghi đích xong nhưng lỗi trước ack | Không nhân đôi side effect qua retry |
| Poison message | Payload cố định gây lỗi mỗi lần | Bị cách ly/DLQ, không chặn hệ thống vô hạn |

Ví dụ:
 
~~~text
Lần 1: HTTP POST /shipments(orderId=42) -> timeout
Server: thực tế đã tạo shipment sh-42
Lần 2: retry cùng orderId=42 -> server thấy idempotency key
Expected: chỉ có một shipment, kết quả được liên kết về orderId=42
~~~

Để test đầy đủ, mock server có thể mô phỏng **thao tác đã thành công nhưng response bị mất**; collector sau retry chỉ phản ánh output cuối cùng. Kiểm tra thêm **số side effect tại server/DB**, vì số HTTP requests có thể lớn hơn một theo thiết kế retry.

### 24.1. “Không có message thừa” phải được định nghĩa rõ

Nếu flow có thể gửi message lại sau timeout, gọi `output.receive(0)` một lần không đủ để kết luận không có duplicate. Tùy contract, có thể:

- Kiểm tra business sink chỉ có một row.
- Đợi flow phát signal hoàn tất rồi đếm output.
- Kiểm soát lịch retry và quan sát trong một cửa sổ đủ quy định.
- Dùng unique event ID và collection của mọi attempt để giải thích kết quả.

Không yêu cầu collector giữ vai trò “exactly once” mà thực tế transport không cam kết. Thiết kế **idempotency ở consumer** khi luồng có khả năng giao ít nhất một lần.

## 25. Isolation: dọn collector, context và message tồn dư

Một bài test output có thể xanh hoặc đỏ ngẫu nhiên nếu collector/queue sống chung giữa nhiều test.

### 25.1. Các vấn đề thường gặp

- `QueueChannel` giữ message từ test trước.
- `PublishSubscribeChannel` vẫn đăng ký handler collector sau khi test kết thúc.
- `MockIntegrationContext` chưa `resetBeans()`, nên outbound adapter thật không được khôi phục.
- Poller/JMS/Kafka listener của test trước vẫn chạy và tiếp tục đẩy message.
- Hai test song song chia sẻ một topic, consumer group hoặc tên file.
- Bộ nhớ chứa payload mutable; test đọc nó sau khi thread khác đã sửa.
- OutputDestination của test binder còn message cũ do dùng chung application context.

### 25.2. Quy tắc dọn an toàn

| Tài nguyên | Phương pháp |
|---|---|
| Collector tự viết | `clear()` sau test và kiểm tra queue không bị consumer khác dùng |
| QueueChannel | Drain có kiểm soát hoặc dùng context/queue riêng từng test |
| Pub/sub subscriber | `unsubscribe(handler)` trong `finally`/`@AfterEach` |
| MockIntegrationContext | `resetBeans()` sau thay endpoint |
| Inbound adapter/poller | Kiểm soát start/stop, hủy session/threads đúng lifecycle |
| File | `@TempDir`, kiểm tra output dir trống trước khi chạy |
| HTTP mock server | Đặt port ngẫu nhiên, reset request journal |
| Kafka/Rabbit/JMS | Topic/queue/group test riêng; cleanup hoặc test namespace độc lập |
| Database | Rollback khi phù hợp, truncate/test schema riêng; không phụ thuộc state cũ |

**Tránh mặc định `@DirtiesContext` cho mọi test.** Nó giúp tách context khi cấu hình/bean bị thay đổi khó phục hồi, nhưng tạo overhead đáng kể. Ưu tiên cleanup chính xác; dùng context isolation khi không thể bảo đảm reset.

### 25.3. Khi kết quả flakey

Một cách điều tra có trình tự:

1. In correlation ID, tên channel, deadline và số message đã nhận (không in secret).
2. Kiểm tra flow đã subscribe handler và endpoint đang running.
3. Kiểm tra thời điểm producer, poller, consumer và assertion.
4. Xem có competing consumer hoặc publisher không.
5. Kiểm tra queue/topic/file/DB có dữ liệu cũ.
6. Kiểm tra mock server/broker/test container đã ready.
7. Xác định output collector có nằm trước hay sau tác động ở đích.
8. Kiểm tra race do test song song, subscriber chưa cleanup hoặc policy retry.

Không chỉ tăng timeout từ 2 giây lên 60 giây mà bỏ qua lỗi wiring, deadlock hoặc endpoint bị stop.

## 26. Case study: File/SFTP inbound → xử lý đơn hàng → HTTP outbound

Giả sử một hệ thống nhận file CSV từ SFTP, parse đơn hàng, gọi API của đối tác qua HTTP gateway và ghi trạng thái vào database.

~~~mermaid
flowchart LR
    R["SFTP remote directory"] --> SYNC["SFTP synchronizer"]
    SYNC --> FILE["Local File inbound poller"]
    FILE --> IN["ordersInput"]
    IN --> PARSE["CSV parser / validator"]
    PARSE --> VALID["validOrders"]
    VALID --> HTTP["HTTP outbound gateway"]
    HTTP --> RESULT["ordersResult"]
    RESULT --> DB["Database writer"]
    PARSE -. "invalid data" .-> REJECT["rejectedOrders"]
    HTTP -. "transport error" .-> RETRY["Retry / recovery"]
    VALID -. "test collector" .-> OBS["Observed messages"]
~~~

### 26.1. Contract

Input fixture:

~~~text
remote file: orders-42.csv
content:
  orderId,total
  42,100

Expected internal message:
  payload OrderEvent(orderId=42,total=100)
  header correlationId=order-42
  header sourceFile=orders-42.csv

Expected HTTP:
  POST /shipments
  {"orderId":"42","total":100}
  X-Correlation-Id: order-42

Expected reply:
  shipmentId=sh-42

Expected database:
  orderId=42, shipmentId=sh-42, status=SUBMITTED
~~~

### 26.2. Thiết kế collector theo tầng

| Collector/observation | Nhận dữ liệu gì? | Chứng minh |
|---|---|---|
| `ordersInput` | File message sau inbound adapter | Poller đã phát file vào channel |
| `validOrders` / wire tap | DTO + correlation | Parse/validate thành công, routing đúng |
| `rejectedOrders` | Thông tin lỗi CSV | Lỗi dữ liệu đi nhánh reject |
| `ordersResult` | Reply từ HTTP gateway | Response đã được chuyển về flow |
| Mock HTTP server | Request body/headers | HTTP outbound thật sự được gửi |
| Database test | Row trạng thái cuối | Tác động nghiệp vụ cuối cùng hoàn tất |

### 26.3. Danh sách test

1. File hợp lệ → đúng một DTO trên collector, một HTTP request, một row kết quả.
2. File không phù hợp filter → không đi vào luồng; không gọi HTTP.
3. CSV thiếu cột → nhận reject output, không tạo shipment.
4. HTTP 201 → reply đúng `shipmentId` và correlation.
5. HTTP 400 → lỗi nghiệp vụ được ghi nhận, không retry nếu chính sách quy định.
6. HTTP 503 rồi 201 → retry đúng số lần và kết quả cuối đúng.
7. Timeout khi server thực sự đã ghi → idempotency giữ một shipment.
8. Hai file cùng `orderId` → không nhân đôi side effect ngoài quy định.
9. Poller restart → metadata filter/dedup xử lý đúng.
10. SFTP mất kết nối rồi phục hồi → không có message giả/thiếu, có log và recovery.
11. DB lỗi sau HTTP thành công → luồng bù trừ/khôi phục, không giả định rollback HTTP.
12. Gateway không có reply → timeout/error có deadline rõ ràng.
13. Hai test chạy song song → dữ liệu, remote path, mock server và DB không trộn nhau.

### 26.4. Nhận diện kết luận thiếu bằng chứng

Nếu test chỉ assert `validOrders.receive(...) != null`, mới chứng minh parser và routing **trước HTTP**. Nếu test chỉ thấy HTTP request đến mock server, chưa chứng minh DB đã ghi. Nếu DB row có sẵn từ test trước, kết luận cũng không hợp lệ. Mỗi test cần có **dữ liệu đầu vào độc lập và kết quả đích quan sát được**.

## 27. Ma trận kiểm thử output theo loại adapter

| Loại adapter | Output collector phù hợp | Kiểm tra bắt buộc ngoài collector |
|---|---|---|
| File inbound | Queue/wire tap sau source hoặc parse | File filter, duplicate, encoding, lifecycle |
| File outbound | Collector trước handler | File thực, tên/nội dung, quyền ghi, overwrite policy |
| SFTP inbound | Channel sau synchronizer/file source | Remote sync, host key, reconnect, accept-once |
| SFTP outbound | Collector trước sender | Remote file và trạng thái upload/rename |
| HTTP inbound gateway | Channel sau mapping HTTP | HTTP response, status, headers, timeout |
| HTTP outbound gateway | Reply channel sau gateway | Mock server nhận đúng request, retry/error |
| JMS inbound/outbound | Channel ngay cạnh adapter | Broker ack/transaction/redelivery |
| AMQP/RabbitMQ | Channel gần adapter | Exchange/binding, confirm, nack/DLQ |
| Kafka | OutputDestination (nếu Stream) hoặc channel SI | Topic/key/schema/offset/partition/sink result |
| JDBC/JPA polling | Queue sau mapper/handler | Transaction, row status, concurrent poll |
| Service activator | Terminal output channel/mock handler | Side effect thật nếu có external dependency |

Mục đích của bảng: **đặt collector ở nơi ranh giới hợp đồng trở nên quan sát được**, đồng thời không che giấu điều gì **chưa được test**.

## 28. Các anti-pattern khi dùng MessageCollector và kiểm tra output

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Import legacy `MessageCollector` vào Spring Integration thuần | Sai dependency hoặc API không có | `QueueChannel`/collector riêng/`MockIntegrationContext` |
| Dùng `MessageCollector` của binder cũ cho app Stream mới | API đã bị thay thế | `InputDestination`/`OutputDestination` |
| Coi collector có message là outbound success | Không thấy lỗi I/O hoặc downstream | Test side effect ở đích |
| Dùng collector như consumer thứ hai trên `DirectChannel` | Cạnh tranh lấy message | Dùng wire tap, pub/sub đúng semantics hoặc channel test riêng |
| `receive()` không timeout | Test treo khi thiếu output | `receive(timeout)` |
| Chỉ assert message đầu | Bỏ qua output thừa hoặc thiếu nhánh | Kiểm số lượng, tập business IDs, completion |
| So sánh mọi header theo snapshot | Hỏng test khi ID/timestamp framework thay đổi | Assert header thuộc contract |
| So sánh byte[] bằng `toString()` | Không kiểm nội dung | `assertArrayEquals` hoặc UTF-8 decode |
| Assert `null` ngay sau send bất đồng bộ | Có thể message đến muộn | Dùng deadline và completion signal |
| Không dọn collector/subscriber | Nhận nhầm output test cũ | Teardown/reset/context isolation |
| Mock cả flow, rồi tuyên bố đã test Kafka/SFTP | Không chạy protocol thật | Test adapter tích hợp có hạ tầng ngoài |
| Dùng một correlation ID cho cả suite | Không phân biệt test/song song | ID duy nhất theo test run |
| Retry nhưng không test idempotency | Side effect bị nhân đôi | Test duplicate, replay, partial failure |
| Collector giữ token/PII nguyên văn trong log | Rò bí mật qua report/CI | Redact và giới hạn metadata |

## 29. Checklist nghiệm thu và bài tập tự kiểm tra

### Checklist

- [ ] Xác định dự án dùng Spring Integration thuần hay Spring Cloud Stream.
- [ ] Nếu tài liệu yêu cầu `MessageCollector`, xác nhận đó là **test binder legacy** và version tương ứng.
- [ ] Chọn collector phù hợp: `QueueChannel`, terminal handler, wire tap, mock handler hoặc `OutputDestination`.
- [ ] Không làm thay đổi semantics production ngoài phạm vi bài test đang tuyên bố.
- [ ] Có timeout hữu hạn, fixture và correlation ID độc lập.
- [ ] Assert payload đúng kiểu, encoding/schema và các header nghiệp vụ cần thiết.
- [ ] Assert số lượng, routing, thứ tự theo phạm vi bảo đảm và output không mong muốn.
- [ ] Với outbound, có bằng chứng side effect tại hệ thống đích.
- [ ] Với gateway, có assertion reply/status/timeout, không chỉ input message.
- [ ] Với poller, có kiểm soát lịch chạy, duplicate và restart.
- [ ] Với broker, kiểm tra ack/offset/redelivery khi đó là contract.
- [ ] Có negative test cho lỗi dữ liệu, timeout và retry.
- [ ] Có cleanup collector, endpoint, subscriber và dữ liệu test.
- [ ] Đã ghi rõ những điều đã test và điều chưa chứng minh.

### Tình huống A

**Câu hỏi:** Một project Spring Integration thuần không tìm thấy lớp `MessageCollector`. Có nên thêm toàn bộ Spring Cloud Stream legacy test support?

**Trả lời:** Không mặc định. Hãy dùng `QueueChannel` hoặc collector handler/`MockIntegrationContext` của Spring Integration. `MessageCollector` thuộc test binder cũ của Spring Cloud Stream.

### Tình huống B

**Câu hỏi:** Test dùng `OutputDestination.receive(...)` thấy message trên binding `orders-out-0`. Điều đó chứng minh Kafka đã lưu record?

**Trả lời:** Không. Test binder chạy trong JVM, mô phỏng binding. Cần integration test riêng với Kafka để kiểm tra publish, key, topic, offset và xử lý ở đích.

### Tình huống C

**Câu hỏi:** Thêm một handler collector vào `DirectChannel` có sẵn outbound adapter, đôi khi collector nhận còn outbound không nhận. Tại sao?

**Trả lời:** `DirectChannel` không phát cùng message đến mọi subscriber; collector trở thành consumer cạnh tranh. Dùng wire tap hoặc một nhánh fan-out đúng semantics.

### Tình huống D

**Câu hỏi:** `QueueChannel.receive(0)` trả null sau khi gửi message vào `ExecutorChannel`. Kết luận message mất?

**Trả lời:** Chưa. Output có thể đến sau; cần chờ có timeout, kiểm tra handler đang hoạt động, error flow và lifecycle.

### Tình huống E

**Câu hỏi:** HTTP outbound gateway nhận 201 nhưng không có row trong database downstream. Collector sau gateway có output hợp lệ. Test đã hoàn chỉnh chưa?

**Trả lời:** Chưa nếu contract yêu cầu DB row. Phải kiểm tra sink result và xử lý lỗi giữa gateway và writer.

### Tình huống F

**Câu hỏi:** Một splitter tạo ba message, test chỉ lấy được message đầu tiên và đánh dấu PASS. Thiếu điều gì?

**Trả lời:** Cần kiểm đủ ba output, business ID, correlation/sequence và trường hợp output thừa hoặc thiếu.

### Tình huống G

**Câu hỏi:** Adapter file nhận lại cùng file sau restart, collector báo hai message. Có phải collector lỗi?

**Trả lời:** Không nhất thiết. Cần kiểm tra accept-once filter, metadata store, xử lý file sau đọc và semantics retry; collector chỉ đang quan sát dữ liệu đến.

### Tình huống H

**Câu hỏi:** Test thay outbound adapter bằng mock handler rồi assert đúng payload. Có thể tuyên bố đã test SSH host-key verification của SFTP?

**Trả lời:** Không. Adapter SFTP thật đã bị thay thế; phải dùng SFTP server test và xác minh kết nối, host key, upload cùng lỗi mạng.

### Tình huống I

**Câu hỏi:** Bộ test có các message từ lần chạy trước trong `QueueChannel`. Làm gì để tránh xanh giả?

**Trả lời:** Cô lập context/queue, drain hoặc reset trước test, dùng business ID riêng, bảo đảm không có poller khác vẫn chạy và cleanup subscriber sau test.

## 30. Tài liệu tham khảo và lưu ý phiên bản

- **Spring Integration — Testing support:** https://docs.spring.io/spring-integration/reference/testing.html. Tham khảo `@SpringIntegrationTest`, `MockIntegrationContext`, mock handler và cách kiểm soát endpoint.
- **Spring Cloud Stream — Testing (test binder):** https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html. Tham khảo `InputDestination`, `OutputDestination`, binding/destination và cách kích hoạt test binder theo phiên bản.
- **Spring Cloud Stream — tài liệu các bản cũ:** https://cloud.spring.io/spring-cloud-stream/reference/html/spring-cloud-stream.html. Phần testing giải thích chuyển từ test support binder cũ sang test binder sử dụng Spring Integration; dùng để đối chiếu `MessageCollector` của codebase legacy.

**Chọn đúng tài liệu phiên bản:** Các dòng Spring Integration/Spring Cloud Stream khác nhau có thể đổi signature, dependency, test annotation hoặc lifecycle. Khi triển khai dự án thật, kiểm tra các class hiện có trên classpath và không ghép mã từ hai thế hệ API trong cùng một test chỉ vì tên gọi giống nhau.

## Kết luận

**MessageCollector và kiểm tra output** giúp biến một luồng tích hợp khó quan sát thành các điểm kiểm thử cụ thể: message được phát ra ở đâu, chứa payload/header gì, có đúng số lượng, đúng nhánh và đúng thời điểm hay không. Với **Spring Integration thuần**, `QueueChannel`, terminal collector handler, wire tap và `MockIntegrationContext` là công cụ trực tiếp để quan sát flow. Với **Spring Cloud Stream**, cần phân biệt lớp legacy `MessageCollector` và test binder mới dùng `InputDestination`/`OutputDestination`. Quan trọng nhất, **một collector nhìn thấy message chưa phải bằng chứng hệ thống ngoài đã xử lý**; muốn kiểm tra adapter qua file, SFTP, HTTP, JMS, AMQP, Kafka và database phải kết hợp assertion trên channel với **side effect, lỗi, retry, idempotency và lifecycle thật**. Khi giới hạn được điều mỗi bài test chứng minh và dọn sạch state giữa các lượt chạy, bộ test trở nên chính xác, ổn định và hữu ích cho vận hành.

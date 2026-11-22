# Giữ payload, headers và message identity

**Chương:** Bridge  
**Bài học:** Giữ payload, headers và message identity  
**Phạm vi:** `SPRING_INTEGRATION_PATTERN` — thực hành Enterprise Integration Patterns (EIP) với Spring Integration để tạo luồng thông điệp ít phụ thuộc, dễ mở rộng; kết nối Bridge với Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử hành vi thực tế.

## 1. Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Trình bày vai trò của **Bridge**: nối hai message channel để chuyển tiếp message mà không chủ đích biến đổi nội dung.
2. Phân biệt **payload**, **headers**, **message identity** của Spring Messaging và **event identity** của nghiệp vụ.
3. Hiểu vì sao Bridge có thể giữ nguyên message trong một luồng cục bộ nhưng **không bảo đảm** toàn bộ hành trình qua adapter, converter, broker và retry đều giữ nguyên Java object hoặc message ID.
4. Viết Java DSL sử dụng `.bridge()`, truyền `Message<?>` qua hai channel và kiểm tra dữ liệu/định danh bằng test.
5. Nhận biết ranh giới gây thay đổi message: `Transformer`, `Header Enricher`, `ChannelInterceptor`, serialization, message store, broker adapter và request–reply.
6. Thiết kế correlation, idempotency, trace, xử lý lỗi và quan sát để chuyển tiếp an toàn khi ứng dụng chạy bất đồng bộ hoặc đa dịch vụ.

## 2. Bridge trong Enterprise Integration Patterns

Bridge là mẫu tích hợp **kết nối hai message channel**. Nó hữu ích khi hai đoạn luồng có ranh giới tổ chức hoặc khác cách tiêu thụ message, nhưng **không cần chuyển đổi** payload như Transformer, phân loại như Router hay lọc như Filter.

Một Bridge có hai trách nhiệm cốt lõi:

- Nhận message từ channel phía trước.
- Chuyển tiếp message đó tới channel phía sau theo cấu hình của flow.

~~~mermaid
flowchart LR
    P["Producer"] --> C1["ordersIn: DirectChannel"]
    C1 --> B["Bridge"]
    B --> C2["ordersOut: QueueChannel"]
    C2 --> Q["Poller / Consumer"]
    Q --> H["Service Activator"]
~~~

Trong Spring Integration, Bridge có thể được khai báo trong Java DSL qua `.bridge()`. Về ý định của pattern, Bridge **không tự đóng vai trò Transformer, Filter hay Header Enricher**. Vì vậy, đối với một đoạn chuyển tiếp nội bộ đơn giản, ta kỳ vọng payload và các header của message được đi tiếp.

Tuy nhiên, *tính đúng đắn của nội dung*, *định danh của message*, *địa chỉ nhận lỗi* và *khả năng xử lý sau crash* là những thuộc tính khác nhau. Cần mô tả và kiểm tra riêng.

### Khi nào nên dùng Bridge?

- Nối `DirectChannel` với `QueueChannel` để tách producer khỏi poller xử lý nền.
- Nối hai đoạn flow có cách tổ chức khác nhau nhưng không cần sửa payload.
- Tạo điểm quan sát hoặc điểm gắn chính sách dispatch/monitoring giữa hai channel.
- Chuyển từ một nguồn đã cấu hình `PollableChannel` sang một channel khác mà không phải viết handler chỉ có nhiệm vụ trả lại message.

Khi hai endpoint có thể nối trực tiếp và không cần ranh giới riêng, Bridge có thể không cần thiết. Việc thêm Bridge **không tự tạo độ bền dữ liệu, tăng throughput hoặc giải quyết lỗi**.

## 3. Cấu trúc một Spring Message

Spring Messaging biểu diễn message bằng giao diện `Message<T>`, gồm:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Payload** | Dữ liệu ứng dụng đang truyền | `OrderPlaced(eventId, orderId)` |
| **Headers** | Metadata mô tả message và cách xử lý | `eventId`, `correlationId`, `replyChannel`, `errorChannel` |
| **Message ID** | Định danh kỹ thuật của một Spring message, thường nằm ở `MessageHeaders.ID` | UUID được cấp khi message được tạo |
| **Timestamp** | Thời điểm tạo message/header theo cơ chế của Spring | `MessageHeaders.TIMESTAMP` |
| **Business event ID** | Định danh sự kiện nghiệp vụ ổn định xuyên các lần gửi lại | `evt-00042` |
| **Correlation ID** | Gom các message có cùng ngữ cảnh/yêu cầu/nhóm | `order-123` hoặc `batch-7` |

Ví dụ tạo một message:

~~~java
record OrderPlaced(String eventId, String orderId, long totalInCents) {}

OrderPlaced event = new OrderPlaced("evt-00042", "order-123", 249900);

Message<OrderPlaced> message = MessageBuilder
        .withPayload(event)
        .setHeader("eventId", event.eventId())
        .setHeader("correlationId", event.orderId())
        .setHeader("traceId", "trace-demo-01")
        .build();

System.out.println(message.getPayload());
System.out.println(message.getHeaders().getId());
System.out.println(message.getHeaders().get("eventId"));
~~~

**Lưu ý:** `MessageHeaders.ID` là định danh của message do Spring tạo/quản lý; `eventId` do nghiệp vụ tạo. Hai ID có ý nghĩa khác nhau, kể cả khi chúng cùng tồn tại trong một `Message<?>.`

### 3.1 MessageHeaders và tính bất biến

Tập hợp `MessageHeaders` được thiết kế với giao diện **không cho sửa trực tiếp** như một `Map` tùy ý. Để thay header, thường cần tạo hoặc xây dựng lại message bằng `MessageBuilder`, một `Header Enricher` hay cơ chế tương đương.

Điều đó **không có nghĩa message được deep-copy**:

- Payload có thể là đối tượng Java khả biến. Nếu nhiều thành phần cùng giữ tham chiếu tới nó, thay đổi bên trong payload có thể lộ ra ngoài.
- Giá trị một header cũng có thể chứa đối tượng khả biến.
- Một Bridge chuyển tiếp message không chịu trách nhiệm đóng băng tất cả object trong payload/header.

Với dữ liệu nghiệp vụ quan trọng, nên dùng `record`, value object bất biến, dữ liệu đã được validate hoặc chuyển đổi sang biểu diễn ổn định ở ranh giới tích hợp.

## 4. Ba tầng “identity” thường bị nhầm

Trong một flow, câu “message vẫn là message cũ” có thể chỉ ba điều khác nhau:

| Tầng identity | Câu hỏi | Cách kiểm tra | Có nên dùng để chống xử lý trùng? |
|---|---|---|---|
| **Java object identity** | Hai biến có trỏ tới cùng một object `Message` không? | `first == second` | Không: chỉ có ý nghĩa trong cùng JVM và phụ thuộc triển khai. |
| **Spring message ID** | Trường `MessageHeaders.ID` có giữ giá trị không? | `first.getHeaders().getId().equals(second.getHeaders().getId())` | Không nên: ID có thể đổi khi tạo message mới hoặc qua transport. |
| **Business event identity** | Hai lần giao có thuộc cùng một sự kiện nghiệp vụ không? | So sánh `eventId` do producer cấp, lưu trong payload/header | Có: phù hợp làm khóa idempotency nếu thiết kế ổn định. |

**Correlation ID** khác với ba tầng trên. Nó dùng để liên kết message thuộc cùng request, batch hoặc nhóm cho Aggregator. Có thể có nhiều message khác nhau cùng `correlationId`, trong khi mỗi message có ID riêng.

~~~mermaid
flowchart TD
    E["Business event: evt-00042"] --> M1["Spring Message A: UUID-a"]
    E --> M2["Spring Message B: UUID-b (republish / retry)"]
    M1 --> C["correlationId = order-123"]
    M2 --> C
    C --> G["Nhóm theo đơn hàng"]
~~~

Ở ví dụ này, cả A và B đại diện cho cùng một business event; việc có hai Spring message ID khác nhau **không làm cho đây thành hai đơn hàng hợp lệ**.

## 5. Điều gì được giữ khi đi qua Bridge cục bộ?

Với Bridge thông thường trong cùng ứng dụng, mục đích là **chuyển tiếp message**, nên những nội dung sau được kỳ vọng không bị thay đổi bởi chính Bridge:

1. **Payload value** — kiểu và dữ liệu được đưa qua, không có logic biến đổi nghiệp vụ của Bridge.
2. **Headers** — metadata của message được chuyển theo, bao gồm các custom headers; Bridge không được dùng như một bước làm sạch hoặc đổi header.
3. **Message identity** — khi cùng `Message<?> ` được chuyển tiếp trực tiếp, ID của message được giữ. Đây là hành vi nên kiểm tra bằng test cho cấu hình đang dùng.

Điều **không nên suy ra** từ các nhận xét trên:

- Bridge cam kết giữ cùng **Java object reference** qua mọi loại channel và mọi cơ chế serialization.
- Mọi header đều sẽ sống sót khi qua HTTP, JMS, AMQP hoặc Kafka adapter.
- Bridge tự cung cấp ACK, transaction, persistence, retry và DLQ.
- Một message giữ ID có nghĩa nghiệp vụ đã xử lý chính xác một lần.
- Message được chuyển tiếp thành công có nghĩa consumer sau Bridge đã commit nghiệp vụ.

Một `ChannelInterceptor` có thể thay thế message ở `preSend`; `Transformer` sau Bridge có thể tạo message khác; persistent store/adapter có thể tuần tự hóa rồi tái dựng object. Vì vậy, khi khẳng định identity được giữ, hãy ghi rõ **phạm vi quan sát và các thành phần nằm trên đường đi**.

### 5.1 Minh họa hai ranh giới

~~~mermaid
flowchart LR
    A["Message A: payload + headers + UUID-a"] --> B["Bridge cục bộ"]
    B --> C["Message A: dữ liệu chuyển tiếp"]
    C --> D["Outbound adapter + converter"]
    D --> E[("Broker")]
    E --> F["Inbound adapter"]
    F --> G["Message B: cần xác minh header mapping và UUID"]
~~~

Bên trái, không có bước chuyển đổi nghiệp vụ được chủ đích thực hiện bởi Bridge. Bên phải, client/protocol/adapter có thể chuyển message sang định dạng wire rồi tái tạo Spring message mới. Muốn bảo đảm khả năng liên kết ở cả hai đầu, sử dụng `eventId`/`correlationId` có mapping rõ ràng.

## 6. Java DSL: tạo Bridge từ DirectChannel sang QueueChannel

Ví dụ này nối channel đồng bộ vào queue để một consumer nhận sau. Queue chỉ là **bộ nhớ cục bộ**, dùng để kiểm tra chuyển tiếp, chưa nhằm bảo đảm không mất message khi ứng dụng restart.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class OrderBridgeConfig {

    @Bean
    MessageChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean
    PollableChannel ordersOut() {
        return new QueueChannel(100);
    }

    @Bean
    IntegrationFlow orderBridgeFlow() {
        return IntegrationFlow
                .from("ordersIn")
                .bridge()
                .channel("ordersOut")
                .get();
    }
}
~~~

Giải thích:

- `ordersIn` là điểm gửi message vào flow, dùng `DirectChannel` để gọi handler theo cách đồng bộ.
- `.bridge()` khai báo endpoint chuyển tiếp message.
- `ordersOut` là `QueueChannel`, cho phép consumer gọi `receive(timeout)` để nhận.
- `100` là dung lượng hàng đợi nội bộ. Khi đầy, producer có thể bị chờ hoặc gửi thất bại tùy cách gọi `send` và timeout; cần kiểm tra giới hạn tải.
- Nếu chưa có consumer, message có thể nằm chờ trong queue; nhưng queue bộ nhớ không bảo toàn dữ liệu sau khi tiến trình chết.

Bridge được đặt để làm rõ ranh giới. Nó không chuyển `ordersOut` thành queue RabbitMQ, không tự có persistent message store, không tự bắt exception từ mọi handler ở phía sau.

### 6.1 Gửi một message có metadata

~~~java
OrderPlaced event = new OrderPlaced("evt-00042", "order-123", 249900);

Message<OrderPlaced> sent = MessageBuilder
        .withPayload(event)
        .setHeader("eventId", event.eventId())
        .setHeader("correlationId", event.orderId())
        .setHeader("sourceSystem", "checkout")
        .build();

boolean accepted = ordersIn.send(sent);
if (!accepted) {
    throw new IllegalStateException("Bridge input rejected message");
}
~~~

`send()` thành công cho biết message được channel nhận theo hợp đồng của nó. Khi `ordersOut` là queue trong bộ nhớ, `accepted == true` **không phải** là xác nhận message đã được ghi bền vững hay consumer đã hoàn thành xử lý.

### 6.2 Đọc message từ channel đích

~~~java
Message<?> received = ordersOut.receive(2_000);
if (received == null) {
    throw new IllegalStateException("No bridged message received");
}

System.out.println(received.getPayload());
System.out.println(received.getHeaders().get("eventId"));
System.out.println(received.getHeaders().getId());
~~~

Ví dụ giả sử code gọi đang có tham chiếu đến hai bean `ordersIn`, `ordersOut`. Khi triển khai thực tế, có thể inject chúng bằng `@Qualifier` hoặc tạo service gửi/nhận.

## 7. Kiểm thử tự động payload, headers và ID

Thay vì chỉ kiểm tra `send() == true`, nên nhận message ở đầu bên kia và đối chiếu các trường cụ thể. Đoạn test dưới đây sử dụng Spring Test và JUnit 5; giữ `OrderBridgeConfig` ở mục trước trong cùng test classpath.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OrderBridgeConfig.class)
class OrderBridgeTest {

    @Autowired
    @Qualifier("ordersIn")
    MessageChannel input;

    @Autowired
    @Qualifier("ordersOut")
    PollableChannel output;

    record OrderPlaced(String eventId, String orderId, long totalInCents) {}

    @Test
    void bridgeForwardsPayloadHeadersAndId() {
        OrderPlaced event =
                new OrderPlaced("evt-00042", "order-123", 249900);

        Message<OrderPlaced> sent = MessageBuilder
                .withPayload(event)
                .setHeader("eventId", event.eventId())
                .setHeader("correlationId", event.orderId())
                .setHeader("sourceSystem", "checkout")
                .build();

        assertTrue(input.send(sent));

        Message<?> received = output.receive(2_000);
        assertNotNull(received);

        // Không có Transformer trên đường đi.
        assertEquals(sent.getPayload(), received.getPayload());

        // Những header cần thiết được giữ nguyên.
        assertEquals("evt-00042", received.getHeaders().get("eventId"));
        assertEquals("order-123", received.getHeaders().get("correlationId"));
        assertEquals("checkout", received.getHeaders().get("sourceSystem"));

        // Kỳ vọng cho đúng cấu hình Bridge chuyển tiếp cục bộ này.
        assertEquals(sent.getHeaders().getId(),
                     received.getHeaders().getId());
    }
}
~~~

**Phạm vi khẳng định:** test xác minh một Bridge nội bộ nối `DirectChannel` với `QueueChannel`, không có converter/interceptor làm thay message. Kết quả test **không** là bằng chứng rằng ID sẽ giữ nguyên qua Kafka/JMS/AMQP, HTTP, serializer, retry hoặc mọi phiên bản của framework.

Nếu cần kiểm tra **cùng tham chiếu object**, có thể thêm `assertSame(sent, received)` cho một cấu hình cụ thể; đó là kỳ vọng về đường chạy/triển khai hiện tại và nên được giữ riêng khỏi kiểm thử hợp đồng **giữ giá trị payload, headers và ID**. Các tích hợp bền vững hoặc phân tán không thể lấy `==` làm điều kiện đúng sai.

## 8. Channel nào cũng “chuyển tiếp giống nhau” sao?

Bridge là handler chuyển tiếp, nhưng **channel trước và sau Bridge quyết định lịch chạy và cách xử lý**.

| Ranh giới | Hành vi chủ yếu | Điều cần kiểm chứng |
|---|---|---|
| `DirectChannel` → Bridge → `DirectChannel` | Handler đồng bộ, thường trên thread gọi. | Thời gian block, lan truyền exception, transaction hiện tại. |
| `DirectChannel` → Bridge → `QueueChannel` | Enqueue để consumer đọc sau. | Capacity, thời gian chờ, dữ liệu còn khi restart, thread tiêu thụ. |
| `QueueChannel` → Bridge → channel khác | Nguồn pollable cần một poller lấy dữ liệu. | Poller, transaction khi dequeue, retry nếu handler lỗi. |
| `ExecutorChannel` → Bridge → channel khác | Giao việc qua executor bất đồng bộ. | Rejection, giới hạn executor, error handling ở thread khác. |
| `PublishSubscribeChannel` → Bridge → đích | Có nhiều subscriber hoặc nhánh tùy cấu hình. | Mỗi subscriber nhận gì, cách xử lý exception và thứ tự. |
| Bridge → outbound adapter | Đổi từ channel nội bộ sang hệ thống ngoài. | Converter, header mapping, publisher confirm, ACK hoặc offset. |

### 8.1 Cấu hình Bridge từ QueueChannel có poller

Nếu input là `PollableChannel`, flow cần được kích hoạt bằng poller. Ví dụ minh họa trong một cấu hình **khác** so với `OrderBridgeConfig` ở trên:

~~~java
@Bean
IntegrationFlow bufferedBridgeFlow() {
    return IntegrationFlow
            .from("bufferedInput", endpoint -> endpoint.poller(
                    Pollers.fixedDelay(500).maxMessagesPerPoll(10)))
            .bridge()
            .channel("nextChannel")
            .get();
}
~~~

Giả định đã khai báo các bean `bufferedInput` kiểu `PollableChannel` và `nextChannel` phù hợp. Không khai báo hai flow cùng cạnh tranh một input trừ khi đã chủ đích thiết kế competing consumers.

Khi poller lấy message rồi phía sau báo lỗi, khả năng **quay lại queue** phụ thuộc vào message store, transaction và error handler. Bridge không tự đưa message về đầu queue.

## 9. Khi nào headers bị thay đổi hoặc thất lạc?

Bridge không chủ đích sửa headers, nhưng luồng tích hợp thường có nhiều thành phần ở trước hoặc sau nó.

| Thành phần/bước | Rủi ro đối với header | Hướng xử lý |
|---|---|---|
| `MessageBuilder` hoặc `Transformer` tạo message mới | Header không được copy, ID có thể mới. | Quy định danh sách header cần bảo tồn; test cụ thể. |
| `Header Enricher` | Thêm hoặc ghi đè metadata theo cấu hình. | Phân biệt header nghiệp vụ với header do framework quản lý. |
| `ChannelInterceptor` | `preSend` có thể trả về message khác hoặc từ chối gửi. | Đọc cấu hình interceptor, kiểm thử tại cả hai đầu. |
| `Filter` hoặc `Router` | Message có thể bị loại hoặc sang nhánh khác. | Tách lỗi bỏ qua/định tuyến khỏi thao tác thay đổi message. |
| `Splitter` | Một message gốc thành nhiều message con, tạo sequence/correlation metadata. | Giữ business `eventId` và thêm định danh phần con khi cần. |
| `Aggregator` | Nhiều message hợp thành một message kết quả. | Xác định ID của message kết quả và correlation semantics. |
| Serialization/persistent store | Object có thể được tái dựng; class/serializer ảnh hưởng metadata. | Kiểm thử deserialize, schema/version compatibility, required headers. |
| AMQP/JMS/Kafka/HTTP adapter | Header không hỗ trợ hoặc bị ánh xạ/loại bỏ. | Khai báo header mapper và integration test qua transport thật. |

Ví dụ một Transformer xây dựng message mới nhưng quên đưa theo `eventId`:

~~~java
.handle(OrderPlaced.class, (order, headers) -> {
    // Ví dụ sai về propagation nếu downstream cần eventId:
    return MessageBuilder.withPayload(order.orderId()).build();
})
~~~

Handler tạo **message mới**, nên không thể mặc định các header tùy chỉnh của message gốc đều xuất hiện ở đầu ra. Trong Spring Integration, endpoint có thể áp dụng cơ chế header propagation/merge tùy loại handler, do đó hãy kiểm tra **message đầu ra thực tế** thay vì suy đoán chỉ từ một dòng `MessageBuilder` trong handler.

Nếu muốn thay payload mà giữ đúng những header nghiệp vụ cần thiết, hãy dùng Transformer có quy tắc propagation rõ và viết test:

~~~java
Message<String> transformed = MessageBuilder
        .withPayload(order.orderId())
        .copyHeaders(originalMessage.getHeaders())
        .setHeader("transformation", "order-to-id")
        .build();

// Payload đã đổi; kiểm tra eventId/correlationId cần giữ.
// ID/timestamp kỹ thuật có thể được sinh hoặc xử lý theo
// chính sách của MessageBuilder/MessageHeaders: test cụ thể.
~~~

**Ghi nhớ:** ngay cả khi `copyHeaders(...)` được sử dụng, cần xác minh xử lý **các header framework có quy tắc đặc biệt** như ID và timestamp. Mục tiêu ổn định giữa các hệ thống nên là `eventId`, `correlationId` và metadata nghiệp vụ được định nghĩa rõ.

## 10. Ranh giới broker/adapter: message identity không phải wire identity

Giả sử luồng chạy:

~~~mermaid
flowchart LR
    A["Message A trong service X"] --> B["Bridge"]
    B --> C["AMQP / JMS / Kafka outbound adapter"]
    C --> D[("Broker")]
    D --> E["Inbound adapter"]
    E --> F["Message B trong service Y"]
~~~

Broker thường không lưu nguyên một Java `Message<?>` cùng tham chiếu object. Adapter sử dụng converter, serializer hoặc header mapper để chuyển sang dạng có thể truyền qua mạng. Ở đầu nhận, một Spring `Message<?>` khác có thể được xây dựng.

Do đó, phân biệt:

- **Payload equality:** sau convert qua JSON/Avro/byte array, biểu diễn hoặc kiểu dữ liệu có thể khác; cần so sánh ý nghĩa nghiệp vụ sau deserialize.
- **Header propagation:** custom headers có thể không được hỗ trợ hoặc phải cấu hình mapper; một số header là thông tin cục bộ, chẳng hạn đối tượng `replyChannel`/`errorChannel` không thích hợp để coi là dữ liệu wire tùy ý.
- **Spring message ID:** không nên coi là ID bất biến qua mọi transport. Có thể có broker message ID khác với Spring message ID.
- **Business event ID:** hãy đưa vào schema payload hoặc header có mapping xác định và sử dụng ở phía nhận để deduplicate.
- **Trace/correlation:** bảo tồn bằng định dạng header được cả hai đầu hỗ trợ và test end-to-end.

Khi chọn Kafka, offset định danh **vị trí record trong một partition**; nó không thay thế `eventId`. Với RabbitMQ hoặc JMS, acknowledgment của consumer chỉ phản ánh quy tắc xác nhận delivery/transaction của transport, không biến `MessageHeaders.ID` thành khóa nghiệp vụ.

## 11. Correlation, Aggregator và request–reply

Bridge thường được chèn vào luồng có `Splitter`/`Aggregator` hoặc `Messaging Gateway`. Vì thế cần xem metadata mà các component này dùng.

### 11.1 Correlation không phải identity

Trong luồng chia một đơn hàng thành ba phần:

~~~text
OrderPlaced(eventId=evt-42, orderId=order-7)
    -> Splitter
       -> ReserveStock(part=1, correlationId=order-7)
       -> ChargePayment(part=2, correlationId=order-7)
       -> CreateInvoice(part=3, correlationId=order-7)
    -> Aggregator(correlationId=order-7)
~~~

Ba message con có **định danh message riêng**, cùng `correlationId` để gom nhóm, và có thể dùng `eventId`/child ID để chống xử lý trùng. Bridge đặt giữa các channel không tự cấu hình correlation strategy, release strategy, sequence size hay timeout của Aggregator.

Nếu yêu cầu Aggregator phục hồi qua restart, phải cân nhắc `MessageGroupStore` bền vững và xử lý message con bị gửi lại; **Bridge không lưu trạng thái nhóm**.

### 11.2 Reply channel và error channel

Gateway hoặc handler có thể sử dụng `replyChannel` và `errorChannel` để trả kết quả hoặc thông tin lỗi trong ứng dụng. Bridge cục bộ có thể chuyển tiếp các header này khi chuyển tiếp message, nhưng:

- `replyChannel` trỏ tới một `MessageChannel` nội bộ có thể không còn ý nghĩa sau khi message ra khỏi tiến trình.
- Reply phải tới đúng nơi được consumer/gateway chờ; timeout và reply trễ cần được xử lý.
- Một error channel không tự bảo đảm retry, rollback hoặc NACK.
- Khi cần request–reply xuyên broker, hãy dùng reply destination và correlation ID có hợp đồng rõ ràng.

Không tự coi Bridge là một **Gateway**; Bridge chuyển tiếp message trong flow, còn Gateway cung cấp giao diện gọi và cơ chế mapping request–reply cho code ứng dụng.

## 12. Identity khi retry và redelivery

Ngay cả khi Bridge giữ toàn bộ thông tin ở lượt đi đầu tiên, hệ thống vẫn có thể gặp message lặp vì consumer crash, timeout hoặc producer publish lại.

Ví dụ:

1. Service A gửi `OrderPlaced(eventId=evt-42)`.
2. Bridge chuyển message đến outbound adapter rồi qua broker.
3. Service B commit hóa đơn trong database.
4. Service B chết trước khi broker ghi nhận ACK/offset commit.
5. Message được giao lại; service B lại gặp `eventId=evt-42`.

Trong tình huống này, việc **Spring message ID có giữ hay thay đổi** không quan trọng bằng khả năng nhận diện cùng một `eventId`. Consumer cần một operation idempotent, chẳng hạn unique key trên `processed_event(event_id)` và commit đánh dấu đã xử lý **cùng transaction** với thay đổi hóa đơn.

~~~sql
-- Minh họa PostgreSQL, chỉ thực hiện business write khi event chưa có.
BEGIN;

INSERT INTO processed_event(event_id)
VALUES (:eventId)
ON CONFLICT (event_id) DO NOTHING;

-- Ứng dụng kiểm tra insert count.
-- Nếu bằng 1: tạo/cập nhật hóa đơn trong cùng transaction.
-- Nếu bằng 0: đã xử lý event này, bỏ qua tác động trùng.

COMMIT;
~~~

Tránh sửa tên `eventId` theo mỗi lần retry; đó phải là khóa **ổn định xuyên các lần giao của cùng sự kiện**. Với side effect ngoài transaction như email hoặc HTTP thanh toán, cần idempotency key ở hệ thống đích hoặc outbox có khả năng phục hồi.

## 13. Error channel và retry khi Bridge gặp lỗi

Bridge không thực hiện logic nghiệp vụ, nhưng việc gửi sang channel đích vẫn có thể thất bại:

- `QueueChannel` đầy hoặc timeout enqueue.
- `ExecutorChannel` từ chối task vì executor quá tải.
- Subscriber hoặc handler đồng bộ phía sau ném `MessagingException`.
- Poller lấy message từ queue có persistent store nhưng transaction/DB lỗi.
- Channel đích không có subscriber phù hợp, hoặc cấu hình sai.

Phản ứng phụ thuộc vào thread và cơ chế dispatch:

| Trường hợp | Đường lỗi thường thấy | Ý nghĩa |
|---|---|---|
| Bridge chạy đồng bộ qua `DirectChannel` | Exception có thể propagate về caller của `send()`. | Caller quyết định retry/rollback; không tự động có `ErrorMessage`. |
| Bridge chạy từ poller | Poller hoặc error handler bắt exception theo cấu hình. | Cần kiểm tra rollback khi dequeue và tình trạng message. |
| Bridge tới async executor | Lỗi ở worker thread có thể đi qua error handler/error channel của async boundary. | Producer có thể đã được trả kết quả trước khi consumer thất bại. |
| Bridge tới channel bền vững | Ghi message có thể tham gia transaction store phù hợp. | Chỉ khi giao dịch commit thì mới có bằng chứng lưu bền vững. |

~~~mermaid
flowchart TD
    I["Message đi vào Bridge"] --> S{"Gửi sang channel đích"}
    S -->|Được nhận| N["Chuyển bước xử lý kế tiếp"]
    S -->|Bị từ chối / exception| E["Caller, poller hoặc async error handler"]
    E --> P{"Chính sách xử lý"}
    P -->|Có thể thử lại| R["Retry có giới hạn + backoff"]
    P -->|Không phục hồi| Q["Quarantine / DLQ thích hợp"]
    P -->|Có transaction| T["Rollback khi được cấu hình"]
    R --> S
~~~

Sơ đồ thể hiện **những lựa chọn cần cấu hình**, không phải mặc định Bridge tự thực hiện toàn bộ. Không dùng `errorChannel` như một bằng chứng rằng message đã được lưu, đã ACK hoặc sẽ được redeliver.

## 14. Kiểm thử những thay đổi không mong muốn

Một bộ test hữu ích cần bao phủ cả **giá trị message** lẫn **cách xử lý lỗi**.

| Tình huống | Cách tạo | Điều cần khẳng định |
|---|---|---|
| Chuyển tiếp thuần | `DirectChannel → Bridge → QueueChannel` | Payload, custom headers và message ID đúng kỳ vọng trong cấu hình cục bộ. |
| Object payload khả biến | Gửi `Map` hoặc DTO mutable rồi thay đổi trường. | Xác định rõ có dùng chung tham chiếu; cân nhắc immutable payload. |
| Header interceptor | Gắn interceptor có khả năng tạo message khác. | Header bắt buộc còn; nếu ID đổi thì phân biệt message kỹ thuật và event ID. |
| Transformer sau Bridge | Đổi payload thành DTO mới. | `eventId` và `correlationId` được copy theo hợp đồng. |
| Splitter/Aggregator | Chia nhiều phần có chung correlation. | Mỗi phần có ID/phần tử phù hợp; Aggregator không treo khi retry. |
| Broker adapter | Gửi qua AMQP/JMS/Kafka thật. | Metadata được map đúng, payload deserialize được, event ID ổn định. |
| Consumer nhận trùng | Gửi lại cùng business event. | Chỉ một tác động nghiệp vụ được commit. |
| Queue đầy | Đạt `QueueChannel` capacity. | Send fail/timeout rõ ràng; không bỏ message âm thầm. |
| Restart giữa xử lý | Dừng ứng dụng sau enqueue hoặc sau business commit. | Hành vi persistence và redelivery đúng cấu hình; không trùng tác động. |
| Lỗi handler | Ném exception ở consumer sau Bridge. | Error path, transaction và retry được đo, không suy luận từ mỗi `send()`. |

Nên viết thêm assertion cho trạng thái database/side effect cuối cùng. Hai message có cùng `eventId` đi vào consumer có thể là tình huống bình thường dưới at-least-once delivery; trạng thái nghiệp vụ mới là tiêu chí xác nhận chống duplicate.

### Bộ câu hỏi quan sát khi debug

Khi nhận một message ở đầu cuối, ghi nhận riêng:

~~~text
businessEventId = payload.eventId / header.eventId
correlationId   = header.correlationId
springMessageId = headers.id
payloadType     = type(payload)
inputChannel    = ordersIn
outputChannel   = ordersOut
transport       = in-memory | JDBC store | AMQP | JMS | Kafka
deliveryAttempt = count (nếu nguồn/adapter cung cấp)
traceId         = propagated trace context
~~~

Giá trị `deliveryAttempt` và `traceId` phải lấy từ metadata thực tế hoặc do ứng dụng chủ động tạo; không giả định mọi channel đều tự có hai header này.

## 15. Checklist thiết kế Bridge giữ dữ liệu và định danh

- [ ] Bridge được dùng để nối channel; không gắn với kỳ vọng biến đổi payload/header của Transformer hay Header Enricher.
- [ ] Đã định nghĩa chính xác phải giữ **payload value**, **custom headers**, **Spring message ID**, **event ID** và **correlation ID** ở phạm vi nào.
- [ ] Payload/header quan trọng dùng kiểu bất biến hoặc có quy tắc sao chép rõ ràng; không dựa vào deep-copy ngầm.
- [ ] Test so sánh message trước/sau Bridge cho cấu hình cục bộ thực tế, kể cả ID và header bắt buộc.
- [ ] Test header mapping/serialization riêng ở mọi ranh giới outbound/inbound adapter.
- [ ] Không dùng `MessageHeaders.ID` hoặc Java reference `==` làm khóa idempotency xuyên dịch vụ.
- [ ] `eventId` ổn định qua publish lại, retry và redelivery; consumer thực thi idempotent.
- [ ] Correlation/reply/error headers được kiểm soát khi dùng Splitter, Aggregator, Gateway và broker.
- [ ] Có giới hạn capacity, poller, transaction, retry/backoff và error handling cho channel đầu vào/đầu ra.
- [ ] Kiểm thử lỗi gửi, queue đầy, handler exception, restart và broker redelivery thay vì chỉ kiểm tra `send()`.
- [ ] Logs và tracing tách biệt Spring message ID với business ID; có chỉ số backlog, retry và lỗi của bridge path.

## 16. Kết luận

Bridge là thành phần **chuyển tiếp** giữa các channel trong Spring Integration. Ở đường đi cục bộ đơn giản, Bridge được dùng để giữ nguyên payload và headers, đồng thời có thể giữ Spring message ID do tiếp tục truyền chính message đó. Dù vậy, **cùng Java object**, **cùng Spring message ID**, **cùng sự kiện nghiệp vụ** và **cùng correlation group** là bốn khái niệm khác nhau.

Để xây dựng luồng EIP đáng tin cậy, hãy kiểm tra message tại ranh giới thực tế, giữ `eventId` ổn định, triển khai correlation/idempotency đúng vị trí và thiết kế rõ transaction, retry, error channel, broker ACK hay offset commit. Bridge giúp nối các đoạn luồng mà không thêm bước biến đổi; các cam kết vận chuyển và phục hồi vẫn thuộc trách nhiệm của channel, adapter và hệ thống xử lý xung quanh.

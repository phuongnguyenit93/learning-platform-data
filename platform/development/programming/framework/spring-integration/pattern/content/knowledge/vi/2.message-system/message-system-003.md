# MessageBuilder và tạo message có chủ đích

## 1. Bối cảnh và mục tiêu

Trong chương **Message system** của module **SPRING_INTEGRATION_PATTERN**, một luồng xử lý được xây dựng từ các thành phần trao đổi thông điệp qua channel. Đây là nền tảng để triển khai các **Enterprise Integration Patterns** bằng Spring Integration: Router quyết định nhánh đi, Filter loại thông điệp không phù hợp, Transformer biến đổi dữ liệu, Splitter/Aggregator xử lý nhóm thông điệp, Gateway kết nối mã nghiệp vụ với messaging, còn retry và error channel giúp quản lý lỗi. Muốn các thành phần ít phụ thuộc nhau và dễ kiểm thử, thông điệp đầu vào phải được tạo ra với ý nghĩa rõ ràng.

**MessageBuilder** là công cụ tạo đối tượng **Message** gồm dữ liệu nghiệp vụ (*payload*) và thông tin đi kèm (*headers*). “Tạo message có chủ đích” nghĩa là chủ động xác định:

1. **Dữ liệu nào** thực sự cần truyền đi?
2. **Metadata nào** downstream cần để định tuyến, liên kết, quan sát và xử lý?
3. **Metadata nào không nên truyền tiếp** vì đã hết hiệu lực, không cần thiết hoặc nhạy cảm?
4. **Ai chịu trách nhiệm** đặt giá trị header và giữ cho chúng nhất quán?

Sau bài này, bạn có thể tạo message mới, bổ sung hoặc loại bỏ header, tạo message dẫn xuất mà không sửa message cũ, lựa chọn chính sách sao chép header và kiểm tra hành vi bằng JUnit.

## 2. Message là gì và vì sao cần builder?

Spring Messaging định nghĩa giao diện tổng quát:

~~~java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
~~~

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Payload | Dữ liệu chính mà consumer xử lý | Bản ghi đơn hàng, chuỗi văn bản, byte array |
| Header nghiệp vụ | Ngữ cảnh để consumer hiểu hoặc quyết định xử lý | tenantId, eventType, schemaVersion |
| Header tích hợp | Metadata phục vụ cơ chế messaging | id, timestamp, replyChannel, errorChannel, correlationId |
| MessageChannel | Kênh chuyển message giữa producer và consumer | DirectChannel, QueueChannel, PublishSubscribeChannel |

Đối tượng **Message** không có phương thức để đặt lại payload hoặc headers sau khi tạo. Bản đồ **MessageHeaders** chỉ cho phép đọc: gọi put/remove trên nó có thể gây **UnsupportedOperationException**. Đây là một hợp đồng giúp các thành phần không vô tình thay đổi cấu trúc message mà thành phần khác đang sử dụng.

Tuy nhiên, **tính bất biến ở đây chỉ áp dụng cho cấu trúc message và bản đồ header**. Nếu payload chứa một đối tượng mutable như ArrayList, hoặc một giá trị header là Map có thể sửa được, nội dung bên trong các đối tượng đó vẫn có thể bị thay đổi qua tham chiếu chia sẻ. Hãy ưu tiên record, đối tượng bất biến hoặc bản sao phòng vệ khi cần xử lý song song.

Có thể tạo **GenericMessage** trực tiếp, nhưng MessageBuilder diễn tả rõ hơn ý định thêm header, sao chép context và tạo message dẫn xuất.

~~~mermaid
flowchart LR
    P["Payload nghiệp vụ"] --> B["MessageBuilder"]
    H["Headers có chủ đích"] --> B
    B --> M["Message<T> bất biến về cấu trúc"]
    M --> C["MessageChannel"]
    C --> F["Filter / Router / Transformer / Gateway"]
~~~

## 3. Tạo message mới từ payload

Ví dụ sử dụng **org.springframework.integration.support.MessageBuilder**, trình xây dựng message mặc định của Spring Integration. Trong hệ sinh thái Spring còn có **org.springframework.messaging.support.MessageBuilder**; cần chọn đúng import cho API đang dùng, đặc biệt khi cần các hàm tiện ích riêng của Spring Integration như setCorrelationId hoặc setPriority.

~~~java
import java.math.BigDecimal;

import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

record OrderPlaced(String orderId, String customerId, BigDecimal total) {}

OrderPlaced event = new OrderPlaced(
        "ORD-2026-001",
        "CUS-007",
        new BigDecimal("125000.00")
);

Message<OrderPlaced> message = MessageBuilder.withPayload(event)
        .setHeader("eventType", "order.placed")
        .setHeader("tenantId", "tenant-hcm")
        .setHeader("schemaVersion", 1)
        .setHeader("traceId", "trace-abc-123")
        .setCorrelationId(event.orderId())
        .build();

OrderPlaced payload = message.getPayload();
String tenant = message.getHeaders().get("tenantId", String.class);
Object correlation = message.getHeaders().get("correlationId");
~~~

Đọc ví dụ theo thứ tự: **withPayload** chọn dữ liệu chính, **setHeader** thêm metadata phục vụ consumer, **setCorrelationId** gán khóa liên kết các message thuộc cùng đơn hàng, và **build** tạo message để chuyển qua channel. Các giá trị tenantId và traceId trong ví dụ phải được lấy từ ngữ cảnh đã xác thực khi triển khai thực tế; không nên tự bịa giá trị mặc định cho mọi yêu cầu.

Payload phải khác **null**. Nếu cần biểu diễn sự vắng mặt của dữ liệu, hãy dùng một kiểu mô hình phù hợp hoặc một thông điệp nghiệp vụ có trạng thái rõ ràng; đừng coi việc truyền null là một message bình thường.

### Khi nào dùng payload, khi nào dùng header?

Một quy tắc hữu ích: **payload trả lời “cần xử lý cái gì?”, header trả lời “xử lý nó trong ngữ cảnh nào?”**.

| Thông tin | Nên đặt ở đâu? | Lý do |
| --- | --- | --- |
| Mã đơn hàng, số tiền, các dòng hàng | Payload | Là dữ liệu nghiệp vụ chính |
| Loại sự kiện để Router chọn nhánh | Header hoặc kiểu payload, tùy hợp đồng | Giúp định tuyến mà không cần biết cấu trúc chi tiết của payload |
| Tenant đã xác thực | Header nếu là context dùng xuyên luồng | Nhiều handler cùng cần, nhưng phải bảo đảm không thể bị giả mạo |
| Trace ID | Header | Phục vụ quan sát và liên kết log |
| Mật khẩu, access token, thông tin thẻ | Không đưa vào header trao đổi/log tùy tiện | Tránh rò rỉ khi trace, serialize hoặc chuyển qua adapter |
| UUID nhận diện riêng một message | Header id do framework tạo | Không trùng với mã đơn hàng hoặc correlation ID |

Tên header tự định nghĩa nên có quy ước nhất quán; ví dụ **tenantId**, **eventType**, **schemaVersion**, **traceId**. Tốt nhất gom tên header thành hằng số để producer và consumer không viết lệch chính tả:

~~~java
final class OrderHeaders {
    static final String EVENT_TYPE = "eventType";
    static final String TENANT_ID = "tenantId";
    static final String SCHEMA_VERSION = "schemaVersion";
    static final String TRACE_ID = "traceId";

    private OrderHeaders() {}
}
~~~

## 4. Điều khiển headers một cách tường minh

MessageBuilder hỗ trợ các thao tác quan trọng:

| API | Hành vi | Tình huống dùng |
| --- | --- | --- |
| withPayload(value) | Bắt đầu một message mới với payload đã chọn | Event mới, kết quả transform |
| fromMessage(source) | Bắt đầu từ payload và headers của message cũ | Thêm context nhưng giữ payload |
| setHeader(name, value) | Đặt hoặc thay thế giá trị header; giá trị null có thể dùng để loại header | Gắn nhãn xử lý đã hoàn thành |
| setHeaderIfAbsent(name, value) | Chỉ đặt nếu header chưa có giá trị | Đặt mặc định mà không ghi đè upstream |
| removeHeader(name) | Bỏ một header trong message được tạo | Loại context tạm |
| removeHeaders(patterns...) | Bỏ các header theo tên/pattern được hỗ trợ | Dọn nhóm header |
| copyHeaders(map) | Sao chép và có thể ghi đè các header trùng tên | Cần lấy metadata từ message đầu vào |
| copyHeadersIfAbsent(map) | Chỉ sao chép header chưa tồn tại ở builder | Giữ quyền ưu tiên cho giá trị đã thiết lập |
| build() | Tạo đối tượng Message hoàn chỉnh | Truyền vào channel |

### 4.1. Tạo message dẫn xuất có cùng payload

~~~java
Message<OrderPlaced> reviewed = MessageBuilder.fromMessage(message)
        .setHeaderIfAbsent("sourceSystem", "checkout")
        .setHeader("validated", true)
        .removeHeader("debugOnly")
        .build();

// Message đầu vào giữ nguyên giá trị headers ban đầu.
// Message mới có header validated = true.
~~~

**fromMessage** phù hợp khi chỉ thay đổi cách diễn giải/metadata. Nó tạo message mới và không sửa trực tiếp message truyền vào. Mặc dù payload được tái sử dụng, nếu payload là đối tượng mutable thì hai message vẫn có thể chia sẻ cùng đối tượng đó.

### 4.2. Đổi kiểu payload và chọn header được truyền tiếp

Ví dụ Transformer chuẩn hóa sự kiện thành dữ liệu để ghi sổ:

~~~java
record InvoiceCommand(String orderId, BigDecimal amount) {}

Message<OrderPlaced> incoming = message;
OrderPlaced order = incoming.getPayload();

InvoiceCommand command =
        new InvoiceCommand(order.orderId(), order.total());

Message<InvoiceCommand> outgoing =
        MessageBuilder.withPayload(command)
                .copyHeaders(incoming.getHeaders())
                .removeHeader("debugOnly")
                .removeHeader("temporaryRoutingHint")
                .setHeader("eventType", "invoice.requested")
                .setHeader("processedBy", "invoice-transformer")
                .build();
~~~

**withPayload** là lựa chọn đúng khi payload chuyển từ OrderPlaced sang InvoiceCommand: **fromMessage** không có mục đích đổi kiểu payload. Với **copyHeaders**, những header truyền đi tiếp phải còn đúng ngữ nghĩa. Ví dụ, eventType cũ là order.placed cần được cập nhật thành invoice.requested; còn một routing hint chỉ có hiệu lực ở chặng trước nên bị xóa.

Hãy chú ý thứ tự:

~~~java
Message<String> result = MessageBuilder.withPayload("normalized")
        .setHeader("origin", "current")
        .copyHeadersIfAbsent(incoming.getHeaders())
        .build();
~~~

Trong ví dụ này, giá trị **origin=current** được giữ nguyên nếu incoming có header origin khác. Nếu thay **copyHeadersIfAbsent** bằng **copyHeaders** ở cùng vị trí, giá trị đến từ incoming có thể ghi đè origin vừa đặt. Khi muốn giá trị mới có quyền ưu tiên, cũng có thể sao chép trước rồi dùng **setHeader** sau.

### 4.3. Headers chuẩn và kiểu dữ liệu

Không phải header nào cũng là String:

| Header chuẩn | Giá trị điển hình | Điều cần nhớ |
| --- | --- | --- |
| MessageHeaders.ID | UUID | Do framework tạo; không tự ghi đè |
| MessageHeaders.TIMESTAMP | Long | Thời điểm tạo message; không tự ghi đè |
| MessageHeaders.REPLY_CHANNEL | MessageChannel hoặc tên channel | Chỉ đặt khi thực sự có luồng request/reply |
| MessageHeaders.ERROR_CHANNEL | MessageChannel hoặc tên channel | Định tuyến một số lỗi messaging; không thay thế xử lý ngoại lệ ở mọi tầng |
| IntegrationMessageHeaderAccessor.CORRELATION_ID | Object | Khóa liên kết các message chung một giao dịch/nhóm |
| IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER | Integer | Thứ tự phần tử trong nhóm |
| IntegrationMessageHeaderAccessor.SEQUENCE_SIZE | Integer | Tổng số phần tử của nhóm nếu biết |
| IntegrationMessageHeaderAccessor.PRIORITY | Integer | Chỉ có tác dụng ưu tiên khi channel/consumer hỗ trợ, chẳng hạn PriorityChannel |

**ID** đại diện cho *một message instance*, còn **correlationId** đại diện cho *mối quan hệ nghiệp vụ* giữa nhiều message. Ví dụ cùng một đơn hàng có message “đã đặt”, “đã thanh toán” và “đã gửi hàng”: chúng nên có message ID riêng, nhưng có thể dùng chung correlationId nếu một flow cần liên kết chúng.

~~~java
Message<String> first = MessageBuilder.withPayload("item-1")
        .setCorrelationId("BATCH-42")
        .setSequenceNumber(1)
        .setSequenceSize(2)
        .build();

Message<String> second = MessageBuilder.withPayload("item-2")
        .setCorrelationId("BATCH-42")
        .setSequenceNumber(2)
        .setSequenceSize(2)
        .build();
~~~

Cặp sequenceNumber/sequenceSize chỉ có ý nghĩa khi producer và downstream đã thống nhất cơ chế grouping, ví dụ để Aggregator ghép đúng hai phần tử. Nếu trong flow có Splitter tự quản lý các header tương ứng, cần tôn trọng quy tắc do Splitter áp dụng, tránh tự đặt giá trị mâu thuẫn.

**ID và timestamp là header chỉ đọc.** Không dùng setHeader để cố định MessageHeaders.ID hoặc MessageHeaders.TIMESTAMP, cũng không dựa vào việc chúng được sao chép nguyên từ message trước. Khi tạo một message mới, framework quản lý định danh/thời điểm của message mới. Nếu cần một mã định danh bền qua nhiều bước, hãy khai báo một header nghiệp vụ riêng như orderId/correlationId.

## 5. Đưa message vào luồng Spring Integration

Tạo message có chủ đích giúp các endpoint làm việc theo hợp đồng rõ ràng:

~~~mermaid
flowchart LR
    A["Order API"] --> B["MessageBuilder"]
    B --> C["orderInputChannel"]
    C --> D{"Filter: hợp lệ?"}
    D -->|Có| E{"Router: eventType"}
    D -->|Không| X["Loại / báo lỗi theo thiết kế"]
    E -->|order.placed| F["Transformer: InvoiceCommand"]
    E -->|order.cancelled| G["Cancel handler"]
    F --> H["Outbound adapter"]
~~~

Ví dụ một producer gửi sự kiện vào channel đã được cấu hình trong Spring:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {
    private final MessageChannel orderInputChannel;

    public OrderEventPublisher(
            @Qualifier("orderInputChannel") MessageChannel orderInputChannel) {
        this.orderInputChannel = orderInputChannel;
    }

    public void publish(OrderPlaced order, String tenantId, String traceId) {
        if (order == null || tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Thiếu đơn hàng hoặc tenantId");
        }

        Message<OrderPlaced> event = MessageBuilder.withPayload(order)
                .setHeader(OrderHeaders.EVENT_TYPE, "order.placed")
                .setHeader(OrderHeaders.TENANT_ID, tenantId)
                .setHeader(OrderHeaders.TRACE_ID, traceId)
                .setCorrelationId(order.orderId())
                .build();

        boolean accepted = orderInputChannel.send(event);
        if (!accepted) {
            throw new IllegalStateException("Channel không chấp nhận message");
        }
    }
}
~~~

Trong ứng dụng thực, cần có bean **orderInputChannel** và ít nhất một endpoint phù hợp để nhận message theo loại channel đã chọn. Phương thức send trả về boolean, nhưng cũng có thể phát sinh exception do cấu hình hoặc lỗi xử lý downstream, nhất là với DirectChannel đồng bộ. Việc send thành công **không mặc nhiên là dữ liệu đã được lưu bền vững hoặc xử lý thành công trên toàn hệ thống**.

Consumer có thể đọc header mà không phụ thuộc vào lớp publisher:

~~~java
import org.springframework.messaging.Message;

void handle(Message<OrderPlaced> incoming) {
    OrderPlaced order = incoming.getPayload();
    String tenant = incoming.getHeaders().get("tenantId", String.class);
    String eventType = incoming.getHeaders().get("eventType", String.class);

    // Kiểm tra tenant, eventType và xử lý nghiệp vụ tương ứng.
}
~~~

Khi handler chỉ trả về một **payload**, các message-producing endpoint thường truyền tiếp headers đầu vào. Khi một **Transformer** trả về nguyên một Message, Transformer chịu trách nhiệm về headers của message trả về; không nên ngầm giả định mọi header đầu vào sẽ được bảo toàn. Một số adapter hoặc endpoint có quy tắc propagation riêng, vì vậy cần kiểm tra hợp đồng của endpoint đang dùng.

## 6. Thiết kế header phục vụ Router, Aggregator, retry và error handling

MessageBuilder tạo metadata; **không tự triển khai** các pattern. Metadata chỉ có hiệu lực khi flow có component xử lý nó.

**Router:** Có thể đọc eventType để phân nhánh, nhưng phải định nghĩa tập giá trị hợp lệ và hành vi với loại sự kiện không nhận diện được. Nếu eventType được sinh từ input bên ngoài, cần chuẩn hóa/kiểm tra trước khi dùng để định tuyến sang đường nhạy cảm.

**Filter:** Header như tenantId và schemaVersion có thể giúp chọn điều kiện, nhưng Filter không thay thế xác thực hoặc phân quyền. Header do người gọi tự gửi không đáng tin cho tới khi được kiểm chứng ở ranh giới hệ thống.

**Transformer:** Khi đổi payload, dùng withPayload và chính sách copyHeaders rõ ràng. Đặt lại eventType/schemaVersion nếu nội dung mới đã mang ý nghĩa hoặc hợp đồng khác.

**Splitter/Aggregator:** Các trường correlationId, sequenceNumber, sequenceSize phải nhất quán và phù hợp cách chia nhóm. Tránh dùng MessageHeaders.ID làm group key; ID thay đổi khi tạo message dẫn xuất.

**Gateway/reply channel:** ReplyChannel nên được khai báo trong flow request/reply cần phản hồi, không mặc định gắn vào mọi sự kiện fire-and-forget. Channel được đặt bằng tên phải thực sự phân giải được khi chạy.

**Retry/error channel:** Header errorChannel có thể tham gia điều hướng lỗi theo cơ chế Spring Integration, nhưng việc một exception được gửi đến đâu còn tùy endpoint, executor, error handling và cấu hình gateway. Không tạo retry chỉ bằng cách đặt một header tùy ý: cần advice hoặc cơ chế retry của adapter, kèm nguyên tắc idempotency để tránh xử lý lặp.

**Observability:** traceId giúp nối log qua các chặng. Chỉ log metadata cần thiết; tránh ghi toàn bộ message nếu payload/headers chứa dữ liệu nhạy cảm. Thực tế còn cần truyền trace context đúng với công cụ quan sát đang dùng.

## 7. Kiểm thử hành vi tạo message

Không cần chạy toàn bộ ứng dụng để kiểm tra hợp đồng của MessageBuilder. Ví dụ dưới đây dùng **JUnit 5** và một **DirectChannel** có subscriber nhận message ngay trong tiến trình:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

class MessageBuilderExampleTest {

    @Test
    void buildsAndSendsMessageWithExplicitHeaders() {
        Message<String> original = MessageBuilder.withPayload("ORD-42")
                .setHeader("eventType", "order.placed")
                .setCorrelationId("ORD-42")
                .build();

        DirectChannel channel = new DirectChannel();
        AtomicReference<Message<?>> received = new AtomicReference<>();
        channel.subscribe(received::set);

        assertTrue(channel.send(original));
        assertSame(original, received.get());
        assertEquals("order.placed",
                received.get().getHeaders().get("eventType"));
        assertEquals("ORD-42", received.get().getPayload());
    }

    @Test
    void derivedMessageRetainsOriginalHeadersButCanOverrideThem() {
        Message<String> original = MessageBuilder.withPayload("pending")
                .setHeader("eventType", "order.placed")
                .setHeader("stage", "created")
                .build();

        Message<String> derived = MessageBuilder.fromMessage(original)
                .setHeader("stage", "validated")
                .removeHeader("eventType")
                .build();

        assertEquals("created", original.getHeaders().get("stage"));
        assertEquals("order.placed", original.getHeaders().get("eventType"));
        assertEquals("validated", derived.getHeaders().get("stage"));
        assertFalse(derived.getHeaders().containsKey("eventType"));
        assertNotEquals(original.getHeaders().getId(),
                derived.getHeaders().getId());
    }
}
~~~

Những kiểm tra này chứng minh: message được đưa vào channel, header có giá trị như mong đợi, message dẫn xuất không sửa headers cũ và mang ID mới. Đây là các ví dụ kiểm thử cục bộ; khi ghép vào ứng dụng, còn phải kiểm tra route thực tế, lỗi downstream, serialization và behavior theo loại channel.

## 8. Các lỗi thiết kế thường gặp

| Sai sót | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nhét mọi thứ vào headers | Message khó hiểu, dễ rò rỉ thông tin và tốn chi phí truyền | Chỉ đưa metadata mà downstream thật sự cần |
| Dùng ID của message như mã giao dịch | Không còn liên kết ổn định khi tạo message mới | Dùng orderId/correlationId riêng |
| Tin rằng Message bất biến sâu | Mutable payload/header value vẫn có thể bị sửa | Dùng kiểu bất biến hoặc defensive copy |
| Copy tất cả headers mà không xét ý nghĩa | Routing hint, debug flag hoặc context cũ lan sang bước mới | Chọn lọc, xóa hoặc thay header không còn hiệu lực |
| Giả định copyHeadersIfAbsent sẽ ghi đè | Giá trị cũ/đã đặt được ưu tiên ngoài dự kiến | Xác định rõ thứ tự sao chép và đặt header |
| Gán priority nhưng không có PriorityChannel | Thứ tự xử lý không thay đổi | Chọn channel/consumer thực sự hỗ trợ ưu tiên |
| Tự đặt id/timestamp | Phụ thuộc sai vào header được framework quản lý | Để framework sinh, dùng khóa nghiệp vụ độc lập |
| Giả định send trả true nghĩa là đã xử lý xong | Bỏ sót lỗi hoặc mất dữ liệu ở chặng sau | Thiết kế acknowledgment, transaction, retry phù hợp |
| Hardcode tên reply/error channel không tồn tại | Runtime không định tuyến đúng như mong muốn | Cấu hình channel thực và kiểm thử lỗi |
| Chưa xác thực tenantId từ nguồn bên ngoài | Có thể xử lý dữ liệu sai tenant | Xác thực context ở ranh giới và kiểm tra tại consumer cần thiết |

## 9. Bài thực hành: thiết kế message cho hệ thống giao vận

Giả sử một ứng dụng nhận sự kiện **shipment.created** từ API, sau đó Router chuyển đến nhánh giao nội thành hoặc liên tỉnh. Mỗi shipment có shipmentId, destinationProvince và packageWeight; hệ thống còn cần tenantId, traceId và phiên bản schema.

**Yêu cầu:**

1. Tạo một record ShipmentCreated chứa ba thuộc tính nghiệp vụ.
2. Dùng MessageBuilder tạo Message với eventType, tenantId, traceId, schemaVersion.
3. Dùng shipmentId làm correlationId để liên kết với các sự kiện giao vận về sau.
4. Tạo message dẫn xuất sau bước kiểm tra với header validated=true; bảo toàn message ban đầu.
5. Khi chuyển payload sang một record DispatchCommand, chỉ sao chép headers còn hiệu lực và cập nhật eventType thành dispatch.requested.

Một lời giải mẫu cho phần tạo và dẫn xuất:

~~~java
record ShipmentCreated(String shipmentId, String destinationProvince,
                       double packageWeight) {}
record DispatchCommand(String shipmentId, String routeCode) {}

ShipmentCreated shipment =
        new ShipmentCreated("SHP-42", "Ho Chi Minh", 2.5);

Message<ShipmentCreated> created = MessageBuilder.withPayload(shipment)
        .setHeader("eventType", "shipment.created")
        .setHeader("tenantId", "tenant-hcm")
        .setHeader("traceId", "trace-42")
        .setHeader("schemaVersion", 1)
        .setCorrelationId(shipment.shipmentId())
        .build();

Message<ShipmentCreated> validated = MessageBuilder.fromMessage(created)
        .setHeader("validated", true)
        .build();

DispatchCommand dispatch =
        new DispatchCommand(shipment.shipmentId(), "HCM-INTRA");

Message<DispatchCommand> requested =
        MessageBuilder.withPayload(dispatch)
                .copyHeaders(validated.getHeaders())
                .removeHeader("validated")
                .setHeader("eventType", "dispatch.requested")
                .build();
~~~

Khi mở rộng bài thực hành, hãy xác định routeCode bằng logic định tuyến thực tế thay vì hardcode, kiểm tra packageWeight dương, validate tenantId, và viết test chứng minh created vẫn giữ eventType=shipment.created sau khi requested được tạo. Nếu chuyển message qua broker, hãy xác nhận bộ chuyển đổi hỗ trợ kiểu payload và từng kiểu giá trị header.

## 10. Checklist trước khi phát hành một message

- Payload có kiểu và ý nghĩa nghiệp vụ rõ ràng; giá trị bắt buộc đã được validate.
- Header chỉ chứa metadata cần thiết; tên và kiểu dữ liệu thống nhất giữa producer/consumer.
- Correlation ID phản ánh đúng vòng đời nghiệp vụ; không nhầm với message ID.
- Không cố sửa ID/timestamp do framework quản lý.
- Khi tạo message dẫn xuất, đã xem xét quyền ưu tiên của setHeader, copyHeaders, copyHeadersIfAbsent và các header phải loại bỏ.
- Không đưa token, mật khẩu hay dữ liệu nhạy cảm vào header có thể được log hoặc đẩy sang hệ thống khác.
- Có test cho message được tạo, header quan trọng, tính không thay đổi của message gốc và luồng định tuyến thực tế.

**Nguyên tắc thực hành:** một message tốt cho người nhận biết được *nó mang dữ liệu gì*, *cần xử lý theo ngữ cảnh nào* và *cần giữ lại những metadata nào ở bước kế tiếp*. MessageBuilder giúp thực thi hợp đồng đó ở ranh giới giữa các thành phần Spring Integration.

## Tài liệu tham khảo

- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html): Message, MessageHeaders, MessageBuilder, propagation và các header chuẩn.
- [Spring Integration API — MessageBuilder](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/support/MessageBuilder.html): API tạo message từ payload hoặc một message có sẵn.
- [Spring Framework — Messaging](https://docs.spring.io/spring-framework/reference/integration.html): Các khái niệm chung về Message và MessageChannel.

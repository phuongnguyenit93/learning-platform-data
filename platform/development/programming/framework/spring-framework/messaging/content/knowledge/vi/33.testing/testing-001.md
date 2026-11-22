# Kiểm thử MessageBuilder, header và bộ chuyển đổi dữ liệu

Trong Spring Messaging, một message không chỉ có payload. Nó còn có headers chứa metadata như content type, correlation ID, thông tin định tuyến hoặc dữ liệu phục vụ xử lý. Khi message đi qua nhiều thành phần, payload có thể được chuyển đổi giữa object Java và dạng biểu diễn trên transport. Vì vậy, kiểm thử messaging cần xác nhận đồng thời nội dung payload, headers và kết quả chuyển đổi.

Ba thành phần cần nắm vững:

- **MessageBuilder** tạo message từ payload và thiết lập headers theo cách nhất quán.
- **MessageHeaders** cung cấp metadata của message. Headers của một message đã tạo là bất biến; muốn thay đổi cần tạo message mới hoặc dùng accessor phù hợp.
- **MessageConverter** chuyển payload giữa object Java và dạng dữ liệu mà transport hoặc endpoint sử dụng. Header như content type có thể ảnh hưởng đến cách converter chọn định dạng.

Bài này tập trung vào cách viết unit test cho các thành phần trên, cách kiểm tra lỗi thường gặp và cách phân biệt message conversion với codec ở những transport như RSocket.

## 1. Cấu trúc của một Spring Message

Spring biểu diễn message bằng interface **Message<T>**, gồm payload và headers:

~~~java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
~~~

Payload là dữ liệu chính, ví dụ **OrderCreatedEvent**, **String**, **byte[]** hoặc một DTO. Headers là một map chứa metadata đi kèm.

Ví dụ tạo message:

~~~java
Message<String> message = MessageBuilder
    .withPayload("Order O-100 created")
    .setHeader("correlationId", "corr-100")
    .setHeader("source", "order-service")
    .build();
~~~

Có thể đọc các thành phần:

~~~java
String payload = message.getPayload();
String correlationId = message.getHeaders().get(
    "correlationId",
    String.class
);
~~~

Không nên nhét toàn bộ thông tin vận hành vào payload nếu thông tin đó thuộc metadata. Ví dụ correlation ID, content type và một số thuộc tính định tuyến thường phù hợp với headers hơn. Ngược lại, dữ liệu nghiệp vụ cần được consumer xử lý phải nằm trong payload hoặc schema nghiệp vụ được quy định rõ.

### Headers hệ thống và headers ứng dụng

**MessageHeaders** có một số header chuẩn:

- **MessageHeaders.ID**: định danh message do Spring quản lý.
- **MessageHeaders.TIMESTAMP**: thời điểm tạo message nếu timestamp được bật.
- **MessageHeaders.CONTENT_TYPE**: MIME type mô tả định dạng payload.
- **MessageHeaders.REPLY_CHANNEL**: kênh phản hồi trong các luồng request-reply.
- **MessageHeaders.ERROR_CHANNEL**: kênh xử lý lỗi trong các cơ chế hỗ trợ header này.

Ứng dụng có thể thêm header riêng như **correlationId**, **tenantId** hoặc **eventVersion**. Nên tập trung tên header vào constants để tránh lỗi chính tả và khác biệt giữa producer với consumer.

~~~java
final class OrderHeaders {
    static final String CORRELATION_ID = "correlationId";
    static final String EVENT_VERSION = "eventVersion";

    private OrderHeaders() {
    }
}
~~~

Không nên tùy tiện ghi đè các header hệ thống như ID hoặc timestamp. Cần kiểm tra hợp đồng của từng transport trước khi sử dụng tên header có ý nghĩa đặc biệt.

## 2. Dùng MessageBuilder đúng cách

**MessageBuilder** giúp tạo message mà không cần tự triển khai **Message** hoặc thao tác trực tiếp với map headers.

### Tạo message mới

~~~java
Message<OrderCreatedEvent> message = MessageBuilder
    .withPayload(new OrderCreatedEvent("O-100", "CREATED"))
    .setHeader(OrderHeaders.CORRELATION_ID, "corr-100")
    .setHeader(OrderHeaders.EVENT_VERSION, 1)
    .build();
~~~

**withPayload** nhận payload; **setHeader** thêm hoặc cập nhật header; **build** tạo message hoàn chỉnh.

### Đặt header chỉ khi chưa tồn tại

Dùng **setHeaderIfAbsent** khi muốn giữ giá trị đã được cung cấp trước đó:

~~~java
Message<String> message = MessageBuilder
    .withPayload("ready")
    .setHeader("source", "gateway")
    .setHeaderIfAbsent("source", "fallback")
    .build();
~~~

Trong ví dụ, giá trị **source** vẫn là **gateway**.

### Sao chép headers

Khi tạo message mới dựa trên một message có sẵn, có thể dùng **fromMessage**:

~~~java
Message<String> original = MessageBuilder
    .withPayload("hello")
    .setHeader("correlationId", "corr-1")
    .build();

Message<String> copied = MessageBuilder
    .fromMessage(original)
    .setHeader("source", "worker")
    .build();
~~~

**copyHeaders** sao chép các header từ map và có thể ghi đè giá trị cùng tên đã có. **copyHeadersIfAbsent** chỉ thêm những header chưa tồn tại. Hãy chọn đúng hành vi để tránh vô tình thay correlation ID hoặc metadata do upstream cung cấp.

### Loại bỏ header

Có thể loại bỏ header khi tạo message mới:

~~~java
Message<String> sanitized = MessageBuilder
    .fromMessage(original)
    .removeHeader("internalDebug")
    .build();
~~~

**setHeader(name, null)** cũng có thể được dùng để loại bỏ một header trong builder. **removeHeader** thể hiện ý định rõ ràng hơn và dễ đọc khi xử lý metadata.

## 3. MessageHeaders là bất biến

Sau khi message được tạo, **MessageHeaders** không cho phép thay đổi cấu trúc map trực tiếp. Điều này giúp các thành phần chia sẻ message tránh nhìn thấy một header bị thay đổi bất ngờ.

Không làm như sau:

~~~java
message.getHeaders().put("source", "worker");
~~~

Cách này không hợp lệ vì headers là immutable và thao tác cập nhật map sẽ bị từ chối.

Hãy tạo message mới:

~~~java
Message<String> updated = MessageBuilder
    .fromMessage(message)
    .setHeader("source", "worker")
    .build();
~~~

Cần nhớ rằng tính bất biến của map không tự động làm mọi object được lưu bên trong header trở thành immutable. Nếu header chứa một **Map**, **List** hoặc object mutable, code giữ tham chiếu đến object đó vẫn có thể thay đổi trạng thái bên trong. Tốt nhất nên dùng giá trị metadata đơn giản, bất biến và có kiểu rõ ràng.

## 4. Kiểm thử MessageBuilder bằng JUnit 5

Unit test nên xác nhận payload, header do ứng dụng thêm và hành vi khi sao chép hoặc loại bỏ header.

Giả sử event:

~~~java
public record OrderCreatedEvent(
    String orderId,
    String status
) {}
~~~

Test tạo message:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessageBuilderTest {

    @Test
    void shouldBuildMessageWithPayloadAndHeaders() {
        OrderCreatedEvent event =
            new OrderCreatedEvent("O-100", "CREATED");

        Message<OrderCreatedEvent> message = MessageBuilder
            .withPayload(event)
            .setHeader("correlationId", "corr-100")
            .setHeader("eventVersion", 1)
            .build();

        assertSame(event, message.getPayload());
        assertEquals(
            "corr-100",
            message.getHeaders().get("correlationId")
        );
        assertEquals(
            1,
            message.getHeaders().get("eventVersion")
        );
        assertNotNull(message.getHeaders().getId());
    }
}
~~~

Test dùng **assertSame** để xác nhận builder giữ đúng object payload đã truyền vào. Nếu hệ thống yêu cầu copy hoặc serialize payload, đó là trách nhiệm của bước khác và cần test riêng.

Kiểm thử **setHeaderIfAbsent**:

~~~java
@Test
void shouldKeepExistingHeaderWhenUsingSetHeaderIfAbsent() {
    Message<String> message = MessageBuilder
        .withPayload("ready")
        .setHeader("source", "gateway")
        .setHeaderIfAbsent("source", "fallback")
        .build();

    assertEquals("gateway", message.getHeaders().get("source"));
}
~~~

Kiểm thử copy và remove:

~~~java
@Test
void shouldCopyMessageAndRemoveInternalHeader() {
    Message<String> original = MessageBuilder
        .withPayload("hello")
        .setHeader("correlationId", "corr-1")
        .setHeader("internalDebug", true)
        .build();

    Message<String> copied = MessageBuilder
        .fromMessage(original)
        .setHeader("source", "worker")
        .removeHeader("internalDebug")
        .build();

    assertEquals("hello", copied.getPayload());
    assertEquals("corr-1", copied.getHeaders().get("correlationId"));
    assertEquals("worker", copied.getHeaders().get("source"));
    assertFalse(copied.getHeaders().containsKey("internalDebug"));

    assertTrue(original.getHeaders().containsKey("internalDebug"));
}
~~~

Assertion cuối xác nhận thao tác tạo message mới không làm thay đổi message ban đầu.

Kiểm thử tính bất biến của headers:

~~~java
@Test
void shouldRejectDirectHeaderMutation() {
    Message<String> message = MessageBuilder
        .withPayload("hello")
        .build();

    assertThrows(
        UnsupportedOperationException.class,
        () -> message.getHeaders().put("source", "worker")
    );
}
~~~

Đây là kiểm thử hành vi của **MessageHeaders**. Trong code ứng dụng, nên ưu tiên API builder/accessor thay vì phụ thuộc vào việc bắt exception từ thao tác sửa map.

## 5. Khi cần thay đổi headers: MessageHeaderAccessor

**MessageHeaderAccessor** cung cấp API thao tác headers có kiểm soát. Nó hữu ích khi cần tạo message với nhiều header, làm việc với native headers hoặc cần accessor chuyên biệt của transport.

Ví dụ tạo message qua accessor:

~~~java
MessageHeaderAccessor accessor = new MessageHeaderAccessor();
accessor.setHeader("correlationId", "corr-200");
accessor.setHeader("source", "billing-service");

Message<String> message = MessageBuilder
    .withPayload("payment received")
    .setHeaders(accessor)
    .build();
~~~

Với STOMP, **StompHeaderAccessor** cung cấp các API chuyên biệt để làm việc với command và native STOMP headers. Với message hỗ trợ user/session routing, **SimpMessageHeaderAccessor** có các header dành cho Spring Messaging trên WebSocket.

Không nên coi mọi header ứng dụng là native header của transport. Native headers là metadata do giao thức hoặc adapter quản lý. Khi cần đọc/ghi native header, hãy dùng accessor tương ứng để tránh nhầm giữa header nội bộ của Spring và header trên wire.

### Kiểm thử header theo accessor

Một test có thể xác nhận header được tạo thông qua accessor:

~~~java
@Test
void shouldCreateMessageUsingHeaderAccessor() {
    MessageHeaderAccessor accessor = new MessageHeaderAccessor();
    accessor.setHeader("correlationId", "corr-200");
    accessor.setHeader("source", "billing-service");

    Message<String> message = MessageBuilder
        .withPayload("payment received")
        .setHeaders(accessor)
        .build();

    assertEquals(
        "corr-200",
        message.getHeaders().get("correlationId")
    );
    assertEquals(
        "billing-service",
        message.getHeaders().get("source")
    );
}
~~~

Nếu sử dụng accessor để sửa message đã tồn tại, cần hiểu trạng thái mutable và thời điểm accessor được đóng băng. Không giữ accessor mutable lâu hơn phạm vi xử lý message và không chia sẻ nó giữa nhiều thread.

## 6. MessageConverter làm nhiệm vụ gì?

**MessageConverter** chuyển đổi payload giữa object Java và dạng dữ liệu mà message transport hoặc endpoint cần. Hai phương thức chính là:

- **toMessage(payload, headers)**: chuyển object thành **Message<?>**.
- **fromMessage(message, targetClass)**: chuyển payload của message thành object thuộc kiểu đích.

Một converter có thể quan tâm đến content type để chọn định dạng phù hợp. Ví dụ JSON converter serialize object thành JSON và deserialize JSON thành DTO.

Một số converter thường gặp:

| Converter | Dữ liệu phù hợp |
|---|---|
| **StringMessageConverter** | Chuỗi văn bản |
| **ByteArrayMessageConverter** | Mảng byte |
| **SimpleMessageConverter** | Một số kiểu đơn giản, Serializable và kiểu được hỗ trợ bởi implementation |
| **MappingJackson2MessageConverter** | Object Java và JSON qua Jackson 2 |
| **CompositeMessageConverter** | Kết hợp nhiều converter theo danh sách |

Tên lớp và module có thể khác giữa các thế hệ Spring/Jackson. Hãy kiểm tra phiên bản dependency đang dùng trước khi chọn converter cụ thể.

**MessageConverter** trong Spring Messaging không đồng nghĩa với **HttpMessageConverter** của Spring MVC. Chúng có vai trò tương tự ở mức chuyển đổi dữ liệu nhưng thuộc các abstraction và pipeline khác nhau.

## 7. Kiểm thử JSON converter

Ví dụ dùng **MappingJackson2MessageConverter** để chuyển một event thành JSON message rồi chuyển ngược về DTO.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.util.MimeTypeUtils;

class MessageConverterTest {

    @Test
    void shouldConvertEventToJsonAndBack() {
        MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();

        OrderCreatedEvent event =
            new OrderCreatedEvent("O-100", "CREATED");

        MessageHeaders headers = new MessageHeaders(Map.of(
            MessageHeaders.CONTENT_TYPE,
            MimeTypeUtils.APPLICATION_JSON
        ));

        Message<?> jsonMessage = converter.toMessage(event, headers);

        assertNotNull(jsonMessage);
        assertInstanceOf(String.class, jsonMessage.getPayload());
        assertTrue(
            ((String) jsonMessage.getPayload()).contains("\"orderId\":\"O-100\"")
        );

        Object converted = converter.fromMessage(
            jsonMessage,
            OrderCreatedEvent.class
        );

        assertInstanceOf(OrderCreatedEvent.class, converted);
        assertEquals(event, converted);
    }
}
~~~

Test xác nhận ba điều:

1. Converter tạo được message từ DTO.
2. Payload sau chuyển đổi có dạng JSON như mong đợi.
3. JSON có thể được đọc lại thành đúng kiểu DTO và giữ nguyên dữ liệu.

Trong dự án thực tế, nên kiểm tra content type của message, cấu hình ObjectMapper, naming strategy, date/time module và chính sách xử lý unknown properties. Đừng chỉ kiểm tra JSON chứa một chuỗi con nếu hợp đồng yêu cầu cấu trúc chính xác; có thể parse JSON rồi so sánh từng field hoặc so sánh với JSON fixture đã chuẩn hóa.

### Kiểm thử converter không hỗ trợ payload

Một converter có thể trả về **null** khi không hỗ trợ kiểu payload hoặc định dạng được yêu cầu. Vì vậy, test nên xác nhận cả trường hợp thành công lẫn trường hợp không chuyển đổi được.

~~~java
@Test
void shouldReturnNullWhenTargetTypeIsUnsupported() {
    MappingJackson2MessageConverter converter =
        new MappingJackson2MessageConverter();

    Message<byte[]> message = MessageBuilder
        .withPayload(new byte[] {1, 2, 3})
        .setHeader(
            MessageHeaders.CONTENT_TYPE,
            MimeTypeUtils.APPLICATION_OCTET_STREAM
        )
        .build();

    Object result = converter.fromMessage(message, OrderCreatedEvent.class);

    assertNull(result);
}
~~~

Hành vi chính xác còn phụ thuộc converter và cấu hình phiên bản. Nếu converter được đặt trong một pipeline có nhiều delegate, converter khác có thể xử lý message sau khi converter đầu tiên không nhận dạng được. Vì vậy, hãy test cả converter riêng lẻ và toàn bộ converter chain mà ứng dụng sử dụng.

## 8. Kiểm thử header và payload độc lập

Một lỗi phổ biến là vô tình serialize metadata vào payload hoặc giả định header sẽ tự động trở thành một field JSON.

Ví dụ message có payload event và correlation ID:

~~~java
Message<OrderCreatedEvent> message = MessageBuilder
    .withPayload(new OrderCreatedEvent("O-100", "CREATED"))
    .setHeader("correlationId", "corr-100")
    .setHeader(
        MessageHeaders.CONTENT_TYPE,
        MimeTypeUtils.APPLICATION_JSON
    )
    .build();
~~~

Khi converter serialize payload, đối tượng được chuyển đổi là **OrderCreatedEvent**. Header **correlationId** vẫn thuộc **MessageHeaders**; nó không tự động trở thành field trong JSON. Adapter transport có thể ánh xạ một số header sang native headers hoặc metadata, tùy theo giao thức.

Nên viết assertion riêng:

~~~java
assertEquals("O-100", message.getPayload().orderId());
assertEquals(
    "corr-100",
    message.getHeaders().get("correlationId")
);
assertEquals(
    MimeTypeUtils.APPLICATION_JSON,
    message.getHeaders().get(MessageHeaders.CONTENT_TYPE)
);
~~~

Cách tách assertion giúp xác định lỗi nằm ở payload, header hay converter.

## 9. Kiểm thử converter chain và cấu hình endpoint

Khi ứng dụng có nhiều định dạng, một converter đơn lẻ có thể không đủ. **CompositeMessageConverter** cho phép kết hợp nhiều converter để tìm converter phù hợp.

Ví dụ tạo composite:

~~~java
CompositeMessageConverter converter = new CompositeMessageConverter(
    List.of(
        new StringMessageConverter(),
        new ByteArrayMessageConverter(),
        new MappingJackson2MessageConverter()
    )
);
~~~

Thứ tự delegate và khả năng hỗ trợ MIME type ảnh hưởng đến converter được chọn. Nếu hai converter cùng nhận một loại payload hoặc content type, cần kiểm tra thứ tự và cấu hình thực tế. Không nên dựa vào thứ tự ngẫu nhiên hoặc default không được ghi nhận.

Trong Spring STOMP, các converter được cấu hình cho message broker và được sử dụng khi chuyển payload của message đến/đi từ handler. **SimpMessagingTemplate** cũng sử dụng converter để hỗ trợ **convertAndSend** và **convertAndReceive**.

Ví dụ gửi object:

~~~java
messagingTemplate.convertAndSend(
    "/topic/orders/created",
    event,
    Map.of("correlationId", "corr-100")
);
~~~

Khi kiểm thử template hoặc endpoint, cần xác nhận destination, payload và headers sau khi conversion. Một unit test chỉ gọi converter không chứng minh rằng broker adapter đã map headers đúng như mong muốn.

### Phân biệt RSocket codec

Với RSocket trong Spring, phần chuyển đổi data payload thường được cấu hình qua **RSocketStrategies** với **Encoder** và **Decoder**. Đây là codec abstraction dành cho RSocket, không nên mặc định thay thế nó bằng **MessageConverter** của STOMP hoặc messaging template.

Nếu ứng dụng hỗ trợ nhiều transport, hãy kiểm thử riêng:

- Spring Message và MessageConverter ở pipeline messaging tương ứng.
- Encoder/Decoder và MIME type trong RSocket.
- Native headers/metadata mapping của từng transport.

Chung một DTO không có nghĩa mọi transport sẽ serialize nó theo cùng cách.

## 10. Kiểm thử lỗi chuyển đổi và dữ liệu không hợp lệ

Ngoài trường hợp thành công, cần kiểm thử dữ liệu thiếu, sai kiểu, JSON không hợp lệ và content type không được hỗ trợ.

Các tình huống cần xác nhận:

- Payload JSON sai cú pháp.
- JSON hợp lệ nhưng thiếu field bắt buộc.
- Giá trị field có kiểu không tương thích.
- Content type không khớp với payload thực tế.
- Converter không hỗ trợ target class.
- Header bắt buộc như correlation ID bị thiếu.
- Header có giá trị sai kiểu hoặc sai định dạng.
- Payload quá lớn hoặc vượt giới hạn được ứng dụng cho phép.

Không nên nuốt lỗi conversion rồi trả về một DTO rỗng hoặc giá trị mặc định không rõ ràng. Hãy chuyển lỗi thành exception hoặc error signal có ý nghĩa, ghi log an toàn và trả lỗi theo hợp đồng của transport.

Đối với header, validation nên diễn ra ở ranh giới tiếp nhận message. Ví dụ:

~~~java
String correlationId = message.getHeaders().get(
    "correlationId",
    String.class
);

if (correlationId == null || correlationId.isBlank()) {
    throw new IllegalArgumentException(
        "Missing correlationId header"
    );
}
~~~

Không đưa toàn bộ headers hoặc payload nhạy cảm vào exception message. Chỉ log những metadata đã được cho phép.

## 11. Checklist kiểm thử

- [ ] MessageBuilder tạo đúng payload và các header ứng dụng.
- [ ] **setHeaderIfAbsent** giữ nguyên header đã tồn tại.
- [ ] **copyHeaders** và **copyHeadersIfAbsent** được dùng đúng semantics.
- [ ] **fromMessage** tạo message mới mà không làm thay đổi message ban đầu.
- [ ] **removeHeader** loại bỏ đúng metadata cần thiết.
- [ ] MessageHeaders không bị sửa trực tiếp.
- [ ] Header hệ thống và header ứng dụng được phân biệt rõ.
- [ ] Content type được đặt đúng với định dạng payload.
- [ ] Converter serialize và deserialize đúng kiểu dữ liệu.
- [ ] Converter không hỗ trợ payload được xử lý đúng.
- [ ] Converter chain chọn đúng delegate theo cấu hình.
- [ ] Header và payload được kiểm thử độc lập.
- [ ] Native headers được kiểm thử theo đúng transport adapter.
- [ ] RSocket Encoder/Decoder được kiểm thử riêng với MIME type tương ứng.
- [ ] Có test cho JSON lỗi, field thiếu, sai kiểu và header bắt buộc bị thiếu.

## 12. Tài liệu tham khảo

- [Spring Framework Reference: Message](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message.html) — mô hình message, headers và accessor.
- [Spring Framework API: MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html) — tạo message, sao chép và cập nhật headers.
- [Spring Framework API: MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html) — header chuẩn và tính bất biến.
- [Spring Framework API: MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html) — hợp đồng chuyển đổi payload.
- [Spring Framework Reference: STOMP Message Conversion](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html) — cấu hình converter cho STOMP messaging.
- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — RSocketStrategies và codec Encoder/Decoder.

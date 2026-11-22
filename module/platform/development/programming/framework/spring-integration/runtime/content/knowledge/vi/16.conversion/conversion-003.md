# MessageConverter và chuyển đổi message trong Spring Integration

## Mục tiêu bài học

Trong **Spring Integration Runtime**, cùng một thông tin nghiệp vụ có thể xuất hiện dưới nhiều hình thức: chuỗi JSON từ HTTP, mảng byte từ queue, Java object trong service activator hoặc bản ghi được mã hóa để gửi ra broker. Flow chỉ hoạt động đúng khi các endpoint hiểu chính xác **kiểu payload**, **metadata** và **quy tắc chuyển đổi** tại từng ranh giới.

Sau bài này, bạn có thể:

- Giải thích vai trò của **MessageConverter** trong Spring Messaging và vai trò của **transformer** trong Spring Integration.
- Xác định nơi chuyển đổi diễn ra: inbound/outbound adapter, gateway, phương thức handler, channel hoặc transformer tường minh.
- Cấu hình bộ chuyển đổi JSON ↔ Java object; xử lý trường hợp converter không hỗ trợ hoặc dữ liệu không hợp lệ.
- Kiểm soát **contentType**, encoding, kiểu dữ liệu, headers và correlation khi chuyển message.
- Đánh giá ảnh hưởng của conversion tới threading, throughput, transaction, retry, lỗi và message store.
- Kiểm thử cả dữ liệu hợp lệ, dữ liệu lỗi, message bị phát lại và nhiều message chạy đồng thời.

**Phạm vi:** Bài tập trung vào cách message được chuyển và điều phối ở runtime. Nó không giả định rằng mọi protocol adapter đều dùng chung một API converter.

## 1. Cần chuyển đổi message khi nào?

Ví dụ quy trình nhận đơn hàng:

~~~mermaid
flowchart LR
    A["HTTP / broker\nJSON text hoặc bytes"] --> B["Inbound adapter"]
    B --> C["Spring Message\npayload + headers"]
    C --> D["Chuyển đổi JSON → OrderCommand"]
    D --> E["Service activator\nkiểu nghiệp vụ"]
    E --> F["Chuyển OrderEvent → JSON"]
    F --> G["Outbound adapter\nHTTP / broker"]
~~~

Một **Spring Message** gồm payload và tập headers; ví dụ:

~~~text
Message
  payload: byte[] chứa {"orderId":"O-42","amount":125000}
  headers:
    contentType: application/json
    correlationId: checkout-42
    id: ...
    timestamp: ...
~~~

Chuyển đổi payload từ byte[] sang đối tượng Java có thể cần:

1. Đọc bytes theo định dạng và charset phù hợp.
2. Phân tích JSON, xác định cấu trúc/trường.
3. Tạo đối tượng **OrderCommand**.
4. Kiểm tra yêu cầu nghiệp vụ (ví dụ orderId không được rỗng).
5. Quyết định header nào cần giữ, thêm, xóa hoặc thay đổi.

**Deserialize thành công chưa đồng nghĩa dữ liệu hợp lệ về nghiệp vụ.** JSON hợp lệ vẫn có thể thiếu trường bắt buộc, mang amount âm hoặc chứa phiên bản schema không được hỗ trợ.

## 2. MessageConverter khác transformer và serializer thế nào?

| Cơ chế | Mục đích chính | Ranh giới thường gặp |
| --- | --- | --- |
| **MessageConverter** (Spring Messaging) | Chuyển giữa **Message<?>** và đối tượng, thông qua phương thức chuyển đổi và metadata | Converter được một adapter, method resolver hoặc thành phần được cấu hình gọi |
| **Transformer** (Spring Integration) | Một endpoint trong flow biến message/payload đầu vào thành đầu ra; có thể dùng MessageConverter bên trong | Giữa hai channel, dễ nhìn thấy và theo dõi trong message flow |
| **ConversionService** (Spring Core) | Chuyển kiểu Java như String → Integer, enum, value object theo converter đã đăng ký | Ràng buộc kiểu và chuyển tham số; không thay thế parser JSON tùy ý |
| **Serializer/deserializer** | Biến dữ liệu thành bytes/text và ngược lại theo một định dạng | I/O, lưu trữ, truyền qua mạng, broker |
| **Protocol-specific converter** | Chuyển giữa message/record của giao thức và Spring Message hoặc đối tượng | JMS, AMQP, Kafka, HTTP và các adapter tương ứng |

Interface trung tâm của Spring Messaging là **org.springframework.messaging.converter.MessageConverter**:

~~~java
public interface MessageConverter {
    Object fromMessage(Message<?> message, Class<?> targetClass);
    Message<?> toMessage(Object payload, MessageHeaders headers);
}
~~~

- **fromMessage**: lấy message và kiểu đích; trả về đối tượng đã chuyển, hoặc **null** nếu converter không hỗ trợ trường hợp đó. Lỗi chuyển đổi thực sự có thể được báo bằng exception.
- **toMessage**: tạo Spring Message từ payload và headers; có thể trả về **null** nếu không hỗ trợ.
- Một số converter hoặc framework tích hợp hỗ trợ thêm conversion hint, content-type resolver và cấu hình format.

Lưu ý: Đây là **mô tả hợp đồng API**, không phải lời hứa rằng mọi channel sẽ tự động gọi một bean MessageConverter. Đăng ký bean chỉ là một phần; bạn cần nối nó vào đúng adapter/endpoint hoặc gọi tường minh.

Ví dụ dễ nhầm: **org.springframework.jms.support.converter.MessageConverter** có tên giống nhưng phục vụ việc chuyển đổi JMS Message với API riêng. Spring AMQP và Spring Kafka cũng có các converter/record converter ở tầng giao thức. Cần kiểm tra **package, chiều chuyển đổi và điểm áp dụng** trước khi cấu hình.

### Transformer là endpoint trong flow

Transformer không bị giới hạn ở chuyển kiểu dữ liệu. Nó có thể chuẩn hóa JSON, trích một trường, thêm bớt header, làm giàu nội dung hoặc biến một lệnh thành sự kiện. Trong khi đó, một MessageConverter thường đóng vai trò **chiến lược chuyển đổi** được endpoint/adapter gọi.

Nếu cần chuyển rõ ràng giữa hai bước, transformer giúp người đọc biết chính xác **conversion nằm ở đâu**, dễ gắn error flow và đo latency. Nếu adapter đã có conversion phù hợp, không nhất thiết thêm một transformer chỉ để làm lại công việc đó.

## 3. Quyết định conversion tại đúng ranh giới

Trong một flow thực tế có thể có **nhiều lần chuyển đổi**:

~~~text
Broker record bytes
  → [converter/deserializer của adapter]
  → Spring Message<String> hoặc Message<byte[]>
  → [transformer: JSON thành OrderCommand]
  → Message<OrderCommand>
  → [service activator: xử lý nghiệp vụ]
  → Message<OrderEvent>
  → [converter của outbound adapter hoặc transformer]
  → JSON text / bytes / broker record
~~~

Các câu hỏi cần trả lời:

- Adapter đã deserialize thành Java object hay mới chỉ trả bytes/string?
- Bên gửi đặt **contentType** và charset gì? Content type có khớp payload thực tế?
- Đích cần **OrderCommand**, String JSON hay byte[]?
- Header nào là metadata truyền tải, header nào là dữ liệu nghiệp vụ? **correlationId** có cần đi tiếp không?
- Chuyển đổi được làm ở adapter hay transformer? Có vô tình làm **hai lần** không?

Thông thường, nên chọn **một dạng payload nội bộ nhất quán** (ví dụ DTO bất biến) và chuyển sang dạng truyền tải ở rìa hệ thống. Nhờ đó các handler nghiệp vụ không phải tự đoán mỗi lần payload là String, byte[] hay Map.

### Content type không phải bằng chứng tuyệt đối về cấu trúc

Ví dụ header **application/json** cho biết định dạng dự kiến; nó không bảo đảm bytes hợp lệ hoặc payload đã là DTO. Ngược lại, một DTO đã được giải mã có thể vẫn mang contentType cũ nếu transformer chỉ trả payload và framework sao chép headers.

Nên có chính sách rõ ràng:

- Xác minh content type/encoding khi nhận dữ liệu ngoài.
- Bỏ hoặc cập nhật header mô tả biểu diễn cũ khi đổi sang dạng nội bộ.
- Thiết lập lại content type phù hợp khi mã hóa outbound.
- Không suy diễn lớp Java cần tạo từ header type do nguồn không đáng tin cậy cung cấp nếu chưa có allowlist hoặc schema được kiểm soát.

## 4. Ví dụ: dùng MappingJackson2MessageConverter trong transformer

Đây là một ví dụ rút gọn dùng **Spring Messaging MessageConverter** để xử lý JSON. Giả sử ứng dụng đã có **ObjectMapper** được cấu hình (ví dụ Spring Boot cung cấp bean Jackson) và đã bật hạ tầng Spring Integration annotation.

Payload nghiệp vụ:

~~~java
import java.math.BigDecimal;

public record OrderCommand(String orderId, BigDecimal amount) {
}
~~~

Khai báo converter cho đúng mục đích, dùng Jackson chung đã cấu hình:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.messaging.converter.MessageConverter;

@Configuration
class OrderConversionConfiguration {

    @Bean("orderJsonMessageConverter")
    MessageConverter orderJsonMessageConverter(ObjectMapper objectMapper) {
        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter();
        converter.setObjectMapper(objectMapper);
        return converter;
    }
}
~~~

Đặt conversion trong hai transformer tường minh. Một transformer giải mã trước xử lý; transformer còn lại mã hóa trước khi đưa sang adapter outbound:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;
import org.springframework.messaging.converter.MessageConversionException;
import org.springframework.messaging.converter.MessageConverter;
import org.springframework.stereotype.Component;

@Component
class OrderConversionEndpoints {
    private final MessageConverter jsonConverter;

    OrderConversionEndpoints(
            @Qualifier("orderJsonMessageConverter")
            MessageConverter jsonConverter) {
        this.jsonConverter = jsonConverter;
    }

    @Transformer(inputChannel = "rawOrders", outputChannel = "readyOrders")
    public OrderCommand decode(Message<?> input) {
        Object value =
                jsonConverter.fromMessage(input, OrderCommand.class);
        if (!(value instanceof OrderCommand order)) {
            throw new MessageConversionException(
                    input, "Không hỗ trợ kiểu hoặc contentType đầu vào");
        }

        if (order.orderId() == null || order.orderId().isBlank()
                || order.amount() == null
                || order.amount().signum() < 0) {
            throw new MessageConversionException(
                    input, "Dữ liệu OrderCommand không hợp lệ");
        }
        return order;
    }

    @Transformer(inputChannel = "outgoingOrders",
                 outputChannel = "serializedOrders")
    public Message<?> encode(Message<OrderCommand> input) {
        Message<?> output = jsonConverter.toMessage(
                input.getPayload(), input.getHeaders());
        if (output == null) {
            throw new MessageConversionException(
                    input, "Không thể mã hóa OrderCommand thành message");
        }
        return output;
    }
}
~~~

Một message đầu vào có thể được adapter/gateway gửi tới channel **rawOrders**:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<String> raw = MessageBuilder.withPayload("""
        {"orderId":"O-42","amount":125000}
        """)
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .setHeader("correlationId", "checkout-42")
        .build();

// Gửi raw vào channel rawOrders qua producer/gateway đã được cấu hình.
// Transformer decode tạo OrderCommand cho handler ở readyOrders.
~~~

**Điểm cần chú ý khi triển khai ví dụ:**

1. **rawOrders**, **readyOrders**, **outgoingOrders** và **serializedOrders** là các tên channel trong flow; cần nối producer/consumer phù hợp. Annotation không tự tạo một luồng nghiệp vụ hoàn chỉnh.
2. **MappingJackson2MessageConverter** dựa vào content type mà nó hỗ trợ; conversion có thể trả **null** nếu không phù hợp. JSON hỏng hoặc không parse được sẽ gây lỗi chuyển đổi.
3. Transformer **decode** trả payload kiểu OrderCommand. Headers có thể được framework chuyển tiếp, nhưng **contentType** cũ có thể không còn biểu diễn đúng payload nội bộ: cần định nghĩa chính sách header tại ranh giới này.
4. Transformer **encode** trả một Message đầy đủ, để converter tự tạo payload/headers theo cấu hình. Không suy đoán payload outbound luôn là String: tùy converter, nó có thể là **byte[]**. Xác minh yêu cầu của adapter đích.
5. Đối với **Message<?>** được tạo mới, cần kiểm tra header correlation, trace và business headers có được giữ như mong đợi hay không. Đừng coi ID/timestamp và các header đặc biệt là dữ liệu có thể tùy ý sao chép.
6. Ví dụ minh họa conversion trong Java 17+/Spring hiện đại. Trong Spring Integration thực tế, có thể thay transformer thủ công bằng các transformer JSON có sẵn hoặc dùng converter do adapter hỗ trợ khi phù hợp.

### Tại sao kiểm tra null và validation lại quan trọng?

Converter có thể hiểu kiểu đầu vào nhưng không chuyển sang kiểu đích được, hoặc không hỗ trợ content type. Phân biệt hai tình huống:

| Tình huống | Ví dụ | Cách phản ứng |
| --- | --- | --- |
| Không hỗ trợ conversion | Text CSV gửi vào converter chỉ nhận JSON | Từ chối định dạng/đi tuyến phù hợp; không ép kiểu tùy tiện |
| Dữ liệu hỏng | JSON thiếu dấu ngoặc, bytes sai encoding | Ghi nhận conversion failure, chuyển error flow/DLQ theo chính sách |
| Parse được nhưng sai nghiệp vụ | amount âm, orderId rỗng | Validation error rõ ràng; thường không retry vô hạn |
| Schema thay đổi | Trường bắt buộc bị đổi tên | Quy tắc tương thích schema và versioning |
| Payload đã là kiểu đích | OrderCommand đi vào chặng chỉ nhận OrderCommand | Có thể bỏ qua conversion tốn kém; bảo đảm type contract |

## 5. ConversionService, datatype channel và phương thức handler

**ConversionService** của Spring chuyển đổi các kiểu Java qua những **Converter** hoặc **GenericConverter** đã đăng ký. Ví dụ String → Long, enum hoặc kiểu value object tùy cấu hình.

Spring Integration còn có cơ chế **datatype channel**: channel có thể được khai báo kiểu payload được phép; nếu cấu hình thêm converter thích hợp, framework có thể thử chuyển payload tới kiểu được khai báo trước khi dispatch. Đây là **ràng buộc kiểu tại channel**, không phải công cụ parse mọi JSON tự động.

Tương tự, khi method handler có tham số cụ thể:

~~~java
import org.springframework.integration.annotation.ServiceActivator;

@ServiceActivator(inputChannel = "readyOrders")
public void handleOrder(OrderCommand command) {
    // command đã có đúng kiểu theo hợp đồng của channel/endpoint.
    // Tiến hành xử lý nghiệp vụ.
}
~~~

Framework có cơ chế phân giải tham số và có thể sử dụng conversion đã được cấu hình cho một số kiểu tham số. **Không nên dựa vào việc một String JSON sẽ tự biến thành OrderCommand** chỉ vì tên tham số của method là OrderCommand. Khi dữ liệu đi từ hệ thống ngoài, hãy khai báo conversion tại đúng điểm và kiểm tra bằng integration test.

### Phân biệt ba dạng chuyển đổi dễ bị lẫn

| Đầu vào → đầu ra | Công cụ phù hợp thường gặp | Điều phải kiểm chứng |
| --- | --- | --- |
| String "42" → Long 42 | ConversionService | Format số, null, overflow |
| String/byte[] JSON → OrderCommand | JSON MessageConverter hoặc JSON transformer | Content type, charset, schema, validation |
| JMS/Kafka/AMQP record → Spring Message | Converter/deserializer của adapter giao thức | Payload, headers, transport metadata, acknowledgment |

Không ép kiểu bằng cast nếu đối tượng thực tế vẫn là byte[]/String: cast không giải mã dữ liệu. Ngược lại, không serialize JSON rồi parse lại chỉ để chuyển giữa hai DTO Java nếu mapping trực tiếp có thể diễn đạt rõ hơn.

## 6. Header, content type và correlation trong lúc chuyển đổi

Trong runtime, message có thể mang **messageId**, **correlationId**, **sequenceNumber**, **sequenceSize**, thông tin định tuyến, content type và metadata do adapter tạo. Việc thay payload không tự động biến các headers đó thành đúng/ngữ nghĩa mới.

Ví dụ flow thu thập nhiều phần của đơn hàng:

~~~mermaid
flowchart TD
    A["Phần A: JSON/bytes\ncorrelationId=order-42"] --> CA["Chuyển payload thành DTO A"]
    B["Phần B: JSON/bytes\ncorrelationId=order-42"] --> CB["Chuyển payload thành DTO B"]
    CA --> AG["Aggregator\nnhóm theo correlationId"]
    CB --> AG
    AG --> O["Kết quả tổng hợp"]
~~~

Nếu conversion vô tình làm mất **correlationId** hoặc sửa nó thành giá trị khác, aggregator có thể tạo group sai, chờ mãi hoặc gom nhầm message. Ngược lại, copy toàn bộ header của transport vào message nghiệp vụ có thể khiến metadata của adapter cũ rò sang adapter mới.

Một chính sách thiết kế thường hữu ích:

- **Giữ** business key, correlation key và các trace header đã được cho phép.
- **Làm mới/loại bỏ** content type, kiểu payload hoặc các header chỉ còn đúng cho dữ liệu cũ.
- **Không tin tưởng** header điều khiển class đích đến từ bên ngoài; dùng allowlist/schema do ứng dụng kiểm soát.
- **Phân biệt** message ID kỹ thuật với ID nghiệp vụ/idempotency key. Chuyển đổi tạo message mới có thể thay message ID; không dùng ID kỹ thuật làm khóa nghiệp vụ nếu muốn chống lặp xuyên retry hoặc qua nhiều hệ thống.
- **Kiểm tra** quy tắc header mapping của outbound adapter; một số header chỉ có ý nghĩa trong JVM, không thể hoặc không nên truyền nguyên vẹn lên wire.

Với JSON, charset và định dạng date/time, số decimal, enum, null, unknown fields cần được định nghĩa cùng phía producer và consumer. Thiếu hợp đồng schema khiến hai ứng dụng có thể parse “thành công” nhưng hiểu khác nghĩa.

## 7. Thread safety, hiệu năng và conversion ở runtime

Chuyển đổi thường không có state nghiệp vụ, nhưng **instance converter có thể được dùng đồng thời** bởi nhiều endpoint hoặc thread:

~~~text
Producer A -- DirectChannel --┐
                              ├── shared converter --> handler
Producer B -- DirectChannel --┘

ExecutorChannel --> thread pool --> nhiều lần chuyển đổi song song
Poller / nhiều consumer ---------> nhiều lần chuyển đổi song song
~~~

**DirectChannel chạy đồng bộ theo từng lần gửi**, không có nghĩa toàn bộ consumer chỉ có một thread. ExecutorChannel, poller có task executor và nhiều instance ứng dụng còn tăng khả năng xử lý đồng thời.

Các lưu ý:

- Cấu hình converter/ObjectMapper **trước khi** nhận traffic. ObjectMapper của Jackson thường có thể dùng chung giữa nhiều thread sau khi cấu hình ổn định; tránh chỉnh cấu hình dùng chung trong lúc đang chuyển đổi.
- Không lưu một biến mutable kiểu **currentMessage**, **lastPayload** hoặc buffer dùng chung trong converter nếu không bảo vệ đúng cách. Ưu tiên biến cục bộ và DTO bất biến.
- Không dùng **SimpleDateFormat** chia sẻ trong custom converter nếu không có bảo vệ; dùng **java.time** formatter bất biến hoặc cấu hình Jackson phù hợp.
- JSON mapping, validation và tạo bản sao dữ liệu tiêu tốn CPU và có thể cấp phát nhiều bộ nhớ. Đo kích thước message, latency, allocation và saturation của executor trước khi tăng concurrency.
- Với message lớn, có thể cần giới hạn kích thước, streaming parser hoặc định dạng nhị phân phù hợp. Không đặt toàn bộ payload lớn vào log khi conversion thất bại.
- Với converter không rõ thread-safety do thư viện cung cấp, xem hợp đồng API hoặc kiểm thử concurrent access; **singleton bean không tự làm mã bất biến thành thread-safe**.

### Ví dụ custom converter dễ lỗi

~~~java
// Không an toàn nếu nhiều thread gọi cùng lúc:
class UnsafeConverterState {
    private String currentOrderId;

    void convert(String json) {
        currentOrderId = extractOrderId(json);
        // Thread khác có thể ghi đè currentOrderId tại đây.
        publish(currentOrderId);
    }

    String extractOrderId(String json) { return json; }
    void publish(String id) {}
}
~~~

Trong converter/transformer an toàn hơn, **orderId** là biến cục bộ của một lần gọi; các dependency dùng chung chỉ giữ state khi được thiết kế rõ ràng và đồng bộ đúng phạm vi.

## 8. Lỗi conversion, transaction và retry

Đặt conversion trước handler nghiệp vụ giúp từ chối message sai định dạng sớm. Tuy nhiên, vị trí conversion còn ảnh hưởng đến **cách lỗi xuất hiện và cách retry hoạt động**.

| Chỗ conversion xảy ra | Lỗi thường đi về đâu | Điều cần chú ý |
| --- | --- | --- |
| Đồng bộ qua DirectChannel | Exception thường truyền về caller của send | Nếu sender có transaction cùng thread, lỗi có thể khiến transaction rollback theo cấu hình |
| Sau ExecutorChannel | Lỗi xảy ra trên thread worker | Caller có thể đã hoàn thành send; cần error flow/errorChannel thích hợp |
| Trong polling consumer | Lỗi xuất hiện trong vòng poll/handler | Xem transaction của poller, retry advice và cách nguồn xử lý redelivery |
| Trong inbound adapter/deserializer | Có thể lỗi trước khi tạo Spring Message chuẩn | Định tuyến lỗi, ack, DLQ phụ thuộc adapter/broker |
| Trong outbound adapter | Message nội bộ có thể đã được xử lý trước khi mã hóa | Cần quyết định retry, idempotency, phát trùng sự kiện |

Một converter tốt nên **ném lỗi có ý nghĩa** khi payload sai; không nuốt exception rồi trả dữ liệu trống giống như thành công. Với unsupported format, từ chối rõ ràng hoặc chuyển tới nhánh fallback có chủ đích.

### Retry conversion có ý nghĩa gì?

- **JSON không hợp lệ hoặc schema không tương thích**: retry với cùng bytes thường không giải quyết được; cân nhắc quarantine/DLQ, quan sát và sửa dữ liệu nguồn.
- **Lỗi tạm thời** ở bước tra cứu phụ trợ (nếu conversion có gọi dịch vụ ngoài): có thể retry có backoff, nhưng khi đó conversion không còn là phép biến đổi thuần; cần cân nhắc tách I/O khỏi converter.
- **Lỗi sau conversion và sau side effect**: retry có thể xử lý lại cùng message; phải thiết kế **idempotency** bằng business key, unique constraint hoặc outbox/inbox phù hợp.
- **Transaction**: rollback DB không làm đảo ngược mọi side effect bên ngoài, và transaction gắn với thread của producer không tự động chạy tiếp qua ExecutorChannel.

Nếu message được đặt vào **MessageStore**, cần biết store đang lưu payload **trước hay sau conversion** và serializer dùng cho persistent store. Đổi schema/class ở phiên bản ứng dụng mới có thể khiến message cũ không được đọc lại. Trường hợp lưu group/aggregator, correlation và expiry cũng phải được bảo toàn sau conversion.

## 9. Kiểm thử conversion theo hợp đồng của flow

Tối thiểu nên kiểm tra các nhóm tình huống:

1. **Happy path:** String hoặc byte[] JSON hợp lệ có header application/json chuyển thành DTO đúng giá trị.
2. **Unsupported input:** content type lạ hoặc payload không được hỗ trợ phải có kết quả được định nghĩa rõ (null/exception/fallback).
3. **Malformed payload:** JSON sai cú pháp, thiếu trường, sai kiểu, charset bất thường.
4. **Business validation:** amount âm, orderId rỗng hoặc khóa trùng; phân biệt với lỗi parse.
5. **Header contract:** correlationId, business key, trace headers được giữ/đổi đúng; contentType không bị giữ sai sau đổi biểu diễn.
6. **Outbound round trip:** DTO → message serialized → DTO có thể đọc lại; kiểm tra nội dung và kiểu byte[]/String thực tế của adapter.
7. **Concurrency:** nhiều message khác nhau qua cùng bean converter không làm lẫn dữ liệu hoặc trạng thái.
8. **Retry/redelivery:** phát lại cùng requestId không tạo duplicate side effect nghiệp vụ; lỗi conversion được chuyển tới đúng error flow.
9. **Compatibility:** producer phiên bản cũ/mới tương thích với consumer theo chính sách schema; thử message còn tồn trong persistent store khi nâng cấp.

Ví dụ pseudo-test kiểm tra hai chiều:

~~~java
Message<String> input = MessageBuilder
        .withPayload("""
                {"orderId":"O-42","amount":125000}
                """)
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .build();

Object decoded = jsonConverter.fromMessage(input, OrderCommand.class);
assert decoded instanceof OrderCommand;
assert ((OrderCommand) decoded).orderId().equals("O-42");

Message<?> encoded =
        jsonConverter.toMessage(decoded, input.getHeaders());
assert encoded != null;
assert encoded.getPayload() != null;

// Không ép assert payload == String khi converter có thể xuất byte[].
~~~

Đây là đoạn minh họa logic test, với biến **jsonConverter** đã được khởi tạo từ cấu hình ở trên; trong test thực tế nên dùng assertion library/JUnit và kiểm tra cả lỗi, headers, runtime channel.

### Chẩn đoán khi flow production thất bại

Khi một message “đến channel nhưng handler không nhận đúng dữ liệu”, kiểm tra theo thứ tự:

1. Payload **thực tế** ở đầu vào từng endpoint là kiểu nào? byte[], String, Map hay DTO?
2. Header **contentType** có khớp với payload và converter được chọn không?
3. Converter được cấu hình **ở đâu**; thành phần nào thực sự gọi nó?
4. Converter trả **null**, ném exception hay trả object sai kiểu?
5. Transformer có giữ đúng business/correlation headers không?
6. Đường message có qua **ExecutorChannel**, poller, retry advice hay adapter async không? Error flow có nhận được lỗi?
7. Message bị retry/redelivery bao nhiêu lần, và idempotency key nào phân biệt một nghiệp vụ duy nhất?
8. Số message lỗi tăng cùng payload size/CPU, hay chỉ xảy ra khi nhiều luồng? Kiểm tra thread safety, pool saturation và latency chuyển đổi.

Ghi log tên channel/endpoint, kiểu payload, contentType, correlationId, business key, exception class và nguyên nhân ngắn gọn. Tránh log đầy đủ raw payload có thông tin cá nhân hoặc bí mật.

## 10. Checklist thiết kế

- Xác định **hợp đồng dữ liệu** ở mỗi ranh giới: kiểu payload, định dạng, charset, version, null/optional fields.
- Phân biệt **Spring Messaging MessageConverter**, **Spring Integration transformer** và converter của giao thức.
- Biết chắc conversion xảy ra ở **adapter, channel, method resolver hay transformer**; không chồng nhiều lần vô tình.
- Kiểm soát header **contentType**, **correlationId** và type metadata khi đổi biểu diễn.
- Từ chối payload không hỗ trợ hoặc sai định dạng bằng lỗi rõ ràng; phân biệt lỗi không thể khắc phục với lỗi tạm thời.
- Thiết kế DTO bất biến, converter không giữ state theo message; kiểm thử gọi song song.
- Rà soát transaction, ack/retry và error flow tại các **thread boundary**.
- Tính đến duplicate, persistent message store và schema evolution trước khi cho flow chạy dài hạn.
- Đo latency, throughput và memory theo payload size; tránh deserialize/serialize lại nếu không cần thiết.

## Kết luận

**MessageConverter** tạo cầu nối giữa Spring Message và dạng dữ liệu mà thành phần xử lý cần; **transformer** là bước xử lý tường minh trong message flow, có thể sử dụng MessageConverter hoặc phép biến đổi riêng. Muốn conversion an toàn tại runtime, cần xác định đúng điểm áp dụng, hợp đồng payload/headers, xử lý lỗi và phạm vi concurrency. Khi flow chứa poller, executor, transaction, retry, message store hoặc aggregator, lỗi conversion không chỉ là lỗi parse: nó có thể thay đổi khả năng định tuyến, correlation, khôi phục và tính nhất quán nghiệp vụ.

## Tài liệu tham khảo

- [Spring Framework Javadoc — MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
- [Spring Framework Javadoc — MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MappingJackson2MessageConverter.html)
- [Spring Integration Reference — Message Transformers](https://docs.spring.io/spring-integration/reference/transformer.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)

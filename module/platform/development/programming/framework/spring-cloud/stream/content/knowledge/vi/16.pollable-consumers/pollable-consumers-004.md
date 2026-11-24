# Chuyển đổi kiểu khi đọc thông điệp chủ động

Với consumer thông thường, Spring Cloud Stream gọi hàm xử lý khi message đến và có thể suy ra kiểu payload từ chữ ký của Function hoặc Consumer. Với pollable consumer, ứng dụng chủ động gọi PollableMessageSource.poll() để lấy message. Khi callback nhận Message<?>, kiểu đích không phải lúc nào cũng được suy ra từ lambda. Vì vậy, Spring Cloud Stream cung cấp overload nhận ParameterizedTypeReference<?> để đưa ra gợi ý kiểu cho quá trình chuyển đổi payload.

Bài học này tập trung vào cách đọc message thành POJO, collection và kiểu generic; cách phối hợp kiểu đích với content-type; và cách xử lý lỗi chuyển đổi trong vòng polling. Đây là một phần của mô hình Supplier/Function/Consumer và binding của Spring Cloud Stream: pollable source cung cấp đầu vào, binder kết nối với Kafka, RabbitMQ hoặc broker có hỗ trợ polling, còn converter biến payload trên wire thành kiểu mà nghiệp vụ cần.

## 1. PollableMessageSource và kiểu payload

PollableMessageSource đại diện cho một nguồn message mà ứng dụng lấy dữ liệu theo yêu cầu. Thay vì framework tự gọi consumer mỗi khi message đến, ứng dụng gọi poll() từ một vòng lặp, scheduler hoặc cơ chế điều phối riêng.

Một pollable source có thể được khai báo bằng thuộc tính spring.cloud.stream.pollable-source. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      pollable-source: orders
      bindings:
        orders-in-0:
          destination: orders.created
          group: order-reader
          content-type: application/json
~~~

Tên orders tạo binding đầu vào orders-in-0. Binding kết nối tới destination orders.created, thuộc consumer group order-reader. content-type mô tả định dạng payload để message converter lựa chọn cách giải mã.

Khả năng pollable consumer và các chi tiết acknowledgement phụ thuộc binder. Trước khi chọn mô hình này cho production, hãy xác nhận binder và phiên bản đang dùng hỗ trợ pollable source, cùng với cách nó thực hiện timeout, xác nhận và redelivery.

Khi ứng dụng gọi poll(), callback nhận một Message<?>. Nếu không truyền thông tin kiểu đích, payload có thể vẫn ở dạng byte array, chuỗi hoặc kiểu đã được binder/converter xử lý tùy đường đi dữ liệu. Khi cần một kiểu cụ thể, hãy cung cấp ParameterizedTypeReference:

~~~java
boolean received = ordersIn.poll(
        message -> {
            OrderCreated order = (OrderCreated) message.getPayload();
            process(order);
        },
        new ParameterizedTypeReference<OrderCreated>() {});
~~~

Overload này có chữ ký:

~~~java
boolean poll(MessageHandler handler, ParameterizedTypeReference<?> type);
~~~

type là conversion hint. Framework dùng nó cùng content-type của message hoặc binding để tìm converter phù hợp và chuyển payload sang kiểu yêu cầu. Sau khi chuyển đổi thành công, callback có thể lấy payload dưới dạng OrderCreated.

## 2. Khai báo kiểu dữ liệu và poll một POJO

Giả sử producer phát sự kiện đơn hàng dưới dạng JSON:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "ORD-1001",
  "customerId": "CUS-01",
  "totalMinorUnits": 125500
}
~~~

Khai báo kiểu Java tương ứng:

~~~java
record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        long totalMinorUnits) {}
~~~

Inject PollableMessageSource và cung cấp kiểu đích cho poll():

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.stream.binder.PollableMessageSource;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderPollingConfiguration {

    @Bean
    ApplicationRunner orderPoller(PollableMessageSource ordersIn) {
        return args -> {
            boolean received = ordersIn.poll(
                    message -> {
                        OrderCreated order =
                                (OrderCreated) message.getPayload();
                        System.out.printf(
                                "Order %s from %s, total=%d%n",
                                order.orderId(),
                                order.customerId(),
                                order.totalMinorUnits());
                    },
                    new ParameterizedTypeReference<OrderCreated>() {});

            if (!received) {
                System.out.println("No order message is available");
            }
        };
    }
}
~~~

Ví dụ gọi poll() một lần khi ApplicationRunner chạy để minh họa conversion. Trong ứng dụng hoạt động liên tục, cần gọi poll theo chu kỳ hoặc trong một vòng lặp có kiểm soát; không nên dùng một lần gọi này như một consumer chạy mãi.

poll() trả về true khi đã nhận và xử lý thành công một message, hoặc false khi không có message để xử lý trong lần gọi đó. Có thể dùng kết quả này để quyết định chờ, tiếp tục đọc batch hoặc cập nhật metric.

## 3. Chuyển đổi collection và kiểu generic

Khi payload là collection, kiểu đích cần giữ cả thông tin phần tử. Nếu chỉ dùng List.class, Java type erasure làm mất kiểu của phần tử; converter có thể chỉ tạo danh sách các Map thay vì OrderLine.

Ví dụ payload JSON là một danh sách dòng đơn hàng:

~~~json
[
  { "productId": "SKU-01", "quantity": 2 },
  { "productId": "SKU-02", "quantity": 1 }
]
~~~

Khai báo kiểu:

~~~java
record OrderLine(String productId, int quantity) {}
~~~

Dùng ParameterizedTypeReference<List<OrderLine>>:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.core.ParameterizedTypeReference;

ParameterizedTypeReference<List<OrderLine>> orderLinesType =
        new ParameterizedTypeReference<List<OrderLine>>() {};

boolean received = ordersIn.poll(
        message -> {
            @SuppressWarnings("unchecked")
            List<OrderLine> lines =
                    (List<OrderLine>) message.getPayload();

            for (OrderLine line : lines) {
                reserve(line.productId(), line.quantity());
            }
        },
        orderLinesType);
~~~

Kiểu đích generic cũng áp dụng cho map lồng nhau:

~~~java
ParameterizedTypeReference<Map<String, List<OrderLine>>> groupedLinesType =
        new ParameterizedTypeReference<
                Map<String, List<OrderLine>>>() {};
~~~

ParameterizedTypeReference giữ thông tin kiểu tại runtime thông qua anonymous subclass. Nhờ đó converter có thể biết Map chứa List<OrderLine> thay vì chỉ biết kiểu raw Map.

Hãy đảm bảo JSON thực tế có cấu trúc khớp kiểu đích. Nếu payload là object có trường items chứa danh sách, kiểu đích phải là một record wrapper có trường items, không thể yêu cầu converter biến cả object thành List<OrderLine> một cách tự động.

## 4. Phân biệt content-type và kiểu đích

content-type và ParameterizedTypeReference giải quyết hai câu hỏi khác nhau:

- content-type cho biết dữ liệu đầu vào được biểu diễn theo định dạng nào, ví dụ JSON, văn bản thuần hoặc byte array.
- ParameterizedTypeReference cho biết ứng dụng muốn nhận payload dưới kiểu Java nào, ví dụ OrderCreated hoặc List<OrderLine>.

Hai thông tin được dùng kết hợp để lựa chọn MessageConverter. Chỉ đặt content-type: application/json không đủ để xác định JSON phải trở thành OrderCreated, List<OrderLine> hay một kiểu khác. Ngược lại, yêu cầu kiểu OrderCreated cũng không cho converter biết byte đầu vào là JSON, Avro hay một định dạng tùy chỉnh nếu không có metadata hoặc converter phù hợp.

Ví dụ cấu hình JSON:

~~~yaml
spring:
  cloud:
    stream:
      pollable-source: orders
      bindings:
        orders-in-0:
          destination: orders.created
          group: order-reader
          content-type: application/json
~~~

Một số kiểu phổ biến:

| Content type | Dữ liệu thường gặp | Kiểu đích phù hợp |
|---|---|---|
| application/json | JSON object hoặc array | POJO, record, Map, List<T> |
| text/plain | Văn bản | String |
| application/octet-stream | Byte thô | byte[] |

Spring Cloud Stream có các converter mặc định cho JSON, byte array và text. Nếu không có converter hỗ trợ cặp content type/kiểu đích, quá trình chuyển đổi sẽ thất bại. Hãy kiểm tra header contentType, cấu hình binding và kiểu đích trước khi viết converter riêng.

## 5. Đọc header cùng payload đã chuyển đổi

Conversion hint áp dụng cho payload; callback vẫn nhận một Spring Message<?>, vì vậy có thể đọc headers để lấy metadata:

~~~java
ordersIn.poll(
        message -> {
            OrderCreated order =
                    (OrderCreated) message.getPayload();

            String eventId =
                    (String) message.getHeaders().get("eventId");
            String correlationId =
                    (String) message.getHeaders().get("correlationId");

            audit(order, eventId, correlationId);
        },
        new ParameterizedTypeReference<OrderCreated>() {});
~~~

Header có thể chứa event ID, correlation ID hoặc thông tin truy vết. Không giả định mọi header của producer đều được broker truyền nguyên vẹn; binder có thể ánh xạ hoặc lọc header theo khả năng của broker. Nếu header bắt buộc cho nghiệp vụ, hãy kiểm thử nó qua binder thực tế.

Không dùng header thay cho kiểu đích của payload. Ví dụ eventType: OrderCreated không tự khiến converter tạo OrderCreated nếu callback không cung cấp target type hoặc framework không có metadata kiểu tương ứng.

## 6. Đọc nhiều loại payload trong cùng một nguồn

Một destination có thể chứa nhiều loại sự kiện. Nếu mỗi message có cấu trúc khác nhau, không nên ép tất cả thành một POJO duy nhất rồi kiểm tra cast. Có thể dùng một envelope chung, hoặc đọc payload ở dạng Map/JsonNode rồi định tuyến theo event type.

Ví dụ dùng envelope:

~~~java
import com.fasterxml.jackson.databind.JsonNode;

record EventEnvelope(
        String eventType,
        int schemaVersion,
        JsonNode data) {}
~~~

Đọc envelope từ pollable source:

~~~java
ordersIn.poll(
        message -> {
            EventEnvelope envelope =
                    (EventEnvelope) message.getPayload();

            switch (envelope.eventType()) {
                case "OrderCreated" ->
                        handleCreated(envelope.data());
                case "OrderCancelled" ->
                        handleCancelled(envelope.data());
                default ->
                        handleUnknown(envelope.eventType());
            }
        },
        new ParameterizedTypeReference<EventEnvelope>() {});
~~~

Envelope cần là hợp đồng được producer và consumer thống nhất. Khi data có cấu trúc khác nhau theo event type, có thể chuyển tiếp sang kiểu cụ thể bằng ObjectMapper hoặc converter chuyên biệt sau khi kiểm tra event type và schema version. Phải xác thực đầu vào trước khi chuyển đổi; không tin tưởng một giá trị event type tùy ý từ nguồn bên ngoài.

Một lựa chọn khác là dùng nhiều binding, mỗi binding có content type và kiểu payload riêng. Cách này thường dễ kiểm soát hơn nếu các loại sự kiện có vòng đời, quyền truy cập hoặc consumer group khác nhau.

## 7. Khi nào cần custom MessageConverter?

Converter mặc định xử lý các định dạng thông dụng. Chỉ tạo custom converter khi payload dùng định dạng riêng hoặc có quy tắc chuyển đổi không được hỗ trợ sẵn. Converter cần khai báo content type mà nó xử lý và các kiểu đích được hỗ trợ.

Ví dụ minh họa converter cho một định dạng nhị phân nội bộ application/order-binary:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.converter.AbstractMessageConverter;
import org.springframework.util.MimeType;

class OrderBinaryMessageConverter extends AbstractMessageConverter {

    OrderBinaryMessageConverter() {
        super(new MimeType("application", "order-binary"));
    }

    @Override
    protected boolean supports(Class<?> targetClass) {
        return OrderCreated.class.equals(targetClass);
    }

    @Override
    protected Object convertFromInternal(
            Message<?> message,
            Class<?> targetClass,
            Object conversionHint) {

        byte[] bytes = (byte[]) message.getPayload();
        return OrderBinaryCodec.decode(bytes);
    }
}
~~~

Đăng ký converter dưới dạng bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderConverterConfiguration {

    @Bean
    MessageConverter orderBinaryMessageConverter() {
        return new OrderBinaryMessageConverter();
    }
}
~~~

OrderBinaryCodec đại diện cho bộ giải mã của định dạng riêng. Converter thực tế cần kiểm tra độ dài, magic/version byte, dữ liệu lỗi và giới hạn kích thước trước khi giải mã. Không dùng ví dụ này để thay thế serializer Avro/Protobuf của binder nếu hệ thống đã có serializer/deserializer chuyên dụng.

Converter tùy chỉnh được thêm vào stack converter của Spring Cloud Stream và có thể được ưu tiên trước converter mặc định. Vì vậy, phạm vi supports() và content type phải đủ hẹp để không vô tình chiếm các message JSON hoặc text thông thường.

## 8. Poll theo lịch và xử lý một batch

Không nên tạo vòng lặp polling bận liên tục khi không có message. Có thể dùng @Scheduled để điều khiển nhịp poll và giới hạn số message mỗi lượt:

~~~java
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.cloud.stream.binder.PollableMessageSource;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableScheduling
class PollingScheduleConfiguration {}

@Component
class OrderBatchPoller {

    private final PollableMessageSource ordersIn;

    OrderBatchPoller(PollableMessageSource ordersIn) {
        this.ordersIn = ordersIn;
    }

    @Scheduled(fixedDelay = 500)
    void pollBatch() {
        for (int i = 0; i < 50; i++) {
            boolean received = ordersIn.poll(
                    message -> {
                        OrderCreated order =
                                (OrderCreated) message.getPayload();
                        process(order);
                    },
                    new ParameterizedTypeReference<OrderCreated>() {});

            if (!received) {
                break;
            }
        }
    }
}
~~~

Ví dụ giới hạn 50 message cho mỗi lượt để một batch không chiếm scheduler vô hạn khi destination luôn có dữ liệu. Điều chỉnh batch size và delay theo throughput, thời gian xử lý và khả năng của broker. Nếu callback xử lý lâu, cần cân nhắc thread pool, concurrency và cách binder quản lý acknowledgement.

Nếu ứng dụng có nhiều pollable source, nên phân biệt từng binding bằng tên và qualifier phù hợp với cách phiên bản Spring Cloud Stream đang tạo bean. Không tiêm một nguồn duy nhất rồi giả định nó đại diện cho tất cả input binding.

## 9. Lỗi chuyển đổi và xử lý lỗi khi poll

Chuyển đổi có thể thất bại trước khi callback xử lý nghiệp vụ, ví dụ:

- JSON sai cú pháp hoặc không thể ánh xạ vào kiểu đích.
- Trường bắt buộc thiếu hoặc có kiểu không tương thích.
- content-type khai báo sai định dạng thực tế.
- Callback cast payload sang kiểu khác với kiểu đã yêu cầu.
- Payload nhị phân bị cắt cụt hoặc dùng schema/version không được hỗ trợ.

Có thể bắt lỗi quanh lời gọi poll để ghi nhận và quan sát:

~~~java
try {
    boolean received = ordersIn.poll(
            message -> {
                OrderCreated order =
                        (OrderCreated) message.getPayload();
                process(order);
            },
            new ParameterizedTypeReference<OrderCreated>() {});

    if (!received) {
        metrics.increment("orders.poll.empty");
    }
}
catch (Exception ex) {
    log.error("Could not poll or convert an order message", ex);
    metrics.increment("orders.poll.failure");
}
~~~

Spring Cloud Stream cấu hình error channel cho pollable source. Nếu callback ném exception, một ErrorMessage có thể được gửi đến error channel của binding, thường có dạng <destination>.<group>.errors, và được nối với errorChannel chung của Spring Integration. Nếu không có subscriber xử lý error channel, lỗi có thể chỉ được ghi log và message được xác nhận như đã xử lý thành công. Vì vậy, không được giả định rằng chỉ cần ném exception là message chắc chắn được redeliver.

Nếu error handler ném exception, message thường bị reject theo mặc định và không được requeue. Với các binder hỗ trợ, có thể ném RequeueCurrentMessageException trực tiếp từ callback để yêu cầu broker đưa message trở lại hàng đợi; trường hợp này bỏ qua error channel. Hành vi cụ thể phụ thuộc binder và cấu hình; requeue không giới hạn có thể tạo vòng lặp lỗi và làm nghẽn consumer.

Phân loại lỗi trước khi chọn hành động:

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi dữ liệu vĩnh viễn | JSON sai, trường bắt buộc không hợp lệ | Ghi nhận, cách ly hoặc DLQ; không retry vô hạn |
| Lỗi tạm thời | Dịch vụ phụ thuộc timeout | Retry có giới hạn/backoff hoặc requeue theo chính sách |
| Lỗi lập trình | Cast sai, NullPointerException | Báo động, sửa code; không tạo vòng requeue vô hạn |
| Lỗi hạ tầng | Broker/registry không sẵn sàng | Theo dõi, phục hồi theo binder và chính sách vận hành |

## 10. Acknowledgement và thời điểm hoàn tất callback

Thông thường, poll() xác nhận message khi MessageHandler kết thúc bình thường. Nếu callback kết thúc bất thường, message bị reject theo cơ chế mặc định của pollable source; reject không đồng nghĩa tự động requeue. Muốn thay đổi hành vi cần error handler, exception hoặc cấu hình binder phù hợp.

Vì vậy, callback cần kết thúc sau khi công việc mà ứng dụng coi là hoàn tất đã được thực hiện. Không khởi chạy tác vụ bất đồng bộ rồi return ngay nếu việc xác nhận message phải đợi tác vụ đó hoàn tất:

~~~java
// Không phù hợp nếu acknowledgement phải chờ xử lý:
ordersIn.poll(message -> {
    executor.submit(() -> process(message));
});
~~~

Ở ví dụ trên, callback có thể kết thúc trước khi process() chạy xong; pollable source có thể xác nhận message quá sớm. Nếu cần xử lý bất đồng bộ, hãy chờ kết quả trong phạm vi callback, dùng một mô hình reactive/binder phù hợp hoặc lưu công việc bền vững trước khi callback kết thúc.

Acknowledgement, transaction và redelivery có khác biệt giữa Kafka, RabbitMQ và Pulsar. Kiểm tra semantics của binder đang dùng, nhất là khi callback gọi cơ sở dữ liệu hoặc dịch vụ ngoài. Polling không tự tạo transaction nguyên tử giữa broker và database.

## 11. Phân biệt JSON conversion với native serialization

Với JSON, Spring Cloud Stream thường dùng MessageConverter dựa trên content type và kiểu đích. Với Avro hoặc Protobuf, ứng dụng có thể dùng serializer/deserializer native của binder hoặc converter chuyên biệt.

Nếu binder đã giải mã payload thành object trước khi callback nhận message, không cần chuyển đổi lại. Nếu payload còn là byte[], phải xác định byte đó là JSON, Avro, Protobuf hay định dạng riêng trước khi giải mã. ParameterizedTypeReference chỉ là gợi ý kiểu; nó không tự cung cấp schema registry, serializer hay thuật toán giải mã nhị phân.

Khi dùng Kafka binder với native decoding, kiểm tra cấu hình deserializer và schema registry tương ứng. Với RabbitMQ hoặc Pulsar, kiểm tra cách binder truyền content type, schema metadata và kiểu payload. Không sao chép cấu hình native serializer của Kafka sang binder khác.

## 12. Kiểm thử chuyển đổi kiểu

Kiểm thử nên bao gồm cả payload đơn giản và generic:

1. Gửi JSON hợp lệ và xác nhận payload trở thành đúng POJO.
2. Gửi JSON array và xác nhận phần tử có kiểu cụ thể, không phải Map không định kiểu.
3. Gửi payload thiếu trường hoặc sai kiểu và xác nhận lỗi được quan sát.
4. Thay đổi content type để xác nhận converter được chọn đúng.
5. Gửi message có header correlation/event ID và xác nhận metadata cần thiết còn nguyên.
6. Kiểm tra callback thành công, callback ném exception và hành vi ack/requeue của binder.
7. Kiểm tra với broker thật vì test converter đơn lẻ không chứng minh native decoding và acknowledgement của broker.

Ví dụ kiểm thử converter JSON độc lập:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.http.MediaType;

class OrderPayloadConversionTest {

    @Test
    void convertsJsonPayloadToOrderCreated() {
        String json = """
                {
                  "eventId": "evt-1",
                  "orderId": "ORD-1",
                  "customerId": "CUS-1",
                  "totalMinorUnits": 125500
                }
                """;

        Message<String> message = MessageBuilder.withPayload(json)
                .setHeader(MessageHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON)
                .build();

        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter();

        OrderCreated order =
                (OrderCreated) converter.fromMessage(message, OrderCreated.class);

        assertEquals("ORD-1", order.orderId());
        assertEquals(125500L, order.totalMinorUnits());
    }
}
~~~

Đây là kiểm thử converter độc lập để minh họa mối quan hệ giữa content type và target class. Trong ứng dụng Spring Cloud Stream, converter được quản lý trong stack converter của framework; để xác nhận overload poll(handler, type) hoạt động đúng với binder, cần thêm integration test dùng pollable source và broker/test environment tương ứng.

## 13. Checklist trước khi triển khai

- Pollable source đã được khai báo và binding *-in-0 trỏ đúng destination/group.
- content-type phản ánh định dạng thực tế của payload.
- poll(handler, ParameterizedTypeReference<?>) cung cấp đúng kiểu đích, bao gồm generic type nếu cần.
- Callback kiểm tra payload và header trước khi thực hiện side effect.
- Converter mặc định đủ dùng; custom converter chỉ được thêm khi có định dạng riêng.
- Lỗi chuyển đổi có error channel, log, metric và chính sách reject/requeue rõ ràng.
- Callback không return trước khi công việc cần thiết hoàn tất nếu acknowledgement phụ thuộc callback.
- Retry/requeue có giới hạn và message lỗi vĩnh viễn được cách ly.
- Kiểm thử cả conversion, acknowledgement và hành vi binder thực tế.

Với pollable consumer, ứng dụng chủ động lấy message nên phải cung cấp đủ thông tin cho converter biết định dạng đầu vào và kiểu đích. content-type mô tả payload trên wire; ParameterizedTypeReference mô tả kiểu Java mà callback cần. Khi hai thông tin khớp nhau và converter hỗ trợ, Spring Cloud Stream có thể chuyển JSON, text hoặc dữ liệu tương ứng thành POJO hay generic collection. Kết hợp conversion đúng với xử lý lỗi và acknowledgement có chủ đích giúp pollable consumer đọc dữ liệu an toàn và dự đoán được trong môi trường bất đồng bộ.

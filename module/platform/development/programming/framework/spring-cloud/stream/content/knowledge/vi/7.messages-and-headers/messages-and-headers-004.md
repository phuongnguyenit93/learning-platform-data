# Mã sự kiện, mã tương quan và mã nguyên nhân

Trong một hệ thống xử lý sự kiện, một nghiệp vụ có thể đi qua nhiều service và tạo ra nhiều message. Khi có lỗi, cần trả lời được ba câu hỏi: message cụ thể nào đang được xử lý, message đó thuộc quy trình nghiệp vụ nào, và message nào đã trực tiếp dẫn tới nó. Ba câu hỏi này tương ứng với **event ID**, **correlation ID** và **causation ID**.

Ba mã có phạm vi khác nhau và không nên dùng thay thế cho nhau. Event ID nhận diện một sự kiện; correlation ID liên kết các message thuộc cùng một hành trình; causation ID chỉ ra nguyên nhân trực tiếp tạo ra sự kiện hiện tại. Spring Cloud Stream có thể truyền các mã này trong message header để các service tiếp tục xử lý mà vẫn giữ được ngữ cảnh.

## 1. Ba loại mã giải quyết ba câu hỏi khác nhau

| Mã | Ý nghĩa | Phạm vi | Ví dụ |
|---|---|---|---|
| Event ID (eventId) | Định danh duy nhất cho một lần phát sự kiện | Một event cụ thể | evt-01H... |
| Correlation ID (correlationId) | Gom các message thuộc cùng một quy trình hoặc yêu cầu nghiệp vụ | Toàn bộ hành trình | corr-checkout-9001 |
| Causation ID (causationId) | Định danh message hoặc command trực tiếp gây ra event hiện tại | Quan hệ cha-con trực tiếp | evt-order-created-9001 |

Ví dụ quy trình đặt hàng:

~~~text
OrderCreated
  eventId       = evt-100
  correlationId = corr-900
  causationId   = (không có, đây là event bắt đầu)

        |
        v

PaymentRequested
  eventId       = evt-101
  correlationId = corr-900
  causationId   = evt-100

        |
        v

PaymentAuthorized
  eventId       = evt-102
  correlationId = corr-900
  causationId   = evt-101

        |
        v

OrderConfirmed
  eventId       = evt-103
  correlationId = corr-900
  causationId   = evt-102
~~~

Tất cả sự kiện cùng thuộc quy trình corr-900, nhưng mỗi sự kiện có event ID riêng. Causation ID của PaymentAuthorized là event ID của PaymentRequested, vì đó là sự kiện trực tiếp kích hoạt bước xử lý thanh toán. Nhờ vậy có thể truy ngược chuỗi nguyên nhân thay vì chỉ biết các message thuộc cùng một quy trình.

### Event ID

Event ID phải ổn định trong suốt vòng đời của một event. Producer tạo mã khi hình thành event, sau đó giữ nguyên mã khi gửi lại do timeout hoặc lỗi kết nối. Nếu mỗi lần retry lại sinh event ID mới, consumer sẽ khó nhận biết hai message là cùng một sự kiện và có thể thực hiện nghiệp vụ hai lần.

Có thể dùng UUID hoặc một định dạng định danh duy nhất khác. Nếu event ID chỉ duy nhất trong phạm vi một producer, hãy ghép thêm source hoặc tên producer khi tạo khóa deduplication, ví dụ (source, eventId).

### Correlation ID

Correlation ID thường được tạo ở ranh giới bắt đầu của một quy trình: API nhận yêu cầu, service tiếp nhận command hoặc một hệ thống ngoài gửi sự kiện vào. Các message phát sinh trong cùng quy trình giữ nguyên correlation ID khi đi qua các service.

Không nên tạo correlation ID mới ở mỗi service, vì như vậy mối liên hệ giữa các bước sẽ bị đứt. Nếu một event khởi tạo một quy trình độc lập mới, quy trình đó có thể có correlation ID mới theo quy ước nghiệp vụ.

### Causation ID

Causation ID tham chiếu tới message hoặc command trực tiếp dẫn đến event hiện tại. Với quy ước event-to-event, causation ID của event mới thường bằng event ID của event đầu vào. Nếu một command trực tiếp gây ra event, có thể lưu command ID làm causation ID; điều quan trọng là toàn hệ thống thống nhất cách định nghĩa và ghi rõ loại đối tượng được tham chiếu.

Causation ID chỉ một quan hệ trực tiếp. Muốn truy ngược nhiều bước, lần theo chuỗi causation ID hoặc tra cứu kho lưu trữ event. Correlation ID chỉ gom nhóm, không thể hiện thứ tự hay quan hệ nhân quả.

## 2. Đặt các mã ở đâu: payload hay header?

Spring Messaging biểu diễn một message bằng payload và headers:

~~~text
Message<T>
  ├── payload  : dữ liệu nghiệp vụ
  └── headers  : metadata đi kèm message
~~~

Payload chứa nội dung nghiệp vụ, ví dụ OrderCreated với order ID, customer ID và tổng tiền. Header chứa metadata điều khiển hoặc mô tả việc vận chuyển message, ví dụ event ID, correlation ID, causation ID, content type và thông tin tracing.

Có hai cách tổ chức thường dùng:

- Đặt các mã trong event envelope/payload để chúng trở thành một phần của hợp đồng sự kiện, có thể lưu trữ và trao đổi giữa nhiều nền tảng.
- Đặt các mã trong header để middleware và các thành phần xử lý message có thể đọc metadata mà không cần giải mã payload nghiệp vụ.

Một hệ thống có thể dùng cả hai: giữ event ID và loại sự kiện trong envelope, đồng thời đưa các giá trị cần thiết vào header để routing, logging và propagation. Khi dùng cả hai nơi, phải định nghĩa nguồn dữ liệu chuẩn và kiểm tra chúng nhất quán. Không để payload ghi eventId=A nhưng header lại ghi eventId=B.

Ví dụ envelope:

~~~json
{
  "eventId": "evt-100",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T10:15:30Z",
  "correlationId": "corr-900",
  "causationId": null,
  "data": {
    "orderId": "ord-9001",
    "customerId": "cus-2001",
    "total": 125000
  }
}
~~~

Ví dụ cùng metadata ở header:

~~~text
eventId       = evt-100
eventType     = OrderCreated
correlationId = corr-900
~~~

Không đưa thông tin cá nhân, token, mật khẩu hoặc dữ liệu bí mật vào các ID. Header thường được ghi vào log, metric hoặc công cụ quản trị broker nên cần xem chúng như metadata có thể bị quan sát bởi nhiều thành phần.

## 3. Tạo message và gắn header trong Spring

Spring Messaging cung cấp Message, MessageHeaders và MessageBuilder. Có thể tạo message có payload và gắn metadata như sau:

~~~java
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class OrderEventFactory {

    public Message<OrderCreated> create(
            OrderCreated order,
            String correlationId) {

        String eventId = UUID.randomUUID().toString();

        return MessageBuilder.withPayload(order)
            .setHeader("eventId", eventId)
            .setHeader("eventType", "OrderCreated")
            .setHeader("correlationId", correlationId)
            .build();
    }

    public record OrderCreated(
        String orderId,
        String customerId,
        long total
    ) {}
}
~~~

Ví dụ này giả định mỗi lần gọi create là một quy trình mới. Trong ứng dụng thực tế, correlation ID thường được nhận từ request context hoặc được tạo một lần tại ranh giới tiếp nhận nghiệp vụ. Event ID nên được tạo và lưu cùng event/outbox trước khi gửi để lần gửi lại vẫn dùng cùng mã.

Có thể tạo message từ dữ liệu đã có bằng MessageBuilder.withPayload(...), rồi đặt header bằng setHeader(name, value). Giá trị header nên là kiểu đơn giản có thể serialize được, phổ biến nhất là chuỗi. Không nên đưa object Java tùy biến vào header với giả định mọi binder đều serialize và phục hồi giống nhau.

### Dùng Message trong function

Nếu function cần đọc metadata, khai báo tham số là Message<T> thay vì chỉ nhận payload T:

~~~java
import java.util.UUID;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
public class OrderEventFunctions {

    @Bean
    Function<Message<OrderCreated>, Message<OrderValidated>> validateOrder() {
        return input -> {
            OrderCreated order = input.getPayload();

            String sourceEventId =
                (String) input.getHeaders().get("eventId");
            String correlationId =
                (String) input.getHeaders().get("correlationId");

            if (sourceEventId == null || sourceEventId.isBlank()) {
                throw new IllegalArgumentException("Missing eventId header");
            }

            OrderValidated validated = new OrderValidated(
                order.orderId(),
                order.total()
            );

            MessageBuilder<OrderValidated> output =
                MessageBuilder.withPayload(validated)
                    .copyHeaders(input.getHeaders())
                    .setHeader("eventId", UUID.randomUUID().toString())
                    .setHeader("eventType", "OrderValidated");

            if (correlationId != null) {
                output.setHeader("correlationId", correlationId);
            }
            output.setHeader("causationId", sourceEventId);

            return output.build();
        };
    }

    public record OrderCreated(String orderId, long total) {}
    public record OrderValidated(String orderId, long total) {}
}
~~~

Function giữ nguyên correlation ID của message đầu vào, tạo event ID mới cho event đầu ra và đặt event ID đầu vào làm causation ID. copyHeaders giúp chuyển tiếp các header cần thiết, sau đó function ghi đè những header có ý nghĩa mới. Khi áp dụng trong production, hãy kiểm soát header nào được phép sao chép; không chuyển tiếp tùy tiện credential hoặc metadata nội bộ sang service khác.

Đoạn code trên minh họa cách ánh xạ metadata. Nếu toàn bộ function có thể được chạy lại khi retry, không tạo một event ID mới cho cùng một kết quả nghiệp vụ ở mỗi lần thử. Hãy tạo ID một lần và lưu cùng bản ghi outbox hoặc trạng thái xử lý để mọi lần phát lại cùng event đều dùng cùng ID.

Nếu function chỉ nhận OrderCreated thay vì Message<OrderCreated>, nó không truy cập trực tiếp các header của message. Khi cần dùng event ID, correlation ID hoặc causation ID trong logic, hãy nhận message hoặc chuyển metadata qua một kiểu dữ liệu nghiệp vụ được định nghĩa rõ ràng.

## 4. Truyền mã qua nhiều service

Mỗi service cần giữ đúng ngữ cảnh của message khi tạo event tiếp theo:

1. Đọc event ID, correlation ID và causation ID của message đầu vào.
2. Kiểm tra event ID và metadata bắt buộc theo hợp đồng.
3. Thực hiện nghiệp vụ.
4. Tạo event ID mới cho event đầu ra.
5. Giữ nguyên correlation ID của quy trình hiện tại.
6. Gán causation ID bằng ID của message hoặc command trực tiếp gây ra event mới.
7. Phát message với header và payload nhất quán.

Ví dụ service xử lý thanh toán nhận PaymentRequested rồi phát PaymentAuthorized:

~~~java
import java.util.UUID;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Function<Message<PaymentRequested>, Message<PaymentAuthorized>> authorizePayment() {
    return input -> {
        PaymentRequested request = input.getPayload();

        // Thực hiện xác thực và xử lý thanh toán ở đây.

        return MessageBuilder.withPayload(
                new PaymentAuthorized(request.paymentId(), "AUTHORIZED"))
            .copyHeaders(input.getHeaders())
            .setHeader("eventId", UUID.randomUUID().toString())
            .setHeader("eventType", "PaymentAuthorized")
            .setHeader(
                "causationId",
                input.getHeaders().get("eventId")
            )
            .build();
    };
}
~~~

Ví dụ rút gọn giả định event đầu vào luôn có eventId. Trong ứng dụng thật, phải kiểm tra header bắt buộc trước khi xử lý và định nghĩa cách xử lý message thiếu metadata. Không tạo causation ID bằng một chuỗi tùy ý hoặc bằng correlation ID; causation ID phải trỏ tới đối tượng gây ra sự kiện theo quy ước đã chọn.

Nếu một message tạo ra nhiều event, mỗi event đầu ra có event ID riêng, cùng correlation ID và có thể cùng causation ID trỏ tới message đầu vào. Nếu event được phát ra bởi một quy trình nền không có message đầu vào, cần ghi rõ nguồn gây ra nó, ví dụ command ID, scheduler execution ID hoặc một nguyên nhân hệ thống được định danh.

## 5. Header chuẩn, header tùy chỉnh và header của broker

Spring Messaging định nghĩa một số header chuẩn, chẳng hạn ID của message và timestamp tạo message. Những header này phục vụ vòng đời message trong framework. Chúng không thay thế event ID nghiệp vụ.

| Header | Ý nghĩa | Cách sử dụng |
|---|---|---|
| MessageHeaders.ID | ID do Spring tạo cho đối tượng message | Dùng khi cần định danh message trong phạm vi framework |
| MessageHeaders.TIMESTAMP | Thời điểm tạo message trong framework | Hỗ trợ quan sát thời điểm message được tạo |
| eventId | ID của event nghiệp vụ | Duy trì ổn định qua retry và redelivery |
| correlationId | ID của quy trình nghiệp vụ | Giữ nguyên qua các service trong cùng hành trình |
| causationId | ID của nguyên nhân trực tiếp | Tham chiếu message/command đã gây ra event |
| eventType | Loại sự kiện | Hỗ trợ phân loại và kiểm tra hợp đồng |

Không ghi đè các header dành riêng của Spring như id và timestamp để lưu event ID hoặc thời gian nghiệp vụ. Nếu cần thời điểm xảy ra nghiệp vụ, dùng trường occurredAt trong event envelope hoặc header tùy chỉnh đã thống nhất.

Spring Integration cũng sử dụng header correlationId cho một số luồng gom nhóm message như aggregator. Nếu ứng dụng dùng splitter/aggregator, cần phân biệt correlation ID nghiệp vụ với correlation ID nội bộ của message group. Có thể dùng tên header riêng như businessCorrelationId để tránh vô tình ghi đè metadata điều khiển của Spring Integration.

Khi message đi qua binder, header được ánh xạ sang metadata của broker:

- Kafka lưu header dưới dạng key/value bytes; binder chuyển đổi giá trị theo header mapper và cấu hình tương ứng.
- RabbitMQ dùng message properties và headers của AMQP.
- Pulsar hỗ trợ message properties dạng key/value trên message.

Cách ánh xạ và kiểu dữ liệu được hỗ trợ có thể khác theo binder và phiên bản. Để tương tác ổn định giữa các hệ thống, ưu tiên tên header thống nhất và giá trị chuỗi hoặc kiểu scalar đơn giản. Kiểm thử header thực tế sau khi message đi qua broker, đặc biệt khi dùng header tùy chỉnh, object phức tạp hoặc nhiều ngôn ngữ.

Không giả định mọi header nội bộ của Spring đều được chuyển tiếp nguyên vẹn qua mọi broker. Một số header có thể bị lọc, đổi kiểu, mã hóa hoặc không được hỗ trợ. Header quan trọng với hợp đồng sự kiện cần được kiểm tra bằng integration test.

## 6. Phân biệt correlation ID và distributed trace ID

Correlation ID phục vụ việc liên kết message theo quy trình nghiệp vụ. Trace ID phục vụ distributed tracing để liên kết các span trong một lần quan sát kỹ thuật. Hai mã có thể cùng tồn tại và thường có phạm vi khác nhau.

| Tiêu chí | Correlation ID | Trace ID |
|---|---|---|
| Mục đích | Theo dõi một hành trình nghiệp vụ | Theo dõi một lần thực thi phân tán |
| Vòng đời | Có thể tồn tại lâu qua nhiều bước và nhiều lần xử lý | Theo ngữ cảnh trace do hệ thống tracing quản lý |
| Nguồn tạo | Ứng dụng hoặc hệ thống tiếp nhận nghiệp vụ | Tracing instrumentation/SDK |
| Ví dụ | corr-order-9001 | W3C trace ID trong traceparent |

Một quy trình nghiệp vụ có thể kéo dài nhiều phút hoặc nhiều ngày, trong khi một trace kỹ thuật có thể kết thúc sau một khoảng thời gian ngắn. Khi một message được xử lý lại hoặc một bước bất đồng bộ được kích hoạt sau đó, hệ thống có thể tạo trace mới nhưng vẫn giữ correlation ID cũ.

Với distributed tracing, sử dụng Micrometer Tracing, OpenTelemetry hoặc instrumentation tương thích để truyền trace context như W3C traceparent và tracestate. Không tự đặt correlation ID làm trace ID, cũng không ghi đè header tracing do thư viện quản lý. Correlation ID có thể được thêm vào log để tìm các hoạt động thuộc cùng quy trình.

## 7. Dùng các mã để chống xử lý trùng

Broker có thể giao lại cùng message khi consumer bị dừng trước khi xác nhận, mất kết nối hoặc xử lý vượt timeout. Do đó, consumer cần chịu được việc nhận một event nhiều lần.

Event ID là khóa thích hợp để nhận diện bản sao của cùng một event. Correlation ID không phù hợp làm khóa deduplication vì nhiều event khác nhau trong cùng quy trình có chung correlation ID. Causation ID cũng không phù hợp vì một nguyên nhân có thể tạo ra nhiều event hợp lệ.

Một bảng lưu dấu event đã xử lý có thể có cấu trúc:

~~~sql
CREATE TABLE processed_events (
    source       VARCHAR(200) NOT NULL,
    event_id     VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (source, event_id)
);
~~~

Consumer kiểm tra và ghi nhận khóa (source, eventId) trong cùng transaction với thay đổi nghiệp vụ:

~~~text
BEGIN TRANSACTION

1. Thử INSERT (source, eventId) vào processed_events.
2. Nếu khóa đã tồn tại:
     bỏ qua side effect nghiệp vụ và kết thúc như một lần nhận trùng.
3. Nếu insert thành công:
     thực hiện thay đổi dữ liệu nghiệp vụ.

COMMIT
~~~

Unique constraint giúp hai instance không cùng xử lý một event như hai lần độc lập. Việc ghi nhận event ID và cập nhật nghiệp vụ phải nằm trong cùng transaction nếu cùng cơ sở dữ liệu; nếu tách rời, lỗi giữa hai thao tác vẫn có thể tạo ra trạng thái không nhất quán.

Với side effect ngoài transaction cơ sở dữ liệu, chẳng hạn gọi cổng thanh toán hoặc gửi email, cần thêm idempotency key hoặc cơ chế đối soát của dịch vụ đích. Việc chỉ lưu event ID trong một bảng không thể tự hoàn tác một HTTP request đã thành công.

Khi producer gửi lại do timeout, hãy gửi lại cùng event ID và cùng nội dung event. Nếu nghiệp vụ thực sự tạo ra một sự kiện mới, hãy tạo event ID mới. Không dùng event ID mới cho mỗi lần retry.

## 8. Lưu và phát metadata cùng Transactional Outbox

Nếu service cập nhật cơ sở dữ liệu rồi gửi event tới broker bằng hai thao tác độc lập, có thể xảy ra tình huống ghi database thành công nhưng gửi message thất bại, hoặc message được gửi nhưng transaction database rollback.

Transactional Outbox lưu thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction. Bản ghi outbox nên lưu event ID, event type, payload, correlation ID, causation ID và thời điểm tạo. Tiến trình relay đọc outbox rồi phát message tới broker.

~~~text
Transaction nghiệp vụ
  ├── UPDATE orders
  └── INSERT outbox_events
        event_id
        event_type
        payload
        correlation_id
        causation_id
        created_at

Outbox relay
  └── Publish event với cùng eventId và metadata
~~~

Nếu relay gửi thành công nhưng bị dừng trước khi đánh dấu bản ghi đã gửi, message có thể được phát lại. Consumer vẫn cần idempotency dựa trên event ID. Outbox giúp phối hợp việc ghi dữ liệu và tạo ý định phát event; nó không tự đảm bảo mỗi message chỉ được chuyển tới broker đúng một lần.

Khi phát lại event từ outbox, DLQ hoặc kho lưu trữ, giữ nguyên event ID, correlation ID và causation ID của event gốc. Có thể thêm metadata riêng cho lần replay, ví dụ replayAttempt hoặc replayedAt, để phân biệt lần phát lại với thời điểm event được tạo. Không thay causation ID của event gốc chỉ vì có một thao tác vận hành replay.

## 9. Ghi log, tìm kiếm và bảo vệ metadata

Đưa các mã vào log có cấu trúc để có thể tìm toàn bộ hành trình:

~~~text
timestamp=2026-11-24T10:15:30Z
service=payment-service
eventType=PaymentAuthorized
eventId=evt-102
correlationId=corr-900
causationId=evt-101
orderId=ord-9001
result=SUCCESS
~~~

Nên ghi các trường định danh cùng service, event type, kết quả và thông tin broker phù hợp như topic, partition, offset hoặc message ID. Không cần ghi toàn bộ payload nếu nó chứa dữ liệu nhạy cảm.

Một số nguyên tắc vận hành:

- Dùng correlation ID để tìm log của toàn bộ một quy trình.
- Dùng event ID để tìm mọi lần nhận, retry, redelivery và xử lý của cùng event.
- Dùng causation ID để truy ngược message trực tiếp gây ra một event.
- Kết hợp event ID với source khi phạm vi duy nhất chỉ được đảm bảo trong một producer.
- Không đưa ID có cardinality cao vào label của metric; điều này có thể làm số lượng time series tăng rất lớn. ID chi tiết phù hợp hơn với log và trace.
- Quy định thời gian lưu trữ log, outbox, inbox và bảng deduplication phù hợp với retention và thời gian replay của event.
- Kiểm soát quyền truy cập vì metadata có thể tiết lộ cấu trúc nghiệp vụ và mối quan hệ giữa các dịch vụ.

## 10. Kiểm tra metadata khi message đi qua broker

Unit test cho factory hoặc function có thể xác nhận mã được tạo và truyền đúng. Test binder giúp kiểm tra Spring Cloud Stream binding trong ứng dụng. Integration test với broker thật cần xác nhận header được ánh xạ và giữ lại theo đúng binder.

Một bài kiểm thử nên bao gồm:

1. Producer tạo event ID và correlation ID; xác nhận cả hai có mặt trong message.
2. Function nhận message và phát event mới; event ID thay đổi, correlation ID giữ nguyên, causation ID trỏ tới event đầu vào.
3. Hai event khác nhau trong cùng quy trình có event ID khác nhau nhưng correlation ID giống nhau.
4. Gửi lại cùng event ID; consumer nhận diện duplicate và không lặp side effect.
5. Kiểm tra header sau khi đi qua Kafka, RabbitMQ hoặc Pulsar, kể cả khi có chuyển đổi kiểu dữ liệu.
6. Đưa message vào DLQ và replay; xác nhận metadata gốc vẫn được bảo toàn.
7. Kiểm tra trường hợp thiếu event ID hoặc correlation ID theo chính sách hợp đồng.

Ví dụ kiểm thử logic tạo event:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class OrderEventFunctionsTest {

    @Test
    void newEventKeepsCorrelationAndReferencesCause() {
        OrderEventFunctions functions = new OrderEventFunctions();

        Message<OrderEventFunctions.OrderCreated> input = MessageBuilder
            .withPayload(new OrderEventFunctions.OrderCreated("ord-9001", 125000))
            .setHeader("eventId", "evt-100")
            .setHeader("correlationId", "corr-900")
            .build();

        Message<OrderEventFunctions.OrderValidated> output =
            functions.validateOrder().apply(input);

        assertNotEquals("evt-100", output.getHeaders().get("eventId"));
        assertEquals("corr-900", output.getHeaders().get("correlationId"));
        assertEquals("evt-100", output.getHeaders().get("causationId"));
    }
}
~~~

Kiểm thử trên minh họa ba quy tắc quan trọng: event mới có ID mới, correlation ID được giữ nguyên, causation ID tham chiếu event đầu vào. Trong project thực tế, cần khởi tạo bean hoặc cấu hình test phù hợp với cách tổ chức function của ứng dụng.

## 11. Quy ước metadata cho một hệ thống nhiều service

Trước khi nhiều nhóm cùng phát triển producer và consumer, nên thống nhất một hợp đồng metadata:

| Trường | Quy ước đề xuất |
|---|---|
| eventId | Bắt buộc với event; duy nhất theo phạm vi source |
| eventType | Bắt buộc; tên loại event ổn định |
| correlationId | Bắt buộc với luồng nghiệp vụ cần truy vết nhiều bước |
| causationId | Có khi event được tạo bởi một message/command khác |
| source | Định danh service hoặc producer phát event |
| occurredAt | Thời điểm nghiệp vụ xảy ra, theo UTC |
| schemaVersion | Phiên bản hợp đồng payload |
| traceparent | Trace context theo chuẩn W3C khi tracing được bật |

Quy ước cũng cần xác định:

- Ai tạo event ID và correlation ID.
- Causation ID tham chiếu event hay command, và cách phân biệt hai loại đó.
- Header nào bắt buộc, header nào tùy chọn.
- Tên header và kiểu dữ liệu được dùng trên tất cả binder.
- Cách xử lý message thiếu hoặc sai metadata.
- Cách bảo toàn ID qua retry, DLQ, outbox, replay và migration.
- Cách lưu event ID đã xử lý và thời gian giữ dữ liệu deduplication.

Với event dùng CloudEvents, có thể dùng các thuộc tính chuẩn như id, source, type, subject và time cho metadata sự kiện. Correlation và causation có thể được biểu diễn bằng extension attributes theo quy ước của tổ chức. Không nên tạo một hợp đồng song song mâu thuẫn với CloudEvents nếu hệ thống đã chọn chuẩn này.

## 12. Trình tự thực hành và tiêu chí hoàn thành

| Bước | Thực hành | Kết quả cần đạt |
|---|---|---|
| 1. Định nghĩa event | Tạo envelope có event ID, event type, source và thời điểm xảy ra | Phân biệt định danh event với dữ liệu nghiệp vụ |
| 2. Tạo correlation | Sinh hoặc nhận correlation ID tại ranh giới quy trình | Nhiều message trong cùng hành trình giữ cùng mã |
| 3. Ghi causation | Khi phát event mới, tham chiếu ID của nguyên nhân trực tiếp | Có thể truy ngược quan hệ cha-con |
| 4. Truyền header | Dùng MessageBuilder và Message<T> | Function đọc và phát metadata đúng |
| 5. Kiểm tra binder | Gửi qua broker và đọc lại header | Biết header nào được giữ, đổi kiểu hoặc bị lọc |
| 6. Chống trùng | Lưu khóa source + eventId trong transaction | Redelivery không lặp side effect |
| 7. Quan sát | Đưa mã vào log và kết hợp trace context | Tìm được event và toàn bộ hành trình nghiệp vụ |

Hoàn thành bài khi có thể giải thích sự khác nhau giữa event ID, correlation ID và causation ID; tạo và truyền được chúng qua Spring Cloud Stream; giữ nguyên correlation ID qua nhiều service; gán causation ID cho nguyên nhân trực tiếp; và dùng event ID để chống xử lý trùng khi broker giao lại message.

## 13. Tài liệu tham khảo chính thức

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html) — kiến trúc binding, binder và xử lý message.
- [Spring Messaging — Message](https://docs.spring.io/spring-framework/reference/integration/spring-integration/message.html) — payload, headers và message abstraction.
- [Spring Messaging — MessageBuilder API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html) — tạo message và thao tác với header.
- [Spring Cloud Stream — Functional model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/programming-model.html) — nhận và trả message trong Supplier, Function và Consumer.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — chuẩn truyền trace context giữa các thành phần.
- [CloudEvents Specification](https://github.com/cloudevents/spec) — envelope và metadata chuẩn cho event.
- [Spring Cloud Stream — Kafka binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html) — cấu hình Kafka binder.
- [Spring Cloud Stream — RabbitMQ binder](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html) — ánh xạ message properties và headers với RabbitMQ.
- [Spring Cloud Stream — Pulsar binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — kết nối và metadata message với Pulsar.


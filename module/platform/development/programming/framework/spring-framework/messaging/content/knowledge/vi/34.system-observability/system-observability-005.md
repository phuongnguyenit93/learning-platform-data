# Liên kết log bằng mã thông điệp và mã tương quan trong Spring Messaging

## Mục tiêu

Trong hệ thống messaging, một thao tác nghiệp vụ có thể tạo ra nhiều message, đi qua nhiều queue hoặc channel, được xử lý bất đồng bộ và gọi tiếp nhiều service. Khi có lỗi, một dòng log riêng lẻ thường không đủ để biết message đến từ đâu, thuộc workflow nào, đã được xử lý ở bước nào hoặc có phải là lần giao lại hay không.

Cách giải quyết là ghi các định danh nhất quán vào message headers và log có cấu trúc. Tuy nhiên, message ID, correlation ID, causation ID và trace ID có mục đích khác nhau. Dùng một UUID cho tất cả có thể khiến log trông liên kết được nhưng làm mất ý nghĩa khi retry, fan-out, request/reply hoặc tạo message mới.

Bài này giải thích cách thiết kế các ID đó, cách dùng với Spring JMS và Spring Integration, cách đưa chúng vào log, và cách liên kết chúng với distributed tracing.

## 1. Phân biệt các loại ID

| Định danh | Trả lời câu hỏi | Phạm vi và vòng đời |
| --- | --- | --- |
| Message ID | Đây là message cụ thể nào? | Một message hoặc một lần publish ở tầng transport |
| Event ID | Đây là sự kiện nghiệp vụ nào? | Một sự kiện logic; nên giữ ổn định khi retry hoặc publish lại cùng sự kiện |
| Correlation ID | Message này thuộc cuộc hội thoại hoặc workflow nào? | Nhiều message liên quan có thể dùng chung một ID |
| Causation ID | Message này được tạo ra trực tiếp bởi message nào? | Trỏ tới message/event cha gần nhất |
| Trace ID | Các thao tác phân tán này thuộc trace nào? | Một distributed trace có thể chứa nhiều span và nhiều message |
| Span ID | Thao tác cụ thể nào trong trace đang chạy? | Một đơn vị công việc; mỗi service hoặc operation có span riêng |
| Delivery attempt | Broker đang giao message lần thứ mấy? | Một lần giao/nhận; tăng khi broker redeliver theo chính sách |

Ví dụ một workflow tạo đơn hàng:

- Client gửi command với correlation ID là `workflow-7f2a`.
- Service Orders nhận command có message ID `ID:orders-104`.
- Service Orders tạo event `OrderCreated`, có event ID `evt-9001` và causation ID trỏ tới command `ID:orders-104`.
- Event được gửi tới hai subscriber. Cả hai vẫn dùng correlation ID `workflow-7f2a`, nhưng mỗi lần publish/delivery có thể có message ID riêng.
- Service Billing tạo event `InvoiceIssued`, có event ID mới và causation ID là `evt-9001`.
- Trace ID liên kết các span trong quá trình xử lý, nếu tracing context được truyền qua các ranh giới messaging.

Các ID trả lời các câu hỏi khác nhau. Message ID dùng để tìm một message; correlation ID gom một luồng công việc; causation ID cho biết quan hệ cha-con; trace ID nối các span; event ID nhận diện sự kiện nghiệp vụ bền vững.

## 2. Vì sao không nên dùng một ID cho mọi thứ?

Một message có thể được xử lý lại hoặc được phát sinh từ một message khác:

- **Redelivery:** broker giao lại cùng message sau khi consumer chưa acknowledge. Đây vẫn là message transport đó, nhưng delivery attempt thay đổi.
- **Republish:** ứng dụng tạo và gửi lại một message mới. Broker thường cấp message ID mới, trong khi event ID và correlation ID có thể giữ nguyên.
- **Fan-out:** một message tạo ra nhiều message con. Các message con có message ID riêng nhưng dùng cùng correlation ID; causation ID của chúng trỏ về message nguồn.
- **Request/reply:** reply phải được ghép với đúng request, ngay cả khi nhiều request đang chạy đồng thời.
- **Splitter/aggregator:** một message được tách thành nhiều phần rồi gom lại. Correlation ID nhóm các phần; sequence number và sequence size giúp xác định vị trí và số lượng phần tử.

Nếu dùng message ID làm correlation ID, các message con sẽ mất liên kết với nhau khi mỗi message được broker cấp ID riêng. Nếu dùng trace ID làm event ID, một trace chứa nhiều event sẽ khiến các event bị xem nhầm là cùng một sự kiện. Nếu dùng correlation ID làm idempotency key, các message khác nhau trong cùng workflow có thể bị loại nhầm.

Một quy tắc thực tế:

- Message ID nhận diện một message.
- Event ID nhận diện một sự kiện nghiệp vụ.
- Correlation ID nhận diện một workflow hoặc conversation.
- Causation ID chỉ ra message/event tạo ra message hiện tại.
- Trace ID và span ID phục vụ distributed tracing.
- Idempotency key bảo vệ một thao tác khỏi side effect lặp; nó có thể trùng event ID trong một số thiết kế, nhưng phải được định nghĩa theo nghiệp vụ.

## 3. Các ID trong Spring Messaging

Spring có abstraction chung là `org.springframework.messaging.Message<T>`. Payload chứa dữ liệu; headers chứa metadata để định tuyến, tương quan và xử lý.

### MessageHeaders.ID

`MessageHeaders.ID` là UUID nhận diện một Spring Message instance. Nó không phải ID nghiệp vụ và cũng không nhất thiết là message ID do broker cấp. Trong Spring Integration, khi message được biến đổi và tạo thành message instance mới, ID và timestamp của message mới cũng thay đổi.

Vì vậy, hãy dùng ID này để chẩn đoán một message trong flow nội bộ của Spring. Nếu cần theo dõi cùng một event qua nhiều lần transform hoặc qua nhiều hệ thống, hãy giữ thêm event ID hoặc correlation ID riêng.

### Spring Integration correlation headers

Spring Integration khai báo các header riêng trong `IntegrationMessageHeaderAccessor`:

- `CORRELATION_ID`: nhóm hai hoặc nhiều message có liên quan.
- `SEQUENCE_NUMBER`: vị trí của message trong một nhóm.
- `SEQUENCE_SIZE`: tổng số message trong nhóm khi đã biết.
- `SEQUENCE_DETAILS`: stack thông tin correlation dùng trong các flow lồng nhau như splitter rồi aggregator.

Có thể đọc các header này bằng accessor:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;

public void inspect(Message<?> message) {
    var accessor = new IntegrationMessageHeaderAccessor(message);

    var messageId = message.getHeaders().getId();
    Object correlationId = accessor.getCorrelationId();
    Integer sequenceNumber = accessor.getSequenceNumber();
    Integer sequenceSize = accessor.getSequenceSize();

    log.info(
            "integration_message messageId={} correlationId={} sequence={}/{}",
            messageId,
            correlationId,
            sequenceNumber,
            sequenceSize);
}
~~~

Các header trên thuộc Spring Integration. Ứng dụng chỉ dùng Spring Messaging thuần không nên giả định mọi message đều có `IntegrationMessageHeaderAccessor.CORRELATION_ID`; hãy định nghĩa header của ứng dụng hoặc thêm Spring Integration khi cần các pattern tương ứng.

## 4. JMS message ID và JMS correlation ID

JMS định nghĩa các header chuẩn:

- `JMSMessageID`: định danh message do provider tạo khi gửi. Spring ánh xạ thành `JmsHeaders.MESSAGE_ID`.
- `JMSCorrelationID`: định danh dùng để liên kết message với message khác, thường là request và reply. Spring ánh xạ thành `JmsHeaders.CORRELATION_ID`.
- `JMSReplyTo`: destination nhận reply.
- `JMSRedelivered`: cho biết message đã được giao lại.
- `JMSDestination` và `JMSTimestamp`: destination và thời điểm gửi.

Các header chuẩn này là read-only đối với ứng dụng gửi message. Provider quản lý message ID, timestamp và các giá trị do broker tạo. Producer có thể cấu hình provider không tạo message ID để tối ưu hiệu năng; nếu bật chế độ đó, không được giả định mọi message đều có JMSMessageID.

### Request/reply bằng JMSCorrelationID

Một pattern phổ biến là:

1. Requester gửi request.
2. Broker cấp `JMSMessageID` cho request.
3. Responder nhận request và gửi reply.
4. Responder đặt `JMSCorrelationID` của reply bằng `JMSMessageID` của request.
5. Requester dùng selector hoặc logic tương đương để tìm reply đúng request.

Ví dụ listener nhận request và gửi reply:

~~~java
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class RequestResponder {

    private final JmsTemplate jmsTemplate;

    public RequestResponder(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @JmsListener(destination = "orders.request")
    public void handle(Message request) throws JMSException {
        String requestMessageId = request.getJMSMessageID();
        Destination replyTo = request.getJMSReplyTo();

        if (requestMessageId == null || replyTo == null) {
            throw new JMSException(
                    "Request requires a JMSMessageID and JMSReplyTo");
        }

        jmsTemplate.send(replyTo, session -> {
            TextMessage reply =
                    session.createTextMessage("accepted");
            reply.setJMSCorrelationID(requestMessageId);
            return reply;
        });
    }
}
~~~

Đoạn code minh họa cách lấy message ID của request và gắn nó vào reply. Trong ứng dụng thật, cần xử lý trường hợp thiếu reply destination theo hợp đồng request/reply của ứng dụng. Việc dùng đối tượng `Destination` trực tiếp cũng tránh phụ thuộc vào chuỗi hiển thị của provider.

Một biến thể khác là requester tạo correlation ID riêng trước khi gửi và responder sao chép giá trị đó sang reply. Cả hai bên phải thống nhất một pattern; không trộn lẫn hai cách trong cùng một request/reply flow.

## 5. Correlation ID cho workflow không phải request/reply

Một workflow có thể phát ra nhiều event mà không có một reply duy nhất. Trong trường hợp đó, dùng một application correlation ID ổn định, chẳng hạn `appCorrelationId`, và truyền nó qua các message con.

Với JMS, custom properties chỉ hỗ trợ các kiểu dữ liệu đơn giản theo quy định JMS. Một cách gửi message bằng `JmsTemplate`:

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(
            String payload,
            String correlationId,
            String causationId) {

        jmsTemplate.convertAndSend(
                "orders.events",
                payload,
                message -> {
                    message.setStringProperty(
                            "appCorrelationId", correlationId);

                    if (causationId != null) {
                        message.setStringProperty(
                                "causationId", causationId);
                    }
                    return message;
                });
    }
}
~~~

Ở đây:

- Broker tạo `JMSMessageID` cho message được gửi.
- `appCorrelationId` do ứng dụng quản lý và giữ nguyên trong workflow.
- `causationId` trỏ tới event hoặc command trực tiếp tạo ra event mới.
- `JMSCorrelationID` được giữ cho request/reply hoặc một giao thức đã thống nhất riêng.

Nếu muốn dùng `JMSCorrelationID` cho correlation của workflow, hãy ghi rõ quy ước đó và bảo đảm không xung đột với request/reply. Spring Integration phân biệt header chung `correlationId` với header JMS `jms_correlationId`: header chung thường nhóm message cho aggregator/resequencer, còn JMSCorrelationID thường dùng để ghép request/reply.

## 6. Đọc ID trong @JmsListener

Một listener có thể nhận Spring `Message<T>` để đọc payload cùng các JMS headers đã được Spring ánh xạ:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(destination = "orders.events")
    public void receive(
            Message<String> message,
            @Header(JmsHeaders.MESSAGE_ID) String messageId,
            @Header(JmsHeaders.CORRELATION_ID) String jmsCorrelationId) {

        String payload = message.getPayload();

        log.info(
                "order_message_received messageId={} jmsCorrelationId={} payloadType={}",
                messageId,
                jmsCorrelationId,
                payload.getClass().getSimpleName());

        process(payload);
    }
}
~~~

Nếu cần đọc custom JMS property hoặc thuộc tính transport khác, listener có thể nhận raw `jakarta.jms.Message` và gọi `getStringProperty("appCorrelationId")`, `getJMSRedelivered()` hoặc `getJMSMessageID()`. Cách đọc này phụ thuộc vào JMS API; cách nhận Spring `Message<T>` phù hợp khi muốn dùng abstraction headers của Spring.

Không đưa raw payload vào log chỉ để dễ tìm message. Hãy log loại payload, mã nghiệp vụ an toàn và các ID đã chuẩn hóa.

## 7. Liên kết message ID, correlation ID và causation ID trong log

Một log event nên có tên ổn định và các trường ID tách biệt:

~~~json
{
  "event": "jms_message_processed",
  "destination": "orders.events",
  "messageId": "ID:orders-104",
  "eventId": "evt-9001",
  "correlationId": "workflow-7f2a",
  "causationId": "ID:orders-103",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "deliveryAttempt": 1,
  "outcome": "SUCCESS",
  "durationMs": 18
}
~~~

Tên field có thể khác giữa các hệ thống log, nhưng ý nghĩa cần nhất quán. Dùng cùng tên cho cùng một khái niệm ở producer, broker bridge, consumer và downstream service. Nếu một hệ thống gọi workflow correlation là `requestId` trong khi hệ thống khác gọi là `correlationId`, cần có mapping rõ ràng.

Khi có lỗi, một log record nên cho phép tìm theo một hoặc nhiều khóa:

- Tìm `messageId` để xem một message transport cụ thể.
- Tìm `eventId` để xem một sự kiện nghiệp vụ qua các lần publish hoặc retry.
- Tìm `correlationId` để xem toàn bộ workflow.
- Tìm `causationId` để lần theo quan hệ message cha-con.
- Tìm `traceId` để mở distributed trace và xem thời gian từng span.

Ghi các ID ở cả log publish và log process. Nếu chỉ ghi ở consumer, sẽ khó biết message được tạo ra từ đâu; nếu chỉ ghi ở producer, sẽ khó biết message đã được xử lý hoặc redeliver hay chưa.

## 8. Gắn ID vào MDC an toàn với listener thread

MDC giúp logging framework tự thêm các field như `correlationId` vào mỗi log line trong phạm vi xử lý. Tuy nhiên, listener container thường dùng thread pool. Thread được tái sử dụng cho message tiếp theo; nếu không xóa hoặc khôi phục MDC, log của message sau có thể mang ID của message trước.

Ví dụ với SLF4J MDC:

~~~java
import org.slf4j.MDC;

public void processWithCorrelation(
        String correlationId,
        String messageId,
        String payload) {

    String previousCorrelationId = MDC.get("correlationId");
    String previousMessageId = MDC.get("messageId");

    try {
        if (correlationId != null) {
            MDC.put("correlationId", correlationId);
        }
        if (messageId != null) {
            MDC.put("messageId", messageId);
        }

        log.info("processing_order_message");
        process(payload);
        log.info("order_message_processed");
    }
    finally {
        restoreMdc("correlationId", previousCorrelationId);
        restoreMdc("messageId", previousMessageId);
    }
}

private static void restoreMdc(String key, String previousValue) {
    if (previousValue == null) {
        MDC.remove(key);
    }
    else {
        MDC.put(key, previousValue);
    }
}
~~~

Đây là ví dụ về phạm vi đồng bộ trong một listener method. Nếu xử lý tiếp tục trên executor khác, callback hoặc reactive pipeline, MDC không tự động đi theo mọi thread. Khi đó cần dùng cơ chế context propagation phù hợp hoặc đưa correlation ID thành dữ liệu tường minh trong message/context.

Không giữ MDC sau khi listener kết thúc và không ghi đè context hiện có mà không khôi phục. Việc này đặc biệt quan trọng khi thread pool tái sử dụng worker thread.

## 9. Trace ID và span ID: liên kết qua service

Distributed tracing bổ sung một lớp quan sát cho workflow. Trace ID định danh trace; mỗi lần gọi service hoặc operation tạo span ID riêng. Khi message đi qua broker, producer cần inject trace context vào header và consumer cần extract nó để tạo span tiếp theo.

W3C Trace Context thường dùng:

- `traceparent`: trace ID, parent span ID và trace flags.
- `tracestate`: dữ liệu mở rộng theo vendor.
- Baggage: thuộc tính bổ sung được truyền qua các ranh giới nếu được cấu hình.

Không nên chỉ copy trace ID thành một custom string rồi coi như đã propagation đầy đủ. Việc inject/extract cần giữ parent-child relationship, sampling flags và các thuộc tính context mà tracing implementation quản lý.

Với Micrometer Tracing, dùng tracing bridge/exporter và instrumentation tương thích. Nếu tự truyền context, dùng API Propagator để inject/extract vào carrier thay vì tự parse hoặc dựng `traceparent`.

### JMS instrumentation trong Spring Framework 7

Spring Framework 7 có thể dùng Jakarta JMS instrumentation của Micrometer khi dependency `io.micrometer:micrometer-jakarta9` có trên classpath. Instrumentation tạo observation cho:

- `jms.message.publish`: thời gian gửi message, thường qua `JmsTemplate`, đồng thời propagate tracing information qua outgoing JMS headers.
- `jms.message.process`: thời gian ứng dụng xử lý message, thường qua `MessageListener` hoặc `@JmsListener`, đồng thời extract tracing context từ incoming headers.

Để kích hoạt observation, cấu hình `ObservationRegistry` trên `JmsTemplate` và `JmsListenerContainerFactory` đang dùng. Với listener có factory riêng, registry phải được cấu hình trên đúng factory mà endpoint tham chiếu. Chỉ thêm dependency mà không gắn registry vào các thành phần này có thể chưa đủ để có observations.

Các observation mặc định có high-cardinality key cho message conversation ID, destination name và message ID. Đây là các field phù hợp cho trace/log để tra cứu một message cụ thể; không nên dùng các giá trị thay đổi liên tục này làm metric label.

Phiên bản Spring Framework và Micrometer quyết định instrumentation nào có sẵn. Với Spring Framework 6.x hoặc Spring Boot 3.x, kiểm tra tài liệu đúng phiên bản và dependency management đang dùng trước khi áp dụng cấu hình của Spring 7.

## 10. Spring Integration: correlation, splitter và aggregator

Spring Integration có sẵn correlation header để nhóm các message trong flow:

- Splitter tạo nhiều message con và gắn correlation ID, sequence number, sequence size.
- Aggregator dùng các giá trị này để biết message nào thuộc cùng nhóm và khi nào nhóm đã đủ điều kiện hoàn tất.
- Resequencer dùng sequence number để sắp xếp lại các message trong nhóm.

Không tự thay thế các header này bằng một custom header mà không cập nhật logic aggregator/resequencer. Nếu tạo correlation ID từ nghiệp vụ, hãy dùng cùng ID đó làm correlation key theo flow đã thiết kế.

### Message history

Khi cần biết message đã đi qua các component Spring Integration nào, có thể bật message history:

~~~java
@Configuration
@EnableIntegration
@EnableMessageHistory
public class IntegrationObservabilityConfiguration {
}
~~~

Spring Integration ghi header history và bổ sung thông tin component được theo dõi khi message đi qua flow. Có thể giới hạn component được track để giảm overhead và tránh làm header quá lớn. Message history hữu ích để điều tra đường đi trong ứng dụng; nó không thay thế message ID, correlation ID hoặc distributed trace.

## 11. Chọn nơi ghi ID: log, trace hay metric?

| Nơi lưu | Nên ghi | Không nên |
| --- | --- | --- |
| Structured log | messageId, eventId, correlationId, causationId, traceId, destination, outcome, deliveryAttempt | Raw payload, token, dữ liệu cá nhân không cần thiết |
| Distributed trace | traceId/spanId, messaging operation, destination, message ID/correlation ID theo instrumentation | Đưa secret hoặc payload nhạy cảm vào span attribute |
| Metrics | destination type, operation, outcome, consumer group hoặc route có cardinality thấp | messageId, eventId, correlationId hoặc user ID làm label |
| Audit record | ID nghiệp vụ, actor, action, thời điểm và kết quả theo chính sách | Toàn bộ message hoặc secret không cần cho audit |

Message ID và correlation ID thường có cardinality rất cao. Nếu dùng chúng làm metric tag, số lượng time series tăng theo số message và có thể làm hệ thống metrics quá tải. Hãy dùng log hoặc trace để tra cứu từng message; metrics dùng để đo xu hướng và tỷ lệ.

## 12. Retry, redelivery và message ID

Khi broker redeliver một JMS message, hãy ghi cả message ID và trạng thái redelivery. JMS có `JMSRedelivered`; một số provider cũng cung cấp `JMSXDeliveryCount` để biết số lần giao. Kiểm tra hỗ trợ và ý nghĩa chính xác theo JMS provider.

Phân biệt:

- **Redelivery cùng message:** message transport được broker gửi lại; message ID thường giữ nguyên, delivery attempt tăng.
- **Republish message mới:** ứng dụng gửi một message mới; broker có thể cấp message ID mới. Nếu đây vẫn là cùng một event nghiệp vụ, event ID và correlation ID nên được giữ lại.
- **Tạo event mới:** event ID mới, causation ID trỏ về event/message đã tạo ra nó, correlation ID giữ nguyên nếu còn trong cùng workflow.

ID không tự bảo vệ khỏi xử lý trùng. Dùng idempotency key hoặc bảng inbox/deduplication theo event ID/business key để ngăn side effect lặp. Ghi trạng thái idempotency trong cùng transaction phù hợp với việc xử lý nghiệp vụ.

Khi message vào dead-letter queue, giữ các ID ban đầu và bổ sung thông tin về nguyên nhân, số lần giao, thời điểm chuyển DLQ. Khi phát lại message, quyết định rõ event ID nào được giữ, message ID nào sẽ mới và có cần một replay ID để phân biệt lần phát lại hay không.

## 13. Kiểm thử khả năng liên kết log

Một bộ test hữu ích nên kiểm tra:

1. Producer tạo correlation ID khi bắt đầu workflow và truyền nó vào mọi message con.
2. Broker cấp message ID và listener đọc được ID đó.
3. Causation ID của message con trỏ đúng message/event cha.
4. Nhiều request chạy đồng thời vẫn ghép reply theo đúng correlation key.
5. Redelivery giữ nguyên định danh message phù hợp và ghi nhận delivery attempt.
6. Republish cùng event giữ event ID/correlation ID nhưng nhận message ID mới nếu broker tạo message mới.
7. MDC được khôi phục sau mỗi listener invocation; message sau không nhận ID của message trước.
8. Trace context được propagate qua producer và consumer; trace có quan hệ span đúng.
9. Log không chứa payload bí mật, token hoặc thông tin cá nhân không được phép.
10. Metrics không tạo label theo từng message hoặc workflow ID.

Có thể dùng integration test với broker thật để xác nhận JMS headers/property được gửi và nhận đúng. Với Spring Integration, kiểm tra message headers và sequence metadata qua splitter/aggregator. Với tracing, dùng test observation handler hoặc exporter test để xác nhận context được inject/extract.

## 14. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng message ID làm correlation ID | Message con không còn chung khóa workflow | Tạo correlation ID ổn định cho workflow |
| Dùng trace ID làm event ID | Nhiều event khác nhau bị gộp thành một sự kiện | Tách trace ID khỏi event ID |
| Dùng JMSCorrelationID cho mọi loại correlation | Request/reply có thể ghép sai hoặc xung đột | Quy định riêng JMS request/reply và workflow correlation |
| Không giữ event ID khi republish | Không thể nhận ra cùng event qua các lần gửi | Dùng event ID do ứng dụng quản lý |
| Không ghi causation ID | Khó lần theo chuỗi message cha-con | Gắn causation ID vào message con |
| Chỉ log ID ở consumer | Không biết message được tạo ở đâu | Ghi ID ở publish, process và lỗi |
| Để MDC tồn tại sau listener | Log của message sau bị gắn sai correlation ID | Khôi phục/xóa MDC trong finally |
| Dùng correlation ID làm metric label | Tạo cardinality quá cao | Để ID trong log/trace |
| Copy trace ID thủ công mà bỏ parent span | Trace bị đứt hoặc sai quan hệ | Dùng Micrometer/OpenTelemetry propagation |
| Log toàn bộ header hoặc payload | Có thể lộ secret hoặc dữ liệu cá nhân | Allow-list field và redact dữ liệu nhạy cảm |

## 15. Checklist triển khai

- [ ] Message ID, event ID, correlation ID, causation ID và trace ID có ý nghĩa riêng.
- [ ] Producer ghi message ID/event ID/correlation ID theo đúng tầng.
- [ ] Consumer log các ID cùng destination, outcome và delivery attempt.
- [ ] JMSCorrelationID được dùng nhất quán cho request/reply nếu cần.
- [ ] Workflow correlation được giữ nguyên qua message con, retry và publish lại.
- [ ] Causation ID chỉ ra message/event trực tiếp tạo ra message hiện tại.
- [ ] Spring Integration dùng CORRELATION_ID, SEQUENCE_NUMBER và SEQUENCE_SIZE đúng pattern.
- [ ] Trace context được inject/extract bằng instrumentation hoặc Propagator phù hợp.
- [ ] MDC được khôi phục trong finally và context được propagate qua thread/reactive boundary.
- [ ] Message history chỉ bật ở các flow cần chẩn đoán.
- [ ] ID high-cardinality không được dùng làm metric label.
- [ ] Log không chứa raw payload, token hoặc dữ liệu nhạy cảm.
- [ ] Có test cho request/reply song song, redelivery, republish, fan-out và context propagation.

## Tài liệu tham khảo

- [Spring Framework — Message-driven POJOs with @JmsListener](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): chữ ký listener, JMS headers và cách truy cập raw JMS Message hoặc Spring Message.
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): JmsTemplate, MessageCreator, request/reply và JMS support.
- [Spring Framework Javadoc — JmsHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/JmsHeaders.html): MESSAGE_ID, CORRELATION_ID, REDELIVERED và các header chuẩn.
- [Spring Integration — Message](https://docs.spring.io/spring-integration/reference/message.html): MessageHeaders.ID, IntegrationMessageHeaderAccessor.CORRELATION_ID và sequence headers.
- [Spring Integration — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): phân biệt correlationId chung và JMSCorrelationID, header mapping và request/reply.
- [Spring Integration — Message History](https://docs.spring.io/spring-integration/reference/message-history.html): bật và đọc history header trong flow.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): JMS publish/process observations và tracing propagation.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): tracing API, context propagation và baggage.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): định dạng traceparent và tracestate.


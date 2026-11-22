# Correlation qua message trong Java Logging: nối chuỗi sự kiện giữa producer và consumer

## 1. Correlation qua message là gì?

Trong ứng dụng Java xử lý HTTP đồng bộ, một request có thể được theo dõi bằng request ID và trace. Trong hệ thống **message-driven**, một công việc thường được tách thành nhiều message đi qua Kafka, JMS, RabbitMQ hoặc broker khác. Message có thể chờ trong queue, được xử lý ở một process khác, retry, giao lại nhiều lần, fan-out sang nhiều consumer hoặc được chuyển tới dead-letter queue (DLQ). Nếu mỗi service chỉ ghi log cục bộ mà **không truyền ngữ cảnh tương quan**, người vận hành rất khó biết những dòng log nào cùng thuộc một hành trình nghiệp vụ.

Ví dụ:

~~~text
HTTP request đặt hàng
    |
    v
order-service
    | publish msg-1 (ORDER_ACCEPTED)
    | correlation_id=corr-42
    v
orders topic
    |
    v
invoice-service
    | consume msg-1
    | publish msg-2 (INVOICE_REQUESTED)
    | correlation_id=corr-42
    | causation_id=msg-1
    v
invoice topic
    |
    v
notification-service
      consume msg-2
      correlation_id=corr-42
~~~

**Correlation qua message** là việc đặt các ID phù hợp trong **header/properties/envelope** của message, chuyển chúng qua các bước xử lý và đưa chúng vào log của từng producer/consumer. Một truy vấn correlation_id=corr-42 có thể trả về cả chuỗi xử lý, còn message_id và causation_id chỉ ra message cụ thể và nguyên nhân sinh message tiếp theo.

Điều này khác với **chỉ đặt một biến global currentRequestId**: message có thể chạy song song trên nhiều thread, nên context phải thuộc về **message và processing scope**, không phải toàn bộ JVM.

### Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt correlation ID, message ID, causation ID, request ID, trace ID và span ID.
- Thiết kế hợp đồng metadata và quy tắc tạo/giữ ID giữa các service.
- Viết một ví dụ Java 17 độc lập minh họa propagation qua hai message.
- Hiểu W3C traceparent và OpenTelemetry messaging spans, không nhầm business correlation với distributed tracing.
- Áp dụng vào Kafka headers, JMSCorrelationID, RabbitMQ properties.
- Truyền context đúng qua thread pool, MDC, asynchronous callback và batch.
- Xử lý retry, redelivery, fan-out, fan-in, DLQ, replay và transactional outbox.
- Kiểm thử log correlation mà không làm lộ thông tin nhạy cảm hoặc tạo metric cardinality quá lớn.

## 2. Sáu ID dễ nhầm trong message logging

| Trường | Ý nghĩa | Phạm vi thông thường | Điều không nên suy ra |
| --- | --- | --- | --- |
| correlation_id | Gom các sự kiện trong cùng một workflow nghiệp vụ | Nhiều message và nhiều service | Không phải danh tính đã xác thực |
| message_id | Nhận diện một logical message/envelope theo hợp đồng | Một message, có thể nhiều lần delivery | Không đồng nghĩa correlation ID |
| causation_id | Sự kiện/message nào trực tiếp kích hoạt sự kiện mới | Quan hệ cha → con | Không mô tả đầy đủ fan-in nhiều nguyên nhân |
| request_id | Nhận diện request ở entry point, thường là HTTP | Một request/hop theo hệ thống | Không nhất thiết sống suốt workflow dài |
| trace_id | Nhận diện các spans liên quan trong một trace | Distributed trace theo tracing model | Không tự đồng nghĩa business workflow |
| span_id | Nhận diện một span cụ thể | Một hoạt động được instrument | Không phải message ID |
| delivery_attempt | Lần broker/consumer thử giao hoặc xử lý | Một lượt giao | Không phải logical message mới |
| idempotency_key | Định danh một operation cần chống xử lý lặp | Theo nghiệp vụ | Không thể dùng correlation ID chung cho mọi message |

Ví dụ một workflow có correlation_id=corr-42:

~~~text
msg-1: ORDER_ACCEPTED
msg-2: INVOICE_REQUESTED, causation_id=msg-1
msg-3: STOCK_RESERVATION_REQUESTED, causation_id=msg-1
msg-4: EMAIL_REQUESTED, causation_id=msg-2
~~~

Cả bốn message cùng correlation ID, nhưng có **message ID riêng**. Một sự kiện có thể được redeliver nhiều lần mà vẫn là cùng logical message. Nếu retry tạo một envelope mới, bạn cần giữ original_message_id hoặc operation_id theo hợp đồng để liên kết hai envelope.

**Business entity ID** như order_id cũng không thay thế correlation_id: một đơn hàng có thể trải qua nhiều workflow, và một workflow có thể tác động nhiều entity.

### Correlation không phải causation

Tìm được hai log cùng corr-42 chỉ có nghĩa chúng được gắn chung workflow; không chứng minh log A gây ra log B. Muốn biết quan hệ nhân quả, dùng causation_id, event graph, thứ tự transaction hoặc span relationship thích hợp. Timestamp từ nhiều node có thể bị clock skew và log buffering nên không đủ để kết luận thứ tự chính xác.

## 3. Ai tạo correlation ID và khi nào giữ nguyên?

Một hợp đồng hữu ích có thể là:

1. **Tại entry point đáng tin:** tạo internal correlation ID nếu chưa có một internal ID hợp lệ. Có thể dùng UUID.randomUUID() hoặc ID generator phù hợp.
2. **Nếu có ID từ đối tác/client:** validate định dạng, chiều dài và nguồn tin cậy. Khi cần tách biệt ranh giới tin cậy, lưu external_reference riêng và tạo internal ID mới.
3. **Producer:** giữ correlation ID của workflow đang xử lý, tạo message ID riêng cho message mới và gắn causation_id nếu xuất phát từ message trước đó.
4. **Consumer:** extract và validate headers. Không tự tạo correlation ID mới cho mỗi lần delivery của cùng message nếu workflow đã có ID hợp lệ.
5. **Khi bắt đầu nghiệp vụ thực sự độc lập:** có thể tạo correlation ID mới, lưu link tới workflow cũ nếu có quan hệ.
6. **Retry/DLQ:** bảo toàn correlation và identity logic theo chính sách; thêm metadata retry/delivery riêng.
7. **Log collector:** giữ field correlation dưới dạng searchable field, không chỉ chèn vào một chuỗi tự do.

Ví dụ sinh ID tại nơi khởi tạo workflow:

~~~java
// Java 17 snippet, không phải chương trình độc lập.
String correlationId = java.util.UUID.randomUUID().toString();
~~~

UUID.randomUUID() tạo một ID phù hợp nhiều trường hợp correlation. **Đừng** đặt email, số điện thoại, token, session ID hoặc payload dưới dạng ID để thuận tiện tra cứu. Và UUID **không thay thế authorization**: biết ID không được phép giúp ai đó xem dữ liệu của người khác.

Một số service dùng cùng request ID cho correlation của một HTTP-to-message flow ngắn; có thể hợp lệ nếu hợp đồng rõ. Nhưng workflow chờ nhiều giờ hoặc bắt đầu từ scheduler có thể cần business correlation dài hơn lifetime của một HTTP request.

## 4. Thiết kế message envelope và schema

Một message nên mang dữ liệu nghiệp vụ và metadata riêng:

~~~json
{
  "message_id": "msg-1",
  "event_type": "ORDER_ACCEPTED",
  "schema_version": 1,
  "occurred_at": "2026-11-10T03:00:00Z",
  "payload": {
    "order_id": "O-42"
  },
  "headers": {
    "correlation_id": "corr-42",
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
  }
}
~~~

Đây là **minh họa JSON**: Kafka thường đặt headers riêng với value, JMS có headers/properties, RabbitMQ có BasicProperties; không cần gói mọi header vào JSON body như ví dụ. Tùy framework, tên và kiểu metadata có thể được ánh xạ sang native headers.

| Metadata | Khi dùng | Chính sách quan trọng |
| --- | --- | --- |
| correlation_id | Xuyên workflow | Tạo ở entry point, validate, giới hạn chiều dài |
| message_id | Mỗi logical message | Broker-generated hoặc application-generated có quy ước |
| causation_id | Message mới có nguyên nhân trước | Chỉ tới message/event thực sự kích hoạt |
| original_message_id | Republish/retry tạo envelope mới | Giữ identity của message ban đầu |
| event_type | Message nghiệp vụ | Enum/hằng số do code kiểm soát, không chọn tùy ý từ user |
| traceparent | Hệ thống dùng tracing | Inject/extract bằng tracing propagator tương thích |
| tracestate | Tracing vendor cần | Không để dữ liệu nhạy cảm hoặc header tràn kích thước |
| baggage | Có nhu cầu propagation thật | Giới hạn, tránh token/PII và cross-tenant leak |
| schema_version | Nhiều phiên bản producer/consumer | Có compatibility policy, test replay |
| delivery_attempt | Retry/redelivery | Dựa trên broker/consumer đáng tin thay vì client tự khai |

Cần thống nhất **charset của header** (ví dụ UTF-8 cho custom text ID), giới hạn byte và quy tắc với **duplicate header key**. Đừng cho message từ nguồn bên ngoài tự gán mức log, tên index, quyền truy cập hoặc tenant thực tế chỉ qua một header.

Một schema event logging nên chứa ít nhất: service, event_type, message_id, correlation_id, destination, outcome, timestamp. Thêm causation_id, trace_id/span_id, attempt và error_type khi có giá trị; tránh đẩy toàn bộ message body vào log.

## 5. Producer: tạo envelope, inject context, log kết quả thật

Producer thường:

1. Nhận context nghiệp vụ hợp lệ.
2. Nếu có distributed tracing, tạo producer span hoặc dùng instrumentation phù hợp rồi inject tracing context vào message carrier.
3. Tạo message_id riêng cho message mới.
4. Gắn correlation_id và causation_id khi có message cha.
5. Publish qua broker client, ghi log **attempt**.
6. Khi nhận callback/ack thành công hoặc thất bại, ghi log kết quả tương ứng.

~~~text
event=MESSAGE_PUBLISH_ATTEMPT id=msg-1 correlation_id=corr-42 destination=orders
event=MESSAGE_PUBLISH_ACK id=msg-1 correlation_id=corr-42 outcome=ACKED
~~~

Hai dòng là minh họa. Một lời gọi send() trả về không ném lỗi chưa chắc đồng nghĩa broker đã xác nhận hay consumer đã xử lý. Phân biệt **publish attempted, broker acknowledged, consumer received, processing completed, business committed và message ack/offset commit**.

Đừng ghi một event MESSAGE_PUBLISHED_SUCCESS ngay sau lời gọi async send nếu broker có thể trả lỗi về sau trong callback. Callback có thể chạy ở một thread không có MDC gốc, nên cần **capture correlation ID bất biến** trước khi đăng ký callback hoặc dùng context instrumentation đúng scope.

## 6. Consumer: extract và log trong scope của từng message

Consumer cần:

1. Nhận message cùng headers/properties từ broker.
2. Validate correlation ID và giới hạn kích thước/nguồn metadata.
3. Extract tracing context bằng propagator khi có instrumentation.
4. Mở processing scope cho **message hiện tại**.
5. Đặt MDC/context nếu dùng; ghi received/started, outcome/failed.
6. Thực hiện business logic và publish message kế tiếp với correlation/causation đúng.
7. Close/restore scope trong finally, kể cả khi exception.
8. Ack/commit/settle theo delivery contract và transaction, không dựa trên việc log thành công.

~~~text
Broker delivery
    |
    v
Read headers, validate IDs
    |
    v
Extract tracing context, open scope/MDC
    |
    +-- log received message_id, correlation_id
    +-- process business operation
    +-- publish children if needed
    +-- log completed / failure
    |
    v
Close scope, clear/restore MDC
    |
    v
Ack / commit / retry according to broker semantics
~~~

Tại các consumer chạy trên thread pool, **không dùng một static mutable currentCorrelationId**. Nó có thể bị ghi đè khi hai message đồng thời tới các thread khác nhau. Context phải nằm trong message envelope hoặc context scope của task hiện tại.

## 7. Ví dụ Java 17 chạy độc lập: hai message nối bởi correlation và causation

Chương trình dưới đây chỉ dùng JDK 17: record làm envelope, ArrayDeque làm queue in-memory và java.util.logging.Logger (JUL) in log ra stdout. Không yêu cầu Kafka, Spring hay thư viện ngoài. Giá trị ID được cố định để output có thể đối chiếu chính xác.

**Tệp: MessageCorrelationDemo.java**

~~~java
import java.util.ArrayDeque;
import java.util.Map;
import java.util.Queue;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class MessageCorrelationDemo {
    private static final Logger LOG =
            Logger.getLogger("example.messaging.correlation");

    private static final String TRACE_ID =
            "4bf92f3577b34da6a3ce929d0e0e4736";

    // Chỉ là parser minh họa cho traceparent version 00.
    private static final Pattern TRACEPARENT_V00 =
            Pattern.compile(
                    "00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})");

    record Message(String id, String type,
                   Map<String, String> headers) {
        Message {
            headers = Map.copyOf(headers);
        }
    }

    private static String extractTraceId(String header) {
        if (header == null) return "none";
        Matcher m = TRACEPARENT_V00.matcher(header);
        if (!m.matches()) return "none";
        if (m.group(1).matches("0{32}")
                || m.group(2).matches("0{16}")) return "none";
        return m.group(1);
    }

    private static String correlation(
            Map<String, String> headers) {
        String id = headers.get("correlation_id");
        if (id == null || !id.matches("corr-[0-9]{1,8}")) {
            throw new IllegalArgumentException(
                    "Invalid internal correlation_id");
        }
        return id;
    }

    private static void publish(
            Queue<Message> queue, Message m) {
        String cid = correlation(m.headers());
        LOG.info("publish id=" + m.id()
                + " type=" + m.type()
                + " correlation_id=" + cid
                + " trace_id=" + extractTraceId(
                        m.headers().get("traceparent")));
        queue.add(m);
    }

    private static void consume(
            Queue<Message> queue, Message m) {
        String cid = correlation(m.headers());
        String cause = m.headers()
                .getOrDefault("causation_id", "-");

        LOG.info("consume id=" + m.id()
                + " correlation_id=" + cid
                + " causation_id=" + cause
                + " trace_id=" + extractTraceId(
                        m.headers().get("traceparent")));

        if ("ORDER_ACCEPTED".equals(m.type())) {
            // Giá trị span ID cố định CHỈ cho mô phỏng.
            String childTraceparent =
                    "00-" + TRACE_ID + "-b7ad6b7169203331-01";

            Message child = new Message(
                    "msg-2", "INVOICE_REQUESTED",
                    Map.of(
                            "correlation_id", cid,
                            "causation_id", m.id(),
                            "traceparent", childTraceparent));
            publish(queue, child);
        }
    }

    public static void main(String[] args) {
        Handler output = new Handler() {
            {
                setLevel(Level.INFO);
            }

            @Override
            public synchronized void publish(LogRecord r) {
                if (isLoggable(r)) {
                    System.out.println(r.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush(); // Không đóng System.out.
            }
        };

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(output);

        Queue<Message> queue = new ArrayDeque<>();
        Message root = new Message(
                "msg-1", "ORDER_ACCEPTED",
                Map.of(
                        "correlation_id", "corr-42",
                        "traceparent",
                        "00-" + TRACE_ID
                            + "-00f067aa0ba902b7-01"));

        try {
            publish(queue, root);
            while (!queue.isEmpty()) {
                consume(queue, queue.remove());
            }
        } finally {
            output.flush();
            LOG.removeHandler(output);
            output.close();
        }
    }
}
~~~

**Biên dịch và chạy với JDK 17 trở lên:**

~~~bash
javac -encoding UTF-8 MessageCorrelationDemo.java
java MessageCorrelationDemo
~~~

**Stdout chính xác:**

~~~text
publish id=msg-1 type=ORDER_ACCEPTED correlation_id=corr-42 trace_id=4bf92f3577b34da6a3ce929d0e0e4736
consume id=msg-1 correlation_id=corr-42 causation_id=- trace_id=4bf92f3577b34da6a3ce929d0e0e4736
publish id=msg-2 type=INVOICE_REQUESTED correlation_id=corr-42 trace_id=4bf92f3577b34da6a3ce929d0e0e4736
consume id=msg-2 correlation_id=corr-42 causation_id=msg-1 trace_id=4bf92f3577b34da6a3ce929d0e0e4736
~~~

### Phân tích code

- Message root msg-1 có correlation_id=corr-42 và traceparent version 00 minh họa.
- publish() ghi một event rồi đưa envelope vào queue. Trong mô phỏng in-memory, đó là thao tác queue.add; trong broker thật, publish acknowledgment cần xử lý riêng.
- consume() **đọc lại context từ headers của đúng message**, không dùng giá trị toàn cục.
- Khi xử lý ORDER_ACCEPTED, chương trình tạo msg-2 có message ID mới và causation_id=msg-1, đồng thời giữ correlation_id.
- Hai traceparent trong ví dụ có cùng trace ID và parent-id khác nhau, chỉ để minh họa ý tưởng metadata khi có span gửi mới.
- LOG không truyền lên root JUL handler nhờ setUseParentHandlers(false); custom Handler chỉ in message nên không có timestamp động.
- ArrayDeque xử lý tuần tự, không có concurrency làm thay đổi thứ tự stdout.

**Giới hạn:** Chương trình **không tạo OpenTelemetry spans**, không triển khai W3C Trace Context đầy đủ, không dùng broker thật, không có delivery acknowledgment, persistence hay retry. TRACEPARENT_V00 chỉ kiểm tra version 00, định dạng và hai ID không toàn số 0. Trong production **không tự sinh span ID cố định hoặc tự sửa chuỗi traceparent** như ví dụ. Phải dùng instrumentation/propagator thật để tạo spans mới, inject/extract context và xử lý version/tracestate/flags theo chuẩn.

Regex corr-[0-9]{1,8} chỉ dành cho dữ liệu mẫu. Hệ thống thật có thể dùng UUID/ULID hoặc chuỗi opaque theo hợp đồng riêng, với validation và trust-boundary rules khác. Không đưa mã demo làm authorization hoặc bộ lọc chung cho mọi message thực.

## 8. W3C Trace Context: tương quan tracing khác correlation nghiệp vụ

Một traceparent version 00 có dạng:

~~~text
version-trace-id-parent-id-trace-flags
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

| Thành phần | Định dạng version 00 | Vai trò |
| --- | --- | --- |
| version | Hai chữ số hex, 00 | Xác định format |
| trace-id | 32 chữ số hex lowercase, không toàn 0 | ID cho trace |
| parent-id | 16 chữ số hex lowercase, không toàn 0 | ID span phía gửi/parent context |
| trace-flags | Hai chữ số hex lowercase | Các cờ như sampled |
| tracestate | Trường bổ sung nếu có | Tracing vendor-specific state |

W3C Trace Context định nghĩa các header và quy tắc truyền context; OpenTelemetry sử dụng propagators để inject/extract qua các carrier tương thích. Trong HTTP, traceparent/tracestate là header; trong Kafka/JMS/RabbitMQ, instrumentation có thể lưu chúng trong message headers/properties.

**Trace ID không phải correlation ID do W3C quy định.** Một workflow có thể đi qua nhiều trace vì thời gian chờ, sampling, trust boundary hoặc batch processing. Correlation ID do ứng dụng định nghĩa có thể tồn tại độc lập.

Khi producer tạo message mới, tracing library cần inject **context của producer/create/send span phù hợp**, thay vì giữ nguyên parent-id của message đã tiêu thụ và coi đó là span mới. Consumer extract message creation context rồi tạo process span hoặc link phù hợp.

### Parent-child hay span links?

Message processing khác HTTP request-response: message có thể chờ lâu, fan-out sang nhiều consumer hoặc được xử lý theo batch. **OpenTelemetry messaging semantic conventions** mô tả các operations create, send, receive, process và settle. Tùy loại broker, instrumentation và cardinality của batch, một consumer có thể có span theo quan hệ parent-child hoặc dùng **span links** đến message creation context.

Nếu batch chứa năm message từ năm traces khác nhau, không gán trace context của record đầu tiên thành parent cho toàn batch rồi nói đó là quan hệ nhân quả của cả năm. Dùng model tracing được instrumentation hỗ trợ và kiểm tra mối quan hệ thực trên trace backend.

### Sampling và retention

Một log có correlation_id có thể còn khi trace được sample out hoặc hết retention. Ngược lại một trace được export có thể không chứa đầy đủ log nghiệp vụ. Vì thế cần **hai lớp liên kết** khi phù hợp: business correlation để gom workflow và trace context để tìm spans chi tiết.

Baggage có thể propagate key/value qua nhiều service, nhưng **không dùng baggage làm nơi cất token, cookie, email hoặc thông tin nhạy cảm**. Giới hạn cả chiều dài và số trường, bởi mọi hop nhận context có thể nhìn thấy metadata được truyền.

## 9. MDC trong SLF4J/Logback: mở và đóng theo scope

Trong ứng dụng dùng SLF4J/Logback, MDC cho phép formatter gắn correlation_id/trace_id vào log:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level corr=%X{correlation_id:-} trace=%X{trace_id:-} %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Đây là **Logback XML**, không chạy với JUL hay Log4j 2. MDC chỉ giúp logging context; nó không tạo distributed span.

Trong consumer (snippet cần SLF4J/backend và biến ứng dụng):

~~~java
// cid, traceId đã được validate và lấy từ đúng message.
try (org.slf4j.MDC.MDCCloseable c =
             org.slf4j.MDC.putCloseable("correlation_id", cid);
     org.slf4j.MDC.MDCCloseable t =
             org.slf4j.MDC.putCloseable("trace_id", traceId)) {

    log.info("process_started id={}", messageId);
    processBusinessMessage();
    log.info("process_completed id={}", messageId);
}
~~~

**Snippet không độc lập:** log, cid, traceId, messageId và processBusinessMessage phải do ứng dụng cung cấp. MDCCloseable giúp remove key khi scope đóng. Nếu scope lồng nhau và key đã có giá trị, remove không nhất thiết khôi phục giá trị trước đó; cần snapshot/restore theo thiết kế.

### Thread reuse và rò rỉ correlation

Worker thread có thể xử lý msg-A rồi msg-B. Nếu quên clear/restore, log msg-B có thể vẫn mang correlation của msg-A. Để tránh:

- Extract context riêng ở đầu **mỗi lần xử lý message**.
- Dùng try/finally hoặc scope có auto-close, kể cả khi exception/cancellation.
- Với thread pool/CompletableFuture, capture context bất biến rồi truyền đúng sang task.
- Không tưởng rằng MDC/ThreadLocal tự lan sang mọi executor thread.
- Với Reactor/reactive pipeline, dùng context propagation của framework thay vì dựa trên ThreadLocal trong callback.
- Khi async logging appender chuyển công việc format sang logging worker, kiểm tra backend có capture MDC tại thời điểm tạo log event hay không.

Nếu một producer callback chạy sau khi method publish return, MDC của callback thread có thể khác MDC của producer. Hãy capture correlation/message ID vào biến final/effectively-final của callback hoặc áp dụng instrumentation đúng scope.

### Ví dụ restore một khóa khi chạy task

~~~java
// Snippet SLF4J, không độc lập.
String capturedCid = cid;
executor.submit(() -> {
    String previous = org.slf4j.MDC.get("correlation_id");
    try {
        org.slf4j.MDC.put("correlation_id", capturedCid);
        doWork();
    } finally {
        if (previous == null) {
            org.slf4j.MDC.remove("correlation_id");
        } else {
            org.slf4j.MDC.put("correlation_id", previous);
        }
    }
});
~~~

Snippet chỉ propagate một MDC key, **không** propagate OpenTelemetry Context, principal bảo mật hay transaction context. Ở hệ thống thật, dùng task decorator/instrumentation có kiểm thử để capture/restore toàn bộ context cần thiết.

## 10. Kafka: correlation qua record headers

Kafka record có topic, partition, offset, key, value, timestamp và **headers**. Custom correlation ID thường nằm ở headers; broker **không tự quy định** correlation_id cho tất cả ứng dụng.

Producer dùng kafka-clients (snippet có dependency và biến producer/cid/payload):

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, String> record =
        new ProducerRecord<>("orders.events", "order-42", payload);

record.headers().add(
        "correlation_id",
        cid.getBytes(StandardCharsets.UTF_8));

producer.send(record, (metadata, error) -> {
    if (error == null) {
        log.info("publish_ack topic={} partition={} offset={}",
                metadata.topic(),
                metadata.partition(),
                metadata.offset());
    } else {
        log.error("publish_failed", error);
    }
});
~~~

Consumer đọc header (snippet kafka-clients):

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Header;

// record là ConsumerRecord<String, String> từ poll().
Header h = record.headers().lastHeader("correlation_id");
String correlation = h == null
        ? null
        : new String(h.value(), StandardCharsets.UTF_8);
~~~

**Lưu ý:**

- Đọc lastHeader là lựa chọn API, không chứng minh các header trùng tên khác an toàn. Thiết kế chính sách với duplicate header xung đột và giới hạn byte.
- Một Kafka topic-partition-offset xác định vị trí record trong partition, **không phải business message ID xuyên nhiều topic**.
- Kafka record key dùng cho partitioning/order theo contract; không tự đổi key thành correlation ID chỉ để dễ search log.
- Consumer retry/rebalance/crash có thể khiến cùng record được xử lý lại. Correlation giúp điều tra nhưng consumer vẫn cần idempotency cho side effects.
- Producer send callback không đồng nghĩa toàn workflow đã hoàn thành; log ack broker tách biệt với consumer outcome.
- Nếu consumer tạo message con ở topic khác, giữ correlation_id, tạo ID mới và thêm causation_id/original_message_id khi cần.
- Với Spring Kafka và OpenTelemetry instrumentation, kiểm tra cách propagator inject/extract, listener batch mode và header mapping thực tế theo phiên bản.
- Khi xử lý batch, mỗi record có context riêng; không gán MDC của record đầu tiên cho tất cả.

## 11. JMS/Jakarta Messaging: request/reply và JMSCorrelationID

JMS có các trường:

- **JMSMessageID:** ID của message do provider xử lý/gán theo cơ chế tương ứng.
- **JMSCorrelationID:** correlation field ứng dụng có thể đặt để liên hệ request và reply.
- **JMSReplyTo:** destination trả lời trong request/reply.
- **JMSRedelivered:** chỉ dấu message có thể đã được giao lại, theo broker/provider semantics.

Trong một mẫu request/reply, reply có thể đặt JMSCorrelationID bằng **JMSMessageID của request** để client ghép cặp. Đây là **một quy ước sử dụng**, không có nghĩa mọi JMSCorrelationID đều phải bằng ID request. Một business workflow có thể dùng internal correlation ID riêng qua nhiều event.

Snippet Jakarta Messaging (cần API, session, producer và payload):

~~~java
jakarta.jms.TextMessage msg =
        session.createTextMessage(payload);
msg.setJMSCorrelationID(cid);
msg.setStringProperty("event_type", "ORDER_ACCEPTED");
producer.send(msg);
~~~

Không giả định JMSMessageID đã có giá trị cuối trước khi provider send. Với ứng dụng Java EE cũ dùng javax.jms, import sẽ khác Jakarta Messaging dùng jakarta.jms. Không trộn hai namespace khi framework không tương thích.

Đừng đưa body nhạy cảm, access token hoặc ID quá dài vào JMSCorrelationID. Trong listener, đọc ID từ **message thực**, validate rồi mở MDC/tracing scope trước khi log.

## 12. RabbitMQ/AMQP: properties và ack riêng biệt

RabbitMQ AMQP 0-9-1 Java client có BasicProperties chứa correlationId, messageId, replyTo, headers và thuộc tính khác. Snippet (cần RabbitMQ client và biến channel/body):

~~~java
com.rabbitmq.client.AMQP.BasicProperties properties =
        new com.rabbitmq.client.AMQP.BasicProperties.Builder()
                .correlationId(cid)
                .messageId(messageId)
                .contentType("application/json")
                .headers(java.util.Map.of(
                        "event_type", "ORDER_ACCEPTED"))
                .build();

channel.basicPublish(
        "orders-exchange", "orders.accepted",
        properties, body);
~~~

**correlationId** ở đây không tự động là traceparent. Nếu dùng tracing, instrumentation/propagator cần chuyển tracing context qua headers theo quy ước được chấp nhận.

Phân biệt:

- Publisher confirm: broker xác nhận theo cấu hình publish/confirm.
- Consumer delivery: message được broker gửi tới consumer.
- Consumer acknowledgment: consumer xác nhận delivery theo policy.
- Business commit: database hoặc downstream side effect đã được commit.
- Log event: chỉ là lời gọi logger/ghi event tại điểm quan sát.

Một dòng “published” ở application không tự thay thế publisher confirms; “processed” không tự xác nhận consumer ack đã tới broker.

Trong hệ thống có kiểu RPC qua RabbitMQ, correlationId thường dùng để ghép reply với request. Nếu muốn **business correlation dài hạn**, phải định nghĩa rõ có dùng lại RPC correlation hay duy trì một ID khác trong headers.

### Các broker khác

SQS có MessageId do dịch vụ tạo và MessageAttributes do producer gửi; FIFO group/deduplication ID có vai trò riêng. Azure Service Bus và những broker khác cũng có message ID/correlation ID theo API riêng. **Không có một header chuẩn duy nhất cho mọi message system.** Nên xây bảng ánh xạ và integration test per-broker.

## 13. Retry, redelivery và DLQ

Một message thất bại có thể được giao lại:

~~~text
MESSAGE_RECEIVED id=msg-7 correlation_id=corr-42 attempt=1
MESSAGE_PROCESS_FAILED id=msg-7 correlation_id=corr-42 attempt=1 error=TIMEOUT
MESSAGE_RECEIVED id=msg-7 correlation_id=corr-42 attempt=2
MESSAGE_PROCESS_COMPLETED id=msg-7 correlation_id=corr-42 attempt=2
~~~

Các dòng là ví dụ, không phải output của chương trình Java mục 7. Hai lượt nhận không có nghĩa hai business operations độc lập.

### Quy tắc khi retry

1. Cùng logical message redelivered thường giữ correlation ID và identity theo broker semantics.
2. Nếu retry handler **republish envelope mới**, tạo new message_id nếu contract yêu cầu, nhưng giữ original_message_id và correlation_id.
3. Có attempt/retry_count từ nguồn đáng tin; không để client khai giảm số lần retry.
4. Đặt backoff, giới hạn attempts, timeout, DLQ policy và giám sát.
5. **Không dùng correlation ID làm idempotency key duy nhất** cho các message khác nhau của cùng workflow; dùng event ID/operation ID phù hợp.
6. Khi có crash sau business commit nhưng trước ack, consumer có thể xử lý lại. Cần cơ chế idempotency, không chỉ log correlation.

### Dead-letter queue

Khi chuyển sang DLQ, giữ metadata cần thiết để truy nguyên:

~~~text
correlation_id=corr-42
original_message_id=msg-7
source_destination=payments
failure_category=VALIDATION_ERROR
last_attempt=5
~~~

Đây là **sơ đồ policy**, không phải tên header chuẩn DLQ của mọi broker. Một số hệ thống bổ sung dead-letter reason, source queue/exchange và delivery count theo cách riêng.

Khi replay từ DLQ:

- Phân biệt ID của message được replay và ID gốc.
- Giữ correlation để tìm lại lịch sử.
- Không đưa toàn bộ payload/token vào error log.
- Không giả định replay không gây side effect: cần idempotency.
- Kiểm tra bridge/redrive tool có làm rơi custom headers hoặc tracing context không.

## 14. Fan-out, fan-in và batch

### Fan-out

~~~text
ORDER_ACCEPTED msg-1 (corr-42)
    |
    +--> INVOICE_REQUESTED msg-2 (cause=msg-1)
    +--> STOCK_RESERVATION_REQUESTED msg-3 (cause=msg-1)
    +--> EMAIL_REQUESTED msg-4 (cause=msg-1)
~~~

Mỗi con có message ID riêng, nhưng giữ correlation ID theo workflow. Nếu tất cả ba consumer cùng retry, chỉ nhìn correlation ID sẽ không phân biệt branch nào đang gặp lỗi; cần message_id, event_type và attempt.

### Fan-in

Nếu ORDER_READY chỉ được phát sau PAYMENT_CONFIRMED **và** STOCK_RESERVED, có **hai nguyên nhân trực tiếp**. Một causation_id đơn không thể mô tả đầy đủ; có thể cần danh sách causation_ids hoặc lưu event graph/workflow state rõ ràng.

Trong tracing, hai message có thể mang trace contexts khác nhau. Một process span cho fan-in/batch có thể dùng span links đến các message creation contexts; không tùy ý chọn trace của record đầu tiên làm parent của tất cả.

### Batch processing

- Extract context cho **từng record**, không chia sẻ một MDC của record đầu.
- Batch log tổng kết nên có batch_id, count, failures, elapsed; không gắn tùy ý một correlation ID cho cả batch.
- Khi log lỗi riêng item, dùng message_id/correlation_id của đúng record.
- Commit theo batch có thể làm record đã xử lý bị replay sau crash; vẫn cần idempotency.
- Nếu tracing công cụ hỗ trợ batch spans/links, dùng theo semantic conventions.

## 15. Bảo mật và quyền riêng tư của correlation headers

Headers là **dữ liệu**, không phải chứng cứ danh tính. Những rủi ro thường gặp:

- Attacker gửi correlation_id của người khác để cố tình gộp log hoặc vượt quyền xem.
- Client gửi CR/LF/control trong ID gây log injection nếu text formatter không escape.
- Một tenant giả header tenant_id hoặc actor_id để khiến log nhận diện nhầm.
- Một message chứa baggage lớn hoặc PII được chuyển tiếp tới nhiều service.
- Instrumentation chấp nhận malformed traceparent mà không theo policy trust boundary.
- Metric dùng correlation_id/message_id làm label, gây high cardinality và chi phí lớn.
- Consumer quên clear MDC, khiến log của tenant khác mang nhầm context.

**Phòng vệ:**

1. Validate ID theo chuẩn được chọn: type/charset/length và nguồn, có giới hạn byte.
2. Sinh internal ID mới khi không tin ID từ external boundary; lưu external_reference riêng.
3. Không dùng correlation_id làm authentication, authorization hoặc token truy cập.
4. Dùng event type, service, severity và tenant scope **từ server/auth context**.
5. Encode untrusted fields theo formatter; structured JSON encoder phải escape đúng.
6. Không nhét token, cookie, email, secret, body vào baggage/headers/log.
7. Phân quyền backend log theo tenant/role, đặt retention và audit truy cập.
8. Chặn dynamic logger/index/destination tùy ý từ input.
9. Giới hạn header count/size để giảm nguy cơ memory/broker overload.
10. Kiểm thử duplicate header, missing header, corrupted value, cross-tenant query và thread reuse.

Tracing ID có thể liên kết các hành vi của người dùng ngay cả khi không phải PII trực tiếp; phân loại quyền riêng tư và retention theo chính sách.

## 16. Correlation không bảo đảm transaction hoặc exactly-once

Một log:

~~~text
MESSAGE_PROCESS_COMPLETED correlation_id=corr-42 message_id=msg-7
~~~

không tự chứng minh DB đã commit, offset được commit, downstream nhận event mới hay side effect đúng một lần.

Một giải pháp cho yêu cầu gửi message đáng tin cậy cùng với cập nhật database là **transactional outbox**:

~~~text
Trong cùng DB transaction:
  update business state
  insert outbox event:
      event_id
      correlation_id
      causation_id
      payload
COMMIT

Outbox publisher:
  đọc event chưa gửi
  publish qua broker
  ghi nhận trạng thái gửi

Consumer:
  deduplicate / process idempotently
  commit/ack theo hợp đồng
~~~

Outbox có thể giúp tránh khoảng cách “DB commit rồi process crash trước khi ghi message”, nhưng publisher và consumer vẫn có thể thấy event trùng do retry. correlation_id giúp nối chuỗi quan sát, **không phải khóa chống trùng**.

Tương tự, distributed trace có thể bị sampling, log có retention ngắn; nếu sự kiện nghiệp vụ/audit cần lưu đầy đủ, dùng event store/audit log bền vững theo yêu cầu riêng, không chỉ dựa vào MDC hoặc tracing span.

## 17. Log schema, truy vấn và observability

Một structured log event ví dụ:

~~~json
{
  "event_type": "MESSAGE_PROCESS_COMPLETED",
  "service": "invoice-service",
  "messaging_system": "kafka",
  "destination": "invoice.events",
  "message_id": "msg-2",
  "correlation_id": "corr-42",
  "causation_id": "msg-1",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "attempt": 1,
  "outcome": "SUCCESS",
  "duration_ms": 28
}
~~~

Đây là **schema minh họa**; OpenTelemetry không bắt buộc chính xác các field tùy biến này. Nếu thêm span_id, phải lấy từ **active span hiện tại** do tracing instrumentation cung cấp, không gán đại một giá trị từ message header rồi gọi đó là consumer span.

Một số event names hữu ích:

~~~text
MESSAGE_PUBLISH_ATTEMPT
MESSAGE_PUBLISH_ACK
MESSAGE_RECEIVED
MESSAGE_PROCESS_STARTED
MESSAGE_PROCESS_COMPLETED
MESSAGE_PROCESS_FAILED
MESSAGE_RETRIED
MESSAGE_DEAD_LETTERED
MESSAGE_ACKED
~~~

Không cần ghi mọi mốc bằng INFO cho tất cả messages: có thể làm tăng chi phí và log storm. Chọn những mốc cần thiết, dùng metrics cho throughput/error rate/latency, gắn log levels đúng mục đích.

### Truy vấn theo correlation

~~~text
Find: correlation_id = corr-42
Then: group by message_id, event_type, attempt, service
Then: follow causation_id to reconstruct message graph
Then: open trace_id in tracing backend if available
~~~

Đây là pseudo-query, không phải SQL/OpenSearch/Loki syntax chạy nguyên văn. Timestamp có thể trễ do broker/collector, và đồng hồ node có thể lệch; dùng causal IDs thay vì chỉ sort theo thời gian.

**Metrics label nên cardinality thấp:** service, destination_class, message_type, outcome và retry_bucket. Không dùng correlation_id, message_id, user_id, trace_id làm Prometheus label theo mỗi message.

## 18. Checklist tích hợp nhiều service

| Câu hỏi | Quyết định cần ghi thành tài liệu |
| --- | --- |
| Entry point nào tạo ID? | HTTP ingress, scheduler, command handler hay message bridge |
| External ID có đáng tin? | Validate/map sang internal ID thế nào |
| Định dạng ID? | UUID/ULID/opaque; charset, length, uniqueness |
| Message ID lấy từ đâu? | Broker hay application; khi republish có đổi không |
| Quan hệ nhân quả? | causation_id đơn hay danh sách nguyên nhân |
| Tracing? | OTel propagator/instrumentation, semantics links |
| Header names/encoding? | Quy ước, UTF-8, duplicate key/size policy |
| Async? | Callback/executor/reactive context propagation |
| MDC? | Open/close/restore cho đúng message |
| Retry? | attempt, original ID, idempotency key |
| DLQ/replay? | Metadata nào bắt buộc giữ |
| Observability? | Schema, index/retention, dashboard, metrics |
| Security? | ID spoofing, PII, cross-tenant isolation |
| Versioning? | Message cũ trong queue/DLQ có được xử lý không |
| Testing? | Unit + real broker integration + collector readback |

Để đổi tên header hoặc tracing conventions, cần **migration window**: consumer phiên bản mới có thể nhận lại message cũ từ DLQ nhiều tuần sau. Có thể hỗ trợ hai phiên bản field trong thời gian chuyển tiếp với luật ưu tiên rõ, cảnh báo khi phát hiện dữ liệu bất thường.

## 19. Kiểm thử correlation qua message

### 19.1. Unit tests

| Case | Kỳ vọng |
| --- | --- |
| Header hợp lệ corr-42 | Consumer log đúng correlation |
| Message con | Giữ correlation, tạo message ID mới, causation trỏ về cha |
| Header thiếu/sai | Reject/quarantine hoặc tạo ID mới theo policy |
| Header chứa CR/LF | Không tạo log injection |
| traceparent sai định dạng | Không coi là trace hợp lệ |
| Trace ID toàn 0 | Bỏ qua tracing context không hợp lệ |
| Retry message | Correlation giữ nguyên, attempt được phân biệt |
| Republish envelope mới | original_message_id đúng |
| Fan-out | Các con có ID riêng, cùng workflow |
| Fan-in | Causation đủ biểu diễn nhiều nguồn |
| Thread reuse | MDC của message trước không rò sang message sau |
| Duplicate header | Áp rule rõ ràng, không tin giá trị tùy tiện |
| Message đến từ tenant khác | Không vượt quyền xem/truy cập |
| DLQ | Giữ nguồn gốc và correlation mà không lộ payload |

### 19.2. Integration test

1. Publish message qua client/broker thật hoặc test broker phù hợp.
2. Kiểm tra header tại broker và consumer, không chỉ log trước send().
3. Consumer A nhận rồi publish child; consumer B nhận, đối chiếu correlation và causation.
4. Giả lập exception, retry/redelivery và kiểm tra identity/attempt.
5. Đưa message vào DLQ, redrive/replay rồi kiểm tra custom headers không mất.
6. Bật tracing instrumentation; kiểm tra traceparent được inject/extract và spans/links hợp lý.
7. Chạy hai message song song, tái sử dụng thread, kiểm tra MDC không lẫn.
8. Kiểm tra log thật từ backend/collector và quyền truy cập, không chỉ mock Logger.
9. Thử invalid header, duplicate key, payload quá lớn và vấn đề charset.
10. Xác minh correlation/trace IDs không được đưa vào high-cardinality metric labels.

### 19.3. Phân biệt lỗi publish, xử lý và ack

Một message có thể đã được producer gửi nhưng callback thất bại; consumer có thể xử lý thành công nhưng crash trước khi ack; outbox có thể phát lại cùng event. Trong mỗi trường hợp cần log tên mốc đúng:

- PUBLISH_ATTEMPT khác PUBLISH_ACK.
- RECEIVED khác PROCESS_COMPLETED.
- BUSINESS_COMMITTED khác ACKED.
- DEAD_LETTERED chỉ nên khẳng định khi DLQ thực sự nhận theo mô hình broker.
- TRACE_EXTRACTED không đồng nghĩa authorization thành công.

Tránh log kết quả thành công quá sớm, vì correlation mạnh đến đâu cũng không sửa được một event được đặt tên sai thực tế.

## 20. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| Producer có corr, consumer không có | Không gắn header hoặc bridge làm rơi | Kiểm tra message headers ở từng hop |
| Một thread ghi corr của message trước | Quên clear/restore MDC | Thêm scope/finally và test thread reuse |
| Cùng corr nhưng trace khác | Long workflow, trace restart/sampling | Giữ business correlation; tracing links khi thích hợp |
| Có traceparent nhưng trace backend rời rạc | Chỉ copy string, không extract/start span | Kiểm tra propagator/instrumentation |
| Retry tạo workflow mới | Tạo lại correlation mỗi lần | Giữ ID gốc và original_message_id |
| Nhiều message bị dedup sai | Dùng correlation làm idempotency key | Dùng event/operation ID riêng |
| DLQ mất corr | DLQ handler/bridge không copy metadata | Test redrive và header mapping |
| Kafka record không có causation | Producer tạo con quên gắn | Gắn causal link từ message cha |
| JMS ID khác mong đợi | Nhầm JMSMessageID và JMSCorrelationID | Kiểm tra request/reply contract |
| Header trùng tên | Producer/interceptor thêm nhiều lần | Định nghĩa duplicate policy |
| Cross-tenant log bị nối nhầm | ID từ client được tin quá mức | Internal correlation + ACL |
| Metric index phình to | Dùng message_id/corr làm label | Dùng label tập giá trị hữu hạn |

**Trình tự điều tra:** chọn một message_id, tìm publish attempt/ack, kiểm tra broker metadata, tìm consumer received/processed, theo causation_id tới message con, xem retry/DLQ và cuối cùng mở trace context. Nếu dữ liệu không khớp, xác định hop nào đã mất header hoặc sai scope.

## 21. Bài tập thực hành

**Bài 1 – Chuỗi ba message.** Mở rộng MessageCorrelationDemo.java để INVOICE_REQUESTED sinh PAYMENT_REVIEW_REQUESTED (msg-3). Giữ correlation_id=corr-42, tạo causation_id=msg-2, dự đoán và kiểm tra stdout.

**Bài 2 – Header lỗi.** Thử traceparent sai format, trace ID toàn 0 và correlation ID chứa xuống dòng. Giải thích vì sao demo có thể reject/cho trace_id=none, và vì sao production phải dùng propagator chuẩn và policy trust boundary.

**Bài 3 – MDC và thread pool.** Dùng một ExecutorService một thread xử lý lần lượt corr-A/corr-B. Cố tình bỏ cleanup để thấy rò context, sau đó thêm restore trong finally và test lại.

**Bài 4 – Kafka retry.** Trong dự án có Kafka client, publish một record với correlation_id, kích hoạt lỗi xử lý một lần, ghi topic-partition-offset, message_id, correlation_id và attempt. Chỉ ra khóa idempotency phù hợp thay vì dùng correlation ID chung.

**Bài 5 – JMS request/reply.** So sánh JMSMessageID, JMSCorrelationID, JMSReplyTo của request và reply theo hai quy ước: reply dùng request message ID hoặc cả hai giữ business correlation ID; kiểm tra hợp đồng nào client/server thống nhất.

**Bài 6 – Fan-out/fan-in.** Một ORDER_ACCEPTED tạo hai message con; chỉ khi cả hai hoàn thành mới tạo ORDER_READY. Vẽ graph message_id/causation_ids và đề xuất span links cho nhiều context.

**Bài 7 – Security.** Đối tác gửi correlation ID của tenant khác và một ID chứa CR/LF. Thiết kế internal ID mapping, validation, encoding, ACL và kiểm thử chống log injection/cross-tenant leakage.

**Bài 8 – Dashboard.** Dùng log mock từ nhiều service để dựng timeline theo correlation_id, group theo message_id và attempt, nối causal graph và chỉ rõ giới hạn do sampling/clock skew/retention.

## 22. Ghi nhớ

**Correlation qua message** kết hợp business correlation, message identity, quan hệ nhân quả và tracing context. correlation_id nối workflow; message_id phân biệt message; causation_id chỉ nguồn sinh message; trace_id/span_id giúp phân tích hoạt động được instrument. Các ID **không tự thay thế nhau**.

Producer cần truyền metadata đúng trong message; consumer phải extract và quản lý scope của từng message; message con giữ business correlation nhưng có identity mới và causal link rõ. Với tracing, dùng OpenTelemetry/W3C propagators và span semantics đúng thay vì copy chuỗi; với Kafka/JMS/RabbitMQ, kiểm thử headers/properties của chính client đang chạy. Retry, DLQ, fan-out, fan-in và batch là những ca không được bỏ qua.

Correlation **không bảo đảm** authentication, authorization, exactly-once, idempotency hay durable audit. Giới hạn và validate ID, không log secret/PII, tránh high-cardinality metric labels, dùng retention và phân quyền. Luôn kiểm tra cả đường đi **producer → broker → consumer → collector/backend**, không chỉ một câu logger.info.

### Tài liệu tham khảo

- W3C Trace Context: https://www.w3.org/TR/trace-context/
- OpenTelemetry Context Propagation: https://opentelemetry.io/docs/concepts/context-propagation/
- OpenTelemetry Messaging Semantic Conventions: https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/
- OpenTelemetry Java Instrumentation: https://opentelemetry.io/docs/languages/java/instrumentation/
- Apache Kafka ProducerRecord: https://kafka.apache.org/clients/javadoc/org/apache/kafka/clients/producer/ProducerRecord.html
- Apache Kafka Headers: https://kafka.apache.org/clients/javadoc/org/apache/kafka/common/header/Headers.html
- Apache Kafka ConsumerRecord: https://kafka.apache.org/clients/javadoc/org/apache/kafka/clients/consumer/ConsumerRecord.html
- Jakarta Messaging Specification: https://jakarta.ee/specifications/messaging/
- RabbitMQ Java Client: https://www.rabbitmq.com/client-libraries/java-client
- RabbitMQ Consumer Acknowledgements and Publisher Confirms: https://www.rabbitmq.com/docs/confirms
- SLF4J Manual: https://www.slf4j.org/manual.html
- Logback MDC: https://logback.qos.ch/manual/mdc.html
- Oracle JDK 17 Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

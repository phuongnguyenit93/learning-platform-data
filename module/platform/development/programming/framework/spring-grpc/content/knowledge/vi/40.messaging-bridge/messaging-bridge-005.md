# Correlation giữa RPC và message

## 1. Vì sao cần correlation xuyên qua message flow?

Trong **SPRING_GRPC**, client gọi RPC theo hợp đồng Protocol Buffers đến service Spring. Service có thể xác thực caller, chuyển request thành command, publish qua broker và để consumer xử lý ở một thời điểm hoặc process khác. Khi đó, một thao tác nghiệp vụ không còn nằm trong một call stack liên tục.

Nếu chỉ log gRPC method ở ingress và log message ID ở consumer, rất khó trả lời các câu hỏi:

- Message này bắt nguồn từ RPC nào?
- Các event và command nào thuộc cùng một thao tác của người dùng?
- Consumer nào đã xử lý message và phát sinh message tiếp theo?
- Một lần retry là attempt mới của cùng operation hay một operation khác?
- Vì sao client nhận ACCEPTED nhưng workflow chưa hoàn tất?

**Correlation** gắn các bước liên quan bằng một định danh xuyên suốt. Nó giúp nối log, trace, operation status và message mà không phụ thuộc việc các bước chạy cùng thread, cùng instance hoặc cùng thời điểm.

~~~mermaid
flowchart LR
    A["gRPC request"] --> B["Ingress / use case"]
    B --> C["Command message"]
    C --> D["Broker"]
    D --> E["Consumer"]
    E --> F["Domain event"]
    F --> G["Another consumer"]
    G --> H["Next event / result"]
    A -.->|correlationId| C
    C -.->|correlationId| F
    F -.->|correlationId| H
~~~

Correlation ID không thay thế message ID, operation ID hoặc distributed trace ID. Mỗi loại định danh giải quyết một câu hỏi khác nhau.

## 2. Phân biệt các loại ID

Một message flow nên quy định ý nghĩa từng định danh trước khi triển khai:

| Định danh | Phạm vi | Dùng để trả lời |
|---|---|---|
| requestId | Một lần nhận request/attempt ở ingress | Log này thuộc lần gọi RPC nào? |
| correlationId | Một tương tác hoặc workflow logic | Những bước nào thuộc cùng một luồng nghiệp vụ? |
| operationId / commandId | Một ý định nghiệp vụ ổn định qua retry | Lệnh tạo đơn này là operation nào? |
| messageId / eventId | Một message cụ thể | Message nào đang được publish hoặc redeliver? |
| causationId | Quan hệ trực tiếp giữa hai message/action | Message nào đã gây ra message hiện tại? |
| traceId | Một distributed trace | Các span kỹ thuật nào thuộc cùng trace? |

Ví dụ, client gửi SubmitOrder ba lần do timeout. Mỗi lần đến ingress có thể có requestId khác nhau, nhưng nếu đó là cùng một ý định thì operationId và idempotency key phải giữ ổn định. Correlation ID cũng nên giữ ổn định nếu client muốn nối toàn bộ workflow qua các lần retry.

Một operation có thể phát nhiều message, mỗi message có messageId riêng nhưng cùng operationId và correlationId. Event tiếp theo có thể dùng causationId trỏ đến messageId trực tiếp đã kích hoạt nó.

## 3. Correlation ID khác trace ID

Hai định danh thường xuất hiện cùng nhau nhưng không nên dùng thay thế nhau:

- **Correlation ID** là định danh nghiệp vụ/ứng dụng do hệ thống quy định. Nó có thể được lưu trong operation record, outbox và message envelope để tra cứu workflow trong thời gian dài.
- **Trace ID** thuộc distributed tracing, thường do OpenTelemetry quản lý. Nó nối các span kỹ thuật và tuân theo sampling, retention, exporter và trace backend.

Một workflow kéo dài nhiều phút hoặc nhiều ngày có thể vượt vòng đời của một trace. Một operation cũng có thể tạo nhiều trace khi có retry, tác vụ chạy theo lịch hoặc workflow được tiếp tục sau thời gian chờ. Vì vậy, lưu correlation ID trong dữ liệu nghiệp vụ và dùng trace ID cho chẩn đoán từng lần thực thi.

Không tạo trace ID thủ công bằng cách đặt nó vào x-correlation-id. Hãy để OpenTelemetry tạo và truyền traceparent/tracestate theo W3C Trace Context. Correlation ID có thể được truyền song song như một trường riêng.

## 4. Nhận correlation ID từ gRPC metadata

Client có thể gửi correlation ID qua metadata, ví dụ x-correlation-id. Metadata key gRPC phải dùng chữ thường; giá trị ASCII dùng Metadata.ASCII_STRING_MARSHALLER.

~~~java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Context;
import io.grpc.Contexts;

import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationIdInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> HEADER =
            Metadata.Key.of(
                    "x-correlation-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Context.Key<String> CORRELATION_ID =
            Context.key("correlation-id");

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._:-]{1,128}");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String supplied = headers.get(HEADER);
        String correlationId =
                supplied != null && SAFE_ID.matcher(supplied).matches()
                        ? supplied
                        : UUID.randomUUID().toString();

        Context context = Context.current()
                .withValue(CORRELATION_ID, correlationId);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

Đây là ví dụ interceptor cho gRPC Java. Đăng ký nó vào server interceptor chain của Spring gRPC starter đang dùng. Nếu hệ thống yêu cầu caller phải cung cấp correlation ID, có thể từ chối giá trị thiếu/sai thay vì tự sinh; nếu không, tạo ID mới ở ingress.

Giới hạn độ dài và tập ký tự để tránh log injection, header quá lớn hoặc dữ liệu bất thường. Correlation ID do client gửi là dữ liệu không đáng tin cậy: nó không chứng minh danh tính, tenant hay quyền truy cập.

## 5. Đọc correlation ID trong service adapter

Sau khi interceptor đặt giá trị vào io.grpc.Context, service implementation có thể lấy ID hiện tại:

~~~java
@Override
public void submitOrder(
        SubmitOrderRequest request,
        StreamObserver<SubmitOrderReply> observer) {

    String correlationId =
            CorrelationIdInterceptor.CORRELATION_ID.get();

    CreateOrderCommand command = mapper.toCommand(
            request,
            callerContext.current(),
            correlationId);

    // Use case lưu correlationId vào operation/outbox cùng command.
    OperationReceipt receipt = submitOrderUseCase.execute(command);

    observer.onNext(SubmitOrderReply.newBuilder()
            .setOperationId(receipt.operationId())
            .setState("ACCEPTED")
            .build());
    observer.onCompleted();
}
~~~

Không đọc correlation ID từ một static mutable field hoặc lưu vào field của singleton service. io.grpc.Context gắn giá trị với RPC hiện tại; mỗi call có context riêng.

Nếu code chuyển sang callback hoặc executor khác, phải chủ động truyền context cần thiết. io.grpc.Context có cơ chế wrap/attach/detach, nhưng không nên giả định mọi thread pool hoặc thư viện ngoài tự động giữ context. Quan trọng hơn, khi công việc được publish sang broker, hãy ghi correlation ID vào message bền vững; không phụ thuộc thread-local sau khi RPC kết thúc.

## 6. Đưa correlation vào command và message envelope

Command và envelope nên giữ correlation độc lập với transport:

~~~java
public record SubmitOrderCommand(
        String operationId,
        String correlationId,
        String requestId,
        String tenantId,
        String customerId,
        java.util.List<OrderLine> lines) {}

public record MessageEnvelope<T>(
        String messageId,
        String messageType,
        int schemaVersion,
        String operationId,
        String correlationId,
        String causationId,
        java.time.Instant occurredAt,
        T payload) {}
~~~

Khi ingress tạo command, correlationId được lấy từ gRPC context, requestId nhận diện attempt hiện tại, còn operationId được tạo hoặc tra từ idempotency store. Khi command được publish, messageId nhận diện message đó; causationId có thể trỏ đến request/command trước đó theo quy ước của hệ thống.

Nếu một command tạo ra ba event, mỗi event có messageId riêng nhưng cùng operationId và correlationId. Event có thể đặt causationId bằng command message ID để biểu diễn quan hệ trực tiếp.

## 7. Truyền correlation qua Kafka headers

Correlation ID có thể nằm trong payload envelope và broker header. Envelope là dữ liệu bền vững, có schema và được consumer dùng như một phần của message contract. Header hữu ích cho middleware, tracing instrumentation và công cụ broker.

Nếu lưu cả hai nơi, phải tạo từ cùng một nguồn và kiểm tra không lệch nhau. Đừng để payload ghi một correlation ID nhưng header lại mang giá trị khác.

~~~java
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;
import java.nio.charset.StandardCharsets;

ProducerRecord<String, MessageEnvelope<SubmitOrderCommand>> record =
        new ProducerRecord<>(
                "orders.commands",
                command.customerId(),
                envelope);

record.headers().add(new RecordHeader(
        "x-correlation-id",
        envelope.correlationId().getBytes(StandardCharsets.UTF_8)));

record.headers().add(new RecordHeader(
        "x-operation-id",
        envelope.operationId().getBytes(StandardCharsets.UTF_8)));

kafkaTemplate.send(record);
~~~

Ví dụ dùng Spring Kafka và Kafka ProducerRecord; cần cấu hình serializer cho envelope. Nếu có OpenTelemetry Kafka instrumentation, để propagator/instrumentation truyền trace context trong header theo W3C thay vì tự tạo traceparent thủ công.

## 8. Outbox relay phải giữ correlation

Outbox relay thường chạy sau khi RPC đã kết thúc, có thể trên thread hoặc instance khác. Vì vậy, correlation ID phải được lưu cùng outbox record hoặc payload:

~~~text
gRPC metadata
     |
     v
Application command
     |
     v
Database transaction
  - business state
  - operation receipt
  - outbox payload + correlationId
     |
     v
Outbox relay (process/thread khác)
     |
     v
Broker message headers + envelope
~~~

Không lấy correlation ID bằng Context.current() trong relay rồi kỳ vọng nhận lại context của RPC cũ. Context của request không tồn tại xuyên qua database và process boundary. Relay phải đọc giá trị đã được persist.

Nếu relay retry cùng một outbox record, giữ nguyên messageId, operationId và correlationId. Header trace context của lần publish có thể được cập nhật theo chính sách tracing, nhưng không được làm thay đổi định danh nghiệp vụ của message.

## 9. Consumer khôi phục context và log theo correlation

Consumer đọc correlation từ envelope hoặc header theo một quy tắc ưu tiên duy nhất. Ví dụ dùng envelope làm nguồn chuẩn:

~~~java
@KafkaListener(topics = "orders.commands")
public void handle(
        ConsumerRecord<String, MessageEnvelope<SubmitOrderCommand>> record) {

    MessageEnvelope<SubmitOrderCommand> envelope = record.value();
    String correlationId = envelope.correlationId();

    MDC.put("correlationId", correlationId);
    MDC.put("operationId", envelope.operationId());
    MDC.put("messageId", envelope.messageId());
    try {
        createOrderUseCase.execute(envelope.payload());
    } finally {
        MDC.remove("correlationId");
        MDC.remove("operationId");
        MDC.remove("messageId");
    }
}
~~~

Đây là skeleton; consumer thực tế còn phải xử lý deserialization, idempotency, transaction, acknowledgement, retry và dead-letter. Dọn MDC trong finally là bắt buộc vì thread consumer thường được tái sử dụng cho message tiếp theo. Nếu không xóa, log của message sau có thể mang nhầm correlation ID.

Khi consumer phát event mới, copy correlation ID và operation ID từ message đã xử lý; đặt causationId bằng message ID gây ra event mới. Không tạo correlation ID mới cho mỗi bước trong cùng workflow nếu mục tiêu là truy vết toàn bộ workflow.

## 10. Distributed tracing qua ranh giới bất đồng bộ

Correlation ID hỗ trợ tìm kiếm log và operation; distributed tracing cung cấp quan hệ span và thời gian giữa các thành phần. Với OpenTelemetry:

- gRPC server instrumentation tạo server span cho RPC.
- Producer instrumentation inject trace context vào message headers.
- Consumer instrumentation extract context và tạo consumer span.
- Các span có thể tiếp nối trace hoặc dùng span link khi fan-out, batch hoặc xử lý bất đồng bộ khiến quan hệ parent-child đơn giản không còn phù hợp.

W3C Trace Context thường dùng traceparent và tracestate. Baggage có thể truyền thêm context nhỏ nhưng cần allowlist, giới hạn kích thước và tránh dữ liệu nhạy cảm. Không đưa access token, email, số điện thoại hoặc dữ liệu khách hàng vào baggage.

Không phải mọi message trong một workflow dài đều cần nằm trong cùng một trace. Retry hoặc scheduled continuation có thể tạo trace mới nhưng vẫn giữ correlation ID và operation ID. Span link có thể nối trace mới với context đã gây ra công việc.

## 11. Request/reply cần ID cho từng lượt chờ

Trong request/reply qua broker, correlation ID được dùng để ghép reply với request đang chờ. Nhưng một workflow có thể phát nhiều request song song cùng correlation ID. Khi đó, chỉ dùng correlation ID làm key cho pending map sẽ ghép nhầm response.

Nên phân biệt:

- correlationId: liên kết toàn bộ workflow.
- replyCorrelationId hoặc requestId: định danh riêng cho một cặp request/reply.
- operationId: định danh nghiệp vụ ổn định.

Ví dụ:

~~~text
Workflow correlationId = wf-100
  Request A requestId = req-A -> Reply A correlation = req-A
  Request B requestId = req-B -> Reply B correlation = req-B
  Request C requestId = req-C -> Reply C correlation = req-C
~~~

Pending request registry nên có timeout, cancellation cleanup, giới hạn số entry và xử lý reply đến muộn. Nếu ingress restart, quyết định xem pending request có cần lưu bền vững hay chuyển sang API operation status. Không giữ entry vô hạn khi client đã hết deadline.

## 12. Retry, redelivery và fan-out

Correlation ID cần ổn định qua retry của cùng workflow:

- Client retry cùng operation: giữ operationId, idempotency key và correlation ID; requestId có thể mới cho từng attempt.
- Broker redelivery cùng message: giữ nguyên messageId và correlation ID; tăng delivery attempt ở metadata riêng.
- Consumer phát event mới: tạo messageId mới, giữ correlation ID/operation ID và đặt causation ID theo message nguồn.
- Fan-out sang nhiều consumer: các nhánh giữ correlation ID chung; mỗi message/event có ID riêng.
- Tạo workflow độc lập mới: tạo correlation ID mới và có thể lưu parent operation/trace link để liên kết.

Không dùng correlation ID làm deduplication key. Nhiều message hợp lệ trong cùng workflow sẽ có chung correlation ID. Deduplication phải dùng message ID, event ID, command ID hoặc business key phù hợp.

## 13. Security và chất lượng dữ liệu correlation

Correlation ID thường đi vào log, trace, message header và công cụ vận hành, vì vậy cần kiểm soát:

- Chỉ chấp nhận tập ký tự và độ dài cho phép.
- Không dùng correlation ID để xác thực, phân quyền hoặc chọn tenant.
- Không nhúng PII, credential hoặc dữ liệu bí mật vào ID.
- Không ghi nguyên metadata tùy ý của caller vào log.
- Giới hạn header/baggage size để tránh request/message phình lớn.
- Giữ correlation ID trong phạm vi tenant và áp dụng quyền truy cập log/trace phù hợp.
- Tránh cho caller chọn ID trùng có chủ đích để gây nhiễu điều tra; có thể namespace hoặc thay thế ID không hợp lệ ở ingress.

Tenant ID phải đến từ principal đã xác thực. Nếu cần lọc theo tenant, log field tenant nên được thiết lập từ security context và có chính sách bảo vệ dữ liệu riêng; correlation ID không thay thế tenant identity.

## 14. Không dùng ID có cardinality cao làm metric label

Correlation ID, operation ID, request ID và message ID có thể có hàng triệu giá trị. Đưa chúng vào metric label sẽ tạo cardinality cao, làm tăng bộ nhớ và chi phí của hệ thống metrics.

Nên dùng:

- **Logs:** correlation ID, operation ID, request ID, message ID và causation ID.
- **Traces:** trace ID/span ID và span attributes đã được kiểm soát.
- **Metrics:** service, RPC method, message type, consumer group, status và outcome có tập giá trị giới hạn.

Ví dụ metric phù hợp: message_publish_total với topic=orders.commands và outcome=success. Correlation ID cụ thể nằm trong log/trace để truy vấn một workflow, không nằm trong label.

## 15. Kiểm thử correlation xuyên suốt

Kiểm thử cần xác minh ID được giữ đúng qua các ranh giới:

| Kịch bản | Điều cần xác minh |
|---|---|
| Client gửi correlation ID hợp lệ | Ingress giữ ID đó theo policy |
| Header thiếu hoặc sai định dạng | Ingress tạo ID mới hoặc trả lỗi theo contract |
| RPC gọi use case | Command nhận đúng correlation ID và operation ID |
| Outbox commit | Correlation ID được persist cùng record |
| Relay publish | Envelope và broker header nhất quán |
| Relay retry | Message giữ message ID và correlation ID |
| Consumer nhận message | Log có correlation/operation/message ID đúng |
| Consumer phát event | Event giữ correlation ID, có message ID mới và causation ID đúng |
| Hai request/reply song song | Reply được ghép theo request-specific ID, không chỉ workflow correlation |
| Client retry | Cùng operation không tạo workflow/side effect trùng |
| Consumer thread tái sử dụng | MDC của message trước không rò sang message sau |
| OpenTelemetry sampling | Correlation ID vẫn cho phép tìm operation dù trace không được sample |

Unit test cho interceptor và mapper xác minh việc lấy/truyền ID. Integration test với gRPC server, database/outbox và broker xác minh context không mất ở các ranh giới bất đồng bộ. Có thể kiểm tra log capture hoặc tracing exporter trong test để xác nhận các thuộc tính đã được gắn đúng.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng trace ID làm operation ID | Retry hoặc workflow tiếp tục tạo định danh kỹ thuật không ổn định | Tách trace, correlation và operation ID |
| Tạo correlation ID mới ở mỗi consumer | Không tìm được toàn bộ workflow | Giữ correlation ID qua các message liên quan |
| Dùng correlation ID làm deduplication key | Bỏ qua các message khác nhau trong cùng workflow | Deduplicate theo message/event/command ID |
| Chỉ giữ ID trong ThreadLocal | Mất context sau executor hoặc process boundary | Persist vào outbox/envelope và broker headers |
| Relay đọc context của RPC cũ | Correlation sai hoặc rỗng | Đọc ID từ outbox record |
| Chỉ dùng correlation ID cho request/reply song song | Ghép nhầm reply | Dùng request-specific reply correlation ID |
| Không xóa MDC | Log message sau mang ID của message trước | Dọn MDC trong finally |
| Đưa correlation ID vào metric label | Cardinality và chi phí metrics tăng mạnh | Đặt ID trong log/trace |
| Tin correlation ID là identity | Lỗ hổng authorization hoặc tenant isolation | Dùng principal đã xác thực cho identity |

**Ghi nhớ:** Correlation ID nối các bước của cùng một workflow từ gRPC metadata qua command, outbox, broker và consumer. Phân biệt nó với request ID, operation ID, message ID, causation ID và trace ID. Đưa correlation vào command/envelope và persist cùng outbox; truyền trace context bằng OpenTelemetry/W3C; khôi phục log context ở consumer và dọn MDC sau xử lý. Giữ ID ổn định qua retry, dùng request-specific ID cho request/reply song song và không dùng correlation ID làm deduplication key, identity hoặc metric label.

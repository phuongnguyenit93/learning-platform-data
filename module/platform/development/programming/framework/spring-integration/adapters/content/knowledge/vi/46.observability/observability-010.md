# Correlation log giữa inbound và outbound trong Spring Integration Adapters

## 1. Bài toán: inbound đã nhận, vì sao outbound chưa tới đích?

Một luồng Spring Integration có thể bắt đầu từ **HTTP inbound gateway, File/SFTP inbound adapter, JMS/AMQP/Kafka listener hoặc JDBC polling**. Message đi qua **MessageChannel, filter, transformer, router, service activator**, rồi kết thúc tại **outbound adapter/gateway**. Khi đối tác báo “chúng tôi đã gửi dữ liệu nhưng chưa nhận kết quả”, những câu hỏi cần trả lời là:

- Inbound đã thực sự tạo một Spring `Message<?>` chưa, hay lỗi xảy ra trước đó?
- Bản ghi đi qua những endpoint nào, nhánh router nào và channel có hàng đợi nào?
- Có bao nhiêu lần gọi outbound? Gửi trùng do retry hay là hai business events khác nhau?
- Một lần `send` thành công có nghĩa broker đã ACK, HTTP đã trả lời, database đã commit hay chỉ channel đã chấp nhận dispatch?
- Khi timeout xảy ra, remote đã thực hiện nghiệp vụ chưa?
- Message có đổi ID qua transformer, splitter/aggregator hoặc process/broker boundary không?
- Vì sao log ở consumer khác không có `traceId` hoặc `correlationId` của producer?

**Correlation logging** là thiết kế để các event log liên quan cùng một hành trình tích hợp có thể được **truy tìm và ghép nối có ngữ cảnh**, mà không cần in toàn bộ payload. Nó kết hợp **ID tương quan ổn định, mốc xử lý rõ nghĩa, log có cấu trúc, header propagation, tracing context và kết quả xác nhận từ hệ thống đích**.

Bài học thuộc chương **Observability** của module **SPRING_INTEGRATION_ADAPTERS**. Trọng tâm là nối tín hiệu giữa inbound/outbound adapter, gateway, poller và MessageChannel khi trao đổi dữ liệu qua **file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu**, đồng thời tôn trọng **hợp đồng message, lỗi, retry và vòng đời kết nối**.

**Kết quả mong đợi:** bạn có thể thiết kế và kiểm thử logging schema có thể nối chuỗi sự kiện từ ingress tới egress, phân biệt attempts với completion, xử lý mất context qua async/broker và dùng log cùng metrics/tracing để điều tra mà không làm lộ dữ liệu nhạy cảm.

> **Nguyên tắc:** Correlation log giúp điều tra; nó **không tự chứng minh exactly-once processing, transaction commit hay audit bất biến**. Khi cần xác nhận nghiệp vụ, phải kiểm tra trạng thái tại nguồn/đích và các cơ chế idempotency, ACK, transaction hoặc reconciliation tương ứng.

## 2. Sáu loại định danh không nên dùng lẫn nhau

| Định danh | Nguồn tạo | Phạm vi đúng | Điều không bảo đảm |
|---|---|---|---|
| **Business ID** | Hệ thống nghiệp vụ | Một đơn hàng, file/batch, payment hoặc giao dịch | Không luôn được phép ghi log; có thể là PII |
| **Correlation reference** | Tầng tích hợp theo hợp đồng | Nối các log/checkpoints thuộc cùng yêu cầu hoặc chuỗi message | Không phải bằng chứng một event đã commit |
| **Trace ID** | OpenTelemetry/Micrometer tracing hoặc hệ tracing tương thích | Một trace gồm nhiều spans và service khi context được propagate | Không phải idempotency key hay business ID |
| **Span ID** | Tracing instrumentation | Một operation cụ thể trong trace | Không ổn định qua retry/hop; không thay correlation |
| **Spring Message ID** | Spring Messaging tạo cho từng message | Một instance `Message<?>` trong JVM/flow | Có thể đổi khi tạo message mới, split hoặc nhận từ broker |
| **Attempt/delivery ID** | Code tích hợp hoặc transport | Một lần thử gọi target hay một lần broker giao message | Không phải unique business event |

Có thể cần thêm **broker identity** như Kafka `topic/partition/offset`, JMS message ID, RabbitMQ delivery tag; những giá trị này có semantics **riêng của giao thức**, không tự đồng nhất với business ID hay Spring Message ID.

### 2.1. Quy tắc định danh thực tế

1. **Correlation reference** nên là một giá trị mờ (*opaque*), không chứa thông tin cá nhân hay secret; giữ ổn định cho các checkpoint thuộc cùng hành trình.
2. **Attempt ID** phải khác cho mỗi lần gọi outbound/retry để không hiểu một lần gọi thành nhiều giao dịch.
3. **Business ID** được xử lý theo phân loại dữ liệu, có thể chỉ lưu trong domain store và dùng một tham chiếu thay thế ở log.
4. **Trace ID/Span ID** được thư viện tracing quản lý; đừng tự ghi đè để cố “khớp” với `correlationId`.
5. **Message ID** dùng để tìm message trong phạm vi cục bộ; khi tạo message mới hoặc crossing process, phải dựa vào ID tương quan được propagate có chủ đích.
6. **Idempotency key** là hợp đồng chống thực thi trùng, không suy ra từ ID log nếu chưa có thiết kế nghiệp vụ rõ.

## 3. Hành trình inbound → outbound và những ranh giới

~~~mermaid
flowchart LR
    EXT[HTTP / File / SFTP / JMS / AMQP / Kafka / DB] --> IN[Inbound Adapter / Gateway]
    IN --> C1[Input Channel]
    C1 --> VAL[Filter / Validation]
    VAL --> T[Transformer]
    T --> R[Router]
    R --> C2[Outbound Channel]
    C2 --> OUT[Outbound Adapter / Gateway]
    OUT --> DST[Broker / API / File / DB]
    IN -. correlation_ref .-> LOG[Structured Logs]
    VAL -. correlation_ref .-> LOG
    T -. correlation_ref .-> LOG
    OUT -. correlation_ref + attempt_ref .-> LOG
    DST -. ACK / outcome .-> RECON[External Confirmation]
    LOG --> INVEST[Investigation]
    RECON --> INVEST
~~~

### 3.1. Các mốc trạng thái không đồng nghĩa nhau

| Mốc | Ví dụ log | Ý nghĩa chính xác |
|---|---|---|
| **SOURCE_OBSERVED** | Poller phát hiện file eligible | Có item ở nguồn, chưa chắc thành Spring Message |
| **INGRESS_ACCEPTED** | HTTP gateway/consumer đưa message vào flow | Message đã được tiếp nhận ở ranh giới xác định |
| **VALIDATED** | Filter/validator chấp nhận | Qua một luật kiểm tra cụ thể |
| **TRANSFORMED** | Transformer tạo payload đầu ra | Chuyển đổi thành công ở endpoint đó |
| **OUTBOUND_ATTEMPTED** | Bắt đầu call/publish/upload | Đã thử gửi; chưa chắc target nhận |
| **TRANSPORT_CONFIRMED** | Broker ACK hoặc response theo protocol | Đích xác nhận ở mức transport/HTTP tương ứng |
| **BUSINESS_COMPLETED** | Audit/status ở hệ thống đích | Hoàn tất theo hợp đồng nghiệp vụ, không luôn đồng bộ |
| **TERMINAL_FAILED** | Hết retry/đưa DLQ theo chính sách | Event không thể tiếp tục theo workflow hiện tại |
| **UNKNOWN_OUTCOME** | Timeout khi chưa biết side effect | Cần readback/reconciliation, không tự retry vô hạn |

Một flow one-way qua Kafka có thể kết thúc ở `TRANSPORT_CONFIRMED` đối với producer, còn `BUSINESS_COMPLETED` chỉ xuất hiện sau khi consumer khác xử lý xong.

## 4. Hợp đồng correlation logging phải được định nghĩa trước

Trước khi viết dòng log đầu tiên, trả lời:

- **Đơn vị theo dõi là gì?** Một request HTTP, một file, một message broker, một item sau splitter hay một batch?
- **Correlation được phát tại đâu?** Ingress edge, poller, adapter hay gateway?
- **Hệ thống nào sở hữu ID này?** Client, integration service hay business domain?
- **Tới đâu cần propagate?** Trong một `IntegrationFlow`, qua một broker hay đến service cuối cùng?
- **Khi nào tạo correlation mới?** Hành trình mới, message con, replay hay workflow bù?
- **Retry có cùng correlation không?** Thường giữ correlation của logical event nhưng có attempt ID mới.
- **Completion được định nghĩa thế nào?** Adapter send, target ACK, processing commit hay callback cuối?
- **Thông tin nào được phép ghi?** Không dựa vào raw payload, URI, file path hoặc message headers.

### 4.1. Bộ trường log đề xuất

| Field | Ý nghĩa | Cách sử dụng |
|---|---|---|
| `event` | Mốc như `INGRESS_ACCEPTED`, `OUTBOUND_ATTEMPTED` | Enum hữu hạn do code quy định |
| `flow` | Tên luồng như `order-http-kafka` | ID logic ổn định, không chứa dữ liệu cá nhân |
| `component` | Endpoint/channel ở checkpoint | Tên do ứng dụng đặt |
| `correlation_ref` | Tham chiếu xuyên các checkpoints | ID mờ có kiểm chứng |
| `trace_id` / `span_id` | Ngữ cảnh tracing | Lấy từ instrumentation đã chuẩn hóa |
| `local_message_ref` | Spring Message ID cục bộ | Không giả định xuyên process |
| `attempt_ref` | Một lần gọi transport/đích | Mỗi attempt mới có ref mới |
| `source_type` / `target_type` | File/SFTP/HTTP/JMS/AMQP/Kafka/DB | Nhóm hữu hạn |
| `stage` / `outcome` | Các mốc nghiệp vụ và kết quả | Không ghi nguyên exception text |
| `error_class` | `NETWORK_TIMEOUT`, `INVALID_SCHEMA`… | Taxonomy hữu hạn |
| `schema_version` | Phiên bản message contract | Allowlist theo hệ thống |
| `duration_ms` | Thời gian của một đoạn đã định | Không nhầm với end-to-end |
| `retry_index` | Thứ tự attempt | Bắt đầu từ 0/1 theo hợp đồng nhất quán |
| `external_receipt_ref` | Tham chiếu ACK/response/commit khi có | Metadata được phân loại an toàn |
| `service` / `instance` | Nguồn phát log | Tham chiếu kỹ thuật được quản lý |

Không cần tất cả trường trong mọi log. Cần giữ **ngữ nghĩa nhất quán** để người trực có thể ghép các event mà không dựa vào thứ tự log khi hệ thống xử lý bất đồng bộ.

## 5. Ví dụ timeline có correlation chung

~~~json
{"time":"2026-11-23T08:00:00.020Z","event":"INGRESS_ACCEPTED","flow":"orders-http-kafka","component":"httpOrderInbound","correlation_ref":"corr-7f92","local_message_ref":"msg-a","outcome":"accepted"}
{"time":"2026-11-23T08:00:00.028Z","event":"VALIDATED","flow":"orders-http-kafka","component":"validateOrder","correlation_ref":"corr-7f92","outcome":"accepted"}
{"time":"2026-11-23T08:00:00.034Z","event":"OUTBOUND_ATTEMPTED","flow":"orders-http-kafka","component":"publishOrders","correlation_ref":"corr-7f92","attempt_ref":"attempt-01","target_type":"kafka"}
{"time":"2026-11-23T08:00:00.049Z","event":"TRANSPORT_CONFIRMED","flow":"orders-http-kafka","component":"publishOrders","correlation_ref":"corr-7f92","attempt_ref":"attempt-01","target_type":"kafka","outcome":"confirmed"}
{"time":"2026-11-23T08:00:00.190Z","event":"BUSINESS_COMPLETED","flow":"orders-consumer-db","component":"storeOrder","correlation_ref":"corr-7f92","local_message_ref":"msg-b","target_type":"database","outcome":"committed"}
~~~

Đây là **log giả lập**, không phải output mặc định của Spring Integration. Hai message ID `msg-a` và `msg-b` có thể khác nhau vì service B tạo Spring Message mới. Mốc `BUSINESS_COMPLETED` ở B chỉ được emit khi code thực sự biết transaction đã hoàn tất theo hợp đồng.

**Không dựa hoàn toàn vào thứ tự timestamp giữa hai máy:** đồng hồ khác nhau, buffer logging, batch exporter và network delay có thể làm dòng được ghi đến collector muộn. Sử dụng trace span relationships, event ID, sequence/attempt và trạng thái nguồn–đích để suy quan hệ nhân quả.

## 6. Phát, tiếp nhận và xác minh correlation reference

### 6.1. Khác biệt giữa nguồn tin cậy và nguồn bên ngoài

Một HTTP client có thể gửi `X-Correlation-ID`; một producer Kafka có thể gắn header `correlationId`. Nếu bạn sao chép nguyên giá trị này vào log, client có thể:

- Chèn dấu xuống dòng gây **log injection**.
- Đưa email, số tài khoản hoặc token vào trường ID.
- Cố ý tái sử dụng ID của sự kiện khác làm kết quả tìm kiếm sai.
- Gửi chuỗi rất dài làm tăng log size hoặc chi phí collector.

**Khuyến nghị:** ở ranh giới không tin cậy, phát **internal correlation reference mới**; nếu cần giữ client request ID thì chuẩn hóa nghiêm ngặt, lưu ở trường khác theo policy và không dùng nó làm bằng chứng định danh/ủy quyền. Giữa các service tin cậy, có thể propagate opaque correlation đã được xác minh theo hợp đồng.

### 6.2. Java helper phát ID an toàn

~~~java
import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationRefs {
    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private CorrelationRefs() {}

    public static String issueInternal() {
        return "corr-" + UUID.randomUUID();
    }

    public static String acceptTrustedOrIssue(Object candidate) {
        if (candidate instanceof String value
                && SAFE.matcher(value).matches()) {
            return value;
        }
        return issueInternal();
    }
}
~~~

**Chú ý:** regex chỉ kiểm tra **hình dạng**, không chứng minh nguồn đáng tin. Chỉ gọi `acceptTrustedOrIssue` trên header từ đối tác/transport có chính sách trust và validation rõ. Với public HTTP ingress, dùng `issueInternal()`, không dùng regex để coi giá trị do client tự tạo là đáng tin.

### 6.3. Không dùng ID log để phân quyền

Một `correlation_ref` có thể bị biết hoặc giả mạo nếu được truyền qua network. Không dùng nó làm credential, authorization token hoặc điều kiện “đã validate message”. Định danh nghiệp vụ phải được kiểm tra riêng bằng authentication, authorization và schema validation.

## 7. MessageHeaders và đường đi qua một IntegrationFlow

Spring Integration xây trên Spring Messaging: một `Message<?>` có **payload** và **headers**. Bạn có thể mang `correlationRef` như một application header trong phạm vi flow, miễn không nhầm nó với các header framework dùng cho request/reply hoặc splitter/aggregator.

### 7.1. Những header dễ nhầm

| Header/khái niệm | Công dụng |
|---|---|
| `MessageHeaders.ID` | Định danh của message hiện hành |
| `MessageHeaders.TIMESTAMP` | Thời điểm framework tạo message header |
| `correlationRef` (custom) | Tham chiếu log xuyên các checkpoint theo hợp đồng của ứng dụng |
| Integration correlation/sequence headers | Hỗ trợ group, splitter/aggregator, ordering tùy flow |
| `replyChannel` / `errorChannel` | Routing nội bộ, có thể là Java object |
| Trace context headers | Truyền thông tin tracing theo chuẩn/instrumentation |
| Transport-specific headers | Kafka topic/offset, HTTP method, JMS message ID… |

**Không dùng header correlation của aggregator như một alias mặc định cho toàn bộ log correlation.** Aggregator có thể cần thay nó để gom nhóm. Dùng custom `correlationRef` có namespace rõ và lưu tương quan tới group ID riêng.

### 7.2. Header có thể bị mất khi tạo message mới

~~~java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

public Message<String> normalize(Message<String> incoming) {
    String normalized = incoming.getPayload().trim();

    return MessageBuilder.withPayload(normalized)
            .copyHeaders(incoming.getHeaders())
            .build();
}
~~~

Ví dụ sao chép header cho **cùng application flow** và được xem xét theo header policy. Nó không phải hướng dẫn copy tất cả header qua HTTP/Kafka/JMS: những header nội bộ như reply/error channels có thể không serializable hoặc không nên đưa sang hệ khác. Hãy xác nhận builder/version và header semantics trong project.

### 7.3. Những điểm cần đo đường truyền header

1. Inbound adapter/gateway tạo Spring Message.
2. Enricher hoặc interceptor phát `correlationRef` nếu chưa có.
3. Filter/router/transformer giữ header theo hợp đồng khi tạo message mới.
4. Executor/queue boundary giữ dữ liệu trong message nhưng không bảo đảm thread-local MDC.
5. Splitter/aggregator thay đổi message lineage; cần xác định quan hệ cha–con.
6. Outbound header mapper chọn những header được phép đi ra network.
7. Consumer bên kia extract header đã mapped và tạo message mới.

## 8. Gắn correlation tại ingress: trước khi nào là hợp lý?

Nên gắn correlation **sớm nhất có thể sau khi ingress có identity đáng tin**. Nếu đặt ở transformer quá muộn, lỗi parse trước transformer sẽ không có ID để nối.

### 8.1. HTTP inbound

Một filter hoặc interceptor HTTP có thể tạo internal correlation trước khi Spring Integration gateway tiếp nhận. Sau đó gateway đưa reference này vào message qua mapping/enricher phù hợp. Cần quản lý **lỗi xảy ra trước gateway** (authentication, body too large, malformed URL) ngay ở HTTP server layer, vì lúc đó chưa tồn tại Spring Message.

### 8.2. File/SFTP/JDBC poller

Khi poller nhận một item, cấp correlation tại thời điểm **message được tạo/accepted**; nếu cần nối đến log của lần scan/poll trước đó, dùng một `poll_ref` riêng. Một poll có thể tạo nhiều messages nên **poll ID không thay thế message correlation**.

### 8.3. JMS/AMQP/Kafka listener

Adapter tạo Spring Message từ transport record; có thể đọc correlation trong header/broker property nếu nguồn đã được xác minh. Nếu không có ID hợp lệ, tạo internal reference rồi giữ quan hệ với broker identity (topic/offset, JMSMessageID, delivery metadata) trong log có quyền.

### 8.4. Đừng tạo một correlation mới ở mỗi endpoint

Nếu một flow phát mới ID ở transformer, router và outbound, người trực sẽ thấy ba cụm log rời nhau dù cùng business event. Phải xác định **điều kiện tái sử dụng** và chỉ tạo mới cho logical boundary được thiết kế, ví dụ một child workflow độc lập nhưng có `parent_correlation_ref`.

## 9. Logging có cấu trúc: projection an toàn thay vì in Message

Viết `log.info("Message={}", message)` có thể in payload và headers, bao gồm token, cookie, file path và PII. Để correlation log an toàn, tạo **bản ghi log mới** chỉ lấy những trường đã được phân loại.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.Message;

public final class IntegrationCheckpointLog {
    private static final Logger LOG =
            LoggerFactory.getLogger(IntegrationCheckpointLog.class);

    private IntegrationCheckpointLog() {}

    public static void received(Message<?> message) {
        Object candidate = message.getHeaders().get("correlationRef");
        String ref = candidate instanceof String s
                && s.matches("[A-Za-z0-9_-]{1,64}")
                ? s : "missing";

        LOG.info(
                "event=INGRESS_ACCEPTED flow=orders "
                + "component=ordersInbound correlation_ref={} "
                + "payload_kind={}",
                ref,
                classifyKind(message.getPayload())
        );
    }

    private static String classifyKind(Object payload) {
        if (payload instanceof byte[]) return "binary";
        if (payload instanceof String) return "text";
        return "object";
    }
}
~~~

Đoạn code trên là một **safe projection tối thiểu**: không stringify payload, không in tất cả headers, không dùng exception message làm lỗi. Với production nên cấp correlation từ middleware tin cậy ở ingress, sử dụng logger có structured fields thực sự và chuẩn hóa service/component/outcome từ danh mục hữu hạn.

### 9.1. Bản ghi event cần có nghĩa độc lập

Các event `INGRESS_ACCEPTED`, `VALIDATED`, `OUTBOUND_ATTEMPTED`, `TRANSPORT_CONFIRMED` phải có **điểm emit được mô tả và kiểm thử**. Không gọi một checkpoint ở trước handler là `BUSINESS_COMPLETED` chỉ vì biểu đồ thiết kế cho thấy bước cuối nằm ngay sau đó.

### 9.2. Không biến correlation ID thành metric label

Metrics nên dùng `flow`, `component`, `protocol`, `outcome` là các nhãn hữu hạn. `correlation_ref`, `message_ref`, `business_id` hoặc `attempt_ref` thuộc **log/trace có phân quyền**, không nên là tag counter/timer vì gây cardinality rất cao.

## 10. Java DSL: điểm gắn correlation và WireTap quan sát

Với Java DSL, một flow có thể thêm header tại ingress và gửi bản sao message sang **WireTap** để xử lý logging metadata:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class CorrelatedFlowConfiguration {
    @Bean
    IntegrationFlow ordersInboundFlow() {
        return IntegrationFlow.from("ordersInbound")
                .enrichHeaders(h -> h.headerFunction(
                        "correlationRef",
                        m -> CorrelationRefs.issueInternal()))
                .wireTap("safeObservabilityChannel")
                .transform(String.class, String::trim,
                        e -> e.id("normalizeOrder"))
                .channel("ordersForOutbound")
                .get();
    }
}
~~~

Ví dụ minh họa điểm **ingress enrichment + checkpoint**. `ordersInbound` và `safeObservabilityChannel` cần có wiring/consumer phù hợp trong ứng dụng; WireTap không tự xử lý logging và không tự redaction. Nếu message đã được một service tin cậy gắn correlation, dùng chính sách **preserve-or-create** thay vì luôn overwrite như ví dụ ingress mới này.

### 10.1. Lưu ý khi dùng WireTap

- Nhánh tap vẫn có thể nhận toàn bộ payload/headers — **chỉ consumer log safe projection** mới được phép xuất ra log.
- Nhánh quan sát đồng bộ có thể làm chậm business flow; async queue có thể tràn hoặc drop log.
- Khi một WireTap ở nhiều vị trí, event cần có `component`/`stage` khác nhau chứ không ghi trùng “received”.
- Nếu log branch thất bại, ứng dụng phải có chính sách riêng cho **diagnostic telemetry** so với **audit bắt buộc**.
- Không giả định một số lượng log tương đương duy nhất số business events khi có publish-subscribe/retry.

## 11. MDC: tiện cho log cùng thread, nhưng không phải message header

**Mapped Diagnostic Context (MDC)** của các logging framework hỗ trợ thêm trường vào log trong phạm vi thread hiện hành. Nó hữu ích cho một handler đồng bộ, nhưng **không tự bảo đảm** chuyển sang `ExecutorChannel`, pool thread khác, poller task hoặc consumer khác process.

### 11.1. Java scope MDC với cleanup

~~~java
import org.slf4j.MDC;

public final class MdcScope {
    private MdcScope() {}

    public static void runWithCorrelation(String correlationRef,
                                          Runnable task) {
        String prior = MDC.get("correlation_ref");
        try {
            MDC.put("correlation_ref", correlationRef);
            task.run();
        } finally {
            if (prior == null) {
                MDC.remove("correlation_ref");
            } else {
                MDC.put("correlation_ref", prior);
            }
        }
    }
}
~~~

Đây là cách minh họa việc **khôi phục context cũ** trong phạm vi đồng bộ. `correlationRef` phải đã được chuẩn hóa, không phải chuỗi tùy ý từ HTTP header. Nếu code đổi thread, callback chạy muộn hoặc task vượt phạm vi `task.run()`, cần thiết kế context propagation riêng.

### 11.2. Những lỗi MDC phổ biến

1. Đặt `MDC.put` mà quên `remove`: thread pool tái sử dụng khiến log request mới mang ID của request cũ.
2. Dựa vào MDC mà không mang ID trong MessageHeaders: qua queue/consumer, correlation bị mất.
3. Copy toàn bộ MDC từ untrusted request: log injection hoặc PII lan sang mọi event.
4. Coi MDC là distributed tracing: MDC không tự tạo spans hoặc nối service.
5. Chỉ gắn MDC ở outbound: lỗi xảy ra trong filter/transformer trước đó thiếu ID.
6. Gắn context ở producer thread nhưng không có task wrapper/instrumentation ở executor.

**Tư duy đúng:** giữ correlation reference trong **message/hợp đồng transport**, sử dụng MDC chỉ như **cách trình bày log ở đoạn xử lý hiện hành**.

## 12. Channel bất đồng bộ và cách giữ quan hệ nhân quả

| Thành phần | Điều thay đổi | Để nối log đúng |
|---|---|---|
| **DirectChannel** | Thường cùng call stack/thread | Header và MDC trong scope đồng bộ có thể cùng xuất hiện |
| **QueueChannel** | Message chờ rồi consumer/poller lấy sau | Header đi theo message; MDC cần khôi phục ở consumer |
| **ExecutorChannel** | Dispatcher/handler chạy ở thread pool | Propagation/instrumentation qua executor và cleanup context |
| **PublishSubscribeChannel** | Fan-out nhiều subscribers, có thể bất đồng bộ | Cùng parent correlation, thêm branch/attempt riêng |
| **Splitter** | Một message thành nhiều children | Parent correlation + item/sequence reference |
| **Aggregator** | Nhiều messages thành một result | Correlation group, group completion và lineage |
| **Broker boundary** | Producer và consumer khác JVM/process | Transport header mapper/trace context và external broker identity |

### 12.1. Thứ tự log không phải thứ tự hoàn tất

Ở flow có `ExecutorChannel`, log `OUTBOUND_ATTEMPTED` của item B có thể xuất hiện trước `VALIDATED` của item A dù A được nhận trước. Cần dựa trên correlation + attempt + **causal relation**, không sort tất cả log chỉ theo timestamp rồi suy rằng code chạy tuần tự.

### 12.2. Queue depth và latency

Correlation logging nên đặt timestamp/metrics tại **enqueue, dequeue, outbound attempt và confirmation** nếu cần tính end-to-end. Timer của handler không đo toàn bộ thời gian chờ queue. Nếu không có message-level timing vì data retention, có thể dùng histogram end-to-end và queue age để quan sát SLO.

## 13. W3C Trace Context và Micrometer/OpenTelemetry

**Trace ID** và **Span ID** hỗ trợ liên kết hoạt động xuyên thành phần và service. Các hệ tracing thường hỗ trợ W3C Trace Context, gồm `traceparent`, và có thể thêm `tracestate`/baggage theo cấu hình.

**Nhưng** một inbound HTTP request, JMS message hoặc Kafka record không tự có cùng behavior propagation; cần instrumentation/extractor/injector phù hợp transport, thư viện và phiên bản Spring Boot/Spring Integration/Micrometer đang dùng.

### 13.1. Những điều không nên tự làm

- Không copy một chuỗi `traceparent` chưa được kiểm tra vào mọi log như một token tin cậy.
- Không tự tạo `spanId` cố định cho tất cả endpoints.
- Không dùng trace ID làm idempotency key hoặc khóa business.
- Không đưa email, account ID hay credential vào tracing baggage.
- Không giả định `MessageHistory` là một distributed trace.

### 13.2. Correlation log và tracing bổ sung nhau

| Mục đích | Correlation log | Distributed tracing |
|---|---|---|
| Gom log một hành trình nghiệp vụ | Tốt, nếu ID được propagate đúng | Tốt khi spans/trace context được thu thập |
| Thấy độ trễ giữa các operations | Cần timestamps/metrics | Span timings thường phù hợp hơn |
| Lưu cả retry/replay cách nhau nhiều giờ | Có thể nếu giữ logical correlation | Không nhất thiết chung một trace; nên tạo trace mới và giữ business correlation |
| Điều tra khi tracing sample bỏ qua | Structured logs có thể vẫn còn | Trace có thể thiếu do sampling |
| Bảo vệ PII | Phải phân loại ID/fields | Cũng phải phân loại attributes/baggage |
| Thấy trạng thái remote đã commit | Cần external outcome evidence | Một span thành công không tự chứng minh business commit |

### 13.3. Quyết định parent/child khi retry và replay

Với retry ngay trong cùng request, spans có thể là các child/sibling attempts theo instrumentation. Với replay từ DLQ sau nhiều giờ, nên tạo một **processing attempt/trace mới** nhưng giữ **stable logical reference** và `replay_of` đã được duyệt. Không ép hai execution độc lập thành một trace vô hạn.

## 14. Header mapping khi đi qua network boundary

Spring `MessageHeaders` có thể chứa Java objects như `replyChannel`, `errorChannel`, file reference hoặc framework metadata; **không copy toàn bộ** sang HTTP, JMS, AMQP, Kafka, SFTP metadata hay database columns.

### 14.1. Nguyên tắc allowlist

1. Xác định **danh sách header công khai** theo hợp đồng transport, chẳng hạn `X-Correlation-Ref` và trace context được instrumentation quản lý.
2. Giới hạn kiểu dữ liệu, ký tự, độ dài, số lượng và trust boundary.
3. Ở receiver, map trở lại application header **có kiểm chứng**; không dùng trực tiếp để cấp quyền.
4. Không đưa `Authorization`/`Cookie`, session, raw user identity, internal routing/channel objects, toàn bộ `history` hoặc error details qua boundary.
5. Tách producer correlation từ delivery metadata của broker; giữ log mapping tại các checkpoint phát/nhận.
6. Kiểm thử serialization/deserialization ở **phiên bản client/adapter thực tế**.

### 14.2. Pseudocode mapping an toàn

~~~text
on_outbound(message, transport):
    correlation = require_valid_internal_correlation(message)
    external_headers = new_empty_header_map()
    external_headers["correlation-ref"] = correlation
    inject_trace_context_using_supported_instrumentation(external_headers)
    send_payload_using_contract(message.payload, external_headers)

on_inbound(external_record, trusted_transport):
    correlation = validate_and_accept_per_trust_policy(
        external_record.headers["correlation-ref"])
    if correlation is invalid or not trusted:
        correlation = issue_new_internal_ref()
    extract_trace_context_if_supported_and_trusted(external_record)
    create_message_with_approved_headers(correlation)
~~~

Đây là **pseudocode**, không phải API mặc định của Kafka/JMS/HTTP. Mỗi adapter có quy tắc đổi tên/kiểu header riêng, và propagation W3C trace context phải dùng thư viện hỗ trợ.

## 15. HTTP inbound gateway → HTTP outbound gateway

### 15.1. Chuỗi mốc điển hình

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant A as Spring Integration Service
    participant B as Remote API
    C->>A: HTTP request
    Note over A: Issue internal correlation_ref
    A->>A: INGRESS_ACCEPTED / VALIDATED
    A->>B: Outbound request + approved correlation header
    Note over A: OUTBOUND_ATTEMPTED + attempt_ref
    alt Remote responds
        B-->>A: Status + response
        A->>A: TRANSPORT_CONFIRMED / APPLICATION_RESULT
        A-->>C: HTTP response
    else Timeout
        A->>A: UNKNOWN_OUTCOME / reconcile
        A-->>C: Error or async status per contract
    end
~~~

### 15.2. Những trường nên ghi

| Checkpoint | Log an toàn |
|---|---|
| HTTP ingress | Route template, method, status class, internal correlation, request size bucket |
| Validation | Schema version, bounded reason code |
| Outbound begin | Target alias, attempt ID, timeout class |
| Outbound end | Status class, duration, response classification được duyệt |
| Retry | New attempt ID, retry index, cause class |
| Client response | Status code, latency, outcome theo hợp đồng gateway |

**Không ghi** raw request/response body, `Authorization`, cookie, query token hay full dynamic URL để ghép log.

### 15.3. HTTP 200/202 và timeout không tương đương completion

- HTTP `200` có thể là response đồng bộ, nhưng body/error code nghiệp vụ vẫn cần được xác minh.
- HTTP `202 Accepted` có thể chỉ có nghĩa remote nhận tác vụ bất đồng bộ.
- Timeout sau khi gửi request là **unknown outcome**, remote có thể đã commit.
- Một outbound gateway tạo reply Spring Message có thể làm **local Message ID thay đổi**; correlation phải được bảo toàn theo contract.
- Client disconnect không chắc đã hủy side effect ở remote.

Nếu cần retry, dùng idempotency key và/hoặc readback theo API đích, không chỉ tìm một dòng log thiếu response rồi gửi lại.

## 16. File inbound/outbound: từ file reference đến business result

File adapter không có sẵn correlation header do remote đối tác gửi. Người thiết kế phải quyết định đơn vị theo dõi:

1. **Một file:** phát reference khi file eligible được nhận.
2. **Một batch trong file:** giữ `parent_file_ref`, tạo `batch_ref` khi cần.
3. **Mỗi record sau splitter:** giữ parent correlation và thêm item reference riêng.

### 16.1. Các checkpoint

| Bước | Event | Điều không được suy |
|---|---|---|
| Scanner phát hiện file | `SOURCE_OBSERVED` | File đã sẵn sàng đọc hoàn chỉnh |
| Inbound tạo message | `INGRESS_ACCEPTED` | File đã parse xong |
| Transformer parse | `VALIDATED` / `PARSE_FAILED` | Outbound đã gửi |
| File outbound ghi | `WRITE_ATTEMPTED` | File đã durable/đã được đối tác lấy |
| Handoff xác nhận | `TRANSPORT_CONFIRMED` (nếu hợp đồng định nghĩa) | Remote nghiệp vụ đã xử lý xong |

### 16.2. Bảo vệ dữ liệu

**Không lấy raw filename/path làm correlation reference hoặc log field mặc định.** Tên file có thể chứa họ tên, số tài khoản hoặc tenant. Dùng opaque file ref do hệ thống tạo, lưu mapping ở nơi có ACL nếu cần. Với file lớn hoặc stream, không đọc payload chỉ để tính correlation; việc tiêu thụ stream có thể làm handler downstream hỏng.

### 16.3. Accept-once filter và restart

File có thể được đọc lại sau restart do metadata store/filter thay đổi, hoặc không được phát lại vì đã được đánh dấu processed. Correlation ref có thể mới cho mỗi processing attempt nhưng cần liên kết tới **nguồn file logical** qua một key nghiệp vụ an toàn để xác định duplicate/replay. Log không thay được idempotent file processing.

## 17. SFTP inbound/outbound: poll ref, file ref và transfer ref

SFTP thường có **poller** và **remote session**, nên không gán một correlation cho toàn bộ lượt poll nếu poll phát nhiều file.

~~~text
poll_ref          = poll-2026-11-23-0800
file_correlation  = corr-1f83
transfer_attempt  = transfer-01
checkpoint        = SFTP_DOWNLOAD_ATTEMPTED
outcome           = transport-timeout
~~~

### 17.1. Những mốc quan trọng

- `POLL_STARTED` / `POLL_EMPTY` / `POLL_FAILED`: sự kiện scheduler/source, có thể **chưa có Spring Message**.
- `FILE_ELIGIBLE`: remote listing/filter xác định file.
- `DOWNLOAD_ATTEMPTED` / `DOWNLOAD_CONFIRMED`: transfer outcome ở client.
- `INGRESS_ACCEPTED`: file được tạo thành message trong flow.
- `OUTBOUND_ATTEMPTED` / `REMOTE_HANDOFF_CONFIRMED`: upload/rename/commit theo hợp đồng remote.
- `BUSINESS_COMPLETED`: nếu đối tác có callback/status/event riêng xác nhận xử lý.

### 17.2. Timeout SFTP và tệp dở dang

Một transfer timeout có thể để lại file tạm hoặc một phần dữ liệu tại target. **Đừng log “sent success” chỉ vì hàm upload đã được gọi.** Cần kiểm tra remote size/checksum, temporary filename/rename semantics, idempotent delivery và các thao tác cleanup đã được duyệt.

### 17.3. Không log thông tin SFTP nhạy cảm

Giữ source/target alias, transfer status, bytes bucket và correlation; tránh username, password, private key, đường dẫn đầy đủ và tên file chứa dữ liệu cá nhân. Nếu connection không mở được, chỉ có poll/session log — **không có message history** cho message chưa được tạo.

## 18. JMS: JMSCorrelationID và logic correlation riêng

JMS hỗ trợ metadata như **`JMSMessageID`** và **`JMSCorrelationID`**. Chúng hữu ích với request/reply và tracking broker, nhưng phải hiểu:

- `JMSMessageID` do provider có thể gán theo semantics gửi; không phải Spring Message ID.
- `JMSCorrelationID` có thể do producer/app đặt; nội dung có thể chưa được tin cậy hoặc là ID reply tương ứng request.
- Một message bị redeliver có thể tạo một **Spring Message mới** ở consumer với attempt context khác.
- JMS ACK/transaction commit khác với việc handler ghi “processed” trước commit.

### 18.1. Khi inbound JMS

Log `broker_message_ref` (nếu policy cho phép), consumer destination alias, application correlation, delivery/redelivery indicator và handler outcome. Nếu producer có contract dùng `JMSCorrelationID` làm ID xuyên service, xác minh/chuẩn hóa trước khi đưa vào log hoặc MDC.

### 18.2. Khi outbound JMS

Ghi `OUTBOUND_ATTEMPTED` và sự kiện đã gửi/commit theo API/session thực tế. Với request/reply, map request correlation đến reply **qua cơ chế gateway/JMS tương ứng**, không trộn reply correlation với ID business.

### 18.3. ACK/transaction và duplicate

Một record bị rollback rồi xử lý lại có thể có cùng logical correlation nhưng attempt mới. Đừng báo hai đơn hàng hoàn tất vì có hai log `HANDLER_STARTED`. Kết quả business cần transaction/target confirmation và chiến lược idempotency.

## 19. AMQP/RabbitMQ: routing, delivery tag và xác nhận

Trong AMQP/RabbitMQ, message có routing properties, headers và body; producer/consumer được tách biệt.

| Thông tin | Phạm vi | Dùng để nối log |
|---|---|---|
| Application correlation header | Hợp đồng giữa producer/consumer | Nối logical event nếu đã validate |
| Exchange/routing key | Routing của broker | Chỉ log alias/giá trị được phép; không mặc định là ID |
| Delivery tag | Delivery trên channel/session liên quan | Không dùng làm global correlation |
| Publisher confirm | Kết quả broker xử lý publish theo semantics | Là mốc transport, không là consumer completion |
| Consumer ACK/NACK | Kết quả delivery xử lý ở consumer | Cần kết hợp transaction/biz outcome |
| DLQ/requeue metadata | Retry/failure path | Nối attempt lineage và reason class |

### 19.1. Publish–consume–commit

Producer ghi `OUTBOUND_ATTEMPTED` trước khi publish; ghi `TRANSPORT_CONFIRMED` khi nhận confirm phù hợp. Consumer nhận message, extract correlation theo mapper được cấu hình, ghi `INGRESS_ACCEPTED` và attempt mới. Nếu consumer đã ACK nhưng nghiệp vụ có side effect ngoài transaction, phải xác minh commit tương ứng.

### 19.2. Poison message loop

Một message lỗi có thể bị NACK/requeue nhiều lần. Khi phân tích log cần thấy **cùng logical correlation + nhiều delivery attempts**, rate/backoff và DLQ, không tự kết luận có nhiều message độc lập từ publisher.

## 20. Kafka: nối producer, topic-partition-offset và consumer

Kafka có các mốc rất rõ về vận chuyển record:

1. Producer gọi `send` và có một **send attempt**.
2. Producer callback nhận metadata hoặc failure theo `acks`/client settings.
3. Record tồn tại ở một **topic/partition/offset** khi broker ghi theo semantics tương ứng.
4. Consumer group nhận/poll record, xử lý và commit offset theo cấu hình.
5. Hệ thống nghiệp vụ downstream có thể còn phải ghi database hoặc gọi API khác.

### 20.1. Producer logging

~~~json
{
  "event":"TRANSPORT_CONFIRMED",
  "flow":"order-publisher",
  "component":"ordersKafkaOutbound",
  "correlation_ref":"corr-7f92",
  "attempt_ref":"send-01",
  "target_type":"kafka",
  "topic_alias":"orders",
  "partition":2,
  "offset":1849,
  "outcome":"confirmed"
}
~~~

Giá trị là **giả lập**, không phải log mặc định từ Spring Kafka/Integration. Partition/offset có thể giúp điều tra một record nhưng không nên trở thành metric labels cho từng message; cần kiểm soát quyền đọc logs.

### 20.2. Consumer logging

~~~json
{
  "event":"INGRESS_ACCEPTED",
  "flow":"order-consumer",
  "component":"ordersKafkaInbound",
  "correlation_ref":"corr-7f92",
  "local_message_ref":"msg-new",
  "consumer_attempt_ref":"consume-02",
  "topic_alias":"orders",
  "partition":2,
  "offset":1849,
  "retry_index":1
}
~~~

Khi consumer nhận `correlation_ref` từ Kafka header, header phải có mapping/serialization tương thích và được kiểm tra. Kafka record **key** có thể chứa customer ID, nên không log raw key làm correlation. `topic/partition/offset` là broker identity, không phải business ID.

### 20.3. Offset commit không đồng nghĩa hoàn tất side effect

Tùy cấu hình container, offset có thể commit trước/sau xử lý hoặc nằm trong transaction. “Consumer lag = 0” và “offset committed” không tự chứng minh remote DB/API đã xử lý thành công. Hãy đặt `BUSINESS_COMPLETED` tại mốc có bằng chứng hợp đồng và kiểm tra khả năng duplicate/replay.

### 20.4. Header tracing và consumer group

W3C trace context qua Kafka yêu cầu producer inject và consumer extract bằng instrumentation thích hợp. Với replay từ retry/DLQ topic, có thể tạo trace mới và giữ logical correlation + `replay_of`; không bắt buộc mọi replay cách nhau nhiều giờ chia sẻ một trace ID.

## 21. JDBC/database adapter: khi một row trở thành message

JDBC inbound polling, outbound update hoặc gateway request/reply có **ranh giới transaction** và **đơn vị dữ liệu** khác các broker. Một `SELECT` có thể lấy nhiều rows, một row có thể đi qua nhiều lần xử lý và một outbound call có thể thành công dù bước cập nhật DB đánh dấu processed thất bại.

### 21.1. Các mức correlation

| Mức | Tham chiếu | Dùng để |
|---|---|---|
| Một poll | `poll_ref` | Tìm một lần chạy scheduled query |
| Một batch SELECT | `query_attempt_ref` | Tìm SQL execution, thời gian, row count |
| Một logical row/event | `correlation_ref` | Nối các endpoint xử lý dữ liệu đó |
| Một lần xử lý lại row | `processing_attempt_ref` | Phân biệt retry/recovery |
| Một DB transaction | `transaction_ref` hoặc evidence riêng | Nối log với commit/rollback khi có |
| Một outbound request | `delivery_attempt_ref` | Chỉ một lần gọi remote |

### 21.2. Mốc ghi log an toàn

~~~text
DB_POLL_STARTED       poll_ref=poll-17
DB_ROWS_SELECTED      poll_ref=poll-17 rows=25
INGRESS_ACCEPTED      correlation_ref=corr-c42 source_type=jdbc
OUTBOUND_ATTEMPTED    correlation_ref=corr-c42 attempt_ref=call-01
OUTCOME_UNKNOWN       correlation_ref=corr-c42 attempt_ref=call-01
RECONCILIATION_RESULT correlation_ref=corr-c42 outcome=confirmed
DB_MARKER_COMMITTED   correlation_ref=corr-c42 transaction_ref=tx-18
~~~

Đây là sự kiện do ứng dụng định nghĩa. Các tên `DB_MARKER_COMMITTED` chỉ được dùng **sau khi có xác nhận commit** chứ không phải khi code mới gọi `update(...)`.

### 21.3. Rủi ro log SQL

Không dùng raw primary key, email, SQL statement chứa literal params hoặc toàn bộ row làm field correlation log nếu chưa được phân loại. Dùng **opaque reference** hoặc mapping có ACL ở domain store. Với dữ liệu cần tham chiếu ổn định xuyên lần retry, có thể dùng ID nội bộ đã phát khi lập sự kiện, không cố khôi phục từ những trường PII.

### 21.4. Lỗi timeout và duplicate transaction

Flow `DB poll → HTTP API → DB mark processed` có thể timeout sau khi remote hoàn tất nhưng trước khi local mark. Một lần poll sau sẽ đọc lại row. Dùng **idempotency key, inbox/outbox hoặc readback/reconciliation** theo kiến trúc để biết có cần gửi lại. Correlation logs cho thấy hai attempts thuộc cùng logical event, không tự ngăn duplicate.

## 22. Poller: nối log trước khi có Spring Message

Một inbound adapter dùng `poller` có thể chạy mỗi vài giây/phút để đọc File, SFTP, JDBC hoặc `QueueChannel`. Nếu poll trả empty, **không có message** nên không thể dựa vào `correlationRef` của message để chứng minh poller đang chạy.

### 22.1. Phân biệt poll và message events

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant S as External Source
    participant A as Inbound Adapter
    participant H as Business Handler
    P->>A: poll(poll_ref)
    A->>S: query / scan / list
    alt Source rỗng
        S-->>A: Không có item
        A-->>P: POLL_EMPTY
    else Có nhiều items
        S-->>A: Item 1, Item 2
        A->>H: Message 1 + correlation_ref_1
        A->>H: Message 2 + correlation_ref_2
    else Lỗi kết nối
        S-->>A: Transport error
        A-->>P: POLL_FAILED
    end
~~~

### 22.2. Thiết kế các cấp ID

- Một lần poll có **`poll_ref`**, không nhất thiết cùng ID với message được tạo.
- Mỗi logical item có **`correlation_ref`** của riêng nó.
- Với batch, message con có **`parent_batch_ref`** và **`item_ref`** nếu có policy.
- Nếu source đã có ID tin cậy, có thể ánh xạ tới logical event reference thay vì phát mới mọi lần xử lý; vẫn phải kiểm soát duplicates.

### 22.3. Cảnh báo “không thấy correlation log”

Có thể do không có dữ liệu nguồn, poller bị lỗi trước khi tạo message, filter loại hết items, logger sampling bỏ qua hoặc log collector lỗi. Kiểm tra **last poll tick, empty/error count, source oldest age và poller lifecycle** trước khi kết luận message đã bị thất lạc.

## 23. Splitter, aggregator và phân nhánh: correlation theo dòng dõi message

Ở các flow `splitter → item handlers → aggregator`, một parent message có thể tạo hàng nghìn children. **Không dùng một ID duy nhất để thay thế mọi thông tin về item và attempt**.

### 23.1. Cấu trúc lineage gợi ý

~~~json
{
  "event":"ITEM_VALIDATED",
  "flow":"invoice-batch",
  "correlation_ref":"corr-batch-92",
  "parent_ref":"batch-92",
  "item_ref":"opaque-item-07",
  "processing_attempt_ref":"item-attempt-01",
  "component":"validateInvoice",
  "outcome":"accepted"
}
~~~

Trường `item_ref` phải là một tham chiếu được phép log, không phải số chứng từ/số tài khoản khách hàng chưa được phân loại. Nếu item là payload nhạy cảm, có thể chỉ ghi `sequence_index` trong phạm vi batch được bảo vệ.

### 23.2. Các mốc nên ghi

1. `BATCH_ACCEPTED` — số item đã xác định, schema và batch reference.
2. `SPLIT_COMPLETED` — số message con được tạo.
3. `ITEM_VALIDATED`/`ITEM_REJECTED` — theo từng item khi thật sự cần và được sampling/giới hạn.
4. `BRANCH_DISPATCHED` — nhánh router được chọn theo danh mục cố định.
5. `AGGREGATION_PENDING`/`AGGREGATION_COMPLETED`/`AGGREGATION_TIMED_OUT` — group state.
6. `OUTBOUND_CONFIRMED` — kết quả của aggregate, không phải tự động của từng item nếu target semantics khác.

### 23.3. Những bẫy thường gặp

- Aggregator tạo message kết quả mới; header correlation của group có thể khác correlation ref ứng dụng.
- Một item timeout không có nghĩa toàn batch thất bại nếu completion strategy cho partial result.
- Một `PublishSubscribeChannel` gửi tới ba subscribers không bảo đảm cả ba nhánh thành công chỉ vì log dispatch được ghi.
- Retry một item phải có attempt mới, không ghi đè lineage cũ.
- Nếu batch lớn, log per-item có thể làm tăng dung lượng và nguy cơ lộ dữ liệu; cân nhắc batch-level metrics và error-only logs.

## 24. Gateway request/reply: nối request, reply và callback

### 24.1. Inbound gateway đồng bộ

Một HTTP/JMS gateway nhận request và chờ reply từ integration flow. Các log cần thể hiện **request accepted, business handler result, reply constructed và response delivered theo semantics có thể xác minh**.

### 24.2. Outbound gateway đồng bộ

Outbound gateway gọi remote và nhận response:

~~~text
INGRESS_ACCEPTED       correlation_ref=corr-r17
GATEWAY_REQUEST_SENT   correlation_ref=corr-r17 attempt_ref=req-01
GATEWAY_REPLY_RECEIVED correlation_ref=corr-r17 attempt_ref=req-01 status_class=2xx
REPLY_TRANSFORMED      correlation_ref=corr-r17 result=accepted
CLIENT_RESPONSE_SENT   correlation_ref=corr-r17 http_status=200
~~~

Log có tên `CLIENT_RESPONSE_SENT` chỉ nên khẳng định điều mà server framework thực sự biết. Nó không chứng minh network delivery tới client cuối cùng đã hoàn tất.

### 24.3. Async callback pattern

Với API remote trả `202 Accepted` và gửi callback sau, yêu cầu ban đầu có thể kết thúc trước callback. Nên lưu **mapping correlation → external job reference** trong state store có quyền hoặc outbox phù hợp. Callback chứa reference cần **authentication và validation**, sau đó mới nối vào logical correlation; không coi callback query param tự xưng là đáng tin.

### 24.4. Reply channel và error channel

Spring Integration có thể lưu `replyChannel`/`errorChannel` trong headers để định tuyến nội bộ. Đây không phải correlation ID và có thể là Java objects. Không serialize/copy các header đó qua broker hoặc log. Gateway reply message có thể được dựng mới và có local Message ID khác; ứng dụng phải giữ reference qua mapping phù hợp.

## 25. ErrorMessage và log khi exception xảy ra

Tùy cấu hình endpoint, error handling và giao thức, lỗi trong Spring Integration có thể được gửi đến `errorChannel` dưới dạng `ErrorMessage`. Trong một số trường hợp có **original message** để đọc metadata/correlation.

### 25.1. Ví dụ nhận diện error context

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

public void handleError(Message<?> inbound) {
    if (!(inbound instanceof ErrorMessage error)) {
        return;
    }

    Message<?> original = error.getOriginalMessage();
    String correlation = "missing";
    if (original != null) {
        Object value = original.getHeaders().get("correlationRef");
        if (value instanceof String ref
                && ref.matches("[A-Za-z0-9_-]{1,64}")) {
            correlation = ref;
        }
    }

    // Chỉ ghi metadata an toàn, không in ErrorMessage/original payload.
    auditSafeFailure(correlation, "PROCESSING_EXCEPTION");
}
~~~

`auditSafeFailure(...)` là **hàm ứng dụng minh họa**, không phải API Spring Integration. Nếu message gốc không tồn tại, có thể dựa trên request/transport context hoặc incident record; không tự dựng một correlation sai để gắn vào luồng khác.

### 25.2. Lỗi có thể xảy ra trước khi tạo message

- File/SFTP poll không mở được session.
- HTTP request bị từ chối trước gateway.
- Kafka deserialization/converter lỗi khi chưa tạo Spring Message hợp lệ.
- JMS/AMQP client không kết nối được broker.
- JDBC query/connection thất bại trước khi có row/message.

Các trường hợp này cần **poll/request/delivery attempt reference** ở adapter/client, không cố lấy `MessageHistory` hoặc `correlationRef` từ message chưa tồn tại.

### 25.3. Không log payload khi lỗi

Một `Throwable.getMessage()` có thể chứa body HTTP, raw record, SQL parameters hoặc URL có token. Log `error_class`/`exception_type` đã chuẩn hóa, component, attempt và correlation; giữ stack trace có kiểm soát khi policy cho phép, tránh dump `error.getPayload()` hoặc original message nguyên vẹn.

## 26. Retry, redelivery, DLQ và idempotency: một logical event, nhiều attempts

**Retry** là lý do phổ biến khiến log có cùng correlation xuất hiện nhiều lần. Nếu không có attempt ID và outcome semantics, dashboard dễ đếm nhiều deliveries như nhiều business events.

### 26.1. Ví dụ một event gửi HTTP ba lần

~~~text
correlation_ref=corr-e21 event=INGRESS_ACCEPTED
correlation_ref=corr-e21 attempt_ref=attempt-01 event=OUTBOUND_ATTEMPTED
correlation_ref=corr-e21 attempt_ref=attempt-01 event=REMOTE_TIMEOUT outcome=unknown
correlation_ref=corr-e21 attempt_ref=attempt-02 event=OUTBOUND_ATTEMPTED
correlation_ref=corr-e21 attempt_ref=attempt-02 event=REMOTE_UNAVAILABLE outcome=retryable
correlation_ref=corr-e21 event=RECONCILIATION_STARTED
correlation_ref=corr-e21 event=BUSINESS_COMPLETED outcome=confirmed
~~~

Đây chỉ là một **timeline giả lập**. Nếu request đầu có thể đã commit, việc gọi attempt thứ hai mà không kiểm tra idempotency/reconciliation có thể gây side effect trùng. Mốc `BUSINESS_COMPLETED` không nhất thiết do attempt thứ hai tạo ra.

### 26.2. Tách các lớp kết quả

| Loại | Gợi ý field |
|---|---|
| Logical event | `correlation_ref`, `event_type` |
| Source delivery | `delivery_ref`, `redelivery_index` |
| Processing invocation | `processing_attempt_ref`, `retry_index` |
| Target call | `outbound_attempt_ref` |
| Business outcome | `completion_status`, `evidence_ref` |
| Replay from DLQ | `replay_ref`, `replay_of`, `reason_class` |

### 26.3. Dùng correlation để điều tra, dùng idempotency để bảo vệ

Correlation không ngăn duplicate. Một idempotency key có thể được tạo từ business command identity **đã xác minh và theo chính sách**, nhưng không bắt buộc trùng `correlation_ref`. Phần chống duplicate thuộc domain/receiver và transaction strategy.

### 26.4. Dead-letter queue

Khi một message vào DLQ, log tối thiểu:

- Original logical correlation nếu có và được phép.
- DLQ transport ref/topic/queue alias.
- Reason class, attempt count và trạng thái cuối.
- Ref tới original event trong kho có quyền.

Khi replay, phát **attempt/replay ref mới**, giữ lineage và thiết lập trace context mới nếu phù hợp. DLQ có thể chứa payload nhạy cảm; không dump DLQ body vào log để đối soát.

## 27. Đồng hồ, timestamp và đo độ trễ end-to-end

### 27.1. Timestamp ở nhiều máy không tuyệt đối

Collector có thể nhận log producer B trước log producer A dù A xử lý trước. Nguyên nhân gồm queue logging, network delay, batching, sampling và clock skew. Nên lưu timestamp chuẩn UTC và độ lệch thời gian hệ thống được quản lý, nhưng **không** giả định chỉ sort theo timestamp là đủ xác định quan hệ nhân quả.

### 27.2. Duration có điểm bắt đầu/kết thúc rõ

| Duration | Start | End |
|---|---|---|
| **Inbound latency** | Request/record đến tầng adapter | Spring Message được accepted |
| **Queue wait** | Enqueue | Consumer bắt đầu xử lý |
| **Handler duration** | Handler invoked | Handler returns/throws |
| **Outbound latency** | Target call started | Protocol response/confirm/timeout |
| **End-to-end latency** | Logical event accepted/source-ready | Business completion theo contract |

Trong cùng JVM, đo elapsed time nên dựa trên **monotonic clock/timer** phù hợp; timestamp wall-clock phục vụ correlation và timeline. Không lấy chênh lệch log timestamps giữa hai máy làm duration chính xác cao khi chưa xử lý clock skew.

### 27.3. Không log timestamp nguồn tùy ý như dữ liệu tin cậy

Một record bên ngoài có thể mang `eventTime` sai định dạng, timezone, tương lai hoặc bị sửa. Nếu dùng nó để đo freshness, phải validate và có cách phân biệt `source_event_time` với `received_at` do hệ thống ghi.

## 28. Kết hợp MessageHistory, Micrometer và tracing

### 28.1. MessageHistory là đường đi cục bộ

Khi được bật và headers được giữ, `MessageHistory` mô tả các component Spring Integration mà message đi qua. Nó giúp biết router/transformer/handler nào có thể đã nhận message, **không** tự đo latency hay chứng minh remote ACK.

### 28.2. Micrometer metrics là số liệu tổng hợp

Nên theo dõi:

| Tín hiệu | Cách dùng |
|---|---|
| Ingress/egress attempts | So sánh số lượng, phát hiện drift |
| Handler failure/retry | Phát hiện lỗi tăng nhưng tránh đếm attempt thành unique event |
| Queue depth/oldest age | Biết nghẽn giữa inbound và outbound |
| Poller last tick/empty/error | Phân biệt không có data với poller dừng |
| Transport confirm rate | Đánh giá publish/upload/call |
| Consumer lag/DLQ | Theo dõi broker backlog và lỗi cuối |
| Business completion SLI | Xác nhận mục tiêu dịch vụ end-to-end |

**Không đưa `correlation_ref` vào meter tags**; giữ ID ở log/trace. Với distributed tracing, tận dụng instrumentation tương thích với Spring Boot/Micrometer/OpenTelemetry và các header mappers theo giao thức.

### 28.3. Một flow “có đủ quan sát”

~~~mermaid
flowchart TD
    A[SLI cảnh báo end-to-end delay] --> B[Metrics: queue / poller / adapter]
    B --> C[Trace context: service và span]
    C --> D[Structured logs theo correlation_ref]
    D --> E[MessageHistory / checkpoint IDs cục bộ]
    E --> F[Broker ACK / DB commit / HTTP result]
    F --> G[Reconciliation và hành động khắc phục]
~~~

Mỗi lớp trả lời một câu hỏi khác nhau; correlation logs là **liên kết điều tra**, không thay metric alert và không thay state authority của hệ thống đích.

## 29. Bảo mật và bảo vệ dữ liệu trong correlation logs

### 29.1. ID cũng có thể là dữ liệu nhạy cảm

Correlation ID chứa email, số điện thoại, account number, filename, URL hoặc raw business ID có thể làm lộ PII. Hash không có secret cho email/số điện thoại entropy thấp cũng có thể bị đoán. Nếu cần ánh xạ ID nhạy cảm, cân nhắc **opaque reference do hệ thống phát** hoặc cơ chế HMAC có quản lý khóa và đánh giá privacy.

### 29.2. Những trường cần tránh

- Raw payload, HTTP request/response bodies, Kafka/JMS/AMQP message bodies.
- `Authorization`, `Cookie`, OAuth access/refresh token, API key, SSH private key.
- Full File/SFTP path chứa tên khách hàng, tenant hoặc tài khoản.
- SQL bind values, database rows, customer data.
- Exception messages có nhúng body/URL/secret.
- Toàn bộ Spring `MessageHeaders` hoặc `MessageHistory` xuất qua network.
- Arbitrary client-supplied IDs chưa kiểm tra; newline/control characters gây log injection.

### 29.3. Kỹ thuật an toàn theo lớp

1. **Omission/allowlist:** chỉ tạo structured log object từ trường cần thiết.
2. **Validation:** giới hạn ký tự/độ dài/giá trị enum.
3. **Separation:** log diagnosis và audit data có policy riêng.
4. **RBAC/retention:** hạn quyền truy cập logs, log export và vòng đời dữ liệu.
5. **Size/rate limits:** giữ chi phí và ngăn log flood khi retry storm.
6. **No raw fallback:** khi sanitizer/parser lỗi, emit error class thay vì dump input.
7. **Transport boundary control:** chỉ propagate headers được cho phép.

### 29.4. Log correlation không phải authorization proof

Người gửi có thể giả một giá trị `correlationRef` từng thấy. Không dùng nó để quyết định “message đã được xác thực”, “payment đã được phê duyệt” hay “có quyền đọc dữ liệu”. Phải dựa vào authentication, authorization, message validation và state nghiệp vụ đáng tin.

## 30. Hợp đồng log mẫu: từ source đến target

Đội phát triển có thể định nghĩa một taxonomy hữu hạn:

| Event | Khi phát | Các field bắt buộc |
|---|---|---|
| `POLL_STARTED` | Poll scheduler bắt đầu | flow, poll_ref, source_type |
| `POLL_EMPTY` | Poll kết thúc không có item | flow, poll_ref, outcome |
| `INGRESS_ACCEPTED` | Có message đầu vào hợp lệ về transport | correlation_ref, flow, component |
| `VALIDATION_REJECTED` | Filter/schema reject | correlation_ref, bounded reason |
| `BRANCH_SELECTED` | Router chọn destination | correlation_ref, branch enum |
| `OUTBOUND_ATTEMPTED` | Bắt đầu call/publish/upload | correlation_ref, attempt_ref, target |
| `TRANSPORT_CONFIRMED` | Đích ACK theo protocol | correlation_ref, attempt_ref, receipt |
| `REMOTE_TIMEOUT` | Không biết có commit chưa | correlation_ref, attempt_ref, unknown |
| `BUSINESS_COMPLETED` | Có bằng chứng completion nghiệp vụ | correlation_ref, evidence_ref |
| `TERMINAL_FAILED` | Event hết retry/được chuyển fail state | correlation_ref, reason, attempts |
| `DLQ_ENQUEUED` | Broker chấp nhận DLQ publish | correlation_ref, DLQ ref |
| `REPLAY_STARTED` | Một lần replay được duyệt | correlation_ref, replay_ref, replay_of |

### 30.1. Phân biệt outcome theo tầng

Một log `TRANSPORT_CONFIRMED` cần ghi `confirmation_scope` khi có nhiều nghĩa, chẳng hạn `broker_publish`, `remote_http_response` hoặc `file_handoff`. `BUSINESS_COMPLETED` chỉ emit khi logic của đích/transaction cho phép kết luận. Điều này ngăn dashboard tổng hợp nhầm `2xx` với business success.

### 30.2. Ví dụ end-to-end File → Kafka → JDBC

~~~text
09:00:00 POLL_STARTED         poll_ref=p-01 source=file
09:00:01 INGRESS_ACCEPTED     correlation_ref=corr-abc source=file
09:00:02 VALIDATED            correlation_ref=corr-abc component=parseInvoice
09:00:03 OUTBOUND_ATTEMPTED   correlation_ref=corr-abc attempt_ref=k-01 target=kafka
09:00:04 TRANSPORT_CONFIRMED  correlation_ref=corr-abc attempt_ref=k-01
09:00:09 INGRESS_ACCEPTED     correlation_ref=corr-abc source=kafka
09:00:11 DB_UPDATE_ATTEMPTED  correlation_ref=corr-abc attempt_ref=db-01
09:00:12 BUSINESS_COMPLETED   correlation_ref=corr-abc evidence_ref=tx-opaque
~~~

Đây là dữ liệu **giả lập** và thời gian chỉ minh họa. Log còn thiếu không mặc nhiên nghĩa message bị mất; cần kiểm tra collector, sampling, broker lag, transaction và external state.

## 31. Kiểm thử helper cấp correlation và dữ liệu log

### 31.1. JUnit cho định dạng và giá trị mới

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class CorrelationRefsTest {
    @Test
    void createsOpaqueReference() {
        String ref = CorrelationRefs.issueInternal();
        assertTrue(ref.startsWith("corr-"));
        assertFalse(ref.contains("@"));
        assertTrue(ref.length() <= 64);
    }

    @Test
    void rejectsUnsafeCandidate() {
        String ref = CorrelationRefs.acceptTrustedOrIssue(
                "foo\nFAKE-LOG-EVENT");
        assertTrue(ref.startsWith("corr-"));
        assertFalse(ref.contains("\n"));
    }
}
~~~

Test này chỉ chứng minh helper xử lý **hình dạng ID**. Nó không chứng minh một HTTP sender đáng tin hay correlation propagation xuyên broker. `acceptTrustedOrIssue` chỉ được dùng theo trust policy đã nói ở mục 6.

### 31.2. Kiểm thử cấu trúc log

Tạo input giả chứa `accessToken`, `password`, `customerEmail`, JSON lồng nhau, Kafka key, filename nhạy cảm và CR/LF. Capture log output của handler và kiểm tra:

- Log chỉ có field allowlist và enum values.
- Không có bất cứ marker secret/PII giả nào.
- Một request có cùng correlation qua các checkpoints nội bộ.
- Retry tạo attempt ID riêng; không tạo logical correlation mới tùy tiện.
- Header tùy ý không tự xuất ra network.
- Khi parser lỗi, không fallback log raw payload.
- Async work không giữ lại MDC của message trước.

### 31.3. Đo cả trường hợp message không xuất hiện

Đối với poller, kiểm thử `POLL_EMPTY`/`POLL_FAILED` độc lập với `INGRESS_ACCEPTED`, vì không phải poll nào cũng phát Spring Message. Với HTTP pre-auth failure hoặc Kafka deserialization failure, đảm bảo có event kỹ thuật dù chưa có message correlation.

## 32. Ma trận kiểm thử end-to-end theo adapter

| Test case | Input/tình trạng | Điều cần chứng minh |
|---|---|---|
| **HTTP happy path** | Request → outbound 2xx | Correlation qua ingress, outbound, reply; outcome đúng |
| **HTTP 202 async** | Remote chấp nhận nhưng chưa xử lý | Log `accepted` khác `completed` |
| **HTTP timeout** | Remote có thể commit | `UNKNOWN_OUTCOME`, không retry mù |
| **File parser reject** | File schema sai | Có source/correlation ref khi đã tạo message, không in file path/body |
| **SFTP poll empty** | Remote không có file | Có poll log, không tạo message correlation giả |
| **SFTP interrupted transfer** | File upload dở | Transfer attempt + resume/readback theo policy |
| **JMS rollback** | Cùng message bị redeliver | Logical ref ổn định nếu contract hỗ trợ; attempt mới |
| **AMQP requeue** | Một poison message nhiều deliveries | Tách deliveries và terminal failure; không log body |
| **Kafka new process** | A publish, B consume | Header mapped/tracing extract đúng; local Message ID khác |
| **Kafka DLQ replay** | Replay sau nhiều giờ | Replay ref và lineage, không bắt buộc một trace cũ |
| **JDBC retry** | DB status chưa commit, remote đã xử lý | Idempotency/reconciliation, không tạo side effect trùng |
| **ExecutorChannel** | Handler chạy khác thread | Context được khôi phục đúng, không leak MDC |
| **Splitter/aggregator** | Batch nhiều items | Parent/child lineage, không coi result history là mọi item |
| **Filter discard** | Payload reject | Mã lý do và correlation xuất hiện ở đúng nhánh |
| **Logger/collector down** | Log thiếu | Business flow và telemetry failure policy được kiểm thử |

### 32.1. Không cần một framework test chung cho mọi giao thức

Mỗi adapter có semantics riêng. Test Kafka broker acknowledgment khác HTTP response; test transaction JDBC khác file handoff. Dù vậy có thể tái sử dụng **assertion chung về correlation header, safe log schema, attempt uniqueness và outcome taxonomy**.

## 33. Runbook CORR-01 — Không tìm thấy log outbound tương ứng inbound

**Trigger:** có event `INGRESS_ACCEPTED` nhưng không tìm được `OUTBOUND_ATTEMPTED`/`BUSINESS_COMPLETED` cùng correlation.

1. Xác minh ID được tìm là **internal correlation** và query log đã giới hạn đúng time range, service/instance, environment.
2. Kiểm tra **sampling, log level, collector health, dropped logs** trước khi kết luận event không xảy ra.
3. Xem history/checkpoints: filter có discard không? Router đã chọn nhánh nào? Transformer có ném exception không?
4. Với QueueChannel/ExecutorChannel, kiểm tra backlog, executor queue/rejection, in-flight và consumer health.
5. Với splitter/aggregator, kiểm tra parent/child refs và group completion/timeouts.
6. Tại outbound adapter, kiểm tra client attempts, error channel, retry/DLQ, connection và target timeout.
7. Xác định header propagation có mất ở custom MessageBuilder hoặc header mapper/broker boundary không.
8. Nếu flow sang service khác, tra broker record ID/offset/ACK và log receiver theo transport identity + trusted correlation.
9. Kiểm tra target/business state bằng phương pháp readback có thẩm quyền; thiếu log outbound **không tự chứng minh** target chưa được cập nhật.
10. Ghi incident, root cause, owner, evidence và việc sửa instrumentation/logic; kiểm thử không lặp lại.

### 33.1. Cây quyết định

~~~mermaid
flowchart TD
    A[Có INGRESS_ACCEPTED] --> B{Đã tìm đúng time range / service?}
    B -->|Không| C[Sửa truy vấn / collector scope]
    B -->|Có| D{Có checkpoint sau validation?}
    D -->|Không| E[Filter / transformer / error flow]
    D -->|Có| F{Có async queue/backlog?}
    F -->|Có| G[Queue age / executor / consumer health]
    F -->|Không| H{Có outbound attempt?}
    H -->|Không| I[Router / header lost / logs sampled]
    H -->|Có| J{Có external confirmation?}
    J -->|Không rõ| K[Retry / DLQ / remote reconciliation]
    J -->|Có| L[Business completion / target readback]
~~~

## 34. Runbook CORR-02 — Log cho thấy gửi trùng hoặc timeout

**Trigger:** một logical `correlation_ref` có hai hoặc nhiều outbound attempts, hoặc remote báo duplicate dù trong log chỉ có một `send`.

1. Nhóm theo logical correlation và business event reference **đã xác minh**.
2. Sắp xếp các `attempt_ref`, transport delivery IDs, retry index và các mốc timeout/ACK.
3. Đối chiếu retry policy (backoff, max attempts, exception classifier) và khả năng broker redelivery.
4. Tại target, kiểm tra **idempotency key, transaction log, business status và receipt**.
5. Nếu kết quả không rõ, đánh dấu `UNKNOWN_OUTCOME` cho tới khi reconcile; không tự replay ngay.
6. Xác định do duplicate source, retry sau timeout, consumer rollback, connector timeout hay operator replay.
7. Phân biệt **attempt count** với **unique events confirmed** trong metrics/audit.
8. Nếu có side effect trùng, thực hiện remediation nghiệp vụ có approval/owner thay vì xóa log.
9. Sửa idempotent receiver/outbox/inbox/transaction boundary nếu nguyên nhân thuộc thiết kế.
10. Bổ sung tests có timeout sau remote commit và redelivery trước commit.

## 35. Dashboard và alerting hỗ trợ correlation logging

### 35.1. Dashboard ba tầng

| Tầng | Panels/thông tin | Mục tiêu |
|---|---|---|
| **Business SLI** | Unique completion %, p95 end-to-end, oldest pending age | Luồng có đáp ứng nhu cầu không? |
| **Flow/adapter** | Ingress, filters, channel queue, outbound attempts, confirms, retry, DLQ | Nghẽn/lỗi ở giai đoạn nào? |
| **Case investigation** | Tìm theo correlation, trace, broker ref, attempt | Truy lại một incident cụ thể |

### 35.2. Những cảnh báo hữu ích

- Có ingress events nhưng xác nhận outbound giảm bất thường, kết hợp flow throughput đủ lớn.
- Queue/broker backlog age vượt SLO, dù error count thấp.
- Tỷ lệ `UNKNOWN_OUTCOME` hoặc timeout tăng; remote may-have-committed.
- Retry/redelivery tăng nhưng unique business completion không tiến triển.
- Correlation propagation thất bại giữa hai service trong integration tests/telemetry probes.
- Logs/meter exporter mất dữ liệu; không coi **no data** là 0 lỗi.

**Không xây cảnh báo với mỗi correlation ID là một metric series.** Correlation nằm ở log index/trace search, metrics chỉ dùng flow, component, protocol, outcome có cardinality thấp.

### 35.3. Logging coverage không phải business success

Một dashboard hiển thị “100% messages có correlation” chứng minh instrumentation coverage của các events đo được, **không** chứng minh mọi message đã được xử lý đúng. Cần thêm confirmation, correctness checks và SLO theo contract.

## 36. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Giải pháp |
|---|---|---|
| Dùng raw email/filename làm correlation | PII rò qua logs/metrics | Opaque internal ref, mapping có quyền |
| Dùng `MessageHeaders.ID` xuyên mọi service | Mất liên kết khi message mới được tạo | Contract correlation header riêng |
| Tạo ID mới ở mọi handler | Không thể nối flow | Preserve correlation; chỉ thêm attempt/branch ID |
| Dùng trace ID làm idempotency key | Replay và sampling khó đảm bảo semantics | Business idempotency key được thiết kế riêng |
| Đưa correlation ID vào Micrometer tag | High cardinality | ID ở structured logs/tracing |
| Chỉ dựa MDC khi qua executor | Mất hoặc lẫn ID giữa threads | Message header + context propagation + cleanup |
| Copy toàn bộ MessageHeaders qua Kafka/HTTP | Lộ secret/topology, serialization lỗi | Header allowlist/mapper |
| Log whole `Message<?>` khi error | Rò payload/headers | Safe projection, reason enum |
| Ghi `BUSINESS_COMPLETED` sau `send()` | Báo success sai khi broker/remote lỗi | Emit theo ACK/commit đúng hợp đồng |
| Không có `attempt_ref` cho retry | Đếm trùng thành nhiều events | Logical correlation + attempt ID riêng |
| Dùng timestamp để suy causal order | Sai khi async/clock skew | Trace relationships/attempt/sequence |
| Bỏ qua error trước khi có Message | Không giải thích được poll/parse errors | Adapter/poller/client event refs |
| Ép replay dài ngày dùng cùng trace | Trace khổng lồ, sai session semantics | Trace mới, giữ lineage/replay_ref |
| Retry timeout không readback | Duplicate side effects | Idempotency, reconciliation |
| Chỉ log transport ACK | Không biết downstream business result | Completion event/target evidence |

## 37. Các tình huống thực hành có lời giải định hướng

### Tình huống A — HTTP đã nhận đơn, Kafka chưa xuất hiện

Log ingress có `corr-01`, nhưng không thấy Kafka publish confirm.

**Hướng xử lý:** tìm checkpoint validate/transform/router, kiểm tra QueueChannel, outbound attempt ID, producer callback, lỗi serialization và broker availability. Không kết luận Kafka đã nhận record chỉ vì channel send trả thành công.

### Tình huống B — Kafka consumer không thấy trace của producer

Service A có trace ID, service B nhận record và log tạo trace mới; correlation ID vẫn giống nhau.

**Hướng xử lý:** kiểm tra producer inject/consumer extract tracing context, header mapper/serializer và instrumentation ở hai service. Correlation đã đủ nối case ở mức log; tracing cần cấu hình đúng, không copy raw context thủ công.

### Tình huống C — SFTP poller không có log correlation

Không có file mới được tải vì remote authentication thất bại trước khi adapter tạo message.

**Hướng xử lý:** dùng `poll_ref`/session event và reason class `AUTH_FAILURE`, xác minh remote connectivity. Không kỳ vọng một MessageHistory/correlation header cho message chưa tồn tại.

### Tình huống D — Cùng JMSCorrelationID nhưng hai message khác nhau

Hai producer dùng cùng `JMSCorrelationID` do cách đặt ID bằng timestamp ngắn.

**Hướng xử lý:** điều tra uniqueness/trust của hợp đồng, không gộp business events theo JMSCorrelationID đơn lẻ. Thiết kế opaque ID đủ phân biệt và giữ JMSMessageID/delivery attempt riêng.

### Tình huống E — HTTP timeout nhưng payment đã được xử lý

Log có `OUTBOUND_ATTEMPTED` và timeout; operator muốn retry ngay.

**Hướng xử lý:** ghi `UNKNOWN_OUTCOME`, kiểm tra idempotency key và trạng thái remote theo API được duyệt. Nếu remote đã commit, ghi confirmation/reconciliation, không tạo giao dịch thứ hai.

### Tình huống F — Mất correlation sau một transformer

Custom code tạo `MessageBuilder.withPayload(...).build()` mà không giữ application headers.

**Hướng xử lý:** cập nhật header propagation cho same-process flow, thêm test. Không copy bừa framework headers khi ra broker; dùng allowlist mapping theo contract.

### Tình huống G — MDC bị dính sang message tiếp theo

Executor pool tái sử dụng thread; log message B mang correlation của A.

**Hướng xử lý:** dùng context-aware executor/instrumentation và scope MDC có cleanup/restore. Đảm bảo correlation nằm trong message; test xử lý nối tiếp và song song nhiều messages.

### Tình huống H — Splitter tạo 500 items, aggregator thiếu 3

Chỉ có batch correlation trong log, không biết item nào chưa hoàn tất.

**Hướng xử lý:** thêm parent/item lineage refs hoặc sequence indices an toàn, per-item result và aggregation state/timeout. Không in toàn bộ batch để tìm 3 items và không kỳ vọng result history chứa tất cả paths.

### Tình huống I — JMS redelivery tạo 50 log “processed”

Một message rollback nhiều lần nhưng handler ghi `PROCESSED` trước transaction commit.

**Hướng xử lý:** đổi event thành `PROCESSING_ATTEMPTED` trước commit và `BUSINESS_COMPLETED` chỉ sau mốc xác nhận, tách redelivery attempts với unique outcome. Kiểm thử rollback.

### Tình huống J — Kafka key chứa email được dùng làm tag

Dashboard metrics có hàng triệu series theo `kafka_key` và rò dữ liệu.

**Hướng xử lý:** bỏ label không hữu hạn/nhạy cảm, giữ tag flow/target/outcome; tạo opaque correlation trong log/trace có phân quyền. Xem incident data exposure theo policy.

### Tình huống K — File outbound ghi xong nhưng đối tác chưa xử lý

Ứng dụng log `FILE_SENT` ngay sau ghi local path, phía đối tác chưa đọc file.

**Hướng xử lý:** phân biệt local write, remote handoff/rename và business completion, bổ sung callback/status nếu hợp đồng yêu cầu. Không kết luận mục tiêu end-to-end chỉ qua outbound adapter success.

### Tình huống L — Batch database poll trùng sau crash

DB poller lấy rows, gọi API thành công, JVM crash trước khi mark processed; lần sau poll lại.

**Hướng xử lý:** nối hai attempts qua logical row reference có quyền, kiểm tra remote outcome và idempotency. Xây durable checkpoint/outbox hoặc reconciliation theo yêu cầu; log alone không ngăn duplicate.

### Tình huống M — Tracing bị sampling, vẫn cần điều tra

Một message hiếm bị lỗi, backend tracing không lưu span do sampling nhưng structured log có correlation.

**Hướng xử lý:** tra log theo opaque reference, endpoint events, broker identity và error class; dùng metrics để xác định phạm vi. Không bật raw payload logging trên toàn production.

### Tình huống N — ErrorMessage không có original message

Handler error không cung cấp original message tại checkpoint cần điều tra, log thiếu correlation.

**Hướng xử lý:** kiểm tra error flow và adapter/client context, giữ correlation tại request/delivery attempt nơi được phép; nếu chưa có Spring Message, dùng source poll/client ref. Không gán ID giả cho event lỗi.

## 38. Checklist thiết kế, kiểm thử và vận hành

### 38.1. Thiết kế contract

- [ ] Đã định nghĩa logical event, correlation reference và owner phát ID?
- [ ] Có phân biệt business ID, trace ID, Spring Message ID và attempt ID?
- [ ] Ingress từ bên ngoài có trust boundary và định dạng kiểm tra?
- [ ] Có taxonomy `attempted/confirmed/completed/unknown/failed` rõ nghĩa?
- [ ] Có xác định điểm ghi log khi poller/client lỗi **trước khi tạo Message**?
- [ ] Có lineage cho splitter/aggregator và DLQ replay?
- [ ] Có idempotency/reconciliation độc lập correlation log?

### 38.2. Cấu hình flow và adapter

- [ ] Application header được giữ qua transformer/router/filter theo contract?
- [ ] QueueChannel/ExecutorChannel có context propagation/MDC cleanup?
- [ ] WireTap chỉ ghi safe projection, không raw Message?
- [ ] HTTP dùng route template, không log token/body/full URI?
- [ ] File/SFTP dùng opaque file reference, không raw path/secret?
- [ ] JMS/AMQP có đúng broker message/delivery/ack semantics?
- [ ] Kafka có đúng header mapping, topic/partition/offset và confirm semantics?
- [ ] JDBC có query/transaction/commit markers đúng điểm?
- [ ] Outbound header mapper chỉ gửi allowlist và trace context đã duyệt?

### 38.3. Kiểm thử

- [ ] Có tests ingress mới, trusted producer, untrusted/malformed header?
- [ ] Log không chứa secret/PII giả, ký tự newline/control nguy hiểm?
- [ ] Header không mất khi tạo message mới?
- [ ] Một retry có attempt mới nhưng giữ logical correlation?
- [ ] Có test timeout sau remote commit và redelivery/replay?
- [ ] Split/aggregate branch lineage có thể truy lại?
- [ ] Async thread không bị lẫn MDC giữa messages?
- [ ] Phân biệt `no data` và `message lost` khi telemetry bị lỗi?
- [ ] Message history/metrics/traces bổ trợ chứ không thay external state?

### 38.4. Vận hành incident

- [ ] Tra đúng flow/service/instance/time range và correlation?
- [ ] Check collector/sample/dropped logs trước khi suy message mất?
- [ ] Có xem queue depth/age, retry/DLQ và adapter health?
- [ ] Có ACK/commit/callback/transaction evidence ở target?
- [ ] `UNKNOWN_OUTCOME` có owner và readback trước retry?
- [ ] Không ghi raw payload khi debug hoặc xử lý exception?
- [ ] Có root cause, action item, test và bằng chứng closure?

## 39. Kết luận

**Correlation log giữa inbound và outbound** là một **hợp đồng quan sát**: mỗi hành trình tích hợp có ID tương quan đủ ổn định, mỗi lần thử có ID riêng, mỗi checkpoint có nghĩa rõ ràng và mỗi kết quả cuối cùng được xác nhận ở lớp thích hợp. Trong Spring Integration, header propagation qua MessageChannel, transformer, router, queue, gateway và broker phải được thiết kế có chủ đích; MDC và tracing giúp trình bày/ngữ cảnh hóa log nhưng không tự thay thế ứng dụng header hay hợp đồng message.

Với **File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC**, cần hiểu các mốc riêng như poll, file handoff, request/reply, broker ACK, offset commit và database transaction. Một dòng log `OUTBOUND_ATTEMPTED` hay `TRANSPORT_CONFIRMED` không chứng minh `BUSINESS_COMPLETED`. Kết hợp **structured logs đã loại dữ liệu nhạy cảm, opaque correlation reference, attempt/lineage IDs, Micrometer metrics, MessageHistory/tracing và xác minh trạng thái tại đích** giúp đội vận hành nối được đầu vào với đầu ra, điều tra retry/timeout chính xác và giảm nguy cơ dữ liệu bị xử lý lặp hoặc thất lạc.

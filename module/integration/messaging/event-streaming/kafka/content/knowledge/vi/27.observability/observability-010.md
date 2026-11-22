# Truyền trace context qua headers và nối trace bất đồng bộ

Trong hệ thống event streaming, một request thường đi qua nhiều service và có thể tiếp tục xử lý sau vài mili giây, vài phút hoặc lâu hơn. HTTP request kết thúc không có nghĩa công việc đã hoàn tất: producer ghi event vào Kafka, consumer nhận event, gọi database hoặc service khác rồi có thể phát thêm event mới. Nếu mỗi service tạo trace độc lập, đội vận hành khó lần theo toàn bộ hành trình của một nghiệp vụ.

Trace context propagation giải quyết vấn đề này bằng cách mang thông tin liên kết trace qua message headers. Producer inject context vào Kafka record; consumer extract context và tạo span liên quan; nếu xử lý tiếp trên thread khác hoặc qua một topic retry, ứng dụng tiếp tục truyền context theo chính sách đã chọn. Với luồng bất đồng bộ có nhiều nguồn đầu vào, span link giúp nối các trace mà không ép một span có nhiều parent.

## 1. Trace, span và context

Distributed trace mô tả hành trình của một công việc qua nhiều thành phần. Trace gồm các span; mỗi span đại diện cho một thao tác có thời gian bắt đầu/kết thúc, thuộc tính, sự kiện và trạng thái lỗi.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Trace | Toàn bộ hành trình của một nghiệp vụ | Tạo đơn hàng và gửi thông báo thanh toán |
| Trace ID | Định danh duy nhất của trace | 32 ký tự hex theo W3C Trace Context |
| Span | Một thao tác trong trace | Gửi record, xử lý message, ghi database |
| Span ID | Định danh một span | 16 ký tự hex theo W3C Trace Context |
| Parent span | Span trực tiếp tạo ra span hiện tại | Consumer span là con của producer span |
| Span link | Liên kết một span với span context khác mà không tạo quan hệ parent-child | Batch consumer nhận nhiều message |
| Trace context | Thông tin cần thiết để tiếp tục hoặc liên kết trace | traceparent, tracestate |
| Baggage | Metadata nghiệp vụ được truyền cùng context | tenant tier hoặc region, nếu được phép |

Một trace có thể đi qua nhiều process và host. Context là dữ liệu truyền giữa các process để backend tracing biết span mới liên quan tới span nào.

~~~mermaid
flowchart LR
    A[HTTP request span] --> B[Producer span]
    B --> C[(Kafka topic)]
    C --> D[Consumer span]
    D --> E[Database span]
    D --> F[HTTP client span]
    F --> G[Downstream service span]
~~~

Trong mô hình parent-child đơn giản, consumer span tiếp tục trace của producer span. Mỗi service tạo span riêng cho thao tác của mình; không dùng chung một span object qua nhiều process.

## 2. Vì sao Kafka cần truyền context qua headers?

Kafka là hệ thống lưu trữ và phân phối message bất đồng bộ. Producer và consumer không giữ một HTTP connection xuyên suốt quá trình xử lý. Message có thể nằm trong topic trước khi consumer đọc, được retry, replay hoặc chuyển qua một pipeline khác.

Nếu không truyền context:

- Producer trace kết thúc sau khi gửi record.
- Consumer tạo trace mới, không biết record xuất phát từ request nào.
- Downstream service tạo trace độc lập.
- Khi điều tra một request chậm hoặc thất bại, phải tìm log bằng event ID và ghép thủ công.

Khi truyền context:

- Producer gắn trace context vào Kafka headers.
- Consumer đọc headers và tạo span có quan hệ với producer.
- Các lời gọi downstream tiếp tục trace context.
- Trace backend hiển thị hành trình qua producer, broker boundary, consumer và downstream.

Headers phù hợp để mang metadata vận chuyển như trace context. Payload vẫn nên chứa dữ liệu nghiệp vụ và event ID theo contract. Không nhúng trace context vào business schema trừ khi có lý do tương thích rõ ràng.

## 3. W3C Trace Context: traceparent và tracestate

W3C Trace Context định nghĩa cách truyền context giữa các hệ thống. Hai header chính là traceparent và tracestate.

### traceparent

Định dạng phổ biến của version 00:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Các thành phần:

| Phần | Độ dài | Ý nghĩa |
|---|---:|---|
| version | 2 ký tự hex | Phiên bản định dạng |
| trace-id | 32 ký tự hex | Định danh trace, không được toàn số 0 |
| parent-id | 16 ký tự hex | Span ID cha, không được toàn số 0 |
| trace-flags | 2 ký tự hex | Cờ trace, bit thấp nhất hiện biểu thị sampled |

Giá trị flags thường gặp:

- 00: cờ sampled không được bật.
- 01: cờ sampled được bật.

Không tự tạo traceparent bằng cách nối chuỗi tùy ý. Dùng OpenTelemetry propagator để kiểm tra, inject và extract đúng định dạng, đồng thời xử lý version/flags.

### tracestate

tracestate mang thông tin vendor-specific đi kèm trace context, ví dụ thông tin của tracing vendor hoặc hệ thống sampling. Nó không thay thế traceparent. Ứng dụng thường nên giữ nguyên tracestate khi chuyển tiếp, trừ khi propagator yêu cầu cập nhật.

### baggage

Baggage là danh sách key/value được truyền xuyên suốt các service. Ví dụ:

~~~text
baggage: tenant-tier=gold,region=ap-southeast
~~~

Baggage không phải ACL, token xác thực hay nguồn dữ liệu đáng tin cậy. Chỉ đưa vào các thuộc tính không nhạy cảm, có giới hạn kích thước và được phép truyền qua ranh giới service. Không truyền password, access token, email, số điện thoại, dữ liệu thanh toán hoặc thông tin cá nhân.

## 4. Kafka headers lưu trace context như thế nào?

Kafka record có key, value, timestamp và headers. Mỗi header có key dạng String và value dạng byte array. OpenTelemetry TextMapPropagator làm việc với một carrier thông qua setter/getter; ứng dụng ánh xạ carrier đó vào Kafka Headers.

Các header thường gặp:

| Header | Nội dung |
|---|---|
| traceparent | Trace ID, parent span ID và trace flags |
| tracestate | Vendor-specific trace state |
| baggage | Metadata propagation được cho phép |

Tên header W3C được viết chữ thường. Nên dùng một dạng canonical nhất quán khi ghi vào Kafka.

### Không dùng Kafka key để truyền trace ID

Kafka key quyết định partitioning/compaction semantics và thường là entity ID như orderId hoặc customerId. Trace ID là metadata quan sát. Đổi key thành trace ID có thể làm thay đổi partition distribution, ordering theo aggregate và hiệu quả log compaction.

Giữ trace context trong headers; giữ business key trong record key; giữ event ID trong payload/header nghiệp vụ theo contract.

### Header có thể bị mất hoặc bị nhân đôi

Kafka Headers cho phép nhiều header cùng tên. Khi inject, tránh để lại nhiều traceparent khác nhau trong cùng record. Setter nên loại bỏ giá trị cũ trước khi thêm giá trị mới, hoặc ứng dụng phải có quy tắc rõ ràng cho header canonical.

Một số connector, SMT, bridge hoặc ứng dụng trung gian có thể tạo record mới và chỉ copy một phần headers. Cần kiểm tra pipeline thực tế để xác minh traceparent, tracestate và baggage được giữ đúng. Không mặc định mọi integration đều bảo toàn headers.

## 5. OpenTelemetry propagation với Java

OpenTelemetry cung cấp TextMapPropagator để inject/extract context vào carrier. Kafka Headers là carrier tùy chỉnh; ta định nghĩa TextMapSetter và TextMapGetter.

~~~java
import io.opentelemetry.context.propagation.TextMapGetter;
import io.opentelemetry.context.propagation.TextMapSetter;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public final class KafkaTraceHeaders {

    private KafkaTraceHeaders() {}

    public static final TextMapSetter<Headers> SETTER =
        (headers, key, value) -> {
            if (headers == null || value == null) {
                return;
            }
            headers.remove(key);
            headers.add(
                key,
                value.getBytes(StandardCharsets.UTF_8)
            );
        };

    public static final TextMapGetter<Headers> GETTER =
        new TextMapGetter<>() {
            @Override
            public Iterable<String> keys(Headers headers) {
                if (headers == null) {
                    return List.of();
                }
                return Arrays.stream(headers.toArray())
                    .map(Header::key)
                    .distinct()
                    .collect(Collectors.toList());
            }

            @Override
            public String get(Headers headers, String key) {
                if (headers == null || key == null) {
                    return null;
                }
                Header header = headers.lastHeader(key);
                if (header == null || header.value() == null) {
                    return null;
                }
                return new String(
                    header.value(),
                    StandardCharsets.UTF_8
                );
            }
        };
}
~~~

Đoạn code dùng List nên cần import java.util.List. Getter lấy header cuối cùng nếu record có header trùng tên; setter xóa header cũ trước khi thêm giá trị mới. Quy tắc này chỉ là cách xử lý carrier nhất quán của ứng dụng; tốt nhất là không tạo duplicate header ngay từ đầu.

Lấy propagator từ OpenTelemetry:

~~~java
TextMapPropagator propagator =
    GlobalOpenTelemetry.getPropagators()
        .getTextMapPropagator();
~~~

SDK/agent cần được cấu hình với W3C Trace Context propagator. Nếu dùng composite propagator, nó có thể inject/extract cả traceparent, tracestate và baggage.

## 6. Inject context khi publish bằng KafkaProducer

Producer span mô tả thao tác gửi message. Trước khi gọi send(), inject context hiện tại vào record headers để consumer có thể tiếp tục trace.

~~~java
public void publish(
        KafkaProducer<String, OrderEvent> producer,
        OrderEvent event) {

    Span span = tracer.spanBuilder("orders publish")
        .setSpanKind(SpanKind.PRODUCER)
        .startSpan();

    ProducerRecord<String, OrderEvent> record =
        new ProducerRecord<>(
            "orders.events",
            event.orderId(),
            event
        );

    try {
        try (Scope scope = span.makeCurrent()) {
            propagator.inject(
                Context.current(),
                record.headers(),
                KafkaTraceHeaders.SETTER
            );
        }

        producer.send(record, (metadata, error) -> {
            if (error != null) {
                span.recordException(error);
                span.setStatus(StatusCode.ERROR);
            }
            span.end();
        });
    }
    catch (RuntimeException error) {
        span.recordException(error);
        span.setStatus(StatusCode.ERROR);
        span.end();
        throw error;
    }
}
~~~

Ví dụ giả định tracer và propagator được inject từ OpenTelemetry SDK. Producer span được kết thúc trong callback khi send hoàn tất; nếu send ném lỗi đồng bộ, catch kết thúc span. Không kết thúc span ngay sau send() nếu muốn ghi nhận kết quả callback bất đồng bộ.

Trong ứng dụng production, cần xử lý callback exception, timeout và shutdown của producer. Nếu dùng transaction, span nên phản ánh kết quả commit/abort theo semantics ứng dụng, không chỉ thời điểm gọi send().

### Inject context nào?

Thông thường inject Context.current() khi producer span đang active. Propagator lấy span hiện tại để tạo traceparent. Nếu inject trước khi tạo producer span, consumer có thể trở thành sibling của producer thay vì child của producer. Cả hai mô hình có thể hợp lệ tùy tracing convention, nhưng cần chọn nhất quán.

## 7. Extract context khi consume

Consumer extract context từ record headers rồi tạo consumer/process span có parent là context được truyền tới.

~~~java
public void handle(ConsumerRecord<String, OrderEvent> record) {
    Context extracted = propagator.extract(
        Context.root(),
        record.headers(),
        KafkaTraceHeaders.GETTER
    );

    Span span = tracer.spanBuilder("orders process")
        .setParent(extracted)
        .setSpanKind(SpanKind.CONSUMER)
        .startSpan();

    try (Scope scope = span.makeCurrent()) {
        orderService.process(record.value());
    }
    catch (RuntimeException error) {
        span.recordException(error);
        span.setStatus(StatusCode.ERROR);
        throw error;
    }
    finally {
        span.end();
    }
}
~~~

Nếu record không có traceparent hợp lệ, propagator trả về context không có remote parent hợp lệ; span mới sẽ bắt đầu một trace mới. Không nên tự ghép trace ID từ event ID.

Consumer span nên có attributes hữu ích như messaging system, destination name, consumer group, partition, offset và operation. Dùng semantic conventions của OpenTelemetry messaging tương thích với instrumentation/version đang triển khai; không gắn payload hoặc thông tin cá nhân làm span attribute.

## 8. Producer span, consumer span và process span

Một message pipeline thường có nhiều thao tác khác nhau:

| Span | Span kind thường dùng | Mục đích |
|---|---|---|
| Publish message | PRODUCER | Ghi nhận gửi record vào Kafka |
| Receive/process message | CONSUMER | Ghi nhận consumer nhận và xử lý record |
| Database query | CLIENT hoặc span theo instrumentation DB | Ghi nhận truy vấn downstream |
| HTTP call | CLIENT | Ghi nhận request sang service khác |
| Retry publish | PRODUCER | Ghi nhận việc phát record sang retry topic |
| Retry processing | CONSUMER | Ghi nhận lần xử lý tiếp theo |

Span names và attributes nên tuân theo semantic conventions. Tránh tạo span quá chi tiết cho từng dòng code hoặc từng field nếu không giúp chẩn đoán.

### Không tạo span trùng

Java agent hoặc instrumentation library có thể tự tạo producer/consumer spans cho Kafka client. Nếu đồng thời tự tạo span thủ công cho cùng thao tác, trace có thể xuất hiện hai span chồng lặp.

Chọn một cách:

- Dùng OpenTelemetry Java agent hoặc instrumentation library tự động.
- Dùng Micrometer Observation/Spring Kafka instrumentation.
- Tự inject/extract và tạo span thủ công khi cần custom behavior.

Nếu kết hợp, xác định rõ span nào do agent tạo và span nào do ứng dụng tạo. Có thể chỉ cần manual propagation cho một integration đặc biệt thay vì tạo lại toàn bộ producer/consumer spans.

## 9. Truyền context qua thread hoặc Executor

OpenTelemetry Context thường được gắn với execution scope hiện tại. Khi chuyển công việc sang thread pool, thread mới không mặc nhiên kế thừa ThreadLocal context của thread gửi task.

Ví dụ sai:

~~~java
executor.execute(() -> {
    // Context.current() có thể là root hoặc context khác.
    processOrder();
});
~~~

Capture context trước khi submit và wrap task:

~~~java
Context captured = Context.current();

executor.execute(
    captured.wrap(() -> {
        processOrder();
    })
);
~~~

Context.wrap() kích hoạt context đã capture trong lúc task chạy và khôi phục context trước đó khi task kết thúc. Cách này giúp span downstream trở thành child đúng của span hiện tại.

### Giữ span sống tới khi async task hoàn tất

Nếu listener tạo consumer span, submit task rồi kết thúc span ngay khi listener return, span sẽ không bao phủ thời gian xử lý thực tế. Với async processing, span phải được kết thúc khi công việc hoàn tất.

~~~java
public void handleAsync(ConsumerRecord<String, OrderEvent> record) {
    Context extracted = propagator.extract(
        Context.root(),
        record.headers(),
        KafkaTraceHeaders.GETTER
    );

    Span span = tracer.spanBuilder("orders async process")
        .setParent(extracted)
        .setSpanKind(SpanKind.CONSUMER)
        .startSpan();

    Context taskContext = extracted.with(span);

    executor.execute(taskContext.wrap(() -> {
        try {
            orderService.process(record.value());
        }
        catch (RuntimeException error) {
            span.recordException(error);
            span.setStatus(StatusCode.ERROR);
        }
        finally {
            span.end();
        }
    }));
}
~~~

Đây là ví dụ tracing, chưa thể hiện đầy đủ acknowledgment/offset semantics. Nếu consumer dùng manual acknowledgment, chỉ acknowledge sau khi async task hoàn tất thành công. Nếu process dừng trước đó, record cần được replay; side effect phải idempotent.

Không giữ Scope mở trên thread listener rồi đóng ở thread executor khác. Scope phải được mở/đóng trong cùng execution context; truyền Context qua wrap hoặc tạo scope mới trong task.

## 10. Reactive pipeline và context propagation

Reactive pipeline có thể đổi thread ở từng operator. ThreadLocal không phải nơi lưu context đáng tin cậy cho mọi scheduler. Khi dùng Reactor, cần instrumentation/context propagation tương thích hoặc dùng cơ chế Reactor Context để giữ context qua operator.

Các nguyên tắc:

- Dùng OpenTelemetry instrumentation hỗ trợ Reactor nếu ứng dụng đã dùng agent.
- Không giả định Context.current() ở mọi callback đều giống nhau nếu chưa có propagation.
- Capture context trước khi subscribe/dispatch công việc.
- Kiểm thử khi pipeline đổi scheduler.
- Đảm bảo span kết thúc khi publisher complete/error/cancel.

Nếu callback bị cancel nhưng span không được đóng, trace backend sẽ có span treo hoặc duration sai. Nếu nhiều subscription dùng chung một Span object, dữ liệu có thể bị trộn; mỗi execution cần lifecycle span rõ ràng.

## 11. Fan-out: một message tạo nhiều công việc

Một consumer có thể nhận một event rồi phát nhiều event khác:

~~~mermaid
flowchart TD
    A[orders.events] --> B[Consumer process span]
    B --> C[Inventory update span]
    B --> D[Payment request span]
    B --> E[Notification publish span]
~~~

Các span downstream có thể là child của consumer process span. Khi publish từng output message, producer span tương ứng inject context hiện tại để consumer downstream tiếp tục đúng trace.

Nếu fan-out chạy song song:

- Capture cùng context cha trước khi submit các task.
- Mỗi task tạo span riêng.
- Không chia sẻ mutable Span/Scope không an toàn giữa thread.
- Đóng từng span khi task tương ứng hoàn tất.
- Theo dõi lỗi riêng của từng nhánh.

Một nhánh thất bại không nhất thiết làm các nhánh khác thất bại. Trace giúp quan sát quan hệ, còn retry/compensation vẫn là logic nghiệp vụ.

## 12. Fan-in và span links

Fan-in xảy ra khi một consumer nhận nhiều message từ nhiều trace rồi tạo một kết quả chung. Một span chỉ có một parent trong mô hình parent-child. Không nên chọn tùy tiện một message làm parent duy nhất nếu công việc thực sự phụ thuộc vào nhiều message.

Span links biểu diễn quan hệ với nhiều span context:

~~~mermaid
flowchart LR
    A[Trace A: event 1] --> D[Batch aggregation span]
    B[Trace B: event 2] --> D
    C[Trace C: event 3] --> D
    D --> E[Aggregated output event]
~~~

Ví dụ tạo batch span có links:

~~~java
SpanBuilder builder = tracer.spanBuilder("orders batch process")
    .setSpanKind(SpanKind.CONSUMER)
    .setNoParent();

for (ConsumerRecord<String, OrderEvent> record : batch) {
    Context extracted = propagator.extract(
        Context.root(),
        record.headers(),
        KafkaTraceHeaders.GETTER
    );

    SpanContext remoteSpan =
        Span.fromContext(extracted).getSpanContext();

    if (remoteSpan.isValid()) {
        builder.addLink(remoteSpan);
    }
}

Span batchSpan = builder.startSpan();
try (Scope scope = batchSpan.makeCurrent()) {
    batchProcessor.process(batch);
}
finally {
    batchSpan.end();
}
~~~

Span links phù hợp với batch, aggregation, scheduled job hoặc process gom nhiều message. Nếu mỗi record được xử lý độc lập trong batch, tạo một consumer span riêng cho mỗi record cũng có thể rõ ràng hơn.

Không tạo hàng chục nghìn links trong một span nếu batch rất lớn. Có thể giới hạn links, chia batch hoặc lưu danh sách event ID trong hệ thống audit riêng.

## 13. Retry và Dead Letter Topic

Retry tạo một lần xử lý mới cho cùng một công việc. Có hai cách liên kết trace thường gặp:

### Giữ cùng trace qua retry ngắn

Với retry nhanh, có thể giữ trace context ban đầu qua retry topic hoặc release/redelivery. Consumer attempt tiếp theo tiếp tục cùng trace, giúp xem toàn bộ attempts trong một trace.

### Tạo trace mới và link về lần trước

Với retry bị trì hoãn lâu, ví dụ chờ hàng giờ, giữ một trace mở quá lâu có thể gây khó đọc và vượt retention của tracing backend. Có thể tạo trace mới cho retry attempt và thêm span link về context của lần xử lý trước. Bảo toàn event ID/original trace ID trong metadata để điều tra.

~~~mermaid
flowchart LR
    A[Original consumer span] --> B[Retry publish span]
    B --> C[(retry topic)]
    C --> D[New retry trace]
    A -. span link .-> D
    D --> E[Retry process span]
    E --> F[DLT nếu hết retry]
~~~

Không có một chính sách duy nhất đúng cho mọi hệ thống. Quyết định phụ thuộc thời gian retry, retention trace, khả năng tìm kiếm và yêu cầu liên kết nghiệp vụ.

### DLT cần giữ trace context

Khi chuyển record sang DLT, giữ:

- traceparent/tracestate hoặc link metadata theo policy.
- event ID và original topic/partition/offset.
- retry attempt/delivery count.
- exception type và failure timestamp.
- correlation ID nghiệp vụ nếu có.

Không đưa stack trace dài hoặc payload nhạy cảm vào baggage. DLT consumer có thể tạo span mới và link tới trace gốc để điều tra mà không phải giữ trace gốc mở vô thời hạn.

## 14. Kafka Streams và trace headers

Kafka Streams nhận record từ source topic và có thể tạo output record ở sink topic. Trace context cần được bảo toàn hoặc được thay đổi có chủ đích khi topology xử lý.

Với Processor API, headers có thể được đọc từ record/context và gắn vào output record. Khi dùng DSL transformations, cần kiểm tra semantics của API/version đang dùng để biết headers được giữ hay thay đổi như thế nào.

Nguyên tắc:

- Giữ trace context khi output là kết quả trực tiếp của một input event.
- Khi một output phụ thuộc nhiều input events, cân nhắc span links.
- Khi topology tạo event mới theo lịch hoặc không có input parent, bắt đầu trace mới.
- Không thay business key chỉ để truyền trace ID.
- Kiểm thử header propagation qua repartition topics, stateful operations và sink topics.

Repartition/changelog topics là internal resources của Kafka Streams. Không mặc định headers sẽ được giữ qua mọi internal transformation hoặc version; xác minh bằng integration test trên đúng Kafka Streams version.

## 15. Kafka Connect và Debezium

Kafka Connect source connector có thể tạo record từ database transaction log; sink connector có thể chuyển record ra hệ thống đích. Tracing context có thể được tạo ở source application trước khi ghi database, nhưng CDC connector không nhất thiết tự biết context của transaction nghiệp vụ.

Với Outbox:

- Ứng dụng ghi event ID và metadata cần thiết trong outbox row.
- Nếu muốn giữ trace context, lưu traceparent/tracestate vào các cột/metadata outbox có contract rõ ràng.
- Debezium/EventRouter có thể định tuyến outbox record; cần cấu hình và kiểm tra header transformation.
- Consumer extract context từ Kafka headers nếu context đã được chuyển đúng.

Không giả định Debezium tự tái tạo trace context của HTTP request chỉ từ transaction log. Nếu ứng dụng không lưu context trong outbox, CDC connector không thể suy ra parent span đã tạo transaction.

SMT có thể đổi topic, unwrap payload hoặc copy field thành header. Kiểm tra transform chain để bảo đảm không xóa traceparent/tracestate ngoài ý muốn. Nếu chuyển trace context từ payload column sang Kafka header, phải chuẩn hóa encoding và bảo vệ dữ liệu.

## 16. Spring Kafka và Micrometer Observation

Spring Kafka hỗ trợ observation cho KafkaTemplate và listener container ở các phiên bản tương thích. Khi bật observation và cấu hình tracing bridge phù hợp, Micrometer có thể tạo observation/span và truyền context theo integration.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    template:
      observation-enabled: true
    listener:
      observation-enabled: true

management:
  tracing:
    sampling:
      probability: 0.10
~~~

Các property và khả năng propagation phụ thuộc Spring Boot/Spring Kafka/Micrometer version. Hãy kiểm tra tài liệu phiên bản đang dùng và xác nhận traceparent thực sự xuất hiện trong Kafka headers. Bật observation không có nghĩa mọi custom executor, callback hoặc integration ngoài Spring tự động giữ context.

### Khi nào cần manual propagation?

- Một custom KafkaProducer/Consumer không đi qua Spring instrumentation.
- Một bridge hoặc retry pipeline không giữ headers.
- Một batch operation cần span links.
- Một executor/reactive callback cần context propagation riêng.
- Một outbox/CDC pipeline cần khôi phục context đã lưu từ database.

Nếu Spring Kafka đã tự inject/extract, không inject lần thứ hai bằng code thủ công. Tránh duplicate traceparent và span trùng.

## 17. Automatic instrumentation với OpenTelemetry Java Agent

OpenTelemetry Java Agent có thể instrument Kafka clients và nhiều framework phổ biến. Khi dùng agent:

- Cấu hình OTLP exporter/collector.
- Chọn propagator, thường gồm tracecontext và baggage.
- Xác minh producer/consumer spans được tạo.
- Kiểm tra headers có traceparent/tracestate.
- Kiểm tra context đi qua executor/reactive framework.
- Không tạo manual span trùng với span tự động.

Ví dụ biến môi trường minh họa:

~~~bash
OTEL_SERVICE_NAME=orders-service
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_PROPAGATORS=tracecontext,baggage
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.10
~~~

Các biến môi trường cần khớp OpenTelemetry Java Agent/SDK version. Agent cần được nạp bằng cơ chế startup phù hợp; chỉ khai báo biến môi trường không tự cài agent vào JVM.

### Chọn agent hay manual instrumentation

| Cách | Phù hợp khi | Lưu ý |
|---|---|---|
| Java agent | Muốn tự động instrument Kafka client, HTTP, DB và framework | Cần kiểm soát version, exporter và duplicate instrumentation |
| Micrometer Observation | Ứng dụng Spring muốn tích hợp observation/tracing theo hệ sinh thái Spring | Cần bridge/exporter tương thích |
| Manual OpenTelemetry API | Có luồng đặc biệt, fan-in, custom carrier hoặc async boundary | Tốn công quản lý span lifecycle và propagation |

Có thể kết hợp agent với manual span cho business operation, nhưng phải phân biệt business span với span transport đã được instrument tự động.

## 18. Sampling và trace bị đứt đoạn

Sampling quyết định trace/span nào được ghi và export. W3C traceparent có trace flags, nhưng sampling policy thực tế do SDK/collector/backend quyết định.

- Parent-based sampler thường tôn trọng sampled decision từ upstream.
- Trace ID ratio sampler chọn trace theo tỷ lệ.
- Tail sampling ở collector có thể giữ trace dựa trên lỗi/latency nếu collector nhận đủ spans.

Nếu producer không sampled, consumer có thể không export span theo parent-based policy. Điều này không nhất thiết nghĩa propagation bị lỗi; có thể chỉ là sampling decision.

Với async pipeline kéo dài, tail sampling cần thời gian chờ đủ để nhận các span đến muộn. Nếu trace kéo dài hàng giờ, collector/backend có thể đã đóng trace trước khi retry span xuất hiện. Hãy chọn retry trace strategy và retention phù hợp.

### Phân biệt missing span với missing context

| Dấu hiệu | Nguyên nhân có thể |
|---|---|
| Consumer span có trace ID mới | Header không có, không extract được hoặc context bị reset |
| Consumer span có cùng trace ID nhưng không có parent | Instrumentation tạo root span hoặc span link |
| Producer span xuất hiện hai lần | Agent và manual instrumentation cùng tạo span |
| Trace không có consumer span | Sampling, consumer chưa chạy, export lỗi hoặc span không được tạo |
| Async span nằm ngoài trace | Context không được capture/wrap qua thread |
| Trace kéo dài bất thường | Span không được end hoặc async completion không đóng span |

Kiểm tra header trước, sau đó kiểm tra extracted context, span parent/link, sampling và exporter.

## 19. Baggage, privacy và trust boundary

Baggage có thể hữu ích để truyền metadata không nhạy cảm, nhưng nó được propagate qua nhiều service và có thể xuất hiện trong trace backend hoặc log.

Không đưa vào baggage:

- Password, API key, OAuth token hoặc session cookie.
- Email, số điện thoại, địa chỉ, mã định danh cá nhân.
- Dữ liệu thẻ, thông tin thanh toán hoặc payload nghiệp vụ.
- Giá trị do client không tin cậy cung cấp rồi dùng làm authorization decision.

Giới hạn số lượng key/value, chiều dài và số hop. Xóa baggage không còn cần thiết khi qua trust boundary. Không cho phép baggage điều khiển tenant authorization, routing bảo mật hoặc quyền truy cập.

Trace context cũng có thể bị producer giả mạo nếu producer có quyền ghi topic. Không dùng trace ID hoặc baggage để xác thực nguồn event. Dùng Kafka authentication/ACL, signature hoặc event provenance nếu cần xác minh nguồn.

## 20. Trace context và correlation ID nghiệp vụ

Trace ID phục vụ quan sát kỹ thuật; event ID/correlation ID phục vụ nghiệp vụ. Hai loại ID có thể liên kết nhưng không thay thế nhau.

| ID | Vòng đời | Mục đích |
|---|---|---|
| Trace ID | Một distributed trace | Gom các span kỹ thuật |
| Span ID | Một thao tác | Xác định span và quan hệ parent |
| Event ID | Một event nghiệp vụ | Deduplicate, audit và replay |
| Correlation ID | Một quy trình nghiệp vụ có thể kéo dài | Tìm các event liên quan |
| Aggregate ID | Một entity/aggregate | Keying, ordering và state transition |

Một nghiệp vụ có thể tạo nhiều trace qua nhiều ngày nhưng vẫn giữ correlation ID. Một trace có thể xử lý nhiều event nếu pipeline fan-in. Không dùng trace ID làm unique key của outbox hoặc idempotency store.

## 21. Kiểm thử propagation

Nên kiểm thử riêng carrier, context, async boundary và integration.

### Unit test inject/extract

~~~java
Headers headers = new RecordHeaders();

Span span = tracer.spanBuilder("test producer").startSpan();
try (Scope scope = span.makeCurrent()) {
    propagator.inject(
        Context.current(),
        headers,
        KafkaTraceHeaders.SETTER
    );
}

Context extracted = propagator.extract(
    Context.root(),
    headers,
    KafkaTraceHeaders.GETTER
);

SpanContext extractedSpan =
    Span.fromContext(extracted).getSpanContext();

assertTrue(extractedSpan.isValid());
assertEquals(span.getSpanContext().getTraceId(),
             extractedSpan.getTraceId());
span.end();
~~~

Test cần xác minh trace ID được giữ, parent span ID đúng và sampled flag được bảo toàn theo propagator.

### Test async

- Tạo span cha.
- Capture context và submit executor task.
- Tạo span con trong task.
- Xác minh parent span ID trỏ về span cha.
- Xác minh span được end khi task complete/error/cancel.
- Chạy nhiều task song song để phát hiện context leakage.

### Integration test với Kafka

1. Publish record từ một trace đã biết.
2. Consume record và xác minh headers có traceparent.
3. Extract context và tạo consumer span.
4. Publish sang topic thứ hai và xác minh context tiếp tục.
5. Thử retry/DLT và kiểm tra policy trace giữ cùng trace hay tạo trace mới có link.
6. Chạy qua Kafka Streams repartition và sink.
7. Chạy qua Kafka Connect/SMT nếu pipeline có Connect.
8. Kiểm tra trace backend hiển thị parent-child/link đúng.

Không chỉ kiểm tra log có trace ID. Cần xác minh parent/link và header thực tế trên record.

## 22. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Producer và consumer có trace ID khác nhau | Producer không inject hoặc consumer không extract | Kiểm tra traceparent trong record headers |
| Header traceparent bị lặp | Setter add mà không remove header cũ hoặc nhiều instrumentation cùng inject | Chọn một propagator/instrumentation và canonical header |
| Consumer span là root span | Context không hợp lệ hoặc code dùng setNoParent | Kiểm tra propagator, getter và parent selection |
| Span async không có parent | Context không được capture qua executor/reactive scheduler | Dùng Context.wrap hoặc instrumentation tương thích |
| Trace có span trùng | Java agent và manual instrumentation cùng tạo transport span | Tắt một lớp instrumentation hoặc chỉ giữ business span thủ công |
| Trace không có baggage | Propagator không bật baggage hoặc integration loại header | Cấu hình composite propagator và kiểm tra header |
| Kafka Streams mất trace | Repartition/processor/output không giữ headers | Kiểm thử headers qua từng topology node và xử lý tường minh |
| Connect/Debezium mất context | Source không lưu context hoặc SMT không copy headers | Lưu metadata ở outbox và kiểm tra transform chain |
| Retry xuất hiện thành trace mới | Chính sách retry tạo root trace hoặc link | Quyết định rõ tiếp tục trace hay tạo trace mới có link |
| Trace thiếu span dù header đúng | Sampling hoặc exporter/backend drop | Kiểm tra trace flags, sampler, collector và export errors |
| Span duration quá dài | Span không kết thúc sau async completion | Đóng span trong completion/error/cancel path |
| Trace backend có dữ liệu nhạy cảm | Baggage/attributes chứa dữ liệu không được phép | Lọc baggage, attributes và áp dụng retention/access policy |

## 23. Checklist triển khai

- Chọn W3C Trace Context làm propagation format xuyên service.
- Cấu hình OpenTelemetry propagator cho tracecontext và baggage nếu cần.
- Inject trace context vào Kafka headers trước khi publish.
- Extract context từ headers trước khi tạo consumer/process span.
- Giữ business key và event ID độc lập với trace ID.
- Tránh duplicate traceparent/tracestate headers.
- Dùng Context.wrap khi chuyển công việc qua executor/thread.
- Kết thúc span khi async work thực sự hoàn tất.
- Dùng span links cho batch/fan-in nhiều parent contexts.
- Quy định trace policy cho retry, delayed retry và DLT.
- Kiểm tra headers qua Kafka Streams, Connect và SMT.
- Chọn agent, Micrometer Observation hoặc manual instrumentation có chủ đích.
- Tránh tạo span trùng giữa automatic và manual instrumentation.
- Cấu hình sampling và tail-sampling phù hợp với thời gian async.
- Không đưa secret/PII hoặc quyền authorization vào baggage.
- Theo dõi missing context, duplicate spans, export errors và span duration.
- Kiểm thử propagation qua producer, broker, consumer, executor và retry pipeline.

## 24. Những nhầm lẫn thường gặp

- **Kafka tự nối trace:** Kafka lưu headers; producer/consumer instrumentation phải inject và extract context.
- **Trace ID là Kafka key:** key quyết định partitioning; trace ID là metadata quan sát.
- **Có traceparent nghĩa là authentication thành công:** trace context không xác minh nguồn gửi.
- **Baggage là nơi lưu token hoặc quyền:** baggage không phải credential hay authorization policy.
- **Consumer phải dùng cùng span với producer:** mỗi process tạo span riêng và nối bằng context.
- **Thread pool tự kế thừa context:** cần context propagation qua executor/reactive boundary.
- **Một batch có một parent phù hợp:** batch từ nhiều trace nên dùng span links hoặc span riêng cho từng record.
- **Retry luôn phải giữ trace mở:** retry dài có thể tạo trace mới và link về trace cũ.
- **Agent và manual spans luôn bổ sung cho nhau:** có thể tạo duplicate producer/consumer spans.
- **Header được giữ nguyên qua mọi connector/SMT:** phải kiểm thử từng integration và transformation.
- **Trace ID thay thế event ID:** trace ID phục vụ debug; event ID phục vụ idempotency và audit.
- **Không thấy span là propagation chắc chắn lỗi:** sampling/exporter cũng có thể làm span không xuất hiện.

Truyền trace context qua Kafka headers giúp nối hành trình bất đồng bộ giữa producer, consumer và downstream service. W3C traceparent/tracestate mang quan hệ trace; baggage chỉ nên chứa metadata không nhạy cảm. OpenTelemetry inject/extract context ở ranh giới message, còn Context.wrap giữ context qua thread và span links mô tả fan-in nhiều nguồn. Để trace đáng tin cậy, cần thống nhất instrumentation, giữ headers qua retry/Streams/Connect, kết thúc span đúng lifecycle và tách trace ID khỏi event ID nghiệp vụ.

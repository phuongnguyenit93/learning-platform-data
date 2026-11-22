# Trace context qua Kafka headers

Trong hệ thống Spring Kafka, một request có thể đi qua nhiều service trước khi hoàn tất: API nhận yêu cầu, service đơn hàng publish event, consumer thanh toán xử lý, service kho cập nhật tồn và một service khác gửi thông báo. Khi một bước chậm hoặc thất bại, chỉ xem log của từng service thường không đủ để biết toàn bộ luồng đã đi qua đâu.

Distributed tracing giải quyết vấn đề đó bằng cách gắn các span vào cùng một trace. Khi message được gửi qua Kafka, trace context cần đi cùng record để consumer có thể tiếp tục trace từ producer. Kafka hỗ trợ việc này thông qua record headers. Header không nằm trong payload JSON và broker lưu chúng cùng record, vì vậy producer và consumer có thể trao đổi metadata tracing mà không phải sửa event contract.

Trong Spring Kafka, Micrometer Observation và Micrometer Tracing có thể tự động inject/extract trace context khi bật observation cho KafkaTemplate và listener container. Bài học tập trung vào cấu trúc trace context, cách truyền qua Kafka headers, cấu hình Spring Boot, kiểm tra header, xử lý retry/DLT, baggage, luồng bất đồng bộ và cách kiểm thử propagation.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích trace, span, traceId, spanId và parent span.
- Mô tả vai trò của Kafka record headers trong distributed tracing.
- Phân biệt trace context với correlation ID và event ID.
- Nhận biết các header W3C như traceparent, tracestate và baggage.
- Cấu hình Micrometer Tracing với Spring Boot.
- Bật observation cho KafkaTemplate và listener container.
- Giải thích cách sender inject và receiver extract trace context.
- Kiểm tra trace headers trong ConsumerRecord.
- Giữ trace context khi forward record qua retry topic và DLT.
- Truyền context đúng khi xử lý trên thread khác.
- Giới hạn baggage và tránh đưa dữ liệu nhạy cảm vào header.
- Kiểm thử trace continuity giữa producer và consumer.

## 1. Trace context là gì?

Trace context là metadata cho phép nhiều service liên kết các thao tác thành một luồng phân tán. Một trace thường gồm nhiều span. Mỗi span đại diện cho một thao tác có thời gian bắt đầu, kết thúc, tên và các thuộc tính.

Ví dụ một luồng xử lý đơn hàng:

~~~text
Trace: 4bf92f3577b34da6a3ce929d0e0e4736

API request
  spanId: 00f067aa0ba902b7
      |
      v
Kafka producer send
  spanId: 11f067aa0ba902b7
  parent: 00f067aa0ba902b7
      |
      v
Kafka consumer process
  spanId: 22f067aa0ba902b7
  parent: 11f067aa0ba902b7
      |
      +--> Database query
      |
      +--> Kafka producer send payment event
                |
                v
          Payment consumer
~~~

Các khái niệm:

| Thành phần | Ý nghĩa |
|---|---|
| Trace | Toàn bộ hành trình của một yêu cầu hoặc một luồng xử lý |
| Span | Một thao tác có thời gian bắt đầu và kết thúc |
| traceId | ID chung để nhận diện trace |
| spanId | ID của một span cụ thể |
| parentSpanId | Span cha đã tạo ra thao tác hiện tại |
| Trace context | Metadata cần thiết để tạo quan hệ giữa các span |
| Baggage | Dữ liệu ngữ cảnh bổ sung được truyền cùng trace theo cấu hình |

Các span trong cùng trace có chung traceId nhưng spanId khác nhau. Khi một service nhận message và tiếp tục xử lý, nó tạo span mới có quan hệ với context nhận được. Nhờ vậy, công cụ tracing có thể hiển thị producer, consumer và các dependency theo một hành trình thống nhất.

Trace context không phải business state. Nó không cho biết đơn hàng đã thanh toán hay chưa, cũng không thay thế eventId hoặc requestId.

## 2. Vì sao Kafka cần truyền trace context qua headers?

Kafka là hệ thống messaging bất đồng bộ. Producer gửi record rồi có thể kết thúc request HTTP ban đầu trước khi consumer xử lý record. Consumer có thể chạy ở process, máy chủ hoặc thời điểm khác.

Nếu không truyền context, consumer thường tạo một trace mới hoàn toàn. Khi đó, dashboard tracing không thể liên kết thao tác publish với thao tác consume.

Kafka record có ba phần quan trọng:

~~~text
ProducerRecord
  key
  value
  headers
      |
      v
Kafka broker
      |
      v
ConsumerRecord
  key
  value
  headers
~~~

Trace context được đặt trong headers. Payload vẫn là event nghiệp vụ, ví dụ OrderCreated. Header chứa metadata như traceparent, tracestate hoặc baggage.

Broker không cần hiểu ý nghĩa của traceparent. Nó lưu và chuyển tiếp headers cùng record. Producer và consumer instrumentation chịu trách nhiệm inject và extract context.

Lợi ích:

- Theo dõi được thời gian publish và consume.
- Xác định service nào tạo ra message gây lỗi.
- Nhìn thấy consumer lag và thời gian xử lý trong cùng trace.
- Nối log của nhiều service qua traceId/spanId.
- Phân tích retry, DLT và các bước downstream.
- Tìm ra điểm nghẽn khi một event đi qua nhiều consumer.

Nếu producer và consumer dùng các tracing framework khác nhau, chúng cần thống nhất propagation format. Một bên gửi W3C Trace Context nhưng bên kia chỉ đọc B3 thì trace có thể bị đứt dù header vẫn tồn tại.

## 3. Các header W3C thường gặp

W3C Trace Context định nghĩa các trường chuẩn để truyền trace context.

| Header | Nội dung | Vai trò |
|---|---|---|
| traceparent | version, trace-id, parent-id và trace-flags | Context cốt lõi để nối trace |
| tracestate | Thông tin trạng thái riêng của vendor | Giữ metadata dành cho tracing implementation |
| baggage | Các cặp key/value tùy chọn | Truyền thông tin ngữ cảnh qua ranh giới service |

Một traceparent version 00 có dạng:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Cấu trúc:

~~~text
version-trace-id-parent-id-trace-flags
  00     32 hex     16 hex       2 hex
~~~

Trong ví dụ:

- 00 là version của định dạng header.
- 4bf92f3577b34da6a3ce929d0e0e4736 là trace ID.
- 00f067aa0ba902b7 là span ID của thao tác cha.
- 01 là flags, trong đó bit sampled được bật.

Không tự tạo traceparent bằng UUID hoặc tự nối chuỗi. Tracing library phải tạo ID, kiểm tra tính hợp lệ và inject đúng format. Giá trị traceparent sai định dạng có thể bị receiver bỏ qua.

### tracestate

tracestate mang thông tin bổ sung theo vendor. Ứng dụng thường không cần tự sửa header này. Hãy để propagator quản lý để tránh làm mất hoặc ghi đè metadata mà tracing backend cần.

### baggage

Baggage truyền các cặp key/value như:

~~~text
baggage: tenant=tenant-42,region=ap-southeast-1
~~~

Baggage có thể hữu ích khi cần giữ một số thuộc tính ngữ cảnh xuyên suốt các service. Tuy nhiên, mọi baggage đều có thể được truyền qua nhiều hệ thống và lưu trong Kafka headers. Chỉ cho phép các trường cần thiết, không truyền token, mật khẩu, email, số điện thoại hoặc dữ liệu cá nhân không cần thiết.

## 4. Trace context khác correlation ID và event ID

Ba loại ID này có mục đích khác nhau và không nên dùng thay thế cho nhau.

| Định danh | Mục đích | Vòng đời |
|---|---|---|
| traceId | Liên kết các span của một trace | Theo hành trình tracing |
| spanId | Nhận diện một thao tác | Theo từng span |
| correlationId | Liên kết các log hoặc message thuộc một business workflow | Theo quy ước nghiệp vụ |
| eventId | Nhận diện duy nhất một event | Theo event, giữ nguyên khi replay cùng event |
| requestId | Nhận diện một yêu cầu nghiệp vụ | Theo yêu cầu logic |

Một request có thể tạo nhiều event và mỗi event có eventId riêng. Các event đó có thể nằm trong cùng một trace hoặc được xử lý ở trace khác tùy cách hệ thống thiết kế luồng bất đồng bộ.

Correlation ID thường được dùng để tìm tất cả log liên quan đến một đơn hàng hoặc một workflow. Trace ID được tracing backend dùng để xây dựng quan hệ cha-con giữa span. Không dùng traceId làm khóa idempotency vì retry hoặc replay có thể có cách tạo trace khác nhau.

Nếu hệ thống đã có correlationId trong payload hoặc header nghiệp vụ, hãy giữ nó độc lập với traceparent. Hai giá trị có thể được ghi vào log cùng lúc để hỗ trợ cả truy vết kỹ thuật và điều tra nghiệp vụ.

## 5. Spring Kafka hỗ trợ Micrometer Observation từ phiên bản nào?

Spring Kafka hỗ trợ Micrometer Observation cho KafkaTemplate và listener containers từ phiên bản 3.0. Observation tạo điểm đo cho thao tác gửi và nhận message. Khi Micrometer Tracing được cấu hình, các observation có thể được chuyển thành span và propagator inject/extract trace context.

Hai thuộc tính quan trọng:

- KafkaTemplate.observationEnabled: bật observation cho thao tác gửi.
- ContainerProperties.observationEnabled: bật observation cho listener container.

Mặc định các thuộc tính này là false. Nếu chỉ bật ở producer mà không bật ở consumer, producer có thể tạo span và inject header, nhưng consumer container không tạo observation nhận tương ứng.

Khi bật observation, các Micrometer Timer truyền thống của template/container được quản lý thông qua observation. Không nên hiểu rằng bật tracing sẽ tự động có hiệu lực nếu thiếu ObservationRegistry hoặc tracing handler phù hợp.

Với batch listener, khả năng tạo observation và phạm vi observation thay đổi theo phiên bản Spring Kafka. Một số phiên bản cũ không tạo observation cho batch listener; các phiên bản mới có thể tạo observation cho cả batch hoặc từng record thông qua cấu hình `recordObservationsInBatch`. Hãy kiểm tra tài liệu của đúng version thay vì giả định record listener và batch listener có hành vi giống nhau.

### Dependency với Spring Boot

Với Spring Boot 3.x, một cấu hình phổ biến dùng Actuator, Micrometer Tracing bridge và exporter OTLP:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>

<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
~~~

Các dependency version cần được quản lý bằng Spring Boot dependency management/BOM. Với Spring Boot 4.x, starter OpenTelemetry có thể được cung cấp theo cách đóng gói mới; hãy theo tài liệu của đúng phiên bản Boot đang dùng thay vì trộn các version độc lập.

Có thể dùng OpenTelemetry hoặc Brave làm tracer implementation. Các service trong cùng hệ thống phải tương thích về propagation format, chẳng hạn cùng dùng W3C Trace Context hoặc cấu hình nhiều propagator theo chính sách chung.

## 6. Bật observation trong Spring Boot

Spring Boot cung cấp các thuộc tính cấu hình observation cho Kafka template và listener.

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
      probability: 1.0
~~~

Trong ví dụ, sampling probability bằng 1.0 để quan sát toàn bộ trace khi phát triển và kiểm thử. Production thường cần điều chỉnh sampling để cân bằng chi phí, lưu lượng và nhu cầu điều tra.

Giá trị mặc định của Spring Kafka observation là false. Chỉ đặt sampling probability không đủ nếu KafkaTemplate hoặc listener observation chưa được bật.

Nếu dùng Spring Boot auto-configuration, các thuộc tính trên được áp dụng cho template và listener container mặc định. Nếu tự tạo KafkaTemplate hoặc container factory riêng, hãy xác nhận chúng cũng nhận cấu hình observation.

### Cấu hình bằng Java

Có thể bật trực tiếp trong cấu hình:

~~~java
@Bean
public KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory) {

    KafkaTemplate<String, OrderEvent> template =
            new KafkaTemplate<>(producerFactory);

    template.setObservationEnabled(true);

    return template;
}
~~~

Bật observation trên listener factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setObservationEnabled(true);

    return factory;
}
~~~

Nếu đã dùng Spring Boot auto-configured template/factory, không cần tạo bean mới chỉ để bật observation. Cấu hình qua application.yml thường dễ quản lý hơn.

## 7. Luồng inject và extract trace context

Khi tracing-capable ObservationRegistry được cấu hình, luồng gửi/nhận thường diễn ra như sau:

~~~mermaid
sequenceDiagram
    participant A as API / Application
    participant P as KafkaTemplate
    participant K as Kafka Broker
    participant C as Listener Container
    participant S as Consumer Service

    A->>P: Gửi OrderCreated
    P->>P: Tạo producer observation/span
    P->>P: Propagator inject trace context
    P->>K: Record + traceparent/tracestate/baggage
    K->>C: ConsumerRecord + headers
    C->>C: Propagator extract trace context
    C->>C: Tạo consumer observation/span
    C->>S: Gọi @KafkaListener
    S->>S: Xử lý nghiệp vụ
~~~

### Phía producer

1. Application đang có một trace hoặc span hiện hành.
2. KafkaTemplate bắt đầu observation cho thao tác gửi.
3. Tracing handler tạo span gửi message.
4. Propagator inject context vào Kafka record headers.
5. Producer gửi record đến broker.

### Phía consumer

1. Listener container poll record và nhận headers.
2. Observation của consumer trích xuất context từ headers.
3. Tracing handler tạo span xử lý có quan hệ với context nhận được.
4. Span được đặt vào scope trong lúc listener xử lý.
5. Log và các thao tác được instrument trong scope có thể dùng traceId/spanId hiện hành.

Nếu listener tiếp tục gửi Kafka message khác, producer observation có thể tạo span con trong cùng trace và inject context mới vào record tiếp theo.

Việc tự động propagation phụ thuộc ObservationRegistry có tracing handler và propagator thực sự. Nếu chỉ có Micrometer metrics mà không có tracing bridge, ứng dụng vẫn có thể tạo timer nhưng không tạo distributed trace.

## 8. Kiểm tra trace headers trong ConsumerRecord

Có thể đọc header để xác minh producer đã gửi trace context:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service"
)
public void consume(ConsumerRecord<String, OrderEvent> record) {
    Header traceParentHeader =
            record.headers().lastHeader("traceparent");

    if (traceParentHeader != null) {
        String traceParent = new String(
                traceParentHeader.value(),
                StandardCharsets.UTF_8
        );

        log.debug(
                "Received Kafka record with traceparent={}, topic={}, partition={}, offset={}",
                traceParent,
                record.topic(),
                record.partition(),
                record.offset()
        );
    }

    billingService.process(record.value());
}
~~~

Đoạn code này chỉ phục vụ quan sát/debug. Không parse traceparent để tự tạo span khi Spring Kafka observation đã làm việc đó. Đọc header không đồng nghĩa ứng dụng đã extract context vào tracer.

Nếu header không tồn tại, kiểm tra:

- KafkaTemplate observation có được bật không?
- ObservationRegistry có tracing handler không?
- Producer có đang gửi qua template đã cấu hình không?
- Có custom ProducerInterceptor hoặc serializer nào thay đổi record không?
- Có thành phần trung gian nào tạo record mới nhưng không copy headers không?
- Producer và consumer có thống nhất propagation format không?

Không log toàn bộ headers trong production nếu có baggage hoặc metadata nhạy cảm.

## 9. Trace context qua nhiều service

Một ví dụ thực tế:

~~~text
order-api
   |
   | Kafka: orders.created
   | traceparent = T1 / producer-span
   v
billing-service
   |
   | Kafka: payments.requested
   | traceparent = T1 / billing-producer-span
   v
payment-service
   |
   | HTTP call to payment gateway
   | trace context propagated
   v
payment-gateway
~~~

Khi các service đều bật tracing và sử dụng propagator tương thích, tracing backend có thể hiển thị một trace nối từ API đến Kafka producer, consumer và downstream HTTP call.

Kafka không tự tạo trace mới ở broker. Span gửi và nhận được tạo ở phía ứng dụng. Broker chỉ lưu record và headers.

Nếu một service không hỗ trợ propagation, trace có thể bị chia thành nhiều phần. Service đó vẫn có thể ghi log và metrics riêng, nhưng không tạo được quan hệ span cha-con xuyên qua ranh giới của nó.

## 10. Trace context qua retry topic và dead-letter topic

Retry và DLT là những đường đi khác của cùng record. Nếu forwarding component giữ lại Kafka headers, trace metadata có thể tiếp tục đi cùng record qua các topic này.

Ví dụ:

~~~text
orders
  |
  | xử lý lỗi
  v
orders-retry-1000
  |
  | xử lý lỗi lần nữa
  v
orders-retry-5000
  |
  | hết retry
  v
orders-dlt
~~~

Khi thiết kế tracing cho retry/DLT, cần chú ý:

- Không xóa traceparent/tracestate khi tạo record retry.
- Không tạo header traceparent thủ công bằng ID ngẫu nhiên.
- Nếu custom recoverer tạo ProducerRecord mới, phải xác định rõ cách copy headers.
- Kiểm tra retry publisher và DLT publisher có observation được bật hay không.
- Ghi retry attempt và exception type bằng header/metadata nghiệp vụ riêng.
- Không dùng retry count làm span ID hoặc trace ID.
- Xác minh trace backend thể hiện từng attempt theo cách mong muốn.

Một record có thể đi qua nhiều lần xử lý. Mỗi lần retry có thể có một span xử lý mới; quan hệ của span phụ thuộc cách framework tạo observation và cách record được forward. Hãy xem trace thực tế thay vì giả định mọi retry đều là cùng một span hoặc đều là trace mới.

### Header gốc và header forwarding

DeadLetterPublishingRecoverer và retry-topic infrastructure có cơ chế giữ metadata của record khi forward. Tuy nhiên, custom recoverer, converter hoặc code tạo ProducerRecord mới có thể làm mất headers nếu chỉ copy key/value.

Khi tự forward record, cần giữ các header cần thiết:

- traceparent và tracestate.
- baggage đã được allowlist.
- eventId và correlationId.
- metadata nguồn như topic/partition/offset nếu quy trình cần audit.
- retry attempt hoặc DLT exception metadata.

Không sao chép một cách mù quáng mọi header từ nguồn không đáng tin cậy. Hãy lọc các header được phép, tránh header trùng tên không có semantics rõ và giới hạn kích thước tổng.

## 11. Baggage qua Kafka headers

Baggage hữu ích khi cần truyền một vài thuộc tính ngữ cảnh xuyên service, ví dụ tenant code hoặc region. Baggage không thay thế payload nghiệp vụ.

Với Micrometer Tracing, có thể tạo baggage trong scope:

~~~java
@Service
public class OrderProcessingService {

    private final Tracer tracer;

    public OrderProcessingService(Tracer tracer) {
        this.tracer = tracer;
    }

    public void processForTenant(String tenantCode) {
        try (BaggageInScope baggage =
                     tracer.createBaggageInScope("tenant", tenantCode)) {

            orderService.process();
        }
    }
}
~~~

Baggage được propagate tự động hay không phụ thuộc BaggageManager và propagation configuration. Với W3C, baggage có thể được truyền trong header baggage. Với B3, baggage không mặc nhiên tự động được propagate nếu chưa cấu hình trường remote tương ứng.

Tạo baggage trong scope cần có span hiện hành để baggage gắn với trace đó. Nếu gọi createBaggageInScope khi không có span hiện hành, không nên giả định giá trị sẽ tự được propagate sang message kế tiếp.

Chỉ cấu hình allowlist các baggage field cần thiết. Không dùng baggage để mang payload lớn, dữ liệu cá nhân, secret hoặc thông tin xác thực. Baggage đi qua nhiều service và có thể xuất hiện trong Kafka headers, log hoặc tracing backend.

Không thêm tenant ID hoặc user ID làm metric label có cardinality cao. Nếu cần tìm trace theo tenant, hãy cân nhắc thuộc tính span hoặc log có kiểm soát, đồng thời tuân thủ chính sách dữ liệu.

## 12. Trace context qua thread và async processing

Micrometer Tracing thường giữ span hiện hành trong thread-local scope. Spring Kafka listener container quản lý observation scope trong lúc gọi listener. Khi listener xử lý đồng bộ trên thread đó, log và các thao tác được instrument có thể thấy context hiện hành.

Context không tự động được bảo đảm khi ứng dụng chuyển sang thread khác bằng executor tùy chỉnh, CompletableFuture hoặc callback không được instrument.

Ví dụ rủi ro:

~~~java
@KafkaListener(topics = "orders")
public void consume(OrderEvent event) {
    CompletableFuture.runAsync(() -> {
        orderService.process(event);
    });
}
~~~

Listener trả về ngay sau khi submit task. Thread pool có thể không mang trace context từ listener sang worker thread. Kết quả là span nghiệp vụ có thể không thuộc trace gốc hoặc log không có traceId mong muốn.

Các cách xử lý:

- Dùng Micrometer Context Propagation và TaskDecorator cho executor.
- Capture/restore context khi submit công việc bất đồng bộ.
- Tạo span mới có parent rõ ràng từ context đã capture.
- Nếu cần bảo đảm offset chỉ được commit sau khi xử lý async xong, thiết kế acknowledgement và lifecycle riêng; trace propagation không giải quyết offset semantics.

Không giữ một SpanInScope mở ở thread này rồi đóng ở thread khác. Scope phải được đóng trên thread đã mở nó. Hãy dùng API context propagation thay vì tự truyền ThreadLocal.

## 13. Tạo span nghiệp vụ bên trong listener

Spring Kafka tạo observation cho thao tác listener khi bật cấu hình. Nếu cần quan sát một bước nghiệp vụ dài bên trong listener, có thể tạo thêm span con bằng Micrometer Tracer.

~~~java
@Component
public class OrderListener {

    private final Tracer tracer;
    private final OrderService orderService;

    public OrderListener(Tracer tracer, OrderService orderService) {
        this.tracer = tracer;
        this.orderService = orderService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-service"
    )
    public void consume(OrderEvent event) {
        Span span = tracer.nextSpan()
                .name("order.validate-and-save")
                .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            span.tag("order.type", event.type());
            orderService.process(event);
        }
        catch (RuntimeException ex) {
            span.error(ex);
            throw ex;
        }
        finally {
            span.end();
        }
    }
}
~~~

Span con giúp phân biệt thời gian validate, lưu database hoặc gọi dependency với tổng thời gian listener. Không tạo span cho mọi dòng code nhỏ; chỉ tạo span ở ranh giới nghiệp vụ hoặc dependency cần điều tra.

Nếu exception được ném lại, Spring Kafka error handler vẫn có thể xử lý retry/DLT. Việc span được đánh dấu lỗi không thay đổi cơ chế retry hay offset commit.

## 14. Propagation thủ công với Micrometer Propagator

Khi gửi message bằng Kafka client không đi qua KafkaTemplate observation hoặc khi tích hợp một transport tùy chỉnh, có thể dùng Micrometer Propagator để inject/extract context.

Không tự tạo chuỗi traceparent. Propagator của tracer sẽ tạo header theo propagation format đã cấu hình.

Ví dụ setter/getter cho Kafka Headers:

~~~java
private static final Propagator.Setter<Headers> KAFKA_SETTER =
        (headers, key, value) -> {
            headers.remove(key);
            headers.add(
                    key,
                    value.getBytes(StandardCharsets.UTF_8)
            );
        };

private static final Propagator.Getter<Headers> KAFKA_GETTER =
        (headers, key) -> {
            Header header = headers.lastHeader(key);

            return header == null
                    ? null
                    : new String(
                            header.value(),
                            StandardCharsets.UTF_8
                    );
        };
~~~

Phía producer, inject context của span hiện hành:

~~~java
Span currentSpan = tracer.currentSpan();

ProducerRecord<String, OrderEvent> record =
        new ProducerRecord<>(
                "orders.created",
                orderId,
                event
        );

if (currentSpan != null) {
    propagator.inject(
            currentSpan.context(),
            record.headers(),
            KAFKA_SETTER
    );
}

kafkaProducer.send(record);
~~~

Phía consumer, extract context và đặt span vào scope:

~~~java
Span span = propagator.extract(
                record.headers(),
                KAFKA_GETTER
        )
        .name("orders.consume")
        .start();

try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
    orderService.process(record.value());
}
catch (RuntimeException ex) {
    span.error(ex);
    throw ex;
}
finally {
    span.end();
}
~~~

Ví dụ này là đường tích hợp thủ công. Nếu KafkaTemplate và listener container đã bật observation với tracing handler, không thêm đoạn inject/extract thủ công song song vì có thể tạo header trùng hoặc span lồng không mong muốn.

Trong code production, hãy xử lý trường hợp không có context, header sai định dạng và lỗi deserialization. Getter ở ví dụ dùng lastHeader() để đọc giá trị cuối cùng; nếu hệ thống cho phép header trùng tên, hãy định nghĩa rõ cách chọn và kiểm tra record đầu vào.

## 15. Trace context và sampling

Sampling quyết định trace nào được ghi nhận hoặc export đến backend. Nó không phải cơ chế bảo đảm message được gửi hoặc consumer được chạy.

Spring Boot mặc định có thể chỉ sample một phần request để giảm chi phí. Khi trace bị sample out, hệ thống vẫn có thể tiếp tục xử lý nghiệp vụ bình thường. Việc có hoặc không có span trong backend không chứng minh record đã mất.

Ví dụ cấu hình trong môi trường phát triển:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Giá trị 1.0 sample toàn bộ trace. Production nên chọn tỷ lệ theo traffic, chi phí backend và mức độ quan trọng của luồng. Có thể tăng sampling tạm thời khi điều tra sự cố, nếu chính sách vận hành cho phép.

Không cố tăng sampling lên 100% mãi trong hệ thống có lưu lượng lớn mà không đánh giá chi phí lưu trữ, exporter queue, network và giới hạn span.

## 16. Quan sát trace trong log

Spring Boot với Micrometer Tracing có thể đưa traceId và spanId vào MDC để log correlation. Nhờ đó, log của producer và consumer có thể được tìm theo trace.

Ví dụ format:

~~~yaml
logging:
  pattern:
    correlation: "[%X{traceId:-},%X{spanId:-}] "
~~~

Log minh họa:

~~~text
[4bf92f3577b34da6a3ce929d0e0e4736,00f067aa0ba902b7]
Publishing OrderCreated eventId=e-100

[4bf92f3577b34da6a3ce929d0e0e4736,22f067aa0ba902b7]
Received OrderCreated eventId=e-100
~~~

Cùng traceId giúp tìm hai log trong cùng hành trình, còn spanId khác nhau xác định thao tác cụ thể.

Không cần tự thêm traceId vào mọi log message nếu MDC đã được cấu hình. Nếu dùng async executor, hãy xác nhận MDC/context được propagate và restore đúng để tránh log của task trước bị rò sang task sau.

## 17. Trace context không thay thế metrics

Tracing giúp điều tra một request hoặc một message cụ thể. Metrics giúp theo dõi xu hướng và cảnh báo ở quy mô toàn hệ thống.

Nên dùng metrics cho:

- KafkaTemplate send latency.
- Listener processing latency.
- Consumer lag.
- Số record thành công/thất bại.
- Retry và DLT rate.
- Số consumer rebalance.
- Số record bị lỗi deserialization.

Dùng trace cho:

- Tại sao một event cụ thể xử lý lâu.
- Service nào gọi dependency chậm.
- Một event đã đi qua những listener nào.
- Lỗi bắt đầu từ thao tác nào.
- Retry attempt nào gây ra lỗi.

Không dùng traceId, spanId, eventId hoặc orderId làm metric label có cardinality cao. Những ID này phù hợp cho trace/log, còn metric nên dùng tag có tập giá trị giới hạn như listener name, result hoặc exception class.

Khi observationEnabled bật, Spring Kafka tạo observation cho KafkaTemplate và listener. Micrometer có thể dùng observation để tạo cả timer metric và span; các metric có low-cardinality tag phù hợp để tổng hợp.

## 18. Bảo mật và giới hạn headers

Kafka headers là metadata gắn với record và có thể được lưu theo retention của topic. Nhiều consumer, retry topic và DLT có thể tiếp tục giữ headers.

Các nguyên tắc:

- Không đưa access token, password hoặc secret vào baggage.
- Không đưa dữ liệu cá nhân vào baggage nếu không có lý do và quyền xử lý rõ ràng.
- Giới hạn số lượng và kích thước baggage field.
- Chỉ propagate các field đã được allowlist.
- Không tin traceparent từ nguồn bên ngoài để quyết định quyền truy cập.
- Không dùng trace context làm bằng chứng xác thực hoặc authorization.
- Kiểm soát log để không in toàn bộ headers nhạy cảm.
- Khi forward record, tránh tích lũy nhiều bản header cùng tên.

Trace context là dữ liệu quan sát, không phải security token. Kẻ gửi message có thể tạo hoặc sửa header nếu họ có quyền ghi topic. Service không được dựa vào traceId hoặc baggage để xác định người dùng có quyền thực hiện nghiệp vụ.

## 19. Các lỗi thường gặp

**Chỉ bật observation ở producer.** Producer inject trace context nhưng consumer không tạo observation nhận. Bật observation cho cả KafkaTemplate và listener container.

**Chỉ cấu hình sampling probability.** Sampling không tự bật Kafka observation. Kiểm tra hai thuộc tính observation-enabled.

**Không có tracing bridge.** Timer vẫn có thể xuất hiện nhưng không có span/propagation. Cài và cấu hình Micrometer Tracing implementation phù hợp.

**Producer và consumer dùng propagation format khác nhau.** Header có thể tồn tại nhưng consumer không extract được. Thống nhất W3C hoặc B3.

**Tự tạo traceparent bằng UUID.** Header không hợp lệ và phá vỡ trace. Để propagator tạo ID.

**Dùng correlationId làm traceId.** Một business workflow và một trace có vòng đời khác nhau. Giữ riêng hai định danh.

**Custom recoverer tạo record mới mà không copy headers.** Trace context bị mất qua retry hoặc DLT. Copy có chọn lọc các header cần thiết.

**Baggage chứa dữ liệu nhạy cảm.** Metadata bị phát tán qua nhiều service và lưu trong Kafka. Dùng allowlist và data minimization.

**Async task không giữ context.** Log và span bị đứt sau khi chuyển thread. Dùng Micrometer Context Propagation hoặc tạo span với parent rõ ràng.

**Tạo span thủ công khi auto observation đã hoạt động.** Có thể tạo duplicate spans hoặc inject header trùng. Chọn một cơ chế propagation cho mỗi ranh giới.

**Dùng traceId làm idempotency key.** Retry hoặc replay có thể không cùng trace. Dùng eventId/requestId ổn định cho idempotency.

**Dùng traceId làm metric label.** Cardinality tăng không giới hạn. Giữ ID trong trace và log.

**Cho rằng không có trace nghĩa là message không được xử lý.** Sampling có thể loại trace khỏi backend. Kiểm tra offset, listener log và metrics riêng.

## 20. Kiểm thử trace context qua Kafka headers

Kiểm thử cần chứng minh trace context thực sự đi từ producer đến consumer, không chỉ chứng minh observation bean đã được tạo.

Các kịch bản nên có:

1. Producer gửi record khi đang có span: record có traceparent hợp lệ.
2. Consumer nhận record: span listener có cùng traceId với context producer.
3. Consumer gửi tiếp event: producer span mới có quan hệ với listener span.
4. Producer gửi khi không có span: hành vi phù hợp với chính sách root trace của ứng dụng.
5. Consumer nhận record thiếu traceparent: listener vẫn xử lý bình thường và tracing không làm hỏng nghiệp vụ.
6. Consumer nhận traceparent sai định dạng: propagator xử lý an toàn.
7. Record đi qua retry topic: headers cần thiết vẫn tồn tại.
8. Record đi vào DLT: trace metadata được giữ theo chính sách.
9. Custom recoverer tạo record mới: header propagation không bị mất.
10. Baggage allowlist: chỉ các trường được phép được truyền.
11. Async executor: span context được capture/restore đúng.
12. Sampling thấp: nghiệp vụ vẫn xử lý dù trace không xuất hiện trong backend.
13. Hai event song song: traceId và spanId không bị dùng nhầm giữa các thread.
14. Header trùng tên: ứng dụng có quy tắc đọc và xử lý rõ.

Với Spring Kafka Test hoặc Testcontainers, có thể gửi ProducerRecord có trace context và nhận ConsumerRecord để kiểm tra headers. Dùng TestObservationRegistry hoặc test tracer để kiểm tra observation/span trong môi trường test. Không chỉ assert log text vì log format có thể thay đổi độc lập với propagation.

## 21. Checklist cấu hình trace context

- [ ] Đã chọn một propagation format chung cho các service.
- [ ] Có Micrometer Tracing bridge và exporter phù hợp.
- [ ] ObservationRegistry có tracing handlers.
- [ ] KafkaTemplate observation được bật.
- [ ] Listener container observation được bật.
- [ ] Producer và consumer dùng cùng W3C/B3 configuration.
- [ ] Trace context được truyền qua Kafka record headers.
- [ ] Không tự tạo traceparent bằng chuỗi hoặc UUID.
- [ ] Correlation ID và event ID vẫn độc lập với trace ID.
- [ ] Retry/DLT forwarding giữ các headers cần thiết.
- [ ] Baggage chỉ chứa field được allowlist.
- [ ] Async executor có context propagation phù hợp.
- [ ] Sampling được điều chỉnh theo môi trường.
- [ ] TraceId/spanId nằm trong log, không dùng làm metric label.
- [ ] Có kiểm thử producer-to-consumer trace continuity.
- [ ] Có kiểm thử header thiếu, sai định dạng và duplicate.
- [ ] Có quy tắc không log baggage hoặc metadata nhạy cảm.

## Kết luận

Trace context đi qua Kafka bằng record headers, cho phép producer và consumer nối các span thành một trace phân tán. Trong Spring Kafka, hãy cấu hình Micrometer Tracing và bật observation ở cả KafkaTemplate lẫn listener container để propagator tự inject/extract context. Giữ traceId, correlationId và eventId đúng vai trò; bảo toàn headers khi forward qua retry/DLT; dùng context propagation khi chuyển thread; và giới hạn baggage để tránh phát tán dữ liệu nhạy cảm. Tracing giúp điều tra đường đi và latency của message, còn offset, retry, idempotency và delivery guarantee vẫn phải được quản lý bằng cơ chế messaging tương ứng.

## Tài liệu tham khảo

- [Spring Kafka – Monitoring and Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Kafka – Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Tracing – Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html)
- [Micrometer Tracing – Using Micrometer Tracing Directly](https://docs.micrometer.io/tracing/reference/api.html)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [W3C Baggage](https://www.w3.org/TR/baggage/)


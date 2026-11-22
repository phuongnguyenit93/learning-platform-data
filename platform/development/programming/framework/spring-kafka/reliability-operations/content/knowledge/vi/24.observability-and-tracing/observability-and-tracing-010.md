# Trace khi publish DLT trong Spring Kafka

Trong một hệ thống Spring Kafka có độ tin cậy cao, việc gửi record lỗi tới **Dead Letter Topic (DLT)** không nên là một thao tác không có dấu vết. Khi một message thất bại ở listener, trải qua retry rồi được DeadLetterPublishingRecoverer chuyển sang DLT, người vận hành cần biết **record xuất phát từ đâu, lỗi nào dẫn đến recovery, lúc nào DLT publish được thử, thao tác gửi thành công hay thất bại, và trace nào liên quan đến lần xử lý ấy**.

Chương **Observation và tracing** đặt câu hỏi sâu hơn việc có log một exception: **làm sao thấy được đường đi của record qua consumer, xử lý nghiệp vụ, error handler, Kafka producer và DLT consumer trong hệ thống tracing phân tán?**

Spring Kafka hỗ trợ **Micrometer Observation** cho các thao tác Kafka listener và KafkaTemplate ở những phiên bản hiện đại. Khi được cấu hình với ObservationRegistry, Micrometer Tracing và một exporter phù hợp, instrumentation có thể tạo spans và truyền trace context qua Kafka headers. Tuy vậy, **DLT recovery không tự động bảo đảm mọi span thuộc cùng một trace cha-con**: error handler có thể chạy sau khi scope của listener observation kết thúc; publish là bất đồng bộ; DLT record có thể giữ headers của message nguồn hoặc nhận propagation headers mới. Các điểm này phải được xác minh trong phiên bản và cấu hình thật.

Mục tiêu của bài học là xây được một đường quan sát đáng tin: phân biệt record metadata với trace context, bật instrumentation đúng nơi, bổ sung observation cho chính bước recovery, xử lý publish failure và có phương án đối chiếu khi trace bị chia nhánh hoặc không được sampled.

## 1. Trace khi publish DLT nghĩa là gì?

Một trace mô tả các bước liên quan tới một hoạt động phân tán. Mỗi **span** biểu diễn một khoảng xử lý, có thời điểm bắt đầu, kết thúc, trạng thái và một số attributes. Trong Kafka, các spans có thể được tạo quanh việc publish và consume record.

Một đường đi lý tưởng:

~~~text
HTTP POST /orders
      |
      v
HTTP server span
      |
      v
Kafka producer span: orders.events
      |
      v
Kafka listener span: orders.events
      |
      +--> business process / database span
      |
      +--> Exception: invalid order
      |
      v
DLT recovery observation
      |
      v
Kafka producer span: orders.events.DLT
      |
      v
Kafka listener span: orders.events.DLT
      |
      v
Quarantine / investigation
~~~

Sơ đồ thể hiện quan hệ mong muốn, **không cam kết mọi span mặc định nằm cùng một cây**. Quan hệ thực tế phụ thuộc việc trace context được truyền trong Kafka record, scope của observation tại thời điểm recoverer chạy, sampling và phiên bản instrumentation.

Khi trace hữu ích, operator có thể trả lời:

- Producer hoặc upstream request nào tạo ra event?
- Consumer group và listener nào gặp lỗi?
- Lỗi đầu tiên xảy ra ở khâu deserialize, validation hay database?
- Record đã retry bao nhiêu lần, trong những khoảng thời gian nào?
- DeadLetterPublishingRecoverer chọn topic/partition đích nào?
- Lệnh send DLT có được broker xác nhận không?
- DLT consumer đã đọc và xử lý record sau đó chưa?
- Có trace bị tách do retry hoặc replay hay không?

Trace bổ sung cho log, metrics và record metadata; nó không thay thế offset, DLT retention hoặc quy trình replay.

## 2. Phân biệt Kafka message, Observation, span và trace headers

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Kafka ConsumerRecord | Dữ liệu, key, headers, topic, partition, offset | Record ở orders.events, partition 2, offset 105 |
| Spring Kafka listener container | Poll, gọi listener, quản lý commit/retry | ordersListener |
| DefaultErrorHandler | Quyết định retry hoặc recovery sau lỗi | 2 retries rồi recover |
| DeadLetterPublishingRecoverer | Tạo ProducerRecord cho DLT và gửi bằng KafkaTemplate | orders.events.DLT |
| ObservationRegistry | Quản lý Observation hiện tại và handlers | Observation context |
| Micrometer Tracing | Liên kết Observation với trace/span context | traceId, spanId |
| Propagation headers | Mang trace context qua ranh giới Kafka | traceparent, tracestate hoặc định dạng được cấu hình |
| DLT metadata headers | Lưu thông tin nguồn và nguyên nhân lỗi | original topic/partition/offset |
| Telemetry exporter | Gửi spans tới backend quan sát | OpenTelemetry collector/Tempo/Jaeger |

Hai nhóm headers thường cùng nằm trên một DLT record nhưng có ý nghĩa khác nhau:

1. **Tracing headers** trả lời câu hỏi record được liên kết với trace nào.
2. **DLT origin/error headers** trả lời record nguồn nào lỗi, ở đâu và vì lý do gì.

Một record có traceparent không có nghĩa recoverer đã ghi đủ DLT original offset. Ngược lại, DLT có original topic/offset không chứng minh trace context đã được truyền đúng.

## 3. Đường đi khi record thất bại và được recovery

Ví dụ topic nguồn:

~~~text
orders.events, partition=1

offset 500: OrderCreated hợp lệ
offset 501: OrderCreated có lỗi validation
offset 502: OrderCreated hợp lệ
~~~

Một listener:

~~~java
@Component
public class OrderListener {

    private final OrderService service;

    public OrderListener(OrderService service) {
        this.service = service;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "order-service"
    )
    public void handle(OrderCreated event) {
        service.validateAndApply(event);
    }
}
~~~

Khi offset 501 gây exception, luồng khái quát:

~~~text
Poll source record 501
       |
       v
Listener invocation
       |
       +--> validateAndApply throws
       |
       v
DefaultErrorHandler
       |
       +--> Retry/backoff nếu retryable
       |
       +--> Hết attempts hoặc non-retryable
       |
       v
DeadLetterPublishingRecoverer
       |
       +--> Chọn DLT destination
       +--> Tạo record mới
       +--> Copy/thêm headers phù hợp
       |
       v
KafkaTemplate.send(DLT)
       |
       +--> Send success
       |        |
       |        v
       |    Recovery được xem xét hoàn tất
       |
       +--> Send error
                |
                v
           Không được coi là recovery thành công
~~~

Trace cần quan sát được **tối thiểu** listener failure và DLT produce attempt. Một observation riêng quanh recovery có thể bổ sung destination, outcome và latency của bước xử lý này.

Không xem thao tác gọi send trả về một future là bằng chứng broker đã nhận record. Việc recoverer chờ kết quả hoặc báo lỗi send phụ thuộc cấu hình và semantics của DeadLetterPublishingRecoverer trong phiên bản Spring Kafka đang sử dụng.

## 4. Điều kiện để tracing hoạt động

Một ứng dụng thường cần:

- Spring Kafka version có Observation instrumentation cho listener và KafkaTemplate.
- Micrometer Observation và ObservationRegistry.
- Micrometer Tracing bridge tương thích.
- Exporter/SDK để gửi trace tới backend.
- Sampling policy.
- Propagator phù hợp với định dạng headers mà các services cùng hiểu.
- KafkaTemplate và listener container bật observation đúng vị trí.
- Backend/query UI để xem traceId và spans.

Trong Spring Boot 3.x, phần dependency thường gồm Spring Kafka, Actuator và tracing bridge. Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
~~~

Để export spans, còn cần exporter/collector configuration tương ứng với Micrometer Tracing và OpenTelemetry SDK/bridge của Spring Boot version đang dùng. Không giả định thêm tracing bridge là đủ để spans xuất hiện ở backend nếu exporter chưa được cấu hình.

Các dependency và cấu hình cụ thể phải tương thích với **BOM của Spring Boot**. Không pha các version Micrometer, Spring Kafka và OpenTelemetry tùy tiện vì có thể dẫn tới tracing không hoạt động hoặc class incompatibility.

## 5. Bật Observation trên listener container

Trong cấu hình Java, có thể bật Observation cho container factory:

~~~java
@Configuration
public class KafkaListenerObservationConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    observedOrderListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);

        factory.getContainerProperties()
                .setObservationEnabled(true);

        return factory;
    }
}
~~~

Listener gắn đúng factory:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "order-service",
        containerFactory = "observedOrderListenerFactory"
)
public void onOrder(OrderCreated event) {
    orderService.validateAndApply(event);
}
~~~

Observation được bật trên **factory thực tế tạo container**. Nếu ứng dụng có nhiều container factories, bật trên một factory không tự kích hoạt cho các listener đang dùng factory khác.

Với consumer transaction, batch listener hoặc các đường lỗi đặc biệt, event/span boundaries có thể khác. Hãy kiểm tra instrumentation trong Spring Kafka version của ứng dụng chứ không mặc định mỗi record đều tạo một span hoàn hảo bất kể cách xử lý.

## 6. Bật Observation trên KafkaTemplate dùng để publish DLT

KafkaTemplate dùng để gửi DLT cũng cần instrumentation:

~~~java
@Configuration
public class DltProducerObservationConfiguration {

    @Bean
    KafkaTemplate<String, byte[]> dltKafkaTemplate(
            ProducerFactory<String, byte[]> dltProducerFactory) {

        KafkaTemplate<String, byte[]> template =
                new KafkaTemplate<>(dltProducerFactory);

        template.setObservationEnabled(true);

        return template;
    }
}
~~~

Ví dụ template dùng byte[] để minh họa DLT lưu raw bytes. Trong thực tế, record lỗi có thể mang một domain object đã deserialize được hoặc raw byte[] từ ErrorHandlingDeserializer. ProducerFactory và serializers phải được cấu hình phù hợp với kiểu key/value thực tế của DLT.

Điểm quan trọng:

- **Listener observation:** đo consumer xử lý record.
- **KafkaTemplate observation:** đo thao tác producer gửi record tới topic, trong trường hợp này là DLT.
- **Recovery observation tùy chọn:** đo logic của error handler/recoverer khi quyết định gửi record lỗi.

Chỉ bật listener observation chưa chắc đã tạo span producer DLT. Ngược lại, producer span không tự cho biết nguyên nhân listener ném exception nếu không có liên kết context/metadata phù hợp.

## 7. DeadLetterPublishingRecoverer và producer span

Một cấu hình record error handler phổ biến:

~~~java
@Configuration
public class KafkaErrorHandlingConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        dltKafkaTemplate,
                        (record, exception) -> new TopicPartition(
                                record.topic() + ".DLT",
                                -1
                        )
                );

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(1_000L, 2L)
                );

        handler.addNotRetryableExceptions(
                InvalidOrderException.class
        );

        return handler;
    }
}
~~~

Ví dụ này giả định dltKafkaTemplate đã được cấu hình đúng serializers và được bật Observation. Destination resolver trả partition -1 để Kafka producer chọn partition, thay vì ép cùng partition nguồn; điều này hữu ích nếu DLT có số partition khác source.

Với retryable error, handler thử lại theo BackOff. Khi lỗi non-retryable hoặc đã hết retries, recoverer tạo ProducerRecord mới và gọi KafkaTemplate để gửi DLT.

Nếu template được instrumentation bằng Micrometer Observation, một **producer observation/span** có thể được tạo cho thao tác gửi DLT. Nhưng **quan hệ cha-con của span này** cần được xem xét ở thời điểm error handler gọi recoverer.

Không nên mô tả một trace thống nhất là mặc định được bảo đảm trong mọi path. Producer span có thể trở thành root hoặc liên kết với một context khác nếu listener observation đã kết thúc hoặc tracing scope không được kích hoạt khi recovery chạy.

## 8. Vì sao trace có thể bị tách ở ranh giới error handler?

Observation thường có một **scope hiện tại** gắn với execution context của thread. KafkaTemplate tạo producer observation có thể lấy parent từ scope đang active. Nhưng error handler xử lý exception có thể diễn ra **ngoài** phạm vi scope của listener observation.

~~~text
Kafka listener observation
        |
        +--> Listener gọi business service
        |
        +--> Exception
        |
        v
Listener observation scope close
        |
        v
DefaultErrorHandler
        |
        +--> DeadLetterPublishingRecoverer
                    |
                    v
               KafkaTemplate.send(DLT)
                    |
                    +--> Không nhất thiết còn
                         listener span làm parent
~~~

Đây là một **khả năng cần xác minh**, không phải khẳng định trình tự implementation chính xác cho mọi phiên bản. Thời điểm kết thúc observation và cách recoverer được gọi tùy Spring Kafka instrumentation và đường xử lý lỗi.

Vấn đề thực tế: DLT producer span có thể tồn tại ở trace khác với listener failure span, dù cùng một record nghiệp vụ. Nếu operator chỉ mở trace gốc mà không thấy DLT producer, cần kiểm tra scope, propagation và record metadata thay vì kết luận recoverer chưa chạy.

Các hướng giải quyết:

1. Bật observation đúng cho listener và KafkaTemplate.
2. Dùng observation riêng quanh recovery với context hợp lệ.
3. Giữ correlation ID và Kafka source metadata trong log.
4. Nếu cần liên kết across async boundaries, dùng context propagation được hỗ trợ.
5. Xem traceparent/tracestate của record DLT thực tế.
6. Không buộc một trace cha-con sai chỉ để dashboard trông liền mạch.

## 9. Bao recovery bằng một Observation riêng

Có thể bọc recoverer trong một observation có tên rõ ràng, ví dụ app.kafka.dlt.recovery. Observation này giúp đo duration và gắn các key-values hữu hạn.

~~~java
@Configuration
public class DltRecoveryTracingConfiguration {

    @Bean
    DefaultErrorHandler observedDltErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate,
            ObservationRegistry observationRegistry) {

        DeadLetterPublishingRecoverer delegate =
                new DeadLetterPublishingRecoverer(
                        dltKafkaTemplate,
                        (record, error) -> new TopicPartition(
                                record.topic() + ".DLT",
                                -1
                        )
                );

        BiConsumer<ConsumerRecord<?, ?>, Exception> observedRecoverer =
                (record, error) -> {

                    Observation observation =
                            Observation.createNotStarted(
                                    "app.kafka.dlt.recovery",
                                    observationRegistry
                            );

                    observation.lowCardinalityKeyValue(
                            "source_topic_group",
                            topicGroup(record.topic())
                    );
                    observation.lowCardinalityKeyValue(
                            "error_category",
                            classifyError(error)
                    );

                    observation.observe(() ->
                            delegate.accept(record, error)
                    );
                };

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        observedRecoverer,
                        new FixedBackOff(1_000L, 2L)
                );

        return handler;
    }

    private static String topicGroup(String topic) {
        return topic.startsWith("orders.") ? "orders" : "other";
    }

    private static String classifyError(Exception error) {
        return error instanceof InvalidOrderException
                ? "validation"
                : "other";
    }
}
~~~

Ý nghĩa:

- DeadLetterPublishingRecoverer vẫn thực hiện việc gửi DLT.
- Observation có tên riêng cho bước recovery.
- Các low-cardinality key-values giúp lọc metrics/traces theo nhóm.
- Khi observation có tracing handler, bước này có thể tạo span tương ứng.
- Scope của observation được mở trong khoảng delegate.accept được gọi.
- KafkaTemplate instrumented được gọi trong khoảng đó có thể lấy recovery observation làm parent, tùy thiết lập ObservationRegistry/tracing integration.

**Giới hạn:** Nếu delegate.accept trả về trước khi broker xác nhận send hoàn tất, duration của recovery observation chỉ phản ánh thời gian thực thi lời gọi recoverer, không mặc định phản ánh broker acknowledgement. Việc error/success cuối cùng phải được quan sát ở KafkaTemplate send result hoặc cấu hình recoverer phù hợp.

Vì vậy, một recovery span không tự chứng minh DLT record đã được ghi bền vững.

## 10. Parent span, trace link và correlation ID

Trong tracing phân tán, không phải mọi quan hệ đều nên cưỡng ép thành parent-child.

- **Parent-child:** bước xử lý mới được khởi tạo trong active trace context của bước cha.
- **Trace link:** span mới có thể liên kết tới context của một message trước đó, phù hợp với async/retry workflow mà không nhất thiết là cùng lời gọi đồng bộ.
- **Correlation ID:** một định danh nghiệp vụ ổn định dùng để đối chiếu records/logs/traces.
- **Original Kafka coordinates:** topic, partition, offset của nguồn record, giúp truy ra chính xác vị trí record trong log.

Ví dụ:

~~~text
Trace T1: Source producer -> Source consumer -> failure

Trace T2: DLT recovery -> DLT producer -> DLT consumer

Correlation:
  event_id = evt-100
  original_topic = orders.events
  original_partition = 1
  original_offset = 501
~~~

Nếu T1 và T2 không cùng trace ID, vẫn có thể tìm ra mối liên hệ qua event ID, DLT original metadata và logs. Nếu tracing implementation hỗ trợ span links, có thể biểu diễn quan hệ context đó một cách chính xác hơn.

**Không sửa traceparent bằng tay chỉ để ép DLT producer thành con của một span đã kết thúc** nếu không có thiết kế propagation rõ ràng. Có thể làm sai causal relationship hoặc tạo hai nguồn context mâu thuẫn.

## 11. Trace headers được mang qua Kafka như thế nào?

Distributed tracing thường dùng propagation để đưa trace context vào carrier của message, ví dụ Kafka headers.

Một Kafka record có thể có:

~~~text
topic = orders.events
partition = 1
offset = 501

headers:
  traceparent = 00-<trace-id>-<span-id>-01
  tracestate = ...
  event-id = evt-100
~~~

Giá trị minh họa theo kiểu W3C Trace Context. Tên headers thực tế tùy propagator được cấu hình và stack tracing.

Khi producer Observation active, instrumentation có thể inject context vào Kafka record headers. Khi consumer Observation active, instrumentation có thể extract context đó để tạo observation/span phù hợp.

DLT record có thể giữ một số headers gốc từ source record, đồng thời recoverer bổ sung DLT metadata. Khi KafkaTemplate publish DLT trong một active Observation, tracing instrumentation có thể thêm hoặc cập nhật propagation headers trên ProducerRecord.

Vì vậy, cần kiểm tra **headers trên record DLT sau khi publish**, không chỉ headers của source record hoặc đoạn code copy headers. Đặc biệt, một tracing header trong DLT có thể biểu diễn context ban đầu hoặc context của một produce operation mới tùy cấu hình và đường gửi.

Không khẳng định có một traceparent cụ thể nếu chưa kiểm tra format propagator đang dùng và kết quả thực tế.

## 12. DLT origin headers khác trace headers

DeadLetterPublishingRecoverer thường đưa vào DLT record các metadata giúp điều tra record gốc, như:

- Original topic.
- Original partition.
- Original offset.
- Original timestamp và timestamp type, tùy khả năng/version.
- Consumer group hoặc exception metadata khi framework hỗ trợ.
- Exception class/message/stacktrace headers, theo cấu hình và phiên bản.

Spring Kafka có các hằng số header liên quan tới DLT trong KafkaHeaders, ví dụ các hằng DLT_ORIGINAL_TOPIC, DLT_ORIGINAL_PARTITION và DLT_ORIGINAL_OFFSET.

Một DLT record minh họa:

~~~text
DLT record:
  destination topic: orders.events.DLT
  destination partition: 0
  destination offset: 112

DLT origin metadata:
  original_topic: orders.events
  original_partition: 1
  original_offset: 501

Trace propagation:
  traceparent: ...
  tracestate: ...
~~~

Destination offset 112 là **offset của record mới trong DLT**, không phải offset của source record. Operator cần cả hai để đối chiếu.

Không tự đọc DLT_ORIGINAL_OFFSET như chuỗi UTF-8 nếu header được Kafka framework mã hóa bằng dạng số/bytes riêng. Dùng helper/API phù hợp của Spring Kafka hoặc decoder có kiểm soát theo hợp đồng header.

## 13. Có nên giữ nguyên trace headers nguồn khi gửi DLT?

Không có một đáp án áp dụng cho mọi trường hợp. Có ba nhu cầu khác nhau:

1. **Giữ correlation với hành trình ban đầu.**
2. **Biểu diễn thao tác DLT publish như một bước mới.**
3. **Không làm lẫn lộn trace context gốc với context hiện tại.**

Nếu copy toàn bộ headers gốc, traceparent gốc có thể tiếp tục tồn tại. Nếu KafkaTemplate instrumentation inject context mới, tracing headers có thể được cập nhật theo propagator. Nếu không có context active ở recoverer, DLT consumer có thể extract context gốc thay vì một DLT producer span mới.

Điều cần làm:

- Quy định tracing propagation format xuyên suốt producer/consumer.
- Quan sát output headers thực tế sau publish.
- Không ghi nhiều giá trị trùng tên tracing header theo cách khiến consumer chọn không nhất quán.
- Dùng event-id và DLT origin metadata như correlation bổ sung.
- Nếu muốn giữ trace gốc để forensic, lưu một **original trace ID** riêng với chính sách privacy và retention phù hợp, không làm nó trở thành propagation header giả.
- Tránh lưu raw baggage có dữ liệu nhạy cảm nếu không cần thiết.

Một header truy vết riêng có thể đặt tên rõ như original-trace-id, nhưng đó là **contract do ứng dụng tạo**, không phải một header mặc định luôn có sẵn của Spring Kafka.

## 14. Propagation khi publish DLT là bất đồng bộ

KafkaTemplate.send thường trả về CompletableFuture trong Spring Kafka hiện đại:

~~~java
CompletableFuture<SendResult<String, OrderEvent>> future =
        kafkaTemplate.send(
                "orders.events",
                "order-100",
                event
        );
~~~

Việc gọi send và việc broker xác nhận kết quả có thể nằm ở thời điểm/threads khác nhau.

~~~text
Consumer thread
       |
       +--> DeadLetterPublishingRecoverer
                 |
                 +--> KafkaTemplate.send(DLT)
                          |
                          +--> tạo observation / producer span
                          |
                          +--> send future returned
                                   |
                                   v
                            Kafka producer I/O
                                   |
                            +------+------+
                            |             |
                            v             v
                        Success        Failure
~~~

Khi quan sát cần tách:

- **Recoverer invocation started**.
- **KafkaTemplate send invoked**.
- **Broker acknowledged publish**.
- **Future completed exceptionally**.
- **Source offset considered recovered**.

Một trace có span producer kết thúc thành công có thể được hiểu khác nhau tùy instrumentation cụ thể. Không đồng nhất việc kết thúc method send với broker đã ghi record.

Trong production, phải quyết định liệu recoverer chờ kết quả send, nhận lỗi trong một khoảng timeout hay chấp nhận xử lý async. Để bảo đảm source offset không bị coi là recovered khi DLT publish lỗi, cần cấu hình hành vi phù hợp và kiểm thử failure path.

## 15. Theo dõi DLT publish failure và không commit offset sớm

Một tình huống nguy hiểm:

~~~text
Source record E thất bại
        |
        v
Recoverer gửi DLT
        |
        v
Broker từ chối vì topic/ACL/serializer lỗi
        |
        v
Ứng dụng vẫn coi recovery thành công
        |
        v
Commit source offset
        |
        v
Record E không có ở DLT và không được đọc lại
~~~

Hành vi mong muốn là **không công nhận recovery thành công** nếu DLT publish chưa đạt mức xác nhận mà hệ thống yêu cầu.

Với DeadLetterPublishingRecoverer, Spring Kafka cung cấp những option liên quan tới kiểm tra kết quả gửi, ví dụ setFailIfSendResultIsError(true) trong các phiên bản hỗ trợ. Ví dụ:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltKafkaTemplate);

recoverer.setFailIfSendResultIsError(true);
~~~

Các lựa chọn chờ send result/timeout phụ thuộc version, producer config và use case. Cần xác định cụ thể **acknowledgment của producer**, retry của producer và contract recovery.

Trong tracing:

- Span của **recovery attempt** cần có outcome rõ.
- Failure cần ghi exception/error category.
- Log cần có topic/partition/offset nguồn và destination.
- Metric cần đếm DLT publish failures.
- Alert nếu recovery liên tục thất bại.
- Không chỉ dựa trên span, vì sampling có thể bỏ qua một lần lỗi.

## 16. Khi có transaction Kafka

Với transactional listener container, một exception có thể làm transaction Kafka hiện tại **abort**; sau đó AfterRollbackProcessor quyết định seek/retry/recovery. Luồng recovery không giống hệt non-transactional DefaultErrorHandler.

~~~text
Transactional listener
        |
        +--> Kafka output in transaction
        |
        +--> Exception
                |
                v
         Kafka transaction ABORT
                |
                v
        AfterRollbackProcessor
                |
                +--> Retry/seek
                |
                +--> Recovery/DLT khi hết attempts
                           |
                           v
                      DLT produce
~~~

Một DLT producer span xuất hiện không tự chứng minh DLT publish và source offset commit nằm cùng một transaction. Nếu muốn **transactional recovery** cho record đã thất bại, cần dùng các khả năng được Spring Kafka version hỗ trợ, như DefaultAfterRollbackProcessor cấu hình transactional KafkaTemplate và commitRecovered khi phù hợp.

Không tự commit source offset sau một produce span có vẻ thành công. Để thiết kế recovery an toàn, cần làm rõ transaction boundary, producer acknowledgments và behavior khi process crash giữa DLT publish với offset commit.

Tracing giúp nhìn thấy các bước; nó không bổ sung atomicity giữa các bước mà transaction chưa bảo vệ.

## 17. Retry có thể tạo nhiều spans cho cùng record

Một record có thể xử lý nhiều lần:

~~~text
Event E, source offset 501
    |
    +--> attempt 1: DB timeout
    |
    +--> attempt 2: DB timeout
    |
    +--> attempt 3: DB timeout
    |
    +--> DLT publish attempt
~~~

Tùy error handler, seek/redelivery và instrumentation, nhiều listener invocations có thể tạo nhiều observations/spans. Một **record Kafka** không đồng nghĩa một **span duy nhất**.

Cần phân biệt:

- **eventId:** logical event.
- **topic/partition/offset:** tọa độ Kafka.
- **delivery attempt:** lần xử lý.
- **traceId/spanId:** một context tracing cụ thể.
- **DLT publish attempt:** thao tác gửi record lỗi.
- **replay attempt:** một lần xử lý về sau, có thể ở trace khác.

Nếu lấy trace ID làm unique event ID, retry/replay có thể làm cùng event thành nhiều logical entities vì trace context không ổn định theo business workflow. Dùng eventId hoặc business operation ID độc lập với tracing.

## 18. Non-blocking retry và trace qua nhiều topic

Với retry topics, record có thể đi theo một chuỗi:

~~~text
orders.events
      |
      +--> failure
      |
      v
orders.events-retry-1000
      |
      +--> failure
      |
      v
orders.events-retry-5000
      |
      +--> failure
      |
      v
orders.events.DLT
~~~

Tên topics ở đây chỉ là ví dụ, không phải quy tắc đặt tên bắt buộc của mọi Spring Kafka version.

Mỗi bước publish/consume là một boundary mới:

- Producer tới retry topic.
- Consumer ở retry topic.
- Producer tới retry topic tiếp theo.
- Consumer ở retry topic tiếp theo.
- Producer tới DLT.
- DLT consumer.

Nếu tracing headers được propagate, các bước có thể liên kết nhau. Nhưng nếu sampling hoặc context propagation không thống nhất, trace có thể bị đứt. Một retry diễn ra sau nhiều phút còn có thể tạo những khoảng thời gian lớn giữa spans.

Không giả định non-blocking retry tương thích với mọi transactional listener configuration. Cần xác nhận giới hạn framework version và cách error handler/retry topics vận hành.

Một dashboard hữu ích nên vừa xem spans vừa có record eventId + original topic/offset để theo dõi workflow dài.

## 19. Poison pill trước @KafkaListener và thiếu listener span

Một record có thể lỗi ngay ở deserialization:

~~~text
KafkaConsumer.poll()
      |
      v
JsonDeserializer throws
      |
      v
Listener method chưa được gọi
      |
      v
Không nhất thiết có listener observation/span
      |
      v
Error handling hoặc consumer poll failure
~~~

Với ErrorHandlingDeserializer, Spring Kafka có thể lưu thông tin exception và raw bytes trong headers để container chuyển record tới error handler/recoverer.

Ví dụ consumer configuration:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.events.OrderCreated
        "[spring.json.trusted.packages]": com.example.events
~~~

Khi một poison pill bị chuyển DLT, **DLT producer span có thể tồn tại dù listener span không tồn tại**. Đó không nhất thiết là lỗi của tracing: record chưa đi vào method listener.

Hãy dùng DLT original metadata, error handler logs, deserialization exception headers và source coordinates để tìm nguyên nhân. Không chỉ đếm listener span failures rồi kết luận mọi lỗi dữ liệu đều được quan sát.

## 20. DLT serializer và raw bytes ảnh hưởng tới trace

Record lỗi deserialize value có thể được recoverer xuất sang DLT dưới dạng **raw byte[]**. Record lỗi nghiệp vụ sau deserialize có thể được gửi dưới dạng domain object.

~~~text
Source value JSON hợp lệ
      |
      v
OrderCreated object
      |
      +--> validation failure
      |
      v
DLT value có thể là OrderCreated


Source value JSON bị hỏng
      |
      v
ErrorHandlingDeserializer
      |
      +--> raw bytes + error metadata
      |
      v
DLT value có thể là byte[]
~~~

DLT ProducerFactory phải có serializers hỗ trợ các kiểu dữ liệu thực tế. Nếu serializer DLT lỗi trước khi send hoàn tất, có thể không có broker acknowledgement hoặc trace span thành công.

Một producer có tracing đúng nhưng serializer không thể serialize byte[] vẫn làm recovery thất bại. Tracing không thay thế kiểm tra ProducerFactory, ACL, topic, partition và message size limits.

Khi DLT dùng chung cho nhiều payload types, có thể cần serializer theo kiểu hoặc nhiều templates; phải bảo đảm truy vết dùng đúng KafkaTemplate đang gửi record DLT.

## 21. Low-cardinality và high-cardinality trong spans/metrics

Observation có thể có low-cardinality key-values để phân nhóm metrics, và high-cardinality attributes trong tracing theo conventions/tracing integration.

**Low-cardinality**, phù hợp với metrics:

~~~text
source_topic_group = orders | payments | other
error_category = validation | deserialization | database | other
recovery_action = dlt | retry | skip
destination_class = dlt | quarantine
~~~

**High-cardinality**, hữu ích khi điều tra một record nhưng không phù hợp làm metric tags:

~~~text
event_id = evt-100
original_partition = 1
original_offset = 501
trace_id = ...
message_key = order-100
~~~

Cần có chính sách riêng cho thông tin nhạy cảm. Không phải cứ là span attribute thì được phép ghi raw payload, customerId, payment token hoặc header chứa PII.

Không tạo một Micrometer Timer series cho mỗi offset hoặc eventId. Đối với logs/traces, cũng phải giới hạn kích thước và sampling/retention, đặc biệt khi exception stacktrace dài.

Ví dụ observation riêng cho recovery nên dùng category đã chuẩn hóa:

~~~java
Observation observation =
        Observation.createNotStarted(
                "app.kafka.dlt.recovery",
                observationRegistry
        )
        .lowCardinalityKeyValue(
                "error_category",
                "validation"
        )
        .lowCardinalityKeyValue(
                "source_topic_group",
                "orders"
        );
~~~

Nếu muốn ghi offset vào trace/log, dùng tracing attributes hoặc structured logging phù hợp mà không biến nó thành metric label không giới hạn.

## 22. Sampling và giới hạn khi tìm trace DLT

Trace sampling giúp giảm chi phí. Nhưng nó cũng có nghĩa một record lỗi có thể **không có trace hoàn chỉnh** trong backend.

Một tình huống:

~~~text
1,000,000 events
       |
       +--> Một tỷ lệ spans được sampled
       |
       +--> Một số record lỗi vào DLT
       |
       +--> DLT publish không có trace được lưu
~~~

Do đó:

- Không dựa vào tracing làm audit ledger duy nhất.
- Với recovery failures, logs và counters cần tồn tại độc lập.
- Có thể cân nhắc sampling policy ưu tiên lỗi, nếu tracing stack hỗ trợ.
- Không giả định span được export chỉ vì code gọi Observation API.
- Khi tail-based sampling, spans có thể xuất hiện trễ trong backend.
- Nếu trace gốc không sampled, DLT producer/consumer cũng có thể không xuất đầy đủ.
- Giữ eventId, original topic/partition/offset trong DLT metadata và structured logs.

Sampling là quyết định chi phí và mục tiêu quan sát; phải cân bằng với nhu cầu forensic cho các incident nghiêm trọng.

## 23. Structured logging để nối các đoạn trace

Nếu trace giữa consumer lỗi và DLT producer bị tách, structured logs giúp dựng lại quan hệ.

Ví dụ log ở recoverer:

~~~text
event=kafka_dlt_recovery
event_id=evt-100
source_topic=orders.events
source_partition=1
source_offset=501
destination_topic=orders.events.DLT
error_category=validation
recovery_phase=send_requested
trace_id=...
span_id=...
~~~

Sau broker confirmation:

~~~text
event=kafka_dlt_publish_result
event_id=evt-100
source_topic=orders.events
source_partition=1
source_offset=501
destination_topic=orders.events.DLT
result=success
destination_partition=0
destination_offset=112
trace_id=...
~~~

Hai log trên minh họa **hai giai đoạn khác nhau**. Không ghi result=success trước khi kết quả DLT publish được xác nhận theo contract ứng dụng.

Một mẫu thực tế nên có:

- eventId hoặc business operation ID đã được xác thực.
- Source topic/partition/offset.
- DLT topic/partition và offset nếu đã nhận metadata.
- Exception category, không log vô tội vạ toàn bộ raw payload.
- TraceId/spanId khi tracing context khả dụng.
- Producer send outcome và thời gian xử lý.
- Retry attempt nếu được framework truyền qua context đáng tin cậy.
- Consumer group và listener ID khi cần điều tra.

Nếu log MDC tự động thêm traceId/spanId, cần nhớ callback async có thể chạy trên thread khác. Đừng mặc định MDC từ consumer thread tự truyền sang producer callback thread mà không có context propagation.

## 24. Propagation qua callback và thread bất đồng bộ

Một failure mode phổ biến:

~~~text
Consumer thread: có trace context
       |
       +--> recoverer tạo async task
                |
                v
Worker thread: không có scope tương ứng
                |
                v
KafkaTemplate.send(DLT)
                |
                +--> producer span thành root mới
~~~

Nếu recovery được chuyển sang executor khác, context gắn với thread ban đầu có thể bị mất. Để truyền context qua async boundary, dùng cơ chế context propagation được hỗ trợ bởi Micrometer và runtime, không tự chia sẻ thread-local state hay KafkaConsumer.

Một số hướng:

1. Sử dụng context-propagating TaskExecutor/TaskDecorator phù hợp với Spring/Micrometer version.
2. Truyền immutable tracing context snapshot bằng API chính thức.
3. Khi tạo producer observation, xác định parent context hợp lệ.
4. Không giữ scope mở vô hạn để chờ async task.
5. Không gọi KafkaConsumer từ thread khác; KafkaConsumer không thread-safe.
6. Nếu không muốn truyền parent xuyên suốt, tạo một trace mới và liên kết qua eventId/original coordinates.

**Không tự copy một traceId string vào MDC rồi coi đó là context propagation đầy đủ.** Span context còn chứa trace flags, sampling state và các metadata khác; chỉ có traceId không bảo đảm quan hệ tracing hợp lệ.

## 25. Gắn error category vào trace mà không tăng metric cardinality

Một recoverer có thể gặp nhiều exception types: InvalidOrderException, SerializationException, TimeoutException hoặc các wrapper exceptions.

Không nên lấy toàn bộ exception.toString() làm tag, vì message có thể chứa Kafka key, payload hoặc request ID. Thay bằng bộ phân loại hữu hạn:

~~~java
private static String errorCategory(Throwable throwable) {

    Throwable current = throwable;

    while (current != null) {
        if (current instanceof InvalidOrderException) {
            return "validation";
        }

        if (current instanceof java.net.SocketTimeoutException) {
            return "network";
        }

        if (current instanceof org.apache.kafka.common.errors
                .SerializationException) {
            return "serialization";
        }

        current = current.getCause();
    }

    return "other";
}
~~~

Đây là ví dụ về classifier, cần điều chỉnh theo exception hierarchy thực tế. Đừng lặp vô hạn qua cause cycle bất thường; trong hệ thống production có thể thêm bảo vệ số bước tối đa hoặc tập identity đã gặp.

Error category dùng low-cardinality key-value giúp biểu đồ so sánh tỷ lệ lỗi. Stacktrace chi tiết chỉ nên đưa vào exception recording/logs có chính sách bảo mật phù hợp, không tạo một tag mới cho mỗi error message.

## 26. DLT consumer và quá trình replay

Record đã ở DLT có thể được một quarantine consumer hoặc công cụ replay xử lý:

~~~text
orders.events.DLT
      |
      v
DLT listener
      |
      +--> Log origin metadata
      +--> Đưa vào quarantine DB
      +--> Chờ operator decision
      |
      v
Replay tool
      |
      +--> Publish lại orders.events
      |
      v
Source consumer xử lý lại
~~~

Về tracing:

- DLT listener có thể tạo consumer span nếu bật observation.
- Replay publisher có thể tạo producer span mới.
- Replay xảy ra sau nhiều giờ hoặc nhiều ngày; không nhất thiết nên duy trì một cây parent-child kéo dài từ trace ban đầu.
- DLT original metadata và eventId ổn định giúp nối sự kiện qua thời gian.
- Nếu replay tạo trace mới, hãy ghi mối quan hệ với original event trong audit logs hoặc span links nếu stack hỗ trợ.
- Không biến DLT replay thành một vòng xử lý vô hạn do record vẫn lỗi.

Khi replay, cần giữ business idempotency key; không tạo ID mới cho một operation đã có side effect bên ngoài Kafka. TraceId không phải idempotency key.

DLT consumer nên ghi nhận **đã đọc**, **đã lưu quarantine** hay **đã replay thành công** như các trạng thái khác nhau, không chỉ log một span DLT consume rồi xem như incident đã khép lại.

## 27. Metrics cần đi cùng tracing DLT

Traces cho biết chi tiết một lần xử lý; metrics giúp phát hiện xu hướng và độ lớn của sự cố.

| Metric/tín hiệu | Mục đích |
|---|---|
| DLT publish attempts | Có bao nhiêu record được thử gửi DLT |
| DLT publish success/failure | Có bao nhiêu lần broker xác nhận hoặc từ chối |
| Recovery latency | Thời gian ở bước recoverer |
| Listener failure rate | Lỗi trước khi tới recovery |
| Retry attempt rate | Số lần retry trước DLT |
| Consumer lag theo partition | Record lỗi có đang giữ partition không |
| DLT topic ingress rate | Tốc độ record xuất hiện trong DLT |
| DLT oldest record age | Backlog điều tra có kéo dài không |
| DLT replay success/failure | Chất lượng vận hành recovery |
| Trace export errors/dropped spans | Telemetry pipeline có mất dữ liệu không |
| Sampling rate | Tỷ lệ traces có thể quan sát |
| Kafka producer send errors | Lỗi ở tầng producer/broker |
| Schema/deserialization errors | Lỗi có thể xảy ra trước listener span |

Không tạo label eventId, offset, orderId hoặc traceId cho metrics counters. Những giá trị đó thuộc log, trace hoặc forensic store.

Một dashboard có thể drill down từ **DLT failure rate tăng** sang traces được sampled và structured logs theo original topic/partition/offset.

## 28. Kiểm thử tracing bằng Kafka thật

Một unit test gọi trực tiếp DeadLetterPublishingRecoverer không chứng minh KafkaTemplate Observation, propagation headers và consumer spans hoạt động đúng trong listener container thực.

Với Testcontainers Kafka hoặc EmbeddedKafka, có thể xây kịch bản:

1. Publish một OrderCreated với eventId cố định.
2. Bật observation ở source listener container.
3. Cố ý ném InvalidOrderException.
4. Error handler recover record vào DLT.
5. DLT producer KafkaTemplate bật observation.
6. DLT consumer nhận record.
7. Thu thập spans trong một test Observation/Tracing setup phù hợp.
8. Đọc record DLT headers và metadata.
9. Xác nhận record source, DLT destination, outcome và trace/correlation behavior.

Bảng test nên bao gồm:

| Kịch bản | Điều cần xác minh |
|---|---|
| Listener thành công | Có listener observation theo cấu hình |
| Listener lỗi rồi retry thành công | Không publish DLT ngoài policy |
| Lỗi cố định, hết retry | Recoverer gửi DLT |
| DLT producer observation enabled | Có producer instrumentation tương ứng |
| DLT consumer observation enabled | Có consumer instrumentation tương ứng |
| Recovery observation riêng | Có span/metric recovery theo sampling và registry |
| Listener scope đóng trước recovery | Parent-child hoặc trace split được xác định rõ |
| Traceparent nguồn tồn tại | DLT record propagation semantics được kiểm chứng |
| Traceparent nguồn thiếu | Recovery vẫn có log/metadata, không crash |
| Deserializer lỗi trước listener | Không kỳ vọng listener span bắt buộc |
| DLT send bị ACL/topic failure | Recovery error được surface; không commit sai |
| DLT serializer lỗi | Không ghi nhận publish thành công giả |
| DLT raw bytes | Producer serializer hỗ trợ payload lỗi |
| Async recovery/executor | Context propagation không bị giả định |
| Sampling tắt | Metrics/logs vẫn chẩn đoán được |
| Transaction abort/recovery | Trace không bị hiểu nhầm là transaction commit |
| DLT replay nhiều giờ sau | EventId và origin metadata vẫn nối được lịch sử |

Kiểm tra cả trace export, DLT records, source offsets và broker acknowledgments. Một trace span xuất hiện không tự chứng minh DLT send đã thành công.

## 29. Cách chẩn đoán khi không thấy trace DLT

### Source consumer có span, DLT producer không có

Kiểm tra KafkaTemplate thực sự dùng bởi DeadLetterPublishingRecoverer có observationEnabled và ObservationRegistry/tracing bridge hợp lệ không. Template khác bean hoặc tự tạo ProducerFactory có thể bỏ qua cấu hình.

### DLT producer span có nhưng là trace mới

Kiểm tra scope tại thời điểm recoverer chạy. Error handler có thể nằm ngoài listener observation scope, hoặc recovery được dispatch sang thread khác. Dùng recovery observation, context propagation hoặc correlation qua origin metadata theo thiết kế.

### DLT consumer không cùng trace với producer

Kiểm tra headers được inject/extract, propagator format, duplicate tracing headers và sampling state. Không tự kết luận headers bị mất nếu trace không được sampled.

### Trace có DLT send nhưng record không ở broker

Có thể span phản ánh send attempt hoặc method call, còn broker send thất bại sau đó. Kiểm tra future/producer acknowledgments, recoverer send-result policy, ACL, topic, serializer và producer logs.

### DLT có record nhưng không có trace

Sampling có thể bỏ qua trace; instrumentation có thể chưa bật; lỗi có thể xảy ra trước listener; tracing exporter có thể bị outage. DLT origin metadata và logs vẫn phải đủ để điều tra.

### Trace hiển thị cùng record nhiều lần

Có thể do retry, redelivery, rebalance hoặc replay. Không dùng traceId làm unique event ID; đối chiếu eventId và original coordinates.

### DLT spans tăng quá nhiều sau outage

Kiểm tra error classification/backoff. Một database outage có thể khiến nhiều record hợp lệ bị đẩy DLT nếu retry policy không phù hợp. Tracing cho biết hiện tượng, không thay thế điều tiết retry hoặc pause/backpressure.

### Trace có dữ liệu nhạy cảm trong tags

Kiểm tra custom Observation conventions, baggage, Kafka headers và log correlation. Loại bỏ PII/secrets khỏi telemetry và áp retention/access control phù hợp.

### Không thấy duration của broker acknowledgement

Recovery Observation chỉ bao lời gọi recoverer, có thể không bao trùm async broker I/O. Dùng send result callbacks hoặc KafkaTemplate instrumentation phù hợp để quan sát kết quả producer ở tầng đúng.

## 30. Runbook điều tra một DLT incident

Giả sử dashboard báo tốc độ DLT tăng mạnh:

1. Xác định DLT topic, consumer group và thời điểm bắt đầu tăng.
2. Xem DLT publish success/failure metrics và Kafka broker/producer health.
3. Lấy một record DLT để xem origin topic, partition, offset và exception metadata.
4. Tra logs source listener theo original coordinates hoặc eventId.
5. Xem traceId/spans liên quan nếu tracing sampling có dữ liệu.
6. Xác định listener failure xảy ra trước hay sau deserialization.
7. Xác định retry policy và số attempts đã tiêu thụ.
8. Kiểm tra DLT producer template và serializer nhận kiểu payload tương ứng.
9. Nếu DLT send thất bại, xác nhận source offset không bị recovered/commit sai.
10. Nếu trace bị tách, đối chiếu eventId/origin headers và kiểm tra observation scope.
11. Nếu nhiều records cùng lỗi, phân loại data poison pill so với dependency outage.
12. Quyết định quarantine, sửa producer schema, phục hồi database hoặc replay theo quy trình.
13. Ghi audit cho quyết định replay và xác nhận idempotency.
14. Đối chiếu consumer lag, DLT backlog và trạng thái business sau khắc phục.

Không replay hàng loạt chỉ vì một trace đã chỉ ra lỗi. Phải biết record có thực hiện side effect ở database/payment trước khi thất bại hay không, vì Kafka rollback và DLT recovery không tự hoàn tác external systems.

## 31. Checklist triển khai tracing cho DLT

- Source Kafka listener container có observationEnabled khi cần.
- KafkaTemplate thực sự dùng cho DLT có observationEnabled.
- ObservationRegistry, tracing bridge, propagator và exporter được cấu hình tương thích.
- Đã biết scope của listener observation so với error handler/recoverer.
- Có recovery Observation riêng nếu cần đo/span bước recovery.
- Không giả định DLT producer span mặc định là con listener span trong mọi đường lỗi.
- Có correlation ID hoặc eventId ổn định độc lập với traceId.
- Có DLT origin topic/partition/offset và exception metadata để forensic.
- Trace propagation headers được kiểm tra trên record DLT thực tế.
- Tránh duplicate/conflicting tracing headers khi copy source headers và inject context mới.
- Không dùng traceparent string thay cho API context propagation chính thức.
- Async callbacks/executors có context propagation hoặc trace-link strategy rõ ràng.
- DLT send result được xác nhận theo recoverer policy, không coi send attempt là publish success.
- DLT serializer hỗ trợ domain object và raw bytes khi cần.
- Không commit source offset như recovered nếu DLT publish thất bại.
- Transactional listener dùng đúng AfterRollbackProcessor/recovery semantics.
- Retry topics, DLT và replay được theo dõi qua nhiều spans hoặc traces theo thiết kế.
- Lỗi deserialization trước listener có logs/metrics riêng.
- Low-cardinality metrics tags không chứa eventId/offset/traceId.
- High-cardinality trace attributes/logs tuân thủ privacy policy.
- Sampling không phải nguồn audit duy nhất.
- DLT metrics, producer errors, consumer lag và replay status đi cùng tracing.
- Đã thử source failure, DLT success/failure, async propagation và missing headers.
- Operator có runbook đối chiếu record DLT với trace và logs.

**Kết luận:** Trace khi publish DLT không chỉ là bật tracing trên consumer. Cần quan sát được **listener failure, error handler/recoverer, KafkaTemplate producer send và DLT consumer**, đồng thời giữ đầy đủ origin metadata để truy vết kể cả khi trace bị tách hoặc không được sampled. Micrometer Observation giúp tạo instrumentation, nhưng quan hệ span, propagation headers và broker acknowledgment phải được kiểm chứng ở đúng version và recovery path. Một hệ thống Spring Kafka đáng tin sẽ kết hợp **trace, structured logs, DLT headers, metrics và offset/recovery semantics**, thay vì coi sự xuất hiện của một span là bằng chứng record lỗi đã được lưu an toàn.


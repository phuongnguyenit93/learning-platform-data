# Theo dõi tốc độ gửi và nhận

Trong hệ thống Spring Kafka, throughput cho biết ứng dụng gửi hoặc xử lý được bao nhiêu record trong một đơn vị thời gian. Chỉ nhìn số message producer gửi đi là chưa đủ: cần so sánh tốc độ gửi, tốc độ broker xác nhận, tốc độ consumer đọc, tốc độ nghiệp vụ xử lý thành công và lượng record còn tồn đọng.

Một dashboard hữu ích trả lời được ba câu hỏi: producer đang đưa dữ liệu vào nhanh đến đâu, consumer đang xử lý nhanh đến đâu, và khoảng cách giữa hai tốc độ có đang làm consumer lag tăng hay không.

## 1. Phân biệt các loại throughput

Trong một luồng `orders`, nên theo dõi ít nhất các đại lượng sau:

| Đại lượng | Cách hiểu | Đo ở đâu |
| --- | --- | --- |
| Send attempt rate | Số lần ứng dụng gọi gửi record mỗi giây | Trước hoặc tại `KafkaTemplate.send()` |
| Send success rate | Số lần gửi được broker xác nhận mỗi giây theo cấu hình producer | Khi future gửi hoàn tất thành công |
| Consume rate | Số record consumer đọc từ Kafka mỗi giây | Kafka consumer client metrics |
| Processing success rate | Số record nghiệp vụ xử lý thành công mỗi giây | Trong listener/service |
| Processing failure rate | Số lần xử lý thất bại mỗi giây | Error handler hoặc listener |
| Byte throughput | Số byte gửi/nhận mỗi giây | Producer/consumer client metrics |
| Consumer lag | Số record consumer group đang chậm so với log end offset | Broker/exporter/monitoring |

Các con số này không nhất thiết bằng nhau. Producer có thể gửi thành công nhưng consumer xử lý chậm; consumer có thể đọc nhanh nhưng xử lý nghiệp vụ thất bại; retry cũng làm một record được giao nhiều lần. Khi báo cáo throughput nghiệp vụ, hãy đếm record hoàn tất thành công, không chỉ đếm số lần listener được gọi.

## 2. Bật Micrometer cho Spring Kafka

Spring Kafka tích hợp Micrometer để đo thời gian gửi qua `KafkaTemplate` và thời gian gọi listener container. Khi Micrometer có trên classpath và application context có một `MeterRegistry`, các timer được tạo tự động:

- `spring.kafka.template`: thời gian gửi record qua `KafkaTemplate`, tách kết quả thành công và thất bại.
- `spring.kafka.listener`: thời gian gọi listener, tách kết quả thành công và thất bại.

Các timer mặc định có tag như `name`, `result` và `exception`. Với concurrent listener container, timer được tạo theo từng consumer thread và tên container có hậu tố tương ứng. Có thể tắt timer bằng `micrometerEnabled` trên `KafkaTemplate` hoặc `ContainerProperties` nếu ứng dụng có lý do cụ thể.

Để xuất metric qua Spring Boot Actuator và Prometheus, thêm các dependency tương thích với phiên bản Spring Boot đang dùng, thường gồm Actuator và Prometheus registry:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

Mở endpoint cần thiết trong cấu hình ứng dụng:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
```

Không mở endpoint metrics ra Internet công khai. Đặt xác thực và giới hạn mạng truy cập theo chính sách vận hành.

## 3. Đếm record gửi thành công

`KafkaTemplate.send()` là thao tác bất đồng bộ. Nếu cần đo send success rate, hãy tăng counter khi future hoàn tất thành công, không tăng ngay khi phương thức `send()` vừa được gọi. Future hoàn tất theo cơ chế acknowledgement của producer và cấu hình `acks`.

Ví dụ dưới đây dùng API `CompletableFuture` của Spring Kafka 3.x trở lên:

```java
@Service
public class OrderPublisher {
    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;
    private final MeterRegistry registry;
    private final Counter sendAttempt;
    private final Counter sendSuccess;
    private final Counter sendFailure;
    private final Timer sendCompletion;

    public OrderPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate,
            MeterRegistry registry) {
        this.kafkaTemplate = kafkaTemplate;
        this.registry = registry;
        this.sendAttempt = Counter.builder("orders.kafka.send")
            .tag("result", "attempt").register(registry);
        this.sendSuccess = Counter.builder("orders.kafka.send")
            .tag("result", "success").register(registry);
        this.sendFailure = Counter.builder("orders.kafka.send")
            .tag("result", "failure").register(registry);
        this.sendCompletion = Timer.builder("orders.kafka.send.completion")
            .register(registry);
    }

    public void publish(OrderEvent event) {
        sendAttempt.increment();
        Timer.Sample sample = Timer.start(registry);
        try {
            kafkaTemplate.send("orders", event.orderId(), event)
                .whenComplete((result, exception) -> {
                    sample.stop(sendCompletion);
                    if (exception == null) {
                        sendSuccess.increment();
                    } else {
                        sendFailure.increment();
                    }
                });
        } catch (RuntimeException ex) {
            sample.stop(sendCompletion);
            sendFailure.increment();
            throw ex;
        }
    }
}
```

Đoạn code minh họa cách đo completion time và kết quả gửi. Trong Spring Kafka 2.x, kiểu trả về của `send()` là `ListenableFuture`; callback cần dùng API tương ứng của version đó. Không chặn thread bằng `get()` chỉ để cập nhật metric trong luồng production.

Timer `orders.kafka.send.completion` đo thời gian từ lúc gọi gửi đến khi future hoàn tất. Nó bao gồm thời gian chờ gửi và acknowledgement, không phải thời gian consumer xử lý record. Nếu cần đo thời gian nghiệp vụ đầu-cuối, phải bổ sung trace hoặc timestamp nghiệp vụ riêng.

## 4. Đo tốc độ xử lý trong listener

Đếm record ở nơi nghiệp vụ hoàn tất thành công. Nếu listener ném exception, tăng bộ đếm failure rồi ném tiếp để Spring Kafka error handler thực hiện retry hoặc recovery:

```java
@Component
public class OrderListener {
    private final OrderService orderService;
    private final MeterRegistry registry;
    private final Counter processed;
    private final Counter failed;
    private final Timer processingTime;

    public OrderListener(OrderService orderService, MeterRegistry registry) {
        this.orderService = orderService;
        this.registry = registry;
        this.processed = Counter.builder("orders.kafka.processed")
            .register(registry);
        this.failed = Counter.builder("orders.kafka.processing.failed")
            .register(registry);
        this.processingTime = Timer.builder("orders.kafka.processing")
            .publishPercentileHistogram()
            .register(registry);
    }

    @KafkaListener(topics = "orders", groupId = "order-projection")
    public void consume(OrderEvent event) {
        Timer.Sample sample = Timer.start(registry);
        try {
            orderService.apply(event);
            processed.increment();
        } catch (RuntimeException ex) {
            failed.increment();
            throw ex;
        } finally {
            sample.stop(processingTime);
        }
    }
}
```

Trong ví dụ, `processed` chỉ tăng khi `orderService.apply()` hoàn tất. `failed` đếm số lần listener thất bại, vì vậy cùng một event có thể làm counter này tăng nhiều lần nếu có retry. Nếu muốn đếm số event duy nhất thất bại cuối cùng, hãy đo riêng tại bước recoverer/DLT.

## 5. Đếm đúng khi dùng batch listener

Với batch listener, một lần gọi method có thể xử lý hàng chục hoặc hàng trăm record. Đếm mỗi lần method được gọi sẽ đo số batch mỗi giây, không phải số record mỗi giây.

```java
private final Counter processedRecords; // Khởi tạo bằng Counter.builder(...).register(registry)

@KafkaListener(
    topics = "orders",
    groupId = "order-batch-projection",
    containerFactory = "batchListenerFactory")
public void consume(List<OrderEvent> events) {
    orderService.applyBatch(events);
    processedRecords.increment(events.size());
}
```

Chỉ tăng counter sau khi batch được xử lý thành công theo semantics của ứng dụng. Nếu xử lý từng record trong batch và một record có thể thất bại riêng, hãy đếm kết quả từng record thay vì tăng toàn bộ batch một cách mù quáng. Có thể đo riêng `batch.size` bằng `DistributionSummary` để biết kích thước batch trung bình và phân bố.

Với Micrometer Observation, hành vi batch phụ thuộc phiên bản Spring Kafka. Theo tài liệu Spring Kafka 4.1, batch listener mặc định không tạo observation; có thể bật `recordObservationsInBatch` trên container factory để tạo observation theo từng record trong batch. Các dòng phiên bản cũ có khác biệt về hỗ trợ batch observation, vì vậy hãy kiểm tra tài liệu đúng version trước khi dựa vào metric này.

```java
factory.getContainerProperties().setRecordObservationsInBatch(true);
```

## 6. Thu thập metric gốc từ Kafka client

Timer của Spring Kafka đo thời gian gọi listener và gửi template. Để hiểu producer/consumer ở tầng Kafka client, có thể gắn `MicrometerProducerListener` và `MicrometerConsumerListener` vào các factory. Các listener này quản lý `KafkaClientMetrics` khi client được tạo và đóng:

```java
@Bean
public ConsumerFactory<String, OrderEvent> consumerFactory(
        MeterRegistry registry) {
    Map<String, Object> props = consumerProperties();
    DefaultKafkaConsumerFactory<String, OrderEvent> factory =
        new DefaultKafkaConsumerFactory<>(props);
    factory.addListener(new MicrometerConsumerListener<>(
        registry, Collections.singletonList(
            new ImmutableTag("service", "order-consumer"))));
    return factory;
}

@Bean
public ProducerFactory<String, OrderEvent> producerFactory(
        MeterRegistry registry) {
    Map<String, Object> props = producerProperties();
    DefaultKafkaProducerFactory<String, OrderEvent> factory =
        new DefaultKafkaProducerFactory<>(props);
    factory.addListener(new MicrometerProducerListener<>(
        registry, Collections.singletonList(
            new ImmutableTag("service", "order-producer"))));
    return factory;
}
```

Các metric client hữu ích gồm:

| Nhóm | Metric Kafka client | Ý nghĩa |
| --- | --- | --- |
| Producer | `record-send-rate`, `record-send-total` | Số record gửi mỗi giây và tổng số record gửi. |
| Producer | `record-error-rate` | Tỷ lệ gửi lỗi. |
| Producer | `record-queue-time-avg` | Thời gian record nằm trong hàng đợi producer trước khi gửi. |
| Producer | `request-latency-avg` | Độ trễ request đến broker. |
| Consumer | `records-consumed-rate`, `records-consumed-total` | Số record consumer đọc mỗi giây và tổng số đã đọc. |
| Consumer | `records-lag-max` | Lag lớn nhất quan sát được trên các partition được gán cho consumer. |
| Consumer | `fetch-rate`, `fetch-latency-avg` | Tần suất và độ trễ fetch từ broker. |

Tên metric xuất ra Micrometer hoặc Prometheus có thể được chuẩn hóa khác tên JMX của Kafka client. Hãy khám phá registry hoặc endpoint metrics của môi trường thay vì giả định tên Prometheus luôn giống tên metric Kafka.

## 7. Bật Micrometer Observation và tracing

Từ Spring Kafka 3.0, có thể bật Micrometer Observation cho `KafkaTemplate` và listener container. Observation cung cấp metric và tracing theo convention, giúp nối hoạt động gửi với hoạt động nhận khi tracing được cấu hình:

```java
kafkaTemplate.setObservationEnabled(true);
containerFactory.getContainerProperties()
    .setObservationEnabled(true);
```

Khi bật Observation, các Micrometer timer truyền thống của template/container được quản lý qua observation thay vì duy trì song song. Vì vậy, không nên cộng số liệu của hai cơ chế như thể chúng là hai lượt gửi hoặc hai lượt xử lý độc lập.

Có thể tùy chỉnh tag qua `KafkaTemplateObservationConvention` và `KafkaListenerObservationConvention`. Giữ tag ở mức cardinality thấp như listener ID, template name, topic hoặc consumer group. Tránh đưa event ID, key, offset, customer ID hoặc exception message vào tag metrics.

## 8. Đọc throughput cùng consumer lag

Throughput cho biết tốc độ, còn lag cho biết backlog đang tích tụ. Nếu producer gửi 1.000 record/giây và consumer xử lý thành công 1.000 record/giây ổn định, backlog có thể giữ nguyên. Nếu producer tiếp tục 1.000 record/giây nhưng consumer chỉ xử lý 700 record/giây, backlog tăng xấp xỉ 300 record/giây.

Kafka lưu offset theo từng partition. Consumer lag thường được tính bằng chênh lệch giữa log end offset và committed offset của consumer group trên partition. Theo dõi lag theo partition giúp phát hiện một partition nóng bị chậm dù throughput tổng thể vẫn cao.

Không nhầm `records-lag-max` của một consumer client với tổng consumer group lag trên toàn cluster. Dashboard group lag từ broker/exporter hoặc công cụ quản trị thường phù hợp để nhìn tổng backlog của group.

## 9. Chẩn đoán từ các chỉ số

| Dấu hiệu | Khả năng cần kiểm tra |
| --- | --- |
| Send attempt tăng nhưng send success giảm | Broker unavailable, serialization, timeout, quota hoặc producer error. |
| `record-queue-time-avg` và request latency tăng | Broker chậm, batch/linger, network hoặc producer buffer bị áp lực. |
| Consumer read rate cao nhưng processing success thấp | Listener chậm, lỗi nghiệp vụ, retry nhiều hoặc downstream quá tải. |
| Producer rate lớn hơn processing rate trong thời gian dài | Consumer lag tăng; kiểm tra concurrency, partition count và thời gian xử lý. |
| Chỉ một partition lag cao | Key skew, một nhóm key nóng hoặc xử lý không đồng đều giữa consumer. |
| Retry/DLT tăng trong khi throughput giảm | Dependency lỗi hoặc payload lỗi đang chiếm thời gian consumer. |

Khi tăng concurrency, kiểm tra số partition và phân bố assignment. Một consumer group không thể dùng nhiều consumer hữu ích hơn số partition đang có; tăng thread mà không tăng partition có thể không tăng throughput.

## 10. Thiết kế dashboard và cảnh báo

Một dashboard vận hành nên có các biểu đồ theo cùng time window:

- Producer send success rate và send failure rate.
- Consumer records consumed rate và business processing success rate.
- Listener processing latency p50, p95, p99.
- Consumer group lag tổng và lag theo partition.
- Retry, recovery và DLT rate.
- Producer buffer/queue time và consumer fetch latency.
- Queue depth, số record in-flight và thời gian pause nếu có backpressure.

Cảnh báo khi lag tăng liên tục trong khi processing rate thấp hơn input rate, send failure vượt ngưỡng, p95/p99 tăng bất thường hoặc DLT rate tăng đột ngột. Dùng cửa sổ nhiều phút để tránh cảnh báo do dao động ngắn.

## 11. Tránh metric cardinality quá cao

Tag metrics nên là các chiều có tập giá trị giới hạn và hữu ích cho việc lọc dashboard. Các tag thường phù hợp gồm `application`, `topic`, `group`, `listener`, `result` và có thể là `partition` nếu số partition được kiểm soát.

Không dùng `eventId`, message key, offset, email, user ID, exception message hoặc payload làm tag. Mỗi giá trị mới có thể tạo một time series mới; số lượng series tăng nhanh làm tốn bộ nhớ, CPU và chi phí lưu trữ của monitoring backend. Nếu cần truy vết một event cụ thể, dùng log có cấu trúc hoặc distributed trace thay vì metric tag.

## 12. Checklist theo dõi tốc độ gửi và nhận

- Phân biệt send attempt, send success, consume rate và business processing success.
- Bật Micrometer timer hoặc Observation cho template và listener theo phiên bản Spring Kafka.
- Gắn Kafka client metrics vào producer/consumer factory khi cần phân tích tầng client.
- Với batch listener, đếm số record trong batch thay vì số lần method được gọi.
- Theo dõi consumer group lag và lag từng partition cùng throughput.
- Đo latency p95/p99, retry, failure và DLT bên cạnh records/second.
- Giữ metric tags ở cardinality thấp; dùng log/trace cho event cụ thể.
- Đặt cảnh báo theo xu hướng và thời gian kéo dài, không chỉ theo một mẫu đo.

Theo dõi tốc độ gửi và nhận hiệu quả cần kết hợp metric của `KafkaTemplate`, listener, Kafka client và nghiệp vụ. Khi đặt throughput cạnh latency, error rate và consumer lag, nhóm vận hành có thể xác định bottleneck nằm ở producer, broker, consumer hay dịch vụ phía sau, rồi điều chỉnh partition, concurrency, batch hoặc backpressure dựa trên dữ liệu.

## Tài liệu tham khảo

- [Monitoring - Spring Kafka](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Micrometer Observation Documentation - Spring Kafka](https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html)
- [Spring Boot Actuator metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)

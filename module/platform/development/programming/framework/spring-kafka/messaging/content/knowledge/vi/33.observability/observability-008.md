# Đo thời gian xử lý listener

Trong ứng dụng Spring Kafka, thời gian xử lý listener là khoảng thời gian container ghi nhận cho một lần gọi listener. Đo chỉ số này giúp phát hiện handler chậm, so sánh độ trễ giữa các listener và theo dõi tỷ lệ xử lý thành công/thất bại. Spring Kafka tích hợp Micrometer để tự tạo timer cho listener; ứng dụng thường chỉ cần có `MeterRegistry` và cấu hình tag phù hợp.

Timer của listener trả lời câu hỏi **mỗi lần listener được gọi mất bao lâu**. Nó không phải thời gian end-to-end từ lúc producer gửi record đến lúc nghiệp vụ hoàn tất, cũng không thay thế consumer lag, Kafka fetch metrics hay thời gian chờ trong retry/backoff. Muốn tìm nguyên nhân chậm, cần xem các nhóm chỉ số này cùng nhau.

## 1. Listener timer hoạt động như thế nào?

Từ Spring Kafka 2.3, listener container tự tạo và cập nhật Micrometer `Timer` nếu Micrometer có trên classpath và ứng dụng có một `MeterRegistry` phù hợp trong application context. Timer được tạo cho các lần gọi listener thành công và thất bại.

Tên meter mặc định là `spring.kafka.listener`. Các tag chính:

| Tag | Giá trị | Ý nghĩa |
|---|---|---|
| `name` | Tên bean của listener container | Xác định listener/container được đo |
| `result` | `success` hoặc `failure` | Kết quả của lần gọi listener |
| `exception` | `none` hoặc `ListenerExecutionFailedException` | Phân biệt lần gọi thành công và thất bại |

Ví dụ một listener xử lý đơn hàng:

```java
@KafkaListener(id = "ordersListener", topics = "orders")
public void consume(OrderCreated event) {
    orderService.createOrder(event);
}
```

Khi container gọi `consume()`, timer ghi nhận thời lượng lần xử lý. Nếu phương thức kết thúc bình thường, sample thuộc nhóm `result=success`. Nếu listener ném exception ra container, sample thuộc nhóm `result=failure`.

Timer phản ánh thời gian gọi listener mà container đo được. Nếu listener gọi database hoặc REST đồng bộ, phần chờ các lời gọi đó nằm trong thời gian xử lý. Nếu listener chỉ khởi chạy tác vụ bất đồng bộ rồi trả về ngay, timer của lần gọi có thể kết thúc trước khi tác vụ nền hoàn tất. Khi cần đo thời gian hoàn tất nghiệp vụ bất đồng bộ, hãy đo riêng trong chính tác vụ đó hoặc dùng observation/span bao trùm vòng đời thực tế.

## 2. Điều kiện để Spring Kafka tự tạo timer

Để có listener timer tự động, ứng dụng cần:

1. Có Micrometer trên classpath.
2. Có `MeterRegistry` trong Spring application context.
3. Listener được chạy bởi Spring Kafka listener container.
4. `ContainerProperties.micrometerEnabled` không bị tắt.

`micrometerEnabled` mặc định là `true`. Với cấu hình thủ công, có thể bật rõ ràng:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated> orderListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setMicrometerEnabled(true);
    return factory;
}
```

Nếu dùng Spring Boot Actuator cùng Micrometer registry tương ứng, Boot thường tự cấu hình registry và các thành phần cần thiết. Nếu ứng dụng có nhiều `MeterRegistry`, cần kiểm tra cách registry được chọn và cấu hình observation/metrics của ứng dụng; tài liệu Spring Kafka mô tả cơ chế tự tạo timer khi có một registry phù hợp trong context.

Có thể tắt listener timer nếu ứng dụng đã có cơ chế đo riêng:

```java
factory.getContainerProperties().setMicrometerEnabled(false);
```

Không tắt timer chỉ để giảm số liệu khi chưa hiểu meter nào đang được xuất. Hãy kiểm tra registry và cấu hình quan sát trước để tránh tạo khoảng trống monitoring.

## 3. Timer đo những dữ liệu nào?

Micrometer `Timer` ghi nhận số lần sự kiện được đo và tổng thời gian của các lần đó. Registry hoặc backend có thể cung cấp thêm max, histogram hoặc percentile tùy cấu hình.

| Dữ liệu | Cách diễn giải |
|---|---|
| `count` | Số lần listener được gọi trong nhóm tag tương ứng |
| `total time` | Tổng thời gian của các lần gọi đã ghi nhận |
| `mean` | Thời gian trung bình, thường suy ra từ total time / count |
| `max` | Thời gian lớn nhất trong cửa sổ thống kê mà registry hỗ trợ |
| `p95`, `p99` | Phân vị độ trễ, cần cấu hình percentile hoặc histogram phù hợp với registry/backend |

Ví dụ: trong 5 phút, listener có 10.000 lần gọi, tổng thời gian xử lý là 50 giây. Mean khoảng 5 ms. Tuy nhiên, mean thấp không chứng minh hệ thống không có record chậm: nếu một số lần gọi mất vài giây, p95/p99 và max sẽ giúp phát hiện đuôi độ trễ.

Khi xuất Prometheus, tên meter và đơn vị có thể được chuẩn hóa theo quy tắc của registry, ví dụ timer được biểu diễn bằng các series `_count`, `_sum` và `_bucket` nếu histogram được bật. Không giả định p95/p99 luôn có sẵn chỉ vì meter là `Timer`; cần cấu hình phân phối và kiểm tra dữ liệu backend thực tế.

## 4. Tách thời gian thành công và thất bại

Spring Kafka duy trì timer riêng theo tag `result`. Có thể dùng chúng để trả lời hai câu hỏi khác nhau:

- Các lần xử lý thành công đang nhanh hay chậm?
- Các lần thất bại có đang tăng lên hoặc mất nhiều thời gian hơn không?

Ví dụ một listener có thể thất bại nhanh do validation, nhưng cũng có thể thất bại chậm do timeout gọi hệ thống ngoài. Hai trường hợp đều có `result=failure`, vì vậy nên kết hợp timer với log, exception và trace để tìm nguyên nhân cụ thể.

Tag `exception` của listener timer mặc định dùng `none` hoặc `ListenerExecutionFailedException`. Đây là exception wrapper mà container dùng khi báo lỗi listener; không nên mặc định tag này luôn chứa tên exception gốc từ tầng nghiệp vụ. Muốn biết lỗi gốc, hãy xem stack trace, log có correlation ID hoặc trace span.

## 5. Thêm static tags cho listener

`ContainerProperties.setMicrometerTags()` cho phép thêm tag cố định vào listener timer. Ví dụ gắn tên service và loại luồng nghiệp vụ:

```java
factory.getContainerProperties().setMicrometerTags(Map.of(
        "service", "order-service",
        "domain", "order",
        "environment", "production"
));
```

Static tags hữu ích khi dashboard cần lọc theo service, môi trường hoặc nhóm listener. Giá trị tag nên có số lượng hữu hạn và ổn định. Không thêm order ID, user ID, email, correlation ID hoặc giá trị ngẫu nhiên vào tag vì mỗi giá trị mới có thể tạo một time series mới và làm tăng cardinality rất nhanh.

## 6. Thêm dynamic tags dựa trên ConsumerRecord

Từ Spring Kafka 2.9.8 và 3.0.6, `micrometerTagsProvider` cho phép tạo tag từ record đang được xử lý. Provider nhận `ConsumerRecord<?, ?>`; các tag trả về được gộp với static tags đã cấu hình.

```java
factory.getContainerProperties().setMicrometerTagsProvider(record -> {
    Header eventType = record.headers().lastHeader("event-type");
    String type = eventType == null
            ? "unknown"
            : new String(eventType.value(), StandardCharsets.UTF_8);

    return Map.of(
            "topic", record.topic(),
            "event_type", type
    );
});
```

Chỉ dùng dynamic tag có tập giá trị nhỏ, ví dụ topic đã biết hoặc một tập event type cố định. Không lấy trực tiếp key, offset, order ID hay tenant ID không giới hạn làm tag. Nếu cần truy vết một record riêng lẻ, ghi ID vào log hoặc trace thay vì metric tag.

`micrometerTagsProvider` áp dụng cho record listener; provider này bị bỏ qua với batch listener. Nếu listener nhận `List<ConsumerRecord<...>>`, hãy chọn static tag hoặc thiết kế metric/observation riêng phù hợp với cấp batch.

## 7. Listener concurrency ảnh hưởng đến tag như thế nào?

Khi dùng `ConcurrentMessageListenerContainer`, Spring Kafka tạo timer cho từng child container/thread. Tag `name` được thêm hậu tố `-n`, với `n` bắt đầu từ `0` đến `concurrency - 1`.

Ví dụ `concurrency = 3` có thể tạo các nhóm meter:

```text
spring.kafka.listener{name="ordersListener-0", result="success", ...}
spring.kafka.listener{name="ordersListener-1", result="success", ...}
spring.kafka.listener{name="ordersListener-2", result="success", ...}
```

Điều này giúp phát hiện một consumer thread có thời gian xử lý khác biệt so với các thread còn lại. Khi xem toàn bộ listener, dashboard cần tổng hợp các series theo nhóm tag chung và loại bỏ hậu tố thread khỏi phép so sánh ở cấp service.

Tăng concurrency không tự động làm từng record xử lý nhanh hơn. Nó tăng số consumer thread có thể xử lý song song khi topic có đủ partition và tài nguyên. Nếu một partition bị dồn nhiều record chậm hoặc listener gọi hệ thống ngoài đang nghẽn, timer theo từng thread sẽ giúp nhìn ra sự chênh lệch.

## 8. Dùng Micrometer Observation thay cho listener timer cơ bản

Từ Spring Kafka 3.0, có thể bật Micrometer Observation cho listener container:

```java
factory.getContainerProperties().setObservationEnabled(true);
```

Khi Observation được bật, các Micrometer timer cơ bản bị tắt; metric timer và trace được quản lý thông qua observation. Đây là lựa chọn phù hợp khi muốn kết hợp thời gian xử lý với distributed tracing và context của message.

Observation mặc định của listener dùng tag `listener.id`. Có thể tùy biến tag bằng `KafkaListenerObservationConvention` và cấu hình convention trên container properties. Từ Spring Kafka 3.0.6, observation context có `ConsumerRecord`, cho phép thêm thuộc tính động từ record. Vẫn cần giới hạn cardinality: tag metric phải có tập giá trị nhỏ; ID riêng của từng record nên nằm trong trace hoặc log.

Với batch listener, mặc định không tạo observation cho từng record vì một observation gắn với thread trong khi một lần gọi listener có thể chứa nhiều record. Nếu cần quan sát từng record trong batch, bật:

```java
factory.getContainerProperties().setRecordObservationsInBatch(true);
```

Khi bật thuộc tính này, Spring Kafka tạo observation cho từng record trong batch; observation đó không được truyền vào phương thức listener. Cách này cho phép quan sát từng record mà vẫn giữ listener nhận cả batch. Nếu không bật per-record batch observations, batch listener tiếp tục dùng Micrometer timer cơ bản cho lần gọi batch.

## 9. Phân biệt listener timer với Kafka client metrics

Listener timer và Kafka client metrics đo hai phần khác nhau của hệ thống:

| Nhóm chỉ số | Đo điều gì? | Dùng để chẩn đoán |
|---|---|---|
| `spring.kafka.listener` | Thời gian gọi listener và kết quả xử lý | Handler chậm, exception, khác biệt giữa listener thread |
| Kafka consumer metrics | Poll, fetch, record rate, lag và trạng thái consumer | Broker/network chậm, consumer không theo kịp tốc độ ghi |
| `spring.kafka.template` | Thời gian gửi record bằng `KafkaTemplate` | Producer send chậm hoặc lỗi gửi |
| Application/database metrics | Thời gian xử lý từng dependency | Truy vấn database, REST call hoặc logic nội bộ chậm |

Spring Kafka có thể bind Kafka client metrics bằng `MicrometerConsumerListener` và `MicrometerProducerListener` trên factory. Từ Spring Kafka 3.3, `KafkaMetricsSupport` cung cấp cơ chế quản lý việc bind/unbind `KafkaMetrics` cho Kafka client. Những metric này bổ sung cho listener timer, không thay thế nó.

Ví dụ, listener timer tăng nhưng consumer lag thấp có thể chỉ ra logic nghiệp vụ hoặc dependency của listener đang chậm. Ngược lại, listener timer ổn định nhưng lag tăng có thể cho thấy lượng record đến cao hơn năng lực xử lý, partition chưa đủ hoặc consumer fetch/assignment có vấn đề.

## 10. Đo riêng một công đoạn bên trong listener

Timer tự động cho biết tổng thời gian container đo được cho listener. Nếu cần tìm công đoạn nào chiếm thời gian, có thể đo thêm một đoạn cụ thể bằng Micrometer `Timer.Sample`.

Ví dụ đo thời gian lưu database bên trong listener:

```java
@Component
class OrderListener {

    private final MeterRegistry registry;
    private final OrderRepository repository;

    OrderListener(MeterRegistry registry, OrderRepository repository) {
        this.registry = registry;
        this.repository = repository;
    }

    @KafkaListener(topics = "orders", groupId = "order-service")
    void consume(OrderCreated event) {
        Timer.Sample sample = Timer.start(this.registry);
        try {
            this.repository.save(Order.from(event));
        }
        finally {
            sample.stop(Timer.builder("app.kafka.listener.database")
                    .description("Time spent saving an order from a Kafka listener")
                    .tag("listener", "orders")
                    .register(this.registry));
        }
    }
}
```

Timer `app.kafka.listener.database` đo riêng thời gian gọi repository. Timer `spring.kafka.listener` của Spring Kafka vẫn đo lần gọi listener tổng thể. So sánh hai timer giúp ước lượng phần thời gian còn lại nằm ở mapping, validation hoặc các bước nghiệp vụ khác.

Không tạo một timer mới cho từng record hoặc từng ID. Đăng ký timer với tag ổn định và dùng lại meter đã được registry quản lý.

## 11. Đọc số liệu và tìm nguyên nhân chậm

Khi listener chậm, hãy xem các tín hiệu theo thứ tự:

1. **p95/p99 và max:** xác định chỉ một số record chậm hay phần lớn record đều chậm.
2. **success/failure:** kiểm tra tỷ lệ thất bại có tăng cùng thời gian xử lý hay không.
3. **theo container/thread:** xem một child container có bị chậm riêng do partition hoặc dữ liệu đặc biệt.
4. **consumer lag và record rate:** xác định tốc độ xử lý có theo kịp tốc độ ghi hay không.
5. **dependency timer:** so sánh thời gian database/HTTP với listener timer tổng thể.
6. **retry và backoff:** phân biệt thời gian listener thực thi với thời gian record chờ retry. Backoff có thể làm tăng tuổi record nhưng không đồng nghĩa listener method đang chạy lâu.
7. **trace và log:** tìm record cụ thể bằng correlation ID hoặc trace ID; không đưa các ID đó vào metric tag.

Một dashboard cơ bản nên có:

- Listener duration p50/p95/p99 và max.
- Số lần gọi theo `result=success` và `result=failure`.
- Consumer lag theo topic/partition/group.
- Records consumed rate và fetch latency.
- Thời gian gửi của `KafkaTemplate`.
- Tỷ lệ retry, DLT và lỗi của dependency bên ngoài.

## 12. Ghi nhớ

- Spring Kafka tự tạo listener `Timer` từ phiên bản 2.3 khi Micrometer và `MeterRegistry` phù hợp có mặt; `micrometerEnabled` mặc định là `true`.
- Meter mặc định là `spring.kafka.listener`, với các tag `name`, `result` và `exception`.
- Concurrent container tạo timer theo child thread; tag `name` có hậu tố `-0`, `-1`, ...
- Dùng `micrometerTags` cho tag cố định và `micrometerTagsProvider` cho tag từ record listener; không dùng ID có cardinality cao.
- Bật `observationEnabled` từ Spring Kafka 3.0 sẽ thay thế timer cơ bản bằng Micrometer Observation; batch listener cần cấu hình per-record observation nếu muốn quan sát từng record.
- Listener timer đo thời gian gọi listener, không phải end-to-end latency hoặc consumer lag.
- Kết hợp listener timer, Kafka client metrics, dependency timers, retry metrics và trace để tìm đúng điểm nghẽn.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Monitoring and Micrometer](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring for Apache Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring for Apache Kafka — Micrometer Observation Documentation](https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)

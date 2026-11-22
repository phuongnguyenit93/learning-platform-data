# micrometerEnabled

Trong một hệ thống Spring Kafka chạy production, thông báo “consumer vẫn RUNNING” không đủ để xác nhận dịch vụ hoạt động tốt. Listener có thể xử lý chậm, liên tục ném exception, retry nhiều lần hoặc không thực hiện business side effect đúng yêu cầu. Để quan sát các vấn đề đó, Spring Kafka tích hợp **Micrometer** và có thể tự ghi nhận thời gian thực thi của Kafka listener.

Thuộc tính **micrometerEnabled** trên **ContainerProperties** kiểm soát việc bật hay tắt **Micrometer Timer metrics cho listener invocation**. Khi cơ chế này được bật và có Micrometer trên classpath, Spring Kafka có thể tạo các timer mang tên **spring.kafka.listener**, gắn tags để phân biệt listener và kết quả thực thi. Metrics này cho phép trả lời những câu hỏi như listener có còn được gọi không, tỷ lệ gọi thành công/thất bại ra sao, latency tăng ở listener nào và một deployment mới có làm thời gian xử lý record tăng hay không.

Tuy nhiên, **micrometerEnabled không phải công tắc bật toàn bộ quan sát Kafka**. Nó không tự xuất metrics lên Prometheus, không tự đo consumer lag hoặc broker health, không bảo đảm distributed tracing và không thay thế business metrics. Trong Spring Kafka hiện đại còn có **Micrometer Observation** qua thuộc tính observationEnabled, có phạm vi và cấu hình khác. Hiểu đúng ranh giới này là trọng tâm của bài học thuộc chương **Monitoring và metrics** trong **Spring Kafka Reliability Operations**.

## 1. Ba lớp observability cần phân biệt

Một ứng dụng Kafka thường cần theo dõi ít nhất ba lớp:

1. **Listener invocation metrics:** thời gian framework gọi listener, kết quả success/failure, exception class; đây là phạm vi liên quan trực tiếp đến micrometerEnabled.
2. **Kafka client metrics:** thông tin của KafkaConsumer/KafkaProducer như fetch rate, records consumed, request latency, coordinator/rebalance hoặc send retries; đến từ Kafka clients và các cơ chế thu thập tương ứng.
3. **Business reliability metrics:** số đơn hàng xử lý thành công, tỷ lệ duplicate, retry exhausted, record ở DLT, side effect database thành công, consumer lag so với SLA; nhiều metric cần ứng dụng tự instrument.

~~~mermaid
flowchart TB
    K["Kafka broker / partitions"] --> C["KafkaConsumer"]
    C --> L["Spring Kafka Listener Container"]
    L --> B["@KafkaListener / business processing"]
    B --> D["Database / HTTP / downstream"]
    L --> T["Micrometer listener timers"]
    C --> M["Kafka client metrics"]
    B --> X["Business metrics"]
    T --> R["MeterRegistry"]
    M --> R
    X --> R
    R --> P["Actuator / Prometheus / monitoring backend"]
~~~

Một metric listener tăng đều không chứng minh downstream side effect đã commit chính xác một lần. Ngược lại, Kafka client vẫn poll bình thường nhưng listener có thể liên tục lỗi. Vì thế, không nên thay thế tất cả dashboard Kafka bằng một timer có tên spring.kafka.listener.

### 1.1 Bảng ý nghĩa từng lớp

| Quan sát cần thiết | Nguồn ưu tiên | Có do micrometerEnabled trực tiếp cung cấp? |
|---|---|---|
| Số lần listener method được gọi | Listener Timer count | Có, khi timer được ghi nhận |
| Thời gian xử lý listener invocation | Listener Timer | Có |
| Listener invocation ném exception | Listener Timer result/exception tags | Có, trong phạm vi invocation |
| Kafka consumer records-lag-max | Kafka client metrics | Không |
| Consumer group committed offset / lag theo partition | Kafka broker/admin/monitoring | Không |
| Kafka producer request latency | Producer/client metrics | Không |
| Record vào Dead Letter Topic | Recovery instrumentation/producer metrics | Không tự động |
| Business order được ghi DB thành công | Business metrics hoặc DB | Không tự động |
| Distributed trace giữa producer và consumer | Micrometer Observation/Tracing và propagation | Không chỉ bởi micrometerEnabled |
| Health endpoint của service | Spring Boot Actuator Health và checks | Không |

## 2. micrometerEnabled nằm ở đâu?

Trong Spring Kafka, thuộc tính có liên quan là:

~~~java
factory.getContainerProperties().setMicrometerEnabled(true);
~~~

Đây là setter trên **ContainerProperties**, được sử dụng khi cấu hình listener container hoặc listener container factory. Với Kafka listener containers, thuộc tính này điều khiển việc tạo các Micrometer timers trong flow xử lý listener nếu các điều kiện của framework được đáp ứng.

Ví dụ:

~~~java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.setBatchListener(false);

        factory.getContainerProperties()
               .setMicrometerEnabled(true);

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrdersListener {

    private final OrderService orderService;

    public OrdersListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "orders-projection",
        topics = "orders",
        groupId = "orders-projection-prod",
        containerFactory = "ordersKafkaListenerContainerFactory"
    )
    public void handle(OrderEvent event) {
        orderService.apply(event);
    }
}
~~~

Các class OrderEvent/OrderService trong ví dụ là model và service giả định. Trong project thực tế, ConsumerFactory còn phải có deserializers, security, bootstrap servers và các consumer properties phù hợp.

### 2.1 Default và sự hiện diện của Micrometer

Trong các dòng Spring Kafka hỗ trợ Micrometer listener timers, **micrometerEnabled thường mặc định là true**. Nhưng timer chỉ có thể được tạo khi thư viện Micrometer phù hợp có trên classpath và có registry để ghi nhận theo cấu hình runtime.

Vì vậy có ba tình huống khác nhau:

| Trạng thái | Kết quả có thể thấy |
|---|---|
| micrometerEnabled=true, Micrometer sẵn sàng | Spring Kafka có thể tạo listener timers |
| micrometerEnabled=false | Listener Timer tự động của cơ chế này bị tắt |
| micrometerEnabled=true nhưng thiếu dependency/registry/export | Có thể không thấy metric ở backend dù property true |

Không suy luận rằng setting true đủ để metric xuất hiện trong Grafana. Cần xác nhận đường dữ liệu **listener → meter registry → exporter → Prometheus/monitoring backend**.

### 2.2 Bật rõ ràng khác với phụ thuộc default

Dù default hiện tại là true, cấu hình explicit có thể hữu ích khi:

- Dự án muốn thể hiện rõ một listener phải được đo timing.
- Có nhiều listener factories và mỗi factory có policy observability khác nhau.
- Có integration tests về metrics.
- Đang migration giữa Micrometer Timer và Micrometer Observation.
- Muốn tắt riêng metrics trong một workload có cardinality hoặc chi phí cao.

Không cấu hình bật/tắt rải rác trong nhiều factory customizers mà không biết thứ tự ưu tiên, vì effective setting tại container có thể khác điều người đọc YAML mong đợi.

## 3. Một listener Timer đo thời gian nào?

Với record listener đồng bộ, timer bao quanh phần thực thi listener invocation mà Spring Kafka instrument.

Ví dụ:

~~~java
@KafkaListener(
    id = "orders-projection",
    topics = "orders",
    groupId = "orders-projection-prod"
)
public void handle(OrderCreated order) {
    validate(order);
    orderService.apply(order);
}
~~~

Một invocation có thể bao gồm validate() và orderService.apply(). Khi listener trả về bình thường, framework có thể ghi nhận timer cho invocation thành công. Khi exception thoát khỏi listener theo semantics framework, timer lỗi có thể được ghi với result/exception tags tương ứng.

Tuy nhiên, phải phân biệt các mốc sau:

~~~text
KafkaConsumer.poll()
  -> ConsumerRecord deserialize
  -> Spring listener invocation START
       -> validate
       -> DB / HTTP processing
  -> Listener invocation END
  -> Container error handling / acknowledgment / offset commit
  -> Các thao tác khác của consumer lifecycle
~~~

**Listener Timer không mặc định đo toàn bộ đường đi end-to-end từ lúc producer gửi record tới khi offset được commit**, cũng không nhất thiết bao gồm thời gian đang chờ BackOff hoặc DLT publisher hoàn tất. Phạm vi chính là listener invocation.

### 3.1 Record processing latency khác event freshness

Giả sử event được producer gửi lúc 10:00:00, nằm trong Kafka hai phút vì consumer lag, sau đó listener xử lý thành công trong 50 ms.

- Listener Timer ghi nhận khoảng 50 ms.
- End-to-end event latency từ producer tới xử lý xong là khoảng hai phút.
- Consumer lag đã gây phần lớn độ trễ.
- Chỉ nhìn spring.kafka.listener sẽ không phát hiện toàn bộ vấn đề freshness.

Muốn đo event age, cần timestamp nguồn đáng tin cậy và instrumentation bổ sung; cần chú ý clock skew, timestamp semantics của Kafka và độ trễ giữa các hệ thống.

### 3.2 Listener có thao tác async

Ví dụ:

~~~java
@KafkaListener(topics = "orders")
public void handle(OrderEvent event) {
    executor.submit(() -> process(event));
}
~~~

Method có thể return gần như ngay lập tức trong khi task thực sự chưa chạy xong. Timer của invocation khi đó **không tự đo đầy đủ thời gian hoàn tất business work trên executor**. Nghiêm trọng hơn, offset có thể được commit trước side effect nếu acknowledgment design không phù hợp.

Khi dùng async listener processing:

- Đo riêng thời gian business task hoàn tất.
- Dùng bounded queues và backpressure.
- Đồng bộ offset acknowledgment với completion theo Kafka/Spring design phù hợp.
- Không coi timer success của method submit là nghiệp vụ thành công.
- Đảm bảo exception của async task được quan sát và recovery.

## 4. Tên meter và các tags thường gặp

Trong cơ chế listener timers của Spring Kafka, meter phổ biến mang tên:

~~~text
spring.kafka.listener
~~~

Micrometer Timer lưu các thông tin như **count**, **totalTime** và **max** thông qua API của MeterRegistry. Các tags trong các phiên bản phổ biến của Spring Kafka gồm:

- **name:** tên hoặc listener/container name theo framework.
- **result:** thành công hoặc thất bại, thường phân biệt success/failure.
- **exception:** loại exception hoặc giá trị không có exception.
- **Các tags tĩnh hoặc động:** bổ sung qua ContainerProperties khi được hỗ trợ.

Ví dụ logic một số time series:

~~~text
spring.kafka.listener
  name=orders-projection-0
  result=success
  exception=none

spring.kafka.listener
  name=orders-projection-0
  result=failure
  exception=DataAccessResourceFailureException
~~~

Đây là minh họa cách phân nhóm metrics, không phải cam kết các phiên bản framework sẽ xuất mọi tag giống hệt nhau. Với concurrent listeners, tên meter tag có thể phản ánh child container và sử dụng hậu tố.

### 4.1 Success có nghĩa gì?

Success của timer thường nghĩa là **listener invocation hoàn thành theo cách framework xem là không lỗi**. Nó không chứng minh:

- DB transaction đã commit bền vững.
- Kafka consumer offset đã commit.
- Một Kafka transaction bên ngoài đã commit.
- Downstream đã nhận HTTP request chính xác một lần.
- Record không được đọc lại sau restart.
- Toàn bộ business workflow đã hoàn thành.

Nếu listener bắt exception, log và return bình thường, timer có thể được ghi thành công:

~~~java
@KafkaListener(topics = "orders")
public void handle(OrderEvent event) {
    try {
        orderService.apply(event);
    }
    catch (Exception ex) {
        log.error("Failed but swallowed", ex);
        // Method return bình thường.
    }
}
~~~

Đây là một anti-pattern nếu exception cần retry hoặc rollback. Metrics success không thể sửa việc listener đã che lỗi nghiệp vụ.

### 4.2 Failure có nghĩa gì?

Failure cho thấy listener invocation được framework ghi nhận lỗi. Nó chưa phân biệt:

- Transient DB timeout có thể retry.
- Poison message cần DLT.
- Lỗi business validation.
- Lỗi serialization/conversion.
- Transaction rollback xảy ra sau callback.

Với một record thất bại ba lần rồi thành công, listener timer có thể ghi nhiều failed invocations và một success invocation. Đây là **số lần gọi listener**, không nhất thiết là số unique Kafka records.

## 5. Đếm invocations và đếm unique records khác nhau

Một record ở orders-0 offset 100 có thể được gọi lại nhiều lần theo DefaultErrorHandler.

~~~text
record orders-0@100
  attempt 1 -> listener throws
  attempt 2 -> listener throws
  attempt 3 -> listener returns success
~~~

Metrics có thể ghi ba listener invocations:

~~~text
failure count += 2
success count += 1
~~~

Nhưng số unique Kafka records được xử lý thành công là một, nếu chỉ tính record tại offset 100.

Không dùng tổng listener timer count như số unique business events hoàn thành trong hệ thống có retry, rebalance hoặc at-least-once redelivery.

### 5.1 DLT và recovery không hiện đầy đủ trong timer

Nếu DefaultErrorHandler recover record bằng cách publish sang DLT, listener có thể đã ném exception nhưng recovery thành công ở tầng container. Timer cho failed invocation không phải metric “DLT publish succeeded”.

Cần các metrics khác:

- Retry attempt count.
- Retry exhausted count.
- DLT publish success/failure.
- Age of oldest DLT event.
- Consumer offset progression.
- Business operation completion.

### 5.2 Deserialization có thể thất bại trước listener

Nếu deserializer ném exception trong KafkaConsumer.poll(), @KafkaListener chưa được gọi. Do đó, listener invocation timer có thể **không tăng** cho record đó, dù consumer đang mắc lỗi nghiêm trọng.

Với ErrorHandlingDeserializer và DefaultErrorHandler, lỗi có thể được chuyển vào flow recovery trước khi listener được gọi. Vì vậy cần metric riêng cho deserialization error và DLT.

**Không sử dụng listener timer failure rate như chỉ số duy nhất cho toàn bộ consumer errors.**

## 6. Bật và tắt tại đúng listener factory

Một ứng dụng thường có nhiều KafkaListenerContainerFactory:

~~~text
ordersRecordFactory  -> orders consumer
paymentsBatchFactory -> payments consumer
auditFactory         -> audit consumer
~~~

Nếu chỉ bật micrometerEnabled trên ordersRecordFactory, không thể kết luận metrics của payments/audit đã được bật theo cùng policy.

Ví dụ chủ động tắt trên workload khác:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, AuditEvent>
auditKafkaListenerContainerFactory(
        ConsumerFactory<String, AuditEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, AuditEvent>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties()
           .setMicrometerEnabled(false);

    return factory;
}
~~~

Một số lý do có thể tắt timer:

- Workload có cách instrumentation riêng.
- Đang bật Micrometer Observation và muốn tránh nhầm các metrics trùng mục đích.
- Cần giảm chi phí thu thập metrics trong một thành phần đặc biệt.
- Có vấn đề cardinality và cần thay lại metric tagging policy.

Nhưng tắt micrometerEnabled cũng có thể khiến dashboard vốn dựa trên spring.kafka.listener không còn dữ liệu. Trước khi thay đổi, phải biết monitoring backend đang đọc metric nào và có phương án migration.

### 6.1 Configurer và auto-configuration

Spring Boot có thể auto-configure listener container factory và hỗ trợ customization qua các extension points. Nếu ứng dụng tự tạo factory, cần kiểm tra có giữ các cấu hình cần thiết của Boot không, ví dụ:

- ConsumerFactory phù hợp.
- Error handler.
- Concurrency/AckMode.
- Interceptors.
- Container observation settings.
- Message converter.
- Transaction manager.

Không tạo một custom factory chỉ để bật micrometerEnabled rồi vô tình bỏ cấu hình retry/transaction của factory cũ.

## 7. Gắn tags tĩnh bằng micrometerTags

Trong các Spring Kafka versions hỗ trợ, ContainerProperties có thể cấu hình **micrometerTags** để bổ sung tags tĩnh cho listener timers.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties()
           .setMicrometerEnabled(true);

    factory.getContainerProperties().setMicrometerTags(
        Map.of(
            "domain", "orders",
            "pipeline", "projection",
            "stage", "consumer"
        )
    );

    return factory;
}
~~~

Tags giúp phân nhóm metrics trong dashboard:

- Domain orders/payments/inventory.
- Pipeline projection/notification/indexing.
- Stage consumer hoặc workload category.
- Environment prod/staging nếu môi trường không được gắn tự động ở exporter.

### 7.1 Tags phải có số giá trị hữu hạn

Một metric có 5 listener names, 2 results, 10 exceptions và 3 domains có thể tạo tối đa khoảng 300 series trước khi tính instance/pod labels. Nếu thêm eventId hoặc orderId làm tag, số series có thể tăng theo từng record.

**Không gắn các giá trị sau làm Micrometer tags cho listener timers:**

- orderId.
- eventId.
- requestId.
- Kafka offset.
- Raw message key có cardinality lớn.
- User ID.
- Full exception message.
- Payload hoặc PII.

Những giá trị này phù hợp hơn với structured logs/traces có giới hạn truy cập, không phải metric tags.

### 7.2 Tags của container khác labels của monitoring system

Một số labels được thêm bởi Prometheus scrape hoặc Kubernetes, như instance, pod, namespace hoặc job. Chúng có thể làm cardinality nhân lên.

Khi thiết kế dashboard, phải tính tổng cardinality sau khi exporter gắn thêm labels, không chỉ tính Map mà code truyền vào setMicrometerTags().

### 7.3 Không hardcode dynamic instance ID vào tag nếu không cần

Một listener ID có UUID hoặc timestamp thay đổi theo từng deploy có thể tạo series mới mỗi lần rollout. Dù thông tin này hữu ích để debug, nó có thể khiến backend giữ hàng nghìn time series không cần thiết.

Nên dùng:

- Logical listener ID ổn định.
- Pod/instance labels do hạ tầng quản lý khi thực sự cần.
- Controlled set of domain/pipeline tags.
- Trace ID/event ID trong logs/traces, không dùng làm Prometheus metric labels.

## 8. Dynamic micrometerTagsProvider

Một số phiên bản Spring Kafka có **micrometerTagsProvider**, cho phép bổ sung tags dựa trên ConsumerRecord. Đây là cơ chế nâng cao và phải kiểm tra API của version thực tế.

Ví dụ minh họa:

~~~java
factory.getContainerProperties()
       .setMicrometerTagsProvider(record ->
           Map.of(
               "topic", record.topic()
           )
       );
~~~

Điểm tốt của ví dụ: topic là một tập có giới hạn, thường phù hợp làm tag nếu số topic không quá lớn.

Điểm nguy hiểm: đổi sang record.key() hoặc eventId vì nó có thể có hàng triệu giá trị. Metrics backend có thể quá tải, tốn memory và chi phí lưu trữ.

### 8.1 Dynamic tags và timer lifetime

Để recording một timer, framework phải chọn meter identity dựa trên name và tags. Nếu mỗi record chọn một bộ tags duy nhất, mỗi invocation có thể đăng ký meter khác nhau. Đó không phải cách sử dụng Micrometer hiệu quả.

Hãy đặt quy tắc:

1. Chỉ dùng tags với tập giá trị hữu hạn.
2. Không lộ dữ liệu cá nhân vào tags.
3. Không dùng exception message làm tag.
4. Có giới hạn cardinality trong thiết kế.
5. Theo dõi số active meter series trước và sau rollout.
6. Kiểm tra behavior theo phiên bản Spring Kafka và Micrometer.

### 8.2 Khi nào provider không cần thiết?

Nếu mỗi listener luôn subscribe đúng một topic, tag topic có thể suy ra từ listener name hoặc cấu hình static. Dùng dynamic provider chỉ để lặp lại thông tin tĩnh khiến logic phức tạp hơn mà không tăng khả năng phân tích.

Với listener subscribe nhiều topics, topic tag có thể hữu ích, nhưng cardinality phải được kiểm soát.

## 9. Spring Boot Actuator và MeterRegistry

**micrometerEnabled=true không tự tạo Prometheus endpoint**. Cần có Micrometer registry và exporter phù hợp.

Một Spring Boot application có thể dùng dependencies:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-registry-prometheus")
    implementation("org.springframework.kafka:spring-kafka")
}
~~~

Phiên bản dependencies nên do Spring Boot BOM/platform quản lý, tránh pin các Micrometer versions không tương thích với Spring Boot/Spring Kafka đang dùng.

Ví dụ cấu hình Actuator:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    prometheus:
      access: unrestricted
~~~

Thuộc tính access và hành vi security khác nhau giữa các Spring Boot versions. Cấu hình trên thể hiện ý tưởng cần expose endpoint; phải đối chiếu dependency version và **bảo vệ endpoint** bằng network policies, authentication hoặc scrape access phù hợp.

Một số phiên bản Boot dùng cơ chế enablement hoặc access policy khác; không chép nguyên khối này mà bỏ qua production security.

### 9.1 Đường dữ liệu metrics

~~~mermaid
flowchart LR
    L["Spring Kafka listener timer"] --> MR["MeterRegistry"]
    MR --> A["Spring Boot Actuator"]
    A --> EP["/actuator/prometheus"]
    EP --> PR["Prometheus scrape"]
    PR --> G["Grafana dashboards"]
~~~

Để dữ liệu xuất hiện cần:

- Listener thật sự chạy và tạo observations/timer records.
- Có MeterRegistry và registry exporter phù hợp.
- Prometheus endpoint đã được expose đúng.
- Monitoring collector có thể truy cập endpoint.
- Scrape config chọn đúng target.
- Không có MeterFilter chặn metric hoặc đổi tên/tag ngoài dự kiến.

### 9.2 Kiểm tra bằng Actuator metrics

Spring Boot Actuator metrics endpoint có thể dùng tên logical Micrometer meter:

~~~text
GET /actuator/metrics/spring.kafka.listener
~~~

Trong các hệ thống có metric, response thường cho thấy measurements và availableTags. Không nên kỳ vọng một timer xuất hiện trước khi đã có listener invocation tương ứng, tùy cách meter được đăng ký và lifecycle runtime.

Để xuất theo Prometheus:

~~~text
GET /actuator/prometheus
~~~

Tên metric trong Prometheus khác tên logical Micrometer do naming convention và đơn vị thời gian.

## 10. Tên metric ở Prometheus

Micrometer Timer thường được xuất ra Prometheus dưới dạng các series có suffix:

~~~text
spring_kafka_listener_seconds_count
spring_kafka_listener_seconds_sum
spring_kafka_listener_seconds_max
~~~

Tên và các series thực tế còn phụ thuộc registry version, histogram/percentile settings và cách metric được export. Để tránh sai, nên kiểm tra endpoint /actuator/prometheus trên runtime thực tế.

Ví dụ PromQL minh họa:

~~~promql
sum by (name) (
  rate(spring_kafka_listener_seconds_count{result="success"}[5m])
)
~~~

Đây là rate của **successful listener invocations**, không phải số unique orders.

Tỷ lệ failed invocations:

~~~promql
sum(rate(spring_kafka_listener_seconds_count{result="failure"}[5m]))
/
clamp_min(
  sum(rate(spring_kafka_listener_seconds_count[5m])),
  0.001
)
~~~

Khi lưu lượng thấp, tỷ lệ lỗi dao động mạnh. Nên kết hợp tối thiểu số attempts/requests trước khi alert theo phần trăm, không đặt một error percentage threshold mà bỏ qua traffic.

### 10.1 Average listener duration

Nếu exporter có _sum và _count:

~~~promql
sum(rate(spring_kafka_listener_seconds_sum[5m]))
/
clamp_min(
  sum(rate(spring_kafka_listener_seconds_count[5m])),
  0.001
)
~~~

Kết quả là **average invocation duration trong giây**, theo phạm vi series được chọn. Giá trị trung bình hữu ích nhưng dễ che tail latency.

### 10.2 p95/p99 latency cần histogram hoặc phân phối phù hợp

Không thể tính p95 đáng tin cậy từ chỉ _sum và _count. Với Prometheus histogram đã được bật, có thể dùng:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, name) (
    rate(spring_kafka_listener_seconds_bucket[5m])
  )
)
~~~

Series _bucket **không tự xuất hiện trong mọi cấu hình**. Cần bật histogram/distribution publication theo Micrometer/Spring Boot version, cân nhắc bucket count và chi phí cardinality.

Một cấu hình thường thấy trong Spring Boot Micrometer:

~~~properties
management.metrics.distribution.percentiles-histogram.spring.kafka.listener=true
~~~

Property này là ví dụ về cách bật histogram trong các phiên bản hỗ trợ, cần xác nhận effective configuration và naming convention của registry. Chỉ bật histogram cho những timers thực sự cần percentile SLO; nhiều buckets nhân với nhiều tags có thể làm metric series tăng đáng kể.

### 10.3 Query theo listener cụ thể

Khi name tag trong runtime phản ánh child IDs, có thể dùng regex theo convention:

~~~promql
sum(
  rate(
    spring_kafka_listener_seconds_count{
      name=~"orders-projection.*",
      result="failure"
    }[5m]
  )
)
~~~

Regex rộng có thể match orders-projection-canary hoặc retry listener có tên tương tự. Trong dashboard production, nên thống nhất naming convention và labels để tránh gộp nhầm.

## 11. Micrometer Timer khác Kafka consumer metrics

Micrometer listener timer không cho thấy tốc độ fetch, số partitions assignment hoặc consumer lag.

Kafka client có một tập metrics riêng từ KafkaConsumer/KafkaProducer. Spring Kafka cũng hỗ trợ tích hợp Micrometer cho các client thông qua factory listeners hoặc Kafka client metrics binder, tùy framework version và cấu hình.

Trong các phiên bản Spring Kafka hỗ trợ, có các thành phần như:

- **MicrometerConsumerListener**: tích hợp Micrometer với ConsumerFactory để thu Kafka consumer metrics.
- **MicrometerProducerListener**: tích hợp với ProducerFactory để thu Kafka producer metrics.
- Các binders/auto-configuration khác do Spring Boot/Micrometer cung cấp.

Chúng **khác** setMicrometerEnabled(true) trên ContainerProperties.

### 11.1 Ví dụ conceptual wiring

~~~java
@Bean
ConsumerFactory<String, OrderEvent> ordersConsumerFactory(
        MeterRegistry registry,
        Map<String, Object> consumerProperties) {

    var factory =
        new DefaultKafkaConsumerFactory<String, OrderEvent>(
            consumerProperties
        );

    factory.addListener(
        new MicrometerConsumerListener<>(registry)
    );

    return factory;
}
~~~

Đoạn code minh họa khái niệm và yêu cầu imports/cấu hình consumer serializers phù hợp. Trong Spring Boot application, một số client metrics có thể đã được auto-configured; **không add listener hai lần** nếu project đã có instrumentation tương đương.

### 11.2 Tách các câu hỏi monitoring

| Câu hỏi | Cơ chế phù hợp |
|---|---|
| Listener mất bao lâu để xử lý một record? | Listener Timer hoặc Observation |
| Consumer có còn poll không? | Consumer metrics, poll monitoring, events |
| Lag của group theo partition là bao nhiêu? | Kafka group lag monitoring |
| Producer có retries hoặc request timeout không? | Producer/client metrics |
| Một event phải chờ bao lâu từ lúc publish? | Event timestamp + application instrumentation |
| Listener thất bại bao nhiêu lần? | Listener failure timer và error handler metrics |
| DLT publish thành công không? | DLT publisher/recoverer monitoring |
| Database đã commit business state chưa? | Business/DB metrics và audit |

Nếu chỉ bật micrometerEnabled rồi hỏi “vì sao consumer lag tăng?”, cần bổ sung đúng metrics thay vì tìm một thuộc tính không liên quan trên timer.

## 12. micrometerEnabled và observationEnabled

Trong Spring Kafka hiện đại, có **Micrometer Observation** để hỗ trợ metrics và tracing dựa trên Micrometer Observation API.

Một container có thể được cấu hình:

~~~java
factory.getContainerProperties().setObservationEnabled(true);
~~~

**observationEnabled** không đồng nghĩa **micrometerEnabled**:

- micrometerEnabled điều khiển **cơ chế Micrometer listener timers truyền thống**.
- observationEnabled điều khiển **Observation instrumentation** của listener; có thể kết nối metrics và tracing tuỳ ObservationRegistry/handlers.
- Khi observation được bật, cơ chế timer truyền thống có thể **bị vô hiệu hóa hoặc không được ghi song song** theo semantics Spring Kafka version, để Observation đảm nhiệm instrumentation tương ứng.

### 12.1 Cần tránh hai kỳ vọng sai

**Sai lầm thứ nhất:** “Bật observationEnabled thì dashboard spring.kafka.listener chắc chắn giữ nguyên mọi tag và series.”

Observation có thể tạo các metrics khác hoặc tags khác theo conventions. Tên meter hoặc schema có thể thay đổi tùy Spring Kafka/Micrometer versions và custom observation conventions. Khi migration, kiểm tra metrics thực tế và cập nhật dashboard/alerts có chủ đích.

**Sai lầm thứ hai:** “Nếu micrometerEnabled=false thì không thể có bất kỳ Kafka metric nào.”

Vẫn có thể có Kafka client metrics, custom meters và observation-based metrics nếu được bật riêng. Tắt một timer không tắt toàn bộ Micrometer infrastructure.

### 12.2 Ví dụ chính sách lựa chọn

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    // Lựa chọn 1: listener timers truyền thống.
    factory.getContainerProperties().setMicrometerEnabled(true);
    factory.getContainerProperties().setObservationEnabled(false);

    return factory;
}
~~~

Hoặc với tracing/observation:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersObservedListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    // Lựa chọn 2: Micrometer Observation.
    factory.getContainerProperties().setObservationEnabled(true);

    return factory;
}
~~~

Ở lựa chọn hai, không nên giả định setMicrometerEnabled(true) sẽ buộc timer truyền thống hoạt động cùng Observation; framework có thể dùng instrumentation path riêng. Cần quan sát effective metric output tại runtime.

### 12.3 Khi nào dùng Timer hay Observation?

| Nhu cầu | Listener Timer truyền thống | Observation |
|---|---|---|
| Đếm invocation và đo duration | Phù hợp | Phù hợp khi metrics handler được cấu hình |
| Dùng dashboard Timer hiện có | Ít thay đổi | Cần kiểm tra migration |
| Distributed tracing qua Kafka | Không tự đủ | Phù hợp hơn với tracing/propagation |
| Correlation với trace/span | Cần instrumentation bổ sung | Hệ thống Observation/Tracing hỗ trợ |
| Chỉ cần một số metrics đơn giản | Ít thành phần hơn | Có thể là overhead không cần thiết |
| Truyền context qua producer-consumer | Không từ micrometerEnabled | Cần Observation/Tracing config đúng |

Không chọn Observation chỉ vì tên “mới hơn”. Chọn theo mục tiêu observability, versions, registry, tracing backend và khả năng vận hành.

## 13. Kiến trúc metrics theo record và theo batch

Spring Kafka hỗ trợ record listener và batch listener.

### 13.1 Record listener

~~~java
@KafkaListener(
    id = "orders-record",
    topics = "orders",
    containerFactory = "recordFactory"
)
public void onRecord(OrderEvent event) {
    service.process(event);
}
~~~

Với record listener, một invocation thường tương ứng một record, vì vậy count timer gần với số lần delivery vào listener. Nhưng một record có thể được gọi lại do retry/rebalance, nên count không phải số unique records.

### 13.2 Batch listener

~~~java
@KafkaListener(
    id = "orders-batch",
    topics = "orders",
    containerFactory = "batchFactory"
)
public void onBatch(List<OrderEvent> events) {
    service.processBatch(events);
}
~~~

Với batch listener, một invocation có thể xử lý nhiều records. Timer count = số **batch invocations**, không phải số records trong batch.

Ví dụ:

~~~text
Batch 1: 120 records -> 1 listener invocation
Batch 2: 100 records -> 1 listener invocation
Batch 3: 80 records  -> 1 listener invocation

Listener Timer count: khoảng 3
Business records attempted: 300
~~~

Nếu đánh giá throughput records/second từ Timer count của batch listener mà không đo batch size, dashboard có thể thấp hơn thực tế rất nhiều.

### 13.3 Đo throughput thực tế cho batch

Có thể tạo custom counter hoặc DistributionSummary:

~~~java
@Component
public class OrderBatchMetrics {

    private final Counter batchRecordsAttempted;

    public OrderBatchMetrics(MeterRegistry registry) {
        this.batchRecordsAttempted = Counter.builder(
                "orders.batch.records.attempted"
            )
            .description("Records attempted by the batch listener")
            .register(registry);
    }

    public void recordBatchSize(int size) {
        batchRecordsAttempted.increment(size);
    }
}
~~~

Đây là số records **attempted**, không phải unique committed business records. Nếu batch thất bại và retry, counter có thể đếm lại. Nên định nghĩa metric semantics rõ ràng.

## 14. Error handler và retry làm méo tỷ lệ success/failure

Một record tạm thời lỗi hai lần rồi thành công có thể tạo:

~~~text
Listener attempt 1 -> failure
Listener attempt 2 -> failure
Listener attempt 3 -> success
~~~

Nếu dashboard tính:

~~~text
success rate = success listener invocations / total invocations
~~~

thì record này có tỷ lệ success 1/3, dù cuối cùng nghiệp vụ có thể hoàn thành. Metrics này phản ánh **listener attempt success rate**, không phải **final recovery success rate**.

Cần có các metrics phụ:

| Metric | Đơn vị cần định nghĩa |
|---|---|
| listener_attempts_total | Số listener invocations |
| listener_failures_total | Số failed invocations |
| record_retries_total | Số retry attempts do error handler |
| recovery_success_total | Số records được recover thành công |
| dlt_published_total | Số records thực sự ghi DLT thành công |
| business_completed_total | Số business operations hoàn tất |
| business_duplicate_total | Số event IDs đã xử lý trước đó |

Một số metric trên là custom metrics, không phải Spring Kafka tự động export.

### 14.1 Không đánh đồng recovery với success

Nếu DeadLetterPublishingRecoverer publish record lỗi vào DLT thành công, handler có thể cho phép consumer tiếp tục. Đây là **successful recovery/quarantine**, không phải listener đã hoàn thành business operation.

Một dashboard chỉ nhìn Kafka lag giảm và listener timer có một failure sẽ không cho biết đã có sự kiện bị quarantine. Cần theo dõi DLT và nghiệp vụ riêng.

### 14.2 Transaction rollback sau listener

Trong transactional listener, method có thể return nhưng Kafka transaction commit hoặc offset coordination sau đó có thể gặp lỗi. Listener Timer success không phải bằng chứng Kafka transaction commit đã hoàn tất.

Nếu mục tiêu là Kafka exactly-once processing, phải theo dõi transaction begin/commit/abort, producer fencing, consumer offsets và downstream read_committed, ngoài listener timing.

## 15. Metrics và consumer lag

Consumer lag là một tín hiệu quan trọng nhưng micrometerEnabled không tự tính nó.

Lag thường cần so sánh:

- Log end offset của partition.
- Committed offset của consumer group.
- Assignment/ownership và thời điểm đo.

Các metrics Kafka client có thể có chỉ số records-lag-max hoặc những lag measurements khác, nhưng chúng không hoàn toàn thay thế lag monitoring theo group/topic/partition từ Kafka Admin/monitoring service.

### 15.1 Vì sao timer thấp nhưng lag vẫn tăng?

Có thể vì:

- Producer ghi 10.000 records/giây, consumer xử lý được 7.000.
- Consumer đang pause.
- Poll/rebalance bị chậm.
- Một poison record gây blocking retry.
- Consumer chỉ được gán một số partitions nóng.
- Listener chạy async và ghi nhận timer ngắn nhưng downstream queue tăng.
- Broker/network đang chậm fetch.

Micrometer listener timer chủ yếu giúp tìm **processing duration**. Để giải thích lag cần thêm rate, partition assignment, pause status và client metrics.

### 15.2 SLO nên dựa trên mục tiêu nghiệp vụ

Ví dụ SLO:

~~~text
99% OrderCreated events phải hoàn tất projection
trong vòng 2 phút kể từ Kafka append timestamp.
~~~

Listener p99 dưới 100 ms là điều tốt nhưng chưa đủ chứng minh SLO trên nếu records có thể chờ trong partition nhiều phút.

Nên theo dõi end-to-end event age và trạng thái xử lý thực sự, kết hợp listener duration, retry, lag và DLT.

## 16. Micrometer tags và chi phí cardinality

Micrometer Registry quản lý meters dựa trên **name + tags**. Mỗi tổ hợp tags khác nhau có thể là một time series riêng ở monitoring backend.

Giả sử:

- 20 listener IDs/children.
- 2 result values.
- 8 exception classes.
- 3 environments.
- 10 pod instances.

Tổng tổ hợp lý thuyết có thể lên tới 20 × 2 × 8 × 3 × 10 = 9.600 series, trước histogram buckets. Thực tế các tổ hợp xuất hiện không nhất thiết đầy đủ nhưng chi phí có thể đáng kể.

Nếu thêm orderId làm tag có hàng triệu giá trị, cardinality có thể bùng nổ.

### 16.1 Quy tắc tags là bounded dimensions

Tags hợp lý:

- service: orders-worker.
- environment: prod.
- listener: orders-projection.
- topic: orders.created, khi tập topics hữu hạn.
- result: success/failure.
- exception category hoặc class có giới hạn.

Tags không phù hợp:

- raw exception message.
- business entity ID.
- event UUID.
- offset.
- Kafka message key có số lượng lớn.
- user email, phone, JWT, token.

### 16.2 Dùng MeterFilter khi cần

Micrometer hỗ trợ MeterFilter để chặn hoặc chuyển đổi meters/tags theo policy của registry. Ví dụ có thể giới hạn số tag values được phép cho một tag trong một meter.

~~~java
@Bean
MeterFilter kafkaListenerCardinalityGuard() {
    return MeterFilter.maximumAllowableTags(
        "spring.kafka.listener",
        "name",
        100,
        MeterFilter.deny()
    );
}
~~~

Đây là guard minh họa; không thay thế thiết kế naming đúng. Nếu ngưỡng 100 bị vượt, những series mới có thể bị deny, làm dashboard thiếu dữ liệu. Cần metric/alert cho việc vượt cardinality budget và quyết định limit dựa trên số listeners thực tế.

### 16.3 Histogram làm tăng series

Histogram buckets nhân số lượng series theo tags. Nếu bật histogram cho mọi listener, mọi exception tag và mọi pod, chi phí có thể tăng mạnh.

Nên bật percentile histogram có chọn lọc, hoặc aggregate theo domain khi đủ đáp ứng SLO. Kiểm tra storage/cost trước khi rollout diện rộng.

## 17. Các cấu hình dễ gây hiểu nhầm

### 17.1 Bật listener timers nhưng không thấy metric

Có thể do:

- Chưa có Micrometer dependency phù hợp.
- Không có registry hoặc registry không được exporter sử dụng.
- Listener chưa từng nhận record hoặc chưa có invocation đo được.
- Container factory khác đang được listener sử dụng.
- micrometerEnabled=false bị customizer ghi đè.
- observationEnabled=true khiến instrumentation path thay đổi.
- MeterFilter loại bỏ hoặc đổi meter.
- Prometheus endpoint chưa expose/scrape.
- Query dùng nhầm logical meter name và Prometheus metric name.

### 17.2 Prometheus thấy metric nhưng không có histogram

Timer count/sum có thể hiện diện trong khi _bucket không xuất hiện vì histogram không được bật. Không nên cố tính p95 từ _sum/_count.

### 17.3 Metrics gắn name khác với @KafkaListener.id

Với concurrency lớn hơn một, name tag có thể phản ánh child containers. Hãy inspect /actuator/metrics/spring.kafka.listener và các tags thực tế trước khi viết dashboard regex.

### 17.4 Listener timer failure thấp nhưng DLT tăng

Deserialization có thể lỗi trước listener, hoặc retry/recovery được thực hiện ở tầng container. Timer không đủ để phản ánh các trường hợp đó. Cần DLT publisher metric riêng.

### 17.5 Listener timer success cao nhưng DB không có dữ liệu

Listener có thể bắt rồi nuốt exception, gửi async tasks và return trước khi hoàn tất, hoặc transaction rollback sau invocation. Cần business counters, transaction result và test lifecycle.

### 17.6 Tắt micrometerEnabled và tưởng tắt toàn bộ Kafka metrics

Kafka client metrics hoặc custom meters vẫn có thể tồn tại. Nếu bật Observation, vẫn có thể có metrics từ ObservationRegistry. Phải phân biệt instrumentation nguồn nào tạo meter.

## 18. Lựa chọn tags cho exception

Một failure timer có thể mang exception class đơn giản, ví dụ:

~~~text
exception=TransientDataAccessException
exception=IllegalArgumentException
exception=SerializationException
~~~

Điều này giúp phân nhóm lỗi, nhưng không phải mọi failure đều đến từ listener. Nên kết hợp root-cause analysis với logs.

Một wrapper như ListenerExecutionFailedException có thể xuất hiện tùy tầng bắt lỗi và implementation. Không khẳng định tag exception luôn là root cause thực sự nếu chưa kiểm tra metric output theo version.

Nếu ứng dụng có hàng trăm exception subclasses, tag exception có thể làm cardinality tăng. Có thể phân loại lỗi thành các nhóm ổn định trong custom metric:

~~~text
error_class=transient_dependency
error_class=invalid_data
error_class=business_conflict
error_class=unexpected
~~~

Đừng đưa exception.getMessage() vào tag; message thường chứa dynamic IDs, URLs hoặc dữ liệu nhạy cảm.

### 18.1 Có thể dùng custom Listener Error metrics

Ví dụ ở service:

~~~java
public class OrderProcessingMetrics {

    private final MeterRegistry registry;

    public OrderProcessingMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordFailure(String category) {
        registry.counter(
            "orders.processing.failure",
            "category", category
        ).increment();
    }
}
~~~

category phải đến từ một enum/tập values hữu hạn do ứng dụng định nghĩa. Không truyền raw exception class/message tùy ý nếu không có chính sách cardinality.

## 19. Thiết kế dashboard có ích cho vận hành

Một dashboard listener tốt nên gồm bốn nhóm:

**Nhóm xử lý:** listener invocation throughput, success/failure rate, average duration, p95/p99 khi histogram available.

**Nhóm consumer:** group lag theo partition, poll/rebalance events, pause state, assignment, records consumed rate.

**Nhóm recovery:** retry attempts, retry exhausted, recoverer failures, DLT publish rate và DLT oldest age.

**Nhóm business:** số events hợp lệ, số events đã áp dụng business effect, duplicate detection, end-to-end age và SLA breaches.

### 19.1 Ví dụ panel

| Panel | Dữ liệu | Câu hỏi |
|---|---|---|
| Orders listener attempts/s | spring.kafka.listener timer count | Listener có xử lý không? |
| Orders listener p95 | Timer histogram | Listener đang chậm hơn bình thường? |
| Failure ratio by listener | result=failure | Listener nào có lỗi? |
| Consumer lag by partition | Group lag metrics | Topic/partition nào bị backlog? |
| Pause duration | Container pause events/metric | Có bị backpressure kéo dài? |
| Retry exhausted | Error handler metric | Record có chuyển sang recovery không? |
| DLT publish failures | Recoverer/producer metric | Record lỗi có được quarantine bền vững? |
| Business completion age | Application instrumentation | SLA nghiệp vụ có đạt không? |

### 19.2 Không alert chỉ từ một metric

Listener success throughput = 0 trong một khoảng có thể do topic không có record mới. Không nên báo outage nếu producer rate cũng bằng 0 và lag bằng 0.

Một alert có ý nghĩa hơn:

~~~text
Consumer lag đang tăng
AND producer rate > 0
AND listener completion throughput thấp
FOR một khoảng thời gian đủ dài
~~~

Nếu đồng thời có error rate cao hoặc pause duration kéo dài, alert có thêm ngữ cảnh nguyên nhân.

## 20. Một cấu hình Spring Boot thực hành

Giả sử ứng dụng dùng Spring Boot Actuator và Prometheus:

~~~groovy
dependencies {
    implementation("org.springframework.kafka:spring-kafka")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-registry-prometheus")
}
~~~

Listener factory:

~~~java
@Configuration
public class KafkaMetricsConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(2);

        ContainerProperties props =
            factory.getContainerProperties();

        props.setMicrometerEnabled(true);
        props.setObservationEnabled(false);

        props.setMicrometerTags(
            Map.of(
                "domain", "orders",
                "pipeline", "projection"
            )
        );

        return factory;
    }
}
~~~

Prometheus exposure qua Actuator cần được cấu hình theo Spring Boot version và được bảo vệ. Một quy trình kiểm tra hiệu quả:

1. Start application với Kafka và một producer test.
2. Gửi một vài orders records.
3. Đợi listener thực sự được gọi.
4. Kiểm tra /actuator/metrics/spring.kafka.listener.
5. Kiểm tra /actuator/prometheus có series tương ứng.
6. Kiểm tra monitoring target đã scrape.
7. Phân nhóm theo name/result/exception và các tags custom.
8. Dùng một test failure có kiểm soát để xem metric result=failure.
9. Đảm bảo dashboard không đếm nhầm retries là unique records.

### 20.1 Không expose Actuator không bảo vệ

Prometheus endpoint và metrics endpoint có thể tiết lộ service names, internal endpoints, exception classes, topology hoặc runtime details. Production cần:

- Network segmentation hoặc service mesh policy.
- Authentication/authorization phù hợp.
- Chỉ expose endpoints cần thiết.
- Kiểm soát raw tag values.
- Không đưa PII vào tags.
- Giám sát scrape load và cardinality.

Metrics collection cũng là một phần của hệ thống vận hành cần security.

## 21. Kiểm thử micrometerEnabled bằng integration test

Unit test gọi trực tiếp method annotated @KafkaListener không đi qua Spring Kafka listener container, nên không kiểm chứng timer instrumentation của container.

Nên dùng Embedded Kafka hoặc Testcontainers Kafka, một Spring ApplicationContext thực và MeterRegistry có thể inspect.

### 21.1 Test thành công

1. Cấu hình listener factory với micrometerEnabled=true.
2. Tạo một MeterRegistry cho test, ví dụ SimpleMeterRegistry.
3. Gửi một record hợp lệ.
4. Đợi @KafkaListener xử lý record thật sự.
5. Tìm meter spring.kafka.listener trong registry theo tags thực tế.
6. Xác nhận invocation count tăng.
7. Xác nhận duration có giá trị hợp lệ.
8. Không assert chính xác latency từng millisecond, vì CI có scheduler jitter.

### 21.2 Test thất bại

1. Gửi record kích hoạt listener ném exception.
2. Cấu hình retry/recovery hữu hạn để test không kẹt.
3. Đợi handler/recovery hoàn tất.
4. Xác nhận failure timer được ghi nhận theo kết quả thực tế.
5. Đối chiếu số attempts với retry policy.
6. Không kết luận DLT thành công chỉ vì failure timer tăng.

### 21.3 Test tắt micrometerEnabled

1. Dùng một factory riêng đặt setMicrometerEnabled(false).
2. Gửi records qua listener đó.
3. Xác nhận các listener timers truyền thống không được ghi cho factory đã tắt, theo registry/test setup.
4. Xác nhận custom metrics hoặc Kafka client metrics có thể vẫn tồn tại nếu được bật độc lập.

Nếu dùng Observation, cần kiểm tra instrumentation path riêng, tránh kết luận sai do một metric cùng tên vẫn được tạo bởi Observation.

### 21.4 Test tags tĩnh

1. Bật setMicrometerTags với domain=orders.
2. Gửi một record.
3. Kiểm tra meter có tag domain=orders.
4. Xác nhận các listener khác không bị gắn nhầm tag.
5. Kiểm tra tên child container khi concurrency>1.

### 21.5 Test cardinality

1. Đưa nhiều record với eventId khác nhau.
2. Xác nhận số meter series không tăng theo eventId.
3. Nếu dùng micrometerTagsProvider, kiểm tra các tags thuộc whitelist.
4. Đo memory footprint của registry dưới tải.
5. Xác nhận giới hạn series phù hợp với metrics backend.

### 21.6 Test retry và batch

- Record listener retry hai lần: timer count có thể phản ánh nhiều invocations.
- Batch listener một invocation chứa nhiều records: timer count không đồng nghĩa record count.
- Lỗi deserialization trước listener: xem error metrics và DLT riêng.
- Transaction abort sau listener return: theo dõi transaction outcome, không chỉ timer success.

## 22. Mẫu integration test với SimpleMeterRegistry

Một test có thể tạo MeterRegistry để đọc metrics do ứng dụng xuất. Khi dùng Spring Boot, phải để **registry mà listener instrumentation sử dụng** thực sự liên kết với registry kiểm thử. Nếu Spring Kafka version dùng global Micrometer registry, cấu hình test cần kết nối hoặc làm sạch global registry đúng cách.

Ví dụ ý tưởng về assertions:

~~~java
@Test
void listenerTimerShouldRecordSuccessfulInvocation() {
    // Arrange: application context với Micrometer registry
    // và Kafka listener container thật.

    producer.send("orders", "order-1001", validOrderPayload);

    await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() -> {

            Timer timer = registry.find("spring.kafka.listener")
                .tag("result", "success")
                .timer();

            assertThat(timer).isNotNull();
            assertThat(timer.count()).isGreaterThan(0);
        });
}
~~~

Đây là pseudocode định hướng; cần bổ sung producer setup, @SpringBootTest/Testcontainers, các imports, và tags thực tế phù hợp version. Không copy nguyên một snippet rồi kỳ vọng compile nếu application chưa có producer, registry hoặc listener factory.

### 22.1 Không để test dùng global registry bẩn

Nếu tests chạy trong một JVM và cùng dùng Metrics.globalRegistry, meters từ test trước có thể làm test sau pass giả hoặc fail ngẫu nhiên.

Có thể:

- Tạo SimpleMeterRegistry riêng.
- Register/unregister registry đúng lifecycle.
- Dùng unique listener IDs/topics cho tests.
- Đọc baseline count trước khi gửi record.
- Assert **delta count** thay vì chỉ count > 0.
- Cleanup listeners/registry sau test.

### 22.2 Assertions nên đo behavior chứ không hardcode tags sai

Nếu concurrent container gắn name là orders-projection-0 thay vì orders-projection, assertion equality theo parent ID có thể fail dù instrumentation hoạt động đúng.

Trước tiên inspect registry meter IDs và tags trong test, sau đó chọn predicate tương ứng với naming convention/version. Điều này cũng quan trọng khi monitoring query ở production.

## 23. Triệu chứng “không có metric spring.kafka.listener”

Khi dashboard không thấy data:

1. Xác nhận listener đã nhận và xử lý record thật, không chỉ container RUNNING.
2. Xác nhận @KafkaListener đang dùng containerFactory nào.
3. Kiểm tra ContainerProperties.micrometerEnabled của factory/container hiệu lực.
4. Kiểm tra Micrometer dependency có trên runtime classpath.
5. Kiểm tra observationEnabled vì nó có thể thay đổi instrumentation.
6. Xác nhận MeterRegistry tồn tại và exporter đã được kích hoạt.
7. Kiểm tra Actuator endpoint metrics có thấy logical meter không.
8. Kiểm tra endpoint prometheus có thấy exported series không.
9. Kiểm tra scrape target, network/security và Prometheus last scrape.
10. Kiểm tra MeterFilter, common tags và naming convention.
11. Kiểm tra có tags khác giả định, nhất là name child suffix.
12. Gửi một record test để tạo invocation mới, đối chiếu count delta.

Không bật log DEBUG toàn bộ Kafka client chỉ để tìm một metric; hãy tách **instrumentation**, **registry**, **exporter**, **scrape** để khoanh vùng.

## 24. Triệu chứng “timer rất nhanh nhưng nghiệp vụ chậm”

Ví dụ timer p95 chỉ 10 ms, nhưng order projection hoàn tất sau 30 giây.

Có thể:

- Listener submit job async rồi return.
- Kafka lag khiến event chờ lâu trước khi listener được gọi.
- Business transaction commit sau listener method.
- Retry/backoff và DLT là phần lớn total latency.
- Consumer chỉ đo invocation, không đo downstream completion.
- Timing metrics bị trộn giữa listener khác hoặc batch processing.
- Một số lỗi xảy ra trước listener nên không xuất hiện ở timer.

Quy trình:

1. Xác định eventId và thời điểm Kafka append.
2. Xác định listener start và end.
3. Xác định business side effect complete timestamp.
4. Kiểm tra lag/pause/retry.
5. Kiểm tra async executor queue.
6. Xác định timer đang đo đúng listener hay không.
7. Thêm business completion metric hoặc tracing span phù hợp.

Không cố ép micrometerEnabled đo những giai đoạn nằm ngoài scope của listener timer.

## 25. Triệu chứng “metrics tăng nhiều hơn số records”

Nếu listener timer count lớn hơn số records được producer gửi, điều đó có thể là bình thường vì:

- Blocking retries gọi listener nhiều lần.
- Consumer restart sau side effect nhưng trước offset commit.
- Group rebalance khiến record được redeliver.
- Manual ack chưa hoàn tất.
- Batch retry chạy lại một tập records.
- Nhiều listeners cùng subscribe topic trong các groups khác nhau.
- Một dashboard cộng cả success/failure attempts.

Muốn đo unique records, cần eventId hoặc topic-partition-offset với deduplication semantics thích hợp, nhưng **không dùng eventId làm metric tag**. Có thể cập nhật một business completion counter chỉ khi idempotent storage xác nhận event chưa từng được xử lý.

## 26. Khi nào nên tắt micrometerEnabled?

Có một vài tình huống hợp lý:

- Workload đã dùng Micrometer Observation và đang migrate metrics.
- Tracing/Observation đã cung cấp dữ liệu cần thiết, muốn tránh trùng timer.
- Một listener chuyên dụng có traffic rất cao, instrumentation cost cần giảm có đo lường.
- Monitoring backend đang gặp cardinality explosion do tags/naming.
- Muốn tạm biệt lập một nhóm listener khỏi timer tự động để đo bằng instrumentation khác.

Tuy nhiên, không nên tắt chỉ vì metric “có nhiều lỗi”. Tắt metric khiến mất tín hiệu, không làm lỗi nghiệp vụ biến mất.

Trước khi tắt, cần:

1. Xác định dashboard/alerts nào phụ thuộc spring.kafka.listener.
2. Xác nhận metrics thay thế đã hoạt động.
3. Đo chi phí instrumentation nếu lý do là performance.
4. Thông báo thay đổi metric schema cho vận hành.
5. Thử trên staging/canary.
6. Theo dõi sau rollout.

## 27. Khuyến nghị triển khai theo từng giai đoạn

Một cách triển khai có kiểm soát:

### Giai đoạn 1: listener timers

Bật micrometerEnabled ở factory cần đo, xác nhận timer count và duration đi qua MeterRegistry. Dùng tags tĩnh có cardinality thấp.

### Giai đoạn 2: consumer/client metrics

Bổ sung Kafka client metrics và lag monitoring. Đảm bảo các dashboard phản ánh group, topic và partitions.

### Giai đoạn 3: error and recovery

Đo retries, DLT publish outcome, deserialization errors, commit failures và rebalance. Phân biệt listener failure với final business outcome.

### Giai đoạn 4: end-to-end SLO

Instrument event age, business completion, duplicate detection, offset progression. Dùng alert theo SLO thay vì chỉ một threshold listener latency.

### Giai đoạn 5: tracing khi cần

Nếu cần correlation producer-consumer hoặc cross-service tracing, đánh giá observationEnabled và Micrometer Tracing. Lập kế hoạch migration metrics/tags để không phá dashboard cũ.

Không cần triển khai tất cả trong một lần. Nhưng cần xác định ranh giới mỗi lớp để không đưa ra kết luận sai từ một metric đơn lẻ.

## 28. Các hiểu nhầm thường gặp

**“micrometerEnabled=true tự bật Prometheus.”** Không. Cần registry/exporter, Actuator endpoint và scrape config.

**“micrometerEnabled mặc định false.”** Không nhất thiết. Trong các dòng hỗ trợ listener timers, default thường true khi Micrometer sẵn sàng.

**“Timer count là số unique Kafka records.”** Không. Retries/redeliveries có thể tăng count; batch listener count là số invocations.

**“Timer success nghĩa offset đã commit.”** Không. Listener invocation thành công khác commit/transaction outcome.

**“Timer failure bằng số records vào DLT.”** Không. Retry attempts và recovery khác nhau.

**“Timer đo luôn Kafka lag.”** Không. Lag cần Kafka client/broker/group monitoring.

**“Bật Observation và Timer sẽ luôn có hai bộ metrics giống nhau.”** Không. Framework có thể tắt timer truyền thống khi Observation được bật; cần inspect thực tế.

**“Tắt micrometerEnabled làm mọi Kafka metrics biến mất.”** Không. Client metrics và custom metrics độc lập.

**“Một record batch = một timer count.”** Không. Một batch invocation có thể chứa nhiều records.

**“Listener xử lý async sẽ được Timer đo tới lúc task hoàn tất.”** Không mặc định nếu method return trước task completion.

**“Gắn eventId vào tag giúp theo dõi chính xác hơn.”** Rất rủi ro. Nó tạo high-cardinality metrics; dùng logs/traces hoặc storage khác.

**“Đã có p95 timer là đủ cho SLO end-to-end.”** Không. Phải tính thời gian records nằm chờ trong Kafka, retry và downstream completion.

**“Mọi lỗi deserialization sẽ được timer ghi.”** Không. Một số lỗi xảy ra trước listener invocation.

**“Không thấy metric chứng minh listener không chạy.”** Không. Có thể là lỗi registry, exporter, scraping, filter hoặc cấu hình.

## 29. Checklist triển khai và vận hành

**Cấu hình container**

- [ ] Xác định đúng ConcurrentKafkaListenerContainerFactory của mỗi @KafkaListener.
- [ ] Biết effective micrometerEnabled và observationEnabled.
- [ ] Micrometer dependency và MeterRegistry hiện diện.
- [ ] Không tạo trùng instrumentation do auto-configuration và custom wiring.
- [ ] Có naming convention cho parent/child listener IDs.
- [ ] Có sự phân biệt record vs batch listener khi đọc count.

**Metrics và tags**

- [ ] Xác nhận meter spring.kafka.listener được ghi trong registry.
- [ ] Kiểm tra actual tags name/result/exception theo framework version.
- [ ] Tags tĩnh/dynamic có cardinality hữu hạn.
- [ ] Không gắn eventId, orderId, offset hoặc PII vào metric tags.
- [ ] Bật histogram có chọn lọc khi cần p95/p99.
- [ ] Prometheus scrape có security và resource budget phù hợp.

**Reliability**

- [ ] Không coi listener success là business commit success.
- [ ] Có monitoring retry, DLT, deserialization và transaction failures.
- [ ] Có Kafka client metrics và consumer lag monitoring.
- [ ] Có idempotency/business completion metrics khi cần.
- [ ] Có SLO end-to-end về event age hoặc business completion.
- [ ] Alerts có điều kiện về traffic, lag và thời gian để giảm false positives.

**Verification**

- [ ] Đã kiểm thử timer success/failure với container thật.
- [ ] Đã kiểm thử micrometerEnabled=false.
- [ ] Đã kiểm thử static tags và concurrency child suffix.
- [ ] Đã kiểm thử retry count khác unique record count.
- [ ] Đã kiểm thử batch invocation count.
- [ ] Đã kiểm thử registry/exporter/scrape end-to-end.
- [ ] Đã kiểm tra tác động của observationEnabled khi migration.
- [ ] Đã đo cardinality và histogram overhead dưới tải.

## 30. Kết luận

**micrometerEnabled** là công tắc cho **Micrometer listener timers** của Spring Kafka. Khi bật và có Micrometer được cấu hình đúng, nó giúp đo số lần listener được gọi, thời gian invocation và phân biệt kết quả success/failure theo tags. Đây là một lớp quan sát quan trọng để phát hiện listener chậm hoặc ném exception nhiều, nhưng **không tự đo consumer lag, không bảo đảm offset đã commit và không chứng minh nghiệp vụ hoàn tất chính xác một lần**.

Một triển khai production cần phân biệt Timer với Kafka client metrics, business metrics và Micrometer Observation; bảo vệ metric cardinality; cấu hình registry/exporter đúng; và kiểm chứng các kết quả trong môi trường có Kafka listener container thực. Đặt micrometerEnabled đúng factory là bước đầu, còn khả năng vận hành đáng tin cậy đến từ việc kết hợp listener timing với lag, retry, DLT, transaction outcome và end-to-end SLO.


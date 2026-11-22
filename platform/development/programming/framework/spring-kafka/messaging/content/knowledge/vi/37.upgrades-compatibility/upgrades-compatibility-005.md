# Migration từ cấu hình cũ

Một ứng dụng Spring Kafka có thể đã chạy ổn định nhiều năm với XML bean, Java configuration tự viết, Kafka client properties cũ hoặc các API xử lý lỗi đã được thay thế. Khi nâng cấp Spring Boot, Spring Kafka hoặc Kafka client, việc chỉ đổi version dependency có thể khiến ứng dụng không compile, gửi/nhận record khác hành vi hoặc thay đổi cách retry và commit offset.

Migration an toàn bắt đầu bằng việc kiểm kê cấu hình và hành vi hiện tại, sau đó nâng cấp từng lớp có kiểm soát. Cần giữ tương thích giữa producer, consumer, topic, event contract và consumer group trong suốt thời gian triển khai nhiều phiên bản. Đặc biệt, không được xem việc ứng dụng khởi động thành công là bằng chứng rằng dữ liệu vẫn được xử lý đúng.

Bài học thuộc chương **Nâng cấp và tương thích** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách chuyển cấu hình Spring Kafka cũ sang cấu hình hiện đại hơn, nhận diện các thay đổi API thường gặp và triển khai migration có thể kiểm chứng, rollback.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Kiểm kê cấu hình Spring Kafka cũ trước khi nâng cấp.
- Chọn version Spring Boot, Spring Kafka, Kafka client và Java tương thích.
- Chuyển cấu hình XML hoặc Java config rời rạc sang cấu hình tập trung.
- Hiểu thay đổi API của `KafkaTemplate.send()` giữa các thế hệ Spring Kafka.
- Chuyển error handler cũ sang `CommonErrorHandler` và `DefaultErrorHandler`.
- Rà soát retry, DLT, acknowledgment và offset commit sau migration.
- Cập nhật serializer/deserializer, type header và trusted packages.
- Giữ đúng transaction, idempotence và isolation level.
- Bảo toàn consumer group và committed offset.
- Thực hiện rolling deployment, canary, rollback và kiểm thử tương thích.

## 1. Migration là thay đổi hành vi, không chỉ đổi dependency

Một ứng dụng Spring Kafka gồm nhiều lớp phụ thuộc:

~~~text
Spring Boot
    |
    v
Spring Kafka
    |
    v
Apache Kafka client
    |
    v
Kafka broker / cluster
    |
    +---- topic / partition / consumer group
    |
    +---- event contract / serializer
    |
    +---- retry / DLT / transaction
~~~

Nâng cấp một lớp có thể ảnh hưởng lớp khác. Ví dụ:

- Spring Boot nâng version có thể kéo theo Spring Framework, Spring Kafka và Kafka client version khác.
- Spring Kafka thay API future của KafkaTemplate có thể làm code callback không compile.
- Error handler mới có thể thay đổi cách seek, retry và commit offset.
- JsonDeserializer có thể áp dụng type header hoặc trusted package khác với cấu hình cũ.
- Kafka client mới có thể có default hoặc validation khác về producer idempotence, timeout và consumer group.
- Broker upgrade có thể ảnh hưởng protocol, transaction coordinator hoặc group behavior.

Vì vậy, cần xác định cả compile compatibility, runtime compatibility và data compatibility.

## 2. Kiểm kê cấu hình hiện tại

Trước khi sửa code, lập inventory các thành phần đang được sử dụng.

| Khu vực | Cần ghi nhận |
|---|---|
| Dependency | Spring Boot, Spring Kafka, kafka-clients, Java và dependency management. |
| Producer | Bootstrap servers, serializers, acks, retries, idempotence, batching, transaction ID. |
| Consumer | Group ID, deserializers, auto commit, AckMode, concurrency, poll settings. |
| Listener | `@KafkaListener`, container factory, method signature, batch/record mode. |
| Error handling | ErrorHandler, CommonErrorHandler, retry policy, recoverer và DLT. |
| Serialization | JSON type headers, mappings, trusted packages, schema registry. |
| Transaction | KafkaTransactionManager, transaction ID prefix, isolation level. |
| Topic | Partition count, replication factor, retention, min ISR và DLT topology. |
| Security | SASL, TLS, JAAS, ACL và secret source. |
| Observability | Logs, metrics, tracing, consumer lag và alert. |
| Tests | EmbeddedKafka/Testcontainers, group ID, offset assumptions và DLT assertions. |

Với mỗi cấu hình, ghi rõ giá trị hiện tại, nơi khai báo, bean nào sử dụng và hành vi mong đợi. Cùng một thuộc tính có thể xuất hiện ở application YAML, Java bean, environment variable và custom factory; cần xác định giá trị cuối cùng mà Kafka client nhận.

Không bắt đầu bằng việc xóa toàn bộ cấu hình cũ. Trước hết phải biết cấu hình nào còn hiệu lực và cấu hình nào chỉ là phần dư.

## 3. Xác định version matrix trước khi nâng cấp

Spring Boot quản lý nhiều dependency thông qua dependency management. Spring Kafka và Kafka client cần được chọn theo ma trận tương thích của phiên bản Boot/Spring Kafka mà dự án hướng tới.

Trước khi nâng cấp, xác minh:

- Phiên bản Java tối thiểu mà Spring Boot và Spring Kafka mục tiêu yêu cầu.
- Spring Kafka version được Spring Boot quản lý.
- Kafka client version được dependency management chọn.
- Broker version và protocol compatibility.
- Các thư viện serializer, schema registry và test container có tương thích.
- Plugin build, test framework và observability exporter có tương thích.

Không override `spring-kafka` hoặc `kafka-clients` version tùy tiện chỉ để dùng một API mới. Nếu cần override, phải có lý do, kiểm tra release notes và test với broker thật tương ứng.

Với migration Spring Boot 2 sang 3, cần tính cả yêu cầu Java mới và thay đổi hệ sinh thái Jakarta trong ứng dụng. Đây là migration nền tảng rộng hơn Kafka; không nên gộp quá nhiều thay đổi không liên quan vào một lần deploy nếu chưa có test coverage phù hợp.

## 4. Dùng dependency management thay vì khai báo version rời rạc

Ví dụ Maven với Spring Boot parent hoặc BOM:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>${spring-boot.version}</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>
</dependencies>
~~~

Với Spring Boot, dependency thường dùng là `org.springframework.kafka:spring-kafka`; Spring Boot dependency management sẽ quản lý version khi dùng parent/BOM tương ứng. Hãy xác minh artifact và version trong dependency catalog của phiên bản dự án.

Nếu không dùng parent, import Spring Boot dependency BOM trong `dependencyManagement`. Tránh khai báo version khác nhau cho Spring Kafka và Kafka client nếu không có kiểm tra tương thích rõ ràng.

Sau khi nâng dependency, kiểm tra dependency tree để phát hiện nhiều phiên bản Kafka client hoặc Spring Kafka cùng xuất hiện. Một classpath có version conflict có thể compile nhưng lỗi runtime bằng `NoSuchMethodError`, `ClassNotFoundException` hoặc linkage error.

## 5. Chuyển cấu hình XML sang Java configuration hoặc Spring Boot properties

Ứng dụng cũ có thể khai báo producer factory, consumer factory, KafkaTemplate và listener container factory trong XML. Ứng dụng mới có thể dùng Spring Boot auto-configuration kết hợp application YAML.

Ví dụ cấu hình producer/consumer cơ bản:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
    consumer:
      group-id: orders-fulfillment
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.acme.orders.contract
~~~

Đây là cấu hình minh họa. Các property cần được đối chiếu với phiên bản Spring Boot mục tiêu và serializer thực tế.

Khi dùng Boot auto-configuration, không cần tự tạo mọi bean nếu cấu hình mặc định đã đáp ứng yêu cầu. Nếu khai báo custom ProducerFactory, ConsumerFactory hoặc KafkaTemplate, hãy xác minh bean đó có nhận đủ Boot properties hay không; custom bean không tự động kế thừa mọi cấu hình mà bạn không truyền vào.

## 6. Khi nào cần giữ custom ProducerFactory và ConsumerFactory?

Custom factory vẫn cần thiết khi ứng dụng có nhiều Kafka cluster, nhiều principal, serializer khác nhau hoặc các consumer group có chính sách riêng.

Ví dụ tạo ConsumerFactory bằng properties:

~~~java
@Bean
ConsumerFactory<String, OrderCreatedEvent> orderConsumerFactory(
        KafkaProperties kafkaProperties,
        SslBundles sslBundles) {

    Map<String, Object> properties =
            new HashMap<>(kafkaProperties.buildConsumerProperties(sslBundles));

    properties.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "orders-fulfillment"
    );

    return new DefaultKafkaConsumerFactory<>(properties);
}
~~~

API của `KafkaProperties.buildConsumerProperties()` có thể nhận thêm tham số hoặc thay đổi theo phiên bản Spring Boot. Khi migration, dùng đúng signature trong version mục tiêu thay vì sao chép ví dụ từ phiên bản khác.

Nếu nhiều factory dùng chung bootstrap server nhưng khác group ID hoặc deserializer, hãy đặt tên bean rõ ràng và gắn đúng `containerFactory` cho từng listener. Tránh tạo factory trùng nhau nhưng cấu hình khác biệt không được tài liệu hóa.

## 7. Migration KafkaTemplate.send(): ListenableFuture sang CompletableFuture

Một thay đổi đáng chú ý trong Spring Kafka 3.0 là API `KafkaTemplate.send()` chuyển từ `ListenableFuture` sang `CompletableFuture`.

Mã cũ có thể dùng callback Spring:

~~~java
ListenableFuture<SendResult<String, OrderCreatedEvent>> future =
        kafkaTemplate.send(topic, event.orderId(), event);

future.addCallback(
        result -> log.info("Sent"),
        error -> log.error("Send failed", error)
);
~~~

Ở Spring Kafka 3.x, dùng `CompletableFuture`:

~~~java
CompletableFuture<SendResult<String, OrderCreatedEvent>> future =
        kafkaTemplate.send(topic, event.orderId(), event);

future.whenComplete((result, error) -> {
    if (error == null) {
        log.info(
                "Sent topic={}, partition={}, offset={}",
                result.getRecordMetadata().topic(),
                result.getRecordMetadata().partition(),
                result.getRecordMetadata().offset()
        );
    } else {
        log.error("Send failed", error);
    }
});
~~~

Các lựa chọn khác gồm `thenApply`, `thenCompose`, `exceptionally` hoặc `handle`. Hãy xử lý exception từ future; nếu bỏ qua future, lỗi publish có thể không được quan sát ở đúng nơi.

Không chặn thread bằng `get()` trong request path nếu không cần thiết. Nếu nghiệp vụ cần xác nhận broker trước khi trả kết quả, dùng timeout hữu hạn và xử lý timeout/failure rõ ràng. Callback nên ngắn và không thực hiện công việc blocking nặng.

## 8. Migration error handler cũ sang CommonErrorHandler

Các phiên bản Spring Kafka cũ có thể sử dụng `ErrorHandler`, `BatchErrorHandler` hoặc `SeekToCurrentErrorHandler`. Trong các phiên bản mới hơn, mô hình `CommonErrorHandler` hợp nhất xử lý lỗi cho record và batch listener; `DefaultErrorHandler` là implementation phổ biến.

Ví dụ cấu hình:

~~~java
@Bean
CommonErrorHandler commonErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Gắn vào factory:

~~~java
factory.setCommonErrorHandler(commonErrorHandler);
~~~

Cần đối chiếu constructor, package và API của version mục tiêu. Nếu dự án cũ đang custom seek/retry behavior, không thay bằng DefaultErrorHandler mặc định mà chưa viết lại semantics mong muốn.

Kiểm tra:
- Exception nào retry và exception nào không retry.
- Số lần retry và backoff.
- Khi nào seek partition và redeliver.
- Khi nào recover sang DLT.
- Offset được commit khi recover như thế nào.
- Batch listener có semantics khác record listener không.
- Recoverer publish DLT có serializer và destination đúng không.

## 9. Migration retry và DLT

Retry có thể được triển khai bằng blocking retry trong error handler hoặc non-blocking retry topics. Đây là hai mô hình khác nhau và không thể đổi qua lại chỉ bằng thay một annotation.

Với blocking retry, consumer có thể tạm dừng tiến độ partition trong thời gian backoff/retry. Với retry topic, record được chuyển qua các topic retry theo lịch và có thể thay đổi ordering tương đối giữa các event.

Khi migration, ghi lại:

- Số lần thử và backoff.
- Exception classification.
- Tên retry topic và DLT.
- Partition count/replication/retention của retry topics.
- DLT header và metadata gốc.
- Cách replay và quyền sở hữu record lỗi.
- Ordering guarantee mà nghiệp vụ đang dựa vào.

Nếu chuyển sang `@RetryableTopic`, xác minh phiên bản Spring Kafka hỗ trợ annotation và cấu hình phù hợp. Không bật cả retry topic và blocking retry cho cùng lỗi một cách vô tình, vì tổng số attempt và thời gian xử lý có thể khác xa dự kiến.

## 10. Rà soát AckMode và offset commit

Migration có thể vô tình thay đổi AckMode, `enable.auto.commit` hoặc transaction semantics. Điều này có thể dẫn tới duplicate hoặc mất record ở cấp ứng dụng.

Các AckMode thường gặp:

| AckMode | Ý nghĩa khái quát |
|---|---|
| RECORD | Commit sau khi từng record được xử lý thành công. |
| BATCH | Commit sau khi xử lý các record của poll batch. |
| TIME / COUNT | Commit theo thời gian hoặc số record, tùy cấu hình. |
| MANUAL | Listener chủ động acknowledge; container quản lý commit theo semantics manual. |
| MANUAL_IMMEDIATE | Acknowledge trên consumer thread có thể commit ngay. |

Không giả định default giữa các version hoặc custom factory là giống nhau. Hãy đọc cấu hình hiệu lực của từng container.

Khi migration:
1. Giữ nguyên group ID nếu muốn tiếp tục từ committed offset hiện tại.
2. Kiểm tra `enable.auto.commit` và AckMode.
3. Kiểm tra error handler có seek hoặc commit recovered offset.
4. Kiểm tra manual acknowledgment được gọi đúng thread.
5. Kiểm tra transaction commit và offset commit có cùng semantics như trước.
6. Test crash sau side effect nhưng trước commit để quan sát redelivery.

`auto.offset.reset` chỉ áp dụng khi group chưa có committed offset hợp lệ. Đổi giá trị này không tự reset offset của group đang hoạt động.

## 11. Migration serializer và deserializer

Cấu hình JSON cũ có thể phụ thuộc FQCN trong type header, trusted packages rộng hoặc default target type không rõ ràng. Khi nâng cấp, cần kiểm tra wire format thực tế.

Ví dụ dùng type mapping ổn định:

~~~yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.type.mapping: order-created:com.acme.orders.OrderCreated
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.type.mapping: order-created:com.acme.fulfillment.contract.OrderCreated
        spring.json.trusted.packages: com.acme.fulfillment.contract
~~~

Producer và consumer dùng class khác package nhưng chung token. Điều này giảm coupling vào FQCN; tuy nhiên payload JSON vẫn phải tương thích.

Nếu cần xử lý deserialize exception qua error handler, xem xét `ErrorHandlingDeserializer` bọc delegate deserializer phù hợp. Kiểm tra type headers, default type, trusted packages, header removal và schema compatibility.

Không thay serializer chỉ để làm code compile. Thay đổi serializer có thể thay đổi bytes trên Kafka và ảnh hưởng mọi consumer đang đọc topic.

## 12. Migration listener method và container factory

Listener cũ có thể dùng `@KafkaListener` với method signature đơn giản hoặc container factory tùy biến.

Ví dụ:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "${app.kafka.topics.orders}",
        groupId = "${spring.kafka.consumer.group-id}",
        containerFactory = "ordersKafkaListenerContainerFactory"
)
public void consume(ConsumerRecord<String, OrderCreatedEvent> record) {
    orderService.handle(record.value());
}
~~~

Kiểm tra method signature cũ:
- Payload object hay ConsumerRecord.
- Có nhận Acknowledgment không.
- Record listener hay batch listener.
- Có dùng Message<?> và message converter không.
- Có cần key, headers, partition, offset không.
- Có custom filter/interceptor không.
- Factory được chọn có đúng deserializer, error handler và AckMode không.

Nếu chuyển từ payload argument sang ConsumerRecord hoặc ngược lại, kiểm tra message conversion và listener adapter. Đừng giả định chỉ thay parameter type là tương đương.

## 13. Migration listener container factory

Factory thường gom các chính sách dùng chung cho listener. Khi nâng cấp, đối chiếu từng thuộc tính thay vì tạo factory mới theo ví dụ mặc định.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
        CommonErrorHandler commonErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(commonErrorHandler);
    factory.setConcurrency(3);

    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

Rà soát concurrency theo partition count và downstream capacity. Kiểm tra poll timeout, idle event, record filter, record interceptor, observation và shutdown behavior nếu ứng dụng đang dùng các tính năng đó.

Nếu factory cũ có custom properties được đặt sau khi bean tạo, bảo đảm migration vẫn áp dụng chúng trước khi container start.

## 14. Migration transaction và producer idempotence

Nếu ứng dụng dùng Kafka transactions, cần bảo toàn cấu hình producer transactional ID prefix, transaction manager và listener container transaction integration.

Ví dụ cấu hình Boot có thể khai báo:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${KAFKA_TRANSACTION_ID_PREFIX}
    consumer:
      properties:
        isolation.level: read_committed
~~~

Tên property và auto-configuration phụ thuộc Spring Boot version. Với custom ProducerFactory, kiểm tra transaction ID prefix được đặt trên factory và prefix là duy nhất giữa các application instance đang chạy đồng thời.

Khi migration:
- Xác minh transactional ID không bị trùng ngoài ý muốn.
- Kiểm tra KafkaTransactionManager và KafkaTemplate cùng dùng ProducerFactory phù hợp.
- Kiểm tra transaction timeout và listener processing duration.
- Giữ consumer `isolation.level=read_committed` nếu cần ẩn aborted transaction.
- Kiểm tra output record và consumed offset được commit trong cùng Kafka transaction khi dùng EOS.
- Nhớ rằng Kafka transaction không tự rollback database hoặc HTTP side effect.

Không bật transaction trong code mới mà chưa xác minh ACL cho transactional ID và recovery behavior.

## 15. Migration security properties

Các ứng dụng cũ có thể khai báo SASL/TLS trực tiếp trong Java properties hoặc file client riêng. Có thể chuyển sang Spring Boot configuration để quản lý tập trung:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="${KAFKA_USERNAME}"
        password="${KAFKA_PASSWORD}";
      ssl.truststore.location: ${KAFKA_TRUSTSTORE_PATH}
      ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
~~~

Nếu producer, consumer và AdminClient dùng principal khác nhau, khai báo properties riêng cho từng client. Không chuyển secret thật vào YAML được commit.

Sau migration, xác minh:
- Principal thực tế.
- ACL topic và group.
- TLS trust chain và hostname verification.
- Secret rotation có áp dụng cho client mới hay client đang chạy.
- Log không chứa JAAS/password/token.
- Negative test vẫn từ chối thao tác không được cấp quyền.

## 16. Giữ tương thích với consumer group và dữ liệu cũ

Consumer group là trạng thái bền vững trong Kafka. Việc đổi group ID tạo group mới, thường khiến ứng dụng bắt đầu theo `auto.offset.reset` nếu chưa có committed offset.

Trong migration, không đổi group ID chỉ để phân biệt release nếu mục tiêu là tiếp tục đọc từ vị trí hiện tại. Nếu cần chạy canary bằng group mới, hiểu rằng canary có thể đọc lại dữ liệu và tạo side effect trùng.

Trước khi rollout:
- Ghi lại group ID và committed offset theo partition.
- Xác định retention của topic có đủ cho thời gian migration không.
- Đảm bảo consumer mới đọc được record cũ còn tồn tại.
- Giữ event schema tương thích trong thời gian overlap.
- Xác định có cần pause, drain hoặc chuyển ownership không.
- Không reset offset để “làm sạch” migration nếu chưa có kế hoạch replay.

Offset là vị trí tiếp theo cần đọc; khi kiểm tra record cuối cùng đã xử lý, cần hiểu commit semantics và redelivery window.

## 17. Compatibility giữa producer và consumer

Producer và consumer có thể được deploy độc lập. Trong thời gian rolling deployment, các version khác nhau có thể cùng chạy và trao đổi record.

Ma trận compatibility cần đánh giá:

| Producer | Consumer | Câu hỏi cần kiểm tra |
|---|---|---|
| Cũ | Cũ | Baseline hiện tại có hoạt động đúng không? |
| Cũ | Mới | Consumer mới có đọc được payload cũ không? |
| Mới | Cũ | Consumer cũ có đọc được payload mới không? |
| Mới | Mới | Contract và behavior mới có đúng không? |

Các thay đổi dễ phá compatibility:
- Đổi field type hoặc format.
- Thêm enum value mà consumer cũ không biết.
- Đổi type header hoặc token.
- Thay serializer.
- Đổi key hoặc partitioning strategy.
- Đổi topic, group ID hoặc header semantics.
- Thay retry/DLT routing.
- Thay default value hoặc null handling.

Với mỗi thay đổi, xác định backward compatibility (consumer mới đọc data cũ), forward compatibility (consumer cũ đọc data mới) và full compatibility theo policy của event contract.

## 18. Chiến lược rolling migration

Một trình tự thường dùng:

1. Kiểm kê version, cấu hình và behavior hiện tại.
2. Nâng cấp code/consumer trước nếu consumer mới cần hỗ trợ payload mới.
3. Deploy consumer mới với khả năng đọc cả payload cũ và mới.
4. Xác minh group membership, assignment, offset và lag.
5. Deploy producer mới nhưng chưa phát thay đổi không tương thích.
6. Bật phát payload mới sau khi consumer tương thích đã sẵn sàng.
7. Theo dõi send errors, deserialization errors, retry, DLT và business state.
8. Chỉ bỏ hỗ trợ payload cũ sau khi thời gian overlap và retention đã được tính toán.

Nếu migration chỉ đổi API nội bộ nhưng wire format không đổi, vẫn cần canary để phát hiện behavior runtime như retry, acknowledgment và transaction.

Không chạy hai consumer group cùng xử lý side effect production chỉ để so sánh version nếu không có cơ chế shadow processing hoặc idempotency phù hợp.

## 19. Canary và feature flag cho thay đổi hành vi

Có thể dùng canary deployment hoặc feature flag để giới hạn phạm vi thay đổi, ví dụ:

- Chỉ một instance dùng error handler mới.
- Chỉ một producer route phát event contract mới.
- Một consumer group shadow đọc dữ liệu nhưng không tạo side effect.
- Bật serializer mới cho một topic test trước.
- Tăng concurrency theo từng bước.

Feature flag không tự giải quyết compatibility. Nếu hai phiên bản cùng ghi một topic, chúng vẫn phải tuân theo cùng wire contract hoặc consumer phải hỗ trợ cả hai.

Canary cần có metric riêng theo version/listener nhưng tránh label cardinality quá cao. Xác định trước điều kiện dừng: error rate, p99 latency, lag, DLT rate hoặc business invariant.

## 20. Rollback plan

Rollback không chỉ là deploy lại binary cũ. Nếu phiên bản mới đã ghi payload mới, tạo topic mới, thay đổi offset hoặc thay đổi side effect, code cũ có thể không đọc được trạng thái mới.

Trước migration, ghi rõ:
- Artifact/version cũ có thể redeploy.
- Cấu hình cũ và secret reference còn hợp lệ.
- Producer mới có phát wire format mà consumer cũ hiểu được không.
- Consumer group/offset có được giữ nguyên không.
- DLT/retry topics có thay đổi schema hoặc naming không.
- Database migration có backward-compatible không.
- Có cần dừng producer hoặc pause consumer trong rollback không.
- Cách xử lý record đã publish trong khoảng migration.

Rollback an toàn nhất khi wire contract và data format vẫn tương thích ngược. Nếu đã phát dữ liệu không tương thích, có thể cần forward fix hoặc compatibility adapter thay vì đơn giản quay về binary cũ.

## 21. Kiểm thử trước và sau migration

Một bộ test migration nên bao gồm:

| Nhóm test | Điều cần xác minh |
|---|---|
| Build/compile | API cũ đã được thay thế và dependency không conflict. |
| Producer | Send future, ack, error callback và serialization. |
| Consumer | Deserialization, listener invocation và group ID. |
| Offset | AckMode, manual ack, redelivery và committed offset. |
| Error handler | Retry count, backoff, recoverer và DLT. |
| Transaction | Commit, abort, fencing và read_committed. |
| Security | SASL/TLS, principal và ACL. |
| Compatibility | Producer cũ/mới với consumer cũ/mới. |
| Operations | Metrics, logs, lag, shutdown và rebalance. |
| Failure | Crash giữa side effect và offset commit, broker unavailable, dependency timeout. |

Dùng EmbeddedKafka cho test tích hợp nhanh và Testcontainers hoặc cluster integration cho behavior phụ thuộc broker/security/version. Unit test cho cấu hình không thay thế test end-to-end.

Khi kiểm thử offset, dùng group ID riêng cho test hoặc quản lý offset rõ ràng. Không để test phụ thuộc dữ liệu còn lại từ lần chạy trước.

## 22. Checklist migration theo từng giai đoạn

**Trước khi nâng cấp**

- [ ] Ghi lại Java, Spring Boot, Spring Kafka và Kafka client version.
- [ ] Lưu dependency tree và cấu hình hiệu lực.
- [ ] Ghi group ID, topic, partition và committed offset.
- [ ] Ghi AckMode, auto commit, retry, DLT và transaction behavior.
- [ ] Lưu baseline throughput, latency, lag và error rate.
- [ ] Xác định wire contract và serializer/deserializer.
- [ ] Chuẩn bị artifact và cấu hình rollback.

**Trong khi nâng cấp**

- [ ] Dùng dependency management tương thích.
- [ ] Sửa API compile-time như KafkaTemplate future.
- [ ] Chuyển error handler và retry theo semantics đã định.
- [ ] Giữ serializer, type mapping và header contract tương thích.
- [ ] Giữ group ID/offset nếu không có kế hoạch migration dữ liệu.
- [ ] Kiểm tra SASL/TLS/ACL và transaction.
- [ ] Deploy canary và quan sát metric.

**Sau khi nâng cấp**

- [ ] Producer send thành công.
- [ ] Consumer assignment ổn định.
- [ ] Offset tiến đúng theo AckMode.
- [ ] Retry/DLT hoạt động theo policy.
- [ ] Business state không thiếu hoặc duplicate ngoài dự kiến.
- [ ] Throughput, p95/p99 và lag trong ngưỡng.
- [ ] Logs/metrics không mất hoặc lộ secret.
- [ ] Runbook và tài liệu cấu hình đã cập nhật.

## 23. Những lỗi thường gặp khi migration

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ đổi dependency version | Runtime behavior có thể đổi mà không được kiểm tra | Lập version matrix và test từng lớp. |
| Override Kafka client tùy tiện | NoSuchMethodError hoặc protocol mismatch | Dùng Boot dependency management và kiểm tra dependency tree. |
| Giữ callback ListenableFuture ở API mới | Compile failure | Chuyển sang CompletableFuture API. |
| Đổi ErrorHandler nhưng không test seek/commit | Duplicate hoặc skip record | Kiểm tra retry, recoverer và offset semantics. |
| Đổi group ID trong rollout | Consumer bắt đầu từ offset khác | Giữ group ID hoặc lập kế hoạch replay rõ ràng. |
| Đổi serializer cùng lúc đổi schema | Consumer cũ không đọc được dữ liệu | Tách thay đổi và kiểm tra wire compatibility. |
| Mở trusted packages rộng | Tăng rủi ro deserialize class không mong muốn | Chỉ allowlist contract package cần thiết. |
| Bật transaction nhưng prefix trùng | Producer fencing | Tạo prefix duy nhất theo instance/lifecycle. |
| Chỉ test ứng dụng start | Bỏ sót lỗi xuất hiện khi gửi/consume | Gửi record thật và kiểm tra side effect/offset. |
| Rollback binary sau khi phát schema mới | Code cũ không đọc được record mới | Thiết kế backward-compatible rollout hoặc forward fix. |

## 24. Bài tập tổng hợp: migration Order Service

Giả sử Order Service đang dùng Spring Kafka cũ với XML config, callback ListenableFuture và SeekToCurrentErrorHandler. Mục tiêu là chuyển sang cấu hình Spring Boot, CompletableFuture và CommonErrorHandler.

Yêu cầu:

1. Ghi lại version Java, Boot, Spring Kafka và Kafka client.
2. Lập inventory producer, consumer, listener factory, serializer, transaction và security.
3. Chọn version matrix được quản lý bởi Boot BOM.
4. Chuyển bootstrap, serializer/deserializer và group ID sang cấu hình có kiểm soát.
5. Chuyển custom bean cần thiết sang Java config, loại bỏ bean trùng.
6. Chuyển KafkaTemplate callback sang CompletableFuture.
7. Chuyển error handler sang CommonErrorHandler/DefaultErrorHandler theo retry semantics cũ.
8. Kiểm tra DLT destination, headers và recoverer.
9. Giữ AckMode, group ID và committed offset.
10. Kiểm tra JSON type mapping và trusted packages.
11. Kiểm tra transaction ID prefix, transaction manager và read_committed.
12. Chạy test producer/consumer, retry, DLT, offset, transaction và ACL.
13. Deploy consumer canary trước khi thay đổi producer wire format.
14. Theo dõi throughput, p99 latency, consumer lag và error rate.
15. Thực hiện rollback rehearsal với record đã phát trong giai đoạn migration.
16. Ghi lại cấu hình cuối cùng và runbook vận hành.

Bài tập hoàn thành khi ứng dụng mới xử lý được record cũ, producer/consumer tương thích trong giai đoạn overlap, offset không bị reset ngoài ý muốn và các semantics retry/transaction vẫn đúng.

## 25. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Inventory | Dependency và cấu hình hiện tại | Xác định được mọi bean/property có hiệu lực. |
| 2. Version matrix | Boot, Spring Kafka, Kafka client, Java | Chọn được bộ version tương thích. |
| 3. Configuration | XML/Java config và Boot properties | Loại bỏ cấu hình trùng mà không mất behavior. |
| 4. Producer API | ListenableFuture và CompletableFuture | Chuyển callback và xử lý lỗi gửi. |
| 5. Error handling | ErrorHandler và CommonErrorHandler | Giữ đúng retry, seek, recover và DLT. |
| 6. Serialization | Type headers, mappings, schema | Đọc được payload cũ và mới. |
| 7. Offset | AckMode, group ID và committed offset | Không reset hoặc commit sai ngoài ý muốn. |
| 8. Transactions | Transaction manager, fencing, isolation | Xác minh commit/abort và read_committed. |
| 9. Deployment | Canary, rolling upgrade và rollback | Chuyển phiên bản mà không phá contract. |
| 10. Verification | Tests, metrics, business integrity | Chứng minh pipeline mới tương thích. |

Bài học hoàn thành khi bạn có thể lập kế hoạch migration từ cấu hình Spring Kafka cũ, xác định thay đổi API/configuration, giữ nguyên semantics quan trọng của offset/retry/transaction và triển khai rolling upgrade có canary, rollback cùng bằng chứng kiểm thử.

Migration thành công khi producer và consumer tiếp tục trao đổi đúng event, offset tiến đúng, retry/DLT và transaction giữ nguyên semantics đã cam kết, đồng thời hệ thống có thể rollback hoặc forward-fix mà không làm mất tính toàn vẹn dữ liệu.


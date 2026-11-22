# Log container config

Khi một Spring Kafka consumer xử lý sai group, không nhận partition như dự kiến, commit offset ở thời điểm khác thiết kế hoặc listener không khởi động, câu hỏi đầu tiên thường là: **container thực sự đang chạy với cấu hình nào?** Chỉ nhìn application.yml hoặc một đoạn @KafkaListener chưa đủ, vì cấu hình có thể đến từ nhiều tầng: Spring Boot properties, ConsumerFactory, listener container factory, annotation overrides, customizers và cấu hình được thêm ở runtime.

Spring Kafka cung cấp thuộc tính **logContainerConfig** trên **ContainerProperties**. Khi bật, listener container **ghi thông tin cấu hình container ở mức INFO lúc khởi động**, giúp kỹ sư đối chiếu effective container settings mà không cần bật DEBUG cho toàn bộ quá trình consume. Đây là một công cụ nhỏ nhưng hữu ích trong chương **Logging và chẩn đoán** của module **Spring Kafka Reliability Operations**.

Bài viết giải thích cách bật thuộc tính, cách đọc log đúng phạm vi, phân biệt cấu hình container với KafkaConsumer client properties, cách chẩn đoán offset/concurrency/transaction/pause, và cách vận hành logging an toàn trên hệ thống nhiều pods.

## 1. Vì sao chỉ nhìn application.yml là chưa đủ?

Một listener Kafka trong Spring Boot thường được hình thành từ nhiều lớp:

~~~mermaid
flowchart TD
    A["application.yml / env vars"] --> B["Spring Boot KafkaProperties"]
    B --> C["ConsumerFactory"]
    B --> D["KafkaListenerContainerFactory"]
    E["Java @Bean / customizer"] --> D
    F["@KafkaListener annotation"] --> G["Actual listener container"]
    D --> G
    C --> G
    G --> H["KafkaConsumer instances"]
    H --> K["Kafka broker"]
~~~

Ví dụ cấu hình ban đầu:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-projection
      enable-auto-commit: false
    listener:
      ack-mode: record
      concurrency: 2
~~~

Nhưng @KafkaListener có thể ghi đè một số lựa chọn:

~~~java
@KafkaListener(
    id = "orders-main",
    topics = "orders.created",
    groupId = "orders-projection-v2",
    concurrency = "4"
)
public void handle(OrderCreated event) {
    orderService.apply(event);
}
~~~

Nếu chỉ đọc YAML, operator có thể tin rằng group đang là orders-projection với concurrency=2. Trong khi listener thực tế có thể sử dụng groupId=orders-projection-v2, concurrency=4.

Ngoài ra, một bean ConcurrentKafkaListenerContainerFactory do ứng dụng tự tạo có thể dùng AckMode khác hoặc đặt các thuộc tính khác với Spring Boot auto-configuration. Log cấu hình container giúp làm rõ tầng container đang vận hành.

### 1.1 Effective configuration không phải một object duy nhất

Nên phân biệt:

- **Cấu hình Spring Boot:** các thuộc tính binding từ application.yml, profile và environment.
- **ConsumerFactory:** Kafka client properties, serializers/deserializers và security.
- **ContainerProperties:** poll/ack/error/idle/pause/transaction-related container behavior.
- **Listener endpoint:** id, topics, groupId, concurrency và một số overrides từ @KafkaListener.
- **KafkaConsumer runtime:** client.id, group membership, assignment, broker coordinator, metrics và trạng thái fetch.
- **Business listener:** logic xử lý, database/HTTP dependencies và retry semantics.

**logContainerConfig không tạo một bản dump hoàn chỉnh của tất cả các lớp này.** Nó chủ yếu giúp xem cấu hình listener container; những thành phần khác cần được xác minh riêng.

## 2. Thuộc tính logContainerConfig là gì?

Spring Kafka cung cấp API:

~~~java
ContainerProperties containerProperties = ...;
containerProperties.setLogContainerConfig(true);
~~~

Đây là một boolean option trong ContainerProperties.

| Thuộc tính | Ý nghĩa |
|---|---|
| Tên | logContainerConfig |
| Setter | setLogContainerConfig(boolean) |
| Vị trí | ContainerProperties |
| Default | false |
| Khi bật | Log cấu hình container ở mức INFO khi container khởi động |
| Có ghi mỗi Kafka record? | Không |
| Có thay đổi commit/retry/partition assignment? | Không |
| Có tự bật DEBUG cho Kafka client? | Không |
| Có thay thế metrics/tracing? | Không |

Điều cần nhớ nhất: **logContainerConfig chủ yếu phục vụ thông tin startup**. Không xem nó là một command bật logging động cho từng poll hoặc một cách truy xuất tất cả thay đổi runtime sau khi container đã chạy.

### 2.1 Bật true không có nghĩa log luôn hiển thị

Nếu logging backend hoặc mức logger chặn INFO, dòng log của Spring Kafka container có thể không xuất hiện.

Một cấu hình Spring Boot thường dùng:

~~~yaml
logging:
  level:
    org.springframework.kafka.listener: INFO
~~~

Không cần đổi toàn bộ root logger sang DEBUG chỉ để xem container configuration.

### 2.2 Định dạng log có thể khác theo Spring Kafka version

Nội dung và format chính xác phụ thuộc code của phiên bản Spring Kafka, cách ContainerProperties biểu diễn cấu hình, loại container và logging framework.

Không viết parser hoặc alert production phụ thuộc cứng vào một dòng toString() cụ thể mà chưa kiểm tra version. Nếu cần dữ liệu máy đọc lâu dài, nên bổ sung một structured startup inventory riêng hoặc application metrics có schema ổn định.

## 3. Bật log container config trên ConcurrentKafkaListenerContainerFactory

Trong ứng dụng dùng @KafkaListener, cách trực tiếp nhất là cấu hình factory được annotation sử dụng.

~~~java
@Configuration
public class OrderKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersKafkaListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<
                String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
               .setLogContainerConfig(true);

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrderConsumer {

    private final OrderService service;

    public OrderConsumer(OrderService service) {
        this.service = service;
    }

    @KafkaListener(
        id = "orders-main",
        topics = "orders.created",
        groupId = "orders-projection",
        containerFactory = "ordersKafkaListenerFactory"
    )
    public void handle(OrderCreated order) {
        service.apply(order);
    }
}
~~~

**Điểm then chốt:** listener phải tham chiếu đúng factory mà trên đó đã bật logContainerConfig. Nếu @KafkaListener dùng một factory khác, thay đổi trên ordersKafkaListenerFactory sẽ không có tác dụng với listener đó.

### 3.1 Factory có thể phục vụ nhiều endpoints

Một factory có thể tạo nhiều listener containers. Nếu các @KafkaListener cùng dùng factory, mỗi container được tạo từ nó có thể thừa hưởng cấu hình logContainerConfig.

Ví dụ:

~~~text
ordersKafkaListenerFactory
  -> orders-main container
  -> orders-retry container
  -> orders-audit container
~~~

Nếu muốn log chỉ một nhóm listeners, có thể tách factory hoặc cấu hình chính xác trên container tương ứng. Không giả định bật setting trên một factory sẽ tự ảnh hưởng mọi Kafka listeners của application.

### 3.2 Thiết lập trước khi container start

Một quy trình rõ ràng:

1. Khai báo ProducerFactory/ConsumerFactory và listener factory.
2. Đặt logContainerConfig=true trên ContainerProperties của factory.
3. Để Spring tạo các listener containers từ factory.
4. Container start, và startup logging phát ra theo mức logger.
5. Kiểm tra log của instance đang chạy.

Nếu đổi property sau khi container đã start, **không nên kỳ vọng log cấu hình startup xuất hiện ngược thời gian**. Có thể cần restart container hoặc application theo cách an toàn để quan sát startup snapshot mới; thao tác restart có thể làm consumer rebalance.

## 4. Trường hợp Spring Boot auto-configuration

Nếu ứng dụng sử dụng Spring Boot Kafka auto-configuration, Spring Boot có thể tạo factory từ KafkaProperties. Khi cần custom factory, hãy tránh bỏ rơi các cấu hình retry, message converter, transaction hoặc AckMode mà Boot đã chuẩn bị.

Một cách thường dùng là tận dụng **ConcurrentKafkaListenerContainerFactoryConfigurer**:

~~~java
@Configuration
public class OrdersKafkaFactoryConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    ordersKafkaListenerFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<String, String> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

        configurer.configure(factory, consumerFactory);

        factory.getContainerProperties()
               .setLogContainerConfig(true);

        return factory;
    }
}
~~~

Phương pháp này cho phép dùng Boot configurer để giữ các thiết lập tương ứng của Boot, sau đó áp dụng thuộc tính riêng cần thiết.

**Lưu ý:** method signatures, bean types, injection và các customizers có thể khác theo Spring Boot version. Nếu project có nhiều Kafka configs, cần kiểm tra bean wiring để chắc chắn configurer được dùng đúng và không có cấu hình phía sau ghi đè giá trị vừa đặt.

### 4.1 Nếu không tạo factory mới

Với một ứng dụng đơn giản, có thể cấu hình ngay factory hiện có thông qua bean configuration/customization hợp lệ của dự án. Không nên tạo bean cùng tên mặc định chỉ để bật logging nếu điều đó làm thay đổi các lựa chọn khác ngoài ý muốn.

Có những tùy chọn cấu hình mức Boot thay đổi theo phiên bản; cách thể hiện ổn định trong bài học là API ContainerProperties.setLogContainerConfig(true) trên factory thực tế.

### 4.2 Đọc @KafkaListener overrides

Các thuộc tính annotation như id, groupId, topics, topicPattern, clientIdPrefix, concurrency hoặc autoStartup có thể ảnh hưởng container thực được tạo.

Ví dụ:

~~~java
@KafkaListener(
    id = "payments-main",
    topics = "payments.confirmed",
    groupId = "payments-processing",
    concurrency = "6",
    autoStartup = "false",
    containerFactory = "paymentsKafkaListenerFactory"
)
public void onPayment(PaymentEvent event) {
    // ...
}
~~~

Nếu autoStartup=false, listener container có thể chưa start; bạn có thể chưa thấy startup configuration log cho nó ở thời điểm application vừa khởi động.

Cần khởi động listener theo lifecycle thực tế và kiểm tra logs tại thời điểm container start.

## 5. Trường hợp KafkaMessageListenerContainer khai báo trực tiếp

Không phải mọi application đều dùng @KafkaListener. Có project tạo KafkaMessageListenerContainer bằng Java.

~~~java
@Bean
KafkaMessageListenerContainer<String, String> manualOrdersContainer(
        ConsumerFactory<String, String> consumerFactory) {

    ContainerProperties properties =
        new ContainerProperties("orders.created");

    properties.setGroupId("manual-orders-group");
    properties.setAckMode(ContainerProperties.AckMode.RECORD);
    properties.setLogContainerConfig(true);

    properties.setMessageListener(
        (MessageListener<String, String>) record ->
            System.out.println(record.value())
    );

    return new KafkaMessageListenerContainer<>(
        consumerFactory,
        properties
    );
}
~~~

Đây là ví dụ độc lập để nhìn rõ ContainerProperties; production nên thay System.out.println bằng logging có kiểm soát hoặc business handler, xử lý exception và có đầy đủ bảo mật.

Một bean container trực tiếp không nhất thiết có trong KafkaListenerEndpointRegistry của annotation-driven listeners. Khi cần truy xuất để pause/stop hoặc chẩn đoán, hãy inject bean theo tên/reference phù hợp.

### 5.1 Concurrency ở direct container

KafkaMessageListenerContainer trực tiếp tương ứng một KafkaConsumer/container. Muốn nhiều consumers trong cùng logical listener, ứng dụng thường dùng ConcurrentMessageListenerContainer hoặc một @KafkaListener factory với concurrency.

Cấu hình logContainerConfig vẫn thuộc ContainerProperties, nhưng cách container được tạo và quản lý child instances sẽ khác.

## 6. Log container config khác log Kafka consumer config

Hai khái niệm dễ bị nhầm:

**Spring Kafka container config log**

- Được bật qua ContainerProperties.logContainerConfig.
- Thuộc framework listener container.
- Phản ánh một tập cấu hình của container.
- Dùng để kiểm tra AckMode, poll, listener-related settings theo nội dung được version log.

**Apache Kafka client config log**

- Do Kafka ConsumerConfig/ProducerConfig và logging của Kafka clients xuất ra.
- Bao gồm client properties như bootstrap.servers, group.id, auto.offset.reset, request.timeout.ms, enable.auto.commit và nhiều tham số Kafka client.
- Có cơ chế log và logger riêng, không phải do logContainerConfig trực tiếp điều khiển.
- Có khả năng hiển thị nhiều chi tiết hạ tầng/security-related config hơn; cần kiểm tra trước khi bật mức logging rộng.

Bảng:

| Câu hỏi | Nguồn ưu tiên |
|---|---|
| Spring listener dùng AckMode nào? | ContainerProperties / container config log |
| Container có observationEnabled không? | Effective ContainerProperties / observability startup inventory |
| Kafka consumer dùng auto.offset.reset gì? | ConsumerFactory/Kafka client effective config |
| Kafka consumer có assigned partition nào? | Consumer assignment logs/events/metrics |
| Listener thực tế xử lý topic nào? | @KafkaListener endpoint + container subscription/runtime assignment |
| Kafka broker giữ bao nhiêu partitions? | Kafka admin/broker metadata |
| Consumer group committed offset là bao nhiêu? | Kafka group offset query |
| Listener có bị retry vô hạn không? | ErrorHandler config + retry logs/metrics |

**Đừng nhầm một dòng cấu hình container với bằng chứng tất cả KafkaConsumer properties đã được áp dụng đúng.**

### 6.1 Tại sao group.id đặc biệt cần đối chiếu?

Trong Spring Kafka, @KafkaListener.id có thể trở thành group ID khi không cung cấp groupId riêng, tùy idIsGroup setting.

Ví dụ:

~~~java
@KafkaListener(
    id = "orders-main",
    topics = "orders.created"
)
public void handle(OrderCreated event) {
    // ...
}
~~~

Nếu idIsGroup=true và không có groupId explicit, group.id thực tế có thể là orders-main thay vì giá trị spring.kafka.consumer.group-id mà operator đọc từ YAML.

Một group mới có namespace committed offsets riêng; service có thể replay dữ liệu hoặc bắt đầu ở offset khác theo auto.offset.reset. Đây là lỗi reliability quan trọng có thể bị hiểu nhầm thành “Kafka không nhận message”.

Cách rõ ràng:

~~~java
@KafkaListener(
    id = "orders-main",
    groupId = "orders-projection-prod",
    topics = "orders.created"
)
~~~

Log container config là một nguồn chứng cứ; vẫn cần kiểm tra effective group membership/committed offsets trên broker.

## 7. Những thuộc tính ContainerProperties cần biết

ContainerProperties có nhiều lựa chọn điều khiển hành vi listener container. Tập nào được thể hiện trong log cấu hình có thể thay đổi theo Spring Kafka version.

| Thuộc tính | Vai trò vận hành | Dấu hiệu cần điều tra |
|---|---|---|
| ackMode | Ranh giới acknowledgment/commit offset | Commit quá sớm hoặc quá muộn |
| syncCommits | Dùng synchronous hay asynchronous commit | Commit latency hoặc error visibility |
| ackCount | Ngưỡng records cho COUNT/COUNT_TIME | Offset tiến chậm |
| ackTime | Ngưỡng thời gian cho TIME/COUNT_TIME | Periodic commit không đúng kỳ vọng |
| pollTimeout | Timeout poll KafkaConsumer | Latency, CPU và nhịp polling |
| pollTimeoutWhilePaused | Timeout poll khi container paused | CPU cao khi paused |
| idleEventInterval | Khoảng phát listener idle event | Không thấy IdleEvent hoặc thấy quá dày |
| noPollThreshold | Ngưỡng đánh giá nonresponsive poll | Cảnh báo consumer không phản hồi |
| monitorInterval | Chu kỳ kiểm tra nonresponsive consumer | Monitoring event cadence |
| pauseImmediate | Pause sau current record hay hết poll | Backpressure phản ứng chậm |
| stopImmediate | Thời điểm stop sau current record | Shutdown duration |
| logContainerConfig | Có log cấu hình startup ở INFO | Thiếu startup snapshot |
| commitLogLevel | Mức log cho offset commits | Debug commit quá nhiễu hoặc không thấy |
| missingTopicsFatal | Lỗi startup khi topic thiếu | Listener không start |
| authExceptionRetryInterval | Retry sau authorization error theo policy | Consumer dừng hoặc chờ do ACL |
| observationEnabled | Bật Micrometer Observation | Trace/metric không xuất hiện |
| micrometerEnabled | Bật legacy Micrometer listener timers | Timer thiếu hoặc trùng với observation |

**Không suy luận mọi property trong bảng đều luôn được ghi ra nguyên vẹn bởi logContainerConfig.** Nội dung toString/config print của framework tùy phiên bản và implementation.

### 7.1 Các thuộc tính liên quan nhau nhưng khác lớp

Một số thông tin gần với container nhưng không phải field của ContainerProperties theo cùng cách:

- **Concurrency:** thường cấu hình ở ConcurrentMessageListenerContainer hoặc factory, có thể được @KafkaListener override.
- **CommonErrorHandler:** thường gắn ở container/factory; không nên trông đợi logContainerConfig thể hiện đủ BackOff/DLT semantics.
- **Deserializer:** thuộc ConsumerFactory/Kafka client setup.
- **Kafka transaction manager:** thuộc transaction integration; cần kiểm tra bean wiring.
- **Broker partition count:** lấy từ broker metadata.

Để chẩn đoán toàn diện phải ghép nhiều nguồn, không dựa vào một log line.

## 8. Ví dụ đọc log startup có ngữ cảnh

Tùy Spring Kafka version, một log cấu hình có thể có cấu trúc/format khác nhau. Sơ đồ sau chỉ minh họa ý nghĩa:

~~~text
INFO [orders-main] Spring Kafka listener container configuration:
  topics: [orders.created]
  ackMode: RECORD
  pollTimeout: 5000
  logContainerConfig: true
  observationEnabled: false
~~~

**Đây là log minh họa, không phải output cam kết byte-for-byte từ một phiên bản Spring Kafka.** Trong thực tế, có thể là một đoạn text dạng ContainerProperties{...}, nhiều trường khác, hoặc được xuất tại logger khác trong package listener.

Khi kiểm tra, nên kết hợp:

- Timestamp startup.
- Pod/instance ID.
- Application version và Spring Kafka version.
- Listener/container ID.
- Consumer group ID.
- Topic subscription.
- Concurrency/child client IDs nếu có.
- Container config snapshot.
- Những sự kiện partition assignment xuất hiện sau startup.

### 8.1 Không dùng grep một field rồi kết luận

Nếu không thấy ackMode trong dòng log, không được kết luận nó bằng một giá trị cụ thể. Có thể version đó không in field này hoặc log line bị cắt/truncated bởi collector.

Đối chiếu thêm configuration bean và runtime metadata khi cần. Log là **chứng cứ**, không phải specification đầy đủ của effective configuration.

### 8.2 Snapshot khác live state

Nếu container đang paused sau khi khởi động, startup config log có thể cho biết pauseImmediate=true nhưng **không chứng minh container hiện đang paused**.

Tương tự, startup log của concurrency=3 không chứng minh ba consumers đều đang có partition assignment. Kafka topic có thể ít partitions hơn, hoặc group rebalance làm một child chưa được gán partition.

Cần kết hợp container state APIs, Application Events và Kafka metrics.

## 9. Ví dụ chẩn đoán AckMode và offset commit

Một service báo “consumer đã xử lý record nhưng offset không tiến đều”. Khả năng là AckMode đang là BATCH thay vì RECORD, hoặc có lỗi trong commit.

Ví dụ cấu hình rõ:

~~~java
factory.getContainerProperties()
       .setAckMode(ContainerProperties.AckMode.RECORD);

factory.getContainerProperties()
       .setLogContainerConfig(true);
~~~

Giả sử một poll nhận A, B, C, D; listener xử lý từng record.

- **AckMode.RECORD:** container thường xác nhận/commit theo record thành công và commit policy.
- **AckMode.BATCH:** container xử lý records từ poll và commit theo batch boundary.
- **AckMode.TIME/COUNT/COUNT_TIME:** commit phụ thuộc thresholds tương ứng.
- **AckMode.MANUAL/MANUAL_IMMEDIATE:** application phải acknowledge theo contract.

Log config giúp xác định giá trị container đang có. Nhưng không chứng minh **mỗi commit đã thực sự thành công**.

### 9.1 Commit logs khác config logs

ContainerProperties có **commitLogLevel** để điều chỉnh mức log liên quan offset commits theo API/version. Ví dụ:

~~~java
factory.getContainerProperties().setCommitLogLevel(
    LogIfLevelEnabled.Level.DEBUG
);
~~~

Đây là cơ chế khác với setLogContainerConfig(true):

- logContainerConfig: log **configuration** lúc startup.
- commitLogLevel: mức log cho những thông tin **offset commit** trong hoạt động.

Nếu muốn điều tra commit progression, chỉ bật logContainerConfig thường không đủ; cần xem consumer group offsets, Kafka client metrics và commit outcomes.

### 9.2 Manual AckMode cần kiểm tra listener code

Một listener manual ack:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "manualAckFactory"
)
public void onOrder(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment ack) {

    orderService.apply(record.value());
    ack.acknowledge();
}
~~~

Nếu code không gọi acknowledge() sau xử lý, offset có thể không tiến theo kỳ vọng. Không có log config nào thay thế việc hiểu listener acknowledgment logic.

**Không đặt ack.acknowledge() trong finally** nếu nghiệp vụ thất bại cần retry.

### 9.3 Auto commit là một tầng khác

Kafka client property **enable.auto.commit** có thể thay đổi semantics nếu bị bật ngoài chủ đích. Đây là client property, phải kiểm tra ConsumerFactory/effective Kafka consumer config.

Đừng kết luận auto commit chỉ từ ackMode của ContainerProperties. Trong Spring Kafka, framework thường điều phối commits và mặc định tắt auto commit nếu không được cấu hình rõ theo các phiên bản hiện đại; vẫn phải kiểm tra effective value.

## 10. Chẩn đoán concurrency và partition assignment

Một tình huống thường gặp: application đặt concurrency=8 nhưng topic chỉ có 3 partitions và consumer group chỉ thấy vài consumer có records.

~~~text
Topic orders.created:
  partitions: 0, 1, 2

Listener concurrency: 8
Consumer group members/child consumers: có thể tới 8

Tối đa 3 members có partitions được gán
Các members còn lại có thể idle
~~~

Không có nghĩa listener container cấu hình sai chỉ vì nhiều child không xử lý message. Một consumer group thường không phân nhiều consumers cùng đọc một partition tại một thời điểm.

### 10.1 Cấu hình trong factory và annotation

~~~java
factory.setConcurrency(4);
~~~

Annotation có thể override:

~~~java
@KafkaListener(
    id = "orders-main",
    concurrency = "8",
    topics = "orders.created"
)
~~~

Concurrency không chỉ là ContainerProperties setting. Kiểm tra effective concurrency ở ConcurrentMessageListenerContainer/endpoint và số child consumers thực tế.

### 10.2 Các child containers có IDs riêng

Một concurrent container có thể tạo child IDs:

~~~text
orders-main-0
orders-main-1
orders-main-2
orders-main-3
~~~

Quy tắc suffix phụ thuộc framework/runtime. Client ID cũng có hậu tố và có thể khác listener ID. Khi tra logs, cần match đúng parent endpoint và children thay vì nhìn một dòng parent rồi xem như toàn bộ consumer đã sẵn sàng.

### 10.3 Cấu hình không bằng ownership runtime

Ngay cả khi startup config đúng, group có thể rebalance vì:

- Pod mới join hoặc rời group.
- Consumer vượt max.poll.interval.ms.
- Topic partition count đổi.
- Broker/coordinator error.
- Network interruption.
- Consumer shutdown/restart.

Cần xem partition assignment logs, ConsumerPartitionAssignedEvent/RevokedEvent theo version, Kafka group describe và lag per partition. Log container config chỉ là điểm xuất phát.

## 11. Chẩn đoán startup bị lỗi vì topic thiếu

Spring Kafka có cấu hình **missingTopicsFatal** trong ContainerProperties ở các version hỗ trợ.

Nếu listener tham chiếu topic không tồn tại, container có thể:

- Fail startup nếu policy yêu cầu topic phải tồn tại.
- Chờ topic xuất hiện hoặc xử lý theo phiên bản/cấu hình khác.
- Bị chặn bởi metadata/authentication errors khiến lỗi trông giống thiếu topic.

Có thể log rõ lựa chọn:

~~~java
factory.getContainerProperties()
       .setMissingTopicsFatal(true);

factory.getContainerProperties()
       .setLogContainerConfig(true);
~~~

Khi container không start, cần kiểm tra:

1. Topic name thực tế từ @KafkaListener.
2. Bootstrap servers và cluster environment.
3. ACL cho Describe/Read.
4. Topic có tồn tại trong cluster không.
5. missingTopicsFatal value.
6. Error logs tại startup.
7. KafkaAdmin auto topic creation policy.
8. Network và broker metadata availability.

### 11.1 Không suy luận thiếu topic chỉ từ empty assignment

Một consumer không được gán partition có thể do topic ít partitions hơn số consumers, group rebalance hoặc subscription khác, chứ không nhất thiết topic không tồn tại.

Log cấu hình container giúp xác định topic mong muốn; broker metadata xác nhận thực tế.

### 11.2 Không tự bật auto-create topic để sửa nhanh

Việc topic tự động được tạo có thể gây số partitions, replication factor hoặc retention không đúng production policy. Nếu phát hiện sai tên topic, sửa cấu hình và quy trình provision thay vì bật auto-create không kiểm soát.

## 12. Chẩn đoán pauseImmediate và backpressure

Một operator gọi pause() nhưng listener vẫn xử lý nhiều records trước khi dừng. Cần xem:

- Container có bật pauseImmediate không?
- Listener là record hay batch?
- max.poll.records bao nhiêu?
- Record hiện tại xử lý lâu không?
- Parent concurrent container có nhiều child chưa pause không?

Ví dụ:

~~~java
factory.getContainerProperties()
       .setPauseImmediate(true);

factory.getContainerProperties()
       .setLogContainerConfig(true);
~~~

Theo semantics:

- pauseImmediate=false: container có thể xử lý hết các records của poll trước rồi mới pause.
- pauseImmediate=true: record listener có thể dừng sau current record, giữ records còn lại trong memory cho resume.

Log cấu hình giúp xác định lựa chọn, nhưng **không cho biết pause hiện tại đã có hiệu lực**. Cần xem:

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("orders-main");

boolean requested = container.isPauseRequested();
boolean effective = container.isConsumerPaused();
~~~

Với concurrent container, requested và effective có thể lệch trong một khoảng khi các child vẫn xử lý records đang chạy.

### 12.1 Pause và consumer poll

Khi container paused, Spring Kafka vẫn có thể poll để duy trì group membership. Tùy version, pollTimeoutWhilePaused quyết định timeout của các poll này.

Nếu listener đang block rất lâu trước khi pause có hiệu lực, max.poll.interval.ms vẫn có thể bị vượt. LogContainerConfig không khắc phục nguyên nhân; cần timeout cho downstream và monitoring listener processing duration.

## 13. Chẩn đoán transaction/EOS

Nếu listener dùng Kafka transactions, application cần biết:

- ProducerFactory có transaction capable không.
- KafkaTransactionManager có được gắn đúng container/factory không.
- Listener có chạy trong Kafka transaction không.
- Consumer offsets có được commit cùng Kafka output không.
- Downstream có dùng read_committed khi cần không.

Một phần transaction-related container settings có thể được phản ánh trong cấu hình container, nhưng **logContainerConfig không tự chứng minh đúng toàn bộ Kafka transaction wiring**.

Ví dụ scenario:

~~~text
@KafkaListener nhận order event
  -> KafkaTemplate gửi orders.out
  -> Container commit consumed offset

Kỳ vọng: output + offset cùng Kafka transaction
~~~

Muốn xác minh thực tế cần:

- Transaction-capable ProducerFactory với transactionIdPrefix.
- KafkaTransactionManager hoặc Kafka-aware manager phù hợp version.
- Listener container transaction configuration.
- KafkaTemplate dùng đúng transactional factory.
- Integration test commit/abort.
- Producer fencing/transaction commit logs.
- Downstream consumer isolation.level=read_committed khi cần.

### 13.1 Tránh nhầm startup config với commit outcome

Ngay cả khi log cho thấy container đã được gắn transaction support, Kafka commit vẫn có thể thất bại do:

- ProducerFencedException.
- Transaction timeout.
- Broker coordinator error.
- Kafka send failure.
- Consumer group rebalance.
- Network interruption.

**Một dòng “container config” không phải bằng chứng transaction commit thành công.**

### 13.2 Transaction manager cấu hình ngoài ContainerProperties

Trong các Spring Kafka versions khác nhau, API gắn KafkaAwareTransactionManager vào listener container có thay đổi. Không copy một setter cũ từ blog rồi kỳ vọng compile ở bản mới.

LogContainerConfig hỗ trợ chẩn đoán; test và bean wiring verification mới chứng minh Kafka transaction thực sự có hiệu lực.

## 14. Logging container config và error handler

Spring Kafka có các error handling components như DefaultErrorHandler, BackOff, DeadLetterPublishingRecoverer, AfterRollbackProcessor và retry topic infrastructure.

Một reader có thể thấy trong log container một số thông tin liên quan retry/error handler, nhưng không nên giả định nó xuất đầy đủ:

- BackOff initial interval.
- Maximum attempts.
- Danh sách non-retryable exceptions.
- DLT topic routing.
- Exception classification logic.
- Recovery commit policy.
- Retry topic delay.
- ErrorHandlingDeserializer config.

Những thông tin này có thể ở các beans/factories khác và cần startup inventory hoặc application configuration riêng.

### 14.1 Ví dụ về retry policy

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    var backOff = new FixedBackOff(1_000L, 4L);

    return new DefaultErrorHandler(
        recoverer,
        backOff
    );
}
~~~

Ví dụ dùng FixedBackOff 1 giây và bốn retries theo semantics của handler tương ứng. Cần hiểu version API để xác định tổng deliveries và recoverer behavior.

Nếu operator thấy record lặp lại nhiều lần, logContainerConfig chỉ cho biết một phần container setup. Phải xem handler bean, exception path và DLT outcomes.

### 14.2 Không dùng DEBUG vô hạn cho mọi record

Để điều tra một case, có thể tăng log level tạm thời cho package/class cụ thể, nhưng logging quá chi tiết trên consumer throughput cao có thể gây:

- Disk và network I/O cao.
- CPU dành cho serialization/log formatting.
- Metric/log backend quá tải.
- PII hoặc payload leak.
- Latency tăng và poll interval vi phạm.
- Chi phí retention lớn.

Bật logContainerConfig ở INFO có ích vì không chủ động log từng record, nhưng vẫn cần kiểm tra số containers và volume startup khi scale-out.

## 15. Logging levels cần đặt thế nào?

Trong Spring Boot:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.kafka.listener: INFO
    org.apache.kafka.clients: WARN
~~~

Đây chỉ là một policy minh họa. Không nhất thiết phải đặt toàn bộ Apache Kafka client package ở WARN nếu muốn client warnings/info hữu ích khác.

Mục tiêu chính là **container logger cho phép INFO**. Nếu runtime dùng Logback/Log4j2 custom config, package override và appender filters cũng có thể quyết định log có xuất hiện hay không.

### 15.1 Khi debug chỉ một listener

Thay vì đặt:

~~~yaml
logging:
  level:
    root: DEBUG
~~~

nên ưu tiên:

1. Bật logContainerConfig đúng listener factory.
2. Giữ package org.springframework.kafka.listener ở INFO.
3. Thu startup logs của pod cần điều tra.
4. Nếu chưa đủ, tăng DEBUG cho class cụ thể trong thời gian giới hạn.
5. Gỡ DEBUG sau khi khép incident.

Trong ứng dụng có hàng trăm child containers, logging startup có thể tạo nhiều dòng. Dù không log từng record, vẫn cần kiểm soát độ lớn và retention.

### 15.2 Logging cấu hình Kafka client là lựa chọn riêng

Apache Kafka clients có thể ghi các dòng dạng ConsumerConfig values hoặc ProducerConfig values lúc tạo client, nhưng nội dung, mức log và redaction tùy client version.

Không coi client config logs là output của logContainerConfig. Nếu cần log Kafka client config để điều tra, xem trước khả năng lộ sensitive settings và chỉ bật phạm vi cần thiết.

## 16. Structured startup inventory bổ sung

Vì logContainerConfig không bảo đảm mọi thông tin operator cần có mặt, một ứng dụng phức tạp có thể bổ sung log **chọn lọc, có schema ổn định và đã sanitize**.

Ví dụ ứng dụng ghi inventory:

~~~text
event=KAFKA_LISTENER_CONFIG
service=orders-projection
instance=pod-a
listenerId=orders-main
groupId=orders-projection-prod
topics=orders.created
concurrency=3
ackMode=RECORD
observationEnabled=true
logContainerConfig=true
applicationVersion=2026.11.15
~~~

Đây là schema **do ứng dụng định nghĩa**, không phải định dạng mặc định của Spring Kafka. Chỉ ghi các trường đã được xác minh đúng từ bean/endpoint thực tế.

### 16.1 Tại sao cần sanitize?

Một số configuration objects có thể chứa:

- Bootstrap addresses và internal hostnames.
- Security mechanism.
- Truststore/keystore paths.
- Topic names liên quan nghiệp vụ nhạy cảm.
- Client IDs hoặc environment-specific routing.
- Custom interceptors/converters có toString() chứa dữ liệu không mong muốn.

Không ghi:

- sasl.jaas.config nguyên văn.
- Username/password, API token, OAuth credentials.
- Private key material.
- Full TLS keystore content.
- Raw Kafka message payload.
- Header values có PII hoặc secret.

Ngay cả khi Spring/Kafka có cơ chế masking riêng, không nên dựa hoàn toàn vào nó cho một custom startup dump.

### 16.2 Ví dụ logging danh sách listener IDs

Trong một Spring application có @KafkaListener registry:

~~~java
@Component
public class KafkaListenerStartupInventory {

    private static final Logger log =
        LoggerFactory.getLogger(KafkaListenerStartupInventory.class);

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerStartupInventory(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void report() {

        for (MessageListenerContainer container :
                registry.getListenerContainers()) {

            log.info(
                "event=KAFKA_LISTENER_INVENTORY listenerId={} running={} " +
                "pauseRequested={}",
                container.getListenerId(),
                container.isRunning(),
                container.isPauseRequested()
            );
        }
    }
}
~~~

Đoạn này chỉ ghi những state fields thông qua container API; nó không cố serialize KafkaConsumer hoặc toàn bộ ConsumerFactory properties. Method getListenerId() và các state APIs cần được đối chiếu với version thực tế nếu có custom listener container type.

### 16.3 Tránh gọi KafkaConsumer ngoài consumer thread

Không dùng code inventory để lấy KafkaConsumer trực tiếp rồi gọi subscribe/assignment/pause/seek tùy ý từ ApplicationReadyEvent thread. KafkaConsumer có quy tắc thread ownership; truy cập không đúng có thể gây race hoặc ConcurrentModification/IllegalStateException.

Dùng registry/container APIs và Application Events đã được Spring Kafka hỗ trợ.

## 17. Chẩn đoán listener ID, group ID và client ID

Trong logs thường có ít nhất ba danh tính:

- **Listener ID:** endpoint/container identity, ví dụ orders-main.
- **Group ID:** Kafka consumer group, ví dụ orders-projection-prod.
- **Client ID:** Kafka client metric/log identifier, có thể là orders-projection-0, orders-projection-1.

Chúng không phải đồng nghĩa.

~~~text
@KafkaListener.id        = orders-main
@KafkaListener.groupId   = orders-projection-prod
client.id for child      = orders-client-0
~~~

Khi một incident được báo trên client.id cụ thể, cần map client về child container/listener và group. Cấu hình container cho biết intent, nhưng runtime client metrics và assignment mới cho thấy consumer cụ thể đang thực hiện gì.

### 17.1 Đổi listener ID có tác dụng phụ?

Khi groupId được khai báo rõ, đổi listener ID có thể ảnh hưởng registry lookup, monitoring labels và application event filtering.

Khi groupId không khai báo và idIsGroup=true, đổi @KafkaListener.id còn có thể **đổi group.id**, dẫn tới namespace offset mới. Đây là lỗi cấu hình nguy hiểm hơn việc đổi một tên log.

### 17.2 Tại sao log container config giúp?

Nếu một deployment vừa refactor listener ID, startup log giúp đối chiếu các IDs/containers thực tế và tìm chỗ khác với contract vận hành.

Dù vậy, đừng chỉ dựa một log line để quyết định reset offsets. Phải kiểm tra group committed offsets thật trên Kafka.

## 18. Chẩn đoán môi trường và profile bị ghi đè

Một service có:

~~~yaml
# application.yml
spring:
  kafka:
    consumer:
      group-id: orders-projection
~~~

Nhưng production environment có thể override:

~~~text
SPRING_KAFKA_CONSUMER_GROUP_ID=orders-projection-blue
~~~

Hoặc @KafkaListener(groupId="orders-projection-prod") có thể ưu tiên một giá trị khác nữa.

Nguồn cấu hình cần đối chiếu theo thứ tự phù hợp với Spring Boot:

- application.yml / application-profile.yml.
- Environment variables.
- ConfigMaps/Secrets.
- Command-line arguments.
- Bean configuration.
- Container factory customizers.
- @KafkaListener overrides.
- Runtime lifecycle changes.

Không nên suy luận precedence bằng trí nhớ trong một hệ thống có nhiều customizers; hãy xem **effective configuration** và test behavior.

### 18.1 Startup log là bằng chứng theo instance

Pod A và pod B có thể chạy khác app version hoặc khác environment variables trong rolling deployment. Không lấy startup config log của pod A để kết luận pod B đang dùng cấu hình giống hệt.

Nên gắn log với:

~~~text
service, environment, pod/instance, build version, listener id, timestamp
~~~

Nếu log collector loại mất các labels này, hãy sửa pipeline logging trước khi đánh giá config drift.

### 18.2 So sánh config drift giữa replicas

Khi group có 5 pods:

1. Lấy startup config log của từng pod.
2. So sánh container properties quan trọng và app version.
3. So sánh runtime group ID, client IDs và assignment.
4. Kiểm tra khác biệt do rollout đang diễn ra có chủ đích không.
5. Xác định instance nào có setting không đúng.
6. Sửa ConfigMap/Deployment/Bean configuration.
7. Rollout có kiểm soát và đo lại group rebalance.
8. Không reset offsets chỉ vì config drift.

Một drift về AckMode hoặc transaction config giữa replicas có thể gây khác biệt behavior theo pod, rất khó chẩn đoán nếu chỉ nhìn dashboard aggregate.

## 19. Log container config và Micrometer Observation

Ở Spring Kafka hiện đại:

~~~java
factory.getContainerProperties()
       .setObservationEnabled(true);

factory.getContainerProperties()
       .setLogContainerConfig(true);
~~~

Hai thuộc tính độc lập về mục đích:

- logContainerConfig: startup configuration logging.
- observationEnabled: tạo observations có thể dẫn tới metrics/tracing.

Nếu metric spring.kafka.listener không xuất hiện, log container config có thể gợi ý observationEnabled hoặc micrometerEnabled đang có giá trị nào. Nhưng cần thêm:

- ObservationRegistry/MeterRegistry có được cấu hình không?
- Prometheus exporter có hoạt động không?
- Tracing bridge có được bật không?
- Listener đã thực sự nhận records chưa?
- Có MeterFilter hoặc sampling policy không?

**Đừng coi logContainerConfig là cách kiểm chứng end-to-end metrics/tracing.** Nó chỉ là một công cụ bổ sung cho observability pipeline.

### 19.1 Timer truyền thống và Observation

Khi observationEnabled được bật, Spring Kafka có thể tắt cơ chế Micrometer listener timer truyền thống tương ứng để tránh instrumentation trùng, theo phiên bản. Chỉ nhìn micrometerEnabled=true trong source mà không xem observationEnabled không đủ để kết luận metric schema cuối cùng.

Điều quan trọng là kiểm tra actual registry metrics và tracing spans sau khi startup.

## 20. Log container config có thể tiết lộ thông tin gì?

Cấu hình vận hành thường không phải public data. Dù logContainerConfig không chủ động dump mọi Kafka client secret, startup log vẫn có thể chứa metadata nội bộ và cách container được thiết kế.

Những loại thông tin cần cân nhắc:

- Topic và consumer group names có thể tiết lộ business workflows.
- Bootstrap hosts và cluster names có thể tiết lộ topology.
- Listener IDs và bean names có thể tiết lộ service structure.
- Custom container properties hoặc message listener toString() có thể chứa dữ liệu riêng.
- Exception strings trong cùng startup log có thể chứa paths hoặc endpoint names.
- Nếu bật thêm client configuration logs, security properties cần được redacted đúng.

### 20.1 Logging policy an toàn

- Chỉ bật khi có mục đích vận hành rõ.
- Dùng INFO package/class phù hợp, tránh DEBUG toàn cục.
- Không tự stringify toàn bộ KafkaProperties/Environment/ConsumerFactory map rồi log.
- Sanitize structured inventory.
- Hạn chế quyền xem startup logs.
- Đặt retention phù hợp.
- Kiểm tra log pipeline masking/redaction.
- Không gửi secret trong error details.
- Phân biệt dev/staging/prod policies.

### 20.2 Có nên bật lâu dài?

Có thể bật lâu dài nếu:

- Tần suất restart không quá lớn.
- Log volume thấp và chi phí chấp nhận được.
- Configuration string được kiểm tra không lộ secrets.
- Đội vận hành thực sự dùng startup config để tra incident.
- Log retention và access control phù hợp.

Không bắt buộc phải luôn bật ở mọi container. Với hệ thống có hàng nghìn consumers và rollout liên tục, chi phí có thể đáng kể. Cần cân nhắc nhu cầu support so với log volume.

## 21. Log container config không tự thay đổi behavior

Một số operator lo rằng bật logging có thể làm listener chuyển AckMode, pause hoặc thay group membership. Bản thân **logContainerConfig** là tùy chọn instrumentation/logging, không phải business/reliability policy.

Nó không tự:

- Thay đổi Kafka offsets.
- Commit hoặc rollback Kafka transactions.
- Restart Kafka consumers.
- Tăng concurrency.
- Thay đổi group.id.
- Seek tới offset mới.
- Chuyển record vào DLT.
- Bật pauseImmediate.
- Tạo Kafka AdminClient.
- Bật Micrometer Observation.

**Nhưng cách triển khai thay đổi vẫn có thể gây hiệu ứng.** Nếu bật setting bằng cách deploy build mới hoặc restart container, quá trình rollout/restart có thể tạo rebalance và ảnh hưởng latency. Phải phân biệt tác động của **deployment** với bản thân logContainerConfig.

## 22. Trình tự điều tra khi thiếu startup config log

Nếu đã setLogContainerConfig(true) mà không thấy dòng log:

1. Xác nhận code đã deploy lên pod cần điều tra.
2. Xác nhận Spring Kafka version có API này.
3. Kiểm tra @KafkaListener thực sự dùng container factory nào.
4. Kiểm tra một customizer có ghi đè ContainerProperties sau khi bạn set không.
5. Xác nhận container đã start, không phải autoStartup=false.
6. Xác nhận package/class logger cho phép INFO.
7. Kiểm tra Logback/Log4j2 appender filters.
8. Kiểm tra log collector có thu startup logs từ lúc container start không.
9. Kiểm tra container config log có định dạng khác suy đoán không.
10. Nếu dùng concurrent container, kiểm tra log parent/child cùng thời điểm.
11. Nếu pod restart quá nhanh, kiểm tra previous container logs.
12. Thử một startup có kiểm soát trên staging với cùng factory.

**Không cần bật root DEBUG** trước khi đã kiểm tra đúng listener factory và logging pipeline.

### 22.1 Một lỗi thường gặp về bean factory

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
debugFactory(ConsumerFactory<String, String> cf) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(cf);
    factory.getContainerProperties().setLogContainerConfig(true);

    return factory;
}
~~~

Nhưng annotation dùng:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "kafkaListenerContainerFactory"
)
~~~

Ứng dụng đã bật logging trên debugFactory, còn listener dùng kafkaListenerContainerFactory. Đây là lỗi wiring, không phải lỗi logback.

## 23. Trình tự điều tra khi container hoạt động sai dù log đúng

Nếu log đúng nhưng behavior vẫn bất thường:

1. Xác nhận config snapshot và application version.
2. Kiểm tra Kafka client effective properties riêng.
3. Kiểm tra broker metadata/topic partitions/ACLs.
4. Kiểm tra committed offsets và group membership.
5. Đọc consumer assignment/rebalance events.
6. Kiểm tra error handler/retry/DLT configuration.
7. Kiểm tra listener exception và business side effects.
8. Kiểm tra transaction manager/producer factory nếu dùng Kafka EOS.
9. Kiểm tra pause/resume state và poll liveness.
10. Kiểm tra metrics/traces, đặc biệt consumer lag, retry và processing latency.
11. Reproduce trên integration/staging nếu cần.
12. Chỉ thay đổi cấu hình sau khi xác định nguyên nhân.

LogContainerConfig cung cấp **cấu hình ban đầu**, không thay thế runtime evidence.

## 24. Bảng các tình huống chẩn đoán

| Triệu chứng | Cần đối chiếu từ container config | Cần thêm nguồn nào |
|---|---|---|
| Listener không start | autoStartup, missingTopicsFatal, topic subscription | Startup exceptions, broker metadata, ACL |
| Consumer đọc từ đầu bất ngờ | Listener/group ID và endpoint overrides | Group committed offsets, auto.offset.reset |
| Offset tiến chậm | AckMode, ackCount, ackTime, syncCommits | Offset query, commit logs, listener duration |
| Một số child idle | Concurrent container setting, listener ID | Topic partition count, group assignment |
| Pause phản ứng chậm | pauseImmediate, pollTimeout | Current record duration, paused events |
| Poll không phản hồi | pollTimeout/monitor settings | Thread dump, downstream timeout, max.poll.interval.ms |
| Retry quá nhiều | Container error configuration nếu có | DefaultErrorHandler, BackOff, DLT metrics |
| Không có Kafka tracing | observationEnabled | ObservationRegistry, trace headers/exporter |
| Send/offset không atomic | Transaction container wiring một phần | KafkaTransactionManager, ProducerFactory, integration test |
| Log cấu hình thiếu | logContainerConfig, logger INFO | Factory wiring, lifecycle, logging pipeline |
| Broker auth error | Không đủ dữ liệu từ container log | Kafka client security settings, ACL, broker logs |
| CPU cao lúc paused | pollTimeoutWhilePaused | CPU profiler, poll metrics, actual pause state |

Một symptom có thể có nhiều nguyên nhân; đừng lấy một field làm kết luận nếu không có evidence phù hợp.

## 25. Kiểm thử lưu trữ cấu hình khi triển khai

Một integration test hữu ích không chỉ assert rằng setter được gọi. Nó cần khởi chạy listener container thực tế và xác nhận startup log có mặt khi flag bật.

### 25.1 Test flag on

1. Tạo listener factory có logContainerConfig=true.
2. Tạo listener container từ factory.
3. Bật INFO cho package/class logger của Spring Kafka container.
4. Gắn test log appender hoặc log capture phù hợp.
5. Start container trong test context.
6. Chờ startup lifecycle hoàn tất.
7. Xác nhận log chứa một thông tin cấu hình container theo format version.
8. Dừng container đúng cách để tránh test leak.

Không dùng byte-for-byte string equality với toàn bộ ContainerProperties.toString(), vì các minor versions có thể thay đổi thứ tự/format fields.

### 25.2 Test flag off

1. Tạo listener factory thứ hai có flag=false.
2. Start container với logger INFO.
3. Xác nhận không có log cấu hình startup thuộc chính cơ chế flag cho container đó.
4. Không giả định mọi Kafka client config logs cũng biến mất; client logging là cơ chế khác.

### 25.3 Test factory wiring

1. Đăng ký factory A flag=true và factory B flag=false.
2. Tạo hai @KafkaListeners dùng explicit containerFactory.
3. Start context.
4. Đối chiếu listener/container IDs trong logs.
5. Xác nhận chỉ container dùng A có cơ chế log config tương ứng.
6. Kiểm tra annotations không tham chiếu nhầm bean.

### 25.4 Test group ID override

1. ConsumerFactory có group.id=from-factory.
2. @KafkaListener đặt groupId=from-annotation.
3. Start listener.
4. Quan sát endpoint/container metadata và group membership thực tế.
5. Xác nhận Kafka group đang dùng from-annotation.
6. Không dùng group reset/seek trong test chỉ để xác nhận logging.

### 25.5 Test sanitized inventory

Nếu ứng dụng có custom startup inventory:

- Inject một secret giả vào test configuration.
- Capture logs.
- Xác nhận secret không xuất hiện.
- Xác nhận các identifiers được phép vẫn có mặt.
- Kiểm tra log record có service/pod/version context.
- Không kiểm tra secret masking bằng cách in secret thật.

## 26. Lưu ý về version compatibility

Spring Kafka đã phát triển nhiều APIs qua các dòng 2.x, 3.x và 4.x. logContainerConfig là thuộc tính ContainerProperties, nhưng:

- Tên package và setter của một số related properties có thể khác.
- Cách tạo container từ listener factory có thể thay đổi.
- Transaction manager/observation APIs khác giữa versions.
- Những thuộc tính mới có thể được bổ sung vào toString/config log.
- Log format và logger class cụ thể có thể thay đổi.
- Spring Boot property bindings/configurer có thể thay đổi.

Vì thế, trong runbook nên ghi:

~~~text
Application version
Spring Boot version
Spring Kafka version
Kafka client version
Listener factory bean name
Container endpoint ID
Timestamp/pod instance của config log
~~~

Đây là metadata phục vụ đối chiếu, không phải nội dung mặc định bắt buộc trong logContainerConfig.

### 26.1 Đừng lấy log version mới để suy diễn một incident cũ

Nếu một lỗi xảy ra trước rolling deployment, log container config của pod mới có thể phản ánh code/config đã sửa. Muốn xác định root cause phải lấy logs của **instance và phiên bản tại thời điểm lỗi**, kể cả previous container logs nếu pod đã restart.

### 26.2 Tránh viết parser quá chặt

Nếu pipeline đọc log startup thành inventory tự động, ưu tiên custom structured log với schema do ứng dụng sở hữu. Không parse một toString() framework như contract ổn định nhiều năm.

## 27. Một runbook triển khai log container config an toàn

Khi cần điều tra một listener cụ thể trong production:

1. Xác định service, listener ID và Kafka consumer group.
2. Kiểm tra đã có startup config log chưa.
3. Nếu chưa có, xác định đúng factory và bật setLogContainerConfig(true).
4. Đảm bảo logger Spring Kafka listener cho phép INFO.
5. Kiểm tra cấu hình không in secrets và log policy phù hợp.
6. Triển khai canary/rolling deployment có kiểm soát.
7. Thu logs đúng pod và đúng build version.
8. Đối chiếu AckMode, poll, pause, idle/monitor và các thuộc tính khả dụng.
9. Đối chiếu annotation overrides, actual group ID và concurrency.
10. Kiểm tra Kafka client config/assignment/offset riêng.
11. Kết hợp application events, lag, retries, DLT, transaction outcomes để xác định root cause.
12. Khi xong, quyết định giữ flag bật hay tắt dựa trên log volume và policy.
13. Ghi lại effective configuration cần thiết trong incident report, không đính kèm secrets.
14. Cập nhật test để phát hiện config drift nếu lỗi có thể lặp lại.

**Không restart toàn bộ Kafka consumers chỉ để lấy log khi sự cố đang diễn ra nếu việc restart có thể làm mất dấu vết và tạo rebalance không cần thiết.** Trước tiên khai thác các logs/state hiện có; chỉ rollout khi phù hợp với incident priority.

## 28. Các hiểu nhầm phổ biến

**“logContainerConfig=true sẽ log từng Kafka record.”** Sai. Nó là startup container configuration logging.

**“Bật logContainerConfig là đã có đầy đủ consumer properties.”** Sai. KafkaConsumer client config và container config thuộc các tầng khác nhau.

**“Log hiển thị listener running nghĩa nó đã được gán partitions.”** Sai. Runtime assignment cần kiểm tra riêng.

**“Container config đúng chứng minh offsets đã commit đúng.”** Sai. Commit success là một outcome runtime.

**“Container config đúng chứng minh Kafka transaction atomic.”** Sai. Cần transaction manager/factory wiring và integration test.

**“Cấu hình trên một factory áp dụng cho mọi @KafkaListener.”** Sai. Chỉ listeners dùng factory đó mới được thừa hưởng.

**“logContainerConfig giúp xem mọi thay đổi runtime theo thời gian.”** Sai. Nó chủ yếu ghi snapshot lúc start.

**“Không thấy log nghĩa là flag=false.”** Không nhất thiết. Có thể logger lọc INFO, container chưa start, logs bị mất hoặc factory khác đang được dùng.

**“Một @KafkaListener có một KafkaConsumer duy nhất.”** Không khi concurrency>1.

**“@KafkaListener.id chỉ là tên hiển thị.”** Không hẳn. Registry và đôi khi group.id phụ thuộc ID khi idIsGroup=true.

**“Phải bật root DEBUG để xem container config.”** Không. Dùng INFO ở logger container phù hợp.

**“Log toàn bộ config luôn an toàn.”** Không. Metadata nội bộ và các giá trị nhạy cảm có thể xuất hiện; cần sanitization và kiểm soát truy cập.

**“Bật flag không thể ảnh hưởng vận hành theo bất kỳ cách nào.”** Bản thân flag không đổi behavior, nhưng deployment/restart để bật nó có thể gây rebalance.

## 29. Checklist trước và sau khi bật

**Phạm vi**

- [ ] Xác định đúng listener ID và factory bean.
- [ ] Đã đọc effective annotation groupId/concurrency/topics.
- [ ] setLogContainerConfig(true) được đặt trước container startup.
- [ ] Không tạo factory mới làm mất error handler/transaction settings.
- [ ] Biết container có autoStartup=false không.

**Logging**

- [ ] Spring Kafka listener logger cho phép INFO.
- [ ] Log collector nhận logs lúc startup.
- [ ] Log có service/instance/version/timestamp.
- [ ] Không log raw credentials hoặc Kafka payload.
- [ ] Có retention và access control phù hợp.
- [ ] Log volume được cân nhắc theo số containers/pods.

**Chẩn đoán**

- [ ] Phân biệt container properties và Kafka client properties.
- [ ] Xác minh runtime group membership/partition assignment.
- [ ] Xác minh committed offsets khi điều tra AckMode.
- [ ] Xác minh pause requested/effective khi điều tra backpressure.
- [ ] Xác minh error handler/BackOff/DLT riêng.
- [ ] Xác minh Kafka transaction outcomes riêng khi dùng EOS.
- [ ] Dùng metrics/tracing để quan sát runtime, không chỉ startup snapshot.

**Kiểm chứng**

- [ ] Đã thử bật flag trên staging.
- [ ] Đã quan sát log startup của listener thật.
- [ ] Đã thử trường hợp flag=false.
- [ ] Đã test factory wiring và @KafkaListener overrides.
- [ ] Đã kiểm tra sanitization của custom inventory.
- [ ] Đã có runbook giữ/tắt flag sau incident.

## 30. Tài liệu tham khảo

- Spring for Apache Kafka — Listener Container Properties: https://docs.spring.io/spring-kafka/reference/kafka/container-props.html
- Spring for Apache Kafka — Message Listener Containers: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html
- Spring Kafka API — ContainerProperties: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/ContainerProperties.html
- Spring Kafka API — KafkaListenerEndpointRegistry: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/config/KafkaListenerEndpointRegistry.html
- Apache Kafka consumer configuration: https://kafka.apache.org/documentation/#consumerconfigs

Các đường dẫn trên là điểm tham khảo; cần đối chiếu version Spring Kafka/Kafka client thực tế của dự án trước khi áp dụng API/cấu hình.

## 31. Kết luận

**logContainerConfig** là một thuộc tính đơn giản nhưng hữu ích của **ContainerProperties**: khi bật, Spring Kafka ghi thông tin cấu hình listener container ở mức **INFO khi container khởi động**. Nó giúp giảm thời gian điều tra những lỗi do khác biệt giữa YAML, Spring Boot auto-configuration, listener factory và @KafkaListener annotation.

Giá trị thực sự của tính năng nằm ở việc dùng **đúng phạm vi**. Nó không phải bản dump toàn bộ Kafka client properties, không thay thế runtime assignment/offset/transaction metrics, không theo dõi mọi thay đổi sau startup và không bảo đảm nội dung cấu hình hoàn toàn không nhạy cảm. Kết hợp log config đã được bảo vệ với listener ID, group ID, client ID, Kafka consumer metrics, application events và integration tests sẽ tạo ra một quy trình chẩn đoán đáng tin cậy mà không cần bật DEBUG tràn lan hoặc vô tình thay đổi behavior xử lý Kafka.


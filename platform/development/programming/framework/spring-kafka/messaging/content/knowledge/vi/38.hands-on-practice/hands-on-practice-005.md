# Tách consumer group cho billing và notification

Trong một hệ thống xử lý đơn hàng, cùng một sự kiện OrderCreated thường cần kích hoạt nhiều nghiệp vụ độc lập. Billing tạo hóa đơn hoặc ghi nhận khoản phải thu; Notification gửi email hoặc thông báo cho khách hàng. Hai luồng này cần nhận cùng một sự kiện, có thể chạy với tốc độ khác nhau và không được chia record cho nhau.

Kafka giải quyết bài toán này bằng consumer group. Billing và Notification dùng chung topic orders nhưng có group ID riêng. Mỗi group có offset và tiến độ đọc độc lập, vì vậy cả hai đều nhận được toàn bộ record. Nếu hai listener dùng chung group ID, Kafka sẽ phân phối partition giữa chúng để chia tải; một record có thể đến Billing hoặc Notification tùy assignment, thay vì được phát cho cả hai.

Bài thực hành này xây dựng producer phát OrderCreated, hai listener tiêu thụ cùng topic bằng hai consumer group độc lập, sau đó kiểm tra offset, partition assignment và hành vi khi scale nhiều instance.

## 1. Mục tiêu và kiến trúc

Sau bài thực hành, bạn có thể:

- Tạo topic orders có nhiều partition.
- Phát event OrderCreated bằng KafkaTemplate.
- Cấu hình listener Billing dùng group billing-service.
- Cấu hình listener Notification dùng group notification-service.
- Chứng minh hai group đều nhận cùng một record.
- Scale nhiều instance trong cùng group để chia tải.
- Quan sát offset và consumer assignment bằng Kafka CLI.
- Hiểu retry, duplicate và idempotency ở từng consumer group.

Kiến trúc mục tiêu:

~~~mermaid
flowchart TD
    API[Order Service / Producer] -->|OrderCreated| T[(orders topic)]
    T --> P0[Partition 0]
    T --> P1[Partition 1]
    T --> P2[Partition 2]
    P0 --> B[Billing consumer group]
    P1 --> B
    P2 --> B
    P0 --> N[Notification consumer group]
    P1 --> N
    P2 --> N
    B --> DB[(Billing database)]
    N --> MAIL[Email / notification provider]
~~~

Hai group đọc độc lập cùng log của topic. Trên cùng một partition, Billing có thể xử lý record tại offset 100 trong khi Notification vẫn đang xử lý offset 85. Kafka không yêu cầu hai group phải cùng tốc độ hoặc cùng committed offset.

Trong mỗi group, các instance chia partition với nhau. Giữa hai group, mỗi group được gán partition độc lập và có thể đọc toàn bộ partition của topic.

## 2. Chuẩn bị project

Dùng một ứng dụng Spring Boot có Spring Kafka và một Kafka broker có thể truy cập từ ứng dụng. Với Maven, dependency chính là:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
~~~

Nếu project dùng Spring Boot dependency management, không cần tự đặt version Spring Kafka trừ khi có lý do tương thích cụ thể. Đối với integration test bằng embedded broker, thêm dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Các ví dụ dưới đây dùng Java record và JSON serialization. Hãy dùng cùng phiên bản Spring Boot/Spring Kafka trong project và broker local đã sẵn sàng trước khi chạy lab.

## 3. Cấu hình topic, producer và consumer

Tạo application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      auto-offset-reset: earliest
      enable-auto-commit: false
      properties:
        spring.json.trusted.packages: com.example.messaging
        spring.json.value.default.type: com.example.messaging.OrderCreated
        spring.json.use.type.headers: false

app:
  kafka:
    topics:
      orders: orders
    groups:
      billing: billing-service
      notification: notification-service
    billing:
      concurrency: 2
    notification:
      concurrency: 1
~~~

Giải thích:

- bootstrap-servers trỏ tới Kafka broker.
- Producer dùng StringSerializer cho key và JsonSerializer cho event.
- Consumer dùng StringDeserializer và JsonDeserializer.
- default type chỉ định class Java để deserialize payload.
- trusted.packages giới hạn package được phép deserialize.
- auto-offset-reset: earliest áp dụng khi group chưa có committed offset hợp lệ.
- Hai group ID khác nhau là phần cốt lõi để hai luồng nhận độc lập.
- Concurrency có thể điều chỉnh theo số partition và năng lực xử lý.

Vì hai listener nhận cùng kiểu event OrderCreated, có thể dùng chung ConsumerFactory. Nếu Billing và Notification cần serializer, deserializer hoặc error handling khác nhau, hãy tạo container factory riêng cho từng listener thay vì làm cấu hình chung trở nên khó kiểm soát.

## 4. Tạo topic orders

Trong môi trường local, có thể khai báo topic bằng Spring Kafka:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;
import org.apache.kafka.clients.admin.NewTopic;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic(
            @Value("${app.kafka.topics.orders}") String topicName) {

        return TopicBuilder.name(topicName)
                .partitions(3)
                .replicas(1)
                .build();
    }
}
~~~

Topic có ba partition để dễ quan sát việc phân phối giữa các consumer. Replication factor 1 phù hợp với broker local đơn lẻ; môi trường production cần replication factor theo chính sách chịu lỗi của cluster.

Nếu topic đã được quản lý bằng Terraform, Helm, Kafka operator hoặc quy trình hạ tầng riêng, có thể bỏ bean NewTopic và provision topic bên ngoài. Không nên để mọi application instance tùy ý thay đổi topology production khi khởi động.

Kiểm tra topic:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
~~~

Kết quả cần xác nhận topic tồn tại và có ba partition. Ghi lại partition ID để đối chiếu với log listener.

## 5. Khai báo event OrderCreated

Tạo event dùng chung cho cả hai consumer:

~~~java
package com.example.messaging;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal totalAmount,
        String currency,
        Instant occurredAt
) {
}
~~~

Các trường có ý nghĩa:

- eventId là định danh duy nhất của event, dùng cho idempotency và điều tra.
- orderId là khóa nghiệp vụ của đơn hàng.
- customerId xác định khách hàng nhận thông báo.
- totalAmount và currency cung cấp dữ liệu cho Billing.
- occurredAt là thời điểm nghiệp vụ tạo event.

Dùng orderId làm Kafka key giúp các event của cùng một đơn hàng thường được định tuyến vào cùng partition, nhờ đó giữ thứ tự trong phạm vi key theo partitioner đang dùng.

Không đưa dữ liệu thanh toán nhạy cảm hoặc thông tin xác thực vào event. Nếu hai consumer cần dữ liệu khác nhau, hãy xác định event contract tối thiểu và phân quyền topic phù hợp.

## 6. Phát event bằng KafkaTemplate

Tạo publisher:

~~~java
package com.example.messaging;

import java.util.concurrent.CompletableFuture;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;
    private final String ordersTopic;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate,
            @Value("${app.kafka.topics.orders}") String ordersTopic) {
        this.kafkaTemplate = kafkaTemplate;
        this.ordersTopic = ordersTopic;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate.send(
                ordersTopic,
                event.orderId(),
                event
        );
    }
}
~~~

Producer gửi event vào topic orders với key là orderId. Future cho phép caller quan sát kết quả gửi:

Ví dụ dùng API Spring Kafka 3.x, trong đó send() trả về CompletableFuture. Nếu project dùng Spring Kafka 2.x, kiểu future và cách đăng ký callback có thể là ListenableFuture; hãy điều chỉnh theo version đang quản lý.

~~~java
publisher.publish(event)
        .whenComplete((result, error) -> {
            if (error != null) {
                log.error("Cannot publish OrderCreated eventId={}",
                        event.eventId(), error);
                return;
            }

            var metadata = result.getRecordMetadata();

            log.info(
                    "Published eventId={} topic={} partition={} offset={}",
                    event.eventId(),
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
            );
        });
~~~

Không ghi log "đã phát thành công" ngay sau khi gọi send() nếu chưa quan sát kết quả future. Khi broker xác nhận, metadata cung cấp partition và offset để đối chiếu với consumer.

## 7. Tạo Billing consumer group

Billing listener dùng group ID billing-service:

~~~java
package com.example.messaging.billing;

import com.example.messaging.OrderCreated;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class BillingOrderListener {

    private final BillingService billingService;

    public BillingOrderListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
            id = "billing-orders-listener",
            topics = "${app.kafka.topics.orders}",
            groupId = "${app.kafka.groups.billing}",
            concurrency = "${app.kafka.billing.concurrency:2}"
    )
    public void onOrderCreated(OrderCreated event) {
        billingService.createInvoice(event);
    }
}
~~~

Với group ID billing-service, Kafka lưu committed offset riêng cho Billing. Billing có thể xử lý event nhanh hoặc chậm mà không làm thay đổi offset của Notification.

Trong ví dụ, BillingService đại diện cho logic nghiệp vụ tạo hóa đơn. Trong ứng dụng thật, thao tác database cần có transaction và idempotency theo eventId hoặc orderId để xử lý an toàn khi record được giao lại.

## 8. Tạo Notification consumer group

Notification listener cũng subscribe topic orders nhưng dùng group ID notification-service:

~~~java
package com.example.messaging.notification;

import com.example.messaging.OrderCreated;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class NotificationOrderListener {

    private final NotificationService notificationService;

    public NotificationOrderListener(
            NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @KafkaListener(
            id = "notification-orders-listener",
            topics = "${app.kafka.topics.orders}",
            groupId = "${app.kafka.groups.notification}",
            concurrency = "${app.kafka.notification.concurrency:1}"
    )
    public void onOrderCreated(OrderCreated event) {
        notificationService.sendOrderConfirmation(event);
    }
}
~~~

Điểm quan trọng là hai annotation có cùng topic nhưng groupId khác nhau. Kafka tạo tiến độ độc lập:

- billing-service đọc toàn bộ event của topic theo offset riêng.
- notification-service cũng đọc toàn bộ event của topic theo offset riêng.
- Billing không lấy mất record của Notification.
- Notification không làm thay đổi committed offset của Billing.

Nếu Notification chậm vì nhà cung cấp email gặp sự cố, Billing vẫn có thể tiếp tục xử lý. Lag của Notification tăng riêng trong group notification-service.

## 9. Điều gì xảy ra nếu hai listener dùng chung group ID?

Để thấy sự khác biệt, thử đổi cả hai groupId thành cùng giá trị order-processors.

Khi đó, hai listener tham gia cùng một consumer group. Kafka xem chúng là các consumer thành viên của cùng một nhóm và phân phối partition cho các thành viên. Một record chỉ được một consumer trong group xử lý theo assignment của partition.

Ví dụ:

| Partition | Consumer được gán trong group order-processors |
|---|---|
| orders-0 | Billing listener |
| orders-1 | Notification listener |
| orders-2 | Billing listener |

Kết quả: một số event có thể chạy qua Billing, số khác qua Notification. Không bảo đảm cả hai nghiệp vụ cùng nhận mọi event. Đây là mô hình competing consumers để chia tải, không phải broadcast.

Để Billing và Notification cùng nhận toàn bộ event, phải giữ group ID riêng:

~~~text
orders topic
  ├── billing-service      -> đọc toàn bộ partitions
  └── notification-service -> đọc toàn bộ partitions
~~~

Không cần tạo hai topic riêng chỉ để hai service nhận cùng một event. Một topic với nhiều consumer group thường là thiết kế phù hợp khi các consumer cần tiến độ và mục tiêu xử lý độc lập.

## 10. Chạy lab và gửi event mẫu

Khởi động Kafka broker, sau đó chạy Spring Boot application. Khi listener start, hai consumer group sẽ join topic orders và nhận partition assignment.

Tạo event mẫu bằng cách gọi publisher từ REST endpoint, CommandLineRunner hoặc một test fixture. Ví dụ dùng CommandLineRunner chỉ để chạy local:

~~~java
package com.example.messaging;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SampleOrderRunnerConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(SampleOrderRunnerConfiguration.class);

    @Bean
    CommandLineRunner publishSampleOrder(OrderEventPublisher publisher) {
        return args -> {
            var event = new OrderCreated(
                    UUID.randomUUID().toString(),
                    "ORD-1001",
                    "CUS-2001",
                    new BigDecimal("125000.00"),
                    "VND",
                    Instant.now()
            );

            publisher.publish(event)
                    .whenComplete((result, error) -> {
                        if (error != null) {
                            log.error("Publish failed", error);
                        }
                        else {
                            log.info("Sample order published at partition={} offset={}",
                                    result.getRecordMetadata().partition(),
                                    result.getRecordMetadata().offset());
                        }
                    });
        };
    }
}
~~~

Mỗi lần chạy runner sẽ phát một event mới. Khi test nhiều lần, có thể phát 10-20 event với các orderId khác nhau để quan sát phân phối partition.

CommandLineRunner chạy một lần trên mỗi application instance. Chỉ bật ví dụ này khi chạy một instance để tạo dữ liệu mẫu; khi thử scale nhiều instance, hãy tắt runner hoặc dùng một endpoint/test producer riêng để tránh mỗi pod tự phát thêm event.

Log mong đợi có cùng eventId xuất hiện ở cả Billing và Notification, dù thứ tự log giữa hai listener có thể khác nhau:

~~~text
Billing received eventId=evt-101 orderId=ORD-1001
Notification received eventId=evt-101 orderId=ORD-1001
~~~

Không yêu cầu hai listener xử lý đồng thời hoặc hoàn tất cùng thời điểm. Chúng có consumer thread, offset và tốc độ độc lập.

## 11. Xác minh hai consumer group trên Kafka CLI

Liệt kê group:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list
~~~

Mong đợi thấy hai group:

~~~text
billing-service
notification-service
~~~

Xem Billing:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group billing-service
~~~

Xem Notification:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group notification-service
~~~

Mỗi group sẽ có các dòng topic orders cho các partition mà group đang quản lý. So sánh:

- GROUP: group ID khác nhau.
- TOPIC: cùng là orders.
- PARTITION: cả hai group đều có assignment cho toàn bộ partition, nếu có đủ consumer hoạt động.
- CURRENT-OFFSET: tiến độ commit độc lập.
- LOG-END-OFFSET: cùng tham chiếu log của topic.
- LAG: có thể khác nhau do tốc độ xử lý khác nhau.
- CONSUMER-ID: instance thuộc group tương ứng.

Nếu cả hai group đều đã xử lý xong cùng lượng record, committed offset có thể bằng nhau. Khi Notification bị chậm, lag của notification-service tăng nhưng lag của billing-service vẫn có thể bằng 0.

## 12. Thử nghiệm scale nhiều instance

Giả sử topic orders có ba partition:

- Billing concurrency = 2.
- Notification concurrency = 1.
- Chạy hai application instance.

Tổng consumer có thể là:

| Group | Concurrency mỗi instance | Số instance | Tổng consumer | Partition |
|---|---:|---:|---:|---:|
| billing-service | 2 | 2 | 4 | 3 |
| notification-service | 1 | 2 | 2 | 3 |

Trong group Billing, tối đa ba consumer được gán partition; consumer thứ tư có thể idle. Trong group Notification, hai consumer chia ba partition. Hai group độc lập nên assignment của Billing không ảnh hưởng assignment của Notification.

Thử tăng topic lên sáu partition trong môi trường lab hoặc tạo topic mới sáu partition, rồi quan sát khả năng scale. Không tăng partition production chỉ để thử nghiệm vì thay đổi này có thể ảnh hưởng key-to-partition mapping và ordering.

## 13. Chứng minh offset độc lập

Để minh họa offset dễ đọc, giả sử đang xét riêng một partition có log end offset là 20. Billing đã xử lý đến vị trí tiếp theo 20, còn Notification mới commit vị trí tiếp theo 12 do service gửi email bị chậm.

Trạng thái minh họa:

| Group | Log end offset | Committed offset | Lag minh họa |
|---|---:|---:|---:|
| billing-service | 20 | 20 | 0 |
| notification-service | 20 | 12 | 8 |

Trong topic ba partition của lab, cần đọc bảng tương ứng cho từng partition; không cộng các offset của các partition thành một offset toàn topic. Offset trong Kafka bắt đầu từ 0 và committed offset thường biểu thị vị trí tiếp theo cần đọc, nên khi tính lag cần dùng đúng semantics của công cụ.

Khi Notification phục hồi, nó tiếp tục từ offset đã commit của chính group đó. Billing không cần đọc lại event chỉ vì Notification đang xử lý backlog.

Đây là lợi ích chính của group riêng: mỗi consumer logic có thể tiến triển, retry và vận hành độc lập.

## 14. Thử nghiệm Notification chậm hoặc ngừng hoạt động

Tạm dừng Notification listener hoặc dừng application instance chứa listener đó. Sau đó tiếp tục phát event.

Quan sát:

- Billing vẫn nhận và xử lý event mới.
- Notification group không tiến offset hoặc lag tăng.
- Khi Notification khởi động lại, nó tiếp tục từ committed offset của group.
- Billing không bị kéo lùi offset do Notification restart.

Nếu Billing và Notification dùng chung group ID, việc dừng một listener có thể thay đổi assignment và khiến consumer còn lại nhận các partition trước đó. Điều này có thể làm một số event được xử lý bởi service không đúng nghiệp vụ.

Với group ID riêng, failure của Notification không làm Billing nhận partition của Notification hoặc ngược lại. Hai service vẫn dùng chung broker/topic nên sự cố broker hoặc topic vẫn có thể ảnh hưởng cả hai.

## 15. Retry và DLT độc lập theo consumer group

Billing và Notification có thể có chính sách retry khác nhau:

- Billing retry lỗi database theo backoff ngắn và có giới hạn.
- Notification retry lỗi nhà cung cấp email theo backoff dài hơn.
- Mỗi luồng có DLT và runbook xử lý riêng.

Nếu dùng @RetryableTopic, cần thiết kế retry topic theo listener/group và naming strategy để tránh va chạm giữa các luồng. Kiểm tra topic phụ trợ được tạo đúng, retention phù hợp và quyền ACL đủ cho producer/consumer.

Một event có thể thành công ở Billing nhưng thất bại ở Notification và đi vào DLT của Notification. Không nên coi event đó là thất bại toàn cục nếu nghiệp vụ Billing đã hoàn tất. Cần có trạng thái xử lý riêng theo consumer hoặc theo bounded context.

## 16. Idempotency cho từng consumer

Kafka consumer có thể nhận lại record khi rebalance, process crash trước khi commit offset hoặc retry. Group riêng không loại bỏ duplicate; nó chỉ tách tiến độ.

Mỗi consumer nên có cơ chế idempotency phù hợp:

- Billing lưu eventId hoặc orderId đã tạo invoice để không tạo hóa đơn hai lần.
- Notification lưu notificationId hoặc eventId và loại thông báo để tránh gửi email trùng.
- Dùng unique constraint hoặc atomic insert để xử lý hai lần giao đồng thời.
- Với API ngoài, dùng idempotency key nếu nhà cung cấp hỗ trợ.

Không dùng chung bảng dedup giữa Billing và Notification theo cách khiến một consumer đánh dấu event đã xử lý rồi ngăn consumer còn lại thực hiện nghiệp vụ của nó. Khóa idempotency cần có phạm vi consumer logic, ví dụ (consumer_name, event_id).

Nếu cần đồng bộ database và phát event, xem xét transactional outbox. Kafka transaction giữa các record Kafka không tự rollback database hoặc email đã gửi.

## 17. Kiểm thử tích hợp hai group

Một integration test nên xác minh cả hai group nhận cùng event. Có thể dùng @EmbeddedKafka hoặc Testcontainers và tạo topic có ít nhất một partition cho test đơn giản.

Các bước kiểm thử:

1. Khởi động broker thử nghiệm và tạo topic orders.
2. Khởi động listener Billing với group billing-test.
3. Khởi động listener Notification với group notification-test.
4. Chờ cả hai listener nhận partition assignment.
5. Gửi một OrderCreated có eventId cố định.
6. Chờ Billing nhận event và xác nhận eventId.
7. Chờ Notification nhận cùng eventId.
8. Gửi nhiều event và xác nhận mỗi group nhận đủ số lượng.
9. Tạm dừng một listener, tiếp tục gửi event và xác nhận group còn lại vẫn xử lý.
10. Khởi động lại listener đã dừng và xác nhận nó đọc backlog từ offset riêng.

Trong test, dùng topic và group ID riêng cho test run để tránh dữ liệu từ test khác. Dùng latch/queue có timeout thay vì Thread.sleep cố định; sleep chỉ trì hoãn test và không chứng minh consumer đã assignment.

Không chỉ assert log được in ra. Nên ghi nhận eventId vào test sink hoặc mock service để xác nhận mỗi group thực sự gọi đúng business handler.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Chỉ Billing hoặc Notification nhận event | Hai listener vô tình dùng cùng group ID | Đặt group ID riêng cho từng consumer logic |
| Một group không xuất hiện trong CLI | Listener chưa start, sai group property hoặc không subscribe topic | Kiểm tra registry, log startup và annotation |
| Consumer idle dù group có nhiều instance | Số consumer lớn hơn số partition | Điều chỉnh concurrency hoặc partition sau khi benchmark |
| Notification xử lý lại nhiều event cũ | Group mới chưa có offset và auto.offset.reset=earliest | Xác định chính sách khởi tạo offset |
| Billing lag thấp nhưng Notification lag cao | Notification chậm hoặc dependency lỗi | Điều tra riêng group Notification và downstream |
| Tạo hóa đơn hoặc gửi email trùng | Record được giao lại và handler chưa idempotent | Dedup theo eventId trong phạm vi consumer |
| Cả hai listener nhận event nhưng thứ tự hoàn tất khác nhau | Hai group có tốc độ và scheduling độc lập | Không phụ thuộc thứ tự hoàn tất giữa hai service |
| Thay đổi concurrency gây rebalance | Consumer membership thay đổi | Theo dõi assignment và xử lý in-flight an toàn |

## 19. Checklist hoàn thành bài thực hành

- [ ] Topic orders tồn tại và có ba partition trong lab.
- [ ] Producer gửi OrderCreated với key là orderId.
- [ ] Billing listener dùng group billing-service.
- [ ] Notification listener dùng group notification-service.
- [ ] Hai listener cùng subscribe topic orders.
- [ ] Cùng eventId xuất hiện trong cả hai business handler.
- [ ] CLI hiển thị hai consumer group riêng biệt.
- [ ] Mỗi group có assignment cho các partition của topic.
- [ ] Lag và committed offset được theo dõi riêng.
- [ ] Dừng Notification không làm Billing ngừng xử lý.
- [ ] Khởi động lại Notification giúp xử lý backlog.
- [ ] Concurrency không vượt quá số partition có ích.
- [ ] Retry/DLT được thiết kế riêng theo luồng nghiệp vụ.
- [ ] Billing và Notification có idempotency độc lập.
- [ ] Integration test xác nhận cả hai group nhận cùng event.

## 20. Mở rộng sau bài thực hành

Sau khi lab chạy ổn định, có thể mở rộng theo các hướng:

- Thêm Analytics consumer group để tính báo cáo mà không sửa producer.
- Thêm Audit consumer group để lưu lịch sử event.
- Dùng schema versioning để thay đổi OrderCreated an toàn.
- Cấu hình retry topic và DLT riêng cho Billing/Notification.
- Bổ sung Micrometer metrics cho lag, processing time và failure rate.
- Dùng transactional outbox để đảm bảo trạng thái đơn hàng và event được ghi bền vững cùng nhau.
- Dùng consumer deployment độc lập để scale Billing và Notification theo tải riêng.

Mô hình một topic với nhiều consumer group giúp một event phục vụ nhiều bounded context mà vẫn giữ tiến độ xử lý độc lập. Billing và Notification dùng chung topic orders nhưng phải có group ID riêng; các instance của cùng một service dùng chung group ID để chia partition. Khi hoàn tất lab, hãy xác nhận cùng eventId xuất hiện ở cả hai consumer, quan sát offset/lag riêng và thử dừng một luồng để chứng minh luồng còn lại tiếp tục hoạt động.


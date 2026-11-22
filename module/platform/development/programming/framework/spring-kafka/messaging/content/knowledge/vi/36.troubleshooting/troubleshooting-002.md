# Topic không tồn tại

Lỗi topic không tồn tại xảy ra khi producer, consumer hoặc listener container tham chiếu đến một Kafka topic chưa được tạo trên cluster mà ứng dụng đang kết nối. Nguyên nhân thường là sai tên topic, tạo topic chưa hoàn tất, cấu hình bootstrap server trỏ nhầm môi trường hoặc cluster không cho phép auto-create topic. Một số lỗi khác như thiếu quyền, partition chưa có leader hoặc broker chưa sẵn sàng có thể trông giống lỗi topic missing nhưng cần cách xử lý khác.

Trong module `SPRING_KAFKA_MESSAGING`, producer gửi event bằng `KafkaTemplate`, consumer nhận event bằng `@KafkaListener`. Topic là tài nguyên được quản lý ở Kafka cluster; tên trong code chỉ là tham chiếu. Vì vậy, cần xác minh topic trên đúng cluster, đúng tên và đúng partition trước khi sửa retry hoặc thay đổi listener.

~~~mermaid
flowchart TD
    A[Producer / Consumer báo topic error] --> B{Topic có trên đúng cluster?}
    B -->|Không| C[Kiểm tra tên và bootstrap server]
    C --> D[Provision topic]
    B -->|Có| E{Partition có leader?}
    E -->|Không| F[Kiểm tra broker/controller]
    E -->|Có| G{Có lỗi authorization?}
    G -->|Có| H[Kiểm tra principal và ACL]
    G -->|Không| I[Kiểm tra metadata, timeout và client config]
    D --> J[Thử gửi/nhận record]
    F --> J
    H --> J
    I --> J
~~~

Các ví dụ event/listener trong bài dùng contract đơn giản sau:

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId
) {}

public interface OrderApplicationService {
    void handle(OrderCreatedEvent event);
}
~~~

## 1. Nhận diện lỗi topic không tồn tại

Một số exception/log thường gặp:

| Dấu hiệu | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| `UnknownTopicOrPartitionException` | Broker chưa tìm thấy topic/partition trong metadata hiện tại | Kiểm tra tên, topic tồn tại và metadata refresh |
| `LEADER_NOT_AVAILABLE` / `LeaderNotAvailableException` | Partition chưa có leader khả dụng, thường gặp lúc tạo topic hoặc bầu leader | Kiểm tra trạng thái partition và broker |
| `TopicAuthorizationException` | Principal không có quyền thao tác với topic | Kiểm tra ACL và identity của ứng dụng |
| `InvalidTopicException` | Tên topic không hợp lệ | Kiểm tra ký tự, độ dài và quy ước đặt tên |
| `TimeoutException` | Request không hoàn tất trong thời gian cho phép | Kiểm tra broker, network, metadata và timeout |
| `InvalidReplicationFactorException` | Replication factor yêu cầu lớn hơn khả năng broker hiện có | Kiểm tra số broker và cấu hình replica |

`UnknownTopicOrPartitionException` không phải lúc nào cũng chứng minh topic chưa từng tồn tại. Nó cũng có thể xuất hiện khi metadata cũ, partition không hợp lệ hoặc topic vừa được tạo nhưng metadata chưa lan truyền đến client. Hãy đối chiếu với kết quả AdminClient/CLI và trạng thái broker trước khi kết luận.

## 2. Phân biệt topic missing với leader chưa sẵn sàng

Topic vừa được tạo có thể đã xuất hiện trong metadata nhưng partition chưa có leader ổn định. Trong giai đoạn này, producer/consumer có thể tạm thời gặp lỗi leader hoặc metadata.

| Trạng thái | Cách nhận biết | Hành động |
|---|---|---|
| Topic không có trong danh sách | --list không thấy tên topic trên cluster đích | Kiểm tra tên và tạo/provision topic |
| Topic tồn tại nhưng partition thiếu leader | --describe hiển thị leader -1 hoặc trạng thái bất thường | Kiểm tra broker/controller và chờ election hoàn tất |
| Topic tồn tại, leader bình thường nhưng bị từ chối | Exception authorization | Cấp ACL phù hợp |
| Topic tồn tại ở cluster khác | Cluster ID/bootstrap server không đúng | Sửa cấu hình môi trường |

Không nên xử lý `TopicAuthorizationException` bằng cách tạo lại topic. Cũng không nên tăng retry vô hạn khi broker từ chối vì ACL; retry không thể tự cấp quyền.

## 3. Kiểm tra tên topic trong ứng dụng

Tên topic phải khớp chính xác giữa producer, listener, cấu hình và hạ tầng. Kafka phân biệt chữ hoa/chữ thường, do đó `orders.created` và `Orders.Created` là hai tên khác nhau.

Các lỗi thường gặp:

- Sai chính tả hoặc khác chữ hoa/chữ thường.
- Producer dùng suffix theo môi trường, còn listener dùng tên cố định.
- Profile Spring Boot không được kích hoạt nên nạp nhầm topic name.
- Tên topic trong `@KafkaListener` khác với tên được provision trong môi trường.
- Topic retry hoặc DLT có suffix khác dự kiến.
- Placeholder cấu hình bị rỗng hoặc không được resolve.

Nên gom topic name vào cấu hình tập trung:

~~~yaml
app:
  kafka:
    topics:
      orders-created: orders.created
      shipments-requested: shipments.requested
~~~

Inject cấu hình đó vào publisher/listener hoặc dùng property placeholder trực tiếp trong annotation:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-service"
)
public void listen(OrderCreatedEvent event) {
    orderService.handle(event);
}
~~~

Tránh hard-code cùng một tên ở nhiều class. Nếu topic name phụ thuộc environment, kiểm tra giá trị đã resolve lúc khởi động và so sánh với tên được tạo trên cluster.

## 4. Xác minh ứng dụng đang kết nối đúng Kafka cluster

Topic có thể tồn tại ở development nhưng không tồn tại ở staging/production. Trước khi tạo topic, xác minh `bootstrap.servers` mà ứng dụng đang dùng.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: orders-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.acme.orders.OrderCreatedEvent
        spring.json.trusted.packages: com.acme.orders
~~~

Kiểm tra các điểm sau:

- Biến `KAFKA_BOOTSTRAP_SERVERS` có được truyền vào process/container không?
- Spring profile nào đang active?
- Producer và consumer có dùng cùng cluster không?
- CLI/AdminClient có dùng đúng bootstrap server với ứng dụng không?
- Ứng dụng có kết nối qua đúng listener address của broker trong Docker/Kubernetes không?
- DNS, TLS, SASL và network policy có khiến client kết nối nhầm endpoint không?

Đừng chỉ kiểm tra `localhost:9092` trên máy host nếu ứng dụng chạy trong container. Trong container, `localhost` trỏ về chính container đó; cần dùng service DNS hoặc địa chỉ broker mà container có thể truy cập.

## 5. Kiểm tra topic bằng Kafka CLI

Kafka CLI giúp xác minh trực tiếp trạng thái topic trên cluster:

~~~bash
# Liệt kê topic
kafka-topics.sh --bootstrap-server localhost:9092 --list

# Xem partition, leader và replica
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders.created

# Tạo topic nếu chưa tồn tại
kafka-topics.sh --bootstrap-server localhost:9092 --create --topic orders.created --partitions 3 --replication-factor 1
~~~

Trên Windows distribution, tên script có thể là `kafka-topics.bat`. Dùng cùng bootstrap server, security config và môi trường với ứng dụng để tránh kiểm tra nhầm cluster.

Nếu topic có trong danh sách, đọc output --describe: xác minh số partition, leader và replica. Nếu topic không có, xác minh lại chính tả và cluster trước khi tạo.

## 6. Tạo topic bằng Spring Kafka KafkaAdmin

Spring Kafka có thể tạo topic khi ứng dụng khởi động thông qua bean `NewTopic` và `KafkaAdmin`. Đây là cách phù hợp với môi trường development/test hoặc hệ thống chọn provisioning topic từ application configuration.

~~~java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic ordersCreatedTopic() {
        return TopicBuilder.name("orders.created")
                .partitions(3)
                .replicas(1)
                .build();
    }
}
~~~

Khi Spring Kafka có `KafkaAdmin` và kết nối broker phù hợp, các bean `NewTopic` được dùng để yêu cầu tạo topic. Nếu topic đã tồn tại, việc tạo không có nghĩa topic hiện tại tự động được đổi partition/replication theo mọi thuộc tính trong bean. Muốn thay đổi cấu hình topic hiện hữu, cần quy trình quản trị riêng và kiểm tra giới hạn thay đổi của Kafka.

Replication factor phải phù hợp với số broker khả dụng. Ví dụ `replicas(3)` không thể tạo thành công trên cluster chỉ có một broker. Chọn partition count theo throughput, ordering và concurrency của consumer group; không tạo số partition tùy tiện chỉ để hết lỗi.

## 7. Khi nào nên provision topic ngoài ứng dụng?

Ở production, nhiều tổ chức quản lý topic qua Terraform, Ansible, Helm, Kafka operator hoặc pipeline hạ tầng. Cách này giúp tách quyền tạo topic khỏi quyền runtime của service và kiểm soát partition, replica, retention, cleanup policy, quota, ACL.

| Cách tạo topic | Phù hợp khi | Lưu ý |
|---|---|---|
| `KafkaAdmin` + `NewTopic` | Local, integration test, service nhỏ có ownership rõ | Runtime identity cần quyền tạo topic |
| Kafka CLI/AdminClient | Vận hành thủ công hoặc script quản trị | Cần chạy đúng cluster và audit thay đổi |
| IaC/Kafka operator | Production nhiều service/môi trường | Topic lifecycle được review và version hóa |
| Broker auto-create | Sandbox hoặc môi trường thử nghiệm có kiểm soát | Có thể tạo topic với partition/replica mặc định không phù hợp |

Không nên phụ thuộc broker auto-create cho production nếu topic cần partition count, replication factor hoặc retention cụ thể.

## 8. Cấu hình auto-create topic

Kafka broker có cấu hình `auto.create.topics.enable` quyết định broker có tự tạo topic khi nhận request tham chiếu đến topic chưa tồn tại hay không. Kafka consumer cũng có thuộc tính `allow.auto.create.topics` để kiểm soát việc consumer cho phép broker auto-create topic khi subscribe/fetch.

Hai cấu hình này ở hai phía khác nhau:

- `auto.create.topics.enable`: cấu hình broker.
- `allow.auto.create.topics`: cấu hình consumer.

Nếu broker tắt auto-create, việc producer/consumer tham chiếu topic chưa tồn tại không tự tạo được topic. Đây thường là lựa chọn dễ kiểm soát hơn ở production. Khi auto-create bật, topic có thể được tạo với default broker settings; ứng dụng không nên giả định topic mới có partition/replica/retention như mong muốn.

Auto-create không thay thế quy trình provisioning. Nếu dùng auto-create trong local, vẫn nên khai báo topic rõ ràng để test phản ánh cấu hình thật.

## 9. Phân biệt quyền tạo topic và quyền sử dụng topic

Một ứng dụng có thể có quyền ghi/đọc topic nhưng không có quyền tạo topic. Nếu topic chưa tồn tại và broker không auto-create, producer sẽ không thể tự khắc phục chỉ bằng retry.

Các quyền cần xem xét tùy security model:

- Create topic: cho identity quản trị/provisioning.
- Describe topic: để kiểm tra metadata.
- Write: cho producer.
- Read: cho consumer.
- Group access: cho consumer group.

`TopicAuthorizationException` hoặc `ClusterAuthorizationException` cần được xử lý bằng ACL/role phù hợp. Không cấp quyền `Create` rộng cho mọi service chỉ để tránh lỗi topic missing. Nên để service runtime chỉ có quyền cần thiết, còn provisioning identity có quyền tạo và cấu hình topic.

## 10. Kiểm tra listener startup khi topic chưa tồn tại

`@KafkaListener` subscribe tới topic được khai báo. Nếu topic chưa tồn tại, hành vi startup phụ thuộc cấu hình container, broker auto-create và Kafka client metadata.

Spring Kafka có `missingTopicsFatal` để chọn việc container có fail startup khi topic được khai báo chưa tồn tại hay không. Có thể bật fail-fast trên container factory:

~~~java
factory.getContainerProperties().setMissingTopicsFatal(true);
~~~

Khi bật, ứng dụng phát hiện cấu hình topic sai sớm hơn thay vì chạy trong trạng thái listener chờ topic xuất hiện. Khi để false, container có thể tiếp tục chờ metadata/topic tùy cấu hình và version. `missingTopicsFatal` không tạo topic; nó chỉ điều khiển phản ứng của listener container.

Nếu topic được tạo bằng `KafkaAdmin`, hãy bảo đảm broker sẵn sàng và quá trình tạo topic hoàn tất trước khi kỳ vọng listener xử lý record. Với môi trường yêu cầu fail-fast, cấu hình rõ ràng và kiểm tra startup log.

## 11. Kiểm tra producer send khi topic không tồn tại

Với Spring Kafka 3.x trở lên, `KafkaTemplate.send()` là thao tác bất đồng bộ và trả về `CompletableFuture<SendResult<K,V>>`. Các phiên bản Spring Kafka cũ hơn dùng `ListenableFuture`. Lỗi metadata hoặc broker có thể xuất hiện trong future, vì vậy không nên chỉ kiểm tra việc gọi method không ném exception đồng bộ.

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {

        return kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event
        );
    }
}
~~~

Ở nơi gọi, quan sát future để ghi nhận kết quả:

~~~java
publisher.publish(event).whenComplete((result, exception) -> {
    if (exception != null) {
        log.error("Cannot publish order event: orderId={}",
                event.orderId(), exception);
        return;
    }

    log.debug("Published order event: topic={} partition={} offset={}",
            result.getRecordMetadata().topic(),
            result.getRecordMetadata().partition(),
            result.getRecordMetadata().offset());
});
~~~

Không bỏ qua exception của future. Nếu publish là bước bắt buộc của nghiệp vụ, cần để lỗi được truyền tới retry/outbox hoặc cơ chế xử lý phù hợp; chỉ log rồi coi nghiệp vụ thành công có thể làm mất event.

## 12. Kiểm tra retry topic và dead-letter topic

Lỗi “topic không tồn tại” cũng có thể xảy ra với retry topic hoặc DLT, không chỉ topic nghiệp vụ. Ví dụ `DeadLetterPublishingRecoverer` định tuyến tới `orders.created.DLT` nhưng topic đó chưa được provision.

Checklist cho retry/DLT:

- Xác minh tên topic sau khi áp dụng `retryTopicSuffix` và `dltTopicSuffix`.
- Tạo đủ retry topics và DLT trước khi bật listener nếu broker tắt auto-create.
- Partition count phải tương thích với cách recoverer định tuyến partition.
- DLT producer có serializer hỗ trợ payload thực tế, kể cả raw `byte[]` nếu có deserialize failure.
- Runtime identity có quyền write DLT; listener DLT có quyền read và group access.
- Theo dõi log recovery publish failure, không nhầm với lỗi listener nghiệp vụ.

Với `@RetryableTopic`, topology có thể tạo các retry/DLT destination theo cấu hình. Kiểm tra tài liệu version Spring Kafka và cơ chế `KafkaAdmin` đang dùng; không giả định annotation tự tạo được topic trong mọi cấu hình production.

## 13. Quy trình chẩn đoán theo thứ tự

Khi gặp lỗi topic không tồn tại, xử lý theo trình tự:

1. Ghi lại topic name chính xác từ exception/log.
2. Xác minh Spring profile và property đã resolve trong process.
3. Xác minh bootstrap server/cluster mà ứng dụng kết nối.
4. Dùng Kafka CLI --list và --describe trên đúng cluster.
5. Nếu topic không có, kiểm tra ownership và quy trình provisioning.
6. Nếu topic có nhưng leader thiếu, kiểm tra broker/controller và trạng thái partition.
7. Nếu bị authorization, kiểm tra principal/ACL thay vì tạo topic.
8. Nếu producer send thất bại, đọc exception gốc từ `CompletableFuture`.
9. Nếu listener không nhận record, kiểm tra subscribe pattern, group, assignment và offset sau khi topic đã tồn tại.
10. Sau khi sửa, gửi một record kiểm thử và xác minh listener/producer hoạt động.

Quy trình này giúp tránh thay đổi nhiều cấu hình cùng lúc và tạo ra topic thừa trên nhầm cluster.

## 14. Kiểm thử topic provisioning

Integration test nên xác minh topic thực sự tồn tại và listener có thể xử lý record:

- Khởi tạo broker test với topic được khai báo tường minh.
- Nếu kiểm thử `KafkaAdmin`, khởi động Spring context có `NewTopic` bean và xác minh topic được tạo.
- Nếu kiểm thử topic missing, tắt broker auto-create hoặc dùng tên topic chưa được tạo.
- Xác minh listener behavior khi `missingTopicsFatal` bật và tắt theo cấu hình.
- Gửi record bằng `KafkaTemplate`, chờ send future hoàn tất và xác minh metadata.
- Xác minh listener nhận đúng payload.
- Kiểm thử DLT/retry topic tồn tại và có partition count phù hợp.
- Có test riêng cho ACL nếu ứng dụng dùng SASL/ACL.

Với Embedded Kafka, khai báo topic qua `@EmbeddedKafka(topics = ...)` để fixture rõ ràng. Với Testcontainers, có thể tạo topic bằng AdminClient trong setup. Không để test dựa vào auto-create ngầm vì hành vi đó có thể khác production.

## 15. Những lỗi thường gặp

- **Sai tên topic hoặc khác chữ hoa/chữ thường:** kiểm tra tên resolve thực tế và tên trên broker.
- **Dùng nhầm bootstrap server:** topic có thể tồn tại ở cluster khác.
- **Cho rằng retry sẽ tự tạo topic:** retry chỉ thử lại thao tác, không thay thế provisioning.
- **Nhầm leader chưa sẵn sàng với topic không tồn tại:** kiểm tra partition leader qua --describe.
- **Nhầm authorization với missing topic:** cấp ACL đúng, không tạo lại topic.
- **Bật auto-create trong production mà không kiểm soát default:** topic có thể có partition/replica không phù hợp.
- **DLT/retry topic chưa được tạo:** recovery publish thất bại sau khi listener xử lý lỗi.
- **Không đợi producer future:** lỗi send bất đồng bộ bị bỏ qua.
- **Listener chờ topic nhưng startup không fail:** cấu hình `missingTopicsFatal` theo yêu cầu vận hành.
- **Tạo topic với replication factor lớn hơn số broker:** AdminClient nhận lỗi tạo topic.
- **Dùng localhost sai trong container:** địa chỉ broker không thể truy cập từ network namespace của ứng dụng.

## 16. Checklist xử lý

- [ ] Đã lấy chính xác topic name từ log/exception.
- [ ] Đã xác minh Spring profile và property đã resolve.
- [ ] Đã xác minh bootstrap server và đúng Kafka cluster.
- [ ] Đã kiểm tra topic bằng `kafka-topics --list` và `--describe`.
- [ ] Đã phân biệt topic missing, leader unavailable, invalid topic và authorization.
- [ ] Topic được provision với partition/replica/retention phù hợp.
- [ ] Đã quyết định rõ dùng KafkaAdmin, CLI/IaC hay auto-create.
- [ ] `missingTopicsFatal` phù hợp với yêu cầu startup.
- [ ] Producer quan sát kết quả `KafkaTemplate.send()` future.
- [ ] Retry topic và DLT đã được tạo, cấp quyền và kiểm tra partition.
- [ ] Integration test xác minh topic provisioning và listener hoạt động.
- [ ] Không cấp quyền Create rộng cho service runtime chỉ để né lỗi.

Lỗi topic không tồn tại cần được xử lý từ metadata và trạng thái cluster trước khi điều chỉnh listener. Xác minh đúng tên, đúng bootstrap server, trạng thái partition và ACL; sau đó provision topic bằng cơ chế có kiểm soát. Khi topic chính, retry topic và DLT được tạo đúng cấu hình, `KafkaTemplate` và `@KafkaListener` có thể hoạt động ổn định qua các môi trường triển khai.

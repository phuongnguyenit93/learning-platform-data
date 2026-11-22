# Topic không tồn tại trong Kafka

Trong một ứng dụng Spring Kafka, **topic không tồn tại** nghĩa là broker không trả về metadata cho topic mà ứng dụng đang cần. Tình huống này thường xuất hiện khi `@KafkaListener` đăng ký một topic chưa được tạo, tên topic sai, ứng dụng kết nối nhầm cluster hoặc topic chưa được provision ở môi trường hiện tại.

Cần phân biệt ba trạng thái:

| Trạng thái | Dấu hiệu thường gặp | Ý nghĩa |
|---|---|---|
| Topic không tồn tại | `UnknownTopicOrPartitionException`, mã `UNKNOWN_TOPIC_OR_PARTITION` | Broker đã trả lời nhưng không tìm thấy topic được hỏi |
| Broker không truy cập được | Timeout, disconnect, `BrokerNotAvailableException` | Ứng dụng chưa xác minh được topic vì không liên lạc được với cluster |
| Không đủ quyền | `TopicAuthorizationException`, `TOPIC_AUTHORIZATION_FAILED` | Topic có thể tồn tại nhưng principal của ứng dụng không được phép xem hoặc sử dụng |

Không nên gom cả ba trường hợp thành “topic bị thiếu”. Cách xử lý và thông tin cần báo cho vận hành khác nhau.

## 1. Vì sao topic không tồn tại?

Các nguyên nhân thường gặp:

- Topic chưa được tạo trong cluster của môi trường đang chạy.
- Tên topic trong `@KafkaListener`, producer hoặc cấu hình bị sai chính tả, sai chữ hoa/thường hoặc dùng nhầm tên giữa các môi trường.
- Ứng dụng khởi động trước bước provision topic. Đây là lỗi thứ tự triển khai thường gặp khi nhiều service cùng khởi động.
- `bootstrap.servers` trỏ tới cluster khác với cluster mà đội vận hành đã tạo topic.
- Broker tắt tự động tạo topic, hoặc client không được phép kích hoạt cơ chế đó.
- Topic đã bị xóa, hoặc quá trình tạo topic chưa hoàn tất khi listener kiểm tra metadata.

Một topic có thể tồn tại ở môi trường local nhưng không tồn tại ở staging hoặc production. Vì vậy, khi điều tra cần kiểm tra đúng địa chỉ broker, đúng credentials và đúng tên topic mà tiến trình đang sử dụng.

## 2. Ảnh hưởng tới Spring Kafka listener

Ví dụ listener đăng ký topic `orders`:

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderEvent event) {
    // Xử lý sự kiện đơn hàng
}
```

Khi container khởi động, Spring Kafka cần metadata của topic để xác định partition mà consumer có thể đọc. Nếu topic chưa tồn tại, hành vi khởi động phụ thuộc vào thuộc tính `missingTopicsFatal` của listener container.

- Khi `missingTopicsFatal=true`, container báo lỗi và không khởi động được nếu topic được khai báo chưa tồn tại. Tùy cấu hình vòng đời ứng dụng, lỗi này có thể làm quá trình khởi động application context thất bại.
- Khi `missingTopicsFatal=false`, container có thể khởi động và tiếp tục chờ metadata/partition xuất hiện. Khi topic được tạo và broker cập nhật metadata, consumer có thể bắt đầu nhận partition.

Từ Spring Kafka 2.3, giá trị mặc định của thuộc tính này là `false`; các phiên bản cũ có hành vi mặc định khác. Nên cấu hình tường minh để hành vi không phụ thuộc vào việc nâng cấp thư viện.

Với Spring Boot, có thể giữ cấu hình consumer do Boot cung cấp rồi đặt thuộc tính trên factory:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> kafkaListenerContainerFactory(
        ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    configurer.configure(factory, consumerFactory);

    // Cho phép container chờ topic được tạo sau khi ứng dụng khởi động.
    factory.getContainerProperties().setMissingTopicsFatal(false);
    return factory;
}
```

Nếu không dùng Spring Boot, đặt cùng thuộc tính trên `ConcurrentKafkaListenerContainerFactory` mà ứng dụng tự cấu hình.

`missingTopicsFatal=false` chỉ thay đổi cách listener xử lý topic đang thiếu lúc khởi động. Nó **không tạo topic**, không sửa tên topic và không khắc phục lỗi kết nối hoặc quyền truy cập. Nếu topic là điều kiện bắt buộc để xử lý nghiệp vụ, readiness vẫn cần phản ánh trạng thái thiếu topic.

## 3. Tạo topic một cách có kiểm soát

Topic nên được tạo trước khi ứng dụng cần sử dụng. Có thể quản lý việc provision bằng công cụ hạ tầng như Terraform, Helm, Kafka operator hoặc quy trình quản trị cluster. Cách này giúp cấu hình partition, replication factor và các topic config được xem xét cùng với môi trường triển khai.

Trong ứng dụng Spring Kafka, có thể khai báo `NewTopic` để `KafkaAdmin` tạo topic khi khởi tạo:

```java
@Configuration
class KafkaTopicsConfiguration {

    @Bean
    NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
                .partitions(6)
                .replicas(3)
                .build();
    }
}
```

Spring Boot thường tự cấu hình `KafkaAdmin` khi có cấu hình Kafka phù hợp. Với ứng dụng Spring không dùng Boot, cần đăng ký `KafkaAdmin` và cung cấp cấu hình kết nối broker. Tài khoản quản trị mà ứng dụng dùng phải có quyền tạo topic.

Chọn số partition và replication factor theo tải, số broker và yêu cầu độ sẵn sàng. Ví dụ trên yêu cầu cluster có đủ broker để đáp ứng replication factor là 3; môi trường local một broker thường cần replication factor là 1.

Một số điểm cần lưu ý:

- Khai báo `NewTopic` không thay thế việc quản lý cấu hình hạ tầng. Hãy kiểm tra hành vi của phiên bản Spring Kafka đang dùng khi topic đã tồn tại và cần thay đổi cấu hình.
- Không nên dựa vào `auto.create.topics.enable` của broker để tự tạo topic trong production. Topic có thể được tạo với partition hoặc replication factor mặc định không phù hợp; lỗi gõ tên topic cũng có thể tạo ra topic ngoài ý muốn.
- `auto.offset.reset=earliest` hoặc `latest` chỉ quyết định vị trí bắt đầu đọc khi không có offset phù hợp. Thuộc tính này không tạo topic.
- Không xóa rồi tạo lại topic như một cách thử nhanh. Việc đó có thể làm mất dữ liệu và gây nhầm lẫn về offset của consumer group.

## 4. Kiểm tra topic trên đúng cluster

Dùng chính địa chỉ broker mà ứng dụng đang kết nối để kiểm tra:

```bash
# Kiểm tra một topic có tồn tại và xem partition/replica
kafka-topics.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --describe \
  --topic orders

# Liệt kê các topic broker trả về
kafka-topics.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --list
```

Nếu lệnh `--describe` báo topic không tồn tại, hãy đối chiếu tên topic với cấu hình ứng dụng và kiểm tra bước provision. Nếu lệnh không kết nối được, điều tra DNS, network, TLS/SASL và trạng thái broker trước khi kết luận topic bị thiếu.

Khi topic đã tồn tại nhưng listener vẫn không xử lý message, tiếp tục kiểm tra consumer group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --describe \
  --group order-service
```

Lệnh này giúp kiểm tra partition assignment, committed offset và lag. Topic tồn tại không đồng nghĩa consumer đã được gán partition hoặc đang đọc thành công.

## 5. Đưa trạng thái topic vào health và readiness

Health của broker và sự tồn tại của một topic cụ thể là hai phép kiểm tra khác nhau. Kafka health indicator do Spring Boot cung cấp (nếu được bật trong phiên bản và cấu hình đang dùng) hữu ích để phát hiện vấn đề kết nối tới cluster. Tuy nhiên, broker có thể hoạt động bình thường trong khi topic `orders` vẫn chưa được tạo.

Nếu một hoặc nhiều topic là điều kiện bắt buộc để service hoạt động, hãy bổ sung health indicator kiểm tra metadata của đúng các topic đó. Kafka `AdminClient` cung cấp API `describeTopics` để làm việc này.

Tạo một `AdminClient` dùng cùng cấu hình quản trị Kafka với ứng dụng:

```java
@Configuration
class KafkaHealthConfiguration {

    @Bean(destroyMethod = "close")
    AdminClient topicHealthAdminClient(KafkaAdmin kafkaAdmin) {
        return AdminClient.create(kafkaAdmin.getConfigurationProperties());
    }
}
```

Sau đó tạo health indicator. Ví dụ dưới đây kiểm tra hai topic bắt buộc, giới hạn tổng thời gian chờ khoảng hai giây và phân biệt topic bị thiếu với lỗi khác:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.common.KafkaFuture;
import org.apache.kafka.common.errors.UnknownTopicOrPartitionException;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("kafkaTopics")
final class KafkaTopicsHealthIndicator implements HealthIndicator {

    private static final Set<String> REQUIRED_TOPICS =
            Set.of("orders", "payments");

    private static final long TIMEOUT_NANOS =
            TimeUnit.SECONDS.toNanos(2);

    private final AdminClient admin;

    KafkaTopicsHealthIndicator(AdminClient admin) {
        this.admin = admin;
    }

    @Override
    public Health health() {
        final Map<String, KafkaFuture<TopicDescription>> descriptions;

        try {
            descriptions = admin.describeTopics(REQUIRED_TOPICS).topicNameValues();
        } catch (RuntimeException ex) {
            // Ví dụ: client chưa kết nối được hoặc cấu hình AdminClient không hợp lệ.
            return Health.down(ex).build();
        }

        List<String> available = new ArrayList<>();
        List<String> missing = new ArrayList<>();
        long deadline = System.nanoTime() + TIMEOUT_NANOS;

        for (var entry : descriptions.entrySet()) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) {
                return Health.down()
                        .withDetail("reason", "Timed out while checking required topics")
                        .build();
            }

            try {
                entry.getValue().get(remaining, TimeUnit.NANOSECONDS);
                available.add(entry.getKey());
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();

                if (cause instanceof UnknownTopicOrPartitionException) {
                    missing.add(entry.getKey());
                } else {
                    // Ví dụ: lỗi ACL hoặc lỗi metadata khác không được coi là topic thiếu.
                    return Health.down(cause)
                            .withDetail("topic", entry.getKey())
                            .build();
                }
            } catch (TimeoutException ex) {
                return Health.down(ex)
                        .withDetail("topic", entry.getKey())
                        .build();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return Health.down(ex).build();
            }
        }

        if (!missing.isEmpty()) {
            return Health.down()
                    .withDetail("missingTopics", missing)
                    .withDetail("availableTopics", available)
                    .build();
        }

        return Health.up()
                .withDetail("topics", available)
                .build();
    }
}
```

Đây là ví dụ nền tảng; trong ứng dụng thực tế, danh sách topic nên đến từ cấu hình theo môi trường thay vì hard-code. Nếu client Kafka của phiên bản đang dùng trả về loại exception khác cho topic không tồn tại, hãy xử lý theo exception thực tế đó. Không chuyển `TopicAuthorizationException`, timeout hoặc lỗi broker thành kết quả “topic không tồn tại”.

`AdminClient` là client quản trị có kết nối mạng. Nên tạo một bean dùng lại và đóng khi application context dừng, như ví dụ trên; không tạo client mới ở mỗi lần gọi health endpoint. Giữ danh sách topic kiểm tra ngắn và timeout hữu hạn để probe không bị treo khi cluster gặp sự cố.

### Gắn health indicator vào readiness của Spring Boot

Với Spring Boot Actuator, bật health probes và thêm indicator `kafkaTopics` vào nhóm readiness:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,kafkaTopics
      show-details: when_authorized
```

Kubernetes có thể gọi:

- `/actuator/health/readiness`: chỉ nhận trạng thái sẵn sàng khi `readinessState` và các kiểm tra bắt buộc trong nhóm đều đạt.
- `/actuator/health/liveness`: kiểm tra tiến trình có còn sống hay không.

Không thêm Kafka vào nhóm liveness chỉ vì broker hoặc topic đang lỗi. Nếu liveness phụ thuộc vào Kafka, sự cố bên ngoài có thể khiến Kubernetes liên tục restart một ứng dụng vốn vẫn chạy bình thường. Readiness được thiết kế để ngừng đưa instance vào nhận traffic hoặc công việc mới trong lúc dependency chưa sẵn sàng.

Nếu topic chỉ phục vụ một tính năng tùy chọn, đừng đưa nó vào readiness chung của toàn service. Hãy kiểm tra những topic thực sự cần cho chức năng cốt lõi, hoặc thể hiện trạng thái suy giảm riêng cho tính năng đó.

## 6. Hiểu đúng ý nghĩa của kết quả readiness

Khi `kafkaTopics` trả về `UP`, điều đó chỉ xác nhận rằng ứng dụng đã truy vấn được metadata và các topic được liệt kê đang tồn tại theo quyền mà `AdminClient` có. Nó chưa chứng minh:

- Consumer đã tham gia group và được gán partition.
- Ứng dụng có quyền `READ`, `WRITE` hoặc quyền cần thiết cho từng nghiệp vụ.
- Partition có leader ổn định, replica đã đồng bộ hoặc cấu hình durability đạt yêu cầu.
- Producer có thể ghi message và consumer có thể xử lý message đầu cuối.

Nếu service chỉ được coi là sẵn sàng sau khi listener nhận partition, cần bổ sung một kiểm tra riêng dựa trên trạng thái listener/container hoặc sự kiện phân công partition. Không nên suy ra trạng thái consumer chỉ từ `describeTopics`.

Health endpoint cũng có thể được gọi thường xuyên bởi nhiều probe. Với cluster lớn hoặc danh sách topic dài, cân nhắc cache kết quả trong một khoảng ngắn và theo dõi thời gian phản hồi của health check. Không để một probe tạo ra lượng request quản trị lớn lên Kafka.

## 7. Quy trình xử lý khi readiness báo topic không tồn tại

1. Đọc chi tiết health indicator để xác định topic nào đang thiếu.
2. Lấy đúng `bootstrap.servers`, tên topic và principal từ cấu hình của instance bị lỗi.
3. Dùng `kafka-topics.sh --describe` trên chính cluster đó để xác minh metadata.
4. Nếu topic thực sự chưa có, kiểm tra manifest hoặc quy trình provision: tên, partition, replication factor và topic config.
5. Nếu topic có nhưng ứng dụng không nhìn thấy, kiểm tra ACL `DESCRIBE` và các quyền `READ`/`WRITE` cần thiết; kiểm tra thêm TLS/SASL nếu có lỗi xác thực.
6. Sau khi provision hoặc sửa cấu hình, xác nhận readiness chuyển sang `UP`, listener được gán partition và consumer group bắt đầu hoạt động.

Có thể dùng bảng sau để định hướng bước điều tra:

| Kết quả quan sát | Hướng xử lý |
|---|---|
| `UnknownTopicOrPartitionException` | Kiểm tra topic name, cluster và bước tạo topic |
| `TopicAuthorizationException` | Kiểm tra principal và ACL cho topic |
| Timeout hoặc disconnect | Kiểm tra broker, network, DNS, TLS/SASL và timeout |
| `LeaderNotAvailableException` | Kiểm tra trạng thái partition, leader election và broker |
| Topic tồn tại nhưng consumer không nhận message | Kiểm tra group, assignment, offset, quyền đọc và logic listener |

Một quy trình triển khai ổn định thường provision topic trước, sau đó khởi động service và dùng readiness để xác nhận các dependency bắt buộc đã sẵn sàng. Nếu service được phép khởi động trước topic, đặt `missingTopicsFatal` theo chính sách đó và để readiness tiếp tục báo chưa sẵn sàng cho tới khi topic xuất hiện.

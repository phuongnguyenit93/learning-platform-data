# Khai báo NewTopic bằng bean

Kafka tổ chức dữ liệu theo topic. Trước khi producer gửi record hoặc consumer đọc record, topic đích phải tồn tại trong cluster, trừ khi cluster cho phép tự tạo topic theo cấu hình broker. Trong ứng dụng Spring Kafka, ta có thể khai báo topic mong muốn dưới dạng bean `NewTopic`. Spring Kafka dùng bean này cùng `KafkaAdmin` để yêu cầu Kafka broker tạo topic khi application context khởi động.

Cách khai báo bằng bean giúp đưa cấu trúc topic vào cấu hình có thể quản lý cùng source code: tên topic, số partition, replication factor và một số topic-level configuration. Nó đặc biệt hữu ích khi ứng dụng sở hữu các topic mà chính ứng dụng publish hoặc consume.

Bài học thuộc chương **Quản lý topic** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời chuẩn bị nền tảng cho serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử.

## 1. Vai trò của NewTopic bean

Một topic là luồng dữ liệu logic trong Kafka. Topic được chia thành một hoặc nhiều partition; mỗi partition là một log có thứ tự riêng. Khi thiết kế topic, ứng dụng cần quyết định ít nhất:

- Tên topic theo quy ước của hệ thống.
- Số partition để đáp ứng khả năng xử lý song song và tải dự kiến.
- Replication factor để xác định số bản sao của mỗi partition.
- Chính sách lưu trữ như retention theo thời gian/dung lượng hoặc log compaction.
- Các cấu hình topic-level cần thiết cho độ bền và vòng đời dữ liệu.

Spring Kafka cung cấp lớp `NewTopic` để biểu diễn yêu cầu tạo topic. Khi Spring Kafka phát hiện các bean NewTopic và có `KafkaAdmin` hoạt động, KafkaAdmin gửi yêu cầu tạo những topic chưa tồn tại tới Kafka cluster.

Luồng khởi tạo tổng quát:

~~~mermaid
flowchart TD
    A[Spring ApplicationContext khởi động] --> B[Phát hiện bean NewTopic]
    B --> C[KafkaAdmin]
    C --> D[AdminClient kết nối Kafka]
    D --> E{Topic đã tồn tại?}
    E -->|Chưa| F[Gửi CreateTopics]
    E -->|Rồi| G[Giữ topic hiện có]
    F --> H[Broker tạo topic]
    H --> I[Producer và consumer sử dụng topic]
    G --> I
~~~

NewTopic bean là một khai báo mong muốn về topic. Nó không phải topic đang hoạt động và cũng không phải Kafka producer/consumer. Broker mới là thành phần lưu metadata và tạo partition/replica.

## 2. KafkaAdmin kết nối việc khai báo bean với broker

`KafkaAdmin` là thành phần Spring Kafka sử dụng Kafka Admin API để quản lý topic. Nó đọc cấu hình kết nối Kafka, tìm các bean NewTopic và yêu cầu broker tạo topic khi ứng dụng khởi động.

Trong Spring Boot, khi Spring Kafka được cấu hình qua `spring.kafka.bootstrap-servers`, auto-configuration thường tạo KafkaAdmin để dùng chung thông tin kết nối. Khi đó, ứng dụng chỉ cần khai báo NewTopic bean:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
~~~

Nếu không dùng Spring Boot auto-configuration hoặc muốn cấu hình riêng, có thể khai báo KafkaAdmin thủ công:

~~~java
@Configuration
public class KafkaAdminConfiguration {

    @Bean
    public KafkaAdmin kafkaAdmin() {
        Map<String, Object> configs = new HashMap<>();
        configs.put(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );

        return new KafkaAdmin(configs);
    }
}
~~~

Trong ví dụ, KafkaAdmin sử dụng bootstrap server để khởi tạo AdminClient. AdminClient là client quản trị Kafka, có thể tạo topic và thực hiện các thao tác metadata/configuration theo quyền ACL được cấp.

Không cần tạo một AdminClient riêng cho từng NewTopic bean. KafkaAdmin quản lý quá trình khởi tạo topic từ các khai báo mà Spring phát hiện.

### 2.1. Phân biệt KafkaAdmin, AdminClient và NewTopic

| Thành phần | Vai trò |
| --- | --- |
| `NewTopic` | Mô tả tên topic, partition, replication factor và topic configuration mong muốn. |
| `KafkaAdmin` | Tích hợp Spring lifecycle với Kafka Admin API và xử lý các NewTopic bean. |
| `AdminClient` | Kafka client thực hiện request quản trị tới broker. |
| Kafka broker | Xác thực request, tạo topic và lưu metadata cluster. |

Khi cần thao tác quản trị động ở thời điểm runtime, ứng dụng có thể sử dụng AdminClient API trực tiếp hoặc một lớp dịch vụ quản trị bao quanh nó. NewTopic bean phù hợp với các topic có cấu trúc được biết trước khi application context khởi động.

## 3. Khai báo NewTopic bean đơn giản

Ví dụ tạo topic `order-events` có sáu partition và replication factor bằng một:

~~~java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic orderEventsTopic() {
        return new NewTopic("order-events", 6, (short) 1);
    }
}
~~~

Constructor nhận ba tham số:

- Tên topic: `order-events`.
- Số partition: `6`.
- Replication factor: `1`.

Replication factor trong constructor có kiểu `short`, vì vậy ví dụ dùng ép kiểu `(short) 1`. Giá trị một phù hợp với môi trường local chỉ có một broker; nó không cung cấp bản sao dự phòng khi broker đó gặp sự cố.

Trong môi trường nhiều broker, replication factor thường được chọn lớn hơn một, tùy yêu cầu sẵn sàng và số broker. Không thể tạo replication factor lớn hơn số broker có thể tham gia lưu replica của topic.

### 3.1. Khai báo bằng TopicBuilder

Spring Kafka cung cấp `TopicBuilder` để biểu diễn topic theo kiểu fluent API, dễ đọc hơn khi có nhiều thuộc tính:

~~~java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic orderEventsTopic() {
        return TopicBuilder.name("order-events")
            .partitions(6)
            .replicas(3)
            .build();
    }
}
~~~

Ví dụ này tạo topic với sáu partition và replication factor ba. TopicBuilder giúp mô tả từng thuộc tính trên một dòng và dễ bổ sung cấu hình topic-level.

Hai cách dùng constructor NewTopic và TopicBuilder đều tạo ra NewTopic bean. Chọn cách nào tùy độ phức tạp của topic; với topic có nhiều cấu hình, TopicBuilder thường dễ đọc và dễ bảo trì hơn.

## 4. Cấu hình topic-level bằng TopicBuilder

Ngoài partition và replication factor, topic có thể có các cấu hình như retention, cleanup policy và segment size. TopicBuilder hỗ trợ thêm cấu hình bằng phương thức `config(name, value)`.

Ví dụ topic lưu event trong bảy ngày:

~~~java
@Bean
public NewTopic orderEventsTopic() {
    return TopicBuilder.name("order-events")
        .partitions(6)
        .replicas(3)
        .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
        .build();
}
~~~

`604800000` mili giây tương đương bảy ngày. Đây là ví dụ chính sách lưu trữ; thời gian retention thực tế cần dựa trên yêu cầu replay, dung lượng, chi phí lưu trữ và quy định dữ liệu của hệ thống.

Một số topic-level configuration thường gặp:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `retention.ms` | Thời gian giữ record theo tuổi dữ liệu trong cơ chế retention theo thời gian. |
| `retention.bytes` | Giới hạn dung lượng log giữ lại theo partition trong chính sách áp dụng. |
| `cleanup.policy` | Chính sách dọn dữ liệu: `delete`, `compact` hoặc kết hợp tùy cấu hình hỗ trợ. |
| `segment.bytes` | Kích thước segment log mục tiêu trước khi roll segment. |
| `min.insync.replicas` | Số replica tối thiểu trong ISR cần có để chấp nhận ghi khi producer dùng `acks=all`. |
| `max.message.bytes` | Giới hạn kích thước record batch mà topic chấp nhận theo cấu hình broker/topic. |

Tên cấu hình là chuỗi Kafka broker hiểu. Nên dùng các hằng số từ `org.apache.kafka.common.config.TopicConfig` khi có hằng số tương ứng để tránh lỗi chính tả.

Không nên đặt các giá trị retention hoặc kích thước chỉ theo thói quen. Một topic event cần replay trong 30 ngày có thể cần retention khác một topic lưu trạng thái mới nhất theo key. Cấu hình phải phản ánh mục đích sử dụng dữ liệu.

## 5. Chọn partition phù hợp

Partition là đơn vị lưu trữ và xử lý song song của topic. Consumer group phân phối partition cho các consumer; trong cùng một group, mỗi partition tại một thời điểm được gán cho tối đa một consumer đang hoạt động.

Số partition ảnh hưởng trực tiếp đến khả năng mở rộng consumer. Nếu topic có sáu partition, một consumer group có thể khai thác tối đa sáu luồng đọc song song ở cấp partition, với điều kiện workload và hạ tầng đủ năng lực. Tạo nhiều consumer hơn partition không làm một partition được nhiều consumer trong cùng group đọc đồng thời.

### 5.1. Những yếu tố cần xem xét

Khi chọn số partition, cần cân nhắc:

- Throughput producer dự kiến và kích thước record.
- Throughput xử lý của mỗi consumer.
- Số consumer tối đa muốn chạy đồng thời trong một group.
- Số lượng group độc lập cùng đọc topic.
- Yêu cầu thứ tự theo key và mức độ phân bố key.
- Tài nguyên broker dành cho partition, file handle, metadata và replication.
- Khả năng tăng partition trong tương lai.

Không có công thức duy nhất đúng cho mọi hệ thống. Có thể ước lượng từ throughput mục tiêu và khả năng xử lý đo được của một consumer, sau đó kiểm chứng bằng benchmark trong môi trường gần production.

### 5.2. Key và thứ tự trong partition

Nếu producer gửi key là `orderId`, các event cùng đơn hàng thường được định tuyến vào cùng partition bởi partitioner mặc định. Consumer có thể đọc theo thứ tự offset của partition đó.

Tuy nhiên, Kafka chỉ bảo đảm thứ tự trong từng partition, không có thứ tự toàn cục giữa tất cả partition. Nếu tăng số partition, ánh xạ key sang partition có thể thay đổi; cần đánh giá tác động với event cùng key và cách hệ thống xử lý dữ liệu cũ/mới.

Ví dụ topic có ba partition:

~~~text
order-events
  Partition 0: Order-A events, Order-D events, ...
  Partition 1: Order-B events, Order-E events, ...
  Partition 2: Order-C events, Order-F events, ...
~~~

Đây là sơ đồ minh họa, không phải cách Kafka cố định key theo chữ cái. Partition thực tế được chọn bởi partitioner và số partition hiện tại.

## 6. Replication factor và độ bền dữ liệu

Replication factor xác định số bản sao của mỗi partition trên các broker khác nhau. Ví dụ replication factor ba nghĩa là mỗi partition có một leader và hai replica follower theo trạng thái phân bổ của cluster.

~~~text
Partition 0, replication factor = 3

Broker 1: Leader
Broker 2: Follower
Broker 3: Follower
~~~

Leader xử lý request đọc/ghi theo giao thức Kafka; follower sao chép dữ liệu từ leader. Nếu leader gặp sự cố, Kafka có thể bầu một replica đủ điều kiện làm leader mới theo trạng thái ISR và cấu hình cluster.

Một vài điểm cần nhớ:

- Replication factor một không có bản sao dự phòng.
- Replication factor ba cần đủ broker có thể đặt replica và thường được dùng khi cần khả năng chịu lỗi tốt hơn.
- Replication factor cao hơn tăng chi phí lưu trữ và replication traffic.
- Replication factor không thay thế cấu hình producer acknowledgement.
- `acks=all` kết hợp `min.insync.replicas` giúp đặt điều kiện xác nhận ghi theo số replica đang đồng bộ.

Ví dụ cấu hình topic:

~~~java
@Bean
public NewTopic paymentEventsTopic() {
    return TopicBuilder.name("payment-events")
        .partitions(6)
        .replicas(3)
        .config(TopicConfig.MIN_IN_SYNC_REPLICAS_CONFIG, "2")
        .build();
}
~~~

Ví dụ trên yêu cầu topic có replication factor ba và min.insync.replicas bằng hai. Producer dùng acks=all có thể nhận lỗi khi số replica trong ISR thấp hơn ngưỡng này, thay vì chấp nhận ghi với mức bảo vệ thấp hơn.

Không nên dùng replication factor ba trong cluster chỉ có một broker. Kafka sẽ không thể tạo topic với replication factor vượt số broker đủ điều kiện; cần chọn giá trị phù hợp với topology thực tế.

## 7. Log retention và cleanup policy

Topic có thể phục vụ các mục đích dữ liệu khác nhau. Một topic event thường cần giữ lịch sử trong một khoảng thời gian để consumer có thể replay. Một topic compacted thường biểu diễn trạng thái mới nhất theo key.

### 7.1. Delete policy

Với cleanup policy `delete`, Kafka xóa các segment cũ khi chúng vượt ngưỡng retention theo thời gian hoặc dung lượng. Record không bị xóa ngay khi consumer đọc xong; retention được quản lý độc lập với committed offset của từng consumer group.

Ví dụ cấu hình retention bảy ngày:

~~~java
@Bean
public NewTopic auditEventsTopic() {
    return TopicBuilder.name("audit-events")
        .partitions(6)
        .replicas(3)
        .config(TopicConfig.CLEANUP_POLICY_CONFIG, "delete")
        .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
        .build();
}
~~~

Nếu consumer ngừng hoạt động lâu hơn retention, một số record cũ có thể bị xóa trước khi consumer quay lại. Vì vậy, retention cần lớn hơn khoảng gián đoạn và replay mà hệ thống muốn hỗ trợ.

### 7.2. Compact policy

Với cleanup policy `compact`, Kafka giữ lại giá trị mới nhất theo key trong log compacted sau khi quá trình compaction chạy. Cách này hữu ích cho topic biểu diễn trạng thái hiện tại như cấu hình, hồ sơ hoặc trạng thái tài khoản theo định danh.

~~~java
@Bean
public NewTopic accountStateTopic() {
    return TopicBuilder.name("account-state")
        .partitions(6)
        .replicas(3)
        .compact()
        .build();
}
~~~

Log compaction không có nghĩa record cũ biến mất ngay sau khi ghi record mới. Compaction chạy nền theo cơ chế Kafka; trong một khoảng thời gian, nhiều phiên bản của cùng key vẫn có thể tồn tại. Record có key null không được xử lý giống một key thông thường trong compaction.

Có thể dùng cleanup policy kết hợp `compact,delete` nếu cần cả compaction và giới hạn retention. Cần đọc rõ semantics của từng chính sách trước khi áp dụng cho dữ liệu nghiệp vụ.

## 8. Khai báo nhiều topic bằng nhiều bean

Một ứng dụng có thể sở hữu nhiều topic. Mỗi topic được khai báo bằng một bean NewTopic riêng:

~~~java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic orderEventsTopic() {
        return TopicBuilder.name("order-events")
            .partitions(6)
            .replicas(3)
            .build();
    }

    @Bean
    public NewTopic paymentEventsTopic() {
        return TopicBuilder.name("payment-events")
            .partitions(3)
            .replicas(3)
            .build();
    }

    @Bean
    public NewTopic accountStateTopic() {
        return TopicBuilder.name("account-state")
            .partitions(6)
            .replicas(3)
            .compact()
            .build();
    }
}
~~~

KafkaAdmin phát hiện các NewTopic bean và gửi yêu cầu tạo các topic chưa tồn tại. Tách mỗi topic thành một phương thức bean giúp cấu hình dễ đọc, dễ review và dễ liên kết với chủ sở hữu nghiệp vụ.

Tên bean không bắt buộc trùng tên topic, nhưng nên mô tả rõ mục đích như `orderEventsTopic` hoặc `paymentEventsTopic`. Tên topic là giá trị được truyền vào TopicBuilder; đó là tên broker sẽ quản lý.

Nếu một ứng dụng có nhiều cluster Kafka, cần bảo đảm các NewTopic bean được xử lý bởi KafkaAdmin kết nối đúng cluster. Không nên giả định một bean NewTopic tự biết nó thuộc cluster nào. Với nhiều KafkaAdmin, cần cấu hình việc quản lý topic rõ ràng theo từng cluster và xác minh behavior theo phiên bản Spring Kafka đang sử dụng.

## 9. Cấu hình NewTopic bằng application properties hay bean?

Một số thiết lập có thể được khai báo trong cấu hình ứng dụng, nhưng NewTopic bean cung cấp cách mô tả rõ từng topic bằng Java configuration.

| Tiêu chí | NewTopic bean | Tạo topic ngoài ứng dụng |
| --- | --- | --- |
| Nơi mô tả | Source code Spring configuration | Script, IaC hoặc quy trình vận hành |
| Thời điểm | Khi Spring context khởi động và KafkaAdmin khởi tạo | Theo pipeline/deployment hoặc thao tác quản trị |
| Phù hợp | Topic nhỏ gọn do ứng dụng sở hữu | Topic production có governance và lifecycle riêng |
| Review thay đổi | Có thể review cùng thay đổi code | Review trong repository IaC hoặc quy trình hạ tầng |
| Quyền quản trị | Ứng dụng cần ACL tạo topic | Pipeline/admin identity thực hiện tạo topic |

Không có lựa chọn duy nhất cho mọi tổ chức. Với môi trường local hoặc ứng dụng nhỏ, NewTopic bean giúp developer chạy ứng dụng mà không phải tạo topic thủ công. Trong production có quy trình quản trị hạ tầng chặt chẽ, tổ chức có thể tạo topic bằng Terraform, Ansible, Helm hoặc pipeline riêng và giới hạn quyền tạo topic của runtime application.

Nếu topic được tạo bên ngoài ứng dụng, listener/producer chỉ cần cấu hình đúng tên topic và quyền truy cập. NewTopic bean không bắt buộc phải xuất hiện trong mọi ứng dụng Spring Kafka.

## 10. Điều gì xảy ra khi topic đã tồn tại?

NewTopic bean thường được dùng để tạo topic còn thiếu. Nếu topic cùng tên đã tồn tại, request CreateTopics có thể trả về lỗi TopicExists cho topic đó; KafkaAdmin xử lý tình huống này như topic đã được tạo và không tự động biến bean thành một bản cập nhật cấu hình tổng quát cho topic hiện hữu.

Điều này có ý nghĩa quan trọng khi sửa code:

- Đổi số partition trong NewTopic bean không phải cách đáng tin cậy để giảm hoặc điều chỉnh partition của topic đã tồn tại.
- Đổi replication factor trong bean không tự động tái phân bổ replica của topic cũ.
- Đổi retention hoặc cleanup policy trong bean không nên được xem là cơ chế cập nhật topic configuration đã tồn tại.
- Cần dùng công cụ Admin API hoặc quy trình vận hành phù hợp để thay đổi cấu hình topic hiện hữu.

Kafka hỗ trợ tăng số partition bằng thao tác quản trị tạo thêm partition, nhưng không hỗ trợ giảm số partition của một topic theo cách tương tự. Tăng partition có thể thay đổi ánh xạ key sang partition, vì vậy cần đánh giá thứ tự event theo key trước khi thay đổi.

Đối với cấu hình topic, cần dùng thao tác alter configuration phù hợp và kiểm tra trạng thái sau thay đổi. Không nên chỉ sửa giá trị trong bean rồi cho rằng broker đã áp dụng.

## 11. KafkaAdmin và thời điểm tạo topic khi ứng dụng khởi động

Trong Spring context, KafkaAdmin khởi tạo các topic được khai báo thông qua NewTopic bean. Quá trình này phụ thuộc kết nối broker và quyền ACL của principal mà ứng dụng sử dụng.

Nếu broker chưa sẵn sàng khi ứng dụng khởi động, hành vi startup phụ thuộc cấu hình KafkaAdmin và phiên bản Spring Kafka. Với hệ thống yêu cầu topic phải tồn tại trước khi service nhận traffic, cần thiết kế readiness/startup policy để tránh ứng dụng được coi là sẵn sàng khi thao tác tạo topic thất bại.

Các điểm cần kiểm tra:

- KafkaAdmin có được tạo và bật trong application context không.
- Bootstrap server có trỏ đúng cluster không.
- Credential có quyền Create trên topic hoặc cluster theo ACL không.
- Replication factor có phù hợp số broker không.
- Topic name có hợp lệ và đúng quy ước không.
- Broker có nhận được yêu cầu tạo topic không.
- Topic sau khởi tạo có đúng partition, replica và config mong đợi không.

Không nên dùng cơ chế tự tạo topic của broker như một thay thế cho quản lý topic có chủ đích. Nếu broker tự tạo topic khi producer gửi đến tên chưa tồn tại, topic có thể được tạo với partition/replication mặc định ngoài mong muốn của ứng dụng.

## 12. Kết hợp NewTopic với KafkaTemplate và @KafkaListener

Khi topic được tạo, producer và consumer có thể sử dụng tên topic đó. Ví dụ:

~~~java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic orderEventsTopic() {
        return TopicBuilder.name("order-events")
            .partitions(6)
            .replicas(3)
            .build();
    }
}
~~~

Producer:

~~~java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
            "order-events",
            event.orderId(),
            event
        );
    }
}
~~~

Consumer:

~~~java
@Component
public class OrderEventListener {

    @KafkaListener(
        topics = "order-events",
        groupId = "billing-service"
    )
    public void onOrderCreated(OrderCreated event) {
        billingService.startBilling(event);
    }
}
~~~

NewTopic bean chỉ chịu trách nhiệm mô tả topic cần tạo. KafkaTemplate chịu trách nhiệm gửi record; @KafkaListener được listener container quản lý để nhận record. Ba thành phần này có quan hệ trong cùng luồng messaging nhưng có trách nhiệm riêng.

Nếu topic được tạo trước bằng quy trình hạ tầng, có thể bỏ NewTopic bean mà vẫn dùng KafkaTemplate và @KafkaListener bình thường.

## 13. Kiểm tra topic sau khi ứng dụng khởi động

Không nên chỉ nhìn thấy application context khởi động thành công rồi kết luận topic đã được tạo đúng. Cần kiểm tra topic metadata từ Kafka cluster.

Có thể dùng Kafka CLI:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --list
~~~

Xem chi tiết topic:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic order-events
~~~

Kết quả mô tả topic thường cho biết partition, leader, replica và ISR. Đây là cách xác nhận cluster đã nhận cấu hình topic.

Có thể dùng AdminClient trong test hoặc công cụ quản trị để đọc metadata và cấu hình topic. Ví dụ kiểm tra metadata bằng AdminClient:

~~~java
try (AdminClient admin = AdminClient.create(Map.of(
        AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092"
))) {
    TopicDescription description = admin.describeTopics(
        List.of("order-events")
    ).allTopicNames().get(10, TimeUnit.SECONDS).get("order-events");

    assertThat(description.partitions()).hasSize(6);
}
~~~

Đoạn code minh họa cách đọc metadata; test thực tế cần broker đang chạy và xử lý trường hợp timeout hoặc topic chưa tồn tại. Kiểm tra số partition có thể thực hiện qua TopicDescription; kiểm tra topic configuration cần dùng API describeConfigs phù hợp.

## 14. Kiểm thử NewTopic bean

Một bài kiểm thử tích hợp nên xác nhận:

1. Application context tạo được KafkaAdmin và NewTopic bean.
2. Kafka cluster nhận yêu cầu tạo topic.
3. Topic xuất hiện trong metadata.
4. Số partition và replication factor đúng với cấu hình.
5. Topic-level configuration quan trọng được áp dụng.
6. Producer có thể gửi record vào topic và consumer có thể đọc record nếu test bao gồm luồng end-to-end.

Có thể dùng Embedded Kafka hoặc Testcontainers để kiểm thử với broker thật. Cần chọn replication factor phù hợp số broker test: broker đơn chỉ tạo được topic với replication factor một. Nếu test cấu hình replicas ba trên broker đơn, thao tác tạo topic sẽ thất bại do thiếu broker đủ điều kiện.

Ví dụ test kiểm tra topic bằng AdminClient có thể chạy sau khi application context khởi tạo và KafkaAdmin đã thực hiện tạo topic. Tránh dùng sleep cố định nếu có thể chờ bằng API metadata với timeout rõ ràng.

## 15. Lỗi thường gặp khi khai báo NewTopic

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Topic không xuất hiện sau khi khởi động | KafkaAdmin không được tạo, broker không truy cập được hoặc bean NewTopic không được phát hiện | Kiểm tra application context, bootstrap servers và log KafkaAdmin |
| Topic creation bị từ chối | ACL thiếu quyền Create hoặc tên topic không hợp lệ | Kiểm tra principal, ACL và topic name |
| Replication factor không khả dụng | Số replica yêu cầu lớn hơn số broker đủ điều kiện | Kiểm tra số broker và đặt replicas phù hợp |
| Topic có ít partition hơn mong đợi | Topic đã tồn tại từ trước với cấu hình khác | Describe topic; tạo thêm partition bằng Admin API nếu cần |
| Retention không thay đổi | Topic đã tồn tại và NewTopic bean không phải cơ chế alter config | Dùng describeConfigs và alterConfigs/alterConfigs API phù hợp |
| Ứng dụng chạy được nhưng producer gửi lỗi UnknownTopicOrPartition | Topic chưa được tạo hoặc producer đang kết nối cluster khác | Kiểm tra cluster, topic metadata và thời điểm khởi tạo |
| Local chạy được nhưng production không tạo topic | ACL hoặc policy production chặn runtime tạo topic | Kiểm tra quyền service account và quy trình provisioning |
| Tăng partition làm thứ tự theo key thay đổi | Ánh xạ key sang partition thay đổi khi topology thay đổi | Đánh giá partitioning strategy và cách xử lý dữ liệu chuyển tiếp |

## 16. Checklist thiết kế NewTopic bean

Trước khi khai báo topic cho một service, hãy trả lời:

1. Topic thuộc domain/nghiệp vụ nào và service nào chịu trách nhiệm?
2. Tên topic có tuân theo naming convention và phân biệt môi trường/phiên bản nếu cần không?
3. Số partition dựa trên throughput, consumer concurrency và khả năng broker ra sao?
4. Replication factor có phù hợp số broker và yêu cầu sẵn sàng không?
5. Producer có dùng acks=all và min.insync.replicas phù hợp khi cần độ bền cao không?
6. Dữ liệu cần giữ bao lâu; nên dùng delete hay compact?
7. Có cần giới hạn message size, segment hoặc cấu hình topic-level nào khác không?
8. Topic đã được tạo bởi pipeline hạ tầng hay ứng dụng sẽ tạo bằng KafkaAdmin?
9. Runtime application có quyền tạo topic trong production không?
10. Có kiểm tra metadata/config sau khi tạo và có quy trình thay đổi topic hiện hữu không?

NewTopic bean giúp đưa cấu trúc topic vào cấu hình Spring một cách rõ ràng và có thể review cùng mã nguồn. Khi kết hợp đúng với KafkaAdmin, nó giúp môi trường phát triển và kiểm thử tạo được topic cần thiết tự động. Trong vận hành, cần hiểu rõ ranh giới giữa khai báo topic mới và thay đổi topic đã tồn tại, đồng thời chọn partition, replication và retention dựa trên yêu cầu thực tế của luồng dữ liệu.


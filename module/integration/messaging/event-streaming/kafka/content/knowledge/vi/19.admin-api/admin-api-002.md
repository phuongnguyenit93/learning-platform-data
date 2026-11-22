# Tạo, mô tả, liệt kê và xóa topic

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này hướng dẫn quản trị topic bằng **Kafka Admin API**: tạo topic, xem metadata và cấu hình, liệt kê topic trong cluster, rồi xóa topic khi không còn cần thiết.

Kafka Admin API cho phép ứng dụng quản trị thực hiện các thao tác mà không cần gọi shell script. Java AdminClient gửi yêu cầu đến broker và trả kết quả bất đồng bộ thông qua KafkaFuture. Vì vậy, ứng dụng cần quản lý timeout, lỗi từng topic, quyền ACL và vòng đời client rõ ràng. Các thao tác xóa topic có thể làm mất dữ liệu, nên cần kiểm tra tên, môi trường và quyền trước khi thực hiện.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của Kafka Admin API và AdminClient.
- Khởi tạo, cấu hình và đóng AdminClient đúng cách.
- Tạo một hoặc nhiều topic bằng NewTopic và createTopics().
- Chọn số partition, replication factor và topic configuration khi tạo topic.
- Liệt kê topic bằng listTopics() và lọc internal topic.
- Mô tả topic, partition, leader, replica và ISR bằng describeTopics().
- Đọc cấu hình topic bằng describeConfigs().
- Xóa một hoặc nhiều topic bằng deleteTopics().
- Xử lý kết quả bất đồng bộ, timeout và các lỗi quản trị thường gặp.
- Phân biệt thao tác quản trị topic với việc tạo topic tự động từ producer.
- Tích hợp quản trị topic vào ứng dụng Java hoặc Spring Kafka.

## 2. Kafka Admin API và AdminClient

Kafka cung cấp Admin API để thực hiện các thao tác quản trị cluster như:

- Tạo, liệt kê, mô tả và xóa topic.
- Tạo thêm partition cho topic.
- Xem và thay đổi cấu hình broker hoặc topic.
- Mô tả broker, cluster, consumer group và ACL.
- Quản lý một số thao tác quản trị khác tùy phiên bản Kafka.

Trong Java, API quản trị được cung cấp qua interface Admin và lớp triển khai AdminClient. AdminClient là client quản trị dùng để gửi request đến Kafka cluster.

~~~mermaid
flowchart LR
    A[Java application] --> B[AdminClient]
    B --> C[Kafka broker]
    C --> D[Controller]
    D --> E[Cluster metadata]
    C --> F[Topic partitions]
    B --> G[KafkaFuture results]
    G --> A
~~~

AdminClient không lưu dữ liệu topic và không thay thế broker controller. Nó gửi yêu cầu quản trị; controller và broker xử lý yêu cầu, cập nhật metadata rồi trả kết quả.

### 2.1. Khi nào dùng AdminClient?

Dùng AdminClient khi ứng dụng cần:

- Tạo topic lúc triển khai tenant hoặc workload mới.
- Kiểm tra topic đã tồn tại và xác minh số partition.
- Hiển thị metadata topic trong trang quản trị.
- Kiểm tra leader, replica và ISR để hỗ trợ vận hành.
- Kiểm tra topic config như retention hoặc cleanup policy.
- Xóa topic test hoặc topic đã được đánh dấu ngừng sử dụng.
- Xây dựng công cụ provisioning cho môi trường dev, test hoặc production.

Với hạ tầng production, topic thường được provision qua pipeline hoặc công cụ quản trị có kiểm soát. Ứng dụng nghiệp vụ không nên tự ý tạo và xóa topic theo từng request người dùng nếu chưa có chính sách rõ ràng.

### 2.2. AdminClient là client bất đồng bộ

Các phương thức quản trị thường trả về một result object chứa KafkaFuture. Ví dụ:

~~~java
CreateTopicsResult result = admin.createTopics(topics);
result.all().get();
~~~

createTopics() gửi request và trả về ngay một result object. all().get() chờ tất cả thao tác trong request hoàn tất hoặc ném exception.

Không nên giả định gọi createTopics() đồng nghĩa topic đã được tạo xong. Nếu cần dùng topic ngay sau đó, hãy chờ kết quả hoặc xử lý future tương ứng.

## 3. Khởi tạo AdminClient

AdminClient dùng cấu hình tương tự các Kafka client khác. Tối thiểu cần bootstrap.servers.

~~~java
import org.apache.kafka.clients.admin.AdminClient;
import java.util.Properties;

Properties properties = new Properties();
properties.put("bootstrap.servers", "localhost:9092");

try (AdminClient admin = AdminClient.create(properties)) {
    // Thực hiện các thao tác quản trị tại đây.
}
~~~

Cấu hình thực tế thường bao gồm:

| Thuộc tính | Vai trò |
|---|---|
| bootstrap.servers | Danh sách broker để client bootstrap và khám phá cluster. |
| client.id | Định danh client trong log và metric. |
| request.timeout.ms | Thời gian chờ một request phản hồi. |
| default.api.timeout.ms | Timeout mặc định cho các thao tác Admin API có timeout. |
| security.protocol | Giao thức bảo mật, ví dụ PLAINTEXT, SSL, SASL_SSL. |
| sasl.mechanism | Cơ chế SASL nếu cluster dùng SASL. |
| ssl.truststore.location | Truststore khi cấu hình TLS theo cách dùng truststore. |

Ví dụ cấu hình:

~~~java
Properties properties = new Properties();
properties.put("bootstrap.servers", "kafka-1:9092,kafka-2:9092");
properties.put("client.id", "topic-admin-service");
properties.put("request.timeout.ms", 15000);
properties.put("default.api.timeout.ms", 30000);
~~~

Nếu cluster dùng SASL hoặc TLS, AdminClient phải được cấu hình bảo mật đúng như các client khác. Không hardcode mật khẩu hoặc private key trong source code; lấy secret từ secret manager hoặc môi trường triển khai phù hợp.

### 3.1. Quản lý vòng đời

AdminClient là tài nguyên có thread và network connection nội bộ. Hãy đóng client khi không còn sử dụng.

- Dùng try-with-resources cho tác vụ ngắn.
- Với service chạy lâu dài, tạo một AdminClient dùng chung theo lifecycle của ứng dụng.
- Không tạo AdminClient mới cho mỗi record hoặc mỗi HTTP request.
- Khi shutdown, gọi close(Duration) hoặc close() để giải phóng tài nguyên.

Một AdminClient có thể phục vụ nhiều thao tác quản trị đồng thời. Tuy nhiên, cần giới hạn số request và timeout để không tạo tải quản trị quá lớn.

## 4. Tạo topic bằng NewTopic và createTopics()

Để tạo topic, dùng lớp NewTopic. Constructor phổ biến nhận:

- Tên topic.
- Số partition.
- Replication factor.

Ví dụ tạo topic orders có 6 partition và replication factor 3:

~~~java
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.NewTopic;

import java.util.List;
import java.util.Properties;

public class CreateOrdersTopic {

    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();
        properties.put("bootstrap.servers", "localhost:9092");

        try (AdminClient admin = AdminClient.create(properties)) {
            NewTopic orders = new NewTopic(
                "orders",
                6,
                (short) 3
            );

            admin.createTopics(List.of(orders)).all().get();

            System.out.println("Topic orders created");
        }
    }
}
~~~

createTopics() nhận collection NewTopic, nên có thể tạo nhiều topic trong một lần gọi.

~~~java
List<NewTopic> topics = List.of(
    new NewTopic("orders", 6, (short) 3),
    new NewTopic("payments", 3, (short) 3),
    new NewTopic("shipments", 6, (short) 2)
);

admin.createTopics(topics).all().get();
~~~

Số replica phải phù hợp với số broker khả dụng và chính sách failure domain. Ví dụ replication factor 3 thường cần ít nhất ba broker đủ điều kiện lưu replica.

### 4.1. Cấu hình topic ngay khi tạo

NewTopic.configs() cho phép đặt topic-level configuration ngay khi tạo.

~~~java
import java.util.Map;

NewTopic orders = new NewTopic(
    "orders",
    6,
    (short) 3
).configs(Map.of(
    "retention.ms", "604800000",
    "cleanup.policy", "delete",
    "min.insync.replicas", "2"
));
~~~

Ví dụ trên:

- retention.ms=604800000: giữ dữ liệu tối đa khoảng 7 ngày theo chính sách thời gian.
- cleanup.policy=delete: xóa segment cũ theo retention policy.
- min.insync.replicas=2: yêu cầu tối thiểu hai replica trong ISR cho ghi acks=all.

Các cấu hình cần được chọn theo yêu cầu nghiệp vụ và cluster. Broker có thể áp dụng default nếu topic không override. Không nên sao chép nguyên giá trị ví dụ sang production mà chưa đánh giá dung lượng, replication và SLA.

### 4.2. Số partition và replication factor

| Tham số | Ý nghĩa | Cần cân nhắc |
|---|---|---|
| Partitions | Số partition của topic | Mức song song consumer, throughput, ordering và chi phí metadata. |
| Replication factor | Số replica được gán cho mỗi partition | Khả năng chịu lỗi, số broker và dung lượng lưu trữ. |
| min.insync.replicas | Số replica tối thiểu trong ISR cho ghi acks=all | Trade-off giữa durability và availability. |

Partition count không chỉ là tham số hiệu năng. Nó ảnh hưởng đến:

- Số consumer có thể xử lý song song trong một group.
- Ordering: Kafka chỉ bảo đảm thứ tự trong một partition.
- Phân bố tải và replica.
- Số file log, metadata và chi phí vận hành.

Replication factor không phải số consumer và cũng không phải số partition. Mỗi partition có một leader và các replica follower.

### 4.3. Kiểm tra trước khi tạo

Một số điều cần xác nhận:

1. Topic name đúng quy ước và chưa được dùng.
2. Partition count phù hợp với throughput và consumer concurrency.
3. Replication factor không vượt số broker đủ điều kiện.
4. Topic config hợp lệ và được broker hỗ trợ.
5. Người gọi có ACL Create trên topic hoặc quyền quản trị tương ứng.
6. Tên topic không trùng với internal topic hoặc topic dành cho dịch vụ khác.

Kafka không tự động biến thao tác create thành upsert. Nếu topic đã tồn tại, request có thể trả TopicExistsException. Ứng dụng nên mô tả topic hiện tại và so sánh với desired configuration, không xóa rồi tạo lại một cách tùy tiện.

### 4.4. Validate-only

Một số phiên bản Kafka hỗ trợ CreateTopicsOptions.validateOnly(true) để yêu cầu broker xác thực request mà không thực sự tạo topic.

~~~java
import org.apache.kafka.clients.admin.CreateTopicsOptions;

CreateTopicsOptions options = new CreateTopicsOptions()
    .validateOnly(true)
    .timeoutMs(10000);

admin.createTopics(List.of(orders), options).all().get();
~~~

Hãy kiểm tra phiên bản broker và Java client đang dùng. Validate-only hữu ích trong công cụ kiểm tra cấu hình, nhưng không thay thế việc kiểm tra quyền, capacity và chính sách triển khai.

## 5. Liệt kê topic bằng listTopics()

Dùng listTopics() để lấy danh sách topic trong cluster.

~~~java
Set<String> topicNames = admin.listTopics().names().get();

for (String topicName : topicNames) {
    System.out.println(topicName);
}
~~~

Kết quả names() là tập tên topic. Nếu cần metadata như topic internal hay partition count, dùng listings():

~~~java
admin.listTopics().listings().get().forEach(topic -> {
    System.out.printf(
        "name=%s internal=%s%n",
        topic.name(),
        topic.isInternal()
    );
});
~~~

### 5.1. Ẩn internal topic

Kafka có các internal topic như __consumer_offsets và __transaction_state. Để chỉ liệt kê topic người dùng, dùng ListTopicsOptions:

~~~java
import java.util.Set;
import org.apache.kafka.clients.admin.ListTopicsOptions;

ListTopicsOptions options = new ListTopicsOptions()
    .listInternal(false);

Set<String> names = admin.listTopics(options).names().get();
~~~

Nếu đang điều tra cluster, có thể bật listInternal(true) để quan sát cả internal topic. Không xóa internal topic chỉ vì nó xuất hiện trong danh sách.

### 5.2. Liệt kê không đồng nghĩa mô tả chi tiết

listTopics() chủ yếu trả về danh sách. Nếu cần leader, replica, ISR hoặc partition metadata, hãy gọi describeTopics() cho các topic cần xem.

Không nên mô tả toàn bộ hàng nghìn topic trên mỗi request UI nếu không cần. Hãy phân trang hoặc giới hạn phạm vi ở tầng ứng dụng nếu hệ thống quản trị có nhiều topic.

## 6. Mô tả topic bằng describeTopics()

Dùng describeTopics() để lấy metadata topic.

~~~java
import java.util.Map;
import java.util.Set;
import org.apache.kafka.clients.admin.TopicDescription;

Map<String, TopicDescription> descriptions =
    admin.describeTopics(Set.of("orders"))
         .allTopicNames()
         .get();

TopicDescription description = descriptions.get("orders");

System.out.println("topic=" + description.name());
System.out.println("internal=" + description.isInternal());
System.out.println("partitions=" + description.partitions().size());
~~~

TopicDescription chứa tên topic, trạng thái internal và danh sách TopicPartitionInfo.

Mỗi partition cung cấp:

- Partition ID.
- Leader hiện tại.
- Danh sách replica.
- Danh sách ISR.
- Một số metadata khác tùy phiên bản API.

### 6.1. In leader, replicas và ISR

~~~java
import java.util.stream.Collectors;
import org.apache.kafka.common.Node;
import org.apache.kafka.common.TopicPartitionInfo;

for (TopicPartitionInfo partition : description.partitions()) {
    Node leader = partition.leader();

    System.out.printf(
        "partition=%d leader=%s replicas=%s isr=%s%n",
        partition.partition(),
        leader == null ? "none" : leader.id(),
        partition.replicas().stream()
            .map(Node::id)
            .collect(Collectors.toList()),
        partition.isr().stream()
            .map(Node::id)
            .collect(Collectors.toList())
    );
}
~~~

Ví dụ output:

~~~text
topic=orders
partition=0 leader=1 replicas=[1, 2, 3] isr=[1, 2, 3]
partition=1 leader=2 replicas=[2, 3, 1] isr=[2, 3]
partition=2 leader=3 replicas=[3, 1, 2] isr=[1, 3]
~~~

Cách đọc:

- Partition 0 có ba replica và cả ba đều trong ISR.
- Partition 1 có replica broker 1 không nằm trong ISR tại thời điểm quan sát.
- Partition 2 có replica broker 2 không nằm trong ISR.
- Leader là broker đang giữ vai trò leader của partition.

Nếu leader là null hoặc ISR thiếu replica, cần kiểm tra trạng thái broker, replica lag và controller. Metadata chỉ phản ánh thời điểm request được xử lý; trạng thái có thể thay đổi ngay sau khi trả kết quả.

### 6.2. Describe nhiều topic

Có thể truyền nhiều tên topic trong một lần gọi:

~~~java
Map<String, TopicDescription> descriptions =
    admin.describeTopics(
        Set.of("orders", "payments", "shipments")
    ).allTopicNames().get();
~~~

Nếu cần kết quả độc lập cho từng topic, có thể xem future trong result map và xử lý lỗi từng topic thay vì chỉ gọi allTopicNames().get() cho toàn bộ request.

## 7. Đọc cấu hình topic bằng describeConfigs()

Metadata partition không chứa toàn bộ topic config. Dùng describeConfigs() với ConfigResource.Type.TOPIC.

~~~java
import java.util.List;
import org.apache.kafka.clients.admin.Config;
import org.apache.kafka.clients.admin.ConfigEntry;
import org.apache.kafka.common.config.ConfigResource;

ConfigResource resource = new ConfigResource(
    ConfigResource.Type.TOPIC,
    "orders"
);

Config config = admin.describeConfigs(List.of(resource))
    .all()
    .get()
    .get(resource);

for (ConfigEntry entry : config.entries()) {
    System.out.printf(
        "name=%s value=%s default=%s sensitive=%s%n",
        entry.name(),
        entry.value(),
        entry.isDefault(),
        entry.isSensitive()
    );
}
~~~

Một số config có thể là default được kế thừa từ broker. isDefault() giúp phân biệt config đang dùng có phải giá trị mặc định hay đã được override ở topic. Với giá trị nhạy cảm, API có thể không trả nội dung thực.

Các config thường cần quan sát:

| Config | Ý nghĩa |
|---|---|
| retention.ms | Thời gian giữ log trước khi đủ điều kiện xóa theo policy. |
| retention.bytes | Giới hạn dung lượng log theo partition. |
| cleanup.policy | Chính sách delete, compact hoặc kết hợp. |
| min.insync.replicas | Ngưỡng ISR tối thiểu cho ghi acks=all. |
| max.message.bytes | Giới hạn kích thước record batch theo cấu hình topic. |
| segment.bytes | Kích thước segment log mục tiêu. |

Nếu cần thay đổi config, Kafka client hiện đại cung cấp incrementalAlterConfigs(). Hãy xác định config nào có thể thay đổi động, giá trị broker default và tác động của việc thay đổi trước khi cập nhật.

## 8. Xóa topic bằng deleteTopics()

Dùng deleteTopics() để yêu cầu Kafka xóa topic.

~~~java
admin.deleteTopics(List.of("orders-test")).all().get();
~~~

Ví dụ hoàn chỉnh:

~~~java
import org.apache.kafka.clients.admin.AdminClient;

import java.util.List;
import java.util.Properties;

public class DeleteTestTopic {

    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();
        properties.put("bootstrap.servers", "localhost:9092");

        try (AdminClient admin = AdminClient.create(properties)) {
            admin.deleteTopics(List.of("orders-test"))
                .all()
                .get();

            System.out.println("Delete request completed");
        }
    }
}
~~~

Xóa topic là thao tác có thể làm mất toàn bộ dữ liệu và metadata của topic. Trước khi thực hiện, cần:

1. Xác minh cluster và môi trường.
2. Xác minh chính xác topic name.
3. Kiểm tra topic có phải topic production hay được service khác sử dụng không.
4. Xác nhận dữ liệu có cần lưu trữ hoặc backup không.
5. Kiểm tra quyền ACL Delete.
6. Kiểm tra broker có cho phép xóa topic không.

### 8.1. Broker phải cho phép xóa topic

Cấu hình broker delete.topic.enable điều khiển việc xóa topic trong các cấu hình Kafka hỗ trợ thuộc tính này. Nếu việc xóa bị vô hiệu hóa, request có thể không hoàn tất như mong đợi.

Hãy kiểm tra cấu hình cluster theo phiên bản và môi trường. Không nên giả định topic sẽ bị xóa chỉ vì AdminClient đã gửi request.

### 8.2. Xóa bất đồng bộ và trạng thái đang xóa

deleteTopics() trả về result object chứa future. Khi all().get() hoàn tất, thao tác đã hoàn tất theo kết quả broker trả về. Tuy nhiên, quá trình dọn dữ liệu vật lý và metadata trên các broker có thể diễn ra bất đồng bộ.

Trong thời gian chuyển tiếp, topic có thể còn xuất hiện trong một số quan sát metadata hoặc log. Không nên lập tức tạo lại cùng tên topic và giả định mọi trạng thái cũ đã biến mất hoàn toàn.

### 8.3. Xóa nhiều topic

~~~java
admin.deleteTopics(
    List.of("orders-test", "payments-test", "shipments-test")
).all().get();
~~~

Nếu một topic không tồn tại hoặc không đủ quyền, thao tác tổng hợp có thể thất bại. Với công cụ quản trị cần báo cáo chính xác từng topic, hãy xử lý future riêng cho từng tên.

Không dùng thao tác xóa rồi tạo lại để thay đổi số partition hoặc sửa config. Xóa topic sẽ làm mất dữ liệu và thay đổi identity của luồng dữ liệu. Với thay đổi partition, dùng API tạo thêm partition; Kafka không hỗ trợ giảm partition count của topic hiện có.

## 9. Xử lý KafkaFuture và lỗi quản trị

Các Admin API thường trả về KafkaFuture. Có thể chờ bằng get() hoặc gắn callback.

~~~java
import org.apache.kafka.clients.admin.CreateTopicsResult;
import org.apache.kafka.clients.admin.NewTopic;
CreateTopicsResult result =
    admin.createTopics(List.of(new NewTopic("audit", 3, (short) 3)));

result.all().whenComplete((ignored, error) -> {
    if (error != null) {
        System.err.println("Create topic failed: " + error.getMessage());
    } else {
        System.out.println("Topic created");
    }
});
~~~

Không chặn thread xử lý HTTP hoặc event loop bằng get() lâu nếu kiến trúc yêu cầu non-blocking. Có thể chuyển future sang CompletableFuture hoặc xử lý callback ở executor phù hợp.

### 9.1. Các lỗi thường gặp

| Exception / lỗi | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| TopicExistsException | Topic đã tồn tại. | Describe topic hiện tại và so sánh cấu hình mong muốn. |
| UnknownTopicOrPartitionException | Topic hoặc partition không tồn tại tại thời điểm request. | Kiểm tra tên và metadata; tránh giả định thao tác trước đã hoàn tất. |
| InvalidReplicationFactorException | Replication factor không phù hợp số broker khả dụng. | Kiểm tra broker count và rack/zone placement. |
| InvalidPartitionsException | Partition count không hợp lệ. | Dùng số partition dương và kiểm tra giới hạn cluster. |
| TopicAuthorizationException | Principal không có quyền trên topic. | Cấp ACL tối thiểu cần thiết. |
| ClusterAuthorizationException | Principal thiếu quyền quản trị cluster. | Kiểm tra quyền cluster-level phù hợp với API. |
| TimeoutException | Broker hoặc controller không phản hồi trong timeout. | Kiểm tra cluster health, network, controller và timeout. |
| UnsupportedVersionException | Broker không hỗ trợ API/version được client yêu cầu. | Đồng bộ phiên bản client/broker và API options. |
| InvalidConfigurationException | Topic config không hợp lệ hoặc không được hỗ trợ. | Kiểm tra tên config, giá trị và broker policy. |

Exception có thể được bọc trong ExecutionException khi gọi KafkaFuture.get(). Hãy kiểm tra getCause() để phân loại lỗi gốc.

### 9.2. Timeout không đồng nghĩa thao tác chắc chắn thất bại

Nếu client timeout, broker có thể đã xử lý request nhưng response không đến được client. Đây là kết quả không rõ ràng.

Ví dụ:

- Client gửi create topic.
- Controller tạo topic thành công.
- Response bị mất.
- Client nhận timeout.

Nếu ứng dụng retry, có thể nhận TopicExistsException. Đây không nhất thiết là lỗi nghiêm trọng; hãy describe topic và xác minh desired state.

Tương tự, sau timeout khi delete, hãy kiểm tra topic còn tồn tại hay đang trong trạng thái xóa trước khi quyết định hành động tiếp theo.

## 10. Desired state và thao tác quản trị an toàn

Công cụ provisioning nên mô tả trạng thái mong muốn rồi so sánh với trạng thái thực tế.

Ví dụ desired state:

~~~text
Topic: orders
Partitions: 6
Replication factor: 3
retention.ms: 604800000
cleanup.policy: delete
min.insync.replicas: 2
~~~

Quy trình:

1. Gọi listTopics() hoặc describeTopics() để kiểm tra topic.
2. Nếu chưa tồn tại, tạo bằng NewTopic.
3. Nếu đã tồn tại, mô tả partition, replica và config.
4. So sánh với desired state.
5. Nếu partition count thấp hơn mục tiêu, có thể tăng bằng createPartitions().
6. Nếu partition count cao hơn mục tiêu, không thể giảm trực tiếp.
7. Nếu config khác, đánh giá và cập nhật bằng incrementalAlterConfigs() khi phù hợp.
8. Không xóa/recreate topic chỉ để ép trạng thái về desired state.

Mô hình này giúp thao tác quản trị có thể retry an toàn hơn sau timeout và tránh xóa nhầm dữ liệu.

### 10.1. Ví dụ kiểm tra topic trước khi tạo

~~~java
import java.util.Set;
import org.apache.kafka.clients.admin.ListTopicsOptions;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.admin.TopicDescription;
Set<String> names = admin.listTopics(
    new ListTopicsOptions().listInternal(false)
).names().get();

if (names.contains("orders")) {
    TopicDescription existing = admin.describeTopics(
        Set.of("orders")
    ).allTopicNames().get().get("orders");

    System.out.println(
        "orders already exists with "
        + existing.partitions().size()
        + " partitions"
    );
} else {
    NewTopic topic = new NewTopic("orders", 6, (short) 3);
    admin.createTopics(List.of(topic)).all().get();
}
~~~

Đây là kiểm tra ở cấp ứng dụng, không phải thao tác compare-and-set nguyên tử. Một process khác vẫn có thể tạo topic giữa lúc list và create. Vì vậy vẫn phải xử lý TopicExistsException và xác minh lại trạng thái sau lỗi.

## 11. Tạo thêm partition cho topic hiện có

Kafka cho phép tăng partition count nhưng không hỗ trợ giảm partition count trực tiếp.

Dùng createPartitions():

~~~java
import java.util.Map;
import org.apache.kafka.clients.admin.NewPartitions;

admin.createPartitions(
    Map.of("orders", NewPartitions.increaseTo(12))
).all().get();
~~~

Tăng partition có thể thay đổi mapping key sang partition nếu producer dùng default partitioner và số partition tăng. Điều này có thể ảnh hưởng ordering theo key trong tương lai. Hãy đánh giá trước khi tăng partition cho topic có yêu cầu ordering nghiệp vụ.

Tăng partition cũng không tự di chuyển dữ liệu cũ sang partition mới. Record đã tồn tại vẫn ở partition cũ.

## 12. Quyền ACL cho Admin API

AdminClient sử dụng principal được cấu hình trong security protocol. Các thao tác quản trị cần quyền phù hợp.

Ví dụ theo nguyên tắc least privilege:

| Thao tác | Quyền cần kiểm tra |
|---|---|
| List topics | Quyền Describe phù hợp trên cluster/topic theo cấu hình ACL. |
| Describe topic | Describe trên topic. |
| Describe topic configs | DescribeConfigs trên topic. |
| Create topic | Create trên topic hoặc quyền cluster-level tương ứng. |
| Delete topic | Delete trên topic hoặc quyền cluster-level tương ứng. |
| Tạo partition | Quyền quản trị phù hợp với topic. |

Tên resource và phạm vi ACL chính xác phụ thuộc authorizer và cấu hình cluster. Không cấp quyền Cluster-level rộng chỉ để một service tạo một topic cụ thể nếu có thể giới hạn bằng topic prefix hoặc resource pattern.

Nên tách principal cho ứng dụng nghiệp vụ và principal cho provisioning. Ứng dụng chỉ gửi/đọc record không nên mặc nhiên có quyền xóa topic.

## 13. Tích hợp AdminClient với Spring

Có thể quản lý AdminClient như một Spring bean để tái sử dụng trong service.

~~~java
import org.apache.kafka.clients.admin.AdminClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaAdmin;

@Configuration
public class KafkaAdminConfiguration {

    @Bean
    public AdminClient adminClient(KafkaAdmin kafkaAdmin) {
        return AdminClient.create(kafkaAdmin.getConfigurationProperties());
    }
}
~~~

Service sử dụng bean:

~~~java
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class TopicManagementService {

    private final AdminClient adminClient;

    public TopicManagementService(AdminClient adminClient) {
        this.adminClient = adminClient;
    }

    public void createOrdersTopic() throws Exception {
        NewTopic orders = new NewTopic(
            "orders",
            6,
            (short) 3
        );

        adminClient.createTopics(List.of(orders)).all().get();
    }
}
~~~

Trong ứng dụng Spring Boot, KafkaAdmin có thể tự tạo topic từ các bean NewTopic khai báo trong context. Cách đó phù hợp khi topic là một phần của cấu hình ứng dụng.

~~~java
@Bean
NewTopic ordersTopic() {
    return new NewTopic("orders", 6, (short) 3);
}
~~~

Nếu cần tạo topic động theo yêu cầu quản trị, dùng AdminClient trong service và áp dụng xác thực, authorization, validation và audit log.

Đảm bảo AdminClient được đóng khi Spring context shutdown. Nếu tạo bean thủ công, khai báo destroy method hoặc lifecycle callback phù hợp với cách quản lý bean của ứng dụng.

## 14. Khi nào nên dùng script CLI và khi nào dùng AdminClient?

| Nhu cầu | Công cụ phù hợp |
|---|---|
| Thao tác nhanh trong lab hoặc terminal | Kafka CLI như kafka-topics.sh |
| Script triển khai đơn giản | CLI hoặc AdminClient tùy hệ thống |
| Ứng dụng quản trị topic theo API | AdminClient |
| Trang quản trị hiển thị metadata | AdminClient |
| Provision topic tự động theo tenant/service | AdminClient hoặc Spring Kafka KafkaAdmin |
| Điều tra cluster thủ công | CLI kết hợp AdminClient |
| Tạo topic cố định khi ứng dụng khởi động | Spring NewTopic bean hoặc pipeline provisioning |

Dù dùng CLI hay API, cần cùng một chính sách phân quyền, naming, replication, retention và audit.

## 15. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Tạo topic nhận TopicExistsException | Topic đã được tạo bởi process khác hoặc request trước thành công nhưng response bị mất. | Describe topic và xác minh desired state. |
| Tạo topic bị InvalidReplicationFactorException | RF cao hơn số broker khả dụng hoặc placement không thể thỏa mãn. | Kiểm tra broker, rack awareness và replication factor. |
| Tạo topic timeout | Controller đang failover, cluster bận hoặc network lỗi. | Kiểm tra controller/broker health; describe lại trước khi retry. |
| Topic xuất hiện nhưng chưa dùng được | Metadata propagation hoặc broker đang hoàn tất thao tác. | Chờ metadata ổn định và kiểm tra partition leader. |
| listTopics không thấy topic nội bộ | listInternal(false) đang lọc internal topic. | Dùng listInternal(true) khi điều tra. |
| describeTopics báo topic không tồn tại | Sai tên, topic vừa bị xóa hoặc metadata chưa cập nhật. | Kiểm tra lại danh sách topic và trạng thái controller. |
| deleteTopics không xóa được | delete.topic.enable tắt, ACL thiếu hoặc topic không tồn tại. | Kiểm tra broker config, ACL và exception gốc. |
| Xóa xong nhưng topic còn trong metadata tạm thời | Quá trình xóa phân tán chưa hoàn tất. | Chờ và xác minh lại, không tạo lại ngay. |
| Không đọc được topic config | Thiếu DescribeConfigs hoặc config nhạy cảm/không trả giá trị. | Kiểm tra ACL và cờ sensitive/default. |
| AdminClient giữ connection sau shutdown | Không đóng client hoặc quản lý lifecycle sai. | Dùng try-with-resources hoặc Spring destroy callback. |

## 16. Checklist trước khi quản trị topic production

Trước khi tạo hoặc xóa topic, hãy xác nhận:

1. Đang kết nối đúng cluster và environment chưa?
2. Topic name đã được validate theo naming convention chưa?
3. Topic có tồn tại hay không?
4. Partition count có phù hợp throughput và ordering không?
5. Replication factor có phù hợp số broker và failure domain không?
6. min.insync.replicas có phù hợp với producer acks không?
7. Retention và cleanup policy có phù hợp yêu cầu lưu trữ không?
8. Có ACL tối thiểu cần thiết cho thao tác không?
9. Có audit log cho người yêu cầu và kết quả không?
10. Nếu delete, đã xác nhận dữ liệu có thể bị loại bỏ chưa?
11. Nếu timeout, ứng dụng có kiểm tra trạng thái thực tế trước khi retry không?
12. AdminClient có timeout và lifecycle rõ ràng không?
13. Có giám sát lỗi API, latency và số thao tác quản trị không?

## 17. Bài tập thực hành

### Bài 1: Tạo topic bằng AdminClient

1. Khởi động Kafka cluster lab có ít nhất ba broker.
2. Tạo topic orders-lab với 6 partition và RF=3.
3. Đặt retention.ms và min.insync.replicas.
4. Chờ future hoàn tất.
5. In thông báo tạo thành công.
6. Chạy lại chương trình và xử lý TopicExistsException.

### Bài 2: Liệt kê topic

1. Gọi listTopics().names().
2. In tất cả topic người dùng.
3. Gọi listTopics() với listInternal(false).
4. Gọi lại với listInternal(true).
5. So sánh kết quả và xác định các internal topic.

### Bài 3: Mô tả metadata

1. Gọi describeTopics() cho orders-lab.
2. In partition count.
3. In leader, replicas và ISR của từng partition.
4. Dừng một broker trong môi trường lab.
5. Mô tả lại topic và quan sát ISR/leader thay đổi.
6. Khởi động broker và theo dõi ISR phục hồi.

### Bài 4: Đọc topic config

1. Dùng ConfigResource.Type.TOPIC.
2. Gọi describeConfigs().
3. In retention.ms, cleanup.policy và min.insync.replicas.
4. Phân biệt config default với config được override.
5. Kiểm tra quyền DescribeConfigs.

### Bài 5: Xóa topic test

1. Tạo topic orders-delete-lab.
2. Liệt kê để xác nhận topic tồn tại.
3. Mô tả topic và xác nhận đúng partition.
4. Xóa topic bằng deleteTopics().
5. Chờ kết quả future.
6. Liệt kê và xác minh topic đã biến mất.
7. Thử xóa một tên không tồn tại và xử lý exception.

Chỉ thực hiện thao tác xóa trên topic lab. Không chạy bài tập này trên topic production hoặc topic dùng chung.

### Bài 6: Xây dựng TopicManagementService

Tạo service Java hoặc Spring có các phương thức:

- createTopic(name, partitions, replicationFactor).
- listTopics(includeInternal).
- describeTopic(name).
- describeTopicConfigs(name).
- deleteTopic(name).

Bổ sung validation tên topic, timeout, xử lý lỗi theo từng topic và audit log. Với deleteTopic(), yêu cầu xác nhận rõ ràng từ tầng gọi và chặn các tên topic được bảo vệ.

## 18. Câu hỏi tự kiểm tra

1. Kafka Admin API dùng để làm gì?
2. AdminClient khác KafkaProducer và KafkaConsumer ở điểm nào?
3. Vì sao các phương thức Admin API thường trả về KafkaFuture?
4. NewTopic nhận các tham số cơ bản nào?
5. Replication factor có thể lớn hơn số broker khả dụng không?
6. Vì sao partition count ảnh hưởng ordering theo key?
7. listTopics() khác describeTopics() như thế nào?
8. Làm sao lọc internal topic?
9. TopicPartitionInfo cung cấp metadata nào?
10. ISR khác replica assignment như thế nào?
11. describeConfigs() dùng ConfigResource ra sao?
12. TopicExistsException nên được xử lý thế nào?
13. Timeout khi create topic có chứng minh topic chưa được tạo không?
14. Vì sao deleteTopics() là thao tác rủi ro?
15. delete.topic.enable có vai trò gì?
16. Có thể giảm partition count của topic hiện có bằng Admin API không?
17. Vì sao không nên xóa rồi tạo lại topic để thay đổi config?
18. AdminClient cần ACL nào để tạo, mô tả và xóa topic?
19. Khi dùng Spring Kafka, có những cách nào để khai báo topic?
20. Sau timeout, vì sao nên mô tả trạng thái thực tế trước khi retry?

## Kết luận

Kafka Admin API cung cấp cách quản trị topic trực tiếp từ ứng dụng Java. NewTopic và createTopics() tạo topic với partition count, replication factor và config mong muốn. listTopics() liệt kê topic; describeTopics() trả về metadata partition, leader, replica và ISR; describeConfigs() đọc cấu hình; deleteTopics() yêu cầu xóa topic.

Các API quản trị trả kết quả bất đồng bộ, vì vậy cần xử lý KafkaFuture, timeout và exception. Timeout không luôn có nghĩa thao tác chưa xảy ra; hãy kiểm tra trạng thái thực tế trước khi retry. Tạo topic cần cân nhắc partition, replication và retention. Xóa topic có thể làm mất dữ liệu nên phải kiểm tra môi trường, tên topic và ACL trước khi thực hiện.

Trong production, nên quản trị topic theo desired state, tách quyền provisioning khỏi ứng dụng nghiệp vụ và ghi audit cho các thao tác thay đổi. AdminClient là nền tảng để xây dựng công cụ quản trị Kafka có kiểm soát trong Java và Spring Kafka.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Admin API | API quản trị cluster và metadata Kafka. |
| AdminClient | Java client thực hiện các thao tác quản trị Kafka. |
| NewTopic | Đối tượng mô tả topic cần tạo. |
| createTopics() | Gửi yêu cầu tạo một hoặc nhiều topic. |
| listTopics() | Liệt kê topic trong cluster. |
| describeTopics() | Lấy metadata chi tiết của topic và partition. |
| TopicDescription | Kết quả mô tả topic. |
| TopicPartitionInfo | Metadata một partition gồm leader, replicas và ISR. |
| describeConfigs() | Đọc cấu hình broker hoặc topic. |
| deleteTopics() | Gửi yêu cầu xóa topic. |
| KafkaFuture | Future đại diện cho kết quả bất đồng bộ của Kafka client. |
| Replication factor | Số replica được gán cho mỗi partition. |
| ISR | Tập replica đang đồng bộ với leader theo điều kiện Kafka. |
| Internal topic | Topic nội bộ Kafka dùng để lưu metadata hoặc trạng thái dịch vụ. |
| ACL | Quy tắc phân quyền principal trên resource Kafka. |
| Desired state | Trạng thái topic mong muốn để so sánh với trạng thái thực tế. |


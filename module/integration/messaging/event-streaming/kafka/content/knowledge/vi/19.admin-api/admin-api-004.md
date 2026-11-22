# Thêm partition và kiểm tra điều kiện thay đổi

## Mục tiêu bài học

Khi throughput tăng hoặc consumer cần thêm khả năng xử lý song song, quản trị viên có thể tăng số partition của Kafka topic bằng Admin API. Thao tác này tạo thêm partition mới và cập nhật metadata của topic. Trước khi thay đổi, cần kiểm tra số partition hiện tại, replication factor, broker capacity, replica assignment, quyền ACL và tác động đến key ordering của ứng dụng.

Bài học hướng dẫn cách dùng Kafka AdminClient để đọc metadata topic, kiểm tra điều kiện, chạy validation-only và gọi createPartitions. Người học cũng thực hành bằng Kafka CLI, tích hợp AdminClient trong Spring Kafka và lập kế hoạch thay đổi an toàn cho consumer group đang hoạt động.

Sau bài học, người học có thể:

- Giải thích partition count ảnh hưởng đến khả năng song song và phân phối dữ liệu.
- Kiểm tra topic metadata, partition, leader, replica và ISR trước khi thay đổi.
- Tăng partition bằng AdminClient.createPartitions.
- Dùng validateOnly để kiểm tra yêu cầu mà chưa áp dụng thay đổi.
- Chỉ định replica assignment cho các partition mới khi cần.
- Đánh giá broker capacity, replication factor, rack awareness và ACL.
- Hiểu tác động của tăng partition đến key mapping, ordering, consumer rebalance và lag.
- Thực hiện thay đổi bằng Kafka CLI và tích hợp thao tác trong Spring.

## 1. Vì sao cần tăng số partition?

Partition là đơn vị lưu trữ và xử lý song song của Kafka topic. Mỗi partition có log riêng, offset riêng và được leader broker phục vụ các request đọc/ghi. Consumer group có thể phân phối các partition cho nhiều consumer để tăng khả năng xử lý song song.

Ví dụ topic orders có ba partition:

~~~text
orders-0
orders-1
orders-2
~~~

Nếu group có sáu consumer, tối đa ba consumer có thể được gán partition; ba consumer còn lại không có partition để đọc. Tăng topic lên sáu partition có thể cho phép cả sáu consumer cùng làm việc, nếu workload và broker capacity phù hợp.

~~~mermaid
flowchart TB
    subgraph BEFORE["Trước khi tăng: 3 partitions"]
        P0["orders-0"] --> C0["Consumer 0"]
        P1["orders-1"] --> C1["Consumer 1"]
        P2["orders-2"] --> C2["Consumer 2"]
        C3["Consumer 3<br/>idle"]
    end
    subgraph AFTER["Sau khi tăng: 6 partitions"]
        Q0["orders-0"] --> D0["Consumer 0"]
        Q1["orders-1"] --> D1["Consumer 1"]
        Q2["orders-2"] --> D2["Consumer 2"]
        Q3["orders-3"] --> D3["Consumer 3"]
        Q4["orders-4"] --> D4["Consumer 4"]
        Q5["orders-5"] --> D5["Consumer 5"]
    end
~~~

Tăng partition có thể giúp:

- Tăng số luồng đọc song song trong một consumer group.
- Phân tán write load và dữ liệu trên nhiều partition leader.
- Giảm lượng dữ liệu mỗi partition phải xử lý trong một số workload.
- Hỗ trợ tăng concurrency của ứng dụng khi consumer trước đó bị giới hạn bởi partition count.

Tăng partition không tự động làm throughput tăng. Nếu bottleneck nằm ở database, network, serializer, broker disk hoặc consumer xử lý nghiệp vụ thì thêm partition có thể không cải thiện đáng kể.

## 2. Những điều cần hiểu trước khi thay đổi

### 2.1. Partition count là tổng số partition mục tiêu

Khi topic hiện có sáu partition và muốn tăng lên mười, giá trị truyền cho Admin API là tổng số partition mới 10, không phải số partition cần thêm 4.

~~~text
Current partition count = 6
Target partition count  = 10
New partitions          = 4
~~~

Kafka tạo các partition có ID tiếp theo, ví dụ partition 6, 7, 8 và 9. Partition cũ vẫn giữ nguyên dữ liệu và offset.

### 2.2. Kafka chỉ hỗ trợ tăng partition

Không thể giảm partition count của một topic đã tồn tại bằng createPartitions. Nếu cần số partition ít hơn, cách thông thường là tạo topic mới với partition count mong muốn rồi migrate dữ liệu/producer/consumer theo kế hoạch.

Không xóa topic cũ trước khi xác minh dữ liệu, consumer group và ứng dụng đã chuyển hoàn tất.

### 2.3. Tăng partition không di chuyển dữ liệu cũ

Các record đang nằm trong partition cũ không tự động được phân phối lại sang partition mới. Partition mới bắt đầu nhận record sau khi metadata thay đổi và producer sử dụng partitioner với số partition mới.

Điều này có nghĩa:

- Dữ liệu lịch sử vẫn nằm ở partition cũ.
- Consumer group sẽ nhận assignment có thêm partition.
- Record mới có thể được phân phối sang partition mới.
- Lag và throughput cần được quan sát sau thay đổi.

### 2.4. Partition count ảnh hưởng đến key mapping

Với record có key, partitioner mặc định thường dùng hash của serialized key kết hợp số partition để chọn partition. Khi số partition thay đổi, cùng một key có thể được ánh xạ sang partition khác cho những record gửi sau.

Ví dụ:

~~~text
Trước: hash(order-42) -> partition 1 trong 3 partition
Sau:   hash(order-42) -> partition 5 trong 6 partition
~~~

Đây là ví dụ minh họa; partition thực tế phụ thuộc serializer, partitioner và thuật toán của client.

Kafka chỉ đảm bảo thứ tự record bên trong một partition. Nếu event cũ của order-42 nằm ở partition 1 và event mới cùng key được gửi sang partition 5 sau khi tăng partition, hai event có thể được consumer xử lý độc lập và không còn thứ tự toàn cục theo key.

Nếu nghiệp vụ yêu cầu strict ordering theo key trong toàn bộ vòng đời dữ liệu, cần đánh giá kỹ trước khi tăng partition. Các lựa chọn gồm:

- Giữ nguyên partition count cho topic đó.
- Tạo topic version mới và migrate có kiểm soát.
- Dùng custom partitioner có mapping ổn định, nhưng phải thiết kế trước capacity và partition range.
- Đưa sequence/version nghiệp vụ vào event và kiểm tra thứ tự ở consumer.

Không coi việc dùng cùng key là bảo đảm ordering bất biến qua mọi lần thay đổi partition count.

## 3. Preflight: kiểm tra điều kiện trước khi tăng partition

Không nên chạy createPartitions ngay khi thấy consumer lag. Trước hết hãy xác định bottleneck và kiểm tra điều kiện của topic/cluster.

### 3.1. Kiểm tra metadata topic

Thu thập:

- Topic có tồn tại và đúng tên không?
- Partition count hiện tại là bao nhiêu?
- Mỗi partition có leader hợp lệ không?
- Replica assignment có đúng replication factor mong muốn không?
- ISR có đủ replica theo yêu cầu durability không?
- Có partition offline hoặc under-replicated không?

Kafka CLI:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic orders
~~~

Ví dụ kết quả:

~~~text
Topic: orders  PartitionCount: 6  ReplicationFactor: 3
Topic: orders  Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,2,3
Topic: orders  Partition: 1  Leader: 2  Replicas: 2,3,1  Isr: 2,3,1
...
~~~

Nếu ISR thiếu hoặc partition offline, cần xử lý sức khỏe cluster trước. Thêm partition trong lúc broker đang thiếu replica có thể làm tăng áp lực metadata, disk và replication.

### 3.2. Kiểm tra broker capacity

Mỗi partition mới tạo thêm:

- Partition log và segment files.
- Replica trên các broker theo replication factor.
- File handle, metadata và index overhead.
- Công việc replication, recovery và leader election.
- Consumer assignment và offset state.

Ước lượng số replica mới:

~~~text
New partition replicas
  = (target partition count - current partition count)
    x replication factor
~~~

Ví dụ tăng từ 6 lên 12 partition với replication factor 3:

~~~text
New partitions = 12 - 6 = 6
New replicas   = 6 x 3 = 18
~~~

Đây là số replica bổ sung trong toàn cluster, không phải 18 replica trên mỗi broker. Cần kiểm tra phân bố theo broker, rack, disk và network.

### 3.3. Kiểm tra replication factor và min.insync.replicas

Khi tăng partition mà không chỉ định replica assignment riêng, Kafka tạo assignment cho partition mới theo replication factor của topic. Cần bảo đảm số broker phù hợp và broker có đủ capacity.

Nếu topic dùng min.insync.replicas=2 và replication factor 3, cần đủ replica đồng bộ để producer với acks=all tiếp tục ghi theo yêu cầu. Thêm partition không sửa được tình trạng ISR thiếu.

Kiểm tra topic config:

~~~bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name orders --describe
~~~

### 3.4. Kiểm tra ACL và quyền quản trị

Principal chạy Admin API cần quyền phù hợp trên topic. Với thao tác thay đổi partition, cần quyền ALTER trên topic; kiểm tra metadata thường cần quyền DESCRIBE. Cụm có policy bổ sung có thể yêu cầu thêm quyền theo cấu hình bảo mật.

Không dùng tài khoản production có quyền rộng hơn mức cần thiết. Nên thực hiện thay đổi bằng principal quản trị được cấp quyền theo quy trình.

### 3.5. Kiểm tra tác động ứng dụng

Trước khi tăng, xác định:

- Producer có dùng key và partitioner nào?
- Có consumer nào giả định partition count cố định không?
- Consumer group có thể rebalance và xử lý thêm partition không?
- Downstream có giới hạn concurrency hoặc connection pool không?
- Có yêu cầu ordering theo key không?
- Có batch job hoặc connector phụ thuộc partition count không?
- Dashboard/alert có hard-code danh sách partition không?

Đặc biệt, nếu ứng dụng lưu partition number bên ngoài Kafka hoặc tự chỉ định partition, cần cập nhật thiết kế tương ứng.

## 4. Đọc metadata và kiểm tra điều kiện bằng AdminClient

Kafka Java AdminClient cho phép quản trị topic bằng API bất đồng bộ. Các lời gọi trả về result object chứa KafkaFuture để ứng dụng chờ hoặc ghép các tác vụ.

### 4.1. Tạo AdminClient

~~~java
import java.util.Properties;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;

public class AdminClientFactory {

    public static AdminClient create() {
        Properties props = new Properties();
        props.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(AdminClientConfig.CLIENT_ID_CONFIG, "topic-admin-tool");
        return AdminClient.create(props);
    }
}
~~~

Trong production, bổ sung TLS/SASL, credential, request timeout và client ID theo chuẩn vận hành của cluster. Không ghi password trực tiếp vào source code.

### 4.2. Đọc partition count hiện tại

~~~java
import java.util.Collections;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.TopicDescription;

public class TopicInspector {

    public static int partitionCount(AdminClient admin, String topic)
            throws Exception {
        TopicDescription description = admin
            .describeTopics(Collections.singleton(topic))
            .values()
            .get(topic)
            .get(15, TimeUnit.SECONDS);

        return description.partitions().size();
    }
}
~~~

TopicDescription.partitions() chứa metadata partition. Từ mỗi TopicPartitionInfo, có thể đọc partition ID, leader, replicas và ISR để kiểm tra sức khỏe topic.

Ví dụ duyệt assignment:

~~~java
TopicDescription description = admin
    .describeTopics(Collections.singleton("orders"))
    .values()
    .get("orders")
    .get();

description.partitions().forEach(partition -> {
    System.out.printf(
        "partition=%d leader=%s replicas=%s isr=%s%n",
        partition.partition(),
        partition.leader(),
        partition.replicas(),
        partition.isr()
    );
});
~~~

Trong code production, đặt timeout rõ ràng cho Future và xử lý exception khi topic không tồn tại hoặc principal không có quyền DESCRIBE.

### 4.3. Kiểm tra broker đang có

~~~java
admin.describeCluster().nodes().get().forEach(node ->
    System.out.printf(
        "brokerId=%d host=%s port=%d rack=%s%n",
        node.id(),
        node.host(),
        node.port(),
        node.rack()
    )
);
~~~

Danh sách node giúp kiểm tra số broker và thông tin rack nếu cluster công bố rack metadata. Có đủ broker về số lượng chưa đồng nghĩa capacity đủ; cần đối chiếu disk, network, CPU và replica placement.

## 5. Tăng partition bằng AdminClient.createPartitions

API chính là:

~~~java
admin.createPartitions(
    Map<String, NewPartitions> newPartitions,
    CreatePartitionsOptions options
);
~~~

NewPartitions.increaseTo(targetCount) nhận tổng partition count mong muốn. CreatePartitionsOptions cho phép đặt timeout và validate-only.

### 5.1. Kiểm tra rồi mới tăng

~~~java
import java.util.Collections;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.CreatePartitionsOptions;
import org.apache.kafka.clients.admin.NewPartitions;
import org.apache.kafka.clients.admin.TopicDescription;

public class PartitionManager {

    public static void increase(
            AdminClient admin,
            String topic,
            int targetCount) throws Exception {

        TopicDescription description = admin
            .describeTopics(Collections.singleton(topic))
            .values()
            .get(topic)
            .get(15, TimeUnit.SECONDS);

        int currentCount = description.partitions().size();

        if (targetCount <= currentCount) {
            throw new IllegalArgumentException(
                "Target partition count must be greater than current count"
            );
        }

        Map<String, NewPartitions> request = Collections.singletonMap(
            topic,
            NewPartitions.increaseTo(targetCount)
        );

        CreatePartitionsOptions options =
            new CreatePartitionsOptions().timeoutMs(30000);

        admin.createPartitions(request, options)
            .all()
            .get(35, TimeUnit.SECONDS);
    }
}
~~~

Đoạn code trên kiểm tra số partition trước khi tạo yêu cầu. Trong ứng dụng quản trị thực tế, nên thêm bước kiểm tra leader/ISR, broker capacity, ACL và approval trước khi gọi increase.

### 5.2. Validate-only trước khi áp dụng

validateOnly(true) yêu cầu broker kiểm tra request mà không thực hiện thay đổi:

~~~java
CreatePartitionsOptions validateOptions =
    new CreatePartitionsOptions()
        .timeoutMs(30000)
        .validateOnly(true);

admin.createPartitions(
    Collections.singletonMap(
        "orders",
        NewPartitions.increaseTo(12)
    ),
    validateOptions
).all().get(35, TimeUnit.SECONDS);
~~~

Nếu validation thành công, request vượt qua các kiểm tra mà broker thực hiện tại thời điểm đó. Đây không phải cam kết rằng lần thực thi sau chắc chắn thành công: trạng thái cluster, quyền, quota hoặc broker availability có thể thay đổi giữa hai lần gọi.

Tính năng validate-only phụ thuộc phiên bản Kafka client và broker hỗ trợ trường tương ứng của CreatePartitions API. Với broker cũ, request có thể bị từ chối do API version không hỗ trợ; cần kiểm tra compatibility của cluster trước khi dựa vào bước này.

Sau khi review kết quả, gửi lại request với validateOnly(false) hoặc dùng options mặc định để thực hiện thật.

### 5.3. Tăng nhiều topic trong một request

Admin API hỗ trợ yêu cầu thay đổi partition cho nhiều topic:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

Map<String, NewPartitions> changes = new HashMap<>();
changes.put("orders", NewPartitions.increaseTo(12));
changes.put("payments", NewPartitions.increaseTo(9));

admin.createPartitions(changes)
    .all()
    .get(35, TimeUnit.SECONDS);
~~~

Kết quả có thể thành công hoặc thất bại theo từng topic. Nếu cần audit rõ từng topic, đọc từng Future trong CreatePartitionsResult.values() thay vì chỉ kiểm tra một kết quả tổng hợp.

Không gộp quá nhiều thay đổi lớn trong một request nếu cần kiểm soát blast radius. Có thể chia theo đợt để quan sát cluster sau mỗi đợt.

Preflight đọc partition count và request createPartitions không phải một transaction khóa topic xuyên suốt. Nếu một operator khác đồng thời thay đổi topic giữa hai bước, request có thể thất bại hoặc gặp trạng thái khác dự kiến. Nên có một đầu mối điều phối thay đổi và luôn xác minh metadata ngay trước/sau thao tác.

## 6. Chỉ định replica assignment cho partition mới

Mặc định Kafka tự tạo replica assignment dựa trên broker và replication factor của topic. Khi cần kiểm soát placement, có thể truyền danh sách broker ID cho các partition mới.

Ví dụ topic hiện có 6 partition, muốn tăng lên 8 và chỉ định replica cho partition 6, 7:

~~~java
import java.util.List;

List<List<Integer>> assignments = List.of(
    List.of(1, 2, 3), // Partition 6: replica trên broker 1, 2, 3
    List.of(2, 3, 1)  // Partition 7: replica trên broker 2, 3, 1
);

NewPartitions newPartitions =
    NewPartitions.increaseTo(8, assignments);

admin.createPartitions(
    Collections.singletonMap("orders", newPartitions)
).all().get();
~~~

Danh sách assignment có một phần tử cho mỗi partition mới. Mỗi phần tử chứa broker ID của các replica; replica đầu tiên thường là preferred leader trong assignment. Số replica trong mỗi danh sách phải phù hợp replication factor của topic và broker ID phải hợp lệ.

Ví dụ dùng List.of nên cần Java 9 trở lên. Với Java 8, tạo các list bằng Arrays.asList hoặc collection tương ứng.

Khi chỉ định assignment:

- Không lặp broker ID trong cùng một partition.
- Không chỉ định broker không tồn tại.
- Phân bố replica qua rack/failure domain khác nhau nếu cluster có rack awareness.
- Tránh dồn leader hoặc replica mới lên một broker đang quá tải.
- Xem xét disk, network và số replica hiện tại của từng broker.

Tạo partition với replica assignment không thay thế quy trình reassignment của các partition đã tồn tại. Nếu muốn chuyển replica của partition cũ sang broker khác, dùng partition reassignment workflow riêng.

## 7. Kafka CLI: tăng partition bằng lệnh

Kafka CLI gọi Admin API ở phía dưới và phù hợp với thao tác quản trị thủ công.

### 7.1. Kiểm tra hiện trạng

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic orders
~~~

Ghi lại partition count, replication factor, leader, replica và ISR.

### 7.2. Tăng từ 6 lên 12 partition

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --alter --topic orders --partitions 12
~~~

Giá trị 12 là tổng partition count mục tiêu. Lệnh này không có nghĩa thêm 12 partition.

### 7.3. Xác minh sau thay đổi

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic orders
~~~

Xác nhận:

- Partition count bằng giá trị mục tiêu.
- Partition mới có leader.
- Replica assignment phù hợp.
- ISR đạt yêu cầu.
- Không có partition offline hoặc under-replicated kéo dài.

CLI alter không cung cấp cùng trải nghiệm validate-only như AdminClient options trong mọi phiên bản. Nếu cần preflight tự động, dùng AdminClient và CreatePartitionsOptions.validateOnly(true).

## 8. Điều gì xảy ra với producer sau khi tăng partition?

Producer lấy metadata topic từ cluster. Khi metadata được cập nhật, producer partitioner có thể chọn trong tập partition mới.

Các điểm cần lưu ý:

- Producer không cần tạo lại KafkaProducer chỉ vì partition count tăng.
- Client có thể cần thời gian refresh metadata.
- Record có key có thể được ánh xạ sang partition khác sau thay đổi.
- Producer chỉ định partition thủ công phải kiểm tra partition ID vẫn hợp lệ.
- Custom partitioner phải xử lý partition count mới.

Nếu producer cache metadata lâu hoặc có custom partitioner, kiểm tra thời điểm metadata refresh và logic chọn partition. Không tự giả định mọi instance producer nhìn thấy metadata mới cùng một thời điểm.

### 8.1. Producer gửi không có key

Partitioner mặc định của Kafka client có thể dùng sticky partitioning cho record không có key để gom batch hiệu quả. Sau khi partition count tăng, phân phối batch có thể thay đổi.

Nếu không có key, ứng dụng không có bảo đảm ordering theo aggregate. Nếu cần ordering, hãy dùng key nghiệp vụ ổn định và thiết kế partition strategy phù hợp.

## 9. Điều gì xảy ra với consumer group?

Khi topic có partition mới, consumer group cần cập nhật assignment để các member có thể đọc partition đó. Tùy assignor và protocol, group có thể thực hiện rebalance hoặc incremental reassignment.

Sau thay đổi:

- Partition mới có thể được gán cho consumer hiện tại hoặc consumer khác.
- Consumer mới có thể được dùng để tăng concurrency.
- Consumer group có thể tạm dừng một phần quá trình fetch trong rebalance.
- Partition mới chưa có committed offset riêng cho group.
- Consumer áp dụng auto.offset.reset khi chưa có offset hợp lệ cho partition mới.

Nếu auto.offset.reset=latest, consumer có thể bắt đầu gần cuối log của partition mới; nếu partition mới chưa có record, nó sẽ bắt đầu chờ record mới. Nếu earliest, consumer đọc từ offset sớm nhất còn có thể đọc.

### 9.1. Số consumer lớn hơn partition count

Trong một consumer group, một partition tại một thời điểm chỉ được gán cho một consumer member. Số consumer hoạt động có partition không thể vượt số partition được subscribe.

Tăng partition có thể cho phép tăng concurrency, nhưng cũng cần đảm bảo downstream đủ capacity. Nếu database connection pool chỉ chịu được bốn worker mà tăng consumer lên mười hai, hệ thống có thể chuyển bottleneck sang database.

### 9.2. Offset của partition mới

Partition mới không có lịch sử record cũ của topic. Consumer group chưa commit offset cho partition đó. Client sẽ dùng reset policy khi bắt đầu đọc.

Không copy committed offset từ partition cũ sang partition mới một cách tùy tiện. Offset là vị trí riêng trong từng partition, không phải checkpoint toàn topic.

## 10. Tích hợp thao tác tăng partition trong Spring

Spring Kafka cung cấp KafkaAdmin để quản lý topic và cấu hình AdminClient. NewTopic bean thường hữu ích để khai báo topic cần tạo khi ứng dụng khởi động; với topic đã tồn tại cần tăng partition theo yêu cầu vận hành, hãy gọi AdminClient rõ ràng và kiểm tra số partition hiện tại.

### 10.1. Tạo AdminClient bean

~~~java
import org.apache.kafka.clients.admin.AdminClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaAdmin;

@Configuration
public class KafkaAdminClientConfiguration {

    @Bean(destroyMethod = "close")
    AdminClient adminClient(KafkaAdmin kafkaAdmin) {
        return AdminClient.create(kafkaAdmin.getConfigurationProperties());
    }
}
~~~

Bean dùng chung AdminClient và đóng khi Spring context shutdown. Không tạo/đóng AdminClient cho từng request quản trị.

### 10.2. Service tăng partition

~~~java
import java.util.Collections;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.NewPartitions;
import org.springframework.stereotype.Service;

@Service
public class TopicPartitionService {

    private final AdminClient adminClient;

    public TopicPartitionService(AdminClient adminClient) {
        this.adminClient = adminClient;
    }

    public void increase(String topic, int targetCount) throws Exception {
        int currentCount = adminClient
            .describeTopics(Collections.singleton(topic))
            .values()
            .get(topic)
            .get(15, TimeUnit.SECONDS)
            .partitions()
            .size();

        if (targetCount <= currentCount) {
            throw new IllegalArgumentException(
                "Target must be greater than current partition count"
            );
        }

        adminClient.createPartitions(
            Collections.singletonMap(
                topic,
                NewPartitions.increaseTo(targetCount)
            )
        ).all().get(35, TimeUnit.SECONDS);
    }
}
~~~

Trong production, service quản trị cần bổ sung xác thực người gọi, allowlist topic, audit log, giới hạn target count, validate-only workflow và approval. Không mở endpoint HTTP cho phép client tùy ý tăng partition trên mọi topic.

### 10.3. NewTopic bean không phải công cụ resize tổng quát

NewTopic bean thường được Spring Kafka dùng để tạo topic nếu chưa tồn tại. Không nên mặc định rằng thay partitions trong bean sẽ luôn resize topic đang tồn tại theo ý muốn. Với topic đã tồn tại, đọc metadata và gọi AdminClient.createPartitions để thực hiện thay đổi có chủ đích.

## 11. Các lỗi thường gặp khi tăng partition

| Lỗi/triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Target count không lớn hơn hiện tại | Truyền nhầm số partition cần thêm thay vì tổng số mục tiêu | Đọc current count và truyền target lớn hơn |
| Topic không tồn tại | Sai tên hoặc chưa tạo topic | Kiểm tra metadata và môi trường |
| Topic authorization failed | Principal thiếu quyền ALTER/DESCRIBE | Cấp ACL đúng phạm vi |
| Invalid replica assignment | Broker ID sai, số replica không hợp lệ hoặc lặp broker | Kiểm tra assignment và replication factor |
| Timeout khi createPartitions | Controller/broker chậm hoặc cluster quá tải | Kiểm tra controller, request latency và broker health |
| Partition mới chưa có leader | Broker/replica assignment có vấn đề | Kiểm tra broker availability, leader election và ISR |
| Consumer lag tăng sau thay đổi | Rebalance, consumer chưa đọc partition mới hoặc downstream nghẽn | Kiểm tra assignment, reset policy, throughput |
| Ordering theo key thay đổi | Key mapping đổi khi partition count thay đổi | Dùng sequence/version, migration hoặc partition strategy ổn định |
| Thêm partition nhưng throughput không tăng | Bottleneck ở downstream hoặc broker resource | Đo CPU, disk, network, batch, DB và consumer processing |

Các exception cụ thể phụ thuộc Kafka client/broker version. Hãy đọc cause chain của KafkaFuture và phân biệt lỗi request với timeout do ứng dụng chờ Future.

## 12. Quy trình thay đổi an toàn

Một quy trình thực tế:

1. Xác định mục tiêu và lý do tăng partition bằng metrics.
2. Ghi lại partition count, replication factor, assignment và ISR hiện tại.
3. Kiểm tra key ordering, custom partitioner và consumer assumptions.
4. Ước lượng số replica mới và tải bổ sung lên broker.
5. Kiểm tra ACL, quota, controller health và broker capacity.
6. Chạy AdminClient validate-only hoặc review command trong change plan.
7. Thực hiện thay đổi theo từng topic/đợt có kiểm soát.
8. Đọc lại metadata và xác minh leader/replica/ISR.
9. Theo dõi consumer rebalance, lag, producer distribution và downstream latency.
10. Ghi nhận kết quả và cập nhật tài liệu vận hành.

Nếu phát hiện vấn đề sau khi tăng, không thể giảm partition count để rollback trực tiếp. Có thể tạm dừng producer/consumer thay đổi, sửa consumer/partitioner hoặc migrate sang topic mới theo kế hoạch. Vì vậy, cần đánh giá key ordering và capacity trước khi thực hiện.

## 13. Bài tập thực hành

### Bài tập 1: Kiểm tra metadata bằng AdminClient

1. Tạo topic orders-lab có ba partition và replication factor phù hợp cluster lab.
2. Viết chương trình AdminClient đọc TopicDescription.
3. In partition ID, leader, replicas và ISR.
4. Kiểm tra số broker bằng describeCluster.
5. Ghi lại current partition count.

### Bài tập 2: Validate-only và tăng partition

1. Dùng AdminClient yêu cầu tăng orders-lab từ 3 lên 6 partition.
2. Gọi với validateOnly(true).
3. Xác minh partition count vẫn là 3.
4. Gọi lại với validate-only tắt.
5. Đọc metadata và xác minh có sáu partition.

### Bài tập 3: Quan sát key mapping và ordering

1. Gửi nhiều record cùng key order-42 khi topic có ba partition.
2. Ghi lại partition và offset của mỗi record.
3. Tăng partition count lên sáu.
4. Gửi tiếp record cùng key.
5. So sánh partition trước/sau và giải thích tác động đến ordering.

### Bài tập 4: Quan sát consumer rebalance

1. Chạy consumer group có hai member đọc topic ba partition.
2. Theo dõi assignment bằng Kafka CLI.
3. Tăng topic lên sáu partition.
4. Quan sát rebalance và assignment mới.
5. Kiểm tra committed offset và lag của partition mới.

### Bài tập 5: Replica assignment

1. Dùng cluster lab có ít nhất ba broker.
2. Tăng topic bằng NewPartitions.increaseTo(target, assignments).
3. Chỉ định broker ID cho từng partition mới.
4. Xác minh leader, replicas và ISR sau khi tạo.
5. So sánh với trường hợp Kafka tự sinh assignment.

## 14. Câu hỏi tự kiểm tra

1. Vì sao tăng partition có thể tăng consumer concurrency?
2. NewPartitions.increaseTo() nhận số partition mới hay tổng partition count mục tiêu?
3. Vì sao không thể giảm partition count bằng Admin API?
4. Tăng partition có di chuyển record cũ sang partition mới không?
5. Vì sao cùng key có thể được ánh xạ sang partition khác sau khi tăng partition?
6. Tác động của thay đổi partition count đến ordering là gì?
7. validateOnly(true) kiểm tra điều gì và không bảo đảm điều gì?
8. Khi chỉ định replica assignment, số broker ID trong mỗi danh sách cần thỏa điều kiện nào?
9. Consumer group xử lý partition mới và offset ban đầu ra sao?
10. Vì sao cần kiểm tra downstream capacity trước khi tăng concurrency?
11. NewTopic bean khác thao tác createPartitions trên topic đã tồn tại thế nào?
12. Nếu cần rollback về partition count cũ, có thể làm trực tiếp không?

Tăng partition là thay đổi cấu trúc topic có ảnh hưởng đến producer, consumer group, key mapping và tài nguyên cluster. Dùng AdminClient để đọc metadata, validate request và xác minh sau thay đổi giúp quản trị viên kiểm soát rủi ro trước khi mở rộng khả năng xử lý song song.

# Mô tả cluster, broker và phân bố replica

Khi vận hành Kafka, cần trả lời được ba câu hỏi: cluster đang có những broker nào, broker nào đang giữ vai trò controller, và các partition của topic đang có leader/replica/ISR trên broker nào. Java Admin API cung cấp AdminClient để lấy thông tin này trực tiếp từ cluster mà không cần tự phân tích log hoặc truy vấn từng broker.

Ba thao tác quan trọng là describeCluster() để xem thông tin cluster và broker, describeTopics() để xem phân bố partition/replica, và describeConfigs() để kiểm tra cấu hình broker/topic ảnh hưởng đến replication. Khi cần điều tra dung lượng replica trên ổ đĩa, có thể dùng describeLogDirs().

## 1. Các thành phần cần phân biệt

Kafka cluster gồm nhiều broker. Mỗi broker có một ID và phục vụ các request client. Topic được chia thành partition; mỗi partition có một replica assignment trên một hoặc nhiều broker.

| Thành phần | Ý nghĩa |
|---|---|
| Cluster | Tập hợp broker cùng quản lý metadata và dữ liệu Kafka |
| Broker | Server lưu log partition và phục vụ request producer/consumer |
| Controller | Thành phần điều phối metadata, leader election và thay đổi topology |
| Topic | Luồng dữ liệu logic được chia thành các partition |
| Partition | Log có thứ tự riêng, được lưu trên một hoặc nhiều broker |
| Leader replica | Replica nhận request ghi và phục vụ đọc theo cấu hình |
| Follower replica | Replica sao chép dữ liệu từ leader |
| ISR (In-Sync Replicas) | Các replica đang theo kịp leader theo tiêu chí đồng bộ của Kafka |
| Offline replica | Replica không khả dụng theo metadata hiện tại |

Broker ID là định danh số của broker trong cluster. Host và port là địa chỉ kết nối; một broker có thể quảng bá nhiều listener. Vì vậy, không nên coi host:port là định danh bền vững thay cho broker ID.

## 2. AdminClient là gì?

AdminClient là client Java dành cho các thao tác quản trị Kafka như:

- Mô tả cluster, broker và controller.
- Liệt kê topic và mô tả partition.
- Đọc cấu hình broker/topic.
- Kiểm tra log directory và replica trên broker.
- Tạo, xóa, tăng partition hoặc thay đổi cấu hình khi ứng dụng có quyền quản trị.

Bài này tập trung vào các API mô tả trạng thái. Các thao tác thay đổi cấu hình hoặc topology cần quy trình vận hành và quyền ACL riêng.

AdminClient là client bất đồng bộ. Hầu hết API trả về một đối tượng kết quả chứa KafkaFuture; ứng dụng có thể chờ kết quả bằng get() hoặc kết hợp các future để xử lý song song. Trong ví dụ học tập, dùng get(timeout, unit) để thể hiện rõ giới hạn chờ.

## 3. Kết nối đến cluster

Ví dụ tạo AdminClient bằng Java:

~~~java
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;

Properties properties = new Properties();
properties.put(
    AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
properties.put(
    AdminClientConfig.REQUEST_TIMEOUT_MS_CONFIG,
    10_000
);
properties.put(
    AdminClientConfig.DEFAULT_API_TIMEOUT_MS_CONFIG,
    30_000
);

try (AdminClient admin = AdminClient.create(properties)) {
    String clusterId = admin.describeCluster()
        .clusterId()
        .get(10, TimeUnit.SECONDS);

    System.out.println("Cluster ID: " + clusterId);
}
~~~

bootstrap.servers chỉ là danh sách địa chỉ ban đầu để client tìm cluster. Sau khi kết nối, AdminClient lấy metadata và gửi request đến broker phù hợp.

Các cấu hình cần quan tâm:

| Cấu hình | Vai trò |
|---|---|
| bootstrap.servers | Địa chỉ broker dùng để bootstrap |
| request.timeout.ms | Thời gian client chờ phản hồi cho một request |
| default.api.timeout.ms | Timeout mặc định cho các Admin API |
| security.protocol | Giao thức kết nối, ví dụ PLAINTEXT, SSL, SASL_SSL |
| sasl.mechanism | Cơ chế SASL khi cluster dùng SASL |
| ssl.truststore.location | Truststore khi xác thực TLS theo cấu hình tương ứng |

Trong môi trường production, lấy thông tin xác thực từ secret/configuration provider. Không hard-code password, private key hoặc JAAS secret trong source code hay log.

## 4. Mô tả cluster và danh sách broker

describeCluster() cung cấp cluster ID, danh sách node và controller hiện tại:

~~~java
import java.util.Collection;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.DescribeClusterResult;
import org.apache.kafka.common.Node;

DescribeClusterResult clusterResult = admin.describeCluster();

String clusterId =
    clusterResult.clusterId().get(10, TimeUnit.SECONDS);

Node controller =
    clusterResult.controller().get(10, TimeUnit.SECONDS);

Collection<Node> brokers =
    clusterResult.nodes().get(10, TimeUnit.SECONDS);

System.out.println("Cluster ID: " + clusterId);
if (controller != null) {
    System.out.printf(
        "Controller: id=%d host=%s port=%d%n",
        controller.id(),
        controller.host(),
        controller.port()
    );
} else {
    System.out.println("Controller: unavailable");
}

for (Node broker : brokers) {
    System.out.printf(
        "Broker: id=%d host=%s port=%d rack=%s%n",
        broker.id(),
        broker.host(),
        broker.port(),
        broker.rack()
    );
}
~~~

Thông tin trả về giúp xác định cluster ID để phân biệt cluster trong môi trường dev, staging và production; broker ID, host, port và rack của các broker mà API trả về; controller hiện tại theo metadata của cluster.

Controller có thể thay đổi sau failover. Ứng dụng quản trị không nên lưu controller ID như một giá trị cố định; hãy truy vấn lại khi cần.

Trong KRaft, cần phân biệt broker role và controller role. Cluster có thể dùng combined node (một node vừa broker vừa controller) hoặc dedicated controller. Thông tin describeCluster() phục vụ mô tả cluster/broker ở góc nhìn Admin API; để kiểm tra trạng thái quorum metadata KRaft như leader, voter, observer và high watermark, dùng API/CLI metadata quorum tương ứng nếu phiên bản Kafka hỗ trợ. Metadata quorum không phải replica assignment của topic.

## 5. Mô tả topic và partition

describeTopics() cho biết topic có những partition nào và replica của mỗi partition được phân bố ra sao.

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.common.Node;
import org.apache.kafka.common.TopicPartitionInfo;

Map<String, TopicDescription> descriptions =
    admin.describeTopics(List.of("orders.events"))
        .allTopicNames()
        .get(15, TimeUnit.SECONDS);

TopicDescription topic = descriptions.get("orders.events");

System.out.println(
    "Topic: " + topic.name()
        + ", internal=" + topic.isInternal()
);

for (TopicPartitionInfo partition : topic.partitions()) {
    String leaderId = partition.leader() == null
        ? "none"
        : Integer.toString(partition.leader().id());
    List<Integer> replicaIds = partition.replicas().stream()
        .map(Node::id)
        .collect(Collectors.toList());
    List<Integer> isrIds = partition.isr().stream()
        .map(Node::id)
        .collect(Collectors.toList());
    List<Integer> offlineIds = partition.offlineReplicas().stream()
        .map(Node::id)
        .collect(Collectors.toList());

    System.out.printf(
        "Partition=%d leader=%s replicas=%s isr=%s offline=%s%n",
        partition.partition(),
        leaderId,
        replicaIds,
        isrIds,
        offlineIds
    );
}
~~~

Đoạn code giả định biến admin đã được tạo ở phần kết nối và nằm trong cùng khối try. Nó dùng allTopicNames() trong Kafka client hiện đại. Với client Kafka cũ, kiểm tra API DescribeTopicsResult tương ứng; một số phiên bản dùng phương thức all() đã cũ hơn. Các ví dụ dùng List.of() yêu cầu Java 9 trở lên.

TopicPartitionInfo cung cấp các trường quan trọng:

| Trường | Ý nghĩa |
|---|---|
| partition() | Số thứ tự partition |
| leader() | Broker đang là leader; có thể null khi chưa có leader khả dụng |
| replicas() | Danh sách broker được gán replica cho partition |
| isr() | Danh sách broker có replica đang ở ISR |
| offlineReplicas() | Replica đang offline theo metadata |

Replica assignment là vị trí dự kiến của các replica. ISR là tập replica hiện đang đáp ứng điều kiện đồng bộ; ISR có thể nhỏ hơn danh sách replicas.

## 6. Đọc kết quả phân bố replica

Ví dụ một topic có ba partition và replication factor bằng 3:

| Partition | Leader | Replicas | ISR | Offline |
|---:|---:|---|---|---|
| 0 | 1 | 1, 2, 3 | 1, 2, 3 | — |
| 1 | 2 | 2, 3, 1 | 2, 3, 1 | — |
| 2 | 3 | 3, 1, 2 | 3, 1 | 2 |

Có thể đọc bảng như sau:

- Partition 0 có ba replica và cả ba đều ở ISR.
- Partition 1 có leader broker 2, ba replica đều đang đồng bộ.
- Partition 2 có leader broker 3, nhưng broker 2 đã offline và không còn trong ISR.

Với partition 2, replication factor vẫn là 3 theo assignment, nhưng ISR chỉ còn 2 replica. Nếu broker 3 gặp sự cố, Kafka chỉ có thể bầu leader từ replica đủ điều kiện theo chính sách election và trạng thái hiện tại.

### Under-replicated partition

Một partition được xem là under-replicated khi số replica trong ISR nhỏ hơn số replica được gán:

\[
ISR\_count < Assigned\_replica\_count
\]

Trong ví dụ partition 2, ISR có 2 broker trong khi assignment có 3 replica, nên partition đang under-replicated.

### Under-min-ISR

Producer dùng acks=all cần số ISR đáp ứng min.insync.replicas của topic/broker. Nếu ISR nhỏ hơn ngưỡng này, broker có thể từ chối ghi với NotEnoughReplicas hoặc NotEnoughReplicasAfterAppend tùy thời điểm lỗi.

Ví dụ:

| min.insync.replicas | ISR hiện tại | Kết quả ghi với acks=all |
|---:|---:|---|
| 2 | 3 | Có thể ghi nếu các điều kiện khác đạt |
| 2 | 2 | Có thể ghi, đang sát ngưỡng |
| 2 | 1 | Không đủ ISR để chấp nhận ghi |

min.insync.replicas không phải số replica mục tiêu; nó là ngưỡng tối thiểu cho ghi acks=all. Cần đặt replication factor lớn hơn hoặc bằng ngưỡng này và giữ đủ broker hoạt động để duy trì availability.

### Tổng hợp leader và replica theo broker

Sau khi lấy được danh sách TopicDescription, có thể đếm số partition leader và số replica được gán cho từng broker:

~~~java
import java.util.HashMap;
import java.util.Map;

Map<Integer, Integer> leadersByBroker = new HashMap<>();
Map<Integer, Integer> replicasByBroker = new HashMap<>();

for (TopicDescription description : descriptions.values()) {
    for (TopicPartitionInfo partition : description.partitions()) {
        Node leader = partition.leader();
        if (leader != null) {
            leadersByBroker.merge(leader.id(), 1, Integer::sum);
        }

        for (Node replica : partition.replicas()) {
            replicasByBroker.merge(replica.id(), 1, Integer::sum);
        }
    }
}

System.out.println("Leader count by broker: " + leadersByBroker);
System.out.println("Replica count by broker: " + replicasByBroker);
~~~

Đây là hai góc nhìn khác nhau. Leader count phản ánh số partition mà broker đang phục vụ với vai trò leader; replica count phản ánh tổng partition replica được gán lên broker đó, gồm cả leader và follower. Số lượng không phản ánh chính xác byte hoặc request rate, nên dashboard production cần kết hợp dung lượng log, bytes in/out, request latency và CPU.

## 7. Kiểm tra cấu hình broker và topic

Phân bố replica cần được đọc cùng cấu hình replication. Dùng describeConfigs() để xem các cấu hình như:

- default.replication.factor: replication factor mặc định khi tạo topic nếu không chỉ định.
- min.insync.replicas: số ISR tối thiểu cho ghi acks=all.
- unclean.leader.election.enable: có cho phép bầu replica ngoài ISR làm leader hay không.
- broker.rack: thông tin rack dùng cho rack-aware replica assignment.

Ví dụ đọc một số cấu hình broker:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.Config;
import org.apache.kafka.clients.admin.ConfigEntry;
import org.apache.kafka.common.config.ConfigResource;

// brokerId lấy từ Node.id() trong kết quả describeCluster().
ConfigResource brokerResource = new ConfigResource(
    ConfigResource.Type.BROKER,
    Integer.toString(brokerId)
);

Map<ConfigResource, Config> brokerConfigs =
    admin.describeConfigs(List.of(brokerResource))
        .all()
        .get(15, TimeUnit.SECONDS);

Config config = brokerConfigs.get(brokerResource);
for (String key : List.of(
        "broker.rack",
        "unclean.leader.election.enable"
)) {
    ConfigEntry entry = config.get(key);
    if (entry != null) {
        System.out.printf("%s=%s source=%s%n",
            key, entry.value(), entry.source());
    }
}
~~~

Để đọc cấu hình topic, tạo ConfigResource với ConfigResource.Type.TOPIC và tên topic. describeConfigs() trả về cấu hình hiệu lực cùng nguồn cấu hình theo phiên bản API; một số cấu hình có thể nhạy cảm hoặc bị ẩn giá trị.

Ví dụ đọc cấu hình topic:

~~~java
ConfigResource topicResource = new ConfigResource(
    ConfigResource.Type.TOPIC,
    "orders.events"
);

Map<ConfigResource, Config> topicConfigs =
    admin.describeConfigs(List.of(topicResource))
        .all()
        .get(15, TimeUnit.SECONDS);

Config topicConfig = topicConfigs.get(topicResource);
for (String key : List.of(
        "min.insync.replicas",
        "unclean.leader.election.enable"
)) {
    ConfigEntry entry = topicConfig.get(key);
    if (entry != null) {
        System.out.printf("%s=%s source=%s%n",
            key, entry.value(), entry.source());
    }
}
~~~

default.replication.factor chỉ ảnh hưởng topic được tạo sau đó; thay đổi giá trị này không tự thay đổi replica assignment của các topic hiện có. Muốn thay đổi replication factor của topic đã tồn tại, cần lập kế hoạch reassignment partition riêng.

Khi cấu hình broker.rack cho từng broker, Kafka có thể dùng rack-aware replica assignment để phân tán replica giữa các rack khác nhau. Hãy kiểm tra rack của broker và danh sách replicas thực tế; không suy ra khả năng chịu lỗi rack chỉ từ replication factor.

## 8. Kiểm tra replica và dung lượng log directory

Khi cần biết broker đang lưu những replica nào trên từng log directory, dùng describeLogDirs():

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.DescribeLogDirsResult;
import org.apache.kafka.clients.admin.LogDirDescription;
import org.apache.kafka.clients.admin.ReplicaInfo;
import org.apache.kafka.common.TopicPartition;

DescribeLogDirsResult result =
    admin.describeLogDirs(List.of(brokerId));

Map<Integer, Map<String, LogDirDescription>> descriptions =
    result.allDescriptions().get(20, TimeUnit.SECONDS);

Map<String, LogDirDescription> brokerDirs =
    descriptions.get(brokerId);

for (Map.Entry<String, LogDirDescription> dir : brokerDirs.entrySet()) {
    System.out.println("Log directory: " + dir.getKey());

    for (Map.Entry<TopicPartition, ReplicaInfo> replica
            : dir.getValue().replicaInfos().entrySet()) {
        ReplicaInfo info = replica.getValue();
        System.out.printf(
            "%s size=%d bytes offsetLag=%d%n",
            replica.getKey(),
            info.size(),
            info.offsetLag()
        );
    }
}
~~~

API này giúp kiểm tra replica nào nằm trên directory nào, dung lượng và offset lag của replica theo thông tin broker trả về. Nó hữu ích khi điều tra disk imbalance hoặc log directory có vấn đề.

Mỗi LogDirDescription còn có trạng thái lỗi của directory. Hãy kiểm tra trường error trước khi coi replicaInfos là dữ liệu đầy đủ; directory offline hoặc lỗi I/O có thể khiến broker trả về trạng thái lỗi thay vì danh sách replica bình thường.

Kết quả describeLogDirs() là ảnh chụp trạng thái tại thời điểm truy vấn. Không coi offset lag ở đây là consumer lag; đây là độ trễ replica so với leader. Consumer lag là khoảng cách tiến độ đọc của consumer group với log end offset.

## 9. Kiểm tra KRaft metadata quorum

Trong KRaft, metadata cluster được lưu và đồng bộ bằng metadata log của controller quorum. Đây là một replication/quorum riêng, khác với replica của topic data.

Để quan sát quorum metadata, dùng công cụ:

~~~bash
bin/kafka-metadata-quorum.sh --bootstrap-server localhost:9092 describe --status
bin/kafka-metadata-quorum.sh --bootstrap-server localhost:9092 describe --replication
~~~

Lệnh status cho biết leader và trạng thái quorum; lệnh replication cung cấp thông tin tiến độ metadata log của các voter/observer theo phiên bản Kafka.

Với Kafka Java Admin API ở các phiên bản hỗ trợ, describeMetadataQuorum() cung cấp thông tin quorum như leader ID/epoch, high watermark, voter và observer. Hãy kiểm tra phiên bản client/broker và ACL trước khi sử dụng.

Không dùng ISR của topic để kết luận metadata quorum đang khỏe. Một cluster có thể có topic replicas khỏe nhưng metadata quorum KRaft gặp vấn đề, hoặc ngược lại.

## 10. Đối chiếu bằng Kafka CLI

Admin API phù hợp khi muốn tích hợp vào ứng dụng quản trị hoặc dashboard. Khi vận hành thủ công, CLI giúp xác minh nhanh kết quả.

### Xem topic, leader và replica assignment

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders.events
~~~

Kết quả thường có các cột Leader, Replicas và Isr cho từng partition.

### Xem cấu hình broker

~~~bash
bin/kafka-configs.sh --bootstrap-server localhost:9092 --entity-type brokers --entity-name 1 --describe --all
~~~

### Xem log directory của broker

~~~bash
bin/kafka-log-dirs.sh --bootstrap-server localhost:9092 --describe --broker-list 1
~~~

### Xem metadata quorum KRaft

~~~bash
bin/kafka-metadata-quorum.sh --bootstrap-server localhost:9092 describe --status
~~~

Trên Windows, dùng file .bat tương ứng trong bin/windows. Một số tùy chọn CLI thay đổi theo phiên bản; kiểm tra --help của bản Kafka đang cài.

## 11. Xử lý lỗi khi gọi Admin API

| Lỗi | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| TimeoutException | Broker bận, network chậm hoặc API timeout quá ngắn | Kiểm tra broker/network, tăng timeout hợp lý và retry có backoff |
| ClusterAuthorizationException | Principal thiếu quyền mô tả cluster | Kiểm tra ACL cluster |
| TopicAuthorizationException | Principal thiếu quyền mô tả topic | Kiểm tra ACL topic |
| UnknownTopicOrPartitionException | Topic không tồn tại hoặc metadata chưa cập nhật | Kiểm tra tên topic và trạng thái tạo topic |
| LeaderNotAvailableException | Partition chưa có leader khả dụng | Kiểm tra broker, controller và replica state |
| UnsupportedVersionException | Client gọi API broker không hỗ trợ | Đồng bộ phiên bản client/broker hoặc dùng API tương thích |
| DisconnectException | Kết nối broker bị đóng hoặc gián đoạn | Kiểm tra listener, firewall, DNS và TLS/SASL |

Admin API trả về future, nên một thao tác có thể thành công trong khi thao tác khác thất bại. Khi mô tả nhiều topic hoặc broker, cần kiểm tra kết quả từng future hoặc dùng API tổng hợp có xử lý exception rõ ràng.

Các quyền thường cần có tùy thao tác gồm DESCRIBE trên cluster để xem thông tin cluster, DESCRIBE trên topic để mô tả partition, và DESCRIBE_CONFIGS trên broker/topic để đọc cấu hình. describeLogDirs() có thể yêu cầu quyền mô tả cluster theo chính sách ACL của môi trường. Hãy cấp quyền tối thiểu cho principal quản trị.

## 12. Quy trình điều tra replica mất đồng bộ

Khi phát hiện partition under-replicated hoặc offline replica, thực hiện theo thứ tự:

1. Dùng describeCluster() xác nhận broker đang hoạt động và controller hiện tại.
2. Dùng describeTopics() xem partition nào thiếu ISR, leader hoặc có offline replica.
3. Kiểm tra describeConfigs() để biết min.insync.replicas, unclean.leader.election.enable và broker.rack.
4. Dùng describeLogDirs() kiểm tra log directory và replica trên broker nghi vấn.
5. Đối chiếu log broker, network, disk capacity và thời gian GC.
6. Với KRaft, kiểm tra metadata quorum riêng bằng Admin API/CLI tương ứng.
7. Sau khi broker hồi phục, tiếp tục theo dõi ISR và under-replicated partition cho đến khi replica bắt kịp.

Không tự động thay đổi replica assignment chỉ vì một replica tạm thời offline. Trước hết xác định nguyên nhân broker mất kết nối, disk lỗi hay replica fetch bị chậm; reassignment không xử lý được nguyên nhân gốc và có thể làm tăng tải cluster.

## 13. Tích hợp AdminClient vào ứng dụng quản trị

Một service quản trị có thể định kỳ lấy cluster snapshot để hiển thị:

- Cluster ID và controller.
- Số broker, broker ID và rack.
- Số topic và partition.
- Leader distribution theo broker.
- Tổng replica, ISR và offline replica.
- Số partition under-replicated và partition không có leader.
- Cấu hình replication quan trọng.

Khi tính leader distribution, đếm partition theo leader().id(); khi tính replica distribution, đếm mỗi broker xuất hiện trong replicas(). Không đếm isr() thay cho replica assignment vì ISR chỉ là tập con đang đồng bộ.

AdminClient phù hợp cho truy vấn snapshot và thao tác quản trị theo yêu cầu. Để giám sát liên tục ở tần suất cao, nên kết hợp broker metrics, JMX/Prometheus exporter và log; không tạo một vòng lặp Admin API quá dày gây thêm tải coordinator/broker.

## 14. Bài tập tự kiểm tra

1. describeCluster() cung cấp những thông tin gì? Vì sao controller ID có thể thay đổi?
2. Phân biệt replicas(), isr() và offlineReplicas() trong TopicPartitionInfo.
3. Một partition có 3 assigned replicas nhưng chỉ 2 ISR. Partition có trạng thái gì?
4. min.insync.replicas=2, ISR còn 1 và producer dùng acks=all. Điều gì có thể xảy ra?
5. Vì sao default.replication.factor không tự thay đổi topic đã tồn tại?
6. describeLogDirs() cho biết replica offset lag; nó khác consumer lag như thế nào?
7. Trong KRaft, metadata quorum khác topic replica ở điểm nào?

## Kết luận

AdminClient giúp mô tả cluster, broker và phân bố replica bằng API có cấu trúc. describeCluster() cho biết cluster ID, broker và controller; describeTopics() cho biết leader, replica assignment, ISR và offline replica; describeConfigs() giúp hiểu các ngưỡng replication; describeLogDirs() cho biết replica đang nằm trên log directory nào.

Khi vận hành, hãy kết hợp trạng thái broker, leader distribution, ISR, offline replica, min.insync.replicas và metadata quorum KRaft. Admin API cung cấp snapshot để điều tra và tích hợp dashboard; metrics broker và CLI bổ sung góc nhìn theo thời gian và xác minh sự cố.

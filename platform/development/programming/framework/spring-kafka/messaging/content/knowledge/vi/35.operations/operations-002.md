# Kiểm tra topic và partition

Trong vận hành Kafka, một topic có thể vẫn tồn tại nhưng luồng messaging vẫn gặp sự cố: partition không có leader, replica không theo kịp leader, ISR giảm, phân bố leader lệch hoặc consumer group không đọc được dữ liệu. Vì vậy, kiểm tra topic không dừng ở việc xác nhận tên topic có trong cluster. Cần xem cấu trúc partition, trạng thái replica, cấu hình topic, quyền truy cập và mức độ tiêu thụ của consumer group.

Với Spring Kafka, ứng dụng có thể dùng Kafka AdminClient để truy vấn metadata và cấu hình topic. Khi vận hành hằng ngày, các lệnh Kafka CLI và dashboard broker cũng rất hữu ích để đối chiếu kết quả. Bài học này hướng dẫn cách kiểm tra theo thứ tự từ sự tồn tại của topic tới sức khỏe partition, offset và consumer group, đồng thời giải thích các dấu hiệu cần xử lý.

Bài học thuộc chương **Vận hành** của module **SPRING_KAFKA_MESSAGING**, tập trung vào việc kiểm tra topic và partition để bảo đảm luồng gửi nhận sự kiện có thể hoạt động ổn định.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Kiểm tra topic có tồn tại trong Kafka cluster hay không.
- Đọc partition count, leader, replicas, ISR và offline replicas.
- Phân biệt replication factor với số partition.
- Nhận biết partition mất leader và under-replicated partition.
- Đọc cấu hình topic như retention, cleanup policy và min ISR.
- Dùng Kafka AdminClient trong Java để mô tả topic và partition.
- Dùng Kafka CLI để kiểm tra topic, config và consumer group.
- Kiểm tra consumer group, committed offset và lag.
- Hiểu ảnh hưởng của việc tăng partition tới key distribution và ordering.
- Xây dựng checklist và runbook kiểm tra topic/partition trong production.

## 1. Topic và partition trong vận hành

Topic là tên logic của một luồng record. Kafka chia topic thành các partition để lưu log và phân phối tải. Mỗi partition là một log có thứ tự riêng, với offset tăng dần theo record được ghi.

Ví dụ topic `orders.created` có ba partition:

~~~text
orders.created
├── partition 0: offset 0, 1, 2, 3, ...
├── partition 1: offset 0, 1, 2, 3, ...
└── partition 2: offset 0, 1, 2, 3, ...
~~~

Khi kiểm tra topic, cần xác định ít nhất:

- Topic có tồn tại và có đúng tên không.
- Có bao nhiêu partition.
- Mỗi partition có leader broker nào.
- Các broker nào giữ replica.
- Replica nào đang nằm trong ISR (in-sync replicas).
- Có replica nào offline hay không.
- Cấu hình retention, cleanup và min ISR có đúng yêu cầu không.
- Consumer group có được gán partition và theo kịp dữ liệu không.

Topic có thể tồn tại nhưng không sẵn sàng phục vụ nếu partition không có leader. Partition cũng có thể vẫn có leader nhưng replication đang suy giảm do ISR nhỏ hơn replication factor.

## 2. Phân biệt partition count và replication factor

Hai thông số thường bị nhầm:

| Thông số | Ý nghĩa | Tác động chính |
|---|---|---|
| Partition count | Số log partition của topic | Khả năng song song, phân phối record và giới hạn consumer trong group. |
| Replication factor | Số replica của mỗi partition | Khả năng chịu lỗi broker và độ bền dữ liệu. |

Ví dụ topic có 6 partition và replication factor 3 nghĩa là mỗi partition có một leader cùng hai replica follower, nếu cluster đủ broker và assignment được phân bố phù hợp.

Tăng partition count có thể tăng khả năng song song nhưng không tự tăng replication factor. Tăng replication factor cần quy trình reassignment replica hoặc công cụ quản trị phù hợp; chỉ chạy lệnh tăng partition không làm dữ liệu có thêm bản sao.

Số partition cũng không thể giảm trực tiếp bằng thao tác alter thông thường. Nếu cần ít partition hơn, thường phải tạo topic mới và di chuyển dữ liệu theo kế hoạch.

## 3. Leader, replica và ISR

Mỗi partition có một leader nhận request produce và phục vụ fetch theo cơ chế Kafka. Các replica follower sao chép dữ liệu từ leader. ISR là tập replica đang theo kịp leader theo tiêu chí của broker.

Ví dụ:

~~~text
Partition 0
  Leader: broker 1
  Replicas: broker 1, broker 2, broker 3
  ISR:      broker 1, broker 2, broker 3

Partition 1
  Leader: broker 2
  Replicas: broker 1, broker 2, broker 3
  ISR:      broker 2, broker 3
~~~

Partition 0 có đủ ba replica trong ISR. Partition 1 có một replica chưa nằm trong ISR; dữ liệu có thể vẫn đọc/ghi qua leader, nhưng khả năng chịu lỗi đã giảm.

Nếu leader bị mất, Kafka có thể bầu leader mới từ ISR. Nếu không còn replica phù hợp trong ISR, partition có thể trở thành unavailable, trừ khi cluster được cấu hình cho phép unclean leader election với trade-off có nguy cơ mất dữ liệu.

Không đánh đồng danh sách replicas với ISR. Replicas mô tả nơi partition được cấu hình lưu; ISR mô tả replica hiện đang đồng bộ theo trạng thái broker.

## 4. Cách kiểm tra topic bằng Kafka CLI

Lệnh cơ bản:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092 --list
~~~

Mô tả một topic:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092 --describe --topic orders.created
~~~

Kết quả thường thể hiện:

- Topic name.
- Partition count.
- Replication factor.
- Partition ID.
- Leader broker ID.
- Replica broker IDs.
- ISR broker IDs.

Ví dụ output minh họa:

~~~text
Topic: orders.created  PartitionCount: 3  ReplicationFactor: 3
Topic: orders.created  Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,2,3
Topic: orders.created  Partition: 1  Leader: 2  Replicas: 1,2,3  Isr: 2,3
Topic: orders.created  Partition: 2  Leader: 3  Replicas: 1,2,3  Isr: 1,2,3
~~~

Ở ví dụ này, partition 1 có ISR chỉ gồm broker 2 và 3, dù replication factor là 3. Cần kiểm tra broker 1, log replication và network để tìm nguyên nhân.

Trên Windows, script có thể có tên `kafka-topics.bat`. Tùy cách cài đặt, dùng file trong thư mục `bin/windows` và giữ nguyên các tham số.

## 5. Kiểm tra topic tồn tại và xử lý topic không tồn tại

Một topic không xuất hiện trong danh sách có thể do:

- Topic chưa được tạo.
- Sai tên hoặc sai cluster/bootstrap server.
- Principal không có quyền list/describe.
- Topic vừa bị xóa hoặc đang trong quá trình thay đổi metadata.
- Công cụ đang kết nối nhầm môi trường.

Không nên lập tức tạo topic khi không tìm thấy. Trước hết xác minh cluster, tên topic, ACL và quy trình provision. Nếu bật auto topic creation, một producer hoặc consumer dùng nhầm tên có thể khiến topic ngoài ý muốn được tạo với cấu hình mặc định.

Trong production, topic nên được provision bằng IaC, Kafka AdminClient hoặc quy trình quản trị đã kiểm soát partition count, replication factor, retention và ACL. Tự động tạo topic từ request runtime cần có giới hạn và validation.

## 6. Kiểm tra topic configuration

Dùng `kafka-configs` để xem cấu hình topic:

~~~bash
kafka-configs.sh --bootstrap-server kafka-1:9092 --entity-type topics --entity-name orders.created --describe
~~~

Một số cấu hình quan trọng:

| Config | Ý nghĩa vận hành |
|---|---|
| `retention.ms` | Thời gian giữ log theo tuổi record, với cleanup policy delete. |
| `retention.bytes` | Giới hạn dung lượng log theo cấu hình topic/partition. |
| `cleanup.policy` | `delete`, `compact` hoặc kết hợp tùy phiên bản/cấu hình. |
| `min.insync.replicas` | Số replica tối thiểu phải đồng bộ để producer dùng `acks=all` được chấp nhận. |
| `segment.bytes` | Kích thước segment log trước khi roll theo điều kiện cấu hình. |
| `max.message.bytes` | Giới hạn kích thước record batch được chấp nhận ở topic, cần đối chiếu giới hạn broker/producer. |

Cấu hình hiệu lực có thể đến từ topic override hoặc broker default. Khi kiểm tra, cần xem cả nguồn config và giá trị thực tế. Không phải mọi config đều được hiển thị giống nhau trên mọi phiên bản Kafka.

Với topic compacted, retention và cleanup semantics khác topic delete thông thường. Không áp dụng máy móc giả định record cũ sẽ bị xóa theo retention.ms khi cleanup policy là compact.

## 7. Hiểu under-replicated và offline partition

Hai dấu hiệu cần chú ý:

- **Under-replicated partition**: số replica trong ISR nhỏ hơn số replica được cấu hình.
- **Offline partition**: partition hiện không có leader khả dụng để phục vụ request.

Ví dụ replication factor là 3 nhưng ISR chỉ còn 2 replica thì partition đang under-replicated. Điều này làm giảm khả năng chịu lỗi; nếu replica còn lại gặp sự cố, partition có thể mất khả năng phục vụ.

Nếu partition không có leader, producer/consumer có thể gặp lỗi như leader unavailable hoặc request timeout. Cần kiểm tra broker log, trạng thái broker, disk, network, controller/quorum và replica synchronization.

Không tự tăng ISR hoặc ép replica vào ISR bằng cách sửa metadata. Broker tự quản lý ISR theo trạng thái đồng bộ; cần khôi phục nguyên nhân khiến follower tụt lại.

## 8. Kiểm tra phân bố leader giữa các broker

Nếu nhiều partition có leader tập trung trên một broker, broker đó có thể chịu tải produce/fetch lớn hơn các broker khác.

Hãy xem leader distribution:

| Broker | Số partition leader | Nhận xét |
|---|---:|---|
| broker 1 | 18 | Có thể đang nhận tải leader lớn. |
| broker 2 | 17 | Tương đối cân bằng. |
| broker 3 | 5 | Có thể chưa cân bằng leader. |

Bảng chỉ minh họa cách đọc, không phải ngưỡng cố định. Cần đối chiếu bytes in/out, request rate, disk throughput, CPU và network. Số leader bằng nhau không bảo đảm tải bằng nhau nếu partition có lưu lượng khác nhau.

Preferred replica election hoặc reassignment có thể giúp cân bằng leader/replica, nhưng phải thực hiện theo quy trình quản trị và kiểm tra ảnh hưởng. Không chạy thao tác reassignment trên production chỉ dựa vào số lượng leader.

## 9. Kiểm tra partition bằng Kafka AdminClient

Ứng dụng Java có thể dùng AdminClient để lấy metadata topic. Ví dụ tạo AdminClient bằng cấu hình bootstrap server:

~~~java
Properties properties = new Properties();
properties.put(
        AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
        "kafka-1:9092,kafka-2:9092"
);

try (AdminClient admin = AdminClient.create(properties)) {
    // Thực hiện các truy vấn metadata tại đây.
}
~~~

Trong ứng dụng Spring Boot, nên dùng cấu hình bảo mật và bootstrap server đã được quản lý. Không tạo AdminClient mới cho mỗi request HTTP; hãy quản lý lifecycle như một bean hoặc service dùng chung và đóng client khi application shutdown.

Nếu cluster dùng SASL/TLS, AdminClient cũng phải nhận các thuộc tính security tương ứng và principal cần có quyền describe/list. Không dùng credential quản trị rộng cho mọi endpoint chỉ đọc metadata.

## 10. Liệt kê topic và mô tả partition bằng AdminClient

Ví dụ kiểm tra topic tồn tại và lấy mô tả partition:

~~~java
public TopicDescription describeTopic(
        AdminClient admin,
        String topicName) throws Exception {

    Set<String> topicNames = admin.listTopics()
            .names()
            .get(10, TimeUnit.SECONDS);

    if (!topicNames.contains(topicName)) {
        throw new IllegalArgumentException(
                "Topic does not exist: " + topicName
        );
    }

    return admin.describeTopics(List.of(topicName))
            .values()
            .get(topicName)
            .get(10, TimeUnit.SECONDS);
}
~~~

Đọc thông tin partition:

~~~java
TopicDescription description =
        describeTopic(admin, "orders.created");

for (TopicPartitionInfo partition : description.partitions()) {
    Node leader = partition.leader();

    String leaderId = leader == null
            ? "NO_LEADER"
            : Integer.toString(leader.id());

    List<Integer> replicaIds = partition.replicas().stream()
            .map(Node::id)
            .toList();

    List<Integer> isrIds = partition.isr().stream()
            .map(Node::id)
            .toList();

    List<Integer> offlineIds = partition.offlineReplicas().stream()
            .map(Node::id)
            .toList();

    log.info(
            "topic={}, partition={}, leader={}, replicas={}, isr={}, offline={}",
            description.name(),
            partition.partition(),
            leaderId,
            replicaIds,
            isrIds,
            offlineIds
    );
}
~~~

Ví dụ dùng `List.toList()` yêu cầu Java 16 trở lên. Nếu dự án dùng Java thấp hơn, thay bằng `collect(Collectors.toList())`.

Khi kiểm tra production, không chỉ log thông tin. Có thể tính các chỉ số:

- Partition không có leader.
- Partition có ISR nhỏ hơn replica count.
- Partition có offline replicas.
- Số leader theo từng broker.
- Topic có partition count khác cấu hình mong đợi.

Nếu AdminClient request timeout hoặc bị authorization error, cần phân biệt lỗi truy vấn với topic thực sự không tồn tại.

## 11. Đọc topic config bằng AdminClient

Có thể dùng `describeConfigs` để đọc cấu hình topic:

~~~java
ConfigResource resource = new ConfigResource(
        ConfigResource.Type.TOPIC,
        "orders.created"
);

Map<ConfigResource, Config> configs = admin
        .describeConfigs(List.of(resource))
        .all()
        .get(10, TimeUnit.SECONDS);

Config config = configs.get(resource);

for (ConfigEntry entry : config.entries()) {
    if (!entry.isSensitive()) {
        log.info(
                "config={}, value={}, source={}, default={}",
                entry.name(),
                entry.value(),
                entry.source(),
                entry.isDefault()
        );
    }
}
~~~

Không log giá trị config nhạy cảm. Một số config có thể bị ẩn hoặc trả null tùy broker và quyền truy cập.

Quyền đọc config có thể khác quyền describe metadata. Nếu metadata đọc được nhưng describeConfigs bị từ chối, kiểm tra ACL operation tương ứng thay vì kết luận topic hỏng.

## 12. Kiểm tra consumer group và partition assignment

Topic khỏe không đồng nghĩa consumer đang đọc tốt. Cần kiểm tra consumer group:

~~~bash
kafka-consumer-groups.sh --bootstrap-server kafka-1:9092 --describe --group orders-fulfillment
~~~

Kết quả thường có:

- Topic và partition.
- Current offset đã commit.
- Log end offset.
- Lag.
- Consumer ID, host và client ID nếu member đang hoạt động.

Ví dụ:

~~~text
GROUP                TOPIC           PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
orders-fulfillment   orders.created  0          1200            1200            0
orders-fulfillment   orders.created  1          980             1100            120
orders-fulfillment   orders.created  2          1500            1500            0
~~~

Partition 1 đang có lag 120 record. Cần kiểm tra consumer được assign partition đó, tốc độ xử lý, lỗi listener, retry và dependency downstream.

Nếu group không xuất hiện hoặc không có committed offset, kiểm tra group ID, trạng thái consumer và chính sách `auto.offset.reset`. Reset policy chỉ áp dụng khi group chưa có offset hợp lệ; thay đổi nó không tự tua một group đã commit offset.

## 13. Partition count giới hạn consumer song song như thế nào?

Trong consumer group thông thường, mỗi partition được gán cho tối đa một consumer member tại một thời điểm. Nếu topic có 4 partition và group có 8 consumer, tối đa 4 consumer có partition của topic đó; số consumer còn lại có thể idle.

Điều này có nghĩa:

- Tăng concurrency vượt partition count không tự tăng khả năng xử lý của topic.
- Tăng partition có thể mở rộng số consumer được gán partition.
- Nhiều partition hơn cũng tăng metadata, file segment, overhead replication và chi phí vận hành.
- Một partition nóng vẫn có thể là bottleneck dù các partition khác nhàn rỗi.

Chọn partition count dựa trên throughput, số consumer dự kiến, ordering, kích thước log, replication và khả năng broker. Không tăng partition chỉ vì muốn con số concurrency lớn hơn.

## 14. Tăng partition có thể ảnh hưởng ordering theo key

Với partitioner mặc định, record có key thường được ánh xạ tới partition dựa trên hash key và số partition hiện tại. Khi tăng partition count, key có thể được ánh xạ sang partition khác đối với các record mới.

Ví dụ trước khi tăng partition:

~~~text
order-1001 -> partition 1
~~~

Sau khi tăng partition:

~~~text
order-1001 -> partition 4
~~~

Các record cũ vẫn nằm ở partition 1; record mới có thể nằm ở partition 4. Kafka không di chuyển record cũ và không tạo một thứ tự toàn cục giữa hai partition. Vì vậy, tăng partition có thể phá giả định rằng mọi event của cùng key luôn đi vào một partition trong suốt vòng đời topic.

Trước khi tăng partition, xác định ordering requirement. Nếu cần giữ thứ tự theo aggregate, cân nhắc custom partitioner ổn định, topic migration có kiểm soát hoặc version/sequence trong event để consumer phát hiện thứ tự.

## 15. Tăng partition bằng Kafka CLI

Có thể tăng partition count bằng:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092 --alter --topic orders.created --partitions 6
~~~

Thao tác này tăng partition count lên 6 nếu topic hiện có ít hơn 6. Không thể dùng lệnh alter thông thường để giảm partition count.

Trước khi chạy:

1. Xác nhận topic đúng cluster và đúng môi trường.
2. Kiểm tra partition count hiện tại.
3. Đánh giá ordering theo key và consumer group.
4. Kiểm tra broker capacity, replica placement và quota.
5. Xác định số partition mục tiêu và lý do thay đổi.
6. Lập kế hoạch theo dõi consumer rebalance và lag sau thay đổi.

Sau khi alter, chạy describe lại để xác minh partition count và kiểm tra replica/leader assignment. Tạo thêm partition không có nghĩa replication đã cân bằng hoặc các partition mới đã có phân bố tối ưu.

## 16. Kiểm tra replication factor và ISR sau sự cố

Khi replication suy giảm, kiểm tra:

- Broker nào đang offline hoặc vừa restart.
- Disk có đầy, chậm hoặc lỗi I/O không.
- Network giữa broker có packet loss hoặc latency cao không.
- Follower fetch có bị chậm không.
- Log directory có lỗi không.
- Broker có đang xử lý reassignment hoặc recovery không.
- ISR có phục hồi sau khi follower bắt kịp không.

Nếu producer dùng `acks=all`, yêu cầu acknowledgement liên quan tới ISR và `min.insync.replicas`. Ví dụ replication factor 3, min ISR 2: producer có thể tiếp tục ghi với ISR 2 khi cấu hình và trạng thái phù hợp; nếu ISR giảm dưới 2, produce có thể bị từ chối. Cần đọc chính xác topic/broker config và producer setting.

Không giảm min.insync.replicas hoặc bật unclean leader election chỉ để xóa lỗi tạm thời. Những thay đổi này ảnh hưởng trực tiếp trade-off giữa availability và durability, có thể làm tăng nguy cơ mất dữ liệu.

## 17. Kiểm tra ACL và quyền mô tả topic

Một công cụ vận hành có thể không nhìn thấy topic vì thiếu quyền, chứ không phải topic không tồn tại.

Các thao tác thường cần quyền phù hợp:

- List topics hoặc metadata cluster.
- Describe topic.
- Describe topic configs.
- Read consumer group offsets.
- Describe consumer group.
- Alter topic hoặc configs nếu có nhiệm vụ quản trị.

Dùng principal read-only cho dashboard/health check nếu chỉ cần quan sát. Tách principal có quyền alter/create/delete khỏi service producer/consumer thông thường.

Với Kafka CLI dùng SASL/TLS, truyền file cấu hình client qua `--command-config`:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9093 --command-config client.properties --describe --topic orders.created
~~~

File cấu hình cần được bảo vệ như secret; không đưa password vào lệnh shell lưu trong history hoặc log CI.

## 18. Các metric và cảnh báo nên theo dõi

Topic/partition cần được giám sát liên tục, không chỉ kiểm tra thủ công khi có sự cố.

| Metric hoặc tín hiệu | Ý nghĩa | Hành động khi bất thường |
|---|---|---|
| Offline partitions | Partition không có leader | Kiểm tra broker, controller/quorum, disk và network. |
| Under-replicated partitions | ISR nhỏ hơn replica count | Kiểm tra follower lag và broker health. |
| ISR shrink/expand rate | Replica liên tục rời/vào ISR | Tìm network/disk/CPU instability. |
| Leader count per broker | Phân bố leader | Đánh giá mất cân bằng tải. |
| Request error/timeout | Client không hoàn thành API request | Đối chiếu broker, network, ACL và client logs. |
| Consumer lag per partition | Consumer tụt lại | Kiểm tra processing rate, key skew và assignment. |
| Disk usage/log dir health | Khả năng lưu trữ broker | Dọn capacity theo retention và mở rộng storage có kế hoạch. |
| Produce/fetch bytes rate | Tải thực tế trên topic/broker | Đối chiếu capacity và traffic pattern. |

Alert nên dựa trên ngưỡng và thời gian kéo dài. Một lần ISR shrink ngắn trong quá trình bảo trì có thể khác với tình trạng under-replicated kéo dài. Cần gắn cảnh báo với runbook và owner cụ thể.

## 19. Runbook kiểm tra topic và partition

Khi có phản ánh producer timeout hoặc consumer lag tăng, có thể đi theo trình tự:

1. Xác nhận bootstrap server và cluster đúng môi trường.
2. Kiểm tra topic có tồn tại và tên có chính xác.
3. Chạy describe topic để xem partition count, leader, replicas và ISR.
4. Xác định partition không có leader hoặc under-replicated.
5. Kiểm tra broker liên quan, disk, network và log.
6. Đọc topic config: retention, cleanup policy, min ISR và message size.
7. Kiểm tra consumer group assignment, current offset, log end offset và lag.
8. Đối chiếu listener errors, retry, DLT và downstream dependency.
9. Kiểm tra ACL nếu metadata hoặc operation bị từ chối.
10. Chỉ thay đổi partition/config sau khi đánh giá ordering, durability và capacity.
11. Xác minh lại metadata và consumer behavior sau thay đổi.
12. Ghi nhận nguyên nhân, thời điểm, thao tác và kết quả phục hồi.

Không xóa hoặc tạo lại topic để “reset” một sự cố nếu chưa có kế hoạch dữ liệu. Việc xóa topic có thể làm mất dữ liệu, thay đổi identity/offset và ảnh hưởng mọi consumer.

## 20. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra topic tồn tại | Bỏ sót partition không leader hoặc ISR suy giảm | Kiểm tra từng partition và replica state. |
| Nhầm partition count với replication factor | Tăng sai thông số để xử lý bottleneck | Xác định đang cần song song hay durability. |
| Nhìn replicas rồi kết luận mọi replica khỏe | Bỏ qua follower ngoài ISR | So sánh replicas với ISR và offline replicas. |
| Thấy topic không list được rồi tạo lại | Có thể tạo nhầm topic hoặc che lỗi ACL/cluster | Xác minh bootstrap, quyền và tên trước. |
| Tăng partition mà không xét key ordering | Event cùng key có thể chuyển partition | Đánh giá ordering và migration strategy. |
| Giảm min ISR để producer ghi tiếp | Giảm mức durability | Chỉ thay đổi sau đánh giá rủi ro và phê duyệt. |
| Cấp quyền admin cho health check | Mở rộng quyền không cần thiết | Dùng principal read-only. |
| Chỉ nhìn tổng consumer lag | Bỏ sót một partition nóng | Theo dõi lag theo partition. |
| Tạo topic tự động với config mặc định | Partition/retention/replication không phù hợp | Provision topic có kiểm soát. |

## 21. Bài tập tổng hợp: kiểm tra topic orders.created

Giả sử cluster có ba broker và topic `orders.created`. Hãy xây dựng một công cụ kiểm tra topic cho đội vận hành.

Yêu cầu:

1. Kết nối AdminClient tới cluster bằng principal chỉ có quyền describe.
2. Kiểm tra topic tồn tại.
3. Đọc partition count và replication factor.
4. In leader, replicas, ISR và offline replicas của từng partition.
5. Đếm partition không có leader.
6. Đếm under-replicated partition.
7. Đếm offline replica và phân bố leader theo broker.
8. Đọc retention.ms, cleanup.policy và min.insync.replicas.
9. Kiểm tra consumer group `orders-fulfillment` và lag theo partition.
10. Đối chiếu producer acks với min ISR.
11. Thử trường hợp thiếu quyền describe và phân biệt authorization failure với topic không tồn tại.
12. Tạo test topic, tăng partition count rồi kiểm tra metadata sau thay đổi.
13. Ghi lại ảnh hưởng của partition expansion tới key distribution.
14. Xuất kết quả health check thành báo cáo có trạng thái HEALTHY, DEGRADED hoặc UNAVAILABLE.
15. Xây dựng runbook cho offline partition và under-replicated partition.

Bài tập hoàn thành khi công cụ có thể chỉ ra topic nào không tồn tại, partition nào không có leader, replica nào chưa đồng bộ, consumer group nào đang lag và cấu hình nào lệch khỏi baseline.

## 22. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Topic model | Topic và partition | Giải thích được log/offset theo partition. |
| 2. Replica model | Leader, replicas, ISR | Phân biệt replica được cấu hình và replica đồng bộ. |
| 3. CLI | kafka-topics và kafka-configs | Mô tả được topic và đọc config. |
| 4. AdminClient | listTopics, describeTopics, describeConfigs | Truy vấn metadata bằng Java. |
| 5. Health | Offline và under-replicated partitions | Phát hiện partition suy giảm. |
| 6. Consumer group | Assignment, committed offset và lag | Tìm được partition consumer đang tụt lại. |
| 7. Partition planning | Count, concurrency và key distribution | Đánh giá được tác động khi tăng partition. |
| 8. Durability | Replication factor, acks và min ISR | Hiểu trade-off khi ISR giảm. |
| 9. Security | ACL và command config | Dùng quyền tối thiểu để kiểm tra. |
| 10. Operations | Metrics và runbook | Chẩn đoán và xác minh sau thay đổi. |

Bài học hoàn thành khi bạn có thể kiểm tra topic từ CLI và AdminClient, giải thích trạng thái từng partition, xác định under-replication/offline leader, kiểm tra consumer lag và đánh giá an toàn trước khi thay đổi partition count.

Kiểm tra topic và partition là bước nền tảng để vận hành Kafka. Hãy nhìn đồng thời leader, replicas, ISR, config và consumer group; một topic có tên hợp lệ chưa chắc đang khỏe. Mọi thay đổi partition hoặc durability cần được đánh giá theo ordering, tải và khả năng chịu lỗi trước khi áp dụng.


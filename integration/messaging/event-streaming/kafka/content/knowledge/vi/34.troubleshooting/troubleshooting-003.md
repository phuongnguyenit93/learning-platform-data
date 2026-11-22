# Topic không tồn tại, metadata cũ và leader chưa sẵn sàng

Khi producer không gửi được record hoặc consumer không đọc được dữ liệu, một nhóm nguyên nhân thường gặp là topic chưa tồn tại, client đang dùng metadata cũ hoặc partition chưa có leader sẵn sàng. Ba tình huống này có biểu hiện gần giống nhau nhưng cách xử lý khác nhau. Tạo lại topic hoặc restart broker ngay khi thấy lỗi có thể che mất nguyên nhân thật, thậm chí làm tình hình xấu hơn.

Quy trình chẩn đoán nên đi theo thứ tự: **xác nhận đúng cluster và tên topic → xác nhận topic/partition tồn tại → kiểm tra leader và replica state → kiểm tra metadata/địa chỉ broker mà client đang dùng → kiểm tra quyền truy cập và cấu hình retry**.

## 1. Phân biệt ba nhóm sự cố

| Nhóm sự cố | Dấu hiệu thường gặp | Câu hỏi đầu tiên |
|---|---|---|
| Topic/partition không tồn tại | `UNKNOWN_TOPIC_OR_PARTITION`, `UnknownTopicOrPartitionException`, topic không xuất hiện trong danh sách | Topic có được tạo trên đúng cluster và đúng tên không? |
| Metadata cũ hoặc không nhất quán | `NOT_LEADER_OR_FOLLOWER`, client tiếp tục gửi đến broker cũ, lỗi xuất hiện sau reassignment/restart | Client đã nhận metadata mới và kết nối được broker được quảng bá chưa? |
| Leader chưa sẵn sàng | `LEADER_NOT_AVAILABLE`, partition unavailable, leader là `-1`/không có | Controller có thể bầu leader từ replica hợp lệ không? |

Một số lỗi có thể xuất hiện trong giai đoạn chuyển tiếp. Ví dụ, ngay sau khi tạo topic, metadata chưa lan đến mọi broker hoặc leader election chưa hoàn tất; `UNKNOWN_TOPIC_OR_PARTITION` hay `LEADER_NOT_AVAILABLE` có thể chỉ là tạm thời. Nếu lỗi kéo dài, phải xác minh trạng thái cluster thay vì tăng retry vô hạn.

## 2. Hiểu các error code quan trọng

| Kafka error | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `UNKNOWN_TOPIC_OR_PARTITION` | Broker không nhận diện topic/partition trong request | Kiểm tra tên, cluster, topic creation, deletion/recreation và metadata |
| `LEADER_NOT_AVAILABLE` | Partition hiện chưa có leader có thể phục vụ request | Kiểm tra leader election, controller, replica và broker availability |
| `NOT_LEADER_OR_FOLLOWER` | Broker nhận request không còn là leader/follower hợp lệ cho partition đó | Client cần metadata mới; kiểm tra leader movement và advertised listener |
| `BROKER_NOT_AVAILABLE` | Broker được tham chiếu không sẵn sàng | Kiểm tra process, network, listener và broker registration |
| `TOPIC_AUTHORIZATION_FAILED` | Principal không có quyền thao tác topic | Kiểm tra ACL/principal; không xử lý như topic missing |
| `INVALID_TOPIC_EXCEPTION` | Tên topic hoặc request topic không hợp lệ | Kiểm tra ký tự, độ dài và quy ước đặt tên |
| `NOT_ENOUGH_REPLICAS` | ISR thấp hơn ngưỡng `min.insync.replicas` với write yêu cầu durability tương ứng | Khôi phục replica/ISR; không nhầm với thiếu leader |
| `NOT_ENOUGH_REPLICAS_AFTER_APPEND` | Replica không đáp ứng điều kiện sau khi append | Kiểm tra ISR, replication và durability policy |
| `REQUEST_TIMED_OUT` / network timeout | Request không hoàn tất trong thời gian chờ | Kiểm tra broker load, network, request latency và timeout |

`TOPIC_AUTHORIZATION_FAILED` khác `UNKNOWN_TOPIC_OR_PARTITION`. Nếu principal thiếu quyền, cần sửa ACL hoặc identity. Đừng tạo một topic khác cùng tên chỉ để né lỗi authorization.

`NOT_ENOUGH_REPLICAS` cũng khác `LEADER_NOT_AVAILABLE`: partition có thể vẫn có leader nhưng số replica trong ISR không đủ để chấp nhận write `acks=all` theo `min.insync.replicas`.

## 3. Xác nhận client đang kết nối đúng cluster

Một lỗi rất dễ bỏ qua là producer, consumer hoặc CLI đang dùng nhầm `bootstrap.servers`. Hai cluster có thể cùng có topic `orders` nhưng dữ liệu, partition count và ACL hoàn toàn khác nhau.

Kiểm tra:

- Giá trị `bootstrap.servers` mà ứng dụng thực sự nạp sau khi resolve environment/profile/secret.
- Cấu hình TLS/SASL và principal đang dùng.
- DNS/IP của bootstrap broker và `advertised.listeners` mà broker trả về trong metadata.
- Cluster ID để phân biệt môi trường nếu có quyền truy vấn.
- Topic được tạo trên đúng môi trường: local, dev, staging, production hay DR.

Ví dụ kiểm tra cluster ID:

```bash
bin/kafka-cluster.sh cluster-id \
  --bootstrap-server broker-1.internal:9092
```

Nếu lệnh CLI dùng endpoint khác với ứng dụng, kết quả CLI không chứng minh ứng dụng đang nhìn thấy cùng cluster. Đối chiếu cấu hình runtime của process, không chỉ file properties trên disk.

## 4. Xác minh topic có thực sự tồn tại

Liệt kê topic trên đúng cluster:

```bash
bin/kafka-topics.sh \
  --bootstrap-server broker-1.internal:9092 \
  --list
```

Describe topic cụ thể:

```bash
bin/kafka-topics.sh \
  --bootstrap-server broker-1.internal:9092 \
  --describe \
  --topic orders
```

Kiểm tra unavailable partitions và under-replicated partitions:

```bash
bin/kafka-topics.sh \
  --bootstrap-server broker-1.internal:9092 \
  --describe --unavailable-partitions

bin/kafka-topics.sh \
  --bootstrap-server broker-1.internal:9092 \
  --describe --under-replicated-partitions
```

Nếu topic không có trong `--list`:

1. Kiểm tra chính tả, dấu chấm/gạch ngang, chữ hoa/thường và suffix môi trường.
2. Kiểm tra lệnh có trỏ đúng cluster không.
3. Kiểm tra topic đã được tạo thành công chưa và có bị xóa gần đây không.
4. Kiểm tra principal có quyền `DESCRIBE`/`CREATE` cần thiết không.
5. Kiểm tra auto topic creation có được bật hay không; không dựa vào nó như cơ chế provision production.

Lưu ý: khả năng liệt kê/describe topic phụ thuộc ACL và cấu hình authorizer. Khi kết quả CLI không rõ ràng, dùng principal vận hành có quyền phù hợp để xác minh và xem log authorization. Không kết luận topic chắc chắn không tồn tại chỉ từ một truy vấn bị từ chối.

## 5. Tạo topic tường minh thay vì trông chờ auto-create

Trong production, nên quản lý topic qua provisioning hoặc AdminClient với partition count, replication factor và config đã được duyệt. Auto topic creation có thể tạo topic sai partition/RF/config do broker defaults; tên gõ sai cũng có thể vô tình tạo một topic rác.

Ví dụ tạo topic bằng CLI:

```bash
bin/kafka-topics.sh \
  --bootstrap-server broker-1.internal:9092 \
  --create \
  --topic orders \
  --partitions 12 \
  --replication-factor 3 \
  --config min.insync.replicas=2 \
  --config cleanup.policy=delete
```

Chỉ chạy lệnh create sau khi xác nhận topic chưa tồn tại và cấu hình trên phù hợp với policy môi trường. Nếu broker có ít hơn ba broker khả dụng, replication factor 3 không thể được đáp ứng.

Trong ứng dụng Java, có thể tạo topic qua AdminClient:

```java
Properties adminProps = new Properties();
adminProps.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);

try (AdminClient admin = AdminClient.create(adminProps)) {
    NewTopic topic = new NewTopic("orders", 12, (short) 3)
            .configs(Map.of(
                    "min.insync.replicas", "2",
                    "cleanup.policy", "delete"));

    admin.createTopics(List.of(topic))
            .all()
            .get(30, TimeUnit.SECONDS);
}
```

Nếu topic đã tồn tại, `createTopics` có thể trả `TopicExistsException`. Đây là trạng thái cần xử lý có chủ đích: describe và xác nhận partition/config hiện tại có đúng không. Không bắt mọi exception rồi bỏ qua.

Với consumer, `allow.auto.create.topics` và broker `auto.create.topics.enable` có thể ảnh hưởng việc topic chưa tồn tại có được tự tạo khi metadata request hay không. Hãy kiểm soát rõ trong môi trường production; topic provisioning nên là trách nhiệm có chủ sở hữu.

## 6. Phân biệt topic missing với topic vừa tạo nhưng chưa sẵn sàng

Sau khi `CreateTopics` trả thành công, các thao tác metadata, assignment và leader election vẫn có thể cần thời gian hoàn tất. Producer/consumer khởi động ngay lập tức có thể gặp lỗi tạm thời.

Một topic được xem là sẵn sàng cho workload khi:

- Topic xuất hiện trong metadata trên đúng cluster.
- Số partition đúng như dự kiến.
- Mỗi partition có leader hợp lệ.
- Replica assignment và ISR đáp ứng yêu cầu của workload.
- Client kết nối được các broker được quảng bá trong metadata.

Không chỉ kiểm tra topic tồn tại. Một topic có thể tồn tại nhưng một hoặc nhiều partition chưa có leader; producer chỉ ghi được vào partition có leader sẵn sàng.

### Chờ leader bằng AdminClient

Ví dụ helper polling có deadline. Nó chỉ coi lỗi `UNKNOWN_TOPIC_OR_PARTITION` là tạm thời trong cửa sổ chờ; các lỗi authorization hoặc cấu hình khác phải được ném ra để điều tra.

```java
static TopicDescription awaitTopicLeaders(
        Admin admin,
        String topicName,
        int expectedPartitions,
        Duration timeout) throws Exception {

    long deadline = System.nanoTime() + timeout.toNanos();

    while (System.nanoTime() < deadline) {
        try {
            TopicDescription description = admin
                    .describeTopics(List.of(topicName))
                    .allTopicNames()
                    .get(5, TimeUnit.SECONDS)
                    .get(topicName);

            if (description != null
                    && description.partitions().size() == expectedPartitions
                    && description.partitions().stream().allMatch(partition ->
                            partition.leader() != null && !partition.leader().isEmpty())) {
                return description;
            }
        } catch (ExecutionException exception) {
            if (!(exception.getCause() instanceof UnknownTopicOrPartitionException)) {
                throw exception;
            }
        }

        Thread.sleep(200);
    }

    throw new TimeoutException("Topic leaders not ready before deadline: " + topicName);
}
```

Đây là ví dụ Java minh họa; cần import các class Kafka và Java tương ứng. Trong môi trường có request timeout ngắn, điều chỉnh thời gian chờ của từng `get()` để không vượt deadline tổng quá nhiều. Nếu topic không xuất hiện trước deadline, kiểm tra lại provision và cluster thay vì tăng timeout liên tục.

## 7. Chẩn đoán `LEADER_NOT_AVAILABLE`

`LEADER_NOT_AVAILABLE` cho biết partition chưa có leader có thể nhận request. Nó thường xuất hiện trong các tình huống:

- Topic/partition vừa được tạo và leader election chưa hoàn tất.
- Broker đang restart hoặc vừa rời cluster.
- Controller đang bầu leader hoặc cập nhật metadata.
- Không còn replica hợp lệ trong ISR để bầu leader theo policy hiện tại.
- Partition offline do disk/log directory lỗi hoặc replica không thể khởi động.
- KRaft controller quorum mất majority hoặc metadata propagation bị gián đoạn.

Kiểm tra partition cụ thể:

```bash
bin/kafka-topics.sh \
  --bootstrap-server broker-1.internal:9092 \
  --describe --topic orders
```

Output có các trường `Leader`, `Replicas`, `Isr`. Nếu `Leader: -1`, partition chưa có leader. So sánh replicas và ISR:

- Replica có trong ISR và broker đang online: điều tra controller election/metadata update.
- Replica được assign nhưng không nằm trong ISR: điều tra replica fetch, disk, network và broker log.
- Không có replica khả dụng: partition có thể offline; cần khôi phục broker/replica hoặc làm theo recovery procedure đã phê duyệt.

Một partition under-replicated vẫn có thể có leader và phục vụ read/write. `UnderReplicatedPartitions > 0` không đồng nghĩa `Leader: -1`. Ngược lại, partition offline là vấn đề availability nghiêm trọng hơn.

## 8. Kiểm tra controller và metadata quorum

### Cluster KRaft

Với KRaft, kiểm tra controller quorum:

```bash
bin/kafka-metadata-quorum.sh \
  --bootstrap-server broker-1.internal:9092 \
  describe --status

bin/kafka-metadata-quorum.sh \
  --bootstrap-server broker-1.internal:9092 \
  describe --replication
```

Xem xét:

- Có controller leader hợp lệ không?
- Voter hiện tại có đủ majority không?
- High watermark có tiến triển không?
- Follower metadata log có lag lớn không?
- Controller log có lỗi election, storage hoặc network không?

Nếu quorum mất majority, metadata operation và leader coordination có thể bị ảnh hưởng. Khôi phục controller voter/quorum trước khi cố gắng tạo topic hoặc ép leader election.

### Cluster ZooKeeper mode

Với Kafka cũ còn dùng ZooKeeper, kiểm tra broker controller đang active, kết nối ZooKeeper ensemble và log election/controller. Dùng quy trình phù hợp với phiên bản; không chạy `kafka-metadata-quorum.sh` trên cluster ZooKeeper mode.

## 9. Chẩn đoán `NOT_LEADER_OR_FOLLOWER` và metadata cũ

Lỗi này thường xuất hiện khi client gửi request tới broker dựa trên metadata cũ trong khi leadership hoặc replica assignment đã thay đổi.

Các tình huống thường gặp:

- Partition leader vừa chuyển do broker restart hoặc failure.
- Partition reassignment vừa hoàn tất hoặc đang diễn ra.
- Controller đã cập nhật metadata nhưng client chưa refresh.
- Client kết nối được bootstrap broker nhưng không kết nối được địa chỉ broker leader trong metadata.
- `advertised.listeners` trả hostname/IP/port không thể truy cập từ mạng client.
- DNS, load balancer hoặc firewall đưa client đến endpoint không đúng.

Kafka producer và consumer chuẩn có cơ chế metadata refresh và retry cho nhiều lỗi transient. Nếu lỗi xuất hiện ngắn sau leader movement rồi biến mất, có thể đó là quá trình bình thường. Nếu lặp lại kéo dài:

1. Kiểm tra leader hiện tại bằng `kafka-topics --describe`.
2. Xác định broker client đang kết nối và broker leader mà metadata quảng bá.
3. Kiểm tra `advertised.listeners` trên broker leader.
4. Từ chính host/container chạy client, kiểm tra DNS, TCP và TLS tới advertised endpoint.
5. Kiểm tra log broker/controller và trạng thái reassignment.
6. Chỉ sau đó mới xem xét metadata refresh/reconnect hoặc restart client.

Bootstrap server chỉ là điểm vào để client lấy metadata. Client sau đó kết nối trực tiếp tới broker được quảng bá trong metadata. Vì vậy, bootstrap port hoạt động không chứng minh mọi broker endpoint đều truy cập được.

## 10. Producer biểu hiện lỗi như thế nào?

Producer cần metadata để biết partition leader trước khi gửi record. Khi topic hoặc leader chưa sẵn sàng, ứng dụng có thể gặp:

- `send()` chờ metadata hoặc buffer trong thời gian giới hạn bởi `max.block.ms`.
- Future/callback hoàn tất với lỗi retriable như leader unavailable hoặc not leader.
- Request timeout/network exception nếu broker không phản hồi.
- Callback thành công sau khi client refresh metadata và retry thành công.

Producer cần phân biệt lỗi transient với lỗi cấu hình vĩnh viễn. Không retry vô hạn với topic sai tên, authorization failure hoặc invalid topic.

### Cấu hình producer cần xem

| Cấu hình | Tác động |
|---|---|
| `bootstrap.servers` | Endpoint ban đầu để lấy metadata |
| `max.block.ms` | Thời gian tối đa `send()`/`partitionsFor()` có thể chờ metadata hoặc buffer |
| `request.timeout.ms` | Thời gian chờ phản hồi request |
| `delivery.timeout.ms` | Giới hạn tổng thời gian delivery, bao gồm retry và chờ acknowledgement |
| `retry.backoff.ms` / `retry.backoff.max.ms` | Khoảng nghỉ giữa các lần retry |
| `metadata.max.age.ms` | Chu kỳ tối đa trước khi client chủ động refresh metadata định kỳ |
| `acks` | Điều kiện acknowledgement của broker |

Không tăng tất cả timeout lên rất lớn để che một partition không có leader. Trước hết phải tìm nguyên nhân leader unavailable. Với producer idempotent, giữ cấu hình tương thích và không tự viết vòng lặp gửi lại một event như một record mới nếu chưa có event ID/deduplication.

## 11. Consumer biểu hiện lỗi như thế nào?

Consumer có thể subscribe thành công nhưng không nhận record vì:

- Topic chưa tồn tại hoặc subscription pattern chưa match.
- Partition chưa có leader hoặc broker leader không truy cập được.
- Consumer group chưa hoàn tất join/rebalance.
- Consumer được assign partition nhưng offset đang ở cuối log (`latest`).
- Group có committed offset cũ nên `auto.offset.reset` không được áp dụng.
- ACL không cho phép `DESCRIBE` hoặc `READ`.

Kiểm tra group:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker-1.internal:9092 \
  --describe --group order-service
```

Đối chiếu `CURRENT-OFFSET`, `LOG-END-OFFSET`, `LAG` và partition assignment. Nếu topic vừa được tạo, xác minh partition đã có leader trước khi kết luận consumer bị treo.

Với `auto.offset.reset=earliest`, consumer chỉ bắt đầu từ earliest khi group chưa có committed offset hợp lệ. Đổi từ `latest` sang `earliest` không làm group đã có offset tự quay về đầu. Để test/replay, dùng group ID riêng hoặc reset offset theo quy trình có kiểm soát.

## 12. Kiểm tra advertised listener từ mạng client

Một nguyên nhân phổ biến của metadata stale-like errors là broker trả địa chỉ leader không thể truy cập từ client. Ví dụ broker quảng bá `broker-2.internal:9092` nhưng container ứng dụng chỉ phân giải được tên DNS khác.

Kiểm tra cấu hình broker:

```properties
listeners=INTERNAL://0.0.0.0:9092
advertised.listeners=INTERNAL://broker-2.internal:9092
listener.security.protocol.map=INTERNAL:SASL_SSL
inter.broker.listener.name=INTERNAL
```

Từ host/container ứng dụng, kiểm tra:

```bash
getent hosts broker-2.internal
nc -vz broker-2.internal 9092
```

Trên Windows có thể dùng:

```powershell
Resolve-DnsName broker-2.internal
Test-NetConnection broker-2.internal -Port 9092
```

Nếu DNS/TCP không thông, kiểm tra routing, firewall, service discovery, NAT và listener mapping. Với TLS, xác minh certificate SAN khớp hostname advertised và truststore của client. Không sửa `advertised.listeners` thành `localhost` nếu client chạy ở host/container khác.

## 13. Xử lý topic vừa bị xóa rồi tạo lại

Xóa và tạo lại topic cùng tên có thể gây nhầm lẫn:

- Topic mới có topic ID khác topic cũ.
- Partition count, replica assignment hoặc config có thể khác.
- Client còn metadata cache của topic/partition cũ trong một khoảng thời gian.
- Consumer group vẫn có committed offset theo topic-partition identity/name semantics; việc tái sử dụng tên có thể làm test/ứng dụng hiểu sai vị trí đọc.

Nếu topic vừa được recreate:

1. Xác nhận topic mới đã được tạo trên đúng cluster.
2. Describe partition count, leader, replicas và config.
3. Đợi metadata và leader ổn định.
4. Kiểm tra group offset có cần reset hay phải dùng group mới.
5. Xác minh producer/consumer đang truy cập đúng topic mới.

Trong test, ưu tiên tên topic duy nhất cho mỗi run thay vì liên tục xóa rồi tạo lại cùng tên. Trong production, không xóa/recreate topic để “refresh metadata” khi chưa đánh giá tác động retention, offsets và consumer state.

## 14. Retry có giới hạn và backoff

Lỗi leader election ngay sau broker restart có thể transient. Client Kafka chuẩn tự refresh metadata và retry nhiều lỗi retriable. Ứng dụng chỉ nên thêm retry ở tầng business khi cần xử lý thao tác cấp cao, với giới hạn rõ ràng.

Một policy retry an toàn thường có:

- Chỉ retry lỗi transient/retriable.
- Exponential backoff có jitter để tránh nhiều client retry đồng thời.
- Deadline tổng và số lần thử tối đa.
- Không retry authorization, invalid topic hoặc lỗi cấu hình vĩnh viễn.
- Log topic, partition, broker, error code và attempt number.
- Sau khi hết retry, đưa lỗi vào luồng xử lý/alert phù hợp thay vì bỏ qua.

Ví dụ pseudocode:

```java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        sendOrRead();
        return;
    } catch (RetriableException error) {
        if (attempt == maxAttempts || deadlineExceeded()) {
            throw error;
        }
        sleep(backoffWithJitter(attempt));
    }
}
```

Đây là pseudocode cho thao tác cấp ứng dụng; không bọc mọi `KafkaException` vào cùng một retry loop. Nếu producer đã gửi nhưng client timeout trước khi nhận acknowledgement, gửi lại như event mới có thể tạo duplicate. Dùng idempotent producer cho retry protocol và event ID/idempotent consumer cho retry ở business layer.

## 15. Quy trình chẩn đoán theo triệu chứng

| Triệu chứng | Kiểm tra đầu tiên | Bước tiếp theo |
|---|---|---|
| `UnknownTopicOrPartitionException` ngay khi startup | Cluster endpoint và tên topic | Provision topic, kiểm tra ACL, chờ metadata nếu topic vừa tạo |
| `LEADER_NOT_AVAILABLE` kéo dài | `Leader: -1`, unavailable partitions | Kiểm tra controller, broker, ISR và log election |
| `NOT_LEADER_OR_FOLLOWER` sau restart | Leader hiện tại và client metadata | Kiểm tra advertised listener/DNS/network, để client refresh metadata |
| Producer `send()` timeout | `max.block.ms`, callback error, broker request latency | Kiểm tra metadata, buffer pressure và leader endpoint |
| Consumer subscribe nhưng không có record | Topic/partition, group assignment, offset | Kiểm tra `earliest/latest`, committed offset, ACL và lag |
| `NOT_ENOUGH_REPLICAS` | ISR count và `min.insync.replicas` | Khôi phục follower replication, không ép leader mới tùy tiện |
| Topic có leader nhưng một broker không truy cập được | Advertised endpoint từ client network | Sửa DNS, listener, firewall hoặc TLS |
| Chỉ một số partition lỗi | Partition-specific leader/replica state | So sánh log directory và broker đang giữ replica đó |

## 16. Những thao tác không nên dùng để chữa cháy

- Không tạo topic mới với tên gần giống chỉ để né `UNKNOWN_TOPIC_OR_PARTITION` trước khi xác nhận typo/cluster.
- Không bật auto topic creation trên production để che lỗi provisioning.
- Không restart toàn bộ broker khi chỉ một partition đang chuyển leader.
- Không bật `unclean.leader.election.enable` chỉ để làm partition có leader mà chưa chấp nhận nguy cơ mất dữ liệu.
- Không xóa log directory hoặc format storage để xử lý metadata stale.
- Không reset consumer group offset nếu chưa xác định chính xác group, topic và partition cần reset.
- Không retry vô hạn với authorization hoặc invalid topic.
- Không tăng timeout đến hàng phút/hàng giờ mà không có deadline và alert.
- Không coi under-replicated partition là offline partition; phân biệt replica lag với không có leader.

Unclean leader election có thể chọn replica ngoài ISR và làm mất các record đã được leader cũ xác nhận nhưng chưa replicate. Đây là quyết định availability so với durability, chỉ thực hiện theo recovery plan đã phê duyệt.

## 17. Checklist xử lý sự cố

- [ ] Xác nhận `bootstrap.servers`, cluster ID và principal của ứng dụng.
- [ ] Xác minh tên topic và partition trên đúng cluster.
- [ ] Kiểm tra ACL/authorization trước khi kết luận topic missing.
- [ ] Describe topic, leader, replicas và ISR.
- [ ] Phân biệt unavailable partition với under-replicated partition.
- [ ] Với KRaft, kiểm tra controller quorum leader, majority và metadata replication.
- [ ] Với ZooKeeper mode, kiểm tra active controller và ZooKeeper connectivity.
- [ ] Kiểm tra advertised listener, DNS, TCP, TLS từ chính client host/container.
- [ ] Xem log broker/controller tại thời điểm lỗi.
- [ ] Kiểm tra consumer group assignment và committed offset nếu consumer không đọc.
- [ ] Chỉ retry lỗi transient với backoff và deadline.
- [ ] Không reset offset, xóa topic hoặc bật unclean election khi chưa có đánh giá dữ liệu.
- [ ] Sau khi phục hồi, xác minh producer ack, consumer progress, ISR và error rate trở lại baseline.

## Tài liệu tham khảo

- [Apache Kafka Protocol — Error Codes](https://kafka.apache.org/protocol)
- [Apache Kafka Admin API](https://kafka.apache.org/documentation/#adminapi)
- [Apache Kafka Producer Configs](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka Operations — Basic Kafka Operations](https://kafka.apache.org/documentation/#basic_ops)
- [Apache Kafka KRaft Operations](https://kafka.apache.org/documentation/#kraft)

Khi gặp topic missing, metadata stale hoặc leader chưa sẵn sàng, hãy xác minh theo lớp: cluster và tên topic, topic/partition metadata, leader/ISR/controller, rồi mới đến client cache và network endpoint. `UNKNOWN_TOPIC_OR_PARTITION`, `NOT_LEADER_OR_FOLLOWER` và `LEADER_NOT_AVAILABLE` có thể xuất hiện trong giai đoạn chuyển tiếp nhưng không có cùng cách khắc phục. Tạo topic tường minh, chờ leader bằng deadline, kiểm tra advertised listeners và chỉ retry lỗi transient sẽ giúp khôi phục đúng nguyên nhân mà không làm mất dữ liệu hoặc che giấu lỗi cấu hình.

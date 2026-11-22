# __consumer_offsets và vòng đời offset đã commit

## Mục tiêu bài học

Kafka consumer group cần lưu tiến độ đọc để consumer có thể khởi động lại hoặc tham gia rebalance mà không phải tự ghi nhớ vị trí đã xử lý. Khi ứng dụng commit offset, group coordinator lưu thông tin đó trong internal topic __consumer_offsets. Đây là topic nội bộ của Kafka, được quản lý bằng cơ chế replication và log compaction.

Bài học giải thích __consumer_offsets lưu những loại metadata nào, group coordinator ghi và đọc committed offset ra sao, offset được giữ trong bao lâu, và điều gì xảy ra khi consumer restart. Người học cũng thực hành kiểm tra, reset và replay offset bằng Kafka CLI, Java Consumer API và Spring Kafka.

Sau bài học, người học có thể:

- Giải thích vai trò của internal topic __consumer_offsets.
- Mô tả mối quan hệ giữa group ID, group coordinator và partition của offsets topic.
- Phân biệt consumer position, committed offset và log end offset.
- Giải thích vòng đời commit và fetch offset khi consumer restart.
- Hiểu log compaction, tombstone và retention của committed offset.
- Cấu hình replication và retention cho internal offsets topic.
- Kiểm tra consumer group và reset offset an toàn để replay dữ liệu.
- Quản lý commit offset trong Java và Spring Kafka, kể cả khi dùng transaction.

## 1. Vì sao Kafka cần lưu committed offset?

Consumer đọc record theo offset của từng partition. Nếu consumer dừng rồi khởi động lại, nó cần biết vị trí tiếp tục đọc. Kafka cho phép consumer group commit offset lên broker để tiến độ đọc được lưu bền vững và dùng chung giữa các instance của cùng group.

Ví dụ, group order-projection đọc topic orders, partition 0. Consumer đã xử lý các record đến offset 41. Vị trí tiếp theo cần đọc là 42, vì vậy group commit offset 42.

~~~mermaid
flowchart LR
    A[Consumer xử lý record offset 41] --> B[Commit next offset 42]
    B --> C[Group coordinator]
    C --> D[Internal topic __consumer_offsets]
    D --> E[Offset được lưu và replicate]
    E --> F[Consumer restart]
    F --> G[OffsetFetch]
    G --> H[Tiếp tục từ offset 42]
~~~

Committed offset là tiến độ do consumer group lưu. Nó không phải vị trí cuối cùng mà broker đã ghi, cũng không phải bằng chứng tự động rằng mọi side effect nghiệp vụ đã thành công. Ứng dụng phải commit sau khi xử lý đúng phần record mà offset đại diện.

## 2. __consumer_offsets là gì?

__consumer_offsets là internal topic Kafka dùng để lưu metadata liên quan đến consumer group, đặc biệt là committed offset theo từng group, topic và partition. Nó cũng lưu thông tin group metadata cần cho việc quản lý membership và trạng thái group.

Đây là topic do Kafka tự tạo và quản lý. Ứng dụng không publish event nghiệp vụ vào topic này và không nên thao tác trực tiếp lên file log hoặc record nội bộ của nó.

### 2.1. Những thông tin được lưu

Ở mức khái niệm, dữ liệu trong __consumer_offsets gồm:

| Nhóm dữ liệu | Nội dung |
|---|---|
| Committed offset | Offset tiếp theo mà group dự định đọc cho một topic-partition |
| Offset metadata | Metadata tùy chọn đi kèm committed offset, do ứng dụng/client cung cấp |
| Commit timestamp/expiration data | Thông tin thời gian phục vụ quản lý vòng đời offset |
| Group metadata | Thông tin membership, generation/protocol và trạng thái group cần cho điều phối |

Định dạng key/value nhị phân của internal topic là chi tiết triển khai theo phiên bản Kafka. Không nên tự parse, ghi hoặc sửa trực tiếp record nội bộ. Dùng Consumer API, Admin API, Kafka CLI và metrics để quan sát.

### 2.2. Cấu trúc logic của một committed offset

Một committed offset gắn với bộ ba:

- Consumer group ID.
- Topic name.
- Partition number.

Ví dụ:

| Group | Topic | Partition | Committed offset |
|---|---|---:|---:|
| order-projection | orders | 0 | 42 |
| order-projection | orders | 1 | 38 |
| billing-service | orders | 0 | 17 |

Hai group có thể commit offset khác nhau cho cùng một partition. Offset của partition 0 trong group order-projection không ảnh hưởng offset partition 0 của group billing-service.

### 2.3. Vì sao đây là internal compacted topic?

Kafka cấu hình __consumer_offsets để sử dụng log compaction. Với cùng một key đại diện cho group/topic/partition, Kafka có thể giữ lại giá trị mới nhất và loại các phiên bản commit cũ trong quá trình cleaner chạy.

Ví dụ một group commit nhiều lần:

| Thời điểm | Group/topic/partition | Offset được commit |
|---|---|---:|
| T1 | order-projection / orders / 0 | 20 |
| T2 | order-projection / orders / 0 | 30 |
| T3 | order-projection / orders / 0 | 42 |

Các commit mới cập nhật trạng thái tiến độ cho cùng key. Sau compaction, Kafka có thể loại các phiên bản cũ và giữ giá trị mới nhất. Việc compact diễn ra nền, không nhất thiết xóa record cũ ngay sau mỗi lần commit.

Khi offset hoặc group metadata hết hạn, Kafka có thể ghi tombstone cho key tương ứng. Tombstone báo cho log cleaner rằng key đó cần được loại bỏ trong quá trình compaction. Vì vậy, internal topic vừa lưu trạng thái mới nhất vừa có thể dọn metadata không còn hiệu lực.

## 3. Group coordinator và partition của __consumer_offsets

Mỗi consumer group được một group coordinator quản lý. Kafka xác định coordinator dựa trên partition của __consumer_offsets tương ứng với group ID. Broker đang làm leader của partition nội bộ đó đảm nhiệm vai trò coordinator cho các group được ánh xạ vào partition.

Quy trình khái quát:

1. Consumer dùng bootstrap server để tìm coordinator cho group ID.
2. Consumer gửi các request membership/offset đến coordinator.
3. Coordinator xử lý commit và fetch offset cho group.
4. Committed offset được ghi vào partition tương ứng của __consumer_offsets.
5. Partition nội bộ được replicate theo replication factor của internal topic.

~~~mermaid
flowchart TB
    subgraph CLIENTS[Consumer applications]
        C1[Consumer A<br/>group order-projection]
        C2[Consumer B<br/>group billing-service]
    end
    subgraph BROKERS[Kafka brokers]
        B1[Broker 1<br/>Group coordinator]
        B2[Broker 2<br/>Replica]
        B3[Broker 3<br/>Replica]
    end
    subgraph INTERNAL[__consumer_offsets partition]
        O[Committed offset records<br/>and group metadata]
    end
    C1 -->|OffsetCommit / OffsetFetch| B1
    C2 -->|OffsetCommit / OffsetFetch| B1
    B1 --> O
    O -->|Replication| B2
    O -->|Replication| B3
~~~

Sơ đồ minh họa một partition của internal topic. Trong cụm thực tế, __consumer_offsets có nhiều partition và các partition được phân bố trên broker. Các group khác nhau có thể do các coordinator khác nhau quản lý.

### 3.1. offsets.topic.num.partitions

offsets.topic.num.partitions xác định số partition của __consumer_offsets khi internal topic được tạo. Nhiều group được phân tán qua các partition này để chia tải coordinator và lưu trữ.

Giá trị mặc định phụ thuộc phiên bản/cấu hình Kafka; hãy kiểm tra cấu hình broker thay vì giả định một con số. Số partition của internal topic là quyết định hạ tầng quan trọng, không nên tùy tiện thay đổi sau khi cụm đã hoạt động vì việc ánh xạ group đến partition phụ thuộc cấu trúc này.

### 3.2. offsets.topic.replication.factor

offsets.topic.replication.factor xác định replication factor của internal topic. Với production, cần đủ replica để committed offset chịu được lỗi broker theo yêu cầu độ bền.

Nếu replication factor lớn hơn số broker đang có, Kafka có thể không tạo được internal topic khi group bắt đầu sử dụng. Trong lab một broker, có thể đặt replication factor bằng một; cấu hình đó không có khả năng chịu lỗi broker.

Committed offset là dữ liệu quan trọng. Nếu mất offset, consumer có thể đọc lại từ vị trí cũ hoặc áp dụng auto.offset.reset khi không còn offset hợp lệ, dẫn đến replay ngoài dự kiến.

## 4. Vòng đời commit offset

Khi consumer commit offset, nó gửi OffsetCommit request đến group coordinator. Coordinator xác thực trạng thái membership và ghi dữ liệu offset vào partition tương ứng của __consumer_offsets. Sau khi điều kiện lưu/replication theo cấu hình nội bộ được đáp ứng, coordinator phản hồi kết quả commit.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant G as Group Coordinator
    participant O as __consumer_offsets
    C->>G: OffsetCommit(group, topic, partition, nextOffset)
    G->>G: Kiểm tra membership/generation
    G->>O: Append offset commit record
    O-->>G: Ghi/replication hoàn tất theo điều kiện
    G-->>C: OffsetCommit response
~~~

Nếu consumer nhận commit success, committed offset đã được coordinator chấp nhận theo giao thức. Nếu response bị mất, kết quả commit có thể không rõ với client; commit cùng một next offset lần nữa thường không làm thay đổi ý nghĩa tiến độ, nhưng ứng dụng vẫn phải quản lý lỗi và trạng thái group.

### 4.1. Offset commit là vị trí tiếp theo

Một điểm dễ nhầm: ConsumerRecord.offset() là offset của record vừa đọc, còn offset commit thường là vị trí tiếp theo cần đọc.

Ví dụ:

~~~text
Đã xử lý record offset 41
Committed offset = 42
Lần đọc tiếp theo bắt đầu từ offset 42
~~~

Nếu commit 41 sau khi đã xử lý record 41, consumer có thể đọc lại record 41 sau restart. Với commit thủ công theo record, cần dùng record.offset() + 1.

### 4.2. Consumer position và committed offset

| Khái niệm | Ý nghĩa |
|---|---|
| Consumer position | Vị trí tiếp theo client sẽ fetch trong phiên hiện tại |
| Committed offset | Vị trí tiếp theo đã được group lưu trên broker |
| Log end offset | Vị trí cuối log; offset tiếp theo mà record mới có thể nhận |
| High watermark | Ranh giới dữ liệu đã replicate đủ điều kiện để consumer đọc theo chế độ thông thường |

Consumer position có thể đi trước committed offset vì ứng dụng đã fetch hoặc xử lý record nhưng chưa commit. Khi restart, consumer thường quay lại committed offset chứ không khôi phục vị trí tạm thời trong RAM của process cũ.

## 5. Vòng đời fetch offset khi consumer restart

Khi consumer khởi động lại và tham gia group:

1. Consumer tìm group coordinator.
2. Consumer tham gia group và nhận assignment.
3. Consumer gửi OffsetFetch request cho các topic-partition được giao.
4. Coordinator trả committed offset nếu còn tồn tại và hợp lệ.
5. Consumer tiếp tục đọc từ committed offset.
6. Nếu không có committed offset hợp lệ, client áp dụng auto.offset.reset.

auto.offset.reset không phải chính sách được áp dụng mỗi lần consumer restart. Nó chỉ được dùng khi group không có committed offset hợp lệ cho partition, ví dụ group mới hoặc offset đã nằm ngoài phạm vi log hiện còn.

Các giá trị phổ biến:

| Giá trị | Hành vi khi không có offset hợp lệ |
|---|---|
| earliest | Đọc từ offset sớm nhất còn có thể đọc |
| latest | Bắt đầu từ cuối log, bỏ qua dữ liệu cũ hiện có |
| none | Ném lỗi để ứng dụng quyết định rõ ràng |

Ví dụ:

~~~properties
auto.offset.reset=earliest
~~~

Nếu group đã commit offset 500 và offset đó còn hợp lệ, consumer tiếp tục từ 500 dù auto.offset.reset=earliest. Nếu offset 500 không còn tồn tại do retention, Kafka có thể áp dụng reset policy theo tình huống offset out of range.

## 6. Retention của committed offset

Committed offset không được giữ vô thời hạn trong mọi trường hợp. Broker có cấu hình offsets.retention.minutes để quản lý thời gian lưu offset của group không còn hoạt động. Khi group không còn member hoạt động trong khoảng thời gian retention và không commit mới, offset có thể hết hạn rồi được dọn khỏi internal topic qua tombstone/compaction.

Các cấu hình liên quan:

| Cấu hình broker | Vai trò |
|---|---|
| offsets.retention.minutes | Thời gian lưu committed offset cho group không hoạt động theo chính sách broker |
| offsets.retention.check.interval.ms | Chu kỳ broker kiểm tra offset đã hết hạn |
| offsets.topic.replication.factor | Replication factor của internal offsets topic |
| offsets.topic.num.partitions | Số partition của internal offsets topic khi được tạo |
| offsets.commit.timeout.ms | Thời gian coordinator chờ thao tác ghi offset nội bộ hoàn tất trước khi trả lỗi timeout |

Giá trị mặc định và giới hạn có thể thay đổi theo phiên bản Kafka. Kiểm tra cấu hình broker thực tế trước khi áp dụng.

### 6.1. Group đang hoạt động và group không hoạt động

Khi group còn consumer hoạt động, committed offset tiếp tục được cập nhật theo tiến độ đọc. Chính sách retention chủ yếu quan trọng khi group không còn member và không commit trong thời gian dài.

Ví dụ:

- Một service chạy liên tục và commit offset thường xuyên: offset của group được duy trì khi group hoạt động.
- Một batch job chạy một lần rồi kết thúc: group trở thành empty; nếu không chạy lại trong thời gian retention, offset có thể hết hạn.
- Một group bị bỏ quên trong môi trường staging: committed offset có thể được dọn, và lần chạy sau sẽ phụ thuộc auto.offset.reset.

Điều này quan trọng với batch consumer chạy theo lịch. Nếu muốn giữ tiến độ qua khoảng nghỉ dài hơn retention, cần cấu hình retention phù hợp hoặc lưu checkpoint nghiệp vụ riêng.

### 6.2. Retention và compaction phối hợp

Offset record được compact theo key để giữ giá trị mới nhất. Khi offset hết hạn, Kafka có thể ghi tombstone cho key. Tombstone được giữ trong khoảng thời gian cần thiết rồi có thể bị cleaner loại bỏ. Vì vậy, quan sát file log vật lý ngay sau khi offset hết hạn không nhất thiết thấy dung lượng giảm tức thì.

Không nên tự xóa record hoặc file của __consumer_offsets để ép group reset. Dùng Admin API hoặc kafka-consumer-groups.sh để thay đổi committed offset theo cách được hỗ trợ.

## 7. Cấu hình internal offsets topic

Một số broker setting minh họa:

~~~properties
# Giá trị ví dụ cho cụm production có ít nhất ba broker.
offsets.topic.num.partitions=50
offsets.topic.replication.factor=3
offsets.retention.minutes=10080
offsets.retention.check.interval.ms=600000
offsets.commit.timeout.ms=5000
~~~

10080 phút tương đương bảy ngày. Đây chỉ là ví dụ cấu hình; cần xem workload, batch schedule và yêu cầu giữ offset của tổ chức.

Với lab một broker, cấu hình replication factor phải phù hợp:

~~~properties
offsets.topic.replication.factor=1
~~~

Không dùng replication factor bằng một cho production nếu cần khả năng chịu lỗi broker. Với cụm hiện hữu, kiểm tra internal topic đã được tạo với số partition/replica nào trước khi thay đổi cấu hình broker; thay đổi default không tự động tái cấu trúc topic đã tồn tại.

## 8. Kiểm tra committed offset bằng Kafka CLI

### 8.1. Xem offset và lag của group

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group order-projection
~~~

Kết quả thường có các cột:

| Cột | Ý nghĩa |
|---|---|
| TOPIC | Topic consumer group đang đọc |
| PARTITION | Partition tương ứng |
| CURRENT-OFFSET | Committed offset hiện tại |
| LOG-END-OFFSET | Vị trí cuối log |
| LAG | Chênh lệch giữa log end offset và committed offset theo cách CLI tính |
| CONSUMER-ID | Consumer đang được gán partition |
| HOST | Host của consumer |
| CLIENT-ID | Client ID |

Lag cao có thể do consumer xử lý chậm, không commit, group đang rebalance hoặc producer ghi nhanh hơn tốc độ xử lý. Đọc committed offset cùng log end offset để phân biệt tiến độ xử lý với tốc độ phát sinh dữ liệu.

### 8.2. Xem trạng thái group và member

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group order-projection --state
~~~

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group order-projection --members --verbose
~~~

Các tùy chọn hiển thị phụ thuộc phiên bản Kafka. Dùng script cùng phiên bản với cluster và kiểm tra --help khi cần.

### 8.3. Xem internal topic

Quản trị viên có thể mô tả topic nội bộ để kiểm tra partition, leader, replica và ISR:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic __consumer_offsets
~~~

Đây là thao tác quan sát. Không dùng console producer/consumer để ghi trực tiếp vào internal topic và không thay đổi cấu trúc key/value nội bộ.

## 9. Reset offset để replay dữ liệu

Reset offset thay đổi committed position của consumer group. Nó không xóa record trong topic và cũng không tạo bản sao record. Khi consumer đọc lại từ offset cũ, ứng dụng sẽ xử lý lại các record đó; side effect có thể lặp nếu consumer không idempotent.

### 9.1. Điều kiện trước khi reset

- Dừng tất cả consumer đang thuộc group cần reset.
- Xác nhận đúng group ID, topic và partition.
- Kiểm tra retention: offset đích phải còn nằm trong phạm vi dữ liệu có thể đọc.
- Xem xét tác động lặp lên database, API, email hoặc hệ thống downstream.
- Ghi lại offset hiện tại để có thể phục hồi.
- Chạy --dry-run trước khi dùng --execute.

### 9.2. Reset về earliest

Xem trước thay đổi:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets --to-earliest --dry-run
~~~

Thực thi sau khi xác nhận:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets --to-earliest --execute
~~~

### 9.3. Reset theo offset cụ thể

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders:0 \
  --reset-offsets --to-offset 100 --dry-run
~~~

Sau khi kiểm tra kết quả:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders:0 \
  --reset-offsets --to-offset 100 --execute
~~~

### 9.4. Reset theo thời gian hoặc dịch chuyển tương đối

Kafka CLI ở các phiên bản hỗ trợ có thể reset theo timestamp (--to-datetime), dịch chuyển offset (--shift-by) hoặc các lựa chọn khác. Kiểm tra kafka-consumer-groups.sh --help của phiên bản đang dùng trước khi chạy.

Reset offset là thao tác ảnh hưởng dữ liệu nghiệp vụ ở downstream vì record có thể được xử lý lại. Không chạy reset trên group đang hoạt động; consumer đang chạy có thể tiếp tục dùng position trong bộ nhớ và commit đè lên offset vừa reset.

## 10. Commit offset bằng Java Consumer API

### 10.1. Commit đồng bộ

Với enable.auto.commit=false, ứng dụng chủ động commit sau khi xử lý record thành công:

~~~java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-projection");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());

KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props);
consumer.subscribe(List.of("orders"));

while (running) {
    ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(500));

    for (ConsumerRecord<String, String> record : records) {
        processBusiness(record);
    }

    consumer.commitSync();
}
~~~

commitSync() commit các offset hiện tại của consumer. Ví dụ này giả định tất cả record trả về trong poll đã xử lý thành công. Nếu một record lỗi và ứng dụng vẫn commit toàn bộ batch, record lỗi có thể bị bỏ qua sau restart.

### 10.2. Commit offset cụ thể theo partition

Ứng dụng có thể tự tạo map offset:

~~~java
TopicPartition partition = new TopicPartition("orders", 0);
long nextOffset = 42L;

Map<TopicPartition, OffsetAndMetadata> offsets = Map.of(
    partition,
    new OffsetAndMetadata(nextOffset)
);

consumer.commitSync(offsets);
~~~

Giá trị 42 là vị trí tiếp theo cần đọc. Nếu record vừa xử lý có offset 41, commit offset 42.

### 10.3. Commit bất đồng bộ

~~~java
consumer.commitAsync((offsets, exception) -> {
    if (exception != null) {
        logger.error("Offset commit failed: {}", offsets, exception);
        return;
    }

    logger.debug("Offset commit succeeded: {}", offsets);
});
~~~

commitAsync() không chặn thread chờ broker phản hồi. Ứng dụng cần xử lý lỗi trong callback và tránh gửi các commit cũ có thể ghi đè tiến độ mới hơn. Khi shutdown hoặc tại ranh giới cần chắc chắn commit cuối, có thể dùng commitSync() theo lifecycle thích hợp.

### 10.4. Kiểm tra committed offset bằng API

~~~java
Set<TopicPartition> partitions = Set.of(
    new TopicPartition("orders", 0)
);

Map<TopicPartition, OffsetAndMetadata> committed =
    consumer.committed(partitions);

OffsetAndMetadata metadata =
    committed.get(new TopicPartition("orders", 0));

if (metadata != null) {
    System.out.println("Committed offset = " + metadata.offset());
}
~~~

Consumer API cũng cung cấp position(partition) để đọc position hiện tại trong phiên consumer. So sánh position() và committed() giúp phát hiện consumer đã fetch/xử lý tiến xa hơn mức đã lưu hay chưa.

## 11. Spring Kafka và commit lifecycle

Spring Kafka listener container quản lý vòng poll và offset commit. AckMode xác định thời điểm container commit offset dựa trên xử lý listener.

Một số chế độ phổ biến:

| AckMode | Hành vi tổng quát |
|---|---|
| RECORD | Commit sau khi listener xử lý thành công từng record |
| BATCH | Commit sau khi xử lý thành công toàn bộ batch được poll |
| TIME | Commit theo thời gian khi có record đã xử lý |
| COUNT | Commit sau số lượng record đã xử lý được cấu hình |
| MANUAL | Listener chủ động acknowledge; container thực hiện commit theo semantics của mode |
| MANUAL_IMMEDIATE | Commit ngay khi acknowledge trong điều kiện phù hợp với thread/container |

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-projection
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

Listener:

~~~java
@KafkaListener(topics = "orders", groupId = "order-projection")
public void consume(ConsumerRecord<String, String> record) {
    processBusiness(record);
}
~~~

Với AckMode.RECORD, container commit sau khi listener xử lý record thành công theo cơ chế quản lý lỗi của container. Nếu listener ném exception, error handler và retry policy sẽ quyết định record được thử lại, recover hay chuyển sang dead-letter topic.

Không bật enable.auto.commit=true đồng thời kỳ vọng Spring listener container hoàn toàn kiểm soát commit. Hãy để container quản lý commit theo AckMode trong cấu hình thông thường của Spring Kafka.

## 12. Kafka transaction và committed offset

Với consume-transform-produce, Kafka có thể commit output record và input offset trong cùng một Kafka transaction. Điều này giúp consumer downstream không thấy output đã commit nếu transaction chưa hoàn tất.

Ví dụ khái niệm với Kafka Java client:

~~~java
producer.beginTransaction();

producer.send(new ProducerRecord<>("orders-processed", key, transformedValue));

Map<TopicPartition, OffsetAndMetadata> offsets =
    Map.of(inputPartition, new OffsetAndMetadata(inputRecord.offset() + 1));

producer.sendOffsetsToTransaction(offsets, consumer.groupMetadata());
producer.commitTransaction();
~~~

Consumer input cần tắt auto commit và consumer downstream thường dùng isolation.level=read_committed để chỉ đọc record thuộc transaction đã commit. Producer cần transactional.id được cấu hình đúng và được khởi tạo transaction theo API.

Transaction Kafka có thể phối hợp output topic và committed offset trong Kafka. Nó không tự bao gồm database bên ngoài; nếu listener cập nhật database, hãy xem xét outbox/inbox hoặc cơ chế idempotency riêng.

## 13. Sự cố thường gặp liên quan đến __consumer_offsets

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Consumer restart đọc lại nhiều record | Offset chưa commit hoặc commit sau xử lý bị lỗi | So sánh committed offset với position và log nghiệp vụ |
| Consumer bỏ qua record | Commit offset quá sớm hoặc commit vượt qua record chưa xử lý | Kiểm tra commit logic, batch và async processing |
| Group không tìm được coordinator | Broker giữ coordinator hoặc partition offsets topic gặp sự cố | Kiểm tra broker availability, leader/ISR của internal topic |
| Offset commit timeout | Coordinator quá tải, replication chậm hoặc internal topic thiếu ISR | Kiểm tra broker request latency, ISR và disk/network |
| Group mới đọc từ đầu/cuối ngoài dự kiến | Không có committed offset hợp lệ và auto.offset.reset được áp dụng | Kiểm tra retention, group ID và reset policy |
| Batch job chạy lại không tiếp tục tiến độ cũ | Offset group đã hết retention | Kiểm tra offsets.retention.minutes và lịch chạy |
| Lag tăng dù consumer vẫn xử lý | Commit chậm hoặc không commit | Kiểm tra AckMode, commit callback và exception |
| Reset offset không có tác dụng như mong đợi | Consumer group vẫn đang hoạt động hoặc consumer commit lại position cũ | Dừng toàn bộ member, reset rồi xác minh trước khi restart |

Không xóa hoặc sửa trực tiếp __consumer_offsets để xử lý các lỗi trên. Hãy kiểm tra coordinator, internal topic replication, commit response và consumer group bằng công cụ hỗ trợ.

## 14. Quy trình vận hành an toàn khi replay

Trước khi replay một group:

1. Xác định chính xác group ID, topic và partition cần đọc lại.
2. Kiểm tra committed offset hiện tại và log end offset.
3. Xác nhận dữ liệu từ offset đích vẫn còn trong retention.
4. Dừng tất cả consumer thuộc group.
5. Xuất/lưu lại offset hiện tại hoặc ghi lại kết quả dry-run.
6. Chạy reset với --dry-run.
7. Đánh giá side effect lặp ở database, API và hệ thống downstream.
8. Thực thi reset bằng --execute.
9. Kiểm tra lại committed offset sau reset.
10. Khởi động consumer và giám sát lag, throughput, lỗi xử lý.

Nếu cần replay mà vẫn giữ luồng production hoạt động, cân nhắc tạo consumer group mới với group ID riêng. Group mới có tiến độ độc lập và không làm thay đổi committed offset của group production. Tuy nhiên, downstream vẫn có thể nhận lại cùng sự kiện và cần idempotency.

## 15. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1: Quan sát vòng đời committed offset

1. Tạo topic orders-lab có hai partition.
2. Chạy consumer group offset-lab với auto commit tắt.
3. Đọc và xử lý một số record rồi commit.
4. Dừng consumer và dùng CLI xem committed offset.
5. Khởi động lại cùng group và xác nhận consumer tiếp tục từ offset đã commit.

### Bài tập 2: So sánh position và committed offset

1. Đọc nhiều record nhưng chỉ commit một phần.
2. Ghi log consumer.position(partition) và consumer.committed(partitions).
3. Dừng process trước commit tiếp theo.
4. Khởi động lại và quan sát record được đọc lại.
5. Giải thích sự khác nhau giữa position trong RAM và offset lưu trong broker.

### Bài tập 3: Reset và replay

1. Dừng toàn bộ consumer của group offset-lab.
2. Chạy reset về earliest với --dry-run.
3. Kiểm tra topic, partition và offset đích.
4. Thực thi reset trong môi trường lab.
5. Khởi động consumer và quan sát dữ liệu được đọc lại.
6. Kiểm tra downstream có xử lý trùng hay không.

### Bài tập 4: Retention của group không hoạt động

1. Dùng môi trường lab và cấu hình offsets retention ngắn.
2. Chạy batch consumer, commit offset rồi dừng group.
3. Quan sát trạng thái group và committed offset qua thời gian.
4. Khởi động lại sau khi offset hết hạn nếu có thể quan sát trong phiên bản đang dùng.
5. Giải thích vai trò của auto.offset.reset.

### Câu hỏi tự kiểm tra

1. __consumer_offsets lưu những loại metadata nào?
2. Group coordinator được liên kết với partition offsets topic ra sao?
3. Vì sao committed offset là vị trí tiếp theo cần đọc?
4. Consumer position khác committed offset như thế nào?
5. Log compaction giúp internal offsets topic quản lý dữ liệu ra sao?
6. Khi nào committed offset của group không hoạt động có thể hết hạn?
7. auto.offset.reset có được áp dụng mỗi lần consumer restart không?
8. Vì sao phải dừng consumer trước khi reset offset?
9. Reset offset có xóa record trong topic không?
10. Kafka transaction có thể commit output record và input offset cùng nhau như thế nào?

Khi hiểu __consumer_offsets là nơi Kafka lưu tiến độ và metadata của consumer group, người vận hành có thể kiểm tra commit, khôi phục consumer sau restart và replay dữ liệu có kiểm soát mà không can thiệp trực tiếp vào internal log.

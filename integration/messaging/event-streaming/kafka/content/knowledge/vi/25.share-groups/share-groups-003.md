# Điều kiện phiên bản, cấu hình và khả năng hỗ trợ của client

## Mục tiêu bài học

Share Groups (Queues for Kafka, KIP-932) bổ sung mô hình tiêu thụ theo từng record bên cạnh consumer group truyền thống. Nhiều consumer trong cùng share group có thể cùng nhận record từ một partition; broker khóa record trong thời gian xử lý và lưu trạng thái acknowledge cho từng record. Cách làm này phù hợp với workload dạng hàng đợi, nơi các công việc độc lập cần được phân phối cho một pool worker và thứ tự xử lý toàn cục không phải yêu cầu bắt buộc.

Tuy nhiên, share group cần broker, feature level và client API hỗ trợ. `KafkaConsumer` thông thường không tự chuyển thành share consumer chỉ bằng cách đổi `group.id` hoặc `group.protocol`. Ứng dụng phải dùng API share consumer riêng hoặc framework đã tích hợp API đó.

Sau bài học, bạn có thể:

- Phân biệt share group với consumer group theo partition assignment, record locking, acknowledgment và ordering.
- Xác định mốc phiên bản preview và production-ready của Apache Kafka Share Groups.
- Kiểm tra `share.version` và điều kiện broker trước khi triển khai.
- Hiểu internal topic `__share_group_state` và cấu hình replication/min ISR.
- Cấu hình broker, share group và share consumer đúng phạm vi.
- Dùng `KafkaShareConsumer` trong Java với implicit hoặc explicit acknowledgment.
- Chọn `ACCEPT`, `RELEASE`, `REJECT` hoặc `RENEW` theo kết quả xử lý.
- Nhận biết giới hạn của Kafka client, librdkafka và Spring Kafka theo phiên bản.
- Tích hợp Share Consumer với `ShareKafkaListenerContainerFactory` trong Spring Kafka.
- Vận hành, quan sát và xử lý lỗi share group bằng công cụ Kafka.

## 1. Share Group giải quyết vấn đề nào?

Trong consumer group truyền thống, Kafka phân phối partition cho các consumer member. Tại một thời điểm, một partition chỉ được một member trong group đọc. Cách này giữ thứ tự record trong partition và phù hợp với event stream cần xử lý tuần tự theo key/partition.

Một số workload lại giống hàng đợi công việc:

- Mỗi record là một công việc độc lập.
- Worker có thời gian xử lý khác nhau.
- Một số record xử lý nhanh, một số record gọi API hoặc chạy tác vụ lâu.
- Khi worker lỗi, công việc cần được giao lại cho worker khác.
- Có thể chấp nhận xử lý không theo thứ tự append của partition.
- Muốn tăng số worker mà không phải tăng partition chỉ để phân chia consumer.

Share Group cho phép nhiều share consumer trong cùng group cùng tiêu thụ record từ một partition. Broker cấp quyền xử lý (acquire) theo từng record thay vì giao độc quyền cả partition cho một consumer. Sau khi xử lý, consumer acknowledge kết quả để broker cập nhật trạng thái record.

```text
Topic: image-jobs
Partition 0: [J1] [J2] [J3] [J4] [J5] [J6]
                 |    |    |    |    |    |
                 +----+----+----+----+----+
                              |
                       Share Group
                              |
                  +-----------+-----------+
                  |           |           |
                  v           v           v
               Worker A    Worker B    Worker C
                 J1          J2          J3
                  |           |           |
                  +---- acknowledge -----+
```

Hình minh họa chỉ mô tả ý tưởng. Broker có thể cấp nhiều record cho một member theo batch; các record đã acquire vẫn bị khóa với member đó trong thời gian lock còn hiệu lực.

## 2. Share Group khác consumer group như thế nào?

| Tiêu chí | Consumer group truyền thống | Share group |
|---|---|---|
| Đơn vị phân phối | Partition | Record được acquire trong partition |
| Phân phối partition | Một member sở hữu partition tại một thời điểm | Nhiều member có thể cùng nhận record từ một partition |
| Tiến độ | Offset commit theo partition | Trạng thái acknowledgment theo record; group có start offset/record state |
| Xử lý đồng thời | Consumer trong cùng group xử lý các partition khác nhau | Nhiều consumer có thể xử lý record khác nhau của cùng partition |
| Ordering | Thứ tự trong partition được giữ nếu xử lý tuần tự | Không bảo đảm thứ tự hoàn tất xử lý giữa các member |
| Retry | Thường dựa trên offset, seek, retry topic hoặc application logic | Record có thể RELEASE hoặc được giao lại khi lock hết hạn |
| Lỗi vĩnh viễn | Application thường dùng DLT hoặc bỏ qua theo offset policy | REJECT record; có thể dùng DLQ khi feature level hỗ trợ |
| Scale consumer | Mức song song hữu ích bị giới hạn bởi số partition | Có thể có nhiều member hơn số partition, tùy giới hạn broker/lock |
| Phù hợp | Event stream, ordering theo key, xử lý tuần tự | Queue-like workload, tác vụ độc lập, xử lý từng record |

Hai loại group có thể tiêu thụ cùng một topic độc lập. Một topic có thể phục vụ một consumer group để dựng projection có thứ tự và một share group để xử lý các tác vụ nền không yêu cầu ordering.

### 2.1. Share Group không loại bỏ partition

Record vẫn được lưu trong partition của topic. Partition vẫn quyết định nơi lưu log, replication, giới hạn throughput và đơn vị phân phối dữ liệu giữa broker. Share group chỉ thay đổi cách broker phân phối quyền xử lý record cho các consumer member.

Share group không làm một partition có throughput vô hạn. Broker vẫn có giới hạn số record đang được acquire trên mỗi share-partition; nếu chạm giới hạn, các poll tiếp theo có thể tạm thời không nhận thêm record cho partition đó.

### 2.2. Share Group không bảo đảm ordering nghiệp vụ

Giả sử partition có các record `A1`, `A2`, `A3`. Worker A có thể nhận `A1`, Worker B nhận `A2`; nếu Worker B xử lý xong trước, side effect của `A2` có thể xảy ra trước `A1`.

Client vẫn nhận các record trong một kết quả poll theo thứ tự offset tăng dần cho từng partition, nhưng khi nhiều member xử lý song song, thứ tự hoàn tất không được bảo đảm. Nếu nghiệp vụ yêu cầu `Created` phải hoàn tất trước `Paid`, hãy dùng consumer group truyền thống hoặc một cơ chế tuần tự hóa theo aggregate.

## 3. Điều kiện phiên bản Apache Kafka

Share Groups đã xuất hiện trong các bản client/broker trước khi được công bố production-ready. Không nên lấy việc class `KafkaShareConsumer` tồn tại trong JAR làm bằng chứng rằng cluster đã sẵn sàng production.

| Phiên bản Apache Kafka | Trạng thái Share Groups | Khuyến nghị |
|---|---|---|
| Kafka 3.9 và các bản API early-access liên quan | API còn ở trạng thái evolving/early access | Chỉ thử nghiệm, không dùng làm nền tảng production |
| Kafka 4.0 | Có API sớm trong một số artifact, chưa phải mốc production-ready | Không coi là phiên bản production cho Share Groups |
| Kafka 4.1 | Preview của KIP-932; không bật mặc định, cần feature `share.version=1` | Dùng để thử nghiệm và đánh giá tương thích |
| Kafka 4.2 | KIP-932 được công bố production-ready | Có thể triển khai production sau khi kiểm tra patch level và cấu hình cluster |
| Kafka 4.3 | Tiếp tục hỗ trợ Share Groups | Dùng feature/version và client phù hợp với cluster |
| Kafka 4.4 | Hỗ trợ Share Groups; `share.version=2` bổ sung DLQ cho share group | Có thể dùng DLQ nếu feature level và group/topic config đã được bật |

Kafka 4.2.1 có bản sửa lỗi quan trọng trong đường xử lý Share Group của Kafka 4.2.0. Khi chọn Kafka 4.2, nên dùng patch release đã bao gồm các sửa lỗi liên quan thay vì dừng ở bản 4.2.0.

### 3.1. Kiểm tra feature level của cluster

Không chỉ kiểm tra version chuỗi của broker. Hãy xem feature level mà cluster đã finalized:

```bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 describe
```

Tìm feature `share.version` trong kết quả. Trên Kafka 4.1, tài liệu phát hành mô tả preview cần nâng feature lên level 1. Trên Kafka 4.4, feature level 2 là điều kiện để dùng DLQ tích hợp cho share group.

Trước khi thay đổi feature level:

- Kiểm tra broker version và feature support của toàn cluster.
- Đọc upgrade guide đúng phiên bản.
- Xác định có cần rolling upgrade hay không.
- Kiểm tra khả năng tương thích client đang chạy.
- Có kế hoạch rollback/downgrade theo giới hạn feature metadata.

Không nâng feature level chỉ để thử một lệnh trên production. Feature level là trạng thái cluster, không phải thuộc tính cấu hình riêng của một consumer.

### 3.2. Client mới kết nối broker cũ

Java `KafkaShareConsumer` có thể kết nối đến broker hỗ trợ share group. Nếu gọi API không được broker version hiện tại hỗ trợ, client có thể nhận `UnsupportedVersionException`.

Vì vậy, kiểm tra cả hai phía:

1. Broker có hỗ trợ Share Group và feature level tương ứng không?
2. Client library có API share consumer và protocol version tương thích không?
3. Framework có tích hợp đúng share consumer API không?
4. Cấu hình group/broker có bật và cho phép feature đó không?

## 4. Internal state topic của Share Group

Share coordinator cần lưu trạng thái share group và trạng thái xử lý record. Kafka sử dụng internal topic `__share_group_state`, được tạo tự động khi cluster bắt đầu sử dụng share group.

Trong Kafka 4.2/4.4, cấu hình mặc định quan trọng gồm:

| Broker property | Giá trị mặc định tham khảo | Vai trò |
|---|---:|---|
| `share.coordinator.state.topic.replication.factor` | 3 | Replication factor của internal state topic |
| `share.coordinator.state.topic.min.isr` | 2 | Số replica tối thiểu phải xác nhận ghi |
| `share.coordinator.state.topic.num.partitions` | 50 | Số partition của state topic; không nên đổi sau khi triển khai |

### 4.1. Cluster có ít hơn ba broker

Với cluster chỉ có một hoặc hai broker, mặc định replication factor 3 khiến internal topic không thể được tạo đủ replica. Nếu muốn thử Share Groups trên cluster nhỏ, phải cấu hình trước khi sử dụng share group lần đầu:

```properties
share.coordinator.state.topic.replication.factor=1
share.coordinator.state.topic.min.isr=1
```

Đây là cấu hình phù hợp cho lab hoặc cluster nhỏ có chủ đích. Production nên có đủ broker và replication/min ISR phù hợp với yêu cầu availability; giảm RF/min ISR làm giảm khả năng chịu lỗi.

### 4.2. Không xóa internal topic

Không xóa `__share_group_state` để reset group hoặc giải quyết lỗi consumer. Topic này chứa trạng thái do share coordinator quản lý. Xóa nó có thể làm mất tiến độ/record state của share group.

Dùng `kafka-share-groups.sh` và các API quản trị được hỗ trợ để kiểm tra hoặc reset share group. Không sửa record internal bằng producer/consumer nghiệp vụ.

## 5. Cấu hình broker và share group

Share Group có cấu hình ở nhiều cấp:

- **Broker configuration:** giới hạn toàn cluster, ví dụ delivery count tối đa, record lock duration tối đa và giới hạn member.
- **Share group configuration:** chính sách cho một group, ví dụ lock duration, delivery count limit, isolation level và auto offset reset.
- **Client configuration:** hành vi polling, acknowledgment mode, acquire mode, deserializer và security.

Không nhầm tên property giữa các cấp. Ví dụ `group.share.record.lock.duration.ms` là giới hạn/default phía broker; `share.record.lock.duration.ms` là cấu hình group.

### 5.1. Broker configuration thường cần quan tâm

Các giá trị dưới đây là tham khảo từ Kafka 4.4; kiểm tra broker config reference của đúng phiên bản trước khi thay đổi:

| Broker property | Giá trị mặc định Kafka 4.4 | Ý nghĩa |
|---|---:|---|
| `group.share.record.lock.duration.ms` | 30000 ms | Lock duration mặc định của record |
| `group.share.delivery.count.limit` | 5 | Số lần giao tối đa mặc định |
| `group.share.partition.max.record.locks` | 2000 | Giới hạn record được acquire trên mỗi share-partition |
| `group.share.session.timeout.ms` | 45000 ms | Session timeout của share group |
| `group.share.heartbeat.interval.ms` | 5000 ms | Heartbeat interval |
| `group.share.max.size` | 200 | Số member tối đa mặc định của một share group |

Broker còn có min/max constraint cho các group-level config. Không đặt giá trị group vượt giới hạn broker cho phép.

### 5.2. Share group configuration

Một số cấu hình group thường dùng:

| Group property | Giá trị mặc định Kafka 4.4 | Tác động |
|---|---:|---|
| `share.record.lock.duration.ms` | 30000 ms | Thời gian một consumer giữ quyền xử lý record |
| `share.delivery.count.limit` | 5 | Số lần giao record tối đa trước khi record bị archive/đưa vào DLQ nếu được cấu hình |
| `share.partition.max.record.locks` | 2000 | Số record được acquire đồng thời trên mỗi partition của group |
| `share.session.timeout.ms` | 45000 ms | Thời gian phát hiện member không còn hoạt động |
| `share.heartbeat.interval.ms` | 5000 ms | Chu kỳ heartbeat |
| `share.renew.acknowledge.enable` | `true` | Cho phép member gia hạn record lock bằng RENEW |
| `share.auto.offset.reset` | `latest` | Vị trí bắt đầu khi group chưa có start offset hợp lệ |
| `share.isolation.level` | `read_uncommitted` | Cách đọc record transactional |

Ví dụ cập nhật cấu hình group:

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type groups --entity-name order-workers \
  --alter --add-config share.record.lock.duration.ms=60000
```

Đọc lại cấu hình:

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type groups --entity-name order-workers --describe
```

Đây là dynamic group config. Một số cấu hình broker-level là read-only và cần restart broker; đừng nhầm việc cập nhật group config với việc thay broker bounds.

### 5.3. Lock duration và delivery count

`share.record.lock.duration.ms` quyết định thời gian record đã acquire không được giao cho consumer khác. Nếu xử lý lâu hơn thời gian lock, record có thể trở lại trạng thái available và được giao lại trong khi worker cũ vẫn còn chạy.

Chọn lock duration dựa trên thời gian xử lý thực tế, percentile cao và thời gian gọi hệ thống bên ngoài. Với tác vụ có thời gian biến động lớn, dùng `RENEW` khi client/broker hỗ trợ hoặc chia công việc thành bước ngắn.

`share.delivery.count.limit` giới hạn số lần record được giao. Giá trị thấp giảm vòng lặp poison message nhưng có thể đưa lỗi tạm thời vào trạng thái archive quá sớm. Giá trị cao tăng cơ hội retry nhưng làm tăng tải và thời gian xử lý record lỗi.

### 5.4. `share.auto.offset.reset` khác `auto.offset.reset`

Share group có cấu hình `share.auto.offset.reset` riêng. Các giá trị được Kafka 4.4 hỗ trợ gồm:

- `earliest`: bắt đầu từ offset sớm nhất còn tồn tại.
- `latest`: bắt đầu từ cuối log hiện tại.
- `by_duration:<ISO-8601 duration>`: bắt đầu từ một khoảng thời gian tính lùi từ hiện tại.

Ví dụ `by_duration:PT2H` chỉ định phạm vi hai giờ trước. Kiểm tra format duration và tính năng được hỗ trợ ở broker/client version đang dùng.

Không mặc định `auto.offset.reset=earliest` của consumer group cũng áp dụng cho share group. Khi khởi tạo group mới, lựa chọn reset quyết định có xử lý backlog hiện có hay chỉ nhận record mới.

## 6. Cấu hình share consumer phía client

Một share consumer cần ít nhất bootstrap servers, group ID và deserializer phù hợp. Java API dùng `KafkaShareConsumer`, không dùng `KafkaConsumer` thông thường.

Ví dụ cấu hình Java:

```java
Properties props = new Properties();
props.setProperty("bootstrap.servers", "kafka-1:9092,kafka-2:9092");
props.setProperty("group.id", "order-workers");
props.setProperty("key.deserializer",
    StringDeserializer.class.getName());
props.setProperty("value.deserializer",
    StringDeserializer.class.getName());

// Chọn acknowledgment tường minh để quyết định theo từng record.
props.setProperty("share.acknowledgement.mode", "explicit");

// Giới hạn số record mỗi poll theo max.poll.records.
props.setProperty("share.acquire.mode", "record_limit");
props.setProperty("max.poll.records", "20");
```

Các thuộc tính `security.protocol`, SASL và SSL có thể được cấu hình giống Kafka client thông thường. Phải cấp quyền đọc topic và quyền sử dụng group tương ứng theo ACL/authorizer của cluster.

### 6.1. `share.acknowledgement.mode`

| Giá trị | Ý nghĩa |
|---|---|
| `implicit` | Client tự acknowledge các record của poll trước khi poll tiếp hoặc commit; đây là mặc định của Java share consumer |
| `explicit` | Ứng dụng phải acknowledge từng record bằng `acknowledge()` trước poll tiếp theo |

Trong explicit mode, nếu gọi `poll()` tiếp theo khi còn record của poll trước chưa được acknowledge, client có thể ném `IllegalStateException`. Điều này giúp ứng dụng không vô tình xác nhận thành công record chưa xử lý.

### 6.2. `share.acquire.mode`

| Giá trị | Ý nghĩa |
|---|---|
| `batch_optimized` | Tối ưu theo batch boundary; số record trả về có thể vượt `max.poll.records` và client có thể prefetch |
| `record_limit` | Số record trả về mỗi poll không vượt `max.poll.records`; kiểm soát số record và thời điểm acquire chặt hơn |

`batch_optimized` thường cho throughput tốt hơn. `record_limit` phù hợp khi cần giới hạn memory hoặc thời gian xử lý batch. Đừng giả định `max.poll.records` luôn là giới hạn cứng nếu đang dùng `batch_optimized`.

### 6.3. Poll liveness và record lock là hai timeout khác nhau

- `max.poll.interval.ms` kiểm soát khoảng cách giữa các lần gọi `poll()` để client duy trì liveness.
- `share.record.lock.duration.ms` kiểm soát thời gian record được acquire trước khi có thể giao lại.
- `share.session.timeout.ms` phát hiện member mất heartbeat.

Tăng lock duration không tự giải quyết việc consumer ngừng gọi poll quá lâu. Ngược lại, poll đều không bảo đảm record còn lock nếu thời gian xử lý vượt lock duration.

## 7. Java API: `KafkaShareConsumer`

### 7.1. Share consumer là một API riêng

Trong Kafka Java client, class chính là:

```java
org.apache.kafka.clients.consumer.KafkaShareConsumer<K, V>
```

Class này triển khai `ShareConsumer<K, V>`. Nó có vòng đời `subscribe()`, `poll()`, acknowledge và commit riêng. Không đổi `group.protocol` của `KafkaConsumer` thành một giá trị share để thay thế API này.

### 7.2. Ví dụ explicit acknowledgment

```java
Properties props = new Properties();
props.put("bootstrap.servers", "localhost:9092");
props.put("group.id", "image-workers");
props.put("key.deserializer", StringDeserializer.class.getName());
props.put("value.deserializer", StringDeserializer.class.getName());
props.put("share.acknowledgement.mode", "explicit");

try (KafkaShareConsumer<String, String> consumer =
         new KafkaShareConsumer<>(props)) {

    consumer.subscribe(List.of("image-jobs"));

    while (!Thread.currentThread().isInterrupted()) {
        ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofSeconds(1));

        for (ConsumerRecord<String, String> record : records) {
            try {
                processImage(record.value());
                consumer.acknowledge(record, AcknowledgeType.ACCEPT);
            } catch (TemporaryStorageException ex) {
                // Lỗi tạm thời: cho phép một worker khác thử lại.
                consumer.acknowledge(record, AcknowledgeType.RELEASE);
            } catch (InvalidJobException ex) {
                // Dữ liệu không thể xử lý: không giao lại record này.
                consumer.acknowledge(record, AcknowledgeType.REJECT);
            }
        }

        // Gửi các acknowledgment đang chờ lên broker.
        consumer.commitSync();
    }
}
```

Đoạn code minh họa cần import các lớp Kafka client tương ứng và xử lý exception theo ứng dụng. `try-with-resources` bảo đảm consumer được đóng khi thoát vòng lặp. Trong explicit mode, mọi record trả về từ poll phải có quyết định acknowledgment trước lần poll tiếp theo.

### 7.3. Ý nghĩa các loại acknowledgment

| AcknowledgeType | Ý nghĩa | Khi dùng |
|---|---|---|
| `ACCEPT` | Xác nhận record đã xử lý thành công | Side effect hoàn tất và có thể ghi nhận thành công |
| `RELEASE` | Trả record về trạng thái có thể được giao lại | Lỗi tạm thời như timeout hoặc dependency chưa sẵn sàng |
| `REJECT` | Từ chối record, không giao lại theo luồng delivery thông thường | Payload sai vĩnh viễn hoặc lỗi nghiệp vụ không thể retry |
| `RENEW` | Gia hạn acquisition lock vì record vẫn đang được xử lý | Tác vụ kéo dài hơn lock duration |

`RENEW` không phải kết quả cuối cùng. Sau khi xử lý xong, ứng dụng vẫn cần một quyết định cuối như ACCEPT, RELEASE hoặc REJECT. API renew chỉ khả dụng khi client/broker version hỗ trợ; kiểm tra phiên bản trước khi sử dụng.

### 7.4. Acknowledge chưa đồng nghĩa đã commit

Trong explicit mode, `acknowledge(record, type)` cập nhật trạng thái acknowledgment ở client. Trạng thái này được gửi lên Kafka khi gọi `commitSync()`, `commitAsync()` hoặc ở lần `poll()` tiếp theo theo semantics của client.

`commitSync()` chờ kết quả commit và có thể ném exception khi thất bại. `commitAsync()` không chờ kết quả; nếu process crash trước khi commit hoàn tất, record có thể được giao lại.

Trong Java API, `commitSync()` trả về map kết quả theo topic-partition, với `Optional<KafkaException>` cho từng entry. Hãy kiểm tra các lỗi trong map và xử lý exception của lời gọi; không bỏ qua kết quả commit trong code production.

Vì vậy, nếu xử lý nghiệp vụ đã thành công nhưng acknowledgment chưa được commit, record có thể xuất hiện lần nữa. Handler cần idempotent hoặc có deduplication key.

### 7.5. Implicit acknowledgment có rủi ro gì?

Với implicit mode, lần gọi `poll()` tiếp theo có thể ngầm acknowledge tất cả record được trả về từ poll trước như đã xử lý thành công. Nếu code gọi poll tiếp dù một record trong batch chưa xử lý xong hoặc đã gặp lỗi, ứng dụng có thể xác nhận nhầm record.

Với tác vụ có retry theo từng record, explicit acknowledgment thường dễ kiểm soát hơn. Chỉ dùng implicit khi ứng dụng thực sự xử lý toàn bộ batch thành công trước khi poll tiếp.

## 8. Record lock, redelivery và poison message

### 8.1. Vòng đời record

Một record trong share group có thể đi qua các trạng thái khái quát:

```text
Available
   |
   | Broker cấp record cho một share consumer
   v
Acquired (có lock)
   |
   +---- ACCEPT ----> Acknowledged
   |
   +---- RELEASE ---> Available (có thể giao lại)
   |
   +---- REJECT ----> Archived / không giao lại
   |
   +---- Lock hết hạn -> Available (có thể giao lại)
```

Record đang acquired không được cấp đồng thời cho consumer khác trong thời gian lock còn hiệu lực. Nếu consumer chết hoặc không acknowledge, lock hết hạn và broker có thể giao lại record.

### 8.2. Vì sao có thể xử lý trùng?

Worker A có thể đã ghi kết quả vào database nhưng crash trước khi commit ACCEPT. Sau khi lock hết hạn, Worker B nhận lại record và thực hiện side effect lần nữa.

Share Group không tự tạo transaction nguyên tử giữa acknowledgment và database/HTTP service. Hãy dùng:

- Event/job ID duy nhất.
- Idempotency key ở API đích.
- Inbox table có unique constraint.
- Upsert hoặc conditional update theo trạng thái/version.
- Transaction database bao quanh deduplication và business update.

### 8.3. Lock duration và tác vụ lâu

Nếu thời gian xử lý có thể vượt 30 giây mặc định, cân nhắc:

1. Đo p95/p99 processing time.
2. Đặt `share.record.lock.duration.ms` đủ cho workload bình thường.
3. Dùng RENEW khi API/version hỗ trợ và ứng dụng còn đang xử lý.
4. Tách công việc dài thành các bước nhỏ, có checkpoint/idempotency.
5. Cảnh báo khi lock timeout/redelivery tăng.

Không tăng lock duration quá lớn để che giấu worker bị treo. Lock dài làm thời gian giao lại record sau crash lâu hơn.

### 8.4. Delivery count limit

Broker đếm số lần record được giao. Khi vượt delivery count limit, record không tiếp tục được giao như bình thường. Mặc định Kafka 4.4 là 5 lần, với giới hạn broker cho phép cấu hình trong khoảng hỗ trợ.

Một policy tốt phân biệt:

- **Transient failure:** RELEASE để retry.
- **Permanent failure:** REJECT để dừng retry.
- **Processing still active:** RENEW nếu cần thêm thời gian.
- **Delivery count exhausted:** điều tra/archive hoặc route DLQ nếu feature được bật.

Không RELEASE mọi exception một cách vô hạn. Retry không giới hạn có thể giữ backlog và tiêu tốn tài nguyên.

## 9. Transactional records và isolation level

Share group có group-level setting `share.isolation.level`:

- `read_uncommitted`: nhận cả record transactional đã commit hoặc bị abort; đây là mặc định tham khảo Kafka 4.4.
- `read_committed`: chỉ nhận record transactional đã commit và record không transactional.

Isolation level áp dụng cho toàn share group, không phải từng consumer member. Với `read_committed`, tiến độ bị giới hạn bởi Last Stable Offset; transaction còn mở có thể chặn share group đọc tiếp qua vị trí đó.

Không nhầm `share.isolation.level` với `isolation.level` của consumer group truyền thống. Kiểm tra group config đúng tên và bảo đảm toàn group dùng semantics mong muốn.

## 10. Dead Letter Queue cho Share Groups

### 10.1. Điều kiện phiên bản

Trong Kafka 4.4, Share Group hỗ trợ DLQ khi feature `share.version` đạt level 2. Tính năng này bổ sung đường xử lý record bị REJECT hoặc vượt delivery count limit.

Kiểm tra feature:

```bash
bin/kafka-features.sh --bootstrap-server kafka-1:9092 describe
```

Tìm `share.version` và xác nhận finalized level phù hợp. Việc nâng feature level phải theo upgrade procedure của Kafka cluster.

### 10.2. Gán DLQ topic cho group

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --alter --add-config errors.deadletterqueue.topic.name=dlq.image-jobs \
  --entity-type groups --entity-name image-workers
```

Tự động tạo DLQ topic mặc định bị tắt. Nếu không bật auto-create ở broker, hãy tạo topic trước và bật cấu hình topic cho share group DLQ:

```bash
bin/kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --create --topic dlq.image-jobs \
  --partitions 6 --replication-factor 3

bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --alter --add-config errors.deadletterqueue.group.enable=true \
  --entity-type topics --entity-name dlq.image-jobs
```

Topic DLQ cần có tên bắt đầu bằng prefix DLQ được cluster cấu hình (mặc định `dlq.`). Nếu bật auto-create, cluster có thể tự gắn topic config cần thiết.

### 10.3. Nội dung DLQ

Mặc định, record DLQ có thể chỉ chứa metadata nguồn như group, topic, partition, offset và delivery count. Muốn copy key/value record gốc, bật group config:

```bash
bin/kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --alter --add-config errors.deadletterqueue.copy.record.enable=true \
  --entity-type groups --entity-name image-workers
```

DLQ không thay thế việc phân loại lỗi. Consumer DLQ cần quy trình điều tra, sửa dữ liệu và replay có kiểm soát. Bảo vệ DLQ bằng ACL và retention phù hợp vì payload có thể chứa dữ liệu nhạy cảm.

## 11. Khả năng hỗ trợ của client và framework

Không phải mọi Kafka client đều hỗ trợ Share Groups cùng thời điểm. Một thư viện hỗ trợ consumer group truyền thống không có nghĩa thư viện đó có share consumer API.

| Client/framework | Tình trạng theo tài liệu hiện hành | Cách tích hợp |
|---|---|---|
| Apache Kafka Java client | `KafkaShareConsumer`/`ShareConsumer` là API riêng; production-ready khi kết hợp broker hỗ trợ Share Groups (Kafka 4.2+) | Dùng trực tiếp `KafkaShareConsumer` |
| Spring Kafka 4.0 | Bắt đầu hỗ trợ Share Consumer | Dùng share consumer factory/container riêng; kiểm tra compatibility của broker |
| Spring Kafka 4.1 | Share Consumer được nâng lên production support cùng Apache Kafka 4.2 | Dùng `ShareConsumerFactory`, `ShareKafkaListenerContainerFactory` và `@KafkaListener` |
| librdkafka 2.15 | Share consumer ở trạng thái preview; public API C; chưa có C++ wrapper trong tài liệu hiện hành | Chỉ thử nghiệm theo giới hạn của release |
| Confluent Kafka Python 2.15 | Có `ShareConsumer` và `DeserializingShareConsumer` ở trạng thái preview, dựa trên librdkafka 2.15 | Chỉ thử nghiệm; không dùng production khi API còn preview |
| Wrapper ngôn ngữ dựa trên librdkafka | Phụ thuộc wrapper đã expose share API hay chưa | Kiểm tra đúng version và API surface của wrapper |
| Client vendor/khác | Không thể suy ra từ việc hỗ trợ Kafka protocol hoặc consumer group | Xác minh release note và test broker/client thực tế |

Share consumer của librdkafka là handle đơn luồng và không thread-safe; không gọi đồng thời nhiều thread trên cùng handle. Mỗi thread nên sở hữu một handle riêng hoặc tuần tự hóa mọi thao tác trên một handle. Preview API có thể thay đổi trước khi đạt GA.

Với Spring Boot, kiểm tra dependency management của đúng dòng Boot/Spring Framework trước khi nâng Spring Kafka lên 4.1. Không ép riêng version Spring Kafka vào ứng dụng cũ mà chưa xác minh ma trận tương thích; cần đồng bộ Spring Kafka, Spring Framework, Boot và Kafka client.

### 11.1. Java: không dùng `KafkaConsumer` thay thế

`KafkaConsumer` truyền thống thực hiện partition assignment và offset management. Share group dùng `KafkaShareConsumer`/`ShareConsumer` với record acknowledgment. Không cấu hình `group.protocol=share` trên consumer thường; `group.protocol` của consumer truyền thống có các giá trị protocol riêng và không phải công tắc chuyển sang share group.

### 11.2. Spring Kafka: cần factory/container riêng

Spring Kafka 4.1 cung cấp:

- `ShareConsumerFactory` và `DefaultShareConsumerFactory`.
- `ShareKafkaMessageListenerContainer`.
- `ShareKafkaListenerContainerFactory`.
- `ShareAcknowledgment` và các chế độ `EXPLICIT`, `MANUAL`, `IMPLICIT`.
- `ShareConsumerRecordRecoverer` để quyết định ACCEPT, RELEASE hoặc REJECT khi listener lỗi.

Không dùng `ConcurrentKafkaListenerContainerFactory` của consumer group thường để chạy share consumer. `@KafkaListener` phải trỏ đến `ShareKafkaListenerContainerFactory`.

### 11.3. Giới hạn cần biết trong Spring Kafka

Theo tài liệu Spring Kafka 4.1:

- Không hỗ trợ chỉ định partition thủ công bằng `TopicPartitionOffset`.
- Không hỗ trợ topic pattern subscription.
- Không hỗ trợ manual offset management như consumer group truyền thống.
- Không hỗ trợ batch listener cho Spring share container. Java `KafkaShareConsumer.poll()` vẫn trả về `ConsumerRecords` theo batch, nhưng acknowledgment được quản lý theo từng record.
- Share container dùng acknowledgment/recoverer riêng; không dùng `CommonErrorHandler` theo cách của partition-based consumer.
- Message converter có thể chưa được hỗ trợ trong share consumer container; kiểm tra tài liệu patch version trước khi thiết kế.

Nếu ứng dụng phụ thuộc vào các tính năng trên, cần kiểm tra giới hạn framework hoặc dùng Java ShareConsumer API trực tiếp.

## 12. Tích hợp Spring Kafka 4.1

### 12.1. Tạo ShareConsumerFactory

```java
@Configuration
public class ShareConsumerConfiguration {

    @Bean
    ShareConsumerFactory<String, String> shareConsumerFactory() {
        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092");
        props.put(ConsumerConfig.GROUP_ID_CONFIG,
            "order-workers");
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);

        return new DefaultShareConsumerFactory<>(props);
    }
}
```

`group.id` là định danh share group. Mọi consumer instance muốn cùng chia workload phải dùng cùng group ID và subscription phù hợp.

### 12.2. Tạo ShareKafkaListenerContainerFactory

```java
@Bean
ShareKafkaListenerContainerFactory<String, String>
shareKafkaListenerContainerFactory(
        ShareConsumerFactory<String, String> shareConsumerFactory) {

    ShareKafkaListenerContainerFactory<String, String> factory =
        new ShareKafkaListenerContainerFactory<>(shareConsumerFactory);

    factory.getContainerProperties().setShareAckMode(
        ContainerProperties.ShareAckMode.MANUAL);

    factory.getContainerProperties().setShareAcknowledgmentTimeout(
        Duration.ofSeconds(45));

    return factory;
}
```

`MANUAL` cho listener quyết định acknowledge, release hoặc reject từng record. Timeout giúp phát hiện record bị quên acknowledgment; nó không tự sửa logic xử lý bị treo.

### 12.3. Listener với acknowledgment thủ công

```java
@Component
public class OrderShareListener {

    @KafkaListener(
        topics = "orders",
        groupId = "order-workers",
        containerFactory = "shareKafkaListenerContainerFactory",
        concurrency = "8"
    )
    public void listen(
            ConsumerRecord<String, String> record,
            ShareAcknowledgment acknowledgment) {

        try {
            processOrder(record.value());
            acknowledgment.acknowledge();
        } catch (TemporaryDependencyException ex) {
            acknowledgment.release();
        } catch (InvalidOrderException ex) {
            acknowledgment.reject();
        }
    }
}
```

Trong MANUAL mode, mỗi record phải có một terminal acknowledgment (`acknowledge`, `release` hoặc `reject`). Có thể gọi `renew()` nhiều lần trước khi kết thúc nếu đang xử lý lâu và lock renewal được hỗ trợ. Nếu không acknowledge một record, poll tiếp theo của thread đó có thể bị chặn.

### 12.4. Concurrency của Spring share container

`concurrency=8` tạo tám share consumer member trong cùng container. Nếu chạy thêm ba application instance, mỗi instance cũng có concurrency 8, tổng số member trong cùng group có thể là 24.

Khác consumer group truyền thống, concurrency không chia partition độc quyền cho từng thread. Broker phân phối record theo share group và record lock. Tăng concurrency cần theo dõi broker coordinator, số record lock, downstream capacity và tốc độ xử lý thực tế.

### 12.5. Error handling riêng

Share container không dùng `CommonErrorHandler` của consumer group. Có thể cấu hình `ShareConsumerRecordRecoverer` để lỗi tạm thời RELEASE và lỗi vĩnh viễn REJECT:

```java
factory.setShareConsumerRecordRecoverer((record, exception) -> {
    if (exception instanceof TemporaryDependencyException) {
        return AcknowledgeType.RELEASE;
    }
    return AcknowledgeType.REJECT;
});
```

Recoverer mặc định của Spring Kafka 4.1 log lỗi và REJECT record; có thể chọn recoverer RELEASE mặc định hoặc custom recoverer như ví dụ để retry lỗi tạm thời. Đoạn code là ví dụ chính sách. Hãy xác minh signature và generic type của recoverer theo Spring Kafka version đang dùng. Broker delivery count vẫn giới hạn số lần giao lại để tránh poison message lặp vô hạn.

## 13. Kiểm tra client và broker trước khi triển khai

Thực hiện checklist sau trong staging:

1. Xác nhận broker version ở mốc hỗ trợ production Share Groups.
2. Kiểm tra `share.version` đã được finalized ở level cần thiết.
3. Kiểm tra `__share_group_state` được tạo và có replication/min ISR đúng.
4. Kiểm tra cluster đủ broker cho replication factor của state topic.
5. Kiểm tra client artifact có `KafkaShareConsumer` hoặc `ShareConsumerFactory` tương ứng.
6. Kiểm tra client/framework version tương thích với broker version.
7. Kiểm tra `group.id`, deserializer, security và ACL.
8. Kiểm tra share group lock duration, delivery count và record lock limit.
9. Kiểm tra `share.auto.offset.reset` để tránh bỏ qua backlog ngoài ý muốn.
10. Kiểm tra acknowledgment mode và xử lý mọi nhánh exception.
11. Kiểm tra poll interval, processing time và lock renewal.
12. Kiểm tra DLQ feature level nếu dùng DLQ tích hợp.
13. Chạy thử crash worker, lock expiry, RELEASE/REJECT và duplicate.
14. Kiểm tra ordering có phù hợp với semantics nghiệp vụ.

## 14. Vận hành share group bằng CLI

### 14.1. Liệt kê share group

```bash
bin/kafka-share-groups.sh --bootstrap-server kafka-1:9092 --list
```

### 14.2. Xem start offset và lag

```bash
bin/kafka-share-groups.sh --bootstrap-server kafka-1:9092 \
  --describe --group order-workers
```

`START-OFFSET` là offset sớm nhất của các record còn đang chờ xử lý trong group. Một số record phía sau start offset có thể đã được xử lý xong; không diễn giải nó như committed offset đơn giản của consumer group truyền thống.

### 14.3. Xem member và trạng thái group

```bash
bin/kafka-share-groups.sh --bootstrap-server kafka-1:9092 \
  --describe --group order-workers --members

bin/kafka-share-groups.sh --bootstrap-server kafka-1:9092 \
  --describe --group order-workers --state
```

Khi mô tả group, Admin client cần quyền DESCRIBE trên các topic mà group sử dụng. Cấp quyền phù hợp cho principal vận hành.

### 14.4. Reset share group offset

Luôn dry-run trước:

```bash
bin/kafka-share-groups.sh --bootstrap-server kafka-1:9092 \
  --reset-offsets --group order-workers --topic orders \
  --to-earliest --dry-run
```

Dừng các member của group và xác nhận group không còn xử lý record trước khi thực thi. Sau khi xác nhận phạm vi replay:

```bash
bin/kafka-share-groups.sh --bootstrap-server kafka-1:9092 \
  --reset-offsets --group order-workers --topic orders \
  --to-earliest --execute
```

Reset có thể khiến record được giao lại. Consumer cần idempotency và downstream phải chịu được replay.

### 14.5. Xóa share group

Chỉ share group không còn active member mới có thể bị xóa. Không xóa group chỉ để khắc phục một record lỗi; trước hết dùng acknowledgment, delivery policy, DLQ hoặc offset reset theo runbook.

## 15. Monitoring và troubleshooting

Theo dõi tối thiểu:

- Số member đang hoạt động trong share group.
- Share group state và assignment.
- Start offset và lag theo topic-partition.
- Số record acquired/in-flight nếu metric/version cung cấp.
- Delivery count, RELEASE, REJECT và redelivery rate.
- Lock expiry và record bị giao lại.
- Acknowledgment commit latency/failure.
- Poll latency, processing latency và heartbeat/session timeout.
- Coordinator state topic health, ISR và replication.
- DLQ volume nếu bật DLQ.
- Consumer throughput và downstream dependency latency.

### 15.1. Một số triệu chứng thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `UnsupportedVersionException` | Broker chưa hỗ trợ API/feature level | Kiểm tra broker version và `share.version` |
| Không tạo được `__share_group_state` | Cluster thiếu broker theo replication factor | Kiểm tra RF/min ISR; cluster nhỏ cần cấu hình trước khi dùng |
| Consumer không nhận record | `share.auto.offset.reset=latest`, group đã ở cuối log, ACL hoặc topic sai | Kiểm tra reset policy, group status, subscription và ACL |
| Record liên tục được giao lại | Lock hết hạn, worker crash hoặc RELEASE quá thường xuyên | Kiểm tra processing time, lock duration và downstream errors |
| Consumer poll trả ít/không có record | Đã chạm record lock limit hoặc nhiều record đang in-flight | Kiểm tra `share.partition.max.record.locks` và ack/lock expiry |
| `IllegalStateException` trước poll tiếp theo | Explicit mode còn record chưa được acknowledge | Bảo đảm mọi record của poll trước có ack terminal |
| Poison message bị xử lý nhiều lần | Dùng RELEASE cho lỗi vĩnh viễn hoặc delivery limit quá cao | Phân loại lỗi, REJECT lỗi vĩnh viễn và cấu hình DLQ phù hợp |
| Spring listener thread bị dừng | Listener exception/recoverer hoặc container không ở trạng thái mong đợi | Kiểm tra recoverer, lifecycle event và restart container theo hướng dẫn |
| Thứ tự side effect thay đổi | Nhiều member xử lý song song cùng partition | Dùng consumer group nếu cần ordering |
| DLQ không nhận record | Feature level chưa đạt 2 hoặc group/topic config thiếu | Kiểm tra `share.version`, group DLQ config và topic enable config |

### 15.2. Không dùng metric lag của consumer group như cùng một semantics

Share group không chỉ có một committed offset tuyến tính như consumer group truyền thống. Dùng `kafka-share-groups.sh --describe`, group state và các metric share-specific để đánh giá record còn chờ xử lý.

## 16. Bảo mật và ACL

Share consumer vẫn sử dụng các cơ chế bảo mật Kafka client như TLS, SASL và ACL. Cần kiểm tra:

- Principal có quyền READ trên topic.
- Principal có quyền phù hợp để tham gia và sử dụng share group.
- Admin principal có quyền DESCRIBE trên topic khi chạy lệnh describe.
- Principal vận hành có quyền quản trị group nếu cần alter/reset/delete.
- DLQ topic có ACL cho broker/client theo cơ chế DLQ của Kafka version.
- Không cấp quyền rộng cho ứng dụng chỉ để vượt qua lỗi authorization.

Khi dùng SASL/TLS, cấu hình tương tự các Kafka client khác. Share consumer không có một cơ chế xác thực riêng tách khỏi Kafka security model.

## 17. Khi nào nên dùng Share Group?

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Event theo đơn hàng cần giữ thứ tự `Created -> Paid -> Shipped` | Consumer group | Ordering theo partition/key quan trọng |
| Nhiều ảnh cần resize độc lập | Share group | Mỗi record là một job độc lập |
| Gửi email theo từng notification, không yêu cầu thứ tự toàn cục | Share group | Pool worker và retry theo record |
| Xử lý transaction log cần đảm bảo thứ tự theo key | Consumer group hoặc Kafka Streams | Cần semantics stream và ordering |
| Tác vụ gọi API bên ngoài có thời gian xử lý không đồng đều | Share group | Worker có thể xử lý record độc lập; RELEASE khi lỗi tạm thời |
| Batch ETL cần listener nhận và commit cả batch như một đơn vị | Consumer group hoặc công cụ batch phù hợp | Spring share container không có batch listener; Java share API trả batch nhưng acknowledge từng record |
| Xử lý record có side effect không idempotent và không thể deduplicate | Thiết kế lại trước khi dùng share group | Redelivery có thể lặp side effect |

Share Group hữu ích khi workload thực sự mang semantics queue. Không nên chuyển toàn bộ topic sang share group chỉ vì muốn tăng consumer count; hãy xác nhận ordering, retry, idempotency và framework support trước.

## 18. Các lỗi và anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách làm phù hợp |
|---|---|---|
| Dùng Kafka 4.1 preview cho production | Feature chưa đạt production support | Dùng Kafka 4.2+ patch phù hợp |
| Dùng `KafkaConsumer` và chỉ đổi `group.id` | Client vẫn chạy consumer group protocol | Dùng `KafkaShareConsumer` hoặc framework share consumer |
| Cho rằng `group.protocol=share` là cấu hình hợp lệ | Nhầm share group với consumer group protocol | Dùng API share consumer riêng |
| Dùng cùng group ID cho các workload muốn nhận bản sao độc lập | Các consumer chia nhau record thay vì mỗi bên nhận tất cả | Dùng share group ID riêng hoặc consumer group riêng |
| Dùng share group cho event cần ordering | Side effect có thể hoàn tất sai thứ tự | Dùng consumer group hoặc tuần tự hóa theo aggregate |
| Dùng implicit ack nhưng xử lý batch chưa xong đã poll tiếp | Record có thể bị acknowledge ngoài ý muốn | Dùng explicit/manual ack và hoàn tất mọi record |
| RELEASE mọi exception | Poison message bị retry nhiều lần | Phân loại transient/permanent, giới hạn delivery count |
| Để lock duration ngắn hơn thời gian xử lý bình thường | Record bị giao lại khi worker cũ vẫn chạy | Tuning lock hoặc renew khi hỗ trợ |
| Để lock duration quá dài | Worker chết khiến thời gian redelivery lâu | Chọn lock theo SLA và có renew/checkpoint |
| Không idempotent side effect | Duplicate delivery tạo dữ liệu hoặc thanh toán trùng | Event ID, inbox, idempotency key |
| Coi `acknowledge()` là đã commit ngay | Crash trước commit có thể redeliver | Commit và kiểm tra kết quả acknowledgment |
| Bỏ qua `__share_group_state` replication | Không tạo được group hoặc state coordinator kém bền vững | Cấu hình RF/min ISR theo cluster size |
| Dùng Spring `ConcurrentKafkaListenerContainerFactory` | Tạo consumer container sai loại | Dùng `ShareKafkaListenerContainerFactory` |
| Dùng `CommonErrorHandler` cho share container | Sai abstraction retry/seek/offset | Dùng `ShareConsumerRecordRecoverer` |
| Cho rằng mọi client Kafka hỗ trợ share group | Có thể gặp UnsupportedVersion hoặc thiếu API | Kiểm tra version/API của từng client |

## 19. Checklist production

- Broker version từ Kafka 4.2 trở lên và patch release đã kiểm tra.
- `share.version` đã finalized ở feature level cần thiết.
- Client library/framework có Share Consumer API tương thích.
- Không dùng `KafkaConsumer` truyền thống để kỳ vọng share semantics.
- `__share_group_state` có replication factor/min ISR phù hợp.
- Cluster ít hơn ba broker đã cấu hình state topic trước lần dùng đầu tiên.
- Share group ID ổn định và riêng cho từng logical workload.
- `share.auto.offset.reset` được chọn có chủ đích.
- Lock duration phù hợp với p95/p99 processing time.
- Delivery count limit và retry policy phù hợp với loại lỗi.
- `share.partition.max.record.locks` phù hợp với throughput và số record in-flight.
- Acknowledgment mode rõ ràng; mọi record đều có terminal acknowledgment.
- Có RENEW cho tác vụ dài nếu client/broker hỗ trợ.
- Handler idempotent hoặc có deduplication cho redelivery.
- `share.isolation.level` phù hợp với transactional producer upstream.
- DLQ chỉ được dùng khi feature level và group/topic config đáp ứng.
- Spring Kafka dùng share factory/container đúng loại nếu tích hợp Spring.
- Monitoring có group state, lag, delivery count, lock expiry, ack failure và DLQ.
- Đã kiểm thử worker crash, lock expiry, RELEASE, REJECT, duplicate và ordering.
- Có runbook reset offset, replay và xử lý poison message.

## 20. Câu hỏi tự kiểm tra

1. Share Group khác consumer group ở đơn vị phân phối công việc như thế nào?
2. Vì sao nhiều share consumer có thể cùng xử lý record từ một partition?
3. Kafka 4.1 và Kafka 4.2 khác nhau thế nào về trạng thái hỗ trợ Share Groups?
4. `share.version` dùng để làm gì và cần kiểm tra bằng công cụ nào?
5. `__share_group_state` lưu trạng thái gì và vì sao cần replication?
6. Vì sao cluster một hoặc hai broker có thể không tạo được internal state topic theo mặc định?
7. `share.record.lock.duration.ms` khác `share.session.timeout.ms` ở điểm nào?
8. `ACCEPT`, `RELEASE`, `REJECT` và `RENEW` khác nhau như thế nào?
9. Vì sao explicit acknowledgment thường phù hợp với xử lý theo từng record?
10. `share.acquire.mode=record_limit` khác `batch_optimized` ra sao?
11. Vì sao share group không bảo đảm thứ tự hoàn tất xử lý?
12. Tại sao side effect cần idempotent dù broker có record lock?
13. `share.auto.offset.reset` khác `auto.offset.reset` như thế nào?
14. Vì sao `KafkaShareConsumer` là API riêng thay vì một chế độ của `KafkaConsumer`?
15. Spring Kafka cần factory/container nào để dùng share consumer?
16. Vì sao `CommonErrorHandler` không phải abstraction xử lý lỗi của share container?
17. Điều kiện để dùng DLQ tích hợp trong Kafka 4.4 là gì?
18. Những metric nào giúp phát hiện record bị redeliver hoặc lock hết hạn?

## 21. Tài liệu tham khảo

- Apache Kafka 4.4 — [KafkaShareConsumer Java API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/KafkaShareConsumer.html)
- Apache Kafka 4.4 — [Consumer and Share Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/)
- Apache Kafka 4.4 — [Group Configs](https://kafka.apache.org/44/configuration/group-configs/)
- Apache Kafka 4.4 — [Broker Configs](https://kafka.apache.org/44/configuration/broker-configs/)
- Apache Kafka — [Upgrading to Kafka 4.2 and Share Groups production readiness](https://kafka.apache.org/42/getting-started/upgrade/)
- Apache Kafka 4.4 — [Managing Share Groups and configuring DLQ](https://kafka.apache.org/44/operations/basic-kafka-operations/)
- Spring Kafka — [Kafka Queues (Share Consumer)](https://docs.spring.io/spring-kafka/reference/kafka/kafka-queues.html)
- Spring Kafka — [What's New in 4.1](https://docs.spring.io/spring-kafka/reference/whats-new.html)
- librdkafka — [Share consumer support and limitations](https://github.com/confluentinc/librdkafka/blob/master/INTRODUCTION.md)
- Confluent Kafka Python — [Share Consumer preview in 2.15](https://github.com/confluentinc/confluent-kafka-python/blob/master/CHANGELOG.md)

## Kết luận

Share Groups bổ sung cách phân phối record theo kiểu queue trong Kafka: nhiều consumer cùng group có thể nhận record từ một partition, broker quản lý record lock và ứng dụng xác nhận kết quả bằng ACCEPT, RELEASE, REJECT hoặc RENEW. Để dùng ổn định, phải kiểm tra broker feature level, internal state topic, broker/group/client config và API hỗ trợ của framework. Kafka 4.2 là mốc production-ready; Spring Kafka 4.1 hỗ trợ share consumer production cùng Kafka 4.2. Share Group phù hợp với công việc độc lập cần retry theo record, nhưng không thay thế consumer group khi nghiệp vụ cần ordering theo partition. Idempotency, lock tuning, delivery limit, monitoring và DLQ là các phần cần thiết của một triển khai production.

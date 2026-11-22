# Phân biệt position, committed offset và end offset

## 1. Vì sao cần phân biệt ba mốc offset?

Khi một Kafka consumer đọc partition, có ba mốc thường được dùng để mô tả tiến độ:

- **Position**: vị trí đọc hiện tại của consumer instance; cho biết offset tiếp theo mà consumer sẽ lấy khi poll.
- **Committed offset**: vị trí đọc đã được lưu cho consumer group; consumer có thể tiếp tục từ đây sau restart hoặc rebalance.
- **End offset**: ranh giới cuối của dữ liệu mà consumer có thể đọc trong partition theo isolation level đang dùng.

Ba giá trị này phục vụ ba mục đích khác nhau. Position phản ánh tiến độ đọc trong bộ nhớ của consumer hiện tại; committed offset phản ánh tiến độ đã lưu bền vững cho group; end offset phản ánh mốc dữ liệu hiện có để đọc. Nhầm lẫn chúng dễ dẫn đến kết luận sai về consumer lag, xử lý lặp hoặc mất record.

Trong Spring Kafka, `@KafkaListener` được listener container gọi sau khi Kafka consumer poll record. Container quản lý position và commit theo `AckMode`; ứng dụng thường quan sát offset của từng record qua header hoặc metadata. Hiểu các khái niệm nền của Kafka Consumer giúp đọc đúng trạng thái của listener khi vận hành.

## 2. Position là gì?

`position` là offset tiếp theo mà một Kafka consumer sẽ đọc từ một `TopicPartition`. Khi consumer poll và nhận các record có offset `100`, `101`, `102`, position thường tiến đến `103` sau khi các record đó được trả về từ `poll()`.

Position thuộc trạng thái runtime của một consumer instance. Nó có thể thay đổi khi:

- Consumer gọi `poll()` và nhận thêm record.
- Ứng dụng gọi `seek()` để chuyển vị trí đọc.
- Consumer được gán partition sau khi tham gia group và khôi phục vị trí bắt đầu.
- Consumer được gán lại partition sau rebalance.

Position không tự động có nghĩa là các record trước đó đã được xử lý nghiệp vụ thành công. `poll()` có thể trả về nhiều record và làm position tiến lên trước khi ứng dụng hoàn tất xử lý tất cả record trong batch. Nếu ứng dụng commit position lúc còn record chưa xử lý, những record đó có thể bị bỏ qua sau khi restart.

Ví dụ:

```text
Partition orders-0

Offset:       100   101   102   103   104   105
              [A]   [B]   [C]   [D]   [E]   [F]
                       poll() trả về A, B, C
                                      |
                                      v
                               position = 103
```

Position `103` có nghĩa lần đọc tiếp theo bắt đầu từ mốc `103`. Nó không có nghĩa offset `100` đến `102` đã được commit cho group. Việc xử lý nghiệp vụ và commit là hai bước khác nhau.

### Position có phải offset của record cuối cùng đã đọc?

Không. Position là offset kế tiếp, không phải offset của record cuối cùng. Nếu record cuối cùng được trả về có offset `102`, position thường là `103`. Tuy nhiên, offset có thể có khoảng trống do log compaction, transaction marker hoặc record không được trả về cho consumer theo isolation level; vì vậy không phải lúc nào offset kế tiếp cũng bằng offset record cuối cùng cộng đúng một theo số lượng record quan sát được.

## 3. Committed offset là gì?

Committed offset là vị trí tiếp theo mà một consumer group đã lưu cho từng partition. Kafka lưu thông tin này trong cơ chế quản lý offset của group, độc lập với bộ nhớ của consumer instance.

Ví dụ consumer xử lý thành công record offset `102`, sau đó commit offset `103`:

```text
Record cuối cùng đã xử lý: 102
Committed offset:          103
Khi đọc tiếp:              bắt đầu từ offset 103
```

Committed offset được quản lý theo cặp consumer group và partition. Hai group khác nhau có thể đọc cùng topic nhưng có committed offset khác nhau. Khi một consumer instance dừng và instance khác tiếp nhận partition, consumer mới khôi phục tiến độ từ committed offset của group.

Nếu group chưa có committed offset cho partition, Kafka áp dụng `auto.offset.reset` để chọn vị trí bắt đầu. Nếu committed offset không còn hợp lệ, ví dụ nằm trước beginning offset do retention đã xóa dữ liệu cũ, chính sách reset cũng có thể được áp dụng tùy cấu hình. `auto.offset.reset` không ghi đè một committed offset còn hợp lệ.

### Commit offset không phải là xử lý record

Kafka không tự biết database update hay thao tác nghiệp vụ của listener đã thành công. Ứng dụng hoặc listener container quyết định thời điểm commit. Nếu commit trước khi xử lý hoàn tất, ứng dụng có nguy cơ mất xử lý. Nếu xử lý xong nhưng dừng trước commit, record có thể được giao lại và tạo tác dụng phụ trùng lặp.

Vì vậy, các consumer nghiệp vụ thường thiết kế theo hướng at-least-once: xử lý thành công rồi commit, đồng thời bảo đảm handler idempotent để chịu được việc giao lại.

## 4. End offset là gì?

End offset là ranh giới cuối của dữ liệu trong một partition, được biểu diễn bằng offset kế tiếp sau vùng dữ liệu mà consumer có thể đọc. Nếu end offset là `106`, vùng offset trước mốc đó có thể chứa các record có offset nhỏ hơn `106`, tùy retention, compaction và isolation level.

End offset không phải offset của record cuối cùng. Nếu record cuối cùng có offset `105`, end offset thường là `106`. Đây là một ranh giới dùng để xác định dữ liệu còn ở phía trước consumer và tính lag.

Có thể lấy end offset bằng Kafka Consumer API:

```java
Map<TopicPartition, Long> endOffsets =
        consumer.endOffsets(Set.of(topicPartition));

Long endOffset = endOffsets.get(topicPartition);
```

Lệnh này truy vấn end offset của partition, không phải thao tác đọc record và không tự thay đổi position của consumer.

### Beginning offset và retention

Partition còn có beginning offset, là offset nhỏ nhất còn được lưu để consumer có thể đọc. Khi retention xóa các segment cũ hoặc log compaction loại bỏ record cũ, beginning offset có thể tiến lên. Vì vậy, không nên giả định partition luôn bắt đầu từ offset `0` hoặc mọi offset lịch sử vẫn còn.

Khoảng đọc có thể hình dung như sau:

```text
Beginning offset                         End offset
       |                                      |
       v                                      v
       40  41  42  43  44  45  46  47  48  49
       |<--------- dữ liệu còn đọc ---------->|
```

Nếu committed offset của group nhỏ hơn beginning offset, consumer không thể đọc lại phần dữ liệu đã bị xóa. Kafka xử lý offset out of range theo `auto.offset.reset` như `earliest`, `latest` hoặc `none`.

## 5. Phân biệt LEO, high watermark và last stable offset

Khi nói về end offset, cần biết Kafka có nhiều ranh giới liên quan đến replication và transaction:

| Mốc | Ý nghĩa |
|---|---|
| Log End Offset (LEO) | Offset kế tiếp mà leader partition sẽ gán cho record mới; phản ánh cuối log trên leader |
| High watermark (HW) | Ranh giới dữ liệu đã được sao chép đủ theo cơ chế replication; consumer thông thường không đọc vượt qua HW |
| Last Stable Offset (LSO) | Ranh giới đọc ổn định cho consumer `read_committed`; giao dịch chưa kết thúc có thể làm LSO thấp hơn HW |

LEO có thể lớn hơn HW khi leader đã ghi record nhưng follower chưa sao chép kịp. Với consumer `isolation.level=read_uncommitted`, vùng đọc khả dụng được giới hạn theo high watermark. Với `isolation.level=read_committed`, consumer chỉ đọc các record thuộc transaction đã commit và không đọc vượt qua last stable offset.

Do đó, end offset mà consumer API cung cấp phụ thuộc isolation level: với `read_uncommitted`, mốc này dựa trên HW; với `read_committed`, mốc này dựa trên LSO. Khi có transaction đang mở, LSO có thể thấp hơn HW. Đây là lý do một consumer `read_committed` có thể chưa nhìn thấy record mà leader đã ghi.

```text
LEO       = 120   leader đã gán offset tiếp theo là 120
HW        = 118   consumer read_uncommitted đọc đến ranh giới 118
LSO       = 115   consumer read_committed đọc đến ranh giới 115

Vùng offset 115..117 có thể đang bị chặn bởi transaction chưa kết thúc.
```

Các giá trị trên chỉ minh họa ranh giới. End offset không phải số record đã được xử lý và không nên đồng nhất với LEO trong mọi ngữ cảnh.

## 6. So sánh position, committed offset và end offset

| Tiêu chí | Position | Committed offset | End offset |
|---|---|---|---|
| Phạm vi | Một consumer instance và partition được gán | Một consumer group và partition | Một partition, theo isolation level của consumer truy vấn |
| Nơi lưu | Trạng thái runtime của consumer | Kafka lưu bền vững cho group | Được xác định từ log/replication/transaction state |
| Ý nghĩa | Offset tiếp theo consumer sẽ đọc | Offset tiếp theo group đã lưu để khôi phục | Ranh giới cuối dữ liệu consumer có thể đọc |
| Thay đổi bởi | `poll()`, `seek()`, assignment | Commit offset của group | Record mới, replication, transaction completion, retention/truncation |
| Có chứng minh nghiệp vụ đã xử lý? | Không | Chỉ phản ánh ứng dụng đã commit theo chính sách của nó | Không |
| Dùng để | Theo dõi tiến độ đọc hiện tại | Khôi phục sau restart/rebalance và tính group lag | Xác định dữ liệu phía trước và tính lag |

Ví dụ một partition có:

```text
committed offset = 41
position         = 45
end offset       = 52
```

Có thể diễn giải:

- Group đã lưu tiến độ để lần đọc tiếp theo bắt đầu từ offset `41`.
- Consumer hiện tại đã poll đến vị trí tiếp theo là `45`.
- Consumer còn cách end offset `7` đơn vị offset theo ranh giới đang quan sát.
- Khoảng từ committed offset đến position là `4` đơn vị offset chưa được lưu commit; các record trong khoảng này có thể đang được xử lý hoặc đã xử lý nhưng chưa commit.

Không được diễn giải các phép trừ này thành số record chính xác trong mọi trường hợp. Log compaction, transaction marker và offset gap có thể khiến khoảng offset khác với số record thực tế.

## 7. Consumer lag được tính như thế nào?

Consumer lag mô tả khoảng cách giữa tiến độ đọc của consumer group và dữ liệu hiện có ở cuối partition. Cách tính phổ biến ở cấp group là:

\[
\text{Committed lag} = \text{End offset} - \text{Committed offset}
\]

Để xem tiến độ của consumer instance hiện tại, có thể dùng:

\[
\text{Position lag} = \text{End offset} - \text{Position}
\]

Hai giá trị trả lời hai câu hỏi khác nhau:

- Committed lag: group còn cách end offset bao xa nếu tính từ tiến độ đã lưu bền vững?
- Position lag: consumer instance hiện tại còn cách end offset bao xa nếu tính từ vị trí đọc trong bộ nhớ?

Ví dụ `committed=41`, `position=45`, `end=52`:

| Chỉ số | Phép tính | Kết quả |
|---|---:|---:|
| Committed lag | 52 - 41 | 11 |
| Position lag | 52 - 45 | 7 |
| Position chưa commit so với committed | 45 - 41 | 4 |

Committed lag lớn hơn position lag có thể là bình thường khi consumer đã poll record nhưng chưa commit. Nếu listener xử lý bất đồng bộ, khoảng cách này có thể bao gồm record đang chờ hoàn tất. Nếu commit quá thường xuyên, chi phí commit tăng; nếu commit quá thưa, committed lag có thể lớn dù listener đã xử lý phần lớn record.

Lag thường được biểu diễn bằng offset distance, không nhất thiết là số lượng message chính xác. Với topic compacted hoặc luồng có transaction, offset có thể bị bỏ trống hoặc record bị ẩn theo isolation level.

## 8. Quan sát ba mốc bằng Kafka Consumer API

Kafka Java Consumer cung cấp các API để kiểm tra position, committed offset và end offset. Ví dụ dưới đây dùng `assign()` để kiểm tra trực tiếp một partition cụ thể:

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-monitor");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

TopicPartition partition = new TopicPartition("orders", 0);

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    // assign() gán partition trực tiếp, không dùng subscribe() trong ví dụ này.
    consumer.assign(List.of(partition));

    long position = consumer.position(partition);

    Map<TopicPartition, OffsetAndMetadata> committedOffsets =
            consumer.committed(Set.of(partition));
    OffsetAndMetadata committed = committedOffsets.get(partition);

    Map<TopicPartition, Long> endOffsets =
            consumer.endOffsets(Set.of(partition));
    long endOffset = endOffsets.get(partition);

    System.out.println("Position: " + position);
    System.out.println("Committed: "
            + (committed == null ? "none" : committed.offset()));
    System.out.println("End offset: " + endOffset);
}
```

`assign()` dùng để gán partition thủ công cho consumer; ví dụ này không tham gia cơ chế tự động phân phối partition của group bằng `subscribe()`. Consumer vẫn có thể truy vấn committed offset theo `group.id`, nhưng ví dụ chỉ quan sát và không commit. Trong ứng dụng thật, không để một consumer monitor tùy tiện commit hoặc seek trên cùng group khi consumer nghiệp vụ đang hoạt động.

Nếu dùng `subscribe()`, consumer phải gọi `poll()` để tham gia group và nhận assignment trước khi truy vấn `position()` cho partition. Không gọi `position()` trên partition chưa được gán cho consumer.

### Seek thay đổi position

`seek()` chuyển position của consumer đến một offset cụ thể:

```java
consumer.seek(partition, 100L);
long position = consumer.position(partition); // 100
```

Thao tác này thay đổi vị trí đọc trong consumer hiện tại. Nó không tự ghi committed offset cho group. Nếu consumer dừng trước khi commit vị trí mới, lần khởi động sau có thể tiếp tục từ committed offset cũ. Nếu muốn lưu vị trí đã seek, cần commit offset theo quy tắc phù hợp.

## 9. Quan sát offset của record trong Spring Kafka

Với `@KafkaListener`, ứng dụng thường cần biết record đang xử lý thuộc topic, partition nào và có offset bao nhiêu. Spring Kafka ánh xạ thông tin này thành message header:

```java
@Component
public class OrderListener {

    @KafkaListener(topics = "orders", groupId = "order-service")
    public void onOrder(
            OrderCreated event,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
            @Header(KafkaHeaders.OFFSET) long offset) {

        log.info("Received orderId={}, topic={}, partition={}, offset={}",
                event.orderId(), topic, partition, offset);
    }
}
```

Các header trên cho biết offset của record cụ thể được listener nhận. Chúng không phải position hiện tại của consumer và cũng không phải committed offset của group.

Nếu cần kiểm soát commit, cấu hình listener container qua `AckMode` và sử dụng `Acknowledgment` khi chọn chế độ manual. Không dùng offset header của record cuối cùng trong batch để commit tùy tiện nếu còn record trước đó chưa xử lý xong hoặc xử lý song song chưa hoàn tất.

## 10. Quan sát group offset bằng Kafka CLI

Lệnh `kafka-consumer-groups.sh --describe` cho biết tiến độ đọc của consumer group theo từng partition:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
```

Các cột thường gặp:

| Cột | Ý nghĩa |
|---|---|
| `CURRENT-OFFSET` | Committed offset hiện được lưu cho group/partition |
| `LOG-END-OFFSET` | End offset mà công cụ sử dụng để so sánh tiến độ với cuối log |
| `LAG` | Khoảng cách giữa log end offset và committed offset theo cách tính của công cụ |
| `CONSUMER-ID` / `HOST` | Consumer instance đang được gán partition, nếu có |

Ví dụ minh họa:

```text
GROUP         TOPIC   PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
order-service orders  0          41               52              11
order-service orders  1          80               80              0
order-service orders  2          25               40              15
```

Partition 1 không có lag theo offset tại thời điểm quan sát. Partition 0 và 2 còn khoảng cách tương ứng 11 và 15. Đây là ảnh chụp trạng thái tại một thời điểm; lag có thể tăng khi producer ghi nhanh hơn consumer hoặc giảm khi consumer xử lý bắt kịp.

CLI hiển thị committed offset của group, không phải position runtime mới nhất của consumer. Vì vậy, `LAG` có thể lớn hơn số record thực sự còn chưa được listener poll nếu có record đã poll/đang xử lý nhưng chưa commit.

## 11. Ảnh hưởng của AckMode và auto-commit

Trong Spring Kafka, listener container thường quản lý commit offset. Từ Spring Kafka 2.3, framework tự đặt `enable.auto.commit=false` nếu ứng dụng chưa cấu hình rõ thuộc tính này, để container kiểm soát commit theo `AckMode`.

| AckMode | Ảnh hưởng đến committed offset |
|---|---|
| `RECORD` | Commit sau khi listener xử lý thành công từng record |
| `BATCH` | Commit sau khi các record trong batch poll được xử lý thành công |
| `TIME`, `COUNT`, `COUNT_TIME` | Commit các offset đã xử lý khi đạt ngưỡng thời gian/số lượng tương ứng |
| `MANUAL` | Listener gọi `acknowledge()`; container xử lý commit theo cơ chế manual/batch |
| `MANUAL_IMMEDIATE` | Commit ngay khi acknowledge được gọi trên consumer thread |

Position có thể tiến lên sau poll trong khi committed offset vẫn giữ nguyên. Đây là hành vi bình thường với `BATCH` hoặc `MANUAL`. Nếu listener xử lý bất đồng bộ, cần bảo đảm chỉ commit đến offset liên tục đã hoàn tất trong từng partition. Không commit vượt qua một record chưa xử lý chỉ vì position đã tiến lên.

Ví dụ: poll trả về offset `10`, `11`, `12`; ứng dụng xử lý xong `10` và `12` nhưng `11` còn đang chạy. Không thể commit `13` an toàn vì khi restart, record `11` sẽ bị bỏ qua. Offset commit phải phản ánh ranh giới liên tục đã xử lý thành công, trong trường hợp này nhiều nhất là `11` (vị trí tiếp theo sau offset `10`).

## 12. Những tình huống dễ gây hiểu nhầm

### Position lớn hơn committed offset

Đây là tình huống phổ biến. Consumer đã poll record nhưng chưa đến thời điểm commit theo `AckMode`, hoặc ứng dụng đang xử lý batch. Nếu instance dừng trước commit, các record đó có thể được giao lại.

### Committed offset bằng end offset

Group đã commit đến ranh giới cuối hiện tại. Nếu producer ghi thêm record, end offset tăng và lag có thể xuất hiện. Bằng nhau tại một thời điểm không có nghĩa topic sẽ không có record mới.

### Committed offset nhỏ hơn beginning offset

Dữ liệu cũ mà group muốn đọc có thể đã bị retention xóa. Consumer gặp offset out of range và hành vi tiếp theo phụ thuộc `auto.offset.reset`. `earliest` chỉ có nghĩa đọc từ beginning offset còn tồn tại, không khôi phục dữ liệu đã bị xóa.

### End offset lớn hơn position nhưng listener không thấy record

Cần kiểm tra consumer có được gán partition đúng không, có đang pause không, `isolation.level` là gì, có transaction đang mở không, record có bị filter/compaction không và deserializer có lỗi không. End offset chỉ là ranh giới; nó không bảo đảm mọi offset bên dưới đều có record được trả cho listener.

### Lag tăng dù listener vẫn xử lý

Producer có thể đang ghi nhanh hơn tốc độ xử lý, batch đang chờ commit, consumer bị rebalance hoặc một partition nóng làm tiến độ group không đồng đều. Cần xem lag từng partition, position, committed offset, throughput và thời gian xử lý thay vì chỉ nhìn một con số tổng.

## 13. Kiểm thử position, committed offset và end offset

Kiểm thử tích hợp nên xác minh mối quan hệ giữa ba mốc sau các thao tác cụ thể:

1. Tạo topic có một partition và gửi một số record đã biết.
2. Gán consumer group mới, cấu hình `auto.offset.reset=earliest` và xác nhận vị trí bắt đầu ở beginning offset còn tồn tại.
3. Poll một batch, kiểm tra position tiến lên trong khi committed offset chưa đổi nếu chưa commit.
4. Xử lý xong batch và commit, sau đó xác nhận committed offset bằng vị trí kế tiếp cần đọc.
5. Dừng consumer và tạo instance khác cùng group; xác nhận consumer mới tiếp tục từ committed offset.
6. Dùng `seek()` để thay đổi position, xác nhận committed offset không đổi cho đến khi commit.
7. Gửi thêm record và kiểm tra end offset tăng; xác nhận lag được tính lại.
8. Nếu dùng transaction, kiểm tra khác biệt giữa `read_uncommitted` và `read_committed` khi có transaction đang mở hoặc bị abort.

Với Spring Kafka, có thể dùng `spring-kafka-test` hoặc Kafka test starter tương ứng với dòng Spring Boot. Để kiểm tra rebalance, retention và transaction isolation sát thực tế, nên bổ sung bài kiểm thử với broker/container phù hợp phiên bản Kafka đang triển khai.

## 14. Tổng kết

- Position là offset tiếp theo mà consumer instance hiện tại sẽ đọc; nó thay đổi theo poll, seek và assignment.
- Committed offset là offset tiếp theo được lưu bền vững cho consumer group và partition; nó dùng để khôi phục sau restart/rebalance.
- End offset là ranh giới cuối dữ liệu consumer có thể đọc; không phải offset của record cuối cùng.
- LEO, high watermark và last stable offset là các ranh giới khác nhau; isolation level ảnh hưởng đến end offset consumer nhìn thấy.
- Committed lag và position lag phản ánh hai loại tiến độ khác nhau; khoảng cách offset không luôn bằng số record chính xác.
- Spring Kafka listener container quản lý commit theo `AckMode`; position có thể tiến trước committed offset.
- `@KafkaListener` có thể nhận topic, partition và offset của record qua `KafkaHeaders`, nhưng các header đó không phải committed offset.

Khi đọc được ba mốc position, committed offset và end offset, đội ngũ có thể phân biệt consumer đã poll đến đâu, group đã lưu tiến độ đến đâu và dữ liệu còn ở phía trước bao nhiêu. Đây là cơ sở để chẩn đoán consumer lag, kiểm soát commit và vận hành luồng messaging Spring Kafka đáng tin cậy.

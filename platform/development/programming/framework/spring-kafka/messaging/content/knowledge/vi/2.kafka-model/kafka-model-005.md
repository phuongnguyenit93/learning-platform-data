# Offset và vị trí đọc

Trong Kafka, consumer không đọc một topic như một danh sách duy nhất. Mỗi topic được chia thành các partition; mỗi partition là một log có thứ tự riêng và mỗi record trong log có một **offset**. Consumer dùng offset để xác định vị trí cần đọc tiếp, còn consumer group lưu **committed offset** để biết nên tiếp tục từ đâu sau khi consumer khởi động lại hoặc partition được giao cho consumer khác.

Hiểu đúng các mốc này giúp kiểm soát việc đọc lại sự kiện, tránh bỏ sót dữ liệu và giải thích được vì sao một record có thể được xử lý nhiều lần.

## 1. Offset là vị trí trong một partition

Kafka gán offset cho record khi record được ghi vào partition. Offset bắt đầu từ 0 trong một log mới và tăng theo thứ tự ghi của partition đó. Ví dụ, topic `orders` có hai partition:

| Partition | Một số offset | Ý nghĩa |
|---|---:|---|
| `orders-0` | 0, 1, 2, 3, ... | Thứ tự record trong partition 0 |
| `orders-1` | 0, 1, 2, 3, ... | Thứ tự record trong partition 1 |

Offset chỉ có ý nghĩa khi đi cùng topic và partition. `orders-0` offset `12` và `orders-1` offset `12` là hai vị trí khác nhau. Vì vậy, không thể dùng một offset đơn lẻ để định danh duy nhất một record trên toàn bộ cluster.

Một vài hệ quả quan trọng:

- Thứ tự được đảm bảo bên trong từng partition. Kafka không cung cấp một thứ tự tổng thể giữa các partition của cùng topic.
- Offset là vị trí trong log, không phải số thứ tự nghiệp vụ, thời điểm tạo sự kiện hay ID đơn hàng.
- Offset được cấp khi record được ghi vào partition. Việc xóa record cũ do retention hoặc compaction không làm các offset phía sau đánh lại từ đầu.
- Các record consumer nhìn thấy không nhất thiết có offset liên tiếp. Compaction có thể loại bỏ record cũ; consumer dùng `read_committed` cũng bỏ qua record thuộc transaction đã abort.

Nếu ứng dụng cần định danh sự kiện ổn định qua nhiều lần gửi hoặc qua nhiều topic, hãy dùng một trường như `eventId` trong payload. Không dùng offset thay cho ID nghiệp vụ.

## 2. Phân biệt ba mốc vị trí

Khi theo dõi một partition, cần phân biệt **log end offset**, **consumer position** và **committed offset**. Cả ba đều liên quan đến offset nhưng trả lời ba câu hỏi khác nhau.

| Mốc | Nó biểu thị điều gì? | Thường thay đổi khi nào? |
|---|---|---|
| Log end offset | Vị trí cuối hiện có của log; thường được biểu diễn bằng offset kế tiếp sẽ được cấp cho record mới | Khi producer ghi thêm record |
| Consumer position | Offset kế tiếp mà consumer sẽ lấy khi đọc tiếp | Khi `poll()` trả record hoặc khi ứng dụng chủ động `seek()` |
| Committed offset | Điểm tiếp tục đã được lưu bền vững cho một consumer group | Khi consumer/container commit offset |

Ví dụ, partition có các record từ offset `100` đến `103`. Một lần `poll()` đã trả các record `102` và `103`; ứng dụng mới xử lý thành công đến offset `101`:

| Giá trị | Ví dụ | Cách hiểu |
|---|---:|---|
| Log end offset | 104 | Record tiếp theo được ghi sẽ nhận offset 104 |
| Consumer position | 104 | Consumer đã lấy dữ liệu đến hết lần poll này; lần đọc tiếp theo bắt đầu tại vị trí 104 |
| Committed offset | 102 | Nếu consumer dừng lúc này, group sẽ tiếp tục từ offset 102 |

Điểm dễ nhầm là `poll()` có thể đưa consumer position đi trước tiến độ xử lý nghiệp vụ. Consumer đã nhận record không có nghĩa ứng dụng đã xử lý thành công record đó. Nếu commit `104` trong khi record `102` và `103` chưa được xử lý, lần khởi động sau sẽ bắt đầu từ `104` và có thể bỏ qua hai record này.

## 3. Committed offset là điểm bắt đầu tiếp theo

Kafka lưu offset theo khóa gồm **consumer group + topic + partition**. Dữ liệu commit được quản lý nội bộ trong topic `__consumer_offsets`. Mỗi consumer group có tiến độ độc lập: hai group cùng đọc `orders` có thể đang ở hai offset khác nhau mà không ảnh hưởng lẫn nhau.

Giá trị commit biểu thị **offset kế tiếp cần đọc**, không phải offset của record vừa xử lý xong. Nếu ứng dụng xử lý thành công record có offset `41`, nó cần commit `42` để lần đọc sau bắt đầu ở `42`.

Quy tắc này cũng giải thích hành vi khi có sự cố:

1. Consumer đọc record `41`.
2. Ứng dụng xử lý record thành công.
3. Consumer commit offset `42`.
4. Consumer dừng hoặc partition được chuyển sang consumer khác.
5. Consumer tiếp quản đọc từ offset `42`.

Nếu ứng dụng đã xử lý `41` nhưng dừng trước khi commit `42`, Kafka vẫn xem `41` là chưa được xác nhận. Consumer tiếp theo có thể đọc lại record đó. Đây là lý do handler cần có khả năng xử lý lặp an toàn (idempotent) khi hệ thống vận hành theo kiểu at-least-once.

## 4. Commit offset và khả năng giao nhận

Thời điểm commit quyết định điều gì có thể xảy ra khi tiến trình gặp lỗi:

| Thứ tự | Rủi ro khi tiến trình dừng giữa chừng | Hành vi thường thấy |
|---|---|---|
| Commit trước, xử lý sau | Offset đã tiến lên nhưng nghiệp vụ chưa hoàn tất | Có thể mất xử lý đối với record đã commit |
| Xử lý thành công trước, commit sau | Nghiệp vụ đã hoàn tất nhưng offset chưa được lưu | Record có thể được giao lại và xử lý trùng |

Với xử lý sự kiện thông thường, ưu tiên hoàn tất tác động nghiệp vụ rồi mới xác nhận offset. Cách này hỗ trợ at-least-once: record chưa được xác nhận có thể được giao lại, nên handler phải chịu được việc lặp. Có thể dùng `eventId` duy nhất, ràng buộc unique trong database, thao tác upsert hoặc bảng ghi nhận sự kiện đã xử lý để chống tác động trùng.

Kafka transaction có thể phối hợp việc ghi record đầu ra và commit offset đầu vào trong cùng một transaction Kafka. Đây là nền tảng cho luồng consume-transform-produce có exactly-once semantics trong phạm vi Kafka. Nếu handler còn ghi sang một database hoặc gọi một hệ thống bên ngoài, transaction Kafka không tự động làm cho tác động bên ngoài đó exactly-once; cần thiết kế idempotency, outbox hoặc cơ chế phối hợp phù hợp.

## 5. Chọn vị trí bắt đầu bằng `auto.offset.reset`

Khi consumer group chưa có committed offset hợp lệ cho partition, Kafka cần một chính sách để xác định vị trí bắt đầu. Cấu hình `auto.offset.reset` quyết định hành vi đó:

| Giá trị | Hành vi |
|---|---|
| `earliest` | Bắt đầu từ offset sớm nhất hiện còn trong log |
| `latest` | Bắt đầu từ cuối log tại thời điểm khởi tạo vị trí đọc; record cũ hơn có thể bị bỏ qua đối với group mới |
| `none` | Báo lỗi nếu không tìm thấy committed offset hợp lệ |

`auto.offset.reset` **không ghi đè một committed offset vẫn còn hợp lệ** mỗi lần ứng dụng khởi động. Nó chỉ được dùng khi group chưa có offset hoặc offset đã lưu không còn hợp lệ, chẳng hạn offset nằm trước phần log còn được giữ lại. Do đó, đổi `earliest` sang `latest` không tự đưa một group đang hoạt động đến cuối topic nếu group đó đã có offset hợp lệ.

Ví dụ cấu hình consumer Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      group-id: billing-v1
      auto-offset-reset: earliest
      enable-auto-commit: false
    listener:
      ack-mode: record
```

Ở đây:

- `group-id` xác định tiến độ đọc độc lập của consumer group.
- `auto-offset-reset: earliest` yêu cầu đọc từ phần dữ liệu sớm nhất còn được giữ nếu group chưa có offset hợp lệ.
- `enable-auto-commit: false` để Spring Kafka container quản lý việc commit theo acknowledgement mode. Từ Spring Kafka 2.3, framework mặc định đặt `enable.auto.commit` thành `false` nếu ứng dụng chưa cấu hình thuộc tính này; khai báo rõ trong ví dụ giúp ý định dễ nhận biết.
- `ack-mode: record` yêu cầu container commit sau khi listener xử lý xong từng record.

Đổi `group-id` tạo một tiến độ đọc riêng. Đây là cách hữu ích để chạy một consumer mới và đọc lại dữ liệu theo chính sách reset, nhưng cần tính trước tác động nghiệp vụ của việc replay.

## 6. Spring Kafka quản lý offset như thế nào?

Với `@KafkaListener`, Spring Kafka thường quản lý consumer và commit offset thông qua listener container. Listener có thể nhận `ConsumerRecord` để đọc metadata của record:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(topics = "orders", groupId = "billing-v1")
public void onOrderCreated(ConsumerRecord<String, OrderCreated> record) {
    process(record.value());

    log.info(
        "Processed topic={}, partition={}, offset={}",
        record.topic(), record.partition(), record.offset()
    );
}
```

`record.offset()` cho biết vị trí của record trong partition. Nó không chứng minh rằng offset đó đã được commit. Việc commit còn phụ thuộc acknowledgement mode và kết quả xử lý của listener container.

Các acknowledgement mode thường gặp:

| Mode | Thời điểm commit |
|---|---|
| `RECORD` | Sau khi listener xử lý xong từng record |
| `BATCH` | Sau khi toàn bộ record của một lần `poll()` được xử lý xong |
| `MANUAL` | Listener chủ động xác nhận bằng `Acknowledgment`; container thực hiện commit theo quy tắc của mode này |
| `MANUAL_IMMEDIATE` | Commit ngay khi listener xác nhận trên consumer thread |

`BATCH` là mode mặc định của listener container. Với batch listener, ứng dụng xử lý một danh sách record trong một lần gọi; cần chọn mode phù hợp với kiểu listener và bảo đảm chỉ xác nhận khi phần việc tương ứng đã hoàn tất.

Nếu cần xác nhận thủ công, cấu hình listener ở mode `manual` và chỉ gọi `acknowledge()` sau khi xử lý thành công:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual
```

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;

@KafkaListener(topics = "orders", groupId = "billing-v1")
public void onOrderCreated(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment acknowledgment) {

    process(record.value());
    acknowledgment.acknowledge();
}
```

Nếu `process()` ném exception trước khi xác nhận, offset chưa được xác nhận theo đoạn code này và container/error handler có thể áp dụng chính sách retry hoặc phục hồi đã cấu hình. Nếu xác nhận trước `process()`, ứng dụng có nguy cơ bỏ qua record khi xử lý thất bại sau đó.

## 7. Đọc lại từ một vị trí khác

Kafka consumer có thể thay đổi consumer position bằng thao tác `seek()` trên một `TopicPartition`. Một số thao tác thường dùng:

- `seek(partition, offset)`: đặt vị trí đọc tiếp theo tại offset chỉ định.
- `seekToBeginning(partitions)`: chuyển vị trí đọc về đầu phần log còn được giữ của các partition đã chọn.
- `seekToEnd(partitions)`: chuyển vị trí đọc đến cuối log của các partition đã chọn.
- `offsetsForTimes(...)`: tìm offset đầu tiên có timestamp lớn hơn hoặc bằng mốc thời gian yêu cầu; kết quả có thể không có nếu partition chưa có record phù hợp.

`seek()` thay đổi vị trí đọc trong bộ nhớ của consumer. Nó không tự động thay đổi committed offset đã lưu cho group. Nếu consumer dừng trước khi vị trí mới được commit, lần khởi động sau vẫn có thể quay lại committed offset cũ.

Trong Spring Kafka, có thể dùng cơ chế như `ConsumerSeekAware` hoặc API của listener container để thực hiện seek theo vòng đời consumer. Kafka consumer không an toàn khi nhiều thread cùng truy cập; thao tác seek cần được thực hiện qua cơ chế của container hoặc trên consumer thread, không gọi tùy tiện từ thread nghiệp vụ.

Phát lại dữ liệu bằng cách seek hoặc reset offset có thể khiến ứng dụng xử lý lại những sự kiện đã tạo tác động trước đó. Hãy bảo đảm handler idempotent và xác định rõ phạm vi partition, offset trước khi replay.

## 8. Retention, compaction và offset không liên tục

Offset là vị trí trong lịch sử log, vì vậy không nên giả định record đầu tiên consumer đọc được luôn có offset 0 hoặc hai record liên tiếp luôn có offset chênh nhau đúng 1.

- **Retention:** Kafka xóa các segment cũ theo chính sách lưu trữ. Offset sớm nhất còn đọc được có thể lớn hơn 0. Nếu committed offset nằm trước vị trí này, consumer gặp offset ngoài phạm vi và Kafka áp dụng `auto.offset.reset` (hoặc báo lỗi với `none`).
- **Compaction:** Với compacted topic, Kafka có thể giữ phiên bản mới nhất của một key và loại bỏ phiên bản cũ. Khoảng offset bị trống là bình thường.
- **Transaction:** Consumer dùng `isolation.level=read_committed` chỉ nhận record thuộc transaction đã commit. Record thuộc transaction abort bị bỏ qua; với transaction đang mở, giới hạn đọc ổn định có thể tạm thời đứng trước log end offset.

Vì vậy, không nên tăng offset bằng cách giả định record tiếp theo luôn là `currentOffset + 1`. Hãy để Kafka consumer điều khiển việc đọc tiếp và dùng offset thực tế trên từng `ConsumerRecord` khi cần ghi log hoặc đối chiếu.

## 9. Theo dõi tiến độ và consumer lag

Có thể xem committed offset, log end offset và lag của một group bằng công cụ dòng lệnh Kafka:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-v1 \
  --describe
```

Kết quả thường có các cột như `CURRENT-OFFSET`, `LOG-END-OFFSET` và `LAG` theo từng partition:

| Cột | Ý nghĩa |
|---|---|
| `CURRENT-OFFSET` | Committed offset hiện tại của group |
| `LOG-END-OFFSET` | Mốc cuối log mà công cụ báo cáo cho partition |
| `LAG` | Chênh lệch giữa hai mốc trên, dùng để ước lượng tiến độ còn lại |

Lag là chỉ số theo offset, không phải lúc nào cũng bằng chính xác số record ứng dụng chưa xử lý. Compaction, transaction và các khoảng offset không có record có thể làm hai con số khác nhau. Khi lag tăng liên tục, hãy kiểm tra tốc độ xử lý, lỗi listener, retry, số partition, số consumer đang hoạt động và tình trạng rebalance.

Nếu cần đưa group về đầu topic, có thể chạy lệnh reset khi group không còn consumer hoạt động. Hãy xem kết quả trước bằng `--dry-run`:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-v1 \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

Chỉ thay `--dry-run` bằng `--execute` sau khi đã xác nhận đúng group, topic và phạm vi partition. Reset offset là thay đổi tiến độ đọc của group; nó có thể tạo ra một đợt replay lớn và lặp lại tác động nghiệp vụ.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Group mới không đọc các record cũ | `auto-offset-reset` đang là `latest` | Kiểm tra group id và reset policy; cân nhắc `earliest` nếu cần đọc lại phần log còn giữ |
| Đổi `auto-offset-reset` nhưng vị trí đọc không đổi | Group đã có committed offset hợp lệ | Kiểm tra `CURRENT-OFFSET`; reset offset có chủ đích nếu muốn replay |
| Một record được xử lý hai lần | Xử lý thành công nhưng dừng trước commit; rebalance hoặc retry | Kiểm tra thời điểm commit và làm handler idempotent |
| Một số record dường như bị bỏ qua | Commit đi trước xử lý, hoặc group bắt đầu ở `latest` | So sánh position, committed offset, reset policy và log của listener |
| Offset không liên tục | Retention, compaction hoặc transaction abort | Không giả định offset liền kề; đối chiếu record thực tế và isolation level |
| Lag tăng dù consumer vẫn chạy | Xử lý chậm, lỗi lặp, retry hoặc thiếu consumer/partition phù hợp | Xem lag theo partition, thời gian xử lý, lỗi và trạng thái group |

## 11. Checklist khi thiết kế consumer

1. Chọn `group-id` ổn định cho một luồng xử lý; chỉ đổi group khi thực sự muốn có tiến độ độc lập.
2. Chọn `earliest`, `latest` hay `none` theo yêu cầu khi group chưa có offset hợp lệ.
3. Xác định rõ lúc nào nghiệp vụ được xem là hoàn tất và commit sau mốc đó.
4. Thiết kế handler idempotent vì record chưa commit có thể được giao lại.
5. Không xem `record.offset()` hoặc consumer position là bằng chứng đã commit.
6. Theo dõi lag theo từng partition và kiểm tra rebalance, retry khi tiến độ bất thường.
7. Khi seek hoặc reset, xác định phạm vi replay và đánh giá tác động đến database hay dịch vụ bên ngoài.

Khi đọc một record, hãy luôn gắn offset với topic và partition. Khi khôi phục consumer, hãy nhìn vào committed offset của đúng group. Hai quy tắc này là nền tảng để giải thích chính xác consumer sẽ đọc record nào tiếp theo và điều gì xảy ra sau một lần lỗi hoặc rebalance.

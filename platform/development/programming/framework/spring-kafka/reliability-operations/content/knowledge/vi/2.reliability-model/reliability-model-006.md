# Offset như mốc tiến độ xử lý

Trong Kafka, một consumer đọc dữ liệu từ topic theo từng partition. Offset là số thứ tự của một vị trí trong partition đó. Khi consumer xử lý một record và commit offset, nó lưu lại mốc mà consumer group có thể tiếp tục đọc từ đó sau khi khởi động lại hoặc nhận partition từ consumer khác.

Vì vậy, offset là một phần quan trọng của độ tin cậy: nó giúp Kafka và ứng dụng xác định tiến độ đọc đã được ghi nhận đến đâu. Tuy nhiên, offset chỉ phản ánh tiến độ mà consumer đã commit. Bản thân nó không chứng minh rằng một nghiệp vụ trong cơ sở dữ liệu hay một lời gọi tới hệ thống bên ngoài đã hoàn tất an toàn. Muốn vận hành đúng, cần hiểu sự khác nhau giữa vị trí đọc, record đã xử lý, acknowledgment và offset đã commit.

## 1. Offset được xác định theo từng partition

Một topic có thể được chia thành nhiều partition. Kafka gán offset cho record trong từng partition theo thứ tự tăng dần. Ví dụ, topic `orders` có hai partition:

| Partition | Các offset trong ví dụ |
|---|---|
| `orders-0` | 0, 1, 2, 3, 4, ... |
| `orders-1` | 0, 1, 2, 3, 4, ... |

Offset `3` ở partition 0 và offset `3` ở partition 1 là hai record khác nhau. Vì vậy, một record được nhận diện bằng bộ thông tin gồm topic, partition và offset; chỉ nhìn offset thì chưa đủ.

Thứ tự được đảm bảo trong phạm vi một partition. Kafka không cung cấp một dãy offset chung để sắp xếp tuyệt đối mọi record thuộc tất cả partition của topic. Nếu ứng dụng cần giữ thứ tự cho các sự kiện cùng một thực thể, producer thường chọn key phù hợp để các sự kiện đó được ghi vào cùng partition.

Offset cũng không nên được hiểu là số lượng record đã xử lý. Một topic compacted có thể loại bỏ record cũ nhưng vẫn giữ nguyên các offset của những record còn lại; một số loại bản ghi điều khiển trong log cũng có thể khiến dãy offset quan sát được có khoảng trống. Do đó, việc thấy offset tăng từ `10` lên `13` không nhất thiết có nghĩa ứng dụng đã bỏ sót hai record.

## 2. Ba khái niệm cần phân biệt

Khi theo dõi tiến độ, cần phân biệt vị trí đọc hiện tại, offset đã commit và offset cuối của log.

| Khái niệm | Ý nghĩa | Vòng đời |
|---|---|---|
| Consumer position | Vị trí tiếp theo mà consumer sẽ đọc trong partition. Vị trí này tiến lên khi các record được trả về từ `poll()`. | Trạng thái đang chạy trong consumer; có thể mất khi consumer dừng. |
| Committed offset | Mốc tiếp tục đọc đã được lưu cho một consumer group và một partition. Giá trị commit thường là offset kế tiếp cần đọc. | Được Kafka lưu để consumer có thể khôi phục sau khi khởi động lại hoặc rebalance. |
| Log end offset | Vị trí ở cuối log của partition, tức mốc kế tiếp sau phần log hiện có. | Thay đổi khi producer ghi thêm dữ liệu. |

Điểm dễ nhầm nhất là committed offset thường biểu diễn **offset kế tiếp cần đọc**, chứ không phải offset của record cuối cùng vừa xử lý. Nếu record ở offset `41` đã xử lý thành công và consumer commit `42`, lần đọc tiếp theo sẽ bắt đầu từ offset `42`.

Kafka lưu committed offset theo consumer group và partition trong topic nội bộ `__consumer_offsets`. Hai consumer group khác nhau có thể đọc cùng một topic nhưng có các mốc tiến độ độc lập. Trong cùng một group, mỗi partition có committed offset riêng.

## 3. Offset trở thành mốc tiến độ như thế nào?

Luồng xử lý thông thường có thể hình dung như sau:

```text
Kafka partition
      |
      v
consumer poll() --------> consumer position tiến lên
      |
      v
Spring Kafka listener xử lý record
      |
      v
listener xử lý thành công / acknowledgment
      |
      v
container commit offset
      |
      v
Kafka lưu committed offset cho group và partition
```

`poll()` đưa record cho consumer và làm consumer position tiến lên. Điều đó chưa có nghĩa nghiệp vụ đã hoàn tất. Trong Spring Kafka, listener container điều phối thời điểm acknowledgment và commit dựa trên `AckMode` cùng cấu hình liên quan. Khi offset được commit, Kafka có một mốc khôi phục mà consumer group có thể sử dụng ở lần đọc tiếp theo.

Ví dụ, consumer group `order-processor` đang đọc partition `orders-0`:

| Sự kiện | Offset của record | Committed offset sau sự kiện |
|---|---:|---:|
| Bắt đầu đọc | 50 | 50 |
| Xử lý record đầu tiên thành công | 50 | 51 |
| Xử lý record tiếp theo thành công | 51 | 52 |
| Bắt đầu xử lý record tiếp theo | 52 | 52 |

Ở đây, committed offset `52` cho biết consumer có thể tiếp tục từ record ở offset `52`. Nó không có nghĩa record offset `52` đã được xử lý.

Acknowledgment và commit có liên quan nhưng không phải lúc nào cũng là cùng một thao tác. Với các chế độ tự động của container, listener trả về thành công sẽ cho container biết record đã được xử lý; container sẽ commit theo `AckMode`. Với chế độ manual, listener gọi `Acknowledgment.acknowledge()` để báo cho container rằng record hoặc batch đã được xác nhận. Thời điểm commit thực tế vẫn phụ thuộc chế độ manual đang dùng và trạng thái xử lý của các record thuộc poll hiện tại.

## 4. Chọn thời điểm commit trong Spring Kafka

Spring Kafka cung cấp `ContainerProperties.AckMode` để xác định cách listener container ghi nhận tiến độ. Với listener container, `enable.auto.commit` được đặt thành `false` mặc định từ Spring Kafka 2.3 nếu ứng dụng chưa cấu hình thuộc tính này. Nên cấu hình rõ ràng để tránh nhầm lẫn với cơ chế auto-commit của Kafka client.

Các chế độ thường dùng:

| AckMode | Khi nào container commit? | Khi phù hợp |
|---|---|---|
| `RECORD` | Sau khi từng record được listener xử lý thành công. | Muốn mốc commit tiến sát từng record; chỉ dùng với record listener. |
| `BATCH` | Sau khi tất cả record nhận được từ một lần `poll()` được xử lý thành công. Đây là chế độ mặc định của listener container. | Muốn giảm số lần commit và chấp nhận mốc tiến độ theo batch poll. |
| `TIME` | Khi đã có acknowledgment đang chờ và khoảng thời gian `ackTime` kể từ lần commit trước đạt ngưỡng. | Điều tiết commit theo thời gian. |
| `COUNT` | Khi số record kể từ lần commit trước đạt `ackCount`. | Điều tiết commit theo số lượng record. |
| `COUNT_TIME` | Khi đạt ngưỡng thời gian hoặc số lượng, tùy điều kiện nào đến trước. | Kết hợp giới hạn theo thời gian và số record. |
| `MANUAL` | Listener chủ động gọi `acknowledge()`; các offset được đưa vào hàng chờ và commit theo ranh giới xử lý poll, tương tự `BATCH`. | Ứng dụng cần quyết định record nào đã được xác nhận. |
| `MANUAL_IMMEDIATE` | Listener gọi `acknowledge()` trên consumer thread thì container yêu cầu commit ngay; nếu gọi từ thread khác, acknowledgment được đưa vào hàng chờ. | Cần yêu cầu commit ngay tại thời điểm xác nhận và kiểm soát rõ thread gọi. |

Ví dụ cấu hình record listener bằng Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-processor
      enable-auto-commit: false
    listener:
      ack-mode: record
```

Listener có thể nhận `ConsumerRecord` để sử dụng metadata của record:

```java
@KafkaListener(topics = "orders")
public void consume(ConsumerRecord<String, OrderCreated> record) {
    orderService.handle(record.value());

    log.info(
        "Processed topic={}, partition={}, offset={}",
        record.topic(),
        record.partition(),
        record.offset()
    );
}
```

Với `AckMode.RECORD`, khi `orderService.handle()` hoàn tất bình thường, container có thể commit tiến độ của record đó. Nếu phương thức ném exception, container chuyển việc xử lý lỗi cho error handler; record có thể được retry hoặc phục hồi theo chính sách đã cấu hình. Không nên tự bắt exception rồi bỏ qua nếu nghiệp vụ thực tế chưa hoàn tất, vì container có thể hiểu listener đã xử lý thành công và tiến độ vẫn được commit.

Nếu cần xác nhận thủ công, cấu hình `MANUAL` và nhận thêm tham số `Acknowledgment`:

```yaml
spring:
  kafka:
    listener:
      ack-mode: manual
```

```java
@KafkaListener(topics = "orders")
public void consume(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment acknowledgment) {

    orderService.handle(record.value());
    acknowledgment.acknowledge();
}
```

Lời gọi `acknowledge()` nên nằm sau khi công việc cần bảo đảm đã hoàn tất. Nếu `orderService.handle()` ghi cơ sở dữ liệu, hãy bảo đảm giao dịch cơ sở dữ liệu đã thành công trước khi xác nhận record. Với `MANUAL`, lời gọi acknowledgment đưa record vào trạng thái đã xác nhận; container commit theo quy tắc của chế độ manual sau khi các record liên quan trong poll được xử lý.

Không nên chuyển record sang một executor rồi để listener trả về ngay trong khi công việc nền vẫn đang chạy. Container có thể xem listener đã hoàn tất và commit offset trước khi công việc thật sự kết thúc. Nếu cần xử lý bất đồng bộ, hãy dùng cơ chế async listener/acknowledgment được Spring Kafka hỗ trợ cho phiên bản đang dùng và chỉ xác nhận khi kết quả xử lý đã hoàn tất. Với acknowledgment ngoài consumer thread hoặc hoàn tất không theo thứ tự, cần đọc kỹ cấu hình `asyncAcks` và giới hạn của phiên bản Spring Kafka tương ứng.

## 5. Offset quyết định điều gì khi ứng dụng gặp sự cố?

Committed offset là mốc khôi phục sau sự cố. Hãy xét consumer đang xử lý record offset `80` và ghi dữ liệu vào cơ sở dữ liệu.

**Xử lý xong rồi mới commit:**

1. Listener nhận record `80`.
2. Ứng dụng ghi thay đổi vào cơ sở dữ liệu thành công.
3. Ứng dụng dừng trước khi commit offset `81`.
4. Consumer khởi động lại và đọc lại từ committed offset `80`.
5. Cùng một nghiệp vụ có thể được thực hiện lần thứ hai.

Đây là tình huống có thể tạo ra xử lý lặp. Cách làm này thường hỗ trợ **at-least-once delivery**: record không bị bỏ qua chỉ vì ứng dụng dừng giữa lúc xử lý và commit, nhưng một record có thể được giao lại.

**Commit trước rồi mới xử lý:**

1. Consumer commit offset `81`.
2. Ứng dụng dừng trước khi ghi thay đổi vào cơ sở dữ liệu.
3. Consumer khởi động lại từ offset `81`.
4. Record `80` không được đọc lại theo tiến độ đã commit, nên nghiệp vụ có thể bị mất.

Đây là rủi ro của **at-most-once processing**: giảm khả năng xử lý lặp nhưng có thể mất công việc nếu sự cố xảy ra sau commit và trước khi xử lý hoàn tất.

Vì vậy, với nghiệp vụ quan trọng, thứ tự phổ biến là xử lý thành công rồi mới xác nhận offset, đồng thời làm cho thao tác nghiệp vụ có tính idempotent. Ví dụ, ứng dụng có thể dùng event ID làm khóa duy nhất, lưu bảng inbox đã xử lý, hoặc dùng ràng buộc duy nhất trong cơ sở dữ liệu để lần giao lại không tạo thêm hiệu ứng nghiệp vụ. Idempotency xử lý trường hợp record được giao nhiều lần; commit offset giúp consumer khôi phục vị trí đọc.

Kafka transaction có thể cung cấp exactly-once semantics cho luồng đọc từ Kafka rồi ghi kết quả trở lại Kafka: các record đầu ra và offset đầu vào được commit trong cùng một transaction. Consumer đọc dữ liệu transactional thường dùng isolation level `read_committed` để không nhận kết quả từ transaction đã abort. Cơ chế này không tự làm cho thao tác ghi vào một cơ sở dữ liệu bên ngoài trở thành exactly-once. Với hệ thống kết hợp Kafka và database, cần thiết kế thêm như inbox/outbox, khóa idempotency hoặc một quy trình phối hợp giao dịch phù hợp.

## 6. Retry, phục hồi và rebalance

Khi listener ném exception, Spring Kafka error handler quyết định cách xử lý tiếp theo: retry tại chỗ, chờ backoff, seek để đọc lại, chuyển record sang nơi phục hồi, hoặc áp dụng chính sách khác. Vì vậy, không thể chỉ nhìn thấy listener đã ném exception rồi kết luận chắc chắn committed offset sẽ đứng yên. Cần xem error handler và cấu hình phục hồi đang dùng. Một record được phục hồi thành công có thể được xem là đã xử lý theo chính sách của container và error handler.

Khi consumer group rebalance, Kafka có thể chuyển partition từ consumer này sang consumer khác. Consumer mới tiếp tục từ committed offset của group cho partition đó. Những record đã xử lý nhưng chưa commit có thể được giao lại; đó là lý do xử lý idempotent vẫn cần thiết ngay cả khi listener chạy ổn định trong điều kiện bình thường.

Thuộc tính `auto.offset.reset` cũng thường bị hiểu nhầm. Thuộc tính này được dùng khi group chưa có committed offset hợp lệ cho partition hoặc offset đã lưu không còn hợp lệ, chẳng hạn do dữ liệu cũ đã hết thời hạn lưu giữ. Các lựa chọn thường gặp là:

- `earliest`: bắt đầu từ offset sớm nhất còn có thể đọc.
- `latest`: bắt đầu từ dữ liệu mới ở cuối partition.
- `none`: báo lỗi nếu không có offset hợp lệ.

`auto.offset.reset` không tự đặt lại một committed offset hợp lệ mỗi lần ứng dụng khởi động. Muốn replay dữ liệu, cần chủ động đặt lại offset của consumer group bằng công cụ quản trị phù hợp hoặc sử dụng group ID mới, sau khi đã đánh giá ảnh hưởng của việc xử lý lại.

## 7. Dùng offset để quan sát độ trễ

Consumer lag thường được tính gần đúng bằng hiệu giữa log end offset và committed offset của từng partition:

```text
lag(partition) = log end offset - committed offset
```

Ví dụ, log end offset là `1,250` và committed offset là `1,200`, lag theo offset là khoảng `50`. Đây là chỉ báo cho biết consumer group đang ở phía sau log bao nhiêu vị trí offset. Do log có thể có khoảng trống, con số này không phải lúc nào cũng bằng chính xác số record nghiệp vụ đang chờ xử lý.

Khi theo dõi hệ thống, nên quan sát lag theo từng partition và theo thời gian. Lag tăng liên tục có thể cho thấy tốc độ xử lý thấp hơn tốc độ producer ghi dữ liệu, một partition bị lệch tải, listener bị chậm, hoặc retry đang kéo dài. Lag giảm về 0 cho thấy committed offset đã bắt kịp cuối log tại thời điểm đo, nhưng không tự chứng minh mọi hiệu ứng bên ngoài đã bền vững nếu ứng dụng commit quá sớm.

Ngoài lag, nên theo dõi tốc độ commit, thời gian xử lý record, số lần retry, lỗi listener, số lần rebalance và phân bố tải giữa các partition. Khi điều tra một record cụ thể, log cả `topic`, `partition`, `offset` và event ID để có thể nối dấu vết xử lý trong ứng dụng với vị trí trong Kafka.

## 8. Những nguyên tắc vận hành cần giữ

- Xem offset như mốc tiếp tục đọc của từng consumer group và partition; không coi nó là số thứ tự toàn cục.
- Tắt Kafka client auto-commit khi để Spring Kafka listener container quản lý acknowledgment và commit; cấu hình `enable-auto-commit=false` rõ ràng.
- Chọn `AckMode` dựa trên yêu cầu về độ trễ commit, thông lượng và khả năng replay. `RECORD` cho mốc tiến độ chi tiết hơn; `BATCH` giảm số lần commit bằng cách gom theo poll.
- Chỉ acknowledgment sau khi phần xử lý cần bảo đảm đã hoàn tất. Đặc biệt cẩn thận với thao tác bất đồng bộ và exception bị bắt rồi bỏ qua.
- Thiết kế nghiệp vụ idempotent để chịu được việc record được giao lại sau crash, retry hoặc rebalance.
- Theo dõi committed offset và lag theo partition; kiểm tra error handler trước khi kết luận một record lỗi sẽ được retry hay phục hồi.
- Đặt lại offset là thao tác vận hành có ảnh hưởng trực tiếp đến dữ liệu được đọc lại hoặc bị bỏ qua. Cần xác định đúng group, topic, partition và mốc đích trước khi thực hiện.

Offset giúp consumer group ghi nhớ tiến độ đọc và khôi phục sau sự cố. Độ tin cậy của toàn bộ quy trình phụ thuộc vào việc ứng dụng chọn đúng thời điểm xác nhận, xử lý lỗi nhất quán và bảo vệ các thao tác nghiệp vụ trước khả năng một record được giao lại.

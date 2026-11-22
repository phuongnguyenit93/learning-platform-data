# max.poll.interval.ms và thời gian xử lý

Một consumer Kafka có thể vẫn kết nối được tới broker nhưng bị rời khỏi consumer group nếu ứng dụng xử lý một lô bản ghi quá lâu. Tình huống này thường xuất hiện khi listener gọi dịch vụ bên ngoài, ghi dữ liệu chậm, xử lý tuần tự một batch lớn hoặc chờ retry với backoff dài. Kafka dùng `max.poll.interval.ms` để giới hạn khoảng thời gian giữa hai lần consumer gọi `poll()`; cấu hình này giúp phát hiện consumer không còn tiến triển trong vòng lặp tiêu thụ.

Trong Spring Kafka, `KafkaMessageListenerContainer` quản lý vòng lặp poll và gọi phương thức `@KafkaListener`. Vì vậy, thời gian chạy listener, số bản ghi nhận trong một lần poll và cách retry đều ảnh hưởng đến khoảng thời gian trước lần poll tiếp theo. Hiểu mối liên hệ này giúp chọn cấu hình phù hợp, tránh rebalance ngoài ý muốn và giảm việc xử lý lại bản ghi.

## 1. Vòng đời poll và ý nghĩa của max.poll.interval.ms

Consumer group cần biết consumer nào đang nhận trách nhiệm xử lý các partition. Với consumer dùng group management, ứng dụng phải tiếp tục gọi `poll()` để chứng minh rằng nó vẫn tiến triển. Một chu kỳ xử lý đơn giản có thể hình dung như sau:

```text
poll()
  |
  +-- nhận tối đa max.poll.records bản ghi
  |
  +-- Spring Kafka gọi listener cho các bản ghi
  |
  +-- xử lý nghiệp vụ / retry / xác nhận offset
  |
poll() tiếp theo
```

`max.poll.interval.ms` là thời gian tối đa được phép giữa hai lần gọi `poll()`. Nếu khoảng cách này vượt quá giới hạn, consumer có thể bị xem là không còn xử lý kịp, rời group và kích hoạt rebalance. Giá trị mặc định của Kafka consumer thường là `300000` ms (5 phút); hãy kiểm tra cấu hình hiệu lực của phiên bản Kafka client đang chạy thay vì giả định mọi môi trường đều giữ mặc định.

Điểm cần nhớ là bộ đếm này gắn với tiến độ gọi `poll()`, không chỉ với thời gian xử lý một bản ghi. Khi một lần poll trả về nhiều bản ghi, listener có thể phải xử lý toàn bộ số bản ghi đó trước khi container gọi poll tiếp theo. Vì thế, một listener xử lý mỗi bản ghi khá nhanh vẫn có thể vượt giới hạn nếu batch quá lớn.

## 2. Phân biệt các cấu hình thường bị nhầm lẫn

| Cấu hình | Vai trò | Ảnh hưởng chính |
|---|---|---|
| `max.poll.interval.ms` | Giới hạn thời gian giữa hai lần `poll()` | Consumer có thể rời group nếu không poll kịp |
| `max.poll.records` | Số bản ghi tối đa trả về từ một lần `poll()` | Quyết định khối lượng listener cần xử lý trong một chu kỳ |
| `session.timeout.ms` | Thời gian broker chờ heartbeat trước khi xem consumer đã mất kết nối | Phát hiện consumer mất liên lạc |
| `heartbeat.interval.ms` | Khoảng thời gian client gửi heartbeat | Điều phối heartbeat trong consumer group |
| `pollTimeout` của Spring Kafka | Thời gian một lần poll chờ dữ liệu khi chưa có bản ghi | Điều khiển thời gian chờ dữ liệu của container |

`session.timeout.ms` và `heartbeat.interval.ms` liên quan đến heartbeat và khả năng phát hiện mất kết nối. `max.poll.interval.ms` theo dõi tiến độ xử lý ở cấp ứng dụng. Consumer có thể vẫn gửi heartbeat trong khi listener đang chạy, nhưng điều đó không thay thế yêu cầu gọi `poll()` đúng hạn. Khi vượt `max.poll.interval.ms`, client có thể rời group dù kết nối mạng chưa bị đứt.

`max.poll.records` giới hạn số bản ghi được trả về cho ứng dụng trong một lần poll. Nó không phải giới hạn kích thước dữ liệu theo byte và không thay thế các cấu hình fetch như `fetch.max.bytes` hoặc `max.partition.fetch.bytes`. Giảm `max.poll.records` thường làm giảm thời gian xử lý của một chu kỳ, đổi lại có thể tăng số lần poll và chi phí xử lý theo lô.

Với static membership, tức consumer được cấu hình `group.instance.id`, việc vượt giới hạn poll có thể khiến partition chưa được phân phối lại ngay lập tức; broker có thể chờ đến khi `session.timeout.ms` hết hạn. Static membership có thể giảm một số rebalance khi instance khởi động lại ngắn hạn, nhưng không giải quyết nguyên nhân listener xử lý quá lâu.

## 3. Tính thời gian cho một chu kỳ xử lý

Khi xử lý tuần tự, có thể ước lượng thời gian một chu kỳ bằng tổng thời gian xử lý các bản ghi cộng với các công việc nằm giữa hai lần poll:

\[
T_{cycle} \approx \sum_{i=1}^{N} T_{handler,i} + T_{commit} + T_{retry} + T_{overhead}
\]

Trong đó:

- `N` là số bản ghi thực tế nhận trong lần poll, không vượt `max.poll.records`.
- `T_handler,i` là thời gian listener xử lý bản ghi thứ `i`, gồm cả các lời gọi DB hoặc HTTP đồng bộ.
- `T_commit` là thời gian xác nhận offset nếu commit nằm trong chu kỳ đó.
- `T_retry` là tổng thời gian chờ và thử lại theo cách retry đang dùng.
- `T_overhead` gồm thời gian scheduling, garbage collection, log và các khoảng trễ khác.

Đây là mô hình ước lượng để lập ngân sách thời gian, không phải công thức đo chính xác nội bộ của Kafka. Khi có xử lý song song, cần đo thời gian thực tế từ lúc poll trả về đến lúc consumer có thể poll tiếp; không nên chỉ lấy thời gian trung bình của một task để suy ra.

Ví dụ, một consumer nhận 120 bản ghi và mỗi bản ghi cần khoảng 700 ms để xử lý tuần tự. Riêng phần listener đã cần khoảng 84 giây. Nếu commit, retry và các khoảng trễ khác cần thêm 15 giây thì chu kỳ vào khoảng 99 giây. Với `max.poll.interval.ms=120000`, phần dự phòng chỉ còn 21 giây. Một lần gọi dịch vụ ngoài chậm hoặc một đợt retry có thể khiến chu kỳ vượt ngưỡng.

Nếu giảm `max.poll.records` xuống 40, phần xử lý tuần tự theo giả định trên còn khoảng 28 giây cho mỗi chu kỳ. Đổi lại, consumer gọi poll thường xuyên hơn và có thể cần thêm lượt xử lý để tiêu thụ cùng lượng dữ liệu. Con số thực tế phải được chọn dựa trên phân bố thời gian xử lý, không chỉ dựa vào thời gian trung bình.

Nguyên tắc cấu hình là giữ thời gian chu kỳ ở mức thấp hơn đáng kể so với `max.poll.interval.ms`, với khoảng dự phòng cho tải tăng, độ trễ hệ thống phụ thuộc, retry và garbage collection. Nên dùng số đo ở p95/p99 hoặc tình huống tải cao để kiểm tra thay vì chỉ dùng happy path.

## 4. Cấu hình trong Spring Boot

Có thể đặt giới hạn thời gian và số bản ghi mỗi poll trong `application.yml`:

```yaml
spring:
  kafka:
    consumer:
      group-id: billing-worker
      enable-auto-commit: false
      max-poll-records: 40
      properties:
        "[max.poll.interval.ms]": "180000"
```

Trong ví dụ này, mỗi lần poll trả về tối đa 40 bản ghi và consumer phải gọi poll tiếp theo trong vòng 180 giây. `enable-auto-commit: false` giúp Spring Kafka container quản lý việc xác nhận offset theo `AckMode` đã cấu hình. Đây là thiết lập thường dùng với Spring Kafka; cần giữ nhất quán giữa thời điểm commit và thời điểm nghiệp vụ được xử lý thành công.

Nếu cấu hình trực tiếp bằng Java, có thể truyền các thuộc tính vào `ConsumerFactory`:

```java
Map<String, Object> consumerProps = new HashMap<>();
consumerProps.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
consumerProps.put(ConsumerConfig.GROUP_ID_CONFIG, "billing-worker");
consumerProps.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
consumerProps.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 40);
consumerProps.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 180_000);

ConsumerFactory<String, OrderCreated> consumerFactory =
        new DefaultKafkaConsumerFactory<>(consumerProps, keyDeserializer, valueDeserializer);
```

Các import và deserializer trong ví dụ được lược bớt để tập trung vào hai thuộc tính cần điều chỉnh. Không nên khai báo cùng một thuộc tính ở nhiều nơi với giá trị khác nhau; hãy kiểm tra cấu hình cuối cùng được dùng để tạo consumer.

## 5. Tác động với @KafkaListener

Ví dụ một record listener xử lý đơn hàng:

```java
@Component
public class BillingListener {

    private final BillingService billingService;

    public BillingListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(topics = "orders", groupId = "billing-worker")
    public void onMessage(OrderCreated event) {
        billingService.handle(event);
    }
}
```

Ngay cả khi phương thức `onMessage` chỉ nhận một `OrderCreated` mỗi lần gọi, container vẫn có thể đang xử lý nhiều record được trả về từ cùng một lần poll. Nếu container gọi listener tuần tự cho 40 record, thời gian của 40 lần gọi có thể cộng dồn trước khi poll tiếp theo diễn ra. Do đó, hãy đánh giá tổng thời gian của cả chu kỳ, không chỉ đo một lần gọi `billingService.handle()`.

Với batch listener, toàn bộ batch thường được chuyển vào một lần gọi phương thức:

```java
@KafkaListener(topics = "orders", groupId = "billing-worker")
public void onBatch(List<OrderCreated> events) {
    billingService.handleBatch(events);
}
```

Batch listener có thể tận dụng thao tác ghi DB theo lô, nhưng một batch lớn cũng làm tăng thời gian trước lần poll tiếp theo. Hãy đặt `max.poll.records` theo thời gian xử lý của batch và khả năng chịu tải của hệ thống phụ thuộc.

`AckMode` quyết định cách container xác nhận offset. Chẳng hạn, `BATCH` thường xác nhận các offset sau khi xử lý xong các record của lần poll; `RECORD` xác nhận sau từng record đối với record listener. Chọn `AckMode` phù hợp với yêu cầu giao nhận, nhưng không coi việc commit từng record là cách thay thế cho việc quản lý thời gian poll: listener vẫn cần hoàn tất công việc hiện tại để container tiếp tục vòng lặp.

## 6. Điều gì xảy ra khi xử lý vượt giới hạn?

Giả sử consumer nhận các bản ghi từ partition `orders-2`, sau đó listener bị chặn 4 phút bởi một lời gọi HTTP. Nếu `max.poll.interval.ms` chỉ là 3 phút, consumer không kịp poll tiếp theo. Kafka có thể loại consumer khỏi group và bắt đầu rebalance để phân phối partition cho consumer khác.

Khi partition được giao cho consumer mới, các bản ghi chưa được commit có thể được đọc lại từ offset đã xác nhận gần nhất. Vì vậy, một bản ghi có thể đã tạo tác động ở DB hoặc hệ thống bên ngoài nhưng vẫn được Kafka giao lại. Đây là lý do consumer nên có xử lý idempotent, ví dụ dùng `eventId` duy nhất để chống ghi nhận một nghiệp vụ hai lần.

Việc tăng `max.poll.interval.ms` có thể giảm rebalance khi xử lý lâu, nhưng nếu đặt quá lớn thì phát hiện consumer bị kẹt cũng chậm hơn. Đồng thời, tăng giới hạn không làm cho listener nhanh hơn, không giảm consumer lag và không sửa được một lời gọi dịch vụ phụ thuộc bị treo vô thời hạn. Hãy cấu hình timeout cho HTTP, DB và các thao tác có thể chờ lâu.

## 7. Cách xử lý khi listener mất nhiều thời gian

1. **Giảm `max.poll.records` trước khi tăng timeout một cách mù quáng.** Bắt đầu với batch nhỏ, đo thời gian chu kỳ và tăng dần nếu hệ thống còn dư khả năng xử lý. Đây thường là lựa chọn phù hợp khi mỗi record có chi phí nghiệp vụ lớn hoặc biến động mạnh.
2. **Đặt `max.poll.interval.ms` theo số đo.** Chọn giá trị lớn hơn thời gian chu kỳ ở tải cao và có dự phòng rõ ràng. Không dùng một timeout rất lớn để che giấu listener bị treo.
3. **Giới hạn thời gian của công việc phụ thuộc.** Đặt connect/read timeout cho HTTP, query timeout cho DB và giới hạn số lần retry. Một retry với backoff dài cũng tiêu thụ ngân sách giữa hai lần poll nếu nó chặn listener.
4. **Tối ưu xử lý theo lô khi có thể.** Nếu nghiệp vụ cho phép, gom thao tác DB hoặc gọi dịch vụ theo batch để giảm overhead. Vẫn phải đo thời gian của cả batch và giữ giới hạn kích thước hợp lý.
5. **Tách công việc kéo dài khỏi listener khi phù hợp.** Listener có thể xác thực sự kiện và chuyển công việc sang một hàng đợi bền vững hoặc lưu vào bảng công việc trong transaction phù hợp, sau đó mới xác nhận offset. Worker riêng xử lý tác vụ lâu. Chỉ commit sau khi công việc đã được lưu bền vững; nếu đưa vào một queue chỉ nằm trong RAM rồi commit Kafka, sự cố tiến trình có thể làm mất công việc.
6. **Cẩn thận với xử lý bất đồng bộ.** Không gọi trực tiếp các phương thức của `KafkaConsumer` từ thread nghiệp vụ vì consumer không thread-safe. Nếu listener trả về kết quả bất đồng bộ hoặc xác nhận ngoài thread poll, cần dùng cơ chế được Spring Kafka hỗ trợ và hiểu rõ cách container giữ offset, pause/resume và thứ tự xác nhận.
7. **Điều chỉnh concurrency theo partition.** Spring Kafka có thể tạo nhiều consumer thông qua `concurrency`; mỗi consumer có vòng lặp poll và ngân sách thời gian riêng. Tăng concurrency có ích khi có đủ partition và tài nguyên, nhưng không làm một listener đang xử lý tuần tự tự động nhanh hơn.

## 8. Theo dõi và chẩn đoán

Khi thấy rebalance lặp lại hoặc consumer lag tăng bất thường, hãy đối chiếu các dấu hiệu sau:

- Thời gian xử lý listener theo record và theo batch, đặc biệt ở p95/p99.
- Số record thực tế nhận từ mỗi lần poll và giá trị `max.poll.records`.
- Thời gian từ lúc bắt đầu xử lý batch đến khi container có thể poll tiếp.
- Thời gian commit offset, số lần retry và tổng thời gian backoff.
- Log của Kafka consumer về việc vượt `max.poll.interval.ms`, rời group và rebalance.
- Consumer lag, tốc độ tiêu thụ và số lần rebalance trong cùng khoảng thời gian.

Một quy trình điều tra hữu ích là tái hiện với kích thước batch và độ trễ phụ thuộc gần giống production, đo thời gian chu kỳ, sau đó giảm `max.poll.records` để xác định phần thời gian có tăng theo số record hay không. Nếu thời gian tăng chủ yếu do một lời gọi HTTP hoặc DB bất thường, cần xử lý timeout và retry ở đúng dependency. Nếu chu kỳ ổn định nhưng luôn gần sát giới hạn, hãy điều chỉnh batch size hoặc timeout và xác minh lại dưới tải cao.

## 9. Các hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| Tăng `session.timeout.ms` sẽ giải quyết listener chậm | Cần xem `max.poll.interval.ms`, vì nó giới hạn thời gian giữa hai lần poll |
| Listener xử lý từng record nên không có batch | Một lần poll vẫn có thể trả nhiều record; thời gian gọi listener có thể cộng dồn |
| `pollTimeout` của Spring Kafka chính là `max.poll.interval.ms` | Một thuộc tính là thời gian chờ trong lần poll; thuộc tính kia là giới hạn giữa hai lần poll |
| Tăng `max.poll.interval.ms` luôn tốt hơn | Timeout quá lớn làm chậm phát hiện consumer không còn tiến triển |
| Commit offset sớm sẽ tránh rebalance | Commit sớm có thể làm mất record nếu nghiệp vụ chưa hoàn tất; cần xác nhận sau khi xử lý hoặc lưu công việc bền vững |
| Tăng `concurrency` sẽ sửa một record xử lý quá lâu | Concurrency phân phối partition qua nhiều consumer; nó không rút ngắn thời gian xử lý của một record đang chạy |

## 10. Checklist trước khi đưa vào production

- Đã đo thời gian xử lý ở tải cao và xác định thời gian tối đa của một chu kỳ poll.
- `max.poll.records` phù hợp với chi phí xử lý mỗi record hoặc mỗi batch.
- `max.poll.interval.ms` lớn hơn thời gian chu kỳ dự kiến với khoảng dự phòng có chủ đích.
- Các lời gọi DB, HTTP và retry đều có timeout hoặc giới hạn thời gian.
- Cơ chế commit offset phù hợp với thời điểm nghiệp vụ được xử lý thành công.
- Listener có tính idempotent để chịu được việc đọc lại sau rebalance hoặc lỗi trước commit.
- Có theo dõi listener latency, consumer lag và log rebalance để phát hiện xu hướng xấu.

`max.poll.interval.ms` là một phần của thiết kế vòng đời consumer. Cấu hình tốt cần cân bằng giữa kích thước batch, thời gian xử lý, retry, commit và khả năng phục hồi của consumer group. Khi đo và kiểm soát được toàn bộ chu kỳ poll, ứng dụng Spring Kafka sẽ ít gặp rebalance do xử lý chậm và vận hành ổn định hơn.

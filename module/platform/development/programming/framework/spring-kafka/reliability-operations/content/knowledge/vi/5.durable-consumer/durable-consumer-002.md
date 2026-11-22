# poll loop và giới hạn max.poll.interval.ms

Một Kafka consumer phải liên tục gọi `poll()` để nhận record mới và tham gia điều phối consumer group. Trong ứng dụng Spring Kafka, listener container quản lý vòng lặp này: container gọi `poll()`, chuyển record cho listener xử lý, xử lý acknowledgment và commit offset theo cấu hình, rồi tiếp tục poll. Nếu thời gian xử lý khiến consumer không gọi `poll()` đủ thường xuyên, Kafka có thể xem consumer đó không còn tiến triển, đưa nó ra khỏi group và phân phối lại partition.

Thuộc tính `max.poll.interval.ms` đặt giới hạn cho khoảng thời gian tối đa giữa hai lần gọi `poll()`. Đây là một giới hạn quan trọng khi vận hành consumer có công việc xử lý lâu, batch lớn, retry có backoff hoặc phụ thuộc vào hệ thống bên ngoài. Hiểu đúng giới hạn này giúp tránh rebalance ngoài ý muốn, xử lý lặp và tình trạng consumer liên tục mất rồi nhận lại partition.

## 1. Vòng lặp poll hoạt động ra sao?

Kafka consumer không nhận record bằng cách chờ broker tự đẩy từng message đến ứng dụng. Ứng dụng chủ động gọi `poll()` để lấy các record đã sẵn sàng. Vòng lặp cơ bản có dạng:

```text
consumer thread
      |
      v
    poll()
      |
      v
Nhận tối đa N record từ các partition được gán
      |
      v
Chuyển record cho listener xử lý
      |
      v
Acknowledgment / commit theo cấu hình
      |
      v
    poll() lần tiếp theo
```

Trong Spring Kafka, `KafkaMessageListenerContainer` chạy consumer trên một thread của container. Thread đó gọi Kafka consumer `poll()` và gọi phương thức `@KafkaListener` tương ứng. Với `ConcurrentMessageListenerContainer`, mỗi container con có consumer và vòng lặp riêng; thuộc tính `concurrency` xác định số consumer container con được tạo.

Ví dụ, một record listener nhận từng record:

```java
@KafkaListener(topics = "payments", groupId = "payment-worker")
public void handle(PaymentRequested event) {
    paymentService.process(event);
}
```

Listener được gọi cho từng record. Tuy nhiên, Kafka consumer có thể đã trả về nhiều record trong một lần `poll()`. Container có thể phải gọi listener nhiều lần để xử lý hết tập record vừa nhận trước khi quay lại `poll()` tiếp theo. Vì thế, dù mỗi lần gọi `handle()` khá nhanh, tổng thời gian xử lý tất cả record của một poll vẫn có thể dài.

Với batch listener, container chuyển cả batch cho một lần gọi listener:

```java
@KafkaListener(topics = "payments", groupId = "payment-worker")
public void handleBatch(List<PaymentRequested> events) {
    paymentService.processBatch(events);
}
```

Batch listener có thể giảm chi phí gọi hàm và gom thao tác I/O, nhưng thời gian xử lý batch cũng phải nằm trong ngân sách thời gian giữa hai lần poll. Việc dùng `AckMode.RECORD` hay `AckMode.BATCH` ảnh hưởng thời điểm commit offset; nó không loại bỏ yêu cầu consumer phải tiếp tục gọi `poll()` đúng hạn.

## 2. max.poll.interval.ms giới hạn điều gì?

`max.poll.interval.ms` là khoảng thời gian tối đa mà Kafka consumer được phép không gọi `poll()` giữa hai lần poll liên tiếp. Khi khoảng thời gian này vượt ngưỡng, consumer được xem là không đáp ứng yêu cầu tiến triển của group. Kafka có thể loại consumer khỏi group và kích hoạt rebalance để partition được giao cho consumer khác.

Thuộc tính này đo thời gian giữa các lần gọi `poll()`, không phải thời gian tối đa của riêng một record và cũng không phải thời gian `poll()` được phép chờ broker trả dữ liệu. Ngân sách thời gian phải bao gồm công việc diễn ra sau khi một poll trả về và trước lần poll kế tiếp, chẳng hạn:

- Xử lý tất cả record đã nhận từ lần poll trước.
- Gọi database, HTTP service, hệ thống thanh toán hoặc dịch vụ bên ngoài.
- Chạy logic nghiệp vụ, serialize/deserialize và xử lý dữ liệu.
- Retry hoặc backoff được thực hiện đồng bộ trên consumer thread.
- Commit offset, callback và các công việc điều phối khác.
- Thời gian tạm dừng do garbage collection, CPU bị tranh chấp hoặc thread bị block.

Có thể lập ngân sách gần đúng như sau:

```text
thời gian giữa hai poll
  = thời gian xử lý record/batch
  + thời gian retry và chờ đồng bộ
  + thời gian commit và công việc phụ
  + thời gian trễ do runtime/hệ điều hành

Điều kiện vận hành:
  thời gian giữa hai poll < max.poll.interval.ms
```

Kafka Java consumer thường có giá trị mặc định `max.poll.interval.ms` là 300.000 ms (5 phút). Giá trị thực tế của ứng dụng phụ thuộc phiên bản client và cấu hình được áp dụng; nên kiểm tra cấu hình runtime thay vì giả định mọi môi trường đều giữ mặc định.

### Ví dụ: batch khiến poll loop trễ hạn

Giả sử consumer nhận 80 record trong một lần poll. Listener xử lý tuần tự, mỗi record mất khoảng 450 ms:

```text
80 record × 450 ms = 36.000 ms = 36 giây
```

Nếu `max.poll.interval.ms` được đặt thành 30.000 ms, consumer có thể vượt giới hạn trước khi xử lý xong tập record và gọi `poll()` tiếp theo. Nếu commit, gọi dịch vụ bên ngoài hoặc gặp GC pause, khoảng thời gian thực tế còn dài hơn.

Điểm quan trọng là tổng thời gian của cả lượt xử lý poll mới quyết định nguy cơ. Một record mất 2 giây có thể an toàn khi giới hạn là 5 phút, nhưng 200 record liên tiếp, mỗi record mất 2 giây, có thể kéo dài hơn 6 phút và làm poll loop quá hạn.

## 3. Phân biệt max.poll.interval.ms với heartbeat và session timeout

Ba thuộc tính thường bị nhầm lẫn vì đều liên quan đến việc consumer còn ở trong group hay không:

| Thuộc tính | Vai trò | Câu hỏi nó trả lời |
|---|---|---|
| `max.poll.interval.ms` | Giới hạn thời gian giữa hai lần gọi `poll()`; giám sát tiến triển của ứng dụng tiêu thụ. | Consumer có tiếp tục lấy dữ liệu và tiến triển xử lý đúng nhịp không? |
| `session.timeout.ms` | Thời gian coordinator chờ heartbeat hợp lệ trước khi xem consumer mất kết nối. | Consumer còn duy trì liên lạc với group coordinator không? |
| `heartbeat.interval.ms` | Khoảng thời gian giữa các heartbeat do consumer gửi theo cơ chế group protocol đang dùng. | Consumer gửi tín hiệu duy trì membership thường xuyên đến mức nào? |

Trong Kafka consumer hiện đại, heartbeat có thể được gửi bởi luồng nền trong khi thread ứng dụng đang xử lý record. Vì vậy, việc heartbeat vẫn hoạt động không có nghĩa consumer được phép ngừng gọi `poll()` vô hạn. `max.poll.interval.ms` bảo vệ tiến triển xử lý ở cấp ứng dụng, trong khi session timeout chủ yếu phát hiện mất liên lạc.

Tăng `session.timeout.ms` không giải quyết trực tiếp việc listener xử lý quá lâu giữa hai lần poll. Tương tự, giảm `heartbeat.interval.ms` không làm cho một batch dài hoàn tất nhanh hơn. Khi chẩn đoán rebalance, cần xem đúng nguyên nhân: mất heartbeat, vượt poll interval, lỗi mạng, consumer dừng, hay một thay đổi membership khác.

## 4. max.poll.records kiểm soát lượng việc sau mỗi poll

`max.poll.records` giới hạn số record tối đa mà một lần `poll()` trả về cho ứng dụng. Đây là một trong những nút điều chỉnh quan trọng nhất khi thời gian xử lý batch ảnh hưởng đến poll interval.

Ví dụ:

```yaml
spring:
  kafka:
    consumer:
      max-poll-records: 50
      properties:
        "[max.poll.interval.ms]": 180000
```

Trong ví dụ này, mỗi lần poll trả về tối đa 50 record và khoảng thời gian giữa hai lần poll không được vượt quá 180 giây. Tên thuộc tính trong `consumer.properties` được chuyển nguyên dạng tới Kafka client; cú pháp ngoặc vuông giúp giữ nguyên key có dấu chấm khi binding cấu hình Spring Boot.

Giảm `max.poll.records` làm giảm lượng công việc có thể dồn vào một chu kỳ poll. Điều này thường giúp consumer quay lại poll sớm hơn và giới hạn thời gian xử lý tối đa của một batch. Đổi lại, ứng dụng có thể thực hiện nhiều chu kỳ poll hơn, tăng chi phí điều phối hoặc giảm hiệu quả của các thao tác vốn có lợi khi gom batch.

`max.poll.records` không giới hạn số record mà broker lưu trong partition và không phải giới hạn tổng lượng dữ liệu consumer fetch về nội bộ. Nó giới hạn số record được trả về trong một lần gọi `poll()`. Vì vậy, không nên xem nó như giới hạn dung lượng topic hoặc cơ chế xóa bớt record.

### Ước lượng cấu hình từ thời gian xử lý

Với listener xử lý tuần tự, có thể bắt đầu bằng phép ước lượng:

```text
T_batch ≈ N × T_record
T_cycle ≈ T_batch + T_commit + T_overhead
```

Trong đó:

- `N` là số record thực tế tối đa có thể nhận trong một poll, không vượt `max.poll.records`.
- `T_record` là thời gian xử lý một record.
- `T_commit` là thời gian dành cho commit và acknowledgment.
- `T_overhead` gồm retry, callback, GC pause và các khoảng chờ khác.

Giả sử một record thường mất 300 ms, một poll nhận 100 record, và commit cùng công việc phụ mất khoảng 5 giây:

```text
T_batch ≈ 100 × 300 ms = 30 giây
T_cycle ≈ 30 + 5 = 35 giây
```

Không nên cấu hình `max.poll.interval.ms` sát 35 giây. Thời gian thực tế thay đổi theo tải, độ trễ database, kích thước payload và các tình huống bất thường. Hãy đo thời gian xử lý ở tải đại diện, xem các percentile cao và chừa khoảng dự phòng đủ lớn. Nếu thời gian xử lý có đuôi dài, hãy giảm số record mỗi poll hoặc thay đổi cách tổ chức công việc thay vì chỉ dựa vào giá trị trung bình.

## 5. Cấu hình consumer trong Spring Kafka

Spring Boot cho phép đặt các thuộc tính Kafka consumer qua `spring.kafka.consumer`. Ví dụ sau giới hạn số record mỗi poll, tắt auto-commit của Kafka client và đặt poll interval thành ba phút:

```yaml
spring:
  kafka:
    consumer:
      group-id: payment-worker
      enable-auto-commit: false
      max-poll-records: 50
      properties:
        "[max.poll.interval.ms]": 180000
    listener:
      ack-mode: record
      concurrency: 3
```

`enable-auto-commit: false` để listener container của Spring Kafka điều phối việc xác nhận và commit offset theo `AckMode`. `concurrency: 3` tạo tối đa ba consumer container con cho listener endpoint này. Mỗi consumer có poll loop và ngân sách `max.poll.interval.ms` riêng.

Concurrency không chia một partition cho nhiều consumer cùng lúc trong cùng một consumer group. Nếu topic chỉ có hai partition, tăng concurrency lên sáu không tạo ra sáu luồng xử lý song song cho hai partition đó; một số consumer sẽ không được gán partition. Nếu chỉ một partition có tải lớn, tăng concurrency cũng không tự chia tải của partition đó thành nhiều consumer. Khi điều chỉnh, cần xem số partition, phân bố key và mức độ song song của nghiệp vụ.

Với cấu hình Java tạo `ConsumerFactory` trực tiếp, có thể đặt thuộc tính bằng hằng số của Kafka client:

```java
Map<String, Object> props = new HashMap<>();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "payment-worker");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 50);
props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 180_000);

ConsumerFactory<String, PaymentRequested> factory =
        new DefaultKafkaConsumerFactory<>(props);
```

Khi dùng cấu hình Java, hãy bảo đảm các thuộc tính được đặt trên đúng `ConsumerFactory` mà listener container thực sự sử dụng. Một cấu hình được khai báo ở file YAML nhưng bị một factory tùy chỉnh ghi đè sẽ không tạo ra hành vi như mong đợi.

## 6. Điều gì xảy ra khi consumer vượt poll interval?

Giả sử consumer A đang sở hữu partition `payments-2`. Consumer A gọi `poll()`, nhận một nhóm record rồi bị block trong lúc gọi dịch vụ thanh toán. Thời gian xử lý vượt `max.poll.interval.ms`.

Một chuỗi sự kiện có thể xảy ra:

1. Consumer A không gọi `poll()` trong khoảng thời gian cho phép.
2. Kafka xem consumer A không còn đáp ứng yêu cầu tiến triển của group.
3. Consumer A rời group hoặc bị xem là không còn đủ điều kiện giữ membership theo group protocol.
4. Group thực hiện rebalance và partition `payments-2` có thể được gán cho consumer B.
5. Consumer B tiếp tục đọc từ committed offset hiện có của group.

Nếu A đã thực hiện hiệu ứng nghiệp vụ nhưng chưa commit offset tương ứng, B có thể đọc lại record đó. Ví dụ, A đã gửi yêu cầu thanh toán đến hệ thống bên ngoài nhưng chưa commit offset; sau rebalance, B nhận lại record và có thể gửi yêu cầu lần nữa. Đây là nguồn gây xử lý trùng khi consumer vượt poll interval.

Kết quả chính xác phụ thuộc thời điểm commit, acknowledgment mode, giao dịch và cách xử lý rebalance. Không nên giả định mọi record trong poll đều được commit hoặc đều bị đọc lại. Hãy thiết kế listener theo hướng idempotent: cùng một event ID được xử lý lại không tạo thêm hiệu ứng nghiệp vụ. Có thể dùng khóa duy nhất, bảng inbox, ràng buộc duy nhất trong database hoặc API đích hỗ trợ idempotency key.

Rebalance cũng có chi phí vận hành: consumer khác phải nhận partition, có thể phải tải lại trạng thái, cache hoặc kết nối liên quan; trong thời gian chuyển giao, độ trễ xử lý tăng. Nếu poll interval thường xuyên bị vượt, hệ thống có thể rơi vào vòng lặp xử lý một phần, mất membership, rebalance rồi xử lý lại.

## 7. Retry và backoff có thể làm poll loop bị chậm

Một listener có thể ném exception khi database tạm thời không khả dụng hoặc dịch vụ bên ngoài trả lỗi. Spring Kafka error handler có thể retry đồng bộ theo backoff. Nếu retry và thời gian chờ diễn ra trên consumer thread, chúng làm tăng thời gian từ poll này đến poll tiếp theo.

Ví dụ, một record cần ba lần thử, mỗi lần mất 4 giây và giữa các lần thử chờ 10 giây:

```text
3 lần xử lý × 4 giây = 12 giây
2 khoảng backoff × 10 giây = 20 giây
Tổng thời gian cho record ≈ 32 giây
```

Nếu một poll chứa nhiều record lỗi hoặc có retry kéo dài, tổng thời gian có thể vượt giới hạn. Cần tính cả thời gian retry trong ngân sách poll loop, không chỉ thời gian xử lý thành công.

Với các khoảng backoff dài, Spring Kafka cung cấp `ContainerPausingBackOffHandler` ở các phiên bản hỗ trợ. Cơ chế này pause container trong thời gian chờ và tiếp tục poll trong lúc tạm dừng để giữ cho consumer duy trì hoạt động với group. Thời gian pause thực tế có thể được làm tròn theo `pollTimeout`, vì vậy cần hiểu cấu hình container và phiên bản đang chạy.

Một lựa chọn khác là chuyển retry dài sang retry topic hoặc một quy trình xử lý riêng. Khi đó, record lỗi được chuyển sang luồng retry theo chính sách đã thiết kế; consumer chính có thể tiếp tục xử lý record khác. Cần xác định rõ thứ tự sự kiện, số lần retry, thời hạn retry, dead-letter topic và cách tránh xử lý lặp giữa luồng chính với luồng retry.

## 8. Xử lý công việc lâu mà vẫn duy trì poll

Nếu một listener thường xuyên xử lý một record lâu hơn ngân sách poll, chỉ tăng `max.poll.interval.ms` có thể che giấu vấn đề và làm chậm thời điểm phát hiện consumer bị treo. Có một số hướng thiết kế cần cân nhắc:

**Giảm thời gian xử lý đồng bộ.** Tối ưu truy vấn database, đặt timeout rõ ràng cho HTTP client, gom thao tác I/O hoặc giảm kích thước payload. Mục tiêu là đưa thời gian xử lý về một giới hạn có thể dự đoán.

**Giảm lượng record mỗi poll.** Điều chỉnh `max.poll.records` để container xử lý ít record hơn trước khi gọi poll tiếp theo. Cách này hữu ích khi tổng thời gian của batch là nguyên nhân chính.

**Pause container khi cần điều tiết tải.** Spring Kafka hỗ trợ pause và resume listener container hoặc partition. Khi consumer bị pause, container vẫn tiếp tục gọi `poll()` theo cơ chế của nó nhưng không lấy thêm record để giao cho listener từ các partition đã pause. Đây là cách hữu ích để tạo backpressure mà vẫn duy trì nhịp poll. Cần dùng API của listener container thay vì gọi trực tiếp `KafkaConsumer.pause()` từ một thread tùy ý.

**Dùng xử lý bất đồng bộ có quản lý acknowledgment.** Nếu chuyển công việc sang executor rồi trả về khỏi listener ngay, container có thể tiếp tục poll trong khi công việc nền chưa xong. Tuy nhiên, acknowledgment phải gắn với kết quả xử lý thực tế. Nếu commit offset trước khi công việc hoàn tất, sự cố có thể làm mất nghiệp vụ. Nếu hoàn tất không theo thứ tự, cần cấu hình và hiểu rõ cơ chế async acknowledgment của phiên bản Spring Kafka đang dùng. Không dùng cùng một `KafkaConsumer` từ thread nền vì Kafka consumer không thread-safe.

**Tách công việc dài thành một quy trình khác.** Nếu một record khởi chạy công việc kéo dài hàng chục phút hoặc nhiều giờ, cân nhắc ghi nhận yêu cầu một cách bền vững rồi giao phần công việc dài cho worker hoặc workflow riêng. Consumer Kafka có thể xác nhận khi bước tiếp nhận đã được lưu an toàn, còn trạng thái hoàn tất của công việc dài được quản lý bằng một cơ chế riêng.

## 9. Các lỗi cấu hình và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Consumer thường xuyên bị rebalance khi tải tăng | Thời gian xử lý batch vượt `max.poll.interval.ms`. | Đo thời gian từ đầu poll đến lần poll tiếp theo; xem số record mỗi poll và thời gian listener. |
| Consumer mất partition khi một dịch vụ bên ngoài chậm | Listener bị block trong lời gọi đồng bộ hoặc retry. | Kiểm tra timeout HTTP/database, backoff và thời gian xử lý tail latency. |
| Lag tăng dù consumer vẫn có heartbeat | Consumer chưa hoàn tất công việc và không gọi poll đủ thường xuyên, hoặc thông lượng thấp hơn tốc độ producer. | Đo poll cadence, thời gian xử lý, số record mỗi giây và lag theo partition. |
| Rebalance xong thì một số nghiệp vụ xuất hiện hai lần | Record đã tạo hiệu ứng bên ngoài nhưng offset chưa commit trước khi partition được giao lại. | Đối chiếu event ID, offset, commit log và cơ chế idempotency. |
| Tăng concurrency nhưng throughput không tăng | Số partition ít, partition nóng hoặc nút thắt nằm ở database/dịch vụ đích. | Kiểm tra assignment, phân bố key, mức sử dụng CPU và thời gian I/O. |
| Đặt poll interval rất lớn nhưng consumer vẫn chậm | Đã nới giới hạn phát hiện consumer chậm mà chưa giải quyết thời gian xử lý hoặc nút thắt. | Xem throughput, lag, timeout và thời gian xử lý thực tế. |

Khi thấy lỗi commit hoặc log báo poll timeout, cần đọc toàn bộ log quanh thời điểm rebalance. Một lỗi commit có thể là hậu quả của việc group đã thay đổi membership; nó không nhất thiết là nguyên nhân gốc. Cần đối chiếu thời điểm listener bắt đầu, listener hoàn tất, lần poll kế tiếp, thời điểm commit và thời điểm partition bị revoke.

## 10. Theo dõi poll loop trong vận hành

Chỉ theo dõi consumer lag là chưa đủ. Lag cho biết tiến độ đã commit đang cách cuối log bao xa, nhưng không chỉ ra chính xác vì sao consumer chậm. Nên kết hợp các tín hiệu sau:

- Thời gian xử lý listener theo record và theo batch, đặc biệt các percentile cao.
- Thời gian giữa hai lần poll hoặc tuổi của lần poll gần nhất nếu hệ thống giám sát có cung cấp.
- Số record nhận mỗi poll và phân bố batch size.
- Thời gian commit offset và số lần commit thất bại.
- Số lần rebalance, partition bị revoke/assign và thời gian chuyển giao.
- Số lần retry, tổng thời gian backoff, số record chuyển sang dead-letter topic.
- Consumer lag theo từng partition và tốc độ tăng/giảm lag.
- Thời gian gọi database, HTTP service, mức sử dụng CPU và thời gian GC pause.

Khi điều tra, hãy log `topic`, `partition`, `offset`, event ID và thời gian xử lý. Những thông tin này giúp nối một record cụ thể với log nghiệp vụ và tiến độ của consumer group. Không nên log toàn bộ payload nhạy cảm chỉ để chẩn đoán; metadata thường đủ để truy vết.

## 11. Quy trình điều chỉnh thực tế

Khi consumer gặp rebalance do poll timeout, có thể tiến hành theo trình tự sau:

1. Xác nhận log cho thấy consumer thực sự vượt `max.poll.interval.ms`, thay vì mất kết nối hoặc bị rebalance bởi thay đổi thành viên khác.
2. Đo thời gian xử lý từ lúc `poll()` trả record đến lần `poll()` kế tiếp ở tải đại diện và tải đỉnh.
3. Xác định thời gian chủ yếu nằm ở listener, batch size, retry/backoff, database, HTTP hay GC.
4. Nếu batch quá lớn, giảm `max.poll.records` và đo lại throughput cùng poll cadence.
5. Nếu xử lý đồng bộ quá lâu, tối ưu I/O, đặt timeout, pause/resume có kiểm soát hoặc chuyển sang kiến trúc async/retry phù hợp.
6. Chỉ tăng `max.poll.interval.ms` khi thời gian xử lý dài là có chủ đích, có giới hạn và đã được đo. Chừa biên dự phòng cho tải đỉnh và sự cố tạm thời.
7. Kiểm tra idempotency và khả năng xử lý lại record sau rebalance; xác nhận offset chỉ sau khi công việc cần bảo đảm đã hoàn tất.
8. Theo dõi lag, rebalance và thời gian listener sau thay đổi để xác nhận hệ thống ổn định.

`max.poll.interval.ms` là giới hạn thời gian để consumer chứng minh rằng vòng lặp xử lý vẫn tiếp tục tiến triển. Vận hành ổn định cần phối hợp kích thước batch, thời gian xử lý, retry, cách acknowledgment và năng lực của các dịch vụ phụ thuộc. Khi mỗi consumer quay lại `poll()` đúng hạn và các nghiệp vụ chịu được việc giao lại, consumer group sẽ ít rebalance ngoài ý muốn hơn và có thể khôi phục tiến độ đáng tin cậy sau sự cố.

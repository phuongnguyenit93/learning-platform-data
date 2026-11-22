# Poll loop và chu kỳ lấy dữ liệu

Kafka consumer nhận dữ liệu bằng cách chủ động gọi `poll()` để lấy các record mà broker đang lưu. Vòng lặp gọi poll liên tục được gọi là **poll loop**. Mỗi lần poll có thể trả về một tập record từ nhiều partition đã được gán cho consumer; consumer xử lý tập record đó rồi tiếp tục poll để nhận dữ liệu mới.

Trong ứng dụng Spring Kafka, thông thường bạn không tự viết vòng `while` và gọi `KafkaConsumer.poll()` trong service. Listener container của Spring Kafka quản lý consumer, poll loop, việc gọi phương thức `@KafkaListener`, điều phối offset và vòng đời consumer. Hiểu chu kỳ poll vẫn rất quan trọng vì nó quyết định lượng dữ liệu nhận mỗi lần, thời gian consumer có thể xử lý một batch, cách group phát hiện consumer chậm và khả năng mở rộng xử lý song song.

## 1. Consumer chủ động lấy dữ liệu

Kafka producer gửi record đến broker, còn consumer chủ động yêu cầu broker trả dữ liệu. Broker không gọi ngược vào ứng dụng để đẩy từng message. Consumer dùng `poll(Duration)` để nhận dữ liệu và duy trì hoạt động tham gia consumer group.

Một poll có thể trả về:

- Nhiều record thuộc cùng một partition.
- Record từ nhiều partition được gán cho consumer.
- Một tập rỗng nếu chưa có dữ liệu phù hợp trong khoảng chờ.

Vì vậy, một lần `poll()` không tương đương với việc nhận đúng một message. Nó là một chu kỳ lấy một tập record mà client hiện có thể trả về theo cấu hình fetch, số record tối đa và dữ liệu sẵn có.

## 2. Các bước trong poll loop

Một poll loop ở mức Kafka client có thể mô tả như sau:

```text
KafkaConsumer thread
       |
       v
   poll(timeout)
       |
       v
 Kiểm tra group, metadata,
 fetch dữ liệu cần thiết
       |
       v
 Trả ConsumerRecords
       |
       v
 Xử lý các record
       |
       v
 Commit offset theo chính sách
       |
       +----------> poll() tiếp theo
```

Đây là mô hình khái quát. Kafka client có thể gửi fetch request bất đồng bộ, nhận dữ liệu và lưu đệm trước khi ứng dụng gọi poll kế tiếp. Việc poll còn tham gia vào quá trình điều phối consumer group và cập nhật tiến độ xử lý. Chi tiết heartbeat phụ thuộc giao thức group và phiên bản Kafka client; không nên xem poll timeout là heartbeat interval.

Ví dụ Java thuần để thấy vòng lặp:

```java
import java.time.Duration;
import java.util.Collections;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

public class BasicPollLoop {

    public void consume(KafkaConsumer<String, String> consumer) {
        consumer.subscribe(Collections.singletonList("orders.events"));

        try {
            while (true) {
                ConsumerRecords<String, String> records =
                        consumer.poll(Duration.ofMillis(1000));

                for (ConsumerRecord<String, String> record : records) {
                    System.out.printf(
                            "topic=%s partition=%d offset=%d key=%s value=%s%n",
                            record.topic(),
                            record.partition(),
                            record.offset(),
                            record.key(),
                            record.value());
                }
            }
        }
        finally {
            consumer.close();
        }
    }
}
```

Ví dụ chỉ minh họa cơ chế poll của Kafka client. Code production cần xử lý shutdown có kiểm soát, exception, commit offset, rebalance và cấu hình bảo mật. Không dùng cùng một `KafkaConsumer` đồng thời từ nhiều thread; Kafka consumer không thread-safe và cần được sở hữu bởi một luồng điều khiển poll.

## 3. Chu kỳ fetch giữa consumer và broker

`poll()` là API mà ứng dụng gọi, còn **fetch** là giao thức client dùng để yêu cầu broker gửi dữ liệu từ các partition. Hai khái niệm liên quan nhưng không đồng nhất.

Chu kỳ fetch có thể diễn ra như sau:

1. Consumer biết các partition đang được gán và vị trí offset cần đọc.
2. Kafka client gửi fetch request đến broker leader của các partition tương ứng.
3. Broker trả các record batch đang có sẵn, hoặc chờ trong giới hạn cấu hình nếu chưa đủ dữ liệu.
4. Client nhận và lưu đệm dữ liệu.
5. Lần `poll()` trả record từ dữ liệu đã fetch và tiếp tục kích hoạt tiến trình lấy dữ liệu khi cần.

Client có thể fetch từ nhiều broker và nhiều partition. Một poll có thể trả dữ liệu đã nằm trong buffer; ngược lại, poll có thể chưa trả record nào nếu chưa có dữ liệu phù hợp hoặc thời gian chờ đã hết.

## 4. Các cấu hình ảnh hưởng đến poll và fetch

Kafka có một số thuộc tính điều khiển lượng dữ liệu nhận và thời gian fetch. Cần hiểu đúng từng thuộc tính vì chúng tác động đến throughput, latency, bộ nhớ và khả năng duy trì consumer group.

| Cấu hình | Vai trò |
| --- | --- |
| `max.poll.records` | Giới hạn số record tối đa ứng dụng nhận được trong một lần `poll()` |
| `max.poll.interval.ms` | Thời gian tối đa giữa hai lần gọi poll trước khi consumer bị xem là không còn tiến triển và có thể rời group |
| `fetch.min.bytes` | Lượng dữ liệu tối thiểu broker cố gắng gom trước khi trả fetch response |
| `fetch.max.wait.ms` | Thời gian tối đa broker chờ để đạt `fetch.min.bytes` trước khi trả response |
| `max.partition.fetch.bytes` | Giới hạn dữ liệu fetch cho mỗi partition trong một request |
| `fetch.max.bytes` | Giới hạn tổng dữ liệu fetch response mà client yêu cầu trong một request |
| `poll(Duration)` | Thời gian tối đa API poll chờ dữ liệu trước khi trả về; không phải giới hạn thời gian xử lý record |
| `session.timeout.ms` | Thời gian broker chờ heartbeat hợp lệ trước khi xem consumer là không hoạt động trong classic group protocol |
| `heartbeat.interval.ms` | Khoảng thời gian heartbeat trong classic group protocol; thường nhỏ hơn session timeout |

Một số thuộc tính trên có thể có cách xử lý hoặc giới hạn khác nhau giữa classic consumer group protocol và consumer group protocol mới. Hãy kiểm tra tài liệu của phiên bản Kafka client đang dùng.

### `max.poll.records`

`max.poll.records` giới hạn số record trả về cho ứng dụng trong một lần poll. Ví dụ, đặt giá trị 100 nghĩa là một lần poll không trả quá 100 record. Thuộc tính này không trực tiếp giới hạn lượng byte mà broker fetch; Kafka client có thể fetch và buffer nhiều dữ liệu hơn rồi phân phối cho các lần poll tiếp theo.

Giảm giá trị có thể làm mỗi lượt xử lý ngắn hơn, giúp consumer gọi poll thường xuyên hơn. Nhưng giá trị quá thấp có thể tăng overhead và giảm throughput. Tăng giá trị có thể cải thiện hiệu quả xử lý batch, nhưng làm tăng thời gian xử lý một poll và lượng record cần giữ trong bộ nhớ.

### `max.poll.interval.ms`

Đây là giới hạn thời gian giữa hai lần gọi poll. Nếu ứng dụng nhận một batch rồi xử lý quá lâu trước khi gọi poll tiếp, consumer có thể bị xem là không còn tiến triển và group có thể thực hiện rebalance.

Ví dụ, nếu `max.poll.interval.ms` là 300.000 ms (5 phút), tổng thời gian xử lý record trong một poll, cộng thời gian xử lý phụ trước lần poll tiếp theo, cần nằm trong giới hạn này với khoảng dự phòng hợp lý.

Không nhầm `max.poll.interval.ms` với `poll(Duration)`. Một poll có thể chờ tối đa một giây để lấy dữ liệu, nhưng việc xử lý batch sau đó có thể kéo dài nhiều phút. `poll(Duration)` không tự giới hạn thời gian xử lý đó.

### `fetch.min.bytes` và `fetch.max.wait.ms`

Hai thuộc tính này điều khiển việc broker gom dữ liệu trước khi trả fetch response. `fetch.min.bytes` càng cao thì broker có thể chờ dữ liệu tích lũy nhiều hơn, giúp tăng hiệu quả batch nhưng có thể tăng latency. `fetch.max.wait.ms` giới hạn thời gian chờ đó.

Với ứng dụng cần phản hồi nhanh, thường dùng giá trị fetch min nhỏ và fetch wait thấp. Với luồng dữ liệu lớn, có thể tăng mức gom batch nếu chấp nhận độ trễ bổ sung.

### Giới hạn byte fetch

`max.partition.fetch.bytes` giới hạn dữ liệu lấy từ mỗi partition, còn `fetch.max.bytes` giới hạn tổng dữ liệu trong fetch response. Các giá trị này cần đủ lớn cho record batch lớn nhất mà producer có thể ghi. Kafka có ngoại lệ cho batch đầu tiên của partition trong một số trường hợp để consumer vẫn có thể tiến lên; vì vậy các giá trị này không nên được hiểu là hàng rào tuyệt đối ngăn mọi batch lớn hơn.

## 5. Spring Kafka listener container quản lý poll loop

Với Spring Kafka, listener container tạo và quản lý `KafkaConsumer`. Container chạy poll loop, lấy record rồi gọi phương thức listener do ứng dụng khai báo.

Ví dụ:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection")
    public void onMessage(ConsumerRecord<String, String> record) {
        System.out.printf("order event: key=%s value=%s%n",
                record.key(), record.value());
    }
}
```

Ứng dụng không cần tự gọi `poll()`. Listener container thực hiện việc đó và gọi `onMessage` khi nhận record. Trong listener thông thường, phần xử lý chạy trên luồng consumer do container quản lý. Khi listener hoàn tất, container tiếp tục chu kỳ poll và xử lý offset theo cấu hình acknowledgement.

Các cấu hình `spring.kafka.consumer.*` được dùng để tạo consumer; cấu hình listener container nằm trong `spring.kafka.listener.*` và các thuộc tính của `ConcurrentKafkaListenerContainerFactory`/`ContainerProperties`. Không nên nhầm cấu hình Kafka client với cấu hình container: `max.poll.records` thuộc consumer client, còn `pollTimeout` là thời gian chờ truyền cho lời gọi poll do container thực hiện.

## 6. Cấu hình poll và fetch trong Spring Boot

Có thể đặt cấu hình consumer trong `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        "[max.poll.interval.ms]": 300000
        "[fetch.min.bytes]": 1
        "[fetch.max.wait.ms]": 500
        "[max.partition.fetch.bytes]": 1048576
        "[fetch.max.bytes]": 52428800
    listener:
      concurrency: 3
```

Trong ví dụ:

- Mỗi poll trả tối đa 100 record.
- Consumer cần tiếp tục poll trong vòng 5 phút.
- Broker có thể chờ tối đa 500 ms để gom fetch data nếu chưa đủ 1 byte tối thiểu.
- Giới hạn fetch theo partition và toàn response được đặt ở mức minh họa.
- Listener container được cấu hình concurrency bằng ba.

Các giá trị trên không phải bộ thông số tối ưu cho mọi ứng dụng. Hãy bắt đầu từ tải thực tế, kích thước record, thời gian xử lý và số partition. Spring Boot cho phép đặt thuộc tính Kafka client chưa có trường cấu hình chuyên biệt trong `consumer.properties`; cú pháp bracket giúp giữ nguyên tên property có dấu chấm.

`enable-auto-commit: false` phù hợp với cách Spring Kafka listener container quản lý commit offset. Trong Spring Kafka, nếu không chỉ định, framework thường đặt auto commit thành false; khai báo rõ trong ví dụ giúp thể hiện chủ đích. Việc commit cụ thể vẫn phụ thuộc `AckMode` của container.

## 7. Poll, xử lý record và commit offset

Poll lấy record không đồng nghĩa record đã được xử lý thành công. Consumer cần xác định khi nào tiến độ đọc được commit.

Trong Spring Kafka, listener container quản lý acknowledgement và commit theo `AckMode`. Với cấu hình mặc định phổ biến `BATCH`, offset được commit sau khi tất cả record trả về từ một poll đã được xử lý. Các chế độ khác như `RECORD`, `MANUAL` và `MANUAL_IMMEDIATE` cho phép điều chỉnh thời điểm xác nhận theo yêu cầu.

Ví dụ luồng xử lý:

```text
poll() trả 50 record
       |
       v
listener xử lý record/batch
       |
       +-- thành công theo AckMode --> commit offset
       |
       +-- có lỗi ------------------> error handler / retry policy
                                      |
                                      v
                               quyết định retry, seek,
                               recover hoặc DLT
       |
       v
poll() tiếp theo
```

Nếu ứng dụng commit offset trước khi hoàn tất tác vụ nghiệp vụ, lỗi xảy ra sau đó có thể làm record không được đọc lại. Ngược lại, nếu xử lý xong nhưng dừng trước khi commit, record có thể được giao lại. Vì vậy, consumer thường cần xử lý idempotent hoặc có cơ chế chống trùng phù hợp.

Không tự commit offset chỉ vì poll đã trả dữ liệu. Hãy hiểu `AckMode`, error handler và retry policy đang dùng trong listener container.

## 8. Record listener và batch listener

Một poll có thể trả nhiều record. Spring Kafka hỗ trợ hai kiểu listener chính:

- **Record listener:** container gọi phương thức cho từng record. Mã nghiệp vụ xử lý từng event một, dù poll có thể trả nhiều record.
- **Batch listener:** container chuyển tập record của một poll cho một lần gọi listener. Mã nghiệp vụ có thể xử lý theo lô.

Ví dụ batch listener:

```java
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderBatchListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-batch-projection",
            containerFactory = "batchKafkaListenerContainerFactory")
    public void onMessages(List<ConsumerRecord<String, String>> records) {
        for (ConsumerRecord<String, String> record : records) {
            // Chuyển đổi và xử lý record trong batch.
        }
    }
}
```

Factory `batchKafkaListenerContainerFactory` cần được cấu hình với `setBatchListener(true)` và consumer factory phù hợp. Nếu dùng record listener mặc định, không thể chỉ đổi kiểu tham số thành `List` mà mong container tự chuyển sang batch mode.

Batch listener có thể giảm overhead gọi phương thức và tận dụng batch insert/update. Đổi lại, thời gian xử lý cả batch phải nằm trong giới hạn poll interval và logic lỗi cần xác định record nào thành công hoặc thất bại theo chính sách của container.

## 9. Thời gian xử lý và nguy cơ vượt max.poll.interval.ms

Giả sử `max.poll.records=100`, mỗi record mất trung bình 100 ms để xử lý tuần tự. Thời gian xử lý danh nghĩa của batch là:

```text
100 record x 100 ms = 10.000 ms = 10 giây
```

Nếu có truy vấn database chậm, gọi HTTP bên ngoài hoặc retry đồng bộ, thời gian thực tế có thể cao hơn nhiều. Khi tổng thời gian giữa hai lần poll vượt `max.poll.interval.ms`, consumer có thể rời group và partition được gán lại cho consumer khác.

Để giảm rủi ro:

1. Đo thời gian xử lý thực tế ở percentile cao, không chỉ nhìn trung bình.
2. Chọn `max.poll.records` phù hợp với thời gian xử lý từng record và batch.
3. Tăng `max.poll.interval.ms` khi nghiệp vụ cần thời gian xử lý dài, nhưng vẫn cần có giới hạn và giám sát.
4. Dùng batch operation hiệu quả nếu có thể giảm thời gian mỗi record.
5. Tránh chờ vô hạn vào dịch vụ bên ngoài trong listener.
6. Dùng pause/resume hoặc backpressure có kiểm soát khi downstream tạm thời không đáp ứng.

Không nên chỉ tăng `max.poll.interval.ms` để che một consumer bị treo. Cần có timeout cho I/O, quan sát thời gian xử lý và chiến lược phục hồi.

## 10. Concurrency và số partition

Trong Spring Kafka, `concurrency` của listener container xác định số consumer thread/container con được tạo cho listener. Mỗi consumer có vòng poll riêng và được Kafka group coordinator gán partition.

Ví dụ topic có sáu partition:

```text
Topic: orders.events (6 partitions)

concurrency = 1  -> 1 consumer xử lý 6 partitions
concurrency = 3  -> 3 consumers, thường khoảng 2 partitions mỗi consumer
concurrency = 6  -> tối đa 6 consumers có partition được gán
concurrency = 8  -> 2 consumer có thể không được gán partition
```

Đây là minh họa phân bổ cân bằng; kết quả thực tế phụ thuộc assignor, số consumer trong toàn group và các thành viên khác. Trong cùng consumer group, một partition tại một thời điểm chỉ được gán cho một consumer. Vì vậy, concurrency cao hơn số partition không làm một partition được xử lý song song bởi nhiều consumer.

Tăng concurrency có thể tăng throughput khi có đủ partition và downstream đủ năng lực. Nó cũng làm tăng số consumer connection, thread và tải lên broker/database. Chọn concurrency theo partition count, thông lượng và tài nguyên thực tế.

## 11. Pause, resume và backpressure

Khi database hoặc dịch vụ phía sau bị quá tải, consumer có thể cần tạm ngừng nhận record từ một số partition. Kafka client hỗ trợ `pause()` và `resume()` theo partition. Spring Kafka listener container cung cấp các API tương ứng để điều phối consumer trong luồng container.

Pause không đồng nghĩa đóng consumer hoặc rời group. Container vẫn có thể tiếp tục poll để duy trì hoạt động group và xử lý các partition không bị pause. Khi downstream sẵn sàng, container resume để tiếp tục lấy record.

Pause/resume hữu ích khi triển khai backpressure, nhưng cần tránh pause quá lâu đến mức vượt giới hạn poll hoặc làm consumer mất tiến độ. Cần theo dõi consumer lag và thời gian pause, đồng thời xác định rõ điều kiện resume.

## 12. Theo dõi poll loop trong vận hành

Để biết consumer có lấy và xử lý dữ liệu đều đặn hay không, cần theo dõi cả Kafka client lẫn ứng dụng:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Consumer lag theo partition | Khoảng cách giữa offset đã commit và log end offset |
| Records consumed rate | Số record consumer xử lý trong một đơn vị thời gian |
| Bytes consumed rate | Lượng dữ liệu đọc từ Kafka |
| Fetch latency | Thời gian phản hồi fetch request |
| Fetch size / records per request | Lượng dữ liệu broker trả cho consumer |
| Processing time | Thời gian listener xử lý một record hoặc batch |
| Poll interval | Khoảng cách thực tế giữa các lần poll |
| Rebalance count/time | Tần suất và thời gian consumer group tái phân bổ partition |

Consumer lag tăng liên tục có thể do producer tăng tải, consumer xử lý chậm, fetch không đủ dữ liệu hoặc downstream bị nghẽn. Cần so sánh lag với processing rate và thời gian poll để tìm nguyên nhân.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Listener nhận nhiều record lâu mới xong | `max.poll.records` cao hoặc xử lý từng record chậm | Đo processing time và điều chỉnh batch size |
| Consumer thường xuyên rebalance | Xử lý batch vượt `max.poll.interval.ms`, lỗi kết nối hoặc thay đổi thành viên group | Kiểm tra poll interval, I/O timeout, heartbeat/session và log rebalance |
| Consumer lag tăng liên tục | Tốc độ xử lý thấp hơn tốc độ producer | Tối ưu xử lý, tăng concurrency nếu có partition và tài nguyên |
| Poll thường xuyên trả batch rỗng | Topic ít dữ liệu, fetch wait hoặc subscription/assignment chưa đúng | Kiểm tra topic, assignment và fetch settings |
| Latency cao nhưng throughput thấp | `fetch.min.bytes` hoặc `fetch.max.wait.ms` quá cao với tải thấp | Giảm thời gian gom batch nếu ưu tiên latency |
| Consumer mất dữ liệu sau lỗi | Commit offset trước khi xử lý hoàn tất hoặc error handling không phù hợp | Kiểm tra AckMode, commit và recovery strategy |
| Bộ nhớ consumer tăng | Batch/fetch quá lớn hoặc giữ record lâu trong ứng dụng | Giảm kích thước batch/fetch, tránh giữ payload không cần thiết |

## 14. Kết luận

Poll loop là chu kỳ trung tâm của Kafka consumer: consumer gọi `poll()`, nhận một tập record từ dữ liệu fetch đã có, xử lý và tiếp tục poll. Fetch là hoạt động giao thức giữa client và broker; các thuộc tính như `fetch.min.bytes`, `fetch.max.wait.ms` và giới hạn byte điều khiển cách dữ liệu được gom và trả về. `max.poll.records` giới hạn số record mỗi poll, còn `max.poll.interval.ms` giới hạn thời gian giữa các lần poll.

Trong Spring Kafka, listener container quản lý poll loop và gọi `@KafkaListener`. Để consumer ổn định, cần cân bằng kích thước batch, thời gian xử lý, commit offset, concurrency và số partition; đồng thời giám sát consumer lag, poll interval và rebalance. Khi hiểu đúng chu kỳ này, bạn có thể điều chỉnh throughput và latency mà vẫn giữ consumer group hoạt động ổn định.

## Tài liệu tham khảo

- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka — KafkaConsumer API](https://kafka.apache.org/documentation/#consumerapi)
- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/annotation-driven.html)

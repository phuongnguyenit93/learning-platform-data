# max.poll.interval.ms và trường hợp xử lý quá lâu

Kafka consumer phải tiếp tục gọi `poll()` để nhận dữ liệu, duy trì tiến độ của consumer group và tham gia xử lý rebalance. Khi ứng dụng xử lý một lô record quá lâu rồi không gọi `poll()` trong thời gian cấu hình, Kafka có thể xem consumer là không còn tiến triển và phân công partition cho consumer khác.

Thuộc tính `max.poll.interval.ms` đặt giới hạn thời gian tối đa giữa hai lần gọi `poll()` liên tiếp. Đây là cấu hình quan trọng khi mỗi record cần gọi dịch vụ bên ngoài, xử lý nghiệp vụ nặng, ghi database hoặc khi một poll trả về nhiều record. Hiểu đúng giới hạn này giúp tránh rebalance lặp lại, xử lý trùng và commit offset sai.

## 1. Poll loop và nhịp tiến triển của consumer

Một consumer group chia các partition cho các thành viên. Mỗi consumer phải thường xuyên gọi `poll()` để lấy record và tham gia giao thức quản lý group.

Một vòng lặp xử lý đồng bộ thường có dạng:

~~~mermaid
flowchart TD
    A["Gọi poll()"] --> B["Nhận một batch record"]
    B --> C["Xử lý từng record"]
    C --> D["Commit offset sau khi xử lý thành công"]
    D --> E{"Còn chạy?"}
    E -->|Có| A
    E -->|Không| F["Đóng consumer"]
~~~

Với cách xử lý tuần tự, consumer chỉ gọi `poll()` lần tiếp theo sau khi đã xử lý batch hiện tại. Thời gian từ lúc `poll()` trả về đến lần gọi `poll()` tiếp theo gồm:

- Thời gian xử lý tất cả record trong batch.
- Thời gian gọi database, HTTP API hoặc dịch vụ khác.
- Thời gian retry nội bộ của ứng dụng.
- Thời gian commit offset.
- Thời gian callback, ghi log, serialize và các công việc phụ.
- Thời gian pause hoặc chờ tài nguyên nếu ứng dụng không tiếp tục poll.

Nếu tổng thời gian này vượt quá `max.poll.interval.ms`, consumer đã vượt giới hạn tiến triển dù tiến trình Java vẫn sống và kết nối mạng vẫn hoạt động.

## 2. max.poll.interval.ms là gì?

`max.poll.interval.ms` là cấu hình phía consumer xác định khoảng thời gian tối đa được phép giữa các lần gọi `KafkaConsumer.poll()`.

Giá trị mặc định thường dùng của Kafka Java consumer là **300.000 ms (5 phút)**.

~~~properties
max.poll.interval.ms=300000
~~~

Nếu ứng dụng không gọi `poll()` trước khi khoảng thời gian này hết hạn, consumer bị xem là không còn tiến triển. Consumer group sẽ thực hiện rebalance để partition có thể được giao cho thành viên khác.

Kafka đo **khoảng cách giữa các lần gọi `poll()`**, không đo riêng thời gian xử lý của một hàm nghiệp vụ. Tuy nhiên, khi ứng dụng xử lý đồng bộ ngay sau `poll()`, thời gian xử lý record chính là phần lớn khoảng cách đó.

Ví dụ:

- Consumer gọi `poll()` lúc 10:00:00.
- `poll()` trả về 100 record.
- Ứng dụng xử lý tuần tự batch trong 4 phút 30 giây.
- Ứng dụng commit offset và gọi `poll()` tiếp theo lúc 10:04:40.

Khoảng cách gần 280 giây vẫn thấp hơn 300 giây. Nếu xử lý kéo dài đến hơn 5 phút, consumer vượt giới hạn và có thể bị loại khỏi group.

`max.poll.interval.ms` không phải thời gian timeout của một record ở broker, không phải thời gian chờ tối đa của `poll(Duration)`, cũng không phải thời gian chờ HTTP hoặc database. Đây là giới hạn nhịp gọi poll của consumer.

## 3. Điều gì xảy ra khi xử lý quá lâu?

Giả sử group `billing-workers` có hai consumer và topic `invoices` có bốn partition:

- Consumer A đang sở hữu partition 0 và 1.
- Consumer B đang sở hữu partition 2 và 3.
- Consumer A nhận một batch có một số record cần gọi dịch vụ thanh toán chậm.
- Ứng dụng A không gọi `poll()` trong hơn `max.poll.interval.ms`.

Quá trình có thể diễn ra như sau:

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant K as Kafka Group Coordinator
    participant B as Consumer B
    A->>K: Poll / duy trì membership
    K-->>A: Batch record của partition 0, 1
    Note over A: Xử lý nghiệp vụ kéo dài
    Note over A,K: Không có poll mới trong max.poll.interval.ms
    A->>K: Consumer bị xem là không còn tiến triển
    K->>B: Bắt đầu rebalance và phân công partition
    K-->>B: Giao thêm partition 0 hoặc 1
    Note over A,B: A có thể đã xử lý một phần batch
    B->>K: Poll với assignment mới
~~~

Các hệ quả thường gặp:

1. **Rebalance ngoài dự kiến:** coordinator cần phân công lại partition.
2. **Consumer khác nhận partition:** thành viên khác có thể bắt đầu xử lý những record mà consumer cũ chưa hoàn thành.
3. **Xử lý trùng:** nếu consumer cũ đã tạo side effect nhưng chưa commit offset, consumer mới có thể đọc lại record đó.
4. **Commit thất bại:** consumer cũ không còn là thành viên hợp lệ hoặc đã mất quyền sở hữu partition nên commit offset có thể thất bại.
5. **Độ trễ tăng:** trong lúc rebalance và khôi phục assignment, record có thể chờ lâu hơn.
6. **Rebalance lặp lại:** nếu consumer mới cũng xử lý quá lâu, group tiếp tục thay đổi assignment.

Vì vậy, một consumer xử lý chậm có thể ảnh hưởng đến các partition và thành viên khác trong cùng group. Đây không chỉ là vấn đề tốc độ của một hàm xử lý.

## 4. Phân biệt max poll interval với heartbeat và session timeout

Kafka có nhiều cơ chế phát hiện consumer không còn hoạt động. Chúng giải quyết các loại vấn đề khác nhau.

| Cấu hình | Mục đích | Tình huống được phát hiện |
|---|---|---|
| `max.poll.interval.ms` | Giới hạn khoảng cách giữa hai lần gọi poll | Consumer không tiếp tục tiến triển ở tầng ứng dụng |
| `session.timeout.ms` | Giới hạn thời gian coordinator chờ heartbeat | Consumer hoặc đường mạng không còn gửi heartbeat |
| `heartbeat.interval.ms` | Khoảng cách gửi heartbeat theo classic group protocol | Duy trì membership giữa các lần poll |
| `max.poll.records` | Giới hạn số record trả về trong một lần poll | Giới hạn kích thước batch ứng dụng nhận mỗi vòng |

Trong Java consumer hiện đại, heartbeat có thể được gửi bởi luồng nền trong khi luồng ứng dụng đang xử lý record. Vì vậy, consumer có thể vẫn gửi heartbeat nhưng không gọi `poll()` đủ nhanh. `max.poll.interval.ms` phát hiện tình huống ứng dụng không tiến triển này.

Với **classic group protocol**, cấu hình thường gặp là:

~~~properties
session.timeout.ms=45000
heartbeat.interval.ms=3000
max.poll.interval.ms=300000
~~~

`heartbeat.interval.ms` thường được đặt nhỏ hơn `session.timeout.ms` để coordinator nhận được nhiều cơ hội phát hiện heartbeat bị mất.

Kafka có consumer group protocol mới (`group.protocol=consumer`) ở các phiên bản hỗ trợ. Với protocol này, một số thiết lập heartbeat và session timeout được điều khiển phía broker thay vì dùng các thuộc tính client classic tương ứng. Cần kiểm tra tài liệu đúng phiên bản và protocol đang sử dụng trước khi thay đổi cấu hình.

Đừng nhầm rằng tăng `session.timeout.ms` sẽ giải quyết được việc xử lý batch quá lâu. Nếu ứng dụng không gọi `poll()` đúng hạn, giới hạn `max.poll.interval.ms` vẫn có thể bị vượt.

### 4.1 Dynamic membership và static membership

Với dynamic membership mặc định, consumer bị xem là không còn tiến triển có thể rời group và kích hoạt rebalance để partition được phân công lại.

Với static membership, ứng dụng cấu hình `group.instance.id` ổn định cho từng consumer instance. Cơ chế này giúp giảm rebalance không cần thiết khi một instance tạm thời khởi động lại. Tuy nhiên, static membership không loại bỏ giới hạn poll.

Khi static member vượt `max.poll.interval.ms`, consumer ngừng gửi heartbeat; partition chỉ được phân công lại sau khi `session.timeout.ms` hết hạn. Vì vậy, thời gian khôi phục có thể dài hơn dynamic member. `group.instance.id` phải duy nhất trong group; không dùng cùng một ID cho nhiều tiến trình chạy đồng thời.

## 5. Quan hệ giữa max poll interval và max poll records

`max.poll.records` giới hạn số record tối đa mà một lần `poll()` trả về cho ứng dụng. Giá trị mặc định thường là 500.

~~~properties
max.poll.records=500
max.poll.interval.ms=300000
~~~

Khi ứng dụng xử lý đồng bộ, số record trong một batch càng lớn thì thời gian xử lý trước lần poll kế tiếp càng dài.

Ví dụ, nếu mỗi record mất trung bình 700 ms để xử lý tuần tự:

- 20 record cần khoảng 14 giây.
- 100 record cần khoảng 70 giây.
- 500 record cần khoảng 350 giây.

Với batch 500 record, thời gian xử lý ví dụ đã vượt 5 phút, chưa tính commit, retry, garbage collection và các tác vụ khác.

Cần nhớ `max.poll.records` giới hạn số record trả về trong mỗi lần poll; nó không thay đổi giới hạn fetch dữ liệu ở broker. Consumer vẫn có thể fetch và lưu record trong bộ đệm nội bộ, sau đó trả về theo giới hạn mỗi lần poll.

### 5.1 Ước lượng thời gian cho một batch

Với xử lý tuần tự, có thể ước lượng:

\[
T_{batch} \approx N \times T_{record} + T_{overhead}
\]

Trong đó:

- `N`: số record tối đa có thể được xử lý trong một batch.
- `T_record`: thời gian xử lý một record.
- `T_overhead`: thời gian commit, callback, retry và các tác vụ phụ.

Ví dụ, ứng dụng xử lý tối đa 40 record, thời gian xử lý p99 của mỗi record là 1,5 giây và overhead 10 giây:

\[
T_{batch} \approx 40 \times 1.5 + 10 = 70\text{ giây}
\]

Con số này còn cách khá xa giới hạn 300 giây. Tuy nhiên, hãy kiểm tra thời gian ở tải cao và các trường hợp bất thường, không chỉ dùng thời gian trung bình.

Một nguyên tắc thực tế là giữ thời gian xử lý batch thấp hơn đáng kể so với `max.poll.interval.ms` để có dư địa cho spike, retry, GC pause và độ trễ hạ tầng.

### 5.2 Chọn batch size phù hợp

| Đặc điểm xử lý | Hướng điều chỉnh |
|---|---|
| Record nhẹ, xử lý nhanh | Có thể tăng `max.poll.records` để tăng throughput |
| Record gọi nhiều dịch vụ bên ngoài | Giảm `max.poll.records`, đặt timeout cho từng lời gọi |
| Record có thời gian xử lý biến động lớn | Dùng p95/p99 hoặc thời gian xấu có thể xảy ra để tính batch |
| Một record có thể mất vài phút | Cân nhắc xử lý bất đồng bộ hoặc tăng interval có kiểm soát |
| Database thường xuyên quá tải | Giảm batch và giới hạn concurrency để tránh dồn tải |

Giảm `max.poll.records` không làm một record xử lý chậm trở nên nhanh hơn. Nó chỉ giảm số lượng record có thể dồn vào cùng một khoảng giữa hai lần poll.

## 6. Ví dụ Java: xử lý đồng bộ và commit sau khi thành công

Với xử lý tuần tự, một cách an toàn cơ bản là tắt auto commit, giới hạn batch và commit sau khi toàn bộ batch đã xử lý thành công.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

public class InvoiceConsumer {
    public static void main(String[] args) {
        Properties props = new Properties();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(ConsumerConfig.GROUP_ID_CONFIG, "billing-workers");
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class.getName());
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class.getName());

        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
        props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, "40");
        props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, "300000");

        try (KafkaConsumer<String, String> consumer =
                     new KafkaConsumer<>(props)) {
            consumer.subscribe(List.of("invoices"));

            while (true) {
                ConsumerRecords<String, String> records =
                        consumer.poll(Duration.ofMillis(500));

                for (ConsumerRecord<String, String> record : records) {
                    processInvoice(record);
                }

                // Chỉ commit khi toàn bộ batch đã xử lý thành công.
                if (!records.isEmpty()) {
                    consumer.commitSync();
                }
            }
        }
    }

    private static void processInvoice(
            ConsumerRecord<String, String> record) {
        // Gọi service nghiệp vụ và chỉ trả về khi xử lý thành công.
        System.out.println("Processing invoice: " + record.key());
    }
}
~~~

Trong ví dụ:

- `enable.auto.commit=false` giúp ứng dụng chủ động quyết định thời điểm commit.
- `max.poll.records=40` giới hạn batch ứng dụng nhận trong một lần poll.
- `max.poll.interval.ms=300000` cho phép tối đa 5 phút giữa hai lần poll.
- `commitSync()` chỉ được gọi sau khi toàn bộ batch hoàn tất.

Đây là mẫu xử lý tuần tự đơn giản. Trong ứng dụng thật, cần có chính sách retry, dead-letter topic (DLT), logging, timeout và idempotency phù hợp. Nếu `processInvoice()` đã ghi database thành công nhưng consumer chết trước khi commit, record có thể được đọc lại. Vì vậy, side effect nghiệp vụ nên có khả năng xử lý lặp an toàn.

Không commit offset trước khi xử lý xong chỉ để tránh rebalance. Làm vậy có thể khiến record chưa xử lý bị bỏ qua khi consumer khác tiếp tục từ offset đã commit.

## 7. Cách xử lý khi một record thực sự mất nhiều thời gian

Có ba hướng chính. Hãy chọn theo đặc điểm nghiệp vụ và yêu cầu ordering.

### 7.1 Giảm số record trong mỗi poll

Đây là cách đơn giản nhất khi từng record chỉ hơi chậm hoặc thời gian xử lý tương đối ổn định.

~~~properties
max.poll.records=10
max.poll.interval.ms=300000
enable.auto.commit=false
~~~

Nếu mỗi record mất 10 giây và xử lý tuần tự, batch 10 record cần khoảng 100 giây cộng overhead. Consumer có thể gọi poll tiếp theo trước giới hạn 5 phút.

Nhược điểm là số lần poll tăng và throughput có thể giảm. Nếu một record riêng lẻ có thể mất hơn 5 phút thì giảm batch xuống 1 vẫn không giải quyết được.

### 7.2 Tăng max.poll.interval.ms có kiểm soát

Nếu một batch hợp lệ cần nhiều thời gian hơn, có thể tăng giới hạn:

~~~properties
max.poll.interval.ms=600000
max.poll.records=20
~~~

Giá trị 600.000 ms tương đương 10 phút. Chỉ tăng khi đã đo được thời gian xử lý thực tế và xác định consumer cần khoảng thời gian đó.

Cần đánh đổi:

- Consumer có thêm thời gian hoàn thành batch.
- Nếu ứng dụng thật sự bị treo, group có thể phải chờ lâu hơn trước khi phát hiện và phân công lại partition.
- Rebalance và phục hồi sau lỗi có thể chậm hơn.
- Một batch quá lớn vẫn có thể vượt giới hạn mới.

Không tăng interval vô hạn để che giấu xử lý chậm. Hãy đặt giới hạn timeout cho HTTP/database và tìm nguyên nhân gây kéo dài.

### 7.3 Dùng worker pool nhưng vẫn duy trì poll

Khi nghiệp vụ có thể chạy bất đồng bộ, có thể tách luồng lấy record và luồng xử lý:

~~~mermaid
flowchart TD
    P["Consumer poll thread"] --> Q["Bounded work queue"]
    Q --> W1["Worker 1"]
    Q --> W2["Worker 2"]
    Q --> W3["Worker N"]
    W1 --> R["Completion / offset tracker"]
    W2 --> R
    W3 --> R
    R --> P
    P --> C["Commit offset an toàn"]
    P --> S["Pause / resume partition"]
~~~

Luồng poll tiếp tục gọi `poll()` để duy trì membership. Worker xử lý record độc lập. Cách này giúp consumer tiếp tục tiến triển ngay cả khi một tác vụ nghiệp vụ kéo dài.

Tuy nhiên, cần quản lý offset và partition cẩn thận:

1. Chỉ một luồng sở hữu và gọi các API của `KafkaConsumer`; consumer không thread-safe.
2. Dùng queue có giới hạn để không nhận vô hạn record khi worker chậm.
3. Khi queue gần đầy, gọi `pause()` trên partition phù hợp; vẫn tiếp tục `poll()` để duy trì group.
4. Khi worker xử lý xong và queue có chỗ, gọi `resume()` trên poll thread.
5. Theo dõi offset hoàn thành riêng theo từng partition.
6. Chỉ commit offset sau phần record đã xử lý thành công liên tục từ đầu; không commit vượt qua một record còn đang xử lý.
7. Khi partition bị revoke, dừng dispatch, chờ phần công việc có thể hoàn tất trong giới hạn hợp lý và commit phần offset an toàn khi vẫn còn quyền.
8. Khi partition đã bị lost, không tiếp tục commit như thể consumer còn sở hữu nó.

`pause()` ngăn consumer trả thêm dữ liệu từ partition đã pause trong các lần poll tiếp theo; nó không thay thế `poll()` và không phải cơ chế giữ membership độc lập.

### 7.4 Giữ ordering khi xử lý bất đồng bộ

Nếu các record cùng partition được đưa vào nhiều worker và xử lý song song, record đến sau có thể hoàn thành trước record đến trước.

Ví dụ:

| Offset | Thời gian xử lý | Thứ tự hoàn thành |
|---:|---:|---:|
| 100 | 8 giây | 3 |
| 101 | 2 giây | 1 |
| 102 | 4 giây | 2 |

Nếu commit offset 103 ngay khi record 102 hoàn thành trong khi record 100 chưa xử lý xong, consumer có thể bỏ qua record 100 sau lần restart/rebalance. Để tránh điều này:

- Xử lý tuần tự theo từng partition nếu nghiệp vụ yêu cầu ordering.
- Hoặc dùng worker theo khóa/partition để bảo đảm thứ tự cần thiết.
- Duy trì completion tracker và chỉ commit qua offset liên tục đã hoàn tất.
- Làm side effect idempotent để xử lý an toàn khi record được giao lại.

Song song hóa có thể tăng throughput, nhưng làm tăng độ phức tạp của offset commit, rebalance và ordering. Không nên chỉ chuyển `process()` sang executor rồi tiếp tục gọi `commitSync()` cho toàn bộ batch như ví dụ đồng bộ.

## 8. Xử lý rebalance và quyền sở hữu partition

Khi consumer vượt `max.poll.interval.ms`, group có thể rebalance. Ứng dụng nên chuẩn bị cho việc partition bị thu hồi ngay cả khi code nghiệp vụ chưa hoàn tất.

Với `ConsumerRebalanceListener`, các callback quan trọng gồm:

- `onPartitionsRevoked`: partition sắp được thu hồi trong quy trình rebalance. Ứng dụng có thể dừng dispatch, chờ công việc có thể hoàn tất trong giới hạn hợp lý và commit phần offset an toàn khi vẫn còn quyền.
- `onPartitionsAssigned`: partition mới được giao. Ứng dụng khởi tạo trạng thái xử lý cho assignment mới.
- `onPartitionsLost`: partition đã mất quyền sở hữu. Không nên commit offset cho partition đã lost.

Trong callback revoke, không chờ vô hạn tất cả worker. Nếu công việc không thể hoàn thành trong thời gian rebalance cho phép, cần hủy hoặc để công việc kết thúc theo chính sách đã thiết kế. Consumer mới có thể đọc lại record chưa commit.

Cần phân biệt:

- **Rebalance:** thay đổi thành viên hoặc assignment của group.
- **Commit offset:** lưu tiến độ đã xử lý của group.
- **Xử lý nghiệp vụ:** side effect mà ứng dụng thực hiện với record.

Ba việc này không tự động diễn ra nguyên tử với nhau. Nếu xử lý database xong nhưng commit offset thất bại, record có thể được xử lý lại. Nếu commit trước khi xử lý, record có thể bị mất khỏi luồng xử lý của ứng dụng.

## 9. Cấu hình với Spring Kafka

Với Spring Boot, có thể cấu hình giới hạn batch và poll interval trong `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-workers
      enable-auto-commit: false
      max-poll-records: 40
      properties:
        max.poll.interval.ms: 300000
~~~

Spring Kafka quản lý poll loop bên trong listener container. Khi listener xử lý đồng bộ, thời gian xử lý các record thuộc poll hiện tại vẫn nằm trong khoảng thời gian giữa hai lần poll của container.

Với record listener:

- Container gọi listener cho từng record.
- Nếu một record chậm hoặc nhiều record liên tiếp xử lý lâu, container có thể không gọi poll tiếp theo kịp thời.
- Có thể giảm `max.poll.records`, tăng poll interval có kiểm soát hoặc cải thiện thời gian xử lý listener.

Với batch listener:

- Listener nhận một batch record từ một lần poll.
- Tổng thời gian xử lý batch phải nằm trong ngân sách poll interval.
- Cần chọn batch size theo thời gian xử lý thực tế của cả batch.

Ví dụ batch listener:

~~~java
@KafkaListener(
    topics = "invoices",
    groupId = "billing-workers",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consumeBatch(List<InvoiceEvent> events) {
    for (InvoiceEvent event : events) {
        invoiceService.process(event);
    }
}
~~~

Nếu `invoiceService.process()` có thể chậm, hãy đo thời gian xử lý batch và chọn `max.poll.records` phù hợp. Khi dùng manual acknowledgment, chỉ acknowledge sau khi phần công việc tương ứng đã thành công. Cấu hình ack mode và cách xử lý lỗi cần thống nhất với chiến lược commit offset của listener container.

Không tạo thread riêng trong listener rồi trả về ngay nếu chưa thiết kế đầy đủ việc theo dõi completion, ack, partition revoke và ordering. Khi listener trả về, container có thể tiếp tục poll và commit theo ack mode hiện tại, trong khi công việc nền vẫn chưa hoàn tất.

## 10. Theo dõi và chẩn đoán poll interval

Khi group rebalance bất thường, cần đối chiếu thời gian poll với thời gian xử lý thực tế.

Các tín hiệu nên theo dõi:

| Chỉ số | Điều cần quan sát |
|---|---|
| Processing duration | Thời gian xử lý một record và toàn bộ batch |
| Poll interval | Khoảng cách thực tế giữa hai lần gọi poll |
| Consumer lag | Khoảng cách giữa vị trí đọc và log end offset |
| Rebalance rate | Số lần group rebalance trong một khoảng thời gian |
| Commit latency/failure | Thời gian commit và lỗi commit |
| Worker queue depth | Số record đang chờ xử lý bất đồng bộ |
| Partition assignment | Partition thường xuyên bị revoke/assign |
| Error/retry rate | Số lần gọi dịch vụ ngoài thất bại hoặc retry |

Kafka client có các consumer metric về thời gian giữa các lần poll, thời gian poll gần nhất, commit latency và lag. Tên metric cụ thể phụ thuộc phiên bản client và hệ thống exporter.

### 10.1 Quy trình điều tra khi consumer bị rebalance do xử lý lâu

1. Xác định group và partition bị ảnh hưởng.
2. Đọc log consumer để tìm thông báo poll timeout, rebalance, commit failure và partition revoke.
3. Đo thời gian giữa hai lần `poll()` trên từng consumer instance.
4. Đo thời gian xử lý p95/p99 của record và batch, bao gồm retry và lời gọi dịch vụ ngoài.
5. Kiểm tra `max.poll.records`, `max.poll.interval.ms` và protocol group đang sử dụng.
6. Kiểm tra consumer có bị chờ database connection, HTTP response, thread pool hoặc queue hay không.
7. Đối chiếu thời điểm commit offset với thời điểm hoàn tất side effect.
8. Sau khi điều chỉnh, quan sát rebalance rate, consumer lag và thời gian poll để xác nhận group ổn định.

Nếu mọi consumer cùng bị chậm, hãy kiểm tra dịch vụ phụ thuộc hoặc hạ tầng dùng chung. Nếu chỉ một consumer gặp vấn đề, kiểm tra partition có dữ liệu gây xử lý lệch tải, một record bất thường hoặc worker pool riêng của instance đó.

## 11. Những hiểu nhầm thường gặp

**“Consumer vẫn gửi heartbeat thì không thể bị rebalance do xử lý lâu.”**  
Không đúng. Heartbeat có thể tiếp tục chạy trong luồng nền, nhưng ứng dụng vẫn phải gọi `poll()` trước khi `max.poll.interval.ms` hết hạn.

**“Tăng `session.timeout.ms` sẽ giải quyết lỗi max poll interval.”**  
Không đúng. Hai cấu hình phát hiện hai tình huống khác nhau. `max.poll.interval.ms` theo dõi tiến triển của ứng dụng; session timeout theo dõi heartbeat.

**“Giảm `max.poll.records` luôn tăng throughput.”**  
Không đúng. Batch nhỏ có thể giảm thời gian xử lý trước lần poll kế tiếp, nhưng làm tăng số vòng poll và overhead.

**“Một record chậm hơn max poll interval chắc chắn sẽ được xử lý xong nếu tăng số consumer.”**  
Không đúng. Một record vẫn có thể chậm trên một consumer. Tăng concurrency chỉ giúp khi partition và thiết kế xử lý cho phép chia tải.

**“Có thể commit offset ngay sau poll rồi xử lý sau.”**  
Cách này có thể làm mất record về mặt xử lý ứng dụng nếu consumer chết trước khi side effect hoàn tất.

**“Chỉ cần tăng max poll interval lên rất lớn.”**  
Điều này có thể làm chậm phát hiện consumer bị treo và trì hoãn phân công lại partition. Cần giới hạn thời gian xử lý và thiết kế retry/async phù hợp.

## 12. Checklist thiết kế consumer xử lý lâu

- [ ] Đo thời gian xử lý record và batch ở tải cao, bao gồm p95/p99 và các tình huống retry.
- [ ] Chọn `max.poll.records` theo ngân sách thời gian giữa hai lần poll.
- [ ] Đặt `max.poll.interval.ms` đủ lớn cho workload hợp lệ và có khoảng dự phòng.
- [ ] Phân biệt poll interval với heartbeat/session timeout theo group protocol.
- [ ] Tắt auto commit khi ứng dụng cần kiểm soát offset theo kết quả nghiệp vụ.
- [ ] Chỉ commit offset của phần record đã xử lý thành công.
- [ ] Có timeout và retry/backoff giới hạn cho database, HTTP và dịch vụ phụ thuộc.
- [ ] Nếu dùng worker pool, giữ `KafkaConsumer` trên một poll thread và dùng queue có giới hạn.
- [ ] Dùng pause/resume để kiểm soát backpressure nhưng vẫn tiếp tục poll.
- [ ] Theo dõi offset hoàn thành liên tục theo partition khi xử lý bất đồng bộ.
- [ ] Xử lý partition revoke/lost và không commit sau khi đã mất quyền sở hữu.
- [ ] Bảo đảm side effect idempotent để chịu được việc record được giao lại.
- [ ] Giám sát rebalance rate, poll interval, consumer lag và commit failure.

`max.poll.interval.ms` bảo vệ consumer group khỏi một thành viên không tiếp tục tiến triển ở tầng ứng dụng. Để xử lý record lâu ổn định, cần phối hợp giới hạn batch, thời gian xử lý, heartbeat, commit offset, backpressure và rebalance. Khi các giới hạn này được thiết kế cùng nhau, consumer có thể xử lý workload nặng mà vẫn duy trì membership và không làm sai tiến độ của luồng sự kiện.

## Tài liệu tham khảo

- [Apache Kafka Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs) — mô tả `max.poll.interval.ms`, `max.poll.records`, heartbeat và session timeout.
- [KafkaConsumer Java API](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html) — poll loop, pause/resume, commit và thread safety của consumer.
- [Kafka Consumer Design](https://kafka.apache.org/documentation/#design_consumer) — consumer group, assignment và cơ chế đọc dữ liệu.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/) — listener container, acknowledgment, batch listener và xử lý rebalance.

Tên cấu hình và hành vi group protocol có thể khác theo phiên bản Kafka. Hãy kiểm tra tài liệu đúng phiên bản client và broker đang triển khai trước khi thay đổi timeout trong production.

# Thử lại tại chỗ và ảnh hưởng đến poll, thứ tự, consumer lag

Consumer Kafka thường xử lý record trong vòng lặp gọi `poll()`. Khi một record gặp lỗi tạm thời, ứng dụng có thể thử xử lý lại ngay tại consumer thread trước khi chuyển sang record tiếp theo. Cách này được gọi là retry tại chỗ (in-place retry) hoặc blocking retry.

Retry tại chỗ dễ hiểu và có thể giữ thứ tự xử lý trong partition, nhưng thời gian chờ và xử lý lại làm consumer thread bận. Nếu tổng thời gian giữa hai lần `poll()` vượt `max.poll.interval.ms`, consumer có thể mất membership và kích hoạt rebalance. Trong lúc đó, các record phía sau bị chặn, offset chưa được commit và consumer lag có thể tăng.

Bài này phân tích tác động của retry tại chỗ đến poll loop, thứ tự, offset và lag; sau đó so sánh với pause/resume, retry topic và dead-letter topic để chọn cách phù hợp.

## 1. Retry tại chỗ diễn ra ở đâu?

Với consumer Java thông thường, một thread sở hữu `KafkaConsumer` và thực hiện các thao tác `poll()`, xử lý record, commit offset và điều khiển partition. Retry tại chỗ thường chạy ngay trong thread này:

1. Consumer gọi `poll()` và nhận một batch.
2. Ứng dụng xử lý record đầu tiên.
3. Nếu handler gặp lỗi tạm thời, ứng dụng chờ backoff rồi gọi handler lại.
4. Chỉ khi record thành công hoặc được xử lý theo chính sách lỗi đã định, ứng dụng mới chuyển sang record tiếp theo.
5. Sau khi hoàn tất batch, ứng dụng commit offset rồi gọi `poll()` tiếp.

~~~mermaid
flowchart TD
    A["poll() nhận batch"] --> B["Xử lý record hiện tại"]
    B --> C{"Xử lý thành công?"}
    C -->|Có| D["Chuyển record tiếp theo"]
    C -->|Không| E{"Còn lượt retry?"}
    E -->|Có| F["Backoff tại consumer thread"]
    F --> B
    E -->|Không| G["Dừng batch / DLT / xử lý lỗi"]
    D --> H{"Còn record trong batch?"}
    H -->|Có| B
    H -->|Không| I["Commit offset đã xử lý"]
    I --> J["poll() tiếp"]
~~~

Điểm đặc trưng là consumer không lấy batch tiếp theo trong lúc đang chờ retry. `poll()` tiếp theo chỉ diễn ra sau khi phần xử lý hiện tại kết thúc.

## 2. Vì sao retry tại chỗ có thể ảnh hưởng max.poll.interval.ms?

`max.poll.interval.ms` giới hạn thời gian tối đa giữa hai lần gọi `poll()`. Đây là cơ chế phát hiện consumer không tiếp tục tiến triển xử lý, khác với heartbeat/session timeout.

Với một batch, thời gian giữa hai lần poll có thể gồm:

`T_poll_gap = T_process_batch + T_retry_backoff + T_commit + T_application_overhead`

Trong đó:

- `T_process_batch`: tổng thời gian xử lý record trong batch.
- `T_retry_backoff`: tổng thời gian chờ giữa các lần retry.
- `T_commit`: thời gian commit offset hoặc hoàn tất transaction.
- `T_application_overhead`: serialize, logging, GC và công việc phụ khác.

Giả sử:

| Thành phần | Thời gian |
|---|---:|
| Xử lý các record bình thường | 18 giây |
| Một record lỗi, retry và backoff | 75 giây |
| Commit offset | 2 giây |
| Tổng khoảng giữa hai lần poll | 95 giây |

Nếu `max.poll.interval.ms=60000`, khoảng 95 giây vượt giới hạn. Consumer có thể bị xem là không còn tiến triển và rời group. Khi đó partition có thể được giao cho consumer khác, trong khi thread cũ vẫn đang chạy handler hoặc retry.

### 2.1. Heartbeat không thay thế poll progress

Kafka consumer có cơ chế heartbeat để coordinator biết member còn tham gia group. Với classic protocol, heartbeat thường được gửi bởi thread nền của client. Tuy nhiên, việc heartbeat còn hoạt động không có nghĩa consumer được phép không gọi `poll()` vô thời hạn.

`max.poll.interval.ms` theo dõi tiến độ gọi poll. Nếu ứng dụng giữ thread trong retry quá lâu, consumer có thể mất membership dù heartbeat đã từng hoạt động bình thường.

Với static membership (`group.instance.id`), khi vượt max poll interval, client ngừng heartbeat; việc thu hồi partition có thể chờ đến session timeout. Điều này có thể làm partition bị giữ lâu hơn khi instance thực sự đã treo. Chi tiết phụ thuộc protocol và phiên bản client/broker.

### 2.2. Chọn max.poll.records cùng max.poll.interval.ms

`max.poll.records` giới hạn số record trả về trong một lần poll. Giảm giá trị này có thể giảm thời gian xử lý batch và giảm số record phải xử lý lại khi có lỗi. Tuy nhiên, giảm quá thấp có thể làm giảm throughput do tăng overhead poll/request.

Không chỉ tính thời gian xử lý trung bình. Hãy dùng thời gian p95/p99 và trường hợp retry xấu nhất để đặt giới hạn có khoảng an toàn.

## 3. Retry tại chỗ ảnh hưởng thứ tự như thế nào?

Retry tại chỗ có một ưu điểm quan trọng: nếu consumer chỉ chuyển sang record tiếp theo sau khi record hiện tại thành công, thứ tự xử lý trong partition được giữ.

Ví dụ partition `orders-0` có các record:

| Offset | Event | Kết quả |
|---:|---|---|
| 100 | OrderCreated | Thành công |
| 101 | PaymentAuthorized | Lỗi tạm thời, retry |
| 102 | OrderPacked | Chưa xử lý |
| 103 | OrderShipped | Chưa xử lý |

Consumer retry offset 101 trước. Khi offset 101 thành công, nó mới xử lý 102 rồi 103. Như vậy, các event sau của cùng partition không vượt qua event đang lỗi.

### 3.1. Head-of-line blocking

Giữ thứ tự có giá phải trả: một record lỗi có thể chặn mọi record phía sau trong cùng partition. Đây là hiện tượng head-of-line blocking.

Nếu consumer thread xử lý tuần tự nhiều partition, retry đồng bộ có thể chặn cả các partition khác được giao cho cùng consumer, dù chỉ một partition có record lỗi.

Ví dụ consumer sở hữu ba partition:

~~~text
orders-0: offset 100 lỗi và đang retry
orders-1: offset 220 sẵn sàng xử lý
orders-2: offset 310 sẵn sàng xử lý
~~~

Nếu handler retry offset 100 bằng cách sleep trong consumer thread, offset 220 và 310 cũng phải chờ. Đây là khác biệt giữa blocking toàn consumer thread và chỉ tạm dừng một partition.

### 3.2. Nếu bỏ qua record lỗi rồi xử lý record sau

Nếu ứng dụng hết retry nhưng vẫn tiếp tục xử lý offset 102 và 103, thứ tự nghiệp vụ có thể bị phá vỡ. Ví dụ `OrderShipped` được xử lý trước khi `PaymentAuthorized` thành công.

Nếu commit offset 104 sau khi đã xử lý 102 và 103, consumer có thể bỏ qua offset 101 ở lần chạy tiếp theo. Vì vậy, không được commit vượt qua record chưa hoàn tất nếu yêu cầu thứ tự và không mất dữ liệu.

Khi hết retry, cần chọn rõ một trong các chính sách:

- Dừng xử lý partition và để record được đọc lại.
- Đưa record vào DLT thành công rồi xem nó là đã được xử lý theo chính sách nghiệp vụ.
- Chuyển record sang retry workflow riêng, đồng thời bảo vệ thứ tự nếu nghiệp vụ yêu cầu.
- Ghi nhận lỗi vĩnh viễn và commit chỉ khi nghiệp vụ cho phép bỏ qua event đó.

Không nên chỉ log lỗi rồi tiếp tục như thể record đã thành công.

## 4. Retry tại chỗ ảnh hưởng consumer lag ra sao?

Consumer lag thường được theo dõi bằng khoảng cách giữa log end offset và committed offset của group theo từng partition. Khi consumer retry tại chỗ:

- Producer vẫn có thể tiếp tục ghi record mới.
- Consumer chưa xử lý record hiện tại và các record sau.
- Offset commit thường chưa tiến lên.
- Khoảng cách giữa end offset và committed offset tăng.

Ví dụ:

| Thời điểm | Log end offset | Committed offset | Lag theo offset |
|---|---:|---:|---:|
| Trước lỗi | 1000 | 950 | 50 |
| Sau 30 giây retry | 1120 | 950 | 170 |
| Retry thành công và xử lý tiếp | 1150 | 1080 | 70 |

Lag tăng không nhất thiết có nghĩa consumer đã chết. Nó có thể đang chờ retry, xử lý một record chậm hoặc chờ commit batch.

Offset lag cũng không phải lúc nào bằng chính xác số record có thể đọc: compaction, transaction và offset gap có thể làm khoảng offset khác số lượng record thực tế. Nên theo dõi thêm record lag, thời gian tuổi của record cũ nhất, processing duration và commit latency.

### 4.1. Phân biệt các loại độ trễ

| Chỉ số | Cho biết điều gì? |
|---|---|
| Consumer lag | Khoảng cách tiến độ consumer so với log end |
| Processing duration | Thời gian handler xử lý record/batch |
| Retry count/rate | Tần suất record phải thử lại |
| Oldest unprocessed record age | Record chưa xử lý lâu nhất đã chờ bao lâu |
| Commit latency | Thời gian commit offset hoàn tất |
| Poll interval | Khoảng thời gian giữa các lần poll |

Kết hợp các chỉ số giúp phân biệt lag do retry, do throughput thấp, do broker chậm hoặc do downstream quá tải.

## 5. Thiết kế retry tại chỗ có giới hạn

Retry tại chỗ phù hợp với lỗi tạm thời có khả năng phục hồi nhanh, chẳng hạn:

- Database connection bị reset trong thời gian ngắn.
- API downstream trả lỗi 503 tạm thời.
- Rate limit yêu cầu chờ một khoảng ngắn.
- Lock contention có thể được giải phóng nhanh.

Không nên retry tại chỗ vô hạn với lỗi dữ liệu hoặc lỗi cấu hình như schema không hợp lệ, thiếu quyền, event không thỏa điều kiện nghiệp vụ. Các lỗi đó thường không tự hết khi chờ.

Một chính sách retry nên có:

1. Phân loại lỗi retryable và non-retryable.
2. Giới hạn tổng số lần thử.
3. Exponential backoff có trần.
4. Jitter để tránh nhiều consumer cùng retry tại một thời điểm.
5. Timeout cho từng lần gọi downstream.
6. Metric và log cho từng lần retry.
7. Hành động rõ ràng khi hết retry: DLT, pause, dừng consumer hoặc xử lý thủ công.

Ví dụ backoff:

| Lần thử | Khoảng chờ cơ sở |
|---:|---:|
| 1 | 250 ms |
| 2 | 500 ms |
| 3 | 1 giây |
| 4 | 2 giây |
| 5 | 4 giây |

Jitter thêm một độ lệch ngẫu nhiên trong khoảng đã chọn. Giới hạn thời gian chờ tối đa để retry không kéo dài vô hạn.

Tổng thời gian retry phải được tính vào ngân sách giữa hai lần poll. Ví dụ trên chỉ là minh họa; lựa chọn thực tế cần theo SLA downstream và `max.poll.interval.ms`.

## 6. Ví dụ Java: retry đồng bộ trong consumer thread

Ví dụ sau xử lý record tuần tự và retry một số lỗi tạm thời. Nếu hết retry, batch không được commit; ứng dụng dừng để record chưa hoàn tất có thể được đọc lại sau khi service phục hồi.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

public class InPlaceRetryConsumer {

    public static void main(String[] args) {
        Properties props = new Properties();
        props.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        props.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "orders-in-place-retry"
        );
        props.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        props.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 20);
        props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 120000);

        try (KafkaConsumer<String, String> consumer =
                 new KafkaConsumer<>(props)) {

            consumer.subscribe(List.of("orders"));

            while (true) {
                ConsumerRecords<String, String> records =
                    consumer.poll(Duration.ofMillis(500));

                try {
                    for (ConsumerRecord<String, String> record : records) {
                        processWithRetry(record, 4);
                    }

                    if (!records.isEmpty()) {
                        // Commit sau khi toàn bộ batch đã xử lý thành công.
                        consumer.commitSync();
                    }

                } catch (RetryExhaustedException exception) {
                    // Không commit batch chứa record chưa xử lý thành công.
                    // Dừng để supervisor có thể khởi động lại consumer.
                    throw exception;
                }
            }
        }
    }

    private static void processWithRetry(
            ConsumerRecord<String, String> record,
            int maxAttempts) {

        long delayMs = 250;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                processOrder(record.key(), record.value());
                return;

            } catch (RetryableProcessingException exception) {
                if (attempt == maxAttempts) {
                    throw new RetryExhaustedException(
                        "Retry exhausted at "
                            + record.topic() + "-"
                            + record.partition() + "@"
                            + record.offset(),
                        exception
                    );
                }

                try {
                    Thread.sleep(delayMs);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new RetryExhaustedException(
                        "Retry interrupted",
                        interrupted
                    );
                }

                delayMs = Math.min(delayMs * 2, 4000);

            } catch (PermanentProcessingException exception) {
                throw new RetryExhaustedException(
                    "Non-retryable event",
                    exception
                );
            }
        }
    }

    private static void processOrder(String key, String value) {
        // Gọi nghiệp vụ; chỉ ném RetryableProcessingException
        // cho lỗi tạm thời đã được xác định.
    }

    static class RetryableProcessingException extends RuntimeException {
        RetryableProcessingException(String message) {
            super(message);
        }
    }

    static class PermanentProcessingException extends RuntimeException {
        PermanentProcessingException(String message) {
            super(message);
        }
    }

    static class RetryExhaustedException extends RuntimeException {
        RetryExhaustedException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

Ví dụ tập trung vào semantics, không phải một consumer production hoàn chỉnh. Cần bổ sung shutdown có kiểm soát, logging, metric, xử lý DLT và chính sách restart. `Thread.sleep()` ở đây cố ý minh họa blocking retry: trong lúc sleep, thread không gọi `poll()`.

Nếu một record trong batch đã được xử lý thành công nhưng record sau hết retry, toàn bộ batch có thể được đọc lại vì offset chưa commit. Handler cần idempotent để các record thành công trước đó không tạo side effect lặp.

### 6.1. Tính ngân sách poll

Với cấu hình ví dụ `max.poll.interval.ms=120000`, cần bảo đảm tổng thời gian xử lý batch, retry và commit thấp hơn 120 giây với khoảng dự phòng.

Không chỉ tính bốn lần retry của một record. Một batch có thể chứa nhiều record đều lỗi và mỗi record đều tiêu thụ thời gian retry. Có thể giảm `max.poll.records`, giới hạn số retry hoặc chuyển sang một cơ chế không chặn poll thread.

## 7. Giữ thứ tự và quản lý offset khi có lỗi

Kafka bảo đảm thứ tự trong một partition log. Ứng dụng phải tránh commit offset vượt qua record chưa xử lý.

Giả sử consumer poll nhận:

| Partition | Offset | Trạng thái |
|---|---:|---|
| orders-0 | 100 | Thành công |
| orders-0 | 101 | Đang retry |
| orders-0 | 102 | Chưa xử lý |
| orders-1 | 220 | Thành công |

Nếu offset 101 chưa hoàn tất, không được commit offset 103 cho partition orders-0. Nếu commit, consumer có thể bỏ qua offset 101 và 102 khi khởi động lại.

Với nhiều partition, có thể commit tiến độ riêng cho từng partition nếu đã xử lý liên tục đến một offset cụ thể. Ví dụ có thể commit orders-1 đến 221 trong khi chưa commit orders-0 vượt quá 101, nhưng cần xây dựng map offset chính xác và bảo đảm không có record trước đó chưa hoàn tất trong partition tương ứng.

Nếu xử lý tuần tự toàn batch và chỉ gọi `commitSync()` sau khi tất cả record thành công, logic đơn giản hơn nhưng một record lỗi có thể khiến các record khác trong batch được xử lý lại. Đây là trade-off giữa đơn giản và khả năng tiến triển độc lập theo partition.

## 8. Khi nào nên dùng pause/resume thay vì sleep?

Nếu chỉ một partition có record lỗi, có thể muốn tạm dừng partition đó trong khi tiếp tục poll các partition khác. KafkaConsumer cung cấp `pause()` và `resume()`.

Mô hình tổng quát:

1. Consumer thread phát hiện record lỗi thuộc partition P.
2. Ghi nhận record và thời điểm retry tiếp theo.
3. Gọi `pause(P)` để ngăn poll trả thêm record từ partition đó.
4. Tiếp tục gọi `poll()` định kỳ để duy trì tiến độ group và xử lý partition khác.
5. Khi đến hạn retry, xử lý lại record đang chờ.
6. Chỉ sau khi record đó thành công hoặc được xử lý theo chính sách lỗi, mới resume partition P.

Ưu điểm:

- Một partition bị lỗi không nhất thiết chặn các partition khác.
- Consumer tiếp tục poll nên giảm nguy cơ vượt `max.poll.interval.ms`.
- Có thể điều tiết từng partition khi downstream gặp sự cố.

Đánh đổi:

- Cần quản lý retry state theo partition.
- Phải bảo đảm record phía sau của partition đang pause không vượt qua record lỗi.
- Cần tính offset commit liên tục cho từng partition.
- Mọi thao tác KafkaConsumer vẫn phải chạy trên thread sở hữu consumer.
- Nếu retry state chỉ nằm trong RAM, process restart có thể làm mất lịch retry; offset chưa commit sẽ giúp đọc lại record nhưng ứng dụng cần phục hồi đúng trạng thái.

Không gọi `pause()`, `resume()`, `poll()` hoặc commit từ worker thread nếu thread đó không sở hữu KafkaConsumer. Worker có thể gửi kết quả về consumer thread qua queue; owner thread mới thực hiện thao tác Kafka.

## 9. Retry topic và dead-letter topic

Retry topic chuyển record lỗi sang topic khác để xử lý lại sau một khoảng chờ. Dead-letter topic (DLT) lưu record đã hết retry hoặc lỗi không thể xử lý tự động.

Ví dụ:

~~~mermaid
flowchart LR
    A["orders"] --> B["Consumer"]
    B -->|Thành công| C["Output / Database"]
    B -->|Lỗi tạm thời| D["orders-retry"]
    D --> E["Retry consumer"]
    E -->|Thành công| C
    E -->|Hết retry| F["orders.DLT"]
~~~

Ưu điểm:

- Consumer chính không phải sleep lâu.
- Có thể thiết lập delay khác nhau theo số lần retry.
- Có thể tách năng lực xử lý retry khỏi luồng chính.
- DLT giúp cô lập poison message để điều tra.

Nhược điểm quan trọng là retry topic có thể làm thay đổi thứ tự. Khi event offset 101 được chuyển sang retry topic, consumer chính có thể tiếp tục offset 102 và 103. Nếu retry event 101 quay lại sau, event sau đã được xử lý trước.

Nếu thứ tự theo aggregate là bắt buộc, cần cơ chế bảo vệ như pause partition, sequence/version check, hoặc thiết kế retry theo partition/key để không cho event sau vượt qua. Chỉ dùng cùng Kafka key trên retry topic không tự bảo đảm thứ tự xuyên qua nhiều topic.

### 9.1. Gửi DLT và commit offset phải đáng tin cậy

Nếu ứng dụng gửi record sang DLT rồi commit offset input bằng hai thao tác riêng, process có thể crash sau khi DLT publish nhưng trước offset commit. Khi đó record đầu vào được đọc lại và có thể tạo DLT duplicate.

Các cách giảm rủi ro:

- Giữ event ID gốc để DLT consumer có thể deduplicate.
- Dùng Kafka transaction để ghi DLT/output và commit input offset nguyên tử khi cả hai đều thuộc Kafka.
- Nếu DLT đích là hệ thống ngoài Kafka, dùng outbox/inbox hoặc idempotency tương ứng.

DLT không nên âm thầm làm mất event. Cần metadata lỗi, số lần thử, thời điểm, consumer group và nguồn topic/partition/offset.

## 10. So sánh các chiến lược retry

| Chiến lược | Poll thread | Thứ tự trong partition | Consumer lag | Độ phức tạp |
|---|---|---|---|---|
| Retry tại chỗ bằng sleep | Bị chặn trong thời gian retry | Giữ được nếu không xử lý record sau | Có thể tăng nhanh | Thấp |
| Pause một partition và tiếp tục poll | Vẫn poll các partition khác | Giữ được nếu partition bị lỗi không được tiến tiếp | Lag tập trung ở partition bị pause | Trung bình/cao |
| Retry topic | Consumer chính tiếp tục xử lý | Có thể đảo thứ tự khi event sau vượt qua | Lag main topic giảm, retry lag tăng | Trung bình |
| DLT sau khi hết retry | Consumer chính có thể tiếp tục sau khi chuyển DLT | Có thể bỏ qua event lỗi theo chính sách | Giảm lag của luồng chính | Trung bình |
| Dừng consumer và đọc lại sau restart | Consumer dừng hoặc rebalance | Không bỏ qua record chưa commit | Lag tăng trong thời gian dừng | Thấp đến trung bình |

Không có một chiến lược phù hợp cho mọi hệ thống. Chọn dựa trên yêu cầu ordering, SLA, loại lỗi, thời gian phục hồi và khả năng chịu lag.

## 11. Spring Kafka: blocking retry và non-blocking retry

Spring Kafka cung cấp các cơ chế xử lý lỗi ở listener container. Tùy phiên bản, các lựa chọn thường gặp gồm:

- `DefaultErrorHandler` với `BackOff` để retry blocking, sau đó recover hoặc chuyển DLT.
- `@RetryableTopic` để tạo retry topic và luồng non-blocking retry.
- `DeadLetterPublishingRecoverer` để publish record không xử lý được sang DLT.

Ví dụ cấu hình khái niệm cho blocking retry:

~~~java
@Bean
DefaultErrorHandler errorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    FixedBackOff backOff = new FixedBackOff(
        1000L,
        3L
    );

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Ví dụ này cho phép retry với khoảng chờ cố định trước khi gọi recoverer. Cần cấu hình serializer, DLT destination, acknowledgement mode và transaction semantics tương ứng với ứng dụng. API và cách container thực hiện backoff có thể khác theo phiên bản Spring Kafka.

Ví dụ non-blocking retry:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1000,
        multiplier = 2.0
    )
)
@KafkaListener(
    topics = "orders",
    groupId = "orders-service"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

Non-blocking retry đưa record qua các retry topic theo lịch. Nó giúp consumer chính tiếp tục xử lý record khác, nhưng có thể làm thay đổi thứ tự. Không dùng cách này cho luồng cần giữ thứ tự tuyệt đối nếu chưa có sequence guard hoặc cơ chế điều phối phù hợp.

Với Spring Kafka, hãy kiểm tra đúng phiên bản để biết retry handler, container pausing backoff, transaction và DLT behavior. Không trộn cấu hình từ các phiên bản khác nhau.

## 12. Phân loại lỗi trước khi retry

Không phải lỗi nào cũng có thể tự hết khi thử lại.

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Timeout ngắn, HTTP 503, connection reset | Retry có giới hạn và backoff |
| Rate limit | HTTP 429 | Tôn trọng Retry-After nếu có, thêm jitter |
| Lỗi dữ liệu | JSON sai, schema không hợp lệ | Không retry vô hạn; DLT hoặc sửa dữ liệu |
| Lỗi cấu hình/quyền | Authorization failure, topic không tồn tại do cấu hình | Sửa cấu hình hoặc quyền |
| Lỗi nghiệp vụ vĩnh viễn | Đơn hàng không đủ điều kiện | Ghi nhận kết quả nghiệp vụ hoặc DLT theo chính sách |
| Lỗi không xác định | Timeout sau khi downstream có thể đã thực hiện side effect | Retry chỉ khi handler idempotent hoặc có idempotency key |

Nếu downstream đã thực hiện side effect nhưng response bị mất, lần retry có thể thực hiện side effect lần nữa. Dùng event ID ổn định, unique constraint hoặc idempotency key để bảo vệ.

## 13. Theo dõi retry và consumer lag

Các metric hữu ích:

- Retry attempts theo topic, partition và exception type.
- Retry exhausted count.
- Consumer lag theo partition.
- Oldest unprocessed record age.
- Poll interval và thời gian xử lý batch.
- Processing duration p95/p99.
- Commit latency.
- Pause duration và số partition đang paused.
- Retry topic lag và DLT ingress rate.
- Số lần rebalance và lý do member rời group.

Một số cách diễn giải:

| Quan sát | Khả năng |
|---|---|
| Lag tăng đồng thời retry count tăng | Downstream hoặc một loại event đang lỗi |
| Lag tăng nhưng retry thấp, processing duration cao | Handler chậm hoặc batch quá lớn |
| Rebalance tăng sau mỗi đợt retry | Poll gap có thể vượt max.poll.interval |
| Main topic lag giảm nhưng retry topic lag tăng | Công việc đã được chuyển sang luồng retry |
| DLT tăng đột biến | Có lỗi dữ liệu, lỗi cấu hình hoặc downstream không phục hồi |
| Một partition lag cao hơn hẳn | Hot key, poison message hoặc partition-specific bottleneck |

Không chỉ cảnh báo theo lag tuyệt đối. Nên kết hợp tốc độ tăng lag, tuổi record cũ nhất và SLA xử lý của nghiệp vụ.

## 14. Quy trình lựa chọn retry strategy

Có thể dùng quy trình sau:

1. Xác định lỗi có retryable không.
2. Đo thời gian phục hồi dự kiến của downstream.
3. Xác định yêu cầu ordering theo partition/key.
4. Tính thời gian xử lý batch và retry so với `max.poll.interval.ms`.
5. Nếu lỗi ngắn và thứ tự quan trọng, cân nhắc retry tại chỗ có giới hạn.
6. Nếu chỉ một partition lỗi nhưng các partition khác cần tiếp tục, cân nhắc pause partition và tiếp tục poll.
7. Nếu cần delay dài và chấp nhận xử lý không theo thứ tự toàn cục, cân nhắc retry topic.
8. Khi hết retry, chuyển DLT hoặc quy trình xử lý thủ công; không âm thầm bỏ record.
9. Bảo đảm handler idempotent và offset chỉ tiến sau khi record được xử lý hoặc recover thành công.
10. Kiểm thử crash, rebalance, downstream outage và replay trước khi triển khai.

## 15. Checklist vận hành retry tại chỗ

- [ ] Chỉ retry lỗi tạm thời; lỗi dữ liệu/configuration có policy riêng.
- [ ] Số lần retry có giới hạn.
- [ ] Backoff có trần và jitter khi có nhiều consumer.
- [ ] Timeout của downstream nhỏ hơn ngân sách thời gian poll.
- [ ] Tính tổng thời gian xử lý batch cộng retry và commit.
- [ ] `max.poll.interval.ms` có khoảng dự phòng so với p95/p99.
- [ ] `max.poll.records` phù hợp thời gian xử lý thực tế.
- [ ] Không xử lý record sau khi bỏ qua record trước nếu cần ordering.
- [ ] Không commit offset vượt qua record chưa hoàn tất.
- [ ] Handler idempotent để chịu được batch bị đọc lại.
- [ ] Có chính sách rõ ràng khi hết retry: pause, DLT hoặc dừng.
- [ ] Theo dõi retry count, poll interval, lag và oldest record age.
- [ ] Đã kiểm thử downstream outage và rebalance trong lúc retry.

Retry tại chỗ giữ record lỗi trong luồng xử lý hiện tại, nên có thể bảo toàn thứ tự trong partition khi consumer không tiến qua record đó. Đổi lại, thời gian retry chiếm poll thread, làm chậm các partition khác cùng consumer, tăng lag và có thể vượt `max.poll.interval.ms`. Hãy dùng retry có giới hạn cho lỗi phục hồi nhanh; với thời gian chờ dài hoặc chỉ một partition bị nghẽn, cân nhắc pause/resume hoặc retry topic, đồng thời bảo vệ offset, ordering và side effect bằng thiết kế idempotent.

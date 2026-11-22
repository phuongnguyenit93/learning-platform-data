# Điều tiết khi hệ thống đích chậm hoặc không khả dụng

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này hướng dẫn cách điều tiết consumer khi hệ thống đích như database, REST API hoặc dịch vụ downstream xử lý chậm, giới hạn tốc độ hoặc tạm thời không khả dụng.

Khi consumer đọc nhanh hơn tốc độ hệ thống đích có thể tiếp nhận, hàng đợi nội bộ tăng, request timeout, connection pool cạn và lỗi dây chuyền xuất hiện. Nếu tiếp tục retry dồn dập, Kafka consumer có thể bị rebalance hoặc hệ thống đích càng quá tải. Cần điều khiển tốc độ nhận và xử lý record, giới hạn concurrency, retry có ngân sách, pause/resume partition và chỉ commit offset sau khi kết quả được xử lý an toàn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận biết dấu hiệu downstream chậm, quá tải hoặc mất kết nối.
- Giải thích mối quan hệ giữa consumer throughput, downstream capacity và consumer lag.
- Thiết kế backpressure bằng pause/resume mà vẫn duy trì poll loop.
- Giới hạn số request đồng thời và dung lượng hàng đợi.
- Áp dụng rate limiting để tuân thủ quota của hệ thống đích.
- Dùng circuit breaker để ngừng gửi request khi downstream đang lỗi.
- Chọn retry ngắn, retry topic hoặc dead-letter topic theo loại lỗi.
- Tránh giữ consumer thread trong thời gian backoff quá dài.
- Commit offset đúng thời điểm và xử lý duplicate khi side effect đã thành công nhưng commit thất bại.
- Cấu hình Java Kafka Consumer và Spring Kafka cho downstream có năng lực xử lý giới hạn.
- Theo dõi consumer lag, request latency, queue depth, retry và thời gian pause để điều chỉnh hệ thống.

## 2. Vấn đề khi downstream không theo kịp Kafka

Kafka có thể cung cấp record với tốc độ cao, nhưng dịch vụ nhận dữ liệu có năng lực giới hạn. Ví dụ:

- Consumer đọc 8.000 record/giây.
- Database chỉ xử lý ổn định 3.000 transaction/giây.
- REST API giới hạn 500 request/giây.
- Một dịch vụ bên ngoài tăng latency từ 40 ms lên 2 giây.
- Connection pool chỉ có 30 connection trong khi worker đồng thời tạo 100 request.

Nếu consumer vẫn nhận và gửi record theo tốc độ cũ, hệ thống sẽ tích lũy công việc chưa hoàn tất.

~~~text
Kafka topic
    |
    v
Consumer poll: 8.000 record/s
    |
    v
Worker queue tăng liên tục
    |
    v
Downstream chỉ xử lý 3.000 record/s
    |
    +--> Request timeout
    +--> Connection pool cạn
    +--> Retry tăng
    +--> Consumer lag tăng
    +--> Downstream càng quá tải
~~~

Đây là tình trạng mất cân bằng năng lực xử lý. Tăng số consumer hoặc worker ngay lập tức có thể làm downstream chịu tải nặng hơn. Điều cần làm trước tiên là giới hạn lượng công việc được gửi đến hệ thống đích và cho phép backlog nằm trong Kafka trong thời gian downstream phục hồi.

## 3. Backpressure là gì?

**Backpressure** là cơ chế điều tiết tốc độ nhận hoặc phát công việc theo năng lực xử lý thực tế của thành phần phía sau.

Với Kafka consumer, backpressure có thể được triển khai ở nhiều tầng:

1. Giảm số record nhận trong mỗi poll.
2. Tạm dừng fetch từ một số partition bằng pause().
3. Giới hạn số worker và request đồng thời.
4. Dùng bounded queue để giới hạn lượng record chờ xử lý.
5. Dùng rate limiter để giới hạn số request mỗi giây.
6. Dùng circuit breaker để tạm ngừng gọi downstream khi lỗi tăng cao.
7. Resume partition khi queue giảm và downstream phục hồi.

Mục tiêu là giữ lượng công việc đang xử lý trong giới hạn mà hệ thống có thể kiểm soát.

### 3.1. Backpressure không phải là xóa backlog

Khi consumer pause partition, record vẫn được giữ trong Kafka theo retention policy. Consumer chưa xử lý các record mới nên consumer lag có thể tăng.

Đó là hành vi có chủ đích: chấp nhận backlog tăng tạm thời để tránh làm hệ thống đích sụp đổ. Sau khi downstream khỏe lại, consumer tiếp tục xử lý và backlog giảm nếu throughput xử lý cao hơn tốc độ record mới đi vào.

### 3.2. Phân biệt ba loại tốc độ

| Tốc độ | Ý nghĩa |
|---|---|
| Ingestion rate | Tốc độ producer ghi record vào Kafka. |
| Consumption rate | Tốc độ consumer poll và nhận record. |
| Processing rate | Tốc độ ứng dụng hoàn tất nghiệp vụ và side effect ở downstream. |

Consumption rate cao không đồng nghĩa processing rate cao. Nếu consumer poll nhanh nhưng worker queue ngày càng lớn, hệ thống chỉ đang chuyển backlog từ Kafka vào bộ nhớ ứng dụng.

Cần đo processing completion rate và queue depth, không chỉ đo số record poll được.

## 4. Xác định ngưỡng tải an toàn

Trước khi cấu hình backpressure, hãy xác định năng lực downstream bằng thử nghiệm tải và quan sát production.

Ví dụ hệ thống đích có thể xử lý ổn định khoảng 2.000 request/giây. Không nên đặt giới hạn đúng 2.000 nếu latency và throughput dao động. Hãy bắt đầu ở mức thấp hơn, chẳng hạn 1.500 request/giây, sau đó điều chỉnh theo p95/p99 latency, error rate và quota.

Các giới hạn cần xác định:

- Request mỗi giây.
- Số request đồng thời.
- Connection pool size.
- Số transaction database đồng thời.
- Kích thước batch.
- Timeout cho connect, read và toàn request.
- Số lần retry tối đa.
- Dung lượng queue chờ xử lý.
- Mức consumer lag có thể chấp nhận.
- Thời gian downstream có thể ngừng phục vụ trước khi vi phạm SLA.

Không dùng CPU của consumer làm chỉ số duy nhất. Consumer có thể CPU thấp nhưng đang chờ database hoặc HTTP API.

## 5. Giảm lượng record nhận mỗi poll

Cấu hình **max.poll.records** giới hạn số record tối đa được trả về trong một lần poll.

Ví dụ:

~~~properties
max.poll.records=50
~~~

Nếu mỗi record cần gọi một API chậm, batch 50 record có thể tạo ra 50 request liên tiếp hoặc một nhóm request đồng thời tùy cách ứng dụng xử lý. Giảm max.poll.records giúp giới hạn lượng dữ liệu một lần đưa vào ứng dụng.

Trong Java:

~~~java
Properties properties = new Properties();

properties.put(
    ConsumerConfig.MAX_POLL_RECORDS_CONFIG,
    50
);
properties.put(
    ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
    false
);
properties.put(
    ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG,
    300000
);
~~~

max.poll.records không phải rate limiter. Consumer có thể poll liên tục nhiều lần và vẫn nhận dữ liệu nhanh hơn downstream. Cần kết hợp với pause/resume, bounded queue hoặc giới hạn tốc độ.

### 5.1. Chọn batch size theo thời gian xử lý

Giả sử:

- max.poll.records = 50.
- Mỗi record xử lý tuần tự mất 100 ms.
- Batch mất khoảng 5 giây, chưa kể commit và network.

Nếu downstream tăng latency lên 1 giây mỗi record, cùng batch có thể mất khoảng 50 giây. Thời gian giữa hai lần poll phải vẫn nằm trong max.poll.interval.ms.

Đo thời gian xử lý batch ở điều kiện tải cao và khi downstream chậm. Đừng chỉ dựa trên thời gian trung bình trong môi trường thử nghiệm.

### 5.2. Giảm batch khi downstream chậm

Có thể áp dụng cấu hình batch nhỏ hơn cho consumer gọi hệ thống đích có latency cao. Tuy nhiên, batch quá nhỏ có thể làm tăng overhead poll, network và commit.

Cần cân bằng giữa:

- Throughput.
- Latency.
- Chi phí request.
- Khả năng phục hồi khi downstream chậm.
- Thời gian xử lý trước poll tiếp theo.

## 6. Pause và resume partition

Java Kafka Consumer cung cấp **pause()** và **resume()** để tạm ngừng hoặc tiếp tục nhận record từ các partition đã được gán.

- pause(partitions): yêu cầu consumer tạm dừng fetch record từ các partition chỉ định.
- resume(partitions): tiếp tục nhận record từ các partition đó.
- assignment không bị xóa khi pause.
- pause không commit offset và không xóa record trong Kafka.
- Consumer vẫn cần tiếp tục gọi poll() để duy trì hoạt động của group.

Đây là công cụ quan trọng để điều tiết khi downstream tạm thời không thể nhận thêm công việc.

### 6.1. Luồng pause/resume

~~~mermaid
flowchart TD
    A[Consumer poll] --> B[Kiểm tra downstream và queue]
    B --> C{Downstream đủ năng lực?}
    C -->|Có| D[Resume partition cần xử lý]
    C -->|Không| E[Pause partition]
    D --> F[Poll và xử lý trong giới hạn]
    E --> G[Tiếp tục poll định kỳ]
    F --> H[Theo dõi latency và queue]
    G --> I[Kiểm tra health signal]
    H --> B
    I -->|Phục hồi| D
    I -->|Vẫn lỗi| E
~~~

Khi partition đã pause, poll vẫn cần được gọi. Các partition đang pause không trả record mới, nhưng consumer tiếp tục tham gia group coordination và thực hiện các công việc cần thiết của client.

Không thay pause bằng Thread.sleep() dài trên consumer thread. Nếu ngừng poll quá lâu, consumer có thể vượt max.poll.interval.ms và bị rời group.

### 6.2. Ví dụ Java pause/resume theo health signal

Ví dụ dưới đây giả định một thành phần giám sát độc lập cập nhật trạng thái downstream vào AtomicBoolean. Health probe không chạy trực tiếp trên consumer thread và không gọi KafkaConsumer.

~~~java
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.errors.WakeupException;
import org.apache.kafka.common.serialization.StringDeserializer;

import java.time.Duration;
import java.util.List;
import java.util.Properties;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class BackpressureConsumer {

    private final AtomicBoolean running = new AtomicBoolean(true);
    private final AtomicBoolean downstreamHealthy =
        new AtomicBoolean(true);
    private final AtomicReference<KafkaConsumer<String, String>> consumerRef =
        new AtomicReference<>();

    public void stop() {
        running.set(false);
        KafkaConsumer<String, String> consumer = consumerRef.get();
        if (consumer != null) {
            consumer.wakeup();
        }
    }

    // Health monitor có thể gọi phương thức này từ thread khác.
    public void updateDownstreamHealth(boolean healthy) {
        downstreamHealthy.set(healthy);
    }

    public void run() {
        Properties properties = new Properties();

        properties.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "orders-backpressure"
        );
        properties.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        properties.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        properties.put(
            ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
            false
        );
        properties.put(
            ConsumerConfig.MAX_POLL_RECORDS_CONFIG,
            50
        );

        try (KafkaConsumer<String, String> consumer =
                 new KafkaConsumer<>(properties)) {

            consumerRef.set(consumer);
            consumer.subscribe(List.of("orders"));

            try {
                while (running.get()) {
                    boolean healthyForThisPoll = downstreamHealthy.get();
                    Set<TopicPartition> assigned =
                        consumer.assignment();

                    if (!assigned.isEmpty()) {
                        if (healthyForThisPoll) {
                            consumer.resume(assigned);
                        } else {
                            consumer.pause(assigned);
                        }
                    }

                    ConsumerRecords<String, String> records =
                        consumer.poll(Duration.ofMillis(500));

                    if (!healthyForThisPoll) {
                        // Poll đầu tiên sau subscribe có thể vừa nhận assignment
                        // vừa trả record. Rewind batch đó trước khi tiếp tục pause.
                        for (TopicPartition partition : records.partitions()) {
                            var partitionRecords = records.records(partition);
                            if (!partitionRecords.isEmpty()) {
                                consumer.seek(
                                    partition,
                                    partitionRecords.get(0).offset()
                                );
                            }
                        }
                        continue;
                    }

                    for (var record : records) {
                        processWithBoundedTimeout(record);
                    }

                    if (!records.isEmpty()) {
                        consumer.commitSync();
                    }
                }
            } catch (WakeupException exception) {
                if (running.get()) {
                    throw exception;
                }
            } finally {
                consumerRef.set(null);
            }
        }
    }

    private void processWithBoundedTimeout(
        org.apache.kafka.clients.consumer.ConsumerRecord<String, String> record
    ) {
        // Gọi downstream với connect/read/request timeout hữu hạn.
    }
}
~~~

Đây là ví dụ minh họa cho xử lý tuần tự và manual commit. Trong ứng dụng thực tế, cần đăng ký stop() với shutdown hook, xử lý exception và dùng health monitor có hysteresis để tránh pause/resume liên tục khi trạng thái chập chờn.

Điểm quan trọng:

- Chỉ consumer owner thread gọi assignment(), pause(), resume(), poll() và commit.
- Thread giám sát chỉ cập nhật health signal.
- Khi downstream không khỏe, consumer vẫn poll nhưng không gửi thêm record.
- Khi downstream phục hồi ổn định, consumer resume partition.
- Chỉ commit sau khi toàn bộ record của batch đã xử lý thành công.

Nếu downstream lỗi giữa batch, không commit toàn bộ batch khi còn record chưa xử lý. Record đã xử lý thành công có thể được đọc lại nếu batch không commit; side effect cần idempotent.

## 7. Backpressure theo từng partition

Không phải mọi partition đều cần pause cùng lúc. Nếu downstream có thể phục vụ một số loại công việc nhưng một partition có tenant hoặc key đang bị throttling, có thể pause riêng partition liên quan.

Ví dụ:

- orders-0 gửi đến API thanh toán đang bị giới hạn.
- orders-1 và orders-2 gửi đến các hệ thống đích khác vẫn khỏe.
- Consumer chỉ pause orders-0, tiếp tục poll và xử lý hai partition còn lại.

Ưu điểm:

- Hạn chế ảnh hưởng dây chuyền.
- Các partition độc lập vẫn tiếp tục xử lý.
- Dễ khoanh vùng tenant hoặc nhóm dữ liệu gặp sự cố.

Rủi ro:

- Partition bị pause có thể tích lũy lag.
- Nếu nhiều key cùng nằm trong partition đó, tất cả đều bị trì hoãn.
- Việc pause một partition không thể tách riêng một key bên trong partition.
- Khi partition được resume, cần giới hạn tốc độ catch-up để không làm downstream quá tải trở lại.

Nếu cần cô lập theo tenant hoặc loại nghiệp vụ, cân nhắc routing sang topic/partition riêng hoặc dùng hàng đợi downstream riêng thay vì kỳ vọng assignor tự hiểu tải nghiệp vụ.

## 8. Bounded queue và giới hạn worker

Một lỗi phổ biến là poll record rồi đẩy tất cả vào executor có queue không giới hạn.

Nếu tốc độ nhận lớn hơn tốc độ xử lý, queue tăng liên tục cho đến khi JVM thiếu heap hoặc thời gian chờ quá dài.

Dùng **bounded queue** để giới hạn số record chờ xử lý. Ví dụ:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadPoolExecutor workers = new ThreadPoolExecutor(
    8,
    8,
    0L,
    TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(200),
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

Trong ví dụ:

- Tối đa 8 worker chạy đồng thời.
- Queue chỉ chứa tối đa 200 task đang chờ.
- Khi queue đầy, executor từ chối task mới.

Ứng dụng phải xử lý RejectedExecutionException hoặc rejection handler có kiểm soát. Không dùng CallerRunsPolicy một cách vô thức trên consumer thread vì consumer thread có thể bị buộc xử lý task đồng bộ và ngừng poll trong thời gian dài.

### 8.1. Kết hợp queue với pause/resume

Một mô hình điều tiết:

1. Consumer owner thread poll batch.
2. Đưa record vào bounded queue nếu còn capacity.
3. Khi queue vượt high watermark, pause các partition cần điều tiết.
4. Trong thời gian pause, vẫn gọi poll định kỳ.
5. Worker hoàn tất công việc và giảm queue depth.
6. Khi queue xuống dưới low watermark, owner thread resume partition.
7. Chỉ commit offset theo tiến độ xử lý liên tục của từng partition.

Nên dùng hai ngưỡng khác nhau:

- **High watermark:** ví dụ queue sử dụng 80% dung lượng thì pause.
- **Low watermark:** ví dụ queue giảm dưới 40% thì resume.

Khoảng cách giữa hai ngưỡng giúp tránh trạng thái pause/resume liên tục khi queue dao động quanh một giá trị.

Batch vừa nhận từ poll có thể lớn hơn phần capacity còn lại của queue. Không được bỏ record hoặc commit offset của batch chỉ vì executor từ chối task. Có thể đặt queue capacity ít nhất bằng max.poll.records, giữ phần batch chưa dispatch trong một pending buffer có giới hạn, hoặc seek partition về offset đầu tiên chưa dispatch rồi pause partition đó. Chỉ commit sau khi toàn bộ record trước vị trí commit đã hoàn tất.

### 8.2. Không commit theo record đã submit

Khi worker pool xử lý song song, việc submit task thành công không có nghĩa nghiệp vụ đã hoàn tất.

Ví dụ:

~~~text
orders-0:
  offset 100 -> Worker A đang xử lý
  offset 101 -> Worker B hoàn tất
  offset 102 -> Worker C hoàn tất
~~~

Không được commit offset 103 chỉ vì hai worker sau đã hoàn tất. Offset 100 còn đang xử lý nên vị trí commit an toàn chưa thể vượt qua nó.

Theo từng partition, chỉ commit offset tiếp theo sau chuỗi record liên tục đã hoàn tất. Nếu xử lý song song, cần completion tracker để quản lý khoảng trống giữa các offset.

## 9. Rate limiting cho downstream

Một số hệ thống đích có quota rõ ràng, chẳng hạn 500 request/giây hoặc 20 request đồng thời. Trong trường hợp đó, **rate limiter** giới hạn tốc độ gọi dịch vụ.

Các thuật toán thường gặp:

- Token bucket: token được bổ sung theo tốc độ cố định; request tiêu thụ token.
- Leaky bucket: request được xử lý theo tốc độ ổn định.
- Fixed window: giới hạn số request trong mỗi cửa sổ thời gian.
- Sliding window: tính quota trên cửa sổ trượt để tránh dồn request ở ranh giới cửa sổ.

Ví dụ token bucket:

~~~text
Quota: 500 request/second
Bucket capacity: 100 tokens

Mỗi request:
  - Lấy 1 token.
  - Nếu còn token: gửi downstream.
  - Nếu hết token: giữ record chờ hoặc pause partition.
Token được bổ sung theo tốc độ cấu hình.
~~~

Rate limiter phải phù hợp với phạm vi quota. Nếu quota áp dụng cho toàn bộ cluster nhưng mỗi consumer tự giới hạn 500 request/giây, 10 consumer có thể tạo 5.000 request/giây. Khi quota là global, cần bộ điều phối token dùng chung hoặc phân bổ quota cho từng instance.

### 9.1. Xử lý HTTP 429 và Retry-After

Khi API trả HTTP 429 Too Many Requests:

- Đọc Retry-After nếu server cung cấp.
- Không retry ngay lập tức theo vòng lặp dày đặc.
- Giảm tốc độ request hoặc tăng thời gian chờ.
- Dùng exponential backoff và jitter.
- Theo dõi quota và tỷ lệ 429 để điều chỉnh rate limiter.

Không nên coi 429 là lỗi nghiệp vụ vĩnh viễn. Đây thường là tín hiệu client cần giảm tốc độ.

## 10. Circuit breaker khi downstream mất khả năng phục vụ

**Circuit breaker** ngăn ứng dụng tiếp tục gọi một hệ thống đích đang lỗi liên tục.

Ba trạng thái phổ biến:

| Trạng thái | Hành vi |
|---|---|
| Closed | Cho phép request đi qua và theo dõi lỗi/latency. |
| Open | Chặn request mới trong một khoảng thời gian. |
| Half-open | Cho phép một số request thử nghiệm để xác định downstream đã phục hồi chưa. |

Luồng hoạt động:

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: Error rate hoặc slow-call rate vượt ngưỡng
    Open --> HalfOpen: Hết thời gian chờ
    HalfOpen --> Closed: Probe thành công
    HalfOpen --> Open: Probe thất bại
~~~

Khi circuit breaker mở:

1. Không tiếp tục gửi request đến downstream.
2. Pause các partition liên quan hoặc ngừng dispatch task mới.
3. Tiếp tục poll để duy trì consumer group.
4. Theo dõi thời gian mở circuit và consumer lag.
5. Khi half-open, chỉ gửi một lượng request thử nghiệm giới hạn.
6. Chỉ resume đầy đủ khi downstream phục hồi ổn định.

Circuit breaker không thay thế retry. Retry xử lý lỗi tạm thời ở một request; circuit breaker ngăn một hệ thống lỗi liên tục bị gọi dồn dập.

### 10.1. Ví dụ chính sách circuit breaker

Một chính sách minh họa:

~~~text
Cửa sổ quan sát: 20 giây
Số request tối thiểu: 20
Mở circuit nếu:
  - Error rate > 50%, hoặc
  - Slow call rate > 70%

Thời gian Open: 15 giây
Half-open: cho phép 3 probe
Nếu 3 probe thành công: Closed
Nếu probe thất bại: quay lại Open
~~~

Các giá trị chỉ là ví dụ. Cần chọn theo latency baseline, SLA, tỷ lệ lỗi tự nhiên và khả năng phục hồi của downstream.

### 10.2. Hysteresis để tránh dao động

Không nên resume ngay sau một health check thành công đơn lẻ. Downstream có thể vừa phục hồi trong vài giây rồi lại quá tải.

Dùng điều kiện phục hồi ổn định:

- Nhiều probe liên tiếp thành công.
- p95 latency trở lại dưới ngưỡng.
- Error rate giảm đủ lâu.
- Connection pool có capacity.
- Queue downstream không tiếp tục tăng.

Có thể kết hợp circuit breaker với pause/resume và rate limiter để tăng dần lưu lượng sau khi phục hồi.

## 11. Retry có giới hạn và exponential backoff

Retry phù hợp với lỗi tạm thời, ví dụ:

- Network timeout ngắn.
- HTTP 503 Service Unavailable.
- Database connection reset.
- Broker hoặc dịch vụ đích đang failover.
- HTTP 429 có Retry-After.

Không retry vô hạn và không retry mọi lỗi giống nhau.

### 11.1. Exponential backoff

Thời gian chờ tăng theo số lần retry:

\[
delay_n = \min(maxDelay,\ baseDelay \times 2^n)
\]

Ví dụ:

| Lần retry | Thời gian chờ trước jitter |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 | 3.200 ms |

### 11.2. Jitter

Nếu hàng nghìn consumer cùng retry tại một thời điểm, chúng có thể tạo ra một đợt request lớn khi downstream vừa phục hồi. Jitter thêm độ ngẫu nhiên vào thời gian chờ để phân tán request:

\[
actualDelay = random(0,\ delay_n)
\]

Có thể dùng full jitter hoặc equal jitter tùy thư viện retry. Giới hạn maxDelay và tổng retry time budget để không kéo dài vô hạn.

### 11.3. Phân loại lỗi trước khi retry

| Loại lỗi | Hành động gợi ý |
|---|---|
| Timeout hoặc connection reset | Retry giới hạn với backoff. |
| HTTP 429 | Tôn trọng Retry-After, giảm rate. |
| HTTP 503 | Retry giới hạn, kết hợp circuit breaker. |
| HTTP 400 do dữ liệu không hợp lệ | Không retry vô hạn; chuyển DLT hoặc xử lý nghiệp vụ. |
| HTTP 401/403 | Dừng hoặc cảnh báo cấu hình xác thực; retry không giải quyết được token/quyền sai. |
| Database deadlock tạm thời | Retry transaction có giới hạn nếu thao tác an toàn. |
| Schema hoặc payload không hợp lệ | DLT hoặc quarantine để điều tra. |

### 11.4. Tránh sleep dài trên consumer thread

Nếu consumer thread xử lý record rồi sleep 60 giây để retry, poll loop có thể không chạy trong khoảng thời gian đó. Nếu vượt max.poll.interval.ms, consumer có thể rời group và partition được giao cho member khác.

Đối với retry ngắn, tổng thời gian xử lý vẫn phải nằm trong poll interval và timeout budget. Với retry dài, nên dùng retry topic, delayed retry hoặc pause container có cơ chế tiếp tục poll thay vì sleep trên consumer thread.

## 12. Retry topic và dead-letter topic

Khi downstream ngừng hoạt động lâu hoặc một record cần chờ lâu trước khi retry, có thể chuyển record sang retry topic.

Ví dụ:

~~~text
orders
   |
   v
Consumer
   |
   +--> Xử lý thành công --> commit input offset
   |
   +--> Lỗi tạm thời
            |
            v
       orders.retry.1m
            |
            v
       Retry consumer
            |
            +--> Thành công
            |
            +--> Vượt retry budget
                       |
                       v
                 orders.DLT
~~~

Retry topic cho phép consumer chính tiếp tục xử lý record khác thay vì bị chặn bởi một record lỗi lâu dài.

Thông tin nên lưu cùng record retry:

- Original topic.
- Original partition.
- Original offset.
- Original timestamp.
- Retry count.
- First failure time.
- Last failure type/message.
- Next eligible retry time nếu hệ thống tự quản lý lịch.
- Event ID và correlation ID.

### 12.1. Không đánh mất record khi chuyển sang retry topic

Nếu ứng dụng gửi record sang retry topic rồi commit offset gốc, cần bảo đảm việc publish retry record đã thành công và bền vững.

Có hai hướng:

1. Dùng Kafka transaction để ghi retry record và commit input offset trong cùng transaction.
2. Nếu không dùng transaction, chỉ commit input sau khi retry record đã được broker xác nhận; chấp nhận khả năng duplicate nếu publish thành công nhưng commit input thất bại và thiết kế consumer retry idempotent.

Không commit input trước khi retry record được ghi bền vững. Nếu làm vậy, ứng dụng có thể mất record khi crash giữa hai thao tác.

### 12.2. Retry topic có thể phá thứ tự

Giả sử cùng một order key có:

~~~text
Offset 100: OrderCreated
Offset 101: OrderPaid
Offset 102: OrderShipped
~~~

Nếu OrderCreated được chuyển sang retry topic trong khi consumer tiếp tục xử lý OrderPaid và OrderShipped, event sau có thể hoàn tất trước event đầu tiên.

Nếu nghiệp vụ yêu cầu ordering nghiêm ngặt theo key:

- Pause partition hoặc key lane cho đến khi record đầu được xử lý.
- Dùng retry theo partition/key có cơ chế giữ thứ tự.
- Đặt sequence number nghiệp vụ và kiểm tra khi xử lý.
- Không cho event sau vượt qua event trước nếu trạng thái nghiệp vụ chưa sẵn sàng.

Retry topic phù hợp khi có thể chấp nhận xử lý lại theo thứ tự khác hoặc khi ứng dụng có cơ chế tái lập thứ tự.

### 12.3. Dead-letter topic (DLT/DLQ)

Sau khi hết retry budget hoặc gặp lỗi không thể phục hồi, record có thể được chuyển đến dead-letter topic để điều tra.

DLT không phải nơi xóa lỗi khỏi hệ thống. Cần:

- Lưu exception class và thông tin lỗi.
- Giữ event ID và metadata nguồn.
- Giới hạn quyền truy cập nếu payload nhạy cảm.
- Có quy trình sửa dữ liệu và replay.
- Theo dõi DLT rate và tuổi record.
- Không tự động replay vô hạn cùng một record lỗi.

## 13. Timeout budget cho toàn luồng

Timeout ở các tầng cần phối hợp. Nếu mỗi tầng có timeout quá dài và retry nhiều lần, tổng thời gian xử lý có thể vượt SLA và max.poll.interval.ms.

Ví dụ budget minh họa:

| Thành phần | Timeout |
|---|---:|
| HTTP connect timeout | 500 ms |
| HTTP response timeout | 2 giây |
| Một lần downstream request | 2,5 giây |
| Retry tối đa trong consumer thread | 2 lần |
| Backoff giữa retry | 200 ms, 500 ms |
| Tổng xử lý một record | Dưới 6 giây |
| max.poll.interval.ms | 120 giây |

Đây chỉ là ví dụ. Cần cộng cả thời gian xử lý batch, commit, serialization và các dependency khác khi tính poll interval.

Không đặt request timeout lớn hơn toàn bộ SLA của consumer. Không tăng max.poll.interval.ms vô hạn để che giấu request bị treo.

## 14. Consumer lag khi downstream chậm

Consumer lag là khoảng cách giữa vị trí log cuối và tiến độ consumer group theo cách công cụ tính. Lag tăng có thể do:

- Downstream xử lý chậm.
- Consumer bị pause.
- Request retry quá nhiều.
- Consumer concurrency thấp.
- Partition skew.
- Rebalance liên tục.
- Consumer hoặc broker có vấn đề về network, CPU hoặc I/O.

Lag là tín hiệu về backlog, không tự chỉ ra nguyên nhân.

Ví dụ:

| Thời điểm | Consumer lag |
|---|---:|
| 10:00 | 2.000 |
| 10:05 | 8.000 |
| 10:10 | 25.000 |
| 10:15 | 60.000 |

Nếu downstream chỉ xử lý 2.000 record/s trong khi producer ghi 3.000 record/s, lag tăng khoảng 1.000 record/s. Sau khi downstream phục hồi, consumer phải xử lý nhanh hơn ingestion rate mới có thể giảm backlog.

### 14.1. Ước tính thời gian catch-up

Nếu:

- Backlog hiện tại là B record.
- Consumer processing rate là C record/s.
- Producer ingestion rate là I record/s.
- C lớn hơn I.

Thời gian catch-up gần đúng:

\[
catchUpTime = \frac{B}{C-I}
\]

Ví dụ:

- Backlog = 600.000 record.
- Consumer xử lý = 5.000 record/s.
- Producer tiếp tục ghi = 3.000 record/s.

\[
catchUpTime = \frac{600000}{5000-3000} = 300\ seconds
\]

Nếu C nhỏ hơn hoặc bằng I, backlog không thể giảm bền vững.

Đây là ước tính đơn giản. Thực tế còn phụ thuộc phân bố partition, kích thước record, retry, downstream latency và tốc độ xử lý thay đổi theo thời gian.

## 15. Cấu hình Spring Kafka cho downstream chậm

Spring Kafka listener container quản lý poll loop và consumer lifecycle. Ứng dụng nên điều tiết thông qua listener container và error handler, không truy cập trực tiếp KafkaConsumer nội bộ từ một thread tùy ý.

Ví dụ cấu hình application.yml:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      max-poll-records: 50
      properties:
        max.poll.interval.ms: 120000
    listener:
      ack-mode: manual
      concurrency: 3
~~~

Các giá trị trên chỉ là cấu hình minh họa:

- enable-auto-commit=false để container/ứng dụng kiểm soát commit.
- max-poll-records giới hạn batch.
- max.poll.interval.ms phải lớn hơn thời gian xử lý batch tối đa dự kiến.
- concurrency không nên vượt quá số partition có ích hoặc năng lực downstream.

### 15.1. Manual acknowledgment

Ví dụ listener chỉ acknowledge sau khi downstream xử lý thành công:

~~~java
@Component
public class OrderListener {

    private final OrderGateway orderGateway;

    public OrderListener(OrderGateway orderGateway) {
        this.orderGateway = orderGateway;
    }

    @KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-service"
    )
    public void onMessage(
        OrderEvent event,
        Acknowledgment acknowledgment
    ) {
        orderGateway.process(event);

        // Chỉ acknowledge sau khi side effect hoàn tất.
        acknowledgment.acknowledge();
    }
}
~~~

Cần cấu hình container AckMode phù hợp với manual acknowledgment. Nếu orderGateway.process() ném exception, listener không acknowledge record; error handler sẽ quyết định retry hoặc recover theo chính sách.

Nếu side effect đã thành công nhưng commit offset thất bại, record có thể được giao lại. OrderGateway nên dùng event ID hoặc idempotency key để tránh side effect bị nhân đôi.

### 15.2. Pause/resume listener container

Có thể lấy listener container thông qua KafkaListenerEndpointRegistry:

~~~java
@Component
public class OrdersListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrdersListenerControl(
        KafkaListenerEndpointRegistry registry
    ) {
        this.registry = registry;
    }

    public void pause() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null) {
            container.pause();
        }
    }

    public void resume() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null) {
            container.resume();
        }
    }
}
~~~

Có thể gọi pause/resume từ một thành phần điều phối dựa trên queue depth, circuit breaker hoặc health signal. Listener container sẽ thực hiện việc pause/resume theo lifecycle của consumer thread. Không lấy KafkaConsumer nội bộ rồi gọi pause/resume từ health monitor.

Khi container pause, listener delivery dừng theo cơ chế container nhưng poll vẫn được duy trì để tránh mất group membership. Hành vi và API chi tiết cần đối chiếu phiên bản Spring Kafka đang sử dụng.

### 15.3. Error handler và backoff

Spring Kafka có thể cấu hình DefaultErrorHandler với backoff và recoverer để xử lý record lỗi sau số lần thử nhất định.

Ví dụ cấu hình minh họa:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
    DeadLetterPublishingRecoverer recoverer
) {
    ExponentialBackOff backOff =
        new ExponentialBackOff(500L, 2.0);

    backOff.setMaxInterval(5000L);
    backOff.setMaxElapsedTime(15000L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Sau khi hết retry, recoverer có thể publish record sang DLT. Cần cấu hình DeadLetterPublishingRecoverer, producer template và topic đích tương ứng.

Với thời gian backoff dài, hãy dùng cơ chế pause-aware phù hợp với listener container, chẳng hạn ContainerPausingBackOffHandler trong các phiên bản Spring Kafka hỗ trợ. Điều này giúp container tiếp tục poll trong thời gian chờ. Kiểm tra API đúng phiên bản trước khi áp dụng.

Không dùng retry vô hạn trên consumer thread khi downstream có thể ngừng nhiều phút. Với thời gian chờ dài, retry topic hoặc container pausing backoff thường dễ kiểm soát hơn.

## 16. Giới hạn concurrency để bảo vệ downstream

Tăng consumer concurrency làm tăng số partition có thể xử lý song song, nhưng cũng tăng số request đồng thời đến downstream.

Ví dụ:

- 4 consumer instance.
- Mỗi instance có 5 worker.
- Tổng số request đồng thời có thể lên đến 20.
- Nếu tăng lên 10 instance, tổng concurrency có thể tăng lên 50.

Nếu downstream chỉ chịu được 20 request đồng thời, scale consumer lên 10 instance có thể làm hệ thống đích quá tải.

Cần tính concurrency toàn hệ thống:

\[
totalConcurrency = instances \times workersPerInstance
\]

Nếu có nhiều consumer group cùng gọi một API, phải cộng tải của tất cả group và service khác cùng sử dụng API đó.

Cân nhắc:

- Giới hạn worker mỗi instance.
- Dùng bulkhead riêng cho từng downstream.
- Dùng rate limiter global nếu quota áp dụng toàn cluster.
- Scale consumer theo lag nhưng đặt trần concurrency.
- Không tăng số consumer vượt số partition nếu không có lợi ích và có thể làm tăng overhead.

## 17. Bulkhead: cô lập hệ thống đích

**Bulkhead** chia tài nguyên thành các nhóm độc lập để lỗi của một downstream không làm cạn toàn bộ worker hoặc connection pool.

Ví dụ:

~~~text
Consumer service
   |
   +--> Payment bulkhead
   |      5 workers
   |      10 connections
   |
   +--> Shipping bulkhead
   |      3 workers
   |      5 connections
   |
   +--> Notification bulkhead
          2 workers
          3 connections
~~~

Nếu Shipping API chậm, queue và worker của Shipping có thể bị đầy nhưng không chiếm hết tài nguyên dành cho Payment.

Có thể kết hợp bulkhead với:

- Queue riêng.
- Rate limiter riêng.
- Circuit breaker riêng.
- Timeout riêng.
- Metric riêng.

Không dùng một executor hoặc connection pool chung không giới hạn cho tất cả downstream nếu workload có mức độ quan trọng khác nhau.

## 18. Chiến lược chọn theo tình huống

| Tình huống | Cách xử lý gợi ý |
|---|---|
| Downstream chậm nhẹ, lỗi ngắn | Giảm batch, giới hạn concurrency và retry ngắn. |
| Downstream trả 429 | Tôn trọng Retry-After, giảm rate và pause nếu cần. |
| Downstream trả 503 liên tục | Mở circuit, pause partition, theo dõi health và resume có kiểm soát. |
| Một tenant hoặc partition bị lỗi | Pause riêng partition nếu có thể cô lập. |
| Một record payload lỗi vĩnh viễn | DLT/quarantine, không retry vô hạn. |
| Retry cần chờ nhiều phút | Retry topic hoặc delayed retry. |
| Thứ tự theo key là bắt buộc | Không để retry topic làm event sau vượt event trước; giữ partition/key lane. |
| Worker queue tăng nhanh | Pause ở high watermark, resume ở low watermark. |
| Downstream có quota toàn cluster | Dùng rate limiter phân tán hoặc chia quota theo instance. |
| Database đã commit nhưng offset commit thất bại | Dùng idempotency key/inbox để chống side effect lặp. |

## 19. Monitoring và cảnh báo

Theo dõi cả Kafka consumer và hệ thống đích.

| Metric | Ý nghĩa | Cảnh báo khi |
|---|---|---|
| Consumer lag | Backlog chưa được xử lý | Tăng liên tục hoặc vượt SLA |
| Processing rate | Tốc độ hoàn tất nghiệp vụ | Thấp hơn ingestion rate kéo dài |
| Downstream request latency p95/p99 | Độ trễ dịch vụ đích | Vượt ngưỡng SLA |
| Downstream error rate | Tỷ lệ request thất bại | Tăng bất thường |
| HTTP 429/503 count | Throttling và unavailable | Tăng nhanh |
| Worker queue depth | Số task chờ xử lý | Gần high watermark kéo dài |
| Active worker count | Số tác vụ đang chạy | Luôn chạm giới hạn |
| Connection pool pending | Request chờ connection | Tăng liên tục |
| Circuit breaker state | Trạng thái bảo vệ downstream | Open kéo dài hoặc dao động |
| Paused partition count/duration | Mức điều tiết consumer | Pause kéo dài bất thường |
| Retry count và retry age | Khối lượng công việc retry | Retry backlog tăng |
| DLT rate | Record không thể xử lý | Tăng đột biến |
| Rebalance count | Tần suất thay đổi group | Tăng cùng lúc với xử lý chậm |

Nên ghi log correlation ID, event ID, topic, partition, offset, downstream name và retry attempt để truy vết một record qua nhiều lần thử.

Không cảnh báo chỉ dựa vào consumer lag tuyệt đối. Cần kết hợp lag growth rate, processing rate, downstream latency và thời gian backlog có thể được xử lý.

## 20. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Consumer lag tăng nhanh | Downstream xử lý chậm hơn ingestion rate. | Đo processing rate, giảm tốc độ gửi, kiểm tra năng lực downstream. |
| Consumer liên tục rebalance | Listener xử lý hoặc retry quá lâu giữa hai lần poll. | Giảm max.poll.records, tránh sleep dài, dùng pause-aware backoff và kiểm tra max.poll.interval.ms. |
| Queue tăng đến hết heap | Executor dùng queue không giới hạn hoặc consumer dispatch quá nhanh. | Dùng bounded queue, high/low watermark và pause/resume. |
| Downstream vẫn quá tải sau khi tăng consumer | Concurrency toàn cluster vượt năng lực hệ thống đích. | Đặt trần concurrency và rate limit global. |
| HTTP 429 tăng | Vượt quota API. | Tôn trọng Retry-After và giảm request rate. |
| Retry tạo đợt tải lớn khi dịch vụ phục hồi | Không có jitter hoặc mọi instance retry cùng lúc. | Exponential backoff với jitter và circuit breaker. |
| Record bị xử lý lặp | Side effect thành công nhưng offset chưa commit. | Dùng idempotency key hoặc inbox/deduplication. |
| Record sau vượt record lỗi | Retry topic làm thay đổi thứ tự xử lý. | Giữ partition/key lane hoặc dùng sequence nghiệp vụ. |
| Partition không tiếp tục sau khi downstream khỏe | Pause không được resume hoặc health signal không cập nhật. | Theo dõi pause state và kiểm tra control loop. |
| DLT tăng liên tục | Lỗi dữ liệu, cấu hình hoặc downstream không được phân loại đúng. | Phân tích exception và retry policy; không tự động replay vô hạn. |

## 21. Checklist triển khai production

Trước khi chạy consumer gọi downstream, hãy xác nhận:

1. Đã đo throughput và concurrency an toàn của hệ thống đích chưa?
2. max.poll.records có phù hợp với thời gian xử lý batch không?
3. Có timeout hữu hạn cho connect, read và toàn request không?
4. Có bounded queue và giới hạn worker không?
5. Có high/low watermark để điều khiển pause/resume không?
6. Consumer vẫn poll định kỳ khi partition đang pause không?
7. Chỉ consumer owner thread gọi KafkaConsumer pause/resume/commit/poll không?
8. Rate limiter có đúng phạm vi quota của downstream không?
9. Circuit breaker có giới hạn thời gian open và probe half-open không?
10. Retry có giới hạn attempt, tổng thời gian, backoff và jitter không?
11. Retry dài có dùng retry topic hoặc pause-aware backoff không?
12. DLT có lưu đủ metadata để điều tra và replay không?
13. Ordering theo partition/key có được bảo vệ khi retry không?
14. Offset chỉ commit sau khi side effect thành công hoặc retry record đã được ghi bền vững không?
15. Side effect có idempotency để xử lý duplicate không?
16. Có dashboard cho lag, processing rate, queue depth, downstream latency, retry và pause duration không?
17. Có thử nghiệm downstream chậm, HTTP 429/503, timeout và phục hồi trong môi trường lab không?

## 22. Bài tập thực hành

### Bài 1: Giả lập downstream chậm

1. Tạo topic orders-lab.
2. Chạy producer gửi 2.000 record/giây.
3. Viết consumer gọi một HTTP mock service.
4. Cấu hình mock service chỉ xử lý 500 request/giây.
5. Quan sát consumer lag và queue depth.
6. Giảm max.poll.records và giới hạn concurrency.
7. So sánh processing rate và downstream latency.

### Bài 2: Pause/resume theo queue watermark

1. Tạo bounded queue có capacity 200.
2. Consumer dispatch record vào worker pool.
3. Pause partition khi queue vượt 160 task.
4. Tiếp tục poll trong thời gian pause.
5. Resume khi queue giảm dưới 80 task.
6. Ghi lại số lần pause/resume và consumer lag.
7. Điều chỉnh ngưỡng để tránh dao động.

### Bài 3: Circuit breaker

1. Tạo mock API trả 200 bình thường.
2. Sau một khoảng thời gian, chuyển sang trả 503.
3. Cấu hình circuit breaker mở khi error rate vượt ngưỡng.
4. Khi circuit open, pause partition và tiếp tục poll.
5. Sau thời gian chờ, cho phép một số probe.
6. Khi probe thành công liên tiếp, resume consumer.
7. Đo số request thất bại trong thời gian downstream lỗi.

### Bài 4: Retry và DLT

1. Tạo topic orders, orders.retry và orders.DLT.
2. Cho mock service trả 503 trong một khoảng thời gian.
3. Retry với exponential backoff và jitter.
4. Hết retry budget thì publish DLT.
5. Kiểm tra metadata original topic/partition/offset và retry count.
6. Mô phỏng publish retry thành công nhưng commit offset gốc thất bại.
7. Giải thích vì sao consumer retry cần idempotent.

### Bài 5: Kiểm tra ordering

1. Gửi ba event cùng order key theo thứ tự Created, Paid, Shipped.
2. Cố tình làm event Created thất bại và chuyển sang retry topic.
3. Quan sát event Paid và Shipped có thể hoàn tất trước Created.
4. Thiết kế lại bằng pause partition hoặc key lane.
5. So sánh throughput với yêu cầu ordering.

## 23. Câu hỏi tự kiểm tra

1. Backpressure giải quyết vấn đề gì khi downstream chậm?
2. Vì sao consumer poll nhanh không có nghĩa nghiệp vụ xử lý nhanh?
3. max.poll.records có tác dụng gì và giới hạn gì?
4. Vì sao không nên Thread.sleep() dài trên consumer thread?
5. pause() có xóa assignment hoặc commit offset không?
6. Vì sao consumer vẫn cần poll khi partition đang pause?
7. Bounded queue ngăn loại sự cố nào?
8. Vì sao cần high watermark và low watermark khác nhau?
9. Rate limiter khác circuit breaker như thế nào?
10. HTTP 429 nên được xử lý ra sao?
11. Exponential backoff và jitter giúp giảm hiện tượng gì?
12. Vì sao retry topic có thể phá ordering?
13. Làm sao bảo đảm không mất record khi publish sang retry topic rồi commit input offset?
14. Vì sao side effect thành công nhưng offset commit thất bại có thể tạo duplicate?
15. Consumer lag tăng có luôn đồng nghĩa Kafka broker chậm không?
16. Khi nào nên pause một partition thay vì toàn bộ consumer?
17. Vì sao tăng concurrency có thể làm downstream quá tải hơn?
18. Kafka transaction có thể bao gồm một database transaction bên ngoài không?

## Kết luận

Khi hệ thống đích chậm hoặc không khả dụng, consumer cần điều tiết lượng công việc đang gửi xuống thay vì tiếp tục nhận và retry không giới hạn. Backpressure bằng pause/resume, bounded queue, giới hạn worker, rate limiter và circuit breaker giúp giữ tải trong phạm vi downstream có thể xử lý.

Retry cần phân loại lỗi, giới hạn số lần và tổng thời gian, dùng exponential backoff cùng jitter. Với thời gian chờ dài, retry topic hoặc pause-aware backoff giúp consumer tiếp tục duy trì poll loop. Khi chuyển record sang retry topic hoặc DLT, phải bảo đảm publish bền vững trước khi commit offset gốc và xử lý duplicate có thể xảy ra.

Cuối cùng, hãy theo dõi consumer lag cùng processing rate, queue depth, downstream latency, error rate và thời gian pause. Thiết kế tốt cho phép Kafka giữ backlog an toàn trong khi downstream phục hồi, sau đó tăng dần tốc độ xử lý mà không tạo thêm một đợt quá tải mới.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Backpressure | Điều tiết tốc độ nhận công việc theo năng lực xử lý phía sau. |
| pause() | Tạm dừng nhận record từ các partition được chỉ định. |
| resume() | Tiếp tục nhận record từ partition đã pause. |
| Bounded queue | Hàng đợi có giới hạn dung lượng để kiểm soát backlog trong ứng dụng. |
| High watermark / low watermark | Hai ngưỡng điều khiển pause và resume nhằm tránh dao động. |
| Rate limiter | Giới hạn số request hoặc tác vụ trong một đơn vị thời gian. |
| Token bucket | Thuật toán rate limiting dựa trên token được bổ sung theo tốc độ. |
| Circuit breaker | Cơ chế ngừng gọi downstream khi lỗi hoặc latency vượt ngưỡng. |
| Bulkhead | Cô lập worker, queue hoặc connection pool giữa các downstream. |
| Exponential backoff | Tăng dần thời gian chờ giữa các lần retry. |
| Jitter | Thêm ngẫu nhiên vào thời gian backoff để phân tán request retry. |
| Retry topic | Topic lưu record cần thử xử lý lại sau một khoảng chờ. |
| DLT/DLQ | Topic lưu record đã hết retry budget hoặc không thể xử lý. |
| Consumer lag | Khoảng cách giữa tiến độ consumer group và log cuối. |
| Processing rate | Tốc độ hoàn tất xử lý nghiệp vụ, khác với tốc độ poll. |
| Idempotency key | Định danh giúp hệ thống đích nhận diện và tránh lặp side effect. |


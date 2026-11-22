# Vòng lặp poll và giới hạn trách nhiệm của luồng consumer

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này tập trung vào vòng lặp **poll** của Java Kafka Consumer và ranh giới trách nhiệm của luồng đang sở hữu consumer.

Một consumer không chỉ gọi hàm lấy record. Vòng lặp poll còn tham gia duy trì hoạt động trong consumer group, nhận assignment, xử lý rebalance và cập nhật tiến độ đọc. Vì vậy, cách tổ chức xử lý record, commit offset và chạy tác vụ nền ảnh hưởng trực tiếp đến khả năng tránh mất dữ liệu, xử lý trùng và giữ thứ tự.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả vai trò của poll trong vòng đời Java Kafka Consumer.
- Giải thích vì sao KafkaConsumer không an toàn khi được gọi đồng thời từ nhiều thread.
- Phân biệt poll timeout, max.poll.interval.ms và session.timeout.ms.
- Tổ chức một vòng lặp poll có xử lý record, commit offset và shutdown đúng cách.
- Hiểu vai trò của ConsumerRebalanceListener khi partition được thu hồi hoặc phân công.
- Dùng pause/resume để kiểm soát backpressure mà vẫn tiếp tục poll.
- Quyết định khi nào xử lý đồng bộ trên consumer thread và khi nào chuyển công việc sang worker pool.
- Tránh commit offset vượt qua record chưa xử lý xong.
- Nhận biết các lỗi thường gặp khi xử lý batch lâu hoặc chia sẻ KafkaConsumer giữa nhiều thread.

## 2. poll là trung tâm của vòng đời consumer

Java Kafka Consumer API cung cấp phương thức **poll(Duration)** để lấy record từ những partition đang được gán cho consumer.

Một vòng đời cơ bản gồm:

1. Tạo KafkaConsumer với cấu hình kết nối, group ID và deserializer.
2. Gọi subscribe() để đăng ký topic với consumer group.
3. Gọi poll() lặp lại để nhận record và tham gia quá trình điều phối group.
4. Xử lý các record đã nhận.
5. Commit offset sau khi xử lý đạt điều kiện an toàn.
6. Tiếp tục poll cho đến khi ứng dụng dừng.
7. Đóng consumer để giải phóng network connection và tài nguyên.

~~~mermaid
flowchart TD
    A[Tạo KafkaConsumer] --> B[subscribe topics]
    B --> C[poll(Duration)]
    C --> D{Có record?}
    D -->|Có| E[Xử lý batch]
    E --> F{Xử lý thành công?}
    F -->|Có| G[Commit offset]
    F -->|Không| H[Không commit batch lỗi]
    G --> C
    H --> I[Retry / dừng / xử lý lỗi]
    I --> C
    D -->|Không| J[Kiểm tra trạng thái và tiếp tục poll]
    J --> C
    C --> K[Shutdown]
    K --> L[close consumer]
~~~

Nếu poll trả về batch rỗng, đó không nhất thiết là lỗi. Consumer có thể đang chờ record mới, chưa được gán partition hoặc hiện tại không có record nào sẵn sàng để trả về.

### 2.1. poll không chỉ lấy dữ liệu

Khi ứng dụng gọi poll(), Kafka client thực hiện nhiều công việc cần thiết cho consumer group:

- Lấy record từ các partition được gán.
- Tham gia hoặc hoàn tất quá trình join group khi cần.
- Xử lý assignment và rebalance.
- Kích hoạt callback của ConsumerRebalanceListener trong các tình huống phù hợp.
- Cập nhật trạng thái và metadata nội bộ của consumer.
- Tiếp tục tiến trình hoạt động của consumer group.

Các phiên bản Kafka client hiện đại có heartbeat thread nội bộ để gửi heartbeat độc lập. Tuy vậy, ứng dụng vẫn phải gọi poll thường xuyên. Nếu thời gian giữa hai lần poll vượt quá max.poll.interval.ms, consumer có thể bị coi là không còn xử lý tiến độ và bị rời group, dù heartbeat thread vẫn hoạt động trong một khoảng thời gian.

Vì vậy, không nên xem poll là một lời gọi fetch dữ liệu đơn thuần. Nó là một phần của giao thức điều phối consumer group.

## 3. KafkaConsumer chỉ nên được sở hữu bởi một thread

**KafkaConsumer không thread-safe.** Một instance consumer không được nhiều thread gọi đồng thời các phương thức như poll(), commitSync(), subscribe(), pause(), resume() hoặc close().

Một thread nên chịu trách nhiệm duy nhất đối với các thao tác consumer:

- Gọi poll().
- Đọc trạng thái assignment và position.
- Gọi commitSync() hoặc commitAsync().
- Thay đổi pause/resume.
- Xử lý rebalance callback.
- Đóng consumer.

Các thread khác có thể thực hiện công việc nghiệp vụ nếu ứng dụng chủ động chuyển record sang worker pool. Tuy nhiên, worker không được trực tiếp gọi các phương thức KafkaConsumer. Kết quả hoàn thành từ worker nên được gửi ngược về thread sở hữu consumer thông qua queue hoặc cơ chế trao đổi thread-safe.

Có một ngoại lệ quan trọng: **wakeup() được thiết kế để có thể gọi từ thread khác** nhằm đánh thức poll đang chờ và giúp ứng dụng shutdown. Đây là phương thức an toàn để dùng từ shutdown hook hoặc thread điều khiển. Ngoại lệ này không làm KafkaConsumer trở thành thread-safe.

### 3.1. Mô hình sở hữu consumer

~~~mermaid
flowchart TD
    subgraph Owner["Consumer owner thread"]
        P[poll]
        A[assignment / position]
        C[commit offsets]
        R[pause / resume]
        P --> A
        A --> C
        C --> R
    end

    P --> Q[Hàng đợi công việc]
    Q --> W1[Worker 1]
    Q --> W2[Worker 2]
    Q --> W3[Worker 3]
    W1 --> D[Hàng đợi kết quả]
    W2 --> D
    W3 --> D
    D --> C
    S[Shutdown thread] -->|wakeup()| P
~~~

Thread sở hữu consumer kiểm soát việc lấy record và tiến độ offset. Worker chỉ xử lý dữ liệu đã nhận và trả kết quả. Cách tổ chức này tránh truy cập đồng thời vào consumer và giúp việc commit offset có một nơi kiểm soát rõ ràng.

## 4. Các cấu hình ảnh hưởng đến poll loop

Một số cấu hình consumer quyết định số record mỗi lần nhận, thời gian xử lý tối đa giữa hai lần poll và cách bắt đầu đọc.

| Cấu hình | Vai trò |
|---|---|
| group.id | Định danh consumer group. |
| enable.auto.commit | Bật hoặc tắt commit offset tự động. |
| auto.commit.interval.ms | Chu kỳ commit khi auto commit được bật. |
| max.poll.records | Số record tối đa consumer trả về trong một lần poll. |
| max.poll.interval.ms | Khoảng thời gian tối đa giữa các lần poll trước khi consumer bị xem là không còn tiến triển. |
| session.timeout.ms | Thời gian coordinator chờ heartbeat trước khi xem consumer là không còn hoạt động. |
| heartbeat.interval.ms | Khoảng cách heartbeat của consumer group; cần phù hợp với session timeout. |
| max.partition.fetch.bytes | Giới hạn dữ liệu fetch cho một partition trong một request theo cấu hình client. |
| fetch.max.bytes | Giới hạn tổng dữ liệu fetch trong một request theo cấu hình client. |
| auto.offset.reset | Chính sách bắt đầu khi group chưa có offset hợp lệ hoặc offset cũ không còn khả dụng. |

### 4.1. max.poll.records

max.poll.records giới hạn số record tối đa được trả về trong một lần poll. Nó không phải giới hạn tổng số byte mà broker gửi qua network; kích thước fetch còn chịu ảnh hưởng của các cấu hình fetch khác.

Ví dụ:

~~~properties
max.poll.records=100
~~~

Consumer nhận tối đa 100 record trong một lần poll. Nếu xử lý mỗi record mất trung bình 50 ms và xử lý tuần tự 100 record, riêng phần xử lý có thể mất khoảng 5 giây, chưa tính database, network và commit.

Khi chọn max.poll.records, hãy đo thời gian xử lý batch ở trường hợp tải cao, không chỉ lấy thời gian trung bình của một record.

### 4.2. max.poll.interval.ms

max.poll.interval.ms giới hạn thời gian giữa các lần gọi poll(). Nếu ứng dụng xử lý một batch quá lâu rồi mới gọi poll tiếp theo, consumer có thể vượt ngưỡng và bị rời group. Partition sau đó có thể được giao cho consumer khác.

Ví dụ:

~~~properties
max.poll.interval.ms=300000
max.poll.records=100
~~~

Giá trị 300.000 ms tương đương 5 phút trong ví dụ. Đây không phải khuyến nghị chung cho mọi ứng dụng; cần điều chỉnh dựa trên thời gian xử lý batch và SLA.

Nếu thời gian xử lý thường xuyên gần hoặc vượt giới hạn, có thể:

- Giảm max.poll.records để mỗi batch nhỏ hơn.
- Tối ưu xử lý record hoặc giảm thời gian chờ dịch vụ phụ thuộc.
- Dùng worker pool nhưng vẫn tiếp tục poll và kiểm soát số công việc đang chạy.
- Điều chỉnh max.poll.interval.ms nếu thời gian xử lý dài là yêu cầu có chủ đích và các rủi ro rebalance đã được đánh giá.

Chỉ tăng max.poll.interval.ms không giải quyết được worker bị treo, xử lý mất kiểm soát hoặc backlog tăng không giới hạn.

### 4.3. session.timeout.ms khác max.poll.interval.ms

Hai cấu hình này xử lý hai tình huống khác nhau:

- **session.timeout.ms:** coordinator dùng heartbeat để phát hiện consumer không còn hoạt động.
- **max.poll.interval.ms:** giới hạn thời gian ứng dụng không gọi poll, phản ánh việc consumer không tiếp tục tiến độ xử lý.

Heartbeat thread nội bộ có thể vẫn gửi heartbeat trong lúc ứng dụng đang xử lý batch. Nhưng nếu ứng dụng không gọi poll trong thời gian quá max.poll.interval.ms, consumer vẫn có thể rời group. Vì vậy, heartbeat thành công không có nghĩa poll loop đang khỏe.

### 4.4. enable.auto.commit

Với enable.auto.commit=true, Kafka client tự động commit offset theo chu kỳ cấu hình. Cách này đơn giản nhưng có thể không phù hợp khi xử lý nghiệp vụ mất thời gian.

Ví dụ rủi ro:

1. Consumer poll và nhận một batch record.
2. Ứng dụng mới xử lý được một phần batch.
3. Offset của batch đã được commit theo cơ chế auto commit.
4. Ứng dụng bị dừng trước khi xử lý phần còn lại.
5. Khi chạy lại, consumer có thể tiếp tục sau các record đã commit và bỏ qua phần nghiệp vụ chưa hoàn tất.

Với ứng dụng cần kiểm soát thời điểm commit theo kết quả xử lý, thường nên dùng:

~~~properties
enable.auto.commit=false
~~~

Sau đó, ứng dụng chủ động commit khi đã xử lý an toàn.

## 5. Xây dựng poll loop cơ bản với commit thủ công

Ví dụ dưới đây xử lý record tuần tự trên consumer thread. Consumer chỉ commit sau khi toàn bộ batch được xử lý thành công.

~~~java
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.errors.WakeupException;
import org.apache.kafka.common.serialization.StringDeserializer;

import java.time.Duration;
import java.util.List;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicBoolean;

public class OrdersConsumer {

    public static void main(String[] args) {
        Properties properties = new Properties();

        properties.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "orders-service"
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
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest"
        );
        properties.put(
            ConsumerConfig.MAX_POLL_RECORDS_CONFIG,
            100
        );
        properties.put(
            ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG,
            300000
        );

        AtomicBoolean running = new AtomicBoolean(true);

        try (KafkaConsumer<String, String> consumer =
                 new KafkaConsumer<>(properties)) {

            Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                running.set(false);
                consumer.wakeup();
            }));

            consumer.subscribe(List.of("orders"));

            try {
                while (running.get()) {
                    ConsumerRecords<String, String> records =
                        consumer.poll(Duration.ofSeconds(1));

                    if (records.isEmpty()) {
                        continue;
                    }

                    for (ConsumerRecord<String, String> record : records) {
                        process(record);

                        System.out.printf(
                            "topic=%s partition=%d offset=%d key=%s%n",
                            record.topic(),
                            record.partition(),
                            record.offset(),
                            record.key()
                        );
                    }

                    // Chỉ commit sau khi toàn bộ batch đã xử lý thành công.
                    consumer.commitSync();
                }
            } catch (WakeupException exception) {
                if (running.get()) {
                    throw exception;
                }
            }
        } catch (Exception exception) {
            // Ghi log và chuyển lỗi lên cơ chế giám sát của ứng dụng.
            exception.printStackTrace();
        }
    }

    private static void process(ConsumerRecord<String, String> record) {
        // Thực hiện nghiệp vụ, ví dụ cập nhật trạng thái đơn hàng.
        // Nếu xử lý thất bại, ném exception để batch không bị commit.
    }
}
~~~

Trong ví dụ:

- Consumer được tạo và sử dụng trong main thread.
- Shutdown hook chỉ gọi wakeup() và cập nhật cờ dừng.
- poll() lấy batch record.
- process() xử lý tuần tự.
- commitSync() chỉ được gọi sau khi toàn bộ batch hoàn tất.
- Nếu process() ném exception, commitSync() không chạy và offset chưa được commit có thể được đọc lại sau restart.
- try-with-resources đóng consumer khi thoát vòng lặp.

Đây là mẫu xử lý at-least-once ở mức consumer offset. Nếu một record đã cập nhật database thành công nhưng ứng dụng dừng trước commit, record có thể được giao lại. Vì thế, thao tác nghiệp vụ nên idempotent hoặc có cơ chế deduplication.

Trong ứng dụng thật, cần thay phần xử lý exception bằng logging, retry, dead-letter topic hoặc dừng consumer theo chính sách đã thiết kế. Không nên bắt exception rồi bỏ qua nhưng vẫn commit cả batch nếu record lỗi chưa được xử lý.

## 6. Commit offset: vị trí tiếp theo cần đọc

Khi commit offset, consumer thường commit **vị trí tiếp theo cần đọc**, không phải offset của record cuối cùng đã xử lý.

Ví dụ:

~~~text
Partition 0:
Offset 10 -> đã xử lý
Offset 11 -> đã xử lý
Offset 12 -> đã xử lý

Committed offset = 13
~~~

Nếu commit theo từng record bằng OffsetAndMetadata, giá trị cần commit thường là record.offset() + 1.

~~~java
TopicPartition partition =
    new TopicPartition(record.topic(), record.partition());

OffsetAndMetadata nextOffset =
    new OffsetAndMetadata(record.offset() + 1);

consumer.commitSync(Map.of(partition, nextOffset));
~~~

Đoạn mã này yêu cầu import TopicPartition và OffsetAndMetadata. Chỉ dùng cách commit theo từng record khi record đó đã được xử lý thành công và không có record trước nó trong cùng partition còn đang chờ xử lý.

### 6.1. commitSync và commitAsync

| Phương thức | Đặc điểm | Khi cân nhắc |
|---|---|---|
| commitSync() | Chờ broker xác nhận commit; lỗi có thể được báo ngay tại lời gọi. | Cần kiểm soát tiến độ và xác nhận commit trước khi tiếp tục. |
| commitAsync() | Gửi commit bất đồng bộ; callback nhận kết quả sau đó. | Cần giảm thời gian chờ trong poll loop và có chiến lược xử lý lỗi phù hợp. |

commitSync() đơn giản để học và dễ xác định điểm commit. Tuy nhiên, nó có thể làm poll loop chờ network. commitAsync() không nên được dùng theo kiểu gửi nhiều commit tùy ý rồi bỏ qua lỗi; callback và thứ tự commit cần được quản lý để tránh commit cũ ghi đè tiến độ mới.

Một mẫu thường gặp là dùng commitAsync() trong luồng bình thường và commitSync() khi shutdown hoặc trước khi partition bị thu hồi. Cần bảo đảm không commit offset vượt quá record đã xử lý.

## 7. Rebalance và ConsumerRebalanceListener

Consumer group phân chia partition giữa các consumer. Khi consumer tham gia, rời group hoặc cluster thay đổi assignment, Kafka có thể thực hiện rebalance.

Trong quá trình rebalance:

- Consumer có thể bị thu hồi một số partition.
- Partition có thể được gán cho consumer khác.
- Consumer cần dừng xử lý công việc thuộc partition đã mất quyền sở hữu.
- Offset của record đã xử lý cần được commit đúng thời điểm nếu dùng manual commit.
- Tài nguyên gắn với partition như buffer hoặc state cục bộ cần được giải phóng hoặc chuyển giao.

Kafka cung cấp **ConsumerRebalanceListener** để ứng dụng phản ứng khi partition bị thu hồi hoặc được gán.

### 7.1. Đăng ký callback

~~~java
consumer.subscribe(
    List.of("orders"),
    new ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(
            Collection<TopicPartition> partitions
        ) {
            // Hoàn tất/commit tiến độ an toàn trước khi mất assignment.
            consumer.commitSync();
        }

        @Override
        public void onPartitionsAssigned(
            Collection<TopicPartition> partitions
        ) {
            for (TopicPartition partition : partitions) {
                System.out.printf(
                    "Assigned %s-%d%n",
                    partition.topic(),
                    partition.partition()
                );
            }
        }
    }
);
~~~

Ví dụ trên giả định ứng dụng xử lý đồng bộ toàn bộ batch trước khi gọi poll tiếp theo. Trong mô hình này, khi callback revoke được gọi, các record từ poll trước đã được xử lý xong và commit định kỳ.

Nếu xử lý bất đồng bộ, không thể gọi commitSync() một cách máy móc trong callback. Cần chỉ commit các offset có xử lý hoàn tất, chờ hoặc hủy công việc thuộc partition bị thu hồi và ngăn worker cũ ghi kết quả sau khi partition đã được giao cho consumer khác.

### 7.2. onPartitionsRevoked và onPartitionsAssigned

- **onPartitionsRevoked:** được gọi khi consumer sắp mất một số partition trong quá trình rebalance. Đây là thời điểm phù hợp để commit tiến độ đã xử lý an toàn và giải phóng tài nguyên gắn với partition.
- **onPartitionsAssigned:** được gọi khi consumer nhận partition. Ứng dụng có thể khởi tạo state cục bộ hoặc khôi phục dữ liệu cần thiết.

Callback được gọi trên thread đang thực hiện poll. Không tạo một luồng khác để gọi consumer từ callback.

### 7.3. Rebalance có thể gây xử lý lặp

Giả sử consumer A xử lý record offset 50 nhưng chưa commit. Partition bị thu hồi và giao cho consumer B. Consumer B tiếp tục từ offset đã commit trước đó nên có thể đọc lại offset 50.

Đây là hành vi bình thường của at-least-once. Ứng dụng phải thiết kế xử lý idempotent và không giả định một record chỉ được gọi process() đúng một lần.

## 8. Giới hạn thời gian xử lý trong poll loop

Nếu xử lý đồng bộ trên consumer thread, thời gian xử lý toàn batch phải đủ ngắn để poll tiếp theo diễn ra trước max.poll.interval.ms.

Giả sử:

- max.poll.records = 100.
- Thời gian xử lý trung bình mỗi record = 100 ms.
- Xử lý tuần tự.

Thời gian xử lý batch có thể khoảng 10 giây, chưa kể thời gian gọi database, API, commit và các thao tác khác. Nếu một số record có độ trễ bất thường, batch có thể mất nhiều thời gian hơn đáng kể.

Cần đo các số liệu:

- Số record mỗi poll.
- Thời gian poll.
- Thời gian xử lý từng record và cả batch.
- Thời gian commit.
- Thời gian lớn nhất giữa hai lần poll.
- Số lần rebalance và nguyên nhân.
- Consumer lag theo partition.

Nếu batch xử lý lâu, có thể giảm max.poll.records hoặc chuyển phần xử lý nặng sang worker pool. Nhưng chuyển việc sang worker pool kéo theo bài toán kiểm soát offset và thứ tự.

## 9. Khi nào nên dùng worker pool?

Xử lý tuần tự trong consumer thread dễ giữ thứ tự và commit an toàn, nhưng có thể không tận dụng được CPU hoặc I/O khi xử lý record tốn thời gian.

Worker pool có thể hữu ích khi:

- Xử lý record độc lập và có thể chạy song song.
- Tác vụ chủ yếu chờ I/O như gọi dịch vụ hoặc truy vấn dữ liệu.
- Throughput yêu cầu cao hơn khả năng xử lý tuần tự.
- Ứng dụng có thể kiểm soát số công việc đang chạy và tiến độ hoàn tất.

Tuy nhiên, không nên chuyển record sang executor không giới hạn rồi tiếp tục poll vô hạn. Nếu worker xử lý chậm hơn tốc độ nhận, hàng đợi sẽ tăng liên tục, bộ nhớ bị tiêu thụ và consumer có thể commit sai tiến độ.

### 9.1. Kiến trúc consumer thread và worker pool

~~~mermaid
flowchart LR
    K[(Kafka partitions)] --> C[Consumer owner thread]
    C --> P[poll]
    P --> Q[Bounded work queue]
    Q --> W1[Worker 1]
    Q --> W2[Worker 2]
    Q --> W3[Worker 3]
    W1 --> R[Completion queue]
    W2 --> R
    W3 --> R
    R --> C
    C --> O[Commit contiguous offsets]
~~~

Luồng owner thread:

1. Poll record từ Kafka.
2. Kiểm tra năng lực tiếp nhận của worker pool.
3. Chuyển record cùng metadata topic-partition-offset vào hàng đợi có giới hạn.
4. Tiếp tục poll theo nhịp phù hợp để giữ group hoạt động.
5. Nhận thông báo hoàn tất từ worker.
6. Cập nhật tiến độ xử lý theo từng partition.
7. Chỉ commit offset an toàn.

Worker thread:

1. Nhận record đã được giao.
2. Thực hiện nghiệp vụ.
3. Trả kết quả thành công/thất bại cùng topic-partition-offset.
4. Không gọi KafkaConsumer.

### 9.2. Commit theo thứ tự hoàn tất, không theo offset lớn nhất

Giả sử một partition có ba record:

~~~text
Offset 10 -> Worker A đang xử lý
Offset 11 -> Worker B đã xử lý xong
Offset 12 -> Worker C đã xử lý xong
~~~

Nếu ứng dụng commit offset 13 chỉ vì worker B và C hoàn tất, consumer có thể bỏ qua offset 10 sau restart dù record đó chưa được xử lý.

Với mỗi partition, chỉ được commit đến vị trí tiếp theo sau **chuỗi record liên tục đã xử lý hoàn tất từ đầu**.

Trong ví dụ:

- Offset 11 và 12 đã xong.
- Offset 10 chưa xong.
- Vị trí an toàn vẫn chưa vượt qua offset 10.

Khi offset 10 hoàn tất, ứng dụng có thể commit offset 13 nếu cả 10, 11 và 12 đều đã hoàn tất.

Quy tắc này rất quan trọng khi worker pool xử lý song song. Việc commit offset lớn nhất đã hoàn tất không bảo đảm các offset nhỏ hơn cũng đã hoàn tất.

### 9.3. Giữ ordering theo partition

Kafka bảo đảm thứ tự record trong một partition. Nhưng nếu ứng dụng chuyển các record của cùng partition đến nhiều worker độc lập, thời gian hoàn thành có thể đảo thứ tự.

Ví dụ:

~~~text
Partition 0:
Offset 20 -> UpdateBalance(account-1)
Offset 21 -> Withdraw(account-1)
~~~

Nếu offset 21 hoàn thành trước offset 20, nghiệp vụ có thể sai dù Kafka đã giao record đúng thứ tự.

Các cách xử lý:

- Xử lý tuần tự theo partition.
- Dùng worker lane riêng cho mỗi partition.
- Dùng key để định tuyến record cùng thực thể đến cùng luồng xử lý tuần tự.
- Dùng cơ chế quản lý thứ tự hoàn tất và chỉ commit chuỗi offset liên tục.

Không nên tăng số worker một cách tùy tiện khi các event có quan hệ thứ tự nghiệp vụ.

## 10. Backpressure bằng pause và resume

Nếu worker pool đã đầy, consumer có thể tạm dừng nhận record từ một số partition bằng **pause()**. Khi worker xử lý xong và hàng đợi giảm, consumer gọi **resume()** để tiếp tục fetch record.

Ví dụ:

~~~java
Set<TopicPartition> assigned =
    consumer.assignment();

if (workQueue.remainingCapacity() == 0) {
    consumer.pause(assigned);
} else if (!assigned.isEmpty()) {
    consumer.resume(assigned);
}

ConsumerRecords<String, String> records =
    consumer.poll(Duration.ofMillis(500));
~~~

Đây là ví dụ minh họa ý tưởng; trong ứng dụng thực tế cần tính cả record đã nhận trong poll hiện tại, công việc đang chạy và giới hạn queue. Không nên chỉ kiểm tra remainingCapacity rồi bỏ qua khả năng nhiều record trong một batch làm queue vượt giới hạn.

Các nguyên tắc:

- Hàng đợi công việc nên có giới hạn.
- Pause/resume phải được gọi trên consumer owner thread.
- Tiếp tục gọi poll() kể cả khi partition đang pause để consumer duy trì hoạt động group.
- Chỉ resume partition khi năng lực xử lý đã sẵn sàng.
- Không pause vĩnh viễn mà không có cơ chế timeout hoặc giám sát.
- Khi rebalance thu hồi partition, hủy hoặc xử lý an toàn công việc còn tồn đọng của partition đó.

pause() không xóa assignment và không commit offset. Nó chỉ yêu cầu consumer tạm thời không nhận record mới từ các partition đã pause.

## 11. subscribe() và assign()

Kafka Consumer có hai cách nhận partition:

| Cách | Cơ chế | Trường hợp dùng |
|---|---|---|
| subscribe(topics) | Consumer tham gia group coordination và Kafka phân phối partition | Hầu hết ứng dụng consumer group thông thường. |
| assign(partitions) | Ứng dụng tự chỉ định partition | Trường hợp cần kiểm soát assignment thủ công hoặc triển khai consumer độc lập. |

Với subscribe(), consumer cần poll để hoàn tất group coordination và nhận assignment. Rebalance có thể xảy ra khi thành viên group thay đổi.

Với assign(), ứng dụng tự quản lý partition; không có cơ chế group rebalance tự động cho assignment đó. Cần hiểu rõ trách nhiệm quản lý tiến độ và tránh để hai consumer cùng xử lý một partition nếu không có cơ chế phối hợp.

Không nên gọi subscribe() và assign() đan xen tùy tiện trên cùng consumer. Hãy chọn một mô hình assignment rõ ràng cho vòng đời consumer.

## 12. Shutdown consumer đúng cách

Khi ứng dụng dừng, consumer cần thoát poll loop và đóng tài nguyên.

Một quy trình phù hợp:

1. Thread điều khiển cập nhật cờ dừng.
2. Gọi consumer.wakeup() để đánh thức poll đang chờ.
3. Consumer owner thread bắt WakeupException.
4. Nếu ứng dụng đang shutdown, thoát vòng lặp.
5. Đóng consumer trên owner thread bằng close(Duration).
6. Hoàn tất các tài nguyên khác theo thứ tự đã thiết kế.

Không nên gọi close() đồng thời từ shutdown hook trong khi owner thread đang poll. Dùng wakeup() để báo hiệu, rồi để owner thread tự đóng consumer.

Nếu có worker pool, shutdown còn cần quy định:

- Ngừng nhận record mới.
- Chờ công việc đã giao hoàn tất trong giới hạn thời gian.
- Commit các offset đã xử lý an toàn.
- Không commit công việc còn dang dở.
- Đóng executor và consumer đúng thứ tự.

## 13. Poll loop trong Spring Kafka

Khi dùng Spring Kafka với **@KafkaListener**, framework quản lý KafkaConsumer và vòng lặp poll bên trong listener container.

Ví dụ:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        topics = "orders",
        groupId = "orders-service"
    )
    public void onMessage(
        String message,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset
    ) {
        System.out.printf(
            "partition=%d offset=%d message=%s%n",
            partition,
            offset,
            message
        );

        // Xử lý nghiệp vụ.
    }
}
~~~

Trong mô hình này:

- Listener container tạo và quản lý consumer.
- Container gọi poll theo cấu hình.
- Listener được gọi khi có record hoặc batch.
- Container quản lý commit theo AckMode và cấu hình listener.
- Ứng dụng cần hiểu cơ chế acknowledgement và error handler của Spring Kafka.

Không tự tạo một vòng poll khác hoặc gọi trực tiếp consumer nội bộ của listener container. Nếu dùng @KafkaListener, hãy cấu hình concurrency, AckMode, error handler và retry theo cơ chế của Spring Kafka.

Nếu listener chuyển công việc sang executor bất đồng bộ, cần dùng cơ chế acknowledgement phù hợp và bảo đảm không commit trước khi xử lý hoàn tất. Không được mặc định rằng listener trả về ngay sau khi submit task đồng nghĩa nghiệp vụ đã thành công.

## 14. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Consumer liên tục rebalance | Xử lý batch quá lâu, consumer restart hoặc heartbeat/session timeout. | Kiểm tra max.poll.interval.ms, session.timeout.ms, poll duration và broker/client logs. |
| CommitFailedException | Partition đã bị thu hồi hoặc group generation không còn hợp lệ khi commit. | Kiểm tra rebalance, thời gian xử lý và commit trong đúng owner thread. |
| WakeupException khi shutdown | Thread khác gọi wakeup() để đánh thức poll. | Chỉ bỏ qua khi ứng dụng đang shutdown; nếu không, xử lý như lỗi. |
| Duplicate record sau restart | Record đã xử lý nhưng offset chưa commit. | Thiết kế consumer idempotent và commit sau xử lý. |
| Record bị bỏ qua sau restart | Offset được commit trước khi xử lý hoàn tất. | Tắt auto commit và kiểm soát commit thủ công. |
| Consumer lag tăng dù CPU thấp | Consumer chờ database/API, poll không đủ nhanh hoặc partition bị giới hạn. | Đo thời gian xử lý, kiểm tra dependency, worker queue và partition assignment. |
| OutOfMemoryError khi dùng worker pool | Hàng đợi không giới hạn hoặc nhận record nhanh hơn xử lý. | Dùng bounded queue, pause/resume và giới hạn số công việc đang chạy. |
| Ordering nghiệp vụ sai | Worker xử lý song song làm record cùng partition hoàn tất sai thứ tự. | Xử lý tuần tự theo partition/key hoặc quản lý sequence và offset hoàn tất. |

## 15. Checklist thiết kế poll loop

Trước khi đưa consumer vào production, hãy kiểm tra:

1. KafkaConsumer có được sở hữu bởi một thread duy nhất không?
2. Mọi lời gọi poll, commit, pause, resume và close có nằm trên owner thread không?
3. enable.auto.commit có phù hợp với cách xử lý record không?
4. max.poll.records có phù hợp với thời gian xử lý batch không?
5. Thời gian giữa hai lần poll có thấp hơn max.poll.interval.ms không?
6. session.timeout.ms và heartbeat.interval.ms có phù hợp với cấu hình group không?
7. ConsumerRebalanceListener có xử lý partition revoke/assign đúng cách không?
8. Offset chỉ được commit sau khi record tương ứng xử lý thành công không?
9. Nếu worker pool được dùng, có bounded queue và backpressure không?
10. Commit có giữ thứ tự liên tục theo từng partition không?
11. Consumer có xử lý duplicate bằng idempotency không?
12. Shutdown có dùng wakeup() và close() đúng thread không?
13. Có metric cho poll latency, processing latency, commit latency, rebalance và consumer lag không?

## 16. Bài tập thực hành

### Bài 1: Viết consumer poll loop cơ bản

Tạo topic **orders-lab** và viết Java consumer:

- group.id là orders-lab-reader.
- enable.auto.commit=false.
- max.poll.records=20.
- poll mỗi lần với timeout 1 giây.
- In topic, partition, offset, key và value.
- Commit đồng bộ sau khi toàn bộ batch xử lý thành công.
- Dừng ứng dụng bằng Ctrl+C và đóng consumer an toàn.

### Bài 2: Quan sát max.poll.interval.ms

1. Cấu hình max.poll.interval.ms nhỏ trong môi trường lab.
2. Thêm thời gian chờ giả lập trong hàm process().
3. Gửi batch đủ lớn để thời gian xử lý vượt ngưỡng.
4. Quan sát rebalance và commit failure.
5. Giảm max.poll.records hoặc tối ưu xử lý.
6. Chạy lại và so sánh.

Không dùng cấu hình thử nghiệm này trên consumer production.

### Bài 3: Kiểm tra rebalance callback

1. Chạy hai consumer cùng group.
2. Theo dõi onPartitionsAssigned và onPartitionsRevoked.
3. Dừng một consumer.
4. Quan sát partition được giao lại.
5. Kiểm tra offset đã commit và record có thể được đọc lại.
6. Giải thích vì sao rebalance có thể dẫn đến duplicate nếu batch chưa commit.

### Bài 4: Tổ chức worker pool an toàn

1. Tạo bounded queue và worker pool có số thread cố định.
2. Consumer owner thread poll và chuyển record cho worker.
3. Worker chỉ xử lý dữ liệu và gửi kết quả về completion queue.
4. Consumer owner thread theo dõi tiến độ hoàn tất theo từng partition.
5. Chỉ commit offset khi tất cả record trước đó trong partition đã hoàn tất.
6. Thử làm cho record offset thấp xử lý chậm hơn record offset cao và xác nhận consumer không commit vượt qua khoảng trống.

## 17. Câu hỏi tự kiểm tra

1. Vì sao poll() cần được gọi thường xuyên ngay cả khi consumer không nhận được record?
2. KafkaConsumer có thread-safe không? Phương thức nào là ngoại lệ cho phép gọi từ thread khác?
3. max.poll.records giới hạn điều gì?
4. max.poll.interval.ms khác session.timeout.ms như thế nào?
5. Vì sao auto commit có thể làm mất tiến độ nghiệp vụ khi batch xử lý lâu?
6. Vì sao commit offset thường là offset của record kế tiếp cần đọc?
7. ConsumerRebalanceListener được gọi trong những tình huống nào?
8. Vì sao worker thread không nên gọi commitSync() trực tiếp?
9. Nếu offset 11 và 12 đã hoàn tất nhưng offset 10 chưa xong, consumer có thể commit 13 không?
10. pause() có thay thế việc gọi poll() không?
11. Vì sao worker pool cần bounded queue?
12. Làm sao shutdown consumer mà không gọi close() từ thread khác?
13. Khi dùng @KafkaListener, thành phần nào quản lý poll loop?
14. Làm sao giữ thứ tự nghiệp vụ khi xử lý song song?

## Kết luận

Vòng lặp poll là trung tâm điều khiển hoạt động của Java Kafka Consumer. Consumer cần gọi poll thường xuyên để nhận record và duy trì tiến độ consumer group. KafkaConsumer không thread-safe, vì vậy một owner thread phải quản lý poll, commit, assignment, pause/resume và close; thread khác chỉ nên gửi tín hiệu wakeup hoặc xử lý công việc đã được chuyển giao.

Xử lý tuần tự giúp đơn giản hóa ordering và commit offset. Khi dùng worker pool, ứng dụng cần bounded queue, backpressure và theo dõi tiến độ hoàn tất theo từng partition. Chỉ commit đến offset tiếp theo sau chuỗi record đã xử lý liên tục, không commit vượt qua record còn dang dở.

Nắm chắc trách nhiệm của poll loop giúp consumer ổn định khi rebalance, restart, xử lý chậm và tải tăng. Đây là nền tảng để triển khai retry, idempotency, manual commit và các mô hình xử lý bất đồng bộ trong Java/Spring Kafka.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| poll() | Lấy record và tham gia tiến trình điều phối consumer group. |
| KafkaConsumer | Client đọc record từ Kafka; không thread-safe. |
| Owner thread | Thread duy nhất quản lý các thao tác KafkaConsumer. |
| max.poll.records | Số record tối đa trả về trong một lần poll. |
| max.poll.interval.ms | Thời gian tối đa giữa hai lần poll. |
| session.timeout.ms | Thời gian coordinator chờ heartbeat trước khi xem consumer không còn hoạt động. |
| commitSync() | Commit offset và chờ broker xác nhận. |
| commitAsync() | Gửi yêu cầu commit bất đồng bộ. |
| ConsumerRebalanceListener | Callback xử lý partition revoke và assign. |
| pause()/resume() | Tạm dừng hoặc tiếp tục nhận record từ partition. |
| Backpressure | Điều tiết tốc độ nhận dữ liệu theo năng lực xử lý. |
| Bounded queue | Hàng đợi có giới hạn dung lượng để kiểm soát backlog. |
| WakeupException | Exception phát sinh khi consumer.wakeup() đánh thức poll. |


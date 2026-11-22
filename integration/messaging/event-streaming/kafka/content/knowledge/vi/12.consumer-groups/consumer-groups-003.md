# Số consumer hữu ích và giới hạn từ số partition

Trong một Kafka consumer group, số consumer có thể xử lý dữ liệu song song bị giới hạn bởi số partition được gán cho group. Với một topic có \(P\) partition và một group có \(C\) consumer cùng subscribe topic đó, số consumer được cấp ít nhất một partition tại cùng thời điểm không thể vượt quá:

\[
\text{consumer hoạt động tối đa} = \min(P, C)
\]

Nếu có ít consumer hơn partition, mỗi consumer thường nhận nhiều partition. Nếu số consumer lớn hơn số partition, phần consumer dư sẽ không được gán partition và không trực tiếp tăng throughput của group.

Đây là giới hạn quan trọng khi thiết kế Kafka. Tăng số consumer chỉ có ích khi group còn partition chưa được khai thác hoặc consumer hiện tại đang là nút thắt có thể chia nhỏ theo partition. Ngược lại, tạo thêm consumer khi mọi partition đã có người xử lý thường chỉ làm tăng tài nguyên và hoạt động rebalance.

## 1. Vì sao partition giới hạn số consumer hữu ích?

Kafka chia topic thành các partition độc lập. Trong một consumer group, tại một thời điểm, mỗi partition chỉ được gán cho tối đa một consumer member của group. Quy tắc này giúp group quản lý offset và duy trì thứ tự đọc trong từng partition.

Ví dụ, topic orders có bốn partition:

~~~text
orders
  partition 0
  partition 1
  partition 2
  partition 3
~~~

Nếu group billing có hai consumer, Kafka có thể phân bổ:

~~~text
Consumer A: partition 0, partition 1
Consumer B: partition 2, partition 3
~~~

Hai consumer có thể poll và xử lý các partition được giao đồng thời. Nếu group có bốn consumer:

~~~text
Consumer A: partition 0
Consumer B: partition 1
Consumer C: partition 2
Consumer D: partition 3
~~~

Mỗi consumer có thể tập trung vào một partition. Nếu group có sáu consumer, vẫn chỉ có bốn consumer được gán partition:

~~~text
Consumer A: partition 0
Consumer B: partition 1
Consumer C: partition 2
Consumer D: partition 3
Consumer E: không có partition
Consumer F: không có partition
~~~

Consumer E và F vẫn có thể là thành viên group và duy trì kết nối với Kafka, nhưng không nhận record từ topic orders trong assignment hiện tại. Chúng không làm tăng khả năng xử lý song song của group.

## 2. Công thức xác định số consumer hoạt động

Với một topic mà tất cả consumer trong group đều subscribe:

- \(P\): tổng số partition của topic.
- \(C\): số consumer member trong group.
- \(A\): số consumer được gán ít nhất một partition.

Khi assignment đã ổn định:

\[
A \leq \min(P,C)
\]

Trong trường hợp tất cả consumer cùng subscribe topic và assignor phân phối partition bình thường, số consumer hoạt động thường đạt \(\min(P,C)\). Consumer dư khi \(C>P\) sẽ không có partition.

Số partition trung bình trên mỗi consumer đang hoạt động khi \(C \leq P\) là:

\[
\text{partition trung bình/consumer} \approx \frac{P}{C}
\]

Phân bổ thực tế là số nguyên và có thể không đều tuyệt đối. Với một topic có 10 partition và 3 consumer, một cách phân bổ cân bằng có thể là 4, 3 và 3 partition.

### Ví dụ theo các tỷ lệ khác nhau

| Partition \(P\) | Consumer \(C\) | Consumer hoạt động tối đa | Consumer không có partition | Ý nghĩa |
|---:|---:|---:|---:|---|
| 4 | 1 | 1 | 0 | Một consumer xử lý cả bốn partition |
| 4 | 2 | 2 | 0 | Mỗi consumer thường nhận hai partition |
| 4 | 4 | 4 | 0 | Mỗi consumer có thể nhận một partition |
| 4 | 6 | 4 | 2 | Hai consumer dư không tăng throughput |
| 8 | 4 | 4 | 0 | Mỗi consumer trung bình nhận hai partition |
| 8 | 8 | 8 | 0 | Có thể xử lý song song trên cả tám partition |
| 8 | 12 | 8 | 4 | Bốn consumer dư không được gán partition |

Bảng giả định các consumer cùng subscribe một topic và group đã hoàn tất assignment. Nếu consumer subscribe các tập topic khác nhau, số consumer hữu ích còn phụ thuộc tập partition mà từng member có thể nhận.

## 3. Consumer nhận nhiều partition khác gì một consumer nhận một partition?

Khi một consumer được gán nhiều partition, một vòng poll() có thể trả về record từ nhiều partition. Consumer duy trì tiến độ riêng cho từng partition và xử lý chúng trong cùng poll loop.

Ví dụ một consumer nhận partition 0, 1 và 2:

~~~text
Consumer A
  poll()
    ├── partition 0: offset 10, 11
    ├── partition 1: offset 25
    └── partition 2: offset 80, 81, 82
~~~

Consumer có thể lần lượt xử lý các record này. Kafka giữ thứ tự offset trong từng partition, nhưng không tạo thứ tự tổng thể giữa partition 0, 1 và 2.

Nếu một consumer xử lý chậm một record của partition 0, các partition khác vẫn có thể có record trong cùng batch. Tuy nhiên, nếu ứng dụng xử lý tuần tự trong một thread, thời gian xử lý lâu có thể làm chậm việc xử lý toàn bộ poll loop.

Một consumer nhận một partition có thể dễ dự đoán tải và thứ tự hơn, nhưng không phải lúc nào cũng cần cấu hình đúng một partition cho mỗi consumer. Nhiều consumer có thể cùng xử lý nhiều partition tùy số lượng partition, chi phí tài nguyên và throughput thực tế.

### Một partition không đồng nghĩa chỉ có một record mỗi lần poll

Consumer có thể nhận nhiều record từ một partition trong một poll, tùy lượng dữ liệu sẵn có và các giới hạn như max.poll.records, fetch.max.bytes và max.partition.fetch.bytes. Giới hạn số consumer không phải giới hạn số record được đọc trong một lần poll.

## 4. Consumer group là phạm vi chia sẻ partition

Cần phân biệt consumer trong cùng group và consumer thuộc các group khác nhau.

### 4.1. Cùng group: chia nhau partition

Hai consumer có cùng group.id tham gia cùng một consumer group. Các partition được phân phối giữa các member; một partition không đồng thời được gán cho hai member trong cùng group.

~~~text
Topic orders: P0, P1, P2, P3

Group billing:
  Consumer B1 -> P0, P1
  Consumer B2 -> P2, P3
~~~

Mục tiêu là chia tải xử lý một luồng dữ liệu giữa các consumer trong cùng ứng dụng logic.

### 4.2. Khác group: mỗi group đọc độc lập

Nếu một group khác cũng subscribe topic orders, group đó có assignment riêng:

~~~text
Topic orders: P0, P1, P2, P3

Group billing:
  Consumer B1 -> P0, P1
  Consumer B2 -> P2, P3

Group analytics:
  Consumer A1 -> P0, P1
  Consumer A2 -> P2, P3
~~~

Cả billing và analytics đều có thể đọc toàn bộ dữ liệu của topic theo tiến độ riêng. Consumer group khác không làm giảm số partition có thể cấp cho group billing.

Vì vậy, không cộng số consumer của các group khác nhau để tính giới hạn song song của một group. Công thức \(\min(P,C)\) được tính riêng cho từng group.

## 5. Nếu consumer subscribe nhiều topic thì tính thế nào?

Một consumer group có thể subscribe nhiều topic. Khi tất cả member subscribe cùng tập topic, tổng số partition có thể được phân phối là tổng partition của các topic đó.

Giả sử:

- orders có 6 partition.
- payments có 4 partition.
- Group billing subscribe cả hai topic.
- Group có 5 consumer.

Tổng cộng có 10 partition. Về giới hạn số member nhận ít nhất một partition:

\[
A \leq \min(5, 6+4) = 5
\]

Cả năm consumer đều có thể nhận partition. Mỗi consumer có thể nhận partition từ một hoặc cả hai topic, tùy assignor.

Tuy nhiên, nếu consumer subscribe bằng pattern hoặc mỗi member có subscription khác nhau, không thể chỉ lấy tổng partition rồi mặc định mọi consumer đều nhận được partition. Assignment còn bị giới hạn bởi subscription và chiến lược phân bổ.

Một điểm nữa: khi một consumer group subscribe nhiều topic, số partition lớn ở một topic không nhất thiết bù được partition không tương thích subscription của topic khác. Cần kiểm tra assignment thực tế theo từng member.

## 6. Tăng consumer có luôn làm throughput tăng không?

Không. Tăng consumer chỉ có thể tăng throughput khi:

- Group có partition chưa được khai thác.
- Các consumer hiện tại đang có đủ CPU, network hoặc khả năng xử lý để chia tải.
- Downstream như database hoặc HTTP service có thể chịu thêm request đồng thời.
- Partition có lưu lượng đủ để việc phân chia tạo ra lợi ích.
- Assignment phân bổ tải tương đối hợp lý.

Ví dụ, topic có 12 partition và group có 3 consumer. Mỗi consumer nhận trung bình bốn partition. Nếu CPU của consumer gần chạm giới hạn, tăng group lên sáu consumer có thể giảm số partition mỗi member xuống khoảng hai và tăng khả năng xử lý song song.

Nhưng nếu topic chỉ có ba partition và group đã có ba consumer, tăng lên sáu consumer không tăng số partition được xử lý. Ba member mới không nhận partition.

Ngay cả khi \(C<P\), tăng consumer cũng chưa chắc tăng throughput nếu bottleneck nằm ở database, API downstream, lock trong ứng dụng hoặc một partition nóng.

## 7. Giới hạn theo partition và vấn đề hot partition

Công thức \(\min(P,C)\) chỉ cho biết số consumer có thể được gán partition. Nó không bảo đảm tải được chia đều.

Kafka thường chọn partition dựa trên key. Các record có cùng key thường đi về cùng partition để giữ thứ tự theo key. Nếu một key tạo ra phần lớn lưu lượng, partition chứa key đó có thể nóng hơn các partition còn lại.

Ví dụ:

~~~text
Topic orders: 4 partitions

partition 0: 10% lưu lượng
partition 1: 15% lưu lượng
partition 2: 70% lưu lượng  <- hot partition
partition 3:  5% lưu lượng
~~~

Dù có bốn consumer và mỗi consumer nhận một partition, consumer nhận partition 2 vẫn có thể quá tải. Ba consumer còn lại có thể nhàn rỗi.

Thêm consumer không chia nhỏ một partition thành nhiều assignment trong cùng group. Để giải quyết hot partition, cần xem xét:

- Key có phân bố đều không?
- Một khách hàng hoặc tài khoản có tạo ra lượng sự kiện quá lớn không?
- Có thể chia nhỏ logical key hoặc dùng nhiều shard không?
- Có yêu cầu giữ thứ tự tuyệt đối theo key không?
- Consumer có thể tối ưu xử lý theo batch hoặc giảm chi phí I/O không?

Nếu chia một key thành nhiều shard, cần cân nhắc vì các sự kiện của cùng thực thể có thể không còn nằm trong một partition và thứ tự theo thực thể sẽ cần cơ chế bổ sung.

## 8. Partition count là giới hạn song song, nhưng không phải mục tiêu càng lớn càng tốt

Tăng số partition có thể tạo thêm cơ hội cho consumer group mở rộng. Tuy nhiên, mỗi partition làm tăng chi phí quản lý trên broker và client:

- File log segment, index và metadata.
- Replica cần lưu trữ và đồng bộ.
- Partition assignment và rebalance.
- File descriptor, memory và cache.
- Công việc phục hồi sau broker restart hoặc failure.
- Chi phí quản lý offset và metrics.

Số partition nên được chọn theo throughput mục tiêu, số consumer dự kiến, dung lượng broker, replication factor, kích thước record và yêu cầu ordering.

Nếu cần tăng số consumer nhưng topic đã có đủ partition, cần đánh giá việc tăng partition trước. Thay đổi partition count có thể ảnh hưởng key-to-partition mapping, thứ tự theo key và compacted topic. Các record cũ không tự di chuyển sang partition mới. Không nên tăng partition chỉ để làm cho số consumer bằng số partition mà chưa kiểm tra các ràng buộc dữ liệu.

### Tăng partition không tự tăng số consumer

Nếu topic có bốn partition và group có hai consumer, tăng topic lên tám partition sẽ tạo thêm partition cho group phân phối. Nhưng nếu vẫn chỉ có hai consumer, tối đa vẫn có hai member hoạt động. Mỗi consumer sẽ có thể nhận thêm partition.

Muốn khai thác mức song song mới, ứng dụng cần tăng số consumer member phù hợp, đồng thời bảo đảm tài nguyên downstream đáp ứng được tải.

## 9. Rebalance khi thêm hoặc bớt consumer

Khi một consumer tham gia hoặc rời group, group có thể cần phân phối lại partition. Quá trình này gọi là rebalance.

Ví dụ group đang có hai consumer trên topic bốn partition:

~~~text
Trước khi scale:
  Consumer A -> P0, P1
  Consumer B -> P2, P3

Thêm Consumer C:
  Sau rebalance:
  Consumer A -> P0, P1
  Consumer B -> P2
  Consumer C -> P3
~~~

Assignment cụ thể phụ thuộc partition assignor và trạng thái group. Trong thời gian rebalance, việc xử lý có thể bị tạm dừng hoặc thay đổi tùy giao thức và assignor. Với cooperative assignor, partition có thể được thu hồi và chuyển giao theo từng phần thay vì thu hồi toàn bộ trong một lần.

Nếu liên tục thêm/bớt instance, group có thể rebalance nhiều lần, gây ảnh hưởng đến throughput và latency. Vì vậy, cần tránh autoscaling dao động quá nhanh quanh một ngưỡng.

### 9.1. Consumer chết và failover

Giả sử group có bốn partition và bốn consumer, mỗi consumer nhận một partition. Nếu một consumer chết, sau khi group phát hiện member mất và rebalance, partition của member đó có thể được gán cho consumer còn lại.

~~~text
Trước sự cố:
  C1 -> P0
  C2 -> P1
  C3 -> P2
  C4 -> P3

C4 dừng:
  Sau rebalance:
  C1 -> P0, P3
  C2 -> P1
  C3 -> P2
~~~

Ba consumer còn lại tiếp tục xử lý cả bốn partition. Mỗi consumer có thể nhận nhiều partition cho đến khi member mới gia nhập.

Thời gian phát hiện member chết phụ thuộc heartbeat, session timeout, poll behavior và group protocol. Không nên giả định partition được chuyển ngay tức thì khi process vừa dừng.

### 9.2. Static membership

Kafka hỗ trợ static membership qua group.instance.id. Static membership giúp giảm một số rebalance không cần thiết khi instance tạm thời khởi động lại với cùng định danh trong giới hạn timeout. Mỗi member đồng thời trong group phải có group.instance.id duy nhất.

Static membership không tạo thêm partition và không làm tăng giới hạn song song. Nó chỉ ảnh hưởng cách group nhận diện member và xử lý việc member rời/vào.

## 10. Cấu hình và quan sát số consumer trong Java

Một KafkaConsumer là một đối tượng không thread-safe. Thông thường, mỗi consumer instance có một poll loop riêng và được quản lý bởi một thread. Không nên dùng một KafkaConsumer để nhiều thread cùng gọi poll, commit hoặc thay đổi assignment.

Ví dụ cấu hình consumer:

~~~java
Properties properties = new Properties();
properties.put("bootstrap.servers", "localhost:9092");
properties.put("group.id", "billing");
properties.put(
    "key.deserializer",
    StringDeserializer.class.getName()
);
properties.put(
    "value.deserializer",
    StringDeserializer.class.getName()
);
properties.put("enable.auto.commit", false);
properties.put("max.poll.records", 200);

KafkaConsumer<String, String> consumer =
    new KafkaConsumer<>(properties);

consumer.subscribe(List.of("orders"));
~~~

Nếu cần nhiều consumer song song trong cùng group, tạo nhiều KafkaConsumer instance với cùng group.id, mỗi instance có poll loop và lifecycle riêng. Không chia sẻ một KafkaConsumer giữa nhiều thread.

Ví dụ đơn giản về số member:

~~~java
int partitionCount = 12;
int consumerCount = 5;

int maxActiveConsumers =
    Math.min(partitionCount, consumerCount);

int idleConsumers =
    Math.max(0, consumerCount - partitionCount);

System.out.println("Active upper bound: " + maxActiveConsumers);
System.out.println("Consumers without partition: " + idleConsumers);
~~~

Đây là phép tính giới hạn cho một topic và một tập consumer cùng subscribe topic đó; nó không thay thế việc kiểm tra assignment thật từ group coordinator.

## 11. Cấu hình concurrency trong Spring Kafka

Spring Kafka cho phép tăng số consumer thread của listener container bằng concurrency.

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, String>
        kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, String> factory =
        new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(4);

    return factory;
}
~~~

Với listener container concurrency bằng 4, Spring Kafka tạo các consumer instance riêng để tham gia group. Nếu topic chỉ có hai partition, tối đa hai consumer trong số đó có thể nhận partition; các consumer còn lại không có assignment cho topic đó.

Concurrency nên được cấu hình dựa trên số partition và năng lực xử lý. Đặt concurrency cao hơn partition count không làm listener xử lý song song hơn trên topic đó.

Có thể cấu hình riêng theo listener bằng thuộc tính concurrency của @KafkaListener trong các phiên bản Spring Kafka hỗ trợ:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing",
    concurrency = "4"
)
public void consume(String event) {
    process(event);
}
~~~

Cần kiểm tra phiên bản Spring Kafka và cấu hình container factory đang dùng. Nếu listener subscribe nhiều topic, số partition có thể nhận được khác với trường hợp chỉ một topic.

## 12. Phân biệt consumer concurrency với xử lý song song bên trong ứng dụng

Có hai cách mở rộng thường bị nhầm:

1. Tăng số KafkaConsumer instance trong cùng group để nhận thêm partition.
2. Một consumer nhận nhiều partition rồi chuyển record sang worker pool xử lý song song.

Cách thứ nhất chịu giới hạn trực tiếp bởi số partition được gán. Cách thứ hai có thể tạo nhiều tác vụ xử lý đồng thời bên trong ứng dụng, nhưng consumer vẫn chỉ có một poll loop và phải quản lý offset cẩn thận.

Nếu đưa record sang worker pool:

- Không commit offset của partition vượt qua record chưa xử lý xong.
- Theo dõi thứ tự hoàn thành theo từng partition.
- Bảo đảm xử lý idempotent vì record có thể được giao lại.
- Giữ poll loop hoạt động để tránh vượt max.poll.interval.ms.
- Dùng pause/resume hoặc giới hạn hàng đợi để tạo backpressure khi worker pool đầy.

Việc xử lý song song trong một partition có thể làm mất thứ tự hoàn thành nghiệp vụ dù Kafka vẫn trả record theo thứ tự offset. Nếu thứ tự theo key quan trọng, cần tuần tự hóa công việc theo partition hoặc key và chỉ commit khi các record trước đó đã hoàn tất.

## 13. Chọn số consumer cho một topic

Không có tỷ lệ consumer/partition duy nhất phù hợp mọi tải. Có thể bắt đầu bằng các bước:

1. Xác định partition count và lưu lượng trung bình/cao điểm của từng partition.
2. Đo thời gian xử lý một record và tài nguyên tiêu thụ của consumer.
3. Ước lượng throughput cần thiết cho mỗi consumer.
4. Bắt đầu với số consumer không vượt số partition đang hoạt động.
5. Theo dõi consumer lag, processing latency, CPU, memory và downstream latency.
6. Tăng consumer nếu partition chưa được khai thác và consumer hiện tại thực sự là nút thắt.
7. Nếu cần thêm mức song song vượt số partition, đánh giá tăng partition và ảnh hưởng đến key mapping, ordering, compaction.
8. Kiểm tra rebalance và khả năng phục hồi khi một consumer dừng.

### Ví dụ sizing

Giả sử topic orders có 12 partition. Benchmark cho thấy một consumer xử lý ổn định khoảng 1.500 record/giây với workload hiện tại. Tổng tải cao điểm là 6.000 record/giây.

Ước lượng sơ bộ:

\[
C_{\text{cần}} = \left\lceil \frac{6000}{1500} \right\rceil = 4
\]

Bốn consumer có thể là điểm bắt đầu vì topic có 12 partition và group có thể phân bổ khoảng ba partition cho mỗi consumer. Sau đó cần đo lại lag và latency. Nếu một partition nóng hoặc database downstream chỉ xử lý được 3.000 record/giây, thêm consumer có thể không giải quyết được bottleneck.

Phép tính này chỉ là sizing ban đầu. Throughput mỗi consumer phụ thuộc kích thước record, batch, logic xử lý, network, broker và downstream.

## 14. Checklist trước khi tăng consumer

| Câu hỏi | Cách đánh giá |
|---|---|
| Topic có bao nhiêu partition? | Kiểm tra metadata và partition assignment |
| Group hiện có bao nhiêu member? | Kiểm tra consumer group state |
| Có consumer nào không được gán partition? | Xem assignment và member count |
| Partition có tải đều không? | So sánh lag và throughput theo partition |
| Consumer hiện tại có phải bottleneck? | Đo CPU, processing latency và downstream |
| Database/API downstream chịu được concurrency mới không? | Benchmark và theo dõi connection pool, latency |
| Rebalance có thường xuyên không? | Kiểm tra group logs và rebalance metrics |
| Có xử lý bất đồng bộ bên trong consumer không? | Kiểm tra thứ tự hoàn thành và offset commit |
| Có cần tăng partition không? | Đánh giá key mapping, ordering, compaction và broker capacity |
| Consumer dư có mục đích failover không? | Cân nhắc chi phí tài nguyên và thời gian failover |

## 15. Những nhầm lẫn thường gặp

- **“Càng nhiều consumer thì throughput càng cao.”** Trong cùng group, số consumer nhận partition bị giới hạn bởi số partition.
- **“Một consumer chỉ xử lý được một partition.”** Consumer có thể được gán nhiều partition và poll record từ tất cả partition đó.
- **“Consumer dư sẽ tự chia partition thành nhiều luồng.”** Một partition chỉ được gán cho tối đa một member trong cùng group tại một thời điểm.
- **“Consumer ở group khác làm giảm partition của group hiện tại.”** Mỗi group có assignment và offset độc lập.
- **“Bốn partition và bốn consumer luôn chia tải đều.”** Partition có thể có lưu lượng khác nhau; hot partition vẫn là nút thắt.
- **“Tăng concurrency trong Spring luôn tăng throughput.”** Nếu concurrency vượt partition count, một số consumer không có assignment.
- **“Một KafkaConsumer có thể được nhiều thread dùng chung.”** KafkaConsumer không thread-safe; mỗi consumer instance cần poll loop được quản lý rõ ràng.
- **“Tăng partition không có tác động khác.”** Key mapping, ordering, compaction và chi phí broker có thể thay đổi.
- **“Có nhiều consumer là có nhiều xử lý song song an toàn.”** Worker pool bên trong ứng dụng cần quản lý thứ tự và offset commit riêng.

## 16. Kết luận

Số partition đặt giới hạn trên cho số consumer có thể nhận dữ liệu song song trong cùng một consumer group. Với một topic, số consumer hoạt động tối đa không vượt quá \(\min(P,C)\). Khi consumer ít hơn partition, mỗi consumer nhận nhiều partition; khi consumer nhiều hơn partition, phần dư không được gán partition và không trực tiếp tăng throughput.

Chọn số consumer cần dựa trên partition count, lưu lượng từng partition, tốc độ xử lý và năng lực hệ thống downstream. Hãy theo dõi assignment và lag theo từng partition, kiểm tra hot partition và rebalance trước khi tăng concurrency. Nếu cần nhiều mức song song hơn số partition, hãy đánh giá việc mở rộng topic cùng ảnh hưởng đến key mapping, ordering và storage thay vì chỉ tăng số instance consumer.

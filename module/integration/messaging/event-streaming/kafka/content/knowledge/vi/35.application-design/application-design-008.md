# Giới hạn fan-out, backpressure và ngân sách độ trễ

Một ứng dụng Kafka có thể hoạt động tốt khi tải thấp nhưng bắt đầu tăng latency, đầy bộ nhớ hoặc tạo consumer lag khi một sự kiện được chuyển tới quá nhiều nhánh xử lý. Vấn đề thường không nằm ở một broker riêng lẻ mà ở cách ứng dụng khuếch đại lưu lượng, giữ dữ liệu chờ trong queue và phản ứng khi downstream chậm hơn upstream.

Thiết kế tốt cần trả lời ba câu hỏi: một event được phân phối tới bao nhiêu nơi, hệ thống làm gì khi nơi nhận không theo kịp, và mỗi công đoạn được phép tiêu tốn bao nhiêu thời gian trong SLA đầu cuối. Fan-out, backpressure và latency budget phải được thiết kế cùng nhau vì tăng số nhánh thường làm tăng tải, queueing và tail latency.

## 1. Mục tiêu bài học

Sau bài học, người học có thể:

- Phân biệt fan-out giữa consumer groups với fan-out do ứng dụng publish nhiều topic hoặc gọi nhiều downstream.
- Ước lượng lưu lượng đọc, ghi, network và concurrency khi số nhánh tăng.
- Giải thích vì sao nhánh chậm có thể kéo dài latency của toàn bộ request.
- Dùng Little's Law và tốc độ drain để ước lượng queue depth, thời gian chờ và thời gian phục hồi sau burst.
- Thiết kế backpressure bằng admission control, bounded queue, producer buffer, consumer pause/resume và downstream concurrency limit.
- Tránh làm mất ordering hoặc commit offset vượt quá công việc đã hoàn thành khi xử lý bất đồng bộ.
- Phân bổ latency budget cho producer, Kafka, consumer, downstream và acknowledgement.
- Chọn timeout, retry, batch size và concurrency theo SLA thay vì tăng mọi giới hạn cùng lúc.
- Theo dõi fan-out amplification, queue saturation, consumer lag, tail latency và khả năng drain backlog.

## 2. Fan-out trong ứng dụng Kafka

Fan-out là việc một event hoặc một kết quả xử lý được chuyển tới nhiều người nhận. Kafka có một số cách tạo fan-out, mỗi cách có chi phí và ngữ nghĩa riêng.

### 2.1. Một topic, nhiều consumer groups

Ví dụ topic `orders` được đọc bởi ba nhóm độc lập:

- `order-projection`: cập nhật read model.
- `fraud-detection`: đánh giá rủi ro.
- `notification`: gửi thông báo.

Mỗi consumer group có offset và tiến độ đọc riêng. Các nhóm không chia sẻ một lần đọc; mỗi nhóm nhận toàn bộ các partition mà nó subscribe.

~~~mermaid
flowchart LR
    P["Order service"] --> T[("orders topic")]
    T --> G1["order-projection"]
    T --> G2["fraud-detection"]
    T --> G3["notification"]
    G1 --> R1["Read model"]
    G2 --> R2["Risk engine"]
    G3 --> R3["Email / push"]
~~~

Nếu có `G` consumer groups đều đọc toàn bộ topic, một record được broker phục vụ cho mỗi group. Số bản log lưu trong Kafka không tự tăng theo số group, nhưng network egress, fetch request, broker CPU và downstream work có thể tăng theo số group.

Ước lượng đơn giản:

~~~text
Client fetch bytes/s ~= topic bytes/s * number_of_full_read_groups
~~~

Đây là tổng lưu lượng đọc gần đúng khi mọi group đọc toàn bộ dữ liệu với tốc độ tương đương. Tải thực tế phụ thuộc tốc độ đọc, fetch batching, cache, replica locality, compression và số partition.

### 2.2. Một consumer group có nhiều consumer instances

Các consumer trong cùng group chia nhau partition assignment. Với một topic có `P` partition và `C` consumer instances trong một group:

~~~text
Active consumers <= min(P, C)
~~~

Một partition thông thường chỉ được giao cho một member đang hoạt động trong cùng group tại một thời điểm. Nếu có 24 partition và 40 consumer instances, tối đa 24 instance có thể nhận partition của topic đó; các instance còn lại không tăng parallelism cho topic.

Tăng số instance không giống tăng số consumer groups:

- Thêm member trong cùng group chủ yếu tăng khả năng xử lý song song đến giới hạn partition.
- Thêm group tạo thêm một luồng đọc độc lập toàn bộ topic và tăng fetch load.

### 2.3. Fan-out bằng cách publish nhiều topic

Một service có thể nhận event rồi publish sang nhiều topic:

~~~text
orders
  -> order-created
  -> billing-commands
  -> inventory-commands
  -> notification-commands
~~~

Cách này tạo thêm write traffic và bản ghi trong các topic đích. Nếu mỗi nhánh cần retention riêng, storage và replication capacity cũng tăng theo.

Nên dùng khi các nhánh có hợp đồng dữ liệu, quyền truy cập, retention hoặc vòng đời độc lập. Nếu chỉ cần nhiều hệ thống đọc cùng một event, nhiều consumer groups trên topic gốc có thể đơn giản hơn.

### 2.4. Fan-out đồng bộ trong request path

Một API có thể gọi đồng thời nhiều dịch vụ:

~~~text
HTTP request
  -> Kafka publish
  -> inventory API
  -> payment API
  -> notification API
  -> chờ tất cả kết quả
~~~

Nếu API chờ tất cả nhánh, thời gian hoàn tất phụ thuộc nhánh chậm nhất. Nếu một nhánh chỉ mang tính best-effort, chờ nó trong request path sẽ làm tăng tail latency mà không tăng giá trị cho phản hồi người dùng.

Hãy phân loại nhánh:

- **Bắt buộc:** request chỉ thành công khi nhánh hoàn tất hoặc đã được ghi nhận bền vững.
- **Có thể trì hoãn:** chấp nhận xử lý bất đồng bộ và theo dõi trạng thái sau.
- **Best-effort:** có thể bỏ qua khi quá tải, nhưng phải ghi metric hoặc event phù hợp.
- **Có thể thử lại:** cần retry bounded, idempotency và chính sách dead-letter.

Không để mọi nhánh có cùng mức ưu tiên và cùng deadline nếu yêu cầu nghiệp vụ khác nhau.

## 3. Định lượng fan-out amplification

### 3.1. Tính lưu lượng theo số nhánh

Giả sử một topic nhận:

- 5.000 event/s.
- Payload trung bình 2 KB.
- 4 consumer groups đọc toàn bộ topic.

Tốc độ dữ liệu logic đầu vào:

~~~text
5.000 * 2 KB = 10 MB/s
~~~

Tổng dữ liệu broker phục vụ cho các group, nếu mỗi group đọc đủ tốc độ:

~~~text
10 MB/s * 4 = 40 MB/s
~~~

40 MB/s là ước lượng client fetch traffic, không phải dung lượng log lưu trên disk. Replication traffic và client fetch traffic là hai thành phần riêng.

Nếu ứng dụng publish thêm ba bản copy vào ba topic đích, write rate logic cũng tăng. Nếu các topic đích có RF=3, lượng replica bytes phải tính theo từng topic và replication factor của nó.

### 3.2. Fan-out theo tỷ lệ

Không phải nhánh nào cũng cần mọi event. Nếu nhánh `i` chỉ nhận tỷ lệ `f_i` của traffic:

~~~text
Output_rate_i = Input_rate * f_i

Total_output_rate = sum(Output_rate_i)
~~~

Ví dụ:

| Nhánh | Tỷ lệ event | Tốc độ với 5.000 event/s |
|---|---:|---:|
| Projection | 100% | 5.000/s |
| Fraud | 30% | 1.500/s |
| Notification | 70% | 3.500/s |
| Analytics | 100% | 5.000/s |

Tổng số lượt xử lý của các nhánh là 15.000 event/s. Đây là tải công việc tổng hợp, dù topic đầu vào chỉ có 5.000 event/s.

### 3.3. Retry làm amplification tăng thêm

Nếu một nhánh xử lý thất bại và retry, số lần gọi downstream lớn hơn số event đầu vào.

Với xác suất một lần thử thất bại độc lập là `p` và tối đa `A` lần thử tổng cộng (tính cả lần đầu), số lần thử kỳ vọng có thể ước lượng:

~~~text
E[attempts] = 1 + p + p^2 + ... + p^(A-1)
            = (1 - p^A) / (1 - p), khi p != 1
~~~

Đây chỉ là mô hình lý tưởng. Trong sự cố thực tế, lỗi thường tương quan: downstream đã quá tải thì nhiều request cùng thất bại, làm retry tạo thêm tải đúng lúc hệ thống yếu nhất.

Vì vậy:

- Giới hạn số lần retry.
- Dùng exponential backoff và jitter.
- Đặt deadline tổng cho toàn bộ retry.
- Dùng circuit breaker hoặc admission control cho downstream.
- Chuyển lỗi kéo dài sang retry topic/DLQ theo chính sách.
- Bảo đảm thao tác có idempotency key nếu có thể được thực hiện lại.

### 3.4. Tail latency tăng theo số nhánh

Khi request phải chờ tất cả nhánh song song, latency của request là giá trị lớn nhất trong các nhánh:

~~~text
T_request = max(T_1, T_2, ..., T_N)
~~~

Nếu mỗi nhánh có xác suất 99% hoàn thành trong 100 ms và giả sử độ trễ các nhánh độc lập:

~~~text
P(all branches <= 100 ms) = 0,99^N
~~~

Với 20 nhánh:

~~~text
0,99^20 ~= 81,8%
~~~

Nghĩa là mỗi nhánh riêng lẻ có p99 dưới 100 ms, nhưng chỉ khoảng 81,8% request có tất cả 20 nhánh cùng hoàn thành dưới 100 ms theo giả định độc lập. Trong thực tế, các nhánh có thể còn tương quan do dùng chung network, broker hoặc database.

Hệ quả thiết kế:

- Không chờ nhánh không bắt buộc trong request path.
- Đặt deadline cho từng nhánh nhỏ hơn deadline tổng.
- Dùng bulkhead để một nhánh không chiếm hết thread/connection của nhánh khác.
- Theo dõi p95/p99 của từng nhánh và latency đầu cuối.
- Giảm fan-out không cần thiết và tránh gọi downstream lặp lại cho cùng dữ liệu.

## 4. Queueing, Little's Law và giới hạn backlog

Backpressure chỉ có tác dụng khi ứng dụng biết queue nào đang tích tụ và có thể giới hạn queue đó.

### 4.1. Little's Law

Trong một hệ thống ổn định:

~~~text
L = lambda * W
~~~

Trong đó:

- `L`: số item trung bình trong hệ thống hoặc queue.
- `lambda`: throughput trung bình, item/s.
- `W`: thời gian trung bình một item ở trong hệ thống, giây.

Ví dụ service xử lý 2.000 event/s và trung bình có 10.000 event đang nằm trong hệ thống:

~~~text
W = L / lambda
  = 10.000 / 2.000
  = 5 giây
~~~

Nếu queue tăng từ 10.000 lên 30.000 event mà throughput không đổi, thời gian chờ trung bình tăng đáng kể. Tăng buffer có thể trì hoãn lúc hệ thống báo lỗi nhưng không làm service xử lý nhanh hơn.

Little's Law áp dụng cho hệ thống ổn định và các đại lượng đo cùng phạm vi. Không lấy consumer lag của một topic rồi chia cho throughput của một service khác nếu hai số không cùng luồng dữ liệu.

### 4.2. Tốc độ queue tăng

Gọi:

- `lambda_in`: tốc độ event đến.
- `mu_out`: tốc độ xử lý hoàn tất.
- `Q0`: backlog ban đầu.

Nếu `lambda_in > mu_out`, backlog tăng gần đúng:

~~~text
Q(t) = Q0 + (lambda_in - mu_out) * t
~~~

Ví dụ producer gửi 4.000 event/s nhưng consumer chỉ xử lý 3.000 event/s:

~~~text
Backlog_growth = 4.000 - 3.000
               = 1.000 event/s
~~~

Sau 10 phút, backlog tăng khoảng 600.000 event nếu tốc độ không đổi.

Một hệ thống dài hạn chỉ ổn định khi năng lực xử lý trung bình lớn hơn tốc độ đầu vào trung bình. Để hấp thụ burst và phục hồi backlog, cần thêm headroom.

### 4.3. Thời gian drain backlog

Khi traffic trở lại mức bình thường và consumer xử lý nhanh hơn traffic mới:

~~~text
Drain_time = Backlog / (mu_out - lambda_normal)
~~~

Ví dụ backlog 600.000 event, consumer xử lý 4.000 event/s và traffic mới là 2.500 event/s:

~~~text
Drain_time = 600.000 / (4.000 - 2.500)
           = 400 giây
           = 6 phút 40 giây
~~~

Nếu `mu_out <= lambda_normal`, backlog không thể giảm. Tăng số consumer chỉ hữu ích nếu bottleneck thực sự nằm ở consumer parallelism và vẫn còn partition, CPU, database hoặc network capacity.

### 4.4. Ước lượng dung lượng queue

Nếu queue giữ `Q` record và kích thước trung bình sau serialization là `S` byte:

~~~text
Queue_bytes ~= Q * S * memory_overhead_factor
~~~

Ví dụ 50.000 record, mỗi record 4 KB và hệ số overhead heap giả định là 1,5:

~~~text
50.000 * 4 KB * 1,5 ~= 300 MB
~~~

Hệ số overhead phải đo theo object model, headers, wrapper và cấu trúc queue. Với Java, một object có thể tiêu tốn nhiều heap hơn kích thước payload. Đừng dùng payload bytes để kết luận heap queue đủ an toàn.

Kafka topic là một durable backlog có retention, nhưng consumer vẫn có thể giữ thêm record trong fetch cache, poll result, executor queue và object graph. Phải tính cả các buffer ở client.

## 5. Backpressure là gì?

Backpressure là cơ chế làm chậm hoặc từ chối đầu vào khi downstream không thể xử lý thêm. Mục tiêu là giữ queue hữu hạn, bảo vệ tài nguyên và duy trì latency có thể dự đoán.

Có ba cách phản ứng chính:

| Cách phản ứng | Hành vi | Khi phù hợp |
|---|---|---|
| Slow down | Giảm tốc độ gửi hoặc poll | Producer có thể chờ, upstream hỗ trợ flow control |
| Buffer bounded | Giữ lượng công việc hữu hạn | Cần hấp thụ burst ngắn |
| Reject/shedding | Từ chối hoặc bỏ công việc theo policy | Hệ thống quá tải và cần bảo vệ request quan trọng |

Một queue không giới hạn không phải backpressure. Nó chỉ chuyển lỗi từ downstream sang heap, GC pause hoặc disk exhaustion.

### 5.1. Backpressure end-to-end

~~~mermaid
flowchart LR
    A["HTTP / upstream"] --> B["Admission control"]
    B --> C["Bounded producer queue"]
    C --> D[("Kafka topic")]
    D --> E["Consumer poll"]
    E --> F["Bounded worker queue"]
    F --> G["Downstream service"]
    G --> H["Database / API"]
    H -. "Queue full / slow response" .-> F
    F -. "Pause / limit poll" .-> E
    C -. "Reject / retry later" .-> B
~~~

Một điểm nghẽn có thể xuất hiện ở bất kỳ lớp nào:

- HTTP request queue.
- Application executor.
- Producer buffer.
- Kafka broker/network.
- Consumer poll cache.
- Worker queue.
- Database connection pool.
- External API rate limit.

Chỉ giới hạn một queue không đủ nếu queue tiếp theo vẫn không giới hạn.

### 5.2. Phân loại công việc trước khi áp dụng shedding

Không phải event nào cũng có thể bỏ:

- Command nghiệp vụ cần xử lý: reject upstream hoặc giữ durable retry.
- Event telemetry không quan trọng: có thể sample/drop theo policy đã thống nhất.
- Notification có thể trì hoãn: ghi vào topic và xử lý sau.
- Audit event: không được âm thầm drop; cần durable acceptance hoặc trả lỗi.
- Duplicate event: có thể deduplicate bằng event ID/idempotency key.

Chính sách overload phải được xác định theo nghiệp vụ. Không dùng chung một cơ chế drop cho mọi topic.

## 6. Backpressure ở producer

Producer Java gửi bất đồng bộ qua `send()`, nhưng lời gọi `send()` vẫn có thể chờ metadata hoặc chờ buffer cấp phát. Khi buffer đầy, producer block tới `max.block.ms` rồi báo lỗi nếu không lấy được tài nguyên.

Các cấu hình liên quan:

| Cấu hình | Vai trò |
|---|---|
| `buffer.memory` | Tổng bộ nhớ producer dùng để buffer record chờ gửi |
| `max.block.ms` | Giới hạn thời gian một số lời gọi như send/partitionsFor có thể block khi chờ metadata hoặc buffer |
| `batch.size` | Kích thước batch mục tiêu cho mỗi partition |
| `linger.ms` | Thời gian chờ gom thêm record vào batch |
| `delivery.timeout.ms` | Giới hạn thời gian tổng để báo thành công/thất bại cho record sau send |
| `request.timeout.ms` | Thời gian chờ response cho một request |
| `max.in.flight.requests.per.connection` | Số request chưa nhận response trên một connection |
| `compression.type` | Codec nén batch |

Kafka 4.4 mặc định `buffer.memory` là 32 MiB, `batch.size` là 16 KiB, `linger.ms` là 5 ms, `max.block.ms` là 60 giây và `delivery.timeout.ms` là 120 giây. Đây là default tham khảo, không phải cấu hình SLA phù hợp cho mọi ứng dụng.

### 6.1. Giới hạn admission trước producer

Không đưa mọi request vào một executor không giới hạn rồi để producer tự block. Hãy giới hạn số send đang chờ và định nghĩa hành vi khi hết slot.

Ví dụ dùng semaphore với Spring Kafka:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;
    private final Semaphore permits = new Semaphore(500);

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        if (!permits.tryAcquire()) {
            return CompletableFuture.failedFuture(
                new RejectedExecutionException("Producer capacity is full"));
        }

        try {
            return kafkaTemplate
                .send("orders", event.orderId(), event)
                .whenComplete((result, error) -> permits.release());
        }
        catch (RuntimeException ex) {
            permits.release();
            throw ex;
        }
    }
}
~~~

Semaphore giới hạn số lần gửi đang chờ hoàn tất callback, không thay thế producer buffer hoặc Kafka quota. Giá trị 500 chỉ là ví dụ; phải sizing theo throughput, thời gian ack, heap và SLA.

Trong HTTP layer, có thể chuyển lỗi capacity thành `429 Too Many Requests` hoặc `503 Service Unavailable` kèm retry guidance phù hợp. Không trả thành công trước khi event được broker acknowledge nếu API cam kết event đã được chấp nhận bền vững.

### 6.2. Không chờ future vô hạn

`KafkaTemplate.send()` trả về `CompletableFuture` trong các phiên bản Spring Kafka hiện đại. Có thể kết hợp timeout ở lớp request:

~~~java
publisher.publish(event)
    .orTimeout(250, TimeUnit.MILLISECONDS)
    .whenComplete((result, error) -> {
        if (error != null) {
            // Ghi metric và trả lỗi theo API contract.
        }
    });
~~~

Timeout ở future phía ứng dụng không tự hủy record đã được gửi hoặc đang được producer xử lý. Nếu caller hết thời gian chờ, callback producer vẫn có thể hoàn thành sau đó. Thiết kế idempotency và trạng thái request để tránh client retry tạo event nghiệp vụ trùng.

### 6.3. Batching không phải backpressure

Tăng `linger.ms` hoặc `batch.size` có thể giảm request overhead và tăng throughput, nhưng cũng có thể tăng thời gian chờ batch và memory trên mỗi partition active.

Producer buffer đầy không được giải quyết bằng cách chỉ tăng `buffer.memory`. Trước hết hãy xác định:

- Broker có đang throttle hoặc chậm ack không?
- Partition nào có batch queue lớn?
- Serialization hoặc partitioner có tốn CPU không?
- Downstream consumer có đang chậm không?
- Số producer instances có tạo quá nhiều active partition buffers không?

### 6.4. Producer ordering và retry

Nếu cần ordering trong partition, giữ idempotence phù hợp và không thay đổi `max.in.flight.requests.per.connection` tùy tiện. Với idempotence bật, Kafka producer kiểm soát retry/order theo các ràng buộc của client. Nếu tắt idempotence và cho phép nhiều request in-flight, retry batch cũ có thể làm thứ tự quan sát bị thay đổi.

## 7. Backpressure ở consumer

Consumer nhận dữ liệu theo fetch và `poll()`. Khi xử lý chậm, cần kiểm soát số record nhận mỗi poll và thời gian giữa các lần poll.

### 7.1. max.poll.records

`max.poll.records` giới hạn số record trả về trong một lần gọi `poll()`. Giá trị mặc định Kafka 4.4 là 500.

Nếu mỗi record mất trung bình 20 ms và consumer xử lý tuần tự 500 record:

~~~text
500 * 20 ms = 10.000 ms = 10 giây
~~~

Đây mới là thời gian xử lý lý tưởng theo trung bình; p95/p99, downstream timeout và GC có thể làm batch lâu hơn. Chọn số record sao cho thời gian xử lý batch có headroom trước `max.poll.interval.ms`.

`max.poll.records` không giới hạn toàn bộ lượng byte consumer fetch từ broker. Consumer có thể cache dữ liệu từ fetch request và trả dần qua các lần poll.

### 7.2. max.poll.interval.ms

`max.poll.interval.ms` giới hạn thời gian giữa các lần gọi `poll()` khi dùng consumer group management. Nếu consumer không poll kịp, nó có thể bị xem là failed và partition được rebalance sang member khác.

Đừng tăng `max.poll.interval.ms` để che một handler bị treo. Trước hết giảm batch size, giới hạn downstream work, hoặc chuyển xử lý sang worker có kiểm soát và giữ poll loop hoạt động.

### 7.3. Pause/resume partition

Khi worker queue gần đầy, có thể pause consumer/partition để ngừng nhận thêm record trong khi vẫn duy trì poll loop. Khi queue xuống dưới ngưỡng thấp hơn, resume để tiếp tục fetch.

Trong Spring Kafka, listener container hỗ trợ `pause()` và `resume()`. Pause có hiệu lực trước poll kế tiếp; container vẫn tiếp tục poll nhưng không lấy thêm record trong lúc paused. Điều này giúp tránh rebalance do ngừng poll hoàn toàn.

Ví dụ điều khiển container:

~~~java
@Component
public class ConsumerFlowController {

    private final KafkaListenerEndpointRegistry registry;

    public ConsumerFlowController(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null) {
            container.pause();
        }
    }

    public void resumeOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null) {
            container.resume();
        }
    }
}
~~~

Listener cần khai báo ID:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "order-projection"
)
public void consume(OrderCreated event) {
    projectionService.apply(event);
}
~~~

Trong thực tế, nối pause/resume với queue depth và hysteresis: pause khi vượt high watermark, chỉ resume khi xuống dưới low watermark. Tránh gọi pause/resume liên tục quanh một ngưỡng duy nhất.

### 7.4. Bounded worker queue

Nếu listener chuyển công việc sang executor, queue phải có giới hạn:

~~~java
@Bean
public ThreadPoolTaskExecutor orderExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("order-worker-");
    executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy());
    return executor;
}
~~~

Khi queue đầy, không được âm thầm bỏ record hoặc commit offset trước khi công việc hoàn thành. Cần một trong các cách:

- Pause partition trước khi queue cạn slot.
- Xử lý đồng bộ trong listener với batch nhỏ.
- Đưa record vào một durable handoff topic và chỉ commit sau khi handoff thành công.
- Dùng retry/DLQ theo chính sách rõ ràng.

### 7.5. Commit offset và xử lý bất đồng bộ

Nếu xử lý song song, record offset 102 có thể hoàn tất trước offset 101. Không được commit offset 103 chỉ vì record 102 đã xong nếu record 101 còn đang xử lý.

Offset commit cho partition là vị trí tiếp tục đọc. Commit vượt qua record chưa xử lý có thể làm mất xử lý sau restart.

Một thiết kế an toàn cần:

- Tắt auto commit khi ứng dụng tự quản lý hoàn tất.
- Theo dõi offset đã xử lý liên tục theo từng partition.
- Chỉ commit offset cao nhất mà mọi offset trước nó đã hoàn tất.
- Pause partition khi có quá nhiều công việc đang chạy.
- Giữ ordering nếu nghiệp vụ yêu cầu theo key/partition.
- Kiểm tra semantics khi rebalance và khi worker đang chạy dở.

Nếu không cần parallelism bất đồng bộ trong một partition, xử lý tuần tự trong listener thường dễ đảm bảo ordering và commit semantics hơn.

## 8. Backpressure ở downstream

Consumer có thể đọc Kafka nhanh hơn nhưng database hoặc API phía sau không theo kịp. Khi đó tăng consumer concurrency thường làm tình trạng xấu hơn.

Các giới hạn cần có:

- Connection pool database.
- Max concurrent HTTP calls.
- Per-host rate limit.
- Request timeout.
- Bounded retry queue.
- Circuit breaker.
- Bulkhead riêng cho từng downstream.
- Giới hạn payload và batch size.

Ví dụ, nếu database chỉ xử lý bền vững 800 transaction/s, chạy 2.000 consumer tasks đồng thời không làm database nhanh gấp 2,5 lần. Nó thường làm connection wait, lock contention và timeout tăng.

Dùng semaphore hoặc bulkhead để giới hạn concurrency theo năng lực downstream. Nếu downstream quá tải, pause consumer hoặc giữ backlog trong Kafka thay vì chuyển toàn bộ backlog vào heap và connection pool.

### 8.1. Retry và dead-letter

Retry có thể được thực hiện trong listener thread, qua retry topic hoặc scheduler. Mỗi cách có tác động khác nhau đến ordering và latency.

- Retry ngắn, có giới hạn có thể phù hợp với lỗi transient.
- Retry topic tách công việc khỏi partition chính nhưng có thể làm event mới vượt qua event cũ.
- DLQ lưu record không thể xử lý sau số lần thử đã định.
- Backoff nên tăng dần và có jitter để tránh tất cả consumer retry cùng lúc.
- Retry phải nằm trong deadline nghiệp vụ; event hết hạn không nên tiếp tục retry vô hạn.

Không retry lỗi permanent như schema sai hoặc validation fail theo cùng cách với lỗi database tạm thời.

## 9. Xây dựng latency budget đầu cuối

Latency budget là tổng thời gian tối đa được phép tiêu tốn qua các bước để đáp ứng SLA.

### 9.1. Phân rã đường đi

Một luồng event có thể gồm:

~~~mermaid
flowchart LR
    A["API ingress"] --> B["Admission + serialize"]
    B --> C["Producer buffer / batch"]
    C --> D["Broker append + ack"]
    D --> E["Consumer lag / fetch"]
    E --> F["Business processing"]
    F --> G["Downstream API / DB"]
    G --> H["Offset commit / response"]
~~~

Ngân sách tổng:

~~~text
T_end_to_end =
  T_ingress
  + T_admission
  + T_producer
  + T_broker
  + T_queue
  + T_processing
  + T_downstream
  + T_commit
~~~

Các thành phần phải được định nghĩa cùng điểm bắt đầu/kết thúc. Ví dụ, nếu `T_producer` đã bao gồm thời gian buffer, không cộng `T_batch` lần nữa.

### 9.2. Ví dụ latency budget 500 ms

Giả sử API cam kết event được xử lý và cập nhật projection trong 500 ms ở điều kiện tải mục tiêu:

| Công đoạn | Ngân sách ví dụ |
|---|---:|
| API ingress và validation | 25 ms |
| Admission, serialization và producer queue | 35 ms |
| Broker append và acknowledgement | 40 ms |
| Consumer queue/fetch lag | 80 ms |
| Business processing | 90 ms |
| Database/downstream | 170 ms |
| Commit và response hoàn tất | 30 ms |
| Headroom | 30 ms |
| **Tổng** | **500 ms** |

Đây là phân bổ thiết kế, không phải latency mặc định của Kafka. Cần thay bằng số đo p95/p99 của workload và SLA thật.

Không cộng các p99 riêng lẻ rồi khẳng định tổng chính xác là p99 đầu cuối. Percentile của tổng phụ thuộc phân phối và tương quan giữa các stage. Budget per-stage là giới hạn vận hành để điều khiển; phải đo thêm histogram end-to-end bằng correlation ID hoặc trace.

### 9.3. Deadline và timeout

Mỗi downstream call nên có timeout nhỏ hơn thời gian còn lại của request. Nếu deadline tổng là 500 ms và các bước trước đã dùng 250 ms, không nên gửi một request downstream có timeout 2 giây.

Mô hình:

~~~text
Remaining_budget = Deadline - Current_time

Call_timeout = min(Service_timeout, Remaining_budget)
~~~

Timeout phải phân biệt:

- Connect timeout: thời gian thiết lập kết nối.
- Request/response timeout: thời gian chờ phản hồi.
- Producer delivery timeout: thời gian tổng để báo kết quả gửi.
- Consumer processing deadline: thời gian xử lý một event.
- Retry deadline: tổng thời gian còn được phép thử lại.
- API deadline: thời gian caller chờ kết quả.

Không đặt mọi timeout bằng nhau. Timeout của tầng trong thường ngắn hơn deadline của tầng ngoài để còn thời gian xử lý lỗi hoặc trả response.

### 9.4. Kafka producer latency

`linger.ms` thêm thời gian chờ để gom batch khi batch chưa đầy. Trong Kafka 4.4 mặc định là 5 ms. `delivery.timeout.ms` bao gồm thời gian record chờ gửi, chờ acknowledgement và retry; giá trị này phải lớn hơn hoặc bằng `request.timeout.ms + linger.ms`.

Nếu API cần phản hồi trong 200 ms, không nên để producer delivery timeout mặc định 120 giây rồi giữ request thread chờ future trong suốt thời gian đó. Cần quyết định API có trả ngay sau khi Kafka ack hay chấp nhận xử lý bất đồng bộ với trạng thái riêng.

### 9.5. Consumer lag là một phần latency

Consumer lag tính bằng số offset chưa đọc không trực tiếp bằng thời gian trễ. Nếu throughput thay đổi theo thời gian hoặc partition có tốc độ khác nhau, cùng một lag count có thể tương ứng thời gian chờ khác nhau.

Ước lượng đơn giản khi tốc độ xử lý ổn định:

~~~text
Lag_time_estimate ~= Lag_records / Consume_rate_records_per_second
~~~

Nên theo dõi cả lag records và thời gian từ event creation/append đến lúc consumer bắt đầu xử lý. Với nhiều partition, đo theo partition rồi tìm partition chậm nhất.

## 10. Chọn timeout, retry và concurrency

### 10.1. Timeout theo deadline

Ví dụ request có deadline 1 giây:

- Validation và admission: tối đa 50 ms.
- Producer ack: tối đa 150 ms.
- Chờ consumer: tối đa 300 ms.
- Downstream: tối đa 350 ms.
- Commit/response: 50 ms.
- Headroom: 100 ms.

Nếu producer đã dùng hết budget, không tiếp tục gọi downstream như thể còn nguyên một giây. Truyền deadline hoặc remaining timeout qua các tầng.

### 10.2. Retry với backoff và jitter

Ví dụ retry schedule:

~~~text
attempt 1: immediate
attempt 2: 100 ms + jitter
attempt 3: 200 ms + jitter
attempt 4: 400 ms + jitter
then: dead-letter / fail
~~~

Đây là ví dụ, không phải giá trị cố định. Tổng thời gian retry phải nhỏ hơn deadline còn lại hoặc chuyển thành xử lý bất đồng bộ.

Jitter giúp tránh retry storm khi nhiều consumer cùng gặp một outage.

### 10.3. Concurrency theo năng lực thực tế

Ước lượng concurrency cần thiết theo throughput và thời gian xử lý trung bình:

~~~text
Concurrency_required ~= Throughput_target * Service_time
~~~

Ví dụ cần xử lý 1.000 event/s, mỗi event dùng 20 ms CPU/service time:

~~~text
Concurrency_required ~= 1.000 * 0,020 = 20
~~~

Công thức là ước lượng đầu tiên theo Little's Law; còn phải xét CPU cores, I/O wait, partition count, downstream limits và tail latency. Tăng concurrency quá cao có thể làm lock contention, context switching và queueing tăng.

### 10.4. Consumer concurrency không vượt giới hạn partition

Nếu topic có 16 partition, một group có 40 consumer instances thì tối đa 16 instance có partition active cho topic đó. Muốn tăng parallelism hơn nữa phải xem xét partition count, key distribution và khả năng chịu tải broker.

Không tăng partition chỉ để chữa downstream chậm. Nếu bottleneck là database, tăng partition và consumer chỉ tăng số request đổ vào database.

## 11. Tuning producer và consumer theo mục tiêu

### 11.1. Producer: ưu tiên throughput hay latency

| Mục tiêu | Hướng điều chỉnh | Trade-off |
|---|---|---|
| Giảm request overhead | Tăng batch/linger hợp lý | Có thể tăng chờ batch |
| Giảm network bytes | Chọn compression codec | Tăng CPU |
| Giới hạn heap producer | Buffer hữu hạn, admission control | Caller có thể bị block/reject |
| Giới hạn thời gian gửi | Delivery timeout theo SLA | Event có thể báo lỗi sớm hơn |
| Giữ ordering | Idempotence và cấu hình in-flight phù hợp | Có thể giới hạn throughput theo connection |

Ví dụ cấu hình khởi đầu để benchmark:

~~~properties
acks=all
enable.idempotence=true
compression.type=lz4
batch.size=32768
linger.ms=5
buffer.memory=67108864
max.block.ms=500
request.timeout.ms=1000
delivery.timeout.ms=3000
~~~

Các con số là ví dụ cho lab, không phải cấu hình production khuyến nghị chung. Phải kiểm tra yêu cầu durability, broker timeout, replication latency và SLA. `delivery.timeout.ms` phải thỏa điều kiện lớn hơn hoặc bằng `request.timeout.ms + linger.ms`.

### 11.2. Consumer: kiểm soát lượng công việc mỗi poll

Ví dụ cấu hình:

~~~properties
enable.auto.commit=false
max.poll.records=100
max.poll.interval.ms=300000
fetch.max.bytes=52428800
max.partition.fetch.bytes=1048576
~~~

`max.poll.records=100` giảm số record trả về mỗi poll so với default 500, nhưng không tự giới hạn mọi byte đã được fetch/cached. Chọn fetch limits theo record batch size và memory budget.

Nếu xử lý mỗi batch lâu, giảm `max.poll.records` hoặc tối ưu downstream trước khi tăng `max.poll.interval.ms`.

### 11.3. Spring Kafka listener concurrency

Ví dụ:

~~~java
@KafkaListener(
    id = "orderProjection",
    topics = "orders",
    groupId = "order-projection",
    concurrency = "8"
)
public void onOrder(OrderCreated event) {
    projectionService.apply(event);
}
~~~

`concurrency` tạo consumer instances trong listener container. Chọn giá trị phù hợp với partition count và năng lực downstream. Nếu topic có 6 partition, concurrency 8 không tạo thêm 2 partition active cho group.

## 12. Đo lường fan-out và backpressure

Không chỉ theo dõi CPU và memory. Cần metric cho từng queue, từng nhánh và latency đầu cuối.

### 12.1. Producer metrics

Theo dõi:

- `record-send-rate`.
- `record-error-rate`.
- `record-retry-rate`.
- `request-latency-avg/max`.
- `buffer-available-bytes`.
- Buffer pool wait time.
- `record-queue-time-avg`.
- `batch-size-avg`.
- `compression-rate-avg`.

Buffer available bytes giảm liên tục hoặc buffer wait tăng là dấu hiệu producer đang bị broker/network chậm hoặc ứng dụng gửi nhanh hơn tốc độ drain.

### 12.2. Consumer metrics

Theo dõi:

- `records-consumed-rate`.
- `records-lag-max` hoặc lag theo partition.
- `fetch-latency-avg/max`.
- `records-lag` theo thời gian.
- `commit-latency-avg/max`.
- `last-poll-seconds-ago`.
- Rebalance count/rate.
- Pause duration và paused partition count.
- Worker queue depth và rejected task count.

Tên metric cụ thể có thể khác theo client/version và exporter. Kiểm tra JMX metric names của phiên bản đang dùng.

### 12.3. Application/downstream metrics

Theo dõi:

- Queue depth và queue wait time.
- Active worker count và rejected tasks.
- Semaphore permits còn lại.
- HTTP connection pool pending/acquired.
- Database pool active/idle/wait.
- Downstream timeout/error rate.
- Retry attempts và DLQ rate.
- End-to-end latency p50/p95/p99.
- Fan-out branch latency và branch completion rate.

Mỗi event nên có event ID/correlation ID và timestamp đủ để đo thời gian từ ingress đến completion. Tránh dùng timestamp từ các host chưa đồng bộ clock để tính latency quá nhỏ; dùng tracing/histogram monotonic trong từng process và đồng bộ thời gian giữa node.

### 12.4. Phát hiện fan-out amplification

Đo các tỷ lệ:

~~~text
Consumer_work_amplification =
  total_branch_events_processed / source_events_ingested

Retry_amplification =
  total_attempts / unique_events

Fetch_amplification =
  total_consumer_fetch_bytes / source_topic_bytes
~~~

Nếu một source event tạo 6 branch processing và mỗi nhánh có trung bình 1,4 lượt thử trên mỗi event (tính cả lần đầu), số lượt xử lý có thể tiến gần 8,4 lần source event trong một cửa sổ tương ứng. Đo bằng event ID và attempt number để phân biệt duplicate, retry và fan-out hợp lệ.

## 13. Load test và kiểm chứng ngân sách

### 13.1. Xác định workload

Tạo workload đại diện:

- Event/s trung bình và peak.
- Payload size distribution, không chỉ average.
- Số partition.
- Số consumer groups.
- Fan-out ratio từng nhánh.
- Retry rate và downstream error rate.
- Thời gian xử lý p50/p95/p99.
- Số producer/consumer instances.

### 13.2. Tăng tải theo bậc

Chạy các mức 25%, 50%, 75%, 100%, rồi 125% tải dự kiến. Ở mỗi mức, ghi:

- Throughput vào/ra.
- p50/p95/p99 latency.
- Consumer lag.
- Producer buffer wait.
- Worker queue depth.
- CPU, heap, GC.
- Broker request/network/disk metrics.
- Downstream pool saturation.
- Error, retry và DLQ rate.

Dừng tăng tải nếu queue tăng liên tục, p99 vượt budget hoặc tài nguyên downstream đã bão hòa.

### 13.3. Thử burst và recovery

Ví dụ:

1. Chạy ở 2.000 event/s trong 10 phút.
2. Tăng lên 5.000 event/s trong 2 phút.
3. Hạ về 2.000 event/s.
4. Đo backlog peak và thời gian drain.
5. Lặp lại khi một downstream chậm hoặc trả lỗi.
6. Kiểm tra queue không vượt giới hạn và heap không tăng không kiểm soát.

Một hệ thống chỉ được xem là phục hồi tốt khi backlog giảm sau burst, latency trở lại budget và không tạo retry storm.

### 13.4. Kiểm thử nhánh chậm

Cố tình làm một downstream chậm hơn:

- Độ trễ tăng gấp 5.
- Tỷ lệ lỗi 10%.
- Timeout hoặc connection reset.
- Giới hạn connection pool.

Xác minh nhánh đó không làm cạn executor/connection pool của nhánh khác. Nếu request không cần chờ nhánh này, kiểm tra nó vẫn trả kết quả trong SLA.

## 14. Lab: thiết kế fan-out và backpressure cho orders

### Mục tiêu

Xây dựng pipeline order event có ba nhánh đọc độc lập, giới hạn producer admission và pause consumer khi downstream queue gần đầy.

### Bước 1: Tạo topic và consumer groups

Tạo topic `orders` với 12 partition trong cluster lab. Tạo ba ứng dụng/group:

- `order-projection`.
- `fraud-detection`.
- `notification`.

Mỗi group đọc toàn bộ topic. Ghi lại consumer lag và fetch throughput của từng group.

### Bước 2: Tạo tải nguồn

Gửi 1.000 event/s, payload trung bình 2 KB. Ghi lại throughput producer và broker.

### Bước 3: Tăng số nhánh

Thêm hai consumer groups nữa. So sánh broker egress và CPU. Xác nhận số bản log không tăng chỉ vì thêm consumer group, nhưng số lượt fetch tăng.

### Bước 4: Làm chậm một nhánh

Thêm delay 100 ms vào `notification`. Quan sát queue depth, consumer lag và latency của hai nhánh còn lại.

Nếu một request chờ cả ba nhánh, đo thời gian hoàn thành theo nhánh chậm nhất. Nếu nhánh notification không bắt buộc, tách nó thành xử lý bất đồng bộ.

### Bước 5: Giới hạn producer admission

Thêm semaphore hoặc bounded queue vào producer service. Khi hết capacity, trả lỗi có thể retry theo API contract. Theo dõi rejected request và producer buffer wait.

### Bước 6: Giới hạn consumer work

Đặt `max.poll.records` phù hợp với thời gian xử lý. Dùng worker queue hữu hạn và pause/resume listener khi queue vượt high watermark.

### Bước 7: Thử retry và downstream failure

Cho downstream trả lỗi transient. Dùng backoff có jitter và giới hạn attempt. Xác minh retry không làm tổng tải tăng vượt khả năng phục hồi.

### Bước 8: Đo latency budget

Gắn correlation ID và ghi thời gian:

- Event accepted.
- Producer acknowledged.
- Consumer started.
- Processing completed.
- Downstream completed.
- Offset committed.

Tính p50/p95/p99 đầu cuối và so sánh với ngân sách đã chọn.

### Bước 9: Thử burst và drain

Tăng input rate gấp đôi trong hai phút, sau đó hạ về bình thường. Tính backlog peak, drain rate và thời gian trở lại trạng thái ổn định.

### Bước 10: Viết kết luận

Ghi lại:

- Fan-out amplification trước/sau.
- Consumer fetch traffic.
- Producer queue/buffer saturation.
- Consumer lag và worker queue depth.
- Thời gian drain backlog.
- p95/p99 từng nhánh và end-to-end.
- High/low watermark đã chọn.
- Retry và shedding policy.
- Bottleneck còn lại.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Nhầm nhiều consumer instances với nhiều groups | Dự báo sai fetch traffic | Phân biệt parallelism trong group và fan-out giữa groups |
| Chờ mọi nhánh trong request path | Tail latency phụ thuộc nhánh chậm nhất | Chỉ chờ nhánh bắt buộc |
| Dùng queue không giới hạn | Heap tăng, GC pause hoặc OOM | Bounded queue và admission control |
| Chỉ tăng producer buffer | Trì hoãn lỗi nhưng không tăng throughput | Tìm bottleneck và giới hạn đầu vào |
| Tăng consumer concurrency khi DB đã bão hòa | Connection wait và timeout tăng | Giới hạn concurrency theo downstream capacity |
| Chỉ nhìn lag count | Không biết thời gian trễ thực | Đo event age và lag theo partition |
| Pause consumer nhưng ngừng poll hoàn toàn | Consumer có thể rời group/rebalance | Dùng pause/resume container giữ poll loop |
| Commit offset trước khi async work hoàn tất | Mất xử lý sau restart | Commit theo offset đã hoàn tất liên tục |
| Retry ngay và không giới hạn | Retry storm | Exponential backoff, jitter, max attempts |
| Dùng retry topic mà không xét ordering | Event mới có thể vượt event cũ | Xác định ordering contract và key |
| Tăng `max.poll.interval.ms` để che handler treo | Rebalance bị trì hoãn và lỗi khó phát hiện | Giảm batch, bounded work và theo dõi poll interval |
| Cộng p99 từng stage rồi coi là p99 end-to-end | Đánh giá sai SLA | Đo histogram end-to-end và dùng stage budget để kiểm soát |
| Tính fan-out bằng số topic nhưng quên groups | Thiếu ước lượng fetch load | Inventory cả topic outputs và consumer groups |
| Không thử burst/recovery | Hệ thống có thể không drain được backlog | Load test burst và đo drain time |

## 16. Checklist production

- [ ] Inventory topic, partition, consumer group và fan-out branch.
- [ ] Phân loại nhánh bắt buộc, trì hoãn, best-effort và retryable.
- [ ] Tính output event rate và fetch traffic theo từng group.
- [ ] Đánh giá tail latency khi request chờ nhiều nhánh.
- [ ] Xác định SLA và latency budget end-to-end.
- [ ] Đo p50/p95/p99 từng stage và end-to-end.
- [ ] Truyền deadline/remaining timeout giữa các tầng.
- [ ] Giới hạn producer admission và application queue.
- [ ] Kiểm tra producer `buffer.memory`, `max.block.ms` và `delivery.timeout.ms`.
- [ ] Chọn `batch.size`, `linger.ms` và compression theo benchmark.
- [ ] Giữ idempotence/ordering theo yêu cầu nghiệp vụ.
- [ ] Giới hạn consumer `max.poll.records` theo thời gian xử lý batch.
- [ ] Bảo đảm poll loop hoạt động và xử lý pause/resume đúng cách.
- [ ] Dùng bounded worker queue và downstream concurrency limit.
- [ ] Commit offset sau khi xử lý tương ứng hoàn tất.
- [ ] Đặt retry limit, exponential backoff và jitter.
- [ ] Xác định DLQ và idempotency cho thao tác retry.
- [ ] Theo dõi consumer lag, event age, queue depth và drain rate.
- [ ] Theo dõi producer buffer wait và rejected admissions.
- [ ] Theo dõi downstream pool saturation và timeout.
- [ ] Load test ở peak và burst.
- [ ] Kiểm tra backlog drain sau khi downstream phục hồi.
- [ ] Có chính sách shedding rõ ràng theo loại event.
- [ ] Cập nhật capacity model khi fan-out hoặc traffic thay đổi.

## 17. Tài liệu tham khảo

- [Apache Kafka 4.4 – Producer Configs](https://kafka.apache.org/44/configuration/producer-configs/)
- [Apache Kafka 4.4 – Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Apache Kafka 4.4 – KafkaProducer API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html)
- [Apache Kafka 4.4 – KafkaConsumer API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html)
- [Spring Kafka – Pausing and Resuming Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html)

Fan-out quyết định số nhánh cùng xử lý một event; backpressure giữ tốc độ đầu vào trong giới hạn năng lực xử lý; latency budget phân bổ thời gian cho từng công đoạn. Khi ba yếu tố được đo và giới hạn cùng nhau, Kafka có thể hấp thụ burst mà không biến backlog thành heap growth, retry storm hoặc tail latency không kiểm soát.

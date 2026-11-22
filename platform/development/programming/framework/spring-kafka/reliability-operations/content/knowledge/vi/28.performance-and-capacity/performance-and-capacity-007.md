# Executor capacity

Trong Spring Kafka, mỗi listener container cần một consumer task để thực hiện vòng `poll()`, quản lý Kafka consumer và gọi listener. Khi ứng dụng tăng `concurrency`, số consumer tasks và số thread cần chạy cũng tăng. Nếu executor không có đủ năng lực, một số tasks có thể phải chờ trong hàng đợi hoặc bị từ chối. Nếu tạo quá nhiều consumer threads, ứng dụng lại có thể tranh CPU, kết nối database và tài nguyên của các dịch vụ downstream.

**Executor capacity** là khả năng executor cung cấp đủ worker threads cho các tasks mà nó quản lý. Trong chương **Hiệu năng và capacity**, cần tính capacity dựa trên toàn bộ topology: số replicas, số listener endpoints, concurrency của từng endpoint, số partitions trong consumer group, thread pool, CPU và giới hạn dependency.

Điểm quan trọng: **concurrency cấu hình, số consumer thực sự được assign partition, số thread executor và số nghiệp vụ xử lý song song là các đại lượng khác nhau**. Tăng một giá trị không tự động làm throughput tăng tương ứng.

## 1. Executor làm gì trong Spring Kafka?

Với `@KafkaListener`, Spring Kafka tạo listener container để quản lý Kafka consumer. Mỗi consumer chạy trong một task dài hạn. Container dùng một executor để chạy consumer task; trong các phiên bản Spring Kafka phổ biến, executor mặc định là `SimpleAsyncTaskExecutor`. Ứng dụng có thể cung cấp executor riêng qua `ContainerProperties.setListenerTaskExecutor(...)`.

~~~text
KafkaListenerEndpointRegistry
          |
          v
Listener container
          |
          +---- submit consumer task to listenerTaskExecutor
                         |
                         v
                  consumer thread
                         |
                         +---- KafkaConsumer.poll()
                         +---- listener invocation
                         +---- ack / commit handling
                         +---- next poll
~~~

Trong mô hình record listener thông thường, consumer thread thực hiện poll và gọi listener. Vì vậy, thread này không phải worker task ngắn được submit cho mỗi record. Nó là task dài hạn, chiếm một thread trong khi container hoạt động.

Điều này làm capacity planning khác với executor dùng cho tác vụ ngắn như gửi email hoặc xử lý HTTP request. Nếu pool có sáu threads nhưng ứng dụng cần chạy mười consumer tasks lâu dài, sáu tasks có thể chiếm hết pool; những tasks còn lại phải chờ hoặc bị từ chối tùy queue và rejection policy.

## 2. Phân biệt concurrency, consumer, partition và thread

| Khái niệm | Ý nghĩa |
|---|---|
| Listener endpoint | Một phương thức/cấu hình `@KafkaListener` được Spring quản lý |
| Container concurrency | Số consumer child containers mà endpoint tạo |
| Kafka consumer | Một client/member tham gia consumer group |
| Consumer thread | Thread chạy consumer task và listener theo mô hình container thông thường |
| Partition | Đơn vị log có thứ tự trong Kafka topic |
| Executor thread capacity | Số tasks executor có thể chạy đồng thời |
| Business parallelism | Số nghiệp vụ thực sự được xử lý song song |

Ví dụ:

~~~java
@KafkaListener(
        id = "orders-listener",
        groupId = "orders-service",
        topics = "orders.events",
        concurrency = "3")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

Endpoint này yêu cầu ba consumer child containers. Trong listener container thông thường, mỗi consumer task cần một thread. Nếu topic có sáu partitions, ba consumers có thể được assign partitions theo assignment strategy. Nếu topic chỉ có hai partitions, tối đa hai consumers trong group nhận partition của topic đó; consumer còn lại vẫn có thể chạy nhưng không có partition được giao.

**Một consumer không có partition vẫn tiêu thụ thread capacity** nếu container của nó đang chạy. Do đó, tăng concurrency vượt partition count có thể tăng số threads mà không tăng khả năng xử lý song song của topic.

## 3. Tính tổng số consumer tasks trước khi chọn pool size

Capacity cần tính ở cấp **toàn ứng dụng và từng consumer group**, không chỉ nhìn một annotation.

Giả sử mỗi replica có ba listener endpoints:

| Listener | Concurrency mỗi replica |
|---|---:|
| `orders-listener` | 4 |
| `payments-listener` | 2 |
| `audit-listener` | 1 |
| **Tổng** | **7** |

Nếu triển khai bốn replicas, cluster có thể có khoảng 28 consumer instances từ các endpoints này. Nhưng executor nằm **trong từng JVM**, không chia sẻ xuyên Pods. Vì vậy, mỗi replica cần khả năng chạy bảy consumer tasks của chính nó.

Công thức tổng quát cho một process:

\[
T_{\text{required}} = \sum_{i=1}^{N} concurrency_i
\]

Chỉ cộng các endpoints thực sự được start và dùng executor đang xét. Nếu nhiều factories dùng executor riêng, tính riêng từng pool. Nếu một executor dùng chung cho nhiều endpoints, cộng concurrency của tất cả endpoints đó.

Đối với consumer group, tổng số members còn phụ thuộc replicas, listener IDs/group IDs, subscription và những consumers khác cùng tham gia group. Không cộng tất cả consumer trong ứng dụng vào một group nếu chúng thực tế dùng group IDs khác nhau.

## 4. Partitions giới hạn mức song song hữu ích

Trong một consumer group, một partition tại một thời điểm chỉ được assign cho tối đa một consumer member. Với topic có sáu partitions:

~~~text
Topic orders.events: 6 partitions

Concurrency = 3:
  consumer-0 -> p0, p1
  consumer-1 -> p2, p3
  consumer-2 -> p4, p5

Concurrency = 6:
  consumer-0 -> p0
  consumer-1 -> p1
  consumer-2 -> p2
  consumer-3 -> p3
  consumer-4 -> p4
  consumer-5 -> p5

Concurrency = 9:
  consumer-0..consumer-5 -> có thể nhận p0..p5
  consumer-6..consumer-8 -> không có partition của topic này
~~~

Với một topic duy nhất, mức song song consumer hữu ích trong group thường không vượt số partitions. Với nhiều topics được subscribe, cần xét tổng partitions có thể được assign và assignment strategy.

Có thể dùng xấp xỉ:

\[
C_{\text{assigned}} \leq \min(C_{\text{group members}}, P_{\text{subscription}})
\]

Đây là giới hạn theo assignment, không phải dự báo throughput chính xác. Partition skew, key distribution, record processing time và downstream bottlenecks vẫn ảnh hưởng hiệu năng.

**Tăng thread pool mà không tăng partitions hoặc cải thiện workload không đảm bảo throughput tăng.** Ngược lại, tăng partitions cũng không có lợi nếu database hoặc CPU đã là bottleneck.

## 5. ListenerTaskExecutor và executor riêng

Có thể cấu hình executor cho listener containers bằng `ContainerProperties.setListenerTaskExecutor(...)`. Ví dụ dùng `ThreadPoolTaskExecutor` với sáu threads cho một endpoint có concurrency sáu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class KafkaExecutorConfiguration {

    @Bean
    public AsyncTaskExecutor kafkaListenerExecutor() {
        var executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(6);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(0);
        executor.setThreadNamePrefix("kafka-orders-");

        return executor;
    }
}
~~~

Gắn vào factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                AsyncTaskExecutor kafkaListenerExecutor) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(6);
    factory.getContainerProperties()
            .setListenerTaskExecutor(kafkaListenerExecutor);

    return factory;
}
~~~

Trong ví dụ:
- `corePoolSize=6` và `maxPoolSize=6` tạo pool cố định sáu worker threads.
- `queueCapacity=0` yêu cầu handoff trực tiếp thay vì giữ consumer tasks trong một queue lớn.
- `threadNamePrefix` giúp nhận diện consumer threads trong thread dumps và logs.
- Concurrency bằng sáu cần sáu thread capacity trong pool này.

`ThreadPoolTaskExecutor` được Spring quản lý như bean và tự khởi tạo qua lifecycle. Không cần tự gọi `initialize()` trong cấu hình bean thông thường.

### 5.1. Chọn queueCapacity có chủ đích

`ThreadPoolTaskExecutor` thường có queue capacity mặc định rất lớn. Với task ngắn, queue có thể hấp thụ burst. Nhưng consumer tasks là task dài hạn, mỗi task giữ một thread trong suốt vòng đời container.

Nếu pool có sáu threads, queue capacity 1.000 và ứng dụng submit mười consumer tasks, bốn tasks cuối có thể nằm chờ rất lâu. Container có thể đã nhận yêu cầu start trong khi consumer task chưa thực sự bắt đầu polling. Điều này tạo khoảng cách giữa **container được yêu cầu start** và **consumer thực sự chạy**.

Queue lớn không làm tăng số consumers đang poll. Nó chỉ trì hoãn thời điểm các tasks được chạy.

### 5.2. Rejection policy

Nếu pool không còn thread capacity và queue không nhận task, executor có thể từ chối task theo rejection policy. Với consumer container, rejection là lỗi triển khai/cấu hình cần được nhìn thấy rõ; không nên dùng policy âm thầm bỏ task.

Tránh `DiscardPolicy` hoặc `DiscardOldestPolicy` cho consumer tasks dài hạn. Việc bỏ một task có thể khiến listener container không có consumer thread hoạt động như mong muốn.

`CallerRunsPolicy` cũng cần thận trọng: nó có thể khiến thread submit task phải chạy consumer loop dài hạn, làm block luồng lifecycle/startup hoặc thread khác ngoài dự kiến. Nên thiết kế pool đủ capacity và để rejection lộ rõ thay vì che giấu thiếu hụt.

## 6. Một executor dùng chung cho nhiều listener

Một ứng dụng có thể có nhiều container factories và endpoints. Nếu tất cả dùng chung một executor, capacity của pool phải đáp ứng **tổng số consumer tasks đang hoạt động** trên executor đó.

Ví dụ mỗi replica:
- `orders-listener`: concurrency 4.
- `payments-listener`: concurrency 3.
- `audit-listener`: concurrency 2.

Tổng cộng cần chín consumer task threads trong process. Pool sáu threads không đủ dù từng endpoint riêng lẻ có concurrency không vượt sáu.

~~~text
Shared listenerTaskExecutor (6 threads)
       |
       +---- orders: 4 tasks
       +---- payments: 3 tasks
       +---- audit: 2 tasks
                    |
                    v
             Total demand = 9
             Capacity = 6
             At least 3 tasks wait/reject
~~~

Có hai hướng:

1. **Pool dùng chung đủ lớn:** dễ quản lý một capacity budget nhưng các listeners cạnh tranh tài nguyên.
2. **Executor riêng theo workload:** cô lập tài nguyên, ví dụ payment listener có pool riêng để audit listener không chiếm hết thread của payment.

Pool dùng chung tận dụng thread capacity khi một listener stop, nhưng có thể tạo noisy neighbor. Pool riêng tăng khả năng cô lập nhưng có thể để thread idle ở một pool trong khi pool khác thiếu capacity.

### 6.1. Tách pool theo criticality

Nếu payment listener có SLA cao hơn audit listener, có thể dùng executor riêng:

~~~text
paymentListenerExecutor: 4 threads
ordersListenerExecutor:  4 threads
auditListenerExecutor:   2 threads
~~~

Điều này giới hạn tác động giữa các workloads ở tầng executor. Tuy nhiên, chúng vẫn chia sẻ CPU, heap, network, broker và có thể cùng dùng database pool. Tách executor không loại bỏ bottlenecks chung.

## 7. Đừng nhầm listenerTaskExecutor với @Async executor

Hai executor có mục đích khác nhau:

| Executor | Nhiệm vụ |
|---|---|
| `listenerTaskExecutor` | Chạy consumer tasks của listener containers |
| `@Async` executor | Chạy phương thức ứng dụng được offload bằng Spring async |
| `applicationTaskExecutor` | Có thể được dùng bởi một số tác vụ Spring Boot/application tùy cấu hình |
| Scheduler executor | Chạy scheduled jobs |
| Web request executor | Xử lý request threads của web server |

Nếu listener container và `@Async` dùng chung một pool nhỏ, consumer loops có thể chiếm hết threads và các async business tasks không chạy. Ngược lại, một `@Async` pool quá lớn có thể cạnh tranh CPU/database với consumers.

Nên đặt tên và metrics riêng cho từng pool. Đừng xem một `ThreadPoolTaskExecutor` có 20 threads là “capacity 20 cho mọi thứ” nếu nó được chia sẻ bởi nhiều loại task.

## 8. Thread capacity không bằng business parallelism

Trong cấu hình container thông thường, mỗi consumer thread có thể poll và gọi listener tuần tự. Khi listener thực hiện blocking I/O, thread bị chiếm trong thời gian chờ database/HTTP.

Ví dụ:
- 4 consumers được assign partitions.
- Mỗi record mất 100ms CPU và 900ms chờ database.
- Mỗi consumer xử lý tuần tự một record tại một thời điểm.

Bốn consumers có thể che giấu một phần thời gian chờ nhờ chạy song song trên các partitions khác nhau. Nhưng nếu database chỉ cho phép hai connections và tất cả listeners cùng cần connection, các consumers còn lại sẽ chờ pool hoặc timeout.

Capacity hiệu quả bị giới hạn bởi nhiều yếu tố:

\[
C_{\text{effective}} \leq \min(C_{\text{consumer}}, C_{\text{assigned partitions}}, C_{\text{executor}}, C_{\text{downstream}})
\]

`C_downstream` có thể là DB connection capacity, HTTP concurrency limit hoặc giới hạn của dịch vụ phụ thuộc. CPU-bound workloads còn bị giới hạn bởi số cores và thời gian CPU cần cho mỗi record.

Đây là mô hình khái niệm; hệ thống có batching, asynchronous processing hoặc nhiều dependencies có thể cần mô hình phức tạp hơn.

## 9. Ước lượng throughput từ processing time

Một phép tính đơn giản cho xử lý tuần tự trên mỗi consumer:

\[
Throughput \approx \frac{C_{\text{active}}}{S}
\]

Trong đó:
- `C_active` là số consumers thực sự có thể xử lý song song và được assign partition.
- `S` là thời gian xử lý trung bình một record, tính bằng giây.

Ví dụ bốn consumers active, mỗi record mất trung bình 200ms:

\[
Throughput \approx \frac{4}{0.2}=20
\]

Tức khoảng 20 records/giây trong mô hình đơn giản, trước khi tính overhead, batch, skew và bottlenecks.

Nếu concurrency tăng từ bốn lên tám nhưng topic chỉ có bốn partitions, `C_active` có thể vẫn chỉ là bốn. Nếu database chỉ phục vụ hai concurrent operations hiệu quả, throughput có thể không tăng như công thức lý tưởng.

Đo **p50/p95/p99 processing time**, không chỉ average. Một số record rất chậm có thể làm consumer poll interval vượt ngưỡng và gây rebalance dù average vẫn thấp.

## 10. CPU-bound và I/O-bound workloads

### 10.1. CPU-bound

Nếu listener chủ yếu thực hiện tính toán CPU:
- Số consumer threads lớn hơn nhiều số cores có thể tăng context switching.
- GC pressure có thể tăng do nhiều records/objects cùng tồn tại.
- Throughput không nhất thiết tăng theo concurrency.
- Batch processing và tối ưu thuật toán có thể hiệu quả hơn thêm threads.

Bắt đầu với concurrency phù hợp số partitions và CPU quota, sau đó đo CPU utilization, throttling, GC pause và processing latency.

### 10.2. I/O-bound

Nếu listener thường chờ database hoặc HTTP:
- Một số threads bổ sung có thể tăng khả năng che giấu thời gian chờ.
- Nhưng downstream có giới hạn connection/rate/concurrency.
- Quá nhiều consumers có thể làm cạn connection pool hoặc tạo retry storm.
- Timeout và circuit breaker quan trọng hơn việc tăng thread vô hạn.

Tăng concurrency chỉ có ý nghĩa nếu dependency có capacity để phục vụ các request đồng thời.

## 11. Phối hợp consumer concurrency với database pool

Giả sử mỗi consumer xử lý một record tại một thời điểm và mỗi record cần một DB connection:

~~~text
Kafka consumers: 8
Hikari maximumPoolSize: 4
~~~

Tối đa bốn consumers có thể giữ DB connections cùng lúc; các consumers còn lại chờ pool. Nếu thời gian chờ dài, listener duration tăng và có thể ảnh hưởng `max.poll.interval.ms`.

Không nhất thiết phải đặt DB pool bằng số consumer trong mọi tình huống, bởi DB connection có thể được dùng ngắn hoặc chỉ một số record cần DB. Nhưng cần đo:
- Hikari active/idle/pending connections.
- Connection acquisition timeouts.
- SQL query latency và lock waits.
- Listener processing p95/p99.
- Consumer lag và rebalance.

Một hướng ước lượng ban đầu là giới hạn số consumer có thể đồng thời đi vào đoạn DB-critical theo capacity mà database chịu được. Nếu concurrency cao hơn, cần queue/backpressure có giới hạn và timeout hữu hạn.

**Không dùng hàng đợi vô hạn ở cả executor lẫn database pool.** Khi backlog tăng, hệ thống có thể giữ quá nhiều records/requests trong memory, làm tăng latency và nguy cơ OOM.

## 12. Phối hợp với max.poll.interval.ms và max.poll.records

Kafka consumer cần gọi `poll()` đủ thường xuyên. `max.poll.interval.ms` giới hạn khoảng thời gian tối đa giữa các lần poll theo cấu hình consumer. Trong container thông thường, listener được gọi trên consumer thread; nếu listener xử lý quá lâu, lần poll tiếp theo bị trì hoãn.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 100
~~~

Nếu một poll trả 100 records và container xử lý tuần tự, tổng thời gian xử lý batch có thể xấp xỉ:

\[
T_{\text{batch}} \approx \sum_{i=1}^{100} T_{\text{record}_i}
\]

Cần cộng deserialize, interceptor, error handling, commit và overhead. Nếu batch processing vượt `max.poll.interval.ms`, consumer có thể mất group membership và trigger rebalance.

Executor capacity không tự sửa được một listener xử lý quá lâu. Tăng số threads trong pool cũng không khiến một consumer thread gọi poll trong khi chính thread đó đang chạy listener đồng bộ.

### 12.1. Async listener/offload cần semantics rõ

Ứng dụng có thể offload business work sang executor khác hoặc dùng asynchronous listener return types mà Spring Kafka hỗ trợ trong phiên bản cụ thể. Nhưng khi xử lý bất đồng bộ:
- Không ack/commit record trước khi công việc thực sự hoàn tất nếu muốn bảo đảm at-least-once.
- Cần hiểu async acknowledgment semantics của Spring Kafka version đang dùng.
- Không chia sẻ `KafkaConsumer` hoặc gọi consumer APIs từ worker thread tùy ý.
- Phải kiểm soát số lượng in-flight records.
- Cần giữ ordering nếu business key/partition yêu cầu.
- Retry và exception handling phải bao phủ lỗi xảy ra sau khi task được offload.
- Shutdown phải chờ hoặc hủy các công việc in-flight theo policy.

Offload không phải cách miễn phí để tăng consumer capacity. Nó chuyển bottleneck từ consumer thread sang executor khác và đòi hỏi quản lý offset, ordering, memory và backpressure.

## 13. Bounded queues và backpressure

Queue giúp hấp thụ burst, nhưng queue của `listenerTaskExecutor` không phải nơi phù hợp để giữ hàng trăm consumer tasks chờ thread. Các tasks đó là vòng đời consumer dài hạn, không phải công việc ngắn.

Với business work được offload, một queue bounded có thể giúp giới hạn memory và áp dụng backpressure:

~~~text
Kafka consumer
      |
      v
bounded work queue
      |
      +---- capacity available -> worker executes
      |
      +---- queue full -> reject / pause / controlled retry
~~~

Nếu queue đầy, phải có policy rõ ràng:
- Tạm pause container/partition để ngừng nhận thêm records.
- Giữ record chưa ack để có thể redelivery.
- Từ chối task và truyền failure về error handling phù hợp.
- Giới hạn in-flight count và thời gian chờ.

Không bỏ task âm thầm hoặc commit offset rồi mới phát hiện worker không xử lý. Khi dùng manual acknowledgment hoặc async listener, phải xác minh chính xác ack semantics.

### 13.1. Queue latency là một phần processing latency

Nếu record đã được poll khỏi Kafka rồi nằm trong application queue, consumer lag theo committed offset có thể không phản ánh đầy đủ thời gian chờ trong queue. Hãy đo riêng:
- Queue depth.
- Queue wait time.
- In-flight task count.
- Processing duration.
- Age của record đang chờ xử lý.
- Offset commit delay.

Nếu queue chứa record lâu, cần xem nó là một phần của end-to-end latency và memory budget.

## 14. Executor metrics và quan sát capacity

Các chỉ số hữu ích cho executor:

| Metric | Ý nghĩa |
|---|---|
| Pool size | Số threads hiện có |
| Active count | Số threads đang chạy task |
| Queue size | Số tasks đang chờ |
| Remaining queue capacity | Dung lượng queue còn lại |
| Task rejection count | Số lần submit task bị từ chối |
| Task execution duration | Thời gian task chạy |
| Thread creation rate | Tần suất tạo threads |
| Consumer start delay | Thời gian từ lệnh start tới consumer thực sự hoạt động |

Với `ThreadPoolTaskExecutor`, có thể quan sát `getPoolSize()`, `getActiveCount()` và queue của underlying executor qua API phù hợp. Micrometer/Spring Boot có thể instrument một số executor beans tùy cấu hình; nếu tự tạo metrics, đặt tên và tags có cardinality thấp.

Không chỉ nhìn `activeCount == poolSize` là lỗi. Với consumer listener tasks dài hạn, pool đầy có thể là trạng thái **đúng mong đợi**: mỗi consumer giữ một thread. Dấu hiệu cần chú ý là demand vượt capacity, tasks bị queue/reject, consumer không start hoặc processing/lag xấu đi.

## 15. Kafka metrics cần xem cùng executor metrics

Executor metrics riêng không đủ để xác định throughput. Kết hợp:

| Nhóm | Chỉ số |
|---|---|
| Executor | Pool size, active threads, queue depth, rejection |
| Consumer | Records consumed, poll rate, poll duration, assignment |
| Kafka group | Lag per partition, rebalance count/duration |
| Listener | Processing p50/p95/p99, error/retry rate |
| Producer | Send rate, request latency, error/retry rate |
| Database | Active/pending connections, acquisition latency, query latency |
| JVM | CPU, thread count, heap, GC pause, CPU throttling |
| Application queue | Depth, wait time, in-flight work |

Ví dụ diễn giải:
- Pool active đủ nhưng consumer lag tăng, DB pool pending cao: có thể downstream DB là bottleneck.
- Pool queue tăng và một số consumer chưa poll: executor capacity không đủ cho container tasks.
- Pool active thấp, consumers có assignment nhưng throughput thấp: kiểm tra listener logic, poll, pause hoặc dependency.
- Consumer lag thấp nhưng application work queue tăng: backlog đã chuyển từ Kafka sang memory queue.
- CPU throttling và processing p99 tăng: thêm threads có thể làm tình hình xấu hơn.

## 16. Capacity planning theo từng tầng

Một quy trình thực tế:

1. Đếm listener endpoints được start trên mỗi replica.
2. Cộng concurrency của từng endpoint để ra số consumer tasks trên một JVM.
3. Xác định executor nào quản lý từng endpoint và tính tổng demand của mỗi pool.
4. So sánh consumer group member count với partitions của subscription.
5. Đo CPU-bound hay I/O-bound processing.
6. Xác định giới hạn DB connections, HTTP downstream concurrency và producer throughput.
7. Chọn pool size và queue policy có giới hạn.
8. Chạy tải đại diện và đo p95/p99, lag, rebalance, queue depth, CPU và DB waits.
9. Tăng concurrency hoặc pool size từng bước, không thay đổi mọi biến cùng lúc.
10. Chọn capacity có headroom phù hợp cho rebalance, rollout và burst.

Ví dụ một replica:

~~~text
orders-listener:       concurrency 4
payments-listener:     concurrency 2
audit-listener:        concurrency 1
-------------------------------------
consumer tasks:        7

shared listener pool:  7 threads
database pool:          5 connections
CPU quota:              4 cores
topic partitions:
  orders:               8
  payments:             4
  audit:                2
~~~

Pool bảy threads có thể chạy bảy consumer tasks, nhưng DB pool năm connections giới hạn các đoạn xử lý cần DB đồng thời. CPU quota bốn cores có thể giới hạn workload CPU-bound. Partition counts không phải một tổng duy nhất nếu ba listeners dùng các group IDs khác nhau; phải phân tích assignment riêng cho mỗi group.

## 17. Thread naming và thread dumps

Đặt thread name prefix riêng giúp nhận diện consumer tasks:

~~~java
executor.setThreadNamePrefix("kafka-orders-");
~~~

Trong thread dump, threads có thể xuất hiện với tên dạng `kafka-orders-1`, `kafka-orders-2` tùy executor. Khi điều tra:
- Thread `RUNNABLE` và dùng CPU cao: có thể CPU-bound.
- Thread đang chờ JDBC connection: kiểm tra pool và database.
- Thread đang chờ HTTP response: kiểm tra downstream timeout.
- Nhiều consumer threads đang chờ lock chung: tìm contention.
- Consumer tasks chưa được tạo/đang nằm trong executor queue: kiểm tra pool capacity và rejection.
- Consumer thread bị block trong listener: đối chiếu `max.poll.interval.ms` và rebalance.

Thread state là bằng chứng tại một thời điểm. Nên lấy nhiều thread dumps cách nhau một khoảng ngắn để phân biệt một trạng thái chờ bình thường với thread bị kẹt lâu.

## 18. Lifecycle và shutdown của executor

Consumer tasks là các tác vụ dài hạn. Khi ứng dụng shutdown:

1. Spring yêu cầu listener containers dừng.
2. Consumer threads kết thúc vòng đời và đóng KafkaConsumer theo cơ chế container.
3. Executor được shutdown theo Spring bean lifecycle.
4. Các tài nguyên khác đóng theo thứ tự phù hợp.

Nếu executor bị shutdown trước khi container hoàn tất stop, listener tasks có thể bị interrupt/reject hoặc shutdown không như mong đợi. Hãy để Spring quản lý lifecycle beans và kiểm tra thứ tự shutdown của custom executors.

Không bật `waitForTasksToCompleteOnShutdown` một cách máy móc cho pool chứa consumer loops: các task này chỉ kết thúc khi container stop signal được xử lý. Nếu executor chờ task hoàn tất trước khi container được dừng, shutdown có thể bị kéo dài.

Phối hợp:
- Spring lifecycle phase timeout.
- Kafka container shutdown timeout.
- `terminationGracePeriodSeconds` của Kubernetes.
- Dependency request timeouts.
- In-flight business task policy nếu có async offload.

Khi process bị `SIGKILL`, cleanup không được bảo đảm. Offset chưa commit có thể redelivery, vì vậy business effects cần idempotency.

## 19. Những sai lầm thường gặp

- **Pool nhỏ hơn tổng consumer concurrency:** một số consumer tasks phải chờ hoặc bị từ chối.
- **Tính capacity theo từng listener nhưng bỏ qua endpoints dùng chung executor:** tổng demand vượt pool.
- **Nhầm pool size với số consumers có partition:** consumer idle vẫn giữ thread.
- **Tăng concurrency vượt partition count:** tăng threads nhưng không tăng parallelism hữu ích.
- **Dùng unbounded queue cho consumer tasks dài hạn:** container start bị trì hoãn và queue che giấu thiếu capacity.
- **Dùng DiscardPolicy:** consumer task có thể bị bỏ mà không có tín hiệu rõ.
- **Dùng chung pool nhỏ cho listenerTaskExecutor và @Async:** consumer loops chiếm hết threads.
- **Coi executor activeCount bằng pool size là lỗi:** với consumer tasks dài hạn, điều đó có thể bình thường.
- **Tăng threads để chữa DB bottleneck:** tạo thêm connection wait và tải lên database.
- **Bỏ qua max.poll.interval.ms:** listener xử lý lâu làm consumer mất group membership.
- **Offload record rồi ack sớm:** có thể commit offset trước khi business work hoàn tất.
- **Dùng KafkaConsumer từ worker thread:** vi phạm thread-safety/ownership.
- **Không đo application queue:** lag Kafka có thể thấp trong khi công việc vẫn đang chờ trong memory queue.
- **Không tính tổng capacity theo replicas:** pool trong JVM không được chia sẻ giữa Pods.
- **Shutdown executor sai thứ tự:** consumer task không có cơ hội dừng graceful.
- **Chỉ đo average latency:** tail latency có thể gây poll interval và rebalance problems.

## 20. Integration tests cho executor capacity

Nên dùng Kafka Testcontainers hoặc Embedded Kafka để kiểm tra container tasks thực sự chạy trên executor được cấu hình.

Các kịch bản:
1. **Pool đủ capacity:** concurrency bằng pool size; xác nhận tất cả consumer tasks start.
2. **Pool thiếu capacity:** concurrency lớn hơn pool; quan sát task queue/rejection và consumer start delay.
3. **Nhiều endpoints dùng chung pool:** tổng concurrency vượt capacity; xác nhận hành vi được hiểu và giám sát.
4. **Partition count thấp hơn concurrency:** xác nhận một số consumer không có assignment nhưng vẫn chiếm threads.
5. **Consumer group rebalance:** thread tasks vẫn hoạt động và assignment thay đổi đúng.
6. **Listener processing chậm:** kiểm tra poll interval và rebalance behavior.
7. **Downstream DB pool nhỏ:** đo connection pending và listener latency dưới tải.
8. **Pause/resume:** container giữ lifecycle phù hợp và xử lý backlog sau resume.
9. **Shutdown:** stop containers trước khi executor kết thúc, xác nhận consumer resources được đóng.
10. **Thread leak:** start/stop/restart container nhiều lần, xác nhận thread count trở lại mức mong đợi.

### 20.1. Kiểm tra thread names và consumer start

Có thể inject custom executor, bật listener với concurrency nhỏ và dùng latch trong listener/test observer để xác nhận consumer task chạy. Thread name prefix giúp kiểm tra tên thread nếu test harness cần quan sát.

Không chỉ assert `container.isRunning()` rồi kết luận consumer task đã thực sự poll hoặc được assign partition. Kiểm tra riêng:
- Container lifecycle state.
- Consumer start/assignment callback hoặc group metadata.
- Thread count/active pool.
- Record thực tế được listener nhận.

### 20.2. Test rejection có kiểm soát

Nếu cố tình cấu hình pool thiếu thread capacity, test cần:
- Dùng executor riêng cho test.
- Giới hạn thời gian chờ.
- Thu thập rejection/start failure.
- Dọn dẹp container và executor trong test lifecycle.
- Không để consumer task bị queue vô hạn khiến suite treo.

Mục đích là chứng minh capacity mismatch có thể quan sát và được xử lý, không phải tạo một test dựa trên timing không ổn định.

## 21. Quy trình điều tra executor saturation

Khi consumer lag tăng hoặc một listener không start, kiểm tra theo thứ tự:

1. Xác định listener endpoint, group ID và concurrency mong đợi.
2. Đếm số container/consumer tasks trên process.
3. Xác định executor được gắn với mỗi factory.
4. So sánh demand với pool size, active count, queue depth và rejection.
5. Kiểm tra consumer thực sự có thread chạy và có poll không.
6. Kiểm tra partitions/assignment trong group.
7. Đo listener processing duration và tail latency.
8. Đối chiếu DB/HTTP connection pools, CPU và JVM thread dumps.
9. Kiểm tra `max.poll.interval.ms`, `max.poll.records` và retry/backoff.
10. Tăng capacity hoặc thay đổi queue/concurrency từng bước, sau đó theo dõi lag và downstream health.

Nếu pool đầy nhưng mọi consumer threads đều đang chạy bình thường, không cần tăng pool chỉ vì active count đạt maximum. Cần tìm dấu hiệu demand bị chặn: queue/rejection, consumer chưa start, processing chậm hoặc downstream saturation.

## 22. Checklist production

Trước khi triển khai hoặc thay đổi executor capacity:
- Đã cộng concurrency của mọi listener endpoint trên mỗi replica chưa?
- Đã xác định endpoints nào dùng chung `listenerTaskExecutor` chưa?
- Pool size có đủ cho tất cả consumer tasks dài hạn không?
- Queue capacity có giới hạn và có chủ đích không?
- Rejection policy có làm lộ lỗi thay vì bỏ task âm thầm không?
- Concurrency có phù hợp số partitions và group topology không?
- Có consumer threads idle vì concurrency vượt partition count không?
- CPU-bound hay I/O-bound workload đã được đo chưa?
- DB/HTTP downstream có đủ capacity cho concurrency dự kiến không?
- Listener p95/p99 có nằm trong giới hạn `max.poll.interval.ms` không?
- `max.poll.records` có làm batch processing quá lâu không?
- Listener task pool có bị dùng chung với `@Async` hoặc scheduler không?
- Nếu offload business work, có bounded queue, backpressure và ack semantics rõ ràng không?
- Metrics có pool size, active count, queue, rejection và consumer lag không?
- Thread names có giúp tìm đúng listener trong thread dump không?
- Shutdown order có dừng containers trước khi executor bị đóng không?
- Đã test pool đủ/thiếu capacity, rebalance và graceful shutdown chưa?

**Executor capacity** là một phần của capacity planning cho Spring Kafka: mỗi consumer task cần thread để poll và chạy listener, nhưng số thread chỉ là một trong nhiều giới hạn. Hãy tính tổng demand từ replicas và concurrency, kiểm tra partition assignment, cấu hình executor có queue/rejection rõ ràng, rồi đối chiếu với CPU và downstream pools. Tăng thread pool chỉ có ích khi executor thực sự là bottleneck; nếu giới hạn nằm ở partitions, database, listener processing hoặc `max.poll.interval.ms`, tăng threads có thể làm hệ thống tốn tài nguyên hơn mà không tăng throughput.


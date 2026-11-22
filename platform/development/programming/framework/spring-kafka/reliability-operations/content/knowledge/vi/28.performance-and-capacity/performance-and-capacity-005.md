# Consumer fetch sizing

Trong Spring Kafka, **consumer fetch sizing** là việc lựa chọn kích thước và nhịp độ dữ liệu mà Kafka consumer lấy từ broker. Cấu hình fetch ảnh hưởng trực tiếp đến **throughput, latency, memory, network utilization, khả năng xử lý record lớn và độ ổn định của consumer group**. Một consumer lấy quá ít dữ liệu có thể tạo nhiều request nhỏ, tốn network round trips và không tận dụng được batch. Một consumer lấy quá nhiều dữ liệu có thể giữ lượng records lớn trong memory, làm listener xử lý lâu, tăng garbage collection và vượt giới hạn thời gian giữa các lần poll.

Các cấu hình quan trọng gồm **fetch.min.bytes**, **fetch.max.wait.ms**, **max.partition.fetch.bytes**, **fetch.max.bytes** và **max.poll.records**. Chúng không thay thế nhau: một số điều khiển kích thước response từ broker, một số điều khiển số records mà một lần poll trả về. Để sizing đúng, cần hiểu cả **Kafka fetch protocol, compressed record batches, Spring listener container, consumer concurrency, partition assignment, max.poll.interval.ms và downstream processing capacity**.

Không có một bộ giá trị fetch tối ưu cho mọi ứng dụng. Mục tiêu là chọn kích thước đủ lớn để đạt throughput mong muốn, đủ nhỏ để giữ latency và memory trong ngân sách, đồng thời bảo đảm listener xử lý xong trước khi consumer phải poll lại.

## 1. Consumer fetch hoạt động như thế nào?

Kafka consumer không yêu cầu broker gửi từng record một. Consumer gửi **FetchRequest** cho các partitions mà nó đang sở hữu. Broker trả về các record batches có sẵn theo giới hạn fetch và điều kiện chờ đã cấu hình.

Một vòng hoạt động đơn giản:

~~~text
Spring Kafka listener container
          |
          v
KafkaConsumer.poll()
          |
          v
FetchRequest tới broker
  - partitions
  - fetch limits
  - minimum bytes
          |
          v
Kafka broker
  - kiểm tra dữ liệu có sẵn
  - chờ nếu chưa đủ fetch.min.bytes
  - không chờ quá fetch.max.wait.ms
          |
          v
FetchResponse
  - record batches
  - offsets
  - metadata
          |
          v
KafkaConsumer buffer/cache
          |
          v
poll() trả records cho container
          |
          v
@KafkaListener xử lý
~~~

Consumer có thể fetch dữ liệu trước và giữ trong các buffer nội bộ. Vì thế, thời điểm broker trả FetchResponse và thời điểm listener xử lý từng record không nhất thiết trùng nhau.

**Fetch sizing điều khiển cách lấy dữ liệu từ broker; max.poll.records điều khiển số records được trả về trong một lần poll.** Đây là khác biệt quan trọng nhất khi tuning.

## 2. Năm cấu hình cần phân biệt

| Cấu hình | Điều khiển | Đơn vị |
|---|---|---|
| **fetch.min.bytes** | Lượng dữ liệu tối thiểu broker cố gắng tích lũy trước khi trả response | bytes |
| **fetch.max.wait.ms** | Thời gian tối đa broker chờ khi chưa đủ fetch.min.bytes | milliseconds |
| **max.partition.fetch.bytes** | Giới hạn dữ liệu fetch cho mỗi partition trong một request | bytes |
| **fetch.max.bytes** | Giới hạn tổng dữ liệu fetch response cho một request | bytes |
| **max.poll.records** | Số records tối đa trả về trong một lần poll | records |

Các cấu hình này có quan hệ nhưng không thể thay thế nhau:

- fetch.min.bytes và fetch.max.wait.ms tạo trade-off giữa batching và latency.
- max.partition.fetch.bytes bảo vệ khỏi việc một partition chiếm quá nhiều dữ liệu trong fetch.
- fetch.max.bytes giới hạn kích thước response ở mức request.
- max.poll.records giới hạn số records mà ứng dụng nhận ở mỗi lần poll.
- max.poll.interval.ms giới hạn thời gian giữa các lần gọi poll; nó không phải fetch-size setting nhưng ảnh hưởng trực tiếp tới lựa chọn max.poll.records.

## 3. fetch.min.bytes: chờ đủ dữ liệu để batching

**fetch.min.bytes** là lượng dữ liệu tối thiểu mà broker cố gắng trả về cho một FetchRequest. Nếu dữ liệu có sẵn chưa đạt ngưỡng, broker có thể chờ thêm records tới khi đủ lượng bytes hoặc hết thời gian fetch.max.wait.ms.

Giá trị mặc định thường là **1 byte**, tức broker có thể trả dữ liệu ngay khi có dữ liệu phù hợp mà không phải chờ tích lũy một batch lớn.

Ví dụ:

~~~text
fetch.min.bytes = 65536  (64 KiB)
fetch.max.wait.ms = 200

t=0ms    Consumer gửi FetchRequest
t=20ms   Broker có 8 KiB
t=60ms   Broker có 24 KiB
t=110ms  Broker có 70 KiB
         -> đạt min bytes
         -> broker trả response
~~~

Nếu sau 200 ms vẫn chưa đủ 64 KiB, broker không tiếp tục chờ vô hạn; nó trả những dữ liệu hiện có theo semantics fetch.

Tăng fetch.min.bytes có thể:
- Giảm số response nhỏ khi traffic ổn định.
- Tăng lượng dữ liệu mỗi response.
- Tăng network efficiency và khả năng batching.
- Tăng latency đối với topic ít traffic hoặc partition ít dữ liệu.
- Tăng lượng dữ liệu đến cùng lúc, ảnh hưởng memory và processing burst.

Không nên đặt fetch.min.bytes lớn chỉ để tối đa throughput nếu yêu cầu nghiệp vụ cần xử lý record ngay khi có.

## 4. fetch.max.wait.ms: giới hạn thời gian chờ batching

**fetch.max.wait.ms** là thời gian tối đa broker chờ để đạt fetch.min.bytes trước khi trả response.

Ví dụ:
- fetch.min.bytes = 128 KiB
- fetch.max.wait.ms = 100 ms

Nếu consumer nhận dữ liệu nhanh, broker có thể trả ngay khi đạt 128 KiB. Nếu traffic chậm, broker trả sau tối đa khoảng 100 ms với lượng dữ liệu hiện có.

Tác động:
- Giá trị thấp: giảm thời gian chờ, có thể tăng số fetch responses nhỏ.
- Giá trị cao: tăng cơ hội gom dữ liệu, nhưng tăng latency ở traffic thấp.
- Giá trị quá cao: records mới có thể nằm trong broker buffer lâu hơn dù consumer đang hoạt động bình thường.

fetch.max.wait.ms không phải thời gian listener được phép xử lý record và không thay thế max.poll.interval.ms.

## 5. max.partition.fetch.bytes: giới hạn theo partition

**max.partition.fetch.bytes** là lượng dữ liệu tối đa mà consumer yêu cầu broker trả về cho mỗi partition trong một FetchResponse.

Ví dụ:
- Topic orders có 12 partitions.
- Consumer hiện sở hữu 3 partitions.
- max.partition.fetch.bytes = 1 MiB.

Mỗi partition có thể đóng góp dữ liệu tới giới hạn tương ứng trong response, subject to tổng fetch.max.bytes và những quy tắc fetch của broker.

Cấu hình này hữu ích khi:
- Một partition có traffic cao hơn các partition khác.
- Consumer cần giới hạn dữ liệu lấy từ từng partition.
- Có record batches lớn.
- Muốn tránh một partition chiếm quá nhiều fetch buffer.

Giá trị mặc định phổ biến là **1 MiB**. Cần đối chiếu với Kafka client version và kích thước record batch lớn nhất thực tế.

### 5.1. Ngoại lệ để consumer vẫn tiến triển

Giới hạn max.partition.fetch.bytes không phải một hard cap tuyệt đối trong mọi trường hợp. Kafka bảo đảm consumer có thể tiến triển: nếu batch đầu tiên trong partition đầu tiên không rỗng của fetch request lớn hơn giới hạn, broker vẫn có thể trả batch đó để consumer không bị kẹt vĩnh viễn vì không thể lấy một batch nào đủ nhỏ.

Điều này có nghĩa:
- Không nên dựa vào max.partition.fetch.bytes để từ chối mọi record quá lớn.
- Consumer vẫn có thể nhận batch vượt ngưỡng cấu hình trong trường hợp đặc biệt.
- Nếu có record batch lớn, cần sizing memory và downstream theo kích thước thực tế.
- Giới hạn producer/broker message size vẫn cần được thiết kế riêng.

## 6. fetch.max.bytes: giới hạn ở mức FetchResponse

**fetch.max.bytes** giới hạn tổng lượng dữ liệu broker cố gắng trả về cho một FetchRequest. Đây là mức tổng thể, khác với giới hạn cho từng partition.

Ví dụ:
~~~text
fetch.max.bytes = 16 MiB
max.partition.fetch.bytes = 4 MiB

Một response có thể lấy dữ liệu từ nhiều partitions,
nhưng tổng lượng dữ liệu được yêu cầu bị giới hạn
ở mức fetch.max.bytes theo semantics của Kafka.
~~~

fetch.max.bytes giúp tránh một request lấy quá nhiều dữ liệu từ nhiều partitions cùng lúc. Tuy nhiên, cũng như max.partition.fetch.bytes, Kafka có ngoại lệ cho batch đầu tiên cần trả về để consumer có thể tiến triển. Vì vậy, đây không phải một hard memory cap tuyệt đối.

Giá trị mặc định phổ biến là **50 MiB**. Đừng tăng giá trị này mà không tính:
- Số consumers trên mỗi pod.
- Số broker connections.
- Số partitions đang được assign.
- Số FetchResponses có thể đang được xử lý.
- Compression ratio.
- Kích thước object sau deserialize.
- Số records còn nằm trong consumer buffer và application queue.

## 7. max.poll.records: số records mỗi poll

**max.poll.records** giới hạn số records tối đa mà một lần gọi KafkaConsumer.poll() trả về cho ứng dụng.

Ví dụ:
~~~text
max.poll.records = 200

poll() có thể trả:
  200 records
  hoặc 120 records
  hoặc 5 records
  hoặc 0 records
~~~

Giá trị mặc định phổ biến là **500**.

max.poll.records không điều khiển trực tiếp số bytes broker fetch. Kafka consumer có thể đã lấy dữ liệu vào buffer trước khi poll trả records. Nếu đặt max.poll.records thấp, dữ liệu có thể được trả dần qua nhiều lần poll từ buffer.

Tăng max.poll.records:
- Có thể giảm overhead mỗi record và tận dụng batch processing.
- Có thể tăng throughput nếu listener xử lý hiệu quả theo lô.
- Tăng thời gian xử lý một poll nếu listener xử lý đồng bộ.
- Tăng nguy cơ vượt max.poll.interval.ms.
- Có thể làm tăng lượng records đang nằm trong application memory.

Giảm max.poll.records:
- Giảm số records trong một lần poll.
- Giúp listener quay lại poll thường xuyên hơn nếu xử lý từng record.
- Có thể giảm burst processing.
- Có thể giảm throughput nếu overhead per-poll lớn.
- Không đảm bảo memory giảm theo cùng tỷ lệ vì consumer có thể đã prefetch dữ liệu.

**max.poll.records là giới hạn số lượng records, không phải byte limit.**

## 8. fetch sizing và max.poll.interval.ms

Kafka consumer group cần consumer gọi poll theo nhịp. **max.poll.interval.ms** giới hạn thời gian tối đa giữa các lần poll trong mô hình consumer group tương ứng.

Nếu listener xử lý quá lâu trước khi poll tiếp:
- Consumer có thể bị xem là không còn tiến triển.
- Partition assignment có thể bị thu hồi.
- Consumer group có thể rebalance.
- Record chưa commit có thể được giao lại.
- Business side effects có thể bị lặp nếu không idempotent.

Ví dụ:
~~~text
max.poll.records = 500
processing time per record = 100 ms

Thời gian xử lý tối đa lý thuyết:
  500 × 100 ms = 50.000 ms
~~~

50 giây chưa tính deserialize, logging, database waits, transaction commit, error handling và thời gian scheduling. Nếu max.poll.interval.ms là 60 giây, khoảng an toàn có thể rất nhỏ.

Một phép tính sơ bộ:
\[
T_{\mathrm{poll}} \approx N_{\mathrm{records}} \times T_{\mathrm{record}}
\]

Nên bảo đảm thời gian xử lý một poll ở tail latency (ví dụ p99) thấp hơn max.poll.interval.ms với margin phù hợp.

Không chọn max.poll.records chỉ dựa trên average processing time. Một record chậm bất thường hoặc downstream timeout có thể làm cả batch kéo dài.

## 9. Quan hệ giữa fetch limits và memory

Consumer fetch sizing ảnh hưởng memory theo nhiều lớp:
1. Bytes nhận từ broker.
2. Compressed record batches trong network/client buffers.
3. Dữ liệu sau giải nén.
4. Deserialized Java objects.
5. Records được trả từ poll và giữ trong container/listener.
6. Application work queues hoặc asynchronous tasks.
7. Logging/metrics/tracing context.

Một response 10 MiB trên wire có thể tạo footprint lớn hơn đáng kể sau giải nén và deserialize, đặc biệt khi payload là JSON có nhiều object/string.

Không thể tính memory chính xác bằng fetch.max.bytes đơn lẻ.

Một ước lượng ban đầu cho application:
~~~text
memory pressure
  ≈ fetch buffers
  + decompressed batches
  + deserialized records
  + listener in-flight work
  + application queues
  + JVM overhead
~~~

Với concurrency 8, không thể coi một consumer fetch buffer là toàn bộ memory của pod. Mỗi consumer có state/buffers riêng và nhiều consumers có thể fetch đồng thời.

Khi sizing:
- Dùng số consumers thực tế trên mỗi pod.
- Đo kích thước record và batch p95/p99.
- Đo compression ratio.
- Đo object footprint sau deserialize.
- Đo queue depth/in-flight tasks.
- Chừa heap headroom cho GC, transactions và framework objects.

## 10. Compression làm thay đổi phép tính

Kafka producer có thể nén record batches bằng gzip, snappy, lz4 hoặc zstd tùy cấu hình và client version.

Consumer nhận dữ liệu nén qua mạng, sau đó cần giải nén để xử lý records. Vì thế:
- Bytes trên wire có thể nhỏ hơn nhiều so với object graph trong heap.
- fetch.max.bytes không trực tiếp phản ánh kích thước dữ liệu sau deserialize.
- Một batch nén có thể chứa nhiều records.
- Compression ratio thay đổi theo nội dung payload.
- Payload text/JSON lặp lại có thể nén tốt hơn payload đã mã hóa hoặc nén sẵn.

Ví dụ:
~~~text
Compressed batch on wire: 2 MiB
After decompression:       12 MiB
After deserialization:     25 MiB heap estimate
~~~

Các con số chỉ minh họa. Phải đo bằng payload production-like, không dùng một compression ratio cố định cho mọi topic.

## 11. Kích thước record batch và giới hạn producer/broker

Consumer fetch settings cần phối hợp với giới hạn kích thước message/batch ở các thành phần khác:
- Producer max.request.size.
- Producer batch.size.
- Broker message.max.bytes hoặc topic max.message.bytes.
- Consumer max.partition.fetch.bytes.
- Consumer fetch.max.bytes.
- Các giới hạn record batch và serializer.

Nếu producer được phép gửi batch lớn hơn max.partition.fetch.bytes, Kafka vẫn có ngoại lệ trả batch đầu tiên để đảm bảo tiến triển, nhưng ứng dụng nên cấu hình có chủ đích thay vì dựa vào ngoại lệ.

Với large records:
1. Xác định kích thước batch tối đa thực tế.
2. Xem giới hạn broker/topic có cho phép không.
3. Xem producer request có cho phép không.
4. Sizing consumer partition fetch đủ cho workload bình thường.
5. Đánh giá heap sau deserialize.
6. Kiểm tra timeout, retry và DLT có thể chứa record lớn.
7. Tránh cho một record khổng lồ chiếm hết memory budget.

Không tăng tất cả message/fetch limits lên hàng trăm MiB chỉ để làm một record đặc biệt hoạt động. Có thể cân nhắc lưu payload lớn ở object storage và chỉ gửi reference qua Kafka.

## 12. Một ví dụ tính poll processing budget

Giả sử:
- max.poll.records = 120.
- Processing time p50 = 8 ms/record.
- Processing time p95 = 20 ms/record.
- Processing time p99 = 45 ms/record.
- max.poll.interval.ms = 300.000 ms.

Ước lượng:
~~~text
p50 poll work:
  120 × 8 ms = 960 ms

p95 poll work:
  120 × 20 ms = 2.400 ms

p99 worst-like poll work:
  120 × 45 ms = 5.400 ms
~~~

Các phép nhân này giả định xử lý tuần tự và dùng percentile như ước lượng đơn giản. Tail latency của cả batch có thể lớn hơn do phân phối và downstream contention.

Nếu listener xử lý song song, cần tính worker concurrency, queueing và thời gian chờ completion; không chỉ chia tổng thời gian cho số threads.

Mục tiêu là giữ khoảng cách giữa poll calls đủ an toàn, không phải sử dụng hết max.poll.interval.ms.

## 13. Spring Boot cấu hình fetch properties

Spring Boot cho phép đặt Kafka consumer properties trong application YAML. Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      bootstrap-servers: localhost:9092
      group-id: orders-service
      properties:
        "[fetch.min.bytes]": 65536
        "[fetch.max.wait.ms]": 100
        "[max.partition.fetch.bytes]": 4194304
        "[fetch.max.bytes]": 16777216
        "[max.poll.records]": 200
        "[max.poll.interval.ms]": 300000
~~~

Các giá trị trên là một cấu hình minh họa:
- fetch.min.bytes = 64 KiB.
- fetch.max.wait.ms = 100 ms.
- max.partition.fetch.bytes = 4 MiB.
- fetch.max.bytes = 16 MiB.
- max.poll.records = 200.
- max.poll.interval.ms = 5 phút.

Tên property bracket notation giúp giữ nguyên key có dấu chấm trong map properties theo binding conventions của Spring Boot. Cú pháp chính xác cần xác nhận với version Boot đang dùng.

Không sao chép nguyên bộ giá trị này vào production mà chưa đo throughput, latency và memory.

## 14. Cấu hình bằng DefaultKafkaConsumerFactory

Nếu tạo ConsumerFactory thủ công, có thể đặt các Kafka ConsumerConfig properties trong map:
 
~~~java
@Bean
ConsumerFactory<String, OrderEvent> orderConsumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-service");

    props.put(ConsumerConfig.FETCH_MIN_BYTES_CONFIG, 64 * 1024);
    props.put(ConsumerConfig.FETCH_MAX_WAIT_MS_CONFIG, 100);
    props.put(ConsumerConfig.MAX_PARTITION_FETCH_BYTES_CONFIG, 4 * 1024 * 1024);
    props.put(ConsumerConfig.FETCH_MAX_BYTES_CONFIG, 16 * 1024 * 1024);
    props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 200);
    props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 300_000);

    return new DefaultKafkaConsumerFactory<>(
            props,
            new StringDeserializer(),
            new JsonDeserializer<>(OrderEvent.class));
}
~~~

Đây là code minh họa; serializer/deserializer cần được cấu hình type mapping, trusted packages và schema policy phù hợp với ứng dụng.

Các hằng ConsumerConfig giúp tránh lỗi chính tả property name. Cần giữ security properties như SASL/TLS và các consumer options khác từ cấu hình thực tế, không thay bằng map tối giản trong ví dụ.

## 15. Cấu hình fetch cho listener container

ConsumerFactory tạo consumers với Kafka client properties. Listener container quyết định cách poll và dispatch records.

Ví dụ factory:
~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersKafkaListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties()
            .setPollTimeout(1_000L);

    return factory;
}
~~~

**concurrency** là số consumer threads/child containers cho listener, tùy partition assignment và container type. Tăng concurrency có thể tăng khả năng tiêu thụ song song, nhưng cũng làm tăng số Kafka consumers, connections, buffers và memory footprint.

pollTimeout của Spring container là thời gian container chờ poll trả về theo cách gọi poll của nó; nó không phải fetch.max.wait.ms và không thay thế fetch.max.wait.ms.

Một cấu hình hợp lý phải phối hợp:
- Kafka fetch limits trong ConsumerFactory.
- Listener container concurrency.
- Poll timeout.
- AckMode.
- Record/batch listener mode.
- Error handler/backoff.
- max.poll.interval.ms.

## 16. Record listener và batch listener

Record listener:
~~~java
@KafkaListener(
        topics = "orders.created",
        containerFactory = "ordersKafkaListenerFactory")
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Batch listener:
~~~java
@KafkaListener(
        topics = "orders.created",
        containerFactory = "ordersBatchListenerFactory")
public void consumeBatch(List<OrderEvent> events) {
    orderService.processBatch(events);
}
~~~

Batch listener có thể tận dụng database batch writes hoặc bulk API, nhưng:
- Một lần callback có thể xử lý nhiều records.
- Thời gian callback tăng theo batch size.
- Một record lỗi có thể ảnh hưởng xử lý batch/error handling.
- Cần hiểu acknowledgment và partial batch failure semantics.
- max.poll.records ảnh hưởng số records có thể được trả về từ một poll.

Với record listener, container thường dispatch records riêng lẻ nhưng poll vẫn có thể lấy một lượng records lớn. Không hiểu nhầm rằng record listener nghĩa là Kafka chỉ fetch một record mỗi request.

## 17. Concurrency và tổng fetch capacity

Giả sử:
- 6 partitions.
- Listener concurrency = 3.
- Mỗi consumer nhận khoảng 2 partitions.
- fetch.max.bytes = 16 MiB.

Không nên suy ra toàn pod chỉ dùng tối đa 16 MiB. fetch.max.bytes áp dụng cho một FetchRequest; nhiều consumers và requests có thể hoạt động đồng thời.

Một cách nhìn ngân sách:
~~~text
Pod
  |
  +-- Consumer 0 -> fetch buffers, records, listener work
  |
  +-- Consumer 1 -> fetch buffers, records, listener work
  |
  +-- Consumer 2 -> fetch buffers, records, listener work
  |
  +-- Spring container + application heap
~~~

Tăng concurrency:
- Có thể tăng tổng throughput khi partitions đủ và processing song song.
- Tăng số network connections và broker requests.
- Tăng memory buffers và deserialization work.
- Có thể làm database/API contention nặng hơn.
- Không có lợi nếu concurrency lớn hơn số partitions có thể được assign cho group.

Fetch sizing phải được đánh giá ở **cấp pod và toàn cluster**, không chỉ từng consumer.

## 18. Số partitions ảnh hưởng fetch sizing thế nào?

Consumer fetch requests có thể bao gồm nhiều partitions. Một consumer sở hữu nhiều partitions có thể lấy dữ liệu từ nhiều partition trong một request, subject to fetch limits.

Ví dụ:
~~~text
Consumer A owns:
  orders/P0
  orders/P1
  orders/P2
  orders/P3

Consumer B owns:
  orders/P4
  orders/P5
  orders/P6
  orders/P7
~~~

Nếu P0 có traffic lớn còn P1-P3 gần như trống, fetch response của Consumer A có thể chủ yếu đến từ P0. max.partition.fetch.bytes giúp giới hạn lượng lấy từ từng partition, trong khi fetch.max.bytes giới hạn mức tổng request.

Partition count tăng có thể:
- Tăng số partitions được fetch bởi consumer.
- Tăng metadata và per-partition state.
- Tăng số partition-level buffers/requests.
- Tăng tổng series/metrics.
- Tạo thêm cơ hội song song nếu có consumer capacity.

Không chỉ tăng fetch.max.bytes khi tăng partitions; hãy đo response sizes, broker load và consumer memory.

## 19. Partition skew và hot partitions

Một topic có thể phân bố traffic không đều:
~~~text
P0: 80% traffic
P1: 5%
P2: 5%
P3: 5%
P4: 5%
~~~

Nếu một consumer sở hữu P0, nó có thể bị giới hạn bởi hot partition dù các partitions khác ít dữ liệu.

Tuning fetch.max.bytes không sửa được partition skew. Cần:
- Kiểm tra partition key strategy.
- Đo throughput/lag theo partition.
- Xem một key nóng có dồn records vào một partition không.
- Cân nhắc thay đổi key distribution hoặc topic partitioning.
- Đảm bảo ordering requirement trước khi thay key.
- Cân nhắc consumer assignment/concurrency.

Không tăng max.partition.fetch.bytes cho mọi partition chỉ để xử lý một hot partition mà chưa đo memory và broker impact.

## 20. fetch.min.bytes có ý nghĩa khác nhau theo traffic profile

### High-throughput stream

Khi records đến liên tục, fetch.min.bytes cao hơn có thể giúp gom response lớn hơn và giảm overhead.

### Low-throughput command topic

Nếu chỉ vài records mỗi phút, fetch.min.bytes lớn khiến consumer thường xuyên đợi tới fetch.max.wait.ms. Điều này tăng latency cho command.

### Bursty workload

Khi traffic đến theo burst, min bytes có thể gom records tốt trong burst nhưng tăng độ trễ ở khoảng giữa các burst.

### Latency-sensitive event

Nếu mỗi record cần được xử lý ngay, giữ fetch.min.bytes nhỏ và fetch.max.wait.ms thấp thường phù hợp hơn.

Không tuning dựa trên throughput trung bình. Hãy đo latency p50/p95/p99 trong cả giai đoạn yên tĩnh và peak.

## 21. Ví dụ trade-off giữa batching và latency

Giả sử:
- Incoming rate = 2.000 records/giây.
- Average compressed record size = 1 KiB.
- fetch.min.bytes = 64 KiB.
- fetch.max.wait.ms = 100 ms.

Ở rate ổn định, 64 KiB có thể tích lũy nhanh; broker trả response trước timeout. Nhưng ở 10 records/giây, lượng dữ liệu 64 KiB có thể cần nhiều giây mới đủ, nên broker trả theo fetch.max.wait.ms.

~~~text
High traffic:
  min bytes reached quickly
  -> low additional wait

Low traffic:
  min bytes not reached
  -> wait until max wait
  -> return smaller response
~~~

Đó là lý do fetch.max.wait.ms là giới hạn quan trọng cho latency khi traffic thấp. fetch.min.bytes không có nghĩa consumer sẽ chờ đủ lượng bytes bất kể thời gian.

## 22. fetch.min.bytes không phải broker-side batch.size

Hai cấu hình thường bị nhầm:
- Producer batch.size điều khiển cách producer gom records trước khi gửi.
- Consumer fetch.min.bytes điều khiển broker chờ lượng dữ liệu trong fetch response.
- fetch.max.wait.ms giới hạn thời gian broker chờ dữ liệu.
- linger.ms ở producer điều khiển thời gian producer chờ gom batch.

Producer batching và consumer fetch batching nằm ở hai phía khác nhau của pipeline.

~~~text
Producer:
  linger.ms + batch.size
       |
       v
Kafka record batches
       |
       v
Broker log
       |
       v
Consumer:
  fetch.min.bytes + fetch.max.wait.ms
       |
       v
FetchResponse
~~~

Tăng linger.ms có thể cải thiện producer batching nhưng thêm latency ở đầu vào. Tăng fetch.min.bytes có thể cải thiện fetch response batching nhưng thêm latency ở đầu ra. Cần đo end-to-end latency, không tối ưu từng phía riêng biệt.

## 23. receive.buffer.bytes và network socket buffer

**receive.buffer.bytes** là cấu hình socket receive buffer của consumer, khác với fetch.max.bytes. Nó điều khiển kích thước receive buffer của TCP socket theo Kafka client/network stack.

Tăng receive.buffer.bytes có thể giúp throughput trên high-bandwidth/high-latency network trong một số tình huống, nhưng:
- OS có thể điều chỉnh giá trị thực.
- Nhiều connections làm tổng socket memory tăng.
- Không làm broker trả nhiều records hơn về mặt protocol.
- Không thay thế fetch limits.
- Cần đo TCP/network behavior.

Không tăng socket receive buffer theo cùng tỷ lệ với fetch.max.bytes mà không hiểu network path và số connections.

## 24. request.timeout.ms và fetch.max.wait.ms

Hai cấu hình có mục đích khác nhau:
- fetch.max.wait.ms: broker chờ tối đa để đáp ứng fetch.min.bytes.
- request.timeout.ms: client chờ response cho request trước khi xem request timeout theo semantics Kafka client.
- default.api.timeout.ms: timeout mặc định cho một số AdminClient APIs, không phải consumer fetch wait.
- max.poll.interval.ms: thời gian tối đa giữa các lần poll.

Cần tránh cấu hình request.timeout.ms quá thấp so với fetch.max.wait.ms cộng network latency. Nếu request timeout xảy ra trước khi broker có thể trả fetch response bình thường, consumer có thể tạo lỗi/ retry không cần thiết.

Đừng tăng request.timeout.ms để che một listener callback chậm; listener processing time thuộc poll interval và application processing, không phải fetch request timeout.

## 25. fetch sizing và broker quotas

Broker có thể áp dụng quotas theo client/user và network/request rate. Consumer fetch tuning quá mạnh có thể:
- Tăng network throughput.
- Tăng fetch request rate nếu batch nhỏ.
- Tăng response size nếu fetch lớn.
- Tăng broker memory/network pressure.
- Bị throttle khi vượt quota.

Khi thấy consumer throughput không tăng dù tăng fetch limits, kiểm tra:
- Consumer lag.
- Broker throttling metrics.
- Network throughput.
- Request latency.
- Number of fetch requests.
- CPU và GC ở consumer.
- Listener processing latency.
- Quota configuration.

Không kết luận fetch.max.bytes quá thấp nếu thực tế consumer đang bị throttled hoặc downstream chậm.

## 26. Broker replica fetch settings không phải consumer fetch settings

Kafka broker có cấu hình **replica.fetch.max.bytes** và các cấu hình replication fetch khác. Chúng phục vụ follower replicas lấy dữ liệu từ leader để replication.

Consumer settings như fetch.max.bytes và max.partition.fetch.bytes phục vụ application consumers.

Không đổi replica.fetch.max.bytes chỉ để tăng throughput của Spring Kafka listener. Đó là hai luồng dữ liệu khác nhau:
~~~text
Application consumer:
  Consumer fetch properties
  -> application

Broker replication:
  Replica fetch properties
  -> follower broker
~~~

Nếu replication lag hoặc ISR shrink, cần điều tra broker replication, không dùng consumer fetch sizing để xử lý.

## 27. Isolation level ảnh hưởng dữ liệu consumer nhìn thấy

Consumer dùng **isolation.level=read_committed** chỉ nhận các transactional records đã commit và không vượt qua Last Stable Offset khi có transaction chưa hoàn tất.

Điều này có thể khiến consumer chưa nhận được records mới dù broker đã lưu dữ liệu phía sau một transaction đang mở.

~~~text
Log:
  committed record A
  open transaction T1
  later record B

read_committed consumer:
  có thể chờ T1 kết thúc trước khi đọc qua vùng đó
~~~

Nếu consumer có vẻ chờ dù fetch settings lớn, kiểm tra:
- Transaction duration.
- Producer commit/abort.
- Last Stable Offset.
- Transaction coordinator.
- Consumer lag semantics.

Tăng fetch.max.bytes không giúp consumer vượt qua một transaction đang mở khi isolation semantics không cho phép.

## 28. max.poll.records và batch listener sizing

Với batch listener, max.poll.records gần như là giới hạn số records có thể được giao trong một lần poll. Một batch lớn có thể tăng hiệu quả bulk operations nhưng cũng làm:
- Database transaction dài hơn.
- Heap object count tăng.
- Retry một batch trở nên tốn kém.
- Partial failure phức tạp hơn.
- Thời gian giữa poll calls tăng.

Ví dụ:
~~~text
max.poll.records = 500
average DB write = 3 ms/record

Sequential batch work:
  500 × 3 ms = 1.500 ms
~~~

Nếu bulk insert mất 200 ms cho 500 records, batch có thể hiệu quả hơn. Nhưng phải đo p99 và kiểm tra transaction/lock contention.

Chọn batch size theo:
- Database batch capacity.
- Downstream API request limits.
- Memory footprint.
- Retry semantics.
- Poll interval budget.
- Latency objective.

Không dùng max.poll.records lớn chỉ vì batch listener có thể nhận list.

## 29. max.poll.records và asynchronous processing

Một listener có thể đưa records vào executor rồi return. Khi đó poll loop có thể tiếp tục nhanh, nhưng application work queue tăng.

~~~text
Kafka poll
  |
  v
max.poll.records records
  |
  v
listener enqueues work
  |
  v
poll returns
  |
  v
next poll
  |
  v
worker queue grows
~~~

Nếu enqueue nhanh hơn tốc độ worker xử lý:
- Memory tăng theo queue depth.
- Consumer có thể commit offsets trước khi business task hoàn tất nếu acknowledgment design sai.
- Rebalance có thể xảy ra trong khi worker vẫn xử lý.
- Duplicate side effects có thể xuất hiện.

Fetch sizing phải tính cả **in-flight work queue**, không chỉ listener return latency. Giới hạn queue, dùng bounded executor và thiết kế acknowledgment phù hợp.

## 30. Backpressure và fetch sizing

Khi downstream chậm, giảm fetch/poll batch có thể giảm burst, nhưng không thay thế backpressure end-to-end.

Một hệ thống có thể phối hợp:
- max.poll.records nhỏ hơn để giới hạn records mỗi poll.
- fetch.min.bytes thấp hơn để giảm chờ batching nếu latency quan trọng.
- Container pause/resume khi queue vượt high/low watermark.
- Bounded worker pool.
- Rate limit tại dependency boundary.
- Concurrency phù hợp.
- Lag alert và pause duration monitoring.

~~~text
Queue depth >= HIGH
       |
       v
pause consumer
       |
       v
downstream drains queue
       |
       v
Queue depth <= LOW
       |
       v
resume consumer
~~~

Không dùng fetch.max.bytes làm cơ chế rate limiter. Fetch limits điều khiển kích thước lấy dữ liệu, không bảo đảm tốc độ records/giây.

## 31. Sizing theo throughput target

Một quy trình định lượng:
1. Xác định throughput target records/second.
2. Đo average và p99 compressed batch/record sizes.
3. Đo processing time per record và batch.
4. Xác định partitions và consumer concurrency.
5. Xác định memory budget per pod.
6. Chọn max.poll.records theo poll processing budget.
7. Chọn max.partition.fetch.bytes theo record batch size và per-partition burst.
8. Chọn fetch.max.bytes theo tổng response và memory budget.
9. Chọn fetch.min.bytes/fetch.max.wait.ms theo latency target.
10. Load test ở peak và burst traffic.
11. Đo GC, lag, fetch latency và broker throttling.
12. Điều chỉnh từng nhóm settings và so sánh.

Đừng thay tất cả cấu hình cùng lúc vì sẽ khó xác định yếu tố nào làm throughput/latency thay đổi.

## 32. Ví dụ sizing cho service latency-sensitive

Giả sử:
- Mỗi record nhỏ, trung bình 2 KiB compressed.
- Peak 500 records/s.
- Listener cần phản hồi nhanh.
- Concurrency 4.
- Processing p99 15 ms/record.

Một cấu hình thử nghiệm có thể:
~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[fetch.min.bytes]": 1
        "[fetch.max.wait.ms]": 50
        "[max.partition.fetch.bytes]": 1048576
        "[fetch.max.bytes]": 8388608
        "[max.poll.records]": 100
        "[max.poll.interval.ms]": 300000
~~~

Lý do:
- fetch.min.bytes thấp để không chờ batch lớn.
- fetch.max.wait.ms thấp để giới hạn fetch wait khi topic ít traffic.
- Partition fetch limit ở mức 1 MiB cho record nhỏ.
- Fetch response cap 8 MiB là điểm bắt đầu để thử.
- max.poll.records 100 giới hạn batch xử lý mỗi poll.

Đây chỉ là **starting point**, không phải best practice phổ quát. Cần benchmark và điều chỉnh theo partitions, broker response size và memory.

## 33. Ví dụ sizing cho throughput-oriented worker

Giả sử:
- Record trung bình 4 KiB compressed.
- Traffic ổn định cao.
- Batch database writes hiệu quả.
- Consumer có heap headroom.
- Latency mục tiêu cho phép thêm một ít batching delay.

Một cấu hình thử:
~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[fetch.min.bytes]": 131072
        "[fetch.max.wait.ms]": 100
        "[max.partition.fetch.bytes]": 4194304
        "[fetch.max.bytes]": 33554432
        "[max.poll.records]": 400
        "[max.poll.interval.ms]": 300000
~~~

Có thể gom nhiều records hơn mỗi response và poll. Nhưng cần xác nhận:
- Batch listener xử lý trong thời gian poll budget.
- Heap không tăng quá mức.
- Broker không bị throttled.
- Consumer lag giảm thay vì chỉ tạo burst.
- Error handler không retry một batch quá lớn.
- Downstream DB có capacity tương ứng.

Nếu listener p99 processing quá lâu, giảm max.poll.records hoặc tăng poll interval có chủ đích, đồng thời kiểm tra side effects/rebalance.

## 34. Ví dụ sizing cho large records

Giả sử một số records có batch size 3 MiB sau nén và 15 MiB sau giải nén.

Cần:
- Xác nhận producer và broker cho phép batch này.
- Đặt max.partition.fetch.bytes ở mức phù hợp với batch size thông thường.
- Đặt fetch.max.bytes đủ cho nhiều partitions nếu response cần dữ liệu từ nhiều partitions.
- Kiểm tra ngoại lệ first batch có thể vượt giới hạn fetch.
- Đo decompressed heap size và deserialize object graph.
- Xem giới hạn HTTP/database khi payload được chuyển tiếp.

Một consumer có thể đọc được batch lớn nhưng OOM sau khi deserialize. Fetch sizing thành công ở network layer không chứng minh heap đủ lớn.

## 35. Quan sát fetch metrics

Các Kafka consumer metrics hữu ích có thể gồm:
- fetch-rate.
- fetch-size-avg / fetch-size-max.
- records-per-request-avg.
- bytes-consumed-rate.
- records-consumed-rate.
- fetch-latency-avg / max.
- records-lag / records-lag-max.
- partition assignment.
- request latency/throttle time.
- poll-idle-ratio hoặc metrics liên quan poll tùy client version.

Tên metric chính xác phụ thuộc Kafka client version, JMX/Micrometer binder và exporter naming convention.

Các câu hỏi khi đọc:
- Fetch size nhỏ có phải do fetch.min.bytes quá thấp?
- Fetch latency cao có phải do fetch.max.wait.ms?
- Records per request thấp có phải topic ít traffic hay partition distribution?
- Bytes consumed tăng nhưng listener throughput không tăng có phải downstream bottleneck?
- Lag tăng dù fetch response lớn có phải listener xử lý chậm?
- Throttle time tăng có phải broker quota?

Không tuning theo một metric riêng lẻ.

## 36. Đọc fetch-size và latency cùng nhau

Một vài mẫu diễn giải:

| Quan sát | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Fetch size nhỏ, fetch rate cao | Traffic thưa hoặc min bytes thấp | Xem latency target và fetch.min.bytes |
| Fetch latency gần fetch.max.wait.ms | Broker thường chờ đủ min bytes | Xem min bytes và traffic profile |
| Fetch size lớn, GC tăng | Batch/decompression/object graph lớn | Giảm batch hoặc memory pressure |
| Consumer lag tăng, fetch rate thấp | Consumer không fetch được hoặc assignment/network issue | Kiểm tra broker, group, errors |
| Fetch rate cao, records/request thấp | Nhiều fetch nhỏ | Xem min bytes, partitions và traffic |
| Bytes consumed cao, processing throughput thấp | Listener/downstream bottleneck | Xem DB/API latency và queue |
| Broker throttle tăng | Quota hoặc broker capacity | Kiểm tra quota/broker metrics |

Đây là các giả thuyết để điều tra, không phải ánh xạ nguyên nhân chắc chắn.

## 37. fetch.max.bytes không phải memory limit

Một lỗi sizing phổ biến là đặt:
~~~text
fetch.max.bytes = 32 MiB
JVM heap = 64 MiB
~~~

rồi kỳ vọng consumer không thể giữ quá 32 MiB.

Điều đó sai vì:
- Có thể nhiều fetch requests/consumer buffers.
- Nhiều consumers trong một pod.
- Broker có thể trả batch đầu tiên lớn hơn limit để bảo đảm tiến triển.
- Compression làm dữ liệu sau giải nén lớn hơn wire size.
- Deserialized objects có overhead.
- Listener và executor giữ references.
- Framework/GC cần headroom.

Hãy dùng heap profiling/load test để xác định memory footprint. Fetch limits chỉ là một phần của budget.

## 38. Tăng fetch.max.bytes khi nào?

Có thể cân nhắc tăng khi:
- Fetch response thường xuyên bị giới hạn ở fetch.max.bytes.
- Nhiều partitions có backlog đồng thời.
- Consumer network round trips là bottleneck.
- Heap có headroom.
- Broker/network có capacity.
- Poll processing time vẫn trong budget.

Không nên tăng khi:
- Consumer đang bị DB/API bottleneck.
- GC đã cao.
- Pod memory gần limit.
- Listener vượt max.poll.interval.ms.
- Broker đang throttle hoặc overloaded.
- Partition skew mới là nguyên nhân chính.

Tăng fetch.max.bytes trong tình huống downstream chậm có thể làm queue/buffer lớn hơn mà không tăng business throughput.

## 39. Giảm max.poll.records khi nào?

Có thể giảm khi:
- Listener xử lý tuần tự và batch callback quá dài.
- Consumer thường vượt max.poll.interval.ms.
- Một poll tạo burst quá lớn vào database.
- Retry một batch có chi phí cao.
- Memory per poll cao.
- Muốn poll thường xuyên hơn để duy trì group progress.

Nhưng nếu giảm quá thấp:
- Overhead mỗi poll tăng.
- Database bulk operations kém hiệu quả.
- Throughput giảm.
- Consumer có thể không tận dụng đủ network fetch buffers.

Chọn dựa trên p99 processing time và throughput, không chỉ average.

## 40. Tăng max.partition.fetch.bytes khi nào?

Có thể tăng khi:
- Record batches bình thường gần hoặc vượt giới hạn hiện tại.
- Consumer cần đọc các batch lớn hợp lệ.
- Một partition có burst lớn và response bị giới hạn.
- Heap và downstream có đủ capacity.

Không tăng nếu:
- Record size nhỏ.
- Bottleneck ở listener/DB.
- Một partition nóng gây memory pressure.
- Bạn đang cố khắc phục message size vượt broker/topic policy.

Với large records, phối hợp producer max.request.size, broker/topic message size và consumer limits. Đừng chỉ đổi consumer setting.

## 41. fetch.min.bytes và latency SLO

Nếu yêu cầu event-to-processing p99 dưới 100 ms, cấu hình fetch.max.wait.ms = 500 ms có thể không phù hợp với traffic thấp. Nhưng p99 end-to-end còn gồm:
- Producer linger/batch wait.
- Broker append/replication.
- Fetch wait.
- Consumer poll scheduling.
- Listener processing.
- Database/API.
- Commit/transaction.
- Queueing.

Không thể kết luận fetch.max.wait.ms phải bằng p99 SLO; nó chỉ là một phần ngân sách latency.

Một latency budget:
~~~text
End-to-end latency
  = producer delay
  + broker delay
  + fetch wait
  + listener queue/process
  + downstream
  + commit/transaction
~~~

Tối ưu fetch wait mà listener processing chiếm 95% latency sẽ không tạo khác biệt lớn.

## 42. Backoff, retry và fetch sizing

Blocking retry có thể làm consumer không tiến poll bình thường trong thời gian backoff hoặc giữ partition processing. Một record poison có thể làm lag tăng dù fetch settings lớn.

Retry topics chuyển record sang topic retry, cho phép source listener tiếp tục các records khác theo topology. Nhưng retry topic consumer cũng có fetch settings riêng.

Cần sizing riêng cho:
- Main consumer group.
- Retry topic consumers.
- DLT consumers.
- Replay/rebuild consumers.

Không mặc định một ConsumerFactory config tối ưu cho tất cả. Retry topics thường có traffic burst khác main topic; DLT có thể ít traffic nhưng records lớn và cần investigation.

## 43. Fetch sizing khi dùng nhiều clusters

Một service có thể consume từ nhiều Kafka clusters. Mỗi ConsumerFactory có thể có:
- Bootstrap servers riêng.
- Security config riêng.
- Fetch limits riêng.
- Concurrency riêng.
- Topic/partition profile riêng.

Không chia sẻ một ConsumerFactory hoặc AdminClient giữa các clusters nếu config/security/metrics scope khác nhau.

Một cluster high-throughput analytics có thể dùng fetch batching lớn, trong khi cluster command latency-sensitive dùng fetch.min.bytes thấp và fetch.max.wait.ms ngắn.

## 44. Sizing và autoscaling

Khi scale consumer replicas:
- Partitions được phân phối lại.
- Số consumers tăng.
- Tổng fetch requests có thể tăng.
- Tổng memory buffers tăng.
- Broker connection count tăng.
- Per-consumer assigned partitions có thể giảm.
- Throughput có thể tăng cho tới khi downstream/broker/partition limits đạt trần.

Nếu số consumers lớn hơn partitions, một số consumers có thể không được assign partition. Tăng replicas vượt partition count không tự tăng throughput.

Autoscaling dựa trên lag cần xét:
- Lag per partition và lag age.
- Processing throughput.
- Consumer concurrency.
- Downstream capacity.
- Broker quotas.
- Fetch response sizes.
- Memory/CPU headroom.

Không scale consumer replicas chỉ dựa trên CPU nếu bottleneck là fetch/network hoặc downstream database.

## 45. Fetch sizing và broker-side load

Fetch requests có chi phí tại broker:
- Request parsing/dispatch.
- Partition log reads.
- Network response.
- Page cache/disk activity tùy workload.
- Quota accounting.
- Request queueing.

Nhiều consumer instances với fetch.max.wait.ms rất thấp và fetch.min.bytes nhỏ có thể tạo nhiều fetch requests. Ngược lại, fetch responses lớn có thể làm network egress tăng đột biến.

Tối ưu consumer không được làm broker quá tải. Load test phải quan sát cả consumer và broker.

## 46. Consumer fetch và rack awareness

Trong Kafka deployments có rack-aware replica selection, consumer có thể ưu tiên replica gần rack để giảm network cost tùy cấu hình client/broker và phiên bản hỗ trợ.

Fetch sizing vẫn áp dụng cho consumer requests; rack awareness ảnh hưởng broker/replica được chọn, không thay thế fetch limits.

Khi triển khai nhiều vùng/availability zones:
- Đo network egress/cross-zone.
- Xem rack metadata và replica placement.
- Xem latency khi fetch từ replica gần.
- Không giả định tăng fetch.max.bytes sẽ giải quyết cross-zone latency.
- Đảm bảo consistency/isolation semantics theo Kafka configuration.

## 47. Một quy trình tuning từng bước

Nên thay đổi từng nhóm settings theo thứ tự:

1. **Baseline**: đo fetch size, fetch latency, records/request, bytes/sec, lag, processing duration, GC và memory.
2. **Poll budget**: chọn max.poll.records dựa trên thời gian xử lý p99 và max.poll.interval.ms.
3. **Partition fetch**: xem kích thước batch p99 và đặt max.partition.fetch.bytes đủ cho workload bình thường.
4. **Request fetch cap**: đặt fetch.max.bytes theo số partitions, response size và memory budget.
5. **Batch wait**: điều chỉnh fetch.min.bytes/fetch.max.wait.ms theo latency/throughput target.
6. **Concurrency**: kiểm tra tổng consumers, partition distribution và per-pod memory.
7. **Network**: xem receive buffer, broker quotas, fetch request rate và throttling.
8. **Stress test**: peak traffic, burst, large records, downstream slowdown và broker recovery.
9. **Canary rollout**: áp dụng cho một phần consumers trước.
10. **Compare**: so sánh throughput, p99 latency, GC, lag và broker load trước/sau.
11. **Document**: ghi rõ workload assumptions và lý do của từng giá trị.
12. **Revisit**: sizing lại khi record size, partition count hoặc concurrency thay đổi.

Không có lợi ích nếu chỉ tăng một con số mà không biết metric nào cần cải thiện.

## 48. Một ma trận workload tham khảo

| Workload | fetch.min.bytes | fetch.max.wait.ms | max.poll.records | Ưu tiên |
|---|---|---|---|---|
| Command latency-sensitive | Thấp | Thấp | Vừa/nhỏ | Giảm wait và poll duration |
| High-throughput event stream | Vừa/lớn | Vừa | Vừa/lớn nếu processing nhanh | Batching và network efficiency |
| Large record processing | Theo traffic | Theo latency | Thấp/vừa | Memory và record batch size |
| Batch DB writer | Vừa | Vừa | Lớn nếu batch callback nhanh | Bulk throughput |
| Retry/DLT consumer | Theo retry traffic | Theo yêu cầu xử lý | Vừa | Recovery reliability |
| Sparse topic | Thấp | Thấp/vừa | Không quá quan trọng | Không chờ min bytes lâu |

Bảng là điểm bắt đầu định tính. Không có giá trị byte/millisecond phổ quát cho từng workload.

## 49. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Latency cao ở topic ít traffic | fetch.min.bytes lớn và fetch.max.wait.ms dài | Giảm min bytes hoặc max wait |
| Nhiều fetch requests nhỏ | min bytes thấp, traffic thưa hoặc nhiều partitions ít data | Đo fetch rate và latency trước khi tăng min bytes |
| Consumer OOM | Response/batches lớn, concurrency cao, decompression/object overhead | Giảm burst, giới hạn queue, đo heap |
| Consumer lag tăng dù fetch size lớn | Listener/downstream bottleneck | Đo processing latency và queue |
| Rebalance do poll timeout | max.poll.records lớn hoặc listener xử lý chậm | Giảm poll batch, tối ưu processing, xem max.poll.interval |
| Record batch lớn không được xử lý ổn định | Partition fetch sizing và message limits không đồng bộ | Kiểm tra batch size và consumer/broker limits |
| Throughput không tăng khi tăng fetch.max.bytes | Broker quota, hot partition, downstream bottleneck | Xem broker/client metrics |
| Broker egress tăng mạnh | Fetch responses lớn hoặc nhiều consumers | Đo tổng consumers và response rate |
| GC tăng sau khi tăng concurrency | Nhiều buffers và object graphs | Giảm concurrency/batch hoặc tăng capacity |
| Batch retry tốn nhiều thời gian | max.poll.records lớn và một record lỗi | Điều chỉnh batch/error handling semantics |

Đây là các giả thuyết chẩn đoán; cần dùng metrics và logs để xác nhận nguyên nhân thực tế.

## 50. Kiểm thử fetch sizing với Kafka broker

Nên dùng Kafka broker thật trong integration test, ví dụ **Testcontainers Kafka** hoặc EmbeddedKafka phù hợp với dependency version.

### Test 1: fetch batching ở traffic ổn định

1. Tạo topic nhiều partitions.
2. Cấu hình fetch.min.bytes và fetch.max.wait.ms.
3. Produce records theo rate ổn định.
4. Đo fetch size/records per request và end-to-end latency.
5. So sánh với fetch.min.bytes nhỏ hơn.
6. Xác nhận throughput và p95/p99 latency thay đổi như dự đoán.

### Test 2: low-traffic latency

1. Gửi một record mỗi khoảng thời gian dài.
2. Đặt fetch.min.bytes lớn hơn record size.
3. Đặt fetch.max.wait.ms đã biết.
4. Đo thời gian record được giao.
5. Giảm fetch.max.wait.ms.
6. So sánh latency, không chỉ nhìn consumer lag.

### Test 3: max.poll.records

1. Produce một số lượng records lớn.
2. Chạy record listener và batch listener ở cấu hình poll records khác nhau.
3. Đo số records mỗi poll/callback.
4. Đo thời gian xử lý poll và memory.
5. Xác nhận không vượt max.poll.interval.ms.
6. Kiểm tra offset/ack semantics khi batch lỗi.

### Test 4: large record batch

1. Produce record batches gần giới hạn cấu hình.
2. Thử max.partition.fetch.bytes nhỏ hơn batch size.
3. Xác nhận behavior của batch đầu tiên và consumer progress theo Kafka client/broker version.
4. Kiểm tra heap sau decompression/deserialization.
5. Xác nhận không OOM và không tạo retry loop.

### Test 5: concurrency và memory

1. Chạy nhiều listener consumers.
2. Tăng concurrency từng bước.
3. Đo heap, GC, network connections và fetch throughput.
4. Xác nhận tổng pod memory nằm trong budget.
5. Xác nhận consumer group assignment không tạo quá nhiều idle consumers.

### Test 6: downstream slowdown

1. Làm database chậm có kiểm soát.
2. Đo poll processing duration và lag.
3. Thử giảm max.poll.records.
4. Thử bounded queue/pause-resume nếu có async processing.
5. Xác nhận consumer không rebalance ngoài dự kiến.
6. Kiểm tra duplicate/idempotency khi retry.

### Test 7: broker throttling

1. Áp dụng quota test nếu môi trường hỗ trợ.
2. Đo throttle time và fetch rate.
3. Thử thay fetch sizing.
4. Xác nhận không nhầm quota bottleneck với fetch size bottleneck.
5. Khôi phục quota và so sánh.

Các bài test nên có timeout, metrics collection và workload repeatable. Một lần chạy benchmark không đại diện cho mọi production traffic profile.

## 51. Đọc kết quả benchmark

Khi so sánh hai cấu hình, nên ghi:
- Throughput records/sec.
- Throughput bytes/sec.
- End-to-end latency p50/p95/p99.
- Fetch size avg/max.
- Fetch latency avg/max.
- Records per request.
- Consumer lag max và lag age.
- Listener processing duration.
- Poll interval distribution.
- Heap usage và GC pause.
- Broker request rate, network egress và throttle.
- Rebalance count.
- Error/retry/DLT rates.

Ví dụ bảng:
| Metric | Config A | Config B |
|---|---:|---:|
| Throughput | 8.000 rec/s | 9.500 rec/s |
| p99 latency | 90 ms | 145 ms |
| Max lag | 12.000 | 8.000 |
| Heap peak | 1.2 GiB | 1.8 GiB |
| Rebalances | 0 | 2 |

Số liệu trên chỉ minh họa cách so sánh. Config B tăng throughput và giảm lag nhưng latency và heap tăng; lựa chọn cần dựa trên SLO và capacity budget, không chỉ một metric.

## 52. Checklist khi một consumer chậm

Khi consumer lag tăng:
1. Xác nhận consumer có assignment đúng.
2. Xem fetch request rate và fetch latency.
3. Xem fetch size avg/max và records per request.
4. Xem bytes-consumed-rate và records-consumed-rate.
5. Đo listener processing p95/p99.
6. Xem max.poll.records và max.poll.interval.
7. Kiểm tra DB/API latency, executor queue và pause state.
8. Kiểm tra broker throttling và network throughput.
9. Kiểm tra partition skew/hot keys.
10. Kiểm tra compression và deserialize CPU.
11. Xem rebalance/retry/DLT events.
12. Chỉ thay đổi fetch settings khi dữ liệu chỉ ra fetch path là bottleneck.

Consumer lag là kết quả của producer rate trừ consumer processing/commit progress; tăng fetch limit không đảm bảo lag giảm nếu listener không xử lý nhanh hơn.

## 53. Những hiểu nhầm thường gặp

**fetch.max.bytes là giới hạn memory tuyệt đối của consumer.** Không đúng. Nhiều requests, consumers, decompression và object overhead có thể làm memory lớn hơn.

**max.partition.fetch.bytes nhỏ hơn record batch nghĩa record không bao giờ đọc được.** Không đúng trong mọi trường hợp; Kafka có ngoại lệ cho batch đầu tiên để consumer tiến triển.

**max.poll.records điều khiển fetch bytes từ broker.** Không đúng. Nó giới hạn số records trả về từ một lần poll.

**Tăng max.poll.records luôn tăng throughput.** Không đúng. Listener có thể xử lý lâu hơn, tăng memory và vượt poll interval.

**fetch.min.bytes lớn luôn tốt vì response lớn hơn.** Không đúng. Topic ít traffic có thể tăng latency vì broker chờ dữ liệu.

**fetch.max.wait.ms là thời gian listener xử lý.** Không đúng. Đây là thời gian broker chờ để đạt fetch.min.bytes.

**pollTimeout của Spring container là fetch.max.wait.ms.** Không đúng. Chúng thuộc hai tầng khác nhau.

**fetch.max.bytes và max.partition.fetch.bytes là một.** Không đúng. Một cái áp dụng tổng fetch request, một cái theo partition.

**Tăng fetch limits giải quyết hot partition.** Không đúng. Partition skew thường cần xem key distribution và partitioning.

**Tăng concurrency luôn tăng throughput.** Không đúng nếu partitions không đủ hoặc downstream đã bão hòa.

**read_committed consumer không có data là do fetch size nhỏ.** Không nhất thiết. Consumer có thể đang chờ transaction hoàn tất/Last Stable Offset.

**receive.buffer.bytes thay thế fetch.max.bytes.** Không đúng. Một cái liên quan TCP socket buffer, một cái là Kafka fetch response sizing.

**Broker replica.fetch.max.bytes điều khiển Spring consumer.** Không đúng. Nó phục vụ broker replication fetch.

**Tăng request.timeout.ms sửa listener callback chậm.** Không đúng. Listener processing time cần xem poll interval và application design.

## 54. Quy trình triển khai production

Khi tuning consumer fetch sizing trong Spring Kafka:

1. Đo workload thực tế: record size, batch size, traffic rate, compression ratio và partition skew.
2. Xác định latency SLO, throughput target và memory budget của pod.
3. Chọn max.poll.records theo thời gian xử lý p99 và max.poll.interval.ms.
4. Chọn max.partition.fetch.bytes theo kích thước record batches và burst của mỗi partition.
5. Chọn fetch.max.bytes theo tổng response dự kiến và số partitions được assign.
6. Chọn fetch.min.bytes/fetch.max.wait.ms theo trade-off giữa batching và latency.
7. Phối hợp producer/broker/topic message size limits với consumer fetch limits.
8. Tính tổng resource theo số consumers/concurrency trên mỗi pod.
9. Đo memory sau giải nén và deserialize, không chỉ bytes trên wire.
10. Kiểm tra broker quota, fetch request rate, network egress và throttling.
11. Không dùng fetch sizing thay cho backpressure, bounded queues hoặc downstream rate limits.
12. Thử nghiệm riêng record listener, batch listener, retry topic và DLT consumers.
13. Load test high traffic, sparse traffic, burst, large records và downstream slowdown.
14. Canary rollout từng thay đổi và so sánh throughput, latency, lag, GC và broker load.
15. Ghi rõ assumptions, version, giá trị cấu hình và lý do để lần tuning sau có cơ sở.

**Consumer fetch sizing** là bài toán cân bằng giữa lượng dữ liệu broker trả về, số records listener nhận mỗi poll, thời gian xử lý và memory mà mỗi consumer giữ. fetch.min.bytes/fetch.max.wait.ms quyết định mức batching và thời gian chờ; max.partition.fetch.bytes/fetch.max.bytes giới hạn kích thước fetch theo partition và request; max.poll.records quyết định số records trả cho ứng dụng. Một cấu hình tốt phải phù hợp với record size, partition distribution, concurrency, compression, downstream capacity và max.poll.interval.ms. Hãy đo toàn bộ đường đi từ broker tới listener và business side effects, rồi thay đổi từng nhóm setting có kiểm chứng.

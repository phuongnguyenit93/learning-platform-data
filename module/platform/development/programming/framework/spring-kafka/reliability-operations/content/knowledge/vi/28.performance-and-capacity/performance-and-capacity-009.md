# Memory khi giữ record để retry trong Spring Kafka

Khi một Kafka listener xử lý record thất bại, Spring Kafka có thể retry record đó sau một khoảng backoff. Trong thời gian chờ, record và những object liên quan có thể vẫn được giữ trong heap của consumer process. Với payload lớn, batch nhiều record, concurrency cao hoặc retry kéo dài, việc giữ dữ liệu này có thể chiếm đáng kể bộ nhớ, làm tăng GC pause, tạo allocation pressure và cuối cùng gây `OutOfMemoryError`.

Vì vậy, retry policy không chỉ là câu hỏi “thử lại bao nhiêu lần và chờ bao lâu?”. Nó còn là một **quyết định về nơi lưu record trong thời gian chờ retry**:

- Giữ record trong memory của ứng dụng rồi giao lại.
- Seek offset để Kafka consumer đọc lại record từ broker sau đó.
- Republish record sang retry topic để broker lưu giữ và một consumer khác xử lý sau.
- Đưa record vào một durable store/outbox/quarantine được thiết kế riêng.

Các cách này có trade-off khác nhau về heap, network, broker storage, latency, ordering và delivery semantics. Bài học tập trung vào **memory khi giữ record để retry** trong Spring Kafka, đặc biệt là hành vi của `DefaultErrorHandler`, tùy chọn `seekAfterError`, batch/concurrency, backoff, retry topics và cách sizing capacity.

Điểm quan trọng nhất: **serialized record size không bằng lượng heap mà record chiếm trong consumer JVM**. Sau khi fetch, decompress, deserialize và chuyển thành object graph, một message có thể dùng nhiều bộ nhớ hơn kích thước bytes ban đầu. Cần đo bằng workload thực tế và giới hạn số records/batches/in-flight tasks có thể tồn tại đồng thời.

## 1. Record có thể nằm ở đâu trong một lần retry?

Một record đi qua nhiều lớp trước và trong lúc retry:

~~~text
Kafka broker
   |
   | Fetch response (serialized bytes, có thể compressed)
   v
Kafka consumer fetch buffers
   |
   | poll()
   v
Spring Kafka listener container
   |
   | convert / deserialize / dispatch
   v
Listener receives ConsumerRecord / payload object
   |
   +-- Success --> acknowledgement / offset handling
   |
   +-- Failure --> error handler
                    |
                    +-- Seek offsets; fetch lại sau backoff
                    |
                    +-- Retain unprocessed records in memory
                    |
                    +-- Republish to retry topic
                    |
                    +-- Recover to DLT
~~~

Không phải mọi lần retry đều giữ một bản sao độc lập của toàn bộ record. Nhiều thành phần giữ **reference** tới cùng một object hoặc batch. Tuy vậy, các references đó làm object chưa thể được garbage collector thu hồi. Nếu listener tạo thêm object copies, giữ task trong executor queue hoặc lưu retry state riêng, memory footprint có thể tăng thêm.

Một cách nhìn hữu ích là phân biệt:

| Nơi giữ dữ liệu | Ví dụ | Tác động memory |
|---|---|---|
| Kafka client fetcher | Các batches đã fetch nhưng chưa được trả hết qua poll | Consumer heap và buffers |
| Poll result | Records được trả về từ `poll()` | Tập record đang chờ container xử lý |
| Listener/container | Record hiện tại và records còn lại trong batch | Giữ object references |
| Error handler | Retry/recovery state, record cần giao lại | Có thể kéo dài lifetime của records |
| Deserializer/converter | Object graph, byte arrays, String, DTO | Có thể lớn hơn serialized bytes |
| Application executor | Tasks đang chờ hoặc chạy async | Queue và in-flight objects |
| Kafka producer | Records đang chờ gửi retry/DLT/output | Producer buffers và serialized data |
| Retry topic/DLT | Record được lưu trên broker | Dịch chuyển retention sang broker; vẫn có client buffers |

Một incident memory thường không đến từ một record đơn lẻ mà từ **nhiều records cùng tồn tại lâu hơn dự kiến**.

## 2. Vì sao serialized size đánh giá thấp heap usage?

Giả sử một record có value 200 KB trên Kafka. Trong consumer JVM, dữ liệu có thể trải qua các dạng:

1. Byte arrays hoặc buffers được fetch từ broker.
2. Decompression nếu batch/record được nén.
3. Deserialization thành String, JSON tree hoặc Java DTO.
4. Object graph gồm nested objects, collections, strings và boxed primitives.
5. Business transformations tạo thêm objects.
6. Retry/error handling giữ references tới record và payload.
7. Logging/tracing/conversion có thể tạo thêm metadata hoặc copies nếu implementation yêu cầu.

Một payload JSON 200 KB có thể trở thành object graph lớn hơn nhiều, đặc biệt khi có nhiều String fields, maps, lists và nested DTOs. Không có một multiplier cố định phù hợp với mọi serializer, JVM và schema.

### 2.1. Ví dụ về object amplification

Một JSON payload:

~~~json
{
  "orderId": "order-42",
  "customer": {
    "name": "Example Customer",
    "addresses": [
      { "city": "HCMC", "postalCode": "700000" }
    ]
  },
  "items": [
    { "sku": "A-1", "quantity": 2, "price": 10.5 },
    { "sku": "B-2", "quantity": 1, "price": 25.0 }
  ]
}
~~~

Khi deserialize, JVM tạo nhiều object: root DTO, customer DTO, address list, address DTO, items list, item DTOs, Strings, numeric wrappers hoặc primitive fields tùy model. Mỗi object có header/alignment/reference overhead. String có thể giữ backing array; collections giữ array nội bộ và references.

Với một record, overhead có thể nhỏ. Với 10.000 records có cùng shape, object overhead trở thành đáng kể.

### 2.2. Compression không giảm heap theo cùng tỷ lệ

Kafka batch compression giúp giảm bytes trên network và log storage. Khi consumer fetch và decompress, application vẫn cần dữ liệu ở dạng có thể xử lý. Không lấy compressed size để sizing heap cho listener.

Ví dụ:

- Compressed batch: 5 MB.
- Decompressed record data: 30 MB.
- Deserialized DTO graph: 55 MB.

Các con số trên chỉ minh họa khả năng amplification. Hãy đo bằng payload production-like, serializer và JVM thực tế.

### 2.3. Byte arrays, String và copies

Nếu listener nhận `byte[]`, application có thể giữ bytes gốc. Nếu nhận String rồi parse JSON, bytes/string/tree/DTO có thể cùng tồn tại trong một giai đoạn. Nếu code serialize lại record để publish retry/DLT, producer có thể giữ thêm byte buffers.

Hạn chế tạo nhiều copies không cần thiết, nhưng đừng tối ưu bằng cách chia sẻ mutable object giữa threads nếu điều đó gây data races hoặc làm thay đổi payload trong lúc retry.

## 3. DefaultErrorHandler và hai cách xử lý records còn lại

Trong Spring Kafka hiện đại, `DefaultErrorHandler` xử lý lỗi listener, retry theo BackOff và chuyển record đến recoverer khi retry policy kết thúc.

Khi một record trong poll thất bại, những records chưa được xử lý trong poll cũng cần được xử lý đúng. Spring Kafka có hai hướng quan trọng:

- **Seek behavior:** error handler seek các offsets cần thiết để records được fetch/delivery lại sau đó.
- **Retain behavior:** với `seekAfterError=false` trong các phiên bản hỗ trợ, container giữ các records chưa xử lý trong memory và resubmit chúng sau một poll được pause để duy trì consumer liveness.

Tùy chọn retain có thể hữu ích khi muốn tránh seek/re-fetch, nhưng đổi lại records cần retry vẫn chiếm heap trong thời gian chờ.

### 3.1. Seek-based retry

Mô hình khái niệm:

~~~text
poll() returns records 100..109
       |
       v
listener handles 100, 101, 102
       |
       v
record 103 fails
       |
       v
error handler seeks relevant offset(s)
       |
       v
backoff / retry handling
       |
       v
consumer polls again
       |
       v
Kafka redelivers from the seek position
~~~

Trong seek-based handling, container/error handler dùng consumer position để yêu cầu đọc lại các records cần thiết. Những records từ poll trước không cần được giữ như một retained in-memory collection cho lần resubmit theo cơ chế retain; tuy nhiên Kafka client vẫn có fetch buffers và container vẫn có thể giữ references trong quá trình xử lý hiện tại.

Seek không có nghĩa memory usage bằng zero. Nó chỉ thay đổi nơi container lấy lại record cho lần delivery tiếp theo: broker/client fetch path thay vì giữ nguyên tập records chưa xử lý để resubmit.

### 3.2. Retain-based retry với seekAfterError=false

Ở những phiên bản Spring Kafka hỗ trợ `setSeekAfterError(false)`, container có thể giữ records chưa xử lý và giao lại sau khi thực hiện một poll trong trạng thái pause.

~~~text
poll() returns records 100..109
       |
       v
listener handles 100, 101, 102
       |
       v
record 103 fails
       |
       v
records requiring redelivery are retained in memory
       |
       v
container pauses delivery and performs poll to maintain liveness
       |
       v
backoff expires
       |
       v
retained records are resubmitted
~~~

Cách này tránh seek/re-fetch cho phần records được giữ lại theo cơ chế của container, nhưng **lifetime của record objects dài hơn**. Nếu batch lớn hoặc backoff dài, các object references có thể tồn tại lâu trong heap.

Đây là lựa chọn cần cân nhắc khi sizing memory. Không bật retain mode chỉ vì nó có vẻ đơn giản hơn seek mà không đo lượng records và payload giữ lại.

### 3.3. Tùy chọn phụ thuộc phiên bản

`seekAfterError` và semantics của retain/resubmit có thể thay đổi theo Spring Kafka version. Trước khi sử dụng, kiểm tra Javadoc/reference của đúng dependency, đặc biệt nếu service đang dùng version cũ hơn hoặc có custom error handler.

Không giả định mọi error handler đều có hành vi giống `DefaultErrorHandler`. Custom handler có thể seek, retain, discard hoặc publish records theo cách riêng.

## 4. Memory trade-off giữa seek và retain

| Tiêu chí | Seek/re-fetch | Retain/resubmit |
|---|---|---|
| Nơi lấy lại records | Kafka broker qua consumer fetch | Records đang được container giữ |
| Heap lifetime của batch cũ | Có thể ngắn hơn sau khi references được giải phóng | Có thể kéo dài đến khi resubmit/recover |
| Network/fetch work | Có thể fetch lại dữ liệu | Tránh một phần re-fetch cho records retained |
| Backoff dài | Consumer/container vẫn cần xử lý poll/liveness đúng cách | Retained objects có thể nằm trong heap suốt thời gian chờ |
| Batch lớn | Không giữ retained collection qua các lần retry theo cùng cơ chế | Có thể tốn heap đáng kể |
| Ordering/re-delivery | Theo seek/consumer semantics | Theo thứ tự resubmit của container |
| Phù hợp | Cần giới hạn heap và chấp nhận re-fetch | Muốn giữ records trong memory và đã sizing đủ |

Không có một lựa chọn tốt nhất cho mọi workload. Nếu payload nhỏ, batch nhỏ và backoff ngắn, retain có thể hoạt động tốt. Nếu payload lớn, batch lớn hoặc outage dài, seek hoặc retry topics có thể phù hợp hơn.

## 5. Công thức capacity cho records đang được giữ

Một mô hình ước lượng ban đầu:

~~~text
Retained heap estimate
  ≈ concurrent consumers
    × retained records per consumer
    × average in-memory bytes per record
    × retention multiplier
~~~

Trong đó:

- **Concurrent consumers**: số child consumer containers đang hoạt động trong instance.
- **Retained records per consumer**: số records có thể còn được giữ từ poll/batch khi retry.
- **Average in-memory bytes per record**: heap footprint đo từ object graph sau deserialize, không phải Kafka serialized size.
- **Retention multiplier**: phần overhead bổ sung do references, batch/list structures, error state, conversion và các objects cùng tồn tại. Đây là hệ số đo được, không phải constant của Spring Kafka.

Tổng heap còn cần cộng fetch buffers, listener allocations, producer buffers, executor queues, framework overhead và phần application khác.

### 5.1. Ví dụ tính toán

Giả sử một instance có:

- 4 child consumers.
- Mỗi consumer có thể giữ 250 records từ poll.
- Heap footprint trung bình sau deserialize là 80 KB/record.
- Hệ số dự phòng cho object/batch overhead là 1,5 trong ví dụ đo đạc.

~~~text
4 × 250 × 80 KB × 1.5
= 120,000 KB
≈ 117 MiB
~~~

Khoảng 117 MiB chỉ là ước lượng phần retained batch theo giả định trên. Nó chưa bao gồm fetch buffers, producer buffers, application state, thread stacks, caches và các records đang được xử lý ở những nơi khác.

Nếu payload trung bình tăng gấp đôi hoặc concurrency tăng từ 4 lên 8, phần memory ước lượng cũng tăng gần tuyến tính trong mô hình đơn giản.

### 5.2. P95/P99 quan trọng hơn average

Payload sizes thường có phân bố lệch: phần lớn records nhỏ nhưng một số records rất lớn. Dùng average có thể đánh giá thấp memory ở giờ cao điểm.

Nên đo:

- Serialized value size p50/p95/p99.
- Deserialized object graph size p50/p95/p99.
- Records per poll/batch.
- Số records retained khi retry.
- Số consumer children trên mỗi pod.
- Thời gian giữ record trong memory.
- Tỷ lệ records có payload đặc biệt lớn.

Sizing nên dựa trên workload peak hoặc percentile được SLO chấp nhận, không chỉ average của một ngày yên tĩnh.

### 5.3. Không nhân số retry attempts một cách máy móc

Nếu cùng một record object được giữ và resubmit, số lần retry không nhất thiết tạo thêm một bản sao object đầy đủ cho mỗi attempt. Memory có thể chủ yếu phụ thuộc số records đang retained và object allocations phát sinh trong mỗi attempt.

Ngược lại, nếu code lưu mỗi attempt vào list/cache, tạo transformed copies hoặc enqueue task mới, memory có thể tăng theo attempts. Hãy phân tích object references và heap dominator thay vì giả định retry count luôn là multiplier.

## 6. max.poll.records: giới hạn số records trả về từ poll

`max.poll.records` là consumer configuration giới hạn số records mà một lần `poll()` trả về cho application. Đây là một trong những nút điều khiển quan trọng đối với kích thước batch và lượng dữ liệu mà listener container có thể phải xử lý.

Ví dụ Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.records: 100
~~~

Nếu một consumer poll tối đa 100 records thay vì 500, số records trong một lần xử lý có thể giảm, từ đó giảm retained batch size trong nhiều kịch bản.

Nhưng `max.poll.records` **không phải byte limit tuyệt đối cho heap**:

- 100 records có thể là 100 KB hoặc hàng trăm MB tùy payload.
- Kafka consumer fetcher có thể đã buffer dữ liệu từ broker trước khi poll trả records.
- Một record/batch có thể lớn hơn giới hạn fetch thông thường theo quy tắc đảm bảo consumer có thể tiến triển.
- Deserialized objects có thể lớn hơn serialized bytes.
- Nhiều child consumers có các poll/fetch state riêng.

### 6.1. Chọn max.poll.records theo memory và processing time

Giảm `max.poll.records` thường giảm lượng records xử lý trong một poll nhưng có thể làm tăng số poll và giảm throughput nếu batch processing được tối ưu.

Ngoài memory, phải xem tổng thời gian xử lý batch so với `max.poll.interval.ms`. Batch nhỏ hơn có thể giúp consumer quay lại poll thường xuyên hơn, nhưng không thay thế timeout cho một record bị treo.

### 6.2. Batch listener có batch object lớn

Với batch listener, container chuyển nhiều records cho một invocation. Một batch 500 records với payload lớn có thể giữ cả list, ConsumerRecord wrappers và DTO objects cùng lúc.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders.bulk",
    groupId = "orders-bulk-service"
)
public void consumeBatch(List<OrderEvent> events) {
    bulkService.process(events);
}
~~~

Nếu batch listener thất bại ở một record, error handling và retry semantics cần được hiểu theo batch mode. Việc giữ/replay batch có thể khiến nhiều records khác cũng phải ở lại memory trong khi chỉ một record lỗi.

Đừng chỉ đo size của record lỗi; hãy đo toàn bộ batch và object graph được listener giữ.

## 7. Fetch byte limits không phải heap cap

Kafka consumer có các cấu hình như:

- `fetch.max.bytes`: giới hạn tổng bytes của một fetch response theo semantics client.
- `max.partition.fetch.bytes`: giới hạn bytes fetch cho mỗi partition.
- `max.poll.records`: số records trả về qua một poll.
- `fetch.min.bytes` và `fetch.max.wait.ms`: ảnh hưởng cách broker gom dữ liệu trước khi trả fetch response.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        fetch.max.bytes: 52428800
        max.partition.fetch.bytes: 1048576
        max.poll.records: 100
~~~

Các giá trị chỉ minh họa. Hãy chọn theo payload size, partition count, throughput và memory budget.

### 7.1. Một batch có thể vượt giới hạn dự kiến

Kafka consumer có các quy tắc cho phép tiến triển khi batch đầu tiên trong partition lớn hơn `max.partition.fetch.bytes` hoặc fetch limit tương ứng. Vì vậy không xem các cấu hình byte này như một hard heap ceiling tuyệt đối.

Nếu producer cho phép record rất lớn, consumer phải có capacity và policy xử lý tương ứng. Tốt hơn là định nghĩa payload size limits ở producer/topic/broker contract.

### 7.2. Fetcher có thể giữ nhiều dữ liệu hơn một poll

`max.poll.records` giới hạn records trả cho một poll, không nhất thiết giới hạn lượng bytes đã được fetch/cache trong client. Consumer có thể có buffered data cho lần poll sau.

Khi điều tra heap, xem cả Kafka client fetch buffers và records đã chuyển lên application objects.

### 7.3. Nhiều partitions đồng thời

Một fetch request có thể lấy dữ liệu từ nhiều assigned partitions. Với concurrency lớn, mỗi consumer child có fetch state riêng. Tổng memory của một pod phải tính theo **tất cả consumers**, không phải một consumer đơn lẻ.

## 8. Concurrency nhân mức tiêu thụ memory

Một `ConcurrentMessageListenerContainer` có thể quản lý nhiều child consumers. Mỗi child có consumer client, fetch buffers, assignment và poll batches riêng.

~~~text
orders-listener (concurrency=4)
    |
    +-- child-0: fetch buffers + current/retained records
    +-- child-1: fetch buffers + current/retained records
    +-- child-2: fetch buffers + current/retained records
    +-- child-3: fetch buffers + current/retained records
~~~

Nếu mỗi child có thể giữ 200 records và mỗi record có heap footprint 150 KB, retained payload estimate trước overhead là:

~~~text
4 × 200 × 150 KB = 120,000 KB ≈ 117 MiB
~~~

Tăng concurrency có thể tăng throughput khi có đủ partitions và downstream capacity, nhưng cũng làm tăng số consumer instances, fetch buffers, batches và in-flight listener work.

### 8.1. Concurrency không tạo thêm partition

Nếu topic chỉ có 3 partitions mà listener concurrency là 8, không có nghĩa 8 consumers cùng xử lý song song một partition. Một số child có thể không được assign partitions, nhưng vẫn có overhead về threads/client lifecycle tùy implementation.

Hãy tính memory theo child consumers thực sự chạy và được assign, đồng thời đo khi rebalance.

### 8.2. Nhiều listener containers trong cùng JVM

Một Spring Boot application có thể có nhiều listener factories và nhiều listeners:

- Orders listener concurrency 4.
- Payments listener concurrency 3.
- Audit listener concurrency 2.

Tổng consumer children là 9, chưa kể producer templates, retry listeners và AdminClient. Nếu chỉ sizing từng listener riêng, tổng heap có thể vượt pod limit.

Dùng service-wide memory budget và metrics theo listener ID/container.

## 9. Backoff kéo dài làm record sống lâu hơn

Một retry policy có thể có số attempts nhỏ nhưng thời gian giữ record dài:

~~~java
DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(10_000L, 5L)
        );
~~~

Ví dụ này dùng backoff 10 giây với số lần retry được cấu hình theo API Spring Kafka. Tổng thời gian một record có thể nằm trong retry flow còn phụ thuộc listener processing, lần giao lại, recovery và cách handler tính attempts.

Khi record được retained trong memory, backoff dài làm object references tồn tại lâu hơn. Khi nhiều partitions cùng gặp lỗi dependency, số retained records có thể tăng và GC khó thu hồi chúng.

### 9.1. Backoff và heap occupancy

Một cách nhìn đơn giản:

~~~text
Memory pressure
  ∝ records retained concurrently
    × heap footprint per record
    × time records remain reachable
~~~

Đây không phải công thức GC chính xác, nhưng nhấn mạnh hai yếu tố: số lượng records đồng thời được giữ và lifetime của chúng.

Nếu database outage kéo dài 20 phút, retain mode có thể giữ các records chưa xử lý trong khoảng thời gian đáng kể. Nếu nhiều records được poll trong lúc dependency lỗi, memory pressure tăng theo backlog đang nằm trong process.

### 9.2. Retry nhiều lần không có nghĩa tăng heap tuyến tính

Nếu handler resubmit cùng records, số references có thể không tăng theo số attempts. Nhưng mỗi attempt có thể tạo exception objects, stack traces, temporary payload transformations, logs và DB/network buffers.

Một retry storm làm allocation rate tăng ngay cả khi retained set không tăng. Theo dõi cả heap occupancy và allocation/GC rate.

## 10. ContainerPausingBackOffHandler và poll liveness

Với backoff dài, chặn consumer thread bằng sleep có thể làm nó không poll đủ thường xuyên và vi phạm `max.poll.interval.ms`. Spring Kafka cung cấp `ContainerPausingBackOffHandler` trong các phiên bản hỗ trợ để phối hợp backoff với việc pause container, cho phép container tiếp tục poll theo cơ chế cần thiết.

Ví dụ cấu hình minh họa:

~~~java
DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(30_000L, 3L),
                new ContainerPausingBackOffHandler()
        );
~~~

Kiểm tra constructor/API trên đúng Spring Kafka version trước khi dùng. Cách xử lý backoff dài giúp bảo vệ group liveness, nhưng **không tự giải quyết memory retention**.

Nếu kết hợp `seekAfterError=false`, retained records vẫn có thể nằm trong memory trong lúc container pause/backoff. Poll để duy trì liveness không có nghĩa records retained được giải phóng.

### 10.1. Pause khác stop

Pause container tạm ngừng delivery/fetch từ những partitions đã pause theo semantics của container, trong khi container vẫn có thể poll để duy trì group membership. Stop đóng consumer và rời lifecycle/group.

Không stop consumer chỉ để giải phóng retained records nếu chưa đánh giá offset, in-flight work, redelivery và rebalance. Restart có thể khiến records được đọc lại, nên business side effects phải idempotent.

### 10.2. Backoff handler không thay thế capacity planning

Một handler giữ poll loop khỏe mạnh nhưng heap vẫn có thể cạn nếu retained set lớn. Cần sizing records/batch, memory metrics, bounded retries và recovery path độc lập.

## 11. Stateful retry và retry state caches

Một số ứng dụng dùng Spring Retry hoặc custom stateful retry để lưu trạng thái attempts theo message key/record identity. Khi đó memory có thể tăng không chỉ vì payload records mà còn vì **retry state entries**.

Một state cache có thể lưu:

- Key nhận diện record.
- Số lần retry.
- Timestamp lần thử gần nhất.
- Exception hoặc retry context.
- Metadata dùng để quyết định tiếp tục hay kết thúc.

Nếu cache không có giới hạn capacity/TTL/eviction hoặc key không ổn định, các entries có thể tồn tại lâu hơn dự kiến.

### 11.1. Retry state nên bounded

Thiết kế cache cần xác định:

1. Số entries tối đa.
2. TTL hoặc expiry policy.
3. Cách cleanup khi recovery thành công.
4. Cách xử lý khi process restart.
5. Khóa retry state có ổn định qua redelivery không.
6. Có lưu exception/stack trace hoặc payload lớn không.

Không lưu toàn bộ `ConsumerRecord` hoặc DTO graph trong một retry cache nếu chỉ cần key và attempt metadata.

### 11.2. In-memory state không phải durable retry log

Nếu process crash, retry state trong heap có thể mất. Kafka committed offsets và redelivery là cơ chế phục hồi khác. Không dùng in-memory retry cache làm bằng chứng record đã được lưu bền vững.

Nếu cần retry state sống qua process restart, cân nhắc retry topics hoặc durable store với idempotency/reconciliation rõ ràng.

## 12. Retry topics chuyển một phần retention sang broker

Với non-blocking retry, record được publish sang retry topic và được consume lại sau một khoảng thời gian. Thay vì giữ record trong application heap trong suốt backoff, hệ thống lưu record trên Kafka broker.

~~~text
source topic
   |
   v
listener fails
   |
   v
producer sends retry record
   |
   v
retry topic (broker retention)
   |
   | delay / due time
   v
retry listener consumes record
   |
   +-- success
   |
   +-- fail --> next retry topic / DLT
~~~

Cách này giảm thời gian giữ record trong consumer JVM cho backoff dài, nhưng không làm memory cost bằng zero:

- Consumer vẫn fetch batches từ retry topic.
- Producer vẫn buffer/serialize retry records.
- Retry listener vẫn deserialize payload.
- Retry headers và metadata làm record lớn hơn.
- Broker cần disk/network/replication capacity.
- Nhiều retry topics có thể làm tăng metadata và operational overhead.

### 12.1. Khi nào retry topics phù hợp?

Retry topics thường đáng cân nhắc khi:

- Backoff kéo dài từ hàng chục giây đến phút.
- Không muốn giữ consumer thread/batch trong memory suốt thời gian chờ.
- Có thể chấp nhận ordering semantics thay đổi giữa source và retry topics.
- Có đủ broker capacity và policy retention.
- Retry processing có thể được thiết kế idempotent.

### 12.2. Khi nào blocking retry phù hợp?

Blocking retry có thể phù hợp khi:

- Lỗi thường ngắn và transient.
- Cần giữ thứ tự xử lý của partition theo cách đơn giản.
- Payload nhỏ và batch/concurrency được giới hạn.
- Backoff ngắn.
- Không muốn thêm retry topics và routing infrastructure.

Không chọn retry topics chỉ để giảm heap nếu broker đang thiếu disk/network capacity hoặc ordering requirements không cho phép chuyển record sang topic khác.

### 12.3. Ordering cần được xem xét

Khi một record lỗi được chuyển sang retry topic, records phía sau trong source topic có thể tiếp tục được xử lý, tùy cấu hình. Điều đó có thể làm thay đổi thứ tự hoàn tất nghiệp vụ.

Nếu yêu cầu ordering nghiêm ngặt theo key/partition, cần thiết kế retry strategy bảo toàn sequencing hoặc chặn tiến độ phù hợp. Memory optimization không được làm sai domain ordering.

## 13. Async listener và application executor queues

Một nguồn memory rất lớn nằm ngoài Spring Kafka error handler: listener submit task sang executor rồi return.

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    workerPool.submit(() -> orderService.process(event));
}
~~~

Nếu executor queue không giới hạn, consumer có thể poll và submit records nhanh hơn worker xử lý. Queue giữ references tới event objects, làm heap tăng không giới hạn dù Spring Kafka không retain records cho retry.

Đây là **application queue**, không phải retained records collection của `DefaultErrorHandler`.

### 13.1. Bounded executor queue

Dùng bounded queue và một rejection/backpressure policy được thiết kế rõ:

~~~java
@Bean
public ThreadPoolTaskExecutor orderWorkerPool() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("order-worker-");
    executor.initialize();
    return executor;
}
~~~

Các con số chỉ minh họa. Bounded queue giới hạn số tasks chờ nhưng cần xử lý queue-full behavior. Một `RejectedExecutionException` có thể được truyền về listener để error handler xử lý, hoặc application có thể pause container qua control plane phù hợp.

### 13.2. Ack sau khi async task hoàn tất

Nếu listener return trước khi worker hoàn tất, container có thể acknowledge/commit input record theo policy trước khi business task thành công. Khi đó memory queue và data correctness đều có rủi ro.

Một thiết kế đáng tin cậy phải:

- Chỉ ack khi work hoàn tất theo contract.
- Hoặc ghi durable inbox/work item trước khi ack Kafka.
- Giới hạn số in-flight tasks.
- Dùng idempotency cho redelivery.
- Drain/cancel tasks có kiểm soát khi shutdown.

Không dùng một queue in-memory không giới hạn như durable retry store.

## 14. Producer buffers khi publish retry hoặc DLT

Khi recoverer gửi record sang retry topic/DLT, producer có thể giữ serialized records trong accumulator/buffer cho đến khi broker nhận hoặc delivery timeout xảy ra.

Các cấu hình liên quan:

- `buffer.memory`: memory budget của producer accumulator.
- `batch.size`: kích thước batch theo partition.
- `linger.ms`: thời gian chờ để gom batch.
- `max.block.ms`: thời gian `send()` có thể block khi chờ metadata/buffer.
- `delivery.timeout.ms`: giới hạn thời gian delivery theo producer semantics.
- `max.request.size`: giới hạn request size phía producer.

Ví dụ Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        buffer.memory: 33554432
        batch.size: 16384
        linger.ms: 5
        max.block.ms: 60000
        delivery.timeout.ms: 120000
~~~

Các giá trị là ví dụ, không phải recommendation chung. Nếu nhiều consumers cùng phát sinh DLT/retry sends trong outage, producer buffers có thể tăng cùng lúc với retained consumer records.

### 14.1. Memory của producer và consumer cộng dồn

Một service vừa consume vừa publish retry/DLT có thể giữ:

- Consumer fetch buffers.
- Retained records từ listener failure.
- Deserialized payload objects.
- Producer accumulator buffers cho retry/DLT sends.
- Send futures/callback state.
- Serialization temporary buffers.

Sizing pod chỉ theo `-Xmx` và `max.poll.records` mà bỏ producer buffers là chưa đầy đủ.

### 14.2. Send result phải được xử lý đúng

Không coi gọi `KafkaTemplate.send()` là record đã được lưu bền vững. Với `DeadLetterPublishingRecoverer`, cấu hình kiểm tra send result theo khả năng version hỗ trợ, ví dụ `setFailIfSendResultIsError(true)`, và đặt timeout phù hợp.

Nếu DLT publish thất bại, recovery phải được coi là thất bại theo policy. Đừng ack record nguồn chỉ để giải phóng memory khi chưa có nơi lưu bền vững cho nó.

## 15. Deserialization, conversion và payload size

Memory retention có thể tăng mạnh nếu deserializer tạo object graph lớn hoặc converter tạo thêm bản sao.

Các câu hỏi cần trả lời:

- Listener nhận `ConsumerRecord<K,V>`, DTO hay batch?
- Deserializer tạo object gì và có copy bytes không?
- JSON parser tạo tree trung gian trước DTO không?
- Message converter có tạo String/byte[] mới không?
- Listener có giữ payload trong cache hoặc closure không?
- Exception có giữ reference tới payload/context không?
- Logging/tracing có serialize payload lần nữa không?

### 15.1. Tránh giữ record trong exception/custom cache

Một custom exception có thể giữ toàn bộ DTO làm field để điều tra. Nếu retry state hoặc error queue giữ exception lâu, payload graph vẫn sống.

Thường chỉ cần ghi metadata an toàn như event ID, topic, partition, offset và exception category. Nếu cần giữ raw payload, dùng durable quarantine/DLT với access controls và retention, không giữ trong heap vô hạn.

### 15.2. Payload lớn nên có contract rõ

Đặt giới hạn payload size ở producer/schema/API contract. Với file hoặc blob lớn, cân nhắc lưu object ở object storage và chỉ gửi reference + checksum/metadata qua Kafka.

Điều này giảm memory, network và broker storage, nhưng cần lifecycle/authorization cho external object và bảo đảm object tồn tại trong thời gian record cần replay.

## 16. Batch listener và memory khi một record lỗi

Batch listener có thể giữ nhiều records trong cùng invocation. Nếu một record gây exception, error handler cần biết record nào thất bại hoặc phải xử lý batch retry theo semantics được cấu hình.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders.bulk",
    groupId = "orders-bulk"
)
public void consume(List<ConsumerRecord<String, OrderEvent>> records) {
    for (ConsumerRecord<String, OrderEvent> record : records) {
        bulkService.process(record.value());
    }
}
~~~

Một batch có 500 records; nếu record thứ 490 lỗi, những records trước đó có thể đã tạo side effects, còn các records phía sau chưa xử lý. Retry toàn batch có thể làm nhiều records được gọi lại.

Memory concerns:

- Toàn bộ batch list còn reachable.
- Payload DTOs trong batch vẫn còn sống.
- Temporary processing results có thể được giữ trong list/map.
- Retry/recovery logic có thể cần giữ references tới records còn lại.
- Error objects có thể giữ stack/context.

### 16.1. Batch size cần dựa trên bytes và objects

`max.poll.records=500` không đảm bảo batch luôn nhỏ. Một batch 500 records nhỏ khác hoàn toàn 500 records có payload vài trăm KB.

Đo batch heap footprint ở percentile cao và chọn giới hạn phù hợp. Nếu payload size rất biến động, có thể cần giới hạn message size ở producer/schema layer hoặc tách large payload khỏi Kafka.

### 16.2. Batch failure semantics

Batch listener có thể ném `BatchListenerFailedException` để chỉ rõ record index thất bại trong những API hỗ trợ. Cách xử lý retry/seek/recover phụ thuộc handler và version.

Đừng tự giữ một bản copy toàn batch trong application cache để “retry sau” nếu container đã có cơ chế error handling. Điều đó có thể nhân đôi memory mà không cải thiện reliability.

## 17. Backpressure khi downstream lỗi

Nếu một database hoặc HTTP dependency ngừng hoạt động, nhiều records có thể liên tục thất bại và bước vào retry. Khi đó có ba lựa chọn tổng quát:

1. **Retry ngắn có giới hạn:** phù hợp transient failures.
2. **Pause/backpressure:** giảm intake trong lúc chờ dependency.
3. **Retry topic/durable queue:** chuyển pending work ra khỏi heap của consumer.

Một mô hình circuit breaker:

~~~text
Listener failure rate tăng
       |
       v
Classify exception
       |
       +-- transient, short outage --> bounded retry
       |
       +-- downstream unavailable --> pause / backpressure
       |
       +-- long delay needed --> retry topic
       |
       +-- permanent payload error --> DLT/quarantine
~~~

Không pause vì mọi exception. Lỗi payload không hợp lệ có thể được recovery sang DLT ngay nếu DLT khỏe mạnh; lỗi dependency kéo dài có thể cần backpressure để tránh retry storm.

### 17.1. Pause không tự giải phóng retained records

Nếu container đang giữ records trong memory để resubmit, gọi `pause()` không đồng nghĩa những references đó biến mất. Pause kiểm soát việc nhận/delivery records; memory được giải phóng khi references không còn reachable và GC thu hồi.

Cần xác định chính xác error handler/container state trước khi cho rằng pause sẽ làm heap giảm.

### 17.2. Pause scope

Một child consumer bị lỗi không nhất thiết yêu cầu pause toàn bộ listeners trong JVM. Chọn container/partition scope theo dependency và ordering. Nếu dependency dùng chung toàn service và tất cả consumers phụ thuộc nó, service-level gate có thể phù hợp hơn.

## 18. GC và dấu hiệu memory pressure

Khi records được giữ lâu, GC không thể thu hồi chúng dù application không còn xử lý record ở thời điểm đó. Heap occupancy có thể duy trì ở mức cao qua nhiều GC cycles.

Các biểu hiện:

- Old generation occupancy tăng.
- Mixed/full GC thường xuyên hơn.
- GC pause kéo dài.
- Allocation rate tăng khi retry tạo exception/transformation objects.
- Promotion failure hoặc evacuation failure.
- Container bị OOMKilled do vượt memory limit của pod.
- Producer buffer/fetch buffers cạnh tranh heap với application objects.

### 18.1. Heap dump và dominator tree

Khi có memory incident, heap dump có thể cho biết object graph nào giữ memory:

- `ConsumerRecord` / payload DTOs.
- `ArrayList` hoặc batch collections.
- Byte arrays / Strings.
- Retry state/cache entries.
- Executor queue tasks.
- Producer accumulator/buffers.
- Application caches hoặc closures.

Dominator tree cho biết object nào giữ references tới nhiều objects khác. Đây là cách tìm retained set thực tế tốt hơn chỉ suy đoán từ cấu hình.

Heap dump có thể chứa payload nhạy cảm. Thu thập, lưu trữ và chia sẻ theo chính sách bảo mật; tránh để file dump ở nơi truy cập công khai.

### 18.2. Heap không phải toàn bộ container memory

Kubernetes memory limit bao gồm nhiều vùng ngoài Java heap: metaspace, code cache, thread stacks, direct buffers, native memory, mmap và process overhead.

Nếu `-Xmx` đặt sát pod memory limit, Kafka client/direct buffers hoặc native allocations có thể làm container bị OOMKilled dù heap chưa chạm max.

Để sizing, cần headroom cho non-heap và OS/container overhead.

## 19. Metrics nên theo dõi cho retry memory

Một dashboard capacity nên kết hợp application, JVM và Kafka metrics.

| Metric | Ý nghĩa |
|---|---|
| JVM heap used / max | Mức sử dụng heap |
| Old-gen occupancy | Objects sống lâu/retained |
| Allocation rate | Tốc độ tạo objects |
| GC pause duration/count | Chi phí thu hồi memory |
| Process/container RSS | Memory thực tế của process |
| Direct buffer pool used | Native/direct memory của buffers |
| Records per poll | Số records nhận mỗi poll |
| Batch size bytes | Tổng payload bytes của batch |
| Retained retry record count | Số records đang được giữ để retry, nếu instrument được |
| Retry duration / attempts | Lifetime và tần suất retry |
| In-flight listener count | Công việc đang chạy |
| Executor queue depth | Tasks đang chờ |
| Producer buffer available/wait | Producer memory pressure |
| Consumer lag / oldest record age | Backlog bên broker |
| DLT/retry publish failures | Đường offload retry có khỏe không |

Các metric như `retained_retry_record_count` có thể cần custom instrumentation; không mặc định Spring Kafka expose sẵn mọi giá trị internal retained collection.

### 19.1. Metric về thời gian giữ record

Nếu ứng dụng cần biết memory retention kéo dài bao lâu, có thể instrument thời điểm record vào retry flow và thời điểm retry/recovery hoàn tất. Không cần lưu toàn bộ payload trong metric state; lưu metadata nhỏ theo bounded cache hoặc phát event/metric phù hợp.

Cẩn thận với event ID làm metric tag vì cardinality cao. Event ID nên ở log/trace nếu policy cho phép.

### 19.2. Correlate memory với retry

Một timeline có ý nghĩa:

~~~text
10:00 downstream DB bắt đầu chậm
10:02 retry attempts tăng
10:03 retained retry records tăng
10:04 old-gen occupancy tăng
10:05 GC pause p99 tăng
10:06 consumer lag tăng
10:08 circuit breaker mở / listener pause
10:12 DB phục hồi, retry tiếp tục
10:15 heap và lag giảm dần
~~~

Nếu heap tăng trước khi retry rate tăng, có thể nguyên nhân nằm ở cache hoặc workload khác. Correlation giúp đặt giả thuyết; heap dump và thread dump mới xác nhận references.

## 20. Cấu hình mẫu cho retained records có giới hạn

Một ví dụ cấu hình listener factory và error handler:

~~~java
@Configuration
public class RetryMemoryConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        var properties = factory.getContainerProperties();
        properties.setPollTimeout(1_000L);

        return factory;
    }

    @Bean
    public CommonErrorHandler commonErrorHandler(
            DeadLetterPublishingRecoverer recoverer) {

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(2_000L, 2L)
                );

        // Chỉ dùng trên version hỗ trợ và sau khi đã sizing retained batch.
        handler.setSeekAfterError(false);

        return handler;
    }
}
~~~

Đoạn code minh họa retain mode. Các constructor/imports và API phải khớp Spring Kafka version. Trong production, factory còn cần các cấu hình serializer, transaction, error handler, observation và consumer properties phù hợp.

**Đây không phải một cấu hình “an toàn mặc định” cho mọi payload.** Khi bật `seekAfterError=false`, phải sizing retained records và kiểm tra behavior dưới batch/concurrency/outage.

### 20.1. Seek-based alternative

Nếu muốn container seek để fetch lại thay vì giữ records trong memory qua retry, giữ `seekAfterError` ở behavior mặc định của version hoặc cấu hình rõ theo API được hỗ trợ.

Đừng bật retain mode chỉ vì muốn tránh broker fetch; re-fetch thường là trade-off hợp lý nếu memory headroom là ràng buộc chính.

### 20.2. Giới hạn số records

Ví dụ consumer properties:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      properties:
        max.poll.records: 100
        max.partition.fetch.bytes: 1048576
        fetch.max.bytes: 52428800
~~~

Các giá trị phải được chọn cùng payload limits và concurrency. Không coi fetch byte limits là hard heap cap, như đã giải thích ở phần trên.

## 21. Sizing memory cho pod Spring Kafka

Một cách lập ngân sách:

~~~text
Pod memory limit
  >= JVM heap budget
   + metaspace / code cache
   + thread stacks
   + direct/native buffers
   + OS/container overhead
   + safety headroom

JVM heap budget
  >= application baseline
   + consumer fetch buffers
   + retained/retry records
   + active listener object graphs
   + executor queues
   + producer buffers and callbacks
   + caches/framework state
   + GC headroom
~~~

Không đặt `-Xmx` bằng toàn bộ pod memory limit. Chừa khoảng cho native/direct memory, thread stacks và process overhead.

### 21.1. Tính theo instance, không theo cluster tổng

Giả sử cluster có 12 consumer instances nhưng mỗi pod có memory limit 1 GiB. Không thể lấy tổng heap của 12 pods chia trung bình để kết luận một pod đủ memory.

Một partition hotspot hoặc rebalance có thể khiến một pod tạm thời có nhiều records/assignments hơn dự kiến. Sizing phải dựa trên per-pod peak, concurrency và worst-case assignment.

### 21.2. Headroom khi rebalance

Trong rebalance, assignment thay đổi và consumer có thể fetch/process records từ partitions mới. Các references của poll/batch cũ, in-flight work và new fetch activity có thể chồng lấp trong một khoảng ngắn tùy lifecycle.

Không chỉ benchmark steady-state. Kiểm tra memory peak khi deploy rolling, restart, partition reassignment và dependency outage.

## 22. Outage kéo dài: giữ trong heap hay chuyển sang durable retry?

Nếu downstream outage kéo dài 30 phút, giữ nhiều records trong consumer heap có thể không còn là chiến lược tốt. Cần cân nhắc nơi lưu pending work.

| Strategy | Pending data nằm ở đâu? | Ưu điểm | Chi phí/rủi ro |
|---|---|---|---|
| In-memory retain | Consumer JVM heap | Tránh re-fetch, thao tác nhanh | Heap pressure, mất state khi crash |
| Seek/re-fetch | Kafka source topic + client fetch | Giảm retained collection lifetime | Fetch lại, consumer vẫn phải retry |
| Retry topic | Kafka broker log | Backoff dài không giữ source record trong heap | Extra produce/consume, disk/network, ordering |
| Durable outbox/inbox | Database/storage | Bền vững và có thể điều phối | DB capacity, duplicate/reconciliation |
| DLT/quarantine | Kafka topic hoặc durable store | Giữ payload lỗi để điều tra/replay | Cần write success, ACL, retention và replay policy |

Không dùng in-memory retain làm durable storage. Process crash hoặc pod OOM có thể làm mất retry state trong memory; Kafka committed offsets quyết định record nào sẽ được giao lại.

### 22.1. Source retention vẫn quan trọng

Với seek/re-fetch, record phải còn trong Kafka source topic khi consumer quay lại. Nếu outage kéo dài hơn retention và record bị xóa trước khi đọc lại, consumer không thể fetch lại dữ liệu đã hết hạn.

Theo dõi oldest unprocessed event age, topic retention, consumer lag và outage duration. Retry topics cũng có retention riêng cần đủ dài cho thời gian chờ và operational recovery.

### 22.2. Retry topic không tự bảo đảm exactly-once

Republish sang retry topic rồi crash trước khi source offset commit có thể tạo duplicate retry records khi source được đọc lại. Cần idempotency, original topic/partition/offset metadata và consumer deduplication khi phù hợp.

## 23. Ordering và partition semantics khi retry

Giữ record trong memory hoặc seek lại có thể ảnh hưởng thứ tự giao record trong partition theo handler/container behavior. Retry topics có thể cho phép source partition tiếp tục trong khi record lỗi đang chờ.

Hãy xác định requirement:

- Có cần strict ordering toàn partition không?
- Có thể xử lý các records khác key song song không?
- Một record lỗi có chặn các records phía sau không?
- Có thể retry theo key/aggregate sequence không?
- Replay có thể chạy sau event mới hơn không?

Nếu nghiệp vụ cần thứ tự theo aggregate, một memory optimization làm record lỗi được xử lý muộn hơn có thể tạo state transition sai. Cần sequence/version checks và idempotency.

### 23.1. Không skip để giảm heap

Không ack/commit một record lỗi chỉ để giải phóng batch khỏi memory nếu chưa có durable recovery. Điều đó có thể làm record biến mất khỏi source processing path.

Nếu quyết định quarantine/skip theo business policy, phải lưu record bền vững, audit và chỉ sau đó mới hoàn tất recovery theo semantics được định nghĩa.

## 24. Những sai lầm thường gặp

**Dùng serialized size để tính heap.** Deserialization, object graph, copies và batch wrappers làm footprint khác xa bytes trên Kafka.

**Bật `seekAfterError=false` mà không tính retained batch.** Records chưa xử lý có thể sống trong heap suốt backoff/retry.

**Cho rằng mỗi retry tạo một bản copy đầy đủ.** Cùng object references có thể được resubmit; đo retained set thật thay vì nhân attempts máy móc.

**Cho rằng seek nghĩa memory bằng zero.** Consumer fetch buffers và current poll objects vẫn dùng memory.

**Chỉ giảm `max.poll.records`.** Fetcher buffers, payload size, concurrency, producer buffers và executor queues vẫn có thể làm heap/native memory cao.

**Coi `max.partition.fetch.bytes` là hard heap limit.** Kafka có behavior cho batch đầu tiên để bảo đảm progress; deserialized objects còn lớn hơn bytes.

**Tăng concurrency để xử lý backlog mà không tính heap.** Nhiều child consumers đồng nghĩa thêm fetch buffers, batches và in-flight objects.

**Dùng backoff dài trên retained records mà không theo dõi heap.** Record lifetime tăng và GC không thể thu hồi objects còn reachable.

**Dùng unbounded executor queue.** Listener có thể ack nhanh trong khi task queue giữ vô hạn payloads.

**Chờ producer send vô hạn khi DLT outage.** Producer buffers và retained source records có thể cùng tăng.

**Dùng retry topics nhưng quên broker capacity.** Heap giảm nhưng disk/network/metadata/consumer load tăng.

**Nuốt exception để listener return thành công.** Offset có thể được commit dù output/recovery chưa bền vững.

**Ack trước khi async task hoàn tất.** Memory queue và delivery semantics trở nên không an toàn.

**Giữ exception chứa payload lớn trong retry cache.** Stack/context references có thể giữ cả object graph.

**Không có upper bound cho stateful retry cache.** Entries tích lũy qua thời gian và process lifetime.

**Để `-Xmx` sát container memory limit.** Direct buffers, metaspace và thread stacks có thể làm pod OOMKilled.

**Không test outage kéo dài.** Steady-state memory không phản ánh retained records khi dependency lỗi.

**Dựa vào heap usage trung bình.** P99 payload và batch size mới quyết định peak memory.

**Skip record để giải phóng memory.** Có thể làm mất dữ liệu và phá offset ordering.

## 25. Runbook khi heap tăng trong lúc retry

### Giai đoạn A — Xác định retry mode

1. Xác định listener ID, group, topic và consumer concurrency.
2. Xác định handler đang dùng: `DefaultErrorHandler`, custom handler hay retry topics.
3. Kiểm tra `seekAfterError` và behavior theo đúng Spring Kafka version.
4. Ghi backoff, attempts, max.poll.records và fetch byte limits.
5. Xác định records đang được retained, seek/re-fetch hay publish ra retry/DLT.
6. Xác định dependency đang làm listener thất bại.

### Giai đoạn B — Xác định memory owner

1. Xem heap used/max và old-gen occupancy.
2. Xem GC logs, allocation rate và pause duration.
3. Thu heap dump nếu được phép và an toàn.
4. Xem dominator tree cho ConsumerRecord, DTO, byte arrays, lists, retry caches và executor queues.
5. Kiểm tra producer buffer/direct memory.
6. So sánh số records per poll, payload sizes và concurrency.
7. Xem memory peak theo pod, không chỉ cluster average.

### Giai đoạn C — Ổn định intake

1. Khắc phục downstream nếu có thể.
2. Giảm `max.poll.records` hoặc batch size theo kế hoạch nếu retained batches quá lớn.
3. Giảm concurrency nếu tổng per-pod buffers/records vượt budget.
4. Dùng pause/backpressure khi cần ngừng intake, nhưng không giả định pause giải phóng retained records.
5. Cân nhắc seek/re-fetch hoặc retry topics cho backoff dài nếu semantics phù hợp.
6. Giới hạn executor queues và retry state caches.
7. Bảo đảm DLT/retry publish failure không bị coi là recovery success.

### Giai đoạn D — Phục hồi và xác minh

1. Resume theo policy khi dependency phục hồi.
2. Theo dõi heap/old-gen/GC khi records được retry.
3. Xác nhận committed offsets và consumer lag tiến triển.
4. Kiểm tra duplicate side effects và idempotency.
5. Theo dõi retry topic/DLT ingress và backlog.
6. Chờ heap trở lại baseline sau khi retained references được giải phóng.
7. Cập nhật capacity model bằng measurements từ incident.

Không kết luận memory leak chỉ vì heap chưa giảm ngay sau khi retry kết thúc. GC có thể chưa chạy, hoặc JVM giữ committed heap để tái sử dụng. Cần xem live set/GC behavior và heap dump.

## 26. Integration và load tests cho retry memory

Một unit test chỉ kiểm tra listener ném exception không đủ chứng minh memory behavior của container. Cần integration/load test với Kafka broker và payloads có kích thước đại diện.

### 26.1. Kiểm tra seek behavior

1. Tạo topic nhiều partitions.
2. Cấu hình record listener và `DefaultErrorHandler`.
3. Gửi batch records với một record được thiết kế để fail.
4. Xác nhận handler seek/redelivery theo policy.
5. Đo consumer fetches và listener attempts.
6. Theo dõi heap sau khi current poll references được giải phóng.
7. Xác nhận không có offset bị commit vượt record chưa recovery.

### 26.2. Kiểm tra retain mode

1. Dùng version hỗ trợ `seekAfterError=false`.
2. Cấu hình `max.poll.records` và concurrency cố định.
3. Gửi records có payload size biết trước.
4. Làm một record fail và giữ backoff đủ dài để quan sát.
5. Đo heap occupancy và retained objects.
6. Xác nhận container vẫn duy trì poll/liveness theo cơ chế.
7. Cho retry thành công và theo dõi references được giải phóng sau đó.

Không assert một số byte heap tuyệt đối trong mọi CI run vì GC/JVM/environment gây biến động. So sánh xu hướng, retained object counts và giới hạn capacity trong môi trường ổn định.

### 26.3. Payload size distribution

Test với:

- Small payload.
- Typical payload.
- P95 payload.
- P99/maximum allowed payload.
- Compressed payload có expansion ratio lớn.
- Payload deserialize thành object graph nhiều nested objects.

Xác nhận memory peak nằm trong budget ở concurrency và batch size mục tiêu.

### 26.4. Batch listener failure

Gửi batch lớn rồi làm record ở giữa batch fail. Kiểm tra batch retry semantics, record ordering, side effects đã xảy ra trước lỗi và heap retention. Dùng idempotency để kiểm tra records được gọi lại không nhân đôi business effects.

### 26.5. Long outage

Làm downstream dependency unavailable trong khoảng thời gian đủ dài để tạo backlog/retries.

Quan sát:

- Retained record count/heap.
- Old-gen occupancy và GC pauses.
- Consumer lag.
- Retry attempts và duration.
- Container poll/group membership.
- DLT/retry topic producer behavior.
- Recovery sau khi dependency hoạt động lại.

Đây là bài test quan trọng nhất vì memory pressure thường xuất hiện khi nhiều records cùng bị giữ trong outage, không phải trong một retry đơn lẻ.

### 26.6. OOM/restart recovery

Trong môi trường test cô lập, restart consumer process khi records đang retry. Xác nhận Kafka committed offsets cho phép redelivery cần thiết, side effects idempotent và retry state in-memory không được xem là durable.

Không cố tình gây OOM trong production để kiểm thử. Dùng staging với resource limits tương tự và payload/throughput đã kiểm soát.

## 27. Capacity review trước khi thay đổi retry policy

Trước khi tăng backoff, concurrency hoặc `max.poll.records`, hãy tính lại:

1. Heap footprint của payload sau deserialize.
2. P95/P99 payload size và batch size.
3. Số consumer children thực tế trên một pod.
4. Số records có thể được giữ đồng thời trong retry.
5. Backoff duration và outage duration cần chịu đựng.
6. Producer buffer budget nếu publish retry/DLT.
7. Executor queue depth và in-flight tasks.
8. JVM non-heap/direct memory.
9. Pod/container memory limit và safety headroom.
10. Kafka source/retry topic retention.
11. Consumer lag catch-up capacity sau recovery.
12. Ordering/idempotency requirements.

Một policy retry chỉ được xem là phù hợp khi nó vừa bảo vệ delivery semantics vừa nằm trong memory/broker capacity thực tế.

### 27.1. Bảng quyết định nhanh

| Điều kiện | Hướng cân nhắc |
|---|---|
| Payload nhỏ, retry ngắn, batch nhỏ | Blocking retry có thể đủ |
| Payload lớn, heap headroom thấp | Ưu tiên giới hạn batch; cân nhắc seek/re-fetch |
| Backoff dài | Container pausing backoff hoặc retry topics tùy semantics |
| Downstream outage kéo dài | Backpressure và durable retry thay vì giữ heap vô hạn |
| Strict per-partition ordering | Thiết kế blocking/partition-level policy cẩn thận |
| Nhiều consumers trong một JVM | Tính tổng fetch/retained memory trên tất cả child containers |
| Async listener | Bounded queue và ack sau completion/durable enqueue |
| DLT producer có thể lỗi | Kiểm tra send result, giữ offset an toàn, không skip |
| Payload có thể rất lớn | Giới hạn contract hoặc lưu blob ngoài Kafka |
| Stateful retry | Cache bounded, TTL và cleanup rõ |

## 28. Các câu hỏi code review

Khi review một listener có retry, hỏi:

- Error handler là `DefaultErrorHandler` hay custom?
- `seekAfterError` đang là true hay false theo effective config?
- Nếu retain mode, tối đa bao nhiêu records có thể được giữ?
- Batch listener hay record listener? Batch có thể lớn đến đâu?
- Payload serialized size và deserialized heap size đã được đo chưa?
- `max.poll.records`, `fetch.max.bytes` và `max.partition.fetch.bytes` có phù hợp không?
- Concurrency trên mỗi pod là bao nhiêu?
- Backoff tối đa là bao lâu?
- Backoff dài có dùng container pausing handler phù hợp không?
- Retry có thể chuyển sang retry topic để tránh giữ heap lâu không?
- Application có unbounded executor/cache nào giữ payload không?
- Producer retry/DLT buffer có được tính trong memory budget không?
- DLT send result có được xác nhận trước khi recovery thành công không?
- Consumer offset có thể bị commit sớm không?
- Rebalance/restart có thể tạo redelivery và duplicate side effects không?
- Heap/GC metrics và retained objects có được theo dõi không?
- Có long-outage/load test với payload P99 không?

Nếu chưa trả lời được số records tối đa có thể cùng tồn tại trong memory, chưa đủ cơ sở để tăng concurrency hoặc bật retain mode trong production.

## 29. Tài liệu tham chiếu theo phiên bản

Đối chiếu tài liệu đúng Spring Kafka/Kafka client version:

- **Spring for Apache Kafka Reference — Handling Exceptions**: `DefaultErrorHandler`, seeks, retries, recovery và `seekAfterError`.
- **Spring Kafka Javadoc — `DefaultErrorHandler`**: retry/backoff configuration, `setSeekAfterError` và recovery behavior.
- **Spring Kafka Reference — Container Pausing**: `ContainerPausingBackOffHandler` và backoff dài.
- **Spring Kafka Reference — Non-blocking Retries / Retryable Topics**: republish sang retry topics, delays và DLT.
- **Spring Kafka Reference — Listener Containers and Batch Listeners**: record/batch delivery, concurrency và poll behavior.
- **Apache Kafka Consumer Configs**: `max.poll.records`, `fetch.max.bytes`, `max.partition.fetch.bytes`, `max.poll.interval.ms`.
- **Apache Kafka Producer Configs**: `buffer.memory`, `batch.size`, `linger.ms`, `max.block.ms`, `delivery.timeout.ms`.
- **Java Virtual Machine documentation**: heap, garbage collection, object allocation và memory diagnostics.
- **Micrometer/Spring Boot Actuator documentation**: JVM memory, GC, executor và Kafka client metrics.
- **Kubernetes resource documentation**: container memory requests/limits và OOMKilled behavior.

Các API, defaults và retry semantics có thể thay đổi giữa Spring Kafka releases. Đặc biệt, xác nhận `seekAfterError=false` và retain/resubmit behavior trên đúng version trước khi dựa vào nó cho capacity planning.

**Kết luận kỹ thuật:** giữ record để retry có thể làm tăng thời gian object tồn tại trong heap, nhất là khi dùng retain/resubmit, batch lớn, payload lớn, concurrency cao hoặc backoff dài. Hãy sizing theo **deserialized heap footprint và số records đồng thời**, kiểm soát `max.poll.records`, fetch limits, executor queues và producer buffers, đồng thời cân nhắc seek/re-fetch hoặc retry topics khi outage/backoff dài. Mục tiêu là bảo toàn retry và offset semantics trong một memory budget có giới hạn, không biến consumer heap thành kho lưu trữ vô hạn.

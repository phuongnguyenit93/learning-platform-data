# Benchmark theo tải thực tế

Benchmark Kafka có ý nghĩa khi workload thử nghiệm gần với workload mà hệ thống sẽ nhận trong production. Một bài đo chỉ gửi record 1 KB liên tục vào broker có thể cho biết giới hạn producer/broker ở một cấu hình cụ thể, nhưng chưa chứng minh ứng dụng Spring Kafka có thể xử lý đơn hàng, thanh toán hoặc event có payload thật với latency và độ tin cậy yêu cầu.

Benchmark thực tế phải đo cả đường đi: tạo event, serialize, gửi qua `KafkaTemplate`, broker nhận và replicate, consumer poll, deserialize, listener xử lý, gọi dependency và hoàn tất side effect. Đồng thời cần quan sát throughput, p95/p99 latency, consumer lag, lỗi, tài nguyên và tính đúng đắn của dữ liệu. Mục tiêu không phải tìm một con số records/second lớn nhất trong điều kiện lý tưởng; mục tiêu là xác định tải mà hệ thống duy trì được trong các SLO đã thống nhất.

## 1. Vì sao benchmark theo tải thực tế?

Một kết quả benchmark chỉ có giá trị trong phạm vi môi trường và workload đã dùng để đo. Nếu payload, key distribution, replication factor, acknowledgement, consumer concurrency hoặc dependency khác production, kết quả có thể dẫn tới quyết định sizing sai.

Ví dụ hai producer cùng gửi 20.000 record/giây nhưng tạo tải rất khác nhau:

| Đặc điểm | Workload A | Workload B |
|---|---|---|
| Payload | Chuỗi cố định 100 byte | JSON event trung bình 3 KB, có nested object |
| Key | Phân bố đều | 20% key chiếm 80% traffic |
| Compression | Không | LZ4 |
| Acknowledgement | `acks=1` | `acks=all`, replication factor 3 |
| Consumer | Chỉ poll và bỏ record | Deserialize, gọi database và cập nhật projection |
| Kết quả được đo | Broker nhận record | Event hoàn tất nghiệp vụ |

Không thể kết luận hai workload có cùng năng lực xử lý chỉ vì records/second bằng nhau. Benchmark phải mô tả rõ nó đo tầng nào và có bao gồm các bước nghiệp vụ nào.

## 2. Xác định mục tiêu và SLO trước khi chạy

Trước khi thay đổi cấu hình, hãy viết mục tiêu định lượng. Ví dụ minh họa:

| Chỉ tiêu | Mục tiêu ví dụ |
|---|---:|
| Throughput bình thường | 8.000 event/s |
| Peak trong 5 phút | 15.000 event/s |
| End-to-end latency p95 | Dưới 250 ms |
| End-to-end latency p99 | Dưới 700 ms |
| Consumer lag khi tải ổn định | Không tăng liên tục |
| Tỷ lệ publish lỗi | Dưới 0,01% |
| Tỷ lệ event bị mất | 0 trong bài audit |
| Recovery sau khi broker restart | Trở lại SLO trong 2 phút |

Các con số trên chỉ là ví dụ để minh họa cách đặt mục tiêu; mỗi hệ thống cần chọn SLO theo nghiệp vụ và hạ tầng thực tế. Ghi rõ cửa sổ đo, percentile, phạm vi topic/partition và cách tính lỗi. Không dùng một mục tiêu throughput tổng mà bỏ qua latency hoặc lag.

Hãy phân biệt ba loại mục tiêu:

- **Capacity target:** mức tải hệ thống cần phục vụ trong điều kiện bình thường và peak.
- **Performance SLO:** latency, error rate và lag cần duy trì ở mức tải đó.
- **Resilience target:** hệ thống phải phục hồi ra sao khi broker, consumer, database hoặc network gặp sự cố.

Một cấu hình chỉ được xem là đạt nếu đồng thời đáp ứng các mục tiêu quan trọng, không phải chỉ đạt throughput.

## 3. Mô hình hóa workload trước khi tạo tải

Workload model là mô tả có thể tái lập của traffic thực tế. Ít nhất cần ghi lại:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Arrival rate | Trung bình, peak và burst có bao nhiêu event/giây? |
| Payload size | Kích thước p50, p95, p99 và tối đa là bao nhiêu byte? |
| Payload shape | JSON đơn giản, nested object, binary, Avro/Protobuf hay nhiều event type? |
| Key distribution | Key phân bố đều hay có hot key/tenant lớn? |
| Topic topology | Có bao nhiêu topic, partition và replication factor? |
| Consumer groups | Có bao nhiêu group đọc cùng topic? |
| Processing cost | Listener chỉ validate hay gọi database, HTTP, cache hoặc nhiều service? |
| Ordering | Có cần giữ thứ tự theo key hoặc partition không? |
| Reliability | `acks`, idempotence, transaction và retry policy nào đang bật? |
| Retention | Dữ liệu được giữ bao lâu và tốc độ ghi tạo ra dung lượng nào? |
| Failure profile | Có lỗi dependency, retry, DLT hoặc rebalance trong workload không? |

Đừng chỉ lấy payload trung bình. Payload lớn ở p99 có thể làm tăng batch size, network throughput, serialization time và memory pressure. Tương tự, traffic trung bình đều không mô phỏng được burst theo giờ mở cửa, campaign hoặc batch import.

## 4. Tính tải record và tải byte

Throughput theo record và theo byte trả lời hai câu hỏi khác nhau. Nếu trung bình có `R` record/giây và kích thước payload trung bình là `S` byte thì tốc độ payload xấp xỉ:

\[
\text{Payload bytes/s} = R \times S
\]

Ví dụ 10.000 record/s với payload 2.048 byte tương đương khoảng 20,48 MB/s payload trước khi tính protocol overhead, batch framing, compression và replication traffic.

Khi sizing cluster, cần xem thêm:

- Kích thước batch và mức độ nén thực tế.
- Replication factor và lượng traffic giữa broker.
- Số consumer group đọc cùng dữ liệu.
- Traffic fetch từ broker tới từng consumer group.
- Retention và tốc độ tăng dung lượng log.
- Traffic cross-zone/cross-rack nếu cluster trải trên nhiều zone.

Không nhân payload bytes/s với replication factor rồi coi đó là network usage chính xác. Đây chỉ là một ước lượng sơ bộ; replication, compression, batching, fetch và placement làm thay đổi lượng byte thực tế.

## 5. Phân bố key và hot partition

Producer thường dùng key để các event liên quan được ghi vào cùng partition. Điều này giữ ordering theo key, nhưng key distribution không đều có thể tạo hot partition.

Ví dụ 12 partition có thể nhận tải trung bình 1.000 record/s mỗi partition nếu phân bố đều. Nếu một tenant lớn chiếm 50% traffic và key của tenant luôn map vào một partition, partition đó có thể nhận gần một nửa toàn bộ traffic trong khi các partition còn lại nhàn hơn.

Benchmark cần giữ phân bố key gần production:

- Số lượng key khác nhau và tần suất xuất hiện của mỗi key.
- Tỷ lệ key nóng nhất và top 10 key.
- Key null hoặc record không có key nếu hệ thống có trường hợp này.
- Partitioning strategy và partition count.
- Sự thay đổi phân bố key khi tăng partition count.

Không chỉ quan sát tổng throughput. Xem lag, bytes và records per partition để phát hiện một partition đã bão hòa trong khi tổng cluster vẫn còn tài nguyên.

## 6. Định nghĩa chính xác các chỉ số

### Throughput

Nên đo riêng:

1. **Generated rate:** số event load generator tạo ra mỗi giây.
2. **Producer accepted rate:** số record được producer xác nhận gửi thành công.
3. **Broker ingress rate:** số record/byte broker nhận vào topic.
4. **Consumer delivery rate:** số record consumer poll và giao cho listener.
5. **Business completion rate:** số event hoàn tất side effect nghiệp vụ.

Các rate này có thể khác nhau. Nếu producer tạo 10.000 event/s nhưng listener chỉ hoàn tất 8.000 event/s, lag sẽ tăng dù producer send vẫn thành công.

### Latency

Đo latency tại các ranh giới:

| Latency | Điểm bắt đầu/kết thúc | Ý nghĩa |
|---|---|---|
| Producer enqueue | Gọi `send()` đến khi method trả về | Thời gian ứng dụng đưa record vào producer buffer; chưa phải broker ack |
| Producer ack | Gọi `send()` đến callback/future hoàn tất | Thời gian serialize, chờ buffer, network, broker và acknowledgement |
| Broker request | Broker nhận request đến khi response | Chi phí xử lý request phía broker |
| Consumer fetch | Gửi fetch đến khi có response | Thời gian fetch và chờ dữ liệu |
| Listener duration | Listener bắt đầu đến khi method hoàn tất | Chi phí xử lý trong consumer application |
| End-to-end | Event được tạo đến khi side effect hoàn tất | Trải nghiệm thực tế của nghiệp vụ |

Latency trung bình không đủ để đánh giá. Luôn xem p50, p95, p99 và max; p99 có thể xấu đi mạnh khi thread pool, connection pool hoặc broker queue gần bão hòa.

### Consumer lag

Consumer lag theo record thường được tính từ log end offset trừ vị trí consumer đã đọc hoặc committed offset, tùy công cụ. Phải ghi rõ loại offset đang dùng. Lag theo record không nói trực tiếp event đã chờ bao lâu; một lag 5.000 record với payload nhỏ và tốc độ xử lý cao khác hoàn toàn 5.000 record bị kẹt ở một hot partition.

Hãy bổ sung event age hoặc time lag: thời gian từ lúc event được tạo/ghi đến lúc consumer hoàn tất. Quan sát lag riêng từng partition và group, không chỉ tổng lag của topic.

## 7. Đo end-to-end latency đúng cách

Để đo thời gian từ producer tới nghiệp vụ hoàn tất, event test nên có `eventId` duy nhất và timestamp tạo event. Consumer ghi timestamp khi bắt đầu và khi side effect hoàn tất.

```java
public record BenchmarkEvent(
        String eventId,
        String customerId,
        Instant createdAt,
        String payload) {
}
```

Listener có thể ghi nhận:

```java
@KafkaListener(topics = "benchmark.orders", groupId = "benchmark-reader")
public void consume(BenchmarkEvent event) {
    Instant listenerStartedAt = Instant.now();
    orderProjection.apply(event);
    Instant completedAt = Instant.now();

    benchmarkMetrics.recordEndToEnd(
            Duration.between(event.createdAt(), completedAt));
    benchmarkMetrics.recordProcessing(
            Duration.between(listenerStartedAt, completedAt));
}
```

Ví dụ minh họa; trong benchmark phân tán, đồng hồ producer và consumer phải được đồng bộ (NTP/chrony) và sai lệch đồng hồ phải nhỏ hơn độ chính xác latency muốn đo. Nếu clock skew lớn, phép trừ timestamp giữa hai máy có thể cho kết quả âm hoặc sai. Có thể dùng distributed tracing hoặc timestamp do cùng một process ghi nhận ở các ranh giới phù hợp.

`listener duration` không bao gồm thời gian record nằm trong broker hoặc chờ poll. `end-to-end latency` mới bao gồm toàn bộ đường đi từ thời điểm tạo event đến khi nghiệp vụ xong. Không dùng một metric thay cho metric còn lại.

## 8. Phân biệt closed-loop và open-loop load

Load generator có thể tạo tải theo hai cách:

- **Closed-loop:** gửi request tiếp theo sau khi request trước hoàn tất. Khi hệ thống chậm, generator tự giảm tốc độ. Cách này dễ tạo hiệu ứng coordinated omission: generator không gửi request trong khoảng hệ thống bị chậm, nên latency đo được có thể trông tốt hơn thực tế.
- **Open-loop:** tạo event theo lịch/rate định trước, không phụ thuộc thời gian phản hồi trước đó. Khi hệ thống không theo kịp, queue/in-flight tăng và latency phản ánh áp lực thực tế.

Với workload production có arrival rate độc lập với tốc độ xử lý, open-loop thường mô phỏng sát hơn. Tuy nhiên, phải giới hạn in-flight và có chính sách khi generator không gửi kịp; nếu chính load generator bão hòa, bài benchmark không còn đo riêng hệ thống mục tiêu.

Nếu dùng closed-loop, ghi rõ concurrency và cách tính latency. Nếu dùng open-loop, ghi rõ target rate, actual generated rate, dropped/scheduled-but-not-sent events và generator utilization.

## 9. Tách benchmark broker khỏi benchmark ứng dụng

Nên thực hiện ít nhất hai loại benchmark:

| Loại | Công cụ | Điều trả lời |
|---|---|---|
| Broker/client baseline | `kafka-producer-perf-test`, `kafka-consumer-perf-test` | Cluster và Kafka client đạt throughput/latency ở cấu hình cơ bản nào? |
| Application end-to-end | Load generator gọi ứng dụng Spring Kafka thật | Toàn bộ serialization, listener, database và business logic xử lý được bao nhiêu? |

Kafka performance tools hữu ích để tạo baseline nhanh, nhưng payload thường đơn giản và không đại diện toàn bộ logic ứng dụng. Nếu broker perf test đã chậm, hãy điều tra cluster/client trước. Nếu broker baseline tốt nhưng ứng dụng chậm, tập trung vào serializer, listener, downstream, thread pool và connection pool.

## 10. Dùng Kafka producer performance tool

Kafka phân phối các công cụ `kafka-producer-perf-test` để đo producer throughput với record có kích thước và tốc độ gửi cấu hình được. Ví dụ với các phiên bản CLI dùng `--producer-props`:

```bash
bin/kafka-producer-perf-test.sh \
  --topic benchmark.orders \
  --num-records 1000000 \
  --record-size 2048 \
  --throughput 10000 \
  --producer-props \
    bootstrap.servers=localhost:9092 \
    acks=all \
    compression.type=lz4
```

Lệnh minh họa gửi một triệu record, payload 2 KB và target khoảng 10.000 record/s. Hãy kiểm tra `--help` của đúng Kafka distribution. CLI thay đổi theo phiên bản; các bản mới bổ sung `--bootstrap-server`, `--reporting-interval` và `--command-property`, trong khi một số option cũ được đánh dấu deprecated. Đừng copy lệnh giữa hai major version mà không kiểm tra.

Kết quả producer perf tool thường cho biết record/byte rate, latency gửi và các thống kê client. Nó không đo thời gian listener xử lý hoặc side effect database. Hãy dùng nó để kiểm tra baseline producer/broker, không dùng làm bằng chứng duy nhất cho end-to-end SLO.

## 11. Dùng Kafka consumer performance tool

`kafka-consumer-perf-test` đo khả năng consumer đọc dữ liệu từ topic. Ví dụ minh họa cho CLI dùng option `--messages`:

```bash
bin/kafka-consumer-perf-test.sh \
  --bootstrap-server localhost:9092 \
  --topic benchmark.orders \
  --messages 1000000 \
  --group benchmark-reader
```

Một số phiên bản mới chuyển `--messages` sang `--num-records`; kiểm tra `--help` của binary đang chạy. Có thể dùng consumer properties/config file để mô phỏng fetch settings và security tương tự ứng dụng.

Consumer perf test thường tập trung vào đọc record và không chạy business logic Spring listener. Nếu consumer chỉ poll rồi bỏ record, throughput có thể cao hơn nhiều so với ứng dụng phải deserialize JSON, validate, gọi database và commit offset.

## 12. Benchmark đúng ứng dụng Spring Kafka

End-to-end benchmark cần chạy đúng artifact ứng dụng hoặc một harness dùng cùng cấu hình producer/consumer và cùng business path. Load generator nên gửi payload thật, key thật và header giống production.

Một kiến trúc thử nghiệm điển hình:

```text
Load generator
   |
   | event + key + eventId + createdAt
   v
Spring Kafka producer / KafkaTemplate
   |
   v
Kafka cluster (topic, partitions, replicas)
   |
   v
Spring @KafkaListener
   |
   +--> deserialize / validate
   |
   +--> service / database / HTTP dependency
   |
   v
Business completion + metrics/traces
```

Giữ serializer/deserializer, listener factory, error handler, acknowledgement mode, database schema và dependency giống production. Nếu dùng mock database hoặc bỏ validation, ghi rõ vì kết quả chỉ phản ánh phần đã giữ lại.

## 13. Load generator dùng KafkaTemplate

Với Spring Kafka 3.x, `KafkaTemplate.send()` trả về `CompletableFuture`. Có thể dùng semaphore để giới hạn số send đang in-flight và đo producer acknowledgement latency:

```java
Semaphore inFlight = new Semaphore(5_000);
LongAdder succeeded = new LongAdder();
LongAdder failed = new LongAdder();

for (long i = 0; i < totalRecords; i++) {
    inFlight.acquire();
    long startedAt = System.nanoTime();
    BenchmarkEvent event = createEvent(i);

    kafkaTemplate.send("benchmark.orders", event.customerId(), event)
            .whenComplete((result, error) -> {
                try {
                    if (error == null) {
                        succeeded.increment();
                        producerAckTimer.record(
                                System.nanoTime() - startedAt,
                                TimeUnit.NANOSECONDS);
                    } else {
                        failed.increment();
                    }
                } finally {
                    inFlight.release();
                }
            });
}

inFlight.acquire(5_000);
inFlight.release(5_000);
```

Đây là skeleton minh họa giới hạn in-flight; code hoàn chỉnh cần quản lý interruption, shutdown, exception khi `send()` ném đồng bộ, timeout và kết quả callback. Vòng lặp này tạo tải theo khả năng hoàn tất của producer (closed-loop có giới hạn concurrency), không bảo đảm một arrival rate cố định. Nếu cần open-loop, bổ sung rate limiter hoặc scheduler phát event theo lịch và ghi nhận event bị trễ so với lịch gửi.

Không gọi `future.get()` ngay sau từng `send()` trong vòng lặp tải cao nếu mục tiêu là đo producer throughput; cách đó biến benchmark thành gửi tuần tự và giới hạn concurrency về gần một. Ngược lại, cũng không gửi vô hạn future mà không giới hạn in-flight vì có thể làm cạn heap và đo khả năng chịu tải của generator thay vì Kafka.

Với Spring Kafka 2.x, API send có thể trả `ListenableFuture`; điều chỉnh callback theo version của dự án. Hãy giữ cùng một version khi so sánh các lần chạy.

## 14. Mô phỏng payload và key giống production

Load generator nên tái tạo đặc điểm dữ liệu thay vì lặp một chuỗi hằng:

- Sinh JSON có kích thước theo phân bố thực tế, ví dụ p50 800 byte, p95 4 KB, p99 12 KB.
- Sinh key theo phân bố tenant/customer/order thực tế.
- Dùng event type có tần suất khác nhau.
- Thêm header trace/correlation nếu ứng dụng sử dụng.
- Giữ tỷ lệ field optional, array và nested object gần production.
- Bao gồm payload gần giới hạn `max.request.size` hoặc `max.message.bytes` nếu hệ thống có event lớn.

Các kích thước trên chỉ là ví dụ. Lấy phân bố từ dữ liệu đã được ẩn danh hoặc thống kê production; không dùng dữ liệu cá nhân/nhạy cảm thật làm payload benchmark nếu không có cơ chế bảo vệ phù hợp.

Nếu chỉ lặp một payload giống hệt nhau, compression ratio có thể cao bất thường và kết quả không đại diện cho event thực. Ngược lại, payload random hoàn toàn có thể khó nén hơn dữ liệu production. Hãy mô phỏng cả entropy và structure của payload.

## 15. Thiết kế các kịch bản tải

Không chỉ chạy một bài test liên tục ở một mức RPS. Dùng nhiều kịch bản để hiểu hành vi hệ thống:

| Kịch bản | Cách chạy | Mục tiêu |
|---|---|---|
| Baseline | Tải thấp, ổn định | Xác định latency/throughput nền |
| Ramp-up | Tăng dần RPS theo từng nấc | Tìm vùng bắt đầu bão hòa |
| Steady-state | Giữ tải mục tiêu trong thời gian đủ dài | Kiểm tra SLO và lag ổn định |
| Burst | Tăng đột ngột lên peak | Đánh giá buffer, backlog và recovery |
| Soak | Chạy tải ổn định trong nhiều giờ | Phát hiện memory leak, GC và resource drift |
| Spike recovery | Dừng burst, trở lại tải bình thường | Đo thời gian drain backlog |
| Failure | Restart broker/consumer hoặc làm dependency chậm | Kiểm tra resilience và recovery |
| Hot-key | Tập trung traffic vào một số key | Phát hiện hot partition và giới hạn ordering |
| Large payload | Tăng tỷ lệ payload lớn | Đo serialization, network, memory và batch behavior |
| Retry/DLT | Tạo tỷ lệ lỗi có kiểm soát | Đo retry amplification và tải DLT |

Steady-state cần đủ dài để loại bỏ ảnh hưởng warm-up và quan sát lag. Soak test phải dài hơn thời gian GC cycle, cache warm-up và các chu kỳ tác vụ nền có thể ảnh hưởng tới ứng dụng.

## 16. Warm-up và thời gian đo

JVM cần thời gian warm-up cho class loading, JIT compilation, connection pool, metadata cache và producer buffer. Không lấy vài giây đầu làm kết quả đại diện.

Một lần chạy có thể chia thành:

1. **Startup:** tạo topic/consumer group, khởi động app và chờ assignment.
2. **Warm-up:** gửi tải tăng dần để JIT và cache ổn định.
3. **Measurement:** giữ target rate và thu metric trong cửa sổ cố định.
4. **Drain:** giảm hoặc dừng producer, chờ consumer xử lý hết backlog.
5. **Verification:** kiểm tra event count, duplicate, missing event và error.

Ví dụ thử nghiệm có thể warm-up 2–5 phút, đo steady-state 10–20 phút và lặp lại ít nhất ba lần. Thời gian thực tế phụ thuộc workload và chi phí môi trường; không coi các khoảng này là tiêu chuẩn cứng.

Không gộp warm-up, measurement và drain thành một con số trung bình. Latency trong giai đoạn drain thường khác steady-state và có thể làm sai kết quả.

## 17. Kiểm soát biến số của môi trường

Để so sánh hai cấu hình, chỉ thay đổi biến đang nghiên cứu. Ghi lại:

- Kafka broker version, Spring Kafka, Kafka client và JVM version.
- Số broker, CPU/RAM/disk/network và loại storage.
- Topic partition count, replication factor, `min.insync.replicas`, retention.
- Producer/consumer properties và serializer/deserializer.
- Số application instance, listener concurrency và CPU/memory limit.
- Database version, connection pool, index, dataset và network latency.
- Load generator host, CPU, memory, network và số thread.
- Thời điểm chạy, workload seed, target rate và thời lượng.
- Các job nền, compaction, backup hoặc workload khác trên cluster.

Không chạy benchmark so sánh trên cluster đang có traffic không kiểm soát. Nếu không thể có môi trường riêng, ghi lại tải nền và xem kết quả chỉ là quan sát tương đối, không phải capacity benchmark có thể tái lập.

## 18. Producer settings cần đưa vào ma trận thử nghiệm

Các cấu hình producer ảnh hưởng đến latency, batching, network và durability:

| Cấu hình | Ảnh hưởng cần quan sát |
|---|---|
| `acks` | Mức acknowledgement và thời gian chờ replica |
| `enable.idempotence` | Tránh duplicate do retry của producer; có ràng buộc tương thích với `acks`, retries và in-flight requests |
| `batch.size` | Batch lớn có thể tăng throughput/compression nhưng dùng thêm buffer và chờ đủ dữ liệu |
| `linger.ms` | Chờ thêm để gom batch; có thể tăng latency khi traffic thấp |
| `compression.type` | Giảm byte truyền/lưu, đổi lại CPU nén/giải nén |
| `buffer.memory` | Dung lượng buffer producer; khi đầy, `send()` có thể block tới `max.block.ms` |
| `max.in.flight.requests.per.connection` | Tăng pipeline request; cần giữ tương thích với idempotence và ordering |
| `delivery.timeout.ms` | Giới hạn tổng thời gian producer báo thành công/thất bại |

Producer idempotence yêu cầu cấu hình tương thích; trong tài liệu Kafka hiện hành, `acks=all`, retries lớn hơn 0 và `max.in.flight.requests.per.connection` không quá 5 là các điều kiện quan trọng. Nếu cấu hình xung đột, producer có thể từ chối cấu hình hoặc vô hiệu hóa idempotence tùy cách đặt property và version. Xem [Apache Kafka Producer Configurations](https://kafka.apache.org/documentation/#producerconfigs).

Ví dụ profile để bắt đầu một ma trận thử nghiệm (không phải preset tối ưu chung):

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[compression.type]": lz4
        "[batch.size]": 65536
        "[linger.ms]": 5
        "[buffer.memory]": 67108864
```

Hãy chạy baseline với cấu hình production hiện tại trước. Sau đó thay từng yếu tố, ví dụ so sánh compression `none`, `lz4`, `zstd`; batch size khác nhau; hoặc `linger.ms` khác nhau. Ghi lại cả producer CPU, broker network và p99 latency. Compression có thể giảm network nhưng làm CPU tăng; lựa chọn tốt phụ thuộc payload và tài nguyên.

## 19. Consumer và listener settings cần thử

| Cấu hình | Tác động có thể có |
|---|---|
| Listener `concurrency` | Số consumer thread; hữu ích tới giới hạn partition và downstream |
| `max.poll.records` | Số record tối đa trả về trong một poll; batch lớn có thể tăng throughput nhưng kéo dài xử lý |
| `fetch.min.bytes` | Chờ đủ dữ liệu trước khi trả fetch; tăng có thể cải thiện throughput nhưng tăng latency |
| `fetch.max.wait.ms` | Giới hạn thời gian broker chờ đạt `fetch.min.bytes` |
| `max.partition.fetch.bytes` | Kích thước dữ liệu tối đa fetch cho một partition mỗi lần |
| `max.poll.interval.ms` | Giới hạn khoảng cách giữa các lần poll trước khi consumer bị xem là không tiến triển |
| Ack mode | Ảnh hưởng commit cadence, duplicate window và overhead |
| Batch listener | Có thể giảm overhead invocation nhưng thay đổi semantics lỗi và commit |

Không tăng `max.poll.records` nếu listener xử lý mỗi record quá lâu mà không xem `max.poll.interval.ms`, memory và retry behavior. Nếu consumer không poll kịp, group có thể rebalance và tạo thêm độ trễ.

Concurrency phải phù hợp số partition. Với một group có 12 partition, đặt concurrency 30 không tạo 30 luồng đọc hữu ích; một số consumer sẽ idle. Tăng concurrency cũng không giúp nếu database connection pool chỉ cho phép ít connection hoặc downstream đã bão hòa.

## 20. Phân biệt producer throughput và consumer throughput

Consumer có thể đọc nhanh hơn producer trong thời gian ngắn vì nó đang drain backlog. Do đó, đo consumer throughput trên topic đã có sẵn dữ liệu có thể cho kết quả cao hơn throughput steady-state của toàn pipeline.

Hãy đo hai trường hợp:

- **Drain test:** nạp sẵn một lượng record rồi đo tốc độ consumer đọc hết. Đây là năng lực xử lý backlog.
- **Steady-state pipeline:** producer và consumer chạy đồng thời với arrival rate ổn định. Đây là năng lực duy trì workload thực tế.

Nếu consumer drain đạt 50.000 record/s nhưng pipeline steady-state chỉ đạt 12.000 record/s, điều đó không mâu thuẫn. Producer, replication, payload generation hoặc downstream có thể là bottleneck của pipeline.

## 21. Consumer lag và thời gian drain backlog

Khi tốc độ producer lớn hơn tốc độ consumer, lag tăng. Gọi:

- \(\lambda\): tốc độ event đi vào partition hoặc hệ thống (record/s).
- \(\mu\): tốc độ consumer xử lý hoàn tất (record/s).
- \(L\): backlog hiện tại (record).

Nếu \(\mu > \lambda\), backlog có thể giảm với tốc độ ròng gần \(\mu - \lambda\). Thời gian drain ước lượng:

\[
T_{drain} \approx \frac{L}{\mu - \lambda}
\]

Ví dụ backlog 120.000 record, producer vẫn gửi 4.000 record/s và consumer hoàn tất 10.000 record/s. Tốc độ giảm ròng khoảng 6.000 record/s; drain ước tính khoảng 20 giây nếu các rate giữ ổn định.

Nếu \(\mu \leq \lambda\), backlog không tự giảm khi producer tiếp tục gửi. Cần tăng năng lực consumer, giảm arrival rate hoặc điều tra bottleneck. Công thức chỉ là ước lượng tổng; hot partition, retry, rebalance và kích thước payload không đồng đều có thể làm thời gian thực tế dài hơn.

## 22. Dùng Little's Law để hiểu concurrency và queue

Little's Law mô tả quan hệ giữa số công việc đang ở trong hệ thống, throughput và thời gian lưu lại:

\[
N = \lambda \times W
\]

Trong đó \(N\) là số công việc trung bình đang in-flight, \(\lambda\) là throughput trung bình và \(W\) là thời gian trung bình trong hệ thống.

Ví dụ nếu listener hoàn tất 2.000 event/s và mỗi event mất trung bình 50 ms, số event đang xử lý/chờ trong phạm vi đo xấp xỉ:

\[
N = 2.000 \times 0,05 = 100
\]

Quan hệ này giúp ước lượng mức concurrency cần thiết, nhưng không có nghĩa cứ tăng thread lên 100 là throughput sẽ đạt 2.000 event/s. CPU, database pool, partition assignment và downstream có thể giới hạn năng lực. Dùng công thức như công cụ suy luận, sau đó xác minh bằng benchmark.

## 23. Theo dõi metric Spring Kafka bằng Micrometer

Spring Kafka có thể tạo timer cho listener và `KafkaTemplate` khi Micrometer có trên classpath và application context có một `MeterRegistry` phù hợp. Từ Spring Kafka 2.3, listener timer có tên `spring.kafka.listener`; từ 2.5, template send timer có tên `spring.kafka.template`. Có thể thêm tag tĩnh hoặc tag provider theo record, nhưng cần tránh tag cardinality cao như order ID/customer ID. Xem [Spring Kafka Micrometer Monitoring](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html).

Từ Spring Kafka 3.0, có thể bật Micrometer Observation trên `KafkaTemplate` và `ContainerProperties`; khi bật observation, timer Micrometer tương ứng được quản lý qua observation. Batch listener có giới hạn riêng theo version và cấu hình. Xem [Spring Kafka Micrometer Observation](https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html).

Ví dụ cấu hình Java:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(6);
    factory.getContainerProperties().setObservationEnabled(true);
    return factory;
}

@Bean
KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory) {

    KafkaTemplate<String, OrderEvent> template =
            new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    return template;
}
```

API và auto-configuration có thể khác theo Spring Kafka/Spring Boot version. Nếu ứng dụng đã dùng Boot auto-configured `KafkaTemplate` hoặc listener factory, hãy cấu hình bean hiện có thay vì tạo bean trùng không cần thiết.

## 24. Metric broker và consumer cần quan sát

Ngoài metric Spring, cần theo dõi Kafka client và broker:

| Thành phần | Metric/quan sát | Dấu hiệu cần điều tra |
|---|---|---|
| Producer | Record/byte rate, request latency, batch size, buffer availability, retry/error | Producer send latency tăng, buffer cạn, retry/error tăng |
| Consumer | Records consumed rate, bytes rate, fetch latency, records lag/max, fetch throttle | Lag tăng, fetch rate giảm hoặc throttle tăng |
| Broker | Bytes in/out, Produce/Fetch request latency, request queue time | Request queue/local/remote time tăng |
| Replica | Under-replicated partitions, ISR shrink/expand, offline log directory | Durability và replication bị ảnh hưởng |
| Network | Throughput, retransmit, connection count, network processor idle | Network saturation hoặc connection churn |
| JVM | Heap, allocation rate, GC pause, CPU | GC/CPU tăng cùng latency |
| Storage | Disk throughput, latency, utilization, page cache | Broker I/O trở thành bottleneck |

Apache Kafka công bố nhiều broker/client metrics qua JMX, gồm request timing, consumer records lag, under-replicated partitions và network/request handler idle ratio. Tên metric có thể thay đổi theo Kafka version; hãy dùng metric catalog của version đang triển khai. Xem [Apache Kafka Monitoring](https://kafka.apache.org/documentation/#monitoring).

## 25. Theo dõi downstream và JVM

Trong Spring listener, Kafka có thể vẫn fetch nhanh nhưng listener xử lý chậm vì database hoặc HTTP service. Vì vậy, benchmark phải thu thêm:

- CPU process/container và CPU throttling.
- Heap, allocation rate, GC pause và số lần full GC.
- Số thread, thread pool queue depth và rejected task.
- Database connection pool active/idle/pending, query latency và lock wait.
- HTTP client connection pool, timeout, retry và remote latency.
- Cache hit ratio và thời gian truy cập cache.
- Serialization/deserialization duration.
- Listener processing duration và exception rate.

Nếu chỉ nhìn Kafka consumer lag, có thể kết luận sai rằng cần tăng consumer concurrency trong khi database connection pool mới là giới hạn. Tăng consumer có thể làm database quá tải nặng hơn.

## 26. Tìm điểm bão hòa (saturation point)

Saturation point là mức tải mà tăng thêm input không còn làm business completion throughput tăng tương ứng, trong khi latency, lag hoặc error bắt đầu tăng nhanh.

Một ví dụ dạng đường cong:

```text
Throughput
  ^
  |                         ________ capacity plateau
  |                    ____/
  |                ___/
  |            ___/
  |        ___/
  |_______/________________________________> Offered load
              ^
          saturation

Latency/lag thường tăng nhanh quanh và sau điểm saturation.
```

Không chọn điểm ngay sát plateau làm operating target nếu workload có burst. Cần có headroom để chịu peak, rebalance, broker maintenance và biến động downstream. Mức headroom nên dựa trên độ biến động traffic và SLO, không áp dụng một tỷ lệ cố định cho mọi hệ thống.

## 27. Chẩn đoán bottleneck theo dấu hiệu

| Dấu hiệu | Bottleneck có thể nằm ở | Kiểm tra tiếp |
|---|---|---|
| Producer ack latency tăng, broker CPU/network cao | Broker, replication, network hoặc request queue | Produce request timing, broker disk/network, ISR |
| Producer ack latency tăng, broker còn rảnh | Producer serialization, buffer, DNS/TLS hoặc generator | Client CPU, buffer wait, serializer duration |
| Broker ingress tốt nhưng consumer lag tăng | Consumer/listener hoặc downstream | Listener timer, consumer CPU, poll rate, DB pool |
| Một partition lag cao hơn nhiều | Hot key hoặc partition skew | Records/bytes per partition, key distribution |
| Listener duration tăng cùng DB pool pending | Database saturation | Query latency, lock, pool size, DB CPU |
| p99 tăng nhưng p50 ổn định | Tail latency, GC, lock contention hoặc dependency outlier | Histogram, GC pause, thread dump, trace |
| Throughput tăng nhưng network bytes giảm mạnh | Compression hiệu quả hoặc payload khác workload | Payload distribution, compression ratio và CPU |
| Rebalance tăng cùng lag spike | Poll interval, processing quá lâu hoặc member churn | `max.poll.interval.ms`, heartbeat, listener duration |
| Consumer fetch rate thấp, lag thấp | Ít dữ liệu hoặc fetch wait cao | Arrival rate, `fetch.min.bytes`, `fetch.max.wait.ms` |
| Retry/DLT tăng và lag tăng | Dependency lỗi hoặc retry amplification | Exception class, backoff, DLT publish rate |

Chỉ thay cấu hình sau khi có giả thuyết được metric hỗ trợ. Ví dụ, tăng `fetch.min.bytes` khi consumer đã bị giới hạn bởi database không giải quyết bottleneck và có thể làm latency tăng.

## 28. Thử nghiệm batching và compression có kiểm soát

Batching và compression thường là hai biến đáng thử đầu tiên ở producer, nhưng phải đo trên payload thực tế.

Quy trình:

1. Chạy baseline với cấu hình hiện tại.
2. Giữ nguyên workload, thay một giá trị `batch.size`.
3. Đo throughput, p95/p99 producer ack, CPU producer/broker và bytes/s.
4. Trả về baseline rồi thử `linger.ms` khác.
5. Thử `compression.type` (`none`, `lz4`, `zstd`) trên cùng payload distribution.
6. So sánh cả network savings, CPU cost và end-to-end latency.

Producer batching gom record theo partition; batch lớn hơn có thể giảm số request và cải thiện compression, nhưng buffer sử dụng nhiều hơn và record có thể chờ lâu hơn để batch đầy. `linger.ms` là giới hạn chờ gom batch, không phải độ trễ cố định cho mọi record; batch đầy có thể được gửi sớm. Default có thể thay đổi theo Kafka version, vì vậy ghi lại version khi báo cáo. Xem [Apache Kafka Producer Configurations](https://kafka.apache.org/documentation/#producerconfigs).

## 29. Thử nghiệm partition count và consumer concurrency

Tạo một ma trận thử nghiệm theo số partition và concurrency, ví dụ:

| Partitions | Concurrency | Mục tiêu |
|---:|---:|---|
| 3 | 1 | Baseline một consumer |
| 3 | 3 | Một consumer trên mỗi partition |
| 6 | 3 | Hai partition mỗi consumer (tùy assignment) |
| 6 | 6 | Tăng số consumer song song |
| 6 | 12 | Quan sát consumer thừa và overhead |

Đây chỉ là ma trận ví dụ. Dùng key distribution giống production và xem per-partition throughput/lag. Tăng partition count có thể tăng parallelism nhưng cũng tăng metadata, file segment, leader assignment và ảnh hưởng ordering theo key khi partitioner map key sang partition mới.

Không chọn partition count chỉ dựa vào throughput một lần chạy. Cần xem khả năng scale consumer group, số broker, phân bố leader, retention, replication và kế hoạch tăng tải tương lai.

## 30. Thử nghiệm retry, DLT và failure injection

Retry tạo thêm traffic và thời gian xử lý. Nếu benchmark chỉ có happy path, năng lực production có thể bị đánh giá cao hơn thực tế.

Thiết kế các kịch bản:

- Tỷ lệ transient failure nhỏ, ví dụ 0,1% record.
- Dependency chậm làm listener duration tăng theo từng đợt.
- Một nhóm record poison message phải đi DLT.
- DLT broker publish tạm thời thất bại.
- Consumer restart/rebalance khi đang có backlog.
- Database timeout làm nhiều record retry cùng lúc.

Quan sát retry attempts, retry topic/DLT ingress, listener failure rate, lag và recovery time. Đảm bảo test có giới hạn để không tạo retry storm ngoài ý muốn. Khi benchmark DLT, cần xác minh không mất record và không lặp vô hạn.

## 31. Đo độ đúng dữ liệu cùng performance

Throughput cao không có ý nghĩa nếu record bị mất hoặc xử lý trùng ngoài contract. Mỗi event trong benchmark nên có ID duy nhất. Sau test, đối chiếu:

- Số event generator đã tạo.
- Số event producer xác nhận thành công.
- Số event được consumer nhận.
- Số event business hoàn tất.
- Số event lỗi/retry/DLT.
- Số event duplicate theo `eventId`.
- Số event thiếu hoặc không có trạng thái cuối.

Nếu dùng at-least-once, duplicate delivery có thể xảy ra và consumer cần idempotent. Không kết luận dữ liệu sai chỉ vì listener invocation count lớn hơn generated count; hãy phân biệt invocation, event ID duy nhất và business completion.

## 32. Benchmark trong môi trường gần production

Một benchmark đáng tin cậy nên dùng topology tương đương production ở các yếu tố quan trọng:

- Broker version và cấu hình broker tương đương.
- Số broker, partition, replication factor và `min.insync.replicas`.
- Storage class, disk throughput và network placement.
- Producer/consumer instance count và CPU/memory limit.
- Security protocol, authentication và ACL nếu security có overhead đáng kể.
- Serialization, Schema Registry, TLS và compression.
- Database/dependency với dataset và connection pool gần thực tế.
- Monitoring/tracing agent tương tự production.

Nếu môi trường test nhỏ hơn, hãy dùng kết quả để so sánh tương đối hoặc tìm bottleneck, không nhân tỷ lệ CPU/broker một cách tuyến tính để suy ra capacity production. Kafka throughput phụ thuộc partition placement, replication, network, disk, key skew và workload mix.

Không chạy stress test trên production cluster khi chưa có kế hoạch, giới hạn tải và phối hợp vận hành. Một benchmark có thể làm tăng lag, ảnh hưởng quota hoặc gây cạnh tranh tài nguyên với traffic thật.

## 33. Quy trình benchmark có thể tái lập

1. Ghi lại câu hỏi cần trả lời và SLO.
2. Thu thập workload profile từ production hoặc dữ liệu mô phỏng đã được kiểm soát.
3. Chuẩn bị cluster, topic, partition, replication và dataset.
4. Xác minh load generator không phải bottleneck.
5. Chạy baseline và warm-up.
6. Chạy steady-state theo target rate và ghi đủ metric.
7. Lặp lại ít nhất ba lần hoặc đủ lần để đánh giá độ biến thiên.
8. Thử burst, soak, hot-key và failure scenario.
9. Thay một nhóm biến có chủ đích, không đổi đồng thời nhiều config.
10. Kiểm tra lag drain, event completeness, duplicate và DLT.
11. So sánh kết quả với baseline bằng cùng cửa sổ đo và cùng workload.
12. Lưu cấu hình, version, seed, command và dashboard snapshot để tái lập.

Nếu kết quả giữa các lần chạy dao động lớn, tìm nguyên nhân môi trường trước khi chọn con số tốt nhất. Báo cáo median của các lần chạy và độ phân tán; không chỉ chọn lần chạy nhanh nhất.

## 34. Mẫu báo cáo benchmark

Mỗi lần benchmark nên lưu một báo cáo có cấu trúc:

| Trường | Giá trị cần ghi |
|---|---|
| Run ID / thời gian | ID duy nhất, thời gian bắt đầu/kết thúc |
| Application | Commit SHA, Spring Boot/Spring Kafka/Kafka client version |
| Cluster | Broker version, broker count, CPU/RAM/disk/network |
| Topic | Partition, replication factor, retention, min ISR |
| Producer | acks, idempotence, compression, batch size, linger, in-flight |
| Consumer | group count, concurrency, max poll records, ack mode |
| Payload | p50/p95/p99 size, schema, key distribution |
| Workload | target/actual event rate, burst, duration, open/closed loop |
| Results | generated/acked/consumed/completed rate, p50/p95/p99 latency |
| Lag | max/avg per partition, oldest event age, drain duration |
| Errors | send failure, listener failure, retry, DLT, duplicate/missing |
| Resources | CPU, heap, GC, network, disk, DB pool |
| Conclusion | bottleneck, SLO pass/fail, capacity và headroom |

Kết luận phải nói rõ giới hạn đo. Ví dụ: “Ở 8.000 event/s, p99 end-to-end đạt 420 ms, lag không tăng, không thiếu event; tại 10.000 event/s, p99 vượt 1 giây và partition 2 lag tăng liên tục do hot key.” Cách viết này hữu ích hơn “Kafka đạt 10k TPS”.

## 35. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| Producer perf test chứng minh ứng dụng đạt throughput đó | Công cụ chỉ đo producer/broker path cơ bản; không chạy business listener |
| Throughput cao đồng nghĩa latency tốt | Hệ thống có thể tăng throughput trong khi p99 và lag đã vượt SLO |
| Chỉ cần đo latency trung bình | p95/p99 mới cho thấy tail latency và outlier |
| Tổng consumer lag thấp nghĩa mọi partition ổn | Một hot partition có thể lag cao trong khi tổng lag vẫn thấp |
| Payload size trung bình đủ đại diện | p95/p99 size và payload entropy ảnh hưởng batching/compression/network |
| Tăng concurrency luôn tăng throughput | Partition, CPU và downstream giới hạn parallelism |
| `send()` trả về là broker đã ack | `KafkaTemplate.send()` trả future; thời điểm future hoàn tất mới phản ánh kết quả send theo ack config |
| Consumer poll nhanh nghĩa nghiệp vụ nhanh | Listener/database có thể hoàn tất chậm hơn nhiều |
| Một lần benchmark là đủ | JVM warm-up, noise và môi trường làm kết quả dao động; cần lặp lại |
| Tối đa hóa throughput là mục tiêu duy nhất | Phải đạt throughput cùng latency, lag, error và correctness SLO |
| Kết quả cluster nhỏ có thể nhân tuyến tính lên production | Partition, replication, storage và network tạo giới hạn phi tuyến |

## Checklist trước khi chấp nhận benchmark

- SLO throughput, p95/p99 latency, lag, error và recovery đã được xác định.
- Workload có payload size distribution, key skew, event mix và burst giống thực tế.
- Phân biệt broker/client baseline với end-to-end Spring Kafka benchmark.
- Load generator có đủ CPU/network và giới hạn in-flight hợp lý.
- Producer/consumer properties và dependency version được lưu lại.
- Có warm-up, steady-state, burst, soak và failure scenario phù hợp.
- Đo generated, producer-acked, consumer-delivered và business-completed rate riêng.
- Đo p50/p95/p99 và end-to-end latency với clock/tracing phù hợp.
- Theo dõi consumer lag và event age theo partition.
- Theo dõi producer, consumer, broker, JVM, network, disk và downstream metrics.
- Kiểm tra event completeness, duplicate, retry và DLT.
- Mỗi lần chạy chỉ thay đổi biến có chủ đích và được lặp lại.
- Có báo cáo kết quả, cấu hình, run ID và giới hạn đo.
- Operating target còn headroom so với saturation point.

Benchmark theo tải thực tế kết nối con số throughput với latency, lag, correctness và tài nguyên của toàn bộ pipeline. Bắt đầu bằng workload model có payload/key distribution thật, đo broker baseline rồi đo ứng dụng Spring Kafka end-to-end, chạy nhiều kịch bản và thay đổi cấu hình từng bước. Chỉ chấp nhận capacity khi hệ thống duy trì được SLO trong steady-state, burst và recovery, đồng thời không mất event hoặc tạo side effect trùng ngoài contract.

## Tài liệu tham khảo

- [Apache Kafka – Producer Configurations](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka – Monitoring](https://kafka.apache.org/documentation/#monitoring)
- [Apache Kafka – Producer Performance Tool source](https://github.com/apache/kafka/blob/trunk/tools/src/main/java/org/apache/kafka/tools/ProducerPerformance.java)
- [Spring for Apache Kafka – Micrometer Monitoring](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring for Apache Kafka – Micrometer Observation](https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html)

# Kiểm chứng hiệu năng đồng thời với thứ tự và ngữ nghĩa xử lý

Một benchmark Kafka có thể đạt hàng trăm nghìn record mỗi giây nhưng vẫn không đạt yêu cầu production nếu record bị mất, bị xử lý trùng, event cùng key hoàn tất sai thứ tự hoặc offset được commit trước khi công việc thực sự hoàn tất. Vì vậy, kiểm chứng hiệu năng phải đo đồng thời **throughput, latency, độ ổn định và tính đúng đắn của luồng xử lý**.

Mục tiêu không phải tìm cấu hình có số record/giây cao nhất bằng mọi giá. Mục tiêu là tìm cấu hình đạt tải cần thiết trong khi vẫn giữ các bất biến nghiệp vụ: event không bị mất ngoài chính sách cho phép, side effect không bị nhân đôi ngoài kiểm soát, thứ tự theo key được bảo toàn khi nghiệp vụ yêu cầu và trạng thái đã commit phản ánh đúng công việc đã hoàn tất.

## 1. Hiệu năng và ngữ nghĩa phải được đo cùng nhau

Một pipeline Kafka thường có nhiều mốc xử lý:

1. Ứng dụng tạo event.
2. Producer gửi request và nhận acknowledgement từ broker.
3. Record được consumer fetch.
4. Ứng dụng xử lý record.
5. Side effect được ghi vào database hoặc dịch vụ đích.
6. Consumer commit offset hoặc transaction được commit.

Không nên dùng một chỉ số duy nhất để đại diện cho toàn bộ pipeline:

| Chỉ số | Đo tại đâu | Điều nó chứng minh |
|---|---|---|
| Producer send rate | Producer client | Ứng dụng đang gọi gửi bao nhiêu record |
| Producer acknowledged rate | Callback/ack của producer | Bao nhiêu record đã nhận acknowledgement theo cấu hình producer |
| Broker ingress rate | Broker | Broker nhận bao nhiêu byte/record/request |
| Consumer fetch rate | Consumer client | Bao nhiêu record đã được fetch |
| Processing completion rate | Ứng dụng consumer | Bao nhiêu record đã xử lý xong logic |
| Durable side-effect rate | Database/dịch vụ đích | Bao nhiêu kết quả đã được ghi bền vững |
| Committed offset progress | Consumer group | Offset nào đã được xác nhận hoàn tất |

Producer send rate cao không có nghĩa consumer đã xử lý xong. Consumer fetch rate cao cũng không có nghĩa side effect đã commit. Benchmark phải ghi nhận riêng từng mốc và chỉ so sánh các mốc có cùng định nghĩa.

## 2. Xác định bất biến nghiệp vụ trước khi chạy benchmark

Trước khi tăng tải, cần viết rõ điều gì phải luôn đúng. Các bất biến thường gặp:

- **No loss:** mọi event thuộc phạm vi test cuối cùng phải được xử lý hoặc nằm trong trạng thái lỗi/DLQ đã được xác định.
- **Duplicate policy:** có thể có redelivery theo at-least-once, nhưng side effect phải idempotent hoặc deduplicate theo event ID.
- **Per-key ordering:** event của cùng entity phải được áp dụng theo sequence tăng dần.
- **Commit correctness:** offset chỉ được commit đến vị trí mà tất cả record trước đó trong partition đã hoàn tất theo semantics của ứng dụng.
- **Transaction visibility:** consumer `read_committed` không nhìn thấy record thuộc transaction bị abort.
- **Bounded lag:** consumer và downstream phải bắt kịp trong thời gian mục tiêu sau khi tải dừng.
- **Failure recovery:** khi producer, consumer hoặc broker lỗi, hệ thống phải phục hồi theo đúng semantics đã chọn.

Không phải workload nào cũng cần tất cả bất biến. Ví dụ, event telemetry độc lập có thể không cần ordering theo key; workflow thay đổi số dư tài khoản thường cần thứ tự nghiêm ngặt theo account ID. Hãy chọn bất biến theo nghiệp vụ thay vì áp cùng một tiêu chuẩn cho mọi topic.

## 3. Thiết kế dữ liệu test để phát hiện mất, trùng và sai thứ tự

Mỗi record benchmark nên mang đủ metadata để đối chiếu đầu vào và đầu ra. Một schema test đơn giản:

```json
{
  "runId": "perf-2026-11-20-a",
  "eventId": "perf-2026-11-20-a:account-42:00000125",
  "key": "account-42",
  "sequence": 125,
  "createdAtEpochMs": 1795178165000,
  "payloadHash": "sha256:...",
  "payload": {"amount": 2500}
}
```

Ý nghĩa:

- `runId` cô lập dữ liệu của một lần chạy, tránh trộn kết quả giữa các benchmark.
- `eventId` duy nhất để phát hiện duplicate và đối chiếu record.
- `key` là entity được partition, ví dụ account/order/customer ID.
- `sequence` tăng theo từng key để kiểm tra thứ tự nghiệp vụ.
- `createdAtEpochMs` phục vụ đo end-to-end latency khi đồng hồ các máy đã đồng bộ.
- `payloadHash` giúp phát hiện payload bị thay đổi hoặc sai dữ liệu.

Sequence phải được tạo theo đúng thứ tự nghiệp vụ. Nếu nhiều producer thread cùng phát event cho một key, cần có bộ cấp sequence hoặc cơ chế serialize riêng; nếu không, test có thể tạo sequence sai ngay từ phía generator và kết luận nhầm Kafka làm đảo thứ tự.

Nếu topic có filter, SMT, retry hoặc DLT, bộ kiểm chứng phải biết event nào được phép biến đổi, bỏ qua hoặc chuyển sang luồng lỗi. Không thể coi mọi chênh lệch giữa input và output là mất dữ liệu nếu hợp đồng pipeline cho phép filtering.

## 4. Các công thức kiểm chứng

Giả sử test run có tập event đầu vào (I), tập kết quả đã hoàn tất (O), và mỗi event có `eventId` duy nhất.

**Duplicate count** là số lần một event ID xuất hiện vượt quá lần đầu:

\[
Duplicates = \sum_{id} \max(0, count_O(id)-1)
\]

**Missing count** là số event đầu vào chưa có kết quả sau khi pipeline đã drain và hết thời gian chờ:

\[
Missing = |I - unique(O)|
\]

**Unexpected count** là số event đầu ra không thuộc input của run hiện tại. Chỉ số này giúp phát hiện record cũ hoặc dữ liệu từ lần test khác lọt vào kết quả.

**Order violation** xảy ra khi sequence của cùng key được áp dụng nhỏ hơn sequence đã áp dụng trước đó:

\[
Violation(k,i) = 1 \quad \text{nếu } seq_{k,i} \le seq_{k,i-1}
\]

Nếu yêu cầu không bỏ sequence, cần kiểm tra thêm gap: `seq_current > seq_previous + 1`. Duplicate, gap và out-of-order là ba loại lỗi khác nhau; không gộp thành một bộ đếm chung.

Chỉ kết luận missing sau khi consumer đã bắt kịp, mọi task đã hoàn tất, transaction visibility đã được áp dụng đúng và thời gian drain đã hết. Trong lúc benchmark đang chạy, event chưa xuất hiện ở output có thể chỉ đang nằm trong backlog.

## 5. Thứ tự trong Kafka được bảo đảm ở phạm vi nào?

Kafka giữ thứ tự record trong một partition theo offset. Kafka không tạo thứ tự toàn cục giữa các partition của cùng topic.

Để các event của cùng entity đi vào cùng partition, producer thường dùng entity ID làm key:

```java
new ProducerRecord<>("account-events", accountId, event);
```

Khi key và partitioner ổn định, các event cùng key được định tuyến vào cùng partition. Tuy nhiên, cần lưu ý:

- Key null không tạo được bảo đảm ordering theo entity.
- Nhiều producer gửi cùng key đồng thời: thứ tự trong log là thứ tự broker append, không tự động là thứ tự nghiệp vụ mà các thread gọi `send()` mong muốn.
- Async processing ở consumer có thể làm side effect hoàn tất sai thứ tự dù record được fetch đúng offset.
- Retry topic hoặc DLT có thể làm event sau được xử lý trước event cũ đang retry.
- Thay đổi số partition có thể làm hash key ánh xạ sang partition khác; event cũ và mới của cùng key có thể nằm ở hai partition trong giai đoạn chuyển đổi.

Nếu ordering là yêu cầu cốt lõi, cần định nghĩa rõ phạm vi: toàn topic, theo partition hay theo entity key. Trong đa số hệ thống event, bảo đảm theo key là lựa chọn thực tế hơn vì thứ tự toàn cục sẽ hạn chế song song.

## 6. Kiểm tra thứ tự ở producer

Producer có thể gửi bất đồng bộ để đạt throughput cao. Kafka producer giữ thứ tự append trong partition theo các request và cơ chế retry của nó, nhưng ứng dụng phải cấu hình đúng và không tạo race ở tầng business.

Các cấu hình cần kiểm tra:

| Cấu hình | Vai trò | Lưu ý khi benchmark |
|---|---|---|
| `enable.idempotence` | Ngăn duplicate do retry producer trong cùng producer session | Bật khi cần semantics chống duplicate do retry |
| `acks` | Mức acknowledgement | `all` chờ acknowledgement từ các replica hiện thuộc ISR; `1` chỉ chờ leader; `0` không chờ broker response |
| `retries` | Số lần retry lỗi có thể retry | Cần đọc cùng `delivery.timeout.ms` và idempotence |
| `max.in.flight.requests.per.connection` | Số request chưa hoàn tất trên một connection | Với idempotence bật, Kafka hỗ trợ tối đa 5; cấu hình đúng giới hạn để giữ ordering khi retry |
| `linger.ms` | Thời gian chờ gom batch | Tăng batching có thể tăng throughput nhưng thêm latency |
| `batch.size` | Kích thước batch cho mỗi partition | Cần đủ traffic trên từng partition để batch đầy |
| `compression.type` | Codec nén record batch | Đo cả CPU, byte mạng và latency |

Ví dụ cấu hình producer cho bài test ưu tiên durability và idempotence:

```java
Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        EventSerializer.class.getName());
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 5);
props.put(ProducerConfig.LINGER_MS_CONFIG, 5);
props.put(ProducerConfig.BATCH_SIZE_CONFIG, 64 * 1024);
props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "lz4");
```

Các giá trị `linger.ms`, `batch.size` và codec chỉ là điểm bắt đầu để thử nghiệm, không phải cấu hình tối ưu cho mọi workload. Cần chạy ma trận nhiều mức và đo lại latency p95/p99.

Với `acks=all`, `min.insync.replicas` đặt ngưỡng ISR tối thiểu để broker chấp nhận write. Ví dụ replication factor 3 và `min.insync.replicas=2`: nếu chỉ còn một replica trong ISR, write yêu cầu `acks=all` sẽ bị từ chối thay vì xác nhận với durability thấp hơn. `acks=1` có thể có throughput/latency tốt hơn nhưng leader có thể xác nhận trước khi follower replicate; nếu leader lỗi ở thời điểm đó, record đã được acknowledge vẫn có thể mất. `acks=0` không phù hợp để đo acknowledged throughput hoặc kiểm chứng durability vì client không nhận xác nhận broker.

Khi idempotence bật, `max.in.flight.requests.per.connection` không được vượt quá 5. Nếu tắt idempotence, kết hợp retry với nhiều request in-flight có thể khiến batch sau thành công trước batch trước bị retry; hãy kiểm tra ordering thực tế thay vì giả định mọi cấu hình producer đều giữ thứ tự.

### Đo acknowledgement thay vì chỉ đếm lời gọi send

`send()` thường trả về trước khi broker xác nhận. Bộ đo throughput nên tăng bộ đếm acknowledged trong callback:

```java
long startedAt = System.nanoTime();

producer.send(record, (metadata, exception) -> {
    if (exception == null) {
        acknowledged.increment();
        ackLatency.record(System.nanoTime() - startedAt);
    } else {
        sendFailures.increment();
    }
});
```

Đo `System.nanoTime()` trong cùng process để tính thời gian từ lúc gửi đến callback; không dùng timestamp monotonic của máy producer để so trực tiếp với máy consumer. Nếu cần end-to-end latency qua nhiều host, dùng wall-clock timestamp và đồng bộ NTP/PTP, đồng thời ghi nhận clock skew.

Idempotent producer chống duplicate do retry ở protocol của producer. Nó không tự loại bỏ duplicate do ứng dụng gửi lại cùng một event như một `send()` mới sau timeout hoặc restart; `eventId` và deduplication ở consumer vẫn cần thiết nếu nghiệp vụ yêu cầu.

## 7. Kiểm tra thứ tự và commit ở consumer

Trong consumer group truyền thống, một partition được giao cho tối đa một consumer member tại một thời điểm. Nếu xử lý tuần tự trên consumer thread và commit sau khi xử lý xong, ứng dụng có thể giữ thứ tự trong partition.

Rủi ro xuất hiện khi consumer dispatch record sang executor:

```text
Partition 0: offset 100 -> worker A (xử lý 800 ms)
             offset 101 -> worker B (xử lý 100 ms)
             offset 102 -> worker C (xử lý 200 ms)

Thứ tự hoàn tất: 101 -> 102 -> 100
```

Log vẫn đúng thứ tự offset, nhưng side effect đã hoàn tất out-of-order. Nếu record 100 là `AccountCreated` và record 101 là `AccountClosed`, trạng thái đích có thể sai.

Một lỗi nghiêm trọng hơn là commit vị trí tiếp theo `103` sau khi đã poll đến offset `102`, trong khi offset `100` chưa hoàn tất. Offset commit là vị trí tiếp theo mà consumer sẽ đọc sau khi khôi phục; commit vượt qua record chưa xử lý có thể khiến offset `100` bị bỏ qua sau restart.

Các cách bảo vệ:

- Xử lý tuần tự từng partition nếu ordering quan trọng.
- Nếu xử lý song song theo key, chỉ cho phép một event của cùng key chạy tại một thời điểm và giữ sequencer theo key.
- Duy trì completion map theo partition; chỉ commit offset cao nhất tạo thành một dải liên tục các record đã hoàn tất.
- Khi partition bị revoke, dừng nhận việc mới, chờ hoặc hủy in-flight work theo chính sách, rồi commit watermark an toàn.
- Không gọi API `KafkaConsumer` từ worker thread vì consumer không thread-safe; thread sở hữu consumer thực hiện poll, pause/resume và commit.

Ví dụ xử lý tuần tự và commit sau khi xử lý:

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "account-projector");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        EventDeserializer.class.getName());
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");

try (KafkaConsumer<String, AccountEvent> consumer = new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("account-events"));

    while (!Thread.currentThread().isInterrupted()) {
        ConsumerRecords<String, AccountEvent> records =
                consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, AccountEvent> record : records) {
            applyIdempotently(record.key(), record.value(), record.offset());
        }

        consumer.commitSync();
    }
}
```

`applyIdempotently()` phải hoàn tất side effect bền vững trước khi vòng lặp commit. Ví dụ này minh họa at-least-once khi side effect ở database không nằm trong Kafka transaction: crash sau database commit nhưng trước Kafka offset commit có thể khiến record được đọc lại. Database cần unique event ID, inbox table hoặc upsert/version check để tránh áp dụng trùng.

## 8. Phân biệt at-most-once, at-least-once và exactly-once

| Semantics | Thứ tự commit | Rủi ro chính | Kiểm chứng |
|---|---|---|---|
| At-most-once | Commit trước khi xử lý | Có thể mất record nếu crash sau commit | So sánh input với kết quả, xác nhận loss được phép hay không |
| At-least-once | Xử lý xong rồi commit | Có thể redeliver nếu crash trước commit | Đếm duplicate event ID và kiểm tra idempotent side effect |
| Exactly-once trong Kafka pipeline | Consume-process-produce và offset nằm trong cùng Kafka transaction | Transaction abort/retry, chi phí transaction và LSO visibility | Dùng consumer `read_committed`, đối chiếu committed output và input |

Kafka transactions có thể atomically commit output records cùng consumer offsets trong một Kafka-to-Kafka pipeline. `processing.guarantee=exactly_once_v2` của Kafka Streams cung cấp semantics exactly-once cho xử lý và ghi dữ liệu Kafka trong phạm vi hỗ trợ của framework.

Kafka transaction không tự tạo transaction phân tán với database, HTTP API hoặc hệ thống bên ngoài. Nếu consumer ghi database rồi commit Kafka offset, crash giữa hai bước vẫn tạo cửa sổ duplicate. Cần inbox/outbox, unique constraint, idempotent API hoặc một giao thức phối hợp phù hợp.

Khi dùng transaction, consumer `isolation.level=read_committed` chỉ đọc các record thuộc transaction đã commit. Record thuộc transaction abort không được trả cho consumer này; consumer có thể bị giới hạn bởi Last Stable Offset (LSO) khi transaction còn mở. Vì vậy, benchmark transaction phải so sánh committed-visible throughput, không chỉ số byte đã append vào log.

## 9. Retry, DLT và thứ tự theo key

Retry là nơi nhiều hệ thống vô tình phá thứ tự:

1. Event sequence 10 lỗi tạm thời và được chuyển sang retry topic.
2. Consumer tiếp tục xử lý sequence 11 từ topic chính.
3. Sequence 11 hoàn tất trước sequence 10.
4. Retry worker xử lý sequence 10 sau đó.

Hệ thống đạt throughput cao hơn vì không chặn toàn partition, nhưng side effect theo key đã out-of-order.

Nếu cần giữ thứ tự:

- Dùng blocking retry có giới hạn cho partition/key khi lỗi phải chặn event sau.
- Hoặc retry theo key với một sequencer, chỉ cho phép sequence tiếp theo chạy khi sequence trước hoàn tất.
- Lưu trạng thái retry và deadline để tránh giữ partition vô hạn.
- Chuyển lỗi không thể phục hồi sang DLT với event ID, key, sequence, error class và original topic/partition/offset.
- Khi replay DLT, xác định rõ replay có thể làm event cũ xuất hiện sau event mới hay không.

Không có một chiến lược retry duy nhất vừa tối đa hóa throughput, vừa đảm bảo strict ordering, vừa tránh head-of-line blocking. Đây là trade-off phải đo và quyết định theo nghiệp vụ.

## 10. Consumer concurrency và số partition

Trong consumer group truyền thống, số consumer active có thể xử lý song song bị giới hạn bởi số partition được subscribe. Tăng consumer vượt số partition không làm tăng throughput của topic đó; consumer dư sẽ idle.

Tuy nhiên, tăng partition cũng có chi phí:

- Nhiều partition hơn có thể tăng mức song song giữa các key.
- Nhiều partition hơn làm tăng metadata, file segment, replication và overhead quản trị.
- Với cùng tổng traffic, mỗi partition có thể nhận ít record hơn, làm batch nhỏ và compression kém hiệu quả.
- Tăng partition count có thể làm thay đổi mapping key-to-partition, ảnh hưởng ordering trong giai đoạn chuyển đổi.

Kafka Share Groups cho phép nhiều share consumer cùng nhận các record khác nhau trong một partition, nên có thể tăng mức song song vượt số partition. Đổi lại, record cùng partition có thể được xử lý bởi các consumer khác nhau và hoàn tất out-of-order. Nếu cần strict per-key ordering, phải có serialization/sequence control ở ứng dụng hoặc chọn consumer group truyền thống với xử lý tuần tự phù hợp.

## 11. Ma trận benchmark cần chạy

Không nên thay đổi nhiều cấu hình cùng lúc. Bắt đầu từ baseline rồi thay từng yếu tố hoặc dùng thiết kế thí nghiệm có kiểm soát.

| Nhóm | Biến cần thử | Điều phải giữ cố định/đo thêm |
|---|---|---|
| Partitioning | Số partition, key distribution, hot-key ratio | Per-partition throughput, key order violations, batch size |
| Producer concurrency | Số producer, số thread, in-flight requests | Producer CPU, buffer wait, ack latency, retry |
| Producer batching | `linger.ms`, `batch.size` | p95/p99 latency, batch-size-avg, request rate |
| Compression | none, gzip, snappy, lz4, zstd | CPU, bytes in/out, compression ratio, latency |
| Durability | `acks=1` và `acks=all`, RF, `min.insync.replicas` | ISR, error rate, leader failover, data loss |
| Consumer concurrency | Consumer count, `max.poll.records`, xử lý tuần tự/song song | Active consumers, lag, completion order, commit watermark |
| Processing cost | CPU-only, database write, HTTP call, state store | Downstream saturation, retries, side-effect duplicates |
| Delivery semantics | at-most-once, at-least-once, Kafka EOS | Missing, duplicates, transaction aborts, visible output |
| Failure | Consumer kill, producer restart, broker failover, network delay | Recovery time, redelivery, ordering, backlog drain |

Payload cần có nhiều kích thước và phân bố gần thực tế. Test chỉ với record rất nhỏ có thể tối ưu request overhead nhưng không đại diện cho workload chứa JSON lớn, schema headers hoặc payload nén.

## 12. Quy trình chạy benchmark có thể lặp lại

Một lần chạy nên có các pha:

1. **Chuẩn bị:** tạo topic riêng cho run, xác nhận partition/replication/ISR, cấu hình consumer group mới và ghi lại toàn bộ client/broker config.
2. **Warm-up:** phát tải thấp để khởi tạo connection, metadata, JIT, page cache và state store.
3. **Ramp-up:** tăng dần producer rate hoặc concurrency theo các nấc đã định.
4. **Steady state:** giữ tải cố định đủ lâu để queue/lag và latency ổn định; ghi metric theo chu kỳ.
5. **Overload test:** tăng vượt công suất mục tiêu để quan sát backpressure, error, retry và queue growth.
6. **Drain:** dừng producer, chờ consumer xử lý hết backlog và transaction hoàn tất.
7. **Correctness audit:** đối chiếu input/output theo run ID, event ID, sequence và payload hash.
8. **Repeat:** chạy lại nhiều lần và so sánh median/p95 giữa các lần, không chọn kết quả tốt nhất đơn lẻ.

Với test dài, thêm soak test để phát hiện memory leak, disk growth, RocksDB compaction, connection leak và throughput suy giảm theo thời gian.

Load generator cũng có thể là bottleneck. Theo dõi CPU, network, GC, queue và producer buffer của máy phát tải. Nếu generator đạt 100% CPU hoặc network saturation, số đo chỉ phản ánh giới hạn generator. Với throughput lớn, phân tán generator trên nhiều host và tổng hợp theo `runId`.

## 13. Công cụ benchmark và giới hạn của chúng

Kafka có các script benchmark như:

```bash
bin/kafka-producer-perf-test.sh \
  --topic perf-input \
  --num-records 10000000 \
  --record-size 1024 \
  --throughput -1 \
  --producer-props bootstrap.servers=localhost:9092 acks=all linger.ms=5
```

```bash
bin/kafka-consumer-perf-test.sh \
  --bootstrap-server localhost:9092 \
  --topic perf-input \
  --messages 10000000 \
  --group perf-consumer
```

Các script này hữu ích để đo throughput cơ bản của broker/client và so sánh cấu hình. Chúng không thay thế ứng dụng benchmark có event ID, sequence, business side effect, retry, transaction và audit output. Consumer perf test đọc record không chứng minh ứng dụng production xử lý đúng thứ tự hoặc commit đúng watermark.

Với kiểm chứng nghiệp vụ, nên có một harness riêng gồm producer tạo sequence theo key, consumer thực hiện đúng logic xử lý/commit dự kiến và auditor đọc kết quả cuối cùng. Có thể dùng perf test CLI để tìm baseline broker trước, sau đó chạy harness để xác minh semantics ở tải mục tiêu.

## 14. Đo throughput, latency và backlog

Throughput ổn định nên tính từ số record đã hoàn tất trong cửa sổ thời gian, không chỉ số record đã submit:

\[
Throughput = \frac{CompletedRecords}{SteadyStateSeconds}
\]

Đo latency bằng histogram và báo cáo p50/p95/p99. Không chỉ dùng mean vì tail latency thường là nguyên nhân gây timeout, retry và rebalance.

Backlog cần được đo theo partition và theo tuổi record:

- Consumer lag theo offset cho biết consumer position cách log end offset bao xa.
- Lag theo offset không luôn bằng số record chính xác khi topic compacted, có transaction hoặc retention đã xóa record.
- Event age từ `createdAt` giúp phát hiện record cũ dù offset lag nhỏ.
- Per-partition lag giúp phát hiện hot partition hoặc key skew bị che khuất bởi cluster average.

Khi dừng tải, đo thời gian drain:

\[
DrainTime \approx \frac{BacklogRecords}{SustainableCompletionRate}
\]

Đây là ước lượng khi completion rate ổn định và không có traffic mới. Thời gian thực tế còn phụ thuộc downstream, retry, rebalance và phân bố backlog theo partition.

## 15. Metrics cần thu thập đồng thời

### Producer

- `record-send-rate`, `record-error-rate`, `record-retry-rate`.
- `request-latency-avg`, `request-latency-max`.
- `batch-size-avg`, `compression-rate-avg`.
- `bufferpool-wait-time`, record queue time và request rate.
- Số callback success/failure và acknowledged latency histogram của harness.

### Broker

- Bytes in/out, messages in, Produce/Fetch requests per second.
- Request queue/local/remote/response latency theo request type.
- Request handler và network processor idle.
- ISR, under-replicated partitions, replication bytes và leader changes.
- CPU, disk latency/IOPS, page cache, network throughput và socket errors.

### Consumer và ứng dụng

- `records-consumed-rate`, `records-lag-max`, fetch latency và commit latency.
- Processing completion rate và processing latency histogram.
- In-flight work count, executor queue depth, per-partition watermark.
- Duplicate event ID, missing sequence, order violation và payload hash mismatch.
- Database/API latency, error, retry, transaction commit/rollback và connection pool.

### Kafka Streams

- Process rate/latency, commit latency, task assignment và rebalance.
- `processing.guarantee`, transaction abort/error và output visibility.
- State store operation latency, restore rate, changelog lag và RocksDB/disk metrics.

## 16. Kiểm thử khi có lỗi

Benchmark chỉ ở trạng thái bình thường chưa đủ để xác nhận semantics. Cần tiêm lỗi có kiểm soát:

| Fault injection | Kết quả mong đợi cần xác minh |
|---|---|
| Producer timeout sau khi broker có thể đã append | Retry không làm nhân đôi event do producer protocol; application resubmit vẫn phải được dedupe bằng event ID |
| Producer process restart | Kiểm tra event đã gửi nhưng chưa nhận callback; xác định duplicate policy của ứng dụng |
| Consumer crash sau side effect nhưng trước offset commit | At-least-once có thể redeliver; idempotent sink phải giữ một side effect |
| Consumer crash sau commit nhưng trước side effect | Nếu commit trước xử lý, có thể mất event; xác nhận at-most-once trade-off |
| Consumer rebalance khi còn in-flight records | Không commit vượt watermark liên tục; record chưa hoàn tất phải được retry hoặc xử lý lại |
| Broker leader failover | Kiểm tra producer retries, ISR, error rate, ordering và acknowledged data |
| Network delay/packet loss | Đo retry, timeout, backpressure và recovery sau khi mạng ổn định |
| Transaction abort | `read_committed` không nhận output bị abort; input offset trong transaction không được commit một phần |
| Downstream chậm hoặc unavailable | Lag tăng có kiểm soát, queue không tăng vô hạn, retry/DLT tuân thủ ordering contract |
| Retry/DLT replay | Event cũ không làm trạng thái entity lùi version hoặc ghi side effect trùng |

Sau mỗi fault, không chỉ kiểm tra service đã `RUNNING`. Phải chờ drain và audit event ID/sequence để xác nhận dữ liệu cuối cùng đúng.

## 17. Tiêu chí chấp nhận benchmark

Một kết quả benchmark chỉ được chấp nhận khi đáp ứng đồng thời các điều kiện đã thống nhất:

| Nhóm | Ví dụ tiêu chí |
|---|---|
| Throughput | Completion rate đạt mục tiêu trong steady state |
| Latency | p95/p99 nằm trong SLO |
| Backlog | Lag ổn định khi tải bằng hoặc thấp hơn capacity; drain trong thời gian mục tiêu |
| Loss | Missing count bằng 0 sau drain, trừ trường hợp được policy cho phép và ghi nhận rõ |
| Duplicate | Không có duplicate side effect; duplicate delivery nằm trong chính sách và được dedupe |
| Ordering | Không có order violation trong phạm vi key/partition đã cam kết |
| Commit | Offset không vượt qua record chưa hoàn tất |
| Transactions | Aborted output không xuất hiện với consumer `read_committed` |
| Recovery | Sau fault, service phục hồi và audit cuối cùng vẫn đạt các bất biến |
| Resource | CPU, disk, network, heap và downstream còn headroom theo mục tiêu vận hành |

Đặt rõ thời điểm bắt đầu/kết thúc tính SLO. Ví dụ, throughput có thể đo trong steady state, còn missing/duplicate/order phải audit sau drain. Không so sánh một cấu hình đã drain hoàn toàn với cấu hình khác vẫn còn backlog.

## 18. Những lỗi benchmark thường gặp

- **Chỉ đo producer send rate:** record có thể chưa được broker acknowledge hoặc consumer xử lý.
- **Chỉ đo consumer fetch rate:** ứng dụng có thể chưa ghi side effect hoặc commit offset.
- **Dùng key ngẫu nhiên nhưng yêu cầu ordering theo key:** test không kiểm tra được hot-key và sequence.
- **Một producer thread cho mọi workload:** không đại diện concurrency và có thể không đạt công suất cần thiết.
- **Quá nhiều consumer trên topic ít partition:** consumer dư idle, số lượng process không đồng nghĩa song song hữu ích.
- **Async processing nhưng commit offset theo record lớn nhất:** có thể skip record chưa hoàn tất.
- **Tăng partition giữa run:** mapping key có thể đổi, khiến kết quả ordering không còn so sánh trực tiếp.
- **Bật retry nhưng không audit event ID:** duplicate và out-of-order bị che khuất.
- **Dùng `read_uncommitted` để đo output transaction:** có thể đếm record đã abort.
- **Không đồng bộ clock:** end-to-end latency bị sai do clock skew.
- **Không warm-up hoặc chỉ chạy một lần:** JIT, cache, compaction và startup làm kết quả nhiễu.
- **Generator bão hòa:** benchmark đo giới hạn máy phát tải thay vì Kafka.
- **Không drain backlog:** kết luận missing quá sớm hoặc bỏ qua thời gian phục hồi.

## 19. Checklist kiểm chứng trước khi chốt cấu hình

- Xác định bất biến no-loss, duplicate policy, ordering scope và delivery semantics.
- Tạo `runId`, `eventId`, key, sequence và payload hash cho từng record.
- Cố định topic, partition, replication, key distribution, payload size và client config.
- Đo riêng send, ack, fetch, processing, durable side effect và committed offset.
- Ghi histogram p50/p95/p99, throughput, lag và resource metrics.
- Kiểm tra producer idempotence, `acks`, retry, in-flight requests và batching.
- Kiểm tra consumer serial/parallel processing, contiguous commit watermark và rebalance handling.
- Kiểm tra retry/DLT có phá per-key ordering hay không.
- Kiểm tra transaction bằng `read_committed` và phân biệt Kafka EOS với database side effect.
- Chạy warm-up, ramp-up, steady state, overload, drain, audit và repeated runs.
- Tiêm producer/consumer/broker/network/downstream failures có kiểm soát.
- Chỉ chấp nhận cấu hình khi throughput/latency đạt SLO và correctness audit không vi phạm bất biến.

Kiểm chứng hiệu năng Kafka phải trả lời được cả hai câu hỏi: hệ thống xử lý được bao nhiêu event trong giới hạn latency, và các event đó có được xử lý đúng semantics hay không. Khi đo acknowledged/completed throughput cùng duplicate, missing, sequence, offset watermark và transaction visibility, đội kỹ thuật có thể chọn cấu hình có năng lực thực tế mà không đánh đổi âm thầm tính đúng đắn của luồng sự kiện.

## Tài liệu tham khảo

- [Apache Kafka Producer Configs](https://kafka.apache.org/44/documentation/#producerconfigs)
- [Apache Kafka Consumer Configs](https://kafka.apache.org/44/documentation/#consumerconfigs)
- [Apache Kafka Design: Message Delivery Semantics](https://kafka.apache.org/44/design/design/)
- [Kafka Streams Core Concepts and Processing Guarantees](https://kafka.apache.org/44/streams/core-concepts/)
- [Kafka Operations: Basic Kafka Operations and Performance Tools](https://kafka.apache.org/44/operations/basic-kafka-operations/)

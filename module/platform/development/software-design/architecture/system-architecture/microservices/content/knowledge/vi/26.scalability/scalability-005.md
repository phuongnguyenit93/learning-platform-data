# Mở rộng consumer theo phân vùng và đặc điểm công việc

## 1. Bối cảnh: tăng số consumer không luôn tăng thông lượng

Trong microservices, một producer có thể phát hàng nghìn sự kiện mỗi giây vào Kafka, RabbitMQ, Amazon SQS hoặc một nền tảng streaming khác. Consumer xử lý sự kiện để lưu trạng thái, gửi thông báo, tính toán báo cáo, đồng bộ dữ liệu hoặc gọi API bên ngoài. Khi lưu lượng tăng, phản xạ quen thuộc là tăng số replica của consumer từ 2 lên 10.

Nhưng số instance không phải biến duy nhất quyết định năng lực xử lý. Với Kafka, **số partition trong một consumer group giới hạn số consumer có thể chủ động đọc song song** từ topic đó. Với RabbitMQ hoặc SQS, cơ chế phân phối và ordering khác: một queue có thể được chia cho nhiều worker, nhưng prefetch, visibility timeout, FIFO message group và downstream capacity vẫn giới hạn thông lượng thực tế.

Một số tình huống:
- Topic Kafka có 6 partition, deploy 12 consumer cùng group: thông thường chỉ tối đa 6 member được giao partition; các member còn lại nhàn rỗi.
- Topic có 24 partition và 24 consumer, nhưng 70% sự kiện cùng một customer key: partition chứa key nóng bị nghẽn trong khi phần lớn partition khác nhẹ.
- Tăng từ 4 lên 16 consumer khiến database có 16 lần số connection và write concurrency: consumer nhanh hơn trong vài giây rồi database quá tải, timeout và retry tăng.
- Consumer tính toán CPU nặng không tăng throughput vì CPU limit của pod quá thấp.
- Consumer gọi API có rate limit 100 requests/giây; tăng replica chỉ khiến nhận nhiều 429 hơn.
- Consumer xử lý batch chậm hơn `max.poll.interval.ms` và bị rebalance lặp, tạo lag tăng dù đã scale.

**Mục tiêu bài học:** chọn mức song song dựa trên **phân vùng dữ liệu, loại công việc, giới hạn downstream, yêu cầu ordering và hành vi khi lỗi**, thay vì chỉ tăng replica theo cảm tính.

Sau bài học, bạn có thể:
1. Giải thích mối quan hệ giữa topic partition, consumer group và worker concurrency.
2. Phân biệt mở rộng theo partition và song song bên trong một consumer.
3. Lựa chọn partition key để cân bằng load mà không phá ordering nghiệp vụ.
4. Ước lượng năng lực xử lý, thời gian xả backlog và điểm nghẽn.
5. Tối ưu cho workload CPU-bound, I/O-bound, DB-bound và external API-bound.
6. Thiết kế autoscaling theo consumer lag, age và giới hạn tài nguyên.
7. Xử lý offset commit, rebalance, idempotency, retry, DLQ và backpressure.
8. Áp dụng đúng mô hình cho Kafka, Kafka Streams, RabbitMQ, SQS và Kinesis.

## 2. Phân biệt bốn loại song song

Trong kiến trúc event-driven, thường có ít nhất bốn cấp:

| Cấp | Đơn vị song song | Ai điều phối? | Hạn chế quan trọng |
| --- | --- | --- | --- |
| **Partition/shard** | Những tập bản ghi có thứ tự riêng | Broker/stream platform | Số partition, key distribution và thứ tự |
| **Consumer instance/member** | Tiến trình/pod tham gia cùng group | Group coordinator / consumer framework | Mỗi partition thường do một member trong group xử lý |
| **Processing worker/thread** | Tác vụ xử lý business logic | Ứng dụng hoặc framework | Ordering, offset commit, CPU, thread safety |
| **Downstream operation** | DB connection, HTTP request, transaction | Pool, limiter, database/API | Quota, locking, connection limits, latency |

Tăng số worker thread trong một consumer có thể tăng xử lý song song nhưng không tạo thêm partition. Ngược lại, tăng partition không tự tăng throughput nếu consumer pool hoặc downstream đã đạt giới hạn.

**Khả năng song song có ích** là mức nhỏ nhất trong những giới hạn có ý nghĩa ở từng giai đoạn của pipeline. Ví dụ 32 partition, 16 consumer, mỗi consumer một worker, nhưng database chỉ chịu được 40 writes/giây: 16 consumer không thể biến DB thành 160 writes/giây.

Vì vậy phải lập **capacity budget từ đầu đến cuối** chứ không chỉ đo số message được `poll`.

## 3. Kafka partition và consumer group hoạt động thế nào?

Kafka lưu bản ghi theo thứ tự tăng dần của offset **bên trong từng partition**. Không có thứ tự toàn cục đơn giản giữa tất cả partition của một topic.

```text
Topic orders.events: 6 partitions

P0: [o1] [o4] [o9]  ----> Consumer A
P1: [o2] [o7]       ----> Consumer B
P2: [o3] [o6]       ----> Consumer C
P3: [o5] [o8]       ----> Consumer A
P4: [o10]           ----> Consumer B
P5: [o11]           ----> Consumer C

Consumer group: order-projection
  A, B, C  (mỗi partition gán cho một member tại một thời điểm)
```

Với mô hình consumer group subscribe topic theo cách thông thường:
- Các member **cùng `group.id`** chia nhau các partition.
- Một partition được gán cho một member trong group tại một thời điểm; một member có thể được gán nhiều partition.
- Các group khác nhau đọc độc lập và có offset riêng. Ví dụ `order-projection` và `order-audit` đều có thể đọc toàn bộ topic.
- Khi member tham gia/rời group hoặc topology thay đổi, coordinator có thể **rebalance** phân chia lại partition.
- Partition count giới hạn số member có việc hữu ích khi topic chỉ có một tập partition cố định.

Ví dụ với 8 partition:
- 1 member có thể nhận 8 partition.
- 4 member có thể mỗi member nhận khoảng 2 partition.
- 8 member có thể mỗi member nhận 1 partition.
- 12 member thường có 4 member không được gán partition của topic này.

Đây là quy tắc phổ biến cho một topic của một group. Nếu group subscribe nhiều topic, assignment thực tế phụ thuộc tổng các partition, assignor, subscription pattern và chính sách phân phối; không thể chỉ lấy partition count của một topic rồi kết luận mọi member sẽ nhàn rỗi.

**Không nhầm consumer group với subscription “mỗi replica đều cần nhận tất cả event”.** Nếu mỗi replica có group.id khác nhau, tất cả có thể đọc toàn bộ topic, tạo side effect trùng, không phải tăng capacity cho một logical consumer.

## 4. Partition key là quyết định kiến trúc nghiệp vụ

Kafka dùng partitioner để chọn partition. Khi cung cấp key ổn định, các record cùng key thường đi tới một partition theo chính sách partitioner hiện hành. Điều này cho phép duy trì thứ tự của một chuỗi sự kiện liên quan khi producer gửi đúng thứ tự và delivery semantics được xử lý phù hợp.

Ví dụ:

```text
Event key: orderId
  order-42 -> P2: Created, Reserved, Paid, Shipped
  order-77 -> P5: Created, Cancelled
```

Key nên đại diện cho **đơn vị cần bảo toàn thứ tự**, thường là aggregate ID như `orderId`, `accountId` hoặc `shipmentId`. Chọn key ngẫu nhiên cho mọi event giúp phân tải nhưng có thể làm các event của cùng aggregate rơi vào những partition khác nhau, từ đó khó đảm bảo state machine xử lý theo thứ tự.

Đặt key ở mức quá rộng cũng nguy hiểm:
- Key bằng `tenantId` khiến một tenant lớn dồn tất cả event về một partition.
- Key bằng một giá trị cố định `billing` khiến topic nhiều partition nhưng chỉ một partition có tải.
- Key bằng timestamp giây có thể gây skew và không phản ánh ordering nghiệp vụ.
- Key bằng entity ID nhưng một entity quá nóng có thể bão hòa một partition.

### Quy tắc chọn key

1. Xác định phạm vi ordering thật sự cần: per order, per account, per customer hay không cần.
2. Đo phân phối cardinality và traffic theo key, không chỉ số lượng key.
3. Đảm bảo producer gửi key đúng, nhất quán giữa tất cả nơi phát event.
4. Xác định hành vi khi key null, thay serializer, thay partitioner hoặc tăng số partition.
5. Không giả định per-key ordering nếu các producer khác nhau phát event cạnh tranh mà không có sequence/version.
6. Với key cực nóng, xem xét phân tách workload hoặc đổi mô hình aggregate khi nghiệp vụ cho phép.

**Không có cách chia một chuỗi bắt buộc xử lý tuần tự của một aggregate thành nhiều partition mà vẫn tự động giữ nguyên thứ tự.** Nếu xử lý song song trên cùng aggregate, cần thêm cơ chế sequence, optimistic concurrency, reconciliation hoặc thay đổi mô hình nghiệp vụ.

## 5. Số partition: giới hạn song song nhưng không phải nút tăng tốc vô hạn

Tăng partition count có thể nâng trần số consumer active, nhưng mỗi partition có chi phí metadata, file handles, scheduling, network, replication và vận hành. Partition quá nhiều làm tăng overhead của broker và consumer, trong khi partition quá ít khóa trần horizontal scaling.

Khi thiết kế ban đầu, cần hỏi:
- Throughput event/giây hiện tại và dự báo đỉnh là bao nhiêu?
- Mỗi event cần bao nhiêu CPU, I/O, database writes, external requests?
- Có ordering theo key nào bắt buộc không?
- Một partition xử lý ổn định bao nhiêu event/giây với workload này?
- Dự kiến mở rộng tới bao nhiêu consumer instances/processing slots?
- Có bao nhiêu topic/consumer group, retention và replication factor?
- Broker cluster có đủ capacity cho partition count đó không?

Một cách ước lượng sơ bộ:

```text
required_partitions ≳ ceil(peak_rate / sustainable_rate_per_partition)
```

Ví dụ peak 12.000 event/giây, một partition có thể xử lý ổn định 500 event/giây ở workload đã đo: cần tối thiểu khoảng 24 partition **nếu phân phối key tương đối đều và downstream chịu được tổng throughput**. Kết quả chỉ là điểm khởi đầu; cần headroom và benchmark, không phải “đảm bảo 24 partition sẽ đạt mục tiêu”.

### Tăng partition trên topic đang chạy

Với Kafka, tăng số partition của một topic có thể khiến key được ánh xạ vào partition khác khi partitioner dựa trên hash modulo partition count. Trong giai đoạn chuyển, các event cũ của key nằm ở partition trước, event mới có thể ở partition mới, dẫn đến việc **không còn bảo đảm thứ tự theo key xuyên lịch sử/cutover** theo giả định cũ.

Bởi vậy, **không tăng partition count trên production mà không đánh giá yêu cầu ordering và consumer state**. Lựa chọn gồm:
- Chỉ tăng khi workload không cần strict per-key ordering qua thời điểm chuyển.
- Dùng topic version mới với partition count khác và migration được thiết kế.
- Áp dụng routing/partitioning policy có kiểm soát và cutover theo key.
- Dùng sequence/version per aggregate, conditional writes hoặc cơ chế ordering ở domain.
- Dừng/điều phối producer-consumer theo một kế hoạch có giới hạn khi hợp đồng yêu cầu.

Nếu topic nhiều consumer group, tất cả group và Kafka Streams/stateful processing cần được đánh giá. Partition change là quyết định về **contract lưu trữ và routing**, không chỉ chỉnh một tham số throughput.

## 6. Workload CPU-bound: giới hạn bởi năng lực tính toán

CPU-bound gồm:
- Parse và kiểm tra payload nặng.
- Mã hóa/giải mã, nén, hashing hoặc chuyển đổi dữ liệu.
- Tính toán giá, tính điểm, analytics hoặc xử lý ảnh.
- Validation phức tạp trên record lớn.

Dấu hiệu:
- CPU usage và throttling cao.
- Poll/consumer lag tăng trong khi network/DB không bão hòa.
- Latency xử lý mỗi record tăng khi số worker vượt CPU quota.
- Thêm replica hữu ích tới khi CPU cluster hoặc partition concurrency đạt giới hạn.

Hướng xử lý:
1. Profile CPU trước khi scale để tránh tối ưu nhầm.
2. Đo chi phí xử lý trung bình và p95/p99 theo loại event.
3. Giữ số worker phù hợp số CPU thực được cấp; tránh tạo hàng trăm thread tranh vài CPU core.
4. Tăng replica nếu còn partition và capacity cluster.
5. Nếu mỗi record rất nặng, cân nhắc batch/vectorization hoặc tách workload theo stage.
6. Ghi rõ nếu xử lý bất đồng bộ bên trong consumer, cách theo dõi hoàn tất theo offset phải an toàn.

Ví dụ container được cấp 1 vCPU nhưng tạo thread pool 32 worker để tính hash CPU-bound: throughput có thể không tăng mà context switching, GC và throttling tăng. Cần benchmark ở CPU limits thực tế.

## 7. Workload I/O-bound: giới hạn bởi latency và concurrency

I/O-bound gồm gọi HTTP API, query database, đọc object storage hoặc chờ network. Một worker dành nhiều thời gian chờ nên concurrency có thể tăng throughput, **nhưng chỉ tới khi downstream và connection pools chạm ngưỡng**.

Mô hình xấp xỉ:

```text
throughput ≈ in_flight_operations / average_latency
```

Nếu mỗi request tới downstream mất trung bình 200 ms, 10 request in-flight lý thuyết tương đương khoảng 50 request/giây trong điều kiện không lỗi và không có overhead khác. Nếu downstream chỉ cho phép 30 request/giây, tăng lên 100 in-flight không tạo thêm quyền quota.

Cần giới hạn:
- Max concurrent requests theo provider/tenant.
- HTTP connection pool per route, timeout và retry budget.
- DB connection pool và transaction concurrency.
- Memory buffer của request đang chờ.
- Deadline toàn operation và thời gian còn lại khi dequeue.
- Token bucket/rate limiter ở consumer thay vì để upstream tạo 429 liên tục.

Một consumer I/O-bound có thể dùng async I/O hoặc worker pool theo kiểu bounded concurrency. Tuy nhiên, **KafkaConsumer API thông thường không thread-safe**; poll, assignment, commit và seek cần một mô hình sở hữu rõ, không chia sẻ cùng instance KafkaConsumer để nhiều thread gọi bừa.

## 8. DB-bound: tăng consumer có thể làm giảm throughput

Một pipeline consumer thường ghi database:

```text
Kafka partitions → Consumer workers → DB connection pool → PostgreSQL
```

Nếu DB đã bão hòa CPU, IOPS, locks hoặc connection limit:
- Tăng replicas tạo thêm connections và transactions.
- Lock contention làm p99 latency tăng.
- Retry sau deadlock/timeout phát sinh thêm tải.
- Consumer lag tăng vì mỗi message mất nhiều thời gian hơn.
- Thậm chí throughput thực tế giảm.

Hướng xử lý:
- Batch write hợp lý, dùng prepared statements hoặc upsert có điều kiện.
- Kiểm tra schema/index và các transaction giữ khóa lâu.
- Giới hạn concurrent writes theo DB capacity, không theo partition count.
- Phân vùng bảng hoặc tách workload lưu trữ khi thật sự phù hợp.
- Tách những event chỉ đọc khỏi event ghi nặng bằng topics/consumer groups khác nếu cần SLA riêng.
- Theo dõi `connection_pool_active/pending`, lock waits, deadlocks, IOPS, WAL/redo và DB p95 latency.

**Partition giúp phân chia nguồn công việc, không phân chia tự động khả năng ghi của một database chung.**

## 9. External API-bound: quota và idempotency quyết định tốc độ

Ví dụ consumer xử lý `ShipmentRequested` bằng cách gọi API vận chuyển. Provider cho phép 100 request/giây, nhưng Kafka có 48 partition và team tăng consumer lên 48 pod.

Nếu mỗi pod tự áp rate limit 100 request/giây, tổng lưu lượng có thể trở thành 4.800 request/giây và provider trả hàng loạt 429. Hạn mức thường áp cho **account/client/tenant**, không phải cho mỗi pod.

Thiết kế đúng:
1. Xác định quota toàn cục theo credential/tenant/provider.
2. Dùng rate limiter phân tán hoặc phân bổ quota có kiểm soát cho các consumer.
3. Tôn trọng `Retry-After` và backoff/jitter phù hợp.
4. Không retry mọi lỗi 4xx; phân loại transient vs permanent.
5. Gắn idempotency key/operation ID cho API có side effect, nếu provider hỗ trợ.
6. Khi timeout không biết kết quả, thực hiện reconciliation thay vì tạo thao tác mới không cùng identity.
7. Có DLQ/manual review cho trường hợp không thể hoàn tất trong retry budget.
8. Giữ consumer concurrency dưới giới hạn gây nghẽn của provider, kể cả khi Kafka partitions nhiều.

Với provider rate limit nghiêm ngặt, consumer count thường phải dựa trên **quota** trước rồi mới dựa trên partition count.

## 10. Workload không đồng đều: lag bình quân có thể che partition nóng

Giả sử topic có 8 partition, tổng lag là 80.000 messages. Phân bố:

```text
P0: 70.000  #############################  HOT
P1:  2.000  ##
P2:  2.000  ##
P3:  1.500  #
P4:  1.500  #
P5:  1.000  #
P6:  1.000  #
P7:  1.000  #
```

Tổng lag lớn không có nghĩa chỉ cần thêm consumer. Nếu P0 bị nóng do key duy nhất và yêu cầu xử lý tuần tự, việc tăng từ 8 lên 16 consumer **không làm P0 được đọc đồng thời bởi 2 member cùng group**.

Các nguyên nhân phổ biến:
- Một tenant/customer chiếm phần lớn event.
- Event key quá ít giá trị, không phân phối đều.
- Một loại event có processing time lớn.
- Poison message lặp lại ở một offset gây chặn partition.
- Một partition dùng downstream khóa riêng hoặc shard DB đã nóng.
- Consumer assignment không đều vì nhiều topics, partition sizes hoặc cấu hình assignor.

Giải pháp phải đúng nguyên nhân:
- Đo lag và throughput **theo partition**, kèm processing latency theo event type.
- Thay key hoặc tách tenant lớn thành luồng riêng nếu nghiệp vụ cho phép.
- Tách công việc nặng thành pipeline/topic với pool khác.
- Tối ưu hot handler, batch hoặc cách truy cập DB.
- Xử lý poison message có giới hạn thay vì retry vô hạn.
- Chỉ tăng partition/replicas khi còn parallelism hợp lệ và đủ capacity.

Không tự thay key thành random UUID nếu domain cần đảm bảo ordering cho cùng order/account.

## 11. Song song bên trong một partition: lợi ích và cái giá

Kafka chỉ có một member nhận một partition trong một group, nhưng ứng dụng có thể **đọc batch rồi dispatch các record sang worker pool**. Điều này có thể tăng tốc khi xử lý độc lập hoặc I/O-bound, nhưng làm offset commit và ordering phức tạp.

Ví dụ:

```text
P2 offsets: 100, 101, 102, 103

Consumer poll:
  100 -> worker A (chậm)
  101 -> worker B (xong)
  102 -> worker C (xong)
  103 -> worker D (xong)

Không được commit offset 104 nếu 100 chưa hoàn tất
mà ứng dụng không có cơ chế replay/transaction riêng.
```

Nếu commit offset cao trước khi tác vụ có offset thấp thành công, consumer restart có thể bỏ qua record chưa xử lý: **mất công việc**. Nếu giữ offset nhưng cho các event cùng aggregate xử lý đảo thứ tự, state machine có thể sai.

Các chiến lược:
- **Tuần tự theo partition:** dễ nhất để giữ order/commit, nhưng giới hạn throughput.
- **Parallel per independent key:** route cùng key tới cùng worker lane, xử lý tuần tự trong lane, song song giữa các key; vẫn cần commit liên tục theo offset đã hoàn tất.
- **Batch với bounded concurrency:** chờ hoàn thành toàn bộ batch rồi commit offset hợp lệ; cần timeout/backpressure và có thể ảnh hưởng latency.
- **Outbox/inbox local durable handoff:** consumer ghi công việc vào durable store theo hợp đồng rồi mới ack nguồn; worker độc lập xử lý phía sau.
- **Kafka Streams/processors:** dùng framework đã quản lý partition ownership/state thay vì tự triển khai offset logic thiếu kiểm chứng.

**Không commit theo “offset lớn nhất đã hoàn thành” một cách mù quáng.** Phải commit **ranh giới liên tục** mà mọi offset trước đó đã được xử lý hoặc được chuyển sang trạng thái bền vững theo hợp đồng.

## 12. Tính toán sơ bộ throughput và thời gian xả backlog

Một mô hình công suất đơn giản:

- `P`: số partition có công việc.
- `C`: consumer members trong một group.
- `R`: thông lượng xử lý bền vững của một partition-worker với loại event hiện tại.
- `λ` (lambda): tốc độ sự kiện đến trung bình/đỉnh.
- `μ` (mu): năng lực xử lý tổng có thể duy trì.

Nếu mỗi consumer xử lý tuần tự trên partition được giao, có thể ước lượng trần sơ bộ:

```text
effective_parallel_slots ≤ min(P, C × slots_per_consumer)
μ ≈ effective_parallel_slots × R
```

Nhưng khi một member nhận nhiều partition, overhead poll, CPU, batch và cách handler chạy khiến “slots” không đơn giản bằng số partition; cần benchmark. Ngoài ra trần thực là mức nhỏ hơn giữa consumer-side capacity và downstream capacity.

Ví dụ:
- P = 12 partition, C = 6 members.
- Mỗi partition có thể xử lý bền vững khoảng 150 event/giây dưới workload hiện tại.
- Nếu cả 12 partition thực sự được xử lý song song và downstream đủ khỏe, trần ước lượng là khoảng 1.800 event/giây.
- Producer ghi 2.200 event/giây: lag sẽ tăng khoảng 400 event/giây theo mô hình ổn định này.

Nếu ingest giảm còn 1.000 event/giây và processing vẫn 1.800:
- Năng lực xử lý backlog ròng ≈ 800 event/giây.
- Với backlog 80.000 event, lý thuyết mất khoảng 100 giây để đuổi kịp.
- Thực tế sẽ lâu hơn do skew, rebalances, spikes, retry, consumer startup và hạn chế downstream.

Một hệ thống được scale đúng cần **μ lớn hơn λ đỉnh có ý nghĩa trong thời gian đủ dài** hoặc có chính sách chấp nhận backlog/độ trễ hoàn tất. Khi năng lực thấp hơn lưu lượng đến liên tục, chỉ tối ưu retry hoặc tăng queue buffer sẽ không làm lag tự giảm.

### Little's Law như công cụ bổ sung

Với hệ ổn định, số work items đang xử lý trung bình gần bằng arrival rate nhân thời gian ở hệ thống:

```text
L ≈ λ × W
```

Nếu 100 operations/giây có thời gian end-to-end 0,2 giây, trung bình có khoảng 20 operations đang in-flight theo giả định của công thức. Con số này giúp thiết kế bounded concurrency, nhưng không thay thế đo latency tail và ràng buộc downstream.

## 13. Poll loop, thời gian xử lý và rebalance

Kafka consumer cần tiếp tục tham gia group và đáp ứng các giới hạn liveness. Nếu poll loop bị chặn quá lâu bởi business logic, consumer có thể vượt `max.poll.interval.ms`; group coi member không còn tiến hành xử lý bình thường và partition có thể bị giao cho member khác, dẫn tới replay và duplication.

Những cấu hình cần hiểu:
- `max.poll.records`: số record tối đa trả về từ một lần `poll`; **không** phải giới hạn kích thước toàn bộ dữ liệu đã fetch.
- `max.poll.interval.ms`: giới hạn thời gian giữa những lần `poll` được chấp nhận trước khi group xử lý member như không tiến triển.
- `session.timeout.ms` và heartbeat: quyết định phát hiện thành viên mất kết nối theo protocol/config.
- `fetch.min.bytes` / `fetch.max.wait.ms`: ảnh hưởng batch/network tradeoff.
- `max.partition.fetch.bytes` và `fetch.max.bytes`: ảnh hưởng kích thước fetch/memory.
- `enable.auto.commit`: quyết định offset tự động; nếu processing có side effect lâu, cần hiểu rõ thời điểm commit.

Thực hành:
1. Không khóa poll thread để chờ external API hàng phút nếu không kiểm soát deadline/interval.
2. Giới hạn batch hoặc offload xử lý sang worker queue có capacity hữu hạn.
3. Dùng `pause` partition khi queue đầy và `resume` khi có chỗ; tiếp tục `poll` ở mô hình phù hợp để duy trì membership.
4. Commit offset theo kết quả đã hoàn tất, có xử lý khi revoke partition.
5. Xử lý shutdown/rebalance an toàn: ngừng nhận thêm việc, drain trong deadline, commit phần hoàn tất, cho phép replay phần chưa chắc chắn.
6. Đo số rebalances và thời gian không xử lý, thay vì chỉ lag.

Các protocol/assignor hiện đại có thể giảm mức độ gián đoạn rebalance, nhưng **không thay thế** thiết kế xử lý duplicate, offset và in-flight records an toàn.

## 14. Cooperative rebalance và static membership

Khi nhóm consumer scale lên/xuống hoặc rolling deploy, Kafka có thể cần chuyển partition ownership. Rebalance thường xuyên làm ngắt xử lý, tạo lag tạm thời và kích hoạt replay của record chưa được commit.

Hai hướng tối ưu:
- **Cooperative/incremental rebalancing** với assignor hỗ trợ giúp giảm số partition bị revoke cùng lúc trong một số tình huống.
- **Static membership** với `group.instance.id` ổn định giúp tránh churn membership không cần thiết khi instance khởi động lại nhanh trong những điều kiện được hỗ trợ.

Không nên copy cùng `group.instance.id` cho hai replica đang chạy; member identity phải duy nhất trong group. Nếu dùng Kubernetes, cần gắn instance identity với pod/slot ổn định và hiểu lifecycle/rollout của workload.

Các chi tiết còn phụ thuộc Kafka client/broker version, group protocol và assignor; cấu hình phải được kiểm chứng trên hệ đang chạy. Một rollout hợp lý có readiness, preStop/shutdown deadline và giới hạn tốc độ thay replica để không tạo rebalance liên tiếp.

Đo ít nhất:
- Rebalance count/time.
- Partition assignments/member.
- Commit latency/failure.
- Lag theo partition sau rollout.
- Tỷ lệ record được xử lý lặp sau revoke/crash.

## 15. Offset, acknowledgment và bảo đảm giao hàng

Trong Kafka, “đã fetch record” không đồng nghĩa “đã thực hiện side effect thành công”. Offset commit quyết định nơi consumer tiếp tục đọc sau restart.

Một số semantics:
- **At-most-once:** commit trước rồi xử lý; nếu crash sau commit có thể mất công việc.
- **At-least-once:** xử lý rồi commit; nếu crash sau side effect nhưng trước commit, record có thể được xử lý lại.
- **Exactly-once trong phạm vi hỗ trợ:** có thể dùng transaction Kafka để liên kết ghi kết quả ra Kafka và commit offset, hoặc thiết kế idempotent/transactional ở hệ đích. Không nên suy rộng “exactly once Kafka” thành “HTTP/DB/email bên ngoài tự đúng một lần”.

Với side effect ở PostgreSQL, cách phổ biến:
1. Nhận event có `eventId` / `operationId` bền vững.
2. Trong một DB transaction, kiểm tra/ghi idempotency record với unique constraint.
3. Thực thi cập nhật nghiệp vụ và ghi nhận event đã xử lý cùng transaction.
4. Commit DB thành công.
5. Sau đó commit offset Kafka thích hợp.
6. Nếu crash ở khoảng giữa, record được replay nhưng DB phát hiện đã xử lý, không nhân đôi side effect.

Ví dụ mô hình inbox:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Đây là cấu trúc minh họa. Cần đặt logic dedup và business write trong transaction phù hợp và kiểm soát xử lý cạnh tranh để tránh race. Nếu sự kiện gọi external payment API, DB unique constraint không tự ngăn provider nhận hai yêu cầu khi crash ở cửa sổ không xác định; dùng provider idempotency key và reconciliation.

**Scale consumer chỉ an toàn khi duplicate/replay đã được tính vào thiết kế.**

## 16. Các pattern xử lý concurrency phổ biến

### Pattern A — Một poll loop, xử lý đồng bộ theo record

```text
KafkaConsumer.poll()
    -> record 1: xử lý xong
    -> record 2: xử lý xong
    -> record 3: xử lý xong
    -> commit completed offsets
    -> poll tiếp
```

Ưu điểm: đơn giản, thứ tự theo partition dễ giữ, commit dễ hiểu. Hạn chế: một record chậm có thể kéo dài poll interval, chặn các partition khác cùng được giao. Hợp với workload nhanh, ổn định hoặc khi ordering là ưu tiên cao.

### Pattern B — Poll thread + bounded worker pool

```text
Poll thread (owner của KafkaConsumer)
       |
       +--> bounded queue / per-key lanes
                    |
                    +--> worker-1
                    +--> worker-2
                    +--> worker-3
       |
       +--> track completed offsets per partition
       +--> commit only contiguous completed offsets
```

Ưu điểm: dùng tốt CPU và I/O concurrency. Hạn chế: nhiều state quản lý, cần pause/resume, xử lý cancel/revoke, tránh commit nhảy cóc. Nếu cùng key cần ordered processing, route theo key hoặc dùng lane tuần tự.

### Pattern C — Consumer ghi vào inbox/task store bền vững

```text
Kafka → Ingest Consumer → Durable Inbox DB
                             |
                             +→ Worker pool
                                   |
                                   +→ downstream
```

Ingest consumer có thể commit Kafka sau khi công việc đã được lưu bền vững thành công theo giao kèo. Worker pool scale theo tốc độ xử lý và DB/job state. Tradeoff là thêm storage, transaction, cleanup và hai cấp retry. Phù hợp khi business task rất lâu, cần workflow state hoặc strict control over retries.

### Pattern D — Kafka Streams hoặc stream processing framework

Framework quản lý assignment, processing topology, state stores và recovery; phù hợp aggregation, join, transformation hoặc per-key stateful logic. Nhưng partitioning, repartition topics, state restore và topology compatibility phải được hiểu đúng. Không giả định framework tự loại bỏ skew hoặc giới hạn của downstream API.

### Pattern E — Tách workload nặng sang topic riêng

```text
RawEvents
   |
   +--> LightweightIndexer (fast, many partitions)
   |
   +--> HeavyScoringTopic → ScoringWorkers (CPU-heavy)
   |
   +--> ExternalDeliveryTopic → RateLimitedWorkers
```

Cách này giúp mỗi workload có retry, concurrency, timeout và SLO riêng. Nhưng cần hợp đồng event, idempotency và xác định thứ tự của các bước.

## 17. Pseudocode Kafka poll loop với bounded processing

Ví dụ kiến trúc minh họa (không phải class hoàn chỉnh có thể copy chạy ngay):

```java
// Một thread duy nhất sở hữu KafkaConsumer.
// Worker pool xử lý payload; poll-thread là nơi duy nhất
// thay đổi assignment, pause/resume, seek và commit.

while (running) {
    ConsumerRecords<String, OrderEvent> batch =
        consumer.poll(Duration.ofMillis(250));

    for (ConsumerRecord<String, OrderEvent> record : batch) {
        TopicPartition partition =
            new TopicPartition(record.topic(), record.partition());

        if (!inFlight.tryAcquire(partition)) {
            consumer.pause(Set.of(partition));
            // Record cần giữ trong bounded buffer/queue có ownership rõ;
            // không được bỏ record vừa poll rồi commit vượt nó.
            buffer.defer(record);
            continue;
        }

        workers.submit(() -> {
            try {
                processIdempotently(record);
                completions.markSuccess(partition, record.offset());
            } catch (Exception e) {
                failures.record(partition, record.offset(), e);
            } finally {
                inFlight.release(partition);
            }
        });
    }

    // Kiểm tra những offset liên tục đã hoàn thành trên poll-thread.
    // Commit offset = highest contiguous processed offset + 1.
    Map<TopicPartition, OffsetAndMetadata> safeOffsets =
        completions.contiguousCommitPositions();
    consumer.commitSync(safeOffsets);

    // Resume khi buffer còn chỗ, theo trạng thái assignment thực tế.
    flowControl.resumePartitionsWithCapacity(consumer);
}
```

Đây là **pseudocode thiết kế**, các lớp `buffer`, `completions`, `inFlight`, `flowControl` chưa được định nghĩa. Cần triển khai riêng logic không mất record, retry/requeue, revoke callback, shutdown, duplicate completion và assignor. `KafkaConsumer` không an toàn để nhiều worker cùng gọi `commit` hoặc `pause`; thao tác đó phải đặt ở thread sở hữu consumer.

Nếu đội chưa có kinh nghiệm với offset bookkeeping, hãy ưu tiên framework/processing model đã kiểm chứng thay vì tự xây executor queue phức tạp từ đầu.

## 18. Spring Kafka: concurrency không vượt qua partition ceiling

Với Spring Kafka, listener container có thể quản lý nhiều consumer instances và cung cấp cấu hình `concurrency`. Ví dụ minh họa:

```java
@KafkaListener(
    topics = "orders.events",
    groupId = "order-projection",
    concurrency = "4"
)
public void onOrderEvent(OrderEvent event) {
    orderProjectionService.applyIdempotently(event);
}
```

Ý nghĩa:
- Container có thể tạo nhiều consumer delegates để đọc partitions.
- Effective parallelism vẫn bị giới hạn bởi tổng partition được gán cho group.
- Nếu topic có 3 partition, đặt concurrency 16 không tạo 16 partition active.
- Trong multi-topic/container setup, assignment phụ thuộc subscription và configuration.
- Handler phải chịu được duplicate delivery, rebalance và concurrent calls đến shared dependencies.
- Khi code cần manual ack, transaction, batch listener hoặc async processing, phải cấu hình và xử lý theo đúng cơ chế listener container; không suy luận từ method đơn giản.

Ví dụ cấu hình minh họa:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      max-poll-records: 200
    listener:
      concurrency: 4
```

Cấu hình thực tế phụ thuộc phiên bản Spring Boot/Spring Kafka và acknowledgement mode; đặt `enable-auto-commit: false` **không tự làm xử lý exactly once**. Bản thân `max-poll-records` phải phù hợp với processing time, memory và deadline. Nếu mỗi record lâu, batch 200 có thể khiến poll interval quá hạn dù consumer count có vẻ hợp lý.

Với batch processing, error handler và DLQ cần xác định rõ phần nào của batch đã hoàn tất, có thể retry và được commit.

## 19. Backpressure: khi không thể xử lý kịp, phải giới hạn đầu vào

Khi producer nhanh hơn consumer, Kafka lưu backlog. Điều này giúp tách thời gian phát/đọc trong giới hạn retention và storage, nhưng không có nghĩa consumer có thể giữ vô hạn công việc trong memory.

Một thiết kế ổn định:

```text
Broker backlog
      |
      v
Poll bounded batch
      |
      v
Bounded in-flight queue  ---> capacity full?
      |                         |
      v                         +→ pause partitions
Workers                             and keep group alive
      |
      v
Downstream limiter
      |
      v
Ack/commit after durable completion
```

Không nên:
- Poll 10.000 messages rồi enqueue không giới hạn vào heap.
- Dùng thread pool có unbounded queue, khiến backlog chuyển từ broker bền vững sang JVM memory dễ mất.
- Tăng concurrency không giới hạn khi downstream 429/503.
- Commit offset ngay lúc enqueue công việc **chưa bền vững** rồi tin rằng nó chắc chắn hoàn thành.
- Tắt consumer vì queue đầy nhưng không tính rebalance, shutdown và retry.

Nên:
1. Đặt max in-flight theo memory và latency budget.
2. Giới hạn queue length và worker concurrency.
3. Pause các partition đầy, resume theo low watermark.
4. Vẫn duy trì poll/heartbeats theo client protocol.
5. Từ chối hoặc trì hoãn work theo hợp đồng, không âm thầm bỏ record.
6. Có flow control xuống DB/API và giới hạn retries.
7. Giám sát age của record cũ nhất, không chỉ tổng lag.

Backpressure thực sự là cách quản lý **tốc độ tiêu thụ tương ứng năng lực hoàn tất công việc**, không đơn giản là tạo thêm thread.

## 20. Batching và record size: không tối ưu chỉ bằng số lượng record

Batching có thể giảm overhead network/DB round trips, nhưng tạo tradeoff latency, memory và fault isolation.

Ví dụ consumer nhận 200 bản ghi:
- Với DB insert theo batch, throughput có thể cao hơn 200 transaction nhỏ.
- Nhưng một bản ghi lỗi có thể làm rollback cả batch, buộc chiến lược chia/lọc phù hợp.
- Bản ghi lớn 5 MB không tương đương bản ghi JSON 1 KB; `max.poll.records` không kiểm soát hết memory.
- Batch lớn khiến consumer giữ partition lâu và thời gian ack kéo dài.
- Nếu ordering cần theo key, batch parallelization phải giữ ranh giới hợp đồng.

Những câu hỏi:
1. Có thể gộp side effect an toàn không?
2. Từ mỗi record có idempotency key riêng không?
3. Nếu lỗi một record, có thể xác định và retry riêng không?
4. Có ràng buộc transaction size, locks hoặc WAL/redo không?
5. Latency p99 của batch có làm vi phạm SLA không?
6. Consumer có giữ poll interval và memory limit không?

Không mặc định batch lớn luôn nhanh hơn; benchmark với payload và downstream thực tế. Tối ưu throughput phải đi cùng xác nhận correctness và thời gian hoàn tất.

## 21. Autoscaling theo lag: khi nào nên tăng replica?

HPA dựa trên CPU là một tín hiệu hữu ích cho CPU-bound consumer, nhưng không đủ khi I/O wait hoặc backlog tăng mà CPU thấp. Các hệ thống autoscaling như KEDA có thể dùng Kafka lag hoặc chỉ số tùy chỉnh để đề xuất replicas, tùy cấu hình trigger/scaler và môi trường.

Ý tưởng điều khiển:

```text
Lag / oldest message age / processing rate
                     |
                     v
           Autoscaler decides
                     |
         +-----------+-----------+
         |                       |
         v                       v
Scale up if capacity       Scale down if stable,
available and needed       safe drain and low backlog
         |
         v
Consumer group rebalance
         |
         v
Effective throughput measured
```

Cần giới hạn thực tế:
- `maxReplicas` không nên vượt quá parallelism có ích khi chỉ subscribe một topic có P partition, trừ lý do khác đã được chứng minh.
- Downstream có quota/concurrency budget; autoscaling không được vượt budget đó.
- Startup/rebalance mất thời gian; quá nhạy theo lag có thể tạo scale oscillation.
- Một partition nóng không được giải quyết bằng việc thêm member nhàn rỗi.
- Workload async rất lâu có thể cần scale theo in-flight tasks và age thay vì chỉ lag đầu nguồn.
- Khi scale down, phải drain an toàn và commit offset đã xử lý, tránh replay không kiểm soát.
- Có min replicas phù hợp yêu cầu recovery và availability.

### Lag count khác message age

10.000 messages lag có thể:
- Chỉ cần 10 giây để xử lý nếu records nhẹ và parallelism lớn.
- Cần 3 giờ nếu mỗi record gọi provider chậm và rate-limited.

Vì vậy hãy theo dõi cả:
- `records-lag-max` / lag per partition/group.
- **Age of oldest unprocessed record** hoặc end-to-end event-to-effect latency.
- Incoming rate và completed processing rate.
- Per-record processing time theo loại event.
- Rebalance downtime, error/retry rate.
- Downstream saturation.

Autoscaler tốt dựa vào **mục tiêu độ trễ hoàn tất**, không chỉ phản ứng với số message chưa đọc.

## 22. Autoscale có kiểm soát và chống thrashing

Khi consumer scale liên tục 4 → 10 → 4 → 10:
- Kafka group rebalances lặp lại.
- Tasks in-flight bị dừng/đọc lại.
- Connection pools liên tục mở/đóng.
- Cache không kịp warm, throughput thực giảm.
- Hệ thống hiểu lag tăng là cần scale thêm, tạo vòng lặp xấu.

Hướng kiểm soát:
1. Dùng polling interval và smoothing window phù hợp.
2. Có stabilization window/cooldown cho scale down.
3. Giới hạn bước thay replica mỗi lần.
4. Đo **sustainable throughput after rebalance**, không chỉ số pod đang Running.
5. Giữ replica tối thiểu phù hợp các service critical.
6. Giảm rate/concurrency nếu DB/provider bão hòa dù lag tăng.
7. Quản lý graceful shutdown/revocation; không kill pod vô điều kiện khi còn side effect chưa hoàn tất.
8. Có override trong incident để giới hạn retry storms.

Các tham số cụ thể của Kubernetes HPA, KEDA trigger và Kafka scaler phải dựa vào phiên bản/cấu hình thực tế; bài học này không áp một manifest mặc định cho mọi hệ thống.

## 23. Kafka so với RabbitMQ, SQS và Kinesis

Không thể áp nguyên quy tắc `consumer_count ≤ partition_count` của Kafka cho mọi message queue.

| Nền tảng | Đơn vị song song chính | Thứ tự và giới hạn |
| --- | --- | --- |
| **Kafka** | Partitions được chia trong consumer group | Thứ tự theo partition; group member assignment giới hạn số consumer active |
| **Kafka Streams** | Tasks/partitions của topology, có thể kèm state stores | Số partition nguồn/repartition tác động task parallelism và state recovery |
| **RabbitMQ** | Queue có nhiều competing consumers, prefetch và ack | Không có “Kafka partition ceiling” tương đương; ordering với nhiều consumers/acks có thể phức tạp |
| **Amazon SQS Standard** | Message được worker nhận theo cơ chế queue, visibility timeout | At-least-once, có thể duplicate và không bảo đảm strict ordering |
| **Amazon SQS FIFO** | Message groups và cơ chế FIFO | Trong một message group, xử lý tuần tự theo contract; nhiều groups cho phép song song |
| **Amazon Kinesis Data Streams** | Shards, partition keys và consumer models | Thứ tự theo shard; shard throughput/limits và split/merge ảnh hưởng scaling |

### RabbitMQ

Một queue có thể có nhiều competing consumers nhận messages; prefetch giới hạn số messages chưa ack chuyển tới từng consumer hoặc channel tùy cấu hình/cơ chế broker. Quá nhiều unacked messages có thể làm tăng memory và gây xử lý lệch tải. Việc thêm consumers giúp tới khi queue, broker, application hoặc downstream đạt trần. Với workload cần strict order, dùng single-active-consumer/thiết kế tuần tự tương ứng hoặc thay mô hình xử lý thay vì giả định nhiều worker luôn giữ FIFO end-to-end.

### SQS Standard

Tăng workers có thể tăng concurrency nhưng cần:
- Visibility timeout đủ cho processing hoặc extend khi cần.
- Idempotency vì duplicate delivery có thể xảy ra.
- DLQ và giới hạn số lần receive.
- Concurrency budget theo downstream.
- Long polling/batching để kiểm soát cost/throughput.

### SQS FIFO

Message group ID là đơn vị serialization có ý nghĩa. Nếu tất cả messages dùng một `MessageGroupId`, throughput concurrency bị giới hạn dù queue có nhiều workers. Tách nhiều group chỉ hợp lý nếu các group có thể xử lý độc lập. Cần hiểu deduplication và ordering của provider.

### Kinesis

Partition key quyết định shard routing; shard có throughput/quota hữu hạn. Tăng shard có thể tăng capacity nhưng cần xem consumer fan-out, checkpoint, shard lifecycle và ordering khi reshard. Các con số quota thay đổi theo service mode và nhà cung cấp, vì vậy không nên sao chép trực tiếp giá trị từ Kafka.

**Thông điệp chung:** tìm đúng đơn vị phân phối công việc và giới hạn concurrency của hệ broker đang dùng, sau đó kết hợp với loại workload và ordering nghiệp vụ.

## 24. Xử lý poison message và retry mà không khóa cả partition

Một record có schema sai hoặc dữ liệu vi phạm invariant có thể gây exception mỗi lần xử lý. Nếu consumer liên tục retry cùng offset mà không có giới hạn, partition có thể ngừng tiến triển dù các record phía sau hoàn toàn hợp lệ.

Cần phân biệt:
- **Transient:** timeout, 503, broker/network temporary; có thể retry với deadline/budget.
- **Permanent:** schema không hỗ trợ, dữ liệu sai không thể xử lý; cần báo lỗi/DLQ hoặc quy trình sửa dữ liệu.
- **Unknown outcome:** external operation có thể đã thành công nhưng response mất; cần reconciliation/idempotency.

Một chính sách:
1. Kiểm tra schema và phân loại lỗi.
2. Với transient, retry ít lần có backoff/jitter; tránh giữ poll loop bị chặn quá `max.poll.interval.ms`.
3. Nếu cần chờ dài, chuyển qua retry topic/task store có lịch thực thi và đủ metadata để không mất quan hệ nghiệp vụ.
4. Với permanent, đưa record vào DLQ cùng error class, original topic/partition/offset, event ID và correlation ID không nhạy cảm.
5. Commit/advance offset nguồn chỉ sau khi cơ chế lưu DLQ hoặc xử lý thay thế đã **bền vững** theo hợp đồng.
6. Có owner kiểm tra DLQ, cảnh báo age, replay process và quy tắc dữ liệu nhạy cảm.
7. Khi replay, idempotency phải chống side effects trùng.

Lưu ý: đẩy record lỗi sang DLQ rồi xử lý tiếp có thể phá strict ordering của aggregate nếu record sau được xử lý trước record lỗi. Khi ordering là bắt buộc, cần **block/lane quarantine** hoặc workflow recovery giữ thứ tự, thay vì DLQ toàn cục rồi chạy tiếp vô điều kiện.

## 25. Metrics và dashboards dành cho consumer scaling

Một dashboard hữu ích nên có cả **traffic, tiến độ xử lý, tài nguyên và chất lượng nghiệp vụ**.

| Nhóm | Chỉ số | Dùng để quyết định |
| --- | --- | --- |
| Input | `records_in_per_second` / bytes in | Producer tăng tải thật hay burst tạm thời? |
| Backlog | Lag theo group/topic/partition | Partition nào đang ùn? |
| Backlog age | Oldest unprocessed message age | SLO xử lý trễ bao nhiêu? |
| Output | Successful completed events per second | Scale có tăng **completion throughput** không? |
| Processing | Handler p50/p95/p99, time by event type | CPU, IO, lock hay payload nặng? |
| Consumers | Members assigned, partitions per member | Consumer nhàn rỗi vì trần partition? |
| Rebalance | Count/duration, partitions revoked | Scale gây downtime hay churn? |
| Offset | Commit latency/error, replay/duplicate rate | Độ an toàn và tiến độ processing |
| Failures | Retry rate, DLQ rate, poison event counts | Lỗi transient hay permanent? |
| Memory | In-flight queue length, heap/GC, OOM | Backpressure có hiệu lực? |
| CPU | CPU usage, throttling, quota | Workload CPU-bound? |
| Database | Connection pool active/pending, latency, locks | Downstream đã bão hòa? |
| External API | 429/503, timeout, quota remaining | Scale có vượt rate limit? |
| Business | Event-to-effect latency, pending workflows | Người dùng có đạt kết quả đúng hạn? |

Nhãn metric cần được thiết kế tránh cardinality bùng nổ. Không đưa raw `orderId`, `customerId`, API secret hoặc payload vào time-series labels. Có thể đo theo event type, topic, partition, consumer group và service, với số nhãn được kiểm soát.

### Hai câu hỏi quan trọng

- **Scale hiệu quả chưa?** Sau tăng từ 4 lên 8 members, completion rate có tăng, lag age có giảm và downstream có còn headroom không?
- **Scale đúng chỗ chưa?** Lag có tập trung ở một partition/key, một event type hay một backend giới hạn công suất không?

Một dashboard chỉ vẽ “number of pods” và “total lag” không đủ để trả lời.

## 26. Phân tích bottleneck theo trình tự

Khi lag tăng, một quy trình điều tra:

```text
Lag tăng?
   |
   +→ Producer rate tăng hay processing rate giảm?
   |
   +→ Lag phân bố đều hay một partition/key nóng?
   |      |
   |      +→ Một partition nóng: key skew / poison / heavy record
   |      +→ Nhiều partition nóng: capacity hoặc downstream
   |
   +→ CPU throttling cao?
   |      +→ CPU-bound: profile, tăng CPU/slots có ích
   |
   +→ DB/API latency hoặc 429 tăng?
   |      +→ Downstream-bound: giới hạn concurrency, tối ưu backend
   |
   +→ Rebalance count tăng?
   |      +→ Membership/poll interval/rolling deploy issue
   |
   +→ In-flight queue đầy?
          +→ Backpressure cần thiết; xử lý backlog có kế hoạch
```

Ở mỗi nhánh, ưu tiên đo **completion throughput**. Consumer tăng tốc poll nhưng không hoàn tất side effect có thể chỉ chuyển backlog từ Kafka sang memory hoặc task store, không cải thiện SLO.

Thử nghiệm scale nên có một biến chính (replicas, worker concurrency hoặc DB pool) và tải đủ đại diện. Đừng tăng tất cả cùng lúc rồi không biết yếu tố nào tạo lợi ích.

## 27. Bài toán thực tế: Order Projection và Shipment API

Giả sử hệ thống có hai consumer groups khác nhau trên cùng event stream:

```text
orders.events (24 partitions, key=orderId)
       |
       +--> order-projection group
       |      ghi read model PostgreSQL
       |      mục tiêu: < 3s event-to-view
       |
       +--> shipment-request group
              gọi shipping partner API
              quota: 120 requests/second
              mục tiêu: < 2 phút để tạo shipment
```

### Consumer A: Order Projection

Đặc điểm:
- Ghi database, nhiều record nhỏ.
- Cần ordering per orderId.
- Dễ batch và dùng upsert version-aware nếu hợp đồng cho phép.

Thiết kế:
- Dùng key `orderId`, 24 partition cho khả năng chia công việc.
- Benchmark số writes/giây, CPU/IOPS/locking DB.
- Chọn số consumer ≤ partition capacity hữu ích và DB connection budget.
- Tránh xử lý cùng orderId song song rồi ghi state cũ đè state mới.
- Dùng inbox/idempotency key, kiểm tra optimistic sequence/version.
- Đo max lag và age per partition, database p99 và duplicate handling.

### Consumer B: Shipment Request

Đặc điểm:
- Gọi HTTP API bên ngoài với quota 120 req/giây.
- Latency mỗi request có thể dài; kết quả timeout đôi khi không xác định.
- Cần idempotency, retry budget và reconciliation.

Thiết kế:
- Consumer group riêng có offset/lag riêng.
- Bounded concurrency tính từ quota, latency và thời gian xử lý, không scale bằng cách cho mỗi pod 120 req/giây.
- Limiter toàn cục hoặc phân quota có kiểm soát cho mọi replicas.
- Nếu partner 429, giảm sending rate và giữ backlog an toàn.
- Sử dụng `shipmentOperationId` làm idempotency key tại provider khi có hỗ trợ.
- DLQ/manual intervention cho lỗi permanent; không phá ordering của lifecycle shipment.
- Theo dõi age của request cũ nhất và số shipment pending.

**Điểm học được:** cùng 24 Kafka partitions không có nghĩa hai consumer groups nên có cùng số replicas hoặc worker threads. Một group giới hạn bởi PostgreSQL throughput và ordering; group kia giới hạn bởi API quota và latency.

## 28. Bài toán tính quy mô minh họa

Hệ thống có:
- Topic 16 partitions; group đang có 4 consumer pods.
- Mỗi pod xử lý trung bình 400 events/giây khi downstream khỏe và các partition được phân phối hợp lý.
- Producer tăng lên 2.400 events/giây.
- Database có năng lực bền vững 2.000 writes/giây.
- Mỗi event yêu cầu một DB write.

Nhận định:
1. Với 4 pods, năng lực consumer lý thuyết 1.600 events/giây: lag tăng ~800/giây.
2. Tăng lên 6 pods, consumer-side lý thuyết 2.400/giây; nhưng database chỉ đủ 2.000/giây.
3. Khi đó tổng **completed events** không thể bền vững đạt 2.400/giây nếu chưa cải thiện DB hoặc thay mô hình writes.
4. Tăng tới 16 pods sẽ không khắc phục giới hạn DB; có thể gây lock/connection contention và giảm throughput.
5. Cần tối ưu batch, query/index, partitioning dữ liệu hoặc cách dùng DB, đồng thời kiểm soát ingress/backlog/age SLO.

Các giả định số học chỉ dùng để hướng dẫn capacity reasoning, không là benchmark cho Kafka hoặc PostgreSQL. Khi quyết định production cần đo steady-state, p99 latency, spikes, retries, skew và headroom.

## 29. Kiểm thử load, rebalance và fault tolerance

Một chiến lược kiểm tra trước khi tăng scale:

**Tình huống A — Cân bằng phân vùng**
- Tạo test data có phân phối key gần production.
- Kiểm tra assignment, lag/throughput từng partition.
- So sánh 2, 4, 8 consumer members và tìm điểm diminishing returns.

**Tình huống B — Hot key**
- Cho 60–80% lưu lượng dùng một key/tenant.
- Xác định partition nóng, backlog age và memory.
- Kiểm tra việc tăng replicas có thực sự làm giảm age của key đó không.
- Đề xuất shard key mới chỉ khi không phá ordering nghiệp vụ.

**Tình huống C — CPU-bound**
- Tăng payload complexity trong khi giữ input rate.
- Quan sát CPU throttling, GC, processing time và lag.
- Benchmark workers/CPU limit cùng nhau.

**Tình huống D — DB/provider-bound**
- Giới hạn DB writes hoặc HTTP quota có kiểm soát.
- Scale replicas và xác nhận rate limiter/backpressure giới hạn tải.
- Kiểm tra retries không tạo bão 429/503.

**Tình huống E — Rebalance/rolling deploy**
- Thêm/rút members khi đang xử lý event.
- Kill một member ở thời điểm side effect đã commit nhưng offset chưa commit.
- Xác minh replay không tạo duplicate side effect.
- Đo thời gian rebalance và tiến độ hồi phục.

**Tình huống F — Poison message**
- Một record sai schema, rồi các record hợp lệ.
- Kiểm tra DLQ/retry budget, không mất bản ghi và policy ordering.
- Nếu pause partition, bảo đảm alarm/owner có khả năng xử lý.

**Tình huống G — Backlog recovery**
- Tạm ngưng downstream, cho backlog tích tụ.
- Mở lại downstream và đo thời gian catch-up.
- Kiểm tra retention, pending age, connection pool và DLQ backlog.

Test cần môi trường được phép và workload đại diện. Không mặc định bắn lưu lượng gây quá tải production; nếu dùng chaos/load canary trong production phải có quy trình phê duyệt và giới hạn an toàn.

## 30. Những anti-pattern phổ biến

**“Lag tăng thì tăng pod.”** Nếu partition ceiling hoặc downstream đã bão hòa, chỉ tăng chi phí, rebalance và connection contention.

**“Có 100 partitions thì chắc chắn đạt 100 lần throughput.”** Broker, CPU, DB, network, key skew và consumer implementation có thể đặt trần thấp hơn nhiều.

**“Một consumer group cho mỗi replica để mọi replica có việc.”** Điều này khiến mỗi replica đọc toàn bộ event và có thể nhân side effects, không phải scale một logical consumer.

**“Commit ngay sau poll.”** Nếu record chưa được xử lý bền vững, crash có thể làm mất công việc.

**“Dùng worker pool nhưng commit offset lớn nhất đã xong.”** Một offset thấp còn pending có thể bị bỏ qua sau restart.

**“Tất cả messages dùng key=tenantId.”** Tenant lớn trở thành hot partition; cần xác định ordering thật sự theo tenant hay aggregate nhỏ hơn.

**“Tăng partition count không ảnh hưởng business semantics.”** Mapping theo key có thể thay đổi, ảnh hưởng per-key ordering trong migration.

**“Async là không có giới hạn.”** Queue chỉ trì hoãn áp lực, backlog có retention và chi phí; downstream quota vẫn tồn tại.

**“Retry lỗi nào cũng được.”** Permanent lỗi không tự hết; retry không giới hạn khóa partition và làm hệ thống thêm tải.

**“Exactly once chỉ cần bật flag Kafka.”** Side effect với DB, email, HTTP vẫn cần idempotency/transaction/reconciliation tùy ranh giới.

**“Chỉ đo total lag.”** Một hot partition có thể quyết định SLO của nhóm sự kiện quan trọng dù tổng lag không quá cao.

**“Tối đa hóa số message được poll.”** Poll rate không đồng nghĩa số event xử lý thành công.

**“Đặt concurrency=100 khi chỉ có 8 partition sẽ giải quyết lag.”** Concurrency hữu ích bị giới hạn bởi partition assignment và workload; cùng một member có thể nhận nhiều partition nhưng không tự nhân bản capacity.

## 31. Checklist thiết kế consumer scaling

Trước khi quyết định tăng replica/concurrency, xác nhận:

### Dữ liệu và ordering
- [ ] Partition/shard/message-group key phản ánh đúng đơn vị ordering nghiệp vụ.
- [ ] Cardinality và traffic distribution theo key đã được đo.
- [ ] Đã biết tác động của việc tăng số partition/reshard tới key mapping và consumer state.
- [ ] Handler chịu được duplicate, replay và sự kiện sai thứ tự ở mức hợp đồng cho phép.

### Capacity
- [ ] Có số đo input rate, completion rate, peak và backlog age.
- [ ] Đã phân loại bottleneck CPU, I/O, DB, external API hay skew.
- [ ] Có benchmark per partition/worker và giới hạn downstream.
- [ ] Có max in-flight, queue, connection pool, rate limit và retry budget.
- [ ] Các replica mới thực sự nhận partition/workload có ích.

### Độ an toàn xử lý
- [ ] Offset/ack chỉ được xác nhận khi công việc hoàn thành bền vững.
- [ ] Worker concurrency không phá ordering hoặc có cơ chế xử lý rõ.
- [ ] Shutdown/rebalance drain và revoke callbacks đã được kiểm thử.
- [ ] Poison/retry/DLQ policy có owner và không tạo bế tắc vô hạn.
- [ ] Idempotency key phù hợp với business operation.

### Vận hành
- [ ] Autoscaling có cooldown và trần dựa trên khả năng thật.
- [ ] Dashboard thể hiện per-partition lag, oldest age, p95/p99, rebalances và backend saturation.
- [ ] Có kịch bản catch-up sau downtime và kế hoạch khi lag vượt retention.
- [ ] Có runbook giới hạn concurrency khi downstream bị quá tải.
- [ ] Có owner theo consumer group, topic, broker và downstream.

## 32. Bài tập thực hành

### Bài 1 — Trần song song

Topic `orders.events` có 12 partitions. Consumer group `order-projection` chạy 3, sau đó 6, 12 và 18 pods. Mô tả sự phân công partition điển hình, số consumer có việc và tại sao 18 pods không mặc định tốt hơn 12.

### Bài 2 — Chọn partition key

Events gồm `OrderCreated`, `OrderReserved` và `OrderPaid`. Nghiệp vụ phải áp dụng trạng thái theo thứ tự cho mỗi order. So sánh key `orderId`, `tenantId` và random UUID; giải thích ưu/nhược về load skew và ordering.

### Bài 3 — Catch-up time

Producer ghi 1.800 event/giây; consumer xử lý bền vững 2.200 event/giây; backlog hiện 120.000 events. Tính thời gian lý thuyết để xả backlog nếu các tốc độ giữ ổn định. Nêu ba yếu tố khiến thực tế lâu hơn.

### Bài 4 — Async offset commit

Một partition có offsets 100, 101, 102. Worker hoàn thành 101 và 102 trước 100. Hãy quyết định offset nào có thể commit an toàn theo quy tắc contiguous completion và giải thích khi consumer restart.

### Bài 5 — Workload-bound scale

Có 16 partitions, 8 consumer pods, API provider chỉ cho 80 requests/giây. Mỗi pod tự đặt limiter 80 requests/giây. Giải thích vấn đề, đề xuất cơ chế hạn mức tổng và metrics kiểm chứng.

### Bài 6 — Rebalance khi xử lý lâu

Handler mất 7 phút nhưng `max.poll.interval.ms` là 5 phút trong cấu hình minh họa. Thiết kế lại poll/processing hoặc task handoff để không liên tục rebalance và vẫn tránh mất record.

### Bài 7 — Poison event và order

Một event thiếu field bắt buộc ở offset 400, các event sau là update cùng order. Hãy thiết kế retry, DLQ/quarantine, offset policy và cách bảo đảm trạng thái order không bị xử lý vượt event lỗi.

### Bài 8 — So sánh broker

Cùng workload gửi thông báo, xác định cơ chế song song khi dùng Kafka partitions, RabbitMQ competing consumers, SQS Standard và SQS FIFO message groups. Những ràng buộc nào khác nhau về ordering/duplicate?

### Bài 9 — Autoscaling

Thiết kế chính sách scale từ 2 tới 12 pods dựa trên oldest unprocessed age và completion throughput. Bổ sung cooldown, maxReplicas theo partition count, DB capacity và cách drain an toàn khi scale xuống.

### Bài 10 — Luồng nghiệp vụ cuối

Consumer nhận `PaymentCaptured` rồi ghi database và gọi service gửi hóa đơn. Mô tả inbox/idempotency, transactional boundaries và tình huống crash giữa DB commit, gửi invoice và offset commit.

## 33. Ghi nhớ

- **Số partition/shard/message group và phân phối key giới hạn parallelism thực, không phải số pod duy nhất.**
- **Kafka consumer group thường phân mỗi partition cho một member; scale vượt số partition không tạo throughput chỉ vì có thêm replica.**
- **Partition key là quyết định về ordering và hot-key risk**, cần dựa trên aggregate boundary và traffic distribution.
- **CPU-bound, I/O-bound, DB-bound, external API-bound cần chiến lược concurrency khác nhau.**
- **Đo completed processing rate và message age**, không chỉ poll rate hoặc total lag.
- **Tăng consumer có thể làm downstream nghẽn hơn** nếu không có connection/rate/concurrency budget.
- **Poll/commit/rebalance là phần của correctness**: ack sai thời điểm có thể mất công việc, xử lý song song sai có thể phá thứ tự.
- **Backpressure phải giữ buffer hữu hạn và lưu backlog tại nơi bền vững phù hợp**, không chuyển vô hạn vào heap.
- **Idempotency và reconciliation là điều kiện vận hành khi có replay/duplicate**; không suy rộng exactly-once qua các side effects bên ngoài.
- **Autoscaling cần tính cả partition ceiling, skew, rebalance, startup và shutdown**, không scale chỉ theo một biểu đồ lag.
- **Mỗi nền tảng queue/stream có ngữ nghĩa khác nhau**: không sao chép mù các quy tắc Kafka sang RabbitMQ, SQS FIFO hoặc Kinesis.

Một consumer architecture có khả năng mở rộng tốt **không chỉ đọc nhanh hơn**, mà còn **hoàn tất đúng nhiều công việc hơn trong giới hạn tài nguyên và hợp đồng nghiệp vụ**, đồng thời biết giảm tốc, hồi phục và xử lý trùng khi điều kiện vận hành thay đổi.

### Tài liệu tham khảo

- Apache Kafka — Consumer Configuration: https://kafka.apache.org/documentation/#consumerconfigs
- Apache Kafka — Design and Consumer Groups: https://kafka.apache.org/documentation/#design
- Spring for Apache Kafka — Reference Documentation: https://docs.spring.io/spring-kafka/reference/
- Kafka Streams — Core Concepts: https://kafka.apache.org/documentation/streams/core-concepts
- RabbitMQ — Consumer Prefetch: https://www.rabbitmq.com/docs/consumer-prefetch
- AWS SQS — FIFO Queue Logic: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-understanding-logic.html
- AWS Kinesis Data Streams — Key Concepts: https://docs.aws.amazon.com/streams/latest/dev/key-concepts.html
- Kubernetes — Horizontal Pod Autoscaling: https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/
- KEDA — Kafka Scaler: https://keda.sh/docs/latest/scalers/apache-kafka/
- Google SRE Book — Addressing Cascading Failures: https://sre.google/sre-book/addressing-cascading-failures/

Các ví dụ, công thức và cấu hình trong bài dùng để suy luận kiến trúc. Cần kiểm chứng phiên bản Kafka client, Spring Kafka, broker, plugin autoscaler và đặc điểm workload thực tế trước khi áp dụng vào production.

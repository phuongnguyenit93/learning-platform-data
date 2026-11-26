# Đặc điểm multi-process nhiều máy khi mở rộng Spring Batch

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích mô hình **multi-process, multi-machine**: các worker chạy trên JVM/process độc lập, có thể ở nhiều máy hoặc container khác nhau.
- Phân biệt tài nguyên **riêng từng process** (heap, thread, connection pool cục bộ) với tài nguyên **dùng chung toàn hệ thống** (DB, storage, broker, quota API, JobRepository khi được chia sẻ).
- So sánh **remote partitioning** và **remote chunking** về quyền sở hữu reader, nơi tạo chunk, nơi quản lý `StepExecution` và giao thức trao đổi thông điệp.
- Thiết kế partition và xử lý đồng thời sao cho các worker không bỏ sót, không chồng lấn, có thể chạy lại an toàn khi mất process hoặc kết nối mạng.
- Hiểu vì sao delivery/reply/ack có thể bị lặp hoặc mất, và vì sao cần **idempotent writer, correlation, timeout, backpressure và reconciliation**.
- Ước lượng hiệu quả scale-out, chi phí serialization/network, số worker, DB connection, CPU/memory, độ lệch partition và khả năng đáp ứng SLA.
- Lập checklist triển khai, giám sát và kiểm thử lỗi cho job Spring Batch chạy qua nhiều máy.

## 1. Multi-process nhiều máy là gì?

Trong một ứng dụng Spring Batch chạy **single-process nhiều luồng**, các worker thread cùng nằm trong một JVM và cùng chia sẻ heap. Với mô hình **multi-process nhiều máy**, manager và worker có thể nằm ở **những JVM riêng biệt**, triển khai trên các container/pod hoặc các host khác nhau. Chúng giao tiếp qua mạng, thường bằng messaging middleware hoặc cơ chế phân phối công việc phù hợp.

~~~mermaid
flowchart LR
    S["Scheduler / API"] --> M["Manager JVM<br/>Job orchestration"]
    M --> Q["Middleware<br/>requests / replies"]
    Q --> W1["Worker JVM A<br/>CPU / heap / pool riêng"]
    Q --> W2["Worker JVM B<br/>CPU / heap / pool riêng"]
    Q --> W3["Worker JVM C<br/>CPU / heap / pool riêng"]
    W1 --> DB["Business DB / Storage dùng chung"]
    W2 --> DB
    W3 --> DB
    M --> JR["JobRepository / metadata"]
    W1 -. "khi kiến trúc yêu cầu" .-> JR
    W2 -. "khi kiến trúc yêu cầu" .-> JR
    W3 -. "khi kiến trúc yêu cầu" .-> JR
~~~

**Một process khác không đơn thuần là “thread khác”.** Trong Java, object thường không thể được tham chiếu trực tiếp qua hai JVM: để giao việc, cần mô tả dữ liệu, serialize/deserialize, định danh công việc và giao thức trao đổi. Việc mạng có thể timeout, broker có thể giao lại và một worker có thể biến mất sau khi đã commit khiến tính đúng đắn khó hơn mô hình cục bộ.

Mặt khác, nhiều JVM cho phép khai thác thêm CPU/RAM từ nhiều host và giảm phạm vi ảnh hưởng của **một worker JVM bị lỗi**. Tuy nhiên, nếu mọi JVM cùng ghi vào một DB đã bão hòa, thêm node không tăng thông lượng mà còn làm tăng contention.

### “Nhiều process” và “nhiều máy” là hai trục khác nhau

| Cách triển khai | Đặc trưng | Khi nào có ích? |
| --- | --- | --- |
| Một JVM, nhiều thread | Heap và bean dùng chung; không cần mạng giữa thread | Scale-up vừa phải, workload vừa một node |
| Nhiều JVM trên **một máy** | Heap/GC riêng; vẫn cạnh tranh CPU/RAM/đĩa cùng host | Cô lập lỗi process, nhưng chưa tăng năng lực vật lý |
| Nhiều JVM trên **nhiều máy** | Mỗi JVM có CPU/RAM/quota riêng; giao tiếp qua network | Scale-out CPU, giảm blast radius, worker linh hoạt |
| Nhiều pod trên Kubernetes | Process cách ly theo container, điều phối qua scheduler | Quản lý replica, resource limit, rolling deploy, health check |
| Worker JVM kết nối DB/middleware chung | Scale xử lý nhưng chia sẻ các điểm nghẽn ngoại vi | Cần ngân sách DB, broker, API trên toàn cluster |

Lưu ý container trên cùng node vẫn có thể tranh tài nguyên vật lý. Số replica là **số đơn vị triển khai**, không phải số host vật lý được cấp riêng.

## 2. Ranh giới chia sẻ: cái gì riêng, cái gì vẫn chung?

| Thành phần | Trong từng worker JVM | Trên toàn hệ thống | Hệ quả |
| --- | --- | --- | --- |
| Java heap, static variables, bean singleton | Riêng từng JVM | Không tự đồng bộ giữa JVM | `synchronized` và `AtomicLong` không tạo khóa/đếm toàn cluster |
| Thread pool, `ThreadLocal`, transaction context | Riêng process/thread | Không lan qua request message | Mỗi worker phải mở transaction theo ngữ cảnh của chính nó |
| JDBC connection pool | `DataSource`/pool riêng từng replica | DB server giới hạn tổng session | `poolSize=10` trên 5 pod có thể tạo đến 50 session |
| `StepExecution`/checkpoint | Là metadata logic của Spring Batch | Có thể lưu trong shared `JobRepository` theo kiến trúc | Cần ownership, cập nhật trạng thái và restart nhất quán |
| Business table / index / lock | Truy cập qua connection cục bộ | Cùng DB/index/row | Hai worker có thể tranh lock dù ở hai máy |
| Object storage / network / broker | Client local ở mỗi process | Endpoint và quota dùng chung | Tổng RPS/băng thông có thể đạt trần |
| File tạm và local disk | Thường riêng từng node/container | Không mặc nhiên hiện trên node khác | Không lưu checkpoint bắt buộc trên disk ephemeral của worker |
| Scheduler và job launch | Có thể chạy ở nhiều process | Cần điều phối để tránh trùng job ngoài ý muốn | Identifying `JobParameters` + repository chung và khi cần khóa toàn job |

Ví dụ: mỗi pod dùng `HikariDataSource.maximumPoolSize=12`, có bốn pod worker và một pod manager. Riêng worker đã có thể dùng tới `4 × 12 = 48` session DB, chưa kể manager và ứng dụng realtime. **Tăng số pod phải đi kèm phép tính ngân sách tài nguyên chung**; không suy luận DB có thể chịu tải chỉ vì mỗi pod còn CPU trống.

### Transaction không đi theo thông điệp

Spring Framework với transaction imperative thường ràng buộc `PlatformTransactionManager` và resource vào **thread hiện tại**. Transaction JDBC mở trong manager **không được “gói” rồi chuyển qua mạng** để worker tiếp tục dùng. Worker xử lý dữ liệu phải có transaction manager/connection riêng.

Ngay cả khi manager và worker trỏ đến cùng DB, việc chúng thuộc cùng một `JobExecution` **không** biến các thao tác thành một transaction phân tán. Các chunk đã commit ở worker A không tự rollback vì worker B thất bại.

## 3. Hai mô hình phân phối quan trọng trong Spring Batch

Spring Batch thường dùng hai hướng khi xử lý dữ liệu lớn qua nhiều JVM:

- **Remote partitioning**: manager **chia miền dữ liệu/công việc**, remote worker chạy **worker step** tương ứng, thường tự đọc/ghi vùng dữ liệu.
- **Remote chunking**: manager **đọc dữ liệu và tạo chunk**, gửi **nội dung chunk** qua middleware để worker xử lý/ghi và phản hồi.

Chúng khác nhau không chỉ ở hình thức message mà cả nơi quản lý reader, checkpoint, nhu cầu network và điểm nghẽn.

| Tiêu chí | Remote partitioning | Remote chunking |
| --- | --- | --- |
| Đơn vị giao việc | Tham số partition, `StepExecution`/miền dữ liệu | Chunk chứa các item đã đọc |
| Reader chính | Ở worker step từng partition | Ở manager |
| Processor/writer | Ở worker | Ở worker |
| Metadata/checkpoint | Theo `StepExecution` của partition; worker cần truy cập metadata theo giao thức/cấu hình đã chọn | Reader và tiến độ chunk thuộc step ở manager; worker cần giao thức request/reply |
| Lượng dữ liệu trên mạng | Thường message nhỏ chứa ID/range/file path | Payload item có thể rất lớn, lặp theo mỗi chunk |
| Điểm nghẽn đặc trưng | DB nguồn chia được không? Partition lệch tải? | Manager reader đơn luồng? Broker backlog/payload? |
| Độ linh hoạt chia tải | Chia theo file, tenant, ID range; có thể tăng số partition | Cân bằng theo chunk được gửi đến worker, phụ thuộc broker và consumer |
| Phục hồi | Phục hồi partition/step từ metadata, key ổn định | Phục hồi reader/progress manager, đối chiếu chunk đã xử lý khi reply/ack mất |
| Phù hợp | Input có thể chia thành miền độc lập, worker tự truy cập nguồn | Manager đọc đủ nhanh nhưng xử lý/ghi tốn CPU/I/O |

### Sơ đồ đối chiếu

~~~mermaid
flowchart TD
    subgraph RP["Remote partitioning"]
      PM["Manager: Partitioner"] --> PQ["Thông điệp: partition id + range"]
      PQ --> PW1["Worker A: Reader → Processor → Writer"]
      PQ --> PW2["Worker B: Reader → Processor → Writer"]
    end
    subgraph RC["Remote chunking"]
      CM["Manager: Reader → Chunk"] --> CQ["Thông điệp: danh sách item"]
      CQ --> CW1["Worker A: Processor → Writer"]
      CQ --> CW2["Worker B: Processor → Writer"]
      CW1 --> CR["Reply / kết quả"]
      CW2 --> CR
      CR --> CM
    end
~~~

Cấu trúc request/reply và thành phần metadata phụ thuộc Spring Batch Integration, transport, phiên bản framework và cách cấu hình. Đừng giả định **một class cấu hình áp dụng y nguyên cho mọi release**.

## 4. Remote partitioning: phân chia dữ liệu và trạng thái worker

Giả sử job nhập đơn hàng từ snapshot đã đóng, gồm 12 triệu record có khóa `(snapshot_id, order_id)`. Manager chia thành 12 khoảng ID không giao nhau; sáu worker slot ở ba pod xử lý từng khoảng. Worker nào nhận khoảng nào không quan trọng đối với kết quả **nếu** mọi worker tuân thủ cùng quy tắc partition, checkpoint và idempotency.

~~~text
Snapshot: orders-2026-11-25

Manager:
    partition000 -> [1, 1_000_001)
    partition001 -> [1_000_001, 2_000_001)
    ...
    partition011 -> [11_000_001, 12_000_001)

Worker pods:
    pod-A: 2 worker slots
    pod-B: 2 worker slots
    pod-C: 2 worker slots

12 partitions, tối đa 6 đang chạy đồng thời theo capacity đã đặt.
~~~

Các khoảng `[startInclusive, endExclusive)` liền nhau, không overlap về **giá trị khóa**. Nếu có ID thưa, số record thực của từng khoảng vẫn có thể rất khác nhau; chia đều độ rộng không bảo đảm cân bằng thời gian.

### Ba bất biến tối thiểu của partition

1. **Bao phủ đầy đủ:** mọi record của snapshot nằm trong đúng một miền được giao.
2. **Không chồng lấn:** không có hai partition cùng sở hữu một business key trong một lần phân công hợp lệ.
3. **Tái lập khi restart:** cùng `JobInstance` phải biết lại partition name, boundary, snapshot và checkpoint tương thích.

Thêm bất biến nghiệp vụ: **worker phải xử lý độc lập hoặc kết hợp kết quả đúng cách**. Hai partition đọc ID khác nhau nhưng cùng update một dòng `daily_total` theo phép đọc–sửa–ghi có thể mất cập nhật hoặc tranh lock.

### Một `Partitioner` thuần dữ liệu (Spring Batch 5.x)

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class FixedRangePartitioner implements Partitioner {

    private final long firstInclusive;
    private final long endExclusive;

    public FixedRangePartitioner(long firstInclusive, long endExclusive) {
        if (firstInclusive < 0 || endExclusive < firstInclusive) {
            throw new IllegalArgumentException("Invalid range");
        }
        this.firstInclusive = firstInclusive;
        this.endExclusive = endExclusive;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long total = endExclusive - firstInclusive;
        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        if (total == 0) {
            return result;
        }

        int count = (int) Math.min(total, (long) gridSize);
        long base = total / count;
        long remain = total % count;
        long start = firstInclusive;

        for (int i = 0; i < count; i++) {
            long width = base + (i < remain ? 1L : 0L);
            long end = start + width;

            ExecutionContext context = new ExecutionContext();
            context.putLong("startId", start);
            context.putLong("endExclusive", end);
            result.put(String.format("partition%03d", i), context);
            start = end;
        }

        if (start != endExclusive) {
            throw new IllegalStateException("Partition coverage mismatch");
        }
        return result;
    }
}
~~~

Bài toán ví dụ sử dụng ID không âm, khoảng vừa kiểu `long`, dữ liệu snapshot cố định. `gridSize` là số partition được yêu cầu, **không phải số JVM**. Số thread/consumer/worker slot thực tế có thể nhỏ hơn hoặc lớn hơn số process do cấu hình runtime.

### Reader riêng của worker qua `@StepScope`

Worker nhận `StepExecutionContext`, được framework đặt vào ngữ cảnh worker step theo cấu hình remote partitioning. Một reader có thể bind các range đã gửi:

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderRow(String snapshotId, long orderId, String payload) {}

@Configuration
class WorkerReaderConfiguration {

    @Bean
    @StepScope
    JdbcCursorItemReader<OrderRow> partitionReader(
            DataSource dataSource,
            @Value("#{jobParameters['snapshotId']}") String snapshotId,
            @Value("#{stepExecutionContext['startId']}") Long startId,
            @Value("#{stepExecutionContext['endExclusive']}") Long endExclusive) {

        if (snapshotId == null || startId == null || endExclusive == null
                || startId >= endExclusive) {
            throw new IllegalArgumentException("Invalid partition context");
        }

        return new JdbcCursorItemReaderBuilder<OrderRow>()
                .name("partitionReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT order_id, payload
                    FROM order_snapshot
                    WHERE snapshot_id = ?
                      AND order_id >= ?
                      AND order_id < ?
                    ORDER BY order_id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setString(1, snapshotId);
                    ps.setLong(2, startId);
                    ps.setLong(3, endExclusive);
                })
                .rowMapper((rs, ignored) ->
                        new OrderRow(
                                snapshotId,
                                rs.getLong("order_id"),
                                rs.getString("payload")))
                .saveState(true)
                .build();
    }
}
~~~

`@StepScope` cô lập reader theo `StepExecution`, không theo host hay thread bất kỳ. Trong local hoặc remote partitioning, mỗi partition có một `StepExecution` riêng. Nhưng nếu code của ứng dụng lại tự tạo thêm thread xử lý chung một reader trong **cùng** `StepExecution`, bean `@StepScope` không tự biến cursor thành thread-safe.

Snapshot cần tồn tại và được worker truy cập nhất quán. Không lưu một path local như `C:\\temp\\batch.csv` hoặc `/tmp/batch.csv` rồi trông chờ worker trên máy khác tự nhìn thấy file đó; dùng object storage hoặc volume chia sẻ có contract rõ.

## 5. Worker step, writer và liên kết manager–worker

Trong remote partitioning, worker step thường là step chunk-oriented, nhận một miền dữ liệu và transaction manager của chính worker. Với API Spring Batch **5.x**:

~~~java
@Bean
Step remoteWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<OrderRow> partitionReader,
        ItemWriter<OrderRow> outputWriter) {

    return new StepBuilder("remoteWorkerStep", jobRepository)
            .<OrderRow, OrderRow>chunk(200, transactionManager)
            .reader(partitionReader)
            .writer(outputWriter)
            .build();
}
~~~

Các import còn lại: `org.springframework.batch.core.Step`, `org.springframework.batch.core.repository.JobRepository`, `org.springframework.batch.core.step.builder.StepBuilder`, `org.springframework.batch.item.ItemWriter` và `org.springframework.transaction.PlatformTransactionManager`. Bean method nằm trong configuration của worker.

Một writer đơn giản, **không giữ mutable state**, dùng PostgreSQL:

~~~java
@Bean
ItemWriter<OrderRow> outputWriter(JdbcTemplate jdbc) {
    return chunk -> {
        for (OrderRow row : chunk) {
            jdbc.update("""
                INSERT INTO imported_order(
                    snapshot_id, order_id, payload
                )
                VALUES (?, ?, ?)
                ON CONFLICT (snapshot_id, order_id)
                DO UPDATE SET payload = EXCLUDED.payload
                """,
                row.snapshotId(), row.orderId(), row.payload());
        }
    };
}
~~~

Ví dụ giả định bảng `imported_order` có primary key `(snapshot_id, order_id)` và snapshot không đổi. Với dữ liệu có version mới hoặc side effect từ trigger/audit/API, `UPSERT` đơn thuần không đủ; cần version condition, outbox hoặc idempotency key nghiệp vụ.

**Chú ý kiến trúc:** đoạn này minh họa **logic worker step**, chưa phải toàn bộ ứng dụng remote partitioning chạy được. Để thành hệ thống hoàn chỉnh còn cần:

- Manager `Partitioner`/`PartitionHandler` và endpoint gửi request.
- Worker message listener hoặc Spring Batch Integration adapter nhận thông điệp, tra `StepExecution` và thực thi đúng worker step.
- Request/reply channel, serializer, transport, correlation, retry, timeout, routing.
- Cấu hình `JobRepository`, worker step registration/locator và quyền truy cập metadata **tương thích cơ chế remote partitioning đã chọn**.
- Điều phối startup, security, metrics, graceful shutdown và quy trình restart.

Trong Spring Batch Integration, một cách triển khai có manager dùng handler dựa trên message channel và worker nhận `StepExecutionRequest` thông qua listener/adapters. Những thành phần cụ thể thay đổi theo phiên bản và transport, do đó **không nối nhầm class của remote partitioning vào pipeline remote chunking**.

### Có bắt buộc cùng JobRepository?

Cần trả lời theo **giao thức remote partitioning** cụ thể. Với cơ chế trong đó worker nhận định danh `StepExecution` rồi tra/update state qua `JobRepository`, manager và worker cần truy cập metadata repository phù hợp và thống nhất. Trong kiến trúc khác, giao thức có thể có cách quản lý metadata khác; không thể giả định mỗi worker dùng DB metadata riêng rồi tự khớp trạng thái.

Dù cơ chế nào, chỉ có **một nguồn trạng thái đáng tin cậy** cho vòng đời của một partition và cách đối soát khi manager/worker bất đồng về kết quả. Một message “đã nhận” chưa có nghĩa partition đã `COMPLETED`.

## 6. Remote chunking: payload và backlog nằm trên mạng

Remote chunking giữ reader ở manager. Manager tổ chức chunk rồi gửi item qua middleware cho worker xử lý/ghi và nhận reply. Nó có thể phù hợp khi **reader tập trung đủ nhanh** nhưng processor/writer tốn CPU hoặc cần tài nguyên ở nhiều máy.

~~~mermaid
sequenceDiagram
    participant M as Manager JVM
    participant Q as Request Broker
    participant W as Worker JVM
    participant D as Business DB
    participant R as Reply Channel
    M->>M: Reader đọc 200 item
    M->>Q: Publish chunk K (payload + correlation)
    Q->>W: Deliver K
    W->>D: Process/write chunk, commit theo cấu hình
    W->>R: Reply chunk K
    R-->>M: Kết quả/ack logic
    M->>M: Xác nhận tiến độ chunk
~~~

**Một số giới hạn đặc trưng:**

- Manager reader có thể trở thành **single bottleneck** dù thêm rất nhiều worker.
- Broker phải chịu serialize item, payload size, throughput request và reply, storage, retention, retry, DLQ.
- Manager cần theo dõi chunk đang outstanding và **không coi publish thành công là worker đã commit**.
- Khi worker đã commit nhưng reply thất lạc, có thể cần xử lý message/reply lặp, reconciliation và idempotent writer.
- Tăng `chunkSize` giảm số message nhưng tăng kích thước payload, memory, transaction duration và lượng công việc phải làm lại khi lỗi.

Ngược lại, remote partitioning thường chỉ gửi thông tin miền/range và để worker tự đọc, nên ít payload trên mạng **giữa manager và worker**, nhưng tăng số reader trực tiếp truy cập nguồn.

Không thể kết luận remote partitioning luôn tốt hơn remote chunking: nếu nguồn dữ liệu chỉ hỗ trợ một cursor tuần tự và không thể phân chia an toàn, remote chunking có thể là kiến trúc thực tế hơn.

## 7. Failure model: mạng không cho biết chính xác worker đã làm gì

Trong một JVM, lỗi đồng bộ thường lan qua call stack. Trên nhiều máy, một lời gọi có thể timeout dù phía nhận đã xử lý xong. Hãy xét hai kịch bản.

### Trường hợp A: worker chết trước commit

~~~text
Manager gửi partition/chunk K
      ↓
Worker bắt đầu transaction
      ↓
Worker JVM chết trước commit
      ↓
DB rollback transaction chưa commit (nếu DB hoạt động đúng)
      ↓
Coordinator phát hiện lỗi và phục hồi K theo cơ chế hỗ trợ
~~~

Cần lưu ý worker có thể đã thực hiện HTTP call bên ngoài DB transaction. Những call đó **không tự rollback**, nên kết quả nghiệp vụ vẫn có thể đã xảy ra.

### Trường hợp B: worker commit, phản hồi bị mất

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Broker
    participant W as Worker A
    participant W2 as Worker B
    participant D as DB
    M->>Q: Work K
    Q->>W: Deliver K
    W->>D: COMMIT business effect K
    Note over W,M: Worker/network hỏng trước ACK/reply
    M->>Q: Retry/dispatch lại K (nếu giao thức cho phép)
    Q->>W2: Deliver K
    W2->>D: Replay K
    D-->>W2: Dedup/UPSERT, không tạo hiệu ứng trùng
    W2-->>M: K đã hoàn tất
~~~

Khi timeout, manager chỉ biết **chưa có phản hồi đáng tin cậy**, không biết chắc worker chưa ghi. Nếu hệ thống retry quá sớm khi worker cũ vẫn còn chạy, có thể có **hai worker đang làm cùng K**. Cần quyền sở hữu/lease, timeout hợp lý và nếu yêu cầu độc quyền nghiêm ngặt thì **fencing** tại nơi ghi.

Mức bảo đảm thực tế thường là **at-least-once processing/delivery + idempotent business effect**, không phải mọi dòng code chỉ được chạy một lần.

### Ma trận lỗi nên xét ngay từ thiết kế

| Vị trí lỗi | Dấu hiệu | Điều phải kiểm chứng |
| --- | --- | --- |
| Manager trước khi dispatch | Chưa tạo request | Metadata còn chỉ đúng phần công việc cần chạy |
| Message publish thành công nhưng manager crash | Có thể có request tồn tại trong broker | Request/reply correlation và recovery khi manager quay lại |
| Worker đã nhận nhưng chưa commit | Task đang in-flight; worker chết | Rollback, timeout/requeue và checkpoint thích hợp |
| Worker commit rồi ACK/reply mất | Manager nghĩ chưa xong, output đã có | Writer idempotent, dedup, reconciliation |
| Worker sống nhưng lease hết | Hai worker có thể cùng xử lý K | Fencing/claim, tránh concurrent side effect |
| Broker lỗi hoặc DLQ tăng | Không phát được hoặc không xử lý được message | Backpressure, retry hữu hạn, không làm mất work |
| Worker mới khác schema | Deserialize lỗi, poison message | Versioned contract, rolling upgrade tương thích |
| JobRepository tạm mất kết nối | Không cập nhật được trạng thái | Không tự đánh dấu COMPLETED; phục hồi metadata trước retry |

## 8. Restart, checkpoint và ranh giới một JobInstance

Spring Batch phân biệt `Job`, `JobInstance` (tên job + identifying `JobParameters`), `JobExecution` (một lần attempt) và `StepExecution` (một lần thực thi step). Với remote partitioning, các partition có metadata thực thi riêng; restart cùng `JobInstance` có thể bỏ qua step/partition đã hoàn tất và xử lý lại phần lỗi theo contract.

Điều kiện để restart có ý nghĩa:

1. **Tập đầu vào bất biến:** dùng snapshot ID, manifest file hoặc watermark đã chốt.
2. **Partition name/boundary tái lập:** không tạo cùng tên partition nhưng range khác khi retry.
3. **Reader checkpoint xác định:** ví dụ `ORDER BY order_id` trên khóa duy nhất, `ItemStream` được quản lý đúng.
4. **Writer idempotent:** cùng business key có hiệu ứng cuối đúng khi chạy lặp.
5. **Side effect được đối soát:** HTTP, message, file hoặc aggregate không thể được bảo vệ chỉ bằng transaction JDBC.
6. **Metadata bền vững:** không để trạng thái duy nhất trong RAM của một worker hoặc local disk không chia sẻ.
7. **Worker ownership rõ ràng:** worker cũ phải dừng/không còn quyền ghi trước khi nhận lại phần việc có rủi ro xung đột.

Khi manager hoặc worker JVM chết đột ngột, metadata có thể vẫn ở `STARTED`. **Không sửa thủ công trạng thái hoặc xóa `BATCH_*` để “mở khóa” khi chưa xác minh worker cũ đã dừng**. Cần runbook tương thích phiên bản Spring Batch, khả năng stop/restart và hạ tầng messaging.

### Restart khác chạy instance mới

Nếu job nhập ngày `2026-11-25` bị lỗi, hãy giữ identifying `businessDate`/`snapshotId` nếu mục đích là **restart cùng công việc logic**. Thêm một `run.id` hoặc timestamp identifying mới có thể tạo `JobInstance` mới và bỏ qua checkpoint cũ. Đó là một **reprocess** mới cần chính sách riêng, không nên đánh tráo với restart.

## 9. Idempotency xuyên JVM và các hệ thống bên ngoài

Một `synchronized` block hoặc `AtomicLong` chỉ bảo vệ trạng thái **trong một JVM**, không đồng bộ hai pod. Khóa chống ghi trùng phải được thi hành tại nguồn trạng thái **chia sẻ và bền vững**: unique constraint ở DB, ledger, idempotency key của API hoặc inbox/outbox.

### 9.1. Ghi bảng theo business key

~~~sql
CREATE TABLE imported_order (
    snapshot_id VARCHAR(100) NOT NULL,
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);
~~~

~~~sql
-- PostgreSQL: ghi version mới hơn, không để replay cũ ghi đè.
INSERT INTO imported_order(snapshot_id, order_id, source_version, payload)
VALUES (:snapshotId, :orderId, :version, :payload)
ON CONFLICT (snapshot_id, order_id) DO UPDATE
SET source_version = EXCLUDED.source_version,
    payload = EXCLUDED.payload
WHERE imported_order.source_version < EXCLUDED.source_version;
~~~

Với cùng key và cùng version, phép ghi không làm thay đổi dòng đã lưu. Tuy nhiên, nếu trigger DB tạo audit bất chấp nội dung hoặc có tác dụng ngoài DB, cần xem xét liệu **toàn bộ hiệu ứng** có idempotent hay không. Khi source snapshot không thay đổi, có thể dùng `DO NOTHING` với ràng buộc kiểm tra payload; khi source có version, áp dụng quy tắc ordering/version phù hợp.

### 9.2. Transactional outbox

Nếu worker vừa ghi đơn hàng vừa gửi sự kiện qua broker, lỗi giữa **DB commit** và **message publish** có thể làm mất thông điệp; gửi trước commit có thể tạo message cho dữ liệu bị rollback. Transactional outbox lưu nghiệp vụ và bản ghi outbox **trong cùng transaction DB**. Publisher riêng gửi event có `event_key` ổn định; consumer dùng inbox/dedup khi event bị giao lại.

~~~text
Worker chunk TX:
    INSERT/UPSERT imported_order
    INSERT outbox(event_key, payload) ON CONFLICT DO NOTHING
COMMIT
    ↓
Publisher đọc outbox và publish
    ↓
Consumer nhận event (có thể nhận lặp) → dedup theo event_key
~~~

Outbox giảm khoảng trống bất nhất DB–publish, nhưng **không tự bảo đảm broker chỉ giao một lần**. Chỉ dùng một `event_key` deterministic cho cùng hiệu ứng; UUID ngẫu nhiên mới ở mỗi retry đánh mất khả năng dedup.

### 9.3. API bên ngoài

Nếu worker gọi API thanh toán/fulfillment, phải dùng idempotency key ổn định được API đích thực sự hỗ trợ. Khi timeout, cần query trạng thái hoặc replay **cùng key** theo contract. DB unique key ở hệ nội bộ **không** tự bảo vệ API bên ngoài.

## 10. Scale-out và giới hạn năng lực thực tế

Giả sử job phải xử lý **8 triệu đơn hàng trong một giờ xử lý hữu ích**:

~~~text
R_target = 8.000.000 / 3.600 ≈ 2.222 business items/s
~~~

Một worker slot xử lý được **320 lượt công việc thô/giây** khi benchmark riêng. Trung bình một item hữu ích cần `1,10` lượt thô do retry/rework:

~~~text
R_raw_required ≈ 2.222 × 1,10 = 2.444 lượt/s

Số worker lý tưởng (không contention):
ceil(2.444 / 320) = 8 worker slots
~~~

Nhưng giả sử business DB chỉ ghi bền vững **1.600 lượt tương đương/s** dưới tải chung:

~~~text
R_raw_cap = min(8 × 320, 1600) = 1600/s
R_effective_cap ≈ 1600 / 1,10 ≈ 1455 items/s

T_estimate ≈ 8.000.000 / 1455 ≈ 5.498 giây ≈ 92 phút
~~~

**Không đạt SLA một giờ** dù có thêm node. Cần giảm thao tác ghi mỗi item, tối ưu SQL/batch writer/index, tăng năng lực DB, đổi tổ chức dữ liệu hoặc điều chỉnh cửa sổ. Tạo 16 worker chỉ đẩy thêm request/connection đến DB đã bão hòa.

### Cấu hình `gridSize` và số worker khác nhau

Giả sử manager tạo 12 partition, mỗi worker pod xử lý tối đa 2 partition đồng thời, có 3 pod:

~~~text
Number of partitions = 12
Worker slots          = 3 pods × 2 = 6
Concurrency           ≤ 6 partitions đồng thời
Mỗi đợt xử lý          ≈ 6 partitions nếu phân bố đều
~~~

Trong thực tế duration từng partition có thể lệch do ID thưa, tenant lớn hoặc payload nặng. Thời gian toàn job chịu ảnh hưởng partition chậm nhất (**straggler**). Tạo nhiều partition nhỏ có thể giúp chia tải linh hoạt nhưng tăng metadata, dispatch, connection churn và chi phí restart. Phải đo điểm cân bằng.

### Các trần cần đo

| Nút thắt | Dấu hiệu | Cách tiếp cận |
| --- | --- | --- |
| CPU worker | CPU quota sát trần, processor chậm | Thêm host/pod nếu DB/API còn dư; tối ưu CPU/item |
| Memory/GC worker | Heap cao, GC pause/OOM | Giảm buffer/chunk, giới hạn in-flight, scale memory |
| Business DB writer | Lock wait, WAL/IO, commit chậm | Batch writes, giảm contention, thay thuật toán ghi |
| Source DB reader | Full scan, connection pool pending | Chia range theo index, snapshot, tối ưu query |
| Broker/network | Publish/consume lag, request/reply lớn, DLQ | Backpressure, giảm payload, thêm broker capacity phù hợp |
| JobRepository | Metadata lock, update step chậm | Cân bằng số partition/chunk, tune metadata DB |
| API rate limit | HTTP 429/timeout, retry tăng | Global limiter, backoff, cache/batch API |
| Skew partition | Một vài worker chạy lâu, worker khác rảnh | Chia theo chi phí/quantile và bảo vệ business ordering |

## 11. Vấn đề network: serialization, latency và schema

So với nhiều thread trong một JVM, nhiều process cần biến công việc thành message:

- **Serialization:** dữ liệu phải được mã hóa/giải mã; class/model không được giả định có cùng class loader.
- **Payload size:** chunk lớn tạo pressure cho network, heap, broker disk và timeout.
- **Schema evolution:** manager và worker có thể chạy **hai phiên bản ứng dụng khác nhau** trong rolling deployment; message phải có compatibility rule.
- **Correlation:** reply cần quay về đúng job/step/chunk; duplicate/lost reply phải được xử lý.
- **Security:** xác thực, phân quyền, mã hóa đường truyền, bảo vệ payload chứa dữ liệu nhạy cảm.
- **Retry/redelivery:** lỗi mạng không cung cấp chắc chắn trạng thái commit; phải có idempotency và reconciliation.
- **Ordering:** broker có thể giữ thứ tự **trong một partition/queue theo điều kiện riêng**, nhưng không mặc nhiên giữ thứ tự toàn hệ thống giữa nhiều worker.

Với remote partitioning, message thường là ID/range/file key nên nhẹ; worker đọc trực tiếp từ nguồn. Với remote chunking, manager gửi cả item nên chi phí serialization/network có thể đáng kể.

### Chọn kiểu message phù hợp

Một payload giao partition có thể mang các trường logic:

~~~json
{
  "jobExecutionId": 1234,
  "stepExecutionId": 5678,
  "partitionName": "partition003",
  "snapshotId": "orders-2026-11-25",
  "schemaVersion": 1
}
~~~

**Đây là biểu diễn khái niệm**, không phải JSON wire format mặc định của `StepExecutionRequest` trong Spring Batch Integration. Trường range và metadata có thể được tra qua `JobRepository` hoặc kèm message theo protocol. Không tự thay đổi protocol framework nếu chưa xác minh yêu cầu của adapter và tương thích manager–worker.

Khi worker không thể deserialize dữ liệu, cần phân loại lỗi/schema mismatch, retry có giới hạn và DLQ; đừng lặp vô hạn một poison message rồi làm backlog không bao giờ xả.

## 12. Backpressure và quota chung cho nhiều JVM

Một coordinator chạy trên nhiều máy phải quản lý tổng **in-flight work**, không chỉ queue trong từng worker. Nếu mỗi worker có 100 outstanding request và có 20 replica, số lượng request đang xử lý/chờ có thể lên tới 2.000, vượt hạn mức DB/broker.

~~~text
Effective in-flight ≈ Σ(worker replica active tasks + prefetched pending tasks)

R_end_to_end ≤ min(
    R_manager,
    R_broker,
    R_worker_total,
    R_business_DB,
    R_external_API
)
~~~

Cần phân biệt số message **ready**, **unacked/in-flight**, retry/DLQ và backlog reply. RabbitMQ `messages_ready` không tính message đã giao nhưng chưa ack; Kafka consumer lag không đồng nghĩa số item nghiệp vụ chưa commit. Dashboard nên đo **tuổi của phần việc chờ lâu nhất** và **thông lượng item hữu ích**, không chỉ depth.

### Cơ chế điều tiết thường dùng

| Cơ chế | Chặn được gì? | Giới hạn |
| --- | --- | --- |
| Bounded worker thread pool | Số tác vụ thực thi đồng thời trong một JVM | Không giới hạn toàn cluster khi thêm pod |
| Broker prefetch/in-flight control | Message đưa tới consumer nhưng chưa ack | Không tự tăng DB capacity |
| Coordinator admission control | Số partition/chunk được cấp quyền chạy | Cần recover permit khi crash và quản lý owner |
| Global API rate limiter | Tổng request sử dụng cùng API key/tenant | Cần trạng thái chia sẻ giữa replica |
| DB pool max per pod + tổng connection budget | Tránh mở quá nhiều session DB | Session limit không thay thế lock/IO throughput |
| Retry exponential backoff + jitter | Retry storm sau lỗi tạm thời | Không xử lý được lỗi schema/poison message |
| Bounded queue / workload scheduling | Hạn chế backlog tăng vô hạn | Phải bảo đảm không đánh rơi công việc chưa commit |

Một distributed lock có lease mà hết hạn **không đồng nghĩa worker cũ đã ngừng ghi**. Khi cần độc quyền, triển khai owner token/fencing hoặc cơ chế kiểm tra phiên bản tại DB/API. Đặt concurrency quota cho job/tenant/resource xuyên suốt mọi đường khởi chạy: scheduler, API, chạy tay, backfill và restart.

## 13. Triển khai trên nhiều máy: ưu tiên tính nhất quán cấu hình

Để manager và worker hoạt động đúng, cần kiểm soát ít nhất:

1. **Phiên bản ứng dụng và message schema**: rollout có compatibility giữa phiên bản trước/sau.
2. **Job/step names**: manager và worker thống nhất tên step theo giao thức; không đổi tên tùy ý nếu cần restart metadata cũ.
3. **JobParameters, snapshot và partitions**: identifying parameters và boundary phải cố định cho một `JobInstance`.
4. **JobRepository/metadata**: cấu hình persistence và quyền truy cập đúng cho kiến trúc remote partitioning đã chọn.
5. **Transaction manager ở worker**: writer dùng datasource tham gia transaction như mong muốn.
6. **Message routing**: request/reply destination, correlation, serializer, authentication và retry/DLQ.
7. **Resource limits**: CPU/memory request/limit, worker slots, pool DB, API quota và broker capacity.
8. **Graceful stop**: cho worker hoàn tất/rollback tác vụ đang chạy theo semantics hỗ trợ, cập nhật metadata và ngăn owner cũ ghi tiếp.
9. **Security**: worker chỉ có quyền DB/topic/bucket cần thiết, secrets không hardcode, truyền qua kênh được bảo vệ.
10. **Observability**: logs/traces có `jobExecutionId`, `stepExecutionId`, partition/business key và host/pod để truy vết.

Kubernetes `replicas: 5` chỉ bảo đảm triển khai số pod theo controller, **không** bảo đảm có năm pod nhận được công việc hay mỗi pod có dữ liệu đúng. Cần health/readiness, consumer subscription/step registration và load test sau scale.

### Metadata và dữ liệu nghiệp vụ phải bền vững

Không lưu checkpoint duy nhất bằng file local của một worker pod nếu pod đó có thể bị thay. Dùng `JobRepository` bền vững, snapshot/manifest lâu đủ cho restart và output được khóa theo business key.

Không chạy quá nhiều worker khiến repository update metadata hoặc DB business sụp đổ; một shared persistent repository là điểm phục vụ dùng chung, cần tính năng lực và backup phù hợp.

## 14. Quan trắc một job phân tán

Bảng metric dưới dùng **tên logic minh họa**, không có nghĩa Spring Batch hoặc broker tự xuất mọi metric với đúng nhãn đó.

| Lớp | Metric cần theo dõi | Câu hỏi |
| --- | --- | --- |
| Job | Start/end, elapsed, status, business window, SLA | Toàn job có hoàn thành đúng hạn? |
| Step/partition | `StepExecution` status, duration, read/write/commit/rollback | Partition nào là straggler hoặc failed? |
| Worker process | CPU, heap, GC, active threads, queue, restarts | Còn năng lực CPU/RAM và có crash loop? |
| Database | Connection active/pending, lock wait, deadlock, commit latency | DB có phải bottleneck toàn cluster? |
| Middleware | Request ready/unacked, reply lag, retry/DLQ, oldest message age | Công việc đang kẹt ở giai đoạn nào? |
| Network | Bytes/s, p95 latency, timeout, serialization errors | Chi phí phân tán có áp đảo xử lý? |
| Nghiệp vụ | Số khóa hợp lệ, missing/duplicate count, source version | Kết quả cuối có đúng sau retry? |
| Recovery | Thời gian phát hiện lỗi, retry count, restart duration | RTO có đạt yêu cầu? |

**Tách throughput thô và hữu ích.** Một worker có thể xử lý 100 request/s nhưng 20% là redelivery; nếu đếm mỗi attempt như công việc mới, dashboard sẽ báo thông lượng cao dù backlog nghiệp vụ không giảm.

### Một log truy vết tối thiểu

~~~java
System.out.printf(
    "jobExecutionId=%d stepExecutionId=%d partition=%s worker=%s thread=%s%n",
    jobExecutionId,
    stepExecutionId,
    partitionName,
    System.getenv().getOrDefault("HOSTNAME", "unknown"),
    Thread.currentThread().getName());
~~~

Các biến ở đoạn mã là thông tin ứng dụng lấy từ ngữ cảnh xử lý. Đừng gắn business key có cardinality cực cao vào metric time-series; dùng logs/traces để điều tra chi tiết và kiểm soát dữ liệu nhạy cảm.

Với distributed tracing, mỗi message cần truyền correlation/trace context theo transport được hỗ trợ. `ThreadLocal` ở manager không tự xuất hiện trong worker process; chỉ các metadata được truyền rõ ràng mới đi qua ranh giới JVM.

## 15. Kiểm thử lỗi và restart trước khi chạy production

Một bộ kiểm thử đáng tin cậy nên bao gồm:

1. **Chạy một worker slot** trên snapshot cố định: xác nhận đầu ra, thời gian và số chunk/partition.
2. **Tăng 2 → 4 → 8 worker slots**: đo tốc độ toàn job, CPU/DB/middleware; không mặc định tuyến tính.
3. **Partition boundary**: record tại biên, ID thưa, partition rỗng, khóa trùng, tenant lớn; kiểm chứng không thiếu/trùng.
4. **Worker crash trước commit**: kill một worker trong staging, xác nhận rollback và xử lý lại phần chưa hoàn tất.
5. **Worker commit nhưng reply/ack mất**: mô phỏng mất phản hồi và giao lại K; kiểm tra không có hiệu ứng nghiệp vụ trùng.
6. **Manager crash**: để có work in-flight rồi restart manager theo quy trình hỗ trợ; xác nhận metadata và broker không mất việc.
7. **Worker cũ vẫn sống khi lease hết**: kiểm chứng cơ chế chống hai owner cùng ghi, hoặc thực hiện takeover an toàn.
8. **JobRepository tạm không truy cập được**: lỗi được báo/giữ trạng thái hợp lệ; không tự ghi `COMPLETED`.
9. **Broker backlog/DLQ**: worker chậm, payload lớn, schema mismatch, retry storm; đo oldest age và drain time.
10. **Data source drift**: sửa snapshot giữa các attempt để xác nhận giải pháp phát hiện/không cho restart sai.
11. **Rolling deployment**: manager phiên bản cũ, worker phiên bản mới và ngược lại trong giai đoạn chuyển đổi; kiểm tra schema compatibility.
12. **Tải chung DB/API**: chạy song song với dịch vụ realtime, đo connection wait, 429, deadlock và throughput hữu ích.
13. **Graceful shutdown**: dừng một pod, xác định worker đã hoàn tất/rollback và metadata được cập nhật đúng.
14. **Reconciliation cuối job**: so sánh source/target theo business key/version, kiểm tra outbox/HTTP side effect đã được xử lý.

Chỉ nhìn thấy tất cả worker “alive” hoặc hàng đợi về 0 **không** chứng minh dữ liệu đã hoàn chỉnh. Cần trạng thái Spring Batch **và phép kiểm tra nghiệp vụ**.

## 16. Khi nào chọn mô hình multi-process nhiều máy?

| Bằng chứng từ workload | Giữ một JVM / local concurrency | Nên cân nhắc multi-process / multi-machine |
| --- | --- | --- |
| CPU/RAM của một node còn dư | Đơn giản hơn, ít broker và vận hành | Chưa cần scale-out |
| Processor CPU-bound và host đã hết core | Thêm thread không tăng CPU | Phân tán compute lên nhiều worker nodes |
| Input chia theo range/file/tenant rõ ràng | Local partitioning có thể đủ | Remote partitioning nếu vượt một node |
| Reader tập trung nhanh nhưng writer/processor chậm | Local xử lý có thể đủ ở quy mô nhỏ | Remote chunking nếu message overhead chịu được |
| DB writer hoặc API đã bão hòa | Tối ưu SQL/batch write/rate limit trước | Thêm node không tự sửa bottleneck |
| JVM crash làm mọi worker dừng, RTO nghiêm ngặt | Cần checkpoint và vận hành phục hồi tốt | Nhiều JVM giảm blast radius; vẫn cần recovery protocol |
| Dữ liệu lưu trong nhiều khu vực mạng | Có thể phát sinh chuyển data lớn về một host | Đặt worker gần dữ liệu và cân nhắc network/consistency |
| Cần nâng/hạ worker đàn hồi | Tăng thread có giới hạn host | Scale pod/process kèm quota chung và backpressure |

Không có một lựa chọn đúng cho mọi job. **Remote partitioning** thường hấp dẫn khi công việc chia được thành miền ổn định; **remote chunking** phù hợp khi manager reader là trung tâm còn worker cần mở rộng phần processing/writing; **parallel steps** phù hợp khi có nhiều flow độc lập và bước join. Quyết định dựa trên đường găng, sự độc lập dữ liệu, metadata/restart và nút thắt thật.

## 17. Bài tập tình huống

Một job phải nhập **6 triệu đơn hàng trong 60 phút**. Nguồn lưu snapshot bất biến theo `snapshotId`. Có ba worker pod, mỗi pod có 2 worker slot; mỗi slot xử lý độc lập **350 lượt thô/s**, workload thực tế cần `1,10` lượt xử lý cho mỗi đơn hàng hữu ích. Writer DB chỉ chịu được tổng cộng **1.400 lượt thô/s** dưới tải chung.

**Câu hỏi:**

1. Thông lượng hữu ích cần thiết để hoàn thành trong 60 phút là bao nhiêu?
2. Sáu worker slot có công suất thô lý tưởng là bao nhiêu? DB có trở thành bottleneck không?
3. Thông lượng hữu ích cao nhất theo mô hình cận trên bằng bao nhiêu, và thời gian tối thiểu ước lượng để xử lý 6 triệu đơn hàng?
4. Nếu manager tạo 12 partition, `gridSize=12` có nghĩa 12 worker chạy cùng lúc không?
5. Nếu worker A commit một partition rồi mất reply, việc gửi lại partition có an toàn khi writer dùng `UPDATE total = total + amount` không?
6. Nếu một pod có pool JDBC tối đa 10 connection, các pod có chia sẻ một pool mười connection không?

**Gợi ý lời giải:**

~~~text
R_target = 6.000.000 / 3.600 ≈ 1.667 item/s

Worker raw capacity = 3 pods × 2 slots × 350 = 2.100 lượt/s
DB raw cap = 1.400 lượt/s → DB là bottleneck

R_effective ≤ 1.400 / 1,10 ≈ 1.273 item/s
T_process ≥ 6.000.000 / 1.273 ≈ 4.714 giây ≈ 78,6 phút
~~~

Vì vậy **không đạt mục tiêu 60 phút** theo giả định, dù tổng worker lý tưởng đủ mạnh. Mười hai partition có thể phải xếp hàng trên sáu slot. Phép cộng `total = total + amount` không idempotent khi replay nếu không có operation ledger/transaction bảo vệ. Ba pool JDBC độc lập có thể dùng tới **30 connection** đến DB, chưa tính manager và dịch vụ khác.

## Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): mô hình scaling, parallel steps, remote chunking và partitioning.
- [Spring Batch 5.2 – Scaling](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): tham khảo API/mô hình ở dòng Spring Batch 5.x.
- [Spring Batch Reference – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): ghép Spring Batch với messaging middleware.
- [Spring Batch Reference – Item Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/index.html): `ItemStream`, reader/writer và checkpoint.
- [Spring Batch Reference – JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): metadata, transaction và persistence.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): message channels, endpoints, request/reply.
- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): semantics ack và confirm.
- [Kubernetes Documentation – Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): replica, rollout và quản lý vòng đời pod.

## Ghi nhớ

**Multi-process nhiều máy là scale-out bằng các JVM độc lập, không phải một transaction chung trải qua nhiều máy.** Worker có heap, thread, pool và transaction riêng, nhưng DB, JobRepository, broker, network và API quota có thể vẫn là nút thắt dùng chung. Remote partitioning phân phối miền dữ liệu để worker tự đọc; remote chunking phân phối chunk đã đọc ở manager. Khi có mất mạng hoặc crash, một công việc có thể đã commit nhưng chưa được xác nhận, nên cần partition ổn định, metadata bền vững, idempotency, retry/backpressure và đối soát. Chỉ thêm máy sau khi đã đo điểm nghẽn, throughput hữu ích và khả năng restart.

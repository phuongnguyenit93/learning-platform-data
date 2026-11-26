# Benchmark gridSize

Trong Spring Batch partitioning, tăng `gridSize` từ 4 lên 16 nghe có vẻ sẽ làm job nhanh gấp bốn. Thực tế, **gridSize không đồng nghĩa với 16 worker threads, 16 JVM, 16 DB connections hoặc speedup 4×**. `Partitioner` có thể chỉ trả một số partition khác; `TaskExecutorPartitionHandler` có thể chỉ có bốn active threads; một phần công việc nằm trong queue; database có thể nghẽn ở cùng một index hoặc bảng tổng hợp; nhiều partitions quá nhỏ làm thời gian điều phối và cập nhật `JobRepository` vượt lợi ích song song.

**Benchmark gridSize** là một thí nghiệm đo có kiểm soát để xác định số lượng/phân bố partitions phù hợp với **dữ liệu, kiến trúc và tài nguyên thực**, đồng thời kiểm tra kết quả nghiệp vụ, restart và tail latency. Mục tiêu không phải chọn con số lớn nhất hay tìm một “công thức gridSize theo CPU” cố định, mà là xác định vùng cấu hình có **throughput hữu ích cao, makespan thấp, ít lãng phí tài nguyên, đủ headroom và khả năng phục hồi**.

Bài thuộc chương **Performance testing** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module hướng đến mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và những mô hình xử lý phân tán phù hợp; học cách đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và lựa chọn kiến trúc theo tài nguyên thực tế. Nội dung dùng ví dụ **Spring Batch 5.x/Java 17+** theo mô hình local partitioning rồi mở rộng sang remote partitioning; với các phiên bản khác, cần kiểm tra API/configuration và diễn giải metric theo stack đang chạy.

> **Nguyên tắc benchmark:** phải thay đổi `gridSize` trong một thiết kế thí nghiệm rõ ràng, nhưng **đo cả kết quả phân vùng, concurrency thực, business commits, latency, tài nguyên và data correctness**. Một JobExecution `COMPLETED` với thời gian ngắn hơn chưa đủ nếu record bị trùng, thiếu hoặc chỉ ghi output đã tồn tại từ lần benchmark trước.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của `gridSize` đối với `Partitioner`, `PartitionStep` và `PartitionHandler`; phân biệt nó với số partitions thực tế, thread pool size, worker nodes và DB connections.
2. Xác định biến độc lập/biến kiểm soát khi benchmark: grid, pool, chunk, dataset, snapshot, broker, datasource và JobRepository.
3. Thiết kế các partition ranges bất biến, nửa mở, không overlap và kiểm phân bố bản ghi, kích thước bytes, chi phí xử lý.
4. Lập baseline `gridSize=1` và sweep `1/2/4/8/16/32` theo một workload được định danh.
5. Đo **job makespan**, committed logical records/s, speedup, parallel efficiency, p95/p99 partition duration, skew và tail.
6. Thu `StepExecution` counters, metrics executor, Hikari pool, DB locks/CPU, JobRepository updates và broker backlog khi remote.
7. Nhận diện nút thắt CPU, I/O, SQL/index, connection pool, serialization và worker startup/metadata overhead.
8. Phân biệt **strong scaling** (cùng số bản ghi) với **weak scaling** (workload tăng cùng capacity).
9. Kiểm tra fault injection, retry/restart, nguồn dữ liệu bất biến, idempotency và correctness sau từng benchmark.
10. Đề xuất gridSize dựa trên **đường cong throughput–latency–chi phí** và SLO có headroom, không suy từ một lần chạy nhanh nhất.

**Bài toán xuyên suốt:** hệ thống nhập 8 triệu giao dịch từ bảng staging PostgreSQL trong một snapshot bất biến, xử lý mỗi record bằng một phép biến đổi thuần, rồi ghi kết quả với unique business key. Local manager dùng `TaskExecutorPartitionHandler`, pool ban đầu bốn threads và một database business chung. Ta sẽ so `gridSize=1,2,4,8,16,32`, giữ **tổng 8 triệu records**, chunk size và các resources ổn định trong pha đầu. Sau đó mới thay đổi thread budget/partition strategy để thấy mối quan hệ nhân quả.

## 2. gridSize thực chất điều khiển điều gì?

Trong Spring Batch partitioning, manager tạo worker `StepExecution` dựa trên các partitions được một `Partitioner` cung cấp. Tùy builder/handler topology, `gridSize` được truyền như một **gợi ý số partition** cho `partition(int gridSize)`. Một `Partitioner` có thể trả **ít hơn, bằng hoặc khác số này** theo hợp đồng triển khai.

~~~mermaid
flowchart TD
    M["Manager PartitionStep"] --> P["Partitioner.partition(gridSize)"]
    P --> X["Map: partitionName → ExecutionContext"]
    X --> H["PartitionHandler"]
    H --> E["TaskExecutor / remote dispatch"]
    E --> W1["workerStep:partition0"]
    E --> W2["workerStep:partition1"]
    E --> W3["workerStep:partitionN"]
    W1 --> DB[("Business DB")]
    W2 --> DB
    W3 --> DB
    M -. "manager + worker metadata" .-> J[("JobRepository")]
~~~

**Bốn số cần báo cáo riêng:**

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | ---: | --- |
| `requestedGridSize` | 16 | Gợi ý/chỉ tiêu chia công việc |
| `partitionsReturned` | 16 | Số `ExecutionContext`/partition thực sự được tạo |
| `maxConcurrentWorkerSteps` | 4 | Số worker StepExecutions hoạt động cùng lúc |
| `effectiveDBOperations` | Phụ thuộc | SQL/transactions thực chạy và commit đồng thời |

**Ví dụ:** `gridSize=16`, partitioner trả 16 ranges, executor `maxPoolSize=4` → nhiều nhất khoảng bốn worker tasks đang chạy tại một thời điểm; phần còn lại đợi trong queue hoặc chưa được dispatch. Với `JdbcCursorItemReader` giữ connection lâu, số SQL writers hoạt động còn có thể thấp hơn vì DB pool bị chờ.

### gridSize không phải “throttleLimit”

Trong các API/cách cấu hình Spring Batch khác nhau có những tham số giới hạn concurrency riêng. Khi benchmark partitioning, cần xác định **handler đang dùng** và nơi đặt `gridSize`, không lấy một tham số multi-threaded step làm tương đương. Đặc biệt, đừng kết luận thay `gridSize` sẽ thay `ThreadPoolTaskExecutor.corePoolSize`: chúng là **hai cấu hình khác nhau**.

## 3. Local và remote partitioning cần phép đo khác nhau

| Kiến trúc | Ý nghĩa gridSize thực tế | Capacity giới hạn | Overhead nổi bật |
| --- | --- | --- | --- |
| **Local partitioning** | Gợi ý số partition cho manager local | Thread pool, CPU/JVM, DB pool/locks | Scheduling, StepExecution/checkpoint metadata |
| **Remote partitioning** | Số logical partitions manager có thể dispatch | Worker JVMs/consumer concurrency, network, DB | Serialization, broker, worker scheduling và JobRepository |
| **Multi-threaded step** | Không dùng partition map theo cùng semantics | Chunk concurrency/shared reader | Thread safety/checkpoint |
| **Parallel flows** | Số branches theo job flow, không phải `Partitioner` ranges | Flow executor và dependencies | Join/barrier và shared resources |
| **Remote chunking** | Đơn vị song song là chunk requests, không dùng gridSize của partitioner | Manager reader, broker, worker processing | Payload size/in-flight/reply correlation |

**Không benchmark `gridSize` bằng cách thay đổi worker count của remote chunking rồi gọi hai biến này một thứ.** Có thể nghiên cứu chung về throughput, nhưng phải đặt đúng tên biến và state model.

## 4. Chọn mục tiêu benchmark trước khi chạy

Một benchmark tốt trả lời câu hỏi **có thể ra quyết định**:

- Job 8 triệu records có cần hoàn tất trong **20 phút**, bao gồm validation và publication?
- Database có giới hạn **12 active application connections** cho batch?
- Worker pod/JVM có CPU/memory budget nào và phải chia sẻ tài nguyên với dịch vụ khác?
- Sau crash một worker, job cần restart/hoàn tất trong tối đa bao lâu?
- Output độc lập theo record hay cập nhật một hot aggregate row cần serialization?
- Ưu tiên **giảm job makespan** hay **giảm p99 time-to-visible** cho những record đến cuối?

Ví dụ đặt các mục tiêu minh họa:

~~~text
Source input:      8,000,000 immutable logical records
Deadline:          <= 20 minutes wall clock
Throughput target: >= ~6,667 source records covered / second
DB application cap: 12 active connections (giả định)
Correctness:       no missing/extra/wrong business effects
Restart:           same snapshot, no duplicate effects
Resource headroom: no sustained pool starvation/queue explosion
~~~

`8.000.000 / 1.200 ≈ 6.667 records/s` chỉ là thông lượng trung bình để đủ 20 phút **nếu toàn bộ 20 phút dành cho xử lý records**. Nếu validation/publication mất 3 phút, import thực cần `8.000.000 / 1.020 ≈ 7.843 records/s`. Ghi rõ việc tính **input covered** hay **new business rows committed** khi có filter/skip/dedup.

## 5. Định nghĩa metric: throughput, makespan và tail

**Job makespan:** `JobExecution.endTime - startTime` theo timestamp hợp lệ, hoặc đo elapsed bằng monotonic timer tại benchmark runner cho một run; bao gồm startup, worker scheduling, chunks và các steps thật của flow.

**Committed logical throughput:**

\[
X_{\text{business}} =
\frac{\text{số logical outcomes mới/đúng đã commit}}
{\text{thời gian benchmark tính bằng giây}}
\]

Đừng gọi `readCount/s`, `ItemProcessor invocation/s` hay `broker ACK/s` là business throughput: retries, skips, filter và duplicate requests làm chúng khác nhau.

**Speedup** và **parallel efficiency** theo strong scaling:

\[
S(G)=\frac{T_{\text{baseline}}}{T_G},\qquad
E(G)=\frac{S(G)}{G}
\]

Với `T_G` là median makespan của cấu hình gridSize=G và baseline gridSize=1 **trên cùng workload**. `E(G)` chỉ có ý nghĩa như hiệu suất **theo số partition yêu cầu**, không phản ánh chính xác hiệu suất **theo số active workers** nếu thread pool/nodes giữ nguyên. Khi pool=4 còn G=16, nên báo thêm `S(G)/maxConcurrentWorkers` theo định nghĩa đo đạc, tránh giả định 16 CPU workers.

**Tail metrics:** p95/p99 worker/partition duration, oldest pending age, p99 chunk commit, job-to-publish latency; chúng mô tả phân phối **khác nhau**. Một job hoàn tất sau partition chậm nhất, không phải sau partition trung bình.

## 6. Vì sao baseline phải thật sự giống workload đang so?

Benchmark `gridSize=1` và `gridSize=8` phải dùng:

1. Cùng input snapshot/version, logical record count, size distribution và business rules.
2. Cùng schema/indexes, query plans phù hợp, transaction isolation và DB server capacity.
3. Cùng chunk size/skip/retry policy, writer, JobRepository và output correctness gate.
4. Cùng các worker JVM/resources nếu đang nghiên cứu **gridSize riêng biệt**.
5. Cùng warm-cache/initial data state policy và cách tính start/end timestamps.
6. Cùng mức load nền hoặc một môi trường tách biệt, hoặc ghi rõ phần nhiễu.

**Sai phổ biến:** run `gridSize=1` chèn vào bảng rỗng, run `gridSize=8` cùng `batchKey` nên writer chỉ làm `ON CONFLICT DO NOTHING`. Lần thứ hai có thể nhanh vượt trội nhưng **không thực hiện cùng business effects**. Dùng batchKey/target dataset riêng hoặc reset dữ liệu theo quy trình có kiểm soát, đồng thời duy trì statistics/index state công bằng.

### Đừng dùng lại JobInstance đã COMPLETED

Spring Batch không cho chạy lại một JobInstance đã hoàn tất một cách tùy tiện. Mỗi run benchmark độc lập nên có **identifying JobParameters khác**, chẳng hạn `benchmarkRunId`, nhưng cùng **business source snapshot và biến thể output dataset được isolate**. Ngược lại, **restart test** phải dùng lại identifying parameters của JobInstance còn có thể restart: hai loại test khác nhau.

## 7. Strong scaling và weak scaling

**Strong scaling**: giữ input cố định 8 triệu records, tăng parallelism; mục tiêu là giảm `T_job`.

**Weak scaling**: tăng cả năng lực và input theo tỷ lệ tương ứng, ví dụ 2 triệu records/2 workers, 4 triệu/4 workers, 8 triệu/8 workers; mục tiêu là thời gian hoàn tất gần như giữ nguyên hoặc throughput tăng theo capacity.

~~~text
Strong scaling:
G=1   → 8,000,000 records
G=2   → 8,000,000 records
G=4   → 8,000,000 records
G=8   → 8,000,000 records

Weak scaling:
G=1   → 1,000,000 records
G=2   → 2,000,000 records
G=4   → 4,000,000 records
G=8   → 8,000,000 records
~~~

**Không trộn hai hình thức** trong cùng đường cong speedup mà không chú thích. Benchmark **gridSize** đầu tiên nên dùng strong scaling; sau đó mở rộng weak scaling khi cần lập capacity plan cho tăng trưởng dữ liệu/nodes.

## 8. Amdahl's Law cho phần không thể song song

Giả sử 15% thời gian baseline nằm ở setup, manager coordination, validation hoặc publication không song song. Speedup lý tưởng:

\[
S(N) = \frac{1}{s + (1-s)/N}
\]

Với `s=0,15`:

| Active workers N | Speedup Amdahl lý tưởng | Nhận xét |
| ---: | ---: | --- |
| 1 | 1,00× | Baseline |
| 2 | ~1,74× | Tăng đáng kể |
| 4 | ~2,76× | Diminishing returns |
| 8 | ~3,90× | Dù có 8 workers |
| 16 | ~4,92× | Bắt đầu gần giới hạn |
| Vô hạn | ~6,67× | Trần do 15% serial work |

Đây là mô hình **lý tưởng**, giả định phần parallelizable chia đều và không có contention/metadata overhead; benchmark thật thường thấp hơn hoặc đôi khi có hiệu ứng cache khiến tốc độ khác. Không dùng Amdahl để suy định `gridSize` tối ưu nếu **gridSize không bằng worker count** hoặc dữ liệu bị skew.

## 9. Nhiều partitions không bảo đảm phân tải đều

Giả sử partitioner chia theo numerical ID width:

~~~text
P0: [0, 2M)      10,000 records
P1: [2M, 4M)     20,000 records
P2: [4M, 6M)  7,500,000 records
P3: [6M, 8M)    470,000 records
~~~

Mặc dù `gridSize=4`, phần lớn công việc nằm ở P2. Ba workers kết thúc sớm, CPU rảnh trong khi P2 quyết định **makespan**. Tăng gridSize thành 8 có thể **hoặc không** giúp nếu P2 vẫn chứa hầu hết items.

**Benchmark phải đo distribution per partition:** actual records, bytes, average processing cost, chunk commits, read/write counts, duration và errors. **Range width**, file count hoặc số items từ planner không nhất thiết tương đương execution cost.

## 10. Kiến trúc workload và measurement boundaries

~~~mermaid
flowchart LR
    S[("Immutable staging snapshot")] --> P["Partitioner/gridSize"]
    P --> H["TaskExecutorPartitionHandler"]
    H --> W["Worker StepExecutions"]
    W --> D[("Business DB")]
    W --> R[("JobRepository")]
    D --> V["Reconciliation + publication gate"]
    H -. "active/queued tasks" .-> M["Benchmark metrics"]
    W -. "per-step durations/counts" .-> M
    R -. "metadata latency" .-> M
    D -. "pool/locks/WAL" .-> M
    V -. "end-to-end makespan" .-> M
~~~

**Phân ranh ba phép đo:**

- `T_manager`: manager partition step start → manager step end (có bao gồm worker scheduling/aggregation theo implementation).
- `T_worker`: mỗi worker StepExecution start → end; dùng để phân tích skew/slowest partition, không cộng các durations để ra job elapsed.
- `T_job_e2e`: JobExecution start → hoàn tất validation/publication; tiêu chí quan trọng khi user chỉ đọc kết quả sau toàn batch.

**Tổng durations của 16 worker steps không bằng wall-clock** vì chúng chạy chồng nhau. Ngược lại, có một worker chậm 5 phút có thể kéo cả job, dù 15 worker khác mỗi worker chỉ mất 10 giây.

## 11. Fixture dữ liệu có thể tái hiện

Một schema PostgreSQL tối giản:

~~~sql
CREATE TABLE staged_payment (
    batch_key     VARCHAR(120) NOT NULL,
    record_id     BIGINT NOT NULL,
    tenant_id     VARCHAR(80) NOT NULL,
    amount        NUMERIC(18,2) NOT NULL,
    input_version VARCHAR(100) NOT NULL,
    PRIMARY KEY (batch_key, record_id)
);

CREATE TABLE normalized_payment (
    batch_key   VARCHAR(120) NOT NULL,
    record_id   BIGINT NOT NULL,
    tenant_id   VARCHAR(80) NOT NULL,
    net_amount  NUMERIC(18,2) NOT NULL,
    source_hash VARCHAR(128) NOT NULL,
    PRIMARY KEY (batch_key, record_id)
);

-- PRIMARY KEY (batch_key, record_id) đã tạo B-tree index
-- phục vụ predicate range này ở PostgreSQL;
-- không tạo thêm index trùng chỉ để làm benchmark.
~~~

**Chuẩn bị ít nhất ba fixture có cùng business rule nhưng phân bố khác:**

| Dataset | Phân bố | Mục đích |
| --- | --- | --- |
| **Uniform** | 8 triệu IDs/records liên tục hoặc tương đối đều | Đo scaling khi phân vùng cân bằng |
| **Sparse** | IDs có lỗ, phân bố tập trung ở vài ranges | Phát hiện gridSize lớn nhưng partitions rỗng |
| **Skewed cost** | Số rows tương tự nhưng 5% records tốn CPU/DB I/O gấp 20× | Phát hiện skew theo **chi phí**, không chỉ row count |

Thêm các trường hợp biên nhỏ (`0,1,3` records), cùng record IDs ở hai `batchKey`/tenants và source versions khác nhau. Với dữ liệu nhạy cảm, dùng **synthetic data**, không copy raw customer records vào test hoặc báo cáo benchmark.

### Snapshot phải bất biến trong cả một run và một restart

Không thêm records vào cùng `batchKey` khi job đang chạy. Nếu source có thể cập nhật, hãy snapshot sang một bảng/staging version hoặc manifest bất biến; persist `sourceVersion` trong JobParameters/ExecutionContext và xác minh trên reader. **Một bài benchmark “nhanh hơn” nhưng thiếu hàng vì source thay trong lúc split là không hợp lệ.**

## 12. Range Partitioner theo khoảng nửa mở

Với dữ liệu khóa số, khoảng `[startInclusive,endExclusive)` tránh overlap tại biên. Một partitioner minh họa:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

final class BenchmarkRangePartitioner implements Partitioner {
    private final long minInclusive;
    private final long maxExclusive;
    private final String batchKey;
    private final String inputVersion;

    BenchmarkRangePartitioner(long minInclusive, long maxExclusive,
                              String batchKey, String inputVersion) {
        if (minInclusive > maxExclusive) {
            throw new IllegalArgumentException("Invalid range");
        }
        this.minInclusive = minInclusive;
        this.maxExclusive = maxExclusive;
        this.batchKey = batchKey;
        this.inputVersion = inputVersion;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize < 1) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long domain = Math.subtractExact(maxExclusive, minInclusive);
        if (domain == 0) {
            // Empty-work policy phải có integration test riêng.
            return Map.of();
        }

        int partitions = (int) Math.min((long) gridSize, domain);
        long base = domain / partitions;
        long remainder = domain % partitions;
        long cursor = minInclusive;
        Map<String, ExecutionContext> results = new LinkedHashMap<>();

        for (int i = 0; i < partitions; i++) {
            long rangeSize = base + (i < remainder ? 1L : 0L);
            long end = Math.addExact(cursor, rangeSize);
            ExecutionContext ctx = new ExecutionContext();
            ctx.putString("batchKey", batchKey);
            ctx.putString("inputVersion", inputVersion);
            ctx.putLong("startInclusive", cursor);
            ctx.putLong("endExclusive", end);
            results.put("partition" + i, ctx);
            cursor = end;
        }
        if (cursor != maxExclusive) {
            throw new IllegalStateException("Coverage mismatch");
        }
        return results;
    }
}
~~~

**Điều kiện của ví dụ:** `min/max` được lấy từ immutable snapshot, không tính lại từ bảng mutable giữa restart. Với `Long.MAX_VALUE` là ID cao nhất, không được tính `maxExclusive=maxId+1` vì overflow; chọn một cách biểu diễn cận có kiểm soát hoặc partition theo key list. Dữ liệu sparse có thể khiến range không rỗng nhưng query **0 row**, nên `partitionsReturned=8` vẫn không bảo đảm tám workers có khối lượng tương tự.

**Stable naming:** `partition0`, `partition1`... có ý nghĩa trong một JobInstance/source mapping cố định. Nếu đổi `gridSize` khi **restart cùng JobInstance**, các ranges/partition identities có thể khác, làm checkpoint/replay không an toàn. **Benchmark grid khác nhau trên JobInstances độc lập**, không dùng restart làm cách đổi grid.

## 13. Unit test Partitioner trước khi đo performance

Nếu partitions overlap, benchmark có thể đếm work hai lần; nếu thiếu, job có thể nhanh giả. Kiểm các bất biến trước:

~~~java
@Test
void partitionsCoverDomainWithoutOverlap() {
    Map<String, ExecutionContext> result =
            new BenchmarkRangePartitioner(
                    0L, 101L, "bench-snapshot", "v1").partition(8);

    List<ExecutionContext> ranges = result.values().stream()
            .sorted(Comparator.comparingLong(
                    x -> x.getLong("startInclusive")))
            .toList();

    assertEquals(8, ranges.size());
    long cursor = 0L;
    long sum = 0L;
    for (ExecutionContext ctx : ranges) {
        long start = ctx.getLong("startInclusive");
        long end = ctx.getLong("endExclusive");
        assertEquals(cursor, start);
        assertTrue(end > start);
        sum += end - start;
        cursor = end;
        assertEquals("v1", ctx.getString("inputVersion"));
    }
    assertEquals(101L, cursor);
    assertEquals(101L, sum);
}
~~~

**Bổ sung test:** `gridSize=0` bị từ chối; domain rỗng; một record nhưng grid=8; ranges có số phần dư; negative IDs; `long` overflow; reader SQL dùng `>= start` và `< end` chứ không dùng `BETWEEN start AND endExclusive`. Với nguồn theo file, cần test mỗi immutable file nằm **đúng một partition**, không dùng numeric range invariants vô điều kiện.

## 14. Worker reader phải riêng per StepExecution

Trong partitioning, reader nên lấy range từ **worker `ExecutionContext`** và có state riêng:

~~~java
record PaymentInput(
        String batchKey, long recordId,
        String tenantId, BigDecimal amount) {}

@Bean
@StepScope
JdbcCursorItemReader<PaymentInput> partitionReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['batchKey']}") String batchKey,
        @Value("#{stepExecutionContext['inputVersion']}") String inputVersion,
        @Value("#{stepExecutionContext['startInclusive']}") Long start,
        @Value("#{stepExecutionContext['endExclusive']}") Long end) {

    return new JdbcCursorItemReaderBuilder<PaymentInput>()
            .name("paymentReader")
            .dataSource(dataSource)
            .sql("""
                SELECT batch_key, record_id, tenant_id, amount
                FROM staged_payment
                WHERE batch_key = ?
                  AND input_version = ?
                  AND record_id >= ?
                  AND record_id < ?
                ORDER BY record_id
                """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, batchKey);
                ps.setString(2, inputVersion);
                ps.setLong(3, start);
                ps.setLong(4, end);
            })
            .rowMapper((rs, index) -> new PaymentInput(
                    rs.getString("batch_key"),
                    rs.getLong("record_id"),
                    rs.getString("tenant_id"),
                    rs.getBigDecimal("amount")))
            .saveState(true)
            .build();
}
~~~

**Lưu ý:** `@StepScope` tạo reader phù hợp worker step lifecycle; `ItemReader/ItemStream` giữ cursor/state mutable không nên vô tình chia sẻ singleton giữa StepExecutions. `ORDER BY record_id` ổn định thứ tự **trong partition**, nhưng không cam kết thứ tự hoàn tất giữa partitions.

Benchmark reader hiệu năng còn cần xem cách `JdbcCursorItemReader` giữ JDBC connection/cursor lâu. Nếu thử `JdbcPagingItemReader`, cần unique sort key và **cùng stable snapshot**, không chuyển reader strategy giữa hai grid runs rồi quy toàn bộ khác biệt cho grid.

## 15. Worker step và transaction boundary

~~~java
@Bean
Step workerStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentInput> reader,
        ItemProcessor<PaymentInput, PaymentOutput> processor,
        ItemWriter<PaymentOutput> writer) {
    return new StepBuilder("workerStep", repository)
            .<PaymentInput, PaymentOutput>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

`PaymentOutput` và các bean khác do ứng dụng triển khai. Mỗi worker xử lý chunks trong **các transactions độc lập**; khi một partition fail, chunks đã commit ở partition khác không bị rollback toàn cục. **Benchmark không được xoá mất bằng chứng partial commits**, và writer phải replay-safe.

**Trong pha benchmark gridSize**, giữ `chunk(200)` cố định để đo tác động của phân vùng. Sau khi chọn grid range tốt mới sweep chunk size; nếu thay cả chunk lẫn grid cùng lúc, không biết đâu là nguyên nhân cải thiện throughput.

## 16. TaskExecutorPartitionHandler cho phép sweep gridSize

Ví dụ đọc biến cấu hình `bench.grid-size` cho từng run/container:

~~~java
@Bean
ThreadPoolTaskExecutor benchmarkExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(64);
    executor.setThreadNamePrefix("bench-partition-");
    executor.initialize();
    return executor;
}

@Bean
TaskExecutorPartitionHandler benchmarkPartitionHandler(
        @Qualifier("workerStep") Step workerStep,
        @Qualifier("benchmarkExecutor") TaskExecutor executor,
        @Value("${bench.grid-size:4}") int gridSize) {

    TaskExecutorPartitionHandler handler =
            new TaskExecutorPartitionHandler();
    handler.setStep(workerStep);
    handler.setTaskExecutor(executor);
    handler.setGridSize(gridSize);
    return handler;
}

@Bean
Step managerStep(
        JobRepository repository,
        Partitioner snapshotPartitioner,
        TaskExecutorPartitionHandler benchmarkPartitionHandler) {

    return new StepBuilder("managerStep", repository)
            .partitioner("workerStep", snapshotPartitioner)
            .partitionHandler(benchmarkPartitionHandler)
            .build();
}
~~~

Ở đây, `gridSize=8` và `maxPoolSize=4` là **thí nghiệm cố tình tách số partitions và số threads**. Đây là configuration skeleton, chưa phải một project chạy độc lập: application còn cần `Job`, source snapshot manifest, datasource, processors/writers, imports, metrics và test beans.

**Không thay `handler.setGridSize` trên một Job đang chạy hoặc cùng JobInstance đang restart.** Mỗi cấu hình grid trong benchmark cần được áp dụng trước khi launch một independent JobInstance/context. Với `gridSize=32`, queue 64 đủ giữ tasks trong thí nghiệm này nhưng không có nghĩa mỗi job thực sẽ được chấp nhận trong mọi workload; khi có nhiều jobs đồng thời, executor capacity và rejection vẫn phải được đo.

## 17. Pha 1: sweep grid khi executor cố định

**Giữ `poolSize=4`, DB/schema, chunk size=200, cùng input** và thử:

~~~text
G ∈ {1, 2, 4, 8, 16, 32}
Executor core=max=4
Max active worker steps <=4
Benchmark 8,000,000 logical input rows mỗi run
~~~

Ý nghĩa:

- G=1 → một partition, executor còn rảnh ba threads; là baseline.
- G=2 → tối đa hai partitions chạy cùng lúc.
- G=4 → có khả năng dùng hết bốn workers.
- G=8/16/32 → số partitions tăng nhưng **capacity active threads vẫn là bốn**; các partitions còn lại xếp hàng.
- Nếu G>4 cải thiện rõ, có thể do **giảm straggler/khắc phục partition skew**, tăng scheduling flexibility hoặc giảm overhead xử lý một partition lớn; không kết luận “có 16 threads”.
- Nếu G>4 chậm đi, có thể do StepExecution/reader startup, DB scans, JobRepository writes và queue/scheduling overhead.

**Phải báo cáo `partitionsReturned` thật**, không chỉ ghi G, vì partitioner có thể tạo ít partition hơn gợi ý, ví dụ input có ba immutable files thì G=32 vẫn chỉ có ba partitions.

## 18. Pha 2: tách gridSize khỏi worker capacity

Pha 1 chỉ trả lời “chia bao nhiêu partition khi pool=4?”. Pha 2 kiểm tác động **concurrency**:

| gridSize | Executor threads | Câu hỏi nghiên cứu |
| ---: | ---: | --- |
| 4 | 4 | Baseline matched |
| 8 | 4 | Over-partitioning có giúp cân bằng tải? |
| 8 | 8 | Tăng worker capacity có giúp throughput? |
| 16 | 8 | Nhiều tasks trong queue hơn có giảm tail? |
| 16 | 16 | DB có chịu nổi 16 active partitions? |
| 32 | 16 | Partition overhead vs scheduling flexibility |

**Giữ nguyên các yếu tố khác** và đo DB pool/CPU/GC/locks. Mỗi cấu hình nên ghi ít nhất `requestedGridSize`, `partitionsReturned`, `activeWorkersMax`, `executorQueuedMax` và `dbConnectionsPendingMax`.

**Không mặc định chia 8 partitions rồi chạy 8 remote worker pods tạo 8 DB connections.** Reader cursor, writer, JobRepository và business validation có nhu cầu connection khác nhau. Muốn biết thực tế phải đo lifecycle của từng resource.

## 19. Pha 3: so partition strategy, không chỉ con số

Khi gridSize thay đổi nhưng throughput bão hòa hoặc tail vẫn rất dài, phải thử **chiến lược phân vùng**:

| Chiến lược | Ưu thế | Rủi ro/benchmark cần kiểm |
| --- | --- | --- |
| Numeric ID ranges | Tạo nhanh, query theo indexed key | Sparse/skewed data |
| Equal-count key ranges | Số rows gần nhau | Chi phí lấy quantiles/bounds, row cost vẫn lệch |
| Hash/modulo | Chia keys gần đều theo hash | Có thể phá locality/index/ordering, DB scans |
| File/object ranges | Phù hợp immutable files | File size/rate khác nhau |
| Tenant/region partitions | Isolation hoặc locality | Một tenant có thể chiếm 90% work |
| Pre-sharded work manifests | Control workload size và restart | Manifest generation overhead, stable identities |

**Không đổi strategy trong restart cùng JobInstance** nếu `ExecutionContext`/checkpoint cũ còn được dùng. Benchmark mỗi chiến lược như **một biến thể độc lập** và kiểm coverage/source integrity trước khi so performance.

## 20. Tính chi phí partition metadata

Mỗi worker `StepExecution` cần metadata (status, counters, context, lifecycle) và manager cần điều phối/tổng hợp kết quả. Khi chia 8 triệu records thành 8 partitions, overhead có thể nhỏ; khi chia thành **80.000 partitions**, mỗi partition ~100 records, việc tạo/lưu StepExecutions và chạy reader lifecycle có thể thành bottleneck.

~~~text
Total items             = 8,000,000
gridSize 8              = ~1,000,000 items per partition
gridSize 80             = ~100,000 items per partition
gridSize 8,000          = ~1,000 items per partition
gridSize 80,000         = ~100 items per partition

Giả định chỉ minh họa partitioner chia đều theo record count.
~~~

**Đừng đo riêng thời gian `ItemProcessor` rồi bỏ manager overhead.** Một benchmark đầy đủ phải thấy thời gian tạo Map/ExecutionContext, lưu StepExecutions, executor queue, mở reader/writer, chunk commits và manager aggregation. Trong remote setup, thêm serialization, broker dispatch/reply, worker startup và shared JobRepository contention.

## 21. Cần thu những số liệu nào trong mỗi run?

Một bản ghi benchmark nên có:

| Nhóm | Metric | Câu hỏi trả lời |
| --- | --- | --- |
| **Input** | `snapshotId`, expected items, bytes, distribution | Hai run có cùng workload không? |
| **Partition** | Requested grid, actual count, non-empty count | Partitioner có làm đúng gợi ý? |
| **Concurrency** | Active workers max/mean, executor queue max | Có thật nhiều worker chạy? |
| **Job** | End-to-end wall time, manager duration, validation time | Deadline toàn batch có đạt? |
| **Worker** | Per-partition read/write/filter/skip, duration | Có skew hoặc bỏ sót? |
| **DB** | Active/pending connections, SQL latency, locks, WAL | Có bị DB giới hạn? |
| **CPU/JVM** | CPU core usage, heap, GC pauses, allocation | Có nghẽn CPU/memory? |
| **Metadata** | JobRepository update latency, failed/retried steps | Chia quá nhỏ có đắt? |
| **Remote** | Queue oldest age, unacked, dispatch/reply latency | Broker có backlog không? |
| **Correctness** | Missing/extra/value mismatch, idempotency conflicts | Throughput có hữu ích? |
| **Recovery** | Restart duration, work replay, unknown outcomes | Over-partitioning có làm restart đắt? |

**Không dùng `JobExecution.COMPLETED` làm metric duy nhất.** Một job có thể `COMPLETED` dù business rules cho phép skip quá nhiều records; một run với nhiều `ON CONFLICT DO NOTHING` có thể đạt tốc độ cao mà không tạo output mới. Dùng **business data reconciliation** để khóa điều kiện “kết quả đạt”.

## 22. Đọc StepExecution metadata đúng phạm vi

Sau khi job hoàn tất, lấy **worker StepExecutions** từ JobRepository/thông tin JobExecution theo phiên bản đang chạy. Ví dụ skeleton:

~~~java
Collection<StepExecution> executions =
        jobExecution.getStepExecutions();

List<StepExecution> workerSteps = executions.stream()
        .filter(step -> step.getStepName().startsWith("workerStep:"))
        .toList();

long totalRead = workerSteps.stream()
        .mapToLong(StepExecution::getReadCount).sum();
long totalWritten = workerSteps.stream()
        .mapToLong(StepExecution::getWriteCount).sum();
long totalSkipped = workerSteps.stream()
        .mapToLong(step -> step.getReadSkipCount()
                + step.getProcessSkipCount()
                + step.getWriteSkipCount())
        .sum();

System.out.printf(
        "workers=%d read=%d write=%d skip=%d%n",
        workerSteps.size(), totalRead, totalWritten, totalSkipped);
~~~

**Lưu ý:**

- Manager `StepExecution` có thể không đọc/ghi trực tiếp 8 triệu records; không lấy counts của manager làm toàn job work.
- `writeCount` là metadata theo semantics Spring Batch, **không tự tương đương số logical rows mới** trong business DB, nhất là khi writer dedup/UPSERT hoặc external side effects.
- Khi có retry/restart, counts phải gắn **một JobExecution cụ thể** và được giải thích theo attempt; không cộng mù StepExecution cũ/mới rồi gọi đó là unique input.
- `startTime/endTime` của StepExecution là mốc metadata lifecycle; khi so durations **giữa remote JVMs**, chú ý clock synchronization và khả năng metadata update bị chậm.

### Per-partition report hữu ích hơn tổng số worker

~~~text
partitionName  readCount  writeCount  skipCount  durationMs  status
partition0       900,000     900,000          0      34,100  COMPLETED
partition1     1,060,000   1,060,000          0      39,400  COMPLETED
partition2     3,900,000   3,900,000          0     142,200  COMPLETED
partition3     2,140,000   2,140,000          0      77,600  COMPLETED
~~~

Các số là **ví dụ**, tổng 8 triệu; partition2 là straggler. Đừng chỉ nhìn elapsed chung và tăng gridSize; trước hết xác định tại sao P2 tốn nhiều records/chi phí hơn.

## 23. Đo thời gian worker bằng clock phù hợp

Ở **cùng một JVM**, `System.nanoTime()` phù hợp đo elapsed interval. Nhưng timestamp monotonic **không được persist làm checkpoint qua JVM restart**. Một probe chỉ dùng trong test:

~~~java
final class WorkerDurationProbe implements StepExecutionListener {
    private final ConcurrentMap<Long, Long> starts =
            new ConcurrentHashMap<>();
    private final ConcurrentMap<Long, Long> durations =
            new ConcurrentHashMap<>();

    @Override
    public void beforeStep(StepExecution execution) {
        if (execution.getId() != null) {
            starts.put(execution.getId(), System.nanoTime());
        }
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        Long id = execution.getId();
        Long start = id == null ? null : starts.remove(id);
        if (start != null) {
            durations.put(id,
                    Math.max(0L, System.nanoTime() - start));
        }
        return execution.getExitStatus();
    }

    Map<Long, Long> nanosecondsByStepExecution() {
        return Map.copyOf(durations);
    }
}
~~~

**Giới hạn:**

1. Đây là probe đo đoạn `beforeStep → afterStep`, **không** bảo đảm JobRepository đã persist final status, business validation hay publication.
2. Nếu JVM bị kill trước `afterStep`, duration không được ghi; cần JobRepository/heartbeat/timeout để điều tra.
3. Probe là singleton test-only thread-safe và phải reset/thay instance giữa runs; production ưu tiên Micrometer Observation/Timer instrumentation hiện có thay vì tự tạo nhiều metric trùng nhau.
4. Với **remote partitioning**, đo từng worker bằng monotonic clock tại worker JVM, publish duration metric; **không lấy hiệu giữa nanoTime của hai máy**.
5. `execution.getId()` phải tồn tại và unique theo JobRepository namespace; nếu nhiều repositories, cần include namespace khi kết hợp data.

## 24. Các phép đo Spring Batch và Micrometer

Nếu project đang bật Micrometer/Observation cho Spring Batch, tận dụng những **timer/counter đã có theo version**. Tự viết probe khi cần mốc mà instrumentation mặc định không cung cấp:

~~~text
batch.job.wall_time
batch.manager.partition.plan_time
batch.manager.partition.dispatch_time
batch.worker.step.duration
batch.worker.chunk.process_time
batch.worker.chunk.commit_outcome
batch.worker.restart.replay_time
batch.reconciliation.duration
~~~

Đây là **tên metric ứng dụng gợi ý**, không phải tuyên bố tất cả có sẵn trong Spring Batch. Với mỗi timer cần định nghĩa **start/end**. Đặc biệt, `ItemWriteListener.afterWrite` có thể chạy **trước khi DB transaction commit**; không đặt tên timer ở callback ấy là `db.commit.duration`. Muốn biết commit outcome, đo ở transaction manager/`TransactionSynchronization.afterCommit` và resource metrics phù hợp.

**Không dùng mỗi partitionName, requestId hoặc StepExecution ID làm metric tags có cardinality cao** nếu hàng chục nghìn partitions; giữ chúng trong structured logs/traces/JobRepository, tổng hợp metric theo job, worker role, grid bucket, status/reason có tập giá trị kiểm soát.

## 25. Theo dõi executor thực thay vì suy từ grid

Với `ThreadPoolTaskExecutor`, có thể lấy:

~~~java
int active = executor.getActiveCount();
int poolSize = executor.getPoolSize();
int queued = executor.getThreadPoolExecutor()
        .getQueue().size();
~~~

Đây là **snapshot tức thời**; để biết `maxActive` hoặc queue p95 theo thời gian phải sampling/instrument ở những khoảng hợp lý, và chấp nhận sample có thể bỏ sót spikes ngắn. `getActiveCount` không chứng minh CPU đang bận: thread có thể blocked trên DB connection/lock.

### Chứng minh ít nhất hai workers chạy đồng thời

Trong correctness integration test, đặt `CountDownLatch(2)` ở một **worker StepExecution start hook** chắc chắn có hai participants, timeout hữu hạn. Worker thứ nhất chờ worker thứ hai tới hook; nếu executor thực chỉ có một thread, test sẽ fail thay vì ngộ nhận `gridSize=4` là 4 active workers.

**Không đặt barrier 16 participants** khi pool chỉ có 4 active threads hoặc partitions rỗng không tới processor; test sẽ tự deadlock. Benchmark đo throughput nên **không giữ barrier blocking trong đường xử lý chính**, vì nó làm méo timing; kiểm concurrent execution ở test riêng.

## 26. HikariCP và DB connections là một ngân sách chung

Ví dụ resource picture:

~~~text
gridSize requested          = 16
partitioner actual          = 16
executor active max         = 8
Hikari maximumPoolSize      = 6
JDBC cursor readers         = có thể giữ 1 connection/active worker
Business writers            = transaction connections theo datasource setup
JobRepository               = metadata connections / pool riêng hoặc chung

=> Có khả năng workers phải chờ connection dù CPU còn rảnh.
~~~

**Không áp dụng công thức máy móc `poolSize=gridSize`.** Cursor reader, JDBC writer, StepExecution metadata, manager và validation có thể cùng cần connections; một số transaction reuse connection hoặc dùng datasource khác. Cần đo **active, idle, pending, acquisition latency, timeouts** và giới hạn server-side connections. Tăng connection pool quá nhiều có thể đẩy bottleneck sang DB CPU/locks thay vì giải quyết.

### Test pool exhaustion

Cho G=16, executor 8, pool nhỏ có chủ đích, với timeout rõ:

- Job có thể chậm hoặc FAIL theo policy, nhưng **không được treo vô hạn**.
- Connection waiting/timeout tăng phải xuất hiện trong metric/log.
- Sau lỗi cần đối soát partial output, restart hợp lệ và không nhân đôi business effects.
- Khi tăng pool, đo **DB server** đồng thời: cải thiện thread waits không bảo đảm commits/s tăng nếu DB đã saturation.

## 27. Database bottleneck và lock contention

Giả sử tất cả worker steps ghi vào một dòng `daily_total`:

~~~sql
UPDATE daily_total
SET total_amount = total_amount + :delta
WHERE batch_key = :batchKey;
~~~

Nhiều partitions cùng update một key có thể khiến DB serialize transactions qua row lock. Với grid=16, workers chờ lock lâu hơn, p99 chunk duration tăng trong khi committed throughput **không đổi**.

**Cách phân tích:**

1. Query plan: reader SQL có dùng index theo `batch_key,record_id` hay full scans?
2. Lock wait/deadlock metrics: contention ở output row/index hay JobRepository tables?
3. Transaction duration: chunks quá lớn giữ lock lâu?
4. Unique constraints: writer dedup nhiều làm tốn index operations mà không tạo rows?
5. WAL/checkpoints/disk: commit latency spikes có đến từ I/O log?
6. Source read locality: nhiều parallel range scans có phá sequential I/O/OS cache?

**Phương án thiết kế:** workers ghi record-level output/partition totals idempotent, sau đó reducer tổng hợp khi tất cả partitions validated. Khi business yêu cầu update aggregate ngay, phải chọn concurrency/locking contract khác và test deadlock/retry.

## 28. JobRepository cũng có giới hạn

Một worker `StepExecution` cập nhật metadata trạng thái, counters và `ExecutionContext` theo commit/checkpoint policy. Khi G lớn, số rows/transactions update metadata và hoạt động manager aggregation tăng.

| Dấu hiệu | Khả năng | Cách kiểm |
| --- | --- | --- |
| Tăng G làm manager duration tăng | Tạo/lưu quá nhiều StepExecutions | Partition creation/metadata SQL time |
| Business SQL nhanh nhưng job vẫn chậm | Metadata/commit overhead | JobRepository DB pool/locks/timers |
| Restart càng lâu khi G lớn | Nhiều worker statuses/checkpoints cần đối soát | Restart run duration |
| DB pool pending tăng nhưng business CPU thấp | Metadata và reader tranh pool | Tách data source metrics |
| Batch metadata tables tăng mạnh theo runs | Benchmark tạo nhiều JobInstances | Cleanup/retention có kiểm soát theo policy |

**Không truncate JobRepository để “cho benchmark sạch” khi các jobs khác cùng dùng.** Dùng repository/schema test riêng; nếu cleanup job metadata thì theo API/chính sách đã xác định và chỉ trong môi trường thử nghiệm được phép.

## 29. Little's Law: nhiều work in-flight có thể chỉ làm tăng chờ

Trong trạng thái tương đối ổn định:

\[
L = \lambda W
\]

`L` là số requests/chunks trung bình trong hệ, `λ` là completion rate trung bình theo cùng đơn vị và `W` là thời gian từ vào hệ tới hoàn tất. Nếu một executor/broker có 160 chunks in-flight với throughput 80 chunks/s ổn định, thời gian trung bình ở trong ranh giới đó khoảng:

\[
W = 160/80 = 2\text{ giây/chunk}
\]

Khi tăng G từ 16 lên 64 nhưng pool và DB capacity không đổi, `L` có thể tăng trong khi `λ` gần như đứng yên, làm latency tăng. **Little's Law nói về trung bình và ranh giới đo nhất quán**; không trực tiếp suy ra p99, không phù hợp áp dụng máy móc khi backlog đang tăng không ổn định hoặc work đơn vị không đồng nhất.

**Với batch hữu hạn**, queueing và makespan khác hệ arrival liên tục: một số partitions có thể nằm queue rồi mới chạy, nhất là khi `partitionsReturned ≫ activeWorkers`. Báo cáo cả **queue wait per partition** nếu instrument được.

## 30. Thiết kế thí nghiệm chống nhiễu

Thực hiện từng cấu hình **nhiều lần** thay vì chỉ chạy một lần. Một kế hoạch đề xuất:

1. **Định nghĩa một snapshot test duy nhất** với source immutable, cardinality, checksum, rule version.
2. **Chuẩn bị output riêng mỗi run** hoặc cleanup có kiểm soát; thống kê unique logical effects sau run.
3. **Warm-up** JVM, connection pool, SQL plans nếu mục tiêu là steady-state; nhưng đo startup riêng nếu SLA tính cold starts.
4. **Đảo/randomize thứ tự các grid runs**, không luôn chạy 1→2→4→8→16 vì JVM/DB cache có thể nóng dần.
5. **Giữ fixed pool/config** trong pha 1; chạy pha 2 riêng khi muốn khảo sát concurrency.
6. **Lặp ít nhất vài run**, giữ raw samples; chọn số lần lặp theo độ nhiễu và confidence mong muốn.
7. **Ghi load nền**, DB disk/WAL checkpoint, GC, software versions, hardware allocations và broker state.
8. **Đối soát business data** sau mỗi lần chạy; nếu fail, **loại run khỏi tập cấu hình hợp lệ** và điều tra, không chỉ xoá outlier để tăng median.
9. **Dùng cùng measurement boundaries** và báo số liệu min/median/p95 hoặc variation/interval khi đủ mẫu.
10. **Lặp lại ứng viên** dưới skew, failures, short burst và degraded capacity trước production.

**Đừng tuyên bố sự khác biệt 2% là có ý nghĩa nếu run-to-run variability 10%**, cũng đừng tự dùng p99 của năm lần chạy job như một estimate ổn định. Với p99, cần đủ observations ở cấp worker/chunk, và xác định percentile đang tính trên **partition durations hay job executions**.

## 31. Bảng kết quả giả định: chọn knee point

Đây là **số liệu minh họa**, không phải kết quả thực nghiệm đã chạy hay khuyến nghị mặc định cho Spring Batch. Giả định strong scaling trên **8 triệu logical input records**, cùng executor=4 threads, chunk=200, database/fixture không đổi, mọi run đều vượt qua correctness gate:

| Requested grid G | Partitions thực | Active workers max | Median job elapsed | Logical throughput | Speedup vs G=1 | DB wait/tail |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | 1 | 1.900 s | ~4.211 records/s | 1,00× | Thấp |
| 2 | 2 | 2 | 1.020 s | ~7.843 records/s | 1,86× | Thấp |
| 4 | 4 | 4 | 570 s | ~14.035 records/s | 3,33× | Vừa |
| 8 | 8 | 4 | 540 s | ~14.815 records/s | 3,52× | Vừa |
| 16 | 16 | 4 | 550 s | ~14.545 records/s | 3,45× | Tăng |
| 32 | 32 | 4 | 620 s | ~12.903 records/s | 3,06× | Tăng mạnh |

**Diễn giải đúng:**

- `G=1→4`: nhiều worker thực cùng chạy, speedup tăng rõ rệt.
- `G=4→8`: active workers vẫn bốn; cải thiện nhỏ có thể đến từ **partition balancing/scheduling** tốt hơn, không phải thêm CPU threads.
- `G=8→16`: thông lượng gần như đứng yên nhưng overhead tăng; phải kiểm variation trước khi kết luận 8 thật sự nhanh hơn 16.
- `G=32`: nhiều worker lifecycle/metadata tasks và queue/DB contention có thể khiến job chậm đi.
- Không tự động chọn `G=8` nếu G=4 có variation thấp hơn, recovery nhanh hơn, ít overhead hoặc đáp ứng mọi SLA với headroom tốt hơn.

### Minh họa đường cong

~~~text
Committed throughput (k records/s)
16 |              * G8   * G16
14 |         * G4                  * G32
12 |
10 |
 8 |    * G2
 6 |
 4 | * G1
   +-----------------------------------
      1    2    4     8    16    32
                   requested gridSize

Đường minh họa, không phải plot từ kết quả đo thật.
~~~

**Knee point** là vùng tăng concurrency/partitions bắt đầu cho lợi ích throughput rất nhỏ so với chi phí latency, tài nguyên hoặc recovery. Trong bảng, G4/G8 là những ứng viên đáng thử thêm bằng run lặp lại và workload skewed; không thể quyết định chỉ bằng một dòng.

## 32. Vì sao tốc độ cao ở G lớn có thể là ảo?

Các tình huống khiến records/s **được báo cao nhưng work khác nhau**:

1. Lần chạy đầu tạo 8 triệu rows; lần sau writer conflict `DO NOTHING` nên gần như không thay đổi DB.
2. Reader đã filter/skip hàng trăm nghìn lỗi nhưng throughput tính trên input read.
3. Partition ranges overlap làm hai workers cùng đọc một số IDs, trong khi bỏ sót IDs khác.
4. Source snapshot khác nhau về size, network locality hoặc thời gian process.
5. `JobExecution` chưa kết thúc nhưng monitor dừng đồng hồ sau manager dispatch.
6. Remote manager báo publish 8 triệu items, broker còn queue backlog, worker chưa commit.
7. Benchmark không tính validation/archive/publication, trong khi production SLA có tính.
8. Output table có trigger/index/constraints khác giữa các runs.

**Cách chống:** cho mỗi run đi qua một **reconciliation gate** kiểm expected input keys/values, filtered/quarantined theo policy, không có extra/duplicate logical effects và những trạng thái unknown; chỉ run đạt mới được dùng để so performance.

## 33. SQL reconciliation sau mỗi benchmark

Với fixture **mỗi input hợp lệ tạo đúng một output**, PostgreSQL:

~~~sql
-- Input rows không có business output.
SELECT s.record_id
FROM staged_payment s
LEFT JOIN normalized_payment o
  ON o.batch_key = s.batch_key
 AND o.record_id = s.record_id
WHERE s.batch_key = :batchKey
  AND o.record_id IS NULL;

-- Output không thuộc source batch snapshot.
SELECT o.record_id
FROM normalized_payment o
LEFT JOIN staged_payment s
  ON s.batch_key = o.batch_key
 AND s.record_id = o.record_id
WHERE o.batch_key = :batchKey
  AND s.record_id IS NULL;

-- Sai tenant hoặc giá trị business, giả sử rule net = amount * 95%.
SELECT s.record_id, s.amount, o.net_amount
FROM staged_payment s
JOIN normalized_payment o
  ON o.batch_key = s.batch_key
 AND o.record_id = s.record_id
WHERE s.batch_key = :batchKey
  AND (
      o.tenant_id <> s.tenant_id
      OR o.net_amount <> ROUND(s.amount * 0.95, 2)
  );
~~~

**Kỳ vọng:** cả ba truy vấn không có row. Nếu fixture có `input_version`, test phải xác nhận mọi source row thuộc đúng version hoặc bổ sung predicate version trong staging identity; nếu `batchKey` có thể bị dùng lại cho nhiều snapshots thì business key/schema cần chứa version hoặc batch identity phù hợp.

**Đừng chỉ so `COUNT(*)`.** Input thiếu record A nhưng output thừa record B có thể vẫn cho count bằng nhau. Nếu job có filter/skip, mở rộng expected outcome thành **output ∪ filtered ∪ quarantined** với policy rõ; `writeCount` metadata không thay kết quả SQL.

## 34. Resource bottleneck migration

Tăng gridSize hoặc active workers có thể chuyển bottleneck:

~~~text
G=1:
  CPU worker bận, DB rất nhàn.

G=4:
  CPU và DB được sử dụng tốt hơn; thông lượng tăng.

G=8 (8 active workers):
  DB connections pending; nhiều workers chờ.

G=16:
  DB lock waits + GC + broker reply queue tăng;
  throughput gần như không đổi, p99 tăng mạnh.
~~~

**Không phải các mốc trên luôn đúng**; chỉ là một chuỗi hành vi có thể gặp. Luôn đo bottleneck **sau mỗi thay đổi**. Nếu DB bị giới hạn bởi một hot row, thêm processors không giải quyết; nếu reader tại manager là cổ chai, remote partitioning giúp khi reader được chia sang workers, còn remote chunking có thể vẫn giữ reader tại manager.

### Cân nhắc database CPU, không chỉ connection pool

Một pool có 12 connections nhưng DB CPU 100% nghĩa thêm 12 connections khác có thể tăng context switching/locks và làm p99 tệ hơn. Ngược lại, nếu nhiều connections pending nhưng server CPU/IO thấp, có thể đang sizing pool quá nhỏ hoặc connections bị giữ bởi cursor lâu. Tìm **cause** bằng pool wait, query profile và resource metrics.

## 35. Remote partitioning: gridSize và worker fleet

Ở remote partitioning, `gridSize=16` có thể tạo 16 logical partitions rồi dispatch cho worker JVMs qua middleware. **Số workers/node/consumer concurrent** do deployment, broker và handler configuration quyết định.

~~~mermaid
flowchart TB
    M["Manager: gridSize=16"] --> P["16 partition requests"]
    P --> Q[("Broker request queue")]
    Q --> A["Worker pod A: concurrency 2"]
    Q --> B["Worker pod B: concurrency 2"]
    Q --> C["Worker pod C: concurrency 2"]
    Q --> D["Worker pod D: concurrency 2"]
    A --> DB[("Shared business DB")]
    B --> DB
    C --> DB
    D --> DB
    A -. "StepExecution" .-> J[("Shared JobRepository")]
    B -. "StepExecution" .-> J
    C -. "StepExecution" .-> J
    D -. "StepExecution" .-> J
~~~

**Đo thêm những tín hiệu chỉ có ở remote:**

- Broker `messages.ready`, `unacked`, oldest age, redelivery/failed publishes.
- Worker fleet active instances, consumer concurrency, scaling lag/startup time.
- Partition request dispatch → worker start latency, worker processing → manager observed completion latency.
- Deserialize/serialization/network bytes per partition; reply correlation/unknown outcomes.
- Shared JobRepository connection/locking overhead và worker DB pool tổng across pods.
- Worker crash/restart, late reply, source locality và permission/mount failures.

**Một job có 16 partitions trên bốn pods không tự có 16 CPU workers**. Nếu mỗi pod chỉ cho concurrency=2 thì capacity tối đa khoảng tám worker steps trước khi tính pool/DB. Thêm pods có thể tăng throughput nếu tài nguyên chung không nghẽn, nhưng **không** biến mỗi partition thành exactly-once delivery.

## 36. Chọn gridSize khi có worker autoscaling

Khi worker fleet autoscale, số active workers thay đổi **trong một run**. Benchmark cần ghi:

1. Grid size và số partitions thực.
2. Số worker instances/consumer slots theo thời gian.
3. Worker pod startup/warm-up time.
4. Thời gian work chờ queue trước khi scale-out.
5. Số partitions được xử lý trước khi pod mới ready.
6. Tail duration của last partitions và thời gian scale-in.

**Không lấy giá trị replicas ở cuối run rồi suy mọi giây đều có số ấy.** Nếu 8 pods chỉ ready ở phút thứ 5 trong job 7 phút, speedup khác nhiều việc có sẵn 8 pods từ đầu.

**Đánh đổi:** chia nhiều partitions nhỏ tạo work đủ cho autoscaler phân phối nhưng tăng metadata/broker overhead; chia quá ít partitions khiến pods mới idle và một straggler giữ cả job. Tìm granularity dựa **partition duration so với startup+dispatch overhead**, không dựa một công thức cứng.

## 37. Failure/restart phải là một pha benchmark riêng

Một cấu hình `G=32` có thể hoàn tất nhanh hơn `G=8` khi không lỗi nhưng **khôi phục chậm hơn** do nhiều worker contexts/checkpoints/retries. Thử ít nhất:

| Fault | Mục đích | Assertion sau recovery |
| --- | --- | --- |
| Processor fail ở một partition | Kiểm independent chunk transactions | Failed partition hiển thị đúng; partial committed work còn |
| Worker JVM kill trước commit | Kiểm rollback và restart | Không có output chưa commit được coi success |
| Worker kill sau commit trước reply | Kiểm commit/ACK uncertainty | Idempotent replay, không duplicate effects |
| Manager restart giữa dispatch | Kiểm durable pending/reply state | Không mất partition hoặc accept stale reply |
| DB pool timeout | Kiểm resource saturation | Failure/timeout bounded, không treo vĩnh viễn |
| DB deadlock | Kiểm retry classification | Retry/fail theo policy, không double-apply |
| Broker queue backlog | Kiểm distributed saturation | Pending age/dispatch lag rõ |
| Source version thay | Kiểm snapshot integrity | Fail/quarantine thay vì restart sai dữ liệu |
| Last partition rất chậm | Kiểm straggler tail | Không “complete early”, QoS được đo |

**Với local partitioning**, kill JVM làm **manager và mọi local worker threads** cùng chết; lỗi một worker thread throw exception **không tương đương** whole-JVM crash. **Với remote partitioning**, kill một worker node có thể để manager và các nodes khác sống; test hai failure modes riêng.

**Không gọi một run `COMPLETED` sau restart là đúng nếu chưa đối soát**. JobRepository checkpoint và business DB commit có thể không nằm trong một ACID transaction, nên output idempotency cần chịu được replay.

## 38. Không thay gridSize giữa restart cùng JobInstance

Giả sử lần đầu:

~~~text
grid=4:
partition0 = [0,2M)
partition1 = [2M,4M)
partition2 = [4M,6M)
partition3 = [6M,8M)
~~~

Manager chạy 60% rồi FAILED. Nếu restart mà đổi grid=8 và tính lại ranges:

~~~text
partition0 = [0,1M)      (cùng tên nhưng nghĩa khác)
partition1 = [1M,2M)
...
~~~

Một `StepExecution` cũ tên `partition0` có checkpoint cho range `[0,2M)`; partition mới cùng tên `[0,1M)` có semantics khác. **Không an toàn khi tự thay mappings** và giả định framework vẫn resume đúng. Để benchmark grid khác, tạo **JobInstances độc lập**, không ép cùng JobInstance nhận grid mới.

Với restart thực:

- Giữ identifying JobParameters/snapshot.
- Giữ partition identities và `ExecutionContext` ổn định theo hợp đồng.
- Nếu framework sử dụng `PartitionNameProvider` để lấy names trên restart, đảm bảo names nhất quán với trước đó.
- Kiểm JobExecution/StepExecution statuses, partial commits, idempotency ledger.
- Không tự sửa bảng `BATCH_STEP_EXECUTION` thành `COMPLETED` để vượt lỗi stale metadata.

**Đây là một trong các khác biệt quan trọng giữa benchmark và production restart.** Một phép thử cấu hình mới không được ngụy trang thành recovery của dữ liệu đang xử lý dở.

## 39. Chọn gridSize bằng SLO và Pareto frontier

Một cấu hình tốt phải đạt **nhiều ràng buộc cùng lúc**:

~~~text
MUST:
  Business reconciliation = PASS
  Job deadline <= 20 phút
  Recovery path = PASS
  Worker / broker / DB resource limits không vượt budget

PREFER:
  Lower median + p95 job makespan
  Lower p99 partition/chunk/record-to-visible latency
  Lower DB pool contention / GC / metadata overhead
  Enough capacity headroom when one worker node is lost
~~~

**Pareto frontier:** một cấu hình không bị cấu hình khác **vừa nhanh hơn (hoặc bằng), vừa ít chi phí/tail latency hơn (hoặc bằng)** với ít nhất một chiều tốt hơn. Khi G8 chỉ nhanh hơn G4 5% nhưng p99 tail, metadata/heap hoặc restart cost tăng mạnh, G4 có thể là lựa chọn production an toàn hơn.

### Cách ra quyết định từng bước

1. Loại run có **missing/duplicate/incorrect output**, sai source version hoặc job status không rõ.
2. Loại run vi phạm hard SLA deadline, latency, DB max connection, memory/queue budget.
3. So các ứng viên bằng **median + run-to-run variability**, không chọn một best-case sample.
4. So tốc độ **logical committed effects**, không chỉ `writeCount` hoặc record reads.
5. Xem p95/p99 **slowest partition**, retries và recovery khi một worker crash.
6. Kiểm headroom ở 70–80% peak load hoặc theo capacity policy thực, không coi 100% utilization là thành công mặc định.
7. Chọn cấu hình đơn giản/ổn định nếu speedup tăng không đáng kể.
8. Ghi rõ khi nào cần **benchmark lại**: schema/index changes, data skew, worker pool, DB version, workload size hoặc transport thay đổi.

**Không coi `gridSize=CPU cores` là nguyên tắc phổ quát**: CPU-bound và I/O-bound khác nhau; pool workers, DB servers, queueing và partition costs mới quyết định.

## 40. Báo cáo benchmark có thể kiểm toán

Một báo cáo cho mỗi run nên chứa:

~~~yaml
# Một mẫu report YAML minh họa, không phải config Spring Batch.
runId: benchmark-grid-008-run-03
experiment: strong-scaling-fixed-pool
environment:
  java: "17"
  springBatch: "5.x"
  db: "PostgreSQL, version được ghi từ môi trường thực"
  workerPoolSize: 4
  datasourcePoolLimit: 12
input:
  snapshotId: "staged-payment-v3"
  logicalInputRecords: 8000000
  inputChecksum: "sha256:expected-immutable-manifest-hash"
parameters:
  requestedGridSize: 8
  partitionsReturned: 8
  chunkSize: 200
results:
  jobStatus: COMPLETED
  wallTimeSeconds: 540
  committedLogicalRecords: 8000000
  committedThroughputPerSecond: 14815
  maxActiveWorkers: 4
  maxExecutorQueued: 4
  missingRecords: 0
  extraRecords: 0
  valueMismatches: 0
  correctness: PASS
notes:
  - "Số liệu và checksum chỉ minh họa định dạng báo cáo"
~~~

**Không copy giá trị giả vào báo cáo thực.** Ghi Java/OS/container CPU limits, DB cluster topology, migration schema revision, broker config (nếu remote), cold/warm cache policy, run timestamps, benchmark seed và link tới logs/traces/captured metadata khi được phép.

### Kết quả statistical nên được trình bày thế nào?

Nếu mỗi cấu hình chạy bảy lần, nên ghi `median(T_job)`, `IQR`/min–max hoặc confidence interval phù hợp, và toàn bộ raw samples cho review. Nếu run B nhanh hơn A chỉ 1–2% nhưng IQR lớn, **không khẳng định có speedup đáng tin cậy**. Với p99 chunk latency, cần histogram đủ lượng observations; không lấy p99 của từng worker rồi **trung bình** thành p99 tổng.

Thứ tự chạy các cấu hình nên được đảo hoặc random hóa có seed để tránh xu hướng warm cache. Cần xem xét multiple comparisons khi thử rất nhiều configs rồi chỉ chọn giá trị tốt nhất.

## 41. Các negative tests trước khi tin đường cong

| Test | Điều kiện tạo lỗi | Kỳ vọng |
| --- | --- | --- |
| T01 | `gridSize=0` | Fail-fast configuration, không chạy job |
| T02 | `gridSize > số records/files` | Partitioner policy rõ, không giả concurrency |
| T03 | Sparse IDs tạo empty ranges | Không missing/overlap, skew được đo |
| T04 | Reader dùng end inclusive sai | Property/integration test phát hiện boundary duplicate |
| T05 | Hai batches cùng record IDs | Không cross-batch output |
| T06 | Tăng grid, giữ pool=1 | Active workers vẫn ~1; không báo giả concurrency |
| T07 | Bốn workers, DB pool thiếu | Pending/timeout rõ, không treo vô hạn |
| T08 | Executor queue/rejection | Job status thất bại đúng, không mất partition |
| T09 | Một worker StepExecution fail | Partial commits/restart policy đúng |
| T10 | Job restart source snapshot đổi | Detect mismatch, không đọc tiếp checkpoint sai |
| T11 | Writer `DO NOTHING` trên output tồn tại | Reconciliation/metric không gọi no-op là new throughput |
| T12 | Một partition 90% records | Job tail/skew được phản ánh |
| T13 | Processor jitter không đều | Có variability và đủ samples |
| T14 | Processor CPU-bound bão hòa | G lớn hơn core/pool không giúp vô hạn |
| T15 | DB hot-row lock contention | p99/throughput phản ánh lock waits |
| T16 | Worker JVM crash trước commit | Rollback và replay an toàn |
| T17 | Worker commit rồi mất reply | Idempotent replay, outcome không đếm trùng |
| T18 | Remote reply đến muộn | Không correlate vào JobExecution mới |
| T19 | Tăng partitions tới hàng nghìn | Metadata overhead/JobRepository pressure có evidence |
| T20 | Benchmark run A/B không cùng source version | Harness loại kết quả không so sánh được |
| T21 | Filter/skip records có policy | Quality gate dựa exact expected outcomes |
| T22 | Broker backlog khi scale remote nodes | Queue wait vs worker service time đo riêng |

Các tests T01–T05 phù hợp unit/property/integration; T06–T15 cần DB/executor metrics; T16–T18 cần fault injection/crash test trong môi trường tách biệt. **Không tạo 8 triệu records và kill process mỗi lần chạy unit tests**; phân tầng suite để đảm bảo CI vẫn thực dụng.

## 42. Runbook khi gridSize tăng nhưng job chậm hơn

**Tình huống:** G=4 cho elapsed 600 giây, G=16 cho elapsed 750 giây trên cùng snapshot, mặc dù manager tạo đủ 16 partitions.

1. **Kiểm experiment validity:** cùng snapshot, data output reset đúng, chunk size/worker CPU/DB config không bị thay; correctness PASS?
2. **Kiểm effective concurrency:** `partitionsReturned`, executor active max, queue depth, remote workers ready count có tương xứng?
3. **Xem per-partition durations/counts:** có một straggler, partitions rỗng hay quá nhiều tiny partitions?
4. **Kiểm reader/source:** indexed range scans hay full scans, source I/O contention, connection lifetime?
5. **Kiểm DB writer:** pool active/pending, transaction duration, row locks/deadlocks, WAL/checkpoint, unique key conflicts.
6. **Kiểm JobRepository:** metadata insertion/update latency, StepExecution count, shared pool contention.
7. **Kiểm JVM:** CPU saturation, GC pause, heap bytes/items in-flight, thread scheduling.
8. **Nếu remote:** broker queue age, unacked/redelivery, header/routing, worker startup và reply delay.
9. **Phân biệt attempts vs effects:** tăng retry/duplicate/no-op có đang làm raw processor/s cao giả?
10. **Tìm knee point:** chạy lại G=4/8/16 theo thứ tự đảo, đủ repetitions và ghi variation.
11. **Chỉ thay một biến:** giảm G, đổi partition strategy, điều chỉnh pool/chunk/SQL trong pha riêng; đo lại end-to-end.
12. **Chốt cấu hình có headroom:** correctness, deadline, tail, resource budget và recovery đều đạt; lưu report và điều kiện rollback.

### Chẩn đoán A — grid=16 nhưng chỉ có bốn active workers

~~~text
Requested grid: 16
Partitions returned: 16
Executor max active: 4
Executor queue: 12 at peak
DB CPU: ~45%
Worker pool configured max: 4

=> Không có 16 worker parallel. Muốn test 16 active workers,
   phải làm thí nghiệm pha 2 với pool budget riêng,
   rồi quan sát DB/resource headroom.
~~~

### Chẩn đoán B — có 16 workers nhưng DB saturated

~~~text
Requested grid: 16
Active workers: 16
DB CPU: ~100%
Hikari pending: high
DB lock wait p99: high
Logical committed throughput: almost flat

=> Chạm bottleneck DB. Tăng grid tiếp thường tạo WIP/latency,
   không có thêm committed results. Kiểm SQL/locks,
   reducing hot spots, pool và concurrency cap.
~~~

### Chẩn đoán C — nhiều partitions nhưng vẫn có một straggler

~~~text
Partitions: 32
P0..P30: 20-30 seconds each
P31: 6 minutes because 80% expensive rows
Overall job: dominated by P31

=> Chia theo actual cost/record volume thay vì ID width,
   hoặc dùng smaller stable shards/dynamic work queue
   với recovery protocol phù hợp.
~~~

**Không tăng timeout vô hạn, xóa JobRepository, tắt validation hoặc cho skip mọi exception** để benchmark “xanh”. Các thao tác ấy có thể che mất data correctness và làm độ tin cậy production kém đi.

## 43. Anti-patterns trong benchmark gridSize

| Sai lầm | Tác hại | Thay bằng |
| --- | --- | --- |
| Gọi `gridSize` là số CPU threads | Kết luận speedup sai | Đo partitionsReturned/activeWorkers |
| Benchmark grid và chunk size đổi cùng lúc | Không phân biệt nguyên nhân | Sweep từng biến rồi test interaction |
| Thay grid giữa restart JobInstance | Partition names/checkpoints có thể lệch | Independent JobInstances cho mỗi config |
| Source DB mutable trong lúc chia range | Mất/trùng records | Immutable snapshot/version |
| `BETWEEN start AND endExclusive` | Đọc boundary hai lần | `>= start AND < endExclusive` |
| Dùng H2 để khẳng định PostgreSQL throughput | Query plans/locks/SQL khác | DB sát production/Testcontainers |
| Không kiểm StepExecution per partition | Không thấy skew/failures | Worker metadata + business DB |
| Chỉ đo processor time | Bỏ reader/DB/metadata/publication | End-to-end measurement |
| Lấy mean hoặc best run duy nhất | Bị noise/cache/outlier | Median + variability + repetitions |
| Chạy grid theo thứ tự tăng cố định | Warm cache bias | Randomize/rotate order |
| Tái sử dụng output từ run trước | Upsert no-op làm nhanh giả | Isolated output/verified reset |
| Đếm broker ACK/read/s là throughput | Chưa có business commit | Logical committed outcomes |
| G quá lớn trên ít data | Empty/tiny partitions overhead | Bounded grid, cost-aware partitions |
| Thấy DB pool pending thì tăng pool mãi | DB server có thể saturation | Đo server CPU/locks và transaction |
| Tăng worker nhưng source reader singleton | Cursor/thread safety lỗi | Step-scoped reader/partition ranges |
| Không test failure/restart | Benchmark tốt khi happy path nhưng replay sai | Fault injection + idempotency |
| Không đặt limit cho executor queue | Memory/backlog/latency tăng | Bounded queue/rejection policy |
| Bỏ qua JobRepository overhead | G lớn có thể nghẽn metadata | Repository metrics và retention |
| Dùng metric tag là partition ID hàng triệu giá trị | Cardinality tăng mạnh | Low-cardinality metric labels |
| Chọn grid tối đa, không xét SLA/chi phí | Tail/recovery/cost kém | Pareto/SLO + headroom |

## 44. Bài thực hành cuối bài

Thiết lập một job Spring Batch 5.x/Java 17+ dùng **PostgreSQL immutable staging**, `BenchmarkRangePartitioner`, `@StepScope` reader, business writer idempotent và `TaskExecutorPartitionHandler`. Tạo ba datasets: **uniform**, **sparse** và **skewed cost**; một phiên bản dùng local workers, một phiên bản remote nếu có sẵn broker/worker topology.

**Phần A — correctness và baseline**

1. Seed 100.000 records trong fast integration profile và 8 triệu records trong performance profile, kèm snapshot/version.
2. Unit test `gridSize=0/1/2/4/8` với range coverage, edge cases, no overlap/gap và per-tenant isolation.
3. Chạy G=1, pool=4, chunk=200, ghi start/end, StepExecution/DB outcome, CPU/connection metrics.
4. Đối soát source keys/values với business output; đảm bảo same snapshot semantics.

**Phần B — sweep gridSize**

5. Giữ pool=4, thử G=1/2/4/8/16/32. Mỗi config dùng JobInstance mới và output isolate.
6. Chạy nhiều repetitions, đảo thứ tự các configs, ghi raw samples.
7. Báo requested grid, actual partitions, max active workers, queue max, per-partition duration, logical commits/s và total makespan.
8. Lập bảng speedup, parallel efficiency theo đúng mẫu số và chọn knee candidates.

**Phần C — kiểm resource và skew**

9. Chạy G=8 với pool=4 vs pool=8; so DB pending/CPU/GC và elapsed.
10. Tạo một hot aggregate row để thử DB lock contention; ghi p99 transaction duration.
11. Chạy sparse/skewed data và xem partition worker duration distribution.
12. Chuyển từ numeric range sang balanced-by-record-count strategy; giữ source/rule tương đương.
13. Thử chunk=50/200/1000 **trong pha riêng**, chỉ sau khi grid sweep xong.

**Phần D — recovery và báo cáo**

14. Tiêm lỗi ở một partition sau vài chunks commit, restart cùng JobInstance và source mapping không đổi.
15. Tiêm worker crash trước/sau commit ở test process-level/broker phù hợp; đảm bảo idempotency.
16. Kiểm exact business coverage, payload/value correctness, no duplicate logical effects sau recovery.
17. Đề xuất gridSize dựa trên SLO, capacity headroom, cost và variability; ghi điều kiện rollback/rebenchmark.

**Tiêu chí đạt:** người học có **evidence đo được**, không chỉ “G8 nhanh hơn G4” từ một lần; có test chứng minh executor active thực, data correctness được bảo vệ, không đổi grid khi restart và hiểu nguyên nhân nếu tăng grid làm job chậm đi.

## 45. Checklist trước production

- [ ] `gridSize` được hiểu là **partitioning hint**, khác `partitionsReturned`, thread pool, remote pods và DB connections.
- [ ] Có baseline G=1 và benchmark sweep nhiều G trên **cùng immutable snapshot**.
- [ ] Dùng independent JobInstances cho grid khác nhau; restart giữ mapping/identifying parameters.
- [ ] Partitioner/reader coverage được unit/integration test: ranges nửa mở, không overlap/gap, đúng batch/version.
- [ ] `@StepScope`/reader state bảo đảm thread safety per worker StepExecution.
- [ ] Có resource budget rõ cho executor queue, JDBC pool, CPU/heap và worker nodes.
- [ ] Đã đo actual active worker steps và queue wait, không suy từ G.
- [ ] Có `JobRepository` worker StepExecution counts, statuses, durations và metadata latency.
- [ ] Committed logical throughput được phân biệt với read/attempt/writeCount/broker ACK rates.
- [ ] Có exact source/output key/value reconciliation sau mọi benchmark.
- [ ] Writer idempotent; duplicate key khác payload được phân loại theo policy.
- [ ] Không dùng output cũ làm các runs sau dễ hơn hoặc “chạy nhanh” giả.
- [ ] DB schema/index/plan và source/target state được giữ công bằng giữa các runs.
- [ ] Các runs được lặp lại, đổi thứ tự, báo median/variation, không chọn best-case.
- [ ] Strong scaling và weak scaling được ghi nhãn rõ, không ghép tốc độ khác workloads.
- [ ] Đã kiểm skew theo actual item count/bytes/cost, không chỉ numeric range width.
- [ ] Đã kiểm pool pending, DB locks, WAL, source I/O, GC và worker/JobRepository overhead.
- [ ] Khi G lớn, đã kiểm tiny/empty partitions và metadata scheduling overhead.
- [ ] Remote benchmark đã đo queue age, redelivery, worker autoscaling/startup và reply handling.
- [ ] Có fault tests: worker fail, JVM kill, commit/reply uncertainty, restart và source mismatch.
- [ ] Có SLO về job deadline, p95/p99 tail, recovery latency và resource headroom.
- [ ] Đã lựa chọn knee/Pareto candidates dựa correctness, stability và cost thay vì maximum grid.
- [ ] Metrics tags có cardinality kiểm soát; execution/partition IDs nằm ở logs/traces/metadata.
- [ ] Báo cáo benchmark lưu snapshot ID, run config, versions, data checks, raw samples và runbook.
- [ ] Có quy trình rebenchmark khi source distribution, business SQL, DB/CPU hoặc worker topology thay đổi.

**Ghi nhớ:** **benchmark gridSize** không phải tăng dần một số nguyên tới khi thấy CPU cao. Trong Spring Batch partitioning, cần **tách gridSize khỏi số partition thực và worker concurrency**, so các runs trên cùng snapshot, đo **JobExecution makespan, committed logical throughput, worker tail/skew, DB/JobRepository contention**, rồi đối soát source-output và thử restart/crash. Giá trị tốt nhất là **điểm cân bằng có bằng chứng và đủ headroom**, không nhất thiết là gridSize lớn nhất hay cấu hình có thời gian tốt nhất trong một lần chạy.

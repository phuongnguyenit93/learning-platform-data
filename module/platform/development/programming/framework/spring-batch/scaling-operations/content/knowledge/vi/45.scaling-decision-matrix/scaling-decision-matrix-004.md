# Khi nào dùng local partitioning trong Spring Batch?

> **Chương:** Ma trận lựa chọn  
> **Module:** `SPRING_BATCH_SCALING_OPERATIONS` — mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán; chú trọng đo nút thắt, thread safety, retry/restart và vận hành dựa trên tài nguyên thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nêu chính xác **local partitioning** là gì, cách nó khác multi-threaded step, parallel steps, remote partitioning và remote chunking.
2. Quyết định **khi nào nên dùng** dựa trên khả năng chia dữ liệu, tài nguyên một JVM, thời gian xử lý, yêu cầu phục hồi và chi phí vận hành.
3. Thiết kế partition không chồng lấn, có ranh giới ổn định qua retry/restart và xử lý được data skew.
4. Phân biệt `gridSize`, số partition thực tế, concurrency của `TaskExecutor`, `chunkSize` và kích thước connection pool.
5. Vận dụng `StepScope`, `ExecutionContext`, `JobRepository`, writer idempotent và các phép đối soát để bảo đảm tính đúng đắn.
6. Thiết lập baseline, thử nghiệm tăng tải và tiêu chí go/no-go trước khi đưa local partitioning vào production.

## 1. Câu trả lời nhanh: khi nào chọn local partitioning?

**Local partitioning** là cơ chế Spring Batch chia một **worker step** thành nhiều phân vùng logic (partition). Mỗi partition có một `StepExecution` và `ExecutionContext` riêng; các worker step chạy **đồng thời trong cùng tiến trình JVM** nhờ `TaskExecutor`, thường do `TaskExecutorPartitionHandler` phối hợp.

Nên ưu tiên đánh giá **local partitioning** khi đồng thời có những điều kiện:

1. **Dữ liệu có thể chia thành các tập độc lập:** theo dải khóa, shard, file, tenant hoặc manifest đã chốt; mỗi bản ghi thuộc đúng phạm vi dự kiến.
2. **Một máy/JVM vẫn còn dư năng lực thực:** CPU, heap, I/O, connection pool và dịch vụ downstream chịu được concurrency tăng.
3. **Muốn có checkpoint và trạng thái theo partition:** dễ quan sát phần việc hoàn tất/thất bại và khởi động lại những partition đủ điều kiện.
4. **Chưa cần phân phối qua nhiều nút:** không muốn gánh thêm message broker, remote worker lifecycle, network và correlation protocol.

Không nên dùng local partitioning chỉ vì job xử lý nhiều dòng. Nếu database đã bão hòa, reader không chia được dữ liệu, tác vụ phải thực hiện tuần tự theo thứ tự toàn cục hoặc một JVM không đủ CPU/RAM, tăng số partition có thể **làm job chậm hơn hoặc tăng rủi ro dữ liệu**.

> **Quy tắc quyết định:** local partitioning phù hợp khi **có thể chia công việc đúng**, **có tài nguyên cục bộ để chạy song song**, và **muốn quản lý từng phần việc bằng metadata Spring Batch**.

### Tình huống trực quan

Một job đọc 8 triệu bản ghi đã chốt trong bảng `invoice_snapshot` và tính tổng mỗi hóa đơn độc lập. Server có 8 CPU, database còn băng thông và connection pool. Có thể chia 8 triệu record thành 16 dải ID ổn định; chạy tối đa 4 dải đồng thời trong một JVM rồi benchmark tăng lên 8. Đây là ứng viên tốt cho local partitioning.

Ngược lại, nếu mọi giao dịch phải ghi vào cùng một sổ cái theo **thứ tự thời gian tuyệt đối** và bản ghi sau phụ thuộc số dư bản ghi trước, partitioning không tự giải quyết quan hệ phụ thuộc đó. Phải thiết kế lại bất biến theo từng tài khoản hoặc giữ phần nghiệp vụ bắt buộc tuần tự.

## 2. Cơ chế hoạt động

Một **manager step** gọi `Partitioner` để sinh bản đồ partition name → `ExecutionContext`. Spring Batch tạo/điều phối `StepExecution` tương ứng, giao cho `PartitionHandler` chạy worker step và tổng hợp trạng thái. Trong local partitioning, những worker step chạy bằng các luồng trong **cùng một JVM**.

~~~mermaid
flowchart TB
    J[Job] --> M[Manager / PartitionStep]
    M --> P[Partitioner tạo manifest phân vùng]
    P --> EC1["partition-000: ExecutionContext A"]
    P --> EC2["partition-001: ExecutionContext B"]
    P --> ECN["partition-N: ExecutionContext N"]
    EC1 --> W1[Worker StepExecution A]
    EC2 --> W2[Worker StepExecution B]
    ECN --> WN[Worker StepExecution N]
    W1 --> T[TaskExecutor: giới hạn thread đồng thời]
    W2 --> T
    WN --> T
    T --> S[Reader / Processor / Writer theo partition]
    S --> DB[(Business data)]
    W1 -. status, checkpoint .-> JR[(JobRepository)]
    W2 -. status, checkpoint .-> JR
    WN -. status, checkpoint .-> JR
    JR -. tổng hợp trạng thái .-> M
~~~

**Những điều không nên hiểu nhầm:**

- `gridSize=16` là một thông số gợi ý cho việc phân vùng; không tự tạo 16 JVM hoặc bảo đảm 16 luồng xử lý đồng thời. `Partitioner` quyết định số partition trong map trả về.
- `TaskExecutor` quyết định **bao nhiêu worker step có thể chạy đồng thời trong JVM**, chịu ảnh hưởng từ cấu hình pool/queue và các hạn chế khác.
- `chunkSize` quyết định kích thước giao dịch/chunk ở **bên trong từng worker step**. Có 16 partition với `chunkSize=500` không có nghĩa sẽ commit 8.000 record một lần.
- Mỗi partition có `StepExecution` riêng, nhưng **không đồng nghĩa** mỗi partition có toàn bộ tài nguyên riêng: mọi partition vẫn chia sẻ CPU, heap, mạng, disk, DB và các singleton ứng dụng.
- Local partitioning thường sử dụng chung một `JobRepository`; nếu ứng dụng crash, tất cả worker thread đang hoạt động trong JVM đó đều chịu ảnh hưởng.

### Những thành phần cần biết

| Thành phần | Chức năng | Điều cần lưu ý |
|---|---|---|
| `PartitionStep` / manager step | Quản lý partition và trạng thái | Phải quan sát cả manager lẫn worker executions |
| `Partitioner` | Sinh tên partition và `ExecutionContext` | Ranh giới phải ổn định, đúng và không chồng lấn |
| `TaskExecutorPartitionHandler` | Chạy worker step cục bộ bằng `TaskExecutor` | Không tạo worker trên máy khác |
| `StepExecution` | Trạng thái và số đếm của một partition | Có thể restart tùy chính sách step/job |
| `ExecutionContext` | Lưu tham số phân vùng và checkpoint | Hợp đồng key/serializer phải ổn định qua restart |
| `@StepScope` | Tạo bean theo ngữ cảnh step execution | Tránh chia sẻ state reader/writer không thread-safe |
| `JobRepository` | Lưu metadata thực thi | Tăng số partition/chunk có thể tăng tải DB metadata |

## 3. Ma trận so sánh các lựa chọn scaling

| Cách xử lý | Đơn vị song song | Nơi chạy | Thích hợp khi | Chi phí/rủi ro chính |
|---|---|---|---|---|
| **Single-thread step** | Một luồng/chunk tuần tự | Một JVM | Khối lượng nhỏ, logic thứ tự, baseline | Throughput bị giới hạn |
| **Multi-threaded step** | Chunk song song của **cùng step execution** | Một JVM | Muốn song song chunk và các component xử lý được concurrency | Reader/writer thread safety, thứ tự đọc, restart phức tạp |
| **Local partitioning** | **Nhiều StepExecution** theo dải dữ liệu | Một JVM, nhiều thread | Dataset chia độc lập; cần cô lập state/checkpoint theo partition | Khai thác giới hạn một node; manifest và resource contention |
| **Parallel steps** | Các step khác nhau chạy song song | Một JVM hoặc mô hình triển khai tương ứng | Nhiều nhánh công việc độc lập trong flow | Phụ thuộc giữa step, tổng hợp kết quả |
| **Remote partitioning** | Partition được giao cho worker process | Nhiều JVM/nút | Một node không đủ tài nguyên hoặc cần scale ngang | Messaging, ownership, network, version/contract, quan sát phân tán |
| **Remote chunking** | Manager đọc và gửi chunk cho worker | Nhiều JVM/nút | Reader tập trung, processor/writer cần phân tán | Request/reply, redelivery, idempotency, manager bottleneck |

**Câu hỏi phân biệt quan trọng:** nếu vấn đề là nhiều **nhánh business flow**, nghĩ tới *parallel steps*. Nếu đó là **một loại step áp dụng cho nhiều tập dữ liệu độc lập**, nghĩ tới *partitioning*. Nếu công việc phải phân tán qua nhiều máy, cân nhắc *remote partitioning*; local partitioning không vượt qua giới hạn tài nguyên của một JVM.

### 3.1. Local partitioning so với multi-threaded step

Cả hai có thể dùng `TaskExecutor` nhưng trạng thái xử lý khác nhau:

- **Multi-threaded step:** các chunk cùng thuộc một step logic và có thể dùng chung reader/processor/writer tùy cấu hình. Phải xác minh khả năng thread-safe của từng component và semantics của checkpoint trong môi trường nhiều luồng.
- **Local partitioning:** mỗi partition có `StepExecution` và context riêng; với bean `@StepScope` đúng cách, reader/writer có state riêng cho từng worker step. Đây là ưu thế khi reader là dạng cursor/paging theo từng dải dữ liệu.

Local partitioning vẫn cần kiểm tra **shared singleton**, static cache, DB connection pool, transaction isolation và bảng kết quả chung. Partition không tạo một JVM độc lập để bảo vệ khỏi race condition.

### 3.2. Local partitioning so với remote partitioning

Hai mô hình thường dùng chung ý tưởng `Partitioner`, `StepExecution` và ranh giới dữ liệu. Khác biệt cốt lõi:

| Tiêu chí | Local | Remote |
|---|---|---|
| Vị trí worker | Thread cùng JVM | Tiến trình hoặc máy khác |
| Truyền công việc | Điều phối trong process | Cần hạ tầng giao tiếp/transport được cấu hình |
| Network giữa manager/worker | Không cần broker cho điều phối nội bộ | Thường có message/broker hoặc transport tương ứng |
| Giới hạn scale | CPU, RAM, I/O của node | Cụm worker và tài nguyên downstream |
| Khi JVM crash | Mọi partition đang chạy đều bị ảnh hưởng | Worker khác có thể tiếp tục, tùy thiết kế |
| Độ phức tạp vận hành | Thấp hơn | Cao hơn: routing, retry, DLQ, version contract, scaling |

Đừng xem remote partitioning là bước nâng cấp bắt buộc chỉ vì dữ liệu có hàng triệu dòng. Nếu DB là nút thắt, tăng số JVM chỉ tăng cạnh tranh connection và lock.

## 4. Cây quyết định chọn local partitioning

~~~mermaid
flowchart TD
    A[Job hiện tại chưa đạt SLA] --> B{Đã đo bottleneck?}
    B -->|Chưa| BASE[Đo baseline CPU, I/O, DB, wait, throughput]
    BASE --> B
    B -->|Rồi| C{Đầu vào chia độc lập được?}
    C -->|Không| ALT[Giữ tuần tự hoặc thiết kế lại data dependency]
    C -->|Có| D{Một JVM còn tài nguyên thực?}
    D -->|Không| E{Nguồn downstream còn khả năng scale?}
    E -->|Không| TUNE[Tối ưu SQL, pool, I/O, truy vấn, downstream]
    E -->|Có| REM[Đánh giá remote partitioning / nhiều node]
    D -->|Có| F{Cần trạng thái/checkpoint theo phần dữ liệu?}
    F -->|Có| LOC[Thử local partitioning]
    F -->|Không| MT[So sánh multi-threaded step và local partitioning]
    LOC --> BENCH[Benchmark 1, 2, 4, 8 worker và đối soát]
    MT --> BENCH
    BENCH --> G{Throughput tăng và dữ liệu đúng?}
    G -->|Có| GO[Rollout tăng tải có kiểm soát]
    G -->|Không| REVISIT[Xem lại chia dải, skew và tài nguyên]
~~~

Cây quyết định không thay thế benchmark. Nó chỉ giúp giảm số phương án phải thử và buộc nhóm trả lời **tại sao** muốn tăng concurrency.

## 5. Điều kiện tiên quyết: partition độc lập và bao phủ đủ dữ liệu

Partitioning an toàn phụ thuộc vào cách chia dữ liệu hơn là số thread. Mỗi business item phải được xử lý **đúng phạm vi dự kiến**, có thể khôi phục và có khóa nhận diện.

### 5.1. Phép kiểm tra đúng của một tập partition

Gọi `I` là tập business key trong một snapshot logic cố định và `P_i` là tập khóa của partition thứ `i`. Với xử lý một-vào-một, phân vùng lý tưởng có:

~~~text
Union(P_i) = I                         # Không thiếu dữ liệu
Intersection(P_i, P_j) = empty (i != j) # Không chồng lấn dữ liệu
Mỗi partition có tên và phạm vi ổn định qua restart
~~~

Nếu một record được chủ động sao chép sang nhiều partition để phục vụ tính toán, cần **quy tắc kết hợp kết quả** khác; không áp dụng máy móc bất biến “mỗi key xuất hiện một lần”.

### 5.2. Các chiến lược chia đầu vào

| Chiến lược | Khi phù hợp | Điểm phải kiểm tra |
|---|---|---|
| **Range theo ID hoặc thời gian** | Dữ liệu có khóa có thể sắp xếp, range scan nhanh | Dải thưa/dày gây skew; cutoff và ranh giới inclusive/exclusive |
| **Hash/modulo theo business key** | Khóa phân bố đều, không cần thứ tự | Index/SQL có hỗ trợ, modulo ổn định qua restart |
| **Danh sách file/object shard** | Input gồm nhiều file độc lập | File immutable, version/ETag, không đọc hai lần một file |
| **Tenant/merchant/region** | Có boundary nghiệp vụ rõ | Tenant lớn tạo partition quá tải; cần phân biệt quyền truy cập |
| **Manifest theo khối lượng ước lượng** | Dữ liệu lệch mạnh, cần cân bằng partition | Cần snapshot/manifest bền vững và có thể tạo lại |

Một câu SQL dùng dải nửa mở cho input đã chốt:

~~~sql
SELECT id, amount, merchant_id
FROM invoice_snapshot
WHERE batch_id = :batch_id
  AND id >= :from_inclusive
  AND id < :to_exclusive
ORDER BY id;
~~~

Ví dụ phân vùng:

~~~text
partition-000: [0,       1_000_000)
partition-001: [1_000_000, 2_000_000)
partition-002: [2_000_000, 3_000_000)
...
~~~

Dấu `[a,b)` có nghĩa `a` được tính, `b` không được tính. Dùng nửa mở giúp hai partition liền kề không cùng đọc một ID ranh giới. Các dải chỉ là ví dụ; production phải tính từ khóa thực và bảo đảm không mất record nằm ngoài dải.

**Cần giữ snapshot:** nếu bảng nguồn vẫn thêm/sửa/xóa record trong lúc worker xử lý, hai worker có thể nhìn các trạng thái khác nhau. `batch_id`, snapshot table hoặc high-water mark cố định giúp tránh đọc thiếu/đọc lại khi restart. Với paging reader, sort key nên **duy nhất và ổn định**.

### 5.3. Data skew làm hỏng giả định chia đều

Chia 16 dải ID có chiều dài bằng nhau không có nghĩa 16 dải có khối lượng xử lý bằng nhau. Ví dụ một dải có 70% record, các dải còn lại hầu như rỗng: tốc độ cả job bị giới hạn bởi **partition chậm nhất**.

Khắc phục bằng cách:

1. Thống kê mật độ record/chi phí xử lý theo dải trước khi chia.
2. Chia thành **nhiều partition logic hơn số worker chạy đồng thời**, ví dụ 32–64 partition với 4–8 thread, để queue có cơ hội cân bằng tải.
3. Dùng manifest có các dải theo **số record hoặc work cost ước lượng**, không chỉ chia đều ID space.
4. Với tenant cực lớn, cho phép chia tiếp tenant thành nhóm con theo khóa thứ hai nếu nghiệp vụ cho phép.
5. Đo `p50/p95/max partition duration` và throughput theo partition; không chỉ dùng số partition đã hoàn tất.

Số partition quá lớn cũng có giá: nhiều `StepExecution` hơn, metadata/transaction overhead và thời gian khởi tạo context lớn hơn.

## 6. Cấu hình Spring Batch: ví dụ local partitioning

Ví dụ dưới đây minh họa **Spring Batch theo phong cách builder ở các phiên bản hiện đại**, sử dụng JDBC và `TaskExecutor`. Các lớp domain, store manifest và writer là thành phần **ứng dụng phải tự xây dựng**; tên property, kiểu exception hoặc bean wiring có thể được điều chỉnh theo phiên bản Spring Batch dự án đang dùng.

### 6.1. Tạo một partition manifest cố định

Một manifest được lưu theo `batchId` chứa các tên và dải khóa đã chốt:

~~~text
batchId=invoice-2026-11-26
partition-000: fromInclusive=0,       toExclusive=250000
partition-001: fromInclusive=250000,  toExclusive=500000
partition-002: fromInclusive=500000,  toExclusive=750000
partition-003: fromInclusive=750000,  toExclusive=1000000
~~~

`Partitioner` lấy manifest và chuyển thành `ExecutionContext`:

~~~java
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

import java.util.LinkedHashMap;
import java.util.Map;

// PartitionRange và PartitionManifestStore là abstraction của ứng dụng.
public final class ManifestPartitioner implements Partitioner {
    private final PartitionManifestStore manifestStore;
    private final String batchId;

    public ManifestPartitioner(
            PartitionManifestStore manifestStore, String batchId) {
        this.manifestStore = manifestStore;
        this.batchId = batchId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        // Manifest bất biến, được chốt trước khi bắt đầu JobInstance.
        for (PartitionRange r : manifestStore.loadRanges(batchId)) {
            ExecutionContext context = new ExecutionContext();
            context.putString("batchId", batchId);
            context.putLong("fromInclusive", r.fromInclusive());
            context.putLong("toExclusive", r.toExclusive());

            if (partitions.putIfAbsent(r.name(), context) != null) {
                throw new IllegalStateException("Duplicate partition name");
            }
        }
        return partitions;
    }
}
~~~

Trong ví dụ này, số partition được **manifest định trước**; tham số `gridSize` không dùng để tính lại ranh giới. Đó là lựa chọn có chủ ý nhằm giữ tên/phạm vi ổn định khi restart. Nếu ứng dụng muốn tự sinh partition theo `gridSize`, nó phải lưu hoặc tái tạo **cùng bản đồ partition cho cùng job logic**.

### 6.2. Cấu hình manager và worker step

~~~java
@Bean
public ThreadPoolTaskExecutor localPartitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(32);
    executor.setThreadNamePrefix("batch-partition-");
    executor.initialize();
    return executor;
}

@Bean
public Step localWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<SourceRow> partitionReader,
        ItemProcessor<SourceRow, OutputRow> processor,
        ItemWriter<OutputRow> writer) {

    return new StepBuilder("localWorkerStep", jobRepository)
            .<SourceRow, OutputRow>chunk(500, transactionManager)
            .reader(partitionReader)
            .processor(processor)
            .writer(writer)
            .build();
}

@Bean
public Step localPartitionManager(
        JobRepository jobRepository,
        Step localWorkerStep,
        Partitioner manifestPartitioner,
        ThreadPoolTaskExecutor localPartitionExecutor) {

    return new StepBuilder("localPartitionManager", jobRepository)
            .partitioner("localWorkerStep", manifestPartitioner)
            .step(localWorkerStep)
            .gridSize(16)
            .taskExecutor(localPartitionExecutor)
            .build();
}
~~~

Ở đây `gridSize(16)` là gợi ý; nếu manifest thực tế có 32 partition, map của `ManifestPartitioner` chứa 32 phần. Executor cấu hình tối đa **4 worker task chạy đồng thời** trong ví dụ, phần còn lại chờ queue. Không nên xem `gridSize` như số thread và không đặt `maxPoolSize` bằng số record.

`ThreadPoolTaskExecutor`, `StepBuilder`, `JobRepository`, `PlatformTransactionManager`, `ItemReader`, `ItemProcessor` và `ItemWriter` cần import từ Spring Framework/Spring Batch phù hợp. Mẫu trên tập trung vào việc nối manager/worker; phần tạo `ManifestPartitioner` theo `JobParameters`, khai báo domain, writer và giao dịch phải được hoàn thiện trong ứng dụng.

### 6.3. Reader phải lấy đúng context của partition

Với worker step, reader có thể sử dụng late binding:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<SourceRow> partitionReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['fromInclusive']}") Long fromInclusive,
        @Value("#{stepExecutionContext['toExclusive']}") Long toExclusive,
        @Value("#{stepExecutionContext['batchId']}") String batchId) {

    PostgresPagingQueryProvider query = new PostgresPagingQueryProvider();
    query.setSelectClause("SELECT id, amount");
    query.setFromClause("FROM invoice_snapshot");
    query.setWhereClause(
            "WHERE batch_id = :batchId " +
            "AND id >= :fromInclusive AND id < :toExclusive");
    query.setSortKeys(Map.of("id", Order.ASCENDING));

    return new JdbcPagingItemReaderBuilder<SourceRow>()
            .name("invoicePartitionReader")
            .dataSource(dataSource)
            .queryProvider(query)
            .parameterValues(Map.of(
                    "batchId", batchId,
                    "fromInclusive", fromInclusive,
                    "toExclusive", toExclusive))
            .rowMapper((rs, index) -> new SourceRow(
                    rs.getLong("id"),
                    rs.getBigDecimal("amount")))
            .pageSize(500)
            .saveState(true)
            .build();
}
~~~

Đây là **mẫu cấu hình JDBC/PostgreSQL**; import lớp query provider, `Order` và builder theo version thực tế. `@StepScope` giúp bean nhận đúng `stepExecutionContext` khi worker step chạy, tạo state reader theo partition thay vì tái sử dụng một cursor duy nhất trên nhiều thread. `SourceRow` là domain type của ứng dụng. Đảm bảo cột `id` là sort key duy nhất, phạm vi không overlap và dữ liệu snapshot bất biến trong lúc job/restart.

Một reader dùng checkpoint state cần tên ổn định (ở đây `invoicePartitionReader`), và phải được kiểm thử khi restart. Nếu thay tên bean/reader hoặc cấu trúc `ExecutionContext` giữa các release, checkpoint cũ có thể không còn tương thích.

## 7. `gridSize`, executor, chunk size và pool: bốn núm chỉnh khác nhau

| Cấu hình | Điều khiển | Sai lầm thường gặp |
|---|---|---|
| `gridSize` / manifest | Số phần việc logic hoặc gợi ý cho `Partitioner` | Nghĩ rằng đó là số luồng hoặc số process |
| `TaskExecutor` core/max/queue | Số worker step có thể chạy đồng thời trong một JVM | Dồn quá nhiều task gây quá tải CPU/RAM |
| `chunkSize` | Số item trong một chunk transaction | Tăng quá lớn khiến rollback/retry đắt và heap tăng |
| JDBC/API connection pool | Số kết nối/tác vụ I/O phục vụ worker | Cho nhiều thread hơn tổng tài nguyên DB/downstream |

Một cách ước lượng ban đầu:

~~~text
activePartitions <= availableExecutorThreads
activePartitions <= practicalResourceCapacity

memoryHeadroom >
    activePartitions * (chunkSize * averageItemFootprint
                        + readerBuffers + writerBuffers)
    + JVM/GC/application overhead
~~~

Đây là **bất đẳng thức vận hành sơ bộ**, không phải giới hạn do Spring Batch tự tính. Nhiều writer có thể giữ buffer, batch statement hoặc session riêng; mỗi partition có thể sử dụng nhiều connection trong một transaction phức tạp. Đo heap và connection thực tế mới biết giới hạn.

### Ví dụ chọn concurrency

Giả sử:

- JVM chạy trên một node **8 vCPU**.
- Database có pool giới hạn **24 connection** cho ứng dụng, trong đó các thành phần khác cần giữ khoảng **8 connection**.
- Mỗi worker partition thường giữ **1–2 connection** tại cùng thời điểm tùy implementation.
- Mục tiêu là xử lý 16–32 partition logic.

Khoảng dư DB cho worker là `24 - 8 = 16` connection. Nếu worker có thể dùng 2 connection đồng thời thì giới hạn sơ bộ do DB là `16 / 2 = 8` worker. Nhưng 8 vCPU không có nghĩa luôn nên chạy 8 worker; bắt đầu từ **4 worker**, benchmark 2 → 4 → 8 và kiểm tra cả CPU, GC, pool wait, DB locks, throughput, latency.

Nên dùng **partition count lớn hơn concurrency** một mức hợp lý khi thời gian xử lý từng partition khác nhau. Ví dụ 32 partition, 4 thread cho phép worker rảnh tiếp tục lấy partition kế tiếp mà không phải chờ partition dài nhất ngay từ đầu.

### 7.1. Chọn chunk size

Giả sử mỗi partition có reader/write riêng, `chunkSize=500` nghĩa là một worker xử lý 500 item trong mỗi chunk transaction theo cấu hình. Tăng lên 5.000 có thể giảm số commit và tăng throughput **nếu** writer/broker/DB phù hợp, nhưng cũng làm:

- Dùng thêm RAM cho item/buffer.
- Tăng thời gian giữ transaction và khả năng tranh chấp lock.
- Tăng chi phí làm lại chunk khi transaction rollback.
- Kéo dài thời gian dừng có kiểm soát hoặc checkpoint.

Hãy tune `chunkSize` và worker concurrency theo từng trục trong một phép thử có kiểm soát; tránh thay cả hai rồi không biết nguyên nhân tăng/giảm hiệu năng.

## 8. Ước lượng lợi ích và điểm dừng scale

Local partitioning tăng tốc phần **có thể xử lý song song**. Phần cố định như mở kết nối, sinh manifest, tổng hợp trạng thái, I/O đã bão hòa hoặc bước tuần tự vẫn còn đó.

Một cách ước lượng theo định luật Amdahl:

~~~text
Speedup(N) <= 1 / (s + (1 - s) / N)

s = phần thời gian phải xử lý tuần tự (0 <= s <= 1)
N = số worker có thể chạy song song hiệu quả
~~~

Nếu `s=0.15`, trần tăng tốc lý thuyết với 4 worker:

~~~text
1 / (0.15 + 0.85 / 4) ≈ 2.76 lần
~~~

Với 8 worker:

~~~text
1 / (0.15 + 0.85 / 8) ≈ 3.90 lần
~~~

Đây là **giới hạn minh họa**, chưa tính lock contention, network, GC, data skew, metadata commits và external API rate limit. Trong thực tế, `speedup(N)` có thể thấp hơn nhiều hoặc giảm khi tăng N.

### Bảng benchmark giả định

| Worker đồng thời | Thời gian xử lý cùng snapshot 2 triệu bản ghi | Throughput trung bình | Nhận xét |
|---:|---:|---:|---|
| 1 | 80 phút | ~417 record/giây | Baseline |
| 2 | 44 phút | ~758 record/giây | Tăng tốt |
| 4 | 27 phút | ~1.235 record/giây | Có lợi |
| 8 | 25 phút | ~1.333 record/giây | Lợi ích tăng ít |
| 12 | 31 phút | ~1.075 record/giây | Có thể đã tranh chấp DB/GC |

**Tất cả số trên là ví dụ giả định**, không phải benchmark Spring Batch chung. Nếu đường cong thử nghiệm thực tế giống như vậy, 4 worker có thể là lựa chọn tốt hơn 8–12 worker nhờ ít tài nguyên, độ trễ ổn định và headroom cho tải khác.

### Chi phí không nên bỏ qua

Đối với 64 partition nhưng chỉ 4 worker, số lần ghi metadata và tạo `StepExecution` nhiều hơn so với 4 partition. Nếu partition quá nhỏ, phần tạo/dispatch/commit có thể chiếm tỷ trọng đáng kể. Nếu quá lớn, một partition chậm làm ảnh hưởng thời gian kết thúc toàn job. Chọn granularity từ đo đạc `partitionDuration` và `partitionSkewRatio`, không áp dụng công thức “partition = CPU × 10” cho mọi hệ thống.

## 9. Thread safety và trạng thái khi chạy nhiều partition

**Tạo nhiều `StepExecution` không bảo đảm mọi bean đều cô lập.** Một bean singleton có state mutable vẫn có thể được các worker sử dụng đồng thời.

| Loại thành phần | Rủi ro | Khuyến nghị |
|---|---|---|
| Stateful `ItemReader` | Cùng cursor hoặc chỉ số đọc bị truy cập đồng thời | Bean `@StepScope` riêng theo partition và bounds từ context |
| Stateful `ItemProcessor` | Dùng chung map/cache/counter mutable | Pure function hoặc state theo StepScope, không mutable global |
| `ItemWriter` | Buffer/số thứ tự/connection shared không an toàn | Writer phù hợp cho concurrency, transaction rõ ràng |
| `JobScope` bean | State có thể được chia sẻ giữa worker steps | Chỉ dùng cho cấu hình hoặc state thread-safe |
| `static` cache/singleton | Rò rỉ trạng thái giữa partition và giữa job | Tránh state mutable không được đồng bộ |
| External API client | Rate limit, connection contention, non-idempotent call | Pool/rate limit chung, idempotency key và retry bounded |
| Aggregation table | Cùng key bị nhiều partition update | Phân vùng theo business key hoặc dùng lock/atomic update phù hợp |

### 9.1. Tách reader theo partition không giải quyết mọi race

Hai partition có reader riêng nhưng cùng xử lý một customer ID do manifest overlap vẫn có thể ghi trùng vào cùng bảng. Sự cố lúc đó là **partition boundary**, không chỉ thread safety. Hãy dùng ràng buộc duy nhất theo business key, validation của manifest và đối soát.

Nếu business logic cần cập nhật một aggregate chung, thiết kế theo khóa owner duy nhất hoặc tính partial results rồi giảm/tổng hợp sau. Một `ConcurrentHashMap` trong JVM có thể làm chương trình ít race hơn nhưng không tự giải quyết consistency khi job restart hoặc JVM crash.

## 10. Restart, retry và bảo toàn tính đúng đắn

Local partitioning có ưu thế mỗi partition sở hữu `StepExecution` và `ExecutionContext`. Khi job thất bại rồi restart đúng `JobInstance`, framework có thể dùng metadata đã lưu để xác định các partition đã hoàn tất và các partition phải chạy tiếp, **phụ thuộc cấu hình restart/step và trạng thái thực tế**.

Các bất biến cần giữ:

1. **Partition name và dữ liệu nguồn ổn định:** `partition-000` phải ứng với đúng tập input đã chốt, kể cả sau restart.
2. **Checkpoint đúng ranh giới commit:** reader state, writer transaction và metadata có ngữ nghĩa phục hồi rõ ràng.
3. **Không tiếp tục hai phiên bản cùng xử lý một partition vô ý:** một JVM cũ có thể chưa dừng khi bản mới chạy.
4. **Writer idempotent:** nếu item bị đọc lại vì crash hoặc commit/reply lệch, không sinh side effect trùng.
5. **Đối soát độc lập:** kiểm tra tập business key và giá trị nguồn/đích, không chỉ nhìn `BatchStatus.COMPLETED`.

### Tình huống lỗi thường gặp

~~~mermaid
sequenceDiagram
    participant P as Manager / PartitionStep
    participant W as Worker partition-003
    participant D as Business DB
    participant R as JobRepository
    P->>W: Chạy partition-003
    W->>D: Ghi chunk 500 item
    D-->>W: Commit
    Note over W,R: JVM lỗi trước checkpoint phù hợp
    P->>R: Restart cùng JobInstance
    R-->>P: Trạng thái checkpoint đã lưu
    P->>W: Chạy lại phần chưa xác nhận
    W->>D: Ghi lại business key đã có
    D-->>W: Idempotent/đối soát chặn trùng
~~~

Nếu business DB và `JobRepository` cùng tham gia một transaction nhất quán, rủi ro commit lệch có thể được giảm; nếu ghi sang hệ thống khác hoặc gọi API, ranh giới transaction có thể khác. Không được tuyên bố exactly-once chỉ nhờ local partitioning.

### 10.1. Viết idempotent ở đích

Với một kết quả duy nhất theo ngày và invoice:

~~~sql
CREATE TABLE invoice_result (
    business_date DATE NOT NULL,
    invoice_id BIGINT NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    calculation_version INT NOT NULL,
    PRIMARY KEY (business_date, invoice_id)
);

INSERT INTO invoice_result (
    business_date, invoice_id, amount, calculation_version
) VALUES (
    :business_date, :invoice_id, :amount, :calculation_version
)
ON CONFLICT (business_date, invoice_id) DO NOTHING;
~~~

Mẫu PostgreSQL trên giúp tránh duplicate row nhưng **không đủ** nếu bản chạy lại cho cùng invoice ID tính ra `amount` hoặc `calculation_version` khác. Khi có conflict, ứng dụng nên kiểm tra kết quả cũ có tương đương hay không; nếu không, đưa vào báo cáo sai lệch thay vì bỏ qua âm thầm.

### 10.2. Khi thay đổi partition count qua restart

Một sai lầm nghiêm trọng là dựa vào `gridSize` để tính lại dải dữ liệu sau khi job chạy lỗi: lần đầu tạo 8 partition, lần restart cấu hình thành 16 partition với **tên/phạm vi đã đổi**. Các `StepExecution` lưu trong JobRepository có thể không còn tương ứng dữ liệu ban đầu.

Giải pháp là lưu manifest bất biến theo logical batch/job, giữ partition names, source snapshot ID và ranh giới. Khi muốn repartition, phải coi đó là **một quy trình migration/replay** có kiểm chứng dữ liệu, không tự ý đổi giữa restart.

### 10.3. Các dấu hiệu phải điều tra trước khi restart

- Worker JVM cũ còn sống hoặc có job/step thực sự đang ghi.
- Snapshot nguồn không còn tồn tại hoặc đã thay đổi.
- Trạng thái `ExecutionContext` khác schema mà bản mới hiểu.
- External side effect đã commit nhưng checkpoint không đồng bộ.
- Manifest có partition mất tên, thiếu dải, overlap hoặc thay đổi thứ tự keyset.
- Có kết quả đích nhưng các count trong StepExecution chưa xác nhận.

Khi không xác định được ranh giới, cần **fencing và đối soát** trước khi replay; đừng tự tạo `run.id` mới để chạy lại toàn bộ batch.

## 11. Vận hành và quan sát local partitioning

Các metric nên gắn với **job/step/release** và có thể tổng hợp theo partition khi cần chẩn đoán. Tránh đưa business key hoặc ID có cardinality cao vào metric label.

| Metric hoặc kiểm tra | Phản ánh | Cách dùng |
|---|---|---|
| Partition count theo `COMPLETED/FAILED/STARTED` | Tiến độ thực thi | Tìm partition treo hoặc thất bại |
| `readCount`, `writeCount`, `filterCount`, skip/retry | Tình trạng từng StepExecution | Khoanh vùng dữ liệu lỗi |
| Duration / max / p95 của partition | Skew và nút thắt chậm nhất | Điều chỉnh manifest granularity |
| Active/queued executor tasks | Concurrency và queue | Phát hiện pool đầy/quá dài |
| CPU, heap, GC pause | Giới hạn JVM | Tránh overparallelization |
| JDBC active, idle, pending, lock wait | Giới hạn DB | Tối ưu SQL, pool và concurrency |
| Rows/giây và latency chunk | Throughput thực | So sánh các mức parallelism |
| Duplicate/missing/extra key | Đúng sai dữ liệu nghiệp vụ | Go/no-go độc lập với status |
| JobRepository update latency | Chi phí metadata | Giảm partition quá nhỏ/commit overhead |

### Những cảnh báo vận hành có ích

- Một partition có duration cao hơn nhiều so với các partition tương đương → **skew**.
- Executor active luôn kịch trần nhưng CPU thấp, JDBC pool pending cao → **I/O/DB contention**.
- CPU gần đầy, GC liên tục, throughput giảm khi tăng worker → **saturated JVM**.
- Một partition lỗi lặp lại cùng business key → **lỗi dữ liệu hoặc range**, không nên retry vô hạn.
- `BatchStatus.COMPLETED` nhưng output key set không khớp manifest → **lỗi nghiệp vụ** vẫn phải xử lý.

## 12. Runbook triển khai có kiểm soát

### Bước 1 — Đo baseline tuần tự

Trên một snapshot đại diện, ghi lại:

1. Tổng item, số item lọc/skip, số lượng output và checksum/tổng kiểm soát nghiệp vụ.
2. Thời gian job, throughput theo phút, latency reader/processor/writer/chunk.
3. CPU, heap, GC, I/O, JDBC active/wait, lock contention và giới hạn API.
4. Kết quả khi gây retry và restart ở phiên bản tuần tự.

Nếu truy vấn reader chiếm 80% thời gian vì full table scan, việc thêm worker nhiều khả năng khiến DB tệ hơn. Tối ưu filter, index, partition pruning và query plan trước.

### Bước 2 — Chốt partition manifest

Chọn business key ổn định, snapshot/cutoff và chiến lược chia dải. Sinh manifest, kiểm tra tổng số record, intersection/gap, dải không rỗng và skew ước lượng. Giữ manifest đủ lâu để phục vụ restart.

### Bước 3 — Cô lập state và giới hạn tài nguyên

Tạo worker step với `@StepScope` cho reader/writer stateful, kiểm tra shared services và transaction. Chọn `chunkSize` dựa trên baseline. Cấu hình `ThreadPoolTaskExecutor` với giới hạn thread/queue rõ ràng, đặt headroom cho DB connection pool và downstream.

### Bước 4 — Benchmark theo bậc

Chạy **cùng snapshot** và cùng logic nghiệp vụ theo các mức 1 → 2 → 4 → 8 worker (tùy hạ tầng). Không tự đổi chunk size, SQL và số worker cùng lúc. Thu thập speedup, resource usage, partition skew và đối soát kết quả sau mỗi lần chạy.

### Bước 5 — Kiểm tra lỗi và restart

Trên môi trường thử nghiệm, cố ý:

- Làm hỏng một partition có dữ liệu lỗi.
- Dừng JVM giữa lúc một partition đang ghi chunk.
- Cho writer commit xong rồi giả lập lỗi trước checkpoint theo thiết kế transaction phù hợp.
- Restart cùng JobInstance và kiểm tra những partition `COMPLETED` không bị xử lý lại ngoài chính sách.
- Kiểm tra output chống duplicate và đúng số record/giá trị.
- Thử một dải có nhiều record hơn các dải khác để kiểm tra tail latency.

### Bước 6 — Rollout và giữ phương án quay lại

Triển khai dần trên một nhóm job/khối dữ liệu độc lập, ghi nhãn release, `batchId`, manifest version và các chỉ số. Giữ cấu hình xử lý tuần tự hoặc concurrency thấp hơn để giảm tải khi cần; **không làm mất checkpoint/manifest** trong lúc rollback cấu hình. Chỉ tăng tải khi đạt ngưỡng đúng dữ liệu và throughput.

## 13. Tình huống thực tế: xử lý 6 triệu giao dịch

Một batch settlement đọc **6 triệu giao dịch** từ bảng snapshot cố định, mỗi giao dịch độc lập tạo một kết quả theo business key. SLA xử lý là **90 phút**.

**Baseline:** một worker hoàn thành trong 150 phút. CPU JVM chỉ sử dụng khoảng 25%, DB còn khả năng xử lý nhưng một truy vấn nguồn chậm ở vài dải ID. Nhóm tối ưu index/range query rồi thử local partitioning.

**Thiết kế:** tạo 24 partition theo manifest, mỗi partition khoảng 250.000 giao dịch trên dữ liệu snapshot. Executor có 4 thread, `chunkSize=500`, reader `@StepScope` và writer idempotent. Trong thử nghiệm dữ liệu thật, các dải không chia đều chi phí nên nhóm theo dõi duration từng partition.

| Thử nghiệm | Thời gian giả định | Kết quả |
|---|---:|---|
| Single-thread baseline | 150 phút | Không đạt SLA |
| Local, 2 worker | 89 phút | Đạt sát ngưỡng, ít headroom |
| Local, 4 worker | 55 phút | Đạt SLA với headroom |
| Local, 8 worker | 53 phút | Ít lợi ích thêm, pool DB wait tăng |

Các con số là **tình huống minh họa**. Quyết định chọn **4 worker** dựa trên tốc độ, khả năng dự phòng và database capacity; không chọn 8 worker chỉ vì nhanh hơn 2 phút.

### Khi có lỗi trong partition

Giả sử `partition-017` thất bại do một input không hợp lệ. Các partition còn lại đã commit thành công. Sau khi phân loại lỗi và sửa nguồn theo policy, hệ thống restart cùng logical job; manifest và partition name không đổi. Những phần đã hoàn tất không cần xử lý lại nếu framework và cấu hình restart xác nhận đúng trạng thái. Đối soát source snapshot với business sink để tìm thiếu/thừa/giá trị lệch trước khi công bố kết quả.

### Khi nào chuyển sang remote?

Sáu tháng sau, dữ liệu tăng gấp 5 lần; node hiện tại đã gần hết CPU/heap trong khi DB và các service downstream còn capacity. Benchmark cho thấy tăng thread trong một JVM không cải thiện được. Khi đó có lý do để thử **remote partitioning** với nhiều worker JVM, giữ lại manifest và idempotency contract đang có, đồng thời bổ sung transport, ownership, retry và observability phân tán. Nếu downstream đã bão hòa, chuyển remote vẫn chưa giải quyết được vấn đề gốc.

## 14. Chọn phương án khác khi local partitioning không phù hợp

| Tín hiệu thực tế | Hướng thay thế đáng thử | Lý do |
|---|---|---|
| Job nhỏ, overhead partition chiếm đáng kể | Sequential step | Ít chi phí quản lý, dễ vận hành |
| Chia input khó, nhưng chunks có thể xử lý song song an toàn | Multi-threaded step | Không cần tự thiết kế manifest nhiều partition |
| Có nhiều nhánh công việc độc lập | Parallel steps | Song song theo nghiệp vụ thay vì chia một step |
| Worker CPU-bound, một node hết CPU/heap | Remote partitioning | Scale ngang trên nhiều JVM/nút |
| Reader tập trung nhưng processor/writer tốn thời gian ở nơi khác | Remote chunking | Đẩy phần xử lý chunk tới worker remote |
| DB I/O, locks, SQL là nút thắt | Index, query optimization, caching hợp lệ, batching | Tăng worker có thể làm DB quá tải |
| Tác vụ yêu cầu thứ tự toàn cục nghiêm ngặt | Sequential hoặc thiết kế lại theo owner key | Partition độc lập không giữ được total order |
| External API giới hạn QPS nghiêm | Global rate limiter, workload scheduling | Thêm partition có thể làm nhiều lỗi 429 hơn |
| Khó đảm bảo nguồn immutable và restart chính xác | Snapshot/manifest trước, rồi mới scale | Correctness là điều kiện trước khi tăng tốc |

## 15. Những anti-pattern dễ gặp

**1. `gridSize=100` nên mặc định sẽ có 100 thread.** Sai: partitioner có thể tạo ít hoặc nhiều partition hơn gợi ý; executor quyết định concurrency.

**2. Chia range theo min/max nhưng không kiểm tra mật độ record.** Một dải có phần lớn dữ liệu làm job kết thúc theo partition chậm nhất.

**3. Dùng reader singleton có cursor mutable cho mọi partition.** Dễ gây race và checkpoint lỗi; dùng step-scoped reader với bounds cụ thể.

**4. Thay partition names/ranges khi restart để “cân bằng lại”.** StepExecution/ExecutionContext cũ có thể không còn khớp đầu vào; phải có kế hoạch migration có kiểm chứng.

**5. Tăng worker vì CPU đang thấp dù JDBC pool chờ cao.** Trường hợp này có thể đang nghẽn DB; tăng thread chỉ tăng contention.

**6. Tăng chunk size quá lớn để giảm commit.** Có thể tăng heap, transaction duration và retry cost.

**7. Gộp bộ đếm của manager và mọi worker như số record nghiệp vụ.** Metadata có thể gồm nhiều execution và retry; đối soát phải theo business key tại sink.

**8. Cho rằng mỗi partition tự có đúng một writer an toàn.** Khi overlap input hoặc external side effect không idempotent, cùng record có thể bị ghi nhiều lần.

**9. Chỉ theo dõi job status = COMPLETED.** Cần kiểm chứng input/output count, key set và quy tắc nghiệp vụ, nhất là sau restart.

**10. Mở quá nhiều partition mà không giới hạn queue và pool.** Làm tăng metadata, memory, backpressure và thời gian dừng.

## 16. Checklist ra quyết định

Trước khi chọn local partitioning:

- [ ] Đã đo bottleneck của job tuần tự trên snapshot và workload đại diện.
- [ ] Business item có thể chia độc lập; đã mô tả bất biến coverage và no-overlap.
- [ ] Có business key ổn định, snapshot/cutoff hoặc manifest có thể khôi phục.
- [ ] Có lý do rõ ràng để cần `StepExecution` và checkpoint theo partition.
- [ ] JVM còn CPU/heap/I/O phù hợp, database và API downstream còn headroom.
- [ ] Đã chọn số partition logic khác với giới hạn worker đồng thời.
- [ ] Reader/writer stateful được scope theo step; các singleton còn lại đã được kiểm tra thread safety.
- [ ] Pool, chunk size, executor queue và giới hạn external QPS được cấu hình rõ.
- [ ] Writer idempotent hoặc có cơ chế xử lý replay/compensation tương đương.
- [ ] Đã kiểm thử restart cùng JobInstance, partition names/bounds ổn định và xử lý lỗi.
- [ ] Đã đối soát source/output theo key, count và value dưới concurrency.
- [ ] Benchmark chứng minh throughput tăng và resource usage còn trong ngưỡng an toàn.
- [ ] Có số liệu phân biệt CPU saturation, DB contention, GC và partition skew.
- [ ] Có kế hoạch rollback concurrency hoặc chuyển hướng khi một node chạm giới hạn.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `gridSize=24` và executor có 4 thread. Có bao nhiêu partition chạy đồng thời?

*Gợi ý:* Tùy số partition thực tế và giới hạn executor; với 24 partition được tạo ra và pool chỉ có 4 thread phục vụ task, thường tối đa khoảng 4 partition worker chạy cùng lúc. `gridSize` không buộc 24 thread.

**Câu 2.** Vì sao `@StepScope` đặc biệt hữu ích cho reader trong local partitioning?

*Gợi ý:* Mỗi `StepExecution` có context khác nhau và reader state riêng; tránh dùng chung cursor, state checkpoint hoặc tham số range.

**Câu 3.** Vì sao chia đều dải ID chưa chắc tối ưu?

*Gợi ý:* ID space có thể thưa/dày không đồng đều, và chi phí xử lý từng record có thể khác nhau. Tổng thời gian phụ thuộc partition chậm nhất.

**Câu 4.** Job tăng từ 4 lên 8 worker nhưng throughput gần như không đổi, JDBC pool pending tăng. Có nên tăng tiếp?

*Gợi ý:* Không đủ cơ sở. Cần kiểm tra database, SQL/locks, connection pool và giới hạn I/O; tăng concurrency có thể gây chậm hơn.

**Câu 5.** Partition đã commit 500 invoice nhưng JVM crash trước checkpoint tương ứng. Khi restart cần điều gì?

*Gợi ý:* Writer idempotent theo business key, ranh giới transaction rõ và đối soát kết quả; không giả định checkpoint phản ánh mọi side effect.

**Câu 6.** Khi nào remote partitioning phù hợp hơn local partitioning?

*Gợi ý:* Khi dữ liệu đã chia độc lập và một JVM/nút chạm giới hạn thực, còn downstream vẫn có capacity; chấp nhận thêm độ phức tạp của phân phối, messaging và vận hành.

## Kết luận

Local partitioning là lựa chọn tốt khi **một loại công việc có thể chia thành nhiều tập dữ liệu độc lập**, **một JVM vẫn đủ tài nguyên để xử lý đồng thời** và hệ thống cần **trạng thái/checkpoint riêng theo partition** để quản lý retry/restart. Hiệu năng đến từ phân vùng đúng, StepScope đúng, concurrency có giới hạn, truy vấn hiệu quả và writer an toàn; không đến từ việc tăng `gridSize` vô hạn. Hãy chốt snapshot và manifest, đo baseline, thử nhiều mức worker và đối soát theo business key. Nếu bottleneck nằm ở database hoặc dependency có thứ tự, giải quyết nút thắt đó trước; nếu một node đã hết năng lực trong khi downstream còn dư, lúc ấy mới có lý do kỹ thuật rõ ràng để đánh giá remote partitioning.

# Worker logging theo partition name trong Spring Batch

## Mục tiêu bài học

Khi Spring Batch mở rộng một job thành hàng chục hoặc hàng trăm partition, các worker chạy đồng thời có thể ghi log xen kẽ trên một JVM, nhiều JVM hoặc nhiều pod. Nếu log chỉ nói “worker failed” hoặc “chunk took 12 seconds”, người trực vận hành không biết **phần dữ liệu nào**, **lần thực thi nào**, **worker instance nào** và **giai đoạn nào** đã gây lỗi.

**Worker logging theo partition name** là cách đưa tên phần việc logic do `Partitioner` tạo ra vào các sự kiện log quan trọng của worker, rồi liên kết nó với JobRepository, transaction, message correlation, metrics và tracing. Partition name giúp tìm cùng một phần việc qua nhiều thread và lần khôi phục, nhưng không thay thế được JobExecution/StepExecution ID hoặc business key.

Bài thuộc chương **Thiết kế worker** của module **SPRING_BATCH_SCALING_OPERATIONS**: mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán, đồng thời bảo đảm thread safety, retry/restart, đo bottleneck và vận hành theo tài nguyên thực tế.

Học xong, bạn có thể:

- Định nghĩa tên partition **deterministic**, không tiết lộ dữ liệu nhạy cảm.
- Phân biệt `partitionName`, `stepName`, `stepExecutionId`, `jobExecutionId`, worker instance, correlation ID và business event ID.
- Đưa `partitionName` vào `ExecutionContext` để worker ghi log mà không phải đoán từ tên thread.
- Dùng SLF4J MDC trong **đúng thread và đúng phạm vi**, tránh rò MDC khi thread pool tái sử dụng thread.
- Thêm `StepExecutionListener`, `ChunkListener` và cấu hình logging để theo dõi start, progress, retry, failure, finish.
- Hiểu giới hạn MDC qua `TaskExecutor`, async callback và remote worker JVM.
- Tổ chức structured logs, log retention, privacy và metric cardinality.
- Viết test về context isolation, retry, restart, crash, message redelivery và case study hiệu năng.

## 1. Vì sao phải log theo partition?

Giả sử manager chia dữ liệu giao dịch thành các khoảng:

| Partition | Từ ID (bao gồm) | Đến ID (loại trừ) |
| --- | ---: | ---: |
| `range-0000` | 1 | 250001 |
| `range-0001` | 250001 | 500001 |
| `range-0002` | 500001 | 750001 |
| `range-0003` | 750001 | 1000001 |

Nếu bốn worker cùng ghi:

~~~text
INFO  Started worker
WARN  Retrying database timeout
ERROR Step failed
~~~

ta không biết partition nào đang lỗi. Khi một thread pool thực thi partition A rồi B, log của chúng còn có thể bị xen nhau.

Một log có ngữ cảnh:

~~~text
INFO  event=partition_started jobExecutionId=8100
      stepExecutionId=8142 partitionName=range-0002
      workerInstance=worker-jvm-03 from=500001 to=750001

WARN  event=chunk_retry jobExecutionId=8100
      stepExecutionId=8142 partitionName=range-0002
      retryAttempt=2 errorCategory=DB_TIMEOUT

ERROR event=partition_failed jobExecutionId=8100
      stepExecutionId=8142 partitionName=range-0002
      status=FAILED
~~~

Các ID chỉ minh họa. Log theo partition name phải trả lời được ba câu: **phần việc nào**, **lần thực thi nào**, **trạng thái và nguyên nhân gì**. Một tên partition đứng riêng chưa đủ.

## 2. Phân biệt danh tính logic và danh tính thực thi

| Trường | Vai trò | Tính ổn định |
| --- | --- | --- |
| `jobName` | Tên định nghĩa job | Thường không đổi giữa các lần chạy |
| JobInstance | Công việc logic, được nhận dạng bằng job và identifying JobParameters | Xuyên các lần restart cùng instance |
| `jobExecutionId` | Một lần thực thi JobInstance | Có thể khác khi restart |
| `managerStepName` | Tên step điều phối | Theo cấu hình |
| `workerStepName` / `stepName` | Tên StepExecution thực tế | Có thể được framework bổ sung suffix partition |
| **`partitionName`** | Tên logic của một phạm vi input | Nên ổn định trong cùng công việc |
| `stepExecutionId` | ID StepExecution trong JobRepository | Thuộc một execution cụ thể |
| `workerInstance` | Tên JVM/pod/container đang chạy | Có thể thay khi recovery |
| `threadName` | Tên thread hiện tại | Có thể tái sử dụng cho partition khác |
| `correlationId` | Ghép request/reply qua middleware | Theo một request hoặc conversation |
| `businessEventId` | ID side effect nghiệp vụ | Phục vụ dedupe/đối soát |

Hai lần chạy có thể cùng `partitionName=range-0002` nhưng khác `jobExecutionId`, `stepExecutionId` và worker instance.

~~~text
JobInstance daily-import/2026-11-25
  JobExecution 8100 (FAILED)
    StepExecution 8142
      partitionName=range-0002, worker=worker-a

JobInstance daily-import/2026-11-25 (restart)
  JobExecution 8125 (COMPLETED)
    StepExecution 8221
      partitionName=range-0002, worker=worker-b
~~~

Đây là timeline khái niệm; cách StepExecution được tạo lại phụ thuộc cơ chế restart/framework. Khi tra log một partition, dùng **tập định danh ghép** thay vì chỉ một tên.

## 3. Quy tắc đặt partition name dễ truy vấn

Partition name tốt phải:

1. **Deterministic:** cùng input và thuật toán chia tạo cùng tên.
2. **Duy nhất trong một lần partition:** không hai phần việc cùng key Map.
3. **Ổn định qua restart:** không lấy `UUID.randomUUID()` hoặc `System.currentTimeMillis()`.
4. **Có cấu trúc:** tên ngắn, dễ tìm và không phụ thuộc host.
5. **Không chứa dữ liệu bí mật/PII:** tránh email, số thẻ, token, raw account IDs nếu chính sách bảo mật không cho phép.
6. **Không mã hóa state không cần thiết:** input range đã được lưu trong ExecutionContext.
7. **Có version/cutoff rõ:** nếu đổi thuật toán chia phải xem lại restart compatibility.

Ví dụ:

~~~text
range-0000
range-0001
time-20261125-00
time-20261125-01
tenant-shard-0007
source-slice-0012
~~~

Không nên đặt tên theo worker pod vì partition có thể di chuyển sau lỗi. Cũng không nên dùng duy nhất `partition-0` để so sánh log của **các JobInstance khác nhau**.

Nếu nghiệp vụ chia theo ngày địa phương, phải biết timezone và DST khi tạo range, không dùng tên ngày để suy ra giới hạn UTC thiếu căn cứ.

## 4. Partition name được Spring Batch sinh ở đâu?

Một `Partitioner` trả về `Map<String, ExecutionContext>`: key là tên partition logic, value là input riêng của partition. Manager tạo và quản lý worker StepExecutions từ các phần việc đó, rồi dùng PartitionHandler dispatch local hoặc remote.

~~~mermaid
flowchart TB
    M["Manager Step"] --> P["Partitioner"]
    P --> A["range-0000 → ExecutionContext A"]
    P --> B["range-0001 → ExecutionContext B"]
    P --> C["range-0002 → ExecutionContext C"]
    A --> WA["Worker StepExecution A"]
    B --> WB["Worker StepExecution B"]
    C --> WC["Worker StepExecution C"]
    WA --> L[["Structured logs"]]
    WB --> L
    WC --> L
~~~

Framework thường có một quy tắc đặt tên worker StepExecution từ worker step và partition name, ví dụ dạng `workerStep:partitionName`. Tuy nhiên **không nên parse chuỗi tên step bằng dấu hai chấm làm nguồn nhận dạng duy nhất**, vì naming có thể thay đổi/tùy biến.

Để worker logging rõ ràng, ứng dụng có thể tự **ghi cùng partitionName vào ExecutionContext**. Đây là quy ước do ứng dụng thiết kế; không mặc nhiên là trường mà Spring Batch chèn sẵn trong mọi ExecutionContext.

## 5. Ví dụ Java: Partitioner mang tên và input range

Ví dụ Java 17, Spring Batch 5.x; các time windows được xác định theo UTC và dùng cận trên loại trừ.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class UtcWindowPartitioner implements Partitioner {

    private final Instant start;
    private final Instant end;
    private final Duration width;

    public UtcWindowPartitioner(
            Instant start, Instant end, Duration width) {
        if (!start.isBefore(end)) {
            throw new IllegalArgumentException("Empty interval");
        }
        if (width.isZero() || width.isNegative()) {
            throw new IllegalArgumentException("Invalid width");
        }
        this.start = start;
        this.end = end;
        this.width = width;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> partitions =
                new LinkedHashMap<>();

        int index = 0;
        for (Instant from = start;
             from.isBefore(end);
             from = from.plus(width)) {

            Instant next = from.plus(width);
            Instant to = next.isBefore(end) ? next : end;

            String partitionName = String.format(
                    Locale.ROOT, "time-%04d", index++);

            ExecutionContext context = new ExecutionContext();
            context.putString("partitionName", partitionName);
            context.putString("fromInclusive", from.toString());
            context.putString("toExclusive", to.toString());
            partitions.put(partitionName, context);
        }

        return partitions;
    }
}
~~~

**Điểm quan trọng:**

- Map key và `ExecutionContext.partitionName` có cùng giá trị.
- Reader và log có thể dùng chung hai cận `[fromInclusive,toExclusive)`.
- `gridSize` được framework truyền vào nhưng ví dụ cố ý không dùng để quyết định range: số partition phụ thuộc thời lượng và width. `gridSize(8)` **không tự bảo đảm đúng tám partition**.
- `start`, `end`, `width` phải ổn định cho JobInstance/công việc logic. Đừng tự lấy `Instant.now()` mỗi lần restart.
- Production cần validate số partition tối đa và nguy cơ `Instant.plus` vượt phạm vi khi input quá lớn.

Tên `time-0002` không được dùng một mình để chứng minh input không đổi. Cần xem cả JobParameters/cutoff và `fromInclusive`/`toExclusive` thực tế.

## 6. ExecutionContext khác log và metric

`ExecutionContext` chứa input partition và state checkpoint cần thiết cho Spring Batch. Ví dụ:

~~~text
partitionName = time-0002
fromInclusive = 2026-11-25T12:00:00Z
toExclusive   = 2026-11-25T18:00:00Z
sourceShard   = 3
~~~

Nó **không phải nơi lưu log history**. Tránh ghi vào ExecutionContext hàng triệu message, payload item, toàn bộ stack trace, thông tin nhạy cảm hoặc số liệu có thể được tạo lại từ metric.

| Thành phần | Trách nhiệm |
| --- | --- |
| ExecutionContext | Input và checkpoint/restart state |
| JobRepository | JobExecution/StepExecution và trạng thái |
| Structured logs | Timeline điều tra lỗi, latency, retry |
| Metrics | Throughput, duration, queue age, pool wait |
| Tracing | Liên kết hành trình request xuyên service |
| Business DB/ledger | Kết quả thực, idempotency và đối soát |

Một log `partition_finished` **không thay thế** trạng thái được lưu trong JobRepository. Nếu JVM chết, không có gì đảm bảo log cuối đã được ghi.

## 7. Thiết kế schema structured logs

Nên thống nhất **tên trường, định dạng và ngữ nghĩa** trước khi nhiều worker cùng ghi log.

| Field | Nội dung |
| --- | --- |
| `timestamp` | ISO-8601 với UTC/offset |
| `level` | INFO/WARN/ERROR/DEBUG |
| `service` | Batch worker service |
| `jobName` | Tên job |
| `jobExecutionId` | Lần chạy job |
| `stepName` | Tên StepExecution thực tế |
| `stepExecutionId` | ID execution |
| **`partitionName`** | Identity logic của partition |
| `workerInstance` | Process/pod/host xử lý |
| `event` | Mã sự kiện ổn định |
| `rangeStart`, `rangeEndExclusive` | Input đã chốt |
| `readCount`, `writeCount`, `commitCount` | Batch counters khi thích hợp |
| `rollbackCount`, `retryAttempt` | Fault/recovery |
| `correlationId` | Message request/reply ID nếu có |
| `elapsedMs` | Thời gian giai đoạn |
| `errorCategory` | Mã lỗi chuẩn hóa |

Ví dụ JSON:

~~~json
{
  "timestamp": "2026-11-26T02:12:03.521Z",
  "level": "INFO",
  "service": "batch-worker",
  "jobName": "normalizeOrdersJob",
  "jobExecutionId": 8100,
  "stepName": "normalizeWorkerStep:time-0002",
  "stepExecutionId": 8142,
  "partitionName": "time-0002",
  "workerInstance": "worker-jvm-03",
  "event": "partition_started",
  "rangeStart": "2026-11-25T12:00:00Z",
  "rangeEndExclusive": "2026-11-25T18:00:00Z"
}
~~~

Đây là schema của **ứng dụng**, không phải message Spring Batch tự động tạo. `event` giúp alert và truy vấn ổn định dù câu mô tả tự do thay đổi.

## 8. Vì sao không nên parse tên step?

Anti-pattern:

~~~java
String partitionName =
        stepExecution.getStepName().split(":")[1];
~~~

Cách này giả định mọi worker StepExecution name đều có đúng một dấu `:` và partition name luôn đứng sau nó.

Các tình huống có thể gây lỗi: đổi quy ước đặt tên, tên có thêm dấu phân cách, custom `StepExecutionSplitter`, unit test worker step độc lập hoặc một step không có partition nhưng tên tương tự.

**Tốt hơn:** ứng dụng khai báo key `partitionName` trong ExecutionContext, validate ở đầu worker step, và **log thêm stepName thực tế** để đối chiếu metadata framework.

Nếu dự án có contract tên step riêng, hãy tài liệu hóa nó và kiểm thử khi nâng cấp; tránh có hai nguồn identity mâu thuẫn mà không phát hiện.

## 9. SLF4J MDC: đưa metadata vào log theo thread

**Mapped Diagnostic Context (MDC)** hỗ trợ đính các cặp key–value vào log event. Trong các logging backend thường dùng, MDC gắn với **ngữ cảnh thread**.

~~~java
MDC.put("partitionName", "time-0002");
log.info("event=reader_started");
MDC.remove("partitionName");
~~~

Nhờ formatter/JSON encoder tương ứng, các log từ reader, processor và writer trên cùng thread có thể chứa `partitionName` mà không cần thêm tham số ở mỗi dòng.

**Nhưng thread pool tái sử dụng thread.** Nếu worker A đặt MDC rồi quên dọn, worker B chạy sau trên cùng thread có thể log sai thành A.

### MDC tuyệt đối không phải nguồn sự thật nghiệp vụ

- MDC không phải checkpoint.
- MDC không tự lưu vào JobRepository.
- MDC không tự lan tới mọi async task.
- MDC không tự vượt broker/JVM.
- MDC không quyết định transaction đã commit.
- MDC không thay thế idempotency key hoặc xác thực input.

Chỉ coi MDC là **bản sao tạm của context đáng tin cậy** trong một ranh giới thực thi cụ thể.

## 10. Java: StepExecutionListener gắn và dọn MDC

Listener sau dành cho worker step **có partitionName trong ExecutionContext**. Nó không giữ current partition trong field singleton.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public final class PartitionLoggingListener
        implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionLoggingListener.class);

    @Override
    public void beforeStep(StepExecution execution) {
        clearContext();

        try {
            String partitionName = execution
                    .getExecutionContext()
                    .getString("partitionName", "");

            if (partitionName.isBlank()) {
                throw new IllegalStateException(
                        "Missing partitionName");
            }

            MDC.put("partitionName", partitionName);
            MDC.put("jobExecutionId", String.valueOf(
                    execution.getJobExecution().getId()));
            MDC.put("stepExecutionId", String.valueOf(
                    execution.getId()));
            MDC.put("stepName", execution.getStepName());

            log.info(
                "event=partition_started status={} from={} to={}",
                execution.getStatus(),
                execution.getExecutionContext()
                        .getString("fromInclusive", "n/a"),
                execution.getExecutionContext()
                        .getString("toExclusive", "n/a"));

        } catch (RuntimeException ex) {
            clearContext();
            throw ex;
        }
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        try {
            log.info(
                "event=partition_finished status={} readCount={} " +
                "writeCount={} commitCount={} rollbackCount={}",
                execution.getStatus(),
                execution.getReadCount(),
                execution.getWriteCount(),
                execution.getCommitCount(),
                execution.getRollbackCount());
            return null; // Không thay đổi ExitStatus.
        } finally {
            clearContext();
        }
    }

    private void clearContext() {
        MDC.remove("partitionName");
        MDC.remove("jobExecutionId");
        MDC.remove("stepExecutionId");
        MDC.remove("stepName");
    }
}
~~~

### Vì sao không lưu identity vào field của listener?

Nhiều StepExecutions có thể chạy đồng thời trong một ApplicationContext. Nếu listener có `private String currentPartitionName`, worker B có thể ghi đè tên của worker A giữa lúc A đang log.

Ở ví dụ này, listener là **stateless singleton**; identity của từng lần gọi nằm ở `StepExecution` và MDC của đúng thread.

### Ranh giới an toàn

Mẫu này thích hợp với **worker step thực thi tuần tự trên một thread**. Trong multi-threaded chunks hoặc callback bất đồng bộ, `beforeStep` không tự gắn context vào mọi thread con. Việc `afterStep` dọn MDC cũng không thể diễn ra khi JVM bị kill đột ngột. Cần thiết kế propagation tại **thread thật sự thực thi** và đối soát trạng thái qua JobRepository.

Nếu listener được gắn vào manager step không có `partitionName`, nó sẽ báo lỗi có chủ đích. Chỉ đăng ký với worker step có hợp đồng dữ liệu đó.

## 11. Đăng ký listener vào worker Step

Ví dụ Spring Batch 5.x:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step normalizeWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemWriter<OrderRow> writer,
        PartitionLoggingListener listener) {

    return new StepBuilder(
            "normalizeWorkerStep", jobRepository)
            .<OrderRow, OrderRow>chunk(500, transactionManager)
            .reader(reader)
            .writer(writer)
            .listener(listener)
            .build();
}
~~~

`OrderRow` và reader/writer là các thành phần của ứng dụng, chưa được khai báo trong đoạn ví dụ. Bean cần nằm trong lớp cấu hình hợp lệ; đây là mẫu kiến trúc, không phải dự án standalone đã build.

Một `ItemProcessor` có thể nhận tên partition qua `@StepScope`:

~~~java
@Bean
@StepScope
public ItemProcessor<OrderRow, OrderRow> normalizeProcessor(
        @Value("#{stepExecutionContext['partitionName']}")
                String partitionName) {

    return row -> {
        log.debug(
                "event=normalize_item partitionName={} itemId={}",
                partitionName, row.id());
        return row;
    };
}
~~~

Cần import `ItemProcessor`, `@StepScope`, `@Value` và logger ở cấu hình thật. **Đừng bật DEBUG cho mọi item ở production** khi có hàng chục triệu record. Việc truyền `partitionName` trực tiếp như tham số có thể hữu ích cho async code khi MDC không được propagate.

## 12. Logback formatter phải render MDC

Nếu đã đặt MDC nhưng formatter không xuất các trường, log vẫn không có partition name. Ví dụ `logback-spring.xml`:

~~~xml
<configuration>
  <appender name="CONSOLE"
            class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX}
      %-5level [%thread] %logger{36}
      jobExec=%X{jobExecutionId:-none}
      stepExec=%X{stepExecutionId:-none}
      partition=%X{partitionName:-none}
      - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

Cấu hình minh họa: production có thể chỉnh pattern thành một dòng và xác minh cú pháp của backend thực. Nếu hệ thống dùng structured JSON encoder, hãy map MDC thành JSON fields thay vì tự tạo chuỗi JSON bằng nối text không escape.

**Kiểm thử cả stdout thật**: việc `MDC.get("partitionName")` trả đúng giá trị chỉ chứng minh context nội bộ, không chứng minh log collector đã nhận đúng trường.

## 13. Mốc log quan trọng trong vòng đời partition

| Event | Mức thường dùng | Nội dung |
| --- | --- | --- |
| `partition_started` | INFO | Job/step IDs, name, range, worker instance |
| `reader_opened` | DEBUG hoặc INFO có chọn lọc | Loại reader, source/range |
| `chunk_completed` | DEBUG/metric | Chunk size, latency |
| `chunk_retry` | WARN có rate limit | Loại lỗi, attempt, backoff |
| `partition_progress` | INFO theo chu kỳ | Read/write counts, elapsed |
| `partition_failed` | ERROR | Exception, phase, rollback/status |
| `partition_finished` | INFO | BatchStatus, read/write/commit/rollback |
| `partition_restarted` | INFO | Execution mới và range được giữ ổn định |
| `worker_shutdown` | INFO/WARN | Drain/inflight/chunk đang dở |

Đừng coi một dòng `readCount=50000` là checkpoint thực. Nếu JobRepository mới commit position 49500, job có thể đọc lại phần chưa commit sau restart. Log là công cụ điều tra, **không phải cơ chế resume**.

## 14. ChunkListener cho progress mà không log từng item

Một `ChunkListener` có thể lấy trực tiếp `StepExecution` từ `ChunkContext`, không cần phụ thuộc MDC của thread khác.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.ChunkContext;

public final class PartitionProgressListener
        implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionProgressListener.class);

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution step = context.getStepContext()
                .getStepExecution();

        // Giảm tần suất thay vì INFO mỗi item/chunk.
        if (step.getCommitCount() % 100 == 0) {
            log.info(
                "event=partition_progress partitionName={} " +
                "stepExecutionId={} readCount={} writeCount={} " +
                "commitCount={} rollbackCount={}",
                step.getExecutionContext()
                        .getString("partitionName", "unknown"),
                step.getId(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getCommitCount(),
                step.getRollbackCount());
        }
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        StepExecution step = context.getStepContext()
                .getStepExecution();

        log.warn(
            "event=chunk_error partitionName={} stepExecutionId={}",
            step.getExecutionContext()
                    .getString("partitionName", "unknown"),
            step.getId());
    }
}
~~~

### Giới hạn cần hiểu

- Các callback trong Spring Batch 5.x cần được gắn vào worker step và kiểm thử với topology thật.
- `afterChunk` thường diễn ra sau khi chunk transaction được hoàn tất, nhưng **không chứng minh các side effect HTTP ngoài transaction đã commit**.
- `afterChunkError` có thể xảy ra dù retry sau đó thành công; không log nó như lỗi cuối cùng của StepExecution.
- `commitCount` là bộ đếm step; điều kiện modulo chỉ là **sampling đơn giản**, không bảo đảm nhịp thời gian.
- Với multi-threaded chunks, callback và counters có thể xen kẽ. Log theo execution identity và tránh dựa vào thứ tự dòng tuyệt đối.

## 15. TaskExecutor và vấn đề MDC không tự propagate

MDC thường gắn với thread đang chạy. Khi manager gọi `TaskExecutor.execute`, không có bảo đảm chung rằng context của manager tự xuất hiện đúng trên worker thread.

Một mẫu `TaskDecorator` có thể copy snapshot MDC từ **thread submit** sang task thread, rồi khôi phục giá trị trước đó trong `finally`:

~~~java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcCopyTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable delegate) {
        Map<String, String> captured =
                MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous =
                    MDC.getCopyOfContextMap();

            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }

                delegate.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Ví dụ gắn vào executor:

~~~java
@Bean
public ThreadPoolTaskExecutor workerExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(16);
    executor.setTaskDecorator(new MdcCopyTaskDecorator());
    executor.setThreadNamePrefix("batch-worker-");
    executor.initialize();
    return executor;
}
~~~

**Cảnh báo cốt lõi:** TaskDecorator **chỉ copy context đang có ở thread submit**; nếu manager thread không mang partitionName của partition A thì decorator **không thể tự suy ra A**. Phải thiết lập identity tại boundary có StepExecution thật hoặc truyền metadata khi submit task.

Cách này cũng không tự giải quyết `CompletableFuture` dùng executor khác, callback HTTP, scheduler/reactive execution hay thread do thư viện bên ngoài tạo. Với các trường hợp đó, cần cơ chế propagation riêng và kiểm thử thread reuse.

## 16. Listener singleton giữ currentPartitionName là race condition

Ví dụ không an toàn:

~~~java
@Component
public class UnsafePartitionListener
        implements StepExecutionListener {

    private String currentPartitionName;

    @Override
    public void beforeStep(StepExecution step) {
        currentPartitionName = step.getExecutionContext()
                .getString("partitionName");
    }

    public void log() {
        logger.info("partition={}", currentPartitionName);
    }
}
~~~

Hai StepExecutions A và B chạy đồng thời:

~~~text
A.beforeStep → currentPartitionName=A
B.beforeStep → currentPartitionName=B
A.log        → in sai partition=B
~~~

Đây là race do **shared mutable state**, không được sửa bằng tăng pool DB hoặc đổi thread name. Nên lấy identity từ `StepExecution` tại mỗi callback, dùng MDC đúng thread với cleanup, hoặc cô lập object theo phạm vi thật sự phù hợp concurrency.

`@StepScope` là scope theo **StepExecution**, không tự tạo instance riêng cho từng chunk thread trong một multi-threaded step.

## 17. Remote partitioning: tái tạo log context ở worker JVM

Trong **remote partitioning**, manager tạo các worker StepExecutions và gửi yêu cầu qua middleware; worker JVM nhận request, dùng thông tin thực thi và JobRepository để chạy worker step.

~~~mermaid
sequenceDiagram
    participant M as Manager JVM
    participant J as JobRepository
    participant Q as Request broker
    participant W as Worker JVM
    participant L as Log collector

    M->>J: Tạo StepExecution + ExecutionContext
    M->>Q: Dispatch partition request
    Q->>W: Giao yêu cầu
    W->>J: Truy xuất StepExecution/context
    J-->>W: partitionName, range, execution IDs
    W->>W: beforeStep → bind MDC
    W->>L: partition_started/progress/error
    W->>J: Checkpoint/status
    W->>W: afterStep → cleanup MDC
    W-->>M: Reply/status theo protocol
~~~

MDC từ manager **không tự đi qua broker**. Worker nên lấy identity từ StepExecution và ExecutionContext đáng tin cậy theo giao thức của Spring Batch Integration, sau đó gắn nó vào log ở ranh giới thực thi.

### Vì sao vẫn cần workerInstance?

Một partition có thể chạy ở `worker-a`, rồi được phục hồi ở `worker-b`. Các trường mang ý nghĩa khác nhau:

~~~text
partitionName  = time-0002  # Phần việc logic
jobExecutionId = 8100       # Lần chạy job
stepExecutionId= 8142       # Step execution
workerInstance = worker-a   # Process thực thi
~~~

Khi worker thay đổi, **partitionName không được tự đổi theo hostname**. Log từ nhiều instance cần được nối bằng partition identity cùng execution metadata.

### Message header do ứng dụng mang theo

Nếu có custom header `batchPartitionName` để làm tracing, coi đó là **bản sao phục vụ quan sát**, không phải nguồn cấp quyền truy cập dữ liệu. Worker có thể xác minh header trùng với `ExecutionContext.partitionName`; nếu không khớp, báo lỗi/cảnh báo theo contract.

Không để một header chưa được xác thực quyết định worker được đọc range/tenant nào. Phạm vi đọc phải dựa trên metadata và quyền của ứng dụng.

## 18. Remote chunking: đừng tự tạo partition name giả

**Remote chunking** khác **remote partitioning**. Manager remote chunking thường đọc item và gửi các chunk đến worker để process/write. Worker không mặc nhiên có một worker StepExecution partition cho từng chunk.

Vì vậy không nên thêm `partitionName=partition-0000` vào mọi log nếu giao thức không tồn tại logical partition tương ứng.

Một schema tốt cho remote chunking thường ưu tiên:

| Field | Vai trò |
| --- | --- |
| `managerJobExecutionId` | Execution manager gửi chunk |
| `managerStepExecutionId` | Step manager đọc/chia chunk |
| `chunkCorrelationId` | Request–reply identity theo protocol |
| `logicalWorkId` | Work unit application-defined nếu có |
| `attempt` | Lượt thử theo tầng được định nghĩa |
| `workerInstance` | JVM nhận và xử lý chunk |
| `event` | Received, processing, committed, reply failed... |

Nếu kiến trúc chủ động gắn mỗi chunk với một business shard/time window, có thể log custom `partitionName` **theo hợp đồng của ứng dụng**, nhưng phải giải thích đó là business partition, không đánh đồng với StepExecution partition.

### Tại sao phân biệt lại quan trọng?

Nếu khi điều tra một chunk bị gửi lại, dashboard hiển thị partition name không có thật, người vận hành dễ đi tìm StepExecution không tồn tại. Cần định danh đúng **đơn vị phần việc của mô hình** trước khi xây logger.

## 19. Correlation header không phải partition identity

Trong Spring Integration và middleware, có thể xuất hiện:

- `correlationId`: dùng để ghép request–reply hoặc một group message, tùy component.
- `sequenceNumber`/`sequenceSize`: vị trí và số lượng phần tử của splitter/aggregator group.
- `replyChannel` hoặc broker reply-to: đường nhận reply.
- `MessageHeaders.ID`: danh tính message envelope.
- `traceId`: nối các span quan sát qua service.

Trong khi đó, **partitionName** đại diện phạm vi dữ liệu logic. Một partition có thể liên quan nhiều request/attempt khi có recovery; các correlation IDs không bắt buộc giống tên partition.

~~~text
partitionName  = time-0002

Attempt/execution đầu:
  jobExecutionId  = 8100
  stepExecutionId = 8142
  correlationId   = req-8100-8142-1

Lần thực thi phục hồi:
  jobExecutionId  = 8125
  stepExecutionId = 8221
  correlationId   = req-8125-8221-1
~~~

Đây là ví dụ định danh do ứng dụng giả định, không phải format wire bắt buộc của Spring Batch Integration.

### Không ghi đè header framework

Nếu messaging gateway/remote partitioning handler sở hữu `correlationId` để ghép reply, ứng dụng không nên thay bằng partitionName rồi coi request/reply vẫn hoạt động. Có thể thêm **application header** riêng, nhưng phải kiểm tra mapper/converter khi message qua RabbitMQ/Kafka.

Header mapping test phải chứng minh:

1. Giá trị tồn tại ở worker sau serialization.
2. Kiểu dữ liệu/encoding được bảo toàn.
3. Header không mâu thuẫn với ExecutionContext.
4. Giá trị không chứa dữ liệu nhạy cảm hoặc newline/log injection.
5. Reply được ghép đúng request dù worker hoàn thành đảo thứ tự.

## 20. Retry, restart và log một partition qua nhiều lần thực thi

Cùng một partition name có thể xuất hiện trong một lần chạy lỗi và lần restart sau. Khi lọc log:

~~~text
jobName=normalizeOrdersJob
partitionName=time-0002
businessRunKey=2026-11-25
~~~

có thể thấy:

~~~text
09:00  jobExec=8100 stepExec=8142 worker=worker-a
       partition=time-0002 event=partition_started

09:05  jobExec=8100 stepExec=8142 worker=worker-a
       partition=time-0002 event=partition_failed

09:12  jobExec=8125 stepExec=8221 worker=worker-b
       partition=time-0002 event=partition_started

09:17  jobExec=8125 stepExec=8221 worker=worker-b
       partition=time-0002 event=partition_finished status=COMPLETED
~~~

**Không giả định** mọi restart luôn tạo đúng cách bố trí StepExecution ở ví dụ; ID/tên thực tế phụ thuộc framework và trạng thái checkpoint. Điều quan trọng là log phân biệt **logical work**, **execution attempt** và **worker instance**.

### Khi nào cần thêm attempt?

Nếu transport có thể redeliver cùng message trong một execution, số attempts có thể được quản lý ở tầng broker/handler chứ không trùng với JobExecution count. Nên đặt `messageAttempt` hoặc `handlerRetryAttempt` cùng mô tả phạm vi, tránh trường chung tên `retryCount` gây hiểu nhầm.

### Input partition phải ổn định

Log start nên ghi hoặc liên kết tới `fromInclusive`, `toExclusive`, shard/cutoff đã chốt. Nếu mã partitioning đổi trong lần restart, cùng tên `time-0002` có thể nhận input khác; đó là vấn đề restart/correctness chứ không chỉ logging.

## 21. Worker crash: không có dòng finish không có nghĩa rollback

Một sự cố khó:

~~~text
T0  Worker nhận partition time-0002
T1  Worker xử lý 15 chunk
T2  Chunk thứ 15 COMMIT DB
T3  JVM chết trước khi gửi reply/log kết thúc
T4  Manager chưa nhận kết quả cuối
~~~

Khi xem log, có thể chỉ thấy `partition_progress` mà không thấy `partition_finished`. Không nên kết luận toàn bộ 15 chunk đã rollback, vì DB có thể đã commit một phần và JobRepository có checkpoint tương ứng.

**Cần kết hợp:**

- `StepExecution` và `ExecutionContext` trong JobRepository.
- Commit/rollback trạng thái resource theo transaction thực.
- Trạng thái broker request/ack/reply nếu có.
- Ledger/business idempotency để tránh xử lý lại sai.
- Worker liveness và timestamps để xác định sự cố.

### Log trạng thái chưa chắc chắn trung thực

Ví dụ:

~~~text
ERROR event=partition_reply_failed
      partitionName=time-0002
      stepExecutionId=8142
      dbCommitStatus=COMMITTED
      replyDeliveryStatus=UNKNOWN
      errorCategory=BROKER_CONNECTION_LOST
~~~

Chỉ log `COMMITTED` nếu worker thực sự biết commit đã thành công; nếu không, dùng `UNKNOWN`. Phân biệt **thông tin đã quan sát** với suy luận sau timeout.

Một reply thất lạc không đồng nghĩa request được phép chạy song song trên worker khác. Đặc biệt với remote partitioning, phải kiểm tra quyền sở hữu StepExecution trước khi dispatch lại.

## 22. Logging lỗi nên ghi phase và khả năng phục hồi

Các nhóm lỗi phổ biến ở worker:

| Phase | Ví dụ lỗi | Field hữu ích |
| --- | --- | --- |
| `READ` | Query timeout, cursor closed | Data range, SQL category, checkpoint |
| `PROCESS` | Validation, CPU timeout, API 429 | Processor/operation, retryable |
| `WRITE` | Deadlock, unique conflict, lock wait | Transaction status, chunk size |
| `COMMIT` | Transaction manager/DB error | Commit status có chắc không? |
| `REPLY` | Broker disconnect | Correlation, reply state |
| `RESTART` | Checkpoint mismatch | Previous/current execution IDs |
| `SHUTDOWN` | Forced stop | Inflight/unacked/chunk state |

Log lỗi nên có:

~~~text
event=chunk_retry
partitionName=time-0002
stepExecutionId=8142
phase=WRITE
errorCategory=DB_DEADLOCK
retryAttempt=2
backoffMs=400
outcome=RETRYING
~~~

Đừng ghi `status=FAILED` ở một event tạm thời nếu step cuối cùng có thể `COMPLETED` sau retry. Phân biệt `chunk_retry`, `chunk_error`, `partition_failed`.

### Stack trace và rate limit

Một stack trace ở ERROR khi lỗi đã exhausted hữu ích cho điều tra. Nhưng hàng nghìn retry giống nhau không cần hàng nghìn stack trace đầy đủ. Dùng metric/counter, sampling và giữ log lần đầu/lần cuối đủ ngữ cảnh.

Không log nguyên `Exception.getMessage()` nếu có nguy cơ chứa URL với token, SQL parameters hoặc PII mà chưa qua redaction policy.

## 23. Log khác metric, trace và business reconciliation

| Nguồn | Trả lời tốt nhất | Không thay thế |
| --- | --- | --- |
| Structured logs | Một partition đã trải qua những mốc/lỗi gì? | Checkpoint thực |
| Metrics | Bao nhiêu partition chậm, p95, throughput, pool wait? | Danh sách item đã ghi |
| Distributed tracing | Request đi qua manager/broker/worker thế nào? | Business idempotency |
| JobRepository | StepExecution nào hoàn tất, checkpoint ở đâu? | Timeline chi tiết network/API |
| Business DB/ledger | Output có đủ, không trùng, đúng phiên bản? | Root cause của timeout |

### Metric cardinality

`partitionName` và `jobExecutionId` có thể tạo rất nhiều giá trị khác nhau. Nếu mỗi ngày có 10.000 partitions, việc dùng kết hợp `jobExecutionId,partitionName` làm label của Prometheus counter có thể tạo số time series rất lớn.

Khuyến nghị mặc định:

- **Logs/traces:** có partitionName, stepExecutionId, correlationId đầy đủ để tìm một sự cố.
- **Metrics:** label có số giá trị kiểm soát như `job`, `step`, `status`, `workerPool`, `errorCategory`.
- **Business audit:** sử dụng business key trong kho có quyền truy cập phù hợp, không biến nó thành label metric.

Nếu hệ thống nhỏ có partition names cố định và cardinality được kiểm soát, có thể cân nhắc metric per-partition. Đây là quyết định vận hành dựa vào quy mô thật, không phải quy tắc cấm tuyệt đối.

## 24. Distributed tracing qua manager và worker

Tracing context có thể đi qua message headers nếu framework/instrumentation hỗ trợ. **MDC không tự lan qua network**.

~~~mermaid
sequenceDiagram
    participant M as Manager JVM
    participant Q as Broker
    participant W as Worker JVM
    participant T as Telemetry backend

    M->>Q: Request + trace context
    Q->>W: Message được giao
    W->>W: Khôi phục trace context
    W->>W: Đọc StepExecution/partitionName
    W->>T: Span và log có execution identity
    W-->>Q: Reply/correlation theo protocol
    Q-->>M: Reply
~~~

Phân biệt các ID:

- `traceId`: liên kết spans trong một trace.
- `correlationId`: ghép một request–reply hoặc message group.
- `partitionName`: phạm vi dữ liệu logic.
- `stepExecutionId`: execution cụ thể trong JobRepository.
- `businessEventId`: định danh side effect/deduplication.

Không dùng trace ID làm idempotency key. Nếu trace được sampling, vẫn cần logs/metrics/JobRepository cho các lỗi quan trọng.

### Cẩn trọng với propagation

- Header mapper có thể loại `traceparent` hoặc custom fields.
- Worker may start new spans khi message đến; không giả định mọi process có cùng ThreadLocal.
- `replyChannel` nội bộ JVM có thể không serialize nguyên dạng.
- Async callback cần context propagation phù hợp backend và executor.
- Không lấy thông tin authorization từ trace baggage chưa được xác thực.

## 25. Log volume: không in INFO cho mọi item

Với 20 triệu item, nếu mỗi item tạo một log trung bình 300 byte:

\[
20.000.000\times300
=6.000.000.000\ \mathrm{bytes}
\]

Tức khoảng **6 GB thập phân** chỉ cho phần log ấy, chưa tính JSON overhead, indexing, replication, stack traces hay retry.

### Chính sách log thực tế

- **INFO:** partition start/finish, progress theo chu kỳ, tổng hợp lỗi/retry.
- **WARN:** retry đáng chú ý, slow partition, backlog vượt ngưỡng.
- **ERROR:** lỗi cuối, dữ liệu mâu thuẫn hoặc sự cố cần can thiệp.
- **DEBUG:** item-level diagnostics trong khoảng thời gian điều tra có kiểm soát.
- **TRACE:** chỉ bật khi cần và có giới hạn, thường không dùng mặc định cho batch lớn.
- **Metrics:** thay việc log mỗi chunk chỉ để đo độ trễ.

Có thể log progress **mỗi 30 giây** hoặc **mỗi 100 chunk**, tùy phân bố workload. Nên giới hạn tốc độ log với lỗi lặp và có retention phù hợp.

### Không dùng log làm commit counter

Một item bị retry có thể được log nhiều lần; `readCount` có thể khác `writeCount` do filter/skip, còn StepExecution checkpoint phụ thuộc transaction. Tính throughput hữu ích bằng số business operation commit hợp lệ và thời gian toàn tuyến, không đếm số dòng INFO.

## 26. Bảo mật: partitionName không được lộ PII

Nếu partitioning theo khách hàng hoặc tenant, đừng đặt tên bằng email/địa chỉ/số thẻ.

Nên dùng:

~~~text
partitionName=tenant-shard-0007
partitionName=time-20261125-02
partitionName=range-0012
~~~

Không nên dùng:

~~~text
partitionName=customer-email@example.org
partitionName=payment-card-number-here
partitionName=access-token-here
~~~

### Các biện pháp

1. Dùng shard ID/pseudonymous key khi đủ cho vận hành.
2. Kiểm tra/cắt giới hạn chiều dài và ký tự của header trước khi log.
3. Chống log injection bằng structured fields và escaping JSON.
4. Không đưa raw payload, token, password và query parameters nhạy cảm vào exception log.
5. Phân quyền xem log theo môi trường và tổ chức.
6. Có retention/redaction theo chính sách.
7. Không dùng partitionName trong log làm cơ chế cấp quyền truy cập dữ liệu.

Logging là chức năng **observability**, không phải authorization.

## 27. Tra cứu một partition chậm và xác định bottleneck

Giả sử log tìm được:

~~~text
jobName=normalizeOrdersJob
jobExecutionId=8100
partitionName=time-0002
~~~

Timeline:

~~~text
02:00 event=partition_started from=... to=...
02:03 event=partition_progress readCount=250000
02:07 event=chunk_retry errorCategory=DB_DEADLOCK
02:10 event=partition_progress readCount=420000
02:13 event=partition_failed status=FAILED
~~~

Đây là một **bộ điều kiện lọc logic**, không phải cú pháp của một query engine cụ thể; Elasticsearch/OpenSearch, Loki và Splunk có query syntax khác nhau.

Dựa vào metric bổ sung:

| Tín hiệu | Nghi vấn |
| --- | --- |
| SQL p95 cao và readCount tăng chậm | Reader query/index/source DB |
| ReadCount tăng nhanh, writeCount chậm | Writer/target DB bottleneck |
| DB lock wait cao | Hot rows hoặc transaction contention |
| Worker CPU cao, DB nhàn | Processor CPU-bound |
| JDBC pool pending cao | Thiếu connection hoặc DB giữ connection lâu |
| Broker queue age cao, CPU worker nhàn | Inbound routing/consumer config |
| Retry đồng loạt tăng | Downstream outage/retry storm |
| Một partition chứa quá nhiều item | Data skew |
| Không có finish log sau worker crash | Cần xem JobRepository, không tự suy đoán rollback |

Không tăng số worker chỉ vì thấy một partition chậm: nếu DB lock đã cao, tăng concurrency có thể khiến tình trạng tệ hơn.

## 28. JUnit test: MDC được dọn sau StepExecution

Kiểm thử listener ngay ở mức unit/component để phát hiện rò identity.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

class PartitionLoggingListenerTest {

    private final PartitionLoggingListener listener =
            new PartitionLoggingListener();

    @Test
    void contextIsClearedAfterStep() {
        StepExecution execution =
                MetaDataInstanceFactory.createStepExecution();

        execution.getExecutionContext().putString(
                "partitionName", "time-0002");

        try {
            listener.beforeStep(execution);
            assertEquals(
                    "time-0002", MDC.get("partitionName"));
        } finally {
            listener.afterStep(execution);
        }

        assertNull(MDC.get("partitionName"));
        assertNull(MDC.get("jobExecutionId"));
        assertNull(MDC.get("stepExecutionId"));
        assertNull(MDC.get("stepName"));
    }
}
~~~

Test giả định có `spring-batch-test`, JUnit 5 và SLF4J provider có MDC phù hợp. Cần dùng logging backend thật ở lớp integration test vì `MDC.get` đúng không chứng minh field đã được xuất ra stdout/collector.

### Các test bổ sung

- PartitionName rỗng → listener fail rõ và không để lại MDC.
- Hai partition A/B chạy song song → không hoán đổi identity.
- Chạy B ngay sau A trên **cùng thread pool thread** → B không bị gắn tên A.
- Chunk throw exception → log lỗi giữ đúng partition.
- Worker StepExecutor async → task thật có context theo cơ chế đã thiết kế.
- Formatter output có `partitionName` đúng JSON/path, không chỉ trong memory.

## 29. Test thread reuse và lỗi propagation

Một test TaskDecorator phải dùng **ít nhất hai đến ba tác vụ liên tiếp trên cùng thread**, bởi task đầu tiên có thể log đúng dù quên cleanup.

Kịch bản:

1. Tạo `ThreadPoolTaskExecutor` với core=max=1.
2. Trên thread submit, gắn MDC partition A rồi submit task A.
3. Gắn MDC partition B rồi submit task B.
4. Xóa MDC trên caller, submit task C.
5. Task A phải thấy A, B thấy B, C không được thấy A/B.
6. Cho task B throw exception và xác minh TaskDecorator vẫn restore/clear.
7. Thử song song nhiều tasks bằng `CountDownLatch`, có deadline hữu hạn.

**Giới hạn:** decorator chỉ copy MDC lúc submit; nó không phát hiện partition từ một task đã được manager tạo nhưng caller không đặt identity. Test riêng phải xác minh nơi bind context ở worker StepExecution.

Ngoài ra, nếu chunk code spawn `CompletableFuture` trên executor khác, lại cần test propagation ở executor đó. Không được kết luận một TaskDecorator giải quyết toàn bộ thread model.

## 30. Integration test nhiều JVM và fault injection

Một topology thử nghiệm thực tế:

~~~mermaid
flowchart TB
    M["Manager JVM"] --> Q[["Request/reply broker"]]
    Q --> W1["Worker JVM A"]
    Q --> W2["Worker JVM B"]
    W1 --> J[("JobRepository")]
    W2 --> J
    M --> J
    W1 --> D[("Business DB")]
    W2 --> D
    W1 --> L[["Log collector"]]
    W2 --> L
    M --> L
~~~

| Kịch bản | Điều cần kiểm tra ở log | Điều cần kiểm tra ngoài log |
| --- | --- | --- |
| Hai partition chạy đồng thời | Identity không bị đảo | Data ranges không chồng lấn |
| Worker A chậm, B nhanh | Progress/elapsed tách riêng | Manager vẫn tổng hợp đúng |
| Kill trước DB commit | Có thể thiếu finish log | Rollback/restart đúng |
| Kill sau commit trước reply | Log có thể kết thúc đột ngột | Writer không nhân đôi side effect |
| Broker redelivery | Correlation/attempt đủ điều tra | Không xử lý trùng dữ liệu |
| Manager timeout, worker còn chạy | Timeline phản ánh trạng thái chưa rõ | Không giao cùng StepExecution thiếu kiểm soát |
| Một header bị lọc | Log cảnh báo metadata thiếu | Worker vẫn dùng ExecutionContext |
| Restart ở worker khác | Tên partition logic vẫn đúng | Input/checkpoint ổn định |
| Rolling deploy | Worker/version có trong log | Protocol tương thích |

**Chú ý:** một worker bị kill bằng tín hiệu cưỡng bức có thể không chạy `afterStep` hay flush log. Không dùng sự tồn tại của `partition_finished` làm điều kiện duy nhất cho correctness. Cần đối soát JobRepository, DB và broker state thực.

## 31. Case study: 24 triệu sự kiện và 16 partitions

Một hệ thống tổng hợp **24.000.000 sự kiện** có SLA **25 phút**. Manager chia input thành 16 partitions với cận dữ liệu ổn định; tám worker JVM xử lý song song.

Thông lượng tối thiểu lý tưởng:

\[
R_{\mathrm{required}}
=\frac{24.000.000}{25\times60}
=16.000\ \mathrm{items/s}
\]

Trước khi có partition-aware logging, dashboard chỉ thấy job quá hạn; không biết phần việc nào chậm.

### Bước 1 — Chuẩn hóa metadata

Mỗi worker log:

~~~text
partitionName=time-0000 ... time-0015
jobExecutionId=<execution hiện tại>
stepExecutionId=<worker execution hiện tại>
workerInstance=<JVM đang xử lý>
fromInclusive=<đầu window>
toExclusive=<cuối window, loại trừ>
~~~

Manager giữ danh sách các partition và JobParameters/cutoff đã chốt. Worker có `partition_started`, progress định kỳ và `partition_finished` hoặc lỗi.

### Bước 2 — Phát hiện partition chậm

Giả định 15 partition hoàn thành trong khoảng 13–18 phút, còn `time-0011` mất 27 phút. Log có nhiều `DB_LOCK_TIMEOUT`; CPU worker thấp nhưng lock wait DB cao.

Điều này gợi ý **hot row contention hoặc transaction dài**, không nhất thiết thiếu JVM.

### Bước 3 — Benchmark giả định

| Cấu hình | Throughput hữu ích | Thời gian lý tưởng 24 triệu/N | Đúng dữ liệu |
| --- | ---: | ---: | --- |
| 4 JVM, DB lock cao | 10.000 item/s | 40,0 phút | PASS |
| 8 JVM, DB lock cao | 13.500 item/s | 29,6 phút | PASS |
| 12 JVM, DB lock cao | 13.800 item/s | 29,0 phút | PASS nhưng đắt |
| 8 JVM sau giảm contention | 18.500 item/s | 21,6 phút | PASS |
| 12 JVM sau giảm contention | 19.000 item/s | 21,1 phút | PASS, lợi ích biên nhỏ |

Mọi số liệu đều **giả định**, `N/R` chỉ ước lượng thời gian tối thiểu theo throughput chứ không phải cam kết SLA. Log giúp tìm bottleneck nhưng tự nó **không làm job nhanh hơn**.

### Bước 4 — Kiểm chứng restart

Kill worker đang xử lý `time-0011` ngay sau commit một chunk nhưng trước reply. Sau khi phục hồi:

- Partition identity và range không thay.
- Log phân biệt các worker instances/execution attempts.
- Không có side effect trùng theo business key.
- JobRepository có trạng thái phù hợp.
- Cuối job, đối soát đủ business events hợp lệ.

**Bài học:** khi partition-aware logs liên kết với metrics và metadata, “job chậm” trở thành câu hỏi có thể điều tra: **partition nào, tại phase nào, chờ resource gì và đã commit gì trước lỗi**.

## 32. Những lỗi triển khai thường gặp

| Sai lầm | Tác hại | Cách đúng |
| --- | --- | --- |
| Chỉ log hostname/thread | Không biết phạm vi dữ liệu | Log partitionName + execution IDs |
| Chỉ log partitionName | Trộn nhiều lần chạy/restart | Thêm job/step identity |
| Parse `stepName` tùy tiện | Hỏng khi convention thay đổi | Đặt identity vào ExecutionContext |
| Gắn partition name UUID mới mỗi lần retry | Không ghép được logical work | Deterministic names, attempt tách riêng |
| Singleton field `currentPartition` | Race khi parallel StepExecutions | Stateless listener, MDC đúng thread |
| Không dọn MDC | Log B mang partition A | Cleanup trong finally/afterStep |
| Chỉ gắn MDC ở manager thread | Worker thread/JVM thiếu context | Bind từ StepExecution ở worker |
| Tin TaskDecorator tự biết partition | Copy context không đúng | Propagation có nguồn identity rõ |
| Ép remote chunking có partitionName giả | Sai mô hình execution | Dùng chunk correlation/work ID |
| INFO cho từng item | Tăng CPU/I/O và chi phí log | Log summary + metrics |
| Dùng partitionName làm metric label vô hạn | High cardinality | Dùng logs/traces cho IDs động |
| Log raw payload/token | Lộ dữ liệu | Redaction và phân quyền |
| Coi finish log là DB commit proof | Crash/async side effect | JobRepository và đối soát |
| Coi `writeCount` là unique keys | Retry/filter/skip | So tập business keys |
| Không test worker chết sau commit | Bỏ qua duplicate window | Fault injection |
| Coi broker FIFO là business commit order | Worker có thể hoàn thành đảo thứ tự | Sequence guard khi nghiệp vụ yêu cầu |
| Tăng worker khi DB lock cao | Contention tăng | Đo SQL, lock và sửa bottleneck |

## 33. Checklist triển khai và vận hành

- [ ] Partition names deterministic, duy nhất trong tập và không lộ PII.
- [ ] Partitioner ghi `partitionName` và input range đúng ExecutionContext.
- [ ] Map key và `ExecutionContext.partitionName` nhất quán.
- [ ] Input cutoff/window ổn định qua restart.
- [ ] Worker log `jobExecutionId`, `stepExecutionId`, `stepName`, `workerInstance`.
- [ ] Structured schema có `timestamp`, `level`, `event` và `partitionName`.
- [ ] Logging backend thực sự render MDC/JSON fields.
- [ ] Listener stateless, không dùng field mutable chứa current partition.
- [ ] MDC được dọn ngay cả khi task/step gặp exception.
- [ ] TaskExecutor propagation được test trên thread thật và thread reuse.
- [ ] Không giả định MDC tự vượt broker/JVM.
- [ ] Không ghi đè protocol correlation/reply headers của Integration.
- [ ] Remote chunking không bị gắn partition identity giả.
- [ ] Có lifecycle events start/progress/finish/error với tần suất hợp lý.
- [ ] Metrics đo throughput, DB pool wait/lock, broker queue age, retry.
- [ ] Metric labels không có ID động không giới hạn.
- [ ] Có chính sách log redaction, retention, access control.
- [ ] Reply trễ/duplicate/timeout được log cùng correlation đúng.
- [ ] Restart phân biệt logical partition với execution/attempt mới.
- [ ] Log trạng thái commit chưa rõ bằng `UNKNOWN`, không đoán.
- [ ] Test nhiều partition đồng thời, MDC cleanup, async callbacks.
- [ ] Test worker crash trước/sau commit, redelivery và restart.
- [ ] Đối soát JobRepository và business DB thay vì chỉ đọc log.
- [ ] Có runbook tìm partition chậm/lỗi từ log và metric.
- [ ] SLA được đánh giá bằng thời gian end-to-end cùng tính đúng dữ liệu.

## 34. Câu hỏi tự kiểm tra

**1. Vì sao chỉ `partitionName=time-0002` chưa đủ cho điều tra?**

Vì cùng tên có thể xuất hiện ở nhiều JobExecution/restart hoặc job khác. Cần jobName, jobExecutionId, stepExecutionId, workerInstance và thời gian.

**2. Spring Batch có tự ghi `partitionName` vào mọi ExecutionContext không?**

Không nên giả định. Partitioner trả Map có key là tên partition; ứng dụng có thể tự đưa `partitionName` vào ExecutionContext làm logging contract tường minh.

**3. Vì sao không nên parse `stepExecution.getStepName()` để lấy partition bằng dấu hai chấm?**

Vì tên có thể bị đổi/tùy biến; parse có thể sai. Log stepName gốc và dùng input context đã thống nhất.

**4. MDC có đi qua RabbitMQ/Kafka từ manager sang worker không?**

Không tự động. Worker cần dựng lại context từ StepExecution; tracing/correlation headers có cơ chế propagation riêng và cần kiểm thử.

**5. Listener singleton có field `currentPartitionName` nguy hiểm ở đâu?**

Hai StepExecutions đồng thời có thể ghi đè field, khiến log A hiển thị tên B.

**6. Vì sao phải dọn MDC trong finally và test thread reuse?**

Thread pool tái sử dụng threads. Nếu không dọn, request tiếp theo có thể mang partition identity cũ dù request đầu log đúng.

**7. TaskDecorator có tự xác định partitionName từ TaskExecutor không?**

Không. Nó chỉ copy MDC của thread submit task; nếu caller không có partition đúng thì task cũng không có.

**8. Trong remote chunking, nên log field nào thay partitionName nếu không có partition?**

Dùng request/chunk correlation ID, logical work ID và manager job/step execution identity theo contract.

**9. Tại sao không dùng mọi partitionName và JobExecutionId làm metric labels?**

Vì cardinality có thể rất lớn theo số partition/lần chạy. Logs/traces phù hợp cho tìm kiếm ID động, metrics nên tổng hợp.

**10. Worker commit DB rồi chết trước log `partition_finished`. Có thể kết luận rollback không?**

Không. Cần kiểm tra JobRepository, DB state, broker và idempotency ledger; log cuối có thể không được flush.

**11. `readCount=100000`, `writeCount=95000` có chắc mất 5000 item không?**

Không. Có thể có filter/skip/rollback và cách tính counter. Cần xem metadata và đối soát business keys.

**12. Vì sao không nên INFO log mọi item?**

Hàng chục triệu item có thể tạo nhiều GB log, tăng CPU/I/O và chi phí collector. Dùng lifecycle/progress logs với metrics và DEBUG có chọn lọc.

**13. Partition `time-0002` chạy ở worker-a rồi worker-b. Trường nào nên ổn định?**

Partition name và logical input range cần ổn định; workerInstance và execution IDs có thể khác theo recovery.

**14. Làm sao kiểm tra một partition chậm vì DB lock thay vì thiếu thread?**

Dùng partition timeline/progress cùng DB lock wait, SQL p95, pool wait, CPU worker. Nếu lock wait cao, tăng concurrency có thể phản tác dụng.

**15. Log partitionName có thay thế business idempotency key không?**

Không. Partition name định danh phần việc, có thể chứa nhiều business events. Dedupe phải dựa vào identity của side effect và transaction phù hợp.

---

**Ghi nhớ:** **Partition name là định danh logic của phần dữ liệu**, không phải tên thread, hostname, message ID hay business idempotency key. Muốn worker logging đáng tin cậy, hãy lưu tên partition vào ExecutionContext một cách tường minh; log kèm JobExecution/StepExecution và worker instance; bind MDC ở đúng thread và cleanup nghiêm ngặt. Khi scale sang nhiều JVM, worker phải dựng lại context từ metadata thay vì dựa vào ThreadLocal của manager. Kết hợp structured logs, metrics, tracing, JobRepository và đối soát business data để trả lời **partition nào chậm, lỗi ở đâu, đã commit gì và phục hồi ra sao**.

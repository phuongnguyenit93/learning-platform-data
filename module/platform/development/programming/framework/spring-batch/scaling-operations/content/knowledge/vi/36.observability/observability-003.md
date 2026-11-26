# Log theo partition name trong Spring Batch

> **Chương:** Observability
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình xử lý phân tán; đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và lựa chọn kiến trúc phù hợp tài nguyên.

Khi một job có 16 partition chạy song song, dòng log `"Processing order"` không còn đủ để xác định **worker nào đã xử lý**, **phần dữ liệu nào bị ảnh hưởng** và **kết quả thuộc lần chạy/restart nào**. Nếu chỉ dựa vào thread name hoặc timestamp, một incident có thể mất hàng giờ để khoanh vùng. **Log theo partition name** giúp gắn ngữ cảnh của từng phần việc vào các sự kiện đọc, xử lý, ghi, rollback và hoàn tất worker step.

Tuy vậy, một log có `partitionName` không tự trở thành log đáng tin cậy: phải biết partition key lấy từ đâu, phân biệt nó với `StepExecutionId`, **truyền context qua thread/broker đúng cách**, cleanup `MDC` khi thread được tái sử dụng và tránh in dữ liệu nhạy cảm.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `jobName`, `JobInstanceId`, `JobExecutionId`, `StepExecutionId`, `stepName` và `partitionName` trong Spring Batch.
2. Thiết kế **structured logging** để truy vấn theo partition, worker, input snapshot, status, error code mà không ghép chuỗi log khó phân tích.
3. Gắn context bằng `StepExecutionListener` và SLF4J `MDC`; biết chính xác nơi cần **dọn MDC** khi kết thúc.
4. Truyền MDC đến **chunk threads** với `TaskDecorator` và nạp lại correlation trong **remote workers**, không giả định `ThreadLocal` tự đi qua executor hoặc broker.
5. Thiết kế log cho skip/retry/rollback/restart, tránh báo sai “đã commit” và không làm ngập log khi dữ liệu lỗi hàng loạt.
6. Kiểm thử partition context không bị cross-talk và dùng log phối hợp `JobRepository`, metrics, tracing để điều tra sự cố vận hành.

## 1. Bài toán vận hành: log của 16 worker trộn nhau

Giả sử manager chia 4 triệu đơn hàng thành 16 partition. Một phần chạy trên máy A, phần khác ở các worker pods B, C và D.

~~~text
2026-11-26 10:00:01 INFO  Processing batch
2026-11-26 10:00:02 WARN  Order validation failed
2026-11-26 10:00:02 ERROR Database timeout
2026-11-26 10:00:03 INFO  Processing batch
~~~

Các dòng này không giúp trả lời:

- Database timeout thuộc **partition nào**?
- Nó xảy ra ở `JobExecution` đầu hay lần **restart**?
- Partition đó đọc **file/range/tenant** nào?
- Lỗi có khiến worker `FAILED`, hay chunk được retry rồi thành công?
- Cần replay phần việc nào mà không chạy lại partition đã `COMPLETED`?

Một log có cấu trúc tốt hơn:

~~~text
time=2026-11-26T10:00:02Z level=ERROR
event=chunk_rollback job=ordersImport
jobExecutionId=502 stepExecutionId=719
stepName=ordersWorker:partition-0007
partitionName=partition-0007
sourceVersion=orders-2026-11-26
workerId=worker-pod-b
errorCode=DB_CONNECTION_TIMEOUT
message="Chunk transaction rolled back"
~~~

Đây là **mẫu sự kiện minh họa**, không phải kết quả mặc định của Spring Batch hoặc một format Logback tự sinh. Các trường phải được cấu hình/ghi rõ và một phần metadata cần được ứng dụng cung cấp.

## 2. Các định danh không được đánh đồng

| Trường | Ý nghĩa | Có ổn định qua restart? | Dùng cho |
| --- | --- | --- | --- |
| `jobName` | Tên job, ví dụ `ordersImport` | Có | Gom nhóm loại pipeline |
| `JobInstanceId` | Một `JobInstance` được xác định theo job name + identifying parameters | **Có** khi restart cùng instance | Liên kết lịch sử của cùng công việc logic |
| `JobExecutionId` | Một **lượt thực thi** của JobInstance | Không; restart tạo execution mới | Điều tra một lần chạy |
| `StepExecutionId` | Một **lượt chạy step/worker step** | Có thể đổi khi restart | Tra metadata/checkpoint/counters của worker |
| `stepName` | Tên step execution | Thường ổn định theo kế hoạch partition | Tra `StepExecution`, cấu trúc step |
| `partitionName` | **Logical partition key** do `Partitioner` trả về | **Nên ổn định** nếu input plan giữ nguyên | Ghép log các lần chạy/retry của cùng phần việc |
| `workerId` | Pod/host/process/container đang thực hiện | Có thể đổi | Điều tra node, pool, sự cố hạ tầng |
| `sourceVersion` | Phiên bản snapshot/manifest input | Phải bất biến trong cùng kế hoạch | Đối soát dữ liệu và replay |
| `correlationId` | ID luồng trao đổi request/reply/message | Theo hợp đồng transport | Theo dấu một request qua các thành phần |

**Quan trọng:** `partitionName` là **tên phân vùng logic**, không phải `StepExecutionId`, thread name hoặc process ID. Partition `partition-0007` có thể được một worker khác xử lý trong lần restart nhưng vẫn biểu diễn **cùng miền dữ liệu**.

### Step name có luôn chứa partition name không?

Trong các cấu hình partitioning quen thuộc, worker `StepExecution` thường có tên dạng:

~~~text
ordersWorker:partition-0007
~~~

Đây là **quy ước tên do cơ chế splitter tạo trong mô hình đó**, không nên mặc định mọi kiến trúc hoặc mọi adapter remote đều lưu đúng định dạng này. Một step không partitioned chỉ có tên step; một ứng dụng có thể custom splitter/naming.

**Cách chắc chắn:** lấy `stepExecution.getStepName()` làm `stepName`, và chủ động đưa `partitionName` vào `ExecutionContext` từ `Partitioner` để có **field riêng**. Tránh suy partition key bằng `split(":")` trên chuỗi tên step: đổi naming convention sẽ làm log sai hoặc vỡ parser.

## 3. Thiết kế log schema trước khi thêm MDC

Đối với Batch, nên có **schema ngữ nghĩa nhất quán**, dù đầu ra là JSON hoặc log text có `key=value`.

| Nhóm | Trường gợi ý | Ghi chú |
| --- | --- | --- |
| Thời gian | `timestamp`, `level` | UTC và chuẩn thời gian nhất quán |
| Pipeline | `service`, `jobName`, `jobInstanceId`, `jobExecutionId` | Phân biệt loại job và lần chạy |
| Worker | `stepName`, `stepExecutionId`, `partitionName`, `workerId` | Tương quan metadata và node |
| Dữ liệu | `sourceVersion`, `fileId` hoặc `rangeId` | Không log nguyên payload/PII |
| Sự kiện | `event`, `phase`, `outcome` | Từ vựng có kiểm soát |
| Lỗi | `errorCode`, `exceptionType`, `retryable` | Nhóm nguyên nhân thay vì chỉ message tự do |
| Tương quan | `traceId`, `spanId`, `correlationId`, `messageId` | Có nếu tracing/broker thực sự cung cấp |
| Đo lường | `readCount`, `writeCount`, `skipCount`, `rollbackCount`, `elapsedMs` | Chọn sự kiện tóm tắt phù hợp |

Các trường có ý nghĩa khác nhau nên **không dùng chung tên**. Ví dụ `jobExecutionId` không được gán bằng `JobInstanceId`; `partitionName` không được mặc định bằng `workerId`.

### Bộ event names nên cố định

~~~text
job_started / job_finished
partition_started / partition_finished
chunk_committed / chunk_rollback
item_skipped / item_filtered_summary
retry_exhausted
worker_disconnected / reply_timeout
partition_restarted / reconciliation_mismatch
~~~

Lựa chọn tên tùy hệ thống, nhưng nên duy trì như một **log contract**. Dashboard/alert theo `event=chunk_rollback` đáng tin hơn tìm kiếm chuỗi message tiếng Anh bị thay đổi khi refactor.

## 4. Partitioner gắn partition name vào ExecutionContext

`Partitioner.partition(gridSize)` trả về một `Map<String, ExecutionContext>`. **Key của map** là logical partition name; các giá trị trong context chứa tham số phạm vi cho worker.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class FilePartitioner implements Partitioner {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        // Ví dụ: danh sách file đã được chốt trong manifest input.
        for (int i = 0; i < gridSize; i++) {
            String name = "partition-%04d".formatted(i);
            ExecutionContext context = new ExecutionContext();
            context.putString("partitionName", name);
            context.putString("fileId", "orders-" + i + ".csv");
            context.putString("sourceVersion", "snapshot-2026-11-26");
            result.put(name, context);
        }
        return result;
    }
}
~~~

Đoạn code minh họa Java 17/Spring Batch 5.x. Trong production, không được **tự giả định có đúng `gridSize` file**; `Partitioner` phải dựa trên manifest/range thật đã chốt, xử lý file ít/nhiều hơn gridSize, gắn tenant và bảo đảm không trùng/bỏ sót dữ liệu. `sourceVersion` nên đến từ tham số/snapshot thật thay vì hardcode.

### Vì sao lưu partitionName hai nơi?

~~~text
partition map key    : partition-0007
ExecutionContext key : partitionName = partition-0007
Worker StepExecution : ordersWorker:partition-0007 (trong cấu hình phổ biến)
~~~

Map key cho splitter xác định phân vùng logic; `ExecutionContext` cung cấp field rõ ràng cho listener/reader và cho remote worker nhận từ metadata. Đây là **quy ước ứng dụng** giúp tránh parse tên step.

**Không** sinh `partitionName = UUID.randomUUID()` ở mỗi restart. Nếu cùng logical partition thay tên và thay range, log không còn hỗ trợ truy vết hoặc khôi phục checkpoint đáng tin cậy.

## 5. MDC là gì và giúp gì cho log?

SLF4J cung cấp `MDC` (*Mapped Diagnostic Context*) để gắn cặp `key=value` vào **ngữ cảnh của thread hiện tại** khi logging backend hỗ trợ. Logback thường xuất các giá trị này bằng `%X{key}` trong pattern hoặc qua structured encoder.

Ví dụ:

~~~java
import org.slf4j.MDC;

MDC.put("partitionName", "partition-0007");
log.info("Worker started");
MDC.remove("partitionName");
~~~

Với cấu hình backend phù hợp, log có thể được gắn `partitionName=partition-0007` mà không cần đưa chuỗi đó vào mọi `log.info(...)`.

### Những giới hạn cần hiểu

- MDC **không phải kho dữ liệu nghiệp vụ**: nó hỗ trợ logging, không quyết định partition/restart.
- MDC của backend thông dụng dựa trên **thread-local context**, không mặc định truyền an toàn sang thread khác.
- Thread pool **tái sử dụng thread**. Nếu quên dọn MDC, worker kế tiếp có thể mang `partitionName` của worker trước.
- MDC **không đi qua message broker hoặc network** trừ khi có cơ chế chuyển context trong message headers/payload.
- Nếu một event bắt buộc phải có identity chính xác để audit, hãy lưu identity đó trong **business record/quarantine**, không chỉ trông chờ MDC có mặt trong log.
- MDC có thể trống ở `JobLauncher`, manager flow, background task hoặc thread ngoài phạm vi step; log schema cần thể hiện `null/unknown` đúng nghĩa chứ không tự bịa partition.

## 6. Gắn MDC trong lifecycle của worker step

Một nơi hợp lý để tạo context cho log lifecycle là `StepExecutionListener` đăng ký trên **worker step**. Từ `StepExecution`, ta lấy metadata có thật; `partitionName` được truyền qua `ExecutionContext`.

### 6.1. Listener minh họa

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.batch.item.ExecutionContext;

public final class PartitionLoggingListener
        implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionLoggingListener.class);

    private static final String[] KEYS = {
            "jobName", "jobInstanceId", "jobExecutionId",
            "stepExecutionId", "stepName", "partitionName",
            "fileId", "sourceVersion"
    };

    @Override
    public void beforeStep(StepExecution step) {
        MDC.put("jobName",
                step.getJobExecution().getJobInstance().getJobName());
        MDC.put("jobInstanceId", String.valueOf(
                step.getJobExecution().getJobInstance().getId()));
        MDC.put("jobExecutionId", String.valueOf(
                step.getJobExecution().getId()));
        MDC.put("stepExecutionId", String.valueOf(step.getId()));
        MDC.put("stepName", step.getStepName());

        ExecutionContext context = step.getExecutionContext();
        MDC.put("partitionName",
                context.containsKey("partitionName")
                        ? context.getString("partitionName") : "not-partitioned");

        if (context.containsKey("fileId")) {
            MDC.put("fileId", context.getString("fileId"));
        }
        if (context.containsKey("sourceVersion")) {
            MDC.put("sourceVersion",
                    context.getString("sourceVersion"));
        }

        log.info("event=partition_started status={}",
                step.getStatus());
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        try {
            log.info(
                "event=partition_finished status={} exitCode={} "
                + "readCount={} writeCount={} skipCount={} rollbackCount={}",
                step.getStatus(),
                step.getExitStatus().getExitCode(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getSkipCount(),
                step.getRollbackCount());
            return null; // Không thay đổi ExitStatus của framework.
        } finally {
            for (String key : KEYS) {
                MDC.remove(key);
            }
        }
    }
}
~~~

**Đặc điểm của ví dụ:** Listener **không chứa field mutable theo partition** nên có thể dùng một singleton cho nhiều worker nếu callback chạy theo thread riêng. Khi `afterStep` chạy theo vòng đời bình thường, nó dọn các khóa mà listener đã tạo. Đoạn này minh họa cách gắn ngữ cảnh **trên thread thực thi callbacks**; không có nghĩa tất cả log ở thread khác tự động nhận được MDC.

**Các ràng buộc quan trọng:**

1. Đăng ký listener ở **worker step**, không chỉ ở manager `PartitionStep`; manager không xử lý từng item của worker.
2. Các tên `KEYS` là namespace do ứng dụng sở hữu. Nếu interceptor khác đã dùng những MDC keys đó, không nên xóa/ghi đè mù; hãy dùng namespace riêng hoặc cơ chế lưu/phục hồi context theo scope.
3. Nếu process bị kill cứng, `afterStep` không nhất thiết chạy. Mỗi task/thread reuse vẫn cần cleanup độc lập.
4. Nếu `beforeStep` ném exception giữa chừng, cần cơ chế cleanup thích hợp trong framework/adapter; production có thể đóng gói việc bind MDC theo `try/finally` tại ranh giới thực thi.
5. Không giữ `StepExecution`/`ExecutionContext` trong **field singleton mutable** rồi dùng từ những worker khác.

### 6.2. Đăng ký listener

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step ordersWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemWriter<OrderRow> writer,
        PartitionLoggingListener loggingListener) {

    return new StepBuilder("ordersWorkerStep", jobRepository)
            .<OrderRow, OrderRow>chunk(200, transactionManager)
            .reader(reader)
            .writer(writer)
            .listener(loggingListener)
            .build();
}
~~~

`OrderRow`, reader và writer là phần ứng dụng phải định nghĩa; listener cần được tạo thành bean hoặc cung cấp qua cấu hình. Với partitioning, builder này mô tả **worker step** được `PartitionHandler` điều phối, không phải manager step. Đoạn mã hướng tới Spring Batch 5.x và chưa phải ứng dụng độc lập có thể chạy ngay.

## 7. Xuất partitionName trong Logback

Nếu dùng Spring Boot với Logback, có thể cấu hình encoder pattern để đọc MDC:

~~~xml
<!-- Ví dụ file logback-spring.xml, không phải file được tạo trong bài. -->
<configuration>
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level
                [%thread] job=%X{jobName:-none}
                jobExecutionId=%X{jobExecutionId:-none}
                stepExecutionId=%X{stepExecutionId:-none}
                partitionName=%X{partitionName:-none}
                %logger{36} - %msg%n%ex{short}</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Đoạn này minh họa cách `%X{partitionName}` lấy dữ liệu từ MDC. Một số renderer sẽ giữ khoảng trắng/xuống dòng trong pattern; khi dùng production, hãy cấu hình pattern **một dòng**, hoặc ưu tiên JSON có fields riêng. Spring Boot/Logback version và cấu hình ứng dụng có thể khác; cần kiểm tra encoder đang hoạt động thực tế.

### Vì sao structured JSON thường dễ truy vấn hơn?

~~~json
{
  "timestamp": "2026-11-26T10:00:02Z",
  "level": "WARN",
  "service": "orders-batch-worker",
  "event": "item_skipped",
  "jobExecutionId": 502,
  "stepExecutionId": 719,
  "stepName": "ordersWorker:partition-0007",
  "partitionName": "partition-0007",
  "sourceVersion": "orders-2026-11-26",
  "phase": "PROCESS",
  "errorCode": "INVALID_ORDER"
}
~~~

Đây là **schema đích**, không phải JSON mà Logback tự sinh nếu chỉ thêm `MDC.put`. Cần lựa chọn encoder/structured logging capability tương thích Spring Boot/Logback đang sử dụng và kiểm tra rằng MDC keys được xuất thành fields như mong đợi.

Trong backend log search, tìm theo field:

~~~text
jobExecutionId = 502
AND partitionName = "partition-0007"
AND level IN ("WARN", "ERROR")
~~~

Đây là **pseudo-query**, không phải cú pháp chung của OpenSearch, Elasticsearch, Loki, Splunk hay Datadog. Mỗi backend có ngôn ngữ query riêng.

## 8. Multi-threaded step: MDC không tự đi sang chunk threads

Đây là tình huống dễ sai nhất. `beforeStep` thường chạy ở thread điều phối step. Nếu thêm `TaskExecutor` để các chunks chạy song song, từng chunk có thể được thực thi trên **thread pool khác**:

~~~mermaid
flowchart TB
    S["Step thread<br/>beforeStep: MDC partition-0007"] --> E["TaskExecutor"]
    E --> A["chunk thread A<br/>MDC có thể rỗng"]
    E --> B["chunk thread B<br/>MDC có thể rỗng"]
    E --> C["chunk thread C<br/>MDC có thể còn context cũ<br/>nếu cleanup sai"]
~~~

Vì vậy, thấy đúng MDC ở `partition_started` **không chứng minh** log của `ItemProcessor`, `ItemWriter` hay listener chạy trong chunk thread có `partitionName` đúng.

### 8.1. Truyền MDC bằng TaskDecorator

Với `ThreadPoolTaskExecutor` của Spring Framework, có thể dùng `TaskDecorator` để **copy MDC tại thời điểm task được submit**, rồi **phục hồi context trước đó trong finally**:

~~~java
import java.util.Map;

import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
ThreadPoolTaskExecutor batchChunkExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(64);
    executor.setThreadNamePrefix("batch-chunk-");

    TaskDecorator decorator = task -> {
        Map<String, String> captured = MDC.getCopyOfContextMap();
        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    };

    executor.setTaskDecorator(decorator);
    executor.initialize();
    return executor;
}
~~~

**Tính chất của ví dụ:**

- Context được copy **lúc submit**, không phải lúc bean `ThreadPoolTaskExecutor` được tạo.
- `previous` được phục hồi ngay cả khi task ném exception.
- Các worker tasks chạy đồng thời có bản sao MDC riêng, không dùng chung một `Map` mutable.
- Thread name `batch-chunk-...` là hỗ trợ debug, **không phải** partition name.
- Ví dụ không cấu hình rejection policy/shutdown/retry; cần sizing và graceful shutdown phù hợp workload thật.

Đoạn này dành cho task thực sự chạy qua **executor đã được trang bị decorator**. Nếu code dùng `CompletableFuture` mặc định, executor khác, scheduler, Reactor hoặc thư viện tự tạo thread, MDC cần propagation tương ứng; không tự lan sang những đường thực thi đó.

### 8.2. Gắn executor vào multi-threaded worker step

~~~java
@Bean
Step multiThreadedOrdersWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemWriter<OrderRow> writer,
        PartitionLoggingListener loggingListener,
        ThreadPoolTaskExecutor batchChunkExecutor) {

    return new StepBuilder("multiThreadedOrdersWorkerStep", jobRepository)
            .<OrderRow, OrderRow>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .listener(loggingListener)
            .taskExecutor(batchChunkExecutor)
            .build();
}
~~~

**Lưu ý về Spring Batch 5.x:** API builder và tùy chọn multi-threaded step phụ thuộc phiên bản đang dùng; kiểm tra chữ ký cụ thể trên phiên bản dự án. Hơn nữa, khi chạy multi-threaded chunks trong **cùng một `StepExecution`**, reader/writer có state phải được đánh giá thread safety và checkpoint; thêm `TaskDecorator` **chỉ giải quyết MDC**, không làm `JdbcCursorItemReader` hay `FlatFileItemReader` tự nhiên thread-safe.

### 8.3. Phân biệt executor của local partitioning

Nếu manager dùng `TaskExecutorPartitionHandler`, executor gửi **worker step tasks**. MDC tại manager thread được copy lúc submit thường **chưa có** partitionName cụ thể. Khi worker `beforeStep` chạy, listener mới biết partitionName từ `StepExecution.getExecutionContext()` và ghi MDC trên worker thread.

Nếu **bên trong worker step** còn dùng executor khác cho chunks, cần propagation tiếp từ worker step thread sang các chunk threads. Một decorator ở executor của manager **không tự bao phủ** executor nội bộ của chunk.

## 9. Remote partitioning: MDC không đi qua JVM

Trong remote partitioning, manager phân chia công việc và gửi worker `StepExecution`/request tới tiến trình khác qua middleware. MDC của manager nằm trong thread/process manager; nó **không đi cùng request qua network** chỉ vì bạn gọi `MDC.put(...)`.

~~~mermaid
flowchart LR
    M["Manager JVM<br/>MDC manager fields"] --> B["Message broker"]
    B --> W["Remote worker JVM"]
    W --> X["Nhận StepExecution/context<br/>bind MDC tại worker"]
    X --> L["Structured logs<br/>partitionName + execution IDs"]
    W --> R["Worker reply + correlation"]
    R --> M
~~~

### Nguồn context đáng tin ở remote worker

- `StepExecution.getStepName()`: tên step execution do framework cung cấp.
- `StepExecution.getExecutionContext()`: metadata partition/range/file do ứng dụng/partitioner đưa vào.
- `StepExecution.getJobExecution()`: định danh execution khi worker có metadata phù hợp.
- Message headers: `correlationId`, trace context hoặc request identity **nếu adapter tích hợp truyền qua**.
- Worker runtime: hostname/pod/container ID theo môi trường triển khai.

**Không** đọc `MDC.get("partitionName")` ở worker và mặc định nó đã được manager chuyển qua broker. Worker phải **tái tạo context** từ StepExecution/envelope thực sự nhận được, rồi dọn khi hoàn tất.

### Manager log gì? Worker log gì?

| Thành phần | Sự kiện nên log | Identity quan trọng |
| --- | --- | --- |
| **Manager** | Partition plan, request dispatched, timeout, reply received, restart decision | JobExecution, logical partition, request/correlation ID |
| **Worker** | Partition started, chunk progress, skip, rollback, partition finished | StepExecution, partitionName, source snapshot, workerId |
| **Broker adapter** | Publish failure, redelivery, reply correlation, DLQ | Message ID, correlation ID, attempt/headers |
| **JobRepository/monitoring** | Execution state và counters | JobInstance/JobExecution/StepExecution IDs |

Một **timeout ở manager** không chứng minh worker failed; worker có thể đã commit nhưng mất reply. Log nên biểu diễn `reply_timeout` hoặc `status_unknown`, không tự ghi `partition_failed` khi chưa có bằng chứng.

## 10. Phân biệt partition key, request ID và attempt khi retry/restart

Giả sử partition `partition-0007` chạy lỗi, rồi restart:

~~~text
JobInstanceId     = 100         (không đổi)
JobExecutionId    = 502         (lần chạy đầu)
StepExecutionId   = 719
partitionName     = partition-0007

JobExecutionId    = 503         (restart cùng JobInstance)
StepExecutionId   = 743
partitionName     = partition-0007 (không đổi)
~~~

Nếu truy vấn log theo `StepExecutionId=719`, bạn chỉ xem **attempt cũ**. Truy vấn theo `JobInstanceId=100 AND partitionName=partition-0007` mới giúp ghép lịch sử **logic partition** xuyên restart. Tuy nhiên, vẫn cần `sourceVersion` nếu nhiều snapshot/job sử dụng tên partition giống nhau.

### Dùng log để trả lời ba câu hỏi khác nhau

| Câu hỏi | Field nên dùng |
| --- | --- |
| “Lần chạy nào lỗi?” | `jobExecutionId` và `stepExecutionId` |
| “Partition logic nào bị ảnh hưởng xuyên restart?” | `jobInstanceId` + `partitionName` + `sourceVersion` |
| “Message/reply cụ thể nào không tới?” | `correlationId` + broker `messageId`/request ID |

**Không** sinh `correlationId` mới mỗi lần retry nếu nghiệp vụ cần nối nhiều attempts của **cùng request logic**; có thể dùng thêm `attemptId` riêng để phân biệt lần gửi. Các ID có vai trò khác nhau và cần được định nghĩa trong hợp đồng message.

## 11. Log tại read/process/write mà không làm ngập hệ thống

Trong job xử lý hàng triệu records, log mỗi item ở `INFO` có thể tốn CPU, I/O và làm ngập backend log.

### Khuyến nghị theo cấp độ

| Mức | Sự kiện | Ví dụ |
| --- | --- | --- |
| `INFO` | Khởi động/kết thúc partition, tiến độ định kỳ, tổng kết counters | `partition_started`, `partition_finished` |
| `WARN` | Item lỗi có chủ đích được skip, retry bất thường, chất lượng giảm | `item_skipped` với reasonCode |
| `ERROR` | Worker thất bại, retry exhausted, không ghi được audit, trạng thái không rõ | `partition_failed`, `external_result_unknown` |
| `DEBUG` | Thông tin chẩn đoán chi tiết ở mẫu nhỏ | Bước xử lý/chunk trace, query timing |
| `TRACE` | Debug tạm thời theo chính sách vận hành | Không bật đại trà cho data volume lớn |

**Cần phân biệt:** Một item được skip theo chính sách có thể là sự kiện `WARN` nhưng **không** làm worker `FAILED`. Ngược lại, timeout API có thể chỉ là **attempt thất bại** đang retry; không log thành sự cố `ERROR` lặp lại hàng nghìn lần khi policy còn đang xử lý.

### Log message với fields được kiểm soát

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderProcessor.class);

@Override
public OutputOrder process(InputOrder item) {
    if (item.amountMinor() <= 0) {
        log.warn("event=invalid_item sourceKey={} reasonCode={}",
                item.sourceKey(), "INVALID_AMOUNT");
        throw new InvalidOrderRecordException("Invalid amount");
    }
    return normalize(item);
}
~~~

`InputOrder`, `OutputOrder`, `normalize`, `InvalidOrderRecordException` và imports là các thành phần ví dụ; đoạn này không phải class hoàn chỉnh. Trong production, nếu item cuối cùng được **retry/skip**, log WARN ngay trong processor có thể xuất hiện **nhiều lần cho cùng item**. Vì vậy **log phát hiện validation attempt** và **log item thực sự được skip** phải mang event names khác nhau.

### Khi nào log item_skipped?

`SkipListener` có callback `onSkipInRead`, `onSkipInProcess` và `onSkipInWrite`. Chúng phản ánh quyết định skip của fault-tolerant step (theo lifecycle của framework), khác với mọi lần exception xuất hiện.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.batch.core.SkipListener;
import org.springframework.batch.item.file.FlatFileParseException;

public final class OrderSkipLogListener
        implements SkipListener<InputOrder, OutputOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderSkipLogListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        if (error instanceof FlatFileParseException parsed) {
            log.warn(
                "event=item_skipped phase=READ lineNumber={} errorCode={}",
                parsed.getLineNumber(), "CSV_PARSE_ERROR");
        } else {
            log.warn("event=item_skipped phase=READ errorCode={} "
                    + "sourcePositionKnown=false",
                    "UNIDENTIFIED_READ_ERROR");
        }
    }

    @Override
    public void onSkipInProcess(InputOrder item, Throwable error) {
        log.warn("event=item_skipped phase=PROCESS "
                + "sourceKey={} errorCode={}",
                item.sourceKey(), "INVALID_ORDER");
    }

    @Override
    public void onSkipInWrite(OutputOrder item, Throwable error) {
        log.warn("event=item_skipped phase=WRITE "
                + "sourceKey={} exceptionType={}",
                item.sourceKey(), error.getClass().getSimpleName());
    }
}
~~~

**Không xem log này là quarantine bền vững.** Với read skip, framework không truyền item nên `sourceKey` có thể chưa xác định; muốn sửa/replay cần lưu file + logical record position trong **durable audit/quarantine** thích hợp. Code ở trên **không nên được dùng để tự động nuốt mọi lỗi hạ tầng**: chỉ loại exception đã được policy cho skip mới kích hoạt các callback khi framework xác nhận skip.

### Đếm đúng thay vì log mỗi record

- Counter của `StepExecution` cho biết read/write/skip/rollback của **execution**.
- Metric aggregation cho biết tỷ lệ lỗi, latency và throughput theo job/partition group.
- Durable quarantine cho biết **item nguồn nào** thực sự cần sửa.
- Log dùng để nối các sự kiện và nguyên nhân trong thời gian vận hành.

Ba nguồn này bổ sung nhau; **số dòng log WARN không bằng số item lỗi duy nhất**, đặc biệt sau rollback/restart.

## 12. Log chunk progress đúng ranh giới commit

`ItemWriter.write(...)` được gọi trong quá trình chunk và có thể được gọi lại sau rollback. Do đó:

~~~java
// Không nên khẳng định đã commit chỉ vì writer vừa chạy:
log.info("event=chunk_committed");
~~~

Log trong writer nên dùng tên sự kiện đúng như `write_attempted` hoặc `writer_completed`, vì transaction có thể **rollback sau đó**.

### ChunkListener.afterChunk

Trong chunk-oriented step chuẩn, `afterChunk` chạy sau khi **chunk transaction hoàn tất thành công**. Đây là nơi phù hợp để log một sự kiện `chunk_committed`, với caveat về transaction manager:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;

public final class ChunkProgressLogListener
        implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ChunkProgressLogListener.class);

    @Override
    public void afterChunk(ChunkContext context) {
        var step = context.getStepContext().getStepExecution();
        log.info("event=chunk_committed "
                + "commitCount={} readCount={} writeCount={} "
                + "skipCount={}",
                step.getCommitCount(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getSkipCount());
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        var step = context.getStepContext().getStepExecution();
        log.warn("event=chunk_rollback_or_error stepExecutionId={} "
                + "rollbackCount={}",
                step.getId(), step.getRollbackCount());
    }
}
~~~

Các counters trong `StepExecution` là **tích lũy theo execution**, không phải số item riêng của chunk vừa commit. Đừng dùng một dòng `afterChunk` để kết luận mọi HTTP/Kafka side effects đã commit atomically với database.

Nếu log mỗi chunk ở `INFO` tạo quá nhiều sự kiện, có thể log **định kỳ theo thời gian**, mỗi N chunks hoặc chuyển tóm tắt sang metric. Mọi cách sampling phải tránh làm mất **các sự kiện lỗi nghiêm trọng**.

## 13. Log lỗi hệ thống mà không nhầm với item bị skip

Một lỗi DB/network có thể xảy ra ở 50 workers cùng lúc. Nếu mỗi worker log toàn bộ stack trace cho mọi retry attempt, backend logging dễ quá tải, làm chậm recovery và che mất root cause.

### Tách attempt, exhausted và failure

| Event | Ý nghĩa | Log level gợi ý |
| --- | --- | --- |
| `retry_scheduled` | Sẽ thử lại exception retryable | `DEBUG` hoặc aggregate metric |
| `retry_exhausted` | Đã hết budget cho operation | `WARN/ERROR` theo mức ảnh hưởng |
| `partition_failed` | Worker StepExecution không hoàn tất | `ERROR` với exception/counters |
| `reply_timeout` | Manager chưa nhận phản hồi từ worker | `WARN`; **không** kết luận worker chưa commit |
| `reconciliation_needed` | External effect ở trạng thái chưa xác nhận | `ERROR` hoặc alert nghiệp vụ |
| `partition_finished` | Worker step kết thúc với status/ExitStatus cụ thể | `INFO` hoặc `ERROR` nếu FAILED |

Khi sự cố diện rộng, nên dùng **reasonCode chuẩn**, rate limit hoặc sampling cho những sự kiện lặp và giữ **một vài stack trace đầy đủ** cho nguyên nhân gốc. Không sampling mù các record audit bắt buộc.

### Không log sai thời điểm

Một log `"write succeeded"` ở cuối `ItemWriter.write` chỉ chứng minh method đã trả về, **không** chứng minh transaction commit. `"message sent"` chỉ chứng minh producer client đã nhận một kết quả, không nhất thiết consumer downstream đã xử lý. Tên event phải thể hiện mốc có thật:

~~~text
writer_returned
chunk_committed
outbox_event_persisted
broker_publish_acknowledged
downstream_operation_confirmed
~~~

## 14. Log trong local partitioning và parallel steps

### Local partitioning

Nhiều worker step chạy trong **một JVM**, có thể chung logging backend nhưng khác threads. Một singleton `PartitionLoggingListener` **không giữ mutable currentPartition** có thể an toàn khi bind MDC ngay trên worker thread; tuy nhiên mọi component dùng chung state vẫn cần kiểm tra thread safety.

Nếu listener để field `String currentPartitionName` rồi `beforeStep` ghi vào đó, Worker B có thể ghi đè context của Worker A. Tránh:

~~~java
// Anti-pattern:
private String currentPartitionName; // Singleton mutable!

public void beforeStep(StepExecution step) {
    currentPartitionName = step.getStepName();
}
~~~

Dùng StepExecution/ExecutionContext tại thời điểm event, MDC ở thread hiện hành với cleanup, hoặc `@StepScope` để lấy metadata bất biến từng worker. `@StepScope` không có nghĩa thread-safety tự động cho **multi-threaded chunks cùng StepExecution**.

### Parallel steps

Khi chạy hai flows/steps song song, cả hai có thể có cùng `partitionName` dạng `partition-0001` nếu mỗi step có partitioner riêng. Vì thế, **partitionName một mình chưa phải global identifier**; log phải đi cùng `jobInstanceId`, `stepName` hoặc ít nhất manager/worker step identity.

~~~text
job=ordersImport step=ordersWorkerA:partition-0001
job=ordersImport step=ordersWorkerB:partition-0001
~~~

Hai phần việc trên khác nhau dù partition key giống nhau.

## 15. Quan sát rollback, restart và item replay

Một worker có thể `FAILED` sau khi nhiều chunks đã commit. Khi restart, `JobExecutionId` và `StepExecutionId` mới; cùng logical partition được tiếp tục theo checkpoint khi cấu hình restart hợp lệ.

### Sự kiện nên có

~~~text
event=partition_started jobInstanceId=100
  jobExecutionId=502 stepExecutionId=719
  partitionName=partition-0007

event=chunk_rollback stepExecutionId=719
  errorCode=DB_TIMEOUT

event=partition_finished jobExecutionId=502
  stepExecutionId=719 status=FAILED

event=partition_started jobInstanceId=100
  jobExecutionId=503 stepExecutionId=743
  partitionName=partition-0007

event=partition_finished jobExecutionId=503
  stepExecutionId=743 status=COMPLETED
~~~

Đây là mẫu lifecycle log **giả định**; nếu process bị kill, dòng `partition_finished` có thể không tồn tại. Khi đó `JobRepository`, worker heartbeat, container lifecycle và broker state là những nguồn bổ sung cần đối chiếu.

### Dùng metadata thay vì đoán từ log

`StepExecution` có counters/status, `ExecutionContext` giữ checkpoint. Log có thể bị mất hoặc gửi lặp nếu collector lỗi. Không dùng số dòng `chunk_committed` làm sổ cái chính xác cho số business records đã commit; đối soát với `JobRepository` và hệ thống đích.

Đặc biệt, nếu writer dùng upsert/idempotent no-op khi replay, `writeCount` của framework **không nhất thiết bằng số hàng mới** ở database. Log chỉ giúp hiểu đường chạy, không thay thế unique business key.

## 16. Bảo vệ dữ liệu nhạy cảm và chi phí log

Logging là một kênh dữ liệu có retention, quyền truy cập và khả năng xuất ra bên ngoài. Khi tăng số worker, một lỗi lập trình log toàn item có thể nhân lượng dữ liệu nhạy cảm lên nhiều lần.

### Không nên log

- Mật khẩu, token, credential, session cookie, header `Authorization`.
- Số thẻ, dữ liệu tài khoản nhạy cảm, tên/ngày sinh/địa chỉ đầy đủ, raw record chứa PII.
- Full exception message của client/SQL nếu có thể chứa secret hoặc SQL parameters nhạy cảm.
- Payload lớn của mỗi message/chunk hoặc toàn bộ `ExecutionContext`.

### Thay bằng gì?

- `sourceKey` **được phép log** theo chính sách và không chứa PII trực tiếp; nếu nhạy cảm, dùng token/hash có quản lý.
- `errorCode` có danh mục, `exceptionType`, phase và partition.
- `fileId`/`sourceVersion` hoặc stable range ID để tra record qua kho audit được phân quyền.
- Thống kê lỗi theo nhóm, kèm một sample đủ để điều tra thay vì dump dữ liệu.

**MDC chỉ là metadata, nhưng vẫn có thể chứa dữ liệu nhạy cảm.** Đừng đưa tenant names/email/customer IDs vào MDC nếu log backend có phạm vi truy cập rộng; chọn mã nội bộ theo policy.

### Cardinality trong log và metrics

Log backend thường cho phép tìm theo nhiều trường có cardinality cao, nhưng index/storage của `stepExecutionId` hoặc source IDs vẫn tốn chi phí. Với **metrics time series**, tránh dùng `sourceKey`, `stepExecutionId` hoặc từng partition ID không giới hạn làm labels vì có thể sinh hàng triệu series.

Một cách phân tầng:

| Dữ liệu | Nơi lưu |
| --- | --- |
| Log event có job/partition/execution IDs | Centralized logs với retention có kiểm soát |
| Throughput, latency, error rate | Metrics với label cardinality thấp |
| Một operation/item lỗi cần replay | Durable audit/quarantine/ledger |
| Quan hệ request qua nhiều service | Distributed tracing khi có propagation thật |

## 17. Liên kết logging với metrics và tracing

Không nên biến một tool thành nguồn chân lý cho mọi câu hỏi:

~~~mermaid
flowchart TB
    W["Worker StepExecution"] --> L["Structured logs<br/>partitionName + errorCode"]
    W --> M["Metrics<br/>throughput, lag, rollback"]
    W --> T["Traces<br/>request/span correlation"]
    W --> J[("JobRepository<br/>status, counters, context")]
    W --> B[("Business output / audit")]
    L --> I["Incident investigation"]
    M --> I
    T --> I
    J --> I
    B --> I
~~~

### Gắn trace context thế nào?

Nếu dùng Micrometer Tracing/OpenTelemetry với Spring Boot phiên bản phù hợp, `traceId`/`spanId` có thể được thêm tự động hoặc qua logging configuration. Nhưng để trace đi qua **manager → broker → remote worker → downstream API**, cần instrumentation và **context propagation qua message headers** thực sự được hỗ trợ/cấu hình.

**Không** giả định manager và remote worker sẽ có cùng trace ID nếu chỉ bật tracing dependency. Trong một số hệ thống, mỗi attempt/worker có span/trace riêng và liên hệ với request gốc qua link/correlation ID. Cần thiết kế cách nối log theo **job/partition identities** ngay cả khi không có distributed trace liên tục.

### Metrics quan trọng

| Metric / tín hiệu | Mục đích |
| --- | --- |
| Worker active/completed/failed | Theo dõi phân tán và tiến độ |
| Read/write items per second | Throughput theo job/step |
| Chunk commit/rollback rate | Phát hiện lỗi transaction hoặc retry storm |
| `readSkipCount` / `processSkipCount` / `writeSkipCount` | Phân loại lỗi dữ liệu |
| Retry attempts và exhausted | Đo sự cố ngoài transaction |
| Broker request/reply latency, redelivery, DLQ depth | Định vị lỗi remote |
| CPU, heap, connection pool, queue depth | Đo bottleneck thực |
| Reconciliation mismatch và quarantine backlog | Chất lượng và tiến độ khắc phục |

Đừng cộng manager counters và worker counters một cách mù để báo số records duy nhất. Sử dụng `JobRepository` đúng semantics của partitioning và business output cho kết quả cuối.

## 18. Kiểm thử MDC và log context

Một bài test log tốt không chỉ kiểm tra “có log”. Nó cần chứng minh **đúng partition**, **đúng attempt** và **không rò context**.

### 18.1. Unit test listener với StepExecution

Spring Batch Test cung cấp `MetaDataInstanceFactory` để tạo metadata phục vụ test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

class PartitionLoggingListenerTest {

    @Test
    void bindsVaDonMdcTheoPartition() {
        StepExecution step =
                MetaDataInstanceFactory.createStepExecution();
        step.getExecutionContext().putString(
                "partitionName", "partition-0007");
        step.getExecutionContext().putString(
                "sourceVersion", "snapshot-v1");

        PartitionLoggingListener listener =
                new PartitionLoggingListener();

        try {
            listener.beforeStep(step);
            assertEquals(
                "partition-0007", MDC.get("partitionName"));
            assertEquals(
                String.valueOf(step.getId()),
                MDC.get("stepExecutionId"));
            assertEquals(
                "snapshot-v1", MDC.get("sourceVersion"));
        } finally {
            listener.afterStep(step);
        }

        assertNull(MDC.get("partitionName"));
        assertNull(MDC.get("stepExecutionId"));
    }
}
~~~

Ví dụ dùng JUnit 5, `spring-batch-test` và backend SLF4J MDC phù hợp. Test này xác nhận **thread hiện tại**, chưa xác nhận propagation đến executor threads hoặc log encoder thực sự xuất fields.

### 18.2. Test TaskDecorator không làm rò context

Kịch bản tối thiểu:

1. Thread A đặt `partitionName=partition-0001`, submit task qua **decorated executor**.
2. Thread B đặt `partitionName=partition-0002`, submit task cùng executor.
3. Mỗi task dùng `MDC.get("partitionName")` và trả lại kết quả.
4. Assert task A nhìn `0001`, task B nhìn `0002`.
5. Submit task tiếp theo **không có MDC**, assert context không mang tên partition cũ.
6. Gây exception trong task rồi submit lại, assert `finally` đã cleanup.

Phải chạy test với **thread pool thực sự** và pool size nhỏ để ép tái sử dụng threads. Tránh một `new Thread()` riêng cho mỗi task: nó không kiểm tra được leak qua thread pool.

### 18.3. Test log encoder và schema

Kiểm tra một `partition_started` log chứa:

~~~text
jobName
jobInstanceId
jobExecutionId
stepExecutionId
stepName
partitionName
sourceVersion (nếu được cung cấp)
event
timestamp / level
~~~

Nếu dùng JSON logging, parse record và assert fields, không so khớp chuỗi log đầy đủ phụ thuộc timestamp/thread. Nếu dùng Logback test appender, test cũng cần kiểm tra **MDC snapshot gắn với logging event**, không lấy MDC từ test thread sau khi sự kiện đã kết thúc.

### 18.4. Test manager/worker remote

| Kịch bản | Điều phải chứng minh |
| --- | --- |
| Manager gửi request partition 0007 | Worker nhận đúng partition context |
| Remote worker khác JVM | Log worker có partitionName dù manager MDC không được chia sẻ |
| Broker redelivery | Request được nối đúng correlation và business key |
| Worker crash rồi restart | Same partitionName, **new execution IDs** |
| Reply đến trễ | Log thể hiện attempt/correlation; không tuyên bố worker thất bại khi trạng thái chưa rõ |
| Hai partitions chạy cùng pod | Không trộn MDC/ExecutionContext |
| Hai chunk threads dùng cùng StepExecution | Mỗi thread nhận context đúng mà không làm reader stateful trở nên unsafe |
| Thread pool tái sử dụng | Không giữ partitionName của task trước |
| Log broker không có partition | Không tự điền “last partition” từ singleton mutable |
| JobRepository unavailable | Log vẫn cho phép điều tra ID đã biết, không coi log là checkpoint |

### 18.5. Test restart có dữ liệu

Chạy một partition cho vài chunks commit, gây lỗi rồi restart cùng `JobInstance`:

- Kiểm tra hai `JobExecutionId` khác nhau nhưng **cùng logical partitionName**.
- Đối chiếu `StepExecution` status và checkpoint với log lifecycle.
- Không đếm số lần `partition_started` là số business record đã ghi.
- Kiểm tra writer dùng idempotency key ổn định để replay không tạo output trùng.
- Nếu worker bị kill cứng, test phải chấp nhận **không có log partition_finished** và dùng metadata/heartbeat để phát hiện.

## 19. Truy vấn và dashboard phục vụ sự cố

### Tình huống A: Một file chậm bất thường

Tìm các `partition_started`/`partition_finished` cùng `fileId` và tính thời gian xử lý; đối chiếu `readCount`/`writeCount`, throughput, DB lock wait và input size. Có thể partition bị skew vì file lớn hơn các file còn lại, không hẳn thread pool thiếu.

### Tình huống B: Worker thất bại khi DB timeout

1. Lọc `jobExecutionId` và `partitionName` trong thời gian lỗi.
2. Xem `chunk_rollback`, `retry_exhausted`, `partition_finished` nếu có.
3. Đối chiếu `JobRepository` cho `FAILED` StepExecution và số chunk commit.
4. Kiểm tra datasource pool, DB failover và lock wait.
5. Khôi phục dependency rồi restart phần việc cần thiết; **không skip lỗi DB** chỉ để job hoàn tất.

### Tình huống C: Remote reply timeout

Không kết luận “worker không làm gì” chỉ vì manager log `reply_timeout`. Tìm cùng `correlationId` tại worker, đối chiếu business output/operation IDs và `StepExecution`. Worker có thể đã commit nhưng reply mất. Replay phải bảo đảm idempotency.

### Tình huống D: Skip tăng theo partition

Nhóm `item_skipped` theo `partitionName`/`errorCode` và so với số input tương ứng. Nếu chỉ 1 tenant/file có tỷ lệ lỗi cao, tổng lỗi toàn job có thể che mất vấn đề cục bộ. Dữ liệu để sửa/replay vẫn phải lấy từ **quarantine**, không từ chuỗi log bị sampling.

## 20. Runbook: kiểm tra log partition khi production chậm hoặc lỗi

1. **Chốt identity:** JobInstance, JobExecution, manager step, worker step, partitionName, source snapshot/file/range.
2. **Xác minh phạm vi:** Có bao nhiêu worker đang active, `COMPLETED`, `FAILED` hoặc `STOPPED`? Có worker cũ chưa thoát không?
3. **Kiểm tra context:** Log có đúng partitionName và workerId hay bị trống/lẫn? MDC có được truyền qua executor/broker đúng cách không?
4. **So khớp metadata:** Từ `JobRepository` lấy status, counters và `ExecutionContext`; không suy luận từ log text đơn lẻ.
5. **Định vị bottleneck:** CPU, DB pool, lock wait, broker latency, chunk rollback, file skew và executor queue.
6. **Phân loại lỗi:** Data validation (có thể skip) khác DB/network timeout (retry/fail/reconcile).
7. **Kiểm tra side effect:** Có chunk commit nhưng manager chưa nhận reply? Business operation có unique key không?
8. **Giảm log noise:** Dùng summary event/metrics, kiểm tra sampling và tránh stack trace lặp quá mức.
9. **Khôi phục có kiểm soát:** Restart đúng `JobInstance`/partition, giữ partition mapping và snapshot; không sửa JobRepository metadata tùy tiện.
10. **Đối soát trước publish:** Input keys, output unique IDs, skip/filter/quarantine, pending/unknown và trạng thái hệ thống đích.
11. **Bổ sung test:** Reproduce context leak, executor reuse, reply loss hoặc crash window vừa gặp.

### Checklist triển khai

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Logical partition key | Được cấp từ `Partitioner`, ổn định qua restart |
| Step metadata | Log phân biệt JobInstance, JobExecution, StepExecution |
| MDC lifecycle | Bind trên worker thread, cleanup sau step/task |
| Executor propagation | Có `TaskDecorator` hoặc cơ chế tương đương cho đúng executor |
| Remote propagation | Worker tái tạo identity từ StepExecution/message, không dựa vào manager MDC |
| Structured log | `partitionName`, `event`, `status`, `errorCode` truy vấn được |
| Log semantics | Không coi writer return là commit, manager timeout là worker failed |
| Volume và PII | Không log payload nhạy cảm; sampling/retention hợp lý |
| Reconciliation | `JobRepository` và business ledger là nguồn kiểm chứng |
| Test | Concurrency, thread reuse, remote redelivery, restart có đủ |

## 21. Bài tập tình huống

Job xử lý **8 triệu records**, manager tạo 16 partitions bằng `TaskExecutorPartitionHandler`. Worker step lại chạy **multi-threaded chunks** trên một `ThreadPoolTaskExecutor` khác. Team thêm một singleton listener:

~~~java
private String currentPartition;

public void beforeStep(StepExecution step) {
    currentPartition = step.getStepName();
    MDC.put("partitionName", currentPartition);
}
~~~

Sau vài giờ, dashboard xuất hiện các biểu hiện:

- Log `partition_started` có tên đúng, nhưng log trong processor **không có** partitionName.
- Một số log processor mang partitionName của **worker trước** trên cùng thread pool.
- Manager báo timeout cho `partition-0005`, trong khi worker sau đó ghi `COMPLETED`.
- Khi restart, `StepExecutionId` thay đổi nên query log theo ID cũ không tìm thấy attempts mới.
- Hệ thống bật `DEBUG` cho mọi item và volume log tăng mạnh, khiến throughput giảm.

**Câu hỏi:**

1. Vì sao mutable singleton `currentPartition` có thể gây cross-talk?
2. Vì sao `beforeStep` đã gọi `MDC.put` mà processor trên chunk threads vẫn thiếu partitionName?
3. `TaskDecorator` cần được gắn lên executor nào trong kiến trúc này?
4. Trong `finally` của decorator phải phục hồi những gì?
5. Vì sao không thể kết luận worker failed chỉ từ manager reply timeout?
6. Cần dùng ID nào để nối lịch sử một logical partition xuyên restart?
7. Làm sao giảm log volume mà vẫn giữ bằng chứng lỗi và khả năng đối soát?

**Định hướng trả lời:** Không giữ partition state trong field mutable của singleton. Bind từ `StepExecution/ExecutionContext` vào MDC theo worker và dọn context khi kết thúc; dùng `TaskDecorator` của **chunk executor** để copy/restoring MDC cho thread pool, ngoài decorator ở manager nếu cần. Remote worker phải tái tạo context từ metadata/message. Timeout có thể xảy ra sau worker commit nên phải kiểm tra `JobRepository`, correlation và business output. Dùng `jobInstanceId + logical partitionName (+ sourceVersion)` để nối các attempts, còn `stepExecutionId` dùng cho một execution cụ thể. Log tóm tắt per partition/chunk, metric throughput/error-rate và durable quarantine thay cho dump tất cả items.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps và partitioning.
- [Spring Batch Reference — Partitioning](https://docs.spring.io/spring-batch/reference/scalability.html#partitioning): `Partitioner`, `ExecutionContext`, `PartitionHandler` và worker `StepExecution`.
- [Spring Batch Reference — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): `StepExecutionListener`, `ChunkListener` và `SkipListener`.
- [Spring Batch Reference — JobRepository and Metadata](https://docs.spring.io/spring-batch/reference/schema-appendix.html): JobExecution/StepExecution/counters.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint và restart.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): messaging/correlation trong remote processing.
- [SLF4J Manual — MDC](https://www.slf4j.org/manual.html): logging API và diagnostic context.
- [Logback Manual — MDC](https://logback.qos.ch/manual/mdc.html): `MDC`, cấu hình `%X{}` và thread-local behavior.
- [Spring Framework API — TaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskDecorator.html): hook trang bị context cho executor task.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor` và thread pools.
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/): tracing/correlation ID theo instrumentation.

> **Ghi nhớ:** Log theo partition name hiệu quả khi **partition key là logical identity ổn định**, có đủ JobInstance/JobExecution/StepExecution context và được **bind/propagate/cleanup đúng thread/process boundary**. Với Spring Batch song song hoặc phân tán, hãy kết hợp structured logs, `JobRepository`, metrics/tracing và business reconciliation để thấy cả tiến độ lẫn tính đúng — không dựa vào MDC, tên thread hay số dòng log như nguồn chân lý duy nhất.

# Log theo JobExecution ID

## 1. Vì sao log phải gắn với `JobExecution ID`?

Một hệ thống Spring Batch có thể chạy hàng chục job đồng thời. Cùng một job cũng có thể chạy nhiều lần: lần đầu thất bại, lần sau được restart, hoặc xử lý lô dữ liệu mới. Khi log chỉ ghi `jobName` hay thông báo “Import started”, người vận hành khó phân biệt dòng log nào thuộc lần thực thi nào.

Trong chương **Observability** của module **SPRING_BATCH_SCALING_OPERATIONS**, mục tiêu là **liên kết từng dòng log với `JobExecution ID`** để quan sát, chẩn đoán và khôi phục job dữ liệu lớn. Chủ đề này hỗ trợ những kiến trúc multi-threaded step, parallel steps, partitioning và phân tán, nơi log đến từ nhiều luồng hoặc nhiều tiến trình. Nó cũng giúp tìm nút thắt, phát hiện lỗi thread safety, đánh giá retry/restart và điều chỉnh tài nguyên theo tình trạng thực tế.

Ví dụ một job `dailyOrdersImport` gặp deadlock trên worker thứ ba:

~~~text
2026-11-26 09:00:01 INFO  jobExecutionId=2401 stepExecutionId=6801 stepName=ordersWorkerStep:part0 - Đọc 1000 dòng
2026-11-26 09:00:01 INFO  jobExecutionId=2401 stepExecutionId=6802 stepName=ordersWorkerStep:part1 - Đọc 1000 dòng
2026-11-26 09:00:02 ERROR jobExecutionId=2401 stepExecutionId=6803 stepName=ordersWorkerStep:part2 - Ghi dữ liệu thất bại: deadlock
2026-11-26 09:01:20 INFO  jobExecutionId=2402 stepExecutionId=6812 stepName=ordersWorkerStep:part2 - Restart partition lỗi
~~~

Các ID trên chỉ là ví dụ. `2401` và `2402` là **hai `JobExecution` khác nhau**; nếu `2402` restart lần chạy `2401` thì cả hai thuộc cùng một `JobInstance`. Vì vậy, log hữu ích thường chứa thêm `jobInstanceId` để nối lịch sử nhiều lần restart.

## 2. Phân biệt các mã định danh để không truy sai

| Trường | Dùng để nhận diện | Thay đổi khi restart? |
|---|---|---|
| `jobName` | Định nghĩa job, ví dụ `dailyOrdersImport` | Không, nếu giữ nguyên định nghĩa |
| `jobInstanceId` | Một `JobInstance`: `jobName` và các **identifying JobParameters** | **Không**, nếu restart đúng instance |
| `jobExecutionId` | Một lần cố gắng chạy `JobInstance` | **Có**, mỗi `JobExecution` mới có ID mới |
| `stepExecutionId` | Một lần thực thi cụ thể của một step hoặc partition | **Có**, khi tạo `StepExecution` mới |
| `stepName` | Step hoặc partition, ví dụ `ordersWorkerStep:part2` | Thường giữ nguyên giữa các lần restart |
| `batchId` / `businessDate` | Lô nghiệp vụ do ứng dụng định nghĩa | Phụ thuộc tham số; không thay thế metadata ID |
| `traceId` | Một trace phân tán (khi có hệ thống tracing) | Có quy tắc riêng; không mặc nhiên bằng JobExecution ID |

Ba câu hỏi vận hành khác nhau dẫn đến ba kiểu tìm kiếm:

- “Lần chạy nào thất bại?” → tra **`jobExecutionId`**.
- “Các lần restart của cùng lô nằm ở đâu?” → tra **`jobInstanceId`** rồi đối chiếu từng `jobExecutionId`.
- “Partition nào thất bại trong lần chạy đó?” → lọc thêm **`stepExecutionId`** và **`stepName`**.

**Không lấy `JobParameters.run.id` làm `JobExecution ID`.** `run.id` chỉ là một tham số có thể được `RunIdIncrementer` thay đổi để tạo instance mới; nó không đại diện cho ID do JobRepository cấp.

## 3. Cách làm: Structured Logging với SLF4J MDC

SLF4J **MDC (Mapped Diagnostic Context)** cho phép gắn cặp `key=value` vào ngữ cảnh log trên **luồng hiện tại**. Khi hệ thống dùng Logback, mỗi log event có thể được format với `jobExecutionId`, `jobInstanceId`, `stepExecutionId` và `stepName`.

~~~mermaid
flowchart LR
    A["JobRepository cấp JobExecution.id"] --> B["JobExecutionListener"]
    B --> C["MDC: jobExecutionId / jobInstanceId"]
    C --> D["Job / Step logs"]
    D --> E["Logback console hoặc JSON logs"]
    E --> F["Log collector / query theo ID"]
    A --> G["BATCH_JOB_EXECUTION"]
    G --> H["BATCH_STEP_EXECUTION"]
    F --> I["Đối chiếu log với metadata"]
    H --> I
~~~

MDC hữu ích khi logger tự thêm ID vào mọi dòng trong phạm vi một luồng. Tuy nhiên, **MDC không tự lan truyền an toàn qua thread pool, message queue hay JVM khác**. Vì vậy cần tách cách xử lý cho job thông thường và job thực thi song song.

### 3.1. Cấu hình Logback hiển thị ID

Với ứng dụng Spring Boot dùng Logback, có thể đặt trong `src/main/resources/logback-spring.xml`:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] jobExecutionId=%X{jobExecutionId:-na} jobInstanceId=%X{jobInstanceId:-na} stepExecutionId=%X{stepExecutionId:-na} stepName=%X{stepName:-na} %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

`%X{jobExecutionId:-na}` lấy giá trị MDC theo khóa, dùng `na` khi không có context. Log bên ngoài vòng đời Batch (ví dụ log khởi động ứng dụng) có thể không có `jobExecutionId`; điều này là bình thường.

Trong production, nên dùng **log có cấu trúc dạng JSON** với những trường ID riêng để hệ thống tập trung log lọc chính xác bằng trường, thay vì chỉ tìm chuỗi tự do. Có thể cấu hình JSON encoder theo thư viện logging ứng dụng sử dụng; không nên phụ thuộc tuyệt đối vào một pattern console.

### 3.2. Gắn `JobExecution ID` bằng listener

Đoạn Java dưới đây minh họa **Spring Batch 5.x / Java 17**, với `JobRepository` và `PlatformTransactionManager` được cấu hình sẵn. Listener của job thiết lập MDC ngay sau khi JobRepository đã tạo execution; listener của step bổ sung các ID riêng cho step.

~~~java
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class BatchLogCorrelationConfiguration {

    @Bean
    public Job demoImportJob(
            JobRepository jobRepository,
            @Qualifier("demoImportStep") Step step,
            JobLogMdcListener jobLogMdcListener) {

        return new JobBuilder("demoImportJob", jobRepository)
                .listener(jobLogMdcListener)
                .start(step)
                .build();
    }

    @Bean
    public Step demoImportStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            StepLogMdcListener stepLogMdcListener) {

        return new StepBuilder("demoImportStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    LoggerFactory.getLogger("batch.orders")
                            .info("Đang xử lý lô đơn hàng");
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .listener(stepLogMdcListener)
                .build();
    }

    @Bean
    public JobLogMdcListener jobLogMdcListener() {
        return new JobLogMdcListener();
    }

    @Bean
    public StepLogMdcListener stepLogMdcListener() {
        return new StepLogMdcListener();
    }

    static void restoreMdc(Map<String, String> previous) {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }

    public static final class JobLogMdcListener
            implements JobExecutionListener {

        private static final Logger log =
                LoggerFactory.getLogger(JobLogMdcListener.class);
        private final ThreadLocal<Map<String, String>> previousContext =
                new ThreadLocal<>();

        @Override
        public void beforeJob(JobExecution execution) {
            previousContext.set(MDC.getCopyOfContextMap());
            MDC.put("jobExecutionId", String.valueOf(execution.getId()));
            MDC.put("jobInstanceId",
                    String.valueOf(execution.getJobInstance().getId()));

            log.info("Job bắt đầu: jobName={}",
                    execution.getJobInstance().getJobName());
        }

        @Override
        public void afterJob(JobExecution execution) {
            try {
                log.info("Job kết thúc: status={} exitCode={}",
                        execution.getStatus(),
                        execution.getExitStatus().getExitCode());
            } finally {
                restoreMdc(previousContext.get());
                previousContext.remove();
            }
        }
    }

    public static final class StepLogMdcListener
            implements StepExecutionListener {

        private static final Logger log =
                LoggerFactory.getLogger(StepLogMdcListener.class);
        private final ThreadLocal<Map<String, String>> previousContext =
                new ThreadLocal<>();

        @Override
        public void beforeStep(StepExecution execution) {
            previousContext.set(MDC.getCopyOfContextMap());

            JobExecution jobExecution = execution.getJobExecution();
            MDC.put("jobExecutionId",
                    String.valueOf(jobExecution.getId()));
            MDC.put("jobInstanceId",
                    String.valueOf(jobExecution.getJobInstance().getId()));
            MDC.put("stepExecutionId",
                    String.valueOf(execution.getId()));
            MDC.put("stepName", execution.getStepName());

            log.info("Step bắt đầu");
        }

        @Override
        public ExitStatus afterStep(StepExecution execution) {
            try {
                log.info(
                        "Step kết thúc: status={} readCount={} writeCount={} " +
                        "readSkipCount={} processSkipCount={} writeSkipCount={} " +
                        "rollbackCount={}",
                        execution.getStatus(),
                        execution.getReadCount(),
                        execution.getWriteCount(),
                        execution.getReadSkipCount(),
                        execution.getProcessSkipCount(),
                        execution.getWriteSkipCount(),
                        execution.getRollbackCount());
            } finally {
                restoreMdc(previousContext.get());
                previousContext.remove();
            }

            // null: giữ nguyên ExitStatus hiện có của step.
            return null;
        }
    }
}
~~~

**Vì sao thiết kế theo cách này?**

1. `beforeJob` lấy ID **thật** từ `JobExecution`, không tự tạo UUID và không nhầm với `JobParameters`.
2. `beforeStep` lấy ID từ `StepExecution.getJobExecution()`, nhờ đó step chạy trên một luồng khác vẫn có thể tái lập ngữ cảnh logging **khi listener được gọi trên luồng thực thi step**.
3. `afterJob` / `afterStep` ghi trạng thái và bộ đếm tổng kết trước khi gỡ MDC.
4. `ThreadLocal` giữ bản sao MDC đã có trước listener; `restoreMdc` phục hồi ngữ cảnh thay vì xóa nhầm các khóa logging của hệ thống.
5. Với listener hoạt động trên luồng thực thi thông thường của Spring Batch, `before...` và `after...` tạo cặp mở/đóng hợp lý. Nếu ứng dụng tự chuyển việc thực thi sang luồng khác ở giữa, phải quản lý context tại ranh giới luồng; không được mặc nhiên dựa vào ThreadLocal.

Đây là ví dụ về **Tasklet step chạy đồng bộ**. Đối với chunk step, cách gắn listener tương tự, còn `readCount` / `writeCount` phản ánh khối lượng xử lý thực tế.

### 3.3. Gắn listener vào step chunk đang có

Nếu ứng dụng đã có reader, processor và writer, chỉ cần bổ sung listener:

~~~java
return new StepBuilder("ordersStep", jobRepository)
        .<Order, Order>chunk(500, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .listener(stepLogMdcListener)
        .build();
~~~

`Order`, `reader`, `processor` và `writer` là các thành phần nghiệp vụ đang tồn tại; không cần đổi cơ chế đọc/ghi để bổ sung log correlation.

## 4. MDC và xử lý song song: chỗ dễ mất `jobExecutionId` nhất

### 4.1. Thread pool không tự kế thừa MDC

MDC phổ biến trong SLF4J/Logback sử dụng **ThreadLocal**. Nếu job chạy trên `batch-thread-1` rồi gửi task sang `batch-thread-2`, task mới có thể ghi:

~~~text
jobExecutionId=na stepExecutionId=na ... Đã ghi 500 bản ghi
~~~

Nguyên nhân không nhất thiết là JobRepository thiếu metadata. Ngữ cảnh logging của luồng cha **không được tự động chuyển sang worker**. Khi thread pool tái sử dụng luồng, MDC cũ còn sót lại cũng có thể khiến log của job A bị gán nhầm cho job B.

Với `ThreadPoolTaskExecutor` của Spring, có thể dùng `TaskDecorator` để chụp MDC ngay lúc submit task, truyền vào luồng nhận, rồi **phục hồi** context trước đó trong `finally`:

~~~java
import java.util.Map;

import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class BatchExecutorConfiguration {

    @Bean
    public ThreadPoolTaskExecutor batchTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("batch-");

        executor.setTaskDecorator(task -> {
            Map<String, String> submittingMdc =
                    MDC.getCopyOfContextMap();

            return () -> {
                Map<String, String> previousMdc =
                        MDC.getCopyOfContextMap();
                try {
                    applyMdc(submittingMdc);
                    task.run();
                } finally {
                    applyMdc(previousMdc);
                }
            };
        });

        return executor;
    }

    private static void applyMdc(Map<String, String> context) {
        if (context == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(context);
        }
    }
}
~~~

Executor có thể được đưa vào `.taskExecutor(batchTaskExecutor)` của manager partition step hoặc cấu hình song song phù hợp với kiểu step. Với Spring quản lý bean, vòng đời khởi tạo và đóng pool do container đảm nhiệm.

**Giới hạn quan trọng:** `TaskDecorator` chỉ sao chép **ngữ cảnh có tại thời điểm task được submit**. Nếu task được gửi từ một luồng vốn không có ID, bản sao vẫn trống. Khi step thực thi thực sự bắt đầu, `StepExecutionListener` nên gắn lại `jobExecutionId` và `stepExecutionId` từ metadata chính xác; đây là nguồn đáng tin hơn so với MDC được thừa kế.

### 4.2. Multi-threaded step

Trong multi-threaded step, `StepExecutionListener.beforeStep` thường chạy ở luồng điều phối step, còn xử lý chunk diễn ra trên các luồng worker. Listener gắn MDC ở luồng điều phối **không đủ** để bảo đảm mọi log bên trong `ItemReader`, `ItemProcessor` hay `ItemWriter` có ID.

Khi dùng task executor cho chunk step, cần cơ chế truyền context như ở trên, hoặc một cơ chế gắn lại ID ở ranh giới công việc có bảo đảm truy cập đúng `StepExecution`. Không dùng biến `static` mutable để lưu “currentExecutionId”: hai job chạy cùng lúc sẽ ghi đè ID của nhau.

Nếu ứng dụng chạy nhiều step song song hoặc có `@Async`, mọi executor liên quan đến logging đều cần đánh giá khả năng truyền và dọn ngữ cảnh. Không giả định một `TaskDecorator` ở một bean sẽ tự áp dụng cho các executor khác.

### 4.3. Partitioning cục bộ

Với `PartitionStep`, manager khởi tạo nhiều worker `StepExecution`. Chẳng hạn:

~~~text
jobExecutionId=2401 stepExecutionId=6801 stepName=ordersWorkerStep:part0
jobExecutionId=2401 stepExecutionId=6802 stepName=ordersWorkerStep:part1
jobExecutionId=2401 stepExecutionId=6803 stepName=ordersWorkerStep:part2
~~~

Mỗi worker có `stepExecutionId` riêng nhưng cùng `jobExecutionId` của lần chạy. Gắn listener vào **worker step** là cách đơn giản để có log ngay ở nơi xử lý. Nếu chỉ gắn listener vào manager step, log trong worker sẽ thiếu ngữ cảnh riêng của partition.

Để chẩn đoán lệch tải (*data skew*), có thể log thêm các giới hạn đã gán cho partition như `minId/maxId` hoặc `dateRange` tại đầu step. Tránh ghi toàn bộ `ExecutionContext` vào log vì nó có thể chứa thông tin nhạy cảm hoặc dữ liệu dài.

### 4.4. Remote partitioning và remote chunking

Khi worker ở JVM hoặc host khác, MDC trên manager **không thể tự truyền qua mạng**. Cách làm thích hợp là đưa **correlation metadata** vào message header/payload đã định nghĩa, hoặc sử dụng `StepExecution` mà remote worker nhận được để lấy `JobExecution ID` rồi gắn MDC **tại phía nhận**.

Một thông điệp có thể mang:

~~~json
{
  "jobExecutionId": 2401,
  "stepExecutionId": 6803,
  "partitionName": "part2",
  "correlationId": "orders-2026-11-26-part2"
}
~~~

Đây là **hình dạng ví dụ của metadata ứng dụng**, không phải định dạng wire protocol mặc định của Spring Batch. Không tin tưởng mù quáng các ID nhận từ client bên ngoài; worker phải đối chiếu với metadata công việc hợp lệ. Sau khi xử lý message, xóa hoặc phục hồi MDC trong `finally` để tránh rò ngữ cảnh sang message tiếp theo.

Trong remote chunking, worker có thể xử lý request chunk không mang trực tiếp đầy đủ `StepExecution` của manager; khi đó cần giao ước message rõ ràng cho correlation ID và log ở cả nơi gửi lẫn nơi nhận. Message bị giao lại có thể xuất hiện nhiều lần, vì thế nên ghi cả message ID/attempt khi phân tích lỗi.

## 5. Log tại những điểm nào là đủ để điều tra?

Không nên log một dòng cho mỗi item khi xử lý hàng triệu bản ghi: chi phí I/O và dung lượng log có thể trở thành nút thắt. Nên đặt log ở những điểm phản ánh **trạng thái chuyển tiếp** và **khối lượng đã hoàn thành**.

| Điểm ghi log | Nội dung gợi ý | Mức log |
|---|---|---|
| Job bắt đầu | `jobExecutionId`, `jobInstanceId`, `jobName`, batch ID đã được kiểm soát | `INFO` |
| Step/partition bắt đầu | `stepExecutionId`, `stepName`, dải dữ liệu, cấu hình chunk/concurrency | `INFO` |
| Tiến độ định kỳ | `readCount`, `writeCount`, records/giây, số partition còn chạy | `INFO` với tần suất thấp |
| Retry tạm thời | Loại exception, số lần thử, step/partition, thao tác lỗi | `WARN` |
| Lỗi khiến step/job dừng | Exception stack trace, trạng thái, ID tương quan | `ERROR` |
| Step/job kết thúc | `BatchStatus`, `ExitStatus`, read/write/skip/rollback, duration | `INFO` hoặc `ERROR` theo kết quả |
| Tài nguyên bất thường | DB pool chờ kết nối, queue backlog, worker treo lâu | Metrics/alert và `WARN` khi vượt ngưỡng |

**Không log toàn bộ dữ liệu nghiệp vụ** để tạo correlation. Tránh mật khẩu, token, thông tin cá nhân, dữ liệu thanh toán và nội dung `ExecutionContext` chưa được lọc. Có thể sử dụng mã lô hoặc mã bản ghi đã được phép ghi log, nhưng ID của metadata Batch thường là đủ để tìm đúng execution.

### 5.1. Đếm tiến độ nhưng tránh spam log

Với chunk-oriented step, có thể dùng `ChunkListener` hoặc `StepExecutionListener` để ghi tiến độ theo chu kỳ thời gian hoặc sau một số chunk lớn; nhớ rằng chunk có thể rollback và retry, vì thế đếm “đã xử lý” trong một callback chưa chắc bằng số item **đã commit**.

Ví dụ định hướng:

~~~text
INFO jobExecutionId=2401 stepExecutionId=6802 stepName=ordersWorkerStep:part1
     committedReadCount=150000 committedWriteCount=149980 durationSec=180
     throughputItemsPerSec=833.2
~~~

Các trường `committedReadCount` và `throughputItemsPerSec` ở đây **là trường log do ứng dụng định nghĩa**, không phải tên metric tích hợp mặc định. Cần lấy counter phù hợp ở thời điểm checkpoint và xác định mẫu số elapsed time trước khi tính tốc độ; nếu có filter/skip, `readCount` và `writeCount` không bắt buộc bằng nhau.

### 5.2. Phân biệt log, metrics và traces

Ba tín hiệu có vai trò khác nhau:

- **Logs** trả lời “Execution ID này đã làm gì, thất bại ở đâu?” bằng các bản ghi chi tiết có `jobExecutionId`.
- **Metrics** trả lời “Tỷ lệ lỗi, duration, throughput, backlog và áp lực tài nguyên thay đổi thế nào?” thông qua số đo tổng hợp. Có thể tích hợp Micrometer/Actuator khi có dependency và cấu hình tương ứng.
- **Traces** trả lời “Thời gian phân bổ qua bước và các lời gọi phụ thuộc như thế nào?” khi ứng dụng có quan sát/tracing phân tán và truyền ngữ cảnh đúng cách.

**Không dùng `jobExecutionId`, `stepExecutionId` hoặc mã bản ghi làm label/tag của Prometheus metric.** Những ID tăng liên tục tạo số lượng time series lớn (*high cardinality*) và gây chi phí bộ nhớ/lưu trữ đáng kể. Đặt ID ở **log field** và liên kết với trace/span khi cấu hình tracing cho phép; metrics nên dùng các label có giá trị giới hạn như `jobName`, `stepName` (cân nhắc partition suffix), trạng thái và môi trường.

## 6. Từ `jobExecutionId` tìm lại JobRepository

JobRepository lưu trạng thái thực thi của Spring Batch. Khi người vận hành nhận alert với `jobExecutionId=2401`, có thể truy metadata bằng `JobExplorer` hoặc SQL read-only.

Ví dụ SQL minh họa với các bảng metadata chuẩn:

~~~sql
SELECT je.JOB_EXECUTION_ID,
       je.JOB_INSTANCE_ID,
       ji.JOB_NAME,
       je.STATUS,
       je.EXIT_CODE,
       je.START_TIME,
       je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE je.JOB_EXECUTION_ID = :jobExecutionId;

SELECT STEP_EXECUTION_ID,
       STEP_NAME,
       STATUS,
       READ_COUNT,
       WRITE_COUNT,
       READ_SKIP_COUNT,
       PROCESS_SKIP_COUNT,
       WRITE_SKIP_COUNT,
       ROLLBACK_COUNT,
       START_TIME,
       END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

Chỉ cần quyền **đọc** bảng metadata để điều tra. Không sửa trạng thái trực tiếp trong database nhằm “làm job restart được” khi chưa xác nhận tiến trình còn chạy hay không. Tên bảng và khả năng lưu history có thể khác nếu ứng dụng tùy biến JobRepository/schema.

Đoạn code truy bằng API:

~~~java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

JobExecution execution = jobExplorer.getJobExecution(jobExecutionId);
if (execution == null) {
    throw new IllegalArgumentException(
            "Không tìm thấy JobExecution ID=" + jobExecutionId);
}

System.out.println("instanceId=" +
        execution.getJobInstance().getId());
System.out.println("status=" + execution.getStatus());
execution.getStepExecutions().forEach(step ->
        System.out.println(step.getStepName() + ": " +
                step.getStatus()));
~~~

`jobExplorer` là bean `JobExplorer` đã được cấu hình hoặc inject; `jobExecutionId` là `long`/`Long` người vận hành cần truy vết. Với job lớn, không cần đọc mọi dòng log rồi mới biết job nào lỗi: dùng metadata để xác định step/partition, sau đó truy log theo các ID tương ứng.

## 7. Tìm log trong một sự cố thực tế

Giả sử dashboard cho thấy `dailyOrdersImport` thất bại lúc 02:15. Alert cung cấp `jobExecutionId=2401`.

1. **Tìm execution:** truy `BATCH_JOB_EXECUTION` hoặc `JobExplorer` để xác nhận `STATUS=FAILED`, `JOB_INSTANCE_ID=1003` và `jobName` chính xác.
2. **Tìm step lỗi:** truy `BATCH_STEP_EXECUTION` theo `JOB_EXECUTION_ID=2401`, xem step `ordersWorkerStep:part2` có `ROLLBACK_COUNT`/`WRITE_SKIP_COUNT` bất thường.
3. **Lọc log theo ID:** truy `jobExecutionId=2401` và `stepExecutionId=6803`, ưu tiên thời điểm bắt đầu lỗi, exception đầu tiên và log retry, thay vì chỉ đọc stack trace cuối.
4. **Đối chiếu tài nguyên:** xem DB deadlock/lock wait, pool connection wait, thread pool queue và thời gian transaction quanh cùng thời điểm để xác định nút thắt.
5. **Khắc phục và restart:** sau khi xác nhận nguyên nhân và tính nhất quán dữ liệu, restart đúng `JobInstance`. Execution mới có ID mới, ví dụ `2402`, nhưng vẫn có `jobInstanceId=1003`.
6. **Đối soát sau restart:** truy cả hai execution theo `jobInstanceId=1003` để biết partition nào được chạy lại và theo dõi read/write/skip cho đến khi hoàn tất.

Ví dụ ý tưởng truy vấn trong hệ thống log có cấu trúc (cú pháp cụ thể phụ thuộc Loki, Elasticsearch, OpenSearch, Splunk...):

~~~text
jobExecutionId = "2401"
jobExecutionId = "2401" AND stepExecutionId = "6803"
jobInstanceId = "1003" AND level IN ("ERROR", "WARN")
~~~

Những dòng trên là **biểu thức lọc minh họa**, không phải cú pháp truy vấn chung chạy được ở mọi backend. Nếu ứng dụng dùng console pattern, log tập trung phải có pipeline parser để tách các trường trước khi lọc chính xác.

## 8. Trường hợp dễ sai và cách kiểm chứng

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra / khắc phục |
|---|---|---|
| `jobExecutionId=na` ở tasklet/chunk | MDC chưa được gắn hoặc task chạy sang luồng khác | Kiểm tra `beforeJob/beforeStep`, executor và `TaskDecorator` |
| Log của job B mang ID job A | Thread pool tái sử dụng luồng còn MDC cũ | Phục hồi/dọn MDC bằng `finally` tại mọi ranh giới task |
| Chỉ log manager, không có ID worker | Listener chỉ gắn ở manager step | Gắn `StepExecutionListener` trên worker step |
| Restart vẫn hiện ID của lần chạy cũ | Hardcode `jobExecutionId` hoặc cache trong singleton | Lấy ID mới từ `JobExecution` của lần chạy hiện tại |
| Trộn log hai partition | Chỉ lọc theo `jobExecutionId` | Lọc thêm `stepExecutionId` hoặc `stepName` |
| Remote worker thiếu correlation | Header/message không chứa ID hoặc receiver không gắn MDC | Thiết kế metadata truyền ID và khôi phục MDC phía nhận |
| Log quá nhiều làm giảm throughput | Log INFO từng item và chứa payload lớn | Log định kỳ theo chunk/thời gian; đo I/O log |
| Dashboard metrics phình to | Gắn execution ID làm label/tags | Chuyển execution ID sang log; metrics dùng tag có cardinality thấp |
| Log cho thấy `COMPLETED` nhưng dữ liệu thiếu | Job có skip/filter, thống kê không được đối soát | Kiểm tra `read/write/skip` và kết quả nghiệp vụ |

### Checklist kiểm thử

1. Chạy một job đồng bộ và xác nhận log trong `beforeJob`, tasklet/chunk và `afterJob` cùng có một `jobExecutionId`.
2. Chạy **hai `JobInstance` đồng thời**: xác nhận hai giá trị ID khác nhau, không có dòng log bị gắn nhầm qua thread pool.
3. Dùng partitioning 4 worker: xác nhận tất cả worker có cùng `jobExecutionId` nhưng `stepExecutionId` và `stepName` khác nhau.
4. Cố ý làm một partition thất bại rồi restart: xác nhận `jobInstanceId` giữ nguyên, `jobExecutionId` đổi và log phân biệt chính xác hai lần thực thi.
5. Thử task bị lỗi sớm (exception trong worker) rồi cho thread pool tái sử dụng luồng: xác nhận `finally` xóa/phục hồi context và không để lọt ID cũ.
6. Kiểm tra tìm kiếm log tập trung theo execution ID và đối chiếu `BATCH_STEP_EXECUTION`; kiểm tra bản ghi bị skip/filter và kết quả cuối cùng.
7. Kiểm tra log không chứa dữ liệu nhạy cảm, đồng thời đo overhead ghi log khi tăng worker lên 2, 4, 8 để bảo đảm logging không thành nút thắt mới.

## 9. Kết luận

Để log theo **`JobExecution ID`** trong Spring Batch, lấy ID được cấp bởi **JobRepository**, gắn vào **MDC** thông qua `JobExecutionListener` và `StepExecutionListener`, cấu hình Logback/structured logging để xuất trường đó trên mỗi log event. Khi có multi-threaded step, parallel steps hoặc partitioning, cần quản lý **truyền và dọn MDC tại ranh giới luồng**; remote worker phải nhận correlation metadata ở phía nhận. Sử dụng `jobInstanceId` để nối các lần restart, `stepExecutionId` để khoanh vùng worker, và đối chiếu log với metadata, metrics và dữ liệu nghiệp vụ trước khi kết luận job xử lý đúng.

# Gắn step execution ID vào log trong Spring Batch

## 1. Vấn đề: một step chạy nhiều lần thì phân biệt log bằng gì?

Trong Spring Batch, một `Job` có thể chạy hằng ngày, chạy lại khi thất bại, hoặc có nhiều execution đồng thời với những bộ tham số khác nhau. Một job cũng có thể gồm nhiều `Step`. Vì vậy, một dòng log chỉ chứa tên step:

```text
INFO  OrderWriter - Wrote 100 orders
```

chưa đủ để xác định nó thuộc **lần thực thi step nào**. Khi hai execution cùng ghi log vào một hệ thống tập trung, các dòng có thể xen kẽ:

```text
09:00:01 INFO importOrdersStep - Read chunk 1
09:00:01 INFO importOrdersStep - Read chunk 1
09:00:02 ERROR importOrdersStep - Database timeout
09:00:02 INFO importOrdersStep - Wrote chunk 2
```

Không có khóa tương quan, người vận hành khó biết lỗi timeout liên quan tới chunk của lần chạy nào.

**`stepExecutionId`** là ID của một `StepExecution` được lưu trong `JobRepository`. Khi được đưa vào log, nó giúp nối các dòng log của một lần thực thi step với metadata Spring Batch. Đây là một phương pháp **log correlation** (liên kết log theo ngữ cảnh).

Ví dụ có ID:

```text
2026-11-16 09:00:01 INFO  [stepExecutionId=8702] OrderReader - Read chunk 1
2026-11-16 09:00:01 INFO  [stepExecutionId=8703] OrderReader - Read chunk 1
2026-11-16 09:00:02 ERROR [stepExecutionId=8702] OrderWriter - Database timeout
2026-11-16 09:00:02 INFO  [stepExecutionId=8703] OrderWriter - Wrote chunk 2
```

Từ đây có thể lọc toàn bộ log với `stepExecutionId=8702` rồi truy vấn `BATCH_STEP_EXECUTION` để biết status, thời gian bắt đầu/kết thúc và số lượng item đã xử lý.

Trong ngữ cảnh **Spring Batch Core Processing → Logging**, bài học này giải thích cách lấy ID, gắn ID vào log bằng **SLF4J MDC**, giữ và dọn context đúng vòng đời, xử lý đa luồng, rồi sử dụng ID khi điều tra một job thất bại.

## 2. Hiểu đúng các ID trong Spring Batch

Spring Batch phân biệt ba cấp:

```text
Job: importOrdersJob
 |
 +-- JobInstance #121: businessDate=2026-11-16
       |
       +-- JobExecution #501: FAILED
       |     |
       |     +-- StepExecution #8702: importOrdersStep, FAILED
       |
       +-- JobExecution #502: COMPLETED (restart)
             |
             +-- StepExecution #8703: importOrdersStep, COMPLETED
```

| Trường | Đại diện cho | Dùng để làm gì? |
| --- | --- | --- |
| `jobName` | Tên định nghĩa job | Lọc log của một nghiệp vụ lớn |
| `jobInstanceId` | Một công việc logic, dựa trên tên job và identifying parameters | Theo dõi cùng một công việc qua các lần restart |
| `jobExecutionId` | Một lần thử chạy job | Gom log của tất cả step trong một lần chạy |
| `stepName` | Tên step trong job | Xác định giai đoạn xử lý |
| **`stepExecutionId`** | Một lần thực thi cụ thể của step | Điều tra chính xác log và metadata của step |
| `traceId`/`spanId` | Ngữ cảnh distributed tracing nếu ứng dụng có tracing | Theo vết giữa batch, API, queue và dịch vụ ngoài |

Điểm cần nhớ:

- `stepName` có thể lặp lại trong nhiều job execution; **không phải khóa duy nhất của log**.
- Một lần **restart** thường tạo `JobExecution` mới và `StepExecution` mới cho những step chạy lại; `stepExecutionId` vì thế có thể đổi dù vẫn thuộc cùng `JobInstance`.
- `stepExecutionId` do một repository sinh ra, không nhất thiết duy nhất xuyên nhiều database hoặc môi trường. Khi tập trung log từ nhiều hệ thống, nên giữ thêm `service`, `environment` và `jobName`.
- `stepExecutionId` không phải số thứ tự chunk, không phải ID của item, và không đồng nghĩa với business key.

Trong ứng dụng, đối tượng `StepExecution` cung cấp:

```java
Long stepExecutionId = stepExecution.getId();
String stepName = stepExecution.getStepName();
Long jobExecutionId = stepExecution.getJobExecution().getId();
String jobName = stepExecution.getJobExecution()
        .getJobInstance()
        .getJobName();
```

Thông thường ID được gán khi Spring Batch đăng ký execution vào `JobRepository` trước khi step chạy. Nếu bạn tự tạo `StepExecution` chưa được lưu trong một unit test, `getId()` có thể là `null`.

## 3. SLF4J MDC: cách gắn ngữ cảnh vào nhiều dòng log

**MDC** (*Mapped Diagnostic Context*) là một bảng khóa–giá trị gắn với ngữ cảnh ghi log. Với SLF4J và backend thông dụng như Logback, MDC thường được giữ theo **thread**.

Thay vì truyền tham số ID vào mọi lệnh:

```java
log.info("stepExecutionId={} Processing order={}", stepExecutionId, orderId);
```

ta đặt ID một lần khi step bắt đầu:

```java
MDC.put("stepExecutionId", String.valueOf(stepExecution.getId()));
```

Sau đó logger có thể ghi nội dung nghiệp vụ:

```java
log.info("Processing order={}", orderId);
```

Nếu pattern logging có `%X{stepExecutionId}`, dòng log sẽ tự có ID. Đây là **trường bổ sung trong sự kiện log**, không cần chèn ID vào message bằng tay.

### MDC không phải nơi lưu trạng thái batch

| MDC | JobRepository / ExecutionContext |
| --- | --- |
| Phục vụ log correlation | Phục vụ quản lý vòng đời batch và checkpoint |
| Thường là dữ liệu tạm trong thread hiện tại | Metadata/trạng thái được lưu bởi Spring Batch |
| Không được tự động lưu vào database | `StepExecution` được ghi vào repository |
| Không bảo đảm có mặt ở thread khác | Context của step được framework quản lý theo cơ chế riêng |
| Phải dọn sau khi công việc kết thúc | Có quy trình cập nhật, restart và quản lý metadata |

Không dùng `MDC.put(...)` để thay cho việc lưu `ExecutionContext` hoặc làm dữ liệu phục hồi sau restart. Khi JVM dừng, MDC không giúp khôi phục tiến độ xử lý.

## 4. Cách tiêu chuẩn: StepExecutionListener đặt và xóa MDC

Với một step xử lý tuần tự, cách rõ ràng là tạo `StepExecutionListener`:

- `beforeStep(StepExecution)`: lấy ID và gắn vào MDC trước khi logic step chạy.
- `afterStep(StepExecution)`: ghi log tổng kết và **xóa context** để thread có thể được dùng lại an toàn.

Ví dụ dưới đây sử dụng các package **Spring Batch 5.x**, Java 17+, SLF4J 2 và Logback (như các dự án Spring Boot 3.x thông dụng).

### 4.1. Viết listener

```java
package com.example.batch.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public final class StepExecutionMdcListener
        implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepExecutionMdcListener.class);

    @Override
    public void beforeStep(StepExecution stepExecution) {
        JobExecution jobExecution = stepExecution.getJobExecution();

        MDC.put("jobName",
                jobExecution.getJobInstance().getJobName());
        MDC.put("jobExecutionId",
                String.valueOf(jobExecution.getId()));
        MDC.put("stepName",
                stepExecution.getStepName());
        MDC.put("stepExecutionId",
                String.valueOf(stepExecution.getId()));

        log.info("Step execution started");
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        try {
            log.info(
                    "Step execution finished: status={}, read={}, write={}, skip={}",
                    stepExecution.getStatus(),
                    stepExecution.getReadCount(),
                    stepExecution.getWriteCount(),
                    stepExecution.getSkipCount()
            );
        } finally {
            MDC.remove("stepExecutionId");
            MDC.remove("stepName");
            MDC.remove("jobExecutionId");
            MDC.remove("jobName");
        }

        // null: không sửa ExitStatus do Spring Batch đã tính.
        return null;
    }
}
```

**Vì sao dùng `finally` trong `afterStep`?** Một exception phát sinh trong đoạn log tổng kết không nên làm mất bước cleanup của MDC. Dữ liệu MDC có tính cục bộ theo thread; nếu thread được tái sử dụng mà còn giữ `stepExecutionId` cũ, log của công việc tiếp theo có thể bị gắn **sai ID**.

Trong ví dụ này, các key `jobName`, `jobExecutionId`, `stepName` và `stepExecutionId` được listener sở hữu. Nếu ứng dụng có các thành phần khác cũng sửa cùng các key, cần quy ước một chủ sở hữu hoặc lưu/khôi phục giá trị MDC trước đó, thay vì xóa trạng thái mà thành phần khác mong đợi.

`afterStep` được Spring Batch gọi trong vòng đời step thông thường, kể cả khi step kết thúc lỗi theo flow của framework. Tuy nhiên, **JVM crash, tiến trình bị kill hoặc lỗi nghiêm trọng làm quá trình shutdown không hoàn tất** không bảo đảm callback được gọi. Khi điều tra lỗi kiểu này, dựa thêm vào repository, log hệ thống và metric trạng thái job đang chạy quá lâu.

### 4.2. Gắn listener vào Step

Một listener được khai báo thành bean **không tự động áp dụng cho mọi step**. Phải đăng ký vào những step cần log correlation:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> orderReader,
        ItemProcessor<OrderRow, OrderRow> orderProcessor,
        ItemWriter<OrderRow> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderRow, OrderRow>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .listener(new StepExecutionMdcListener())
            .build();
}
```

`OrderRow`, reader, processor và writer ở đây là các thành phần của ứng dụng, cần được định nghĩa riêng. Với nhiều step, có thể tái sử dụng **cùng listener stateless** nếu listener chỉ sử dụng biến local và MDC theo thread; đừng cất `StepExecution` hiện tại trong trường mutable của singleton listener.

### 4.3. Dòng log trong reader, processor và writer

Khi các thành phần chạy trong **cùng thread có MDC**, chúng chỉ cần dùng logger bình thường:

```java
private static final Logger log =
        LoggerFactory.getLogger(OrderProcessor.class);

public OrderRow process(OrderRow order) {
    log.debug("Validating orderId={}", order.orderId());
    return order;
}
```

Ví dụ kết quả:

```text
2026-11-16 09:15:00.025 INFO  [job=importOrdersJob jobExec=501 step=importOrdersStep stepExec=8702] Step execution started
2026-11-16 09:15:00.030 DEBUG [job=importOrdersJob jobExec=501 step=importOrdersStep stepExec=8702] Validating orderId=O-100
2026-11-16 09:15:00.082 INFO  [job=importOrdersJob jobExec=501 step=importOrdersStep stepExec=8702] Step execution finished: status=COMPLETED, read=100, write=100, skip=0
```

Với tasklet và chunk step chạy tuần tự, `beforeStep` thường thực thi trên cùng thread với logic step. Nếu xử lý có **worker thread, partition hoặc async**, một listener ở main step thread chưa bảo đảm tất cả log phía worker có MDC. Trường hợp đó được giải thích riêng ở phần đa luồng.

## 5. Cấu hình Logback hiển thị step execution ID

Đưa dữ liệu vào MDC chưa đủ; log backend phải được cấu hình để **ghi trường MDC** ra console hoặc file.

### 5.1. Logback pattern

Trong dự án Spring Boot sử dụng Logback, có thể tạo `src/main/resources/logback-spring.xml`:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>
                %d{yyyy-MM-dd HH:mm:ss.SSS} %-5level
                [job=%X{jobName:-na} jobExec=%X{jobExecutionId:-na}
                 step=%X{stepName:-na} stepExec=%X{stepExecutionId:-na}]
                [%thread] %logger{36} - %msg%n
            </pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Logback sử dụng cú pháp `%X{key}` để đọc giá trị MDC. Phần `:-na` cung cấp giá trị mặc định khi chưa có key, chẳng hạn ở log khởi động ứng dụng hoặc log ngoài phạm vi step.

Trong file thật, có thể đặt toàn bộ phần `<pattern>... </pattern>` thành một dòng để tránh khoảng trắng hoặc xuống dòng do formatting XML tác động đến định dạng console. Nếu dự án đã có cấu hình logging tập trung, bổ sung field MDC vào cấu hình đó thay vì thay thế toàn bộ logging hiện có.

### 5.2. Log JSON cho hệ thống tập trung

Khi đẩy log tới OpenSearch/Elasticsearch, Loki, Splunk hoặc một nền tảng quan sát khác, **structured logging** thường có ích hơn việc tìm bằng chuỗi:

```json
{
  "timestamp": "2026-11-16T09:15:00.030+07:00",
  "level": "DEBUG",
  "logger": "com.example.batch.OrderProcessor",
  "message": "Validating orderId=O-100",
  "service": "order-batch",
  "environment": "production",
  "jobName": "importOrdersJob",
  "jobExecutionId": "501",
  "stepName": "importOrdersStep",
  "stepExecutionId": "8702"
}
```

Đây là **ví dụ schema JSON mong muốn**, không phải định dạng tự động của mọi Logback encoder. Tùy phiên bản Spring Boot và encoder, MDC có thể được xuất tự động thành trường JSON, nằm trong một object `mdc`, hoặc cần cấu hình thêm. Khi thiết lập ingest pipeline, hãy kiểm tra vị trí và kiểu dữ liệu thực tế của `stepExecutionId`.

Trường JSON là chuỗi trong ví dụ để phù hợp giá trị MDC (`MDC.put` lưu chuỗi). Hệ thống log có thể parse sang integer, nhưng phải làm nhất quán nếu muốn lọc chính xác.

Ví dụ truy vấn logic trong hệ log:

```text
service = "order-batch"
AND environment = "production"
AND stepExecutionId = "8702"
```

Không nhất thiết ghi `jobParameters` đầy đủ vào log. Chúng có thể chứa đường dẫn nội bộ, mã định danh khách hàng hoặc dữ liệu nhạy cảm; chỉ xuất các trường cho phép và thực sự cần cho điều tra.

## 6. Lấy stepExecutionId trong ItemReader, ItemProcessor, ItemWriter

MDC hữu ích khi muốn **mọi dòng log** tự mang ID. Nhưng một số component còn cần ID trực tiếp để tạo sự kiện audit, liên kết bản ghi hoặc truyền qua API. Khi đó có hai cách phù hợp.

### 6.1. Truyền qua StepScope

Spring Batch hỗ trợ `@StepScope` và Spring Expression Language (SpEL) để lấy dữ liệu từ step đang chạy:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
ItemProcessor<OrderRow, OrderRow> auditingProcessor(
        @Value("#{stepExecution.id}") Long stepExecutionId) {

    return item -> {
        log.info("Validating orderId={} stepExecutionId={}",
                item.orderId(), stepExecutionId);
        return item;
    };
}
```

Đoạn minh họa giả định `log` là logger đã được khai báo trong lớp cấu hình, `OrderRow` là model ứng dụng. Vì component có `@StepScope`, tham số được resolve khi có `StepContext`, không phải lúc Spring khởi tạo singleton ở startup.

Ưu điểm: method biết rõ ID và có thể sử dụng trong logic audit. Nhược điểm: bạn phải truyền ID vào **từng dòng log quan tâm**, và vẫn cần context thích hợp nếu component thực thi trong một luồng ngoài cơ chế quản lý step.

**Không gọi StepScope bean bên ngoài phạm vi step** và kỳ vọng SpEL vẫn hoạt động. Nếu component được gọi từ một test unit thuần Java, tốt hơn hãy truyền một ID giả hoặc xây component qua constructor trực tiếp.

### 6.2. Nhận StepExecution qua listener

Một component tự triển khai `StepExecutionListener` có thể nhận `StepExecution` trong `beforeStep` và sử dụng trong quá trình chạy. Nhưng cần chú ý:

- Bean dùng chung giữa các execution không nên giữ ID ở mutable field nếu có nhiều step chạy đồng thời.
- Với component được **delegate** bên trong một composite reader/processor/writer, Spring Batch có thể không tự động phát hiện listener; cần đăng ký tường minh.
- Nếu chỉ dùng để logging, một listener tập trung đặt MDC thường đơn giản hơn việc đưa listener vào mọi processor.

### 6.3. Truyền ID rõ ràng sang hệ thống ngoài

MDC không tự chuyển qua HTTP, Kafka, JDBC hay message queue. Nếu phía nhận cần theo dõi batch step, thêm một **correlation header hoặc field** riêng:

```text
X-Batch-Job-Execution-Id: 501
X-Batch-Step-Execution-Id: 8702
```

Chỉ truyền các ID này khi contract giữa các hệ thống cho phép. Không dùng chúng như khóa idempotency thay cho business key: một job restart tạo execution mới, vì vậy cùng nghiệp vụ có thể nhận ID mới.

## 7. Đa luồng: MDC không tự đi theo TaskExecutor

Đây là giới hạn quan trọng nhất khi gắn `stepExecutionId`.

Trong một step xử lý tuần tự:

```text
Step thread
   beforeStep() -> MDC.put(stepExecutionId=8702)
        |
        +-- read()
        +-- process()
        +-- write()
        |
   afterStep()  -> MDC.remove(stepExecutionId)
```

Nhưng khi dùng `TaskExecutor`, hoạt động chunk có thể chạy trên các thread khác:

```text
Coordinator thread                Worker threads
beforeStep()
  MDC = 8702
      |
      +--- submit chunk -------> pool-1-thread-1: MDC = ?
      +--- submit chunk -------> pool-1-thread-2: MDC = ?
      |
afterStep()
  remove MDC
```

MDC trong Logback thông thường dựa trên `ThreadLocal`; worker thread **không mặc nhiên kế thừa** ngữ cảnh của thread gửi task. Vì thế log của writer/processor có thể bị thiếu `stepExecutionId` mặc dù listener vẫn chạy đúng.

### 7.1. TaskDecorator sao chép và khôi phục MDC

Nếu ứng dụng dùng `ThreadPoolTaskExecutor` của Spring, có thể dùng `TaskDecorator` để truyền bản sao MDC từ thread gửi task sang thread thực thi:

```java
package com.example.batch.logging;

import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        // Chụp snapshot khi task được submit.
        Map<String, String> callerContext =
                MDC.getCopyOfContextMap();

        return () -> {
            // Lưu MDC cũ của worker thread để không rò context.
            Map<String, String> workerPreviousContext =
                    MDC.getCopyOfContextMap();

            try {
                if (callerContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(callerContext);
                }

                task.run();
            } finally {
                if (workerPreviousContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(workerPreviousContext);
                }
            }
        };
    }
}
```

Tạo executor:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
TaskExecutor batchStepTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("batch-chunk-");
    executor.setTaskDecorator(new MdcTaskDecorator());
    executor.initialize();
    return executor;
}
```

Trong cấu hình step Spring Batch 5.x, có thể gắn `taskExecutor(batchStepTaskExecutor)` vào builder nếu step được thiết kế để xử lý nhiều chunk song song.

**Giới hạn của cách này:** decorator chỉ sao chép MDC hiện có **ở thread submit task**. Nếu submit xảy ra trước khi listener đặt MDC, hoặc task được gửi qua một executor không dùng decorator, ID vẫn thiếu. Ngoài ra, khi thực thi partition, mỗi worker có thể sở hữu một `StepExecution` **khác** coordinator; chỉ sao chép ID của coordinator sẽ tạo log tương quan sai. Trong trường hợp đó, phải thiết lập MDC theo **StepExecution thực sự của worker**.

Nếu framework dùng executor khác (JDK `ExecutorService`, messaging listener container, Reactor, virtual threads hoặc hệ remote worker), cần cơ chế truyền context phù hợp từng API. Đừng coi `TaskDecorator` là giải pháp bao phủ mọi loại async.

### 7.2. Vì sao phải khôi phục MDC cũ?

Thread pool tái sử dụng thread. Nếu task A đặt `stepExecutionId=8702` rồi task B không đặt lại ID, log của task B có thể hiển thị sai là `8702`. Đoạn `try/finally` ở decorator đảm bảo:

1. Task nhận snapshot context tại lúc submit.
2. Worker dùng context đó trong lúc chạy.
3. Khi task hoàn tất hoặc ném exception, worker được khôi phục về context trước đó.

Đây là khác biệt giữa **correlation đúng** và việc chỉ “làm cho log có vẻ có ID”.

### 7.3. Partitioning và remote chunking

Trong partitioned step:

```text
Manager StepExecution #8700
   |
   +-- Partition stepExecution #8701
   +-- Partition stepExecution #8702
   +-- Partition stepExecution #8703
```

Log xử lý item trong partition `#8702` phải được gắn ID `8702`, **không phải ID `8700` của manager**.

Với local partitioning, đặt listener/context tại worker step phù hợp; với remote partitioning/chunking, phía worker cần nhận ID hoặc tạo ngữ cảnh từ `StepExecution` được framework gán cho công việc của nó. Trong hệ thống phân tán, cũng nên kết hợp `jobExecutionId`, `partitionName` và `traceId` khi cần truy vấn xuyên các thành phần.

## 8. Chunk retry, rollback và restart ảnh hưởng ID ra sao?

### 8.1. Retry trong cùng StepExecution

Khi một chunk bị rollback và retry **trong cùng StepExecution**, `stepExecutionId` thường **không đổi**. Ví dụ:

```text
stepExecutionId=8702 chunk=5 attempt=1 -> SQL timeout
stepExecutionId=8702 chunk=5 attempt=2 -> success
```

Điều này có ích: có thể tìm tất cả log của một lần step, kể cả retry. Nhưng nếu muốn phân biệt retry attempt, cần ghi thêm thông tin về retry/chunk theo cơ chế của ứng dụng. Không suy diễn số lần retry chỉ từ số dòng log trùng nhau.

### 8.2. Restart tạo execution mới

Khi job thất bại rồi restart:

```text
JobInstance 121
  JobExecution 501 -> StepExecution 8702 FAILED
  JobExecution 502 -> StepExecution 8703 COMPLETED
```

Vì vậy:

- Tra `stepExecutionId=8702` để xem lỗi ban đầu.
- Tra `stepExecutionId=8703` để xem lần chạy lại.
- Dùng `jobInstanceId=121` hoặc identifying JobParameters để nối hai execution cùng công việc logic.

Nếu một step đã hoàn thành và không được chạy lại theo cấu hình restart, sẽ không có StepExecution mới tương ứng cho lần restart đó. Không giả định mọi restart đều tạo bản ghi mới cho tất cả các step.

### 8.3. Một ID không thay thế business correlation

Với một hóa đơn `invoiceId=INV-2026-001` được xử lý hai lần ở hai execution khác nhau, `stepExecutionId` không cho biết hai xử lý đó có cùng nghiệp vụ. Nếu cần điều tra trùng giao dịch, nên dùng business key đã kiểm soát và khả năng idempotency của writer, đồng thời giữ `stepExecutionId` để biết **lần nào đã xử lý**.

## 9. Đối chiếu log với metadata của JobRepository

Khi gặp log:

```text
ERROR [stepExec=8702] Could not commit chunk
```

người vận hành có thể tìm metadata của execution tương ứng. Với `JobRepository` JDBC dùng tên bảng mặc định, câu SQL minh họa:

```sql
SELECT
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS AS STEP_STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.READ_SKIP_COUNT,
    se.PROCESS_SKIP_COUNT,
    se.WRITE_SKIP_COUNT,
    se.START_TIME,
    se.END_TIME,
    je.JOB_EXECUTION_ID,
    je.STATUS AS JOB_STATUS,
    je.JOB_INSTANCE_ID,
    ji.JOB_NAME
FROM BATCH_STEP_EXECUTION se
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_EXECUTION_ID = se.JOB_EXECUTION_ID
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE se.STEP_EXECUTION_ID = :stepExecutionId;
```

Trong truy vấn này:

1. `BATCH_STEP_EXECUTION` cho biết trạng thái và số lượng item của lần chạy step.
2. `BATCH_JOB_EXECUTION` nối step với lần chạy job tương ứng.
3. `BATCH_JOB_INSTANCE` cho biết tên job và instance.
4. Khi cần chi tiết lỗi, xem thêm `EXIT_CODE`, `EXIT_MESSAGE`, exception log và thông tin hạ tầng trong khoảng thời gian thực thi.

Các bảng metadata có thể dùng table prefix tùy chỉnh hoặc thay đổi chi tiết schema theo phiên bản, vì vậy điều chỉnh SQL theo `JobRepository` thực tế. `STEP_EXECUTION_ID` nên được tra cứu **trong đúng database và môi trường**, không mặc định ID là duy nhất giữa production, staging và test.

### Truy vấn bằng JobExplorer

Ngoài SQL, ứng dụng có thể dùng `JobExplorer` để đọc metadata:

```java
StepExecution step =
        jobExplorer.getStepExecution(jobExecutionId, stepExecutionId);

if (step != null) {
    log.info("Recovered metadata: step={}, status={}",
            step.getStepName(),
            step.getStatus());
}
```

Ví dụ sử dụng biến `jobExplorer` (bean `JobExplorer`) và hai ID đã lấy từ log hoặc sự kiện điều tra. API `getStepExecution(jobExecutionId, stepExecutionId)` thuộc cách tra cứu Spring Batch 5.x thường gặp; kiểm tra chữ ký của phiên bản dự án. Mục đích của truy vấn là đối chiếu dữ liệu đã lưu, **không dùng trong mỗi item** vì việc truy cập repository nhiều lần có thể gây overhead không cần thiết.

## 10. Kiểm thử listener và tránh rò MDC

Gắn ID vào log là hạ tầng quan sát. Vì nó dựa vào thread-local state, cần đặc biệt chú ý hai điều kiện: **đúng ID trong thời gian step chạy** và **không còn ID sau khi step kết thúc**.

### 10.1. Unit test với JUnit 5 và Mockito

Đoạn sau sử dụng mock `StepExecution` để cô lập listener khỏi database, phù hợp kiểm thử hành vi MDC:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.StepExecution;

class StepExecutionMdcListenerTest {

    @Test
    void putsStepExecutionIdInMdcAndRemovesItAfterStep() {
        StepExecution step = mock(StepExecution.class);
        JobExecution job = mock(JobExecution.class);
        JobInstance instance = mock(JobInstance.class);

        when(step.getId()).thenReturn(8702L);
        when(step.getStepName()).thenReturn("importOrdersStep");
        when(step.getJobExecution()).thenReturn(job);
        when(step.getStatus()).thenReturn(BatchStatus.COMPLETED);
        when(job.getId()).thenReturn(501L);
        when(job.getJobInstance()).thenReturn(instance);
        when(instance.getJobName()).thenReturn("importOrdersJob");

        StepExecutionMdcListener listener =
                new StepExecutionMdcListener();

        try {
            listener.beforeStep(step);

            assertEquals("8702", MDC.get("stepExecutionId"));
            assertEquals("501", MDC.get("jobExecutionId"));
            assertEquals("importOrdersStep", MDC.get("stepName"));
            assertEquals("importOrdersJob", MDC.get("jobName"));
        } finally {
            listener.afterStep(step);
        }

        assertNull(MDC.get("stepExecutionId"));
        assertNull(MDC.get("jobExecutionId"));
        assertNull(MDC.get("stepName"));
        assertNull(MDC.get("jobName"));
    }
}
```

Unit test xác nhận vòng đời lưu/xóa MDC, không chứng minh log backend đã xuất field. Để kiểm thử định dạng Logback, có thể thêm test integration gắn test appender và kiểm tra `ILoggingEvent.getMDCPropertyMap()` hoặc parse JSON đầu ra theo cấu hình logger của dự án.

### 10.2. Integration test chạy một step thực tế

Một integration test với `spring-batch-test` có thể:

1. Dựng một `Step` đơn giản với reader/processor/writer test và listener đã đăng ký.
2. Khởi chạy qua công cụ test tương ứng với version Spring Batch.
3. Trong processor, ghi log có thông điệp cố định, ví dụ `"processing-test-item"`.
4. Lấy `StepExecution` kết quả, đọc `getId()` và đối chiếu với MDC của log event đã capture.
5. Xác minh sau step không còn `stepExecutionId` trong thread đã chạy listener.
6. Khởi chạy lần nữa với một execution mới, xác minh log mang ID mới.

Với Spring Batch 5.x, `@SpringBatchTest` kết hợp `JobLauncherTestUtils` thường được dùng để khởi chạy job/step trong integration test. Với Spring Batch 6.x, cần dùng các API test tương ứng, bao gồm `JobOperatorTestUtils`. Phần kiểm thử metadata cần dùng `JobRepository` riêng để không gây ảnh hưởng các job đang chạy.

### 10.3. Test đa luồng

Khi step sử dụng `TaskExecutor`, nên cố ý tạo một test chạy nhiều chunk trên thread pool. Capture các log event từ processor/writer và kiểm tra:

- Mỗi event có `stepExecutionId` của **worker step execution thực sự**.
- Không có event nào mang ID từ một step execution trước đó.
- Khi hai step execution đồng thời, log có thể xen kẽ nhưng ID vẫn phân biệt được.
- Các thread pool được tái sử dụng sau khi step kết thúc không giữ lại MDC cũ.

Không nên dùng `Thread.sleep` rồi suy ra propagation đã hoạt động. Một kiểm tra cụ thể trên MDC của log event hoặc trong `Callable`/`Runnable` của worker sẽ chứng minh rõ hơn.

## 11. Khi nào dùng thêm JobExecutionListener và Trace?

### Logging cấp job

`JobExecutionListener` có thể đặt `jobExecutionId` và `jobName` trong ngữ cảnh lúc job bắt đầu rồi dọn khi job kết thúc. Nhưng điều này **không thay thế StepExecutionListener**, bởi `stepExecutionId` chỉ xác định được theo step. Hơn nữa, MDC ở job thread không tự truyền vào mọi worker thread.

Nếu dùng cả hai listener, hãy quy định rõ chủ sở hữu:

- Job listener quản lý `jobName` và `jobExecutionId`.
- Step listener quản lý `stepName` và `stepExecutionId`.
- Step listener không xóa key do job listener sở hữu.

Ví dụ listener trong phần 4 tự quản lý cả bốn trường nên **không cần** thêm job listener chỉ để lấy hai ID ấy. Nếu ứng dụng đã có job MDC listener, hãy điều chỉnh listener step cho phù hợp để tránh xóa context giữa vòng đời job.

### Distributed tracing

Một job có thể gọi API, gửi message hoặc xử lý remote partition. `stepExecutionId` xác định lần chạy step trong repository batch nhưng **không tự tạo distributed trace**. Nếu ứng dụng dùng Micrometer Tracing/OpenTelemetry, log có thể mang thêm `traceId` và `spanId` do tracing instrumentation cung cấp.

Giữ cả hai nhóm định danh giúp nối:

```text
stepExecutionId=8702 (lần chạy step)
       |
       +-- traceId=abc... (truy vấn dịch vụ catalog)
       |
       +-- traceId=def... (gọi dịch vụ payment)
```

Tùy cách thiết kế tracing, một step có thể có một trace lớn hoặc nhiều trace riêng cho các lệnh gọi. Không giả định mọi dòng log trong một step sẽ có cùng `traceId`. Khi cần, thêm `stepExecutionId` như span attribute có cardinality cao **trong trace**, còn metrics nên nhóm theo job/step name.

## 12. Logging an toàn và hiệu quả ở quy mô lớn

### 12.1. Thêm ID vào field, không lạm dụng chuỗi message

Nên:

```text
INFO stepExecutionId=8702 event=chunk_completed read=100 written=100
```

Hạn chế:

```text
INFO StepExecution 8702 completed chunk ...
```

Cách thứ hai buộc hệ thống tìm kiếm phải parse message. Field có tên ổn định giúp lọc, nhóm và xây dashboard dễ hơn.

### 12.2. Không biến stepExecutionId thành metric label

ID thay đổi theo execution. Nếu dùng:

```text
batch_step_duration_seconds{
    step_execution_id="8702"
}
```

thì số lượng time series có thể tăng liên tục theo lịch sử job. Metric thường nên dùng các label **có cardinality thấp** như `jobName`, `stepName`, `status` và `environment`. ID cụ thể nên nằm trong **log hoặc trace** để tìm lần chạy bị lỗi.

### 12.3. Không log mọi item ở mức INFO

Một job đọc hàng triệu item sẽ tạo lượng log rất lớn nếu mỗi item đều `INFO`. Có thể:

- Dùng `INFO` cho bắt đầu/kết thúc step, chunk summary quan trọng hoặc thay đổi trạng thái.
- Dùng `DEBUG` cho item cụ thể khi điều tra trong môi trường kiểm soát.
- Dùng `ERROR` cho exception có đầy đủ `stepExecutionId`, tên step và ngữ cảnh tối thiểu.
- Theo dõi throughput, duration, read/write/skip bằng metrics thay vì in mọi record.

Với dữ liệu nhạy cảm, không log toàn bộ payload, password, token hoặc thông tin cá nhân chỉ để có context. `stepExecutionId` cho phép truy lại metadata mà không nhất thiết phơi bày dữ liệu nghiệp vụ.

### 12.4. Thời gian, môi trường và tính nhất quán

Log tập trung nên có timestamp với offset hoặc UTC rõ ràng. Nếu hai instance ghi log bằng timezone khác nhau, một `stepExecutionId` vẫn giúp gom dòng, nhưng thứ tự thời gian có thể gây nhầm lẫn khi đồng hồ máy chủ lệch. Nên đồng bộ thời gian máy và quy ước timezone khi lưu log; không dựa duy nhất vào thời điểm ingest của log collector.

Môi trường nên được ghi riêng (`dev`, `staging`, `prod`). Một `stepExecutionId=8702` ở staging hoàn toàn có thể không liên quan tới `8702` ở production.

## 13. Sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Log không có `stepExecutionId` | Listener chưa đăng ký với step | Kiểm tra `.listener(...)` trong StepBuilder hoặc cấu hình listener |
| MDC đã có ID nhưng console không hiển thị | Pattern/JSON encoder không xuất MDC | Thêm `%X{stepExecutionId}` hoặc cấu hình MDC fields |
| Log reader có ID, log writer thiếu ID | Writer thực thi ở worker thread khác | Dùng cơ chế propagation theo executor hoặc đặt context ở worker thực sự |
| Log step sau mang ID của step trước | Quên cleanup khi thread pool tái sử dụng | `MDC.remove`/`clear` trong `finally` và khôi phục context đúng phạm vi |
| Partition log cùng mang ID manager | Sao chép MDC từ manager thay vì gắn execution của partition | Khởi tạo context theo từng worker `StepExecution` |
| Sau restart không tìm thấy log với ID cũ | Restart tạo `StepExecution` mới | Tra bằng `jobInstanceId`/`jobExecutionId` để nối các lần chạy |
| `stepExecution.getId()` bằng `null` trong unit test | Tự tạo execution chưa lưu repository | Mock ID, dùng `MetaDataInstanceFactory` hoặc chạy qua repository test |
| Nhiều log có cùng ID nhưng không biết retry nào | Retry trong cùng step execution | Ghi thông tin attempt/chunk riêng nếu cần |
| Truy vấn ID tìm sai run | ID chỉ duy nhất trong một repository | Thêm `environment`/`service` và truy vấn đúng database |
| Log JSON thiếu MDC dù pattern console đúng | Console và JSON encoder cấu hình khác nhau | Kiểm tra encoder và ingest mapping thực tế |
| Metric có số lượng series tăng nhanh | Gắn `stepExecutionId` làm label | Chuyển ID sang log/trace, metric chỉ dùng nhãn ổn định |
| Listener có field giữ StepExecution bị lẫn giữa các job | Singleton mutable state không an toàn khi chạy song song | Dùng local variables/MDC theo thread hoặc scope riêng |

## 14. Bài tập thực hành

Giả sử ứng dụng có job `importOrdersJob` gồm hai step:

```text
importOrdersJob
    |
    +-- readOrdersStep
    |
    +-- persistOrdersStep
```

**Bài 1 — MDC cơ bản.** Tạo `StepExecutionMdcListener`, đăng ký cho cả hai step, cấu hình Logback để in `jobName`, `jobExecutionId`, `stepName` và `stepExecutionId`. Chạy job và xác nhận mỗi step có ID riêng.

**Bài 2 — Dọn context.** Viết JUnit test gọi `beforeStep` và `afterStep`. Kiểm tra MDC có ID lúc chạy, rồi trả về `null` sau khi kết thúc. Cho hai execution liên tiếp để bắt lỗi dùng lại ID cũ.

**Bài 3 — Job restart.** Chủ động gây lỗi ở `persistOrdersStep`, ghi lại `stepExecutionId`, sau đó restart cùng `JobInstance`. So sánh ID của lần lỗi và lần restart. Dùng `jobInstanceId` để nối hai lần chạy.

**Bài 4 — Đa luồng.** Chuyển một step sang thực thi chunk bằng `ThreadPoolTaskExecutor`. Đầu tiên quan sát log thiếu MDC nếu chưa propagation; sau đó thêm `MdcTaskDecorator` và kiểm tra log worker có đúng ID. Khởi chạy hai step execution đồng thời để kiểm chứng không rò context.

**Bài 5 — Điều tra lỗi thực tế.** Với một dòng `ERROR stepExecutionId=...`, viết câu SQL join `BATCH_STEP_EXECUTION`, `BATCH_JOB_EXECUTION` và `BATCH_JOB_INSTANCE` để tìm status, thời gian và read/write/skip counts. So sánh metadata với log nguyên nhân.

**Bài 6 — Structured log.** Xuất một log JSON có các trường `stepExecutionId` và `jobExecutionId`. Tạo filter theo ID trong hệ log của dự án; bảo đảm trường đó không bị lẫn với payload nhạy cảm và không bị đổi kiểu dữ liệu giữa các service.

## 15. Kết luận

Gắn **`stepExecutionId` vào log** giúp biến một chuỗi log rời rạc thành lịch sử có thể truy vết của **một lần thực thi step cụ thể**. Với Spring Batch xử lý tuần tự, `StepExecutionListener` kết hợp SLF4J MDC và Logback pattern là cách triển khai gọn, dễ bảo trì. Mấu chốt không chỉ là gọi `MDC.put(...)`, mà còn phải **xóa hoặc khôi phục MDC đúng vòng đời**, hiểu rằng MDC thường gắn với thread, và dùng ID của **worker step thực sự** khi xử lý song song.

Khi điều tra, hãy nối `stepExecutionId` trong log với `BATCH_STEP_EXECUTION` và `jobExecutionId` trong `JobRepository`. Kết hợp thêm `jobInstanceId` để theo dõi restart, `traceId` khi gọi dịch vụ ngoài và metrics mức job/step để giám sát xu hướng. Như vậy, một lỗi chunk hay item cụ thể có thể được truy lại chính xác mà không làm tăng lượng log hoặc metric không cần thiết.

### Tài liệu tham khảo

- [Spring Batch Reference — Domain: Job, JobExecution, StepExecution](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch Reference — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html)
- [Spring Batch Reference — Parallel Processing and Scaling](https://docs.spring.io/spring-batch/reference/scalability.html)
- [SLF4J — MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html)
- [Logback — MDC](https://logback.qos.ch/manual/mdc.html)
- [Spring Framework — TaskDecorator API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskDecorator.html)

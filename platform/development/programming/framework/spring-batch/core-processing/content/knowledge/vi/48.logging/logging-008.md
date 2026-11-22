# Structured log cho batch trong Spring Batch Core Processing

Khi một ứng dụng Spring Batch xử lý nhiều job, nhiều step và nhiều lần restart, dòng log kiểu `INFO - Finished processing orders` rất khó dùng để điều tra sự cố. Người vận hành cần biết **job nào**, **lần thực thi nào**, **step nào**, **trạng thái gì**, **đã xử lý bao nhiêu item** và **lỗi thuộc giai đoạn nào**. Nếu tất cả thông tin chỉ nằm trong một chuỗi message tự do, việc lọc trên hệ thống quản lý log sẽ phụ thuộc vào cách mỗi lập trình viên viết câu tiếng Anh hoặc tiếng Việt.

**Structured logging** là cách ghi mỗi sự kiện thành một bản ghi có trường dữ liệu ổn định, thường ở dạng **một object JSON trên một dòng** (*JSON Lines*). Trong Spring Batch, cách này đặc biệt hữu ích vì framework đã có mô hình định danh và theo dõi thực thi rõ ràng: `JobInstance`, `JobExecution`, `StepExecution`, `BatchStatus`, `ExitStatus` và các bộ đếm của step.

Bài này xây dựng cách thiết kế và triển khai structured log cho batch từ cấu hình xuất JSON, thêm execution context vào MDC, ghi sự kiện vòng đời job/step, log skip và lỗi, đến cách tìm kiếm, kiểm thử và vận hành log an toàn.

## 1. Vấn đề của log văn bản tự do

Ví dụ ba dòng từ hai lần chạy khác nhau:

```text
2026-11-16 01:01:04 INFO  Start importOrders
2026-11-16 01:01:07 ERROR Cannot write item
2026-11-16 01:01:10 INFO  importOrders finished
```

Ta không biết lỗi ghi thuộc `JobExecution` nào, step nào, item có được retry hoặc skip hay không, và `finished` có nghĩa `COMPLETED` hay `FAILED`. Nếu hai execution chạy đồng thời, chỉ tìm theo `importOrders` sẽ trộn nhiều luồng log.

Một bản ghi có cấu trúc có thể mang những thông tin mà hệ thống log tìm kiếm trực tiếp:

```json
{
  "@timestamp": "2026-11-16T01:01:10.218Z",
  "level": "INFO",
  "service": "order-batch",
  "eventType": "batch.step.finished",
  "message": "Batch step finished",
  "jobName": "importOrders",
  "jobInstanceId": "305",
  "jobExecutionId": "4812",
  "stepName": "writeOrders",
  "stepExecutionId": "9207",
  "batchStatus": "COMPLETED",
  "exitCode": "COMPLETED",
  "readCount": 1000,
  "writeCount": 987,
  "filterCount": 10,
  "skipCount": 3,
  "durationMs": 42500
}
```

Đây là **JSON minh họa một schema do ứng dụng quy ước**. Tên trường mặc định như `@timestamp`, `logger_name`, `log.level` có thể khác giữa Logstash, ECS, GELF và các encoder. Các trường `eventType`, `jobExecutionId`, `skipCount` được ứng dụng chủ động bổ sung bằng MDC hoặc API logging có cấu trúc; Spring Batch không tự xuất toàn bộ object này ở mọi log statement.

## 2. Log phải gắn đúng tầng định danh của Spring Batch

```text
Job: importOrders
 |
 +-- JobInstance 305 -- identifying params: businessDate=2026-11-15
 |     |
 |     +-- JobExecution 4811: FAILED
 |     |     +-- StepExecution 9206: loadOrders, FAILED
 |     |
 |     +-- JobExecution 4812: COMPLETED (restart)
 |           +-- StepExecution 9207: loadOrders, COMPLETED
 |
 +-- JobInstance 306 -- identifying params: businessDate=2026-11-16
       |
       +-- JobExecution 4813: STARTED
             +-- StepExecution 9208: loadOrders, STARTED
```

| Trường log | Nguồn điển hình | Công dụng |
| --- | --- | --- |
| `jobName` | `jobExecution.getJobInstance().getJobName()` | Phân biệt các quy trình batch |
| `jobInstanceId` | `jobExecution.getJobInstance().getId()` | Gom các lần thử chạy của cùng công việc logic |
| `jobExecutionId` | `jobExecution.getId()` | Khóa quan trọng nhất để tìm log đúng **một lần chạy** |
| `stepName` | `stepExecution.getStepName()` | Xác định giai đoạn đang xử lý |
| `stepExecutionId` | `stepExecution.getId()` | Phân biệt các lần thực thi của cùng step, kể cả restart |
| `batchStatus` | `getStatus().name()` | `STARTED`, `COMPLETED`, `FAILED`, `STOPPED`... |
| `exitCode` | `getExitStatus().getExitCode()` | Kết quả thoát, có thể được quy trình Batch tùy biến |
| `businessDate` | `JobParameters` được chọn lọc | Kỳ xử lý nghiệp vụ, hữu ích cho tìm theo ca/ngày |
| `traceId`, `spanId` | Hạ tầng tracing khi có | Liên kết log với distributed trace |

**Không đồng nhất `JobInstance` với `JobExecution`.** Cùng một instance có thể `FAILED` rồi restart thành công, tạo hai execution ID khác nhau. Khi trả lời “lỗi phát sinh ở lần chạy nào”, hãy dùng `jobExecutionId`; khi trả lời “công việc cho ngày X đã hoàn tất chưa”, cần xem cả chuỗi execution thuộc cùng instance.

`JobRepository` là nguồn metadata chính thức để biết trạng thái và số đếm của lần chạy. Log là chuỗi **sự kiện quan sát và điều tra**; nó có thể bị mất hoặc trùng trong quá trình chuyển tới hệ thống tập trung và không thay thế metadata giao dịch của Batch.

## 3. Định nghĩa một hợp đồng trường log ổn định

Một hệ thống vận hành nhiều job cần quy ước trường và kiểu dữ liệu, thay vì để từng lớp Java đặt tên tùy hứng. Có thể chia thành các nhóm:

| Nhóm | Trường nên có | Nguyên tắc |
| --- | --- | --- |
| Thời gian | `@timestamp`, `durationMs` | Timestamp ISO-8601 có múi giờ/UTC; duration là số mili giây |
| Nguồn phát | `service`, `environment`, `logger`, `thread`, `serviceVersion` | Dùng tên ổn định, không đưa ID item vào tag nguồn phát |
| Phân loại | `eventType`, `level`, `message` | `eventType` là mã máy đọc được; message dành cho con người |
| Job | `jobName`, `jobInstanceId`, `jobExecutionId` | Luôn mang ID khi đã có metadata |
| Step | `stepName`, `stepExecutionId` | Gắn cho log phát sinh trong step |
| Kết quả | `batchStatus`, `exitCode`, `errorType`, `errorCode` | Phân biệt lỗi và kết quả cuối |
| Đếm xử lý | `readCount`, `writeCount`, `filterCount`, `skipCount`, `rollbackCount` | Số có kiểu numeric trong JSON khi xuất summary |
| Nghiệp vụ | `businessDate`, `sourceType`, `fileLogicalName` | Chỉ đưa giá trị đã được phê duyệt để ghi log |
| Tracing | `traceId`, `spanId`, `correlationId` | Dùng khi có distributed tracing và hệ thống liên quan |

Đặt tên sự kiện theo một danh sách cố định, ví dụ:

```text
batch.job.started
batch.job.finished
batch.step.started
batch.step.finished
batch.item.skipped
batch.chunk.rollback
batch.execution.failed
batch.execution.recovery-requested
```

Một số quy tắc thực tế:

1. **Tên trường ổn định:** không lúc dùng `jobId`, lúc dùng `jobExecution` nếu cả hai cùng chỉ một ID. Chọn tên công khai và duy trì xuyên suốt các module.
2. **Kiểu nhất quán:** `durationMs` và các counter là số; `jobExecutionId` có thể chọn số hoặc chuỗi nhưng phải thống nhất trong schema và truy vấn. MDC của SLF4J lưu giá trị chuỗi, còn `addKeyValue(...)` có thể giữ dữ liệu numeric khi encoder hỗ trợ.
3. **Thời gian rõ múi giờ:** ghi timestamp theo UTC hoặc chuẩn ISO-8601 có offset. Kỳ nghiệp vụ `businessDate` là ngày logic, không đồng nghĩa ngày hệ thống phát log.
4. **Sự kiện không phụ thuộc câu chữ:** dashboard dựa vào `eventType=batch.step.finished`, không dùng regex tìm `Finished` trong message.
5. **Có phiên bản schema khi cần:** nếu hợp đồng thay đổi lớn, bổ sung `schemaVersion` hoặc áp dụng mapping chuyển đổi tại nơi thu nhận.
6. **Tránh dữ liệu nhạy cảm:** chỉ định rõ trường nào được phép log; không in toàn bộ `JobParameters`, `ExecutionContext` hoặc item.

## 4. Bật JSON logging với Spring Boot 3.4+

Từ **Spring Boot 3.4**, structured logging được hỗ trợ sẵn với các định dạng **ECS**, **GELF** và **Logstash**. Nếu ứng dụng dùng cấu hình logging mặc định của Spring Boot, có thể bật dạng Logstash JSON theo cấu hình:

```yaml
spring:
  application:
    name: order-batch

logging:
  structured:
    format:
      console: logstash
```

Một sự kiện được logger phát ra khi đó sẽ được format thành JSON thay vì pattern văn bản thông thường. Có thể dùng `ecs` nếu tổ chức đã chuẩn hóa theo Elastic Common Schema, hoặc `gelf` nếu dùng hệ thống tương thích GELF. Các trường trong **SLF4J MDC** và các key-value pair tạo bởi **SLF4J 2 fluent API** có thể được encoder structured logging của Spring Boot đưa vào JSON.

Để ghi JSON ra file do ứng dụng quản lý:

```yaml
logging:
  file:
    name: logs/order-batch.jsonl
  structured:
    format:
      file: logstash
```

Đây là lựa chọn **thay thế hoặc bổ sung** cho console tùy môi trường. Trong Kubernetes hoặc container, một cấu hình thường gặp là ghi mỗi JSON event ra **stdout** để agent log thu gom; nếu vừa ghi console vừa ghi file, cần cấu hình hệ thống thu nhận tránh ingest trùng.

**Giới hạn phiên bản:** Spring Boot 3.3 và các phiên bản trước không có đầy đủ các property `logging.structured.format.*` nêu trên. Nếu dự án dùng Boot cũ hoặc Spring Framework thuần, có thể cấu hình encoder JSON trong Logback/Log4j2. Khi đã có `logback-spring.xml` tùy chỉnh, Boot không nhất thiết tự thay encoder của file đó; cần khai báo encoder tương thích hoặc chuyển về cấu hình logging Boot hỗ trợ.

### Tùy chọn Logback encoder cho dự án dùng Boot cũ

Đối với ứng dụng dùng Logback, thư viện `net.logstash.logback:logstash-logback-encoder` cung cấp `LogstashEncoder`. Hãy chọn phiên bản encoder tương thích với Logback/Java của dự án, rồi cấu hình:

```xml
<!-- src/main/resources/logback-spring.xml -->
<configuration>
    <appender name="JSON_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="JSON_CONSOLE"/>
    </root>
</configuration>
```

Ví dụ này minh họa cấu hình **thay thế** khi Boot chưa có structured logging tích hợp. Cần bổ sung dependency encoder với một version cụ thể đã tương thích, và tránh dùng đồng thời nhiều appender xuất cùng một event đến cùng pipeline ingest. Cả encoder JSON tích hợp và LogstashEncoder đều chỉ định dạng log; trường `jobExecutionId` vẫn phải được chương trình cung cấp.

## 5. Thêm ngữ cảnh bằng SLF4J MDC

`MDC` (*Mapped Diagnostic Context*) là bản đồ key-value gắn với ngữ cảnh của **thread** phát log. Khi đặt `jobExecutionId` vào MDC, các logger được gọi trên thread đó có thể tự gắn ID này vào mọi event mà không cần truyền ID qua mọi hàm của reader, processor và writer.

Ví dụ ngắn:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class MdcExample {
    private static final Logger log =
            LoggerFactory.getLogger(MdcExample.class);

    public void runWithContext(long jobExecutionId) {
        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("jobExecutionId",
                             Long.toString(jobExecutionId))) {
            log.info("Reading first input page");
            log.info("Reading second input page");
        }
        // putCloseable loại bỏ key khi close.
    }
}
```

Các dòng log trong khối sẽ có `jobExecutionId` nếu encoder đã được cấu hình lấy MDC. `putCloseable` phù hợp khi scope log được giới hạn trong một block. Với nhiều key cần bảo toàn giá trị MDC từ ngữ cảnh trước đó, có thể sao chép map, đặt key và **khôi phục map cũ trong `finally`**.

Đặc biệt với thread pool, phải làm sạch MDC sau mỗi đoạn xử lý. Nếu quên, thread từng xử lý `JobExecution 4811` có thể được tái sử dụng cho `4812` nhưng vẫn mang ID cũ trong log; đó là lỗi correlation nghiêm trọng.

### Structured fields cho riêng một sự kiện

MDC là lựa chọn cho thông tin lặp lại trong nhiều log trên cùng thread. Các con số chỉ có ở một sự kiện tổng kết có thể đưa trực tiếp vào câu log bằng **SLF4J 2 fluent logging API**:

```java
log.atInfo()
   .addKeyValue("eventType", "batch.step.finished")
   .addKeyValue("readCount", step.getReadCount())
   .addKeyValue("writeCount", step.getWriteCount())
   .addKeyValue("filterCount", step.getFilterCount())
   .addKeyValue("skipCount", step.getSkipCount())
   .log("Batch step finished");
```

Khi encoder hỗ trợ key-value pair, cách này giúp giữ các counter dưới dạng **number** trong JSON. Khả năng hiển thị key-value pair phụ thuộc backend logging/encoder; nếu dùng pattern plain text không hỗ trợ, những trường ấy có thể không xuất hiện như mong muốn.

## 6. Ghi sự kiện vòng đời job qua `JobExecutionListener`

`JobExecutionListener` được gọi trước khi job bắt đầu thực thi và sau khi job hoàn tất hoặc thất bại. Đây là nơi thích hợp để ghi **một sự kiện bắt đầu và một sự kiện kết thúc** cho mỗi `JobExecution`.

Ví dụ dành cho **Spring Batch 5.2.x, SLF4J 2 và Java 17**:

```java
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class JobEventLoggingListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(JobEventLoggingListener.class);

    @Override
    public void beforeJob(JobExecution execution) {
        withJobMdc(execution, () ->
                log.atInfo()
                   .addKeyValue("eventType", "batch.job.started")
                   .addKeyValue("batchStatus",
                           execution.getStatus().name())
                   .log("Batch job started"));
    }

    @Override
    public void afterJob(JobExecution execution) {
        withJobMdc(execution, () ->
                log.atInfo()
                   .addKeyValue("eventType", "batch.job.finished")
                   .addKeyValue("batchStatus",
                           execution.getStatus().name())
                   .addKeyValue("exitCode",
                           execution.getExitStatus().getExitCode())
                   .log("Batch job finished"));
    }

    private static void withJobMdc(
            JobExecution execution, Runnable logAction) {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            MDC.put("jobName",
                    execution.getJobInstance().getJobName());
            MDC.put("jobInstanceId",
                    String.valueOf(execution.getJobInstance().getId()));
            MDC.put("jobExecutionId",
                    String.valueOf(execution.getId()));
            logAction.run();
        } finally {
            // Giữ nguyên MDC của caller, kể cả khi logAction lỗi.
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }
}
```

Hai callback này chỉ mở MDC **trong lúc ghi event lifecycle**, tránh giả định rằng toàn bộ job luôn chạy trên một thread. Dù listener được tái sử dụng cho nhiều execution song song, nó không lưu `JobExecution` vào field mutable chung.

`afterJob` được gọi với cả execution thành công và thất bại theo hợp đồng listener. `batch.job.finished` có nghĩa **callback kết thúc đã diễn ra**; cần đọc `batchStatus` và `exitCode` để xác định kết quả, không tự coi mọi `finished` là `COMPLETED`. Nếu muốn mức log `ERROR` cho kết quả thất bại, có thể phát sự kiện `batch.execution.failed` riêng với exception đã được kiểm soát.

## 7. Gắn MDC vào quá trình xử lý step

Đối với **chunk-oriented step chạy đồng bộ trên một thread**, `StepExecutionListener.beforeStep` có thể đặt các khóa MDC trước khi reader/processor/writer chạy; `afterStep` ghi counter rồi dọn khóa.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class StepEventLoggingListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepEventLoggingListener.class);

    @Override
    public void beforeStep(StepExecution step) {
        MDC.put("jobName",
                step.getJobExecution().getJobInstance().getJobName());
        MDC.put("jobInstanceId", String.valueOf(
                step.getJobExecution().getJobInstance().getId()));
        MDC.put("jobExecutionId", String.valueOf(
                step.getJobExecution().getId()));
        MDC.put("stepName", step.getStepName());
        MDC.put("stepExecutionId", String.valueOf(step.getId()));

        log.atInfo()
           .addKeyValue("eventType", "batch.step.started")
           .log("Batch step started");
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        try {
            log.atInfo()
               .addKeyValue("eventType", "batch.step.finished")
               .addKeyValue("batchStatus", step.getStatus().name())
               .addKeyValue("exitCode",
                       step.getExitStatus().getExitCode())
               .addKeyValue("readCount", step.getReadCount())
               .addKeyValue("writeCount", step.getWriteCount())
               .addKeyValue("filterCount", step.getFilterCount())
               .addKeyValue("readSkipCount", step.getReadSkipCount())
               .addKeyValue("processSkipCount",
                       step.getProcessSkipCount())
               .addKeyValue("writeSkipCount", step.getWriteSkipCount())
               .addKeyValue("skipCount", step.getSkipCount())
               .addKeyValue("commitCount", step.getCommitCount())
               .addKeyValue("rollbackCount", step.getRollbackCount())
               .log("Batch step finished");
        } finally {
            MDC.remove("stepExecutionId");
            MDC.remove("stepName");
            MDC.remove("jobExecutionId");
            MDC.remove("jobInstanceId");
            MDC.remove("jobName");
        }
        return null; // Không sửa ExitStatus do Spring Batch xác định.
    }
}
```

Ví dụ listener giả định **các key MDC dành riêng cho batch trước đó chưa có giá trị**, và `beforeStep`/`afterStep` thực hiện trên cùng thread theo mô hình step đồng bộ. Nếu ứng dụng cần lồng các scope MDC trên cùng thread, nên bao từng đoạn bằng cơ chế snapshot/restore map trước đó thay vì xóa key; nếu dùng parallel/partitioned step, phải xét **thread-local propagation** như mục 10.

Tại thời điểm `afterStep`, các counter `readCount`, `writeCount`, `filterCount` và các loại `skipCount` phản ánh kết quả mà Spring Batch đang tổng kết cho step. Chúng là nguồn đáng tin hơn so với việc tự tăng counter mỗi khi một logger ghi thông điệp. `StepExecutionListener.afterStep` có thể trả về một `ExitStatus` để ảnh hưởng exit code; trả `null` giữ kết quả hiện có.

### Gắn listener vào `JobBuilder` và `StepBuilder`

Trong cấu hình Spring Batch 5.x, có thể thêm listener trực tiếp vào builder:

```java
@Bean
Job importOrdersJob(JobRepository repository, Step importOrdersStep) {
    return new JobBuilder("importOrders", repository)
            .listener(new JobEventLoggingListener())
            .start(importOrdersStep)
            .build();
}

@Bean
Step importOrdersStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, ProcessedOrder> processor,
        ItemWriter<ProcessedOrder> writer) {

    return new StepBuilder("importOrdersStep", repository)
            .<Order, ProcessedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(new StepEventLoggingListener())
            .build();
}
```

Phần code là ví dụ trích từ class cấu hình `@Configuration`; các kiểu `Order`/`ProcessedOrder` và các bean reader/processor/writer phải được ứng dụng định nghĩa. Các import chính thuộc `org.springframework.batch.core.job.builder.JobBuilder`, `org.springframework.batch.core.step.builder.StepBuilder`, `org.springframework.batch.core.repository.JobRepository` và `org.springframework.transaction.PlatformTransactionManager`.

Không bắt buộc mỗi step phải có listener riêng; một listener **không giữ state chung** có thể tái sử dụng. Tuy nhiên, việc gắn listener vào job và step phải tuân thủ cách Spring Batch cấu hình trong dự án để tránh phát cùng một lifecycle event nhiều lần.

## 8. Log filter, skip, retry và failure đúng ý nghĩa

Trong Spring Batch, cần phân biệt:

- **Filter:** `ItemProcessor.process(item)` trả về `null`, nghĩa là item được loại theo nghiệp vụ. Framework tăng `filterCount`; đây không phải lỗi.
- **Skip:** exception xảy ra khi đọc/xử lý/ghi được `skipPolicy` chấp nhận, làm tăng `readSkipCount`, `processSkipCount` hoặc `writeSkipCount`.
- **Retry:** một exception có thể khiến framework thử lại; nếu lần sau thành công thì item **không bị skip** chỉ vì từng có exception.
- **Failure:** exception không xử lý được có thể làm `StepExecution` và `JobExecution` chuyển `FAILED`.

Không nên phát sự kiện `batch.item.skipped` từ `ItemReadListener.onReadError` hoặc `ItemWriteListener.onWriteError`: callback lỗi có thể chạy nhiều lần vì retry/rollback, trong khi skip chỉ được xác lập sau khi framework áp dụng chính sách.

### Log skip bằng `SkipListener`

`SkipListener` có callback dành riêng cho item thực sự được skip. Ví dụ đơn giản cho pipeline có input/output là `String`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class SkipEventLoggingListener
        implements SkipListener<String, String> {

    private static final Logger log =
            LoggerFactory.getLogger(SkipEventLoggingListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        report("read", error);
    }

    @Override
    public void onSkipInProcess(String item, Throwable error) {
        report("process", error);
    }

    @Override
    public void onSkipInWrite(String item, Throwable error) {
        report("write", error);
    }

    private void report(String phase, Throwable error) {
        log.atWarn()
           .addKeyValue("eventType", "batch.item.skipped")
           .addKeyValue("phase", phase)
           .addKeyValue("errorType",
                   error.getClass().getSimpleName())
           .log("Batch item skipped");
    }
}
```

Gắn listener này ở step builder có `faultTolerant()` và skip policy phù hợp, chẳng hạn:

```java
.faultTolerant()
.skip(InvalidRecordException.class)
.skipLimit(20)
.listener(new SkipEventLoggingListener())
```

`InvalidRecordException` là kiểu exception ứng dụng tự khai báo. **Không log nguyên item** hoặc `error.getMessage()` khi chúng có thể chứa dữ liệu cá nhân, token hay nội dung file nhạy cảm. Nếu cần truy vết item để sửa dữ liệu, dùng một mã bản ghi đã được phép lưu log (hoặc mã băm an toàn theo chính sách), kết hợp truy vấn ở hệ thống dữ liệu gốc.

Ở bản tổng kết step, hãy ghi `readCount`, `writeCount`, `filterCount`, ba loại skip và `skipCount`. Đẳng thức `skipCount = readSkipCount + processSkipCount + writeSkipCount` là ý nghĩa của tổng skip cấp step; **không cộng `filterCount` vào `skipCount`**. Log skip theo từng item giúp điều tra nguyên nhân, còn counter của `StepExecution` phản ánh kết quả cuối của lần thực thi.

### Khi cần log stack trace

Với exception làm step thất bại, nên có ít nhất một log `ERROR` mang stack trace và execution ID để điều tra:

```java
if (step.getStatus() == BatchStatus.FAILED
        && !step.getFailureExceptions().isEmpty()) {
    Throwable cause = step.getFailureExceptions().get(0);
    log.atError()
       .addKeyValue("eventType", "batch.execution.failed")
       .addKeyValue("errorType", cause.getClass().getSimpleName())
       .setCause(cause)
       .log("Batch step failed");
}
```

Đoạn code có thể được gọi từ `afterStep` **trước khi dọn MDC**, với import `org.springframework.batch.core.BatchStatus`. Phải tránh ghi cùng một stack trace quá nhiều lần qua reader, writer, retry listener và job listener. Trong production, chọn một nơi ghi error detail chính, còn các callback khác chỉ cần mã lỗi và thông tin correlation. Stack trace cũng có thể lộ chuỗi SQL hoặc dữ liệu đầu vào; cần xét chính sách retention và redaction.

## 9. Ví dụ luồng JSON log của một lần chạy

Giả sử job `importOrders` có `jobExecutionId=4812`, step `loadOrders` đọc thành công 500 item, lọc 10, skip 2 khi process và ghi 488 item. Dưới đây là các **event minh họa** dạng JSON Lines; cấu trúc theo schema ứng dụng đã chọn:

```jsonl
{"@timestamp":"2026-11-16T01:00:00Z","level":"INFO","eventType":"batch.job.started","jobName":"importOrders","jobInstanceId":"305","jobExecutionId":"4812","message":"Batch job started"}
{"@timestamp":"2026-11-16T01:00:01Z","level":"INFO","eventType":"batch.step.started","jobName":"importOrders","jobInstanceId":"305","jobExecutionId":"4812","stepName":"loadOrders","stepExecutionId":"9207","message":"Batch step started"}
{"@timestamp":"2026-11-16T01:00:05Z","level":"WARN","eventType":"batch.item.skipped","jobExecutionId":"4812","stepName":"loadOrders","stepExecutionId":"9207","phase":"process","errorType":"InvalidRecordException","message":"Batch item skipped"}
{"@timestamp":"2026-11-16T01:00:45Z","level":"INFO","eventType":"batch.step.finished","jobExecutionId":"4812","stepName":"loadOrders","stepExecutionId":"9207","batchStatus":"COMPLETED","readCount":500,"writeCount":488,"filterCount":10,"processSkipCount":2,"skipCount":2,"message":"Batch step finished"}
{"@timestamp":"2026-11-16T01:00:46Z","level":"INFO","eventType":"batch.job.finished","jobName":"importOrders","jobInstanceId":"305","jobExecutionId":"4812","batchStatus":"COMPLETED","exitCode":"COMPLETED","message":"Batch job finished"}
```

Với `jobExecutionId=4812`, operator có thể lọc toàn bộ chuỗi event, thấy step và nguyên nhân skip, rồi đối chiếu trạng thái hiện tại trong `JobRepository`. Nếu cần xác nhận **mọi item nghiệp vụ thực sự đã được ghi**, phải còn đối chiếu dữ liệu đầu ra và chính sách filter/skip; chỉ log `COMPLETED` chưa chứng minh chất lượng dữ liệu.

## 10. MDC trong batch chạy đa luồng, partitioning và async

**MDC thường là thread-local**. Khi job chuyển công việc sang thread pool hoặc worker process, các key `jobExecutionId`/`stepExecutionId` có thể không đi theo. Các tình huống cần xét:

| Kiểu thực thi | Vấn đề correlation | Cách tiếp cận |
| --- | --- | --- |
| Chunk step đồng bộ | Reader/processor/writer thường chạy trên thread của step | `StepExecutionListener` đặt/dọn MDC theo lifecycle step |
| Multi-threaded step với `TaskExecutor` | Worker thread không mặc nhiên nhận MDC của thread điều khiển | Truyền MDC vào task và khôi phục sau mỗi task |
| Partitioned step | Mỗi partition có `StepExecution`/step name riêng | Gắn ID **của partition worker**, không chỉ copy ID của master |
| `AsyncItemProcessor`/`AsyncItemWriter` | Đoạn xử lý có thể chuyển thread | Truyền correlation context có chủ đích; không giả định MDC tự đi theo |
| Remote partitioning/chunking | Chạy trên JVM/process khác | Đưa correlation fields vào message headers/payload an toàn, tái tạo MDC ở worker |
| HTTP/API call sang service khác | Trace nằm trên hệ thống phân tán | Dùng tracing propagation và gắn `traceId`/`spanId` khi có |

### Ví dụ truyền MDC với `TaskDecorator`

Trong Spring Framework, một `TaskDecorator` có thể capture MDC tại lúc submit task, đặt nó trên thread thực thi và khôi phục lại context cũ sau khi chạy:

```java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public class MdcCopyTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable delegate) {
        Map<String, String> submittingThreadContext =
                MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> workerThreadContext =
                    MDC.getCopyOfContextMap();
            try {
                if (submittingThreadContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(submittingThreadContext);
                }
                delegate.run();
            } finally {
                if (workerThreadContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(workerThreadContext);
                }
            }
        };
    }
}
```

Cấu hình ví dụ:

```java
@Bean
ThreadPoolTaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setThreadNamePrefix("batch-worker-");
    executor.setTaskDecorator(new MdcCopyTaskDecorator());
    executor.initialize();
    return executor;
}
```

Đoạn này giả định Spring dùng `ThreadPoolTaskExecutor` với import `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor`. Nếu bước Batch được cấu hình dùng executor khác, cần đặt decoration trên đúng executor đó. Việc copy MDC chỉ giải quyết **các trường log**, không tự truyền Spring Batch `StepScope`/`JobScope`, transaction hoặc security context.

Ở partitioned step, không nên giữ nguyên `stepExecutionId` của partition master nếu task đang thực thi worker step có ID riêng. Khi worker bắt đầu, hãy gắn dữ liệu từ **`StepExecution` của worker**. Với các queue/remote worker, MDC phải được thiết lập rồi dọn ở đầu/cuối xử lý message để tránh rò rỉ context giữa các tác vụ.

## 11. Structured log, tracing và Micrometer: nhiệm vụ khác nhau

Ba nhóm dữ liệu quan sát thường được dùng cùng nhau:

```text
JobRepository / JobExplorer
    -> JobExecution, StepExecution, BatchStatus, counters

Structured logs
    -> sự kiện, exception, correlation, chi tiết điều tra

Metrics / tracing
    -> duration, throughput, active jobs, dependency latency
```

Spring Batch có observability/metrics tích hợp dựa trên Micrometer ở các phiên bản hỗ trợ. Một số metric có tên như `spring.batch.job`, `spring.batch.step`, `spring.batch.item.read`, `spring.batch.item.process` và `spring.batch.chunk.write`. Những timer cho biết thời gian xử lý; **số lần thu thập timer không bằng `writeCount` hay `skipCount`** của `StepExecution`.

Tracing có thể tự thêm `traceId`/`spanId` vào log qua Spring Boot/Micrometer Tracing khi được cấu hình phù hợp. Cần giữ **cả** các ID trace và ID batch: một `JobExecution` có thể trải qua nhiều trace hoặc gọi nhiều service, trong khi trace ID không ổn định qua các lần restart.

Đối với một lần thực thi:

- Từ dashboard Batch mở `jobExecutionId` để xem job, step, status và counters.
- Từ log lọc `jobExecutionId`, rồi tìm `ERROR` hoặc `eventType=batch.item.skipped` để điều tra.
- Từ `traceId`/`spanId` trên log tìm các lời gọi tới database/API/queue bị chậm.
- Dùng metrics để so độ trễ kỳ hiện tại với baseline những kỳ trước.

Không nên lấy hệ thống log làm nguồn duy nhất để đếm item đã commit. Log có thể bị trễ khi ingest, được sampling, bị mất do process chết hoặc xuất hiện trùng khi shipper retry; `JobRepository` vẫn là nguồn thực thi cốt lõi.

## 12. Tìm kiếm và tổng hợp log trong công cụ vận hành

Khi `jobExecutionId` là một field JSON riêng, người vận hành không còn phải tìm bằng chuỗi message. Truy vấn minh họa ở hệ thống hỗ trợ Lucene/Kibana query syntax:

```text
jobExecutionId:"4812" AND level:"ERROR"
```

Tìm skip theo step:

```text
jobName:"importOrders" AND stepName:"loadOrders"
AND eventType:"batch.item.skipped"
```

Đối với Loki, có thể giữ nhãn có cardinality thấp như `service`/`environment`, parse trường JSON lúc truy vấn:

```logql
{service="order-batch", environment="production"}
| json
| jobExecutionId="4812"
```

Nếu đã xuất log dạng JSON Lines trong một file phục vụ điều tra offline, có thể lọc bằng `jq`:

```bash
jq -c 'select(.jobExecutionId == "4812" and .eventType == "batch.step.finished")' batch.jsonl
```

Các ví dụ truy vấn phụ thuộc mapping/index của hệ thống log. Hãy chuẩn hóa tên trường lúc ingest để tránh trường hợp một node dùng `jobExecutionId` dạng chuỗi, node khác dùng số. `jobExecutionId` có cardinality cao; **không nên đặt nó làm Prometheus label hoặc Loki stream label** khi có nhiều execution. Nên giữ ID này trong nội dung event và dùng bộ lọc field khi truy vấn.

### Những câu hỏi dashboard có thể trả lời

| Mục tiêu | Bộ lọc/nhóm dữ liệu |
| --- | --- |
| Tìm tất cả log của một lần chạy | `jobExecutionId` |
| Tìm root cause của step thất bại | `stepExecutionId`, `level=ERROR`, `errorType` |
| Tìm loại skip tăng bất thường | `eventType=batch.item.skipped`, nhóm theo `phase`/`errorType` |
| Xác nhận step kết thúc và số liệu | `eventType=batch.step.finished`, đối chiếu `StepExecution` |
| Kiểm tra restart của một kỳ nghiệp vụ | `jobInstanceId`, so các `jobExecutionId` khác nhau |
| Theo dõi lỗi theo phiên bản deploy | `serviceVersion`, `environment`, `eventType` |

Đếm số bản ghi log `batch.item.skipped` có thể hỗ trợ tìm xu hướng nhưng vẫn cần đối chiếu `StepExecution.skipCount`. Với log phát lại, mất sự kiện hoặc retention khác nhau, hai giá trị không luôn trùng nhau.

## 13. Độ tin cậy và chi phí của pipeline log

Structured JSON dễ xử lý bằng máy nhưng không tự bảo đảm log được lưu bền vững. Một pipeline phổ biến:

```text
Spring Batch process
   -> stdout / JSON appender
   -> container runtime hoặc file log
   -> collector / forwarder
   -> queue / log storage / index
   -> search UI / alerting
```

Một số nguyên tắc thiết kế:

1. **Một JSON object trên một dòng:** stack trace cần được escape thành field JSON; không tự nối chuỗi nhiều dòng làm vỡ log event.
2. **Tránh log mỗi item thành công:** với 10 triệu item, log `INFO` cho từng item gây tốn I/O, CPU, dung lượng index và làm chậm batch. Ưu tiên log ở ranh giới job/step, thời điểm cảnh báo và chu kỳ tiến độ có kiểm soát.
3. **Log lỗi vừa đủ:** skip có thể xảy ra hàng nghìn lần; có thể giới hạn log chi tiết, nhưng counter chính thức vẫn phải lấy từ metadata. Nếu sampling, phải công khai việc log không đại diện đầy đủ cho từng item.
4. **Quy định retention:** giữ summary lifecycle đủ lâu cho audit/điều tra, còn log kỹ thuật chi tiết có thể có thời gian lưu ngắn hơn tùy yêu cầu hệ thống.
5. **Kiểm soát backpressure:** nếu logger/collector bị chậm, chính batch không nên vô tình nghẽn nhiều phút vì một log event không quan trọng. Với async appender, hiểu rõ policy mất log khi queue đầy.
6. **Theo dõi chính pipeline log:** số event bị drop, lỗi gửi, queue depth và khả năng tìm kiếm sau deploy đều quan trọng. Không coi “ứng dụng vẫn chạy” là bằng chứng log đã vào hệ thống.
7. **Tránh gửi trùng:** nếu console log được agent thu gom, không đồng thời cấu hình một appender đẩy cùng event đến cùng storage mà không deduplicate.

### Số liệu tiến độ nên ghi theo chu kỳ

Đối với job chạy hàng giờ, chỉ có `batch.step.started` và `batch.step.finished` sẽ tạo khoảng im lặng dài. Có thể bổ sung `batch.step.progress` mỗi N chunk hoặc mỗi khoảng thời gian phù hợp, với `readCount`, `writeCount`, `commitCount` và timestamp. Đây là tính năng do ứng dụng bổ sung bằng listener hoặc dịch vụ giám sát, không phải một sự kiện JSON tự động của Spring Batch.

**Không suy ra job treo chỉ vì không có log mới**: chunk có thể xử lý rất lâu hoặc đang chờ I/O. Hãy kết hợp liveness của process, timestamp metadata, metric active, transaction và đặc điểm step.

## 14. Quy tắc bảo vệ dữ liệu trong structured log

Khi chuyển từ log text sang JSON có schema tốt, việc tìm và phân tích thông tin trở nên dễ hơn, nhưng cũng dễ làm lộ dữ liệu nếu ghi nguyên object. Trong batch, các nguồn nhạy cảm thường là:

- `JobParameters` chứa API token, mật khẩu, đường dẫn nội bộ, user ID, mã khách hàng, số tài khoản hoặc khóa truy cập.
- `ExecutionContext` chứa checkpoint, dữ liệu tạm, đối tượng được serialize và giá trị nghiệp vụ.
- Item đọc từ file, database, queue hoặc request của đối tác.
- Exception message chứa câu SQL, tên bảng, dữ liệu input hoặc payload bên ngoài.
- Header/message context truyền qua các hệ thống xử lý từ xa.

Thay vì:

```java
log.info("Job parameters: {}", jobExecution.getJobParameters());
log.error("Could not process record {}", item, exception);
```

hãy chỉ ghi các trường được duyệt:

```java
log.atInfo()
   .addKeyValue("eventType", "batch.input.selected")
   .addKeyValue("jobName",
           jobExecution.getJobInstance().getJobName())
   .addKeyValue("inputKind", "daily-order-file")
   .addKeyValue("businessDate", "2026-11-15")
   .log("Selected batch input");
```

`businessDate` là dữ liệu nghiệp vụ minh họa an toàn trong ví dụ; thực tế nên lấy từ tham số đã được validate và cho phép log. Đối với mã khách hàng/item, chỉ log ID nếu hệ thống có chính sách phù hợp; có thể dùng một định danh nội bộ không chứa PII hoặc token hóa trước khi ghi. **Không xem hash thông thường là bảo đảm ẩn danh**, nhất là khi miền giá trị nhỏ hoặc dễ đoán.

Nên phân quyền truy cập log theo môi trường, có retention và cơ chế xóa phù hợp, kiểm soát export, đồng thời redaction ở cả **ứng dụng và pipeline thu nhận** khi cần. Đừng dựa vào việc UI che một trường trong khi dữ liệu gốc vẫn nằm ở backend log.

## 15. Kiểm thử structured log và MDC

Có thể kiểm thử phần dựng correlation context mà không cần khởi chạy toàn bộ job. Ví dụ dưới kiểm tra `StepEventLoggingListener` bằng metadata giả lập của `spring-batch-test` và JUnit Jupiter:

```java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

import static org.junit.jupiter.api.Assertions.*;

class StepEventLoggingListenerTest {

    @AfterEach
    void clearMdc() {
        MDC.clear();
    }

    @Test
    void addsAndRemovesStepCorrelationFields() {
        StepExecution execution =
                MetaDataInstanceFactory.createStepExecution();
        StepEventLoggingListener listener =
                new StepEventLoggingListener();

        listener.beforeStep(execution);
        try {
            assertEquals(execution.getStepName(),
                    MDC.get("stepName"));
            assertEquals(String.valueOf(execution.getId()),
                    MDC.get("stepExecutionId"));
            assertEquals(String.valueOf(
                    execution.getJobExecution().getId()),
                    MDC.get("jobExecutionId"));
        } finally {
            listener.afterStep(execution);
        }

        assertNull(MDC.get("stepExecutionId"));
        assertNull(MDC.get("jobExecutionId"));
    }
}
```

Test này kiểm tra **truyền và dọn MDC ở cùng thread**. Để xác nhận JSON thực sự có `eventType` và số đếm dưới dạng numeric, cần thêm một test tích hợp logger/encoder hoặc thu nhận log output rồi parse thành JSON. Có thể kiểm tra những điểm như:

| Tình huống | Kỳ vọng |
| --- | --- |
| Start/finish của một job | Có `batch.job.started` và `batch.job.finished` với cùng `jobExecutionId` |
| Hai execution của cùng instance | Có **hai** `jobExecutionId` nhưng cùng `jobInstanceId` |
| Step kết thúc sau filter/skip | JSON summary có counter khớp `StepExecution` |
| Retry rồi thành công | Không log sai thành skip cuối cùng |
| Thread pool tái sử dụng thread | Log job sau không thừa ID job trước |
| Worker chạy partition khác | `stepExecutionId` là ID của worker thực thi |
| Exception chứa dữ liệu nhạy cảm | Dữ liệu bị loại/redact khỏi event xuất ra |
| Encoder/collector gặp lỗi | Có tín hiệu vận hành về log bị drop hoặc ingest thất bại |

Khi test cả JSON encoder, tránh so sánh nguyên văn cả dòng vì timestamp, tên thread và thứ tự key có thể thay đổi. Parse JSON và so **field có ý nghĩa**, nhất là `eventType`, correlation IDs, trạng thái và counters.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Log đã là JSON nhưng không có `jobExecutionId` | Chưa đưa ID vào MDC/key-value, hoặc encoder không đọc MDC | Đặt correlation fields trong listener và kiểm tra JSON thực tế |
| Log của hai job bị lẫn ID | MDC tồn tại sau khi thread được tái sử dụng | Dọn/khôi phục MDC trong `finally` hoặc scope callback |
| Log trong `ItemProcessor` không có step ID | Processor chạy trên worker thread khác | Cấu hình propagation theo executor hoặc thêm context ở worker |
| Partition log mang ID step master | Copy MDC master qua mọi worker | Gắn lại ID thực của `StepExecution` từng partition |
| `COMPLETED` có log `ERROR` | Một lỗi đã được retry/skip thành công | Đọc `BatchStatus`, counter và skip policy; phân biệt lỗi tạm thời với thất bại cuối |
| Số lần log skip khác `skipCount` | Log bị sampling, drop, replay hoặc lỗi callback bị nhầm thành skip | Dùng `StepExecution` làm nguồn số liệu đếm chính |
| Trường số bị index dạng chuỗi | Cho mọi số vào MDC (giá trị chuỗi), mapping không thống nhất | Dùng typed `addKeyValue` cho summary, chuẩn hóa mapping tại ingest |
| Chỉ có message, key-value không thấy | Pattern/encoder không hỗ trợ fluent key-value pairs | Bật structured encoder hoặc thêm provider phù hợp |
| Log một sự kiện xuất hai lần | Console và file/collector cùng ingest vào một đích | Rà soát appender và pipeline |
| Structured log không bật khi có `logback-spring.xml` | File tùy chỉnh đang dùng PatternLayout thay vì encoder JSON | Cấu hình structured encoder trong custom Logback |
| Tăng đột biến dung lượng logs | Log mỗi item, kèm object lớn hoặc full stack trace cho mọi retry | Dùng event summary, giới hạn log detail và có retention |
| Không tìm thấy job theo ngày nghiệp vụ | Chỉ ghi timestamp thực thi, thiếu business date/logical key | Thêm trường nghiệp vụ an toàn, không ghi toàn bộ parameters |
| Log thiếu sau crash | Buffer/queue chưa flush hoặc collector không nhận kịp | Theo dõi pipeline, điều chỉnh appender/flush và không thay thế `JobRepository` |

## 17. Tài liệu tham khảo và phạm vi phiên bản

Các ví dụ Java về `JobExecutionListener`, `StepExecutionListener`, `SkipListener`, `JobExecution` và `StepExecution` sử dụng **Spring Batch 5.2.x** cùng Java 17 và SLF4J 2. Spring Batch 6.x có một số thay đổi về package/API, nên điều chỉnh import theo version dự án. Phần cấu hình native structured logging yêu cầu **Spring Boot 3.4 trở lên**; với Boot cũ, dùng encoder JSON được cấu hình tường minh.

- [Spring Boot Reference — Logging, Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot Blog — Structured logging in Spring Boot 3.4](https://spring.io/blog/2024/08/23/structured-logging-in-spring-boot-3-4/)
- [SLF4J Manual — MDC và fluent logging](https://www.slf4j.org/manual.html)
- [SLF4J API — `MDC`](https://www.slf4j.org/api/org/slf4j/MDC.html)
- [Spring Batch 5.2 API — `JobExecutionListener`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobExecutionListener.html)
- [Spring Batch 5.2 API — `StepExecutionListener`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/StepExecutionListener.html)
- [Spring Batch 5.2 API — `SkipListener`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/SkipListener.html)
- [Spring Batch 5.2 Reference — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/intercepting-execution.html)
- [Spring Batch 5.2 Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/5.2/monitoring-and-metrics.html)
- [logstash-logback-encoder — Logback JSON encoder](https://github.com/logfellow/logstash-logback-encoder)

Để structured log thực sự phục vụ vận hành Spring Batch, hãy thống nhất **schema sự kiện**, gắn đúng `jobExecutionId`/`stepExecutionId` vào ngữ cảnh thực thi, ghi lifecycle và kết quả bằng listener, rồi xuất JSON qua encoder phù hợp. Với worker thread và remote partition, cần truyền correlation context rõ ràng và luôn dọn MDC. Khi đọc log, phân biệt **sự kiện** với **metadata đã commit**, dùng `JobRepository` để xác nhận trạng thái/counter và sử dụng log để tìm nguyên nhân. Cách phối hợp đó tạo thành một dòng truy vết có thể tìm kiếm, an toàn và đáng tin cậy từ lúc job bắt đầu đến khi hoàn tất hoặc thất bại.

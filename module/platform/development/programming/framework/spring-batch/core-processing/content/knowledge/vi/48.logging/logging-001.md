# Log ở Job Listener trong Spring Batch

## 1. Mục tiêu của bài học

Trong Spring Batch, một job có thể được khởi chạy bởi scheduler, API nội bộ, câu lệnh vận hành hoặc một job khác. Khi xử lý hàng nghìn hay hàng triệu bản ghi, thông tin “job được gọi” chưa đủ để biết **job có bắt đầu thực thi, kết thúc ở trạng thái nào, mất bao lâu và lỗi nằm ở đâu**.

`JobExecutionListener` là một điểm mở rộng ở cấp job để ghi lại các sự kiện quan trọng ngay trước và sau khi Spring Batch thực thi một `JobExecution`. Đặt log tại đây giúp mỗi lần thực thi có một dấu vết nhất quán, không phải rải những lệnh log khởi đầu/kết thúc ở mọi step.

Trong bài học thuộc nhóm **Logging** của **Spring Batch Core Processing**, bạn sẽ học:

- Phân biệt log từ scheduler/`JobLauncher` với log từ `JobExecutionListener`.
- Sử dụng hai callback `beforeJob` và `afterJob`.
- Ghi log tên job, instance ID, execution ID, tham số nghiệp vụ an toàn, `BatchStatus`, `ExitStatus`, thời lượng và tổng số bản ghi.
- Đăng ký listener với `JobBuilder` trong Spring Batch 5.x.
- Phân loại log `INFO`, `WARN` và `ERROR`; xử lý stack trace và thông tin nhạy cảm.
- Hiểu giới hạn của listener trong các trường hợp job bị từ chối launch, process bị dừng đột ngột, chạy bất đồng bộ hoặc restart.
- Kiểm thử hành vi logging và quan sát kết quả từ một job thực tế.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Batch 5.x và SLF4J. Ở phiên bản khác, một vài API cấu hình có thể thay đổi nhưng cách tổ chức log theo vòng đời execution vẫn tương tự.

## 2. Vị trí của JobExecutionListener trong luồng xử lý

Một luồng đơn giản gồm:

```text
Scheduler / REST / CLI
         |
         | gọi JobLauncher.run(job, parameters)
         v
     JobRepository
         |
         | tạo / xác nhận JobExecution
         v
      Job bắt đầu
         |
         +-- JobExecutionListener.beforeJob(execution)
         |       -> log sự kiện bắt đầu
         |
         +-- Step 1
         |      Reader -> Processor -> Writer
         |
         +-- Step 2
         |      Reader -> Processor -> Writer
         |
         +-- JobExecutionListener.afterJob(execution)
         |       -> log trạng thái cuối, thời lượng, số đếm, lỗi
         |
         v
     Lưu metadata / trả kết quả cho launcher
```

**Điểm cần phân biệt:** listener thuộc vòng đời **JobExecution**, còn scheduler thuộc vòng đời **yêu cầu launch**. Nếu scheduler gọi lại một `JobInstance` đã hoàn tất và `JobLauncher` ném `JobInstanceAlreadyCompleteException`, Spring Batch không tạo execution mới nên các callback job listener không được chạy cho yêu cầu bị từ chối ấy.

Do đó:

- Log trong **scheduler/launch coordinator** trả lời “ai yêu cầu chạy, lúc nào, request có được chấp nhận không?”.
- Log trong **job listener** trả lời “execution nào đã bắt đầu và kết thúc ra sao?”.
- Log trong **step/chunk/item listener** trả lời “giai đoạn nào đọc, ghi, skip hoặc xử lý lỗi gì?”.

Ba nguồn log có thể liên kết bằng tên job, `jobInstanceId`, `jobExecutionId` và một `correlationId` nếu hệ thống yêu cầu.

### Phạm vi của từng callback

| Callback | Thời điểm và dữ liệu | Việc nên làm |
| --- | --- | --- |
| `beforeJob(JobExecution)` | Khi một JobExecution chuẩn bị chạy các step | Ghi nhận thời điểm bắt đầu, execution ID, tên job, kỳ dữ liệu, nguồn kích hoạt nếu có |
| `afterJob(JobExecution)` | Sau khi việc thực thi job kết thúc theo vòng đời thông thường | Ghi trạng thái cuối, mã thoát, thời lượng, số đếm và lỗi chính |
| `beforeStep/afterStep` | Trước/sau từng StepExecution | Ghi chi tiết theo step, cảnh báo step có số lượng bản ghi bất thường |
| `onReadError/onWriteError/onSkip...` | Khi có lỗi thao tác hoặc item bị skip | Phục vụ điều tra lỗi cụ thể; kiểm soát tần suất log |

`JobExecutionListener` không được gọi cho **mọi lần cron kích hoạt**. Nó gắn với một execution thực tế đã đi vào luồng xử lý của job.

## 3. JobInstance và JobExecution trong thông điệp log

Spring Batch phân biệt:

- **`Job`:** định nghĩa công việc, ví dụ `dailyReportJob`.
- **`JobInstance`:** tên job kết hợp với các `JobParameters` được đánh dấu identifying, ví dụ `businessDate=2026-11-15`.
- **`JobExecution`:** một lần cố gắng thực thi instance đó.

Giả sử job tổng hợp ngày 15/11 lần đầu thất bại, sau đó restart thành công:

```text
JobInstance 1201: dailyReportJob + businessDate=2026-11-15
   |
   +-- JobExecution 9001: FAILED
   |
   +-- JobExecution 9002: COMPLETED
```

Nếu chỉ ghi `jobName=dailyReportJob` và `businessDate=2026-11-15`, bạn khó phân biệt log của lần đầu với lần restart. Nếu chỉ ghi `jobExecutionId`, người vận hành lại khó biết execution đang xử lý kỳ dữ liệu nào. Vì vậy nên ghi **cả khóa nghiệp vụ an toàn và execution ID**.

Ví dụ hai dòng log:

```text
event=batch.job.finished job=dailyReportJob instanceId=1201 executionId=9001 businessDate=2026-11-15 status=FAILED
event=batch.job.finished job=dailyReportJob instanceId=1201 executionId=9002 businessDate=2026-11-15 status=COMPLETED
```

Dấu vết này thể hiện rõ một instance có hai execution, không phải hai kỳ nghiệp vụ khác nhau.

## 4. Những trường nên ghi trong job listener

Một thông điệp log có cấu trúc nhất quán sẽ dễ tìm kiếm hơn so với câu văn tùy ý ở từng nơi.

| Trường | Nguồn | Mục đích |
| --- | --- | --- |
| `event` | Giá trị cố định như `batch.job.started` / `batch.job.finished` | Lọc theo loại sự kiện |
| `job` | `execution.getJobInstance().getJobName()` | Nhận diện job |
| `jobInstanceId` | `execution.getJobInstance().getInstanceId()` | Nhận diện kỳ xử lý logic |
| `jobExecutionId` | `execution.getId()` | Nhận diện lần chạy |
| `businessDate` | Whitelist từ `JobParameters` | Nhận diện kỳ dữ liệu |
| `status` | `execution.getStatus()` | Trạng thái cuối ở cấp job |
| `exitCode` | `execution.getExitStatus().getExitCode()` | Kết quả có thể được tùy biến bởi flow/step |
| `durationMs` | Thời điểm bắt đầu và kết thúc execution | Theo dõi SLA, độ trễ |
| `readCount` / `writeCount` / `skipCount` | Tổng từ các `StepExecution` thuộc execution | Theo dõi khối lượng xử lý |

Không ghi nguyên toàn bộ `JobParameters` một cách mặc định: chúng có thể chứa token, thông tin định danh khách hàng, đường dẫn nhạy cảm hoặc dữ liệu nghiệp vụ. Thay vào đó, chọn rõ những field được phép đưa vào log, ví dụ ngày nghiệp vụ hoặc mã lô nội bộ không nhạy cảm.

### BatchStatus và ExitStatus không giống nhau

`BatchStatus` thể hiện trạng thái vòng đời: `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, `STOPPED` và một số trạng thái khác.

`ExitStatus` là mã kết thúc được dùng để đánh giá kết quả và điều hướng flow; mã này có thể được tùy biến, chẳng hạn `NO_DATA`. Một job có thể có `BatchStatus.COMPLETED` và `ExitStatus` mang mã nghiệp vụ khác `COMPLETED`. Khi điều tra, log cả hai sẽ giúp tránh kết luận sai.

## 5. Cài đặt listener với SLF4J

Spring Boot starter thường đã cung cấp cơ chế logging qua SLF4J và một logging backend như Logback. Không cần thêm một hệ thống logging mới chỉ để ghi log từ listener.

Ví dụ triển khai:

```java
package com.example.batch.logging;

import java.time.Duration;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.stereotype.Component;

@Component
public class BatchJobLoggingListener implements JobExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(BatchJobLoggingListener.class);

    @Override
    public void beforeJob(JobExecution execution) {
        String jobName = execution.getJobInstance().getJobName();
        String businessDate =
            execution.getJobParameters().getString("businessDate");

        log.info(
            "event=batch.job.started job={} instanceId={} " +
            "executionId={} businessDate={} status={}",
            jobName,
            execution.getJobInstance().getInstanceId(),
            execution.getId(),
            businessDate,
            execution.getStatus()
        );
    }

    @Override
    public void afterJob(JobExecution execution) {
        String jobName = execution.getJobInstance().getJobName();
        String businessDate =
            execution.getJobParameters().getString("businessDate");

        BatchStatus status = execution.getStatus();
        String exitCode =
            execution.getExitStatus().getExitCode();

        long readCount = 0;
        long writeCount = 0;
        long filterCount = 0;
        long skipCount = 0;

        for (StepExecution step : execution.getStepExecutions()) {
            readCount += step.getReadCount();
            writeCount += step.getWriteCount();
            filterCount += step.getFilterCount();
            skipCount += step.getSkipCount();
        }

        Long durationMs = null;
        if (execution.getStartTime() != null &&
            execution.getEndTime() != null) {

            durationMs = Duration.between(
                execution.getStartTime(),
                execution.getEndTime()
            ).toMillis();
        }

        String message =
            "event=batch.job.finished job={} instanceId={} " +
            "executionId={} businessDate={} status={} exitCode={} " +
            "durationMs={} readCount={} writeCount={} " +
            "filterCount={} skipCount={}";

        Object[] fields = {
            jobName,
            execution.getJobInstance().getInstanceId(),
            execution.getId(),
            businessDate,
            status,
            exitCode,
            durationMs,
            readCount,
            writeCount,
            filterCount,
            skipCount
        };

        if (status == BatchStatus.FAILED) {
            log.error(message, fields);
            logFirstFailure(execution);

        } else if (status == BatchStatus.STOPPED ||
                   status == BatchStatus.UNKNOWN) {
            log.warn(message, fields);

        } else {
            log.info(message, fields);
        }
    }

    private void logFirstFailure(JobExecution execution) {
        List<Throwable> errors =
            execution.getAllFailureExceptions();

        if (errors.isEmpty()) {
            return;
        }

        Throwable first = errors.get(0);

        log.error(
            "event=batch.job.failure executionId={} exceptionType={}",
            execution.getId(),
            first.getClass().getName(),
            first
        );
    }
}
```

Trong ví dụ:

1. `beforeJob` ghi một sự kiện mở đầu cho từng execution.
2. `afterJob` lấy trạng thái cuối và tổng số đếm trên các `StepExecution` thuộc lần chạy đó.
3. Thời lượng chỉ được tính khi cả hai thời điểm có giá trị.
4. `FAILED` được log ở mức `ERROR`; `STOPPED`/`UNKNOWN` ở `WARN`; trạng thái còn lại ở `INFO`.
5. Ví dụ chỉ log stack trace của lỗi đầu tiên để tránh ghi cùng một lỗi hàng chục lần khi nhiều step đã báo exception.

Đoạn `Object[] fields` tương ứng với các dấu `{}` trong SLF4J. Một cấu hình logging khác có thể chuyển sang JSON có field riêng, nhưng phần quan trọng vẫn là tên trường ổn định và thông tin tương quan đầy đủ.

**Về tính riêng tư:** Stack trace có thể chứa thông điệp exception mang dữ liệu nghiệp vụ. Với dữ liệu nhạy cảm, hãy giới hạn quyền truy cập log, loại bỏ nội dung không cần thiết hoặc chỉ ghi mã lỗi đã chuẩn hóa. Không log nguyên request body, token, mật khẩu hay toàn bộ input record.

**Về số đếm:** Các tổng `readCount`, `writeCount` và `skipCount` trên đây thuộc **JobExecution hiện tại**. Khi restart, các execution trước có số đếm riêng. Tổng của một execution không nhất thiết là tổng số bản ghi duy nhất của cả JobInstance qua nhiều lần restart, đặc biệt khi có rollback và xử lý lại.

## 6. Đăng ký listener vào JobBuilder

Chỉ khai báo `@Component` chưa đủ để bảo đảm listener sẽ được dùng bởi job cụ thể. Cần đăng ký listener trong cấu hình `Job`.

Ví dụ một job tasklet đơn giản, có `JobRepository` và transaction manager:

```java
package com.example.batch.config;

import com.example.batch.logging.BatchJobLoggingListener;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class DailyReportJobConfiguration {

    @Bean
    Step dailyReportStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager) {

        return new StepBuilder("dailyReportStep", repository)
            .tasklet((contribution, context) -> {
                // Xử lý báo cáo theo businessDate trong JobParameters.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
    }

    @Bean
    Job dailyReportJob(
            JobRepository repository,
            @Qualifier("dailyReportStep") Step step,
            BatchJobLoggingListener listener) {

        return new JobBuilder("dailyReportJob", repository)
            .start(step)
            .listener(listener)
            .build();
    }
}
```

Từ đó, mỗi `JobExecution` của `dailyReportJob` được thực thi qua Spring Batch sẽ gọi listener tại các điểm vòng đời tương ứng.

Nếu hệ thống có nhiều job và cùng dùng một mẫu log, có thể dùng chung một listener không lưu trạng thái theo từng execution. Tránh đặt `JobExecution` hiện tại vào field của singleton listener, vì các job khác nhau hoặc nhiều execution có thể chạy đồng thời.

### Cấu hình logging ở Spring Boot

Ví dụ `application.yml`:

```yaml
spring:
  batch:
    job:
      enabled: false

logging:
  level:
    root: INFO
    com.example.batch.logging: INFO
```

Đặt `spring.batch.job.enabled=false` nếu ứng dụng muốn scheduler hoặc entry point riêng chủ động gọi `JobLauncher`. Nếu yêu cầu là chạy ngay khi Spring Boot startup, có thể dùng cơ chế tự khởi chạy phù hợp; listener vẫn hoạt động khi job được thực thi.

Đối với production, nên chuyển log đến hệ thống tập trung có khả năng tìm theo `executionId` và `job`. Không nên chỉ dựa vào file log cục bộ của một container có thể bị thay thế.

## 7. Một log mẫu từ JobExecutionListener

Giả sử job có một step, đọc 1.000 bản ghi, ghi 998 bản ghi và skip 2 bản ghi lỗi theo policy đã cấu hình:

```text
INFO  event=batch.job.started job=dailyReportJob instanceId=321 executionId=1001 businessDate=2026-11-15 status=STARTED

INFO  event=batch.job.finished job=dailyReportJob instanceId=321 executionId=1001 businessDate=2026-11-15 status=COMPLETED exitCode=COMPLETED durationMs=4312 readCount=1000 writeCount=998 filterCount=0 skipCount=2
```

Nếu job thất bại trong writer:

```text
INFO  event=batch.job.started job=dailyReportJob instanceId=321 executionId=1002 businessDate=2026-11-15 status=STARTED

ERROR event=batch.job.finished job=dailyReportJob instanceId=321 executionId=1002 businessDate=2026-11-15 status=FAILED exitCode=FAILED durationMs=2830 readCount=600 writeCount=300 filterCount=0 skipCount=0

ERROR event=batch.job.failure executionId=1002 exceptionType=java.lang.IllegalStateException
      ... stack trace ...
```

Các con số trên chỉ minh họa định dạng log. Trong trường hợp chunk retry, rollback hoặc nhiều step, số đếm cần được diễn giải theo metadata cụ thể. Không suy ra tác động cuối cùng lên database chỉ từ `writeCount`: hãy kiểm tra dữ liệu đích khi điều tra sai lệch.

## 8. Log từ listener có thay thế log ở scheduler không?

Không. Ví dụ scheduler gọi:

```java
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .toJobParameters();

jobLauncher.run(dailyReportJob, params);
```

Nếu lần chạy của cùng `JobInstance` đã hoàn tất, yêu cầu sẽ bị từ chối, thường bằng `JobInstanceAlreadyCompleteException`. Vì không có execution mới, listener không ghi thêm dòng `batch.job.started` hoặc `batch.job.finished` nào.

Muốn ghi mọi lần scheduler **cố gắng launch**, cần một lớp gọi launcher có log riêng:

```java
try {
    log.info(
        "event=batch.launch.requested job={} businessDate={}",
        dailyReportJob.getName(),
        businessDate
    );

    JobExecution execution =
        jobLauncher.run(dailyReportJob, parameters);

    log.info(
        "event=batch.launch.accepted job={} executionId={}",
        dailyReportJob.getName(),
        execution.getId()
    );

} catch (JobInstanceAlreadyCompleteException ex) {
    log.info(
        "event=batch.launch.rejected reason=already_completed " +
        "job={} businessDate={}",
        dailyReportJob.getName(),
        businessDate
    );

} catch (JobExecutionAlreadyRunningException ex) {
    log.warn(
        "event=batch.launch.rejected reason=already_running " +
        "job={} businessDate={}",
        dailyReportJob.getName(),
        businessDate
    );
}
```

Đoạn mã giả định `jobLauncher`, `dailyReportJob`, `parameters` và `businessDate` đã được khai báo trong lớp coordinator, cùng các import exception cần thiết.

Để audit chính xác từng attempt, kể cả khi process chết hoặc log bị mất, có thể cần lưu bản ghi yêu cầu launch bền vững riêng. Log trong listener cung cấp thông tin **execution**, còn audit lần launch là một nhu cầu rộng hơn.

## 9. Log lỗi, ngưỡng log và tránh gây nhiễu

### Phân cấp mức log

| Cấp độ | Ví dụ sử dụng |
| --- | --- |
| `INFO` | Job bắt đầu, job hoàn tất, thời lượng, tổng item |
| `WARN` | Job bị dừng có chủ đích, trạng thái chưa rõ, số lượng bản ghi bất thường, yêu cầu launch trùng |
| `ERROR` | Job thất bại, callback gặp lỗi cần điều tra, exception không được xử lý |
| `DEBUG` | Chi tiết tham số được phép ghi, luồng kiểm tra nội bộ hoặc thông tin chẩn đoán tạm thời |
| `TRACE` | Dấu vết rất chi tiết, chỉ bật khi thực sự cần và có giới hạn |

Một số hệ thống coi `STOPPED` là trạng thái hợp lệ do người vận hành chủ động dừng, nên có thể dùng `INFO` thay vì `WARN`. Cấp độ log cần phù hợp với chính sách vận hành, không phải một quy định cứng của Spring Batch.

### Tránh log từng item ở cấp job

Một job xử lý một triệu item có thể làm hệ thống log bị quá tải nếu mỗi bản ghi đều phát một dòng `INFO`. Tại `JobExecutionListener` nên ghi sự kiện tổng hợp. Nếu cần quan sát chi tiết lỗi của item, dùng `SkipListener`, `ItemReadListener` hoặc listener tương ứng ở cấp step, kết hợp rate limiting, sampling và quy tắc ẩn dữ liệu nhạy cảm.

### Không làm thất bại job chỉ vì hệ thống log phụ bị lỗi

Job listener nên thực hiện thao tác nhanh, đơn giản. Việc ghi log SLF4J thông thường không cần mở kết nối mạng trực tiếp trong callback. Tránh gọi API giám sát đồng bộ với timeout dài hoặc ghi một transaction audit phức tạp ngay trong `afterJob`.

Exception phát sinh trong callback có thể ảnh hưởng đến quá trình hoàn tất job hoặc làm khó việc ghi metadata, tùy thời điểm và cách xử lý của framework. Vì vậy, nếu listener gọi thêm hệ thống ngoài, cần kiểm soát lỗi, thời gian chờ và chính sách fail-open/fail-closed theo nhu cầu vận hành.

## 10. Logging khi restart

Một `JobInstance` có thể có nhiều `JobExecution`. Nếu job thất bại và được restart với cùng identifying parameters, listener được gọi cho **execution mới**, nên sẽ có thêm cặp log bắt đầu/kết thúc.

```text
job=dailyReportJob instanceId=321 executionId=1001 status=FAILED
job=dailyReportJob instanceId=321 executionId=1002 status=COMPLETED
```

Cặp log cho thấy quá trình restart đã thành công mà không tạo một JobInstance khác. Những step đã hoàn tất ở execution trước có thể không chạy lại trong execution sau, trừ khi cấu hình cho phép. Vì thế số `readCount` của execution restart có thể nhỏ hơn tổng số bản ghi của toàn bộ kỳ dữ liệu.

Khi tổng hợp báo cáo, đừng cộng `readCount` của mọi execution và coi đó là số bản ghi duy nhất đã xử lý. Số item có thể bị đọc lại do rollback/restart; cần dùng thông tin dữ liệu nghiệp vụ và trạng thái step để diễn giải đúng.

## 11. Vấn đề thread, MDC và launcher bất đồng bộ

### SLF4J MDC

MDC (Mapped Diagnostic Context) cho phép thêm các khóa như `jobExecutionId` vào log mà không phải viết lặp tất cả trường trong mọi câu lệnh.

Ví dụ:

```java
import org.slf4j.MDC;

try (MDC.MDCCloseable ignored = MDC.putCloseable(
        "jobExecutionId",
        String.valueOf(execution.getId()))) {

    log.info(
        "event=batch.job.started job={}",
        execution.getJobInstance().getJobName()
    );
}
```

Đoạn này đặt MDC chỉ trong phạm vi khối `try`; kết thúc khối sẽ bỏ giá trị MDC vừa thêm. Đây là cách an toàn để listener không để lại correlation ID cho một job khác trong thread được tái sử dụng.

**Quan trọng:** MDC thường gắn với thread. Việc đặt MDC trong `beforeJob` rồi xóa ngay sau callback **không tự động khiến mọi log ở step/worker thread có cùng context**. Nếu cần MDC xuyên suốt job đa luồng hoặc dùng async executor, phải thiết kế truyền context sang các thread liên quan hoặc ghi trực tiếp `jobExecutionId` từ execution context ở điểm phát log.

Khi log cần được liên kết bền vững, các ID lưu trong metadata Batch và tham số non-identifying an toàn đáng tin cậy hơn việc chỉ dựa vào ThreadLocal.

### Launcher bất đồng bộ

Một số cấu hình `JobLauncher` chạy job trên executor bất đồng bộ. Khi đó:

- Scheduler gọi `jobLauncher.run(...)` và có thể nhận JobExecution còn `STARTING` hoặc `STARTED`.
- Listener được chạy trên luồng thực thi job, không nhất thiết là luồng scheduler.
- Dòng `batch.launch.accepted` xuất hiện không có nghĩa `batch.job.finished` đã được ghi.
- Muốn biết kết quả cuối cần listener `afterJob`, `JobExplorer` hoặc hệ thống quan sát metadata.

Không ghi `COMPLETED` ngay khi lời gọi launcher trả về mà chưa có bằng chứng execution đã hoàn tất.

## 12. Những trường hợp listener không thể ghi log

Listener ghi đúng sự kiện mà nó được gọi, nhưng không bao phủ mọi loại lỗi hạ tầng:

| Trường hợp | Khả năng ghi log từ JobExecutionListener |
| --- | --- |
| Execution chạy và kết thúc bình thường | `beforeJob` và `afterJob` được gọi theo vòng đời thông thường |
| Job thất bại trong step | Thông thường `afterJob` vẫn chạy, có thể ghi `FAILED` và lỗi |
| Job bị từ chối do instance đã `COMPLETED` | Không tạo execution mới, không có callback tương ứng |
| Job bị từ chối vì execution khác đang chạy | Không có callback job listener cho yêu cầu bị từ chối |
| Tham số sai và launcher từ chối trước khi chạy | Không bảo đảm có callback |
| JVM/container bị kill đột ngột | Không bảo đảm `afterJob` kịp chạy |
| Logging backend mất kết nối hoặc log bị drop | Callback có thể chạy nhưng log vẫn không được lưu |
| Listener chưa được đăng ký vào job | Không có log từ listener dù job vẫn chạy |
| Job không được scheduler kích hoạt | Không có execution để listener ghi log |

Để giám sát toàn hệ thống, kết hợp log listener, log launch coordinator, metadata `JobRepository` và kiểm tra **kỳ đã đến hạn nhưng chưa có execution thành công**. Cảnh báo “không có kết quả đúng giờ” giúp phát hiện trường hợp scheduler không chạy dù không có log `ERROR`.

## 13. Test log ở JobExecutionListener

Không cần khởi chạy cả batch job chỉ để kiểm tra listener tạo đúng dòng log. Có thể khởi tạo một `JobExecution` trong test và dùng `OutputCaptureExtension` của Spring Boot để bắt output từ logging backend.

Ví dụ JUnit 5:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class BatchJobLoggingListenerTest {

    private final BatchJobLoggingListener listener =
        new BatchJobLoggingListener();

    @Test
    void logsJobStartWithBusinessKey(CapturedOutput output) {
        JobInstance instance =
            new JobInstance(42L, "dailyReportJob");

        JobParameters parameters =
            new JobParametersBuilder()
                .addString("businessDate", "2026-11-15", true)
                .toJobParameters();

        JobExecution execution =
            new JobExecution(instance, parameters);

        execution.setStatus(BatchStatus.STARTED);

        listener.beforeJob(execution);

        assertThat(output.getOut())
            .contains("event=batch.job.started")
            .contains("job=dailyReportJob")
            .contains("businessDate=2026-11-15");
    }

    @Test
    void logsCompletedJob(CapturedOutput output) {
        JobInstance instance =
            new JobInstance(43L, "dailyReportJob");

        JobParameters parameters =
            new JobParametersBuilder()
                .addString("businessDate", "2026-11-16", true)
                .toJobParameters();

        JobExecution execution =
            new JobExecution(instance, parameters);

        execution.setStatus(BatchStatus.COMPLETED);

        listener.afterJob(execution);

        assertThat(output.getOut())
            .contains("event=batch.job.finished")
            .contains("status=COMPLETED")
            .contains("readCount=0");
    }
}
```

Test ở trên chứng minh logic tạo thông điệp log với một execution giả lập. Cần cấu hình backend log để console output được capture theo môi trường test. Việc `JobExecution` ở ví dụ không có ID thực từ repository là bình thường vì test không chạy qua `JobLauncher`.

Đối với integration test, dùng `spring-batch-test` để chạy job với `JobRepository` test và xác nhận:

1. Listener được đăng ký vào đúng job.
2. Lần chạy thành công phát một sự kiện bắt đầu và một sự kiện kết thúc với `BatchStatus.COMPLETED`.
3. Lần chạy thất bại phát sự kiện kết thúc `FAILED` và thông tin lỗi phù hợp.
4. Restart tạo log có `jobExecutionId` mới nhưng giữ `jobInstanceId`.
5. Yêu cầu chạy lại instance đã hoàn tất bị launcher từ chối và **không** tạo log bắt đầu của execution mới.
6. Khi job chạy bất đồng bộ, trạng thái kết thúc được ghi khi execution hoàn tất thay vì ngay sau khi scheduler phát lệnh.

Có thể assert cả dữ liệu metadata của `JobExecution` và các dòng log liên quan để chắc rằng thông tin quan sát phản ánh đúng trạng thái thực thi.

## 14. Thiết kế log cho vận hành và tìm kiếm

Một quy ước dễ dùng là mỗi sự kiện gồm các cặp `key=value` hoặc các field JSON có tên ổn định. Nếu log được thu thập bởi hệ thống có hỗ trợ structured logging, nên lưu `jobExecutionId` thành trường riêng để truy vấn theo ID.

Ví dụ dạng JSON minh họa:

```json
{
  "event": "batch.job.finished",
  "job": "dailyReportJob",
  "jobInstanceId": 321,
  "jobExecutionId": 1001,
  "businessDate": "2026-11-15",
  "status": "COMPLETED",
  "exitCode": "COMPLETED",
  "durationMs": 4312,
  "readCount": 1000,
  "writeCount": 998,
  "skipCount": 2
}
```

Mục tiêu là **dễ tương quan và dễ thống kê**, không bắt buộc log phải dùng JSON. Nếu dùng định dạng chữ, hãy giữ thứ tự và tên field nhất quán.

Các dashboard nên theo dõi thời lượng job theo ngày, tỷ lệ `FAILED`, số lần restart, số bản ghi đọc/ghi/skip và kỳ nghiệp vụ chưa hoàn tất trước hạn SLA. Không nên dùng các ID biến động cao như `jobExecutionId` làm label cho metric time series nếu hệ thống giám sát không đáp ứng cardinality lớn; ID nên nằm trong log, trace và metadata.

## 15. Những lỗi phổ biến

| Dấu hiệu | Nguyên nhân có thể | Cách giải quyết |
| --- | --- | --- |
| Job chạy nhưng không thấy log listener | Quên `.listener(listener)` trong `JobBuilder` | Đăng ký listener vào job |
| Chỉ thấy log bắt đầu, không có log kết thúc | Process bị kill, logging lỗi hoặc listener exception | Đối chiếu JobRepository, logs container, health/sự cố hạ tầng |
| Scheduler bị từ chối mà không có log listener | Không có JobExecution mới | Log lỗi launch ở coordinator |
| Log `COMPLETED` dù job chưa xong | Nhầm launcher accepted với job finished khi async | Ghi trạng thái cuối từ `afterJob` hoặc metadata |
| Không phân biệt được restart | Chỉ log job name | Ghi cả `jobInstanceId` và `jobExecutionId` |
| Log chứa token hoặc dữ liệu cá nhân | In toàn bộ `JobParameters`/exception | Whitelist, mask/redact trường nhạy cảm |
| Log bị nhân nhiều dòng trên một triệu item | Log `INFO` mỗi item | Dùng log tổng hợp ở job, chọn lọc log lỗi ở item |
| MDC sai giữa các job hoặc thread | Quên dọn MDC hoặc không truyền context | Dùng try-with-resources và truyền context có kiểm soát |
| Số `readCount` không bằng số record cuối ở DB | Filter, skip, rollback, restart hoặc logic nghiệp vụ | Đối chiếu số đếm step với dữ liệu đích |
| Listener gây lỗi phụ làm khó trạng thái batch | Gọi hệ ngoài trong callback mà không xử lý lỗi | Giữ callback nhẹ, có retry/monitoring ngoài luồng nếu cần |
| Không thấy job nào chạy trong ngày | Scheduler không trigger, thiếu quyền hoặc cấu hình sai | Monitor kỳ dự kiến và audit launch ngoài listener |

## 16. Bài tập thực hành

Hãy tạo job `dailyInventoryJob` có hai step: đọc và chuẩn hóa tồn kho, sau đó lưu bản tổng hợp. Đăng ký một `JobExecutionListener` ghi log bắt đầu và kết thúc với các field: `job`, `jobInstanceId`, `jobExecutionId`, `businessDate`, `status`, `exitCode`, `durationMs`, `readCount`, `writeCount` và `skipCount`.

Chạy bốn kịch bản: job hoàn tất thành công; step ghi dữ liệu ném exception; restart cùng kỳ dữ liệu sau lỗi; scheduler gửi lại kỳ đã hoàn tất. Hãy so sánh log listener với metadata của JobRepository và log ở coordinator. Xác định kịch bản nào **có yêu cầu launch nhưng không có callback listener**, kịch bản nào có **nhiều JobExecution của cùng JobInstance**.

Sau đó bổ sung `correlationId` non-identifying vào tham số job, dùng nó trong log theo nguyên tắc không lộ dữ liệu nhạy cảm. Nếu ứng dụng có nhiều thread, kiểm tra xem MDC có truyền đến các thread xử lý đúng như thiết kế hay không.

## 17. Tổng kết

`JobExecutionListener` là điểm tập trung phù hợp để log **vòng đời một lần thực thi job**. `beforeJob` cung cấp dấu vết bắt đầu; `afterJob` ghi trạng thái cuối, thời lượng, số đếm và lỗi. Log nên có khóa nghiệp vụ, JobInstance ID và JobExecution ID để phân biệt job theo kỳ với các lần restart. Listener cần được đăng ký vào `JobBuilder`, giữ xử lý ngắn gọn, tránh lộ thông tin nhạy cảm và không giả định mọi yêu cầu scheduler đều tạo JobExecution. Kết hợp listener log với log launch và metadata Spring Batch sẽ giúp hệ thống theo dõi, điều tra và vận hành batch đáng tin cậy hơn.

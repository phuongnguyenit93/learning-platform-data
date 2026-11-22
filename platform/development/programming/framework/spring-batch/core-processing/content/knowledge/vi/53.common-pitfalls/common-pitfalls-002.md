# Chạy lại job COMPLETED như restart: lỗi thường gặp trong Spring Batch

## 1. Bối cảnh và triệu chứng

Một tình huống phổ biến trong vận hành Spring Batch:

1. Một job nhập dữ liệu đã chạy xong với trạng thái `COMPLETED`.
2. Người vận hành phát hiện báo cáo thiếu trường hoặc nguồn được điều chỉnh.
3. Họ gửi lại **cùng tên job và cùng tham số định danh**, mong job “restart để chạy lại”.
4. Spring Batch từ chối yêu cầu bằng ngoại lệ `JobInstanceAlreadyCompleteException`.

Thông báo thường có ý nghĩa tương tự:

```text
A job instance already exists and is complete for identifying parameters
```

Đây không phải sự cố tự nhiên của `JobRepository`. **Spring Batch cố ý không cho restart một `JobInstance` đã hoàn tất.** Cơ chế này bảo vệ một kỳ xử lý đã hoàn thành khỏi việc bị thực thi lặp ngoài ý muốn.

Bài học thuộc nhóm **Lỗi thường gặp** của **Spring Batch Core Processing**, tập trung vào chủ đề **“Chạy lại job COMPLETED như restart”**. Sau bài học, bạn sẽ:

- Hiểu chính xác quan hệ giữa `Job`, `JobParameters`, `JobInstance` và `JobExecution`.
- Phân biệt **restart một instance chưa hoàn tất** và **chạy một instance mới để tái xử lý dữ liệu**.
- Biết vì sao cùng identifying parameters bị từ chối khi instance đã `COMPLETED`.
- Không dùng timestamp hoặc `run.id` ngẫu nhiên để vượt qua lỗi một cách thiếu kiểm soát.
- Chọn hướng xử lý có kiểm soát khi dữ liệu đã hoàn thành thật sự cần làm lại.
- Thiết kế writer idempotent, audit, checkpoint và kiểm thử để tránh ghi trùng.
- Xử lý đúng lỗi trong scheduler, API vận hành và ứng dụng Spring Boot.

Các ví dụ sử dụng Java 17+, Spring Boot 3.x và Spring Batch 5.x. Nguyên tắc về JobInstance và restart tương tự ở nhiều phiên bản khác, nhưng một số API và schema metadata có thể khác.

## 2. Bốn khái niệm không được nhầm

Trước tiên, cần xác định **đối tượng nào** đang được chạy lại.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Job` | Định nghĩa logic các step | `dailySettlementJob` |
| `JobParameters` | Tập tham số cung cấp khi khởi chạy; có trường identifying và non-identifying | `businessDate=2026-11-15` |
| `JobInstance` | Danh tính của **một kỳ xử lý logic**: tên job + identifying parameters | Đối soát ngày 15/11/2026 |
| `JobExecution` | **Một lần cố gắng thực thi** của JobInstance | Lần đầu lỗi, lần sau restart thành công |

Mô hình:

```text
Job: dailySettlementJob
         |
         +-- JobInstance 1001
         |   identifying: businessDate=2026-11-15
         |       |
         |       +-- JobExecution 5001: FAILED
         |       +-- JobExecution 5002: COMPLETED
         |
         +-- JobInstance 1002
             identifying: businessDate=2026-11-16
                 |
                 +-- JobExecution 5003: COMPLETED
```

Hai execution 5001 và 5002 thuộc **cùng JobInstance**, vì chúng cùng xử lý một kỳ nghiệp vụ. Execution 5003 thuộc một instance khác do `businessDate` khác.

Với instance 1001, sau khi execution 5002 đã `COMPLETED`, gửi lại cùng tham số định danh để “restart lần thứ ba” sẽ bị từ chối.

### Công thức định danh JobInstance

```text
JobInstance identity
    = jobName + identifying JobParameters
```

Công thức này không có nghĩa mọi tham số đều dùng để phân biệt instance. Chỉ những tham số được đánh dấu **identifying** mới đóng góp vào định danh.

Ví dụ:

```java
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedAt", "2026-11-15T18:10:00Z", false)
    .toJobParameters();
```

- `businessDate` là identifying: cùng ngày nghiệp vụ ⇒ cùng instance.
- `requestedAt` là non-identifying: có thể thay đổi giữa các yêu cầu mà không tạo danh tính instance mới.

**Hậu quả:** Nếu job đã `COMPLETED` cho `businessDate=2026-11-15`, việc thay `requestedAt` không làm job restart hay chạy mới. Spring Batch vẫn nhận thấy instance cũ đã hoàn tất.

## 3. Thế nào là restart và thế nào là reprocess?

Đây là điểm cốt lõi của bài.

### Restart

**Restart** là tiếp tục một `JobInstance` đã có lần chạy không hoàn tất thành công, thường do trạng thái `FAILED` hoặc `STOPPED`, nếu cấu hình job và metadata cho phép.

Ví dụ:

```text
Tên job: dailySettlementJob
Identifying parameters: businessDate=2026-11-15

JobExecution 5001 -> FAILED
  stepA -> COMPLETED
  stepB -> FAILED

Restart cùng identifying parameters:
JobExecution 5002 -> COMPLETED
  stepA -> thường được bỏ qua
  stepB -> được chạy lại theo checkpoint/restart state
```

Spring Batch dựa trên `JobRepository` và `ExecutionContext` để xác định những step đã hoàn thành và trạng thái nào cần khôi phục.

### Reprocess hoặc rerun có chủ đích

**Reprocess** nghĩa là xử lý lại dữ liệu đã hoàn tất theo một quyết định nghiệp vụ mới: ví dụ nguồn được sửa, logic tính toán đổi hoặc cần tái tạo báo cáo. Với một instance `COMPLETED`, đây **không phải restart**.

Nếu muốn Spring Batch thực thi một lần mới, cần định nghĩa **JobInstance mới** qua một bộ identifying parameters khác hoặc một job name khác theo thiết kế có chủ đích. Đồng thời ứng dụng phải định nghĩa điều gì xảy ra với kết quả cũ.

Ví dụ:

```text
JobInstance 1001:
  businessDate=2026-11-15
  revision=1
  JobExecution -> COMPLETED

JobInstance 1002 (reprocess có kiểm soát):
  businessDate=2026-11-15
  revision=2
  JobExecution -> COMPLETED
```

Hai instance cùng liên quan ngày 15/11 nhưng phiên bản xử lý khác nhau. **Revision phải có ý nghĩa nghiệp vụ, được quản lý và audit**, không phải một giá trị ngẫu nhiên sinh chỉ để tránh exception.

### Bảng quyết định nhanh

| Trạng thái trước | Mong muốn | Thao tác phù hợp |
| --- | --- | --- |
| Chưa có instance | Chạy kỳ mới | Launch với business key của kỳ |
| `FAILED`, có thể restart | Tiếp tục kỳ cũ sau khi sửa lỗi | Launch lại cùng identifying parameters |
| `STOPPED`, đủ điều kiện restart | Tiếp tục kỳ đã dừng | Restart cùng identifying parameters |
| `STARTED` hoặc `STARTING` | Người dùng gửi trùng | Theo dõi execution cũ, không chạy chồng |
| `COMPLETED` | Scheduler gửi lại không có thay đổi nghiệp vụ | Bỏ qua như duplicate hợp lệ |
| `COMPLETED` | Muốn sửa lại kết quả đã công bố | Quy trình reprocess có phiên bản, chiến lược dữ liệu đích và audit |
| `COMPLETED` | Muốn chạy một kỳ khác | Thay khóa nghiệp vụ theo kỳ mới |

## 4. Vì sao Spring Batch từ chối job COMPLETED?

Khi gọi:

```java
JobExecution execution =
    jobLauncher.run(dailySettlementJob, parameters);
```

Spring Batch sẽ dùng repository để tìm `JobInstance` có tên job và identifying parameters tương ứng. Khi một JobInstance đã hoàn tất, job launcher không tạo một JobExecution mới để chạy lại cùng instance. Yêu cầu có thể nhận ngoại lệ:

```java
org.springframework.batch.core.repository
    .JobInstanceAlreadyCompleteException
```

Đây là một quy tắc bảo vệ dữ liệu. Nếu mỗi yêu cầu chạy lại được chấp nhận, hệ thống có thể:

- Ghi trùng giao dịch hoặc bản ghi tính tiền.
- Phát lại email, thông báo hay event đã gửi.
- Tính tổng doanh thu hai lần.
- Ghi đè báo cáo cũ mà không có audit.
- Gây xung đột với kỳ xử lý tiếp theo.
- Tạo kết quả không thể giải thích vì nguồn đã thay đổi.

Bảo vệ ở cấp JobInstance không tự động bảo đảm exactly-once ở mọi hệ thống ngoài, nhưng nó ngăn một nguồn chạy trùng phổ biến.

### Ngoại lệ không phải lúc nào cũng chứng minh scheduler bị lỗi

Nếu scheduler dùng cron hàng ngày nhưng vì cấu hình sai luôn gửi cùng `businessDate`, lần đầu job chạy thành công; các lần sau bị từ chối. Ở cấp Spring Batch, quy tắc bảo vệ đang làm đúng việc. **Lỗi nằm ở logic tính kỳ dữ liệu của scheduler**, không phải ở JobRepository.

Ngược lại, nếu người vận hành cố ý gửi lại cùng kỳ để kiểm tra trạng thái, có thể xem `JobInstanceAlreadyCompleteException` như một câu trả lời hợp lệ: “kỳ này đã hoàn tất, không khởi chạy lại”.

## 5. Ví dụ: cùng parameters sau COMPLETED

Giả sử định nghĩa:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .toJobParameters();

JobExecution first =
    jobLauncher.run(dailySettlementJob, parameters);
```

Nếu `first.getStatus() == BatchStatus.COMPLETED`, thì lời gọi:

```java
JobExecution second =
    jobLauncher.run(dailySettlementJob, parameters);
```

không tạo execution mới; thay vào đó launcher sẽ từ chối vì instance đã hoàn tất.

Cũng không giải quyết được bằng cách chỉ thêm một tham số **non-identifying**:

```java
JobParameters later = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedAt", "2026-11-16T03:00:00Z", false)
    .toJobParameters();
```

Vì identifying part vẫn giống nhau, Spring Batch vẫn tìm cùng JobInstance đã `COMPLETED`.

## 6. Một lỗi nguy hiểm: thêm run.id hoặc timestamp cho mọi lần chạy

Một “cách chữa” thường thấy:

```java
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addLong("run.id", System.currentTimeMillis())
    .toJobParameters();
```

Với phương thức builder mặc định, tham số thêm vào là identifying nếu không chỉ định khác. Khi `run.id` thay đổi, mỗi lần có thể trở thành một **JobInstance mới** dù vẫn xử lý ngày 15/11.

Kết quả:

```text
dailySettlementJob + date=2026-11-15 + run.id=101
    -> JobInstance A, COMPLETED

dailySettlementJob + date=2026-11-15 + run.id=102
    -> JobInstance B, COMPLETED

dailySettlementJob + date=2026-11-15 + run.id=103
    -> JobInstance C, COMPLETED
```

Job chạy lại được, nhưng đây là **ba instance khác nhau**, không phải restart. Nếu writer không idempotent, dữ liệu có thể bị ghi ba lần.

**Không nên tăng run.id tự động chỉ để “vượt qua” ngoại lệ** khi bài toán thật là tiếp tục instance đã failed hoặc ngăn xử lý lại một kỳ đã completed.

### JobParametersIncrementer và startNextInstance

Spring Batch có cơ chế `JobParametersIncrementer` và API liên quan đến **start next instance**, ví dụ một incrementer tăng `run.id`. Đây là công cụ để khởi chạy **JobInstance tiếp theo** bằng tham số đã thay đổi, chứ không phải để restart instance đã hoàn tất.

| Hành động | Ý nghĩa |
| --- | --- |
| `JobLauncher.run(job, sameIdentifyingParameters)` sau FAILED | Có thể restart instance hiện có |
| `JobLauncher.run(job, sameIdentifyingParameters)` sau COMPLETED | Bị từ chối |
| `JobOperator.startNextInstance(jobName)` với incrementer | Tạo instance tiếp theo theo quy tắc incrementer |
| Chạy với `revision=2` identifying | Instance mới theo phiên bản xử lý nghiệp vụ |

Nếu incrementer chỉ tăng một ID mà không mô tả kỳ dữ liệu, ứng dụng vẫn cần biết chính xác nguồn nào sẽ được xử lý và dữ liệu đích được cập nhật ra sao.

## 7. Tình huống cần làm lại dữ liệu đã COMPLETED

Không phải mọi yêu cầu “rerun” đều sai. Có trường hợp nghiệp vụ chính đáng:

1. File ngày 15/11 bị thiếu một phần dữ liệu và sau đó nhận được bản nguồn đúng.
2. Công thức tính hoa hồng có lỗi, cần tái tính kỳ cũ.
3. Kết quả xuất báo cáo bị hỏng trong hệ thống lưu file ngoài Batch.
4. Một nguồn tham chiếu (tỷ giá, danh mục, chính sách) đã được điều chỉnh.
5. Người dùng cần tạo một **bản báo cáo mới**, giữ bản cũ để đối chiếu.

Trong các trường hợp đó, cần một quy trình **reprocess có chủ đích**, không đánh lừa cơ chế restart.

Một mô hình có thể dùng các identifying parameters:

```java
JobParameters reprocessParameters =
    new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("revision", 2L, true)
        .addString("requestedBy", "operations", false)
        .addString("reasonCode", "SOURCE_CORRECTION", false)
        .toJobParameters();
```

`revision=2` được quản lý bởi hệ thống vận hành như một phiên bản hợp lệ. Nó tạo JobInstance khác với `revision=1`.

Nhưng thay `revision` **không tự làm dữ liệu đích đúng**. Writer phải có chính sách rõ:

- Ghi vào bảng staging theo phiên bản, sau đó kiểm tra và publish.
- Upsert/replace kết quả của kỳ theo khóa duy nhất.
- Ghi một version mới và chuyển con trỏ “active version” có kiểm soát.
- Dùng event bù trừ (compensation) khi tác động cũ không thể rollback.
- Chặn thông báo/thanh toán trùng bằng business idempotency key.

Một bản ghi revision mới có thể được tạo để tái tính, nhưng không đồng nghĩa được gửi email hoặc trừ tiền lần hai.

## 8. Thiết kế reprocess an toàn theo phiên bản

Một pipeline phù hợp:

```text
       Yêu cầu reprocess ngày D, revision R
                       |
                       v
             Xác thực quyền và lý do
                       |
                       v
              Chốt source snapshot
              checksum/rule version
                       |
                       v
           Tạo JobInstance mới: (D,R)
                       |
                       v
                Ghi vào staging
                       |
                       v
               Kiểm tra dữ liệu
                       |
                     PASS?
                  /         \
                Có           Không
                |              |
                v              v
       Publish có kiểm soát   Giữ kết quả cũ
       / thay active version  + báo lỗi
                |
                v
       Audit revision, execution,
       source hash và kết quả
```

Bảng dữ liệu minh họa:

```sql
CREATE TABLE settlement_result_version (
    business_date DATE NOT NULL,
    revision BIGINT NOT NULL,
    account_id VARCHAR(100) NOT NULL,
    net_amount DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (business_date, revision, account_id)
);

CREATE TABLE settlement_active_version (
    business_date DATE PRIMARY KEY,
    revision BIGINT NOT NULL
);
```

Khi chạy reprocess, writer ghi `(business_date, revision, account_id)` mới vào staging/result-version. Sau khi đối soát thành công, hệ thống mới cập nhật bảng active version hoặc thay thế kết quả hiện hành trong transaction phù hợp.

Thiết kế này giúp:

- Truy vấn được kết quả cũ.
- Không tự phát sinh duplicate trong một phiên bản.
- Có thể so sánh chênh lệch giữa các revision.
- Có lịch sử kiểm tra và rollback nghiệp vụ có kiểm soát.
- Phân biệt rõ **lần chạy kỹ thuật** với **phiên bản dữ liệu được công bố**.

Nếu hệ thống đã có bảng đích không hỗ trợ version, lựa chọn upsert hoặc replace cũng có thể phù hợp. Nhưng phải kiểm soát foreign key, transaction, tác động downstream và trường hợp job dừng giữa quá trình thay thế dữ liệu.

## 9. Phân biệt restart với reprocess trong scheduler

Scheduler thường phát kỳ nghiệp vụ theo ngày/giờ:

```text
Cron 01:10 ngày 16/11/2026
      |
      v
businessDate = 2026-11-15
      |
      v
dailySettlementJob + date=2026-11-15
```

Yêu cầu đầu tiên được chấp nhận. Nếu scheduler vô tình phát lại cùng kỳ vào 01:15:

- Nếu execution trước đang chạy, có thể nhận `JobExecutionAlreadyRunningException`.
- Nếu execution trước `COMPLETED`, nhận `JobInstanceAlreadyCompleteException`.
- Nếu execution trước `FAILED`, có thể restart, tùy cấu hình job và chính sách điều phối.

Scheduler cần ghi các outcome khác nhau, không xử lý bằng một `catch(Exception)` rồi tự tăng timestamp.

Một service điều phối có thể trả về trạng thái nghiệp vụ:

| Trạng thái launch | Ý nghĩa cho scheduler |
| --- | --- |
| `ACCEPTED_NEW` | Một JobInstance mới được khởi chạy |
| `ACCEPTED_RESTART` | Một JobExecution mới của instance chưa hoàn tất đã được tạo |
| `ALREADY_RUNNING` | Có execution đang chạy, không nên phát thêm |
| `ALREADY_COMPLETED` | Kỳ đã hoàn tất, bỏ qua trigger trùng |
| `RESTART_REJECTED` | Cần kiểm tra cấu hình/trạng thái |
| `INVALID_PARAMETERS` | Cần sửa request |
| `UNKNOWN_ERROR` | Cần đối soát JobRepository trước khi retry |

Những chuỗi trên là **mã do ứng dụng định nghĩa**, không phải enum chuẩn của Spring Batch. Khi một launcher chạy bất đồng bộ, việc request được chấp nhận không chứng minh job đã hoàn tất. Phải theo dõi trạng thái cuối của JobExecution.

## 10. Xử lý JobInstanceAlreadyCompleteException đúng cách

Một pattern an toàn là phân loại ngoại lệ và báo lại thông tin rõ cho người dùng/hệ thống điều phối:

```java
import java.time.LocalDate;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class SettlementLaunchService {

    private static final Logger log =
        LoggerFactory.getLogger(SettlementLaunchService.class);

    private final JobLauncher launcher;
    private final Job settlementJob;

    public SettlementLaunchService(
            JobLauncher launcher,
            @Qualifier("dailySettlementJob") Job settlementJob) {
        this.launcher = launcher;
        this.settlementJob = settlementJob;
    }

    public LaunchResult launchScheduled(LocalDate businessDate) {
        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", businessDate.toString(), true)
            .toJobParameters();

        try {
            JobExecution execution =
                launcher.run(settlementJob, parameters);

            log.info(
                "event=batch.launch.accepted job={} date={} " +
                "instanceId={} executionId={} status={}",
                settlementJob.getName(),
                businessDate,
                execution.getJobInstance().getInstanceId(),
                execution.getId(),
                execution.getStatus()
            );

            // Không suy ra SUCCESS từ việc launcher.run() trả về;
            // launcher có thể bất đồng bộ.
            return new LaunchResult(
                "ACCEPTED",
                execution.getId()
            );

        } catch (JobInstanceAlreadyCompleteException ex) {
            log.info(
                "event=batch.launch.skipped reason=already_completed " +
                "job={} date={}",
                settlementJob.getName(),
                businessDate
            );
            return new LaunchResult("ALREADY_COMPLETED", null);

        } catch (JobExecutionAlreadyRunningException ex) {
            log.info(
                "event=batch.launch.skipped reason=already_running " +
                "job={} date={}",
                settlementJob.getName(),
                businessDate
            );
            return new LaunchResult("ALREADY_RUNNING", null);

        } catch (JobRestartException |
                 JobParametersInvalidException ex) {
            log.error(
                "event=batch.launch.rejected job={} date={}",
                settlementJob.getName(),
                businessDate,
                ex
            );
            return new LaunchResult("REJECTED", null);

        } catch (Exception ex) {
            log.error(
                "event=batch.launch.error job={} date={}",
                settlementJob.getName(),
                businessDate,
                ex
            );
            // Không tự tạo run.id để retry.
            return new LaunchResult("UNKNOWN_ERROR", null);
        }
    }

    public record LaunchResult(String outcome, Long executionId) {
    }
}
```

Đoạn mã minh họa cách ghi nhận kết quả yêu cầu launch, không thay thế API giám sát. `UNKNOWN_ERROR` có thể bao gồm lỗi hạ tầng xảy ra sau khi JobExecution đã được tạo nhưng phía gọi chưa nhận được phản hồi; cần đối soát repository trước khi kết luận job chưa chạy.

Trường hợp `ALREADY_COMPLETED` đối với một trigger trùng được xử lý như **kỳ đã hoàn tất**, không tự động ghi lỗi hệ thống nghiêm trọng. Nếu yêu cầu đến từ thao tác reprocess có phê duyệt, phải dùng một API/đường xử lý khác để tạo revision mới.

## 11. Vì sao JobRestartException không phải JobInstanceAlreadyCompleteException?

Một số nhóm ngoại lệ liên quan đến trạng thái và cấu hình:

| Ngoại lệ | Tình huống điển hình | Hướng kiểm tra |
| --- | --- | --- |
| `JobInstanceAlreadyCompleteException` | Instance cùng identifying parameters đã hoàn tất | Không restart; bỏ qua duplicate hoặc thiết kế reprocess mới |
| `JobExecutionAlreadyRunningException` | Instance đang có execution hoạt động | Chờ execution cũ, không phát trùng |
| `JobRestartException` | Restart bị cấm hoặc không hợp lệ vì cấu hình/trạng thái | Kiểm tra `preventRestart()`, Step state, metadata |
| `JobParametersInvalidException` | Request thiếu hoặc sai tham số | Sửa tham số theo JobParametersValidator |
| Exception hạ tầng khác | Không xác nhận chắc outcome launch | Tra metadata trước khi thử lại |

Nếu job đã hoàn thành, việc đổi `ExitStatus` hoặc số lần start của một step không biến nó thành instance có thể restart. Trạng thái ở cấp job phải được hiểu riêng với trạng thái từng step.

## 12. BatchStatus và ExitStatus: đừng nhầm COMPLETED với exit code

`BatchStatus` thể hiện trạng thái vòng đời, ví dụ `STARTED`, `COMPLETED`, `FAILED`, `STOPPED`. `ExitStatus` là mã kết thúc có thể được ứng dụng tùy biến, thường dùng điều hướng flow.

Ví dụ một job xử lý nguồn rỗng có thể kết thúc với:

```text
BatchStatus = COMPLETED
ExitStatus  = NO_DATA
```

Nếu chính sách coi “không có dữ liệu” là một trường hợp hoàn tất hợp lệ, instance vẫn được xem là completed, và việc gửi lại cùng identifying parameters không làm nó restart.

Ngược lại, một execution có log thông báo “processed 1000 items” nhưng `BatchStatus=FAILED` vẫn không phải completed. Đừng chỉ nhìn một log, một exit code tùy biến hoặc việc launcher trả về object để quyết định trạng thái thực.

### ExitStatus tùy biến không tự động cho phép restart

Một listener có thể trả `ExitStatus("WARNING")` hay `ExitStatus("NO_DATA")`. Việc này **không tự chuyển** `BatchStatus.COMPLETED` thành `FAILED`. Muốn một lỗi chất lượng dữ liệu khiến job thất bại, phải thiết kế flow/step và trạng thái cuối rõ ràng.

## 13. Cẩn trọng với allowStartIfComplete(true)

Spring Batch có phương thức:

```java
Step step = new StepBuilder("revalidateStep", repository)
    .tasklet(revalidateTasklet, transactionManager)
    .allowStartIfComplete(true)
    .build();
```

`allowStartIfComplete(true)` cho phép một **step đã COMPLETED** được chạy lại trong **một JobExecution mới của JobInstance được phép restart**. Nó không tự động bỏ qua quy tắc **JobInstance đã COMPLETED thì không được restart**.

Ví dụ:

```text
JobInstance K:
  JobExecution 1: FAILED
    prepareStep: COMPLETED
    writeStep: FAILED

Restart JobInstance K:
  prepareStep có allowStartIfComplete(true)
    -> có thể chạy lại dù step trước đã COMPLETED
  writeStep -> chạy lại theo checkpoint
```

Nhưng:

```text
JobInstance K:
  JobExecution 2: COMPLETED

Gửi lại cùng identifying parameters:
  -> JobInstanceAlreadyCompleteException
  -> allowStartIfComplete(true) không giúp được
```

Đây là nhầm lẫn phổ biến: **điều khiển chạy lại step** khác với **cho phép restart toàn bộ job instance**.

Tương tự, bật `restartable=true` hoặc không gọi `preventRestart()` không có nghĩa Spring Batch cho chạy lại một instance đã hoàn thành.

## 14. Có nên xóa metadata để job chạy lại không?

Một cách xử lý nguy hiểm trong môi trường production là xóa dữ liệu ở:

- `BATCH_JOB_INSTANCE`
- `BATCH_JOB_EXECUTION`
- `BATCH_JOB_EXECUTION_PARAMS`
- `BATCH_STEP_EXECUTION`
- Các bảng execution context tương ứng

để Spring Batch “không còn nhớ” instance `COMPLETED`.

**Không nên dùng cách này để reprocess.** Xóa metadata làm mất lịch sử execution, phá quan hệ restart/checkpoint, khiến việc audit khó khăn và có thể tạo không nhất quán với dữ liệu đã commit tại hệ thống đích.

Kể cả khi repository không còn metadata, **kết quả nghiệp vụ trước đó vẫn có thể nằm trong database, file, API hoặc queue**. Job chạy lại sẽ không biết đã ghi gì trước đó và có thể tạo duplicate.

### Trường hợp test

Trong integration test, dùng tiện ích như `JobRepositoryTestUtils.removeJobExecutions()` để cô lập dữ liệu metadata giữa các test là hợp lý, nếu dùng trên **database test độc lập**.

Điều đó **không phải quy trình vận hành để chạy lại một job completed trong production**.

Nếu cần giữ phiên bản mới của dữ liệu đã xử lý, hãy thiết kế reprocess với identifying parameters có ý nghĩa và chiến lược cập nhật đích rõ ràng.

## 15. Điều gì xảy ra với dữ liệu đích khi tạo instance mới?

Spring Batch kiểm soát danh tính execution, nhưng **không tự xóa hoặc chống trùng kết quả nghiệp vụ**.

Một số kiểu writer và rủi ro:

| Kiểu writer | Khi tạo instance mới cho cùng kỳ | Biện pháp |
| --- | --- | --- |
| `INSERT` không có unique constraint | Ghi thêm bản ghi trùng | Unique key/constraint, staging, quy tắc idempotent |
| `INSERT` có unique constraint | Có thể lỗi duplicate key | Thiết kế upsert/replace có chủ đích |
| `UPDATE` theo business key | Có thể ghi đè kết quả cũ | Audit, version, xác minh tính đúng và tác động downstream |
| Writer tạo file cố định | Có thể ghi đè hoặc append vào file cũ | File naming/versioning, xuất ra temporary file rồi publish |
| Writer gửi email | Email có thể gửi lại | Dedupe theo business event, không gửi lại vô điều kiện |
| Writer gọi thanh toán API | Nguy cơ tạo tác động tài chính lặp | Idempotency key và đối soát trạng thái |
| Writer publish message | Có thể phát lại event | Outbox/dedupe key và consumer idempotent |

Ví dụ PostgreSQL:

```sql
CREATE TABLE daily_settlement (
    business_date DATE NOT NULL,
    account_id VARCHAR(100) NOT NULL,
    net_amount NUMERIC(18, 2) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (business_date, account_id)
);
```

Khóa chính theo `(business_date, account_id)` giúp ngăn duplicate logic trong bảng. Nếu reprocess phải cập nhật số tiền, có thể thiết kế `UPSERT`:

```sql
INSERT INTO daily_settlement (
    business_date, account_id, net_amount
)
VALUES (:businessDate, :accountId, :netAmount)
ON CONFLICT (business_date, account_id)
DO UPDATE SET
    net_amount = EXCLUDED.net_amount,
    updated_at = CURRENT_TIMESTAMP;
```

Cách này bảo vệ số dòng không bị nhân đôi, nhưng **không tự bảo đảm đúng nghiệp vụ**: trường nào được phép cập nhật, dữ liệu downstream đã đọc kết quả cũ chưa, các thay đổi có cần được audit không? Với dữ liệu tài chính, có thể phù hợp hơn khi ghi kết quả version mới và chỉ chuyển active version sau khi đối soát.

## 16. Hướng dẫn xử lý khi gặp JobInstanceAlreadyCompleteException

Khi gặp lỗi, nên xử lý theo trình tự thay vì lập tức thay tham số:

**Bước 1 — Xác định kỳ dữ liệu.** Ghi tên job, những identifying parameters, phiên bản rule/source và yêu cầu nghiệp vụ: tại sao muốn chạy lại?

**Bước 2 — Xem lịch sử instance.** Dùng `JobExplorer` hoặc truy vấn metadata để xác nhận instance đã `COMPLETED` và xác định execution cuối.

**Bước 3 — Phân loại yêu cầu.** Nếu là trigger trùng, bỏ qua và báo “đã xử lý”. Nếu là lỗi job trước đó chưa completed, xem hướng restart. Nếu là reprocess, sang bước tiếp.

**Bước 4 — Đánh giá tác động dữ liệu.** Xác định bảng/file/API đã có kết quả nào, hệ thống downstream nào đã đọc, có sự kiện không thể rút lại không.

**Bước 5 — Thiết kế định danh lần xử lý mới.** Chọn `revision` hoặc `reprocessVersion` identifying, lý do và phê duyệt; snapshot nguồn phải có version/checksum rõ ràng.

**Bước 6 — Thực thi có kiểm soát.** Ghi vào staging hoặc dùng upsert/version với idempotency; tránh ghi đè không kiểm tra.

**Bước 7 — Đối soát và audit.** Kiểm tra số lượng, tổng tiền, business keys, thay đổi so với kết quả cũ và trạng thái publish.

**Bước 8 — Đóng yêu cầu.** Lưu request ID, người phê duyệt, lý do, JobInstance ID/JobExecution ID mới, kết quả đối soát và thời điểm áp dụng dữ liệu mới.

Nếu không xác minh được trạng thái hiện tại, không nên tự động xử lý lại chỉ vì caller timeout. Lời gọi launcher có thể đã tạo execution rồi nhưng caller chưa nhận được phản hồi.

## 17. Dùng JobExplorer để quan sát instance và execution

Một service đọc metadata có thể giúp phân biệt đã hoàn tất với đang chạy hoặc đã failed.

Ví dụ tra theo tên job và tham số:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class SettlementHistoryReader {

    private final JobExplorer explorer;

    public SettlementHistoryReader(JobExplorer explorer) {
        this.explorer = explorer;
    }

    public List<JobExecution> executions(
            String jobName,
            JobParameters parameters) {

        JobInstance instance =
            explorer.getJobInstance(jobName, parameters);

        if (instance == null) {
            return List.of();
        }

        return explorer.getJobExecutions(instance);
    }
}
```

Đối với Spring Batch 5.x, API `JobExplorer.getJobInstance(jobName, parameters)` cho phép tra JobInstance theo bộ tham số. Trong dự án có nhiều phiên bản Batch, cần điều chỉnh theo giao diện API đang sử dụng.

Danh sách `JobExecution` cần được xem cùng `BatchStatus`, `ExitStatus` và thời điểm thực thi. Không suy luận rằng execution cuối là `COMPLETED` chỉ từ số lượng phần tử hoặc chỉ từ chuỗi log của scheduler.

### SQL để quan sát metadata

Có thể truy vấn các bảng chuẩn của Spring Batch ở chế độ **read-only**:

```sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.CREATE_TIME,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE AS ji
JOIN BATCH_JOB_EXECUTION AS je
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'dailySettlementJob'
ORDER BY ji.JOB_INSTANCE_ID, je.JOB_EXECUTION_ID;
```

Với schema Spring Batch 5.x, bảng parameters thường có cấu trúc tương ứng:

```sql
SELECT
    je.JOB_EXECUTION_ID,
    p.PARAMETER_NAME,
    p.PARAMETER_TYPE,
    p.PARAMETER_VALUE,
    p.IDENTIFYING
FROM BATCH_JOB_EXECUTION AS je
JOIN BATCH_JOB_EXECUTION_PARAMS AS p
    ON p.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
ORDER BY je.JOB_EXECUTION_ID, p.PARAMETER_NAME;
```

Tên bảng/cột metadata có thể khác giữa các phiên bản Spring Batch và schema đã tùy biến. Các truy vấn chỉ minh họa cách **đọc lịch sử**, không khuyến nghị cập nhật trực tiếp status bằng SQL.

## 18. Ví dụ định nghĩa Job có thể restart sau FAILED

Một Job thông thường có thể restart nếu được cấu hình và metadata cho phép. Điều này không thay đổi quy tắc chống restart instance đã completed.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SettlementJobConfig {

    @Bean("dailySettlementJob")
    Job dailySettlementJob(
            JobRepository repository,
            @Qualifier("settlementStep") Step step) {

        return new JobBuilder("dailySettlementJob", repository)
            .start(step)
            .build();
    }
}
```

Nếu step thất bại:

```text
JobInstance K
    |
    +-- JobExecution 1: FAILED
```

Cùng identifying parameters có thể khởi chạy JobExecution 2. Nếu lần hai thành công:

```text
JobInstance K
    |
    +-- JobExecution 1: FAILED
    +-- JobExecution 2: COMPLETED
```

Từ thời điểm đó, JobInstance K không được restart thêm lần nữa bằng cùng identity.

### preventRestart()

Spring Batch cho phép chặn restart ngay cả khi job thất bại:

```java
Job job = new JobBuilder("oneShotJob", repository)
    .start(step)
    .preventRestart()
    .build();
```

Khi đó yêu cầu restart một instance đã có execution có thể gặp `JobRestartException`. Tùy chọn này **không** làm job completed có thể chạy lại; nó làm chính sách restart chặt hơn.

## 19. Ví dụ integration test: COMPLETED không thể restart

Đoạn test dưới đây chạy job thật qua `JobLauncher` và `JobRepository` với cơ sở dữ liệu H2 riêng cho test. Job có một tasklet đếm số lần chạy, cho phép quan sát instance nào thực sự được khởi tạo.

Các dependency Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Ví dụ:

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(
    classes = CompletedInstanceTest.TestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always",
        "spring.datasource.url=jdbc:h2:mem:completed_job_test;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password="
    }
)
class CompletedInstanceTest {

    @Autowired
    private JobLauncher launcher;

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    @Qualifier("demoJob")
    private Job job;

    @Autowired
    @Qualifier("runCounter")
    private AtomicInteger counter;

    @BeforeEach
    void reset() {
        repositoryTestUtils.removeJobExecutions();
        counter.set(0);
    }

    private JobParameters parameters(
            String businessDate,
            String requestId,
            Long revision) {

        JobParametersBuilder builder =
            new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .addString("requestId", requestId, false);

        if (revision != null) {
            builder.addLong("revision", revision, true);
        }

        return builder.toJobParameters();
    }

    @Test
    void sameIdentityAfterCompletedIsRejected() throws Exception {
        JobParameters firstRequest =
            parameters("2026-11-15", "request-A", null);

        JobExecution first = launcher.run(job, firstRequest);

        assertEquals(BatchStatus.COMPLETED, first.getStatus());
        assertEquals(1, counter.get());

        // requestId thay đổi nhưng NON-identifying.
        JobParameters duplicateRequest =
            parameters("2026-11-15", "request-B", null);

        assertThrows(
            JobInstanceAlreadyCompleteException.class,
            () -> launcher.run(job, duplicateRequest)
        );

        // Tasklet không được gọi thêm.
        assertEquals(1, counter.get());
    }

    @Test
    void newBusinessDateCreatesAnotherInstance() throws Exception {
        JobExecution d1 = launcher.run(
            job, parameters("2026-11-15", "A", null)
        );

        JobExecution d2 = launcher.run(
            job, parameters("2026-11-16", "B", null)
        );

        assertEquals(BatchStatus.COMPLETED, d1.getStatus());
        assertEquals(BatchStatus.COMPLETED, d2.getStatus());

        assertNotEquals(
            d1.getJobInstance().getInstanceId(),
            d2.getJobInstance().getInstanceId()
        );
        assertEquals(2, counter.get());
    }

    @Test
    void explicitRevisionCreatesNewInstanceNotRestart()
            throws Exception {

        JobExecution original = launcher.run(
            job, parameters("2026-11-15", "A", 1L)
        );

        JobExecution reprocessed = launcher.run(
            job, parameters("2026-11-15", "B", 2L)
        );

        assertEquals(BatchStatus.COMPLETED, original.getStatus());
        assertEquals(BatchStatus.COMPLETED, reprocessed.getStatus());

        // Hai JobInstance khác nhau.
        assertNotEquals(
            original.getJobInstance().getInstanceId(),
            reprocessed.getJobInstance().getInstanceId()
        );
        assertEquals(2, counter.get());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean("runCounter")
        AtomicInteger runCounter() {
            return new AtomicInteger();
        }

        @Bean("demoStep")
        Step demoStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                @Qualifier("runCounter") AtomicInteger counter) {

            return new StepBuilder("demoStep", repository)
                .tasklet((contribution, context) -> {
                    counter.incrementAndGet();
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
        }

        @Bean("demoJob")
        Job demoJob(
                JobRepository repository,
                @Qualifier("demoStep") Step step) {

            return new JobBuilder("demoJob", repository)
                .start(step)
                .build();
        }
    }
}
```

### Ý nghĩa của ba test

1. **`sameIdentityAfterCompletedIsRejected`:** cùng `businessDate`, thay `requestId` non-identifying vẫn bị từ chối. Tasklet không chạy thêm.
2. **`newBusinessDateCreatesAnotherInstance`:** ngày khác tạo instance khác; đây là kỳ xử lý mới thông thường.
3. **`explicitRevisionCreatesNewInstanceNotRestart`:** cùng ngày nhưng revision identifying khác tạo instance mới. Test chỉ chứng minh định danh; không có nghĩa reprocess đã được kiểm soát đủ về mặt nghiệp vụ.

Ví dụ dùng H2 in-memory và bộ đếm để dễ quan sát, **không chạy Content QA trong STEP 4**. Với một writer thật, integration test cần kiểm tra thêm bảng đích, transaction và idempotency trước khi coi reprocess an toàn.

## 20. Test restart sau FAILED để đối chiếu

Để tránh nhầm lẫn, thêm một trường hợp job thất bại trước khi hoàn tất. Giả sử tasklet tạo lỗi một lần:

```java
AtomicBoolean failOnce = new AtomicBoolean(true);

Step flakyStep = new StepBuilder("flakyStep", repository)
    .tasklet((contribution, context) -> {
        if (failOnce.getAndSet(false)) {
            throw new IllegalStateException("Simulated failure");
        }
        return RepeatStatus.FINISHED;
    }, transactionManager)
    .build();
```

Với `JobParameters` định danh cố định:

```text
First run:
  JobInstance ID = 2001
  JobExecution ID = 6101
  BatchStatus = FAILED

Second run (same identifying params):
  JobInstance ID = 2001
  JobExecution ID = 6102
  BatchStatus = COMPLETED

Third run (same identifying params):
  JobInstanceAlreadyCompleteException
```

Trường hợp này minh họa đúng nghĩa **restart**: execution đầu chưa hoàn tất; execution sau là một lần thử mới của cùng instance. Sau khi lần restart hoàn tất, instance không còn được restart tiếp.

Với lỗi step/chunk thật, test cần xác nhận những step đã `COMPLETED` được bỏ qua theo cấu hình restart, dữ liệu đã commit không ghi trùng và checkpoint của reader được khôi phục đúng.

## 21. Test matrix cho lỗi “restart job COMPLETED”

| Kịch bản | Identifying parameters | Trạng thái trước | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| Chạy lần đầu | Ngày D | Chưa có instance | Tạo instance và execution |
| Gửi lại y nguyên | Ngày D | `COMPLETED` | `JobInstanceAlreadyCompleteException` |
| Đổi non-identifying request ID | Ngày D | `COMPLETED` | Vẫn bị từ chối |
| Đổi identifying businessDate | Ngày D+1 | D đã `COMPLETED` | Instance mới |
| Đổi identifying revision | Ngày D, revision 2 | D/revision 1 `COMPLETED` | Instance mới, **không phải restart** |
| Lần đầu FAILED | Ngày D | `FAILED` | Có thể restart cùng instance |
| Lần đầu STOPPED | Ngày D | `STOPPED` | Có thể restart theo policy |
| Lần đầu đang chạy | Ngày D | `STARTED` | Từ chối launch trùng |
| Job có `preventRestart()` | Ngày D | `FAILED` | Restart bị từ chối |
| Step có `allowStartIfComplete(true)` | Ngày D | Job đã `COMPLETED` | Vẫn không restart job |
| Job `COMPLETED` nhưng `ExitStatus=NO_DATA` | Ngày D | `COMPLETED` | Vẫn không restart job |
| Thay nguồn nhưng giữ identity | Ngày D | `COMPLETED` | Bị từ chối; cần reprocess có version |
| Xóa metadata test rồi chạy | Ngày D | Metadata bị dọn trong test | Có thể tạo instance, **không phải giải pháp production** |
| Hai node phát cùng trigger | Ngày D | Cạnh tranh khởi chạy | Một execution hợp lệ; các yêu cầu còn lại có thể bị từ chối |

Với concurrent test, dùng cơ chế đồng bộ như `CountDownLatch` để bảo đảm execution đầu thật sự đang chạy trước khi trigger thứ hai đến, thay vì dựa vào `Thread.sleep`.

## 22. Các anti-pattern cần tránh

| Anti-pattern | Hậu quả | Giải pháp |
| --- | --- | --- |
| Coi `JobInstanceAlreadyCompleteException` là bug phải “sửa bằng run.id” | Chạy trùng kỳ nghiệp vụ | Phân biệt duplicate trigger với yêu cầu reprocess |
| Thêm timestamp identifying ở mỗi lần launch | Mỗi trigger tạo instance mới | Dùng business key xác định; timestamp tracing là non-identifying |
| Thay non-identifying parameters rồi nghĩ đã tạo instance mới | Vẫn bị từ chối | Hiểu rõ cờ identifying |
| Nghĩ `allowStartIfComplete(true)` cho phép restart Job đã completed | Lỗi vẫn xảy ra | Phân biệt chính sách step và job |
| Tắt `preventRestart()` để chạy lại Job COMPLETED | Không giải quyết trường hợp completed | Dùng reprocess/new instance theo thiết kế |
| Xóa bảng `BATCH_*` để vượt lỗi | Mất lịch sử và state, rủi ro duplicate | Giữ repository; quản lý revision/reprocess |
| Dùng `startNextInstance` khi thật ra muốn restart FAILED | Tạo instance mới | Giữ identifying parameters cho restart |
| Không kiểm tra status trước khi phát trigger tự động | Log lỗi vô ích, retry loop | Tra metadata và phân loại outcome |
| Bỏ qua tác động tới database đích | Báo cáo/tiền bị nhân đôi | Upsert/version/outbox/idempotency |
| Không ghi lại lý do reprocess | Khó kiểm toán vì cùng kỳ có nhiều version | Audit revision, source hash, người phê duyệt |
| Reprocess trên nguồn đã thay đổi nhưng không version | Không thể tái hiện kết quả | Source snapshot và checksum |
| Chỉ test xem JobLauncher chạy thành công | Không phát hiện double-write | Assert dữ liệu đích và business invariants |
| Nhầm `ExitStatus` với `BatchStatus` | Kết luận sai khả năng restart | Đọc cả hai trạng thái |
| Dùng JobExecution ID làm khóa chống trùng | Restart có ID mới, gây tác động lặp | Dùng khóa nghiệp vụ bền vững |
| Xử lý `UNKNOWN_ERROR` bằng cách tạo instance mới ngay | Có thể xử lý trùng execution đã được tạo | Đối soát JobRepository trước khi retry |

## 23. Bài tập thực hành

Xây dựng một job `dailyRevenueJob` gồm hai step:

1. `loadTransactionsStep` đọc giao dịch của một `businessDate`.
2. `writeRevenueStep` lưu tổng doanh thu theo `businessDate` và `merchantId`.

Yêu cầu thực hiện:

- **Trường hợp A:** chạy ngày D lần đầu đến `COMPLETED`; gửi lại cùng identifying parameters, kiểm tra bị từ chối và writer không ghi thêm.
- **Trường hợp B:** thêm `requestId` non-identifying rồi gọi lại; giải thích vì sao vẫn bị từ chối.
- **Trường hợp C:** mô phỏng lỗi lần đầu làm job `FAILED`; khởi chạy lại với cùng identifying parameters và kiểm tra có JobExecution mới của cùng JobInstance.
- **Trường hợp D:** bổ sung `revision=2` identifying cho một yêu cầu reprocess có lý do; kiểm tra JobInstance khác, nhưng dữ liệu đích không bị nhân đôi.
- **Trường hợp E:** step đầu đã `COMPLETED`, step sau `FAILED`; restart và kiểm tra step đầu có được chạy lại hay không. Thử thêm `allowStartIfComplete(true)` để quan sát khác biệt.
- **Trường hợp F:** thực hiện reprocess khi nguồn thay đổi; lưu source checksum và quy trình phê duyệt trước khi publish.
- **Trường hợp G:** chạy scheduler hai lần cùng ngày và xác định log/monitoring nào phản ánh trigger trùng và execution cuối.

Trong bảng kết quả, ghi tên job, identifying parameters, JobInstance ID, JobExecution ID, BatchStatus, ExitStatus và số bản ghi đích trước/sau từng lần thử.

Hãy giải thích trường hợp nào là **restart thật**, trường hợp nào là **new instance**, trường hợp nào phải **bỏ qua duplicate**, và trường hợp nào cần **reprocess có audit**.

## 24. Tổng kết

**Không thể restart một JobInstance đã `COMPLETED` bằng cách gọi lại cùng identifying JobParameters.** Spring Batch chủ động từ chối qua `JobInstanceAlreadyCompleteException` để bảo vệ dữ liệu và lịch sử xử lý.

Restart chỉ dành cho một instance chưa hoàn tất thành công và còn đủ điều kiện khôi phục. Khi cần xử lý lại kết quả đã hoàn thành, hãy xem đó là **reprocess nghiệp vụ**, tạo danh tính/phiên bản mới có chủ đích và bảo vệ dữ liệu đích bằng transaction, versioning hoặc idempotency. Đừng tăng `run.id` ngẫu nhiên, xóa metadata hoặc bật `allowStartIfComplete(true)` với kỳ vọng vượt qua quy tắc của JobInstance.

Hiểu đúng sự khác biệt giữa **JobInstance**, **JobExecution**, **restart**, **new instance** và **reprocess** giúp xử lý lỗi một cách an toàn, giữ nguyên khả năng audit và tránh những lần chạy trùng có thể gây sai lệch dữ liệu.

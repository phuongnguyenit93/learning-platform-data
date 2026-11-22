# JobInstance không restart được khi COMPLETED trong Spring Batch

Trong Spring Batch, một Job có thể được chạy nhiều lần, nhưng không phải lần chạy nào cũng là một lần restart. Khi một JobInstance đã kết thúc với trạng thái **COMPLETED**, Spring Batch xem lần xử lý logic đó đã hoàn tất. Nếu gọi lại cùng Job với cùng bộ JobParameters nhận diện, framework sẽ từ chối tạo execution mới và thường ném JobInstanceAlreadyCompleteException.

Đây là hành vi có chủ đích để tránh xử lý trùng một JobInstance. Muốn tiếp tục một Job thất bại hoặc bị dừng, ta restart chính JobInstance đó với các identifying JobParameters ban đầu. Muốn chạy lại một JobInstance đã COMPLETED, ta cần tạo **JobInstance mới**, thường bằng cách thêm một identifying parameter biểu thị lần chạy mới.

Bài học này giải thích quan hệ giữa Job, JobInstance và JobExecution; lý do COMPLETED không thể restart; cách phân biệt restart với rerun; vai trò của identifying và non-identifying JobParameters; cách dùng RunIdIncrementer, JobParametersIncrementer và JobOperator; cùng các lưu ý về idempotency, dữ liệu đầu ra và vận hành.

## 1. Phân biệt Job, JobInstance và JobExecution

Ba khái niệm này là nền tảng để hiểu vì sao một JobInstance đã COMPLETED không thể được chạy lại với cùng tham số.

- **Job** là định nghĩa quy trình batch, gồm tên Job, các Step, flow và cấu hình.
- **JobInstance** đại diện cho một lần xử lý logic của Job với một bộ identifying JobParameters cụ thể.
- **JobExecution** là một lần thực thi cụ thể của JobInstance. Một JobInstance có thể có nhiều JobExecution nếu lần thực thi trước thất bại hoặc bị dừng và được restart.

Có thể hình dung:

~~~text
Job: dailyImportJob
  |
  +-- JobInstance (businessDate=2026-11-15)
        |
        +-- JobExecution #1 -> FAILED
        |
        +-- JobExecution #2 -> COMPLETED
~~~

Hai JobExecution thuộc cùng một JobInstance vì chúng dùng cùng identifying parameters. Execution thứ hai là lần restart sau khi execution đầu thất bại.

Nếu sau đó ứng dụng chạy lại với cùng identifying parameters, Spring Batch không tạo JobExecution #3 vì JobInstance đã COMPLETED.

Muốn xử lý một lần logic mới, phải tạo JobInstance mới:

~~~text
Job: dailyImportJob
  |
  +-- JobInstance (businessDate=2026-11-15, run.id=1)
  |     +-- JobExecution #1 -> COMPLETED
  |
  +-- JobInstance (businessDate=2026-11-15, run.id=2)
        +-- JobExecution #2 -> STARTED / COMPLETED
~~~

Ở đây ngày nghiệp vụ giống nhau nhưng run.id là identifying parameter khác nhau, nên hai JobInstance khác nhau.

## 2. JobInstance được xác định như thế nào?

Spring Batch xác định JobInstance bằng:

- Tên Job.
- Tập hợp JobParameters được đánh dấu là identifying.

Có thể biểu diễn khái niệm:

~~~text
JobInstance identity = Job name + identifying JobParameters
~~~

Ví dụ:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addString("sourceSystem", "CRM")
    .toJobParameters();
~~~

Với cách thêm tham số mặc định này, các giá trị được đánh dấu identifying. Vì vậy, JobInstance được xác định bởi tên Job cùng businessDate và sourceSystem.

Chạy lại Job với cùng tên và cùng identifying values sẽ tìm đến cùng JobInstance.

### Cùng tham số nghĩa là cùng JobInstance

Ví dụ hai lần gọi:

~~~java
jobLauncher.run(
    dailyImportJob,
    new JobParametersBuilder()
        .addString("businessDate", "2026-11-15")
        .addString("sourceSystem", "CRM")
        .toJobParameters()
);

jobLauncher.run(
    dailyImportJob,
    new JobParametersBuilder()
        .addString("businessDate", "2026-11-15")
        .addString("sourceSystem", "CRM")
        .toJobParameters()
);
~~~

Hai lần gọi dùng cùng Job name và cùng identifying parameters. Nếu JobInstance đã COMPLETED, lần gọi thứ hai không phải một lần chạy mới; nó bị từ chối.

Nếu JobInstance đang chạy, framework có thể ném JobExecutionAlreadyRunningException. Nếu execution trước FAILED hoặc STOPPED và Job có thể restart, lần gọi với cùng tham số có thể tạo JobExecution mới trên JobInstance cũ.

## 3. Vì sao JobInstance COMPLETED không thể restart?

COMPLETED biểu thị JobInstance đã hoàn tất thành công theo trạng thái cuối cùng mà JobRepository ghi nhận. Spring Batch dùng metadata này để ngăn một JobInstance đã hoàn tất bị thực thi lại ngoài ý muốn.

Lý do chính:

1. **Tránh xử lý trùng:** cùng một lô dữ liệu không bị ghi lại chỉ vì scheduler gửi cùng request lần nữa.
2. **Bảo vệ trạng thái nghiệp vụ:** dữ liệu đã publish hoặc đã đối soát không bị tạo lại ngoài kế hoạch.
3. **Giữ ý nghĩa của restart:** restart dùng để tiếp tục công việc chưa hoàn tất, không phải để tạo một lần xử lý mới sau khi đã thành công.
4. **Bảo vệ metadata:** JobRepository có thể phân biệt một JobExecution mới của cùng JobInstance với một JobInstance mới.

Ví dụ Job nhập file theo ngày:

- Lần chạy với businessDate=2026-11-15 hoàn tất.
- Scheduler vô tình gửi lại đúng JobParameters.
- Nếu framework cho chạy lại, dữ liệu ngày đó có thể được insert, gửi thông báo hoặc publish file lần thứ hai.
- Việc từ chối giúp phát hiện request chạy trùng.

Thông báo thường gặp:

~~~text
JobInstanceAlreadyCompleteException:
A job instance already exists and is complete for parameters ...
~~~

Tên thông báo chi tiết có thể khác giữa phiên bản, nhưng ý nghĩa là JobInstance tương ứng đã hoàn tất.

### COMPLETED là trạng thái cuối của JobInstance

Một JobInstance có thể có nhiều JobExecution khi restart sau lỗi, nhưng khi JobInstance đã đạt COMPLETED, nó không còn là đối tượng có thể restart với cùng identifying parameters.

Muốn chạy lại, hãy xác định đó là một lần xử lý logic mới hay một thao tác sửa chữa dữ liệu. Sau đó tạo JobInstance mới với identifying parameter phù hợp.

## 4. Phân biệt restart và rerun

Hai hành động này thường bị gọi chung là "chạy lại", nhưng trong Spring Batch chúng khác nhau.

| Hành động | JobInstance | JobParameters | Khi dùng |
|---|---|---|---|
| Restart | Giữ nguyên | Giữ identifying parameters | Execution trước FAILED hoặc STOPPED và Job cho phép restart |
| Rerun thành JobInstance mới | Mới | Có ít nhất một identifying parameter khác | Cần xử lý lại một lô hoặc tạo lần xử lý logic mới |
| Gọi lại cùng instance đã COMPLETED | Không đổi | Không đổi | Bị từ chối |
| Thay non-identifying parameter | Không đổi | Identifying set không đổi | Chỉ thay metadata phụ, không tạo instance mới |

### Ví dụ restart sau FAILED

~~~text
JobInstance: importJob(businessDate=2026-11-15)

Execution 1:
  validateStep -> COMPLETED
  importStep   -> FAILED
  Job          -> FAILED

Restart cùng identifying parameters:

Execution 2:
  validateStep -> được bỏ qua theo chính sách restart mặc định
  importStep   -> chạy lại
  Job          -> COMPLETED
~~~

Đây là restart vì JobInstance vẫn là một và công việc chưa hoàn tất được tiếp tục.

### Ví dụ rerun sau COMPLETED

~~~text
JobInstance 1:
  importJob(businessDate=2026-11-15, run.id=1)
  JobExecution -> COMPLETED

Yêu cầu chạy lại cùng ngày nghiệp vụ:

JobInstance 2:
  importJob(businessDate=2026-11-15, run.id=2)
  JobExecution -> chạy như một instance mới
~~~

Đây là rerun. Spring Batch không tiếp tục checkpoint của instance đầu; nó khởi tạo một JobInstance mới. Vì vậy, cần kiểm soát side effect và dữ liệu đầu ra để tránh ghi trùng.

## 5. Tạo JobInstance mới bằng identifying JobParameter

Cách trực tiếp nhất là thêm một identifying parameter mới, chẳng hạn run.id hoặc reprocess.sequence.

Ví dụ:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addString("sourceSystem", "CRM")
    .addLong("run.id", 2L)
    .toJobParameters();

jobLauncher.run(dailyImportJob, parameters);
~~~

Vì run.id là identifying parameter, bộ tham số mới tạo JobInstance mới dù businessDate và sourceSystem giống lần trước.

### Dùng tham số có ý nghĩa

Không nên thêm một tham số ngẫu nhiên chỉ để vượt qua lỗi nếu không có chính sách vận hành. Tên tham số nên diễn tả lý do tạo instance mới:

- run.id: số thứ tự lần chạy.
- reprocess.id: mã lần xử lý lại.
- correction.version: phiên bản điều chỉnh.
- source.snapshot: mã snapshot nguồn.
- reconciliation.id: mã lần đối soát.

Chọn identifying parameter phù hợp với định nghĩa một lần xử lý logic trong nghiệp vụ.

### Phân biệt run ID và business key

run.id có thể phân biệt lần chạy; businessDate có thể là khóa nghiệp vụ của dữ liệu.

| businessDate | run.id | Ý nghĩa |
|---|---:|---|
| 2026-11-15 | 1 | Lần xử lý đầu tiên |
| 2026-11-15 | 2 | Lần chạy lại sau điều chỉnh |
| 2026-11-16 | 1 | Lần xử lý đầu tiên của ngày mới |

Không nên dùng run ID để thay thế business key. Hai loại tham số phục vụ hai mục đích khác nhau.

## 6. Identifying và non-identifying JobParameters

Spring Batch cho phép đánh dấu một JobParameter có tham gia xác định JobInstance hay không.

Ví dụ:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("sourceSystem", "CRM", true)
    .addString("requestedBy", "operator-01", false)
    .addLong("run.id", 2L, true)
    .toJobParameters();
~~~

Tham số thứ ba của các phương thức builder là cờ identifying:

- true: tham số tham gia xác định JobInstance.
- false: tham số không tham gia xác định JobInstance.

Trong ví dụ:

- businessDate và sourceSystem là identifying.
- run.id là identifying.
- requestedBy là non-identifying.

Nếu chỉ thay requestedBy nhưng giữ các identifying parameters, JobInstance vẫn là một. Nếu instance đó đã COMPLETED, thay requestedBy không cho phép chạy lại.

### Non-identifying parameter không tạo instance mới

Ví dụ:

~~~java
JobParameters first = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();

JobParameters second = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedBy", "operator", false)
    .toJobParameters();
~~~

Hai bộ tham số có cùng identifying set. Vì vậy, chúng đại diện cùng JobInstance.

Dùng non-identifying parameters cho thông tin vận hành không làm thay đổi danh tính xử lý, chẳng hạn người yêu cầu, correlation ID hoặc ghi chú. Không dùng chúng làm mã lần chạy nếu cần tạo JobInstance mới.

## 7. Dùng RunIdIncrementer

Spring Batch cung cấp RunIdIncrementer để tăng một identifying parameter có tên run.id.

Có thể gắn incrementer vào Job:

~~~java
@Bean
Job dailyImportJob(
        JobRepository jobRepository,
        Step importStep,
        Step publishStep) {

    return new JobBuilder("dailyImportJob", jobRepository)
        .start(importStep)
        .next(publishStep)
        .incrementer(new RunIdIncrementer())
        .build();
}
~~~

RunIdIncrementer tạo bộ JobParameters tiếp theo bằng cách tăng run.id. Nếu chưa có giá trị trước đó, nó khởi tạo giá trị theo quy tắc của implementation, thông thường là 1.

Ví dụ:

~~~text
Lần trước:
  businessDate = 2026-11-15
  run.id        = 1

Bộ tham số kế tiếp:
  businessDate = 2026-11-15
  run.id        = 2
~~~

### Incrementer không tự chạy khi gọi JobLauncher.run()

Đây là điểm dễ nhầm. Khai báo incrementer trên Job không có nghĩa mỗi lần gọi jobLauncher.run(job, sameParameters) thì Spring Batch tự tăng run.id.

JobLauncher.run() nhận chính bộ JobParameters mà caller truyền vào. Incrementer được dùng bởi cơ chế lấy bộ tham số kế tiếp, ví dụ JobOperator.startNextInstance(jobName).

Nếu ứng dụng tự gọi JobLauncher, ứng dụng phải tự tạo bộ JobParameters mới hoặc gọi một cơ chế tạo tham số kế tiếp phù hợp.

## 8. Dùng JobParametersIncrementer tùy chỉnh

Khi quy tắc tạo instance mới phức tạp hơn tăng một số, có thể triển khai JobParametersIncrementer.

Interface có phương thức:

~~~java
public interface JobParametersIncrementer {
    JobParameters getNext(JobParameters parameters);
}
~~~

Ví dụ tăng reprocess.sequence:

~~~java
public class ReprocessIncrementer
        implements JobParametersIncrementer {

    @Override
    public JobParameters getNext(JobParameters parameters) {
        long nextSequence = 1L;

        if (parameters != null
                && parameters.getLong("reprocess.sequence") != null) {
            nextSequence =
                parameters.getLong("reprocess.sequence") + 1L;
        }

        return new JobParametersBuilder(parameters)
            .addLong("reprocess.sequence", nextSequence, true)
            .toJobParameters();
    }
}
~~~

Gắn vào Job:

~~~java
return new JobBuilder("dailyImportJob", jobRepository)
    .start(importStep)
    .incrementer(new ReprocessIncrementer())
    .build();
~~~

Incrementer tùy chỉnh có thể giữ nguyên business date và source system, đồng thời tăng mã lần xử lý lại.

Cần bảo đảm tham số mới thật sự identifying. Nếu gọi addLong với identifying=false, JobInstance không đổi.

## 9. Dùng JobOperator.startNextInstance()

Nếu Job được cấu hình JobParametersIncrementer, JobOperator có thể tạo và khởi chạy JobInstance tiếp theo.

Ví dụ khái niệm:

~~~java
long executionId = jobOperator.startNextInstance("dailyImportJob");
~~~

Cách này yêu cầu:

- Job có tên đã đăng ký trong JobRegistry hoặc cấu hình JobOperator tương ứng.
- Job có JobParametersIncrementer.
- JobOperator có các dependency cần thiết như JobLauncher, JobRepository và JobRegistry.
- Bộ tham số tiếp theo tạo ra một JobInstance mới hợp lệ.

startNextInstance là lựa chọn phù hợp cho scheduler hoặc công cụ vận hành muốn yêu cầu instance kế tiếp theo incrementer của Job.

### So sánh với JobLauncher.run()

| API | Trách nhiệm |
|---|---|
| JobLauncher.run(job, parameters) | Chạy Job với đúng JobParameters caller truyền vào |
| JobOperator.startNextInstance(jobName) | Lấy tham số tiếp theo từ incrementer rồi khởi chạy instance mới |
| JobOperator.restart(executionId) | Restart một JobExecution đủ điều kiện restart |
| JobExplorer | Tra cứu JobInstance, JobExecution và StepExecution metadata |

Không dùng startNextInstance để restart một execution FAILED cụ thể. Nó tạo instance tiếp theo theo incrementer. Muốn restart một execution thất bại, dùng cơ chế restart phù hợp với execution đó và giữ identifying parameters của JobInstance.

## 10. Restart một JobInstance FAILED hoặc STOPPED

Nếu JobInstance chưa hoàn tất và execution trước ở trạng thái có thể restart, Spring Batch có thể tạo JobExecution mới trên cùng JobInstance.

Ví dụ:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addString("sourceSystem", "CRM")
    .toJobParameters();

jobLauncher.run(dailyImportJob, parameters);
~~~

Nếu lần trước với đúng identifying parameters đã FAILED và Job không bị cấu hình ngăn restart, lời gọi có thể tạo execution mới để tiếp tục.

Trong vận hành, có thể dùng:

~~~java
long newExecutionId = jobOperator.restart(failedExecutionId);
~~~

restart nhận ID của JobExecution cần restart. Execution phải ở trạng thái phù hợp, chẳng hạn FAILED hoặc STOPPED, và Job phải restartable.

Không truyền execution ID của một JobExecution COMPLETED với kỳ vọng chạy lại. Một instance đã COMPLETED không còn là instance có thể restart.

### Job phải cho phép restart

Job có thể được cấu hình ngăn restart:

~~~java
return new JobBuilder("oneShotJob", jobRepository)
    .start(oneTimeStep)
    .preventRestart()
    .build();
~~~

Nếu execution trước thất bại, Job này không thể được restart theo cách thông thường. preventRestart() không phải cách cho phép rerun sau COMPLETED; nó hạn chế restart của JobInstance thất bại.

Nếu cần một lần xử lý mới, tạo JobInstance mới với identifying parameters mới và xác định rõ tác động nghiệp vụ.

## 11. allowStartIfComplete không mở khóa JobInstance COMPLETED

Một Step có thể được cấu hình:

~~~java
@Bean
Step refreshReferenceStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet refreshTasklet) {

    return new StepBuilder("refreshReferenceStep", jobRepository)
        .tasklet(refreshTasklet, transactionManager)
        .allowStartIfComplete(true)
        .build();
}
~~~

allowStartIfComplete(true) cho phép Step đã COMPLETED được chạy lại trong một lần **restart của JobInstance chưa hoàn tất** khi flow và chính sách restart đưa Job quay lại Step đó.

Nó không cho phép gọi lại một JobInstance mà JobExecution cuối cùng đã COMPLETED.

Phân biệt:

- JobInstance FAILED/STOPPED: có thể restart nếu Job cho phép.
- Step đã COMPLETED trong một JobInstance đang được restart: có thể được chạy lại nếu allowStartIfComplete(true).
- JobInstance đã COMPLETED: không thể restart bằng cùng identifying parameters, dù một Step có allowStartIfComplete(true).

Đây là hai phạm vi khác nhau: chính sách chạy lại Step trong một JobInstance có thể restart và quy tắc không chạy lại một JobInstance đã hoàn tất.

## 12. Flow có thể khiến Job COMPLETED dù một Step thất bại

Khi đọc metadata, cần xem trạng thái cuối của JobExecution, không chỉ nhìn một Step riêng lẻ.

Ví dụ flow có thể chuyển từ một ExitStatus thất bại sang terminal end() để coi nhánh lỗi đã được xử lý:

~~~java
return new JobBuilder("fileValidationJob", jobRepository)
    .start(validateStep)
        .on("COMPLETED").to(importStep)
    .from(validateStep)
        .on("FAILED").to(recordRejectedFileStep)
    .from(validateStep)
        .on("*").fail()
    .from(recordRejectedFileStep)
        .on("COMPLETED").end()
    .from(recordRejectedFileStep)
        .on("*").fail()
    .end()
    .build();
~~~

Trong ví dụ, file bị từ chối có thể làm validation Step thất bại, nhưng nhánh xử lý reject hoàn tất và Job kết thúc COMPLETED theo chính sách flow.

Khi JobExecution cuối cùng COMPLETED, JobInstance được xem là đã hoàn tất. Không thể restart cùng instance chỉ vì một Step bên trong có trạng thái FAILED.

Nếu nghiệp vụ muốn Job vẫn được coi là thất bại để có thể restart sau khi sửa nguyên nhân, hãy thiết kế terminal transition phù hợp, chẳng hạn fail(), thay vì end().

## 13. Không dùng non-identifying parameter để ép rerun

Một lỗi phổ biến là thêm tham số mới nhưng đánh dấu non-identifying:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addLong("rerunSequence", 2L, false)
    .toJobParameters();
~~~

Mặc dù rerunSequence có giá trị khác, nó không tham gia JobInstance identity. Nếu JobInstance với businessDate này đã COMPLETED, lần chạy vẫn bị từ chối.

Cách đúng nếu thực sự muốn tạo instance mới:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addLong("rerunSequence", 2L, true)
    .toJobParameters();
~~~

Chỉ thay đổi cờ identifying khi có chủ đích nghiệp vụ. Không biến mọi tham số vận hành thành identifying vì điều đó có thể tạo quá nhiều JobInstance và làm khó quản lý lịch sử.

## 14. Thiết kế tham số cho rerun có kiểm soát

Một Job chạy theo ngày có thể dùng:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("sourceSystem", "CRM", true)
    .addLong("run.id", 2L, true)
    .addString("requestedBy", "operator", false)
    .addString("reason", "Corrected source mapping", false)
    .toJobParameters();
~~~

Trong ví dụ:

- businessDate xác định ngày nghiệp vụ.
- sourceSystem xác định nguồn dữ liệu.
- run.id tạo JobInstance mới cho lần xử lý lại.
- requestedBy và reason là metadata vận hành không thay đổi identity.

Cần quyết định quy tắc tăng run ID:

- Tăng tự động theo incrementer.
- Lấy sequence từ hệ thống điều phối.
- Dùng mã reprocess request do người vận hành tạo.
- Dùng correction version được quản lý trong database.

Không nên lấy timestamp tùy tiện nếu hệ thống cần biết các lần chạy lại thuộc cùng một yêu cầu sửa chữa. Một mã reprocess có ý nghĩa thường dễ audit hơn.

## 15. Rerun không tự bảo đảm dữ liệu đầu ra an toàn

Tạo JobInstance mới chỉ giải quyết danh tính execution trong JobRepository. Nó không tự xóa output cũ, rollback dữ liệu đã commit hoặc bảo đảm writer không ghi trùng.

Ví dụ Job ghi bảng kết quả:

~~~sql
INSERT INTO daily_customer_summary
    (business_date, customer_id, total_amount)
VALUES
    (:businessDate, :customerId, :totalAmount)
~~~

Nếu chạy lại cùng businessDate bằng run.id mới, các row có thể bị duplicate hoặc vi phạm unique constraint.

Trước khi cho phép rerun, phải xác định chính sách dữ liệu:

- Xóa kết quả của lần trước trong phạm vi được phép rồi tính lại.
- Ghi kết quả vào bảng staging theo run ID, sau đó publish phiên bản được chọn.
- Dùng upsert nếu nghiệp vụ cho phép cập nhật kết quả.
- Dùng unique business key và kiểm tra nội dung hiện có.
- Lưu lịch sử phiên bản và trạng thái active.
- Tách lần chạy kỹ thuật khỏi mã lô nghiệp vụ.

Không nên xóa toàn bộ dữ liệu cũ một cách mù quáng. Cần giới hạn theo business key, batch ID hoặc version và bảo đảm các downstream consumer hiểu phiên bản nào là chính thức.

### Tách run ID khỏi business key

Ví dụ bảng kết quả có thể lưu:

| Cột | Vai trò |
|---|---|
| business_date | Ngày nghiệp vụ |
| customer_id | Khóa bản ghi nghiệp vụ |
| run_id | Lần thực thi tạo ra kết quả |
| is_current | Phiên bản đang được dùng |
| processed_at | Thời điểm xử lý |

Thiết kế cụ thể tùy hệ thống. Điểm quan trọng là rerun có thể tạo dữ liệu mới nhưng vẫn phải có quy tắc chọn kết quả chính thức.

## 16. Rerun file và tài nguyên bên ngoài

Nếu Job tạo file output, chạy lại bằng JobInstance mới có thể ghi đè file cũ hoặc tạo nhiều file trùng.

Một số cách:

- Tên file chứa business date và run ID.
- Ghi vào thư mục staging riêng của lần chạy.
- Chỉ publish file sau khi mọi Step thành công.
- Lưu manifest ghi nhận phiên bản output.
- Dùng bước promotion để chọn bản kết quả được công nhận.
- Giữ output cũ theo retention policy.

Ví dụ:

~~~java
Path output = outputDirectory.resolve(
    "customer-summary-"
        + businessDate
        + "-run-"
        + runId
        + ".csv"
);
~~~

Tên file riêng giúp tránh ghi đè trong quá trình rerun. Một Step publish sau đó có thể cập nhật manifest hoặc chuyển file vào vị trí chính thức.

Với API, message broker hoặc hệ thống thanh toán, cần idempotency key hoặc cơ chế versioning. JobInstance mới không làm hệ thống đích quên rằng một business operation đã được thực hiện.

## 17. Xử lý request chạy trùng từ scheduler

Một scheduler có thể gửi cùng JobParameters nhiều lần do timeout, retry hoặc cấu hình lịch chạy. Khi JobInstance đã COMPLETED, Spring Batch từ chối request lặp. Đây là một cơ chế bảo vệ hữu ích.

Ứng dụng nên phân biệt:

- Request trùng của cùng một lần chạy: giữ identifying parameters giống nhau.
- Restart sau FAILED/STOPPED: giữ nguyên identifying parameters.
- Rerun có chủ đích sau COMPLETED: tạo identifying parameter mới.
- Lô nghiệp vụ mới: thay business key hoặc identifying parameters tương ứng.

Không thêm run.id mới mỗi lần scheduler retry request nếu ý định chỉ là gửi lại cùng một lần chạy. Làm vậy sẽ biến request trùng thành JobInstance mới và có thể xử lý dữ liệu hai lần.

### Dùng mã request ổn định

Một scheduler có thể tạo runRequestId trước khi gọi Job và giữ nguyên ID đó khi retry việc gửi lệnh. Nếu request đã được tiếp nhận hoặc Job đã hoàn tất, lần gửi lại vẫn ánh xạ về cùng JobInstance.

Nếu cần một rerun mới, tạo request ID mới theo quy trình phê duyệt hoặc điều phối.

## 18. Tra cứu JobInstance và JobExecution trước khi chạy

Trước khi quyết định restart hay rerun, công cụ vận hành nên tra cứu trạng thái hiện tại.

Có thể dùng JobExplorer:

~~~java
List<JobInstance> instances =
    jobExplorer.getJobInstances("dailyImportJob", 0, 20);

for (JobInstance instance : instances) {
    List<JobExecution> executions =
        jobExplorer.getJobExecutions(instance);

    for (JobExecution execution : executions) {
        log.info(
            "instanceId={}, executionId={}, status={}, exitStatus={}",
            instance.getInstanceId(),
            execution.getId(),
            execution.getStatus(),
            execution.getExitStatus()
        );
    }
}
~~~

Ví dụ trên minh họa cách tra cứu. Trong ứng dụng thực tế, cần lọc theo business key hoặc JobParameters để xác định đúng instance, thay vì chỉ dựa vào danh sách gần đây.

Thông tin cần kiểm tra:

- Job name.
- Identifying JobParameters.
- JobInstance ID.
- Các JobExecution thuộc instance.
- Trạng thái execution cuối cùng.
- StepExecution nào FAILED hoặc STOPPED.
- ExitStatus và failure exception.
- Job có restartable không.

Đừng tạo một instance mới chỉ vì không biết instance cũ đang ở trạng thái nào. Trước hết xác định đó là request trùng, restart hợp lệ hay rerun nghiệp vụ.

## 19. Các exception thường gặp khi launch lại

Một số lỗi thường gặp:

| Exception | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| JobInstanceAlreadyCompleteException | JobInstance đã COMPLETED với identifying parameters này | Nếu cần rerun, tạo JobInstance mới có identifying parameter khác |
| JobExecutionAlreadyRunningException | Có execution của cùng instance đang chạy | Kiểm tra trạng thái hiện tại; không khởi chạy song song cùng instance |
| JobRestartException | Không thể restart execution/instance theo chính sách hiện tại | Kiểm tra preventRestart, trạng thái và restartability |
| JobParametersInvalidException | JobParameters không hợp lệ theo validator | Sửa tham số đầu vào |
| NoSuchJobException | Không tìm thấy Job theo tên | Kiểm tra JobRegistry hoặc cấu hình |
| JobParametersNotFoundException | Không tìm thấy tham số được yêu cầu trong thao tác điều phối | Kiểm tra cấu hình incrementer hoặc request |

Không bắt JobInstanceAlreadyCompleteException rồi tự động thêm run ID và chạy lại. Làm vậy có thể che giấu scheduler gửi lặp và tạo side effect trùng. Hãy để lớp điều phối quyết định request là duplicate hay một rerun được yêu cầu rõ ràng.

## 20. Có nên xóa metadata để chạy lại cùng JobInstance?

Không nên xóa trực tiếp các dòng trong bảng metadata Spring Batch để ép JobInstance COMPLETED chạy lại.

JobRepository lưu quan hệ giữa:

- BATCH_JOB_INSTANCE.
- BATCH_JOB_EXECUTION.
- BATCH_JOB_EXECUTION_PARAMS.
- BATCH_STEP_EXECUTION.
- BATCH_JOB_EXECUTION_CONTEXT.
- BATCH_STEP_EXECUTION_CONTEXT.

Các bảng này có khóa ngoại và liên kết trạng thái. Xóa một phần metadata có thể để lại dữ liệu mồ côi, phá lịch sử audit hoặc làm restart/checkpoint không còn nhất quán.

Nếu cần xử lý lại, hãy tạo JobInstance mới bằng identifying parameter phù hợp. Nếu có yêu cầu bảo trì metadata, dùng quy trình retention/cleanup được thiết kế và kiểm thử riêng, không thao tác thủ công trong lúc Job đang hoạt động.

## 21. Tạo một JobInstance mới với JobLauncher

Ví dụ một service điều phối rerun:

~~~java
@Service
public class ImportJobLauncher {

    private final JobLauncher jobLauncher;
    private final Job dailyImportJob;

    public ImportJobLauncher(
            JobLauncher jobLauncher,
            Job dailyImportJob) {
        this.jobLauncher = jobLauncher;
        this.dailyImportJob = dailyImportJob;
    }

    public JobExecution rerun(
            LocalDate businessDate,
            long runId,
            String sourceSystem) throws Exception {

        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", businessDate.toString(), true)
            .addString("sourceSystem", sourceSystem, true)
            .addLong("run.id", runId, true)
            .toJobParameters();

        return jobLauncher.run(dailyImportJob, parameters);
    }
}
~~~

Caller phải cung cấp một run ID mới và hợp lệ. Trong hệ thống thực tế, nên kiểm tra quyền và lý do rerun, lưu audit request, và xác định output của lần chạy mới sẽ được publish như thế nào.

Không tự tăng run ID trong một retry HTTP hoặc retry message của cùng request. Mã run ID nên được tạo một lần cho yêu cầu rerun logic và được giữ ổn định qua các lần gửi lại request đó.

## 22. Kiểm thử hành vi COMPLETED và rerun

Cần kiểm thử cả hành vi từ chối lẫn cách tạo instance mới.

### Test 1: chạy cùng parameters sau khi COMPLETED

1. Khởi chạy Job với identifying parameters P.
2. Xác nhận JobExecution kết thúc COMPLETED.
3. Gọi lại cùng Job với cùng P.
4. Xác nhận lần gọi thứ hai bị từ chối bằng JobInstanceAlreadyCompleteException.
5. Xác nhận không có JobExecution mới được tạo cho cùng instance.

### Test 2: thay non-identifying parameter

1. Chạy Job với businessDate là identifying parameter.
2. Đánh dấu requestedBy là non-identifying.
3. Chạy lại với cùng businessDate nhưng requestedBy khác.
4. Xác nhận vẫn là cùng JobInstance.
5. Nếu instance đã COMPLETED, xác nhận launch bị từ chối.

### Test 3: thêm identifying run ID

1. Chạy Job với businessDate và run.id=1.
2. Xác nhận COMPLETED.
3. Chạy với cùng businessDate nhưng run.id=2.
4. Xác nhận một JobInstance mới được tạo.
5. Kiểm tra output không bị ghi trùng ngoài chính sách.

### Test 4: restart instance FAILED

1. Chạy Job với parameters P và làm một Step thất bại.
2. Xác nhận JobExecution FAILED.
3. Sửa điều kiện lỗi.
4. Chạy lại cùng P hoặc dùng JobOperator.restart(executionId).
5. Xác nhận JobExecution mới thuộc cùng JobInstance.
6. Kiểm tra Step đã hoàn tất và checkpoint được xử lý đúng.

### Test 5: allowStartIfComplete

Tạo một JobInstance thất bại ở Step sau, trong khi một Step trước đã COMPLETED và bật allowStartIfComplete. Restart JobInstance và xác nhận Step được chạy lại theo cấu hình. Sau khi toàn bộ JobInstance COMPLETED, gọi lại cùng parameters vẫn phải bị từ chối.

### Test 6: incrementer

Kiểm tra RunIdIncrementer hoặc incrementer tùy chỉnh:

- Không có run ID ban đầu.
- Run ID đã tồn tại.
- Tham số business key được giữ lại.
- Tham số tăng là identifying.
- Hai lần gọi startNextInstance tạo hai JobInstance khác nhau.
- Gọi JobLauncher.run với cùng parameters không tự tăng run ID.

## 23. Quy trình quyết định restart hay rerun

Khi nhận yêu cầu "chạy lại Job", hãy xác định mục đích trước:

1. **Tra cứu JobInstance:** tìm đúng Job name và identifying parameters.
2. **Kiểm tra execution cuối:** xác định FAILED, STOPPED, COMPLETED hay đang chạy.
3. **Nếu FAILED/STOPPED:** kiểm tra restartability và dùng lại identifying parameters ban đầu.
4. **Nếu đang chạy:** không khởi chạy thêm execution cùng instance; kiểm tra execution hiện tại.
5. **Nếu COMPLETED:** không restart cùng instance; xác định có cần một lần xử lý logic mới không.
6. **Nếu cần rerun:** tạo identifying parameter mới có ý nghĩa, ví dụ run.id hoặc reprocess.id.
7. **Kiểm tra dữ liệu đầu ra:** xác định upsert, staging, versioning hoặc cleanup có kiểm soát.
8. **Giữ request ID ổn định:** tránh tạo instance mới khi scheduler chỉ gửi lại cùng request.
9. **Ghi audit:** lưu người yêu cầu, lý do và run ID.
10. **Đối soát kết quả:** xác nhận dữ liệu cuối phản ánh đúng lần chạy được công nhận.

## 24. Những lỗi thiết kế thường gặp

### Gọi lại JobLauncher với cùng parameters sau COMPLETED

Cùng identifying parameters trỏ đến cùng JobInstance. Spring Batch từ chối tạo execution mới. Nếu cần rerun, tạo instance mới.

### Thay non-identifying parameter và nghĩ rằng đã tạo instance mới

Non-identifying parameter không tham gia identity. Thay requestedBy hoặc correlation ID không thay đổi JobInstance.

### Nghĩ RunIdIncrementer tự tăng khi JobLauncher.run()

Incrementer không tự sửa parameters do caller truyền. Nó được dùng khi yêu cầu bộ parameters tiếp theo qua cơ chế hỗ trợ incrementer.

### Dùng restart cho một Job đã hoàn tất

Restart dành cho execution thất bại hoặc dừng đủ điều kiện. Một JobInstance COMPLETED không thể restart bằng cùng identifying parameters.

### Dùng allowStartIfComplete để chạy lại toàn Job

Tùy chọn này điều khiển một Step đã COMPLETED trong một JobInstance đang restart. Nó không mở khóa một JobInstance đã COMPLETED.

### Tạo run ID mới cho mọi lần scheduler retry

Request trùng có thể trở thành JobInstance mới và xử lý cùng dữ liệu nhiều lần. Giữ request ID ổn định cho cùng một yêu cầu logic.

### Rerun nhưng không xử lý dữ liệu đầu ra

JobInstance mới không xóa output cũ. Writer có thể tạo duplicate, vi phạm unique constraint hoặc publish phiên bản sai.

### Xóa bảng metadata để ép chạy lại

Thao tác này có thể phá liên kết JobRepository, checkpoint và audit. Dùng identifying parameters mới và quy trình rerun có kiểm soát.

### Dùng timestamp ngẫu nhiên làm identity mà không có audit

Timestamp tạo instance mới nhưng không giải thích vì sao rerun. Dùng run request ID hoặc correction version có ý nghĩa và lưu lý do.

## 25. Những điểm cần nhớ

- JobInstance được xác định bằng Job name và identifying JobParameters.
- Một JobInstance có thể có nhiều JobExecution khi restart sau FAILED hoặc STOPPED.
- Khi JobInstance đã COMPLETED, launch lại với cùng identifying parameters bị từ chối bằng JobInstanceAlreadyCompleteException.
- Restart tiếp tục một JobInstance chưa hoàn tất; rerun tạo một JobInstance mới.
- Thêm identifying parameter mới như run.id hoặc reprocess.id để tạo instance mới.
- Thay non-identifying parameter không tạo JobInstance mới.
- RunIdIncrementer và JobParametersIncrementer tạo bộ tham số kế tiếp; JobLauncher.run không tự gọi incrementer.
- JobOperator.startNextInstance dùng incrementer để khởi chạy instance kế tiếp; JobOperator.restart dùng execution ID đủ điều kiện restart.
- preventRestart hạn chế restart sau thất bại; nó không phải cơ chế rerun sau COMPLETED.
- allowStartIfComplete áp dụng cho Step trong một lần restart JobInstance chưa hoàn tất, không cho phép restart JobInstance đã COMPLETED.
- Flow dùng end() có thể khiến Job kết thúc COMPLETED dù một Step trước đó thất bại; cần kiểm tra trạng thái cuối của JobExecution.
- JobInstance mới không tự bảo vệ output khỏi ghi trùng; cần idempotency, versioning, staging hoặc upsert.
- Không xóa metadata JobRepository để ép chạy lại.
- Tra cứu trạng thái trước khi quyết định restart hay rerun và ghi audit cho mọi lần xử lý lại.

Spring Batch từ chối restart một JobInstance đã COMPLETED để giữ ý nghĩa của trạng thái hoàn tất và tránh thực thi trùng. Khi cần tiếp tục công việc chưa hoàn thành, restart JobInstance thất bại hoặc dừng với cùng identifying parameters. Khi cần xử lý lại một lần logic đã hoàn tất, tạo JobInstance mới bằng identifying parameter có ý nghĩa và kiểm soát dữ liệu đầu ra để lần chạy mới an toàn.


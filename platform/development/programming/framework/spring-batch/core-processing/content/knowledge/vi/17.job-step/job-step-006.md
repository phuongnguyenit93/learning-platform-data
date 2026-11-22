# Restart job con

Trong Spring Batch, một Job có thể gọi một Job khác như một Step thông qua `JobStep`. Job được gọi bên trong thường được xem là **child job**, còn Job chứa JobStep là **parent job**. Cấu trúc này giúp tách một quy trình lớn thành các Job có trách nhiệm riêng, có thể theo dõi và vận hành độc lập.

Khi child job thất bại, nó có thể được restart theo `JobInstance` và `JobParameters` của chính nó. Parent job cũng có trạng thái và lịch sử thực thi riêng. Vì vậy, cần phân biệt restart child job trực tiếp với restart parent job chứa JobStep. Hai thao tác liên quan nhưng không đồng nghĩa: restart parent có thể làm JobStep launch child lại, còn restart child trực tiếp không tự động làm parent Step chuyển sang hoàn tất.

## 1. JobStep và quan hệ parent-child

`JobStep` là một loại Step có nhiệm vụ khởi chạy một Job khác bằng `JobLauncher`. Parent Job xem việc chạy child job như một bước trong flow của nó.

Ví dụ, quy trình xử lý đơn hàng có thể được chia thành:

- `dailyOrderJob`: parent job điều phối toàn bộ quy trình.
- `validateOrderJob`: child job kiểm tra dữ liệu đầu vào.
- `processOrderJob`: child job xử lý đơn hàng.
- `publishSummaryStep`: Step của parent tạo báo cáo tổng kết.

Flow có thể được mô tả như sau:

```text
Parent Job: dailyOrderJob
       |
       v
JobStep: validateOrderJobStep
       |
       +----> Child Job: validateOrderJob
       |             |
       |             +--> JobExecution của child
       |             +--> Các StepExecution của child
       |
       v
JobStep: processOrderJobStep
       |
       +----> Child Job: processOrderJob
       |             |
       |             +--> JobExecution của child
       |             +--> Các StepExecution của child
       |
       v
Parent Step: publishSummaryStep
       |
       v
Parent Job kết thúc
```

Parent và child có các đối tượng thực thi riêng:

| Đối tượng | Phạm vi |
|---|---|
| Parent `JobInstance` | Một đơn vị công việc logic của parent job. |
| Parent `JobExecution` | Một lần chạy cụ thể của parent job. |
| Parent `StepExecution` cho JobStep | Một lần parent thực hiện bước gọi child job. |
| Child `JobInstance` | Một đơn vị công việc logic của child job, được xác định bằng tên child job và identifying parameters. |
| Child `JobExecution` | Một lần thử thực thi child job. |
| Child `StepExecution` | Các lần thực thi Step bên trong child job. |

Child job không chỉ là một phương thức Java được gọi bên trong parent. Nó có JobInstance, JobExecution, StepExecution và metadata riêng trong `JobRepository`.

## 2. Vì sao cần phân biệt restart parent và restart child?

Giả sử parent job chạy một JobStep để gọi `customerImportJob`. Child job bắt đầu xử lý dữ liệu nhưng thất bại ở Step thứ hai:

```text
Parent JobExecution #100
  |
  +--> Parent StepExecution: customerImportJobStep = FAILED
          |
          +--> Child JobInstance: customerImportJob / businessDate=2026-11-15
                  |
                  +--> Child JobExecution #201 = FAILED
                          validateStep = COMPLETED
                          importStep   = FAILED
```

Khi restart parent với cùng identifying parameters, parent tạo một JobExecution mới cho cùng Parent JobInstance. JobStep được thực hiện lại và gọi child job với các tham số đã trích xuất. Nếu child JobInstance trước đó đang ở trạng thái có thể restart như `FAILED` hoặc `STOPPED`, Spring Batch có thể tạo Child JobExecution mới cho cùng Child JobInstance.

```text
Parent JobInstance: dailyOrderJob / businessDate=2026-11-15
  |
  +--> Parent JobExecution #100 = FAILED
  |       customerImportJobStep = FAILED
  |
  +--> Parent JobExecution #105 = COMPLETED
          customerImportJobStep = COMPLETED
             |
             +--> Child JobInstance: customerImportJob / businessDate=2026-11-15
                     |
                     +--> Child JobExecution #201 = FAILED
                     +--> Child JobExecution #208 = COMPLETED
```

Restart parent thường là cách tự nhiên khi muốn tiếp tục toàn bộ quy trình điều phối từ JobStep đã thất bại. Nếu chỉ restart child trực tiếp, parent JobExecution và Parent StepExecution vẫn giữ trạng thái cũ. Parent không tự biết child đã được xử lý thủ công cho đến khi có cơ chế đồng bộ hoặc parent được chạy lại theo cách phù hợp.

## 3. Child job được xác định bằng JobParameters nào?

Khi JobStep gọi child job, nó cần tạo `JobParameters` cho child. `JobParametersExtractor` chịu trách nhiệm trích xuất tham số từ `StepExecution` của parent.

Các tham số định danh của child quyết định Child JobInstance. Vì vậy, lựa chọn tham số ảnh hưởng trực tiếp đến restart:

- Cùng tên child job và cùng identifying parameters: cùng Child JobInstance.
- Khác identifying parameters: Child JobInstance mới.
- Thay đổi tham số không định danh: vẫn là cùng Child JobInstance.

Ví dụ, nếu child job xử lý dữ liệu theo ngày và file nguồn:

```text
Child Job: customerImportJob
  businessDate=2026-11-15  (identifying)
  inputFile=customers.csv  (identifying)
  parentExecutionId=100    (non-identifying)
```

`businessDate` và `inputFile` xác định đơn vị công việc của child. `parentExecutionId` chỉ dùng truy vết parent nào đã yêu cầu chạy child. Khi parent restart, parent có JobExecution ID mới; nếu `parentExecutionId` là tham số định danh của child, mỗi lần restart parent sẽ tạo Child JobInstance mới và có thể xử lý dữ liệu lại từ đầu. Vì vậy, thông tin truy vết thường nên là tham số không định danh.

## 4. Trích xuất JobParameters cho child bằng JobParametersExtractor

Spring Batch cung cấp interface `JobParametersExtractor` và implementation `DefaultJobParametersExtractor`. Có thể dùng extractor mặc định khi các key cần chuyển từ ExecutionContext đã được xác định. Với quy tắc nghiệp vụ cụ thể, có thể triển khai extractor riêng để kiểm soát chính xác identifying và non-identifying parameters.

Ví dụ custom extractor:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.step.job.JobParametersExtractor;

public class CustomerImportParametersExtractor
        implements JobParametersExtractor {

    @Override
    public JobParameters getJobParameters(Job job, StepExecution stepExecution) {
        JobParameters parentParameters =
                stepExecution.getJobExecution().getJobParameters();

        String businessDate = parentParameters.getString("businessDate");
        String inputFile = stepExecution.getExecutionContext()
                .getString("inputFile");

        if (businessDate == null || inputFile == null) {
            throw new IllegalStateException(
                    "businessDate and inputFile are required for child job");
        }

        return new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .addString("inputFile", inputFile, true)
                .addLong("parentExecutionId",
                        stepExecution.getJobExecution().getId(), false)
                .toJobParameters();
    }
}
```

Extractor trên lấy ngày nghiệp vụ từ JobParameters của parent và đường dẫn file từ Step ExecutionContext. Hai giá trị này được đánh dấu identifying cho child. ID lần chạy của parent được thêm để truy vết nhưng không tham gia danh tính Child JobInstance.

Nếu giá trị `inputFile` được tạo ở một Step trước đó, Step đó cần lưu key vào ExecutionContext trước khi JobStep được thực hiện. Có thể dùng StepExecution trực tiếp hoặc cơ chế `ExecutionContextPromotionListener` nếu dữ liệu cần được đưa lên Job ExecutionContext.

## 5. Khai báo JobStep trong Java

Với Spring Batch 5 trở lên, có thể cấu hình JobStep từ `StepBuilder`, chỉ định child Job, JobLauncher, extractor và transaction manager:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.job.JobParametersExtractor;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ParentJobConfig {

    @Bean
    public Step customerImportJobStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JobLauncher jobLauncher,
            Job customerImportJob,
            JobParametersExtractor customerImportParametersExtractor) {

        return new StepBuilder("customerImportJobStep", jobRepository)
                .job(customerImportJob)
                .launcher(jobLauncher)
                .parametersExtractor(customerImportParametersExtractor)
                .transactionManager(transactionManager)
                .build();
    }

    @Bean
    public Job dailyOrderJob(
            JobRepository jobRepository,
            Step customerImportJobStep,
            Step publishSummaryStep) {

        return new JobBuilder("dailyOrderJob", jobRepository)
                .start(customerImportJobStep)
                .next(publishSummaryStep)
                .build();
    }
}
```

`customerImportJob` là child job đã được khai báo ở cấu hình riêng. `customerImportJobStep` là Step của parent, chịu trách nhiệm launch child. `JobParametersExtractor` tạo bộ tham số cho child từ trạng thái của parent StepExecution.

Trong ứng dụng thực tế, cần bảo đảm child Job được đăng ký trong cùng application context hoặc được cung cấp qua cơ chế cấu hình phù hợp. Parent và child thường dùng chung `JobRepository` để metadata của cả hai Job được quản lý và tra cứu thống nhất.

## 6. Điều gì xảy ra khi child job FAILED?

Khi child job thất bại, JobStep nhận kết quả thất bại từ child và parent Step thường kết thúc `FAILED`. Parent Job theo đó thường kết thúc `FAILED` nếu flow không có transition riêng để xử lý kết quả lỗi.

```text
Parent Job
   |
   v
JobStep: runChildJob
   |
   v
Child JobExecution
   |
   +--> validateStep = COMPLETED
   +--> importStep   = FAILED
   |
   v
Child JobExecution = FAILED
   |
   v
Parent JobStep = FAILED
   |
   v
Parent JobExecution = FAILED
```

Nếu child JobInstance có thể restart, chạy lại parent JobInstance với cùng identifying parameters sẽ khiến JobStep được thử lại. Khi extractor tạo lại đúng identifying JobParameters cho child, `JobLauncher` nhận diện Child JobInstance cũ và có thể tạo Child JobExecution mới để restart.

Điều kiện quan trọng là extractor phải trả về bộ identifying parameters ổn định. Nếu mỗi lần parent restart lại thêm UUID hoặc timestamp mới vào identifying parameters của child, Spring Batch sẽ tạo Child JobInstance mới thay vì restart instance thất bại.

## 7. Điều gì xảy ra khi child job đã COMPLETED?

Child JobInstance đã hoàn tất không thể được launch lại như một công việc mới với cùng identifying parameters. Nếu JobStep được thực hiện lại và gọi child bằng đúng tham số định danh của instance đã `COMPLETED`, Spring Batch thường ném `JobInstanceAlreadyCompleteException`.

Có thể gặp trường hợp:

```text
Child JobInstance: customerImportJob / businessDate=2026-11-15
  |
  +--> Child JobExecution #201 = COMPLETED

Parent restart
  |
  +--> JobStep chạy lại
          |
          +--> launch child với cùng identifying parameters
                    |
                    +--> JobInstanceAlreadyCompleteException
```

Tình huống này thường xảy ra khi parent JobStep cần chạy lại trong khi child đã hoàn tất ở lần trước, ví dụ parent bị dừng hoặc lỗi ở ranh giới sau khi child đã commit kết quả nhưng trước khi parent Step được ghi nhận hoàn tất. Cũng có thể xảy ra nếu cấu hình cho phép parent JobStep chạy lại sau khi nó đã hoàn thành.

Không nên xử lý bằng cách tự động thêm tham số định danh mới cho child. Điều đó có thể làm child chạy lại toàn bộ dữ liệu và tạo tác dụng phụ trùng lặp. Trước tiên cần xác định child đã hoàn thành đúng công việc chưa và trạng thái parent Step đã được lưu như thế nào.

Các hướng xử lý phù hợp:

1. Thiết kế child job idempotent, có khóa nghiệp vụ để lần chạy mới không tạo dữ liệu trùng.
2. Dùng trạng thái hoặc audit record để parent nhận biết child đã hoàn tất đúng đơn vị công việc và xử lý tiếp theo theo quy tắc rõ ràng.
3. Nếu thực sự cần một lần xử lý mới, tạo Child JobInstance mới bằng tham số định danh mang ý nghĩa nghiệp vụ, ví dụ `reprocessVersion` hoặc `correctionBatchId`.
4. Chỉ bật `allowStartIfComplete(true)` cho JobStep khi việc launch child lại đã được thiết kế và kiểm soát an toàn.

## 8. Restart child trực tiếp

Có thể cần restart child job độc lập để sửa lỗi dữ liệu hoặc khôi phục một lần chạy mà không muốn chạy lại toàn bộ parent. Khi đó, dùng chính Child JobInstance và identifying JobParameters của lần chạy trước.

Quy trình tổng quát:

1. Tra cứu Child JobExecution thất bại bằng `JobExplorer` hoặc `JobRepository`.
2. Xác định Child JobInstance và identifying JobParameters.
3. Sửa nguyên nhân thất bại, ví dụ file đầu vào, dữ liệu hoặc cấu hình phụ thuộc.
4. Restart child bằng API điều phối phù hợp, chẳng hạn `JobOperator.restart(executionId)` hoặc launch child bằng cùng Job và cùng identifying parameters.
5. Theo dõi Child JobExecution mới đến trạng thái cuối.
6. Đồng bộ kết quả với parent theo quy trình vận hành của ứng dụng.

Ví dụ minh họa restart bằng `JobOperator`:

```java
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class ChildJobRestartService {

    private final JobOperator jobOperator;

    public ChildJobRestartService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public Long restartChild(Long failedExecutionId) throws Exception {
        return jobOperator.restart(failedExecutionId);
    }
}
```

`failedExecutionId` phải là ID của Child JobExecution cần restart, không phải Parent JobExecution ID. Thao tác restart child trực tiếp không tự động đánh dấu Parent StepExecution là `COMPLETED`. Nếu parent vẫn ở trạng thái thất bại, cần có bước điều phối để xác nhận child đã hoàn tất và cho phép parent tiếp tục mà không launch trùng child.

## 9. Restart parent để JobStep gọi lại child

Khi muốn toàn bộ flow parent tiếp tục theo thiết kế, thường restart parent JobInstance. Spring Batch tạo Parent JobExecution mới; các Step đã hoàn thành thường được bỏ qua theo chính sách restart, còn JobStep thất bại được thực hiện lại.

```text
Parent JobInstance: dailyOrderJob / businessDate=2026-11-15
  |
  +--> Parent JobExecution #100 = FAILED
  |       validateStep = COMPLETED
  |       customerImportJobStep = FAILED
  |
  +--> Parent JobExecution #105
          validateStep = skipped (đã hoàn thành)
          customerImportJobStep = chạy lại
             |
             +--> Child JobInstance cùng identifying parameters
                      Child JobExecution mới
```

Nếu child trước đó thất bại, lần gọi mới có thể restart child. Nếu child đã hoàn tất, lần gọi có thể bị từ chối như đã giải thích ở phần trước. Do đó, việc restart parent cần xem cả lịch sử Child JobExecution, không chỉ trạng thái parent.

Parent và child có thể có chính sách restart khác nhau. Parent có thể cho phép restart nhưng child bị cấu hình `preventRestart()`, hoặc ngược lại. Cần kiểm tra chính sách của cả hai Job và các Step liên quan.

## 10. Lưu ý về JobParameters và RunIdIncrementer

Một lỗi phổ biến là dùng `RunIdIncrementer` cho child job rồi cho rằng mọi lần parent restart đều sẽ tiếp tục đúng child instance. Incrementer tạo tham số định danh mới cho lần chạy kế tiếp; do đó có thể tạo Child JobInstance mới.

Ví dụ, nếu child nhận:

```text
businessDate=2026-11-15
run.id=1
```

và khi restart extractor hoặc launcher tạo:

```text
businessDate=2026-11-15
run.id=2
```

thì đây là Child JobInstance mới, không phải restart Child JobInstance cũ. Điều này có thể hữu ích khi nghiệp vụ chủ đích tạo một lần xử lý mới, nhưng không phù hợp nếu mục tiêu là tiếp tục lần chạy thất bại.

Hãy xác định rõ:

- Tham số nào xác định đơn vị công việc của child?
- Tham số nào chỉ phục vụ trace/log?
- Parent restart có phải giữ nguyên child identifying parameters không?
- Khi tái xử lý dữ liệu đã hoàn tất, mã phiên bản hoặc mã correction nào biểu diễn yêu cầu đó?

Một quy ước tốt là dùng khóa nghiệp vụ ổn định làm identifying parameters, còn ID parent execution và thông tin người yêu cầu là non-identifying parameters.

## 11. Transaction và JobRepository trong JobStep

JobStep có transaction riêng cho việc thực hiện Step của parent, trong khi child job thực hiện các transaction của các Step bên trong nó. Không nên mở một transaction duy nhất bao trùm parent và toàn bộ child job.

Ví dụ:

```text
Parent JobStep transaction
       |
       +--> launch child Job
                |
                +--> Child Step 1 chunk transactions
                +--> Child Step 2 chunk transactions
                +--> Child Tasklet transactions
```

Các transaction dữ liệu của child được quản lý bởi transaction manager cấu hình cho các Step child. Nếu parent và child dùng chung database, transaction boundary vẫn nên được giữ ở phạm vi từng Step/chunk. Child job có thể đã commit dữ liệu trước khi parent JobStep hoàn tất.

Điều này giải thích vì sao có thể xuất hiện trường hợp child đã `COMPLETED` nhưng parent JobStep chưa ghi nhận hoàn tất. Transaction rollback của parent không tự động hoàn tác mọi transaction đã commit trong child. Thiết kế restart cần dựa trên metadata của cả hai cấp và bảo đảm các thao tác nghiệp vụ có tính idempotent.

## 12. Theo dõi parent và child execution

Khi điều tra lỗi, cần tra cứu đúng cấp:

| Cần tìm | Thông tin cần xem |
|---|---|
| Parent JobInstance | Tên parent Job và identifying parent JobParameters. |
| Parent JobExecution | Lần chạy parent, trạng thái cuối và lỗi. |
| Parent StepExecution | JobStep nào thất bại, ExitStatus và thời điểm thực thi. |
| Child JobInstance | Tên child Job và identifying child JobParameters. |
| Child JobExecution | Lần chạy child nào thất bại/hoàn tất, có bao nhiêu lần restart. |
| Child StepExecution | Step bên trong child gây lỗi, số liệu đọc/ghi và checkpoint. |

`JobExplorer` có thể dùng để tra cứu JobInstance và các JobExecution theo tên Job, tham số hoặc ID. Khi JobStep lưu child execution ID hoặc kết quả vào ExecutionContext/audit, việc lần theo quan hệ parent-child sẽ dễ hơn. Không nên dựa vào ID parent và child giống nhau; đây là hai execution độc lập.

Một cách vận hành hữu ích là ghi log các thông tin sau ở thời điểm JobStep gọi child:

- Parent JobExecution ID.
- Parent StepExecution ID và tên JobStep.
- Child Job name.
- Child JobParameters, đặc biệt identifying parameters.
- Child JobExecution ID trả về từ JobLauncher nếu có.
- Child BatchStatus và ExitStatus.

Không ghi bí mật hoặc token vào log JobParameters. Chỉ ghi các giá trị cần truy vết.

## 13. Kiểm thử restart parent và child

Kiểm thử đơn vị cho `JobParametersExtractor` nên xác nhận bộ tham số child được tạo đúng và giữ nguyên identifying parameters khi parent restart.

Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;

class CustomerImportParametersExtractorTest {

    @Test
    void keepsChildIdentityStableAcrossParentExecutions() {
        JobParameters parentParameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-15", true)
                .toJobParameters();
        JobExecution parentExecution = new JobExecution(
                new JobInstance(1L, "dailyOrderJob"),
                100L,
                parentParameters);
        StepExecution parentStepExecution =
                new StepExecution("customerImportJobStep", parentExecution);
        parentStepExecution.getExecutionContext()
                .putString("inputFile", "customers.csv");

        Job childJob = mock(Job.class); // Extractor không cần đọc metadata của Job.
        JobParameters childParameters =
                new CustomerImportParametersExtractor()
                        .getJobParameters(childJob, parentStepExecution);

        assertEquals("2026-11-15", childParameters.getString("businessDate"));
        assertEquals("customers.csv", childParameters.getString("inputFile"));
        assertFalse(childParameters.getParameters()
                .get("parentExecutionId").isIdentifying());
    }
}
```

Test trên minh họa cách kiểm tra identifying flag. Trong test thực tế, có thể tạo hai Parent JobExecution khác ID nhưng cùng identifying JobParameters, gọi extractor cho từng StepExecution rồi xác nhận các tham số định danh của child bằng nhau trong khi `parentExecutionId` khác nhau và vẫn không định danh.

Integration test cần chạy parent JobStep cùng child Job trên `JobRepository` test:

1. Chạy parent lần đầu, cấu hình child thất bại ở một Step.
2. Xác nhận parent JobExecution và child JobExecution đều thất bại theo flow.
3. Sửa điều kiện lỗi và restart parent với cùng identifying parent JobParameters.
4. Xác nhận child có JobExecution mới nhưng vẫn cùng Child JobInstance.
5. Xác nhận child hoàn tất và parent tiếp tục đến Step sau JobStep.
6. Tạo thêm trường hợp child đã `COMPLETED` nhưng parent JobStep phải chạy lại để kiểm tra cách ứng dụng xử lý `JobInstanceAlreadyCompleteException`.

Test cần dùng dữ liệu cố định và kiểm tra dữ liệu nghiệp vụ sau restart, không chỉ kiểm tra trạng thái `COMPLETED`. Nếu child ghi dữ liệu ra database, xác nhận không có bản ghi trùng hoặc cập nhật sai khi Step được chạy lại.

## 14. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Restart parent nhưng child tạo JobInstance mới | Extractor thêm identifying parameter mới mỗi lần parent chạy. | Giữ child identifying parameters ổn định qua restart. |
| Child đã COMPLETED nhưng JobStep launch lại bị từ chối | Cùng child JobInstance không được launch lại sau khi hoàn tất. | Kiểm tra child execution và trạng thái parent; xử lý completed child theo chính sách rõ ràng. |
| Restart child trực tiếp nhưng parent vẫn FAILED | Child và parent có execution metadata riêng. | Đồng bộ trạng thái và điều phối parent tiếp tục theo cách được thiết kế. |
| Dùng parentExecutionId làm identifying parameter của child | Parent restart có execution ID mới nên tạo child instance mới. | Dùng parentExecutionId làm non-identifying để truy vết. |
| Dùng RunIdIncrementer cho mọi lần gọi child | Mỗi lần gọi có thể tạo Child JobInstance mới và xử lý lại dữ liệu. | Chỉ dùng incrementer khi cần một đơn vị xử lý mới có chủ đích. |
| Cho rằng rollback parent sẽ rollback child | Child Step có transaction riêng và có thể đã commit. | Kiểm tra trạng thái child và thiết kế thao tác idempotent. |
| Chỉ xem Parent JobExecution khi điều tra | Không biết child đã chạy đến đâu hoặc đã hoàn tất chưa. | Tra cứu cả Parent StepExecution và Child JobExecution/StepExecution. |
| Không kiểm tra chính sách restart của child | Child có thể được cấu hình không cho restart. | Kiểm tra `preventRestart`, trạng thái execution và khả năng restart của từng Step. |

## Kết luận

`JobStep` cho phép parent Job gọi một child Job như một Step, nhưng parent và child có JobInstance, JobExecution và StepExecution riêng. Khi child thất bại, restart parent với cùng identifying parameters thường khiến JobStep gọi lại child; nếu child cũng dùng cùng identifying parameters, Spring Batch có thể restart đúng Child JobInstance. Nếu child đã `COMPLETED`, launch lại cùng instance sẽ bị từ chối, vì vậy cần kiểm tra lịch sử và chính sách xử lý completed child. Hãy dùng `JobParametersExtractor` để tạo tham số child ổn định, giữ ID parent execution ở dạng non-identifying khi chỉ phục vụ trace, và thiết kế các thao tác nghiệp vụ idempotent để parent-child restart an toàn.

# Dùng JobStep cho quy trình độc lập

Trong Spring Batch, `JobStep` cho phép một Job khởi chạy một Job khác như một Step trong Job flow. Job bên ngoài đóng vai trò điều phối; Job được gọi bên trong thường được gọi là *child job* hoặc *job con*. Cách tổ chức này hữu ích khi một quy trình lớn gồm nhiều quy trình batch độc lập, có thể tái sử dụng hoặc cần được quản lý bằng lifecycle riêng.

Ví dụ, Job tổng hợp dữ liệu cuối ngày có thể lần lượt gọi Job nhập dữ liệu, Job đối soát và Job tạo báo cáo. Mỗi Job con vẫn có cấu trúc Step, JobParameters, JobInstance và JobExecution riêng. Job cha theo dõi lời gọi Job con thông qua một Step kiểu JobStep.

`JobStep` phù hợp khi muốn tái sử dụng một Job đã được định nghĩa, tách trách nhiệm giữa các quy trình hoặc giữ metadata thực thi của từng quy trình riêng biệt. Nó không đơn giản chỉ là gọi một method Java: JobStep dùng `JobLauncher` và `JobRepository` để khởi chạy Job con theo cơ chế của Spring Batch.

## 1. JobStep là gì?

`JobStep` là một implementation của `Step` có nhiệm vụ khởi chạy một Job khác. Trong Job cha, JobStep xuất hiện như một Step bình thường; khi Step này được thực thi, nó gọi `JobLauncher` để chạy Job con.

```text
Parent Job: dailySettlementJob
    |
    +--> Step: prepareSettlementStep
    |
    +--> JobStep: importTransactionsJobStep
    |       |
    |       +--> Child Job: importTransactionsJob
    |               +--> extractTransactionsStep
    |               +--> normalizeTransactionsStep
    |
    +--> JobStep: reconcileAccountsJobStep
    |       |
    |       +--> Child Job: reconcileAccountsJob
    |               +--> compareBalancesStep
    |               +--> recordDifferencesStep
    |
    +--> Step: publishSummaryStep
```

Trong sơ đồ, `dailySettlementJob` không cần chứa trực tiếp mọi Step chi tiết của hai quy trình con. Nó chỉ khai báo hai JobStep để gọi các Job tương ứng. Mỗi Job con có thể được phát triển, kiểm thử và tái sử dụng độc lập.

Một JobStep có các thành phần chính:

- Job con cần được khởi chạy.
- `JobLauncher` thực hiện yêu cầu khởi chạy.
- `JobParametersExtractor` tạo JobParameters cho Job con từ metadata của lần thực thi Job cha.
- `JobRepository` lưu metadata của Step cha và các JobExecution của Job con theo cấu hình repository.

## 2. Job cha và Job con có execution riêng

Điểm quan trọng nhất khi dùng JobStep là Job con thực sự được khởi chạy như một Job. Nó có JobInstance và JobExecution riêng, không phải các Step bổ sung bên trong cùng JobExecution của Job cha.

```text
Parent JobExecution #100
  |
  +-- StepExecution: prepareSettlementStep
  |
  +-- StepExecution: importTransactionsJobStep
        |
        +-- Child JobExecution #205
              |
              +-- StepExecution: extractTransactionsStep
              +-- StepExecution: normalizeTransactionsStep
```

Parent JobExecution lưu lịch sử của Job cha. StepExecution của JobStep ghi nhận lần thực thi Step wrapper đó. Job con có JobExecution riêng với các StepExecution của chính nó.

Vì vậy, khi điều tra lỗi, cần phân biệt ba lớp metadata:

1. JobExecution của Job cha.
2. StepExecution của JobStep trong Job cha.
3. JobExecution và StepExecution của Job con.

Job con cũng có JobInstance riêng, được xác định bởi tên Job con và các JobParameters identifying mà JobStep truyền vào. Hai Job cha khác nhau có thể vô tình khởi chạy cùng một JobInstance con nếu chúng truyền cùng bộ identifying parameters cho cùng Job con.

## 3. Cấu hình JobStep bằng Java

Trong Spring Batch hiện đại, có thể dùng `JobStepBuilder` để tạo một Step khởi chạy Job con. Ví dụ:

```java
@Bean
public Step importTransactionsJobStep(
        JobRepository jobRepository,
        JobLauncher jobLauncher,
        Job importTransactionsJob,
        JobParametersExtractor childParametersExtractor) {

    return new JobStepBuilder(new StepBuilder("importTransactionsJobStep", jobRepository))
            .job(importTransactionsJob)
            .launcher(jobLauncher)
            .parametersExtractor(childParametersExtractor)
            .build();
}
```

Trong cấu hình này:

- `new StepBuilder("importTransactionsJobStep", jobRepository)` tạo định nghĩa Step wrapper ở Job cha.
- `.job(importTransactionsJob)` chỉ định Job con sẽ được chạy.
- `.launcher(jobLauncher)` cung cấp thành phần khởi chạy Job con.
- `.parametersExtractor(childParametersExtractor)` xác định bộ JobParameters truyền sang Job con.
- `.build()` tạo JobStep để đăng ký vào Job cha.

Job con phải được khai báo như một Job bean độc lập. JobStep chỉ tham chiếu và khởi chạy Job đó; nó không tự tạo các Step con.

API builder có thể thay đổi giữa các phiên bản Spring Batch. Với dự án đang dùng phiên bản khác, hãy sử dụng builder/constructor tương ứng với dependency thực tế. Nguyên tắc vẫn là cấu hình Job con, JobLauncher và JobParametersExtractor cho JobStep.

## 4. Truyền JobParameters sang Job con

Job con thường cần dữ liệu đầu vào giống hoặc liên quan đến Job cha, ví dụ ngày nghiệp vụ, mã nguồn dữ liệu hoặc đường dẫn file. `JobParametersExtractor` quyết định các tham số nào được truyền sang Job con.

Ví dụ cấu hình `DefaultJobParametersExtractor` để chọn các key cần chuyển tiếp:

```java
@Bean
public JobParametersExtractor childParametersExtractor() {
    DefaultJobParametersExtractor extractor = new DefaultJobParametersExtractor();
    extractor.setKeys(new String[] {
            "businessDate",
            "sourceSystem",
            "inputFile"
    });
    return extractor;
}
```

Sau đó JobStep dùng extractor này khi khởi chạy Job con. Hãy khai báo rõ các key mà Job con cần thay vì dựa vào một giả định ngầm về tham số được truyền.

`DefaultJobParametersExtractor` là implementation tiêu chuẩn để trích xuất tham số từ metadata của execution cha theo các key được cấu hình. Nếu cần đổi tên key, tạo tham số mới hoặc áp dụng quy tắc identifying khác, có thể triển khai một `JobParametersExtractor` tùy chỉnh.

### Tùy chỉnh tham số cho Job con

Đôi khi Job con cần tên tham số khác với Job cha. Ví dụ, Job cha dùng `businessDate`, trong khi Job con yêu cầu `settlementDate`. Có thể triển khai extractor riêng:

```java
public class SettlementParametersExtractor implements JobParametersExtractor {

    @Override
    public JobParameters extractJobParameters(
            Job job,
            StepExecution stepExecution) {

        String businessDate = stepExecution.getJobExecution()
                .getJobParameters()
                .getString("businessDate");

        if (businessDate == null || businessDate.isBlank()) {
            throw new IllegalArgumentException("businessDate is required");
        }

        return new JobParametersBuilder()
                .addString("settlementDate", businessDate, true)
                .addString("parentJobName",
                        stepExecution.getJobExecution().getJobInstance().getJobName(), false)
                .toJobParameters();
    }
}
```

Phương thức của `JobParametersExtractor` nhận Job con và StepExecution của JobStep cha. Từ đó, extractor có thể đọc JobParameters hoặc ExecutionContext của parent execution để tạo bộ tham số thích hợp.

Trong ví dụ, `settlementDate` là identifying parameter của Job con; `parentJobName` chỉ phục vụ truy vết nên được đánh dấu non-identifying. Cách đánh dấu phải dựa trên nghiệp vụ của Job con.

## 5. JobInstance của Job con và định danh tham số

JobInstance của Job con được xác định theo tên Job con và các JobParameters identifying mà extractor tạo ra. JobInstance của Job cha không tự động trở thành JobInstance của Job con.

Ví dụ, Job cha chạy cho ngày `2026-11-15` và extractor truyền `settlementDate=2026-11-15` sang Job con:

```text
Parent JobInstance: dailySettlementJob / businessDate=2026-11-15
        |
        +--> JobStep: importTransactionsJobStep
                 |
                 +--> Child JobInstance:
                        importTransactionsJob / settlementDate=2026-11-15
```

Nếu hai Job cha khác nhau cùng gọi `importTransactionsJob` với `settlementDate=2026-11-15` và không có identifying parameter nào khác, chúng sẽ cùng hướng đến một JobInstance con. Nếu JobInstance đó đã hoàn tất, lần khởi chạy tiếp theo có thể bị từ chối vì instance đã complete. Nếu đang chạy, có thể nhận exception báo execution đang chạy.

Hãy quyết định rõ Job con đại diện cho công việc logic nào:

- Nếu Job con phải xử lý đúng một lần cho mỗi ngày nghiệp vụ, chỉ ngày nghiệp vụ và các khóa nghiệp vụ liên quan nên xác định instance.
- Nếu Job con phải chạy riêng cho từng tenant hoặc nguồn dữ liệu, đưa tenant/source key vào identifying parameters.
- Nếu mỗi parent invocation thực sự cần một child run độc lập, hãy truyền một business request ID ổn định cho lần yêu cầu đó. Không thêm timestamp ngẫu nhiên chỉ để né lỗi instance trùng.

Restart cần giữ nguyên identifying parameters của Job con để tiếp tục cùng JobInstance con. Tạo một tham số identifying mới thường đồng nghĩa với tạo một công việc logic mới, không phải restart công việc cũ.

## 6. JobStep và restart của Job cha

JobStep có metadata StepExecution trong Job cha và khởi chạy Job con bằng JobLauncher. Nếu Job con thất bại, lần thực thi JobStep của Job cha cũng không hoàn tất bình thường. Khi Job cha được restart, JobStep có thể được thực thi lại và yêu cầu khởi chạy Job con với bộ JobParameters được extractor tạo ra.

Kết quả của lần khởi chạy lại phụ thuộc trạng thái JobInstance con:

- Nếu Job con thất bại và có thể restart, JobLauncher có thể tạo JobExecution mới trên cùng JobInstance con.
- Nếu Job con vẫn đang chạy, yêu cầu khởi chạy trùng có thể bị từ chối.
- Nếu Job con đã hoàn tất với cùng identifying parameters, yêu cầu chạy lại có thể bị từ chối vì JobInstance đã complete.
- Nếu extractor tạo identifying parameters khác, JobLauncher có thể tạo JobInstance con mới; điều này có thể không đúng nếu mục tiêu là restart công việc trước đó.

Vì vậy, JobParametersExtractor cần tạo kết quả ổn định qua các lần restart của Job cha. Đừng dùng `JobExecutionId` của parent làm identifying parameter cho child nếu mục tiêu là restart child JobInstance cũ: parent execution ID thay đổi qua restart.

Nếu Job con đã hoàn tất nhưng Job cha thất bại sau đó ở một Step khác, khi restart Job cha, Step JobStep đã hoàn tất thường được bỏ qua theo quy tắc restart của Spring Batch. Nếu JobStep được cấu hình `allowStartIfComplete(true)`, nó có thể chạy lại; khi đó Job con có thể từ chối vì JobInstance đã complete. Chỉ bật tùy chọn này khi hành vi chạy lại đã được thiết kế rõ ràng.

## 7. Cấu hình Job cha gọi nhiều Job con

Một Job cha có thể gọi nhiều Job con tuần tự bằng nhiều JobStep:

```java
@Bean
public Job dailySettlementJob(
        JobRepository jobRepository,
        Step prepareSettlementStep,
        Step importTransactionsJobStep,
        Step reconcileAccountsJobStep,
        Step publishSummaryStep) {

    return new JobBuilder("dailySettlementJob", jobRepository)
            .start(prepareSettlementStep)
            .next(importTransactionsJobStep)
            .next(reconcileAccountsJobStep)
            .next(publishSummaryStep)
            .build();
}
```

Flow trên cho phép tách mỗi quy trình con thành một Job riêng, trong khi Job cha giữ thứ tự điều phối tổng thể. Nếu một JobStep thất bại, các Step sau của Job cha không tiếp tục theo luồng tuần tự mặc định.

Có thể dùng conditional transition hoặc decider giữa các JobStep để chọn Job con theo kết quả của quy trình trước. Ví dụ, chỉ chạy Job đối soát khi Job nhập dữ liệu hoàn tất với exit code phù hợp.

## 8. Theo dõi trạng thái Job con

JobStep là một Step trong Job cha, nhưng Job con có JobExecution riêng. Khi điều tra hoặc xây dựng dashboard, nên hiển thị cả thông tin của parent StepExecution và child JobExecution.

Các thông tin hữu ích gồm:

| Thông tin | Ý nghĩa |
|---|---|
| Parent JobExecution ID | Lần chạy Job điều phối |
| Parent JobStep StepExecution ID | Lần thực thi wrapper Step |
| Child JobInstance ID | Công việc logic của Job con |
| Child JobExecution ID | Lần thực thi cụ thể của Job con |
| Child BatchStatus | Trạng thái vòng đời Job con |
| Child ExitStatus | Kết quả thoát của Job con |

Có thể dùng `JobExplorer` để tra cứu metadata của Job con theo ID nếu ứng dụng lưu hoặc có thể truy xuất ID tương ứng. Khi thiết kế logging, nên ghi tên Job con, JobInstance ID và JobExecution ID để người vận hành có thể lần theo cả hai cấp.

Không nên chỉ nhìn trạng thái của parent JobStep mà bỏ qua child JobExecution. Nếu Job con thất bại, child execution cung cấp chi tiết về Step nào trong quy trình con gặp lỗi.

## 9. JobStep có chạy đồng bộ hay bất đồng bộ?

JobStep sử dụng `JobLauncher` để khởi chạy Job con. Hành vi chờ đợi phụ thuộc vào cấu hình của launcher. Với launcher đồng bộ, lời gọi thường chỉ trả về sau khi Job con kết thúc; JobStep có thể dựa trên trạng thái cuối cùng để xác định kết quả Step cha.

Nếu dùng launcher bất đồng bộ, `run()` có thể trả về khi Job con vẫn đang chạy. Khi đó cần xem xét cẩn thận cách JobStep xác định kết quả và cách parent flow chờ/quan sát child execution. Không nên giả định parent Step tự động chờ child Job hoàn tất chỉ vì JobLauncher trả về một `JobExecution`.

Với cấu trúc JobStep tuần tự thông thường, launcher đồng bộ là lựa chọn dễ hiểu và phổ biến hơn. Nếu mục tiêu là khởi chạy Job con nền rồi để Job cha tiếp tục ngay, cần thiết kế một cơ chế điều phối bất đồng bộ riêng, lưu child execution ID và xác định cách parent chờ hoặc nhận kết quả. Nếu không, Job cha có thể chuyển tiếp khi child Job chưa hoàn tất.

## 10. JobStep khác gì với Flow và Step thông thường?

Các cơ chế dưới đây đều giúp tổ chức Job, nhưng ranh giới thực thi khác nhau:

| Cơ chế | Đơn vị được gọi | Metadata thực thi |
|---|---|---|
| Step thông thường | Tasklet hoặc chunk processing | StepExecution thuộc JobExecution hiện tại |
| Flow trong Job | Một chuỗi/nhánh Step trong cùng Job flow | Các StepExecution thuộc JobExecution của Job đó |
| `JobStep` | Một Job khác được khởi chạy bằng JobLauncher | Child JobInstance và JobExecution riêng; parent có StepExecution wrapper |
| Partitioning | Nhiều phần xử lý của một Step | StepExecution riêng cho từng partition, gắn với JobExecution của Job hiện tại |

Dùng Flow khi chỉ muốn nhóm và tái sử dụng một đoạn điều phối Step trong cùng Job. Dùng JobStep khi cần gọi một Job độc lập có JobParameters, JobInstance, JobExecution và lifecycle riêng.

Dùng partitioning khi cần chia một tập dữ liệu thành nhiều phần để xử lý song song hoặc phân tán. Partitioning không có nghĩa là gọi một Job độc lập cho từng phần.

## 11. JobStep khác gì với gọi JobLauncher thủ công trong Tasklet?

Về kỹ thuật, một Tasklet có thể inject `JobLauncher` rồi gọi Job khác. Tuy nhiên, nếu mục tiêu là mô hình hóa Job con như một Step trong Job cha, `JobStep` diễn đạt rõ quan hệ này và tích hợp với flow builder của Spring Batch.

Với JobStep, cấu hình khai báo tường minh Job con, launcher và parameters extractor. Framework quản lý vòng đời của Step wrapper và thực hiện việc khởi chạy Job con theo cơ chế JobStep.

Nếu tự gọi `JobLauncher` trong Tasklet, ứng dụng phải tự xử lý nhiều chi tiết hơn như trích xuất tham số, phân loại exception, ghi nhận child execution, đồng bộ trạng thái và restart. Việc gọi thủ công có thể phù hợp với một tích hợp đặc thù, nhưng không nên dùng chỉ để thay thế JobStep trong một flow lồng Job thông thường.

## 12. Tách Job con để tái sử dụng và quản lý độc lập

Một lợi ích của JobStep là Job con có thể được dùng từ nhiều Job cha hoặc được khởi chạy độc lập bởi scheduler/API khác. Ví dụ, `importTransactionsJob` có thể được gọi từ Job quyết toán cuối ngày, nhưng cũng có thể được chạy độc lập để nhập lại dữ liệu của một nguồn cụ thể.

Để tái sử dụng an toàn:

- Đặt tên Job con ổn định và mô tả đúng trách nhiệm của nó.
- Định nghĩa JobParameters rõ ràng, gồm identifying parameters thể hiện công việc nghiệp vụ.
- Không phụ thuộc vào mutable field của Job cha hoặc singleton bean để lấy dữ liệu.
- Truyền dữ liệu qua JobParameters hoặc lưu ở repository/dịch vụ dùng chung.
- Thiết kế Job con có thể restart độc lập và có quy tắc idempotency cho side effect.
- Tránh để Job con phụ thuộc vào thứ tự chạy hoặc trạng thái chỉ tồn tại trong bộ nhớ của Job cha.

Một Job con được tái sử dụng tốt nên có hợp đồng đầu vào/đầu ra rõ ràng. Parent Job chỉ cần biết tham số cần truyền và ý nghĩa kết quả của child Job, không cần biết mọi chi tiết triển khai bên trong.

## 13. Lỗi thường gặp khi dùng JobStep

### Không truyền đủ JobParameters

Job con cần `businessDate` nhưng extractor không chuyển tiếp key này. Job con có thể thất bại khi validate tham số hoặc xử lý nhầm dữ liệu mặc định. Hãy khai báo rõ các key cần thiết và kiểm tra bộ tham số thực tế được tạo.

### Child JobInstance bị trùng ngoài ý muốn

Hai Job cha khác nhau gọi cùng Job con với cùng identifying parameters. Nếu Job con đã hoàn tất, lần gọi tiếp theo có thể bị từ chối. Hãy thiết kế identifying parameters theo business key và quyết định rõ có cần chia sẻ cùng một JobInstance hay không.

### Dùng parent execution ID làm tham số nhận diện child

Parent JobExecution ID thay đổi khi restart. Nếu truyền nó làm identifying parameter, child JobInstance có thể thay đổi giữa các lần restart và tạo công việc mới ngoài ý muốn. Dùng business key ổn định.

### Giả định JobStep và Job con dùng cùng một StepExecution

Job con có JobExecution và StepExecution riêng. Khi debug, cần truy vấn đúng metadata ở cấp cha hoặc con.

### Dùng asynchronous launcher mà không có cơ chế chờ

JobStep có thể nhận lại JobExecution khi child vẫn chạy nếu launcher bất đồng bộ. Parent flow cần cơ chế chờ hoặc điều phối kết quả rõ ràng.

### Cấu hình Job con như Step thường

Job con không tự động trở thành một phần của Job cha chỉ vì có bean Job. Cần tạo JobStep và đăng ký JobStep đó trong flow của Job cha.

### Bỏ qua lỗi child Job

Nếu Job con thất bại, cần để kết quả đó phản ánh vào JobStep và Job cha theo chính sách flow. Không bắt exception rồi tiếp tục như thể quy trình con đã thành công.

## 14. Kiểm thử JobStep

Khi kiểm thử JobStep, cần xác nhận cả hành vi của parent và child:

- Parent Job khởi chạy đúng Job con.
- JobParametersExtractor truyền đủ key và đánh dấu identifying đúng.
- Child Job tạo JobInstance và JobExecution với tham số mong muốn.
- Khi child Job thành công, JobStep và parent flow đi tiếp đúng nhánh.
- Khi child Job thất bại, parent Step/Job phản ánh kết quả phù hợp.
- Khi parent Job restart sau child failure, child JobInstance được restart với identifying parameters ổn định.
- Khi child Job đã hoàn tất, lần gọi lặp xử lý đúng quy tắc duplicate/already-complete.
- Hai parent Job không vô tình xung đột cùng một child JobInstance nếu nghiệp vụ yêu cầu các lần chạy độc lập.

Ví dụ integration test có thể chạy parent Job với tham số `businessDate`, sau đó dùng `JobExplorer` kiểm tra metadata của child Job. Cần kiểm tra cả ID JobInstance và JobExecution của child để xác nhận quan hệ lồng Job được tạo đúng.

## 15. Những nhầm lẫn thường gặp

**Coi JobStep như một Step chứa nhiều Step con trong cùng JobExecution.** JobStep khởi chạy một Job độc lập, có JobInstance và JobExecution riêng.

**Cho rằng JobParameters tự động được truyền nguyên vẹn.** Hãy cấu hình `JobParametersExtractor` để xác định tham số của Job con.

**Cho rằng JobInstance của child giống JobInstance của parent.** Hai Job có identity riêng; child identity dựa trên tên child Job và identifying parameters được truyền.

**Dùng JobExecution ID làm business key cho child.** Execution ID thay đổi qua restart. Dùng business key ổn định nếu muốn tiếp tục cùng công việc logic.

**Dùng JobStep chỉ để nhóm Step trong cùng Job.** Nếu không cần JobExecution riêng, Flow hoặc cấu trúc Job flow thông thường có thể đơn giản hơn.

**Không theo dõi child JobExecution.** Parent StepExecution chỉ là wrapper; metadata của child mới cho biết chi tiết các Step bên trong Job con.

## 16. Cách thiết kế quy trình độc lập bằng JobStep

Hãy tách một quy trình thành Job con khi nó có trách nhiệm rõ ràng, đầu vào/đầu ra xác định và có thể được tái sử dụng hoặc vận hành độc lập. Trong Job cha, tạo JobStep trỏ đến Job con, cung cấp JobLauncher và một JobParametersExtractor rõ ràng. Chọn identifying parameters dựa trên business key ổn định để child JobInstance không bị tạo trùng hoặc thay đổi ngoài ý muốn khi restart.

Theo dõi cả parent StepExecution lẫn child JobExecution, và kiểm tra trạng thái Job con khi điều tra lỗi. Dùng JobStep khi cần ranh giới Job độc lập; dùng Flow khi chỉ cần tổ chức các Step trong cùng Job, và dùng partitioning khi cần chia nhỏ công việc của một Step. Cách phân chia này giúp quy trình lớn có thể được lắp ghép từ các Job nhỏ, tái sử dụng và quản lý vòng đời riêng một cách rõ ràng.

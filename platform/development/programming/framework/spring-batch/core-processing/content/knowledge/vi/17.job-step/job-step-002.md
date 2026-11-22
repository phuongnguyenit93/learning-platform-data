# Parent job và child job

Trong Spring Batch, một Job có thể điều phối một Job khác thông qua `JobStep`. Job đóng vai trò điều phối được gọi là **parent job**; Job được khởi chạy bên trong một Step của parent được gọi là **child job**. Cách tổ chức này cho phép chia một quy trình batch lớn thành các Job nhỏ hơn, có thể tái sử dụng và theo dõi execution riêng.

Ví dụ, một parent job xử lý quy trình chốt ngày có thể lần lượt khởi chạy child job nhập giao dịch, child job đối soát và child job tạo báo cáo. Mỗi child job vẫn là một Job Spring Batch độc lập với tên, JobParameters, JobInstance, JobExecution và các Step riêng.

## 1. Parent job và child job là gì?

Parent job là Job điều phối luồng công việc tổng thể. Một Step đặc biệt trong parent, gọi là `JobStep`, khởi chạy child job bằng `JobLauncher`.

Child job là Job được gọi từ JobStep. Nó có thể được định nghĩa như một Job thông thường và cũng có thể được khởi chạy độc lập từ một scheduler, API hoặc một parent job khác.

Ví dụ quy trình:

```text
monthEndParentJob
        |
        v
  prepareBatchStep
        |
        v
  importTransactionsJobStep
        |       \
        |        +--> importTransactionsJob (child job)
        |                  |
        |                  +--> readTransactionsStep
        |                  +--> validateTransactionsStep
        |                  +--> persistTransactionsStep
        |
        v
  reconcileAccountsJobStep
        |       \
        |        +--> reconcileAccountsJob (child job)
        |                  |
        |                  +--> calculateBalancesStep
        |                  +--> compareLedgerStep
        |
        v
  generateReportStep
        |
        v
       End
```

Parent job không trực tiếp gọi từng method của các Step bên trong child job. Nó khởi chạy child job như một đơn vị công việc thông qua JobStep. Nhờ đó, child job có thể giữ cấu trúc và metadata execution riêng.

## 2. Khi nào nên dùng child job?

Child job hữu ích khi một quy trình có những nhóm công việc tương đối độc lập, có thể tái sử dụng hoặc cần theo dõi riêng.

Các trường hợp thường gặp:

- **Tái sử dụng quy trình:** nhiều parent job cùng cần chạy một quy trình import hoặc đối soát đã được định nghĩa thành child job.
- **Chia quy trình lớn thành module:** mỗi child job đảm nhiệm một miền nghiệp vụ, giúp cấu hình và vận hành dễ quản lý hơn.
- **Theo dõi execution riêng:** child job có JobExecution, StepExecution và lịch sử riêng trong JobRepository.
- **Có thể chạy độc lập:** child job có thể được chạy riêng để kiểm thử, vận hành lại hoặc phục vụ một luồng khác.
- **Tách chính sách xử lý:** child job có thể có chunk size, retry, skip, listener và restart policy riêng.

Không nên tạo child job chỉ để chia một Job thành thật nhiều phần nhỏ nếu các phần đó không cần ranh giới độc lập. Nếu các công việc chỉ là những Step nối tiếp trong cùng một quy trình, một Job với nhiều Step thường đơn giản hơn.

## 3. JobStep kết nối parent và child job như thế nào?

`JobStep` là một loại Step dùng để khởi chạy một Job khác. Khi parent job đi tới JobStep, Spring Batch dùng `JobLauncher` để khởi chạy child job và dùng `JobParametersExtractor` để tạo JobParameters cho child từ execution của parent.

Các thành phần chính:

- **Parent Job:** định nghĩa flow tổng thể.
- **JobStep:** đại diện cho vị trí trong parent flow nơi child job được khởi chạy.
- **Child Job:** Job được thực thi bởi JobStep.
- **JobLauncher:** thực hiện lời gọi khởi chạy child job.
- **JobParametersExtractor:** chuyển hoặc trích xuất tham số từ parent execution để tạo tham số cho child job.
- **JobRepository:** lưu metadata của cả parent và child executions.

Với Spring Batch 5, có thể khai báo JobStep bằng `JobStepBuilder`:

```java
@Bean
Step importTransactionsJobStep(
        JobRepository jobRepository,
        JobLauncher jobLauncher,
        Job importTransactionsJob,
        JobParametersExtractor childJobParametersExtractor) {

    return new JobStepBuilder(new StepBuilder(
            "importTransactionsJobStep", jobRepository))
            .job(importTransactionsJob)
            .launcher(jobLauncher)
            .parametersExtractor(childJobParametersExtractor)
            .build();
}
```

JobStep này được đưa vào parent flow như một Step thông thường. Khi được thực thi, nó khởi chạy `importTransactionsJob` bằng JobLauncher và tham số do extractor tạo ra.

## 4. Cấu hình JobParametersExtractor

Parent và child là hai Job độc lập, do đó cần xác định rõ child nhận những tham số nào. `JobParametersExtractor` chịu trách nhiệm tạo bộ `JobParameters` cho child từ `StepExecution` của JobStep.

Có thể dùng `DefaultJobParametersExtractor` khi việc chuyển các key có sẵn đáp ứng yêu cầu:

```java
@Bean
JobParametersExtractor childJobParametersExtractor() {
    DefaultJobParametersExtractor extractor =
            new DefaultJobParametersExtractor();

    extractor.setKeys(new String[] {
            "businessDate",
            "batchId",
            "sourceSystem"
    });

    return extractor;
}
```

Danh sách key thể hiện các giá trị cần chuyển cho child. Các giá trị có thể được lấy từ dữ liệu execution mà extractor hỗ trợ, chẳng hạn JobParameters của parent hoặc ExecutionContext của StepExecution theo hợp đồng của implementation. Nếu cần ánh xạ phức tạp, đổi tên key, tạo tham số bổ sung hoặc kiểm soát cờ identifying chính xác, có thể triển khai `JobParametersExtractor` tùy chỉnh.

Không nên mặc định rằng mọi JobParameters của parent đều phải được truyền xuống child. Child chỉ nên nhận các tham số thực sự cần thiết cho công việc của nó. Việc truyền rõ ràng giúp tránh phụ thuộc ngầm và giảm nguy cơ hai parent tạo cùng một child JobInstance ngoài ý muốn.

### Truyền dữ liệu được tạo trong Step của parent

Nếu parent tạo `batchId` trong một Step trước JobStep, có thể lưu giá trị đó vào StepExecutionContext hoặc JobExecutionContext, rồi cấu hình extractor lấy key tương ứng để tạo JobParameters cho child.

Ví dụ luồng dữ liệu:

```text
Parent prepareBatchStep
        |
        +--> tạo batchId = BATCH-20261115-01
        |
        v
Parent JobExecutionContext
        |
        v
JobParametersExtractor
        |
        v
Child JobParameters
  batchId=BATCH-20261115-01
  businessDate=2026-11-15
```

Với dữ liệu lớn, chỉ truyền định danh như `batchId`, đường dẫn file hoặc snapshot ID. Dữ liệu thực tế nên được lưu trong database, file hoặc object storage; không đưa cả danh sách bản ghi vào JobParameters.

## 5. Định nghĩa child job như một Job độc lập

Child job được khai báo như Job thông thường, có thể chứa một hoặc nhiều Step:

```java
@Bean
Job importTransactionsJob(
        JobRepository jobRepository,
        Step readTransactionsStep,
        Step validateTransactionsStep,
        Step persistTransactionsStep) {

    return new JobBuilder("importTransactionsJob", jobRepository)
            .start(readTransactionsStep)
            .next(validateTransactionsStep)
            .next(persistTransactionsStep)
            .build();
}
```

Child job có thể dùng chunk-oriented Step, Tasklet Step, listener, retry/skip và ExecutionContext giống bất kỳ Job nào khác. Việc nó được gọi từ parent không làm thay đổi cách định nghĩa nội bộ.

Parent job có thể khai báo chuỗi Step, trong đó JobStep đóng vai trò một mắt xích:

```java
@Bean
Job monthEndParentJob(
        JobRepository jobRepository,
        Step prepareBatchStep,
        Step importTransactionsJobStep,
        Step reconcileAccountsJobStep,
        Step generateReportStep) {

    return new JobBuilder("monthEndParentJob", jobRepository)
            .start(prepareBatchStep)
            .next(importTransactionsJobStep)
            .next(reconcileAccountsJobStep)
            .next(generateReportStep)
            .build();
}
```

Trong flow này, parent chạy `prepareBatchStep`, sau đó khởi chạy child import, rồi child reconcile, cuối cùng mới tạo báo cáo nếu các Step trước hoàn tất theo flow bình thường.

## 6. Parent và child có JobInstance, JobExecution riêng

Parent job và child job không dùng chung một JobInstance. Mỗi Job có tên riêng và JobInstance được xác định bằng tên Job cùng identifying JobParameters của chính Job đó.

Ví dụ:

```text
Parent:
  monthEndParentJob
  businessDate=2026-11-15
      -> Parent JobInstance P1
      -> Parent JobExecution P-E1

Child:
  importTransactionsJob
  businessDate=2026-11-15
  batchId=BATCH-20261115-01
      -> Child JobInstance C1
      -> Child JobExecution C-E1
```

JobStep trong parent có StepExecution riêng để ghi nhận lần gọi child. Child có JobExecution và các StepExecution của riêng nó. JobRepository lưu các metadata này riêng biệt nhưng có thể truy vấn để liên hệ quá trình điều phối.

Hệ quả quan trọng: nếu hai parent job khác nhau khởi chạy cùng một child job với cùng identifying parameters, chúng có thể cùng nhắm tới một child JobInstance. Nếu child đang chạy, lần launch sau có thể bị từ chối vì execution đã chạy. Nếu child đã hoàn tất, lần launch với cùng identifying parameters có thể bị từ chối vì instance đã complete. Vì vậy, phải thiết kế child identity theo đúng đơn vị công việc cần thực hiện.

Nếu mỗi parent batch cần một child execution độc lập, hãy đưa một định danh batch nghiệp vụ ổn định vào identifying parameters của child. Định danh đó phải giữ nguyên qua restart của cùng parent; không tạo UUID mới mỗi lần retry.

## 7. Parent JobParameters và Child JobParameters

JobParameters của parent không tự động trở thành toàn bộ JobParameters của child theo một quy tắc nghiệp vụ chung. JobStep dùng extractor để tạo tham số child. Cần quyết định:

- Tham số nào được kế thừa từ parent?
- Tham số nào được lấy từ JobExecutionContext hoặc StepExecutionContext?
- Giá trị nào là identifying đối với child?
- Child có cần tham số riêng không có ở parent không?
- Những giá trị nào phải bất biến qua restart?

Ví dụ parent có `requestedBy`, `businessDate` và `batchId`. Child import có thể chỉ cần `businessDate`, `batchId` và `sourceSystem`. `requestedBy` có thể không cần nếu child không ghi nhận người yêu cầu.

Identifying flag được đánh giá theo định nghĩa của child job. Một tham số identifying ở parent không nhất thiết phải có cùng vai trò ở child nếu extractor tùy chỉnh tạo JobParameters mới. Hãy xác định rõ định danh child để tránh vô tình gom các lần chạy khác nhau vào cùng instance hoặc tạo instance mới khi restart.

## 8. ExecutionContext giữa parent và child không tự động chia sẻ

Parent và child có JobExecution riêng, vì vậy JobExecutionContext của parent không phải một map dùng chung tự động với child. Việc child nhận dữ liệu cần thông qua cơ chế có chủ đích:

1. Parent lưu giá trị cần chia sẻ vào JobParameters hoặc ExecutionContext.
2. JobParametersExtractor lấy các key được chọn từ execution của parent.
3. Extractor tạo JobParameters cho child.
4. Child đọc các tham số qua `JobParameters` hoặc `@StepScope`.
5. Nếu child tạo kết quả cho parent dùng sau đó, child lưu kết quả vào database hoặc một kho dữ liệu bền vững với khóa tham chiếu chung.

Ví dụ child tạo báo cáo và lưu `reportLocation` vào bảng kết quả theo `batchId`. Sau khi JobStep hoàn tất, Step tiếp theo của parent truy vấn bảng đó bằng `batchId`. Cách này rõ ràng hơn việc cố chia sẻ trực tiếp object hoặc context nội bộ giữa hai JobExecution.

## 9. Child job thành công, thất bại và trạng thái của parent

JobStep quan sát kết quả thực thi child job và phản ánh kết quả đó vào StepExecution của parent. Nếu child hoàn tất thành công, JobStep có thể hoàn tất và parent flow chuyển tới Step tiếp theo. Nếu child thất bại, JobStep thường thất bại theo và parent job dừng ở vị trí đó, trừ khi parent flow có transition xử lý kết quả tương ứng.

```text
Parent Job
    |
    v
Child JobStep
    |
    +---- Child COMPLETED ---> Parent JobStep COMPLETED
    |                                  |
    |                                  v
    |                            Parent Step tiếp theo
    |
    +---- Child FAILED -------> Parent JobStep FAILED
                                       |
                                       v
                                Parent Job FAILED
```

Có thể khai báo flow có điều kiện dựa trên ExitStatus của JobStep, giống các Step khác. Ví dụ, child import thất bại có thể chuyển tới Step ghi nhận lô bị lỗi hoặc thực hiện thao tác bù trừ. Cần phân biệt `BatchStatus` và `ExitStatus`: BatchStatus mô tả trạng thái thực thi; ExitStatus là mã kết quả được dùng trong flow transition.

## 10. Restart parent job và child job

Parent và child có lịch sử execution riêng. Khi parent thất bại tại JobStep, cần xem cả trạng thái parent StepExecution lẫn child JobExecution để xác định cách restart an toàn.

### Child thất bại

Nếu child job thất bại, có thể khắc phục nguyên nhân rồi restart parent job với cùng identifying JobParameters. Khi parent tiếp tục tới JobStep, child có thể được khởi chạy lại với cùng identifying parameters để restart child JobInstance, nếu child cho phép restart và metadata cần thiết còn nguyên.

### Child đã hoàn tất

Một tình huống cần chú ý là child đã hoàn tất nhưng parent bị dừng hoặc gặp sự cố trước khi JobStep của parent được ghi nhận hoàn tất. Khi parent restart, JobStep có thể thử khởi chạy child với cùng identifying parameters. Child JobInstance đã `COMPLETED` không thể restart như một instance thất bại; việc launch lại có thể bị từ chối vì instance đã hoàn tất.

Do đó, cần thiết kế và kiểm thử tình huống gián đoạn giữa thời điểm child hoàn tất và thời điểm parent JobStep hoàn tất. Có thể cần cơ chế đối chiếu child JobExecution hiện có để xác nhận child đã thành công và cho parent tiếp tục, hoặc một orchestration/recovery strategy phù hợp. Không nên giải quyết bằng cách tự động thêm timestamp mới vào identifying parameters, vì điều đó có thể tạo child JobInstance mới và thực hiện lại toàn bộ tác vụ.

### Child đã commit một phần rồi thất bại

Nếu child dùng chunk processing, các chunk đã commit được giữ lại. Khi restart child cùng JobInstance, reader có hỗ trợ checkpoint có thể tiếp tục từ trạng thái đã lưu. Các tác dụng phụ ngoài transaction cần idempotency vì chúng có thể đã xảy ra trước khi lỗi được ghi nhận.

### Những Step đã hoàn tất trong parent

Khi restart parent cùng JobInstance, các Step đã `COMPLETED` thường được bỏ qua. JobStep đã hoàn tất sẽ không chạy lại trừ khi được cấu hình `allowStartIfComplete(true)`. Chỉ bật tùy chọn đó khi việc gọi child lặp lại là an toàn và có chủ đích.

## 11. Idempotency và tác dụng phụ của child job

Child job thường xử lý dữ liệu nghiệp vụ lớn hoặc gọi hệ thống bên ngoài. Parent restart hoặc child retry có thể làm một phần công việc được thực hiện lại. Vì vậy, child cần thiết kế idempotent theo định danh nghiệp vụ.

Một số biện pháp:

- Dùng `batchId`, `sourceFileId` hoặc business key ổn định để nhận diện cùng một công việc.
- Dùng unique constraint hoặc upsert để tránh ghi bản ghi trùng.
- Dùng idempotency key khi gọi API tạo giao dịch hoặc gửi yêu cầu sang hệ thống đối tác.
- Lưu trạng thái và mã xác nhận của hệ thống đích để đối soát khi response bị mất.
- Ghi sự kiện cần phát vào transactional outbox rồi xử lý gửi bằng publisher có thể retry an toàn.
- Tách thao tác chuẩn bị, thực hiện và xác nhận thành các Step có đầu ra bền vững.

Không nên giả định parent job và child job cùng nằm trong một transaction. Transaction của parent JobStep và transaction của các chunk bên trong child không tạo thành một transaction phân tán bao trùm toàn bộ hai Job. Dữ liệu đã commit trong child vẫn có thể tồn tại nếu parent thất bại sau đó.

## 12. Child job chạy đồng bộ hay bất đồng bộ?

JobStep sử dụng JobLauncher để khởi chạy child job. Cách JobLauncher thực thi phụ thuộc cấu hình launcher và executor. Với launcher đồng bộ, lời gọi thường chờ child kết thúc trước khi JobStep hoàn tất. Nếu dùng launcher bất đồng bộ, cần hiểu rõ trạng thái trả về và cách parent theo dõi child đang chạy.

Nếu yêu cầu nghiệp vụ là parent phải đợi child hoàn tất rồi mới chạy Step tiếp theo, cần bảo đảm cơ chế launch và orchestration thực sự cung cấp hành vi chờ đó. Không nên chỉ cấu hình executor bất đồng bộ rồi giả định parent tự động đồng bộ kết quả.

Nếu mục tiêu là khởi chạy nhiều Job độc lập song song và tổng hợp kết quả sau, có thể cần một mô hình điều phối khác với JobStep tuần tự, ví dụ partitioning, remote orchestration hoặc một Job quản lý trạng thái các execution con. Hãy chọn cách triển khai dựa trên yêu cầu về đồng bộ, giới hạn concurrency và khả năng phục hồi.

## 13. Theo dõi parent và child trong JobRepository

JobRepository lưu metadata riêng cho từng JobInstance, JobExecution và StepExecution. Khi điều tra một quy trình parent-child, nên theo dõi:

- Parent JobInstance ID và Parent JobExecution ID.
- Tên JobStep và StepExecution ID trong parent.
- Tên child job, Child JobInstance ID và Child JobExecution ID.
- Child JobParameters, đặc biệt là identifying parameters.
- Trạng thái từng Step bên trong child.
- Thời điểm bắt đầu, kết thúc, exception và ExitStatus.
- Mã nghiệp vụ chung như `batchId` để liên kết log và dữ liệu giữa hai Job.

Có thể dùng `JobExplorer` để đọc thông tin JobExecution và StepExecution phục vụ màn hình giám sát. Log nên ghi parent execution ID, child execution ID và business key để có thể truy vết toàn bộ quy trình.

Không nên sửa trực tiếp các bảng metadata `BATCH_*` để ép child hoặc parent chuyển trạng thái. Metadata chứa lịch sử và checkpoint mà framework cần để restart. Hãy dùng API và quy trình vận hành phù hợp.

## 14. Khi nào dùng JobStep, khi nào dùng nhiều Step trong một Job?

| Nhu cầu | Cách tổ chức phù hợp |
|---|---|
| Các phần là những bước liên tiếp của cùng một quy trình, không cần Job identity riêng | Nhiều Step trong cùng Job |
| Một quy trình con được tái sử dụng bởi nhiều parent | Child job qua JobStep |
| Muốn child có JobInstance, JobExecution và lịch sử riêng | Child job qua JobStep |
| Chỉ cần rẽ nhánh theo kết quả của Step | Flow transition trong cùng Job |
| Cần chia dữ liệu lớn thành nhiều phần xử lý song song | Partitioning hoặc mô hình parallel processing phù hợp |
| Cần điều phối nhiều Job độc lập và theo dõi trạng thái bất đồng bộ | Orchestration có quản lý trạng thái riêng |

JobStep tạo thêm một lớp metadata và yêu cầu thiết kế JobParametersExtractor. Nếu không cần identity hoặc lifecycle riêng cho quy trình con, thêm một Step trong cùng Job thường dễ hiểu và vận hành hơn.

## 15. Các lỗi thường gặp khi thiết kế parent-child job

**Cho rằng child job chỉ là một Step khác:** child có JobInstance, JobExecution và các StepExecution riêng. JobStep là Step của parent dùng để khởi chạy Job độc lập.

**Không cấu hình JobParametersExtractor:** child có thể thiếu tham số bắt buộc hoặc nhận tham số không đúng phạm vi nghiệp vụ.

**Truyền toàn bộ tham số parent xuống child:** tạo phụ thuộc ngầm và có thể làm định danh child không đúng. Chỉ truyền key child thực sự cần.

**Không thiết kế identifying parameters cho child:** nhiều parent có thể vô tình nhắm cùng child JobInstance, hoặc một lần chạy nghiệp vụ mới bị coi là instance cũ đã hoàn tất.

**Tạo timestamp mới mỗi lần restart:** child trở thành JobInstance mới và có thể xử lý lại từ đầu thay vì restart instance cũ.

**Cho rằng ExecutionContext của parent tự chia sẻ với child:** hai JobExecution có context riêng. Hãy truyền qua JobParameters hoặc kho dữ liệu bền vững.

**Cho rằng toàn bộ parent-child nằm trong một transaction:** transaction của các Step/chunk riêng biệt; dữ liệu đã commit trong child không tự rollback khi parent thất bại.

**Bỏ qua trường hợp child complete nhưng parent chưa ghi nhận Step complete:** cần kiểm thử recovery ở ranh giới này và có cách đối chiếu execution.

**Dùng JobStep cho mọi nhóm công việc nhỏ:** nếu chỉ cần chuỗi Step đơn giản, một Job nhiều Step có thể ít phức tạp hơn.

## Kết luận

Parent job điều phối quy trình tổng thể; child job là một Job độc lập được khởi chạy từ `JobStep`. JobStep dùng `JobLauncher` và `JobParametersExtractor` để chuyển các tham số cần thiết sang child. Parent và child có JobInstance, JobExecution, StepExecution và ExecutionContext riêng; dữ liệu chỉ được chia sẻ qua parameters hoặc kho dữ liệu được thiết kế rõ ràng. Khi restart, cần giữ identifying parameters ổn định, kiểm tra trạng thái child và thiết kế idempotency cho tác dụng phụ. Dùng child job khi cần tái sử dụng, lifecycle hoặc lịch sử execution độc lập; nếu chỉ cần các bước liên tiếp trong một quy trình, nhiều Step trong cùng Job thường là lựa chọn đơn giản hơn.

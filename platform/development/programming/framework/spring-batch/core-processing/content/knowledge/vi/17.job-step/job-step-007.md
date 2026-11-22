# Phân biệt JobStep với flow lồng nhau

Trong Spring Batch, `JobStep` và flow lồng nhau đều giúp tổ chức một Job lớn thành những phần công việc có thể quản lý riêng. Tuy nhiên, hai cách này có ranh giới thực thi khác nhau.

- **`JobStep`** gọi một Job khác thông qua `JobLauncher`. Job được gọi có `JobInstance` và `JobExecution` riêng, với JobParameters được trích xuất từ execution của Job cha.
- **Flow lồng nhau (subflow)** là một `Flow` gồm nhiều Step được nhúng vào flow của Job cha. Các Step trong subflow vẫn thuộc cùng JobExecution của Job cha; không có một Job con độc lập được khởi chạy.

Vì vậy, hãy dùng `JobStep` khi phần công việc cần có vòng đời Job riêng, có thể chạy độc lập, nhận bộ tham số riêng hoặc được theo dõi/restart như một Job khác. Dùng subflow khi muốn nhóm và tái sử dụng một chuỗi Step trong cùng một Job, với cùng ngữ cảnh JobExecution và một flow điều khiển thống nhất.

## 1. Hai cách tổ chức Job lớn

Giả sử một quy trình xử lý đơn hàng có các giai đoạn chuẩn bị dữ liệu, kiểm tra, làm giàu, nạp vào database và tạo báo cáo. Có thể chia quy trình thành các phần nhỏ theo hai cách.

### Dùng JobStep

Job cha gọi một Job con tại một Step:

```text
Parent Job
  |
  +--> Prepare Step
  |
  +--> JobStep: launch Child Job
  |       |
  |       +--> Child JobExecution
  |               |
  |               +--> Validate Step
  |               +--> Enrich Step
  |               +--> Load Step
  |
  +--> Report Step
```

Job con có tên Job, JobInstance, JobExecution, JobParameters và các StepExecution riêng. JobStep là Step của Job cha dùng để khởi chạy và nhận kết quả từ Job con.

### Dùng flow lồng nhau

Job cha chứa một subflow như một phần của cùng flow:

```text
Parent JobExecution
  |
  +--> Prepare Step
  |
  +--> Processing Flow
  |       |
  |       +--> Validate Step
  |       +--> Enrich Step
  |       +--> Load Step
  |
  +--> Report Step
```

Subflow chỉ nhóm các Step thành một đơn vị logic. Các Step bên trong chạy trong JobExecution của Job cha. Không có JobLauncher gọi một Job con và không tạo JobInstance con.

## 2. JobStep là gì?

`JobStep` là một triển khai của `Step` dùng để chạy một Job khác. Nó đóng vai trò cầu nối giữa Job cha và Job con:

1. Job cha bắt đầu thực thi Step được cấu hình là JobStep.
2. JobStep lấy JobParameters cho Job con thông qua `JobParametersExtractor`.
3. JobStep gọi Job con qua `JobLauncher`.
4. Job con tạo hoặc tìm JobInstance tương ứng, sau đó tạo JobExecution nếu điều kiện launch cho phép.
5. Job con thực thi các Step của chính nó và cập nhật metadata.
6. JobStep nhận kết quả thực thi của Job con và phản ánh kết quả đó vào StepExecution của Job cha.
7. Flow của Job cha tiếp tục hoặc kết thúc dựa trên kết quả của JobStep.

Job con là một Job thực sự trong Spring Batch, có thể được khởi chạy riêng bởi scheduler hoặc một ứng dụng khác nếu cấu hình cho phép. JobStep chỉ là một cách để Job cha gọi Job con như một phần của quy trình lớn hơn.

## 3. Cấu hình JobStep trong Spring Batch 5

Có thể khai báo JobStep bằng `StepBuilder.job(...)`, sau đó cung cấp `JobLauncher` và `JobParametersExtractor`:

```java
@Bean
Step childJobStep(
        JobRepository jobRepository,
        JobLauncher jobLauncher,
        Job childImportJob,
        JobParametersExtractor childParametersExtractor) {

    return new StepBuilder("childImportJobStep", jobRepository)
            .job(childImportJob)
            .launcher(jobLauncher)
            .parametersExtractor(childParametersExtractor)
            .build();
}
```

Trong ví dụ:

- `childImportJob` là Job được khởi chạy.
- `jobLauncher` thực hiện yêu cầu launch Job con.
- `childParametersExtractor` tạo bộ JobParameters cho lần chạy Job con.
- `childImportJobStep` là Step nằm trong flow của Job cha.

JobStep không tự động biến mọi tham số của Job cha thành tham số con theo một quy tắc nghiệp vụ phù hợp. Hãy cấu hình extractor để truyền đúng những giá trị Job con cần.

### Trích xuất JobParameters cho Job con

`JobParametersExtractor` nhận `Job` và `StepExecution` của JobStep để tạo bộ tham số cho Job con. Có thể dùng `DefaultJobParametersExtractor` hoặc triển khai extractor tùy chỉnh.

Ví dụ extractor tùy chỉnh sao chép một số tham số từ Job cha:

```java
@Bean
JobParametersExtractor childParametersExtractor() {
    return (childJob, stepExecution) -> {
        JobParameters parentParameters = stepExecution
                .getJobExecution()
                .getJobParameters();

        return new JobParametersBuilder()
                .addString(
                        "businessDate",
                        parentParameters.getString("businessDate"),
                        true)
                .addString(
                        "inputFile",
                        parentParameters.getString("inputFile"),
                        true)
                .addString(
                        "requestedBy",
                        parentParameters.getString("requestedBy"),
                        false)
                .toJobParameters();
    };
}
```

Ví dụ giả định Job cha đã validation để bảo đảm các tham số bắt buộc có giá trị. Tham số identifying của Job con phải phản ánh định danh nghiệp vụ của phần công việc con. Nếu Job con xử lý cùng một tập dữ liệu, việc giữ cùng identifying parameters có thể giúp nhận diện cùng JobInstance; nếu là một đợt con khác, cần một business key riêng.

Không nên thêm timestamp hoặc UUID ngẫu nhiên vào identifying parameters chỉ để né lỗi `JobInstanceAlreadyCompleteException`. Việc đó có thể biến một lần restart thành một JobInstance mới và làm dữ liệu bị xử lý lại từ đầu.

### Dùng DefaultJobParametersExtractor

Nếu cần truyền các tham số có sẵn theo tên, có thể cấu hình extractor mặc định:

```java
@Bean
JobParametersExtractor childParametersExtractor() {
    DefaultJobParametersExtractor extractor =
            new DefaultJobParametersExtractor();

    extractor.setKeys(new String[] {
            "businessDate",
            "inputFile"
    });

    return extractor;
}
```

Các key được chọn cần tồn tại ở phạm vi mà extractor đọc theo cấu hình của phiên bản Spring Batch đang dùng. Nếu cần mapping phức tạp, đổi identifying flag hoặc kết hợp dữ liệu từ Job/Step ExecutionContext, custom `JobParametersExtractor` thường rõ ràng hơn.

## 4. Job con có metadata riêng

Điểm khác biệt quan trọng của JobStep là Job con có vòng đời metadata độc lập. Khi được launch, Job con có:

- Job name riêng.
- JobInstance riêng, được xác định bằng tên Job con và identifying JobParameters của nó.
- JobExecution riêng cho từng lần chạy hoặc restart.
- StepExecution riêng cho các Step bên trong Job con.
- Job ExecutionContext và Step ExecutionContext của chính nó.

Job cha cũng có metadata của nó. JobStep là một StepExecution trong JobExecution cha; Job con được launch sẽ tạo JobExecution độc lập. Trong một cấu hình thông thường, cả hai có thể dùng chung một `JobRepository` database để quản lý lịch sử, nhưng các execution vẫn là các execution khác nhau.

Sơ đồ khái niệm:

```text
Parent JobInstance
  |
  +-- Parent JobExecution 7001
        |
        +-- StepExecution: prepareStep
        |
        +-- StepExecution: childJobStep
        |       |
        |       +-- Child JobInstance
        |             |
        |             +-- Child JobExecution 8101
        |                    |
        |                    +-- StepExecution: validate
        |                    +-- StepExecution: load
        |
        +-- StepExecution: reportStep
```

Do đó, có thể tra cứu và quan sát Job con như một Job độc lập bằng `JobExplorer`, đồng thời Job cha vẫn ghi nhận JobStep đã chạy và kết quả của nó.

## 5. Flow lồng nhau là gì?

`Flow` là một cấu trúc mô tả trình tự Step, các nhánh rẽ và các điểm kết thúc. Một subflow là Flow được định nghĩa riêng rồi đưa vào flow của Job cha.

Ví dụ, nhóm ba Step kiểm tra, chuẩn hóa và nạp dữ liệu thành một Flow:

```java
@Bean
Flow orderProcessingFlow(
        Step validateOrdersStep,
        Step normalizeOrdersStep,
        Step loadOrdersStep) {

    return new FlowBuilder<SimpleFlow>("orderProcessingFlow")
            .start(validateOrdersStep)
            .next(normalizeOrdersStep)
            .next(loadOrdersStep)
            .build();
}
```

Đưa subflow vào Job cha:

```java
@Bean
Job parentImportJob(
        JobRepository jobRepository,
        Step prepareInputStep,
        Flow orderProcessingFlow,
        Step createReportStep) {

    return new JobBuilder("parentImportJob", jobRepository)
            .start(prepareInputStep)
            .next(orderProcessingFlow)
            .next(createReportStep)
            .end()
            .build();
}
```

Ở đây, `orderProcessingFlow` chỉ là một phần cấu trúc của `parentImportJob`. Các Step bên trong subflow được thực thi như các Step của Job cha. Không có `JobLauncher` được gọi và không tạo JobInstance con.

## 6. Subflow có thể chứa conditional transition

Subflow không chỉ là danh sách Step tuyến tính. Nó có thể chứa nhánh dựa trên `ExitStatus`, giống flow cấp Job:

```java
@Bean
Flow validationFlow(
        Step validateStep,
        Step enrichStep,
        Step useExistingDataStep) {

    return new FlowBuilder<SimpleFlow>("validationFlow")
            .start(validateStep)
                .on("NEEDS_ENRICHMENT").to(enrichStep)
            .from(validateStep)
                .on("ALREADY_ENRICHED").to(useExistingDataStep)
            .end();
}
```

Job cha có thể nối subflow này với các Step khác:

```java
@Bean
Job parentJob(
        JobRepository jobRepository,
        Step prepareStep,
        Flow validationFlow,
        Step reportStep) {

    return new JobBuilder("parentJob", jobRepository)
            .start(prepareStep)
            .next(validationFlow)
            .next(reportStep)
            .end()
            .build();
}
```

Subflow giữ logic điều khiển gần với các Step liên quan. Khi một nhánh được chọn, những Step ở nhánh khác không được thực thi trong lần chạy đó.

## 7. FlowStep: bọc Flow như một Step

Ngoài việc đưa Flow trực tiếp vào Job flow, Spring Batch còn có `FlowStep`, cho phép đóng gói một Flow thành một Step:

```java
@Bean
Step orderProcessingFlowStep(
        JobRepository jobRepository,
        Flow orderProcessingFlow) {

    return new StepBuilder("orderProcessingFlowStep", jobRepository)
            .flow(orderProcessingFlow)
            .build();
}
```

`FlowStep` hữu ích khi muốn sử dụng Flow ở nơi một Step được mong đợi hoặc muốn đóng gói một cụm Step thành một đơn vị trong flow cấp trên. Nó vẫn thực thi Flow trong ngữ cảnh Job cha; nó không khởi chạy một Job khác và không tạo một JobInstance con như JobStep.

Khi dùng FlowStep, cần hiểu rằng Flow được đóng gói như một Step ở cấp cấu trúc. Các Step thực tế bên trong Flow vẫn có execution và metadata theo cơ chế của Spring Batch. Không nên coi FlowStep là một cách tạo ranh giới Job độc lập.

## 8. So sánh JobStep và flow lồng nhau

| Tiêu chí | JobStep | Subflow trong Job cha |
|---|---|---|
| Thành phần được gọi | Một Job khác | Một Flow gồm các Step |
| JobInstance | Có JobInstance con | Không tạo JobInstance mới |
| JobExecution | Có JobExecution con | Dùng JobExecution của Job cha |
| JobParameters | Truyền qua `JobParametersExtractor` | Dùng JobParameters của Job cha |
| StepExecution | JobStep có StepExecution cha; Job con có StepExecution riêng | Các Step trong subflow thuộc JobExecution cha |
| JobRepository | Job con ghi metadata execution riêng; có thể dùng chung repository | Các execution thuộc Job cha |
| Restart | Job con có chính sách restart riêng; Job cha cũng phải xử lý kết quả JobStep | Restart theo JobInstance và flow của Job cha |
| Chạy độc lập | Job con có thể được launch riêng | Subflow không phải Job độc lập; cần một Job chứa nó |
| Tái sử dụng | Tái sử dụng một Job hoàn chỉnh | Tái sử dụng nhóm Step/flow logic |
| Điều khiển flow | Job cha điều khiển trước/sau JobStep; Job con điều khiển flow nội bộ | Một flow liên tục điều khiển các Step trong cùng Job |
| Tham số và context | Cần trích xuất tham số; context của hai Job không tự động là một | Các Step chia sẻ JobExecution context của Job cha theo cơ chế context promotion |
| Phù hợp khi | Có quy trình con độc lập, cần lịch sử và vòng đời riêng | Muốn nhóm các Step trong cùng một quy trình nghiệp vụ |

## 9. Khi nào nên dùng JobStep?

JobStep phù hợp khi phần công việc được xem là một Job độc lập về nghiệp vụ hoặc vận hành.

### Job con cần chạy độc lập

Ví dụ, hệ thống có Job `customerImportJob` và Job `accountReconciliationJob`. Một Job tổng có thể gọi từng Job con qua JobStep, nhưng mỗi Job con cũng có thể được scheduler chạy độc lập khi cần.

### Cần lịch sử và trạng thái execution riêng

Nếu muốn theo dõi Job con với JobInstance/JobExecution riêng, tra cứu riêng qua JobExplorer hoặc áp dụng chính sách restart độc lập, JobStep là lựa chọn phù hợp.

### Cần truyền bộ tham số riêng

Job con có thể cần business key, ngày nghiệp vụ hoặc mã batch khác với Job cha. `JobParametersExtractor` cho phép xác định chính xác dữ liệu đầu vào của Job con.

### Cần tách nhóm triển khai hoặc quyền sở hữu

Một nhóm phát triển có thể quản lý Job con như một quy trình hoàn chỉnh với Step, listener, validator và chính sách restart riêng. Job cha chỉ chịu trách nhiệm điều phối các Job con theo trình tự lớn hơn.

### Muốn lồng một Job có flow phức tạp

Nếu quy trình con đã là một Job có nhiều nhánh, decider, listener hoặc quy tắc restart riêng, gọi nó bằng JobStep có thể giữ được ranh giới và cấu trúc độc lập.

## 10. Khi nào nên dùng flow lồng nhau?

Subflow phù hợp khi chỉ cần nhóm logic Step, không cần một JobExecution mới.

### Các Step là các giai đoạn của cùng một quy trình

Ví dụ, `validateStep`, `normalizeStep` và `loadStep` là các giai đoạn tự nhiên của một lần import. Chúng cùng sử dụng business parameters và trạng thái Job cha.

### Muốn tái sử dụng một cụm Step

Một Flow có thể được dùng trong nhiều Job khác nhau nếu các Step và tham số tương thích. Tái sử dụng Flow không tạo ra Job con và không thêm một lớp JobLauncher.

### Muốn một JobExecution duy nhất

Nếu vận hành muốn một JobExecution thể hiện toàn bộ quy trình, subflow giữ các Step trong cùng execution. Việc theo dõi, restart và flow status được quản lý như một Job thống nhất.

### Không cần Job con chạy độc lập

Nếu không có nhu cầu khởi chạy riêng, không cần JobInstance riêng hoặc bộ JobParameters riêng, subflow thường đơn giản hơn JobStep.

## 11. Parameters và ExecutionContext giữa Job cha và Job con

JobStep tạo ranh giới giữa hai Job. JobParameters của Job con được tạo bởi `JobParametersExtractor`; không nên giả định mọi JobParameters của cha được truyền tự động hoặc context của cha và con là cùng một object.

Nếu Job con cần dữ liệu từ Job cha:

1. Xác định rõ các tham số con cần nhận.
2. Dùng `JobParametersExtractor` để mapping các giá trị đó.
3. Chọn identifying flag theo định danh nghiệp vụ của Job con.
4. Validation tham số ở Job con trước khi thực hiện tác dụng phụ.
5. Dùng repository và API metadata để tra cứu execution con.

Với subflow, các Step dùng JobParameters của Job cha. Nếu một Step tạo dữ liệu trong Step ExecutionContext và Step khác cần sử dụng, có thể dùng `ExecutionContextPromotionListener` để đưa key cần thiết lên Job ExecutionContext.

Không nên dùng Job ExecutionContext của Job cha như một kênh chia sẻ tự động với Job con. Nếu cần truyền dữ liệu lớn, hãy lưu dữ liệu ở database hoặc storage và truyền business key/URI an toàn qua JobParameters.

## 12. Restart và lỗi khi dùng JobStep

JobStep có hai tầng trạng thái:

- JobExecution của Job cha, trong đó có StepExecution đại diện cho JobStep.
- JobInstance/JobExecution của Job con được khởi chạy từ JobStep.

Khi Job con thất bại, JobStep thường phản ánh kết quả thất bại và flow Job cha xử lý theo transition đã cấu hình. Có thể restart Job cha nếu điều kiện cho phép; việc chạy lại JobStep sẽ khởi chạy Job con với tham số được extractor tạo ra.

Vì Job con có định danh riêng, cần hiểu hành vi khi parent Job được restart:

- Nếu Job con đã thất bại và có thể restart, cùng identifying parameters cho phép tiếp tục JobInstance con.
- Nếu Job con đã hoàn tất nhưng parent Job chưa ghi nhận JobStep hoàn tất do một khoảng lỗi hiếm gặp, việc launch lại với cùng identifying parameters có thể gặp trạng thái JobInstance đã hoàn tất. Cần kiểm thử tình huống này và thiết kế quy trình phục hồi phù hợp.
- Nếu extractor tạo identifying parameters mới mỗi lần restart, Job con có thể bị xem là JobInstance mới và chạy lại từ đầu.

Không nên giải quyết vấn đề bằng cách thêm ID ngẫu nhiên cho mỗi lần gọi. Hãy xác định child business key, trạng thái execution con và quan hệ giữa lần chạy cha/con.

## 13. Restart và lỗi khi dùng subflow

Subflow dùng cùng JobInstance và JobExecution với Job cha. Khi Job cha restart:

- Các Step đã hoàn tất thường được bỏ qua theo chính sách restart.
- Step thất bại hoặc chưa hoàn tất được xử lý theo metadata và checkpoint của Job cha.
- Các nhánh subflow được đánh giá theo flow và trạng thái execution.
- Không có Job con riêng để restart độc lập.

Nếu một Step bên trong subflow thất bại, có thể restart Job cha theo điều kiện. Không thể khởi chạy riêng subflow như một Job độc lập; nếu cần chạy độc lập, hãy đóng gói nó thành một Job hoặc tạo JobStep gọi một Job riêng.

## 14. Transaction và ranh giới thực thi

JobStep không tạo một transaction duy nhất bao trùm toàn bộ Job cha và Job con. Các Step bên trong Job con quản lý transaction theo cấu hình của chính chúng. JobStep chỉ điều phối việc launch và nhận kết quả của Job con.

Với subflow, các Step vẫn thuộc Job cha, nhưng mỗi chunk/Tasklet Step có transaction boundary theo cấu hình riêng. Việc dùng cùng JobExecution không có nghĩa toàn bộ subflow chạy trong một transaction lớn.

Trong cả hai cách, không nên giả định một transaction JDBC có thể rollback mọi tác dụng phụ ở hệ thống ngoài. Nếu Job con hoặc Step gửi HTTP, email, message hay thao tác file, cần thiết kế idempotency, outbox hoặc đối soát khi restart.

## 15. Quan sát và vận hành

### Theo dõi JobStep

Khi dùng JobStep, có thể tra cứu:

- Parent JobExecution để biết toàn bộ quy trình lớn.
- Parent StepExecution của JobStep để biết trạng thái bước gọi Job con.
- Child JobExecution để xem trạng thái, exit code, thời gian và các StepExecution bên trong Job con.

Job con có thể có nhiều lần chạy qua restart. Vì vậy, khi hiển thị trên dashboard, nên liên kết parent JobExecution ID với child JobExecution ID bằng thông tin tương quan được lưu/ghi nhận rõ ràng.

### Theo dõi subflow

Với subflow, tra cứu JobExecution của Job cha và các StepExecution bên trong. Không tìm một JobExecution con vì không có Job con được launch.

## 16. Những lỗi thường gặp

### Dùng JobStep chỉ để nhóm vài Step

Nếu các Step chỉ là các giai đoạn của cùng Job, JobStep tạo thêm JobInstance/JobExecution, yêu cầu trích xuất tham số và làm phức tạp restart. Subflow thường phù hợp hơn.

### Dùng subflow khi cần chạy quy trình con độc lập

Subflow không thể được launch độc lập bằng JobLauncher và không có metadata JobInstance riêng. Nếu cần lịch sử, tham số và restart riêng, hãy tạo Job con và gọi bằng JobStep.

### Không cấu hình JobParametersExtractor

Job con có thể thiếu tham số bắt buộc hoặc nhận tham số identifying không đúng. Xác định hợp đồng tham số con và mapping rõ ràng.

### Truyền timestamp ngẫu nhiên vào Job con

Điều này có thể tạo JobInstance con mới mỗi lần parent restart, làm mất khả năng restart đúng instance và gây xử lý trùng. Dùng business key ổn định.

### Nhầm ExecutionContext cha và con

Job con có context riêng. Dùng extractor để truyền tham số hoặc storage chung qua khóa tham chiếu; không giả định context tự chia sẻ.

### Nghĩ JobStep và Job con nằm trong cùng transaction

JobStep gọi JobLauncher; các transaction của Job con được quản lý theo cấu hình của nó. Parent Step không tạo transaction phân tán bao trùm tất cả hoạt động.

### Nghĩ FlowStep là JobStep

FlowStep đóng gói một Flow thành một Step, không khởi chạy Job mới. Muốn JobInstance/JobExecution con, cần JobStep.

## 17. Quy trình chọn giữa JobStep và flow lồng nhau

Khi thiết kế quy trình lớn, hãy đặt các câu hỏi sau:

1. Phần công việc có cần được launch độc lập ngoài Job cha không? Nếu có, ưu tiên Job riêng và JobStep.
2. Có cần JobInstance, JobExecution, JobParameters và restart policy riêng không? Nếu có, dùng JobStep.
3. Phần công việc chỉ là chuỗi hoặc nhánh Step trong cùng quy trình không? Nếu có, dùng subflow.
4. Các Step có cần chia sẻ cùng JobParameters và JobExecutionContext không? Nếu có, subflow thường tự nhiên hơn.
5. Có cần đóng gói một Flow để dùng như một Step không? Cân nhắc FlowStep; nó vẫn không tạo Job con.
6. Nếu dùng JobStep, đã định nghĩa identifying parameters và extractor ổn định chưa?
7. Đã kiểm thử restart cả parent và child, đặc biệt khoảng lỗi giữa child completion và parent metadata update chưa?
8. Đã xác định transaction boundary và tính idempotent của tác dụng phụ chưa?

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Gọi một Job đối soát độc lập từ Job tổng | JobStep |
| Job con có thể chạy riêng bởi scheduler | JobStep |
| Job con cần JobParameters và restart riêng | JobStep |
| Nhóm validate, transform và load trong cùng Job | Subflow |
| Tái sử dụng chuỗi Step trong nhiều Job | Subflow |
| Muốn một JobExecution theo dõi toàn bộ quy trình | Subflow |
| Đóng gói Flow thành một Step ở flow cấp trên | FlowStep |

## Kết luận

`JobStep` khởi chạy một Job khác, tạo ranh giới JobInstance/JobExecution riêng và truyền tham số qua `JobParametersExtractor`. Nó phù hợp khi quy trình con cần chạy độc lập, có metadata, tham số và restart policy riêng. Flow lồng nhau chỉ nhóm các Step trong cùng JobExecution của Job cha; nó phù hợp để tổ chức và tái sử dụng các giai đoạn của một quy trình thống nhất. `FlowStep` có thể bọc một Flow thành một Step nhưng vẫn không tạo Job con. Hãy chọn theo ranh giới nghiệp vụ, nhu cầu vận hành, tham số, restart và transaction thay vì chỉ dựa vào độ dài của flow.

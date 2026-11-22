# Một job có nhiều step phụ thuộc nhau

Một Spring Batch Job có thể gồm nhiều Step thực hiện các phần việc khác nhau của cùng một quy trình. Các Step có thể chạy lần lượt, rẽ nhánh theo kết quả, hoặc chạy song song khi chúng độc lập. Khi Step sau cần kết quả do Step trước tạo ra, Job flow phải thể hiện rõ thứ tự phụ thuộc và cách chuyển dữ liệu giữa chúng.

Ví dụ, một quy trình nhập đơn hàng có thể gồm:

1. Đọc file đầu vào và kiểm tra cấu trúc.
2. Chuẩn hóa dữ liệu đã hợp lệ.
3. Ghi đơn hàng vào database.
4. Tạo báo cáo kết quả.

Step 2 cần dữ liệu do Step 1 tạo ra; Step 3 cần dữ liệu đã chuẩn hóa; Step 4 cần kết quả ghi dữ liệu. Đây là một chuỗi phụ thuộc. Spring Batch cho phép mô hình hóa chuỗi này trong Job flow, quản lý execution của từng Step và lưu metadata để có thể theo dõi hoặc restart khi xảy ra lỗi.

## 1. Job flow và quan hệ phụ thuộc giữa các Step

Một Job định nghĩa quy trình gồm các Step và cách chuyển từ Step này sang Step khác. Quan hệ phụ thuộc được thể hiện trong flow. Thứ tự khai báo bean hoặc thứ tự các phương thức cấu hình không tự tạo ra quan hệ phụ thuộc.

Với một quy trình tuyến tính:

~~~text
Job: importOrders
    |
    v
validateInput
    |
    v
normalizeOrders
    |
    v
writeOrders
    |
    v
createReport
~~~

Mỗi Step chỉ bắt đầu sau khi Step đứng trước kết thúc theo điều kiện chuyển tiếp của flow. Trong trường hợp đơn giản, các Step tiếp tục khi Step trước hoàn thành thành công.

Cần phân biệt hai loại quan hệ:

- **Phụ thuộc về trình tự:** Step B chỉ được chạy sau khi Step A hoàn thành theo một điều kiện xác định.
- **Phụ thuộc về dữ liệu:** Step B cần một kết quả, file, ID hoặc trạng thái do Step A tạo ra.

Một flow có thể xác định đúng thứ tự nhưng vẫn chưa đủ nếu Step sau không biết cách lấy dữ liệu đầu ra của Step trước. Vì vậy, thiết kế nhiều Step cần giải quyết cả luồng điều khiển lẫn luồng dữ liệu.

## 2. Khai báo các Step chạy tuần tự

Với quy trình tuyến tính, có thể dùng start() và next() để khai báo thứ tự thực thi. Ví dụ sau dùng API Java phổ biến của Spring Batch 5:

~~~java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step normalizeOrdersStep,
        Step writeOrdersStep,
        Step createReportStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(validateInputStep)
            .next(normalizeOrdersStep)
            .next(writeOrdersStep)
            .next(createReportStep)
            .build();
}
~~~

start(validateInputStep) xác định Step đầu tiên. Mỗi lời gọi next() thêm Step tiếp theo vào flow. JobRepository lưu metadata về JobExecution và StepExecution khi Job chạy.

Các Step được cấu hình riêng. Chúng có thể là Tasklet Step hoặc chunk-oriented Step tùy loại công việc. Ví dụ, kiểm tra file có thể dùng Tasklet; chuẩn hóa và ghi nhiều bản ghi thường phù hợp với chunk processing.

~~~java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validateInputTasklet) {

    return new StepBuilder("validateInputStep", jobRepository)
            .tasklet(validateInputTasklet, transactionManager)
            .build();
}
~~~

Một Step chunk-oriented có thể được khai báo như sau:

~~~java
@Bean
Step writeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("writeOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Commit interval của Step chunk là 100 item. Ranh giới transaction của từng chunk nằm bên trong Step. Việc Job điều phối nhiều Step không tạo ra một transaction duy nhất bao trùm toàn bộ Job.

Trong flow tuần tự thông thường, nếu Step trước thất bại, các Step tiếp theo sẽ không tự chạy như thể Step trước đã thành công. Job kết thúc theo trạng thái lỗi trừ khi flow có khai báo một transition khác cho kết quả đó.

## 3. Chuyển dữ liệu giữa các Step

Các Step trong cùng một JobExecution có thể cần trao đổi thông tin. Spring Batch cung cấp hai ExecutionContext với phạm vi khác nhau:

- **Step ExecutionContext** thuộc về một StepExecution. Nó thường lưu trạng thái riêng của Step, ví dụ vị trí reader cần khôi phục khi restart.
- **Job ExecutionContext** thuộc về JobExecution. Nó phù hợp để chia sẻ các giá trị nhỏ giữa các Step trong cùng lần chạy Job.

Nếu Step đầu tạo ra đường dẫn file đã kiểm tra, Step sau có thể đọc đường dẫn đó từ Job ExecutionContext.

### Step ghi thông tin dùng chung

Ví dụ một Tasklet lưu đường dẫn file đầu ra vào Job ExecutionContext:

~~~java
@Bean
Tasklet validateInputTasklet() {
    return (contribution, chunkContext) -> {
        JobExecution jobExecution =
                contribution.getStepExecution().getJobExecution();

        // Giả sử file đã được kiểm tra và chuẩn bị thành công.
        String validatedFile = "/data/batch/validated-orders.csv";

        jobExecution.getExecutionContext()
                .putString("validatedOrdersFile", validatedFile);

        return RepeatStatus.FINISHED;
    };
}
~~~

Giá trị validatedOrdersFile được đặt trong Job ExecutionContext để Step sau có thể truy cập. Job ExecutionContext được lưu qua JobRepository trong vòng đời thực thi Step; dữ liệu chia sẻ nên được công bố khi Step tạo ra nó đã hoàn thành thành công.

### Step sau đọc thông tin

Một bean reader có thể dùng @StepScope để nhận giá trị trong Job ExecutionContext khi Step bắt đầu:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> validatedOrdersReader(
        @Value("#{jobExecutionContext['validatedOrdersFile']}")
        String inputFile,
        LineMapper<Order> orderLineMapper) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("validatedOrdersReader")
            .resource(new FileSystemResource(inputFile))
            .lineMapper(orderLineMapper)
            .saveState(true)
            .build();
}
~~~

@StepScope trì hoãn việc tạo reader cho đến khi Step chạy, khi đó giá trị trong execution context đã có thể được phân giải. Reader được đặt tên ổn định và bật saveState(true) để Spring Batch lưu trạng thái cần thiết cho restart.

Trong ứng dụng thực tế, Step tạo file phải bảo đảm file tồn tại và hoàn chỉnh trước khi Step đọc bắt đầu. Nếu file có thể bị thay thế giữa các lần restart, nên lưu thêm thông tin nhận diện phiên bản nguồn, chẳng hạn checksum hoặc mã lô dữ liệu.

### Khi nào dùng Step ExecutionContext và Job ExecutionContext?

| Nhu cầu | Nơi lưu phù hợp |
|---|---|
| Vị trí đọc tiếp theo của một reader | Step ExecutionContext |
| Trạng thái nội bộ cần phục hồi của một Step | Step ExecutionContext |
| Đường dẫn file do Step trước tạo để Step sau dùng | Job ExecutionContext |
| Mã lô hoặc kết quả nhỏ cần chia sẻ giữa các Step | Job ExecutionContext |
| Tập dữ liệu nghiệp vụ lớn | Database, file hoặc kho lưu trữ chuyên dụng |

Không nên đưa danh sách hàng nghìn hoặc hàng triệu item vào ExecutionContext. Context được thiết kế để lưu metadata và trạng thái phục hồi, không phải để thay thế kho dữ liệu nghiệp vụ.

Nếu một Step cần công bố một key từ Step ExecutionContext sang Job ExecutionContext, có thể dùng ExecutionContextPromotionListener. Cách này hữu ích khi component tạo dữ liệu muốn lưu trạng thái trong phạm vi Step trước, sau đó chỉ đưa một số key được chọn lên phạm vi Job khi Step hoàn thành.

Ví dụ cấu hình listener:

~~~java
@Bean
ExecutionContextPromotionListener promoteOutputPath() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();

    listener.setKeys(new String[] { "validatedOrdersFile" });
    return listener;
}
~~~

Đăng ký listener trên Step tạo ra giá trị cần chia sẻ:

~~~java
return new StepBuilder("validateInputStep", jobRepository)
        .tasklet(validateInputTasklet, transactionManager)
        .listener(promoteOutputPath())
        .build();
~~~

Tasklet có thể đặt key vào Step ExecutionContext:

~~~java
contribution.getStepExecution()
        .getExecutionContext()
        .putString("validatedOrdersFile", validatedFile);
~~~

Listener sẽ thực hiện việc promotion theo cấu hình trạng thái của nó. Cần bảo đảm key được ghi đúng tên và Step kết thúc ở trạng thái được phép promotion.

## 4. Phân biệt JobParameters với dữ liệu được tạo trong Job

JobParameters và ExecutionContext đều có thể cung cấp giá trị cho nhiều Step, nhưng mục đích khác nhau.

**JobParameters** là đầu vào của một JobInstance. Chúng thường mô tả kỳ dữ liệu, file nguồn, tenant hoặc chế độ chạy. Các identifying parameters quyết định danh tính JobInstance.

**Job ExecutionContext** lưu dữ liệu phát sinh trong quá trình chạy và được các Step trong cùng JobExecution chia sẻ. Ví dụ, Step đầu tạo ra tên file tạm hoặc mã batch đã xử lý.

Ví dụ:

~~~text
JobParameters:
  businessDate = 2026-11-15
  inputFile = /data/in/orders.csv

Step validateInput:
  đọc inputFile
  kiểm tra dữ liệu
  tạo validatedFile

Job ExecutionContext:
  validatedFile = /data/out/validated-orders.csv

Step writeOrders:
  đọc validatedFile
  ghi dữ liệu vào database
~~~

Không nên thay đổi JobParameters để truyền kết quả runtime từ Step này sang Step khác. Hãy dùng ExecutionContext cho trạng thái runtime và dùng nơi lưu dữ liệu nghiệp vụ phù hợp cho dữ liệu lớn hoặc cần được truy vấn độc lập.

## 5. Điều hướng flow theo kết quả của Step

Không phải quy trình nào cũng có một đường đi tuyến tính. Có trường hợp Step kiểm tra dữ liệu và cần chọn nhánh xử lý tùy kết quả.

Spring Batch hỗ trợ khai báo transition dựa trên ExitStatus của Step. Ví dụ, nếu Step kiểm tra thành công thì tiếp tục nhập dữ liệu; nếu thất bại thì chạy Step ghi nhận lỗi:

~~~java
@Bean
Job importWithValidationJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step writeOrdersStep,
        Step recordValidationFailureStep) {

    return new JobBuilder("importWithValidationJob", jobRepository)
            .start(validateInputStep)
                .on("COMPLETED").to(writeOrdersStep)
            .from(validateInputStep)
                .on("FAILED").to(recordValidationFailureStep)
            .from(writeOrdersStep)
                .on("*").end()
            .from(recordValidationFailureStep)
                .on("*").fail()
            .end()
            .build();
}
~~~

Trong ví dụ:

- on("COMPLETED") khớp với kết quả hoàn thành của Step kiểm tra.
- on("FAILED") khớp với kết quả thất bại và chuyển sang Step ghi nhận lỗi.
- on("*") là mẫu khớp các mã kết quả còn lại của Step tương ứng.
- end() kết thúc Job flow với kết quả hoàn thành theo transition đã khai báo.
- fail() kết thúc flow với kết quả thất bại.

Ví dụ này thể hiện rằng Step ghi nhận lỗi vẫn có thể được thực hiện để lưu thông tin chẩn đoán, trong khi kết quả cuối của Job vẫn là thất bại. Trong flow thực tế, cần khai báo các transition phù hợp với các ExitStatus mà Step có thể trả về.

### BatchStatus và ExitStatus trong điều hướng

BatchStatus mô tả trạng thái vòng đời thực thi, chẳng hạn COMPLETED, FAILED hoặc STOPPED. ExitStatus là mã kết quả được dùng để mô tả kết quả của Step và điều hướng flow.

Một Step có thể kết thúc với BatchStatus COMPLETED nhưng trả về một ExitStatus nghiệp vụ như NO_DATA. Khi đó, flow có thể dùng on("NO_DATA") để chọn nhánh tương ứng.

Ví dụ, một Step kiểm tra file có thể trả về mã NO_DATA nếu file hợp lệ nhưng không có bản ghi:

~~~java
contribution.setExitStatus(new ExitStatus("NO_DATA"));
return RepeatStatus.FINISHED;
~~~

Transition tương ứng có thể được khai báo:

~~~java
return new JobBuilder("importOptionalDataJob", jobRepository)
        .start(checkDataStep)
            .on("NO_DATA").to(createEmptyReportStep)
        .from(checkDataStep)
            .on("COMPLETED").to(importDataStep)
        .from(createEmptyReportStep)
            .on("*").end()
        .from(importDataStep)
            .on("*").end()
        .end()
        .build();
~~~

Cần thiết kế thứ tự và mẫu transition để các kết quả có thể xảy ra đều được xử lý rõ ràng. Không nên dùng một mã COMPLETED chung cho mọi tình huống nghiệp vụ nếu các tình huống đó cần đi theo những nhánh khác nhau.

## 6. Dùng JobExecutionDecider cho quyết định nghiệp vụ

Khi điều kiện rẽ nhánh phức tạp hơn một mã ExitStatus đơn giản, có thể dùng JobExecutionDecider. Decider nhận JobExecution và StepExecution gần nhất, sau đó trả về một FlowExecutionStatus để flow chọn nhánh.

Ví dụ, job có thể chọn quy trình nhập toàn bộ hoặc nhập phần thay đổi dựa trên JobParameter mode:

~~~java
public class ImportModeDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        String mode = jobExecution.getJobParameters().getString("mode");

        if ("FULL".equalsIgnoreCase(mode)) {
            return new FlowExecutionStatus("FULL");
        }

        return new FlowExecutionStatus("DELTA");
    }
}
~~~

Flow sử dụng các trạng thái do Decider trả về:

~~~java
return new JobBuilder("modeBasedImportJob", jobRepository)
        .start(prepareInputStep)
        .next(importModeDecider)
            .on("FULL").to(fullImportStep)
        .from(importModeDecider)
            .on("DELTA").to(deltaImportStep)
        .from(fullImportStep)
            .on("*").end()
        .from(deltaImportStep)
            .on("*").end()
        .end()
        .build();
~~~

Decider chỉ quyết định nhánh tiếp theo. Nó không thay thế công việc xử lý dữ liệu của Step. Giữ phần quyết định tập trung trong Decider giúp flow dễ đọc khi điều kiện nghiệp vụ cần kiểm tra nhiều tham số hoặc metadata.

Nếu quyết định chỉ phụ thuộc vào kết quả trực tiếp của một Step, transition theo ExitStatus thường đơn giản hơn. Nếu quyết định dựa trên nhiều giá trị runtime hoặc cần dùng chung một logic chọn nhánh, Decider phù hợp hơn.

## 7. Step phụ thuộc dữ liệu và Step độc lập

Khi thiết kế flow, cần xác định Step nào thực sự phụ thuộc vào kết quả của Step khác.

Ví dụ:

~~~text
                  +--> generateCustomerReport --+
prepareData ------|                              |----> publishReports
                  +--> generateOrderReport -----+
~~~

Hai Step tạo báo cáo có thể chạy độc lập sau khi prepareData hoàn thành. Step publishReports chỉ bắt đầu khi cả hai nhánh tạo báo cáo đã kết thúc.

Nếu hai Step cần cùng một file hoặc cùng một bản ghi đầu ra, chúng có phụ thuộc dữ liệu. Không nên đưa chúng vào hai nhánh chạy song song nếu một nhánh có thể thay đổi dữ liệu mà nhánh còn lại đang đọc.

Với các công việc độc lập, Spring Batch hỗ trợ split để chạy nhiều Flow song song bằng một TaskExecutor. Sơ đồ khái quát:

~~~text
                    +--> customerFlow --+
prepareData --> split                   +--> publishReports
                    +--> orderFlow -----+
~~~

Mỗi flow con có thể chứa một hoặc nhiều Step. Step sau điểm hội tụ chỉ chạy khi các flow trong split đã hoàn thành theo quy tắc của flow.

Khi chạy song song, cần xem xét:

- Hai nhánh có truy cập hoặc cập nhật cùng một dữ liệu hay không.
- Có cần khóa, phân vùng dữ liệu hoặc thiết kế writer an toàn đồng thời không.
- Các bean dùng chung có trạng thái mutable hay không.
- Job ExecutionContext có bị nhiều nhánh cùng ghi vào một key hay không.
- Tài nguyên database, thread pool và dịch vụ bên ngoài có đủ khả năng chịu tải không.

Chỉ nên chạy song song khi các nhánh thực sự độc lập hoặc đã có cơ chế đồng bộ rõ ràng. Nếu Step B cần đầu ra của Step A, hãy giữ quan hệ phụ thuộc trong flow.

## 8. Transaction và lỗi giữa các Step

Mỗi Step có vòng đời và transaction riêng. Với chunk-oriented Step, mỗi chunk thường có một transaction. Các Step không mặc nhiên nằm trong cùng một transaction lớn.

Giả sử Job có ba Step:

~~~text
Step A: validate and prepare  -> COMPLETED
Step B: write to database    -> FAILED
Step C: create report        -> NOT STARTED
~~~

Nếu Step A đã commit dữ liệu hoặc tạo file, khi Step B thất bại, các thay đổi đã commit của Step A không tự động bị rollback. Step C không chạy trong lần flow này nếu không có transition xử lý lỗi đưa flow đến đó.

Điều này có một số hệ quả:

- Step sau chỉ được chạy khi điều kiện chuyển tiếp từ Step trước được thỏa mãn.
- Dữ liệu Step trước tạo ra có thể vẫn tồn tại dù Step sau thất bại.
- Khi restart, Step đã hoàn thành thường được bỏ qua và Spring Batch tiếp tục từ Step cần chạy lại.
- Nếu Step tạo ra tác động bên ngoài transaction, cần tính đến khả năng tác động đó đã xảy ra trước khi Job thất bại.

Với các tác động không thể rollback như gửi email, gọi API hoặc phát message, nên dùng idempotency key, outbox hoặc cơ chế bù trừ phù hợp. Một Step được chạy lại không nên tạo bản ghi hoặc gửi thông báo trùng ngoài ý muốn.

## 9. Restart Job có nhiều Step

Spring Batch lưu JobInstance, JobExecution và StepExecution trong JobRepository. Khi một Job thất bại, người vận hành có thể restart cùng JobInstance nếu trạng thái và cấu hình cho phép.

Ví dụ:

~~~text
JobInstance: importOrders, businessDate=2026-11-15

JobExecution 101:
  validateInputStep   -> COMPLETED
  normalizeOrdersStep -> COMPLETED
  writeOrdersStep     -> FAILED
  createReportStep    -> NOT STARTED

JobExecution 108 (restart):
  validateInputStep   -> skipped (đã hoàn thành)
  normalizeOrdersStep -> skipped (đã hoàn thành)
  writeOrdersStep     -> chạy lại
  createReportStep    -> chạy sau khi writeOrdersStep hoàn thành
~~~

Đây là hành vi mặc định thường gặp khi restart JobInstance: Step đã hoàn thành được bỏ qua. Step thất bại được thực thi lại, sử dụng checkpoint nếu các component hỗ trợ restart.

Nếu cần chạy lại một Step đã hoàn thành mỗi lần Job restart, có thể cấu hình allowStartIfComplete(true) cho Step đó. Chỉ bật khi thao tác của Step an toàn khi lặp hoặc có cơ chế làm sạch dữ liệu cũ.

Khi restart, cần giữ nguyên identifying JobParameters để tiếp tục cùng JobInstance. Nếu thay đổi identifying parameter, Spring Batch tạo JobInstance mới và không sử dụng checkpoint của instance trước.

### Restart và dữ liệu giữa các Step

Nếu Step A tạo file cho Step B, hãy bảo đảm file đó vẫn tồn tại và còn đúng phiên bản khi Job được restart. Nếu file tạm bị xóa sau lần chạy đầu, Step B có thể không tiếp tục được dù checkpoint của nó còn hợp lệ.

Một số cách thiết kế:

- Lưu đầu ra trung gian ở vị trí bền vững, có định danh theo JobInstance hoặc business key.
- Lưu metadata nhận diện file trong Job ExecutionContext.
- Tạo lại đầu ra một cách an toàn nếu Step tạo dữ liệu được chạy lại.
- Dùng database staging table nếu cần truy vấn, kiểm tra và phục hồi dữ liệu trung gian.
- Dọn dữ liệu tạm theo chính sách vòng đời rõ ràng, sau khi Job không còn cần restart.

Checkpoint của reader chỉ khôi phục vị trí đọc; nó không bảo đảm file nguồn vẫn tồn tại hoặc không thay đổi.

## 10. Quy tắc thiết kế một Job có nhiều Step phụ thuộc nhau

Khi chia một quy trình thành nhiều Step, nên xác định ranh giới công việc theo trách nhiệm rõ ràng. Mỗi Step nên có đầu vào, đầu ra và điều kiện hoàn thành dễ hiểu.

Một số nguyên tắc hữu ích:

1. **Một Step, một trách nhiệm chính.** Tách các công việc như kiểm tra đầu vào, biến đổi, ghi dữ liệu và tạo báo cáo khi chúng có vòng đời hoặc cách phục hồi khác nhau.
2. **Khai báo phụ thuộc trong Job flow.** Dùng next(), transition hoặc Decider để thể hiện chính xác điều kiện Step sau được chạy.
3. **Chuyển metadata bằng ExecutionContext.** Dùng Job ExecutionContext cho các giá trị nhỏ cần chia sẻ giữa Step; dùng Step ExecutionContext cho checkpoint riêng.
4. **Lưu dữ liệu nghiệp vụ ở nơi phù hợp.** Dữ liệu lớn nên nằm trong database hoặc file bền vững, không nhồi vào ExecutionContext.
5. **Thiết kế Step có thể restart.** Reader, writer và đầu ra trung gian phải hỗ trợ tiếp tục hoặc chạy lặp an toàn.
6. **Không chạy song song khi còn phụ thuộc chưa giải quyết.** Chỉ split các nhánh độc lập hoặc đã có cơ chế đồng bộ.
7. **Đặt tên Step ổn định.** Metadata và lịch sử execution gắn với tên Step; đổi tên tùy tiện có thể ảnh hưởng việc nhận diện trạng thái giữa các phiên bản triển khai.
8. **Quan sát từng Step.** Theo dõi BatchStatus, ExitStatus, thời gian chạy và các bộ đếm để biết chính xác Step nào đã hoàn thành hoặc thất bại.

Một Job có nhiều Step không nhất thiết tốt hơn một Step lớn. Chia Step khi có lợi ích rõ ràng về trách nhiệm, phục hồi, khả năng quan sát hoặc điều hướng nghiệp vụ. Nếu các thao tác luôn phải thành một đơn vị xử lý nhỏ và không cần vòng đời riêng, có thể giữ chúng trong cùng Step.

## 11. Theo dõi và kiểm thử luồng nhiều Step

Khi kiểm tra một Job nhiều Step, cần xác nhận cả thứ tự thực thi và dữ liệu truyền giữa các Step.

Với một Job tuần tự, có thể quan sát danh sách StepExecution thuộc JobExecution và kiểm tra:

- Step nào đã bắt đầu và kết thúc.
- Thứ tự Step thực tế.
- BatchStatus và ExitStatus của từng Step.
- Các bộ đếm đọc, ghi, lọc, skip, commit và rollback nếu là chunk Step.
- Các key quan trọng trong Job ExecutionContext.
- Đầu ra trung gian mà Step kế tiếp sử dụng.

Khi viết integration test, có thể dùng JobLauncherTestUtils trong bộ hỗ trợ kiểm thử Spring Batch để chạy Job với JobParameters cụ thể. Một số kịch bản quan trọng:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Tất cả Step thành công | Các Step chạy đúng thứ tự và Job hoàn thành |
| Step đầu thất bại | Step phụ thuộc phía sau không chạy theo nhánh thành công |
| Step giữa thất bại | Step sau không chạy; trạng thái và checkpoint được lưu |
| Restart sau lỗi | Step đã hoàn thành được xử lý theo cấu hình; Step lỗi có thể tiếp tục |
| Nhánh điều kiện khác nhau | Flow đi đúng nhánh theo ExitStatus hoặc Decider |
| Thiếu dữ liệu chia sẻ | Step tiêu thụ báo lỗi rõ ràng thay vì dùng giá trị mặc định sai |
| Chạy song song | Không có ghi đè dữ liệu hoặc tranh chấp tài nguyên ngoài dự kiến |

Một test chỉ kiểm tra Job có trạng thái COMPLETED là chưa đủ nếu quy trình có nhiều nhánh. Nên kiểm tra cả StepExecution được tạo, thứ tự thực thi và dữ liệu đầu ra của các Step quan trọng.

Khi đọc một Job nhiều Step, hãy lần theo ba mối quan hệ: flow quyết định Step nào chạy tiếp; ExecutionContext hoặc kho dữ liệu chia sẻ đầu ra giữa các Step; JobRepository lưu trạng thái để theo dõi và restart. Thiết kế rõ cả ba giúp quy trình batch dễ vận hành và phục hồi khi một công đoạn gặp lỗi.


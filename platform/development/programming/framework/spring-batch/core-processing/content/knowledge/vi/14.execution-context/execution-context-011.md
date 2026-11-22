# Phân biệt context với job parameters

Trong Spring Batch, **JobParameters** và **ExecutionContext** đều mang dữ liệu trong quá trình chạy Job, nhưng chúng giải quyết hai vấn đề khác nhau:

- **JobParameters** là dữ liệu đầu vào được truyền khi khởi chạy Job. Chúng mô tả lần chạy được yêu cầu và các tham số identifying có thể xác định JobInstance.
- **ExecutionContext** là vùng lưu trạng thái có thể thay đổi trong lúc thực thi. Spring Batch và ứng dụng dùng nó để lưu checkpoint, tiến độ và dữ liệu cần khôi phục khi restart.

Một cách nhớ ngắn gọn: JobParameters trả lời **“Job được yêu cầu chạy với đầu vào nào?”**; ExecutionContext trả lời **“Job đã xử lý đến đâu và cần giữ trạng thái gì để tiếp tục?”**

Nếu dùng nhầm hai cơ chế, Job có thể tạo JobInstance không đúng, restart sai dữ liệu, hoặc mất trạng thái trung gian giữa các Step.

## 1. JobParameters là gì?

JobParameters là tập tham số được truyền cho Job khi ứng dụng gọi JobLauncher. Các giá trị thường mô tả đơn vị công việc cần xử lý hoặc cách thức thực hiện công việc đó.

Ví dụ một Job nhập file có thể nhận:

- Đường dẫn file đầu vào.
- Ngày nghiệp vụ.
- Mã khách hàng hoặc mã kỳ đối soát.
- Chế độ FULL hoặc DELTA.
- Mã yêu cầu từ hệ thống gọi.

Tạo JobParameters bằng JobParametersBuilder:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/customers.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("mode", "FULL", false)
        .toJobParameters();
~~~

Tham số boolean cuối cùng xác định giá trị có phải **identifying parameter** hay không:

- true: tham gia xác định JobInstance.
- false: không tham gia xác định JobInstance.

Trong ví dụ:

- inputFile và businessDate là identifying parameters.
- mode là non-identifying parameter.

JobParameters được tạo trước khi Job chạy và được xem là dữ liệu đầu vào của lần thực thi. Bản thân JobParameters là đối tượng bất biến; nếu cần ghi lại tiến độ thay đổi trong lúc chạy, hãy dùng ExecutionContext.

### JobParameters được truyền cho JobLauncher

~~~java
JobExecution execution = jobLauncher.run(
        customerImportJob,
        parameters
);
~~~

JobLauncher nhận Job cùng JobParameters và yêu cầu JobRepository xác định JobInstance tương ứng. Nếu điều kiện khởi chạy hợp lệ, Spring Batch tạo JobExecution cho lần thực thi.

JobParameters gắn với lần thực thi và được lưu trong metadata repository. Chúng có thể được đọc trong các thành phần của Job, nhưng không phải nơi để lưu checkpoint sau mỗi chunk.

## 2. Identifying parameters quyết định JobInstance

Một JobInstance được xác định bởi:

1. Tên Job.
2. Tập identifying JobParameters.

Ví dụ Job customerImportJob chạy với:

~~~text
inputFile = /data/customers-01.csv
businessDate = 2026-11-15
mode = FULL
~~~

Nếu inputFile và businessDate được đánh dấu identifying, tên Job cùng hai giá trị đó xác định một JobInstance.

~~~text
Job definition: customerImportJob
       |
       +-- JobInstance A
       |     inputFile=/data/customers-01.csv
       |     businessDate=2026-11-15
       |
       +-- JobInstance B
             inputFile=/data/customers-02.csv
             businessDate=2026-11-15
~~~

Hai file đầu vào khác nhau tạo ra hai JobInstance khác nhau vì inputFile là identifying parameter.

Nếu chỉ thay mode từ FULL sang DELTA mà mode không identifying, JobInstance vẫn có cùng danh tính. Giá trị mode vẫn là một phần của JobParameters của lần thực thi, nhưng không tạo ra JobInstance mới.

### Vì sao danh tính JobInstance quan trọng?

Spring Batch dùng JobInstance để quản lý lịch sử và restart:

- Nếu JobInstance đang chạy, yêu cầu chạy trùng có thể bị từ chối.
- Nếu JobInstance đã hoàn thành, chạy lại với cùng identifying parameters thường bị từ chối vì instance đó đã hoàn tất.
- Nếu JobInstance thất bại hoặc dừng và có thể restart, lần chạy tiếp theo dùng cùng identifying parameters để tiếp tục instance cũ.
- Nếu thay đổi identifying parameter, yêu cầu thuộc JobInstance mới và không dùng checkpoint của instance cũ.

Vì vậy, hãy chọn identifying parameters theo đơn vị nghiệp vụ cần xử lý. Nếu mỗi file là một công việc riêng, mã file hoặc đường dẫn file có thể là identifying parameter. Nếu mỗi ngày đối soát là một công việc riêng, businessDate có thể tham gia danh tính.

Không nên dùng một tham số tăng ngẫu nhiên làm identifying chỉ để tránh lỗi chạy trùng nếu mục tiêu thực sự là restart Job cũ. Làm vậy sẽ tạo JobInstance mới và không khôi phục trạng thái của instance đang dang dở.

## 3. Non-identifying parameters dùng khi nào?

Non-identifying parameter được lưu cùng lần thực thi nhưng không ảnh hưởng đến danh tính JobInstance.

Ví dụ:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "/data/customers.csv", true)
        .addString("notificationMode", "EMAIL", false)
        .toJobParameters();
~~~

Trong ví dụ, notificationMode không làm thay đổi JobInstance. Tham số này có thể điều khiển cách gửi thông báo hoặc cách ghi log nếu điều đó không làm thay đổi ý nghĩa dữ liệu nghiệp vụ được xử lý.

Hãy cẩn thận khi chọn non-identifying parameter. Nếu một giá trị làm thay đổi tập dữ liệu, quy tắc tính toán hoặc kết quả nghiệp vụ, việc không đưa nó vào danh tính có thể khiến hai yêu cầu khác nhau bị xem là cùng JobInstance.

Ví dụ, nếu mode=FULL và mode=DELTA tạo ra hai kết quả nghiệp vụ khác nhau cho cùng file và ngày xử lý, hãy cân nhắc xem mode có nên là identifying parameter hay không. Quyết định phụ thuộc vào định nghĩa một đơn vị xử lý logic của ứng dụng.

Cũng cần giữ các tham số có ý nghĩa nhất quán khi restart. Dù một parameter không identifying, thay đổi nó giữa lần chạy lỗi và lần restart vẫn có thể làm thay đổi kết quả. JobInstance identity và tính nhất quán nghiệp vụ là hai vấn đề cần xem xét riêng.

## 4. ExecutionContext là gì?

ExecutionContext là vùng lưu dữ liệu key-value gắn với một lần thực thi. Khác với JobParameters, ExecutionContext có thể được cập nhật trong khi Job hoặc Step đang chạy.

Ví dụ:

~~~java
ExecutionContext context = stepExecution.getExecutionContext();

context.putLong("lastCustomerId", 98765L);
context.putInt("processedCount", 500);
context.putString("outputFile", "/data/result-part-01.csv");
~~~

Các giá trị này có thể biểu diễn:

- Vị trí reader đã xử lý.
- ID cuối cùng đã đọc.
- Số bản ghi đã hoàn tất.
- Tên file tạm đang được tạo.
- Một mã trạng thái trung gian.
- Thông tin cần chuyển từ Step này sang Step khác.

ExecutionContext không phải một biến local chỉ tồn tại trong một phương thức. Spring Batch lưu trạng thái của nó vào JobRepository theo vòng đời thực thi để hỗ trợ restart và tiếp tục công việc.

Các giá trị đưa vào ExecutionContext cần tương thích với cơ chế serialization được cấu hình cho JobRepository. Nên ưu tiên kiểu dữ liệu đơn giản, nhỏ và ổn định như String, số, boolean, ngày giờ hoặc ID. Tránh lưu object graph lớn, connection, stream, service hay object không thể serialize.

## 5. Có hai phạm vi ExecutionContext

Spring Batch có ExecutionContext ở hai cấp:

| Phạm vi | Thuộc về | Mục đích |
|---|---|---|
| Job ExecutionContext | JobExecution | Lưu trạng thái dùng chung giữa các Step trong một lần chạy Job |
| Step ExecutionContext | StepExecution | Lưu trạng thái riêng của một Step, thường dùng cho checkpoint |

### Job ExecutionContext

Job ExecutionContext được gắn với JobExecution. Nó phù hợp với dữ liệu cần được Step sau sử dụng.

Ví dụ:

- Step đầu tiên xác định tên file chuẩn hóa.
- Step tiếp theo cần biết tên file đó.
- Một Step tổng hợp ghi nhận ID của báo cáo được tạo.
- Các Step sau cần biết mã kỳ xử lý hoặc kết quả trung gian.

### Step ExecutionContext

Step ExecutionContext được gắn với một StepExecution. Nó phù hợp với trạng thái chỉ có ý nghĩa trong phạm vi Step đó.

Ví dụ:

- Reader đang ở dòng nào của file.
- ID cuối cùng đã đọc.
- Trang hiện tại của paging reader.
- Số lượng item đã xử lý trong Step.
- Trạng thái nội bộ cần khôi phục khi restart Step.

Không nên lưu mọi dữ liệu vào Job ExecutionContext. Nếu dữ liệu chỉ phục vụ checkpoint của một reader, hãy giữ nó ở Step ExecutionContext để tránh làm Job context phình to và khó hiểu.

## 6. Vòng đời và khả năng lưu trạng thái

Khi Job bắt đầu, Spring Batch tạo JobExecution. Mỗi Step được thực thi tạo một StepExecution tương ứng. Mỗi đối tượng có ExecutionContext riêng.

~~~text
JobParameters
     |
     v
JobLauncher
     |
     v
JobRepository
     |
     v
JobInstance
     |
     v
JobExecution
  + Job ExecutionContext
     |
     +--> StepExecution A
     |       + Step ExecutionContext A
     |
     +--> StepExecution B
             + Step ExecutionContext B
~~~

Với chunk Step, trạng thái Step ExecutionContext thường được cập nhật tại ranh giới checkpoint khi chunk hoàn tất. Khi chunk commit, trạng thái cần thiết có thể được lưu cùng metadata của Step theo transaction configuration.

Khi Job restart:

1. Spring Batch tìm JobInstance bằng tên Job và identifying JobParameters.
2. Repository lấy metadata của các lần thực thi trước.
3. Step đã hoàn thành thường được bỏ qua, trừ khi cấu hình cho phép chạy lại.
4. Step chưa hoàn thành hoặc thất bại được khởi động lại theo trạng thái đã lưu.
5. Reader hoặc writer có hỗ trợ ItemStream mở lại với ExecutionContext trước đó.
6. Step tiếp tục từ checkpoint mà thành phần xử lý có thể khôi phục.

Nếu metadata repository chỉ lưu trong bộ nhớ và tiến trình đã kết thúc, trạng thái có thể mất. Muốn restart qua lần khởi động ứng dụng mới, cần JobRepository bền vững, thường là database-backed repository.

## 7. So sánh trực tiếp JobParameters và ExecutionContext

| Tiêu chí | JobParameters | ExecutionContext |
|---|---|---|
| Mục đích | Đầu vào của lần chạy | Trạng thái trong quá trình chạy |
| Thời điểm tạo | Trước khi Job khởi chạy | Được tạo và cập nhật trong quá trình thực thi |
| Có thay đổi khi Job chạy? | Không; đối tượng tham số là bất biến | Có; là vùng lưu trạng thái mutable |
| Xác định JobInstance? | Các identifying parameters có | Không |
| Phạm vi | Gắn với JobExecution | JobExecution hoặc StepExecution |
| Dùng cho checkpoint? | Không phải cơ chế checkpoint | Có |
| Chia sẻ giữa các Step? | Các Step có thể đọc cùng tham số đầu vào | Job context có thể giữ dữ liệu dùng chung |
| Restart | Dùng identifying parameters để tìm JobInstance | Khôi phục tiến độ và trạng thái đã lưu |
| Ví dụ | inputFile, businessDate, tenantId | lastReadId, currentLine, generatedFile |

Một quy tắc thực tế:

- Dữ liệu đã biết trước khi chạy và mô tả yêu cầu xử lý: JobParameters.
- Dữ liệu phát sinh hoặc thay đổi trong lúc chạy: ExecutionContext.
- Trạng thái reader/writer để restart: Step ExecutionContext.
- Dữ liệu trung gian cần Step sau sử dụng: Job ExecutionContext.

## 8. Ví dụ: JobParameters cho đầu vào, ExecutionContext cho tiến độ

Giả sử Job nhập file khách hàng. JobParameters chứa đường dẫn file và ngày nghiệp vụ. Reader lưu ID cuối cùng đã đọc vào Step ExecutionContext.

### Khởi chạy Job với JobParameters

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/customers.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();

JobExecution execution =
        jobLauncher.run(customerImportJob, parameters);
~~~

### Reader nhận JobParameters

Có thể dùng StepScope để inject tham số lúc Step bắt đầu:

~~~java
@Bean
@StepScope
public FlatFileItemReader<RawCustomer> customerReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<RawCustomer>()
            .name("customerReader")
            .resource(inputFile)
            .delimited()
            .names("id", "name", "email")
            .targetType(RawCustomer.class)
            .saveState(true)
            .build();
}
~~~

Ở đây inputFile là dữ liệu đầu vào cố định của lần chạy. Reader có thể dùng nó để mở đúng file. saveState(true) cho phép reader lưu trạng thái riêng vào ExecutionContext để hỗ trợ restart.

### Lưu tiến độ trong Step ExecutionContext

Một thành phần có thể cập nhật trạng thái xử lý:

~~~java
public class ProgressListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        ExecutionContext context =
                stepExecution.getExecutionContext();

        context.putLong(
                "lastReadCount",
                stepExecution.getReadCount());

        return stepExecution.getExitStatus();
    }
}
~~~

Ví dụ trên minh họa việc ghi một giá trị vào Step ExecutionContext. Trong ứng dụng thực tế, listener cần được đăng ký với Step và cập nhật trạng thái tại thời điểm phù hợp. Đối với checkpoint reader, nên để reader triển khai ItemStream và tự lưu vị trí đọc qua open/update thay vì dùng listener để đoán vị trí.

## 9. Chuyển dữ liệu từ Step context sang Job context

Một Step có thể tạo ra dữ liệu cần Step tiếp theo sử dụng. Có thể lưu dữ liệu đó trong Job ExecutionContext.

Ví dụ Step tạo báo cáo và muốn truyền reportId cho Step gửi thông báo:

~~~java
public class CreateReportTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        StepExecution stepExecution = chunkContext
                .getStepContext()
                .getStepExecution();

        stepExecution.getExecutionContext()
                .putLong("reportId", 12345L);

        return RepeatStatus.FINISHED;
    }
}
~~~

Đoạn code trên lưu reportId vào Step ExecutionContext. Để Step tiếp theo sử dụng như dữ liệu chung ở cấp Job, có thể dùng **ExecutionContextPromotionListener**.

~~~java
@Bean
public ExecutionContextPromotionListener reportContextPromotionListener() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();

    listener.setKeys(new String[] {"reportId"});
    return listener;
}
~~~

Đăng ký listener với Step tạo báo cáo:

~~~java
@Bean
public Step createReportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ExecutionContextPromotionListener reportContextPromotionListener) {

    return new StepBuilder("createReportStep", jobRepository)
            .tasklet(new CreateReportTasklet(), transactionManager)
            .listener(reportContextPromotionListener)
            .build();
}
~~~

Sau khi Step hoàn tất theo điều kiện listener được cấu hình, key reportId được promote từ Step ExecutionContext lên Job ExecutionContext. Step sau có thể đọc giá trị đó.

Nếu cần promote chỉ khi Step hoàn thành thành công, hãy cấu hình các ExitStatus phù hợp cho listener, thay vì mặc định promote mọi kết quả. Với dữ liệu cần thiết cho Step sau, hãy xác định rõ điều kiện thành công và cách xử lý khi Step trước thất bại.

## 10. Đọc Job ExecutionContext và Step ExecutionContext bằng scope

Trong Spring Batch, các scope cho phép inject dữ liệu runtime vào bean.

### Đọc JobParameters

~~~java
@Bean
@StepScope
public ItemReader<RawCustomer> reader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {
    // Tạo reader theo file đầu vào.
}
~~~

### Đọc Job ExecutionContext

~~~java
@Bean
@StepScope
public ItemProcessor<RawCustomer, Customer> processor(
        @Value("#{jobExecutionContext['importMode']}") String importMode) {
    // Dùng dữ liệu chung của Job.
}
~~~

### Đọc Step ExecutionContext

~~~java
@Bean
@StepScope
public ItemWriter<Customer> writer(
        @Value("#{stepExecutionContext['outputPath']}") String outputPath) {
    // Dùng trạng thái riêng của Step hiện tại.
}
~~~

Các biểu thức này thường được dùng cùng @StepScope vì dữ liệu chỉ có khi Step thực sự chạy. Không nên tạo một singleton bean ngay lúc application context khởi động rồi cố đọc JobParameters chưa tồn tại.

Nếu key chưa được lưu trong context, biểu thức có thể nhận null hoặc không thể resolve theo kiểu dữ liệu được yêu cầu. Hãy bảo đảm Step trước đã ghi/promote key và kiểu dữ liệu phù hợp.

## 11. Dùng ExecutionContext cho checkpoint của reader

Một reader hỗ trợ restart thường triển khai ItemStream. Ba phương thức chính:

- open(ExecutionContext): khôi phục trạng thái đã lưu hoặc khởi tạo trạng thái mới.
- update(ExecutionContext): lưu tiến độ hiện tại tại checkpoint.
- close(): giải phóng resource.

Ví dụ reader tùy chỉnh lưu ID cuối cùng đã đọc:

~~~java
public class CustomerReader implements ItemStreamReader<Customer> {

    private final CustomerRepository repository;
    private long lastId;

    public CustomerReader(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public void open(ExecutionContext context) {
        lastId = context.getLong("lastId", 0L);
    }

    @Override
    public Customer read() {
        Customer customer = repository.findNextAfter(lastId);

        if (customer != null) {
            lastId = customer.getId();
        }

        return customer;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("lastId", lastId);
    }

    @Override
    public void close() {
        // Đóng resource nếu reader tự mở resource.
    }
}
~~~

Trong ví dụ:

- lastId là trạng thái thay đổi theo tiến độ đọc.
- open() khôi phục lastId từ ExecutionContext.
- read() lấy bản ghi tiếp theo.
- update() lưu vị trí hiện tại tại checkpoint.

Khi Job restart, reader mới được mở bằng context đã lưu và có thể tiếp tục từ ID tương ứng.

Trong ứng dụng thực tế, truy vấn findNextAfter cần có thứ tự ổn định, khóa duy nhất và điều kiện phân trang tái lập. Nếu nguồn dữ liệu thay đổi giữa lần chạy đầu và restart, chỉ lưu ID cuối cùng có thể chưa đủ để bảo đảm cùng một tập dữ liệu.

## 12. Không dùng JobParameters để lưu tiến độ

Một lỗi thiết kế là cố gắng biến JobParameters thành nơi lưu trạng thái thay đổi:

~~~java
// Không có API cập nhật JobParameters theo kiểu này.
parameters.addLong("lastProcessedId", lastId);
~~~

JobParameters không phải một map mutable để Step cập nhật sau mỗi chunk. Nếu muốn lưu ID cuối cùng đã xử lý, hãy dùng Step ExecutionContext.

Ngược lại, cũng không nên đặt inputFile hoặc businessDate vào ExecutionContext chỉ vì có thể ghi key-value. Những giá trị này đã là đầu vào của lần chạy và có thể tham gia xác định JobInstance; hãy giữ chúng trong JobParameters.

Dùng đúng cơ chế giúp metadata có ý nghĩa rõ ràng:

- JobParameters thể hiện yêu cầu chạy.
- ExecutionContext thể hiện trạng thái thực thi.
- JobInstance thể hiện đơn vị xử lý logic.
- JobExecution thể hiện một lần thực thi cụ thể.

## 13. Restart: hai cơ chế phối hợp như thế nào?

Khi restart một JobInstance, Spring Batch cần cả JobParameters và ExecutionContext.

Ví dụ:

~~~text
Job: customerImportJob
JobParameters:
  inputFile=customers.csv (identifying)
  businessDate=2026-11-15 (identifying)

JobInstance A
  |
  +-- JobExecution 1: FAILED
  |      |
  |      +-- Step importCustomersStep
  |             Step ExecutionContext:
  |               lastId=200
  |
  +-- JobExecution 2: RESTART
         |
         +-- Dùng lại JobInstance A
         |
         +-- Reader mở với checkpoint lastId=200
                |
                v
           Tiếp tục sau ID 200
~~~

JobParameters xác định JobInstance nào cần restart. ExecutionContext lưu tiến độ của Step để reader/writer có thể khôi phục.

Nếu thay inputFile thành một file khác và inputFile là identifying parameter, yêu cầu mới tạo JobInstance khác. Context của JobInstance cũ không được dùng cho lần chạy mới.

Nếu chỉ thay non-identifying parameter, danh tính JobInstance vẫn có thể giữ nguyên. Nhưng nếu giá trị đó làm thay đổi cách xử lý dữ liệu, restart có thể tạo kết quả không nhất quán. Vì vậy, không chỉ nhìn cờ identifying; hãy đánh giá ý nghĩa nghiệp vụ của từng tham số.

## 14. Job context không thay thế Step context

Có thể lưu mọi thứ vào Job ExecutionContext, nhưng điều đó thường làm trạng thái khó quản lý.

Ví dụ, reader lưu currentLine vào Job context. Nếu Job có hai Step cùng đọc file, key currentLine có thể bị trùng hoặc bị Step khác ghi đè.

Cách phân chia rõ hơn:

| Dữ liệu | Nơi lưu phù hợp |
|---|---|
| Đường dẫn file đầu vào | JobParameters |
| Ngày nghiệp vụ | JobParameters |
| Chế độ xử lý xác định khi khởi chạy | JobParameters |
| Vị trí đọc file của Step A | Step A ExecutionContext |
| Trang hiện tại của reader Step B | Step B ExecutionContext |
| ID báo cáo cần Step gửi email sử dụng | Job ExecutionContext |
| Kết quả trung gian dùng chung giữa nhiều Step | Job ExecutionContext |
| Counter phục vụ checkpoint riêng của Step | Step ExecutionContext |

Job context phù hợp với trạng thái chia sẻ giữa các Step trong cùng JobExecution. Step context phù hợp với tiến độ riêng của một StepExecution.

## 15. ExecutionContext không phải nơi lưu dữ liệu nghiệp vụ lớn

ExecutionContext được lưu cùng metadata thực thi. Vì vậy, nếu đưa object graph lớn vào context, có thể làm metadata phình to, tăng chi phí serialize/deserialize và ảnh hưởng thời gian restart.

Ví dụ không nên lưu toàn bộ danh sách khách hàng:

~~~java
context.put("allCustomers", customers);
~~~

Thay vào đó, lưu một ID hoặc vị trí tham chiếu:

~~~java
context.putLong("stagingBatchId", stagingBatchId);
context.putString("outputFile", outputFilePath);
~~~

Khi cần dữ liệu, Step tiếp theo tải lại từ database hoặc file bằng ID đó.

Cũng không nên lưu các object không thể serialize hoặc gắn với vòng đời tài nguyên như:

- Connection hoặc DataSource.
- BufferedReader hoặc BufferedWriter.
- HTTP client/session không được thiết kế để serialize.
- Spring bean hoặc proxy.
- Thread, executor hoặc lock.
- Entity graph lớn có quan hệ vòng.

ExecutionContext nên chứa trạng thái nhỏ, có thể khôi phục và có ý nghĩa khi restart.

## 16. Đặt tên key và tránh xung đột

ExecutionContext là map key-value. Khi nhiều thành phần cùng lưu trạng thái, hãy đặt key có namespace hoặc tên reader/step rõ ràng.

Ví dụ:

~~~java
context.putLong("customerReader.lastId", lastId);
context.putString("reportStep.outputPath", outputPath);
context.putInt("validationStep.invalidCount", invalidCount);
~~~

Tránh dùng key chung chung như current, status hoặc count nếu nhiều thành phần có thể ghi cùng context.

Với Step ExecutionContext, key vẫn nên có tên rõ để dễ chẩn đoán trong metadata. Với Job ExecutionContext, cần đặc biệt tránh xung đột giữa các Step vì đây là vùng trạng thái chia sẻ.

Không đổi tên key tùy tiện giữa các phiên bản ứng dụng nếu JobInstance cũ có thể được restart bằng code mới. Nếu cấu trúc context thay đổi, hãy cân nhắc tương thích ngược hoặc cơ chế migration/default value.

## 17. JobParameters và ExecutionContext trong test

Khi kiểm thử Job, hãy xác nhận cả đầu vào và trạng thái thực thi.

Ví dụ chạy Job với JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/tmp/customers.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();

JobExecution execution =
        jobLauncherTestUtils.launchJob(parameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());

assertEquals(
        "/tmp/customers.csv",
        execution.getJobParameters().getString("inputFile"));
~~~

Có thể kiểm tra Step ExecutionContext:

~~~java
StepExecution stepExecution = execution.getStepExecutions()
        .stream()
        .filter(step -> "importCustomersStep".equals(step.getStepName()))
        .findFirst()
        .orElseThrow();

ExecutionContext context = stepExecution.getExecutionContext();

assertEquals(
        200L,
        context.getLong("lastCustomerId"));
~~~

Assertion cụ thể phụ thuộc reader và key mà ứng dụng lưu. Với reader dựng sẵn, key nội bộ có thể khác; nên kiểm tra qua API hoặc hành vi restart thay vì gắn test với implementation detail không ổn định.

### Test identifying parameters

Một test riêng nên xác nhận:

- Cùng tên Job và cùng identifying parameters tạo cùng JobInstance.
- Thay identifying parameter tạo JobInstance khác.
- Thay non-identifying parameter không đổi danh tính JobInstance.
- JobInstance đã hoàn tất không được chạy lại như một instance mới với cùng identifying parameters.
- Restart JobInstance thất bại dùng lại đúng identifying parameters và khôi phục checkpoint.

## 18. Những lỗi thường gặp

### Dùng ExecutionContext thay cho JobParameters

Đường dẫn file và ngày nghiệp vụ đã biết trước khi chạy nên được truyền bằng JobParameters. Nếu chỉ lưu chúng trong context, danh tính JobInstance không phản ánh đúng đơn vị công việc.

### Dùng JobParameters để lưu checkpoint

JobParameters không phải vùng dữ liệu mutable. Vị trí reader, ID cuối cùng hoặc số chunk đã xử lý thuộc ExecutionContext.

### Đưa mọi trạng thái vào Job context

Trạng thái riêng của reader/Step nên ở Step ExecutionContext. Nếu dùng Job context cho tất cả, các Step có thể ghi đè key của nhau và khó restart độc lập.

### Nghĩ rằng non-identifying parameter không quan trọng

Nó không quyết định JobInstance identity nhưng vẫn có thể thay đổi cách xử lý. Cần giữ các giá trị này nhất quán khi restart nếu chúng ảnh hưởng kết quả.

### Lưu object lớn vào ExecutionContext

Context được lưu trong metadata repository. Object graph lớn làm tăng chi phí lưu, đọc và restart. Hãy lưu ID hoặc vị trí tham chiếu.

### Nghĩ rằng Job context tự động nhận mọi giá trị từ Step context

Step context và Job context là hai phạm vi riêng. Muốn chia sẻ key từ Step sang Job, hãy dùng cơ chế promotion hoặc cập nhật Job ExecutionContext có chủ đích.

### Nghĩ rằng restart chỉ cần ExecutionContext

Spring Batch cần xác định đúng JobInstance bằng JobParameters trước, rồi mới khôi phục ExecutionContext tương ứng.

## 19. Cách chọn đúng nơi lưu dữ liệu

Khi thiết kế một Job, hãy phân loại từng giá trị:

1. Giá trị có sẵn trước khi Job bắt đầu và mô tả yêu cầu xử lý? Dùng JobParameters.
2. Giá trị có tham gia xác định một đơn vị nghiệp vụ độc lập? Đánh dấu identifying.
3. Giá trị chỉ điều khiển cách chạy nhưng không tạo đơn vị xử lý mới? Cân nhắc non-identifying.
4. Giá trị phát sinh trong khi xử lý và cần tiếp tục sau restart? Dùng ExecutionContext.
5. Trạng thái chỉ phục vụ một Step? Dùng Step ExecutionContext.
6. Kết quả trung gian cần Step sau sử dụng? Dùng Job ExecutionContext hoặc promotion.
7. Dữ liệu lớn hoặc dữ liệu nghiệp vụ chính? Lưu ở database/file; context chỉ giữ ID tham chiếu.
8. Giá trị cần giữ ổn định khi restart? Kiểm tra cả identifying và non-identifying JobParameters cùng nguồn dữ liệu.

Phân biệt rõ hai cơ chế giúp Job có danh tính đúng và khả năng khôi phục đáng tin cậy. JobParameters mô tả yêu cầu chạy và xác định JobInstance thông qua các tham số identifying. ExecutionContext lưu trạng thái thay đổi trong quá trình thực thi ở cấp Job hoặc Step. Khi dùng đúng phạm vi, Spring Batch có thể vừa biết đang xử lý công việc nào, vừa khôi phục được công việc đã tiến hành đến đâu.

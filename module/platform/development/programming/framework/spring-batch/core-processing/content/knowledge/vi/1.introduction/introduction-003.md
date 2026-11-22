# Job, Step và flow thực thi trong Spring Batch

Spring Batch tổ chức một quy trình xử lý dữ liệu thành các **Job** và **Step**. Job mô tả một lần chạy nghiệp vụ ở cấp cao, còn Step chia công việc đó thành những phần có thể thực thi, quản lý giao dịch, ghi nhận trạng thái và khởi động lại. Flow xác định Step nào chạy tiếp theo dựa trên kết quả của Step trước đó.

Nắm được ba khái niệm này giúp bạn đọc cấu hình Spring Batch, thiết kế quy trình nhiều bước và xử lý đúng các tình huống như lỗi giữa chừng, chạy lại hoặc rẽ nhánh theo dữ liệu.

## 1. Bức tranh tổng thể

Một ứng dụng có thể định nghĩa nhiều Job. Mỗi Job gồm một hoặc nhiều Step; các Step được nối theo một flow tuyến tính hoặc có điều kiện.

Ví dụ quy trình nhập dữ liệu khách hàng:

1. Kiểm tra file đầu vào.
2. Đọc, chuẩn hóa và lưu từng nhóm bản ghi.
3. Tạo báo cáo kết quả.
4. Nếu file không hợp lệ, chuyển sang Step ghi nhận dữ liệu bị từ chối.

Trong Spring Batch, quy trình này được khai báo thành một Job. Mỗi công đoạn là một Step. Job điều phối các Step theo flow được cấu hình.

~~~text
Job: customerImportJob
  |
  +--> validateInputStep
          |
          +-- COMPLETED ------> importCustomersStep
          |                          |
          |                          +--> createReportStep
          |
          +-- INVALID_INPUT --> recordRejectedFileStep
~~~

Các thành phần chính có trách nhiệm khác nhau:

| Thành phần | Vai trò |
|---|---|
| **Job** | Định nghĩa quy trình xử lý ở cấp cao và thứ tự điều phối các Step |
| **Step** | Định nghĩa một đơn vị công việc có thể thực thi và theo dõi |
| **JobLauncher** | Nhận yêu cầu chạy Job cùng JobParameters |
| **JobRepository** | Lưu metadata về Job, lần chạy, Step, trạng thái và checkpoint |
| **JobParameters** | Cung cấp tham số cho một lần chạy và xác định danh tính JobInstance |
| **JobExecution** | Đại diện cho một lần thực thi cụ thể của Job |
| **StepExecution** | Đại diện cho một lần thực thi cụ thể của Step |
| **ExecutionContext** | Lưu trạng thái cần thiết để tiếp tục công việc, đặc biệt khi restart |

**Job** và **Step** là các định nghĩa được cấu hình trong ứng dụng. **JobExecution** và **StepExecution** là các đối tượng runtime được tạo ra mỗi khi công việc thực sự chạy.

## 2. Job: định nghĩa một quy trình xử lý

**Job** là đơn vị xử lý cấp cao nhất trong Spring Batch. Một Job thường đại diện cho một công việc nghiệp vụ có điểm bắt đầu, các bước xử lý và kết quả cuối cùng.

Ví dụ:

- Nhập dữ liệu đơn hàng từ file CSV.
- Đối soát giao dịch trong ngày.
- Tính toán số dư cuối ngày.
- Đọc dữ liệu từ hệ thống nguồn rồi đồng bộ sang hệ thống đích.

Một Job có tên duy nhất trong phạm vi repository và được xây dựng từ các Step hoặc Flow. Job không chứa toàn bộ logic xử lý dữ liệu; logic cụ thể nằm trong từng Step và các thành phần mà Step sử dụng.

### Khai báo Job

Với API builder hiện đại của Spring Batch 5, có thể tạo Job bằng **JobBuilder** và truyền **JobRepository**:

~~~java
@Configuration
public class CustomerImportJobConfig {

    @Bean
    public Job customerImportJob(
            JobRepository jobRepository,
            Step validateInputStep,
            Step importCustomersStep,
            Step createReportStep) {

        return new JobBuilder("customerImportJob", jobRepository)
                .start(validateInputStep)
                .next(importCustomersStep)
                .next(createReportStep)
                .build();
    }
}
~~~

Trong ví dụ này:

- **customerImportJob** là tên Job.
- **start(validateInputStep)** chỉ định Step đầu tiên.
- **next(importCustomersStep)** nối Step nhập dữ liệu sau Step kiểm tra.
- **next(createReportStep)** nối Step tạo báo cáo sau Step nhập dữ liệu.
- **build()** hoàn tất định nghĩa Job.

Đây là flow tuyến tính. Spring Batch chạy lần lượt các Step theo thứ tự đã khai báo. Nếu một Step thất bại, Job thông thường kết thúc với trạng thái thất bại và không tiếp tục các Step phía sau.

**JobRepository** được truyền vào builder để Job có thể lưu và truy xuất metadata thực thi. Trong ứng dụng Spring Boot, hạ tầng Batch thường được cấu hình tự động nếu ứng dụng có các dependency và cấu hình phù hợp. Khi tự cấu hình hạ tầng, cần cung cấp **JobRepository** và transaction manager tương ứng.

### Job definition, JobInstance và JobExecution

Ba khái niệm này cần được phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| **Job** | Định nghĩa quy trình, ví dụ customerImportJob |
| **JobInstance** | Một lần chạy logic được nhận diện bởi tên Job và các identifying JobParameters |
| **JobExecution** | Một lần thử thực thi JobInstance |

Ví dụ Job **customerImportJob** được chạy với tham số **inputFile=/data/customer-01.csv**. Tên Job cùng identifying parameter này xác định một JobInstance. Nếu lần chạy thất bại và được khởi động lại với cùng identifying parameters, Spring Batch tạo một JobExecution mới thuộc cùng JobInstance.

Có thể hình dung:

~~~text
Job definition: customerImportJob
  |
  +-- JobInstance A (inputFile=customer-01.csv)
  |      |
  |      +-- JobExecution 1: FAILED
  |      |
  |      +-- JobExecution 2: COMPLETED  (restart)
  |
  +-- JobInstance B (inputFile=customer-02.csv)
         |
         +-- JobExecution 1: COMPLETED
~~~

Một JobInstance được xác định bởi:

- Tên Job.
- Các JobParameter được đánh dấu là identifying.

Nếu thay đổi một identifying parameter, lần chạy sẽ thuộc JobInstance khác. Nếu chỉ thay đổi parameter không identifying, danh tính JobInstance vẫn giữ nguyên.

Thông thường, một JobInstance đã **COMPLETED** không thể được chạy lại với đúng bộ identifying parameters đó. Muốn thực hiện một lượt nghiệp vụ mới, hãy cung cấp identifying parameter mới, chẳng hạn mã kỳ xử lý hoặc ngày nghiệp vụ. **RunIdIncrementer** cũng có thể tạo tham số tăng dần để tạo JobInstance mới, nhưng không nên tăng run id khi mục đích thực sự là restart một JobInstance đang dang dở.

## 3. JobParameters: dữ liệu đầu vào và danh tính lần chạy

**JobParameters** là tập tham số được truyền khi khởi chạy Job. Chúng có thể chứa đường dẫn file, ngày xử lý, mã khách hàng, chế độ chạy hoặc các giá trị điều khiển khác.

Ví dụ tạo tham số:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/customer.csv", true)
        .addString("mode", "FULL", false)
        .toJobParameters();
~~~

Tham số thứ ba cho biết giá trị đó có tham gia xác định JobInstance hay không:

- **true**: identifying parameter.
- **false**: non-identifying parameter.

Trong ví dụ trên, **inputFile** tham gia xác định JobInstance. **mode** được lưu như tham số của lần chạy nhưng không làm thay đổi danh tính JobInstance.

Hãy chọn identifying parameters theo nghiệp vụ. Nếu mỗi file là một đơn vị xử lý độc lập, đường dẫn hoặc mã file có thể là identifying parameter. Nếu **mode** chỉ điều chỉnh cách xử lý trong cùng một đơn vị nghiệp vụ, nó có thể là non-identifying parameter. Cần bảo đảm việc restart vẫn dùng đúng các tham số cần thiết để tiếp tục công việc cũ.

## 4. Step: một đơn vị công việc trong Job

**Step** là một giai đoạn xử lý có thể theo dõi độc lập. Mỗi Step có thể thực hiện một tác vụ đơn giản hoặc xử lý dữ liệu theo từng nhóm bản ghi.

Ví dụ trong Job nhập khách hàng:

- **validateInputStep**: kiểm tra file và cấu trúc dữ liệu.
- **importCustomersStep**: đọc, chuyển đổi và ghi khách hàng.
- **createReportStep**: tổng hợp số bản ghi thành công và bị bỏ qua.

Spring Batch cung cấp nhiều kiểu Step. Hai kiểu phổ biến nhất khi bắt đầu là:

1. **Tasklet Step**: thực hiện một tác vụ được đóng gói trong Tasklet.
2. **Chunk-oriented Step**: xử lý dữ liệu theo từng chunk, thường kết hợp ItemReader, ItemProcessor và ItemWriter.

### 4.1. Tasklet Step

Tasklet phù hợp với công việc có logic tương đối gọn, không cần mô hình đọc và ghi từng item theo chunk. Ví dụ:

- Kiểm tra file tồn tại.
- Tạo thư mục làm việc.
- Xóa dữ liệu tạm.
- Gọi một thủ tục chuẩn bị dữ liệu.
- Tạo file báo cáo từ kết quả đã có.

Một Tasklet triển khai phương thức **execute**:

~~~java
@Bean
public Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("validateInputStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                // Thực hiện kiểm tra đầu vào tại đây.
                // Có thể ném exception nếu dữ liệu không hợp lệ.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
~~~

**RepeatStatus** cho biết Tasklet đã hoàn tất hay cần được gọi tiếp:

- **RepeatStatus.FINISHED**: Tasklet đã hoàn thành.
- **RepeatStatus.CONTINUABLE**: yêu cầu framework gọi lại Tasklet.

Mỗi lần gọi Tasklet được thực hiện trong transaction do Step sử dụng. Nếu Tasklet trả về **CONTINUABLE**, framework có thể gọi lại nó cho đến khi nhận **FINISHED** hoặc xảy ra lỗi. Vì vậy, Tasklet cần được thiết kế cẩn thận để không lặp lại một thao tác không an toàn.

### 4.2. Chunk-oriented Step

Chunk-oriented processing phù hợp khi cần xử lý nhiều bản ghi. Spring Batch chia dữ liệu thành các nhóm có kích thước cấu hình, xử lý nhóm đó rồi commit transaction.

Một chunk thường có ba thành phần:

- **ItemReader**: đọc một item tại một thời điểm.
- **ItemProcessor**: kiểm tra hoặc chuyển đổi item; có thể trả về null để lọc item khỏi kết quả ghi.
- **ItemWriter**: ghi các item đã được xử lý trong chunk.

Ví dụ cấu hình Step đọc và nhập dữ liệu khách hàng:

~~~java
@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawCustomer> customerReader,
        ItemProcessor<RawCustomer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<RawCustomer, Customer>chunk(100, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
~~~

Với chunk size là **100**, framework xử lý tối đa 100 item trong một chunk trước khi commit. Chunk cuối cùng có thể nhỏ hơn nếu nguồn dữ liệu đã hết.

Luồng xử lý cơ bản:

~~~text
ItemReader
    |
    v
ItemProcessor
    |
    v
Tập item của chunk
    |
    v
ItemWriter
    |
    v
Commit transaction
    |
    v
Đọc chunk tiếp theo
~~~

Một chu kỳ chunk thường diễn ra như sau:

1. Reader đọc từng item cho đến khi đủ kích thước chunk hoặc nguồn trả về null.
2. Processor xử lý từng item. Item bị lọc có thể được loại khỏi danh sách ghi bằng cách trả về null.
3. Writer nhận các item còn lại trong chunk và ghi chúng.
4. Khi xử lý chunk thành công, transaction được commit.
5. Framework tiếp tục chunk tiếp theo cho đến khi hết dữ liệu.

Chunk size ảnh hưởng đến hiệu năng, mức sử dụng bộ nhớ và phạm vi rollback. Chunk quá nhỏ có thể làm tăng số lần commit. Chunk quá lớn có thể giữ nhiều dữ liệu trong bộ nhớ và khiến transaction kéo dài. Hãy chọn kích thước dựa trên đặc tính dữ liệu, tài nguyên và khả năng của hệ thống đích.

### 4.3. Chọn Tasklet hay Chunk

| Tình huống | Cách triển khai thường phù hợp |
|---|---|
| Xóa file tạm hoặc tạo thư mục | Tasklet |
| Kiểm tra điều kiện đầu vào | Tasklet |
| Gọi một thủ tục chuẩn bị dữ liệu | Tasklet |
| Đọc hàng triệu dòng CSV | Chunk |
| Chuyển đổi từng bản ghi | Chunk |
| Ghi dữ liệu theo lô vào database | Chunk |
| Lọc hoặc kiểm tra từng item | Chunk với ItemProcessor |

Không nên ép mọi công việc vào chunk. Ngược lại, nếu xử lý tập dữ liệu lớn bằng một Tasklet duy nhất, bạn sẽ phải tự xây dựng nhiều cơ chế mà chunk processing đã cung cấp sẵn, chẳng hạn đọc theo lô, commit định kỳ và checkpoint.

## 5. StepExecution và trạng thái thực thi

Mỗi lần một Step được chạy trong một JobExecution, Spring Batch tạo một **StepExecution**. Đối tượng này lưu trạng thái và số liệu của lần chạy Step đó.

Một số thông tin thường gặp:

- **status**: trạng thái thực thi của Step.
- **exitStatus**: mã kết quả dùng trong điều phối flow.
- **readCount**: số item đã đọc.
- **writeCount**: số item đã ghi.
- **filterCount**: số item bị lọc.
- **readSkipCount**, **processSkipCount**, **writeSkipCount**: số item bị bỏ qua ở từng giai đoạn.
- **commitCount**: số lần commit.
- **rollbackCount**: số lần rollback.
- **startTime**, **endTime**, **lastUpdated**: mốc thời gian thực thi.
- **executionContext**: dữ liệu trạng thái của Step.

Các số liệu này hữu ích khi theo dõi tiến độ, điều tra lỗi hoặc xác định vì sao số lượng bản ghi đầu vào và đầu ra khác nhau.

### BatchStatus và ExitStatus

Hai loại trạng thái này có mục đích khác nhau:

- **BatchStatus** mô tả trạng thái thực thi ở cấp framework, ví dụ STARTING, STARTED, COMPLETED, FAILED, STOPPED hoặc ABANDONED.
- **ExitStatus** biểu diễn kết quả thoát của Job hoặc Step. Mã mặc định thường tương ứng với kết quả thực thi, nhưng ứng dụng có thể đặt mã riêng như NO_DATA, INVALID_INPUT hoặc COMPLETED_WITH_WARNINGS.

Điểm quan trọng: **flow transition dùng ExitStatus để quyết định nhánh tiếp theo**, còn BatchStatus phản ánh trạng thái thực thi tổng thể.

Ví dụ, một Step có thể hoàn thành về mặt kỹ thuật (BatchStatus **COMPLETED**) nhưng trả về ExitStatus tùy chỉnh **NO_DATA**. Job có thể dùng mã này để chuyển sang một Step xử lý trường hợp không có dữ liệu.

Không nên xem BatchStatus và ExitStatus là hai tên gọi thay thế cho cùng một giá trị.

## 6. Flow: điều phối thứ tự các Step

Flow mô tả đường đi của Job qua các Step. Spring Batch hỗ trợ flow tuyến tính, flow có điều kiện và flow song song.

### 6.1. Flow tuyến tính

Cấu hình tuyến tính dùng **start()** và **next()**:

~~~java
@Bean
public Job customerImportJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importCustomersStep,
        Step createReportStep) {

    return new JobBuilder("customerImportJob", jobRepository)
            .start(validateInputStep)
            .next(importCustomersStep)
            .next(createReportStep)
            .build();
}
~~~

Thứ tự là:

~~~text
validateInputStep
        |
        v
importCustomersStep
        |
        v
createReportStep
        |
        v
      End
~~~

Đây là lựa chọn dễ đọc khi mọi Step cần chạy theo một chuỗi cố định. Khi một Step thất bại, flow mặc định không tiếp tục như thể Step đó đã thành công.

### 6.2. Flow có điều kiện

Trong quy trình thực tế, Step tiếp theo có thể phụ thuộc vào kết quả của Step hiện tại. Dùng **on()** để khai báo transition theo ExitStatus.

Ví dụ: sau khi kiểm tra file, Job sẽ nhập dữ liệu nếu hợp lệ hoặc ghi nhận file bị từ chối nếu có lỗi nghiệp vụ:

~~~java
@Bean
public Job customerImportJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importCustomersStep,
        Step recordRejectedFileStep) {

    return new JobBuilder("customerImportJob", jobRepository)
            .start(validateInputStep)
                .on("COMPLETED").to(importCustomersStep)
            .from(validateInputStep)
                .on("INVALID_INPUT").to(recordRejectedFileStep)
            .from(validateInputStep)
                .on("*").fail()
            .end()
            .build();
}
~~~

Ý nghĩa:

- **on("COMPLETED")**: nếu Step kiểm tra có ExitStatus COMPLETED, chuyển sang Step nhập dữ liệu.
- **on("INVALID_INPUT")**: nếu Step kiểm tra trả về mã kết quả tùy chỉnh này, chuyển sang Step ghi nhận file bị từ chối.
- **on("*")**: mẫu ký tự đại diện cho các ExitStatus còn lại; ở đây Job kết thúc theo nhánh thất bại.
- **from(validateInputStep)**: khai báo thêm transition xuất phát từ cùng Step.
- **to(...)**: chuyển sang Step hoặc thành phần flow tiếp theo.
- **fail()**: kết thúc Job theo trạng thái thất bại.
- **end()**: hoàn tất cấu hình flow.

Để transition INVALID_INPUT hoạt động, Step kiểm tra phải thực sự tạo ExitStatus tương ứng. Có thể thực hiện điều đó bằng logic của Step hoặc listener, chẳng hạn **StepExecutionListener.afterStep**. Chỉ đặt một chuỗi trong cấu hình flow không tự làm Step phát ra mã kết quả đó.

Mẫu **on()** khớp với ExitStatus exit code, không phải tên của BatchStatus. Vì vậy, khi debug một nhánh không chạy như mong đợi, hãy kiểm tra **StepExecution.getExitStatus()** trước.

Các transition phải được khai báo đủ để xử lý những kết quả mà Step có thể trả về. Nếu một kết quả không khớp transition nào, flow có thể không đi theo nhánh bạn dự kiến.

### 6.3. Các kiểu kết thúc transition

Một số lựa chọn thường dùng trong flow:

| Cấu hình | Ý nghĩa |
|---|---|
| **to(step)** | Chuyển sang Step hoặc Flow tiếp theo |
| **end()** | Kết thúc Job theo nhánh kết thúc thành công |
| **fail()** | Kết thúc Job với trạng thái thất bại |
| **stopAndRestart(step)** | Dừng Job và chỉ định nơi tiếp tục khi Job được restart |

**stopAndRestart** hữu ích khi quy trình cần tạm dừng có chủ đích, ví dụ chờ một công việc bên ngoài hoàn tất trước khi tiếp tục. Cần phân biệt trạng thái dừng có chủ đích với trạng thái lỗi: chúng có cách vận hành và restart khác nhau.

## 7. JobExecutionDecider: quyết định nhánh bằng logic

Transition theo ExitStatus phù hợp khi kết quả của Step đã đủ để chọn nhánh. Khi cần quyết định dựa trên JobParameters, trạng thái tổng hợp hoặc dữ liệu nghiệp vụ, có thể dùng **JobExecutionDecider**.

Decider nhận **JobExecution** và **StepExecution**, sau đó trả về **FlowExecutionStatus**:

~~~java
@Bean
public JobExecutionDecider importModeDecider() {
    return (jobExecution, stepExecution) -> {
        String mode = jobExecution.getJobParameters().getString("mode");

        if ("FULL".equals(mode)) {
            return new FlowExecutionStatus("FULL");
        }

        return new FlowExecutionStatus("DELTA");
    };
}
~~~

Có thể nối Decider vào Job:

~~~java
@Bean
public Job customerImportJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step fullImportStep,
        Step deltaImportStep,
        JobExecutionDecider importModeDecider) {

    return new JobBuilder("customerImportJob", jobRepository)
            .start(validateInputStep)
            .next(importModeDecider)
            .from(importModeDecider).on("FULL").to(fullImportStep)
            .from(importModeDecider).on("DELTA").to(deltaImportStep)
            .end()
            .build();
}
~~~

Ở đây:

1. Job chạy **validateInputStep**.
2. Decider đọc parameter **mode**.
3. Nếu mode là FULL, flow chuyển sang **fullImportStep**.
4. Với trường hợp còn lại, flow chuyển sang **deltaImportStep**.

**FlowExecutionStatus** của Decider được dùng để khớp các transition bắt đầu từ Decider. Nó có vai trò tương tự một kết quả điều phối riêng cho flow; không nên nhầm nó với BatchStatus hoặc ExitStatus của Step.

Hãy giữ logic quyết định trong Decider ở mức điều phối. Phần xử lý dữ liệu lớn hoặc cập nhật nghiệp vụ nên được đặt trong Step chuyên trách để dễ theo dõi và restart.

## 8. Flow song song

Một Job có thể chạy các nhánh độc lập song song bằng **split()** và **TaskExecutor**.

Ví dụ, sau khi chuẩn bị dữ liệu, hai nhánh độc lập có thể lần lượt tạo chỉ mục tìm kiếm và tổng hợp số liệu. Nếu không có phụ thuộc dữ liệu giữa hai nhánh, chúng có thể chạy đồng thời.

~~~java
@Bean
public Job parallelJob(
        JobRepository jobRepository,
        Flow indexingFlow,
        Flow reportingFlow,
        TaskExecutor taskExecutor) {

    return new JobBuilder("parallelJob", jobRepository)
            .start(indexingFlow)
            .split(taskExecutor)
            .add(reportingFlow)
            .end()
            .build();
}
~~~

**indexingFlow** và **reportingFlow** là các Flow đã được định nghĩa riêng. **TaskExecutor** cung cấp cơ chế thực thi bất đồng bộ cho các nhánh trong split.

Khi thiết kế flow song song, cần chú ý:

- Chỉ chạy song song những nhánh không phụ thuộc kết quả tức thời của nhau.
- Kiểm tra reader, writer, service và tài nguyên dùng chung có an toàn khi nhiều thread truy cập hay không.
- Tránh để hai nhánh ghi đồng thời vào cùng một tập dữ liệu nếu không có cơ chế đồng bộ hoặc phân vùng phù hợp.
- Xem xét giới hạn kết nối database, dung lượng thread pool và tải của hệ thống đích.
- Thiết kế xử lý lỗi và khả năng chạy lại cho từng nhánh.

Song song hóa có thể rút ngắn thời gian xử lý, nhưng không tự động làm cho các thao tác dùng chung trở nên an toàn. Nếu dữ liệu cần được chia thành các phần độc lập để xử lý trên nhiều worker, hãy tìm hiểu thêm về partitioning. Nếu cần truyền các nhóm dữ liệu giữa các tiến trình, remote chunking là một mô hình khác cần cân nhắc.

## 9. Vòng đời thực thi của Job và Step

Khi ứng dụng yêu cầu chạy một Job, luồng xử lý ở mức khái niệm diễn ra như sau:

~~~text
Ứng dụng / Scheduler
        |
        v
    JobLauncher
        |
        v
    JobRepository
  tạo JobExecution
        |
        v
     Job chạy
        |
        v
  Điều phối Flow
        |
        v
  Tạo StepExecution
        |
        v
     Step chạy
        |
        +---- cập nhật trạng thái, số liệu,
        |     ExecutionContext và checkpoint
        |
        v
  Chọn transition tiếp theo
        |
        +----> Step tiếp theo
        |
        +----> Nhánh khác / Decider
        |
        v
    Job kết thúc
        |
        v
  Lưu trạng thái cuối
~~~

Các bước chính:

1. Ứng dụng hoặc scheduler gọi **JobLauncher** với Job và JobParameters.
2. **JobRepository** kiểm tra danh tính JobInstance, trạng thái các lần chạy trước và điều kiện khởi động.
3. Spring Batch tạo **JobExecution** cho lần chạy mới.
4. Job bắt đầu flow và xác định Step cần chạy.
5. Framework tạo **StepExecution** cho Step đó.
6. Step thực hiện Tasklet hoặc chunk processing. Trong quá trình này, framework cập nhật metadata, số liệu và checkpoint.
7. Khi Step kết thúc, flow dùng kết quả thực thi để chọn transition tiếp theo.
8. Khi không còn Step nào cần chạy, Job lưu trạng thái kết thúc.

**JobRepository** là trung tâm quản lý metadata của quá trình này. Với repository dựa trên database, metadata thường được lưu trong các bảng như:

- **BATCH_JOB_INSTANCE**
- **BATCH_JOB_EXECUTION**
- **BATCH_JOB_EXECUTION_PARAMS**
- **BATCH_STEP_EXECUTION**
- **BATCH_JOB_EXECUTION_CONTEXT**
- **BATCH_STEP_EXECUTION_CONTEXT**

Các bảng này phục vụ việc theo dõi lịch sử chạy, xác định JobInstance, kiểm tra trạng thái và khôi phục checkpoint. Chúng không thay thế bảng dữ liệu nghiệp vụ của ứng dụng.

## 10. ExecutionContext và khả năng restart

Một lợi ích quan trọng của Spring Batch là khả năng tiếp tục Job sau khi bị lỗi hoặc dừng. Để làm được điều đó, framework cần lưu trạng thái thực thi.

**ExecutionContext** là vùng lưu key-value gắn với JobExecution hoặc StepExecution:

- **Job ExecutionContext**: lưu trạng thái cần chia sẻ giữa các Step trong cùng một lần chạy Job.
- **Step ExecutionContext**: lưu trạng thái riêng của Step, thường dùng cho checkpoint của reader hoặc writer.

Ví dụ, một reader đọc file lớn có thể lưu vị trí hoặc số dòng đã xử lý. Nếu Job bị lỗi sau một số chunk đã commit, lần restart có thể mở lại reader từ checkpoint phù hợp thay vì bắt đầu lại toàn bộ file.

Các thành phần cần duy trì trạng thái thường sử dụng hợp đồng **ItemStream**:

- **open(executionContext)**: khôi phục hoặc khởi tạo trạng thái khi Step bắt đầu.
- **update(executionContext)**: ghi trạng thái hiện tại vào ExecutionContext tại checkpoint.
- **close()**: giải phóng tài nguyên khi kết thúc.

Nhiều reader và writer có sẵn trong Spring Batch đã hỗ trợ lưu trạng thái. Với thành phần tự viết, hãy triển khai ItemStream khi cần lưu và khôi phục tiến độ. Chỉ ghi vào ExecutionContext những dữ liệu cần thiết để tiếp tục công việc; tránh lưu đối tượng lớn hoặc dữ liệu nghiệp vụ không liên quan.

### Điều kiện để restart đúng

Restart không đơn giản là gọi Job lại với bất kỳ tham số nào. Cần giữ đúng danh tính JobInstance và bảo đảm các thành phần xử lý có thể khôi phục trạng thái.

Một số điểm cần nhớ:

1. Dùng lại cùng identifying JobParameters khi muốn restart JobInstance cũ.
2. JobInstance đã hoàn tất thường không được chạy lại với cùng identifying parameters.
3. Khi Job thất bại, các Step đã hoàn thành thường được bỏ qua trong lần restart.
4. Có thể cấu hình **allowStartIfComplete(true)** cho Step cần chạy lại ngay cả khi Step đó đã hoàn thành ở lần trước.
5. **startLimit** giới hạn số lần một Step được phép bắt đầu.
6. **preventRestart()** trên Job dùng khi muốn Job không cho phép restart.
7. Reader, writer và thao tác nghiệp vụ cần có chiến lược khôi phục hoặc tính idempotent phù hợp.

Ví dụ cấu hình một Step được phép chạy lại dù đã hoàn thành ở lần thực thi trước:

~~~java
@Bean
public Step refreshReferenceDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("refreshReferenceDataStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                // Làm mới dữ liệu tham chiếu.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
~~~

Chỉ bật **allowStartIfComplete(true)** khi việc chạy lại Step là có chủ đích và an toàn. Nếu Step gửi email, trừ tiền hoặc tạo giao dịch bên ngoài, chạy lại có thể gây tác dụng phụ trùng lặp.

### Restart và tính idempotent

Spring Batch quản lý metadata, transaction và checkpoint, nhưng không thể tự bảo đảm mọi tác động bên ngoài chỉ xảy ra một lần.

Ví dụ, một Step gọi API của hệ thống khác rồi ứng dụng bị dừng trước khi metadata được cập nhật. Khi restart, API có thể được gọi lần nữa. Hệ thống nên có cơ chế chống trùng như idempotency key, mã giao dịch duy nhất hoặc kiểm tra trạng thái trước khi ghi.

Với chunk processing, dữ liệu trong một chunk chưa commit có thể được xử lý lại sau rollback hoặc restart. Vì vậy, reader, processor và writer cần được thiết kế phù hợp với ranh giới transaction. Không nên giả định mọi thao tác ngoài transaction database sẽ tự động được rollback cùng transaction của Step.

## 11. Những nhầm lẫn thường gặp

### Nhầm Job với JobExecution

Job là định nghĩa cấu hình. JobExecution là một lần thực thi cụ thể. Một Job definition có thể tạo nhiều JobInstance, và một JobInstance có thể có nhiều JobExecution khi được restart sau lỗi hoặc dừng.

### Nhầm Step với một phương thức Java

Step là đơn vị thực thi do Spring Batch quản lý. Bên trong Step có thể gọi nhiều service hoặc phương thức Java, nhưng Step còn có metadata, transaction boundary, listener, trạng thái và khả năng restart.

### Nghĩ rằng next() xử lý mọi nhánh lỗi

**next()** phù hợp với flow tuyến tính. Khi cần chọn Step tiếp theo dựa trên kết quả, hãy khai báo transition theo ExitStatus hoặc dùng Decider. Đừng giả định một Step thất bại vẫn tự động chuyển sang Step kế tiếp.

### Dùng BatchStatus để khai báo on()

**on()** khớp ExitStatus. Nếu một Step có BatchStatus COMPLETED nhưng ExitStatus NO_DATA, transition **on("COMPLETED")** sẽ không khớp với kết quả đó. Hãy kiểm tra cả hai loại trạng thái khi điều tra flow.

### Dùng JobParameters mới khi muốn restart

Thay đổi identifying parameter sẽ tạo JobInstance khác. Nếu mục tiêu là tiếp tục JobInstance cũ, hãy dùng lại identifying parameters và để Spring Batch xử lý lịch sử thực thi cùng checkpoint.

### Xem chunk size là số bản ghi chắc chắn được ghi

Chunk size là số item được gom trong một đơn vị xử lý. Processor có thể lọc item bằng cách trả về null; skip policy cũng có thể bỏ qua item lỗi. Do đó, số item đọc, xử lý và ghi có thể khác nhau.

### Cho các nhánh song song ghi vào cùng tài nguyên mà không kiểm soát

Các flow song song có thể truy cập database, file hoặc API cùng lúc. Cần thiết kế tính an toàn luồng, khóa, phân vùng hoặc cơ chế chống ghi trùng trước khi tăng mức song song.

## 12. Gợi ý thiết kế một Job dễ vận hành

Khi bắt đầu thiết kế Job, hãy xác định đơn vị nghiệp vụ mà Job đại diện và bộ tham số nhận diện một lần xử lý. Sau đó chia quy trình thành các Step có trách nhiệm rõ ràng.

Một số nguyên tắc thực tế:

- Đặt tên Job và Step theo hành động nghiệp vụ, ví dụ customerImportJob, validateInputStep, importCustomersStep.
- Giữ mỗi Step tập trung vào một công đoạn để dễ theo dõi và xử lý lỗi.
- Dùng Tasklet cho tác vụ đơn lẻ; dùng chunk processing cho dữ liệu cần đọc, xử lý và ghi theo lô.
- Chọn chunk size theo kích thước dữ liệu và đặc tính transaction.
- Dùng ExitStatus tùy chỉnh hoặc Decider khi flow cần rẽ nhánh theo kết quả nghiệp vụ.
- Lưu checkpoint cần thiết trong ExecutionContext để hỗ trợ restart.
- Thiết kế thao tác bên ngoài database có khả năng chống thực hiện trùng.
- Chỉ chạy song song những nhánh độc lập và có thể chia sẻ tài nguyên một cách an toàn.
- Theo dõi JobExecution và StepExecution để hiểu kết quả, số liệu và nguyên nhân lỗi.

Khi đọc một cấu hình Spring Batch, hãy lần lượt tìm Job được khai báo ở đâu, Step đầu tiên là gì, mỗi Step sử dụng Tasklet hay chunk processing, các transition dựa trên ExitStatus nào và JobRepository lưu metadata ra sao. Những câu hỏi này giúp bạn lần theo toàn bộ đường đi của một Job từ lúc được khởi chạy đến khi hoàn tất hoặc cần restart.

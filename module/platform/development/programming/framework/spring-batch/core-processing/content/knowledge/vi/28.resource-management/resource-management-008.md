# Tên output theo job instance

Trong Spring Batch, một JobInstance đại diện cho một lần xử lý logic với một bộ identifying JobParameters. Một JobInstance có thể có nhiều JobExecution khi lần chạy trước thất bại hoặc bị dừng rồi được restart. Khi tạo file output, cần quyết định tên file gắn với JobInstance hay từng JobExecution.

Nếu mục tiêu là restart và tiếp tục cùng một kết quả, tên output nên ổn định theo JobInstance. Lần restart sẽ dùng lại cùng JobInstance ID và cùng đường dẫn output, nhờ đó writer có thể khôi phục checkpoint đã lưu. Nếu tên file chứa JobExecution ID hoặc timestamp mới mỗi lần launch, mỗi lần restart có thể tạo một file khác và làm kết quả bị chia thành nhiều phần.

## 1. JobInstance và JobExecution khác nhau thế nào?

JobInstance đại diện cho một đơn vị công việc logic. Nó được xác định bởi tên Job và các JobParameters được đánh dấu identifying.

JobExecution là một lần thực thi cụ thể của JobInstance. Khi Job thất bại và được restart, Spring Batch tạo JobExecution mới nhưng vẫn thuộc JobInstance cũ.

~~~text
Job: exportOrders
Identifying parameters:
  businessDate = 2026-11-15
  sourceBatch = 8421
            |
            v
       JobInstance 52
            |
       +----+----+
       |         |
       v         v
  Execution 90  Execution 94
     FAILED      COMPLETED
       |         ^
       +---------+
          restart
~~~

Trong ví dụ, Execution 90 và 94 là hai lần chạy của cùng JobInstance 52. JobInstance ID giữ nguyên giữa các lần restart; JobExecution ID thay đổi theo từng lần thực thi.

Sự khác biệt này quyết định cách đặt tên output:

- Dùng JobInstance ID nếu muốn một file logic cho toàn bộ vòng đời xử lý, bao gồm restart.
- Dùng JobExecution ID nếu cố ý muốn mỗi lần thực thi tạo một artifact riêng, chẳng hạn file chẩn đoán hoặc file staging theo attempt.
- Dùng identifying business key nếu tên file cần dễ đọc và ổn định theo nghiệp vụ, đồng thời phải bảo đảm key duy nhất và an toàn cho tên file.

## 2. Vì sao output nên gắn với JobInstance?

Một Job có thể đọc dữ liệu, tổng hợp và tạo file báo cáo. Nếu lần đầu xử lý được một số chunk rồi thất bại, restart cần tiếp tục cùng công việc. Khi đó writer phải mở đúng file đã tạo và khôi phục vị trí ghi đã lưu.

Ví dụ tên file theo JobInstance:

~~~text
orders-job-52.csv
~~~

Lần chạy đầu và lần restart đều dùng file này:

~~~text
JobExecution 90 (FAILED)
  -> ghi một số chunk vào orders-job-52.csv

JobExecution 94 (RESTART)
  -> mở lại orders-job-52.csv
  -> khôi phục writer checkpoint
  -> ghi tiếp phần còn lại
~~~

Nếu thay bằng tên dựa trên JobExecution ID:

~~~text
orders-execution-90.csv
orders-execution-94.csv
~~~

thì lần restart có thể tạo file mới. File đầu chứa phần dữ liệu đã ghi ở lần trước, file thứ hai chứa phần còn lại; downstream phải tự ghép và đối soát. Đây thường không phải hành vi mong muốn khi restart cùng JobInstance.

Tên output theo JobInstance giúp một đơn vị công việc logic có một đường dẫn ổn định. Nó cũng giúp người vận hành tra file từ JobInstance ID trong JobRepository.

## 3. Chọn thành phần dùng để tạo tên output

Có một số lựa chọn thường gặp:

| Thành phần tên | Ổn định khi restart cùng JobInstance? | Phù hợp khi |
|---|---|---|
| JobInstance ID | Có | Cần định danh duy nhất theo repository |
| JobExecution ID | Không | Muốn artifact riêng cho mỗi attempt |
| Identifying business parameter | Có nếu giữ nguyên | Muốn tên file có ý nghĩa nghiệp vụ |
| Non-identifying parameter | Không bảo đảm | Chỉ dùng làm metadata phụ, không định danh output |
| Timestamp tạo ở mỗi lần launch | Không | Muốn file riêng cho mỗi lần chạy mới, không dùng cho restart |
| UUID sinh mới ở mỗi lần launch | Không | Tạo artifact độc lập, không cần tiếp tục checkpoint |

JobInstance ID thường là lựa chọn đơn giản khi tên file chỉ cần duy nhất trong phạm vi JobRepository. Giá trị này do repository cấp sau khi JobInstance được tạo.

Có thể kết hợp ID với tên Job hoặc business date để dễ đọc:

~~~text
exportOrders-20261115-instance-52.csv
~~~

Nếu dùng business key làm tên chính, cần xác định key có thực sự unique hay không. Ví dụ chỉ dùng ngày có thể gây trùng nếu cùng ngày có nhiều nguồn dữ liệu hoặc nhiều tenant. Có thể kết hợp ngày với source batch ID hoặc JobInstance ID.

## 4. Lấy JobInstance ID trong lúc Job chạy

JobInstance đã được tạo trước khi JobExecution bắt đầu các Step. Vì vậy, khi beforeJob được gọi, ứng dụng có thể lấy ID từ JobExecution:

~~~java
long jobInstanceId =
        jobExecution.getJobInstance().getInstanceId();
~~~

Có thể tạo tên file và lưu đường dẫn vào Job ExecutionContext. Cách này giúp reader/writer ở Step sau nhận đường dẫn bằng late binding.

Ví dụ listener:

~~~java
public class OutputPathJobListener implements JobExecutionListener {

    private final Path outputDirectory;

    public OutputPathJobListener(Path outputDirectory) {
        this.outputDirectory =
                outputDirectory.toAbsolutePath().normalize();
    }

    @Override
    public void beforeJob(JobExecution jobExecution) {
        try {
            Files.createDirectories(outputDirectory);
        } catch (IOException exception) {
            throw new IllegalStateException(
                    "Cannot create batch output directory",
                    exception);
        }

        long instanceId =
                jobExecution.getJobInstance().getInstanceId();

        String fileName = "orders-" + instanceId + ".csv";
        Path outputPath =
                outputDirectory.resolve(fileName).normalize();

        if (!outputPath.startsWith(outputDirectory)) {
            throw new IllegalStateException(
                    "Output path is outside the configured directory");
        }

        jobExecution.getExecutionContext().putString(
                "orders.output.path",
                outputPath.toString());
    }
}
~~~

Listener dùng JobInstance ID nên khi restart cùng instance sẽ tính lại đúng tên file. Giá trị đường dẫn cũng được đặt vào Job ExecutionContext để các Step có thể sử dụng.

Đường dẫn thư mục nên đến từ cấu hình ứng dụng hoặc một nguồn tin cậy. Không nối trực tiếp một chuỗi tùy ý do người dùng cung cấp vào tên file mà không kiểm tra, vì các ký tự như ../ có thể làm đường dẫn thoát khỏi thư mục output dự kiến.

## 5. Đăng ký listener trên Job

Khai báo listener như một bean và đăng ký trên JobBuilder:

~~~java
@Bean
OutputPathJobListener outputPathJobListener(Environment environment) {
    String directory =
            environment.getRequiredProperty("batch.output.directory");
    return new OutputPathJobListener(Paths.get(directory));
}

@Bean
Job exportOrdersJob(
        JobRepository jobRepository,
        OutputPathJobListener outputPathJobListener,
        Step exportOrdersStep) {

    return new JobBuilder("exportOrdersJob", jobRepository)
            .listener(outputPathJobListener)
            .start(exportOrdersStep)
            .build();
}
~~~

beforeJob chạy sau khi JobExecution đã được tạo và trước khi các Step thực hiện. Đây là thời điểm phù hợp để tạo metadata runtime gắn với JobInstance.

Trong ví dụ, listener chỉ tính đường dẫn và ghi vào Job ExecutionContext. File thực tế được mở bởi writer trong Step. Tách việc xác định tên khỏi việc ghi file giúp Job orchestration không phải tự quản lý nội dung output.

Khi restart, beforeJob chạy lại cho JobExecution mới. Vì JobInstance ID không đổi nên đường dẫn được tính lại giống lần đầu. Không sinh UUID hoặc timestamp mới trong listener nếu output phải được tiếp tục trên cùng file.

## 6. Dùng Job ExecutionContext để truyền output path

Reader/writer step-scoped có thể nhận đường dẫn từ Job ExecutionContext qua SpEL:

~~~java
@Value("#{jobExecutionContext['orders.output.path']}")
String outputPath
~~~

Job ExecutionContext phù hợp với giá trị runtime cần chia sẻ giữa các Step trong cùng JobExecution. Trong ví dụ này, orders.output.path là metadata nhỏ, còn nội dung file được lưu trên filesystem.

Nếu output path cần được giữ nguyên qua restart, listener có thể tính lại từ JobInstance ID như trên. Có thể lưu thêm các trường như output version hoặc format để kiểm tra khi mở lại file.

Không lưu nội dung file hoặc danh sách record vào ExecutionContext. Context nên chứa đường dẫn, mã batch, version hay checksum; dữ liệu output nằm trong file hoặc storage chuyên dụng.

## 7. Khai báo writer step-scoped theo output path

Writer cần được tạo khi StepExecution đã hoạt động để có thể đọc giá trị trong Job ExecutionContext.

Ví dụ FlatFileItemWriter:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobExecutionContext['orders.output.path']}")
        String outputPath) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("ordersWriter")
            .resource(new FileSystemResource(outputPath))
            .delimited()
            .names("id", "customerId", "amount")
            .saveState(true)
            .build();
}
~~~

Các điểm quan trọng:

- @StepScope bật late binding để lấy output path khi Step chạy.
- name("ordersWriter") cung cấp tên ổn định cho writer state trong ExecutionContext.
- resource(...) trỏ tới file được định danh bởi JobInstance.
- saveState(true) cho phép writer lưu checkpoint cần thiết cho restart.

Tên writer cũng nên giữ ổn định qua các lần triển khai nếu cần restart từ metadata cũ. Đổi tên component có thể làm thay đổi key mà writer dùng trong ExecutionContext.

Không tạo writer bằng new ở trong processor hoặc tasklet để né scope. Hãy để Spring quản lý bean, target instance và lifecycle của ItemStream.

## 8. Gắn writer vào Step và Job

Step dùng writer đã được khai báo step-scoped:

~~~java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        FlatFileItemWriter<Order> orderWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, Order>chunk(500, transactionManager)
            .reader(orderReader)
            .writer(orderWriter)
            .build();
}
~~~

Job đăng ký listener để xác định đường dẫn trước khi Step bắt đầu:

~~~java
@Bean
Job exportOrdersJob(
        JobRepository jobRepository,
        OutputPathJobListener outputPathJobListener,
        Step exportOrdersStep) {

    return new JobBuilder("exportOrdersJob", jobRepository)
            .listener(outputPathJobListener)
            .start(exportOrdersStep)
            .build();
}
~~~

Step definition có thể là singleton vì reader/writer được inject dưới dạng scoped proxy. Target writer thực tế được tạo trong Step scope với output path của JobExecution hiện tại.

Nếu Job có nhiều Step ghi các file khác nhau, có thể lưu nhiều key trong Job ExecutionContext, ví dụ orders.output.path, summary.output.path và rejects.output.path. Mỗi writer step-scoped nhận đúng key tương ứng.

## 9. Tên output phải ổn định qua restart

Restart tạo JobExecution mới cho cùng JobInstance. Do đó, đường dẫn output được dùng trong lần restart phải giống đường dẫn ở lần chạy đầu.

Các yếu tố cần giữ ổn định:

- Job name và identifying JobParameters của JobInstance.
- Cách tính tên file từ JobInstance ID hoặc business key.
- Output directory và quy tắc chuẩn hóa đường dẫn.
- Tên writer dùng để lưu checkpoint.
- Format và schema của file.
- Dữ liệu nguồn mà writer đang xuất.
- Cấu hình writer liên quan đến append, restart và state.

Ví dụ:

~~~text
Lần đầu:
  JobInstance ID = 52
  output = /batch/output/orders-52.csv

Restart:
  JobInstance ID = 52
  output = /batch/output/orders-52.csv

Lần chạy logic mới:
  JobInstance ID = 53
  output = /batch/output/orders-53.csv
~~~

Nếu output directory thay đổi giữa lần đầu và restart, writer có thể mở một file mới trong khi ExecutionContext chứa checkpoint của file cũ. Hãy cấu hình directory ổn định hoặc lưu đường dẫn đã chọn trong metadata bền vững và kiểm tra nó trước khi tiếp tục.

## 10. Không dùng JobExecution ID nếu muốn một file cho toàn JobInstance

JobExecution ID thay đổi sau mỗi lần restart. Vì vậy, dùng nó trong tên file sẽ tạo một output khác cho mỗi attempt.

Ví dụ:

~~~text
orders-execution-90.csv
orders-execution-94.csv
~~~

Cách này phù hợp khi muốn lưu lại artifact riêng cho từng attempt, ví dụ:
- Lưu snapshot đầu ra của mỗi lần chạy để điều tra.
- Tạo file staging độc lập trước khi xác nhận kết quả.
- Giữ lại output của lần chạy lỗi để phân tích.
- Muốn so sánh các lần thực thi khác nhau.

Nhưng nếu writer phải tiếp tục file đã ghi dở, tên theo JobExecution ID là không phù hợp. Khi restart, JobExecution mới sẽ trỏ tới file khác và checkpoint của writer không còn khớp với resource đó.

Có thể dùng hai cấp tên nếu cần cả hai mục tiêu:
- Working file theo JobInstance để restart.
- Log hoặc audit record theo JobExecution để phân biệt từng attempt.

## 11. Identifying JobParameters và tên file theo nghiệp vụ

Có thể tạo tên file từ identifying JobParameters thay vì ID số của JobInstance. Ví dụ:

~~~text
orders-20261115-source-8421.csv
~~~

Cách này làm tên file dễ hiểu hơn với người vận hành. Tuy nhiên, cần bảo đảm các parameter tạo nên tên file thực sự identifying và đủ để phân biệt các JobInstance.

Ví dụ JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("sourceBatchId", 8421L, true)
        .toJobParameters();
~~~

Tên file có thể được tạo từ hai giá trị này nếu chúng đã được chuẩn hóa. Một JobInstance khác phải có businessDate hoặc sourceBatchId khác theo quy tắc nghiệp vụ.

Không dùng non-identifying parameter để tạo một output path có thể thay đổi giữa các lần restart. Parameter đó không tạo JobInstance mới; do vậy hai lần launch có thể được xem là cùng instance nhưng lại ghi vào hai file khác nhau.

Nếu muốn đơn giản hóa tính duy nhất, dùng JobInstance ID làm phần định danh chính và thêm business date đã được format để người vận hành dễ đọc.

## 12. Chuẩn hóa và bảo vệ tên file

Tên file thường được tạo từ Job name, business key, tenant hoặc parameter do caller truyền. Cần giới hạn ký tự và đường dẫn để tránh va chạm hoặc truy cập ngoài thư mục dự kiến.

Một số nguyên tắc:

- Dùng JobInstance ID số làm thành phần duy nhất.
- Chuẩn hóa business date theo một format cố định, chẳng hạn yyyyMMdd.
- Chỉ cho phép tập ký tự an toàn trong tenant code hoặc source key.
- Không dùng nguyên chuỗi path do caller truyền nếu không kiểm tra.
- Chuẩn hóa đường dẫn bằng Path.normalize() và kiểm tra nó vẫn nằm trong output directory.
- Phân tách thư mục theo môi trường hoặc tenant nếu các repository khác nhau có thể tạo cùng ID.
- Giữ extension và file format nhất quán.

Ví dụ tên file:

~~~text
/batch/output/
  orders-20261115-instance-52.csv
  orders-20261116-instance-53.csv
~~~

Nếu JobInstance ID chỉ unique trong một JobRepository, không nên giả định ID đó unique toàn công ty hoặc trên mọi môi trường. Có thể thêm tên Job, environment hoặc tenant đã chuẩn hóa vào path.

## 13. Output directory và nhiều môi trường chạy

Một ứng dụng có thể chạy trên development, staging và production. Nếu cùng một filesystem hoặc object storage được chia sẻ, tên file chỉ có JobInstance ID có thể trùng giữa hai repository độc lập.

Ví dụ:

~~~text
/batch/dev/exportOrders/instance-52.csv
/batch/prod/exportOrders/instance-52.csv
~~~

Nên tổ chức output directory theo:
- Environment.
- Tên Job.
- Tenant hoặc business domain nếu cần cô lập.
- JobInstance ID hoặc identifying business key.

Đường dẫn gốc nên được cấu hình qua property:

~~~properties
batch.output.directory=/var/app/batch/output
~~~

Không hard-code đường dẫn tuyệt đối vào writer. Điều đó giúp triển khai cùng Job trên nhiều môi trường mà vẫn giữ được quy tắc tên file.

Nếu output nằm trên shared filesystem hoặc object storage, kiểm tra quyền đọc/ghi, tính nhất quán, khả năng rename và chính sách retention của storage đó.

## 14. Restart writer và checkpoint của file

FlatFileItemWriter triển khai ItemStream nên có thể lưu state vào Step ExecutionContext. Khi Step restart, writer dùng state đã lưu để tiếp tục resource tương ứng.

Để cơ chế này hoạt động:

- Writer cần có tên ổn định.
- Resource path phải giống lần chạy trước.
- saveState(true) phải được bật nếu cần checkpoint.
- File đã ghi dở cần còn tồn tại.
- Không xóa file hoặc tạo file rỗng trước khi writer khôi phục state.
- Không thay đổi format hoặc thứ tự dữ liệu giữa các lần restart.

Writer có thể lưu số dòng hoặc thông tin cần thiết để biết vị trí đã ghi. Khi mở lại trong chế độ restart, implementation sẽ dùng ExecutionContext để khôi phục trạng thái. Không tự append thủ công ngoài lifecycle của writer nếu không hiểu checkpoint, vì có thể ghi lặp dữ liệu hoặc tạo file không khớp metadata.

Nếu dùng custom writer, cần triển khai ItemStream và lưu checkpoint vào Step ExecutionContext. @StepScope chỉ quản lý target instance; nó không tự lưu trạng thái writer.

## 15. File output đã tồn tại: overwrite, append hay restart?

Cần phân biệt ba tình huống:

1. **JobInstance mới:** file theo ID mới thường chưa tồn tại; writer tạo output mới.
2. **Restart cùng JobInstance:** file có thể đã chứa dữ liệu từ các chunk commit trước; writer cần khôi phục checkpoint và tiếp tục.
3. **Chạy lại có chủ đích với JobInstance mới:** tạo output khác để giữ kết quả của lần xử lý logic mới.

Không đặt một chính sách overwrite/append chung cho mọi trường hợp mà không xét restart. Với FlatFileItemWriter, các thuộc tính như append, shouldDeleteIfExists và saveState có ý nghĩa khác nhau. Hãy dựa vào hành vi restart của writer và kiểm thử với JobRepository thật; đừng xóa file cũ trước khi framework đọc checkpoint.

Nếu file cùng JobInstance đã tồn tại nhưng không có checkpoint tương ứng, đó có thể là file orphan do process dừng ngoài lifecycle hoặc metadata không đồng bộ. Không tự động append vào file đó. Cần đối chiếu JobExecution/StepExecution, xác định dữ liệu đã commit đến đâu và áp dụng quy trình phục hồi.

## 16. Dùng file staging và chỉ publish sau khi Job thành công

Nếu downstream không được phép nhìn thấy file chưa hoàn chỉnh, có thể ghi vào file staging theo JobInstance rồi publish sau khi mọi Step cần thiết hoàn thành.

Ví dụ:

~~~text
/batch/staging/orders-instance-52.part
               |
               | writer ghi và có thể restart
               v
         Job hoàn thành
               |
               | bước publish cuối
               v
/batch/published/orders-instance-52.csv
~~~

Cách làm:

1. Writer ghi vào đường dẫn staging ổn định theo JobInstance.
2. Restart tiếp tục file staging bằng checkpoint.
3. Một Step cuối kiểm tra file, số record và checksum.
4. Step publish di chuyển hoặc copy file sang thư mục published.
5. Downstream chỉ đọc thư mục published hoặc manifest đã xác nhận.

Nếu staging và published nằm trên cùng filesystem, atomic move có thể giúp consumer không nhìn thấy file đang được chuyển dở, tùy filesystem và cách triển khai. Với object storage, rename thường không phải thao tác atomic; có thể cần copy rồi cập nhật manifest hoặc trạng thái publication.

Nên dùng một Step publish riêng thay vì làm side effect phức tạp trong afterJob nếu cần transaction, retry và metadata rõ ràng. Step publish có thể được restart và kiểm tra xem output đã được công bố hay chưa.

## 17. Xử lý JobInstance mới và output cũ

Khi tạo JobInstance mới, output name mới sẽ tránh ghi đè file của instance trước. Tuy nhiên, cần có chính sách retention để thư mục output không tăng vô hạn.

Một số cách quản lý:

- Lưu output theo ngày hoặc batch partition.
- Xóa file staging của execution cũ sau thời gian retention.
- Giữ file published theo chính sách nghiệp vụ.
- Lưu manifest chứa JobInstance ID, JobExecution ID cuối, đường dẫn và checksum.
- Không xóa output của JobInstance đang chạy hoặc còn có thể restart.
- Dùng quy trình cleanup có kiểm tra trạng thái JobRepository.

Không xóa file chỉ vì JobExecution gần nhất FAILED. File có thể chứa dữ liệu của các chunk đã commit và cần thiết cho restart. Chỉ cleanup khi đã xác định JobInstance không còn restart hoặc output đã được xử lý theo chính sách lưu trữ.

## 18. Nhiều Job chạy đồng thời

Hai JobInstance khác nhau có thể chạy đồng thời. Tên output phải tránh collision giữa chúng.

Dùng JobInstance ID thường giải quyết được va chạm trong cùng JobRepository. Nếu tên dựa trên business key, cần bảo đảm key có uniqueness phù hợp. Ví dụ hai tenant có cùng business date thì tên chỉ chứa date sẽ bị trùng.

Trong partitioned Step, nhiều worker có thể cùng ghi output. Không để tất cả worker cùng mở một file với các writer độc lập trừ khi có thiết kế đồng bộ/aggregation rõ ràng. Thông thường, mỗi partition ghi file riêng theo partition name hoặc ID, rồi một Step tổng hợp tạo output cuối cùng.

Ví dụ:

~~~text
orders-instance-52/
  partition-0.csv
  partition-1.csv
  partition-2.csv
  merged.csv
~~~

JobInstance ID xác định thư mục của lần xử lý logic. Partition key xác định artifact con. Khi restart, tên file của partition phải ổn định theo partition execution để worker tiếp tục đúng file.

## 19. Ghi metadata output để truy vết

Ngoài tên file, có thể lưu metadata output trong Job ExecutionContext hoặc một bảng artifact registry.

Các trường thường hữu ích:

- JobInstance ID.
- JobExecution ID tạo hoặc hoàn tất output.
- Job name.
- Business date hoặc source batch ID.
- Output path.
- Output format/version.
- Record count.
- File size.
- Checksum.
- Publication status và timestamp.

Ví dụ metadata:

~~~json
{
  "jobName": "exportOrdersJob",
  "jobInstanceId": 52,
  "jobExecutionId": 94,
  "outputFile": "/batch/published/orders-52.csv",
  "formatVersion": "v2",
  "recordCount": 12000,
  "publicationStatus": "PUBLISHED"
}
~~~

JobInstance ID cho biết file thuộc đơn vị xử lý logic nào; JobExecution ID cho biết lần thực thi nào đã hoàn tất việc tạo hoặc publish file. Hai định danh này bổ sung cho nhau.

Không ghi nội dung nhạy cảm vào file name hoặc metadata. Dùng ID đã được phê duyệt và giới hạn quyền đọc artifact registry.

## 20. Kiểm thử tên output theo JobInstance

Cần kiểm thử cả quy tắc đặt tên và hành vi restart thực tế.

Các kịch bản:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Launch Job lần đầu | Output name chứa JobInstance ID đã tạo |
| Restart cùng JobInstance | Output path giống lần chạy đầu |
| JobInstance mới | Output path mới, không ghi đè file cũ |
| Thay identifying parameter | Tạo instance mới và tên output mới |
| Thay non-identifying parameter | Không vô tình đổi output path của cùng instance |
| Writer restart | Khôi phục checkpoint và tiếp tục đúng file |
| File staging | Consumer không thấy file trước khi publish |
| Publish Step retry | Không publish trùng hoặc mất file |
| Hai JobInstance đồng thời | Không ghi chung output |
| Hai tenant cùng business date | Không collision nếu tenant là một phần của key |
| Output directory không tồn tại | Được tạo theo chính sách hoặc Job fail rõ ràng |
| Path không hợp lệ | Job từ chối đường dẫn ngoài thư mục cho phép |
| Partitioning | Mỗi partition ghi resource riêng hoặc có cơ chế merge đúng |
| Cleanup | Không xóa file còn cần cho restart |

Một integration test điển hình:
1. Launch Job với identifying parameters cố định.
2. Cho writer ghi một số chunk rồi cố ý làm Step thất bại.
3. Ghi lại JobInstance ID và output path.
4. Restart cùng JobInstance.
5. Xác nhận JobExecution ID thay đổi nhưng JobInstance ID và output path giữ nguyên.
6. Xác nhận file cuối có đủ record và không có dòng bị ghi trùng.
7. Launch với identifying parameters mới và xác nhận output path khác.

Test cần dùng JobRepository và writer phù hợp với cấu hình production. Unit test chỉ kiểm tra hàm tạo tên file sẽ không chứng minh checkpoint được khôi phục đúng.

## 21. Lỗi thường gặp

**Dùng JobExecution ID cho output cần restart.** Mỗi lần restart tạo file mới, làm output bị phân mảnh.

**Sinh timestamp hoặc UUID mới trong beforeJob.** Restart cùng JobInstance có thể nhận đường dẫn khác và không khớp checkpoint cũ.

**Dùng non-identifying parameter làm tên duy nhất.** Parameter có thể thay đổi nhưng JobInstance vẫn là một; output path không còn ổn định.

**Đổi output directory giữa các lần chạy.** Writer mở resource khác trong khi metadata giữ checkpoint của file cũ.

**Không bật lưu state cho writer.** Writer không có checkpoint cần thiết để tiếp tục đúng vị trí.

**Đổi writer name.** Các key ExecutionContext có thể không còn khớp với metadata đã lưu.

**Xóa file khi restart.** Dữ liệu đã commit của các chunk trước có thể bị mất.

**Append thủ công không theo checkpoint.** Có thể ghi trùng hoặc sai thứ tự record.

**Cho consumer đọc file đang ghi.** Downstream có thể xử lý dữ liệu chưa hoàn chỉnh; dùng staging và publish.

**Dùng business date đơn lẻ làm tên file.** Nhiều nguồn hoặc tenant cùng ngày có thể collision.

**Cho nhiều partition ghi cùng một file không đồng bộ.** Có thể mất dữ liệu, trộn thứ tự hoặc hỏng file.

**Cleanup file của Job FAILED quá sớm.** File có thể còn cần cho restart cùng JobInstance.

## 22. Quy trình thiết kế output name theo JobInstance

Khi tạo file output cho Spring Batch, hãy thực hiện theo trình tự:

1. Xác định file thuộc một JobInstance hay một JobExecution riêng.
2. Nếu cần restart cùng file, dùng JobInstance ID hoặc identifying business key ổn định.
3. Không dùng JobExecution ID, timestamp mới hoặc UUID mới cho output cần tiếp tục.
4. Tạo output path sau khi JobExecution/JobInstance đã tồn tại, chẳng hạn trong beforeJob.
5. Lưu path vào Job ExecutionContext để Step-scoped writer late-bind.
6. Dùng @StepScope và saveState(true) cho writer cần checkpoint.
7. Giữ ổn định output directory, writer name, format và input qua restart.
8. Chuẩn hóa path và kiểm tra output nằm trong thư mục được phép.
9. Dùng staging và Step publish nếu downstream chỉ được đọc file hoàn chỉnh.
10. Có retention/cleanup dựa trên trạng thái JobInstance và yêu cầu lưu trữ.
11. Với partitioning, tạo resource riêng cho từng partition hoặc cơ chế merge có kiểm soát.
12. Kiểm thử JobInstance ID giữ nguyên qua restart, JobExecution ID thay đổi và file cuối không thiếu/trùng record.

Tên output theo JobInstance tạo một định danh bền vững cho artifact của một lần xử lý logic. JobExecution ID giúp truy vết từng attempt; JobInstance ID giúp giữ cùng output path qua restart. Khi kết hợp định danh ổn định, Step-scoped writer, checkpoint và quy trình publish, Spring Batch có thể tiếp tục file đã ghi dở và cung cấp output hoàn chỉnh cho hệ thống downstream.


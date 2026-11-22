# Điều kiện job có thể restart

Spring Batch cho phép chạy lại một Job đã thất bại hoặc được dừng có kiểm soát, nhưng khả năng restart phụ thuộc vào danh tính JobInstance, trạng thái execution cuối cùng, cấu hình restart của Job và metadata đã được lưu trong JobRepository. Restart tạo một JobExecution mới cho cùng JobInstance; framework dùng trạng thái và checkpoint đã persist để quyết định Step nào cần chạy lại và component nào cần khôi phục state.

Một Job không thể được restart chỉ vì lần chạy trước có lỗi trong log. Job phải kết thúc ở trạng thái cho phép restart, không còn execution đang chạy, Job phải được cấu hình restartable và các thành phần đọc/ghi phải có đủ state để tiếp tục an toàn. Hiểu rõ các điều kiện này giúp tránh tạo nhầm JobInstance mới, chạy lại Step đã hoàn thành hoặc làm trùng dữ liệu sau sự cố.

## 1. Phân biệt JobInstance và JobExecution

Đây là điều kiện nền tảng để hiểu restart.

- **JobInstance** đại diện cho một lần xử lý logic với một bộ tham số định danh cụ thể.
- **JobExecution** đại diện cho một lần thực thi JobInstance. Một JobInstance có thể có nhiều JobExecution nếu lần chạy trước thất bại hoặc bị dừng và được restart.

Danh tính JobInstance được xác định bởi tên Job và các JobParameter được đánh dấu identifying.

Ví dụ:

~~~text
Job name: importOrdersJob
Identifying parameters:
  businessDate = 2026-11-15
  sourceFileId = 8421

                    |
                    v
JobInstance: importOrdersJob / 2026-11-15 / 8421
                    |
          +---------+---------+
          |                   |
          v                   v
JobExecution 101       JobExecution 108
FAILED                 COMPLETED
(lần chạy đầu)         (lần restart)
~~~

JobExecution 101 và 108 thuộc cùng một JobInstance. Restart không tạo một JobInstance mới; nó tạo execution tiếp theo cho instance đã có.

Nếu thay đổi một identifying JobParameter, Spring Batch xem đó là một JobInstance khác. Điều này phù hợp khi muốn chạy một công việc mới, nhưng không phải cách tiếp tục execution cũ.

## 2. Điều kiện về JobParameters

Khi muốn restart, cần khởi chạy lại đúng Job với cùng identifying JobParameters đã xác định JobInstance ban đầu.

Ví dụ lần chạy đầu:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("sourceFileId", 8421L, true)
        .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
~~~

Nếu execution thất bại, gọi JobLauncher lần nữa với cùng tên Job và cùng identifying parameters sẽ yêu cầu restart JobInstance đó, nếu các điều kiện trạng thái và cấu hình khác cho phép.

~~~java
JobParameters sameParameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("sourceFileId", 8421L, true)
        .toJobParameters();

jobLauncher.run(importOrdersJob, sameParameters);
~~~

Không thêm một identifying parameter mới chỉ để thử chạy lại. Ví dụ, nếu lần restart thêm run.id=2 hoặc timestamp mới và parameter đó là identifying, Spring Batch sẽ tạo JobInstance mới thay vì tiếp tục instance cũ.

### Identifying và non-identifying parameters

JobParameters có thể được đánh dấu identifying hoặc non-identifying.

- Identifying parameter tham gia tạo danh tính JobInstance.
- Non-identifying parameter được lưu cùng execution nhưng không làm thay đổi danh tính JobInstance.

Không nên dùng non-identifying parameter để âm thầm thay đổi ý nghĩa dữ liệu nguồn hoặc đích giữa các lần restart. Dù parameter không tham gia nhận diện instance, thay đổi giá trị đầu vào giữa hai lần chạy vẫn có thể khiến checkpoint cũ không còn phù hợp. Hãy giữ các input ảnh hưởng đến kết quả ổn định trong suốt vòng đời JobInstance.

## 3. Trạng thái JobExecution cho phép restart

Restart thường được thực hiện sau khi JobExecution trước kết thúc ở trạng thái FAILED hoặc STOPPED.

| BatchStatus của execution gần nhất | Có thể restart? | Ý nghĩa |
|---|---|---|
| FAILED | Có, nếu Job restartable và các điều kiện khác hợp lệ | Job kết thúc do lỗi |
| STOPPED | Có, nếu Job restartable | Job được dừng có kiểm soát |
| COMPLETED | Không cho cùng JobInstance | Công việc đã hoàn tất |
| STARTING / STARTED | Chưa thể restart đồng thời | Execution vẫn đang khởi chạy hoặc chạy |
| STOPPING | Chưa thể restart ngay | Đang trong quá trình dừng |
| ABANDONED | Không nên restart execution này | Execution được đánh dấu bỏ qua/không tiếp tục |
| UNKNOWN | Không thể restart an toàn theo trạng thái metadata | Kết quả transaction hoặc execution không xác định |

Điều kiện chính xác còn phụ thuộc phiên bản Spring Batch, trạng thái StepExecution và cấu hình Job. Khi execution đang chạy, repository ngăn một execution khác khởi chạy cùng JobInstance để tránh xử lý đồng thời cùng một công việc.

Các lỗi thường gặp khi launch:

- JobExecutionAlreadyRunningException: JobInstance đang có execution chạy.
- JobInstanceAlreadyCompleteException: JobInstance đã hoàn thành.
- JobRestartException: không thể restart do trạng thái hoặc cấu hình.
- JobParametersInvalidException: JobParameters không hợp lệ theo validator.
- StartLimitExceededException: Step đã vượt giới hạn số lần bắt đầu.

Không nên xóa metadata hoặc tự sửa BatchStatus trong database chỉ để vượt qua các lỗi này. Trước hết hãy xác định execution nào đang chạy, kết thúc ở trạng thái nào và vì sao repository từ chối restart.

## 4. Job phải được cấu hình restartable

Mặc định, Job được xây dựng bằng JobBuilder có thể restart. Có thể chủ động vô hiệu hóa restart bằng preventRestart():

~~~java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .preventRestart()
            .build();
}
~~~

Khi Job được cấu hình preventRestart(), nếu execution trước thất bại hoặc dừng, Spring Batch không cho restart cùng JobInstance. Muốn chạy lại, ứng dụng phải tạo một JobInstance mới bằng identifying parameters mới theo quy tắc nghiệp vụ.

Chỉ dùng preventRestart() khi Job thực sự không thể hoặc không được phép tiếp tục từ execution trước. Trong đa số quy trình batch dài, restartability là khả năng quan trọng để phục hồi sau lỗi.

Nếu Job cần restart, không gọi preventRestart() trong cấu hình.

## 5. JobRepository phải lưu được metadata

JobRepository là nơi lưu JobInstance, JobExecution, StepExecution, trạng thái và ExecutionContext. Restart dựa vào metadata này để biết lần chạy trước đã đi đến đâu.

Với JDBC JobRepository, các bảng thường gặp gồm:

| Metadata | Bảng |
|---|---|
| JobInstance | BATCH_JOB_INSTANCE |
| JobExecution | BATCH_JOB_EXECUTION |
| JobParameters | BATCH_JOB_EXECUTION_PARAMS |
| StepExecution | BATCH_STEP_EXECUTION |
| Job ExecutionContext | BATCH_JOB_EXECUTION_CONTEXT |
| Step ExecutionContext | BATCH_STEP_EXECUTION_CONTEXT |

Tên bảng có thể thay đổi theo table prefix và schema được cấu hình. JobRepository cần được cấu hình đúng và schema metadata phải được khởi tạo tương ứng với phiên bản Spring Batch.

Nếu JobRepository không lưu được trạng thái, framework không thể khôi phục chính xác execution. Không dùng một repository in-memory tạm thời cho Job cần restart qua lần khởi động process hoặc qua nhiều node. Với môi trường production, cần repository bền vững và backup/retention phù hợp.

Không tự xóa các hàng BATCH_* hoặc sửa trực tiếp trạng thái execution để ép restart. Những thay đổi như vậy có thể làm mất liên kết giữa JobInstance, JobExecution, StepExecution và context đã lưu.

## 6. Step đã hoàn thành thường được bỏ qua khi restart

Khi Job có nhiều Step và một Step thất bại, restart cùng JobInstance thường bỏ qua các Step đã hoàn thành, rồi tiếp tục từ Step chưa hoàn thành hoặc thất bại.

Ví dụ:

~~~text
JobInstance: dailyImport

Execution đầu:
  validateFileStep  -> COMPLETED
  importDataStep    -> FAILED
  createReportStep  -> NOT STARTED

Restart:
  validateFileStep  -> không chạy lại
  importDataStep    -> restart từ checkpoint
  createReportStep  -> chạy sau khi import hoàn tất
~~~

Đây là hành vi quan trọng để tránh thực hiện lại những công đoạn đã hoàn tất. Nếu Step đầu gửi thông báo, tạo file hoặc cập nhật hệ thống ngoài, việc bỏ qua Step đã completed giúp tránh lặp side effect.

Nếu nghiệp vụ yêu cầu chạy lại một Step đã completed khi Job restart, có thể cấu hình allowStartIfComplete(true) cho Step đó. Cần hiểu tác động của việc chạy lại và bảo đảm thao tác idempotent.

## 7. allowStartIfComplete cho Step đã hoàn thành

Mặc định, một Step đã COMPLETED trong JobInstance sẽ không chạy lại khi Job được restart. Có thể cho phép chạy lại bằng allowStartIfComplete(true):

~~~java
@Bean
Step rebuildSummaryStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet rebuildSummaryTasklet) {

    return new StepBuilder("rebuildSummaryStep", jobRepository)
            .tasklet(rebuildSummaryTasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
~~~

Tùy chọn này hữu ích khi Step tạo báo cáo hoặc dữ liệu dẫn xuất có thể được tái tạo an toàn sau khi Step sau thất bại.

Không bật tùy chọn này một cách máy móc. Nếu Step đã gửi thanh toán, phát email, tạo đơn hàng hoặc thực hiện một side effect không idempotent, chạy lại có thể tạo kết quả trùng.

Cần phân biệt:
- allowStartIfComplete(true) cho phép Step completed được chạy lại trong lần restart phù hợp.
- Nó không làm JobInstance đã COMPLETED trở nên restartable.
- Nó không thay thế restartability của Job hoặc điều kiện trạng thái JobExecution.

## 8. startLimit giới hạn số lần Step được bắt đầu

Step có thể được cấu hình giới hạn số lần bắt đầu bằng startLimit(n):

~~~java
@Bean
Step importDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importDataStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .startLimit(3)
            .build();
}
~~~

Với giới hạn 3, Step không được bắt đầu vượt quá số lần cho phép theo metadata của Step trong JobInstance. Nếu restart nhiều lần khiến Step vượt giới hạn, framework có thể ném StartLimitExceededException.

startLimit không phải retry limit cho từng item. Retry limit kiểm soát số lần thử lại một thao tác; startLimit kiểm soát số lần Step được bắt đầu trong vòng đời JobInstance.

Hãy đặt startLimit khi có lý do vận hành rõ ràng. Nếu đặt quá thấp, một Job có thể không còn cơ hội restart sau một số sự cố hạ tầng ngắn hạn. Nếu không cần giới hạn đặc biệt, dùng mặc định của framework.

## 9. FAILED và STOPPED khác nhau thế nào?

FAILED thường biểu thị Step hoặc Job kết thúc do exception hoặc lỗi xử lý. STOPPED thường là trạng thái kết thúc sau khi Job được yêu cầu dừng có kiểm soát.

Cả hai trạng thái đều có thể là điểm bắt đầu cho restart nếu Job restartable và metadata hợp lệ.

Ví dụ dừng có kiểm soát:

~~~text
JobExecution đang STARTED
       |
       | yêu cầu stop
       v
JobExecution STOPPING
       |
       | framework dừng tại điểm an toàn
       v
JobExecution STOPPED
       |
       | restart cùng JobInstance
       v
JobExecution mới
~~~

Không restart khi execution vẫn đang STOPPING. Hãy chờ framework hoàn tất quá trình dừng và repository ghi trạng thái cuối cùng là STOPPED.

Dừng có kiểm soát hữu ích khi cần tạm ngưng batch do bảo trì hoặc ưu tiên tài nguyên. Nó cho phép framework lưu metadata và kết thúc Step theo lifecycle thay vì kill process đột ngột.

## 10. ABANDONED và UNKNOWN không phải điểm restart thông thường

ABANDONED biểu thị execution được đánh dấu là không tiếp tục. Trong flow restart, StepExecution abandoned không được tự động chạy lại như một Step failed. Trạng thái này có thể được dùng khi người vận hành quyết định bỏ qua một Step hoặc execution không còn được tiếp tục.

UNKNOWN biểu thị framework không xác định được kết quả thực thi một cách an toàn, thường liên quan đến lỗi trong lúc cập nhật transaction hoặc metadata. Không nên tự động restart khi không biết business data đã commit hay chưa.

Khi gặp các trạng thái này:

1. Kiểm tra log và nguyên nhân execution rơi vào trạng thái đó.
2. Đối chiếu metadata với dữ liệu nghiệp vụ đã ghi.
3. Xác định có thể phục hồi bằng quy trình vận hành được phê duyệt hay phải tạo JobInstance mới.
4. Không tự sửa BatchStatus bằng SQL để ép framework chạy tiếp.

Nếu cần bỏ qua một Step, dùng flow hoặc thao tác quản trị phù hợp và hiểu rõ ảnh hưởng tới kết quả nghiệp vụ. ABANDONED là quyết định về vòng đời execution, không phải cách thay thế cho skip item.

## 11. Điều kiện restart của reader và writer

Job restartable vẫn có thể không phục hồi đúng nếu reader hoặc writer không lưu state cần thiết.

Các component có state thường triển khai ItemStream hoặc ItemStreamReader/ItemStreamWriter:

- open(ExecutionContext): khôi phục state đã lưu.
- update(ExecutionContext): đưa checkpoint hiện tại vào context.
- close(): giải phóng resource.

Ví dụ cấu hình reader dựng sẵn:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
~~~

saveState(true) cho phép reader lưu state cần thiết để restart. Tên reader cần ổn định vì framework dùng tên component để quản lý các key trong ExecutionContext.

Nếu dùng reader/writer tự viết, cần triển khai ItemStream đúng lifecycle. Nếu dùng delegate hoặc composite, bảo đảm các delegate có state được đăng ký để framework gọi open, update và close.

## 12. Dữ liệu nguồn và đích phải ổn định qua restart

Checkpoint chỉ có ý nghĩa khi dữ liệu mà nó tham chiếu vẫn giữ nguyên.

Ví dụ reader đã lưu vị trí dòng 10.000 trong file đầu vào. Nếu file bị thay thế bằng một file khác trước khi restart, vị trí 10.000 không còn đại diện cho cùng dữ liệu. Job có thể bỏ sót hoặc xử lý sai bản ghi.

Cần bảo đảm:

- File đầu vào không bị thay đổi trong vòng đời JobInstance.
- Database source có thứ tự đọc ổn định hoặc snapshot/watermark rõ ràng.
- Query sort có thứ tự xác định, thường dựa trên khóa duy nhất.
- Partition boundaries không thay đổi giữa các lần restart.
- File output hoặc resource đích vẫn tồn tại nếu writer cần tiếp tục.
- Version/checksum của nguồn được kiểm tra khi restart nếu dữ liệu có thể thay đổi.

Với database, một reader phân trang theo ID cần dùng thứ tự ổn định và điều kiện lọc phù hợp. Nếu dữ liệu mới được chèn vào hoặc bản ghi bị xóa giữa các lần chạy, cần xác định liệu Job có nên xử lý snapshot ban đầu hay dữ liệu hiện tại.

## 13. Transaction và checkpoint phải nhất quán

Spring Batch lưu checkpoint theo lifecycle của chunk. Với database writer, dữ liệu ghi và metadata checkpoint cần có transaction semantics phù hợp để tránh một bên đi trước bên kia.

Nếu business data và JobRepository dùng chung transaction resource trong cấu hình phù hợp, các thay đổi có thể commit/rollback cùng nhau. Nếu chúng dùng hai database hoặc hai transaction manager cục bộ khác nhau, không mặc định chúng là một transaction nguyên tử.

Có thể xuất hiện tình huống:

- Business data đã commit nhưng checkpoint chưa được lưu.
- Checkpoint được lưu nhưng đích ghi ngoài transaction chưa xác nhận.
- File hoặc API đã nhận dữ liệu nhưng transaction database rollback.

Để restart an toàn:

- Dùng transaction manager quản lý đúng business resource.
- Giữ reader/writer checkpoint khớp với dữ liệu đã commit.
- Dùng unique constraint, upsert hoặc idempotency key khi có thể ghi lại.
- Dùng outbox khi cần phát message sau khi business transaction commit.
- Có quy trình đối soát cho các tác động ngoài transaction.

Không xem Job status là bằng chứng duy nhất về trạng thái dữ liệu nghiệp vụ. Một Job FAILED vẫn có thể có nhiều chunk trước đó đã commit thành công.

## 14. Restart Job bằng JobLauncher hoặc JobOperator

Có thể restart bằng cách gọi JobLauncher với cùng identifying JobParameters sau khi execution trước kết thúc ở trạng thái restartable.

~~~java
JobExecution execution =
        jobLauncher.run(importOrdersJob, sameIdentifyingParameters);
~~~

JobRepository kiểm tra JobInstance và trạng thái execution trước đó. Nếu điều kiện hợp lệ, nó tạo JobExecution mới gắn với cùng JobInstance.

Đối với thao tác quản trị, JobOperator có phương thức restart theo JobExecution ID:

~~~java
long newExecutionId =
        jobOperator.restart(failedExecutionId);
~~~

Phương thức và exception cụ thể cần theo API Spring Batch đang sử dụng. JobOperator thường được dùng bởi console hoặc dịch vụ vận hành để restart một execution đã thất bại hoặc dừng.

Không gọi restart nhiều lần song song cho cùng execution. JobRepository có cơ chế bảo vệ để ngăn cùng JobInstance được chạy đồng thời, nhưng phía gọi vẫn nên xử lý các exception trạng thái và không lặp request quản trị vô hạn.

## 15. RunIdIncrementer tạo JobInstance mới

JobParametersIncrementer thường được dùng để tạo bộ JobParameters mới cho một lần chạy mới. RunIdIncrementer là ví dụ phổ biến, nó tăng một parameter run.id.

~~~java
@Bean
Job dailyImportJob(
        JobRepository jobRepository,
        Step importStep) {

    return new JobBuilder("dailyImportJob", jobRepository)
            .incrementer(new RunIdIncrementer())
            .start(importStep)
            .build();
}
~~~

Mỗi lần increment run.id theo cách identifying sẽ tạo JobInstance mới. Đây là hành vi phù hợp khi muốn chạy lại công việc như một batch mới, nhưng không phải restart checkpoint của JobInstance đã thất bại.

Phân biệt hai ý định:

- **Restart:** giữ identifying parameters để tiếp tục cùng JobInstance.
- **Run mới:** tạo identifying parameters mới, ví dụ business date hoặc run ID mới.

Không thêm timestamp mới một cách tự động khi người vận hành chọn restart. Nếu scheduler luôn tạo tham số mới, mỗi lần chạy có thể trở thành JobInstance mới và bỏ qua checkpoint của lần thất bại trước.

## 16. Flow control có thể ảnh hưởng khả năng restart

Flow DSL quyết định Step tiếp theo và trạng thái cuối của Job. Cần hiểu sự khác nhau giữa hoàn thành, thất bại và dừng.

Một flow kết thúc Job với trạng thái COMPLETED sẽ làm JobInstance hoàn thành. Khi đó cùng JobInstance không thể restart như một Job FAILED hoặc STOPPED.

Nếu cần dừng Job để restart từ một Step cụ thể, dùng cơ chế stop/restart của flow thay vì kết thúc Job như COMPLETED. Khi thiết kế flow, kiểm tra cả BatchStatus và ExitStatus: ExitStatus có thể điều khiển transition, còn BatchStatus phản ánh trạng thái vòng đời mà JobRepository dùng để quản lý execution.

Không gán ExitStatus tùy ý rồi cho rằng Job đã trở thành restartable. Hãy để framework kết thúc execution bằng BatchStatus phù hợp.

## 17. Những điều kiện khiến restart không an toàn

Ngay cả khi JobRepository cho phép restart, kết quả nghiệp vụ vẫn có thể không an toàn nếu dữ liệu hoặc side effect không thể lặp.

Ví dụ:

- Writer đã gửi email nhưng process dừng trước khi checkpoint được lưu.
- API đã tạo giao dịch nhưng response timeout, khiến Job không biết kết quả.
- File output đã được ghi nhưng checkpoint chưa được commit.
- Reader dùng offset trên file đã bị thay đổi.
- Một Step completed được chạy lại và tạo duplicate.
- Job dùng một identifying parameter mới nên tạo instance khác.
- Hai database commit độc lập và rơi vào trạng thái không đồng bộ.

Các biện pháp bảo vệ:

- Thiết kế writer idempotent.
- Dùng business key và unique constraint.
- Dùng idempotency key cho API.
- Ghi outbox cùng transaction nghiệp vụ.
- Dùng file riêng theo JobInstance và chỉ publish khi hoàn thành.
- Giữ snapshot hoặc version nguồn.
- Đối soát dữ liệu trước khi restart nếu có tác động ngoài transaction.

Restartability của framework và restart safety của nghiệp vụ là hai điều liên quan nhưng khác nhau. Framework có thể tạo execution mới đúng metadata, nhưng ứng dụng vẫn phải bảo đảm việc xử lý lại không gây duplicate hoặc bỏ sót dữ liệu.

## 18. Quy trình xác định một Job có thể restart

Khi một Job thất bại, kiểm tra theo thứ tự:

1. **Xác định JobInstance:** kiểm tra tên Job và identifying JobParameters của lần chạy trước.
2. **Kiểm tra execution cuối:** xác nhận BatchStatus là FAILED hoặc STOPPED và execution không còn đang chạy.
3. **Kiểm tra restartability:** xác nhận Job không dùng preventRestart().
4. **Kiểm tra Step:** xác định Step nào completed, failed, stopped hoặc abandoned; kiểm tra allowStartIfComplete và startLimit.
5. **Kiểm tra JobRepository:** bảo đảm metadata và ExecutionContext đã được persist.
6. **Kiểm tra component state:** reader/writer hỗ trợ ItemStream và key state còn tương thích.
7. **Kiểm tra nguồn/đích:** file, query, partition boundaries và output resource vẫn phù hợp với checkpoint.
8. **Kiểm tra transaction:** xác định business data và checkpoint có thể lệch nhau hay không.
9. **Kiểm tra idempotency:** xác nhận retry/restart không tạo side effect trùng.
10. **Khởi chạy lại đúng instance:** dùng cùng identifying parameters hoặc JobOperator.restart trên execution phù hợp.

Nếu một điều kiện chưa rõ, không nên restart lặp đi lặp lại để thử vận may. Đối chiếu metadata với dữ liệu nghiệp vụ trước, đặc biệt khi Job ghi ra hệ thống ngoài transaction.

## 19. Kiểm thử điều kiện restart

Restart cần được kiểm thử bằng JobRepository và resource phù hợp, không chỉ bằng unit test cho một listener.

Các kịch bản quan trọng:

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Job lần đầu hoàn thành | Launch lại cùng identifying parameters bị từ chối vì instance đã complete |
| Job thất bại | Restart tạo JobExecution mới cho cùng JobInstance |
| Job dừng có kiểm soát | Restart được sau khi status chuyển thành STOPPED |
| Job còn đang chạy | Launch trùng bị từ chối |
| Job dùng preventRestart | Restart bị từ chối |
| Thay identifying parameter | Tạo JobInstance mới |
| Thêm run.id mới | Tạo instance mới, không tiếp tục checkpoint cũ |
| Step đã completed | Được bỏ qua mặc định khi restart |
| Step allowStartIfComplete | Step completed được chạy lại theo cấu hình |
| Step vượt startLimit | Không được bắt đầu thêm |
| Reader hỗ trợ saveState | Tiếp tục từ checkpoint đã lưu |
| Input thay đổi | Job phát hiện hoặc xử lý theo chính sách version |
| Writer không idempotent | Test phát hiện nguy cơ duplicate |
| Execution UNKNOWN/ABANDONED | Không tự động restart như execution FAILED |

Một integration test điển hình: chạy Job với dữ liệu đủ nhiều để hoàn thành một vài chunk, cố ý làm writer lỗi ở chunk sau, xác nhận JobExecution FAILED, sau đó restart cùng identifying parameters và kiểm tra dữ liệu cuối cùng không thiếu hoặc trùng.

Cũng nên kiểm tra trường hợp process bị dừng đột ngột để hiểu hành vi metadata và transaction của môi trường triển khai. Một process kill có thể để lại trạng thái khác với việc Job được dừng có kiểm soát.

## 20. Lỗi thường gặp khi restart

**Thêm parameter mới khi restart.** JobLauncher tạo JobInstance mới và không dùng checkpoint của instance cũ.

**Restart Job đã COMPLETED.** JobInstance đã hoàn thành; cần một lần chạy mới với identifying parameters mới nếu muốn xử lý lại.

**Job dùng preventRestart().** Framework từ chối restart cùng instance dù execution trước FAILED.

**Execution vẫn đang chạy hoặc STOPPING.** Cần chờ trạng thái kết thúc trước khi restart.

**Step completed bị chạy lại ngoài ý muốn.** Kiểm tra allowStartIfComplete và side effect của Step.

**Vượt startLimit.** Step không thể bắt đầu thêm trong cùng JobInstance theo giới hạn đã đặt.

**Reader/writer không lưu state.** Job có thể bắt đầu lại nhưng không biết vị trí tiếp tục phù hợp.

**Đổi tên component hoặc key ExecutionContext.** Checkpoint cũ không còn được đọc đúng.

**Nguồn dữ liệu đã thay đổi.** Offset hoặc last ID không còn đại diện cho cùng dữ liệu.

**Sửa trực tiếp bảng metadata.** Có thể làm hỏng quan hệ execution và tính nhất quán của repository.

**Cho rằng FAILED đồng nghĩa rollback toàn Job.** Các chunk đã commit trước đó vẫn có thể tồn tại; restart cần xử lý phần đã commit một cách an toàn.

## 21. Quy trình thiết kế Job có khả năng restart

Khi xây dựng Job, hãy xác định trước các điều kiện restart:

- Chọn identifying JobParameters ổn định để định danh một đơn vị công việc.
- Giữ Job restartable nếu nghiệp vụ cho phép tiếp tục sau lỗi.
- Không dùng preventRestart() nếu cần phục hồi cùng JobInstance.
- Để JobRepository lưu metadata bền vững.
- Dùng Step ExecutionContext và ItemStream cho checkpoint.
- Giữ tên Step, reader, writer và key state ổn định qua các lần triển khai.
- Xác định Step completed có được chạy lại hay không.
- Đặt startLimit chỉ khi có yêu cầu rõ.
- Giữ dữ liệu nguồn/đích ổn định hoặc có version/snapshot.
- Thiết kế writer idempotent và side effect có thể phục hồi.
- Kiểm thử FAILED, STOPPED, COMPLETED, restart và process interruption.

Một Job có thể restart khi cùng JobInstance còn ở trạng thái cho phép tiếp tục, Job được cấu hình restartable, JobRepository lưu đủ metadata và các Step/component có thể khôi phục checkpoint. Restart tạo một JobExecution mới cho cùng instance; JobParameters mới có identifying value sẽ tạo instance khác. Khi kết hợp đúng trạng thái, metadata, transaction và idempotency, Spring Batch có thể tiếp tục công việc sau sự cố mà không phải xử lý lại tùy tiện hoặc làm sai lệch dữ liệu.


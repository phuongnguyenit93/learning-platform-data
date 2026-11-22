# Restartable job là gì?

Trong Spring Batch, một **restartable Job** là Job có thể tiếp tục một đơn vị công việc đã thất bại hoặc bị dừng từ trạng thái đã lưu, thay vì phải bắt đầu lại toàn bộ dữ liệu từ đầu. Spring Batch sử dụng `JobRepository` để lưu metadata của lần thực thi, `ExecutionContext` để lưu checkpoint và trạng thái của Reader/Step để xác định phần công việc cần tiếp tục.

Restart không đồng nghĩa với tạo một JobInstance mới. Khi restart, ứng dụng thường dùng cùng tên Job và cùng identifying `JobParameters` để nhận diện lại JobInstance trước đó. Spring Batch tạo một `JobExecution` mới cho lần thử tiếp theo, giữ lại lịch sử lần chạy cũ và áp dụng chính sách restart của Job cùng các Step.

Khả năng restart là đặc tính cần được thiết kế trong Job, Reader, Writer và transaction boundary. Việc chỉ gọi lại `JobLauncher.run()` không tự bảo đảm dữ liệu được tiếp tục đúng vị trí hoặc không bị ghi trùng.

## 1. Job restartable giải quyết vấn đề gì?

Một batch job có thể xử lý hàng nghìn hoặc hàng triệu bản ghi và chạy trong thời gian dài. Nếu ứng dụng hoặc database gặp lỗi ở gần cuối, chạy lại toàn bộ từ đầu có thể tốn thời gian và tạo tác dụng phụ trùng lặp.

Ví dụ Job nhập file 100.000 đơn hàng, commit interval 1.000:

```text
importOrdersJob
  |
  +--> Chunk 1: COMMITTED (1.000 orders)
  +--> Chunk 2: COMMITTED (1.000 orders)
  +--> ...
  +--> Chunk 70: COMMITTED
  +--> Chunk 71: FAILED / ROLLED BACK
  +--> Các chunk còn lại chưa chạy
```

Nếu Job hỗ trợ restart và Reader lưu checkpoint, lần chạy tiếp theo có thể tiếp tục từ ranh giới đã commit gần nhất. Các chunk đã commit được giữ lại; chunk thất bại được xử lý lại theo trạng thái đã lưu.

Nếu không có metadata bền vững hoặc Reader không lưu state, ứng dụng có thể phải đọc lại từ đầu. Trong trường hợp đó, Writer phải chịu được việc xử lý lặp và không tạo dữ liệu trùng.

## 2. JobInstance và JobExecution khi restart

Spring Batch phân biệt đơn vị công việc logic và từng lần thử thực thi:

- `JobInstance`: một đơn vị công việc được xác định bằng tên Job và identifying JobParameters.
- `JobExecution`: một lần thực thi cụ thể của JobInstance.
- `StepExecution`: một lần thực thi cụ thể của Step trong một JobExecution.

Khi JobInstance thất bại và được restart, JobInstance vẫn giữ nguyên nhưng có JobExecution mới:

```text
Job: importOrdersJob
Identifying parameters: fileId=orders-2026-11-15
       |
       v
JobInstance #50
       |
       +--> JobExecution #101: FAILED
       |       importStep: FAILED
       |
       +--> JobExecution #108: COMPLETED
               importStep: tiếp tục từ checkpoint
```

Lịch sử JobExecution trước đó không bị ghi đè. Điều này giúp người vận hành biết lần nào thất bại, lần nào restart và kết quả cuối của từng lần thực thi.

### Identifying JobParameters quyết định restart đúng instance

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("fileId", "orders-2026-11-15", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

`fileId` là identifying parameter, còn `requestedBy` không tham gia định danh. Khi restart, cần dùng cùng identifying parameters để trỏ đến cùng JobInstance. Nếu thay `fileId` hoặc thêm một identifying UUID mới, Spring Batch có thể tạo JobInstance mới thay vì restart instance cũ.

Không nên thêm timestamp hoặc UUID mới vào identifying parameters mỗi lần retry chỉ để tránh lỗi launch trùng. Cách đó biến lần gọi thành công việc mới và có thể làm toàn bộ dữ liệu được xử lý lại.

## 3. Điều kiện trạng thái để restart

Khả năng restart phụ thuộc trạng thái JobExecution trước đó và cấu hình của Job.

| Trạng thái trước đó | Hành vi thông thường khi launch lại cùng identifying parameters |
|---|---|
| Chưa từng chạy | Tạo JobInstance và JobExecution mới. |
| `STARTED` hoặc đang chạy | Từ chối launch trùng, thường bằng `JobExecutionAlreadyRunningException`. |
| `FAILED` | Có thể tạo JobExecution mới để restart nếu Job cho phép. |
| `STOPPED` | Có thể restart nếu trạng thái và cấu hình cho phép. |
| `COMPLETED` | Không restart cùng JobInstance; thường nhận `JobInstanceAlreadyCompleteException`. |
| `ABANDONED` | Không tiếp tục theo cách restart thông thường. |
| `UNKNOWN` | Cần điều tra metadata và trạng thái thực tế trước khi quyết định. |

Restart chủ yếu dùng để tiếp tục công việc chưa hoàn thành. Nếu Job đã `COMPLETED` mà nghiệp vụ yêu cầu xử lý lại dữ liệu, cần tạo JobInstance mới bằng identifying parameter mang ý nghĩa nghiệp vụ như `reprocessVersion` hoặc `correctionBatchId`.

## 4. JobRepository lưu thông tin restart như thế nào?

`JobRepository` quản lý metadata của JobInstance, JobExecution, StepExecution và ExecutionContext. Trong cấu hình database phổ biến, các bảng metadata mặc định gồm:

| Bảng | Vai trò |
|---|---|
| `BATCH_JOB_INSTANCE` | Lưu định danh của JobInstance. |
| `BATCH_JOB_EXECUTION` | Lưu các lần thực thi của JobInstance và trạng thái. |
| `BATCH_JOB_EXECUTION_PARAMS` | Lưu JobParameters của từng lần thực thi. |
| `BATCH_STEP_EXECUTION` | Lưu trạng thái, thời gian và bộ đếm của StepExecution. |
| `BATCH_JOB_EXECUTION_CONTEXT` | Lưu Job ExecutionContext. |
| `BATCH_STEP_EXECUTION_CONTEXT` | Lưu Step ExecutionContext. |

Nhờ metadata được lưu bền vững, lịch sử thực thi có thể tồn tại qua lần dừng và khởi động lại ứng dụng. Nếu dùng repository in-memory, metadata có thể mất khi process kết thúc; vì vậy, cấu hình đó không phù hợp với yêu cầu restart qua nhiều lần khởi động ứng dụng.

JobRepository lưu metadata thực thi, không thay thế bảng dữ liệu nghiệp vụ. Dữ liệu đơn hàng, khách hàng hoặc kết quả import vẫn cần được lưu trong các bảng ứng dụng phù hợp.

## 5. ExecutionContext và checkpoint

`ExecutionContext` là vùng lưu trữ key-value gắn với JobExecution hoặc StepExecution. Reader và các thành phần `ItemStream` có thể dùng context để lưu trạng thái cần thiết cho restart.

Ví dụ, `FlatFileItemReader` lưu vị trí dòng đã đọc:

```java
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.FileSystemResource;

FlatFileItemReader<Order> orderReader =
        new FlatFileItemReaderBuilder<Order>()
                .name("orderFileReader")
                .resource(new FileSystemResource("data/orders.csv"))
                .delimited()
                .names("id", "customerId", "amount")
                .targetType(Order.class)
                .saveState(true)
                .build();
```

`saveState(true)` cho phép Reader lưu state vào ExecutionContext. Khi Step commit một chunk, Spring Batch gọi cơ chế cập nhật state của các thành phần `ItemStream` để lưu checkpoint phù hợp với transaction.

Khi restart, Reader có thể mở lại nguồn và khôi phục vị trí đọc từ context. Cần giữ tên Reader ổn định giữa các lần chạy vì tên này thường được dùng để đặt key trong ExecutionContext.

### Job ExecutionContext và Step ExecutionContext

Hai phạm vi thường dùng:

- **Step ExecutionContext:** lưu checkpoint hoặc trạng thái riêng của một Step, ví dụ vị trí đọc trong file.
- **Job ExecutionContext:** lưu thông tin nhỏ cần chia sẻ giữa nhiều Step trong cùng một JobExecution, ví dụ mã batch hoặc kết quả kiểm tra đầu vào.

Không nên lưu toàn bộ nội dung file hoặc dữ liệu nghiệp vụ lớn trong ExecutionContext. Hãy lưu checkpoint, khóa hoặc metadata nhỏ; dữ liệu chính nằm trong database hoặc file storage phù hợp.

## 6. Reader phải hỗ trợ restart

Không phải mọi `ItemReader` đều tự động có khả năng khôi phục vị trí. Reader muốn tham gia cơ chế checkpoint cần triển khai `ItemStream` hoặc được bọc bởi một thành phần quản lý state phù hợp.

Các reader của Spring Batch như `FlatFileItemReader`, `JdbcCursorItemReader` và `JdbcPagingItemReader` có thể lưu state khi được cấu hình phù hợp. Reader tùy chỉnh nên triển khai các phương thức `open`, `update` và `close` của `ItemStream` để quản lý trạng thái.

Ví dụ khái quát một reader tự quản lý chỉ số:

```java
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamReader;

public class RestartableListReader implements ItemStreamReader<String> {

    private static final String CURRENT_INDEX = "current.index";

    private final List<String> items;
    private int index;

    public RestartableListReader(List<String> items) {
        this.items = items;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        this.index = executionContext.containsKey(CURRENT_INDEX)
                ? executionContext.getInt(CURRENT_INDEX)
                : 0;
    }

    @Override
    public String read() {
        if (index >= items.size()) {
            return null;
        }
        return items.get(index++);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putInt(CURRENT_INDEX, index);
    }

    @Override
    public void close() {
        // Giải phóng tài nguyên nếu reader có sử dụng.
    }
}
```

Ví dụ trên minh họa cách lưu và khôi phục index; trong ứng dụng thực tế, nguồn `items` phải ổn định giữa lần chạy đầu và lần restart. Nếu danh sách thay đổi hoặc thứ tự item thay đổi, cùng index có thể trỏ đến bản ghi khác. Với database, nên dùng khóa sắp xếp ổn định và query có thứ tự xác định.

## 7. Writer cần an toàn khi item được xử lý lại

Checkpoint không thể bảo đảm mọi tác dụng phụ chỉ xảy ra một lần. Nếu một item đã được gửi tới hệ thống ngoài nhưng chunk rollback trước khi checkpoint commit, lần restart có thể gửi lại item đó.

Vì vậy, Writer cần được thiết kế idempotent:

- Dùng unique constraint trên business key.
- Dùng upsert hoặc `MERGE` với quy tắc cập nhật xác định.
- Dùng idempotency key khi gọi API ngoài.
- Ghi message vào transactional outbox trong cùng transaction với dữ liệu nghiệp vụ.
- Tránh phép cộng dồn hoặc tạo mới không có khóa chống trùng khi retry.

Ví dụ, nếu Job import đơn hàng, khóa duy nhất có thể là `(source_system, source_order_id)`. Cùng một đơn hàng được ghi lại sau restart sẽ cập nhật hoặc được nhận diện là đã tồn tại theo chính sách, không tạo thêm một dòng mới.

Restartability và idempotency bổ sung cho nhau: checkpoint giảm phần công việc phải làm lại; idempotency bảo vệ dữ liệu nếu một phần công việc vẫn phải chạy lại.

## 8. Cấu hình một Job restartable

Job trong Spring Batch mặc định có thể restart nếu không bị cấu hình ngăn restart. Có thể cấu hình Step và Job như sau:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportJobConfig {

    @Bean
    public Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<Order> reader,
            ItemProcessor<Order, ProcessedOrder> processor,
            ItemWriter<ProcessedOrder> writer) {

        return new StepBuilder("importStep", jobRepository)
                .<Order, ProcessedOrder>chunk(500, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .build();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository jobRepository,
            Step importStep) {

        return new JobBuilder("importOrdersJob", jobRepository)
                .start(importStep)
                .build();
    }
}
```

Không gọi `.preventRestart()` trong cấu hình trên, nên Job giữ chính sách restart mặc định. Reader phải hỗ trợ state nếu muốn khôi phục vị trí đọc; Writer phải được thiết kế an toàn khi xử lý lại dữ liệu.

### Ngăn Job restart bằng preventRestart()

Nếu một Job không thể chạy lại an toàn, có thể khai báo:

```java
return new JobBuilder("oneTimeJob", jobRepository)
        .preventRestart()
        .start(oneTimeStep)
        .build();
```

Khi Job đã có lần chạy thất bại, yêu cầu restart sẽ bị từ chối bằng `JobRestartException`. Chỉ dùng tùy chọn này khi nghiệp vụ thực sự không cho phép restart. Nếu có thể làm cho Reader/Writer idempotent và lưu checkpoint, thường nên giữ khả năng phục hồi.

## 9. allowStartIfComplete và startLimit của Step

Job restartable không có nghĩa mọi Step đều chạy lại. Trong lần restart, Step đã `COMPLETED` thường được bỏ qua. Hai tùy chọn Step ảnh hưởng hành vi này:

### allowStartIfComplete(true)

Mặc định, Step đã hoàn thành được bỏ qua khi Job restart. Có thể cấu hình `allowStartIfComplete(true)` nếu muốn Step đó chạy lại trong lần restart:

```java
return new StepBuilder("refreshReferenceDataStep", jobRepository)
        .tasklet(refreshReferenceDataTasklet, transactionManager)
        .allowStartIfComplete(true)
        .build();
```

Chỉ bật khi thao tác an toàn nếu được thực hiện nhiều lần. Ví dụ refresh bảng tham chiếu bằng upsert có thể phù hợp; gửi email, tính phí hoặc phát thông báo không có idempotency thì có thể tạo tác dụng phụ trùng.

### startLimit(n)

`startLimit(n)` giới hạn số lần Step được phép bắt đầu:

```java
return new StepBuilder("fragileStep", jobRepository)
        .tasklet(fragileTasklet, transactionManager)
        .startLimit(3)
        .build();
```

Khi vượt giới hạn, Spring Batch từ chối bắt đầu Step thêm lần nữa. `startLimit` không phải số lần retry của một item; nó giới hạn số lần StepExecution có thể bắt đầu theo chính sách Step. Hãy dùng nó cho tác vụ có giới hạn vận hành rõ ràng, không dùng thay cho retry policy của item.

## 10. Restart bằng JobLauncher

Để restart một Job thất bại, có thể gọi `JobLauncher.run()` với cùng Job và identifying JobParameters. Spring Batch tra cứu JobInstance tương ứng và tạo JobExecution mới nếu trạng thái cùng cấu hình cho phép.

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("fileId", "orders-2026-11-15", true)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
```

Nếu lần chạy trước thất bại, lần gọi tiếp theo với cùng tham số định danh có thể restart instance đó. Nếu lần trước đã `COMPLETED`, lần gọi thường bị từ chối bằng `JobInstanceAlreadyCompleteException`. Nếu execution đang chạy, lần gọi trùng thường bị từ chối bằng `JobExecutionAlreadyRunningException`.

Không thêm một identifying parameter mới chỉ để ép Job chạy lại. Nếu muốn một lần xử lý mới, hãy dùng mã correction hoặc version có ý nghĩa nghiệp vụ và hiểu rằng đó là JobInstance mới.

## 11. Restart bằng JobOperator

`JobOperator` cung cấp API vận hành để restart một JobExecution theo ID:

```java
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class JobRestartService {

    private final JobOperator jobOperator;

    public JobRestartService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public Long restart(long failedExecutionId) throws Exception {
        return jobOperator.restart(failedExecutionId);
    }
}
```

`failedExecutionId` là ID của JobExecution cần restart. Cần xác nhận đây là execution đúng JobInstance và trạng thái có thể restart. Trong ứng dụng vận hành, nên giới hạn quyền restart, ghi audit người yêu cầu và kiểm tra dữ liệu đầu vào đã được sửa nếu nguyên nhân thất bại vẫn còn.

## 12. Transaction boundary giúp restart đáng tin cậy

Chunk Step thường commit transaction theo từng chunk. Khi một chunk thất bại, transaction của chunk đó rollback; các chunk đã commit vẫn được giữ. Đây là mốc phục hồi quan trọng cho restart.

```text
JobExecution #1: FAILED
  Chunk 1: COMMITTED
  Chunk 2: COMMITTED
  Chunk 3: ROLLED BACK
  Chunk 4: chưa chạy

Restart cùng JobInstance
  |
  v
JobExecution #2
  Khôi phục checkpoint sau Chunk 2
  Tiếp tục xử lý Chunk 3
```

Không nên mở một transaction duy nhất bao trùm toàn bộ Job. Nếu tất cả chunk tham gia transaction bên ngoài, các lần commit dự kiến có thể không trở thành commit độc lập; một lỗi cuối Job có thể làm rollback lượng lớn dữ liệu và phá vỡ kỳ vọng restart.

Đối với Tasklet, transaction được quản lý theo từng lần gọi `execute()`. Nếu Tasklet thực hiện file move hoặc gọi API, các tác dụng phụ ngoài database không tự rollback. Cần thiết kế kiểm tra trạng thái trước khi thực hiện lại.

## 13. Reader và dữ liệu nguồn phải ổn định

Checkpoint chỉ có ý nghĩa nếu cùng một vị trí vẫn trỏ đến cùng một phần dữ liệu khi restart. Một số rủi ro:

- File nguồn bị thay thế sau lần chạy đầu.
- Dữ liệu database thay đổi thứ tự vì query không có `ORDER BY` ổn định.
- Paging query dùng offset nhưng bản ghi mới được chèn/xóa làm vị trí trang dịch chuyển.
- Partition plan được tính lại với phạm vi khác.
- Reader tùy chỉnh không lưu đúng state sau commit.

Để bảo đảm restart:

1. Dùng file bất biến hoặc lưu checksum/version của file đầu vào.
2. Dùng query có thứ tự xác định bằng khóa duy nhất.
3. Với dữ liệu biến động, dùng snapshot, watermark hoặc thời điểm chốt dữ liệu.
4. Lưu thông tin phạm vi partition ổn định trong ExecutionContext.
5. Giữ tên reader và cấu trúc ExecutionContext tương thích giữa các lần chạy.

Nếu dữ liệu nguồn thay đổi mà không có snapshot, restart có thể bỏ sót hoặc đọc trùng item dù checkpoint được khôi phục chính xác theo vị trí cũ.

## 14. Restart và skip/retry

Restart, retry và skip là ba cơ chế khác nhau:

- **Retry:** thử lại thao tác lỗi trong cùng quá trình thực thi theo retry policy.
- **Skip:** bỏ qua item khi exception thuộc loại được phép skip và chưa vượt skip limit.
- **Restart:** tạo JobExecution mới cho JobInstance chưa hoàn thành và tiếp tục từ metadata/checkpoint đã lưu.

Khi restart:

- Item trong chunk đã commit thường không được đọc lại nếu Reader khôi phục đúng checkpoint.
- Item trong chunk rollback có thể được đọc và xử lý lại.
- Item đã skip trong chunk đã commit thường nằm trước checkpoint và không bị gặp lại.
- Item đã skip trong chunk rollback có thể được skip lại khi chunk được thực hiện lại.

Vì vậy, reject listener hoặc thao tác ghi lỗi cần idempotent. Nếu skip limit cần tích lũy xuyên nhiều JobExecution, hãy lưu bộ đếm nghiệp vụ riêng; không chỉ dựa vào skip count của một lần thực thi.

## 15. Kiểm thử khả năng restart

Một Job chỉ nên được xem là restartable sau khi kiểm tra được cả metadata và dữ liệu nghiệp vụ sau restart.

Kịch bản kiểm thử hữu ích:

1. Chuẩn bị dữ liệu đầu vào cố định và JobParameters định danh.
2. Chạy Job lần đầu và tạo lỗi có kiểm soát sau một vài chunk đã commit.
3. Xác nhận JobExecution đầu tiên là `FAILED`, các chunk trước đã commit và checkpoint đã lưu.
4. Sửa điều kiện lỗi hoặc dependency để Job có thể tiếp tục.
5. Restart cùng JobInstance bằng cùng identifying JobParameters.
6. Xác nhận JobExecution mới có ID khác nhưng JobInstance ID giống lần đầu.
7. Xác nhận Reader tiếp tục từ checkpoint, Writer không tạo dữ liệu trùng và Job kết thúc đúng trạng thái.
8. Kiểm tra các tác dụng phụ ngoài database như file, message hoặc API call không bị lặp ngoài ý muốn.

Với Spring Batch Test, `JobLauncherTestUtils` hỗ trợ launch Job/Step; `JobExplorer` hoặc `JobRepository` có thể tra cứu lịch sử JobExecution và StepExecution. Test nên dùng cùng identifying parameters giữa lần chạy đầu và restart. Nếu thêm UUID identifying mới, test sẽ tạo JobInstance mới và không còn kiểm tra restart.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nhầm restart với launch JobInstance mới | Xử lý lại toàn bộ dữ liệu như một công việc khác. | Giữ nguyên identifying JobParameters khi restart. |
| Reader không lưu state | Restart có thể đọc lại từ đầu hoặc không khôi phục đúng vị trí. | Dùng reader hỗ trợ ItemStream và bật lưu state. |
| Nguồn dữ liệu thay đổi giữa hai lần chạy | Checkpoint có thể trỏ đến dữ liệu khác, gây mất hoặc trùng item. | Dùng file bất biến, snapshot hoặc watermark. |
| Writer không idempotent | Item được thử lại có thể tạo bản ghi hoặc tác dụng phụ trùng. | Unique constraint, upsert, idempotency key hoặc outbox. |
| Dùng `preventRestart()` ngoài ý muốn | Job thất bại không thể tiếp tục cùng JobInstance. | Chỉ cấu hình khi nghiệp vụ thực sự cấm restart. |
| Bật `allowStartIfComplete(true)` cho Step có side effect | Step hoàn tất có thể chạy lại và gửi/gia tăng tác dụng phụ. | Bảo đảm Step idempotent trước khi bật. |
| Nhầm `startLimit` với retry limit | Giới hạn số lần bắt đầu Step thay vì số lần thử item. | Dùng retry policy cho item; startLimit cho số lần Step start. |
| Dùng repository in-memory cho restart qua process restart | Metadata có thể mất khi ứng dụng dừng. | Dùng JobRepository bền vững trong database. |
| Mở transaction bao trùm toàn Job | Chunk không commit độc lập và rollback có phạm vi quá lớn. | Đặt transaction boundary ở Step/chunk. |

## Kết luận

Restartable Job là Job có thể tiếp tục một JobInstance chưa hoàn thành bằng cách tạo JobExecution mới và sử dụng metadata/checkpoint đã lưu. Khả năng này dựa vào JobRepository bền vững, identifying JobParameters ổn định, Reader hỗ trợ lưu state, transaction boundary theo Step/chunk và Writer có khả năng xử lý lặp an toàn. `preventRestart()`, `allowStartIfComplete(true)` và `startLimit()` điều chỉnh chính sách restart ở cấp Job hoặc Step. Hãy kiểm thử bằng cách cố ý làm Job thất bại giữa chừng rồi restart cùng JobInstance, đồng thời xác nhận dữ liệu đầu ra và các tác dụng phụ không bị mất hoặc nhân đôi.

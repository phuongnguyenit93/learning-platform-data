# Step có thể restart từ checkpoint nào?

Trong Spring Batch, một Step có thể tiếp tục từ **checkpoint gần nhất đã được lưu thành công**. Với Step xử lý theo chunk, checkpoint thường tương ứng với ranh giới commit của chunk. Nếu một chunk gặp lỗi trước khi commit, transaction của chunk đó được rollback và dữ liệu trong chunk có thể được đọc, xử lý lại khi Job restart.

Checkpoint không phải vị trí mà Spring Batch tự đoán từ số dòng hoặc thời gian chạy. Đó là trạng thái do reader, writer hoặc logic của ứng dụng lưu vào **ExecutionContext**, sau đó được **JobRepository** duy trì để lần thực thi tiếp theo có thể khôi phục.

## 1. Checkpoint là gì?

Checkpoint là một mốc trạng thái đã được lưu để Step có thể tiếp tục công việc sau khi bị gián đoạn. Nó mô tả phần tiến độ mà framework và các thành phần xử lý có thể khôi phục.

Giả sử một Step đọc file CSV và ghi khách hàng vào database theo chunk 100 bản ghi:

~~~text
Chunk 1: dòng 1   - 100   -> ghi thành công -> COMMIT
Chunk 2: dòng 101 - 200   -> ghi thành công -> COMMIT
Chunk 3: dòng 201 - 300   -> đang xử lý     -> lỗi, ROLLBACK
~~~

Nếu ứng dụng gặp lỗi trong chunk 3, checkpoint gần nhất vẫn là sau chunk 2. Khi restart, Step tiếp tục từ trạng thái đã lưu sau chunk 2. Những bản ghi thuộc chunk 3 có thể được đọc và xử lý lại.

~~~text
Nguồn dữ liệu
     |
     v
[1 - 100]   COMMIT  <--- checkpoint 1
     |
     v
[101 - 200] COMMIT  <--- checkpoint 2
     |
     v
[201 - 300] ERROR
             |
             +---- ROLLBACK
                      |
                      v
                  RESTART
                      |
                      v
                Tiếp tục từ checkpoint 2
~~~

Vì vậy, câu trả lời thông thường cho câu hỏi “Step restart từ checkpoint nào?” là: **từ checkpoint cuối cùng đã được lưu và commit thành công**, chứ không phải từ item cuối cùng mà chương trình đã bắt đầu đọc.

Cách khôi phục cụ thể phụ thuộc vào loại Step, reader/writer có hỗ trợ lưu trạng thái hay không và ứng dụng có lưu checkpoint tùy chỉnh hay không.

## 2. ExecutionContext lưu checkpoint ở đâu?

Spring Batch dùng **ExecutionContext** để lưu dữ liệu trạng thái dạng key-value. Có hai phạm vi thường gặp:

| Phạm vi | Đối tượng sở hữu | Mục đích |
|---|---|---|
| Job ExecutionContext | JobExecution | Lưu dữ liệu cần chia sẻ giữa các Step trong cùng lần chạy Job |
| Step ExecutionContext | StepExecution | Lưu trạng thái riêng của Step, thường dùng cho vị trí đọc/ghi và checkpoint |

Checkpoint của reader thường nằm trong Step ExecutionContext vì tiến độ đọc thuộc về Step đang thực hiện.

Với JobRepository sử dụng database, Spring Batch lưu các ExecutionContext trong metadata repository, thường là:

- **BATCH_JOB_EXECUTION_CONTEXT**: ExecutionContext của JobExecution.
- **BATCH_STEP_EXECUTION_CONTEXT**: ExecutionContext của StepExecution.

Ví dụ một Step ExecutionContext có thể chứa dữ liệu như:

~~~text
{
    "customerReader.current.count": 200,
    "customerReader.read.count": 200,
    "lastProcessedCustomerId": 98765
}
~~~

Các key thực tế phụ thuộc vào reader, writer hoặc logic do ứng dụng triển khai. Không nên dựa vào tên key nội bộ của một reader cụ thể; hãy xem ExecutionContext như hợp đồng lưu trạng thái của thành phần đó.

### JobRepository có vai trò gì?

ExecutionContext chỉ tồn tại trong bộ nhớ của một đối tượng Java sẽ không đủ để restart sau khi tiến trình ứng dụng kết thúc. Trạng thái phải được lưu thông qua JobRepository.

Trong môi trường cần restart sau khi ứng dụng bị tắt hoặc máy chủ khởi động lại, hãy sử dụng JobRepository có khả năng lưu metadata bền vững, thường là repository dựa trên database. Repository chỉ lưu trong bộ nhớ sẽ mất dữ liệu khi tiến trình kết thúc và không thể cung cấp checkpoint cho một lần chạy mới sau đó.

## 3. Chunk Step restart từ ranh giới commit

Với chunk-oriented processing, Spring Batch đọc và xử lý dữ liệu theo nhóm. Mỗi chunk được xử lý trong transaction; khi chunk thành công, transaction được commit và checkpoint tương ứng được cập nhật.

Ví dụ Step có chunk size bằng 100:

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

Giả sử reader đọc một file có 1.000 dòng:

| Chunk | Dữ liệu | Kết quả | Checkpoint gần nhất |
|---|---:|---|---:|
| 1 | 1–100 | Commit thành công | Sau dòng 100 |
| 2 | 101–200 | Commit thành công | Sau dòng 200 |
| 3 | 201–300 | Writer gặp lỗi, rollback | Vẫn sau dòng 200 |
| 4 trở đi | Chưa được xử lý | Chưa chạy | Vẫn sau dòng 200 |

Khi restart, reader được khôi phục từ trạng thái sau chunk 2. Chunk 3 được thực hiện lại.

**Chunk size ảnh hưởng đến tần suất tạo checkpoint** trong mô hình chunk thông thường:

- Chunk nhỏ: checkpoint và commit thường xuyên hơn, lượng công việc phải làm lại khi lỗi thường ít hơn; đổi lại có thể tăng chi phí transaction và commit.
- Chunk lớn: ít lần commit hơn, có thể tăng hiệu năng trong một số trường hợp; đổi lại transaction kéo dài và có thể phải xử lý lại nhiều item hơn khi chunk thất bại.

Chunk size không phải một con số bảo đảm rằng đúng từng ấy bản ghi sẽ được ghi. Processor có thể lọc item bằng cách trả về null, skip policy có thể bỏ qua item lỗi và chunk cuối cùng có thể nhỏ hơn cấu hình.

### Vì sao chunk chưa commit được xử lý lại?

Giả sử chunk 3 đã đọc 100 item, processor đã chuyển đổi chúng và writer bắt đầu ghi. Nếu writer ném exception trước khi transaction commit, các thay đổi nằm trong transaction sẽ bị rollback.

Checkpoint của chunk trước đó vẫn là trạng thái gần nhất đã commit. Khi restart, reader khôi phục trạng thái này và đọc lại dữ liệu cần thiết cho chunk 3.

Điều này cũng có nghĩa processor có thể được gọi lại cho những item thuộc chunk chưa commit. Hãy thiết kế processor và các thao tác phụ trợ sao cho việc gọi lại không gây tác dụng phụ ngoài ý muốn.

## 4. ItemStream và cách reader lưu vị trí đọc

Spring Batch sử dụng hợp đồng **ItemStream** để các thành phần có trạng thái có thể mở, lưu và khôi phục trạng thái.

Ba phương thức quan trọng:

| Phương thức | Khi nào được gọi | Trách nhiệm |
|---|---|---|
| **open(ExecutionContext)** | Khi Step mở stream | Đọc trạng thái cũ hoặc khởi tạo trạng thái mới |
| **update(ExecutionContext)** | Tại thời điểm cập nhật checkpoint | Ghi tiến độ hiện tại vào ExecutionContext |
| **close()** | Khi Step đóng stream | Giải phóng tài nguyên |

Một reader hỗ trợ restart cần khôi phục được vị trí đọc trong open(), đồng thời cập nhật trạng thái trong update().

### Ví dụ với FlatFileItemReader

Các reader dựng sẵn như FlatFileItemReader hỗ trợ lưu trạng thái đọc. Có thể cấu hình reader như sau:

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

Các điểm cần chú ý:

- **name("customerReader")** đặt tên ổn định cho reader để trạng thái của nó được nhận diện trong ExecutionContext.
- **saveState(true)** cho phép reader lưu trạng thái cần thiết để restart.
- **@StepScope** giúp reader nhận JobParameters tại thời điểm Step chạy.
- **inputFile** phải trỏ tới đúng nguồn dữ liệu của JobInstance đang được restart.

Với reader có hỗ trợ ItemStream, Spring Batch có thể gọi các phương thức vòng đời stream và lưu checkpoint cùng metadata của Step.

Một số reader có tùy chọn saveState. Nếu đặt **saveState(false)**, reader không lưu trạng thái restart của nó. Khi đó, framework không thể khôi phục vị trí đọc từ checkpoint do reader cung cấp; cách xử lý khi restart phụ thuộc vào thiết kế của reader và nguồn dữ liệu, và thường có nguy cơ đọc lại từ đầu.

### Reader tự viết cần lưu trạng thái

Nếu bạn tự triển khai reader, hãy cung cấp cơ chế lưu và khôi phục vị trí. Ví dụ đơn giản dưới đây dùng mã khách hàng cuối cùng đã đọc:

~~~java
public class CustomerReader implements ItemStreamReader<Customer> {

    private long lastProcessedId;
    private CustomerRepository repository;

    public CustomerReader(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        lastProcessedId = executionContext.getLong("lastProcessedId", 0L);
    }

    @Override
    public Customer read() {
        Customer customer = repository.findNextAfter(lastProcessedId);

        if (customer != null) {
            lastProcessedId = customer.getId();
        }

        return customer;
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putLong("lastProcessedId", lastProcessedId);
    }

    @Override
    public void close() {
        // Giải phóng tài nguyên nếu reader có mở tài nguyên.
    }
}
~~~

Cơ chế trên minh họa ba việc:

1. open() lấy lại mã cuối cùng đã lưu.
2. read() lấy bản ghi tiếp theo và cập nhật vị trí hiện tại trong đối tượng reader.
3. update() ghi vị trí đó vào ExecutionContext tại checkpoint.

Trong ứng dụng thực tế, truy vấn findNextAfter phải có thứ tự ổn định và điều kiện phân trang rõ ràng. Nếu dữ liệu nguồn thay đổi trong lúc Job bị gián đoạn, chỉ lưu ID cuối cùng có thể chưa đủ để bảo đảm kết quả nhất quán.

Nếu một reader được bọc bên trong reader khác, hãy bảo đảm trạng thái của delegate cũng được quản lý. Có thể cần đăng ký stream delegate với Step bằng cơ chế stream(...), hoặc triển khai wrapper chuyển tiếp đầy đủ các lời gọi ItemStream. Nếu framework không biết một thành phần cần lưu trạng thái, checkpoint của thành phần đó có thể không được cập nhật.

## 5. Tasklet Step restart từ đâu?

Tasklet Step không tự động có checkpoint theo vị trí item giống chunk reader. Tasklet được gọi thông qua phương thức execute, và ứng dụng quyết định trạng thái nào cần lưu nếu công việc có thể tiếp tục giữa chừng.

Với Tasklet thực hiện một tác vụ ngắn, không có trạng thái trung gian, khi Step thất bại và được restart, tác vụ thường được chạy lại từ đầu.

Nếu Tasklet thực hiện công việc dài theo nhiều lượt, có thể lưu tiến độ vào Step ExecutionContext. Ví dụ, Tasklet xử lý một tập ID theo từng nhóm:

~~~java
@Bean
public Step rebuildIndexStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        IndexService indexService) {

    return new StepBuilder("rebuildIndexStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                ExecutionContext context = chunkContext
                        .getStepContext()
                        .getStepExecution()
                        .getExecutionContext();

                long lastId = context.getLong("lastId", 0L);

                long nextId = indexService.rebuildNextBatch(lastId, 500);

                if (nextId == lastId) {
                    return RepeatStatus.FINISHED;
                }

                context.putLong("lastId", nextId);
                return RepeatStatus.CONTINUABLE;
            }, transactionManager)
            .build();
}
~~~

Trong ví dụ:

- lastId là tiến độ đã lưu của Tasklet.
- Mỗi lần gọi xử lý một nhóm tối đa 500 bản ghi.
- Nếu còn dữ liệu, Tasklet cập nhật lastId và trả về CONTINUABLE.
- Khi hết dữ liệu, Tasklet trả về FINISHED.

TaskletStep thực hiện mỗi lần gọi Tasklet trong transaction. Khi trạng thái ExecutionContext được lưu cùng transaction thành công, lần restart có thể khôi phục checkpoint đã commit gần nhất.

Nếu Tasklet gọi API bên ngoài hoặc ghi file mà các thao tác đó không nằm trong cùng transaction, việc lưu lastId không tự động hoàn tác tác động bên ngoài khi transaction rollback. Cần thiết kế thao tác theo lô có khả năng chạy lại an toàn.

## 6. Điều kiện để Spring Batch khôi phục đúng checkpoint

Có checkpoint trong ExecutionContext chưa đủ. Việc restart còn phụ thuộc vào danh tính JobInstance, JobRepository và cách các thành phần xử lý lưu trạng thái.

### Dùng lại identifying JobParameters

Một JobInstance được xác định bởi tên Job và các identifying JobParameters.

Khi muốn restart một JobInstance đang thất bại hoặc bị dừng, hãy chạy lại với cùng bộ identifying parameters. Spring Batch dựa vào metadata cũ để tạo JobExecution mới thuộc JobInstance đó và khôi phục tiến độ của các Step.

~~~text
customerImportJob
       |
       +-- JobInstance(inputFile=customers.csv)
                |
                +-- JobExecution 1: FAILED
                |       |
                |       +-- importCustomersStep
                |               checkpoint: sau chunk 2
                |
                +-- JobExecution 2: RESTARTED
                        |
                        +-- importCustomersStep
                                tiếp tục sau chunk 2
~~~

Nếu thay đổi identifying parameter, chẳng hạn đổi inputFile, Spring Batch tạo JobInstance mới. JobInstance mới không tiếp tục từ checkpoint của JobInstance cũ.

Các parameter không identifying không làm thay đổi danh tính JobInstance. Tuy nhiên, hãy bảo đảm những giá trị ảnh hưởng tới việc xử lý vẫn phù hợp khi restart; không nên đổi chế độ xử lý giữa chừng nếu điều đó làm thay đổi ý nghĩa của checkpoint cũ.

### JobRepository phải giữ được metadata

Khi ứng dụng bị dừng hoàn toàn, checkpoint phải còn tồn tại trong repository. Nếu metadata chỉ nằm trong bộ nhớ của tiến trình đã kết thúc, lần chạy mới không thể tìm lại checkpoint cũ.

Trong môi trường production, thường dùng database-backed JobRepository và giữ nguyên các bảng metadata qua những lần triển khai hoặc khởi động lại ứng dụng.

### Reader và writer phải hỗ trợ trạng thái cần thiết

Các reader/writer có trạng thái cần triển khai ItemStream hoặc được đăng ký như stream với Step. Nếu thành phần không lưu tiến độ, framework không thể tự suy ra vị trí an toàn để tiếp tục.

Cần đặc biệt chú ý:

- Reader tự viết không lưu vị trí.
- Reader được bọc trong một wrapper không chuyển tiếp ItemStream.
- Reader đặt saveState(false).
- Nguồn dữ liệu thay đổi giữa hai lần chạy.
- Tên reader hoặc cấu hình reader thay đổi khiến trạng thái cũ không còn khớp.

Trong các trường hợp này, Step có thể đọc lại dữ liệu từ đầu, không khôi phục được đúng vị trí, hoặc khôi phục một vị trí không còn phù hợp với nguồn dữ liệu hiện tại.

## 7. Khi Job restart, Step nào được chạy lại?

Khả năng restart của Job và checkpoint của Step có liên quan nhưng không phải cùng một khái niệm.

Khi restart một JobInstance:

- Step đã hoàn thành thường được bỏ qua.
- Step thất bại hoặc chưa hoàn thành có thể được chạy lại từ checkpoint đã lưu.
- Step mới chưa từng chạy sẽ bắt đầu từ đầu.
- Step được cấu hình **allowStartIfComplete(true)** có thể được thực thi lại dù đã hoàn thành trước đó.

Ví dụ:

~~~text
Job lần 1
  |
  +--> validateInputStep       COMPLETED
  |
  +--> importCustomersStep     FAILED
         checkpoint: chunk 8
  |
  +--> createReportStep        NOT STARTED

Job restart
  |
  +--> validateInputStep       SKIPPED
  |
  +--> importCustomersStep     RESTART từ checkpoint chunk 8
  |
  +--> createReportStep        START từ đầu
~~~

### allowStartIfComplete không phải là checkpoint

Có thể cấu hình:

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

**allowStartIfComplete(true)** cho phép Step đã hoàn thành được thực thi lại khi JobInstance được restart. Cấu hình này điều khiển việc Step có được phép chạy lại hay không; nó không tự tạo ra checkpoint mới và cũng không thay thế cơ chế lưu trạng thái của reader hoặc Tasklet.

Hãy xác định rõ ý nghĩa khi Step chạy lại, đặc biệt với tác vụ tạo báo cáo, gửi thông báo hoặc gọi hệ thống ngoài. Nếu Step không an toàn khi thực hiện nhiều lần, cần có cơ chế chống trùng.

### startLimit không xác định checkpoint

startLimit giới hạn số lần Step được phép bắt đầu. Nó không quyết định vị trí đọc tiếp theo.

~~~java
new StepBuilder("importCustomersStep", jobRepository)
        .<RawCustomer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .startLimit(3)
        .build();
~~~

Nếu Step đã vượt quá giới hạn bắt đầu, lần restart tiếp theo có thể bị từ chối. Việc tăng startLimit không thay thế việc lưu checkpoint đúng cách.

Tương tự, preventRestart() là cấu hình ở cấp Job để không cho phép restart Job. Nó không thay đổi cách một reader lưu vị trí đọc.

## 8. Checkpoint và transaction: điều gì được làm lại?

Checkpoint thường được gắn với ranh giới transaction của chunk. Điều này tạo ra một số tình huống:

| Tình huống | Hành vi thường gặp khi restart |
|---|---|
| Chunk đã commit | Tiếp tục sau checkpoint của chunk đó |
| Chunk đang xử lý nhưng rollback | Đọc và xử lý lại dữ liệu thuộc chunk chưa commit |
| Step thất bại trước checkpoint đầu tiên | Bắt đầu lại từ trạng thái ban đầu |
| Reader không lưu trạng thái | Không thể khôi phục vị trí do reader cung cấp; có thể đọc lại từ đầu |
| Step đã hoàn thành | Thường được bỏ qua khi restart Job |
| Step mới chưa chạy | Bắt đầu từ đầu |

### Tác động ngoài transaction

Transaction của Step thường bảo vệ các thao tác nằm trong transaction manager tương ứng, chẳng hạn ghi dữ liệu vào cùng database. Tuy nhiên, một lời gọi HTTP, gửi email hoặc ghi file bên ngoài không tự động được rollback cùng database transaction.

Ví dụ:

1. Writer gọi API để tạo hóa đơn.
2. API tạo hóa đơn thành công.
3. Database transaction của chunk gặp lỗi trước commit.
4. Spring Batch rollback chunk.
5. Job restart và gọi lại API cho cùng hóa đơn.

Nếu API không hỗ trợ idempotency, hệ thống có thể tạo hóa đơn trùng. Vì vậy, hãy sử dụng mã giao dịch duy nhất, idempotency key, bảng outbox hoặc cơ chế kiểm tra trạng thái phù hợp với nghiệp vụ.

**Checkpoint bảo đảm khả năng khôi phục tiến độ metadata; nó không tự bảo đảm mọi tác động bên ngoài chỉ xảy ra một lần.**

### Skip và retry ảnh hưởng thế nào?

Trong chunk processing, retry có thể khiến một item được xử lý lại trong cùng lần chạy. Skip policy có thể cho phép bỏ qua item lỗi để chunk tiếp tục.

Khi chunk cuối cùng commit, checkpoint phản ánh tiến độ đã hoàn tất của chunk đó, bao gồm cả những item được xử lý thành công và các item được skip theo cấu hình. Khi restart sau checkpoint này, các item đã được ghi nhận là skip không tự động được đưa lại vào xử lý như thể chưa từng gặp lỗi.

Hãy theo dõi readCount, writeCount, filterCount, các skip count và log lỗi để hiểu chính xác dữ liệu nào đã được xử lý, lọc hoặc bỏ qua.

## 9. Nguồn dữ liệu thay đổi có thể làm checkpoint mất ý nghĩa

Checkpoint của reader chỉ có ý nghĩa khi nguồn dữ liệu ở lần restart tương thích với nguồn dữ liệu lúc tạo checkpoint.

Ví dụ reader lưu vị trí sau dòng 10.000 của file customers.csv. Sau khi Job lỗi, một người thay file bằng phiên bản khác có thêm hoặc xóa dòng. Reader tiếp tục từ vị trí đã lưu nhưng nội dung tại vị trí đó có thể không còn là bản ghi mong đợi.

Một số biện pháp thực tế:

- Dùng file đầu vào bất biến cho mỗi JobInstance.
- Đưa mã file, phiên bản dữ liệu hoặc ngày nghiệp vụ vào identifying JobParameters.
- Lưu checksum hoặc metadata nguồn nếu nghiệp vụ yêu cầu xác minh nguồn không đổi.
- Với database paging, dùng khóa sắp xếp ổn định và điều kiện truy vấn có thể tái lập.
- Tránh phân trang theo offset trên một tập dữ liệu liên tục thay đổi mà không có snapshot hoặc điều kiện nhất quán.

Nếu dữ liệu nguồn có thể thay đổi, cần định nghĩa rõ một JobInstance đang xử lý snapshot nào. Chỉ lưu số dòng hoặc ID cuối cùng chưa chắc đã đủ.

## 10. Checkpoint trong partitioned Step

Với partitioning, một Step được chia thành nhiều partition để xử lý song song hoặc phân tán. Mỗi partition có StepExecution và ExecutionContext riêng.

~~~text
masterStep
   |
   +--> partition 0
   |       checkpoint riêng
   |
   +--> partition 1
   |       checkpoint riêng
   |
   +--> partition 2
           checkpoint riêng
~~~

Khi một partition thất bại, lần restart có thể khôi phục partition đó từ checkpoint riêng của nó, trong khi các partition đã hoàn thành được xử lý theo trạng thái đã lưu.

Điều này đòi hỏi:

- Mỗi partition có phạm vi dữ liệu ổn định và không chồng lấn ngoài ý muốn.
- Reader của từng partition lưu được trạng thái cần thiết.
- Metadata của từng StepExecution được lưu bền vững.
- Tài nguyên dùng chung được quản lý an toàn khi nhiều partition chạy đồng thời.

Checkpoint của master Step không thay thế checkpoint của từng worker Step. Khi debug một Job partitioned, hãy xem ExecutionContext và trạng thái của từng StepExecution tương ứng.

## 11. Ví dụ lần chạy lỗi và restart

Giả sử Job nhập file có 450 bản ghi, chunk size là 100.

Lần chạy đầu:

~~~text
Chunk 1: 1   - 100  -> COMMITTED
Chunk 2: 101 - 200  -> COMMITTED
Chunk 3: 201 - 300  -> COMMITTED
Chunk 4: 301 - 400  -> FAILED, ROLLBACK
Chunk 5: 401 - 450  -> chưa chạy
~~~

Tại thời điểm lỗi, checkpoint gần nhất là sau chunk 3. Khi restart với cùng JobInstance và reader hỗ trợ khôi phục trạng thái:

~~~text
Chunk 1: đã commit -> không cần xử lý lại
Chunk 2: đã commit -> không cần xử lý lại
Chunk 3: đã commit -> không cần xử lý lại
Chunk 4: đọc và xử lý lại từ trạng thái sau chunk 3
Chunk 5: tiếp tục sau khi chunk 4 hoàn tất
~~~

Nếu chunk 4 được commit thành công trong lần restart, checkpoint mới chuyển tới sau bản ghi 400. Sau đó Job xử lý 50 bản ghi cuối.

Nếu reader không lưu trạng thái, kết quả có thể khác: reader có thể bắt đầu lại từ đầu. Khi đó writer và dữ liệu đích phải có cơ chế tránh ghi trùng hoặc phải được thiết kế để xử lý lại an toàn.

## 12. Theo dõi checkpoint khi điều tra lỗi

Khi một Step không restart từ vị trí bạn mong đợi, hãy quan sát metadata của lần chạy trước và cấu hình stream.

| Thông tin | Cần hiểu điều gì |
|---|---|
| JobInstance | Lần restart có đang dùng đúng identifying JobParameters không? |
| JobExecution | Lần chạy trước kết thúc ở trạng thái nào? |
| StepExecution | Step thất bại hay đã hoàn thành? |
| ExecutionContext | Trạng thái checkpoint cuối cùng được lưu là gì? |
| readCount | Có bao nhiêu item đã được đọc trong execution đó? |
| writeCount | Có bao nhiêu item đã được ghi? |
| commitCount | Có bao nhiêu transaction chunk đã commit? |
| Reader configuration | Reader có hỗ trợ ItemStream và lưu trạng thái không? |
| JobRepository | Metadata có được lưu bền vững không? |

Có thể xem metadata trong các bảng repository như BATCH_JOB_EXECUTION, BATCH_STEP_EXECUTION và BATCH_STEP_EXECUTION_CONTEXT. Khi đọc dữ liệu, cần đối chiếu đúng JobExecution và StepExecution thuộc JobInstance đang restart.

Đừng chỉ dựa vào readCount để suy ra chính xác vị trí đọc. Reader có thể đọc trước, lọc item hoặc thực hiện logic phân trang riêng. ExecutionContext của reader mới là nơi chứa trạng thái khôi phục mà thành phần đó cung cấp.

## 13. Nguyên tắc thiết kế Step có thể restart

Khi xây dựng Step, hãy quyết định ngay từ đầu dữ liệu nào cần được lưu để tiếp tục công việc.

- Với xử lý theo chunk, chọn chunk size phù hợp và dùng reader/writer có hỗ trợ ItemStream khi cần khôi phục trạng thái.
- Với reader tự viết, triển khai open, update, close và lưu một vị trí có thể tái lập.
- Với Tasklet dài, lưu tiến độ nghiệp vụ trong Step ExecutionContext tại các ranh giới transaction an toàn.
- Giữ identifying JobParameters ổn định khi restart JobInstance cũ.
- Dùng JobRepository bền vững nếu cần restart sau khi tiến trình hoặc máy chủ dừng.
- Giữ nguồn dữ liệu ổn định trong suốt vòng đời của JobInstance.
- Thiết kế các tác động ngoài transaction có tính idempotent hoặc có cơ chế chống trùng.
- Kiểm tra từng partition riêng nếu dùng partitioning.
- Phân biệt Step đã hoàn thành với Step thất bại; Step hoàn thành thường được bỏ qua trong lần restart Job.

Điểm cốt lõi là checkpoint phản ánh **trạng thái gần nhất mà Step đã lưu an toàn**. Với chunk Step, đó thường là chunk cuối cùng đã commit. Với Tasklet hoặc reader tự viết, ứng dụng phải lưu đủ trạng thái để có thể tiếp tục đúng công việc. Khi checkpoint, JobParameters, JobRepository và nguồn dữ liệu được quản lý nhất quán, Spring Batch có thể restart một Job mà không cần xử lý lại toàn bộ dữ liệu đã hoàn tất.

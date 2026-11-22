# Kiểm thử nhiều loại lỗi

Trong Spring Batch, một Job có thể gặp nhiều loại lỗi ở những giai đoạn khác nhau: đọc dữ liệu, xử lý item, ghi kết quả, truy cập database, gọi service ngoài hoặc khôi phục sau khi ứng dụng dừng. Mỗi loại lỗi có thể cần một cách xử lý khác nhau. Có lỗi phải làm Step thất bại ngay; có lỗi tạm thời nên retry; có lỗi dữ liệu được phép skip; có lỗi cần rollback transaction; và có lỗi chỉ xuất hiện khi restart.

Kiểm thử fault tolerance cần xác nhận cả hai mặt: ứng dụng phản ứng đúng với lỗi và dữ liệu sau lỗi vẫn nhất quán. Chỉ kiểm tra Job trả về `COMPLETED` hoặc `FAILED` là chưa đủ. Cần kiểm tra exception, số lần retry, skip count, listener, transaction, dữ liệu đã commit và trạng thái khi restart.

## 1. Xác định các nhóm lỗi cần kiểm thử

Trước khi viết test, hãy liệt kê lỗi theo vị trí phát sinh và kết quả mong muốn.

| Vị trí | Ví dụ lỗi | Hành vi thường cần kiểm tra |
|---|---|---|
| ItemReader | Dòng CSV sai định dạng, lỗi parse, nguồn dữ liệu tạm thời không truy cập được | Skip lỗi dữ liệu được cho phép; retry lỗi tạm thời nếu phù hợp; dừng với lỗi không thể phục hồi |
| ItemProcessor | Validation thất bại, dữ liệu tham chiếu không tồn tại, timeout khi gọi service | Skip lỗi nghiệp vụ được cho phép; retry lỗi phụ thuộc tạm thời; không skip lỗi lập trình |
| ItemWriter | Constraint violation, deadlock, database unavailable | Rollback chunk khi cần; retry deadlock; skip item ghi lỗi nếu nghiệp vụ cho phép |
| Transaction | Deadlock, lock timeout, commit failure | Transaction được rollback đúng; lần thử lại chạy trong transaction phù hợp |
| Service ngoài | HTTP 429, 5xx, timeout, response không hợp lệ | Timeout, retry/backoff, phân loại lỗi và idempotency |
| Restart | Tiến trình dừng sau một số chunk đã commit | Khôi phục checkpoint; không ghi trùng hoặc bỏ sót dữ liệu |
| Skip policy | Skip vượt ngưỡng, exception không được phép skip | Step thất bại và metadata phản ánh đúng số lượng lỗi |

Không nên gộp mọi lỗi thành một nhóm `Exception`. Một lỗi dữ liệu không hợp lệ và một lỗi database mất kết nối có ý nghĩa vận hành rất khác nhau.

## 2. Chiến lược kiểm thử fault tolerance

Một bộ test tốt nên đi từ thành phần nhỏ đến toàn bộ Step hoặc Job:

1. **Unit test reader/processor/writer:** kiểm tra mapping dữ liệu, exception và quy tắc nghiệp vụ.
2. **Step integration test:** chạy Step thật với reader, processor, writer và transaction manager thử nghiệm để kiểm tra skip, retry, rollback và counters.
3. **Job integration test:** chạy toàn bộ Job để kiểm tra flow, trạng thái Step và restart.
4. **Dependency integration test:** dùng database hoặc HTTP server giả lập để kiểm tra lỗi giao tiếp, timeout và transaction thực tế.
5. **Failure/restart test:** chủ động làm Job thất bại giữa chừng rồi chạy lại cùng JobInstance.

Test nên kích hoạt lỗi có chủ đích và xác định trước kết quả mong đợi. Tránh phụ thuộc vào lỗi ngẫu nhiên như làm database thật mất kết nối hoặc chờ một timeout dài trong mỗi lần chạy test.

## 3. Chuẩn bị Spring Batch Test

Spring Batch cung cấp module `spring-batch-test` với các tiện ích để chạy Job/Step trong test và truy cập metadata.

Với dự án Spring Boot, thêm dependency test tương ứng với phiên bản Spring Batch đang dùng. Với Gradle, khai báo theo dependency management của dự án, ví dụ:

```groovy
testImplementation("org.springframework.batch:spring-batch-test")
testImplementation("org.springframework.boot:spring-boot-starter-test")
testRuntimeOnly("com.h2database:h2")
```

Nếu không dùng Spring Boot, cần khai báo các dependency JUnit, Spring Test, Spring Batch Test và database test tương thích.

Ví dụ cấu trúc test:

```java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class ImportJobFaultToleranceTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    JobRepositoryTestUtils jobRepositoryTestUtils;

    @AfterEach
    void cleanUp() {
        jobRepositoryTestUtils.removeJobExecutions();
    }
}
```

`@SpringBatchTest` đăng ký các thành phần hỗ trợ test Spring Batch, bao gồm `JobLauncherTestUtils`, `JobRepositoryTestUtils` và các listener hỗ trợ scope. Cần cung cấp Job/Step và `JobRepository` trong test application context. Dùng database test riêng để tránh xóa hoặc thay đổi metadata của môi trường khác.

`JobLauncherTestUtils` có thể chạy toàn bộ Job hoặc một Step cụ thể. Ví dụ:

```java
JobExecution execution = jobLauncherTestUtils.launchJob(jobParameters);

JobExecution stepExecution = jobLauncherTestUtils.launchStep(
        "importOrdersStep", jobParameters);
```

Tên method và overload cần đối chiếu với phiên bản `spring-batch-test` của dự án. Nếu test context có nhiều Job, hãy cấu hình Job mà `JobLauncherTestUtils` cần chạy một cách tường minh.

## 4. Kiểm tra trạng thái Job và Step

Sau khi launch, kiểm tra trạng thái cuối cùng và metadata của StepExecution:

```java
JobExecution execution = jobLauncherTestUtils.launchJob(jobParameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());
assertEquals(ExitStatus.COMPLETED, execution.getExitStatus());

StepExecution stepExecution = execution.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.COMPLETED, stepExecution.getStatus());
assertEquals(10, stepExecution.getReadCount());
```

Với test lỗi, có thể kỳ vọng `BatchStatus.FAILED` và kiểm tra `ExitStatus` hoặc exception được ghi nhận. Không nên chỉ assert trạng thái Job; hãy lấy đúng StepExecution để biết lỗi phát sinh ở đâu.

Các bộ đếm thường cần kiểm tra:

- `readCount`: số item reader đã đọc.
- `writeCount`: số item được writer ghi theo metadata của Step.
- `filterCount`: số item processor chủ động lọc bằng cách trả `null`.
- `readSkipCount`, `processSkipCount`, `writeSkipCount`: số skip ở từng giai đoạn.
- `rollbackCount`: số lần rollback được ghi nhận.
- `commitCount`: số lần commit được ghi nhận.
- `skipCount`: tổng số skip của Step.

Ý nghĩa bộ đếm có thể bị ảnh hưởng bởi retry, buffering và loại reader/writer. Hãy kết hợp counters với dữ liệu thực tế trong database hoặc output file để xác nhận kết quả nghiệp vụ.

## 5. Kiểm thử lỗi đọc dữ liệu

Reader có thể lỗi khi parse file, chuyển đổi kiểu, đọc database hoặc lấy dữ liệu từ API. Nên tách lỗi dữ liệu có thể skip khỏi lỗi nguồn/hạ tầng cần dừng hoặc retry.

### Test lỗi parse file được skip

Với `FlatFileItemReader`, có thể tạo resource test chứa một dòng hợp lệ và một dòng sai định dạng. Cấu hình reader dùng strict parsing để dòng lỗi tạo `FlatFileParseException`, rồi cấu hình Step cho phép skip loại exception đó.

Ví dụ cấu hình Step:

```java
return new StepBuilder("readFileStep", jobRepository)
        .<CustomerInput, Customer>chunk(10, transactionManager)
        .reader(fileReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(2)
        .listener(skipListener)
        .build();
```

Test cần xác nhận:

- Step hoàn tất khi số dòng lỗi nằm trong giới hạn.
- `readSkipCount` tăng theo số dòng bị skip.
- Các dòng hợp lệ vẫn được ghi.
- `SkipListener.onSkipInRead()` được gọi.
- Dòng lỗi không tạo ra item giả trong output.

Với lỗi reader không thể khôi phục, chẳng hạn database connection bị đóng, không nên tự động skip như lỗi parse. Có thể cấu hình retry cho lỗi tạm thời hoặc để Step thất bại nếu nguồn không còn khả dụng.

### Test reader ném exception theo kịch bản

Một reader giả lập giúp chủ động tạo lỗi ở lần đọc cụ thể:

```java
public class FailingOnceReader implements ItemReader<String> {

    private final AtomicBoolean fail = new AtomicBoolean(true);
    private int index;

    private final List<String> values = List.of("A", "B", "C");

    @Override
    public String read() {
        if (index == 1 && fail.compareAndSet(true, false)) {
            throw new TransientDataAccessResourceException(
                    "Temporary source failure");
        }

        if (index >= values.size()) {
            return null;
        }

        return values.get(index++);
    }
}
```

Đây là test double minh họa; cách tăng index và khôi phục vị trí cần được điều chỉnh theo hành vi muốn kiểm tra. Với reader có trạng thái, nên triển khai `ItemStream` hoặc dùng reader test chuyên biệt để kiểm tra checkpoint chính xác. Test phải chứng minh lỗi được retry/skip theo policy và không làm mất item kế tiếp.

## 6. Kiểm thử lỗi trong ItemProcessor

Processor thường phát sinh lỗi validation, dữ liệu tham chiếu không tồn tại hoặc lỗi khi gọi service. Có thể dùng processor thật với service mock để tạo exception có kiểm soát.

Ví dụ processor:

```java
public class CustomerProcessor
        implements ItemProcessor<CustomerInput, Customer> {

    private final CustomerValidationService validationService;

    public CustomerProcessor(CustomerValidationService validationService) {
        this.validationService = validationService;
    }

    @Override
    public Customer process(CustomerInput item) {
        validationService.validate(item);
        return new Customer(item.customerId(), item.name());
    }
}
```

Trong test, cấu hình mock ném exception cho một business key:

```java
doThrow(new InvalidCustomerException("Invalid customer"))
        .when(validationService)
        .validate(argThat(item -> item.customerId().equals("C-002")));
```

Nếu `InvalidCustomerException` được cấu hình skip, test nên xác nhận:

- `processSkipCount` tăng đúng.
- Item `C-002` không xuất hiện trong output.
- Các item hợp lệ trước và sau nó vẫn được ghi.
- `SkipListener.onSkipInProcess()` nhận đúng item và exception.
- Job chỉ thất bại nếu tổng skip vượt limit hoặc phát sinh lỗi không được xử lý.

Nếu processor trả `null` cho một item, đó là filter. Test cần xác nhận `filterCount` tăng và skip count không tăng. Phân biệt hai trường hợp này giúp tránh đánh giá sai chất lượng dữ liệu.

## 7. Kiểm thử lỗi trong ItemWriter

Writer nhận một chunk gồm nhiều item nên lỗi ghi có thể ảnh hưởng cả nhóm. Nên kiểm thử tối thiểu ba tình huống:

1. Writer ném exception trước khi ghi bất kỳ item nào.
2. Writer ghi một phần rồi ném exception.
3. Writer gặp lỗi tạm thời ở lần đầu nhưng thành công ở lần retry.

Ví dụ writer giả lập lỗi một lần:

```java
public class FailingOnceWriter implements ItemWriter<Order> {

    private final AtomicBoolean fail = new AtomicBoolean(true);
    private final List<Order> written = new ArrayList<>();

    @Override
    public void write(Chunk<? extends Order> chunk) {
        if (fail.compareAndSet(true, false)) {
            throw new TransientDataAccessException("Temporary write failure") {};
        }

        written.addAll(chunk.getItems());
    }

    public List<Order> getWritten() {
        return List.copyOf(written);
    }
}
```

Writer trên minh họa việc cố tình ném lỗi một lần. Danh sách trong bộ nhớ không rollback theo transaction database, vì vậy không dùng nó để chứng minh tính nguyên tử của transaction. Khi kiểm tra rollback thực tế, hãy dùng database test và writer tham gia transaction.

### Kiểm tra rollback khi writer ghi dở

Một integration test có thể cấu hình writer ghi vào bảng H2 rồi ném exception giữa chunk. Sau khi Step thất bại, truy vấn database để xác nhận những insert thuộc transaction chưa commit đã được rollback.

Test cần phân biệt:

- Bản ghi của chunk trước đã commit phải còn.
- Bản ghi của chunk lỗi phải được rollback nếu exception yêu cầu rollback.
- Nếu retry thành công, chunk được ghi đúng một lần.
- Nếu skip được cấu hình cho một item ghi lỗi, chỉ những item hợp lệ được lưu theo policy.

Với writer dùng HTTP API, email hoặc file system, transaction database không thể tự rollback tác dụng phụ ngoài đó. Hãy mock dependency để kiểm tra idempotency key hoặc dùng outbox trong integration test riêng.

## 8. Kiểm thử retry và giới hạn retry

Retry phù hợp với lỗi tạm thời như deadlock, lock acquisition failure hoặc service timeout có khả năng tự hết. Test nên kiểm tra cả trường hợp retry thành công và trường hợp đã hết số lần thử.

Ví dụ cấu hình:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
```

Test retry thành công nên dùng một dependency giả lập ném lỗi trong những lần đầu rồi trả kết quả ở lần tiếp theo. Có thể dùng Mockito:

```java
when(exchangeService.lookup("C-100"))
        .thenThrow(new TransientDataAccessException("Temporary") {})
        .thenReturn(new CustomerProfile("C-100", "ACTIVE"));
```

Sau khi chạy Step, xác nhận Job hoàn tất và dependency được gọi lại theo chính sách retry. Không nên hard-code một số lần gọi trong test nếu test chưa xác định rõ cách tính `retryLimit` của phiên bản Spring Batch đang dùng; hãy dựa vào hợp đồng API và cấu hình thực tế.

Test retry exhausted cần cấu hình dependency luôn ném exception. Xác nhận Step thất bại, lỗi cuối cùng được giữ trong metadata và không có dữ liệu đầu ra không hợp lệ.

### Kiểm thử backoff

Nếu dùng backoff, tránh để test chờ nhiều giây không cần thiết. Có thể cấu hình interval rất nhỏ trong test hoặc dùng policy giả lập để xác nhận policy được gắn vào Step. Test tích hợp cần kiểm tra số lần thử và trạng thái cuối; đo thời gian thực chỉ nên dùng khi thật sự cần kiểm tra tích hợp scheduler/backoff.

## 9. Kiểm thử skip và skip limit

Với skip, nên có ba nhóm test:

- Exception được cho phép skip và tổng skip nằm trong limit.
- Exception không được phép skip.
- Tổng số skip vượt limit.

Ví dụ cấu hình:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(2)
```

Test với hai item lỗi cần xác nhận Step có thể hoàn tất, `skipCount` bằng 2 và các item hợp lệ được ghi. Test với ba item lỗi cần xác nhận Step thất bại do vượt limit. Skip limit áp dụng chung cho read, process và write, vì vậy có thể kiểm tra nhiều giai đoạn trong cùng một Step để xác nhận tổng số skip.

Một test riêng nên ném exception không được khai báo skippable. Step phải thất bại ngay theo chính sách, dù số skip trước đó còn thấp hơn limit.

### Kiểm tra SkipListener

Mock listener hoặc service lưu dead-letter record để xác nhận callback tương ứng:

```java
verify(skipListener).onSkipInProcess(
        argThat(item -> item.customerId().equals("C-002")),
        isA(InvalidCustomerException.class));
```

Với read skip, callback chỉ nhận exception vì reader có thể chưa tạo được item. Với write skip, callback nhận item đầu ra. Không dùng `ItemProcessListener.onProcessError()` để thay thế kiểm tra skip cuối cùng vì một lỗi có thể được retry rồi thành công.

## 10. Kiểm thử rollback và noRollback

`noRollback()` thay đổi rollback classification cho một loại exception. Đây là cấu hình nhạy cảm vì có thể giữ lại các thay đổi đã thực hiện trong transaction.

Ví dụ:

```java
.faultTolerant()
.skip(ValidationException.class)
.skipLimit(10)
.noRollback(ValidationException.class)
```

Test nên so sánh hai cấu hình:

1. Exception writer mặc định làm transaction rollback.
2. Exception được khai báo no-rollback và được skip theo policy.

Trong test, dùng database test và truy vấn dữ liệu sau khi Step kết thúc để xác nhận chính xác bản ghi nào đã commit. Đặc biệt, tạo một writer có thể ném exception sau khi ghi một phần để chứng minh no-rollback có thể để lại partial write nếu cấu hình sai.

Chỉ dùng no-rollback cho exception phát sinh trong tình huống đã biết không có thay đổi nào cần hoàn tác, chẳng hạn validation toàn bộ chunk trước khi writer bắt đầu ghi. Không nên dùng no-rollback cho deadlock hoặc lỗi kết nối database.

## 11. Kiểm thử lỗi service ngoài

Nếu processor hoặc writer gọi REST API, nên kiểm tra từng nhóm phản hồi:

| Phản hồi | Cách xử lý thường gặp | Điều cần assert |
|---|---|---|
| HTTP 400/422 do dữ liệu không hợp lệ | Lỗi nghiệp vụ; có thể skip nếu được phép | Item bị skip hoặc Step thất bại đúng policy |
| HTTP 401/403 | Lỗi cấu hình/xác thực | Step thất bại, không retry vô hạn |
| HTTP 429 | Tôn trọng quota/Retry-After, retry có giới hạn | Số lần gọi và backoff phù hợp |
| HTTP 5xx | Có thể retry | Thành công sau retry hoặc thất bại khi hết limit |
| Connect/read timeout | Có thể retry nếu thao tác an toàn | Timeout được áp dụng và retry có giới hạn |
| Response sai schema | Lỗi hợp đồng dữ liệu | Phân loại rõ, không coi như lỗi mạng tạm thời |

Dùng HTTP stub server hoặc mock client để trả từng response. Không phụ thuộc API production trong unit test.

Nếu request tạo tác dụng phụ, chẳng hạn tạo giao dịch hoặc gửi lệnh thanh toán, test cần xác nhận cùng một idempotency key được dùng qua các lần retry. Một timeout không chứng minh server chưa thực hiện thao tác; server có thể đã commit nhưng response bị mất.

## 12. Kiểm thử restart sau lỗi

Restart là một trong những kiểm thử quan trọng nhất của fault tolerance. Cần mô phỏng tình huống một số chunk đã commit, chunk tiếp theo thất bại, rồi Job được khởi chạy lại với cùng identifying JobParameters.

Một kịch bản điển hình:

```text
Lần chạy đầu:
  Chunk 1 -> commit
  Chunk 2 -> commit
  Chunk 3 -> exception -> rollback
  Job -> FAILED

Restart cùng JobInstance:
  Khôi phục checkpoint đã lưu
  Chunk 1 và 2 không bị ghi lại
  Tiếp tục phần chưa hoàn tất
  Job -> COMPLETED
```

Để test restart đáng tin cậy:

1. Dùng reader hỗ trợ `ItemStream` và `saveState`.
2. Dùng `JobRepository` bền vững trong suốt hai lần launch.
3. Dùng cùng identifying JobParameters cho lần restart.
4. Tạo lỗi có chủ đích ở một chunk sau khi đã có chunk commit.
5. Xác nhận lần đầu `FAILED` và dữ liệu của các chunk đã commit vẫn tồn tại.
6. Launch lại JobInstance và xác nhận Step tiếp tục theo checkpoint.
7. Kiểm tra kết quả cuối không thiếu hoặc trùng item.

Ví dụ khung test:

```java
@Test
void restartsFailedJobFromSavedCheckpoint() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
            .addString("inputVersion", "fixture-v1")
            .toJobParameters();

    JobExecution first = jobLauncherTestUtils.launchJob(parameters);
    assertEquals(BatchStatus.FAILED, first.getStatus());

    JobExecution restarted = jobLauncherTestUtils.launchJob(parameters);
    assertEquals(BatchStatus.COMPLETED, restarted.getStatus());

    assertEquals(expectedIds, outputRepository.findAllIds());
}
```

Ví dụ giả định test fixture làm lỗi đúng một lần và giữ nguyên JobRepository, input cùng output database giữa hai lần launch. Không tạo identifying parameter mới cho lần restart; nếu thêm timestamp hoặc UUID mới, Spring Batch sẽ tạo JobInstance khác và chạy như một công việc mới.

## 13. Kiểm thử nhiều lỗi trong cùng một Job

Một Job thực tế có thể gặp lỗi ở nhiều giai đoạn. Có thể xây dựng một test matrix để xác nhận từng loại lỗi và kết quả:

| Kịch bản | Cấu hình | Kết quả mong đợi |
|---|---|---|
| Một dòng file sai định dạng | Skip parse exception, limit còn | Dòng lỗi bị skip; dòng hợp lệ được ghi |
| Một item validation thất bại | Skip validation exception | Process skip count tăng; listener ghi nhận item |
| Database deadlock một lần | Retry deadlock exception | Transaction được thử lại; chunk commit khi thành công |
| Database luôn lỗi | Retry có giới hạn | Step thất bại sau khi hết retry |
| Số item lỗi vượt skip limit | Skip policy và limit nhỏ | Step thất bại khi vượt ngưỡng |
| Writer ném lỗi sau partial write | Rollback mặc định | Không còn partial write trong transaction bị rollback |
| Validation writer được no-rollback | Skip + noRollback cụ thể | Item được xử lý theo policy; xác nhận không có thay đổi ngoài dự kiến |
| Ứng dụng dừng sau chunk commit | Reader lưu checkpoint | Restart tiếp tục và không ghi trùng |
| Service ngoài timeout sau khi server đã xử lý | Idempotency key | Retry không tạo tác dụng phụ trùng |

Không nhất thiết phải tạo một test duy nhất chứa tất cả lỗi. Các test nhỏ theo kịch bản giúp xác định nguyên nhân thất bại rõ hơn. Sau đó có thể có một số integration test end-to-end để xác nhận các chính sách kết hợp với nhau.

## 14. Dùng test doubles để tạo lỗi có kiểm soát

Một số kỹ thuật thường dùng:

- **Mockito:** cấu hình mock ném exception ở lần gọi đầu, trả kết quả ở lần sau hoặc luôn thất bại.
- **Fault-injecting reader/processor/writer:** component test tự viết để ném lỗi tại item hoặc lần gọi được chọn.
- **Database test:** tạo constraint violation, lock conflict hoặc transaction rollback trên database thử nghiệm.
- **HTTP stub server:** mô phỏng 429, 5xx, timeout và response sai định dạng.
- **Barrier/latch:** đồng bộ thread trong test concurrency để tạo điều kiện tranh chấp có thể lặp lại.

Nên để điểm tiêm lỗi được điều khiển bằng test fixture hoặc business key rõ ràng. Tránh dựa vào `Thread.sleep()` dài hoặc xác suất ngẫu nhiên vì test sẽ chậm và không ổn định.

## 15. Kiểm thử listener và metadata

Listener cũng là một phần của fault tolerance và cần được kiểm tra:

- `SkipListener` chỉ ghi nhận item khi item thực sự bị skip.
- `RetryListener` hoặc cơ chế quan sát retry ghi nhận đúng attempt nếu ứng dụng có dùng.
- `ChunkListener.afterChunk()` chỉ phản ánh chunk commit thành công; `afterChunkError()` phản ánh chunk rollback.
- `StepExecutionListener.afterStep()` ghi nhận trạng thái cuối của Step.
- Các bộ đếm read/write/filter/skip/rollback phản ánh đúng kịch bản.

Nếu listener ghi audit vào database, kiểm tra transaction boundary. Một bản ghi audit trong cùng transaction có thể rollback cùng chunk; một lời gọi HTTP hoặc message broker không tự tham gia transaction database.

Không nên assert nội dung log bằng cách so khớp toàn bộ chuỗi nếu không cần thiết. Ưu tiên kiểm tra callback, metadata và dữ liệu audit đã lưu.

## 16. Kiểm thử song song và race condition

Nếu Step dùng multi-threading, partitioning hoặc split flow, cần kiểm tra:

- Processor, writer, listener và service dùng chung có thread-safe không.
- Các partition có phạm vi dữ liệu không chồng lấn không.
- Writer có ghi trùng khi retry hoặc chạy lại không.
- Skip counters và audit records có bị ghi đè không.
- Connection pool và executor có đủ giới hạn tài nguyên không.
- Khi một worker thất bại, các worker khác và Job có kết thúc ở trạng thái mong đợi không.

Test concurrency nên điều khiển thứ tự bằng latch/barrier thay vì phụ thuộc scheduler. Khi kiểm tra deadlock, database test cần hỗ trợ isolation/locking gần với môi trường thật; H2 không mô phỏng đầy đủ mọi hành vi khóa của PostgreSQL, MySQL, Oracle hoặc SQL Server.

## 17. Kiểm thử hiệu năng và độ ổn định của retry

Fault tolerance có thể làm Job chạy lâu hơn do retry, backoff và skip isolation. Với các Job lớn, nên đo:

- Tổng thời gian Job và thời gian từng Step.
- Số lần retry trên mỗi item/chunk.
- Tổng thời gian chờ backoff.
- Skip rate theo từng giai đoạn.
- Transaction duration, rollback count và lock wait.
- Throughput khi không có lỗi và khi có lỗi.
- Thời gian restart sau khi thất bại.

Test hiệu năng nên dùng dữ liệu đại diện và môi trường có cấu hình gần production. Không dùng unit test để khẳng định throughput thực tế. Có thể tạo workload có tỷ lệ lỗi được kiểm soát để đo ảnh hưởng của retry và skip.

## 18. Những lỗi thường gặp khi kiểm thử fault tolerance

**Chỉ assert JobStatus:** Job có thể `COMPLETED` nhưng đã skip nhiều item. Hãy kiểm tra counters và dữ liệu output.

**Chỉ mock exception mà không chạy Step:** unit test xác nhận logic processor nhưng không kiểm tra được rollback, skip limit, listener hoặc metadata của Spring Batch.

**Dùng mock writer để kết luận transaction rollback:** collection trong bộ nhớ không tự rollback theo database transaction. Dùng database test để xác minh commit/rollback.

**Tạo JobParameters mới khi test restart:** Job có thể trở thành JobInstance mới và không kiểm tra restart của instance cũ.

**Không giữ JobRepository giữa hai lần launch:** metadata và checkpoint không được khôi phục như production.

**Dùng `sleep()` để test retry/backoff:** test dễ chậm và không ổn định. Dùng policy/test double có thể kiểm soát.

**Không test skip limit vượt ngưỡng:** cấu hình skip có thể cho phép lỗi nhiều hơn dự kiến mà không được phát hiện.

**Không kiểm tra writer partial write:** no-rollback hoặc retry sai có thể để lại dữ liệu dở dang.

**Giả định HTTP rollback cùng database:** tác dụng phụ bên ngoài cần idempotency hoặc outbox; database rollback không hoàn tác request đã được hệ thống khác xử lý.

**Chỉ dùng H2 để kết luận về deadlock production:** hành vi khóa và SQLState phụ thuộc database/driver. Cần integration test với database tương ứng khi tính đúng đắn phụ thuộc vào locking.

## Kết luận

Kiểm thử nhiều loại lỗi trong Spring Batch cần bao phủ reader, processor, writer, transaction, service ngoài và restart. Dùng `spring-batch-test` để chạy Job/Step thật, kiểm tra `BatchStatus`, `ExitStatus`, counters, listener và dữ liệu đã commit. Tạo lỗi có chủ đích bằng test doubles, mock service, HTTP stub và database test; kiểm tra riêng retry thành công, retry exhausted, skip trong giới hạn, vượt skip limit, exception không được skip, rollback và no-rollback. Với restart, giữ nguyên JobRepository và identifying JobParameters, xác nhận checkpoint cùng kết quả không trùng hoặc thiếu item. Bộ test tốt chứng minh không chỉ Job phản ứng đúng với lỗi mà cả dữ liệu và trạng thái sau lỗi vẫn đáp ứng yêu cầu nghiệp vụ.

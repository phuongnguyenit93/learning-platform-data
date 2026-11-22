# Kiểm thử skip allowed và skip limit exceeded

Trong Spring Batch, `skip` cho phép một step tiếp tục xử lý khi gặp một số lỗi được xác định là có thể bỏ qua. Ví dụ, một dòng CSV có dữ liệu sai định dạng hoặc một bản ghi vi phạm quy tắc nghiệp vụ có thể được skip nếu nghiệp vụ cho phép tiếp tục với các bản ghi còn lại.

`skipLimit` đặt giới hạn tổng số item được phép skip trong một step execution. Khi số lần skip vượt quá giới hạn, step thất bại với `SkipLimitExceededException`. Vì vậy, hai trường hợp biên cần được kiểm thử rõ ràng:

- **Skip allowed:** số item bị skip không vượt quá giới hạn; step có thể hoàn thành nếu các xử lý còn lại thành công.
- **Skip limit exceeded:** số item cần skip vượt giới hạn; step phải thất bại và không tiếp tục như thể dữ liệu đã được xử lý bình thường.

Với `skipLimit(10)`, tối đa 10 skip được chấp nhận. Skip thứ 11 làm vượt giới hạn. Giới hạn này áp dụng tổng hợp cho skip ở giai đoạn đọc, xử lý và ghi của step, không phải 10 lần cho từng giai đoạn riêng biệt.

Kiểm thử cần xác nhận trạng thái `StepExecution`, các bộ đếm `readSkipCount`, `processSkipCount`, `writeSkipCount`, `skipCount`, số item được ghi và nguyên nhân thất bại. Chỉ assert job hoàn thành hoặc thất bại là chưa đủ để chứng minh skip policy hoạt động đúng.

## Skip và skipLimit trong chunk processing

Trong chunk-oriented step, dữ liệu đi qua ba giai đoạn: reader, processor và writer. Exception có thể phát sinh ở bất kỳ giai đoạn nào.

| Giai đoạn | Ví dụ lỗi có thể skip | Bộ đếm tương ứng |
| --- | --- | --- |
| Read | Dòng file không parse được, bản ghi nguồn bị lỗi định dạng | `readSkipCount` |
| Process | Dữ liệu nghiệp vụ không hợp lệ, không thể chuyển đổi một item | `processSkipCount` |
| Write | Một item vi phạm constraint hoặc lỗi ghi được phân loại cho phép skip | `writeSkipCount` |

Spring Batch theo dõi các loại skip này trong `StepExecution`. `skipCount` là tổng số skip ở các giai đoạn. `skipLimit` áp dụng cho tổng này trong step, không phải một quota riêng cho từng loại exception hoặc từng chunk.

Ví dụ, nếu step có `skipLimit(5)` và đã có 2 read skip cùng 2 process skip, thì chỉ còn một skip được phép. Một write skip tiếp theo sẽ làm tổng vượt giới hạn và step thất bại.

### Cấu hình skip policy

Với Spring Batch 5, có thể cấu hình skip trực tiếp trên step builder:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(10)
            .build();
}
```

Trong ví dụ, step cho phép skip tối đa 10 exception thuộc loại `InvalidOrderException` theo quy tắc skip của Spring Batch. Nếu skip thứ 11 xảy ra, step thất bại do vượt giới hạn.

`faultTolerant()` bật cấu hình fault-tolerant cho chunk step, cho phép khai báo skip/retry. Chỉ khai báo các loại exception thực sự có thể bỏ qua. Không nên dùng `.skip(Exception.class)` một cách rộng rãi nếu lỗi hạ tầng như mất kết nối database hoặc lỗi cấu hình không được phép bỏ qua.

### SkipLimit bằng 0

Nếu không cấu hình `skipLimit`, giá trị mặc định thường là 0. Khi đó, exception được khai báo skip vẫn không có lần skip nào được chấp nhận; lần đầu tiên sẽ vượt giới hạn và làm step thất bại.

```java
.faultTolerant()
.skip(InvalidOrderException.class)
// Không đặt skipLimit: mặc định là 0
```

Khai báo `.skip(...)` xác định loại lỗi có thể được phân loại là skip, còn `skipLimit` xác định số lượng tối đa được phép. Cả hai điều kiện đều cần được thỏa mãn.

## Ngưỡng được tính như thế nào?

Giả sử `skipLimit` là 3:

| Số skip tích lũy | Kết quả |
| ---: | --- |
| 0 | Step tiếp tục bình thường |
| 1 | Được phép |
| 2 | Được phép |
| 3 | Được phép; đã chạm giới hạn nhưng chưa vượt |
| 4 | Vượt giới hạn; step thất bại |

Điểm cần nhớ là **bằng giới hạn vẫn được phép**. Step chỉ thất bại khi số skip vượt quá giới hạn. Với giới hạn bằng 0, skip đầu tiên đã là vượt giới hạn.

Giới hạn được tích lũy trong phạm vi step execution, qua các chunk của step. Một chunk mới không làm bộ đếm skip trở về 0. Nếu step bị restart, execution mới có metadata và bộ đếm theo lifecycle restart của Spring Batch; không nên giả định một lần restart là phần tiếp nối số học đơn giản của bộ đếm cũ. Hãy kiểm tra từng `StepExecution` và lịch sử execution khi phân tích restart.

## Kiểm thử hai trường hợp biên

Một test hữu ích cần chạy cùng cấu hình step với hai bộ dữ liệu khác nhau:

1. Bộ dữ liệu có đúng số item lỗi bằng `skipLimit`: step phải được phép hoàn tất.
2. Bộ dữ liệu có số item lỗi lớn hơn `skipLimit` một đơn vị: step phải thất bại.

Ví dụ đặt `skipLimit(2)`:

```text
Case A: đúng giới hạn
Input:  valid-1, invalid-1, valid-2, invalid-2, valid-3
Skip:   2
Output: valid-1, valid-2, valid-3
Result: COMPLETED

Case B: vượt giới hạn
Input:  valid-1, invalid-1, invalid-2, invalid-3, valid-2
Skip:   cần 3
Limit:  2
Result: FAILED khi phát sinh skip thứ 3
```

Đặt chunk size đủ lớn trong ví dụ test để các item cùng nằm trong một chunk giúp tập trung vào ranh giới skip. Với test production-like, nên kiểm tra thêm trường hợp lỗi xuất hiện ở nhiều chunk để xác nhận bộ đếm được tích lũy xuyên suốt step.

## Thiết kế fixture cho test

Để test có thể tái lập, dữ liệu đầu vào nên thể hiện rõ item hợp lệ và item gây exception. Không nên dựa vào file hoặc database dùng chung mà không kiểm soát trạng thái.

Ví dụ mô hình input và output:

```java
public record OrderInput(String orderId, boolean invalid) {
}

public record Order(String orderId) {
}

public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Processor ném exception cho item không hợp lệ:

```java
public class OrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.invalid()) {
            throw new InvalidOrderException(
                    "Invalid order: " + input.orderId());
        }
        return new Order(input.orderId());
    }
}
```

Trong test, có thể dùng `ListItemReader` để cung cấp dữ liệu xác định. Writer test có thể là writer đơn giản hoặc writer ghi vào database test. Với integration test, cần dùng `JobRepository` thật của context test để các bộ đếm và trạng thái được lưu như khi chạy ứng dụng.

## Cấu hình step dùng trong integration test

Ví dụ dưới đây chọn bộ dữ liệu dựa trên job parameter `scenario`. Reader được khai báo `@StepScope` để nhận parameter của lần chạy.

```java
@Bean
@StepScope
ItemReader<OrderInput> orderTestReader(
        @Value("#{jobParameters['scenario']}") String scenario) {

    List<OrderInput> items = switch (scenario) {
        case "at-limit" -> List.of(
                new OrderInput("O-1", false),
                new OrderInput("O-2", true),
                new OrderInput("O-3", false),
                new OrderInput("O-4", true),
                new OrderInput("O-5", false));
        case "over-limit" -> List.of(
                new OrderInput("O-1", false),
                new OrderInput("O-2", true),
                new OrderInput("O-3", true),
                new OrderInput("O-4", true),
                new OrderInput("O-5", false));
        default -> throw new IllegalArgumentException(
                "Unknown scenario: " + scenario);
    };

    return new ListItemReader<>(items);
}
```

Khai báo processor, writer và step:

```java
@Bean
ItemProcessor<OrderInput, Order> orderTestProcessor() {
    return new OrderProcessor();
}

@Bean
ItemWriter<Order> orderTestWriter() {
    return chunk -> {
        // Writer test: việc ghi được xác nhận qua writeCount.
    };
}

@Bean
Step skipLimitTestStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderTestReader,
        ItemProcessor<OrderInput, Order> orderTestProcessor,
        ItemWriter<Order> orderTestWriter) {

    return new StepBuilder("skipLimitTestStep", jobRepository)
            .<OrderInput, Order>chunk(10, transactionManager)
            .reader(orderTestReader)
            .processor(orderTestProcessor)
            .writer(orderTestWriter)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(2)
            .build();
}
```

Chunk size là 10 để toàn bộ fixture năm item được xử lý trong cùng một chunk. Writer không cần ghi dữ liệu nghiệp vụ thật trong ví dụ; `StepExecution.writeCount` giúp xác nhận số output được chuyển tới writer. Trong dự án thực tế, có thể thay writer bằng writer test ghi vào bảng tạm để assert nội dung cụ thể.

Đưa step vào một job test:

```java
@Bean
Job skipLimitTestJob(
        JobRepository jobRepository,
        Step skipLimitTestStep) {

    return new JobBuilder("skipLimitTestJob", jobRepository)
            .start(skipLimitTestStep)
            .build();
}
```

## Kiểm thử skip đúng bằng giới hạn

Với `skipLimit(2)`, fixture `at-limit` có hai item gây `InvalidOrderException` và ba item hợp lệ. Step phải hoàn tất vì tổng số skip bằng giới hạn, không vượt quá nó.

Ví dụ dùng `@SpringBatchTest` và `JobLauncherTestUtils`:

```java
@SpringBootTest
@SpringBatchTest
class SkipLimitIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("skipLimitTestJob")
    private Job skipLimitTestJob;

    @BeforeEach
    void configureJob() {
        jobLauncherTestUtils.setJob(skipLimitTestJob);
    }

    @Test
    void completesWhenSkipCountEqualsLimit() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("scenario", "at-limit", true)
                .addString("testRunId", UUID.randomUUID().toString(), true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchStep(
                "skipLimitTestStep", parameters);

        StepExecution stepExecution = execution.getStepExecutions()
                .stream()
                .filter(step -> step.getStepName()
                        .equals("skipLimitTestStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(BatchStatus.COMPLETED, stepExecution.getStatus());
        assertEquals(2, stepExecution.getProcessSkipCount());
        assertEquals(2, stepExecution.getSkipCount());
        assertEquals(3, stepExecution.getWriteCount());
        assertEquals(5, stepExecution.getReadCount());
    }
}
```

Các assertion xác nhận:

- Step hoàn thành thành công.
- Hai lỗi processor được skip.
- Tổng skip bằng 2, đúng bằng `skipLimit`.
- Ba output hợp lệ được chuyển tới writer.
- Reader đã đọc đủ năm item.

Nếu ứng dụng có skip ở nhiều giai đoạn, không nên chỉ assert `processSkipCount`; cần kiểm tra cả `skipCount` và các bộ đếm theo giai đoạn.

## Kiểm thử vượt giới hạn

Fixture `over-limit` có ba item lỗi trong khi step chỉ cho phép hai skip. Khi lỗi thứ ba được phân loại là skip, tổng skip vượt giới hạn và Spring Batch ném `SkipLimitExceededException`; step phải kết thúc ở trạng thái `FAILED`.

```java
@Test
void failsWhenSkipCountExceedsLimit() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
            .addString("scenario", "over-limit", true)
            .addString("testRunId", UUID.randomUUID().toString(), true)
            .toJobParameters();

    JobExecution execution = jobLauncherTestUtils.launchStep(
            "skipLimitTestStep", parameters);

    StepExecution stepExecution = execution.getStepExecutions()
            .stream()
            .filter(step -> step.getStepName()
                    .equals("skipLimitTestStep"))
            .findFirst()
            .orElseThrow();

    assertEquals(BatchStatus.FAILED, stepExecution.getStatus());
    assertTrue(stepExecution.getFailureExceptions().stream()
            .anyMatch(SkipLimitExceededException.class::isInstance));
}
```

Không nên phụ thuộc vào một giá trị `writeCount` cố định trong test vượt giới hạn nếu thay đổi chunk size hoặc thứ tự item. Khi vượt giới hạn trong lúc xử lý chunk hiện tại, chunk đó có thể rollback và writer chưa được gọi; các chunk trước đó đã commit vẫn có thể giữ kết quả. Điều quan trọng là xác nhận step thất bại vì `SkipLimitExceededException` và đối chiếu các bộ đếm thực tế.

Nếu exception được bọc bởi một exception khác trong phiên bản hoặc lớp tích hợp của ứng dụng, test có thể duyệt chuỗi cause để tìm `SkipLimitExceededException`. Nên kiểm tra `failureExceptions` và log của step thay vì chỉ so khớp chuỗi thông điệp.

## Kiểm thử bằng JobExplorer

`JobLauncherTestUtils` trả về `JobExecution` của lần chạy test. Có thể đọc `StepExecution` trực tiếp từ đối tượng đó. Nếu cần truy vấn lại metadata đã lưu, dùng `JobExplorer`.

```java
@Autowired
private JobExplorer jobExplorer;

void assertExecutionWasPersisted(JobExecution launchedExecution) {
    JobExecution persisted = jobExplorer.getJobExecution(
            launchedExecution.getId());

    assertNotNull(persisted);
    assertEquals(
            launchedExecution.getStatus(),
            persisted.getStatus());
}
```

`JobExplorer` hữu ích khi test cần xác nhận metadata tồn tại trong repository, hoặc khi phân tích một execution sau khi launcher đã trả về. Nó cũng giúp lấy các `StepExecution` và kiểm tra bộ đếm sau khi step kết thúc.

Không nên truy vấn trực tiếp bảng `BATCH_STEP_EXECUTION` trong test thông thường nếu API metadata đã đáp ứng yêu cầu. Dùng API repository giúp test ít phụ thuộc vào schema nội bộ hơn.

## Kiểm thử skip ở cả read, process và write

Giới hạn skip được áp dụng cho tổng skip của step. Cần có test chứng minh các giai đoạn dùng chung một quota.

Ví dụ với `skipLimit(2)`:

| Giai đoạn | Số skip | Tổng tích lũy | Kết quả |
| --- | ---: | ---: | --- |
| Read | 1 | 1 | Được phép |
| Process | 1 | 2 | Được phép, bằng giới hạn |
| Write | 1 | 3 | Vượt giới hạn; step thất bại |

Một test tích hợp có thể cấu hình reader, processor và writer để lần lượt ném các exception thuộc loại skip. Khi write skip thứ ba xuất hiện, step phải vượt giới hạn dù từng giai đoạn riêng lẻ chưa đạt hai skip.

Khi viết test writer skip, cần hiểu cơ chế writer xử lý chunk. Writer nhận một nhóm item; nếu writer ném exception, Spring Batch có thể phải xác định item gây lỗi theo cơ chế fault-tolerant và có thể gọi lại writer trong quá trình scan/rollback. Vì vậy, fixture writer cần có hành vi xác định và không tạo side effect ngoài transaction trong mỗi lần gọi thử.

## Kiểm thử exception được phép skip và không được phép skip

Skip limit chỉ được áp dụng sau khi exception được phân loại là có thể skip. Một exception không nằm trong skip policy có thể làm step thất bại ngay cả khi skip count vẫn thấp hơn giới hạn.

Ví dụ cấu hình:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.noSkip(NonRecoverableOrderException.class)
.skipLimit(10)
```

Trong đó:

- `InvalidOrderException` được phép skip nếu chưa vượt giới hạn.
- `NonRecoverableOrderException` không được skip và làm step thất bại.
- Một exception không được khai báo trong policy cũng không tự động trở thành skip.

Nên có test riêng cho exception không được phép skip:

```java
@Test
void failsImmediatelyForNonSkippableException() {
    // Chuẩn bị input khiến processor ném NonRecoverableOrderException.
    // Khởi chạy step và xác nhận FAILED dù skipCount còn dưới limit.
}
```

Test này phân biệt lỗi do vượt giới hạn với lỗi do loại exception không được phép bỏ qua. Hai trường hợp đều có thể làm step `FAILED`, nhưng nguyên nhân và cách khắc phục khác nhau.

## Retry và skip limit

Retry và skip giải quyết hai vấn đề khác nhau:

- Retry thử lại một thao tác có thể thất bại tạm thời, ví dụ deadlock hoặc timeout.
- Skip cho phép bỏ qua một item sau khi exception được phân loại là có thể bỏ qua và các lần retry (nếu có) không giải quyết được lỗi.

Ví dụ:

```java
.faultTolerant()
.retry(DeadlockLoserDataAccessException.class)
.retryLimit(3)
.skip(InvalidOrderException.class)
.skipLimit(10)
```

Ở đây, lỗi deadlock được retry theo cấu hình; lỗi dữ liệu `InvalidOrderException` được phép skip. Nếu ứng dụng cấu hình cùng một exception type cho cả retry và skip, cần hiểu thứ tự và chính sách phân loại của phiên bản Spring Batch đang dùng, đồng thời kiểm thử rõ số attempt và thời điểm item được skip.

Không cộng `retryCount` vào `skipCount`. Một item có thể có nhiều lần retry nhưng cuối cùng được xử lý thành công, nên không tiêu thụ skip limit. Ngược lại, một item bị skip sau lỗi có thể tiêu thụ một skip theo giai đoạn phát sinh lỗi.

Listener cũng có thể được gọi nhiều lần trong quá trình retry. Nếu cần ghi nhận item bị bỏ qua cuối cùng, `SkipListener` phù hợp hơn việc tạo một reject record cuối cùng trong mọi callback error.

## Kiểm tra SkipListener khi skip được chấp nhận

Nếu ứng dụng cần lưu bản ghi bị skip vào bảng reject, có thể dùng `SkipListener`. Test cần xác nhận listener được gọi cho item thực sự bị skip và không bị gọi như một quyết định skip cuối cùng khi item chỉ gặp lỗi tạm thời rồi retry thành công.

Ví dụ listener:

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    private final RejectedOrderRepository rejectedOrderRepository;

    public OrderSkipListener(
            RejectedOrderRepository rejectedOrderRepository) {
        this.rejectedOrderRepository = rejectedOrderRepository;
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable cause) {
        rejectedOrderRepository.save(
                new RejectedOrder(item.orderId(), cause.getMessage()));
    }
}
```

Trong step:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(2)
.listener(orderSkipListener)
```

Test ở ngưỡng cho phép có thể xác nhận số reject record bằng số item thực sự bị skip. Test vượt ngưỡng cần kiểm tra listener và reject records theo transaction boundary thực tế của step. Không nên giả định mọi callback hoặc side effect ngoài transaction sẽ rollback cùng chunk.

Nếu reject repository dùng cùng transaction resource với step, record có thể tham gia transaction chunk theo cấu hình. Nếu ghi sang hệ thống ngoài, cần idempotency để xử lý việc callback hoặc chunk được thực hiện lại.

## Kiểm tra StepExecution counters

`StepExecution` cung cấp các bộ đếm quan trọng:

| Getter | Ý nghĩa |
| --- | --- |
| `getReadCount()` | Số item reader đã đọc |
| `getWriteCount()` | Số item được ghi thành công theo metadata step |
| `getReadSkipCount()` | Số skip ở reader |
| `getProcessSkipCount()` | Số skip ở processor |
| `getWriteSkipCount()` | Số skip ở writer |
| `getSkipCount()` | Tổng skip của step |
| `getFilterCount()` | Số item processor filter bằng cách trả `null` |
| `getCommitCount()` | Số transaction commit được ghi nhận cho step |
| `getRollbackCount()` | Số rollback được ghi nhận cho step |

Trong test ở ngưỡng cho phép, có thể assert:

```java
assertEquals(2, stepExecution.getSkipCount());
assertEquals(2, stepExecution.getProcessSkipCount());
assertEquals(0, stepExecution.getReadSkipCount());
assertEquals(0, stepExecution.getWriteSkipCount());
```

Việc kiểm tra từng counter giúp phát hiện exception bị phân loại nhầm tầng. Ví dụ, nếu test mong đợi process skip nhưng `readSkipCount` tăng, có thể reader đã ném exception trước khi item được chuyển tới processor.

Không nên suy ra số item bị filter từ skip count. Processor trả `null` là filtering và tăng `filterCount`, không phải skip. Tương tự, retry count không phải một loại skip counter.

## Kiểm thử nhiều chunk để xác nhận bộ đếm tích lũy

Một lỗi thường gặp trong test là đặt tất cả item vào một chunk, sau đó vô tình chỉ kiểm tra một tình huống. Để chứng minh skip limit được tích lũy xuyên suốt step, hãy dùng chunk size nhỏ hơn số item và phân bố lỗi qua nhiều chunk.

Ví dụ `skipLimit(3)`, chunk size 2:

```text
Chunk 1: valid, invalid  -> processSkipCount = 1
Chunk 2: valid, invalid  -> processSkipCount = 2
Chunk 3: invalid, valid  -> processSkipCount = 3 (được phép)
Chunk 4: invalid, valid  -> skip thứ 4, step FAILED
```

Test này xác nhận giới hạn không được reset khi chunk commit. Nếu chunk đầu và chunk thứ hai đã commit, business data của chúng vẫn tồn tại khi chunk sau vượt giới hạn. Điều này cũng giúp kiểm thử writer có idempotent và restart behavior.

## Kiểm thử restart sau skip limit exceeded

Khi step vượt skip limit, step thất bại. Việc restart phụ thuộc cấu hình restartable của job, identifying parameters, reader state và dữ liệu nguồn.

Test restart nên trả lời:

- Job có được phép restart không?
- Reader có thể tiếp tục từ checkpoint đã commit không?
- Bộ dữ liệu gây lỗi có thay đổi sau khi xử lý nguyên nhân không?
- Skip limit áp dụng cho step execution mới theo metadata restart ra sao?
- Các chunk đã commit trước lỗi có bị ghi lại không?
- Writer có xử lý an toàn khi item được đọc lại không?

Không nên tự động tăng `skipLimit` trong lần restart chỉ để job vượt qua lỗi nếu không có quyết định nghiệp vụ. Nếu một dữ liệu lỗi cần được sửa, hãy sửa nguồn hoặc xử lý theo quy trình reject/replay có kiểm soát. Nếu policy thay đổi, ghi nhận rõ cấu hình và phiên bản ứng dụng đã dùng cho execution.

Trong test restart, giữ nguyên identifying parameters để tiếp tục cùng `JobInstance`. Không sinh `runId` identifying mới ở lần restart; làm như vậy sẽ tạo một instance khác và không kiểm tra được restart thực sự.

## Test isolation và JobParameters

Spring Batch lưu metadata trong `JobRepository`. Nếu hai test dùng cùng job name và identifying parameters, test sau có thể gặp `JobInstanceAlreadyCompleteException` hoặc trạng thái execution còn tồn tại từ test trước.

Với test độc lập, tạo identifying parameter riêng cho mỗi lần chạy:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("scenario", "at-limit", true)
        .addString("testRunId", UUID.randomUUID().toString(), true)
        .toJobParameters();
```

Với test restart, tạo parameter một lần rồi tái sử dụng cùng bộ parameter ở lần chạy sau. Không tạo UUID mới giữa lần chạy đầu và restart.

Nếu dùng `JobRepositoryTestUtils`, có thể dọn metadata do test tạo ra:

```java
@Autowired
private JobRepositoryTestUtils jobRepositoryTestUtils;

@AfterEach
void cleanBatchMetadata() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

Cleanup metadata không tự xóa business data, file hoặc reject records. Hãy cleanup các dữ liệu đó theo test ID riêng. Nếu test chạy song song trên cùng repository, không dùng cleanup toàn cục có thể xóa execution của test khác; ưu tiên database/schema riêng hoặc cleanup theo phạm vi được kiểm soát.

## Lỗi thường gặp trong test skip limit

### Nghĩ rằng bằng skipLimit là thất bại

Skip thứ `N` vẫn được phép khi `skipLimit(N)`. Chỉ skip thứ `N+1` mới vượt giới hạn. Test cần có cả trường hợp bằng giới hạn và vượt một đơn vị.

### Nghĩ skipLimit áp dụng riêng cho read, process và write

Các bộ đếm được cộng lại thành tổng skip của step. Một read skip và một process skip đều tiêu thụ cùng quota.

### Dùng exception không nằm trong skip policy

Step có thể thất bại ngay cả khi skip count còn thấp hơn limit. Kiểm tra loại exception và cấu hình `.skip(...)`/`.noSkip(...)`.

### Assert chỉ BatchStatus

`FAILED` có thể do lỗi không được phép skip, lỗi writer, lỗi transaction hoặc vượt limit. Kiểm tra `failureExceptions`, counters và log để xác nhận nguyên nhân.

### Không tạo identifying parameters riêng cho từng test

Metadata cũ có thể làm test bị ảnh hưởng bởi lần chạy trước. Dùng `testRunId` riêng cho test độc lập và giữ nguyên parameters cho test restart.

### Bỏ qua transaction và chunk commit

Khi vượt limit ở chunk hiện tại, chunk đó có thể rollback, nhưng các chunk trước đã commit vẫn còn. Test phải kiểm tra dữ liệu theo từng transaction boundary.

### Dùng retry count như skip count

Retry là lần thử lại; skip là quyết định bỏ item. Kiểm tra đúng counter và callback theo mục tiêu test.

### Chỉ test processor skip mà không test reader/writer

Nếu ứng dụng cho phép skip ở nhiều giai đoạn, cần kiểm thử tổng skip được tích lũy qua các giai đoạn. Với writer skip, chú ý writer có thể được gọi lại trong quá trình xác định item lỗi.

## Ma trận kiểm thử đề xuất

Một bộ test tối thiểu cho step có `skipLimit(2)` có thể gồm:

| Trường hợp | Input/lỗi | Kết quả mong đợi |
| --- | --- | --- |
| Không có lỗi | 0 skip | `COMPLETED`, skip count 0 |
| Dưới giới hạn | 1 skip | `COMPLETED`, skip count 1 |
| Đúng giới hạn | 2 skip | `COMPLETED`, skip count 2 |
| Vượt giới hạn | 3 skip | `FAILED`, có `SkipLimitExceededException` |
| Exception không được skip | 1 lỗi không nằm trong policy | `FAILED` dù skip count chưa đạt limit |
| Skip ở nhiều giai đoạn | Read 1 + process 1 + write 1 | Vượt tổng giới hạn 2 |
| Retry rồi thành công | Lỗi tạm thời, sau đó thành công | `COMPLETED`, không tăng skip cho item đó |
| Nhiều chunk | Skip phân bố qua nhiều chunk | Tổng skip được tích lũy trong step |
| Restart | Step thất bại rồi chạy lại cùng instance | Checkpoint và business output đúng, không duplicate |

Không phải mọi ứng dụng đều cần toàn bộ ma trận ngay từ đầu. Các trường hợp đúng giới hạn, vượt giới hạn, exception không được skip và test isolation là nền tảng quan trọng nhất.

## Nguyên tắc triển khai

Khi viết test cho skip policy, hãy thống nhất các điểm sau:

1. Xác định chính xác exception nào được phép skip.
2. Đặt `skipLimit` theo quy tắc nghiệp vụ và hiểu rằng giới hạn áp dụng tổng cho read/process/write.
3. Kiểm thử số skip bằng giới hạn và lớn hơn giới hạn một đơn vị.
4. Kiểm tra `BatchStatus`, `ExitStatus` và `failureExceptions`.
5. Assert các counter theo giai đoạn cùng `skipCount` tổng.
6. Phân biệt filtering, retry và skip.
7. Kiểm thử exception không được phép skip.
8. Phân bố lỗi qua nhiều chunk nếu cần xác nhận counter tích lũy.
9. Kiểm tra transaction rollback của chunk vượt giới hạn và dữ liệu từ chunk trước đã commit.
10. Dùng identifying parameters riêng cho test độc lập và giữ nguyên parameters khi restart.
11. Kiểm tra `SkipListener` và reject output nếu ứng dụng lưu dữ liệu bị bỏ qua.

`JobLauncherTestUtils` phù hợp để chạy step/job trong integration test; `JobExplorer` giúp đọc metadata đã lưu; `JobRepositoryTestUtils` hỗ trợ cleanup có kiểm soát. Dùng database test phù hợp và xác nhận cả trạng thái batch lẫn kết quả business data.

## Ghi nhớ

`skip` xác định loại exception có thể bỏ qua; `skipLimit` xác định tổng số skip tối đa của một step. Với `skipLimit(N)`, đúng N skip vẫn được chấp nhận, còn skip thứ N+1 làm step thất bại với `SkipLimitExceededException`. Tổng này bao gồm read, process và write skip, không phải quota riêng cho từng giai đoạn hay từng chunk. Hãy kiểm thử hai trường hợp biên bằng dữ liệu xác định, kiểm tra `BatchStatus`, failure exception và các skip counters, đồng thời phân biệt skip với retry và filtering. Khi vượt giới hạn, chunk hiện tại có thể rollback trong khi các chunk trước đã commit vẫn tồn tại; test restart phải giữ nguyên identifying parameters và xác nhận writer không tạo dữ liệu trùng.

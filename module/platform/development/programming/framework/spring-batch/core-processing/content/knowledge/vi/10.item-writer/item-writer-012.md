# Kiểm thử writer với chunk rỗng và nhiều item trong Spring Batch

Trong chunk-oriented processing, `ItemWriter` nhận một nhóm item đầu ra và ghi chúng vào hệ thống đích. Kích thước chunk có thể thay đổi: chunk cuối thường nhỏ hơn commit interval, processor có thể lọc một số item, và nguồn dữ liệu có thể rỗng ngay từ đầu. Vì vậy, khi kiểm thử writer, cần xác nhận cả nội dung được ghi lẫn số lần writer được gọi trong từng tình huống.

Một điểm quan trọng là phân biệt **writer nhận một chunk rỗng khi được gọi trực tiếp** với **Spring Batch không gọi writer vì output chunk rỗng**. Trong chunk processing mặc định, nếu không có output item sau bước đọc và xử lý, framework bỏ qua lời gọi writer. Kiểm thử hai trường hợp này ở đúng tầng giúp tránh nhầm lẫn giữa trách nhiệm của writer và hành vi điều phối của framework.

## 1. Vai trò của ItemWriter trong chunk processing

Luồng xử lý cơ bản:

```text
ItemReader
    |
    v
Đọc tối đa commit interval item
    |
    v
ItemProcessor (nếu có)
    |
    +---- output object -> giữ lại trong output chunk
    |
    +---- null          -> filter item khỏi output
    |
    v
ItemWriter nhận output chunk
    |
    v
Commit transaction
```

Trong Spring Batch 5, `ItemWriter` nhận một `Chunk`:

```java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

Writer thường duyệt `chunk.getItems()` để ghi dữ liệu. Mỗi lần được framework gọi, chunk chứa các output item của một lần xử lý chunk. Nếu reader không có item hoặc processor lọc hết item, output chunk rỗng và writer không được gọi trong đường xử lý mặc định.

Với Spring Batch phiên bản cũ, chữ ký writer có thể dùng `List<? extends T>` thay vì `Chunk`. Khi viết test, cần dùng API tương ứng với phiên bản thư viện mà dự án đang sử dụng.

## 2. Phân biệt ba trường hợp cần kiểm thử

| Tình huống | Input reader | Output processor | Hành vi writer theo chunk processing mặc định |
| --- | --- | --- | --- |
| Nguồn rỗng | Không có item; lần đọc đầu trả về `null`. | Không có item để xử lý. | Không được gọi. |
| Processor lọc hết | Reader đọc được item. | Tất cả lần `process()` trả về `null`. | Không được gọi vì output chunk rỗng. |
| Có nhiều item | Reader cung cấp nhiều item. | Có output item. | Được gọi theo từng chunk có output; chunk cuối có thể nhỏ hơn commit interval. |

Ví dụ commit interval bằng 3:

```text
Input có 5 item, processor giữ tất cả:
  Chunk 1: [A, B, C] -> writer gọi với 3 item
  Chunk 2: [D, E]    -> writer gọi với 2 item

Input rỗng:
  Không có output chunk -> writer không được gọi

Input có 4 item, processor lọc cả 4:
  readCount = 4, filterCount = 4
  Không có output chunk -> writer không được gọi
```

Kết quả này cho thấy số lần gọi writer phụ thuộc vào output sau processor, không chỉ phụ thuộc số item reader đã đọc.

## 3. Kiểm thử writer độc lập với một chunk nhiều item

Unit test writer trực tiếp giúp xác nhận cách writer chuyển đổi và ghi một nhóm item. Không cần khởi chạy job nếu mục tiêu chỉ là kiểm tra logic ghi.

Ví dụ writer chuyển các `Order` thành bản ghi lưu trữ:

```java
public class OrderItemWriter implements ItemWriter<Order> {

    private final OrderRepository repository;

    public OrderItemWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        List<OrderEntity> entities = chunk.getItems().stream()
            .map(order -> new OrderEntity(order.getId(), order.getTotal()))
            .toList();

        repository.saveAll(entities);
    }
}
```

Test có thể truyền nhiều item và xác nhận repository nhận đúng dữ liệu:

```java
@ExtendWith(MockitoExtension.class)
class OrderItemWriterTest {

    @Mock
    OrderRepository repository;

    @Test
    void writesEveryItemInChunk() throws Exception {
        OrderItemWriter writer = new OrderItemWriter(repository);
        Chunk<Order> chunk = new Chunk<>();
        chunk.add(new Order("A-1", new BigDecimal("10.00")));
        chunk.add(new Order("A-2", new BigDecimal("20.00")));
        chunk.add(new Order("A-3", new BigDecimal("30.00")));

        writer.write(chunk);

        ArgumentCaptor<Iterable<OrderEntity>> captor =
            ArgumentCaptor.forClass(Iterable.class);
        verify(repository).saveAll(captor.capture());

        assertThat(StreamSupport.stream(captor.getValue().spliterator(), false))
            .extracting(OrderEntity::getOrderId)
            .containsExactly("A-1", "A-2", "A-3");
    }
}
```

Đây là unit test cho logic writer. Trong code thực tế, có thể dùng assertion phù hợp với kiểu tham số của repository và tránh raw type của captor bằng cách capture một `List` hoặc dùng `ArgumentCaptor` theo API Mockito của dự án. Mục tiêu là xác nhận đủ item, đúng thứ tự nếu thứ tự có ý nghĩa, và đúng dữ liệu được chuyển đổi.

Unit test không xác nhận transaction của chunk, số lần framework gọi writer hoặc hành vi khi processor filter. Những điều đó cần kiểm thử tích hợp với step/job.

## 4. Kiểm thử writer khi được truyền chunk rỗng trực tiếp

Một writer có thể được gọi trực tiếp trong unit test với `Chunk` rỗng để xác nhận implementation không lỗi khi không có item, nếu ứng dụng muốn writer có hành vi no-op trong trường hợp đó:

```java
@Test
void handlesEmptyChunkAsNoOp() throws Exception {
    OrderItemWriter writer = new OrderItemWriter(repository);
    Chunk<Order> emptyChunk = new Chunk<>();

    writer.write(emptyChunk);

    verify(repository).saveAll(List.of());
}
```

Assertion cụ thể phụ thuộc cách writer được viết. Nếu writer chủ động trả về sớm khi `chunk.isEmpty()`, test nên xác nhận repository không bị gọi:

```java
@Override
public void write(Chunk<? extends Order> chunk) {
    if (chunk.isEmpty()) {
        return;
    }
    repository.saveAll(mapOrders(chunk.getItems()));
}
```

Khi đó test tương ứng:

```java
writer.write(new Chunk<>());
verifyNoInteractions(repository);
```

Hai cách trên thể hiện hai hợp đồng writer khác nhau. Nếu writer luôn gọi `saveAll` với collection rỗng, hãy kiểm tra repository thực sự chấp nhận điều đó. Nếu muốn rỗng là no-op, kiểm tra rằng không có thao tác ghi nào được phát sinh.

Tuy nhiên, kiểm thử gọi trực tiếp `write(emptyChunk)` không chứng minh rằng Spring Batch sẽ gọi writer với chunk rỗng. Trong chunk-oriented processing tiêu chuẩn, framework bỏ qua `ItemWriter.write()` khi output chunk rỗng. Hành vi tích hợp đó cần một test riêng.

## 5. Dùng writer ghi nhận để kiểm tra số lần gọi

Trong test tích hợp, một recording writer giúp quan sát số lần writer được gọi và nội dung từng chunk. Ví dụ:

```java
public class RecordingItemWriter<T> implements ItemWriter<T> {

    private final List<List<T>> writtenChunks = new ArrayList<>();

    @Override
    public void write(Chunk<? extends T> chunk) {
        writtenChunks.add(new ArrayList<>(chunk.getItems()));
    }

    public List<List<T>> getWrittenChunks() {
        return List.copyOf(writtenChunks);
    }

    public void clear() {
        writtenChunks.clear();
    }
}
```

Writer lưu bản sao của item list ở mỗi lần gọi. Việc sao chép quan trọng vì chunk là đối tượng được framework quản lý; test không nên giữ một tham chiếu mutable rồi giả định nội dung của nó không bao giờ thay đổi.

Nếu step chạy bất đồng bộ hoặc test chạy song song, recording writer cần đồng bộ phù hợp hoặc mỗi test phải dùng một instance riêng. Ví dụ trên đơn giản hóa cho test chạy tuần tự trong một application context.

## 6. Kiểm thử tích hợp với nguồn rỗng và nhiều item

Một job test có thể dùng `ListItemReader`, processor tùy chọn và recording writer. Dùng `@StepScope` để tạo reader mới cho mỗi execution dựa trên job parameter, tránh chia sẻ iterator đã cạn giữa các lần chạy.

Ví dụ cấu hình theo Spring Batch 5:

```java
@TestConfiguration
class WriterChunkTestConfiguration {

    @Bean
    @StepScope
    ItemReader<Integer> writerTestReader(
            @Value("#{jobParameters['scenario']}") String scenario) {
        List<Integer> items = switch (scenario) {
            case "EMPTY" -> List.of();
            case "MANY" -> List.of(1, 2, 3, 4, 5);
            case "FILTER_ALL" -> List.of(1, 2, 3, 4);
            default -> throw new IllegalArgumentException("Unknown scenario: " + scenario);
        };
        return new ListItemReader<>(items);
    }

    @Bean
    @StepScope
    ItemProcessor<Integer, Integer> writerTestProcessor(
            @Value("#{jobParameters['scenario']}") String scenario) {
        return item -> "FILTER_ALL".equals(scenario) ? null : item;
    }

    @Bean
    RecordingItemWriter<Integer> recordingItemWriter() {
        return new RecordingItemWriter<>();
    }

    @Bean
    Step writerTestStep(JobRepository jobRepository,
                        PlatformTransactionManager transactionManager,
                        ItemReader<Integer> writerTestReader,
                        ItemProcessor<Integer, Integer> writerTestProcessor,
                        RecordingItemWriter<Integer> recordingItemWriter) {
        return new StepBuilder("writerTestStep", jobRepository)
            .<Integer, Integer>chunk(3, transactionManager)
            .reader(writerTestReader)
            .processor(writerTestProcessor)
            .writer(recordingItemWriter)
            .build();
    }

    @Bean
    Job writerTestJob(JobRepository jobRepository, Step writerTestStep) {
        return new JobBuilder("writerTestJob", jobRepository)
            .start(writerTestStep)
            .build();
    }
}
```

Với commit interval bằng 3:

- `EMPTY` tạo reader không có item.
- `FILTER_ALL` đọc bốn item nhưng processor trả về `null` cho tất cả.
- `MANY` đọc năm item và giữ lại toàn bộ, tạo hai lần ghi với kích thước lần lượt là 3 và 2.

Test tích hợp có thể dùng `@SpringBootTest`, `@SpringBatchTest` và import cấu hình trên. Tắt auto-launch của Spring Boot để job chỉ chạy khi test yêu cầu:

```java
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@SpringBatchTest
@Import(WriterChunkTestConfiguration.class)
class WriterChunkIntegrationTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("writerTestJob")
    Job writerTestJob;

    @Autowired
    RecordingItemWriter<Integer> writer;

    @BeforeEach
    void prepare() {
        writer.clear();
        jobLauncherTestUtils.setJob(writerTestJob);
    }

    private JobExecution launch(String scenario) throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            .addString("requestId", UUID.randomUUID().toString(), true)
            .addString("scenario", scenario, false)
            .toJobParameters();
        return jobLauncherTestUtils.launchJob(parameters);
    }
}
```

Mỗi lần chạy có `requestId` identifying duy nhất để tạo `JobInstance` riêng. `scenario` là non-identifying trong ví dụ vì request ID đã phân biệt từng lần chạy; trong ứng dụng thực tế, identifying parameters phải được chọn theo đơn vị công việc nghiệp vụ.

## 7. Assertion khi nguồn input rỗng

Khi scenario là `EMPTY`, reader trả về `null` ngay lần đọc đầu tiên. Step vẫn có thể hoàn tất thành công, nhưng writer không có chunk output để ghi:

```java
@Test
void doesNotInvokeWriterWhenReaderHasNoItems() throws Exception {
    JobExecution execution = launch("EMPTY");

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

    StepExecution step = execution.getStepExecutions()
        .iterator()
        .next();

    assertThat(step.getReadCount()).isZero();
    assertThat(step.getWriteCount()).isZero();
    assertThat(writer.getWrittenChunks()).isEmpty();
}
```

Test này xác nhận cả trạng thái step và việc writer không được gọi. Chỉ assertion `writeCount == 0` chưa đủ để chứng minh writer không được gọi, vì một writer tùy chỉnh vẫn có thể được gọi với chunk rỗng trong một cách gọi trực tiếp hoặc một flow tùy chỉnh. Recording writer giúp quan sát chính xác số lần gọi trong job test.

## 8. Assertion khi processor lọc hết item

Trường hợp `FILTER_ALL` khác với input rỗng: reader vẫn đọc item, nhưng processor loại bỏ tất cả. Framework không gọi writer vì output chunk không có item:

```java
@Test
void doesNotInvokeWriterWhenProcessorFiltersEveryItem() throws Exception {
    JobExecution execution = launch("FILTER_ALL");

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

    StepExecution step = execution.getStepExecutions()
        .iterator()
        .next();

    assertThat(step.getReadCount()).isEqualTo(4);
    assertThat(step.getFilterCount()).isEqualTo(4);
    assertThat(step.getWriteCount()).isZero();
    assertThat(writer.getWrittenChunks()).isEmpty();
}
```

Test này chứng minh reader đã cung cấp bốn item, processor đã filter bốn item và writer không được gọi. Khi theo dõi production, đây là khác biệt quan trọng giữa nguồn rỗng và nguồn có dữ liệu nhưng toàn bộ dữ liệu bị loại.

## 9. Assertion khi có nhiều item và chunk cuối nhỏ

Với scenario `MANY`, reader cung cấp năm item và commit interval bằng ba. Writer được gọi hai lần:

```java
@Test
void writesManyItemsInSeparateChunks() throws Exception {
    JobExecution execution = launch("MANY");

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

    StepExecution step = execution.getStepExecutions()
        .iterator()
        .next();

    assertThat(step.getReadCount()).isEqualTo(5);
    assertThat(step.getWriteCount()).isEqualTo(5);

    assertThat(writer.getWrittenChunks())
        .containsExactly(List.of(1, 2, 3), List.of(4, 5));
}
```

Assertion `containsExactly` kiểm tra cả số lần gọi, kích thước từng chunk và thứ tự item. Nếu thứ tự không phải yêu cầu nghiệp vụ, có thể dùng assertion ít ràng buộc hơn. Trong ví dụ này, reader tuần tự nên thứ tự được giữ nguyên.

Chunk cuối có hai item dù commit interval là ba. Đây là hành vi bình thường; writer nhận phần còn lại và ghi nó trong transaction cuối. Không cần thêm item giả để làm đầy chunk.

## 10. Kiểm thử writer được gọi trực tiếp với nhiều kích thước chunk

Ngoài kiểm thử tích hợp, có thể viết parameterized test cho writer để kiểm tra nhiều kích thước đầu vào: 0, 1, đúng commit interval và lớn hơn commit interval. Unit test trực tiếp không mô phỏng việc framework chia chunk, nhưng giúp xác nhận writer xử lý được mọi collection mà implementation của nó dự kiến nhận.

Ví dụ với writer ghi vào repository:

```java
@ParameterizedTest
@ValueSource(ints = {1, 2, 3, 10})
void writesAllItemsForDifferentChunkSizes(int size) throws Exception {
    OrderItemWriter writer = new OrderItemWriter(repository);
    Chunk<Order> chunk = new Chunk<>();

    for (int i = 1; i <= size; i++) {
        chunk.add(new Order("ORDER-" + i, BigDecimal.TEN));
    }

    writer.write(chunk);

    verify(repository).saveAll(argThat(items ->
        StreamSupport.stream(items.spliterator(), false).count() == size
    ));
}
```

Nếu muốn kiểm thử chunk rỗng trong cùng bộ test, thêm trường hợp `size = 0` và assertion phù hợp với hợp đồng writer: no-op hoặc gọi repository với danh sách rỗng. Không nên trộn assertion của unit test này với kỳ vọng framework gọi writer khi output rỗng.

## 11. Kiểm tra transaction và rollback khi writer lỗi

Writer thường thực hiện thao tác ghi của chunk. Nếu writer ném exception và thao tác ghi tham gia transaction của step, transaction chunk sẽ rollback. Các chunk trước đã commit vẫn được giữ lại; chunk hiện tại không được xem là ghi thành công.

Một test tích hợp có thể dùng writer giả lập ném exception ở lần gọi thứ hai:

```java
public class FailingRecordingWriter<T> implements ItemWriter<T> {

    private int calls;

    @Override
    public void write(Chunk<? extends T> chunk) {
        calls++;
        if (calls == 2) {
            throw new IllegalStateException("Simulated writer failure");
        }
    }
}
```

Với commit interval 3 và năm item, lần ghi đầu có thể commit ba item. Lần ghi thứ hai thất bại và step/job kết thúc `FAILED` nếu không có retry/skip phù hợp. Khi test transaction thật, cần dùng database test và writer ghi vào database tham gia cùng transaction manager để kiểm tra rollback bằng dữ liệu đã commit, thay vì chỉ kiểm tra exception.

Nếu writer gọi API hoặc ghi sang một datasource không tham gia transaction, rollback của chunk không tự hoàn tác tác động bên ngoài. Khi đó cần idempotency hoặc transactional outbox. Đây là lý do writer cần được thiết kế để xử lý lại an toàn, kể cả khi processor đã được thiết kế thuần biến đổi.

## 12. Writer được gọi lại khi retry hoặc restart

Không nên giả định mỗi chunk chỉ gọi writer đúng một lần trong mọi tình huống. Nếu writer thất bại, fault-tolerant step có thể retry theo cấu hình. Nếu chunk rollback rồi job restart, dữ liệu chưa commit có thể được ghi lại.

Với writer có side effect bên ngoài, hãy kiểm tra:

- Hai lần ghi cùng một item có tạo ra bản ghi trùng hay không.
- API đích có nhận idempotency key ổn định hay không.
- Một chunk ghi một phần rồi thất bại có thể được gửi lại mà không nhân đôi dữ liệu hay không.
- Metadata và dữ liệu đích có cùng transaction hay cần outbox/đối soát.
- Writer có giữ trạng thái mutable giữa các lần gọi làm kết quả khác nhau hay không.

Với writer database, unique constraint và upsert có thể giúp chống ghi trùng, nhưng cần thiết kế theo khóa nghiệp vụ. Với message broker, cần phân biệt publish thành công với việc đánh dấu event đã publish; consumer nên idempotent vì delivery có thể lặp.

## 13. Dọn dữ liệu và cô lập test

Job test ghi metadata vào `JobRepository`, còn writer có thể ghi dữ liệu vào database test. Nếu nhiều test dùng chung database, dữ liệu từ test trước có thể ảnh hưởng assertion của test sau.

Một số cách cô lập:

- Dùng H2 hoặc schema riêng cho test.
- Dùng identifying parameter duy nhất cho từng lần chạy.
- Xóa dữ liệu nghiệp vụ test theo khóa của test, trong transaction hoặc fixture riêng.
- Dùng recording writer có instance riêng cho test hoặc gọi `clear()` trước mỗi execution.
- Dọn metadata bằng `JobRepositoryTestUtils` chỉ khi repository hoàn toàn thuộc quyền sở hữu của test suite.

Ví dụ:

```java
@Autowired
JobRepositoryTestUtils jobRepositoryTestUtils;

@AfterEach
void cleanMetadata() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

Không dùng tiện ích cleanup này trên repository production hoặc repository chia sẻ với job khác. Xóa metadata cũng không tự xóa dữ liệu mà writer đã ghi vào bảng nghiệp vụ; cần dọn hai phần theo cách độc lập và có kiểm soát.

Nếu test chạy song song, tránh dùng một recording writer singleton có danh sách mutable chung. Hãy tạo context/bean riêng, dùng dữ liệu test có khóa phân biệt hoặc đồng bộ việc ghi nhận để các test không ghi đè kết quả của nhau.

## 14. Các lỗi thường gặp khi kiểm thử writer

**Chỉ kiểm tra `writeCount`:** bộ đếm bằng 0 không nói rõ writer không được gọi hay writer có gọi nhưng không ghi item. Dùng recording writer hoặc verify mock để xác nhận invocation.

**Nhầm input rỗng với filter hết:** cả hai đều có thể không gọi writer, nhưng `readCount` và `filterCount` khác nhau. Kiểm tra cả reader, processor và bộ đếm step.

**Mong writer nhận chunk rỗng từ framework:** chunk processing tiêu chuẩn bỏ qua lời gọi writer khi output rỗng. Nếu cần kiểm thử implementation với chunk rỗng, gọi writer trực tiếp trong unit test.

**Cho rằng chunk cuối phải đủ commit interval:** writer nhận chunk cuối nhỏ hơn interval nếu còn item. Test số lượng không chia hết cho interval để xác nhận phần dữ liệu cuối không bị mất.

**Giữ tham chiếu đến chunk mutable:** lưu bản sao `new ArrayList<>(chunk.getItems())` trong recording writer để assertion không phụ thuộc vào thay đổi về sau.

**Chia sẻ writer stateful giữa test:** danh sách ghi nhận hoặc bộ đếm invocation có thể chứa dữ liệu từ test trước. Reset state hoặc tạo instance riêng.

**Không kiểm tra rollback:** writer ném exception có thể khiến chunk rollback, nhưng writer gọi hệ thống ngoài vẫn có thể đã tạo side effect. Dùng transaction test và idempotency phù hợp.

**Dọn metadata quá rộng:** xóa mọi execution trong repository dùng chung có thể ảnh hưởng test khác hoặc job đang chạy. Chỉ cleanup repository cô lập.

## 15. Thiết kế bộ test writer theo hành vi

Một bộ test writer hữu ích nên có các trường hợp sau:

1. **Một item:** writer nhận một item và ghi đúng một kết quả.
2. **Nhiều item:** writer ghi đủ item, đúng thứ tự nếu thứ tự có ý nghĩa.
3. **Chunk rỗng gọi trực tiếp:** writer xử lý theo hợp đồng đã chọn, thường là no-op.
4. **Nguồn rỗng trong job:** writer không được framework gọi; step vẫn có thể hoàn tất.
5. **Processor filter hết:** reader có read count, filter count tăng; writer không được gọi.
6. **Chunk cuối nhỏ:** writer nhận phần item còn lại và ghi đúng số lượng.
7. **Writer lỗi:** transaction chunk rollback và trạng thái job phản ánh thất bại nếu không phục hồi.
8. **Retry/restart:** writer có thể nhận lại item mà không tạo side effect trùng.

Không phải mọi writer đều cần tất cả các test ở cùng một lớp. Unit test nên tập trung vào logic mapping/ghi; integration test nên xác nhận cách framework chia chunk, gọi writer, quản lý transaction và cập nhật metadata.

## 16. Cách chọn assertion phù hợp

Khi kiểm tra nội dung writer nhận, dùng `containsExactly(...)` nếu thứ tự là một phần của hợp đồng. Dùng `containsExactlyInAnyOrder(...)` nếu thứ tự không quan trọng nhưng tập item phải đầy đủ. Với dữ liệu lớn, có thể kiểm tra kích thước, tổng số, khóa nghiệp vụ hoặc checksum thay vì so sánh toàn bộ object.

Khi kiểm tra số lần gọi, dùng `verify(writer, times(n))` nếu writer là mock hoặc dùng recording writer để lưu từng chunk. Với job có commit interval 3 và năm item không bị filter, kỳ vọng hai lần gọi có kích thước 3 và 2. Với input rỗng hoặc output rỗng, kỳ vọng không có invocation trong chunk processing mặc định.

Khi kiểm tra trạng thái, assertion `BatchStatus.COMPLETED` nên đi cùng các bộ đếm `readCount`, `filterCount`, `writeCount` và dữ liệu thực tế ở hệ thống đích nếu đó là mục tiêu của job. Một job hoàn tất không tự chứng minh writer đã ghi đúng dữ liệu.

Kiểm thử writer với chunk rỗng và nhiều item giúp xác nhận ranh giới giữa dữ liệu reader cung cấp, dữ liệu processor giữ lại và dữ liệu writer thực sự ghi. Kết hợp unit test cho writer với integration test cho job, kiểm tra invocation, kích thước chunk, transaction và hành vi retry, ứng dụng có thể phát hiện sớm việc bỏ sót item, ghi trùng hoặc xử lý sai trường hợp không có output.

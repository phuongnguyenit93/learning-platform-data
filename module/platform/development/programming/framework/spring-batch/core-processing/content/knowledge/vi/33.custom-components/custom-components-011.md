# Kiểm thử custom component độc lập

Trong Spring Batch, một Job được ghép từ các component như ItemReader, ItemProcessor, ItemWriter, Tasklet, listener và các service hỗ trợ. Khi tự viết component, nên kiểm thử logic của từng component độc lập trước khi ghép chúng vào Step hoặc Job. Cách này giúp xác định lỗi ở đúng ranh giới, chạy test nhanh và không cần khởi động toàn bộ Batch infrastructure cho mọi trường hợp.

Kiểm thử độc lập tập trung vào hợp đồng của component: input nào được nhận, output nào được trả về, trạng thái nào được lưu, exception nào được ném và dependency nào được gọi. Những hành vi cần JobRepository, transaction manager, scheduler hoặc database thật sẽ được kiểm tra ở integration test riêng.

## 1. Vì sao cần kiểm thử component độc lập?

Một Step có thể gồm nhiều thành phần:

~~~text
Resource / Database / Queue
          |
          v
      ItemReader
          |
          v
    ItemProcessor
          |
          v
       ItemWriter
          |
          v
   Database / File / API
~~~

Nếu một Job thất bại, nguyên nhân có thể nằm ở reader, processor, writer, transaction hoặc cấu hình Step. Nếu chỉ kiểm thử toàn Job, test có thể chậm và khó xác định component nào gây lỗi.

Unit test từng component giúp:

- Kiểm tra logic nghiệp vụ với input nhỏ và xác định.
- Bao phủ các trường hợp biên như null, empty, dữ liệu sai và exception.
- Xác nhận reader dừng đúng lúc và không bỏ sót item.
- Kiểm tra processor lọc hoặc biến đổi item đúng hợp đồng.
- Kiểm tra writer tạo đúng thao tác ghi và xử lý lỗi.
- Kiểm tra lifecycle của ItemStream và khả năng khôi phục state.
- Giảm phụ thuộc vào database, file system, broker và Spring context.

Không cần tạo JobLauncher hoặc JobRepository trong một test chỉ kiểm tra phép tính của processor. Hãy tạo đối tượng cần kiểm thử trực tiếp và thay dependency bên ngoài bằng fake hoặc mock phù hợp.

## 2. Phân biệt unit test, slice test và integration test

Ba loại test có mục tiêu khác nhau:

| Loại test | Phạm vi | Ví dụ |
| --- | --- | --- |
| Unit test | Một component và dependency được kiểm soát | Kiểm tra OrderProcessor tính thuế |
| Component test / slice test | Một nhóm component với một phần infrastructure | Kiểm tra reader với parser và file fixture |
| Spring Batch integration test | Step/Job cùng repository, transaction và resource | Chạy Step thật với database test và kiểm tra restart |

Unit test thường không cần khởi tạo ApplicationContext. Component test có thể dùng Spring context nhỏ nếu cần kiểm tra dependency injection hoặc scope. Integration test mới kiểm tra sự phối hợp của nhiều thành phần và infrastructure.

Không biến mọi unit test thành test khởi động toàn ứng dụng. Làm vậy tăng thời gian chạy và khiến lỗi cấu hình Spring che lấp lỗi logic của component.

## 3. Chọn test double phù hợp

Khi component phụ thuộc repository, client hoặc service ngoài, có thể dùng các loại test double:

| Loại | Mục đích |
| --- | --- |
| Stub | Trả kết quả đã định trước cho lời gọi |
| Fake | Cài đặt đơn giản nhưng có hành vi thật, ví dụ in-memory repository |
| Mock | Theo dõi lời gọi và cho phép cấu hình hành vi |
| Spy | Bọc một object thật để quan sát hoặc thay thế một phần hành vi |

Ví dụ processor phụ thuộc một service tra cứu khách hàng:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, OrderOutput> {

    private final CustomerService customerService;

    public OrderProcessor(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Override
    public OrderOutput process(OrderInput input) {
        Customer customer =
                customerService.findByCode(input.customerCode());

        if (customer == null) {
            throw new UnknownCustomerException(input.customerCode());
        }

        return new OrderOutput(
                input.orderId(),
                customer.id(),
                input.amount());
    }
}
~~~

Unit test có thể mock CustomerService để kiểm soát kết quả:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderProcessorTest {

    @Mock
    private CustomerService customerService;

    private OrderProcessor processor;

    @BeforeEach
    void setUp() {
        processor = new OrderProcessor(customerService);
    }

    @Test
    void mapsOrderWhenCustomerExists() throws Exception {
        OrderInput input =
                new OrderInput(1001L, "C001", new BigDecimal("250.00"));
        Customer customer = new Customer(501L, "C001");

        when(customerService.findByCode("C001"))
                .thenReturn(customer);

        OrderOutput output = processor.process(input);

        assertEquals(1001L, output.orderId());
        assertEquals(501L, output.customerId());
        assertEquals(new BigDecimal("250.00"), output.amount());
        verify(customerService).findByCode("C001");
    }
}
~~~

Ví dụ dùng record để ngắn gọn; nếu dự án dùng class thông thường, thay bằng constructor/getter tương ứng. Test kiểm tra kết quả nghiệp vụ và tương tác cần thiết, không phụ thuộc Spring Batch runtime.

## 4. Kiểm thử custom ItemReader

ItemReader có hợp đồng đơn giản: mỗi lần gọi read() trả về một item tiếp theo; khi không còn item, trả về null. Reader có thể ném exception nếu không thể đọc hoặc dữ liệu không hợp lệ.

Một custom reader có thể đọc từ repository:

~~~java
public class OrderCursorReader implements ItemReader<OrderInput> {

    private final OrderRepository repository;
    private final Iterator<OrderInput> iterator;

    public OrderCursorReader(OrderRepository repository) {
        this.repository = repository;
        this.iterator = repository.findPendingOrders().iterator();
    }

    @Override
    public OrderInput read() {
        return iterator.hasNext() ? iterator.next() : null;
    }
}
~~~

Đây chỉ là ví dụ reader nhỏ để minh họa hợp đồng. Trong thực tế, không nên nạp toàn bộ tập dữ liệu lớn vào List/Iterator nếu mục tiêu là đọc theo trang hoặc streaming.

### Kiểm tra thứ tự item và EOF

~~~java
@Test
void returnsItemsInOrderThenNullAtEnd() throws Exception {
    OrderRepository repository = mock(OrderRepository.class);
    when(repository.findPendingOrders()).thenReturn(List.of(
            new OrderInput(1L, "C001", new BigDecimal("10.00")),
            new OrderInput(2L, "C002", new BigDecimal("20.00"))));

    OrderCursorReader reader = new OrderCursorReader(repository);

    assertEquals(1L, reader.read().orderId());
    assertEquals(2L, reader.read().orderId());
    assertNull(reader.read());
    assertNull(reader.read());
}
~~~

Các kiểm tra quan trọng:

- Item được trả đúng thứ tự theo hợp đồng.
- Mỗi item chỉ được trả đúng số lần dự kiến.
- Khi hết dữ liệu, reader trả null.
- Gọi read() sau EOF không làm phát sinh item giả.
- Empty input trả null ngay ở lần đọc đầu.
- Lỗi từ nguồn được truyền ra theo exception phù hợp, không bị đổi thành EOF một cách âm thầm.

Nếu thứ tự là yêu cầu nghiệp vụ, test phải xác nhận thứ tự chứ không chỉ xác nhận tập item.

### Kiểm tra empty input

~~~java
@Test
void returnsNullWhenNoOrdersExist() throws Exception {
    OrderRepository repository = mock(OrderRepository.class);
    when(repository.findPendingOrders()).thenReturn(List.of());

    OrderCursorReader reader = new OrderCursorReader(repository);

    assertNull(reader.read());
}
~~~

Không trả về một object rỗng để biểu diễn hết dữ liệu. Theo hợp đồng ItemReader, null là dấu hiệu kết thúc input.

### Kiểm tra exception

~~~java
@Test
void propagatesRepositoryFailure() {
    OrderRepository repository = mock(OrderRepository.class);
    when(repository.findPendingOrders())
            .thenThrow(new DataAccessResourceFailureException("database unavailable"));

    assertThrows(
            DataAccessResourceFailureException.class,
            () -> new OrderCursorReader(repository));
}
~~~

Nếu custom reader bắt exception để thêm context, hãy kiểm tra exception mới giữ nguyên nguyên nhân gốc. Không bắt mọi exception rồi trả null, vì Spring Batch sẽ hiểu đó là hết dữ liệu và có thể kết thúc Step sai.

## 5. Kiểm thử reader có state

Reader có state cần kiểm thử nhiều hơn việc trả item. Nếu reader triển khai ItemStream, phải xác nhận open, update và close hoạt động đúng.

Ví dụ reader đọc danh sách nhỏ và lưu chỉ số tiếp theo:

~~~java
public class IndexedReader
        implements ItemStreamReader<String> {

    private static final String NEXT_INDEX = "indexedReader.nextIndex";

    private final List<String> items;
    private int nextIndex;

    public IndexedReader(List<String> items) {
        this.items = items;
    }

    @Override
    public void open(ExecutionContext context) {
        nextIndex = context.containsKey(NEXT_INDEX)
                ? context.getInt(NEXT_INDEX)
                : 0;
    }

    @Override
    public String read() {
        if (nextIndex >= items.size()) {
            return null;
        }
        return items.get(nextIndex++);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(NEXT_INDEX, nextIndex);
    }

    @Override
    public void close() {
        // Giải phóng resource nếu reader thực sự sở hữu resource.
    }
}
~~~

Test khôi phục state:

~~~java
@Test
void restoresPositionFromExecutionContext() throws Exception {
    IndexedReader reader =
            new IndexedReader(List.of("A", "B", "C", "D"));

    ExecutionContext context = new ExecutionContext();
    context.putInt("indexedReader.nextIndex", 2);

    reader.open(context);

    assertEquals("C", reader.read());
    assertEquals("D", reader.read());
    assertNull(reader.read());
}
~~~

Test checkpoint:

~~~java
@Test
void storesNextPositionInExecutionContext() throws Exception {
    IndexedReader reader =
            new IndexedReader(List.of("A", "B", "C"));
    ExecutionContext context = new ExecutionContext();

    reader.open(context);
    assertEquals("A", reader.read());
    assertEquals("B", reader.read());

    reader.update(context);

    assertEquals(2, context.getInt("indexedReader.nextIndex"));
}
~~~

Trong một reader thật, state nên mô tả vị trí có thể khôi phục như offset, page, sort key hoặc token. Không lưu cả danh sách item lớn vào ExecutionContext.

### Kiểm thử chu kỳ restart

Test có thể tạo reader thứ nhất, đọc một số item, gọi update, sau đó tạo instance mới và open bằng context đã lưu:

~~~java
@Test
void newReaderContinuesFromSavedCheckpoint() throws Exception {
    List<String> items = List.of("A", "B", "C", "D");
    ExecutionContext checkpoint = new ExecutionContext();

    IndexedReader firstRun = new IndexedReader(items);
    firstRun.open(checkpoint);
    assertEquals("A", firstRun.read());
    assertEquals("B", firstRun.read());
    firstRun.update(checkpoint);
    firstRun.close();

    IndexedReader restarted = new IndexedReader(items);
    restarted.open(checkpoint);

    assertEquals("C", restarted.read());
    assertEquals("D", restarted.read());
    assertNull(restarted.read());
}
~~~

Test này xác nhận logic của reader. Nó chưa chứng minh JobRepository lưu checkpoint trong transaction đúng cách; phần đó thuộc integration test của Step.

## 6. Kiểm thử reader quản lý resource

Reader có thể mở file, cursor, stream hoặc client session. Cần xác nhận resource được đóng đúng lúc và lỗi mở/đọc được xử lý đúng.

Có thể inject abstraction để test:

~~~java
public class MessageReader implements ItemStreamReader<Message> {

    private final MessageSource source;

    public MessageReader(MessageSource source) {
        this.source = source;
    }

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        source.open();
    }

    @Override
    public Message read() throws Exception {
        return source.receive();
    }

    @Override
    public void update(ExecutionContext context) {
        // Lưu offset hoặc token nếu source hỗ trợ.
    }

    @Override
    public void close() throws ItemStreamException {
        source.close();
    }
}
~~~

Test lifecycle:

~~~java
@Test
void delegatesResourceLifecycle() throws Exception {
    MessageSource source = mock(MessageSource.class);
    MessageReader reader = new MessageReader(source);
    ExecutionContext context = new ExecutionContext();

    reader.open(context);
    reader.update(context);
    reader.close();

    verify(source).open();
    verify(source).close();
}
~~~

Nếu reader mở resource trong constructor, test khó kiểm soát lifecycle và có thể mở connection trước khi Step bắt đầu. Ưu tiên mở resource trong open() và đóng trong close() theo hợp đồng ItemStream.

## 7. Kiểm thử custom ItemProcessor

ItemProcessor nhận một item và trả về item đã biến đổi. Nếu trả null, Spring Batch xem item đó bị filter và không chuyển tới writer.

Ví dụ processor:

~~~java
public class AmountProcessor
        implements ItemProcessor<OrderInput, OrderOutput> {

    @Override
    public OrderOutput process(OrderInput input) {
        if (input.amount() == null || input.amount().signum() <= 0) {
            return null;
        }

        BigDecimal tax = input.amount()
                .multiply(new BigDecimal("0.10"));
        BigDecimal total = input.amount().add(tax);

        return new OrderOutput(input.orderId(), total);
    }
}
~~~

Test trường hợp hợp lệ:

~~~java
@Test
void calculatesAmountAndTax() throws Exception {
    AmountProcessor processor = new AmountProcessor();
    OrderInput input =
            new OrderInput(1001L, "C001", new BigDecimal("100.00"));

    OrderOutput output = processor.process(input);

    assertEquals(1001L, output.orderId());
    assertEquals(new BigDecimal("110.0000"), output.totalAmount());
}
~~~

Scale của BigDecimal trong kết quả phụ thuộc phép tính và cách chuẩn hóa của ứng dụng. Trong dự án thật, nên định nghĩa rõ rounding mode và scale thay vì để test phụ thuộc scale phát sinh tình cờ.

### Test filter bằng null

~~~java
@Test
void filtersInvalidAmount() throws Exception {
    AmountProcessor processor = new AmountProcessor();
    OrderInput input =
            new OrderInput(1002L, "C002", BigDecimal.ZERO);

    assertNull(processor.process(input));
}
~~~

Phân biệt filter với lỗi dữ liệu. Nếu nghiệp vụ yêu cầu record sai phải được reject hoặc skip có thống kê, không nên trả null vì null có nghĩa là filter và có thể không kích hoạt skip listener.

### Test exception và boundary

Với processor, nên kiểm tra:

- Input null nếu API cho phép hoặc quy định rõ không cho phép.
- Giá trị bằng 0, âm và giá trị cực lớn.
- Field bắt buộc bị thiếu.
- Enum không hỗ trợ.
- Ngày ở biên timezone hoặc ngày không hợp lệ.
- Service dependency timeout hoặc trả về not found.
- Exception được phân loại đúng để Step có thể retry, skip hoặc fail.

Không viết một test cho mọi giá trị có thể có. Tập trung vào boundary làm thay đổi nhánh logic hoặc quy tắc nghiệp vụ.

## 8. Kiểm thử processor có dependency

Với processor gọi repository hoặc API, mock dependency để kiểm soát các tình huống:

~~~java
@ExtendWith(MockitoExtension.class)
class CustomerEnrichmentProcessorTest {

    @Mock
    private CustomerRepository repository;

    private CustomerEnrichmentProcessor processor;

    @BeforeEach
    void setUp() {
        processor = new CustomerEnrichmentProcessor(repository);
    }

    @Test
    void enrichesInputWhenCustomerExists() throws Exception {
        when(repository.findByCode("C001"))
                .thenReturn(Optional.of(new Customer(501L, "C001")));

        EnrichedOrder result = processor.process(
                new OrderInput(1001L, "C001", new BigDecimal("25.00")));

        assertEquals(501L, result.customerId());
        verify(repository).findByCode("C001");
    }

    @Test
    void rejectsUnknownCustomer() {
        when(repository.findByCode("MISSING"))
                .thenReturn(Optional.empty());

        assertThrows(
                UnknownCustomerException.class,
                () -> processor.process(
                        new OrderInput(1002L, "MISSING", BigDecimal.TEN)));
    }
}
~~~

Mock giúp kiểm soát phản hồi và xác nhận lời gọi quan trọng. Không nên verify mọi getter hoặc mọi lời gọi nội bộ vì test sẽ gắn chặt với implementation. Hãy assert output và chỉ verify interaction có ý nghĩa, chẳng hạn không gọi repository khi input đã bị loại từ bước validation.

## 9. Kiểm thử custom ItemWriter

ItemWriter nhận một Chunk các item và ghi chúng ra đích. Trong Spring Batch 5, phương thức write nhận Chunk:

~~~java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
~~~

Ví dụ writer chuyển item sang repository:

~~~java
public class OrderResultWriter implements ItemWriter<OrderOutput> {

    private final OrderResultRepository repository;

    public OrderResultWriter(OrderResultRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends OrderOutput> chunk) {
        repository.saveAll(chunk.getItems());
    }
}
~~~

Test writer:

~~~java
@Test
void writesEveryItemInChunk() throws Exception {
    OrderResultRepository repository =
            mock(OrderResultRepository.class);
    OrderResultWriter writer = new OrderResultWriter(repository);

    List<OrderOutput> items = List.of(
            new OrderOutput(1L, new BigDecimal("10.00")),
            new OrderOutput(2L, new BigDecimal("20.00")));

    writer.write(new Chunk<>(items));

    verify(repository).saveAll(items);
}
~~~

Test xác nhận writer chuyển đúng item và đúng thứ tự nếu thứ tự có ý nghĩa. Với writer thực hiện insert/update, có thể capture tham số để kiểm tra mapping SQL hoặc command object.

### Test chunk rỗng

Nếu writer có thể được gọi với chunk rỗng trong cách sử dụng riêng, hãy xác định hành vi mong muốn:

~~~java
@Test
void doesNotCallRepositoryForEmptyChunk() throws Exception {
    OrderResultRepository repository =
            mock(OrderResultRepository.class);
    OrderResultWriter writer = new OrderResultWriter(repository);

    writer.write(new Chunk<>());

    verifyNoInteractions(repository);
}
~~~

Hành vi này là lựa chọn của custom writer. Đừng áp đặt cho mọi writer; nếu writer cần ghi marker hoặc metadata dù chunk rỗng, test phải phản ánh đúng contract đó.

### Test lỗi ghi

~~~java
@Test
void propagatesRepositoryWriteFailure() {
    OrderResultRepository repository =
            mock(OrderResultRepository.class);
    OrderResultWriter writer = new OrderResultWriter(repository);

    doThrow(new DataAccessResourceFailureException("write failed"))
            .when(repository).saveAll(anyList());

    assertThrows(
            DataAccessResourceFailureException.class,
            () -> writer.write(new Chunk<>(List.of(
                    new OrderOutput(1L, BigDecimal.TEN)))));
}
~~~

Writer không nên nuốt exception rồi tiếp tục như thể ghi thành công. Spring Batch cần biết thao tác ghi thất bại để rollback, retry hoặc fail theo cấu hình Step.

## 10. Kiểm thử writer có ItemStream

Custom writer có thể triển khai ItemStreamWriter để quản lý file, buffer hoặc checkpoint. Kiểm thử riêng:

- open() khởi tạo resource đúng một lần.
- write() ghi đúng nội dung hoặc cập nhật đúng buffer.
- update() lưu state cần thiết.
- open() lần sau khôi phục từ state.
- close() giải phóng resource kể cả khi xử lý lỗi.

Ví dụ writer lưu số item đã ghi:

~~~java
public class CountingWriter<T> implements ItemStreamWriter<T> {

    private static final String COUNT_KEY = "countingWriter.count";
    private int count;

    @Override
    public void open(ExecutionContext context) {
        count = context.containsKey(COUNT_KEY)
                ? context.getInt(COUNT_KEY)
                : 0;
    }

    @Override
    public void write(Chunk<? extends T> chunk) {
        count += chunk.size();
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(COUNT_KEY, count);
    }

    @Override
    public void close() {
        // Đóng resource nếu có.
    }
}
~~~

Test:

~~~java
@Test
void persistsWriterState() throws Exception {
    CountingWriter<String> writer = new CountingWriter<>();
    ExecutionContext context = new ExecutionContext();

    writer.open(context);
    writer.write(new Chunk<>(List.of("A", "B", "C")));
    writer.update(context);

    assertEquals(3, context.getInt("countingWriter.count"));
}
~~~

Đây là ví dụ minh họa state. Với writer ghi file thật, nên test nội dung file và vị trí khôi phục bằng temporary directory thay vì chỉ kiểm tra một counter.

## 11. Kiểm thử Tasklet độc lập

Tasklet thực hiện một thao tác hữu hạn trong một lần gọi execute hoặc lặp lại tùy RepeatStatus. Có thể test trực tiếp bằng mock dependency và StepContribution/ChunkContext.

Ví dụ:

~~~java
public class ArchiveTasklet implements Tasklet {

    private final ArchiveService archiveService;

    public ArchiveTasklet(ArchiveService archiveService) {
        this.archiveService = archiveService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        archiveService.archiveCompletedOrders();
        return RepeatStatus.FINISHED;
    }
}
~~~

Test:

~~~java
@Test
void archivesCompletedOrdersAndFinishes() throws Exception {
    ArchiveService archiveService = mock(ArchiveService.class);
    ArchiveTasklet tasklet = new ArchiveTasklet(archiveService);

    RepeatStatus result = tasklet.execute(
            mock(StepContribution.class),
            mock(ChunkContext.class));

    assertEquals(RepeatStatus.FINISHED, result);
    verify(archiveService).archiveCompletedOrders();
}
~~~

Nếu Tasklet trả CONTINUABLE, cần kiểm tra điều kiện dừng và state qua nhiều lần execute. Tránh test bằng vòng lặp vô hạn; dùng stub để kiểm soát số lần gọi và xác nhận sau khi đạt điều kiện thì trả FINISHED.

## 12. Kiểm thử listener độc lập

Listener thường ghi log, phát event, cập nhật audit hoặc điều chỉnh trạng thái. Có thể gọi callback trực tiếp với StepExecution/JobExecution được tạo trong test.

Ví dụ StepExecutionListener:

~~~java
public class AuditStepListener implements StepExecutionListener {

    private final AuditService auditService;

    public AuditStepListener(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        auditService.started(
                stepExecution.getId(),
                stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        auditService.finished(
                stepExecution.getId(),
                stepExecution.getStatus().name());
        return null;
    }
}
~~~

Test:

~~~java
@Test
void recordsStepStartAndFinish() {
    AuditService auditService = mock(AuditService.class);
    AuditStepListener listener = new AuditStepListener(auditService);
    StepExecution execution =
            MetaDataInstanceFactory.createStepExecution();

    listener.beforeStep(execution);
    ExitStatus exitStatus = listener.afterStep(execution);

    verify(auditService).started(
            execution.getId(),
            execution.getStepName());
    verify(auditService).finished(
            execution.getId(),
            execution.getStatus().name());
    assertNull(exitStatus);
}
~~~

Nếu listener trả về ExitStatus mới, test cần xác nhận chính xác mã và mô tả. Listener chỉ ghi audit/metrics thường nên trả null để giữ ExitStatus hiện tại.

Với JobExecutionListener, tạo JobExecution bằng test factory phù hợp rồi gọi beforeJob/afterJob trực tiếp. Không cần JobLauncher nếu mục tiêu chỉ là kiểm tra nội dung event.

## 13. Kiểm thử late binding và Step scope

Bean @StepScope hoặc @JobScope dùng scoped proxy và cần context tương ứng. Nếu unit test gọi target trực tiếp mà không kích hoạt scope, có thể gặp lỗi scope không active.

Spring Batch Test cung cấp StepScopeTestUtils để chạy một callback trong StepExecution context:

~~~java
@SpringBatchTest
@SpringJUnitConfig(BatchConfiguration.class)
class ScopedReaderTest {

    @Autowired
    private ItemReader<OrderInput> orderReader;

    @Test
    void readsUsingCurrentStepContext() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "orders-test.json")
                .toJobParameters();
        StepExecution stepExecution =
                MetaDataInstanceFactory.createStepExecution(parameters);

        OrderInput item = StepScopeTestUtils.doInStepScope(
                stepExecution,
                () -> orderReader.read());

        assertNotNull(item);
    }
}
~~~

Ví dụ này cần file fixture và cấu hình Batch tương ứng. API factory và test support cần khớp phiên bản Spring Batch Test của dự án.

Nếu chỉ kiểm tra logic processor không phụ thuộc scope, hãy tạo processor trực tiếp thay vì khởi động Spring context. Dùng scope test khi thực sự cần xác nhận late binding, SpEL hoặc scoped proxy.

### Kiểm tra hai StepExecution có state riêng

Nếu bean đọc JobParameters hoặc StepExecutionContext, nên tạo hai StepExecution với giá trị khác nhau và xác nhận proxy trả target đúng theo context hiện tại. Điều này phát hiện singleton vô tình giữ giá trị của lần chạy đầu.

Không dùng một StepExecution context cho toàn bộ test suite nếu test cần kiểm tra tính độc lập giữa hai execution.

## 14. Kiểm thử exception để hỗ trợ retry và skip

Custom component cần ném loại exception có ý nghĩa. Spring Batch dùng exception type trong retry/skip policy, vì vậy test cần xác nhận đúng loại exception được truyền ra.

Ví dụ:

~~~java
@Test
void throwsInvalidOrderForBusinessDataError() {
    OrderProcessor processor = new OrderProcessor(customerService);
    OrderInput invalid = new OrderInput(
            null, "C001", new BigDecimal("10.00"));

    assertThrows(
            InvalidOrderException.class,
            () -> processor.process(invalid));
}
~~~

Nên phân biệt:

- Lỗi dữ liệu vĩnh viễn: có thể reject hoặc skip nếu nghiệp vụ cho phép.
- Lỗi tạm thời: có thể retry, ví dụ timeout dịch vụ hoặc deadlock.
- Lỗi cấu hình: thường cần fail sớm thay vì retry.
- Lỗi hạ tầng không phục hồi: cần fail và cảnh báo.

Không test retry limit bằng cách gọi component trực tiếp nhiều lần rồi kết luận Step sẽ retry đúng. Retry là hành vi của fault-tolerant Step và cần integration test với cấu hình retry thật.

## 15. Kiểm thử transaction ở đúng tầng

Unit test của custom writer có thể xác nhận nó gọi repository hoặc JDBC abstraction đúng cách. Nhưng unit test không chứng minh database rollback khi chunk thất bại.

Để kiểm tra transaction:

- Dùng database test và transaction manager thật.
- Chạy Step hoặc chunk integration test.
- Gây lỗi có kiểm soát sau một thao tác ghi.
- Truy vấn database sau khi Step kết thúc để xác nhận dữ liệu chưa commit đã rollback.
- Kiểm tra JobRepository/checkpoint nếu test có restart.

Không mock transaction manager rồi kết luận rollback hoạt động. Mock chỉ xác nhận lời gọi method, không thực thi semantics transaction của database.

Nếu custom component gọi API hoặc ghi file ngoài transaction database, unit test cần xác nhận request/file command đúng; integration test phải kiểm tra chiến lược idempotency, staging hoặc compensation của ứng dụng.

## 16. Kiểm thử với file fixture và temporary directory

Reader/writer xử lý file thường dễ test bằng thư mục tạm do JUnit cung cấp:

~~~java
@TempDir
Path tempDir;
~~~

Tạo file đầu vào:

~~~java
Path input = tempDir.resolve("orders.csv");
Files.writeString(
        input,
        "orderId,amount\n1001,250.00\n",
        StandardCharsets.UTF_8);
~~~

Sau khi gọi reader, assert object đã được parse đúng. Với writer, ghi các item vào file trong tempDir rồi đọc lại bằng đúng charset và parser để kiểm tra nội dung.

Các tình huống nên có:

- File rỗng.
- File chỉ có header.
- Một record và nhiều record.
- Ký tự Unicode.
- Dòng thiếu field hoặc thừa field.
- Delimiter/quote trong giá trị.
- Line ending LF và CRLF nếu cần hỗ trợ cả hai.
- File không tồn tại hoặc không có quyền đọc.
- Writer ghi lỗi hoặc thư mục đích không tồn tại.

Temporary directory được test framework quản lý và dọn dẹp. Không dùng đường dẫn output cố định trong thư mục làm việc vì test chạy song song có thể ghi đè lẫn nhau.

## 17. Kiểm thử với clock và thời gian xác định

Component tạo timestamp bằng Instant.now() thường khó test vì kết quả thay đổi theo thời điểm chạy.

Thay vì gọi system clock trực tiếp, inject Clock:

~~~java
public class TimestampProcessor
        implements ItemProcessor<OrderInput, OrderOutput> {

    private final Clock clock;

    public TimestampProcessor(Clock clock) {
        this.clock = clock;
    }

    @Override
    public OrderOutput process(OrderInput input) {
        return new OrderOutput(input.orderId(), Instant.now(clock));
    }
}
~~~

Test với clock cố định:

~~~java
@Test
void usesProvidedClock() throws Exception {
    Instant fixedInstant = Instant.parse("2026-11-15T10:30:00Z");
    Clock clock = Clock.fixed(fixedInstant, ZoneOffset.UTC);
    TimestampProcessor processor = new TimestampProcessor(clock);

    OrderOutput output = processor.process(
            new OrderInput(1001L, "C001", BigDecimal.TEN));

    assertEquals(fixedInstant, output.processedAt());
}
~~~

Clock cố định giúp test ổn định, không phụ thuộc timezone hoặc thời điểm thực thi. Nếu nghiệp vụ dùng ngày địa phương, truyền ZoneId rõ ràng và test cả thời điểm sát ranh giới ngày.

## 18. Kiểm thử tính bất biến và side effect

Processor thường nên biến đổi input thành output mà không sửa object đầu vào nếu không có lý do rõ ràng. Test có thể giữ lại giá trị trước khi gọi và xác nhận input không bị thay đổi.

Ví dụ:

~~~java
@Test
void doesNotMutateInput() throws Exception {
    OrderInput input =
            new OrderInput(1001L, "C001", new BigDecimal("10.00"));

    AmountProcessor processor = new AmountProcessor();
    processor.process(input);

    assertEquals("C001", input.customerCode());
    assertEquals(new BigDecimal("10.00"), input.amount());
}
~~~

Nếu component có side effect, test cần xác nhận side effect được gọi đúng số lần và với key phù hợp. Với API có idempotency key, assert key ổn định theo business ID để retry không tạo thao tác trùng.

Không dùng test unit để giả định side effect ngoài hệ thống sẽ rollback cùng database. Đó là vấn đề kiến trúc cần được kiểm tra ở integration test hoặc contract test.

## 19. Kiểm thử concurrency ở mức component

Nếu custom component được thiết kế để dùng đồng thời, cần xác định state nào được chia sẻ và state nào riêng cho thread/execution.

Các câu hỏi cần kiểm tra:

- Reader có thread-safe hay chỉ dùng một thread?
- Writer có thể nhận nhiều Chunk đồng thời không?
- Counter hoặc buffer có cần atomic/synchronized không?
- Một execution có thể ghi đè state của execution khác không?
- Dependency mock/fake có hỗ trợ gọi đồng thời trong test không?

Không viết test concurrency chỉ bằng cách gọi nhiều thread rồi kiểm tra một counter chung nếu điều đó không đại diện cho cách Step thực sự chạy. Test concurrency nên mô phỏng đúng contract, số worker và cơ chế đồng bộ của component.

Nếu component không thread-safe, ghi rõ nó chỉ được dùng trong single-threaded Step hoặc dùng partitioning để mỗi worker có instance riêng. Một unit test xác nhận logic đơn luồng không chứng minh component an toàn khi dùng chung nhiều thread.

## 20. Dùng JUnit parameterized test cho nhiều trường hợp

Với logic có nhiều input/output đơn giản, parameterized test giúp tránh lặp code:

~~~java
@ParameterizedTest
@CsvSource({
        "100.00, 110.00",
        "0.00, 0.00",
        "50.00, 55.00"
})
void calculatesExpectedTotal(
        String amount,
        String expectedTotal) throws Exception {

    AmountProcessor processor = new AmountProcessor();
    OrderInput input = new OrderInput(
            1L, "C001", new BigDecimal(amount));

    OrderOutput output = processor.process(input);

    assertEquals(
            new BigDecimal(expectedTotal),
            output.totalAmount());
}
~~~

Ví dụ cần điều chỉnh expected scale và quy tắc filter theo implementation thực tế. Với dữ liệu phức tạp, dùng MethodSource để tạo object rõ ràng hơn CSV string.

Parameterized test phù hợp cho boundary values, enum, format ngày và các trường hợp mapping. Không nhồi nhiều hành vi khác nhau vào một test chỉ để giảm số method.

## 21. Tổ chức test và đặt tên

Có thể tổ chức test theo component:

~~~text
src/test/java
  com.example.batch
    reader
      OrderReaderTest.java
    processor
      OrderProcessorTest.java
    writer
      OrderWriterTest.java
    tasklet
      ArchiveTaskletTest.java
    listener
      AuditStepListenerTest.java
~~~

Tên test nên mô tả điều kiện và kết quả:

- returnsItemsInOrderThenNullAtEnd
- restoresPositionFromExecutionContext
- filtersOrdersBelowMinimumAmount
- throwsInvalidOrderWhenCustomerIsMissing
- writesEveryItemInChunk
- propagatesRepositoryWriteFailure
- recordsStepStartAndFinish

Một test nên tập trung vào một hành vi chính. Có thể có nhiều assertion liên quan trong cùng test, nhưng tránh tạo một test lớn kiểm tra reader, processor, writer và transaction cùng lúc.

## 22. Những lỗi thường gặp khi test custom component

### Khởi động toàn bộ Spring context cho logic thuần

Test chậm và khó xác định lỗi. Tạo component trực tiếp, mock dependency và chỉ dùng Spring context khi cần kiểm tra wiring hoặc scope.

### Mock chính component đang kiểm thử

Test chỉ kiểm tra mock được cấu hình ra sao. Hãy tạo instance thật của component và mock dependency bên ngoài.

### Chỉ kiểm tra happy path

Reader, processor và writer thường có nhiều nhánh ở empty input, null, EOF, exception và dữ liệu biên. Thêm test cho các nhánh làm thay đổi hành vi.

### Reader trả empty object khi hết dữ liệu

Spring Batch hiểu null là EOF. Trả object rỗng có thể khiến Step xử lý thêm một item giả.

### Processor trả null cho mọi loại lỗi

Null biểu thị filter. Dùng exception rõ ràng cho lỗi dữ liệu cần skip/reject hoặc lỗi hệ thống cần retry/fail.

### Không kiểm thử ItemStream lifecycle

Reader/writer có thể hoạt động trong một lần gọi nhưng không khôi phục được sau restart. Test open/update/close và checkpoint riêng.

### Test transaction bằng mock

Mock không thực hiện rollback database. Dùng integration test với transaction manager và database phù hợp.

### Test scoped bean ngoài Step context

Scoped proxy cần context hoạt động. Dùng StepScopeTestUtils hoặc test listener khi cần xác nhận late binding.

### Test file trên đường dẫn cố định

Test có thể ghi đè dữ liệu hoặc xung đột khi chạy song song. Dùng @TempDir.

### Dựa vào thời gian hiện tại

Test có thể thất bại theo timezone hoặc thời điểm chạy. Inject Clock và dùng Clock.fixed.

### Verify mọi lời gọi nội bộ

Test dễ vỡ khi refactor dù kết quả không đổi. Ưu tiên assert output, exception và side effect có ý nghĩa.

### Cho rằng unit test chứng minh Step hoạt động đúng

Unit test không xác nhận transaction, retry, skip, checkpoint hoặc flow transition. Bổ sung integration test cho hành vi thuộc framework.

## 23. Khi nào cần Spring Batch Test?

Spring Batch Test cung cấp tiện ích hỗ trợ kiểm thử Job và Step, chẳng hạn:

- @SpringBatchTest để đăng ký test utilities.
- JobLauncherTestUtils để chạy Job hoặc Step trong integration test.
- JobRepositoryTestUtils để dọn metadata test khi phù hợp.
- StepScopeTestUtils để kích hoạt Step scope.
- StepScopeTestExecutionListener để cung cấp StepExecution context cho test.

Không cần các tiện ích này cho mọi unit test. Dùng chúng khi test cần Spring Batch infrastructure hoặc muốn xác nhận hành vi Step/Job thực tế.

Ví dụ chạy một Step qua JobLauncherTestUtils:

~~~java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class ImportStepIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void executesImportStep() throws Exception {
        JobExecution execution =
                jobLauncherTestUtils.launchStep("importOrdersStep");

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    }
}
~~~

Đây là integration test, không phải unit test độc lập. Nó hữu ích để kiểm tra Step wiring, reader/processor/writer lifecycle và metadata. Cần cấu hình test database/resource và xác nhận dữ liệu đầu ra, không chỉ assert BatchStatus.

## 24. Ma trận kiểm thử tối thiểu theo loại component

| Component | Trường hợp cần kiểm tra |
| --- | --- |
| ItemReader | Có dữ liệu, empty input, thứ tự, EOF, exception, state restore |
| ItemProcessor | Mapping đúng, filter bằng null, input biên, validation, dependency lỗi |
| ItemWriter | Chunk đúng, empty chunk theo contract, mapping ghi, write failure, state |
| Tasklet | Thực hiện side effect đúng, FINISHED/CONTINUABLE, lỗi dependency |
| Listener | Callback đúng, event đúng, giữ ExitStatus khi chỉ quan sát |
| ItemStream | open/update/close, khôi phục checkpoint, đóng resource |
| Scoped bean | Late binding theo StepExecution/JobExecution, state không rò rỉ |

Ma trận là điểm bắt đầu. Không phải mọi component đều cần mọi trường hợp; chọn test theo trách nhiệm và rủi ro thực tế của implementation.

## 25. Quy trình viết unit test cho custom component

Khi bắt đầu kiểm thử một component, hãy làm theo thứ tự:

1. Xác định interface và hợp đồng của component: input, output, EOF, exception và lifecycle.
2. Tách logic nghiệp vụ khỏi Spring context, database hoặc file nếu có thể.
3. Liệt kê dependency bên ngoài và quyết định dùng stub, fake hay mock.
4. Viết test happy path với input nhỏ, dễ đọc.
5. Viết test cho empty/null, boundary và exception.
6. Với reader/writer có state, kiểm tra ItemStream open/update/close và restart.
7. Với scoped bean, kích hoạt đúng StepExecution hoặc JobExecution context.
8. Với file, dùng fixture và temporary directory.
9. Với thời gian, inject Clock để tạo kết quả xác định.
10. Chỉ kiểm tra tương tác có ý nghĩa; tránh verify implementation detail.
11. Chuyển các hành vi transaction, retry, skip và flow sang integration test.
12. Chạy test trong cấu hình dự án và kiểm tra test không phụ thuộc thứ tự hoặc dữ liệu môi trường.

Mỗi test nên có tên mô tả điều kiện và kết quả. Giữ fixture nhỏ, không dùng chung mutable state giữa test và luôn dọn resource đã mở.

## Kết luận

Kiểm thử custom component độc lập giúp xác nhận hợp đồng của ItemReader, ItemProcessor, ItemWriter, Tasklet, listener và ItemStream mà không cần chạy toàn bộ Job. Tạo component thật, thay dependency bên ngoài bằng stub/fake/mock, kiểm tra happy path, EOF, filter, exception, state và resource lifecycle. Dùng StepScopeTestUtils khi cần late binding, temporary directory cho file và Clock cố định cho logic thời gian. Unit test không chứng minh transaction, retry, skip hay restart của toàn Step; những hành vi đó cần integration test với Spring Batch infrastructure và resource phù hợp. Tách đúng phạm vi test giúp lỗi được phát hiện nhanh, rõ nguyên nhân và dễ bảo trì.

# Thread safety của custom component

Trong Spring Batch, một custom component có thể được gọi bởi nhiều thread hoặc nhiều lần thực thi Job cùng lúc. Nếu component giữ state có thể thay đổi trong field, các lời gọi đồng thời có thể ghi đè dữ liệu của nhau, làm mất item, tạo kết quả sai hoặc gây lỗi khó tái hiện. Vì vậy, khi bật multi-threaded Step, partitioning, parallel flow hoặc chạy nhiều JobExecution đồng thời, cần xác định rõ component nào được chia sẻ và component nào có state riêng.

Thread safety không chỉ là việc thêm từ khóa synchronized. Cần hiểu vòng đời bean của Spring, phạm vi StepExecution, cách Spring Batch gọi reader/processor/writer, transaction theo thread, checkpoint và resource được chia sẻ. Một thiết kế tốt thường giữ component stateless, dùng dữ liệu bất biến, phân vùng công việc hoặc cô lập state theo từng StepExecution. Chỉ đồng bộ hóa khi thực sự cần chia sẻ một tài nguyên không thể tách riêng.

## 1. Thread safety là gì?

Một component được xem là thread-safe khi nhiều thread có thể gọi nó đồng thời mà không làm hỏng invariant hoặc tạo kết quả không nhất quán. Component có thể dùng state nội bộ, miễn là mọi truy cập và cập nhật state được kiểm soát đúng.

Ví dụ component sau không an toàn khi nhiều thread gọi đồng thời:

~~~java
public class SequenceProcessor
        implements ItemProcessor<OrderInput, Order> {

    private long sequence;

    @Override
    public Order process(OrderInput input) {
        sequence++;
        return new Order(sequence, input.orderId());
    }
}
~~~

Hai thread có thể cùng đọc một giá trị sequence, cùng tăng và tạo ra số thứ tự trùng nhau. Việc dùng long thay vì Long không giải quyết race condition.

Một cách tốt hơn là không giữ bộ đếm nghiệp vụ trong processor. Nếu sequence phải được cấp duy nhất, dùng sequence/identity do database quản lý hoặc một dịch vụ cấp ID có bảo đảm đồng thời. Nếu chỉ cần số đếm phục vụ metrics, có thể dùng AtomicLong hoặc cơ chế metrics thread-safe, nhưng không dùng bộ đếm đó làm checkpoint hay dữ liệu nghiệp vụ.

## 2. Những mô hình concurrency trong Spring Batch

Thread safety trở nên quan trọng khi một Job xử lý nhiều phần công việc đồng thời. Các mô hình thường gặp:

| Mô hình | Cách chạy | Rủi ro chính |
|---|---|---|
| Multi-threaded Step | Các chunk hoặc phần xử lý của Step được thực thi trên nhiều thread theo TaskExecutor | Component của Step có thể nhận lời gọi đồng thời |
| Partitioning | Một manager Step chia dữ liệu thành nhiều worker StepExecution | Worker dùng chung bean singleton hoặc ghi đè state/resource |
| Parallel flows | Nhiều nhánh Step chạy đồng thời | Service, listener và resource dùng chung giữa các nhánh |
| Concurrent JobExecution | Cùng Job definition được chạy cho nhiều JobInstance | Singleton bean được nhiều lần chạy sử dụng cùng lúc |
| Async processing | Processor hoặc công việc được gửi sang executor | Kết quả có thể hoàn tất không theo thứ tự và context không tự truyền sang mọi thread |

Không nên giả định mọi thành phần trong mọi mô hình đều được gọi trên cùng một thread. Cách phân phối lời gọi phụ thuộc loại Step, cấu hình executor và phiên bản Spring Batch. Hãy xác định chính xác thành phần nào được framework gọi đồng thời trong mô hình đang dùng rồi thiết kế tương ứng.

## 3. Spring bean mặc định là singleton

Trong Spring, bean không khai báo scope thường có scope singleton: một instance được dùng trong application context. Điều này có nghĩa hai JobExecution khác nhau có thể dùng cùng một instance reader, processor, writer, tasklet hoặc listener nếu bean đó được khai báo singleton.

Ví dụ:

~~~java
@Component
public class CustomerProcessor
        implements ItemProcessor<CustomerInput, Customer> {

    private String currentBatchId;

    public void setCurrentBatchId(String currentBatchId) {
        this.currentBatchId = currentBatchId;
    }

    @Override
    public Customer process(CustomerInput input) {
        return new Customer(currentBatchId, input.customerId());
    }
}
~~~

Thiết kế này không an toàn nếu hai JobExecution cùng cập nhật currentBatchId. Một thread có thể ghi batch ID của Job B trong khi thread khác đang xử lý item của Job A.

Không nên lưu dữ liệu thay đổi theo lần chạy trong field của singleton. Hãy truyền batch ID như tham số của item hoặc method, hoặc dùng bean scoped phù hợp nếu cần late binding.

## 4. Ưu tiên component stateless

Component stateless không giữ state thay đổi giữa các lần gọi. Nó chỉ dùng input hiện tại và dependency được cấu hình ổn định. Đây thường là lựa chọn dễ mở rộng và dễ kiểm thử nhất.

~~~java
@Component
public class NormalizeOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    private final CurrencyPolicy currencyPolicy;

    public NormalizeOrderProcessor(CurrencyPolicy currencyPolicy) {
        this.currencyPolicy = currencyPolicy;
    }

    @Override
    public Order process(OrderInput input) {
        BigDecimal normalizedAmount =
                currencyPolicy.normalize(input.amount(), input.currency());

        return new Order(
                input.orderId(),
                input.customerId(),
                normalizedAmount);
    }
}
~~~

Thiết kế này an toàn nếu CurrencyPolicy cũng không có mutable shared state hoặc tự quản lý state đồng thời đúng cách. Việc dùng final cho dependency ngăn thay thế tham chiếu sau khi constructor hoàn tất, nhưng không tự làm object được tham chiếu trở thành thread-safe.

Các nguyên tắc hữu ích:

- Giữ cấu hình bất biến sau khi bean được tạo.
- Dùng biến local cho dữ liệu của một lần gọi.
- Không lưu item hiện tại vào field.
- Không lưu batch ID hoặc partition ID trong field singleton.
- Tránh dùng collection mutable chung nếu không có cơ chế đồng bộ.
- Đưa state nghiệp vụ cần bền vững vào database hoặc ExecutionContext theo đúng phạm vi.

## 5. @StepScope không tự làm component thread-safe

@StepScope tạo target bean theo một StepExecution. Nó hữu ích để inject JobParameters hoặc StepExecutionContext của lần thực thi đó và cô lập bean giữa các StepExecution khác nhau.

Tuy nhiên, một StepExecution có thể được xử lý bởi nhiều thread trong multi-threaded Step. Các thread đó có thể cùng gọi một target bean @StepScope. Vì vậy, @StepScope không bảo đảm field mutable của bean an toàn khi truy cập đồng thời.

Phân biệt:

| Scope | Phạm vi instance | Điều scope giải quyết | Điều scope không giải quyết |
|---|---|---|---|
| Singleton | Một application context | Chia sẻ dependency và cấu hình | Không tự bảo vệ mutable state |
| @JobScope | Một JobExecution | Cô lập bean giữa các JobExecution | Không tự đồng bộ truy cập từ nhiều Step/thread |
| @StepScope | Một StepExecution | Cô lập bean giữa các StepExecution | Không tự bảo vệ nhiều thread cùng StepExecution |

Ví dụ reader @StepScope nhận partition range thường phù hợp với partitioning vì mỗi worker có StepExecution riêng. Nhưng nếu một worker Step lại chạy nhiều chunk thread cùng lúc, reader của worker đó vẫn có thể được nhiều thread dùng chung.

Hãy chọn scope theo vòng đời dữ liệu, sau đó vẫn đánh giá thread safety theo cách component được gọi.

## 6. Phân biệt state theo Job, Step, partition và item

Trước khi viết custom component, hãy xác định state thuộc phạm vi nào:

| Phạm vi | Ví dụ | Nơi lưu phù hợp |
|---|---|---|
| Toàn ứng dụng | Cấu hình, client dùng chung | Bean bất biến hoặc dependency thread-safe |
| Một JobExecution | Batch ID, source version | JobParameters hoặc JobExecutionContext |
| Một StepExecution | Checkpoint, phạm vi Step | StepExecutionContext / ItemStream |
| Một partition | minId, maxId, file segment | StepExecutionContext của worker |
| Một item | Validation result, transformed value | Item/biến local, không lưu vào field chung |
| Nghiệp vụ lâu dài | Trạng thái xử lý, business sequence | Database hoặc hệ thống nghiệp vụ |

Đừng dùng một field singleton để giữ state của nhiều item hoặc nhiều partition. Đừng dùng JobExecutionContext làm nơi cập nhật đồng thời một bộ đếm từ nhiều worker nếu không có cơ chế đồng bộ và quy tắc merge rõ ràng.

## 7. Reader và thread safety

Reader thường có state: vị trí hiện tại, cursor, file handle, page number hoặc checkpoint. Nhiều reader được thiết kế để một thread đọc tuần tự. Nếu nhiều thread gọi read() đồng thời, có thể xảy ra:

- Hai thread đọc cùng một item.
- Một item bị bỏ qua do cập nhật vị trí không nguyên tử.
- Thứ tự item thay đổi.
- Checkpoint không phản ánh đúng những item đã commit.
- Cursor hoặc file handle bị truy cập đồng thời không được hỗ trợ.

Không nên chia sẻ một reader stateful giữa các thread nếu implementation không cam kết thread-safe.

### Dùng partitioning để cô lập reader

Nếu có thể chia dữ liệu thành các phạm vi độc lập, partitioning thường là cách rõ ràng hơn. Mỗi worker StepExecution có reader riêng và phạm vi dữ liệu riêng.

~~~text
Manager Step
    |
    +--> Partition 0: IDs 1..1000 --> Reader 0 --> Writer 0
    |
    +--> Partition 1: IDs 1001..2000 --> Reader 1 --> Writer 1
    |
    +--> Partition 2: IDs 2001..3000 --> Reader 2 --> Writer 2
~~~

Reader có thể nhận minId/maxId qua StepExecutionContext:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<Customer> partitionReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return createReaderForRange(dataSource, minId, maxId);
}
~~~

Mỗi worker có một target reader theo StepExecution. Cần bảo đảm các range không chồng lấn, bao phủ đúng dữ liệu và có thứ tự paging ổn định. Nếu dùng keyset paging, sort key nên duy nhất hoặc có tie-breaker ổn định.

### SynchronizedItemStreamReader

Spring Batch cung cấp SynchronizedItemStreamReader để đồng bộ hóa lời gọi read() của một delegate ItemStreamReader. Nó có thể hữu ích khi cần chia sẻ một reader không thread-safe trong một số cấu hình.

Việc đồng bộ read() làm các lần lấy item diễn ra tuần tự, nên có thể giảm lợi ích concurrency ở reader. Ngoài ra, các item được đọc tuần tự vẫn có thể được xử lý và ghi ở các chunk/thread khác nhau theo thứ tự hoàn tất không cố định. Nếu checkpoint được cập nhật trong khi chunk hoàn tất không theo thứ tự, cần đánh giá khả năng restart và xử lý lại item.

SynchronizedItemStreamReader không biến toàn bộ pipeline thành một chuỗi xử lý có thứ tự và không làm mọi method của delegate tự động thread-safe. Đọc tài liệu API của phiên bản Spring Batch đang dùng và kiểm thử restart trước khi chọn wrapper này.

## 8. Processor và thread safety

Processor stateless thường dễ chạy song song vì mỗi lần gọi xử lý một item riêng. Rủi ro xuất hiện khi processor:

- Ghi item hiện tại vào field.
- Dùng HashMap hoặc ArrayList mutable chung.
- Tăng bộ đếm không đồng bộ.
- Dùng formatter hoặc parser không thread-safe.
- Gọi service có mutable state.
- Dùng ThreadLocal mà không dọn dẹp đúng cách.
- Dựa vào thứ tự item để tạo kết quả.

Ví dụ không an toàn:

~~~java
public class PriceProcessor implements ItemProcessor<Input, Output> {

    private final Map<String, BigDecimal> rates = new HashMap<>();
    private Input current;

    @Override
    public Output process(Input item) {
        current = item;
        BigDecimal rate = rates.get(item.currency());
        return convert(current, rate);
    }
}
~~~

Field current có thể bị thread khác ghi đè. HashMap không an toàn nếu có cập nhật đồng thời. Nếu rates chỉ được nạp một lần rồi không thay đổi, có thể tạo map bất biến sau khi khởi tạo:

~~~java
public class PriceProcessor implements ItemProcessor<Input, Output> {

    private final Map<String, BigDecimal> rates;

    public PriceProcessor(Map<String, BigDecimal> configuredRates) {
        this.rates = Map.copyOf(configuredRates);
    }

    @Override
    public Output process(Input item) {
        BigDecimal rate = rates.get(item.currency());
        if (rate == null) {
            throw new UnsupportedCurrencyException(item.currency());
        }
        return convert(item, rate);
    }
}
~~~

Map.copyOf tạo bản sao không sửa đổi qua tham chiếu map được trả về. Các giá trị bên trong cũng nên là object bất biến; một collection không sửa đổi nhưng chứa value mutable vẫn có thể cần bảo vệ riêng.

## 9. Writer và thread safety

Writer có thể nhận nhiều chunk đồng thời trong multi-threaded Step hoặc được dùng bởi nhiều worker nếu bean bị chia sẻ. Cần xác định writer có hỗ trợ concurrent calls hay không.

### JDBC writer

Các writer built-in như JdbcBatchItemWriter thường được cấu hình một lần rồi dùng trong Step. NamedParameterJdbcTemplate/JdbcTemplate được thiết kế để dùng chung sau khi cấu hình. Tuy nhiên, custom parameter provider, callback hoặc dependency được gọi từ writer vẫn phải thread-safe.

Không lưu Connection hoặc PreparedStatement đang dùng trong field của writer. Hãy dùng JdbcTemplate/NamedParameterJdbcTemplate để framework lấy connection theo transaction hiện tại.

### File writer

Hai thread ghi cùng một file có thể xen kẽ byte, đảo thứ tự hoặc làm hỏng record. Nếu cần parallel output, ưu tiên một file riêng cho mỗi partition rồi dùng Step khác merge các file sau khi tất cả worker hoàn tất.

Chỉ dùng synchronized write nếu chấp nhận ghi tuần tự và đã kiểm tra thứ tự, flush, checkpoint cùng restart. Một khóa synchronized quanh toàn bộ writer có thể loại bỏ phần lớn lợi ích của parallelism.

### Writer tùy chỉnh có buffer

Nếu writer giữ StringBuilder, list hoặc buffer trong field, các lời gọi đồng thời có thể làm trộn dữ liệu. Có thể dùng buffer riêng theo invocation hoặc đồng bộ hóa vùng critical section. Cần cân nhắc việc flush/clear buffer khi transaction rollback: dữ liệu đã đưa ra ngoài transaction không tự được hoàn tác.

## 10. Ví dụ custom writer với JDBC

Một custom writer có thể dùng JdbcTemplate và không giữ mutable state theo item:

~~~java
public class AuditItemWriter implements ItemWriter<AuditRecord> {

    private final JdbcTemplate jdbcTemplate;

    public AuditItemWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends AuditRecord> chunk) {
        jdbcTemplate.batchUpdate(
                """
                INSERT INTO batch_audit(record_id, event_type, created_at)
                VALUES (?, ?, ?)
                """,
                chunk.getItems(),
                chunk.size(),
                (statement, item) -> {
                    statement.setString(1, item.recordId());
                    statement.setString(2, item.eventType());
                    statement.setTimestamp(3, Timestamp.from(item.createdAt()));
                });
    }
}
~~~

Writer không lưu item hoặc statement trong field. JdbcTemplate quản lý callback JDBC và lấy connection theo transaction context hiện tại. Điều kiện quan trọng là DataSource của JdbcTemplate phải tham gia transaction manager mà Step đang dùng.

Nếu writer cần ghi thêm metrics, dùng metrics library có hỗ trợ concurrency. Không tự cộng vào một long field dùng chung rồi coi đó là số bản ghi đã commit: writer có thể được gọi lại hoặc chunk có thể rollback. Bộ đếm nghiệp vụ nên được đối soát từ database hoặc StepExecution metadata.

## 11. Tasklet và listener

Tasklet hoặc listener cũng có thể là singleton bean. Nếu cùng instance được dùng trong nhiều StepExecution, field mutable theo lần chạy có thể gây race condition.

Với Tasklet:

- Tránh lưu trạng thái của lần gọi execute() vào field singleton.
- Dùng biến local hoặc ExecutionContext cho checkpoint cần thiết.
- Dùng @StepScope nếu tasklet phụ thuộc tham số hoặc state riêng của StepExecution.
- Nếu cùng StepExecution có nhiều thread, vẫn phải bảo vệ state được chia sẻ.

Với listener:

- Không giả định callback luôn được gọi theo một thứ tự toàn cục khi có concurrency.
- Không dùng ArrayList/HashMap chung để ghi nhận callback đồng thời.
- Không dựa vào listener để thực hiện tác dụng phụ không idempotent.
- Nếu cần tổng hợp kết quả, dùng collector thread-safe hoặc lưu event bền vững rồi tổng hợp sau.

Listener có thể được gọi ở các thời điểm khác nhau của lifecycle. Cần phân biệt callback theo item, chunk, Step và Job để không nhầm lẫn giữa event của các thread.

## 12. ExecutionContext không phải kho state đồng thời tùy ý

ExecutionContext được dùng để lưu trạng thái cần khôi phục. Nó không nên được xem như một ConcurrentHashMap tổng quát cho mọi thread.

Trong partitioning, mỗi worker có StepExecutionContext riêng nên phù hợp để lưu checkpoint hoặc phạm vi của worker đó. Trong multi-threaded Step, nhiều chunk thread có thể cùng làm việc trong một StepExecution; cập nhật các key context từ nhiều thread cần được thiết kế rõ ràng.

Nguyên tắc:

- Mỗi component sở hữu một tập key có namespace riêng.
- Không để nhiều thread ghi cùng key mà không có quy tắc merge.
- Không cập nhật context từ thread tự tạo ngoài lifecycle Spring Batch nếu không kiểm soát transaction/persistence.
- Chỉ lưu dữ liệu nhỏ cần cho restart.
- Không lưu item đang xử lý vào context như một biến dùng chung.

Nếu cần tổng hợp số liệu từ nhiều partition, có thể để mỗi worker ghi kết quả riêng rồi manager Step đọc và tổng hợp sau khi worker hoàn tất. Cách này tránh tranh chấp trên một key chung.

## 13. ItemStream lifecycle và thread safety

Reader/writer triển khai ItemStream có ba callback open(), update() và close(). Đây là lifecycle của stream theo StepExecution, không phải callback được gọi độc lập cho từng item.

Không nên:

- Mở/đóng cùng một resource ở mỗi lần read hoặc write nếu component được thiết kế giữ resource xuyên Step.
- Để nhiều thread cùng cập nhật một checkpoint key mà không có cơ chế đồng bộ.
- Đóng reader hoặc writer từ một thread trong khi thread khác còn đang sử dụng.
- Giả định close() của một thread sẽ đợi mọi công việc do ứng dụng tự tạo hoàn tất.

Nếu component dùng trong partitioning, mỗi worker nên có stream/resource riêng. Nếu component được chia sẻ giữa nhiều thread, cần có hợp đồng đồng bộ rõ ràng cho cả read/write và checkpoint. Chỉ đồng bộ method read() không tự giải quyết trạng thái update()/close().

## 14. Transaction là thread-bound

Trong mô hình transaction thông thường của Spring, transaction gắn với thread hiện tại. Một transaction của chunk không tự truyền sang thread mới do ứng dụng tạo.

Điều này có nghĩa:

- Không dùng new Thread hoặc parallelStream() bên trong processor/writer để thực hiện database work rồi giả định nó thuộc transaction chunk hiện tại.
- Không giữ JDBC Connection trong field để chia sẻ giữa thread.
- Dùng JdbcTemplate hoặc repository để lấy connection theo transaction hiện hành.
- Nếu cần async work, thiết kế transaction boundary và xử lý lỗi riêng cho async task.
- Chỉ commit chunk khi tất cả thao tác thuộc chunk đã hoàn tất theo mô hình được cấu hình.

Nếu worker thread tự mở transaction riêng, transaction đó có thể commit dù transaction của chunk chính rollback. Đây là nguồn gây dữ liệu lệch nếu không có cơ chế phối hợp.

Với nhiều resource hoặc nhiều database, transaction local không tự bảo đảm atomicity xuyên resource. Cần xem xét transaction manager phù hợp, distributed transaction hoặc outbox/compensation.

## 15. Resource dùng chung và client bên ngoài

Các dependency như HTTP client, cache client hoặc connection pool có thể được thiết kế để dùng chung, nhưng cần kiểm tra thread-safety contract của implementation.

Ví dụ:

- JdbcTemplate và NamedParameterJdbcTemplate được thiết kế dùng chung sau khi cấu hình.
- Một số HTTP client là immutable/thread-safe; một số request builder hoặc response object chỉ dùng cho một request.
- EntityManager không nên được giữ trong field rồi dùng đồng thời ngoài transaction/context quản lý.
- File stream, cursor và mutable parser thường không an toàn nếu nhiều thread cùng truy cập.
- Một cache có thể thread-safe ở thao tác đơn lẻ nhưng không bảo đảm chuỗi thao tác read-modify-write là nguyên tử.

Đừng suy luận một object thread-safe chỉ vì nó được inject từ Spring. Spring quản lý lifecycle và dependency injection; thread safety thuộc hợp đồng của object và cách ứng dụng sử dụng nó.

## 16. Atomic và concurrent collections

Khi thật sự cần chia sẻ dữ liệu giữa các thread, có thể dùng các cấu trúc đồng bộ phù hợp:

| Nhu cầu | Lựa chọn có thể dùng |
|---|---|
| Bộ đếm kỹ thuật | AtomicLong hoặc LongAdder |
| Map cache cập nhật đồng thời | ConcurrentHashMap |
| Danh sách event append-only | ConcurrentLinkedQueue |
| Trạng thái phức hợp cần cập nhật nguyên tử | synchronized, Lock hoặc atomic reference/update function |
| Kết quả theo partition | Collection riêng theo partition rồi merge |

ConcurrentHashMap bảo vệ thao tác map ở mức phù hợp, nhưng chuỗi thao tác nhiều bước vẫn có thể race. Ví dụ kiểm tra containsKey rồi put không phải lúc nào cũng tương đương một thao tác nguyên tử; dùng computeIfAbsent hoặc phương thức atomic phù hợp.

AtomicLong bảo vệ phép cộng hoặc tăng, nhưng không tạo transaction với database. Nếu process tăng counter rồi chunk rollback, counter vẫn có thể giữ giá trị đã tăng. Do đó, chỉ dùng counter trong bộ nhớ cho telemetry hoặc mục tiêu không yêu cầu chính xác theo commit.

## 17. Synchronized và giới hạn của khóa

Từ khóa synchronized bảo đảm chỉ một thread tại một thời điểm thực thi vùng code được bảo vệ trên cùng monitor. Nó hữu ích khi cần bảo vệ một invariant nhỏ:

~~~java
public class InMemoryAuditCollector {

    private final List<AuditRecord> records = new ArrayList<>();

    public synchronized void add(AuditRecord record) {
        records.add(record);
    }

    public synchronized List<AuditRecord> snapshot() {
        return List.copyOf(records);
    }
}
~~~

Ví dụ này đồng bộ truy cập list. Tuy nhiên, mọi thread phải dùng cùng instance collector; tạo nhiều instance không bảo vệ state chung. Việc snapshot cũng tạo bản sao trong vùng khóa, nên danh sách lớn có thể làm tăng contention.

Không đặt synchronized quanh toàn bộ process() hoặc write() nếu bên trong có gọi network/database chậm mà không cần thiết. Khóa quá rộng làm các thread xếp hàng và triệt tiêu concurrency.

Khi dùng Lock, phải release trong finally. Với synchronized, monitor tự được giải phóng khi thoát khỏi block kể cả khi có exception.

## 18. Thứ tự xử lý và kết quả song song

Parallel processing thường không bảo đảm thứ tự hoàn tất giống thứ tự đọc. Ví dụ item 1 cần 2 giây, item 2 cần 100 ms; item 2 có thể hoàn tất trước item 1.

Nếu nghiệp vụ yêu cầu thứ tự:

- Chia partition theo khóa để các item phụ thuộc cùng nằm trong một partition.
- Giữ thứ tự trong mỗi partition nếu cần.
- Dùng sequence/version để writer phát hiện cập nhật cũ.
- Dùng cơ chế reorder có giới hạn nếu phải khôi phục thứ tự toàn cục.
- Tránh parallelism cho phần xử lý phụ thuộc tuần tự nếu không thể bảo đảm invariant.

Không nên dùng một biến sequence trong processor để suy ra thứ tự item khi nhiều thread chạy đồng thời. Thứ tự gọi process(), thứ tự hoàn tất và thứ tự commit có thể khác nhau.

## 19. Partitioning thường giúp cô lập state tốt hơn

Nếu workload có thể chia thành các vùng độc lập, partitioning cho phép mỗi worker có:

- StepExecution riêng.
- StepExecutionContext riêng.
- Reader và writer scoped riêng.
- Resource hoặc file riêng.
- Phạm vi khóa dữ liệu riêng.

Ví dụ partition theo region:

~~~java
@Bean
@StepScope
ItemReader<Customer> customerReader(
        @Value("#{stepExecutionContext['regionCode']}") String regionCode,
        CustomerRepository repository) {

    return new RegionCustomerReader(repository, regionCode);
}
~~~

Partitioner gán regionCode khác nhau cho mỗi worker. Reader của từng worker chỉ đọc vùng tương ứng.

Partitioning không tự giải quyết mọi race condition. Nếu hai partition ghi cùng customer ID hoặc cập nhật cùng một bảng tổng hợp, database vẫn có thể gặp lock contention hoặc lost update. Thiết kế partition key sao cho dữ liệu đầu ra ít chồng lấn nhất có thể.

## 20. Cẩn trọng với ThreadLocal

ThreadLocal lưu giá trị riêng theo thread, có thể hữu ích cho context kỹ thuật ngắn hạn. Tuy nhiên, thread pool tái sử dụng thread cho nhiều item hoặc nhiều JobExecution. Nếu không remove giá trị, dữ liệu của lần xử lý trước có thể rò sang tác vụ sau.

Không dùng ThreadLocal để thay thế JobParameters hoặc ExecutionContext. Những giá trị đó cần gắn với execution, không gắn với danh tính thread vì một execution có thể dùng nhiều thread và một thread có thể xử lý nhiều execution theo thời gian.

Nếu buộc phải dùng ThreadLocal:

- Đặt giá trị trong phạm vi rõ ràng.
- Dọn bằng remove() trong finally.
- Không lưu object lớn hoặc dữ liệu nhạy cảm.
- Không giả định child thread tự nhận giá trị.
- Kiểm thử với executor thread pool được tái sử dụng.

## 21. Retry và idempotency trong môi trường concurrent

Retry có thể làm cùng một item hoặc chunk được xử lý nhiều lần. Khi nhiều thread cùng retry, một thao tác kiểm tra rồi ghi có thể race:

~~~text
Thread A: kiểm tra order chưa tồn tại
Thread B: kiểm tra order chưa tồn tại
Thread A: insert order
Thread B: insert order
~~~

Kiểm tra ở Java không thay thế unique constraint trong database. Dùng khóa duy nhất, upsert, optimistic locking hoặc idempotency key để bảo vệ invariant ở nơi dữ liệu được lưu.

Các thao tác ngoài transaction như gửi email hoặc gọi API tạo giao dịch cần idempotency key ổn định. Retry sau timeout có thể xảy ra dù hệ thống đích đã thực hiện request nhưng response bị mất.

## 22. Ví dụ kiểm thử race condition

Unit test tuần tự không phát hiện được mọi lỗi concurrency. Có thể dùng CountDownLatch, CyclicBarrier hoặc executor để tạo các lời gọi đồng thời có kiểm soát.

Ví dụ kiểm tra collector:

~~~java
@Test
void recordsAllEventsFromConcurrentCallers() throws Exception {
    int workers = 8;
    int eventsPerWorker = 1_000;

    InMemoryAuditCollector collector = new InMemoryAuditCollector();
    ExecutorService executor = Executors.newFixedThreadPool(workers);
    CountDownLatch start = new CountDownLatch(1);

    try {
        List<Future<?>> tasks = new ArrayList<>();
        for (int worker = 0; worker < workers; worker++) {
            int workerId = worker;
            tasks.add(executor.submit(() -> {
                start.await();
                for (int i = 0; i < eventsPerWorker; i++) {
                    collector.add(new AuditRecord(workerId, i));
                }
                return null;
            }));
        }

        start.countDown();
        for (Future<?> task : tasks) {
            task.get();
        }

        assertEquals(workers * eventsPerWorker, collector.snapshot().size());
    } finally {
        executor.shutdownNow();
    }
}
~~~

Test này tạo tải đồng thời có thể lặp lại và xác nhận không mất event. Với component Spring Batch, nên bổ sung Step integration test chạy nhiều chunk/partition và kiểm tra invariant dữ liệu cuối cùng.

Không nên chỉ assert thời gian chạy hoặc dựa vào Thread.sleep() để tạo race. Dùng latch/barrier để đồng bộ thời điểm bắt đầu và buộc các thread đi qua vùng code liên quan.

## 23. Kiểm thử transaction và restart khi có concurrency

Thread safety cần được kiểm tra cùng transaction behavior:

- Một chunk rollback có làm counter trong memory sai lệch không?
- Hai partition có thể ghi trùng business key không?
- Restart có đọc lại item chưa commit mà không tạo duplicate không?
- Checkpoint có bị cập nhật vượt quá dữ liệu đã commit không?
- Listener có ghi audit hai lần khi retry không?
- Một resource có bị đóng khi worker khác vẫn đang dùng không?

Với database, dùng integration test trên database tương ứng nếu logic phụ thuộc locking/isolation. H2 có thể không tái hiện deadlock hoặc concurrency behavior giống PostgreSQL, MySQL, Oracle hay SQL Server.

Test restart nên giữ JobRepository và database giữa lần chạy đầu và lần restart. Tạo lỗi có chủ đích sau khi một số chunk đã commit, restart cùng identifying JobParameters, rồi đối chiếu tập business key cuối cùng để phát hiện thiếu hoặc trùng.

## 24. Logging và metrics trong xử lý song song

Khi nhiều thread xử lý cùng Step, log có thể xen kẽ. Nên ghi các định danh để truy vết:

- JobExecution ID.
- StepExecution ID.
- Partition name hoặc worker ID.
- Business key của item.
- Thread name nếu cần phân tích concurrency.
- Retry attempt hoặc error category.

Không dùng thread name làm định danh nghiệp vụ vì thread pool tái sử dụng thread và tên thread không ổn định giữa các lần chạy.

Metrics như processed count, failure count và latency cần dùng collector thread-safe. Phân biệt metrics trong bộ nhớ với StepExecution counters và số bản ghi thực sự đã commit. Khi chunk rollback hoặc retry, một lần gọi processor không đồng nghĩa một item đã được ghi thành công.

## 25. Các lỗi thường gặp

**Cho rằng singleton bean được Spring tự đồng bộ:** scope singleton chỉ nói về số instance, không bảo vệ field mutable.

**Cho rằng @StepScope đồng nghĩa thread-safe:** nhiều thread trong cùng StepExecution vẫn có thể dùng chung target bean.

**Chia sẻ một reader stateful giữa nhiều thread:** vị trí đọc, cursor và checkpoint có thể race. Dùng reader riêng theo partition hoặc cơ chế đồng bộ đã kiểm thử.

**Dùng HashMap/ArrayList mutable chung:** cập nhật đồng thời có thể mất dữ liệu hoặc làm hỏng cấu trúc. Dùng immutable state, concurrent collection hoặc khóa.

**Tăng counter trong processor rồi coi là số commit:** retry và rollback làm counter trong memory lệch với dữ liệu thực tế.

**Giữ Connection hoặc Statement trong field:** connection gắn với transaction/thread và không nên được chia sẻ giữa worker.

**Dùng synchronized quá rộng:** làm mọi thread chờ nhau và triệt tiêu lợi ích parallelism.

**Tạo thread thủ công trong processor/writer:** transaction và context của Spring Batch không tự truyền sang thread mới.

**Dùng ThreadLocal mà không remove:** thread pool có thể giữ state của item hoặc Job trước.

**Giả định thứ tự xử lý được giữ nguyên:** kết quả song song có thể hoàn tất và commit không theo thứ tự đọc.

**Cập nhật chung một ExecutionContext key từ nhiều worker:** checkpoint hoặc metadata có thể bị ghi đè. Dùng context riêng và merge sau.

**Không kiểm thử restart khi dùng synchronized reader:** đồng bộ read không tự bảo đảm checkpoint phù hợp với thứ tự commit.

## Kết luận

Thread safety của custom component trong Spring Batch phụ thuộc vào state mà component giữ, scope bean và mô hình concurrency đang chạy. Ưu tiên reader/processor/writer stateless, dependency bất biến và resource riêng theo StepExecution hoặc partition. Nhớ rằng @StepScope chỉ cô lập bean giữa các StepExecution; nhiều thread cùng một StepExecution vẫn có thể gọi chung target. Với reader stateful, file writer, listener, ExecutionContext và cache mutable, cần xác định quyền sở hữu state và đồng bộ đúng phạm vi. Transaction gắn với thread hiện tại, nên không tự tạo thread rồi kỳ vọng transaction chunk được truyền sang. Kiểm thử concurrency bằng latch/barrier, kiểm tra dữ liệu cuối, rollback và restart; dùng partitioning khi có thể chia dữ liệu độc lập để giảm chia sẻ state và giữ tính đúng đắn khi mở rộng xử lý song song.

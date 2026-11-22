# Implement ItemStream cho component có state

Trong Spring Batch, một component có state cần giữ lại tiến độ hoặc tài nguyên giữa các lần gọi thường phải tham gia lifecycle của `ItemStream`. Interface này cho phép framework mở component trước khi Step xử lý, lưu state tại các checkpoint và đóng tài nguyên khi Step kết thúc.

`ItemStream` đặc biệt quan trọng với custom `ItemReader` và `ItemWriter`. Ví dụ, một reader đọc API theo offset cần lưu offset đã commit; một writer ghi file cần lưu vị trí hoặc trạng thái ghi; một component xử lý cần giữ một số state bền vững qua restart. Nếu chỉ lưu state trong field Java, dữ liệu đó sẽ mất khi application process dừng và Job không thể khôi phục đúng tiến độ.

## 1. ItemStream là gì?

`ItemStream` là contract lifecycle của Spring Batch dành cho component cần mở, cập nhật và đóng state. Interface có ba phương thức:

```java
public interface ItemStream {

    void open(ExecutionContext executionContext) throws ItemStreamException;

    void update(ExecutionContext executionContext) throws ItemStreamException;

    void close() throws ItemStreamException;
}
```

Ý nghĩa của từng phương thức:

- `open(ExecutionContext)`: mở resource và khôi phục state đã lưu từ lần chạy trước. Nếu chưa có checkpoint, khởi tạo state ban đầu.
- `update(ExecutionContext)`: ghi state hiện tại vào `ExecutionContext` để Spring Batch lưu tại checkpoint.
- `close()`: giải phóng resource như stream, cursor, file handle hoặc client session.

Các interface reader/writer kết hợp với ItemStream:

```java
public interface ItemStreamReader<T> extends ItemReader<T>, ItemStream {
}

public interface ItemStreamWriter<T> extends ItemWriter<T>, ItemStream {
}
```

Vì vậy, một custom reader có state thường triển khai `ItemStreamReader<T>`, còn writer có state triển khai `ItemStreamWriter<T>`. `ItemStream` không thay thế `ItemReader` hoặc `ItemWriter`; nó bổ sung lifecycle và khả năng lưu/khôi phục state.

## 2. Vì sao component có state cần ItemStream?

Một bean Spring singleton có thể sống trong suốt vòng đời application context. Field của bean chỉ tồn tại trong bộ nhớ process. Khi Job bị dừng hoặc JVM crash, field đó biến mất.

Ví dụ một reader đọc API theo offset:

```java
public class ApiReader implements ItemReader<Customer> {

    private long nextOffset;

    @Override
    public Customer read() {
        Customer customer = api.fetch(nextOffset);
        nextOffset++;
        return customer;
    }
}
```

Reader này có thể đọc tiếp trong cùng process vì `nextOffset` vẫn còn trong bộ nhớ. Nhưng nếu Job đã commit 500 item rồi process bị dừng, instance mới sẽ khởi tạo `nextOffset` về 0. Reader đọc lại từ đầu và có thể tạo dữ liệu trùng.

Khi triển khai `ItemStream`, reader có thể lưu offset vào `ExecutionContext` trước mỗi commit. Lần restart tiếp theo, `open()` đọc offset đã lưu và tiếp tục từ vị trí phù hợp.

Các tình huống thường cần ItemStream:

- Reader giữ vị trí đọc trong file, cursor, API hoặc message source.
- Writer giữ vị trí ghi, số bản ghi đã ghi hoặc metadata của output.
- Component cần khôi phục một checkpoint nghiệp vụ qua restart.
- Component cần mở/đóng tài nguyên đúng theo vòng đời Step.
- Delegate bên trong composite reader/writer có state riêng.

Một service stateless không cần implement ItemStream chỉ để được Spring inject. Chỉ triển khai khi component thực sự có lifecycle hoặc state cần quản lý bởi Step.

## 3. ExecutionContext lưu state ở đâu?

`ExecutionContext` là một key-value map do Spring Batch quản lý. Có hai phạm vi thường gặp:

- **Step ExecutionContext:** state riêng của một `StepExecution`, thường dùng để lưu checkpoint của reader/writer.
- **Job ExecutionContext:** state ở phạm vi `JobExecution`, có thể được chia sẻ giữa các Step trong cùng JobExecution.

Với `ItemStream` của một Step, tham số truyền vào `open()` và `update()` thường là Step `ExecutionContext`. Spring Batch lưu metadata qua `JobRepository`, cho phép state được khôi phục khi Job restart.

Ví dụ state của reader:

```java
private static final String OFFSET_KEY = "customerApiReader.nextOffset";

@Override
public void open(ExecutionContext context) {
    nextOffset = context.getLong(OFFSET_KEY, 0L);
}

@Override
public void update(ExecutionContext context) {
    context.putLong(OFFSET_KEY, nextOffset);
}
```

`open()` lấy giá trị đã lưu; nếu key chưa tồn tại thì bắt đầu từ offset 0. `update()` ghi vị trí hiện tại để repository lưu tại checkpoint.

Không nên xem `ExecutionContext` như một nơi lưu mọi dữ liệu của ứng dụng. Chỉ lưu state cần để tiếp tục xử lý, không lưu object graph lớn, stream đang mở, JDBC connection, iterator hoặc dữ liệu có thể truy vấn lại dễ dàng.

## 4. Lifecycle open, update và close trong một Step

Trong chunk-oriented Step, Spring Batch quản lý lifecycle của các stream đã đăng ký. Về khái niệm, thứ tự diễn ra như sau:

```text
Step bắt đầu
    |
    v
open(executionContext)
    |
    v
read -> process -> write
    |
    v
update(executionContext)
    |
    v
Commit chunk và lưu checkpoint
    |
    +----> chunk tiếp theo
    |          |
    |          +--> read -> process -> write
    |          +--> update -> commit
    |
    v
Step kết thúc
    |
    v
close()
```

`open()` được gọi khi Step bắt đầu, trước khi component xử lý item. `update()` được gọi ở các điểm checkpoint, thường trước khi transaction chunk commit, để state trong `ExecutionContext` được lưu cùng tiến độ. `close()` giải phóng tài nguyên khi Step kết thúc.

Điểm quan trọng: không dùng `close()` để lưu checkpoint cuối cùng. `close()` chủ yếu dành cho giải phóng tài nguyên. Việc lưu state thuộc về `update()`.

Nếu `open()`, `read()`/`write()`, `update()` hoặc `close()` phát sinh lỗi, Step có thể thất bại tùy thời điểm và cách exception được xử lý. Không nên bắt rồi bỏ qua lỗi lifecycle vì điều đó có thể làm mất checkpoint hoặc để resource ở trạng thái không xác định.

## 5. Checkpoint được lưu tại commit boundary

Trong chunk processing, reader có thể đã đọc nhiều item trước khi writer ghi xong. `update()` cho phép component ghi state vào `ExecutionContext` ở checkpoint của chunk. JobRepository lưu context cùng tiến độ Step theo transaction/repository configuration.

Ví dụ chunk size 100:

```text
Chunk 1: đọc item 1..100
  update: nextOffset=100
  commit

Chunk 2: đọc item 101..200
  update: nextOffset=200
  commit

Chunk 3: đọc item 201..300
  writer lỗi -> rollback
```

Nếu chunk 3 rollback, checkpoint bền vững vẫn phải phản ánh chunk cuối đã commit, tức offset 200. Khi restart, reader tiếp tục từ item 201.

Trong cùng process, Spring Batch có thể buffer item đã đọc để replay khi rollback, tùy loại reader và transaction behavior. Sau process restart, buffer bộ nhớ không còn; reader phải dùng checkpoint đã lưu để khôi phục nguồn đọc.

Không ghi checkpoint bền vững sau mỗi lần `read()` nếu mục tiêu là checkpoint theo chunk. Việc ghi state vào `ExecutionContext` và commit metadata cần theo đúng transaction boundary để state không đi trước dữ liệu nghiệp vụ đã commit.

## 6. Tự implement ItemStreamReader

Một custom reader có state thường triển khai `ItemStreamReader<T>`. Ví dụ dưới đây đọc dữ liệu từ API có hỗ trợ offset và page size. API được giả định trả một page ổn định theo offset; danh sách rỗng có nghĩa đã hết dữ liệu.

```java
public class CustomerApiItemReader implements ItemStreamReader<Customer> {

    private static final String NEXT_OFFSET_KEY = "customerApiReader.nextOffset";
    private static final int PAGE_SIZE = 100;

    private final CustomerApiClient client;

    private long nextOffset;
    private Iterator<Customer> currentPage = Collections.emptyIterator();
    private boolean exhausted;

    public CustomerApiItemReader(CustomerApiClient client) {
        this.client = client;
    }

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        nextOffset = context.getLong(NEXT_OFFSET_KEY, 0L);
        currentPage = Collections.emptyIterator();
        exhausted = false;
    }

    @Override
    public Customer read() throws Exception {
        while (!currentPage.hasNext() && !exhausted) {
            List<Customer> page = client.fetch(nextOffset, PAGE_SIZE);

            if (page.isEmpty()) {
                exhausted = true;
                return null;
            }

            currentPage = page.iterator();
        }

        if (!currentPage.hasNext()) {
            return null;
        }

        Customer customer = currentPage.next();
        nextOffset++;
        return customer;
    }

    @Override
    public void update(ExecutionContext context) throws ItemStreamException {
        context.putLong(NEXT_OFFSET_KEY, nextOffset);
    }

    @Override
    public void close() throws ItemStreamException {
        currentPage = Collections.emptyIterator();
        exhausted = true;
    }
}
```

Ví dụ thể hiện ba trách nhiệm chính:

- `open()` khôi phục offset đã commit và reset buffer trong bộ nhớ.
- `read()` lấy item tiếp theo, tăng offset sau khi trả item.
- `update()` lưu offset hiện tại vào `ExecutionContext`.
- `close()` giải phóng state tạm trong reader.

Đây là ví dụ minh họa cho API có offset ổn định. Nếu API dùng continuation token, cần lưu token và vị trí bên trong page sao cho restart không bỏ sót item. Nếu một page đã được fetch nhưng mới xử lý một phần, chỉ lưu token của page tiếp theo là chưa đủ; phải lưu được vị trí tiếp tục trong page hiện tại hoặc dùng API có thể fetch lại từ item tiếp theo.

Ngoài ra, offset pagination chỉ an toàn khi thứ tự và tập dữ liệu nguồn ổn định. Nếu bản ghi mới được chèn trước offset hiện tại, offset có thể dịch chuyển và gây trùng hoặc bỏ sót. Có thể cần snapshot ID, watermark, sort key duy nhất hoặc continuation token gắn với một snapshot.

## 7. Tự implement ItemStreamWriter

Writer có state cũng có thể triển khai `ItemStreamWriter<T>`. Ví dụ writer cần lưu một số metadata về output như số bản ghi đã ghi hoặc vị trí logic của file.

```java
public class CountingOrderWriter implements ItemStreamWriter<Order> {

    private static final String WRITTEN_COUNT_KEY = "countingOrderWriter.writtenCount";

    private long writtenCount;

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        writtenCount = context.getLong(WRITTEN_COUNT_KEY, 0L);
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        // Ghi các Order vào đích theo transaction/resource phù hợp.
        // Chỉ tăng counter sau khi các thao tác ghi trong lời gọi này hoàn tất.
        writtenCount += chunk.size();
    }

    @Override
    public void update(ExecutionContext context) throws ItemStreamException {
        context.putLong(WRITTEN_COUNT_KEY, writtenCount);
    }

    @Override
    public void close() throws ItemStreamException {
        // Đóng resource output nếu writer đang giữ resource.
    }
}
```

Đây là ví dụ về lifecycle state, không phải writer file hoàn chỉnh. Với writer ghi file thực tế, cần đồng bộ vị trí file, nội dung đã ghi và checkpoint transaction. Nếu file được ghi ngoài transaction rồi chunk rollback, file có thể đã chứa dữ liệu trong khi `ExecutionContext` quay về checkpoint cũ. Khi restart, writer có thể ghi trùng.

Với file output, ưu tiên `FlatFileItemWriter` hoặc implementation Spring Batch đã xử lý state và restart. Nếu phải viết custom writer, thiết kế append/overwrite, truncate/seek, temporary file, atomic publish và idempotency rõ ràng. Với database writer, dùng transaction manager phù hợp để dữ liệu và metadata được commit nhất quán.

## 8. ItemProcessor có state có thể dùng ItemStream

Processor thường nên stateless: cùng input tạo cùng output và không phụ thuộc vào thứ tự gọi trước đó. Tuy nhiên, một processor có thể cần mở resource hoặc lưu state riêng, ví dụ một bộ tra cứu được tải theo StepExecution.

Khi cần lifecycle đó, processor có thể triển khai `ItemStream` cùng `ItemProcessor`:

```java
public class ReferenceEnrichmentProcessor
        implements ItemProcessor<Order, EnrichedOrder>, ItemStream {

    private static final String VERSION_KEY = "referenceProcessor.version";

    private final ReferenceService referenceService;
    private String referenceVersion;

    public ReferenceEnrichmentProcessor(ReferenceService referenceService) {
        this.referenceService = referenceService;
    }

    @Override
    public void open(ExecutionContext context) {
        referenceVersion = context.containsKey(VERSION_KEY)
                ? context.getString(VERSION_KEY)
                : referenceService.currentVersion();
    }

    @Override
    public EnrichedOrder process(Order order) {
        return referenceService.enrich(order, referenceVersion);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putString(VERSION_KEY, referenceVersion);
    }

    @Override
    public void close() {
        // Giải phóng resource nếu processor có mở resource.
    }
}
```

Trong ví dụ, processor giữ version của dữ liệu tham chiếu để lần restart không vô tình dùng một version khác. Nếu processor chỉ cần gọi một service stateless, không cần triển khai ItemStream.

Stateful processor cần đặc biệt cẩn thận với retry và rollback. Một lần `process()` có thể được gọi lại. Tránh tăng counter, ghi database hoặc gửi message không idempotent trong processor chỉ vì nó có state.

## 9. Đặt key ExecutionContext ổn định và không trùng

`ExecutionContext` là map dùng chung trong phạm vi StepExecution. Nếu hai component ghi cùng một key, component gọi sau có thể ghi đè state của component trước.

Không nên dùng key quá chung:

```java
context.putLong("offset", nextOffset);
context.putLong("count", count);
```

Nên đặt key có namespace theo component:

```java
context.putLong("customerApiReader.nextOffset", nextOffset);
context.putLong("orderWriter.writtenCount", writtenCount);
```

Một số base class như `ItemStreamSupport` cung cấp cơ chế tạo execution context key dựa trên tên component. Đặt tên component ổn định bằng `setName(...)` để tránh trùng key khi có nhiều reader/writer.

Ví dụ ý tưởng:

```java
public class CustomerReader extends ItemStreamSupport
        implements ItemStreamReader<Customer> {

    private static final String OFFSET = "nextOffset";

    @Override
    public void open(ExecutionContext context) {
        String key = getExecutionContextKey(OFFSET);
        nextOffset = context.getLong(key, 0L);
    }

    @Override
    public void update(ExecutionContext context) {
        String key = getExecutionContextKey(OFFSET);
        context.putLong(key, nextOffset);
    }
}
```

Tên method và cách cấu hình name cần đối chiếu với base class/version đang dùng, nhưng nguyên tắc là key phải duy nhất trong StepExecution và ổn định giữa các lần restart.

Không đổi tên reader hoặc key state tùy tiện khi còn JobExecution cần restart. Nếu cấu trúc state thay đổi, cần có chiến lược tương thích hoặc migration metadata.

## 10. Chỉ lưu dữ liệu cần thiết trong ExecutionContext

ExecutionContext được lưu bền vững qua JobRepository. Vì vậy, giá trị lưu vào đó phải có thể serialize theo serializer được cấu hình và phải đủ nhỏ để ghi metadata hiệu quả.

Các giá trị phù hợp thường gồm:

- Số dòng hoặc item count đã commit.
- Offset, page number hoặc continuation token.
- ID cuối cùng đã xử lý.
- Version/checksum của input.
- Trạng thái nghiệp vụ nhỏ cần cho Step tiếp theo.

Tránh lưu:

- `InputStream`, `BufferedReader`, `ResultSet`, `Connection` hoặc file handle đang mở.
- Iterator hoặc parser đang giữ trạng thái trong bộ nhớ.
- Toàn bộ danh sách hàng nghìn/hàng triệu item.
- Object không serialize được hoặc object graph lớn không cần thiết.
- Secret/token nhạy cảm nếu không có cơ chế bảo vệ phù hợp.

Resource đang mở phải được tạo lại trong `open()`. ExecutionContext chỉ lưu đủ thông tin để tái tạo vị trí hoặc trạng thái, không lưu chính resource handle.

## 11. Đăng ký ItemStream với Step

Khi reader hoặc writer trực tiếp được truyền vào Step và implementation cũng là `ItemStream`, các cấu hình Step chuẩn của Spring Batch thường tự đăng ký lifecycle cho component đó.

Ví dụ:

```java
return new StepBuilder("importCustomersStep", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(customerApiItemReader)
        .writer(customerWriter)
        .build();
```

Nếu reader/writer được bọc trong một delegate hoặc composite và component có state bị ẩn bên trong wrapper, Step có thể không tự nhận ra delegate là stream. Khi đó, cần đăng ký stream tường minh:

```java
return new StepBuilder("importCustomersStep", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(compositeReader)
        .writer(compositeWriter)
        .stream(delegateReader)
        .stream(delegateWriter)
        .build();
```

Hoặc wrapper/composite có thể tự implement `ItemStream` và chuyển tiếp ba callback đến các delegate:

```java
@Override
public void open(ExecutionContext context) {
    delegateReader.open(context);
}

@Override
public void update(ExecutionContext context) {
    delegateReader.update(context);
}

@Override
public void close() {
    delegateReader.close();
}
```

Nếu composite có nhiều delegate, phải đảm bảo mọi stream được mở, cập nhật và đóng đúng một lần. Khi một delegate lỗi trong `open()`, cần xử lý đóng các resource đã mở trước đó.

## 12. Điều gì xảy ra nếu quên đăng ký stream?

Nếu một component có implement `ItemStream` nhưng không được đăng ký với Step, Spring Batch có thể không gọi `open()`, `update()` hoặc `close()` cho component đó.

Hậu quả có thể gồm:

- Reader không khôi phục offset từ ExecutionContext.
- Writer không lưu checkpoint.
- Resource không được đóng đúng lifecycle.
- Restart bắt đầu từ đầu hoặc tiếp tục sai vị trí.
- State của delegate không được lưu dù wrapper bên ngoài vẫn chạy.

Một triệu chứng thường gặp là lần chạy đầu thành công nhưng restart sau lỗi lại đọc lại dữ liệu đã commit. Khi điều tra, kiểm tra component có implement `ItemStream` và có được đăng ký trực tiếp hoặc qua `.stream(...)` hay không.

Không nên chỉ dựa vào việc class có method tên `open`, `update`, `close`. Nó phải implement đúng interface và được Step quản lý lifecycle.

## 13. Sử dụng AbstractItemCountingItemStreamItemReader

Spring Batch cung cấp `AbstractItemCountingItemStreamItemReader<T>` để giảm code cho custom reader có thể khôi phục bằng cách đếm item. Base class này quản lý item count và lưu/khôi phục count trong ExecutionContext; subclass tập trung vào cách mở nguồn, đọc item và định vị lại nguồn.

Một custom reader có thể theo mẫu:

```java
public class CustomOrderReader
        extends AbstractItemCountingItemStreamItemReader<Order> {

    private BufferedReader reader;

    public CustomOrderReader(Resource resource) {
        setName("customOrderReader");
        setSaveState(true);
        this.resource = resource;
    }

    @Override
    protected void doOpen() throws Exception {
        // Mở resource và chuẩn bị reader.
    }

    @Override
    protected Order doRead() throws Exception {
        // Đọc và trả về item kế tiếp; null khi EOF.
        return null;
    }

    @Override
    protected void doClose() throws Exception {
        // Đóng reader/resource.
    }

    @Override
    protected void jumpToItem(int itemIndex) throws Exception {
        // Định vị nguồn đến itemIndex khi restart.
    }
}
```

Đây là skeleton minh họa. Cần khai báo field `resource` và implement các method theo API của phiên bản Spring Batch trong dự án. Base class sẽ quản lý count/checkpoint; `jumpToItem(...)` phải thực sự đưa nguồn đọc đến vị trí tương ứng.

Base class này phù hợp khi nguồn có thể định vị bằng số item, ví dụ file dòng hoặc danh sách có thứ tự ổn định. Nếu nguồn dùng continuation token hoặc cursor phức tạp, triển khai `ItemStreamReader` trực tiếp có thể phù hợp hơn.

## 14. State trong memory và state đã commit

Component thường có hai dạng state:

- **In-memory state:** field đang thay đổi trong process khi đọc/ghi item.
- **Checkpoint state:** giá trị đã ghi vào `ExecutionContext` và được repository lưu bền vững.

Hai dạng này có thể khác nhau trong lúc một chunk đang xử lý. Ví dụ reader đã đọc đến item 250 trong bộ nhớ nhưng checkpoint cuối cùng chỉ đến item 200 vì chunk hiện tại chưa commit.

```text
Checkpoint đã commit: item 200
          |
          v
Reader tiếp tục đọc item 201..250
          |
          v
Writer lỗi, transaction rollback
          |
          v
Checkpoint bền vững vẫn là item 200
```

Khi restart sau process failure, reader phải dùng checkpoint đã commit, không dùng field trong memory của process cũ. Nếu component đọc từ nguồn không thể replay, cần transaction ở nguồn hoặc một cơ chế lưu offset/idempotency phù hợp.

Không tự ghi ExecutionContext ra một kho khác sau mỗi `read()` mà không phối hợp transaction với JobRepository. Làm như vậy có thể khiến offset tiến xa hơn dữ liệu đầu ra đã commit.

## 15. Rollback và ItemStream

`ItemStream.update()` được gọi ở checkpoint trước khi commit chunk. Khi transaction chunk rollback, metadata checkpoint được lưu cùng transaction/repository configuration thường được rollback về checkpoint trước đó.

Tuy nhiên, rollback database không tự tua ngược mọi resource bên ngoài. Một custom reader có thể đã tiêu thụ message từ queue, gọi API hoặc tiến cursor. Cần xác định reader có transactional hay không:

- Reader không transactional thường được Spring Batch buffer item đã đọc để replay trong cùng process khi rollback.
- Reader transactional như queue có thể trả item về nguồn khi transaction rollback; cần cấu hình reader/transaction đúng để tránh vừa buffer vừa nhận lại cùng item.
- Sau process restart, buffer memory mất và reader khôi phục từ checkpoint đã lưu.

Đối với nguồn ngoài transaction, thiết kế replay/idempotency hoặc lưu một checkpoint có thể tái tạo đúng item tiếp theo. Không giả định chỉ implement ItemStream là đủ để hoàn tác side effect của nguồn.

## 16. Restart cần cùng JobInstance và nguồn ổn định

Để khôi phục StepExecution đúng, Job cần được restart trong cùng JobInstance. Điều đó thường yêu cầu giữ nguyên các identifying JobParameters.

Ngoài JobParameters, nguồn dữ liệu cũng phải ổn định:

- File không bị ghi đè hoặc thay đổi thứ tự dòng.
- Query có `ORDER BY` xác định và tập dữ liệu không dịch chuyển ngoài ý muốn.
- API offset/token trỏ đến cùng snapshot hoặc cùng phiên bản dữ liệu.
- Reader name và ExecutionContext keys không thay đổi tùy tiện.
- Serializer của ExecutionContext có thể đọc state đã lưu từ phiên bản trước.

Ví dụ, reader lưu `lastProcessedId=500`. Nếu lần restart query không còn cùng thứ tự hoặc ID 500 không còn đại diện cho cùng ranh giới dữ liệu, reader có thể bỏ sót hoặc đọc trùng. Với nguồn biến động, dùng snapshot ID, watermark hoặc manifest để cố định tập dữ liệu.

Nếu thay đổi định dạng state qua một phiên bản deploy, cân nhắc thêm version key:

```java
context.putInt("customerReader.stateVersion", 2);
context.putLong("customerReader.nextOffset", nextOffset);
```

Trong `open()`, kiểm tra version và xử lý tương thích hoặc fail rõ ràng nếu state cũ không còn dùng được. Không diễn giải một key cũ theo format mới mà không có migration.

## 17. Xử lý exception trong lifecycle

Các method `ItemStream` khai báo `ItemStreamException`. Nên wrap lỗi I/O hoặc lỗi khôi phục state bằng exception này để Spring Batch nhận biết lỗi lifecycle:

```java
@Override
public void open(ExecutionContext context) throws ItemStreamException {
    try {
        openRemoteSession();
        nextOffset = context.getLong(NEXT_OFFSET_KEY, 0L);
    } catch (RuntimeException ex) {
        closeRemoteSessionQuietly();
        throw new ItemStreamException("Cannot open customer API reader", ex);
    }
}
```

Các nguyên tắc:

- Nếu `open()` thất bại sau khi đã mở một phần resource, cố gắng giải phóng resource đã mở.
- Không nuốt exception trong `update()`; nếu checkpoint không được ghi đúng, Step không nên tiếp tục như thể đã lưu thành công.
- `close()` nên giải phóng resource và xử lý trạng thái đóng lặp an toàn nếu lifecycle có thể gọi sau lỗi.
- Không ghi checkpoint mới trong `close()` thay cho `update()`.
- Exception message nên nêu component và resource cần thiết nhưng tránh lộ secret hoặc dữ liệu nhạy cảm.

## 18. Thread safety của ItemStream

`ItemStream` không tự làm component thread-safe. Nếu nhiều thread gọi `read()` hoặc `write()` trên cùng một instance, các field state như offset, iterator hoặc file position có thể bị cập nhật đồng thời.

Với multi-threaded Step, component được gắn với StepExecution có thể được nhiều worker thread dùng chung. Cần kiểm tra reader/writer có hỗ trợ concurrent access hay không.

Các hướng thiết kế:

- Ưu tiên state riêng theo partition bằng partitioned Step, mỗi partition có StepExecution và target bean riêng.
- Dùng component stateless hoặc state immutable khi có thể.
- Nếu phải chia sẻ mutable state, dùng cơ chế đồng bộ/atomic phù hợp và đảm bảo thứ tự nghiệp vụ.
- Không dùng một file cursor hoặc API offset duy nhất cho nhiều thread nếu nguồn không hỗ trợ concurrent partitioning.
- Không cho nhiều partition ghi cùng một key ExecutionContext hoặc cùng một file output mà không có phân vùng rõ ràng.

`@StepScope` tạo target instance theo StepExecution; nó không tự tạo một instance cho mỗi thread. Scope và thread safety là hai vấn đề khác nhau.

## 19. ItemStream và delegate/composite components

Một composite reader có thể phối hợp nhiều delegate reader. Nếu các delegate đều có state, composite cần quản lý lifecycle cho từng delegate hoặc Step phải đăng ký từng delegate stream.

Ví dụ:

```java
public class CustomerCompositeReader
        implements ItemStreamReader<Customer> {

    private final ItemStreamReader<Customer> first;
    private final ItemStreamReader<Customer> second;

    public CustomerCompositeReader(
            ItemStreamReader<Customer> first,
            ItemStreamReader<Customer> second) {
        this.first = first;
        this.second = second;
    }

    @Override
    public void open(ExecutionContext context) {
        first.open(context);
        second.open(context);
    }

    @Override
    public Customer read() throws Exception {
        Customer item = first.read();
        return item != null ? item : second.read();
    }

    @Override
    public void update(ExecutionContext context) {
        first.update(context);
        second.update(context);
    }

    @Override
    public void close() {
        first.close();
        second.close();
    }
}
```

Đây là ví dụ khái niệm; composite thực tế cần xử lý việc mở/đóng một phần khi delegate thất bại và tránh key trùng trong ExecutionContext. Nếu cả hai delegate dùng key giống nhau, state của chúng có thể ghi đè nhau. Mỗi delegate cần tên/key riêng.

Một lựa chọn khác là để composite chỉ đọc dữ liệu và đăng ký các delegate bằng `.stream(first).stream(second)` trong Step. Chọn một nơi chịu trách nhiệm lifecycle và tránh gọi `open/update/close` hai lần cho cùng một delegate.

## 20. Những nhầm lẫn thường gặp

**Cho rằng implement ItemStream tự động lưu mọi field.** Chỉ những giá trị được ghi vào ExecutionContext trong `update()` mới được lưu qua checkpoint.

**Lưu state trong close().** `close()` dành cho giải phóng resource; checkpoint phải được ghi trong `update()`.

**Lưu InputStream hoặc Connection vào ExecutionContext.** Handle đang mở không thể được khôi phục qua process restart. Chỉ lưu thông tin cần để mở lại và định vị resource.

**Quên đăng ký delegate stream.** Nếu stream bị ẩn trong wrapper, Step có thể không gọi lifecycle. Đăng ký bằng `.stream(...)` hoặc chuyển tiếp lifecycle từ composite.

**Dùng key chung cho nhiều component.** Các component có thể ghi đè state của nhau. Dùng key có namespace và tên ổn định.

**Cập nhật checkpoint sau mỗi read và coi đó là commit.** State trong memory có thể đi trước dữ liệu đã commit. Cập nhật ExecutionContext tại checkpoint do framework quản lý.

**Cho rằng rollback tự rewind mọi nguồn.** File, API và message source có hành vi khác nhau. Cần replay, transaction hoặc idempotency phù hợp.

**Cho rằng @StepScope làm stream thread-safe.** Một target bean có thể được nhiều thread trong cùng StepExecution dùng chung.

**Thay đổi key hoặc format state mà không tương thích.** Job đang dở có thể không đọc được checkpoint cũ. Giữ key ổn định hoặc version hóa state.

## 21. Kiểm thử ItemStream

Một bài kiểm thử restart cần xác nhận cả state được ghi và state được khôi phục bởi một instance mới.

Ví dụ kiểm thử reader theo offset ở mức đơn vị:

```java
@Test
void restoresOffsetFromExecutionContext() throws Exception {
    CustomerApiClient client = new FakeCustomerApiClient();
    CustomerApiItemReader reader = new CustomerApiItemReader(client);

    ExecutionContext firstContext = new ExecutionContext();
    reader.open(firstContext);

    reader.read();
    reader.read();
    reader.update(firstContext);
    reader.close();

    CustomerApiItemReader restartedReader = new CustomerApiItemReader(client);
    restartedReader.open(firstContext);

    Customer next = restartedReader.read();

    assertEquals(3L, next.getId());
    restartedReader.close();
}
```

Đây là test minh họa cho hợp đồng offset. Fake API phải trả dữ liệu ổn định theo offset và test cần điều chỉnh ID mẫu cho phù hợp.

Các trường hợp nên kiểm thử:

1. `open()` không có key: component bắt đầu ở vị trí đầu tiên.
2. `open()` có checkpoint: component khôi phục đúng vị trí.
3. `update()` ghi đúng state và không ghi object/resource không serialize được.
4. Tạo instance mới rồi mở với ExecutionContext cũ: đọc item kế tiếp, không đọc lại item đã commit.
5. `close()` giải phóng resource khi Step hoàn tất và khi có lỗi.
6. Hai component trong cùng Step dùng key khác nhau.
7. Delegate stream được đăng ký và lifecycle chỉ được gọi đúng số lần.
8. Rollback một chunk không làm checkpoint bền vững vượt dữ liệu đã commit.
9. Restart với input version khác được phát hiện hoặc xử lý theo chính sách.
10. Chạy partition/multi-thread để xác nhận state không bị chia sẻ sai.

Unit test với `ExecutionContext` giúp kiểm tra logic open/update. Integration test với JobRepository và transaction manager thực tế mới xác nhận checkpoint được lưu cùng chunk commit và được dùng lại khi restart Job.

## 22. Cách thiết kế component có state

Trước hết, xác định state nào cần sống qua một chunk, qua một StepExecution hay qua một JobExecution. Nếu chỉ là dữ liệu tạm trong một lần gọi, không cần đưa vào ExecutionContext. Nếu cần restart, triển khai `ItemStream` và lưu một checkpoint nhỏ, ổn định, có thể serialize.

Đặt `open()` để tạo resource và khôi phục state; đặt `update()` để ghi state tại commit boundary; đặt `close()` để giải phóng resource. Dùng key có namespace và giữ tên component ổn định. Đảm bảo Step nhận biết stream trực tiếp hoặc đăng ký delegate tường minh.

Khi triển khai reader, bảo đảm nguồn có thể được định vị lại từ checkpoint hoặc có cơ chế transaction/replay. Khi triển khai writer, bảo đảm side effect và checkpoint không lệch nhau sau rollback. Với processor, ưu tiên stateless và chỉ dùng ItemStream khi thực sự cần lifecycle/state riêng.

Kiểm thử bằng cách lưu ExecutionContext, tạo instance mới và xác nhận component tiếp tục đúng vị trí. Sau đó kiểm thử integration qua rollback và restart với JobRepository thật. `ItemStream` cung cấp nền tảng lifecycle và checkpoint; tính đúng đắn cuối cùng vẫn phụ thuộc vào cách component quản lý resource, transaction, nguồn dữ liệu và side effect của chính nó.

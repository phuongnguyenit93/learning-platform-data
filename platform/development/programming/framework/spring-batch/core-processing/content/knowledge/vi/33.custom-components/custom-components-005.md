# Save state bằng ExecutionContext

Trong Spring Batch, custom reader hoặc writer thường phải nhớ tiến độ giữa các chunk và khôi phục tiến độ đó khi job được restart. Ví dụ, reader cần biết record tiếp theo cần đọc, writer cần biết mốc dữ liệu đã ghi, hoặc một component cần nhớ file/partition hiện tại.

Số liệu runtime trong field Java không tồn tại sau khi process dừng. Spring Batch cung cấp `ExecutionContext` để lưu state của `StepExecution` hoặc `JobExecution`, cùng hợp đồng `ItemStream` để component mở resource, cập nhật checkpoint và đóng resource theo vòng đời step.

Khi được cấu hình đúng, framework lưu `ExecutionContext` thông qua `JobRepository` tại ranh giới checkpoint của chunk. Một execution mới của cùng `JobInstance` có thể đọc lại context đã lưu và tiếp tục công việc.

`ExecutionContext` chỉ là nơi lưu trạng thái có thể khôi phục. Nó không tự làm custom component restartable. Component phải tự định nghĩa state nào cần lưu, khôi phục state đó trong `open`, cập nhật nó trong `update`, và bảo đảm nguồn dữ liệu vẫn có cùng ý nghĩa khi restart.

## 1. Vì sao custom component cần lưu state?

Custom reader có thể đọc dữ liệu từ API, file, cursor database hoặc một nguồn nội bộ. Sau mỗi chunk, Spring Batch cần biết phần dữ liệu nào đã được commit để lần restart không bỏ sót hoặc xử lý lặp ngoài dự kiến.

Ví dụ job đọc 1.000 record, chunk size là 100:

```text
Chunk 1: đọc record 1..100    -> ghi thành công -> COMMIT
Chunk 2: đọc record 101..200  -> ghi thành công -> COMMIT
Chunk 3: đọc record 201..300  -> lỗi trước commit

Restart cùng JobInstance:
  khôi phục checkpoint đã commit ở record 200
  tiếp tục từ record 201
```

Nếu reader chỉ giữ `currentIndex` trong một field Java, giá trị đó mất khi JVM hoặc process dừng. `ExecutionContext` lưu biểu diễn bền vững của checkpoint để execution tiếp theo có thể khôi phục.

Những state thường cần lưu gồm:

- Vị trí đọc đã commit, chẳng hạn item index, page number hoặc last processed key.
- Tên file hiện tại và vị trí trong danh sách file.
- Watermark hoặc mốc thời gian đã xử lý.
- Token phân trang/cursor có thể serialize và dùng lại.
- Trạng thái nhỏ cần thiết để tiếp tục một writer hoặc custom tasklet.

Không phải mọi field trong component đều cần lưu. Chỉ lưu thông tin cần thiết để tái tạo trạng thái runtime sau restart.

## 2. ExecutionContext là gì?

`ExecutionContext` là một map key/value do Spring Batch quản lý. Nó cho phép component lưu các giá trị có thể serialize và khôi phục trong một execution sau đó.

Có hai phạm vi chính:

| Loại context | Phạm vi | Dùng khi |
|---|---|---|
| Step `ExecutionContext` | Một `StepExecution` | Lưu checkpoint riêng của reader, writer hoặc worker step |
| Job `ExecutionContext` | Một `JobExecution` | Lưu dữ liệu cần được chia sẻ giữa các step trong cùng job execution |

Reader và writer thường lưu checkpoint vào Step `ExecutionContext` được truyền vào `ItemStream.open` và `ItemStream.update`. Context này thuộc step đang chạy, nên mỗi worker/partition có thể có state riêng.

Job context thích hợp cho dữ liệu cần chuyển từ step này sang step khác. Không nên dùng job context làm nơi ghi state của từng item nếu dữ liệu đó chỉ thuộc một step hoặc một partition.

## 3. ItemStream là hợp đồng lifecycle

Một custom component cần tham gia checkpoint thường triển khai `ItemStream`. Interface có ba callback chính:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

Ý nghĩa:

| Callback | Khi nào được gọi | Trách nhiệm |
|---|---|---|
| `open` | Khi step mở component | Khởi tạo resource và khôi phục state từ context |
| `update` | Khi framework cập nhật checkpoint | Ghi state hiện tại vào context |
| `close` | Khi step đóng component | Giải phóng resource và state runtime |

Reader thường triển khai `ItemStreamReader<T>`; writer thường triển khai `ItemStreamWriter<T>`. Hai interface này kết hợp hợp đồng đọc/ghi với `ItemStream`.

```java
public interface ItemStreamReader<T>
        extends ItemReader<T>, ItemStream {
}

public interface ItemStreamWriter<T>
        extends ItemWriter<T>, ItemStream {
}
```

Một class chỉ triển khai `ItemReader<T>` hoặc `ItemWriter<T>` mà không tham gia `ItemStream` sẽ không tự cung cấp lifecycle checkpoint cho Spring Batch. Nếu custom component cần restart, hãy triển khai đúng interface stream hoặc đăng ký stream tương ứng với step.

## 4. Vòng đời open, update và close

Vòng đời khái quát của một custom reader trong chunk step:

```text
Step bắt đầu
    |
    v
reader.open(stepExecutionContext)
    |
    v
Đọc item và xử lý chunk
    |
    v
reader.update(stepExecutionContext)
    |
    v
JobRepository lưu checkpoint theo transaction phù hợp
    |
    +--> COMMIT: checkpoint được lưu
    |
    +--> ROLLBACK: checkpoint của chunk chưa commit không trở thành mốc restart
    |
    v
Lặp lại cho chunk tiếp theo
    |
    v
reader.close()
```

`open` phải hỗ trợ cả hai tình huống: context chưa có key state vì đây là lần chạy đầu, hoặc context đã có key vì đây là lần restart.

`update` nên ghi state hiện tại vào context một cách xác định. Framework có thể gọi callback này ở nhiều checkpoint; việc ghi cùng một giá trị vào cùng key không nên tạo side effect nghiệp vụ.

`close` dùng để đóng cursor, stream, socket hoặc resource runtime. Không dùng `close` làm nơi duy nhất lưu checkpoint, vì `close` cũng được gọi khi step kết thúc thất bại hoặc bị dừng.

## 5. Lưu key có namespace

Một `ExecutionContext` có thể chứa state của nhiều stream trong cùng step. Vì vậy, key cần ổn định và không đụng nhau.

Không nên dùng key quá chung như:

```java
executionContext.putInt("index", currentIndex);
```

Nếu hai custom reader cùng ghi key `index`, component này có thể ghi đè state của component kia.

Hãy đặt namespace theo tên component và ý nghĩa của state:

```java
executionContext.putInt(
    "orderReader.currentIndex",
    currentIndex
);
```

Có thể dùng `ItemStreamSupport` để lấy key theo tên bean/component. `ItemStreamSupport` cũng cung cấp cơ chế quản lý tên cho stream.

```java
public class IndexedOrderReader
        extends ItemStreamSupport
        implements ItemStreamReader<Order> {

    private static final String INDEX_KEY = "currentIndex";

    // ...
}
```

Đặt tên ổn định trong constructor:

```java
public IndexedOrderReader(List<Order> orders) {
    this.orders = List.copyOf(orders);
    setName("indexedOrderReader");
}
```

Khi dùng `getExecutionContextKey(INDEX_KEY)`, key được tạo từ tên stream và suffix state. Nhờ đó nhiều stream có thể dùng cùng suffix như `currentIndex` mà không ghi đè nhau.

Không đặt tên theo timestamp, UUID ngẫu nhiên hoặc giá trị thay đổi giữa các lần restart. Nếu tên thay đổi, component có thể không tìm được key checkpoint cũ.

## 6. Ví dụ custom reader lưu vị trí đọc

Ví dụ sau minh họa một reader đọc từ danh sách bất biến. Mục tiêu là thể hiện cách một custom component lưu và khôi phục chỉ số item; trong production, nguồn dữ liệu lớn nên được đọc theo cursor, page hoặc keyset thay vì nạp toàn bộ vào `List`.

```java
public class IndexedOrderReader
        extends ItemStreamSupport
        implements ItemStreamReader<Order> {

    private static final String INDEX_KEY = "currentIndex";

    private final List<Order> orders;
    private int currentIndex;

    public IndexedOrderReader(List<Order> orders) {
        this.orders = List.copyOf(orders);
        setName("indexedOrderReader");
    }

    @Override
    public void open(ExecutionContext executionContext) {
        String key = getExecutionContextKey(INDEX_KEY);

        if (executionContext.containsKey(key)) {
            currentIndex = executionContext.getInt(key);
        } else {
            currentIndex = 0;
        }
    }

    @Override
    public Order read() {
        if (currentIndex >= orders.size()) {
            return null;
        }

        return orders.get(currentIndex++);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putInt(
            getExecutionContextKey(INDEX_KEY),
            currentIndex
        );
    }

    @Override
    public void close() {
        // Không còn resource ngoài cần đóng trong ví dụ này.
    }
}
```

Cách hoạt động:

1. Lần đầu, `open` không tìm thấy key nên đặt `currentIndex = 0`.
2. Mỗi lần `read` trả về một order, index tăng lên.
3. Khi framework cập nhật checkpoint, `update` ghi index vào Step `ExecutionContext`.
4. Khi restart cùng JobInstance, `open` đọc lại index đã lưu và tiếp tục từ vị trí tương ứng.

Reader ví dụ giữ toàn bộ dữ liệu trong memory để minh họa. Với database, API hoặc file lớn, state thường nên là last key, page token, file position hoặc cursor marker có thể tái tạo.

## 7. Dùng AbstractItemCountingItemStreamItemReader

Spring Batch có lớp cơ sở `AbstractItemCountingItemStreamItemReader<T>` dành cho custom reader có thể khôi phục bằng số lượng item đã đọc. Lớp này quản lý bộ đếm và state phổ biến, giúp giảm phần code phải tự viết.

Custom reader kế thừa lớp này thường triển khai:

- `doOpen()` để mở nguồn dữ liệu.
- `doRead()` để đọc item tiếp theo.
- `doClose()` để đóng nguồn.
- `jumpToItem(int itemIndex)` để đưa nguồn đến vị trí cần khôi phục khi restart.

Ví dụ khung triển khai:

```java
public class CustomOrderReader
        extends AbstractItemCountingItemStreamItemReader<Order> {

    private final OrderSource source;

    public CustomOrderReader(OrderSource source) {
        this.source = source;
        setName("customOrderReader");
    }

    @Override
    protected void doOpen() throws Exception {
        source.open();
    }

    @Override
    protected Order doRead() throws Exception {
        return source.readNext();
    }

    @Override
    protected void doClose() throws Exception {
        source.close();
    }

    @Override
    protected void jumpToItem(int itemIndex) throws Exception {
        source.skip(itemIndex);
    }
}
```

`source.skip(itemIndex)` chỉ là minh họa. Với database, việc nhảy đến item có thể phải dùng query có thứ tự ổn định hoặc keyset pagination; với file, có thể cần đọc bỏ qua các record trước đó. Cần triển khai sao cho vị trí được khôi phục tương ứng với thứ tự item của lần chạy ban đầu.

Nếu nguồn có cơ chế checkpoint riêng tốt hơn item count, ví dụ API continuation token hoặc database last ID, có thể triển khai `ItemStream` trực tiếp để lưu token/key đó thay vì cố quy đổi thành index.

## 8. Checkpoint theo item count hay business key?

Không phải nguồn nào cũng nên lưu số thứ tự item.

| Kiểu nguồn | State có thể lưu | Lưu ý |
|---|---|---|
| Danh sách cố định | Index item | Danh sách và thứ tự phải không đổi |
| File tuần tự | Record count hoặc vị trí được reader hỗ trợ | File phải bất biến giữa lần chạy và restart |
| Database | Last processed primary key hoặc page marker | Query phải có thứ tự xác định |
| API phân trang | Continuation token/page cursor | Token phải còn hiệu lực khi restart |
| Partitioned data | Partition key và checkpoint riêng | Mỗi worker cần namespace/context riêng |

Với database, lưu last processed ID thường bền vững hơn offset nếu dữ liệu được sắp xếp theo khóa duy nhất:

```sql
SELECT ORDER_ID, CUSTOMER_ID, TOTAL
FROM ORDERS
WHERE ORDER_ID > ?
ORDER BY ORDER_ID
FETCH FIRST 500 ROWS ONLY
```

Ở checkpoint, lưu ID cuối đã commit. Khi restart, query tiếp tục với `ORDER_ID > lastId`.

Cú pháp giới hạn số dòng tùy database. Quan trọng là thứ tự phải xác định và khóa dùng làm checkpoint phải duy nhất hoặc có tie-breaker ổn định.

## 9. Cập nhật ExecutionContext trong update

`update` là nơi custom stream ghi state cần khôi phục. Ví dụ với last processed key:

```java
@Override
public void update(ExecutionContext executionContext) {
    if (lastCommittedOrderId != null) {
        executionContext.putLong(
            getExecutionContextKey("lastOrderId"),
            lastCommittedOrderId
        );
    }
}
```

Khi mở lại:

```java
@Override
public void open(ExecutionContext executionContext) {
    String key = getExecutionContextKey("lastOrderId");

    if (executionContext.containsKey(key)) {
        lastCommittedOrderId = executionContext.getLong(key);
    } else {
        lastCommittedOrderId = null;
    }

    source.openAfter(lastCommittedOrderId);
}
```

Tên biến `lastCommittedOrderId` nhấn mạnh checkpoint phải đại diện cho dữ liệu đã được commit. Đừng lưu mốc đã đọc trước khi chunk hoàn tất rồi coi nó là mốc đã xử lý thành công.

Nếu reader đọc trước nhiều item để lấp chunk, trạng thái runtime có thể tiến xa hơn checkpoint đã commit. `update` và cơ chế chunk của Spring Batch phải phối hợp để chỉ lưu mốc phù hợp với transaction. Custom reader cần được kiểm thử với rollback/retry thực tế, không chỉ với lần chạy thành công.

## 10. Checkpoint phải gắn với commit boundary

Spring Batch xử lý chunk trong transaction. Khi chunk commit, state của `ItemStream` được cập nhật và lưu cùng metadata theo cấu hình transaction/repository. Khi chunk rollback, checkpoint của chunk chưa commit không được dùng làm mốc restart đã hoàn tất.

Ví dụ:

```text
Checkpoint đã commit: orderId = 200
Chunk kế tiếp:
  đọc 201
  đọc 202
  đọc 203
  writer lỗi
  transaction rollback

Restart:
  mở context với lastOrderId = 200
  đọc lại từ sau orderId 200
```

Nếu checkpoint tiến đến 203 dù chunk chứa 201–203 chưa commit, lần restart có thể bỏ qua dữ liệu chưa được ghi. Đây là lỗi nghiêm trọng: checkpoint đã đi trước dữ liệu nghiệp vụ.

Ngược lại, nếu dữ liệu đã commit nhưng checkpoint không được lưu đồng bộ, item có thể được đọc lại. Vì vậy, writer nên có unique constraint, upsert hoặc idempotency phù hợp để chống ghi trùng.

## 11. JobRepository lưu ExecutionContext

`ExecutionContext` được Spring Batch lưu thông qua `JobRepository`. Với JDBC JobRepository, state được lưu trong metadata của step/job execution và được khôi phục khi execution mới bắt đầu.

Trong thiết kế chuẩn:

- Step context giữ checkpoint riêng của step.
- Job context giữ dữ liệu chia sẻ giữa các step trong cùng JobExecution.
- JobRepository lưu metadata và context để hỗ trợ restart.
- Transaction configuration quyết định mối quan hệ commit giữa metadata và dữ liệu nghiệp vụ.

Không dùng một `HashMap` static hoặc field singleton để thay thế `ExecutionContext`. Những giá trị trong memory không bền vững qua process restart và có thể bị trộn giữa các execution đồng thời.

Nếu JobRepository và database nghiệp vụ dùng hai datasource/transaction manager khác nhau, không mặc định rằng checkpoint và dữ liệu nghiệp vụ được commit nguyên tử. Cần đánh giá trường hợp một bên commit còn bên kia thất bại và thiết kế idempotency/đối soát phù hợp.

## 12. Step ExecutionContext và Job ExecutionContext

Reader/writer thông thường nhận Step `ExecutionContext` trong `open` và `update`. Đây là nơi thích hợp cho state chỉ có ý nghĩa trong step đó.

Ví dụ:

```java
executionContext.putLong("orderReader.lastOrderId", 9001L);
```

Nếu một step tạo dữ liệu cần step sau sử dụng, có thể lưu tạm trong Step context rồi promote một số key lên Job context bằng cơ chế như `ExecutionContextPromotionListener`.

Job context không nên được dùng làm vùng ghi chung không kiểm soát cho các worker chạy song song. Nếu nhiều step/partition cùng cập nhật key, có thể có race condition hoặc ghi đè. Dùng key riêng, dữ liệu bất biến hoặc một kho lưu trữ có cơ chế đồng bộ.

## 13. Giá trị nào nên lưu?

ExecutionContext cần chứa state nhỏ, có thể serialize và đủ để tái tạo tiến độ.

Nên lưu:

- `String`, `Long`, `Integer`, `Boolean` và kiểu scalar phù hợp.
- Last processed ID hoặc watermark.
- Page number hoặc continuation token.
- File name/version và record count cần để khôi phục.
- Mã phiên bản schema state nếu cần hỗ trợ nâng cấp.

Không nên lưu:

- JDBC `Connection`, `ResultSet`, `PreparedStatement`.
- File handle, `InputStream`, socket hoặc parser đang mở.
- Spring bean, service hoặc object runtime không serialize được.
- Collection lớn chứa toàn bộ item đã đọc.
- Payload nhạy cảm không cần thiết.
- Một object phức tạp phụ thuộc class version khó tương thích qua deployment.

Tài nguyên runtime phải được mở lại trong `open`; không serialize chính resource đang mở vào context.

## 14. Serialization và tương thích state

ExecutionContext cần được serialize để lưu vào repository. Vì vậy, kiểu dữ liệu được đưa vào context phải tương thích với serializer đang cấu hình.

Cách an toàn thường là lưu giá trị đơn giản:

```java
executionContext.putString("orderReader.sourceVersion", sourceVersion);
executionContext.putLong("orderReader.lastId", lastId);
executionContext.putInt("orderReader.page", pageNumber);
```

Nếu lưu custom object, object đó phải tương thích với serializer và phiên bản class khi job được restart. Một deployment mới có thể đọc context được ghi bởi deployment cũ; thay đổi class hoặc package có thể làm quá trình deserialize thất bại.

Đối với checkpoint, scalar và token có format rõ ràng thường dễ duy trì hơn object Java phức tạp.

## 15. Version hóa key và state schema

Tên key là một phần của hợp đồng restart. Khi đổi key hoặc thay đổi ý nghĩa của giá trị, execution cũ có thể không khôi phục được đúng state.

Có thể đặt key có version:

```java
private static final String LAST_ID_KEY = "orderReader.v1.lastId";
```

Nếu cấu trúc state cần thay đổi, hãy có chiến lược tương thích:

- Đọc key cũ khi key mới chưa tồn tại.
- Chuyển đổi giá trị cũ sang biểu diễn mới nếu có thể.
- Giữ reader cũ cho các JobInstance đang restart nếu migration quá phức tạp.
- Không âm thầm coi checkpoint không hiểu được là lần chạy mới từ đầu.

Ví dụ fallback có chủ đích:

```java
@Override
public void open(ExecutionContext context) {
    String newKey = getExecutionContextKey("v2.lastId");
    String oldKey = getExecutionContextKey("v1.lastId");

    if (context.containsKey(newKey)) {
        lastId = context.getLong(newKey);
    } else if (context.containsKey(oldKey)) {
        lastId = context.getLong(oldKey);
    } else {
        lastId = 0L;
    }
}
```

Ví dụ này chỉ phù hợp khi `v1.lastId` và `v2.lastId` có cùng semantics. Nếu ý nghĩa khác nhau, cần migration rõ ràng hoặc từ chối restart với thông báo có thể điều tra.

## 16. Lưu state cho custom writer

Writer cũng có thể triển khai `ItemStream` nếu cần khôi phục trạng thái như file hiện tại, record count, last written key hoặc mốc output.

Ví dụ writer JDBC ghi dữ liệu và lưu last ID đã ghi:

```java
public class CheckpointingOrderWriter
        extends ItemStreamSupport
        implements ItemStreamWriter<Order> {

    private static final String LAST_ID_KEY = "lastOrderId";

    private final JdbcTemplate jdbcTemplate;
    private Long lastOrderId;

    public CheckpointingOrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
        setName("checkpointingOrderWriter");
    }

    @Override
    public void open(ExecutionContext context) {
        String key = getExecutionContextKey(LAST_ID_KEY);
        lastOrderId = context.containsKey(key)
            ? context.getLong(key)
            : null;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            jdbcTemplate.update(
                "INSERT INTO PROCESSED_ORDERS (ORDER_ID, TOTAL) VALUES (?, ?)",
                order.id(),
                order.total()
            );
            lastOrderId = order.id();
        }
    }

    @Override
    public void update(ExecutionContext context) {
        if (lastOrderId != null) {
            context.putLong(
                getExecutionContextKey(LAST_ID_KEY),
                lastOrderId
            );
        }
    }

    @Override
    public void close() {
        // JdbcTemplate không giữ resource mở ở đây.
    }
}
```

Ví dụ giả định các lệnh insert và cập nhật JobRepository được phối hợp transaction theo cấu hình ứng dụng. Nếu dữ liệu nghiệp vụ và metadata không cùng transaction boundary, không được coi hai checkpoint là atomic.

Trong thực tế, writer thường không cần lưu last ID nếu database đã có khóa duy nhất và việc ghi có thể lặp an toàn. Hãy lưu state writer chỉ khi nó thực sự cần để khôi phục output.

## 17. File writer và checkpoint

Custom writer ghi file cần xử lý cẩn thận hơn writer JDBC vì filesystem không tự tham gia transaction JDBC.

State file có thể bao gồm:

- Resource/file ID bất biến.
- Vị trí ghi hoặc record count đã commit.
- Tên file tạm đang sử dụng.
- Trạng thái header đã ghi.
- Version của output format.

Tuy nhiên, chỉ lưu byte offset vào `ExecutionContext` không đủ để bảo đảm file và JobRepository commit nguyên tử. Process có thể dừng giữa lúc flush file và lưu metadata hoặc ngược lại.

Với output quan trọng, nên cân nhắc:

1. Ghi file vào tên tạm duy nhất cho JobInstance.
2. Dùng writer có hỗ trợ restart và transaction-aware behavior phù hợp.
3. Xác minh nội dung/record count sau khi step hoàn tất.
4. Dùng step cuối để publish/rename file khi job đạt điều kiện thành công.
5. Giữ file tạm hoặc manifest để điều tra nếu job thất bại.

Không dùng `close()` làm dấu hiệu file đã được publish thành công. `close()` chỉ là lifecycle cleanup; publish nên là một bước nghiệp vụ riêng.

## 18. Đăng ký ItemStream trong step

Spring Batch cần biết component nào phải nhận callback `open`, `update` và `close`.

Khi custom reader/writer được truyền trực tiếp vào step và kiểu component triển khai `ItemStreamReader` hoặc `ItemStreamWriter`, framework có thể đăng ký stream lifecycle cùng step.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemStreamReader<Order> orderReader,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrders", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderWriter)
        .build();
}
```

Khai báo kiểu trả về bean đủ cụ thể cũng giúp infrastructure nhận diện interface stream. Nếu method `@Bean` chỉ khai báo một interface quá tổng quát, một số metadata về lifecycle có thể không được nhìn thấy như mong muốn.

## 19. Delegate và composite component

Một wrapper hoặc composite có thể chứa nhiều reader/writer delegate. Nếu wrapper không chuyển tiếp `ItemStream` lifecycle đến delegate, Spring Batch có thể chỉ gọi lifecycle trên wrapper và bỏ qua state của delegate.

Ví dụ, step dùng một composite writer nhưng file writer bên trong cần lưu checkpoint. Nếu composite không forward `open`, `update`, `close`, hãy đăng ký delegate stream với step:

```java
return new StepBuilder("exportOrders", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .writer(compositeWriter)
    .stream(fileDelegateWriter)
    .build();
```

Chỉ đăng ký delegate riêng khi wrapper không tự quản lý/forward stream lifecycle. Nếu delegate đã được wrapper đăng ký và forward, đăng ký lặp có thể làm lifecycle callback bị gọi hai lần.

Với custom composite, có thể tự triển khai `ItemStreamWriter` và chuyển tiếp ba callback tới các delegate stream. Hãy bảo đảm mỗi delegate được mở, cập nhật và đóng đúng một lần.

## 20. Scoped bean và state theo execution

Custom reader thường cần `@StepScope` nếu nó nhận JobParameters hoặc state riêng theo StepExecution.

```java
@Bean
@StepScope
ItemStreamReader<Order> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        OrderSourceFactory sourceFactory) {

    OrderSource source = sourceFactory.open(inputFile);
    return new CustomOrderReader(source);
}
```

Scoped target được tạo cho StepExecution hiện tại. Điều đó giúp mỗi execution có reader state riêng. Proxy không thay thế `ItemStream`; reader vẫn phải triển khai stream lifecycle nếu cần checkpoint.

Với partitioning, mỗi worker StepExecution có thể nhận context riêng và custom reader cần lưu state bằng key trong context của worker đó. Không dùng static field hoặc singleton mutable để giữ index dùng chung cho các partition.

## 21. Rollback và state trong memory

Một điểm quan trọng khi tự triển khai reader: `ExecutionContext` checkpoint được quản lý theo transaction, nhưng field Java như `currentIndex` không tự rollback cùng JDBC transaction.

Ví dụ reader đã tăng index khi đọc item, sau đó writer ném exception. Transaction có thể rollback, nhưng biến `currentIndex` trong object vẫn đã tăng. Spring Batch có cơ chế buffering/recovery cho chunk, nhưng custom reader phải tương thích với cách step retry, skip và rollback hoạt động.

Do đó:

- Không tự coi field runtime là checkpoint đã commit.
- Chỉ ghi checkpoint trong `update` theo lifecycle của framework.
- Đảm bảo `open` có thể khôi phục từ checkpoint bền vững.
- Kiểm thử trường hợp writer lỗi giữa chunk, retry, skip và restart.
- Với reader phức tạp, cân nhắc kế thừa base class Spring Batch có hỗ trợ item counting/restart thay vì tự viết toàn bộ cơ chế.

Nếu custom reader cần tiếp tục ngay trong cùng execution sau rollback, hãy hiểu cách reader buffering và fault-tolerance của step tương tác với nguồn dữ liệu. Có thể cần cơ chế reset/reposition phù hợp với nguồn, không chỉ khôi phục ở lần restart process.

## 22. Nguồn dữ liệu phải ổn định

Checkpoint chỉ có ý nghĩa khi state được áp dụng trên cùng một nguồn dữ liệu và cùng thứ tự logic.

Ví dụ reader lưu `lastOrderId = 500`. Nếu trước khi restart, dữ liệu nguồn bị xóa, cập nhật hoặc thay đổi thứ tự, query tiếp theo có thể trả về một tập item khác với lần chạy ban đầu.

Các biện pháp:

- Dùng input snapshot hoặc file bất biến.
- Chọn khóa thứ tự ổn định và duy nhất.
- Lưu source ID/version/checksum nếu cần xác nhận input.
- Dùng watermark hoặc thời điểm snapshot cho dữ liệu thay đổi liên tục.
- Giữ manifest cố định nếu một step đọc nhiều resource.

Không lưu offset/index rồi giả định nguồn có thể thay đổi tùy ý mà vẫn restart đúng.

## 23. Step restart và reader checkpoint là hai cơ chế khác nhau

Spring Batch dùng metadata để quyết định step nào cần chạy lại. `ExecutionContext` của reader quyết định reader tiếp tục từ đâu khi step được khởi động lại.

| Cơ chế | Câu hỏi được trả lời |
|---|---|
| JobInstance/JobExecution metadata | Đây có phải cùng một lần xử lý nghiệp vụ không? |
| StepExecution status | Step đã hoàn tất, thất bại hay bị dừng? |
| Step `ExecutionContext` | Reader/writer cần khôi phục state nào? |
| Job `ExecutionContext` | Dữ liệu nào cần chia sẻ giữa các step? |

Muốn restart cùng JobInstance, giữ nguyên identifying JobParameters. Nếu thêm identifying parameter mới, Spring Batch tạo JobInstance khác và không dùng checkpoint của instance cũ.

`ExecutionContext` không tự cho phép restart một job đã hoàn tất hoặc một step bị cấu hình không restart. Restart policy và metadata vẫn được áp dụng.

## 24. Không lưu state quá lớn

ExecutionContext được lưu trong JobRepository và có chi phí serialize/ghi metadata. Không nên đưa hàng chục nghìn item, toàn bộ file content hoặc một object graph lớn vào context.

Thay vì lưu danh sách item đã đọc:

```java
// Không nên lưu toàn bộ dữ liệu đã xử lý vào ExecutionContext
executionContext.put("processedOrders", processedOrders);
```

Hãy lưu một checkpoint nhỏ:

```java
executionContext.putLong("orderReader.lastOrderId", lastOrderId);
```

Khi restart, query lại dữ liệu sau checkpoint. Nếu nguồn không hỗ trợ truy vấn lại, hãy cân nhắc staging hoặc lưu state trong một bảng chuyên dụng thay vì phình to metadata context.

## 25. ExecutionContext và dữ liệu nhạy cảm

JobRepository có thể lưu context trong database metadata. Không ghi credential, access token, thông tin thanh toán hoặc payload nhạy cảm vào context nếu không cần thiết.

Nếu component cần credential để mở resource, hãy lấy từ secret/configuration provider tại runtime và chỉ lưu một reference/version không nhạy cảm trong context nếu cần xác định đúng cấu hình restart.

Không log toàn bộ ExecutionContext trong production. Log key cần thiết hoặc mã correlation đã được làm sạch.

## 26. Kiểm thử custom component có restart

Unit test cho `open`, `read`, `update` có thể kiểm tra logic key, nhưng integration test với Spring Batch mới chứng minh checkpoint được lưu và khôi phục đúng qua JobRepository.

Các trường hợp nên kiểm tra:

1. Lần đầu context rỗng: reader bắt đầu từ đầu.
2. Context có key: `open` khôi phục đúng item index/last key.
3. `update` ghi state vào đúng key có namespace.
4. Hai stream cùng suffix nhưng khác name không ghi đè state.
5. Chunk commit: checkpoint được lưu.
6. Chunk rollback: checkpoint chưa commit không trở thành mốc restart.
7. Restart cùng JobInstance: reader tiếp tục sau checkpoint gần nhất.
8. Thay identifying JobParameters: job tạo instance mới.
9. Source version thay đổi: job phát hiện hoặc từ chối restart không an toàn.
10. Delegate trong composite: lifecycle callback được gọi đúng số lần.
11. Nhiều partition: mỗi worker có state riêng.
12. State value có thể serialize và deserialize qua JobRepository.

Ví dụ kiểm tra logic context trực tiếp:

```java
@Test
void restoresReaderPositionFromExecutionContext() throws Exception {
    IndexedOrderReader reader = new IndexedOrderReader(orders);

    ExecutionContext context = new ExecutionContext();
    context.putInt("indexedOrderReader.currentIndex", 2);

    reader.open(context);

    assertThat(reader.read().id()).isEqualTo(orders.get(2).id());

    reader.close();
}
```

Tên key trong test cần khớp với quy tắc `getExecutionContextKey` của stream. Integration test nên dùng reader bean thật và JobRepository để xác nhận lifecycle tự động được Spring Batch gọi.

## 27. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ giữ index trong field Java | Mất tiến độ khi process restart | Lưu state qua `ItemStream.update` |
| Không khôi phục trong `open` | Restart bắt đầu sai vị trí | Đọc key từ `ExecutionContext` |
| Không triển khai `ItemStream` | Framework không biết lifecycle checkpoint | Dùng `ItemStreamReader`/`ItemStreamWriter` |
| Dùng key chung như `index` | Các stream ghi đè state nhau | Namespace theo tên component |
| Đổi tên stream giữa các lần chạy | Không tìm thấy checkpoint cũ | Giữ tên ổn định |
| Lưu object runtime không serialize được | Không thể lưu/đọc context | Chỉ lưu scalar/token nhỏ |
| Lưu checkpoint trước commit | Restart có thể bỏ sót dữ liệu chưa commit | Cập nhật state tại lifecycle checkpoint |
| Không kiểm thử rollback | Field runtime có thể lệch với checkpoint | Test rollback, retry, skip và restart |
| Wrapper không forward ItemStream | Delegate không được open/update/close | Forward lifecycle hoặc đăng ký `.stream(delegate)` |
| Dùng Job context cho state riêng của worker | State có thể bị chia sẻ/ghi đè | Dùng Step context riêng |
| Thay đổi nguồn dữ liệu giữa restart | Checkpoint trỏ sang dữ liệu khác | Snapshot/version input |
| Lưu toàn bộ item vào context | Metadata lớn và tốn chi phí serialize | Lưu last key/page token và query lại |

## 28. Quy trình thiết kế state cho custom component

Khi xây dựng reader, writer hoặc tasklet có thể restart, hãy thực hiện theo thứ tự:

1. Xác định chính xác state runtime nào cần khôi phục sau restart.
2. Chọn Step `ExecutionContext` hay Job `ExecutionContext` theo phạm vi dữ liệu.
3. Chọn biểu diễn checkpoint nhỏ và ổn định: item index, last key, page token hoặc file marker.
4. Triển khai `ItemStream` với `open`, `update` và `close`.
5. Đặt tên stream ổn định và namespace cho từng key.
6. Đăng ký component/delegate với step để lifecycle được gọi.
7. Bảo đảm state có thể serialize và tương thích qua deployment.
8. Giữ input ổn định hoặc lưu source version để kiểm tra khi restart.
9. Phối hợp checkpoint với transaction/commit boundary và idempotency của writer.
10. Integration test cả success, rollback, retry, skip, restart và concurrency.

## Kết luận

`ExecutionContext` là nơi Spring Batch lưu state có thể khôi phục của step hoặc job. Custom reader/writer tham gia cơ chế này bằng `ItemStream`: `open` khôi phục state, `update` ghi checkpoint và `close` giải phóng resource. Spring Batch lưu context thông qua `JobRepository` theo lifecycle checkpoint của step.

Hãy dùng Step context cho state riêng của component/worker, đặt key có namespace và tên stream ổn định, chỉ lưu dữ liệu nhỏ có thể serialize, và bảo đảm checkpoint phản ánh dữ liệu đã commit. Đăng ký đúng stream, kiểm tra delegate trong composite, giữ nguồn dữ liệu ổn định và kiểm thử rollback/restart thực tế. `ExecutionContext` không tự làm custom component restartable; component phải định nghĩa và thực hiện đầy đủ quy tắc khôi phục state.

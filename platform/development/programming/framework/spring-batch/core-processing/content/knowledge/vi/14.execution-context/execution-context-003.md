# Key ổn định cho reader state

Trong Spring Batch, reader có thể lưu tiến độ đọc vào Step `ExecutionContext` để tiếp tục đúng vị trí khi Job được restart. Mỗi giá trị được lưu dưới dạng một cặp key/value. **Key của reader state cần ổn định qua các lần chạy và triển khai ứng dụng**, vì reader dùng chính key đó để tìm lại checkpoint đã lưu.

Nếu tên reader hoặc key bị đổi, code mới có thể không đọc được checkpoint cũ. Reader có thể tưởng đây là lần chạy đầu tiên và bắt đầu lại từ đầu, dẫn đến đọc trùng hoặc xử lý sai dữ liệu. Nếu nhiều stream component ghi vào cùng một key, trạng thái của component này có thể ghi đè trạng thái của component khác.

Thiết kế key ổn định cần quan tâm đến phạm vi `ExecutionContext`, tên reader, namespace của từng component, kiểu dữ liệu, khả năng tương thích khi nâng cấp và cách xử lý các execution đang dở.

## 1. Reader state được lưu trong ExecutionContext

Một reader restartable thường triển khai `ItemStream` hoặc `ItemStreamReader`. Trong vòng đời Step, Spring Batch gọi các callback:

| Callback | Vai trò |
|---|---|
| `open(ExecutionContext)` | Nhận context đã lưu và khôi phục vị trí đọc |
| `update(ExecutionContext)` | Ghi trạng thái hiện tại của reader vào context |
| `close()` | Đóng stream và giải phóng tài nguyên |

Ví dụ, reader lưu vị trí hiện tại:

```java
private static final String CURRENT_INDEX_KEY = "ordersReader.currentIndex";

@Override
public void open(ExecutionContext context) {
    currentIndex = context.getInt(CURRENT_INDEX_KEY, 0);
}

@Override
public void update(ExecutionContext context) {
    context.putInt(CURRENT_INDEX_KEY, currentIndex);
}
```

Khi Step được restart, `open()` đọc lại giá trị đã lưu. Nếu key chưa tồn tại, reader bắt đầu từ vị trí mặc định. Nếu key đã tồn tại, reader tiếp tục từ checkpoint tương ứng.

Key không chỉ là tên biến trong code. Nó là một phần của metadata được lưu trong `JobRepository`, thường tồn tại lâu hơn object Java và có thể được đọc bởi phiên bản ứng dụng được triển khai sau này. Vì vậy, thay đổi key cần được xem như thay đổi định dạng dữ liệu checkpoint.

## 2. Phạm vi của key: Step ExecutionContext và Job ExecutionContext

Spring Batch có ExecutionContext ở phạm vi JobExecution và StepExecution. Reader state thường thuộc Step context vì vị trí đọc gắn với một lần thực thi Step cụ thể.

```text
JobExecution
  |
  +-- Job ExecutionContext
  |      +-- report.outputLocation
  |
  +-- StepExecution: importOrdersStep
  |      +-- Step ExecutionContext
  |             +-- ordersReader.currentIndex
  |             +-- ordersReader.resourceIndex
  |
  +-- StepExecution: importCustomersStep
         +-- Step ExecutionContext
                +-- customersReader.currentIndex
```

Hai StepExecution có ExecutionContext riêng, nên cùng một key có thể xuất hiện trong hai context khác nhau mà không xung đột. Tuy nhiên, trong cùng một StepExecution, các stream component cần tránh dùng trùng key.

Không nên lưu vị trí đọc của một reader vào Job context chỉ vì muốn các Step khác nhìn thấy nó. Checkpoint của reader thuộc về vòng đời Step và nên được lưu trong Step ExecutionContext. Job context phù hợp với dữ liệu cần chia sẻ giữa các Step, không phải namespace chung cho mọi reader.

## 3. Đặt key theo namespace ổn định

Key nên mô tả component và ý nghĩa giá trị. Một quy ước đơn giản:

```text
<reader-name>.<state-name>
```

Ví dụ:

```text
ordersFileReader.currentLine
ordersFileReader.resourceIndex
ordersPagingReader.lastOrderId
customerReader.currentPage
```

Tên reader giúp nhận diện nguồn tạo ra state; phần suffix mô tả checkpoint cụ thể. Nếu tự viết reader, có thể khai báo key thành constant:

```java
public class OrdersReader implements ItemStreamReader<Order> {

    private static final String CURRENT_LINE_KEY =
            "ordersFileReader.currentLine";
    private static final String RESOURCE_INDEX_KEY =
            "ordersFileReader.resourceIndex";

    // Các field và phương thức reader khác.
}
```

Không nên dùng key quá chung như `index`, `count`, `position` hoặc `state` khi một Step có nhiều component. Các tên chung dễ xung đột và khó hiểu khi điều tra metadata.

Namespace nên ổn định qua các phiên bản ứng dụng. Tránh tạo key dựa trên giá trị thay đổi mỗi lần chạy như timestamp, UUID ngẫu nhiên hoặc `JobExecutionId`, vì reader sẽ không tìm thấy checkpoint cũ khi restart.

## 4. Tên reader của component tích hợp sẵn cũng cần ổn định

Nhiều reader tích hợp sẵn của Spring Batch dùng tên được cấu hình để tạo namespace cho các key nội bộ trong ExecutionContext. Vì vậy, builder thường yêu cầu `.name(...)` khi bật save state.

Ví dụ với `FlatFileItemReader`:

```java
@Bean
public FlatFileItemReader<Order> ordersFileReader(
        @Value("${batch.orders-file}") Resource resource) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("ordersFileReader")
            .resource(resource)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

Tên `ordersFileReader` phải giữ ổn định giữa lần chạy đầu và lần restart. Nếu đổi thành `orderFileReaderV2`, implementation có thể tạo key khác và không tìm thấy checkpoint được lưu dưới tên cũ.

Tương tự với database paging reader:

```java
@Bean
public JdbcPagingItemReader<Order> ordersPagingReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        RowMapper<Order> rowMapper) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("ordersPagingReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .rowMapper(rowMapper)
            .pageSize(200)
            .saveState(true)
            .build();
}
```

Ngoài tên reader, query và sort key cũng phải giữ ngữ nghĩa tương thích. Key ổn định nhưng query thay đổi khiến thứ tự dữ liệu khác đi vẫn có thể làm checkpoint trỏ đến vị trí không còn đúng.

## 5. Dùng tên ổn định với ItemStreamSupport

Nếu custom reader kế thừa `ItemStreamSupport`, có thể đặt tên component bằng `setName()` và dùng namespace đó khi tạo key:

```java
public class OrdersItemReader extends AbstractItemCountingItemStreamItemReader<Order> {

    public OrdersItemReader() {
        setName("ordersItemReader");
    }

    @Override
    protected Order doRead() {
        // Đọc item kế tiếp từ nguồn dữ liệu.
        return readNextOrder();
    }

    @Override
    protected void doOpen() {
        // Mở nguồn dữ liệu.
    }

    @Override
    protected void doClose() {
        // Đóng nguồn dữ liệu.
    }
}
```

Các class hỗ trợ như `AbstractItemCountingItemStreamItemReader` quản lý bộ đếm và state theo quy ước của framework. Tên component được dùng để phân biệt key của reader. Hãy giữ tên này ổn định và không tái sử dụng cùng một tên cho các reader độc lập trong cùng phạm vi Step context.

Nếu tự triển khai `ItemStream` mà không dùng class hỗ trợ, cần tự khai báo key rõ ràng và đảm bảo chúng không đụng với key của component khác.

## 6. Key phải ổn định cả về tên lẫn ý nghĩa

Giữ nguyên chuỗi key là chưa đủ. Ý nghĩa và kiểu dữ liệu của giá trị cũng phải tương thích.

Ví dụ, phiên bản đầu lưu:

```java
context.putInt("ordersReader.position", 1200);
```

Phiên bản sau đổi cách hiểu `position` từ số dòng thành byte offset. Chuỗi key không đổi, nhưng cùng giá trị `1200` mang ý nghĩa khác. Reader mới có thể khôi phục sai vị trí.

Khi thiết kế state, cần ghi nhớ:

- Key mô tả rõ đơn vị và ý nghĩa, ví dụ `currentLineNumber`, `lastCommittedOrderId` hoặc `resourceIndex`.
- Kiểu dữ liệu cần ổn định, ví dụ `Long` cho ID lớn thay vì `Integer`.
- Giá trị mặc định phải có ý nghĩa cho lần chạy đầu và không làm reader bỏ qua dữ liệu.
- Không lưu object phức tạp nếu chỉ cần một ID, offset hoặc chỉ số nhỏ.
- Không lưu tài nguyên runtime như `InputStream`, `ResultSet`, connection hoặc thread.
- Nếu cấu trúc state thay đổi, có kế hoạch đọc dữ liệu cũ hoặc chuyển đổi checkpoint.

Đặt tên có đơn vị cũng giúp tránh việc code mới hiểu nhầm giá trị cũ. Ví dụ, `byteOffset` rõ ràng hơn `position` nếu reader thực sự lưu offset theo byte.

## 7. Tránh collision giữa các reader và delegate

Một Step có thể có nhiều stream component: reader chính, reader delegate, writer có state hoặc listener triển khai ItemStream. Nếu hai component cùng ghi một key, component ghi sau có thể ghi đè giá trị của component trước.

Ví dụ không tốt:

```java
// Reader A
context.putLong("position", currentOrderId);

// Reader B
context.putLong("position", currentCustomerId);
```

Sau khi lưu, context chỉ có một giá trị `position`; không thể phân biệt nó thuộc reader nào.

Sử dụng namespace riêng:

```java
// Reader A
context.putLong("ordersReader.lastOrderId", currentOrderId);

// Reader B
context.putLong("customersReader.lastCustomerId", currentCustomerId);
```

Với composite reader hoặc multi-resource reader, hãy kiểm tra cả component ngoài và delegate. Nếu delegate triển khai `ItemStream`, cần đăng ký delegate với Step khi framework không tự quản lý nó qua wrapper:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(compositeReader)
        .writer(orderWriter)
        .stream(fileDelegateReader)
        .build();
```

Nếu delegate không nhận được callback `open()` và `update()`, state của nó sẽ không được khôi phục hoặc lưu dù key đã được đặt đúng. Tên key ổn định và đăng ký stream đúng là hai yêu cầu khác nhau, đều cần thiết.

## 8. Key ổn định qua restart và deployment

ExecutionContext thường được lưu trong database cùng metadata của JobRepository. Vì vậy, một execution có thể được tạo bởi phiên bản ứng dụng cũ và được restart bởi phiên bản mới. Nếu phiên bản mới thay đổi tên reader, key, kiểu dữ liệu hoặc ngữ nghĩa checkpoint, nó có thể không đọc được metadata cũ.

Ví dụ:

```text
Phiên bản 1
  reader name: ordersReader
  key: ordersReader.currentLine
  value: 5000 (dòng tiếp theo cần đọc)
       |
       v
  Job bị dừng, checkpoint lưu trong repository
       |
       v
Phiên bản 2 được triển khai
  reader name: orderInputReader
  key mới: orderInputReader.offset
       |
       v
  Reader mới không tìm thấy key cũ
```

Nếu reader mới mặc định về vị trí đầu, dữ liệu đã xử lý có thể bị đọc lại. Nếu nó hiểu sai kiểu hoặc ý nghĩa của giá trị cũ, dữ liệu có thể bị bỏ qua.

### Chiến lược thay đổi key

Khi cần đổi tên hoặc cấu trúc checkpoint, có thể chọn một trong các cách:

1. **Giữ tương thích:** tiếp tục dùng key cũ nếu ngữ nghĩa không thay đổi.
2. **Đọc cả key cũ và mới:** khi mở context, ưu tiên key mới; nếu chưa có thì đọc key cũ, chuyển đổi giá trị rồi ghi theo schema mới.
3. **Migration có kiểm soát:** chuyển đổi metadata của các execution đang dở bằng một công cụ migration đã được kiểm thử và có backup.
4. **Hoàn tất execution cũ trước deployment:** nếu không thể hỗ trợ checkpoint cũ, dừng nhận Job mới, để các Job cũ hoàn tất hoặc xử lý chúng theo quy trình vận hành đã xác định.

Không nên âm thầm đổi key và hy vọng mọi Job đang dở sẽ tự bắt đầu lại an toàn. Quyết định restart từ đầu hay tiếp tục cần dựa trên quy tắc nghiệp vụ và khả năng chống xử lý trùng của writer.

## 9. Version hóa checkpoint khi cấu trúc state thay đổi

Với reader tự viết có nhiều trường state, có thể lưu thêm một version để nhận diện định dạng checkpoint:

```java
private static final String STATE_VERSION_KEY = "ordersReader.stateVersion";
private static final String LAST_ID_KEY = "ordersReader.lastCommittedId";
private static final int CURRENT_STATE_VERSION = 2;

@Override
public void open(ExecutionContext context) {
    int version = context.getInt(STATE_VERSION_KEY, 1);

    if (version == 1) {
        // Chuyển giá trị cũ sang định dạng hiện tại nếu cần.
        long oldPosition = context.getLong("ordersReader.position", 0L);
        lastCommittedId = convertLegacyPosition(oldPosition);
    } else if (version == CURRENT_STATE_VERSION) {
        lastCommittedId = context.getLong(LAST_ID_KEY, 0L);
    } else {
        throw new IllegalStateException(
                "Unsupported reader state version: " + version
        );
    }
}

@Override
public void update(ExecutionContext context) {
    context.putLong(LAST_ID_KEY, lastCommittedId);
    context.putInt(STATE_VERSION_KEY, CURRENT_STATE_VERSION);
}
```

Đây là minh họa cho migration logic; `convertLegacyPosition()` phải được xác định theo ý nghĩa thật của checkpoint cũ. Không thể chuyển đổi an toàn nếu thiếu thông tin để ánh xạ vị trí cũ sang dữ liệu mới.

Nếu có nhiều version được hỗ trợ, hãy giới hạn rõ khoảng version, ghi log khi chuyển đổi và xóa key cũ chỉ sau khi đã bảo đảm state mới được ghi thành công. Không nên version hóa quá phức tạp nếu state chỉ có một số key đơn giản và không có yêu cầu giữ execution qua nhiều phiên bản.

## 10. Key ổn định không thay thế nguồn dữ liệu ổn định

Reader có thể khôi phục đúng key nhưng vẫn đọc sai dữ liệu nếu nguồn đầu vào thay đổi.

Ví dụ, `FlatFileItemReader` lưu dòng hiện tại. Nếu file bị thay thế hoặc chèn thêm dòng trước vị trí checkpoint, cùng dòng số 5000 có thể là một bản ghi khác. Với `JdbcPagingItemReader`, nếu query sort theo cột không duy nhất hoặc dữ liệu thay đổi trong lúc restart, vị trí trang có thể không còn trỏ đến cùng tập bản ghi.

Để restart đáng tin cậy:

- Giữ nguyên file đầu vào hoặc xác thực checksum/version của file trước khi resume.
- Dùng sort key duy nhất, ổn định cho database paging.
- Cân nhắc snapshot hoặc watermark nếu dữ liệu nguồn thay đổi liên tục.
- Lưu khóa nghiệp vụ hoặc ID cuối cùng đã commit thay vì chỉ lưu vị trí mơ hồ.
- Kiểm tra rằng query và điều kiện lọc vẫn tương thích với checkpoint cũ.

Key xác định nơi lưu trạng thái; giá trị và nguồn dữ liệu quyết định trạng thái đó có còn đúng hay không.

## 11. saveState và tên reader

Với reader tích hợp sẵn, `saveState(true)` cho phép lưu trạng thái restart vào ExecutionContext. Khi bật tính năng này, hãy đặt tên reader rõ ràng và ổn định:

```java
return new FlatFileItemReaderBuilder<Order>()
        .name("ordersFileReader")
        .resource(resource)
        .delimited()
        .names("orderId", "amount")
        .targetType(Order.class)
        .saveState(true)
        .build();
```

Nếu đặt `saveState(false)`, reader không lưu checkpoint riêng. Khi đó, việc giữ tên ổn định không giúp khôi phục vị trí đọc của reader đó, và ứng dụng cần chấp nhận đọc lại từ đầu hoặc có cơ chế khác.

Không nên đổi tên reader chỉ để phản ánh tên class mới hoặc cách đặt tên code mới nếu vẫn cần restart các execution cũ. Tên reader là một phần của định danh state, không chỉ là nhãn hiển thị.

## 12. Kiểm tra key khi điều tra lỗi restart

Khi một reader bất ngờ bắt đầu từ đầu hoặc đọc trùng dữ liệu, hãy xem metadata của StepExecution trước và sau khi restart:

- StepExecution cũ có `ExecutionContext` chứa key mong đợi không?
- Tên reader trong phiên bản mới có còn giống tên đã tạo checkpoint không?
- Key có thay đổi chữ hoa/thường, prefix hoặc suffix không?
- Kiểu dữ liệu và ý nghĩa của value có thay đổi không?
- Reader có được đăng ký như `ItemStream` để `open()`/`update()` được gọi không?
- `saveState` có bật không?
- Nguồn dữ liệu, sort order, file version hoặc query có thay đổi không?
- Step có đang restart đúng JobInstance với identifying JobParameters cũ không?

Trong log, có thể ghi reader name, state version và checkpoint ID/offset đã khôi phục. Tránh log toàn bộ ExecutionContext nếu có thể chứa dữ liệu nhạy cảm hoặc object không cần thiết.

Không nên sửa trực tiếp các bản ghi metadata trong JobRepository để ép reader về một vị trí khác nếu chưa hiểu quan hệ giữa StepExecution, transaction và dữ liệu nghiệp vụ. Dùng API vận hành hoặc quy trình migration được kiểm soát.

## 13. Những nhầm lẫn thường gặp

**Đổi tên reader mà không nghĩ đến execution cũ.** Tên có thể được dùng làm prefix cho các key nội bộ. Đổi tên có thể khiến reader không tìm thấy checkpoint cũ.

**Dùng key chung như `position` cho nhiều component.** Các stream có thể ghi đè state của nhau. Hãy dùng namespace riêng cho từng reader/delegate.

**Chỉ giữ key mà thay đổi ý nghĩa value.** Cùng một key nhưng đổi đơn vị từ dòng sang byte offset vẫn có thể làm reader khôi phục sai vị trí.

**Dùng timestamp hoặc UUID ngẫu nhiên trong key.** Key mới mỗi lần chạy sẽ không trỏ đến checkpoint cũ. Chỉ dùng thành phần động khi nó thực sự là định danh ổn định của một resource trong cùng execution.

**Cho rằng key ổn định đủ để restart chính xác.** File, query hoặc thứ tự dữ liệu thay đổi vẫn có thể làm checkpoint sai.

**Quên đăng ký delegate ItemStream.** Component có key đúng nhưng không nhận callback lưu/khôi phục thì state không được duy trì.

**Lưu object lớn vào ExecutionContext.** Context là metadata checkpoint. Nên lưu các giá trị nhỏ, có thể serialize và có định dạng ổn định.

## 14. Quy tắc thiết kế key cho reader state

Hãy chọn một tên reader ổn định, đặt key có namespace và mô tả đúng ý nghĩa, giữ kiểu dữ liệu cùng đơn vị qua các phiên bản, và chỉ lưu state cần thiết để khôi phục. Với reader tích hợp sẵn, đặt `.name(...)` rõ ràng và bật `.saveState(true)` khi cần restart. Với reader tự viết, khai báo key thành constant, dùng prefix riêng, triển khai `ItemStream` và đăng ký đầy đủ với Step.

Trước khi đổi tên hoặc schema key, hãy xác định có JobExecution nào đang dở cần restart hay không. Nếu có, giữ tương thích hoặc triển khai migration có kiểm soát. Kết hợp key ổn định với nguồn dữ liệu ổn định, checkpoint đúng ranh giới commit và JobRepository được duy trì sẽ giúp reader khôi phục đúng tiến độ qua các lần restart và deployment.

# Processor trả null để filter item

Trong chunk-oriented processing của Spring Batch, `ItemProcessor<I, O>` nhận từng item do reader cung cấp và quyết định item đó sẽ trở thành output như thế nào. Processor có thể trả về một object đã được chuyển đổi, hoặc trả về `null` để loại item khỏi luồng xử lý. Cách trả về `null` được gọi là filtering.

Khi một item bị filter, Spring Batch không chuyển item đó tới `ItemWriter`. Item vẫn được tính là đã đọc, nhưng không đóng góp vào số item được ghi. Đây là cách phù hợp khi bản ghi hợp lệ về cấu trúc nhưng không thuộc phạm vi kết quả cần tạo, chẳng hạn đơn hàng đã hủy trong job chỉ xuất đơn hàng đang hoạt động.

Filtering khác với việc ném exception để skip một item. `null` biểu thị quyết định nghiệp vụ có chủ đích rằng item không cần output; exception biểu thị quá trình xử lý gặp lỗi và cần được xử lý theo retry/skip policy hoặc làm step thất bại.

## Hợp đồng của ItemProcessor

`ItemProcessor<I, O>` có một phương thức `process` nhận input kiểu `I` và trả về output kiểu `O`:

```java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

Có ba kết quả chính:

| Kết quả của `process()` | Ý nghĩa | Điều xảy ra tiếp theo |
| --- | --- | --- |
| Trả về object `O` | Item được chấp nhận và chuyển đổi | Output được đưa vào chunk để writer ghi |
| Trả về `null` | Item bị filter có chủ đích | Item bị loại khỏi output, writer không nhận item đó |
| Ném exception | Xử lý item gặp lỗi | Spring Batch áp dụng retry/skip policy nếu step được cấu hình; nếu không xử lý được, step thất bại |

Ví dụ đơn giản:

```java
ItemProcessor<OrderInput, Order> processor = input -> {
    if ("CANCELLED".equalsIgnoreCase(input.status())) {
        return null;
    }

    return new Order(
            input.orderId(),
            input.customerId(),
            input.amount(),
            input.status());
};
```

Trong ví dụ, đơn hàng có trạng thái `CANCELLED` bị loại khỏi output. Các đơn hàng khác được chuyển thành `Order` và tiếp tục tới writer. Không cần ném exception hoặc cấu hình skip chỉ để bỏ một item hợp lệ theo điều kiện nghiệp vụ này.

## Spring Batch xử lý item bị filter như thế nào?

Trong một chunk, Spring Batch đọc các item từ `ItemReader`, gọi processor cho từng item rồi tập hợp các output khác `null` để chuyển tới writer.

```text
ItemReader
   |
   +--> Order A --> ItemProcessor --> Order A' --+
   |                                             |
   +--> Order B --> ItemProcessor --> null       |  bị filter
   |                                             |
   +--> Order C --> ItemProcessor --> Order C' --+
                                                 |
                                                 v
                                         ItemWriter
                                         [A', C']
```

Giả sử chunk size là 3 và reader trả về ba item. Nếu processor trả về output cho hai item và `null` cho item còn lại, writer chỉ nhận hai output. Chunk vẫn được xử lý theo ranh giới transaction của step; filtering không tự tạo một chunk riêng và cũng không làm thay đổi định nghĩa identifying parameters của job.

Nếu tất cả item trong một chunk đều bị filter, không có output để ghi. Spring Batch không chuyển các item đó tới writer; phần cập nhật metadata và transaction vẫn tuân theo lifecycle của step.

### Ví dụ với đơn hàng

Giả sử job chỉ xuất các đơn hàng có trạng thái `NEW` hoặc `PAID`. Các trạng thái `CANCELLED` và `DRAFT` là hợp lệ trong dữ liệu nguồn nhưng không thuộc kết quả cần xuất.

```java
public class ExportableOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        String status = input.status();

        if (!"NEW".equalsIgnoreCase(status)
                && !"PAID".equalsIgnoreCase(status)) {
            return null;
        }

        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException("Order amount must be positive");
        }

        return new Order(
                input.orderId().trim(),
                input.customerId().trim(),
                input.amount(),
                status.toUpperCase(Locale.ROOT));
    }
}
```

Ở đây có hai quyết định khác nhau:

- Trạng thái không thuộc tập được xuất: filter bằng cách trả về `null`.
- Đơn hàng thuộc tập cần xuất nhưng có số tiền không hợp lệ: ném exception nghiệp vụ.

Phân biệt rõ hai trường hợp giúp thống kê filtering và skip phản ánh đúng bản chất dữ liệu.

## Filtering không giống skip

Đây là điểm quan trọng khi thiết kế processor và theo dõi kết quả step.

**Filtering** là quyết định có chủ đích của processor. Processor trả về `null`, Spring Batch bỏ output của item và tăng `filterCount` trong `StepExecution`. Không có exception nên skip policy không được gọi cho quyết định filtering đó.

**Skipping** xảy ra khi một thao tác đọc, xử lý hoặc ghi ném exception thuộc loại được cấu hình skip. Spring Batch ghi nhận lỗi vào bộ đếm skip tương ứng, ví dụ `processSkipCount` nếu exception phát sinh trong processor. Skip thường dùng cho bản ghi lỗi mà nghiệp vụ cho phép bỏ qua sau khi ghi nhận lỗi.

| Tiêu chí | Filtering (`return null`) | Skipping (exception + skip policy) |
| --- | --- | --- |
| Ý nghĩa | Item hợp lệ nhưng không cần output | Item gặp lỗi được phép bỏ qua |
| Cách biểu diễn | Processor trả về `null` | Processor/reader/writer ném exception |
| Skip limit | Không tiêu thụ skip limit | Có thể tiêu thụ skip limit |
| Bộ đếm | `filterCount` | `readSkipCount`, `processSkipCount` hoặc `writeSkipCount` tùy tầng |
| Ghi nhận lỗi | Không tự tạo skip record | Có thể ghi nhận qua `SkipListener` |
| Ví dụ | Không xuất đơn hàng đã hủy | Dữ liệu ngày tháng sai định dạng và được phép skip |

Không nên trả về `null` cho dữ liệu sai chỉ để job tiếp tục. Làm như vậy khiến bản ghi biến mất khỏi output mà không được tính là lỗi skip, gây khó khăn cho kiểm toán và đối soát.

### Ví dụ skip cho dữ liệu không hợp lệ

Nếu một đơn hàng có mã bắt buộc nhưng bị thiếu, ứng dụng có thể ném `InvalidOrderException` và cấu hình skip nếu nghiệp vụ cho phép tiếp tục:

```java
return new StepBuilder("exportOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
```

Trong ví dụ, tối đa 50 exception thuộc loại được chỉ định có thể được skip theo chính sách của step. Những lỗi vượt giới hạn hoặc không thuộc loại được cho phép có thể làm step thất bại. Filtering vẫn được biểu diễn riêng bằng `return null` và không làm tăng skip count.

## Phân biệt null của processor với null của reader

Hai trường hợp này có ý nghĩa hoàn toàn khác nhau:

- `ItemReader.read()` trả về `null`: nguồn dữ liệu đã hết, step không còn item để đọc.
- `ItemProcessor.process(item)` trả về `null`: chỉ item hiện tại bị filter, reader vẫn tiếp tục cung cấp các item tiếp theo.

Ví dụ reader có 1.000 đơn hàng. Nếu processor filter 200 đơn, job vẫn tiếp tục xử lý 800 đơn còn lại. Processor trả `null` không kết thúc job và không báo EOF cho reader.

Reader không nên trả về `null` để biểu thị một bản ghi không hợp lệ hoặc không muốn xử lý. Theo hợp đồng reader, `null` báo kết thúc input. Nếu reader trả `null` giữa nguồn dữ liệu, Spring Batch có thể xem dữ liệu đã kết thúc và không đọc các bản ghi phía sau.

## Filter ở Reader hay ở Processor?

Không phải điều kiện lọc nào cũng nên đặt trong processor. Vị trí lọc phụ thuộc vào nguồn dữ liệu và ý nghĩa nghiệp vụ.

| Tình huống | Vị trí phù hợp thường gặp | Lý do |
| --- | --- | --- |
| Chỉ đọc đơn hàng có trạng thái `NEW` từ database | Điều kiện `WHERE` trong reader/query | Database loại dữ liệu sớm, giảm I/O và số item phải đọc |
| Cần đọc tất cả trạng thái để thống kê số bản ghi bị loại | Reader đọc toàn bộ, processor filter | Giữ được số liệu đầu vào và `filterCount` |
| Điều kiện lọc cần tính toán từ nhiều trường sau khi ánh xạ | Processor | Quy tắc nằm trên mô hình input đã chuẩn hóa |
| Điều kiện phụ thuộc logic nghiệp vụ dùng chung cho nhiều nguồn | Processor | Tách logic khỏi cách truy xuất nguồn |
| Loại dữ liệu không thuộc phạm vi truy vấn ngay từ đầu | Reader | Không cần đưa item không liên quan vào pipeline |

Lọc ở database có thể hiệu quả hơn vì giảm lượng dữ liệu truyền qua mạng và xử lý trong JVM. Tuy nhiên, nếu cần báo cáo số item đã bị loại theo quy tắc processor, lọc sớm ở query sẽ khiến những item đó không xuất hiện trong `readCount` hoặc `filterCount` của step.

Một nguyên tắc hữu ích: điều kiện xác định tập dữ liệu cần đọc có thể đặt ở reader; điều kiện quyết định một item đã đọc có được chuyển thành output hay không thường đặt ở processor.

## Filtering trong CompositeItemProcessor

Spring Batch cung cấp `CompositeItemProcessor` để ghép nhiều processor. Các delegate được gọi lần lượt; output của processor trước trở thành input của processor sau. Nếu một delegate trả về `null`, chuỗi xử lý dừng cho item đó và item bị filter. Những delegate phía sau không nhận item này.

```text
OrderInput
    |
    v
NormalizeProcessor
    |
    v
ValidateProcessor
    |
    v
FilterCancelledProcessor
    |
    +---- null -----------------> item bị filter
    |
    v
MapToOrderProcessor
    |
    v
Order output
```

Ví dụ:

```java
public class FilterCancelledProcessor
        implements ItemProcessor<NormalizedOrder, NormalizedOrder> {

    @Override
    public NormalizedOrder process(NormalizedOrder order) {
        if (order.status() == OrderStatus.CANCELLED) {
            return null;
        }
        return order;
    }
}
```

Nếu `FilterCancelledProcessor` trả về `null`, processor ánh xạ cuối cùng không được gọi cho item đó. Điều này giúp tránh thực hiện transformation hoặc truy cập dữ liệu không cần thiết cho bản ghi đã bị loại.

Khi sắp xếp processor chain, nên đặt những bước chuẩn hóa cần thiết trước điều kiện lọc, rồi đặt các bước làm giàu hoặc chuyển đổi tốn chi phí sau điều kiện lọc nếu chúng không cần chạy cho item bị loại. Tuy nhiên, validation bắt buộc để xác định dữ liệu hợp lệ phải được thực hiện trước khi dùng giá trị đó làm căn cứ lọc.

## Theo dõi số lượng item bị filter

`StepExecution` cung cấp các bộ đếm để theo dõi kết quả xử lý. Trong đó:

- `readCount`: số item reader đã đọc.
- `writeCount`: số item writer đã ghi thành công theo metadata step.
- `filterCount`: số item processor đã filter bằng cách trả về `null`.
- `readSkipCount`, `processSkipCount`, `writeSkipCount`: số item bị skip ở từng giai đoạn do exception và skip policy.

Ví dụ, step đọc 1.000 item, filter 120 item và ghi 880 item thành công có thể có các số liệu:

| Bộ đếm | Giá trị minh họa |
| --- | ---: |
| `readCount` | 1.000 |
| `filterCount` | 120 |
| `writeCount` | 880 |
| `processSkipCount` | 0 |

Nếu có thêm 5 item bị skip do lỗi processor, `processSkipCount` phản ánh nhóm lỗi đó riêng với 120 item bị filter. Các bộ đếm có thể có quan hệ khác nhau khi xảy ra retry, rollback hoặc skip ở reader/writer; cần đọc chúng cùng trạng thái execution và log của step.

Có thể đọc số liệu trong `StepExecutionListener`:

```java
public class FilterStatisticsListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        long read = stepExecution.getReadCount();
        long written = stepExecution.getWriteCount();
        long filtered = stepExecution.getFilterCount();

        System.out.printf(
                "Read=%d, written=%d, filtered=%d%n",
                read, written, filtered);

        return stepExecution.getExitStatus();
    }
}
```

Listener trên minh họa cách đọc bộ đếm sau khi step kết thúc. Trong production, nên ghi các số liệu này vào logging/metrics có cấu trúc và gắn với job name, job execution ID, step name cùng business date để dễ truy vết.

`filterCount` chỉ cho biết có bao nhiêu item bị loại. Nó không tự lưu lý do cụ thể hoặc nội dung item. Nếu cần biết vì sao từng bản ghi bị filter, phải thiết kế thêm cơ chế ghi nhận phù hợp.

## Khi cần lưu lý do filter hoặc dữ liệu bị loại

`ItemProcessor` chỉ trả về output hoặc `null`. Khi trả `null`, thông tin item và lý do filter không tự được chuyển tới writer. Nếu yêu cầu nghiệp vụ cần lưu các bản ghi bị loại vào file reject, bảng audit hoặc báo cáo, không nên chỉ dùng `null` rồi kỳ vọng writer có thể lấy lại item đó.

Một cách thiết kế là tạo kiểu kết quả thể hiện quyết định xử lý:

```java
public record OrderDecision(
        Order acceptedOrder,
        OrderInput originalInput,
        String decision,
        String reason) {

    public boolean accepted() {
        return acceptedOrder != null;
    }
}
```

Processor luôn trả về `OrderDecision`, kể cả khi bản ghi bị loại:

```java
public class OrderDecisionProcessor
        implements ItemProcessor<OrderInput, OrderDecision> {

    @Override
    public OrderDecision process(OrderInput input) {
        if ("CANCELLED".equalsIgnoreCase(input.status())) {
            return new OrderDecision(
                    null, input, "FILTERED", "Order is cancelled");
        }

        Order order = new Order(
                input.orderId(),
                input.customerId(),
                input.amount(),
                input.status());

        return new OrderDecision(order, input, "ACCEPTED", null);
    }
}
```

Writer sau đó có thể định tuyến `ACCEPTED` tới writer chính và `FILTERED` tới audit/reject writer. Với cách này, các quyết định filter được biểu diễn như output bình thường nên `filterCount` của Spring Batch không tự tăng cho các trường hợp đó. Nếu cần thống kê riêng, ứng dụng phải ghi nhận số lượng accepted/filtered trong writer hoặc một cơ chế thống kê phù hợp với transaction.

Một lựa chọn khác là tách thành các step hoặc luồng xử lý riêng nếu yêu cầu lưu bản ghi loại bỏ phức tạp. Cần tránh ghi side effect trực tiếp từ processor nếu transaction rollback hoặc retry có thể khiến audit bị ghi trùng. Hãy phối hợp audit với transaction của step hoặc dùng idempotency key.

## Filter và skip listener

`SkipListener` được gọi khi item bị skip do exception theo skip policy. Nó không phải listener dành cho item bị filter bằng `return null`.

Nếu cần lưu các item bị skip, có thể dùng `SkipListener` để nhận item và exception tương ứng. Nếu cần lưu item bị filter, cần dùng một thiết kế riêng như `OrderDecision` ở trên hoặc một cơ chế theo dõi có chủ đích. Không nên kỳ vọng `onSkipInProcess` được gọi khi processor trả về `null`, vì đó không phải lỗi skip.

Việc tách hai loại sự kiện giúp báo cáo vận hành rõ ràng:

| Sự kiện | Nguồn thông tin | Nơi ghi nhận phù hợp |
| --- | --- | --- |
| Item bị filter | Processor trả `null` | `filterCount`, metrics hoặc output quyết định riêng |
| Item bị skip | Exception được skip policy chấp nhận | Skip counters và `SkipListener` |
| Item xử lý thành công | Processor trả output và writer ghi thành công | `writeCount` cùng dữ liệu đích |

## Filtering và transaction, retry, restart

Filtering là quyết định của processor trong một lần xử lý item. Nó vẫn nằm trong luồng chunk và chịu ảnh hưởng của transaction/retry/restart ở cấp chunk.

Một số lưu ý:

- Processor nên có kết quả xác định: cùng input và cùng dữ liệu tham chiếu trong phạm vi job nên dẫn đến cùng quyết định filter.
- Tránh gọi API hoặc ghi audit không idempotent trong processor, vì processor có thể được gọi lại khi retry hoặc chunk rollback.
- Nếu điều kiện filter phụ thuộc vào ngày nghiệp vụ, trạng thái cấu hình hoặc phiên bản quy tắc, hãy truyền thông tin đó qua `JobParameters` hoặc cấu hình bất biến cho lần chạy.
- Khi restart, giữ nguyên identifying parameters để tiếp tục cùng `JobInstance`.
- Không dùng filter để che giấu lỗi hạ tầng hoặc dữ liệu sai cần được xử lý theo skip/retry policy.

Ví dụ, job xuất dữ liệu theo ngày chỉ nhận các đơn hàng có `createdDate` nằm trong kỳ. Ngày bắt đầu và kết thúc nên được xác định từ `JobParameters`; nếu dùng `LocalDate.now()` trong processor, restart vào ngày khác có thể tạo ra quyết định filter khác lần chạy đầu.

Nếu processor filter item trước khi writer chạy, writer không cần xử lý item đó. Tuy nhiên, nếu processor đã gọi hệ thống ngoài hoặc ghi log/audit có side effect, những tác động đó không nhất thiết được rollback cùng chunk. Hãy giữ processor thuần transformation khi có thể.

## Kiểm thử processor có filtering

Processor có thể kiểm thử độc lập bằng unit test. Nên kiểm tra cả trường hợp được giữ lại, trường hợp bị filter và trường hợp dữ liệu lỗi.

```java
class ExportableOrderProcessorTest {

    private final ExportableOrderProcessor processor =
            new ExportableOrderProcessor();

    @Test
    void filtersCancelledOrder() throws Exception {
        OrderInput input = new OrderInput(
                "O-1002", "C-02", new BigDecimal("89.00"), "CANCELLED");

        assertNull(processor.process(input));
    }

    @Test
    void keepsNewOrder() throws Exception {
        OrderInput input = new OrderInput(
                "O-1001", "C-01", new BigDecimal("125.50"), "NEW");

        Order result = processor.process(input);

        assertNotNull(result);
        assertEquals("O-1001", result.getOrderId());
        assertEquals("NEW", result.getStatus());
    }

    @Test
    void rejectsInvalidAmount() {
        OrderInput input = new OrderInput(
                "O-1003", "C-03", BigDecimal.ZERO, "NEW");

        assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));
    }
}
```

Ngoài unit test processor, integration test của step nên xác nhận:

- Item bị filter không xuất hiện trong bảng/file đích.
- `filterCount` tăng theo số item processor trả `null`.
- `writeCount` chỉ phản ánh các item writer thực sự ghi thành công.
- Skip counters chỉ tăng khi exception được skip policy chấp nhận.
- Khi tất cả item bị filter, step vẫn có thể hoàn thành với 0 item được ghi.
- Khi chunk rollback hoặc job restart, không phát sinh audit hoặc side effect trùng lặp.

## Các lỗi thường gặp

### Trả null vì dữ liệu không hợp lệ

Điều này khiến item bị tính là filtered thay vì skipped. Nếu dữ liệu không hợp lệ cần được ghi nhận như lỗi, hãy ném exception nghiệp vụ và cấu hình skip policy/SkipListener phù hợp.

### Nghĩ rằng trả null sẽ kết thúc step

`null` từ processor chỉ loại item hiện tại. Reader vẫn tiếp tục đọc các item tiếp theo. Chỉ `null` từ `ItemReader.read()` mới biểu thị hết input.

### Mong writer nhận được item đã filter

Writer chỉ nhận các output khác `null`. Nếu cần lưu item bị loại, hãy trả về một decision/result object và định tuyến bằng writer hoặc dùng một luồng audit riêng.

### Dùng SkipListener để bắt filtering

Filtering không phải exception skip, vì vậy `SkipListener` không nhận sự kiện đó. Hãy dùng `filterCount` để đếm hoặc thiết kế output riêng để lưu lý do.

### Filter ở processor dù database có thể lọc sớm

Đọc tất cả dữ liệu rồi loại phần lớn trong processor có thể tốn I/O và CPU. Nếu điều kiện lọc có thể biểu diễn chính xác ở truy vấn nguồn và không cần thống kê những item bị loại trong step, hãy cân nhắc lọc ngay tại reader.

### Processor có side effect trước khi trả null

Nếu processor gửi message, gọi API hoặc ghi dữ liệu trước khi trả `null`, side effect vẫn đã xảy ra dù item không tới writer. Nếu có retry hoặc rollback, side effect có thể bị lặp. Hãy giữ processor thuần hoặc dùng cơ chế idempotent/transactional phù hợp.

## Ghi nhớ

Trong Spring Batch, `ItemProcessor` trả về `null` để filter item hiện tại khỏi luồng output. Item đó đã được reader đọc nhưng không được chuyển tới writer; Spring Batch ghi nhận bằng `filterCount`, không phải skip count. `null` từ reader lại có nghĩa là hết input. Hãy dùng filtering cho item hợp lệ nhưng không cần kết quả, còn dữ liệu lỗi cần xử lý bằng exception và skip/retry policy. Nếu cần lưu lý do hoặc nội dung item bị loại, hãy thiết kế output quyết định hoặc luồng audit riêng thay vì chỉ trả `null`.

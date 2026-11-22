# Filtering processor

Trong Spring Batch, `ItemProcessor` có thể vừa biến đổi dữ liệu vừa quyết định item nào được đưa tiếp đến Writer. Khi một Processor trả về `null`, Spring Batch hiểu rằng item đó được **filter** và sẽ không ghi item này ra output của Step.

Filtering phù hợp khi item hợp lệ về cấu trúc nhưng không thuộc phạm vi cần xử lý, ví dụ đơn hàng đã hủy, giao dịch ngoài kỳ, khách hàng không thuộc tenant hoặc bản ghi không thỏa điều kiện nghiệp vụ. Đây là quyết định xử lý bình thường, không phải lỗi. Vì vậy, filtering khác với skip: filter trả `null`, còn skip thường xảy ra khi một exception được cấu hình để bỏ qua.

## 1. Filtering trong chunk processing

Một chunk Step thường có luồng:

```text
ItemReader
    |
    v
ItemProcessor
    |
    +--> trả object  -> đưa item vào chunk output
    |
    +--> trả null    -> filter item, không chuyển tới Writer
    |
    v
ItemWriter nhận các item còn lại
```

Ví dụ Reader đọc 5 đơn hàng. Processor giữ lại 3 đơn hàng đang hoạt động và trả `null` cho 2 đơn hàng đã hủy. Writer chỉ nhận 3 đơn hàng được giữ lại.

```text
Reader:      A   B   C   D   E
Processor:   A  null C  null E
Writer:      A       C       E
```

Item bị filter vẫn đã được đọc và xử lý bởi Processor, nhưng không trở thành output item của chunk. Trong một Step chạy bình thường không có skip, `readCount` bao gồm các item đã đọc, `filterCount` đếm item bị filter và `writeCount` đếm item được ghi. Với retry/skip, các bộ đếm có thể phức tạp hơn do một item có thể được thử lại.

## 2. Trả về null để filter item

API `ItemProcessor<I, O>` cho phép trả về một object kiểu `O` hoặc `null`. Giá trị `null` là tín hiệu filter:

```java
import org.springframework.batch.item.ItemProcessor;

public class ActiveOrderProcessor
        implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        if (order.isCancelled()) {
            return null;
        }

        return order;
    }
}
```

Trong ví dụ, đơn hàng đã hủy không được gửi tới Writer. Processor không ném exception vì đây là điều kiện loại bỏ đã được dự kiến trong nghiệp vụ.

Có thể dùng lambda cho logic đơn giản:

```java
ItemProcessor<Order, Order> activeOrderProcessor = order ->
        order.isCancelled() ? null : order;
```

Không trả về một object rỗng để biểu diễn filter. Writer vẫn nhận object đó và có thể ghi dữ liệu không hợp lệ. Dùng `null` khi muốn loại item khỏi output của pipeline.

## 3. Ví dụ lọc theo trạng thái nghiệp vụ

Giả sử Job chỉ export đơn hàng có trạng thái `PAID` hoặc `READY_TO_SHIP`:

```java
public class ExportableOrderProcessor
        implements ItemProcessor<Order, ExportOrder> {

    @Override
    public ExportOrder process(Order order) {
        if (order.getStatus() != OrderStatus.PAID
                && order.getStatus() != OrderStatus.READY_TO_SHIP) {
            return null;
        }

        return new ExportOrder(
                order.getId(),
                order.getCustomerId(),
                order.getAmount());
    }
}
```

Processor đồng thời filter và transform: item không đủ điều kiện trả `null`; item đủ điều kiện được chuyển thành `ExportOrder`.

Điều kiện lọc nên phản ánh quy tắc nghiệp vụ rõ ràng. Nếu trạng thái không được hỗ trợ là lỗi dữ liệu, hãy ném exception nghiệp vụ thay vì tự động filter. Nếu mọi trạng thái ngoài hai giá trị trên đều được phép loại bỏ, trả `null` là hợp lý.

## 4. Kết hợp Filtering Processor với Step

Ví dụ cấu hình chunk Step trong Spring Batch 5:

```java
@Bean
public Step exportPaidOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, ExportOrder> exportableOrderProcessor,
        ItemWriter<ExportOrder> exportWriter) {

    return new StepBuilder("exportPaidOrdersStep", jobRepository)
            .<Order, ExportOrder>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(exportableOrderProcessor)
            .writer(exportWriter)
            .build();
}
```

Spring Batch gọi Processor cho từng item Reader trả về. Những item có kết quả `null` bị loại khỏi chunk output; Writer chỉ nhận các `ExportOrder` còn lại. Nếu toàn bộ item trong một chunk bị filter, Writer có thể không được gọi với dữ liệu rỗng; Step vẫn tiếp tục và checkpoint theo cơ chế chunk.

Commit interval xác định nhịp chunk theo số item đầu vào được đọc/xử lý, không phải cam kết Writer luôn nhận đúng số lượng đó. Ví dụ chunk size 200 nhưng có 35 item bị filter thì Writer chỉ nhận tối đa 165 item trong chunk đó.

## 5. Filtering khác với skip

Filtering và skip đều có thể làm một item không xuất hiện trong output, nhưng ý nghĩa và cách cấu hình khác nhau.

| Tiêu chí | Filtering | Skip |
|---|---|---|
| Tín hiệu | Processor trả `null` | Exception được cấu hình skip |
| Ý nghĩa | Item hợp lệ nhưng không cần xử lý tiếp | Có lỗi được phép bỏ qua theo policy |
| Cấu hình `faultTolerant()` | Không cần chỉ để filter | Thường dùng để cấu hình skip/retry |
| Bộ đếm | `filterCount` | `readSkipCount`, `processSkipCount`, `writeSkipCount` |
| Skip limit | Không tiêu thụ skip limit | Có tiêu thụ skip limit |
| Ví dụ | Đơn hàng đã hủy không cần export | Ngày tháng sai format hoặc dữ liệu không hợp lệ được phép reject |

Ví dụ filtering:

```java
if (order.isCancelled()) {
    return null;
}
```

Ví dụ skip lỗi nghiệp vụ có thể phục hồi ở cấp record:

```java
if (order.getAmount() == null) {
    throw new InvalidOrderException("amount is required");
}
```

Step có thể cấu hình skip cho exception cụ thể:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
```

Không dùng skip để diễn tả một điều kiện nghiệp vụ loại bỏ bình thường. Ngược lại, không filter một item chỉ vì dữ liệu của nó lỗi; làm vậy có thể che giấu chất lượng dữ liệu kém và khiến Job trông như thành công.

## 6. Theo dõi số lượng item bị filter

Spring Batch ghi nhận số item bị filter trong `StepExecution`. Có thể đọc `filterCount` sau khi Step hoàn tất:

```java
long filtered = stepExecution.getFilterCount();
long read = stepExecution.getReadCount();
long written = stepExecution.getWriteCount();
long skipped = stepExecution.getSkipCount();
```

Các bộ đếm thường dùng:

| Bộ đếm | Ý nghĩa |
|---|---|
| `readCount` | Số item Reader đã đọc theo metadata Step. |
| `writeCount` | Số item đã được ghi thành công theo metadata Step. |
| `filterCount` | Số item Processor loại bằng cách trả về `null`. |
| `readSkipCount` | Số lỗi đọc được skip. |
| `processSkipCount` | Số lỗi Processor được skip. |
| `writeSkipCount` | Số lỗi Writer được skip. |
| `skipCount` | Tổng số skip ở các phase. |

Có thể dùng `StepExecutionListener.afterStep()` để ghi nhận số lượng sau khi Step kết thúc:

```java
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class FilterMetricsListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        long filtered = stepExecution.getFilterCount();
        long written = stepExecution.getWriteCount();

        log.info("Step {} filtered={}, written={}",
                stepExecution.getStepName(), filtered, written);

        return null;
    }
}
```

`afterStep()` chạy khi Step kết thúc. Nếu cần thống kê bền vững theo từng lý do filter, chỉ `filterCount` là chưa đủ vì nó không lưu nguyên nhân của từng item. Hãy thiết kế thêm audit/reject output phù hợp.

## 7. Lắng nghe item bị filter bằng ItemProcessListener

`ItemProcessListener.afterProcess(item, result)` nhận kết quả Processor. Khi `result == null`, có thể nhận biết item đã bị filter:

```java
import org.springframework.batch.core.ItemProcessListener;

public class FilterObservationListener
        implements ItemProcessListener<Order, ExportOrder> {

    @Override
    public void beforeProcess(Order item) {
    }

    @Override
    public void afterProcess(Order item, ExportOrder result) {
        if (result == null) {
            log.debug("Filtered order {}", item.getId());
        }
    }

    @Override
    public void onProcessError(Order item, Exception e) {
        log.warn("Processing failed for order {}", item.getId(), e);
    }
}
```

Đăng ký listener trong Step:

```java
return new StepBuilder("exportPaidOrdersStep", jobRepository)
        .<Order, ExportOrder>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(exportableOrderProcessor)
        .writer(exportWriter)
        .listener(filterObservationListener)
        .build();
```

Listener hữu ích để quan sát hoặc ghi log. Tuy nhiên, không nên thực hiện một side effect không idempotent như gửi email hoặc gọi API chỉ vì item bị filter. Callback có thể được gọi trong một chunk sau đó rollback/retry; log hoặc external effect có thể bị lặp dù dữ liệu chunk chưa commit.

Nếu cần lưu audit bền vững cho item bị filter, hãy đưa quyết định filter vào một object kết quả và ghi audit trong transaction phù hợp, như phần tiếp theo.

## 8. Lưu lý do filter thay vì chỉ tăng filterCount

Processor trả `null` chỉ nói rằng item bị loại. Nó không truyền lý do sang Writer vì item đã bị loại khỏi output. Nếu cần báo cáo vì sao từng record bị filter, có thể dùng một kiểu kết quả bao bọc quyết định xử lý:

```java
public record OrderDecision(
        Order order,
        boolean accepted,
        String reason) {
}
```

Processor luôn trả về decision:

```java
ItemProcessor<Order, OrderDecision> decisionProcessor = order -> {
    if (order.isCancelled()) {
        return new OrderDecision(order, false, "CANCELLED");
    }
    if (order.getAmount().signum() <= 0) {
        return new OrderDecision(order, false, "NON_POSITIVE_AMOUNT");
    }
    return new OrderDecision(order, true, null);
};
```

Sau đó, một routing Writer có thể gửi decision hợp lệ đến Writer nghiệp vụ và decision bị loại đến Writer audit/reject. Ví dụ về ý tưởng:

```java
ClassifierCompositeItemWriter<OrderDecision> decisionWriter =
        new ClassifierCompositeItemWriterBuilder<OrderDecision>()
                .classifier(decision -> decision.accepted()
                        ? acceptedOrderWriter
                        : filteredOrderAuditWriter)
                .build();
```

Ví dụ này minh họa routing theo từng item; cần khai báo các delegate Writer phù hợp với kiểu `OrderDecision` và cấu hình transaction/lifecycle của chúng. Khác với filtering bằng `null`, cả hai loại decision vẫn là item output của Processor, sau đó được chuyển tới Writer tương ứng.

Nếu audit record phải cùng commit với dữ liệu nghiệp vụ, các Writer nên dùng cùng database và transaction manager. Nếu audit là hệ thống riêng, cần idempotency hoặc outbox để tránh trạng thái audit lệch với dữ liệu chính.

## 9. Kết hợp nhiều Processor bằng CompositeItemProcessor

Một pipeline có thể gồm nhiều Processor: filter trước, sau đó enrich và transform. `CompositeItemProcessor` gọi các delegate theo thứ tự; nếu một delegate trả `null`, item bị filter và các delegate phía sau không nhận item đó.

```java
ItemProcessor<Order, Order> filterCancelled = order ->
        order.isCancelled() ? null : order;

ItemProcessor<Order, EnrichedOrder> enrichOrder = order ->
        new EnrichedOrder(
                order,
                customerService.findSegment(order.getCustomerId()));

CompositeItemProcessor<Order, EnrichedOrder> processor =
        new CompositeItemProcessorBuilder<Order, EnrichedOrder>()
                .delegates(List.of(filterCancelled, enrichOrder))
                .build();
```

Thứ tự quan trọng: `filterCancelled` chạy trước để tránh gọi `customerService` cho đơn hàng đã hủy. Nếu đảo thứ tự, ứng dụng có thể thực hiện truy vấn hoặc enrichment tốn kém cho item cuối cùng vẫn bị loại.

Nếu một delegate ném exception, đó là lỗi processing và được xử lý theo retry/skip policy của Step. Nếu delegate trả `null`, pipeline dừng cho item đó mà không coi là exception.

## 10. Filtering theo JobParameters

Một Job có thể nhận điều kiện lọc lúc launch, ví dụ chỉ export đơn hàng có amount tối thiểu hoặc thuộc một tenant. Dùng `@StepScope` để inject giá trị:

```java
@Bean
@StepScope
public ItemProcessor<Order, Order> minimumAmountProcessor(
        @Value("#{jobParameters['minimumAmount']}") BigDecimal minimumAmount) {

    if (minimumAmount == null) {
        throw new IllegalArgumentException("minimumAmount is required");
    }

    return order -> order.getAmount().compareTo(minimumAmount) >= 0
            ? order
            : null;
}
```

Launch Job:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("minimumAmount", "100.00", true)
        .toJobParameters();
```

Nếu `minimumAmount` làm thay đổi tập item thuộc batch, cần quyết định nó có phải identifying parameter hay không. Nếu cùng JobInstance được restart với điều kiện lọc khác, kết quả có thể không nhất quán với checkpoint và dữ liệu đã commit. Thông thường, tham số ảnh hưởng đến phạm vi nghiệp vụ nên được định danh hoặc được lưu cố định trong metadata batch.

## 11. Nên filter ở Reader hay Processor?

Không phải điều kiện nào cũng cần đặt trong Processor. Nếu nguồn dữ liệu hỗ trợ filter hiệu quả, có thể đẩy điều kiện xuống Reader/query để giảm lượng dữ liệu phải đọc và chuyển qua pipeline.

| Đặt điều kiện ở đâu | Khi phù hợp | Tác động |
|---|---|---|
| Reader/query | Điều kiện đơn giản, có thể biểu diễn trong SQL hoặc query nguồn | Ít item được đọc; giảm I/O và processing. |
| Processor | Điều kiện cần logic Java, dữ liệu đã enrich hoặc nhiều quy tắc nghiệp vụ | Item được đọc và tính vào `readCount`; item bị loại tăng `filterCount`. |
| Writer/routing | Cần gửi item tới các output khác nhau hoặc lưu cả accepted/rejected decision | Item vẫn được giữ dưới dạng decision và được route. |

Ví dụ nếu chỉ lấy đơn hàng `status = 'PAID'`, có thể thêm điều kiện vào SQL Reader. Nhưng nếu phải kiểm tra kết hợp nhiều field, dữ liệu tham chiếu hoặc chính sách thay đổi theo từng JobParameter, Processor có thể rõ ràng hơn.

Đẩy filter xuống Reader có thể cải thiện hiệu năng, nhưng các item bị loại sẽ không xuất hiện trong `filterCount` vì Processor không nhìn thấy chúng. Nếu cần báo cáo số lượng bị loại theo nghiệp vụ, cần thống kê query hoặc audit riêng.

## 12. Filtering và chunk size

Chunk size xác định số item được đọc/xử lý trước khi commit theo cấu hình Step. Filtering làm giảm số item Writer nhận nhưng không nhất thiết làm thay đổi số item cần đọc để đạt commit interval.

Ví dụ chunk size là 5:

```text
Reader:      A   B   C   D   E
Processor:   A  null C  null E
Writer:      A       C       E
Commit:      sau khi chunk đầu vào được xử lý
```

Chunk có 5 item đầu vào nhưng chỉ 3 item được ghi. Nếu cả 5 item đều bị filter, không có item nào được gửi đến Writer, nhưng Step vẫn phải tiến hành quản lý checkpoint/transaction theo lifecycle chunk.

Không tăng chunk size chỉ để bù số item bị filter nếu chưa đo hiệu năng. Chunk lớn hơn làm tăng phạm vi rollback, thời gian transaction và memory. Nếu tỷ lệ filter cao, hãy cân nhắc filter tại Reader/query khi điều kiện có thể đẩy xuống nguồn.

## 13. Filtering phải ổn định qua retry và restart

Một Processor có thể được gọi lại nếu chunk retry hoặc Job restart. Điều kiện filter nên có tính xác định với cùng item và cùng tham số batch.

Ví dụ, filter theo `order.status` được lưu trong item là khá ổn định. Filter theo trạng thái từ một API thay đổi liên tục có thể đưa cùng item vào output ở lần chạy đầu nhưng loại nó ở lần restart.

Để giữ kết quả nhất quán:

1. Dùng cùng identifying JobParameters khi restart.
2. Giữ snapshot/version của dữ liệu nguồn nếu điều kiện lọc phụ thuộc trạng thái nguồn.
3. Lưu phiên bản rule hoặc policy nếu quy tắc filter có thể thay đổi.
4. Tránh gọi service ngoài có trạng thái biến động cho mỗi item nếu kết quả phải ổn định.
5. Không tạo side effect trong Processor chỉ để đánh dấu item đã filter.

Nếu cần filter theo một bảng tham chiếu có thể thay đổi, hãy snapshot dữ liệu tham chiếu hoặc lưu version/time cutoff của policy. Khi đó cùng JobInstance có thể áp dụng cùng một tập quy tắc trong suốt restart.

## 14. Side effect trong Processor và transaction

Processor nên chủ yếu thực hiện tính toán, mapping, enrichment có kiểm soát và quyết định filter. Không nên gửi email, gọi API tạo giao dịch hoặc ghi audit độc lập ngay trong `process()`.

Lý do: Processor có thể được gọi lại do retry hoặc rollback. Database transaction của chunk có thể rollback, nhưng side effect ở hệ thống bên ngoài không tự được hoàn tác. Item có thể bị filter sau khi một side effect đã xảy ra, hoặc chunk có thể fail sau khi Processor xử lý một số item.

Nếu cần ghi nhận item bị filter, hãy:

- Trả về decision object và ghi audit qua Writer trong transaction phù hợp.
- Ghi sự kiện vào outbox cùng transaction database.
- Dùng idempotency key ổn định theo business item và batch.
- Chỉ publish thông báo sau khi transaction/Step thành công.

Listener cũng có thể được gọi trong một lần thử chunk sau đó rollback. Dùng listener để log/metrics quan sát là phù hợp; dùng nó làm nơi duy nhất ghi dữ liệu nghiệp vụ bền vững cần được cân nhắc kỹ.

## 15. Filter tất cả item và kết quả Step

Một Step có thể đọc nhiều item nhưng filter tất cả. Khi đó Writer không ghi bản ghi nào, nhưng Step vẫn có thể hoàn thành bình thường nếu không có lỗi khác.

Ví dụ:

```text
readCount   = 1000
filterCount = 1000
writeCount  = 0
skipCount   = 0
BatchStatus = COMPLETED
```

Đây có thể là kết quả hợp lệ nếu không có item nào thuộc điều kiện xử lý. Nhưng trong một số hệ thống, `writeCount = 0` có thể cho thấy cấu hình filter sai hoặc dữ liệu nguồn bất thường.

Có thể kiểm tra sau Step:

```java
if (stepExecution.getReadCount() > 0
        && stepExecution.getWriteCount() == 0
        && stepExecution.getFilterCount() > 0) {
    log.info("All input items were filtered");
}
```

Nếu nghiệp vụ yêu cầu phải có ít nhất một output, hãy kiểm tra điều kiện đó trong listener/validation Step và kết thúc Job với trạng thái phù hợp. Không mặc định mọi Step có `writeCount = 0` đều là lỗi.

## 16. Kiểm thử Filtering Processor

Kiểm thử nên xác nhận cả quyết định cho từng item lẫn số liệu Step sau khi chạy.

Unit test cho Processor:

```java
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@Test
void filtersCancelledOrder() throws Exception {
    Order cancelled = new Order("ORD-1", OrderStatus.CANCELLED);
    Order paid = new Order("ORD-2", OrderStatus.PAID);

    assertNull(processor.process(cancelled));
    assertNotNull(processor.process(paid));
}
```

Integration test với Job/Step nên xác nhận:

1. Reader đọc đúng số item đầu vào.
2. Processor trả `null` cho đúng điều kiện.
3. Writer chỉ nhận các item không bị filter.
4. `StepExecution.filterCount` tăng đúng.
5. `skipCount` không tăng chỉ vì filtering.
6. Nếu Processor ném exception, skip/retry policy được áp dụng riêng.
7. Restart cùng JobInstance cho kết quả filter nhất quán.
8. Nếu audit filtered items được bật, audit và output nghiệp vụ không bị trùng sau retry.

Ví dụ assertion:

```java
assertEquals(10, stepExecution.getReadCount());
assertEquals(3, stepExecution.getFilterCount());
assertEquals(7, stepExecution.getWriteCount());
assertEquals(0, stepExecution.getSkipCount());
```

Các con số trên giả định không có retry, skip hoặc lỗi khác và Writer ghi thành công mọi item được giữ lại. Với Step có retry/skip, hãy kiểm tra bộ đếm theo semantics của phiên bản Spring Batch và kịch bản test cụ thể.

## 17. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Trả object rỗng thay vì `null` | Writer vẫn nhận item và có thể ghi dữ liệu sai. | Trả `null` để filter. |
| Dùng exception cho điều kiện loại bỏ bình thường | Tốn chi phí fault-tolerance và làm tăng skip count. | Dùng null-return filtering. |
| Filter dữ liệu lỗi như thể đó là dữ liệu không cần thiết | Che giấu lỗi chất lượng dữ liệu. | Ném exception nghiệp vụ và dùng reject/skip policy rõ ràng. |
| Nhầm `filterCount` với `skipCount` | Báo cáo vận hành sai nguyên nhân loại item. | Theo dõi riêng filter và các loại skip. |
| Mong Writer nhận item đã filter | Item trả `null` không còn trong chunk output. | Dùng decision object và routing Writer nếu cần audit. |
| Ghi audit/API trong Processor | Retry/rollback có thể tạo side effect lặp hoặc lệch. | Ghi qua Writer/outbox với idempotency. |
| Filter phụ thuộc dữ liệu ngoài thay đổi | Restart có thể đưa ra quyết định khác. | Dùng snapshot/version/cutoff ổn định. |
| Filter quá muộn sau enrichment tốn kém | Tăng query và chi phí xử lý cho item sẽ bị loại. | Đặt filter rẻ và xác định sớm trong chain. |
| Filter ở Reader nhưng mong `filterCount` tăng | Item không đi qua Processor nên không được tính là filtered. | Thống kê điều kiện Reader riêng hoặc filter trong Processor. |
| Cho rằng Step có 0 write luôn thất bại | Có thể hiểu nhầm một batch hợp lệ không có item phù hợp. | Đặt quy tắc nghiệp vụ rõ cho empty output. |

## Kết luận

Filtering Processor loại item khỏi output bằng cách trả về `null`. Đây là cách biểu diễn một quyết định nghiệp vụ bình thường; item bị filter không đi tới Writer và được tính vào `filterCount`, không phải `skipCount`. Hãy dùng filtering cho record hợp lệ nhưng không thuộc phạm vi xử lý, còn lỗi dữ liệu nên được phân loại bằng exception và skip/fail policy. Đặt điều kiện lọc sớm khi có thể, giữ rule ổn định qua restart và tránh side effect trong Processor. Nếu cần lưu lý do filter, hãy trả về decision object rồi route tới Writer audit phù hợp thay vì trả `null` và làm mất thông tin item.

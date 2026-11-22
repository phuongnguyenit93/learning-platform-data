# Processor stateless và stateful

Trong Spring Batch, `ItemProcessor<I, O>` nhận một item đầu vào, thực hiện biến đổi hoặc kiểm tra và trả về item đầu ra. Processor có thể được thiết kế **stateless** (không giữ trạng thái thay đổi phụ thuộc các item đã xử lý) hoặc **stateful** (giữ dữ liệu trong object và có thể phụ thuộc lịch sử xử lý).

Stateless processor thường dễ kiểm thử, dễ chạy song song và an toàn hơn khi Spring Batch retry một item. Stateful processor có thể hữu ích khi cần cache dữ liệu tham chiếu, kiểm tra thứ tự hoặc duy trì thông tin giữa các item, nhưng cần thiết kế rõ vòng đời, checkpoint, rollback và concurrency. Một processor có field không tự động trở thành restartable; trạng thái cần tồn tại qua lần restart phải được lưu bằng cơ chế phù hợp.

## 1. Vai trò của ItemProcessor

Trong chunk-oriented processing, Spring Batch đọc item bằng `ItemReader`, chuyển từng item qua `ItemProcessor`, rồi gửi kết quả còn lại cho `ItemWriter`:

```text
ItemReader
    |
    v
ItemProcessor.process(item)
    |
    +--> Trả object mới hoặc object đã biến đổi
    |          |
    |          v
    |       ItemWriter
    |
    +--> Trả null: filter item, không gửi item đó cho writer
```

Interface cơ bản:

```java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

Processor thường đảm nhiệm các công việc như chuẩn hóa dữ liệu, kiểm tra quy tắc nghiệp vụ, tính toán trường dẫn xuất, chuyển đổi kiểu dữ liệu hoặc quyết định item có đủ điều kiện đi tiếp hay không.

`process()` có thể trả về một object cùng kiểu hoặc kiểu khác. Nếu trả về `null`, Spring Batch xem item đó đã được filter và không chuyển nó đến writer. Nếu processor ném exception, Step xử lý theo cấu hình fault-tolerance, retry và skip nếu có.

## 2. Stateless processor là gì?

Stateless processor không lưu trạng thái thay đổi từ lần gọi `process()` này sang lần gọi tiếp theo. Kết quả xử lý của một item chỉ phụ thuộc vào item đó và các quy tắc hoặc dữ liệu cấu hình ổn định.

Ví dụ, processor chuẩn hóa đơn hàng:

```java
public class NormalizeOrderProcessor
        implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        String normalizedCustomerCode =
                order.getCustomerCode().trim().toUpperCase(Locale.ROOT);

        return new Order(
                order.getId(),
                normalizedCustomerCode,
                order.getAmount().setScale(2, RoundingMode.HALF_UP)
        );
    }
}
```

Mỗi lần gọi `process()` độc lập với những item đã xử lý trước đó. Nếu Spring Batch gọi lại processor cho cùng một item do retry hoặc rollback, kết quả vẫn nhất quán miễn là input và quy tắc xử lý không đổi.

Một ví dụ khác là lọc đơn hàng không hợp lệ:

```java
public class EligibleOrderProcessor
        implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        if (order.getAmount().signum() <= 0) {
            return null;
        }

        return order;
    }
}
```

Processor không cần nhớ số lượng item đã xử lý hoặc mã đơn hàng trước đó. Nó chỉ quyết định item hiện tại có được chuyển tiếp hay không.

### Đặc điểm của stateless processor

- Không có mutable field lưu tiến độ hoặc kết quả của item trước.
- Không phụ thuộc thứ tự gọi `process()` nếu nghiệp vụ không yêu cầu thứ tự.
- Dễ viết unit test vì mỗi test có thể kiểm tra một input và output cụ thể.
- Dễ tái sử dụng trong nhiều Step hoặc nhiều Job nếu dependency của nó an toàn khi dùng chung.
- Thường phù hợp hơn với retry, multi-threaded Step và partitioning.

Stateless không có nghĩa processor không được có field. Các dependency bất biến như cấu hình, mapper hoặc service có thể được inject. Điều quan trọng là processor không sửa trạng thái dùng chung theo từng item và không để kết quả phụ thuộc vào lịch sử gọi.

## 3. Stateful processor là gì?

Stateful processor giữ một hoặc nhiều giá trị tồn tại giữa các lần gọi `process()`. Kết quả có thể phụ thuộc vào những item đã xử lý trước đó, hoặc object có thể duy trì cache và tài nguyên được mở trong suốt vòng đời Step.

Một số trường hợp có thể cần state:

- Cache dữ liệu tham chiếu để tránh truy vấn lặp lại cho từng item.
- Kiểm tra một chuỗi item có đúng thứ tự hay không.
- Phát hiện mã nghiệp vụ đã xuất hiện trong cùng luồng dữ liệu.
- Tính số liệu tích lũy hoặc trạng thái phụ thuộc các item trước.
- Giữ tài nguyên được mở trong lúc Step thực thi, chẳng hạn parser hoặc client chuyên dụng.

Ví dụ đơn giản về trạng thái tích lũy:

```java
public class RunningTotalProcessor
        implements ItemProcessor<Order, OrderWithRunningTotal> {

    private BigDecimal runningTotal = BigDecimal.ZERO;

    @Override
    public OrderWithRunningTotal process(Order order) {
        runningTotal = runningTotal.add(order.getAmount());

        return new OrderWithRunningTotal(order, runningTotal);
    }
}
```

Kết quả của item hiện tại phụ thuộc vào tổng của các item đã xử lý trước đó. Đây là processor stateful thực sự. Tuy nhiên, ví dụ này chỉ minh họa khái niệm; nó chưa xử lý việc lưu checkpoint, rollback hoặc gọi đồng thời. Không nên dùng nguyên mẫu này trong Job cần retry, restart hoặc chạy nhiều thread.

## 4. Phân biệt trạng thái của object và trạng thái cần restart

Không phải mọi state trong processor đều cần lưu vào `ExecutionContext`. Cần phân biệt ít nhất hai loại:

| Loại state | Ví dụ | Cách xử lý |
|---|---|---|
| Cache có thể tái tạo | Map sản phẩm được tải từ bảng danh mục khi Step mở | Nạp lại trong vòng đời Step; không nhất thiết phải serialize cache |
| State phụ thuộc tiến độ item | Sequence cuối cùng đã xử lý, tập key đã thấy | Cần checkpoint hoặc lưu trong kho dữ liệu phù hợp nếu phải khôi phục sau restart |

Một processor có thể có field nhưng vẫn cho kết quả ổn định nếu field đó là cache chỉ đọc được tạo từ dữ liệu tham chiếu không đổi trong lần chạy. Ngược lại, một processor giữ bộ đếm hoặc danh sách item đã thấy có thể thay đổi kết quả theo lịch sử và cần xử lý cẩn thận hơn.

`@StepScope` giúp tạo bean gắn với một `StepExecution` và cho phép inject JobParameters hoặc StepExecutionContext. Nó không tự động serialize field của bean, không tự tạo checkpoint và không tự làm processor an toàn khi nhiều thread cùng gọi. Muốn state tồn tại qua restart, cần lưu nó bằng `ExecutionContext` hoặc một cơ chế bền vững khác.

## 5. Stateful processor dùng cache chỉ đọc

Một cách sử dụng stateful an toàn hơn là tải dữ liệu tham chiếu một lần khi Step mở, sau đó chỉ đọc cache trong `process()`. Ví dụ, mỗi đơn hàng cần bổ sung tên nhóm sản phẩm từ bảng danh mục.

```java
public class ProductEnrichmentProcessor
        implements ItemProcessor<Order, EnrichedOrder>, ItemStream {

    private final ProductRepository productRepository;
    private Map<String, Product> productsById = Map.of();

    public ProductEnrichmentProcessor(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        Map<String, Product> loaded = productRepository.findAll().stream()
                .collect(Collectors.toMap(Product::getId, Function.identity()));
        productsById = Map.copyOf(loaded);
    }

    @Override
    public EnrichedOrder process(Order order) {
        Product product = productsById.get(order.getProductId());
        if (product == null) {
            throw new IllegalArgumentException("Unknown product: " + order.getProductId());
        }

        return new EnrichedOrder(order, product.getCategory());
    }

    @Override
    public void update(ExecutionContext executionContext) {
        // Cache được nạp lại trong open(), không cần lưu toàn bộ Map vào context.
    }

    @Override
    public void close() {
        productsById = Map.of();
    }
}
```

Trong ví dụ này, processor giữ cache trong field nhưng không thay đổi cache khi xử lý từng item. `Map.copyOf()` tạo một map không thể sửa đổi qua reference này. Khi Step được restart, `open()` tải lại cache từ repository. Vì cache được tái tạo, không cần đưa toàn bộ dữ liệu danh mục vào ExecutionContext.

Đăng ký processor là stream của Step để framework gọi các callback `ItemStream`:

```java
@Bean
public Step enrichOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ProductEnrichmentProcessor processor,
        ItemWriter<EnrichedOrder> writer) {

    return new StepBuilder("enrichOrdersStep", jobRepository)
            .<Order, EnrichedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .stream(processor)
            .build();
}
```

Với cache lớn, tải toàn bộ bảng vào memory có thể không phù hợp. Có thể dùng cache giới hạn kích thước, service tra cứu có cache hoặc join dữ liệu ở query của reader. Cũng cần xác định dữ liệu tham chiếu có được phép thay đổi giữa các lần restart hay không; nếu kết quả cần nhất quán tuyệt đối, nên dùng version hoặc snapshot của dữ liệu tham chiếu.

## 6. Stateful processor phụ thuộc lịch sử item

Một processor có thể cần biết item trước để kiểm tra thứ tự hoặc phát hiện dữ liệu trùng. Ví dụ, nguồn dữ liệu được yêu cầu sắp theo sequence tăng dần. Processor giữ sequence cuối cùng đã xử lý:

```java
public class IncreasingSequenceProcessor
        implements ItemProcessor<Order, Order>, ItemStream {

    private static final String LAST_SEQUENCE_KEY = "sequenceProcessor.lastSequence";
    private long lastSequence;

    @Override
    public void open(ExecutionContext executionContext) {
        lastSequence = executionContext.getLong(LAST_SEQUENCE_KEY, 0L);
    }

    @Override
    public Order process(Order order) {
        if (order.getSequence() <= lastSequence) {
            throw new IllegalStateException("Input sequence is not increasing");
        }

        lastSequence = order.getSequence();
        return order;
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putLong(LAST_SEQUENCE_KEY, lastSequence);
    }

    @Override
    public void close() {
        // Không có tài nguyên ngoài cần đóng.
    }
}
```

Với processor dạng này, cần đăng ký nó như stream để `open()` và `update()` được gọi. `open()` khôi phục sequence đã lưu; `update()` ghi trạng thái hiện tại vào Step ExecutionContext tại điểm checkpoint.

Đây là ví dụ minh họa cho cơ chế lưu state, không phải một mẫu an toàn cho mọi cấu hình fault-tolerance. Nếu chunk rollback hoặc processor được gọi lại do retry, field `lastSequence` trong bộ nhớ có thể đã tiến lên dù transaction chưa commit. `ExecutionContext` được rollback theo transaction không tự đưa field Java trong processor quay về giá trị cũ. Processor cần có chiến lược rollback-aware, chẳng hạn tách state tạm của chunk khỏi state đã commit, hoặc tránh giữ state phụ thuộc lịch sử trong processor khi Step có retry/skip phức tạp.

Đối với logic phát hiện trùng hoặc kiểm tra uniqueness quan trọng, cân nhắc dùng unique constraint, bảng staging hoặc kho trạng thái có transaction phù hợp. Đừng dựa hoàn toàn vào một `HashSet` trong processor để bảo đảm tính duy nhất xuyên suốt các lần chạy và restart.

## 7. Retry và rollback ảnh hưởng đến stateful processor thế nào?

Spring Batch có thể gọi lại processor trong một số tình huống fault-tolerance. Ví dụ, một item có thể được xử lý lại khi retry sau exception, hoặc cả chunk có thể được thực thi lại sau rollback tùy loại lỗi và cấu hình.

Stateless processor có lợi thế ở đây: gọi lại cùng input với cùng quy tắc thường tạo cùng output. Stateful processor có thể đã thay đổi field trong lần gọi trước, do đó lần gọi lại có thể tạo kết quả khác hoặc làm bộ đếm bị tăng hai lần.

Ví dụ một processor tăng bộ đếm trong `process()`:

```java
private long processedCount;

@Override
public Order process(Order order) {
    processedCount++;
    return order;
}
```

Nếu chunk rollback và item được xử lý lại, `processedCount` có thể tính cả lần xử lý chưa commit. Đây không nhất thiết là số item đã xử lý thành công. Không nên dùng field kiểu này để báo cáo số liệu chính thức; hãy dùng counter do `StepExecution` quản lý hoặc cập nhật số liệu sau khi chunk commit.

Một số nguyên tắc khi processor có state:

- Tránh side effect không thể rollback trong `process()`, như gửi email, gọi API tạo giao dịch hoặc ghi trực tiếp dữ liệu ngoài transaction.
- Nếu phải thực hiện side effect, thiết kế idempotency key hoặc chuyển thao tác sang writer/after-commit/outbox phù hợp.
- Phân biệt state đã commit với state đang thay đổi trong chunk hiện tại.
- Không giả định việc ghi ExecutionContext sẽ tự rollback field trong bộ nhớ.
- Kiểm thử trường hợp writer lỗi sau khi processor đã xử lý toàn bộ chunk, retry item và restart sau khi process bị dừng.

## 8. Stateful processor và chạy đa luồng

Trong multi-threaded Step, nhiều thread có thể gọi cùng một processor instance. Nếu processor chứa mutable field, các thread có thể đồng thời đọc và ghi field đó, gây race condition hoặc kết quả phụ thuộc thứ tự thread.

Ví dụ nguy hiểm:

```java
public class UnsafeCounterProcessor implements ItemProcessor<Order, Order> {

    private long count;

    @Override
    public Order process(Order order) {
        count++;
        return order.withSequence(count);
    }
}
```

Với nhiều thread, hai item có thể nhận cùng sequence hoặc thứ tự sequence không phản ánh thứ tự nghiệp vụ. Dùng `AtomicLong` chỉ bảo vệ thao tác tăng số, không bảo đảm thứ tự nghiệp vụ, restartability hay rollback correctness.

Các lựa chọn thiết kế:

- Ưu tiên processor stateless và dependency bất biến.
- Nếu state chỉ là cache, tải cache bất biến trước khi xử lý và bảo đảm an toàn khi nhiều thread đọc.
- Nếu state phải tách theo worker, dùng partitioning để mỗi partition có `StepExecution` và state riêng; thiết kế bean scope và stream cho từng partition.
- Nếu state cần chia sẻ giữa nhiều thread, dùng một cơ chế đồng bộ hoặc kho trạng thái có transaction rõ ràng, đồng thời cân nhắc tác động hiệu năng.
- Không giả định `@StepScope` tự làm một bean an toàn khi nhiều thread trong cùng Step cùng gọi nó.

## 9. Scope của processor trong Spring

Một processor thường được khai báo thành bean singleton. Nếu nó stateless và các dependency an toàn khi dùng chung, singleton có thể phù hợp. Nếu processor cần cấu hình hoặc state riêng cho từng StepExecution, có thể dùng `@StepScope`:

```java
@Bean
@StepScope
public ItemProcessor<Order, Order> orderProcessor(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return order -> enrichForBusinessDate(order, businessDate);
}
```

Step scope cho phép inject JobParameters vào thời điểm Step chạy và tạo target gắn với StepExecution. Tuy nhiên:

- Scope không tự lưu field vào JobRepository.
- Muốn lưu state qua restart, processor vẫn cần `ItemStream` hoặc cơ chế persistence riêng.
- Với multi-threaded Step, nhiều thread có thể cùng dùng processor của StepExecution đó; mutable state vẫn cần được xử lý concurrency.
- Với partitioning, mỗi partition có StepExecution riêng nên có thể tổ chức state theo từng partition.

Nếu processor chỉ cần đọc JobParameters và không giữ state thay đổi, có thể giữ thiết kế stateless và dùng Step scope chỉ để lấy tham số lúc runtime.

## 10. Composite processor và state của delegate

Spring Batch cho phép ghép nhiều processor bằng `CompositeItemProcessor`. Mỗi delegate xử lý output của delegate trước:

```text
Order
  |
  v
NormalizeProcessor
  |
  v
ValidateProcessor
  |
  v
EnrichProcessor
  |
  v
ItemWriter
```

Ví dụ cấu hình:

```java
@Bean
public CompositeItemProcessor<Order, EnrichedOrder> orderProcessor(
        ItemProcessor<Order, Order> normalizeProcessor,
        ItemProcessor<Order, Order> validateProcessor,
        ItemProcessor<Order, EnrichedOrder> enrichProcessor) {

    return new CompositeItemProcessorBuilder<Order, EnrichedOrder>()
            .delegates(normalizeProcessor, validateProcessor, enrichProcessor)
            .build();
}
```

Nếu một delegate cần lifecycle `ItemStream`, phải bảo đảm delegate đó được đăng ký với Step để callback `open`, `update` và `close` được gọi. Tùy cấu trúc composite và phiên bản framework, không nên giả định mọi delegate stream tự động được phát hiện. Có thể đăng ký rõ ràng bằng `.stream(delegate)` trong cấu hình Step.

State của mỗi delegate cần được đánh giá riêng. Một composite gồm các processor stateless vẫn đơn giản để chạy đồng thời; chỉ một delegate stateful không an toàn cũng có thể khiến toàn bộ pipeline không thread-safe hoặc không restart đúng.

## 11. Kiểm thử stateless và stateful processor

Với stateless processor, unit test thường chỉ cần input và expected output:

```java
@Test
void normalizesCustomerCode() {
    NormalizeOrderProcessor processor = new NormalizeOrderProcessor();
    Order input = new Order(10L, "  ab-01 ", new BigDecimal("12.345"));

    Order output = processor.process(input);

    assertEquals("AB-01", output.getCustomerCode());
    assertEquals(new BigDecimal("12.35"), output.getAmount());
}
```

Với stateful processor, ngoài kết quả từng item, cần kiểm thử vòng đời và state:

- `open()` với context rỗng tạo trạng thái ban đầu đúng.
- `update()` ghi đúng checkpoint vào ExecutionContext.
- Một instance mới `open()` với context đã lưu khôi phục được state.
- Sau khi restart, item tiếp theo được xử lý đúng theo state đã commit.
- Chunk rollback và retry không làm state vượt quá tiến độ đã commit.
- Nhiều thread không làm hỏng state nếu Step được cấu hình chạy song song.

Kiểm thử stateful processor nên bao gồm cả tình huống lỗi ở writer, vì lỗi có thể xảy ra sau khi processor đã cập nhật field. Chỉ test chuỗi item thành công liên tiếp chưa đủ để chứng minh processor an toàn khi restart.

## 12. Những nhầm lẫn thường gặp

**Cho rằng mọi processor đều phải stateless.** Stateless là lựa chọn mặc định tốt, nhưng stateful có thể hữu ích với cache, kiểm tra chuỗi hoặc logic cần lịch sử. Điều quan trọng là quản lý state đúng vòng đời.

**Cho rằng có field là state đã được lưu.** Field chỉ tồn tại trong object Java. Muốn khôi phục sau restart, phải lưu state vào ExecutionContext hoặc kho bền vững khác.

**Cho rằng `@StepScope` tự làm processor restartable.** Step scope quản lý phạm vi bean theo StepExecution, không tự serialize field hoặc lưu checkpoint.

**Cho rằng `AtomicLong` giải quyết mọi vấn đề đa luồng.** Atomic chỉ bảo vệ thao tác nguyên tử. Nó không giải quyết thứ tự nghiệp vụ, rollback, checkpoint hoặc tính idempotent.

**Tạo side effect trong `process()`.** Processor có thể được gọi lại do retry/rollback. Side effect bên ngoài transaction có thể xảy ra nhiều lần hoặc không khớp với kết quả commit.

**Dùng state trong processor làm số liệu commit chính thức.** Field có thể tăng trong chunk rollback. Dùng StepExecution counters hoặc ghi nhận sau commit cho số liệu thực tế.

## 13. Chọn kiểu processor phù hợp

Ưu tiên stateless processor khi mỗi item có thể được xử lý độc lập. Nếu cần cache, hãy dùng dữ liệu tham chiếu bất biến và tái tạo cache trong vòng đời Step. Nếu nghiệp vụ thực sự phụ thuộc lịch sử item, xác định rõ state thuộc về một StepExecution, lưu checkpoint khi cần restart và xử lý riêng tình huống rollback, retry, skip và chạy đa luồng.

Một processor tốt không chỉ tạo ra output đúng trong một lần chạy thuận lợi. Nó còn phải giữ được hành vi nhất quán khi item được xử lý lại, chunk rollback, Job restart hoặc Step chạy song song. Thiết kế stateless thường làm các yêu cầu đó đơn giản hơn; stateful vẫn có thể dùng khi state có phạm vi và vòng đời được quản lý rõ ràng.

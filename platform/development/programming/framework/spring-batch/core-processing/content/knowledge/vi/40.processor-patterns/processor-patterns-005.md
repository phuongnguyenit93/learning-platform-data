# Composite processor

`CompositeItemProcessor<I, O>` kết hợp nhiều `ItemProcessor` thành một pipeline tuần tự. Mỗi delegate nhận output của delegate trước và tạo input cho delegate tiếp theo. Cách tổ chức này giúp chia xử lý item thành các bước nhỏ như validation, chuẩn hóa, enrichment và chuyển đổi sang model đầu ra.

Composite processor chỉ điều phối chuỗi xử lý cho một item. Nó không tự chạy các delegate song song, không ghi dữ liệu và không tạo transaction riêng. Spring Batch vẫn gọi composite từ chunk step; exception, filtering, retry, skip và transaction được xử lý theo policy của step.

## 1. CompositeItemProcessor hoạt động như thế nào?

`CompositeItemProcessor` gọi các delegate theo đúng thứ tự đã cấu hình. Output của delegate thứ nhất trở thành input của delegate thứ hai, cứ tiếp tục cho đến delegate cuối cùng.

```text
ItemReader<OrderInput>
        |
        v
CompositeItemProcessor
        |
        +--> validateProcessor
        |       OrderInput -> ValidatedOrder
        |
        +--> normalizeProcessor
        |       ValidatedOrder -> NormalizedOrder
        |
        +--> enrichProcessor
        |       NormalizedOrder -> EnrichedOrder
        |
        v
ItemWriter<EnrichedOrder>
```

Ví dụ pipeline tách ba trách nhiệm:

- Validation kiểm tra dữ liệu đầu vào và từ chối item không hợp lệ.
- Normalization chuẩn hóa mã, chuỗi hoặc định dạng ngày.
- Enrichment bổ sung dữ liệu tham chiếu hoặc giá trị tính toán.

Delegate cuối cùng trả về kiểu dữ liệu mà writer nhận. Không có bước tự động quay lại output của delegate trước.

## 2. Khai báo các kiểu dữ liệu trung gian

Nên đặt kiểu dữ liệu rõ ràng giữa các bước. Điều này giúp mỗi processor có contract nhỏ và thể hiện được dữ liệu đã qua xử lý nào.

```java
public record OrderInput(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

public record ValidatedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

public record NormalizedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

public record EnrichedOrder(
        String orderId,
        Long customerId,
        BigDecimal amount,
        String riskCategory) {
}
```

Ví dụ dùng Java record để giữ dữ liệu bất biến. Với class thông thường, có thể dùng constructor, getter và immutable value object tương tự.

## 3. Viết các delegate processor riêng

Mỗi delegate triển khai `ItemProcessor<I, O>`. Phương thức `process` nhận một item và trả về item tiếp theo hoặc `null` để filter item.

Processor validation:

```java
public class OrderValidationProcessor
        implements ItemProcessor<OrderInput, ValidatedOrder> {

    @Override
    public ValidatedOrder process(OrderInput input) {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new InvalidOrderException("orderId is required");
        }
        if (input.amount() == null || input.amount().signum() < 0) {
            throw new InvalidOrderException("amount must be non-negative");
        }

        return new ValidatedOrder(
            input.orderId().trim(),
            input.customerCode(),
            input.amount()
        );
    }
}
```

Processor normalization:

```java
public class OrderNormalizationProcessor
        implements ItemProcessor<ValidatedOrder, NormalizedOrder> {

    @Override
    public NormalizedOrder process(ValidatedOrder order) {
        return new NormalizedOrder(
            order.orderId().toUpperCase(Locale.ROOT),
            order.customerCode().trim().toUpperCase(Locale.ROOT),
            order.amount().setScale(2, RoundingMode.HALF_UP)
        );
    }
}
```

Processor enrichment:

```java
public class OrderEnrichmentProcessor
        implements ItemProcessor<NormalizedOrder, EnrichedOrder> {

    private final CustomerLookup customerLookup;

    public OrderEnrichmentProcessor(CustomerLookup customerLookup) {
        this.customerLookup = customerLookup;
    }

    @Override
    public EnrichedOrder process(NormalizedOrder order) {
        Customer customer = customerLookup.findByCode(order.customerCode());
        if (customer == null) {
            throw new UnknownCustomerException(order.customerCode());
        }

        return new EnrichedOrder(
            order.orderId(),
            customer.id(),
            order.amount(),
            customer.riskCategory()
        );
    }
}
```

Giữ lookup, mapping và validation trong component có tên rõ ràng. Khi cần thay đổi quy tắc chuẩn hóa, chỉ delegate tương ứng cần được sửa hoặc thay thế.

## 4. Ghép delegate bằng CompositeItemProcessorBuilder

Trong Spring Batch 5, có thể dùng `CompositeItemProcessorBuilder` để khai báo chuỗi delegate:

```java
@Bean
CompositeItemProcessor<OrderInput, EnrichedOrder> orderCompositeProcessor(
        OrderValidationProcessor validationProcessor,
        OrderNormalizationProcessor normalizationProcessor,
        OrderEnrichmentProcessor enrichmentProcessor) throws Exception {

    return new CompositeItemProcessorBuilder<OrderInput, EnrichedOrder>()
        .delegates(
            validationProcessor,
            normalizationProcessor,
            enrichmentProcessor
        )
        .build();
}
```

Thứ tự trong `delegates(...)` là thứ tự thực thi. Ở ví dụ trên, enrichment nhận `NormalizedOrder`, không nhận `OrderInput` hoặc `ValidatedOrder`.

Builder kiểm tra cấu hình cơ bản như danh sách delegate. Do generic type của danh sách delegate thường được biểu diễn qua wildcard, compiler không phải lúc nào cũng phát hiện được mọi mismatch giữa các kiểu trung gian. Hãy khai báo kiểu từng processor rõ ràng và kiểm thử toàn bộ chain.

## 5. Dùng setDelegates khi không dùng builder

Cũng có thể cấu hình `CompositeItemProcessor` trực tiếp:

```java
@Bean
CompositeItemProcessor<OrderInput, EnrichedOrder> orderCompositeProcessor(
        OrderValidationProcessor validationProcessor,
        OrderNormalizationProcessor normalizationProcessor,
        OrderEnrichmentProcessor enrichmentProcessor) throws Exception {

    CompositeItemProcessor<OrderInput, EnrichedOrder> composite =
        new CompositeItemProcessor<>();

    composite.setDelegates(List.of(
        validationProcessor,
        normalizationProcessor,
        enrichmentProcessor
    ));
    composite.afterPropertiesSet();

    return composite;
}
```

`afterPropertiesSet()` xác nhận cấu hình cần thiết đã được thiết lập. Khi dùng builder, phần khởi tạo này được builder xử lý.

Không thay đổi danh sách delegate trong lúc step đang chạy. Cấu hình pipeline nên bất biến trong suốt một execution để tránh mỗi item đi qua một chuỗi khác nhau.

## 6. Kết nối composite processor với chunk step

Composite processor được truyền vào step như một `ItemProcessor` thông thường:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        CompositeItemProcessor<OrderInput, EnrichedOrder> orderCompositeProcessor,
        ItemWriter<EnrichedOrder> orderWriter) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderInput, EnrichedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderCompositeProcessor)
        .writer(orderWriter)
        .build();
}
```

Chunk size và transaction manager vẫn được cấu hình ở step. Composite không mở transaction riêng cho từng delegate; các delegate chạy trong flow xử lý item của chunk hiện tại.

## 7. Thứ tự delegate ảnh hưởng kết quả

Đổi thứ tự delegate có thể thay đổi cả semantics lẫn kiểu dữ liệu được truyền.

Ví dụ đúng:

```text
OrderInput
   -> validate
   -> normalize
   -> enrich
   -> EnrichedOrder
```

Ví dụ sai về mặt logic:

```text
OrderInput
   -> enrich (cần customerCode đã normalize)
   -> normalize
```

Trong ví dụ sai, lookup có thể thất bại nếu mã khách hàng chứa khoảng trắng hoặc khác chữ hoa/thường. Các bước cần được sắp theo dependency dữ liệu và quy tắc nghiệp vụ.

Nếu một bước cần dữ liệu do bước sau tạo ra, pipeline tuyến tính không thể giải quyết dependency đó bằng cách đổi thứ tự tùy ý. Hãy thiết kế lại input/output object hoặc tạo một processor điều phối chuyên biệt.

## 8. Null là tín hiệu filter item

Theo contract của `ItemProcessor`, trả về `null` có nghĩa item bị filter và không được chuyển tiếp tới writer. Trong `CompositeItemProcessor`, nếu một delegate trả `null`, chain dừng cho item đó; các delegate còn lại không được gọi.

Ví dụ:

```java
public class IgnoreCancelledOrderProcessor
        implements ItemProcessor<NormalizedOrder, NormalizedOrder> {

    @Override
    public NormalizedOrder process(NormalizedOrder order) {
        if (order.isCancelled()) {
            return null;
        }
        return order;
    }
}
```

Pipeline:

```text
OrderInput
   -> validate
   -> normalize
   -> filterCancelled
         |
         +--> null: dừng chain, writer không nhận item
         |
         +--> item: tiếp tục enrich
```

Đảm bảo chỉ dùng `null` cho filtering có chủ đích. Nếu null biểu thị dữ liệu đầu vào bị thiếu hoặc lỗi mapping, hãy ném exception phù hợp để step áp dụng policy fail/skip/retry.

## 9. Phân biệt filter với exception

Filter và exception có ý nghĩa vận hành khác nhau:

| Hành vi processor | Ý nghĩa | Tác động trong step |
|---|---|---|
| Trả về item | Tiếp tục pipeline và có thể tới writer | Tăng process count; writer xử lý item |
| Trả về `null` | Item bị filter | Tăng filter count; writer không nhận item |
| Ném exception | Xử lý item thất bại | Step áp dụng rollback, retry hoặc skip policy |

Không nên trả `null` để che giấu lỗi dữ liệu. Ví dụ customer không tồn tại có thể là lỗi cần reject/audit, không phải filter bình thường.

## 10. Exception từ delegate được truyền lên step

Nếu một delegate ném exception, `CompositeItemProcessor` không tiếp tục các delegate sau cho item đó. Exception được truyền lên chunk step để Spring Batch xử lý theo fault-tolerance configuration.

```text
validate -> normalize -> enrich
                         |
                         +--> exception
                               |
                               v
                       chunk fault handling
                         /           \
                      retry         skip/fail
```

Không bắt mọi exception trong delegate rồi trả `null`. Làm vậy biến lỗi thành filter và khiến step có thể hoàn thành dù item bị mất.

Nếu cần thêm ngữ cảnh, hãy bọc exception với item key và nguyên nhân gốc, nhưng tránh đưa payload nhạy cảm vào message/log.

## 11. Retry và skip với composite processor

Fault tolerance được cấu hình trên step, không phải trên từng delegate riêng lẻ:

```java
return new StepBuilder("importOrders", jobRepository)
    .<OrderInput, EnrichedOrder>chunk(100, transactionManager)
    .reader(orderReader)
    .processor(orderCompositeProcessor)
    .writer(orderWriter)
    .faultTolerant()
    .retry(TransientCustomerLookupException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(50)
    .build();
```

Ví dụ này retry lỗi lookup tạm thời và skip lỗi input đã phân loại. Các exception thực tế cần được chọn theo nguyên nhân và semantics của ứng dụng.

Khi retry, composite có thể chạy lại từ đầu cho item đó; do đó delegate cần tránh side effect không idempotent. Nếu delegate gửi message, ghi file hoặc gọi API, hãy dùng outbox/idempotency hoặc chuyển side effect sang giai đoạn sau commit.

Không retry lỗi validation cố định như thiếu order ID. Không skip lỗi hạ tầng diện rộng như database unavailable nếu việc tiếp tục các item khác không có ý nghĩa.

## 12. Delegate nên tập trung một trách nhiệm

Pipeline dễ bảo trì khi mỗi delegate có một mục đích rõ:

- Validation: xác nhận field bắt buộc, range và invariant của item.
- Normalization: chuẩn hóa định dạng, mã và whitespace.
- Enrichment: bổ sung dữ liệu từ reference data.
- Classification: gán category hoặc route metadata cho item.
- Mapping: chuyển sang DTO/entity mà writer cần.

Tránh tạo một delegate cho mỗi dòng code nhỏ nếu điều đó làm pipeline khó đọc. Ngược lại, một processor khổng lồ chứa nhiều bước độc lập khiến logic khó kiểm thử và thay đổi.

Chọn ranh giới dựa trên khả năng đặt tên, tái sử dụng, kiểm thử độc lập và thay đổi riêng biệt.

## 13. Processor nên stateless khi có thể

Processor thường được tạo như Spring singleton. Nếu lưu state mutable theo item trong field, các item hoặc thread có thể ảnh hưởng lẫn nhau.

Ưu tiên processor stateless:

```java
public class NormalizeCodeProcessor
        implements ItemProcessor<OrderInput, NormalizedOrder> {

    @Override
    public NormalizedOrder process(OrderInput input) {
        return new NormalizedOrder(
            input.orderId().trim().toUpperCase(Locale.ROOT),
            input.customerCode().trim().toUpperCase(Locale.ROOT),
            input.amount()
        );
    }
}
```

Nếu cần cache, hãy dùng cấu trúc thread-safe hoặc cache có lifecycle/eviction rõ ràng. Không dùng field `currentItem`, `currentIndex` hoặc biến tạm dùng chung giữa các lời gọi.

## 14. Composite processor không chạy song song

Composite gọi delegate lần lượt trong cùng lời gọi `process`. Ba delegate không được chạy đồng thời chỉ vì chúng được khai báo trong danh sách.

Nếu cần concurrency, đó là quyết định ở kiến trúc step như multi-threaded step hoặc partitioning. Khi đó phải kiểm tra thread safety của từng delegate và các service mà chúng dùng.

Không dùng composite như một cách parallelize enrichment. Nếu hai tác vụ độc lập cần chạy song song, cân nhắc một processor chuyên biệt dùng executor có giới hạn và timeout, nhưng cần kiểm soát transaction context, lỗi, cancellation và resource.

## 15. Enrichment và hiệu năng database

Delegate enrichment thường tra cứu database hoặc service. Nếu mỗi item tạo một query, pipeline có thể gặp N+1 lookup và throughput giảm mạnh.

Các cách tối ưu:

- Cache reference data nhỏ và ổn định trong một cache thread-safe.
- Bulk lookup theo chunk nếu kiến trúc cho phép.
- Đưa reference data vào một bảng/staging hoặc join ở query reader.
- Dùng index phù hợp cho lookup key.
- Đặt timeout và phân loại lỗi transient cho remote lookup.

Không cache dữ liệu thay đổi liên tục mà không có TTL/version phù hợp. Nếu kết quả enrichment phải nhất quán trong một job, hãy xác định snapshot hoặc version của reference data.

## 16. Dùng ValidatingItemProcessor trong chain

Spring Batch cung cấp `ValidatingItemProcessor<T>` để tích hợp validator vào pipeline. Có thể dùng `setFilter(true)` nếu muốn validation failure được chuyển thành filter theo contract của processor; mặc định, validation failure thường được ném ra dưới dạng exception.

Ví dụ:

```java
@Bean
ValidatingItemProcessor<OrderInput> orderValidationProcessor(
        Validator<OrderInput> validator) {

    ValidatingItemProcessor<OrderInput> processor =
        new ValidatingItemProcessor<>(validator);
    processor.setFilter(false);
    return processor;
}
```

Chỉ bật filter khi validation failure thực sự có nghĩa item được loại bỏ theo nghiệp vụ. Nếu cần reject record và lưu lý do, dùng exception/skip listener hoặc một luồng reject riêng.

## 17. Composite processor và ClassifierCompositeItemProcessor

Hai component có mục tiêu khác nhau:

| Component | Hành vi | Khi dùng |
|---|---|---|
| `CompositeItemProcessor` | Gọi tất cả delegate theo thứ tự, truyền output sang delegate tiếp theo | Nhiều bước xử lý tuần tự cho cùng item |
| `ClassifierCompositeItemProcessor` | Chọn một processor theo classifier cho item | Các loại item đi theo những nhánh xử lý khác nhau |

Ví dụ chain:

```text
input -> validate -> normalize -> enrich -> output
```

Ví dụ routing:

```text
                 +--> priorityProcessor --+
input -> classify|                       +--> output
                 +--> standardProcessor -+
```

Không dùng `CompositeItemProcessor` để mô phỏng routing bằng các delegate có điều kiện tự trả nguyên item. Nếu chỉ một nhánh cần chạy, classifier composite diễn đạt ý định rõ hơn.

## 18. Kết hợp routing và chaining

Có thể dùng classifier để chọn một composite pipeline phù hợp theo loại item. Mỗi nhánh là một chuỗi delegate riêng.

Ví dụ về ý tưởng:

```text
OrderInput
   |
   v
Classifier
   |
   +--> Retail pipeline: validate -> normalize -> enrich retail
   |
   +--> Wholesale pipeline: validate -> normalize -> enrich wholesale
   |
   +--> Internal pipeline: validate -> map internal
```

Giữ kiểu input/output chung ở ranh giới các nhánh để writer có thể nhận một contract thống nhất. Nếu các nhánh trả kiểu khác nhau, thêm một bước mapping cuối để chuyển về output type chung.

## 19. Kiểm thử từng delegate độc lập

Mỗi processor nên có unit test cho contract riêng trước khi kiểm thử chain.

Ví dụ test normalization:

```java
@Test
void normalizesOrderCodes() {
    var processor = new OrderNormalizationProcessor();
    var input = new ValidatedOrder(
        " ord-1 ", " cust-a ", new BigDecimal("10"));

    NormalizedOrder result = processor.process(input);

    assertThat(result.orderId()).isEqualTo("ORD-1");
    assertThat(result.customerCode()).isEqualTo("CUST-A");
    assertThat(result.amount()).isEqualByComparingTo("10.00");
}
```

Test riêng giúp xác định lỗi nằm ở validation, normalization hay enrichment thay vì chỉ biết composite trả kết quả sai.

## 20. Kiểm thử thứ tự delegate trong composite

Test chain nên xác nhận output cuối cùng và thứ tự gọi delegate. Có thể dùng processor thật hoặc mock với `InOrder`.

```java
@Test
void invokesDelegatesInConfiguredOrder() throws Exception {
    ItemProcessor<OrderInput, ValidatedOrder> validate =
        input -> new ValidatedOrder(
            input.orderId(), input.customerCode(), input.amount());

    ItemProcessor<ValidatedOrder, NormalizedOrder> normalize =
        order -> new NormalizedOrder(
            order.orderId().toUpperCase(Locale.ROOT),
            order.customerCode(),
            order.amount());

    ItemProcessor<NormalizedOrder, EnrichedOrder> enrich =
        order -> new EnrichedOrder(
            order.orderId(), 42L, order.amount(), "LOW");

    CompositeItemProcessor<OrderInput, EnrichedOrder> composite =
        new CompositeItemProcessorBuilder<OrderInput, EnrichedOrder>()
            .delegates(validate, normalize, enrich)
            .build();

    EnrichedOrder result = composite.process(
        new OrderInput("ord-1", "C-1", new BigDecimal("5.00")));

    assertThat(result.orderId()).isEqualTo("ORD-1");
    assertThat(result.customerId()).isEqualTo(42L);
}
```

Test trên dùng lambda để tập trung vào việc truyền output giữa các bước. Trong test đầy đủ, có thể mock từng delegate để verify thứ tự gọi và tham số nhận được.

## 21. Kiểm thử null short-circuit

Cần xác nhận khi delegate trả `null`, delegate sau không được gọi và composite trả `null`.

```java
@Test
void stopsChainWhenDelegateFiltersItem() throws Exception {
    AtomicBoolean laterDelegateCalled = new AtomicBoolean(false);

    ItemProcessor<OrderInput, ValidatedOrder> filter = input -> null;
    ItemProcessor<ValidatedOrder, EnrichedOrder> later = order -> {
        laterDelegateCalled.set(true);
        return new EnrichedOrder(
            order.orderId(), 1L, order.amount(), "LOW");
    };

    CompositeItemProcessor<OrderInput, EnrichedOrder> composite =
        new CompositeItemProcessorBuilder<OrderInput, EnrichedOrder>()
            .delegates(filter, later)
            .build();

    assertThat(composite.process(
        new OrderInput("O-1", "C-1", BigDecimal.ONE)))
        .isNull();
    assertThat(laterDelegateCalled).isFalse();
}
```

Test này bảo đảm filtering không vô tình gọi enrichment hoặc side effect phía sau.

## 22. Kiểm thử exception propagation

Nếu delegate ném exception, composite phải truyền lỗi ra caller và không gọi các bước sau.

```java
@Test
void stopsChainWhenDelegateThrows() {
    ItemProcessor<OrderInput, ValidatedOrder> failing = input -> {
        throw new InvalidOrderException("invalid order");
    };

    ItemProcessor<ValidatedOrder, EnrichedOrder> later = order -> {
        throw new AssertionError("must not be called");
    };

    CompositeItemProcessor<OrderInput, EnrichedOrder> composite =
        new CompositeItemProcessorBuilder<OrderInput, EnrichedOrder>()
            .delegates(failing, later)
            .build();

    assertThatThrownBy(() -> composite.process(
        new OrderInput("O-1", "C-1", BigDecimal.ONE)))
        .isInstanceOf(InvalidOrderException.class);
}
```

Ở integration test, kiểm tra exception này được step phân loại đúng thành fail, skip hoặc retry theo cấu hình.

## 23. Kiểm thử composite trong step

Unit test composite không xác nhận filter count, skip count hoặc transaction của step. Nên có integration test với reader, composite processor và writer thật hoặc fixture kiểm soát được.

Các assertion hữu ích:

- Số item đọc.
- Số item được filter do processor trả `null`.
- Số item ghi.
- Số item bị skip và exception cause.
- Dữ liệu output cuối cùng.
- Số lần delegate enrichment được gọi khi có retry.
- Transaction rollback khi writer thất bại.

Ví dụ một item bị filter không nên xuất hiện trong writer output, còn item hợp lệ phải đi qua đủ delegate.

## 24. Delegate có side effect và retry

Processor lý tưởng chỉ biến đổi item. Nếu delegate gửi email, ghi database độc lập hoặc gọi API, retry có thể thực hiện side effect nhiều lần.

Ví dụ enrichment gọi dịch vụ đối tác có thể bị timeout sau khi đối tác đã xử lý request. Spring Batch retry item, và cùng request có thể được gửi lại.

Các biện pháp:

- Dùng idempotency key dựa trên business ID của item.
- Ưu tiên đọc dữ liệu và tính toán trong processor, để writer thực hiện thay đổi transactional.
- Dùng outbox để ghi sự kiện trong cùng transaction database, publish sau commit.
- Phân loại timeout/exception để quyết định retry có an toàn không.
- Giữ số lần retry và backoff có giới hạn.

Không giả định transaction chunk có thể rollback HTTP request hoặc message đã gửi.

## 25. Composite processor và partitioning

Khi step chạy partitioned hoặc multi-threaded, cùng một processor bean có thể được gọi từ nhiều thread tùy cách cấu hình. Composite không tự đồng bộ state cho delegate.

Đảm bảo:

- Delegate stateless hoặc thread-safe.
- Cache dùng chung là thread-safe và có chính sách cập nhật rõ.
- Không giữ item hiện tại trong field mutable.
- Không chia sẻ EntityManager, JDBC Connection hoặc parser không thread-safe.
- Lookup service có connection pool và timeout phù hợp.

Nếu một delegate cần state riêng theo worker, thiết kế scope và lifecycle phù hợp; đừng đặt state của partition vào singleton processor.

## 26. Logging và quan sát pipeline

Khi chain có nhiều bước, log nên cho biết item key và bước xử lý đang gặp lỗi. Tránh log toàn bộ payload nếu có dữ liệu cá nhân hoặc nhạy cảm.

Có thể dùng metric/counter riêng cho:

- Số item vào validation và số item bị từ chối.
- Số item đã normalize.
- Số lookup thành công/thất bại.
- Thời gian trung bình của từng delegate.
- Số retry/skip theo exception category.

Không thêm side effect vào processor chỉ để đếm nếu nó làm metric bị đếm lặp khi retry. Dùng metrics có semantics rõ hoặc listener phù hợp với lifecycle.

## 27. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cấu hình sai thứ tự delegate | Bước sau nhận dữ liệu chưa chuẩn hóa | Sắp thứ tự theo dependency và test chain |
| Mismatch kiểu trung gian | Lỗi compile bị bỏ lọt hoặc ClassCastException runtime | Khai báo generic cụ thể cho từng delegate |
| Delegate trả `null` ngoài ý muốn | Item bị filter và không tới writer | Chỉ dùng null cho filtering có chủ đích |
| Bắt exception rồi trả null | Lỗi dữ liệu/hạ tầng bị che thành filter | Ném exception có phân loại rõ |
| Một processor làm quá nhiều việc | Khó test và thay đổi | Chia theo trách nhiệm có ý nghĩa |
| Delegate giữ mutable state | Kết quả item phụ thuộc thứ tự hoặc thread | Dùng processor stateless/thread-safe |
| Lookup một query mỗi item | N+1 và throughput thấp | Bulk lookup, cache hoặc join |
| Side effect trong processor không idempotent | Retry tạo hành động trùng | Outbox/idempotency hoặc chuyển side effect |
| Dùng chain khi chỉ cần một nhánh | Chạy các bước không liên quan | Dùng classifier composite |
| Nghĩ composite chạy song song | Hiểu sai concurrency | Composite chạy delegate tuần tự |
| Chỉ test composite output | Không phát hiện delegate sau vẫn chạy sau null/error | Test short-circuit và exception |

## 28. Quy trình thiết kế composite processor

Khi thiết kế pipeline, hãy xác định:

1. Input type và output type cuối cùng của processor là gì?
2. Các bước nghiệp vụ có thể tách thành những trách nhiệm độc lập nào?
3. Kiểu dữ liệu trung gian giữa mỗi delegate là gì?
4. Thứ tự delegate phụ thuộc dữ liệu nào?
5. Trường hợp nào filter bằng `null`, trường hợp nào phải ném exception?
6. Delegate nào có I/O, lookup hoặc side effect?
7. Retry có thể gọi lại delegate nào và side effect có idempotent không?
8. Processor có thể được gọi đồng thời trong partition/multi-threaded step không?
9. Có cần chain tất cả bước hay chỉ chọn một nhánh bằng classifier?
10. Unit test có kiểm tra thứ tự, null, exception và integration test có xác nhận step counters/output không?

## Kết luận

`CompositeItemProcessor<I, O>` nối nhiều `ItemProcessor` thành một pipeline tuần tự. Mỗi delegate nhận output của bước trước; delegate trả `null` sẽ filter item và dừng chain, còn exception được truyền lên step để áp dụng retry/skip/rollback policy.

Hãy khai báo kiểu dữ liệu trung gian rõ ràng, giữ mỗi delegate tập trung một trách nhiệm, cấu hình thứ tự có chủ đích và dùng `CompositeItemProcessorBuilder` trong Spring Batch 5. Composite không chạy song song và không tự làm side effect idempotent. Kiểm thử từng delegate, toàn bộ chain, null short-circuit, exception propagation và hành vi của step để bảo đảm pipeline hoạt động đúng.

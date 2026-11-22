# Chain processor theo thứ tự

Trong Spring Batch, một item đôi khi cần đi qua nhiều bước biến đổi trước khi được ghi. Ví dụ, dữ liệu thô cần được chuẩn hóa, bổ sung thông tin tham chiếu, kiểm tra quy tắc nghiệp vụ rồi chuyển thành DTO dành cho hệ thống đích. Có thể triển khai toàn bộ logic trong một `ItemProcessor`, nhưng khi các bước có trách nhiệm riêng, `CompositeItemProcessor` giúp ghép nhiều processor thành một chuỗi có thứ tự.

`CompositeItemProcessor<I, O>` gọi các delegate lần lượt. Output của processor trước trở thành input của processor kế tiếp. Chuỗi kết thúc khi delegate cuối cùng tạo ra output `O`, hoặc sớm hơn nếu một delegate trả về `null` để filter item. Đây là xử lý tuần tự trên từng item; nó không fan-out một item đến nhiều nhánh và cũng không chạy các delegate song song.

## 1. Khi nào cần chain processor?

Một pipeline xử lý đơn hàng có thể gồm các bước:

1. Chuẩn hóa mã, khoảng trắng và định dạng đầu vào.
2. Tra cứu thông tin khách hàng hoặc dữ liệu tham chiếu.
3. Tính toán giá trị dẫn xuất.
4. Kiểm tra điều kiện nghiệp vụ.
5. Chuyển thành object phù hợp với writer.

Nếu đặt tất cả trong một processor lớn, class đó dễ có nhiều trách nhiệm và khó kiểm thử từng bước. Tách thành các processor nhỏ giúp mỗi bước có một đầu vào, đầu ra và mục đích rõ ràng.

Ví dụ sơ đồ:

```text
RawOrder
   |
   v
NormalizeProcessor
   |
   v
NormalizedOrder
   |
   v
EnrichProcessor
   |
   v
EnrichedOrder
   |
   v
ExportMappingProcessor
   |
   v
OrderExport
```

Chuỗi processor hữu ích khi:

- Các bước biến đổi có thứ tự phụ thuộc rõ ràng.
- Output của bước này là input của bước tiếp theo.
- Muốn tái sử dụng một processor trong nhiều Job/Step.
- Muốn unit test từng bước mà không cần chạy cả Job.
- Muốn tách logic chuẩn hóa, enrichment, validation và mapping.

Nếu chỉ có một phép biến đổi đơn giản, một `ItemProcessor` là đủ. Không cần tạo composite chỉ để bọc một processor duy nhất.

## 2. CompositeItemProcessor hoạt động như thế nào?

`CompositeItemProcessor<I, O>` là implementation của `ItemProcessor<I, O>`. Nó giữ danh sách delegate processor và thực thi theo thứ tự danh sách.

Với một item `x`, hành vi khái niệm là:

```text
result = x

for each delegate in configured order:
    if result is null:
        stop and return null
    result = delegate.process(result)

return result
```

Điều quan trọng là mỗi delegate nhận kết quả mới nhất, không nhận lại item ban đầu. Nếu delegate đầu biến `RawOrder` thành `NormalizedOrder`, delegate thứ hai phải nhận `NormalizedOrder`.

Composite không tự đoán cách chuyển đổi kiểu. Các delegate cần có hợp đồng kiểu dữ liệu tương thích với nhau.

## 3. Ví dụ ba processor nối tiếp

Giả sử Job đọc dữ liệu đơn hàng thô và cần tạo object xuất dữ liệu:

```java
public record RawOrder(
        String orderId,
        String customerCode,
        String amountText) {
}

public record NormalizedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

public record EnrichedOrder(
        String orderId,
        Customer customer,
        BigDecimal amount,
        BigDecimal taxRate) {
}

public record OrderExport(
        String orderId,
        String customerName,
        BigDecimal amount,
        BigDecimal tax) {
}
```

Mỗi processor chỉ thực hiện một bước:

```java
ItemProcessor<RawOrder, NormalizedOrder> normalizeProcessor = raw -> {
    String orderId = raw.orderId().trim();
    String customerCode = raw.customerCode().trim().toUpperCase(Locale.ROOT);
    BigDecimal amount = new BigDecimal(raw.amountText().trim());

    return new NormalizedOrder(orderId, customerCode, amount);
};

ItemProcessor<NormalizedOrder, EnrichedOrder> enrichProcessor = order -> {
    Customer customer = customerService.findByCode(order.customerCode());
    BigDecimal taxRate = taxService.rateFor(customer.region());

    return new EnrichedOrder(
            order.orderId(), customer, order.amount(), taxRate);
};

ItemProcessor<EnrichedOrder, OrderExport> exportMappingProcessor = order -> {
    BigDecimal tax = order.amount().multiply(order.taxRate());

    return new OrderExport(
            order.orderId(),
            order.customer().name(),
            order.amount(),
            tax);
};
```

Kết quả của `normalizeProcessor` được truyền vào `enrichProcessor`; kết quả enrichment tiếp tục được truyền vào `exportMappingProcessor`.

## 4. Cấu hình CompositeItemProcessorBuilder

Spring Batch cung cấp `CompositeItemProcessorBuilder` để cấu hình chuỗi:

```java
@Bean
ItemProcessor<RawOrder, OrderExport> orderCompositeProcessor(
        ItemProcessor<RawOrder, NormalizedOrder> normalizeProcessor,
        ItemProcessor<NormalizedOrder, EnrichedOrder> enrichProcessor,
        ItemProcessor<EnrichedOrder, OrderExport> exportMappingProcessor) {

    return new CompositeItemProcessorBuilder<RawOrder, OrderExport>()
            .delegates(List.of(
                    normalizeProcessor,
                    enrichProcessor,
                    exportMappingProcessor))
            .build();
}
```

`delegates(...)` nhận danh sách processor theo thứ tự cần thực thi. `List.of(...)` tạo một danh sách có thứ tự xác định, giúp cấu hình dễ đọc và tránh vô tình thay đổi thứ tự trong lúc khởi tạo.

Nếu ứng dụng dùng cấu hình builder trực tiếp thay vì bean method, nguyên tắc vẫn giống nhau: khai báo input type của composite, output type cuối cùng và danh sách delegate đúng thứ tự.

## 5. Đưa composite vào Step

Composite là một `ItemProcessor` nên được gắn vào Step như processor thông thường:

```java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawOrder> orderReader,
        ItemProcessor<RawOrder, OrderExport> orderCompositeProcessor,
        ItemWriter<OrderExport> orderWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<RawOrder, OrderExport>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderCompositeProcessor)
            .writer(orderWriter)
            .build();
}
```

Step chỉ cần biết kiểu đầu vào `RawOrder` và kiểu đầu ra `OrderExport`. Các kiểu trung gian được xử lý bên trong chuỗi delegate.

Không cần tạo Step riêng cho từng phép biến đổi nếu các bước chỉ là những phép biến đổi trên cùng một item và không cần commit/checkpoint riêng. Dùng nhiều Step khi có ranh giới nghiệp vụ, transaction, restart hoặc tài nguyên độc lập cần quản lý riêng.

## 6. Thứ tự delegate quyết định kết quả

Thứ tự trong danh sách là thứ tự thực thi. Không thể đổi chỗ tùy ý nếu một processor phụ thuộc output của processor trước.

Ví dụ:

```text
RawOrder
   |
   v
Normalize amount text
   |
   v
Parse BigDecimal
   |
   v
Calculate tax
```

Nếu tính thuế trước khi parse số tiền, processor không có giá trị `BigDecimal` để thực hiện phép tính. Nếu enrichment cần customer code đã chuẩn hóa, normalize phải chạy trước enrichment.

Hãy đặt tên delegate theo hành động và thể hiện thứ tự trong cấu hình. Tránh lấy thứ tự từ một cấu trúc không bảo đảm iteration order, ví dụ map không có quy tắc thứ tự rõ ràng.

### Không nên tạo thứ tự ngầm từ dependency injection

Nếu inject một collection processor từ Spring context, thứ tự có thể phụ thuộc cách Spring sắp xếp bean hoặc annotation `@Order`. Với pipeline nghiệp vụ quan trọng, cấu hình danh sách tường minh giúp người đọc nhận ra chuỗi xử lý ngay tại nơi composite được tạo.

Nếu dự án chủ ý dùng `@Order`, hãy quy định thứ tự bằng convention, kiểm thử danh sách delegate và tránh để một bean mới vô tình thay đổi pipeline.

## 7. Kiểu dữ liệu giữa các processor phải khớp

Mỗi delegate có kiểu `ItemProcessor<I, O>`. Output `O` của bước trước phải tương thích với input `I` của bước sau.

| Delegate | Input | Output |
|---|---|---|
| `normalizeProcessor` | `RawOrder` | `NormalizedOrder` |
| `enrichProcessor` | `NormalizedOrder` | `EnrichedOrder` |
| `exportMappingProcessor` | `EnrichedOrder` | `OrderExport` |
| Composite | `RawOrder` | `OrderExport` |

Khai báo generic rõ ràng giúp compiler phát hiện nhiều lỗi kiểu trước khi Job chạy. Tuy nhiên, danh sách delegate của composite dùng wildcard generic, nên compiler không phải lúc nào cũng chứng minh được mọi cặp input/output trung gian trong danh sách. Hãy khai báo biến processor với kiểu cụ thể và kiểm thử toàn chuỗi.

Không ép kiểu raw hoặc dùng `ItemProcessor` không generic để né lỗi compile. Cách đó chuyển lỗi kiểu sang runtime, thường khó điều tra hơn khi Job đã xử lý một phần dữ liệu.

## 8. Delegate trả về null: dừng chuỗi và filter item

Theo hợp đồng `ItemProcessor`, trả về `null` nghĩa là item không được chuyển tiếp đến writer. Với `CompositeItemProcessor`, nếu một delegate trả `null`, composite dừng chuỗi cho item đó và trả `null`; các delegate phía sau không được gọi cho item này.

Ví dụ:

```java
ItemProcessor<NormalizedOrder, EnrichedOrder> filterInvalidOrder = order -> {
    if (order.amount().signum() <= 0) {
        return null;
    }
    return enrich(order);
};
```

Nếu delegate này trả `null`, `exportMappingProcessor` không chạy. Item được filter khỏi pipeline và không được gửi đến writer.

Điều này khác với ném exception:

- `return null`: filter item theo quyết định của processor.
- `throw exception`: báo lỗi; Step áp dụng rollback, retry, skip hoặc fail theo cấu hình.

Không trả `null` để che lỗi hệ thống như timeout database hoặc service không khả dụng. `null` nên biểu thị một quyết định nghiệp vụ có chủ đích.

## 9. Kiểm tra dữ liệu ở từng giai đoạn

Một chain tốt đặt mỗi quy tắc ở giai đoạn phù hợp:

- Normalize: chuẩn hóa định dạng và giá trị đầu vào.
- Parse: chuyển chuỗi sang kiểu domain, báo lỗi nếu không thể parse.
- Enrich: lấy dữ liệu tham chiếu hoặc bổ sung thông tin.
- Validate: kiểm tra các invariant nghiệp vụ.
- Map: tạo output DTO.

Không nhất thiết phải có một processor cho từng bước nhỏ. Nếu hai thao tác luôn đi cùng nhau, có cùng trách nhiệm và không cần tái sử dụng riêng, có thể gộp chúng. Mục tiêu là tách các bước có ý nghĩa, không tạo quá nhiều class vụn.

Ví dụ validator:

```java
ItemProcessor<EnrichedOrder, EnrichedOrder> validateOrder = order -> {
    if (order.customer() == null) {
        throw new InvalidOrderException("Customer is required");
    }
    if (order.amount().signum() <= 0) {
        throw new InvalidOrderException("Amount must be positive");
    }
    return order;
};
```

Validator có thể trả lại cùng object nếu hợp lệ. Nó không bắt buộc phải tạo object mới, nhưng tránh mutate object dùng chung nếu điều đó gây side effect ngoài ý muốn.

## 10. Xử lý exception trong chain

Nếu một delegate ném exception, `CompositeItemProcessor` không tiếp tục gọi các delegate sau cho item đó; exception được truyền ra ngoài. Spring Batch xử lý exception ở cấp Step theo retry/skip/rollback policy.

Ví dụ:

```text
RawOrder
   |
   v
NormalizeProcessor       thành công
   |
   v
EnrichProcessor          ném ServiceUnavailableException
   |
   X
ExportMappingProcessor   không được gọi
```

Các nguyên tắc:

- Không bắt exception trong delegate rồi trả về object giả để chain tiếp tục.
- Giữ cause chain khi wrap exception.
- Phân biệt lỗi dữ liệu cố định với lỗi transient.
- Đặt retry policy cho exception có khả năng phục hồi.
- Chỉ skip exception khi nghiệp vụ cho phép bỏ item.
- Không dùng `null` thay cho exception cần được điều tra.

Nếu một delegate gọi service ngoài, cấu hình timeout và retry ở đúng tầng. Processor có thể được gọi lại cho cùng item khi chunk retry; lời gọi ngoài phải an toàn khi lặp hoặc chỉ đọc dữ liệu.

## 11. Retry và skip áp dụng cho toàn chuỗi

Với Step dùng `CompositeItemProcessor`, Spring Batch nhìn thấy một processor ở cấp Step. Nếu một delegate bên trong ném exception, Step nhận exception đó và áp dụng policy đã cấu hình.

Ví dụ:

```java
return new StepBuilder("exportOrdersStep", jobRepository)
        .<RawOrder, OrderExport>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(orderCompositeProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(ServiceUnavailableException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
```

Trong ví dụ, lỗi service tạm thời có thể được retry; lỗi dữ liệu được phép skip trong giới hạn. Nếu lỗi xuất hiện ở `normalizeProcessor`, `enrichProcessor` hoặc `exportMappingProcessor`, exception type vẫn là căn cứ để policy quyết định.

Nếu cần policy khác nhau cho từng bước, có thể dùng exception type riêng hoặc cấu hình `RetryPolicy`/`SkipPolicy` có phân loại. Không nên dựa vào vị trí delegate hoặc message exception để phân loại nếu có thể dùng class exception rõ ràng.

## 12. Processor chain không phải fan-out

`CompositeItemProcessor` là chuỗi tuần tự: output của delegate trước đi vào delegate sau. Nó không gửi cùng item ban đầu đến nhiều processor độc lập.

| Mẫu | Hành vi |
|---|---|
| `CompositeItemProcessor` | Nối tiếp: A → B → C. |
| Routing/classifier processor | Chọn một processor phù hợp theo điều kiện. |
| Fan-out tùy chỉnh | Một input tạo nhiều output/nhánh độc lập theo thiết kế riêng. |
| `CompositeItemWriter` | Gửi cùng item/chunk đến nhiều writer. |

Ví dụ, nếu một đơn hàng cần vừa tính báo cáo thuế vừa tạo thông điệp thông báo, không nên đặt hai processor độc lập nối tiếp nếu cả hai cần cùng input và tạo hai kết quả khác nhau. Hãy tạo một processor trả về object kết hợp, dùng routing phù hợp hoặc thiết kế fan-out ở tầng xử lý khác.

Không nhầm `CompositeItemProcessor` với `CompositeItemWriter`: một cái biến đổi item qua chuỗi, cái kia phối hợp các writer.

## 13. So sánh với ClassifierCompositeItemProcessor

Nếu cần chọn một processor dựa trên loại item hoặc điều kiện, `ClassifierCompositeItemProcessor` phù hợp hơn chain cố định. Ví dụ, giao dịch `CARD` đi qua processor thẻ, giao dịch `BANK` đi qua processor ngân hàng.

```text
Transaction
    |
    v
Classifier
    |
    +---- CARD ----> CardProcessor
    |
    +---- BANK ----> BankTransferProcessor
```

Trong khi đó, chain luôn chạy theo cùng một thứ tự delegate:

```text
Transaction
    |
    v
Normalize
    |
    v
Enrich
    |
    v
Validate
```

Có thể kết hợp hai mẫu nếu cần: một bước trong chain là classifier chọn processor chuyên biệt, sau đó kết quả tiếp tục qua các bước chung. Chỉ kết hợp khi flow thực sự cần, vì nhiều tầng routing có thể làm khó theo dõi.

## 14. Đăng ký delegate thành bean riêng

Trong ứng dụng Spring, mỗi delegate có thể là một bean riêng để dễ tái sử dụng và kiểm thử:

```java
@Bean
ItemProcessor<RawOrder, NormalizedOrder> normalizeProcessor() {
    return raw -> new NormalizedOrder(
            raw.orderId().trim(),
            raw.customerCode().trim().toUpperCase(Locale.ROOT),
            new BigDecimal(raw.amountText().trim()));
}

@Bean
ItemProcessor<NormalizedOrder, EnrichedOrder> enrichProcessor(
        CustomerService customerService,
        TaxService taxService) {
    return order -> {
        Customer customer = customerService.findByCode(order.customerCode());
        BigDecimal rate = taxService.rateFor(customer.region());
        return new EnrichedOrder(
                order.orderId(), customer, order.amount(), rate);
    };
}

@Bean
ItemProcessor<EnrichedOrder, OrderExport> exportMappingProcessor() {
    return order -> new OrderExport(
            order.orderId(),
            order.customer().name(),
            order.amount(),
            order.amount().multiply(order.taxRate()));
}
```

Composite bean nhận các delegate đã được Spring quản lý:

```java
@Bean
ItemProcessor<RawOrder, OrderExport> orderCompositeProcessor(
        ItemProcessor<RawOrder, NormalizedOrder> normalizeProcessor,
        ItemProcessor<NormalizedOrder, EnrichedOrder> enrichProcessor,
        ItemProcessor<EnrichedOrder, OrderExport> exportMappingProcessor) {

    return new CompositeItemProcessorBuilder<RawOrder, OrderExport>()
            .delegates(List.of(
                    normalizeProcessor,
                    enrichProcessor,
                    exportMappingProcessor))
            .build();
}
```

Nếu có nhiều bean cùng generic type hoặc cùng interface, dùng `@Qualifier` để injection không mơ hồ. Đặt tên bean phản ánh trách nhiệm và giữ thứ tự danh sách tường minh.

## 15. StepScope và JobParameters trong delegate

Một delegate có thể cần JobParameters, ví dụ tenant ID, business date hoặc chế độ chạy. Khi đó, delegate có thể được khai báo `@StepScope`:

```java
@Bean
@StepScope
ItemProcessor<NormalizedOrder, EnrichedOrder> enrichProcessor(
        CustomerService customerService,
        TaxService taxService,
        @Value("#{jobParameters['tenant.id']}") Long tenantId) {

    return order -> {
        Customer customer = customerService.findByTenantAndCode(
                tenantId, order.customerCode());
        BigDecimal rate = taxService.rateFor(customer.region());
        return new EnrichedOrder(
                order.orderId(), customer, order.amount(), rate);
    };
}
```

`@StepScope` giúp giá trị được resolve theo StepExecution hiện tại. Nếu delegate không phụ thuộc execution và không giữ state mutable, singleton thường đơn giản hơn.

Không lưu state của từng item vào field của singleton processor. Với multi-threaded Step hoặc nhiều Job chạy đồng thời, field mutable có thể bị các execution ghi đè lẫn nhau.

## 16. Stateless và thread safety

Processor thường nên càng gần pure function càng tốt: nhận một object, trả về object mới và không thay đổi trạng thái dùng chung. Điều này giúp chain an toàn khi retry và dễ chạy đồng thời.

Nếu Step chạy nhiều thread hoặc partition workers, cần kiểm tra tất cả delegate:

- Delegate có dùng mutable field dùng chung không?
- Service được inject có thread-safe không?
- Cache có cơ chế đồng bộ và giới hạn kích thước không?
- Có giữ `currentItem`, counter hoặc buffer trong field không?
- Có gọi API ngoài với rate limit hoặc connection pool phù hợp không?

Composite không tự tuần tự hóa các lần gọi. Nếu nhiều thread gọi cùng composite bean, các delegate có thể được gọi đồng thời. Dùng processor stateless hoặc scope riêng theo StepExecution; không giả định chain tự tạo một instance cho mỗi item.

## 17. Side effect trong chain

Processor có thể được gọi lại khi retry hoặc khi chunk rollback được xử lý. Vì vậy, delegate nên tránh side effect không idempotent như gửi email, thu tiền hoặc publish message.

Các lựa chọn an toàn hơn:

- Chỉ đọc dữ liệu tham chiếu trong enrichment.
- Tạo command/event object thay vì gửi ngay.
- Ghi ý định vào outbox trong transaction của chunk.
- Dùng idempotency key ổn định nếu phải gọi API có tác dụng phụ.
- Đưa side effect sang writer/Step riêng có transaction và recovery strategy rõ ràng.

Nếu delegate gọi API đọc và timeout, retry có thể gọi lại request; vẫn cần timeout và giới hạn retry. Nếu API thay đổi trạng thái, outcome timeout có thể không rõ và phải có idempotency/status lookup.

## 18. Logging và theo dõi từng delegate

Ở cấp Step, `ItemProcessListener` quan sát một lần gọi processor được cấu hình. Nếu processor đó là `CompositeItemProcessor`, listener bao quanh toàn bộ chain; nó không tự tạo callback riêng cho từng delegate bên trong.

Nếu cần đo thời gian từng bước, có thể:

- Bọc từng delegate bằng decorator đo thời gian.
- Ghi metric trong từng processor.
- Dùng tracing span riêng cho từng thao tác enrichment/validation.
- Dùng log có tên bước và business correlation ID.

Không log toàn bộ payload nhạy cảm ở mỗi bước. Metric tag nên có cardinality thấp, ví dụ `processor=normalize` hoặc `processor=enrich`, tránh dùng order ID làm tag.

## 19. Kiểm thử từng processor độc lập

Vì mỗi delegate có trách nhiệm riêng, hãy unit test từng processor:

- Normalize: khoảng trắng, chữ hoa/thường, định dạng số.
- Enrich: dữ liệu tham chiếu tồn tại, không tồn tại và service lỗi.
- Validate: trường hợp hợp lệ và vi phạm invariant.
- Mapping: output field, kiểu dữ liệu và giá trị dẫn xuất.

Ví dụ test normalize:

```java
@Test
void normalizesOrderFields() throws Exception {
    ItemProcessor<RawOrder, NormalizedOrder> processor = raw ->
            new NormalizedOrder(
                    raw.orderId().trim(),
                    raw.customerCode().trim().toUpperCase(Locale.ROOT),
                    new BigDecimal(raw.amountText().trim()));

    NormalizedOrder result = processor.process(
            new RawOrder(" O-1001 ", " c001 ", " 250.00 "));

    assertThat(result.orderId()).isEqualTo("O-1001");
    assertThat(result.customerCode()).isEqualTo("C001");
    assertThat(result.amount()).isEqualByComparingTo("250.00");
}
```

Unit test từng delegate giúp xác định lỗi thuộc bước nào, thay vì chỉ biết toàn bộ composite trả sai kết quả.

## 20. Kiểm thử thứ tự thực thi

Có thể dùng Mockito `InOrder` để xác nhận delegate được gọi theo đúng thứ tự:

```java
@Test
void delegatesAreInvokedInConfiguredOrder() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<RawOrder, NormalizedOrder> normalize = mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<NormalizedOrder, EnrichedOrder> enrich = mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<EnrichedOrder, OrderExport> map = mock(ItemProcessor.class);

    RawOrder raw = new RawOrder("O-1", "C-1", "10.00");
    NormalizedOrder normalized = new NormalizedOrder(
            "O-1", "C-1", new BigDecimal("10.00"));
    EnrichedOrder enriched = new EnrichedOrder(
            "O-1", new Customer("C-1", "Lan", "VN"),
            new BigDecimal("10.00"), new BigDecimal("0.1"));
    OrderExport expected = new OrderExport(
            "O-1", "Lan", new BigDecimal("10.00"), new BigDecimal("1.00"));

    when(normalize.process(raw)).thenReturn(normalized);
    when(enrich.process(normalized)).thenReturn(enriched);
    when(map.process(enriched)).thenReturn(expected);

    ItemProcessor<RawOrder, OrderExport> composite =
            new CompositeItemProcessorBuilder<RawOrder, OrderExport>()
                    .delegates(List.of(normalize, enrich, map))
                    .build();

    assertThat(composite.process(raw)).isEqualTo(expected);

    InOrder order = inOrder(normalize, enrich, map);
    order.verify(normalize).process(raw);
    order.verify(enrich).process(normalized);
    order.verify(map).process(enriched);
}
```

Các model và constructor trong ví dụ là fixture test minh họa. Test cần xác nhận delegate sau nhận đúng output của delegate trước, không chỉ xác nhận cả ba mock đã được gọi.

## 21. Kiểm thử filter và exception propagation

Một test quan trọng là xác nhận `null` dừng chain:

```java
@Test
void nullFromDelegateStopsRemainingProcessors() throws Exception {
    ItemProcessor<RawOrder, NormalizedOrder> normalize = raw -> null;
    ItemProcessor<NormalizedOrder, OrderExport> map = mock(ItemProcessor.class);

    ItemProcessor<RawOrder, OrderExport> composite =
            new CompositeItemProcessorBuilder<RawOrder, OrderExport>()
                    .delegates(List.of(normalize, map))
                    .build();

    assertThat(composite.process(
            new RawOrder("O-1", "C-1", "10.00"))).isNull();

    verifyNoInteractions(map);
}
```

Và xác nhận exception không bị composite nuốt:

```java
@Test
void exceptionStopsChainAndPropagates() throws Exception {
    RuntimeException failure = new IllegalStateException("enrichment failed");
    ItemProcessor<RawOrder, NormalizedOrder> normalize = raw -> {
        throw failure;
    };
    ItemProcessor<NormalizedOrder, OrderExport> map = mock(ItemProcessor.class);

    ItemProcessor<RawOrder, OrderExport> composite =
            new CompositeItemProcessorBuilder<RawOrder, OrderExport>()
                    .delegates(List.of(normalize, map))
                    .build();

    assertThatThrownBy(() -> composite.process(
            new RawOrder("O-1", "C-1", "10.00")))
            .isSameAs(failure);

    verifyNoInteractions(map);
}
```

Các test này xác nhận semantics cơ bản của chain: delegate sau chỉ chạy khi delegate trước trả về object khác null và không ném exception.

## 22. Kiểm thử tích hợp với Step

Unit test composite không xác nhận transaction, filter count, retry, skip hoặc writer integration. Có thể dùng `@SpringBatchTest` và `JobLauncherTestUtils` để chạy Step/Job thật trong test:

- Xác nhận item hợp lệ đi qua toàn bộ chain và được ghi.
- Xác nhận item bị filter không đến writer và filter count đúng.
- Xác nhận exception ở từng delegate làm Step retry/skip/fail theo policy.
- Xác nhận thứ tự mapping tạo output đúng.
- Xác nhận JobParameters được inject đúng vào delegate `@StepScope`.
- Xác nhận chain hoạt động khi restart và không lặp side effect.

Nếu delegate gọi database hoặc service ngoài, dùng fixture xác định và test double phù hợp. Không để test phụ thuộc vào dữ liệu production hoặc một dịch vụ mạng không ổn định.

## 23. Những lỗi thường gặp

### Đảo thứ tự delegate

Processor sau nhận dữ liệu chưa được chuẩn hóa hoặc chưa enrichment. Khai báo danh sách theo thứ tự nghiệp vụ và test thứ tự gọi.

### Không khớp kiểu input/output

Output của processor trước không tương thích input của processor sau. Khai báo generic cụ thể cho từng delegate và tránh raw type/cast tùy tiện.

### Nghĩ các delegate chạy song song

`CompositeItemProcessor` gọi delegate tuần tự cho từng item. Nếu cần xử lý song song, đó là thiết kế concurrency khác ở cấp Step/partition hoặc hạ tầng xử lý.

### Nghĩ composite fan-out một item

Output của delegate trước được truyền vào delegate sau. Dùng classifier hoặc thiết kế fan-out riêng nếu cần nhiều nhánh độc lập.

### Delegate trả null nhưng vẫn mong bước sau chạy

`null` là filter signal và dừng chain cho item đó. Nếu cần biểu diễn một giá trị rỗng hợp lệ, dùng object/Optional hoặc kiểu kết quả rõ ràng thay vì null.

### Bắt exception rồi trả object mặc định

Lỗi thật bị che giấu và dữ liệu sai tiếp tục đến writer. Truyền exception hoặc chuyển thành kết quả nghiệp vụ có trạng thái rõ ràng.

### Nhồi mọi logic vào một delegate

Composite không giúp ích nếu một delegate vẫn làm toàn bộ công việc. Tách theo trách nhiệm và giữ mỗi bước có thể hiểu, test độc lập.

### Tách quá nhiều processor nhỏ

Một chuỗi dài các bước vụn làm tăng overhead và khó đọc. Chỉ tách khi có trách nhiệm, quy tắc hoặc khả năng tái sử dụng rõ ràng.

### Lưu state mutable trong singleton

Nhiều item/thread có thể dùng chung processor và làm lẫn state. Ưu tiên delegate stateless hoặc scope phù hợp.

### Đặt side effect không idempotent trong processor

Retry có thể gọi lại delegate. Dùng idempotency, outbox hoặc chuyển side effect sang giai đoạn có recovery rõ ràng.

### Dựa vào ItemProcessListener để đo từng delegate

Listener của Step bao quanh composite như một processor. Dùng decorator hoặc metric bên trong delegate nếu cần quan sát từng bước.

## 24. Quy trình xây dựng processor chain

Khi thiết kế một pipeline biến đổi item, có thể thực hiện theo trình tự:

1. Xác định kiểu input từ reader và kiểu output cần writer.
2. Chia logic thành các bước có trách nhiệm rõ ràng: normalize, enrich, validate, map.
3. Xác định input/output generic của từng delegate.
4. Sắp xếp delegate theo quan hệ dữ liệu phụ thuộc.
5. Tạo `CompositeItemProcessorBuilder<I, O>` với danh sách delegate tường minh.
6. Quyết định rõ điều kiện nào trả `null` để filter và điều kiện nào phải ném exception.
7. Đăng ký delegate và composite thành bean; dùng `@StepScope` khi cần JobParameters/state theo Step.
8. Đưa composite vào Step như một `ItemProcessor` thông thường.
9. Xác định retry/skip policy cho exception từ bất kỳ delegate nào.
10. Giữ delegate stateless/thread-safe và tránh side effect không idempotent.
11. Unit test từng processor, thứ tự chain, null short-circuit và exception propagation.
12. Integration test filter count, writer output, transaction, retry/skip và restart.

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Nhiều bước biến đổi nối tiếp | `CompositeItemProcessor<I, O>` |
| Chọn một processor theo loại/điều kiện | Classifier/routing processor |
| Gửi cùng item đến nhiều writer | `CompositeItemWriter` |
| Một delegate loại item khỏi output | Trả `null` có chủ đích |
| Một delegate phát hiện lỗi cần xử lý | Ném exception phù hợp retry/skip/fail policy |
| Theo dõi từng bước trong chain | Decorator, metric hoặc tracing trong delegate |

## Kết luận

`CompositeItemProcessor<I, O>` cho phép ghép nhiều `ItemProcessor` thành một chuỗi có thứ tự: output của delegate trước trở thành input của delegate sau. Dùng `CompositeItemProcessorBuilder` với danh sách delegate tường minh, khai báo kiểu trung gian tương thích và đặt thứ tự theo phụ thuộc dữ liệu. Khi một delegate trả `null`, item bị filter và các delegate còn lại không chạy; khi delegate ném exception, lỗi truyền ra Step để retry, skip hoặc fail theo policy. Chain là xử lý tuần tự trên từng item, không phải fan-out hay parallel processing. Hãy giữ delegate nhỏ, stateless và an toàn khi retry, rồi kiểm thử riêng từng bước cùng toàn bộ chain trong Step.

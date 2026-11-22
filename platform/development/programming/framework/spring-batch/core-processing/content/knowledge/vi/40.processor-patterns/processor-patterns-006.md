# Classifier processor

Trong Spring Batch, một `ItemProcessor<I, O>` thường nhận một item đầu vào, kiểm tra hoặc biến đổi nó rồi trả về item đầu ra. Khi cùng một step phải xử lý nhiều loại input theo những quy tắc khác nhau, một processor duy nhất có thể trở nên quá phức tạp với nhiều nhánh `if/else`. Pattern **classifier processor** giải quyết vấn đề đó bằng cách chọn một processor delegate cho từng item.

Spring Batch cung cấp `ClassifierCompositeItemProcessor<I, O>`. Component này cũng là một `ItemProcessor<I, O>`, nhưng bên trong nó dùng một `Classifier` để quyết định delegate nào sẽ xử lý item hiện tại. Step chỉ nhìn thấy một processor tổng hợp; các quy tắc xử lý cụ thể được tách thành nhiều processor nhỏ hơn.

Ví dụ, một job nhận cả đơn hàng nội địa và quốc tế. Đơn hàng nội địa cần tính thuế theo quy định trong nước; đơn hàng quốc tế cần đổi tiền tệ và tính phí nhập khẩu. Classifier kiểm tra thông tin của từng input, chọn processor tương ứng và trả kết quả về cùng một kiểu output để writer xử lý tiếp.

## Classifier processor là gì?

Classifier processor là cách tổ chức pipeline theo hai bước:

1. Phân loại item đầu vào để chọn một delegate.
2. Gọi `process(item)` trên delegate được chọn và trả kết quả của delegate đó.

Luồng xử lý:

```text
                  ItemReader
                      |
                      v
                  Input item
                      |
                      v
                   Classifier
                      |
             +--------+--------+
             |                 |
             v                 v
      Domestic processor  International processor
             |                 |
             v                 v
       Domestic result     International result
             |                 |
             +--------+--------+
                      |
                      v
                  ItemWriter
```

Chỉ delegate được chọn mới xử lý item đó. Classifier không tự biến đổi dữ liệu, không gọi tất cả processor và không ghi output. Nó chỉ trả về component cần được gọi.

`ClassifierCompositeItemProcessor` nằm trong package `org.springframework.batch.item.support`. Nó kết hợp hai abstraction:

- `ItemProcessor<I, O>` của Spring Batch: xử lý một item và trả output.
- `Classifier<C, T>` của Spring: nhận một đối tượng và chọn một đối tượng khác dựa trên nội dung đầu vào.

Với classifier processor, `C` thường là kiểu input và `T` là một `ItemProcessor` có thể xử lý input đó.

## Khi nào nên dùng classifier processor?

Pattern này hữu ích khi một luồng input chứa nhiều nhóm item có quy tắc xử lý khác nhau, nhưng vẫn có thể đưa kết quả về cùng một output contract.

Các trường hợp thường gặp:

- Đơn hàng nội địa và quốc tế có cách tính phí khác nhau.
- Thanh toán thẻ và chuyển khoản cần validation khác nhau.
- Hồ sơ cá nhân và doanh nghiệp cần quy tắc chuẩn hóa riêng.
- Giao dịch theo từng loại sản phẩm có công thức tính khác nhau.
- Message từ nhiều event type cần được chuyển đổi sang một mô hình kết quả chung.
- Dữ liệu cũ và dữ liệu mới cần các bộ chuyển đổi khác nhau.

Không nhất thiết phải dùng classifier cho mọi điều kiện. Nếu chỉ có một hoặc hai phép biến đổi ngắn, một processor đơn giản với nhánh điều kiện có thể dễ đọc hơn. Classifier phát huy tác dụng khi các nhánh có trách nhiệm riêng, có thể kiểm thử độc lập hoặc được tái sử dụng.

## Interface Classifier

`Classifier<C, T>` có một method chính:

```java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
```

`classify` nhận item và trả về delegate. Ví dụ:

```java
Classifier<OrderInput, ItemProcessor<?, ? extends Order>> classifier = input -> {
    if (input.international()) {
        return internationalProcessor;
    }
    return domesticProcessor;
};
```

Classifier có thể được triển khai bằng lambda, method reference hoặc class riêng. Với logic routing đơn giản, lambda đặt ngay trong cấu hình giúp nhìn thấy điều kiện. Với logic có nhiều rule, cần kiểm tra dữ liệu hoặc dùng nhiều dependency, class riêng thường dễ kiểm thử và bảo trì hơn.

Classifier nên có tính xác định: cùng một input và cùng một cấu hình phải chọn cùng một delegate. Tránh gọi API, ghi database hoặc thực hiện side effect trong `classify`, vì framework có thể xử lý lại item khi retry hoặc rollback.

## Ví dụ đầy đủ: chọn processor theo loại đơn hàng

Giả sử input có các thuộc tính:

```java
public record OrderInput(
        String orderId,
        String countryCode,
        BigDecimal amount) {

    public boolean international() {
        return countryCode != null
                && !"VN".equalsIgnoreCase(countryCode);
    }
}
```

Output là một mô hình thống nhất:

```java
public record ProcessedOrder(
        String orderId,
        BigDecimal payableAmount,
        String currency,
        BigDecimal fee,
        String processingRoute) {
}
```

Hai processor delegate cùng nhận `OrderInput` và trả `ProcessedOrder`:

```java
@Bean
ItemProcessor<OrderInput, ProcessedOrder> domesticOrderProcessor() {
    return input -> new ProcessedOrder(
            input.orderId(),
            input.amount(),
            "VND",
            calculateDomesticTax(input.amount()),
            "DOMESTIC");
}

@Bean
ItemProcessor<OrderInput, ProcessedOrder> internationalOrderProcessor() {
    return input -> new ProcessedOrder(
            input.orderId(),
            convertToSettlementCurrency(input.amount(), input.countryCode()),
            "USD",
            calculateImportFee(input),
            "INTERNATIONAL");
}
```

Các method `calculateDomesticTax`, `convertToSettlementCurrency` và `calculateImportFee` là logic nghiệp vụ do ứng dụng triển khai. Hai delegate có cùng input/output type nên có thể thay thế cho nhau tại vị trí classifier chọn processor.

Tạo classifier:

```java
@Bean
Classifier<OrderInput, ItemProcessor<?, ? extends ProcessedOrder>>
orderProcessorClassifier(
        ItemProcessor<OrderInput, ProcessedOrder> domesticOrderProcessor,
        ItemProcessor<OrderInput, ProcessedOrder> internationalOrderProcessor) {

    return input -> input.international()
            ? internationalOrderProcessor
            : domesticOrderProcessor;
}
```

Sau đó cấu hình composite processor:

```java
@Bean
ClassifierCompositeItemProcessor<OrderInput, ProcessedOrder> orderProcessor(
        Classifier<OrderInput, ItemProcessor<?, ? extends ProcessedOrder>>
                orderProcessorClassifier) {

    ClassifierCompositeItemProcessor<OrderInput, ProcessedOrder> processor =
            new ClassifierCompositeItemProcessor<>();
    processor.setClassifier(orderProcessorClassifier);
    return processor;
}
```

`ClassifierCompositeItemProcessor` thực thi delegate do classifier trả về. Cấu hình theo setter như trên là cách trực tiếp; nếu phiên bản Spring Batch của dự án có builder tương ứng, có thể dùng builder để cấu hình cùng contract.

## Gắn classifier processor vào step

Từ góc nhìn của step, composite processor chỉ là một `ItemProcessor` bình thường:

```java
@Bean
Step processOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ClassifierCompositeItemProcessor<OrderInput, ProcessedOrder> orderProcessor,
        ItemWriter<ProcessedOrder> orderWriter) {

    return new StepBuilder("processOrdersStep", jobRepository)
            .<OrderInput, ProcessedOrder>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Step không cần biết có bao nhiêu delegate hoặc điều kiện phân loại là gì. Việc routing nằm trong classifier processor, còn writer nhận output theo kiểu `ProcessedOrder`.

Nếu không cần processor cho một số item, delegate có thể trả `null` theo semantics của `ItemProcessor`; item đó sẽ bị filter và không chuyển tới writer. Cần phân biệt hành vi này với classifier trả `null`, vốn có nghĩa không chọn được delegate và thường dẫn tới lỗi khi composite cố gọi processor.

## Điều kiện phân loại và thứ tự rule

Classifier có thể dựa trên một thuộc tính hoặc nhiều thuộc tính. Ví dụ, giao dịch có thể được phân loại theo quốc gia, kênh bán và giá trị:

```java
return input -> {
    if (input.countryCode() == null) {
        return invalidInputProcessor;
    }
    if (!"VN".equalsIgnoreCase(input.countryCode())) {
        return internationalProcessor;
    }
    if (input.amount().compareTo(HIGH_VALUE_LIMIT) >= 0) {
        return highValueProcessor;
    }
    return domesticProcessor;
};
```

Thứ tự điều kiện thể hiện ưu tiên nghiệp vụ. Trong ví dụ, đơn hàng quốc tế có giá trị cao vẫn đi vào nhánh quốc tế vì điều kiện quốc tế được kiểm tra trước. Nếu đổi thứ tự, item có thể được route sang processor khác.

Với nhiều điều kiện, hãy tách logic phân loại thành một hàm có tên hoặc một enum route:

```java
enum OrderRoute {
    DOMESTIC,
    INTERNATIONAL,
    HIGH_VALUE,
    INVALID
}

private OrderRoute classifyOrder(OrderInput input) {
    if (input.countryCode() == null || input.amount() == null) {
        return OrderRoute.INVALID;
    }
    if (!"VN".equalsIgnoreCase(input.countryCode())) {
        return OrderRoute.INTERNATIONAL;
    }
    if (input.amount().compareTo(HIGH_VALUE_LIMIT) >= 0) {
        return OrderRoute.HIGH_VALUE;
    }
    return OrderRoute.DOMESTIC;
}
```

Sau đó map `OrderRoute` sang delegate. Điều này giúp test rule độc lập với Spring Batch và tránh một lambda dài khó đọc.

### Xử lý default route

Mọi input hợp lệ cần có một nhánh được xác định. Có thể dùng:

- Processor mặc định cho loại thông thường.
- Processor riêng cho dữ liệu chưa phân loại.
- Processor reject để tạo kết quả lỗi có cấu trúc.
- Exception rõ ràng nếu input vi phạm contract và không thể tiếp tục.

Không trả `null` từ classifier để biểu diễn default hoặc filter. Nếu không có delegate, hãy trả processor mặc định hoặc ném exception nghiệp vụ cụ thể.

Ví dụ với `switch`:

```java
return input -> switch (input.channel()) {
    case "WEB" -> webProcessor;
    case "STORE" -> storeProcessor;
    case "PARTNER" -> partnerProcessor;
    default -> unsupportedChannelProcessor;
};
```

Nếu `channel` có thể null, kiểm tra trước khi switch. Không để `NullPointerException` trở thành cơ chế routing ngầm.

## Classifier trả null và processor trả null

Hai trường hợp này có semantics khác nhau:

| Giá trị null xuất hiện ở đâu? | Ý nghĩa | Hành vi mong đợi |
| --- | --- | --- |
| `classifier.classify(item)` | Không chọn được delegate | Lỗi cấu hình/routing; không có processor để gọi |
| `delegate.process(item)` | Processor quyết định filter item | Item không được chuyển tới writer |

Ví dụ processor filter:

```java
ItemProcessor<OrderInput, ProcessedOrder> skipCancelledProcessor = input -> {
    if (input.cancelled()) {
        return null;
    }
    return mapActiveOrder(input);
};
```

Đây là filter hợp lệ nếu nghiệp vụ quy định không phát output cho đơn đã hủy. Spring Batch tăng filter count tương ứng. Nếu cần lưu dấu vết item bị loại, hãy ghi metrics hoặc dùng cơ chế audit phù hợp; không dùng classifier trả null để filter.

## Generic type của delegate

Các delegate được chọn cần tương thích với kiểu input và output của composite processor.

Với `ClassifierCompositeItemProcessor<I, O>`:

- Classifier nhận một `I` hoặc kiểu cha tương thích.
- Delegate phải nhận được `I`.
- Kết quả delegate phải gán được cho `O`.

Nếu tất cả delegate nhận `OrderInput` và trả `ProcessedOrder`, generic type khá đơn giản. Nếu các delegate trả các subtype khác nhau, hãy định nghĩa một interface hoặc sealed hierarchy chung.

Ví dụ:

```java
public sealed interface PaymentResult
        permits CardPaymentResult, BankTransferResult {
    String paymentId();
}

public record CardPaymentResult(
        String paymentId,
        String authorizationCode) implements PaymentResult {
}

public record BankTransferResult(
        String paymentId,
        String bankReference) implements PaymentResult {
}
```

Các processor có thể trả `CardPaymentResult` hoặc `BankTransferResult`, còn composite khai báo output là `PaymentResult`. Writer phía sau nhận kiểu chung và có thể xử lý subtype theo nhu cầu.

Tránh raw type hoặc unchecked cast trong classifier. Lỗi generic có thể bị che khi compile và chỉ xuất hiện khi một nhánh cụ thể chạy. Nếu hai nhánh có output không liên quan, hãy chuẩn hóa về một output DTO hoặc tách thành các step khác nhau.

## Tách processor thành component nhỏ

Mỗi delegate nên phụ trách một trách nhiệm rõ ràng. Ví dụ:

```text
OrderInput
   |
   +--> DOMESTIC ------> DomesticTaxProcessor
   |
   +--> INTERNATIONAL -> InternationalFeeProcessor
   |
   +--> WHOLESALE -----> WholesaleDiscountProcessor
```

Các delegate có thể được khai báo thành bean riêng, inject service cần thiết và unit test độc lập. Classifier không nên chứa công thức tính thuế, quy tắc đổi tiền hoặc logic validation chi tiết; nó chỉ chọn processor dựa trên đặc điểm item.

Điều này giúp thay đổi quy tắc của một nhánh mà ít ảnh hưởng tới các nhánh khác. Cũng có thể tái sử dụng một processor trong nhiều job nếu input/output contract giống nhau và component không giữ state theo execution.

## Kết hợp classifier với CompositeItemProcessor

`ClassifierCompositeItemProcessor` chọn một processor. `CompositeItemProcessor` chạy nhiều processor theo chuỗi. Hai component có thể được kết hợp khi mỗi route cần một pipeline riêng.

So sánh:

```text
CompositeItemProcessor:
Input -> Normalize -> Validate -> Enrich -> Output
```

```text
ClassifierCompositeItemProcessor:
                 Input
                   |
               Classifier
                /      \
          Processor A  Processor B
                \      /
                 Output
```

Ví dụ, cả đơn hàng nội địa và quốc tế đều cần chuẩn hóa dữ liệu, nhưng các bước tính toán sau đó khác nhau. Có thể tạo hai pipeline:

```java
ItemProcessor<OrderInput, ProcessedOrder> domesticPipeline =
        new CompositeItemProcessorBuilder<OrderInput, ProcessedOrder>()
                .delegates(
                        domesticNormalizer,
                        domesticValidator,
                        domesticTaxProcessor)
                .build();

ItemProcessor<OrderInput, ProcessedOrder> internationalPipeline =
        new CompositeItemProcessorBuilder<OrderInput, ProcessedOrder>()
                .delegates(
                        internationalNormalizer,
                        internationalValidator,
                        internationalFeeProcessor)
                .build();
```

Classifier trả về một trong hai pipeline. Mỗi pipeline chạy tuần tự các processor delegate bên trong nó. Cách này hữu ích khi mỗi loại item có nhiều bước xử lý riêng nhưng output vẫn cùng một contract.

Nếu mọi nhánh đều dùng chung normalize và validate, có thể đặt các bước chung trước hoặc sau classifier thay vì lặp chúng trong từng pipeline. Chọn cấu trúc sao cho rule dùng chung chỉ có một nguồn định nghĩa.

## Phân biệt với processor có nhiều if/else

Một processor đơn có thể viết:

```java
public ProcessedOrder process(OrderInput input) {
    if (input.international()) {
        return processInternational(input);
    }
    return processDomestic(input);
}
```

Cách này phù hợp nếu logic ngắn, số nhánh ít và không cần tái sử dụng. Classifier composite phù hợp hơn khi:

- Mỗi nhánh có nhiều logic hoặc dependency riêng.
- Các nhánh cần test độc lập.
- Delegate có thể được tái sử dụng.
- Số loại input có thể mở rộng.
- Mỗi nhánh cần cấu hình riêng hoặc có pipeline riêng.

Không nên tạo hàng chục processor một dòng chỉ để thay thế một `if/else` đơn giản. Mục tiêu là tách trách nhiệm, không phải tăng số class không cần thiết.

## Validation trước và sau phân loại

Classifier thường dựa trên field của input. Nếu field cần thiết thiếu hoặc sai format, phải xác định validation nằm ở đâu.

Một cách là validate các invariant chung trước khi classifier chạy:

```text
Reader
  |
  v
Common validation processor
  |
  v
Classifier processor
  |
  +--> Domestic processor
  +--> International processor
```

Ví dụ `orderId` và `amount` phải tồn tại ở mọi loại đơn hàng; kiểm tra chúng trước routing. Sau đó từng delegate kiểm tra quy tắc riêng như currency, country code hoặc tax identifier.

Nếu classifier cần phân loại cả input không hợp lệ, có thể có một `invalidInputProcessor` để tạo reject result. Điều quan trọng là không để một field null gây lỗi không có chủ đích trong classifier.

Validation nên phân biệt:

- Lỗi cấu trúc: không thể parse input, thường được xử lý ở reader.
- Lỗi chung: thiếu field bắt buộc cho mọi loại item.
- Lỗi theo route: field hợp lệ với nhánh này nhưng không hợp lệ với nhánh khác.
- Lỗi hạ tầng: dependency ngoài tạm thời không sẵn sàng, có thể retry.

## Exception, retry và skip

Nếu delegate ném exception, exception được truyền qua `ClassifierCompositeItemProcessor` lên step. Step có thể áp dụng retry, skip hoặc fail theo fault-tolerance policy.

Ví dụ retry lỗi service tạm thời và skip lỗi dữ liệu nghiệp vụ:

```java
return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderInput, ProcessedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(classifierProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientPricingException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
```

`TransientPricingException` và `InvalidOrderException` là exception ví dụ của ứng dụng. Chỉ retry lỗi có khả năng phục hồi; lỗi dữ liệu cố định thường nên reject/skip theo policy. Không catch exception trong delegate rồi trả output giả để step tiếp tục nếu item thực tế chưa được xử lý đúng.

Classifier nên tránh side effect. Nếu classifier gọi service ngoài và service thất bại, retry có thể gọi classifier nhiều lần. Tốt hơn là đưa dữ liệu routing vào input hoặc thực hiện enrichment trong processor có retry policy rõ ràng.

### Retry có thể gọi delegate lại

Processor thường nên có tính xác định và không tạo side effect không idempotent. Nếu processor gửi email, tạo giao dịch hoặc gọi API thay đổi trạng thái, retry có thể thực hiện hành động nhiều lần.

Đặt side effect ở writer hoặc một bước tích hợp có idempotency key/outbox. Processor nên tập trung biến đổi dữ liệu và tạo kết quả.

## Filter item trong từng nhánh

Một delegate có thể trả `null` để filter item. Điều này có thể khác nhau theo route:

- Processor nội địa filter đơn hàng bị hủy.
- Processor quốc tế filter đơn hàng chưa có chứng từ.
- Processor bán buôn luôn trả kết quả sau khi áp dụng discount.

Filter count của step phản ánh item processor trả `null`. Nếu cần phân biệt lý do filter, hãy ghi metrics theo route hoặc tạo audit/reject output trước khi trả null. Đừng biến một lỗi không phân loại được thành filter im lặng.

Nếu business cần xử lý item bị loại, có thể trả về một output có trạng thái `REJECTED` thay vì null để writer ghi vào reject table/file. Chọn theo yêu cầu lưu vết và downstream contract.

## XML configuration

Có thể khai báo classifier và composite processor thành bean rồi tham chiếu composite trong chunk step XML.

Bean classifier:

```xml
<bean id="orderProcessorClassifier"
      class="com.example.batch.OrderProcessorClassifier">
    <property name="domesticProcessor" ref="domesticOrderProcessor"/>
    <property name="internationalProcessor" ref="internationalOrderProcessor"/>
</bean>
```

Composite processor:

```xml
<bean id="classifierProcessor"
      class="org.springframework.batch.item.support.ClassifierCompositeItemProcessor">
    <property name="classifier" ref="orderProcessorClassifier"/>
</bean>
```

Đăng ký trong step:

```xml
<batch:step id="processOrdersStep">
    <batch:tasklet>
        <batch:chunk reader="orderReader"
                     processor="classifierProcessor"
                     writer="orderWriter"
                     commit-interval="100"/>
    </batch:tasklet>
</batch:step>
```

`OrderProcessorClassifier` là class ứng dụng implement `Classifier<OrderInput, ItemProcessor<?, ? extends ProcessedOrder>>` và cung cấp setter cho các delegate. Tên class và namespace parser cần tương thích với version Spring Batch đang dùng. Với Java configuration, lambda thường ngắn hơn; XML hữu ích khi dự án quản lý wiring tập trung trong file cấu hình.

## Scope và lifecycle của delegate

Classifier composite không tự làm cho các delegate trở thành step-scoped. Nếu delegate cần `JobParameters`, `StepExecution` hoặc state riêng của một lần chạy, khai báo bean với `@StepScope` hoặc scope phù hợp.

Ví dụ:

```java
@Bean
@StepScope
ItemProcessor<OrderInput, ProcessedOrder> internationalProcessor(
        @Value("#{jobParameters['exchangeRate']}") BigDecimal exchangeRate) {

    return input -> convertInternationalOrder(input, exchangeRate);
}
```

Composite processor có thể nhận proxy của scoped bean và gọi delegate khi step đang chạy. Không tự tạo delegate bằng `new` nếu nó cần dependency injection, scope proxy hoặc bean lifecycle của Spring.

### Delegate stateful

Processor thường nên stateless. Nếu delegate giữ mutable state, ví dụ counter hoặc cache thay đổi theo item, cần xem xét:

- Có nhiều step execution dùng chung singleton bean không?
- Có chạy multi-threaded step hoặc partitioning không?
- State có phải khôi phục khi restart không?
- State có thuộc về item hay thuộc về execution?

Không dùng field singleton để lưu `currentOrder` hoặc route hiện tại. Nếu state cần bền vững, lưu trong `ExecutionContext` qua một component `ItemStream` hoặc persistence store thích hợp; không dựa vào bộ nhớ của processor.

## Thread safety và parallel processing

Classifier processor có thể được gọi từ nhiều thread nếu step được cấu hình đa luồng hoặc các execution dùng chung bean. Classifier lambda stateless đọc field immutable thường dễ an toàn hơn classifier cập nhật biến dùng chung.

Các nguyên tắc:

- Không giữ item hiện tại trong field của classifier.
- Không cập nhật mutable counter dùng chung mà không đồng bộ.
- Delegate singleton cần thread-safe hoặc stateless.
- Delegate có resource/state riêng nên dùng scope hoặc instance riêng theo execution/partition.
- Không chia sẻ một mutable formatter/parser không thread-safe giữa nhiều worker.
- Nếu cần metrics, dùng Micrometer counter hoặc cơ chế thread-safe phù hợp.

Partitioning thường dễ kiểm soát hơn khi mỗi worker có processor/delegate instance và input partition riêng. Dù classifier chỉ chọn delegate, nó không tự tạo parallelism; concurrency do step/partition configuration quyết định.

## Hiệu năng và chi phí routing

Classifier thường có chi phí rất nhỏ so với I/O hoặc logic processor. Tuy nhiên, một classifier phức tạp có thể gọi nhiều service hoặc thực hiện query cho từng item, làm mất lợi ích của routing đơn giản.

Để giữ hiệu năng:

- Dùng field đã có trên item để phân loại nếu có thể.
- Tránh query database trong `classify` cho từng item.
- Nếu cần enrichment, cân nhắc processor chuyên trách có cache hoặc batch lookup.
- Giữ rule routing ngắn và xác định.
- Đo thời gian từng delegate để phát hiện một nhánh chậm.
- Tránh tạo object processor mới cho mỗi lần `classify`.

Delegate thường được inject như bean dùng lại. Nếu mỗi item cần cấu hình khác nhau, truyền dữ liệu đó trong input/context thay vì tạo hàng nghìn processor instance.

## Kiểm thử classifier độc lập

Classifier nên được kiểm thử riêng để xác nhận mọi loại input được route tới đúng delegate.

```java
@Test
void selectsInternationalProcessorForForeignOrder() {
    Classifier<OrderInput, ItemProcessor<?, ? extends ProcessedOrder>> classifier =
            input -> input.international()
                    ? internationalProcessor
                    : domesticProcessor;

    ItemProcessor<?, ? extends ProcessedOrder> selected =
            classifier.classify(new OrderInput(
                    "O-100", "US", new BigDecimal("100.00")));

    assertSame(internationalProcessor, selected);
}
```

Nên có test cho từng nhánh và các boundary value:

- Country code viết hoa/thường.
- Country code null hoặc không được hỗ trợ.
- Amount bằng đúng ngưỡng phân loại.
- Channel không nằm trong allowlist.
- Field bắt buộc bị thiếu.

Nếu dùng enum route, test riêng hàm `classifyOrder` để bảo đảm thứ tự ưu tiên rule.

## Kiểm thử ClassifierCompositeItemProcessor

Ngoài classifier, cần kiểm tra composite thực sự gọi delegate được chọn và trả kết quả của delegate.

```java
@Test
void compositeInvokesOnlySelectedProcessor() throws Exception {
    OrderInput input = new OrderInput(
            "O-200", "US", new BigDecimal("250.00"));

    when(internationalProcessor.process(input)).thenReturn(expectedOrder);

    ClassifierCompositeItemProcessor<OrderInput, ProcessedOrder> composite =
            new ClassifierCompositeItemProcessor<>();
    composite.setClassifier(candidate -> candidate.international()
            ? internationalProcessor
            : domesticProcessor);

    ProcessedOrder result = composite.process(input);

    assertEquals(expectedOrder, result);
    verify(internationalProcessor).process(input);
    verifyNoInteractions(domesticProcessor);
}
```

Test này chứng minh một input quốc tế chỉ gọi processor quốc tế. Bổ sung test cho input nội địa, delegate trả null và delegate ném exception.

### Kiểm thử filter

Cho delegate được chọn trả `null`; xác nhận composite trả `null` và step không chuyển item đó tới writer. Kiểm tra filter count nếu chạy step integration.

### Kiểm thử exception

Cho delegate ném exception; xác nhận composite truyền lỗi lên caller. Sau đó kiểm tra retry/skip policy ở mức step, vì unit test composite không chứng minh fault-tolerance configuration hoạt động.

## Integration test với step/job

Unit test chỉ xác nhận routing. Integration test nên chạy một step thật với input thuộc nhiều route:

1. Tạo fixture gồm item nội địa, quốc tế, high-value và item không hợp lệ.
2. Launch job với identifying `JobParameters` riêng.
3. Xác nhận `JobExecution` và `StepExecution` có status mong đợi.
4. Kiểm tra output của mỗi nhánh.
5. Xác nhận item bị filter không tới writer.
6. Xác nhận item reject được lưu theo policy.
7. Kiểm tra read/process/filter/write counts.

Ví dụ assertion:

```java
assertEquals(2, jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM domestic_orders", Integer.class));

assertEquals(1, jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM international_orders", Integer.class));
```

Số lượng phụ thuộc fixture. Nên kiểm tra business key cụ thể để xác nhận mỗi item vào đúng route, không chỉ kiểm tra tổng row count.

### Kiểm thử restart

Nếu processor delegate stateless, thường không cần lưu state của processor. Tuy nhiên, query/reader, input và các JobParameters dùng cho routing phải giữ ổn định khi restart. Nếu delegate có state riêng, kiểm thử state lifecycle và không để state trong singleton field.

Chạy step tới một số chunk, làm step thất bại, sau đó restart cùng identifying parameters. Xác nhận item được xử lý đúng nhánh và không có output trùng hoặc thiếu.

## Lỗi thường gặp

### Classifier trả về sai processor

Điều kiện hoặc thứ tự rule không đúng có thể đưa item sang nhánh khác. Test từng route và boundary value.

### Classifier trả null

Composite không có delegate để gọi. Định nghĩa default processor hoặc ném exception có ý nghĩa.

### Nhầm classifier null với processor null

Classifier null là lỗi chọn delegate; processor null là filter item. Xử lý hai trường hợp riêng.

### Generic type không tương thích

Delegate không nhận đúng input hoặc output không thể gán vào kiểu chung. Dùng interface/DTO output chung và tránh raw type.

### Đưa toàn bộ business logic vào classifier

Classifier trở thành một processor lớn trá hình. Chỉ giữ rule lựa chọn ở classifier, chuyển logic xử lý vào delegate.

### Dùng classifier cho một điều kiện quá đơn giản

Thêm nhiều bean không làm code dễ hiểu hơn nếu mỗi nhánh chỉ có một phép gán. Dùng processor đơn giản khi phù hợp.

### Nhầm classifier composite với CompositeItemProcessor

Classifier chọn một delegate; composite processor tuần tự chạy nhiều delegate. Chọn đúng semantics.

### Delegate có side effect không idempotent

Retry có thể gọi lại processor và thực hiện side effect trùng. Giữ processor thuần hoặc dùng idempotency/outbox cho side effect.

### Delegate singleton giữ mutable state

Nhiều execution/thread có thể ghi đè state của nhau. Dùng processor stateless hoặc scope riêng.

### Classifier gọi service/database cho từng item

Routing trở thành điểm nghẽn và dễ retry side effect. Đưa dữ liệu cần phân loại vào item hoặc enrichment stage.

### Không test nhánh mặc định

Input mới hoặc field null có thể rơi vào nhánh sai. Định nghĩa default/error route và test.

### Chỉ test classifier mà không test composite/step

Classifier có thể trả đúng delegate nhưng wiring step sai. Chạy integration test để xác nhận output cuối.

## Nguyên tắc thiết kế

Khi triển khai classifier processor, hãy xác định:

1. Những loại input nào cần quy tắc xử lý khác nhau?
2. Rule phân loại dựa trên field nào và có ổn định không?
3. Thứ tự ưu tiên giữa các điều kiện có rõ ràng không?
4. Mọi nhánh có delegate hợp lệ và default/error route chưa?
5. Các delegate có cùng input type và output contract tương thích không?
6. Có cần DTO/interface chung cho các output subtype không?
7. Có nhánh nào trả `null` để filter và đã phân biệt với classifier null chưa?
8. Logic chung nên đặt trước/sau classifier hay lặp trong từng pipeline?
9. Delegate có được Spring quản lý, có scope và thread safety phù hợp không?
10. Processor có side effect khiến retry tạo hành động trùng không?
11. Integration test đã xác nhận routing, filter, exception và output chưa?

`ClassifierCompositeItemProcessor` phù hợp khi mỗi item cần đúng một processor trong nhiều lựa chọn. Giữ classifier tập trung vào quyết định route, đặt business logic trong delegate, dùng output type chung và định nghĩa rõ nhánh mặc định. Dùng `CompositeItemProcessor` bên trong từng nhánh khi cần nhiều bước xử lý tuần tự. Giữ delegate stateless hoặc cô lập state theo step execution, tránh side effect không idempotent và kiểm thử cả classifier lẫn step thực tế.

## Ghi nhớ

Classifier processor dùng `Classifier` để chọn một `ItemProcessor` delegate cho từng input. `ClassifierCompositeItemProcessor<I, O>` được gắn vào step như một processor bình thường; nó gọi processor được chọn và trả kết quả. Classifier chỉ định tuyến, còn delegate thực hiện transformation/validation. Các delegate phải nhận được kiểu input chung và trả output tương thích; có thể dùng interface/DTO chung nếu các nhánh trả subtype. Delegate trả `null` có nghĩa filter item, còn classifier trả `null` là không chọn được processor và thường gây lỗi. Định nghĩa default/error route, giữ rule deterministic/stateless, đặt side effect ở nơi idempotent và chọn scope phù hợp cho delegate. Classifier chọn một nhánh, trong khi `CompositeItemProcessor` chạy nhiều processor theo chuỗi; có thể kết hợp hai pattern để tạo pipeline riêng cho từng loại item. Kiểm thử rule, delegate được gọi, filter, exception và output của step/job để xác nhận routing đúng.

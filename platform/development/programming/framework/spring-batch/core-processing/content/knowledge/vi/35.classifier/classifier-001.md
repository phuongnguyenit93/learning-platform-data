# Classifier xác định processor hoặc writer

Trong Spring Batch, `Classifier` cho phép chọn một component xử lý dựa trên dữ liệu của item. Thay vì dùng một processor hoặc writer duy nhất cho mọi item, step có thể phân loại từng item rồi chuyển nó tới processor hoặc writer phù hợp.

Hai component thường dùng cho cách routing này là:

- `ClassifierCompositeItemProcessor<I, O>`: chọn một `ItemProcessor` cho từng input item rồi trả về kết quả của processor đó.
- `ClassifierCompositeItemWriter<T>`: chọn một `ItemWriter` cho từng output item rồi chuyển item tới writer tương ứng.

`Classifier` chỉ quyết định **chọn delegate nào**. Nó không tự chuyển đổi dữ liệu, không ghi database và không quản lý transaction. Công việc thực tế vẫn do `ItemProcessor` hoặc `ItemWriter` được chọn thực hiện.

Ví dụ một job xử lý đơn hàng có hai nhóm: đơn hàng nội địa và đơn hàng quốc tế. Processor nội địa tính thuế theo quy tắc trong nước; processor quốc tế kiểm tra tiền tệ và phí hải quan. Sau khi xử lý, writer có thể đưa kết quả vào hai bảng hoặc hai file khác nhau. Classifier đọc thuộc tính của item và chọn đúng delegate cho từng trường hợp.

## Classifier là gì?

`Classifier<C, T>` là interface của Spring Core Classification, nằm trong package `org.springframework.classify`. Hợp đồng của nó là nhận một đối tượng đầu vào và trả về một đối tượng được chọn:

```java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
```

Trong ngữ cảnh Spring Batch:

- `C` là kiểu item mà classifier dùng để ra quyết định.
- `T` là kiểu delegate được chọn, ví dụ `ItemProcessor` hoặc `ItemWriter`.

Ví dụ classifier chọn processor theo loại đơn hàng:

```java
Classifier<OrderInput, ItemProcessor<?, ? extends Order>> classifier = input -> {
    if (input.international()) {
        return internationalOrderProcessor;
    }
    return domesticOrderProcessor;
};
```

Classifier có thể được viết bằng lambda, method reference hoặc class riêng implement `Classifier`. Với logic đơn giản, lambda giúp nhìn thấy điều kiện routing ngay tại nơi cấu hình. Với logic phức tạp, class riêng dễ kiểm thử và tái sử dụng hơn.

Classifier nên trả về một delegate hợp lệ cho mọi input mà step có thể nhận. Nếu trả `null`, composite không có processor/writer để gọi và thường sẽ phát sinh lỗi runtime. Nếu cần một nhánh mặc định, hãy trả về default delegate một cách tường minh.

## ClassifierCompositeItemProcessor

`ClassifierCompositeItemProcessor<I, O>` là một `ItemProcessor` tổng hợp. Nó dùng classifier để chọn một processor dựa trên input item, gọi processor đó và trả kết quả.

```text
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
       Domestic order     International order
             |                 |
             +--------+--------+
                      |
                      v
                 Output item
```

Chỉ một processor được chọn cho mỗi input item. Các processor còn lại không được gọi cho item đó.

### Ví dụ chọn processor theo thuộc tính input

Giả sử input model:

```java
public record OrderInput(
        String orderId,
        String countryCode,
        BigDecimal amount) {

    public boolean international() {
        return !"VN".equalsIgnoreCase(countryCode);
    }
}
```

Hai processor cùng nhận `OrderInput` và trả về `Order`:

```java
@Bean
ItemProcessor<OrderInput, Order> domesticOrderProcessor() {
    return input -> new Order(
            input.orderId(),
            input.amount(),
            "VND",
            calculateDomesticTax(input.amount()));
}

@Bean
ItemProcessor<OrderInput, Order> internationalOrderProcessor() {
    return input -> new Order(
            input.orderId(),
            convertToSettlementCurrency(input.amount(), input.countryCode()),
            "USD",
            calculateImportFee(input));
}
```

Các method `calculateDomesticTax`, `convertToSettlementCurrency` và `calculateImportFee` là logic nghiệp vụ do ứng dụng cung cấp. Hai processor có cùng input type và output type, nên có thể được chọn bởi cùng một `ClassifierCompositeItemProcessor<OrderInput, Order>`.

Khai báo classifier và composite processor:

```java
@Bean
Classifier<OrderInput, ItemProcessor<?, ? extends Order>> orderProcessorClassifier(
        ItemProcessor<OrderInput, Order> domesticOrderProcessor,
        ItemProcessor<OrderInput, Order> internationalOrderProcessor) {

    return input -> input.international()
            ? internationalOrderProcessor
            : domesticOrderProcessor;
}

@Bean
ClassifierCompositeItemProcessor<OrderInput, Order> orderProcessor(
        Classifier<OrderInput, ItemProcessor<?, ? extends Order>> orderProcessorClassifier) {

    return new ClassifierCompositeItemProcessorBuilder<OrderInput, Order>()
            .classifier(orderProcessorClassifier)
            .build();
}
```

`ClassifierCompositeItemProcessorBuilder` giúp cấu hình composite và kiểm tra các dependency cần thiết khi build. Cũng có thể tạo `ClassifierCompositeItemProcessor` rồi gọi `setClassifier(...)` nếu muốn cấu hình theo JavaBean style.

### Gắn composite processor vào step

```java
@Bean
Step processOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ClassifierCompositeItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("processOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Đối với step, composite processor chỉ là một `ItemProcessor` bình thường. Step không cần biết có bao nhiêu processor delegate hoặc classifier dựa trên điều kiện nào.

## Kiểu dữ liệu giữa các processor delegate

Các processor delegate được chọn phải tương thích với generic input/output của composite.

Với composite khai báo `ClassifierCompositeItemProcessor<I, O>`:

- Classifier nhận một giá trị tương thích với `I`.
- Processor được chọn phải nhận được `I`.
- Kết quả của processor phải có thể gán cho `O`.

Ví dụ nhiều processor trả về các subtype khác nhau:

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

Composite có thể khai báo output là `PaymentResult`, trong khi từng delegate trả subtype cụ thể. Writer phía sau có thể nhận `PaymentResult` và tiếp tục phân loại theo subtype hoặc field nghiệp vụ.

Không ép kiểu tùy tiện trong classifier. Nếu delegate có input/output không tương thích, lỗi có thể chỉ xuất hiện khi một nhánh cụ thể được chạy. Dùng generic type rõ ràng và một kiểu output chung có ý nghĩa nghiệp vụ.

### Processor trả về null

Giống `ItemProcessor` thông thường, delegate processor được chọn có thể trả `null` để filter item. Khi đó item không được chuyển tới writer của step.

Phân biệt hai trường hợp:

- Classifier trả `null`: không có delegate để thực thi, thường là lỗi cấu hình/routing.
- Processor được chọn trả `null`: filter item theo semantics của Spring Batch.

Nếu filter là hành vi hợp lệ, ghi nhận `filterCount` và thiết kế metrics phù hợp. Không dùng classifier trả `null` để biểu diễn việc filter.

## Nhiều tầng processor và composite processor

`ClassifierCompositeItemProcessor` chọn một processor trong số các delegate. Nó khác `CompositeItemProcessor`, vốn chạy một chuỗi processor theo thứ tự.

Ví dụ:

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

Có thể kết hợp hai cách. Ví dụ classifier chọn một pipeline riêng cho từng loại input, trong khi mỗi pipeline là một `CompositeItemProcessor` gồm normalize, validate và enrich:

```java
ItemProcessor<OrderInput, Order> domesticPipeline =
        new CompositeItemProcessorBuilder<OrderInput, Order>()
                .delegates(domesticNormalizer, domesticValidator, domesticEnricher)
                .build();
```

Classifier trả về `domesticPipeline` hoặc `internationalPipeline`. Cách này hữu ích khi các loại input có nhiều bước xử lý khác nhau nhưng vẫn chia sẻ một output contract.

Không tạo một chuỗi composite dài nếu các nhánh thực tế chỉ cần một processor khác nhau. Chọn cấu trúc phản ánh đúng nghiệp vụ để dễ hiểu và test.

## ClassifierCompositeItemWriter

`ClassifierCompositeItemWriter<T>` là một `ItemWriter` tổng hợp. Nó phân loại từng item trong chunk và chuyển item tới writer được chọn.

```text
                 Chunk<Order>
                       |
                       v
                   Classifier
                       |
             +---------+---------+
             |                   |
             v                   v
       Domestic writer     International writer
             |                   |
             v                   v
       domestic_orders      foreign_orders
```

Khác với processor composite, writer composite thực hiện routing cho từng output item trong chunk. Các item có thể được chia thành các nhóm theo writer delegate; mỗi writer nhận phần chunk dành cho nó.

### Ví dụ chọn writer theo loại đơn hàng

Giả sử output model:

```java
public record Order(
        String orderId,
        BigDecimal amount,
        String currency,
        boolean international) {
}
```

Hai writer có thể ghi vào hai bảng khác nhau:

```java
@Bean
JdbcBatchItemWriter<Order> domesticOrderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("INSERT INTO domestic_orders(order_id, amount) VALUES (?, ?)")
            .itemPreparedStatementSetter((order, ps) -> {
                ps.setString(1, order.orderId());
                ps.setBigDecimal(2, order.amount());
            })
            .build();
}

@Bean
JdbcBatchItemWriter<Order> internationalOrderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("INSERT INTO international_orders(order_id, amount, currency) VALUES (?, ?, ?)")
            .itemPreparedStatementSetter((order, ps) -> {
                ps.setString(1, order.orderId());
                ps.setBigDecimal(2, order.amount());
                ps.setString(3, order.currency());
            })
            .build();
}
```

Classifier chọn writer:

```java
@Bean
Classifier<Order, ItemWriter<? super Order>> orderWriterClassifier(
        ItemWriter<Order> domesticOrderWriter,
        ItemWriter<Order> internationalOrderWriter) {

    return order -> order.international()
            ? internationalOrderWriter
            : domesticOrderWriter;
}

@Bean
ClassifierCompositeItemWriter<Order> orderRoutingWriter(
        Classifier<Order, ItemWriter<? super Order>> orderWriterClassifier) {

    return new ClassifierCompositeItemWriterBuilder<Order>()
            .classifier(orderWriterClassifier)
            .build();
}
```

Composite writer có thể được gắn vào step bằng `.writer(orderRoutingWriter)`, giống một writer bình thường.

### Gắn writer composite vào step

```java
@Bean
Step routeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ClassifierCompositeItemWriter<Order> orderRoutingWriter) {

    return new StepBuilder("routeOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderRoutingWriter)
            .build();
}
```

Step chỉ biết một writer là `orderRoutingWriter`. Classifier và các delegate chịu trách nhiệm chọn đích cho từng item.

## Writer được gọi theo nhóm

`ClassifierCompositeItemWriter` không có nghĩa mỗi item tạo ra một lần gọi writer riêng. Nó phân loại item trong chunk, gom item theo delegate writer rồi gọi writer tương ứng với nhóm item đó.

Ví dụ chunk có:

```text
[D-1, I-1, D-2, D-3, I-2]

Domestic writer nhận:      [D-1, D-2, D-3]
International writer nhận: [I-1, I-2]
```

Điều này cho phép delegate writer tiếp tục sử dụng batch write hiệu quả. Thứ tự item bên trong nhóm thường theo thứ tự chúng xuất hiện trong chunk, nhưng không nên dựa vào thứ tự gọi giữa các nhóm delegate nếu implementation dùng map để nhóm writer. Nếu nghiệp vụ yêu cầu thứ tự toàn cục giữa các đích, hãy thiết kế một cơ chế ghi tuần tự có thứ tự rõ ràng hoặc chia thành các step riêng.

Một writer delegate có thể nhận chunk rỗng không? Theo cách routing thông thường, chỉ delegate có item được phân loại mới được gọi. Đừng dựa vào callback rỗng để trigger side effect; hãy dùng listener hoặc step riêng cho công việc luôn phải chạy.

## Chọn delegate theo nhiều điều kiện

Classifier có thể sử dụng nhiều thuộc tính để quyết định nhánh. Ví dụ, đơn hàng có thể được phân loại theo quốc gia, mức tiền và kênh bán:

```java
@Bean
Classifier<OrderInput, ItemProcessor<?, ? extends Order>> orderClassifier(
        ItemProcessor<OrderInput, Order> domesticProcessor,
        ItemProcessor<OrderInput, Order> highValueProcessor,
        ItemProcessor<OrderInput, Order> internationalProcessor) {

    return input -> {
        if (!"VN".equalsIgnoreCase(input.countryCode())) {
            return internationalProcessor;
        }
        if (input.amount().compareTo(new BigDecimal("100000000")) >= 0) {
            return highValueProcessor;
        }
        return domesticProcessor;
    };
}
```

Thứ tự điều kiện là một phần của nghiệp vụ. Đơn hàng quốc tế có giá trị cao sẽ vào nhánh quốc tế vì điều kiện đó được kiểm tra trước. Nếu đổi thứ tự, item có thể đi vào nhánh khác.

Với nhiều điều kiện, nên tách hàm phân loại có tên rõ ràng:

```java
private Route classifyOrder(OrderInput input) {
    if (input.countryCode() == null) {
        return Route.INVALID;
    }
    if (!"VN".equalsIgnoreCase(input.countryCode())) {
        return Route.INTERNATIONAL;
    }
    if (input.amount().compareTo(HIGH_VALUE_LIMIT) >= 0) {
        return Route.HIGH_VALUE;
    }
    return Route.DOMESTIC;
}
```

Sau đó classifier map `Route` sang delegate. Cách này giúp unit test logic quyết định độc lập với Spring Batch.

## Nhánh mặc định và dữ liệu không hợp lệ

Classifier cần định nghĩa hành vi cho mọi trường hợp. Có thể chọn một trong các cách:

- Default delegate xử lý các item không thuộc nhánh đặc biệt.
- Nhánh reject processor/writer ghi nhận dữ liệu không hợp lệ.
- Ném exception có ý nghĩa khi input không thể phân loại.
- Validate bắt buộc trước classifier để loại bỏ input thiếu thông tin.

Ví dụ:

```java
return input -> switch (input.channel()) {
    case "WEB" -> webProcessor;
    case "STORE" -> storeProcessor;
    case "PARTNER" -> partnerProcessor;
    default -> throw new UnsupportedOperationException(
            "Unsupported channel: " + input.channel());
};
```

Nếu `channel` có thể null, xử lý rõ ràng trước switch. Không để `NullPointerException` trở thành cơ chế định tuyến ngầm.

Với dữ liệu sai nhưng cần ghi reject, có thể chọn `rejectProcessor` trả về một subtype/result có trạng thái reject hoặc route sang reject writer. Nếu processor trả `null`, item bị filter và không tới writer; đó không tương đương với ghi reject record.

## Chọn processor hay writer để routing?

Việc phân loại nên đặt ở tầng phù hợp với quyết định nghiệp vụ:

| Câu hỏi | Nơi routing phù hợp |
| --- | --- |
| Mỗi loại input cần quy tắc chuyển đổi/validation khác nhau? | `ClassifierCompositeItemProcessor` |
| Các item đã chuẩn hóa nhưng cần ghi vào đích khác nhau? | `ClassifierCompositeItemWriter` |
| Cần cả quy tắc xử lý khác nhau và đích ghi khác nhau? | Có thể dùng cả hai, với classifier riêng ở từng tầng |
| Toàn bộ job flow khác nhau theo tham số launch? | Job flow/decider hoặc các step riêng có thể phù hợp hơn |
| Một item phải được ghi vào tất cả các đích? | `CompositeItemWriter`, không phải classifier writer |

Đừng route ở writer nếu sự khác nhau thực chất là quy tắc tính toán hoặc validation. Ngược lại, không nên nhân bản processor chỉ để chọn một bảng đích khác nhau nếu output model đã đủ thông tin và logic chuyển đổi giống nhau.

## So sánh với CompositeItemProcessor và CompositeItemWriter

Tên các composite khá giống nhau nhưng semantics khác:

| Component | Hành vi |
| --- | --- |
| `CompositeItemProcessor` | Chạy nhiều processor theo chuỗi; output của processor trước là input của processor sau |
| `ClassifierCompositeItemProcessor` | Chọn một processor theo từng input item |
| `CompositeItemWriter` | Gửi cùng chunk tới nhiều writer delegate theo cấu hình |
| `ClassifierCompositeItemWriter` | Phân loại từng item và gửi item tới writer được chọn |

Ví dụ:

```text
CompositeItemWriter:
  item A --> database writer
         --> audit file writer
```

```text
ClassifierCompositeItemWriter:
  item A --> domestic writer
  item B --> international writer
```

Nếu một item phải được ghi đồng thời vào bảng nghiệp vụ và audit file, `CompositeItemWriter` thường phù hợp hơn. Nếu item chỉ được ghi vào một trong nhiều đích tùy thuộc thuộc tính, `ClassifierCompositeItemWriter` phù hợp hơn.

## Đăng ký stream của delegate writer

Các delegate writer có thể là writer stateful, ví dụ `FlatFileItemWriter` triển khai `ItemStream` để lưu checkpoint. `ClassifierCompositeItemWriter` được dùng ở vị trí `.writer(...)`, nhưng không nên giả định mọi delegate `ItemStream` bên trong đều tự động được step quản lý lifecycle.

Nếu delegate không được composite forward hoặc đăng ký tự động, đăng ký stream tường minh:

```java
return new StepBuilder("routeOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderRoutingWriter)
        .stream(domesticFileWriter)
        .stream(internationalFileWriter)
        .build();
```

Khi restart, mỗi writer cần nhận đúng `ExecutionContext` và khôi phục resource/state riêng. Đặt tên writer khác nhau và ổn định để key state không bị trùng. Nếu writer delegate là JDBC writer không cần state riêng, không thêm `.stream(...)` chỉ vì nó là delegate; chỉ đăng ký các component thực sự implement `ItemStream` và cần lifecycle.

Nếu một delegate vừa được wrapper forward lifecycle vừa được đăng ký trực tiếp, callback có thể bị gọi hai lần. Xác định một đường quản lý stream duy nhất.

## Transaction khi routing writer

Classifier writer thường được gọi trong transaction của chunk step. Nếu tất cả delegate ghi vào cùng datasource và cùng transaction manager, các thao tác database có thể tham gia cùng transaction chunk.

Tuy nhiên, nếu các delegate ghi tới resource khác nhau, một transaction database không tự động tạo atomic commit cho tất cả:

| Delegate | Transaction behavior |
| --- | --- |
| Hai JDBC writer cùng datasource/transaction | Có thể cùng tham gia transaction chunk |
| JDBC writer dùng datasource khác | Có thể có transaction độc lập |
| File writer | File I/O không tự động tham gia transaction JDBC |
| Message writer | Broker acknowledgement/transaction có semantics riêng |
| HTTP/API writer | Side effect bên ngoài thường không rollback cùng chunk |

Ví dụ, domestic writer ghi database thành công rồi international writer ném exception. Nếu cả hai dùng cùng transaction resource, chunk có thể rollback cả hai nhóm database changes. Nếu một delegate đã gửi message hoặc ghi file ngoài transaction, side effect đó có thể còn lại dù chunk rollback.

Với nhiều đích output, cân nhắc transactional outbox, staging file, idempotency key hoặc bước publish/finalize sau khi chunk/job hoàn tất. Không coi classifier composite là distributed transaction coordinator.

## Retry, skip và idempotency

Classifier và delegate có thể được gọi nhiều lần trong các tình huống retry, rollback hoặc skip processing. Vì vậy:

- Classifier nên xác định và không có side effect.
- Processor delegate nên tránh side effect không idempotent.
- Writer delegate cần xử lý replay an toàn theo transaction/business key.
- Retry policy chỉ áp dụng cho exception có khả năng phục hồi.
- Skip policy cần phân biệt lỗi dữ liệu với lỗi hạ tầng.

Ví dụ, nếu classifier gọi API để hỏi loại khách hàng trước khi chọn processor, mỗi retry có thể gọi API lặp lại. Nên đưa thông tin routing vào item từ reader/enrichment step hoặc dùng một service cache/idempotent phù hợp, thay vì tạo side effect trong `classify`.

Với writer, một delegate có thể đã ghi một phần output ngoài transaction rồi ném exception. Khi Spring Batch retry hoặc xử lý lại chunk, cùng item có thể tới delegate lần nữa. Dùng unique constraint, upsert, event ID hoặc idempotency key để tránh duplicate.

## Thread safety và parallel processing

`ClassifierCompositeItemWriter` không nên được xem là thread-safe chỉ vì nó là component của Spring Batch. Nếu step chạy đa luồng hoặc nhiều execution dùng chung instance, classifier và delegate writer cần an toàn với concurrency.

Các điểm cần kiểm tra:

- Classifier có state mutable dùng chung không?
- Delegate writer có thread-safe không?
- Nhiều thread có thể ghi cùng một file hoặc cùng một mutable buffer không?
- `@StepScope` có tạo instance riêng đúng phạm vi execution không?
- Partition có writer/resource riêng hay cùng tranh một output path?
- Các transaction có chia sẻ connection hoặc resource không phù hợp không?

Một classifier stateless dựa trên field immutable của item thường an toàn hơn classifier cập nhật counter hoặc lưu `currentRoute` trong field. Với delegate writer stateful, dùng instance/resource riêng theo step hoặc partition nếu cần.

Nếu thứ tự toàn cục của item quan trọng, parallel routing và việc nhóm theo writer có thể làm thứ tự quan sát ở các đích khác nhau không còn tương đương thứ tự input. Thiết kế sequence number hoặc bước merge có thứ tự nếu downstream yêu cầu.

## XML configuration

Với Java configuration, có thể tạo composite bằng builder hoặc bean và inject vào step. Trong XML, cũng có thể khai báo classifier và composite processor/writer dưới dạng bean rồi tham chiếu trong chunk step. Cấu trúc XML và class names cần tương thích với Spring Batch version đang dùng.

Ví dụ khai báo classifier bean và composite processor theo JavaBean style:

```xml
<bean id="orderProcessorClassifier"
      class="com.example.batch.OrderProcessorClassifier">
    <property name="domesticProcessor" ref="domesticOrderProcessor"/>
    <property name="internationalProcessor" ref="internationalOrderProcessor"/>
</bean>

<bean id="orderProcessor"
      class="org.springframework.batch.item.support.ClassifierCompositeItemProcessor">
    <property name="classifier" ref="orderProcessorClassifier"/>
</bean>

<batch:step id="processOrdersStep">
    <batch:tasklet>
        <batch:chunk reader="orderReader"
                     processor="orderProcessor"
                     writer="orderWriter"
                     commit-interval="100"/>
    </batch:tasklet>
</batch:step>
```

`OrderProcessorClassifier` là class ứng dụng implement `Classifier<OrderInput, ItemProcessor<?, ? extends Order>>` và có setter cho hai delegate. Composite processor nhận classifier qua property. Với Spring Batch version có constructor/builder API khác, dùng cấu hình tương thích với dependency.

Tương tự, có thể khai báo `ClassifierCompositeItemWriter` và classifier writer bean rồi tham chiếu composite bằng `writer="orderRoutingWriter"`. Nếu writer delegate implement `ItemStream`, khai báo stream theo cú pháp `batch:streams` được XSD version hỗ trợ hoặc dùng cấu hình Java `.stream(...)`.

Không cần dùng XML chỉ để có classifier; Java configuration thường thuận tiện hơn khi classifier được tạo từ lambda hoặc method reference.

## Kiểm thử classifier độc lập

Classifier nên được test riêng để xác nhận từng loại item đi tới đúng delegate.

```java
@Test
void routesInternationalOrderToInternationalProcessor() {
    ItemProcessor<OrderInput, Order> domestic = input -> domesticOrder;
    ItemProcessor<OrderInput, Order> international = input -> internationalOrder;

    Classifier<OrderInput, ItemProcessor<?, ? extends Order>> classifier =
            input -> input.international() ? international : domestic;

    assertSame(international, classifier.classify(
            new OrderInput("O-2", "US", new BigDecimal("100.00"))));
}
```

Test này chỉ kiểm tra quyết định routing. Cần thêm test cho input nội địa, giá trị null/không hợp lệ và nhánh mặc định.

Nếu classifier dùng nhiều điều kiện, tạo test cho boundary values, ví dụ amount đúng bằng ngưỡng, country code khác chữ hoa/thường và channel không hỗ trợ.

## Kiểm thử ClassifierCompositeItemProcessor

Có thể mock delegate processor để xác nhận composite gọi đúng một nhánh:

```java
@Test
void compositeProcessorInvokesSelectedDelegate() throws Exception {
    OrderInput input = new OrderInput(
            "O-2", "US", new BigDecimal("100.00"));

    when(internationalProcessor.process(input)).thenReturn(expectedOrder);

    Order result = compositeProcessor.process(input);

    assertEquals(expectedOrder, result);
    verify(internationalProcessor).process(input);
    verifyNoInteractions(domesticProcessor);
}
```

Test cần xác nhận output được trả đúng và processor không được chọn không bị gọi. Thêm case delegate trả `null` để xác nhận filtering theo semantics của processor.

## Kiểm thử ClassifierCompositeItemWriter

Với writer, tạo mock delegate và chunk có item thuộc nhiều route:

```java
@Test
void routesItemsToTheirWriterGroups() throws Exception {
    Chunk<Order> chunk = new Chunk<>(List.of(
            domesticOrder1,
            internationalOrder1,
            domesticOrder2));

    routingWriter.write(chunk);

    verify(domesticWriter).write(argThat(items ->
            items.getItems().equals(
                    List.of(domesticOrder1, domesticOrder2))));

    verify(internationalWriter).write(argThat(items ->
            items.getItems().equals(List.of(internationalOrder1))));
}
```

Đây là ví dụ kiểm thử grouping; cách matcher và constructor `Chunk` cần khớp Spring Batch version/Mockito version trong dự án. Không assert thứ tự gọi giữa các delegate nếu implementation không cam kết thứ tự nhóm. Hãy assert tập item mỗi delegate nhận.

## Integration test với JobLauncherTestUtils

Unit test classifier chưa chứng minh writer/processor composite được gắn đúng vào step. Integration test nên chạy một job nhỏ với input có nhiều loại item.

Kịch bản kiểm thử:

1. Chuẩn bị input có ít nhất hai loại item.
2. Launch job với identifying `JobParameters` riêng cho test.
3. Xác nhận `JobExecution` và step đạt trạng thái mong đợi.
4. Kiểm tra processor delegate được gọi theo từng loại input.
5. Kiểm tra dữ liệu được ghi vào đúng bảng/file đích.
6. Xác nhận không có item bị mất hoặc ghi vào hai nhánh ngoài ý muốn.
7. Kiểm tra counters và reject output cho nhánh không hợp lệ.

Ví dụ assertion database:

```java
assertEquals(2, jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM domestic_orders", Integer.class));

assertEquals(1, jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM international_orders", Integer.class));
```

Các con số phụ thuộc fixture. Nên query business key để xác nhận item cụ thể nằm ở đúng đích, không chỉ kiểm tra tổng row count.

## Kiểm thử transaction và rollback

Tạo một delegate writer ném exception sau khi được gọi và xác nhận transaction chunk rollback đối với các database writer dùng chung transaction resource. Sau đó kiểm tra:

- Dữ liệu của chunk hiện tại không còn nếu transaction rollback.
- Dữ liệu của chunk trước đã commit vẫn còn.
- Job/step có trạng thái đúng theo fault-tolerance policy.
- Restart hoặc retry không tạo duplicate.

Nếu một delegate ghi file hoặc gửi message, test cần mô phỏng side effect ngoài transaction và xác nhận idempotency/staging/outbox xử lý replay. Không kết luận mọi delegate rollback chỉ từ việc database table không có row.

## Kiểm thử delegate ItemStream và restart

Nếu writer delegate là `FlatFileItemWriter` hoặc custom `ItemStreamWriter`, integration test cần xác nhận stream được đăng ký và state được khôi phục:

1. Chạy job để một số chunk commit.
2. Làm step thất bại sau khi một nhóm writer đã ghi.
3. Restart cùng identifying parameters và cùng output resource.
4. Xác nhận writer delegate mở lại từ checkpoint phù hợp.
5. Kiểm tra output không thiếu, không duplicate và không trộn dữ liệu giữa route.

Giữ tên writer ổn định, key `ExecutionContext` riêng và đăng ký `.stream(...)` nếu delegate không được wrapper/composite forward lifecycle.

## Lỗi thường gặp

### Classifier trả về sai delegate

Điều kiện routing sai hoặc thứ tự if/else không đúng có thể gửi item sang nhánh khác. Test từng route và boundary value.

### Classifier trả null

Composite không có delegate để gọi. Định nghĩa default hoặc ném exception có ý nghĩa khi input không hợp lệ.

### Nhầm null từ processor với null từ classifier

Processor trả null có nghĩa filter item; classifier trả null thường là lỗi routing. Không dùng chung hai semantics.

### Generic type không tương thích

Delegate nhận/trả kiểu không phù hợp với composite. Dùng interface/supertype chung có ý nghĩa và tránh unchecked cast.

### Dùng CompositeItemProcessor khi chỉ cần chọn một nhánh

Composite processor chạy tuần tự tất cả delegate; classifier processor chọn một delegate. Chọn đúng semantics.

### Dùng CompositeItemWriter khi item chỉ nên tới một đích

Composite writer có thể gửi cùng item tới nhiều delegate. Classifier writer phù hợp với routing độc quyền theo item.

### Dùng classifier writer nhưng mong thứ tự nhóm cố định

Writer có thể gom item theo delegate và thứ tự gọi nhóm không phải hợp đồng nghiệp vụ. Dùng step/flow riêng hoặc writer có điều phối thứ tự rõ ràng nếu cần.

### Đặt side effect trong classifier

Classifier có thể được gọi lại khi retry hoặc replay. Giữ classifier stateless và chỉ quyết định delegate.

### Quên đăng ký stream của writer delegate

Writer ẩn bên trong composite có thể không nhận `open/update/close`. Đăng ký stream tường minh hoặc forward lifecycle.

### Delegate writer không idempotent

Rollback/retry có thể gọi writer lại. Dùng transaction phù hợp, unique key, upsert, outbox hoặc staging.

### Chia sẻ delegate stateful giữa các step/partition

Nhiều execution có thể tranh cùng file/resource hoặc mutable state. Cô lập instance/resource và kiểm tra thread safety.

## Nguyên tắc thiết kế

Khi dùng classifier để chọn processor hoặc writer, hãy xác định:

1. Routing dựa trên input hay output item?
2. Điều kiện phân loại có rõ ràng, xác định và không có side effect không?
3. Mọi nhánh có delegate hợp lệ và có default/error behavior không?
4. Các processor delegate có input/output type tương thích không?
5. Writer delegate có nhận đúng kiểu output và chỉ nhận item thuộc route của nó không?
6. Có cần chọn một nhánh hay gửi item tới nhiều writer?
7. Có phụ thuộc thứ tự gọi giữa các delegate không?
8. Delegate có transaction, idempotency và thread-safety phù hợp không?
9. Writer delegate có `ItemStream` cần đăng ký lifecycle riêng không?
10. Retry/skip/restart có thể gọi classifier hoặc delegate lại không?
11. Unit và integration test đã xác nhận routing, output, rollback và restart chưa?

`ClassifierCompositeItemProcessor` phù hợp khi mỗi input cần một cách xử lý trong nhiều processor. `ClassifierCompositeItemWriter` phù hợp khi mỗi output item cần đi tới một writer được chọn. Giữ classifier đơn giản, deterministic và stateless; dùng kiểu chung cho các delegate; xác định default route; và bảo đảm writer delegate có transaction/idempotency/lifecycle phù hợp. Kiểm thử từng nhánh cùng job thực tế để chắc chắn không mất, trùng hoặc ghi sai item.

## Ghi nhớ

`Classifier<C, T>` nhận item và trả về delegate được chọn. `ClassifierCompositeItemProcessor<I, O>` chọn một processor cho từng input rồi trả kết quả; processor trả `null` có nghĩa filter. `ClassifierCompositeItemWriter<T>` phân loại từng output item, gom item theo writer và chuyển từng nhóm tới delegate phù hợp. Dùng classifier processor cho khác biệt về transformation/validation, classifier writer cho khác biệt về đích ghi; dùng `CompositeItemProcessor` hoặc `CompositeItemWriter` khi cần chạy nhiều delegate theo chuỗi hoặc ghi tới nhiều đích. Định nghĩa default/error route, giữ classifier stateless, đảm bảo generic type tương thích và không dựa vào thứ tự gọi giữa các writer group. Kiểm tra transaction, retry, idempotency, thread safety và đăng ký stream của delegate writer để routing vẫn đúng khi rollback hoặc restart.

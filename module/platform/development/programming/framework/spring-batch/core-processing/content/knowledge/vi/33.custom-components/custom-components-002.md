# Tự viết ItemProcessor

Trong Spring Batch, ItemProcessor là thành phần nhận một item từ ItemReader, thực hiện xử lý ở cấp item rồi trả về item đầu ra cho ItemWriter. Khi cần áp dụng quy tắc nghiệp vụ, chuẩn hóa dữ liệu, chuyển đổi kiểu, bổ sung thông tin hoặc loại item khỏi luồng, ta có thể tự viết một implementation của ItemProcessor<I, O>.

Processor là ranh giới tự nhiên giữa dữ liệu đầu vào và dữ liệu cần ghi. Reader tập trung lấy dữ liệu; processor tập trung biến đổi hoặc quyết định item có được chuyển tiếp; writer tập trung ghi kết quả. Giữ ranh giới này rõ ràng giúp từng phần dễ kiểm thử, tái sử dụng và thay đổi độc lập.

Một processor tốt thường xử lý một item bằng logic có thể hiểu và kiểm thử riêng. Nó không nên giữ trạng thái mutable dùng chung giữa các lần gọi, tự quản lý transaction của chunk hoặc tạo side effect không thể lặp an toàn. Trong chunk processing, cùng một item có thể được xử lý lại khi transaction rollback hoặc job restart, vì vậy tính xác định và idempotency cần được cân nhắc ngay từ thiết kế.

## 1. ItemProcessor là gì?

Spring Batch định nghĩa interface tổng quát:

~~~java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
~~~

Hai kiểu generic mô tả hợp đồng dữ liệu:

- I là kiểu item reader cung cấp cho processor.
- O là kiểu item processor trả về để writer nhận.

Processor có thể giữ nguyên kiểu dữ liệu, ví dụ OrderInput thành OrderInput đã chuẩn hóa; hoặc chuyển sang kiểu khác, ví dụ OrderInput thành OrderEntity hay InvoiceRow.

Ví dụ processor chuyển đơn hàng đầu vào thành command ghi database:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, OrderToSave> {

    @Override
    public OrderToSave process(OrderInput input) {
        return new OrderToSave(
                input.orderId().trim(),
                input.customerId().trim(),
                input.amount().setScale(2, RoundingMode.HALF_UP));
    }
}
~~~

Processor được gọi cho từng item mà reader cung cấp. Nó không nhận toàn bộ chunk trong interface cơ bản; mỗi lần gọi xử lý một item. Spring Batch quản lý việc gom các item đầu ra thành chunk và chuyển chúng cho writer.

## 2. Vị trí của processor trong chunk step

Một chunk-oriented step thường có reader, processor và writer:

~~~mermaid
flowchart LR
    A[ItemReader] --> B[ItemProcessor]
    B --> C[ItemWriter]
    C --> D[Commit chunk]
~~~

Ví dụ chunk size là 100:

1. Reader đọc các item đầu vào.
2. Processor được gọi riêng cho từng item.
3. Item hợp lệ được chuyển thành output; item được filter sẽ không đi tiếp.
4. Writer nhận danh sách item đầu ra của chunk.
5. Spring Batch commit transaction theo cấu hình step.

Nếu processor ném exception, chunk đi theo fault-tolerant policy đã cấu hình hoặc step thất bại. Nếu processor trả về null, item đó được xem là đã filter và không được gửi tới writer.

Processor không quyết định trực tiếp thời điểm commit. Nó nên tập trung xử lý item và để step/transaction manager quản lý ranh giới transaction.

## 3. Cấu hình một ItemProcessor tùy chỉnh

Có thể tạo processor như một Spring bean rồi inject vào step:

~~~java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor(
        CustomerRepository customerRepository) {

    return new OrderProcessor(customerRepository);
}

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

Phần khai báo generic của chunk phải khớp với kiểu vào và kiểu ra của pipeline:

- Reader trả OrderInput.
- Processor nhận OrderInput và trả Order.
- Writer nhận Order.

Nếu các kiểu không khớp, lỗi thường xuất hiện ở compile time khi khai báo đầy đủ generic. Tránh dùng raw type hoặc ép kiểu không cần thiết vì chúng làm mất lợi ích kiểm tra kiểu của Java.

Trong cấu hình Spring Batch 5, StepBuilder nhận JobRepository và chunk size cùng PlatformTransactionManager. Với phiên bản cũ hơn, API builder có thể khác; hãy dùng API tương ứng với phiên bản dự án.

## 4. Phân biệt transform, filter và skip

Processor có ba kiểu kết quả thường gặp:

| Hành vi | Cách thể hiện | Ý nghĩa |
|---|---|---|
| Transform | Trả về object khác hoặc object đã chuẩn hóa | Item tiếp tục tới writer |
| Filter | Trả về null | Item bị loại có chủ đích, không gửi tới writer |
| Processing error | Ném exception | Step áp dụng retry/skip/fail policy hoặc kết thúc lỗi |

Filter và skip không giống nhau. Filter là quyết định nghiệp vụ bình thường, ví dụ chỉ xuất các đơn hàng có trạng thái ACTIVE. Skip là cách xử lý một item gặp lỗi được chính sách cho phép bỏ qua, ví dụ một dòng đầu vào sai định dạng hoặc một bản ghi có dữ liệu không hợp lệ.

Ví dụ filter:

~~~java
public class ActiveOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (!"ACTIVE".equalsIgnoreCase(input.status())) {
            return null;
        }
        return mapToOrder(input);
    }
}
~~~

Item bị filter không làm tăng skip count. Spring Batch theo dõi số item bị filter riêng trong StepExecution. Không dùng null để che giấu lỗi parse, lỗi database hoặc exception ngoài dự kiến; các lỗi đó phải được biểu diễn bằng exception để policy xử lý.

## 5. Chuyển đổi dữ liệu trong processor

Một nhiệm vụ phổ biến của processor là chuyển dữ liệu từ DTO đầu vào sang mô hình mà writer cần. Ví dụ file nguồn lưu ngày dưới dạng chuỗi và số tiền có thể có nhiều chữ số thập phân; processor chuẩn hóa chúng thành kiểu domain.

~~~java
public class InvoiceProcessor
        implements ItemProcessor<InvoiceInput, Invoice> {

    private static final DateTimeFormatter DATE_FORMAT =
            DateTimeFormatter.ofPattern("uuuu-MM-dd");

    @Override
    public Invoice process(InvoiceInput input) {
        LocalDate invoiceDate =
                LocalDate.parse(input.invoiceDate(), DATE_FORMAT);

        BigDecimal amount = input.amount()
                .setScale(2, RoundingMode.HALF_UP);

        return new Invoice(
                input.invoiceNumber().trim(),
                invoiceDate,
                amount,
                input.currency().toUpperCase(Locale.ROOT));
    }
}
~~~

Nên dùng BigDecimal cho số tiền và formatter có pattern tường minh cho ngày tháng. Không dựa vào locale hoặc timezone mặc định của máy chạy batch. Nếu chuyển đổi không thành công, hãy ném exception có ngữ cảnh thay vì trả về object với giá trị mặc định không đúng.

Mapping và chuẩn hóa biểu diễn thường phù hợp với processor. Những quy tắc phức tạp phụ thuộc trạng thái hệ thống hoặc chính sách nghiệp vụ nên được tách thành service chuyên trách để processor dễ đọc.

## 6. Validation trong ItemProcessor

Processor thường là nơi kiểm tra các điều kiện nghiệp vụ trước khi ghi dữ liệu:

- Mã đơn hàng không được để trống.
- Số tiền phải lớn hơn hoặc bằng 0.
- Ngày hóa đơn không được nằm ngoài khoảng cho phép.
- Mã khách hàng phải tồn tại.
- Trạng thái đơn hàng phải thuộc tập giá trị hỗ trợ.

Ví dụ:

~~~java
public class ValidateOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new InvalidOrderException("orderId is required");
        }

        if (input.amount() == null
                || input.amount().signum() < 0) {
            throw new InvalidOrderException(
                    "amount must be zero or greater");
        }

        return new Order(
                input.orderId().trim(),
                input.customerId(),
                input.amount());
    }
}
~~~

Validation cần phân biệt lỗi dữ liệu và lỗi hệ thống. Một order thiếu orderId là lỗi dữ liệu của item; database timeout khi kiểm tra customer là lỗi hạ tầng có thể tạm thời. Không nên dùng cùng một exception cho cả hai nếu policy retry/skip khác nhau.

Với validation nhiều rule, có thể dùng Bean Validation hoặc một Validator chuyên biệt. Processor vẫn chịu trách nhiệm quyết định validation failure được ném ra, được chuyển thành reject record hay được filter theo nghiệp vụ.

## 7. Dùng ValidatingItemProcessor

Spring Batch cung cấp ValidatingItemProcessor để áp dụng một Validator cho từng item. Nó hữu ích khi validation có thể biểu diễn bằng một đối tượng Validator tách biệt.

Ví dụ:

~~~java
@Bean
Validator<OrderInput> orderInputValidator() {
    return input -> {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new ValidationException("orderId is required");
        }
        if (input.amount() == null || input.amount().signum() < 0) {
            throw new ValidationException("amount must be non-negative");
        }
    };
}

@Bean
ItemProcessor<OrderInput, OrderInput> validatedOrderProcessor(
        Validator<OrderInput> orderInputValidator) {

    ValidatingItemProcessor<OrderInput> processor =
            new ValidatingItemProcessor<>(orderInputValidator);
    return processor;
}
~~~

Mặc định, validation failure được ném ra dưới dạng exception. Nếu cấu hình processor với chế độ filter, validation failure có thể khiến item bị loại bằng cách trả về null. Chỉ bật filter khi nghiệp vụ xác định rằng item không hợp lệ được loại có chủ đích; nếu cần theo dõi reject và lý do, thường nên ném exception và xử lý qua skip listener/reject store.

ValidatingItemProcessor không thay thế toàn bộ logic mapping hoặc enrichment. Có thể đặt nó trong một chain cùng processor chuyển đổi dữ liệu.

## 8. Enrichment bằng service hoặc repository

Processor có thể bổ sung thông tin cần thiết từ service hoặc repository. Ví dụ, input chỉ chứa customerId nhưng writer cần thêm segment của khách hàng:

~~~java
public class EnrichOrderProcessor
        implements ItemProcessor<OrderInput, EnrichedOrder> {

    private final CustomerService customerService;

    public EnrichOrderProcessor(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Override
    public EnrichedOrder process(OrderInput input) {
        Customer customer =
                customerService.getRequired(input.customerId());

        return new EnrichedOrder(
                input.orderId(),
                customer.id(),
                customer.segment(),
                input.amount());
    }
}
~~~

Đây là enrichment đồng bộ theo từng item. Với hàng triệu item, một query riêng cho mỗi item có thể tạo N+1 query và làm job chậm. Có thể cân nhắc:

- Đưa thông tin cần thiết vào join trong reader query nếu phù hợp.
- Cache dữ liệu tham chiếu bất biến hoặc ít thay đổi.
- Dùng bulk lookup theo nhóm nếu kiến trúc processor cho phép.
- Chia dữ liệu bằng partition để kiểm soát tải.
- Đo thời gian gọi service và số query thực tế trước khi tối ưu.

Không cache dữ liệu mutable vô thời hạn nếu kết quả phải phản ánh trạng thái mới nhất. Cache cần có chính sách lifetime, giới hạn bộ nhớ và invalidation phù hợp.

## 9. Tách processor thành các thành phần nhỏ

Khi processor có nhiều trách nhiệm, hãy tách các bước thành class hoặc service nhỏ:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    private final OrderValidator validator;
    private final OrderNormalizer normalizer;
    private final CustomerEnricher enricher;

    public OrderProcessor(
            OrderValidator validator,
            OrderNormalizer normalizer,
            CustomerEnricher enricher) {
        this.validator = validator;
        this.normalizer = normalizer;
        this.enricher = enricher;
    }

    @Override
    public Order process(OrderInput input) {
        validator.validate(input);
        OrderInput normalized = normalizer.normalize(input);
        return enricher.enrich(normalized);
    }
}
~~~

Mỗi thành phần có thể được kiểm thử độc lập. Processor điều phối trình tự xử lý và chuyển kết quả giữa các thành phần. Nếu một bước có thể filter item, cần quyết định rõ bước sau có được gọi hay không và biểu diễn quyết định đó bằng null theo contract.

Tránh tạo một processor khổng lồ vừa parse, gọi nhiều API, gửi message, ghi database, cập nhật metric và quyết định routing. Những trách nhiệm đó làm processor khó kiểm thử và khó xác định hành vi khi retry.

## 10. Kết hợp nhiều processor bằng CompositeItemProcessor

Khi muốn chạy tuần tự nhiều processor, Spring Batch cung cấp CompositeItemProcessor. Output của delegate trước trở thành input của delegate sau.

Ví dụ:

~~~java
@Bean
ItemProcessor<OrderInput, EnrichedOrder> orderProcessorChain(
        ItemProcessor<OrderInput, OrderInput> normalizeProcessor,
        ItemProcessor<OrderInput, Order> mapProcessor,
        ItemProcessor<Order, EnrichedOrder> enrichProcessor) throws Exception {

    CompositeItemProcessor<OrderInput, EnrichedOrder> composite =
            new CompositeItemProcessor<>();

    composite.setDelegates(List.of(
            normalizeProcessor,
            mapProcessor,
            enrichProcessor));
    composite.afterPropertiesSet();
    return composite;
}
~~~

Trong chain này:

1. Normalize processor nhận OrderInput và trả OrderInput.
2. Map processor nhận OrderInput và trả Order.
3. Enrich processor nhận Order và trả EnrichedOrder.

Kiểu output của mỗi delegate phải tương thích với kiểu input của delegate tiếp theo. Nếu một delegate trả null, chuỗi dừng cho item đó và item bị filter; delegate phía sau không nhận null.

CompositeItemProcessor phù hợp khi các bước có thứ tự rõ và muốn tái sử dụng từng processor. Đừng chia nhỏ quá mức thành nhiều delegate chỉ để tạo nhiều class; chain nên thể hiện các bước xử lý có ý nghĩa.

## 11. Chọn processor theo loại item

Nếu input có nhiều loại record và mỗi loại cần logic khác nhau, có thể dùng ClassifierCompositeItemProcessor để chọn processor phù hợp dựa trên item.

Ví dụ khái quát:

~~~java
@Bean
ItemProcessor<ImportRecord, ImportResult> classifiedProcessor(
        ItemProcessor<CustomerRecord, ImportResult> customerProcessor,
        ItemProcessor<OrderRecord, ImportResult> orderProcessor) {

    ClassifierCompositeItemProcessor<ImportRecord, ImportResult> composite =
            new ClassifierCompositeItemProcessor<>();

    composite.setClassifier(record -> {
        if (record instanceof CustomerRecord) {
            return item -> customerProcessor.process((CustomerRecord) item);
        }
        if (record instanceof OrderRecord) {
            return item -> orderProcessor.process((OrderRecord) item);
        }
        throw new IllegalArgumentException(
                "Unsupported record type: " + record.getClass().getName());
    });
    return composite;
}
~~~

Ví dụ minh họa cách phân nhánh theo kiểu record; trong ứng dụng thực tế, nên dùng classifier riêng có kiểu rõ ràng và kiểm soát unchecked cast nếu có. Một lựa chọn khác là thiết kế interface chung với các implementation có thể xử lý cùng kiểu input.

Không trả về null processor từ classifier nếu không có quy tắc xử lý rõ ràng. Record type không hỗ trợ nên tạo lỗi có ngữ cảnh hoặc đi vào nhánh reject được thiết kế riêng.

## 12. Processor có thể trả về cùng object hay cần object mới?

Processor có thể trả lại chính object đầu vào nếu không cần thay đổi:

~~~java
public class PassThroughOrderProcessor
        implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order item) {
        return item;
    }
}
~~~

Tuy nhiên, nếu cần chuẩn hóa hoặc thêm dữ liệu, thường nên tạo object đầu ra mới, nhất là khi input là immutable record hoặc được dùng ở nhiều nơi. Việc mutate object đầu vào có thể gây tác dụng phụ nếu reader/cache/test fixture hoặc một nhánh xử lý khác còn giữ tham chiếu tới object đó.

Nếu object là mutable và processor thay đổi trực tiếp, hãy xác định rõ quyền sở hữu object và bảo đảm không có consumer khác dùng đồng thời. Immutable DTO/domain object thường giúp pipeline dễ dự đoán hơn.

## 13. Exception từ processor và fault-tolerant step

Method process có thể ném Exception. Spring Batch chuyển lỗi đó cho cơ chế xử lý lỗi của step. Tùy cấu hình, exception có thể:

- Làm step/job thất bại.
- Được retry nếu được phân loại retryable và còn retry limit.
- Được skip nếu exception được khai báo skippable và skip limit chưa vượt.

Ví dụ cấu hình:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TemporaryCustomerServiceException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .listener(skipListener)
        .build();
~~~

Trong ví dụ, lỗi service tạm thời được retry tối đa theo cấu hình; lỗi dữ liệu riêng của item có thể được skip. Đây chỉ là chính sách mẫu: cần xác định exception nào thực sự tạm thời, có thể retry an toàn và exception nào được phép bỏ qua theo nghiệp vụ.

Không bắt tất cả Exception trong process rồi trả null. Cách đó biến lỗi hệ thống thành filter im lặng, làm mất dữ liệu và khiến metadata không phản ánh đúng lỗi. Hãy để exception truyền ra hoặc chuyển thành exception domain cụ thể với cause được giữ lại.

## 14. Phân biệt lỗi dữ liệu với lỗi hạ tầng

Một processor có thể gọi database, REST API hoặc service khác. Cần phân loại lỗi theo khả năng phục hồi:

| Tình huống | Cách xử lý thường phù hợp |
|---|---|
| Thiếu trường bắt buộc | Validation exception; fail hoặc skip theo chính sách |
| Mã trạng thái không được hỗ trợ | Lỗi dữ liệu; thường reject hoặc fail |
| API tạm thời timeout | Có thể retry có giới hạn và backoff |
| API trả về “customer không tồn tại” | Lỗi nghiệp vụ/dữ liệu; không retry vô hạn |
| Database deadlock | Transaction rollback rồi retry nếu cấu hình phù hợp |
| Lỗi lập trình như NullPointerException ngoài dự kiến | Thường fail và điều tra, không skip đại trà |

Không nên phân loại mọi RuntimeException là skippable hoặc retryable. Một rule quá rộng có thể che giấu lỗi lập trình hoặc lỗi cấu hình.

Nếu cần lưu reject record, dùng listener hoặc cơ chế riêng để lưu source ID, input reference, exception type và lý do. Đảm bảo việc ghi reject có transaction semantics phù hợp với step và không tạo bản ghi duplicate khi retry.

## 15. Side effect và tính idempotent

Processor có thể được gọi lại nếu chunk rollback hoặc thao tác được retry. Vì vậy, processor nên ưu tiên logic thuần hoặc side effect có thể lặp an toàn.

Ví dụ không nên làm trong processor:

~~~java
public Order process(OrderInput input) {
    paymentGateway.charge(input.paymentToken(), input.amount());
    return map(input);
}
~~~

Nếu transaction của chunk rollback sau khi charge thành công, lần xử lý lại có thể charge thêm lần nữa. Database transaction không thể tự hoàn tác một request thanh toán đã được hệ thống ngoài chấp nhận.

Các lựa chọn tốt hơn:

- Processor chỉ xác thực và tạo command cần thực hiện.
- Writer ghi command/outbox record cùng transaction database.
- Một dispatcher riêng gửi message hoặc gọi API từ outbox.
- Dùng idempotency key ổn định theo business operation.
- Lưu trạng thái xử lý để chống gửi trùng và hỗ trợ reconciliation.

Nếu processor bắt buộc gọi service đọc dữ liệu, hãy bảo đảm lời gọi đó không tạo side effect hoặc có semantics an toàn khi lặp. Đặt timeout, giới hạn retry và quan sát latency.

## 16. Processor trong multi-threaded step

Trong multi-threaded step, cùng một processor bean có thể được nhiều worker thread gọi đồng thời. Vì vậy, processor thường nên stateless:

~~~java
@Component
public class AmountNormalizer
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        BigDecimal amount =
                input.amount().setScale(2, RoundingMode.HALF_UP);
        return new Order(input.orderId(), amount);
    }
}
~~~

Không lưu item hiện tại, batch ID thay đổi theo lần gọi hoặc counter mutable trong field singleton nếu không có cơ chế đồng bộ. Biến local trong process thuộc lần gọi đó và an toàn hơn state dùng chung.

Nếu processor phụ thuộc vào cấu hình theo JobParameters hoặc partition context, có thể dùng StepScope để late binding theo StepExecution. Tuy nhiên, StepScope không có nghĩa một instance mới được tạo cho mỗi chunk thread trong multi-threaded step. Nếu target processor được nhiều thread gọi, nó vẫn phải thread-safe.

Trong partitioning, mỗi worker có StepExecution riêng; processor step-scoped có thể nhận context của partition tương ứng. Đây thường là cách rõ ràng hơn nếu mỗi worker cần state riêng.

## 17. Không dùng processor làm nơi quản lý chunk

ItemProcessor nhận từng item, không nhận danh sách toàn chunk. Không nên tự giữ danh sách item trong field để chờ đủ một nhóm rồi xử lý, vì:

- State có thể bị trộn giữa các chunk hoặc thread.
- Rollback/restart có thể làm danh sách trong bộ nhớ không đồng bộ với checkpoint.
- Bộ nhớ tăng theo số item.
- Lifecycle của state không khớp với transaction của chunk.

Nếu cần xử lý theo nhóm, cân nhắc reader query theo batch, writer hỗ trợ bulk operation hoặc thiết kế một bước aggregation riêng. Nếu cần biết ranh giới chunk, có thể dùng listener hoặc writer phù hợp thay vì lưu state tùy tiện trong processor.

## 18. Hiệu năng của processor

Processor thường được gọi một lần cho mỗi item, vì vậy chi phí nhỏ trên mỗi lần gọi có thể trở thành đáng kể khi xử lý hàng triệu bản ghi.

Một số hướng tối ưu:

- Tránh tạo formatter hoặc parser đắt tiền lặp lại nếu có thể dùng instance immutable/thread-safe.
- Không gọi database/API nhiều lần cho cùng dữ liệu tham chiếu.
- Dùng batch lookup hoặc join trong reader khi phù hợp.
- Tránh logging toàn bộ payload ở mức INFO cho mỗi item.
- Giữ object graph output vừa đủ cho writer.
- Đo thời gian process riêng với read và write để xác định bottleneck.
- Giới hạn concurrency theo khả năng của dependency bên ngoài.

Cache có thể tăng throughput nhưng phải có giới hạn bộ nhớ và chính sách hết hạn. Với dữ liệu tham chiếu thay đổi trong lúc job chạy, quyết định cache có thể ảnh hưởng tính nhất quán nghiệp vụ.

Không tối ưu bằng cách bỏ validation bắt buộc hoặc thay exception bằng giá trị mặc định không đúng. Đo trước, tối ưu vùng tốn thời gian và giữ nguyên semantics dữ liệu.

## 19. Theo dõi processor bằng listener và metadata

Spring Batch có ItemProcessListener để quan sát lifecycle xử lý item:

~~~java
public class OrderProcessListener
        implements ItemProcessListener<OrderInput, Order> {

    @Override
    public void beforeProcess(OrderInput item) {
        // Có thể ghi nhận correlation ID nếu cần.
    }

    @Override
    public void afterProcess(OrderInput item, Order result) {
        // result có thể null nếu item bị filter.
    }

    @Override
    public void onProcessError(OrderInput item, Exception e) {
        // Ghi thông tin lỗi có kiểm soát.
    }
}
~~~

Listener hữu ích cho logging, metrics và audit. Tránh ghi payload nhạy cảm hoặc toàn bộ item vào log. Nếu listener ghi dữ liệu reject/audit vào database, cần hiểu transaction và retry semantics để không tạo record trùng.

StepExecution có các bộ đếm như readCount, writeCount, filterCount, processSkipCount và skipCount. Có thể dùng chúng để quan sát:

- Bao nhiêu item được đọc.
- Bao nhiêu item bị filter do processor trả null.
- Bao nhiêu item được ghi.
- Bao nhiêu lỗi process được skip.

Các bộ đếm này hỗ trợ vận hành nhưng không thay thế đối soát dữ liệu đầu ra. Nếu filter count tăng bất thường, cần kiểm tra quy tắc filter và input distribution.

## 20. Unit test cho ItemProcessor

Processor nên có unit test độc lập vì nó thường chứa quy tắc chuyển đổi và validation quan trọng.

Ví dụ:

~~~java
class OrderProcessorTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void normalizesOrderFields() throws Exception {
        OrderInput input = new OrderInput(
                " ORD-1001 ",
                " CUS-01 ",
                new BigDecimal("12.345"));

        Order result = processor.process(input);

        assertEquals("ORD-1001", result.orderId());
        assertEquals("CUS-01", result.customerId());
        assertEquals(new BigDecimal("12.35"), result.amount());
    }

    @Test
    void rejectsNegativeAmount() {
        OrderInput input = new OrderInput(
                "ORD-1002",
                "CUS-02",
                new BigDecimal("-1.00"));

        assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));
    }
}
~~~

Các trường hợp nên có:

1. Input hợp lệ tạo đúng output.
2. Chuỗi có khoảng trắng được chuẩn hóa theo quy tắc.
3. Giá trị null hoặc thiếu trường bắt buộc được xử lý rõ.
4. Số tiền, ngày tháng và enum được chuyển đổi đúng.
5. Điều kiện filter trả null đúng khi nghiệp vụ yêu cầu.
6. Validation failure ném đúng exception type.
7. Lỗi từ dependency được giữ nguyên cause hoặc chuyển thành exception có ý nghĩa.
8. Enrichment dùng dữ liệu service đúng và xử lý trường hợp không tìm thấy.
9. Processor không mutate input ngoài ý muốn.
10. Nhiều lần gọi cùng input cho kết quả xác định nếu logic được thiết kế deterministic.

Không cần mock toàn bộ framework Spring Batch trong unit test processor. Test trực tiếp method process với input và dependency cần thiết; dùng integration test riêng cho cấu hình step và fault-tolerant behavior.

## 21. Integration test processor trong step

Unit test không chứng minh processor được gắn đúng vào step hoặc filter/skip counter hoạt động như mong đợi. Integration test nên chạy step với reader, processor và writer test đơn giản.

Ví dụ kiểm tra filter:

~~~java
JobExecution execution =
        jobLauncherTestUtils.launchStep(
                "filterOrdersStep",
                jobParameters);

StepExecution stepExecution = execution.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("filterOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(3, stepExecution.getFilterCount());
assertEquals(7, stepExecution.getWriteCount());
~~~

Ví dụ giả định reader trả 10 item, processor filter 3 item và 7 item còn lại được writer ghi. Cần dùng JobRepository test riêng hoặc dọn metadata phù hợp để mỗi lần chạy có JobParameters xác định.

Với skip/retry, kiểm tra cả số lần gọi processor, skip count, output cuối, reject store và trạng thái job. Với side effect, test rollback/retry để chứng minh không tạo duplicate.

## 22. Những lỗi thường gặp

**Dùng null để biểu diễn lỗi.** Null là tín hiệu filter theo contract. Hãy ném exception cho lỗi cần retry/skip/fail.

**Nhầm filter với skip.** Filter là loại item có chủ đích; skip là bỏ item gặp exception được policy cho phép.

**Dùng raw type hoặc generic không khớp.** Kiểu output của processor phải tương thích với kiểu writer nhận.

**Đặt quá nhiều trách nhiệm trong một processor.** Tách validation, normalization và enrichment thành thành phần có ý nghĩa.

**Gọi API có side effect trong process.** Rollback/retry có thể gọi lại processor và tạo tác động trùng. Dùng outbox hoặc idempotency.

**Bắt mọi exception rồi trả item mặc định.** Lỗi bị che giấu và dữ liệu sai được ghi. Phân loại exception rõ ràng.

**Dùng cùng exception cho validation và timeout.** Retry/skip policy khó chính xác. Tách exception theo bản chất lỗi.

**Giữ mutable state trong singleton processor.** Multi-threaded step có thể làm trộn state. Giữ processor stateless hoặc bảo vệ state có chủ đích.

**Giả định StepScope tạo instance per thread.** StepScope gắn với StepExecution. Component vẫn phải thread-safe nếu nhiều thread cùng gọi target.

**Làm N+1 query khi enrichment.** Một query mỗi item có thể làm job chậm. Cân nhắc join, cache có kiểm soát hoặc bulk lookup.

**Không kiểm tra filter count và reject count.** Job có thể hoàn thành nhưng loại quá nhiều item. Đặt ngưỡng và đối soát theo nghiệp vụ.

## 23. Quy trình xây dựng processor

Khi tự viết ItemProcessor, có thể làm theo trình tự:

1. Xác định kiểu input từ reader và kiểu output writer cần.
2. Xác định processor làm transform, validation, enrichment hay filter.
3. Định nghĩa rõ điều kiện trả null và exception nào được ném.
4. Tách quy tắc nghiệp vụ vào service/validator có thể kiểm thử độc lập.
5. Giữ logic deterministic và tránh side effect không idempotent.
6. Cấu hình processor vào step với generic type khớp reader/writer.
7. Chọn retry/skip policy theo exception type và yêu cầu nghiệp vụ.
8. Kiểm tra thread safety nếu step dùng TaskExecutor, partitioning hoặc parallel flow.
9. Viết unit test cho logic item và integration test cho filter/skip/retry.
10. Theo dõi filterCount, processSkipCount, latency và kết quả đối soát trong production.

## Kết luận

ItemProcessor<I, O> nhận một item từ reader và trả về item đầu ra cho writer. Khi tự viết processor, hãy xác định rõ kiểu input/output, tách transform, validation, enrichment và filter theo trách nhiệm. Trả null chỉ khi muốn filter item có chủ đích; ném exception khi cần step áp dụng retry, skip hoặc fail policy.

Giữ processor stateless và có kết quả xác định, đặc biệt khi step chạy nhiều thread hoặc item có thể được xử lý lại sau rollback. Tránh side effect không idempotent trong process; dùng writer, outbox hoặc cơ chế idempotency cho tác động cần commit. Kết hợp unit test với step integration test để xác nhận mapping, filter count, exception policy và output thực tế. Một processor nhỏ, có hợp đồng rõ ràng giúp chunk pipeline dễ kiểm soát và phục hồi.

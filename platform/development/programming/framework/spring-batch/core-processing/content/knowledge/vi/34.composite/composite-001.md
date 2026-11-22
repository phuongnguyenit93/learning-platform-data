# CompositeItemProcessor

Trong Spring Batch, `CompositeItemProcessor<I, O>` cho phép kết hợp nhiều `ItemProcessor` nhỏ thành một processor duy nhất. Với mỗi item đầu vào, composite gọi các delegate theo thứ tự đã khai báo; output của delegate trước trở thành input của delegate tiếp theo. Kết quả cuối cùng được chuyển cho `ItemWriter`.

Mô hình này phù hợp khi pipeline có nhiều bước xử lý độc lập, chẳng hạn chuẩn hóa dữ liệu, kiểm tra hợp lệ, chuyển đổi sang domain object và bổ sung thông tin tham chiếu. Mỗi delegate có một trách nhiệm rõ ràng, có thể kiểm thử và tái sử dụng riêng. Composite điều phối thứ tự chạy mà không phải gộp toàn bộ logic vào một class lớn.

`CompositeItemProcessor` thực hiện các delegate tuần tự cho từng item. Nó không chạy các processor song song, không tạo transaction riêng và không thay thế fault-tolerant policy của step. Nếu một delegate trả về `null`, item bị filter và các delegate còn lại không được gọi cho item đó. Nếu delegate ném exception, exception được truyền ra để step áp dụng retry, skip hoặc fail policy.

## 1. CompositeItemProcessor là gì?

`CompositeItemProcessor<I, O>` là implementation của `ItemProcessor<I, O>`. Nó chứa một danh sách các processor delegate và chạy chúng theo thứ tự.

Ví dụ một pipeline xử lý đơn hàng:

1. Chuẩn hóa chuỗi và mã trạng thái.
2. Kiểm tra dữ liệu đầu vào.
3. Chuyển `OrderInput` thành `Order`.
4. Bổ sung phân khúc khách hàng.
5. Trả `EnrichedOrder` cho writer.

Sơ đồ:

~~~mermaid
flowchart LR
    A[OrderInput] --> B[NormalizeProcessor]
    B --> C[ValidateProcessor]
    C --> D[MapToOrderProcessor]
    D --> E[EnrichOrderProcessor]
    E --> F[EnrichedOrder]
    F --> G[ItemWriter]
~~~

Nếu không dùng composite, một class có thể phải thực hiện cả năm trách nhiệm. Khi dùng composite, mỗi delegate có thể tập trung vào một bước và có hợp đồng input/output riêng.

## 2. Nguyên tắc nối các delegate

Điều kiện quan trọng nhất là kiểu output của một delegate phải tương thích với kiểu input của delegate tiếp theo.

Ví dụ:

| Thứ tự | Processor | Input | Output |
|---|---|---|---|
| 1 | `NormalizeOrderProcessor` | `OrderInput` | `OrderInput` |
| 2 | `MapOrderProcessor` | `OrderInput` | `Order` |
| 3 | `EnrichOrderProcessor` | `Order` | `EnrichedOrder` |

Chuỗi có hợp đồng tổng thể là `ItemProcessor<OrderInput, EnrichedOrder>`.

Composite không tự chuyển đổi kiểu dữ liệu. Nếu delegate thứ nhất trả về `Customer` nhưng delegate tiếp theo yêu cầu `Order`, ứng dụng phải thiết kế lại chain hoặc thêm bước mapping phù hợp. Java generic giúp kiểm tra kiểu ở nhiều điểm khai báo, nhưng do type erasure và danh sách delegate có kiểu tổng quát, một số sai lệch có thể chỉ xuất hiện lúc chạy.

Hãy giữ kiểu của từng delegate cụ thể trong khai báo bean và tránh raw type hoặc cast không cần thiết. Tên delegate nên thể hiện rõ input/output hoặc trách nhiệm để người đọc dễ theo dõi luồng dữ liệu.

## 3. Viết các processor delegate nhỏ

Mỗi delegate nên làm một công việc có thể diễn đạt rõ ràng. Ví dụ, processor chuẩn hóa:

~~~java
public class NormalizeOrderProcessor
        implements ItemProcessor<OrderInput, OrderInput> {

    @Override
    public OrderInput process(OrderInput input) {
        return new OrderInput(
                input.orderId() == null
                        ? null : input.orderId().trim(),
                input.customerId() == null
                        ? null : input.customerId().trim(),
                input.amount(),
                input.status() == null
                        ? null : input.status().trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Delegate này chỉ chuẩn hóa biểu diễn. Nó không truy cập database và không quyết định một đơn hàng có được phép ghi hay không.

Processor kiểm tra dữ liệu:

~~~java
public class ValidateOrderProcessor
        implements ItemProcessor<OrderInput, OrderInput> {

    @Override
    public OrderInput process(OrderInput input) {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new InvalidOrderException("orderId is required");
        }
        if (input.customerId() == null || input.customerId().isBlank()) {
            throw new InvalidOrderException("customerId is required");
        }
        if (input.amount() == null || input.amount().signum() < 0) {
            throw new InvalidOrderException("amount must be non-negative");
        }
        return input;
    }
}
~~~

Delegate validation trả lại item nếu hợp lệ. Khi dữ liệu không hợp lệ, nó ném exception có ý nghĩa để step xử lý theo policy. Cách này giữ được thông tin lỗi và cho phép cấu hình skip/reject nếu nghiệp vụ cho phép.

Processor chuyển đổi sang domain object:

~~~java
public class MapOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        return new Order(
                input.orderId(),
                input.customerId(),
                input.amount(),
                OrderStatus.valueOf(input.status()));
    }
}
~~~

Processor enrichment có thể bổ sung dữ liệu tham chiếu:

~~~java
public class EnrichOrderProcessor
        implements ItemProcessor<Order, EnrichedOrder> {

    private final CustomerService customerService;

    public EnrichOrderProcessor(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Override
    public EnrichedOrder process(Order order) {
        Customer customer =
                customerService.getRequired(order.customerId());

        return new EnrichedOrder(
                order,
                customer.segment(),
                customer.region());
    }
}
~~~

Các ví dụ trên dùng record/constructor minh họa. Model thực tế có thể là JavaBean, record hoặc domain type phù hợp với ứng dụng.

## 4. Cấu hình CompositeItemProcessor

Có thể khai báo từng delegate thành Spring bean rồi ghép chúng trong một bean composite:

~~~java
@Bean
ItemProcessor<OrderInput, OrderInput> normalizeOrderProcessor() {
    return new NormalizeOrderProcessor();
}

@Bean
ItemProcessor<OrderInput, OrderInput> validateOrderProcessor() {
    return new ValidateOrderProcessor();
}

@Bean
ItemProcessor<OrderInput, Order> mapOrderProcessor() {
    return new MapOrderProcessor();
}

@Bean
ItemProcessor<Order, EnrichedOrder> enrichOrderProcessor(
        CustomerService customerService) {
    return new EnrichOrderProcessor(customerService);
}

@Bean
ItemProcessor<OrderInput, EnrichedOrder> orderProcessor(
        ItemProcessor<OrderInput, OrderInput> normalizeOrderProcessor,
        ItemProcessor<OrderInput, OrderInput> validateOrderProcessor,
        ItemProcessor<OrderInput, Order> mapOrderProcessor,
        ItemProcessor<Order, EnrichedOrder> enrichOrderProcessor)
        throws Exception {

    CompositeItemProcessor<OrderInput, EnrichedOrder> composite =
            new CompositeItemProcessor<>();

    composite.setDelegates(List.of(
            normalizeOrderProcessor,
            validateOrderProcessor,
            mapOrderProcessor,
            enrichOrderProcessor));

    composite.afterPropertiesSet();
    return composite;
}
~~~

`setDelegates` nhận danh sách processor theo đúng thứ tự thực thi. `afterPropertiesSet()` cho phép composite kiểm tra cấu hình bắt buộc trong giai đoạn khởi tạo bean. Trong ví dụ, các delegate được khai báo thành bean riêng nên có thể inject dependency, thay thế implementation và kiểm thử độc lập.

Nếu có nhiều bean cùng implement một kiểu generic giống nhau, nên dùng qualifier hoặc tên bean rõ ràng để tránh Spring inject nhầm candidate. Có thể khai báo tên cụ thể:

~~~java
@Bean("normalizeOrderProcessor")
ItemProcessor<OrderInput, OrderInput> normalizeOrderProcessor() {
    return new NormalizeOrderProcessor();
}
~~~

và inject bằng `@Qualifier("normalizeOrderProcessor")` khi cần phân biệt.

## 5. Gắn composite vào chunk step

Từ góc nhìn của step, composite chỉ là một `ItemProcessor<I, O>` thông thường. Reader cung cấp kiểu input của chain, writer nhận kiểu output cuối:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, EnrichedOrder> orderProcessor,
        ItemWriter<EnrichedOrder> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, EnrichedOrder>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

Step không cần biết có bao nhiêu delegate bên trong composite. Nó chỉ làm việc với hợp đồng tổng thể `OrderInput` sang `EnrichedOrder`.

Khi thay đổi nội bộ chain nhưng vẫn giữ nguyên input/output tổng thể, cấu hình reader và writer có thể giữ nguyên. Đây là một lợi ích quan trọng của composition.

## 6. Thứ tự delegate ảnh hưởng kết quả

Composite chạy delegate theo thứ tự trong danh sách. Đổi thứ tự có thể làm thay đổi kết quả hoặc khiến chain không còn đúng kiểu.

Ví dụ:

- Chuẩn hóa trước validation giúp `" ORD-1 "` được kiểm tra như `"ORD-1"`.
- Validation trước normalization có thể từ chối dữ liệu có khoảng trắng nếu rule yêu cầu chuỗi đã sạch.
- Mapping sang domain object phải xảy ra trước enrichment nếu enrichment nhận domain object.
- Enrichment trước validation có thể tạo query không cần thiết cho item chắc chắn bị loại.

Hãy sắp xếp chain theo dependency dữ liệu và chi phí xử lý. Những bước kiểm tra rẻ có thể đặt sớm để loại dữ liệu không hợp lệ trước khi gọi service hoặc database. Tuy nhiên, không thay đổi thứ tự chỉ vì hiệu năng nếu nó làm thay đổi semantics nghiệp vụ.

Một sơ đồ thứ tự tham khảo:

~~~text
Input
  -> normalize representation
  -> validate required fields
  -> map to domain
  -> enrich reference data
  -> output
~~~

## 7. Filter bằng cách trả về null

Theo contract của `ItemProcessor`, trả về `null` có nghĩa item bị filter. Trong `CompositeItemProcessor`, nếu một delegate trả `null`, composite dừng chuỗi cho item đó và trả `null` cho step. Những delegate đứng sau không được gọi.

Ví dụ filter đơn hàng bị hủy:

~~~java
public class ExcludeCancelledOrderProcessor
        implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        if (order.status() == OrderStatus.CANCELLED) {
            return null;
        }
        return order;
    }
}
~~~

Nếu filter delegate được đặt trước enrichment, đơn hàng CANCELLED không tạo thêm truy vấn lấy thông tin khách hàng. Nếu đặt sau enrichment, service đã được gọi trước khi item bị loại.

Filter không phải skip:

| Tình huống | Kết quả |
|---|---|
| Delegate trả object | Item tiếp tục qua delegate kế tiếp |
| Delegate trả `null` | Item bị filter; chain dừng |
| Delegate ném exception | Chain dừng do lỗi; step áp dụng retry/skip/fail policy |

Không trả `null` để che giấu lỗi service, lỗi chuyển đổi hoặc dữ liệu bắt buộc bị hỏng. Những trường hợp đó cần exception và chính sách xử lý rõ ràng.

## 8. Exception propagation qua composite

Nếu một delegate ném exception, composite không tự biến exception thành null hoặc tự quyết định skip. Exception được truyền ra khỏi lời gọi `process`; fault-tolerant step quyết định retry, skip hay fail.

Ví dụ:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, EnrichedOrder>chunk(100, transactionManager)
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

Trong ví dụ, exception validation được phân loại là skippable; lỗi dịch vụ tạm thời có thể retry theo giới hạn. Cần bảo đảm exception thực tế từ delegate đúng loại đã cấu hình. Nếu delegate bọc exception, giữ cause và cấu hình policy theo exception được framework nhìn thấy.

Không bắt mọi exception trong từng delegate rồi trả về object mặc định. Cách đó che giấu lỗi và có thể đưa dữ liệu sai tới writer.

## 9. Retry và việc chạy lại cả chain

Khi fault-tolerant step retry một item, cần thiết kế để việc gọi lại processor không gây tác dụng phụ ngoài ý muốn. Trong chain, một exception ở delegate thứ tư có thể khiến các delegate trước đó được chạy lại ở lần thử sau.

Ví dụ:

1. Normalize delegate chạy thành công.
2. Validation delegate chạy thành công.
3. Mapping delegate chạy thành công.
4. Enrichment delegate gọi service và timeout.
5. Step retry item; composite chạy lại từ delegate đầu.

Vì vậy, các delegate trước lỗi có thể được gọi nhiều lần. Điều này thường an toàn nếu chúng chỉ chuẩn hóa, kiểm tra hoặc tạo object mới. Nó có thể nguy hiểm nếu chúng ghi database, gửi message hoặc thực hiện thao tác không idempotent.

Các nguyên tắc:

- Giữ processor delegate thuần hoặc chỉ thực hiện thao tác đọc an toàn.
- Nếu phải gọi service có side effect, dùng idempotency key hoặc chuyển tác động sang writer/outbox.
- Không lưu “đã xử lý item” chỉ trong field bộ nhớ của delegate.
- Phân biệt lỗi tạm thời có thể retry với lỗi dữ liệu không nên retry.
- Đặt retry limit và backoff phù hợp với dependency.

Composite không tạo checkpoint giữa các delegate. Checkpoint và transaction thuộc lifecycle của step/chunk, không phải từng mắt xích trong chain.

## 10. Chọn vị trí validation và filter

Vị trí của validation/filter có ảnh hưởng tới chi phí và ý nghĩa dữ liệu:

| Bước | Mục tiêu | Vị trí thường hợp lý |
|---|---|---|
| Kiểm tra trường bắt buộc | Phát hiện input không thể xử lý | Sớm, sau chuẩn hóa tối thiểu |
| Kiểm tra enum/code | Chặn giá trị không hỗ trợ | Trước mapping hoặc ngay khi map |
| Filter theo điều kiện đơn giản | Loại item không cần xử lý tiếp | Trước enrichment tốn kém |
| Kiểm tra trạng thái tham chiếu | Xác minh dữ liệu từ hệ thống khác | Sau khi có khóa cần tra cứu |
| Chuẩn hóa output | Đưa dữ liệu về dạng writer cần | Gần cuối chain nếu là format đầu ra |

Không có thứ tự duy nhất đúng cho mọi job. Ví dụ, nếu normalization làm thay đổi dữ liệu dùng để tra cứu, nó phải xảy ra trước enrichment. Nếu filter dựa trên dữ liệu chỉ có sau enrichment, filter phải đặt sau bước đó.

Hãy mô tả rõ mỗi delegate nhận dữ liệu nào, trả dữ liệu nào và điều kiện nào khiến item bị filter hoặc ném exception. Điều này giúp người bảo trì hiểu tại sao một item không tới writer.

## 11. Kết hợp với ValidatingItemProcessor

`ValidatingItemProcessor<T>` là một delegate có sẵn để chạy `Validator<T>`. Nó có thể được đặt trong chain khi kiểu input/output tại vị trí đó vẫn là `T`.

Ví dụ:

~~~java
@Bean
ItemProcessor<OrderInput, OrderInput> validationProcessor(
        Validator<OrderInput> orderValidator) {

    ValidatingItemProcessor<OrderInput> processor =
            new ValidatingItemProcessor<>(orderValidator);
    return processor;
}
~~~

Composite có thể kết hợp normalize, validate và map:

~~~java
composite.setDelegates(List.of(
        normalizeOrderProcessor,
        validationProcessor,
        mapOrderProcessor));
~~~

Mặc định, validation failure được biểu diễn bằng exception. Nếu cấu hình `filter` trên `ValidatingItemProcessor`, validation failure có thể khiến item bị loại. Chọn hành vi dựa trên nghiệp vụ: dữ liệu sai cần reject/audit thường nên phát sinh exception để listener lưu lý do; item không cần xử lý theo điều kiện bình thường có thể được filter.

## 12. Dùng CompositeItemProcessor với các kiểu dữ liệu trung gian

Các delegate không cần cùng một kiểu input/output. Điểm mạnh của composite là nối được các kiểu trung gian:

~~~java
ItemProcessor<RawOrderRow, NormalizedOrderRow>
ItemProcessor<NormalizedOrderRow, ValidatedOrder>
ItemProcessor<ValidatedOrder, EnrichedOrder>
ItemProcessor<EnrichedOrder, OrderEntity>
~~~

Hợp đồng tổng thể:

~~~java
ItemProcessor<RawOrderRow, OrderEntity>
~~~

Mỗi kiểu trung gian nên thể hiện trạng thái dữ liệu rõ ràng. Ví dụ `NormalizedOrderRow` có nghĩa chuỗi đã được chuẩn hóa; `ValidatedOrder` có nghĩa các điều kiện cơ bản đã được kiểm tra. Cách đặt tên này giúp giảm việc truyền một DTO tổng quát có nhiều field nullable và không rõ field nào đã sẵn sàng.

Không cần tạo class trung gian cho mọi phép biến đổi một dòng. Chỉ tạo kiểu mới khi nó làm rõ ranh giới hoặc bất biến dữ liệu. Với biến đổi nhỏ không làm thay đổi hợp đồng, có thể giữ nguyên kiểu input/output.

## 13. CompositeItemProcessor không phải bộ phân nhánh

Composite thực hiện tất cả delegate theo thứ tự cho mỗi item, trừ khi một delegate trả null hoặc ném exception. Nó không chọn một delegate duy nhất theo loại item.

Nếu cần chọn processor theo loại record, dùng classifier như `ClassifierCompositeItemProcessor` hoặc tự viết một processor điều phối theo loại dữ liệu. Ví dụ:

~~~text
ImportRecord
  -> CustomerRecord: CustomerProcessor
  -> OrderRecord: OrderProcessor
  -> PaymentRecord: PaymentProcessor
~~~

Sau khi xử lý riêng theo loại, có thể dùng một composite khác bên trong từng nhánh nếu nhánh đó cũng có nhiều bước tuần tự.

Không dùng composite chỉ để mô phỏng if/else bằng các delegate trả null. Điều đó làm flow khó hiểu và có thể khiến nhiều delegate chạy không cần thiết.

## 14. CompositeItemProcessor không chạy song song

Tên “composite” chỉ việc ghép các processor; nó không có nghĩa các delegate được chạy đồng thời. Với một item, thứ tự gọi là tuần tự:

~~~text
delegate 1 -> delegate 2 -> delegate 3 -> output
~~~

Nếu delegate thứ hai cần kết quả của delegate thứ nhất, tuần tự là điều bắt buộc. Nếu mục tiêu là tăng throughput, concurrency được cấu hình ở step/partition/flow level qua TaskExecutor hoặc partitioning, không phải bằng cách đổi danh sách delegate.

Khi step chạy nhiều thread, nhiều item có thể đi qua cùng composite đồng thời. Vì vậy, composite và các delegate dùng chung cần an toàn khi được gọi đồng thời. Không đặt mutable current item hoặc state theo lần gọi trong field singleton.

## 15. Thread safety của composite và delegate

Composite chủ yếu giữ danh sách delegate và gọi chúng theo thứ tự. Nhưng điều đó không tự làm delegate thread-safe. Nếu cùng composite bean được nhiều worker gọi, mỗi delegate cũng có thể được gọi đồng thời.

Ưu tiên:

- Delegate stateless, dùng biến local trong `process`.
- Dependency đọc dữ liệu an toàn và có connection/transaction theo thread.
- Cấu hình immutable sau khi bean được khởi tạo.
- Không giữ `currentItem`, `currentBatchId` hoặc buffer mutable dùng chung trong field.
- Nếu có state riêng theo partition, truyền qua StepExecutionContext và tạo target phù hợp bằng StepScope.

StepScope gắn với StepExecution, không đồng nghĩa một instance mới cho mỗi chunk thread trong multi-threaded step. Nếu target processor của cùng step bị gọi đồng thời, nó vẫn phải thread-safe. Với partitioning, mỗi worker có StepExecution riêng nên StepScope thường phù hợp hơn cho state thuộc worker.

## 16. Side effect và idempotency

Một delegate có thể được gọi lại khi chunk rollback, retry hoặc restart. Vì vậy, tránh thực hiện side effect không thể hoàn tác trong `process`.

Ví dụ không an toàn:

~~~java
public Order process(OrderInput input) {
    paymentGateway.charge(input.paymentToken(), input.amount());
    return mapToOrder(input);
}
~~~

Nếu delegate này chạy thành công nhưng một delegate phía sau ném exception, step có thể retry cả item. Lệnh charge có thể được gửi lần nữa.

Thiết kế an toàn hơn:

1. Các delegate xác thực, chuẩn hóa và tạo command.
2. Writer ghi dữ liệu hoặc outbox record trong transaction.
3. Dispatcher gửi tác động bên ngoài sau commit.
4. API ngoài nhận idempotency key ổn định để chống lặp.
5. Có quy trình reconciliation khi kết quả gọi ngoài không rõ ràng.

Một delegate gọi service chỉ đọc thường ít rủi ro hơn, nhưng vẫn cần timeout, giới hạn retry và xử lý trạng thái dữ liệu thay đổi.

## 17. Hiệu năng của processor chain

Mỗi item đi qua từng delegate cho tới khi chain kết thúc. Nếu có N item và K delegate, số lần gọi có thể lên tới N × K trong trường hợp tất cả item đi qua toàn bộ chain.

Để chain hiệu quả:

- Đặt bước kiểm tra rẻ và có khả năng loại item sớm trước các bước tốn kém.
- Tránh tạo object trung gian quá lớn nếu không cần thiết.
- Không query database riêng cho mỗi delegate nếu có thể gộp hoặc bulk lookup.
- Cache dữ liệu tham chiếu chỉ khi semantics và lifetime rõ ràng.
- Tránh logging payload ở mức INFO cho mọi delegate/item.
- Đo thời gian theo từng delegate để xác định bottleneck.
- Giới hạn concurrency theo năng lực database và API ngoài.

Không gộp mọi bước vào một processor chỉ để giảm số lần gọi method nếu điều đó làm mất ranh giới trách nhiệm và khả năng kiểm thử. Chi phí gọi method Java thường nhỏ so với I/O; cần đo trước khi tối ưu.

## 18. Logging và quan sát từng delegate

Có thể dùng `ItemProcessListener` ở cấp step để quan sát toàn bộ lời gọi processor được cấu hình. Nếu cần đo thời gian từng delegate, có thể bọc delegate bằng decorator hoặc dùng metrics ở bên trong delegate.

Ví dụ decorator đo thời gian:

~~~java
public class TimedProcessor<I, O> implements ItemProcessor<I, O> {

    private final String name;
    private final ItemProcessor<I, O> delegate;
    private final Timer timer;

    public TimedProcessor(
            String name,
            ItemProcessor<I, O> delegate,
            MeterRegistry registry) {
        this.name = name;
        this.delegate = delegate;
        this.timer = registry.timer("batch.processor.duration", "delegate", name);
    }

    @Override
    public O process(I item) throws Exception {
        return timer.recordCallable(() -> delegate.process(item));
    }
}
~~~

Ví dụ cần điều chỉnh theo API metrics đang dùng và exception contract của dự án. Không ghi toàn bộ item vào metric tag vì cardinality có thể tăng không giới hạn. Tag nên là tên delegate hoặc step, không phải ID từng record.

Khi log lỗi, giữ source ID hoặc correlation ID, tên delegate nếu có và exception cause. Tránh log dữ liệu nhạy cảm hoặc thông tin xác thực.

## 19. Kiểm thử từng delegate

Mỗi delegate có thể được unit test độc lập. Điều này giúp xác định lỗi thuộc normalization, validation, mapping hay enrichment mà không phải chạy toàn bộ job.

Ví dụ test normalization:

~~~java
@Test
void trimsIdentifiersAndNormalizesStatus() throws Exception {
    NormalizeOrderProcessor processor =
            new NormalizeOrderProcessor();

    OrderInput input = new OrderInput(
            " ORD-10 ",
            " CUS-20 ",
            new BigDecimal("12.50"),
            " active ");

    OrderInput result = processor.process(input);

    assertEquals("ORD-10", result.orderId());
    assertEquals("CUS-20", result.customerId());
    assertEquals("ACTIVE", result.status());
}
~~~

Unit test của từng delegate nên tập trung vào hợp đồng của delegate đó: input hợp lệ, biên, null, exception và output. Enrichment delegate nên mock dependency để kiểm tra cách xử lý customer không tồn tại hoặc service timeout.

## 20. Kiểm thử toàn bộ CompositeItemProcessor

Ngoài test từng delegate, cần test thứ tự và hành vi của composite:

1. Các delegate được gọi đúng thứ tự.
2. Output của delegate trước được truyền vào delegate sau.
3. Output cuối có đúng kiểu và giá trị writer mong đợi.
4. Delegate trả null làm chain dừng; delegate phía sau không được gọi.
5. Delegate ném exception làm chain dừng và exception được truyền ra.
6. Cấu hình rỗng hoặc thiếu delegate bắt buộc bị phát hiện khi khởi tạo theo contract phiên bản đang dùng.
7. Chain có các kiểu trung gian khác nhau hoạt động đúng.
8. Nhiều lần gọi cùng input cho kết quả xác định.
9. Concurrent calls không trộn state.
10. Retry gọi lại chain không tạo side effect duplicate.

Có thể dùng Mockito để kiểm tra thứ tự:

~~~java
InOrder order = inOrder(normalizeProcessor, mapProcessor, enrichProcessor);

composite.process(input);

order.verify(normalizeProcessor).process(input);
order.verify(mapProcessor).process(normalizedInput);
order.verify(enrichProcessor).process(mappedOrder);
~~~

Ví dụ giả định các delegate là mock và composite đã được cấu hình với chúng. Khi test output, nên kiểm tra cả giá trị trả về thay vì chỉ xác nhận method đã được gọi.

## 21. Integration test trong chunk step

Unit test composite không chứng minh step đã nối reader, processor và writer đúng. Integration test nên chạy step với dữ liệu nhỏ và writer có thể quan sát kết quả.

Ví dụ các assertion cần có:

- Job/step hoàn thành với input hợp lệ.
- Writer nhận đúng kiểu output cuối của chain.
- Item filter không xuất hiện trong writer.
- Invalid item được xử lý theo skip/fail policy đã cấu hình.
- Skip listener lưu đúng source ID và nguyên nhân.
- Retry không tạo output hoặc side effect trùng.
- Filter count, process skip count và write count khớp với tập dữ liệu test.

Nếu processor gọi database hoặc API, dùng integration test cho transaction/retry boundary phù hợp. Không chỉ mock tất cả dependency rồi kết luận side effect an toàn.

## 22. Những lỗi thường gặp

**Đảo thứ tự delegate.** Output có thể chưa được chuẩn hóa hoặc chưa có dữ liệu cần thiết cho bước kế tiếp. Khai báo chain theo dependency và kiểm thử thứ tự.

**Kiểu output không khớp input tiếp theo.** Composite không tự convert type. Dùng kiểu trung gian rõ ràng và generic cụ thể.

**Nghĩ composite chạy song song.** Các delegate của một item chạy tuần tự. Concurrency được cấu hình ở step/partition/flow.

**Delegate trả null quá sớm.** Item bị filter và những bước sau không chạy. Chỉ filter khi đó là quyết định nghiệp vụ chủ đích.

**Bắt exception rồi trả null.** Lỗi biến thành filter im lặng. Ném exception phù hợp để step áp dụng policy.

**Gọi side effect trong delegate.** Retry có thể chạy lại các delegate trước đó. Dùng idempotency hoặc outbox cho tác động bên ngoài.

**Một delegate giữ mutable state trong singleton.** Nhiều item/thread có thể ghi đè state. Giữ delegate stateless hoặc bảo vệ state đúng cách.

**Enrichment tạo N+1 query.** Mỗi item có thể phát sinh nhiều lần gọi database. Đo và cân nhắc join, cache hoặc bulk lookup.

**Không kiểm tra null ở đầu chain.** Một input null không hợp lệ có thể gây lỗi khó hiểu trong delegate đầu. Xác định contract của reader và kiểm tra dữ liệu ở ranh giới phù hợp.

**Chain quá dài và khó đọc.** Tách class không có nghĩa là tạo hàng chục bước vụn vặt. Giữ mỗi delegate có trách nhiệm và giá trị độc lập.

## 23. Quy trình thiết kế CompositeItemProcessor

Khi xây dựng một composite, hãy thực hiện theo thứ tự:

1. Xác định kiểu item reader trả về và kiểu writer cần nhận.
2. Chia pipeline thành các bước có trách nhiệm rõ ràng.
3. Xác định input/output type của từng delegate và bảo đảm các mắt xích tương thích.
4. Quyết định bước nào transform, validate, enrich hoặc filter.
5. Đặt validation rẻ và filter sớm nếu điều đó giữ nguyên semantics nghiệp vụ.
6. Khai báo từng delegate thành bean và ghép theo đúng thứ tự.
7. Gắn composite vào step như một ItemProcessor thông thường.
8. Cấu hình retry/skip theo exception type thực tế từ delegate.
9. Kiểm tra thread safety và idempotency của toàn bộ chain.
10. Viết unit test từng delegate, test chain và integration test step.
11. Theo dõi latency, filter count, process skip count và output reconciliation.

## Kết luận

`CompositeItemProcessor<I, O>` kết hợp nhiều `ItemProcessor` thành một pipeline tuần tự cho từng item. Output của delegate này được truyền làm input cho delegate kế tiếp; kiểu dữ liệu giữa các mắt xích phải tương thích. Composite trả kết quả cuối cho writer, dừng chain khi một delegate trả `null`, và truyền exception ra để step áp dụng retry, skip hoặc fail policy.

Hãy chia logic thành delegate có trách nhiệm rõ như normalize, validate, map và enrich; khai báo generic cụ thể; ghép đúng thứ tự; và giữ các delegate stateless, có thể chạy lại an toàn. Composite không tạo transaction, không chạy delegate song song và không tự làm side effect trở nên idempotent. Kiểm thử từng delegate, thứ tự chain, filter/exception propagation và toàn bộ step để bảo đảm pipeline xử lý đúng dữ liệu trước khi ghi.

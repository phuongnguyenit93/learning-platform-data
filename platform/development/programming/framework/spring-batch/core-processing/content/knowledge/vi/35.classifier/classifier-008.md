# Classifier có state

Trong Spring Batch, Classifier thường được dùng để chọn một delegate phù hợp với từng item. Ví dụ, một giao dịch BUY được chuyển tới processor xử lý mua, một giao dịch SELL được chuyển tới processor xử lý bán. Cách triển khai đơn giản nhất là classifier chỉ đọc dữ liệu đầu vào và trả về delegate tương ứng.

Tuy nhiên, trong một số hệ thống, classifier còn giữ state: cache thông tin định tuyến, đếm số lần phân loại, lưu cấu hình theo execution hoặc áp dụng chính sách dựa trên trạng thái của một lần chạy. Khi đó, cần xác định state thuộc phạm vi nào, ai cập nhật nó, có được chia sẻ giữa các thread hay không và có cần khôi phục khi restart hay không.

Một classifier có state không mặc nhiên là sai. Rủi ro xuất hiện khi state làm thay đổi kết quả phân loại theo thứ tự lời gọi, trong khi Spring Batch có thể retry item, rollback chunk, chạy song song hoặc restart Step. Thiết kế cần bảo đảm cùng một item được định tuyến nhất quán theo quy tắc nghiệp vụ, hoặc có cơ chế lưu quyết định định tuyến đủ bền vững để khôi phục.

## 1. Classifier trong Spring Batch

Classifier là một abstraction nhận một đối tượng đầu vào và trả về một kết quả phân loại. Trong Spring, interface có dạng tổng quát:

~~~java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
~~~

Trong Spring Batch, ClassifierCompositeItemProcessor sử dụng Classifier để chọn ItemProcessor cho item hiện tại:

~~~text
ItemReader
    |
    v
Input item
    |
    v
ClassifierCompositeItemProcessor
    |
    v
Classifier.classify(item)
    |
    +---- Route A ----> Processor A
    |
    +---- Route B ----> Processor B
    |
    +---- Route C ----> Processor C
    |
    v
Output item
    |
    v
ItemWriter
~~~

Một classifier stateless thường chỉ dựa vào thuộc tính của item và cấu hình bất biến:

~~~java
public class PaymentClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final ItemProcessor<Payment, PaymentResult> cardProcessor;
    private final ItemProcessor<Payment, PaymentResult> transferProcessor;

    public PaymentClassifier(
            ItemProcessor<Payment, PaymentResult> cardProcessor,
            ItemProcessor<Payment, PaymentResult> transferProcessor) {
        this.cardProcessor = cardProcessor;
        this.transferProcessor = transferProcessor;
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        return switch (payment.type()) {
            case CARD -> cardProcessor;
            case TRANSFER -> transferProcessor;
        };
    }
}
~~~

Classifier này không cần nhớ item trước đó. Với cùng một Payment có cùng type, nó luôn chọn cùng delegate. Đây thường là hành vi dễ hiểu, dễ kiểm thử và an toàn hơn khi retry/restart.

## 2. State trong classifier có thể là gì?

Từ state có thể chỉ nhiều loại dữ liệu khác nhau. Cần phân biệt chúng trước khi quyết định cách lưu và đồng bộ:

| Loại state | Ví dụ | Mục đích |
|---|---|---|
| Configuration state | Map loại giao dịch sang processor | Quyết định route theo cấu hình |
| Cache state | Cache route hoặc policy tra cứu từ dịch vụ ngoài | Giảm chi phí tra cứu lặp lại |
| Execution state | Số lần đã xử lý trong một StepExecution, chế độ của partition | Phản ánh tiến độ của lần chạy |
| Metrics state | Số lần classifier chọn từng nhánh | Quan sát tải và hành vi định tuyến |
| Business state | Quyết định một hồ sơ đã chuyển qua giai đoạn nào | Thể hiện trạng thái nghiệp vụ |
| Invocation-order state | Bộ đếm tăng sau mỗi lần classify để chọn nhánh tiếp theo | Định tuyến dựa trên thứ tự gọi |

Configuration state thường nên bất biến sau khi bean được tạo. Cache và metrics có thể thay đổi trong runtime nhưng cần thread safety. Execution state cần gắn với đúng JobExecution, StepExecution hoặc partition. Business state nên được quản lý bởi hệ thống nghiệp vụ có tính bền vững. Invocation-order state là loại cần thận trọng nhất vì retry, rollback và concurrency có thể làm thay đổi thứ tự gọi.

Không nên gom mọi loại dữ liệu này vào một field mutable duy nhất. Mỗi state cần có chủ sở hữu, vòng đời và quy tắc khôi phục riêng.

## 3. Vì sao cần classifier có state?

Một classifier có state có thể hữu ích trong một số trường hợp:

- Cache kết quả tra cứu policy để không gọi dịch vụ cấu hình cho từng item.
- Giữ registry route được nạp khi Step bắt đầu.
- Thu thập số lần classifier chọn từng delegate để phục vụ metrics.
- Dùng thông tin riêng của StepExecution hoặc partition để chọn cách xử lý.
- Giữ một snapshot cấu hình ổn định trong suốt một lần chạy.

Ví dụ, hệ thống có thể nạp mapping loại giao dịch và phiên bản chính sách từ database trước khi Step chạy. Classifier dùng snapshot đó để định tuyến nhất quán trong cả Step. State này hữu ích vì các item không phải truy vấn lại cấu hình cho mỗi lần phân loại.

Ngược lại, nếu classifier tăng bộ đếm rồi luân phiên chọn processor A, B, A, B, route của item phụ thuộc vào số lần classify trước đó. Kiểu state này thường không phù hợp cho nghiệp vụ cần restart và retry chính xác.

## 4. Stateful không đồng nghĩa với mutable tùy ý

Một component có thể chứa state nhưng vẫn an toàn nếu state bất biến sau khi khởi tạo. Ví dụ, Map route được tạo từ cấu hình rồi đóng băng:

~~~java
public class PaymentClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final Map<PaymentType, ItemProcessor<Payment, PaymentResult>> routes;

    public PaymentClassifier(
            Map<PaymentType, ItemProcessor<Payment, PaymentResult>> routes) {
        this.routes = Map.copyOf(routes);
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        ItemProcessor<Payment, PaymentResult> processor =
                routes.get(payment.type());

        if (processor == null) {
            throw new IllegalArgumentException(
                    "Unsupported payment type: " + payment.type());
        }
        return processor;
    }
}
~~~

Classifier giữ một Map trong field, nhưng không sửa Map sau khi constructor hoàn tất. Nếu các delegate cũng đáp ứng thread-safety, nhiều thread có thể đọc cấu hình này đồng thời.

Map.copyOf bảo vệ cấu trúc map khỏi thay đổi qua tham chiếu map được trả về. Nó không tự làm các object processor bên trong trở thành immutable hoặc thread-safe. Cần đánh giá từng delegate riêng.

## 5. Ví dụ cache state trong classifier

Giả sử route phụ thuộc vào một policy được tra cứu theo tenant. Nếu mỗi item đều gọi PolicyService, Job có thể tạo ra nhiều truy vấn lặp lại. Một cache có thể lưu policy đã tra:

~~~java
public class TenantClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final PolicyService policyService;
    private final Map<PaymentType, ItemProcessor<Payment, PaymentResult>> routes;
    private final ConcurrentMap<String, PaymentType> tenantPolicyCache =
            new ConcurrentHashMap<>();

    public TenantClassifier(
            PolicyService policyService,
            Map<PaymentType, ItemProcessor<Payment, PaymentResult>> routes) {
        this.policyService = policyService;
        this.routes = Map.copyOf(routes);
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        PaymentType selectedType = tenantPolicyCache.computeIfAbsent(
                payment.tenantId(),
                policyService::findPaymentType);

        ItemProcessor<Payment, PaymentResult> processor = routes.get(selectedType);
        if (processor == null) {
            throw new IllegalStateException(
                    "No processor configured for " + selectedType);
        }
        return processor;
    }
}
~~~

Ví dụ này minh họa cache theo tenant. Trước khi dùng trong production, cần quyết định:

- Policy có thể thay đổi trong lúc Job đang chạy hay không?
- Cache cần sống trong một StepExecution, một JobExecution hay toàn application?
- Có cần hết hạn cache hoặc làm mới theo version không?
- Nếu lookup thất bại tạm thời, có retry được không?
- Nếu nhiều thread cùng lookup một tenant, có chấp nhận một lần load hay cần cơ chế khác?

ConcurrentHashMap hỗ trợ truy cập đồng thời cho map. computeIfAbsent giúp tính toán và cài đặt giá trị theo key một cách phối hợp trong map. Tuy nhiên, hàm mapping không nên có side effect khó lặp lại và không nên gọi lại chính map theo cách gây đệ quy. Cũng cần chú ý exception: nếu lookup ném lỗi, giá trị không được cache và lần gọi sau có thể thử lại.

Cache chỉ phù hợp nếu policy được phép dùng lại trong khoảng thời gian xác định. Nếu policy thay đổi giữa Job, cần pin policy version vào JobParameters hoặc ExecutionContext để tất cả item của cùng execution dùng cùng một snapshot.

## 6. Metrics state: đếm lượt phân loại

Classifier có thể giữ bộ đếm kỹ thuật để biết mỗi nhánh được chọn bao nhiêu lần:

~~~java
public class CountingPaymentClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final PaymentClassifier delegate;
    private final ConcurrentMap<PaymentType, LongAdder> counts =
            new ConcurrentHashMap<>();

    public CountingPaymentClassifier(PaymentClassifier delegate) {
        this.delegate = delegate;
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        counts.computeIfAbsent(payment.type(), key -> new LongAdder()).increment();
        return delegate.classify(payment);
    }

    public long countFor(PaymentType type) {
        LongAdder count = counts.get(type);
        return count == null ? 0L : count.sum();
    }
}
~~~

LongAdder phù hợp với bộ đếm có nhiều cập nhật đồng thời. Nó giảm tranh chấp so với một AtomicLong duy nhất trong một số workload nhiều thread. Giá trị sum() là số lượt classify đã ghi nhận, không nhất thiết là số item đã commit.

Một item có thể được classify nhiều lần khi retry hoặc khi framework cô lập item lỗi. Một chunk có thể rollback sau khi classifier đã tăng counter. Vì vậy, không dùng counter này làm số bản ghi nghiệp vụ đã ghi thành công. Muốn đếm số item commit, hãy lấy thông tin từ database, StepExecution counters hoặc một cơ chế audit gắn với transaction commit.

## 7. State phụ thuộc thứ tự lời gọi có rủi ro gì?

Ví dụ sau dùng bộ đếm để luân phiên route:

~~~java
public class RoundRobinClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final AtomicInteger next = new AtomicInteger();
    private final List<ItemProcessor<Payment, PaymentResult>> processors;

    public RoundRobinClassifier(
            List<ItemProcessor<Payment, PaymentResult>> processors) {
        this.processors = List.copyOf(processors);
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        int index = Math.floorMod(next.getAndIncrement(), processors.size());
        return processors.get(index);
    }
}
~~~

AtomicInteger bảo vệ phép tăng bộ đếm khi nhiều thread gọi cùng lúc. Nhưng nó chỉ giải quyết race condition ở bộ đếm; nó không bảo đảm định tuyến ổn định theo item.

Giả sử lần đầu:

~~~text
classify item A -> Processor 0
classify item B -> Processor 1
classify item C -> Processor 0
~~~

Nếu item B được retry, lần gọi tiếp theo có thể nhận Processor 1 hoặc Processor 0 tùy các item khác đã gọi classify trước đó. Khi chạy song song, thứ tự lấy giá trị counter còn phụ thuộc scheduling của thread. Sau restart, counter có thể được khởi tạo lại từ đầu.

Nếu delegate A và B có quy tắc nghiệp vụ khác nhau, cùng một item có thể được xử lý theo hai cách khác nhau. Đây là rủi ro dữ liệu, không phải chỉ là sai số metrics.

Round-robin chỉ nên dùng nếu mục tiêu là phân phối tải không gắn với ý nghĩa nghiệp vụ, các delegate có hành vi tương đương và hệ thống chấp nhận thứ tự phân phối thay đổi khi retry/restart. Nếu yêu cầu phân phối ổn định, dùng routing key xác định thay vì bộ đếm lời gọi.

## 8. Dùng routing key ổn định thay cho bộ đếm

Nếu mục tiêu là chia item vào nhiều processor hoặc worker một cách ổn định, có thể tính route từ khóa bất biến của item:

~~~java
public class StableShardClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final List<ItemProcessor<Payment, PaymentResult>> processors;

    public StableShardClassifier(
            List<ItemProcessor<Payment, PaymentResult>> processors) {
        if (processors.isEmpty()) {
            throw new IllegalArgumentException("At least one processor is required");
        }
        this.processors = List.copyOf(processors);
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        int index = Math.floorMod(
                payment.paymentId().hashCode(),
                processors.size());
        return processors.get(index);
    }
}
~~~

Với cùng paymentId và cùng danh sách processor, route luôn giống nhau. Retry không làm item tự chuyển sang nhánh khác.

Nếu danh sách processor thay đổi kích thước hoặc thứ tự, hash modulo có thể tạo route khác. Khi route cần ổn định qua nhiều phiên bản triển khai, cần version hóa thuật toán, giữ số shard ổn định hoặc dùng consistent hashing với cấu hình được pin theo JobExecution.

Đối với nghiệp vụ, thường nên định tuyến theo type, tenant, region hoặc một business key rõ ràng thay vì phân phối tùy ý theo bộ đếm.

## 9. State theo JobExecution và StepExecution

Một classifier có thể cần dữ liệu thay đổi theo từng lần chạy, ví dụ:

- Policy version được chọn khi launch Job.
- Region được gán cho worker partition.
- Ngưỡng xử lý riêng cho Step.
- Mapping route được xác định từ tham số đầu vào.

Không nên giữ những giá trị này trong field của singleton dùng chung giữa nhiều JobExecution. Hãy dùng JobParameters, JobExecutionContext hoặc StepExecutionContext theo đúng phạm vi.

| Nguồn state | Phạm vi | Khi phù hợp |
|---|---|---|
| JobParameters | Đầu vào của JobExecution | File, ngày nghiệp vụ, policy version |
| JobExecutionContext | Một JobExecution, có thể chia sẻ giữa các Step | Metadata được tạo trong quá trình Job |
| StepExecutionContext | Một StepExecution | Checkpoint hoặc cấu hình riêng của Step/partition |
| Bean @JobScope | Một JobExecution | Dependency cần state theo Job |
| Bean @StepScope | Một StepExecution | Dependency cần state theo Step |
| Singleton immutable | Application context | Cấu hình chung không đổi |

Scope điều khiển vòng đời bean; ExecutionContext lưu dữ liệu cần khôi phục. Hai khái niệm có liên quan nhưng không thay thế nhau.

## 10. Dùng @StepScope cho classifier

Nếu classifier cần nhận cấu hình riêng của Step, có thể khai báo bean với @StepScope:

~~~java
@Bean
@StepScope
PaymentClassifier paymentClassifier(
        @Value("#{stepExecutionContext['routeMode']}") String routeMode,
        CardPaymentProcessor cardProcessor,
        TransferPaymentProcessor transferProcessor) {

    return new PaymentClassifier(routeMode, cardProcessor, transferProcessor);
}
~~~

Ví dụ này giả định PaymentClassifier được thiết kế nhận routeMode qua constructor và chỉ sử dụng giá trị đó trong phạm vi StepExecution. Classifier có thể chọn cách định tuyến theo routeMode.

@StepScope giúp mỗi StepExecution có target bean riêng. Nó không tự làm target thread-safe nếu nhiều thread trong cùng StepExecution cùng gọi classifier. Nếu classifier có mutable field được cập nhật trong classify(), cần đồng bộ hoặc thiết kế lại để state không bị chia sẻ nguy hiểm.

Nếu cần giá trị chung cho toàn Job, @JobScope có thể phù hợp hơn. Tuy nhiên, một bean JobScope vẫn có thể được truy cập đồng thời bởi các Step chạy song song trong cùng JobExecution; scope không phải khóa đồng bộ.

## 11. Lưu state cần restart bằng ExecutionContext

Classifier interface chỉ có method classify(). Nó không tự cung cấp callback open/update/close và Spring Batch không tự động persist field của classifier vào JobRepository.

Nếu state của classifier phải được khôi phục khi restart, cần tích hợp lifecycle hoặc lưu state qua một thành phần được Step quản lý. Một cách là để classifier triển khai ItemStream và đăng ký stream đó với Step:

~~~java
public class StatefulClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>>,
                   ItemStream {

    private static final String ROUTE_COUNT_KEY =
            "paymentClassifier.routeCount";

    private final ItemProcessor<Payment, PaymentResult> primary;
    private final ItemProcessor<Payment, PaymentResult> secondary;
    private long routeCount;

    public StatefulClassifier(
            ItemProcessor<Payment, PaymentResult> primary,
            ItemProcessor<Payment, PaymentResult> secondary) {
        this.primary = primary;
        this.secondary = secondary;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        routeCount = executionContext.getLong(ROUTE_COUNT_KEY, 0L);
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        boolean usePrimary = (routeCount++ % 2L) == 0L;
        return usePrimary ? primary : secondary;
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putLong(ROUTE_COUNT_KEY, routeCount);
    }

    @Override
    public void close() {
        // Không có resource cần giải phóng trong ví dụ này.
    }
}
~~~

Đăng ký composite như processor và classifier như stream của Step:

~~~java
@Bean
Step paymentStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Payment> reader,
        ClassifierCompositeItemProcessor<Payment, PaymentResult> processor,
        StatefulClassifier classifier,
        ItemWriter<PaymentResult> writer) {

    return new StepBuilder("paymentStep", jobRepository)
            .<Payment, PaymentResult>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .stream(classifier)
            .build();
}
~~~

Đăng ký stream giúp Step gọi lifecycle ItemStream để mở, cập nhật và đóng state. Chỉ triển khai ItemStream mà không đăng ký component với Step thì không đủ để bảo đảm các callback được gọi.

Ví dụ trên minh họa cơ chế lưu/khôi phục state, nhưng bộ đếm luân phiên vẫn có vấn đề với retry và concurrency. update() ghi state tại checkpoint của Step, không biến mỗi lần classify thành một quyết định route được commit nguyên tử cùng item. Nếu chunk rollback hoặc một item được retry, routeCount có thể đã thay đổi trong memory. Trong multi-threaded Step, nhiều thread còn có thể cập nhật counter đồng thời.

Vì vậy, không dùng mẫu luân phiên này cho quyết định nghiệp vụ cần tính xác định. Với state quan trọng, hãy lưu quyết định route theo business key trong database hoặc xác định route từ dữ liệu bất biến.

## 12. Thứ tự update và rollback cần được hiểu đúng

ExecutionContext và transaction của chunk được Spring Batch quản lý theo lifecycle của Step. ItemStream.update() được gọi ở các mốc cập nhật trạng thái của stream, thường trong quá trình xử lý chunk trước khi transaction hoàn tất.

Không nên coi việc tăng field trong classifier là một thay đổi đã commit. Một chunk có thể:

1. Gọi classifier cho một số item.
2. Tăng state trong bộ nhớ.
3. Gọi writer.
4. Gặp lỗi và rollback transaction.
5. Retry item hoặc chunk.

State trong bộ nhớ không tự rollback cùng transaction database. Nếu classifier đã tăng counter, sau rollback counter có thể vẫn tiến lên. Điều này khiến route của lần retry khác route ban đầu.

Muốn state phản ánh dữ liệu đã commit, cần dùng một cơ chế transaction-aware phù hợp, hoặc lưu trạng thái theo business key trong cùng transaction với kết quả. Không thể chỉ dùng AtomicLong hay synchronized để tạo tính nhất quán với database transaction.

## 13. Thread safety của stateful classifier

Một classifier singleton có thể được nhiều Step hoặc JobExecution sử dụng đồng thời. Một classifier @StepScope có thể được nhiều thread trong cùng StepExecution gọi. Do đó, phải xác định ai truy cập từng field.

Các ví dụ rủi ro:

- HashMap mutable được nhiều thread cập nhật.
- Bộ đếm long tăng không nguyên tử.
- Field currentItem bị ghi đè giữa hai lời gọi.
- Cache bị làm mới trong khi thread khác đang đọc.
- Classifier đóng resource trong khi thread khác đang classify.

Nếu state chỉ là cache, dùng cấu trúc concurrent hoặc snapshot immutable. Nếu state là dữ liệu theo StepExecution, ưu tiên instance riêng theo Step và tránh chia sẻ với worker khác. Nếu state là business state, dùng database hoặc hệ thống có cơ chế concurrency control.

AtomicInteger và AtomicLong chỉ bảo vệ phép cập nhật đơn lẻ. Chúng không làm cho nhiều field được cập nhật như một transaction, không giải quyết rollback và không bảo đảm route ổn định theo item.

## 14. Cache invalidation và snapshot policy

Cache trong classifier có thể trở thành nguồn lỗi nếu dữ liệu định tuyến thay đổi giữa lúc Job đang chạy.

Ví dụ, tenant A ban đầu được route sang Processor X. Trong khi Job chạy, policy được cập nhật để route sang Processor Y. Nếu cache không có quy tắc version, một số item có thể đi X và item khác đi Y tùy thời điểm cache refresh.

Các chiến lược:

- **Snapshot theo execution:** nạp toàn bộ mapping tại thời điểm Step bắt đầu và dùng bất biến đến hết Step.
- **Versioned policy:** JobParameters lưu policyVersion; mọi lookup dùng đúng version đó.
- **TTL cache:** chấp nhận policy có thể đổi sau một khoảng thời gian; chỉ dùng khi nghiệp vụ cho phép.
- **Explicit invalidation:** cập nhật cache khi có event thay đổi policy, đồng thời xác định cách xử lý item đang chạy.
- **Per-partition cache:** mỗi worker có snapshot riêng nếu partition cần policy độc lập.

Với batch có yêu cầu tái lập kết quả, snapshot/versioned policy thường dễ kiểm soát hơn TTL cache. Khi restart, cần nạp lại đúng policy version đã dùng ban đầu, không mặc định lấy policy mới nhất.

## 15. State trong partitioning

Partitioning thường là cách phù hợp để cô lập state theo worker. Manager Step tạo các ExecutionContext riêng cho từng partition; mỗi worker có StepExecution và có thể có classifier riêng theo @StepScope.

Ví dụ partitioner cung cấp route mode:

~~~java
ExecutionContext context = new ExecutionContext();
context.putString("routeMode", "REGION_A");
partitions.put("regionA", context);
~~~

Classifier của worker nhận mode:

~~~java
@Bean
@StepScope
RegionClassifier regionClassifier(
        @Value("#{stepExecutionContext['routeMode']}") String routeMode,
        RegionAProcessor regionAProcessor,
        RegionBProcessor regionBProcessor) {

    return new RegionClassifier(routeMode, regionAProcessor, regionBProcessor);
}
~~~

Mỗi worker có context riêng, nên routeMode của partition A không ghi đè partition B. Đây là state cấu hình theo partition, không phải bộ đếm toàn cục dùng để phân phối item.

Nếu worker Step chạy nhiều thread, classifier của worker vẫn có thể được gọi đồng thời. Hãy giữ classifier stateless sau khi constructor hoàn tất hoặc bảo vệ state mutable cần thiết.

## 16. Phân biệt classifier state với processor state

Classifier chỉ quyết định delegate nào sẽ nhận item. Processor thực hiện nghiệp vụ. Đừng để classifier tích lũy logic mà đáng ra thuộc processor.

| Trách nhiệm | Thành phần phù hợp |
|---|---|
| Chọn delegate theo type | Classifier |
| Validate amount | ItemProcessor |
| Tính phí | ItemProcessor hoặc domain service |
| Gọi policy để xác định route | Classifier hoặc routing service |
| Lưu checkpoint | ItemStream/ExecutionContext |
| Lưu trạng thái nghiệp vụ lâu dài | Repository/domain service |
| Ghi output | ItemWriter |
| Đếm số item đã commit | StepExecution metadata hoặc database |

Nếu classifier phải sửa item, ghi database hoặc gọi API có side effect chỉ để chọn nhánh, có thể cần tách một bước enrichment hoặc routing service. Classifier nên trả về lựa chọn xử lý; delegate chịu trách nhiệm thực hiện quy tắc của nhánh.

## 17. Xử lý lỗi trong classifier

Classifier có thể gặp:

- Item thiếu route key.
- Route key không được hỗ trợ.
- Cache lookup thất bại.
- Policy service timeout.
- Mapping cấu hình thiếu delegate.
- Lỗi khi đọc state hoặc khôi phục state.

Hãy phân biệt lỗi dữ liệu với lỗi hạ tầng:

| Lỗi | Cách xử lý có thể phù hợp |
|---|---|
| Type không được hỗ trợ | Fail fast hoặc fallback có audit |
| Field route bắt buộc bị thiếu | Validation failure; skip chỉ khi nghiệp vụ cho phép |
| Policy service timeout tạm thời | Retry có giới hạn nếu lookup an toàn |
| Không có delegate trong cấu hình | Lỗi cấu hình, thường nên fail Step |
| Cache chứa policy version không hợp lệ | Dừng và báo lỗi, tránh chọn nhánh tùy tiện |
| State checkpoint không đọc được | Không tiếp tục với route không xác định |

Không trả null từ classifier nếu composite cần một delegate. Null delegate có thể gây lỗi khi composite gọi processor. Nếu muốn filter item, delegate được chọn có thể trả null theo hợp đồng ItemProcessor; đó là quyết định khác với việc classifier không tìm được route.

## 18. Skip và retry khi classifier có state

Classifier được gọi trong giai đoạn process khi được dùng bên trong ClassifierCompositeItemProcessor. Exception từ classifier hoặc delegate có thể chịu ảnh hưởng của skip/retry policy của Step.

Retry có thể khiến classifier được gọi lại cho cùng item. Vì vậy:

- classify nên xác định và không phụ thuộc vào bộ đếm lời gọi nếu route có ý nghĩa nghiệp vụ.
- Lookup cache nên an toàn khi thực hiện lại.
- Không ghi side effect không idempotent trong classify.
- Nếu route cần được cố định, lưu route theo business key hoặc tính từ dữ liệu bất biến.
- Exception phân loại lỗi tạm thời và lỗi vĩnh viễn nên khác nhau.

Ví dụ cấu hình:

~~~java
return new StepBuilder("paymentStep", jobRepository)
        .<Payment, PaymentResult>chunk(100, transactionManager)
        .reader(reader)
        .processor(classifierComposite)
        .writer(writer)
        .faultTolerant()
        .retry(TemporaryPolicyLookupException.class)
        .retryLimit(3)
        .skip(UnsupportedPaymentTypeException.class)
        .skipLimit(20)
        .build();
~~~

Chỉ skip loại payment không hỗ trợ nếu hợp đồng nghiệp vụ cho phép loại record đó. Nếu classifier không tìm thấy delegate do cấu hình deploy sai, không nên biến lỗi cấu hình thành skip của từng item.

## 19. Kiểm thử classifier có state

Unit test cần kiểm tra cả kết quả định tuyến lẫn cách state thay đổi:

- Route được chọn đúng với item hợp lệ.
- State khởi tạo đúng.
- Cache hit không gọi lại dịch vụ không cần thiết.
- Cache miss nạp và lưu kết quả đúng.
- Unknown route có hành vi rõ ràng.
- Concurrent classify không làm hỏng cấu trúc cache hoặc counter.
- State không bị chia sẻ giữa hai StepExecution nếu yêu cầu isolation.

Ví dụ kiểm tra cache:

~~~java
@Test
void loadsTenantPolicyOnlyOnce() {
    PolicyService policyService = mock(PolicyService.class);
    when(policyService.findPaymentType("TENANT-1"))
            .thenReturn(PaymentType.CARD);

    TenantClassifier classifier =
            new TenantClassifier(policyService, configuredRoutes());

    classifier.classify(paymentFor("TENANT-1", "P-1"));
    classifier.classify(paymentFor("TENANT-1", "P-2"));

    verify(policyService, times(1)).findPaymentType("TENANT-1");
}
~~~

Test này xác nhận cache hoạt động trong một instance classifier. Cần thêm test cho policy version thay đổi, lỗi lookup và nhiều thread cùng truy cập một tenant.

## 20. Kiểm thử concurrency

Test tuần tự không đủ để phát hiện race condition. Dùng ExecutorService cùng CountDownLatch hoặc CyclicBarrier để nhiều thread bắt đầu classify gần như đồng thời.

Với cache, kiểm tra:

- Không mất entry.
- Không trả về delegate sai.
- Số lần gọi policy service phù hợp với semantics cache đã chọn.
- Không có exception do collection bị thay đổi đồng thời.

Với counter, kiểm tra tổng số invocation sau khi mọi Future hoàn tất. Tuy nhiên, kết quả counter chỉ chứng minh tính chính xác của phép đếm, không chứng minh route theo item ổn định.

Với routing nghiệp vụ, kiểm tra cùng một item được classify nhiều lần luôn trả cùng delegate, kể cả khi các item khác được classify đồng thời.

## 21. Kiểm thử restart và checkpoint

Nếu classifier triển khai ItemStream hoặc dùng ExecutionContext, cần test qua hai lần JobExecution với JobRepository bền vững:

1. Launch Job với identifying parameters cố định.
2. Cho một số chunk commit rồi tạo lỗi có kiểm soát.
3. Đọc lại checkpoint đã lưu.
4. Restart cùng JobInstance và cùng input.
5. Xác nhận state classifier được mở lại đúng.
6. Xác nhận cùng business item vẫn được route nhất quán.
7. Đối chiếu dữ liệu đầu ra để phát hiện thiếu hoặc trùng.

Test cần bao gồm trường hợp chunk rollback sau khi classifier đã được gọi. Nếu state trong memory tiến lên nhưng transaction rollback, hãy xác nhận lần retry có thể định tuyến khác hay không. Với route nghiệp vụ, kết quả khác nhau thường là dấu hiệu thiết kế cần thay đổi.

Không chỉ assert Job COMPLETED. Hãy so sánh tập business key và kết quả theo từng loại route với kết quả mong đợi.

## 22. Logging và metrics

Khi classifier có cache hoặc state, log nên giúp trả lời:

- Item được route theo key nào?
- Delegate nào được chọn?
- Policy version nào được dùng?
- Kết quả đến từ cache hay lookup?
- Classifier có gặp unknown route không?
- Item được retry bao nhiêu lần?

Tránh log raw payload hoặc dữ liệu nhạy cảm nếu không cần. Có thể ghi business key, route key, policy version, JobExecution ID và StepExecution ID.

Metrics nên phân biệt:

- Số lần classify được gọi.
- Số lần cache hit/miss.
- Số lần lookup policy thất bại.
- Số item được processor xử lý.
- Số item được writer commit.

Các số này không đồng nghĩa. Một invocation có thể được retry; một output có thể bị rollback. Dùng StepExecution counters hoặc dữ liệu đã commit để báo cáo kết quả nghiệp vụ.

## 23. Khi nào nên tránh state trong classifier?

Hãy ưu tiên classifier stateless khi:

- Route có thể suy ra trực tiếp từ item.
- Retry/restart cần cho cùng item cùng kết quả.
- Step chạy song song hoặc có partition.
- State chỉ phục vụ đếm và có thể dùng metrics riêng.
- Có thể đưa policy vào immutable configuration.
- Có thể dùng routing key ổn định thay cho bộ đếm.

Nếu cần state, hãy giữ nó ở mức tối thiểu và làm rõ:

1. State thuộc application, JobExecution, StepExecution hay partition?
2. Ai là chủ sở hữu và cập nhật state?
3. Có nhiều thread đọc/ghi không?
4. State có phải khôi phục khi restart không?
5. Chunk rollback có cần hoàn tác state không?
6. Retry cùng item có phải chọn cùng route không?
7. Policy thay đổi giữa execution được xử lý thế nào?

Nếu không trả lời được các câu hỏi này, state có thể đang được đặt sai tầng.

## 24. Các lỗi thường gặp

**Dùng bộ đếm lời gọi để quyết định route nghiệp vụ:** retry và concurrency có thể khiến cùng item đi qua delegate khác. Dùng khóa ổn định hoặc lưu quyết định theo business key.

**Cho rằng AtomicInteger giải quyết mọi vấn đề:** atomic chỉ bảo vệ cập nhật counter, không xử lý rollback, restart hoặc tính nhất quán giữa các field.

**Giữ state execution trong singleton:** nhiều JobExecution có thể ghi đè dữ liệu của nhau. Dùng JobParameters, ExecutionContext hoặc scope đúng phạm vi.

**Cho rằng @StepScope tự thread-safe:** nhiều thread trong cùng StepExecution vẫn có thể gọi cùng target bean.

**Không persist state cần restart:** field trong memory mất khi process dừng. Dùng ItemStream/ExecutionContext hoặc kho dữ liệu bền vững.

**Chỉ implement ItemStream mà quên đăng ký:** Step không gọi lifecycle nếu stream không được đăng ký hoặc không được nhận diện qua component.

**Coi update() như commit của từng classify:** update là callback lưu trạng thái stream theo lifecycle Step, không tự làm mỗi quyết định route thành transaction riêng.

**Cache policy không có version:** một Job có thể dùng nhiều policy khác nhau nếu cache bị refresh giữa chừng. Pin version hoặc snapshot theo execution.

**Dùng cache mutable không thread-safe:** nhiều thread có thể làm hỏng state hoặc đọc giá trị không nhất quán. Dùng immutable snapshot hoặc concurrent structure.

**Dùng metrics counter làm số item đã commit:** retry và rollback khiến số lần classify khác số item được ghi thành công.

**Trả null khi không tìm thấy delegate:** composite có thể lỗi khi gọi processor. Fail fast hoặc trả về fallback có chủ đích.

**Bỏ qua kiểm thử restart:** một classifier chạy đúng trong lần đầu có thể route khác sau khi khởi động lại do state được reset hoặc policy đã đổi.

## Kết luận

Classifier có state có thể giữ cấu hình, cache, metrics hoặc state theo execution để hỗ trợ định tuyến. Cần phân biệt state bất biến với state mutable, state kỹ thuật với business state, và state theo application với state theo Job/Step/partition. Classifier dựa vào thứ tự lời gọi hoặc bộ đếm để đổi delegate dễ gặp lỗi khi retry, rollback, concurrency và restart; AtomicInteger chỉ giải quyết cập nhật đồng thời chứ không bảo đảm cùng item luôn đi cùng route. Ưu tiên định tuyến xác định từ item hoặc routing key ổn định. Nếu cần cache, dùng cấu trúc thread-safe và pin policy version; nếu cần khôi phục state, tích hợp ItemStream/ExecutionContext và đăng ký lifecycle với Step. Kiểm thử cả cache, concurrency, rollback và restart để bảo đảm state không làm thay đổi kết quả nghiệp vụ ngoài ý muốn.

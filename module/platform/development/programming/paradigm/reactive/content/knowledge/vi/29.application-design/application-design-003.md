# Thiết kế ứng dụng

## Thiết kế API trả về kiểu phản ứng thay vì tự đăng ký

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Một quyết định thiết kế quan trọng là để API trả về kiểu phản ứng, mô tả công việc cần thực hiện, rồi giao quyền đăng ký cho thành phần sở hữu vòng đời tiêu thụ dữ liệu.

Khi một phương thức service gọi `subscribe()` bên trong rồi trả về `void`, caller không còn nhìn thấy toàn bộ công việc. Nó không thể ghép bước tiếp theo, xử lý lỗi trong cùng pipeline, đặt timeout, điều khiển demand hoặc hủy công việc khi không còn cần. Ngược lại, nếu service trả về `Mono<T>` hoặc `Flux<T>`, caller có thể kết hợp nhiều thao tác thành một chuỗi và chọn điểm bắt đầu thực thi phù hợp.

Thiết kế này tạo ra một quy tắc ownership rõ ràng: **thành phần tạo Publisher mô tả công việc; thành phần tiêu thụ chịu trách nhiệm subscribe và quản lý vòng đời**. Trong ứng dụng Spring WebFlux, framework thường là thành phần tiêu thụ ở ranh giới HTTP. Trong một job nền hoặc tiến trình độc lập, một scheduler hoặc worker có thể sở hữu subscription. Service ở giữa giữ vai trò ghép logic nghiệp vụ và trả Publisher về caller.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Chọn `Mono<T>`, `Flux<T>` hoặc `Mono<Void>` làm kiểu trả về theo hợp đồng kết quả.
- Thiết kế repository, service và controller trả về Publisher thay vì tự gọi `subscribe()`.
- Ghép các bước bất đồng bộ bằng `map`, `flatMap`, `zip` và `then`.
- Đưa lỗi, timeout, retry và cancellation vào cùng pipeline.
- Hiểu vì sao nested subscription làm mất quyền điều phối của caller.
- Dùng `defer`, `fromCallable` và scheduler để trì hoãn hoặc cô lập công việc blocking.
- Xác định những ranh giới hợp lệ để subscribe trong ứng dụng.
- Bảo toàn transaction context, Reactor Context và vòng đời tài nguyên qua một chuỗi.
- Kiểm thử API reactive bằng `StepVerifier`.

## 1. Publisher là hợp đồng mô tả công việc

Reactive Streams định nghĩa `Publisher<T>` là nguồn phát các phần tử kiểu `T` tới Subscriber. Trong Project Reactor, hai kiểu thường dùng là:

- `Mono<T>`: phát tối đa một phần tử, hoặc hoàn tất rỗng, hoặc phát lỗi.
- `Flux<T>`: phát từ không đến nhiều phần tử, rồi hoàn tất hoặc phát lỗi.

Khi một phương thức trả về Publisher, nó cho caller biết loại dữ liệu và cách tiếp tục xử lý. Publisher cũng mang theo vòng đời reactive: subscription, demand, tín hiệu dữ liệu, lỗi, hoàn tất và cancellation.

Ví dụ một repository:

~~~java
interface CustomerRepository {
    Mono<Customer> findById(String customerId);

    Flux<Customer> findActiveCustomers();

    Mono<Customer> save(Customer customer);
}
~~~

Các phương thức không tự subscribe. Caller có thể ghép chúng với bước nghiệp vụ:

~~~java
Mono<CustomerView> view =
    customerRepository.findById(customerId)
        .map(customer ->
            new CustomerView(customer.id(), customer.name())
        );
~~~

Biểu thức trên tạo một Publisher mới. Với nguồn cold thông thường, truy vấn bắt đầu khi có subscription. Caller có thể thêm timeout, logging, recovery hoặc ghép thêm dữ liệu trước khi framework tiêu thụ.

### Chọn kiểu trả về theo ý nghĩa nghiệp vụ

| Kiểu trả về | Hợp đồng | Ví dụ |
|---|---|---|
| `Mono<Customer>` | Không quá một Customer | Tìm theo ID |
| `Mono<Receipt>` | Một kết quả nghiệp vụ | Xác nhận thanh toán |
| `Mono<Void>` | Chỉ cần biết hoàn tất hay lỗi | Xóa cache, lưu audit |
| `Flux<Order>` | Một chuỗi Order | Tìm nhiều đơn |
| `Flux<ServerSentEvent<T>>` | Dòng sự kiện liên tục | SSE stream |
| `Publisher<T>` | Hợp đồng Reactive Streams tổng quát | API thư viện trung lập Reactor |

Ưu tiên `Mono` và `Flux` trong mã ứng dụng dùng Reactor vì chúng cung cấp các toán tử và ngữ nghĩa cụ thể. Dùng `Publisher<T>` khi muốn công khai hợp đồng Reactive Streams tổng quát hoặc tích hợp với thư viện khác.

Không dùng `void` cho một phương thức service thực hiện công việc bất đồng bộ nếu caller cần biết khi nào công việc kết thúc hoặc thất bại. Hãy trả `Mono<Void>`.

## 2. Vì sao service không nên tự subscribe?

Xét một service tự subscribe:

~~~java
// Không nên: service tự khởi động công việc và không trả lại Publisher.
void sendReceipt(String orderId) {
    orderRepository.findById(orderId)
        .flatMap(order -> mailClient.sendReceipt(order))
        .subscribe();
}
~~~

Cách viết này có vẻ ngắn, nhưng tạo ra nhiều vấn đề:

1. Caller không thể biết lúc nào gửi receipt hoàn tất.
2. Lỗi không được chuyển về pipeline của caller; overload subscribe không có error consumer có thể khiến lỗi trở thành lỗi không được xử lý.
3. Caller không thể đặt timeout hoặc retry quanh toàn bộ workflow.
4. Caller không thể hủy tác vụ thông qua subscription mà nó sở hữu.
5. Service có thể chạy tiếp sau khi request HTTP đã bị hủy.
6. Test khó kiểm tra hành vi bằng `StepVerifier`, vì phương thức không trả Publisher.
7. Transaction hoặc Reactor Context của caller không tự truyền sang subscription mới.

Thiết kế trả Publisher:

~~~java
Mono<Void> sendReceipt(String orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(mailClient::sendReceipt)
        .then();
}
~~~

Caller nhận lại một `Mono<Void>` đại diện cho toàn bộ công việc. Nó có thể ghép thêm bước, xử lý lỗi và quyết định thời điểm subscribe.

~~~java
Mono<Void> workflow =
    orderService.sendReceipt(orderId)
        .timeout(Duration.ofSeconds(3))
        .doOnError(error ->
            log.warn("Could not send receipt for order {}", orderId, error)
        );
~~~

Không có subscription mới bị tạo ở giữa. Một subscription cuối cùng điều phối toàn bộ chuỗi.

### Nested subscription phá vỡ composition

Khi một phương thức gọi `subscribe()` bên trong, nó tạo một subscription độc lập. Pipeline bên ngoài không tự chờ subscription đó và không sở hữu lỗi hoặc cancellation của nó.

~~~java
// Không nên: Publisher con bị tách khỏi pipeline bên ngoài.
Mono<OrderView> loadView(String id) {
    return orderRepository.findById(id)
        .doOnNext(order ->
            auditService.recordViewed(order).subscribe()
        )
        .map(this::toView);
}
~~~

Nếu ghi audit là một phần của workflow, hãy ghép Publisher con bằng `flatMap` hoặc `then`:

~~~java
Mono<OrderView> loadView(String id) {
    return orderRepository.findById(id)
        .flatMap(order ->
            auditService.recordViewed(order)
                .thenReturn(toView(order))
        );
}
~~~

Bây giờ kết quả chỉ phát sau khi audit hoàn tất. Nếu audit lỗi, lỗi truyền theo cùng pipeline; nếu caller hủy, cancellation có thể truyền tới thao tác audit.

Nếu audit phải được thực hiện độc lập kể cả khi caller rời đi, hãy ghi một job hoặc outbox event bền vững và để worker sở hữu công việc đó. Một lời gọi `subscribe()` không thay thế được hàng đợi công việc có vòng đời và khả năng phục hồi.

## 3. Để controller WebFlux trả Publisher cho framework

Trong Spring WebFlux, controller có thể trả trực tiếp `Mono` hoặc `Flux`. Framework đăng ký Publisher và chuyển các tín hiệu thành HTTP response.

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    Mono<OrderView> find(@PathVariable String id) {
        return orderService.findView(id);
    }

    @GetMapping(produces = MediaType.APPLICATION_NDJSON_VALUE)
    Flux<OrderView> findAll() {
        return orderService.findAllViews();
    }
}
~~~

Controller không cần gọi `subscribe()`. Nó trả về hợp đồng phản ứng để WebFlux quản lý subscription, demand, ghi response và cancellation.

Nếu client ngắt kết nối hoặc hủy request, framework có thể hủy subscription của response. Cancellation truyền qua pipeline và tới các Publisher con theo khả năng của adapter. Một truy vấn reactive có thể được hủy hoặc ngừng tiêu thụ; một thư viện blocking có thể không dừng thao tác bên dưới ngay lập tức.

### Không block để lấy kết quả trong controller

~~~java
// Không nên trong WebFlux.
@GetMapping("/{id}")
OrderView find(@PathVariable String id) {
    return orderService.findView(id).block();
}
~~~

`block()` chặn thread hiện tại để chờ kết quả. Trong WebFlux, thread đó có thể là event loop đang phục vụ nhiều kết nối. Chặn event loop làm giảm khả năng đáp ứng của nhiều request khác.

Trả Publisher để framework tiếp tục xử lý bất đồng bộ:

~~~java
@GetMapping("/{id}")
Mono<OrderView> find(@PathVariable String id) {
    return orderService.findView(id);
}
~~~

## 4. Ghép các bước phụ thuộc bằng flatMap

Nếu bước sau cần giá trị từ bước trước và trả về Publisher, dùng `flatMap`.

~~~java
Mono<OrderDetail> findDetail(String orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            customerRepository.findById(order.customerId())
                .map(customer ->
                    new OrderDetail(order, customer)
                )
        );
}
~~~

`findById` trả `Mono<Order>`. Sau khi nhận order, `flatMap` gọi Publisher tìm customer và ghép kết quả. Nếu dùng `map` thay vì `flatMap`, kết quả sẽ là `Mono<Mono<OrderDetail>>`, tức Publisher lồng nhau.

Với nhiều bản ghi, `flatMap` có thể chạy các Publisher con đồng thời:

~~~java
Flux<OrderView> views =
    orderRepository.findRecent()
        .flatMap(
            order -> customerRepository.findById(order.customerId())
                .map(customer -> new OrderView(order, customer)),
            12
        );
~~~

Tham số 12 giới hạn số Publisher con đang hoạt động đồng thời. Kết quả có thể phát theo thứ tự inner hoàn tất, không nhất thiết theo thứ tự nguồn. Nếu cần bảo toàn thứ tự, cân nhắc `flatMapSequential`; nếu cần xử lý lần lượt, dùng `concatMap`.

Không tăng concurrency tùy tiện. Caller có thể điều khiển concurrency theo giới hạn connection pool, quota của dịch vụ phụ thuộc và năng lực xử lý.

## 5. Ghép các nguồn độc lập bằng zip

Nếu hai nguồn độc lập và cần cả hai kết quả, dùng `Mono.zip`:

~~~java
Mono<OrderDashboard> dashboard =
    Mono.zip(
        orderRepository.findById(orderId),
        paymentRepository.findLatestForOrder(orderId),
        inventoryRepository.findReservation(orderId)
    )
    .map(tuple ->
        new OrderDashboard(
            tuple.getT1(),
            tuple.getT2(),
            tuple.getT3()
        )
    );
~~~

Các nguồn có thể được subscribe và tiến hành độc lập. `zip` phát tuple khi mỗi nguồn cung cấp một giá trị. Nếu một nguồn hoàn tất rỗng, kết quả zip có thể hoàn tất rỗng; nếu một nguồn lỗi, lỗi được truyền tới downstream và các nguồn còn lại do toán tử quản lý có thể bị hủy.

Nếu một dữ liệu là tùy chọn, biểu diễn giá trị mặc định trước khi zip:

~~~java
Mono<Promotion> promotion =
    promotionRepository.findForOrder(orderId)
        .defaultIfEmpty(Promotion.none());
~~~

Dùng `zip` khi cần đồng thời các giá trị. Nếu chỉ cần chờ một thao tác hoàn tất mà không cần giá trị của nó, dùng `then`.

## 6. Biểu diễn thao tác không có giá trị bằng Mono<Void>

Nhiều thao tác service không có kết quả dữ liệu để trả về: xóa bản ghi, gửi thông báo, ghi audit hoặc xác nhận một command. `Mono<Void>` thể hiện rằng caller chỉ cần biết thao tác hoàn tất hay thất bại.

~~~java
interface NotificationService {
    Mono<Void> sendOrderCreated(String orderId);
}

interface OrderRepository {
    Mono<Void> deleteById(String orderId);
}
~~~

Ghép hai thao tác tuần tự:

~~~java
Mono<Void> cancelOrder(String orderId) {
    return orderRepository.markCancelled(orderId)
        .then(notificationService.sendOrderCreated(orderId));
}
~~~

`then` chờ Publisher trước hoàn tất, bỏ giá trị của nó rồi mới subscribe Publisher tiếp theo. Nếu bước đầu lỗi, bước sau không được chạy.

Nếu cần trả kết quả cố định sau khi thao tác hoàn tất, dùng `thenReturn`:

~~~java
Mono<CommandResult> deleteOrder(String orderId) {
    return orderRepository.deleteById(orderId)
        .thenReturn(new CommandResult(orderId, "DELETED"));
}
~~~

Không nên đổi `Mono<Void>` thành `Mono<Boolean>` chỉ để có một phần tử giả nếu caller không cần giá trị đó. Kiểu trả về nên thể hiện chính xác hợp đồng.

## 7. Để lỗi nằm trong cùng pipeline

Một API trả Publisher cho phép caller quyết định chính sách lỗi ở đúng tầng có đủ ngữ cảnh.

Service có thể chuyển lỗi hạ tầng thành lỗi miền:

~~~java
Mono<Order> findRequired(String orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(
            new OrderNotFoundException(orderId)
        ))
        .onErrorMap(
            DataAccessException.class,
            OrderStoreUnavailableException::new
        );
}
~~~

Caller có thể thêm fallback nếu nghiệp vụ cho phép:

~~~java
Mono<OrderView> view =
    orderService.findRequired(orderId)
        .flatMap(order -> viewAssembler.assemble(order))
        .onErrorResume(
            OrderStoreUnavailableException.class,
            error -> cachedViews.find(orderId)
        );
~~~

Nếu service tự subscribe, caller không thể ghép recovery vào cùng workflow. Trả Publisher giữ nguyên kênh lỗi để các tầng có thể xử lý theo chính sách của mình.

Không nên bắt mọi lỗi rồi trả `Mono.empty()` ở service chỉ để tránh báo lỗi. Điều đó có thể làm caller nhầm lẫn giữa "không có dữ liệu" và "không thể truy cập dữ liệu". Dùng kiểu kết quả hoặc exception miền rõ ràng.

## 8. Tạo Publisher một cách lười khi cần thiết

Trả kiểu reactive không có nghĩa mọi biểu thức bên trong đều tự động lazy. Ví dụ:

~~~java
Mono<Customer> wrong =
    Mono.just(legacyDao.loadCustomer(customerId));
~~~

Java đánh giá `legacyDao.loadCustomer(customerId)` trước khi gọi `Mono.just`. Nếu DAO blocking, lời gọi đã chặn thread tại thời điểm lắp ráp pipeline.

Dùng `fromCallable` để trì hoãn lời gọi:

~~~java
Mono<Customer> customer =
    Mono.fromCallable(() -> legacyDao.loadCustomer(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

`fromCallable` gọi callable khi có subscription; `subscribeOn` chuyển công việc nguồn sang scheduler phù hợp cho blocking I/O. Nếu dùng một API reactive non-blocking, không cần chuyển nó sang bounded elastic chỉ vì nó giao tiếp với mạng hoặc database.

Dùng `defer` khi cần tạo Publisher mới theo từng subscription:

~~~java
Mono<Config> config =
    Mono.defer(() -> configService.loadCurrent());
~~~

Điều này hữu ích khi việc tạo Publisher phụ thuộc trạng thái tại thời điểm subscribe hoặc mỗi Subscriber cần một nguồn riêng.

## 9. Validation và lỗi đồng bộ

Một phương thức Java có thể kiểm tra đối số ngay lúc được gọi. Nhưng nếu muốn mọi lỗi của thao tác được biểu diễn trong Publisher, hãy trì hoãn validation và trả `Mono.error`:

~~~java
Mono<Order> submit(OrderCommand command) {
    return Mono.defer(() -> {
        if (command.quantity() <= 0) {
            return Mono.error(
                new InvalidOrderCommandException("quantity must be positive")
            );
        }

        return orderRepository.create(command);
    });
}
~~~

Validation xảy ra khi subscribe, và exception được biểu diễn thành tín hiệu lỗi của Publisher. Điều này giúp caller kiểm thử và ghép lỗi cùng các bước khác.

Có trường hợp validation ở assembly là hợp lý, ví dụ đối số null vi phạm hợp đồng lập trình và cần fail-fast ngay khi gọi method. Hãy chọn một chính sách nhất quán và ghi rõ trong API. Điểm quan trọng là không bắt exception rồi gọi `subscribe()` bên trong để "xử lý" nó.

## 10. Cancellation và vòng đời của request

Khi service trả Publisher, caller cuối cùng có thể hủy subscription. Trong WebFlux, framework gắn subscription với vòng đời HTTP response. Nếu client disconnect, cancellation có thể truyền từ response writer tới các Publisher con.

~~~java
Mono<OrderView> response =
    orderRepository.findById(orderId)
        .flatMap(order ->
            inventoryClient.find(order.id())
                .map(stock -> new OrderView(order, stock))
        )
        .doOnCancel(() ->
            log.debug("Order view subscription cancelled")
        );
~~~

Nếu controller trả `response` cho WebFlux, framework sở hữu subscription. Nếu client hủy, `doOnCancel` có thể quan sát sự kiện và Reactor yêu cầu upstream dừng.

Cancellation là yêu cầu ngừng công việc, không phải rollback. Một HTTP request đã gửi tới dịch vụ khác có thể đã được xử lý. Một câu lệnh database đã commit không tự được hoàn tác chỉ vì caller hủy. Với thao tác có tác dụng phụ, cần idempotency key, trạng thái workflow và đối soát.

### Tác vụ cần tiếp tục sau khi client rời đi

Nếu nghiệp vụ yêu cầu công việc tiếp tục dù HTTP client disconnect, không gắn tác vụ đó vào subscription response. Hãy lưu job hoặc outbox event trong transaction rồi giao cho worker nền:

~~~java
Mono<JobAccepted> requestExport(ExportCommand command) {
    return exportJobRepository.create(command)
        .flatMap(job ->
            outboxRepository.append(ExportRequested.from(job))
                .thenReturn(new JobAccepted(job.id()))
        );
}
~~~

Worker nền subscribe hoặc consume message ở ranh giới sở hữu của nó. Client chỉ nhận job ID và có thể truy vấn trạng thái sau đó. Công việc được quản lý bằng persistence, retry và lifecycle riêng.

## 11. Transaction và Reactor Context

Trong reactive transaction, transaction context thường gắn với subscription và được truyền qua Reactor Context. Nếu một service tự gọi `subscribe()`, nó tạo subscription mới, tách khỏi context của caller. Hệ quả có thể là câu lệnh repository không còn tham gia transaction mà caller đã mở.

Ví dụ giữ các thao tác trong cùng pipeline:

~~~java
Mono<Void> updateOrder(Order order) {
    return transactionalOperator.transactional(
        orderRepository.save(order)
            .then(auditRepository.recordOrderUpdated(order.id()))
    );
}
~~~

Cả hai thao tác được ghép trong Publisher mà `TransactionalOperator` quản lý. Điều này chỉ bảo đảm transaction nếu repository tham gia cùng transaction manager và cùng transactional resource theo cấu hình.

Reactor Context cũng có thể mang correlation ID, security context hoặc metadata theo subscription. Nested subscription không tự kế thừa context của chuỗi bên ngoài. Trả Publisher và ghép bằng toán tử giúp context đi theo cùng một đường thực thi.

Không dùng ThreadLocal như cơ chế duy nhất để truyền dữ liệu xuyên scheduler trong ứng dụng reactive. Hãy dùng Reactor Context hoặc tích hợp context propagation được framework hỗ trợ.

## 12. Khi nào được subscribe trực tiếp?

Quy tắc "service không tự subscribe" không có nghĩa ứng dụng không bao giờ gọi `subscribe()`. Mỗi Publisher cần một Subscriber để thực thi. Vấn đề là chọn đúng nơi sở hữu vòng đời.

Các ranh giới hợp lệ thường gồm:

- Framework web như Spring WebFlux tiêu thụ Publisher trả từ controller.
- Adapter message listener tiêu thụ Publisher cho mỗi message và quản lý ack/nack.
- Worker nền quản lý job có persistence và retry.
- Scheduler của ứng dụng kích hoạt tác vụ định kỳ.
- Entry point của một ứng dụng command-line hoặc batch job.

Ví dụ một tác vụ nền do thành phần worker sở hữu:

~~~java
@Component
class DailyReportWorker {
    private final ReportService reportService;

    DailyReportWorker(ReportService reportService) {
        this.reportService = reportService;
    }

    Disposable startJob(String reportDate) {
        return reportService.generate(reportDate)
            .doOnError(error ->
                log.error("Daily report generation failed", error)
            )
            .subscribe();
    }
}
~~~

Ví dụ này chỉ phù hợp khi worker thực sự sở hữu lifecycle của job và có chính sách giữ handle, quan sát lỗi, hủy khi shutdown và bảo đảm công việc có thể phục hồi. Trong ứng dụng sản xuất, tác vụ quan trọng thường nên được ghi nhận bền vững trước khi worker xử lý; không dựa vào một subscription trong bộ nhớ như hàng đợi đáng tin cậy.

Nếu dùng overload `subscribe()` không có error consumer, hãy bảo đảm lỗi được xử lý ở nơi khác một cách rõ ràng. Tốt hơn là dùng overload có callback lỗi hoặc một cơ chế quản lý worker tập trung. Không gọi `subscribe()` từ service chỉ vì "muốn nó chạy".

### Quản lý Disposable

Các overload subscribe trả về `Disposable`. Thành phần sở hữu có thể giữ handle để hủy công việc:

~~~java
Disposable task = reportService.generate(reportDate)
    .subscribe(
        report -> log.info("Generated report {}", report.id()),
        error -> log.error("Report failed", error)
    );

// Khi lifecycle của worker kết thúc:
task.dispose();
~~~

Chỉ dispose khi chính sách nghiệp vụ cho phép hủy. Nếu job cần tiếp tục sau restart hoặc phải hoàn tất sau khi request kết thúc, hãy dùng job queue bền vững thay vì giữ một Disposable trong memory.

## 13. Không biến tác dụng phụ thành công việc ẩn

Các toán tử `doOnNext`, `doOnSuccess`, `doOnError` và `doFinally` phù hợp để quan sát: logging, metrics hoặc ghi nhận lifecycle. Chúng không phải nơi để tách một Publisher con mà không ghép nó vào chuỗi.

Không nên:

~~~java
Mono<Order> order =
    orderRepository.findById(orderId)
        .doOnNext(value ->
            notificationService.send(value).subscribe()
        );
~~~

Nếu notification là một phần của workflow, hãy dùng:

~~~java
Mono<Order> order =
    orderRepository.findById(orderId)
        .flatMap(value ->
            notificationService.send(value)
                .thenReturn(value)
        );
~~~

Nếu notification là sự kiện độc lập cần phát sau khi order commit, ghi outbox trong cùng transaction và để publisher worker phát message. Cách đó làm rõ thời điểm event được chấp nhận và cho phép retry sau lỗi.

## 14. API reactive giúp caller kiểm soát backpressure

Với `Flux`, Subscriber cuối có thể điều khiển demand. Nếu service tự subscribe và tiêu thụ nguồn ngay, caller không còn cơ hội quyết định tốc độ nhận dữ liệu.

Ví dụ API trả Flux:

~~~java
Flux<OrderEvent> streamOrderEvents(String orderId) {
    return eventRepository.findEvents(orderId)
        .filter(OrderEvent::isVisible);
}
~~~

Caller có thể giới hạn số phần tử:

~~~java
Flux<OrderEvent> firstEvents =
    orderService.streamOrderEvents(orderId)
        .take(100);
~~~

Hoặc xử lý từng phần tử với concurrency hữu hạn:

~~~java
Flux<ProcessedEvent> processed =
    orderService.streamOrderEvents(orderId)
        .flatMap(this::processEvent, 8);
~~~

Khi caller hủy, cancellation có thể truyền về service và nguồn. Khi caller giới hạn demand, các toán tử có thể điều chỉnh request upstream theo prefetch và buffer policy của chúng.

Nếu service tự subscribe, nó tự chọn cách tiêu thụ và có thể yêu cầu không giới hạn, khiến tầng gọi không thể áp dụng backpressure theo nhu cầu của mình.

## 15. Kiểm thử API trả Publisher

Vì service trả Publisher, test có thể kiểm tra tín hiệu mà không cần tự gọi `block()` hoặc tạo subscription ẩn.

~~~java
@Test
void findViewReturnsMappedCustomer() {
    Customer customer = new Customer("c-7", "Linh");

    when(customerRepository.findById("c-7"))
        .thenReturn(Mono.just(customer));

    StepVerifier.create(customerService.findView("c-7"))
        .expectNext(new CustomerView("c-7", "Linh"))
        .verifyComplete();

    verify(customerRepository).findById("c-7");
}
~~~

Kiểm thử lỗi:

~~~java
@Test
void missingCustomerIsReturnedAsReactiveError() {
    when(customerRepository.findById("missing"))
        .thenReturn(Mono.empty());

    StepVerifier.create(customerService.findRequired("missing"))
        .expectError(CustomerNotFoundException.class)
        .verify();
}
~~~

Kiểm thử tính lazy:

~~~java
@Test
void sourceIsInvokedOnlyAfterSubscription() {
    AtomicInteger calls = new AtomicInteger();

    Mono<Integer> result =
        Mono.fromCallable(calls::incrementAndGet);

    assertThat(calls.get()).isZero();

    StepVerifier.create(result)
        .expectNext(1)
        .verifyComplete();

    assertThat(calls.get()).isEqualTo(1);
}
~~~

Kiểm thử cancellation:

~~~java
@Test
void cancellationIsPropagatedToSource() {
    AtomicBoolean cancelled = new AtomicBoolean();

    StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .doOnCancel(() -> cancelled.set(true))
    )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectNext(0L, 1L)
        .thenCancel()
        .verify();

    assertThat(cancelled).isTrue();
}
~~~

Các test này xác minh API trả Publisher, phát dữ liệu/lỗi đúng hợp đồng và cho phép caller kiểm soát subscription. Với test transaction hoặc Reactor Context, cần kiểm tra bằng cấu hình transaction/context tương ứng; chỉ test giá trị đầu ra không đủ để chứng minh subscription không bị tách.

## 16. Những nhầm lẫn thường gặp

- **Trả Mono nghĩa là công việc tự chạy:** Publisher mô tả công việc; subscription kích hoạt nguồn theo semantics của nó.
- **Service phải subscribe để bảo đảm công việc chạy:** caller hoặc framework sở hữu subscription ở ranh giới tiêu thụ.
- **subscribe trong doOnNext vẫn thuộc pipeline ngoài:** nó tạo subscription độc lập, không tự chia sẻ lỗi, demand hoặc cancellation.
- **block là cách lấy kết quả để nối các tầng:** block chặn thread; hãy ghép Publisher bằng toán tử.
- **Mono.just(methodCall()) trì hoãn methodCall:** Java đánh giá đối số trước khi gọi just; dùng fromCallable hoặc defer.
- **Mono<Void> không có giá trị nên không hữu ích:** nó biểu diễn hoàn tất hoặc lỗi của thao tác bất đồng bộ.
- **doOnError thay thế onErrorResume:** doOnError chỉ quan sát; onErrorResume mới thay Publisher khi lỗi.
- **flatMap và map giống nhau:** flatMap ghép Publisher con; map biến đổi một giá trị đồng bộ.
- **Cancellation rollback mọi thao tác đã gửi:** cancellation yêu cầu dừng; tác dụng phụ đã commit cần idempotency và đối soát.
- **Một worker subscribe là đủ cho job bền vững:** subscription trong memory không thay thế job store, outbox hoặc message broker.
- **Transaction context tự truyền qua nested subscribe:** subscription mới tách khỏi context của caller; hãy giữ các thao tác trong cùng pipeline.
- **Mọi nguồn Flux đều cold:** hot/shared Publisher có thể phát độc lập với từng Subscriber; API cần mô tả semantics kết nối và replay nếu quan trọng.

## 17. Bài tập vận dụng

Một endpoint tạo đơn hàng cần thực hiện các bước: kiểm tra khách hàng, lưu đơn hàng, giữ tồn kho và phát sự kiện `OrderCreated`. Nếu client ngắt kết nối, hệ thống vẫn phải bảo đảm workflow đã được chấp nhận có thể hoàn tất hoặc phục hồi.

Hãy thiết kế API:

1. Repository và service nên trả về những kiểu reactive nào?
2. Controller WebFlux nên trả Publisher hay tự subscribe?
3. Bước kiểm tra khách hàng và đọc chính sách giá có thể kết hợp bằng toán tử nào nếu độc lập?
4. Lưu đơn hàng và outbox cần nằm trong transaction nào?
5. Giữ tồn kho là một bước đồng bộ trong transaction hay một workflow bất đồng bộ? Giải thích ranh giới.
6. Nếu client disconnect sau khi lệnh đã commit, tác vụ nào cần tiếp tục và ai sở hữu subscription?
7. Làm thế nào để retry message mà không tạo đơn hàng hoặc reservation trùng?
8. Viết test `StepVerifier` cho thành công, lỗi validation, repository rỗng và cancellation.

**Gợi ý:** service trả `Mono<OrderAccepted>` hoặc `Mono<Void>` theo hợp đồng; controller trả Publisher để WebFlux quản lý subscription. Ghi đơn hàng và outbox trong cùng transaction nếu dùng cùng database. Worker outbox sở hữu subscription/consumer cho workflow tiếp tục sau request, với event ID, idempotency và trạng thái bền vững. Dùng `zip` cho các dữ liệu độc lập, `flatMap` cho bước phụ thuộc và `then` khi chỉ cần chờ thao tác hoàn tất.

## Kết luận

API reactive nên trả `Mono` hoặc `Flux` để caller có thể ghép công việc, xử lý lỗi, đặt timeout, kiểm soát demand và hủy subscription. Service mô tả workflow bằng Publisher; controller WebFlux hoặc worker ở ranh giới tiêu thụ sở hữu subscription. Tránh tự subscribe hoặc block giữa các tầng vì chúng tách lỗi, cancellation, Reactor Context và transaction khỏi pipeline của caller. Với tác vụ cần tiếp tục sau khi HTTP request kết thúc, hãy ghi job hoặc outbox bền vững rồi giao cho worker có vòng đời riêng. Thiết kế ownership rõ ràng giúp các thành phần Java reactive dễ kết hợp, dễ kiểm thử và có hành vi vận hành dự đoán được.

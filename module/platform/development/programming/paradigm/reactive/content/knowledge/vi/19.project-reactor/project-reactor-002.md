# Project Reactor

## Tạo, ghép và trả về chuỗi Reactor trong mã Java

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học cách tổ chức ứng dụng quanh các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, điều khiển scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Project Reactor cung cấp các kiểu Publisher và toán tử để mô tả một quy trình xử lý ngay trong mã Java. Kỹ năng cốt lõi là tạo nguồn phù hợp, ghép các bước đồng bộ và bất đồng bộ thành một chuỗi, rồi trả chuỗi đó về nơi chịu trách nhiệm tiêu thụ dữ liệu.

Một chuỗi Reactor không phải là tập hợp các lệnh đã chạy ngay khi ta gọi phương thức. Phần lớn pipeline chỉ mô tả các bước cần thực hiện. Khi một Subscriber đăng ký, nguồn bắt đầu phát tín hiệu theo hợp đồng Reactive Streams. Vì vậy, thiết kế một phương thức service trả về `Mono<T>` hoặc `Flux<T>` giúp caller ghép thêm xử lý, quản lý lỗi và cancellation trong cùng một luồng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Chọn `Mono` hoặc `Flux` theo số lượng phần tử của kết quả.
- Tạo nguồn bằng các factory method phù hợp với dữ liệu có sẵn, phép tính trì hoãn hoặc nguồn bất đồng bộ.
- Ghép các bước biến đổi bằng `map`, `filter`, `flatMap` và `concatMap`.
- Kết hợp các nguồn độc lập bằng `zip`, `merge` hoặc `concat`.
- Biểu diễn thứ tự phụ thuộc giữa các bước bằng `then` và `thenReturn`.
- Viết phương thức Java trả về Publisher để tầng gọi tiếp tục kết hợp.
- Xác định ranh giới subscribe phù hợp và tránh nested subscription.
- Kiểm thử tín hiệu của chuỗi Reactor bằng `StepVerifier`.

## 1. Chuỗi Reactor là một Publisher được ghép từ nhiều bước

Project Reactor có hai kiểu Publisher thường dùng:

- `Mono<T>` phát tối đa một phần tử rồi hoàn tất, hoàn tất rỗng hoặc phát lỗi.
- `Flux<T>` phát từ không đến nhiều phần tử, rồi hoàn tất hoặc phát lỗi.

Chọn kiểu theo hợp đồng kết quả, không theo việc thao tác có bất đồng bộ hay không. Một truy vấn database trả về một bản ghi thường là `Mono<Customer>`; một truy vấn trả về nhiều bản ghi thường là `Flux<Order>`. Một lời gọi HTTP vẫn có thể trả `Mono` nếu response chỉ có một giá trị.

Ví dụ một chuỗi đơn giản:

~~~java
Mono<String> greeting =
    Mono.just("reactor")
        .map(String::toUpperCase)
        .map(value -> "Hello, " + value);
~~~

Biểu thức tạo một Publisher mới sau mỗi toán tử. `map` biến đổi giá trị đồng bộ; nó không tự subscribe nguồn. Khi có Subscriber, giá trị `"reactor"` đi qua hai phép biến đổi và kết quả cuối là `"Hello, REACTOR"`.

Một chuỗi nhiều phần tử:

~~~java
Flux<Integer> evenNumbers =
    Flux.range(1, 10)
        .filter(number -> number % 2 == 0)
        .map(number -> number * 10);
~~~

Nguồn phát các số từ 1 đến 10. `filter` chỉ giữ số chẵn, còn `map` nhân mỗi số với 10. Kết quả là một Flux phát 20, 40, 60, 80 và 100.

~~~mermaid
flowchart LR
    A[Source] --> B[filter]
    B --> C[map]
    C --> D[Publisher kết quả]
    E[Subscriber] -. subscribe / request .-> D
~~~

Các toán tử trả về Publisher nên ta có thể nối tiếp chúng thành một biểu thức. Việc ghép chuỗi giúp thể hiện quan hệ giữa các bước và giữ tín hiệu dữ liệu, lỗi, hoàn tất, demand và cancellation trong cùng một quy trình.

## 2. Tạo nguồn với factory method

Reactor cung cấp nhiều cách tạo nguồn. Mỗi factory thể hiện một thời điểm và cách tạo dữ liệu khác nhau.

### Giá trị đã có sẵn: just và justOrEmpty

Dùng `Mono.just(value)` khi giá trị đã tồn tại:

~~~java
Customer customer = new Customer("c-101", "An");

Mono<Customer> source = Mono.just(customer);
~~~

Đối số của `Mono.just` được Java đánh giá ngay khi gọi phương thức. Nếu viết `Mono.just(loadCustomer())`, lời gọi `loadCustomer()` xảy ra trong lúc lắp ráp pipeline. Ngoài ra, `Mono.just` không chấp nhận `null`.

Nếu giá trị có thể null và muốn biểu diễn null thành Mono rỗng, dùng `Mono.justOrEmpty`:

~~~java
Mono<Customer> source = Mono.justOrEmpty(customerOrNull);
~~~

Không dùng null như một phần tử của `Mono` hoặc `Flux`. Reactive Streams không cho phép phát null.

### Phép tính cần trì hoãn: fromCallable và fromSupplier

Dùng `fromCallable` khi muốn gọi một phép tính đồng bộ lúc Publisher được subscribe:

~~~java
Mono<Customer> customer =
    Mono.fromCallable(() -> legacyDao.loadCustomer(customerId));
~~~

Callable chỉ được gọi khi có subscription. Nếu nó trả về null, Reactor biểu diễn kết quả thành Mono rỗng; nếu nó ném exception, exception trở thành tín hiệu `onError`.

`fromSupplier` phù hợp với phép tính đồng bộ trả về giá trị:

~~~java
Mono<Instant> now =
    Mono.fromSupplier(Instant::now);
~~~

Mỗi subscription vào nguồn cold này có thể gọi supplier và nhận giá trị được tạo tại thời điểm đó.

Việc trì hoãn không tự biến lời gọi blocking thành non-blocking. Nếu `legacyDao.loadCustomer` dùng JDBC đồng bộ, hãy kết hợp với `subscribeOn(Schedulers.boundedElastic())` để cô lập thread blocking.

### Tạo nguồn mới cho từng subscription: defer

Dùng `defer` khi cần tạo Publisher bên trong mỗi subscription:

~~~java
Mono<Customer> customer =
    Mono.defer(() -> customerRepository.findById(customerId));
~~~

Supplier của `defer` được gọi khi có subscription. Điều này hữu ích khi việc chọn hoặc tạo Publisher phụ thuộc trạng thái tại thời điểm subscribe, hoặc khi mỗi Subscriber cần một nguồn mới.

So sánh:

| Factory | Điều gì được cung cấp? | Thời điểm đánh giá |
|---|---|---|
| `Mono.just(value)` | Giá trị đã có | Đối số được đánh giá trong assembly |
| `Mono.justOrEmpty(value)` | Giá trị có thể null | Đối số được đánh giá trong assembly |
| `Mono.fromCallable(callable)` | Phép tính có thể ném lỗi | Khi nguồn được thực thi theo subscription |
| `Mono.fromSupplier(supplier)` | Phép tính trả giá trị | Khi nguồn được thực thi theo subscription |
| `Mono.defer(supplier)` | Một Publisher khác | Supplier tạo Publisher khi subscribe |

### Nguồn nhiều phần tử

Dùng `Flux.fromIterable` để phát các phần tử của collection:

~~~java
Flux<Order> orders =
    Flux.fromIterable(orderList);
~~~

Dùng `Flux.range` để tạo một dãy số nguyên:

~~~java
Flux<Integer> pages =
    Flux.range(0, 4);
~~~

Dùng `Flux.empty()` khi nguồn không có phần tử nhưng hoàn tất bình thường; dùng `Flux.error(error)` khi nguồn thất bại:

~~~java
Mono<Customer> missing =
    Mono.empty();

Mono<Customer> failed =
    Mono.error(new IllegalStateException("Customer lookup failed"));
~~~

Các factory này giúp biểu diễn rõ ba kết quả khác nhau: có giá trị, không có giá trị và lỗi. Đừng dùng một giá trị null hoặc một chuỗi rỗng để thay thế cả ba trạng thái.

## 3. Biến đổi phần tử với map và filter

`map` nhận một giá trị và trả về một giá trị mới. Dùng nó cho phép biến đổi đồng bộ, ngắn và không cần Publisher con:

~~~java
Mono<CustomerView> view =
    customerRepository.findById(customerId)
        .map(customer ->
            new CustomerView(customer.id(), customer.name())
        );
~~~

Nếu hàm ánh xạ ném exception, Reactor chuyển exception đó thành tín hiệu lỗi của chuỗi. Không cần tự bọc exception bằng `try/catch` rồi gọi `subscribe`.

`filter` giữ lại phần tử đáp ứng điều kiện:

~~~java
Flux<Order> payableOrders =
    orderRepository.findAll()
        .filter(Order::isPaymentPending);
~~~

Với `Mono`, nếu giá trị không vượt qua điều kiện, kết quả trở thành Mono rỗng. Có thể bổ sung `switchIfEmpty` nếu nghiệp vụ cần xử lý trường hợp không có kết quả:

~~~java
Mono<Order> order =
    orderRepository.findById(orderId)
        .filter(Order::isPaymentPending)
        .switchIfEmpty(Mono.error(
            new OrderNotPayableException(orderId)
        ));
~~~

`switchIfEmpty` chỉ chạy Publisher thay thế khi nguồn hoàn tất mà không phát phần tử. Nó không xử lý lỗi; lỗi cần được xử lý bằng các toán tử error tương ứng.

## 4. Ghép Publisher con với flatMap

Khi một phần tử cần kích hoạt một thao tác bất đồng bộ trả về Publisher, dùng `flatMap`. Đây là toán tử thường dùng để kết hợp các bước I/O trong Reactor.

~~~java
Mono<OrderView> orderView =
    orderRepository.findById(orderId)
        .flatMap(order ->
            customerRepository.findById(order.customerId())
                .map(customer -> new OrderView(order, customer))
        );
~~~

`customerRepository.findById` trả về `Mono<Customer>`. `flatMap` đăng ký Publisher con và ghép kết quả vào chuỗi ngoài. Nếu dùng `map` thay thế, kiểu kết quả sẽ là `Mono<Mono<OrderView>>`, tức Publisher lồng nhau.

Với nhiều phần tử, `flatMap` có thể xử lý nhiều Publisher con đồng thời:

~~~java
Flux<OrderView> views =
    orderRepository.findRecent()
        .flatMap(order ->
            customerRepository.findById(order.customerId())
                .map(customer -> new OrderView(order, customer)),
            16
        );
~~~

Tham số `16` giới hạn số Publisher con đang hoạt động đồng thời. Kết quả có thể được phát theo thứ tự hoàn tất của các Publisher con, không nhất thiết theo thứ tự nguồn.

Nếu thứ tự đầu ra phải theo thứ tự nguồn nhưng vẫn muốn các inner chạy đồng thời, dùng `flatMapSequential`. Nếu bản thân các thao tác phải được thực hiện lần lượt, dùng `concatMap`:

~~~java
Flux<OrderResult> sequential =
    orderRepository.findPending()
        .concatMap(order -> orderService.process(order));
~~~

| Toán tử | Cách xử lý Publisher con | Thứ tự đầu ra |
|---|---|---|
| `flatMap` | Có thể chạy đồng thời | Có thể xen kẽ theo thời điểm hoàn tất |
| `flatMapSequential` | Chạy đồng thời | Theo thứ tự nguồn |
| `concatMap` | Subscribe lần lượt, chờ inner hoàn tất | Theo thứ tự nguồn |

Chọn theo yêu cầu nghiệp vụ và năng lực dịch vụ phụ thuộc. Tăng concurrency không phải lúc nào cũng tăng thông lượng; nó có thể làm cạn connection pool hoặc tạo quá nhiều request đang chờ.

## 5. Biểu diễn thứ tự phụ thuộc bằng then

Đôi khi bước sau chỉ cần bắt đầu khi bước trước hoàn tất, nhưng không cần giá trị của bước trước. Dùng `then` để biểu diễn quan hệ đó:

~~~java
Mono<Receipt> receipt =
    inventoryService.reserve(order)
        .then(paymentService.authorize(order));
~~~

Nếu `reserve` trả về `Mono<Reservation>`, `then` bỏ giá trị Reservation và chờ Publisher đó hoàn tất trước khi subscribe vào Publisher thanh toán. Kết quả của chuỗi là `Mono<Receipt>`.

Nếu cần giữ lại giá trị của bước trước, dùng `flatMap`:

~~~java
Mono<OrderReceipt> receipt =
    inventoryService.reserve(order)
        .flatMap(reservation ->
            paymentService.authorize(order)
                .map(payment ->
                    new OrderReceipt(order.id(), reservation.id(), payment.id())
                )
        );
~~~

`thenReturn(value)` chờ nguồn hoàn tất rồi phát một giá trị cố định:

~~~java
Mono<Order> reservedOrder =
    inventoryService.reserve(order)
        .thenReturn(order);
~~~

Các toán tử này thể hiện rõ liệu kết quả của bước trước có được sử dụng hay chỉ cần chờ nó hoàn tất. Không dùng `doOnNext` để gọi một Publisher con rồi bỏ qua nó; hãy ghép Publisher con vào chuỗi.

## 6. Kết hợp các nguồn độc lập

Nếu hai nguồn độc lập và cần cả hai kết quả, dùng `Mono.zip`:

~~~java
Mono<CustomerDashboard> dashboard =
    Mono.zip(
        customerRepository.findById(customerId),
        orderRepository.findRecentByCustomer(customerId).collectList()
    )
    .map(tuple ->
        new CustomerDashboard(tuple.getT1(), tuple.getT2())
    );
~~~

Hai nguồn có thể được subscribe và tiến hành độc lập. Khi cả hai phát giá trị, `zip` kết hợp chúng thành một tuple. Nếu một nguồn hoàn tất rỗng, `zip` có thể hoàn tất rỗng mà không gọi mapper; nếu cần giá trị mặc định cho nguồn tùy chọn, hãy dùng `defaultIfEmpty` hoặc `switchIfEmpty` trước khi zip.

Khi chỉ cần chờ nhiều tác vụ hoàn tất mà không cần giá trị, dùng `Mono.when`:

~~~java
Mono<Void> sideEffects =
    Mono.when(
        auditRepository.record(order),
        notificationService.publishOrderCreated(order)
    );
~~~

`Mono.when` hoàn tất khi các Publisher đầu vào hoàn tất. Nếu một Publisher phát lỗi, kết quả cũng lỗi và các Publisher còn lại do toán tử quản lý có thể bị hủy theo hành vi của toán tử. Nếu nghiệp vụ cần thu thập nhiều lỗi thay vì dừng ngay, hãy xem xét biến thể delay-error phù hợp.

Với nhiều Flux, phân biệt `merge` và `concat`:

~~~java
Flux<Event> merged =
    Flux.merge(primaryEvents, secondaryEvents);

Flux<Event> concatenated =
    Flux.concat(firstBatch, secondBatch);
~~~

`merge` cho phép các nguồn phát xen kẽ theo thời điểm có tín hiệu. `concat` subscribe nguồn sau khi nguồn trước hoàn tất, vì vậy giữ thứ tự theo từng nguồn. Chọn merge khi các luồng độc lập và có thể xen kẽ; chọn concat khi cần tiêu thụ trọn nguồn trước rồi mới đến nguồn sau.

## 7. Ghép pipeline trong phương thức Java

Một service nên mô tả quy trình và trả về Publisher. Ví dụ sau ghép tìm đơn hàng, đặt chỗ tồn kho và thanh toán:

~~~java
@Service
class OrderService {
    private final OrderRepository orders;
    private final InventoryService inventory;
    private final PaymentService payments;

    OrderService(
        OrderRepository orders,
        InventoryService inventory,
        PaymentService payments
    ) {
        this.orders = orders;
        this.inventory = inventory;
        this.payments = payments;
    }

    Mono<OrderReceipt> process(String orderId) {
        return orders.findById(orderId)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order ->
                inventory.reserve(order)
                    .flatMap(reservation ->
                        payments.authorize(order, reservation)
                            .map(payment ->
                                new OrderReceipt(
                                    order.id(),
                                    reservation.id(),
                                    payment.id()
                                )
                            )
                    )
            )
            .doOnError(error ->
                log.warn("Order processing failed: {}", orderId, error)
            );
    }
}
~~~

Phương thức `process` không tự subscribe. Nó trả về `Mono<OrderReceipt>` mô tả toàn bộ workflow. Caller có thể ghép thêm timeout, tracing, recovery hoặc chuyển đổi kết quả. Lỗi từ repository, inventory hoặc payment đi theo cùng một kênh lỗi, trừ khi được xử lý ở một bước cụ thể.

Nếu cần kiểm tra đầu vào trước khi gọi service phụ thuộc, có thể đặt `filter`, `flatMap` hoặc một hàm validation trả về Mono ngay trong chuỗi. Mục tiêu là để các bước có quan hệ nghiệp vụ được biểu diễn thành một Publisher kết quả duy nhất.

### Trả Publisher từ controller

Trong ứng dụng Spring WebFlux, controller có thể trả trực tiếp Publisher:

~~~java
@RestController
class OrderController {
    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @PostMapping("/orders/{id}/process")
    Mono<OrderReceipt> process(@PathVariable String id) {
        return orders.process(id);
    }
}
~~~

Framework quản lý subscription và vòng đời response. Controller không cần gọi `subscribe()` rồi tự chuyển kết quả sang một biến khác. Khi client hủy request, framework có thể hủy subscription tương ứng và cancellation truyền qua pipeline theo hợp đồng của các thành phần tham gia.

Cách tổ chức này giúp tầng web tập trung vào HTTP, service tập trung vào workflow nghiệp vụ, còn repository/client chịu trách nhiệm giao tiếp với nguồn dữ liệu.

## 8. Trả Flux từ phương thức xử lý nhiều phần tử

Một phương thức có thể trả `Flux<T>` khi kết quả là một chuỗi phần tử:

~~~java
@Service
class CatalogService {
    private final ProductRepository products;

    CatalogService(ProductRepository products) {
        this.products = products;
    }

    Flux<ProductView> search(String keyword) {
        return products.search(keyword)
            .filter(Product::isVisible)
            .map(product ->
                new ProductView(product.id(), product.name(), product.price())
            );
    }
}
~~~

Caller có thể tiếp tục ghép pipeline:

~~~java
Flux<ProductView> discounted =
    catalogService.search("keyboard")
        .filter(view -> view.price().compareTo(limit) < 0)
        .take(20);
~~~

`take(20)` giới hạn số phần tử phát xuống downstream. Khi đủ số lượng, cancellation có thể truyền upstream để nguồn ngừng công việc còn có thể dừng.

Nếu cần xử lý từng sản phẩm bằng một Publisher con:

~~~java
Flux<ProductAvailability> availability =
    catalogService.search("keyboard")
        .flatMap(view ->
            inventoryService.findAvailability(view.id())
                .map(stock -> new ProductAvailability(view, stock)),
            8
        );
~~~

Giới hạn concurrency là 8 trong ví dụ. Nếu cần giữ thứ tự sản phẩm từ kết quả tìm kiếm, dùng `flatMapSequential` hoặc `concatMap` theo yêu cầu.

## 9. Đưa xử lý lỗi vào đúng vị trí

Lỗi là một tín hiệu kết thúc của chuỗi nếu không được phục hồi. Dùng `onErrorMap` để chuẩn hóa exception, `onErrorResume` để chuyển sang Publisher thay thế và `doOnError` để quan sát:

~~~java
Mono<Product> product =
    productRepository.findById(productId)
        .switchIfEmpty(Mono.error(new ProductNotFoundException(productId)))
        .doOnError(error -> metrics.recordLookupFailure())
        .onErrorMap(
            DataAccessException.class,
            error -> new CatalogUnavailableException(error)
        )
        .onErrorResume(
            CatalogUnavailableException.class,
            error -> productCache.findById(productId)
        );
~~~

Vị trí toán tử quyết định lỗi nào được quan sát và phục hồi. Ở ví dụ trên, `doOnError` nhìn thấy lỗi trước khi DataAccessException được chuyển đổi. Nếu cần quan sát loại lỗi đã chuẩn hóa, đặt callback sau `onErrorMap`.

Với Flux, một lỗi có thể kết thúc cả luồng. Nếu mỗi phần tử độc lập và lỗi của một phần tử không được làm dừng phần tử còn lại, đặt recovery bên trong mapper:

~~~java
Flux<ImportResult> results =
    records.flatMap(record ->
        importService.importOne(record)
            .map(ImportResult::success)
            .onErrorResume(error ->
                Mono.just(ImportResult.failure(record.id(), error))
            ),
        12
    );
~~~

Trong ứng dụng thực tế, `ImportResult.failure` nên chỉ chứa mã lỗi và thông tin an toàn, không trả nguyên stack trace cho caller. Nếu cần xử lý tuần tự, có thể dùng cùng cách recovery bên trong `concatMap`.

Không nên bắt mọi lỗi rồi trả giá trị mặc định nếu điều đó che giấu lỗi dữ liệu hoặc vi phạm nghiệp vụ. Chọn recovery theo ngữ nghĩa và khả năng phục hồi thực tế.

## 10. Quan sát pipeline mà không tách luồng

Các toán tử `doOn...` phù hợp cho tác dụng phụ quan sát như log, metric và tracing:

~~~java
Mono<OrderReceipt> result =
    orderService.process(orderId)
        .doOnSubscribe(subscription -> metrics.recordStarted())
        .doOnSuccess(receipt -> metrics.recordSucceeded())
        .doOnError(error -> metrics.recordFailed())
        .doFinally(signal -> metrics.recordTerminated(signal));
~~~

Các callback này quan sát vòng đời và tín hiệu, không thay thế kết quả của Publisher. Với `Mono`, `doOnSuccess` cũng được gọi khi Mono hoàn tất rỗng; tham số có thể là null. Nếu chỉ muốn quan sát phần tử thực sự được phát, dùng `doOnNext`.

Tránh gọi `subscribe()` trong `doOnNext` để chạy tác vụ nghiệp vụ phụ:

~~~java
// Không nên: tạo một subscription độc lập.
orders.doOnNext(order ->
    notificationService.sendCreated(order).subscribe()
);
~~~

Pipeline ngoài không chờ notification, không nhận lỗi từ Publisher con và không tự hủy subscription con khi bị cancel. Hãy ghép tác vụ bằng `flatMap` hoặc `then`:

~~~java
Flux<Order> notified =
    orders.flatMap(order ->
        notificationService.sendCreated(order)
            .thenReturn(order),
        8
    );
~~~

Khi đó, notification là một phần của workflow kết quả. Nếu notification là tác vụ nền tách rời theo chủ đích, cần một thành phần sở hữu vòng đời, retry, giới hạn tải và lưu trữ phù hợp thay vì subscribe tùy tiện trong callback.

## 11. Subscription ở ranh giới tiêu thụ

Một pipeline có thể được trả qua nhiều tầng mà chưa thực thi. Ứng dụng cần một điểm tiêu thụ cuối cùng. Với framework như Spring WebFlux, framework subscribe thay caller. Với một tác vụ độc lập ở entry point, mã ứng dụng có thể subscribe:

~~~java
Disposable task =
    reportService.generateDailyReport()
        .subscribe(
            report -> log.info("Report generated: {}", report.id()),
            error -> log.error("Report generation failed", error),
            () -> log.info("Report job completed")
        );
~~~

`subscribe` bắt đầu một subscription. Với overload trả về `Disposable`, mã gọi có thể giữ handle để hủy tác vụ khi chủ sở hữu kết thúc. Cần xử lý callback lỗi rõ ràng, đặc biệt với công việc nền.

Không nên gọi `subscribe()` ở mỗi tầng service. Nếu service tự subscribe, nó không còn trả về Publisher đại diện cho toàn bộ công việc. Caller mất khả năng ghép lỗi, timeout, retry và cancellation vào cùng workflow.

### Khi nào dùng block?

`block()` chờ đồng bộ để lấy kết quả từ Publisher. Nó có thể cần thiết ở một ranh giới tích hợp với mã imperative, nhưng không nên dùng trong event loop hoặc giữa pipeline reactive:

~~~java
// Không nên trong service/controller reactive:
Customer customer = customerRepository.findById(customerId).block();
~~~

Lời gọi này chặn thread hiện tại và phá vỡ lợi ích của xử lý bất đồng bộ. Hãy trả về `Mono<Customer>` để caller ghép tiếp. Nếu buộc phải tích hợp với một API đồng bộ, cô lập ranh giới blocking và kiểm soát timeout, thread cùng vòng đời.

## 12. Kiểm thử chuỗi Reactor

Dùng `StepVerifier` để xác minh các tín hiệu mà Publisher phát ra:

~~~java
Mono<String> greeting =
    Mono.just("reactor")
        .map(String::toUpperCase)
        .map(value -> "Hello, " + value);

StepVerifier.create(greeting)
    .expectNext("Hello, REACTOR")
    .verifyComplete();
~~~

Test xác minh một phần tử được phát rồi luồng hoàn tất. Với Mono rỗng:

~~~java
StepVerifier.create(Mono.<String>empty())
    .verifyComplete();
~~~

Với lỗi:

~~~java
StepVerifier.create(
        Mono.<String>error(new IllegalArgumentException("invalid input"))
    )
    .expectError(IllegalArgumentException.class)
    .verify();
~~~

Với một chuỗi bất đồng bộ có Publisher con:

~~~java
Mono<String> composed =
    Mono.just("order-1")
        .flatMap(id -> Mono.just("processed-" + id));

StepVerifier.create(composed)
    .expectNext("processed-order-1")
    .verifyComplete();
~~~

Các bài kiểm thử hữu ích khác:

- Nguồn chỉ được thực thi khi có subscription.
- Nhiều subscription có tạo số lần gọi nguồn như dự kiến không?
- `flatMap` có giới hạn concurrency và thứ tự phù hợp không?
- `concatMap` có chờ inner hoàn tất không?
- `zip` xử lý nguồn rỗng như thế nào?
- Lỗi từ Publisher con có đi tới đúng recovery không?
- Cancellation có được truyền tới nguồn và cleanup tài nguyên không?

Kiểm thử nên xác minh hợp đồng quan sát được: giá trị, thứ tự, lỗi, hoàn tất, demand và cancellation. Không cần phụ thuộc vào chi tiết thread nội bộ nếu đó không phải yêu cầu của bài.

## 13. Những nhầm lẫn thường gặp

- **Tạo Mono nghĩa là công việc đã chạy:** phần lớn Publisher chỉ mô tả công việc; subscription mới khởi động nguồn theo đặc tính của nó.
- **`Mono.just(methodCall())` trì hoãn lời gọi:** Java đánh giá đối số trước khi gọi `just`; dùng `fromCallable` hoặc `defer` nếu cần trì hoãn.
- **`map` tự kết hợp Publisher con:** `map` tạo Publisher lồng nhau; dùng `flatMap` để ghép Publisher con.
- **`flatMap` luôn giữ thứ tự nguồn:** inner có thể hoàn tất theo thứ tự khác; chọn `flatMapSequential` hoặc `concatMap` khi cần thứ tự.
- **`then` giữ giá trị của bước trước:** `then` bỏ giá trị trước và chờ hoàn tất; dùng `flatMap` nếu cần giá trị đó.
- **`zip` luôn phát kết quả khi một nguồn có giá trị:** `zip` cần mỗi nguồn phát một giá trị; nguồn rỗng có thể khiến kết quả rỗng.
- **`doOnNext` là nơi ghép tác vụ bất đồng bộ:** callback quan sát không tự kết hợp Publisher trả về; dùng toán tử ghép.
- **Service nên tự subscribe để bảo đảm chạy:** service nên trả Publisher; caller hoặc framework sở hữu subscription ở biên tiêu thụ.
- **`block()` là cách đơn giản để nối các tầng:** block chặn thread và làm đứt chuỗi reactive.
- **Fallback nên áp dụng cho mọi lỗi:** recovery cần phân biệt lỗi dữ liệu, nghiệp vụ và hạ tầng, tránh che giấu nguyên nhân.

## 14. Bài tập vận dụng

Một ứng dụng cần tạo trang chi tiết đơn hàng. Để dựng trang, service phải:

1. Đọc đơn hàng theo ID.
2. Đọc thông tin khách hàng tương ứng.
3. Đọc danh sách dòng hàng.
4. Kết hợp ba kết quả thành `OrderDetailView`.

Hãy thiết kế chuỗi Reactor:

- Phương thức service nên trả về `Mono<OrderDetailView>` hay `Flux<OrderDetailView>`? Vì sao?
- Nếu đơn hàng không tồn tại, nên biểu diễn kết quả thế nào?
- Hai truy vấn khách hàng và dòng hàng có độc lập sau khi đã có đơn hàng không? Dùng toán tử nào để kết hợp?
- Nếu một nguồn phụ hoàn tất rỗng, `zip` sẽ có hành vi gì? Có cần giá trị mặc định không?
- Controller WebFlux nên trả Publisher hay gọi `block()`?
- Viết một kiểm thử `StepVerifier` xác nhận view được phát và luồng hoàn tất.

**Gợi ý:** dùng `findById` để lấy `Mono<Order>`, `switchIfEmpty` cho trường hợp không tìm thấy, sau đó `flatMap` để bắt đầu hai truy vấn độc lập. Dùng `Mono.zip(customerMono, linesMono.collectList())` để kết hợp kết quả và `map` để tạo view. Trả Mono từ controller để framework quản lý subscription.

## Kết luận

Tạo và ghép chuỗi Reactor trong Java là việc chọn đúng nguồn `Mono` hoặc `Flux`, nối các phép biến đổi đồng bộ và Publisher con bất đồng bộ, rồi trả Publisher về tầng gọi. Dùng `map` và `filter` cho biến đổi, `flatMap` cho công việc bất đồng bộ, `concatMap` khi cần tuần tự, `zip` cho nguồn độc lập và `then` cho thứ tự phụ thuộc không cần giữ giá trị trước. Giữ lỗi, demand và cancellation trong cùng chuỗi bằng cách tránh nested subscription; để caller hoặc framework subscribe ở ranh giới tiêu thụ. Khi kết hợp thiết kế này với `StepVerifier`, ta có thể xây dựng các phương thức service dễ ghép, dễ kiểm thử và phù hợp với mô hình reactive.

# Ranh giới dùng block trong mã mệnh lệnh và tránh block trên event loop trong Spring WebFlux

## 1. Vì sao cần một ranh giới block?

WebClient trả về Mono<T> hoặc Flux<T>. Publisher mô tả một thao tác bất đồng bộ; nó chưa phải kết quả Java có sẵn ngay tại thời điểm gọi method.

Trong WebFlux, cách tự nhiên là giữ publisher xuyên suốt request path:

~~~java
@GetMapping("/products/{id}")
Mono<Product> getProduct(@PathVariable String id) {
    return productClient.getProduct(id);
}
~~~

Spring WebFlux subscribe và ghi response theo reactive lifecycle. Thread xử lý request không cần chờ đồng bộ cho tới khi upstream trả lời.

Tuy nhiên, không phải mọi phần của hệ thống đều reactive. Ứng dụng có thể cần tích hợp với batch job, command-line tool, thư viện cũ chỉ có API đồng bộ, adapter cho hệ thống kế thừa hoặc một đoạn test cần lấy kết quả để assertion.

Trong những ranh giới đó, block() có thể là lựa chọn hợp lệ nếu thread hiện tại được phép chờ. Điều quan trọng là **vị trí thực thi của lời gọi block**, không phải tên class hoặc method chứa nó.

Một method tên ImperativeAdapter vẫn không an toàn nếu được gọi từ event loop của WebFlux. Ngược lại, method gọi block() từ main thread của CLI hoặc worker thread thông thường có thể phù hợp.

## 2. Event loop là gì và vì sao không được block?

WebFlux thường chạy trên server non-blocking như Reactor Netty. Thay vì cấp một thread riêng cho từng request và để thread đó chờ I/O, server dùng một số lượng event-loop worker nhỏ, cố định để xử lý nhiều kết nối.

~~~text
Nhiều HTTP connections
   |       |       |
   v       v       v
+-----------------------+
| Event-loop workers    |
|                       |
| nhận I/O events       |
| chạy callback         |
| chuyển reactive signal|
| ghi response          |
+-----------------------+
           |
           v
    upstream I/O events
~~~

Một event-loop thread có thể phục vụ nhiều request và callback. Khi một request gọi thao tác blocking, thread đó không thể tiếp tục xử lý công việc khác trong thời gian chờ.

Hậu quả có thể gồm:

- Nhiều request khác tăng latency dù upstream của chúng đã sẵn sàng.
- Kết nối mới và callback I/O bị xử lý chậm.
- Throughput giảm mạnh khi tải tăng.
- Timer, timeout và các tác vụ reactive trên cùng worker bị trễ.
- Nếu code chờ một kết quả mà chính event loop cần xử lý để tạo ra, ứng dụng có thể rơi vào deadlock hoặc timeout.
- Reactor có thể ném IllegalStateException khi phát hiện blocking API được gọi trên thread được đánh dấu non-blocking.

Đây là lý do không gọi block() trên event loop, kể cả khi request chỉ chờ một API nhanh vài mili giây. Một lần block ngắn vẫn chiếm thread dùng chung.

## 3. block() thực sự làm gì?

Mono.block() subscribe vào publisher hiện tại và chờ một giá trị hoặc terminal signal:

~~~java
Product product = webClient.get()
    .uri("/products/{id}", 42)
    .retrieve()
    .bodyToMono(Product.class)
    .block();
~~~

Lệnh trên chuyển pipeline bất đồng bộ thành lời gọi đồng bộ tại thread đang chạy nó. Thread gọi phải chờ response.

Các đặc điểm quan trọng:

1. block() tạo subscription mới mỗi lần được gọi. Với một WebClient request lạnh (cold publisher), gọi block hai lần thường gửi hai HTTP request.
2. block() trả giá trị khi Mono phát item rồi complete.
3. Nếu Mono complete mà không phát item, block() trả null.
4. Nếu Mono phát error, lỗi được ném về thread gọi block.
5. Nếu publisher không phát tín hiệu, block() không có timeout và có thể chờ vô hạn.
6. block(Duration) giới hạn thời gian chờ của caller; nó không làm cho thread đang chờ trở thành non-blocking.
7. Với Mono<Void>, complete bình thường trả về null vì publisher không phát object.

Ví dụ có timeout:

~~~java
Product product = webClient.get()
    .uri("/products/{id}", 42)
    .retrieve()
    .bodyToMono(Product.class)
    .block(Duration.ofSeconds(5));
~~~

Nếu không có tín hiệu trong năm giây, lời gọi chờ kết thúc bằng timeout exception. Cần phân biệt timeout của Reactor với connect/read/response timeout ở HTTP client; cấu hình transport timeout vẫn cần thiết.

### 3.1. blockOptional() để biểu diễn kết quả rỗng

Nếu publisher có thể complete mà không phát giá trị, blockOptional() giúp biểu diễn trường hợp đó rõ hơn:

~~~java
Optional<Product> product = productMono
    .blockOptional(Duration.ofSeconds(5));
~~~

Kết quả là Optional.of(product) nếu Mono phát một Product, hoặc Optional.empty() nếu Mono complete mà không phát item.

Điều này khác với một ResponseEntity<Product> có body null. Trong trường hợp thứ hai, Mono vẫn có thể phát một ResponseEntity; Optional bên ngoài vẫn có giá trị.

Không dùng blockOptional() để che giấu lỗi. Error từ publisher vẫn được truyền ra ngoài.

## 4. Ranh giới dùng block hợp lệ

Có thể dùng block() khi chương trình đang ở một ranh giới đồng bộ thực sự và thread hiện tại được phép chờ.

| Ranh giới | Có thể block? | Điều kiện |
| --- | --- | --- |
| Main method của CLI | Có | Chờ ở thread điều khiển chương trình, có timeout |
| Batch worker thread | Có | Worker được thiết kế để chạy tác vụ đồng bộ |
| Test method JUnit | Có | Test thread không phải event loop; thường ưu tiên StepVerifier |
| Công cụ migration chạy một lần | Có | Chờ có kiểm soát và đóng tài nguyên đúng lifecycle |
| Adapter cho API đồng bộ cũ | Có thể | Chỉ được gọi từ thread blocking-safe |
| WebFlux controller | Không | Return Mono/Flux cho framework |
| WebFlux WebFilter | Không | Compose publisher và return Mono<Void> |
| Reactor Netty event loop | Không | Không chờ đồng bộ |
| Scheduler parallel/single | Không | Đây là các scheduler non-blocking |
| Callback của WebClient | Không | Tiếp tục bằng map/flatMap/then |

Một ranh giới tốt thường có một method tên và contract thể hiện rõ tính đồng bộ, ví dụ fetchForBatchBlocking. Method đó không nên được gọi từ controller, WebFilter hoặc callback đang chạy trên event loop.

### 4.1. Ví dụ adapter cho batch job

~~~java
public final class ProductBatchAdapter {
    private final ProductService productService;

    public ProductBatchAdapter(ProductService productService) {
        this.productService = productService;
    }

    // Chỉ gọi từ batch/CLI worker thread, không gọi từ WebFlux event loop.
    public ProductSnapshot fetchForBatch(String productId) {
        return productService.fetch(productId)
            .blockOptional(Duration.ofSeconds(5))
            .orElseThrow(() ->
                new IllegalStateException("Product response was empty")
            );
    }
}
~~~

Adapter chặn ở đúng ranh giới và có timeout. Phần service bên trong vẫn có thể giữ API reactive để được tái sử dụng bởi WebFlux controller.

Đặt tên có hậu tố Blocking hoặc ForBatch giúp người gọi nhận ra contract, nhưng tên không thay thế việc kiểm soát thread thực tế.

## 5. Không block trong WebFlux controller

Đây là cách sai:

~~~java
@GetMapping("/products/{id}")
Mono<Product> getProduct(@PathVariable String id) {
    Product product = productClient.getProduct(id)
        .block(Duration.ofSeconds(5));

    return Mono.just(product);
}
~~~

Controller đang chạy trong request processing path của WebFlux. Khi gọi block, nó giữ thread trong lúc đợi WebClient. Sau đó tạo Mono mới không làm cho thao tác chờ vừa xảy ra trở thành bất đồng bộ.

Cách đúng:

~~~java
@GetMapping("/products/{id}")
Mono<Product> getProduct(@PathVariable String id) {
    return productClient.getProduct(id);
}
~~~

Nếu cần status, header và body của WebClient response, giữ nguyên ResponseEntity trong reactive pipeline:

~~~java
@GetMapping("/products/{id}")
Mono<ResponseEntity<Product>> getProduct(@PathVariable String id) {
    return productClient.getProductEntity(id);
}
~~~

Hoặc chuyển đổi metadata bằng operator:

~~~java
Mono<ProductView> view = productClient.getProductEntity(id)
    .map(response -> new ProductView(
        response.getStatusCode().value(),
        response.getHeaders().getETag(),
        response.getBody()
    ));
~~~

Nếu phải gọi thêm một API phụ thuộc kết quả đầu tiên, dùng flatMap:

~~~java
Mono<ProductView> view = productClient.getProduct(id)
    .flatMap(product ->
        inventoryClient.getInventory(product.id())
            .map(inventory -> new ProductView(product, inventory))
    );
~~~

Nếu hai request độc lập, có thể ghép bằng Mono.zip rồi chỉ phát một kết quả khi cả hai hoàn tất. Không cần block từng request.

## 6. Không block trong WebFilter, handler hoặc callback reactive

Quy tắc tương tự áp dụng ngoài controller:

- WebFilter.filter phải return publisher cho chain.
- Functional handler nên return Mono<ServerResponse>.
- map, flatMap, doOnNext và callback của WebClient không được chờ đồng bộ.
- Không gọi Thread.sleep để chờ event hoặc retry.
- Không gọi Future.get() hoặc CompletableFuture.join() trên event loop.
- Không gọi toStream() hoặc toIterable() để duyệt publisher vô hạn trong request path.

Ví dụ WebFilter đúng:

~~~java
@Component
public class RequestAuditFilter implements WebFilter {
    private final AuditService auditService;

    public RequestAuditFilter(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return auditService.recordRequest(exchange.getRequest())
            .then(chain.filter(exchange));
    }
}
~~~

then nối completion của audit publisher với filter chain. Không cần gọi block() để chờ ghi audit xong.

Nếu audit library chỉ có API blocking, hãy bọc riêng thao tác đó bằng Mono.fromCallable và boundedElastic.

## 7. Tích hợp thư viện blocking bằng boundedElastic

Có thể gặp JDBC đồng bộ, SDK cũ, filesystem API hoặc thư viện HTTP blocking. Không gọi chúng trực tiếp trên event loop.

Reactor cung cấp pattern chuẩn:

~~~java
Mono<Inventory> inventory =
    Mono.fromCallable(() -> legacyInventoryClient.lookup(sku))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Hai phần có vai trò khác nhau:

- Mono.fromCallable trì hoãn lời gọi blocking cho tới khi có subscription và chuyển giá trị trả về thành Mono.
- subscribeOn(Schedulers.boundedElastic()) chuyển quá trình subscribe và thực thi source sang worker phù hợp với tác vụ blocking.

boundedElastic có giới hạn số thread và hàng đợi để hấp thụ tác vụ blocking mà không tạo thread vô hạn. Khi tải vượt năng lực, tác vụ có thể phải chờ trong queue hoặc bị từ chối theo giới hạn cấu hình.

Không xem boundedElastic như tài nguyên vô hạn. Hãy đo thời gian chờ, số tác vụ đang chạy, queue và lỗi quá tải.

### 7.1. Không dùng Mono.just cho lời gọi blocking

Sai:

~~~java
Mono<Inventory> inventory =
    Mono.just(legacyInventoryClient.lookup(sku))
        .subscribeOn(Schedulers.boundedElastic());
~~~

lookup(sku) được thực thi ngay lúc tạo biểu thức Mono.just, trước khi scheduler có thể chuyển source sang worker. Nếu đoạn code đang chạy trên event loop, thao tác blocking đã xảy ra trên event loop.

Đúng:

~~~java
Mono<Inventory> inventory =
    Mono.fromCallable(() -> legacyInventoryClient.lookup(sku))
        .subscribeOn(Schedulers.boundedElastic());
~~~

fromCallable chỉ gọi lookup khi subscribe diễn ra trên scheduler đã chọn.

### 7.2. API blocking không trả về giá trị

Nếu thư viện đồng bộ trả void, dùng Mono.fromRunnable:

~~~java
Mono<Void> saveAudit(AuditRecord record) {
    return Mono.fromRunnable(() -> blockingAuditClient.write(record))
        .subscribeOn(Schedulers.boundedElastic())
        .then();
}
~~~

Nếu tác vụ trả nhiều kết quả nhưng API đồng bộ đã aggregate thành List, có thể dùng Mono.fromCallable với List. Nếu nguồn thực sự là stream, cân nhắc API streaming phù hợp thay vì đọc toàn bộ dữ liệu vào RAM.

### 7.3. Null từ thư viện cũ

Mono.fromCallable không phát giá trị nếu Callable trả null; nó complete empty. Nếu API cũ dùng null để biểu diễn không tìm thấy dữ liệu, hãy chuyển đổi semantics đó một cách tường minh:

~~~java
Mono<Inventory> inventory =
    Mono.fromCallable(() -> legacyInventoryClient.lookup(sku))
        .subscribeOn(Schedulers.boundedElastic())
        .switchIfEmpty(Mono.error(
            new InventoryNotFoundException(sku)
        ));
~~~

Chỉ dùng switchIfEmpty khi null thực sự có nghĩa là not found. Nếu null biểu diễn trạng thái khác, hãy chuyển sang Optional hoặc kiểu kết quả domain rõ ràng.

## 8. subscribeOn và publishOn khác nhau thế nào?

Hai operator đều chuyển execution context, nhưng vị trí tác động khác nhau.

| Operator | Tác động | Cách dùng điển hình |
| --- | --- | --- |
| subscribeOn(scheduler) | Chuyển quá trình subscribe/source execution sang scheduler | Bọc source blocking bằng fromCallable |
| publishOn(scheduler) | Chuyển signal và operator phía downstream sau vị trí publishOn | Chuyển bước xử lý tiếp theo sang worker |

Ví dụ subscribeOn:

~~~java
Mono<Data> result =
    Mono.fromCallable(() -> blockingClient.fetch())
        .subscribeOn(Schedulers.boundedElastic())
        .map(this::convert);
~~~

Source blocking và map phía sau chạy theo execution context đã chọn, trừ khi có operator khác đổi scheduler.

Ví dụ publishOn:

~~~java
Mono<String> result =
    webClient.get()
        .uri("/data")
        .retrieve()
        .bodyToMono(Data.class)
        .publishOn(Schedulers.boundedElastic())
        .map(legacyFormatter::format);
~~~

WebClient vẫn thực hiện I/O theo cơ chế non-blocking của connector. publishOn chuyển bước map phía sau sang boundedElastic vì formatter là blocking.

Với một lời gọi blocking độc lập, pattern fromCallable(...).subscribeOn(boundedElastic()) thường dễ đọc và cô lập hơn.

### 8.1. Không nhầm scheduler với quyền gọi block

Đoạn sau vẫn sai nếu được gọi từ event loop:

~~~java
Product product = webClient.get()
    .uri("/products/42")
    .retrieve()
    .bodyToMono(Product.class)
    .subscribeOn(Schedulers.boundedElastic())
    .block(Duration.ofSeconds(5));
~~~

subscribeOn có thể chuyển subscription và source work. Nhưng block() vẫn chặn thread gọi nó cho tới khi có kết quả. Nếu thread gọi là event loop, chính event loop đó vẫn bị giữ lại.

Tương tự, publishOn(Schedulers.boundedElastic()) không biến một lệnh block() đặt trước publishOn thành an toàn.

**Scheduler chuyển nơi thực thi các phần reactive; nó không thay đổi bản chất đồng bộ của lời gọi block ở thread hiện tại.**

## 9. Đừng dùng boundedElastic để che một WebClient block

Không nên viết:

~~~java
Mono<Product> product =
    Mono.fromCallable(() ->
        webClient.get()
            .uri("/products/42")
            .retrieve()
            .bodyToMono(Product.class)
            .block()
    ).subscribeOn(Schedulers.boundedElastic());
~~~

WebClient vốn đã non-blocking. Bọc nó trong Callable rồi block sẽ chiếm một worker boundedElastic trong suốt thời gian chờ network, biến I/O non-blocking thành blocking, tốn thêm thread và làm mất lợi ích của reactive I/O.

Đúng:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/42")
    .retrieve()
    .bodyToMono(Product.class);
~~~

Chỉ offload đoạn code thực sự blocking, ví dụ SDK cũ hoặc JDBC đồng bộ. Đừng offload toàn bộ WebClient chỉ vì publisher của nó chưa phát kết quả ngay lập tức.

## 10. Mã mệnh lệnh cần gọi nhiều WebClient request

Nếu một batch job cần hai API độc lập, đừng block sau từng request:

~~~java
Product product = productClient.getProduct(id)
    .block(Duration.ofSeconds(5));

List<Review> reviews = reviewClient.getReviews(id)
    .collectList()
    .block(Duration.ofSeconds(5));
~~~

Cách này tạo hai lần chờ tuần tự. Tổng thời gian có thể gần bằng tổng latency của hai upstream.

Hãy compose trước rồi block một lần ở ranh giới:

~~~java
Mono<BatchProductReport> report =
    Mono.zip(
        productClient.getProduct(id),
        reviewClient.getReviews(id).collectList()
    ).map(tuple ->
        new BatchProductReport(tuple.getT1(), tuple.getT2())
    );

BatchProductReport result =
    report.block(Duration.ofSeconds(8));
~~~

Hai request độc lập có thể chạy đồng thời. Caller chỉ chờ một kết quả tổng hợp.

Nếu request thứ hai phụ thuộc dữ liệu từ request đầu tiên, dùng flatMap rồi block một lần sau cùng:

~~~java
Mono<OrderDetails> details =
    orderClient.getOrder(orderId)
        .flatMap(order ->
            customerClient.getCustomer(order.customerId())
                .map(customer -> new OrderDetails(order, customer))
        );

OrderDetails result =
    details.block(Duration.ofSeconds(8));
~~~

## 11. Xử lý Flux ở ranh giới đồng bộ

Flux<T> có thể phát nhiều phần tử. Nếu nguồn hữu hạn và kích thước được kiểm soát, có thể aggregate thành List rồi block:

~~~java
List<Product> products = webClient.get()
    .uri("/products")
    .retrieve()
    .bodyToFlux(Product.class)
    .collectList()
    .block(Duration.ofSeconds(10));
~~~

Cách này phù hợp với một danh sách hữu hạn, có giới hạn kích thước rõ ràng.

Không dùng collectList() với stream vô hạn hoặc dữ liệu rất lớn. Nó phải giữ toàn bộ phần tử trong bộ nhớ trước khi trả List.

Các API như blockFirst(), blockLast(), toIterable() và toStream() cũng có thể chặn caller. Không dùng chúng trên event loop. Với streaming lớn, nên giữ publisher reactive hoặc thiết kế consumer đồng bộ riêng có queue/backpressure và giới hạn tài nguyên rõ ràng.

## 12. CompletableFuture và các cách chờ tương đương

Không chỉ Mono.block() mới gây blocking. Những lời gọi sau cũng chặn thread:

~~~java
future.get();
future.join();
mono.toFuture().get();
mono.toFuture().join();
~~~

toFuture() tự nó tạo một CompletableFuture bridge; lời gọi get() hoặc join() mới là thao tác chờ đồng bộ.

Nếu đã có CompletableFuture, đưa nó vào reactive pipeline:

~~~java
Mono<Customer> customer =
    Mono.fromFuture(legacyAsyncClient.fetchCustomer(id));
~~~

Nếu API trả CompletionStage, có thể dùng Mono.fromCompletionStage. Sau đó compose bằng map/flatMap thay vì gọi get/join.

Nếu một imperative caller thực sự cần kết quả, block một lần ở outer boundary với timeout. Không block giữa các bước của pipeline.

## 13. Timeout, cancellation và giới hạn của blocking call

Timeout là cần thiết, nhưng không giải quyết được mọi vấn đề.

### 13.1. block(Duration) giới hạn thời gian chờ của caller

~~~java
Product product = productMono
    .block(Duration.ofSeconds(4));
~~~

Caller không chờ vô hạn. Khi quá hạn, Reactor kết thúc thao tác chờ bằng timeout exception và hủy subscription theo semantics của API.

### 13.2. Timeout không bảo đảm thư viện blocking dừng ngay

Nếu source là JDBC driver hoặc SDK blocking không phản hồi interruption, việc hủy subscription không nhất thiết dừng ngay lệnh I/O đang chạy. Vì vậy:

- Cấu hình connection timeout, socket/read timeout hoặc query timeout ở thư viện gốc.
- Giới hạn số blocking worker và queue.
- Không dựa vào Reactor timeout làm timeout duy nhất cho API blocking.
- Theo dõi các tác vụ vẫn chạy sau khi caller đã timeout.

### 13.3. Timeout của WebClient

WebClient có thể cấu hình timeout ở connector/client phù hợp với transport. Ngoài ra, có thể đặt Reactor timeout cho toàn bộ publisher:

~~~java
Mono<ResponseEntity<Product>> response =
    webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .toEntity(Product.class)
        .timeout(Duration.ofSeconds(4));
~~~

Transport timeout và publisher timeout giải quyết các lớp khác nhau. Hãy đặt cả hai theo SLA; tránh retry tự động không giới hạn khi upstream đã quá tải.

## 14. Scheduler nào dành cho công việc nào?

| Scheduler | Mục đích | Có phù hợp cho blocking I/O? |
| --- | --- | --- |
| Schedulers.parallel() | CPU-bound work, số worker gần số CPU core | Không |
| Schedulers.single() | Một worker dùng chung cho các tác vụ tuần tự | Không |
| Schedulers.boundedElastic() | Cô lập blocking I/O hoặc API đồng bộ cũ | Có, trong giới hạn |
| Schedulers.immediate() | Thực thi ngay trên thread hiện tại | Không tạo isolation |
| Schedulers.newBoundedElastic(...) | Pool riêng có giới hạn do ứng dụng quản lý | Có, khi cần isolation riêng |

Không chuyển blocking I/O sang parallel(). Reactor đánh dấu thread mặc định của single/parallel là non-blocking; gọi blocking API như block trên các thread đó có thể gây IllegalStateException.

boundedElastic được thiết kế để hấp thụ blocking work với giới hạn. Nếu mọi request đều đẩy nhiều tác vụ blocking vào đó, pool vẫn có thể quá tải. Tối ưu gốc bằng reactive driver hoặc API non-blocking nếu có.

Nếu tạo scheduler riêng bằng newBoundedElastic, ứng dụng phải quản lý và dispose scheduler khi không còn dùng. Không tạo scheduler mới cho từng request.

## 15. Spring MVC, Spring WebFlux và mã đồng bộ

Spring MVC và Spring WebFlux có concurrency model khác nhau.

| Đặc điểm | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Mô hình thường gặp | Servlet request thread xử lý request | Event-loop worker xử lý nhiều request |
| Giả định mặc định | Có thể dùng blocking I/O trên servlet worker | Không block request-processing thread |
| Reactive return type | Có thể trả Mono/Flux | Là mô hình tự nhiên |
| Blocking code | Chiếm một servlet thread; cần giới hạn pool | Có thể chặn event loop và ảnh hưởng nhiều request |
| HTTP client đồng bộ | RestClient phù hợp với imperative flow | Ưu tiên WebClient non-blocking |
| Tích hợp thư viện blocking | Có thể chạy trên servlet worker hoặc executor | Offload sang boundedElastic hoặc worker chuyên dụng |

Một controller Spring MVC chạy theo mô hình đồng bộ có thể dùng API blocking, nhưng mỗi request chờ sẽ chiếm servlet thread và cần tính capacity. Nếu dùng Mono hoặc Flux, hãy trả publisher cho Spring xử lý thay vì block rồi bọc lại.

Trong WebFlux, không gọi block trong controller. Hãy giữ request path non-blocking.

Nếu ứng dụng hoàn toàn imperative và không cần reactive composition, RestClient là lựa chọn đồng bộ phù hợp trong Spring Framework hiện đại. WebClient vẫn có thể được dùng ở synchronous style bằng cách block ở cuối một luồng imperative ngoài controller/event loop.

## 16. Cách kiểm tra và phát hiện blocking

Một số dấu hiệu giúp tìm blocking call:

- Thread dump có event-loop worker nằm lâu trong socket read, JDBC, file I/O, monitor wait hoặc Thread.sleep.
- Log thread name cho thấy code request path đang chạy trên thread kiểu reactor-http-nio-*.
- Latency tăng đồng thời trên nhiều endpoint dù upstream khác nhau.
- Reactor ném thông báo block() không được hỗ trợ trên thread non-blocking.
- Thread pool boundedElastic có queue dài hoặc nhiều worker chờ I/O.

Có thể log thread name trong lúc điều tra:

~~~java
.doOnNext(value ->
    log.debug("Processing on thread {}",
        Thread.currentThread().getName()))
~~~

Không dùng tên thread làm logic production; tên có thể thay đổi theo server và cấu hình.

### 16.1. BlockHound trong test

BlockHound giúp phát hiện một số lời gọi blocking trên thread được đánh dấu non-blocking. Có thể cài đặt trong test/integration test:

~~~java
@BeforeAll
static void installBlockHound() {
    BlockHound.install();
}
~~~

BlockHound không thay thế code review và kiểm thử tải. Một số thư viện cần integration hoặc allow-list; không có cảnh báo không chứng minh toàn bộ code path là non-blocking.

## 17. Các anti-pattern thường gặp

| Anti-pattern | Vì sao có vấn đề | Cách sửa |
| --- | --- | --- |
| block trong WebFlux controller | Giữ event-loop trong lúc chờ | Return Mono/Flux |
| block trong WebFilter | Chặn request chain trên worker | Compose publisher và return Mono<Void> |
| block trong map/flatMap callback | Callback có thể chạy trên event loop | Dùng operator reactive hoặc offload đúng đoạn blocking |
| Mono.just(blockingCall()) | Blocking call chạy ngay khi assembly | Mono.fromCallable(...).subscribeOn(boundedElastic) |
| Mono.fromCallable(() -> webClient...block()) | Biến WebClient non-blocking thành blocking | Dùng WebClient publisher trực tiếp |
| subscribeOn rồi block ở event loop | Caller vẫn bị block | Chỉ block ở imperative boundary |
| publishOn rồi block trước operator | Scheduler switch chưa xảy ra tại vị trí block | Không block giữa pipeline |
| block nhiều lần trên cùng Mono | Mỗi lần có thể tạo subscription/request mới | Compose rồi block một lần |
| block không timeout trong batch | Có thể chờ vô hạn | block(Duration) và timeout transport |
| collectList trên Flux vô hạn | Không complete và giữ bộ nhớ tăng mãi | Giữ streaming hoặc giới hạn bằng take |
| Future.get/join trên event loop | Blocking tương tự block | Mono.fromFuture và compose |
| Thread.sleep trong reactive chain | Chặn worker và làm trễ signal | delayElement/delaySubscription hoặc timer Reactor |
| Dùng parallel cho JDBC | Block CPU scheduler non-blocking | boundedElastic hoặc reactive driver |
| Tạo scheduler mỗi request | Rò rỉ thread và chi phí tạo pool | Dùng shared boundedElastic hoặc pool được quản lý |
| Nuốt timeout thành empty | Mất nguyên nhân và có thể tạo kết quả giả | Map timeout thành lỗi domain rõ ràng |

## 18. Java 17+ Spring Boot WebFlux demo

Demo gồm một WebClient gọi upstream, một service giữ publisher reactive, một WebFlux controller trả Mono và một adapter batch minh họa điểm block ở imperative boundary.

### 18.1. Cấu trúc dự án

~~~text
webflux-block-boundary/
  build.gradle
  src/
    main/
      java/demo/
        DemoApplication.java
        Product.java
        ProductClient.java
        ProductService.java
        ProductController.java
        ProductBatchAdapter.java
      resources/
        application.properties
    test/
      java/demo/
        BlockingBoundaryTest.java
~~~

### 18.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 18.3. application.properties

~~~properties
spring.application.name=webflux-block-boundary
catalog.base-url=http://localhost:9090
~~~

Trong test, DynamicPropertySource thay base URL bằng MockWebServer cục bộ.

### 18.4. DemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 18.5. Product.java

~~~java
package demo;

import java.math.BigDecimal;

public record Product(
    long id,
    String name,
    BigDecimal price
) {
}
~~~

### 18.6. ProductClient.java

~~~java
package demo;

import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ProductClient {
    private final WebClient webClient;

    public ProductClient(
            WebClient.Builder builder,
            Environment environment) {
        String baseUrl =
            environment.getRequiredProperty("catalog.base-url");
        this.webClient = builder.baseUrl(baseUrl).build();
    }

    public Mono<ResponseEntity<Product>> getProduct(String id) {
        return webClient.get()
            .uri("/products/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .toEntity(Product.class);
    }
}
~~~

Method trả Mono<ResponseEntity<Product>>. Nó giữ status, headers và body trong cùng một publisher. Không có lời gọi block trong client.

### 18.7. ProductService.java

~~~java
package demo;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ProductService {
    private final ProductClient client;

    public ProductService(ProductClient client) {
        this.client = client;
    }

    public Mono<ResponseEntity<Product>> getProduct(String id) {
        return client.getProduct(id)
            .map(remote -> {
                HttpHeaders headers = new HttpHeaders();

                String etag = remote.getHeaders().getETag();
                if (etag != null) {
                    headers.setETag(etag);
                }

                String requestId =
                    remote.getHeaders().getFirst("X-Request-Id");
                if (requestId != null) {
                    headers.set("X-Request-Id", requestId);
                }

                return new ResponseEntity<>(
                    remote.getBody(),
                    headers,
                    remote.getStatusCode()
                );
            });
    }
}
~~~

Service chỉ chuyển tiếp các header đã chọn. Nó không chuyển tiếp mù quáng toàn bộ header của upstream.

### 18.8. ProductController.java

~~~java
package demo;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/api/products/{id}")
    public Mono<ResponseEntity<Product>> getProduct(
            @PathVariable String id) {
        return service.getProduct(id);
    }
}
~~~

Controller trả publisher cho WebFlux. Nó không gọi block hoặc subscribe.

### 18.9. ProductBatchAdapter.java

~~~java
package demo;

import java.time.Duration;
import org.springframework.http.ResponseEntity;

public class ProductBatchAdapter {
    private final ProductService service;

    public ProductBatchAdapter(ProductService service) {
        this.service = service;
    }

    // Chỉ gọi từ batch/CLI worker thread, không gọi từ event loop.
    public ResponseEntity<Product> fetchForBatch(String id) {
        return service.getProduct(id)
            .blockOptional(Duration.ofSeconds(5))
            .orElseThrow(() ->
                new IllegalStateException("No response entity")
            );
    }
}
~~~

Đây là imperative boundary. Adapter chặn một lần, có timeout và biểu diễn empty publisher bằng exception rõ ràng. Trong ứng dụng thật, hãy đăng ký adapter bằng cấu hình phù hợp hoặc tạo nó tại batch composition root; không gọi method này từ controller.

### 18.10. BlockingBoundaryTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.IOException;
import java.math.BigDecimal;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BlockingBoundaryTest {
    private static final MockWebServer UPSTREAM = startServer();

    private static MockWebServer startServer() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        } catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "catalog.base-url",
            () -> UPSTREAM.url("/").toString()
        );
    }

    @AfterAll
    static void stopServer() throws IOException {
        UPSTREAM.shutdown();
    }

    @Autowired
    ProductService service;

    @Autowired
    WebTestClient webTestClient;

    @Test
    void reactiveServiceCanBeVerifiedWithoutBlock() {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .addHeader("ETag", "\"p-42\"")
            .addHeader("X-Request-Id", "req-42")
            .setBody("""
                {"id":42,"name":"Keyboard","price":79.90}
                """));

        StepVerifier.create(service.getProduct("42"))
            .assertNext(response -> {
                assertEquals(HttpStatus.OK, response.getStatusCode());
                assertEquals("\"p-42\"", response.getHeaders().getETag());
                assertEquals("req-42",
                    response.getHeaders().getFirst("X-Request-Id"));
                assertEquals(
                    new Product(42, "Keyboard", new BigDecimal("79.90")),
                    response.getBody()
                );
            })
            .verifyComplete();
    }

    @Test
    void webFluxControllerReturnsReactiveResponse() {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .addHeader("ETag", "\"p-7\"")
            .setBody("""
                {"id":7,"name":"Mouse","price":25.50}
                """));

        webTestClient.get()
            .uri("/api/products/7")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("ETag", "\"p-7\"")
            .expectBody()
            .json("""
                {"id":7,"name":"Mouse","price":25.50}
                """);
    }

    @Test
    void blockIsUsedOnlyAtTheImperativeTestBoundary() {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .addHeader("X-Request-Id", "batch-9")
            .setBody("""
                {"id":9,"name":"Screen","price":199.90}
                """));

        ProductBatchAdapter adapter = new ProductBatchAdapter(service);

        ResponseEntity<Product> response =
            adapter.fetchForBatch("9");

        assertNotNull(response);
        assertEquals(200, response.getStatusCode().value());
        assertEquals("batch-9",
            response.getHeaders().getFirst("X-Request-Id"));
        assertEquals("Screen", response.getBody().name());
    }
}
~~~

Test đầu dùng StepVerifier để kiểm tra reactive service mà không block. Test thứ hai đi qua WebFlux controller bằng WebTestClient. Test thứ ba gọi adapter từ JUnit test thread để minh họa block ở một ranh giới đồng bộ.

### 18.11. Chạy ứng dụng và test

Tại thư mục dự án:

~~~bash
./gradlew bootRun
~~~

Hoặc:

~~~bash
gradle bootRun
~~~

Khi chạy ứng dụng, cấu hình catalog.base-url phải trỏ tới một upstream đang hoạt động. Ví dụ:

~~~bash
curl -i http://localhost:8080/api/products/42
~~~

Chạy test:

~~~bash
./gradlew test
~~~

MockWebServer cung cấp upstream local cho test. Các test không phụ thuộc Internet hoặc dịch vụ bên ngoài.

Demo minh họa hai cách dùng cùng một service:

- WebFlux controller giữ Mono và để framework subscribe.
- Batch adapter chờ kết quả ở imperative boundary với timeout.

## 19. Checklist quyết định có nên block hay không

Trước khi gọi block(), hãy tự kiểm tra:

1. Thread hiện tại có phải Reactor Netty event loop hoặc thread non-blocking không?
2. Lời gọi có nằm trong controller, WebFilter, handler hoặc callback reactive không?
3. Đây có phải ranh giới đồng bộ được xác định rõ như CLI, batch worker hoặc test không?
4. Có thể return Mono/Flux và để caller compose tiếp không?
5. Có nhiều request độc lập cần ghép bằng zip trước khi chờ không?
6. Publisher có thể empty không; có cần blockOptional không?
7. Có timeout hữu hạn cho caller không?
8. HTTP client/SDK/JDBC đã có connect/read/query timeout riêng chưa?
9. Nếu dùng thư viện blocking trong reactive chain, đã bọc fromCallable và subscribeOn(boundedElastic) chưa?
10. Có vô tình wrap WebClient rồi gọi block bên trong Callable không?
11. Nếu xử lý Flux, nguồn có hữu hạn và kích thước được giới hạn không?
12. Cancellation và cleanup có được truyền về upstream không?
13. Có thể thay API blocking bằng reactive driver/client không?
14. Có test hoặc quan sát để phát hiện blocking trên event loop không?

| Tình huống | Cách làm |
| --- | --- |
| WebFlux controller gọi WebClient | Return Mono/Flux |
| WebFlux controller cần status/header/body | Compose Mono<ResponseEntity<T>> |
| Batch job cần một kết quả | block(Duration) một lần ở worker boundary |
| Mono có thể empty | blockOptional(Duration) |
| Batch cần nhiều API độc lập | Mono.zip rồi block một lần |
| Thư viện cũ blocking trong reactive chain | fromCallable + subscribeOn(boundedElastic) |
| Thư viện blocking trả void | fromRunnable + subscribeOn(boundedElastic) |
| CPU-bound transformation | Dùng parallel khi cần, không block |
| Flux hữu hạn, nhỏ | collectList rồi block ở boundary |
| Flux dài hạn/lớn | Giữ streaming; không aggregate toàn bộ |
| CompletableFuture trong reactive code | Mono.fromFuture |
| Kiểm thử publisher | StepVerifier hoặc WebTestClient |

## 20. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Vì sao không gọi block trong WebFlux controller?

**Đáp án:** Controller thường chạy trên event-loop worker dùng chung. block giữ worker trong lúc chờ, làm trễ request và callback khác.

**Câu 2.** block() có tạo subscription không?

**Đáp án:** Có. Mỗi lần gọi block tạo subscription mới; với publisher lạnh, gọi nhiều lần có thể thực thi request hoặc side effect nhiều lần.

**Câu 3.** block() trả gì khi Mono complete empty?

**Đáp án:** Trả null. Dùng blockOptional để nhận Optional.empty rõ ràng hơn.

**Câu 4.** block(Duration) có làm lời gọi trở thành non-blocking không?

**Đáp án:** Không. Nó chỉ giới hạn thời gian caller chờ; thread vẫn bị chặn trong khoảng đó.

**Câu 5.** Dùng scheduler nào để cô lập một lời gọi JDBC đồng bộ?

**Đáp án:** Bọc lời gọi trong Mono.fromCallable và dùng subscribeOn(Schedulers.boundedElastic()).

**Câu 6.** Vì sao Mono.just(legacyCall()) không an toàn?

**Đáp án:** legacyCall được thực thi ngay khi tạo Mono, trước khi scheduler có thể chuyển source sang worker. Dùng fromCallable.

**Câu 7.** subscribeOn và publishOn khác nhau thế nào?

**Đáp án:** subscribeOn chuyển quá trình subscribe/source execution; publishOn chuyển signal và operator phía downstream từ vị trí được đặt.

**Câu 8.** Đặt subscribeOn(boundedElastic) trước block có bảo vệ event loop gọi block không?

**Đáp án:** Không. block vẫn chặn thread gọi nó. Scheduler chỉ chuyển phần reactive execution được điều khiển bởi operator.

**Câu 9.** Có nên bọc WebClient rồi gọi block bên trong fromCallable không?

**Đáp án:** Không. WebClient vốn non-blocking; hãy return publisher và compose trực tiếp.

**Câu 10.** Nếu có hai WebClient request độc lập trong batch job thì làm gì?

**Đáp án:** Ghép bằng Mono.zip hoặc operator phù hợp, sau đó block một lần ở imperative boundary.

**Câu 11.** block có thay thế connect/read timeout của HTTP client không?

**Đáp án:** Không. block(Duration) giới hạn thời gian chờ của caller; transport vẫn cần timeout riêng.

**Câu 12.** Có thể dùng boundedElastic vô hạn không?

**Đáp án:** Không. Pool và queue có giới hạn; quá nhiều blocking work vẫn gây nghẽn. Hãy giới hạn tải và ưu tiên API non-blocking.

## 21. Ghi nhớ và tài liệu chính thức

- block() chuyển reactive publisher thành lời gọi đồng bộ tại thread hiện tại.
- Ranh giới block phải được xác định bằng execution context: CLI, batch worker hoặc test thread có thể chờ; WebFlux event loop thì không.
- WebFlux sử dụng số lượng nhỏ event-loop workers; một blocking call có thể ảnh hưởng nhiều request.
- block(Duration) giới hạn thời gian chờ, không làm caller non-blocking.
- Mỗi lần block tạo subscription mới; không gọi nhiều lần trên cùng publisher nếu không muốn request/side effect lặp lại.
- blockOptional biểu diễn Mono empty bằng Optional.empty.
- Dùng Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic()) cho API đồng bộ cũ.
- Dùng publishOn để chuyển các bước downstream; dùng subscribeOn để chuyển source subscription/execution.
- Không dùng Mono.just(blockingCall()) và không wrap WebClient rồi block bên trong Callable.
- Không dùng Future.get, join, Thread.sleep hoặc toStream trên event loop.
- Giữ WebClient pipeline reactive; ghép nhiều request rồi chỉ block một lần ở outer imperative boundary nếu cần.
- Cấu hình timeout ở transport và thư viện blocking; không chỉ dựa vào Reactor timeout.
- boundedElastic có giới hạn và cần được giám sát; reactive driver vẫn là lựa chọn tốt hơn cho I/O nếu có.

Tài liệu chính thức:

1. [Spring Framework Reference — WebFlux Concurrency Model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): khác biệt concurrency model giữa MVC và WebFlux, event-loop workers và cảnh báo blocking I/O.
2. [Spring Framework Reference — WebClient Synchronous Use](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html): dùng WebClient theo synchronous style bằng block ở cuối pipeline và ghép nhiều request trước khi chờ.
3. [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient là HTTP client reactive, non-blocking và hỗ trợ streaming.
4. [Project Reactor Reference — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): subscribeOn, publishOn, boundedElastic, parallel và execution context.
5. [Project Reactor Reference — FAQ: Wrap a Synchronous, Blocking Call](https://projectreactor.io/docs/core/release/reference/faq.html): pattern fromCallable kết hợp subscribeOn(boundedElastic).
6. [Project Reactor Javadoc — Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): block, block(Duration), blockOptional và semantics subscription.
7. [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier và kiểm thử publisher.
8. [BlockHound](https://github.com/reactor/BlockHound): công cụ phát hiện blocking call trên non-blocking thread trong quá trình phát triển/kiểm thử.

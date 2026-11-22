# Phối hợp nhiều lời gọi độc lập và giới hạn số yêu cầu đồng thời với Spring WebClient

## 1. Bài toán fan-out khi gọi nhiều API

Một endpoint tổng hợp thường cần dữ liệu từ nhiều dịch vụ:

- Thông tin sản phẩm từ Catalog API.
- Số lượng tồn kho từ Inventory API.
- Giá hiện tại từ Pricing API.
- Đánh giá hoặc khuyến nghị từ một dịch vụ khác.

Nếu các lời gọi độc lập, việc chờ từng request xong rồi mới gửi request tiếp theo làm tăng latency tổng. Với ba request có thời gian phản hồi lần lượt 300 ms, 400 ms và 250 ms, cách tuần tự có thể mất khoảng 950 ms cộng overhead. Nếu gửi đồng thời và chờ tất cả, thời gian gần với request chậm nhất, khoảng 400 ms cộng overhead.

Tuy nhiên, gửi hàng trăm request cùng lúc cũng có thể làm quá tải dịch vụ phía sau, cạn connection pool, tăng hàng đợi và tạo retry storm. Vì vậy cần hai quyết định riêng:

1. **Phối hợp kết quả:** những lời gọi nào độc lập, cần đợi tất cả hay chỉ cần một kết quả?
2. **Giới hạn tải:** tối đa bao nhiêu lời gọi được phép đang chạy đồng thời trong một luồng xử lý?

Spring WebClient kết hợp với Reactor cung cấp các operator như Mono.zip, Flux.flatMap, flatMapSequential và concatMap để giải quyết hai vấn đề này.

## 2. WebClient và Publisher có tính lazy

WebClient trả về Mono hoặc Flux. Khi tạo publisher, request thường chưa được gửi ngay. Publisher mô tả công việc cần thực hiện; request bắt đầu khi có subscription.

~~~java
Mono<Product> product = webClient.get()
        .uri("/products/{id}", "p-1")
        .retrieve()
        .bodyToMono(Product.class);
~~~

Đoạn code trên tạo một Mono mô tả request. Khi một subscriber subscribe vào Mono, WebClient mới thực hiện HTTP exchange.

Điều này cho phép ghép nhiều request thành một pipeline trước khi subscribe:

~~~java
Mono<Product> product = fetchProduct(id);
Mono<Inventory> inventory = fetchInventory(id);
Mono<Price> price = fetchPrice(id);

return Mono.zip(product, inventory, price, Dashboard::new);
~~~

Mono.zip subscribe vào các nguồn khi pipeline được subscribe. Các request HTTP độc lập có thể cùng đang chờ I/O. Không cần tạo một thread riêng cho mỗi request; Reactor Netty xử lý I/O bất đồng bộ.

Không gọi subscribe() bên trong service để tự khởi chạy từng request. Cũng không gọi block() sau từng lời gọi. Hãy trả Mono/Flux cho controller hoặc tầng gọi để toàn bộ lifecycle, lỗi và cancellation được quản lý trong một pipeline.

## 3. Mono.zip: phối hợp các lời gọi độc lập trả một kết quả

### 3.1. Khi nào dùng zip?

Dùng Mono.zip khi cần giá trị từ nhiều nguồn độc lập trước khi tạo kết quả tổng hợp.

~~~java
Mono<Dashboard> dashboard(String id) {
    Mono<Product> product = fetchProduct(id);
    Mono<Inventory> inventory = fetchInventory(id);
    Mono<Price> price = fetchPrice(id);

    return Mono.zip(product, inventory, price, Dashboard::new);
}
~~~

Dashboard chỉ được tạo khi cả ba Mono phát giá trị. Hàm Dashboard::new nhận kết quả theo đúng thứ tự nguồn đã truyền vào zip.

Nếu các request mất thời gian lần lượt 300 ms, 400 ms và 250 ms, tổng thời gian chờ gần với request chậm nhất thay vì cộng cả ba thời gian. Con số thực tế còn phụ thuộc network, connection pool, DNS, server và overhead decode.

### 3.2. zip không biến lời gọi phụ thuộc thành độc lập

Các nguồn chỉ có thể chạy song song khi chúng không cần kết quả của nhau.

Ví dụ đúng: lấy product, inventory và price theo cùng một product ID; ba API đều có thể được gọi ngay.

Ví dụ phụ thuộc: phải lấy order trước để biết customerId, rồi mới lấy customer. Dùng flatMap:

~~~java
Mono<OrderSummary> summary(String orderId) {
    return fetchOrder(orderId)
            .flatMap(order ->
                    fetchCustomer(order.customerId())
                            .map(customer -> new OrderSummary(order, customer))
            );
}
~~~

Không thể gọi fetchCustomer trước khi biết customerId. Dùng zip trong trường hợp này không tạo ra tính song song có ích.

### 3.3. zip và Mono rỗng

Mono có thể hoàn tất mà không phát giá trị. Mono.zip cần mỗi nguồn phát một giá trị để gọi hàm kết hợp. Nếu một nguồn hoàn tất rỗng, zip hoàn tất rỗng và hủy các nguồn còn lại.

Nếu một nguồn là dữ liệu tùy chọn, chuyển empty thành một giá trị đại diện trước khi zip:

~~~java
Mono<Optional<Recommendation>> recommendation =
        fetchRecommendation(id)
                .map(Optional::of)
                .defaultIfEmpty(Optional.empty());

return Mono.zip(
        fetchProduct(id),
        recommendation,
        ProductPage::new
);
~~~

Cách này phân biệt rõ trường hợp không có recommendation với trường hợp request bị lỗi.

### 3.4. zip và lỗi

Mặc định, nếu một nguồn phát lỗi, Mono.zip phát lỗi đó và hủy các nguồn còn lại. Đây là hành vi fail-fast phù hợp khi kết quả tổng hợp không thể hoàn thành nếu thiếu một thành phần bắt buộc.

Nếu muốn chờ các nguồn còn lại hoàn tất trước khi phát lỗi, có thể dùng Mono.zipDelayError:

~~~java
return Mono.zipDelayError(
        fetchProduct(id),
        fetchInventory(id),
        fetchPrice(id),
        Dashboard::new
);
~~~

zipDelayError trì hoãn lỗi cho tới khi các nguồn còn lại có cơ hội hoàn tất. Nếu nhiều nguồn lỗi, các exception có thể được kết hợp dưới dạng suppressed exceptions. Nếu một nguồn hoàn tất rỗng, kết quả cuối cùng vẫn có thể là Mono rỗng sau khi các nguồn khác hoàn tất.

Không dùng zipDelayError chỉ để che lỗi. Chọn fail-fast hay delay-error dựa trên việc ứng dụng có cần thu thập tất cả kết quả/lỗi hay không.

## 4. Mono.when: chờ nhiều tác vụ không cần giá trị

Mono.zip phù hợp khi cần kết hợp các giá trị. Nếu các publisher chỉ biểu diễn thao tác hoàn tất, ví dụ ghi audit, cập nhật metric hoặc phát sự kiện, chúng thường có kiểu Mono<Void>.

Mono<Void> hoàn tất mà không phát giá trị. Vì vậy, không dùng zip để chờ nhiều Mono<Void>; zip sẽ không có giá trị để gọi combinator.

Dùng Mono.when:

~~~java
Mono<Void> saveSideEffects(Event event) {
    return Mono.when(
            writeAudit(event),
            updateCounter(event),
            publishNotification(event)
    );
}
~~~

Mono.when hoàn tất khi các tác vụ hoàn tất. Nếu cần trả một kết quả sau các side effect:

~~~java
return Mono.when(writeAudit(event), publishNotification(event))
        .thenReturn(new Accepted(event.id()));
~~~

Mono.when là công cụ phối hợp tín hiệu hoàn tất; nó không thu thập kết quả từ các nguồn. Có thể dùng Mono.whenDelayError khi muốn trì hoãn lỗi để các tác vụ còn lại có cơ hội kết thúc.

## 5. Flux.flatMap: giới hạn số lời gọi đang chạy đồng thời

### 5.1. Bài toán danh sách nhiều ID

Giả sử cần gọi Catalog API cho 500 product ID. Đoạn sau tạo một publisher cho mỗi ID và cho phép tất cả inner publisher được subscribe theo khả năng điều phối của operator:

~~~java
Flux<Product> products = Flux.fromIterable(ids)
        .flatMap(this::fetchProduct);
~~~

Với danh sách lớn, fan-out không giới hạn có thể tạo quá nhiều request đang chờ, tăng áp lực lên connection pool và upstream. Hãy đặt maxConcurrency:

~~~java
Flux<Product> products = Flux.fromIterable(ids)
        .flatMap(this::fetchProduct, 8);
~~~

Con số 8 là số inner Publisher tối đa được subscribe và merge đồng thời trong subscription này. Khi một request hoàn tất, operator có thể subscribe request tiếp theo từ nguồn.

### 5.2. Cú pháp có cả concurrency và prefetch

~~~java
Flux<Product> products = Flux.fromIterable(ids)
        .flatMap(this::fetchProduct, 8, 1);
~~~

Hai tham số có ý nghĩa khác nhau:

| Tham số | Ý nghĩa |
| --- | --- |
| maxConcurrency = 8 | Tối đa 8 inner Publisher đang được xử lý đồng thời |
| prefetch = 1 | Số phần tử được yêu cầu trước từ mỗi inner Publisher |

Với fetchProduct trả Mono<Product>, mỗi inner publisher chỉ phát tối đa một phần tử, nên prefetch 1 là lựa chọn dễ hiểu. Với inner Flux phát nhiều phần tử, prefetch ảnh hưởng số phần tử được yêu cầu trước từ mỗi inner publisher và lượng dữ liệu có thể được giữ trong hàng đợi.

**prefetch không phải số request đồng thời.** Tham số điều khiển số inner Publisher đang hoạt động là maxConcurrency.

### 5.3. flatMap không bảo toàn thứ tự đầu vào

flatMap merge kết quả khi các inner publisher phát dữ liệu. Request nào hoàn tất trước có thể phát kết quả trước, dù ID của nó nằm sau trong danh sách.

Ví dụ đầu vào:

~~~text
p-1, p-2, p-3
~~~

Thời gian phản hồi:

~~~text
p-1: 500 ms
p-2: 100 ms
p-3: 250 ms
~~~

Kết quả có thể phát theo thứ tự:

~~~text
p-2, p-3, p-1
~~~

Đây là hành vi mong muốn khi ưu tiên throughput và mỗi kết quả độc lập. Nếu cần giữ thứ tự đầu vào, dùng flatMapSequential.

## 6. Chọn flatMap, flatMapSequential hay concatMap

| Operator | Số inner publisher hoạt động | Thứ tự output | Khi phù hợp |
| --- | --- | --- | --- |
| flatMap(mapper, concurrency) | Nhiều, tối đa concurrency | Theo thời điểm hoàn tất | Ưu tiên throughput; kết quả độc lập |
| flatMapSequential(mapper, concurrency) | Nhiều, tối đa concurrency | Giữ thứ tự nguồn | Cần song song nhưng output phải đúng thứ tự |
| concatMap(mapper) | Một lần một inner | Giữ thứ tự nguồn | Tác vụ phụ thuộc thứ tự hoặc cần tuần tự |

### 6.1. flatMapSequential

~~~java
Flux<Product> ordered = Flux.fromIterable(ids)
        .flatMapSequential(this::fetchProduct, 8, 1);
~~~

flatMapSequential subscribe vào các inner publisher một cách eager như flatMap, nhưng giữ output theo thứ tự nguồn. Nếu request đầu tiên chậm còn request thứ hai hoàn tất sớm, kết quả thứ hai phải chờ trong hàng đợi cho tới khi kết quả đầu tiên được phát.

Do đó, flatMapSequential có thể cần bộ nhớ để giữ các kết quả đã hoàn tất nhưng chưa đến lượt phát. Chọn nó khi thứ tự thực sự quan trọng.

### 6.2. concatMap

~~~java
Flux<Product> sequential = Flux.fromIterable(ids)
        .concatMap(this::fetchProduct);
~~~

concatMap chờ inner publisher hiện tại hoàn tất rồi mới subscribe inner tiếp theo. Nó bảo toàn thứ tự và chỉ có một request được thực hiện tại một thời điểm trong pipeline đó.

Dùng khi API có quota rất thấp, thao tác có thứ tự bắt buộc hoặc request sau phụ thuộc side effect của request trước. Nếu các request độc lập và upstream chịu được concurrency, concatMap có thể làm giảm throughput không cần thiết.

### 6.3. Ví dụ minh họa thời gian

~~~text
flatMap, concurrency = 3
p-1: [------response------]
p-2: [--response--]
p-3: [----response----]
output: p-2, p-3, p-1

flatMapSequential, concurrency = 3
p-1: [------response------]
p-2: [--response--] (chờ phát)
p-3: [----response--] (chờ phát)
output: p-1, p-2, p-3

concatMap
p-1: [------response------]
p-2:                      [--response--]
p-3:                                    [----response----]
output: p-1, p-2, p-3
~~~

## 7. Giới hạn concurrency theo từng subscription

maxConcurrency trong flatMap áp dụng cho một subscription của pipeline.

Ví dụ mỗi request tới endpoint local gọi:

~~~java
client.findMany(ids, 4)
~~~

Mỗi subscription có thể chạy tối đa 4 inner request. Nếu có 20 request local đồng thời, mỗi request đều có pipeline riêng, tổng số request tới upstream có thể lớn hơn 4 rất nhiều.

Vì vậy, phân biệt:

- **Per-subscription limit:** giới hạn trong một lần xử lý danh sách; dùng flatMap maxConcurrency.
- **Global bulkhead:** giới hạn tổng lời gọi đang chạy qua nhiều request local; dùng cơ chế chia sẻ như semaphore/bulkhead hoặc giới hạn ở tầng gateway.
- **Connection pool limit:** giới hạn tài nguyên kết nối của HTTP client; các request vượt số connection có thể phải chờ acquire. Đây là giới hạn transport, không thay thế quota nghiệp vụ.
- **Rate limit:** giới hạn số request trong một khoảng thời gian, ví dụ 50 request/giây. Nó khác giới hạn số request đang chạy đồng thời.

Nếu mỗi lời gọi trung bình mất 500 ms và hệ thống cần xử lý khoảng 12 request/giây, định luật Little cho ước lượng ban đầu khoảng 6 request đang in-flight. Đây chỉ là điểm xuất phát; hãy đo p95/p99 latency, quota upstream, connection pool và tải thực tế trước khi chọn giới hạn.

Không đặt concurrency thật cao chỉ để làm đầy connection pool. Tải quá lớn có thể làm upstream chậm hơn, khiến nhiều request cùng timeout rồi retry, tạo thành retry storm.

## 8. Xử lý lỗi trong fan-out

### 8.1. Lỗi mặc định của flatMap

Mặc định, khi một inner publisher phát lỗi, flatMap truyền lỗi xuống downstream và hủy các inner publisher còn lại. Đây là fail-fast.

Hành vi này phù hợp khi toàn bộ batch chỉ có ý nghĩa nếu mọi item thành công. Nếu một item lỗi nhưng các item khác vẫn cần kết quả, hãy phục hồi lỗi bên trong mapper.

### 8.2. Phục hồi lỗi theo từng item

~~~java
Flux<LookupResult> results = Flux.fromIterable(ids)
        .flatMap(id ->
                fetchProduct(id)
                        .map(LookupResult::success)
                        .onErrorResume(error ->
                                Mono.just(LookupResult.failure(
                                        id,
                                        classify(error)
                                ))
                        ),
                8,
                1
        );
~~~

onErrorResume nằm bên trong mapper nên lỗi của một item được chuyển thành LookupResult.failure. Các item còn lại tiếp tục chạy.

Nếu đặt onErrorResume bên ngoài flatMap, lỗi đầu tiên có thể kết thúc batch trước khi các item còn lại hoàn tất; fallback lúc đó thường chỉ xử lý lỗi của toàn bộ pipeline.

Không đưa raw exception message, URL nội bộ, token hoặc body nhạy cảm vào kết quả trả client. Hãy chuyển lỗi thành mã trạng thái nghiệp vụ đã được lọc.

### 8.3. Delay error

Nếu muốn cho các inner publisher còn lại tiếp tục rồi mới phát lỗi, Reactor có các biến thể delay-error như flatMapDelayError. Chúng hữu ích khi cần thu thập nhiều lỗi trong một batch.

Delay error không đồng nghĩa với bỏ qua lỗi. Kết quả cuối cùng vẫn có thể là error sau khi backlog hoàn tất. Nếu muốn batch luôn trả một kết quả cho từng ID, phục hồi lỗi theo từng item thường rõ ràng hơn.

### 8.4. Không retry toàn bộ batch nếu chỉ một item lỗi

Sai lầm phổ biến là đặt retry sau pipeline fan-out:

~~~java
Flux.fromIterable(ids)
        .flatMap(this::fetchProduct, 8)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200)));
~~~

Khi batch lỗi, retry ở ngoài có thể subscribe lại nguồn và gọi lại cả các request đã thành công trước đó. Điều này tạo tải lặp không cần thiết.

Đặt timeout và retry trong publisher của từng request nếu chính sách retry là theo item:

~~~java
Mono<Product> fetchProduct(String id) {
    return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class)
            .timeout(Duration.ofSeconds(2))
            .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                    .filter(this::isRetryable));
}
~~~

Ví dụ này cho phép tối đa hai lần retry sau lần thử đầu. Chỉ retry lỗi đã xác định là tạm thời; không retry mặc định mọi 4xx. Với POST hoặc thao tác có side effect, chỉ retry khi có idempotency key hoặc cơ chế chống tạo dữ liệu trùng.

## 9. Timeout, cancellation và backpressure

### 9.1. Timeout cho từng request và toàn bộ batch

Đặt timeout trong fetchProduct để giới hạn thời gian của từng HTTP request:

~~~java
Mono<Product> fetchProduct(String id) {
    return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class)
            .timeout(Duration.ofSeconds(2));
}
~~~

Đặt timeout sau flatMap để giới hạn toàn bộ batch:

~~~java
Flux<Product> products = Flux.fromIterable(ids)
        .flatMap(this::fetchProduct, 8, 1)
        .timeout(Duration.ofSeconds(10));
~~~

Hai giới hạn phục vụ hai mục tiêu khác nhau. Nếu một request chậm 5 giây nhưng các request khác nhanh, per-request timeout và batch timeout sẽ có hành vi khác nhau.

### 9.2. Cancellation

Khi client local hủy subscription, cancellation truyền xuống pipeline. Các inner publisher đang chạy được cancel theo contract của Reactor và WebClient connector. Điều này giúp ngừng công việc không còn người nhận kết quả.

Không gọi subscribe() lồng nhau vì publisher độc lập sẽ không còn được quản lý bởi cancellation của pipeline chính.

### 9.3. Backpressure

Backpressure cho phép downstream kiểm soát lượng phần tử được yêu cầu từ upstream. flatMap kết hợp demand với concurrency và prefetch để điều tiết inner publisher.

Tuy nhiên, backpressure không tự làm một danh sách Java đã được nạp sẵn trở nên nhỏ. Nếu ứng dụng tải một triệu ID vào List rồi mới gọi Flux.fromIterable, List đó vẫn chiếm bộ nhớ. Với dữ liệu lớn, đọc ID theo page hoặc stream từ nguồn dữ liệu thay vì materialize toàn bộ.

Không gọi collectList() cho response lớn nếu không thực sự cần danh sách trong memory. Hãy xử lý từng phần tử và chỉ gom kết quả khi số lượng đã được giới hạn.

## 10. Concurrency không phải rate limiting

Hai giới hạn thường bị nhầm:

| Loại giới hạn | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Concurrency | Có bao nhiêu request đang chạy cùng lúc? | Tối đa 8 request in-flight |
| Rate limit | Có bao nhiêu request được bắt đầu trong một khoảng thời gian? | Tối đa 50 request mỗi giây |

Nếu mỗi request mất 10 ms, concurrency 8 vẫn có thể tạo hàng trăm request/giây. Ngược lại, rate limit 50 request/giây không đảm bảo chỉ có 8 request đang chạy nếu latency tăng cao.

Nếu upstream áp quota theo giây, cần rate limiter riêng. Nếu upstream giới hạn số tác vụ đang xử lý, cần bulkhead/concurrency limit. Một hệ thống có thể cần cả hai.

## 11. WebClient I/O không cần parallel() để chạy đồng thời

WebClient là non-blocking HTTP client. Với các request I/O độc lập, flatMap hoặc Mono.zip đã cho phép các request đang chờ I/O tiến triển đồng thời.

Không cần dùng:

~~~java
Flux.fromIterable(ids)
        .parallel()
        .runOn(Schedulers.parallel())
        .flatMap(this::fetchProduct);
~~~

parallel() chia sequence thành rails cho xử lý song song theo scheduler; nó không phải công cụ giới hạn số HTTP request. Dùng nó một cách máy móc có thể làm code phức tạp mà không cải thiện I/O.

Nếu cần gọi thư viện blocking cũ, bọc thao tác blocking và chuyển nó sang boundedElastic:

~~~java
Mono<Result> legacyCall(String id) {
    return Mono.fromCallable(() -> blockingClient.fetch(id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Sau đó vẫn có thể dùng flatMap với maxConcurrency để giới hạn số tác vụ blocking đang chạy.

## 12. Ví dụ Java 17+ chạy được: Dashboard và batch lookup

Ví dụ dùng Spring Boot 3.5.5, Java 17+ và WebFlux. Ứng dụng có hai cách phối hợp:

- dashboard(id): gọi Product, Inventory và Price độc lập rồi kết hợp bằng Mono.zip.
- findMany(ids, maxConcurrent): gọi Product API cho danh sách ID với giới hạn concurrency.
- findManyOrdered(...): giữ thứ tự ID bằng flatMapSequential.
- findManySequential(...): gọi lần lượt bằng concatMap.

### 12.1. Cấu trúc dự án

~~~text
webclient-fanout/
├── pom.xml
└── src/
    ├── main/java/example/fanout/
    │   ├── DemoApplication.java
    │   ├── CatalogProperties.java
    │   ├── CatalogClientConfiguration.java
    │   ├── CatalogClient.java
    │   ├── CatalogController.java
    │   ├── Product.java
    │   ├── Inventory.java
    │   ├── Price.java
    │   └── Dashboard.java
    └── test/java/example/fanout/
        └── CatalogClientTest.java
~~~

### 12.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webclient-fanout</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 12.3. Product.java

~~~java
package example.fanout;

public record Product(String id, String name) {
}
~~~

### 12.4. Inventory.java

~~~java
package example.fanout;

public record Inventory(int available) {
}
~~~

### 12.5. Price.java

~~~java
package example.fanout;

import java.math.BigDecimal;

public record Price(BigDecimal amount, String currency) {
}
~~~

### 12.6. Dashboard.java

~~~java
package example.fanout;

public record Dashboard(
        Product product,
        Inventory inventory,
        Price price
) {
}
~~~

### 12.7. CatalogProperties.java

~~~java
package example.fanout;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(String baseUrl) {
}
~~~

### 12.8. CatalogClientConfiguration.java

~~~java
package example.fanout;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogClientConfiguration {

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            CatalogProperties properties
    ) {
        return builder.baseUrl(properties.baseUrl()).build();
    }

    @Bean
    CatalogClient catalogClient(WebClient catalogWebClient) {
        return new CatalogClient(catalogWebClient);
    }
}
~~~

### 12.9. CatalogClient.java

~~~java
package example.fanout;

import java.time.Duration;
import java.util.function.Function;

import org.reactivestreams.Publisher;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<Dashboard> dashboard(String id) {
        Mono<Product> product = get("/products/{id}", id, Product.class);
        Mono<Inventory> inventory = get(
                "/inventory/{id}", id, Inventory.class);
        Mono<Price> price = get("/prices/{id}", id, Price.class);

        return Mono.zip(product, inventory, price, Dashboard::new)
                .timeout(Duration.ofSeconds(3));
    }

    public Mono<Product> findProduct(String id) {
        return get("/products/{id}", id, Product.class)
                .retryWhen(Retry.backoff(
                                2,
                                Duration.ofMillis(100))
                        .filter(this::isRetryable));
    }

    public Flux<Product> findMany(
            Iterable<String> ids,
            int maxConcurrent
    ) {
        return boundedMap(ids, this::findProduct, maxConcurrent);
    }

    public Flux<Product> findManyOrdered(
            Iterable<String> ids,
            int maxConcurrent
    ) {
        requirePositive(maxConcurrent);

        return Flux.fromIterable(ids)
                .flatMapSequential(this::findProduct, maxConcurrent, 1);
    }

    public Flux<Product> findManySequential(Iterable<String> ids) {
        return Flux.fromIterable(ids)
                .concatMap(this::findProduct, 1);
    }

    private <T> Mono<T> get(String path, String id, Class<T> type) {
        return webClient.get()
                .uri(path, id)
                .retrieve()
                .bodyToMono(type)
                .timeout(Duration.ofSeconds(2));
    }

    private boolean isRetryable(Throwable error) {
        return error instanceof WebClientResponseException response
                && response.getStatusCode().is5xxServerError();
    }

    static <I, O> Flux<O> boundedMap(
            Iterable<I> inputs,
            Function<? super I, ? extends Publisher<? extends O>> mapper,
            int maxConcurrent
    ) {
        requirePositive(maxConcurrent);

        return Flux.fromIterable(inputs)
                .flatMap(mapper, maxConcurrent, 1);
    }

    private static void requirePositive(int maxConcurrent) {
        if (maxConcurrent < 1) {
            throw new IllegalArgumentException(
                    "maxConcurrent must be greater than zero");
        }
    }
}
~~~

Phân tích:

- dashboard tạo ba Mono độc lập. Khi Mono.zip được subscribe, cả ba request có thể chạy đồng thời.
- Dashboard::new chỉ được gọi sau khi cả Product, Inventory và Price có giá trị.
- findProduct áp dụng timeout cho từng request và retry tối đa hai lần đối với lỗi HTTP 5xx.
- findMany dùng flatMap với maxConcurrent để giới hạn số request đang in-flight trong subscription hiện tại.
- findManyOrdered vẫn cho phép request chạy đồng thời nhưng phát kết quả theo thứ tự ID đầu vào.
- findManySequential chỉ chạy một request tại một thời điểm.
- boundedMap kiểm tra concurrency phải lớn hơn 0; prefetch bằng 1 phù hợp với inner publisher trả Mono.

Retry trong ví dụ chỉ áp dụng lỗi 5xx. Lỗi 4xx, timeout và lỗi kết nối không tự động được retry. Đây là chính sách minh họa; production cần xác định rõ lỗi tạm thời và idempotency của từng API.

### 12.10. CatalogController.java

~~~java
package example.fanout;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/catalog")
public class CatalogController {

    private final CatalogClient client;

    public CatalogController(CatalogClient client) {
        this.client = client;
    }

    @GetMapping("/dashboard/{id}")
    public Mono<Dashboard> dashboard(@PathVariable String id) {
        return client.dashboard(id);
    }

    @GetMapping("/products")
    public Flux<Product> products(
            @RequestParam("ids") List<String> ids,
            @RequestParam(defaultValue = "4") int maxConcurrent
    ) {
        if (maxConcurrent < 1 || maxConcurrent > 16) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "maxConcurrent must be between 1 and 16"
            );
        }

        return client.findMany(ids, maxConcurrent);
    }
}
~~~

Giới hạn 1 đến 16 là chính sách của API demo. Ứng dụng thực tế nên chọn giá trị tối đa dựa trên quota upstream và năng lực của hệ thống.

### 12.11. DemoApplication.java

~~~java
package example.fanout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 12.12. application.yml

~~~yaml
catalog:
  base-url: http://localhost:8081
~~~

Trong môi trường thật, đưa URL upstream vào cấu hình triển khai. Không hardcode credential hoặc token vào source code.

## 13. Kiểm thử bằng MockWebServer và StepVerifier

MockWebServer cho phép kiểm thử WebClient qua HTTP thật ở local. Có thể cấu hình response theo path và kiểm tra cách pipeline phối hợp các request.

Tệp CatalogClientTest.java:

~~~java
package example.fanout;

import java.io.IOException;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogClientTest {

    private MockWebServer server;
    private CatalogClient client;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        WebClient webClient = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .build();

        client = new CatalogClient(webClient);
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void combinesIndependentRequestsIntoDashboard() {
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                return switch (request.getPath()) {
                    case "/products/p-1" -> json(
                            "{\"id\":\"p-1\",\"name\":\"Keyboard\"}");
                    case "/inventory/p-1" -> json(
                            "{\"available\":8}");
                    case "/prices/p-1" -> json(
                            "{\"amount\":49.90,\"currency\":\"USD\"}");
                    default -> new MockResponse().setResponseCode(404);
                };
            }
        });

        StepVerifier.create(client.dashboard("p-1"))
                .assertNext(dashboard -> {
                    assertThat(dashboard.product().name())
                            .isEqualTo("Keyboard");
                    assertThat(dashboard.inventory().available())
                            .isEqualTo(8);
                    assertThat(dashboard.price().currency())
                            .isEqualTo("USD");
                    assertThat(dashboard.price().amount())
                            .isEqualByComparingTo("49.90");
                })
                .verifyComplete();
    }

    @Test
    void boundedMapNeverExceedsConfiguredConcurrency() {
        AtomicInteger inFlight = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();

        List<Integer> ids = IntStream.range(0, 12)
                .boxed()
                .toList();

        Flux<Integer> result = CatalogClient.boundedMap(
                ids,
                id -> Mono.delay(Duration.ofMillis(50))
                        .doOnSubscribe(subscription -> {
                            int current = inFlight.incrementAndGet();
                            maximum.accumulateAndGet(current, Math::max);
                        })
                        .doFinally(signal -> inFlight.decrementAndGet())
                        .thenReturn(id),
                3
        );

        StepVerifier.create(result)
                .expectNextCount(12)
                .verifyComplete();

        assertThat(maximum.get()).isEqualTo(3);
        assertThat(inFlight.get()).isZero();
    }

    private MockResponse json(String body) {
        return new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody(body);
    }
}
~~~

Test đầu tiên xác nhận ba endpoint độc lập được kết hợp thành một Dashboard đúng dữ liệu. Test thứ hai tạo 12 publisher bất đồng bộ và đo số publisher đang hoạt động; giá trị lớn nhất phải bằng 3 khi maxConcurrent là 3.

StepVerifier xác nhận các tín hiệu của Mono/Flux mà không cần block trong code ứng dụng. Test concurrency dùng Mono.delay để mô phỏng I/O bất đồng bộ và kiểm tra chính helper mà findMany sử dụng.

### 13.1. Chạy test

Tại thư mục có pom.xml:

~~~bash
mvn test
~~~

### 13.2. Chạy ứng dụng

~~~bash
mvn spring-boot:run
~~~

Giả sử Catalog API, Inventory API và Pricing API đang chạy tại localhost:8081:

~~~bash
curl http://localhost:8080/catalog/dashboard/p-1
curl "http://localhost:8080/catalog/products?ids=p-1&ids=p-2&ids=p-3&maxConcurrent=2"
~~~

Dashboard gọi ba API độc lập rồi trả một đối tượng tổng hợp. Endpoint products gọi nhiều product ID với tối đa hai inner request đồng thời trong subscription đó.

## 14. Cấu hình connection pool và giới hạn transport

WebClient thường dùng Reactor Netty làm HTTP connector trong ứng dụng Spring Boot WebFlux. Connection pool có thể giới hạn số kết nối và số request đang chờ lấy connection.

Ví dụ cấu hình minh họa:

~~~java
ConnectionProvider provider = ConnectionProvider.builder("catalog")
        .maxConnections(32)
        .pendingAcquireMaxCount(64)
        .build();

HttpClient httpClient = HttpClient.create(provider);

WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .baseUrl("http://localhost:8081")
        .build();
~~~

Cần dependency Reactor Netty HTTP và các import tương ứng:

~~~java
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;
~~~

maxConnections giới hạn connection trong pool; pendingAcquireMaxCount giới hạn số yêu cầu đang chờ acquire connection. Đây là kiểm soát tài nguyên transport. Nó không thay thế giới hạn fan-out theo nghiệp vụ.

Với HTTP/2, một connection có thể multiplex nhiều stream, vì vậy không suy luận đơn giản rằng một connection tương đương một request. Hãy kết hợp giới hạn ứng dụng, connection pool và quota của upstream.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi block() sau từng request | Các request chạy tuần tự và chặn thread | Ghép Mono bằng zip hoặc flatMap |
| Gọi subscribe() riêng cho từng request | Mất quản lý lỗi và cancellation chung | Trả một Mono/Flux duy nhất |
| Dùng zip cho các request phụ thuộc nhau | Không thể tạo request sau khi chưa có dữ liệu đầu vào | Dùng flatMap cho bước phụ thuộc |
| Dùng zip với Mono<Void> | Zip không nhận giá trị để kết hợp | Dùng Mono.when |
| Quên xử lý Mono rỗng trong zip | Toàn bộ zip có thể hoàn tất rỗng | defaultIfEmpty hoặc switchIfEmpty |
| Dùng flatMap không giới hạn với danh sách lớn | Quá nhiều request đồng thời | Đặt maxConcurrency |
| Nhầm prefetch với concurrency | Giới hạn tải không đúng kỳ vọng | Điều chỉnh tham số maxConcurrency |
| Cần giữ thứ tự nhưng dùng flatMap | Kết quả có thể phát theo thứ tự hoàn tất | Dùng flatMapSequential |
| Dùng concatMap cho mọi trường hợp | Chỉ có một request chạy mỗi lần | Dùng flatMap khi có thể chạy độc lập |
| Đặt onErrorResume ngoài cả batch | Một lỗi có thể làm mất kết quả của các item khác | Phục hồi lỗi bên trong mapper |
| Retry toàn bộ fan-out | Request đã thành công có thể bị gọi lại | Retry từng inner publisher |
| Retry mọi 4xx/5xx | Lặp request không thể khắc phục hoặc tạo retry storm | Chỉ retry lỗi tạm thời và có giới hạn |
| Nghĩ concurrency per subscription là global | Nhiều request local có thể vượt tổng quota | Dùng bulkhead hoặc limiter dùng chung |
| Nhầm concurrency với rate limit | Có thể vượt quota request/giây | Dùng rate limiter riêng |
| collectList() cho dữ liệu lớn | Giữ toàn bộ kết quả trong heap | Xử lý streaming hoặc phân trang |
| Dùng parallel() để tăng HTTP I/O | Thêm scheduler không cần thiết | Dùng flatMap với concurrency phù hợp |
| Không đặt timeout | Một inner request có thể giữ slot quá lâu | Đặt timeout theo request và batch |

## 16. Checklist chọn cách phối hợp

Trước khi triển khai fan-out, hãy trả lời:

1. Các request có thật sự độc lập hay request sau cần dữ liệu request trước?
2. Cần một giá trị tổng hợp, nhiều giá trị hay chỉ chờ các side effect hoàn tất?
3. Nếu một nguồn rỗng, kết quả tổng hợp phải như thế nào?
4. Nếu một nguồn lỗi, fail-fast hay đợi các nguồn khác hoàn tất?
5. Có cần bảo toàn thứ tự input không?
6. Một subscription được phép có bao nhiêu request đang chạy?
7. Nhiều request local đồng thời có cần global bulkhead không?
8. Upstream giới hạn concurrency, request/giây hay cả hai?
9. Timeout và retry áp dụng cho từng request hay cả batch?
10. Một item lỗi có làm hỏng toàn bộ batch không?
11. Cancellation có truyền tới các request đang chạy không?
12. Danh sách đầu vào và kết quả có đủ nhỏ để giữ trong memory không?
13. Connection pool và pending acquire queue có phù hợp với concurrency không?
14. Có test đo số inner publisher hoạt động tối đa và test lỗi/cancel không?

## 17. Ghi nhớ

- Mono.zip phối hợp nhiều Mono độc lập và tạo một kết quả khi tất cả nguồn phát giá trị.
- Mono.zip fail-fast; nguồn rỗng hoặc lỗi có thể làm hủy các nguồn còn lại.
- Dùng defaultIfEmpty cho nguồn tùy chọn; dùng zipDelayError khi thật sự cần trì hoãn lỗi.
- Mono.when phù hợp để chờ nhiều tác vụ Mono<Void>.
- Flux.flatMap(mapper, maxConcurrency, prefetch) giới hạn số inner publisher đang hoạt động trong một subscription.
- maxConcurrency giới hạn số request đồng thời; prefetch điều khiển demand phần tử từ mỗi inner publisher.
- flatMap không bảo toàn thứ tự; flatMapSequential chạy đồng thời nhưng giữ thứ tự; concatMap chạy tuần tự.
- Concurrency trong một subscription không phải global concurrency giữa nhiều request local.
- Rate limit, bulkhead và connection pool giải quyết các lớp giới hạn khác nhau.
- Đặt timeout và retry ở từng request; không retry lại cả batch nếu chỉ một item lỗi.
- Phục hồi lỗi bên trong mapper nếu muốn các item khác tiếp tục.
- WebClient I/O không cần parallel() hoặc block(); hãy compose Mono/Flux và giữ backpressure.
- Kiểm thử fan-out bằng MockWebServer và StepVerifier, đo số publisher đang in-flight và xác nhận cancellation/error.

**Tài liệu chính thức:**
- [Spring Framework — WebClient: Synchronous Use and composing multiple calls](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html)
- [Spring Framework — WebClient retrieve()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html)
- [Project Reactor 3.5 — Flux Javadoc: flatMap, flatMapSequential, concatMap](https://docs.spring.io/projectreactor/reactor-core/docs/3.5.x/api/reactor/core/publisher/Flux.html)
- [Project Reactor — Mono Javadoc: zip and zipDelayError](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Spring Framework — Testing WebClient with MockWebServer](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html)
- [Reactor Netty — Connection Provider](https://projectreactor.io/docs/netty/release/reference/http-client.html)

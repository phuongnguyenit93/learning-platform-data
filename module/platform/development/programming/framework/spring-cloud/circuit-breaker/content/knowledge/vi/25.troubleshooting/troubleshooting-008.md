# Reactive pipeline không được bao đúng hoặc bị đăng ký nhiều lần

## Vì sao lỗi này khó nhận ra?

Trong Spring Cloud Circuit Breaker, lời gọi reactive thường được biểu diễn bằng `Mono` hoặc `Flux`. Publisher mô tả một luồng xử lý; nó chưa thực thi request ngay tại thời điểm được tạo. Với phần lớn publisher từ `WebClient`, công việc I/O bắt đầu khi có subscription. Vì vậy, một phương thức có thể trả về `Mono` trông đúng nhưng Circuit Breaker chưa chắc đã bao đúng đoạn gọi mạng, và một publisher có thể bị subscribe nhiều lần ngoài ý muốn.

Hai triệu chứng thường xuất hiện cùng nhau:

- **Pipeline không được bao đúng:** lỗi kết nối, timeout hoặc HTTP status không được ghi nhận vào Circuit Breaker vì chúng xảy ra ngoài publisher được bảo vệ, hoặc bị xử lý thành tín hiệu thành công trước khi đi qua breaker.
- **Publisher bị đăng ký nhiều lần:** cùng một publisher cold bị nhiều subscriber kích hoạt, làm HTTP request được gửi nhiều lần, metrics tăng nhiều lần và có thể lặp lại thao tác có tác dụng phụ.

Trong hệ thống Spring Cloud dùng WebFlux, cần giữ ranh giới rõ giữa việc tạo publisher, áp dụng Circuit Breaker và subscribe. Mỗi subscription có thể tương ứng với một lần thực thi dependency. Không thể suy ra số request mạng chỉ từ số lần phương thức service được gọi.

## Hiểu vòng đời của Mono và Flux

Reactor publisher thường được tạo theo kiểu lazy. Ví dụ:

```java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", productId)
    .retrieve()
    .bodyToMono(Product.class);
```

Đoạn mã này tạo publisher mô tả request. Khi subscriber đăng ký, WebClient mới thực hiện lời gọi. Một publisher cold có thể chạy lại toàn bộ nguồn cho mỗi subscriber:

```java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", productId)
    .retrieve()
    .bodyToMono(Product.class);

product.subscribe();
product.subscribe(); // Có thể phát sinh một HTTP request thứ hai.
```

Đối với `WebClient`, mỗi subscription vào publisher request thường tạo một lần thực thi HTTP riêng. Nếu publisher được bọc bởi Circuit Breaker, mỗi lần subscription được bảo vệ có thể được ghi nhận như một lần gọi riêng. Vì vậy, hai subscription không phải hai cách đọc cùng một kết quả; chúng có thể là hai lần gọi dependency.

`Mono.just(value)` thường giữ sẵn một giá trị đã được tạo, trong khi `Mono.defer(supplier)` gọi supplier khi có subscription. `Mono.defer` hữu ích khi cần trì hoãn việc tạo publisher hoặc thực hiện thao tác phụ cho từng subscription:

```java
Mono<Product> product = Mono.defer(() ->
    webClient.get()
        .uri("/products/{id}", productId)
        .retrieve()
        .bodyToMono(Product.class)
);
```

`defer` không tự chống subscribe nhiều lần. Nó làm cho việc tạo publisher được thực hiện theo từng subscription; nếu có hai subscriber, supplier vẫn có thể chạy hai lần. Muốn chia sẻ một lần thực thi cho nhiều nhánh, phải thiết kế chia sẻ kết quả một cách có chủ đích.

## Đặt Circuit Breaker quanh đúng đoạn gọi dependency

Với Spring Cloud Circuit Breaker reactive API, dùng `ReactiveCircuitBreakerFactory` để tạo breaker và truyền publisher chính cùng fallback publisher vào `run`:

```java
import java.time.Duration;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ProductService {
    private final WebClient webClient;
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public ProductService(
            WebClient webClient,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.webClient = webClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public Mono<ProductView> find(String productId) {
        Mono<ProductView> primary = Mono.defer(() ->
            webClient.get()
                .uri("/products/{id}", productId)
                .retrieve()
                .bodyToMono(Product.class)
                .timeout(Duration.ofSeconds(2))
                .map(ProductView::available)
        );

        return circuitBreakerFactory.create("product-catalog").run(
            primary,
            error -> Mono.just(ProductView.unavailable(productId))
        );
    }
}
```

`primary` chứa lời gọi HTTP, timeout và chuyển đổi response. `run` bọc publisher đó bằng Circuit Breaker và nhận fallback publisher. Vì timeout nằm bên trong publisher được truyền vào `run`, tín hiệu timeout có thể được breaker quan sát và phân loại theo cấu hình provider. `Product` và `ProductView` là kiểu dữ liệu của ứng dụng; trạng thái `unavailable` cần thể hiện rõ dữ liệu không lấy được.

Nếu dùng trực tiếp Resilience4j Reactor operator, có thể bọc publisher bằng `CircuitBreakerOperator`:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.reactor.circuitbreaker.operator.CircuitBreakerOperator;
import reactor.core.publisher.Mono;

Mono<Product> protectedCall = Mono.defer(() ->
    webClient.get()
        .uri("/products/{id}", productId)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(2))
).transformDeferred(CircuitBreakerOperator.of(circuitBreaker));
```

Ví dụ operator dùng một instance `CircuitBreaker` đã được lấy từ registry Resilience4j. Chọn **một** điểm tích hợp cho một lời gọi: dùng reactive factory của Spring Cloud hoặc dùng operator trực tiếp. Không bọc cùng một request bằng cả `ReactiveCircuitBreakerFactory.run(...)` và `CircuitBreakerOperator` cho cùng mục đích nếu chưa thiết kế rõ hai lớp bảo vệ.

## Hiểu transform và transformDeferred

Reactor cung cấp `transform` và `transformDeferred` để áp dụng một phép biến đổi lên publisher:

- `transform` áp dụng hàm biến đổi khi pipeline được lắp ráp. Publisher kết quả vẫn có thể được subscribe nhiều lần.
- `transformDeferred` áp dụng hàm biến đổi theo từng subscriber. Cách này hữu ích khi phép biến đổi cần tạo hoặc lấy decorator riêng theo subscription.

Ví dụ:

```java
Mono<Product> protectedCall = remoteCall
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker));
```

`transformDeferred` không phải cơ chế chống gọi trùng. Nếu `protectedCall` có hai subscriber và nguồn là cold, nguồn vẫn có thể chạy hai lần. Nó cũng không tự cache kết quả. Muốn hiểu số lần gọi, hãy theo dõi subscription thực tế và vị trí của operator trong chuỗi.

Khi dùng `ReactiveCircuitBreakerFactory.run`, factory đã chịu trách nhiệm áp dụng Circuit Breaker cho publisher. Không cần bọc thêm `CircuitBreakerOperator` chỉ vì publisher được tạo bằng `Mono.defer` hoặc `transformDeferred`.

## Lỗi do tự subscribe trong service hoặc controller

Một lỗi phổ biến là gọi `subscribe()` bên trong service rồi trả về một publisher khác:

```java
// Không nên: tạo một subscription tách rời khỏi request của WebFlux.
public Mono<ResponseEntity<String>> refresh(String id) {
    productService.find(id).subscribe();
    return Mono.just(ResponseEntity.accepted().body("started"));
}
```

Subscription được tạo thủ công không còn nằm trong lifecycle của request WebFlux. Gateway hoặc controller có thể trả response trước khi lời gọi hoàn tất; lỗi có thể không đi vào error handling của request; client hủy request cũng không nhất thiết hủy subscription tách rời. Nếu đoạn gọi đã được bọc Circuit Breaker, breaker vẫn có thể ghi nhận subscription đó, nhưng ứng dụng mất khả năng phối hợp nó với luồng response chính.

Hãy trả publisher để framework quản lý subscription:

```java
public Mono<ResponseEntity<ProductView>> find(String id) {
    return productService.find(id)
        .map(ResponseEntity::ok);
}
```

Chỉ gọi `subscribe()` ở ranh giới ứng dụng được thiết kế rõ ràng cho tác vụ nền, có cơ chế quản lý lifecycle, lỗi, retry và shutdown riêng. Với xử lý nền quan trọng, cân nhắc hàng đợi bền vững thay vì tạo một subscription không được quản lý trong request handler.

## Một publisher được dùng ở nhiều nhánh có thể gọi dependency nhiều lần

Ví dụ sau có vẻ như dùng lại cùng một biến `Mono`, nhưng `Mono` từ WebClient là cold:

```java
Mono<Product> product = productClient.find(productId);

return Mono.zip(
    product,
    product.map(Product::displayName)
);
```

`Mono.zip` subscribe vào mỗi nguồn đầu vào. Ở đây cả `product` và `product.map(...)` đều subscribe vào cùng publisher cold, nên upstream có thể được thực thi hai lần. Nếu upstream chứa WebClient và Circuit Breaker, có thể có hai HTTP request và hai lần ghi nhận breaker.

Nếu hai nhánh cần cùng một kết quả, chia sẻ kết quả sau khi áp dụng Circuit Breaker:

```java
Mono<Product> sharedProduct = productClient.find(productId)
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker))
    .cache();

return Mono.zip(
    sharedProduct,
    sharedProduct.map(Product::displayName)
);
```

Trong cấu trúc này, cache nằm sau Circuit Breaker. Nguồn được bảo vệ chạy một lần cho lần subscribe đầu tiên; các nhánh dùng chung kết quả đã được cache trong cùng publisher instance. `Mono.cache()` cũng cache terminal signal, bao gồm lỗi, nên cần hiểu thời gian sống và phạm vi của publisher. Không lưu publisher đã cache vào singleton field nếu dữ liệu phụ thuộc vào request hoặc người dùng, vì có thể chia sẻ kết quả giữa các request không liên quan.

Vị trí cache ảnh hưởng điều breaker quan sát. Nếu đặt cache trước Circuit Breaker, nhiều subscriber có thể đi qua breaker nhưng nhận lại cùng một terminal signal từ nguồn đã chạy trước đó. Khi đó số lần breaker ghi nhận có thể khác số lần HTTP request thực sự được gửi. Hãy chọn vị trí theo mục tiêu đo: breaker thường nên bao quanh lời gọi dependency thực tế, sau đó mới chia sẻ kết quả cho nhiều nhánh trong cùng một luồng nghiệp vụ.

## Thứ tự Retry và Circuit Breaker làm thay đổi số liệu

`retryWhen` resubscribe vào publisher khi có lỗi phù hợp. Vị trí của Retry so với Circuit Breaker quyết định breaker quan sát từng lần thử hay kết quả cuối của cả chuỗi retry.

```java
// Circuit Breaker nằm trong Retry: mỗi lần retry subscribe lại qua breaker.
Mono<Product> countEachAttempt = remoteCall
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker))
    .retryWhen(retrySpec);

// Retry nằm trong Circuit Breaker: breaker bao toàn bộ chuỗi retry.
Mono<Product> countLogicalCall = remoteCall
    .retryWhen(retrySpec)
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker));
```

Ở cách thứ nhất, mỗi lần retry có thể trở thành một lần gọi riêng đối với Circuit Breaker. Ở cách thứ hai, breaker quan sát kết quả cuối của publisher đã retry; các lần thử bên trong vẫn tạo request mạng nhưng không nhất thiết được ghi nhận thành từng call độc lập ở breaker ngoài. Hãy chọn theo mục tiêu đo lường và kiểm tra thứ tự decorator của provider đang dùng.

Retry có thể nhân tải lên dependency. Nếu một request được thử lại ba lần và nhiều request cùng gặp lỗi, backend có thể nhận một đợt request lớn hơn số request nghiệp vụ ban đầu. Đặt giới hạn số lần, backoff, jitter và deadline tổng. Không retry thao tác ghi nếu chưa có idempotency key hoặc cơ chế chống xử lý trùng.

## Đặt fallback sau ranh giới cần đo

Vị trí `onErrorResume` ảnh hưởng kết quả Circuit Breaker nhìn thấy. Nếu xử lý lỗi thành một giá trị bình thường trước khi áp dụng breaker, breaker có thể ghi nhận thành công dù dependency chính đã thất bại:

```java
// Fallback nằm trong vùng được bảo vệ: breaker có thể chỉ thấy kết quả hoàn tất bình thường.
Mono<ProductView> possiblyMisclassified = remoteCall
    .onErrorResume(error -> Mono.just(ProductView.unavailable()))
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker));
```

Nếu muốn Circuit Breaker ghi nhận lỗi của dependency trước khi fallback tạo phản hồi thay thế, đặt fallback ở ngoài operator:

```java
Mono<ProductView> correctlyClassified = remoteCall
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker))
    .onErrorResume(error -> Mono.just(ProductView.unavailable()));
```

Với Spring Cloud `ReactiveCircuitBreaker`, truyền fallback function riêng vào `run` để integration quản lý thứ tự ghi nhận và fallback:

```java
return reactiveCircuitBreakerFactory.create("catalog").run(
    remoteCall,
    error -> Mono.just(ProductView.unavailable())
);
```

Fallback là kết quả thay thế cho caller; nó không chứng minh dependency đã thành công. Theo dõi riêng số lần fallback, số lỗi chính và trạng thái Circuit Breaker để tránh một response HTTP 200 che mất sự cố.

## Timeout cần nằm trong vùng Circuit Breaker cần quan sát

Nếu muốn timeout được tính là kết quả lỗi của dependency, đặt toán tử timeout trong publisher được Circuit Breaker bảo vệ:

```java
Mono<Product> protectedWithTimeout = remoteCall
    .timeout(Duration.ofSeconds(2))
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker));
```

Khi timeout phát ra `TimeoutException` bên trong publisher, Circuit Breaker có thể ghi nhận nó theo predicate cấu hình. Nếu đặt timeout bên ngoài operator, timeout có thể hủy subscription upstream từ phía ngoài; cách breaker ghi nhận cancellation phụ thuộc operator/provider và phiên bản. Hãy xác nhận bằng test và metrics, không giả định timeout bên ngoài luôn được tính là lỗi.

Timeout của Reactor cũng không bảo đảm server đã dừng xử lý request. Với thao tác ghi, server có thể đã thực hiện tác động nhưng response chưa về kịp. Kết hợp timeout với idempotency và deadline nghiệp vụ.

## Phân biệt lỗi HTTP, lỗi transport và lỗi trong bước xử lý sau response

Với `WebClient.retrieve()`, response 4xx/5xx mặc định được chuyển thành `WebClientResponseException` nếu không tùy chỉnh status handling. Lỗi kết nối, DNS hoặc timeout thường xuất hiện dưới dạng lỗi transport tương ứng. Nếu dùng `exchangeToMono` hoặc tự chuyển status thành một giá trị bình thường, Circuit Breaker có thể không nhìn thấy exception.

Ví dụ chuyển status 5xx thành lỗi trước khi hoàn tất publisher:

```java
Mono<Product> remoteCall = webClient.get()
    .uri("/products/{id}", productId)
    .retrieve()
    .onStatus(
        status -> status.is5xxServerError(),
        response -> response.createException()
    )
    .bodyToMono(Product.class);
```

Nếu status được chuyển thành đối tượng kết quả như `ProductView.unavailable()` trước khi đi qua Circuit Breaker, breaker có thể ghi nhận thành công. Hãy quyết định rõ status nào là lỗi dependency, status nào là kết quả nghiệp vụ và cấu hình `recordException`, `ignoreException` hoặc xử lý result tương ứng.

Ngoài ra, cần xác định phạm vi pipeline được bảo vệ. Nếu chỉ bọc HTTP request nhưng phép giải mã body hoặc bước biến đổi quan trọng nằm ngoài operator, lỗi ở bước đó có thể không được tính vào breaker. Ngược lại, không nên đưa các bước nghiệp vụ cục bộ không thuộc dependency vào cùng failure rate nếu chúng có thể phát sinh lỗi độc lập.

## Flux dài hạn và subscription không kết thúc

Circuit Breaker reactive thường đánh giá kết quả khi publisher hoàn tất hoặc phát lỗi. Với `Mono`, vòng đời thường ngắn và có một kết quả. Với `Flux`, một subscription có thể phát nhiều phần tử và kéo dài lâu. Nếu bọc một stream vô hạn như SSE, WebSocket hoặc event feed không kết thúc, breaker có thể giữ lời gọi ở trạng thái đang chạy trong thời gian dài và không có terminal signal để đánh giá kết quả cuối.

Với stream dài hạn, hãy xác định rõ mục tiêu bảo vệ:

- Nếu cần bảo vệ bước thiết lập kết nối, áp dụng timeout và Circuit Breaker cho thao tác mở kết nối hoặc lấy stream ban đầu.
- Nếu cần theo dõi lỗi trong quá trình stream, dùng metrics, reconnect policy và health signal phù hợp với giao thức.
- Không coi mỗi phần tử `onNext` là một lời gọi độc lập của Circuit Breaker nếu operator đang bao toàn bộ publisher.
- Khi subscriber hủy stream, kiểm tra cancellation có giải phóng tài nguyên và permit đúng cách; không tự xem client disconnect là lỗi dependency.

Đừng dùng Circuit Breaker request-response để thay thế cơ chế giám sát sức khỏe của một kết nối streaming kéo dài.

## Chẩn đoán khi request bị gọi nhiều lần

Khi thấy một request nghiệp vụ tạo nhiều HTTP request, kiểm tra theo thứ tự:

1. Tìm tất cả vị trí gọi `subscribe()` trong controller, service và helper.
2. Kiểm tra publisher có được dùng ở nhiều nhánh như `zip`, `when`, `flatMap` hoặc nhiều response subscriber hay không.
3. Kiểm tra `retry`, `repeat`, `cache`, `share` và các operator multicast.
4. Kiểm tra framework hoặc filter có tạo thêm subscription hay không.
5. Đếm số lần subscription và số lần HTTP request thực tế ở WebClient filter hoặc mock server.
6. Đối chiếu số subscription với metrics Circuit Breaker để xác định operator đang nằm trước hay sau điểm chia sẻ.

Một cách quan sát đơn giản trong môi trường phát triển:

```java
Mono<Product> remoteCall = Mono.defer(() -> {
    log.debug("Subscribing to catalog request for productId={}", productId);
    return webClient.get()
        .uri("/products/{id}", productId)
        .retrieve()
        .bodyToMono(Product.class);
});

return remoteCall
    .doOnSubscribe(subscription -> log.debug("Catalog publisher subscribed"))
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker));
```

Log `doOnSubscribe` cho biết số subscription đi qua publisher. Không ghi token, thông tin nhạy cảm hoặc dữ liệu cá nhân vào log. Trong production, ưu tiên counter/trace có cardinality thấp thay vì log mọi request ở mức debug.

## Kiểm thử bằng StepVerifier và publisher có thể điều khiển

Kiểm thử reactive nên xác minh số lần nguồn được thực thi, số lần fallback và tín hiệu cuối. Ví dụ dùng `Mono.defer` trong mock để đếm subscription thực tế:

```java
@Test
void oneSubscriptionProducesOneRemoteExecution() {
    AtomicInteger executions = new AtomicInteger();
    when(productClient.find("p-1")).thenReturn(Mono.defer(() -> {
        executions.incrementAndGet();
        return Mono.just(new Product("p-1"));
    }));

    StepVerifier.create(productService.find("p-1"))
        .expectNextMatches(product -> product.id().equals("p-1"))
        .verifyComplete();

    assertThat(executions).hasValue(1);
}
```

Để kiểm tra subscribe hai lần có thực thi nguồn hai lần hay không:

```java
Mono<Product> result = productService.find("p-1");

StepVerifier.create(result)
    .expectNextCount(1)
    .verifyComplete();

StepVerifier.create(result)
    .expectNextCount(1)
    .verifyComplete();

assertThat(executions).hasValue(2);
```

Nếu thiết kế yêu cầu chỉ gọi dependency một lần cho nhiều nhánh, thêm cache hoặc cơ chế chia sẻ ở đúng vị trí rồi kiểm tra số execution vẫn bằng một. Không dùng cache toàn cục để làm test qua chỉ vì nó che được lỗi subscribe nhiều lần.

Các trường hợp nên có trong bộ kiểm thử:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Một subscription thành công | Supplier chạy một lần và breaker ghi nhận một kết quả. |
| Dependency phát exception | Breaker ghi nhận theo predicate và fallback chạy đúng một lần. |
| Hai subscriber vào publisher cold | Có hai lần thực thi nếu không có chia sẻ kết quả. |
| Nhiều nhánh dùng chung publisher đã cache sau breaker | Dependency chỉ được gọi một lần trong phạm vi publisher đó. |
| Retry được bật | Số lần thử thực tế khớp retry policy và thứ tự decorator. |
| Timeout xảy ra trong vùng được bảo vệ | Breaker nhận tín hiệu timeout theo cấu hình. |
| Subscriber hủy | Tài nguyên được giải phóng; cancellation không bị nhầm thành response thành công. |
| Fallback tự lỗi | Lỗi fallback được truyền/quan sát riêng và không che mất nguyên nhân ban đầu. |

`StepVerifier` cho phép kiểm tra publisher mà không cần gọi `subscribe()` thủ công trong mã ứng dụng. Với thời gian retry hoặc timeout, có thể dùng virtual time nếu publisher và scheduler hỗ trợ; tránh chờ thực lâu trong test. Khi dùng mock HTTP server, đếm số request thực sự nhận được để xác nhận không chỉ số lần gọi phương thức client.

## Phân biệt các dấu hiệu trong metrics

Khi publisher bị subscribe nhiều lần, có thể thấy số lời gọi được bảo vệ, số request HTTP và số lần ghi nhận Circuit Breaker tăng tương ứng. Tuy nhiên, nếu cache, retry hoặc fallback nằm ở vị trí khác nhau, các số đếm không nhất thiết bằng nhau.

Nên quan sát riêng:

- Số lần service method tạo publisher.
- Số subscription đi vào publisher được bảo vệ.
- Số request thực tế gửi đến dependency.
- Số lần retry.
- Số lần Circuit Breaker ghi nhận success, failure, slow call hoặc not permitted.
- Số lần fallback được gọi và số lần fallback hoàn tất.

Đặt metric tag theo dependency hoặc breaker ID ổn định. Không đưa product ID, user ID, request ID hoặc exception message vào tag vì cardinality tăng nhanh. Dùng trace ID trong log hoặc distributed tracing để theo dõi một request cụ thể.

Nếu request HTTP thực tế tăng nhưng số lần breaker không tăng, có thể một phần request nằm ngoài vùng được bảo vệ hoặc retry được đặt bên trong boundary. Nếu breaker metrics tăng nhưng request đến dependency không tăng, có thể Circuit Breaker đang từ chối lời gọi, cache đang trả kết quả hoặc lỗi phát sinh trước khi gửi mạng. Hãy đối chiếu cả ba lớp: subscription, breaker event và HTTP client.

## Các lỗi thường gặp và cách khắc phục

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Tạo publisher nhưng không trả hoặc không subscribe | Lời gọi không được thực thi. | Trả `Mono`/`Flux` cho WebFlux hoặc subscribe tại một ranh giới tác vụ nền có quản lý. |
| Gọi `subscribe()` trong service/controller | Subscription tách khỏi request lifecycle, lỗi và cancellation khó quản lý. | Trả publisher về cho framework. |
| Subscribe nhiều lần vào publisher cold | Dependency bị gọi nhiều lần và breaker ghi nhận nhiều invocation. | Kiểm tra subscriber, chia sẻ kết quả khi cần và test số execution. |
| Bọc breaker sau khi lỗi đã được chuyển thành giá trị fallback | Breaker có thể chỉ thấy thành công. | Đặt fallback ngoài boundary hoặc dùng fallback API của reactive circuit breaker. |
| Đặt timeout ngoài breaker khi muốn ghi nhận timeout | Breaker có thể chỉ thấy cancellation tùy provider. | Đặt timeout trong publisher được bảo vệ và xác nhận bằng test. |
| Dùng imperative factory rồi `block()` | Chặn event-loop và làm mất mô hình reactive. | Dùng `ReactiveCircuitBreakerFactory` hoặc Reactor operator. |
| Dùng cả factory và operator cho cùng một dependency call | Hai breaker hoặc hai lớp metrics có thể lồng nhau. | Chọn một integration boundary rõ ràng. |
| Đặt breaker sau cache hoặc share mà không hiểu semantics | Metrics breaker có thể không tương ứng số request mạng. | Đặt breaker quanh nguồn dependency rồi chia sẻ kết quả nếu mục tiêu là đếm remote call. |
| Retry ở ngoài breaker nhưng tưởng chỉ có một lần ghi nhận | Mỗi lần retry có thể resubscribe qua breaker. | Xác định thứ tự decorator và đo cả attempts lẫn logical calls. |
| Dùng Circuit Breaker cho Flux vô hạn | Call có thể không có terminal signal để đánh giá. | Bảo vệ bước kết nối và giám sát stream bằng cơ chế riêng. |

## Quy trình xử lý sự cố

Khi thấy reactive pipeline không được bảo vệ hoặc dependency bị gọi nhiều lần, thực hiện theo trình tự:

1. Xác định publisher nào chứa lời gọi dependency và xác định nó là cold, hot hay đã được cache/share.
2. Vẽ lại chuỗi operator từ nguồn đến subscriber, đánh dấu vị trí Circuit Breaker, timeout, retry, fallback và cache.
3. Xác nhận WebFlux/controller trả publisher và không tạo subscription tách rời.
4. Đếm subscription và request HTTP thực tế bằng `doOnSubscribe`, mock hoặc HTTP test server.
5. Đặt Circuit Breaker quanh đúng đoạn cần đo; bảo đảm lỗi và timeout phát sinh bên trong boundary.
6. Xác định một lần gọi nghiệp vụ có cần chia sẻ kết quả cho nhiều nhánh hay cần gọi dependency riêng cho từng nhánh.
7. Kiểm tra thứ tự Retry, fallback và cache để metrics phản ánh đúng điều muốn bảo vệ.
8. Chạy StepVerifier cho success, error, timeout, cancellation và nhiều subscriber.
9. Đối chiếu metrics Circuit Breaker với số lần request thực tế đến dependency trước khi kết luận đã khắc phục.

Reactive pipeline được bảo vệ đúng khi subscription thực thi lời gọi dependency đi qua một Circuit Breaker có ranh giới rõ, lỗi cần theo dõi không bị chuyển thành success trước khi breaker quan sát, và số subscription phản ánh đúng số lần gọi mà nghiệp vụ mong muốn. Giữ publisher trong lifecycle của WebFlux, kiểm soát retry/fallback/cache và kiểm thử bằng StepVerifier sẽ giúp tránh gọi trùng, ghi nhận sai failure rate và làm sai lệch hành vi bảo vệ trong Spring Cloud Circuit Breaker.

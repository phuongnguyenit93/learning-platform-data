# Kiểm thử reactive bằng StepVerifier

Spring Data Elasticsearch Reactive trả về `Mono` và `Flux` thay vì kết quả đồng bộ. Các publisher này mô tả một luồng xử lý bất đồng bộ; chúng thường chỉ thực thi khi có subscriber. Vì vậy, unit test không nên gọi `.block()` hoặc tự `subscribe()` chỉ để lấy kết quả. Project Reactor cung cấp `StepVerifier` trong module `reactor-test` để đăng ký vào publisher, điều khiển demand và kiểm tra lần lượt các tín hiệu mà publisher phát ra.

`StepVerifier` giúp kiểm tra cả kết quả lẫn hành vi của một pipeline: phần tử phát ra, thứ tự, completion, error, backpressure, cancellation, retry và thời gian. Với Spring Data Elasticsearch, có thể dùng nó để kiểm thử service/repository reactive ở mức unit bằng mock, rồi bổ sung integration test với Elasticsearch thật để xác nhận mapping, query, persistence và search visibility.

## 1. Vì sao cần StepVerifier?

Trong lập trình reactive, một method trả về `Mono<T>` hoặc `Flux<T>` chưa chắc đã thực hiện công việc ngay tại thời điểm được gọi. Nó trả về một mô tả publisher. Khi test chỉ gọi method mà không subscribe, pipeline có thể chưa chạy và assertion không kiểm tra được gì.

Ví dụ:

```java
Mono<ProductDocument> result = productService.findById("p-100");
```

Đoạn code trên mới tạo publisher. `StepVerifier` subscribe vào publisher, yêu cầu phần tử và kiểm tra tín hiệu:

```java
StepVerifier.create(result)
    .expectNextMatches(product -> product.getId().equals("p-100"))
    .verifyComplete();
```

`verifyComplete()` bắt đầu quá trình kiểm thử và chờ publisher phát completion. Nếu publisher không phát tín hiệu như mong đợi hoặc bị treo, test sẽ thất bại theo timeout của verifier.

### StepVerifier kiểm tra tín hiệu Reactive Streams

Một publisher có thể phát các tín hiệu:

- `onSubscribe`: subscriber nhận subscription.
- `onNext`: publisher phát một phần tử.
- `onError`: publisher kết thúc bằng lỗi.
- `onComplete`: publisher hoàn tất bình thường.

StepVerifier mô tả kỳ vọng theo thứ tự. Nếu publisher phát sai thứ tự, phát thêm phần tử, phát error thay vì complete hoặc không kết thúc, test sẽ báo lỗi.

## 2. Thêm dependency `reactor-test`

`StepVerifier`, `TestPublisher` và `PublisherProbe` nằm trong artifact `reactor-test`. Với Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Với Maven:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

Nếu dự án dùng Spring Boot dependency management, để BOM quản lý version tương thích của Reactor thay vì tự chọn một version khác với Reactor Core đang chạy. Nếu không dùng BOM, bảo đảm `reactor-test` và `reactor-core` có version tương thích.

Import thường dùng:

```java
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.TestPublisher;
import reactor.test.publisher.PublisherProbe;
```

## 3. Kiểm thử `Mono` cơ bản

`Mono<T>` phát tối đa một phần tử rồi complete, hoặc phát error. Có thể dùng `expectNext`, `assertNext`, `expectNextMatches` và `verifyComplete`.

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class MonoStepVerifierTest {

    @Test
    void emitsOneValueAndCompletes() {
        Mono<String> source = Mono.just("wireless mouse");

        StepVerifier.create(source)
            .expectNext("wireless mouse")
            .verifyComplete();
    }

    @Test
    void emitsNoValueAndCompletes() {
        Mono<String> source = Mono.empty();

        StepVerifier.create(source)
            .verifyComplete();
    }

    @Test
    void assertsTheEmittedObject() {
        ProductDocument product = new ProductDocument("p-100", "Mouse");

        StepVerifier.create(Mono.just(product))
            .assertNext(actual -> {
                assertThat(actual.getId()).isEqualTo("p-100");
                assertThat(actual.getName()).isEqualTo("Mouse");
            })
            .verifyComplete();
    }
}
```

`expectNext(value)` so sánh giá trị theo `equals`. `assertNext(consumer)` phù hợp khi cần nhiều assertion trên cùng một phần tử. `expectNextMatches(predicate)` phù hợp với một điều kiện boolean ngắn.

### Kiểm tra `Mono<Void>`

Các thao tác như delete hoặc cập nhật không trả nội dung có thể trả `Mono<Void>`. Publisher hoàn tất mà không phát `onNext`:

```java
StepVerifier.create(productService.delete("p-100"))
    .verifyComplete();
```

Không viết `expectNext(null)`: Reactive Streams không cho phép phát `null`.

## 4. Kiểm thử `Flux` và thứ tự phần tử

`Flux<T>` có thể phát từ 0 đến nhiều phần tử. `expectNext` kiểm tra từng giá trị theo thứ tự:

```java
@Test
void emitsProductsInExpectedOrder() {
    Flux<String> names = Flux.just("Mouse", "Keyboard", "Monitor");

    StepVerifier.create(names)
        .expectNext("Mouse")
        .expectNext("Keyboard")
        .expectNext("Monitor")
        .verifyComplete();
}
```

Có thể gom nhiều giá trị trong một lời gọi:

```java
StepVerifier.create(names)
    .expectNext("Mouse", "Keyboard", "Monitor")
    .verifyComplete();
```

Nếu chỉ quan tâm số lượng:

```java
StepVerifier.create(Flux.range(1, 100))
    .expectNextCount(100)
    .verifyComplete();
```

`expectNextCount(n)` xác nhận có đúng n phần tử kế tiếp trong luồng kỳ vọng; nó không kiểm tra nội dung từng phần tử. Khi nội dung quan trọng, dùng `assertNext` hoặc `expectNextMatches`.

### Kiểm tra phần tử cuối cùng hoặc danh sách đã ghi nhận

Có thể ghi các phần tử đã phát vào collection:

```java
StepVerifier.create(Flux.just("A", "B", "C"))
    .recordWith(ArrayList::new)
    .expectNextCount(3)
    .consumeRecordedWith(values ->
        assertThat(values).containsExactly("A", "B", "C")
    )
    .verifyComplete();
```

Không nên thu toàn bộ một luồng rất lớn chỉ để kiểm thử. Dùng fixture nhỏ, hoặc kiểm tra số lượng và một số invariant quan trọng.

## 5. `verifyComplete`, `verify`, và timeout

Các terminal verification method bắt đầu subscription và chờ tín hiệu:

| Method | Kỳ vọng |
|---|---|
| `verifyComplete()` | Publisher kết thúc bằng `onComplete` |
| `verifyError()` | Publisher kết thúc bằng error |
| `verifyError(Class)` | Error có kiểu mong đợi |
| `verifyErrorMessage(String)` | Error có message mong đợi |
| `verify()` | Kết thúc theo kịch bản đã mô tả, không ép kiểu terminal cụ thể |
| `verify(Duration)` | Chạy verification với timeout tường minh |

Trong test có publisher có thể không kết thúc, luôn đặt timeout để tránh CI treo:

```java
StepVerifier.create(productService.search("mouse"))
    .expectNextCount(2)
    .thenCancel()
    .verify(Duration.ofSeconds(3));
```

Có thể cấu hình default timeout cho StepVerifier trong test suite, nhưng timeout tường minh ở những test có khả năng chờ lâu giúp ý định rõ ràng hơn.

## 6. Kiểm tra error

Một publisher có thể kết thúc bằng lỗi. Dùng `expectError` để kiểm tra loại lỗi:

```java
@Test
void propagatesSearchFailure() {
    RuntimeException failure = new RuntimeException("Elasticsearch unavailable");

    StepVerifier.create(Mono.error(failure))
        .expectError(RuntimeException.class)
        .verify();
}
```

Kiểm tra message:

```java
StepVerifier.create(Mono.error(new IllegalStateException("invalid state")))
    .verifyErrorMessage("invalid state");
```

Hoặc kiểm tra sâu hơn:

```java
StepVerifier.create(service.findById("missing"))
    .expectErrorSatisfies(error -> {
        assertThat(error)
            .isInstanceOf(ProductNotFoundException.class)
            .hasMessageContaining("missing");
    })
    .verify();
```

### Kiểm tra fallback

Nếu service chuyển lỗi thành giá trị mặc định bằng `onErrorResume`, hãy kiểm tra kết quả cuối cùng thay vì mong đợi error:

```java
Mono<String> result = remoteCall()
    .onErrorResume(error -> Mono.just("fallback"));

StepVerifier.create(result)
    .expectNext("fallback")
    .verifyComplete();
```

Test nên xác nhận đúng loại lỗi nào được fallback. Không nên nuốt mọi exception nếu lỗi mapping, validation hoặc programming error cần được phát hiện.

## 7. Kiểm thử `switchIfEmpty` và not-found behavior

Repository tìm theo ID thường trả `Mono.empty()` khi không có document. Service có thể chuyển empty thành domain exception:

```java
public Mono<ProductDocument> getRequired(String id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(id)
        ));
}
```

Kiểm thử cả hai nhánh:

```java
@Test
void returnsProductWhenFound() {
    ProductDocument product = new ProductDocument("p-100", "Mouse");
    when(repository.findById("p-100")).thenReturn(Mono.just(product));

    StepVerifier.create(service.getRequired("p-100"))
        .expectNext(product)
        .verifyComplete();
}

@Test
void returnsNotFoundWhenEmpty() {
    when(repository.findById("missing")).thenReturn(Mono.empty());

    StepVerifier.create(service.getRequired("missing"))
        .expectError(ProductNotFoundException.class)
        .verify();
}
```

`switchIfEmpty` chỉ chạy khi upstream hoàn tất mà không phát phần tử. Nó không xử lý error; error cần `onErrorResume` hoặc cơ chế khác.

## 8. Kiểm thử backpressure và demand

Một trong những lợi ích của StepVerifier là kiểm soát số phần tử subscriber yêu cầu. Có thể tạo verifier với `initialRequest(0)` để ban đầu chưa yêu cầu phần tử nào:

```java
@Test
void emitsOnlyWhenDemandIsRequested() {
    Flux<Integer> source = Flux.range(1, 3);

    StepVerifier.create(source, 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(2)
        .expectNext(2, 3)
        .verifyComplete();
}
```

`thenRequest(n)` gửi demand thêm n phần tử. Test trên kiểm tra publisher tuân thủ demand theo từng bước.

### Kiểm tra chưa phát thêm phần tử khi chưa request

```java
StepVerifier.create(Flux.range(1, 3), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .then(() -> assertThat(true).isTrue())
    .thenRequest(1)
    .expectNext(2)
    .thenRequest(1)
    .expectNext(3)
    .verifyComplete();
```

Không cần thêm assertion giả như `assertThat(true)` trong test thực tế; ví dụ chỉ minh họa vị trí có thể thực hiện một side-effect/assertion đồng bộ giữa các bước. Nếu cần chứng minh upstream không phát quá demand, dùng `TestPublisher` hoặc kiểm tra subscription/demand của publisher phù hợp.

## 9. `thenRequest` và `expectNoEvent`

`thenRequest(n)` điều khiển demand ở thời điểm cụ thể trong kịch bản. `expectNoEvent(duration)` xác nhận trong khoảng thời gian đó không có tín hiệu nào xảy ra.

Ví dụ publisher phát sau một khoảng delay:

```java
StepVerifier.withVirtualTime(() -> Mono.delay(Duration.ofSeconds(5)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(4))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .verifyComplete();
```

`expectNoEvent` cũng xem subscription là một event. Vì vậy, nên gọi `expectSubscription()` trước khi dùng nó để tránh test thất bại ngay khi subscription xảy ra.

## 10. Kiểm tra cancellation

Cancellation xảy ra khi subscriber không còn muốn nhận dữ liệu, ví dụ client đóng kết nối hoặc người dùng hủy một luồng export.

```java
@Test
void cancelsAfterReceivingTwoItems() {
    StepVerifier.create(Flux.range(1, 10))
        .expectNext(1, 2)
        .thenCancel()
        .verify();
}
```

Test này xác nhận kịch bản kết thúc bằng cancel. Nếu service có cleanup khi cancel, cần kiểm tra cleanup được gọi bằng `PublisherProbe`, mock hoặc một side effect có thể quan sát.

### Cancellation không đồng nghĩa với rollback

Hủy một publisher không tự hoàn tác các thao tác đã hoàn tất trước đó. Nếu pipeline đã ghi một số document vào Elasticsearch rồi bị cancel, những document đó vẫn có thể tồn tại. Với job bulk hoặc export, cần thiết kế checkpoint, idempotency và cleanup riêng.

## 11. Kiểm thử `doFinally` và cleanup

`doFinally` nhận tín hiệu kết thúc dạng `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`. Có thể dùng nó để giải phóng metric/resource nhẹ hoặc quan sát lifecycle:

```java
AtomicReference<SignalType> termination = new AtomicReference<>();

Flux<Integer> source = Flux.range(1, 10)
    .doFinally(termination::set);

StepVerifier.create(source)
    .expectNext(1, 2, 3)
    .thenCancel()
    .verify();

assertThat(termination.get()).isEqualTo(SignalType.CANCEL);
```

Với cleanup bất đồng bộ, dùng `usingWhen` và kiểm tra publisher cleanup được subscribe/hoàn tất. Không chỉ kiểm tra một cờ nếu tài nguyên thực tế cần đóng qua một API async.

## 12. Virtual time cho publisher có delay

Test dùng `Thread.sleep()` thường chậm và không ổn định. `StepVerifier.withVirtualTime` cho phép điều khiển thời gian ảo để test `delay`, `timeout`, `interval`, retry backoff và các operator phụ thuộc scheduler được hỗ trợ.

Ví dụ:

```java
@Test
void emitsAfterFiveVirtualSeconds() {
    StepVerifier.withVirtualTime(
            () -> Mono.delay(Duration.ofSeconds(5))
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(5))
        .expectNext(0L)
        .verifyComplete();
}
```

Test không phải chờ năm giây thật. Verifier tiến virtual clock tới mốc được yêu cầu.

### Tạo publisher bên trong supplier

Hãy tạo publisher bên trong lambda truyền cho `withVirtualTime`:

```java
StepVerifier.withVirtualTime(() -> service.delayedResult())
    .thenAwait(Duration.ofSeconds(10))
    .expectNext("ready")
    .verifyComplete();
```

Không tạo publisher có scheduler/timer trước khi gọi `withVirtualTime`, vì scheduler thật có thể đã được gắn vào publisher trước khi virtual scheduler được cài đặt.

### Custom scheduler

Nếu service nhận scheduler được inject, test nên inject `VirtualTimeScheduler` hoặc một scheduler test phù hợp thay vì hard-code `Schedulers.parallel()` bên trong service. Khi publisher dùng một scheduler không được virtual time thay thế, `thenAwait` có thể không điều khiển được thời gian của publisher đó.

## 13. Kiểm thử timeout

`timeout` chuyển publisher thành error nếu không có tín hiệu trong khoảng thời gian cấu hình:

```java
Mono<String> result = Mono.<String>never()
    .timeout(Duration.ofSeconds(3));

StepVerifier.withVirtualTime(() -> result)
    .thenAwait(Duration.ofSeconds(3))
    .expectError(TimeoutException.class)
    .verify();
```

Trong ví dụ thực tế, nên tạo cả `Mono.never()` và operator `timeout` bên trong supplier để virtual scheduler được sử dụng đúng:

```java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never().timeout(Duration.ofSeconds(3))
    )
    .thenAwait(Duration.ofSeconds(3))
    .expectError(TimeoutException.class)
    .verify();
```

Phân biệt timeout do Reactor operator với timeout của Elasticsearch HTTP client hoặc server. Virtual time chỉ điều khiển scheduler mà Reactor sử dụng; nó không làm Elasticsearch thật chạy nhanh hơn và không thay thế integration test timeout mạng.

## 14. Kiểm thử retry và backoff

Ví dụ service retry khi gặp lỗi tạm thời:

```java
Mono<String> call = Mono.defer(() -> remoteCall())
    .retryWhen(Retry.backoff(2, Duration.ofSeconds(1)));
```

Có thể kiểm tra retry bằng virtual time:

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> retried = Mono.defer(() -> {
    int attempt = attempts.incrementAndGet();
    if (attempt < 3) {
        return Mono.error(new IOException("temporary"));
    }
    return Mono.just("ok");
}).retryWhen(Retry.backoff(2, Duration.ofSeconds(1))
    .jitter(0));

StepVerifier.withVirtualTime(() -> retried)
    .thenAwait(Duration.ofSeconds(3))
    .expectNext("ok")
    .verifyComplete();

assertThat(attempts.get()).isEqualTo(3);
```

Để virtual time hoạt động chắc chắn, có thể chuyển toàn bộ phần tạo publisher và retry vào supplier:

```java
AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() -> Mono.defer(() -> {
        int attempt = attempts.incrementAndGet();
        return attempt < 3
            ? Mono.error(new IOException("temporary"))
            : Mono.just("ok");
    }).retryWhen(Retry.backoff(2, Duration.ofSeconds(1)).jitter(0)))
    .thenAwait(Duration.ofSeconds(3))
    .expectNext("ok")
    .verifyComplete();

assertThat(attempts.get()).isEqualTo(3);
```

Trong production, không retry mọi lỗi Elasticsearch. Lỗi mapping/validation thường không retry; lỗi tạm thời có thể retry có giới hạn; version conflict cần đọc lại và tính lại theo nghiệp vụ. Test cần xác nhận đúng loại lỗi được retry và số lần retry tối đa.

## 15. `TestPublisher` để kiểm soát nguồn phát

`TestPublisher` là publisher dành cho test. Nó cho phép test chủ động phát phần tử, complete hoặc error vào subscriber.

```java
@Test
void processesItemsAsTheyArrive() {
    TestPublisher<String> source = TestPublisher.create();

    Flux<String> result = source.flux()
        .map(String::toUpperCase);

    StepVerifier.create(result)
        .then(() -> source.next("mouse"))
        .expectNext("MOUSE")
        .then(() -> source.next("keyboard"))
        .expectNext("KEYBOARD")
        .then(source::complete)
        .verifyComplete();
}
```

`TestPublisher` hữu ích khi muốn kiểm soát thời điểm upstream phát dữ liệu, kiểm tra pipeline phản ứng với dữ liệu đến từng phần hoặc mô phỏng một publisher do ứng dụng tự xây dựng.

### Phát error có kiểm soát

```java
TestPublisher<ProductDocument> source = TestPublisher.create();
RuntimeException failure = new RuntimeException("source failed");

StepVerifier.create(source.flux())
    .then(() -> source.error(failure))
    .expectErrorMatches(error -> error == failure)
    .verify();
```

Không dùng `TestPublisher` để giả lập toàn bộ hành vi Elasticsearch server. Nó kiểm soát publisher ở tầng reactive; mapping, query DSL, routing và persistence cần integration test.

## 16. Kiểm tra demand với `TestPublisher`

Có thể kiểm tra subscriber đã yêu cầu dữ liệu như thế nào:

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux(), 0)
    .expectSubscription()
    .thenRequest(1)
    .then(() -> source.next(1))
    .expectNext(1)
    .thenCancel()
    .verify();

source.assertWasRequested();
```

`TestPublisher` cung cấp các assertion như `assertWasSubscribed`, `assertWasRequested`, `assertWasNotRequested` và `assertCancelled` tùy API/version. Dùng chúng để xác nhận pipeline đã subscribe/request/cancel đúng hành vi.

Không cố tình phát quá demand bằng một publisher compliant trong test thông thường. Nếu muốn kiểm tra cách pipeline xử lý một publisher vi phạm Reactive Streams, `TestPublisher` có chế độ non-compliant; chỉ dùng khi có một yêu cầu cụ thể vì nó mô phỏng nguồn không tuân thủ giao thức.

## 17. `PublisherProbe` để kiểm tra nhánh publisher

`PublisherProbe` bọc một publisher để quan sát nó có được subscribe, request hoặc cancel hay không. Nó hữu ích khi test `switchIfEmpty`, `onErrorResume`, `then` hoặc nhánh fallback.

Ví dụ:

```java
@Test
void usesFallbackWhenPrimaryIsEmpty() {
    PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("fallback"));

    Mono<String> result = Mono.<String>empty()
        .switchIfEmpty(fallback.mono());

    StepVerifier.create(result)
        .expectNext("fallback")
        .verifyComplete();

    fallback.assertWasSubscribed();
    fallback.assertWasRequested();
}
```

Nếu primary publisher có dữ liệu, fallback không được subscribe:

```java
PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("fallback"));

StepVerifier.create(Mono.just("primary").switchIfEmpty(fallback.mono()))
    .expectNext("primary")
    .verifyComplete();

fallback.assertWasNotSubscribed();
```

Probe kiểm tra publisher branch được sử dụng đúng; nó không thay thế assertion về giá trị nghiệp vụ.

## 18. Kiểm thử Reactor Context

Reactor Context là cơ chế truyền dữ liệu gắn với subscription, thường dùng cho correlation ID hoặc metadata ở tầng reactive. Nó khác `ThreadLocal` vì không phụ thuộc việc pipeline luôn chạy trên cùng một thread.

Có thể đặt context trong test:

```java
StepVerifier.create(
        Mono.deferContextual(context ->
            Mono.just(context.get("tenantId"))
        ),
        StepVerifierOptions.create()
            .withInitialContext(Context.of("tenantId", "tenant-42"))
    )
    .expectAccessibleContext()
    .contains("tenantId", "tenant-42")
    .then()
    .expectNext("tenant-42")
    .verifyComplete();
```

`expectAccessibleContext()` cho phép kiểm tra context có mặt tại subscription. Có thể dùng `StepVerifierOptions` để đặt scenario name hoặc initial context.

### Context và Spring Security

Trong ứng dụng reactive có Spring Security, security context thường được truyền qua Reactor Context. Không giả định `SecurityContextHolder` dạng ThreadLocal luôn chứa authentication đúng trong mọi callback reactive. Khi service phụ thuộc vào principal/tenant, hãy test cả trường hợp có context và thiếu context bằng cách cấu hình context phù hợp hoặc dùng WebFlux security test utilities.

## 19. Kiểm thử `Mono.zip` và kết hợp nhiều nguồn

Service có thể kết hợp nhiều publisher, ví dụ lấy sản phẩm và tồn kho:

```java
public Mono<ProductView> getView(String id) {
    return Mono.zip(
        productRepository.findById(id),
        inventoryClient.getStock(id)
    ).map(tuple -> new ProductView(
        tuple.getT1().getId(),
        tuple.getT1().getName(),
        tuple.getT2()
    ));
}
```

Test bằng StepVerifier:

```java
@Test
void combinesProductAndInventory() {
    ProductDocument product = new ProductDocument("p-100", "Mouse");
    when(productRepository.findById("p-100"))
        .thenReturn(Mono.just(product));
    when(inventoryClient.getStock("p-100"))
        .thenReturn(Mono.just(12));

    StepVerifier.create(service.getView("p-100"))
        .assertNext(view -> {
            assertThat(view.id()).isEqualTo("p-100");
            assertThat(view.name()).isEqualTo("Mouse");
            assertThat(view.stock()).isEqualTo(12);
        })
        .verifyComplete();
}
```

`Mono.zip` thường cần mỗi nguồn phát một giá trị. Nếu một nguồn empty, zip có thể hoàn tất empty; nếu một nguồn error, zip phát error. Hãy viết test cho các nhánh đó nếu service có logic fallback hoặc not-found.

## 20. Kiểm thử service Spring Data Elasticsearch bằng mock

Unit test nên tập trung vào logic service và hợp đồng reactive, không cần khởi động Elasticsearch cho mọi trường hợp.

Ví dụ service dùng reactive repository:

```java
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Flux<ProductDocument> findByCategory(String category) {
        return repository.findByCategory(category)
            .filter(product -> product.getStatus() == ProductStatus.ACTIVE);
    }

    public Mono<ProductDocument> create(ProductDocument product) {
        return repository.save(product);
    }
}
```

Repository:

```java
public interface ProductRepository
        extends ReactiveElasticsearchRepository<ProductDocument, String> {

    Flux<ProductDocument> findByCategory(String category);
}
```

Unit test với Mockito:

```java
@ExtendWith(MockitoExtension.class)
class ProductServiceTest {

    @Mock
    ProductRepository repository;

    ProductService service;

    @BeforeEach
    void setUp() {
        service = new ProductService(repository);
    }

    @Test
    void returnsOnlyActiveProducts() {
        ProductDocument active = product("p-1", ProductStatus.ACTIVE);
        ProductDocument inactive = product("p-2", ProductStatus.INACTIVE);

        when(repository.findByCategory("accessories"))
            .thenReturn(Flux.just(active, inactive));

        StepVerifier.create(service.findByCategory("accessories"))
            .expectNext(active)
            .verifyComplete();

        verify(repository).findByCategory("accessories");
    }
}
```

Mock repository trả publisher để service xử lý. StepVerifier subscribe và xác nhận nội dung đầu ra. Mockito `verify` xác nhận dependency được gọi với tham số đúng.

### Đừng mock những gì test đang muốn xác nhận

Nếu test muốn kiểm tra derived query method tạo ra query đúng với Elasticsearch mapping, mock repository sẽ bỏ qua phần đó. Unit test chỉ xác nhận service gọi repository và xử lý kết quả; derived query, mapping và server behavior cần integration test.

## 21. Kiểm thử `ReactiveElasticsearchOperations`

Với custom query, service có thể phụ thuộc `ReactiveElasticsearchOperations`:

```java
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchService(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Flux<ProductDocument> search(Query query) {
        return operations.search(query, ProductDocument.class)
            .map(SearchHit::getContent);
    }
}
```

Có thể mock method `search` để trả `Flux<SearchHit<ProductDocument>>` đã dựng trong test, rồi dùng StepVerifier xác nhận service map đúng `SearchHit` sang entity. Tuy nhiên, việc tạo `SearchHit` có thể cần builder/constructor tùy version Spring Data. Giữ test ở mức service nếu mục tiêu chỉ là kiểm tra mapping đầu ra; dùng integration test khi cần kiểm tra query thực tế.

### Kiểm tra query được tạo

Nếu service tự xây `NativeQuery`, có thể tách query builder thành component riêng và kiểm tra các tham số đầu vào/field/filter bằng unit test. Với Query DSL phức tạp, integration test trên Elasticsearch thật là bằng chứng tốt hơn việc chỉ so sánh một object builder nội bộ.

## 22. Kiểm thử save và delete reactive

Ví dụ kiểm tra save trả entity đã lưu:

```java
@Test
void createsProduct() {
    ProductDocument input = new ProductDocument("p-100", "Mouse");
    when(repository.save(input)).thenReturn(Mono.just(input));

    StepVerifier.create(service.create(input))
        .expectNext(input)
        .verifyComplete();

    verify(repository).save(input);
}
```

Với delete trả `Mono<Void>`:

```java
@Test
void deletesProduct() {
    when(repository.deleteById("p-100")).thenReturn(Mono.empty());

    StepVerifier.create(service.delete("p-100"))
        .verifyComplete();
}
```

Kiểu trả về chính xác của một số repository method phụ thuộc interface/version. Hãy dùng chữ ký thật của dependency; không ép mọi delete method thành `Mono<Boolean>` nếu API thực tế trả `Mono<Void>`.

## 23. Kiểm thử lazy execution và side effect

Một pipeline có side effect nên dùng `defer` nếu side effect cần xảy ra khi subscribe:

```java
AtomicInteger calls = new AtomicInteger();

Mono<Integer> result = Mono.defer(() ->
    Mono.just(calls.incrementAndGet())
);
```

Có thể xác nhận publisher chưa chạy trước subscription và mỗi subscription tạo một lần thực thi:

```java
assertThat(calls.get()).isZero();

StepVerifier.create(result)
    .expectNext(1)
    .verifyComplete();

assertThat(calls.get()).isEqualTo(1);

StepVerifier.create(result)
    .expectNext(2)
    .verifyComplete();

assertThat(calls.get()).isEqualTo(2);
```

Không phải mọi publisher đều cold. Một số publisher chia sẻ subscription hoặc phát nóng. Test nên hiểu semantics của nguồn dữ liệu thay vì mặc định mọi `Flux` đều thực thi lại từ đầu mỗi khi subscribe.

## 24. Kiểm thử retry không lặp side effect sai

Nếu một publisher ghi document và retry khi response lỗi, cần hiểu liệu lần ghi trước có thể đã thành công ở server nhưng response bị mất hay không. Retry có thể gửi cùng thao tác lần nữa.

Các test cần xem xét:

- ID document ổn định để upsert có tính idempotent.
- Không tạo duplicate khi retry.
- Chỉ retry lỗi tạm thời đã được chọn.
- Giới hạn số lần retry.
- Backoff có jitter trong production; virtual time trong test.
- Không retry version conflict với cùng token cũ.
- Error cuối cùng được truyền tới caller khi hết retry.

StepVerifier kiểm tra tín hiệu và số lần thử; mock/spy có thể đếm invocation. Integration test xác nhận trạng thái document cuối cùng sau retry.

## 25. Kiểm thử timeout và lỗi từ Elasticsearch client

Unit test có thể giả lập timeout bằng `Mono.error(new TimeoutException(...))` hoặc publisher `never().timeout(...)`. Nhưng nó không chứng minh timeout cấu hình ở reactive Elasticsearch client hoạt động đúng.

Integration test cần kiểm tra:

- Connection timeout.
- Response timeout.
- Elasticsearch trả lỗi 4xx/5xx.
- Cluster từ chối request do quá tải.
- Publisher truyền error tới service/controller.
- Cancellation được xử lý khi HTTP client đóng kết nối.

Không tạo test chờ một Elasticsearch server thật bị treo chỉ bằng `Thread.sleep`. Dùng test server/proxy hoặc cấu hình timeout có kiểm soát nếu cần xác minh tầng mạng.

## 26. Integration test với Elasticsearch thật

Mock không thể xác nhận mapping, analyzer, derived query, serialization hoặc server behavior. Nên có một số integration test chạy với Elasticsearch tương thích, thường dùng Testcontainers hoặc môi trường test cô lập.

Một cấu trúc test:

```text
JUnit test
   |
   v
Spring application context
   |
   v
ReactiveElasticsearchOperations / Repository
   |
   v
Elasticsearch test container
   |
   v
StepVerifier kiểm tra Mono/Flux
```

Ví dụ khung test:

```java
@SpringBootTest
class ProductRepositoryIntegrationTest {

    @Autowired
    ProductRepository repository;

    @Autowired
    ReactiveElasticsearchOperations operations;

    @Test
    void savesAndFindsProduct() {
        ProductDocument product = new ProductDocument("p-100", "Mouse");

        StepVerifier.create(repository.save(product))
            .assertNext(saved -> assertThat(saved.getId()).isEqualTo("p-100"))
            .verifyComplete();

        StepVerifier.create(repository.findById("p-100"))
            .assertNext(found -> assertThat(found.getName()).isEqualTo("Mouse"))
            .verifyComplete();
    }
}
```

Đây là khung minh họa. Test cần cấu hình Elasticsearch endpoint/container và index mapping phù hợp. GET theo ID có semantics realtime mặc định, còn test search phải xử lý refresh visibility.

### Dọn dữ liệu giữa các test

Mỗi test nên dùng ID duy nhất hoặc xóa dữ liệu test trước/sau khi chạy. Nếu test chạy song song, tránh dùng cùng index/document ID theo cách gây race. Có thể tạo index riêng theo test suite hoặc dùng prefix/namespace.

## 27. Search visibility và refresh trong integration test

Sau khi lưu document, GET theo ID có thể đọc document ngay; search query có thể chưa thấy cho tới khi refresh. Nếu test đang xác minh search, hãy đồng bộ rõ ràng:

- Dùng refresh policy `WAIT_UNTIL` cho write nếu API test hỗ trợ.
- Hoặc gọi refresh index qua `IndexOperations` phù hợp.
- Sau đó chạy search bằng `StepVerifier`.

Ví dụ ý tưởng với thao tác refresh:

```java
StepVerifier.create(repository.save(product))
    .expectNextCount(1)
    .verifyComplete();

// Refresh the test index using the index operations API for the
// Spring Data Elasticsearch version configured by the project.

StepVerifier.create(repository.findByName("Mouse"))
    .expectNextMatches(found -> found.getId().equals("p-100"))
    .verifyComplete();
```

Không dùng `Thread.sleep(1000)` để chờ refresh. Test dựa vào refresh API hoặc policy sẽ xác định hơn và ít phụ thuộc tốc độ CI.

## 28. Kiểm thử repository derived query

Reactive repository có thể khai báo query method:

```java
public interface ProductRepository
        extends ReactiveElasticsearchRepository<ProductDocument, String> {

    Flux<ProductDocument> findByStatus(ProductStatus status);

    Flux<ProductDocument> findByCategoryAndStatus(
        String category,
        ProductStatus status
    );
}
```

Unit test với mock chỉ xác nhận service gọi method. Integration test cần index fixture và gọi method thật để xác nhận Spring Data tạo query đúng, mapping field đúng và kết quả phù hợp.

Nếu method trả `Flux`, StepVerifier có thể xác nhận số lượng, thứ tự theo sort đã định nghĩa và điều kiện filter. Nếu thứ tự không được query bảo đảm, không viết test đòi thứ tự cố định; hãy kiểm tra theo tập hợp hoặc bổ sung sort rõ ràng.

## 29. Kiểm thử backpressure của service

Nếu service trả Flux lớn hoặc có operator concurrency, có thể test demand từng phần:

```java
StepVerifier.create(service.streamProducts(), 0)
    .expectSubscription()
    .thenRequest(5)
    .expectNextCount(5)
    .thenCancel()
    .verify(Duration.ofSeconds(3));
```

Test này xác nhận subscriber chỉ yêu cầu năm phần tử trước khi cancel. Nó không tự chứng minh Elasticsearch chỉ fetch đúng năm document; search page size, scroll/PIT và prefetch ở các tầng khác có thể khiến server/client đã lấy nhiều hơn.

Nếu mục tiêu là giới hạn request Elasticsearch, cần kiểm tra query/page size và số request qua client mock, metrics hoặc integration instrumentation.

## 30. Kiểm thử `flatMap` concurrency

Có thể dùng bộ đếm active operation để kiểm tra giới hạn concurrency của một pipeline:

```java
AtomicInteger active = new AtomicInteger();
AtomicInteger maximum = new AtomicInteger();

Function<Integer, Mono<Integer>> operation = value ->
    Mono.defer(() -> {
        int current = active.incrementAndGet();
        maximum.accumulateAndGet(current, Math::max);

        return Mono.delay(Duration.ofMillis(10))
            .map(ignored -> value)
            .doFinally(signal -> active.decrementAndGet());
    });

Flux<Integer> result = Flux.range(1, 20)
    .flatMap(operation, 4);

StepVerifier.create(result)
    .expectNextCount(20)
    .verifyComplete();

assertThat(maximum.get()).isLessThanOrEqualTo(4);
```

Nếu dùng delay thật, test có thể phụ thuộc scheduling. Có thể dùng virtual time với publisher được tạo trong supplier, hoặc dùng latch/TestPublisher để kiểm soát completion. Mục tiêu là đo số inner publisher đang hoạt động, không chỉ số thread.

## 31. Kiểm thử `Context` và correlation metadata

Nếu service cần lấy tenant/correlation ID từ Reactor Context, test cần xác nhận context được truyền tới đúng operator:

```java
Mono<String> result = Mono.deferContextual(context ->
    Mono.just(context.get("correlationId"))
);

StepVerifier.create(
        result,
        StepVerifierOptions.create()
            .withInitialContext(Context.of("correlationId", "req-123"))
    )
    .expectNext("req-123")
    .verifyComplete();
```

Khi service gọi nhiều publisher hoặc chuyển scheduler, hãy test propagation qua các operator quan trọng. Tránh phụ thuộc `ThreadLocal` trong code reactive nếu framework/context propagation chưa được cấu hình rõ.

## 32. Đặt tên scenario và làm test dễ đọc

`StepVerifierOptions` cho phép đặt scenario name để lỗi dễ nhận biết:

```java
StepVerifier.create(
        service.findByCategory("accessories"),
        StepVerifierOptions.create()
            .scenarioName("active products are emitted")
    )
    .expectNextMatches(product -> product.getStatus() == ProductStatus.ACTIVE)
    .verifyComplete();
```

Có thể dùng `as("description")` sau một expectation để đặt tên cho bước cụ thể trong report:

```java
StepVerifier.create(service.findById("p-100"))
    .expectNextMatches(product -> product.getId().equals("p-100"))
    .as("returns the requested product")
    .verifyComplete();
```

Đặt tên scenario theo hành vi nghiệp vụ giúp đọc lỗi CI nhanh hơn, đặc biệt khi có nhiều expectation trong một test.

## 33. Tránh những anti-pattern khi test reactive

### Gọi `.block()` để lấy kết quả

```java
ProductDocument product = service.findById("p-100").block();
```

Cách này biến test thành thao tác đồng bộ, che khuất semantics subscription và có thể block thread. Dùng StepVerifier để kiểm tra publisher trực tiếp.

### Tự gọi `.subscribe()` trong test rồi assert ngay

```java
AtomicReference<ProductDocument> result = new AtomicReference<>();
service.findById("p-100").subscribe(result::set);
assertThat(result.get()).isNotNull();
```

Đây là race condition vì callback có thể chưa chạy khi assertion được thực hiện. StepVerifier quản lý subscription và chờ terminal signal.

### Dùng `Thread.sleep()` để chờ publisher

Sleep làm test chậm và không xác định. Dùng virtual time cho operator dựa trên thời gian, hoặc StepVerifier chờ tín hiệu thực tế.

### Không đặt timeout

Publisher `never()` hoặc bug không complete có thể làm test treo. Đặt timeout phù hợp cho verification.

### Test quá nhiều logic trong một verifier

Một test nên mô tả một hành vi chính. Tách success, empty, error, retry và cancellation thành test riêng để lỗi dễ chẩn đoán.

### Mock Elasticsearch trong integration test

Nếu mục tiêu là kiểm tra mapping hoặc query, mock repository sẽ bỏ qua chính phần cần xác minh. Dùng Elasticsearch thật cho một nhóm test tích hợp nhỏ và tập trung.

### Giả định thứ tự của Flux

Nếu query không có sort, Elasticsearch không bảo đảm thứ tự ổn định. Không dùng `expectNext` theo thứ tự tùy ý; thêm sort hoặc so sánh tập giá trị.

## 34. Tổ chức test suite theo tầng

Một test suite cân bằng thường có ba lớp:

| Loại test | Công cụ | Phạm vi |
|---|---|---|
| Unit test service | Mockito + StepVerifier | Mapping, filter, fallback, error, retry, composition |
| Reactive operator test | StepVerifier + TestPublisher + PublisherProbe | Demand, cancellation, virtual time, branch subscription |
| Integration test | JUnit + Spring context + Elasticsearch test instance + StepVerifier | Mapping, repository query, save/delete/search, refresh và server behavior |

Unit test nên chạy nhanh và không phụ thuộc container. Integration test có thể chạy ít hơn nhưng xác nhận hành vi thực tế. Không cần khởi động Elasticsearch cho mọi test kiểm tra một `map` hoặc `switchIfEmpty` đơn giản.

## 35. Ví dụ service và test hoàn chỉnh

Service:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Mono<ProductDocument> getRequired(String id) {
        return repository.findById(id)
            .switchIfEmpty(Mono.error(new ProductNotFoundException(id)));
    }

    public Flux<ProductDocument> activeProducts(String category) {
        return repository.findByCategory(category)
            .filter(product -> product.getStatus() == ProductStatus.ACTIVE);
    }

    public Mono<ProductDocument> create(ProductDocument product) {
        return repository.save(product);
    }
}
```

Test:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ProductServiceTest {

    @Mock
    ProductRepository repository;

    ProductService service;

    @BeforeEach
    void setUp() {
        service = new ProductService(repository);
    }

    @Test
    void getRequiredEmitsProduct() {
        ProductDocument product = product("p-100", ProductStatus.ACTIVE);
        when(repository.findById("p-100")).thenReturn(Mono.just(product));

        StepVerifier.create(service.getRequired("p-100"))
            .assertNext(actual -> {
                assertThat(actual.getId()).isEqualTo("p-100");
                assertThat(actual.getStatus()).isEqualTo(ProductStatus.ACTIVE);
            })
            .verifyComplete();

        verify(repository).findById("p-100");
    }

    @Test
    void getRequiredEmitsNotFoundWhenRepositoryIsEmpty() {
        when(repository.findById("missing")).thenReturn(Mono.empty());

        StepVerifier.create(service.getRequired("missing"))
            .expectError(ProductNotFoundException.class)
            .verify();
    }

    @Test
    void activeProductsFiltersInactiveDocuments() {
        ProductDocument active = product("p-1", ProductStatus.ACTIVE);
        ProductDocument inactive = product("p-2", ProductStatus.INACTIVE);
        when(repository.findByCategory("accessories"))
            .thenReturn(Flux.just(active, inactive));

        StepVerifier.create(service.activeProducts("accessories"))
            .expectNext(active)
            .verifyComplete();
    }

    private ProductDocument product(String id, ProductStatus status) {
        ProductDocument product = new ProductDocument();
        product.setId(id);
        product.setStatus(status);
        return product;
    }
}
```

Đoạn code là mẫu minh họa; constructor, getter/setter và repository method cần khớp model thực tế của dự án. Test tập trung vào hành vi reactive: service phát đúng giá trị, chuyển empty thành not-found và lọc document inactive.

## 36. Quy trình viết một test StepVerifier

Khi viết test cho một publisher:

1. Tạo fixture nhỏ, xác định publisher cần kiểm tra.
2. Chuẩn bị dependency bằng mock hoặc test publisher nếu cần.
3. Dùng `StepVerifier.create(...)` hoặc `withVirtualTime(...)`.
4. Mô tả subscription/demand nếu hành vi backpressure quan trọng.
5. Kiểm tra giá trị, thứ tự hoặc predicate bằng các expectation phù hợp.
6. Kiểm tra terminal signal: complete, error hoặc cancel.
7. Gọi `verify...` để thực sự chạy kịch bản.
8. Đặt timeout cho test có khả năng chờ.
9. Assert side effect/dependency invocation sau verification.
10. Dùng integration test khi cần xác nhận Elasticsearch server behavior.

## 37. Kết luận

`StepVerifier` là công cụ chính để kiểm thử `Mono` và `Flux` vì nó subscribe vào publisher, điều khiển demand và xác nhận chuỗi tín hiệu Reactive Streams. Có thể dùng `expectNext`, `assertNext`, `expectError`, `verifyComplete`, `thenRequest` và `thenCancel` để kiểm tra dữ liệu, lỗi, backpressure và cancellation. `withVirtualTime` giúp kiểm tra delay, timeout và retry backoff mà không phải chờ thời gian thật.

`TestPublisher` cho phép chủ động điều khiển nguồn phát; `PublisherProbe` xác nhận một nhánh publisher có được subscribe hay không. Trong Spring Data Elasticsearch, dùng Mockito + StepVerifier cho logic service, rồi dùng integration test với Elasticsearch thật để kiểm tra repository query, mapping, persistence và refresh visibility. Tránh `.block()`, tự `subscribe()` rồi assert ngay hoặc `Thread.sleep()`; đặt timeout và kiểm tra đúng semantics về empty, error, ordering, retry và cancellation.

## Tài liệu tham khảo

- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor – StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [Project Reactor – TestPublisher API](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html)
- [Project Reactor – PublisherProbe API](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html)
- [Project Reactor – Virtual Time](https://projectreactor.io/docs/core/release/reference/testing.html#_manipulating_time)
- [Spring Data Elasticsearch – Reactive repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/reactive.html)
- [Spring Data Elasticsearch – Reactive template](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/reactive-template.html)
- [Spring Data Elasticsearch – Testing](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/testing.html)

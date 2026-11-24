# Dùng StepVerifier cho lỗi, subscription và thời gian trong luồng reactive

Trong ứng dụng Spring Cloud Circuit Breaker dùng Reactor, lời gọi được bảo vệ thường được biểu diễn bằng `Mono<T>` hoặc `Flux<T>`. Một publisher chỉ mô tả pipeline cho tới khi có subscriber; kết quả, lỗi, fallback và cancellation chỉ xuất hiện trong quá trình subscription. Vì vậy, kiểm thử reactive cần xác minh các tín hiệu của publisher và thời điểm chúng xảy ra, thay vì gọi phương thức rồi giả định công việc đã hoàn tất.

`StepVerifier` thuộc thư viện `reactor-test`. Nó đăng ký vào publisher và cho phép mô tả một kịch bản theo thứ tự: nhận subscription, yêu cầu dữ liệu, kiểm tra `onNext`, xác minh `onError` hoặc `onComplete`, chờ thời gian, rồi hủy subscription. Công cụ này đặc biệt hữu ích để kiểm tra lỗi, retry, timeout và fallback của `ReactiveCircuitBreaker` mà không phải tự quản lý callback `subscribe()`.

## Thêm reactor-test vào dự án

Khai báo `reactor-test` ở scope test. Nếu dự án dùng Spring Boot hoặc Spring Cloud BOM, để BOM quản lý phiên bản tương thích với Reactor đang có trong ứng dụng:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

Các ví dụ dưới đây dùng JUnit 5, Reactor và `StepVerifier`. Publisher được kiểm tra trực tiếp; không gọi `.subscribe()` thủ công trong test vì `StepVerifier` sẽ tạo subscription khi xác minh kịch bản.

## Kiểm tra giá trị và tín hiệu hoàn tất

Với một `Mono` thành công, dùng `expectNext` để kiểm tra giá trị và `verifyComplete` để xác nhận publisher phát `onComplete` ngay sau đó:

```java
Mono<String> source = Mono.just("catalog-ready");

StepVerifier.create(source)
        .expectNext("catalog-ready")
        .verifyComplete();
```

Với `Flux`, kiểm tra thứ tự và số lượng phần tử. `verifyComplete()` cũng xác nhận không còn phần tử nào khác trước tín hiệu hoàn tất:

```java
Flux<Integer> source = Flux.just(10, 20, 30);

StepVerifier.create(source)
        .expectNext(10)
        .expectNext(20, 30)
        .verifyComplete();
```

Các bước trong verifier là một kịch bản có thứ tự. Nếu publisher phát sai phần tử, phát thêm phần tử hoặc kết thúc bằng tín hiệu khác, test sẽ thất bại tại bước tương ứng. Có thể dùng `as("mô tả bước")` hoặc `StepVerifierOptions` với `scenarioName` để thông báo lỗi dễ đọc hơn trong test suite lớn.

## Xác minh lỗi và exception

Reactive publisher biểu diễn lỗi bằng tín hiệu `onError`. `expectError` kiểm tra kiểu exception; `expectErrorMatches` kiểm tra điều kiện; `expectErrorSatisfies` cho phép assertion chi tiết trên exception:

```java
Mono<Product> source = Mono.error(
        new CatalogUnavailableException("catalog timeout"));

StepVerifier.create(source)
        .expectErrorMatches(error ->
                error instanceof CatalogUnavailableException
                        && error.getMessage().contains("timeout"))
        .verify();
```

Nếu muốn kiểm tra exception cụ thể bằng assertion của JUnit:

```java
StepVerifier.create(source)
        .expectErrorSatisfies(error -> {
            assertInstanceOf(CatalogUnavailableException.class, error);
            assertEquals("catalog timeout", error.getMessage());
        })
        .verify();
```

Không dùng `expectNext` để kiểm tra một lỗi. Khi publisher phát `onError`, nó kết thúc ngay; không thể tiếp tục phát thêm `onNext` hoặc `onComplete` trong cùng subscription. Nếu ứng dụng dùng `onErrorResume` hoặc fallback để biến lỗi thành giá trị, test cần xác minh giá trị thay thế và tín hiệu hoàn tất, vì caller không còn nhận `onError` ban đầu.

## Kiểm tra thời điểm subscription và lazy evaluation

Tạo một `Mono` không đồng nghĩa với việc supplier đã chạy. Dùng `Mono.defer` và bộ đếm để xác minh công việc chỉ bắt đầu khi subscriber đăng ký:

```java
AtomicInteger executions = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    executions.incrementAndGet();
    return Mono.just("loaded");
});

assertEquals(0, executions.get()); // Chưa có subscription.

StepVerifier.create(source)
        .expectSubscription()
        .expectNext("loaded")
        .verifyComplete();

assertEquals(1, executions.get()); // Supplier đã chạy một lần.
```

`StepVerifier.create` tạo publisher verifier; subscription thực tế diễn ra khi test gọi `verifyComplete`, `verify` hoặc một phương thức xác minh tương ứng. Assertion trước bước verify xác nhận assembly chưa kích hoạt supplier.

Cold publisher thường thực thi lại cho mỗi subscriber. Có thể kiểm tra hành vi đó bằng hai kịch bản riêng:

```java
AtomicInteger calls = new AtomicInteger();
Mono<Integer> cold = Mono.defer(() -> Mono.just(calls.incrementAndGet()));

StepVerifier.create(cold)
        .expectNext(1)
        .verifyComplete();

StepVerifier.create(cold)
        .expectNext(2)
        .verifyComplete();

assertEquals(2, calls.get());
```

Điều này quan trọng khi kiểm tra `ReactiveCircuitBreaker`: mỗi subscription vào publisher cold có thể tạo một request dependency mới. Không giả định biến `Mono` được tạo một lần thì lời gọi HTTP cũng chỉ xảy ra một lần.

## Kiểm tra demand và backpressure

`StepVerifier.create(publisher, initialRequest)` cho phép chỉ định số phần tử yêu cầu ban đầu. Dùng `thenRequest(n)` để yêu cầu thêm dữ liệu và kiểm tra publisher tôn trọng demand:

```java
Flux<Integer> source = Flux.range(1, 3);

StepVerifier.create(source, 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(2)
        .expectNext(2, 3)
        .verifyComplete();
```

Kịch bản bắt đầu với demand bằng 0. Chỉ sau `thenRequest(1)` phần tử đầu tiên mới được yêu cầu; lần yêu cầu tiếp theo lấy hai phần tử còn lại. Kiểm tra demand hữu ích với `Flux` streaming, vì một consumer chậm không nên bị buộc nhận dữ liệu vượt quá khả năng xử lý.

## Kiểm tra cancellation

Caller có thể hủy subscription khi client ngắt kết nối, request bị hủy hoặc không còn cần dữ liệu. Dùng `thenCancel()` để xác minh publisher nhận cancellation:

```java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.interval(Duration.ofMillis(100))
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
        .expectNext(0L)
        .thenCancel()
        .verify();

assertTrue(cancelled.get());
```

Cancellation không phải `onComplete` hay `onError`. Khi subscriber hủy, publisher dừng phát cho subscriber đó và các operator/resource có cơ hội giải phóng tài nguyên. Với request được bảo vệ bằng Bulkhead hoặc HTTP client, cần kiểm tra cancellation có truyền tới nguồn và permit/tài nguyên có được giải phóng hay không.

## Dùng virtual time cho delay, retry và timeout

Test dựa trên `Thread.sleep` làm chậm suite và dễ không ổn định trên CI. `StepVerifier.withVirtualTime` thay scheduler Reactor được tạo trong phạm vi test để có thể tiến thời gian ảo mà không phải chờ thật. Publisher cần được tạo bên trong supplier truyền cho `withVirtualTime`; nếu tạo operator phụ thuộc scheduler trước đó, operator có thể đã giữ scheduler thật.

Ví dụ kiểm tra `Mono.delay` sau một phút mà không phải đợi một phút:

```java
StepVerifier.withVirtualTime(() -> Mono.delay(Duration.ofMinutes(1)))
        .expectSubscription()
        .expectNoEvent(Duration.ofSeconds(59))
        .thenAwait(Duration.ofSeconds(1))
        .expectNext(0L)
        .verifyComplete();
```

`expectSubscription()` được đặt trước `expectNoEvent()` vì subscription cũng là một tín hiệu. Sau khi xác nhận subscription, test tiến 59 giây và xác nhận chưa có dữ liệu; sau một giây nữa, `Mono.delay` phát `0L` rồi hoàn tất.

### Kiểm tra retry có backoff

Ví dụ dưới đây mô phỏng dependency lỗi hai lần rồi thành công. `Retry.backoff` chờ một giây trước lần thử thứ hai và hai giây trước lần thử thứ ba; virtual time giúp test hoàn tất nhanh:

```java
AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            int attempt = attempts.incrementAndGet();
            if (attempt < 3) {
                return Mono.error(new IOException("temporary failure"));
            }
            return Mono.just("recovered");
        }).retryWhen(Retry.backoff(2, Duration.ofSeconds(1)).jitter(0d))
)
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectNext("recovered")
        .verifyComplete();

assertEquals(3, attempts.get());
```

Publisher và `Retry` được tạo trong supplier của `withVirtualTime`, vì thế retry dùng scheduler ảo được cài đặt trước subscription. `jitter(0d)` làm khoảng backoff xác định để test không phụ thuộc độ ngẫu nhiên. Trong production, jitter thường hữu ích để tránh nhiều client retry đồng thời.

### Kiểm tra timeout reactive

`timeout(Duration)` phát lỗi nếu nguồn không phát tín hiệu trong thời hạn. Dùng virtual time để xác minh timeout xảy ra tại mốc dự kiến:

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(10))
                .timeout(Duration.ofSeconds(2))
)
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectError(TimeoutException.class)
        .verify();
```

Ở đây nguồn cần mười giây nhưng timeout chỉ cho phép hai giây, vì vậy subscriber nhận `TimeoutException`. Test này kiểm tra operator timeout của Reactor; nó không tự xác minh timeout ở HTTP client, `TimeLimiter` blocking hoặc đồng hồ nội bộ của mọi thư viện bên ngoài.

## Kiểm tra ReactiveCircuitBreaker và fallback

Spring Cloud Circuit Breaker cung cấp `ReactiveCircuitBreaker` để bọc publisher. Phương thức `run` nhận publisher nguồn và hàm fallback trả về publisher cùng kiểu phần tử:

```java
public Mono<Product> findProduct(String productId) {
    ReactiveCircuitBreaker breaker =
            circuitBreakerFactory.create("catalog");

    Mono<Product> request = Mono.defer(
            () -> catalogClient.findProduct(productId));

    return breaker.run(
            request,
            error -> Mono.just(Product.unavailable(productId))
    );
}
```

Test service bằng `StepVerifier` để xác nhận fallback tạo đúng kết quả:

```java
when(catalogClient.findProduct("p-10"))
        .thenReturn(Mono.error(new IOException("catalog offline")));

StepVerifier.create(catalogService.findProduct("p-10"))
        .assertNext(product -> {
            assertEquals("p-10", product.id());
            assertFalse(product.isAvailable());
        })
        .verifyComplete();

verify(catalogClient, times(1)).findProduct("p-10");
```

Kết quả fallback là `onNext` rồi `onComplete`, nên test dùng `assertNext` và `verifyComplete`, không dùng `expectError`. Nếu muốn caller nhận lỗi gốc, cấu hình không có fallback hoặc fallback phát lại lỗi và xác minh bằng `expectErrorMatches`.

Để kiểm tra nhánh nào thực sự được subscribe, có thể dùng `PublisherProbe` từ `reactor-test`:

```java
PublisherProbe<Product> fallbackProbe = PublisherProbe.of(
        Mono.just(Product.unavailable("p-10")));

Mono<Product> protectedCall = breaker.run(
        Mono.error(new IOException("catalog offline")),
        error -> fallbackProbe.mono()
);

StepVerifier.create(protectedCall)
        .assertNext(product -> assertFalse(product.isAvailable()))
        .verifyComplete();

fallbackProbe.assertWasSubscribed();
```

`PublisherProbe` có thể xác nhận fallback được subscribe, hoặc xác nhận publisher nguồn không được subscribe trong trường hợp breaker từ chối lời gọi. Khi kiểm tra trạng thái `OPEN`, hãy cấu hình breaker test với ngưỡng nhỏ và tạo trạng thái mở một cách xác định; không dựa vào thời gian ngẫu nhiên hoặc một breaker dùng chung từ test khác.

## Tách kiểm thử publisher khỏi kiểm thử state machine

`StepVerifier` xác minh hành vi reactive: tín hiệu, subscription, demand, cancellation và thời gian của scheduler Reactor. Nó không thay thế mọi kiểm thử của Resilience4j hoặc Spring context. Nên chia mục tiêu kiểm thử:

| Mục tiêu | Cách kiểm tra |
|---|---|
| Publisher phát đúng giá trị và hoàn tất | `expectNext`, `verifyComplete` |
| Publisher phát đúng exception | `expectError`, `expectErrorMatches`, `expectErrorSatisfies` |
| Nguồn chỉ chạy khi subscribe | `Mono.defer`/`Flux.defer` và bộ đếm |
| Demand và backpressure | `initialRequest`, `thenRequest` |
| Hủy subscription | `thenCancel`, `doOnCancel` hoặc kiểm tra resource cleanup |
| Delay, retry backoff, Reactor timeout | `withVirtualTime`, `thenAwait`, `expectNoEvent` |
| Nhánh fallback có được subscribe | `PublisherProbe` |
| Trạng thái `CLOSED`/`OPEN`/`HALF_OPEN` và metric | Kiểm tra instance Resilience4j, event hoặc metric với cấu hình test riêng |
| Wiring factory, auto-configuration và WebFlux | Spring integration test hoặc `WebTestClient` |

Virtual time chỉ thay thế scheduler Reactor mà test điều khiển. Nó không tự làm thời gian trôi qua trong HTTP server thật, database, thread sleep, scheduler riêng của thư viện khác hoặc đồng hồ của hệ thống bên ngoài. Khi test `waitDurationInOpenState` của Resilience4j, hãy dùng cơ chế clock/scheduler được phiên bản Resilience4j hỗ trợ hoặc cấu hình thời gian test riêng; không cho rằng `thenAwait` luôn làm mọi timer trong JVM tiến lên.

## Tránh các lỗi thường gặp

- **Tự gọi `subscribe()` trong test rồi kiểm tra bằng biến:** test mất quyền kiểm soát thứ tự tín hiệu và có thể kết thúc trước khi callback chạy. Dùng `StepVerifier` để quản lý subscription.
- **Tạo publisher trước `withVirtualTime`:** operator có thể giữ scheduler thật. Tạo toàn bộ chuỗi phụ thuộc thời gian trong supplier của `withVirtualTime`.
- **Dùng `expectNoEvent` trước `expectSubscription`:** subscription được xem là một sự kiện và làm assertion thất bại. Xác nhận subscription trước.
- **Nhầm fallback với thành công của dependency:** fallback có thể phát dữ liệu bình thường tới caller trong khi circuit breaker vẫn ghi nhận lỗi nguồn. Kiểm tra riêng publisher và metric/event của breaker.
- **Chờ bằng `Thread.sleep`:** làm test chậm và dễ flaky. Dùng virtual time cho operator Reactor có hỗ trợ scheduler ảo.
- **Không kiểm tra cancellation:** request bị hủy có thể vẫn giữ tài nguyên nếu cancellation không truyền tới nguồn. Thêm test `thenCancel` cho luồng dài hoặc thao tác có resource.
- **Chỉ mock factory:** mock không chứng minh cấu hình Resilience4j và state transition hoạt động. Bổ sung integration test với factory thật cho những hành vi cần xác minh.

## Một kịch bản kiểm thử hoàn chỉnh

Với một client catalog reactive, có thể tổ chức suite theo thứ tự sau:

1. Kiểm tra publisher thành công trả đúng `Product` và hoàn tất.
2. Kiểm tra publisher lỗi phát đúng exception khi không có fallback.
3. Kiểm tra `Mono.defer` không gọi client trước subscription và gọi đúng một lần khi subscribe.
4. Kiểm tra lỗi dependency được chuyển thành response fallback đúng hợp đồng.
5. Dùng `PublisherProbe` xác nhận fallback được subscribe và nguồn bị từ chối không được gọi khi breaker `OPEN`.
6. Dùng virtual time kiểm tra retry backoff và timeout của Reactor.
7. Kiểm tra cancellation giải phóng tài nguyên và không giữ permit Bulkhead sau khi subscriber hủy.
8. Dùng integration test riêng để xác nhận state transition, HALF_OPEN probe quota, event và metric của Resilience4j.

Một bài test reactive tốt mô tả chính xác subscriber quan sát được điều gì và khi nào. Kết hợp `StepVerifier` với `PublisherProbe`, virtual time và kiểm tra integration của circuit breaker giúp phát hiện lỗi trong pipeline, fallback và chính sách bảo vệ mà không phải dựa vào chờ thời gian thật hoặc callback bất đồng bộ khó kiểm soát.

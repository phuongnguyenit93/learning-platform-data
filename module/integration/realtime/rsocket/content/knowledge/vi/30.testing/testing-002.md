# Kiểm thử Mono, Flux và tín hiệu lỗi bằng StepVerifier

Trong ứng dụng RSocket dùng Spring và Project Reactor, handler thường trả về `Mono<T>` hoặc `Flux<T>`. `Mono` biểu diễn tối đa một phần tử; `Flux` biểu diễn không, một hoặc nhiều phần tử. Cả hai đều là publisher bất đồng bộ và có thể kết thúc bằng `onComplete`, kết thúc lỗi bằng `onError` hoặc bị consumer hủy bằng `cancel`. Vì vậy, kiểm thử reactive cần xác minh cả giá trị, thứ tự tín hiệu, lỗi, demand và cancellation.

`StepVerifier` thuộc thư viện `reactor-test`. Nó subscribe vào publisher, yêu cầu dữ liệu theo kịch bản và cho phép khai báo chuỗi tín hiệu mong đợi. Cách này phù hợp để kiểm tra service và RSocket handler mà không cần gọi `.block()` hoặc tự subscribe trong code production.

## 1. Thêm reactor-test vào dự án

Với Gradle, thêm dependency test:

```groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.junit.jupiter:junit-jupiter'
}
```

Spring Boot dependency management thường quản lý phiên bản Reactor tương thích. Nếu dự án dùng Spring Boot, giữ version alignment giữa `reactor-core` và `reactor-test`; không tự chọn hai phiên bản khác nhau.

Import thường dùng:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
```

`StepVerifier` là công cụ test, không phải operator dùng trong ứng dụng runtime. Không đưa `reactor-test` vào dependency production chỉ để xử lý publisher.

## 2. Publisher phát tín hiệu theo contract nào?

Reactive Streams định nghĩa ba loại tín hiệu từ publisher đến subscriber:

- `onNext(value)`: phát một phần tử.
- `onError(error)`: kết thúc bằng lỗi; sau tín hiệu này không có thêm `onNext` hoặc `onComplete`.
- `onComplete()`: kết thúc bình thường; sau tín hiệu này không có thêm phần tử.

Subscriber cũng gửi tín hiệu điều khiển:

- `onSubscribe(subscription)`: nhận subscription.
- `request(n)`: yêu cầu publisher phát tối đa thêm `n` phần tử.
- `cancel()`: hủy subscription và báo rằng consumer không cần dữ liệu nữa.

Một publisher chỉ có thể kết thúc bằng một trong hai tín hiệu terminal là `onComplete` hoặc `onError`. Cancellation là hành động từ phía subscriber; nó không phải một tín hiệu terminal mà publisher phát tới subscriber. `StepVerifier` giúp kiểm tra các hành vi này theo đúng thứ tự.

## 3. Kiểm thử Mono có giá trị

Với `Mono`, kịch bản phổ biến là một phần tử rồi complete:

```java
@Test
void returnsDeviceStatus() {
    Mono<DeviceStatus> result = Mono.just(
        new DeviceStatus("device-42", "ONLINE"));

    StepVerifier.create(result)
        .expectNextMatches(status ->
            status.deviceId().equals("device-42")
                && status.state().equals("ONLINE"))
        .verifyComplete();
}
```

`expectNextMatches` kiểm tra điều kiện trên phần tử. Nếu muốn so sánh toàn bộ object, dùng `expectNext(expected)`; DTO/record nên có `equals` phù hợp để assertion dễ đọc.

`verifyComplete()` xác nhận publisher phát đúng chuỗi phần tử đã khai báo rồi kết thúc bình thường. Nếu publisher phát thêm phần tử, phát lỗi hoặc không kết thúc, verifier sẽ thất bại (hoặc chờ đến timeout của test).

## 4. Kiểm thử Mono rỗng

`Mono.empty()` hoàn tất bình thường nhưng không phát phần tử:

```java
@Test
void returnsEmptyWhenDeviceDoesNotExist() {
    Mono<DeviceStatus> result = Mono.empty();

    StepVerifier.create(result)
        .verifyComplete();
}
```

Không dùng `expectNext(null)`: Reactive Streams không cho phép `null` làm phần tử. Nếu nghiệp vụ cần biểu diễn không tìm thấy, hãy dùng `Mono.empty()`, một kiểu kết quả rõ ràng hoặc lỗi domain theo contract.

Với service tra cứu, nên kiểm thử riêng hai trường hợp: có dữ liệu và không có dữ liệu. Một `Mono.empty()` không giống `Mono.error(...)`; client có thể cần xử lý hai trường hợp khác nhau.

## 5. Kiểm thử Mono phát lỗi

Có thể kiểm tra loại exception:

```java
@Test
void rejectsInvalidDeviceId() {
    Mono<DeviceStatus> result = Mono.error(
        new IllegalArgumentException("deviceId is required"));

    StepVerifier.create(result)
        .expectError(IllegalArgumentException.class)
        .verify();
}
```

Khi cần kiểm tra message hoặc thuộc tính domain, dùng `expectErrorMatches` hoặc `expectErrorSatisfies`:

```java
StepVerifier.create(service.find("unknown"))
    .expectErrorSatisfies(error -> {
        assertThat(error).isInstanceOf(DeviceNotFoundException.class);
        assertThat(error.getMessage()).contains("unknown");
    })
    .verify();
```

Không chỉ kiểm tra rằng “có lỗi”. Với contract public, cần xác minh lỗi có đúng loại và không để lộ thông tin nội bộ như SQL, token hoặc stack trace cho caller.

## 6. Kiểm thử Flux và thứ tự phần tử

Với `Flux`, dùng `expectNext` để xác minh thứ tự:

```java
@Test
void emitsTelemetryInSequence() {
    Flux<Integer> result = Flux.just(10, 20, 30);

    StepVerifier.create(result)
        .expectNext(10)
        .expectNext(20, 30)
        .verifyComplete();
}
```

Các assertion hữu ích:

| Assertion | Mục đích |
|---|---|
| `expectNext(value...)` | Kiểm tra giá trị và thứ tự chính xác |
| `assertNext(consumer)` | Chạy assertion phức tạp trên phần tử kế tiếp |
| `expectNextMatches(predicate)` | Kiểm tra phần tử theo điều kiện |
| `expectNextCount(n)` | Bỏ qua và xác nhận có đúng `n` phần tử |
| `expectNextSequence(iterable)` | Xác minh một chuỗi phần tử |
| `expectComplete()` | Xác minh tín hiệu complete ở vị trí hiện tại |
| `verifyComplete()` | Xác minh complete sau các assertion đã khai báo |

Ví dụ dùng `assertNext`:

```java
StepVerifier.create(telemetryService.watch("device-42").take(2))
    .assertNext(point -> {
        assertThat(point.deviceId()).isEqualTo("device-42");
        assertThat(point.value()).isPositive();
    })
    .assertNext(point ->
        assertThat(point.sequence()).isGreaterThan(0))
    .verifyComplete();
```

`take(2)` làm publisher hoàn tất sau hai phần tử được nhận. Nếu cần kiểm thử một stream realtime không tự complete, hãy kiểm thử cancellation và lifecycle riêng thay vì mong `verifyComplete()` tự kết thúc.

## 7. Kiểm thử thứ tự và số lượng tín hiệu

Publisher có thể phát đúng các giá trị nhưng sai số lượng hoặc phát thừa. `StepVerifier` giúp phát hiện điều này:

```java
StepVerifier.create(Flux.range(1, 3))
    .expectNext(1, 2, 3)
    .expectComplete()
    .verify();
```

Nếu nguồn phát thêm phần tử thứ tư, verifier sẽ báo sai vì sau `expectComplete()` nó chờ terminal signal. Nếu nguồn phát thiếu phần tử, bước `expectNext` tương ứng không thể hoàn tất và test sẽ timeout.

Khi chỉ quan tâm số lượng:

```java
StepVerifier.create(Flux.range(1, 100))
    .expectNextCount(100)
    .verifyComplete();
```

Không dùng `expectNextCount` nếu thứ tự hoặc nội dung từng phần tử là một phần của contract; khi đó hãy kiểm tra giá trị cụ thể hoặc dùng `assertNext`.

## 8. Kiểm thử demand và backpressure

Mặc định `StepVerifier.create(publisher)` yêu cầu dữ liệu ban đầu không giới hạn. Để kiểm tra publisher có tôn trọng demand, tạo verifier với initial request bằng `0`, rồi yêu cầu từng phần tử:

```java
@Test
void emitsOnlyWhenDemandArrives() {
    StepVerifier.create(Flux.range(1, 3), 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(2)
        .expectNext(2, 3)
        .verifyComplete();
}
```

`thenRequest(n)` gửi thêm demand. Test này xác minh subscriber chỉ nhận dữ liệu khi đã yêu cầu. Nó hữu ích cho `Flux` được tạo từ queue, event source hoặc adapter cần tuân thủ Reactive Streams.

Nếu cần kiểm tra chưa có phần tử nào được phát khi demand bằng 0, có thể dùng `expectNoEvent(Duration)` sau `expectSubscription()`:

```java
StepVerifier.create(Flux.range(1, 3), 0)
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(10))
    .thenRequest(1)
    .expectNext(1)
    .thenCancel()
    .verify();
```

Ví dụ dùng nguồn đồng bộ `range`, nên không phát phần tử khi demand vẫn bằng 0. Không dùng `Flux.interval` để minh họa tình huống này: interval có thể phát tick khi chưa có demand và kết thúc bằng lỗi overflow thay vì giữ tick trong một hàng đợi.

Lưu ý: `expectNoEvent` xem cả subscription là một event. Vì vậy nếu dùng nó để xác minh khoảng không có tín hiệu, hãy gọi `expectSubscription()` trước. `thenAwait` chỉ chờ/tiến thời gian, không tự khẳng định rằng không có tín hiệu trong khoảng đó.

## 9. Kiểm thử cancellation

Stream realtime thường chỉ kết thúc khi client hủy, connection đóng hoặc server phát lỗi. Khi client không còn quan tâm dữ liệu, cancellation cần được truyền tới nguồn để giải phóng tài nguyên.

```java
@Test
void cancelsUpstreamWhenClientLeavesStream() {
    AtomicBoolean cancelled = new AtomicBoolean();

    StepVerifier.withVirtualTime(() ->
            Flux.interval(Duration.ofMillis(100))
            .doOnCancel(() -> cancelled.set(true)))
        .thenAwait(Duration.ofMillis(250))
        .expectNext(0L, 1L)
        .thenCancel()
        .verify();

    assertThat(cancelled).isTrue();
}
```

Publisher có timer được tạo bên trong supplier để virtual scheduler thay thế scheduler thời gian trước khi subscription bắt đầu. `thenCancel()` gửi cancel thay vì chờ complete. `doOnCancel` hữu ích để kiểm tra cleanup được kích hoạt, nhưng nếu nguồn có tài nguyên bên ngoài, hãy xác minh thêm tài nguyên đó thực sự được đóng hoặc subscription downstream được dispose.

## 10. Kiểm thử lỗi được ánh xạ và phục hồi

Service có thể chuyển lỗi kỹ thuật thành lỗi domain bằng `onErrorMap`:

```java
Mono<DeviceStatus> result = repository.findById("device-42")
    .onErrorMap(DataAccessException.class,
        error -> new DeviceStoreException("Cannot load device", error));

StepVerifier.create(result)
    .expectError(DeviceStoreException.class)
    .verify();
```

Với `onErrorResume`, service có thể dùng fallback khi lỗi thuộc nhóm cho phép:

```java
Mono<DeviceStatus> result = remoteClient.status("device-42")
    .onErrorResume(TimeoutException.class,
        error -> cache.findStatus("device-42"));

StepVerifier.create(result)
    .expectNextMatches(status -> status.source().equals("cache"))
    .verifyComplete();
```

Test cần xác minh fallback chỉ chạy với lỗi đã định nghĩa. Không nên fallback mọi `Throwable`, vì có thể che giấu lỗi lập trình, lỗi xác thực hoặc lỗi dữ liệu.

## 11. Kiểm thử retry có kiểm soát

Retry tạo subscription mới cho nguồn. Hãy kiểm tra số lần gọi và loại lỗi được retry:

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    int attempt = attempts.incrementAndGet();
    if (attempt < 3) {
        return Mono.error(new TransientServiceException());
    }
    return Mono.just("ok");
}).retryWhen(Retry.max(2)
    .filter(TransientServiceException.class::isInstance));

StepVerifier.create(source)
    .expectNext("ok")
    .verifyComplete();

assertThat(attempts).hasValue(3);
```

`Mono.defer` bảo đảm counter tăng ở mỗi subscription. `Retry.max(2)` cho phép tối đa hai lần retry sau lần gọi đầu tiên, do đó tổng số attempt tối đa là ba. `filter` giới hạn retry vào lỗi transient đã chọn.

Không retry mặc định mọi lỗi RSocket. Lỗi authorization, invalid route, payload không hợp lệ hoặc business rejection thường không tự hết khi gọi lại. Với command có side effect, retry chỉ an toàn khi có idempotency key hoặc cơ chế tra cứu trạng thái operation.

## 12. Kiểm thử timeout bằng virtual time

Không cần chờ thật nhiều giây để kiểm thử timeout. `withVirtualTime` thay scheduler thời gian của Reactor bằng virtual scheduler:

```java
@Test
void timesOutWhenSourceDoesNotRespond() {
    StepVerifier.withVirtualTime(() ->
            Mono.<String>never()
                .timeout(Duration.ofSeconds(5)))
        .thenAwait(Duration.ofSeconds(5))
        .expectError(TimeoutException.class)
        .verify();
}
```

Publisher phải được tạo bên trong supplier của `withVirtualTime`. Nếu tạo `Flux.interval` hoặc `Mono.delay` trước khi gọi verifier, nó có thể đã giữ scheduler thật và không phản ứng với virtual time.

Virtual time chỉ điều khiển scheduler mà Reactor test có thể thay thế. Nó không làm cho JDBC, socket, `Thread.sleep` hoặc một thư viện blocking chạy nhanh hơn. Với các thao tác blocking, hãy mock dependency hoặc dùng timeout thật có giới hạn phù hợp trong integration test.

## 13. Kiểm thử retry backoff bằng virtual time

Retry có delay cần được kiểm thử mà không chờ thời gian thực:

```java
@Test
void retriesWithBackoffAndThenFails() {
    AtomicInteger attempts = new AtomicInteger();

    StepVerifier.withVirtualTime(() ->
            Mono.defer(() -> {
                attempts.incrementAndGet();
                return Mono.<String>error(new TransientServiceException());
            }).retryWhen(Retry.backoff(2, Duration.ofSeconds(1))
                .jitter(0)
                .filter(TransientServiceException.class::isInstance)))
        .thenAwait(Duration.ofSeconds(3))
        .expectError(TransientServiceException.class)
        .verify();

    assertThat(attempts).hasValue(3);
}
```

Ví dụ tắt jitter để thời gian retry có thể dự đoán trong test. `Retry.backoff(2, 1s)` có một lần gọi đầu và tối đa hai lần retry với delay tăng dần. Tạo toàn bộ pipeline bên trong supplier để retry scheduler được virtualized.

Nếu cấu hình retry có `onRetryExhaustedThrow`, hãy kiểm tra loại exception cuối cùng theo contract thực tế. Reactor có thể bọc lỗi gốc bằng exception biểu thị retry đã cạn nếu không cấu hình cách phát lỗi cuối.

## 14. Dùng StepVerifierOptions để đặt tên kịch bản và demand

Với test phức tạp, `StepVerifierOptions` giúp đặt tên scenario và cấu hình request ban đầu:

```java
StepVerifier.create(
        telemetryService.watch("device-42"),
        StepVerifierOptions.create()
            .scenarioName("telemetry stream emits ordered events")
            .initialRequest(0))
    .expectSubscription()
    .thenRequest(2)
    .expectNextCount(2)
    .thenCancel()
    .verify();
```

Scenario name giúp thông báo lỗi dễ định vị trong suite lớn. `initialRequest(0)` cho phép test điều khiển demand tường minh. Khi test không liên quan backpressure, dùng initial request mặc định để kịch bản gọn hơn.

## 15. Kiểm thử Reactor Context

Ứng dụng reactive thường lưu tenant, security context hoặc correlation data trong Reactor Context. Đổi thread bằng `publishOn`/`subscribeOn` không có nghĩa context sẽ biến mất nếu pipeline được xây dựng theo đúng cơ chế Reactor Context.

```java
@Test
void readsTenantFromReactorContext() {
    Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get("tenantId")))
        .contextWrite(Context.of("tenantId", "tenant-a"));

    StepVerifier.create(result)
        .expectAccessibleContext()
        .contains("tenantId", "tenant-a")
        .then()
        .expectNext("tenant-a")
        .verifyComplete();
}
```

`expectAccessibleContext()` xác minh context có thể được truy cập tại subscription. Có thể dùng `expectNoAccessibleContext()` khi contract yêu cầu publisher không nhận context. Với Spring Security, kiểm thử principal qua `ReactiveSecurityContextHolder` hoặc test support của Spring Security thay vì giả định `ThreadLocal` có mặt trên mọi scheduler.

## 16. Dùng TestPublisher để điều khiển tín hiệu nguồn

`TestPublisher` cho phép test chủ động phát phần tử, complete hoặc error. Nó hữu ích khi cần kiểm soát thời điểm nguồn phát dữ liệu:

```java
@Test
void mapsValuesFromAnExternalPublisher() {
    TestPublisher<Integer> source = TestPublisher.create();

    Flux<String> result = source.flux()
        .map(value -> "value-" + value);

    StepVerifier.create(result)
        .then(() -> source.emit(1, 2))
        .expectNext("value-1", "value-2")
        .verifyComplete();
}
```

`emit(...)` phát các phần tử rồi complete. Nếu muốn phát từng phần tử và điều khiển terminal signal riêng, dùng `next(...)`, `complete()` hoặc `error(...)`. `TestPublisher` cũng có chế độ tuân thủ và không tuân thủ Reactive Streams; chỉ dùng chế độ non-compliant khi chủ đích kiểm thử cách code phản ứng với publisher vi phạm contract.

## 17. Dùng PublisherProbe kiểm tra nhánh fallback

Giá trị cuối cùng đôi khi không đủ để biết một nhánh publisher có được subscribe hay không. `PublisherProbe` cho phép xác minh nhánh được subscribe, request hoặc cancel:

```java
@Test
void subscribesToFallbackWhenPrimaryIsEmpty() {
    PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("cached"));

    Mono<String> result = Mono.<String>empty()
        .switchIfEmpty(fallback.mono());

    StepVerifier.create(result)
        .expectNext("cached")
        .verifyComplete();

    fallback.assertWasSubscribed();
    fallback.assertWasRequested();
    fallback.assertWasNotCancelled();
}
```

Probe đặc biệt hữu ích khi test `switchIfEmpty`, `onErrorResume`, cache hoặc nhánh lazy. Nó giúp phân biệt “đã trả về đúng giá trị” với “đã đi qua đúng nhánh thực thi”.

## 18. Kiểm thử lỗi trong RSocket handler

Spring RSocket handler thường trả `Mono` hoặc `Flux`. Có thể gọi trực tiếp handler để kiểm tra contract reactive mà không cần mở socket:

```java
@Test
void mapsDeviceNotFoundToDomainError() {
    when(deviceService.getStatus("missing"))
        .thenReturn(Mono.error(new DeviceNotFoundException("missing")));

    Mono<DeviceStatus> result = handler.status(
        new DeviceQuery("missing"));

    StepVerifier.create(result)
        .expectError(DeviceNotFoundException.class)
        .verify();
}
```

Ví dụ này giả định handler gọi service reactive và test dùng mock framework như Mockito. Nó kiểm tra logic mapping của handler; nó không kiểm tra routing metadata, serialization, transport, authentication interceptor hoặc kết nối TCP/WebSocket.

Với request-stream:

```java
@Test
void streamsTelemetryUntilCancelled() {
    Flux<TelemetryPoint> result = handler.watch(
        new TelemetryQuery("device-42"));

    StepVerifier.create(result)
        .expectNextCount(2)
        .thenCancel()
        .verify();
}
```

Nếu stream là vô hạn, test phải có điểm dừng rõ ràng: giới hạn bằng `take`, hủy bằng `thenCancel`, hoặc điều khiển nguồn bằng `TestPublisher`. Không gọi `verifyComplete()` với một stream được thiết kế để sống mãi.

## 19. Kiểm thử lỗi transport và lỗi nghiệp vụ ở các tầng khác nhau

StepVerifier có thể kiểm tra publisher phát lỗi, nhưng không tự phân loại lỗi đó có đến từ transport RSocket hay từ service. Nên tách các nhóm test:

| Tầng | Ví dụ | Công cụ phù hợp |
|---|---|---|
| Publisher/service | Validation error, empty result, fallback, retry | StepVerifier, Mockito/TestPublisher |
| Handler | Mapping DTO và domain error thành publisher | StepVerifier với mock service |
| Messaging/security | Route, metadata, authorization, codec | Spring integration test và RSocket client/server |
| Transport | TCP/WebSocket connect, close, timeout, disconnect | Integration test với server thật hoặc test transport |
| Resilience | Reconnect, resume, cancellation, retry sau lỗi mạng | Integration/fault-injection test |

Nếu integration test xác minh lỗi qua `RSocketRequester`, hãy kiểm tra exception/error code mà client thực sự nhận được; lỗi domain có thể được encode thành application error theo cấu hình server. Không giả định exception class ở server luôn được truyền nguyên vẹn qua wire.

## 20. Đặt timeout cho verifier để tránh test treo

`verify()` chờ publisher hoàn tất theo kịch bản. Với publisher không kết thúc hoặc test bị lỗi, thời gian chờ mặc định có thể khiến suite chạy lâu. Có thể đặt timeout riêng:

```java
StepVerifier.create(Mono.delay(Duration.ofMillis(10)))
    .expectNext(0L)
    .verifyComplete();
```

Trong suite cần giới hạn thời gian, dùng `verify(Duration)`:

```java
StepVerifier.create(service.find("device-42"))
    .expectNextCount(1)
    .expectComplete()
    .verify(Duration.ofSeconds(2));
```

Hoặc cấu hình timeout mặc định một lần trong test setup bằng `StepVerifier.setDefaultTimeout(...)`. Đừng đặt timeout quá ngắn đến mức test flaky trên CI. Timeout verifier là giới hạn thời gian test chờ; nó không thay thế timeout nghiệp vụ của service hoặc timeout của RSocket request.

## 21. Những lỗi thường gặp khi dùng StepVerifier

- Gọi `.block()` trước khi đưa publisher vào verifier, khiến test không còn kiểm tra reactive pipeline.
- Gọi `subscribe()` thủ công trong test rồi mới dùng StepVerifier, tạo hai subscription khác nhau.
- Mong `Mono.empty()` phát `null`.
- Dùng `verifyComplete()` với `Flux` realtime không bao giờ complete.
- Quên `thenCancel()` sau khi kiểm tra một phần stream vô hạn.
- Tạo timer publisher trước `withVirtualTime`, khiến scheduler thật được sử dụng.
- Dùng `thenAwait` rồi tưởng nó đã khẳng định không có signal; cần `expectNoEvent` khi muốn assertion đó.
- Gọi `expectNoEvent` trước khi tiêu thụ `onSubscribe`.
- Không đặt timeout, làm test chờ vô hạn khi publisher bị treo.
- Chỉ kiểm tra lỗi tồn tại mà không kiểm tra loại và nội dung domain cần thiết.
- Dùng retry cho mọi exception, kể cả lỗi không thể phục hồi hoặc command không idempotent.
- Dùng unit test handler để kết luận transport, codec và security đã hoạt động.

## 22. Quy trình viết một StepVerifier test

1. Xác định contract của publisher: giá trị, số lượng, thứ tự và terminal signal.
2. Tạo publisher lazy; mock dependency nếu cần điều khiển kết quả.
3. Chọn `StepVerifier.create` hoặc `withVirtualTime` theo đặc tính thời gian.
4. Đặt initial request nếu cần kiểm thử backpressure.
5. Viết assertion cho phần tử, lỗi, complete hoặc cancellation theo thứ tự.
6. Dùng `verifyComplete`, `verify` hoặc `verify(Duration)` để chạy kịch bản.
7. Assert side effect, số lần gọi, nhánh fallback và cleanup bên ngoài verifier.
8. Giữ integration test riêng cho route, metadata, security và transport.

## 23. Quy tắc thiết kế

1. Dùng StepVerifier để kiểm tra tín hiệu reactive thay vì gọi `block()`.
2. Phân biệt `onNext`, `onComplete`, `onError` và cancellation.
3. Kiểm tra cả `Mono` có giá trị, rỗng và lỗi.
4. Kiểm tra thứ tự, số lượng và nội dung phần tử của `Flux`.
5. Dùng initial request và `thenRequest` để kiểm tra demand/backpressure.
6. Dùng `thenCancel` để xác minh stream có thể dừng và cleanup được kích hoạt.
7. Dùng `withVirtualTime` cho delay, interval, timeout và retry backoff; tạo publisher bên trong supplier.
8. Dùng `expectErrorMatches`/`expectErrorSatisfies` để xác minh lỗi domain.
9. Dùng TestPublisher và PublisherProbe khi cần điều khiển nguồn hoặc xác minh nhánh lazy.
10. Kiểm tra Reactor Context nếu handler phụ thuộc tenant, principal hoặc trace context.
11. Đặt timeout cho verifier để test không treo vô hạn.
12. Kết hợp unit test publisher với integration test RSocket cho routing, codec, security và transport.

`StepVerifier` biến contract của `Mono` và `Flux` thành một kịch bản tín hiệu có thể đọc và kiểm chứng. Khi test xác minh đúng giá trị, thứ tự, demand, lỗi, complete và cancellation, các service/handler RSocket có thể giữ hành vi reactive ổn định hơn. Những phần phụ thuộc vào protocol như routing, metadata, authentication và TCP/WebSocket vẫn cần integration test riêng để xác nhận toàn bộ đường đi trên wire.

# Kiểm thử nguồn rỗng, nguồn lỗi và nguồn không kết thúc

Một publisher reactive không chỉ phát dữ liệu. Nó còn có thể hoàn tất bình thường mà không phát phần tử, kết thúc bằng lỗi hoặc tiếp tục tồn tại mà không phát bất kỳ tín hiệu kết thúc nào. Ba hành vi này ảnh hưởng trực tiếp tới cách service, controller và pipeline xử lý request. Nếu chỉ kiểm thử trường hợp có dữ liệu, nhiều lỗi quan trọng sẽ bị bỏ sót: một `Mono` rỗng bị hiểu nhầm thành 404, lỗi bị nuốt thành hoàn tất, hoặc một nguồn không bao giờ kết thúc giữ request và tài nguyên vô thời hạn.

Trong Project Reactor, `StepVerifier` cho phép kiểm tra chính xác chuỗi tín hiệu mà subscriber quan sát được. `TestPublisher` tạo nguồn có thể điều khiển trong test; `PublisherProbe` xác minh nhánh publisher thay thế có được subscribe, request hoặc cancel hay không. Kết hợp các công cụ này giúp kiểm thử cả hành vi bình thường lẫn những đường biên quan trọng của ứng dụng reactive.

## 1. Phân biệt ba trạng thái của publisher

Reactive Streams định nghĩa các tín hiệu chính mà subscriber nhận được: `onSubscribe`, không hoặc nhiều `onNext`, sau đó là đúng một tín hiệu kết thúc `onComplete` hoặc `onError`. Publisher cũng có thể chưa phát tín hiệu kết thúc trong khoảng thời gian quan sát.

| Trạng thái | Ví dụ Reactor | Tín hiệu quan sát | Ý nghĩa |
| --- | --- | --- | --- |
| Rỗng | `Mono.empty()`, `Flux.empty()` | `onSubscribe`, `onComplete` | Hoàn tất bình thường, không có phần tử |
| Lỗi | `Mono.error(e)`, `Flux.error(e)` | `onSubscribe`, `onError(e)` | Kết thúc bất thường với nguyên nhân lỗi |
| Không kết thúc | `Mono.never()`, `Flux.never()` | `onSubscribe`, không có `onNext`/terminal signal | Subscription tiếp tục mở cho tới khi bị hủy hoặc nguồn tự thay đổi |

Nguồn rỗng không phải nguồn lỗi. Nguồn không kết thúc cũng không phải nguồn lỗi; nó chỉ chưa phát tín hiệu nào để kết thúc. Nếu cần giới hạn thời gian chờ, ứng dụng phải áp dụng timeout hoặc cơ chế hủy phù hợp.

```text
Rỗng:             onSubscribe ---------------- onComplete
Lỗi:              onSubscribe ---------------- onError(error)
Không kết thúc:   onSubscribe ---------------- (không có tín hiệu tiếp theo)
```

Với `Mono<T>`, publisher có thể phát tối đa một phần tử. Với `Flux<T>`, publisher có thể phát nhiều phần tử trước complete hoặc error. Một `Flux` cũng có thể hoàn tất rỗng hoặc không bao giờ kết thúc.

## 2. Kiểm thử nguồn rỗng bằng StepVerifier

`StepVerifier` mô tả các tín hiệu mà test mong đợi theo đúng thứ tự. Với nguồn rỗng, dùng `verifyComplete()`:

```java
@Test
void monoEmptyCompletesWithoutValue() {
    StepVerifier.create(Mono.<String>empty())
        .verifyComplete();
}

@Test
void fluxEmptyCompletesWithoutValue() {
    StepVerifier.create(Flux.<String>empty())
        .verifyComplete();
}
```

Hai test xác nhận publisher hoàn tất mà không phát `onNext`. Không dùng `expectNext` cho trường hợp này. Nếu pipeline có kiểu `Mono<Void>`, `verifyComplete()` cũng là cách kiểm tra thành công vì `Mono<Void>` không phát payload.

Nguồn có thể trở nên rỗng sau khi lọc:

```java
Flux<Integer> positiveValues = Flux.just(-3, -1, 0)
    .filter(value -> value > 0);

StepVerifier.create(positiveValues)
    .verifyComplete();
```

Test này quan trọng vì publisher ban đầu có dữ liệu nhưng kết quả của pipeline không có phần tử. Hãy kiểm tra trạng thái sau toàn bộ các operator mà ứng dụng thực sự trả cho caller, thay vì chỉ kiểm tra nguồn ban đầu.

## 3. Kiểm thử defaultIfEmpty và switchIfEmpty

Khi empty là một trạng thái nghiệp vụ hợp lệ, pipeline có thể thay nó bằng giá trị mặc định hoặc một publisher dự phòng:

```java
Mono<String> displayName = userRepository.findName(userId)
    .defaultIfEmpty("Khách");

StepVerifier.create(displayName)
    .expectNext("Khách")
    .verifyComplete();
```

`defaultIfEmpty` phát một giá trị mặc định nếu nguồn hoàn tất mà không phát phần tử. `switchIfEmpty` đăng ký publisher thay thế trong trường hợp đó:

```java
Mono<User> user = userRepository.findById(userId)
    .switchIfEmpty(Mono.defer(() -> userRepository.createGuest(userId)));
```

Dùng `Mono.defer` khi muốn chỉ tạo publisher dự phòng sau khi biết nguồn chính rỗng. Điều này cũng tránh thực thi sớm một lời gọi có tác dụng phụ trong lúc lắp ráp pipeline.

`PublisherProbe` giúp xác minh nhánh dự phòng thực sự được subscribe:

```java
@Test
void subscribesToFallbackWhenSourceIsEmpty() {
    PublisherProbe<String> fallback = PublisherProbe.of(Mono.just("fallback"));

    Mono<String> result = Mono.<String>empty()
        .switchIfEmpty(fallback.mono());

    StepVerifier.create(result)
        .expectNext("fallback")
        .verifyComplete();

    fallback.assertWasSubscribed();
    fallback.assertWasRequested();
}
```

Nên có test đối chứng khi nguồn chính có dữ liệu để xác minh fallback không được subscribe:

```java
@Test
void doesNotSubscribeToFallbackWhenSourceHasValue() {
    PublisherProbe<String> fallback = PublisherProbe.of(Mono.just("fallback"));

    StepVerifier.create(Mono.just("primary").switchIfEmpty(fallback.mono()))
        .expectNext("primary")
        .verifyComplete();

    fallback.assertWasNotSubscribed();
}
```

Nếu `Mono<Void>` hoàn tất thành công, nó cũng không phát `onNext`. Vì vậy, `switchIfEmpty` đặt sau `Mono<Void>` sẽ xem completion thành công đó là empty và kích hoạt fallback. Không dùng `switchIfEmpty` để kiểm tra thành công của một thao tác completion-only.

## 4. Empty trong phép kết hợp nhiều publisher

`Mono.zip` cần mỗi nguồn phát một phần tử để tạo tuple. Nếu một nguồn hoàn tất rỗng trước khi có đủ phần tử, kết quả zip có thể hoàn tất rỗng và không phát tuple:

```java
Mono<Tuple2<String, Integer>> combined = Mono.zip(
    Mono.just("order-42"),
    Mono.<Integer>empty()
);

StepVerifier.create(combined)
    .verifyComplete();
```

Nếu mỗi trường dữ liệu đều bắt buộc, hãy chuyển empty thành lỗi hoặc giá trị miền nghiệp vụ rõ ràng trước khi zip:

```java
Mono<Customer> customer = customerRepository.findById(customerId)
    .switchIfEmpty(Mono.error(new CustomerNotFoundException(customerId)));

Mono<PaymentStatus> payment = paymentClient.status(orderId)
    .defaultIfEmpty(PaymentStatus.unavailable());

Mono<OrderDetails> details = Mono.zip(customer, payment)
    .map(tuple -> new OrderDetails(tuple.getT1(), tuple.getT2()));
```

Test cần xác minh chính sách của từng dependency: dữ liệu bắt buộc biến empty thành lỗi; dữ liệu tùy chọn có thể dùng giá trị mặc định. Không để một `Mono.empty()` vô tình làm toàn bộ endpoint hoàn tất rỗng nếu caller cần phân biệt không tìm thấy tài nguyên với kết quả hợp lệ.

## 5. Kiểm thử nguồn lỗi

Với nguồn lỗi, `StepVerifier` có thể kiểm tra kiểu lỗi, thông điệp hoặc điều kiện trên exception:

```java
@Test
void monoErrorPropagatesExpectedException() {
    RuntimeException failure = new IllegalStateException("database unavailable");

    StepVerifier.create(Mono.<String>error(failure))
        .expectError(IllegalStateException.class)
        .verify();
}

@Test
void checksErrorMessage() {
    StepVerifier.create(Mono.<String>error(
            new IllegalArgumentException("invalid customer id")))
        .expectErrorMessage("invalid customer id")
        .verify();
}
```

Nếu cần kiểm tra nhiều thuộc tính của lỗi, dùng `expectErrorSatisfies` hoặc `expectErrorMatches`:

```java
StepVerifier.create(service.load("missing"))
    .expectErrorSatisfies(error -> {
        assertInstanceOf(CustomerNotFoundException.class, error);
        assertEquals("missing", ((CustomerNotFoundException) error).customerId());
    })
    .verify();
```

Với `Flux`, publisher có thể phát một số phần tử trước khi lỗi xảy ra. Test phải xác minh cả phần tử đã phát và terminal error:

```java
Flux<String> source = Flux.just("first", "second")
    .concatWith(Mono.error(new IllegalStateException("stream failed")));

StepVerifier.create(source)
    .expectNext("first", "second")
    .expectErrorMessage("stream failed")
    .verify();
```

Lỗi là terminal signal. Sau `onError`, nguồn không tiếp tục phát thêm phần tử. Nếu pipeline phục hồi lỗi bằng `onErrorResume`, test phải xác minh hành vi mới mà subscriber quan sát được, không chỉ kiểm tra exception của nguồn ban đầu.

## 6. Kiểm thử chính sách phục hồi lỗi

`onErrorReturn` thay lỗi bằng một giá trị cố định; `onErrorResume` chuyển sang publisher dự phòng; `onErrorMap` đổi loại lỗi nhưng vẫn kết thúc bằng error:

```java
Mono<String> fallbackValue = Mono.<String>error(
        new TimeoutException("upstream timeout"))
    .onErrorReturn("cached");

StepVerifier.create(fallbackValue)
    .expectNext("cached")
    .verifyComplete();
```

Kiểm tra fallback bất đồng bộ:

```java
Mono<Customer> customer = primaryClient.find(customerId)
    .onErrorResume(TransientClientException.class,
        error -> cache.find(customerId));

StepVerifier.create(customer)
    .expectNextMatches(value -> value.id().equals(customerId))
    .verifyComplete();
```

Nên kiểm tra cả hai nhánh: lỗi thuộc nhóm được phép phục hồi thì fallback được subscribe; lỗi không thuộc nhóm đó phải tiếp tục đi xuống. `PublisherProbe` phù hợp để xác minh fallback được hoặc không được dùng. Tránh phục hồi mọi `Throwable` thành empty vì điều đó có thể che lỗi lập trình, lỗi dữ liệu hoặc lỗi hạ tầng cần được quan sát.

Ví dụ kiểm tra loại lỗi không được phục hồi:

```java
PublisherProbe<Customer> fallback = PublisherProbe.of(Mono.just(cachedCustomer));

Mono<Customer> result = Mono.<Customer>error(new SecurityException("forbidden"))
    .onErrorResume(TransientClientException.class, error -> fallback.mono());

StepVerifier.create(result)
    .expectError(SecurityException.class)
    .verify();

fallback.assertWasNotSubscribed();
```

## 7. Nguồn không kết thúc với Mono.never và Flux.never

`Mono.never()` không phát `onNext`, `onComplete` hoặc `onError`. `Flux.never()` có hành vi tương tự nhưng có kiểu publisher nhiều phần tử. Chúng hữu ích để mô phỏng một nguồn bị treo hoặc một subscription chỉ kết thúc khi downstream chủ động hủy.

```java
StepVerifier.create(Mono.<String>never())
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(100))
    .thenCancel()
    .verify(Duration.ofSeconds(1));
```

`expectSubscription()` tiêu thụ sự kiện subscription trước khi gọi `expectNoEvent`. Nếu không, `expectNoEvent` có thể thất bại ngay vì subscription chính là một sự kiện. Sau khoảng quan sát không có tín hiệu, `thenCancel()` chủ động hủy nguồn để test không giữ subscription mở.

Không gọi `verifyComplete()` cho `never()` vì publisher không có điều kiện hoàn tất; test sẽ chờ mãi nếu không có timeout bên ngoài. Với mọi test có thể không nhận terminal signal, hãy dùng `thenCancel()` hoặc giới hạn thời gian xác minh bằng `verify(Duration)`.

## 8. Phân biệt nguồn không kết thúc với timeout

Nguồn `never()` tự nó không lỗi. Toán tử `timeout` biến việc không nhận được tín hiệu trong khoảng thời gian cho phép thành lỗi timeout:

```java
Mono<String> guarded = Mono.<String>never()
    .timeout(Duration.ofSeconds(5));
```

Có thể kiểm thử mà không phải chờ thật năm giây bằng virtual time:

```java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
            .timeout(Duration.ofSeconds(5))
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify(Duration.ofSeconds(1));
```

`withVirtualTime` cung cấp scheduler thời gian ảo cho các operator dùng scheduler mặc định được hỗ trợ. Hãy tạo publisher bên trong supplier truyền cho `withVirtualTime`; nếu tạo `Mono.delay`, `Flux.interval` hoặc timeout trước đó, publisher có thể đã giữ scheduler thật và không được điều khiển bởi virtual clock.

Virtual time phù hợp cho timeout, retry backoff, delay và interval. Nếu pipeline dùng scheduler tùy chỉnh được truyền tường minh, test cần điều khiển scheduler đó riêng hoặc thiết kế dependency thời gian có thể thay thế.

## 9. Dùng TestPublisher để điều khiển nguồn trong test

`TestPublisher` cho phép test chủ động phát phần tử, complete hoặc error sau khi subscriber đã đăng ký. Điều này hữu ích khi cần mô phỏng nguồn bất đồng bộ mà không dùng thread hoặc thời gian thật:

```java
@Test
void handlesEmptyCompletionFromControlledSource() {
    TestPublisher<String> source = TestPublisher.create();

    StepVerifier.create(source.flux())
        .then(source::complete)
        .verifyComplete();
}
```

Có thể điều khiển lỗi:

```java
@Test
void propagatesErrorFromControlledSource() {
    TestPublisher<String> source = TestPublisher.create();
    RuntimeException failure = new IllegalStateException("source failed");

    StepVerifier.create(source.flux())
        .then(() -> source.error(failure))
        .expectErrorMatches(error -> error == failure)
        .verify();
}
```

Với nguồn không kết thúc, chỉ subscribe rồi kiểm tra không có tín hiệu trong khoảng quan sát, sau đó hủy. `TestPublisher` cũng cung cấp các assertion về subscriber và cancellation để xác minh pipeline đã ngừng tiêu thụ nguồn khi downstream không còn cần dữ liệu.

Không dùng `TestPublisher.createNoncompliant(...)` cho test thông thường. Các chế độ non-compliant cố ý vi phạm quy tắc Reactive Streams, chỉ phù hợp khi kiểm thử cách operator bảo vệ trước publisher không tuân thủ hợp đồng.

## 10. Kiểm thử cancellation và cleanup

Cancellation là một hành động từ subscriber, không phải `onComplete` hay `onError`. Khi test một pipeline có thể bị hủy, cần xác minh nguồn nhận được cancellation và tài nguyên được giải phóng:

```java
@Test
void takeCancelsSourceAfterEnoughValues() {
    TestPublisher<Integer> source = TestPublisher.create();

    StepVerifier.create(source.flux().take(2))
        .then(() -> source.next(10, 20))
        .expectNext(10, 20)
        .verifyComplete();

    source.assertCancelled();
}
```

`take(2)` hoàn tất downstream sau hai phần tử và hủy subscription upstream. `TestPublisher.assertCancelled()` xác minh cancellation đã tới nguồn.

Với cleanup đồng bộ, có thể dùng cờ hoặc bộ đếm trong callback `doFinally`/`using`. Với cleanup bất đồng bộ bằng `usingWhen`, tạo publisher cleanup có thể quan sát và xác minh nhánh cancel được subscribe. Không chỉ kiểm tra rằng downstream đã cancel; cần xác minh listener, cursor, connection hoặc subscription tới broker được giải phóng theo hợp đồng của nguồn.

Lưu ý rằng cancellation không bảo đảm một API blocking bên dưới dừng ngay. Test adapter blocking cần kiểm tra timeout/cancellation của chính client và không giả định `thenCancel()` có thể ngắt một lời gọi Java đồng bộ không hỗ trợ interrupt.

## 11. Kiểm thử nguồn không kết thúc trong service component

Một service có thể kết hợp nhiều nguồn, trong đó một nguồn không kết thúc. Ví dụ service chờ dữ liệu cấu hình và dữ liệu hồ sơ:

```java
Mono<ProfileView> profile = Mono.zip(
        profileRepository.findById(profileId),
        configurationService.current()
    )
    .map(tuple -> ProfileView.from(tuple.getT1(), tuple.getT2()));
```

Nếu `configurationService.current()` trả `Mono.never()`, kết quả zip cũng không phát giá trị dù repository đã có profile. Test component nên xác minh service có timeout hoặc fallback nếu hợp đồng yêu cầu response hữu hạn:

```java
Mono<ProfileView> guarded = profile
    .timeout(Duration.ofSeconds(2));
```

Không nên viết test chỉ bằng cách chờ vài giây trên scheduler thật. Dùng virtual time cho timeout và mock dependency bằng `Mono.never()` để test chính sách thời gian một cách xác định. Nếu service được thiết kế cho stream dài hạn, hãy kiểm thử cancellation và cleanup thay vì áp timeout tùy tiện.

## 12. Phân lớp kiểm thử theo phạm vi

Không cần dùng một loại test cho mọi hành vi. Chọn lớp test theo câu hỏi cần trả lời:

| Lớp kiểm thử | Đối tượng | Công cụ phù hợp | Điều cần xác minh |
| --- | --- | --- | --- |
| Operator/pipeline nhỏ | Một chuỗi `map`, `filter`, `switchIfEmpty`, `timeout` | `StepVerifier`, virtual time | Tín hiệu, thứ tự, empty/error/never và fallback |
| Component/service | Phối hợp repository/client và chính sách phục hồi | `StepVerifier`, Mockito, `PublisherProbe`, `TestPublisher` | Nhánh nào được gọi, lỗi nào được phục hồi, cancellation có truyền không |
| Adapter/integration | Database, HTTP client, broker hoặc framework | Testcontainers, WebTestClient, test server thật | Codec, timeout, resource cleanup, transaction và transport behavior |

Operator test nên nhỏ và nhanh, tập trung vào semantics của pipeline. Component test thay dependency bằng publisher điều khiển được để xác minh cách service phối hợp chúng. Integration test dùng adapter hoặc hạ tầng thật để kiểm tra những điều mock không thể chứng minh, chẳng hạn driver có thực sự hủy query, transaction có rollback hay server có đóng response stream khi client disconnect.

## 13. Quy tắc viết test không bị treo

Một test reactive có thể tự treo nếu publisher không phát terminal signal hoặc nếu test chờ một nhánh không được kích hoạt. Hãy áp dụng các quy tắc sau:

- Dùng `verifyComplete()` khi kỳ vọng complete và `verify()` sau `expectError...` khi kỳ vọng lỗi.
- Với nguồn không kết thúc, dùng `thenCancel()` sau khi xác minh subscription và khoảng không có tín hiệu.
- Đặt giới hạn bằng `verify(Duration)` cho test có nguy cơ chờ vô hạn.
- Dùng virtual time cho timeout/delay/retry thay vì `Thread.sleep`.
- Không gọi `.block()` hoặc tự `subscribe()` trong test để quan sát cùng publisher; để `StepVerifier` sở hữu subscription.
- Nếu cần kiểm tra nhánh publisher, dùng `PublisherProbe` thay vì suy luận chỉ từ giá trị cuối.
- Nếu cần điều khiển thời điểm phát, dùng `TestPublisher` thay vì tạo thread thủ công.

`StepVerifier.verify()` có thể chờ vô hạn nếu kịch bản không tạo terminal signal và không có bước cancel. Với test của `Mono.never()` hoặc `Flux.never()`, hãy luôn kết thúc kịch bản bằng cancellation hoặc timeout xác minh hữu hạn.

## 14. Checklist chọn assertion theo trạng thái nguồn

| Trạng thái cần kiểm thử | Kịch bản StepVerifier | Assertion bổ sung |
| --- | --- | --- |
| Empty completion | `verifyComplete()` mà không `expectNext` | Kiểm tra `defaultIfEmpty`/`switchIfEmpty` nếu có |
| Error ngay lập tức | `expectError...` | Kiểm tra loại, message và cause |
| Error sau một số phần tử | `expectNext...` rồi `expectError...` | Xác minh không có phần tử sau terminal error |
| Never | `expectSubscription`, `expectNoEvent`, `thenCancel` | Kiểm tra nguồn nhận cancellation |
| Never có timeout | Virtual time rồi `expectError(TimeoutException.class)` | Kiểm tra thời hạn và fallback |
| Fallback được chọn | Kỳ vọng giá trị từ publisher thay thế | `PublisherProbe.assertWasSubscribed()` |
| Fallback không được chọn | Kỳ vọng dữ liệu nguồn chính | `PublisherProbe.assertWasNotSubscribed()` |
| Cleanup khi cancel | `thenCancel()` | Probe/test resource xác minh cleanup |

## 15. Áp dụng vào ứng dụng reactive

Hãy xem empty, error và never là ba hợp đồng khác nhau cần được biểu diễn và kiểm thử rõ. Empty thường là kết quả nghiệp vụ hợp lệ như không tìm thấy dữ liệu hoặc không có sự kiện; error biểu diễn thất bại; never có thể phù hợp với stream dài hạn nhưng cần quản lý timeout, cancellation và tài nguyên. Dùng `StepVerifier` để xác minh terminal signal, `PublisherProbe` để xác minh nhánh được chọn và `TestPublisher` để điều khiển nguồn trong test.

Phân lớp test giúp phát hiện vấn đề ở đúng nơi: operator test xác minh semantics, component test xác minh chính sách phối hợp, integration test xác minh hành vi của database, HTTP client và transport thật. Với nguồn không kết thúc, luôn xác định ai sở hữu subscription và điều kiện dừng. Khi các trạng thái rỗng, lỗi và không kết thúc được kiểm thử có chủ đích, pipeline Project Reactor sẽ dễ dự đoán hơn và ít có nguy cơ giữ request hoặc tài nguyên vô thời hạn.

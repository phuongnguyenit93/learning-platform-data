# Kiểm thử thời gian chờ, retry, hủy đăng ký và giải phóng kết nối

Trong Spring Data Relational R2DBC, một publisher có thể bị timeout, được subscribe lại khi retry hoặc bị hủy trước khi hoàn tất. Những tín hiệu này ảnh hưởng trực tiếp tới statement, transaction và connection trong pool. Vì vậy, kiểm thử repository/service reactive không chỉ xác nhận giá trị trả về; cần chứng minh rằng timeout được phát đúng lúc, retry có giới hạn, cancellation truyền tới nguồn và connection được trả về pool sau complete, error hoặc cancel.

Một test chỉ dùng mock và xác nhận `Mono` phát đúng DTO chưa đủ để chứng minh driver đã hủy statement hoặc pool đã release connection. Cần kết hợp hai lớp kiểm thử:

- **Unit/reactive tests:** dùng `StepVerifier`, `TestPublisher`, `PublisherProbe` và virtual time để kiểm tra tín hiệu, số lần subscribe, retry và cancellation mà không phụ thuộc database thật.
- **Integration tests:** chạy với R2DBC driver và database mục tiêu, kiểm tra timeout thực tế, transaction rollback, cleanup result/cursor và khả năng lấy lại connection từ pool.

## 1. Vòng đời cần kiểm thử

Một thao tác database reactive thường đi qua các giai đoạn:

```text
Caller subscribe
       |
       v
Acquire connection từ pool
       |
       v
Execute statement
       |
       v
Consume result / map rows
       |
       +--------------------------+
       |            |             |
       v            v             v
   onComplete     onError       cancel
       |            |             |
       v            v             v
  cleanup/close  rollback hoặc  cancel/rollback
       |          cleanup        nếu cần
       +------------+-------------+
                    |
                    v
             Return connection
                    |
                    v
             Pool có thể cấp lại
```

Chi tiết commit/rollback phụ thuộc transaction boundary. Với reactive transaction của Spring, publisher hoàn tất thành công có thể commit; lỗi truyền qua boundary hoặc cancellation trước khi hoàn tất được transaction manager xử lý theo semantics rollback. Dù không có transaction, result/statement và connection vẫn cần được cleanup.

Các test nên xác nhận cả tín hiệu quan sát được ở caller lẫn trạng thái tài nguyên sau đó. `StepVerifier` thấy `onError` chưa tự chứng minh connection đã được trả về pool; cần một phép kiểm tra pool/database riêng.

## 2. Phân biệt các loại timeout

Không có một timeout duy nhất bảo vệ toàn bộ vòng đời R2DBC. Mỗi lớp có thể có deadline riêng:

| Loại timeout | Mục tiêu | Ví dụ lỗi/kết quả |
|---|---|---|
| Pool acquire timeout | Giới hạn thời gian chờ connection rảnh | Acquire timeout từ pool |
| Connection creation timeout | Giới hạn thời gian mở connection mới | Lỗi kết nối hoặc timeout |
| Statement/query timeout | Giới hạn thời gian database xử lý statement | Lỗi do database/driver |
| Reactor `timeout` | Giới hạn thời gian publisher không phát tín hiệu theo operator | `TimeoutException` hoặc fallback |
| Transaction timeout | Giới hạn vòng đời transaction theo transaction manager | Transaction timeout/rollback |
| HTTP response timeout | Giới hạn thời gian request/response ở server, gateway hoặc client | Request timeout hoặc kết nối bị đóng |
| Test verification timeout | Giới hạn thời gian test chờ publisher trong `StepVerifier` | Test thất bại vì không nhận tín hiệu kịp |

Các timeout này không thay thế nhau. Ví dụ Reactor `timeout` có thể hủy subscription, nhưng driver/database cần thực hiện việc cancel statement và cleanup. Pool acquire timeout chỉ giới hạn thời gian chờ connection, không giới hạn thời gian truy vấn sau khi đã lấy được connection.

### 2.1. Timeout cho một lần thử và timeout cho toàn bộ workflow

Khi kết hợp timeout với retry, cần quyết định deadline áp dụng cho từng attempt hay toàn bộ use case.

Timeout cho từng attempt, sau đó retry:

```java
Mono<Customer> oneAttempt = customerRepository.findById(id)
    .timeout(Duration.ofSeconds(2));

return oneAttempt.retryWhen(retryPolicy);
```

Mỗi lần subscribe lại vào `oneAttempt` có deadline hai giây. Tổng thời gian workflow có thể dài hơn hai giây vì có nhiều lần thử và thời gian backoff.

Timeout tổng thể cho cả retry sequence:

```java
return customerRepository.findById(id)
    .retryWhen(retryPolicy)
    .timeout(Duration.ofSeconds(5));
```

Deadline ngoài bao trùm cả lần đầu, các lần retry và khoảng chờ backoff. Khi hết năm giây, publisher tổng thể timeout và hủy attempt đang chạy.

Trong hệ thống thực tế, có thể cần cả hai: timeout ngắn cho từng query và deadline tổng thể cho request. Chọn giá trị theo SLA, không đặt tùy tiện.

### 2.2. Timeout của StepVerifier khác timeout của publisher

Ví dụ:

```java
StepVerifier.create(service.findCustomer(id))
    .expectNextCount(1)
    .verifyComplete(Duration.ofSeconds(3));
```

`verifyComplete(Duration)` giới hạn thời gian test chờ tín hiệu. Nó không cấu hình query timeout hoặc thay đổi publisher production. Nếu muốn kiểm thử operator `timeout`, hãy đặt `timeout(...)` trong pipeline được test rồi xác nhận `TimeoutException`.

## 3. Kiểm thử timeout bằng StepVerifier

Với nguồn không bao giờ phát tín hiệu, có thể xác nhận operator timeout:

```java
@Test
void emitsTimeoutWhenSourceDoesNotRespond() {
    Mono<String> publisher = Mono.<String>never()
        .timeout(Duration.ofMillis(100));

    StepVerifier.create(publisher)
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(2));
}
```

Test này kiểm tra semantics Reactor, không cần database. `Mono.never()` không phát `onNext`, `onComplete` hoặc `onError`; khi timeout hết hạn, operator phát lỗi timeout và hủy upstream.

Nếu có fallback:

```java
Mono<String> publisher = Mono.<String>never()
    .timeout(Duration.ofMillis(100), Mono.just("fallback"));

StepVerifier.create(publisher)
    .expectNext("fallback")
    .verifyComplete();
```

Khi fallback được dùng, downstream thấy completion thành công. Điều này có thể phù hợp cho cache hoặc dữ liệu tùy chọn, nhưng không nên biến timeout của thao tác ghi database thành success giả.

### 3.1. Dùng virtual time để test timer nhanh

Không cần chờ thật nhiều giây để kiểm tra retry backoff hoặc timeout. Reactor Test cung cấp `StepVerifier.withVirtualTime`:

```java
@Test
void timeoutUsesVirtualTime() {
    StepVerifier.withVirtualTime(() ->
            Mono.<String>never()
                .timeout(Duration.ofHours(1))
        )
        .thenAwait(Duration.ofHours(1))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(2));
}
```

Publisher phải được tạo bên trong supplier truyền cho `withVirtualTime`, để scheduler ảo có thể được cài trước khi các operator tạo timer. Nếu tạo publisher trước rồi mới truyền vào, timer có thể đã gắn với scheduler thật.

Virtual time phù hợp cho timer Reactor như `timeout`, `delayElements`, `delaySubscription` và retry backoff dùng scheduler được Reactor quản lý. Nó không làm thời gian thực thi PostgreSQL, network I/O hoặc R2DBC driver chạy nhanh hơn. Với database thật, dùng timeout thực tế có giới hạn và test integration riêng.

### 3.2. Kiểm tra publisher bị hủy khi timeout

Có thể dùng `TestPublisher` để xác nhận timeout hủy upstream:

```java
@Test
void timeoutCancelsUpstream() {
    TestPublisher<String> source = TestPublisher.create();

    StepVerifier.withVirtualTime(() ->
            source.flux().next()
                .timeout(Duration.ofSeconds(5))
        )
        .thenAwait(Duration.ofSeconds(5))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(2));

    source.assertCancelled();
}
```

`TestPublisher.assertCancelled()` xác nhận subscriber đã gửi cancellation tới nguồn test. Đây là bằng chứng ở tầng Reactive Streams; nó chưa chứng minh R2DBC driver đã đóng cursor hoặc pool release connection đúng cách.

## 4. Kiểm thử timeout của database thật

Unit test bằng `Mono.never()` không kiểm tra database hoặc driver. Integration test cần dùng database/driver tương thích với môi trường chạy, thường qua Testcontainers hoặc database test riêng.

Một test tích hợp nên:

1. Tạo query có thể kiểm soát thời gian chạy hoặc dùng một query test fixture đủ chậm.
2. Thực thi qua `DatabaseClient`/repository thật.
3. Áp timeout ở lớp cần kiểm tra.
4. Xác nhận caller nhận đúng lỗi.
5. Xác nhận statement/result được cleanup và connection được trả về pool.
6. Thực hiện query tiếp theo để chứng minh pool vẫn cấp được connection.

Ví dụ PostgreSQL-specific dùng `pg_sleep`:

```java
Mono<Integer> slowQuery() {
    return databaseClient.sql("SELECT 1 FROM pg_sleep(5)")
        .map((row, metadata) -> row.get(0, Integer.class))
        .one();
}

@Test
void cancelsSlowPostgresQueryOnReactorTimeout() {
    StepVerifier.create(slowQuery().timeout(Duration.ofMillis(200)))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(3));
}
```

Đây là ví dụ dành riêng cho PostgreSQL. Hàm `pg_sleep` và cú pháp SQL không portable. Test cần xác nhận đúng phiên bản driver xử lý cancellation như mong đợi; không kết luận database đã dừng ngay chỉ từ việc caller nhận `TimeoutException`.

### 4.1. Reactor timeout và statement timeout khác nhau

Reactor timeout giới hạn thời gian chờ tín hiệu ở tầng publisher. Database statement timeout giới hạn thời gian database cho phép một statement chạy. Hai lớp có thể bổ sung cho nhau:

- Statement timeout giúp database chủ động hủy query vượt thời hạn.
- Reactor timeout bảo vệ caller và hủy subscription khi deadline ứng dụng hết.
- Pool acquire timeout ngăn request chờ connection vô hạn.

Với PostgreSQL, có thể cấu hình `statement_timeout` ở cấp role/database/session hoặc dùng `SET LOCAL` trong transaction tùy chính sách. Ví dụ:

```sql
SET LOCAL statement_timeout = '2s';
```

`SET LOCAL` chỉ có hiệu lực trong transaction hiện tại. Không giả định một câu `SET LOCAL` chạy ở connection khác sẽ áp dụng cho query tiếp theo. Nếu cấu hình ở cấp session trong pool, phải bảo đảm reset trạng thái khi connection được trả về để tránh rò rỉ cấu hình sang request khác.

## 5. Retry có nghĩa là subscribe lại

Trong Reactor, retry không “tiếp tục từ đúng dòng đã lỗi”. Retry subscribe lại upstream publisher. Với một publisher database cold/lazy, điều này thường có nghĩa query hoặc thao tác ghi được thực hiện lại.

Ví dụ:

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    int attempt = attempts.incrementAndGet();

    if (attempt < 3) {
        return Mono.error(new TransientDataAccessResourceException(
            "Temporary failure"
        ));
    }

    return Mono.just("ok");
});

Mono<String> result = source.retry(2);
```

`Mono.defer` tạo nguồn mới ở mỗi lần subscribe. `retry(2)` cho phép tối đa hai lần retry sau lần đầu, tức tổng cộng tối đa ba lần thực thi.

Không nên retry mọi exception. Lỗi validation, unique violation, foreign key, sai SQL hoặc lỗi nghiệp vụ thường không tự biến mất khi thử lại. Retry phù hợp hơn với lỗi tạm thời được phân loại rõ như một số lỗi kết nối, deadlock hoặc serialization conflict theo chính sách hệ thống.

## 6. Retry có backoff và giới hạn

Retry liên tục ngay lập tức có thể làm tình trạng database đang quá tải nặng hơn. Dùng backoff để tạo khoảng nghỉ giữa các lần thử:

```java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .filter(this::isRetryableDatabaseFailure)
    .onRetryExhaustedThrow((spec, signal) -> signal.failure());

Mono<Customer> loadCustomer(Long id) {
    return customerRepository.findById(id)
        .retryWhen(retryPolicy);
}
```

`Retry.backoff(3, ...)` cho tối đa ba lần retry ngoài lần đầu. Backoff tăng dần tới mức tối đa. Có thể thêm jitter để nhiều instance không cùng retry vào một thời điểm; API cụ thể phụ thuộc phiên bản Reactor.

Hàm phân loại nên dựa trên exception type, SQLSTATE hoặc vendor code có cấu trúc:

```java
boolean isRetryableDatabaseFailure(Throwable error) {
    return error instanceof TransientDataAccessResourceException
        || error instanceof R2dbcTransientResourceException;
}
```

Ví dụ chỉ mang tính minh họa. Các loại exception thực tế phụ thuộc Spring exception translation và driver. Không dùng `error.getMessage().contains("timeout")` làm bộ phân loại chính vì message thay đổi theo driver/version/locale.

### 6.1. Số lần retry khác số lần thực thi

Nếu cấu hình ba lần retry, tổng số attempt có thể là bốn:

| Lần | Ý nghĩa |
|---:|---|
| 1 | Lần thực thi ban đầu |
| 2 | Retry lần thứ nhất |
| 3 | Retry lần thứ hai |
| 4 | Retry lần thứ ba |

Hãy ghi rõ giới hạn theo số lần retry hay tổng attempt trong cấu hình và tài liệu. Điều này giúp tránh vô tình tạo tải gấp đôi/gấp nhiều lần dự kiến.

### 6.2. Kiểm thử số lần attempt

```java
@Test
void retriesOnlyUpToConfiguredLimit() {
    AtomicInteger attempts = new AtomicInteger();

    Mono<String> source = Mono.defer(() -> {
        attempts.incrementAndGet();
        return Mono.error(new TransientDataAccessResourceException("temporary"));
    });

    StepVerifier.withVirtualTime(() ->
            source.retryWhen(Retry.backoff(2, Duration.ofSeconds(1)).jitter(0))
        )
        .thenAwait(Duration.ofSeconds(5))
        .expectError(TransientDataAccessResourceException.class)
        .verify(Duration.ofSeconds(2));

    assertEquals(3, attempts.get());
}
```

Test xác nhận một lần đầu cộng hai lần retry. Virtual time giúp không phải chờ backoff thật. Tạo `source` bằng `Mono.defer` để bộ đếm tăng ở mỗi subscription; nếu tạo side effect trước subscription, test có thể đếm sai.

## 7. Retry thao tác ghi cần idempotency

Retry một SELECT thường ít rủi ro về side effect hơn retry INSERT/UPDATE, nhưng vẫn có thể trả dữ liệu khác ở lần sau. Retry thao tác ghi nguy hiểm hơn vì lỗi có thể xảy ra sau khi database đã commit nhưng trước khi ứng dụng nhận được xác nhận.

Ví dụ:

```text
Client gửi INSERT
       |
       v
Database commit thành công
       |
       v
Kết nối bị đứt trước khi response tới ứng dụng
       |
       v
Ứng dụng thấy lỗi kết nối và retry
       |
       v
INSERT thứ hai có thể tạo bản ghi trùng
```

Ứng dụng không thể luôn biết chắc thao tác trước đã commit hay chưa chỉ từ việc client nhận exception. Với write retry, hãy thiết kế idempotency:

- Dùng idempotency key có unique constraint.
- Dùng khóa nghiệp vụ duy nhất nếu phù hợp.
- Dùng upsert có điều kiện theo semantics domain.
- Lưu kết quả thao tác để retry có thể trả lại kết quả trước đó.
- Tránh gửi side effect ngoài database trước khi transaction commit.

Ví dụ bảng request:

```sql
CREATE TABLE payment_request (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(30) NOT NULL,
    CONSTRAINT uk_payment_request_key
        UNIQUE (account_id, idempotency_key)
);
```

Khi retry cùng key, service kiểm tra hash và trạng thái để trả lại kết quả cũ hoặc tiếp tục workflow theo quy tắc. Không cho cùng key được dùng với payload khác mà không phát hiện.

## 8. Đặt retry ở đâu so với transaction?

Vị trí `retryWhen` so với transaction boundary quyết định transaction được tạo lại thế nào.

### 8.1. Retry bên trong transaction boundary

```java
return transactionalOperator.transactional(
    repository.save(entity)
        .retryWhen(retryPolicy)
);
```

Retry được áp dụng cho publisher bên trong transaction. Các attempt có thể chạy trong cùng transaction context/connection tùy transaction manager và cách driver xử lý lỗi. Với database như PostgreSQL, sau một statement error, transaction có thể ở trạng thái failed và không thể tiếp tục statement tiếp theo trước khi rollback. Vì vậy, retry statement trong cùng transaction thường không phải lựa chọn an toàn cho lỗi đã làm transaction thất bại.

### 8.2. Retry toàn bộ transaction

```java
Mono<Order> createOrderWithRetry(Order order) {
    return Mono.defer(() ->
            transactionalOperator.transactional(
                orderRepository.save(order)
                    .flatMap(saved -> saveLines(saved))
                    .thenReturn(order)
            )
        )
        .retryWhen(retryPolicy);
}
```

Ở đây retry nằm ngoài publisher transactional. Mỗi lần subscribe lại có thể bắt đầu một transaction mới và thực hiện lại toàn bộ use case. `Mono.defer` giúp tạo publisher transactional cho mỗi attempt. Cách này phù hợp hơn khi lỗi tạm thời yêu cầu rollback transaction hiện tại trước khi thử lại.

Tuy nhiên, transaction mới không làm side effect trở nên idempotent. Nếu workflow có gọi HTTP, gửi email hoặc phát message, các side effect đó vẫn có thể bị lặp. Chỉ retry toàn use case khi các thao tác đã được thiết kế an toàn khi lặp hoặc có cơ chế outbox/idempotency.

### 8.3. Không giữ connection trong thời gian backoff

Khi retry được đặt bên ngoài transaction publisher, transaction của attempt lỗi có cơ hội rollback/cleanup trước khi `Retry` chờ backoff rồi subscribe lại. Điều này giúp tránh giữ transaction-bound connection trong thời gian chờ giữa các lần thử.

Hãy kiểm tra thực tế bằng pool metrics hoặc integration test, đặc biệt khi dùng custom transaction manager hoặc driver có cancellation/cleanup bất đồng bộ.

## 9. Không retry cancellation như một lỗi tạm thời

Cancellation có nghĩa downstream không còn yêu cầu kết quả. Nó không phải tín hiệu lỗi thông thường mà ứng dụng nên retry tự động.

Ví dụ:

```java
return repository.findAll()
    .retryWhen(retryPolicy);
```

Nếu caller hủy subscription, retry operator không nên tiếp tục tạo attempt mới cho một subscriber đã hủy. Test cần xác nhận cancellation truyền tới upstream và không có lần subscribe mới sau đó.

Không dùng `doOnError` để xử lý cancellation; cancellation không phát `onError`. Dùng `doFinally` để quan sát signal `CANCEL`:

```java
return repository.findAll()
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            metrics.counter("r2dbc.query.cancelled").increment();
        }
    });
```

Callback này nên nhẹ và không block. Không gọi `subscribe()` cho một thao tác cleanup khác bên trong `doFinally`; hãy dùng `usingWhen` hoặc lifecycle API thích hợp nếu cleanup cần thực hiện bất đồng bộ.

## 10. Kiểm thử retry với PublisherProbe

`PublisherProbe` giúp xác nhận publisher fallback hoặc publisher được compose có được subscribe/request/cancel hay không.

Ví dụ fallback sau khi cache miss:

```java
@Test
void subscribesToDatabaseFallbackWhenCacheIsEmpty() {
    PublisherProbe<Customer> databaseProbe =
        PublisherProbe.of(Mono.just(customer));

    Mono<Customer> result = Mono.<Customer>empty()
        .switchIfEmpty(databaseProbe.mono());

    StepVerifier.create(result)
        .expectNext(customer)
        .verifyComplete();

    databaseProbe.assertWasSubscribed();
    databaseProbe.assertWasRequested();
}
```

Probe hữu ích để kiểm tra một nhánh có được kích hoạt. Với retry, có thể dùng `Mono.defer` và `AtomicInteger` để đếm attempt; với fallback, `PublisherProbe` xác nhận nhánh đã được subscribe.

## 11. Kiểm thử cancellation với StepVerifier

Một test cơ bản xác nhận cancellation:

```java
@Test
void cancelsInfiniteSource() {
    StepVerifier.create(Flux.interval(Duration.ofMillis(10)))
        .expectNext(0L)
        .thenCancel()
        .verify(Duration.ofSeconds(2));
}
```

`thenCancel()` gửi cancellation sau khi nhận phần tử mong đợi. `verify(...)` giới hạn thời gian test chờ hoàn tất quá trình kiểm tra.

### 11.1. Dùng TestPublisher để xác nhận upstream bị hủy

```java
@Test
void cancellationReachesUpstream() {
    TestPublisher<Integer> source = TestPublisher.create();

    StepVerifier.create(source.flux())
        .thenCancel()
        .verify(Duration.ofSeconds(2));

    source.assertCancelled();
}
```

Đây là unit test cho Reactive Streams. Nó xác nhận publisher nguồn nhận cancellation, nhưng không kiểm tra cleanup của connection database thật.

### 11.2. Xác nhận không retry sau cancellation

```java
@Test
void doesNotStartAnotherAttemptAfterCancellation() {
    AtomicInteger attempts = new AtomicInteger();

    Mono<String> source = Mono.defer(() -> {
        attempts.incrementAndGet();
        return Mono.<String>never();
    }).retryWhen(Retry.max(3));

    StepVerifier.create(source)
        .thenCancel()
        .verify(Duration.ofSeconds(2));

    assertEquals(1, attempts.get());
}
```

Nguồn `never()` không phát lỗi nên không kích hoạt retry; cancellation kết thúc subscription. Test này xác nhận attempt không tự chạy lại sau khi subscriber hủy.

## 12. Kiểm thử cleanup với usingWhen

Khi code tự quản lý resource reactive, `usingWhen` cung cấp callback cleanup cho các đường complete, error và cancel:

```java
Mono<Result> executeWithResource() {
    return Mono.usingWhen(
        resourceFactory.create(),
        resource -> resource.execute(),
        Resource::close,
        (resource, error) -> resource.close(),
        Resource::close
    );
}
```

Ví dụ này minh họa ba callback cleanup: complete, error và cancel. API overload cụ thể tùy kiểu resource và phiên bản Reactor. Với connection do Spring Data/R2DBC quản lý, thông thường không tự lấy connection raw rồi tự đóng nếu không cần; hãy để `DatabaseClient`, `R2dbcEntityTemplate` hoặc transaction manager quản lý lifecycle.

### 12.1. Test cleanup cho complete/error/cancel

Có thể dùng fake resource đếm số lần cleanup:

```java
AtomicInteger closed = new AtomicInteger();

Mono<String> work = Mono.usingWhen(
    Mono.just(new TestResource()),
    resource -> Mono.just("ok"),
    resource -> {
        closed.incrementAndGet();
        return Mono.empty();
    },
    (resource, error) -> {
        closed.incrementAndGet();
        return Mono.empty();
    },
    resource -> {
        closed.incrementAndGet();
        return Mono.empty();
    }
);
```

Tạo ba test riêng để xác nhận đúng cleanup callback cho complete, error và cancel. Không dùng một counter chung cho nhiều subscription trong cùng test nếu không reset rõ ràng.

## 13. Kiểm tra connection được trả về pool

Đây là phần quan trọng nhất của integration test. Caller nhận `onComplete`, `onError` hoặc `cancel` không tự chứng minh connection đã sẵn sàng cho request tiếp theo.

Một chiến lược test hữu ích là tạo connection pool có `maxSize = 1` trong môi trường test:

1. Bắt đầu một query stream và giữ nó chưa hoàn tất.
2. Xác nhận query thứ hai phải chờ vì connection duy nhất đang bận.
3. Hủy hoặc hoàn tất query thứ nhất.
4. Chờ cleanup trong một khoảng giới hạn.
5. Thực hiện query thứ hai và xác nhận nó lấy được connection.

Nếu connection không được trả về pool, query thứ hai sẽ chờ tới acquire timeout. Cấu hình pool một connection làm lỗi lifecycle dễ quan sát hơn.

### 13.1. Cấu hình pool nhỏ trong test

Ví dụ khái quát với R2DBC Pool:

```java
ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(connectionFactory)
        .initialSize(1)
        .maxSize(1)
        .maxAcquireTime(Duration.ofSeconds(2))
        .maxIdleTime(Duration.ofMinutes(1))
        .build();

ConnectionPool pool = new ConnectionPool(configuration);
```

Đây là cấu hình minh họa; API builder và package cần khớp phiên bản `r2dbc-pool` của dự án. Test nên đóng pool sau khi hoàn tất để không giữ resource giữa các test.

### 13.2. Kiểm thử connection sau cancellation

Ví dụ với PostgreSQL và một stream đủ lớn:

```java
Flux<Long> slowRows = databaseClient.sql("""
        SELECT generate_series(1, 1000000) AS id
        """)
    .map((row, metadata) -> row.get("id", Long.class))
    .all()
    .delayElements(Duration.ofMillis(10));

StepVerifier.create(slowRows)
    .expectNextCount(1)
    .thenCancel()
    .verify(Duration.ofSeconds(5));

StepVerifier.create(databaseClient.sql("SELECT 1")
        .map((row, metadata) -> row.get(0, Integer.class))
        .one())
    .expectNext(1)
    .verifyComplete(Duration.ofSeconds(3));
```

Query `generate_series` là PostgreSQL-specific. `delayElements` làm chậm downstream trong test để có cơ hội hủy khi result đang được tiêu thụ. Query `SELECT 1` sau đó xác nhận pool có thể cấp connection cho thao tác tiếp theo. Trong test thực tế, cấu hình pool `maxSize = 1`, acquire timeout hữu hạn và cleanup test data rõ ràng.

Không khẳng định connection được release ngay tại thời điểm `thenCancel()` trả về nếu driver cleanup bất đồng bộ. Điều cần xác nhận là trong thời hạn được thiết kế, pool có thể cấp lại connection và metric active/acquired trở về trạng thái mong đợi.

### 13.3. Kiểm tra connection sau error

Tạo một query lỗi có chủ đích, xác nhận caller nhận exception, rồi chạy `SELECT 1` trên cùng pool. Test này phát hiện trường hợp statement/result lỗi nhưng connection không được trả về hoặc pool đánh dấu connection hỏng mà không tạo connection thay thế theo cấu hình.

### 13.4. Kiểm tra connection sau complete

Đọc hết result stream, xác nhận complete, rồi thực hiện query thứ hai. Đây là đường lifecycle cơ bản và nên có test riêng, không chỉ kiểm tra cancel/error.

## 14. Kiểm thử cancellation trong transaction

Khi transaction reactive đang mở, cancellation trước khi publisher hoàn tất cần được transaction manager xử lý. Có thể kiểm tra bằng cách ghi dữ liệu rồi giữ publisher chưa complete:

```java
Mono<Void> transactionalWork = transactionalOperator.transactional(
    customerRepository.save(customer)
        .then(Mono.never())
);

StepVerifier.create(transactionalWork)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

Sau khi cancellation và cleanup hoàn tất, đọc lại customer bằng một transaction/query mới và xác nhận bản ghi chưa được commit. Đây là integration test cần database thật; mock publisher không chứng minh transaction rollback.

### 14.1. Không dùng subscription test bên ngoài transaction để che kết quả

Nếu test framework tự mở transaction cho test method và rollback sau test, kết quả có thể không phản ánh commit/rollback của service. Khi kiểm tra cancellation transaction, hãy bảo đảm truy vấn xác minh chạy sau khi transaction của service đã được cleanup và không bị transaction ngoài che khuất.

### 14.2. Timeout trong transaction

Nếu timeout được đặt bên trong transaction boundary:

```java
Mono<Customer> work = transactionalOperator.transactional(
    customerRepository.save(customer)
        .timeout(Duration.ofMillis(100))
);
```

Timeout phát lỗi vào publisher bên trong operator; transaction manager có thể rollback. Nếu fallback được đặt bên trong boundary và biến lỗi thành complete, transaction có thể commit. Test cần kiểm tra vị trí `onErrorResume`/fallback để chắc chắn rollback xảy ra như ý định.

## 15. Kiểm thử retry và giải phóng connection giữa các attempt

Retry toàn transaction nên kết thúc attempt lỗi trước khi bắt đầu backoff và attempt tiếp theo. Có thể dùng pool `maxSize = 1`, một lỗi tạm thời được mô phỏng ở lần đầu, rồi một query kiểm tra hoặc metric để xác nhận connection không bị giữ trong khoảng backoff.

Với unit test, dùng `Mono.defer` và virtual time để xác nhận:

- Số attempt đúng.
- Khoảng backoff được áp dụng.
- Lỗi không thuộc nhóm retryable không kích hoạt retry.
- Cancellation trong backoff không tạo attempt tiếp theo.

Với integration test, dùng database fault injection hoặc một wrapper test quanh `ConnectionFactory` để mô phỏng lỗi ở thời điểm phù hợp. Không cố tình làm database production lỗi để kiểm tra retry.

### 15.1. Kiểm thử không retry lỗi nghiệp vụ

```java
@Test
void doesNotRetryUniqueViolation() {
    AtomicInteger attempts = new AtomicInteger();

    Mono<String> source = Mono.defer(() -> {
        attempts.incrementAndGet();
        return Mono.error(new DuplicateKeyException("duplicate"));
    });

    StepVerifier.create(source.retryWhen(
            Retry.max(3).filter(this::isRetryableDatabaseFailure)))
        .expectError(DuplicateKeyException.class)
        .verify();

    assertEquals(1, attempts.get());
}
```

Test giả định `isRetryableDatabaseFailure` không phân loại duplicate key là lỗi tạm thời. Điều này giúp ngăn retry vô ích và tránh tạo tải thêm.

### 15.2. Kiểm thử cancellation trong backoff

Sau một lỗi đầu tiên, retry operator có thể đang chờ timer. Nếu subscriber hủy trong khoảng chờ, không được tạo attempt tiếp theo:

```java
@Test
void cancellationDuringBackoffStopsFurtherAttempts() {
    AtomicInteger attempts = new AtomicInteger();

    Mono<String> source = Mono.defer(() -> {
        attempts.incrementAndGet();
        return Mono.error(new TransientDataAccessResourceException("temporary"));
    }).retryWhen(Retry.backoff(5, Duration.ofSeconds(10)).jitter(0));

    StepVerifier.withVirtualTime(() -> source)
        .thenAwait(Duration.ofSeconds(1))
        .thenCancel()
        .verify(Duration.ofSeconds(2));

    assertEquals(1, attempts.get());
}
```

Test này dùng virtual time và hủy trước khi backoff đầu tiên hết hạn. Nếu thay đổi thời gian backoff, điều chỉnh phần `thenAwait` để test luôn hủy trong khoảng chờ.

## 16. Kiểm thử WebFlux khi HTTP client ngắt kết nối

Unit test publisher không chứng minh HTTP server thực sự truyền cancellation khi client đóng socket. Cần integration test qua WebFlux server và HTTP client.

Với `WebTestClient`, có thể nhận streaming response rồi hủy consumer:

```java
FluxExchangeResult<CustomerView> result = webTestClient.get()
    .uri("/customers/stream")
    .accept(MediaType.APPLICATION_NDJSON)
    .exchange()
    .expectStatus().isOk()
    .returnResult(CustomerView.class);

StepVerifier.create(result.getResponseBody())
    .expectNextCount(1)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

Test này hủy subscription đọc response body ở phía client. Tùy cấu hình test client/server, việc này có thể không tương đương hoàn toàn với đóng socket TCP thật. Đối với kiểm thử end-to-end, hãy dùng client có thể đóng kết nối thực tế hoặc test harness chạy server trên cổng ngẫu nhiên và chủ động hủy HTTP request.

Sau khi client hủy, kiểm tra:

- Server nhận cancellation hoặc disconnect theo cách connector hỗ trợ.
- Publisher service nhận `doFinally(CANCEL)` nếu cancellation truyền tới pipeline.
- R2DBC result/statement được cleanup.
- Connection trở lại pool trong thời hạn hợp lý.
- Request khác vẫn lấy được connection.
- Không có retry hoặc side effect mới tiếp tục chạy sau cancellation.

## 17. Kiểm thử connection leak với pool nhỏ

Pool `maxSize = 1` là cách đơn giản để làm lộ resource leak trong test:

```text
Test bắt đầu
   |
   v
Query A lấy connection duy nhất
   |
   v
Query A bị giữ/chưa complete
   |
   v
Query B yêu cầu connection -> phải chờ
   |
   v
Hủy/hoàn tất Query A
   |
   v
Query B phải lấy được connection
   |
   v
Test kết thúc và đóng pool
```

Nếu query B không lấy được connection sau khi A đã kết thúc, có thể có vấn đề cleanup, connection leak hoặc connection bị đánh dấu invalid và pool không thể tạo connection thay thế. Cần xem pool metrics/log để phân biệt các trường hợp.

### 17.1. Không kết luận leak từ một lần acquire timeout

Acquire timeout có thể do:

- Query A vẫn đang chạy hợp lệ.
- Database không phản hồi và driver chưa cleanup.
- Pool không tạo được connection thay thế.
- Pool đã hết maxSize do nhiều request đồng thời.
- Test chưa chờ đủ thời gian cho cleanup.

Hãy xác nhận query A đã complete/error/cancel, quan sát active/acquired metrics và kiểm tra query tiếp theo sau thời gian cleanup hữu hạn.

### 17.2. Kiểm tra số lần acquire/release

Nếu cần chẩn đoán sâu, có thể bọc `ConnectionFactory`/`Connection` trong test để đếm:

- Số lần `create()` được gọi.
- Số connection được cấp từ pool.
- Số lần `close()`/release được gọi.
- Số connection đang được giữ.
- Các lệnh `cancel`/cleanup quan sát được nếu wrapper hỗ trợ.

Không dùng wrapper test như bằng chứng rằng driver thật luôn có hành vi giống mock. Kết hợp wrapper unit test với integration test trên driver thật.

## 18. TestPublisher và PublisherProbe nên dùng khi nào?

| Công cụ | Dùng để kiểm tra |
|---|---|
| `StepVerifier` | Tín hiệu `onNext`, `onComplete`, `onError`, request và cancel |
| `withVirtualTime` | Timeout/backoff/delay dựa trên scheduler ảo |
| `TestPublisher` | Điều khiển tín hiệu nguồn và xác nhận cancellation |
| `PublisherProbe` | Publisher có được subscribe, request hoặc cancel không |
| `AtomicInteger` + `Mono.defer` | Đếm số lần thực thi/subscribe của nguồn |
| R2DBC pool metrics | Active, idle, pending acquire và release behavior |
| Testcontainers/database thật | Driver, SQL timeout, transaction, cursor và cleanup thực tế |
| WebTestClient/HTTP client thực | Cancellation từ tầng HTTP tới publisher |

Không cần dùng tất cả công cụ trong mọi test. Chọn công cụ phù hợp với câu hỏi cần xác nhận.

## 19. Những lỗi thường gặp khi kiểm thử timeout, retry và cleanup

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ test `TimeoutException` ở Reactor | Không biết driver/database đã cancel hay chưa | Thêm integration test với R2DBC thật và query tiếp theo |
| Nhầm `verify(Duration)` với query timeout | Test timeout không kiểm tra operator production | Đặt `timeout()` trong publisher và test riêng |
| Dùng virtual time cho database thật | Virtual scheduler không điều khiển network/database I/O | Dùng virtual time cho timer; integration test dùng thời gian thực có giới hạn |
| Tạo publisher trước `withVirtualTime` | Timer có thể dùng scheduler thật | Tạo publisher bên trong supplier |
| Dùng retry không giới hạn | Có thể tạo vòng lặp và gây quá tải | Giới hạn retry, backoff, jitter và deadline tổng |
| Retry mọi exception | Lặp lỗi nghiệp vụ/constraint không thể tự hết | Filter theo loại lỗi/mã lỗi tạm thời |
| Retry INSERT không idempotent | Có thể ghi trùng khi kết quả commit bị mất | Dùng idempotency key/unique constraint/upsert có điều kiện |
| Retry statement trong transaction đã failed | Database có thể từ chối mọi statement tiếp theo | Rollback transaction rồi retry toàn bộ use case trong transaction mới |
| Đặt backoff bên trong transaction dài | Có thể giữ connection trong thời gian chờ | Đặt retry ngoài transactional publisher khi cần transaction mới mỗi attempt |
| Retry sau cancellation | Công việc tiếp tục dù caller đã rời đi | Kiểm thử cancel và không tạo attempt tiếp theo |
| Chỉ test complete, không test error/cancel | Bỏ sót cleanup ở các đường kết thúc khác | Có test riêng cho complete, error và cancel |
| Coi `doFinally(CANCEL)` là bằng chứng connection đã release | Callback chỉ quan sát signal ở pipeline | Kiểm tra pool metrics và thực hiện query kế tiếp |
| Dùng mock connection làm bằng chứng driver thật | Không kiểm tra protocol/cursor/cleanup của driver | Chạy integration test với database/driver mục tiêu |
| Pool test có maxSize lớn | Leak nhỏ khó quan sát | Dùng pool `maxSize = 1` trong test lifecycle |
| Test không đóng pool | Resource còn tồn tại giữa các test | Đóng pool/client/container trong teardown |
| Test dùng transaction ngoài bao quanh test | Có thể che kết quả commit/rollback của service | Xác minh bằng query mới sau khi transaction service kết thúc |
| Chỉ test WebTestClient in-process | Có thể không mô phỏng socket disconnect thật | Bổ sung end-to-end test với HTTP client thực khi cần |

## 20. Quy trình xây dựng bộ test

Với một service R2DBC có timeout, retry và cancellation, có thể triển khai theo thứ tự:

1. **Test tín hiệu cơ bản:** xác nhận success, empty và error bằng `StepVerifier`.
2. **Test timeout logic:** dùng `Mono.never()` hoặc `TestPublisher` và virtual time.
3. **Test cancellation logic:** dùng `thenCancel()` và `TestPublisher.assertCancelled()`.
4. **Test retry:** dùng `Mono.defer`/`AtomicInteger`, xác nhận số attempt và backoff.
5. **Test retry filter:** xác nhận lỗi transient được retry còn duplicate/validation không retry.
6. **Test cancellation trong backoff:** hủy subscription và xác nhận không có attempt tiếp theo.
7. **Test idempotency:** gửi lại cùng command/key và xác nhận không tạo side effect trùng.
8. **Integration test timeout:** chạy query trên database thật và xác nhận lỗi/cleanup.
9. **Integration test pool release:** dùng pool `maxSize = 1`, hoàn tất/hủy query rồi thực hiện query mới.
10. **Integration test transaction:** xác nhận rollback khi timeout/cancel và commit khi complete.
11. **HTTP cancellation test:** đóng response consumer/request và quan sát cleanup ở server.
12. **Quan sát metrics:** kiểm tra active/idle/pending acquire và acquire duration trở về trạng thái dự kiến.

Không cần chạy mọi tình huống qua end-to-end nếu unit test đã kiểm tra logic Reactor rõ ràng. Nhưng ít nhất các hành vi phụ thuộc driver, pool và transaction phải có integration test tương ứng.

## 21. Những metric nên quan sát trong test và production

Các metric giúp phát hiện timeout/retry/cancellation có làm pool bất ổn hay không:

- Active/acquired connections.
- Idle connections.
- Pending acquire và acquire duration.
- Acquire timeout count.
- Connection creation/validation failures.
- Query/statement duration.
- Số lần retry theo operation và error category.
- Số timeout theo tầng: pool, statement, Reactor, HTTP.
- Số cancellation theo endpoint/query.
- Thời gian từ cancellation tới khi connection trở lại pool.
- Transaction duration và rollback count nếu instrumentation hỗ trợ.

Tên metric cụ thể phụ thuộc R2DBC Pool, Spring Boot và Micrometer version. Đừng giả định một tên metric giống nhau trên mọi ứng dụng. Trong test, có thể đọc pool metrics trước và sau scenario; trong production, cảnh báo theo xu hướng pending acquire, timeout và thời gian giữ connection.

Retry cần được quan sát vì nó làm tăng tổng số query. Một lỗi tạm thời nhỏ có thể trở thành cơn bão retry nếu nhiều instance cùng backoff giống nhau. Hãy ghi số attempt, operation và error category; tránh log dữ liệu nhạy cảm hoặc toàn bộ SQL bind values.

## 22. Ví dụ service có timeout và retry được kiểm soát

Ví dụ dưới đây minh họa một truy vấn đọc có thể retry khi gặp lỗi tài nguyên tạm thời:

```java
@Service
public class CustomerQueryService {

    private final CustomerRepository repository;

    private final Retry retryPolicy = Retry.backoff(
            2,
            Duration.ofMillis(100)
        )
        .maxBackoff(Duration.ofSeconds(1))
        .filter(this::isRetryable);

    public CustomerQueryService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> findById(Long id) {
        return Mono.defer(() -> repository.findById(id))
            .timeout(Duration.ofSeconds(2))
            .retryWhen(retryPolicy)
            .timeout(Duration.ofSeconds(5));
    }

    private boolean isRetryable(Throwable error) {
        return error instanceof TransientDataAccessResourceException
            || error instanceof R2dbcTransientResourceException;
    }
}
```

Trong ví dụ:

- `Mono.defer` tạo publisher repository cho mỗi lần subscribe.
- Timeout hai giây giới hạn một attempt.
- Retry tối đa hai lần sau attempt đầu cho loại lỗi đã chọn.
- Timeout năm giây giới hạn toàn bộ workflow.
- Cancellation từ caller truyền qua pipeline và dừng attempt/backoff đang chạy.

Đây là ví dụ cho thao tác đọc. Với thao tác ghi, cần thêm idempotency và cân nhắc retry toàn transaction ở đúng boundary. Các exception type cần được điều chỉnh theo driver và exception translation thực tế.

## 23. Nguyên tắc cần nhớ

- Kiểm thử cả tín hiệu reactive lẫn trạng thái connection/transaction sau complete, error và cancel.
- Phân biệt pool acquire timeout, statement timeout, Reactor timeout, transaction timeout và HTTP timeout.
- `StepVerifier.verify(Duration)` giới hạn thời gian test chờ; nó không đặt timeout cho publisher production.
- Dùng `withVirtualTime` cho timer Reactor và tạo publisher bên trong supplier.
- Virtual time không điều khiển database/network I/O thật.
- `retry` subscribe lại nguồn; với R2DBC, query/ghi có thể được thực thi lại.
- Giới hạn retry, dùng backoff/jitter và filter theo lỗi tạm thời có cấu trúc.
- Số lần retry khác tổng số attempt: ba retry có thể là bốn lần thực thi.
- Retry write cần idempotency vì lỗi có thể xảy ra sau khi database đã commit.
- Đặt retry ngoài transaction publisher khi cần rollback attempt lỗi và bắt đầu transaction mới cho lần thử tiếp theo.
- Không retry lỗi nghiệp vụ/constraint hoặc cancellation một cách mù quáng.
- Dùng `thenCancel()` và `TestPublisher.assertCancelled()` để kiểm tra cancellation ở tầng Reactive Streams.
- `doFinally(CANCEL)` chỉ quan sát cancellation, không tự chứng minh connection đã được release.
- Dùng pool `maxSize = 1` và query tiếp theo để kiểm tra connection được trả về pool.
- Test timeout/cancellation/transaction với database và R2DBC driver thực tế.
- Kiểm tra HTTP disconnect nếu endpoint stream cần giải phóng query khi client rời đi.
- Đóng pool/container sau test và tránh transaction test bên ngoài che khuất commit/rollback của service.
- Theo dõi active/idle/pending connections, acquire latency, retry count, timeout và cleanup duration.

Một bộ test R2DBC đáng tin cậy phải chứng minh được rằng timeout không để thao tác chạy vô hạn, retry không lặp side effect ngoài ý muốn, cancellation dừng công việc đang chạy và connection được trả về pool để request tiếp theo tiếp tục hoạt động. `StepVerifier` cùng virtual time kiểm tra logic tín hiệu một cách nhanh và xác định; Testcontainers hoặc database tích hợp kiểm tra driver, transaction và connection pool thật. Khi kết hợp hai lớp này với retry có giới hạn, idempotency và metric lifecycle, ứng dụng có thể xử lý lỗi tạm thời mà không biến chúng thành cạn connection hoặc tải retry dây chuyền.

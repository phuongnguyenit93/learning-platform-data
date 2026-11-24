# StepVerifier cho chuỗi Reactor và các nhánh lỗi trong Spring Cloud Gateway

Một API Gateway có thể trả đúng HTTP 200 trên đường đi thuận lợi nhưng vẫn có lỗi nghiêm trọng ở các nhánh ít gặp: downstream timeout không được xử lý, filter làm mất lỗi `onError`, response đã commit nhưng vẫn cố thay status, retry lặp một thao tác POST, hoặc cancellation không được chuyển tiếp khi client đóng kết nối. Các vấn đề ấy đặc biệt quan trọng với **SPRING_CLOUD_GATEWAY Server WebFlux** vì việc xử lý request và nhiều GatewayFilter được xây dựng bằng **Reactor `Mono`/`Flux`**.

Trong chương **Kiểm thử**, bài **StepVerifier cho chuỗi Reactor và các nhánh lỗi** hướng dẫn kiểm thử **các tín hiệu reactive** một cách có thể lặp lại: kết quả thành công, chuỗi rỗng, exception được phát ra, fallback, retry, timeout, backpressure và cancellation. Sau đó, bài áp dụng các nguyên tắc này cho custom `GatewayFilter`, route predicate, header mutation, circuit breaker, rate limiting, service discovery, xác thực và observability trong môi trường API Gateway microservices.

Mục tiêu sau bài học:

1. Giải thích vì sao `StepVerifier` kiểm tra **publisher signals**, không chỉ giá trị trả về của phương thức Java.
2. Viết assertions cho `onNext`, `onComplete`, `onError`, `Mono.empty()` và `Flux` nhiều phần tử.
3. Phân biệt lỗi **được phát ra** với lỗi **được chuyển đổi thành fallback/status**, và xác minh đúng nhánh.
4. Kiểm tra timeout/backoff bằng `VirtualTimeScheduler` mà không phải chờ thời gian thật.
5. Dùng `TestPublisher`, `PublisherProbe` và mock GatewayFilterChain để mô phỏng downstream có kiểm soát.
6. Xác định ranh giới giữa **unit tests bằng StepVerifier** và **HTTP integration tests bằng WebTestClient**.

> **Phạm vi:** Ví dụ tập trung vào **Spring Cloud Gateway Server WebFlux**, Project Reactor và `reactor-test`. Gateway **Server Web MVC** sử dụng Servlet/MVC filter abstractions khác; không đem `StepVerifier` áp lên một MVC `HandlerFilterFunction` rồi coi đó là cùng pipeline. API của Reactor Test được đối chiếu với tài liệu Reactor hiện đại; hãy dùng Reactor/Boot/Cloud BOM đúng release train, tránh chốt các số phiên bản không có bằng chứng tương thích. Các mã lỗi và URI ví dụ chỉ dành cho lab.

## 1. Mô hình tín hiệu Reactor: StepVerifier kiểm tra điều gì?

Một reactive `Publisher` không tự thực hiện toàn bộ nghiệp vụ ngay khi phương thức tạo nó được gọi. Việc xử lý thường bắt đầu khi có **subscription**.

Các tín hiệu cơ bản:

| Tín hiệu / thao tác | Ý nghĩa | StepVerifier thường dùng |
|---|---|---|
| `onSubscribe` | Subscriber nhận subscription, có thể yêu cầu dữ liệu | `expectSubscription()` |
| `request(n)` | Subscriber yêu cầu tối đa n phần tử mới theo backpressure | `thenRequest(n)` |
| `onNext(value)` | Phát một phần tử | `expectNext`, `expectNextMatches`, `assertNext` |
| `onComplete` | Kết thúc thành công | `expectComplete()`, `verifyComplete()` |
| `onError(Throwable)` | Kết thúc với lỗi | `expectError`, `expectErrorMatches`, `expectErrorSatisfies` |
| `cancel()` | Subscriber ngừng quan tâm dữ liệu | `thenCancel()` |
| Không có dữ liệu trong khoảng thời gian | Chưa có tín hiệu mong đợi | `expectNoEvent(Duration)` |
| Chờ thời gian ảo trôi qua | Kích hoạt operators phụ thuộc scheduler | `thenAwait(Duration)` |

### Một chuỗi có một terminal signal

Theo Reactor/Reactive Streams, `onComplete` và `onError` là **hai kết thúc thay thế nhau**; một publisher hợp lệ không phát cả hai cho cùng subscription.

~~~mermaid
flowchart TD
    P["Publisher: Mono / Flux"] --> S["onSubscribe"]
    S --> R["request(n)"]
    R --> N["0..N onNext"]
    N --> T{"Kết thúc ra sao?"}
    T -->|Thành công| C["onComplete"]
    T -->|Lỗi| E["onError"]
    R -.-> X["Subscriber cancel"]
    N -.-> X
~~~

**`Mono.empty()` không phải lỗi**, cũng không phải `Mono.just(null)`; Reactor không cho phát `null` như `onNext`. Chuỗi rỗng kết thúc bằng `onComplete` mà không có `onNext`. Nếu API Gateway cần trả `404` khi không có dữ liệu, phải có một quy tắc ánh xạ rõ ràng thay vì suy `empty` là lỗi.

### Đừng nhầm phương thức trả Mono với tác dụng phụ đã hoàn thành

~~~java
Mono<String> response = Mono.fromSupplier(() -> "ready");

// Dòng trên chưa chứng minh có subscription.
// StepVerifier tạo subscriber và kích hoạt kiểm tra các tín hiệu:
StepVerifier.create(response)
    .expectNext("ready")
    .verifyComplete();
~~~

Đoạn code dùng trong **test**; ở production, framework WebFlux/Gateway chịu trách nhiệm subscription. Không tự `subscribe()` trong filter hoặc controller để “chạy cho chắc”.

## 2. Thêm dependency thử nghiệm đúng release train

Trong ứng dụng Gateway Server WebFlux dùng Spring Boot/Spring Cloud BOM phù hợp:

~~~groovy
dependencies {
    // Starter tên khác nhau giữa các release train.
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'

    // JUnit Jupiter, AssertJ, Spring Test, WebTestClient tùy starter.
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // StepVerifier, TestPublisher, PublisherProbe, virtual-time test APIs.
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

**Không thêm `reactor-test` vào production runtime chỉ để Gateway hoạt động.** Đây là thư viện dành cho unit/integration tests. Các module `reactor-core` và `reactor-test` cần tương thích; ưu tiên BOM do Spring Boot quản lý.

Ở các bản Gateway cũ, starter có thể là `spring-cloud-starter-gateway`; với Gateway Server Web MVC, web stack khác. Hãy kiểm tra tên artifact theo đúng release train thay vì trộn dependencies từ nhiều thế hệ.

### Các imports thường gặp

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.TestPublisher;
import reactor.test.publisher.PublisherProbe;

import static org.junit.jupiter.api.Assertions.*;
~~~

Không phải ví dụ nào cũng cần đủ các imports. Hãy coi từng code block như một bài test độc lập, dùng imports cần thiết theo lớp tương ứng.

## 3. StepVerifier cơ bản: Mono thành công và Flux có thứ tự

Một `Mono<T>` có thể phát **tối đa một giá trị** rồi hoàn thành; `Flux<T>` có thể phát nhiều giá trị.

~~~java
package example.gateway.testing;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class BasicSignalsTest {

    @Test
    void monoEmitsOneValueThenCompletes() {
        Mono<String> result =
            Mono.just("catalog").map(String::toUpperCase);

        StepVerifier.create(result)
            .expectNext("CATALOG")
            .verifyComplete();
    }

    @Test
    void fluxEmitsValuesInOrderThenCompletes() {
        Flux<Integer> result =
            Flux.just(1, 2, 3).map(n -> n * 2);

        StepVerifier.create(result)
            .expectNext(2, 4, 6)
            .verifyComplete();
    }
}
~~~

Lời giải thích:

1. `StepVerifier.create(publisher)` định nghĩa kịch bản; nó sẽ subscribe khi `verify...` được gọi.
2. `expectNext(2,4,6)` kiểm tra **thứ tự và giá trị** của `onNext`.
3. `verifyComplete()` xác nhận terminal `onComplete` và thực thi quá trình verify.
4. Nếu thay `Flux.just(1,2,3)` bằng `Flux.just(1,2,3,4)`, test **không còn đúng**, vì còn phần tử không mong đợi trước terminal.

### Không quên bước verify

~~~java
// PHẢN VÍ DỤ: chỉ cấu hình script, chưa kích hoạt kiểm thử.
StepVerifier.create(Mono.just("ok"))
    .expectNext("ok")
    .expectComplete();

// CÓ verify:
StepVerifier.create(Mono.just("ok"))
    .expectNext("ok")
    .expectComplete()
    .verify();
~~~

Nhiều lỗi reactive lọt qua CI chỉ vì test đã tạo StepVerifier nhưng **không gọi `verify()`/`verifyComplete()`/`verifyError()`**.

## 4. Các kiểu assertion giá trị

| API | Khi dùng | Điều cần tránh |
|---|---|---|
| `expectNext("ok")` | Biết chính xác giá trị | Kỳ vọng object với `equals` không phù hợp |
| `expectNextMatches(v -> ...)` | Chỉ cần ràng buộc theo predicate | Predicate quá lỏng khiến test pass sai |
| `assertNext(v -> ...)` | Cần nhiều JUnit assertions cho value | Assertion trong lambda có thể fail trực tiếp |
| `expectNextCount(n)` | Chỉ cần kiểm số lượng phần tử | Không phát hiện dữ liệu sai |
| `expectNextSequence(list)` | So danh sách có thứ tự | Danh sách nguồn phải có expected values đúng |
| `thenConsumeWhile(...)` | Duyệt một dãy khi không biết số lượng cụ thể | Có thể vô tình nuốt dữ liệu bất thường |
| `as("mô tả")` | Gắn tên cho assertion ngay trước | Không thay thế thông báo lỗi nghiệp vụ |
| `scenarioName(...)` | Đặt tên toàn bộ kịch bản | Không sửa được logic test sai |

### Kiểm cấu trúc response thay vì serialize rồi so chuỗi

~~~java
record GatewayResult(String routeId, int status, String body) {}

@Test
void checksStructuredResponse() {
    Mono<GatewayResult> response =
        Mono.just(new GatewayResult("catalog-read", 200, "OK"));

    StepVerifier.create(response)
        .assertNext(value -> {
            assertEquals("catalog-read", value.routeId());
            assertEquals(200, value.status());
            assertEquals("OK", value.body());
        })
        .verifyComplete();
}
~~~

Một object có nhiều trường nên được kiểm từng invariant quan trọng. Không dùng `expectNextCount(1)` để kết luận response có status đúng.

### Thêm tên kịch bản để debug

~~~java
StepVerifier.create(
        Flux.just("A", "B"),
        StepVerifierOptions.create().scenarioName("route-order"))
    .expectNext("A")
    .as("route được xét trước")
    .expectNext("B")
    .as("route được xét sau")
    .verifyComplete();
~~~

Tên giúp tìm lỗi trong các test suites lớn có nhiều kịch bản route/filter. Nếu `assertNext` tự ném AssertionError, tên không nhất thiết được đính vào message của thư viện assertion ngoài StepVerifier.

## 5. Mono.empty, switchIfEmpty và lỗi không tìm thấy dữ liệu

Một nhánh “không có dữ liệu” cần được thiết kế theo hợp đồng API, không tự gọi là lỗi HTTP.

~~~java
import java.util.NoSuchElementException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void emptyPublisherCompletesWithoutValue() {
    StepVerifier.create(Mono.<String>empty())
        .verifyComplete();
}

@Test
void missingResourceMapsToDomainError() {
    Mono<String> result = Mono.<String>empty()
        .switchIfEmpty(
            Mono.error(new NoSuchElementException("item not found")));

    StepVerifier.create(result)
        .expectErrorMatches(error ->
            error instanceof NoSuchElementException
            && "item not found".equals(error.getMessage()))
        .verify();
}
~~~

So sánh:

| Publisher | Tín hiệu | Test mong đợi |
|---|---|---|
| `Mono.just("item")` | onNext("item") → onComplete | `expectNext` → `verifyComplete` |
| `Mono.empty()` | onComplete | `verifyComplete` |
| `Mono.error(new NotFoundException(...))` | onError | `expectError...` → `verify` |
| `Mono.never()` | Không có terminal | Phải cancel hoặc dùng timeout |
| `Mono.justOrEmpty(null)` | onComplete | Không được kỳ vọng onNext(null) |

Ở Gateway, mapping `NoSuchElementException` thành HTTP 404 **không tự xảy ra trong một GatewayFilter unit test**. Controller exception handler, Spring Security hoặc cơ chế HTTP response mapping có trách nhiệm riêng; StepVerifier chỉ kiểm các **signals của Mono**.

## 6. Các nhánh lỗi: expectError, expectErrorMatches và expectErrorSatisfies

Một sequence có thể phát `onError` do lỗi input, backend, network, timeout hoặc bug của filter. Kiểm thử nhánh lỗi nên xác nhận **loại lỗi, thông điệp/nguồn gốc và hậu quả**, không chỉ “có exception”.

~~~java
import java.io.IOException;
import java.util.concurrent.TimeoutException;

@Test
void checksErrorType() {
    Mono<String> result =
        Mono.error(new IOException("connection reset"));

    StepVerifier.create(result)
        .expectError(IOException.class)
        .verify();
}

@Test
void checksErrorPredicate() {
    Mono<String> result =
        Mono.error(new IllegalArgumentException("invalid route id"));

    StepVerifier.create(result)
        .expectErrorMatches(error ->
            error instanceof IllegalArgumentException
            && error.getMessage().contains("route id"))
        .verify();
}

@Test
void checksErrorFieldsWithAssertions() {
    Mono<String> result =
        Mono.error(new TimeoutException("origin exceeded deadline"));

    StepVerifier.create(result)
        .expectErrorSatisfies(error -> {
            assertInstanceOf(TimeoutException.class, error);
            assertEquals("origin exceeded deadline", error.getMessage());
        })
        .verify();
}
~~~

### Không chọn assertion quá yếu

~~~java
// Quá yếu: IllegalStateException và SecurityException đều khiến test pass.
StepVerifier.create(Mono.error(new IllegalStateException("bug")))
    .expectError()
    .verify();

// Tốt hơn khi API cần lỗi cụ thể:
StepVerifier.create(Mono.error(new IllegalStateException("bug")))
    .expectError(IllegalStateException.class)
    .verify();
~~~

`expectError()` hữu ích khi chỉ quan tâm có terminal error, nhưng với logic Gateway chứa retry/circuit breaker/security, hãy dùng **assertion cụ thể theo hợp đồng** để phát hiện sai phân loại lỗi.

## 7. Kiểm thử onErrorMap và giữ nguyên nguyên nhân gốc

Trong Gateway, một lỗi HTTP client có thể được chuyển thành lỗi nghiệp vụ để tầng cao hơn quyết định `502`, `503` hay `504`. `onErrorMap` thay **lỗi được phát ra**, chứ không biến nó thành response thành công.

~~~java
import java.io.IOException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void mapsTransportFailureAndPreservesCause() {
    Mono<String> result = Mono.<String>error(
        new IOException("backend reset"))
        .onErrorMap(IOException.class,
            error -> new IllegalStateException(
                "DOWNSTREAM_UNAVAILABLE", error));

    StepVerifier.create(result)
        .expectErrorSatisfies(error -> {
            assertInstanceOf(IllegalStateException.class, error);
            assertEquals("DOWNSTREAM_UNAVAILABLE", error.getMessage());
            assertInstanceOf(IOException.class, error.getCause());
        })
        .verify();
}
~~~

**Điểm cần kiểm:**

- Lỗi gốc vẫn được giữ trong `cause` để phân tích/tracing phù hợp.
- Không ném thông điệp HTTP client chứa token, query nhạy cảm hoặc hostname nội bộ ra client.
- Không gộp mọi lỗi thành một lớp chung nếu retry policy cần phân biệt lỗi có thể retry và lỗi 4xx.
- `onErrorMap` có thể làm thay đổi loại lỗi mà Retry/CircuitBreaker nhìn thấy; cần test thứ tự operator.

### Thứ tự operator làm thay đổi hành vi

Hai chuỗi sau không nhất thiết tương đương:

~~~java
source.onErrorMap(IOException.class, this::wrap)
      .retryWhen(retrySpec);

source.retryWhen(retrySpec)
      .onErrorMap(IOException.class, this::wrap);
~~~

Ở chuỗi thứ nhất, retry thấy **lỗi đã được map**; ở chuỗi thứ hai, retry thấy **lỗi gốc** trước khi map. Nếu `retrySpec.filter(...)` lọc theo class exception, khác biệt này có thể quyết định có retry hay không.

## 8. Kiểm thử onErrorResume: fallback có đúng nhánh không?

`onErrorResume` nhận một terminal error từ upstream, rồi **đăng ký publisher khác** để phục vụ giá trị thay thế hoặc phát lỗi mới. Đây không phải phép khôi phục mọi lỗi một cách an toàn.

~~~java
import java.io.IOException;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void timeoutUsesDefinedFallback() {
    Mono<String> result = Mono.<String>error(
        new TimeoutException("orders timeout"))
        .onErrorResume(TimeoutException.class,
            error -> Mono.just("DEGRADED"));

    StepVerifier.create(result)
        .expectNext("DEGRADED")
        .verifyComplete();
}

@Test
void nonTimeoutErrorPropagates() {
    Mono<String> result = Mono.<String>error(
        new IOException("broken pipe"))
        .onErrorResume(TimeoutException.class,
            error -> Mono.just("DEGRADED"));

    StepVerifier.create(result)
        .expectError(IOException.class)
        .verify();
}
~~~

Hai test quan trọng như nhau: **lỗi được hỗ trợ fallback**, và **lỗi không nằm trong whitelist không được che giấu**.

### Fallback thành công có thể vẫn sai về HTTP contract

Nếu Gateway gặp timeout từ service xử lý thanh toán, trả body `{"status":"PAID"}` từ một fallback tự tạo là nguy hiểm. Một `Mono.just(...)` thành công chỉ chứng minh publisher đã phát phần tử, **không chứng minh trạng thái nghiệp vụ đúng**.

Test phải có **negative assertions**: không fallback khi lỗi authentication/authorization, không trả dữ liệu user A cho user B, không đổi 503 thành 200 ngoài contract, không replay POST không idempotent.

## 9. Kiểm thử thứ tự pre/post trong GatewayFilterChain

Một custom GatewayFilter có thể thực hiện logic trước khi gọi chain, sau khi chain hoàn thành hoặc khi có lỗi. Trong Reactor, **vị trí operator** quyết định lúc tác dụng phụ được thực hiện.

~~~mermaid
sequenceDiagram
    participant T as StepVerifier
    participant F as Custom GatewayFilter
    participant C as Fake GatewayFilterChain
    T->>F: subscribe()
    F->>F: pre logic
    F->>C: chain.filter(exchange)
    C-->>F: onComplete hoặc onError
    alt onComplete
        F->>F: post-success
        F-->>T: onComplete
    else onError
        F->>F: doOnError / onErrorResume
        F-->>T: onError hoặc fallback complete
    end
~~~

### Test thứ tự bằng Mono.defer và state cục bộ

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void performsPreThenChainThenPostOnSuccess() {
    List<String> events = new ArrayList<>();

    GatewayFilter filter = (exchange, chain) ->
        Mono.defer(() -> {
            events.add("pre");
            return chain.filter(exchange)
                .doOnSuccess(unused -> events.add("post"));
        });

    GatewayFilterChain downstream = exchange ->
        Mono.fromRunnable(() -> events.add("downstream"));

    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/catalog/42"));

    StepVerifier.create(filter.filter(exchange, downstream))
        .expectComplete()
        .verify();

    assertEquals(List.of("pre", "downstream", "post"), events);
}
~~~

`Mono.defer` bảo đảm phần `pre` trong ví dụ được thực thi **khi có subscription**, không chỉ khi test gọi `filter.filter(exchange, chain)`. `doOnSuccess` phù hợp với `Mono<Void>` khi chain hoàn thành; với error, callback đó **không chạy**.

### Nhánh lỗi không được gọi post-success

~~~java
@Test
void skipsPostSuccessWhenDownstreamFails() {
    List<String> events = new ArrayList<>();

    GatewayFilter filter = (exchange, chain) ->
        Mono.defer(() -> {
            events.add("pre");
            return chain.filter(exchange)
                .doOnSuccess(unused -> events.add("post"))
                .doOnError(error -> events.add("error"));
        });

    GatewayFilterChain downstream = exchange ->
        Mono.error(new IllegalStateException("downstream failed"));

    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/catalog/42"));

    StepVerifier.create(filter.filter(exchange, downstream))
        .expectError(IllegalStateException.class)
        .verify();

    assertEquals(List.of("pre", "error"), events);
}
~~~

Ở ứng dụng thật, `doFinally(signal)` có thể quan sát **onComplete, onError và cancel**, nhưng cần đặc biệt thận trọng với assertions trên side effects khi callback `doFinally` xảy ra sau terminal signal; không thiết kế test bị race hoặc logging blocking trên event loop.

## 10. Ví dụ hoàn chỉnh: kiểm thử GatewayFilter chặn request và thay header

Giả sử nhóm Gateway phát triển một filter lab với chính sách:

- Nếu request có `X-Lab-Mode: blocked`, trả **403** và **không gọi downstream chain**.
- Nếu không bị chặn, đặt header `X-Verified-Lab: yes` rồi chuyển tiếp.
- Header `X-Verified-Lab` do Gateway sở hữu; nếu client gửi giá trị giả, filter phải **ghi đè**, không giữ multi-value.
- Không đọc body hoặc can thiệp path/query.

### Implementation của filter

~~~java
package example.gateway.testing;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;

public final class LabGuardFilter {

    private LabGuardFilter() {}

    public static GatewayFilter create() {
        return (exchange, chain) -> {
            String mode = exchange.getRequest().getHeaders()
                .getFirst("X-Lab-Mode");

            if ("blocked".equals(mode)) {
                exchange.getResponse()
                    .setStatusCode(HttpStatus.FORBIDDEN);
                return exchange.getResponse().setComplete();
            }

            ServerHttpRequest request = exchange.getRequest()
                .mutate()
                .headers(headers ->
                    headers.set("X-Verified-Lab", "yes"))
                .build();

            return chain.filter(
                exchange.mutate().request(request).build());
        };
    }
}
~~~

**Không sử dụng `X-Lab-Mode` trong production làm quyền truy cập thật.** Client có thể giả mạo header này. Ví dụ chỉ nhằm thực hành nhánh thành công/short-circuit của filter; xác thực Bearer token và phân quyền production thuộc Spring Security/backend authorization.

### Test thành công: chain được gọi đúng và header được ghi đè

~~~java
package example.gateway.testing;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class LabGuardFilterTest {

    @Test
    void forwardsAndOverwritesClientSuppliedHeader() {
        GatewayFilter filter = LabGuardFilter.create();

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/api/orders/42?sort=price")
                .header("X-Verified-Lab", "forged"));

        AtomicReference<ServerWebExchange> forwarded =
            new AtomicReference<>();

        GatewayFilterChain chain = nextExchange -> {
            forwarded.set(nextExchange);
            return Mono.empty();
        };

        StepVerifier.create(filter.filter(exchange, chain))
            .expectComplete()
            .verify();

        assertNotNull(forwarded.get());
        assertEquals("yes", forwarded.get()
            .getRequest().getHeaders()
            .getFirst("X-Verified-Lab"));
        assertEquals(1, forwarded.get()
            .getRequest().getHeaders()
            .get("X-Verified-Lab").size());
        assertEquals("/api/orders/42",
            forwarded.get().getRequest().getURI().getPath());
        assertEquals("sort=price",
            forwarded.get().getRequest().getURI().getRawQuery());
    }
}
~~~

**Đây là unit test filter**, không có Netty server hay HTTP request đi vào backend thật. `GatewayFilterChain` giả lập giúp ta xác minh **exchange sau khi mutate** và hành vi không làm mất path/query.

### Test chặn: HTTP status 403 và chain không chạy

~~~java
@Test
void blockedRequestCompletesWithoutCallingChain() {
    GatewayFilter filter = LabGuardFilter.create();

    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/orders/42")
            .header("X-Lab-Mode", "blocked"));

    AtomicBoolean forwarded = new AtomicBoolean(false);

    GatewayFilterChain chain = next -> {
        forwarded.set(true);
        return Mono.empty();
    };

    StepVerifier.create(filter.filter(exchange, chain))
        .verifyComplete();

    assertFalse(forwarded.get());
    assertEquals(HttpStatus.FORBIDDEN,
        exchange.getResponse().getStatusCode());
}
~~~

Bổ sung imports phù hợp nếu chép test này vào class riêng:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.http.HttpStatus;
~~~

**Một `Mono<Void>` hoàn thành không có nghĩa HTTP 200.** Ở nhánh bị chặn, publisher phát `onComplete` nhưng response status là `403` vì filter đã set. Do đó test phải kiểm **cả terminal signal lẫn response status/side effects**.

## 11. Lỗi downstream trong filter: phát lỗi hay đổi thành HTTP 504?

Giả sử một GatewayFilter gọi `chain.filter(exchange)`, downstream chain phát một `TimeoutException`. Có hai contract khác nhau:

1. **Propagate lỗi** để một tầng xử lý khác quyết định response.
2. **Bắt một loại lỗi cụ thể**, đổi thành status HTTP (ví dụ 504) và kết thúc response.

### Nếu không có mapping, StepVerifier phải thấy onError

~~~java
@Test
void propagatesBackendErrorWithoutSilencingIt() {
    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/orders/42"));

    GatewayFilterChain chain = next ->
        Mono.error(new IllegalStateException("backend failed"));

    StepVerifier.create(
            LabGuardFilter.create().filter(exchange, chain))
        .expectErrorMatches(error ->
            error instanceof IllegalStateException
            && error.getMessage().contains("backend failed"))
        .verify();
}
~~~

**Không tự assert response sẽ là HTTP 500 ở unit test này**: ta chỉ gọi `GatewayFilter` và fake chain, không khởi động hoàn chỉnh cơ chế chuyển exceptions thành HTTP response của WebFlux/Gateway.

### Filter có lỗi timeout được map thành 504

~~~java
import java.util.concurrent.TimeoutException;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.http.HttpStatus;
import reactor.core.publisher.Mono;

GatewayFilter timeoutTo504 = (exchange, chain) ->
    chain.filter(exchange)
        .onErrorResume(TimeoutException.class, error -> {
            // Khi response đã commit, không còn đổi status an toàn.
            if (exchange.getResponse().isCommitted()) {
                return Mono.error(error);
            }
            exchange.getResponse().setStatusCode(
                HttpStatus.GATEWAY_TIMEOUT);
            return exchange.getResponse().setComplete();
        });
~~~

Và test:

~~~java
var exchange = MockServerWebExchange.from(
    MockServerHttpRequest.get("/api/orders/42"));

GatewayFilterChain timeoutChain = next ->
    Mono.error(new TimeoutException("origin timed out"));

StepVerifier.create(timeoutTo504.filter(exchange, timeoutChain))
    .verifyComplete();

assertEquals(HttpStatus.GATEWAY_TIMEOUT,
    exchange.getResponse().getStatusCode());
~~~

Các snippets thuộc **một ngữ cảnh test có sẵn imports**. `TimeoutException` chỉ là class mô phỏng; timeout Reactor Netty thực tế có thể được biểu diễn bằng **exception khác**. Chỉ catch whitelist exception đã biết, và kiểm tra loại lỗi thực bằng integration tests. **Không bắt mọi `Throwable` rồi trả 200/504**, vì có thể che lỗi security, bug lập trình hoặc lỗi response đã commit.

## 12. TestPublisher: điều khiển tín hiệu downstream từng bước

`TestPublisher<T>` cho phép test tự phát `onNext`, `onComplete` hoặc `onError` vào một publisher mà operator đang subscribe. Nó hữu ích khi muốn tạo **backend giả định trả dữ liệu rồi lỗi**, lỗi kết nối bất ngờ hoặc phản hồi trễ mà không khởi động server.

~~~java
package example.gateway.testing;

import java.io.IOException;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class ManualSignalTest {

    @Test
    void observesValueThenTransportFailure() {
        TestPublisher<String> upstream = TestPublisher.create();

        Flux<String> pipeline = upstream.flux()
            .map(String::toUpperCase);

        StepVerifier.create(pipeline)
            .then(() -> upstream.next("first"))
            .expectNext("FIRST")
            .then(() -> upstream.error(
                new IOException("connection reset")))
            .expectError(IOException.class)
            .verify();
    }
}
~~~

**Điểm mạnh:** quyết định tín hiệu được phát **sau khi StepVerifier đã subscribe** bằng `then(...)`; không cần sleep để “đợi backend”.

**Điểm giới hạn:** `TestPublisher` mô phỏng signals, **không mô phỏng HTTP status, TLS, framing, Netty timeout, connection pooling hay Gateway filter order**. Những thứ đó cần integration tests hoặc test tại lớp transport phù hợp.

### Tránh `Thread.sleep`

~~~java
// Không nên để test phụ thuộc thời gian máy CI.
Thread.sleep(500);
assertEquals(...);
~~~

Hành vi asynchronous có thể thay đổi với CPU contention, GC hoặc scheduler. Dùng TestPublisher/virtual time/explicit publisher assertions thay vì sleep cố định khi kiểm thử Reactor operators.

## 13. PublisherProbe: chứng minh đúng nhánh fallback đã được subscribe

Có trường hợp kết quả cuối giống nhau nhưng ta vẫn cần biết **nhánh nào thực sự chạy**. `PublisherProbe` theo dõi subscription, request và cancel của một publisher.

~~~java
import java.util.concurrent.TimeoutException;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

@Test
void fallbackBranchIsSubscribedOnTimeout() {
    PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("cached-safe-value"));

    Mono<String> result = Mono.<String>error(
        new TimeoutException("origin down"))
        .onErrorResume(TimeoutException.class,
            error -> fallback.mono());

    StepVerifier.create(result)
        .expectNext("cached-safe-value")
        .verifyComplete();

    fallback.assertWasSubscribed();
    fallback.assertWasRequested();
}
~~~

Test nhánh **không phải fallback**:

~~~java
@Test
void healthyResponseDoesNotSubscribeToFallback() {
    PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("cached-safe-value"));

    Mono<String> result = Mono.just("fresh")
        .onErrorResume(TimeoutException.class,
            error -> fallback.mono());

    StepVerifier.create(result)
        .expectNext("fresh")
        .verifyComplete();

    fallback.assertWasNotSubscribed();
}
~~~

Khi Gateway có circuit breaker, fallback, `switchIfEmpty`, cache lookup hoặc conditional downstream calls, **PublisherProbe** giúp kiểm tra “publisher phụ có được dùng không?” mà không cần đếm log message.

### Error fallback không đồng nghĩa response nên là HTTP 200

Nếu “cached-safe-value” là dữ liệu riêng tư hoặc đã hết TTL, fallback thành công có thể vẫn vi phạm hợp đồng. Test nên kèm **freshness, user/tenant isolation, HTTP status và Cache-Control** ở tầng phù hợp. PublisherProbe chỉ chứng minh **luồng điều khiển**, không chứng minh tính đúng đắn nghiệp vụ.

## 14. Virtual time: kiểm thử timeout mà không chờ thật

Một lỗi hay xảy ra khi kiểm thử Retry/timeout là chờ nhiều giây hoặc phút bằng thời gian thật, làm test chậm/flaky. `StepVerifier.withVirtualTime(...)` cho phép điều khiển **virtual scheduler** của Reactor.

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void verifiesDelayedSignalWithoutWaitingOneHour() {
    StepVerifier.withVirtualTime(
            () -> Mono.delay(Duration.ofHours(1))
                .map(value -> "ready"))
        .expectSubscription()
        .expectNoEvent(Duration.ofMinutes(59))
        .thenAwait(Duration.ofMinutes(1))
        .expectNext("ready")
        .verifyComplete();
}
~~~

Những điểm quan trọng:

1. **Publisher chứa time operators phải được tạo bên trong supplier `() -> ...`.**
2. `expectSubscription()` phải đứng trước `expectNoEvent(...)`, vì subscription cũng được xem là một event.
3. `thenAwait(...)` tiến đồng hồ ảo; `expectNoEvent(...)` vừa tiến thời gian vừa kiểm tra không có tín hiệu quá sớm.
4. `verifyComplete()` chạy kịch bản và xác minh signal cuối, không chờ một giờ thật.
5. `withVirtualTime` chỉ thay những schedulers được Reactor Test quản lý, **không tự giả lập Netty socket, DNS, TLS, Redis hoặc một clock tự tạo bên ngoài**.

### Test timeout operator

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

@Test
void timeoutProducesOnErrorAfterFiveVirtualSeconds() {
    StepVerifier.withVirtualTime(
            () -> Mono.<String>never()
                .timeout(Duration.ofSeconds(5)))
        .expectSubscription()
        .expectNoEvent(Duration.ofSeconds(4))
        .thenAwait(Duration.ofSeconds(1))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(2));
}
~~~

`verify(Duration.ofSeconds(2))` ở đây là **timeout thời gian thật của chính test**, để tránh trường hợp kịch bản lỗi và treo CI. Nó **khác** với timeout nghiệp vụ 5 giây ảo được kiểm tra trong publisher.

### Những trường hợp virtual time có thể làm test treo

- Tạo `Mono.delay` hoặc `Retry.backoff` **trước** supplier của `withVirtualTime`, khiến operator dùng scheduler khác.
- Đợi `expectNext` trước khi tiến virtual clock đủ lâu.
- Operator dùng scheduler được cung cấp riêng, không bị thay bằng virtual scheduler.
- Blocking I/O bên trong publisher, không phụ thuộc scheduler ảo.
- Sequence vô hạn/hot source dùng thời gian hoặc execution model phức tạp.

Đừng dùng virtual time để khẳng định **connect timeout thực tới downstream** hay **TLS handshake timeout** đã đúng; cần kiểm thử HTTP client/runtime thật.

## 15. Retry.backoff: đếm attempts và kiểm nhánh hết lượt thử

Ở Gateway, Retry có thể làm một request client tạo nhiều outbound attempts. Kiểm thử `Retry` của Reactor ở mức publisher giúp xác minh **khi nào retry, retry tối đa bao nhiêu và lỗi cuối ra sao**.

### Thành công ở lần thứ ba

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

@Test
void retrySucceedsOnThirdSubscription() {
    AtomicInteger subscriptions = new AtomicInteger();

    StepVerifier.withVirtualTime(() ->
            Mono.defer(() -> {
                int attempt = subscriptions.incrementAndGet();
                if (attempt < 3) {
                    return Mono.<String>error(
                        new IOException("temporary #" + attempt));
                }
                return Mono.just("ok");
            }).retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                    .jitter(0d)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectNext("ok")
        .expectComplete()
        .verify(Duration.ofSeconds(2));

    assertEquals(3, subscriptions.get());
}
~~~

**`Retry.backoff(2, ...)` nghĩa là tối đa hai retries sau lần đầu**, vì vậy có thể có **ba subscriptions/attempts**. `jitter(0d)` tắt randomness để virtual-time test có lịch deterministic; production thường nên giữ jitter hợp lý để tránh đồng loạt retry.

### Khi hết retries, kiểu lỗi có thể khác lỗi gốc

~~~java
@Test
void retryExhaustionIsNotAccidentallySuccessful() {
    AtomicInteger subscriptions = new AtomicInteger();

    StepVerifier.withVirtualTime(() ->
            Mono.defer(() -> {
                subscriptions.incrementAndGet();
                return Mono.<String>error(
                    new IOException("always unavailable"));
            }).retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                    .jitter(0d)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectErrorMatches(error ->
            reactor.core.Exceptions.isRetryExhausted(error))
        .verify(Duration.ofSeconds(2));

    assertEquals(3, subscriptions.get());
}
~~~

Reactor `Retry` có thể dùng wrapper `retry exhausted` khi vượt giới hạn; nên kiểm tra **`Exceptions.isRetryExhausted(error)`** và nguyên nhân gốc nếu hợp đồng yêu cầu, thay vì mặc định lỗi cuối luôn là `IOException` trực tiếp. Với Gateway `Retry GatewayFilter`, việc lọc status codes và HTTP methods còn thêm lớp routing/response logic; **unit test `Retry.backoff` không thay thế integration test của filter Retry thực tế**.

### Mã HTTP ảnh hưởng Retry

| Tình huống | Không nên giả định |
|---|---|
| HTTP 503 từ backend | Mọi Reactor Mono tự biến thành `onError` |
| HTTP 429 + Retry-After | `Retry.backoff` tự đọc header HTTP |
| POST đã gửi một phần body | Request được replay an toàn |
| Retry filter ở Gateway | Cùng một attempt count như code Reactor đơn giản |
| CircuitBreaker + Retry | Luôn cùng thứ tự và số lần gọi |
| Client đã hủy request | Backend không còn side effect |

**HTTP response 503 là một `ResponseEntity`/response status**, không nhất thiết là `onError` trong Reactor. Một HTTP client phải có policy cụ thể để chuyển status thành error hoặc để filter quan sát và quyết định retry.

## 16. Backpressure và cancellation: không chỉ kiểm onNext

Khi upstream nhanh hơn downstream hoặc client ngắt kết nối, reactive pipeline phải xử lý demand/cancellation. `StepVerifier.create(publisher, initialRequest)` có thể bắt đầu với demand bằng 0 để kiểm chứng backpressure.

### Kiểm soát `request(n)`

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void emitsOnlyAsDemandIsRequested() {
    Flux<Integer> numbers = Flux.range(1, 3);

    StepVerifier.create(numbers, 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(2)
        .expectNext(2, 3)
        .verifyComplete();
}
~~~

Nếu operator của bạn **phát vượt demand** (không tuân thủ Reactive Streams), có thể có lỗi hoặc hành vi khác nhau tùy implementation; test cần dùng source kiểm soát demand thật. `Flux.range` tuân thủ demand và là baseline thuận tiện.

### Kiểm tra cancel của luồng dài

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void cancelsLongLivedStream() {
    StepVerifier.withVirtualTime(
            () -> Flux.interval(Duration.ofSeconds(1)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectNext(0L)
        .thenCancel()
        .verify();
}
~~~

Việc `thenCancel()` thành công có nghĩa **subscriber đã hủy subscription** theo kịch bản, không tự chứng minh TCP socket đã đóng ngay hoặc backend đã hủy một tác vụ lưu file. Với Gateway streaming/SSE/WebSocket, test integration phải kiểm tra connection resources, buffer cleanup và side effects riêng.

### Cancellation không phải terminal HTTP response

Nếu client đóng kết nối giữa lúc download, bạn không thể luôn gửi một HTTP 503 mới vì response có thể đã commit hoặc socket không còn. Không viết `onErrorResume` toàn cục trả fallback JSON cho mọi `cancel`: cancellation là một **signal điều khiển subscription**, không phải `onError`.

## 17. Reactor Context: correlation ID và phân tách request

Gateway thường truyền trace ID, request ID hoặc metadata qua Reactor `Context`. Nó **khác ThreadLocal** và khác HTTP headers.

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;

@Test
void seesContextValueAcrossReactiveOperators() {
    Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get("traceId")));

    StepVerifier.create(result,
            StepVerifierOptions.create().withInitialContext(
                Context.of("traceId", "trace-lab-123")))
        .expectAccessibleContext()
        .contains("traceId", "trace-lab-123")
        .then()
        .expectNext("trace-lab-123")
        .verifyComplete();
}
~~~

### Những giới hạn cần biết

- `Context` truyền theo **subscriber/reactive chain**, không phải một Map toàn cục.
- `contextWrite(...)` tác động theo hướng của subscription, khác thứ tự các operator trong chuỗi.
- Một custom filter tự `subscribe()` có thể làm mất context và gây lệch tracing.
- Không đặt raw access token, session cookies hoặc PII không cần thiết vào logs/metrics tags từ context.
- `StepVerifier` kiểm tra đúng Reactor Context nhưng **không chứng minh HTTP trace headers đã propagate qua Reactor Netty**. Cần integration test/observability tooling khi muốn xác minh cả hai hops.

## 18. verifyThenAssertThat và discarded/dropped signals

Sau khi đã xác minh terminal expectation, `verifyThenAssertThat()` cho phép kiểm thêm trạng thái của verifier, chẳng hạn có phần tử bị **drop** hoặc **discard** hay không.

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void filteredElementIsDiscarded() {
    StepVerifier.create(
            Flux.just(1, 2, 3)
                .filter(n -> n % 2 == 1))
        .expectNext(1, 3)
        .expectComplete()
        .verifyThenAssertThat()
        .hasDiscarded(2)
        .hasNotDroppedElements()
        .hasNotDroppedErrors();
}
~~~

**Discard khác dropped:**

- **Discard** có thể là hành vi **bình thường** của operator như `filter` loại một phần tử theo predicate, nếu operator hỗ trợ discard hook.
- **Dropped** mô tả tín hiệu không còn subscriber nhận hợp lệ (ví dụ tín hiệu sau termination) và có thể chỉ ra publisher vi phạm hợp đồng.
- Với pooled `DataBuffer` trong Gateway, việc drop/discard có thể liên quan **release buffers**, nhưng test `hasDiscarded(...)` trên integer **không chứng minh byte buffer đã được giải phóng**.

`verifyThenAssertThat` và TestPublisher hooks nên được dùng cẩn thận khi test song song, vì hooks/schedulers có thể tương tác với process-wide state. Đừng bật/ghi đè Reactor Hooks toàn cục trong từng test mà không cleanup.

## 19. StepVerifier với body Flux trong custom Gateway filters

Trong WebFlux, body request là `Flux<DataBuffer>`. Một filter đọc body để log hoặc kiểm tra JSON có thể:

- Consume body làm downstream không còn dữ liệu.
- Buffer toàn bộ upload lớn vào RAM.
- Quên release pooled `DataBuffer` khi drop/replace.
- Subcribe độc lập, mất cancellation/backpressure.
- Gây lỗi khi Retry cần replay request body.

**StepVerifier phù hợp để kiểm logic xử lý Flux ở mức đơn vị**, ví dụ bảo toàn thứ tự các chunks hoặc xử lý lỗi trong một transformer thuần Reactor. Nhưng việc kiểm bytes thực đi đến backend, `Content-Length`, multipart boundary và HTTP `Range` cần test HTTP end-to-end.

### Ví dụ transformer không giữ state giữa requests

~~~java
import reactor.core.publisher.Flux;

static Flux<String> sanitizeEvents(Flux<String> source) {
    return source
        .filter(event -> !event.isBlank())
        .map(String::trim);
}
~~~

Test:

~~~java
@Test
void removesBlankEventsWithoutChangingOrder() {
    StepVerifier.create(sanitizeEvents(
            Flux.just(" a ", "  ", " b ")))
        .expectNext("a", "b")
        .verifyComplete();
}

@Test
void forwardsSourceErrorAfterValidEvent() {
    Flux<String> source = Flux.just("first")
        .concatWith(Mono.error(
            new IllegalStateException("event source failed")));

    StepVerifier.create(sanitizeEvents(source))
        .expectNext("first")
        .expectError(IllegalStateException.class)
        .verify();
}
~~~

**Lưu ý code:** Đây là transformer `Flux<String>` để học signals, không tự đọc SSE/network bytes. Với `DataBuffer` thực, cần kiểm tra ownership, reference counting, pooled buffers, và không nên coi phép `map(String::trim)` là một HTTP body filter có thể dùng nguyên cho streaming upload.

## 20. StepVerifier không thay WebTestClient: kiểm thử nhiều tầng

Để kiểm một Gateway route đầy đủ, phân tách các lớp test:

~~~mermaid
flowchart TD
    UNIT["Unit: StepVerifier + fake chain"] --> CT["Component: WebFlux codecs, route/filter order"]
    CT --> HTTP["Integration: WebTestClient + real Gateway + mock backend"]
    HTTP --> E2E["End-to-end: ingress/TLS/discovery/security/Redis"]
    UNIT -.->|"Nhanh, kiểm signals và logic filter"| S["Tín hiệu reactive"]
    HTTP -.->|"Xác minh HTTP status/headers/body"| H["Hợp đồng Gateway → backend"]
    E2E -.->|"Thử môi trường triển khai thật"| R["SLO và fault injection"]
~~~

### StepVerifier làm tốt việc gì?

- Test `Mono/Flux` có `onNext/onError/onComplete` theo đúng thứ tự.
- Test nhánh `onErrorResume`, `switchIfEmpty` và `Retry.backoff` theo thời gian ảo.
- Test custom `GatewayFilter` với `MockServerWebExchange` và fake `GatewayFilterChain`.
- Test backpressure, cancellation và `PublisherProbe`.
- Test Reactor Context hoặc các operator đọc metadata đáng tin.

### WebTestClient/integration test làm tốt việc gì?

- Kiểm `Path`/`Method`/`Host` predicates và route match thực.
- Kiểm `StripPrefix`, `RewritePath` và header mutation đến backend.
- Kiểm HTTP status 401/403/429/502/503/504 **của hệ thống**.
- Kiểm Retry thật khi backend trả 503 và timing/backoff.
- Kiểm kết nối `lb://`, TLS, connection reset, timeouts và circuit breaker.
- Kiểm request/response body, streaming, compression, multipart, content length.
- Kiểm Spring Security filter chain chạy trước/khác GatewayFilter.
- Kiểm metrics/traces khi một request qua nhiều hops.

**StepVerifier tạo đúng một subscription trong test không chứng minh một HTTP request thực chỉ có một outbound attempt.** Những test liên quan networking phải đo cả backend call counter.

## 21. WebTestClient: integration test HTTP bên ngoài StepVerifier

Một test thực tế dùng Gateway Server WebFlux đã được khởi động và fake downstream HTTP server. `WebTestClient` có fluent assertions cho HTTP request/response.

Ví dụ **minh họa cách assert**, giả sử đã cấu hình application với route `/api/catalog/**` trỏ đến mock backend trả JSON:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class GatewayHttpContractTest {

    @Autowired
    WebTestClient client;

    @Test
    void catalogRouteReturnsExpectedBody() {
        client.get()
            .uri("/api/catalog/items/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo(42);
    }
}
~~~

**Đây không phải test tự chạy khi chưa có fixture**: cần route match thật, backend test/mocking và Spring Boot test setup phù hợp release train. `WebTestClient` có thể bound-to-server hoặc bound-to-application context tùy cách dùng; với kiểm tra Netty routing, test cần **đường HTTP đủ thật** để Gateway forward đến downstream.

### Mô phỏng các nhánh HTTP cần có

| Lỗi/response từ backend | Assertion HTTP cần xác nhận | Signal-level test bổ sung |
|---|---|---|
| 200 + JSON | Body, Content-Type, route ID/log | `Mono` success |
| 404 | Không tự đổi thành 200 | `switchIfEmpty` hoặc backend status mapping |
| 503 → retry → 200 | Final 200, backend call count, deadline | `Retry.backoff` / predicate lọc errors |
| Backend connection refused | 502/503 tùy Gateway/client policy | `onErrorMap`/`onErrorResume` |
| Timeout sau budget | 504 hoặc mã contract khác | Virtual-time `timeout` |
| 401/403 từ security | Backend không bị gọi nếu chặn trước route | Không đủ nếu chỉ test GatewayFilter |
| 429 từ limiter | RateLimit headers/quota phù hợp | Fake limiter/KeyResolver branches |
| CircuitBreaker open | Fallback/5xx theo policy | PublisherProbe và state machine |
| Body lỗi codec | 400/413/5xx theo contract | `Flux` error/buffer lifecycle |
| Client abort | Socket/stream cleanup | `thenCancel` + integration |
| Response đã commit | Không cố set status mới | Error propagation sau commit |

Mã HTTP cuối ở các ví dụ như 502/503/504 **phụ thuộc runtime và cấu hình**, không được assert theo một giả định chung nếu không có hợp đồng mong đợi.

## 22. Security, RateLimiter, CircuitBreaker và retry: viết negative tests

### Spring Security

Một Gateway WebFlux thường dùng `SecurityWebFilterChain`. Nó có thể trả 401/403 **trước khi custom GatewayFilter được gọi**. Nếu unit test chỉ chạy `filter.filter(exchange, chain)`, bạn **chưa kiểm tra authentication và authorization**.

Negative tests nên gồm:

- Không có Bearer token.
- Token hết hạn hoặc sai audience.
- Đúng token nhưng thiếu scope/role.
- User A gọi resource thuộc user/tenant B.
- Cố giả mạo header `X-Authenticated-User`.
- OPTIONS CORS preflight theo policy và request không match route.

**Đừng dùng Reactor Context hoặc test header tự tạo làm bằng chứng security đã được xác minh.** Cần integration test với Spring Security thật và một identity fixture phù hợp.

### RequestRateLimiter

Một KeyResolver trả `Mono.empty()` có thể làm hệ thống áp **empty-key behavior** khác khi có key. Kiểm riêng nhánh có key/không key/lỗi resolver, sau đó HTTP test 429/403 theo chính sách.

~~~java
Mono<String> resolvedKey = Mono.<String>empty();

StepVerifier.create(resolvedKey)
    .verifyComplete();
~~~

Test trên **chỉ chứng minh resolver không phát key**; không tự chứng minh `RequestRateLimiter` sẽ trả status nào khi key rỗng. Đó là behavior của filter/route và cấu hình phải test riêng.

### CircuitBreaker/fallback

Một fallback publisher có thể được test với `PublisherProbe`; nhưng cần thêm kiểm tra fallback **không trả response private cached sai tenant** và **không đổi mọi 503 thành 200**. Nếu downstream đã gửi một phần response, fallback status/body có thể không đổi được sau commit.

### Retry

Với idempotent GET, có thể cho retry bounded. Với POST/PATCH có side effect, phải có backend idempotency contract; StepVerifier đếm subscriptions chưa đủ để chứng minh tác vụ không bị lặp. Bài integration phải đếm **backend attempts và side effects**, không chỉ terminal response.

## 23. Ma trận test cho filter custom dùng trong Gateway

| Kịch bản | Publisher expectation | Assertion ngoài publisher |
|---|---|---|
| Định tuyến thành công | `onComplete` trên `Mono<Void>` | Chain đã gọi, header/path đúng |
| Bị chặn theo filter | `onComplete` | HTTP status 403/429, chain không gọi |
| Đầu vào không hợp lệ | `onError` hoặc controlled response | Không forward sai/không lộ input |
| Downstream 503 | Có thể onComplete với HTTP response hoặc onError từ client | Status và downstream call count |
| Timeout được map thành 504 | `onComplete` nếu response hoàn tất | Status 504 và không có body sai |
| Timeout chưa được xử lý | `onError` | Global error handler qua HTTP có hợp đồng riêng |
| Error không thuộc fallback whitelist | `onError` | Không che SecurityException |
| Retry thành công | `onNext/onComplete` | Số attempts chính xác, tổng latency |
| Retry exhausted | `onError` | Root cause/wrapper và deadline |
| Empty result | `onComplete` không onNext | HTTP 404/204 nếu contract quy định |
| Cancellation | `thenCancel` | Cleanup buffers/socket/side effects |
| Error sau response commit | Có thể `onError` | Không sửa status/headers đã gửi |
| Multiple concurrent requests | Mỗi publisher độc lập | Không rò state user/tenant |
| Cache hit | Chuỗi hoàn thành | Backend không bị gọi và body đúng |
| No-store/private response | Chuỗi hoàn thành theo policy | Không cache dùng chung |
| WebSocket/SSE | Stream semantics, cancellation | Không buffer vô hạn, đúng protocol |

**Kiểm cả nhánh không được thực thi.** Nếu request bị chặn, assert fake downstream **không được gọi**. Nếu fallback không được phép, assert probe **không được subscribe**. Nếu status không đổi, kiểm response thay vì chỉ kiểm terminal signal.

## 24. Chống flaky tests: thực hành tốt

| Anti-pattern | Vì sao dễ sai | Thay bằng |
|---|---|---|
| Không gọi `verify()` | Test không subscribe/không xác minh | `verifyComplete/verifyError/verify` |
| `Thread.sleep` để chờ async | Phụ thuộc tốc độ máy CI | `TestPublisher`, virtual time, publisher assertions |
| `block()` trong production filter | Chặn event loop, phá non-blocking model | Compose `Mono/Flux`, dùng StepVerifier ở test |
| `expectError()` quá rộng | Bỏ lọt lỗi sai loại | `expectErrorMatches`/`expectErrorSatisfies` |
| Chỉ kiểm onComplete của `Mono<Void>` | Có thể đã trả 403 hoặc không gọi chain | Kiểm status, forwarded flag, exchange |
| `Mono.never()` nhưng không timeout/cancel | Test có thể treo vô hạn | `thenCancel` hoặc `timeout` + verify limit |
| Tạo timed publisher ngoài supplier | Virtual time không kiểm soát scheduler đúng | Tạo chain trong `withVirtualTime(() -> ...)` |
| Đặt retries nhưng không đếm subscriptions | Không biết số outbound attempts | AtomicInteger/test backend counter |
| TestPublisher không phát terminal event | Verify có thể chờ mãi | Phát `complete/error` hoặc cancel |
| Global scheduler/hook thay đổi mà không cleanup | Tests ảnh hưởng nhau | Isolation và restore state |
| Gắn assert vào `doFinally` rồi kiểm ngay không đồng bộ | Có thể race vì callback sau signal | Sử dụng probe/await đồng bộ phù hợp hoặc StepVerifier assertions |
| Chỉ test GET 200 | Không thấy auth, timeout, fallback, body bugs | Ma trận success/error/cancel |
| Assert HTTP status từ fake GatewayFilterChain | Không có web exception mapping | Dùng WebTestClient integration |
| Mọi exception đều map thành 200 | Che lỗi sản xuất | Whitelist recovery, assert status và bảo mật |
| Log toàn payload để test | Rò JWT/cookie/body nhạy cảm | Fake data, scrubbed logs, explicit assertions |

### Timeout của chính StepVerifier

Theo Reactor Test, một số lệnh `verify()` có thể **chờ vô hạn theo mặc định**. Có thể đặt timeout riêng:

~~~java
import java.time.Duration;

StepVerifier.create(Mono.just("ok"))
    .expectNext("ok")
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

`StepVerifier.setDefaultTimeout(Duration)` cũng tồn tại nhưng đặt trạng thái **dùng chung**, nên cần quản lý teardown/restore nếu chọn cách ấy, nhất là tests chạy song song.

### Scenario names và logs

`StepVerifierOptions.scenarioName(...)` và `as(...)` giúp tìm expectation sai. Có thể bật log của StepVerifier/test reactor trong lab, nhưng tránh log raw token, request body hoặc exception message nhạy cảm trên CI logs được chia sẻ.

## 25. Bài thực hành hoàn chỉnh: một service có ba nhánh

Tạo một service test mô phỏng gọi catalog:

- ID khác rỗng và là `42` → trả thành công.
- ID `slow` → Mono delay rồi trả `ready`.
- ID `fail` → IOException.
- ID khác → empty.

~~~java
package example.gateway.testing;

import java.io.IOException;
import java.time.Duration;
import reactor.core.publisher.Mono;

public final class CatalogClientStub {

    public Mono<String> fetch(String id) {
        if (id == null || id.isBlank()) {
            return Mono.error(
                new IllegalArgumentException("id required"));
        }

        return switch (id) {
            case "42" -> Mono.just("item:42");
            case "slow" -> Mono.delay(Duration.ofSeconds(10))
                .map(ignore -> "ready");
            case "fail" -> Mono.error(
                new IOException("backend unavailable"));
            default -> Mono.empty();
        };
    }
}
~~~

Kiểm từng nhánh:

~~~java
package example.gateway.testing;

import java.io.IOException;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class CatalogClientStubTest {

    private final CatalogClientStub client = new CatalogClientStub();

    @Test
    void success() {
        StepVerifier.create(client.fetch("42"))
            .expectNext("item:42")
            .verifyComplete();
    }

    @Test
    void emptyResult() {
        StepVerifier.create(client.fetch("999"))
            .verifyComplete();
    }

    @Test
    void validationError() {
        StepVerifier.create(client.fetch(""))
            .expectError(IllegalArgumentException.class)
            .verify();
    }

    @Test
    void transportError() {
        StepVerifier.create(client.fetch("fail"))
            .expectError(IOException.class)
            .verify();
    }

    @Test
    void delayedResultUsesVirtualTime() {
        StepVerifier.withVirtualTime(
                () -> client.fetch("slow"))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(9))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("ready")
            .verifyComplete();
    }
}
~~~

**Nhánh nào chưa được kiểm?** Một test bổ sung nên tạo `fetch("slow").timeout(Duration.ofSeconds(5))` và mong đợi `TimeoutException` bằng virtual time; một test khác bọc `fetch("fail")` bằng `onErrorResume` nhưng chỉ phục hồi `IOException`, rồi kiểm sai loại exception được giữ nguyên.

### Liên hệ Gateway thực tế

Service stub mô tả những reactive signals giống một HTTP client abstraction, **không phải thay thế mọi semantics của WebClient/Gateway routing**. Nếu backend thật trả HTTP 503, client có thể trả response object bình thường thay vì `Mono.error`, tùy cách API được viết. Khi chuyển bài thực hành này vào Gateway, phải xác minh **status-to-error translation và routing filter order**.

## 26. Checklist trước khi đánh dấu bài kiểm thử hoàn thành

- [ ] Tôi thêm `reactor-test` vào test scope, không vào runtime.
- [ ] Tôi biết phân biệt `Mono`, `Flux`, `empty`, `error` và `never`.
- [ ] Tôi luôn gọi `verify()` hoặc shortcut verify phù hợp.
- [ ] Tôi dùng `expectNext`/`assertNext` cho dữ liệu và `expectComplete`/`expectError` cho terminal.
- [ ] Tôi hiểu `Mono<Void>` hoàn thành **không chứng minh** HTTP status 200.
- [ ] Tôi kiểm tra lỗi theo type/message/cause, không chỉ `expectError()` chung chung.
- [ ] Tôi test cả nhánh fallback xảy ra và không xảy ra bằng `PublisherProbe`.
- [ ] Tôi dùng `TestPublisher` để phát signal downstream có kiểm soát.
- [ ] Tôi dùng `withVirtualTime` đúng: tạo timed publisher trong supplier.
- [ ] Tôi gọi `expectSubscription()` trước `expectNoEvent`.
- [ ] Tôi phân biệt timeout của operator với timeout bảo vệ chính test.
- [ ] Tôi kiểm số retries **và** tổng subscriptions; không nhầm retries với total attempts.
- [ ] Tôi biết `Retry.backoff` exhaustion có thể trả wrapper exception.
- [ ] Tôi test `onErrorMap`, `onErrorResume`, `switchIfEmpty` theo đúng thứ tự operator.
- [ ] Tôi test backpressure `thenRequest` và cancellation `thenCancel` khi liên quan streaming.
- [ ] Tôi hiểu Reactor Context không phải HTTP headers hoặc Spring Security context mặc định.
- [ ] Tôi không tự `subscribe()`, `block()` hoặc làm I/O blocking trong GatewayFilter.
- [ ] Tôi test pre/chain/post order, header mutation và short-circuit bằng fake chain.
- [ ] Tôi không assert response HTTP toàn pipeline từ unit test chỉ gọi GatewayFilter.
- [ ] Tôi có WebTestClient integration tests cho route predicates/filter chain/security/backend.
- [ ] Tôi kiểm 401/403/429, timeout, retry, fallback, cache, response commit và backend attempts.
- [ ] Tôi không log raw JWT, cookie, user ID, request body hoặc bí mật ở test logs.
- [ ] Tôi giữ tests deterministic, hạn chế sleep và kiểm soát process-wide hooks/schedulers.
- [ ] Tôi có ít nhất một negative test chứng minh dữ liệu user/tenant không bị dùng sai.
- [ ] Tôi chạy tests trên **Spring Boot/Spring Cloud/Gateway/Reactor BOM** đã được dự án chấp nhận.
- [ ] Tôi phân biệt unit verification PASS với Content QA và integration/runtime verification chưa chạy.

## 27. Bài tập mở rộng

**Bài 1 — Đổi hợp đồng empty thành 404.** Xây `Mono<String> findItem(id)` trả empty khi không tìm thấy; dùng `switchIfEmpty(Mono.error(...))`. Test trước/sau và giải thích vì sao StepVerifier không trực tiếp chứng minh HTTP 404.

**Bài 2 — Sai loại lỗi.** Viết operator chỉ fallback khi `TimeoutException`; dùng `TestPublisher` phát `IOException` rồi `SecurityException` và xác minh cả hai **không bị nuốt**.

**Bài 3 — Filter short-circuit.** Dùng `LabGuardFilter`, viết test chứng minh header spoofed bị ghi đè, request blocked không gọi fake chain, còn request allowed giữ nguyên path/query.

**Bài 4 — Timeout ảo.** Viết test cho `Mono.delay(Duration.ofMinutes(30)).timeout(Duration.ofMinutes(1))`, dùng `withVirtualTime` và timeout bảo vệ test; tuyệt đối không sleep 30 phút.

**Bài 5 — Retry.** Tạo source lỗi hai lần rồi thành công; kiểm count 3, success signal, test exhaustion và phân biệt wrapper exception. Tại sao phải tắt jitter trong virtual-time test nhưng có thể bật ở production?

**Bài 6 — Backpressure.** Dùng `Flux.range(1,100)` với initialRequest = 0, gọi `thenRequest(10)` rồi `thenCancel()`. Kiểm không mong đợi onComplete của một chuỗi còn chưa phát hết.

**Bài 7 — Fault injection HTTP.** Dùng mock backend trả 503 hai lần rồi 200, kết hợp WebTestClient và backend request counter. So kết quả HTTP với StepVerifier retry unit test; giải thích vì sao Retry GatewayFilter có thể xử lý status khác Reactor `Mono.error`.

**Bài 8 — Security.** Thử request không có JWT, JWT sai scope và token đúng; xác minh backend không nhận request bị chặn. Vì sao chạy `GatewayFilter.filter(...)` đơn lẻ không chứng minh `SecurityWebFilterChain` hoạt động?

## Tài liệu tham khảo chính thức

- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html) — `StepVerifier`, virtual time, `PublisherProbe`, `TestPublisher`, Context và post-verification assertions.
- [Reactor Test — StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html) — terminal expectations, `verify`, `thenRequest`, `thenCancel`, `withVirtualTime`.
- [Reactor Test — StepVerifierOptions](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html) — `scenarioName` và `withInitialContext`.
- [Reactor Test — PublisherProbe](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html) — xác minh subscription/request/cancel của fallback.
- [Reactor Test — TestPublisher](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html) — phát manual signals cho unit tests.
- [Reactor Test — StepVerifier Assertions](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Assertions.html) — dropped/discarded/operator error assertions.
- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — Gateway Server WebFlux route predicates, filter chain, Retry, CircuitBreaker và testing theo phiên bản.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — HTTP assertions, bind-to-server và bind-to-application-context.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html) — `@SpringBootTest`, test auto-configuration và integration fixtures.
- [Reactive Streams Specification](https://www.reactive-streams.org/) — subscription, demand, backpressure, onNext/onError/onComplete và cancellation semantics.

**Ghi nhớ:** `StepVerifier` giúp bạn chứng minh **một chuỗi Reactor phát đúng thứ tự dữ liệu, lỗi, completion hoặc cancellation**. Với Spring Cloud Gateway Server WebFlux, hãy dùng nó để kiểm **custom filter, fallback, timeout, retry, Reactor Context và các nhánh lỗi**, kết hợp `TestPublisher`/`PublisherProbe` để xác nhận **nhánh nào đã thực thi**. Nhưng `Mono<Void>` hoàn thành **không đồng nghĩa HTTP 200**, và `StepVerifier` **không thay WebTestClient** khi phải xác minh routing, Spring Security, status/headers, backend attempts hay TLS thật. Chất lượng kiểm thử đến từ **cả success path lẫn negative paths** và những assertions đúng tầng.

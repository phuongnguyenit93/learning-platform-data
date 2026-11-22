# reactor-test và kiểm thử publisher ngoài Spring context

## 1. Mục tiêu: kiểm thử Reactive Streams bằng Java thuần, không khởi động Spring

Trong ứng dụng Spring Boot dùng WebFlux, R2DBC, reactive messaging hoặc những service bất đồng bộ, phần lớn logic có thể được biểu diễn thành `Mono<T>` và `Flux<T>`. Tuy vậy **một Publisher không cần HTTP server, Spring bean hay `ApplicationContext` để được kiểm thử**. Nếu đơn vị cần thử chỉ nhận dữ liệu, áp dụng toán tử Reactor và trả về `Publisher`, ta có thể tạo object Java trực tiếp, cung cấp dependency giả bằng lambda/fake rồi kiểm tra **chuỗi tín hiệu thực sự phát ra khi subscribe** với thư viện `reactor-test`.

Trọng tâm của bài:

- Hiểu `onSubscribe`, `request(n)`, `onNext`, `onComplete`, `onError` và `cancel()`.
- Dùng `StepVerifier` cho giá trị, thứ tự, hoàn tất, lỗi, yêu cầu backpressure, thời gian và Reactor `Context`.
- Dùng `TestPublisher` để chủ động phát tín hiệu từ một dependency reactive giả.
- Dùng `PublisherProbe` để kiểm tra **nhánh Publisher nào thật sự được subscribe**.
- Viết test chạy với JUnit Jupiter **mà không có `@SpringBootTest`, `@WebFluxTest`, `@Autowired`, `@MockBean` hay server**.
- Phân biệt loại test này với `WebTestClient`/test HTTP Reactive khi yêu cầu là route, codec, filter hay network.
- Tránh các lỗi test “xanh giả”: chỉ assembly mà không subscribe, gọi `subscribe()` trong test rồi kết thúc quá sớm, `Thread.sleep`, `block()` ở chỗ không thích hợp, dùng `TestPublisher` hot sai thời điểm, hoặc không xác nhận terminal signal.

**Đối tượng:** Java 17+, Project Reactor 3.x, JUnit Jupiter; ví dụ thiết lập trong dự án Spring Boot 3.x với Reactor dependencies được Boot quản lý. Các API cốt lõi của `reactor-test` vẫn áp dụng cho ứng dụng Reactor không dùng Spring Boot. Đối với Boot 4.x và Reactor train mới hơn, hãy để BOM của dự án quản lý version và kiểm tra thay đổi API trong Javadoc tương ứng.

## 2. Tại sao assertion thông thường chưa đủ?

### 2.1. Publisher là mô tả chuỗi công việc, không phải giá trị đã có

Với Reactor, một lời gọi như:

```java
Mono<String> result = Mono.just("book")
        .map(String::toUpperCase);
```

mới chỉ tạo pipeline. Với publisher cold như ví dụ này, việc tạo pipeline **không chứng minh đã thực hiện chuỗi xử lý từ source đến subscriber**. Khi subscription được kích hoạt, các tín hiệu mới đi qua chuỗi.

Sai lầm là viết:

```java
@Test
void doesNotVerifyThePublisher() {
    Mono<String> result = Mono.just("book")
            .map(String::toUpperCase);

    assertNotNull(result);
}
```

Đây là **phản ví dụ** trong lớp JUnit có imports. Assertion chỉ chứng minh một object khác null. Nếu phép biến đổi trả chữ thường, không phát giá trị hoặc phát lỗi khi subscribe, test vẫn có thể xanh.

Đúng hơn:

```java
StepVerifier.create(Mono.just("book")
        .map(String::toUpperCase))
        .expectNext("BOOK")
        .verifyComplete();
```

Đoạn minh họa trên yêu cầu import `reactor.test.StepVerifier`. Nó xác nhận **một giá trị `BOOK`**, sau đó **hoàn tất thành công**, không có phần tử thừa hoặc lỗi thay cho complete.

### 2.2. Các loại tín hiệu Reactive Streams

Một chuỗi hợp lệ thông thường:

```text
Subscriber                       Publisher
    |                                |
    | <--------- onSubscribe --------|
    | -------- request(n) ---------->|
    | <--------- onNext(v1) ----------|
    | <--------- onNext(v2) ----------|
    | <--------- onComplete ---------|
    |                                |
    +--- subscription terminated ----+

Hoặc:
    onSubscribe -> request(n) -> onError(exception)

Hoặc:
    onSubscribe -> ... -> cancel()
    (không bắt buộc có onComplete hay onError sau cancel)
```

Ngữ nghĩa cốt lõi:

- `onSubscribe` cung cấp một `Subscription`; subscriber quyết định số lượng phần tử muốn nhận bằng `request(n)`.
- `onNext(value)` chuyển giá trị; đối với `Mono<T>` thông thường có **tối đa một** `onNext`.
- `onComplete()` kết thúc thành công; một Mono có thể hoàn tất **không phát giá trị**.
- `onError(Throwable)` kết thúc lỗi. Một stream hợp lệ không phát thêm `onNext` hoặc terminal signal sau terminal đã đến.
- `cancel()` yêu cầu dừng nhận thêm tín hiệu; việc hủy/cleanup có thể không xảy ra tức thời trong hệ bất đồng bộ.
- `request(n)` là một phần của cơ chế backpressure, không phải “số lần gọi method”; source/operators có thể điều chỉnh demand và prefetch theo chính sách riêng.

**Quan trọng:** `Mono.empty()` khác `Mono.just(null)`. Reactive Streams không cho phát `null` như onNext value; muốn biểu diễn không có dữ liệu, dùng `Mono.empty()`. Với Reactor, `Mono.just(null)` không phải cách hợp lệ để phát một “giá trị null”.

### 2.3. Subscription là ranh giới cần kiểm chứng

Một test kiểm tra reactive logic nên xác nhận tối thiểu **giá trị (nếu có) và terminal signal**, hoặc chứng minh việc cancel là chủ đích. Kiểm tra chỉ giá trị mà không kiểm tra terminal có thể bỏ sót publisher phát thêm dữ liệu, treo vô thời hạn hoặc phát lỗi sau đó.

`StepVerifier` được thiết kế để mô tả các bước mong đợi theo đúng thứ tự và **chỉ chạy verification khi bạn gọi method kích hoạt** như `verify()`, `verifyComplete()` hoặc `verifyError()`.

## 3. Khi nào không cần Spring context?

Một class có phương thức trả `Mono`/`Flux` có thể được kiểm thử như Java object bình thường:

```java
public final class TagFormatter {
    public Flux<String> normalize(List<String> tags) {
        return Flux.fromIterable(tags)
                .map(String::strip)
                .filter(tag -> !tag.isBlank());
    }
}
```

Đây là **snippet lớp minh họa**, giả định đã import Reactor `Flux` và `java.util.List`. Nếu logic chỉ sử dụng toán tử Reactor và dependency có thể truyền bằng constructor, test **không cần** khởi động Boot application.

### 3.1. Không Spring context giúp được gì?

- Không phải chạy component scanning, auto-configuration, database migrations hoặc embedded server.
- Test nhanh, ít trạng thái chia sẻ và lỗi tập trung ở logic Publisher.
- Chủ động thay nguồn dữ liệu bằng `Mono.just(...)`, `Mono.empty()`, `Mono.error(...)`, `Flux.fromIterable(...)`, `TestPublisher` hoặc fake implementation.
- Kiểm soát virtual time/backpressure trực tiếp mà không phải ép cả ứng dụng Spring chờ.
- Dễ thấy lỗi từ operators: `map`, `flatMap`, `filter`, `switchIfEmpty`, `timeout`, `retry`, `onErrorResume` và những biến đổi domain.

### 3.2. Điều gì không được chứng minh?

Một unit test thuần Reactor **không tự xác minh**:

- Spring `@Bean`, `@Component`, `@ConfigurationProperties` hoặc Dependency Injection được cấu hình đúng.
- WebFlux route, Controller/RouterFunction, JSON codec, validation HTTP, security/web filters.
- R2DBC driver thực sự kết nối DB, transaction manager, broker hoặc mạng.
- Reactor Netty HTTP/TCP behavior, socket timeout, TLS, gateway và load balancer.

Khi các mục tiêu trên là hợp đồng, cần test Spring slice/integration phù hợp, như `@WebFluxTest` + `WebTestClient`, `@SpringBootTest`, database Testcontainers hoặc real HTTP integration tests. Không cần nâng mọi unit test thành `@SpringBootTest` chỉ vì class trong dự án có dùng WebFlux.

## 4. Dependency: `reactor-core` và `reactor-test` là hai artifact khác nhau

### 4.1. Vai trò

- `io.projectreactor:reactor-core`: chứa `Mono`, `Flux`, `Schedulers`, `Context` và các operator dùng ở production.
- `io.projectreactor:reactor-test`: chứa `StepVerifier`, `TestPublisher`, `PublisherProbe`, virtual-time support và các test utilities. Chỉ dùng trong **test scope**.
- JUnit Jupiter: test runner/annotations `@Test` và assertions.

**Không** tạo Spring ApplicationContext chỉ để có StepVerifier. `reactor-test` là thư viện Java bình thường, hoạt động với Reactive Streams `Publisher` ngoài Spring.

### 4.2. Gradle Groovy DSL trong dự án Spring Boot 3.x

Trong `build.gradle` đã có plugin Spring Boot, dependency management, repositories và Java toolchain đúng:

```groovy
dependencies {
    implementation 'io.projectreactor:reactor-core'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Đây là **phần dependency/test configuration**, không phải build file hoàn chỉnh. Spring Boot BOM quản lý phiên bản Reactor và những dependencies liên quan; không tự trộn version Reactor Core và Reactor Test khác release train.

Nếu dự án đã dùng `spring-boot-starter-webflux` ở production, `reactor-core` thường đã là transitive dependency, nhưng nên kiểm tra effective dependencies của dự án thay vì giả định từ tên module. `reactor-test` vẫn nên được khai báo/giải quyết rõ trong test scope; có thể đã được một test starter tương thích đưa vào nhưng explicit dependency giúp ý định rõ.

### 4.3. Maven trong dự án đã có Spring Boot parent/BOM

```xml
<dependencies>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-core</artifactId>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Cũng là **đoạn dependency**, không phải `pom.xml` đầy đủ. Dự án cần plugin/compiler target Java 17+, Surefire/JUnit Platform phù hợp và version management.

**Spring Boot 4.x:** các starters được chia nhỏ theo module, nhưng công cụ unit test Reactor vẫn có coordinates `reactor-core`/`reactor-test`. Hãy kiểm tra tài liệu/Dependency BOM của đúng Boot major version thay vì sao chép cấu hình web starter của Boot 3 một cách máy móc. Nếu không sử dụng Spring Boot, phải tự chỉ định Reactor version hoặc Reactor BOM phù hợp.

### 4.4. Kiểm tra dependency resolution

```bash
# Gradle Wrapper:
./gradlew dependencyInsight --dependency reactor-core --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency reactor-test --configuration testRuntimeClasspath

# Maven Wrapper:
./mvnw dependency:tree -Dincludes=io.projectreactor
```

Chạy đúng lệnh của build tool, ở module chứa test. Nếu báo không tìm thấy class `reactor.test.StepVerifier`, kiểm tra `reactor-test` có ở `testCompileClasspath`/test scope hay không; chỉ có `reactor-core` là chưa đủ.

## 5. Nắm API `StepVerifier` trước khi thực hành

### 5.1. Bảng hành động thường dùng

| API | Cần xác nhận |
|---|---|
| `StepVerifier.create(publisher)` | Dựng một kịch bản subscriber cho Publisher |
| `expectSubscription()` | Có sự kiện subscription |
| `expectNext(value...)` | Các giá trị tiếp theo, đúng thứ tự và bằng nhau |
| `expectNextMatches(predicate)` | Giá trị tiếp theo thỏa điều kiện |
| `assertNext(consumer)` | Tự assert nội dung một giá trị |
| `expectNextCount(n)` | Có đúng **n** phần tử tiếp theo, nhưng không kiểm tra từng giá trị |
| `expectComplete()` | Terminal thành công sau các bước trước |
| `expectError(type)` | Terminal lỗi thuộc kiểu cụ thể |
| `expectErrorMatches(predicate)` | Terminal lỗi thỏa điều kiện, chẳng hạn type + message |
| `thenRequest(n)` | Gửi thêm demand tới upstream |
| `thenCancel()` | Hủy subscription, thích hợp cho Publisher không kết thúc |
| `then(Runnable)` | Thực thi tác động test đã sắp đặt sau các bước trước, ví dụ kích `TestPublisher` |
| `thenAwait(duration)` | Chờ hoặc tiến virtual clock để dữ liệu đến |
| `expectNoEvent(duration)` | Xác minh không có event trong khoảng thời gian chỉ định |
| `verify()`/`verify(duration)` | **Kích hoạt** subscription + so sánh toàn bộ kịch bản |
| `verifyComplete()` | Shortcut mong terminal complete rồi chạy verify |
| `verifyError(...)` | Shortcut mong terminal error rồi chạy verify |

Những method trên không thay thế nhau hoàn toàn. Ví dụ `expectNextCount(3)` chỉ khẳng định **số lượng**, không phát hiện ba giá trị bị tính sai nếu thứ tự/giá trị không được assert. `expectErrorMessage("...")` kiểm tra message nhưng không nhất thiết ràng buộc exception type; khi type quan trọng, dùng `expectErrorMatches`, `expectErrorSatisfies` hoặc assertion phù hợp.

### 5.2. Ví dụ ba trạng thái cơ bản

**Publisher có một giá trị và hoàn tất:**

```java
StepVerifier.create(Mono.just("DONE"))
        .expectNext("DONE")
        .verifyComplete();
```

**Publisher không có giá trị nhưng hoàn tất thành công:**

```java
StepVerifier.create(Mono.<String>empty())
        .verifyComplete();
```

**Publisher phát lỗi:**

```java
StepVerifier.create(Mono.<String>error(
        new IllegalStateException("offline")))
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                && "offline".equals(error.getMessage()))
        .verify();
```

Đây là **các đoạn minh họa độc lập về expression**, giả định đang ở test class có imports Reactor. Chúng phân biệt *empty completion* với *error*: cả hai không phát `onNext` nhưng terminal signal khác nhau.

### 5.3. Giới hạn thời gian verification

Mặc định nhiều phương thức `verify...` **không có timeout**, có thể treo nếu publisher chờ vô hạn. Với test không được đảm bảo hoàn tất nhanh, nên gắn timeout theo từng test:

```java
StepVerifier.create(Flux.just(1, 2))
        .expectNext(1, 2)
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

Ví dụ này chạy nếu có import `java.time.Duration` và Reactor. Không nên cố định một số giây cực thấp cho kiểm thử có tài nguyên ngoài; nhưng cũng không để suite treo vô thời hạn. `StepVerifier.setDefaultTimeout(...)` là cấu hình **global** và có thể ảnh hưởng test chạy song song; nếu dùng, quản lý lifecycle/test suite nhất quán.

### 5.4. Không viết kịch bản rồi quên `verify`

Mẫu sai:

```java
StepVerifier.create(Mono.just("A"))
        .expectNext("B")
        .expectComplete();
// Không gọi verify(), verifyComplete() hay verifyError().
```

Đây là **phản mẫu**; test có thể kết thúc mà chưa thực sự chạy assertion Reactive Streams. Bắt buộc phải gọi một terminal verification method. Xây kịch bản không tương đương đã subscribe.

## 6. Ví dụ Java 17+ hoàn chỉnh: logic publisher độc lập với Spring

Ta xây một `QuoteService` sử dụng `Mono` và `Flux` nhưng **không có annotation Spring**, không HTTP, không database. Dependency giá sản phẩm được biểu diễn bằng interface Java, và test có thể cung cấp fake implementation bằng lambda.

### 6.1. Cây file

```text
src/
├── main/java/com/example/reactortesting/
│   └── QuoteService.java
└── test/java/com/example/reactortesting/
    └── QuoteServiceTest.java
```

Khi chạy trong Spring Boot project, hai file này là Java production/test bình thường. Không cần `@SpringBootApplication` trong ví dụ vì ta không khởi động app.

### 6.2. Source production: `QuoteService.java`

**File `src/main/java/com/example/reactortesting/QuoteService.java`:**

```java
package com.example.reactortesting;

import java.time.Duration;
import java.util.List;
import java.util.Locale;
import java.util.NoSuchElementException;
import java.util.Objects;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class QuoteService {

    @FunctionalInterface
    public interface PriceCatalog {
        Mono<Integer> priceFor(String sku);
    }

    public record Quote(String sku, int quantity, int total) {}

    private final PriceCatalog catalog;

    public QuoteService(PriceCatalog catalog) {
        this.catalog = Objects.requireNonNull(catalog);
    }

    public Mono<Quote> quote(String sku, int quantity) {
        return Mono.defer(() -> {
            if (sku == null || sku.isBlank()) {
                return Mono.error(new IllegalArgumentException(
                        "sku required"));
            }
            if (quantity <= 0) {
                return Mono.error(new IllegalArgumentException(
                        "quantity must be positive"));
            }

            return catalog.priceFor(sku)
                    .switchIfEmpty(Mono.error(
                            new NoSuchElementException(
                                    "unknown sku: " + sku)))
                    .map(price -> new Quote(
                            sku,
                            quantity,
                            Math.multiplyExact(price, quantity)));
        });
    }

    public Flux<String> normalize(List<String> tags) {
        return Flux.fromIterable(tags)
                .map(String::strip)
                .filter(tag -> !tag.isEmpty())
                .map(tag -> tag.toUpperCase(Locale.ROOT))
                .distinct();
    }

    public Flux<Long> ticks(Duration period, long count) {
        if (count <= 0) {
            return Flux.error(new IllegalArgumentException(
                    "count must be positive"));
        }
        return Flux.interval(period).take(count);
    }

    public Mono<String> preferred(
            Mono<String> primary,
            Mono<String> fallback) {
        return primary.switchIfEmpty(fallback);
    }

    public Mono<String> traceId() {
        return Mono.deferContextual(context ->
                Mono.just(context.getOrDefault(
                        "traceId", "none")));
    }
}
```

**Thiết kế đáng chú ý:**

1. `PriceCatalog` là một interface functional, nên test có thể truyền `sku -> Mono.just(1200)` hoặc `sku -> Mono.empty()`. Không cần tạo Mockito mock hoặc chạy Spring DI.
2. `quote(...)` dùng `Mono.defer(...)` để đưa validation và lời gọi catalog vào **thời điểm subscribe**. Vì vậy chỉ assembly pipeline không tự đọc catalog; test kiểm tra được sự khác biệt này.
3. `switchIfEmpty(...)` biến kết quả không tìm thấy giá thành error rõ ràng. Empty source không được đánh đồng với một giá trị giá bằng 0.
4. `Math.multiplyExact(int, int)` ném `ArithmeticException` nếu phép nhân tràn số; Reactor chuyển exception phát ra trong operator thành terminal error.
5. `normalize(...)` tạo `Flux<String>` xử lý thứ tự, bỏ chuỗi rỗng, chuẩn hóa chữ hoa theo `Locale.ROOT` và loại giá trị lặp, giúp test tín hiệu `onNext`.
6. `ticks(...)` tạo một stream dựa trên thời gian; test có thể dùng virtual clock để tránh chờ nhiều giờ.
7. `preferred(...)` chọn primary hoặc fallback qua `switchIfEmpty`, dùng để học `PublisherProbe`.
8. `traceId()` đọc **Reactor Context** của subscriber, không phải Spring `ApplicationContext` hoặc ThreadLocal.

Ví dụ không sử dụng dependency ngoài nên phù hợp với unit test độc lập. Trong ứng dụng thật, `PriceCatalog` có thể là adapter truy vấn R2DBC/HTTP, nhưng **unit test này chủ động không kiểm chứng adapter thực**.

### 6.3. Source test: `QuoteServiceTest.java`

**File `src/test/java/com/example/reactortesting/QuoteServiceTest.java`:**

```java
package com.example.reactortesting;

import java.time.Duration;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.PublisherProbe;
import reactor.test.publisher.TestPublisher;
import reactor.util.context.Context;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class QuoteServiceTest {

    private QuoteService withCatalog(
            QuoteService.PriceCatalog catalog) {
        return new QuoteService(catalog);
    }

    @Test
    void quoteEmitsExpectedValueAndCompletes() {
        var service = withCatalog(sku -> Mono.just(1200));

        StepVerifier.create(service.quote("BOOK", 2))
                .expectNext(new QuoteService.Quote(
                        "BOOK", 2, 2400))
                .verifyComplete();
    }

    @Test
    void emptyCatalogBecomesDomainError() {
        var service = withCatalog(sku -> Mono.empty());

        StepVerifier.create(service.quote("MISSING", 1))
                .expectErrorSatisfies(error -> {
                    assertEquals(NoSuchElementException.class,
                            error.getClass());
                    assertEquals("unknown sku: MISSING",
                            error.getMessage());
                })
                .verify();
    }

    @Test
    void catalogErrorIsPropagatedAsTerminalError() {
        var service = withCatalog(sku ->
                Mono.error(new IllegalStateException("offline")));

        StepVerifier.create(service.quote("BOOK", 2))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "offline".equals(error.getMessage()))
                .verify();
    }

    @Test
    void invalidQuantityDoesNotCallCatalog() {
        AtomicInteger calls = new AtomicInteger();
        var service = withCatalog(sku -> {
            calls.incrementAndGet();
            return Mono.just(100);
        });

        StepVerifier.create(service.quote("BOOK", 0))
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && "quantity must be positive"
                                .equals(error.getMessage()))
                .verify();

        assertEquals(0, calls.get());
    }

    @Test
    void catalogIsNotCalledDuringAssembly() {
        AtomicInteger calls = new AtomicInteger();
        var service = withCatalog(sku -> {
            calls.incrementAndGet();
            return Mono.just(500);
        });

        Mono<QuoteService.Quote> pipeline =
                service.quote("PEN", 3);

        assertEquals(0, calls.get());

        StepVerifier.create(pipeline)
                .expectNext(new QuoteService.Quote(
                        "PEN", 3, 1500))
                .verifyComplete();

        assertEquals(1, calls.get());
    }

    @Test
    void fluxNormalizesFiltersAndPreservesFirstOccurrence() {
        var service = withCatalog(sku -> Mono.empty());

        StepVerifier.create(service.normalize(List.of(
                " red ", "RED", "blue", " ", "blue")))
                .expectNext("RED", "BLUE")
                .verifyComplete();
    }

    @Test
    void initialRequestZeroExercisesBackpressure() {
        StepVerifier.create(
                Flux.range(1, 5),
                StepVerifierOptions.create().initialRequest(0))
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(3)
                .expectNext(3, 4, 5)
                .verifyComplete();
    }

    @Test
    void virtualTimeDoesNotWaitTwoRealHours() {
        var service = withCatalog(sku -> Mono.empty());

        StepVerifier.withVirtualTime(() ->
                service.ticks(Duration.ofHours(1), 2))
                .expectSubscription()
                .expectNoEvent(Duration.ofMinutes(59))
                .thenAwait(Duration.ofMinutes(1))
                .expectNext(0L)
                .thenAwait(Duration.ofHours(1))
                .expectNext(1L)
                .verifyComplete();
    }

    @Test
    void testPublisherControlsTheCatalogSignals() {
        TestPublisher<Integer> source = TestPublisher.create();
        var service = withCatalog(sku -> source.mono());

        StepVerifier.create(service.quote("BOOK", 3))
                .expectSubscription()
                .then(() -> {
                    source.assertWasSubscribed();
                    source.emit(400);
                })
                .expectNext(new QuoteService.Quote(
                        "BOOK", 3, 1200))
                .verifyComplete();
    }

    @Test
    void publisherProbeProvesPrimaryPathWasUsed() {
        var service = withCatalog(sku -> Mono.empty());
        PublisherProbe<String> primary = PublisherProbe.of(
                Mono.just("primary"));
        PublisherProbe<String> fallback = PublisherProbe.of(
                Mono.just("fallback"));

        StepVerifier.create(service.preferred(
                primary.mono(), fallback.mono()))
                .expectNext("primary")
                .verifyComplete();

        primary.assertWasSubscribed();
        primary.assertWasRequested();
        fallback.assertWasNotSubscribed();
    }

    @Test
    void publisherProbeProvesFallbackPathWasUsed() {
        var service = withCatalog(sku -> Mono.empty());
        PublisherProbe<String> primary = PublisherProbe.empty();
        PublisherProbe<String> fallback = PublisherProbe.of(
                Mono.just("fallback"));

        StepVerifier.create(service.preferred(
                primary.mono(), fallback.mono()))
                .expectNext("fallback")
                .verifyComplete();

        primary.assertWasSubscribed();
        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
    }

    @Test
    void reactorContextWorksWithoutSpringApplicationContext() {
        var service = withCatalog(sku -> Mono.empty());

        StepVerifier.create(
                service.traceId(),
                StepVerifierOptions.create().withInitialContext(
                        Context.of("traceId", "trace-42")))
                .expectAccessibleContext()
                .contains("traceId", "trace-42")
                .then()
                .expectNext("trace-42")
                .verifyComplete();
    }

    @Test
    void anInfinitePublisherCanBeCancelled() {
        StepVerifier.create(Flux.never())
                .expectSubscription()
                .thenCancel()
                .verify(Duration.ofSeconds(2));
    }

    @Test
    void aBoundedVerificationCompletesWithinDeadline() {
        StepVerifier.create(Mono.just("READY"))
                .expectNext("READY")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }
}
```

Bài test có **14 phương thức `@Test`**. Không có `@SpringBootTest`, `@Autowired`, Spring extension, embedded server, application startup hay stdout cố ý. Khi dùng Java 17+, Reactor Core/Reactor Test và JUnit Jupiter tương thích, kỳ vọng **14/14 test pass**.

Test `StepVerifier.withVirtualTime(...)` không chờ thật hai giờ; virtual scheduler điều khiển thời gian được mô phỏng. Những test khác dùng publisher đồng bộ/deterministic, không có `Thread.sleep()`.

### 6.4. Chạy bằng Wrapper

**Gradle:**

```bash
./gradlew test --tests "com.example.reactortesting.QuoteServiceTest"
```

**Maven:**

```bash
./mvnw -Dtest=QuoteServiceTest test
```

Trên Windows PowerShell, dùng `.\gradlew.bat test --tests "com.example.reactortesting.QuoteServiceTest"` hoặc `.\mvnw.cmd "-Dtest=QuoteServiceTest" test`. Dự án cần có wrapper/test task hoặc Maven Surefire/JUnit Platform tương ứng. Không chạy cả hai lệnh nếu project chỉ có một build system.

**Kết quả dự kiến:** runner báo 14 tests thành công; không có một chuỗi stdout nào do source cố ý in. Log/report chi tiết phụ thuộc Maven/Gradle/IDE, nên kiểm tra test count và trạng thái thật sự thay vì chép một dòng console từ máy khác.

### 6.5. Diễn giải chi tiết các tình huống trong ví dụ

| Test | Hợp đồng được xác nhận | Vì sao đáng kiểm tra |
|---|---|---|
| `quoteEmitsExpectedValueAndCompletes` | Mono phát đúng một `Quote` rồi complete | Không chỉ khẳng định object Publisher khác null |
| `emptyCatalogBecomesDomainError` | Upstream empty chuyển thành `NoSuchElementException` có message đúng | Phân biệt không tìm thấy với error của nguồn |
| `catalogErrorIsPropagatedAsTerminalError` | Lỗi upstream được truyền xuống, không nuốt lỗi | Xác nhận exception type/message |
| `invalidQuantityDoesNotCallCatalog` | Đầu vào sai phát error và không gọi dependency | Phân nhánh hợp đồng và cô lập tác động |
| `catalogIsNotCalledDuringAssembly` | Dependency chỉ được gọi tại subscribe | Chứng minh lazy behavior |
| `fluxNormalizesFiltersAndPreservesFirstOccurrence` | Chuẩn hóa, bỏ rỗng, lọc duplicate đúng thứ tự | Kiểm tra chuỗi `onNext` |
| `initialRequestZeroExercisesBackpressure` | Request 2 rồi 3 mới nhận hết 5 phần tử | Kiểm tra demand thay vì mặc định unbounded |
| `virtualTimeDoesNotWaitTwoRealHours` | Tín hiệu phát theo virtual clock | Tránh timing/flaky tests |
| `testPublisherControlsTheCatalogSignals` | Fake phát dữ liệu sau subscription, business pipeline phản hồi đúng | Kiểm soát source bất đồng bộ |
| `publisherProbeProvesPrimaryPathWasUsed` | Primary được subscribe/request, fallback không được subscribe | Kiểm tra nhánh thật |
| `publisherProbeProvesFallbackPathWasUsed` | Source primary empty khiến fallback được subscribe | Kiểm tra `switchIfEmpty` |
| `reactorContextWorksWithoutSpringApplicationContext` | Subscriber Context đi vào pipeline | Phân biệt Reactor Context với Spring context |
| `anInfinitePublisherCanBeCancelled` | Có thể chủ động cancel nguồn không kết thúc | Tránh chờ completion vô hạn |
| `aBoundedVerificationCompletesWithinDeadline` | Verification có giới hạn thời gian | Ngăn suite treo khi thay source bằng nguồn chờ |

## 7. Kiểm thử `Mono`: onNext, empty, error và defer

### 7.1. Giá trị không phải toàn bộ hợp đồng

Một `Mono<T>` bình thường có thể:

1. Phát một giá trị rồi complete.
2. Complete mà không phát giá trị.
3. Phát error; không complete thành công.
4. Chưa phát terminal trong khoảng quan sát, ví dụ `Mono.never()`.

Test nên phân biệt rõ.

**Có dữ liệu:**

```java
StepVerifier.create(Mono.just(42))
        .expectNext(42)
        .verifyComplete();
```

**Không có dữ liệu, không lỗi:**

```java
StepVerifier.create(Mono.<Integer>empty())
        .verifyComplete();
```

**Lỗi:**

```java
StepVerifier.create(Mono.<Integer>error(
        new IllegalArgumentException("bad input")))
        .expectError(IllegalArgumentException.class)
        .verify();
```

**Nguồn không bao giờ kết thúc:**

```java
StepVerifier.create(Mono.never())
        .expectSubscription()
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

Bốn đoạn là **minh họa trong test**, không phải bốn chương trình Java độc lập. Với nguồn never, không dùng `verifyComplete()` vì không có terminal complete để chờ.

### 7.2. `Mono.defer` khác gọi source khi assembly

Giả sử một repository adapter ghi counter mỗi khi được gọi. Nếu service gọi adapter ngay khi trả Publisher:

```java
public Mono<String> eager(String key) {
    Mono<String> remote = repository.find(key);
    return remote.map(String::trim);
}
```

đây là **snippet minh họa** cho class có field `repository` phù hợp. Lời gọi `repository.find(key)` có thể đã xảy ra trong **assembly**, dù I/O bên trong `remote` chỉ chạy khi subscribe. “Reactive luôn lazy tuyệt đối” là mô tả quá đơn giản.

Muốn trì hoãn cả việc gọi adapter:

```java
public Mono<String> lazy(String key) {
    return Mono.defer(() ->
            repository.find(key).map(String::trim));
}
```

Với trường hợp này, assembly `lazy(key)` không gọi `repository.find(key)`; hành vi được kích hoạt khi subscribe. Test trong phần 6 kiểm tra rõ ranh giới này bằng `AtomicInteger`.

**Thận trọng:** Reactor có cả publisher cold và hot. Một nguồn hot có thể tạo tín hiệu độc lập với subscription; không áp dụng máy móc khái niệm “mọi thứ bắt đầu khi subscribe” cho tất cả nguồn.

### 7.3. Test exception phát ra trong operator

Nếu `map(...)` ném một exception (chẳng hạn `Math.multiplyExact` bị overflow), Reactor thường chuyển exception đó thành `onError` của pipeline. Có thể kiểm tra:

```java
StepVerifier.create(
        Mono.just(Integer.MAX_VALUE)
                .map(n -> Math.multiplyExact(n, 2)))
        .expectError(ArithmeticException.class)
        .verify();
```

Đây là snippet có import `Mono`/`StepVerifier`. Nó không nên dùng `assertThrows(() -> Mono.just(...).map(...))` nếu exception chỉ xảy ra **khi subscribe**; `assertThrows` quanh assembly có thể không quan sát được lỗi thật.

### 7.4. Kiểm thử `onErrorResume`/`onErrorReturn` phải kiểm tra terminal

```java
StepVerifier.create(
        Mono.<String>error(
                new IllegalStateException("offline"))
                .onErrorReturn("cached"))
        .expectNext("cached")
        .verifyComplete();
```

Khi dùng error recovery operator, nguồn ban đầu kết thúc bằng lỗi nhưng pipeline downstream đã chuyển thành giá trị và completion. Nếu test chỉ `expectNext("cached")` mà quên terminal, có thể bỏ sót một publisher còn giữ trạng thái bất thường.

## 8. Kiểm thử `Flux`: thứ tự, số lượng, nhu cầu và hủy

### 8.1. Kiểm tra từng phần tử và thứ tự

```java
StepVerifier.create(Flux.just("A", "B", "C"))
        .expectNext("A", "B", "C")
        .verifyComplete();
```

Kiểm tra này mạnh hơn `expectNextCount(3)` nếu thứ tự/giá trị là một phần hợp đồng.

**Chọn đúng độ chặt:** với `flatMap` bất đồng bộ, thứ tự giữa các inner publisher có thể thay đổi theo scheduler. Nếu nghiệp vụ không yêu cầu thứ tự, đừng dùng `expectNext(...)` theo thứ tự cứng rồi tạo test flaky. Có thể thu về danh sách/sort có chủ đích, dùng `collectList()` với assertion tương đương tập hợp, hoặc điều chỉnh operator như `concatMap` nếu chính hợp đồng yêu cầu thứ tự.

### 8.2. Cơ chế backpressure: bắt đầu từ demand bằng 0

Mặc định StepVerifier thường yêu cầu **unbounded demand**. Nếu muốn chủ động kiểm tra demand, dùng `initialRequest(0)` hoặc overload `StepVerifier.create(publisher, 0)` rồi gửi `thenRequest(n)`.

```java
StepVerifier.create(
        Flux.range(1, 4),
        StepVerifierOptions.create().initialRequest(0))
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(2)
        .expectNext(3, 4)
        .verifyComplete();
```

Đoạn trên minh họa một nguồn `Flux.range` đồng bộ tôn trọng demand. Nó không chứng minh mọi nguồn hoặc mọi operator đều gửi chính xác request 2/2 lên hệ thống ngoài; nhiều operator có **prefetch, buffer hoặc demand transformation**.

**Chú ý:** Reactive Streams cho phép onComplete/onError trong những tình huống không phụ thuộc có được request phần tử hay chưa. Đừng viết assertion “chưa request thì chắc chắn không thể complete/error” như một quy tắc tổng quát.

### 8.3. Kiểm tra cancellation

```java
StepVerifier.create(Flux.never())
        .expectSubscription()
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

Đây là kịch bản có chủ đích không chờ completion. `thenCancel` là một **tác động lên subscription**; nó không xác minh mọi tài nguyên (socket, subscription khác, file, executor) đã được release tức thời. Khi cleanup là một phần hợp đồng, thêm test riêng với mock resource, `doFinally(signalType)` hoặc counters phù hợp.

### 8.4. `expectNextCount` có thể làm test yếu đi

```java
StepVerifier.create(Flux.just("wrong1", "wrong2"))
        .expectNextCount(2)
        .verifyComplete();
```

Test này pass mặc dù dữ liệu có thể không đúng domain. Nó chỉ có ý nghĩa khi **số lượng** là điều cần kiểm tra. Đừng thay tất cả `expectNext(value)` bằng `expectNextCount(n)` chỉ để test bớt fail.

## 9. Kiểm thử thời gian bằng `StepVerifier.withVirtualTime`

### 9.1. Vì sao không nên dùng `Thread.sleep()`?

Giả sử service dùng `delayElement(Duration.ofHours(2))` hoặc `Flux.interval(Duration.ofHours(1))`. Nếu test chờ thời gian thật, suite sẽ rất chậm. Nếu rút xuống vài millisecond, test có thể flaky do scheduler/CI tải nặng.

`StepVerifier.withVirtualTime(...)` thay scheduler thời gian mặc định của Reactor bằng một **virtual scheduler**, rồi cho test tiến đồng hồ theo từng bước. Cách này xác minh **thứ tự tương đối của tín hiệu theo lịch Reactor** mà không thật sự chờ từng giờ.

### 9.2. Bắt buộc tạo publisher bên trong `Supplier`

**Đúng:**

```java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofHours(1)).take(2))
        .expectSubscription()
        .thenAwait(Duration.ofHours(1))
        .expectNext(0L)
        .thenAwait(Duration.ofHours(1))
        .expectNext(1L)
        .verifyComplete();
```

**Phản mẫu dễ sai:**

```java
Flux<Long> alreadyBuilt =
        Flux.interval(Duration.ofHours(1)).take(2);

StepVerifier.withVirtualTime(() -> alreadyBuilt)
        .expectSubscription()
        .thenAwait(Duration.ofHours(2))
        .expectNext(0L, 1L)
        .verifyComplete();
```

Trong phản mẫu, pipeline đã được xây trước khi virtual scheduler được kích hoạt. Một số operator chọn scheduler ngay lúc assembly; virtual time có thể không intercept được lịch, dẫn tới timeout/hang hoặc hành vi khó dự đoán. Vì vậy **Supplier phải tạo pipeline một cách lazy** trong lambda, không chỉ trả object đã được dựng sẵn.

### 9.3. `expectNoEvent` cũng xem subscription là một event

Ví dụ đúng:

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofHours(1)))
        .expectSubscription()
        .expectNoEvent(Duration.ofMinutes(59))
        .thenAwait(Duration.ofMinutes(1))
        .expectNext(0L)
        .verifyComplete();
```

Nếu bỏ `expectSubscription()` rồi gọi `expectNoEvent(...)` làm bước đầu, test có thể fail vì chính sự kiện subscribe xuất hiện trong khoảng “không có event”. Đặt `expectSubscription` trước khi bắt đầu khoảng chờ.

Một sự kiện phát đúng tại ranh giới thời gian có thể khiến assertion dễ hiểu nhầm, nên ví dụ dùng **59 phút không event** rồi **1 phút tiếp theo** để đạt mốc phát giá trị.

### 9.4. Giới hạn của virtual time

Virtual time không phù hợp cho mọi thứ:

- API/network/database thật không tự chạy nhanh hơn chỉ vì bạn tiến virtual clock Reactor.
- Code dùng `Thread.sleep`, `System.currentTimeMillis`, clock bên ngoài hoặc scheduler riêng không được thay thế có thể vẫn phụ thuộc thời gian thật.
- Một số toán tử/scheduler được khởi tạo trước khi bật virtual clock không được kiểm soát như mong muốn.
- Stream vô hạn, concurrency phức tạp hoặc các tác vụ cần thread tiến theo cơ chế thật có thể khiến verification bị khóa.
- Cài đặt virtual scheduler tác động vào scheduler factory của Reactor trong phạm vi test; cần tránh chạy những test virtual time xung đột song song khi ứng dụng dùng global scheduler state.

Giải pháp là tách code phụ thuộc thời gian thành đơn vị nhỏ, truyền `Scheduler`/`Clock` khi thiết kế yêu cầu và dùng test integration thực cho deadline/timeout ở ranh giới ngoài Reactor.

## 10. `TestPublisher`: nguồn giả có thể phát tín hiệu theo ý test

### 10.1. Khác với `Mono.just(...)` như thế nào?

`Mono.just(400)` là một nguồn tĩnh: giá trị đã biết. `TestPublisher` cho phép test **điều khiển thời điểm phát dữ liệu/lỗi/completion**. Điều này hữu ích khi mã được thử cần xử lý nguồn reactive đến chậm, khởi đầu trống, một loạt giá trị, hoặc lỗi xảy ra **sau** khi subscriber đã được đăng ký.

Ví dụ:

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux().map(n -> n * 2))
        .expectSubscription()
        .then(() -> source.next(2, 3).complete())
        .expectNext(4, 6)
        .verifyComplete();
```

Đoạn minh họa trên có thể đặt vào một test method cùng imports. `then(...)` chỉ chạy **sau khi StepVerifier đã subscribe**, nên không gửi dữ liệu quá sớm.

### 10.2. Hot source: lỗi thường gặp là emit trước subscription

`TestPublisher.create()` thông thường tạo một **hot TestPublisher**. Nó phát tín hiệu tới subscriber đang hiện diện, không phải luôn lưu mọi giá trị để phát lại cho subscriber đến sau.

**Phản mẫu:**

```java
TestPublisher<String> source = TestPublisher.create();
source.next("A");

StepVerifier.create(source.flux())
        .expectNext("A")
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

Lời gọi `next("A")` xảy ra **trước** subscription: với hot publisher, test có thể không nhận “A” và timeout/thất bại. Cách sửa là phát dữ liệu trong `then(...)` hoặc dùng `TestPublisher.createCold()` nếu mục tiêu là kiểm tra replay/cold semantics.

**Lưu ý:** `TestPublisher.createCold()` phục vụ mô hình cold/replay và không hoàn toàn giống hot source. Chọn loại phù hợp với dependency thật; đừng đổi sang cold chỉ để chữa một test vốn phải kiểm tra hot behavior.

### 10.3. Phân biệt `next`, `complete`, `error` và `emit`

- `next(value)` gửi `onNext`.
- `complete()` gửi `onComplete`.
- `error(exception)` gửi `onError`.
- `emit(values...)` gửi một hoặc nhiều giá trị rồi hoàn tất.

Ví dụ test error:

```java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux())
        .expectSubscription()
        .then(() -> source.error(
                new IllegalStateException("downstream failed")))
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                && "downstream failed".equals(error.getMessage()))
        .verify();
```

**Không trộn** một `onComplete` rồi tiếp tục `onNext` trong một compliant publisher. Nếu chủ đích cần kiểm thử code xử lý nguồn vi phạm spec, Reactor cung cấp `TestPublisher.createNoncompliant(...)` với các `Violation` cụ thể; đó là bài kiểm thử độ bền riêng, không phải nguồn nên dùng mặc định cho business unit tests.

### 10.4. TestPublisher và kiểm tra số request/subscribers

Tùy version, TestPublisher hỗ trợ các assertion như `assertSubscribers(...)`, `assertMinRequested(...)`, `assertMaxRequested(...)`, `assertCancelled(...)`. Các assertion này có ý nghĩa ở thời điểm cụ thể; một số cấu hình của TestPublisher dọn subscriber sau terminal, khiến assertion **sau khi complete** không còn phản ánh subscription trước đó theo cách bạn tưởng.

Trong ví dụ chạy được, `source.assertWasSubscribed()` được đặt **bên trong `then(...)` và trước `emit(...)`**, đảm bảo thời điểm quan sát rõ ràng. Nếu mục tiêu là kiểm tra nhánh subscribe **sau khi nguồn đã hoàn tất**, hãy ưu tiên `PublisherProbe` thay vì lạm dụng trạng thái nội bộ của TestPublisher.

### 10.5. Không dùng nguồn test có chủ đích vi phạm spec làm thước đo chung

Một publisher phát `null`, phát `onNext` vượt request, phát tín hiệu sau complete hoặc có nhiều terminal signal có thể đại diện cho một upstream lỗi. `createNoncompliant(...)` giúp tái hiện để kiểm thử operator/adapter robust, nhưng **không nên coi các tín hiệu ấy là hành vi hợp lệ của Reactive Streams**. Cần phân biệt rõ “test mong upstream xử lý sai vẫn không treo” với “test mô phỏng hành vi upstream chuẩn”.

## 11. `PublisherProbe`: kiểm tra nhánh fallback đã được subscribe hay chưa

### 11.1. Vì sao chỉ assert giá trị có thể chưa đủ?

Giả sử:

```java
Mono<String> selected =
        primary.switchIfEmpty(fallback);
```

Khi `primary` phát giá trị, fallback không nên được subscribe. Nhưng nếu hai nguồn cùng trả string `"OK"`, chỉ `expectNext("OK")` không chứng minh được **nhánh nào đã chạy**.

`PublisherProbe` bọc Publisher để ghi nhận subscribe/request/cancel mà không yêu cầu test tự phát data bằng TestPublisher.

### 11.2. Primary có giá trị: fallback không được subscribe

```java
PublisherProbe<String> primary = PublisherProbe.of(
        Mono.just("FIRST"));
PublisherProbe<String> fallback = PublisherProbe.of(
        Mono.just("BACKUP"));

StepVerifier.create(
        primary.mono().switchIfEmpty(fallback.mono()))
        .expectNext("FIRST")
        .verifyComplete();

primary.assertWasSubscribed();
primary.assertWasRequested();
fallback.assertWasNotSubscribed();
```

Đây là snippet có imports tương ứng. Ý nghĩa mạnh hơn chỉ so sánh `"FIRST"`: test phát hiện nếu code vô tình subscribe fallback, ngay cả khi giá trị cuối tình cờ giống mong đợi.

### 11.3. Primary empty: fallback được subscribe

```java
PublisherProbe<String> primary = PublisherProbe.empty();
PublisherProbe<String> fallback = PublisherProbe.of(
        Mono.just("BACKUP"));

StepVerifier.create(
        primary.mono().switchIfEmpty(fallback.mono()))
        .expectNext("BACKUP")
        .verifyComplete();

primary.assertWasSubscribed();
fallback.assertWasSubscribed();
fallback.assertWasRequested();
```

Dùng `PublisherProbe.empty()` để tạo một source hoàn tất rỗng mà vẫn ghi nhận hành vi subscribe/request. Đây là case đặc trưng cho `switchIfEmpty`.

### 11.4. TestPublisher và PublisherProbe giải quyết hai câu hỏi khác nhau

| Công cụ | Bạn chủ động điều khiển gì? | Bạn đo lường gì? |
|---|---|---|
| `Mono.just/empty/error` | Dữ liệu, completion/error đơn giản | Kết quả pipeline qua StepVerifier |
| `TestPublisher` | Thời điểm/source signals `onNext/onError/onComplete` | Hành vi khi downstream nhận tín hiệu có kiểm soát |
| `PublisherProbe` | Bọc một Publisher có sẵn hoặc nguồn empty | Nhánh có subscribe/request/cancel không |
| `StepVerifier` | Kịch bản subscriber, demand/time/cancel | Signals và terminal của chuỗi dưới test |

Hai công cụ TestPublisher và PublisherProbe có thể phối hợp trong một test, nhưng không cần nếu một nguồn `Mono.just(...)` và StepVerifier đã đủ để chứng minh hợp đồng.

## 12. Kiểm thử Reactor `Context` mà không dùng Spring `ApplicationContext`

### 12.1. Hai khái niệm context khác nhau hoàn toàn

- **Spring `ApplicationContext`:** container chứa bean, quản lý dependency injection, lifecycle và configuration.
- **Reactor `Context`:** dữ liệu gắn với subscription để operator có thể đọc bằng các API như `Mono.deferContextual(...)`, `contextWrite(...)`; không phải kho bean Spring và không giống ThreadLocal.

Với `reactor-test`, bạn có thể gắn một initial context vào StepVerifier:

```java
StepVerifier.create(
        Mono.deferContextual(context ->
                Mono.just(context.get("traceId"))),
        StepVerifierOptions.create().withInitialContext(
                Context.of("traceId", "trace-A")))
        .expectNext("trace-A")
        .verifyComplete();
```

Đây là snippet minh họa trong test Java có imports. Dữ liệu `trace-A` đến từ **Reactor subscriber context**, không phải Spring DI.

### 12.2. `expectAccessibleContext` là kiểm tra nâng cao

Trong bộ test hoàn chỉnh, ta dùng:

```java
StepVerifier.create(
        service.traceId(),
        StepVerifierOptions.create().withInitialContext(
                Context.of("traceId", "trace-42")))
        .expectAccessibleContext()
        .contains("traceId", "trace-42")
        .then()
        .expectNext("trace-42")
        .verifyComplete();
```

`expectAccessibleContext()` kiểm tra pipeline có context truy cập được; `contains(...)` xác nhận key/value; `then()` quay về các expectation tín hiệu. Một số publisher không tuân theo context-propagation mechanics của Reactor có thể không lộ context theo cách này; hãy kiểm thử đúng operator/library đang dùng.

**Không suy luận** Reactor Context tự động truyền MDC/ThreadLocal hoặc Spring Security context qua mọi thread. Tích hợp context propagation là một chủ đề riêng, phụ thuộc operator, scheduler và hỗ trợ framework.

## 13. Thời gian, Scheduler và các test bất đồng bộ thực

### 13.1. Vì sao test dùng `Thread.sleep` dễ thất thường?

Một phản mẫu:

```java
AtomicReference<String> seen = new AtomicReference<>();

service.someAsyncMono().subscribe(seen::set);
Thread.sleep(50);
assertEquals("OK", seen.get());
```

Đây là **snippet phản mẫu**, giả định method/field đã có. Nếu CI tải nặng hoặc scheduler bị delay, subscriber có thể chưa phát giá trị sau 50 ms dù code đúng. Nếu source phát lỗi và callback không xử lý, test có thể mất thông tin hoặc bị log ở nơi khác; một `subscribe()` bất đồng bộ đơn lẻ **không tự khiến JUnit chờ hoàn tất**.

Thay bằng StepVerifier:

```java
StepVerifier.create(service.someAsyncMono())
        .expectNext("OK")
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

Snippet này giả định service thật và method đúng kiểu; nó buộc test chờ trong giới hạn, xác nhận cả value lẫn terminal. Không dùng `block()` chỉ để biến mọi Reactive test thành imperative test nếu bạn cần kiểm tra nhiều tín hiệu, backpressure, cancellation hoặc Context.

### 13.2. Khi nào `block()` vẫn chấp nhận được?

`block()` có thể hữu ích ở ranh giới chuyển giữa reactive và imperative trong một số công cụ test/CLI, nhưng nó:

- Chỉ lấy kết quả terminal/value theo semantics phù hợp, không tự assert thứ tự nhiều `onNext`.
- Có thể làm mất sự phân biệt giữa empty value và một số cách xử lý `null`.
- Không trực tiếp xác nhận backpressure và request signal.
- Có thể gây lỗi nếu dùng trên Reactor non-blocking event-loop thread.

Với bài kiểm thử pipeline, StepVerifier thường biểu đạt hợp đồng tốt hơn. Nếu chỉ muốn tính một `Mono` đơn giản, cũng nên test error/empty và timeout có chủ đích.

### 13.3. Scheduler injected khác virtual scheduler toàn cục

Nếu service nhận một `Scheduler` qua constructor, có thể dùng `VirtualTimeScheduler` hoặc một scheduler test chuyên biệt cho đơn vị đó, thay vì dựa hoàn toàn vào việc thay Scheduler factory mặc định. Lựa chọn này có ích khi code dùng `publishOn(scheduler)` / `subscribeOn(scheduler)` với scheduler không phải mặc định.

Tuy nhiên, khi tiêm scheduler trực tiếp, vẫn cần quản lý lifecycle, disposal và test isolation. VirtualTimeScheduler không tự thay mọi Java clock hoặc I/O system.

### 13.4. `publishOn`, `subscribeOn` và thứ tự signal

Các toán tử này có thể thay thread thực thi và tác động scheduling. `StepVerifier` vẫn kiểm tra thứ tự **các tín hiệu mà subscriber nhìn thấy**. Nhưng không nên assert tên thread cụ thể nếu đó không phải hợp đồng được API hứa.

Khi code dùng `flatMap` có concurrency, thứ tự completion của inner sources có thể thay đổi. Muốn kiểm tra thứ tự, dùng toán tử có tính thứ tự phù hợp hoặc assertion không phụ thuộc ordering khi nghiệp vụ không yêu cầu. Nếu test dùng thời gian thật để tạo thứ tự tình cờ, đó thường là thiết kế dễ flaky.

## 14. Tính đúng của test: signal, error, cancellation và side effects

### 14.1. Chỉ xác nhận giá trị dễ bỏ sót resource cleanup

Một pipeline có thể phát đúng `"OK"` nhưng không release resource sau cancel. Nếu cleanup là hợp đồng, hãy kiểm chứng side effect cụ thể qua `doFinally(...)` hoặc fake resource/counter:

```java
AtomicInteger finallyCalls = new AtomicInteger();

Flux<Integer> source = Flux.<Integer>never()
        .doFinally(signalType ->
                finallyCalls.incrementAndGet());

StepVerifier.create(source)
        .expectSubscription()
        .thenCancel()
        .verify(Duration.ofSeconds(2));

assertEquals(1, finallyCalls.get());
```

Đây là snippet dành cho nguồn `Flux.never()` đồng bộ và `doFinally`, dùng import `AtomicInteger`. Với các tác vụ cleanup chạy bất đồng bộ, không khẳng định counter phải được cập nhật ngay trên thread test; cần chờ/quan sát phù hợp và quản lý tài nguyên thật.

### 14.2. Nếu upstream error thì không có `onComplete` thành công

Một reactive pipeline không thể hợp lệ vừa phát một `onError` terminal, vừa tiếp tục `onComplete` như một terminal thứ hai. Nếu dùng `onErrorResume`, terminal error ở upstream được **biến đổi** thành một Publisher khác, và downstream có thể kết thúc thành công. Phân biệt “upstream gặp lỗi” với “publisher mà test subscribe phát ra lỗi”.

Ví dụ:

```java
StepVerifier.create(
        Mono.<String>error(new IllegalStateException("fail"))
                .onErrorResume(error -> Mono.just("recovered")))
        .expectNext("recovered")
        .verifyComplete();
```

### 14.3. Error message và object identity

Test nên assert loại exception và một phần message khi chúng thuộc hợp đồng. Đừng ràng buộc toàn bộ stacktrace hoặc message có địa chỉ object/timing mang tính implementation.

Với domain error, `expectErrorSatisfies(...)` có thể dùng JUnit/AssertJ assertion:

```java
StepVerifier.create(
        Mono.<String>error(
                new IllegalArgumentException("bad quantity")))
        .expectErrorSatisfies(error -> {
            assertEquals(IllegalArgumentException.class,
                    error.getClass());
            assertEquals("bad quantity", error.getMessage());
        })
        .verify();
```

Trên JVM/test suite, thông tin stacktrace có thể khác nhưng type/message được bạn kiểm tra có thể ổn định.

## 15. Khi nào cần thêm Spring test hoặc WebTestClient?

Bài này chủ đích **ngoài Spring context**. Nhưng một lớp reactive service có thể tương tác với nhiều boundary; chọn đúng loại test:

| Mục tiêu | Công cụ thường phù hợp |
|---|---|
| Hàm `Flux/Mono` thuần, filter/map/retry/timeout | JUnit + reactor-test, không Spring |
| Service dùng adapter interface trả Mono/Flux | Fake/TestPublisher/PublisherProbe + StepVerifier |
| Validate DI/configuration properties/conditional bean | Spring test context phù hợp |
| WebFlux controller/router HTTP contract | `@WebFluxTest` hoặc WebTestClient |
| R2DBC repository query thật | R2DBC integration tests với database test |
| WebClient request/response protocol | Mock web server/contract test, hoặc WebClient test utilities theo version |
| TCP/HTTP server/network behavior | `RANDOM_PORT` + HTTP client hoặc environment-level test |
| Security filter chain/authorization | Spring Security test integration tương ứng |
| Tính đúng của Reactive Streams subscriber/operator tự xây | StepVerifier/TestPublisher, có thể cần spec compliance tests bổ sung |

**Không được hiểu “không dùng Spring context” nghĩa là “không thể test các publisher được tạo từ ứng dụng Spring Boot”.** Bạn chỉ cần tách đơn vị logic và truyền phụ thuộc cần thiết. Còn việc bean có thực sự được đăng ký/wire theo cấu hình Boot hay không là hợp đồng khác, cần kiểm thử ở lớp cao hơn.

### 15.1. Có nên dùng `@WebFluxTest` để kiểm tra một toán tử `map`?

Thông thường không. `@WebFluxTest` khởi tạo web layer slice, nặng hơn một JUnit test thuần. Nếu chỉ cần xác nhận `Flux.range(1,5).map(n -> n*2)`, một StepVerifier vài dòng đã đủ. Dùng WebFlux test khi thực sự cần mapping, codecs, validation, controller advice hoặc web filters.

### 15.2. Có thể dùng `WebTestClient` không khởi động server không?

Có, trong các chế độ bind tới controller/application context phù hợp, WebTestClient có thể kiểm thử handler/reactive web stack **mà không mở HTTP socket**. Nhưng đó là một công cụ **web-level testing**, khác với việc subscribe trực tiếp vào Mono/Flux bằng StepVerifier. Tên WebTestClient không tự nói request có qua mạng thật hay không; cần đọc setup là bind-to-controller/context hay bind-to-server.

## 16. Debugging và chẩn đoán khi StepVerifier thất bại

### 16.1. Khi test báo expected onNext nhưng nhận onError

- Kiểm tra data source phát `Mono.error` hay operator ném exception.
- Xem lỗi xuất hiện trước hay sau `switchIfEmpty`/`onErrorResume`.
- Xác nhận đã subscribe vào Publisher sau tất cả operator.
- Kiểm tra mapper có null/overflow/IllegalArgumentException không.
- Đừng sửa expected thành bất kỳ error nào nếu domain contract đòi value.

Ví dụ với `quote(...)`: nếu catalog trả `Mono.empty()`, hợp đồng service là lỗi `unknown sku`, không phải `Quote` mặc định. Test đúng nên kỳ vọng lỗi.

### 16.2. Khi test timeout hoặc treo vô hạn

- Có gọi method `verify...` không?
- Publisher có terminal signal không, hay `Flux.never()`?
- StepVerifier bắt đầu với initial request 0 nhưng quên `thenRequest(n)`?
- Dùng virtual time có tạo Publisher trong `Supplier` không?
- Có một `Thread.sleep` hoặc scheduler riêng không được virtualize?
- TestPublisher hot có phát tín hiệu **trước** subscription không?
- Có pipeline tự chặn event-loop bằng `block()`/đồng bộ hóa không?
- Có code async giữ tài nguyên hoặc bị deadlock do lock không?

Đặt `verify(Duration)` là bước bảo vệ hữu ích, nhưng timeout chỉ báo **không quan sát được kịch bản trong thời hạn**; nó không tự xác định nguyên nhân.

### 16.3. Khi test “pass” dù không chạy logic

- Có phải chỉ gọi `assertNotNull(mono)`?
- Có tạo `StepVerifier.create(...).expectNext(...)` nhưng quên `verify`?
- Có tự `subscribe()` rồi JUnit method kết thúc mà không chờ/error handler không?
- Có stub quá sâu, khiến logic cần thử bị thay hoàn toàn bằng `Mono.just(...)`?
- Có assertion kiểu `expectNextCount(n)` quá yếu?
- Có dùng `PublisherProbe` sai vị trí, đo nhầm Publisher đã được subscribe?
- Có so sánh object Publisher thay vì tín hiệu do nó phát ra không?

Test đáng tin phải xác nhận **hành vi downstream** ở đúng ranh giới và, khi cần, **nhánh upstream được dùng**.

### 16.4. Khi không tìm thấy class của reactor-test

Một số imports:

```java
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.TestPublisher;
import reactor.test.publisher.PublisherProbe;
```

Nếu build fail “package reactor.test does not exist”, kiểm tra `reactor-test` dependency có ở test scope, dependency management và test source set. Không thêm `@SpringBootTest` chỉ để giải quyết một import thiếu. Khi Reactor version bị trộn, chọn lại BOM/managed dependencies tương thích.

### 16.5. Khi assertion về context thất bại

Reactor Context là dữ liệu thuộc subscriber, không phải biến global. Nếu code đọc context ở vị trí khác, gắn initial context nhưng không truyền qua Publisher theo cơ chế Reactor hoặc dùng một non-Reactor publisher, expectation có thể sai. Kiểm tra `deferContextual` và chiều ảnh hưởng của `contextWrite`; không giả định dữ liệu tự động trở thành ThreadLocal.

## 17. Những ngộ nhận hay gặp

**“Phải dùng `@SpringBootTest` mới kiểm tra được `Mono`.”** Sai. Reactor là thư viện độc lập; JUnit + `reactor-test` có thể kiểm tra Publisher trực tiếp.

**“Tạo Mono nghĩa là code đã chạy.”** Không với nhiều nguồn cold/lazy. Assembly, subscription và signal emission là các giai đoạn khác nhau.

**“`StepVerifier.create(...)` tự chạy mọi assertion.”** Không. Phải gọi method verify.

**“`Mono.empty()` và `Mono.error(...)` đều không trả giá trị nên giống nhau.”** Sai. Một cái là successful completion, một cái terminal error.

**“`expectNextCount(5)` đủ để chứng minh 5 giá trị đúng.”** Sai. Nó chỉ kiểm tra số lượng các `onNext`.

**“Có thể dùng `Thread.sleep(20)` để chắc chắn publisher async hoàn thành.”** Không đáng tin, đặc biệt trong CI.

**“Virtual time làm mọi network I/O chạy ngay tức thì.”** Sai. Nó điều khiển scheduler thời gian Reactor tương thích, không tăng tốc máy chủ bên ngoài.

**“`expectNoEvent` có thể đặt đầu tiên trước `expectSubscription`.”** Dễ sai vì subscription cũng là event.

**“`TestPublisher.create()` luôn replay mọi signal.”** Sai. Loại hot không bảo đảm replay onNext trước khi subscribe.

**“`PublisherProbe` phải phát dữ liệu thủ công như TestPublisher.”** Sai. Nó bọc một Publisher hoặc nguồn empty và quan sát subscribe/request/cancel.

**“Gọi `block()` là cách kiểm thử backpressure.”** Sai. `block()` không tạo kịch bản request(n) và signal-by-signal như StepVerifier.

**“Reactor Context chính là Spring ApplicationContext.”** Sai. Chúng khác phạm vi, mục đích và cơ chế hoàn toàn.

## 18. Bài tập luyện tập và đáp án

### Bài tập A. Một Mono thành công nhưng không có value

Hãy kiểm tra `Mono.empty()` mà không dùng `block()`.

**Đáp án:**

```java
StepVerifier.create(Mono.<String>empty())
        .verifyComplete();
```

Không dùng `expectNext(null)` vì Reactor không coi null là giá trị hợp lệ.

### Bài tập B. Một nguồn phát hai phần tử rồi lỗi

Tạo `Flux.just("A", "B").concatWith(Mono.error(new IllegalStateException("stop")))`. Cần kiểm tra theo thứ tự A, B, error loại `IllegalStateException`.

**Đáp án:**

```java
StepVerifier.create(
        Flux.just("A", "B")
                .concatWith(Mono.error(
                        new IllegalStateException("stop"))))
        .expectNext("A", "B")
        .expectError(IllegalStateException.class)
        .verify();
```

Đây là snippet trong test JUnit có imports. Lưu ý `concatWith` trả về Flux kết thúc lỗi, nên **không** dùng `verifyComplete()` ở đây.

### Bài tập C. Chủ động phát lỗi sau khi subscribe

Cần TestPublisher mô phỏng upstream báo offline sau subscription.

**Đáp án:**

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.mono())
        .expectSubscription()
        .then(() -> source.error(
                new IllegalStateException("offline")))
        .expectErrorMessage("offline")
        .verify();
```

Điểm thiết yếu là phát `error` trong `then(...)`, sau subscription. Nếu chỉ assert message, type chưa được xác nhận; dùng `expectErrorMatches` khi domain contract cần cả type.

### Bài tập D. Vì sao test với `Flux.interval` bị treo?

Bạn tạo `Flux.interval(Duration.ofDays(1))` **trước** khi gọi `StepVerifier.withVirtualTime(() -> existingFlux)`. Hãy sửa.

**Đáp án:** đặt lời gọi `Flux.interval(...)` **bên trong supplier**, dùng `expectSubscription()` rồi `thenAwait(Duration.ofDays(1))` và `expectNext(0L)`. Nếu source vô hạn, cần `thenCancel()` sau phần đã kiểm chứng thay vì chờ `verifyComplete()`.

### Bài tập E. Primary và fallback có cùng giá trị

Cho primary và fallback đều trả `Mono.just("OK")`. Làm sao chứng minh fallback không được subscribe?

**Đáp án:** bọc hai source bằng `PublisherProbe.of(...)`, subscribe vào `primary.mono().switchIfEmpty(fallback.mono())`, StepVerifier expect `"OK"` rồi `verifyComplete()`, sau đó gọi `primary.assertWasSubscribed()` và `fallback.assertWasNotSubscribed()`. Chỉ so sánh `"OK"` sẽ không phân biệt nhánh.

### Bài tập F. Kiểm tra demand chính xác cho Flux.range

Nguồn `Flux.range(1,4)`, ban đầu request 0. Hãy request 1 rồi request 3 và mong 1, sau đó 2/3/4 rồi complete.

**Đáp án:**

```java
StepVerifier.create(Flux.range(1, 4), 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(3)
        .expectNext(2, 3, 4)
        .verifyComplete();
```

Khi thử publisher phức tạp hơn, nhớ rằng operator có thể prefetch hoặc gom demand; bài tập này dùng nguồn `Flux.range` để mô hình dễ kiểm chứng.

### Bài tập G. Mức độ kiểm thử cần có

Một service trả `Mono<Order>`, phụ thuộc một interface repository; bạn muốn kiểm tra fallback khi repository trả empty. Có cần chạy R2DBC database thật hay Spring context không?

**Đáp án:** nếu mục tiêu là **logic fallback**, không cần. Dùng fake `repository.findById(...) -> Mono.empty()` và StepVerifier. Nếu muốn chứng minh truy vấn SQL và transaction của repository hoạt động với database, cần test integration riêng với DB/test fixture phù hợp.

## 19. Checklist chất lượng trước khi chốt Reactive test

- [ ] Đã xác định publisher đang thử là `Mono` hay `Flux`, cold hay hot, kết thúc hay vô hạn.
- [ ] Mô tả được value signals, terminal signal và tác động cancel/demand nếu thuộc hợp đồng.
- [ ] Có method cuối cùng kích hoạt verification: `verify()`, `verifyComplete()` hoặc tương đương.
- [ ] Không dùng `assertNotNull(publisher)` thay cho test giá trị/terminal.
- [ ] Không dùng `Thread.sleep` để chờ logic bất đồng bộ trong CI.
- [ ] Không dùng `subscribe()` rồi để test kết thúc trước khi kết quả/lỗi đến.
- [ ] Với error, assert đúng type/message hoặc predicate theo hợp đồng.
- [ ] Với empty, xác nhận successful completion, không mong value null.
- [ ] Với Flux có thứ tự nghiệp vụ, assert chính xác thứ tự từng phần tử.
- [ ] Với backpressure, thiết lập initial request và `thenRequest` có chủ đích.
- [ ] Với nguồn vô hạn, dùng `thenCancel` thay vì đợi complete.
- [ ] Với virtual time, tạo Publisher bên trong Supplier sau khi scheduler được bật.
- [ ] Dùng `expectSubscription` trước `expectNoEvent`.
- [ ] Không kỳ vọng virtual time tăng tốc network/DB/Thread.sleep.
- [ ] Với `TestPublisher` hot, phát tín hiệu sau subscription bằng `then(...)`.
- [ ] Không dùng noncompliant publisher như mô hình business source mặc định.
- [ ] Với `PublisherProbe`, assert nhánh subscribe/request rõ ràng.
- [ ] Không nhầm Reactor Context với Spring ApplicationContext hoặc ThreadLocal.
- [ ] Đúng version `reactor-core`/`reactor-test` và BOM của Boot.
- [ ] Không khởi động Spring context nếu chỉ kiểm tra logic Reactive Streams.
- [ ] Bổ sung integration tests riêng cho DI, WebFlux endpoints, codecs, security, R2DBC hoặc network khi cần.
- [ ] Dùng timeout hợp lý đối với test có nguy cơ chờ vô hạn.
- [ ] Chạy đúng test task và kiểm tra số test thực thi trong IDE/Gradle/Maven/CI.

## 20. Kết luận

**`reactor-test` là công cụ kiểm chứng các hợp đồng Reactive Streams ngay trên Publisher, độc lập với Spring context.** `StepVerifier` mô tả và kiểm tra từng tín hiệu khi subscribe; `TestPublisher` cho phép điều khiển upstream; `PublisherProbe` xác nhận nhánh Publisher nào được dùng; virtual time và demand giúp kiểm tra timing/backpressure một cách rõ ràng và nhanh.

Một unit test Reactive tốt không cần chạy cả ứng dụng: nó cần **nguồn dữ liệu/fake hợp lệ**, **assertion về giá trị và terminal**, và **kiểm soát thời gian, subscription, request hoặc cancellation khi chúng là một phần hợp đồng**. Hãy để `@WebFluxTest`, `@SpringBootTest` và real HTTP/DB tests kiểm chứng những ranh giới framework/infra mà publisher unit test không thể tự chứng minh.

## Tài liệu tham khảo chính thức

- [Project Reactor — Testing (Reference Guide)](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, time manipulation, TestPublisher, PublisherProbe và Reactor Context.
- [Project Reactor — StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): các expectation, verify, initial request, cancellation và timeouts.
- [Project Reactor — StepVerifierOptions Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html): `initialRequest`, `scenarioName` và `withInitialContext`.
- [Project Reactor — TestPublisher Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html): hot/cold Publisher, signals, noncompliant modes và assertion timing.
- [Project Reactor — PublisherProbe Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html): xác minh subscribe/request/cancel của một nhánh.
- [Project Reactor — Mono & Flux](https://projectreactor.io/docs/core/release/reference/coreFeatures.html): nền tảng reactive pipelines.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): phân biệt unit testing với Spring application/web tests.
- [Reactive Streams JVM Specification](https://github.com/reactive-streams/reactive-streams-jvm): quy tắc request, onNext, onError, onComplete và cancellation.

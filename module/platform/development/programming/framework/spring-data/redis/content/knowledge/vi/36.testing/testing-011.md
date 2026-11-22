# Kiểm thử luồng phản ứng bằng StepVerifier

Trong **Spring Data Redis reactive**, những lời gọi như `ReactiveStringRedisTemplate.opsForValue().get(key)` không trực tiếp trả về một `String` mà tạo ra `Mono<String>`. Tương tự, thao tác duyệt tập hợp hoặc Stream có thể trả `Flux<T>`. Một chuỗi reactive chỉ thật sự phát tín hiệu khi có **subscriber**; kết quả không chỉ là giá trị mà còn có thể là **hoàn tất rỗng, lỗi, nhiều giá trị hoặc hủy subscription**.

**StepVerifier** thuộc module `reactor-test` của Project Reactor, dùng để **đăng ký vào một publisher và kiểm tra tuần tự các tín hiệu**. Trong kiểm thử Spring Data Redis, StepVerifier cho phép xác minh việc ghi–đọc key, cache miss, TTL, xử lý lỗi Redis, hành vi của `flatMap`/`concatMap`, retry, timeout và các tình huống bất đồng bộ mà không phải gọi `block()` hoặc dựa vào `Thread.sleep(...)`.

Bài học trình bày cách dùng StepVerifier từ unit test đến integration test với Redis thật, lựa chọn giữa thời gian thực và **virtual time**, phân biệt những điều StepVerifier có thể chứng minh với những điều phải được kiểm chứng ở Redis, và các lỗi thường gặp khi kiểm thử reactive pipeline.

## 1. Vì sao cách kiểm thử đồng bộ chưa đủ?

Với `StringRedisTemplate` đồng bộ, mã kiểm thử có thể đọc kết quả trực tiếp:

~~~java
String value = stringRedisTemplate.opsForValue().get("demo:key");
assertThat(value).isEqualTo("hello");
~~~

Trong API reactive:

~~~java
Mono<String> value =
    reactiveRedisTemplate.opsForValue().get("demo:key");
~~~

Biến `value` là **publisher**, không phải giá trị Redis đã tải. Kiểm tra `assertThat(value).isNotNull()` chỉ xác nhận object publisher tồn tại, không xác nhận lệnh `GET` thành công hoặc có giá trị đúng.

Một số code có thể viết:

~~~java
String value = reactiveRedisTemplate.opsForValue()
    .get("demo:key")
    .block();
~~~

`block()` đôi khi được dùng trong test để lấy giá trị, nhưng nó làm mất thông tin về **chuỗi các tín hiệu reactive**, có thể che vấn đề ordering, cancellation hoặc empty/error. Nó cũng dễ bị sao chép nhầm vào đường xử lý WebFlux, nơi blocking gây hại cho event-loop.

Với StepVerifier:

~~~java
StepVerifier.create(
        reactiveRedisTemplate.opsForValue().get("demo:key")
    )
    .expectNext("hello")
    .verifyComplete();
~~~

StepVerifier **tự subscribe**, chờ publisher phát `onNext("hello")`, rồi xác minh publisher `onComplete()` mà không phát thêm giá trị hoặc lỗi.

## 2. Hiểu chính xác các tín hiệu cần kiểm tra

Theo Reactive Streams, subscriber có thể quan sát:

| Tín hiệu | Ý nghĩa | Cách kiểm tra phổ biến |
| --- | --- | --- |
| `onSubscribe` | Publisher cung cấp subscription | `expectSubscription()` |
| `onNext(value)` | Có một giá trị được phát | `expectNext(value)`, `assertNext(...)` |
| `onComplete` | Luồng hoàn tất bình thường | `expectComplete()` / `verifyComplete()` |
| `onError(error)` | Luồng thất bại | `expectError(...)` / `verifyError(...)` |
| `cancel` | Subscriber dừng nhận thêm dữ liệu | `thenCancel()` |
| Không có tín hiệu trong một khoảng | Luồng đang chờ hoặc hoạt động theo thời gian | `expectNoEvent(Duration)` |

`Mono<T>` phát tối đa một `onNext`; `Flux<T>` có thể phát nhiều giá trị. Redis GET đối với key không tồn tại thường tạo `Mono.empty()`, tức **không có `onNext`, chỉ có `onComplete`**. Đây không phải `Mono.just(null)` và cũng không phải lỗi Redis.

~~~text
Mono.just("ok")         onSubscribe → onNext("ok") → onComplete
Mono.empty()            onSubscribe → onComplete
Mono.error(error)       onSubscribe → onError(error)
Flux.just("a","b")      onSubscribe → onNext("a") → onNext("b") → onComplete
Flux.never()            onSubscribe → không phát tín hiệu kết thúc
~~~

Khi kiểm thử một cache:

- **Hit:** `expectNext(value).verifyComplete()`.
- **Miss:** `verifyComplete()` nhưng không có `expectNext`.
- **Redis hỏng:** `expectError...` thay vì coi lỗi là cache miss.
- **Fallback:** kiểm tra giá trị nguồn dự phòng và tín hiệu hoàn tất.

## 3. Dependency và bộ khung dự án

Ví dụ với Java 21, Spring Boot 3.x và Gradle Groovy:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

`reactor-test` cung cấp `StepVerifier`. `spring-boot-starter-test` cung cấp JUnit 5, AssertJ, Mockito và các công cụ test thông dụng theo phiên bản Spring Boot tương ứng. `testcontainers-junit-jupiter` dùng để khởi động Redis thật trong integration test nếu máy có Docker.

Starter WebFlux có thể bỏ nếu dự án không cần HTTP reactive server; việc kiểm thử `Mono`/`Flux` từ Spring Data Redis không bắt buộc phải có controller WebFlux.

Những import thường dùng:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
~~~

Không cần gọi `publisher.subscribe()` thủ công trước `StepVerifier.create(...)`. StepVerifier là subscriber sẽ thực hiện việc đăng ký và quan sát các tín hiệu theo kịch bản.

## 4. Kịch bản đơn giản: giá trị, rỗng và lỗi

### 4.1. Mono có một giá trị

~~~java
@Test
void verifiesOneValueThenCompletion() {
    Mono<String> result = Mono.just("ready");

    StepVerifier.create(result)
        .expectNext("ready")
        .verifyComplete();
}
~~~

`verifyComplete()` xác nhận luồng đã phát đúng các tín hiệu được khai báo và kết thúc bằng `onComplete`. Nó không chấp nhận `onError` hoặc một giá trị dư ngoài dự kiến.

### 4.2. Mono rỗng

~~~java
@Test
void verifiesEmptyResult() {
    Mono<String> result = Mono.empty();

    StepVerifier.create(result)
        .verifyComplete();
}
~~~

Nếu pipeline có hành vi `switchIfEmpty`:

~~~java
@Test
void verifiesFallbackOnEmpty() {
    Mono<String> result = Mono.<String>empty()
        .switchIfEmpty(Mono.just("from-source"));

    StepVerifier.create(result)
        .expectNext("from-source")
        .verifyComplete();
}
~~~

Đây là cách kiểm thử hành vi cache miss: **không có dữ liệu** thì dùng nguồn thay thế, nhưng không tự coi đó là lỗi kết nối Redis.

### 4.3. Mono phát lỗi

~~~java
@Test
void verifiesError() {
    Mono<String> result = Mono.error(
        new IllegalArgumentException("invalid key")
    );

    StepVerifier.create(result)
        .expectErrorMatches(error ->
            error instanceof IllegalArgumentException
                && "invalid key".equals(error.getMessage())
        )
        .verify();
}
~~~

Các cách kiểm tra lỗi:

~~~java
StepVerifier.create(Mono.error(new IllegalStateException("failed")))
    .expectError(IllegalStateException.class)
    .verify();

StepVerifier.create(Mono.error(new IllegalStateException("failed")))
    .expectErrorMessage("failed")
    .verify();
~~~

Chọn assertion đủ rõ nhưng không quá phụ thuộc thông báo từ driver nếu message có thể thay đổi theo phiên bản Lettuce, Jedis hoặc Spring Data Redis. Với lỗi từ Redis thật, thường nên kiểm tra **nhóm exception hoặc behavior**, không khóa test vào toàn bộ stack trace.

### 4.4. Flux nhiều giá trị

~~~java
@Test
void verifiesMultipleValuesInOrder() {
    Flux<String> result = Flux.just("a", "b", "c");

    StepVerifier.create(result)
        .expectNext("a", "b", "c")
        .verifyComplete();
}
~~~

`expectNext("a", "b", "c")` khẳng định **thứ tự phát**. Điều này rất hữu ích khi pipeline dùng `concatMap`, nhưng không nên đặt cùng assertion cho `flatMap` có concurrency nếu nghiệp vụ không hứa giữ thứ tự.

## 5. Kiểm tra dữ liệu phức tạp bằng `assertNext` và `expectNextMatches`

Không phải response lúc nào cũng là String. Một service có thể trả DTO đã map từ Redis:

~~~java
public record ProductView(String id, String name, long priceCents) {
}
~~~

Test:

~~~java
@Test
void verifiesDtoFields() {
    Mono<ProductView> result =
        Mono.just(new ProductView("p-42", "Keyboard", 750000));

    StepVerifier.create(result)
        .assertNext(view -> {
            assertThat(view.id()).isEqualTo("p-42");
            assertThat(view.name()).isEqualTo("Keyboard");
            assertThat(view.priceCents()).isPositive();
        })
        .verifyComplete();
}
~~~

`assertThat` là API của AssertJ. `assertNext` phù hợp khi cần nhiều assertion trên object và muốn lỗi test chỉ ra trường nào sai.

Nếu chỉ cần một điều kiện boolean:

~~~java
StepVerifier.create(result)
    .expectNextMatches(view ->
        view.id().startsWith("p-")
            && view.priceCents() >= 0
    )
    .verifyComplete();
~~~

`expectNextMatches` nhận predicate. Khi predicate trả `false`, StepVerifier báo bước kỳ vọng thất bại. Với DTO nhiều field, `assertNext` thường giúp debug dễ hơn.

### Đặt tên cho từng kỳ vọng

Khi test có nhiều bước, có thể dùng `as(...)` để mô tả bước:

~~~java
StepVerifier.create(Flux.just("STARTED", "RUNNING", "DONE"))
    .expectNext("STARTED").as("initial state")
    .expectNext("RUNNING").as("progress state")
    .expectNext("DONE").as("terminal state")
    .verifyComplete();
~~~

Tên bước chỉ giúp chẩn đoán khi assertion thất bại; nó không thay đổi logic publisher.

## 6. Tạo service Spring Data Redis để kiểm thử

Ví dụ dưới xây một cache sản phẩm dùng `ReactiveStringRedisTemplate`:

- `save(...)`: ghi giá trị với TTL và trả ID khi Redis xác nhận ghi thành công.
- `load(...)`: trả tên sản phẩm, hoặc complete rỗng nếu key chưa có.
- `loadRequired(...)`: biến cache miss thành lỗi nghiệp vụ có thông báo rõ.
- `rename(...)`: đọc tên cũ, ghi tên mới, rồi trả giá trị mới theo dependency.

~~~java
package com.example.redis.testing;

import java.time.Duration;
import java.util.Objects;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveProductCache {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveProductCache(
            ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    private String key(String productId) {
        if (productId == null || productId.isBlank()) {
            throw new IllegalArgumentException(
                "productId must not be blank"
            );
        }
        return "cache:product:v1:" + productId;
    }

    public Mono<String> load(String productId) {
        return redis.opsForValue().get(key(productId));
    }

    public Mono<String> save(
            String productId, String name, Duration ttl) {
        Objects.requireNonNull(name);
        Objects.requireNonNull(ttl);

        return redis.opsForValue()
            .set(key(productId), name, ttl)
            .filter(Boolean.TRUE::equals)
            .switchIfEmpty(Mono.error(
                new IllegalStateException("Redis did not accept SET")
            ))
            .thenReturn(productId);
    }

    public Mono<String> loadRequired(String productId) {
        return load(productId)
            .switchIfEmpty(Mono.error(
                new java.util.NoSuchElementException(
                    "Product is not cached: " + productId
                )
            ));
    }

    public Mono<String> rename(
            String productId, String newName, Duration ttl) {
        Objects.requireNonNull(newName);

        return loadRequired(productId)
            .flatMap(previous ->
                save(productId, newName, ttl)
                    .thenReturn(newName)
            );
    }
}
~~~

Trong `save`, nếu `SET` trả `Mono<Boolean>` phát `false` thì `filter` tạo complete rỗng và `switchIfEmpty` chuyển thành lỗi; `thenReturn` chỉ chạy sau khi bước trước thành công. Nếu Redis phát `onError`, lỗi tự truyền xuống.

`rename` minh họa cách ghép publisher. Việc đọc trước rồi ghi sau **không phải transaction nguyên tử**: worker khác có thể thay đổi key giữa hai thao tác. Mục tiêu ở đây là kiểm thử **thứ tự và tín hiệu** trong pipeline, không phải cung cấp compare-and-set an toàn cho môi trường nhiều writer.

## 7. Unit test service mà không cần Redis server

Khi muốn kiểm tra cách service ghép `Mono` mà không thử network/driver, có thể mock `ReactiveStringRedisTemplate` cùng `ReactiveValueOperations`. Đây là **unit test composition**; việc Redis thực sự ghi đúng sẽ được kiểm tra trong integration test riêng.

~~~java
package com.example.redis.testing;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.core.ReactiveValueOperations;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ReactiveProductCacheUnitTest {

    private ReactiveStringRedisTemplate redis;
    private ReactiveValueOperations<String, String> values;
    private ReactiveProductCache cache;

    @BeforeEach
    void setUp() {
        redis = mock(ReactiveStringRedisTemplate.class);
        values = mock(ReactiveValueOperations.class);
        when(redis.opsForValue()).thenReturn(values);
        cache = new ReactiveProductCache(redis);
    }

    @Test
    void loadReturnsAValue() {
        when(values.get("cache:product:v1:p-1"))
            .thenReturn(Mono.just("Keyboard"));

        StepVerifier.create(cache.load("p-1"))
            .expectNext("Keyboard")
            .verifyComplete();
    }

    @Test
    void missingKeyCompletesWithoutValue() {
        when(values.get("cache:product:v1:unknown"))
            .thenReturn(Mono.empty());

        StepVerifier.create(cache.load("unknown"))
            .verifyComplete();
    }

    @Test
    void requiredValueReportsMissingKey() {
        when(values.get("cache:product:v1:unknown"))
            .thenReturn(Mono.empty());

        StepVerifier.create(cache.loadRequired("unknown"))
            .expectError(java.util.NoSuchElementException.class)
            .verify();
    }

    @Test
    void saveRequiresSuccessfulRedisResponse() {
        when(values.set(
                "cache:product:v1:p-1",
                "Keyboard",
                Duration.ofMinutes(5)))
            .thenReturn(Mono.just(true));

        StepVerifier.create(cache.save(
                "p-1", "Keyboard", Duration.ofMinutes(5)))
            .expectNext("p-1")
            .verifyComplete();
    }

    @Test
    void rejectedWriteDoesNotBecomeSuccess() {
        when(values.set(
                "cache:product:v1:p-1",
                "Keyboard",
                Duration.ofMinutes(5)))
            .thenReturn(Mono.just(false));

        StepVerifier.create(cache.save(
                "p-1", "Keyboard", Duration.ofMinutes(5)))
            .expectError(IllegalStateException.class)
            .verify();
    }
}
~~~

Ở đây `@BeforeEach` tạo mock riêng cho mỗi test nên cấu hình stubbing không rò giữa test. `StepVerifier` subscribe vào publisher từ service và kiểm tra tín hiệu.

`ReactiveValueOperations` là interface generic, nên Mockito và Java có thể phát cảnh báo *unchecked conversion* khi mock class generic. Cảnh báo không làm đổi ý nghĩa kiểm thử; dự án có thể dùng annotation suppression ở khai báo hẹp hoặc cách tạo mock tùy phiên bản.

Test này **không chứng minh** TTL được Redis gắn vào key, cũng không chứng minh sai serializer hay lỗi kết nối được driver translate đúng: những việc đó đòi integration test với Redis thật.

## 8. Integration test: Spring Boot, Redis thật và Testcontainers

Unit test ở trên điều khiển phản hồi của mock. Để kiểm tra Spring Data Redis reactive thực sự kết nối, serialize key, thực hiện lệnh `SET`/`GET` và gắn TTL, dùng một Redis riêng cho integration test.

Ví dụ cấu hình lớp test:

~~~java
package com.example.redis.testing;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(
    classes = ReactiveProductCacheIntegrationTest.TestApp.class
)
class ReactiveProductCacheIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(ReactiveProductCache.class)
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    ReactiveStringRedisTemplate redis;

    @Autowired
    ReactiveProductCache cache;

    @Test
    void writeThenReadWithStepVerifier() {
        String productId = "it-" + UUID.randomUUID();
        String key = "cache:product:v1:" + productId;

        Mono<String> workflow = cache.save(
                productId, "Mechanical Keyboard",
                Duration.ofMinutes(5)
            )
            .then(cache.load(productId));

        try {
            StepVerifier.create(workflow)
                .expectSubscription()
                .expectNext("Mechanical Keyboard")
                .expectComplete()
                .verify(Duration.ofSeconds(8));
        } finally {
            StepVerifier.create(redis.delete(key))
                .expectNextCount(1)
                .expectComplete()
                .verify(Duration.ofSeconds(8));
        }
    }

    @Test
    void missingKeyCompletesEmpty() {
        String productId = "missing-" + UUID.randomUUID();

        StepVerifier.create(cache.load(productId))
            .expectSubscription()
            .expectComplete()
            .verify(Duration.ofSeconds(8));
    }

    @Test
    void setAttachesPositiveTtl() {
        String productId = "ttl-" + UUID.randomUUID();
        String key = "cache:product:v1:" + productId;

        Mono<Duration> workflow = cache.save(
                productId, "Monitor", Duration.ofSeconds(60)
            )
            .then(redis.getExpire(key));

        try {
            StepVerifier.create(workflow)
                .assertNext(remaining ->
                    assertThat(remaining)
                        .isGreaterThan(Duration.ZERO)
                        .isLessThanOrEqualTo(Duration.ofSeconds(60))
                )
                .expectComplete()
                .verify(Duration.ofSeconds(8));
        } finally {
            StepVerifier.create(redis.delete(key))
                .expectNextCount(1)
                .expectComplete()
                .verify(Duration.ofSeconds(8));
        }
    }
}
~~~

`@Testcontainers` quản lý vòng đời Redis container. `@DynamicPropertySource` đưa host và cổng Redis đã được Testcontainers ánh xạ vào Spring Boot context. `@Import` đăng ký service của bài học, còn `@EnableAutoConfiguration` cho phép Spring Boot cấu hình reactive Redis template theo dependency.

Mỗi test dùng `UUID` trong key để tránh đụng dữ liệu của test khác. Sau kiểm tra, `finally` gửi `DELETE` bằng một publisher riêng và xác minh nó hoàn tất. Ví dụ chỉ dùng Redis test, không dùng `FLUSHDB`/`FLUSHALL`.

### Tại sao setup và assertion phải nằm cùng pipeline?

Nếu viết:

~~~java
cache.save(productId, "Monitor", Duration.ofMinutes(5));

StepVerifier.create(cache.load(productId))
    .expectNext("Monitor")
    .verifyComplete();
~~~

thì `cache.save(...)` chỉ **tạo `Mono`** và bị bỏ qua. Không có subscriber để gửi `SET`; lệnh đọc có thể trả empty. Ghép bằng `then(...)`:

~~~java
Mono<String> workflow = cache.save(
        productId, "Monitor", Duration.ofMinutes(5)
    )
    .then(cache.load(productId));

StepVerifier.create(workflow)
    .expectNext("Monitor")
    .verifyComplete();
~~~

`then` chờ phần ghi complete thành công trước khi subscribe phần đọc. Nếu phần ghi phát lỗi, phần đọc không được thực hiện. Đây là **thứ tự trong một subscription**, không tạo transaction Redis nguyên tử.

### Một số đặc điểm của integration test thực

- Cần Docker hoặc runtime tương thích với Testcontainers.
- Startup Redis, network và CI scheduling có thể mất thời gian; `verify(Duration.ofSeconds(8))` là một deadline **ví dụ**, phải điều chỉnh theo SLA test.
- `GET` trên key không tồn tại khác với lỗi kết nối Redis. Không viết test “missing key” bằng cách cố gắng ngắt Redis.
- TTL còn lại sẽ nhỏ hơn thời lượng đã đặt nếu đã trôi thời gian; không assert bằng chính xác `Duration.ofSeconds(60)`.
- Một Redis container độc lập **không chứng minh** kết nối Sentinel, Cluster hay failover; những topology đó cần integration environment riêng.

## 9. `verifyComplete`, `verifyError` và giới hạn thời gian chờ

StepVerifier có một số cách kết thúc:

~~~java
StepVerifier.create(Mono.just("ok"))
    .expectNext("ok")
    .verifyComplete();

StepVerifier.create(Mono.error(
        new IllegalStateException("failure")
    ))
    .verifyError(IllegalStateException.class);
~~~

Các dạng tiện lợi như `verifyComplete()` và `verifyError(...)` rất gọn. Trong integration test có I/O thật, có thể chỉ định **timeout cho bước verify**:

~~~java
StepVerifier.create(redis.opsForValue().get("cache:product:v1:p-1"))
    .expectSubscription()
    .expectNext("Keyboard")
    .expectComplete()
    .verify(Duration.ofSeconds(8));
~~~

`verify(Duration)` giới hạn **thời gian kiểm thử chờ publisher kết thúc**. Nó không tự đặt Redis command timeout trong Lettuce và không hủy những side effect đã được Redis xử lý trước khi timeout.

So sánh ba ranh giới:

| Deadline | Thiết lập ở đâu | Ý nghĩa |
| --- | --- | --- |
| Redis driver command timeout | Lettuce/Spring Redis client configuration | Driver giới hạn thời gian chờ kết quả command |
| Reactor `timeout(Duration)` | Operator trong publisher | Pipeline phát timeout khi upstream chưa có tín hiệu đúng hạn |
| StepVerifier `verify(Duration)` | Test | Test ngừng đợi khi kịch bản chưa hoàn tất trong thời gian quy định |

Không nên cố tình chọn timeout thật ngắn để “chạy test nhanh” nếu nó làm integration test thất bại ngẫu nhiên khi CI tải cao. Khi cần thử timeout có chủ đích, dùng test riêng có fault injection hoặc `VirtualTimeScheduler` ở tầng Reactor.

## 10. Virtual time: kiểm thử thời gian của Reactor mà không đợi thật

Các operator như `Mono.delay`, `Flux.interval`, `delayElements`, `timeout` hay `retryWhen(Retry.backoff(...))` có hành vi phụ thuộc thời gian. Nếu dùng thời gian thật, unit test có thể mất vài giây hoặc vài phút, dễ flaky.

`StepVerifier.withVirtualTime(...)` dùng scheduler thời gian ảo để điều khiển những operator **sử dụng Reactor scheduler tương thích**. Test có thể mô phỏng hai phút trôi qua trong thời gian rất ngắn.

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class VirtualTimeExampleTest {

    @Test
    void verifiesDelayedSignalWithoutWaitingTwoRealMinutes() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofMinutes(2))
                    .map(number -> "READY")
            )
            .expectSubscription()
            .expectNoEvent(Duration.ofMinutes(1))
            .thenAwait(Duration.ofMinutes(1))
            .expectNext("READY")
            .verifyComplete();
    }
}
~~~

Chú ý:

1. Publisher được tạo **bên trong supplier** truyền cho `withVirtualTime`, để Reactor có thể thay scheduler trước khi các operator thời gian được khởi tạo.
2. `expectSubscription()` đứng trước `expectNoEvent(...)`, vì subscription tự nó là một tín hiệu được StepVerifier quan sát.
3. `expectNoEvent` kiểm tra không có sự kiện trong một khoảng thời gian; `thenAwait` chỉ tiến thời gian ảo mà không thêm kỳ vọng “không có sự kiện”.
4. Virtual time điều khiển scheduler của Reactor, **không tua đồng hồ Redis server**.

### Tuyệt đối không dùng virtual time để giả lập TTL ở Redis thật

Giả sử ứng dụng gọi:

~~~java
reactiveRedis.opsForValue()
    .set("demo:key", "value", Duration.ofMinutes(5));
~~~

TTL năm phút được **Redis server** quản lý. Việc gọi `thenAwait(Duration.ofMinutes(5))` trong StepVerifier virtual time không khiến Redis server xóa key ngay lập tức. Nếu muốn kiểm thử TTL thực sự, hãy dùng Redis test với TTL ngắn, đọc `getExpire` hoặc polling bằng deadline thực.

Virtual time phù hợp để kiểm tra **thời điểm retry, delay và timeout ở tầng Reactor**, không phù hợp để giả vờ server Redis đã trải qua năm phút.

## 11. Kiểm thử retry và backoff

Một request Redis có thể gặp lỗi kết nối tạm thời. Reactor cung cấp `retryWhen` để thử lại publisher theo policy, nhưng test cần xác nhận **số lần subscribe**, **kết quả sau retry** và **những loại lỗi nào được retry**.

Ví dụ unit test một nguồn thất bại hai lần rồi thành công, với backoff 5 giây và 10 giây:

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

import static org.assertj.core.api.Assertions.assertThat;

class RetryExampleTest {

    @Test
    void retriesTwiceThenSucceedsUsingVirtualTime() {
        AtomicInteger subscriptions = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.defer(() -> {
                        int attempt = subscriptions.incrementAndGet();
                        if (attempt < 3) {
                            return Mono.<String>error(
                                new IOException("temporary")
                            );
                        }
                        return Mono.just("recovered");
                    })
                    .retryWhen(
                        Retry.backoff(2, Duration.ofSeconds(5))
                            .jitter(0.0)
                    )
            )
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(16))
            .expectNext("recovered")
            .verifyComplete();

        assertThat(subscriptions.get()).isEqualTo(3);
    }
}
~~~

`Retry.backoff(2, ...)` nghĩa là tối đa **hai lần retry sau lần thử ban đầu**. Ở ví dụ này, `jitter(0.0)` chỉ được dùng để thời điểm retry xác định trong unit test; trong production, jitter thường hữu ích để tránh nhiều instance retry cùng lúc.

### Đừng retry tất cả thao tác Redis

Lệnh `GET` có thể retry hữu hạn theo quy định nghiệp vụ, nhưng `INCR` hoặc `XADD` có thể đã được server thực thi trước khi response bị mất. Khi đó retry làm side effect xảy ra lần nữa:

~~~text
Client gửi INCR counter
          |
          v
Redis đã tăng counter
          |
          v
Response mất → client timeout
          |
          v
retryWhen → gửi INCR lần nữa
          |
          v
Counter bị tăng hai lần
~~~

StepVerifier chứng minh publisher **đã subscribe lại** và phát kết quả theo kịch bản. Nó không tự chứng minh retry một nghiệp vụ là an toàn; cần idempotency, ràng buộc dữ liệu hoặc đối soát.

### Kiểm thử bộ lọc retry

~~~java
Mono<String> invalidPayload = Mono.<String>error(
        new IllegalArgumentException("invalid payload")
    )
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(100))
            .filter(error ->
                error instanceof java.io.IOException
            )
    );

StepVerifier.create(invalidPayload)
    .expectError(IllegalArgumentException.class)
    .verify();
~~~

Vì lỗi `IllegalArgumentException` không khớp bộ lọc, pipeline truyền lỗi ngay thay vì retry. Với Redis, bộ lọc nên dựa trên exception type/cause sau khi hiểu cách Spring Data Redis dịch ngoại lệ.

## 12. Kiểm thử `Mono.timeout` khác với Redis command timeout

Giả sử một bước bất đồng bộ không bao giờ phát giá trị hoặc complete:

~~~java
Mono<String> neverResponds = Mono.<String>never()
    .timeout(Duration.ofSeconds(3));
~~~

Kiểm thử bằng virtual time:

~~~java
@Test
void timeoutAfterThreeVirtualSeconds() {
    StepVerifier.withVirtualTime(() ->
            Mono.<String>never()
                .timeout(Duration.ofSeconds(3))
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectError(java.util.concurrent.TimeoutException.class)
        .verify();
}
~~~

Test xác nhận operator `timeout` của Reactor phát lỗi đúng sau thời hạn chờ. Đây **không phải** bài test `RedisCommandTimeoutException` của Lettuce, vì không có Redis command nào trong publisher này.

Trong integration test với Redis thật, nếu mục tiêu là thử command timeout của driver, cần môi trường được kiểm soát để tạo network delay/connection failure, không chỉ dùng `Mono.never()`.

## 13. Kiểm thử thứ tự và concurrency của `Flux`

Khi một service nhận danh sách ID và truy vấn Redis cho từng ID, operator được chọn ảnh hưởng đến thứ tự kết quả:

~~~java
Flux<String> concurrent = Flux.just("a", "b", "c")
    .flatMap(id -> redis.opsForValue().get("cache:item:" + id));

Flux<String> ordered = Flux.just("a", "b", "c")
    .concatMap(id -> redis.opsForValue().get("cache:item:" + id));
~~~

`flatMap` có thể đăng ký nhiều publisher Redis đồng thời và merge kết quả theo thời điểm chúng phát. `concatMap` đợi publisher trước hoàn tất rồi mới đăng ký publisher sau, qua đó giữ thứ tự **của những publisher con trong pipeline**.

### Kiểm thử một hành vi có thứ tự

~~~java
@Test
void concatMapPreservesOrder() {
    Flux<String> result = Flux.just("first", "second")
        .concatMap(name ->
            Mono.delay(Duration.ofMillis(
                    "first".equals(name) ? 200 : 10
                ))
                .map(ignored -> name)
        );

    StepVerifier.withVirtualTime(() -> result)
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectNext("first", "second")
        .verifyComplete();
}
~~~

Ở dạng dùng virtual time, cách an toàn hơn là **tạo toàn bộ pipeline ngay trong supplier** của `withVirtualTime`, thay vì dùng một publisher đã được tạo trước đó có thể nắm giữ scheduler:

~~~java
@Test
void concatMapOrderWithPublisherCreatedInsideSupplier() {
    StepVerifier.withVirtualTime(() ->
            Flux.just("first", "second")
                .concatMap(name ->
                    Mono.delay(Duration.ofMillis(
                            "first".equals(name) ? 200 : 10
                        ))
                        .map(ignored -> name)
                )
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectNext("first", "second")
        .verifyComplete();
}
~~~

Đoạn thứ hai là mẫu nên áp dụng chung khi test Reactor virtual time. Nó kiểm chứng thứ tự phát trong cùng pipeline; không chứng minh nhiều instance Redis service không thể ghi vào cùng key cùng lúc.

### Kiểm thử `flatMap` mà không phụ thuộc thứ tự bất định

Nếu một tác vụ đọc nhiều key Redis độc lập và thứ tự không nằm trong hợp đồng, đừng viết:

~~~java
StepVerifier.create(unorderedValues)
    .expectNext("a", "b", "c") // Dễ flaky nếu flatMap chạy song song.
    .verifyComplete();
~~~

Một cách kiểm tra tập giá trị:

~~~java
import java.util.ArrayList;
import java.util.List;

Flux<String> result = Flux.just("a", "b", "c")
    .flatMap(Mono::just);

StepVerifier.create(result)
    .recordWith(ArrayList::new)
    .expectNextCount(3)
    .consumeRecordedWith(values ->
        assertThat(values).containsExactlyInAnyOrder("a", "b", "c")
    )
    .verifyComplete();
~~~

`recordWith` ghi lại các giá trị `onNext` để `consumeRecordedWith` kiểm tra về sau. Đây là cách phù hợp khi điều cần bảo đảm là **tập nội dung**, không phải thứ tự.

Tuy nhiên, nếu `Flux` có thể rất lớn hoặc vô hạn, không dùng `recordWith` để giữ mọi giá trị vào bộ nhớ. Có thể dùng `take(n)`, predicate hoặc kiểm thử trên một sample hữu hạn, theo hợp đồng nghiệp vụ.

## 14. Integration test với `Flux` Redis Set: thứ tự không cố định

Redis Set là tập hợp không bảo đảm thứ tự. Spring Data Redis reactive có thể phát các member bằng `Flux`, do đó nó rất thích hợp để minh họa kiểm thử **không giả định thứ tự**.

Ví dụ phương thức trong một integration test đã có `ReactiveStringRedisTemplate redis`:

~~~java
@Test
void setMembersContainExpectedValuesInAnyOrder() {
    String key = "it:tags:" + java.util.UUID.randomUUID();

    Flux<String> workflow = redis.opsForSet()
        .add(key, "redis", "reactor", "spring")
        .thenMany(redis.opsForSet().members(key));

    try {
        StepVerifier.create(workflow)
            .recordWith(java.util.ArrayList::new)
            .expectNextCount(3)
            .consumeRecordedWith(values ->
                assertThat(values).containsExactlyInAnyOrder(
                    "redis", "reactor", "spring"
                )
            )
            .expectComplete()
            .verify(Duration.ofSeconds(8));
    } finally {
        StepVerifier.create(redis.delete(key))
            .expectNextCount(1)
            .expectComplete()
            .verify(Duration.ofSeconds(8));
    }
}
~~~

`opsForSet().add(...)` trả `Mono<Long>` biểu diễn số member mới thêm. `thenMany(...)` chờ lệnh thêm hoàn tất rồi đăng ký luồng members. Test thu lại đúng ba giá trị và so sánh không xét thứ tự.

Với một Redis Set, `expectNext("redis", "reactor", "spring")` là một assertion sai về mặt hợp đồng: kể cả khi nhiều lần chạy đều thấy thứ tự đó, Redis không bảo đảm nó ổn định giữa các phiên bản hoặc lần thay đổi tập.

Nếu nghiệp vụ thực sự cần thứ tự, hãy dùng cấu trúc Redis và pipeline có định nghĩa thứ tự rõ, ví dụ Sorted Set theo score hoặc sắp xếp ở ứng dụng sau khi đọc dữ liệu hữu hạn.

## 15. Backpressure và `thenRequest` trong StepVerifier

Reactive Streams cho phép subscriber yêu cầu số lượng phần tử qua cơ chế demand. StepVerifier hỗ trợ tạo một subscription với **initial request** được cấu hình và yêu cầu thêm khi test cần.

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;

class DemandTest {

    @Test
    void checksRequestDemandStepByStep() {
        Flux<Integer> source = Flux.range(1, 3);

        StepVerifier.create(
                source,
                StepVerifierOptions.create().initialRequest(0)
            )
            .expectSubscription()
            .thenRequest(1)
            .expectNext(1)
            .thenRequest(2)
            .expectNext(2, 3)
            .verifyComplete();
    }
}
~~~

Test bắt đầu với demand bằng 0; sau đó yêu cầu một phần tử rồi hai phần tử nữa. Nó xác minh publisher đáp ứng đúng các phần tử đã yêu cầu.

**Backpressure không đồng nghĩa Redis tự rollback command hoặc chặn tất cả I/O đã gửi.** Một số driver/publisher có thể đã tạo command hoặc nhận dữ liệu từ server trước khi downstream yêu cầu thêm, tùy cách triển khai. StepVerifier kiểm tra ngữ nghĩa Reactive Streams ở ranh giới publisher, không cho phép kết luận tuyệt đối về thời điểm một byte được gửi qua socket.

Khi truy vấn nhiều key:

~~~java
Flux<String> values = Flux.fromIterable(productIds)
    .flatMap(id ->
        redis.opsForValue().get("cache:product:v1:" + id),
        8
    );
~~~

Tham số `8` giới hạn concurrency của inner publisher tại `flatMap`. Nó giúp kiểm soát mức đồng thời của pipeline, nhưng không phải một giới hạn cứng cho mọi tài nguyên Redis hoặc database trong toàn ứng dụng. Nếu nhiều HTTP request cùng chạy pipeline, tổng số operation vẫn có thể lớn.

## 16. Kiểm thử cancellation cho stream dài hạn

Một số publisher reactive có thể phát dữ liệu liên tục, như stream sự kiện, Pub/Sub hoặc một `Flux` polling. Các publisher này **không nhất thiết complete tự nhiên**. Nếu test chỉ viết `verifyComplete()`, nó có thể chờ mãi.

Với luồng dài hạn, hãy kiểm tra một vài tín hiệu rồi **hủy subscription**:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void cancellationTerminatesTheSubscription() {
    AtomicBoolean canceled = new AtomicBoolean(false);

    StepVerifier.withVirtualTime(() ->
            Flux.interval(Duration.ofSeconds(1))
                .doOnCancel(() -> canceled.set(true))
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectNext(0L, 1L, 2L)
        .thenCancel()
        .verify();

    assertThat(canceled.get()).isTrue();
}
~~~

Test chứng minh subscriber gửi tín hiệu cancel và callback `doOnCancel` được gọi. Nếu gắn `Flux` này vào một nguồn Redis thật, cần kiểm tra thêm rằng API/client phù hợp giải phóng subscription và connection khi cancel.

Đối với Redis Pub/Sub hoặc Redis Streams, cancellation của một reactive subscription **không thay đổi bảo đảm delivery của Redis**:

- Pub/Sub không lưu lại những message đã gửi trong khi subscriber không kết nối.
- Redis Streams có thể còn entry trong Stream/PEL tùy consumer group và ACK policy.
- Hủy subscription không đồng nghĩa mọi side effect đã thực hiện trước đó được rollback.

### Kiểm thử Redis Pub/Sub không được publish quá sớm

Nếu test tạo subscriber rồi ngay lập tức gọi `PUBLISH`, subscriber có thể chưa hoàn tất đăng ký channel tại Redis. Một message đầu tiên bị mất có thể khiến test thất bại ngẫu nhiên dù code subscriber đúng.

Kịch bản test có thể dùng:

1. Một channel riêng có UUID.
2. Cơ chế xác nhận subscription đã sẵn sàng, hoặc publish lại một message test đến khi có callback trong thời hạn hữu hạn.
3. StepVerifier xác nhận message có nội dung mong đợi.
4. `thenCancel()` để kết thúc subscription.
5. Dọn listener/container theo lifecycle của framework.

Đừng lấy cách publish lại message test làm chính sách retry cho sự kiện nghiệp vụ không lũy đẳng; đó là kỹ thuật **đồng bộ điều kiện sẵn sàng của integration test**, không thay thế message broker bền vững.

## 17. Kiểm tra nhánh fallback bằng `PublisherProbe`

Một bài test đôi khi cần chứng minh **publisher dự phòng đã được subscribe hay chưa**, không chỉ biết giá trị cuối giống nhau.

`PublisherProbe` thuộc `reactor-test`, dùng để quan sát subscription/request/cancellation của một nhánh trong pipeline.

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class FallbackProbeTest {

    @Test
    void subscribesFallbackWhenCacheIsEmpty() {
        PublisherProbe<String> database =
            PublisherProbe.of(Mono.just("from-database"));

        Mono<String> result = Mono.<String>empty()
            .switchIfEmpty(database.mono());

        StepVerifier.create(result)
            .expectNext("from-database")
            .verifyComplete();

        database.assertWasSubscribed();
        database.assertWasRequested();
    }

    @Test
    void doesNotSubscribeFallbackOnCacheHit() {
        PublisherProbe<String> database =
            PublisherProbe.of(Mono.just("from-database"));

        Mono<String> result = Mono.just("from-redis")
            .switchIfEmpty(database.mono());

        StepVerifier.create(result)
            .expectNext("from-redis")
            .verifyComplete();

        database.assertWasNotSubscribed();
    }
}
~~~

Điểm mạnh của `PublisherProbe` là xác minh **đúng nhánh đã được chạy**. Nếu nội dung từ Redis và database tình cờ giống nhau, chỉ kiểm tra `expectNext("value")` không chứng minh service đã dùng nhánh nào.

### Dùng `TestPublisher` để tự điều khiển nguồn tín hiệu

Một bài kiểm thử operator có thể cần phát các tín hiệu theo từng bước mà không dựa vào Redis network:

~~~java
import reactor.test.publisher.TestPublisher;

TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux().map(String::trim))
    .then(() -> source.next("  first  "))
    .expectNext("first")
    .then(source::complete)
    .verifyComplete();
~~~

`TestPublisher` giúp kiểm soát chính xác thời điểm `onNext`/`onComplete` trong unit test. Nó không kiểm tra Redis thực sự phân phối message, định tuyến key hay xử lý network timeout; những yêu cầu đó vẫn thuộc integration/fault-injection test.

## 18. Kiểm thử hành vi lỗi của service Redis

Trong hệ thống thật, service thường gắn một chính sách khi Redis lỗi: cache best-effort có thể trả dữ liệu nguồn; Redis Streams có thể giữ event chưa ACK; distributed lock phải từ chối công việc nếu trạng thái sở hữu không chắc chắn. StepVerifier giúp kiểm tra chính sách đó.

Ví dụ một service cache fallback chỉ với lỗi kết nối:

~~~java
package com.example.redis.testing;

import org.springframework.data.redis.RedisConnectionFailureException;
import reactor.core.publisher.Mono;

public final class CacheFallbackPolicy {

    public Mono<String> getOrFallback(
            Mono<String> redisValue,
            Mono<String> sourceValue) {
        return redisValue
            .onErrorResume(
                RedisConnectionFailureException.class,
                error -> sourceValue
            )
            .switchIfEmpty(sourceValue);
    }
}
~~~

Unit test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.RedisConnectionFailureException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class CacheFallbackPolicyTest {

    private final CacheFallbackPolicy policy =
        new CacheFallbackPolicy();

    @Test
    void fallsBackWhenRedisIsUnavailable() {
        PublisherProbe<String> source =
            PublisherProbe.of(Mono.just("database-value"));

        Mono<String> failed = Mono.error(
            new RedisConnectionFailureException(
                "connection unavailable"
            )
        );

        StepVerifier.create(
                policy.getOrFallback(failed, source.mono())
            )
            .expectNext("database-value")
            .verifyComplete();

        source.assertWasSubscribed();
    }

    @Test
    void propagatesBusinessErrorRatherThanMaskingIt() {
        PublisherProbe<String> source =
            PublisherProbe.of(Mono.just("database-value"));

        Mono<String> failed = Mono.error(
            new IllegalArgumentException("invalid product ID")
        );

        StepVerifier.create(
                policy.getOrFallback(failed, source.mono())
            )
            .expectError(IllegalArgumentException.class)
            .verify();

        source.assertWasNotSubscribed();
    }
}
~~~

Khi nhận `RedisConnectionFailureException`, service được phép fallback. Khi phát `IllegalArgumentException` do dữ liệu nghiệp vụ, service không che lỗi thành một cache miss giả. Việc dùng `PublisherProbe` xác nhận nhánh database có thực sự được subscribe.

Trong production, có thể cần nhận diện cả lỗi command timeout sau exception translation của Spring Data Redis. Tuy nhiên, **không thêm mọi exception vào fallback vô điều kiện**: nếu Redis đang chứa dữ liệu bắt buộc nhất quán, fallback có thể không an toàn.

### Lỗi serializer khác lỗi key không tồn tại

Một cache miss bình thường có thể hoàn tất rỗng:

~~~java
Mono<String> absent = Mono.empty();
~~~

Còn lỗi deserialization sẽ phát `onError`:

~~~java
Mono<String> corrupted = Mono.error(
    new org.springframework.data.redis.serializer.SerializationException(
        "cannot decode cached value"
    )
);
~~~

Hai trường hợp phải được kiểm thử riêng. Nếu service dùng `onErrorResume(error -> Mono.empty())` với tất cả lỗi, một JSON payload không tương thích có thể bị che khuất mãi mãi và chỉ biểu hiện như cache miss tăng cao.

## 19. Test lỗi kết nối, timeout thật bằng fault injection

Mock có thể chứng minh chính sách ứng dụng đối với exception; nó **không thể chứng minh client thật sẽ phát đúng exception đó khi mạng bị gián đoạn**. Để thử đường lỗi ở tầng Redis driver, cần một môi trường tích hợp có thể kiểm soát:

- Redis Testcontainer thật.
- Một network proxy/fault injector như Toxiproxy để tạo độ trễ, mất kết nối hoặc reset connection.
- Timeout của Lettuce/Spring Data Redis được cấu hình theo kịch bản.
- Deadline hữu hạn tại StepVerifier để test không bị treo.
- Key test và payload không nhạy cảm.

Quy trình minh họa:

~~~text
Test setup:
  Spring reactive Redis client → network proxy → Redis test container
                    |
                    v
             Redis bình thường
                    |
                    v
         StepVerifier kiểm tra GET thành công
                    |
                    v
        Fault injector làm đứt kết nối
                    |
                    v
            Gọi GET / SET có kiểm soát
                    |
                    v
         StepVerifier kiểm tra error/fallback
                    |
                    v
         Khôi phục network proxy
                    |
                    v
        Poll/verify Redis client hoạt động lại
~~~

**Không nên tạo Redis command timeout trên server production chỉ để chạy test.** Fault injection phải dùng Redis riêng, có cleanup và giới hạn thời gian. Một lệnh ghi bị timeout có thể đã được thực thi: test cần đối soát key/counter thật nếu kết luận về side effect, không suy ra “không có ghi” chỉ vì `StepVerifier` nhận `onError`.

### StepVerifier không phải công cụ giả lập Redis

| Điều cần kiểm tra | Công cụ phù hợp |
| --- | --- |
| Giá trị, empty, error, completion của `Mono` | StepVerifier + publisher unit test |
| Thứ tự kết quả, cancellation, backpressure của `Flux` | StepVerifier, `TestPublisher`, `PublisherProbe` |
| Backoff/delay/timeout do Reactor scheduler điều khiển | `StepVerifier.withVirtualTime` |
| `SET`/`GET`/`SADD` và TTL thực sự trên server | Spring Data Redis + Redis Testcontainers |
| Serializer hoạt động với payload Redis thật | Integration test với serializer và Redis test |
| Lỗi DNS, connection reset, command timeout driver | Fault injection qua hạ tầng network test |
| Redis Sentinel failover, Cluster redirects | Topology test chuyên biệt nhiều Redis node |
| Side effect nghiệp vụ không trùng khi retry | Integration test trên database/nguồn sự thật có idempotency |

StepVerifier rất mạnh ở việc xác minh **hợp đồng publisher**, nhưng không tự kiểm chứng độ bền dữ liệu, tính nhất quán Redis Cluster hay an toàn của thao tác nghiệp vụ có nhiều hệ thống.

## 20. Những nguyên nhân gây flaky test

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Test đôi khi nhận empty dù vừa gọi save | `save` tạo `Mono` nhưng chưa subscribe | Compose `save.then(load)` trong cùng publisher |
| Test chạy lâu hoặc không kết thúc | Publisher `Flux` vô hạn, không có `onComplete` | Dùng `thenCancel()` hoặc kiểm tra số event hữu hạn |
| `expectNext(a,b,c)` thỉnh thoảng sai | `flatMap` hoặc Redis Set không bảo đảm thứ tự | Dùng `concatMap` nếu cần thứ tự; nếu không, so sánh không xét thứ tự |
| Kiểm thử TTL không đúng khi virtual time | TTL nằm ở Redis server, không thuộc Reactor scheduler | Đọc `getExpire` hoặc dùng Redis test với TTL ngắn |
| Test bị treo khi Redis down | Không đặt deadline cho verify | Dùng `expectComplete().verify(Duration)` và timeout driver |
| Virtual-time test vẫn đợi thời gian thật | Publisher được tạo trước `withVirtualTime` hoặc dùng scheduler không chịu virtual time | Tạo pipeline trong supplier; kiểm tra scheduler |
| Test chạy 2 lần làm counter tăng 2 lần | Subscribe cùng cold publisher nhiều lần | Mỗi test chỉ subscribe có chủ đích; kiểm tra side effect |
| Assertion TTL còn lại bằng chính xác TTL gốc | Thời gian đã trôi giữa `SET` và `getExpire` | Dùng khoảng dương có dung sai |
| Test Pub/Sub bỏ lỡ message đầu tiên | Subscriber chưa đăng ký xong | Đồng bộ sẵn sàng trước publish hoặc dùng polling có timeout trong test |
| Test fail do key khác ghi đè | Dùng key cố định giữa các test chạy song song | Tạo key có UUID/prefix riêng, cleanup từng key |
| Test thỉnh thoảng báo timeout trên CI | Deadline quá sát network/container startup | Đặt timeout hợp lý, giám sát nguyên nhân chậm |
| `assertNext` không bao giờ được gọi | Upstream complete rỗng | Dùng `switchIfEmpty` nếu cần fallback; kiểm tra empty riêng |
| Lỗi serializer bị coi là miss | `onErrorResume` nuốt mọi exception | Chỉ fallback cho lỗi phù hợp với policy |
| Unit test mock pass nhưng production fail | Mock bỏ qua serialization, network và actual command semantics | Bổ sung integration test với Redis thật |
| `then` chạy bước sau dù `SET` trả false | `then` chỉ đợi complete, bỏ Boolean | Kiểm tra `Boolean.TRUE` trước `then` |
| Retry làm `INCR` tăng lặp | Test chỉ kiểm tra kết quả sau retry, không kiểm tra side effect | Thiết kế idempotency và kiểm thử trạng thái cuối |

### Đặc biệt tránh `Thread.sleep` để đồng bộ test

Một test dạng:

~~~java
publisher.subscribe(value -> received.set(value));
Thread.sleep(200);
assertThat(received.get()).isEqualTo("value");
~~~

không ràng buộc được khi nào callback chạy. Trên máy nhanh có thể pass, trên CI đang tải có thể fail. Hơn nữa, `subscribe()` thủ công và việc đọc biến đồng thời phải được thiết kế đúng về visibility và lifecycle.

Nếu publisher có tín hiệu hoàn tất hữu hạn, dùng:

~~~java
StepVerifier.create(publisher)
    .expectNext("value")
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

Nếu publisher được phép phát chậm theo thời gian do Reactor quản lý, dùng virtual time. Nếu cần Redis server thật sự trở lại trạng thái mong đợi sau sự cố, dùng polling có timeout dựa trên **điều kiện quan sát được**, không chỉ một lần chờ cố định.

## 21. Định nghĩa mục tiêu test trước khi viết assertion

Một test tốt bắt đầu từ câu hỏi **nghiệp vụ hoặc hợp đồng publisher cần bảo đảm điều gì**:

| Câu hỏi kiểm thử | Assertion đề xuất |
| --- | --- |
| Lệnh đọc Redis trả đúng giá trị? | `expectNext(expected).expectComplete()` |
| Key không tồn tại thì service làm gì? | `verifyComplete()` hoặc `switchIfEmpty` + `expectNext(fallback)` |
| Lỗi từ Redis có bị che thành thành công? | `expectError(...)` hoặc `expectErrorMatches(...)` |
| Lệnh ghi thành công trước khi đọc? | Một pipeline `save().then(load())` với StepVerifier |
| Redis có thật sự nhận TTL? | Integration test `getExpire(key)` và kiểm tra khoảng hợp lệ |
| Data trong Redis Set có đủ không? | `recordWith` + `containsExactlyInAnyOrder` |
| Service có chạm database khi cache hit? | `PublisherProbe.assertWasNotSubscribed()` |
| Service có fallback khi Redis lỗi đúng nhóm? | Kiểm tra tín hiệu + `PublisherProbe.assertWasSubscribed()` |
| Retry bao nhiêu lần? | Counter ở `Mono.defer` + virtual time |
| Một stream vô hạn có hủy được không? | `thenCancel()` và callback `doOnCancel` |
| Publisher đáp ứng demand không? | `StepVerifierOptions.initialRequest(0)` + `thenRequest` |
| Redis bị failover thì client tự reconnect? | Integration test topology, không chỉ mock `Mono` |

Đặc biệt, StepVerifier không chạy các assertion mã nguồn chỉ vì ta tạo ra publisher. **Phải có lời gọi verify**: `verify()`, `verifyComplete()`, `verifyError(...)` hoặc biến thể có timeout.

## 22. Mẫu quy trình kiểm thử trong dự án Spring Data Redis

Một quy trình dễ duy trì có thể chia thành bốn tầng:

1. **Unit test operator:** dùng `Mono.just`, `Mono.empty`, `Mono.error`, `Flux.just` và StepVerifier. Kiểm tra map, flatMap, concatMap, then, empty, error và cancellation.
2. **Unit test service:** mock reactive Redis operations hoặc dùng `PublisherProbe` để kiểm tra policy fallback, retry, thứ tự subscribe và quy tắc kiểm tra `Boolean` từ Redis command.
3. **Integration test Redis:** dùng Testcontainers, key độc lập, Spring Boot context và StepVerifier; xác minh giá trị thật, Redis Set, TTL, serializer và cleanup.
4. **Resilience test:** lỗi mạng/failover thật trong hạ tầng riêng, đối soát trạng thái nếu command ghi có thể đã thành công trước timeout.

Một ví dụ luồng CI:

~~~text
        Thay đổi code Reactive Redis
                    |
                    v
             JUnit unit tests
             StepVerifier + mocks
                    |
                    v
          Reactor virtual-time tests
              Retry / timeout
                    |
                    v
           Redis integration tests
              Testcontainers
                    |
                    v
            Fault-injection tests
          (khi dự án có hạ tầng riêng)
                    |
                    v
          Quan sát và đối soát kết quả
~~~

Không bắt buộc mỗi pull request đều chạy một topology failover lớn nếu chi phí cao, nhưng những nhánh có cam kết độ tin cậy quan trọng cần được kiểm thử định kỳ trong môi trường mô phỏng sát thực tế.

## 23. Tổng kết

**StepVerifier là công cụ cốt lõi để kiểm thử tín hiệu của `Mono` và `Flux` trong Spring Data Redis reactive.** Thay vì gọi `block()` để lấy một giá trị và bỏ qua các trường hợp khác, StepVerifier mô tả rõ publisher phải phát gì và phải kết thúc như thế nào:

- `expectNext`, `assertNext` và `expectNextMatches` kiểm tra dữ liệu.
- `verifyComplete` và `expectComplete` kiểm tra hoàn tất bình thường.
- `expectError` kiểm tra lỗi thay vì che lỗi thành cache miss.
- `recordWith` và `consumeRecordedWith` kiểm tra kết quả `Flux` khi thứ tự không được bảo đảm.
- `thenRequest` và `thenCancel` kiểm tra demand và cancellation.
- `withVirtualTime` kiểm tra delay, timeout và backoff của Reactor mà không đợi thời gian thật.
- `PublisherProbe` và `TestPublisher` giúp kiểm tra nhánh fallback và tạo tín hiệu theo ý muốn trong unit test.

Khi kết hợp với **Redis Testcontainers**, StepVerifier còn giúp xác minh thao tác ghi–đọc, TTL và các API reactive của Spring Data Redis bằng dữ liệu thật. Tuy nhiên, test virtual time không làm Redis server hết hạn key, một lỗi timeout không chứng minh command chưa được thực thi, và một unit test bằng mock không kiểm tra được network/serializer/failover thật.

Nguyên tắc quan trọng nhất: **kiểm tra đúng hợp đồng publisher, không giả định thứ tự hoặc thời gian mà API không bảo đảm; dùng Redis thật khi muốn chứng minh hành vi Redis, và kiểm thử idempotency riêng khi có side effect.** Nhờ vậy, các luồng reactive có thể được kiểm thử rõ ràng, ổn định và sát yêu cầu nghiệp vụ.

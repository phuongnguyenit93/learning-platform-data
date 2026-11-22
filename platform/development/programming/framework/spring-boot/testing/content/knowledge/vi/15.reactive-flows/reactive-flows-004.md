# Virtual time cho delay, timeout và retry trong Reactor/Spring Boot

> **Module:** Spring Boot – testing  
> **Nhóm:** Luồng Reactive  
> **Trọng tâm:** Dùng `StepVerifier.withVirtualTime` và `VirtualTimeScheduler` để kiểm chứng thời gian của `delay`, `timeout` và `retryWhen` mà không phải đợi đồng hồ thực chạy từng giây, phút hoặc giờ.

## 1. Tại sao một reactive test theo thời gian thường khó?

Reactive streams không nhất thiết phát dữ liệu ngay sau khi ta gọi một method. Nhiều operator sử dụng `Scheduler` để lên lịch hành vi:

- `Mono.delay(Duration)` phát một tín hiệu sau khoảng chờ.
- `Mono#delayElement(Duration)` trì hoãn phát một phần tử.
- `Flux#delayElements(Duration)` tạo khoảng cách thời gian giữa các phần tử.
- `Flux.interval(Duration)` phát số thứ tự theo nhịp.
- `timeout(Duration)` chuyển thành lỗi khi không có tín hiệu phù hợp trước thời hạn.
- `retryWhen(Retry.fixedDelay(...))` đợi giữa các lượt thử lại khi upstream báo lỗi.
- `Retry.backoff(...)` tạo khoảng chờ tăng theo cấp số nhân, có thể có jitter.

Một test sai hướng thường viết:

```java
Flux<String> events = service.events();
Thread.sleep(5000);
assertEquals(..., collectedEvents);
```

Đoạn trên **chỉ minh họa anti-pattern**, không phải chương trình Java độc lập. Nó có nhiều vấn đề:

1. Test chạy chậm đúng bằng thời gian phải đợi.
2. CPU scheduling, CI load và network làm phép đợi dễ flaky.
3. `Thread.sleep` không tự subscribe vào một reactive publisher; nếu không có subscriber, pipeline có thể chưa chạy.
4. Nếu ngủ 5 giây nhưng code lỗi phát tín hiệu ở giây thứ 3, một phép assert chỉ nhìn kết quả cuối có thể vẫn pass.
5. Khi cần thử retry với backoff dài hàng phút hoặc ngày, test thực tế trở nên rất tốn thời gian.

**Virtual time** giải quyết phần liên quan đến **đồng hồ lên lịch trong Reactor**: bộ kiểm thử chủ động tiến đồng hồ từ `t=0` lên `t=5s`, `t=20s`… mà không chờ tương ứng trong đời thực. Nó không thể tua nhanh HTTP/network, JDBC, `Thread.sleep` hoặc bất kỳ thao tác blocking nào không được tích hợp với virtual scheduler.

## 2. Mô hình tinh thần: thời gian thực và thời gian ảo khác nhau

Trong Reactor, một operator thời gian sử dụng `Scheduler` để đặt công việc vào tương lai. Khi dùng scheduler thật, công việc được đánh thức theo clock thật. Khi dùng `VirtualTimeScheduler`, công việc được lưu trong hàng đợi, kèm thời điểm ảo sẽ chạy. Test gọi `thenAwait` hoặc `expectNoEvent` để đẩy đồng hồ ảo tới mốc đó.

```text
                    THỜI GIAN THỰC

test subscribe    sleep/wait 5s       onNext("ready")
     |-------------------------------|
   wall 0s                        wall 5s

                    THỜI GIAN ẢO

test subscribe    advance virtual clock    onNext("ready")
     |.......................|
   virtual 0s             virtual 5s

    Thời gian chờ thật: thường rất nhỏ, không phải 5s.
```

Hai kiểu thời gian phải phân biệt:

| Khái niệm | Ý nghĩa | Dùng trong test |
| --- | --- | --- |
| **Virtual clock** | Đồng hồ của `VirtualTimeScheduler` | Tua `Duration` để kích hoạt delayed tasks |
| **Wall-clock duration** | Thời gian thật của máy/CI | Giới hạn thời gian treo test với `verify(Duration)` |
| **Scheduler** | Thành phần thực thi/lên lịch tác vụ | Operator thời gian sử dụng scheduler phù hợp |
| **Subscription** | Tín hiệu `onSubscribe` bắt đầu pipeline | Phải xảy ra trước khi advance và chờ signals |
| **Backpressure/request** | Subscriber yêu cầu bao nhiêu phần tử | Có thể ảnh hưởng `Flux.interval` và các publisher khác |
| **Cancellation** | Subscriber/timeout dừng một subscription | Không tương đương việc upstream đã thành công |

**Nguyên tắc:** test không chỉ đo *cuối cùng có giá trị gì*; nó còn có thể đo **không được phát trước deadline nào**, **phát ngay sau khi advance tới mốc nào**, **bao nhiêu lần source được subscribe**, và **khi timeout thì lỗi/fallback/cancellation có đúng không**.

## 3. `StepVerifier.withVirtualTime` làm việc như thế nào?

`StepVerifier` là công cụ trong module `reactor-test` để kiểm tra chuỗi Reactive Streams signals: subscription, next value, completion hoặc error. Khi dùng:

```java
StepVerifier.withVirtualTime(() -> Mono.delay(Duration.ofDays(1)))
    .expectSubscription()
    .thenAwait(Duration.ofDays(1))
    .expectNext(0L)
    .verifyComplete();
```

test không cần đợi 24 giờ thực. `withVirtualTime` thiết lập `VirtualTimeScheduler` cho những scheduler factories mặc định mà Reactor quản lý; vì vậy nhiều operator như `Mono.delay`, `timeout` và retry delays có thể dùng đồng hồ ảo.

**Hai điều kiện quyết định thành công:**

1. Publisher/operator sử dụng clock ảo, không dùng một scheduler thật đã tạo sẵn ở nơi khác.
2. Publisher cần được **tạo bên trong `Supplier` truyền vào `withVirtualTime`**, sau khi virtual scheduler đã được cài đặt.

### 3.1. Vì sao tham số phải là `Supplier`?

Sai hướng:

```java
// KHÔNG nên tạo timed publisher trước withVirtualTime:
Mono<Long> value = Mono.delay(Duration.ofHours(1));

StepVerifier.withVirtualTime(() -> value)
    .expectSubscription()
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .verifyComplete();
```

Đoạn trên là **anti-pattern**, có thể lấy scheduler thật trong lúc assembly và không được virtual time điều khiển. Hậu quả có thể là treo, fail hoặc test chạy theo thời gian thật. Không dựa vào một lần pass tình cờ để kết luận thiết kế đúng.

Đúng:

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(1)))
    .expectSubscription()
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .verifyComplete();
```

Toàn bộ việc tạo `Mono.delay` xảy ra **bên trong lambda**, lúc virtual scheduler đã hoạt động.

Nếu production code là method:

```java
Mono<String> messageAfter(Duration duration) {
    return Mono.just("ready").delayElement(duration);
}
```

thì test nên gọi method **trong lambda**:

```java
StepVerifier.withVirtualTime(
        () -> service.messageAfter(Duration.ofHours(1)))
    .expectSubscription()
    .thenAwait(Duration.ofHours(1))
    .expectNext("ready")
    .verifyComplete();
```

Hai snippet method/test trên chỉ minh họa. Project hoàn chỉnh ở phần 6 sử dụng method `delayedGreeting`. Một publisher được tạo trước lambda có thể chứa scheduler đã chốt sẵn; việc `Mono.defer` bên trong service giúp dời thao tác tạo nguồn tới subscribe khi cần, nhưng không thể sửa mọi scheduler được khởi tạo sớm.

### 3.2. `expectSubscription` và `expectNoEvent`

`expectNoEvent(Duration)` assert rằng **không có sự kiện nào xuất hiện** trong quãng thời gian chỉ định. Tín hiệu `subscription` cũng được tính là một event.

Vì vậy:

```java
StepVerifier.withVirtualTime(() -> Mono.delay(Duration.ofSeconds(5)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(4))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .verifyComplete();
```

đúng với ý đồ: sau subscription phải im lặng trong bốn giây ảo, rồi ở mốc năm giây phát `0L` và complete.

Không đặt `expectNoEvent(Duration)` là bước đầu tiên khi pipeline cần subscribe: subscription signal ngay lập tức khiến assertion thất bại. Hãy dùng `expectSubscription()` trước.

### 3.3. `thenAwait` khác `expectNoEvent`

| API | Tác dụng | Có kiểm tra sự im lặng? |
| --- | --- | --- |
| `thenAwait(Duration)` | Tiến clock/đợi để signals có cơ hội xuất hiện | **Không** |
| `expectNoEvent(Duration)` | Tiến clock/đợi, đồng thời fail nếu có event trong khoảng đó | **Có** |
| `expectNext(value)` | Đòi một `onNext` với giá trị đã định | Không biểu đạt deadline riêng |
| `expectNextCount(n)` | Đòi đủ số `onNext` | Không bảo vệ từng giá trị |
| `expectError(Class)` | Đòi terminal error đúng loại | Không bảo vệ thông điệp/cause nếu chưa assert |
| `verifyComplete()` | Kích hoạt verify và đòi complete | Có thể chờ vô hạn nếu virtual clock không được tiến |

Ví dụ cần chứng minh “**không được có email gửi ra trước 5 phút**” nên dùng `expectNoEvent` ở khoảng cần bảo vệ, không chỉ `thenAwait` rồi assert cuối cùng.

## 4. Không phải mọi thao tác bất đồng bộ đều chạy bằng virtual time

`StepVerifier.withVirtualTime` hoạt động khi timed operators lấy scheduler từ Reactor `Schedulers` factories đã được thay, thường là `Schedulers.parallel()`. Nó **không** tự kiểm soát:

- `Thread.sleep(5000)` ở bên trong `Mono.fromCallable`.
- HTTP call từ `WebClient` chờ DNS/socket/server thực.
- Một `ScheduledExecutorService`/`Executor` tự tạo bằng JDK.
- Một `Schedulers.newSingle("external")` được tạo trước lambda và truyền tường minh vào `delayElement(..., scheduler)`.
- SQL transaction, network timeout của HTTP client/JDBC hoặc external broker.
- Một hot source đã phát dữ liệu trước khi subscriber xuất hiện.
- Các side effects dùng đồng hồ thực `Instant.now()` hoặc `System.currentTimeMillis()` thay vì Clock được inject.

Vì thế bài học này nhắm tới **thời gian của Reactor pipeline**. Với HTTP endpoints thật, test virtual time thích hợp cho service/operator ở dưới; integration test về request/response có thể dùng mock HTTP server hoặc test container và thời gian thật ngắn. Đừng cố tua đồng hồ ảo rồi kết luận TLS, connection pool hoặc provider thực đã hết timeout.

### 4.1. Virtual time khác Java virtual threads

Hai thuật ngữ dễ nhầm:

- **Virtual time:** đồng hồ giả được test điều khiển, ví dụ `VirtualTimeScheduler`.
- **Java virtual threads:** cơ chế thực thi lightweight threads của JVM (Java 21+), không làm thời gian chờ tự biến mất.

Việc bật virtual threads trong một ứng dụng không tự giúp `Mono.delay(Duration.ofDays(1))` hoàn thành trong mili-giây khi test. Ngược lại, virtual scheduler không biến `Thread.sleep` thành việc tiến đồng hồ ảo.

## 5. Chuẩn bị dự án Spring Boot với Reactor Test

Ví dụ dưới đây dùng **Java 17, Maven, Spring Boot 3.5.0 và Reactor được quản lý phiên bản bởi Spring Boot BOM**. `reactor-test` được khai báo trực tiếp trong test scope để dùng `StepVerifier`; không trông chờ test starter tự cung cấp dependency ấy.

### 5.1. Cấu trúc tệp

```text
reactive-virtual-time/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/virtualtime/
    │       ├── VirtualTimeApplication.java
    │       ├── ReactiveTimingService.java
    │       └── TimingController.java
    └── test/
        └── java/com/example/virtualtime/
            ├── ReactiveTimingServiceTest.java
            └── TimingControllerTest.java
```

Mỗi public class được đặt trong file cùng tên, cùng package `com.example.virtualtime`. Project này không sử dụng database, external APIs hay secrets.

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-virtual-time</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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
```

- `spring-boot-starter-webflux` cung cấp Reactor Core, WebFlux và cơ chế xử lý reactive HTTP.
- `spring-boot-starter-test` cung cấp JUnit Jupiter/Mockito/Spring Test.
- `reactor-test` cung cấp `StepVerifier`, `TestPublisher`, `VirtualTimeScheduler` và các công cụ test reactive.
- Không tự ấn định phiên bản Reactor trong ví dụ: để dependency management của Spring Boot 3.5.0 chọn bộ thư viện tương thích.

Không cần `@SpringBootTest` để kiểm tra một reactive service thuần. Unit test dùng `new ReactiveTimingService()` sẽ đủ và tránh kích hoạt cả application context. Khi muốn kiểm tra HTTP controller wiring, dùng `@WebFluxTest` độc lập ở phần 8.

## 6. Mã production có delay, timeout và retry

### 6.1. Application entrypoint

```java
// src/main/java/com/example/virtualtime/VirtualTimeApplication.java
package com.example.virtualtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VirtualTimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(VirtualTimeApplication.class, args);
    }
}
```

### 6.2. `ReactiveTimingService.java`

```java
// src/main/java/com/example/virtualtime/ReactiveTimingService.java
package com.example.virtualtime;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class ReactiveTimingService {

    public Mono<String> delayedGreeting(Duration delay) {
        return Mono.just("ready").delayElement(delay);
    }

    public Flux<Long> ticks(Duration interval, long count) {
        return Flux.interval(interval).take(count);
    }

    public Mono<String> simulatedRemote(Duration latency) {
        return Mono.delay(latency).thenReturn("remote-ok");
    }

    public Mono<String> withTimeout(
            Duration latency, Duration limit) {
        return simulatedRemote(latency).timeout(limit);
    }

    public Mono<String> withFallback(
            Duration latency, Duration limit) {
        return withTimeout(latency, limit)
                .onErrorResume(TimeoutException.class,
                        ignored -> Mono.just("cached"));
    }

    public Mono<String> retryTransient(
            Supplier<Mono<String>> attempt) {
        return Mono.defer(attempt)
                .retryWhen(
                        Retry.fixedDelay(2, Duration.ofSeconds(10))
                                .filter(IllegalStateException.class::isInstance)
                                .jitter(0.0)
                                .onRetryExhaustedThrow(
                                        (spec, signal) -> signal.failure()));
    }
}
```

Các thiết kế có chủ đích:

- `delayedGreeting` trì hoãn một giá trị đã có.
- `ticks` dùng `Flux.interval`; phần tử đầu tiên là `0L` sau một `interval` đầy đủ, sau đó `1L`, `2L`…
- `simulatedRemote` giả lập remote call bằng **Reactor timer**, không thực hiện HTTP. Vì vậy nó **phù hợp với virtual time**.
- `withTimeout` thất bại với `TimeoutException` nếu remote giả lập chậm hơn `limit`.
- `withFallback` chỉ chuyển **timeout** thành `"cached"`. Các lỗi khác không bị nuốt bằng một `onErrorResume` quá rộng.
- `retryTransient` thử tối đa **2 lần retry sau lần đầu tiên**, khoảng cách cố định **10 giây ảo**. Chỉ retry khi nhận `IllegalStateException`; `IllegalArgumentException` không retry.
- `Retry.fixedDelay` tạo retry policy; `jitter(0.0)` biểu đạt rõ tính xác định của thời gian trong bài kiểm thử. Với `Retry.backoff`, jitter mặc định hoặc phép tính tăng dần cần được kiểm soát để có expected timeline.
- `onRetryExhaustedThrow((spec,signal) -> signal.failure())` trả lại lỗi gốc của lượt thất bại cuối khi hết budget, giúp test kỳ vọng `IllegalStateException` thay vì mặc định nhận wrapper báo retry exhausted. Đó là **policy của ví dụ**, không phải behavior mặc định của mọi `retryWhen`.
- `Mono.defer(attempt)` bảo đảm `Supplier` được gọi **mỗi lần upstream được subscribe**, điều kiện cần để ví dụ mô phỏng các lần thử lại khác nhau.

**Lưu ý về contract:** trong ứng dụng thật, không mặc định retry mọi `IllegalStateException`; exception nào transient, delay bao nhiêu, số retries bao nhiêu và idempotency thuộc thiết kế nghiệp vụ/operational policy. Đây là ví dụ huấn luyện về cơ chế.

### 6.3. Reactive HTTP controller để gắn service với Spring Boot

```java
// src/main/java/com/example/virtualtime/TimingController.java
package com.example.virtualtime;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class TimingController {
    private final ReactiveTimingService service;

    public TimingController(ReactiveTimingService service) {
        this.service = service;
    }

    @GetMapping(value = "/api/timing/ready",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ready() {
        return service.delayedGreeting(Duration.ofSeconds(1));
    }
}
```

Khi ứng dụng chạy bình thường, endpoint `/api/timing/ready` sẽ trả text `ready` **sau một giây thực** nếu hệ thống hoạt động bình thường. Chỉ unit test với virtual scheduler mới tua được giây đó; không phải cứ trả `Mono` thì WebFlux tự dùng virtual time.

## 7. Bài test hoàn chỉnh bằng `StepVerifier.withVirtualTime`

Tệp dưới đây có **8 phương thức `@Test`**. Nó chạy với JUnit Jupiter và Reactor Test, không tạo Spring context.

```java
// src/test/java/com/example/virtualtime/ReactiveTimingServiceTest.java
package com.example.virtualtime;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactiveTimingServiceTest {

    private final ReactiveTimingService service =
            new ReactiveTimingService();

    @Test
    void delayedValueDoesNotArriveEarly() {
        StepVerifier.withVirtualTime(
                        () -> service.delayedGreeting(
                                Duration.ofHours(6)))
                .expectSubscription()
                .expectNoEvent(Duration.ofHours(5))
                .thenAwait(Duration.ofHours(1))
                .expectNext("ready")
                .verifyComplete();
    }

    @Test
    void intervalEmitsThreeItemsAtTwoSecondCadence() {
        StepVerifier.withVirtualTime(
                        () -> service.ticks(
                                Duration.ofSeconds(2), 3))
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(1))
                .thenAwait(Duration.ofSeconds(1))
                .expectNext(0L)
                .thenAwait(Duration.ofSeconds(2))
                .expectNext(1L)
                .thenAwait(Duration.ofSeconds(2))
                .expectNext(2L)
                .verifyComplete();
    }

    @Test
    void slowRemoteFailsAtTimeoutBoundary() {
        StepVerifier.withVirtualTime(
                        () -> service.withTimeout(
                                Duration.ofSeconds(20),
                                Duration.ofSeconds(5)))
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(4))
                .thenAwait(Duration.ofSeconds(1))
                .expectError(TimeoutException.class)
                .verify();
    }

    @Test
    void fastRemoteFinishesBeforeTimeout() {
        StepVerifier.withVirtualTime(
                        () -> service.withTimeout(
                                Duration.ofSeconds(3),
                                Duration.ofSeconds(5)))
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(2))
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("remote-ok")
                .verifyComplete();
    }

    @Test
    void timeoutCanBecomeExplicitFallback() {
        StepVerifier.withVirtualTime(
                        () -> service.withFallback(
                                Duration.ofSeconds(20),
                                Duration.ofSeconds(5)))
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(4))
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("cached")
                .verifyComplete();
    }

    @Test
    void transientErrorsAreRetriedOnVirtualSchedule() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(
                        () -> service.retryTransient(() -> {
                            int n = attempts.incrementAndGet();
                            return n < 3
                                    ? Mono.error(new IllegalStateException(
                                            "temporary"))
                                    : Mono.just("recovered");
                        }))
                .expectSubscription()
                .then(() -> assertEquals(1, attempts.get()))
                .expectNoEvent(Duration.ofSeconds(9))
                .then(() -> assertEquals(1, attempts.get()))
                .thenAwait(Duration.ofSeconds(1))
                .then(() -> assertEquals(2, attempts.get()))
                .expectNoEvent(Duration.ofSeconds(9))
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("recovered")
                .verifyComplete();

        assertEquals(3, attempts.get());
    }

    @Test
    void nonTransientErrorIsNotRetried() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(
                        () -> service.retryTransient(() -> {
                            attempts.incrementAndGet();
                            return Mono.error(new IllegalArgumentException(
                                    "invalid-input"));
                        }))
                .expectSubscription()
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && "invalid-input".equals(error.getMessage()))
                .verify();

        assertEquals(1, attempts.get());
    }

    @Test
    void retryBudgetStopsAfterThirdTotalAttempt() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(
                        () -> service.retryTransient(() -> {
                            attempts.incrementAndGet();
                            return Mono.error(new IllegalStateException(
                                    "unavailable"));
                        }))
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(9))
                .thenAwait(Duration.ofSeconds(1))
                .expectNoEvent(Duration.ofSeconds(9))
                .thenAwait(Duration.ofSeconds(1))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "unavailable".equals(error.getMessage()))
                .verify();

        assertEquals(3, attempts.get());
    }
}
```

### 7.1. Đối chiếu từng timeline của các test

| Test | Đầu vào | Thời điểm ảo có ý nghĩa | Expected |
| --- | --- | --- | --- |
| `delayedValueDoesNotArriveEarly` | `delayElement(6h)` | Im lặng 0→5h; tiến thêm 1h | `onNext("ready")` rồi complete |
| `intervalEmitsThreeItemsAtTwoSecondCadence` | `interval(2s).take(3)` | 2s, 4s, 6s | `0L`, `1L`, `2L` rồi complete |
| `slowRemoteFailsAtTimeoutBoundary` | latency 20s, timeout 5s | Không tín hiệu đến 4s; 5s hết hạn | `TimeoutException` |
| `fastRemoteFinishesBeforeTimeout` | latency 3s, timeout 5s | 3s | `"remote-ok"` rồi complete |
| `timeoutCanBecomeExplicitFallback` | latency 20s, timeout 5s | 5s | `"cached"` rồi complete |
| `transientErrorsAreRetriedOnVirtualSchedule` | Hai lỗi, sau đó success | Gọi lần 1 tại 0s, lần 2 tại 10s, lần 3 tại 20s | `"recovered"`, tổng 3 attempts |
| `nonTransientErrorIsNotRetried` | `IllegalArgumentException` | Lỗi ngay ở lần đầu | Giữ nguyên lỗi, tổng 1 attempt |
| `retryBudgetStopsAfterThirdTotalAttempt` | Mọi lần đều lỗi transient | 0s, 10s, 20s | Báo lỗi sau 3 attempts |

Ở hai test retry, `AtomicInteger` đếm số lần **Supplier thực sự được gọi**, chứ không đếm số callback của riêng mock. Điều này chứng minh lần 2/3 chỉ xảy ra sau khi virtual clock tiến đúng khoảng chờ.

### 7.2. Vì sao không dùng `Thread.sleep` ở bất kỳ test nào?

Mọi delay của production code mẫu đều được biểu diễn qua **Reactor operators**. Nhờ `withVirtualTime`, từng khoảng 6 giờ/20 giây được mô phỏng. Test không cần đợi thời gian tương ứng.

Điều này không bảo đảm **zero wall-clock time**: class loading, Maven/Spring test bootstrap, JIT và hoạt động CPU vẫn tốn thời gian thật. Nhưng các delay theo `Duration` không còn ép CI phải ngủ lâu.

### 7.3. Kiểm tra “im lặng trước mốc” giúp phát hiện lỗi gì?

Nếu developer sửa `Duration.ofHours(6)` thành một thời gian ngắn hơn, test im lặng 5 giờ sẽ có thể fail vì `onNext` xuất hiện quá sớm. Nếu chỉ gọi `thenAwait(6h)` rồi `expectNext("ready")`, kết quả test có thể vẫn pass dù code đã phát tại giờ 2.

Tương tự, khi kiểm thử retry, nếu policy lỡ giảm delay từ 10 giây xuống 2 giây, `expectNoEvent(9s)` bắt được hành vi retry/phát kết quả quá sớm trong các trường hợp observable; cộng với assertion trên `attempts`, ta kiểm soát được **thời điểm nỗ lực retry** chứ không chỉ terminal result.

## 8. Test HTTP controller bằng `@WebFluxTest` không phải test virtual time

Để kiểm tra route/serialization riêng, ta dùng WebFlux slice test. Service được mock nên không có delay thật, và client test không cần virtual scheduler.

```java
// src/test/java/com/example/virtualtime/TimingControllerTest.java
package com.example.virtualtime;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(TimingController.class)
class TimingControllerTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    ReactiveTimingService service;

    @Test
    void endpointReturnsReactiveBodyFromService() {
        when(service.delayedGreeting(Duration.ofSeconds(1)))
                .thenReturn(Mono.just("ready"));

        client.get()
                .uri("/api/timing/ready")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("ready");

        verify(service).delayedGreeting(Duration.ofSeconds(1));
    }
}
```

**Test này xác nhận:** route `GET /api/timing/ready`, HTTP 200 và response body từ reactive publisher do service mock trả về. Nó **không kiểm chứng** đồng hồ 1 giây trong service thật, vì service đã được `@MockitoBean`.

**Test ở phần 7 xác nhận:** timing/retry/timeout logic thật của service, không nạp Spring web context.

**Nếu muốn kiểm tra HTTP server thật:** `@SpringBootTest(webEnvironment=RANDOM_PORT)` + `WebTestClient` hoặc HTTP client kết nối loopback, nhưng test đó phải kiểm soát duration và tài nguyên thật; không suy ra virtual time của một unit test đã kiểm chứng toàn bộ server/network pipeline.

### 8.1. Có thể gộp `@WebFluxTest` với `withVirtualTime` không?

Không nên tự động giả định một test client/controller dùng scheduler mà `StepVerifier.withVirtualTime` có thể điều khiển. HTTP binding, request subscription, scheduler của Netty, Reactor context và lifecycle có thể được tạo **trước** khi virtual scheduler được bật.

Nếu mục tiêu là **operator timer**, test service bằng Reactor Test trực tiếp. Nếu mục tiêu là **HTTP contract**, mock service để trả `Mono.just(...)` ngay hoặc dùng bounded, deterministic test fixtures. Khi thực sự cần test integration với time control, thiết kế injection của `Scheduler`/`Clock` và khởi tạo context trong vòng đời thích hợp, tránh thay shared global scheduler giữa các test chạy song song.

## 9. Timeout: phải hiểu vị trí operator và deadline

### 9.1. `timeout(Duration)` là khoảng chờ của upstream signal

Trong ví dụ:

```java
return simulatedRemote(Duration.ofSeconds(20))
        .timeout(Duration.ofSeconds(5));
```

Upstream không phát phần tử trong 5 giây ảo. `timeout` phát `TimeoutException` ở downstream và hủy subscription của nguồn không phản hồi. **Nó không có nghĩa remote call thật đã bị hủy ở tầng network** nếu bạn dùng một client không tôn trọng cancellation.

Với `Flux`, `timeout(Duration)` thường đo khoảng cách giữa các tín hiệu, không mặc định là tổng deadline cho cả stream. Nếu một `Flux.interval(2s)` liên tục phát item trước deadline `5s`, mỗi lần có item có thể làm reset đồng hồ chờ tín hiệu tiếp theo. Nếu yêu cầu tổng wall-clock budget 5 giây cho một workflow, cần một policy khác (ví dụ race với timer tổng hoặc đặt timeout ở toàn chuỗi theo cách được thiết kế rõ).

### 9.2. Timeout và fallback có phải là success?

`onErrorResume(TimeoutException.class, ignored -> Mono.just("cached"))` biến một lỗi timeout thành **một output thành công thay thế**. Vậy test phải kiểm tra đúng ý nghĩa business:

- Có fallback **chỉ khi** TimeoutException, không nuốt mọi exception.
- Fallback không phải bằng chứng upstream đã thành công.
- Nếu consumer cần biết dữ liệu stale/cached, contract nên đưa metadata vào response, không chỉ string giống dữ liệu live.
- Trong case timeout, có thể phải đo cancellation, metrics, circuit breaker behavior hoặc phân biệt timeout với permanent failure.

Đừng viết test chỉ `expectNextCount(1).verifyComplete()` cho fallback: một giá trị sai vẫn có thể pass. Hãy assert `expectNext("cached")` và các side effect quan trọng.

### 9.3. Timeout trước retry hay retry trước timeout?

Hai biểu thức khác nhau về bản chất:

```java
// MẪU A: timeout áp dụng riêng từng attempt.
Mono<String> a = source.timeout(Duration.ofSeconds(3))
        .retryWhen(retrySpec);

// MẪU B: timeout áp dụng cho toàn bộ chuỗi sau retry.
Mono<String> b = source.retryWhen(retrySpec)
        .timeout(Duration.ofSeconds(3));
```

**Đây là hai đoạn minh họa**: `source` và `retrySpec` là các biến giả định, không phải class chạy độc lập của phần 6.

- A: một attempt vượt 3 giây → timeout error → retry policy **có thể** retry nếu filter cho phép TimeoutException. Tổng thời gian tất cả attempts và backoffs có thể dài hơn 3 giây.
- B: deadline 3 giây bao cả attempt đầu, các lần retry và khoảng chờ backoff trong phạm vi downstream subscription; khi hết hạn, toàn workflow lỗi, có thể hủy retry đang chờ.
- Nếu retry filter chỉ cho `IllegalStateException` như project mẫu, `TimeoutException` ở A sẽ **không** được retry.

Hãy viết test cho **vị trí operator cụ thể** bạn chọn. Đừng coi `timeout` là network timeout của HTTP client: connect timeout, response timeout, TCP retry và Reactor signal timeout là các cơ chế khác nhau.

### 9.4. Cẩn trọng với chính mốc bằng nhau

Khi event và timeout đều được lên lịch đúng `t=5s`, thứ tự xử lý cùng thời điểm có thể ảnh hưởng kết quả trong một số pipeline. Vì vậy test nên chọn case rõ:

- Fast: latency **3s**, timeout **5s** → phải success.
- Slow: latency **20s**, timeout **5s** → phải TimeoutException.
- Trường hợp biên latency **5s** và timeout **5s** phải được quyết định theo contract và semantics scheduler cụ thể trước khi assert.

Đừng dùng các test biên mơ hồ để suy luận rằng một implementation sai, nhất là khi cả hai tín hiệu được schedule cùng timestamp.

## 10. Retry: thời gian, số lần và loại lỗi

### 10.1. `retry(2)` và `retryWhen(Retry.fixedDelay(2,...))`

`retry(2)` cho phép resubscribe tối đa hai lần khi lỗi, thông thường không áp đặt delay giữa các retries. `Retry.fixedDelay(2, Duration.ofSeconds(10))` thêm delay 10 giây giữa các lượt thử lại và có thể filter loại lỗi.

**Không nhầm `maxRetries=2` với tổng số lần call là 2.**

```text
t = 0s       attempt #1  → IllegalStateException
t = 10s      attempt #2  → IllegalStateException
t = 20s      attempt #3  → "recovered"  → onComplete

Số lần gọi = 1 lần ban đầu + 2 lần retry = 3.
Số khoảng chờ backoff đã trải qua = 2.
```

Nếu retry không bao giờ thành công và hết budget, production code mẫu dùng `onRetryExhaustedThrow` để phát lại chính lỗi cuối. Không có custom policy này, Reactor có thể phát một lỗi wrapper “retry exhausted” và root cause là failure trước đó. Khi test thay policy, hãy update expected error đúng kiểu.

### 10.2. Tại sao `Mono.defer` quan trọng?

Sai:

```java
int n = attempts.incrementAndGet();
Mono<String> source = n < 3
        ? Mono.error(new IllegalStateException("unavailable"))
        : Mono.just("ok");

return source.retryWhen(Retry.fixedDelay(
        2, Duration.ofSeconds(10)));
```

Đây là anti-pattern minh họa: `n` chỉ được tăng **một lần khi assembly**. `retryWhen` resubscribe vào **cùng một publisher** lỗi, nhưng business attempt counter không được tính lại; source có thể cứ báo lỗi.

Đúng khi muốn tạo một nỗ lực mới mỗi lần subscribe:

```java
return Mono.defer(() -> {
    int n = attempts.incrementAndGet();
    return n < 3
            ? Mono.error(new IllegalStateException("temporary"))
            : Mono.just("ok");
}).retryWhen(Retry.fixedDelay(
        2, Duration.ofSeconds(10)));
```

Các đoạn này chỉ minh họa pattern; trong project chính `ReactiveTimingService#retryTransient` đã bọc `Supplier<Mono<String>>` bằng `Mono.defer(attempt)`.

**Lưu ý:** `retryWhen` là resubscription. Với hot publisher, message stream một chiều hoặc side effect đã xảy ra, resubscribe **không** đảm bảo làm lại được nghiệp vụ như một HTTP request mới. Phải hiểu cold/hot semantics, idempotency và repeatability.

### 10.3. Lọc lỗi và tránh retry vô điều kiện

Với user input validation:

- `IllegalArgumentException` là lỗi vĩnh viễn trong ví dụ; thử lại không đổi được input nên không có lợi.
- `IllegalStateException` được dùng như transient marker **chỉ cho mục đích giảng dạy**; trong production nên định nghĩa exception domain phù hợp (ví dụ `TransientGatewayException`).
- `TimeoutException` có thể hoặc không nên retry tùy SLA, tính idempotent của request, side effects và tổng deadline.
- HTTP 429/503 không mặc nhiên an toàn để retry với mọi method, đặc biệt POST payment nếu thiếu idempotency key.

Test `nonTransientErrorIsNotRetried` kiểm tra **chỉ 1 attempt**; test `retryBudgetStopsAfterThirdTotalAttempt` kiểm tra fail **sau đúng 3 attempts**. Cả hai giúp bắt lỗi policy ngoài việc kiểm tra output.

### 10.4. `Retry.backoff` và jitter

`Retry.backoff(maxRetries, initialDelay)` thường tăng delay theo chiến lược backoff và có hỗ trợ jitter để giảm retry storm. Điều này hữu ích ở production nhưng làm timeline khó dự đoán nếu test assert mỗi giây chính xác. Khi cần test **trình tự thời gian xác định**:

- Dùng `Retry.fixedDelay` cho trường hợp hợp đồng delay cố định.
- Với `Retry.backoff`, kiểm soát jitter bằng `jitter(0.0)` hoặc assert theo cửa sổ/hợp đồng phù hợp, thay vì khẳng định một chuỗi ngẫu nhiên cố định.
- Test “đúng 2 retries” tách biệt với test “delay/backoff policy” khi cần.
- Nếu dùng retry policy có maxBackoff, pre-retry hooks hoặc retry filter, đưa các điều kiện ấy vào expected.

**Không set jitter = 0 trong production chỉ để test pass** nếu cần jitter chống tải cao. Cấu hình retry nên có thể test với fake policy/scheduler và giữ policy production đã được thiết kế.

## 11. Làm thế nào để test cancellation khi timeout?

Sau `timeout`, upstream subscription bị hủy. Nếu bạn muốn chứng minh service không tiếp tục chờ/giữ subscription, có thể dùng `doOnCancel` hoặc `doFinally` theo đúng vị trí operator.

Ví dụ method test **có thể thêm** vào class `ReactiveTimingServiceTest` ở phần 7 (phải import `AtomicBoolean` và `assertTrue` nếu dùng code này):

```java
@Test
void timeoutCancelsSlowPublisher() {
    AtomicBoolean cancelled = new AtomicBoolean();

    StepVerifier.withVirtualTime(() ->
                    Mono.delay(Duration.ofSeconds(30))
                            .doOnCancel(
                                    () -> cancelled.set(true))
                            .thenReturn("never")
                            .timeout(Duration.ofSeconds(5)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(5))
            .expectError(TimeoutException.class)
            .verify();

    assertTrue(cancelled.get());
}
```

**Giới hạn:** cancellation được quan sát ở Reactor subscription, không chứng minh một HTTP request đã ngừng chạy trên remote server. Nếu có side effect không hủy được, cần thêm idempotency/circuit breaker, resource cleanup hoặc integration test.

Với `doFinally`, signal type `CANCEL` có thể xuất hiện ở vị trí khác nhau tùy chỗ đặt operator. Đừng viết assert về callback của operator downstream rồi suy đoán nó là cancellation của upstream. Đặt hook ở ngay publisher bạn muốn quan sát.

## 12. Dùng `VirtualTimeScheduler` trực tiếp khi cần kiểm soát clock

`StepVerifier.withVirtualTime` thường là lựa chọn đơn giản nhất vì tự thiết lập virtual scheduler theo test scenario. Khi cần kiểm tra một scheduler cụ thể, Reactor Test còn cung cấp `VirtualTimeScheduler`.

Ví dụ **độc lập với test project ở phần 7**:

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.test.scheduler.VirtualTimeScheduler;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ManualVirtualClockTest {

    @Test
    void runsScheduledTaskWithoutWaitingForWallClock() {
        VirtualTimeScheduler clock = VirtualTimeScheduler.create();
        AtomicInteger executed = new AtomicInteger();

        clock.schedule(
                executed::incrementAndGet,
                30,
                java.util.concurrent.TimeUnit.SECONDS);

        assertEquals(0, executed.get());

        clock.advanceTimeBy(Duration.ofSeconds(29));
        assertEquals(0, executed.get());

        clock.advanceTimeBy(Duration.ofSeconds(1));
        assertEquals(1, executed.get());

        clock.dispose();
    }
}
```

Đây là **một class test bổ sung**, không nằm trong cây tệp ở phần 5 trừ khi bạn tạo thêm `ManualVirtualClockTest.java`. Nó chứng minh scheduler ảo lên lịch tác vụ, không phải Reactor `Mono`/`Flux` tự động nhận clock này.

**Phân biệt quan trọng:** tạo `VirtualTimeScheduler.create()` **không tự động** làm mọi `Schedulers.parallel()` của ứng dụng sử dụng scheduler đó. Để operator dùng clock trực tiếp, inject truyền scheduler phù hợp; hoặc dùng `withVirtualTime`, cơ chế Test hỗ trợ thay các factories mặc định. Nếu tự cài global factory hoặc `VirtualTimeScheduler.getOrSet()`, phải hiểu cleanup/reset và ảnh hưởng tới test khác.

### 12.1. Inject scheduler có lợi khi nào?

Giả sử production class nhận một `Scheduler` qua constructor:

```java
public final class DelayedCommand {
    private final Scheduler scheduler;

    public DelayedCommand(Scheduler scheduler) {
        this.scheduler = scheduler;
    }

    public Mono<String> run() {
        return Mono.delay(
                Duration.ofMinutes(10), scheduler)
                .thenReturn("done");
    }
}
```

Đây là **snippet minh họa** cần imports `Scheduler`, `Mono` và `Duration`. Test có thể tạo `VirtualTimeScheduler clock = VirtualTimeScheduler.create()`, inject nó và kiểm tra stream qua `StepVerifier.create` kết hợp `clock.advanceTimeBy` ở đúng vòng đời. Thiết kế đó giúp tránh phụ thuộc vào global scheduler factory khi ứng dụng đã có scheduler riêng.

Đừng tự ý mix một scheduler inject với `StepVerifier.withVirtualTime` rồi mặc định cả hai là cùng một clock. Nếu operator dùng scheduler riêng, test phải advance **chính scheduler ấy**.

## 13. Phân biệt `verify()` và thời hạn thực của test

Nhiều test bị treo do quên advance virtual clock. Khi đó `verifyComplete()` có thể đợi terminal signal không bao giờ đến. Có thể sử dụng watchdog bằng:

```java
StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                        .thenReturn("ok"))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(10))
        .expectNext("ok")
        .expectComplete()
        .verify(Duration.ofSeconds(5));
```

Ở đây:

- `thenAwait(10s)` tiến **10 giây ảo**.
- `verify(Duration.ofSeconds(5))` đặt **giới hạn thời gian thực** để verification không treo quá lâu.
- `verify()`/`verifyComplete()` kích hoạt test; chỉ xây builder mà không gọi verify chưa chứng minh điều gì.
- Kết quả `verify()` là `Duration` thời gian thực đã dùng để thực hiện verification, không phải số giây ảo mà pipeline đã trải qua.

**Không đặt watchdog thấp đến mức Maven/CI dưới tải cao bị fail tùy tiện.** Nó là cơ chế phát hiện test bị treo, không phải phép assert business deadline.

Nếu code dùng `StepVerifier.setDefaultTimeout(...)`, đây là cấu hình có phạm vi ảnh hưởng nhiều verifiers và cần reset sau test. Để giảm rủi ro tương tác giữa tests, ưu tiên `verify(Duration)` cục bộ cho scenario khi có thể.

## 14. Các lỗi phổ biến khiến virtual time “không hoạt động”

### Lỗi 1: Publisher đã được tạo trước `withVirtualTime`

**Triệu chứng:** Test chạy theo thời gian thật, không phát hoặc treo.  
**Nguyên nhân:** Timed publisher/operator đã chốt scheduler trước khi virtual scheduler được kích hoạt.  
**Khắc phục:** Tạo toàn bộ pipeline trong `Supplier`; nếu bean tạo và lưu publisher ở constructor, refactor để tạo lúc method được gọi/subscribe hoặc inject scheduler.

### Lỗi 2: `expectNoEvent` là bước đầu tiên

**Triệu chứng:** Assertion fail ngay khi subscribe.  
**Nguyên nhân:** Subscription là một event.  
**Khắc phục:** `expectSubscription().expectNoEvent(...)`.

### Lỗi 3: `expectNext` đến trước khi advance time

**Triệu chứng:** Test chờ mãi một phần tử có scheduler được đặt ở tương lai.  
**Nguyên nhân:** Virtual clock đang ở `t=0`, phần tử nằm ở `t=10s`.  
**Khắc phục:** `thenAwait(Duration.ofSeconds(10))` hoặc `expectNoEvent` phù hợp trước khi đòi next signal.

### Lỗi 4: Dùng `Thread.sleep` hoặc blocking I/O

**Triệu chứng:** Test vẫn mất nhiều giây hoặc timeout trên CI.  
**Nguyên nhân:** Đây là wall-clock/blocking operations, không phải Reactor-timed scheduling.  
**Khắc phục:** Thay upstream bằng deterministic fake Mono/Flux hoặc dùng injected Clock/Scheduler; giữ network integration test riêng.

### Lỗi 5: Retry không thay đổi kết quả giữa các subscriptions

**Triệu chứng:** Đã retry 2 lần nhưng luôn cùng một lỗi; attempt counter không tăng.  
**Nguyên nhân:** Counter/request được thực hiện khi assembly, không trong `Mono.defer`.  
**Khắc phục:** Đưa nỗ lực vào `Supplier` được gọi mỗi subscription. Với HTTP operations thật, xác định cả tính idempotent.

### Lỗi 6: Đếm sai số lần retry

**Triệu chứng:** Test nghĩ `Retry.fixedDelay(2,...)` chỉ gọi upstream 2 lần.  
**Nguyên nhân:** Tham số 2 là số lần **retry**, ngoài lần đầu.  
**Khắc phục:** Assert tổng **3 attempts** và hai khoảng chờ tương ứng khi source tiếp tục lỗi.

### Lỗi 7: Scheduler khác không nằm dưới clock ảo

**Triệu chứng:** `thenAwait` không làm task chạy.  
**Nguyên nhân:** Operator sử dụng scheduler đã tạo trước lambda hoặc scheduler custom.  
**Khắc phục:** Tạo publisher lazily, inject/test scheduler đúng instance, tránh tự tạo `Schedulers.newSingle` ngoài test.

### Lỗi 8: Jitter làm expected timeline không xác định

**Triệu chứng:** Test retry pass một lần, fail lần khác khi dùng `Retry.backoff`.  
**Nguyên nhân:** Retry delay biến thiên vì jitter/policy.  
**Khắc phục:** Tách thử policy deterministic với `jitter(0)` khi phù hợp; hoặc assert theo range và policy thực, không cấm jitter ở production chỉ để test xanh.

### Lỗi 9: Sử dụng publisher hot trong test retry

**Triệu chứng:** Retry không re-run tác vụ, mất signals hoặc nhận kết quả phụ thuộc lúc subscribe.  
**Nguyên nhân:** Hot source chia sẻ tín hiệu và không tái phát theo từng subscription.  
**Khắc phục:** Dùng cold publisher/`Mono.defer` cho hành vi mỗi attempt; nếu cần hot stream, test đúng semantics subscription/multicast của nó.

### Lỗi 10: Test virtual time chạy song song với test thay schedulers khác

**Triệu chứng:** Flaky do scheduler state dùng chung.  
**Nguyên nhân:** `withVirtualTime` thao tác scheduler factories/shared state theo cơ chế Reactor Test.  
**Khắc phục:** Không trộn nhiều test thay scheduler global song song nếu chưa kiểm soát; dùng injected `Scheduler` để cô lập tốt hơn, tránh tạo static publisher dùng timer trong test class, reset custom hooks sau test.

### Lỗi 11: Test chỉ kiểm tra kết quả cuối mà bỏ qua deadline

**Triệu chứng:** Test xanh dù response đến quá sớm hoặc retry quá nhanh.  
**Nguyên nhân:** Chỉ `thenAwait` và `expectNext`; không kiểm tra quãng im lặng/attempt count.  
**Khắc phục:** Kết hợp `expectNoEvent`, `AtomicInteger` và các mốc trước/sau deadline.

### Lỗi 12: Dùng WebTestClient như thể nó tự tua thời gian

**Triệu chứng:** WebFlux slice/full integration test vẫn chờ thật.  
**Nguyên nhân:** `WebTestClient` là HTTP test client, không đồng nghĩa `VirtualTimeScheduler`.  
**Khắc phục:** Kiểm tra timed operator ở service với `StepVerifier.withVirtualTime`; kiểm tra HTTP mapping riêng với stub/response ngay.

### Lỗi 13: Nhầm timeout operator với HTTP connection timeout

**Triệu chứng:** Unit test timeout pass nhưng production socket vẫn treo.  
**Nguyên nhân:** Reactive signal timeout không nhất thiết điều khiển connect/read timeout của HTTP transport hoặc remote side effect.  
**Khắc phục:** Tách config của HTTP client/broker, quan sát cancellation và kiểm thử network timeout ở integration/staging.

### Lỗi 14: Quên terminal assertion

**Triệu chứng:** Chỉ kiểm tra có `onNext` nhưng không biết stream có complete hay lỗi sau đó.  
**Nguyên nhân:** Không kiểm tra terminal signal.  
**Khắc phục:** `verifyComplete`, `expectError(...).verify()` hoặc `thenCancel().verify()` tùy contract.

## 15. Kiểm thử nâng cao: yêu cầu dữ liệu và sự đồng bộ của clock

### 15.1. Backpressure với `Flux.interval`

`Flux.interval` phát theo clock. Nếu subscriber không request đủ demand cho tick tiếp theo, có thể gặp backpressure-related error hoặc behavior khác với điều test tưởng tượng. `StepVerifier.withVirtualTime(() -> publisher)` overload mặc định request unbounded, giúp các ví dụ ở phần 7 tập trung vào thời gian.

Nếu thật sự muốn test request(n)/backpressure, dùng overload `withVirtualTime(supplier, initialRequest)` hoặc `StepVerifierOptions`, rồi gọi `thenRequest(n)` ở đúng mốc. Khi đó cần assert behavior khi tick đến nhưng demand bằng 0; đừng đoán từ test unbounded.

### 15.2. `flatMap` lồng timed publishers

Ví dụ:

```java
Flux.just("A", "B")
        .flatMap(value ->
                Mono.delay(Duration.ofSeconds(3))
                        .thenReturn(value));
```

Đây là snippet minh họa. Với `flatMap`, nội dung bên trong được tạo khi upstream phát phần tử; **nếu virtual clock đã được advance quá sớm trước khi inner publisher được tạo/subscribed**, timeline có thể khác kỳ vọng. Hãy xác định subscription/scheduling order, chia thời gian thành các bước và dùng `thenAwait`/`expectNoEvent` theo các mốc. Với `concatMap` các inner sources được xử lý tuần tự; deadline cũng khác.

**Quan trọng:** không suy luận “đã advance 3 giây tức mọi inner `Mono.delay(3s)` chắc xong”. Inner timers có thể bắt đầu sau mốc advance. Tạo pipeline lazily là cần nhưng chưa đủ; chính lúc inner stream subscribe cũng quan trọng.

### 15.3. `PublisherProbe` và `TestPublisher`

`reactor-test` còn có:

- **`PublisherProbe`:** theo dõi một reactive publisher có được subscribed/requested/cancelled hay không, hữu ích khi kiểm tra nhánh fallback hoặc switchIfEmpty.
- **`TestPublisher`:** chủ động phát `onNext`, `onComplete`, `onError` để kiểm tra operator/downstream behavior.

Hai công cụ này không thay thế virtual clock. Chúng cho phép điều khiển **signals** trong khi `VirtualTimeScheduler` điều khiển **thời gian lên lịch**. Một bài test phức tạp có thể kết hợp cả hai, nhưng cần tránh race do tạo và phát signal ngoài vùng kiểm soát.

### 15.4. Retry của side effect có cần test idempotency?

Có. `retryWhen` có thể thực hiện lại network request hoặc write operation khi gặp lỗi. Nếu response lỗi xuất hiện **sau khi remote side effect đã thành công**, việc retry không cẩn thận có thể tạo duplicate order/charge/message. Virtual time chỉ chứng minh retry schedule/budget; nó không chứng minh side effect idempotent.

Với payment/order, cần idempotency key, duplicate detection, transactional semantics và integration test ở boundary thật. Đừng dùng phép test thời gian ảo để kết luận một retry policy đã an toàn cho production.

## 16. Bài tập vận dụng

### Bài 1: Chặn phát trước mốc 24 giờ

Viết `Mono.delay(Duration.ofDays(1)).thenReturn("expired")`. Test bằng `withVirtualTime`:

- Sau subscribe, không có next trong 23 giờ.
- Advance thêm một giờ.
- Phát chính xác `"expired"` rồi complete.

**Gợi ý:** `expectSubscription().expectNoEvent(Duration.ofHours(23)).thenAwait(Duration.ofHours(1))...`.

### Bài 2: Timeout tổng khác timeout mỗi attempt

Giả lập một nguồn luôn chậm 4 giây, retry tối đa hai lần. Thử hai cách đặt `timeout(3s)` trước và sau retry. Viết expected cho từng trường hợp với retry filter cho phép TimeoutException, đồng thời dùng virtual time quan sát số lần resubscribe.

**Tiêu chí:** kết luận tổng deadline 3 giây không giống deadline 3 giây **cho từng attempt** cộng backoffs.

### Bài 3: Lỗi business không được retry

Viết nguồn trả `Mono.error(new IllegalArgumentException("bad"))`. Kiểm tra:

- `expectError(IllegalArgumentException.class)`.
- Attempt count bằng 1.
- Không có delay/backoff trước terminal error.

**Gợi ý:** dùng `AtomicInteger` trong `Supplier`, không increment trước khi tạo pipeline.

### Bài 4: Hai lỗi transient rồi thành công

Viết policy `Retry.fixedDelay(2, 10s)` và Supplier lần 1/2 lỗi, lần 3 trả `"ok"`. Test:

- Attempt 1 ở `t=0`.
- Trước `t=10s` không có retry.
- Attempt 2 ở `t=10s`.
- Attempt 3 ở `t=20s`.
- Next `"ok"` và complete.

**Đáp án tham khảo:** phương thức `transientErrorsAreRetriedOnVirtualSchedule` ở phần 7.

### Bài 5: Publisher tạo sớm

Viết một test cố ý tạo `Mono.delay(1h)` trước `withVirtualTime` và quan sát vì sao không nên phụ thuộc vào behavior đó. Sửa bằng cách chuyển publisher construction vào lambda; thêm watchdog thực để test không treo.

**Lưu ý:** Đây là bài tập nhận diện anti-pattern. Đừng để bản test “sai có chủ đích” chạy không giới hạn trong CI chính.

## 17. Checklist trước khi review một reactive timing test

- [ ] Có dùng `reactor-test` và `StepVerifier.withVirtualTime` cho operator thời gian phù hợp.
- [ ] Publisher và timed operators được **tạo trong Supplier** truyền cho verifier.
- [ ] Không giữ static/cached publisher đã tạo scheduler trước khi virtual time được bật.
- [ ] Có `expectSubscription` trước `expectNoEvent`.
- [ ] Dùng `expectNoEvent` khi hợp đồng cấm tín hiệu đến sớm.
- [ ] Dùng `thenAwait` ở thời điểm muốn clock tiến để operator phát signal.
- [ ] Có assert chính xác value/error/complete; không chỉ `expectNextCount` hoặc count retries.
- [ ] Phân biệt `verify(Duration)` real-time watchdog với virtual delays.
- [ ] Retry test đếm **attempt đầu + retries**, không hiểu sai maxRetries.
- [ ] Có test loại lỗi **không được retry** và nhánh retry exhausted.
- [ ] Backoff jitter/time windows được kiểm soát khi cần timeline xác định.
- [ ] Không cho test virtual time thực hiện production network/database/side effect.
- [ ] Không kỳ vọng virtual time tăng tốc `Thread.sleep` hoặc network I/O.
- [ ] Với hot/async/flatMap sources, đã xét thời điểm subscribe và scheduler thực.
- [ ] Không làm scheduler factory global bị ảnh hưởng khi chạy tests parallel.
- [ ] Chọn Reactor unit test để kiểm tra timer; WebFlux slice/integration test để kiểm tra HTTP contract.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `withVirtualTime` yêu cầu `Supplier<Publisher<?>>` thay vì chỉ một publisher tạo sẵn?

**Trả lời:** Nó cần thiết lập virtual scheduler trước khi timed operators được tạo; tạo trước có nguy cơ giữ scheduler thật và virtual time không còn kiểm soát được.

**Câu 2.** `expectNoEvent(5s)` khác gì `thenAwait(5s)`?

**Trả lời:** Cả hai tiến clock trong virtual test; `expectNoEvent` còn fail nếu có bất kỳ event nào xuất hiện trong quãng đó, còn `thenAwait` không assert sự im lặng.

**Câu 3.** Vì sao cần `expectSubscription()` trước `expectNoEvent`?

**Trả lời:** `onSubscribe` là một event; nếu mong không có sự kiện ngay từ đầu, test có thể fail vì subscription hợp lệ.

**Câu 4.** `Retry.fixedDelay(2, Duration.ofSeconds(10))` có bao nhiêu attempts tối đa?

**Trả lời:** Tối đa **3**: một lần đầu và hai lần retry, ở các mốc 0s, 10s và 20s nếu liên tục lỗi transient và không có jitter/độ trễ phụ.

**Câu 5.** `timeout(5s)` có nghĩa HTTP connect timeout của Netty tự thành 5s không?

**Trả lời:** Không. Đó là timeout cho tín hiệu của reactive publisher; network connect/read timeout và xử lý remote cần cấu hình/test riêng.

**Câu 6.** Với `Mono.delay(30s)` và `timeout(5s)`, test mong lỗi gì?

**Trả lời:** Thường là `TimeoutException` tại virtual `t=5s`, sau khi timeout hủy subscription upstream; nếu có `onErrorResume` có thể đổi thành fallback theo policy.

**Câu 7.** Tại sao retry test nên dùng `Mono.defer` hoặc Supplier tạo attempt mỗi lần subscribe?

**Trả lời:** `retryWhen` thực hiện resubscribe; nếu logic sinh attempt/counter nằm ở assembly, nó có thể chỉ chạy một lần nên không phản ánh retry thực.

**Câu 8.** Virtual time có tăng tốc `Thread.sleep(10000)` trong `Mono.fromCallable` không?

**Trả lời:** Không. `Thread.sleep` chờ wall-clock time; cần fake hoặc refactor sang Reactor timer/injected scheduler để kiểm thử deterministic.

**Câu 9.** `@WebFluxTest` + `WebTestClient` pass có chứng minh service delay 6 giờ đã được test không?

**Trả lời:** Không nếu service được mock hoặc client chạy bằng scheduler thật. Test operator time riêng với `StepVerifier.withVirtualTime`; WebFlux test chủ yếu kiểm tra routing/HTTP mapping.

**Câu 10.** Nếu source phát thành công đúng thời điểm timeout deadline, test nên làm gì?

**Trả lời:** Xác định semantics của policy và scheduler; ưu tiên các case fast/slow rõ ràng rồi bổ sung boundary test khi có yêu cầu, không kết luận từ thứ tự giả định của các scheduled tasks cùng timestamp.

## 19. Tài liệu chính thức

- [Project Reactor – Testing Reactor Code / Manipulating Time](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, lazy Supplier và expectations.
- [Project Reactor – StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): các overload `withVirtualTime`, `thenAwait`, `expectNoEvent`, `verify`.
- [Project Reactor – VirtualTimeScheduler API](https://projectreactor.io/docs/test/release/api/reactor/test/scheduler/VirtualTimeScheduler.html): tạo, tiến và quản lý virtual scheduler.
- [Project Reactor – Retry API](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html): `Retry.fixedDelay`, `Retry.backoff`, retry budget.
- [Project Reactor – RetryBackoffSpec API](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html): jitter, filter, exhaustion handling.
- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): test context, WebFlux slice và test dependencies.

**Điểm cần ghi nhớ:** Virtual time **không biến toàn bộ ứng dụng thành môi trường không có độ trễ**. Nó chỉ cho phép test **điều khiển clock của những Reactor operators dùng scheduler được thay**. Muốn test tốt cho `delay`, `timeout` và `retry`, hãy tạo publisher lazily, tiến thời gian có chủ ý, kiểm tra cả **không phát sớm**, **đúng terminal signal** và **đúng retry policy**.
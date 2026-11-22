# Giới hạn thời gian, hủy đăng ký và giải phóng tài nguyên trong thực thi reactive

## 1. Bài toán và mục tiêu

Trong ứng dụng Spring Boot sử dụng **Spring WebFlux**, HTTP request có thể chờ phản hồi `WebClient`, truy vấn database reactive, stream dữ liệu hoặc giữ kết nối SSE lâu dài. Khi một công việc kéo dài quá mức, client ngắt kết nối hoặc downstream chỉ cần một phần kết quả, ứng dụng phải biết **giới hạn thời gian**, **hủy phần việc không còn được cần** và **dọn tài nguyên**.

Ba khái niệm khác nhau:

- **Timeout:** giới hạn khoảng chờ theo một ngữ nghĩa cụ thể. `timeout(Duration)` của Reactor có thể phát `TimeoutException` khi không nhận được tín hiệu đúng hạn; có thể thay lỗi bằng fallback.
- **Cancellation:** downstream gọi `Subscription.cancel()` để báo với upstream rằng không muốn nhận dữ liệu nữa. Đây là tín hiệu điều khiển của Reactive Streams, **không phải** `onError` hoặc `onComplete`.
- **Cleanup:** giải phóng connection, stream, reactive transaction, subscription tới producer, pooled buffer hay các resource khác trong mọi đường kết thúc: thành công, lỗi và hủy.

Ví dụ chuỗi thường gặp: upstream xử lý quá chậm → operator `timeout` hủy upstream → downstream nhận `TimeoutException` → `onErrorResume` trả fallback → publisher ở ngoài có thể hoàn tất thành công. Cùng request nhưng **upstream ghi nhận cancel, downstream ghi nhận complete**. Nếu cleanup chỉ đặt ở nhánh lỗi, resource có thể bị rò rỉ.

Phạm vi bài: **Reactor (`Mono`/`Flux`) và Spring WebFlux** với Java 17+, Spring Boot 3.3.x / Reactor 3.6.x. Những mô tả về mạng, database và external systems luôn phụ thuộc khả năng hỗ trợ cancel của driver/transport.

## 2. Tín hiệu Reactive Streams và vị trí của cancellation

Pipeline khai báo không tự thực thi chỉ vì có dòng `Mono.just(...)` hoặc `webClient.get()...bodyToMono(...)`. Nó được thực thi khi có **subscription**. Spring WebFlux thường quản lý subscription của `Publisher` mà controller trả về để tạo HTTP response.

```text
Subscriber                                      Publisher / upstream
    │
    ├── subscribe() ─────────────────────────────►
    ◄── onSubscribe(Subscription) ────────────────┤
    ├── request(n) ──────────────────────────────►
    ◄── onNext(value) [0..n giá trị] ────────────┤
    ◄── onComplete() HOẶC onError(cause) ────────┤  (terminal)
    │
    └── HOẶC cancel() ───────────────────────────►  (hủy nhu cầu nhận tiếp)
```

Một publisher `Mono` phát tối đa một giá trị; `Flux` có thể phát nhiều giá trị theo nhu cầu `request(n)`. Hợp đồng Reactive Streams có hai đường tín hiệu kết thúc dữ liệu là `onComplete` và `onError`; `cancel` là yêu cầu từ subscriber đi ngược lên upstream, không phát ra một lỗi mới cho subscriber đã tự hủy.

| Sự kiện tại vị trí quan sát | Ngữ nghĩa | `SignalType` của `doFinally` |
|---|---|---|
| Publisher hoàn tất | `onComplete` (Mono có thể rỗng) | `ON_COMPLETE` |
| Publisher phát lỗi | `onError(Throwable)` | `ON_ERROR` |
| Downstream hủy subscription | Ngừng nhu cầu nhận thêm từ upstream | `CANCEL` |
| Timeout có fallback | Nguồn cũ thường bị cancel, fallback có thể complete | Upstream `CANCEL`; đoạn sau fallback `ON_COMPLETE` |

**Vị trí operator rất quan trọng:** `doFinally` đặt trước `timeout` quan sát sự kết thúc của source; đặt sau `onErrorResume` quan sát kết quả cuối cùng sau xử lý fallback. Hai hook có thể ghi các loại tín hiệu khác nhau mà không mâu thuẫn.

## 3. Giới hạn thời gian với `timeout`

### 3.1. Mono: thời gian chờ một giá trị

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;

Mono<String> slow = Mono.delay(Duration.ofSeconds(3))
        .map(ignored -> "finished");

Mono<String> limited = slow.timeout(Duration.ofMillis(250));
```

Đây là mảnh code đặt trong một phương thức Java có import phía trên, không phải class độc lập. Khi subscribe, `Mono.delay` phát giá trị sau khoảng ba giây, nhưng `timeout` chỉ đợi 250 ms. Vì không có kết quả đúng hạn, `limited` phát `java.util.concurrent.TimeoutException` và thông báo cancel đến nguồn chậm.

**`timeout(Duration)` không tự tạo HTTP 504.** Nó thay đổi tín hiệu reactive. HTTP status được quyết định ở tầng WebFlux/controller/exception handler hoặc proxy.

Có thể xử lý bằng `onErrorResume`:

```java
Mono<String> withFallback = limited.onErrorResume(
        TimeoutException.class,
        ex -> Mono.just("fallback")
);
```

Hoặc cung cấp fallback trực tiếp:

```java
Mono<String> directly = slow.timeout(
        Duration.ofMillis(250),
        Mono.just("fallback")
);
```

Trong cả hai trường hợp, `fallback` là giá trị trả về từ Publisher mới, không có nghĩa nguồn chậm tiếp tục được subscribe để hoàn thành phía sau. Fallback có thể lỗi, trễ hoặc bị cancel tiếp theo; cần thiết kế ngân sách phù hợp.

### 3.2. Flux: khoảng chờ giữa các phần tử

Với `Flux`, `timeout(Duration)` kiểm soát khoảng chờ đến **phần tử đầu** và **giữa các phần tử tiếp theo**. Nó **không phải** deadline tổng của toàn bộ stream.

```java
Flux<Long> regular = Flux.interval(Duration.ofMillis(100))
        .take(20)
        .timeout(Duration.ofMillis(500));
```

Mảnh code trên (cần import `Flux` và `Duration`) thường phát khoảng 20 phần tử trong gần hai giây mà không timeout, bởi khoảng cách giữa hai giá trị liên tục chỉ ~100 ms. Nếu stream ngừng gửi phần tử mới lâu hơn 500 ms, `Flux.timeout` mới phát lỗi (trừ trường hợp nguồn đã kết thúc).

Nếu mục tiêu là "stream chỉ tồn tại tối đa 2 giây", `take(Duration.ofSeconds(2))` có thể hoàn tất stream sau khoảng thời gian đó, nhưng nó **complete bình thường**, không báo lỗi timeout. Nếu mục tiêu là "phải hoàn tất toàn bộ danh sách trong 2 giây", có thể áp timeout cho một `Mono` đại diện việc thu thập/hoàn tất toàn bộ dữ liệu, ví dụ `flux.collectList().timeout(...)` với luồng **hữu hạn** và ngân sách bộ nhớ phù hợp. Không `collectList` một stream vô hạn chỉ để đặt deadline vì dễ gây tăng bộ nhớ.

### 3.3. Vị trí timeout trong luồng nhiều chặng

Giả sử nghiệp vụ gọi dịch vụ A rồi B:

```java
Mono<FinalResult> answer = callA()
        .flatMap(a -> callB(a))
        .timeout(Duration.ofSeconds(3));
```

Đây là sơ đồ cú pháp, trong app cần định nghĩa `FinalResult`, `callA`, `callB`. Timeout ở ngoài giới hạn thời gian publisher A→B hoàn tất, còn timeout riêng mỗi `callA`/`callB` áp dụng cho từng chặng. Hai chặng mỗi chặng cho phép 2 giây có thể tổng cộng chờ gần 4 giây nếu không có ngân sách chung.

Khi ghép `retryWhen`, thứ tự quyết định ngân sách:

- `source.timeout(1s).retryWhen(...)`: mỗi lần thử có thể được đặt lại đồng hồ 1 giây; tổng thời gian gồm nhiều attempt và backoff.
- `source.retryWhen(...).timeout(3s)`: có thêm giới hạn tổng cho Publisher bao quanh các attempt.

Thực thi retry phải giới hạn số lần, chọn backoff, nhận diện lỗi phù hợp và cân nhắc **idempotency**. Timeout/cancel không đảm bảo thao tác ghi dữ liệu ở remote service chưa được thực hiện.

### 3.4. Phân biệt timeout ở tầng mạng và ứng dụng

| Loại giới hạn | Phạm vi | Không đảm bảo |
|---|---|---|
| Reactor `Mono.timeout` | Thời gian chờ tín hiệu/kết thúc của Mono | Không tự áp lên công việc độc lập khỏi subscription |
| Reactor `Flux.timeout` | Khoảng giữa các phần tử | Không là deadline tổng của stream |
| Reactor Netty TCP connect timeout | Thời gian thiết lập kết nối mạng | Không giới hạn toàn bộ thời gian xử lý business |
| Reactor Netty response timeout | Điều kiện chờ đọc response HTTP client | Không thay thế deadline của nhiều chặng/retry |
| Proxy/gateway timeout | Quy tắc hạ tầng mạng | Không nhất thiết tạo `TimeoutException` trong pipeline |
| Business/request deadline | Ngân sách chung do ứng dụng thiết kế | Không tự hoàn tác side effect đã gửi ngoài tiến trình |

Nếu Spring Boot WebFlux trả response streaming đã gửi status và headers, lỗi timeout về sau **không thể luôn sửa response thành HTTP 504 mới**; khi đó có thể phải dừng stream/đóng kết nối hoặc dùng giao thức lỗi ở mức sự kiện.

## 4. Cancellation đến từ đâu?

Cancel xuất phát từ downstream, chẳng hạn:

1. `timeout` không nhận đủ tín hiệu trong thời gian cho phép.
2. Subscriber gọi `dispose()` trên `Disposable` trả về từ `subscribe()`, hoặc gọi `Subscription.cancel()`.
3. Operator chỉ cần một phần dữ liệu như `take(1)`, `next()`, hay `switchMap` chuyển sang nguồn mới.
4. Server/framework phát hiện HTTP client ngắt kết nối và hủy phần subscription liên quan (mức độ, thời điểm tùy transport và pipeline).
5. Một nhánh xử lý đã đủ kết quả và hủy publisher không còn cần thiết.

```text
Producer nguồn ──► operator A ──► operator B ──► HTTP subscriber
                    ▲               ▲               │
                    └── cancel ◄────┴── cancel ◄────┘
```

Cancel là **yêu cầu ngừng tiếp nhận/tiếp tục công việc**, không phải phép "kill thread" bắt buộc. Timer reactive (`Mono.delay`) hoặc driver non-blocking thường có khả năng hủy nhanh. Ngược lại, JDBC đồng bộ, `Thread.sleep`, native call hoặc API bên ngoài có thể tiếp tục chạy dù downstream không còn chờ. Dữ liệu có thể đã ghi xuống database hay được phát tới message broker trước khi cancel tới nơi.

Vì thế **timeout không mặc nhiên rollback transaction hoặc ngăn side effect**. Với thao tác ghi dữ liệu, cần transaction đúng ranh giới, idempotency key, retry có kiểm soát hoặc cơ chế bù trừ theo nghiệp vụ.

**Đối với controller WebFlux, hãy trả lại Publisher.** Framework subscribe để ghi HTTP response và có cơ hội quản lý cancel. Đừng tùy tiện gọi `subscribe()` rồi trả response khác; thao tác tự subscribe trở thành công việc tách khỏi lifecycle request.

## 5. Cleanup trên complete, error và cancel

| API Reactor | Thời điểm/đặc điểm | Khi nên dùng |
|---|---|---|
| `doOnCancel(Runnable)` | Nhận cancel tại vị trí operator; không gọi trên complete/error bình thường | Log/metric cancel, hành động nhẹ khi bị hủy |
| `doFinally(Consumer<SignalType>)` | Sau complete, error **hoặc cancel**; cho biết loại tín hiệu | Thống kê độ trễ, metric, cleanup side effect ngắn |
| `Mono.using` / `Flux.using` | Tạo resource theo **mỗi subscription**, dùng trong một scope, cleanup khi kết thúc/hủy | Resource đóng đồng bộ (`AutoCloseable`/handle) |
| `Mono.usingWhen` / `Flux.usingWhen` | Acquire và cleanup bằng Publisher, hỗ trợ cleanup bất đồng bộ | Reactive connection, transaction, lease |
| `doOnDiscard(Class, Consumer)` | Operator có hỗ trợ discard sẽ chuyển phần tử bị loại bỏ | Dọn pooled buffer/resource trong queue/prefetch |
| `FluxSink.onCancel`, `onDispose` | Callback tại producer do `Flux.create` làm adapter | Tháo đăng ký callback/socket/producer |

Vài phân biệt quan trọng:

- `doOnTerminate` hoặc `doAfterTerminate` phản ứng với complete/error, **không thay thế `doFinally` cho cancellation**.
- `doFinally(signal -> closeAsync())` chỉ tạo `Mono<Void>` nếu `closeAsync()` trả Publisher; nó **không tự subscribe và chờ cleanup**. Dùng `usingWhen` hoặc lifecycle framework khi cleanup phải bất đồng bộ.
- `doOnCancel` không chạy trên complete/error, vì vậy không nên là cơ chế đóng resource duy nhất.
- `doOnDiscard` chỉ được operator hỗ trợ sử dụng và phải đặt ở vị trí đúng; cleanup nên có tính idempotent/safe theo contract của resource.
- Không release hai lần một `DataBuffer` hoặc đóng resource mà framework/driver vẫn sở hữu.

## 6. Ví dụ Spring Boot WebFlux chạy được (Java 17+)

Ví dụ sử dụng Reactor timer để tạo nguồn chậm mà **không block event loop**, và một lease giả để quan sát việc đóng resource. Nó không cần database hay dịch vụ HTTP ngoài.

Cấu trúc project:

```text
reactive-timeout-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/reactivecleanup/ReactiveTimeoutApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/reactivecleanup/CancellationTest.java
```

**`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`**:

```properties
server.port=8080
```

**`src/main/java/com/example/reactivecleanup/ReactiveTimeoutApplication.java`**:

```java
package com.example.reactivecleanup;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@SpringBootApplication
public class ReactiveTimeoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveTimeoutApplication.class, args);
    }
}

@RestController
@RequestMapping("/demo")
class DeadlineController {

    private static final Duration BUDGET = Duration.ofMillis(250);

    @GetMapping("/wait")
    Mono<ResponseEntity<Reply>> waitForValue(
            @RequestParam(defaultValue = "800") long waitMs) {

        if (waitMs < 0) {
            return Mono.just(ResponseEntity.badRequest()
                    .body(new Reply("invalid", "waitMs must be non-negative")));
        }

        Mono<ResponseEntity<Reply>> upstream =
                Mono.delay(Duration.ofMillis(waitMs))
                    .map(tick -> ResponseEntity.ok(
                            new Reply("success", "done")))
                    .doOnCancel(() ->
                            System.out.println("WAIT_UPSTREAM_CANCEL"))
                    .doFinally(this::logUpstreamEnd);

        return upstream
                .timeout(BUDGET)
                .onErrorResume(TimeoutException.class, ignored ->
                        Mono.just(ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                                .body(new Reply("timeout", "wait exceeded 250 ms"))))
                .doFinally(signal ->
                        System.out.println("WAIT_RESULT_FINALLY=" + signal));
    }

    @GetMapping("/resource")
    Mono<ResponseEntity<Reply>> withResource(
            @RequestParam(defaultValue = "800") long waitMs) {

        if (waitMs < 0) {
            return Mono.just(ResponseEntity.badRequest()
                    .body(new Reply("invalid", "waitMs must be non-negative")));
        }

        Mono<ResponseEntity<Reply>> scoped =
                Mono.using(
                        DemoLease::new,
                        lease -> Mono.delay(Duration.ofMillis(waitMs))
                                .map(tick -> ResponseEntity.ok(
                                        new Reply("success", lease.read()))),
                        DemoLease::close
                );

        return scoped
                .timeout(BUDGET)
                .onErrorResume(TimeoutException.class, ignored ->
                        Mono.just(ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                                .body(new Reply("timeout", "lease wait exceeded 250 ms"))));
    }

    private void logUpstreamEnd(SignalType signal) {
        System.out.println("WAIT_UPSTREAM_FINALLY=" + signal);
    }
}

record Reply(String outcome, String detail) {}

final class DemoLease implements AutoCloseable {

    private final AtomicBoolean closed = new AtomicBoolean();

    DemoLease() {
        System.out.println("LEASE_OPENED");
    }

    String read() {
        return "lease result";
    }

    @Override
    public void close() {
        if (closed.compareAndSet(false, true)) {
            System.out.println("LEASE_CLOSED");
        }
    }
}
```

Đây là **một file Java hoàn chỉnh**: chỉ `ReactiveTimeoutApplication` là top-level `public class`; controller, record và lease cùng file là package-private. `spring-boot-starter-webflux` chọn stack reactive (thường embedded Reactor Netty), Spring quản lý subscription của publisher mà controller trả về.

Từ thư mục `reactive-timeout-demo`, chạy:

```bash
gradle bootRun
```

Nếu dự án có Gradle Wrapper, thay bằng `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows PowerShell. Cần JDK 17+ và Gradle tương thích Boot 3.3.x.

### 6.1. Kết thúc thành công

```bash
curl -i "http://localhost:8080/demo/wait?waitMs=20"
```

Kết quả dự kiến: **HTTP 200 OK** và body JSON:

```json
{"outcome":"success","detail":"done"}
```

Nguồn phát giá trị sau khoảng 20 ms, trước 250 ms. `doFinally` phía trước và phía sau timeout thường ghi nhận `ON_COMPLETE`. Không có lý do cancel upstream ở đường thành công.

### 6.2. Nguồn quá chậm: upstream cancel, downstream trả fallback

```bash
curl -i "http://localhost:8080/demo/wait?waitMs=800"
```

Kết quả dự kiến: **HTTP 504 Gateway Timeout** do **controller chủ động chọn status 504**, body JSON:

```json
{"outcome":"timeout","detail":"wait exceeded 250 ms"}
```

Vì `Mono.delay(800 ms)` chưa phát giá trị ở mốc 250 ms, `timeout` cancel upstream và tạo `TimeoutException`. `onErrorResume` chuyển lỗi này thành ResponseEntity 504. Logger trước timeout nhận cancel; đoạn sau fallback có thể hoàn tất bình thường.

Dòng log có thể biểu diễn các sự kiện:

```text
WAIT_UPSTREAM_CANCEL
WAIT_UPSTREAM_FINALLY=cancel
WAIT_RESULT_FINALLY=onComplete
```

Đây là ví dụ **mang tính minh họa tín hiệu**, không cam kết thứ tự dòng log hoặc chính xác format enum `SignalType.toString()`. Giá trị enum của Reactor tương ứng là `CANCEL` và `ON_COMPLETE`. Một pipeline hoàn tất ở downstream **không bác bỏ** việc upstream bị cancel.

### 6.3. Resource được đóng cả khi cancel

```bash
curl -i "http://localhost:8080/demo/resource?waitMs=800"
```

Kết quả dự kiến: HTTP 504, body:

```json
{"outcome":"timeout","detail":"lease wait exceeded 250 ms"}
```

Với mỗi subscription, `Mono.using` gọi `DemoLease::new`, tạo resource, cung cấp nó cho source rồi gọi `DemoLease::close` khi hoàn tất, lỗi hoặc cancel. Trên đường quá hạn, log gồm `LEASE_OPENED` và `LEASE_CLOSED` (mỗi lease một lần trong ví dụ). Nếu dùng đường thành công `waitMs=20`, resource cũng phải đóng: đó là lý do cleanup nằm trong scope `using`, không chỉ ở nhánh lỗi.

`Mono.using` thích hợp cho cleanup **đồng bộ và nhẹ**. Không nên để `close()` thực hiện I/O blocking kéo dài trên Netty event-loop; cần API bất đồng bộ thì dùng `usingWhen`.

## 7. Kiểm thử bằng `StepVerifier.withVirtualTime`

Kiểm tra cancellation/cleanup bằng **virtual time** giúp tránh chờ timer thật và giảm test chập chờn. Quan trọng: khai báo publisher timer **bên trong Supplier của `withVirtualTime`** để dùng virtual scheduler. Đặt dependency `reactor-test` như trong `build.gradle`.

**`src/test/java/com/example/reactivecleanup/CancellationTest.java`**:

```java
package com.example.reactivecleanup;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CancellationTest {

    @Test
    void timeoutCancelsSlowSource() {
        AtomicInteger cancellations = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                    .doOnCancel(cancellations::incrementAndGet)
                    .timeout(Duration.ofSeconds(1))
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectError(TimeoutException.class)
        .verify();

        assertEquals(1, cancellations.get());
    }

    @Test
    void usingCleansResourceOnCancellation() {
        AtomicInteger closes = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.using(
                        Object::new,
                        resource -> Mono.delay(Duration.ofSeconds(10)),
                        resource -> closes.incrementAndGet()
                )
                .timeout(Duration.ofSeconds(1))
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectError(TimeoutException.class)
        .verify();

        assertEquals(1, closes.get());
    }
}
```

Chạy:

```bash
gradle test
```

Kỳ vọng: **2 test pass**; bộ đếm cancel và close đều bằng 1. Đây là test hành vi, không chỉ kiểm tra fallback. Để kiểm thử HTTP 200/504 và JSON, thêm một integration test với `WebTestClient` khi cần.

Trong sản phẩm thật, bổ sung test cho **complete**, **onError**, **cancel chủ động**, trường hợp tín hiệu đến đúng ranh giới timeout, retry và cleanup lỗi. Không viết assert dựa trên thứ tự log khi callback có thể chạy ở scheduler khác.

## 8. Khi cần cleanup bất đồng bộ: `Mono.usingWhen` / `Flux.usingWhen`

Nếu resource có API reactive như `closeAsync(): Mono<Void>`, lệnh:

```java
source.doFinally(signal -> resource.closeAsync());
```

không đủ: lambda chỉ tạo Publisher nhưng **không có subscription để chạy cleanup**. Tự `subscribe()` trong `doFinally` lại tách lỗi/lifecycle cleanup khỏi nguồn. Hãy dùng resource-scoped operator `usingWhen`, hoặc facility tương ứng của driver/framework.

Ví dụ dưới đây là **khung API minh họa**, cần một interface/implementation resource thực và đặt method trong class thích hợp:

```java
interface AsyncLease {
    Mono<String> fetch();
    Mono<Void> closeAsync();
}

Mono<String> queryWithLease(Mono<AsyncLease> acquireLease) {
    return Mono.usingWhen(
            acquireLease,
            AsyncLease::fetch,
            AsyncLease::closeAsync,
            (lease, failure) -> lease.closeAsync(),
            AsyncLease::closeAsync
    );
}
```

Các tham số của `usingWhen` lần lượt là:

1. Publisher **acquire** resource theo mỗi subscription.
2. Hàm dùng resource và trả Publisher của nghiệp vụ.
3. Publisher cleanup khi **complete**.
4. Publisher cleanup khi **error**.
5. Publisher cleanup khi **cancel**.

Trong ứng dụng dùng transaction, cleanup khi complete có thể là commit; khi error/cancel có thể là rollback. Không tự mặc định "close" tương đương rollback; cần dùng đúng API transaction của driver và transaction manager.

Vị trí timeout làm thay đổi loại sự kiện mà `usingWhen` thấy:

```java
// Timeout ngoài: khi hết hạn, usingWhen bị downstream cancel;
// nhánh asyncCancel có thể được kích hoạt.
queryWithLease(acquireLease).timeout(Duration.ofSeconds(2));

// Timeout bên trong resource closure: lỗi TimeoutException
// là onError trong scope sử dụng resource;
// nhánh asyncError của usingWhen có thể được kích hoạt.
Mono.usingWhen(
        acquireLease,
        lease -> lease.fetch().timeout(Duration.ofSeconds(2)),
        AsyncLease::closeAsync,
        (lease, error) -> lease.closeAsync(),
        AsyncLease::closeAsync
);
```

Các đoạn trên **chưa phải chương trình độc lập**, cần định nghĩa `acquireLease` và `AsyncLease`. `Mono.usingWhen` có thể **trì hoãn tín hiệu hoàn thành tới downstream cho đến khi publisher cleanup async kết thúc**; lỗi cleanup có thể thay đổi kết quả cuối. Khi downstream đã cancel, không bảo đảm có thể truyền lỗi cleanup ngược lại cho subscriber đã mất kết nối, nên cần logging/metrics riêng cho cleanup.

Không đóng một connection hai lần: nếu driver/framework đã quản lý release/transaction, hãy dùng cơ chế chính thức của nó thay vì song song tự viết `closeAsync`.

## 9. Khi client HTTP ngắt kết nối và khi gọi WebClient

### 9.1. Client disconnect

```text
HTTP client ──► Spring WebFlux handler ──► Mono/Flux
                                              │
                                              ├── WebClient / R2DBC
                                              └── HTTP response writer

Client disconnect ──► transport phát hiện ──► subscription bị cancel
                                                  └── upstream / cleanup
```

Web server có thể truyền cancellation vào reactive chain khi client đóng kết nối và transport phát hiện được. **Tốc độ phát hiện và khả năng hủy thực tế phụ thuộc vào Netty, driver và nguồn.** Một transaction hoặc HTTP call đã gửi đi có thể vẫn hoàn tất, dù client không đợi response nữa.

Nếu đang stream SSE/body, response status và headers có thể **đã committed**. Khi một lỗi xuất hiện muộn, ứng dụng không thể tùy ý thay status thành 504 và gửi JSON mới; tùy giao thức phải đóng stream, gửi sự kiện lỗi có hợp đồng riêng hoặc để client reconnect.

### 9.2. WebClient: connect, response I/O và operator timeout

```java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

// Đặt trong cấu hình @Bean hoặc method tương ứng.
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3000)
        .responseTimeout(Duration.ofSeconds(2));

WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();

Mono<String> response = client.get()
        .uri("https://example.org/api/ping")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(4));
```

Đoạn trên là **mã minh họa đặt trong method**, chưa phải file độc lập. `CONNECT_TIMEOUT_MILLIS` đặt timeout mở TCP connection, `responseTimeout` xử lý ngưỡng chờ response ở tầng Reactor Netty, còn `Mono.timeout` đặt ngưỡng chờ tín hiệu của publisher được subscribe. Không đánh đồng ba ngữ nghĩa. URL chỉ mang tính ví dụ, không khẳng định endpoint có tồn tại.

`retrieve().bodyToMono(...)` dùng codec/WebClient quản lý body trong đường xử lý chuẩn. Nếu cần branch theo HTTP status, `exchangeToMono`/`exchangeToFlux` cho phép decode có điều kiện và sau khi publisher handler kết thúc, phần body còn chưa tiêu thụ được kiểm tra và release. Khi trực tiếp thao tác `ClientResponse`, pooled `DataBuffer` hoặc HTTP stream thấp tầng, phải theo đúng ownership và contract cleanup tương ứng.

### 9.3. Tránh `subscribe()` tách rời khỏi request

**Mẫu nên tránh trong controller:**

```java
// Anti-pattern: tạo một tác vụ tự chạy, ngoài subscription HTTP.
webClient.get().uri("/slow")
        .retrieve().bodyToMono(String.class)
        .subscribe();

return Mono.just("accepted");
```

Đây là mảnh code minh họa, không phải method đầy đủ. HTTP response có thể trả "accepted" trước khi lệnh WebClient kết thúc, và cancel ở request không tự hủy subscription độc lập đã tạo bằng `subscribe()`.

**Mẫu liên kết đúng vòng đời:**

```java
// Bên trong method trả Mono<String> và có webClient phù hợp.
return webClient.get().uri("/slow")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(2));
```

Framework sẽ subscribe vào chuỗi đó để hoàn thành response. Nếu thực sự cần background job, phải có cơ chế quản lý tác vụ/lifecycle, retry và lỗi riêng.

## 10. Pooled DataBuffer, producer callback và dòng vô hạn

### 10.1. Buffer bị discard khi cancel

Một số operator giữ queue/prefetch. Khi subscriber cancel, những phần tử **chưa được phát xuống dưới** có thể bị loại bỏ. Nếu đó là resource phải release (ví dụ pooled `DataBuffer` mà code tự sở hữu), dọn ở `doOnNext` là chưa đủ.

`doOnDiscard(DataBuffer.class, DataBufferUtils::release)` là một công cụ khi đặt đúng vị trí sau các operator hỗ trợ discard. Chỉ dùng khi **đã xác định quyền sở hữu buffer và tránh double release**. Reactor không hứa mọi operator đều hỗ trợ discard. Nếu codec, framework hay driver đang tự quản lý buffer thì không tự gọi `release` một lần nữa.

Đối với stream/file/connection mở theo subscription, `using`/`usingWhen` làm quyền sở hữu rõ ràng hơn. Với stream vô hạn, luôn có chính sách stop/cancel/reconnect, queue bound và backpressure; không để subscriber bị mất mà producer vẫn giữ listener hoặc socket.

### 10.2. Adapter tạo bằng `Flux.create`

Nếu bọc callback API cũ, phải tháo đăng ký callback khi sink hoàn tất hoặc cancel. Khung minh họa:

```java
Flux<String> events = Flux.create(sink -> {
    // registerWithSource là API adapter do ứng dụng tự định nghĩa.
    Disposable registration = registerWithSource(
            value -> sink.next(value),
            error -> sink.error(error)
    );

    sink.onDispose(registration::dispose);
});
```

**Đây không phải file độc lập có thể biên dịch**, vì `registerWithSource` là hàm giả định; cần import `Flux`/`Disposable` và API callback cụ thể. `onDispose` của sink có thể chạy khi complete, error, cancel; `onCancel` chỉ cho đường cancel (và chạy trước dispose khi cả hai được khai báo). Cần chú ý race: producer có thể callback thêm trong lúc sink đã kết thúc.

### 10.3. Tránh blocking trên event loop

Không gọi `Thread.sleep`, JDBC blocking, `block()` hay SDK blocking dài ngay trên reactor-netty event-loop. Những tác vụ ấy làm nghẽn xử lý nhiều request, và **cancel không nhất thiết interrupt được blocking call**. Nếu buộc phải dùng API blocking, cách ly bằng scheduler như `Schedulers.boundedElastic()` và xác định rõ giới hạn concurrency/cancellation; ưu tiên driver reactive phù hợp khi có thể.

## 11. Quan sát và xử lý lỗi

Ghi trace ID/request ID, thời gian ở từng chặng và số lần hoàn tất theo tín hiệu `ON_COMPLETE`, `ON_ERROR`, `CANCEL`. Đặt `doFinally` **gần upstream cần đo** để hiểu nguyên nhân hủy thực tế, và ở cuối pipeline để biết trạng thái tổng. Đừng coi status 504 hoặc fallback là bằng chứng chắc chắn upstream đã dừng external side effect.

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Có timeout nhưng CPU/DB vẫn chạy | Source blocking hoặc bên thứ ba không hỗ trợ cancel | Kiểm tra driver và cách submit tác vụ; đo thời gian kết thúc thực của source |
| Flux chạy lâu mà `timeout` không nổ | Các phần tử tới đều đặn, dưới khoảng chờ per-item | Thiết kế deadline tổng hoặc giới hạn thời gian stream riêng |
| Upstream báo `CANCEL`, HTTP vẫn trả 504/200 fallback | Timeout hủy upstream, nhánh onErrorResume complete | Quan sát vị trí `doFinally` và response mapping |
| Resource mở liên tục nhưng không đóng | Cleanup chỉ có trên success/error, thiếu cancel | Chuyển sang `using`/`usingWhen` và test đường cancel |
| Cleanup async không chạy | Chỉ tạo `Mono<Void>` trong `doFinally` mà không có subscription | Dùng `usingWhen` hoặc transaction manager đúng cách |
| Pool/heap tăng khi có nhiều cancellation | Pooled buffer/response body không được release, producer không tháo callback | Audit ownership, discard, Netty metrics, connection pool |
| Client ngắt kết nối nhưng request vẫn chạy | Transport chưa nhận ra disconnect hoặc operation không cancellable | Theo dõi cancellation signal và external request lifecycle |
| Streaming lỗi nhưng không có JSON 504 | Status/headers đã gửi trước lúc lỗi | Thiết kế giao thức lỗi streaming, reconnect/heartbeat |
| Retry khuếch đại tải | Timeout trong mỗi attempt, nhiều lần retry/backoff | Giới hạn retry, tổng budget, idempotency và rate limit |

Trong test không nên sleep để chờ log. Dùng `StepVerifier.withVirtualTime` cho timer, kiểm tra counter close/cancel, và integration test với WebTestClient khi cần chứng thực HTTP.

## 12. Checklist thiết kế pipeline an toàn

1. Xác định **timeout nào**: connect, I/O response, Mono, khoảng cách giữa phần tử Flux hay deadline tổng.
2. Liên kết toàn bộ upstream cần hủy vào **cùng subscription**, không vô ý tự `subscribe()`.
3. Biết client/proxy/server có thể đóng kết nối riêng; không mặc định luôn trả được response lỗi sau khi headers committed.
4. Xác định ai **sở hữu resource** và dọn trên **complete, error, cancel**; dùng `usingWhen` nếu release bất đồng bộ.
5. Không coi cancel là rollback hoặc phép kill thread; tác vụ có side effect cần idempotency/transaction.
6. Đặt log/metric đúng vị trí operator, phân biệt trạng thái upstream và downstream sau fallback.
7. Test timeout, success, source error, cancellation và cleanup; tránh phụ thuộc stdout/timing thực.

## 13. Tài liệu chính thức

- Reactor Core 3.6.17 — `Mono.timeout`, `doFinally`, `doOnCancel`, `using` và `usingWhen`: https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Mono.html
- Reactor Core 3.6.11 — `Flux.timeout` giữa các lần phát phần tử: https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Flux.html
- Reactor Core 3.6 — guide về resource và discard: https://projectreactor.io/docs/core/3.6.7/reference/reactor-core-reference-guide-3.6.7.pdf
- Spring Framework — WebClient và Reactor Netty connection/response timeout: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework — `exchangeToMono`, body consumption và release: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html

**Ghi nhớ:** timeout là *giới hạn chờ*; cancellation là *tín hiệu hủy subscription*; cleanup là *trách nhiệm giải phóng tài nguyên trong cả ba nhánh complete/error/cancel*. Phải thiết kế đồng thời cả ba để pipeline reactive đáng tin cậy.
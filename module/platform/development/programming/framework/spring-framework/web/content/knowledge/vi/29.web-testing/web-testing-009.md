# Kiểm thử Flux, SSE, hủy đăng ký và giới hạn thời gian trong Spring WebFlux

## 1. Mục tiêu: kiểm thử một luồng khác với kiểm thử một JSON response

Trong Spring WebFlux, một HTTP response có thể chứa **một đối tượng** (`Mono<T>`), **một chuỗi hữu hạn** (`Flux<T>`), hoặc **một luồng dài hạn/không kết thúc** (Server-Sent Events — SSE, NDJSON streaming…). Kiểm thử phải quan sát các tín hiệu Reactive Streams, không chỉ HTTP status.

Ba loại tín hiệu quan trọng của `Publisher`:

- `onNext(value)`: có phần tử mới.
- `onComplete()`: luồng kết thúc thành công; **không bắt buộc** phải xảy ra với stream SSE sống liên tục.
- `onError(error)`: luồng kết thúc có lỗi; không thể tiếp tục phát `onNext` sau đó.

Ngoài ba tín hiệu downstream, `cancel()` là hành động từ **subscriber gửi ngược lên upstream** để hủy subscription. Hủy không phải lỗi, cũng không phải `onComplete` của nguồn.

```text
                   HTTP status + headers
WebTestClient.exchange() ────────┐
                                 ▼
                       FluxExchangeResult<T>
                                 │ getResponseBody()
                                 ▼
                         Flux<T> đã decode
                                 │
                         StepVerifier
                   ┌─────────────┼──────────────┐
                   ▼             ▼              ▼
              expectNext     expectError     thenCancel
                   │             │              │
             verifyComplete    verify       verify
             (luồng hữu hạn) (kết thúc lỗi) (luồng vô hạn)
```

**Hai lớp kiểm thử bổ sung nhau:**

1. **Kiểm thử HTTP contract/streaming** bằng `WebTestClient`: status, `Content-Type`, mã hóa SSE/NDJSON, dữ liệu đầu ra và behavior khi client hủy.
2. **Kiểm thử trực tiếp Reactor publisher** bằng `StepVerifier`: đúng thứ tự dữ liệu, hoàn tất/lỗi, backpressure, cancellation và các operator thời gian với virtual time.

Bài dùng **Spring Framework 6.1.x, Spring Boot 3.3.x, Java 17+, Reactor Test/JUnit 5**. Mẫu Java độc lập và lệnh chạy nằm ở phần 7.

## 2. Flux hữu hạn: assert phần tử, thứ tự, hoàn tất và lỗi

Khi một endpoint trả chuỗi hữu hạn, cần kiểm tra **đúng loại nội dung**, thứ tự, số phần tử và tín hiệu cuối.

Ví dụ nguồn Reactor thuần:

```java
Flux<Integer> values = Flux.just(2, 4, 6);

StepVerifier.create(values)
    .expectNext(2, 4, 6)
    .verifyComplete();
```

`StepVerifier.create(...)` đăng ký một subscriber kiểm thử. `expectNext(...)` là so sánh từng phần tử **theo thứ tự**. `verifyComplete()` vừa kỳ vọng `onComplete` vừa thực thi verification. Nếu nguồn phát thêm phần tử, phát lỗi hoặc không bao giờ hoàn tất, test sẽ thất bại hoặc có thể bị treo nếu không có thời hạn kiểm thử.

Đối với dữ liệu phức tạp:

```java
StepVerifier.create(service.findProducts())
    .assertNext(p -> assertEquals("Notebook", p.name()))
    .expectNextMatches(p -> p.price() > 0)
    .verifyComplete();
```

Đây là **mã minh họa**, phụ thuộc `service`, `Product.price()` và import `assertEquals` được định nghĩa trong ứng dụng. `assertNext` dùng JUnit assertions bên trong; `expectNextMatches` dùng predicate. Dùng `expectNextCount(n)` khi chỉ cần biết có n phần tử, nhưng với dữ liệu quan trọng nên kiểm tra cả nội dung.

Kiểm tra nguồn kết thúc lỗi:

```java
Flux<String> broken = Flux.concat(
    Flux.just("first"),
    Flux.error(new IllegalStateException("upstream failed"))
);

StepVerifier.create(broken)
    .expectNext("first")
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
        && "upstream failed".equals(error.getMessage()))
    .verify();
```

Các snippet này cần imports `reactor.core.publisher.Flux`, `reactor.test.StepVerifier` và JUnit assertions khi phù hợp. Lưu ý `expectErrorMatches(...).verify()` cho một terminal error; không dùng `verifyComplete()` nếu hợp đồng của luồng là phát lỗi.

**Với HTTP endpoint trả `Flux<T>`:** `expectBodyList(T.class)` phù hợp khi response **hữu hạn và được gom hoàn chỉnh**. Với stream không kết thúc, hãy dùng `returnResult(T.class)` để lấy dữ liệu theo dòng, không gom toàn bộ body.

## 3. SSE: hiểu định dạng để viết assertion chính xác

**Server-Sent Events (SSE)** là cơ chế HTTP một chiều server → client, thường phản hồi `Content-Type: text/event-stream`. Mỗi event có thể bao gồm các trường:

```text
id: 17
event: price-updated
data: {"sku":"P1","price":120}

```

Dòng trống đánh dấu ranh giới event. Có thể có `retry: 5000`, nhiều dòng `data:`, dòng comment `: heartbeat` hoặc sự kiện chỉ có data. Thứ tự và presence của các trường phụ thuộc server; đừng áp đặt tất cả event phải có `id`, `event` hay `retry` nếu hợp đồng không yêu cầu.

Spring hỗ trợ `ServerSentEvent<T>`:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(index -> ServerSentEvent.<String>builder()
            .id(String.valueOf(index))
            .event("tick")
            .data("value-" + index)
            .build());
}
```

Đây là đoạn **minh họa trong controller**; cần các imports `GetMapping`, `MediaType`, `Flux`, `ServerSentEvent`, `Duration`. Nguồn `Flux.interval` phát 0, 1, 2… theo thời gian. Do không có `take(...)`, nó **không tự hoàn tất**.

Kiểm thử SSE qua `WebTestClient`:

```java
FluxExchangeResult<ServerSentEvent<String>> result = client.get()
    .uri("/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
    .returnResult(new ParameterizedTypeReference<ServerSentEvent<String>>() {});

StepVerifier.create(result.getResponseBody())
    .assertNext(e -> {
        assertEquals("tick", e.event());
        assertEquals("0", e.id());
        assertEquals("value-0", e.data());
    })
    .assertNext(e -> assertEquals("value-1", e.data()))
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

Cần imports `FluxExchangeResult`, `ParameterizedTypeReference`, `StepVerifier`, `MediaType`, `ServerSentEvent`, `Duration` và JUnit assertions. Đây là **mã minh họa**; biến `client` cần được khởi tạo đúng; ví dụ hoàn chỉnh ở phần 7. `returnResult(new ParameterizedTypeReference<...>() {})` giữ thông tin kiểu generic để decoder chọn đúng `ServerSentEvent<String>`. Nếu chỉ lấy dữ liệu `data`, có thể decode trực tiếp thành `String` theo media type và codec tương ứng, nhưng khi cần kiểm tra `id/event/retry` nên giải mã `ServerSentEvent<T>`.

**Đừng kiểm tra raw bytes một cách cứng nhắc** nếu mục tiêu là semantic: encoder có thể biểu diễn newline hoặc metadata khác nhau tùy codec/version. Kiểm tra status, `Content-Type`, dữ liệu và event metadata theo hợp đồng. Kiểm tra raw SSE frames riêng khi hợp đồng yêu cầu chính xác wire format.

### SSE khác WebSocket và NDJSON

- **SSE:** một chiều server → client trên HTTP, media type `text/event-stream`, event framing với `data/id/event/retry`.
- **NDJSON:** nhiều JSON object theo từng dòng, media type thường là `application/x-ndjson`; có thể decode thành `Flux<Dto>`, không có metadata SSE.
- **WebSocket:** kết nối hai chiều với protocol framing khác; không dùng `WebTestClient` SSE assertions để kiểm thử một WebSocket session. Với WebSocket dùng `WebSocketClient`/`WebSocketHandler` hoặc công cụ test thích hợp.

`Content-Type` chỉ xác định cách body được diễn giải; nó không tự bảo đảm server thật phát từng chunk mà không bị proxy buffer, vì vậy cần test thực qua HTTP khi muốn kiểm tra streaming network.

## 4. Không bao giờ chờ onComplete của stream vô hạn

Đây là **anti-pattern**:

```java
// Sai nếu endpoint /events không bao giờ onComplete:
client.get().uri("/events")
    .exchange()
    .expectBodyList(String.class)
    .hasSize(10);
```

`expectBodyList` thường đòi đọc hết response để gom mọi phần tử; một stream liên tục có thể không kết thúc và tăng thời gian/bộ nhớ. Tương tự, các thao tác `collectList().block()` hoặc `blockLast()` trên `Flux.interval` vô hạn là không phù hợp.

Cách đúng: kiểm tra một số event có ý nghĩa rồi **chủ động hủy** subscription:

```java
StepVerifier.create(result.getResponseBody())
    .expectNextCount(3)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

`thenCancel()` diễn đạt rõ kỳ vọng: **test dừng sau ba sự kiện, không đòi server gửi `onComplete`**. Thời hạn `verify(Duration.ofSeconds(5))` giúp test fail có giới hạn nếu sự kiện không bao giờ đến.

Có thể dùng `take(n)` để tạo **Flux hữu hạn ở downstream**, ví dụ:

```java
StepVerifier.create(source.take(3))
    .expectNextCount(3)
    .verifyComplete();
```

`take(3)` thu nhận ba phần tử rồi **cancel subscription upstream** và phát `onComplete` cho downstream. Hai quan sát “downstream hoàn tất” và “upstream bị hủy” khác nhau nhưng tương thích. Nếu cần chứng minh cleanup phía producer, phải theo dõi tín hiệu cancel hoặc `doFinally` tại nguồn.

## 5. Hủy đăng ký: kiểm tra đúng SignalType và cleanup

**Cancellation** xảy ra khi người tiêu thụ không muốn nhận thêm dữ liệu. Ví dụ: tab bị đóng, client ngắt SSE, `StepVerifier.thenCancel()`, downstream `take(2)` hoặc timeout hủy nguồn. Reactive Streams gửi `cancel()` ngược về upstream; phần còn lại của pipeline có thể thực hiện `doOnCancel` và `doFinally(SignalType.CANCEL)`.

Ví dụ đơn giản:

```java
AtomicInteger cancelCalls = new AtomicInteger();

Flux<Long> source = Flux.interval(Duration.ofMillis(20))
    .doOnCancel(cancelCalls::incrementAndGet);

StepVerifier.create(source)
    .expectNext(0L, 1L)
    .thenCancel()
    .verify(Duration.ofSeconds(3));

assertEquals(1, cancelCalls.get());
```

Đây là snippet minh họa; cần imports `AtomicInteger`, `Duration`, `Flux`, `StepVerifier` và `assertEquals`. Cách viết với `Flux.interval` và thời gian thật có thể bị ảnh hưởng bởi scheduling; phần 7 cung cấp test **virtual time** ổn định hơn.

Phân biệt:

```java
source
    .doOnCancel(() -> cleanupSubscription())
    .doFinally(signal -> recordFinalSignal(signal));
```

- `doOnCancel` được gọi khi source nhận cancel.
- `doFinally` được gọi sau complete, error hoặc cancel; phân biệt bằng `SignalType.ON_COMPLETE`, `ON_ERROR`, `CANCEL`.
- `doOnTerminate` chỉ phản ánh onComplete/onError ở điểm đặt operator, **không thay thế** `doFinally` khi cần dọn tài nguyên cho cả cancellation.
- Khi đăng ký resource như listener, timer, file handle hoặc subscription đến broker, nên dùng `Flux.using`/`usingWhen` hoặc cleanup phù hợp; viết cleanup idempotent vì nhiều luồng lỗi/timeout có thể tương tác.
- `StepVerifier.thenCancel` xác minh luồng client dừng theo kịch bản, **không tự chứng minh kernel socket đã đóng hay server container đã giải phóng connection**. Cần test thực ở tầng network/lifecycle nếu đó là yêu cầu.

**Kiểm thử cancellation không đồng nghĩa kiểm thử backpressure**: backpressure là `request(n)` điều tiết nhu cầu; cancel là kết thúc subscription. Khi muốn kiểm tra số lượng yêu cầu, dùng `StepVerifier.create(source, initialRequest)` rồi `thenRequest(n)` với `TestPublisher` hoặc nguồn tôn trọng demand. Không suy đoán demand từ số event bạn nhìn thấy.

## 6. Ba loại giới hạn thời gian khác nhau

| Cơ chế | Điều đang giới hạn | Biểu hiện khi vượt |
| --- | --- | --- |
| `WebTestClient.Builder.responseTimeout(Duration)` | Thời gian WebTestClient đợi **response** trong quá trình exchange; mặc định của Spring 6.1 là 5 giây | Exchange/test có thể thất bại vì chờ response quá lâu |
| `StepVerifier.verify(Duration)` | Thời gian thực tối đa dành cho **kịch bản assertion của StepVerifier** | Test fail khi không đạt terminal/cancel expectation kịp hạn; không phải HTTP response |
| Reactor `Publisher.timeout(Duration)` | Khoảng chờ tín hiệu tiếp theo của publisher (tùy overload có timeout cho từng item) | Phát `TimeoutException` downstream và hủy upstream |
| Reactor `take(Duration)` | Khoảng thời gian cho phép phát các phần tử | Hoàn tất downstream khi hết thời gian, thường cancel upstream |
| Connect/read/response timeout của HTTP client nền | DNS/TCP connect, chờ byte response, transport | Lỗi request/transport tương ứng, khác timeout Reactor |
| Deadline nghiệp vụ xuyên retry | Tổng thời gian cả request, retry, xử lý | Phụ thuộc cách thiết kế pipeline và vị trí operator |

### Timeout cho WebTestClient

`WebTestClient` gắn trực tiếp vào controller/router mock (không cần server):

```java
WebTestClient client = WebTestClient
    .bindToController(new EventController())
    .configureClient()
    .responseTimeout(Duration.ofSeconds(5))
    .build();
```

Đây là cấu hình minh họa; phần 7 có class thật. `responseTimeout` của WebTestClient bảo vệ quá trình đợi phản hồi; với SSE **đã bắt đầu**, dùng `StepVerifier.verify(Duration)` để giới hạn thời gian quan sát event. Đừng coi `responseTimeout(5s)` là hợp đồng “mọi SSE connection phải đóng sau 5s”.

### Timeout trong pipeline Reactor

`timeout` phát lỗi nếu không có tín hiệu kịp deadline:

```java
Mono<String> expensive = Mono.delay(Duration.ofSeconds(10))
    .map(value -> "ready")
    .timeout(Duration.ofSeconds(3));
```

Publisher này dự kiến phát lỗi `TimeoutException` (từ `java.util.concurrent`) thay vì phát "ready". Lưu ý `timeout` **không chỉ là assert của test**: nó là một operator sản phẩm có tác dụng hủy subscription upstream. Với `Flux` có event liên tục, `timeout(Duration.ofSeconds(3))` giám sát khoảng **giữa các event**; luồng cứ đều đặn nhận event thì có thể tồn tại lâu hơn 3s. Muốn deadline **tổng** trong cả giao dịch, phải thiết kế ngân sách thời gian riêng (ví dụ áp giới hạn lên một `Mono` đại diện cho toàn bộ kết quả hoặc dùng `take(Duration)` cho stream).

`take(Duration)` có ý nghĩa khác:

```java
Flux<Long> finite = Flux.interval(Duration.ofSeconds(1))
    .take(Duration.ofSeconds(3));
```

Khi hết window, downstream có thể nhận `onComplete` thay vì lỗi timeout. Thứ tự, số item tại đúng ranh giới thời gian và loại scheduler có thể ảnh hưởng; nếu test cần con số chính xác, hãy dùng virtual time và kiểm soát mốc thời gian.

## 7. Ví dụ đầy đủ Java 17+ với JUnit 5, Spring WebFlux và Reactor Test

Project này **không cần chạy HTTP server thật**. `WebTestClient.bindToController(...)` dùng mock server binding để kiểm tra endpoint WebFlux, decoder SSE/NDJSON, trong khi `StepVerifier.withVirtualTime(...)` kiểm tra cancellation và timeout của publisher mà không phải chờ nhiều giây thực tế.

Cấu trúc:

```text
flux-sse-test/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   └── StreamController.java
    └── test/java/demo/
        ├── StreamControllerTest.java
        └── PublisherTimingTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'flux-sse-test'
```

**`build.gradle`** — yêu cầu JDK 17+, Gradle 8.x:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')

    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.test {
    useJUnitPlatform()
}
```

Spring Boot BOM quản lý các phiên bản phụ thuộc tương thích, gồm Reactor. `reactor-test` chứa `StepVerifier`, không phải là thành phần code production cần đưa vào `implementation`. Không yêu cầu plugin Boot vì ví dụ chỉ chạy unit/web-layer tests.

**`src/main/java/demo/StreamController.java`**

```java
package demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class StreamController {
    private final AtomicInteger canceled = new AtomicInteger();

    public int cancellationCount() {
        return canceled.get();
    }

    @GetMapping(value = "/items", produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Item> items() {
        return Flux.just(
            new Item(1, "Notebook"),
            new Item(2, "Pen")
        );
    }

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofMillis(25))
            .map(index -> ServerSentEvent.<String>builder()
                .id(Long.toString(index))
                .event("tick")
                .data("value-" + index)
                .build())
            .doOnCancel(canceled::incrementAndGet);
    }

    public record Item(int id, String name) {}
}
```

`/items` là **NDJSON hữu hạn**; `/events` là SSE **không kết thúc** cho tới khi downstream cancel hoặc connection đóng. `AtomicInteger` giúp quan sát số lần nguồn bị hủy khi cần; test HTTP không dựa vào giá trị này để tránh race giữa mock exchange và cleanup.

**`src/test/java/demo/StreamControllerTest.java`**

```java
package demo;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StreamControllerTest {
    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToController(new StreamController())
            .configureClient()
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }

    @Test
    void finiteNdjsonFluxHasTwoItemsAndCompletes() {
        FluxExchangeResult<StreamController.Item> result = client.get()
            .uri("/items")
            .accept(MediaType.APPLICATION_NDJSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_NDJSON)
            .returnResult(StreamController.Item.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(
                new StreamController.Item(1, "Notebook"),
                new StreamController.Item(2, "Pen"))
            .verifyComplete();
    }

    @Test
    void sseHasMetadataAndCanBeCanceledAfterTwoEvents() {
        FluxExchangeResult<ServerSentEvent<String>> result = client.get()
            .uri("/events")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
            .returnResult(
                new ParameterizedTypeReference<ServerSentEvent<String>>() {});

        StepVerifier.create(result.getResponseBody())
            .assertNext(event -> {
                assertEquals("0", event.id());
                assertEquals("tick", event.event());
                assertEquals("value-0", event.data());
            })
            .assertNext(event -> {
                assertEquals("1", event.id());
                assertEquals("value-1", event.data());
            })
            .thenCancel()
            .verify(Duration.ofSeconds(5));
    }
}
```

**Điểm cần quan sát:** test 1 kết thúc bằng `verifyComplete()` vì hai phần tử là toàn bộ response. Test 2 kết thúc bằng `thenCancel()` vì stream không có `onComplete` tự nhiên. `ParameterizedTypeReference` giữ kiểu `ServerSentEvent<String>` để có thể kiểm tra cả `id`, `event` và `data` sau khi client decode.

**`src/test/java/demo/PublisherTimingTest.java`**

```java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PublisherTimingTest {

    @Test
    void cancelNotifiesUpstream() {
        AtomicInteger cancelCalls = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Flux.interval(Duration.ofSeconds(1))
                    .doOnCancel(cancelCalls::incrementAndGet))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectNext(0L, 1L)
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertEquals(1, cancelCalls.get());
    }

    @Test
    void timeoutEmitsErrorAndCancelsUpstream() {
        AtomicInteger cancelCalls = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                    .doOnCancel(cancelCalls::incrementAndGet)
                    .timeout(Duration.ofSeconds(3)))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(2))
            .thenAwait(Duration.ofSeconds(1))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));

        assertEquals(1, cancelCalls.get());
    }
}
```

Giải thích hai test thời gian:

- `withVirtualTime(Supplier<Publisher>)` thay thế scheduler thời gian của Reactor để kiểm tra các operator như `interval`/`delay`/`timeout` mà không chờ 10 giây thực. **Publisher phải được tạo lười bên trong lambda**; nếu khai báo `Mono.delay(...)` bên ngoài rồi đưa vào, test có thể vẫn dùng scheduler thật.
- `expectSubscription()` xác nhận subscription trước khi gọi `expectNoEvent(...)`. Nếu `expectNoEvent` được đặt ngay đầu mà chưa consume subscription signal, nó có thể fail.
- `thenAwait(...)` tiến đồng hồ ảo. Một `timeout(3s)` được kiểm tra bằng 2s không có event, thêm 1s và kỳ vọng lỗi.
- `verify(Duration.ofSeconds(2))` là **timeout thời gian thực của test**, giúp ngăn test treo nếu kịch bản virtual time bị cấu hình sai. Nó không biến thành operator `timeout` trong production.
- `doOnCancel` trên nguồn đo upstream bị cancel. Cả `thenCancel()` chủ động và `timeout(...)` khi quá hạn đều có thể gửi cancel cho nguồn.
- Các event của SSE qua `WebTestClient` vẫn dùng scheduling/codec thật của mock WebFlux execution; không nên áp virtual time tuỳ tiện vào toàn bộ HTTP test, trừ khi bạn kiểm soát hoàn toàn scheduler và lifecycle.

Chạy trong thư mục project:

```bash
gradle test
```

Khi cả bốn test pass, Gradle kết thúc với:

```text
BUILD SUCCESSFUL
```

Thông tin log và tổng thời gian tùy máy; Gradle sinh báo cáo mặc định tại `build/reports/tests/test/index.html`. Đây là **kết quả kỳ vọng khi chạy**, không phải transcript đã được thu thập. Có thể dùng Gradle Wrapper nếu project có sẵn (`./gradlew test` hoặc `gradlew.bat test`).

## 8. Tách kiểm thử logic thời gian khỏi HTTP I/O và network behavior

`WebTestClient.bindToController(...)` dùng WebFlux mock request/response và chạy controller/codec mà không đi qua TCP socket. Nó là lựa chọn nhanh để kiểm tra status, media type và event decoding. Để kiểm tra **end-to-end streaming thực sự**, có thể dùng:

```java
WebTestClient client = WebTestClient.bindToServer()
    .baseUrl("http://127.0.0.1:8080")
    .responseTimeout(Duration.ofSeconds(5))
    .build();
```

Đây là **snippet minh họa**; phải có server đang chạy trên cổng tương ứng. Với Spring Boot, có thể chạy `@SpringBootTest(webEnvironment = RANDOM_PORT)`, lấy `@LocalServerPort` và gắn base URL động, hoặc dùng `@AutoConfigureWebTestClient` khi phù hợp. Tầng network test hữu ích cho chunk flushing, HTTP proxies, load balancer, TCP disconnect, TLS và behavior của connector.

**Virtual time nên ưu tiên cho business Reactor publishers** dùng `delay`, `interval`, `timeout` và scheduler mặc định. Nó không tự rút ngắn thời gian thực cho:
- Network HTTP, DNS/TLS/connection pool.
- Scheduler đã được khởi tạo riêng và giữ sẵn ngoài lambda.
- Blocking I/O, `Thread.sleep` hoặc external service.
- Request xử lý bằng scheduler không thuộc hệ thống được virtual hóa.

Kiểm tra stream live trong CI cần thời hạn hữu hạn và tốc độ phát event đủ rộng để tránh flaky vì CPU scheduling. Nếu có thể, tách test HTTP “decode được hai event” khỏi test thời gian ở mức publisher virtual time.

## 9. Kiểm thử cancellation thực tế và backpressure nâng cao

Có thể kiểm tra số yêu cầu (`request(n)`) bằng `StepVerifier` khi nguồn hỗ trợ backpressure:

```java
Flux<Integer> demandAware = Flux.range(1, 10);

StepVerifier.create(demandAware, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(1)
    .expectNext(3)
    .thenCancel()
    .verify(Duration.ofSeconds(2));
```

Giải thích: `create(source, 0)` khởi tạo demand bằng 0, `thenRequest(2)` yêu cầu hai phần tử, sau đó thêm một. `thenCancel` dừng luồng dù nguồn có thể phát tới 10 giá trị. Điều này kiểm tra **honor demand** của publisher, không đo chính xác số TCP chunks hoặc HTTP packets gửi ra.

Với tài nguyên thật, hãy kết hợp `doFinally` hoặc `usingWhen` với assertion ở **đúng vị trí upstream**:

```java
AtomicReference<SignalType> finalSignal = new AtomicReference<>();

Flux<Long> source = Flux.interval(Duration.ofSeconds(1))
    .doFinally(finalSignal::set);

StepVerifier.withVirtualTime(() -> source)
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenCancel()
    .verify(Duration.ofSeconds(2));
```

**Đoạn này chỉ để minh họa ý tưởng**, và khi kiểm thử virtual time nghiêm túc phải **tạo cả nguồn `Flux.interval` bên trong lambda**, không dùng `source` được tạo bên ngoài như đoạn phác thảo này. Cách đúng:

```java
AtomicReference<SignalType> finalSignal = new AtomicReference<>();

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .doFinally(finalSignal::set))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenCancel()
    .verify(Duration.ofSeconds(2));

assertEquals(SignalType.CANCEL, finalSignal.get());
```

Cần import `AtomicReference` và `reactor.core.publisher.SignalType`. `doFinally` chạy ở mốc terminal/cancel, phù hợp chứng minh cleanup signal. Trong test production có concurrency, đừng kiểm tra ngay một biến cleanup bất đồng bộ mà không có đồng bộ hóa; dùng `CountDownLatch`/`Awaitility` hoặc sink signal để chờ giới hạn.

## 10. Lỗi phổ biến

1. **`expectBodyList` / `collectList` trên SSE vô hạn.** Test chờ mãi hoặc tiêu thụ không kiểm soát. Dùng `returnResult` và `thenCancel` sau vài event.
2. **Gọi `verifyComplete()` sau vài sự kiện của stream vô hạn.** Không có `onComplete` dự kiến; kết thúc bằng `thenCancel().verify(Duration)`.
3. **Không đặt timeout của bài test.** Kịch bản sai có thể treo pipeline hoặc chờ rất lâu; dùng `verify(Duration)` cho stream.
4. **Nhầm `verify(Duration)` với `Publisher.timeout(Duration)`.** Cái đầu bảo vệ test runner; cái sau thay đổi pipeline thực và phát `TimeoutException`.
5. **Dùng `withVirtualTime` nhưng tạo `Flux.interval` trước supplier.** Scheduler đã được capture; test không tăng tốc như mong đợi.
6. **Gọi `expectNoEvent` trước khi tiêu thụ subscription.** Subscription bản thân là sự kiện; cần `expectSubscription()` trước.
7. **Chỉ assert HTTP 200 cho SSE.** Response có thể không chứa event hoặc sai schema; kiểm tra `Content-Type`, payload, event id/type khi cần.
8. **Decode SSE thành String rồi nghĩ đã kiểm tra metadata.** Khi cần verify `id/event/retry`, dùng `ServerSentEvent<T>`.
9. **Cho rằng hủy downstream luôn chứng minh socket đã đóng.** `thenCancel` xác minh reactive subscription; cần integration test network cho connection closure.
10. **Quên rằng cancel không phải onComplete/onError.** Cleanup trong `doOnTerminate` có thể bỏ sót cancellation; dùng `doFinally`/`doOnCancel` khi thích hợp.
11. **Không phân biệt stream timeout và total deadline.** `Flux.timeout(3s)` có thể không fail nếu cứ có event mỗi 2s; hạn tổng cần chính sách khác.
12. **Kiểm tra chính xác thời điểm phát event real-time ở CI.** CPU scheduling và OS jitter tạo flaky; test logic thời gian bằng virtual time.
13. **Dùng virtual time cho HTTP network thật** rồi mong vài phút truyền mạng diễn ra tức khắc; đồng hồ ảo không thay network I/O.
14. **Bỏ qua client disconnect/reconnect ở production.** SSE client cần retry/backoff, last-event-id nếu dùng cursor/replay; server cần cleanup on cancel và xử lý slow consumer.

## 11. Câu hỏi tự kiểm tra

1. **SSE không bao giờ complete: nên dùng `verifyComplete` hay `thenCancel`?** → `thenCancel` khi đã assert đủ event, kèm `verify(Duration)` để có giới hạn.
2. **`Flux.take(2)` hoàn tất downstream có nghĩa upstream nhận gì?** → Thông thường upstream nhận `cancel()` sau khi đủ hai phần tử.
3. **Khi nào cần `returnResult(new ParameterizedTypeReference<ServerSentEvent<T>>() {})`?** → Khi cần decode SSE có generic data và kiểm tra cả id/event/retry metadata.
4. **Vì sao không dùng `expectBodyList` cho stream vô hạn?** → Nó chờ body hoàn tất và có thể giữ dữ liệu vô hạn.
5. **SSE gửi dữ liệu mỗi 2 giây và `timeout(3s)`, stream kéo dài 5 phút có phải lỗi?** → Không nhất thiết; timeout theo khoảng lặng giữa event không phải deadline tổng.
6. **`verify(Duration.ofSeconds(2))` có tự gửi timeout tới application pipeline không?** → Không; đó là giới hạn thời gian xác minh test.
7. **Virtual time có tăng tốc một request HTTPS thực không?** → Không; chỉ hỗ trợ các operator/scheduler Reactor được điều khiển.
8. **Khi subscriber cancel, nên cleanup listener ở đâu?** → Trong resource lifecycle, ví dụ `doFinally(CANCEL)`, `doOnCancel` hoặc `usingWhen`, cùng kiểm thử side effect.
9. **Để kiểm tra request(n) khác cancel thế nào?** → `request(n)` phát nhu cầu; `cancel()` kết thúc subscription. Dùng StepVerifier initialRequest + thenRequest.
10. **Kiểm thử SSE bằng mock WebFlux đã đảm bảo proxy production không buffer chưa?** → Chưa; cần end-to-end streaming test với proxy/HTTP connector thật.

## 12. Tài liệu tham khảo

- Spring Framework — WebTestClient, streaming response assertions: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework — WebFlux annotated SSE controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
- Spring Framework 6.1 Javadoc — WebTestClient.Builder responseTimeout: https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.Builder.html
- Spring Framework — ServerSentEvent Javadoc: https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/http/codec/ServerSentEvent.html
- Reactor Core — Testing with StepVerifier and virtual time: https://projectreactor.io/docs/core/release/reference/testing.html
- Reactor Test API — StepVerifier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
- Reactive Streams Specification — Subscriber demand and cancellation: https://www.reactive-streams.org/

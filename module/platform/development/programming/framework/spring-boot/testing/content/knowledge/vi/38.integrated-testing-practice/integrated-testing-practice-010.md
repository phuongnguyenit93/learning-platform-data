# Kiểm thử luồng Reactive bằng virtual time và WebTestClient

## 1. Mục tiêu và vấn đề thực tế

Ứng dụng Spring Boot WebFlux thường trả về `Mono<T>` hoặc `Flux<T>` thay vì một giá trị đồng bộ. Luồng đó có thể phát dữ liệu ngay, đợi vài giây, lấy dữ liệu từ một nguồn khác, retry, timeout hoặc stream không có điểm kết thúc như Server-Sent Events (SSE). Nếu kiểm thử bằng `Thread.sleep`, `block()` và các khoảng chờ thật, test suite chậm, dễ flaky và khó mô tả chính xác hợp đồng sự kiện.

Một lỗi thường thấy:

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofHours(1));
StepVerifier.create(ticks)
    .expectNext(0L)
    .verifyComplete();
~~~

Ví dụ này vừa **không chờ đủ 1 giờ**, vừa kỳ vọng một `Flux.interval` vốn không tự hoàn thành sẽ complete. Nếu ai đó tăng timeout test lên vài giờ, test vẫn thiết kế sai. Cần tách hai câu hỏi:

1. **Logic luồng dưới đồng hồ ảo**: “Khi thời gian tăng đúng một giờ, publisher phát gì, có lỗi hay hoàn thành không?” → `StepVerifier.withVirtualTime`, `VirtualTimeScheduler`.
2. **Giao thức HTTP WebFlux**: “Endpoint trả status/content-type đúng, JSON/SSE decode đúng, response stream có hoàn thành hoặc hủy đúng không?” → `WebTestClient` + `StepVerifier.create(responseBody)`.

Bài thuộc nhóm **Thực hành tích hợp** của module **Spring Boot - testing**, tập trung đúng đề bài **Kiểm thử luồng Reactive bằng virtual time và WebTestClient**.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt assembly, subscription, demand/request, next, error, completion và cancellation trong Reactive Streams.
2. Hiểu `Mono`, `Flux`, `Schedulers.parallel()`, `Scheduler` được inject và các toán tử thời gian `delay`, `interval`, `timeout`, `retryWhen`.
3. Dùng `StepVerifier.create`, `StepVerifier.withVirtualTime`, `VirtualTimeScheduler`, `expectSubscription`, `expectNoEvent`, `thenAwait`, `thenCancel` và `verify(Duration)` đúng ngữ nghĩa.
4. Tránh bẫy **publisher được tạo trước khi virtual scheduler được kích hoạt**.
5. Phân biệt đồng hồ ảo Reactor và đồng hồ thật của HTTP server, external DB/broker, Netty và các thư viện không dùng Reactor scheduler.
6. Kiểm một `Flux` có số phần tử hữu hạn bằng `verifyComplete` và một SSE stream dài/vô hạn bằng `thenCancel`.
7. Dùng `WebTestClient` ở ba mức: `bindToController`, `@WebFluxTest` và `@SpringBootTest(webEnvironment = RANDOM_PORT)`.
8. Kiểm JSON response, HTTP 404, `text/event-stream`, `FluxExchangeResult`, backpressure và error propagation.
9. Biết phân biệt `@MockBean` trong WebFlux slice với service thật trong full-context integration test.
10. Tách test logic thời gian ảo khỏi HTTP streaming contract để vừa deterministic vừa không kiểm sai boundary.
11. Viết một dự án hoàn chỉnh **Java 17 + Spring Boot 3.3.5 + Gradle 8.8 + Reactor Test + JUnit Jupiter**.
12. Chẩn đoán test treo, timeout giả, scheduler leak, race trong test và CI flakiness; có checklist và bài tập mở rộng.

**Nguyên tắc vàng:** Virtual time là một scheduler mô phỏng tiến trình thời gian trong những Reactor operators sử dụng scheduler đó. Nó **không** tăng tốc thời gian vật lý của network, JDBC, REST server ở JVM khác hay một `Thread.sleep` độc lập.

## 2. Nắm vững các tín hiệu Reactive Streams

Một `Publisher` được lắp ráp (assembly) trước khi có subscriber. Khi test subscribe, các tín hiệu có thể đến:

~~~text
Publisher assembly
       |
       v
Subscriber subscribes
       |
       v
onSubscribe(Subscription)   <-- request(n) / cancel()
       |
       +-- onNext(A)
       +-- onNext(B)
       +-- onNext(C)
       |
       +-- onComplete()  hoặc  onError(Throwable)
~~~

`onComplete` và `onError` là **terminal signals**: một luồng không được có cả hai. Cancellation do subscriber yêu cầu kết thúc việc nhận, không phải một `onComplete` message do server gửi.

### 2.1. Mono và Flux

| Khái niệm | Phát bao nhiêu giá trị? | Kết thúc thế nào? |
| --- | --- | --- |
| `Mono.just(x)` | Một | onNext(x), onComplete |
| `Mono.empty()` | Không | onComplete |
| `Mono.error(e)` | Không | onError(e) |
| `Flux.just(a,b,c)` | Ba | onNext(a,b,c), onComplete |
| `Flux.interval(period)` | Có thể vô hạn | Không tự complete |
| `Flux.interval(...).take(3)` | Ba | Complete sau phần thứ ba |
| `Flux.never()` | Không | Không gửi terminal signal |
| `Flux.concat(a, Flux.never())` | Giá trị từ a, rồi đứng chờ | Thường phải cancel |

### 2.2. Vì sao subscribe mới là điểm bắt đầu?

Nhiều Reactor publishers là **cold**: assembly chỉ tạo một pipeline mô tả logic. Khi subscribe, nó mới bắt đầu tải dữ liệu hoặc lên lịch timer. `Mono.delay` và `Flux.interval` lập lịch dựa trên scheduler tại giai đoạn phù hợp, nhưng **việc tham chiếu scheduler có thể được chụp ngay lúc assembly**. Do đó mã tạo publisher **trước** `StepVerifier.withVirtualTime` có thể giữ scheduler thật.

### 2.3. Backpressure

Subscriber yêu cầu bao nhiêu phần tử qua `request(n)`. `StepVerifier.create(publisher, initialRequest)` cho phép kiểm demand. Nhưng HTTP streaming còn có network buffers và codecs: test StepVerifier trên một `Flux.range` không đủ để chứng minh backpressure đi xuyên một reverse proxy hay HTTP connection. Những test tích hợp cần đo behavior ở boundary thật.

### 2.4. Trạng thái chung và thread-safety

Reactive code có thể chạy trên threads khác nhau do `publishOn`/`subscribeOn`. Đừng dựa vào thứ tự scheduler execution hay mutable shared lists không đồng bộ. Trong tests, `StepVerifier` cung cấp một cách quan sát tuần tự signals; khi app có concurrent sources, semantics ordering cần được thiết kế rõ.

## 3. StepVerifier cơ bản

Dependency cần thiết trên Gradle:

~~~groovy
testImplementation 'io.projectreactor:reactor-test'
~~~

Spring Boot BOM quản lý version Reactors theo compatibility của Spring WebFlux. Không nên tự pin Reactor Core khác BOM chỉ vì muốn một API test mới nếu chưa kiểm cùng Spring Framework/Netty versions.

Ví dụ:

~~~java
StepVerifier.create(
        Flux.just("A", "B", "C"))
    .expectNext("A", "B", "C")
    .verifyComplete();
~~~

`verifyComplete()` kiểm toàn bộ expected values **và terminal completion**. Nếu publisher phát thêm một giá trị không nằm trong expected, verifier fail.

Kiểm lỗi:

~~~java
StepVerifier.create(
        Mono.error(
            new IllegalArgumentException("invalid")))
    .expectErrorMatches(error ->
        error instanceof IllegalArgumentException
        && "invalid".equals(error.getMessage()))
    .verify();
~~~

Không dùng `verifyComplete()` cho publisher được thiết kế để phát `onError`.

### 3.1. StepVerifier có thể chờ vô hạn

Nếu bạn viết:

~~~java
StepVerifier.create(Flux.never())
    .expectNext("never")
    .verify();
~~~

test có thể treo vì phần tử cần chờ không bao giờ đến. Dùng real-time verification timeout với `verify(Duration.ofSeconds(5))` trên các scenarios phù hợp. Với stream vô hạn, mô tả điểm dừng bằng `thenCancel()`. Còn với virtual-time case, phải **advance virtual clock**, không đơn giản tăng real timeout.

### 3.2. Không có expected completion cho SSE vô hạn

~~~java
StepVerifier.create(
        Flux.concat(Flux.just("A", "B"), Flux.never()))
    .expectNext("A", "B")
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

Test này có chủ đích cancel sau hai messages. Nếu đổi thành `verifyComplete` sẽ fail/hang vì stream chưa complete.

## 4. Virtual time hoạt động như thế nào?

`StepVerifier.withVirtualTime` thay scheduler factories tiêu chuẩn của Reactor trong phạm vi verification, cho phép timed operators dùng **VirtualTimeScheduler** thay vì chờ wall-clock. Nhà phát hành phải được tạo **lazily** sau khi virtual scheduler được bật.

Ví dụ đúng:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
    .expectSubscription()
    .expectNoEvent(Duration.ofDays(1))
    .expectNext(0L)
    .verifyComplete();
~~~

`Mono.delay` tạo giá trị `0L` sau một ngày **ảo**; test không cần chờ một ngày thật. Vì `expectNoEvent` đếm cả subscription signal, phải đặt `expectSubscription()` trước khi dùng nó.

### 4.1. Sai: assembly trước VirtualTimeScheduler

~~~java
Mono<Long> createdTooEarly =
    Mono.delay(Duration.ofDays(1));

// Không nên: publisher có thể đã capture scheduler thật.
StepVerifier.withVirtualTime(() -> createdTooEarly)
    .expectSubscription()
    .thenAwait(Duration.ofDays(1))
    .expectNext(0L)
    .verifyComplete();
~~~

Đây là **anti-pattern minh họa**, không nằm trong runnable tests. Lambda chỉ trả lại publisher được tạo sớm, không bảo đảm virtual time. Sửa bằng cách đặt toàn bộ assembly trong supplier, hoặc inject một explicit `VirtualTimeScheduler` vào service.

### 4.2. thenAwait khác expectNoEvent

| Bước | Ý nghĩa | Có thể có onNext trong thời gian chờ? |
| --- | --- | --- |
| `thenAwait(Duration)` | Tăng virtual clock hoặc chờ thật | Có |
| `expectNoEvent(Duration)` | Tăng clock/chờ và fail nếu có signal | **Không** |
| `expectNext(value)` | Nhận phần tử chính xác | Phải khớp |
| `expectNextCount(n)` | Nhận đúng n phần tử, không quan tâm value | Có |
| `expectSubscription()` | Chờ subscription signal | Có |
| `thenCancel()` | Hủy subscription | Không phải onComplete |
| `verifyComplete()` | Verify onComplete | Terminal |
| `expectError(...)` | Chờ onError | Terminal |

Nếu muốn khẳng định **không có phần tử trước deadline**, dùng `expectNoEvent`. Nếu chỉ muốn timer tiến tiếp, dùng `thenAwait`. Thời điểm đúng bằng boundary có thể phát sự kiện; test nên thiết kế timeline rõ, tránh giả định clock advancement và event processing của các schedulers không được quản lý.

### 4.3. Virtual time không giải quyết mọi thứ

Các ngoại lệ:

- `Thread.sleep` dùng wall-clock, không được virtual scheduler thay thế.
- Một HTTP server ở **JVM riêng** có scheduler/time source độc lập.
- Java `ScheduledExecutorService` tự tạo không tự được thay.
- Một scheduler được chụp trước virtual-time setup có thể vẫn chạy thời gian thật.
- Blocking JDBC, Redis/Kafka broker/network không thể được “nhảy thời gian” bằng StepVerifier.
- `Instant.now()`/`System.currentTimeMillis()` không tự dùng Reactor virtual clock.
- Một operator thực hiện nhiều việc synchronous/blocking trên cùng scheduler có thể khiến virtual advance bị treo.
- Long/infinite immediate loops có thể hog virtual scheduler thread.

Khi business logic dùng wall-clock, nên inject `java.time.Clock` riêng để kiểm timestamps; khi dùng Reactor timers, inject `Scheduler` để kiểm delays. `Clock` và `Scheduler` giải quyết hai nhiệm vụ khác nhau.

## 5. Chọn chiến lược thời gian ảo

### Chiến lược A — withVirtualTime và tạo publisher trong lambda

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofHours(1))
                .take(2))
    .expectSubscription()
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .thenAwait(Duration.ofHours(1))
    .expectNext(1L)
    .verifyComplete();
~~~

Ưu điểm: ít setup, phù hợp Reactor code dùng `Schedulers.parallel()` mặc định. Nhược điểm: sự thay thế factory scheduler có tính global trong JVM; nếu chạy parallel tests/schedulers được khởi tạo sớm, cần thận trọng.

### Chiến lược B — inject VirtualTimeScheduler trực tiếp

~~~java
VirtualTimeScheduler clock =
    VirtualTimeScheduler.create();

try {
    Flux<Long> values =
        Flux.interval(
            Duration.ofHours(1),
            Duration.ofHours(1),
            clock)
            .take(2);

    StepVerifier.create(values)
        .expectSubscription()
        .then(() ->
            clock.advanceTimeBy(Duration.ofHours(1)))
        .expectNext(0L)
        .then(() ->
            clock.advanceTimeBy(Duration.ofHours(1)))
        .expectNext(1L)
        .verifyComplete();
}
finally {
    clock.dispose();
}
~~~

Ưu điểm: scheduler instance riêng cho test, dễ kiểm soát vòng đời, ít tác động đến các tests khác. Nhược điểm: code production phải cho phép inject scheduler vào timed operations; đây thường là điểm thiết kế tốt.

### So sánh hai chiến lược

| Tiêu chí | withVirtualTime | Inject VirtualTimeScheduler |
| --- | --- | --- |
| Tạo publisher | Bắt buộc lazily trong supplier | Có thể inject từ lúc tạo service |
| Scheduler ownership | Virtual factory scope | Per-test instance |
| Dễ dùng với operator mặc định | Rất tốt | Cần đưa scheduler vào operator |
| Tránh ảnh hưởng global schedulers | Cần kiểm test parallelism | Tốt hơn |
| Kiểm thời gian rất dài | Có | Có |
| Dùng với HTTP server JVM khác | Không tự áp dụng | Không tự áp dụng |
| Cleanup | StepVerifier quản lý factory scope | Test tự dispose |
| Dùng khi | Timer operator thuần | Service có dependency Scheduler |

Không dùng `VirtualTimeScheduler.getOrSet()` ở @BeforeAll của mọi class rồi quên reset: global state dễ làm những tests khác bị ảnh hưởng. Nếu phải dùng factory hooks thủ công, document setup/restore chặt chẽ.

## 6. WebTestClient: ba cách kiểm WebFlux

`WebTestClient` là client API hỗ trợ kiểm Reactive HTTP. Với Spring WebFlux, ba cấp thường dùng:

### 6.1. bindToController

Không cần Spring Boot context:

~~~java
FeedController controller =
    new FeedController(fakeFeedService);

WebTestClient client =
    WebTestClient.bindToController(controller).build();
~~~

Đây là **snippet minh họa**: biến `fakeFeedService` cần tạo trước theo interface/constructor đúng dự án. Mục đích là kiểm controller/codec với WebFlux infrastructure mô phỏng, không mở TCP port.

### 6.2. @WebFluxTest

~~~java
@WebFluxTest(FeedController.class)
class FeedWebSliceTest {

    @Autowired
    WebTestClient client;

    @MockBean
    FeedService service;
}
~~~

Spring Boot tự tạo phần WebFlux cần thiết, controller và `WebTestClient`. Một ordinary `@Service` không tự được nạp trong slice; `@MockBean` (Boot 3.3) bổ sung collaborator phù hợp. Cấp này tốt cho route/status/JSON/SSE contract. Nếu ứng dụng dùng functional `RouterFunction`, `@WebFluxTest` không tự tìm functional routes; cần import router bean/config đúng scope hoặc dùng full context.

### 6.3. @SpringBootTest(RANDOM_PORT)

~~~java
@SpringBootTest(
    webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class FeedLiveHttpTest {
    @Autowired
    WebTestClient client;
}
~~~

Với **ứng dụng reactive WebFlux** và WebTestClient được Boot auto-configure cho random-port tests, đây là HTTP integration qua một server thực với port động. Nó dùng thời gian thật của server/Netty, test phải giữ delay ngắn hoặc có cơ chế kiểm soát chuyên biệt. Không giả định `StepVerifier.withVirtualTime` trong test client có quyền thay timer của toàn server — đặc biệt khi server chạy trong thread/JVM riêng.

### 6.4. bindToServer

~~~java
WebTestClient client =
    WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
~~~

Snippet cho một endpoint server đã chạy. `bindToServer` dùng real network; không bảo đảm port 8080 có service hoặc đúng version, vì vậy test CI không hardcode URL này trừ khi chính pipeline quản lý server. Với `RANDOM_PORT`, dùng Boot-provided injected WebTestClient để tránh port collision.

## 7. Streaming SSE: WebTestClient + FluxExchangeResult

SSE thường dùng content type `text/event-stream`; response có thể phát nhiều events theo thời gian và không tự hoàn thành.

Pattern chuẩn:

~~~java
FluxExchangeResult<FeedEvent> result =
    client.get()
        .uri("/api/feeds/news/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
            MediaType.TEXT_EVENT_STREAM)
        .returnResult(FeedEvent.class);

StepVerifier.create(result.getResponseBody())
    .expectNext(event1, event2, event3)
    .verifyComplete();
~~~

Nếu response dài/vô hạn:

~~~java
StepVerifier.create(result.getResponseBody())
    .expectNext(event1, event2)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

**Hai snippet trên cần biến `client`, `event1`, `event2`, `event3` và imports trong test class**; project runnable ở phần sau định nghĩa đầy đủ.

Không dùng `expectBodyList` cho một infinite SSE: lời gọi có thể chờ body hoàn tất mà không bao giờ xong. Dùng `returnResult(...).getResponseBody()` để kiểm stream incrementally.

### Status/headers và body là hai giai đoạn

`exchange().expectStatus()...` kiểm response metadata. `StepVerifier` kiểm payload stream. Nếu stream phát lỗi **sau khi HTTP response đã commit**, status HTTP có thể vẫn là 200 và connection kết thúc bất thường. Không giả định mọi `onError` giữa stream sẽ biến thành HTTP 500; thiết kế error events/application protocol riêng khi cần.

## 8. Project runnable: Java 17 + Spring Boot 3.3.5 + Gradle 8.8

Dự án nhỏ tạo một feed SSE hữu hạn gồm ba sự kiện. Ở production service, events đến sau 25ms để HTTP tests chạy nhanh. Ở virtual-time tests, cùng business logic được chạy với interval **một ngày hoặc hai giờ ảo** mà không chờ thật. Cấu hình scheduler được inject, không bắt test phải can thiệp global Schedulers factory.

### 8.1. Cây thư mục

~~~text
reactive-virtual-time-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/reactivelab/
    │   ├── ReactiveLabApplication.java
    │   ├── FeedSchedulersConfiguration.java
    │   ├── FeedEvent.java
    │   ├── FeedService.java
    │   └── FeedController.java
    └── test/java/com/example/reactivelab/
        ├── FeedVirtualTimeTest.java
        ├── FeedServiceContractTest.java
        ├── FeedWebSliceTest.java
        └── FeedLiveHttpTest.java
~~~

Gradle Wrapper scripts và `gradle-wrapper.jar` do Gradle sinh hoặc có sẵn từ repo. Bài viết không đính kèm binary jar trong Markdown.

### 8.2. settings.gradle

~~~groovy
rootProject.name = 'reactive-virtual-time-lab'
~~~

### 8.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

`spring-boot-starter-webflux` đưa Spring WebFlux, Reactor và server Netty phù hợp; `reactor-test` là dependency cho `StepVerifier` và `VirtualTimeScheduler`. Boot BOM chọn Reactor Core/Test phiên bản tương thích. Không thêm `spring-boot-starter-web` chỉ vì cần WebTestClient: thêm MVC + WebFlux vào cùng app có thể khiến mặc định web application type đổi sang Servlet và làm kết quả test khác.

### 8.4. ReactiveLabApplication.java

~~~java
package com.example.reactivelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ReactiveLabApplication.class, args);
    }
}
~~~

### 8.5. FeedEvent.java

~~~java
package com.example.reactivelab;

public record FeedEvent(
        String channel,
        long sequence,
        String kind) {
}
~~~

JSON ví dụ:

~~~json
{
  "channel": "news",
  "sequence": 1,
  "kind": "tick"
}
~~~

`record` có value-based `equals`/`hashCode` được Java sinh, nên `StepVerifier.expectNext(new FeedEvent(...))` so giá trị ổn định thay vì object identity.

### 8.6. FeedSchedulersConfiguration.java

~~~java
package com.example.reactivelab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration(proxyBeanMethods = false)
public class FeedSchedulersConfiguration {

    @Bean(name = "feedScheduler",
          destroyMethod = "dispose")
    Scheduler feedScheduler() {
        return Schedulers.newSingle("feed-clock");
    }
}
~~~

`Schedulers.newSingle` tạo scheduler **owned by the context**; khi context đóng, Spring gọi `dispose`. Tránh đăng ký trực tiếp shared `Schedulers.parallel()` làm bean disposable rồi vô tình dispose scheduler chung của các thành phần khác. `@WebFluxTest` với mock service không cần scheduler này.

### 8.7. FeedService.java

~~~java
package com.example.reactivelab;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;

@Service
public class FeedService {

    private final Scheduler scheduler;

    public FeedService(
            @Qualifier("feedScheduler")
            Scheduler scheduler) {
        this.scheduler = scheduler;
    }

    public Flux<FeedEvent> events(
            String channel,
            Duration interval,
            int count) {

        if (channel == null || channel.isBlank()) {
            return Flux.error(
                new IllegalArgumentException(
                    "channel must not be blank"));
        }

        if (interval == null
                || interval.isZero()
                || interval.isNegative()) {
            return Flux.error(
                new IllegalArgumentException(
                    "interval must be positive"));
        }

        if (count <= 0) {
            return Flux.error(
                new IllegalArgumentException(
                    "count must be positive"));
        }

        return Flux.interval(
                interval,
                interval,
                scheduler)
            .map(index -> new FeedEvent(
                channel, index + 1, "tick"))
            .take(count);
    }

    public Mono<FeedEvent> snapshot(String channel) {
        return Mono.defer(() -> {
            if (channel == null
                    || channel.isBlank()) {
                return Mono.error(
                    new IllegalArgumentException(
                        "channel must not be blank"));
            }

            return Mono.just(
                new FeedEvent(
                    channel, 0L, "snapshot"));
        });
    }
}
~~~

**Giải thích thiết kế:**

- Không dùng blocking `sleep` để chờ event.
- `Flux.interval(firstDelay, period, scheduler)` chạy timer qua scheduler được inject.
- `take(count)` biến luồng interval thành finite stream có `onComplete`.
- `Flux.error` trả lỗi trong Reactive Streams thay vì ném trước khi subscriber có mặt.
- `Mono.defer` trì hoãn validation/cấp dữ liệu tới subscription.
- Cùng source dùng scheduler thật ở full app và virtual scheduler ở unit tests.
- Channel, interval và count được kiểm để tránh một stream vô tình vô hạn vì count không hợp lệ.

### 8.8. FeedController.java

~~~java
package com.example.reactivelab;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/feeds")
public class FeedController {

    public static final Duration HTTP_INTERVAL =
        Duration.ofMillis(25);

    private final FeedService service;

    public FeedController(FeedService service) {
        this.service = service;
    }

    @GetMapping(
        path = "/{channel}/snapshot",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<FeedEvent> snapshot(
            @PathVariable("channel") String channel) {

        return service.snapshot(channel);
    }

    @GetMapping(
        path = "/{channel}/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<FeedEvent> events(
            @PathVariable("channel") String channel) {

        return service.events(
            channel, HTTP_INTERVAL, 3);
    }
}
~~~

Có hai routes:

| Method/path | Content type | Contract |
| --- | --- | --- |
| GET /api/feeds/{channel}/snapshot | application/json | `Mono<FeedEvent>` có sequence 0, kind snapshot |
| GET /api/feeds/{channel}/events | text/event-stream | `Flux<FeedEvent>` phát 1,2,3 rồi complete |

Endpoint SSE dùng 25ms vì test HTTP nên nhanh; virtual-time tests của service sẽ dùng interval dài để kiểm đúng semantics. Đừng xem 25ms là SLA production — trong hệ thống thật interval lấy từ config hoặc event source.

## 9. FeedVirtualTimeTest: sáu JUnit tests

**src/test/java/com/example/reactivelab/FeedVirtualTimeTest.java**

~~~java
package com.example.reactivelab;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.test.scheduler.VirtualTimeScheduler;

import static org.junit.jupiter.api.Assertions.*;

class FeedVirtualTimeTest {

    @Test
    void oneDayDelayFinishesWithoutWaitingOneDay() {
        StepVerifier.withVirtualTime(
                () -> Mono.delay(Duration.ofDays(1)))
            .expectSubscription()
            .expectNoEvent(Duration.ofDays(1))
            .expectNext(0L)
            .verifyComplete();
    }

    @Test
    void serviceBuiltInsideSupplierUsesVirtualFactory() {
        StepVerifier.withVirtualTime(() -> {
            FeedService service =
                new FeedService(
                    Schedulers.parallel());

            return service.events(
                "news", Duration.ofHours(2), 2);
        })
        .expectSubscription()
        .thenAwait(Duration.ofHours(2))
        .expectNext(
            new FeedEvent("news", 1L, "tick"))
        .thenAwait(Duration.ofHours(2))
        .expectNext(
            new FeedEvent("news", 2L, "tick"))
        .verifyComplete();
    }

    @Test
    void explicitVirtualSchedulerControlsService()
            throws Exception {

        VirtualTimeScheduler clock =
            VirtualTimeScheduler.create();

        try {
            FeedService service =
                new FeedService(clock);

            StepVerifier.create(
                service.events(
                    "orders",
                    Duration.ofDays(1),
                    3))
                .expectSubscription()
                .then(() ->
                    clock.advanceTimeBy(
                        Duration.ofDays(1)))
                .expectNext(
                    new FeedEvent(
                        "orders", 1L, "tick"))
                .then(() ->
                    clock.advanceTimeBy(
                        Duration.ofDays(1)))
                .expectNext(
                    new FeedEvent(
                        "orders", 2L, "tick"))
                .then(() ->
                    clock.advanceTimeBy(
                        Duration.ofDays(1)))
                .expectNext(
                    new FeedEvent(
                        "orders", 3L, "tick"))
                .verifyComplete();
        }
        finally {
            clock.dispose();
        }
    }

    @Test
    void timeoutErrorAppearsAtVirtualDeadline() {
        StepVerifier.withVirtualTime(
                () -> Mono.never()
                    .timeout(Duration.ofHours(5)))
            .expectSubscription()
            .expectNoEvent(Duration.ofHours(5))
            .expectError(TimeoutException.class)
            .verify();
    }

    @Test
    void infiniteTicksCanBeCanceled() {
        StepVerifier.withVirtualTime(
                () -> Flux.interval(
                    Duration.ofDays(1)))
            .expectSubscription()
            .thenAwait(Duration.ofDays(2))
            .expectNext(0L, 1L)
            .thenCancel()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void backpressureRequiresExplicitDemand() {
        StepVerifier.create(
                Flux.range(1, 5),
                0)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(3)
            .expectNext(3, 4, 5)
            .verifyComplete();
    }
}
~~~

### 9.1. Một ngày ảo là kiểm thử thời gian, không phải benchmark

Method đầu verify `Mono.delay` đúng sau một ngày theo virtual clock. Không nên in “test completed in 0ms” làm expected; CPU scheduling/build overhead thực tế có thể khác.

### 9.2. Supplier phải lắp ráp pipeline muộn

Trong `serviceBuiltInsideSupplierUsesVirtualFactory`, ngay cả việc tạo `FeedService(Schedulers.parallel())` cũng nằm **trong lambda**. Nếu service đã được khởi tạo trước `withVirtualTime` và giữ scheduler thật, timed operator có thể không chạy theo virtual clock.

### 9.3. Inject explicit scheduler giúp cô lập global state

`explicitVirtualSchedulerControlsService` tạo scheduler riêng, advance time bằng callbacks và dispose trong finally. Các tests khác không bị global scheduler factory setup của test này ảnh hưởng. Với test chạy parallel, cách inject tường minh thường an toàn, dễ reasoning hơn.

### 9.4. Test timeout phải phát đúng lỗi

`Mono.never().timeout(...)` phát `TimeoutException` ở deadline. Đây là kiểm operator timeout, **không chứng minh network timeout hay reverse-proxy timeout**. Với HTTP streaming, nhiều lớp timeout khác nhau cần test riêng.

### 9.5. thenCancel không phải verifyComplete

`Flux.interval` vô hạn phải được hủy sau đủ phần tử. Nếu viết `verifyComplete` sẽ không hợp với contract. Kiểm giải phóng resources downstream bằng tests chuyên biệt nếu cancellation là yêu cầu nghiệp vụ.

### 9.6. Backpressure test kiểm request(n)

StepVerifier bắt đầu với demand 0, rồi yêu cầu 2 và 3 phần tử. `Flux.range` tuân theo requests và hoàn thành sau 5 phần tử. Không có `Thread.sleep` và không phụ thuộc network timing.

### 9.7. Giới hạn thật của test classes

`withVirtualTime` thay Reactor scheduler factory ở mức process trong thời gian test; không chạy đồng thời một loạt tests cùng thao túng global scheduler mà không có isolation. Trong project này Gradle Test task mặc định chạy một test JVM và JUnit không bật parallel mode. Nếu muốn parallel hóa, ưu tiên inject scheduler explicit hoặc cô lập tests.

## 10. FeedServiceContractTest: lỗi reactive và snapshot

**src/test/java/com/example/reactivelab/FeedServiceContractTest.java**

~~~java
package com.example.reactivelab;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class FeedServiceContractTest {

    private final FeedService service =
        new FeedService(Schedulers.immediate());

    @Test
    void snapshotEmitsOneRecordAndCompletes() {
        StepVerifier.create(
                service.snapshot("news"))
            .expectNext(
                new FeedEvent(
                    "news", 0L, "snapshot"))
            .verifyComplete();
    }

    @Test
    void blankChannelReturnsReactiveError() {
        StepVerifier.create(
                service.snapshot(" "))
            .expectErrorMatches(error ->
                error instanceof IllegalArgumentException
                && error.getMessage()
                    .contains("channel"))
            .verify();
    }

    @Test
    void zeroIntervalIsRejectedBeforeScheduling() {
        StepVerifier.create(
                service.events(
                    "news", Duration.ZERO, 2))
            .expectError(
                IllegalArgumentException.class)
            .verify();
    }

    @Test
    void nonPositiveCountIsRejected() {
        StepVerifier.create(
                service.events(
                    "news",
                    Duration.ofSeconds(1),
                    0))
            .expectError(
                IllegalArgumentException.class)
            .verify();
    }
}
~~~

`Schedulers.immediate()` không thực thi timers lâu trong test này vì các cases chỉ dùng `snapshot` hoặc trả `Flux.error` trước `Flux.interval`. Không dùng immediate scheduler cho positive timed interval tests: timed scheduling có thể không được hỗ trợ như mong muốn. Với positive timed behavior, dùng VirtualTimeScheduler hoặc scheduler thật được sở hữu đúng scope.

### Test validation mà không block

`StepVerifier.expectError` quan sát `onError`, khác `assertThrows(() -> service.events(...))` vì method chủ động trả `Flux.error` thay vì ném exception lúc gọi. Phân biệt lỗi **assembly-time** và **subscription-time** giúp test phản ánh đúng Reactive Streams contract.

## 11. FeedWebSliceTest: WebTestClient HTTP + SSE

**src/test/java/com/example/reactivelab/FeedWebSliceTest.java**

~~~java
package com.example.reactivelab;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@WebFluxTest(FeedController.class)
class FeedWebSliceTest {

    @Autowired
    WebTestClient client;

    @MockBean
    FeedService service;

    private static FeedEvent event(
            long sequence) {
        return new FeedEvent(
            "news", sequence, "tick");
    }

    @Test
    void snapshotHasJsonAndExpectedFields() {
        when(service.snapshot("news"))
            .thenReturn(Mono.just(
                new FeedEvent(
                    "news", 0L, "snapshot")));

        client.get()
            .uri("/api/feeds/news/snapshot")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.channel")
                .isEqualTo("news")
            .jsonPath("$.sequence")
                .isEqualTo(0)
            .jsonPath("$.kind")
                .isEqualTo("snapshot");

        verify(service).snapshot("news");
    }

    @Test
    void finiteSseCanBeDecodedAsFlux() {
        when(service.events(
                "news",
                FeedController.HTTP_INTERVAL,
                3))
            .thenReturn(Flux.just(
                event(1), event(2), event(3)));

        FluxExchangeResult<FeedEvent> result =
            client.get()
                .uri("/api/feeds/news/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(FeedEvent.class);

        StepVerifier.create(
                result.getResponseBody())
            .expectNext(
                event(1), event(2), event(3))
            .verifyComplete();

        verify(service).events(
            "news", FeedController.HTTP_INTERVAL, 3);
    }

    @Test
    void longLivedSseIsCanceledByConsumer() {
        when(service.events(
                "news",
                FeedController.HTTP_INTERVAL,
                3))
            .thenReturn(
                Flux.concat(
                    Flux.just(event(1), event(2)),
                    Flux.never()));

        FluxExchangeResult<FeedEvent> result =
            client.get()
                .uri("/api/feeds/news/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(FeedEvent.class);

        StepVerifier.create(
                result.getResponseBody())
            .expectNext(event(1), event(2))
            .thenCancel()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void snapshotErrorMapsToHttp404() {
        when(service.snapshot("missing"))
            .thenReturn(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND,
                    "channel not found")));

        client.get()
            .uri("/api/feeds/missing/snapshot")
            .exchange()
            .expectStatus().isNotFound();
    }
}
~~~

### 11.1. Tại sao mock service ở WebFlux slice?

`@WebFluxTest(FeedController.class)` chỉ tạo WebFlux components thuộc slice, không scan regular `@Service`. `@MockBean` đăng ký mock hợp lệ trong Spring context theo Spring Boot 3.3. Không cần import `FeedSchedulersConfiguration` hay khởi động một scheduler thread thật cho controller contract.

### 11.2. Phân biệt JSON snapshot với SSE

`snapshot` là một `Mono<FeedEvent>` hữu hạn, dùng `expectBody().jsonPath(...)` để kiểm JSON. `events` là `Flux<FeedEvent>`, dùng `returnResult(FeedEvent.class)` để decode từng SSE data event. Không dùng `expectBodyList` với long-lived streams.

### 11.3. Test SSE không cần virtual time nếu service mock

Mock trả `Flux.just(...)` ngay lập tức. Điều này **không kiểm interval timing** — interval timing đã được kiểm ở `FeedVirtualTimeTest`. Đây là tách trách nhiệm chính xác: controller test kiểm routing/codec/media type, service test kiểm thời gian.

### 11.4. Cancellation là tín hiệu từ consumer

Test `longLivedSseIsCanceledByConsumer` hủy response stream sau hai events. Nó **không** khẳng định upstream socket/server resource đã dọn ngay lập tức; nếu cancellation cleanup là SLO, thêm hook `doFinally`/metrics và assert phù hợp với asynchronous propagation.

### 11.5. 404 trước khi response commit

`snapshotErrorMapsToHttp404` kiểm lỗi xảy ra **trước emission** của response. Với streaming response đã commit sau phần tử đầu, HTTP status thường không còn đổi được; cần protocol-level error event hoặc strategy khác.

## 12. FeedLiveHttpTest: full context và random port

**src/test/java/com/example/reactivelab/FeedLiveHttpTest.java**

~~~java
package com.example.reactivelab;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    classes = ReactiveLabApplication.class,
    webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class FeedLiveHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void realServerServesSnapshotJson() {
        client.get()
            .uri("/api/feeds/news/snapshot")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.channel")
                .isEqualTo("news")
            .jsonPath("$.sequence")
                .isEqualTo(0)
            .jsonPath("$.kind")
                .isEqualTo("snapshot");
    }

    @Test
    void realServerCompletesThreeSseEvents() {
        FluxExchangeResult<FeedEvent> result =
            client.get()
                .uri("/api/feeds/news/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(FeedEvent.class);

        StepVerifier.create(
                result.getResponseBody())
            .expectNext(
                new FeedEvent("news", 1L, "tick"),
                new FeedEvent("news", 2L, "tick"),
                new FeedEvent("news", 3L, "tick"))
            .verifyComplete();
    }

    @Test
    void realServerResponseCanBeCanceled() {
        FluxExchangeResult<FeedEvent> result =
            client.get()
                .uri("/api/feeds/news/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(FeedEvent.class);

        StepVerifier.create(
                result.getResponseBody())
            .expectNext(
                new FeedEvent("news", 1L, "tick"))
            .thenCancel()
            .verify(Duration.ofSeconds(5));
    }
}
~~~

### 12.1. Vì sao không dùng virtual time ở test HTTP này?

Spring Boot khởi động WebFlux server thật qua random port. Netty và WebFlux request handling sử dụng schedulers, threads và connection lifecycle riêng; `StepVerifier.withVirtualTime` quanh HTTP response có thể can thiệp Reactor global factories trong test JVM mà **không kiểm soát an toàn toàn bộ server path**. Bài chọn interval 25ms cho real HTTP và để virtual time kiểm riêng timed domain Publisher.

### 12.2. Real HTTP test còn giá trị gì?

Nó kiểm app startup, server binding, actual routing, codecs, SSE serialization, finite completion và client cancellation qua một network boundary thật. Nó không thay Testcontainers/database/broker integration nếu stream thực phụ thuộc Redis/Kafka.

### 12.3. Random port và địa chỉ WebTestClient

Spring Boot reactive RANDOM_PORT tests có thể auto-configure `WebTestClient` gắn với server port thật. Không hardcode `localhost:8080`. Đừng dùng bean của `@WebFluxTest` rồi tuyên bố đã kiểm TCP transport: mocked WebFlux không mở cổng.

## 13. Tổng số test trong dự án

| Test class | Số @Test | Mục tiêu |
| --- | ---: | --- |
| `FeedVirtualTimeTest` | 6 | Mono.delay, virtual factory, explicit scheduler, timeout, cancel, demand |
| `FeedServiceContractTest` | 4 | snapshot, blank channel, interval/count validation |
| `FeedWebSliceTest` | 4 | JSON, SSE finite, SSE cancellation, 404 trong mocked WebFlux |
| `FeedLiveHttpTest` | 3 | real HTTP snapshot, real SSE completion, HTTP cancellation |
| **Tổng** | **17** | Timed Publisher + HTTP streaming contract |

**Lưu ý minh bạch:** Đây là **17 phương thức @Test được thiết kế** trong Markdown. Chúng chưa được thực thi trong môi trường soạn bài. Đừng xem câu “dự kiến pass” là một kết quả JUnit/CI thật; sau khi dựng project, chạy Gradle và kiểm JUnit reports.

### Lệnh chạy

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu chưa có Wrapper và Gradle tương thích đã được cài:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Chạy từng lớp:

~~~bash
./gradlew test --tests 'com.example.reactivelab.FeedVirtualTimeTest'
./gradlew test --tests 'com.example.reactivelab.FeedServiceContractTest'
./gradlew test --tests 'com.example.reactivelab.FeedWebSliceTest'
./gradlew test --tests 'com.example.reactivelab.FeedLiveHttpTest'
~~~

Buộc test chạy lại nếu Gradle task đã UP-TO-DATE:

~~~bash
./gradlew test --rerun-tasks --stacktrace
~~~

JUnit HTML/XML sau execution:

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-com.example.reactivelab.FeedVirtualTimeTest.xml
build/test-results/test/TEST-com.example.reactivelab.FeedServiceContractTest.xml
build/test-results/test/TEST-com.example.reactivelab.FeedWebSliceTest.xml
build/test-results/test/TEST-com.example.reactivelab.FeedLiveHttpTest.xml
~~~

Output response body xác định từ source; Gradle duration, PID/port, startup logs và test order **không cố định** nên không bịa stdout.

## 14. Sự khác biệt giữa virtual clock và real clock

Một quy trình test tốt phải biết chính xác **đồng hồ thuộc sở hữu ai**.

| Thành phần | Virtual time được không? | Ghi chú |
| --- | --- | --- |
| `Mono.delay` mặc định | Có, nếu operator tạo sau setup | `withVirtualTime` |
| `Flux.interval` có explicit scheduler | Có | Inject `VirtualTimeScheduler` |
| `Mono.timeout` dùng Reactor scheduler | Có | Vẫn cần publisher lazy |
| `Retry.fixedDelay` được cấu hình scheduler | Có | Test retry count và timeline |
| `Thread.sleep` | Không | Wall-clock blocking |
| `Instant.now()` | Không tự đổi | Inject `java.time.Clock` |
| `ScheduledExecutorService` không qua Reactor | Không tự đổi | Tách abstraction |
| Netty HTTP server | Không tự được test-client clock điều khiển | Dùng short real delay hoặc control server scheduler |
| Kafka broker ngoài process | Không | Broker clock/lifecycle riêng |
| PostgreSQL transaction timeout | Không | Database clock riêng |
| Redis TTL | Không | Redis server clock riêng |
| Remote SSE service | Không | Boundary network thật |
| `Flux.just` | Không cần | Không có time dependency |

Trong cùng JVM, một virtual factory có thể ảnh hưởng các Reactor schedulers của test và server, nhưng **điều này không phải kiến trúc isolation ổn định** cho HTTP tests. Đừng dựa vào race-sensitive global state để làm test mạng chạy “nhanh”.

## 15. Timed operator patterns nên kiểm riêng

### 15.1. Delay

~~~java
Mono<String> message =
    Mono.just("READY")
        .delayElement(Duration.ofMinutes(30));

StepVerifier.withVirtualTime(
        () -> Mono.just("READY")
            .delayElement(Duration.ofMinutes(30)))
    .expectSubscription()
    .expectNoEvent(Duration.ofMinutes(30))
    .expectNext("READY")
    .verifyComplete();
~~~

Biến `message` tạo trước dùng để minh họa **assembly sớm có rủi ro**, còn expression trong lambda là trường hợp đúng. Với `delayElement`, không nhầm nó với `delaySubscription`: chúng trì hoãn các giai đoạn khác nhau.

### 15.2. Timeout và fallback

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.<String>never()
            .timeout(
                Duration.ofHours(4),
                Mono.just("PENDING")))
    .expectSubscription()
    .thenAwait(Duration.ofHours(4))
    .expectNext("PENDING")
    .verifyComplete();
~~~

Đây là snippet độc lập phù hợp khi import `Mono`, `Duration`, `StepVerifier`. Fallback phải có nghĩa nghiệp vụ; nếu timeout là lỗi bắt buộc, kiểm `TimeoutException` thay vì đổi thành PENDING vô điều kiện.

### 15.3. Retry với backoff

Reactor `Retry.fixedDelay` hoặc `Retry.backoff` có policy khác nhau: cố định hoặc exponential, có thể có jitter, điều kiện lọc lỗi và scheduler riêng. Để test deterministic:

- Dùng `Flux.defer`/`Mono.defer` để mỗi attempt thực sự tái chạy source.
- Kiểm số lần subscribe/attempt bằng `AtomicInteger`.
- Với `Retry.backoff`, tắt jitter hoặc kiểm trong tolerance đã thiết kế.
- Chạy trên `VirtualTimeScheduler` hoặc tạo cả publisher trong `withVirtualTime`.
- Phân biệt “3 retries” nghĩa là **4 total subscriptions** (initial + 3).
- Không retry mọi exception vô điều kiện, nhất là validation/authorization errors.
- Nếu retry gọi HTTP/broker thật, virtual time chỉ kiểm scheduler policy, không tự làm remote calls biến mất.

### 15.4. debounce/throttle/bufferTimeout

`debounce` cần không có giá trị mới trong một khoảng thời gian mới phát giá trị trước. `sample`/`throttleFirst` chọn theo cửa sổ khác. `bufferTimeout` flush theo count hoặc deadline. Dùng `TestPublisher` để phát chính xác các source signals và `VirtualTimeScheduler` để dịch clock; test cả trường hợp event ngay ở **boundary**, có upstream complete/error và có downstream cancel.

### 15.5. Đặt real-time timeout cho verifier

~~~java
StepVerifier.create(
        Flux.just("A", "B"))
    .expectNext("A", "B")
    .verifyComplete();
~~~

Khi một publisher có nguy cơ hang, dùng `thenCancel().verify(Duration.ofSeconds(5))` hoặc một verification terminal API với configured timeout. Một global StepVerifier default timeout có thể giúp toàn suite, nhưng hãy biết nó không thay virtual-time advancement.

## 16. TestPublisher và mô phỏng nguồn sự kiện

`reactor-test` còn cung cấp `TestPublisher<T>`, hữu ích khi cần điều khiển thủ công `onNext`, `complete` và `error` từ source mà không dựa vào timer thật.

Ví dụ sketch:

~~~java
TestPublisher<String> source =
    TestPublisher.create();

Flux<String> flux = source.flux();

StepVerifier.create(flux)
    .then(() -> source.next("A", "B"))
    .expectNext("A", "B")
    .then(source::complete)
    .verifyComplete();
~~~

Đây là snippet trong một method có imports phù hợp (`reactor.test.publisher.TestPublisher`), dùng để test tín hiệu nguồn. Với scenarios có backpressure, cân nhắc `TestPublisher.createCold()`/`TestPublisher.createNoncompliant(...)` theo Reactor API và xác định yêu cầu thay vì phát events vi phạm contract một cách vô ý.

### Tách hai chiều kiểm

- **TestPublisher** kiểm cách pipeline phản ứng với upstream values/errors.
- **VirtualTimeScheduler** kiểm cách pipeline xử lý thời gian.
- **WebTestClient** kiểm HTTP wire behavior của kết quả pipeline.
- **StepVerifier** là assertion DSL kết nối cả ba.

Không cần nhồi cả ba vào một test; hãy thiết kế từng scenario có nguyên nhân fail rõ.

## 17. Trường hợp SSE infinite và cancellation

Một SSE endpoint production có thể không tự đóng:

~~~java
@GetMapping(
    path="/updates",
    produces=MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<FeedEvent> updates() {
    return eventService.liveEvents();
}
~~~

Snippet minh họa; `eventService` cần implementation riêng. Test HTTP nên:

1. Gửi GET với `Accept: text/event-stream`.
2. Kiểm status và content type.
3. Nhận response `FluxExchangeResult<FeedEvent>`.
4. Dùng `StepVerifier.create(result.getResponseBody())`.
5. Kiểm một vài events cụ thể/sequence/order.
6. `thenCancel` trước khi timeout.
7. Nếu cancellation cleanup quan trọng, kiểm resource disposal ở service layer bằng metrics/hooks.

### Khi nào dùng verifyComplete?

Chỉ khi contract nói stream finite và complete. Demo `events(...).take(3)` hoàn thành sau ba events, nên test finite SSE dùng `verifyComplete`. Với live feed, buộc completion là sai.

### HTTP disconnect có thể đến trễ

Cancellation ở client không đảm bảo cleanup callback của producer chạy **đúng trong cùng thread/microsecond**. Nếu test assert atomic counter ngay sau `thenCancel` trên real HTTP server, kết quả có thể flaky do disconnect được propagate bất đồng bộ. Kiểm eventually/metrics phù hợp và real timeout; đừng dùng `Thread.sleep(500)` như giả định độ trễ mạng cố định.

## 18. So sánh những loại lỗi reactive

| Tình huống | Tín hiệu reactive | HTTP behavior có thể là |
| --- | --- | --- |
| Source valid phát 3 rồi complete | onNext×3, onComplete | 200 + SSE kết thúc |
| Source invalid ngay khi subscribe | onError trước body | Có thể 4xx/5xx tùy exception mapping |
| Error sau 2 SSE events | onNext×2, onError | HTTP status đã commit; connection cắt hoặc custom error frame |
| Client cancel sau event đầu | cancel từ client | Server dừng producer khi thấy cancel |
| Timeout trên Mono trước response | onError(TimeoutException) | Có thể mapped to 5xx/custom status |
| Infinite stream không cancel | Không terminal | Client test treo |
| Flux có no demand | Không phát như mong muốn | Backpressure/consumer stall |
| Event bị buffer/codec giữ | Publisher có onNext, client chưa decode | Streaming flush/framing issue |
| Java exception trong mapper | onError | Tùy phase, response error |
| External broker mất kết nối | retry/error/resource issue | Không giải quyết chỉ bằng vTime |

Muốn kiểm **HTTP response error contract**, định nghĩa `@RestControllerAdvice`, `@ExceptionHandler` hoặc `ResponseStatusException` có chủ đích, rồi test status/body. Đừng mặc định onError tự động biến thành HTTP 503.

## 19. Streaming media types

| Content type | Dùng khi | Cách test |
| --- | --- | --- |
| `application/json` | One JSON object/list hữu hạn | expectBody/jsonPath |
| `text/event-stream` | SSE events | returnResult(type) + StepVerifier |
| `application/x-ndjson` | Newline-delimited JSON streaming | returnResult(type), codec framing |
| `application/json` cho Flux hữu hạn | Có thể serialize JSON array | expectBodyList/JSON assertions nếu finite |
| `application/octet-stream` | Binary streaming | Kiểm byte buffers/framing, memory |
| `text/plain` | Text flux | returnResult(String.class), encoding |

Đừng nhận `Flux<T>` rồi tự coi response luôn là SSE. HTTP media type/content negotiation quyết định encoding. Test phải gửi `Accept` và assert `Content-Type`. Streaming behavior còn phụ thuộc HTTP server flush/buffers và proxy.

## 20. Functional routes và WebTestClient

Một Spring WebFlux application có thể dùng `RouterFunction<ServerResponse>` thay vì `@RestController`:

~~~java
@Bean
RouterFunction<ServerResponse> feedRoutes(
        FeedService service) {

    return RouterFunctions.route(
        RequestPredicates.GET("/functional/feeds"),
        request -> ServerResponse.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .body(
                service.events(
                    "news", Duration.ofMillis(25), 3),
                FeedEvent.class));
}
~~~

Snippet minh họa thuộc một `@Configuration` có imports WebFlux functional routing API. `@WebFluxTest` không tự phát hiện tất cả functional route beans; khi cần kiểm route, import chính configuration/router function hoặc dùng `@SpringBootTest`.

Không dùng `@WebMvcTest` để test WebFlux functional endpoint: đó là Spring MVC slice với infrastructure khác. `WebTestClient` có thể được dùng với MVC khi bound mock/live server trong những thiết lập được Spring hỗ trợ, nhưng với `@WebFluxTest` bài này chỉ tập trung reactive stack.

## 21. Scheduler, Context cache và concurrency

### 21.1. Schedulers.parallel vs newSingle

`Schedulers.parallel()` là scheduler được dùng chung/factory quản lý. `Schedulers.newSingle(name)` tạo scheduler instance riêng. Khi inject một scheduler qua bean, cần xác định **ownership**: ai tạo, ai dispose, có shared process-wide không. Demo dùng newSingle và `destroyMethod=dispose` để Spring quản lý lifecycle.

### 21.2. Test context cache

Spring TestContext cache giữ `ApplicationContext` để tái sử dụng giữa tests cùng configuration key trong một JVM. `@WebFluxTest` có context nhỏ khác với `@SpringBootTest`. Nếu test dùng `@DirtiesContext` tràn lan, startup cost tăng. Không dùng @DirtiesContext để reset một Reactor publisher subscription; mỗi subscription có lifecycle riêng.

### 21.3. VirtualTimeScheduler global effect

`StepVerifier.withVirtualTime` tạm thay Reactor Schedulers factory, vì vậy không nên chạy nhiều tests thao túng factory global đồng thời trên cùng JVM. `VirtualTimeScheduler.create()` inject riêng giúp cô lập hơn. Việc virtual scheduler được dispose/restore cần đúng lifecycle, không lưu nó trong static field dùng chung với các test khác.

### 21.4. Mock và backpressure khi chạy parallel

`@MockBean` trong WebFlux slice là Spring bean mock; nếu hai test methods chạy đồng thời và stub/reset cùng mock, có race. Mặc định JUnit Jupiter không bật method-level parallel mode; nếu CI bật, cần đảm bảo mocks/fixtures/thread safety hoặc dùng isolation.

### 21.5. Không gọi block() ở event loop

Trong application reactive, `block()` trên Reactor nonblocking threads có thể gây lỗi hoặc nghẽn event-loop. Trong test method thuần, đôi khi block() dùng để đọc Mono hữu hạn, nhưng `StepVerifier` cung cấp assertions tốt hơn cho onError/onComplete/cancel/demand/time. Không xây test bằng `block()` và nhiều `Thread.sleep` nếu cần chứng minh Reactive Streams semantics.

## 22. Nguyên nhân test virtual time bị treo

**Ca 1 — publisher được tạo quá sớm.** `Flux.interval` đã capture real Scheduler trước khi `withVirtualTime` active. Sửa: tạo publisher trong supplier.

**Ca 2 — chờ onNext trước khi advance time.** Test đặt `expectNext` ngay sau subscription khi interval chưa tới. Sửa: `thenAwait` hoặc explicit `clock.advanceTimeBy`.

**Ca 3 — chờ completion của infinite stream.** `Flux.interval` không complete. Sửa: `take(n)` nếu contract finite, hoặc `thenCancel`.

**Ca 4 — expectNoEvent trước expectSubscription.** Subscription cũng là event trong StepVerifier. Sửa: `expectSubscription().expectNoEvent(...)`.

**Ca 5 — có non-Reactor time source.** `Thread.sleep`, external Redis TTL, Java scheduler riêng không đổi theo virtual time. Sửa: inject time abstraction phù hợp hoặc test thật với bounded timeout.

**Ca 6 — custom Scheduler dùng trước setup.** Spring service singleton đã capture scheduler thật trước `withVirtualTime`. Sửa: inject VirtualTimeScheduler vào service test, hoặc tạo service sau setup.

**Ca 7 — quá nhiều immediate synchronous events.** Infinite recursion/interval zero scheduling có thể hog thread. Sửa: tránh zero-delay unbounded loops, `take` và giới hạn demand.

**Ca 8 — verifier không có real-time timeout.** Khi publisher fail to emit, test suite có thể đứng mãi. Sửa: `verify(Duration)`/CI timeouts, không lấy timeouts làm substitute for correct expectations.

**Ca 9 — virtual clock được advance từ wrong scheduler instance.** Code tạo nhiều VirtualTimeScheduler instances, operator dùng A mà test advance B. Sửa: pass **same instance** và keep ownership rõ.

**Ca 10 — test chạy concurrently.** Một test thay Schedulers factory global trong khi test khác dùng Reactor timers. Sửa: serialize virtual factory tests hoặc inject per-test scheduler.

## 23. Nguyên nhân WebTestClient SSE test fail

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| 404 trước khi đọc stream | Sai @RequestMapping/path | Kiểm route mapping |
| 406 Not Acceptable | Accept/media type không hợp | Dùng TEXT_EVENT_STREAM |
| 415 Unsupported Media Type | Request Content-Type không đúng | Cấu hình consumes/codec |
| 500 lúc context start | Thiếu service mock trong slice | @MockBean đúng type |
| SSE body không decode thành DTO | Codec/Jackson type mismatch | Kiểm DTO/serializer/returnResult |
| Test chờ completion vô hạn | Stream không complete | thenCancel, không expectBodyList |
| Flux events đến chậm | Scheduler/network/CI load | Tách service vTime test, giảm real test interval |
| Test pass slice, fail live HTTP | Netty/server/config/proxy khác | Kiểm RANDOM_PORT/response headers |
| 200 nhưng stream bị lỗi giữa chừng | HTTP headers đã commit | Kiểm onError và protocol framing |
| Client cancel nhưng server chưa cleanup | Async propagation | Test doFinally/metrics eventually |
| StepVerifier withVirtualTime treo HTTP | Không điều khiển toàn real server clock | Dùng create(responseBody) |
| Application dùng MVC thay WebFlux | Cả web starters, application type khác | Xác định đúng stack |
| Response buffering giữ dữ liệu | Codec/flush/proxy | Kiểm streaming media type |
| Mock service trả null | Mockito default Mono/Flux chưa stub | Trả Mono/Flux hợp lệ |
| Stream cứ chạy nền sau test | Subscription không cancel/dispose | thenCancel, lifecycle cleanup |
| Test fail chỉ khi suite parallel | Shared mocks/global scheduler/ports | Isolate, serialize hoặc refactor |

## 24. TestScheduler vs VirtualTimeScheduler vs Clock

`VirtualTimeScheduler` là implementation trong `reactor-test` dùng để điều khiển timed Reactor operations. Nó không tương đương `java.time.Clock.fixed`:

- `Clock.fixed(Instant, ZoneId)` kiểm *business timestamps*.
- `VirtualTimeScheduler` kiểm *khi nào reactive timer/operator chạy*.
- `TestPublisher` kiểm *upstream signal sequence*.
- `WebTestClient` kiểm *HTTP wire/codec behavior*.

Một ứng dụng có cả timestamp và interval có thể inject cả `Clock` và `Scheduler`. Test có thể advance scheduler mà `Instant.now()` vẫn giữ real wall time nếu code không dùng injected Clock; đó không phải bug của Reactor.

## 25. Retry, timeout và cancellation theo scope

Một retry policy có thể được mô hình hóa:

~~~text
Attempt 1 -> onError(transient) -> wait 1s
Attempt 2 -> onError(transient) -> wait 2s
Attempt 3 -> onNext(success) -> onComplete
~~~

Khi dùng virtual time, assertions nên kiểm tổng số attempts, thời điểm next attempt và terminal success/error. Nhưng business calls tới remote HTTP/DB vẫn cần mock/fake hoặc local test server; chỉ kiểm Scheduler không tự thay thế network.

Khi request bị client cancel:

~~~text
Client WebTestClient.cancel()
           |
           v
HTTP connection/response subscriber canceled
           |
           v
Server Flux subscription cancellation propagated
           |
           v
doFinally(CANCEL) / resource cleanup
~~~

Propagation có thể asynchronous. Không kiểm bằng sleep fixed hoặc assert synchronously trên server-side counter không được đồng bộ. Trong test service layer có thể dùng `doFinally(signalType -> ...)` và assert bằng StepVerifier; trong end-to-end HTTP cần bounded wait/metrics khi cleanup là requirement.

## 26. CI: giữ test nhanh và đáng tin

Phân ba nhóm:

1. **Pure reactive unit:** `FeedVirtualTimeTest`, `FeedServiceContractTest`, không tạo Spring context; thực thi nhanh và deterministic.
2. **WebFlux slice:** `FeedWebSliceTest`, tạo WebTestClient mock server và mock service; kiểm HTTP contract nhanh, không TCP.
3. **Full-context HTTP:** `FeedLiveHttpTest`, Netty trên random port; có wall-clock/IO nên chạy ít scenarios quan trọng.

Cấu hình Gradle dùng `useJUnitPlatform()`. Khi cần phân job PR vs integration, có thể thêm JUnit tags hoặc một `integrationTest` task, nhưng **đừng chạy cùng một test twice mà report đếm sai**. CI release gate phải kiểm JUnit XML thực sự có 17 tests, không coi `UP-TO-DATE` là test run mới.

### GitHub Actions snippet

~~~yaml
name: reactive-tests

on:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v4
      - name: Run all reactive tests
        run: ./gradlew test --rerun-tasks
      - name: Save JUnit reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: reactive-test-results
          path: |
            build/reports/tests/test/
            build/test-results/test/
          if-no-files-found: ignore
~~~

Đây là ví dụ workflow; trong production pin action commits theo supply-chain policy và dùng versions đang được hỗ trợ. Nếu random-port test chỉ fail trên shared CI runner, thu logs, JUnit XML, test duration và Netty bind exceptions trước khi tăng timeout vô hạn.

## 27. Bài tập mở rộng

**A.** Đổi virtual-time interval từ 2 giờ sang 7 ngày; kiểm kết quả không phải chờ wall-clock bảy ngày.

**B.** Tạo Flux.interval ngoài `withVirtualTime` supplier; lý giải vì sao test có thể giữ scheduler thật và sửa.

**C.** Bỏ `expectSubscription` trước `expectNoEvent` rồi xem verifier bắt signal gì.

**D.** Thay `thenAwait` bằng `expectNoEvent` ở giai đoạn không được phát signals và kiểm boundary.

**E.** Bỏ `take(count)` rồi giữ `verifyComplete`; giải thích lỗi test đúng và thiết kế cancellation.

**F.** Dùng explicit `VirtualTimeScheduler.create` cùng một instance cho service và test, dispose sau test.

**G.** Đổi service interval sang zero/negative và kiểm `Flux.error` bằng StepVerifier.

**H.** Thay `Flux.just` mock service bằng `Flux.never` trong WebFlux slice; dùng `thenCancel` đúng lúc.

**I.** Thêm endpoint `application/x-ndjson` với finite Flux; viết test WebTestClient.returnResult kiểm frame decode.

**J.** Viết @WebFluxTest với @MockBean service cho HTTP 404, kiểm ResponseStatusException mapping.

**K.** Viết full RANDOM_PORT test cho SSE và phân biệt nó với mocked WebFlux slice.

**L.** Đo startup time của slice vs full-context, không rút kết luận từ một sample trên máy shared CI.

**M.** Thêm `TestPublisher` để đẩy các events vào service; kiểm response sequence/error/cancellation.

**N.** Viết một retry policy với fixedDelay 1 ngày ảo, kiểm number of attempts và elapsed virtual time.

**O.** Mô phỏng timeout fallback bằng `Mono.never().timeout(Duration, fallback)` và kiểm fallback value.

**P.** Dùng `StepVerifier.create(Flux.range(1,5),0)` kiểm request(2), request(3), completion.

**Q.** Viết producer instrumentation với `doOnCancel`/`doFinally` và xác minh cancel từ subscriber trong service unit test.

**R.** Thêm `@RestControllerAdvice` để map validation errors/ResponseStatusException thành JSON contract rõ.

**S.** Chạy JUnit methods parallel trong branch sandbox; quan sát hazard khi hai tests dùng global virtual scheduler factory, sau đó dùng explicit scheduler injection.

**T.** Thêm Clock.fixed cho timestamp và VirtualTimeScheduler cho interval, chứng minh hai đồng hồ là hai dependencies.

**U.** Thử đổi media type SSE thành application/json, kiểm JSON array vs streaming semantics.

**V.** Đưa client qua real proxy/test gateway nếu production dùng SSE, kiểm buffering và disconnect propagation.

**W.** Tạo integration test với Testcontainers Kafka/Redis, phân biệt virtual retry timing và broker/wall-clock time.

**X.** Kiểm logs cho `onErrorDropped` hoặc network disconnected after cancel; đừng bỏ qua lỗi bị drop.

## 28. Checklist trước khi merge test reactive

- [ ] Test có mô tả assembly, subscription, onNext, terminal và cancellation?
- [ ] Mono/Flux có terminal behavior phù hợp assertion?
- [ ] Với virtual time, publisher được tạo lazy trong supplier?
- [ ] Nếu inject scheduler, test advance đúng instance?
- [ ] Có `expectSubscription` trước `expectNoEvent`?
- [ ] `thenAwait` và `expectNoEvent` được dùng đúng nghĩa?
- [ ] Không dùng `Thread.sleep` để giả lập thời gian reactive?
- [ ] Không coi `Clock.fixed` và VirtualTimeScheduler là một thứ?
- [ ] Không mặc định virtual scheduler điều khiển Netty/external HTTP server?
- [ ] Không dùng `verifyComplete` cho infinite SSE?
- [ ] Có `thenCancel` khi client chủ động dừng stream?
- [ ] Có verification timeout để tránh test treo?
- [ ] Test không dựa vào global Scheduler state giữa methods?
- [ ] Có cleanup/dispose scheduler do test tạo?
- [ ] Không dùng Schedulers.immediate cho timed positive test?
- [ ] Backpressure demand được kiểm khi là contract?
- [ ] `@WebFluxTest` đã có mocks cho ordinary services?
- [ ] `WebTestClient` kiểm route/status/media type/response body?
- [ ] SSE dùng `returnResult().getResponseBody()` thay expectBodyList vô hạn?
- [ ] Có positive finite stream và long-lived cancellation test?
- [ ] Có error-before-headers và error-after-commit strategy rõ?
- [ ] HTTP real-server tests dùng RANDOM_PORT, không hardcode port?
- [ ] Dùng Spring WebFlux stack, không nhầm với MVC?
- [ ] Media type content negotiation được kiểm?
- [ ] JSON codec/serializer đúng với DTO?
- [ ] Các stream test data không chứa secrets/PII?
- [ ] Test không gọi block() trên Reactor event-loop?
- [ ] Retry/backoff/timeout policy tests tách khỏi external network?
- [ ] JUnit test counts và results được xác nhận sau khi chạy thật?
- [ ] CI không che failed tests bằng UP-TO-DATE/cached output?
- [ ] Có JUnit reports khi failure và bounded CI job timeout?
- [ ] Không tăng timeout vô hạn để che race hoặc sai scheduler?

## 29. Tài liệu chính thức

- [Project Reactor — Testing Reactor Core](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, `TestPublisher`, post-execution assertions.
- [Project Reactor — Reactor 3 Reference Guide](https://docs.spring.io/projectreactor/reactor-core/docs/current/reference/html/): lazy supplier, expectNoEvent/thenAwait và giới hạn virtual time.
- [Reactor Test — StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): initial request, withVirtualTime, verify/timeouts.
- [Reactor Test — VirtualTimeScheduler API](https://projectreactor.io/docs/test/release/api/reactor/test/scheduler/VirtualTimeScheduler.html): advanceTimeBy và dispose.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bindToController, bindToServer, streaming FluxExchangeResult.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): Reactive HTTP dispatch và streaming.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @WebFluxTest, @MockBean, WebTestClient và random-port tests.
- [Reactive Streams specification](https://www.reactive-streams.org/): Subscription, request(n), cancel, terminal signals.
- [JUnit Jupiter User Guide](https://docs.junit.org/5.10.2/user-guide/): lifecycle, test isolation và parallel execution.
- [Gradle Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): JUnit Platform, filtering và test reports.

**Tổng kết:** Hãy dùng `StepVerifier.withVirtualTime` hoặc explicit `VirtualTimeScheduler` để kiểm logic delay/interval/timeout **mà không chờ wall-clock**, và dùng `WebTestClient` để kiểm HTTP WebFlux JSON/SSE thật ở đúng boundary. Với finite Flux, verify completion; với long-lived SSE, kiểm một số events rồi cancel. Không ép virtual clock điều khiển external server, không tạo publisher quá sớm, không để các tests cùng thao túng global Scheduler state và luôn phân biệt một JUnit test được thiết kế với kết quả đã chạy thực tế.

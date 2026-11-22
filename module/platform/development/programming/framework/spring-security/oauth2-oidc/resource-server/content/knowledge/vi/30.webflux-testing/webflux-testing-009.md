# Kiểm tra timeout, hủy và thao tác có chặn ngoài dự kiến

Trong **Spring Security OAuth 2.0 / OIDC Resource Server chạy trên WebFlux**, request thường được xử lý bằng các publisher Reactor như `Mono` và `Flux`. Một pipeline reactive chỉ thật sự an toàn khi nó xử lý đúng ba tình huống: **công việc mất quá nhiều thời gian (timeout), subscriber không còn cần kết quả (cancellation), và một đoạn code vô tình chặn thread (blocking)**.

Ba tình huống có liên quan nhưng không giống nhau:

- **Timeout:** một giới hạn thời gian được áp vào publisher hoặc một tầng I/O. Khi quá hạn, pipeline phát lỗi timeout hoặc chuyển sang fallback; operator thường hủy upstream.
- **Cancellation:** downstream chủ động báo không còn cần dữ liệu. Reactor truyền tín hiệu cancel ngược về upstream để các thành phần có thể dừng và giải phóng tài nguyên.
- **Blocking:** một thao tác đồng bộ giữ thread cho tới khi I/O hoặc tính toán kết thúc. Trong WebFlux, blocking trên event-loop có thể làm chậm đồng thời nhiều request khác.

Một ứng dụng có thể cấu hình timeout nhưng vẫn không hủy được công việc bên dưới; có thể nhận cancellation nhưng một thư viện JDBC cũ vẫn tiếp tục chạy; hoặc không có timeout nào hết hạn nhưng một lời gọi `block()` đã làm event-loop đứng lại. Vì vậy cần kiểm tra từng hành vi bằng **Reactor Test, StepVerifier, WebTestClient, TestPublisher, PublisherProbe và BlockHound**.

Bài học thuộc chương **Kiểm thử WebFlux**, sử dụng **Java 17+, Spring Boot 3.x, Spring Security 6.x và Project Reactor** làm bối cảnh. Trọng tâm là kiểm tra thời gian có thể tái lập, chứng minh upstream bị hủy, phát hiện blocking ngoài dự kiến và bảo đảm lỗi phụ thuộc xác thực không làm request được chấp nhận nhầm.

## 1. Mô hình xử lý reactive trong WebFlux

Một request đi qua WebFlux thường có dạng:

~~~text
HTTP request
    |
    v
WebFlux WebFilter chain
    |
    v
Spring Security WebFilter chain
    |
    +-- Bearer token authentication
    |      |
    |      +-- ReactiveJwtDecoder
    |      |
    |      +-- ReactiveOpaqueTokenIntrospector
    |
    v
Authorization
    |
    v
Controller returns Mono/Flux
    |
    v
Service -> WebClient / reactive database / other publisher
    |
    v
HTTP response
~~~

Controller thường trả publisher để framework subscribe và ghi response. Khi client disconnect hoặc response không còn được tiêu thụ, cancellation có thể được truyền xuống pipeline. Nếu ứng dụng tự gọi `subscribe()`, `block()` hoặc chuyển công việc sang một thread không được quản lý, luồng điều khiển này có thể bị phá vỡ.

### 1.1. Reactive không đồng nghĩa với không có thread

Reactor vẫn sử dụng threads và schedulers. Khác biệt là các thao tác I/O reactive thường không giữ một thread trong suốt thời gian chờ. Một event-loop thread có thể điều phối nhiều kết nối; nếu một request gọi blocking I/O trên thread đó, các request khác dùng cùng event loop cũng có thể bị chậm.

### 1.2. Ba tín hiệu kết thúc của publisher

Một publisher có thể kết thúc bằng:

| Tín hiệu | Ý nghĩa | Operator quan sát |
| --- | --- | --- |
| `onComplete` | Hoàn tất bình thường. | `doOnComplete`, `doFinally(ON_COMPLETE)` |
| `onError` | Kết thúc do lỗi. | `doOnError`, `doFinally(ON_ERROR)` |
| `cancel` | Subscriber không còn cần kết quả. | `doOnCancel`, `doFinally(CANCEL)` |

Cancellation **không phải** một `onError` được gửi tới subscriber. Khi subscriber hủy, nó không nhận giá trị hay lỗi kết thúc bình thường từ upstream; các hook quan sát cancellation dùng để cleanup và đo lường.

## 2. Phân biệt timeout, cancellation và blocking

~~~text
TIMEOUT
  Publisher vượt deadline
       |
       +-- timeout operator hủy upstream
       +-- downstream nhận TimeoutException hoặc fallback

CANCELLATION
  Client/subscriber không còn cần kết quả
       |
       +-- cancel truyền ngược upstream
       +-- cleanup có cơ hội chạy
       +-- downstream không nhận kết quả tiếp theo

BLOCKING
  Một đoạn code giữ thread để chờ
       |
       +-- event-loop không xử lý request khác
       +-- latency tăng, throughput giảm
       +-- có thể không phát sinh timeout đúng lúc
~~~

Timeout thường gây cancellation cho upstream, nhưng cancellation không nhất thiết là timeout: client có thể đóng kết nối sớm, `take(1)` có thể hủy nguồn sau phần tử đầu tiên, hoặc test chủ động gọi `thenCancel()`.

Blocking cũng không tự đồng nghĩa với timeout. Một thread có thể bị chặn 200 ms trong khi timeout là 5 giây; request vẫn trả kết quả nhưng đã gây latency cho các request khác.

## 3. Các tầng timeout cần kiểm tra riêng

Một request outbound từ WebFlux có thể chờ ở nhiều giai đoạn:

~~~text
Subscribe
   |
   v
DNS resolution
   |
   v
TCP connect
   |
   v
TLS handshake
   |
   v
Send request
   |
   v
Wait for response / read body
   |
   v
Decode response
   |
   v
Application processing
~~~

Một timeout tổng thể không thay thế mọi timeout ở tầng transport. Ngược lại, đặt nhiều timeout độc lập mà không hiểu quan hệ có thể làm request thất bại sớm hơn hoặc khó chẩn đoán.

| Timeout | Giới hạn | Ví dụ kiểm soát |
| --- | --- | --- |
| DNS/connect timeout | Thời gian tìm địa chỉ/kết nối TCP. | Resolver/HTTP connector configuration. |
| TLS handshake timeout | Thời gian hoàn tất TLS handshake. | TLS client connector policy. |
| Response/read timeout | Thời gian chờ response hoặc dữ liệu tiếp theo. | Reactor Netty `responseTimeout`. |
| Publisher timeout | Thời gian chờ signal từ `Mono` hoặc khoảng im lặng của `Flux`. | Reactor `timeout(Duration)`. |
| End-to-end deadline | Tổng thời gian use case được phép chạy. | Deadline được truyền qua các service layer. |
| Test verification timeout | Giới hạn thời gian test được phép chờ. | `StepVerifier.verify(Duration)`. |

**Test verification timeout không phải production timeout.** `verify(Duration.ofSeconds(2))` giúp test không treo vô hạn; nó không tự thêm timeout vào publisher khi ứng dụng chạy thật.

### 3.1. Mono.timeout và Flux.timeout

Với `Mono`, `timeout(Duration)` giới hạn thời gian chờ kết quả đầu tiên hoặc terminal signal. Với `Flux`, timeout có thể phát sinh nếu không có phần tử tiếp theo trong khoảng thời gian được cấu hình; đây là giới hạn khoảng im lặng giữa các phần tử, không nhất thiết là tổng thời lượng stream.

~~~java
Mono<Order> order =
    orderRepository.findById(orderId)
        .timeout(Duration.ofSeconds(2));

Flux<Event> events =
    eventRepository.findByOrderId(orderId)
        .timeout(Duration.ofSeconds(5));
~~~

Trong ví dụ thứ hai, một stream phát phần tử đều đặn có thể tồn tại lâu hơn 5 giây vì timeout được làm mới khi có tín hiệu theo semantics của operator. Nếu cần **deadline tổng thể**, hãy áp một deadline riêng cho toàn pipeline.

### 3.2. Timeout fallback

`timeout` có thể chuyển sang publisher dự phòng:

~~~java
Mono<Profile> profile =
    remoteProfileClient.fetch(userId)
        .timeout(
            Duration.ofSeconds(2),
            Mono.just(Profile.unavailable()));
~~~

Fallback chỉ phù hợp khi nghiệp vụ định nghĩa rõ kết quả thay thế. Với authentication, authorization hoặc dữ liệu nhạy cảm, **không dùng fallback tạo principal hoặc quyền mặc định** khi introspection/JWT verification timeout.

### 3.3. Retry có thể làm tăng tổng thời gian

~~~java
Mono<Response> response =
    remoteClient.call()
        .timeout(Duration.ofSeconds(2))
        .retry(2);
~~~

Đoạn trên có thể tạo nhiều lần thử, mỗi lần có timeout riêng. Tổng thời gian có thể lớn hơn 2 giây. Với thao tác có side effect, retry có thể gửi lệnh nhiều lần. Cần deadline tổng, retry budget, backoff, phân loại lỗi và idempotency key.

## 4. Cấu hình timeout cho WebClient/Reactor Netty

Một WebClient dùng Reactor Netty có thể cấu hình connect timeout và response timeout:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration
public class DownstreamHttpConfiguration {

    @Bean
    WebClient downstreamWebClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
            .option(
                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                2_000)
            .responseTimeout(Duration.ofSeconds(3));

        return builder
            .clientConnector(
                new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
~~~

`CONNECT_TIMEOUT_MILLIS` giới hạn việc thiết lập kết nối TCP; `responseTimeout` kiểm soát thời gian chờ response theo Reactor Netty. Tên gọi và phạm vi chi tiết cần đối chiếu với phiên bản Reactor Netty thực tế.

### 4.1. Thêm deadline cho một use case

~~~java
public Mono<OrderSummary> getOrderSummary(String orderId) {
    return orderClient.getOrder(orderId)
        .flatMap(order ->
            inventoryClient.getAvailability(order)
                .map(inventory ->
                    OrderSummary.from(order, inventory)))
        .timeout(Duration.ofSeconds(5));
}
~~~

Deadline publisher giới hạn thời gian tổng từ lúc subscribe tới kết quả của pipeline này. Nếu một request cần deadline chung xuyên qua nhiều service, nên truyền deadline/remaining budget qua các layer thay vì mỗi downstream tự đặt timeout dài hơn tổng SLA.

### 4.2. Không đặt timeout tùy tiện quanh toàn ứng dụng

Một timeout global quá thấp có thể làm hỏng download/streaming responses hợp lệ, Server-Sent Events, WebSocket, upload lớn, báo cáo có thời gian tính toán dài hoặc API có SLA khác nhau.

Chọn timeout theo endpoint/use case và loại I/O. Với stream dài, phân biệt **idle timeout** với **maximum session duration**.

## 5. Kiểm thử timeout bằng StepVerifier

`StepVerifier` cho phép mô tả những tín hiệu mong đợi từ publisher theo thứ tự. Khi kiểm tra timeout, nên dùng **virtual time** để test nhanh và ổn định, không phải chờ thật nhiều giây.

Dependency test:

~~~groovy
testImplementation 'io.projectreactor:reactor-test'
~~~

### 5.1. Test Mono timeout với virtual time

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutTests {

    @Test
    void emitsTimeoutWhenMonoDoesNotCompleteInTime() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                    .thenReturn("done")
                    .timeout(Duration.ofSeconds(3)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(1));
    }
}
~~~

Điểm quan trọng:

- Tạo publisher **bên trong supplier** của `withVirtualTime`.
- `thenAwait` tiến virtual clock mà không chờ thật 3 giây.
- `expectError` xác nhận timeout là kết quả của pipeline.
- `verify(Duration)` vẫn đặt giới hạn thật cho thời gian chạy test.

### 5.2. Vì sao phải tạo publisher trong supplier?

Không nên:

~~~java
Mono<Long> delayed = Mono.delay(Duration.ofSeconds(10));

StepVerifier.withVirtualTime(() ->
        delayed.timeout(Duration.ofSeconds(3)))
    .thenAwait(Duration.ofSeconds(3))
    .expectError(TimeoutException.class)
    .verify();
~~~

Một publisher hoặc scheduler được tạo trước khi virtual scheduler được cài có thể đã giữ scheduler thật. Tạo publisher trong supplier giúp các operator lấy scheduler sau khi virtual time đã được thiết lập.

### 5.3. Test fallback sau timeout

~~~java
@Test
void switchesToFallbackAfterTimeout() {
    StepVerifier.withVirtualTime(() ->
            Mono.delay(Duration.ofSeconds(10))
                .thenReturn("remote")
                .timeout(
                    Duration.ofSeconds(2),
                    Mono.just("cached")))
        .thenAwait(Duration.ofSeconds(2))
        .expectNext("cached")
        .verifyComplete();
}
~~~

Test này kiểm tra fallback nghiệp vụ. Nó không chứng minh fallback phù hợp bảo mật; với token authentication, fallback phải không tạo authenticated identity khi nguồn xác thực chưa phản hồi.

## 6. Test cancellation chủ động bằng StepVerifier

`thenCancel()` hủy subscription sau khi các bước trước đó hoàn thành:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CancellationTests {

    @Test
    void propagatesCancellationToSource() {
        AtomicBoolean cancelled = new AtomicBoolean();

        Mono<String> source = Mono.<String>never()
            .doOnCancel(() -> cancelled.set(true));

        StepVerifier.create(source)
            .expectSubscription()
            .thenCancel()
            .verify(Duration.ofSeconds(1));

        assertTrue(cancelled.get());
    }
}
~~~

Kết quả cần xác minh: subscriber đã subscribe, test phát cancel, `doOnCancel` được gọi và không có giá trị hoặc completion được phát sau cancellation.

### 6.1. Phân biệt doOnCancel và doFinally

~~~java
source
    .doOnCancel(() -> metrics.incrementCancel())
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            releaseCancellationResources();
        }
    });
~~~

- `doOnCancel` chạy khi subscription bị hủy.
- `doFinally` chạy khi publisher kết thúc bằng complete, error hoặc cancel.
- `doOnError` không chạy chỉ vì cancellation.
- `doOnSuccess` không phải hook cleanup cho mọi kiểu kết thúc.

Không đặt cleanup chỉ trong `doOnSuccess` nếu resource còn cần được giải phóng khi lỗi hoặc cancel.

## 7. Chứng minh timeout hủy upstream

Một test chỉ xác nhận `TimeoutException` chưa đủ. Cần kiểm tra nguồn upstream đã nhận cancellation.

`TestPublisher` có thể điều khiển tín hiệu của upstream:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class TimeoutCancellationTests {

    @Test
    void timeoutCancelsUpstream() {
        TestPublisher<String> upstream =
            TestPublisher.create();

        StepVerifier.withVirtualTime(() ->
                upstream.mono()
                    .timeout(Duration.ofSeconds(2)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(1));

        upstream.assertCancelled();
    }
}
~~~

Test này kiểm tra một hành vi quan trọng: khi timeout phát sinh, operator hủy source. Trong HTTP client thực tế, cancellation thường được truyền tới transport connector để hủy request/dispose exchange, nhưng mức độ dừng công việc phía server còn phụ thuộc giao thức và server xử lý request.

### 7.1. Test fallback được subscribe, source bị cancel

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;
import reactor.test.publisher.TestPublisher;

class TimeoutFallbackTests {

    @Test
    void cancelsSlowSourceAndSubscribesFallback() {
        TestPublisher<String> source = TestPublisher.create();
        PublisherProbe<String> fallback =
            PublisherProbe.of(Mono.just("fallback"));

        StepVerifier.withVirtualTime(() ->
                source.mono().timeout(
                    Duration.ofSeconds(1),
                    fallback.mono()))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("fallback")
            .verifyComplete();

        source.assertCancelled();
        fallback.assertWasSubscribed();
    }
}
~~~

`PublisherProbe` xác nhận nhánh fallback thật sự được subscribe. Đây là cách kiểm tra control flow tốt hơn việc chỉ nhìn giá trị cuối cùng khi nhiều nhánh có thể trả cùng kết quả.

## 8. Cancellation không đồng nghĩa rollback

~~~text
Client gửi POST /payments
        |
        v
WebFlux service gửi lệnh tới Payment Provider
        |
        v
Provider đã nhận và xử lý lệnh
        |
        v
Client đóng kết nối / publisher bị cancel
        |
        v
Ứng dụng ngừng chờ kết quả

Nhưng payment có thể đã được thực hiện.
~~~

Cancellation là tín hiệu điều khiển luồng. Nó không tự đảo ngược side effect đã commit ở database hoặc hệ thống remote.

Với thao tác có side effect:

- Dùng idempotency key để retry không tạo giao dịch trùng.
- Lưu trạng thái operation để truy vấn kết quả khi client disconnect.
- Dùng transaction/outbox/saga và compensation khi nghiệp vụ cần.
- Phân biệt “client không nhận response” với “server chưa thực hiện”.
- Không báo giao dịch thất bại chỉ vì subscriber bị hủy.

### 8.1. Cancellation có thể đến sau khi side effect đã bắt đầu

~~~java
return paymentClient.createPayment(command)
    .timeout(Duration.ofSeconds(2));
~~~

Timeout có thể hủy publisher client và ngừng chờ. Payment provider vẫn có thể đã nhận request, hoặc xử lý xong nhưng response đến trễ. Cần idempotency key và API truy vấn trạng thái để xác định kết quả cuối.

### 8.2. Cancellation propagation phụ thuộc từng nguồn

| Upstream | Khả năng khi nhận cancel |
| --- | --- |
| `Mono.delay` | Hủy timer. |
| Reactor Netty HTTP exchange | Có thể dispose/cancel exchange; remote server có thể đã nhận request. |
| Reactive database driver | Có thể gửi cancellation tới database nếu driver hỗ trợ. |
| JDBC qua `boundedElastic` | Hủy subscriber không đảm bảo thread/JDBC statement dừng ngay. |
| `Mono.fromFuture` | Hành vi phụ thuộc future và cách bridge/cancel. |
| Custom publisher | Phụ thuộc implementation có xử lý cancel và cleanup đúng không. |

Không tuyên bố một thao tác đã dừng chỉ vì `doOnCancel` chạy ở lớp ngoài. Muốn bảo đảm, cần kiểm tra behavior của driver/connector cụ thể và quan sát resource thật.

## 9. Kiểm tra cleanup khi cancellation xảy ra

Khi publisher quản lý resource như file, stream, cursor hoặc connection, cần cleanup cho mọi đường kết thúc:

~~~java
Flux<DataBuffer> body = downloadClient.fetch()
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            metrics.incrementDownloadCancelled();
        }
    });
~~~

Với resource lifecycle phức tạp, ưu tiên Reactor resource operators như `using`/`usingWhen` theo API và driver phù hợp, để cleanup gắn với complete/error/cancel. Không tự giữ resource trong field dùng chung rồi trông chờ `doOnSuccess` đóng nó.

### 9.1. Test cleanup

~~~java
@Test
void releasesResourceWhenSubscriberCancels() {
    AtomicBoolean released = new AtomicBoolean();

    Mono<String> work = Mono.<String>never()
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                released.set(true);
            }
        });

    StepVerifier.create(work)
        .thenCancel()
        .verify(Duration.ofSeconds(1));

    assertTrue(released.get());
}
~~~

Test trên xác nhận hook cleanup được gọi. Với connection/cursor/file thật, hãy test trạng thái resource tương ứng, ví dụ connection được trả về pool hoặc file handle đã đóng.

### 9.2. Discarded elements

Một số operator có thể loại bỏ phần tử đã được request nhưng không còn được downstream sử dụng khi cancel/error/race. Với resource nằm trong element (ví dụ buffer cần release), tìm hiểu `doOnDiscard` và quy tắc ownership của operator. Chỉ release đối tượng mà pipeline sở hữu; release hai lần hoặc release buffer còn được consumer dùng cũng gây lỗi.

## 10. Phát hiện blocking bằng BlockHound

**BlockHound** là công cụ phát hiện blocking calls trên các thread được đánh dấu non-blocking, thường hữu ích với Reactor event-loop/scheduler.

Dependency test:

~~~groovy
testImplementation 'io.projectreactor.tools:blockhound'
~~~

Cài BlockHound một lần trong test JVM, theo hướng dẫn của version đang dùng:

~~~java
import org.junit.jupiter.api.BeforeAll;
import reactor.blockhound.BlockHound;

class ReactiveBlockingTests {

    @BeforeAll
    static void installBlockHound() {
        BlockHound.install();
    }
}
~~~

BlockHound cần instrumentation của JVM và có thể yêu cầu cấu hình test runtime phù hợp với JDK/agent. Cài một lần cho test process; không gọi install lặp lại ở mỗi test class nếu suite dùng chung JVM.

### 10.1. Một blocking operation trên parallel scheduler

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> bad = Mono.fromCallable(() -> {
        Thread.sleep(20);
        return "done";
    })
    .subscribeOn(Schedulers.parallel());
~~~

Với BlockHound, lời gọi `Thread.sleep` trên non-blocking scheduler có thể bị phát hiện và ném `BlockingOperationError`. Test nên xác nhận blocking không xuất hiện ở các luồng ứng dụng được bảo vệ.

Không nên viết test chỉ để chứng minh `Thread.sleep` bị chặn rồi coi đó là toàn bộ coverage. Cần cài BlockHound và chạy các đường service thực tế có nguy cơ gọi JDBC, filesystem hoặc legacy SDK.

### 10.2. Dời blocking API sang boundedElastic

~~~java
public Mono<Customer> findCustomer(String id) {
    return Mono.fromCallable(() ->
            legacyJdbcRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`boundedElastic` được thiết kế để cô lập công việc blocking có giới hạn. Nó không biến JDBC thành non-blocking và cũng không làm query tự hủy được khi subscriber cancel. Cần giới hạn concurrency, timeout ở JDBC/driver và kiểm soát pool size.

### 10.3. Không dùng parallel cho blocking I/O

`Schedulers.parallel()` dành cho công việc CPU-bound ngắn. Dùng nó cho `Thread.sleep`, JDBC hoặc file I/O có thể làm nghẽn worker thread. Với blocking bridge, dùng `boundedElastic` hoặc executor chuyên biệt có capacity limit.

## 11. Những thao tác blocking thường bị bỏ sót

Không chỉ `Thread.sleep` mới là blocking:

- `Mono.block()` / `Flux.blockFirst()` / `blockLast()`.
- JDBC/JPA repository đồng bộ.
- `RestTemplate` hoặc HTTP client đồng bộ.
- `Files.readAllBytes`, `InputStream.read` và filesystem operations.
- `Future.get()` / `CompletableFuture.join()` khi chờ kết quả.
- `CountDownLatch.await()` / `Semaphore.acquire()`.
- Synchronized lock hoặc monitor contention kéo dài.
- SDK bên thứ ba dùng synchronous network I/O.
- Logging appender đồng bộ chậm hoặc ghi ra filesystem/network.
- JSON/XML processing quá nặng hoặc CPU-bound trên event loop.

Không phải mọi phép tính đều blocking I/O, nhưng phép tính CPU nặng trên event-loop cũng chiếm thread và gây starvation. Với công việc CPU-bound lớn, dùng scheduler/executor riêng có giới hạn và benchmark.

### 11.1. Không gọi block trong controller/service reactive

~~~java
// KHÔNG LÀM.
public Mono<Order> getOrder(String id) {
    Order order = orderRepository.findById(id).block();
    return Mono.just(order);
}
~~~

Thay bằng:

~~~java
public Mono<Order> getOrder(String id) {
    return orderRepository.findById(id);
}
~~~

Nếu repository là JDBC đồng bộ, hãy cô lập qua `fromCallable(...).subscribeOn(boundedElastic())` và cân nhắc chuyển sang reactive driver nếu workload yêu cầu non-blocking end-to-end.

### 11.2. Không tự subscribe trong service

~~~java
// KHÔNG LÀM.
public Mono<Void> sendNotification(Event event) {
    notificationClient.send(event).subscribe();
    return Mono.empty();
}
~~~

`subscribe()` tạo một subscription tách khỏi publisher mà controller/framework đang quản lý. Caller có thể nhận response trước khi notification hoàn tất; cancellation, error handling, tracing và security context propagation không còn nằm trong cùng lifecycle.

Thay bằng:

~~~java
public Mono<Void> sendNotification(Event event) {
    return notificationClient.send(event);
}
~~~

Nếu notification là side effect cần chạy độc lập sau khi request hoàn tất, hãy đưa vào queue/outbox/background worker có lifecycle và retry policy riêng; đừng tạo detached subscription tùy tiện.

## 12. Reactive Security: không block khi lấy SecurityContext

Trong WebFlux, SecurityContext được truyền qua **Reactor Context**. Không dùng `SecurityContextHolder.getContext()` theo cách ThreadLocal của Servlet trong reactive pipeline.

Có thể lấy principal bằng:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(Authentication::getName);
}
~~~

ThreadLocal không tự theo mọi thread switch của Reactor. Dùng `ReactiveSecurityContextHolder` và giữ việc truy cập trong reactive chain.

### 12.1. Không biến timeout xác thực thành authenticated fallback

Giả sử Resource Server dùng opaque token introspection. Nếu AS timeout, pipeline không có bằng chứng token active. Không viết:

~~~java
// KHÔNG LÀM.
introspector.introspect(token)
    .timeout(Duration.ofSeconds(2))
    .onErrorResume(error ->
        Mono.just(defaultAuthenticatedPrincipal()));
~~~

Đây là fail-open authentication. Lỗi timeout phải được giữ là lỗi xác thực/phụ thuộc, hoặc map thành lỗi dịch vụ theo error contract; tuyệt đối không tạo principal/quyền mặc định.

## 13. Timeout cho reactive JWT decoder và opaque introspection

Spring Security WebFlux sử dụng reactive interfaces:

- `ReactiveJwtDecoder` trả `Mono<Jwt>`.
- `ReactiveOpaqueTokenIntrospector` trả `Mono<OAuth2AuthenticatedPrincipal>`.

Nếu có yêu cầu timeout cụ thể cho bước xác thực, có thể bọc publisher:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import reactor.core.publisher.Mono;

public final class BoundedJwtDecoder
        implements ReactiveJwtDecoder {

    private final ReactiveJwtDecoder delegate;
    private final Duration timeout;

    public BoundedJwtDecoder(
            ReactiveJwtDecoder delegate,
            Duration timeout) {
        this.delegate = delegate;
        this.timeout = timeout;
    }

    @Override
    public Mono<Jwt> decode(String token) {
        return delegate.decode(token)
            .timeout(timeout);
    }
}
~~~

Tương tự với introspector:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class BoundedOpaqueIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final Duration timeout;

    public BoundedOpaqueIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            Duration timeout) {
        this.delegate = delegate;
        this.timeout = timeout;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(
            String token) {
        return delegate.introspect(token)
            .timeout(timeout);
    }
}
~~~

Đây là decorator minh họa. Trong production, cần chọn timeout phù hợp với SLA của AS, phân biệt timeout với token inactive, đo latency và xử lý upstream error có chủ đích. Không dùng `onErrorResume` để biến timeout thành active principal.

### 13.1. Authentication timeout khác invalid token

| Kết quả | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| JWT signature/claims sai | Token không hợp lệ. | Authentication thất bại. |
| Introspection trả `active:false` | AS không chấp nhận token. | Authentication thất bại. |
| Introspection timeout | Không xác minh được trạng thái. | Fail closed; ghi nhận dependency timeout. |
| JWKS fetch timeout | Chưa lấy/refresh được signing key cần thiết. | Không chấp nhận token bằng cách bỏ signature check. |
| Token hợp lệ, thiếu scope | Authentication thành công, authorization không đủ. | 403 theo policy. |

HTTP status cho dependency timeout phụ thuộc exception translation và error contract của ứng dụng. Có thể chọn response 5xx/503 để biểu đạt AS unavailable, trong khi invalid token là 401; cần cấu hình và test cụ thể. Điều không được thay đổi là **timeout không bao giờ được coi là bằng chứng token hợp lệ**.

## 14. Kiểm thử Reactive Resource Server bằng WebTestClient

`WebTestClient` kiểm tra ứng dụng WebFlux qua HTTP abstraction. Có thể bind vào application context và áp Spring Security test support:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.beans.factory.annotation.Autowired;

@SpringBootTest
class OrdersWebFluxTests {

    @Autowired
    WebTestClient webTestClient;
}
~~~

Khi tự dựng client từ application context, áp `springSecurity()` theo hướng dẫn Spring Security reactive test support. Nếu dùng test auto-configuration, xác nhận security filter chain thật đã được gắn vào test client.

### 14.1. Test authorization bằng mockJwt

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

webTestClient.mutateWith(
        mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

`mockJwt()` tạo một JWT Authentication giả cho test. Nó hữu ích để kiểm tra controller/authorization rules, nhưng **bỏ qua việc xác minh chữ ký, timestamp, issuer và audience bằng decoder thật**.

### 14.2. Test opaque token authorization

Reactive Security test support có thể cung cấp mock opaque-token authentication:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;

webTestClient.mutateWith(mockOpaqueToken())
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

Helper này kiểm tra behavior sau khi đã có Authentication test; nó không gọi Authorization Server introspection. Để kiểm tra timeout introspection, cần test decoder/introspector thật hoặc một stub reactive có thể điều khiển.

### 14.3. Phân biệt test authentication với test timeout

| Công cụ | Điều nó kiểm tra tốt | Điều không tự chứng minh |
| --- | --- | --- |
| `mockJwt()` | Authorization theo JWT principal/authorities. | Signature/time validation của decoder. |
| `mockOpaqueToken()` | Authorization với opaque principal giả. | HTTP introspection và `active` response. |
| `StepVerifier` | Publisher signals, timeout, cancel. | Toàn bộ HTTP/TLS stack. |
| `WebTestClient` | HTTP response/filter/controller integration. | Blocking ở mọi thread nếu không có BlockHound. |
| BlockHound | Blocking calls trên non-blocking threads. | Business correctness và token policy. |
| Live server + HTTP client | Connection lifecycle, disconnect, transport behavior. | Mọi race condition trong production. |

## 15. Test timeout của reactive authentication

Có thể stub `ReactiveJwtDecoder` trả publisher không bao giờ phát signal:

~~~java
ReactiveJwtDecoder slowDecoder = token -> Mono.never();
ReactiveJwtDecoder boundedDecoder =
    new BoundedJwtDecoder(
        slowDecoder,
        Duration.ofMillis(100));
~~~

Khi request protected tới với Bearer token, test cần xác nhận request không nhận authenticated principal, protected controller không được gọi, timeout được ghi nhận riêng với invalid-token result, không có fallback tạo user/authority và response theo error contract đã định nghĩa.

Với opaque introspector, dùng `Mono.never()` tương tự. Có thể dùng `TestPublisher` để chủ động hoàn tất, lỗi hoặc không phát tín hiệu.

### 15.1. Test bằng TestPublisher

~~~java
TestPublisher<Jwt> decoderResult = TestPublisher.create();

ReactiveJwtDecoder decoder =
    token -> decoderResult.mono();

// Trong test, subscribe request rồi điều khiển decoderResult:
// - next(jwt) để trả JWT
// - error(exception) để mô phỏng lỗi
// - giữ im lặng để timeout
~~~

Khi test timeout bằng virtual time, bảo đảm timeout operator dùng scheduler được virtual-time test kiểm soát. Với full WebTestClient integration, có thể test phần decoder riêng bằng StepVerifier trước, sau đó có một integration test HTTP với timeout thực ngắn và rõ ràng.

## 16. Test không có blocking ngoài dự kiến

Một test suite thực tế có thể cài BlockHound một lần, chạy service publisher trên scheduler đúng như runtime, gọi endpoint qua WebTestClient, bao phủ đường đi JWT decode/introspection và downstream WebClient, xác nhận không có blocking error, và với legacy blocking adapter thì xác nhận nó chạy trên `boundedElastic`/executor được phép.

~~~java
Mono<String> safeLegacyCall =
    Mono.fromCallable(() -> legacyClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
~~~

Test nên xác nhận giá trị/kết quả và scheduler isolation theo thiết kế. Không whitelist rộng toàn bộ package ứng dụng trong BlockHound để làm test xanh; nếu một thư viện thực sự cần allowlist, ghi rõ lý do và giới hạn phạm vi.

### 16.1. BlockHound có thể cần cấu hình runtime

BlockHound instrument bytecode để phát hiện blocking. Một số JDK/build/test runner có yêu cầu về agent/instrumentation. Nếu cài không thành công, đó là lỗi cấu hình test runtime; không kết luận ứng dụng không có blocking.

## 17. Event-loop starvation và dấu hiệu nhận biết

Triệu chứng có thể gồm latency tăng đồng loạt trên nhiều endpoint dù downstream không tăng tải, CPU không cao nhưng event-loop pending tasks tăng, một request dùng JDBC/blocking SDK khiến nhiều request khác chậm theo, timeout xảy ra hàng loạt ở các request không liên quan, throughput giảm mạnh khi concurrency tăng, hoặc thread dump cho thấy `reactor-http-nio-*` đang chờ I/O đồng bộ, lock hoặc `Future.get()`.

### 17.1. Phân biệt downstream chậm với event-loop bị block

| Quan sát | Downstream chậm | Event-loop bị block |
| --- | --- | --- |
| Một downstream cụ thể có latency cao | Thường có | Có thể không |
| Nhiều endpoint độc lập cùng chậm | Ít khả năng | Có thể |
| Thread dump event-loop đang chờ đồng bộ | Không nhất thiết | Dấu hiệu mạnh |
| BlockHound phát hiện blocking | Không nhất thiết | Có thể |
| Tăng event-loop threads là giải pháp | Không bền vững | Không sửa nguyên nhân gốc |

Không tăng event-loop thread count hoặc timeout để che một blocking call chưa được xử lý.

## 18. Cancellation khi client disconnect

Khi client đóng kết nối trước khi response hoàn tất, server có thể nhận được cancellation/disconnect và hủy pipeline đang xử lý. Hành vi cụ thể phụ thuộc server connector, protocol và vị trí request đang chạy.

Một test integration có thể dùng live Reactor Netty server và HTTP client để gửi request tới endpoint trả `Flux` chậm, đọc một phần response hoặc đóng connection, xác nhận server-side publisher quan sát cancellation, xác nhận cleanup/resource release và kiểm tra không còn background task chạy ngoài ý muốn.

`WebTestClient` phù hợp cho phần lớn HTTP contract tests, nhưng một số hành vi socket disconnect cần **live server và client thật** để mô phỏng chính xác.

### 18.1. Stream dài

~~~java
public Flux<ServerSentEvent<String>> streamEvents() {
    return eventPublisher.events()
        .map(value ->
            ServerSentEvent.builder(value).build())
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                metrics.incrementStreamCancelled();
            }
        });
}
~~~

Khi client đóng stream, cleanup cần được kích hoạt. Đừng dùng một timeout tổng ngắn cho SSE/WebSocket nếu nghiệp vụ yêu cầu kết nối dài; dùng idle timeout, heartbeat và maximum lifetime riêng.

## 19. Cancellation, flatMap và công việc song song

`flatMap` có thể subscribe nhiều inner publishers. Khi downstream cancel, Reactor truyền cancellation tới các inner subscriptions mà operator quản lý. Nhưng nếu inner task đã gọi API đồng bộ hoặc tự detach bằng `subscribe()`, nó có thể tiếp tục chạy.

~~~java
Mono<List<InventoryItem>> result =
    Flux.fromIterable(skus)
        .flatMap(inventoryClient::findBySku, 8)
        .collectList()
        .timeout(Duration.ofSeconds(3));
~~~

Ở đây concurrency được giới hạn 8. Khi timeout, Reactor có thể cancel inner publishers; transport/client cần hỗ trợ cancellation để dừng I/O tương ứng. Với thao tác ghi dữ liệu hoặc remote side effects, vẫn cần idempotency và trạng thái nghiệp vụ.

### 19.1. Concurrency limit không phải timeout

`flatMap(..., concurrency)` giới hạn số inner publishers chạy đồng thời, không giới hạn thời gian mỗi publisher. Cần kết hợp concurrency limit, timeout per-call/deadline tổng, backpressure strategy, connection pool limits và cancellation cleanup.

## 20. Error handling khi timeout

Timeout thường phát `TimeoutException`. Có thể map thành domain error:

~~~java
Mono<Order> order =
    orderClient.getOrder(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorMap(
            TimeoutException.class,
            error -> new DownstreamUnavailableException(
                "Orders service timed out", error));
~~~

Không bắt mọi lỗi rồi trả `Mono.empty()`:

~~~java
// KHÔNG LÀM.
source.onErrorResume(error -> Mono.empty());
~~~

Điều này che lỗi timeout, lỗi xác thực và lỗi lập trình, khiến API có thể trả response thành công nhưng thiếu dữ liệu hoặc bỏ qua một bước bảo mật.

### 20.1. Phân loại lỗi

| Nhóm | Ví dụ | Xử lý |
| --- | --- | --- |
| Authentication invalid | JWT signature sai, introspection inactive. | 401 theo security contract. |
| Authorization denied | Thiếu scope/role. | 403. |
| Dependency timeout | AS introspection/downstream không phản hồi. | Fail closed; response 5xx/503 theo contract. |
| Dependency unavailable | Connection refused, DNS, 5xx. | Retry có giới hạn nếu an toàn; nếu không thì fail. |
| Client cancellation | Caller đóng kết nối. | Cleanup; không coi như business failure thông thường. |
| Application bug | NPE, mapping sai. | Error path và alert; không fallback thành success. |

### 20.2. Không retry mọi timeout

Timeout có thể xảy ra sau khi remote side effect đã được thực hiện. Trước khi retry, cần biết operation có idempotent không, có idempotency key không, remote service có status query không, retry có làm nhân đôi giao dịch không và deadline còn đủ không.

Với introspection không tạo side effect nghiệp vụ, retry vẫn phải có budget vì tăng tải AS và có thể làm auth latency xấu hơn.

## 21. Test deadline và retry tổng thể

Giả sử mỗi lần gọi downstream có timeout 2 giây và retry tối đa hai lần. Nếu không có deadline tổng, request có thể kéo dài đáng kể:

~~~text
Attempt 1: up to 2s
Backoff:   200ms
Attempt 2: up to 2s
Backoff:   400ms
Attempt 3: up to 2s
-------------------
Total:     > 6s
~~~

Một deadline tổng giúp bảo đảm request không vượt SLA:

~~~java
Mono<Result> operation =
    callDownstream()
        .timeout(Duration.ofSeconds(2))
        .retryWhen(
            Retry.backoff(1, Duration.ofMillis(100))
                .filter(this::isTransient))
        .timeout(Duration.ofSeconds(3));
~~~

Timeout ngoài cùng đặt giới hạn tổng cho publisher. Cần tính backoff và cancellation của lần gọi đang chạy khi deadline ngoài hết hạn.

### 21.1. Test virtual time cho retry/backoff

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> callCounter.incrementAndGet() < 2
                ? Mono.error(new IOException("temporary"))
                : Mono.just("ok"))
            .retryWhen(
                Retry.backoff(1, Duration.ofSeconds(1))))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext("ok")
    .verifyComplete();
~~~

Publisher được tạo trong supplier để retry/backoff scheduler sử dụng virtual time. Trong test thực tế, giới hạn retry, phân loại exception và deadline ngoài cùng cũng cần được kiểm tra.

## 22. Test cancellation race và thời gian

Các race thường xuất hiện khi timeout xảy ra cùng lúc upstream phát value, client disconnect khi response gần hoàn tất, nhiều requests cùng hủy một shared publisher, retry bắt đầu đúng lúc deadline tổng hết hạn hoặc cache hit hoàn tất đồng thời với cancellation.

Không nên viết assertion phụ thuộc một thứ tự thread ngẫu nhiên. Dùng `TestPublisher`, `PublisherProbe`, virtual time hoặc synchronization primitive chỉ ở test harness và không block event-loop.

### 22.1. Kiểm tra nguồn không tiếp tục phát sau cancel

~~~java
TestPublisher<Integer> source = TestPublisher.create();
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Integer> values = source.flux()
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(values)
    .expectSubscription()
    .thenCancel()
    .verify(Duration.ofSeconds(1));

assertTrue(cancelled.get());
source.assertCancelled();
~~~

### 22.2. Không dùng sleep trong test reactive

Tránh:

~~~java
Thread.sleep(1000);
assertTrue(cancelled.get());
~~~

`Thread.sleep` làm test chậm và dễ flaky. Dùng StepVerifier, virtual time, TestPublisher hoặc synchronization ở test harness.

## 23. WebFlux security test matrix

Với Resource Server reactive, timeout/cancellation/blocking tests nên bao phủ cả authentication pipeline:

| Kịch bản | Kết quả cần xác nhận |
| --- | --- |
| JWT hợp lệ, decoder phản hồi nhanh | Request authenticated và authorization đúng. |
| JWT expired/nbf trong tương lai | Authentication thất bại. |
| ReactiveJwtDecoder không phát signal | Timeout; controller protected không chạy. |
| Opaque introspection active=false | 401 theo contract. |
| Opaque introspection timeout | Fail closed; không tạo principal fallback. |
| JWKS fetch/refresh timeout | Không bỏ qua signature validation. |
| Token hợp lệ nhưng thiếu scope | 403. |
| Downstream WebClient timeout | Lỗi dependency được phân loại. |
| Request bị cancel trong downstream call | Upstream được cancel nếu connector hỗ trợ. |
| Client disconnect trong stream | Cleanup được gọi. |
| JDBC/legacy call trên event loop | BlockHound phát hiện. |
| JDBC/legacy call trên boundedElastic | Không block event loop; concurrency vẫn có giới hạn. |
| Service tự gọi subscribe | Test/inspection phát hiện detached lifecycle. |
| Timeout fallback | Chỉ dùng fallback nghiệp vụ đã cho phép, không tạo identity/quyền. |
| Retry sau timeout | Không lặp side effect hoặc vượt deadline tổng. |

## 24. Quan sát trong production

Các metrics có ích:

- Request latency theo endpoint.
- Timeout count theo dependency/operation.
- Authentication latency (JWT decode, JWKS, introspection).
- Cancellation count theo route/downstream.
- Active subscriptions/streams và số connection đang mở.
- WebClient connection pool pending acquire, active connections và errors.
- Retry attempts, retry exhaustion và total deadline exceeded.
- Event-loop pending tasks/latency và scheduler queue depth.
- Blocking detector/test findings.

Không đưa raw Access Token, Refresh Token, Authorization header, claims nhạy cảm hoặc URL query chứa secret vào metrics/logs/traces.

### 24.1. Phân biệt timeout với cancellation trong telemetry

Một timeout operator thường tạo `TimeoutException` ở downstream và cancel upstream. Nếu chỉ đếm cancellation, không biết nguyên nhân là deadline, client disconnect hay `take()`; nếu chỉ đếm timeout, có thể không biết upstream cleanup có thành công. Ghi riêng timeout phát sinh ở tầng nào, cancellation reason nếu ứng dụng biết, dependency/route và cleanup/connection release outcome.

Không dùng raw token hoặc user identifier làm metric label có cardinality cao.

## 25. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ timeout tự rollback remote work. | Side effect có thể đã commit. | Idempotency, status query, compensation. |
| Chỉ test TimeoutException. | Không biết upstream có bị cancel. | Assert cancellation bằng TestPublisher. |
| Dùng thời gian thật cho mọi timeout test. | Chậm và flaky. | StepVerifier virtual time. |
| Tạo publisher trước `withVirtualTime`. | Operator có thể dùng scheduler thật. | Tạo publisher trong supplier. |
| Dùng `verify(Duration)` như production timeout. | Pipeline runtime vẫn có thể chờ lâu. | Thêm timeout operator/transport config. |
| Dùng `Thread.sleep` trong test. | Chậm, flaky, blocking. | Virtual time và publisher probes. |
| Dùng `block()` trên event-loop. | Starvation nhiều request. | Giữ pipeline reactive. |
| Gọi `subscribe()` trong service. | Detached work, mất cancellation/error propagation. | Trả publisher cho caller. |
| Dùng JDBC trực tiếp trong reactive chain. | Block event-loop. | Reactive driver hoặc boundedElastic bridge. |
| Chạy blocking I/O trên parallel scheduler. | Nghẽn CPU workers. | boundedElastic/executor chuyên biệt. |
| Coi cancellation là `onError`. | Cleanup/metrics sai. | `doOnCancel`/`doFinally(CANCEL)`. |
| Coi cancellation bảo đảm database query dừng. | Driver có thể tiếp tục chạy. | Kiểm tra driver cancellation thực tế. |
| Fallback khi introspection timeout thành active principal. | Fail-open authentication. | Fail closed. |
| Retry mọi timeout. | Duplicate side effects và tăng latency. | Retry transient/idempotent với budget. |
| Dùng timeout tổng ngắn cho SSE/WebSocket. | Stream hợp lệ bị ngắt. | Idle timeout và session policy riêng. |
| Whitelist rộng trong BlockHound. | Che blocking trong ứng dụng. | Allowlist hẹp, có lý do. |

## 26. Quy trình kiểm thử đề xuất

1. **Test publisher ở service layer:** dùng StepVerifier kiểm tra success, error, timeout và cancellation.
2. **Dùng virtual time:** kiểm tra delay, timeout, retry/backoff mà không chờ đồng hồ thật.
3. **Assert upstream cancellation:** TestPublisher và `assertCancelled()`.
4. **Kiểm tra fallback branch:** PublisherProbe xác nhận fallback được subscribe.
5. **Cài BlockHound:** chạy các service reactive và phát hiện blocking trên non-blocking threads.
6. **Kiểm tra blocking bridge:** xác nhận JDBC/legacy calls chạy trên boundedElastic/executor có giới hạn.
7. **Test WebFlux HTTP:** WebTestClient + Spring Security test support cho 401/403/response contract.
8. **Test authentication dependency:** stub ReactiveJwtDecoder/ReactiveOpaqueTokenIntrospector chậm, lỗi hoặc inactive.
9. **Test transport thật:** live server/client để kiểm tra disconnect, connection disposal và stream cancellation.
10. **Test side effects:** xác minh idempotency/status khi cancellation đến sau khi remote operation đã bắt đầu.
11. **Kiểm tra telemetry:** timeout, cancel, dependency error và blocking được phân biệt.
12. **Giữ test deterministic:** không phụ thuộc sleep, wall-clock timing hoặc thứ tự thread không được kiểm soát.

**Ghi nhớ:** `timeout` đặt giới hạn và thường cancel upstream; `cancel` là tín hiệu subscriber không còn cần kết quả; blocking giữ thread và có thể làm nghẽn event-loop. Dùng **StepVerifier với virtual time** để kiểm tra timeout, **TestPublisher/PublisherProbe** để chứng minh cancellation và nhánh fallback, **WebTestClient** để kiểm tra HTTP/Security chain, và **BlockHound** để phát hiện blocking. Cancellation không tự rollback side effect, `verify(Duration)` không phải production timeout, và timeout của JWT/opaque introspection phải **fail closed**, không tạo Authentication khi chưa xác minh được token.

## Tài liệu tham khảo

- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html).
- [Project Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- [Project Reactor — Scheduler and Threading Model](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html).
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Reactor Test — StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html).
- [Reactor Test — TestPublisher API](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html).
- [Reactor Test — PublisherProbe API](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html).
- [BlockHound](https://github.com/reactor/BlockHound).
- [Spring Framework — WebFlux Testing](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html).
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html).
- [Spring Security — Reactive OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html).
- [Reactor Netty — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html).

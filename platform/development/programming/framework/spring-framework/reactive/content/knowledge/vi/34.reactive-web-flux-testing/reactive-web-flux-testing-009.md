# Giới hạn những gì kiểm thử giả lập chứng minh về mạng và backpressure trong Spring WebFlux

## 1. Mục tiêu

Một bài kiểm thử WebFlux có thể xanh nhưng ứng dụng vẫn gặp lỗi khi chạy qua socket, TLS, proxy, load balancer hoặc một client đọc dữ liệu chậm. Nguyên nhân thường là bài test chỉ kiểm tra logic ở một lớp rồi kết luận quá rộng về toàn bộ đường đi của dữ liệu.

Bài học này giúp xác định chính xác giới hạn của từng loại test, đặc biệt khi cần chứng minh HTTP streaming và Reactive Streams backpressure:

- WebTestClient.bindToController(...), bindToRouterFunction(...) và bindToApplicationContext(...) dùng mock request/response, không mở TCP socket.
- StepVerifier kiểm tra tín hiệu và demand ở ranh giới subscription của Publisher; nó không tự mô phỏng kernel TCP, HTTP codec, TLS hoặc proxy.
- WebTestClient.bindToServer(...) và @SpringBootTest(webEnvironment = RANDOM_PORT) gửi HTTP qua server đang chạy, do đó có thể kiểm tra connector và socket thật trên loopback.
- MockWebServer hoặc WireMock cho phép WebClient thật gửi HTTP qua socket tới server giả lập, hữu ích cho lỗi transport và response chậm.
- Kiểm thử qua ingress, TLS termination, network impairment và tải đồng thời cần môi trường có hạ tầng tương ứng.

**Điểm cốt lõi:** Backpressure của Reactor, demand qua WebFlux publisher, khả năng ghi của connector, bộ đệm của hệ điều hành và flow control của HTTP/TCP là các lớp liên quan nhưng không phải cùng một cơ chế. Không thể lấy kết quả request(1) trong một StepVerifier rồi kết luận server production chỉ tạo đúng một phần tử qua mạng.

Bài học dùng Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Reactor và JUnit 5. Ví dụ phân biệt mã độc lập, test mock-bound và test live-server.

## 2. Bốn lớp cần phân biệt khi nói về backpressure

### 2.1. Demand trong Reactive Streams

Ở cấp Publisher/Subscriber, downstream gửi request(n) để báo có thể nhận thêm tối đa n phần tử. Publisher phải tôn trọng demand, không phát quá số lượng đã được yêu cầu.

Ví dụ:

```java
Flux<Integer> source = Flux.range(1, 5);

StepVerifier.create(source, 0)
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(1)
        .expectNext(3)
        .thenCancel()
        .verify();
```

Ở đây test subscriber ban đầu không yêu cầu phần tử nào, sau đó yêu cầu hai rồi một. Flux.range chỉ phát theo demand. Đây là kiểm chứng trực tiếp tại ranh giới Publisher/Subscriber trong cùng tiến trình.

### 2.2. Backpressure giữa các operator Reactor

Một chuỗi như:

```java
source
    .map(this::transform)
    .filter(this::accept)
    .publishOn(Schedulers.parallel(), 16)
    .flatMap(this::saveAsync, 4);
```

có thể thay đổi cách demand được truyền:
- publishOn có queue và prefetch.
- flatMap có concurrency và prefetch riêng.
- limitRate chia nhỏ request upstream.
- buffer, onBackpressureBuffer, onBackpressureDrop và onBackpressureLatest thay đổi cách xử lý khi producer nhanh hơn consumer.

Vì vậy demand ở downstream không nhất thiết được chuyển thành một request(n) giống hệt ở mọi operator upstream. Các operator có thể yêu cầu trước một lượng dữ liệu để duy trì throughput.

### 2.3. Backpressure ở WebFlux và HTTP connector

Spring WebFlux dùng HttpHandler non-blocking và Reactive Streams backpressure. WebHandler, codec, HttpMessageWriter, DataBuffer và server adapter phối hợp để đọc/ghi nội dung.

Với Reactor Netty, server/client connector dùng Netty event loop và channel writability để quản lý I/O. Khi outbound channel không thể ghi thêm, connector có thể điều tiết việc yêu cầu dữ liệu từ publisher. Nhưng giữa publisher và remote subscriber có nhiều lớp buffer.

Một Flux<T> được serialize thành bytes:
- Một phần tử Java có thể tạo ra một hoặc nhiều byte buffers.
- Một buffer có thể chứa một phần của message hoặc nhiều message, tùy codec/framing.
- HTTP writer có thể request trước.
- Connector có thể giữ buffer chờ channel writable.
- Kernel có send buffer/receive buffer.
- Proxy hoặc load balancer có thể buffer response.
- Client connector có thể prefetch bytes trước khi decoder emit object.

Vì vậy không có quy tắc tổng quát rằng một downstream request(1) tương đương một server-side request(1) hoặc một TCP packet.

### 2.4. Flow control của TCP và HTTP/2

TCP điều tiết byte bằng receive window/congestion control. HTTP/2 có flow control theo connection và stream, cũng ở cấp byte. Reactive Streams request(n) điều tiết số phần tử ở cấp Publisher.

Ba cơ chế có thể phối hợp qua connector, nhưng không có phép đổi một-một giữa:
- một object T;
- một DataBuffer;
- một HTTP/2 DATA frame;
- một TCP segment;
- một lần request(n).

Khi một client đọc chậm, các buffer và flow-control window có thể hấp thụ dữ liệu trong một khoảng thời gian trước khi pressure truyền ngược tới Publisher. Test cần đo đúng tầng mà yêu cầu đặt ra.

## 3. WebTestClient có những chế độ nào?

WebTestClient là test client có API fluent tương tự WebClient, nhưng thêm assertions về HTTP response. Nó có thể chạy WebFlux với mock request/response hoặc kết nối một server đang chạy.

| Cách tạo client | Có server/socket thật? | Phạm vi chính |
| --- | --- | --- |
| bindToController(...) | Không | Controller cụ thể, handler mapping và response qua mock objects |
| bindToRouterFunction(...) | Không | Functional endpoint qua mock request/response |
| bindToApplicationContext(...) | Không | WebFlux infrastructure và Spring application context qua mock objects |
| @WebFluxTest | Thường không | Controller slice test với WebTestClient |
| @SpringBootTest mặc định (MOCK) | Không | Spring Boot context trong mock web environment |
| @SpringBootTest(RANDOM_PORT) | Có | Embedded server trên cổng ngẫu nhiên |
| bindToServer() | Có | Kết nối HTTP tới server đang chạy |

### 3.1. bindToController

```java
WebTestClient client = WebTestClient
        .bindToController(new HelloController())
        .build();

client.get()
        .uri("/hello")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("hello");
```

Cách này tạo WebFlux handler chain cho controller đã chỉ định và dùng mock request/response objects. Có thể kiểm tra:
- Mapping path và HTTP method.
- Argument resolution và binding.
- Validation, exception handling nếu đã cấu hình.
- Response status/header/body.
- Codec serialization trong mock exchange.
- Logic controller và publisher mà controller trả về.

Không thể kết luận từ test này rằng:
- TCP socket bind/listen thành công.
- Reactor Netty hoặc Tomcat adapter hoạt động đúng.
- TLS handshake, ALPN hay certificate hợp lệ.
- HTTP/1.1 hoặc HTTP/2 negotiation đúng.
- Firewall, DNS, proxy hoặc ingress chuyển tiếp request.
- Kernel buffer, network backpressure hay slow-client behavior hoạt động đúng.

### 3.2. bindToRouterFunction

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route(
                RequestPredicates.GET("/hello"),
                request -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_PLAIN)
                        .bodyValue("hello"));

WebTestClient client =
        WebTestClient.bindToRouterFunction(routes).build();
```

Chế độ này hữu ích cho functional endpoint. Nó xác minh route predicate và handler behavior qua mock exchange. Nó không mở socket hoặc kiểm tra server connector.

### 3.3. bindToApplicationContext

```java
WebTestClient client =
        WebTestClient.bindToApplicationContext(applicationContext)
                .build();
```

Chế độ này dùng WebFlux configuration, controller beans và WebHandler chain trong Spring context, nhưng vẫn xử lý request/response bằng mock objects. Phù hợp để kiểm tra filter, exception handler, codec configuration và các bean tích hợp với WebFlux.

Nếu cần Spring Security trong mock-bound test, phải cấu hình security test support tương ứng, ví dụ apply springSecurity() khi bind context. Việc test filter trong mock chain không tự chứng minh reverse proxy hoặc TLS ở production.

### 3.4. @WebFluxTest

@WebFluxTest(HelloController.class) là slice test tập trung vào WebFlux controller layer. Spring Boot tự cấu hình WebTestClient cho loại test này; thường không khởi động embedded server.

Nó rất hữu ích để kiểm tra nhanh contract controller, nhưng không dùng kết quả đó để khẳng định HTTP connector, TCP hoặc proxy đã hoạt động.

### 3.5. bindToServer

```java
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
```

Cách này kết nối tới một HTTP server đang chạy. Nếu server là ứng dụng WebFlux của mình, request đi qua client connector, socket, server connector, WebFlux handler chain và response writer.

Đây là bước kiểm chứng khác hẳn bindToController. Tuy vậy, nếu server ở localhost, test vẫn chỉ bao phủ loopback trên máy test. Nó không tự mô phỏng WAN, proxy, TLS termination, DNS production hoặc tải thực tế.

## 4. Bản đồ: test nào chứng minh được điều gì?

| Điều muốn chứng minh | Test phù hợp | Bằng chứng không đủ |
| --- | --- | --- |
| Controller trả đúng DTO | bindToController | Chỉ unit test gọi method nếu còn mapping/codec |
| Route functional được map đúng | bindToRouterFunction | Test service riêng |
| WebFlux filters/configuration được áp dụng | bindToApplicationContext | bindToController không nạp full app context |
| Validation/status/JSON contract | Mock-bound WebTestClient | Không cần socket nếu mục tiêu chỉ là contract |
| Reactive publisher tôn trọng request(n) | StepVerifier với initialRequest | expectBodyList đã aggregate body |
| Operator cancel upstream đúng | StepVerifier + doOnCancel/doFinally | Chỉ assert HTTP 200 |
| Server thật nhận HTTP và serialize response | RANDOM_PORT hoặc bindToServer | Mock-bound WebTestClient |
| HTTP connector và socket loopback | Live-server integration test | Controller test |
| WebClient gửi request thật tới endpoint giả lập | MockWebServer/WireMock | Mock ExchangeFunction |
| Client đọc chậm và hủy response body | Live server + bounded body subscriber | StepVerifier trên Flux không qua HTTP |
| Proxy/ingress timeout và buffering | Test qua đúng proxy/ingress | Localhost test |
| TLS certificate/ALPN/HTTP2 | Live TLS endpoint và client thật | Mock request/response |
| Memory bound dưới tải lớn | Load/stress test + metrics/JFR | Một test đơn lẻ |
| Production network behavior | Staging/chaos/network impairment | Loopback server |

Nguyên tắc: mỗi kết luận chỉ rộng bằng ranh giới thực sự được test.

## 5. Test backpressure đúng ở cấp Publisher với StepVerifier

Đây là nơi có thể kiểm tra demand chính xác nhất vì test kiểm soát trực tiếp subscriber.

### 5.1. Ghi lại request(n)

```java
@Test
void publisherHonorsExplicitDemand() {
    List<Long> requests = new ArrayList<>();

    Flux<Integer> source = Flux.range(1, 5)
            .doOnRequest(requests::add);

    StepVerifier.create(source, 0)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(1)
            .expectNext(3)
            .thenCancel()
            .verify(Duration.ofSeconds(2));

    assertEquals(List.of(2L, 1L), requests);
}
```

Test này chứng minh:
- Subscriber bắt đầu với demand bằng 0.
- Source không phát cho đến khi request.
- Sau request(2), subscriber nhận hai phần tử.
- Sau request(1), subscriber nhận thêm một phần tử.
- Cancellation kết thúc subscription.

Kết quả này không chứng minh HTTP connector gửi một message trên socket cho mỗi lần request, vì test không có HTTP connector hoặc socket.

### 5.2. limitRate thay đổi demand upstream

```java
@Test
void limitRateShapesUpstreamRequests() {
    List<Long> requests = new ArrayList<>();

    Flux<Integer> source = Flux.range(1, 10)
            .doOnRequest(requests::add)
            .limitRate(3);

    StepVerifier.create(source, 0)
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(2)
            .expectNext(3, 4)
            .thenCancel()
            .verify();

    assertFalse(requests.isEmpty());
}
```

limitRate(3) chia request thành các đợt nhỏ hơn ở upstream theo chiến lược replenishment. Không nên khẳng định một chuỗi request cố định chỉ từ giá trị limitRate: high-tide/low-tide, demand ban đầu, operator fusion và phiên bản Reactor có thể ảnh hưởng cách replenishment. Nếu cần kiểm tra chính xác, ghi lại requests trên đúng phiên bản và operator chain thực tế.

### 5.3. Test prefetch và buffering

Một số operator yêu cầu trước dữ liệu để tăng throughput:
- publishOn(scheduler, prefetch).
- flatMap(mapper, concurrency, prefetch).
- buffer(n).
- onBackpressureBuffer(...).

Khi kiểm thử, cần biết buffer nằm ở đâu và giới hạn theo số phần tử hay số byte. Một queue 256 object không đồng nghĩa giới hạn 256 MB nếu kích thước mỗi object khác nhau.

Ví dụ kiểm tra demand không phát vô hạn:

```java
AtomicLong upstreamRequested = new AtomicLong();

Flux<Integer> pipeline = Flux.range(1, 1000)
        .doOnRequest(upstreamRequested::addAndGet)
        .limitRate(8);

StepVerifier.create(pipeline, 0)
        .thenRequest(1)
        .expectNext(1)
        .thenCancel()
        .verify();

assertTrue(upstreamRequested.get() > 0);
```

Assertion trên chỉ xác nhận có demand được truyền upstream; nó không đưa ra một giới hạn bộ nhớ toàn hệ thống. Để chứng minh bounded buffering, cần kiểm tra cấu hình prefetch/concurrency và đo queue/buffer dưới tải.

## 6. Mock-bound WebTestClient có thể kiểm tra gì về stream?

Mock-bound WebTestClient vẫn hữu ích khi controller trả Flux. Nó có thể kiểm tra:
- Publisher được subscribe khi response được ghi.
- Status và content type.
- Serialization/encoding theo codec được cấu hình.
- Thứ tự và nội dung response body.
- Lỗi từ publisher được xử lý theo response lifecycle trong mock exchange.
- Một số hành vi cancellation ở publisher trong môi trường in-memory.

Ví dụ controller:

```java
@RestController
class NumberController {

    @GetMapping(
            value = "/numbers",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    Flux<Integer> numbers() {
        return Flux.range(1, 3);
    }
}
```

Mock test:

```java
@Test
void mockClientVerifiesNdjsonBody() {
    WebTestClient client =
            WebTestClient.bindToController(
                    new NumberController()).build();

    client.get()
            .uri("/numbers")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(
                    MediaType.APPLICATION_NDJSON)
            .expectBody()
            .json("1\n2\n3\n");
}
```

Tùy codec và cách body matcher xử lý NDJSON, có thể dùng returnResult(Integer.class) rồi kiểm tra getResponseBody() bằng StepVerifier thay cho JSON matcher. Mục tiêu của ví dụ là xác nhận contract response; nó vẫn là mock exchange.

**Không suy luận:** vì mock test nhận ba số đúng thứ tự nên production socket cũng sẽ giữ tốc độ, giới hạn buffer hoặc cancellation như vậy. Những đặc tính đó cần live transport test.

## 7. Live-server test với RANDOM_PORT

### 7.1. Vì sao cần RANDOM_PORT?

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT) khởi động embedded server trên một cổng thật được cấp ngẫu nhiên. Khi dùng WebTestClient.bindToServer(), test gửi request HTTP qua loopback socket tới server.

Test này có thể kiểm tra:
- Embedded server thực sự khởi động và bind cổng.
- HTTP request/response qua connector.
- Codec serialization trong đường đi thật.
- Header, status, streaming body và connection behavior.
- Cancellation của client response body có được server quan sát hay không, tùy connector.
- Cấu hình server/client thực tế trong ứng dụng.

Nó vẫn không chứng minh:
- Proxy, gateway hoặc service mesh production hoạt động đúng.
- DNS bên ngoài và routing production.
- TLS nếu test chỉ dùng http://.
- Packet loss/WAN jitter.
- Hành vi dưới số lượng connection rất lớn.
- Memory luôn bounded dưới mọi workload.

### 7.2. Ví dụ kiểm tra body qua HTTP thật

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveHttpTest {

    @LocalServerPort
    int port;

    @Test
    void receivesHttpResponseFromRunningServer() {
        WebTestClient client = WebTestClient
                .bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        client.get()
                .uri("/numbers")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_NDJSON)
                .expectBody()
                .json("1\n2\n3\n");
    }
}
```

Đây là integration test qua socket loopback. Không còn dùng mock ServerHttpRequest/ServerHttpResponse.

### 7.3. Test response stream bằng bounded demand

Khi muốn kiểm tra client đọc response theo demand, dùng returnResult để lấy Flux response body thay vì aggregate bằng expectBodyList:

```java
FluxExchangeResult<Long> result = client.get()
        .uri("/stream")
        .accept(MediaType.APPLICATION_NDJSON)
        .exchange()
        .expectStatus().isOk()
        .returnResult(Long.class);

StepVerifier.create(result.getResponseBody(), 0)
        .thenRequest(1)
        .expectNext(0L)
        .thenCancel()
        .verify(Duration.ofSeconds(10));
```

Đây là test qua HTTP thật nếu client được tạo bằng bindToServer(). Subscriber kiểm soát demand đối với response body Flux ở phía client. Cancellation sẽ đi vào client connector và có thể đóng/hủy việc đọc response.

**Giới hạn cần ghi rõ:** connector có thể đã đọc trước một số byte vào buffer, server có thể đã ghi dữ liệu vào kernel buffer, và proxy có thể buffer. Do đó không assert rằng server publisher chỉ emit đúng một phần tử. Test này chứng minh khả năng consumer hủy body stream qua đường HTTP; để xác nhận server publisher nhận cancellation, instrument server-side doFinally(CANCEL) và chờ signal thực tế.

## 8. Một ví dụ đầy đủ: server quan sát cancellation từ client thật

Ví dụ dưới đây chạy một Spring Boot WebFlux server và một WebTestClient kết nối qua loopback. Server phát một stream dài; client chỉ nhận một phần tử rồi cancel.

### 8.1. Cấu trúc project

```text
webflux-network-test/
  settings.gradle
  build.gradle
  src/main/java/demo/network/
    NetworkTestApplication.java
    StreamProbe.java
    StreamController.java
  src/test/java/demo/network/
    MockBoundTest.java
    LiveBackpressureTest.java
```

### 8.2. Dependencies

Tệp build.gradle:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tệp settings.gradle:

```groovy
rootProject.name = 'webflux-network-test'
```

### 8.3. Application class

Tệp NetworkTestApplication.java:

```java
package demo.network;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NetworkTestApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                NetworkTestApplication.class, args);
    }
}
```

### 8.4. StreamProbe

Tệp StreamProbe.java:

```java
package demo.network;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Component;

import reactor.core.publisher.SignalType;

@Component
public class StreamProbe {

    private final AtomicLong requestCalls = new AtomicLong();

    private volatile CountDownLatch cancelled =
            new CountDownLatch(1);

    public void reset() {
        requestCalls.set(0);
        cancelled = new CountDownLatch(1);
    }

    public void onRequest(long n) {
        requestCalls.incrementAndGet();
    }

    public void onFinally(SignalType signal) {
        if (signal == SignalType.CANCEL) {
            cancelled.countDown();
        }
    }

    public long requestCalls() {
        return requestCalls.get();
    }

    public boolean awaitCancellation(
            long timeout, TimeUnit unit)
            throws InterruptedException {
        return cancelled.await(timeout, unit);
    }
}
```

Probe này ghi nhận:
- Server-side publisher đã nhận ít nhất một request signal.
- Server-side publisher đã nhận cancel, nếu transport đóng/cancel đúng cách.

Nó cố ý không cộng dồn giá trị n thành “số phần tử đã được gửi qua mạng”. Một request có thể có giá trị lớn hoặc được điều chỉnh bởi operator/writer.

### 8.5. StreamController

Tệp StreamController.java:

```java
package demo.network;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class StreamController {

    private final StreamProbe probe;

    public StreamController(StreamProbe probe) {
        this.probe = probe;
    }

    @GetMapping(
            value = "/finite",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Integer> finite() {
        return Flux.range(1, 3);
    }

    @GetMapping(
            value = "/stream",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Long> stream() {
        return Flux.interval(Duration.ofMillis(25))
                .take(10_000)
                .doOnRequest(probe::onRequest)
                .doFinally(probe::onFinally);
    }
}
```

Flux.interval được giới hạn bằng take(10_000) để stream có thể hoàn tất nếu client đọc hết. Nếu client ngừng đọc, cancellation có thể đi ngược qua response writer và connector về publisher.

### 8.6. MockBoundTest

Tệp MockBoundTest.java:

```java
package demo.network;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;

class MockBoundTest {

    @Test
    void controllerWorksWithoutOpeningSocket() {
        StreamController controller =
                new StreamController(new StreamProbe());

        WebTestClient client =
                WebTestClient.bindToController(controller)
                        .build();

        client.get()
                .uri("/finite")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        org.springframework.http.MediaType.APPLICATION_JSON)
                .expectBody()
                .json("[1,2,3]");
    }
}
```

Test này kiểm tra controller và response contract qua mock request/response. Nó không khởi động embedded server.

### 8.7. LiveBackpressureTest

Tệp LiveBackpressureTest.java:

```java
package demo.network;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveBackpressureTest {

    @LocalServerPort
    int port;

    @Autowired
    StreamProbe probe;

    @BeforeEach
    void resetProbe() {
        probe.reset();
    }

    @Test
    void clientCanReadOneItemAndCancelLiveHttpStream()
            throws InterruptedException {

        WebTestClient client = WebTestClient
                .bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        FluxExchangeResult<Long> result = client.get()
                .uri("/stream")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .returnResult(Long.class);

        StepVerifier.create(result.getResponseBody(), 0)
                .thenRequest(1)
                .expectNext(0L)
                .thenCancel()
                .verify(java.time.Duration.ofSeconds(10));

        assertTrue(probe.requestCalls() > 0);
        assertTrue(probe.awaitCancellation(
                5, TimeUnit.SECONDS),
                "Server publisher did not observe cancellation");
    }
}
```

Test này kiểm tra:
1. Spring Boot khởi động embedded server trên cổng thật.
2. WebTestClient kết nối qua HTTP loopback.
3. Response được stream dưới dạng NDJSON.
4. Client subscriber ban đầu request 0, sau đó request 1.
5. Client nhận phần tử đầu rồi cancel response body.
6. Server publisher quan sát cancellation qua doFinally(CANCEL).

Nếu một server adapter/client connector cụ thể drain response thay vì đóng connection ngay, thời điểm cancellation có thể khác. Khi porting test sang connector khác, cần xác minh lifecycle thực tế. Không thay assertion bằng số phần tử server đã emit chính xác, vì connector và kernel buffers có thể đã hấp thụ thêm dữ liệu.

### 8.8. Chạy project

Nếu dự án đã có Gradle wrapper:

```bash
./gradlew test
```

Nếu chưa có Gradle wrapper nhưng đã cài Gradle:

```bash
gradle test
```

Bộ test có hai mục tiêu khác nhau:
- MockBoundTest: kiểm tra controller contract không có socket.
- LiveBackpressureTest: kiểm tra HTTP thật trên loopback và cancellation tới server publisher.

Không coi hai test này thay thế load test qua proxy hoặc production-like network.

## 9. Vì sao request(1) không đồng nghĩa server chỉ emit một item?

Khi client subscriber yêu cầu một item, response body có thể đã trải qua các lớp sau:

```text
Server Flux<T>
   |
   v
HttpMessageWriter / Encoder
   |
   v
DataBuffer queue
   |
   v
Server connector / Netty channel
   |
   v
Kernel TCP send buffer
   |
   v
Network / proxy / load balancer
   |
   v
Client kernel receive buffer
   |
   v
Client connector / decoder
   |
   v
Response Flux<T>
   |
   v
StepVerifier request(1)
```

Một vài item tiếp theo có thể:
- Đã được encode thành bytes.
- Đang nằm trong DataBuffer queue.
- Đã được ghi vào kernel send buffer.
- Đang nằm trong proxy buffer.
- Đã được client connector đọc vào memory nhưng chưa emit thành object.

Vì vậy test có thể chứng minh consumer chỉ yêu cầu một object tiếp theo ở boundary của response Flux, nhưng không thể kết luận không có byte hoặc item tiếp theo ở bất kỳ buffer nào.

Cũng không nên yêu cầu transport phải có chính xác một request(1) ở server cho mỗi object mà client tiêu thụ. Đây là abstraction boundary khác nhau.

## 10. Test outbound WebClient bằng MockWebServer hoặc WireMock

Một bài toán khác là service WebFlux gọi một downstream HTTP API bằng WebClient. Nếu mock trực tiếp ExchangeFunction, ta test cách ứng dụng xử lý response/error ở tầng WebClient abstraction; không test HTTP client connector thực sự.

MockWebServer hoặc WireMock nhận request qua HTTP socket như server thông thường. Có thể dùng cùng WebClient connector production để kiểm tra:
- Method, path, query, headers và request body.
- Response status/body và codec decoding.
- Server trả response chậm.
- Kết nối bị đóng/reset.
- Response body được stream theo chunk.
- Retry, timeout và cancellation trên đường HTTP client.

Ví dụ ý tưởng với MockWebServer (API import/package phụ thuộc phiên bản OkHttp đang dùng):

```java
MockWebServer server = new MockWebServer();
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"id\":42,\"name\":\"keyboard\"}"));
server.start();

WebClient client = WebClient.builder()
        .baseUrl(server.url("/").toString())
        .build();

Mono<Product> result = client.get()
        .uri("/products/42")
        .retrieve()
        .bodyToMono(Product.class);

StepVerifier.create(result)
        .assertNext(product -> {
            assertEquals(42L, product.id());
            assertEquals("keyboard", product.name());
        })
        .verifyComplete();

RecordedRequest request = server.takeRequest();
assertEquals("GET", request.getMethod());
assertEquals("/products/42", request.getPath());

server.shutdown();
```

Đây là snippet minh họa: Product, imports và dependency MockWebServer cần được khai báo. Trong code test thực tế nên dùng try/finally hoặc JUnit extension để đảm bảo server.shutdown() ngay cả khi assertion fail.

MockWebServer tạo network I/O thật giữa client và server giả lập, nhưng không kiểm tra DNS/Internet/downstream production. Nó là công cụ tốt để tạo tình huống có thể tái lập, chẳng hạn delayed response hoặc socket disconnect.

Không nhầm:
- MockWebServer/WireMock: fake server nhận HTTP thật qua socket.
- ExchangeFunction mock: thay thế tầng trao đổi HTTP, không có socket.
- WebTestClient.bindToController: mock WebFlux server request/response.
- WebTestClient.bindToServer: HTTP client nối tới server đang chạy.

## 11. Kiểm tra slow consumer đúng cách

Một test slow-consumer nên có mục tiêu rõ ràng:

1. Server phát dữ liệu liên tục hoặc theo tốc độ kiểm soát.
2. Client đọc chậm hoặc tạm dừng demand.
3. Theo dõi lượng dữ liệu được tạo/encode/buffer.
4. Quan sát cancellation khi client ngừng đọc.
5. Kiểm tra memory và queue có giới hạn theo thiết kế.

### 11.1. Chậm ở downstream operator không nhất thiết là chậm ở socket

Ví dụ:

```java
clientResponseBody
        .delayElements(Duration.ofMillis(500))
        .subscribe(this::process);
```

delayElements làm chậm bước xử lý downstream, nhưng có thể prefetch/buffer một số phần tử. Điều đó không đảm bảo client connector ngừng đọc socket ngay lập tức.

Khi test, dùng subscriber demand có kiểm soát hoặc limitRate, ghi nhận request signals và đo buffer thực tế. Không chỉ đặt một delay rồi kết luận transport đã backpressure.

### 11.2. Dùng body Flux và StepVerifier

Với WebTestClient.bindToServer(), returnResult(...).getResponseBody() cho phép tiêu thụ response body dưới dạng Publisher. Khởi đầu demand bằng 0 rồi yêu cầu từng phần tử là một cách kiểm tra client-side demand và cancellation.

Tuy nhiên, không assert số phần tử server đã emit bằng số lần request phía client. Hãy kiểm tra:
- Client nhận đúng dữ liệu đã yêu cầu.
- Cancellation được gửi khi subscriber hủy.
- Server quan sát cancel nếu connector/transport thực sự propagate.
- Memory/queue không tăng vô hạn trong một test tải riêng.

### 11.3. Kiểm tra inbound request body

Với upload streaming, dùng request body Flux<DataBuffer> hoặc body publisher lớn và client gửi chậm. Một test mock có thể kiểm tra decoder/binding ở mức ứng dụng, nhưng chỉ live server mới đi qua socket receive path.

Trong test thật, theo dõi:
- Số bytes nhận theo thời gian.
- Server publisher request và consume rate.
- Buffer/temporary file usage.
- Client disconnect và cancellation.
- Max in-memory size của multipart/codec.

## 12. HTTP streaming không phải lúc nào cũng giữ nguyên từng phần tử

Khi Flux<T> được encode thành HTTP response:
- JSON application/json có thể được biểu diễn như một JSON array và thường cần xử lý framing khác với NDJSON.
- application/x-ndjson phát mỗi JSON value theo dòng.
- text/event-stream dùng SSE framing, event/data/id fields và flush theo từng event.
- Một số codec có thể aggregate body hoặc buffer theo giới hạn.
- Compression có thể gom bytes và làm thay đổi timing quan sát ở client.

Vì vậy test backpressure cần đúng media type và codec production. Một test expectBodyList thường aggregate body trước khi assert; nó phù hợp để kiểm tra nội dung cuối cùng nhưng không phải lựa chọn tốt nhất để chứng minh streaming incremental hoặc consumer cancellation.

Với streaming, ưu tiên returnResult(T.class) và kiểm tra getResponseBody() như Flux; nếu cần quan sát byte-level framing, kiểm tra raw DataBuffer/bytes với client connector phù hợp.

## 13. TLS, HTTP/2 và proxy: những điều mock không thể chứng minh

### 13.1. TLS

Mock request/response không có TLS handshake. Một live test dùng http://127.0.0.1 cũng không kiểm tra:
- Certificate chain.
- Hostname verification.
- Expiry và trust store.
- TLS protocol/cipher.
- ALPN negotiation.
- Mutual TLS client certificate.

Muốn chứng minh TLS, chạy server HTTPS thật với test certificate và client xác thực certificate đúng cách. Không dùng trust-all trong test rồi kết luận production trust store đúng.

### 13.2. HTTP/2

Mock WebTestClient không xác minh HTTP/2 frame hoặc ALPN. Live HTTP/2 test cần server/client connector thực sự cấu hình HTTP/2, TLS/ALPN hoặc h2c theo môi trường, rồi xác nhận protocol đã thương lượng.

Một status 200 không cho biết request chạy HTTP/1.1 hay HTTP/2. Kiểm tra client protocol, server access log hoặc TLS ALPN evidence.

### 13.3. Reverse proxy và load balancer

Proxy có thể:
- Buffer response thay vì stream ngay.
- Có idle timeout thấp hơn ứng dụng.
- Kết thúc TLS rồi kết nối backend bằng HTTP/1.1.
- Đặt giới hạn connection/stream.
- Nén hoặc thay đổi chunking.
- Đóng kết nối khi client đọc chậm.
- Giữ connection pool và làm thay đổi load distribution.

Localhost test bỏ qua các thành phần này. Nếu production request đi qua Nginx, Envoy, ingress controller, API gateway hoặc service mesh, cần một integration test qua đúng lớp đó hoặc một staging environment tương đương.

### 13.4. Mạng chậm và mất gói

Mock server có thể trì hoãn response, nhưng không mô phỏng đầy đủ packet loss, retransmission, congestion, route changes hoặc NAT idle timeout. Dùng network emulation/chaos tooling hoặc môi trường staging có kiểm soát để kiểm tra các điều kiện này.

## 14. Những gì test mock có thể nói về cancellation

Cancellation có nhiều tầng:

| Tầng | Ví dụ | Cách kiểm tra |
| --- | --- | --- |
| Reactor subscription | Subscriber gọi cancel | StepVerifier.thenCancel, doFinally(CANCEL) |
| WebFlux handler | Client body bị hủy trong mock exchange | Instrument publisher/handler, mock-bound test |
| HTTP client connector | Body consumer cancel | Live client + returnResult body Flux |
| HTTP server connector | Channel đóng, writer cancel | Live server + doFinally(CANCEL) |
| TCP socket | FIN/RST và kernel state | Socket-level test/packet capture |
| Proxy | Upstream/downstream cancellation | Test qua proxy và proxy logs/metrics |

Một test có thể chứng minh cancellation ở một tầng mà không chứng minh nó lan đến tất cả tầng dưới. Ví dụ StepVerifier.thenCancel() chứng minh subscriber đã cancel; để khẳng định server nhận cancellation cần instrument server publisher hoặc transport.

Không nên đặt một biến AtomicBoolean cancelled trong unit test rồi khẳng định network peer đã đóng socket, nếu test không hề có network.

## 15. Đo lường backpressure và buffering trong live test

### 15.1. Đo demand ở Publisher

Dùng doOnRequest ở các điểm khác nhau của pipeline:

```java
Flux<Data> pipeline = source
        .doOnRequest(n -> metrics.sourceDemand(n))
        .publishOn(scheduler, 32)
        .doOnRequest(n -> metrics.workerDemand(n))
        .map(this::encode);
```

Hai điểm có thể thấy request pattern khác nhau do operator prefetch. Chỉ đo để hiểu flow; không tự cộng các con số thành số message đã truyền qua socket.

### 15.2. Đo cancellation

```java
Flux<Data> stream = source
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                metrics.streamCancelled();
            }
        });
```

Đây là tín hiệu lifecycle của Publisher. Nếu đặt trước một operator có subscription riêng hoặc retry, cancellation quan sát được có thể khác ở các đoạn upstream/downstream. Chọn đúng vị trí instrumentation.

### 15.3. Đo connector và Netty

Reactor Netty có Micrometer integration cho HTTP server/client. Các chỉ số thường hữu ích gồm:
- Active connections và total connections.
- Active HTTP/2 streams.
- Data received/sent.
- Response time và errors.
- ByteBuf allocator heap/direct memory.
- Event loop saturation và pending tasks nếu được expose.

Metrics không tự chứng minh backpressure hoạt động đúng, nhưng giúp phát hiện buffer tăng, throughput tụt hoặc connection không được giải phóng. Bật metrics với URI tag dạng template và giới hạn cardinality; tránh tạo một time series cho mỗi ID người dùng.

### 15.4. Đo memory và queue

Nếu yêu cầu là “memory không tăng vô hạn khi client chậm”, cần:
- Xác định mọi queue/buffer và giới hạn.
- Đo heap/direct memory trong thời gian tải.
- Theo dõi pending writes, connection pool và event loop.
- Thử nhiều client tốc độ đọc khác nhau.
- Kiểm tra cancellation/timeout giải phóng buffer.
- Chạy stress test đủ lâu để thấy tích lũy.

Một unit test với request(1) không thể chứng minh memory bounded trong production.

## 16. Test matrix cho một endpoint streaming

Ví dụ endpoint /events trả NDJSON. Bộ kiểm thử nên phân lớp:

| Test | Setup | Assertion | Giới hạn kết luận |
| --- | --- | --- | --- |
| Publisher contract | StepVerifier | Giá trị, order, demand, cancel | Không có HTTP |
| Controller contract | bindToController | Route, status, content type, body | Không có socket |
| Application filter | bindToApplicationContext | Security/filter/codec config | Mock exchange |
| Live HTTP | RANDOM_PORT | Connector, socket, HTTP body | Loopback |
| Slow reader | Live HTTP + bounded body subscriber | Client cancel và server observe cancel | Không chứng minh proxy/WAN |
| Outbound client | MockWebServer | WebClient network request/response, delayed body | Downstream giả lập |
| TLS | Live HTTPS | Certificate/hostname/ALPN | Chỉ test certificate và TLS config đó |
| Proxy | Staging ingress | Buffering, timeout, routing, cancellation | Phụ thuộc môi trường |
| Load | Gatling/k6/Netty load tool | Throughput, p95/p99, memory, connections | Không thay thế functional assertions |
| Chaos | Network impairment | Reconnect, retry, timeout, resource cleanup | Kết quả phụ thuộc kịch bản lỗi |

Không phải endpoint nào cũng cần toàn bộ matrix. Chọn lớp test theo rủi ro và cam kết kỹ thuật của endpoint.

## 17. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| bindToController test xanh nên server production đã chạy được | Không khởi động embedded server hoặc socket | Thêm RANDOM_PORT/bindToServer |
| WebTestClient mặc định luôn là live server | Có thể dùng mock request/response | Xác định chính xác bind mode |
| StepVerifier request(1) chứng minh server emit một item | Không có connector/kernel/proxy trong test | Dùng live network test và không khẳng định 1:1 |
| expectBodyList chứng minh streaming incremental | Body thường được aggregate để assert | Dùng returnResult và response body Flux |
| MockWebServer là mock không có network | Nó nhận HTTP qua socket thật | Phân biệt fake server với mock ExchangeFunction |
| Mock ExchangeFunction chứng minh TLS/socket | Nó thay thế exchange layer | Dùng mock web server hoặc live server |
| delayElements tạo slow network | Nó chỉ làm chậm downstream operator | Test client đọc chậm qua transport thật |
| Cancel StepVerifier chứng minh TCP FIN đã gửi | Chỉ chứng minh subscription cancel | Instrument connector/socket khi cần |
| Test localhost chứng minh ingress production | Bỏ qua proxy/LB | Test qua staging ingress |
| TCP flow control giống Reactor request(n) | Một bên điều tiết byte, một bên điều tiết element | Đo từng lớp riêng |
| NDJSON và JSON array giống nhau | Framing/flush/aggregation khác | Test đúng Content-Type và codec |
| Chỉ đo request count để suy ra memory | Không đo buffer/byte size | Theo dõi heap/direct memory/queue |
| Không test client chậm | Buffer có thể tích lũy hoặc stream bị đóng | Thêm slow-reader/cancel test |
| Mock test đủ cho TLS/HTTP2 | Không có handshake/frame negotiation | Dùng live TLS/HTTP2 endpoint |
| Test timeout không đo cancellation | Error assertion không chứng minh resource cleanup | Assert doOnCancel/doFinally và connection lifecycle |
| Chạy stress test rồi bỏ functional test | Throughput không chứng minh contract | Kết hợp unit, integration và load tests |

## 18. Checklist lựa chọn test

Trước khi viết assertion, trả lời:

1. Tôi đang kiểm tra logic controller, publisher, codec, connector hay network?
2. WebTestClient được tạo bằng bindToController, bindToApplicationContext hay bindToServer?
3. Server có thực sự chạy trong test này không?
4. Test có đi qua đúng server adapter production (Reactor Netty/Tomcat/Jetty) không?
5. Publisher demand được quan sát ở boundary nào?
6. Có operator prefetch/buffer/flatMap concurrency trước điểm đo không?
7. Test body có aggregate toàn bộ response không?
8. Nếu client cancel, server publisher có quan sát doFinally(CANCEL) không?
9. Có phân biệt bytes, DataBuffer và domain objects không?
10. Test có dùng đúng media type/codec production không?
11. Nếu gọi downstream bằng WebClient, mock là ExchangeFunction hay mock HTTP server thật?
12. TLS, HTTP/2, proxy và ingress có nằm trong đường đi test không?
13. Slow client được mô phỏng ở subscriber, socket hay proxy?
14. Có đo memory/queue và connection lifecycle không?
15. Kết luận test có bị mở rộng vượt phạm vi setup không?

## 19. Tài liệu tham khảo chính thức

- [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): các chế độ bindToController, bindToRouterFunction, bindToApplicationContext và bindToServer.
- [Spring Framework – WebFlux Testing](https://docs.spring.io/spring-framework/reference/web/webflux-test.html): mock ServerHttpRequest, ServerHttpResponse, ServerWebExchange và WebTestClient.
- [Spring Boot – Testing Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): mock web environment, @WebFluxTest, @AutoConfigureWebTestClient và live-server test.
- [Spring Framework – Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): HttpHandler, non-blocking I/O, Reactive Streams backpressure, adapters và codecs.
- [Spring Framework – WebClient Testing](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html): MockWebServer/WireMock và lý do test HTTP client với mock server thật.
- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, virtual time, TestPublisher và PublisherProbe.
- [Project Reactor – StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): demand, cancellation, verify và withVirtualTime.
- [Reactor Netty – HTTP Server](https://projectreactor.io/docs/netty/release/reference/http-server.html): server I/O, Reactive Streams backpressure và metrics.
- [Reactor Netty – HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): client connector, network I/O và backpressure.

## 20. Ghi nhớ

**Mock-bound WebTestClient kiểm tra ứng dụng WebFlux qua mock request/response; StepVerifier kiểm tra publisher demand tại subscription boundary.** Hai công cụ này rất tốt để chứng minh logic, mapping, codec và quy tắc Reactive Streams trong phạm vi chúng thực sự chạy.

Muốn kiểm tra HTTP connector và socket, dùng bindToServer() hoặc RANDOM_PORT. Muốn test WebClient outbound qua HTTP thật, dùng MockWebServer/WireMock. Muốn chứng minh proxy, TLS, HTTP/2, slow-client behavior hoặc bounded memory, cần môi trường và phép đo tương ứng.

Đặc biệt, một request(1) ở client không đồng nghĩa server chỉ emit một phần tử: codec, connector, kernel, TCP/HTTP2 flow control và proxy có thể buffer dữ liệu. Hãy tách rõ demand của Reactor, byte flow control và network buffering, rồi chỉ đưa ra kết luận nằm trong ranh giới test đã chạy.

# Mô phỏng kết nối chậm, ngắt kết nối và timeout trong kiểm thử Spring WebFlux

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Kiểm thử WebFlux  
**Bài học:** Mô phỏng kết nối chậm, ngắt kết nối và timeout

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân loại “chậm” theo DNS, TCP connect, TLS handshake, đợi response headers, đọc từng chunk response, gửi request body và đợi dữ liệu tiếp theo trong stream.
2. Chọn đúng tầng kiểm thử: `StepVerifier`, `WebTestClient.bindToController`, HTTP server thật với `RANDOM_PORT`, hay một fake upstream HTTP server có khả năng điều khiển socket.
3. Dùng `Mono.delay`, `Flux.interval` và `StepVerifier.withVirtualTime` để mô phỏng **độ trễ logic** mà không biến test đơn vị thành phép đo mạng.
4. Sử dụng `MockWebServer` để trì hoãn headers/body, giảm tốc độ truyền và cưỡng bức đóng kết nối đang truyền response.
5. Phân biệt `WebTestClient.responseTimeout`, `Mono.timeout`, Reactor Netty `responseTimeout`, TCP connect timeout, pool acquire timeout và giới hạn thời gian của test.
6. Kiểm tra phản ứng khi timeout hoặc hủy subscription: error mapping, fallback, cancel upstream và cleanup resource.
7. Kiểm tra HTTP streaming (SSE) và upload chậm bằng `WebClient`/`Flux` mà không gom cả stream vào RAM.
8. Viết ví dụ hoàn chỉnh với Java 17+, Spring Boot 3.3.5, Reactor Test, WebTestClient và MockWebServer trên cổng ngẫu nhiên.
9. Thiết kế test bền vững trong CI: giới hạn thời gian, không dựa vào IP bên ngoài, không dùng `Thread.sleep` để đồng bộ logic, kiểm tra lỗi theo contract thay vì stack trace.
10. Hiểu điều **không thể** kết luận chỉ từ một test: cancel không bảo đảm database rollback, close socket không tự chứng minh mọi tài nguyên đã được giải phóng, test mock không xác nhận hành vi TCP.

## 1. Chậm ở đâu trong một request WebFlux?

Một HTTP request có thể chậm ở nhiều thời điểm:

```text
WebClient                  Network / Proxy             WebFlux server
   |                             |                            |
   |-- DNS resolve --------------|                            |
   |-- TCP connect --------------|--------------------------->|
   |-- TLS handshake ------------|--------------------------->|
   |-- send headers/body --------|--------------------------->| decode request
   |                             |                            | handler
   |                             |                            | Mono.delay?
   |<-- response status/headers -|----------------------------|
   |<-- response chunk 1 --------|----------------------------|
   |           [đợi]             |                            |
   |<-- response chunk 2 --------|----------------------------|
   |<-- end of body -------------|----------------------------|
   |                             |                            |
```

Từ “slow connection” dễ gây hiểu sai. Một server dùng `Mono.delay(Duration)` chỉ mô phỏng **server chậm trả kết quả**; nó không tự mô phỏng TCP connect chậm, nghẽn TLS, packet loss hoặc mạng thật có băng thông thấp.

Các dạng cần phân biệt:

| Dạng trễ/lỗi | Nằm ở đâu | Cách mô phỏng phù hợp | Dấu hiệu quan sát |
| --- | --- | --- | --- |
| DNS resolve chậm/hỏng | Trước TCP connection | Fake DNS/controlled resolver, proxy hoặc test integration chuyên biệt | UnknownHost/resolver timeout; không phải HTTP 500 |
| TCP connect timeout | Chưa có connection | Network fault proxy, firewall/blackhole được kiểm soát | Connect timeout, không nhận HTTP status |
| TLS handshake chậm/hỏng | Sau TCP, trước HTTP | Fake TLS endpoint, cert/ALPN mismatch, fault proxy | Handshake/SSL exception |
| Đợi response headers | Server nhận request nhưng chưa phản hồi headers | `MockResponse.setHeadersDelay` hoặc handler trả `Mono.delay` | Time to first byte cao |
| Response body chậm | Headers đã tới, các chunk cách nhau lâu | `setBodyDelay`, `throttleBody` | Read/response timeout giữa các chunk |
| Upload body chậm | Client gửi từng chunk chậm | `Flux.delayElements` hoặc `Flux.interval` trong request body | Server chờ request body kết thúc |
| Streaming idle | SSE/NDJSON không có sự kiện mới | `Flux.never`, heartbeat có khoảng nghỉ | Idle-timeout hoặc stream vẫn mở |
| Remote socket đóng đột ngột | TCP connection bị reset/close | `SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY` | Premature close/I/O error, thường không có status 5xx |
| Client chủ động ngắt | Subscriber hủy, browser đóng tab | `take(n)`, `dispose`, đóng client socket | `doFinally(CANCEL)` có thể xuất hiện ở upstream |

Một bài kiểm thử đáng tin phải ghi rõ đang mô phỏng **tầng nào**; nếu chỉ delay trong service rồi gọi đó là “mạng chậm”, kết luận dễ bị phóng đại.

## 2. Ba tầng kiểm thử và giá trị của từng tầng

### 2.1. Unit test với StepVerifier và VirtualTime

`StepVerifier` kiểm tra tín hiệu của Mono/Flux. Với `withVirtualTime`, ta kiểm tra một lần delay logic kéo dài hàng giờ trong vài mili giây thực.

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(2))
                .thenReturn("ready"))
        .expectSubscription()
        .expectNoEvent(Duration.ofHours(1))
        .thenAwait(Duration.ofHours(1))
        .expectNext("ready")
        .verifyComplete();
```

Ưu điểm: nhanh, kiểm tra chính xác pipeline và business timeout. Hạn chế: không kiểm tra TCP socket, TLS, pool, client disconnect hoặc backpressure của network adapter.

### 2.2. WebTestClient bindToController / bindToApplicationContext

```java
WebTestClient client = WebTestClient
        .bindToController(new DemoController())
        .configureClient()
        .responseTimeout(Duration.ofSeconds(2))
        .build();
```

Đây là kiểm thử WebFlux request mapping, codecs, HTTP status/headers/body **không cần mở server TCP**. Nó hữu ích cho validation, error handler và serialization, nhưng không chứng minh behavior khi socket mất hoặc connect timeout.

Nếu cần mock dependency của controller, dùng `@WebFluxTest` kèm mock service phù hợp; cũng không coi đó là full network integration test.

### 2.3. @SpringBootTest(RANDOM_PORT) và WebClient thật

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HttpIntegrationTest {
    @Autowired
    WebTestClient client;
}
```

Spring Boot chạy embedded HTTP server trên cổng ngẫu nhiên; `WebTestClient` có thể kết nối tới server thật. Có thể dùng `@LocalServerPort` cùng `WebClient` khi cần kiểm tra cancellation hoặc streaming theo subscription.

Cách này kiểm tra network transport loopback trong máy test, nhưng **không tái tạo** độ trễ WAN, mất gói thực, NAT hoặc proxy production nếu không bổ sung mô phỏng network faults.

### 2.4. Fake upstream server có điều khiển transport

Khi ứng dụng WebFlux đóng vai **HTTP client** gọi một external service, dùng `MockWebServer` (OkHttp 4.x) để giả lập upstream. Có thể buộc nó:

- Chờ một khoảng thời gian trước khi gửi response headers.
- Chờ trước response body.
- Truyền body theo tốc độ giới hạn.
- Ngắt socket giữa body.
- Trả status 429, 503, header Retry-After hoặc body malformed.

Đây là kiểm thử **outbound WebClient** qua HTTP thật; không cần Internet hoặc remote dependency. Kết hợp với `RANDOM_PORT` sẽ kiểm tra được cả WebFlux server và WebClient outbound.

### 2.5. Khi nào cần Toxiproxy hoặc môi trường network fault?

`MockWebServer` xử lý tốt delayed response và disconnect được kịch bản hóa. Để mô phỏng kết nối bị blackhole, packet loss, jitter, băng thông giới hạn hai chiều, half-open TCP hoặc proxy tunnel, dùng công cụ network fault proxy như Toxiproxy/`tc netem` trong một môi trường test được kiểm soát.

Không sử dụng địa chỉ IP bất kỳ trên Internet làm “host không phản hồi” trong CI: có thể có route khác nhau, firewall trả lỗi ngay hoặc bên ngoài thay đổi behavior. Test cần tài nguyên do bộ test kiểm soát và timeout hữu hạn.

## 3. Phân biệt các timeout

Một request có thể chờ connection từ pool, kết nối TCP, nhận headers hoặc nhận các chunk tiếp theo. Mỗi tầng có cơ chế timeout khác nhau.

| Timeout | API thường dùng | Phạm vi | Khi quá hạn |
| --- | --- | --- | --- |
| Connection pool acquire | `ConnectionProvider.pendingAcquireTimeout` | Chờ lấy channel từ pool | Acquire error; chưa chắc có TCP connection mới |
| TCP connect | Reactor Netty `ChannelOption.CONNECT_TIMEOUT_MILLIS` | Thiết lập connection TCP | Connect exception, chưa có HTTP response |
| SSL handshake | Reactor Netty `secure(spec -> ...)` | Thương lượng TLS | SSL/handshake exception |
| Response/read | Reactor Netty `HttpClient.responseTimeout` | Timeout ở thao tác đọc response theo semantics Netty | Read/response timeout, có thể được wrap |
| Publisher timeout | `Mono.timeout(Duration)` hoặc `Flux.timeout(Duration)` | Chờ tín hiệu tiếp theo trong reactive pipeline | Cancel nguồn và phát TimeoutException nếu không fallback |
| WebTestClient deadline | `WebTestClient.Builder.responseTimeout(Duration)` | Thời gian test client chờ response theo API test | Test thất bại nếu exchange/response chờ quá lâu |
| StepVerifier deadline | `verify(Duration)` | Thời gian thật để hoàn thành **kịch bản assertion** | AssertionError; không tự tạo HTTP 504 |
| Server/gateway timeout | Reverse proxy, load balancer hoặc ứng dụng | Chính sách phía server/hạ tầng | Có thể trả 504/408 hoặc đóng connection; tùy tầng |

Không nhầm chúng:

- `Mono.timeout` có thể đặt deadline trên body publisher của caller, nhưng không cấu hình riêng TCP connect, TLS hay pool.
- `Flux.timeout(Duration)` với stream thông thường kiểm soát **khoảng chờ tín hiệu tiếp theo** (bao gồm tín hiệu đầu); nó không nhất thiết là tổng thời lượng của stream.
- `HttpClient.responseTimeout` của Reactor Netty không nên được gọi là deadline end-to-end tuyệt đối. Nó giúp giới hạn khoảng chờ đọc response; vẫn cần timeout tổng ở tầng nghiệp vụ nếu contract yêu cầu.
- `verify(Duration)` chỉ bảo vệ JUnit test. Khi hết hạn, test ném AssertionError; nó không biến Mono thành onError(TimeoutException).
- `WebTestClient.responseTimeout` kiểm soát hành vi test client, không tự thay đổi timeout mà production WebClient dùng.

### 3.1. Ví dụ cấu hình Reactor Netty client

```java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
        .responseTimeout(Duration.ofSeconds(3));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
```

Cần import `io.netty.channel.ChannelOption`, `reactor.netty.http.client.HttpClient` và `org.springframework.http.client.reactive.ReactorClientHttpConnector`. Đây là client outbound, không thay đổi cấu hình embedded server đang nhận HTTP.

Nếu dùng pool riêng, cấu hình `maxConnections`, `pendingAcquireMaxCount`, `pendingAcquireTimeout` và lifecycle `dispose()`; không tạo pool mới cho từng request.

### 3.2. Timeout là lỗi, nhưng chưa chắc HTTP 504

Nếu WebClient bên trong service gặp `TimeoutException`, service phải quyết định mapping lỗi: có thể trả 504, 503, fallback hoặc retry tùy API contract. Reactor không tự chuyển tất cả timeout thành 504 Gateway Timeout.

Client disconnect cũng không phải 4xx/5xx do server chủ động tạo. Một socket bị đóng giữa body có thể khiến client nhận `PrematureCloseException` hoặc `WebClientRequestException` tùy vị trí lỗi và connector. Vì thế test transport nên assert nhóm lỗi I/O/timeout phù hợp thay vì ép một chuỗi message stacktrace.

## 4. Mô phỏng phản hồi chậm ở controller

Ví dụ controller:

```java
@RestController
class DelayController {

    @GetMapping("/delay")
    public Mono<String> delayed() {
        return Mono.delay(Duration.ofMillis(400))
                .thenReturn("slow-ok");
    }
}
```

`Mono.delay` đặt lịch một tín hiệu sau 400 ms, không chặn event loop. `thenReturn` bỏ giá trị tick (số 0) và phát chuỗi. **Đây là ứng dụng trả kết quả chậm**, không phải mô phỏng TCP handshake hoặc DNS.

Test ở tầng publisher:

```java
StepVerifier.withVirtualTime(
        () -> new DelayController().delayed())
        .expectSubscription()
        .expectNoEvent(Duration.ofMillis(399))
        .thenAwait(Duration.ofMillis(1))
        .expectNext("slow-ok")
        .verifyComplete();
```

Dùng `withVirtualTime` cần **tạo publisher trong Supplier** để scheduler nhận virtual time. Tạo Mono.delay trước khi kích hoạt virtual time có thể khiến phép thử chờ thật hoặc thất bại.

Test HTTP thật:

```java
client.get().uri("/delay")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("slow-ok");
```

Test HTTP chạy chậm khoảng 400 ms thực. Nó kiểm tra endpoint qua HTTP nhưng không đo độ trễ kết nối WAN.

## 5. Mô phỏng upstream phản hồi chậm bằng MockWebServer

### 5.1. Delay headers: server chưa trả status line/headers

```java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .setHeadersDelay(700, TimeUnit.MILLISECONDS)
        .setBody("delayed"));

Mono<String> response = WebClient.builder()
        .baseUrl(server.url("/").toString())
        .build()
        .get()
        .uri("/work")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofMillis(150));
```

Vì mock server cố ý chờ 700 ms trước khi gửi headers nhưng publisher timeout sau 150 ms, caller thường nhận `TimeoutException` do Reactor `timeout`. Kịch bản này xác nhận timeout ở tầng publisher; nó không chứng minh engine connect timeout.

### 5.2. Delay body: đã nhận headers nhưng chậm có nội dung

```java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "text/plain")
        .setBody("body-is-late")
        .setBodyDelay(500, TimeUnit.MILLISECONDS));
```

Ở đây server gửi headers trước, chờ rồi mới gửi body. Có thể kiểm tra response timeout của Reactor Netty hoặc kiểm tra tổng thời gian bằng Mono.timeout. Nếu dùng `retrieve().toBodilessEntity()`, test có thể thành công ngay khi headers tới và **không chứng minh body đã được đọc**; muốn kiểm tra body hãy dùng `bodyToMono(String.class)`.

### 5.3. Throttle từng chunk: băng thông thấp hoặc “đứng” giữa body

```java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "text/plain")
        .setBody("abcdefgh")
        .throttleBody(1, 300, TimeUnit.MILLISECONDS));
```

Mỗi 300 ms truyền một byte. Nếu Reactor Netty `responseTimeout` nhỏ hơn khoảng cách giữa các lần đọc, caller có thể nhận read timeout. Đừng kết luận chắc chắn rằng toàn body phải kết thúc trong 300 ms: `responseTimeout` không phải tổng deadline của response.

### 5.4. Socket đóng nửa chừng

```java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "text/plain")
        .setBody("x".repeat(8192))
        .setSocketPolicy(
                SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY));
```

MockWebServer đóng connection trong lúc body chưa hoàn tất. Khi response có `Content-Length` của toàn body, client nhận body thiếu và thường phát I/O error thay vì trả chuỗi thành công.

Giá trị lỗi cụ thể có thể là `PrematureCloseException`, `WebClientRequestException` hoặc exception wrapped từ Netty theo phiên bản và điểm lỗi. Test nên yêu cầu terminal error và nếu cần phân loại, duyệt cause chain thay vì phụ thuộc message thay đổi theo version.

### 5.5. Socket đóng ngay từ đầu

`SocketPolicy.DISCONNECT_AT_START` mô phỏng remote đóng trước khi xử lý request. Nó khác với disconnect nửa body. Một số HTTP client có thể retry khi connection đóng sớm nếu request an toàn; test phải kiểm soát policy retry và số response được enqueue, tránh kết luận sai từ một lần close.

Không mặc định TCP reset tương đương HTTP status 503. Khi TCP bị reset, server có thể chưa gửi bất kỳ status nào.

## 6. Upload chậm và dữ liệu request body từ từ

WebFlux có thể nhận publisher của request body; client có thể cung cấp data theo từng phần. Với NDJSON, mỗi object được encode và flush theo media type streaming.

```java
record SensorLine(long seq) {}

Flux<SensorLine> slowLines =
        Flux.interval(Duration.ofMillis(200))
                .take(3)
                .map(i -> new SensorLine(i));

Mono<Long> count = webClient.post()
        .uri("/lab/upload")
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(BodyInserters.fromPublisher(
                slowLines, SensorLine.class))
        .retrieve()
        .bodyToMono(Long.class);
```

Đoạn trên cần các import WebClient, MediaType và BodyInserters; biến `webClient` là một client đã trỏ tới HTTP server thực. Server có thể nhận:

```java
@PostMapping(
        value = "/lab/upload",
        consumes = MediaType.APPLICATION_NDJSON_VALUE)
public Mono<Long> upload(@RequestBody Flux<SensorLine> lines) {
    return lines.count();
}
```

Response phát khi request publisher hoàn tất vì `count()` cần đếm đủ các item. Với ba item và khoảng trễ 200 ms mỗi item, response không thể hoàn tất tức thì như một body đã được gửi sẵn. Tuy nhiên, elapsed time trên máy CI còn phụ thuộc scheduler và overhead network, nên **không assert chính xác 600 ms**.

Với upload lớn, phải giới hạn kích thước từng item và tổng số phần tử/bộ nhớ. Nếu client đóng kết nối giữa upload, server có thể nhận cancel hoặc error; cần đảm bảo các tài nguyên tạm (file, stream, DB session) được giải phóng. Nếu cần test upload bandwidth rất thấp, dùng `MockWebServer`/proxy hoặc client stream có controlled pace thay vì `Thread.sleep` trong controller.

## 7. SSE, client disconnect và cancellation

### 7.1. Luồng phản hồi không có điểm kết thúc

Ví dụ server phát một SSE mỗi 120 ms:

```java
@GetMapping(
        value = "/lab/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofMillis(120))
            .map(i -> ServerSentEvent.<String>builder()
                    .id(Long.toString(i))
                    .data("tick-" + i)
                    .build())
            .doFinally(signal ->
                    System.out.println("events ended: " + signal));
}
```

`ServerSentEvent` cho phép client nhận nhiều bản ghi trên một HTTP response. Phản hồi này không có `onComplete` nếu upstream dùng `Flux.interval` vô hạn.

Client chỉ lấy hai sự kiện rồi dừng:

```java
Flux<String> firstTwo = webClient.get()
        .uri("/lab/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(new ParameterizedTypeReference<
                ServerSentEvent<String>>() {})
        .map(ServerSentEvent::data)
        .take(2);

StepVerifier.create(firstTwo)
        .expectNext("tick-0", "tick-1")
        .verifyComplete();
```

Ở phía **client**, `take(2)` hoàn tất sau hai event. Ở phía upstream, nó gửi `cancel` và network adapter thường đóng/cleanup response body. Server có thể quan sát `SignalType.CANCEL` sau khi phát hiện disconnect. Không được khẳng định callback server luôn chạy ngay trong cùng một millisecond với assertion phía client.

### 7.2. Khác biệt giữa cancellation chủ động và mất kết nối ngoài ý muốn

- `take(2)` hoặc `dispose()`: caller chủ động ngừng tiêu thụ. Đó là cách **deterministic** để kiểm tra cancellation của Reactive Streams.
- User đóng tab hoặc proxy cắt socket: hệ thống biết thông qua transport khi I/O phát hiện disconnect; thời điểm có thể khác nhau, nhất là khi server chưa ghi dữ liệu mới.
- `MockWebServer` cưỡng bức ngắt socket: thử nghiệm khả năng WebClient phát hiện broken response.
- `Mono.timeout`: khi quá hạn, nó cancel subscription upstream rồi phát TimeoutException downstream; đây vẫn không phải bằng chứng server đã hoàn tất cleanup ngay lập tức.

Với SSE dài hạn, có thể gửi event/heartbeat theo chu kỳ để tăng cơ hội phát hiện client đã đi. Không tạo heartbeat quá dày gây tốn băng thông hoặc CPU. Client phải xử lý reconnect và `Last-Event-ID` nếu contract yêu cầu resume; không tự giả định server lưu mọi event.

### 7.3. Kiểm tra doFinally(CANCEL)

Có thể test cancellation **ở tầng Flux**, tách khỏi timing của socket:

```java
AtomicReference<SignalType> observed = new AtomicReference<>();

Flux<Integer> source = Flux.range(1, 100)
        .doFinally(observed::set);

StepVerifier.create(source, 2)
        .expectNext(1, 2)
        .thenCancel()
        .verify();

assertEquals(SignalType.CANCEL, observed.get());
```

`StepVerifier.thenCancel()` chủ động hủy. `doFinally` được đặt **trên source**, trước chỗ downstream hủy; nếu đặt sau `take(2)`, callback phía downstream có thể thấy COMPLETE trong khi upstream thực sự bị cancel.

`doFinally` hợp lý để ghi metric/log hoặc release các tài nguyên **đồng bộ** được quản lý tại đó. Nếu cleanup là publisher bất đồng bộ, dùng `usingWhen` hoặc lifecycle API thích hợp; không gọi `connection.close().subscribe()` vô quản lý rồi tuyên bố leak đã được khắc phục.

## 8. Cách kiểm tra lỗi và timeout mà không nuốt lỗi

Một service có thể map timeout thành lỗi nghiệp vụ:

```java
public Mono<String> fetchWithDeadline(WebClient webClient) {
    return webClient.get()
            .uri("/remote/data")
            .retrieve()
            .bodyToMono(String.class)
            .timeout(Duration.ofSeconds(2))
            .onErrorMap(
                    TimeoutException.class,
                    ex -> new UpstreamTimeoutException(ex));
}
```

`UpstreamTimeoutException` là exception nghiệp vụ do ứng dụng tự định nghĩa; đoạn code này mang tính minh họa và cần import `TimeoutException`. Không viết `onErrorResume(e -> Mono.just("OK"))` cho mọi lỗi vì có thể che lỗi kết nối hoặc trả dữ liệu giả như thật.

Với HTTP proxy/service gateway, chỉ trả 504 khi đó là contract đúng; có thể kết hợp `@RestControllerAdvice` hoặc `onErrorResume` trong functional endpoint để map lỗi thành `ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)`.

```java
return webClient.get()
        .uri("/remote/data")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(2))
        .map(ResponseEntity::ok)
        .onErrorResume(TimeoutException.class, ex ->
                Mono.just(ResponseEntity
                        .status(HttpStatus.GATEWAY_TIMEOUT)
                        .body("upstream timed out")));
```

Đoạn này là minh họa riêng cho mapping lỗi; phải đảm bảo status và body kiểu trả về nhất quán với controller thật. Không map tất cả `IOException` thành 504; một kết nối từ chối hoặc TLS handshake fail có thể đáng trả 502/503 tùy API contract.

### 8.1. Retry cần cẩn trọng

Retry trên timeout có thể làm request được gửi lại trong khi remote đã xử lý xong tác vụ ban đầu. Với GET thuần đọc, retry có giới hạn và backoff thường hợp lý hơn. Với POST/PUT có side effect, chỉ retry khi operation idempotent hoặc có idempotency key được server thực thi.

Không đặt `retry()` vô hạn, đặc biệt trước một timeout đã cố định quá thấp; test “đúng” nhưng production có thể tạo request storm.

### 8.2. Error từ transport có thể xuất hiện ở những thời điểm khác nhau

- Không kết nối được: error xảy ra trước HTTP response status.
- Headers đến nhưng body đứt: client có thể thấy status 200 trước khi body publisher phát error.
- Chunk cuối cùng thất lạc: body parser có thể chờ đủ Content-Length hoặc nhận premature-close.
- Client timeout sau khi server commit: server đã thực hiện side effect, dù caller nhìn thấy TimeoutException.

Vì vậy test phải xác minh đúng tầng và giai đoạn. Một assertion chỉ kiểm tra HTTP status 200 không chứng minh toàn bộ body đã được đọc trọn vẹn.

## 9. Project Java 17 + Spring Boot 3.3.5 chạy được

Project dưới đây chạy Spring WebFlux trên cổng ngẫu nhiên khi integration test. Nó có ba nhóm kiểm thử:

1. **WebTestClient + RANDOM_PORT:** endpoint nhanh/chậm và response status/body trên HTTP thật.
2. **StepVerifier:** điều khiển virtual time, timeout và cancellation độc lập với socket.
3. **MockWebServer + WebClient:** delay headers, throttle body, forced socket disconnect.

Không cần Internet trong quá trình chạy test ngoài bước Maven tải dependency lần đầu.

### 9.1. Cấu trúc

```text
webflux-fault-simulation/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── FaultSimulationApplication.java
    │   └── LabController.java
    └── test/java/demo/
        ├── WebFluxHttpIntegrationTest.java
        ├── ReactorTimingTest.java
        └── MockUpstreamFailureTest.java
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-fault-simulation</artifactId>
    <version>1.0.0</version>

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
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
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

Spring Boot parent cung cấp dependency management cho Spring WebFlux, Reactor Netty và JUnit 5; MockWebServer được khóa version 4.12.0 để dùng API `okhttp3.mockwebserver.MockResponse`. OkHttp 5 dùng API khác nên không tự nâng version mà giữ nguyên code test 4.x.

### 9.3. FaultSimulationApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FaultSimulationApplication {
    public static void main(String[] args) {
        SpringApplication.run(FaultSimulationApplication.class, args);
    }
}
```

### 9.4. LabController.java

```java
package demo;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/lab")
public class LabController {

    public record SensorLine(long seq) {
    }

    @GetMapping("/fast")
    public Mono<String> fast() {
        return Mono.just("fast-ok");
    }

    // Mô phỏng handler chậm, không phải TCP connect chậm.
    @GetMapping("/delayed")
    public Mono<String> delayed() {
        return Mono.delay(Duration.ofMillis(400))
                .thenReturn("slow-ok");
    }

    // Không phát headers/body, không terminal.
    @GetMapping("/never")
    public Mono<String> never() {
        return Mono.never();
    }

    // SSE dài hạn, client có thể hủy sau n sự kiện.
    @GetMapping(
            value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofMillis(120))
                .map(index -> ServerSentEvent.<String>builder()
                        .id(Long.toString(index))
                        .data("tick-" + index)
                        .build());
    }

    // Request body đến dần từng NDJSON object.
    @PostMapping(
            value = "/upload",
            consumes = MediaType.APPLICATION_NDJSON_VALUE)
    public Mono<Long> upload(
            @RequestBody Flux<SensorLine> lines) {
        return lines.count();
    }
}
```

`Mono.delay` và `Flux.interval` đều sử dụng scheduler, không block Reactor Netty event loop. `never()` cố ý không complete và không gửi response; trong production, một endpoint như vậy cần deadline và các cơ chế cleanup.

### 9.5. WebFluxHttpIntegrationTest.java

```java
package demo;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebFluxHttpIntegrationTest {

    @Autowired
    WebTestClient testClient;

    @LocalServerPort
    int port;

    private WebClient webClient() {
        return WebClient.builder()
                .baseUrl("http://localhost:" + port)
                .build();
    }

    @Test
    @Timeout(10)
    void fastEndpointReturnsImmediately() {
        testClient.get()
                .uri("/lab/fast")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("fast-ok");
    }

    @Test
    @Timeout(10)
    void delayedHandlerEventuallyReturnsHttp200() {
        testClient.get()
                .uri("/lab/delayed")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("slow-ok");
    }

    @Test
    @Timeout(10)
    void publisherTimeoutCancelsNeverEndingRequest() {
        StepVerifier.create(
                webClient().get()
                        .uri("/lab/never")
                        .retrieve()
                        .bodyToMono(String.class)
                        .timeout(Duration.ofMillis(200)))
                .expectError(java.util.concurrent.TimeoutException.class)
                .verify(Duration.ofSeconds(3));
    }

    @Test
    @Timeout(10)
    void clientCanStopReadingSseAfterTwoEvents() {
        Flux<String> firstTwo = webClient().get()
                .uri("/lab/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .retrieve()
                .bodyToFlux(new ParameterizedTypeReference<
                        ServerSentEvent<String>>() {})
                .map(ServerSentEvent::data)
                .take(2);

        StepVerifier.create(firstTwo)
                .expectNext("tick-0", "tick-1")
                .verifyComplete();
    }

    @Test
    @Timeout(10)
    void slowNdjsonUploadIsConsumedAsFlux() {
        Flux<LabController.SensorLine> lines =
                Flux.interval(Duration.ofMillis(150))
                        .take(3)
                        .map(LabController.SensorLine::new);

        StepVerifier.create(
                webClient().post()
                        .uri("/lab/upload")
                        .contentType(MediaType.APPLICATION_NDJSON)
                        .body(BodyInserters.fromPublisher(
                                lines, LabController.SensorLine.class))
                        .retrieve()
                        .bodyToMono(Long.class))
                .expectNext(3L)
                .verifyComplete();
    }
}
```

Giải thích:

- Hai test đầu dùng `WebTestClient` đã cấu hình với cổng server thật, không chỉ gọi controller trực tiếp.
- Test `/lab/never` có timeout ở **publisher phía client**. Nó phát `TimeoutException` ngay cả khi server không hề trả HTTP status; không assert 504.
- Test SSE dùng `take(2)`: client nhận hai sự kiện rồi cancel subscription. Không assert chính xác thời điểm socket phía server đóng vì network cancellation có thể được quan sát bất đồng bộ.
- Test upload tạo ba object theo lịch 150 ms và truyền NDJSON; server dùng `Flux.count()` nên phản hồi 3 sau khi body stream hoàn tất.
- `@Timeout(10)` là watchdog của JUnit cho từng test, không thay thế timeout nghiệp vụ hay `StepVerifier.verify(Duration)`.

### 9.6. ReactorTimingTest.java

```java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactorTimingTest {

    private final LabController controller = new LabController();

    @Test
    void delayedMonoUsesVirtualTime() {
        StepVerifier.withVirtualTime(controller::delayed)
                .expectSubscription()
                .expectNoEvent(Duration.ofMillis(399))
                .thenAwait(Duration.ofMillis(1))
                .expectNext("slow-ok")
                .verifyComplete();
    }

    @Test
    void timeoutOperatorEmitsTimeoutException() {
        StepVerifier.withVirtualTime(
                        () -> Mono.delay(Duration.ofSeconds(10))
                                .timeout(Duration.ofSeconds(3)))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(3))
                .expectError(TimeoutException.class)
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void cancellationIsObservableOnUpstreamFlux() {
        AtomicReference<SignalType> signal =
                new AtomicReference<>();

        Flux<Integer> source = Flux.range(1, 100)
                .doFinally(signal::set);

        StepVerifier.create(source, 2)
                .expectNext(1, 2)
                .thenCancel()
                .verify();

        assertEquals(SignalType.CANCEL, signal.get());
    }
}
```

Ba test này xác minh semantics reactive **không cần network**. Chúng không thay thế các bài integration test ở mục trước.

### 9.7. MockUpstreamFailureTest.java

```java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.SocketPolicy;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.test.StepVerifier;

class MockUpstreamFailureTest {

    private WebClient webClient(
            MockWebServer server, Duration responseTimeout) {
        HttpClient httpClient = HttpClient.create()
                .responseTimeout(responseTimeout);

        return WebClient.builder()
                .baseUrl(server.url("/").toString())
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }

    @Test
    @Timeout(10)
    void healthyResponseIsFullyRead() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.start();
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader("Content-Type", "text/plain")
                    .setBody("upstream-ok"));

            StepVerifier.create(
                    webClient(server, Duration.ofSeconds(2))
                            .get().uri("/health")
                            .retrieve()
                            .bodyToMono(String.class))
                    .expectNext("upstream-ok")
                    .verifyComplete();
        }
    }

    @Test
    @Timeout(10)
    void delayedHeadersTriggerPublisherTimeout() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.start();
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .setHeadersDelay(700, TimeUnit.MILLISECONDS)
                    .setBody("eventually"));

            StepVerifier.create(
                    webClient(server, Duration.ofSeconds(3))
                            .get().uri("/delayed-headers")
                            .retrieve()
                            .bodyToMono(String.class)
                            .timeout(Duration.ofMillis(150)))
                    .expectError(TimeoutException.class)
                    .verify(Duration.ofSeconds(4));
        }
    }

    @Test
    @Timeout(10)
    void throttledBodyTriggersResponseReadTimeout() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.start();
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader("Content-Type", "text/plain")
                    .setBody("abcdefgh")
                    .throttleBody(1, 300, TimeUnit.MILLISECONDS));

            StepVerifier.create(
                    webClient(server, Duration.ofMillis(120))
                            .get().uri("/throttled")
                            .retrieve()
                            .bodyToMono(String.class))
                    .expectError()
                    .verify(Duration.ofSeconds(4));
        }
    }

    @Test
    @Timeout(10)
    void disconnectMidBodyFailsBodyConsumption() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.start();
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader("Content-Type", "text/plain")
                    .setBody("x".repeat(8192))
                    .setSocketPolicy(
                            SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY));

            StepVerifier.create(
                    webClient(server, Duration.ofSeconds(3))
                            .get().uri("/broken-body")
                            .retrieve()
                            .bodyToMono(String.class))
                    .expectError()
                    .verify(Duration.ofSeconds(4));
        }
    }
}
```

Các test này cố ý không ép tất cả lỗi transport về cùng một Java exception. Với delayed headers, timeout do `Mono.timeout` phát ra nên có thể kiểm tra `TimeoutException` trực tiếp. Với read timeout hoặc broken socket, lớp lỗi có thể khác theo version Netty, vì vậy kịch bản tối thiểu kiểm tra phải **error**, không được complete thành một response body đầy đủ.

Test `throttledBodyTriggersResponseReadTimeout` có thể mở rộng bằng phân loại cause chain của `ReadTimeoutException` nếu hệ thống cần contract chi tiết. Nên có thêm assert request thực sự đến MockWebServer bằng `takeRequest` khi mục tiêu là xác minh path/method; ví dụ ở đây tập trung vào failure injection và response processing.

### 9.8. Chạy và kết quả dự kiến

Tại thư mục chứa `pom.xml`:

```bash
mvn test
```

Với Java 17+, Maven và dependency đã tải được, dự kiến JUnit chạy **12 test case**: 5 HTTP integration, 3 Reactor timing/cancellation và 4 upstream fault injection. Kỳ vọng tất cả test đều pass khi môi trường loopback/CI đáp ứng giới hạn thời gian và socket policy hoạt động như thiết kế.

Không có một stdout cố định để chép nguyên văn vì các dòng log Boot, Netty và thời gian Maven phụ thuộc môi trường. Kết quả quan trọng là số test và không có failure/error.

Có thể chạy riêng:

```bash
mvn -Dtest=ReactorTimingTest test
mvn -Dtest=WebFluxHttpIntegrationTest test
mvn -Dtest=MockUpstreamFailureTest test
```

Chạy ứng dụng phục vụ endpoint mẫu:

```bash
mvn spring-boot:run
```

Ở terminal khác:

```bash
curl -i http://localhost:8080/lab/fast
curl -i http://localhost:8080/lab/delayed
curl -N http://localhost:8080/lab/events
```

`curl -N` vô hiệu hóa output buffering của curl để dễ nhìn các SSE event đến theo thời gian. Dừng stream bằng Ctrl+C. Server có thể nhận tín hiệu disconnect ở thời điểm khác nhau, nhất là khi connection đang idle.

## 10. Quan sát cancellation và tài nguyên

### 10.1. DoFinally ở đúng vị trí

Ví dụ pipeline:

```java
Flux<Long> source = Flux.interval(Duration.ofMillis(100))
        .doFinally(signal -> logSignal(signal));

return source.take(2);
```

`logSignal` là method minh họa, không thuộc project chạy ở mục 9. Khi downstream lấy đủ hai item, source thường thấy `SignalType.CANCEL`, trong khi pipeline sau `take(2)` có thể hoàn tất bình thường. Đặt `doFinally` ở vị trí phù hợp khi muốn phân biệt hai phía.

### 10.2. Không suy luận rollback chỉ từ CANCEL

Nếu response stream bị hủy, một transaction reactive *đang hoạt động và được Spring quản lý* có thể rollback trên cancel theo chính sách Spring 5.3+. Nhưng nếu commit đã xong trước khi client disconnect, cancel không thể hoàn tác commit.

Với R2DBC, đóng connection/rollback cần hoàn tất theo lifecycle của transaction manager. Với resource reactive tự quản lý, dùng `Mono.usingWhen`/`Flux.usingWhen` cho async cleanup, không gọi `close().subscribe()` trong `doFinally` rồi bỏ mất lỗi.

### 10.3. DataBuffer và memory leak

`DataBuffer` có thể chứa Netty pooled memory. Khi đọc raw bytes hoặc tự xử lý streaming với `DataBuffer`, mỗi buffer cần được consume/release đúng contract. Thao tác thấp tầng có thể cần `DataBufferUtils.release` hoặc `DataBufferUtils.releaseConsumer`; nếu dùng codecs chuẩn `bodyToMono(String.class)` hoặc `bodyToFlux(DTO.class)`, framework thường quản lý phần giải mã.

Không dùng `collectList` cho stream vô hạn hoặc không giới hạn kích thước, không tự buffer toàn bộ upload/response lớn. Test tải thấp có thể pass nhưng production bị tràn bộ nhớ.

### 10.4. Connection pool sau cancel

Khi dùng pooled HTTP client, cancel một response thường khiến connection bị đóng hoặc xử lý theo tình trạng có thể tái sử dụng. **Không** mặc định mọi connection bị cancel đều trở về pool ở trạng thái reusable; với response body dở dang, engine có thể loại bỏ channel.

Theo dõi active/idle/pending acquire, thời gian acquire và số connection bị dispose. Test pool exhaustion với maxConnections thấp, một stream bị cancel, rồi kiểm tra request mới hoàn thành trong deadline có giá trị hơn việc chỉ assert log doFinally.

## 11. Phân biệt bốn dạng timeout thường bị lẫn

### 11.1. Connect timeout

Nếu destination không hoàn tất TCP handshake, engine có thể phát connect timeout. Để test chính xác, dùng controlled network fault (proxy/drop), không dùng `Mono.delay` trong controller. Server của controller chỉ chạy **sau** khi connection đã được chấp nhận và request HTTP đã được định tuyến.

### 11.2. Response timeout

Nếu server chậm gửi headers hoặc giữa các chunk, Reactor Netty response timeout có thể được kích hoạt. Dùng MockWebServer để tái hiện hai tình huống riêng: `setHeadersDelay` và `throttleBody`. Test phải thực sự tiêu thụ body, không chỉ lấy status.

### 11.3. Business timeout

`Mono.timeout(Duration)` tính từ subscription tới tín hiệu tương ứng. Nếu response chậm hơn hạn, caller cancel upstream rồi phát `TimeoutException`. Nếu xử lý retry/fallback, đặt operator đúng vị trí để không vô tình thay đổi scope của deadline.

Ví dụ:

```java
Mono<String> result = webClient.get()
        .uri("/remote")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(2));
```

Khi body được tổng hợp thành Mono, timeout này giới hạn thời gian chờ một kết quả duy nhất; với Flux nhiều event, một timeout mặc định có thể được reset sau mỗi item. Không đánh đồng điều đó với “phải kết thúc toàn stream trong hai giây”.

### 11.4. Test timeout

`StepVerifier.verify(Duration)`, JUnit `@Timeout` và WebTestClient responseTimeout là công cụ của test harness. Hạn test nên dư so với latency hợp lệ để giảm flaky, nhưng vẫn phải đủ ngắn để phát hiện treo.

Ví dụ một unit test dùng virtual time không cần chờ hai giây thực chỉ để đòi kết quả bị trễ hai giây logic.

## 12. Thiết kế ma trận test cho một API thật

| Tình huống | Setup | Kỳ vọng | Không nên assert |
| --- | --- | --- | --- |
| Healthy | Mock upstream trả ngay | Status/body đúng | Millisecond elapsed chính xác |
| Delay headers | `setHeadersDelay` lớn hơn client timeout | Timeout error, request không treo | Giả vờ đó là TCP connect timeout |
| Delay body | Headers nhanh, body chậm | Caller timeout hoặc hoàn thành theo cấu hình | Chỉ kiểm tra status 200 |
| Throttle chunks | `throttleBody`, gap lớn | Read timeout đúng lớp logic | Một exception message cố định qua mọi version |
| Disconnect mid-body | `DISCONNECT_DURING_RESPONSE_BODY` | Body publisher phát error | Server phải trả 500 sau socket close |
| Server never completes | `Mono.never()` | Publisher timeout và cancel | HTTP 504 tự động nếu chưa có error handler |
| SSE lấy hai event | Stream dài hạn và `take(2)` | Hai event, client-side complete/cancel upstream | Server doFinally chạy đúng cùng thời điểm test |
| Upload chậm | `Flux.interval` request body | Server consume đủ item, trả count | Assert elapsed đúng số ms tuyệt đối |
| Retry sau timeout | Server ghi sự kiện rồi giữ connection | Không nhân đôi side effect khi có idempotency | Retry tự động đúng cho mọi POST |
| Pool cạn | Pool nhỏ, nhiều stream giữ mở | Request chờ acquire hoặc fail có deadline | Tăng thread là cách sửa pool |
| TLS handshake fail | Cert không hợp lệ trong fake TLS endpoint | Handshake exception | Tắt certificate verification |
| DNS/connection fail | Controlled resolver/network fault | Không nhận HTTP status; lỗi transport | Phụ thuộc một IP Internet bất kỳ |

Ma trận này giúp test đọc được khi một trường hợp fail: failure thuộc logic, HTTP protocol, transport hay test harness.

## 13. Lỗi thường gặp và hướng sửa

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi `Mono.delay` là “TCP chậm” | Test bỏ sót connect/TLS/packet loss | Phân loại rõ delayed handler và network fault |
| Chỉ dùng `bindToController` để test disconnect | Không có socket thật để ngắt | Dùng RANDOM_PORT, WebClient và MockWebServer/proxy |
| Không subscribe `Mono`/`Flux` trong test | Không chạy request | Dùng WebTestClient.exchange hoặc StepVerifier.verify |
| Chỉ assert HTTP status | Bỏ sót body thiếu hoặc socket close giữa response | Consume body và xác minh terminal |
| Dùng `verify()` với source không complete | CI có thể treo | `verify(Duration)` và kịch bản cancel |
| Dùng `Thread.sleep` để đồng bộ callback | Test flaky, chậm | StepVerifier virtual time hoặc test await có timeout |
| Đặt mọi timeout bằng nhau | Không biết nguyên nhân lỗi | Đặt connect, response, operation và test deadlines theo tầng |
| Cho rằng `Flux.timeout` là tổng deadline stream | Stream nhiều event vẫn có thể kéo dài | Dùng chính sách deadline tổng khác nếu cần |
| Bắt đúng message Netty exception | Dễ vỡ theo version | Assert error contract/cause chain |
| Mong browser disconnect cho 504 | Client đã rời đi, không còn response hợp lệ | Quan sát cancel, cleanup và log |
| Log PII trong wiretap | Rò rỉ request/response data | Bật có kiểm soát và redact |
| Bật retry vô hạn | Request storm hoặc side effect trùng | Giới hạn retry, backoff, idempotency |
| Bọc `block()` trong controller | Chặn event loop, gây timeout dây chuyền | Compose reactive operator |
| Không giải phóng raw DataBuffer | Leak pooled direct memory | Release theo contract hoặc dùng codec chuẩn |
| Giữ DB transaction quanh SSE vô hạn | Pool database bị chiếm lâu | Transaction ngắn cho snapshot, stream ngoài transaction |
| Test khẳng định server thấy CANCEL ngay | Phụ thuộc adapter/socket timing | Assert logic cancel ở unit, dùng await có hạn cho integration |
| Test IP công cộng không phản hồi | Route/firewall thay đổi | Dùng local deterministic fake/proxy |
| Dùng fixed port cho mọi test | Port collision trong CI | RANDOM_PORT / MockWebServer tự chọn cổng |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `Mono.delay` trong controller mô phỏng TCP connect chậm được không?  
**Đáp án:** Không. Nó mô phỏng độ trễ xử lý/response sau khi HTTP request đã tới handler.

**Câu 2.** Khi nào dùng `WebTestClient.bindToController`?  
**Đáp án:** Khi kiểm tra routing, codec, status, body, validation mà không cần socket; không dùng nó để chứng minh disconnect/TLS behavior.

**Câu 3.** Cách nào kiểm tra HTTP thật trên cổng ngẫu nhiên?  
**Đáp án:** `@SpringBootTest(webEnvironment=RANDOM_PORT)` và WebTestClient/WebClient kết nối tới `@LocalServerPort`.

**Câu 4.** Muốn upstream chậm gửi headers bằng MockWebServer?  
**Đáp án:** `MockResponse.setHeadersDelay(...)`. Đừng nhầm nó với TCP connect timeout.

**Câu 5.** Muốn mô phỏng socket đứt giữa response body?  
**Đáp án:** `SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY` và yêu cầu client tiêu thụ body.

**Câu 6.** `Mono.timeout` khác `WebTestClient.responseTimeout`?  
**Đáp án:** Mono.timeout thuộc pipeline ứng dụng và phát TimeoutException; WebTestClient responseTimeout là giới hạn của test client.

**Câu 7.** Khi một SSE client dùng `take(2)`, điều gì xảy ra?  
**Đáp án:** Client nhận hai item rồi complete ở phía downstream; upstream bị cancel. Server có thể thấy cancel sau khi transport phát hiện disconnect.

**Câu 8.** Vì sao không assert chính xác elapsed=400 ms cho `Mono.delay(400 ms)`?  
**Đáp án:** Scheduler, GC và tải CI tạo overhead; hãy test đúng giá trị và dùng timeout có khoảng đệm hoặc virtual time.

**Câu 9.** Nếu đã nhận status 200, có chắc body hoàn chỉnh?  
**Đáp án:** Không. Socket có thể đứt khi đang truyền body; cần consume body tới terminal.

**Câu 10.** Timeout client có bảo đảm server chưa ghi database không?  
**Đáp án:** Không. Side effect có thể hoàn tất trước khi caller timeout; cần idempotency và kiểm tra trạng thái.

**Câu 11.** `MockWebServer.throttleBody` hữu ích cho điều gì?  
**Đáp án:** Mô phỏng response body đến chậm theo chunk, kiểm tra read/response timeout.

**Câu 12.** Vì sao không dùng `Thread.sleep` để chứng minh cancellation?  
**Đáp án:** Không có ràng buộc đồng bộ rõ và dễ flaky; dùng StepVerifier/CountDownLatch/await có timeout theo tầng cần kiểm tra.

## 15. Ghi nhớ

- “Kết nối chậm” không phải một trạng thái duy nhất: phân biệt DNS, TCP, TLS, chờ headers, body/stream chậm và upload chậm.
- **StepVerifier + virtual time** kiểm tra logic thời gian nhanh; **WebTestClient mock** kiểm tra WebFlux HTTP abstraction; **RANDOM_PORT** và **MockWebServer** kiểm tra HTTP transport thật.
- `Mono.timeout` và `Flux.timeout` xử lý tín hiệu nghiệp vụ; Reactor Netty `responseTimeout` kiểm soát mạng; `verify(Duration)` và `WebTestClient.responseTimeout` bảo vệ test.
- Luôn tiêu thụ response body đến terminal nếu cần phát hiện disconnect giữa body.
- Khi client hủy SSE, upstream có thể nhận `CANCEL`; việc server nhận biết và cleanup có thể trễ do transport.
- MockWebServer 4.x cho phép `setHeadersDelay`, `setBodyDelay`, `throttleBody` và `SocketPolicy` để tạo kịch bản ổn định.
- Mọi fault-injection test cần deadline rõ ràng, không phụ thuộc Internet và không gắn assertion vào timing tuyệt đối.
- Timeout/disconnect không đồng nghĩa rollback business side effect; kết hợp cancellation cleanup, idempotency, metric và quản lý tài nguyên.

## 16. Tài liệu tham khảo

1. [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bind to controller/application context/server, HTTP assertions, streaming.
2. [Spring Boot 3.3 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): RANDOM_PORT, WebTestClient, @WebFluxTest.
3. [Reactor Netty – HTTP Client Reference](https://projectreactor.io/docs/netty/release/reference/http-client.html): response timeout, connect timeout, pool và lifecycle.
4. [Spring Framework – Reactive Core and Streaming](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): streaming, SSE heartbeat, DataBuffer và codec.
5. [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): HTTP client fluent API, outbound connector.
6. [Project Reactor – Testing and Virtual Time](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, virtual time và cancellation.
7. [Project Reactor – Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): delay/timeout/usingWhen.
8. [Project Reactor – Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): interval/take/timeout và backpressure.
9. [OkHttp MockWebServer 4.x API](https://square.github.io/okhttp/): scripted responses, MockResponse delay/throttle và SocketPolicy.
10. [Reactive Streams Specification](https://www.reactive-streams.org/): cancellation và Publisher/Subscriber semantics.

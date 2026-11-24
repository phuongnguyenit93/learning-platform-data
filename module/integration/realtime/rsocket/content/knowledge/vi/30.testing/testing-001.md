# Phân tầng kiểm thử: hàm xử lý, giao thức, tích hợp và toàn tuyến

Một ứng dụng RSocket có nhiều lớp cùng tham gia xử lý một request: logic nghiệp vụ, reactive pipeline, protocol frame, transport TCP/WebSocket, codec, metadata, bảo mật và hạ tầng triển khai. Một bài test chỉ gọi trực tiếp service không thể phát hiện route sai hoặc MIME type không tương thích; ngược lại, chỉ chạy end-to-end test khiến lỗi nhỏ khó định vị và làm vòng phản hồi chậm.

Chiến lược hiệu quả là phân tầng kiểm thử. Mỗi tầng có phạm vi, công cụ và loại lỗi cần phát hiện riêng:

| Tầng | Đối tượng kiểm thử | Hạ tầng cần có | Mục tiêu |
| --- | --- | --- | --- |
| Unit / hàm xử lý | Service, handler method, mapper, validator, reactive operator | JUnit, Mockito, Reactor Test | Kiểm tra logic nhanh, cô lập dependency |
| Protocol | RSocket interaction, frame semantics, demand, cancel, error, setup | RSocket Java client/server, test transport | Kiểm tra hai peer tuân thủ hợp đồng giao thức |
| Integration | Spring `@MessageMapping`, codec, metadata, security, transport và service thật | Spring Boot test, RSocketRequester | Kiểm tra các thành phần ứng dụng kết nối đúng với nhau |
| End-to-end | Browser/mobile/gateway, service, discovery, proxy, TLS và hệ thống phụ thuộc | Môi trường triển khai gần production | Xác minh hành vi thực tế trên toàn tuyến |

Không cần chạy mọi kịch bản ở mọi tầng. Hãy đặt test ở tầng thấp nhất có thể xác minh được hành vi, rồi bổ sung một số test ở tầng cao hơn cho các ranh giới quan trọng.

## 1. Bức tranh tổng thể của test pyramid

```text
                 /\
                /  \       End-to-end
               /    \      Ít test, chi phí cao
              /------\
             /        \    Integration
            /----------\   Kiểm tra các thành phần kết nối
           /            \
          /--------------\ Protocol
         /                \ Kiểm tra interaction và transport
        /------------------\
       /                    \ Unit
      /______________________\ Nhiều test, chạy nhanh
```

Unit test nên chiếm phần lớn vì nhanh và dễ chẩn đoán. Protocol test tập trung vào những đặc tính của RSocket mà mock không thể xác minh. Integration test kiểm tra cấu hình Spring, encoder/decoder, metadata và bảo mật. End-to-end test ít hơn nhưng phải đại diện cho các đường đi quan trọng của người dùng và vận hành.

Ví dụ với route `orders.create`:

1. Unit test xác minh `OrderService` kiểm tra tồn kho, lưu đơn và phát event đúng.
2. Protocol test xác minh request-response gửi một payload và nhận tối đa một payload phản hồi; stream tôn trọng demand và cancel.
3. Integration test gửi request qua `RSocketRequester`, xác minh route, JSON decoder, Bean Validation, security và handler Spring.
4. End-to-end test đăng nhập từ web app, mở WSS qua proxy, tạo đơn và xác minh trạng thái xuất hiện trong hệ thống downstream.

## 2. Chuẩn bị dependency kiểm thử

Với Spring Boot, bộ test cơ bản thường đã bao gồm JUnit Jupiter, AssertJ, Mockito và Spring Test. Thêm `reactor-test` để kiểm tra `Mono`/`Flux`.

Ví dụ Gradle:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}
```

Nếu không dùng Spring Boot starter, khai báo các dependency test tương ứng:

```kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.mockito:mockito-junit-jupiter")
    testImplementation("org.assertj:assertj-core")
    testImplementation("io.projectreactor:reactor-test")
}
```

Giữ version Reactor Test tương thích với Reactor Core trong dependency management của ứng dụng. Không nâng riêng `reactor-test` lên một dòng version khác với Reactor Core chỉ để lấy API mới.

Khi test transport thực, cần dependency transport mà ứng dụng dùng, thường là `rsocket-transport-netty`. Nếu muốn dùng local transport cho test thuần protocol, thêm `rsocket-transport-local` cùng version với `rsocket-core`. Không cần thêm test transport nếu toàn bộ integration test đã chạy qua TCP/WebSocket thật.

## 3. Unit test cho service và handler

Unit test tập trung vào quyết định nghiệp vụ. Không mở socket, không tạo Spring ApplicationContext và không cần serialize payload qua mạng.

Ví dụ service nhận một reading, kiểm tra giới hạn và lưu repository:

```java
public record SensorReading(
        String deviceId,
        BigDecimal temperatureC,
        Instant measuredAt
) {}

public record StoredReading(String id, SensorReading reading) {}

public interface SensorRepository {
    Mono<StoredReading> save(SensorReading reading);
    Mono<SensorReading> findById(String id);
}

@Service
public class SensorService {

    private final SensorRepository repository;

    public SensorService(SensorRepository repository) {
        this.repository = repository;
    }

    public Mono<ReadingAccepted> store(SensorReading reading) {
        if (reading.temperatureC().compareTo(new BigDecimal("-40")) < 0
                || reading.temperatureC().compareTo(new BigDecimal("125")) > 0) {
            return Mono.error(new InvalidTemperatureException());
        }

        return repository.save(reading)
                .map(saved -> new ReadingAccepted(saved.id(), "ACCEPTED"));
    }
}
```

Test service với mock repository:

```java
@ExtendWith(MockitoExtension.class)
class SensorServiceTest {

    @Mock
    SensorRepository repository;

    @InjectMocks
    SensorService service;

    @Test
    void storesValidReading() {
        SensorReading reading = new SensorReading(
                "sensor-17", new BigDecimal("28.5"), Instant.parse("2026-11-22T10:00:00Z"));
        StoredReading saved = new StoredReading("reading-91", reading);

        when(repository.save(reading)).thenReturn(Mono.just(saved));

        StepVerifier.create(service.store(reading))
                .expectNext(new ReadingAccepted("reading-91", "ACCEPTED"))
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        verify(repository).save(reading);
    }

    @Test
    void rejectsTemperatureOutsideDomainRange() {
        SensorReading reading = new SensorReading(
                "sensor-17", new BigDecimal("160"), Instant.now());

        StepVerifier.create(service.store(reading))
                .expectError(InvalidTemperatureException.class)
                .verify(Duration.ofSeconds(5));

        verifyNoInteractions(repository);
    }
}
```

`StepVerifier` đăng ký vào publisher và xác minh các tín hiệu theo thứ tự. Test không gọi `block()` trên production pipeline và không cần sleep để chờ kết quả.

Handler có thể được test trực tiếp nếu mục tiêu chỉ là kiểm tra cách nó điều phối service:

```java
@Controller
public class SensorMessageHandler {

    private final SensorService service;

    public SensorMessageHandler(SensorService service) {
        this.service = service;
    }

    @MessageMapping("sensors.reading")
    public Mono<ReadingAccepted> receive(@Valid @Payload SensorReading reading) {
        return service.store(reading);
    }
}
```

```java
@ExtendWith(MockitoExtension.class)
class SensorMessageHandlerTest {

    @Mock
    SensorService service;

    @InjectMocks
    SensorMessageHandler handler;

    @Test
    void delegatesReadingToService() {
        SensorReading reading = new SensorReading(
                "sensor-17", new BigDecimal("28.5"), Instant.now());
        ReadingAccepted accepted = new ReadingAccepted("reading-91", "ACCEPTED");
        when(service.store(reading)).thenReturn(Mono.just(accepted));

        StepVerifier.create(handler.receive(reading))
                .expectNext(accepted)
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        verify(service).store(reading);
    }
}
```

Gọi trực tiếp `handler.receive(...)` không kiểm tra Spring route, argument resolver, `@Valid`, codec hoặc security interceptor. Các hành vi đó thuộc integration test.

## 4. Kiểm tra reactive pipeline với Reactor Test

Reactor Test cung cấp ba công cụ quan trọng:

- `StepVerifier`: mô tả kịch bản tín hiệu, demand, error, completion và cancellation.
- `TestPublisher`: chủ động phát `onNext`, `onError`, `onComplete` để kiểm tra consumer hoặc operator.
- `PublisherProbe`: xác minh một nhánh publisher có được subscribe, request hoặc cancel hay không.

### 4.1. Kiểm tra demand và cancellation

Ví dụ service chuyển đổi một stream readings. Test bắt đầu với demand bằng 0, sau đó chủ động yêu cầu từng phần tử:

```java
@Test
void respectsDemandAndCancelsUpstream() {
    TestPublisher<SensorReading> source = TestPublisher.create();

    Flux<String> result = source.flux()
            .map(reading -> reading.deviceId() + ":" + reading.temperatureC());

    StepVerifier.create(result, 0)
            .expectSubscription()
            .then(() -> source.assertSubscribers())
            .thenRequest(1)
            .then(() -> source.next(new SensorReading(
                    "sensor-17", new BigDecimal("28.5"), Instant.now())))
            .expectNext("sensor-17:28.5")
            .thenCancel()
            .verify(Duration.ofSeconds(5));

    source.assertCancelled();
    source.assertMaxRequested(1);
}
```

Test này xác minh subscriber không nhận dữ liệu trước khi yêu cầu. Sau `thenCancel()`, cancellation được truyền ngược tới source. Dùng `TestPublisher` để kiểm tra backpressure ở tầng reactive; cần thêm protocol test để xác minh demand được truyền qua RSocket thành `REQUEST_N`.

### 4.2. Kiểm tra nhánh fallback

`PublisherProbe` hữu ích khi service có fallback hoặc nhánh điều kiện:

```java
@Test
void usesFallbackWhenReadingIsMissing() {
    SensorRepository repository = Mockito.mock(SensorRepository.class);
    when(repository.findById("missing")).thenReturn(Mono.empty());

    PublisherProbe<SensorReading> fallback = PublisherProbe.of(
            Mono.just(new SensorReading(
                    "sensor-fallback", new BigDecimal("20.0"), Instant.now())));

    Mono<SensorReading> result = repository.findById("missing")
            .switchIfEmpty(fallback.mono());

    StepVerifier.create(result)
            .expectNextMatches(value -> value.deviceId().equals("sensor-fallback"))
            .expectComplete()
            .verify(Duration.ofSeconds(5));

    fallback.assertWasSubscribed();
    fallback.assertWasRequested();
}
```

Không chỉ xác minh giá trị cuối; hãy kiểm tra nhánh fallback thật sự được dùng nếu đó là điều cần bảo đảm.

### 4.3. Kiểm tra timeout và retry bằng virtual time

Không cần chờ nhiều giây hoặc nhiều phút để test timeout/retry. `StepVerifier.withVirtualTime` cho phép điều khiển thời gian của Reactor:

```java
@Test
void timesOutWithoutWaitingInRealTime() {
    StepVerifier.withVirtualTime(() -> Mono.<String>never()
                    .timeout(Duration.ofMinutes(2)))
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(2))
            .expectError(TimeoutException.class)
            .verify();
}
```

Publisher phải được tạo bên trong supplier của `withVirtualTime`; nếu tạo trước đó, operator có thể đã giữ scheduler thật và không phản ứng với virtual clock. Virtual time chỉ điều khiển các operator dùng scheduler được Reactor thay thế. Nó không tua nhanh thời gian của TCP socket, WebSocket handshake, Netty event loop hoặc server bên ngoài.

### 4.4. Luôn đặt timeout cho test bất đồng bộ

`verify()` có thể chờ vô hạn nếu publisher không phát terminal signal. Trong test có khả năng treo, dùng `verify(Duration.ofSeconds(...))` hoặc cấu hình default timeout ở cấp test suite. Không dùng timeout quá ngắn khiến CI chậm hoặc máy tải cao sinh false negative.

## 5. Protocol test: kiểm tra hành vi RSocket trực tiếp

Protocol test kiểm tra hai peer RSocket giao tiếp qua transport mà không cần Spring `@MessageMapping`. Đây là tầng phù hợp để xác minh interaction model, metadata, demand, cancel, lỗi protocol và các extension.

Có thể dùng `RSocketServer`, `SocketAcceptor`, `RSocketConnector` và transport Netty. Ví dụ dưới đây dùng TCP trên cổng test được cấp riêng cho test case:

```java
class RSocketProtocolTest {

    private Disposable server;
    private RSocket client;
    private int port;

    private void startServerAndClient(SocketAcceptor acceptor) throws IOException {
        try (ServerSocket reservation = new ServerSocket(0)) {
            port = reservation.getLocalPort();
        }

        server = RSocketServer.create(acceptor)
                .bind(TcpServerTransport.create("localhost", port))
                .block(Duration.ofSeconds(5));

        client = RSocketConnector.create()
                .connect(TcpClientTransport.create("localhost", port))
                .block(Duration.ofSeconds(5));
    }

    @AfterEach
    void closeResources() {
        if (client != null) {
            client.dispose();
        }
        if (server != null) {
            server.dispose();
        }
    }

    @Test
    void requestResponseCrossesTheProtocol() throws IOException {
        startServerAndClient(SocketAcceptor.forRequestResponse(request ->
                Mono.just(DefaultPayload.create("reply:" + request.getDataUtf8()))));

        Mono<String> response = client
                .requestResponse(DefaultPayload.create("ping"))
                .map(Payload::getDataUtf8);

        StepVerifier.create(response)
                .expectNext("reply:ping")
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }
}
```

Ví dụ sử dụng `ServerSocket(0)` để tìm một cổng trống rồi đóng socket giữ chỗ trước khi bind RSocket. Trong suite chạy song song hoặc môi trường nhiều process, vẫn có một khoảng đua nhỏ giữa lúc nhả cổng và lúc RSocket bind; ưu tiên local test transport hoặc test port allocator có cơ chế quản lý nếu dự án đã có. Không dùng một cổng cố định chung cho mọi test.

Test này kiểm tra RSocket `SETUP`, TCP transport, `REQUEST_RESPONSE` và `PAYLOAD` response. Nó không kiểm tra Spring codec, route hay authorization vì server chỉ dùng một `SocketAcceptor` cấp thấp.

Các ví dụ Request-Stream, Fire-and-Forget và Request-Channel tiếp theo là những phần thân test method khác trong cùng `RSocketProtocolTest`; mỗi method gọi `startServerAndClient(acceptor)` với handler tương ứng trước khi sử dụng `client`. Vì helper bind một cổng động, các method khai báo `throws IOException`.

### 5.1. Kiểm tra Request-Stream và demand

Server có thể trả một stream gồm nhiều payload:

```java
SocketAcceptor acceptor = SocketAcceptor.forRequestStream(request ->
        Flux.range(1, 5)
                .map(index -> DefaultPayload.create("item-" + index)));

startServerAndClient(acceptor);
```

Client yêu cầu từng nhóm phần tử:

```java
Flux<String> stream = client
        .requestStream(DefaultPayload.create("start"))
        .map(Payload::getDataUtf8);

StepVerifier.create(stream, 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext("item-1", "item-2")
        .thenRequest(3)
        .expectNext("item-3", "item-4", "item-5")
        .expectComplete()
        .verify(Duration.ofSeconds(5));
```

Test xác minh client không nhận quá demand đã yêu cầu và stream hoàn tất đúng thứ tự. Nếu cần xác minh server không tạo dữ liệu vượt demand, gắn `doOnRequest`/`doOnNext` vào publisher server và quan sát số lượng phát ra; không chỉ kiểm tra số phần tử cuối cùng ở client.

### 5.2. Kiểm tra Fire-and-Forget đúng semantics

Fire-and-Forget không có response payload. `Mono<Void>` phía requester hoàn tất khi thao tác gửi được xác nhận ở phía client/transport; điều đó không chứng minh server đã xử lý xong message.

```java
CountDownLatch handled = new CountDownLatch(1);
AtomicReference<String> received = new AtomicReference<>();

SocketAcceptor acceptor = SocketAcceptor.forFireAndForget(payload ->
        Mono.fromRunnable(() -> {
            received.set(payload.getDataUtf8());
            handled.countDown();
        }));

// Khởi chạy server với acceptor trên test transport trước khi tạo client.
startServerAndClient(acceptor);
client.fireAndForget(DefaultPayload.create("sensor-online"))
        .block(Duration.ofSeconds(5));

assertThat(handled.await(2, TimeUnit.SECONDS)).isTrue();
assertThat(received).hasValue("sensor-online");
```

Đoạn code phần handler minh họa cách xác nhận server thực sự xử lý. Trong test hoàn chỉnh, tạo server với `acceptor` này và đóng cả client/server sau assertion. Không chỉ assert `fireAndForget(...).block()` hoàn tất rồi kết luận business handler đã chạy; nếu cần acknowledgment nghiệp vụ, hãy dùng Request-Response hoặc một route tra cứu trạng thái riêng.

### 5.3. Kiểm tra Request-Channel

Request-Channel cho phép requester gửi một stream payload và responder cũng trả một stream payload. Test cần xác minh cả hai hướng:

```java
SocketAcceptor acceptor = SocketAcceptor.forRequestChannel(requests ->
        Flux.from(requests)
                .map(payload -> DefaultPayload.create(
                        "ack:" + payload.getDataUtf8())));

startServerAndClient(acceptor);

Flux<Payload> outbound = Flux.just(
        DefaultPayload.create("one"),
        DefaultPayload.create("two"),
        DefaultPayload.create("three"));

Flux<String> responses = client.requestChannel(outbound)
        .map(Payload::getDataUtf8);

StepVerifier.create(responses)
        .expectNext("ack:one", "ack:two", "ack:three")
        .expectComplete()
                .verify(Duration.ofSeconds(5));
```

Test thực tế nên bổ sung trường hợp requester gửi chậm, responder trả chậm, một phía cancel và một phía phát lỗi. Channel không phải ba request-response độc lập; nó là một interaction có hai luồng payload gắn với cùng stream ID.

## 6. Integration test với Spring Boot và RSocketRequester

Integration test khởi động Spring ApplicationContext cùng RSocket server thật, sau đó gọi endpoint qua `RSocketRequester`. Đây là nơi kiểm tra route, argument resolver, encoder/decoder, metadata extraction, validation, exception handler, security và service wiring.

Spring Boot có thể bind server vào cổng ngẫu nhiên bằng `spring.rsocket.server.port=0`. `@LocalRSocketServerPort` inject cổng được cấp khi chạy test.

Ví dụ test Request-Response:

```java
@SpringBootTest(properties = {
        "spring.rsocket.server.transport=tcp",
        "spring.rsocket.server.port=0"
})
class SensorRSocketIntegrationTest {

    @LocalRSocketServerPort
    int port;

    @Autowired
    RSocketRequester.Builder requesterBuilder;

    @MockBean
    SensorService sensorService;

    @Test
    void sendsReadingThroughSpringMapping() {
        RSocketRequester requester = requesterBuilder.tcp("localhost", port);
        SensorReading reading = new SensorReading(
                "sensor-17", new BigDecimal("28.5"), Instant.now());
        when(sensorService.store(reading))
                .thenReturn(Mono.just(new ReadingAccepted("reading-91", "ACCEPTED")));

        Mono<ReadingAccepted> response = requester
                .route("sensors.reading")
                .data(reading)
                .retrieveMono(ReadingAccepted.class);

        StepVerifier.create(response)
                .assertNext(result -> {
                    assertThat(result.status()).isEqualTo("ACCEPTED");
                    assertThat(result.id()).isEqualTo("reading-91");
                })
                .verify(Duration.ofSeconds(5));

        verify(sensorService).store(reading);
    }
}
```

Ví dụ giả định ứng dụng có `@MessageMapping("sensors.reading")` và codec JSON tương thích với DTO. Dependency test cần có Spring Boot Test và starter RSocket/WebFlux phù hợp. `@LocalRSocketServerPort` có trong Spring Boot từ 2.7; ở bản cũ hơn, dùng property `local.rsocket.server.port` nếu test support của phiên bản cung cấp.

`RSocketRequester.Builder` là prototype bean có trạng thái cấu hình. Hãy tạo requester riêng cho test hoặc cho một cấu hình kết nối cụ thể; không mutate cùng builder dùng chung cho nhiều test song song.

Nếu production dùng WebSocket, cần một integration test chạy server WebFlux trên cổng HTTP ngẫu nhiên và mở đúng mapping path:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.rsocket.server.transport=websocket",
                "spring.rsocket.server.mapping-path=/rsocket"
        })
class SensorWebSocketIntegrationTest {

    @LocalServerPort
    int httpPort;

    @Autowired
    RSocketRequester.Builder requesterBuilder;

    @Test
    void connectsThroughWebSocketUpgrade() {
        URI endpoint = URI.create("ws://localhost:" + httpPort + "/rsocket");
        RSocketRequester requester = requesterBuilder.websocket(endpoint);

        StepVerifier.create(requester.route("health.ping")
                        .retrieveMono(String.class))
                .expectNext("pong")
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }
}
```

Ví dụ giả định ứng dụng có route `health.ping` trả về `pong`. Test này kiểm tra HTTP Upgrade, WebSocket transport, RSocket SETUP và route qua mapping path. Trong môi trường production dùng TLS, bổ sung một E2E test qua `wss://` và reverse proxy; test local `ws://` không kiểm tra chứng thư, TLS termination hoặc CSP.

### 6.1. Kiểm tra route và codec

Gửi DTO qua `.data(dto)` rồi nhận bằng `.retrieveMono(Response.class)` để xác minh encoder/decoder hai phía. Thêm test với:

- Data MIME type đúng và không đúng.
- Payload thiếu field hoặc sai kiểu.
- Metadata route không tồn tại.
- Custom metadata thiếu decoder.
- Payload lớn hơn giới hạn cấu hình.
- DTO lồng nhau có validation constraint.

Nếu test route sai, xác minh client nhận lỗi route phù hợp và service không bị gọi. Nếu test decode lỗi, gửi raw bytes hoặc payload được encode bằng MIME type khác; `.data(dto)` qua encoder bình thường không tạo ra JSON sai cú pháp.

### 6.2. Kiểm tra Bean Validation và error mapping

Gửi payload có cấu trúc decode được nhưng vi phạm constraint để xác minh `@Valid` được thực thi trước khi vào business handler:

```java
@Test
void rejectsInvalidPayloadBeforeCallingService() {
    RSocketRequester requester = requesterBuilder.tcp("localhost", port);
    SensorReading invalid = new SensorReading(
            "", new BigDecimal("300"), Instant.now());

    StepVerifier.create(requester.route("sensors.reading")
                    .data(invalid)
                    .retrieveMono(ApiError.class))
            .assertNext(error -> assertThat(error.code()).isEqualTo("INVALID_PAYLOAD"))
            .expectComplete()
            .verify(Duration.ofSeconds(5));

    verifyNoInteractions(sensorService);
}
```

Test giả định ứng dụng biểu diễn lỗi validation thành `ApiError` response payload qua `@MessageExceptionHandler`. Nếu hợp đồng của ứng dụng dùng terminal RSocket error, hãy thay assertion bằng `expectError...`. Không trộn hai cách biểu diễn lỗi trong cùng một contract mà không có quy tắc rõ ràng.

### 6.3. Kiểm tra authentication và authorization

Tạo test riêng cho:

- Thiếu credential ở `SETUP` khi policy yêu cầu xác thực kết nối.
- JWT sai chữ ký, sai issuer, hết hạn hoặc audience không hợp lệ.
- Token hợp lệ nhưng thiếu authority của route.
- User A gửi request tới tài nguyên thuộc user B.
- Kết nối dùng chung với token riêng trên từng request.
- Logout, token refresh và thu hồi quyền theo chính sách.

Với test bảo mật, dùng credential giả lập trong test profile. Không commit token production hoặc secret thật vào source/test report.

## 7. Kiểm tra các interaction model và semantics

Mỗi interaction có contract khác nhau. Test phải phản ánh đúng contract thay vì chỉ xác minh rằng không có exception.

| Interaction | Test tối thiểu | Điều cần tránh hiểu sai |
| --- | --- | --- |
| Request-Response | Một request nhận một response hoặc lỗi | Không nhận nhiều response |
| Fire-and-Forget | Server nhận và xử lý message; xác minh bằng signal/trạng thái phía server | Client send hoàn tất không có nghĩa handler đã hoàn tất |
| Request-Stream | Kiểm tra thứ tự, demand, completion, error và cancel | Không yêu cầu vô hạn trong test backpressure |
| Request-Channel | Kiểm tra cả stream request và stream response | Không coi từng payload channel là một interaction mới |
| Metadata-Push | Kiểm tra metadata gắn với kết nối và responder nhận được | Không nhầm metadata-push với metadata của một request |

Với stream/channel, cần kiểm tra terminal error và cancellation ở cả hai phía. Một subscriber hủy không nên để lại producer hoặc task nền chạy vô hạn nếu ứng dụng yêu cầu hủy lan truyền.

## 8. Kiểm tra protocol setup, metadata và lỗi

Một connection RSocket bắt đầu bằng `SETUP`. Integration test cần xác minh:

- Data MIME type và metadata MIME type hai phía thống nhất.
- Setup metadata được giải mã đúng.
- Server từ chối SETUP khi credential hoặc protocol setting không hợp lệ.
- Route metadata được trích xuất đúng key.
- Metadata tùy chỉnh có decoder tương ứng.
- Metadata quá lớn hoặc sai định dạng bị từ chối có kiểm soát.
- `METADATA_PUSH` được xử lý ở cấp kết nối, không gắn nhầm vào request hiện tại.

Khi test lỗi, phân biệt lỗi ở các tầng:

| Lỗi | Nơi thường quan sát | Test cần xác minh |
| --- | --- | --- |
| SETUP bị từ chối | `connect`/connection close | Không có request nào được xử lý |
| Route không tồn tại | Request error | Handler/service không chạy |
| Decode lỗi | Message conversion/decode error | Không gọi business service |
| Validation lỗi | Handler argument resolution | Trả lỗi theo contract, không lưu dữ liệu |
| Business error | Service/handler | Mã lỗi nghiệp vụ ổn định |
| Transport reset | `onClose`, request/stream error | Cleanup và reconnect policy |
| Protocol violation | Protocol error/connection close | Không tiếp tục dùng connection đã lỗi |

Đừng chỉ assert nội dung exception message vì message có thể thay đổi giữa phiên bản. Ưu tiên kiểm tra exception type, protocol error code, error DTO code hoặc trạng thái kết nối.

## 9. Kiểm tra backpressure, cancellation và LEASE

RSocket truyền demand của Reactive Streams qua ranh giới mạng. Protocol test nên kiểm tra:

1. Client gửi initial request-N khi mở Request-Stream/Channel.
2. Server không phát quá số lượng đã được cấp demand.
3. Khi client yêu cầu thêm, server tiếp tục phát.
4. Khi client cancel, server nhận cancellation và dừng công việc có thể dừng.
5. Khi một phía phát lỗi, phía kia nhận terminal signal và tài nguyên được giải phóng.
6. Nếu bật LEASE, request không có lease hợp lệ bị từ chối và được phép sau khi lease mới tới.

Test `StepVerifier.create(stream, 0).thenRequest(n)` hữu ích để điều khiển demand phía client. Để xác minh tác động trên wire, dùng server publisher có `doOnRequest` và `doOnCancel` hoặc một test interceptor ghi nhận request/cancel. Không chỉ dựa vào việc client nhận đúng số phần tử; queue trung gian có thể che giấu việc source đã phát quá sớm.

Không dùng virtual time để giả lập mạng hoặc keepalive thực. Virtual time phù hợp cho timeout/retry operator trong pipeline; keepalive, idle timeout và TCP disconnect cần test transport hoặc môi trường tích hợp với thời gian thực có giới hạn.

## 10. Kiểm tra fragmentation và payload lớn

Nếu ứng dụng gửi payload lớn, test cả hai phía đã bật fragmentation và giới hạn inbound phù hợp:

```java
RSocketServer server = RSocketServer.create(acceptor)
        .fragment(1024)
        .maxInboundPayloadSize(16 * 1024 * 1024);

RSocketConnector connector = RSocketConnector.create()
        .fragment(1024)
        .maxInboundPayloadSize(16 * 1024 * 1024);
```

Ví dụ dùng giới hạn 16 MiB để đủ lớn hơn frame tối đa mặc định xấp xỉ 16 MiB của transport RSocket Java 1.1.5. Trong cấu hình thực tế, `maxInboundPayloadSize` phải luôn lớn hơn hoặc bằng `Transport.maxFrameLength()`; nếu transport đặt frame limit cao hơn, hãy tăng inbound limit tương ứng. Test gửi payload có kích thước nhỏ hơn, bằng và lớn hơn MTU; xác minh peer nhận được đúng data và metadata sau reassembly. Thêm trường hợp vượt `maxInboundPayloadSize` để xác minh lỗi bị giới hạn trước khi cấp phát bộ nhớ quá lớn.

Khi dùng `PayloadDecoder.ZERO_COPY`, test cần kiểm tra ownership và cleanup của payload trên đường success, error, cancel và discard. Với decoder mặc định, RSocket Java copy data/metadata và không yêu cầu ứng dụng theo dõi reference count của payload nhận theo cùng cách zero-copy.

## 11. End-to-end test trên môi trường gần production

End-to-end test xác minh hệ thống hoạt động qua toàn bộ đường đi thực tế. Một kịch bản có thể gồm:

```text
Browser / Mobile
       |
       | WSS + authentication
       v
Ingress / Reverse Proxy
       |
       v
API Gateway / RSocket Edge
       |
       | service discovery + load balancing
       v
RSocket Service Cluster
       |
       +------> Database
       |
       +------> Event Broker
       |
       +------> Downstream Service
```

End-to-end test nên bao gồm các kịch bản đại diện:

- User đăng nhập, mở WSS connection và gọi Request-Response.
- User subscribe Request-Stream, nhận event, cancel khi rời màn hình.
- Hai user dùng chung gateway connection nhưng authorization được tách riêng.
- Token hết hạn trong khi connection còn mở.
- Proxy idle timeout hoặc mạng bị ngắt, client reconnect theo backoff.
- Một server instance bị dừng; request mới được gửi tới instance còn khỏe.
- Server được khởi động lại và đăng ký lại với discovery.
- Payload lớn đi qua TLS/proxy mà không bị cắt hoặc vượt giới hạn.
- Client chậm, queue đạt giới hạn và hệ thống thực hiện chính sách drop/disconnect/backpressure.
- Metrics, tracing và log có correlation ID xuyên suốt request.

Không chạy mọi tổ hợp lỗi trên mỗi commit nếu chi phí quá cao. Chọn một smoke E2E nhỏ cho pull request và chạy bộ resilience/full E2E theo lịch hoặc trước release.

## 12. Contract test giữa client và server

Client và server có thể được phát hành độc lập. Contract test giúp phát hiện thay đổi không tương thích trước khi triển khai:

- Route name và route variables.
- Data MIME type và metadata MIME type.
- Schema của request/response DTO.
- Required/optional field và default value.
- Interaction model của từng route.
- Error code và cách biểu diễn terminal error.
- Authentication metadata và authority cần thiết.
- Giới hạn payload, fragmentation và flow control.

Có thể lưu bộ payload mẫu JSON/CBOR và metadata mẫu như contract fixtures. Client và server build chạy cùng bộ contract test. Với schema thay đổi, test consumer cũ với server mới và client mới với server cũ theo ma trận version được hỗ trợ.

Đừng chỉ so sánh Java class vì hai service có thể dùng ngôn ngữ hoặc serializer khác nhau. Contract là byte format, MIME type, metadata và semantics quan sát được qua protocol.

## 13. Test hạ tầng, transport và fault injection

Một số lỗi chỉ xuất hiện khi có network hoặc hạ tầng thật:

| Tình huống | Công cụ/cách tạo lỗi | Điều cần xác minh |
| --- | --- | --- |
| TCP reset | Dừng server hoặc proxy ngắt socket | Client nhận lỗi và giải phóng stream |
| Latency/jitter | Toxiproxy hoặc network emulator | Timeout, queue và backpressure không vượt giới hạn |
| Packet loss | Network emulator | Keepalive/reconnect và retry có giới hạn |
| Proxy idle timeout | Cấu hình ingress/test proxy | Keepalive tương thích timeout |
| TLS certificate lỗi | Test certificate hết hạn/hostname sai | Handshake bị từ chối an toàn |
| DNS đổi endpoint | Test discovery/DNS fixture | Client reconnect tới endpoint mới |
| Instance chết | Container stop/kill | Discovery loại target và request mới failover |
| Registry tạm mất | Stub hoặc container registry dừng | Snapshot stale được xử lý theo policy |
| Database chậm | Testcontainer hoặc proxy database | Deadline/cancel truyền xuống tầng persistence |

Toxiproxy hoặc công cụ tương tự nên được dùng trong integration/resilience suite. Không thêm độ trễ hoặc packet loss ngẫu nhiên vào unit test vì sẽ làm test chậm và khó tái hiện.

## 14. Test tải và kiểm thử khả năng chịu tải

Load test trả lời câu hỏi hệ thống xử lý bao nhiêu request/stream với latency và error rate nào. Stress test đẩy hệ thống tới điểm bão hòa. Soak test giữ tải lâu để phát hiện leak, queue tăng và connection churn.

Các chỉ số nên thu thập:

- Throughput theo interaction model: request-response, FNF, stream và channel.
- Latency p50, p95, p99 và timeout rate.
- Số kết nối và số stream đồng thời.
- Số request đang pending và queue depth.
- Tỷ lệ cancel, disconnect, reconnect và protocol error.
- Heap/direct memory, GC pause và CPU.
- Số payload bị drop hoặc từ chối do overflow/lease.
- Tải database và downstream service.

Thiết kế tải phải giống hành vi thật. Một triệu Request-Response nhỏ không đại diện cho một nghìn stream dài hạn. Với stream, cần đo thời gian sống, tốc độ phát, demand và số subscriber chậm. Với FNF, phải có cách xác minh server thực sự xử lý message thay vì chỉ đo tốc độ client gửi frame.

Không dùng một lần benchmark để chọn pool size hoặc keepalive. Chạy nhiều lần với cùng dữ liệu, warm-up, concurrency và môi trường; ghi rõ version client/server và cấu hình transport.

## 15. Tổ chức test suite trong dự án

Một cấu trúc dễ duy trì:

```text
src/test/java/
  .../service/
    SensorServiceTest.java
  .../handler/
    SensorMessageHandlerTest.java
  .../protocol/
    RSocketProtocolTest.java
  .../integration/
    SensorRSocketIntegrationTest.java
    RSocketSecurityIntegrationTest.java
  .../e2e/
    SensorFlowE2ETest.java
```

Có thể dùng suffix để phân loại suite:

- `*Test`: unit test nhanh, chạy trong mỗi build.
- `*ProtocolTest`: test RSocket client/server và interaction semantics.
- `*IT`: integration test cần Spring context, database hoặc transport thật.
- `*E2E`: test cần môi trường triển khai hoặc nhiều service.

Tên suffix không tự làm Maven/Gradle chạy đúng suite. Cần cấu hình task hoặc plugin để chỉ định pattern nào chạy ở `test`, `integrationTest` hoặc pipeline release.

Ví dụ chia pipeline:

| Giai đoạn CI | Test chạy | Mục tiêu |
| --- | --- | --- |
| Mỗi commit/PR | Unit + một số protocol test nhanh | Feedback nhanh |
| Merge vào nhánh chính | Unit + protocol + Spring integration | Xác minh wiring và contract |
| Nightly | Full integration + fault injection + soak ngắn | Phát hiện lỗi timing và resource |
| Trước release | E2E, TLS/security, compatibility và load test | Đánh giá khả năng phát hành |

## 16. Tránh test flaky và kết quả sai lệch

Các nguyên tắc thực hành:

- Không dùng `Thread.sleep` để chờ message; dùng `StepVerifier`, `CountDownLatch` có timeout hoặc Awaitility.
- Không dùng cổng cố định dùng chung cho nhiều test; ưu tiên random port hoặc local transport.
- Luôn đóng hoặc dispose kết nối RSocket client/server, scheduler và container sau test; để requester-managed connection kết thúc theo lifecycle của test context.
- Không chia sẻ mutable `RSocketRequester.Builder` giữa các test chạy song song.
- Không phụ thuộc thứ tự test hoặc dữ liệu tồn tại từ lần chạy trước.
- Dùng clock có thể kiểm soát cho logic expiry/token; không giả lập clock của transport bằng Reactor virtual time.
- Dùng timeout hợp lý cho connect, request và `StepVerifier.verify`.
- Chỉ dùng retry trong test nếu mục tiêu là kiểm tra retry; không retry assertion thất bại để che flaky behavior.
- Ghi correlation ID, route và test case ID khi điều tra lỗi protocol.
- Tắt hoặc làm sạch test data ở database/broker để test có thể chạy lặp lại.

Một test xanh không chứng minh hệ thống hoàn toàn đúng. Hãy xem xét coverage theo hành vi, đường lỗi và ranh giới hệ thống; line coverage cao nhưng không có test cancel, timeout, malformed metadata hoặc unauthorized route vẫn có thể bỏ sót lỗi quan trọng.

## 17. Ma trận kiểm thử tối thiểu cho một route

Với mỗi route RSocket, có thể dùng checklist sau:

| Nhóm | Ca kiểm thử |
| --- | --- |
| Input | Hợp lệ, thiếu field, sai kiểu, giá trị ngoài giới hạn, payload quá lớn |
| Routing | Route đúng, route không tồn tại, route variable sai |
| Metadata | Có/thiếu metadata bắt buộc, metadata tùy chọn, MIME type sai |
| Security | Anonymous, token sai, token hết hạn, thiếu authority, truy cập sai tenant |
| Interaction | Đúng model, response cardinality, stream order, channel hai chiều |
| Reactive | Demand, cancel, timeout, retry, fallback, error propagation |
| Protocol | SETUP, REQUEST_N, CANCEL, ERROR, fragmentation nếu sử dụng |
| Resource | Payload release, connection close, scheduler/queue cleanup |
| Operations | Reconnect, discovery change, server restart, proxy timeout |
| Compatibility | Client/server version cũ-mới, codec và schema |

Không phải route nào cũng cần mọi ca. Đánh dấu các mục áp dụng và lý do bỏ qua trong test plan hoặc contract để reviewer hiểu phạm vi.

## 18. Checklist trước khi merge và phát hành

- [ ] Unit test bao phủ logic thành công, lỗi nghiệp vụ và nhánh fallback.
- [ ] Reactive test xác minh demand, cancel, timeout và error signal.
- [ ] Protocol test bao phủ interaction model route sử dụng.
- [ ] FNF test xác minh xử lý ở server, không chỉ send completion.
- [ ] Stream/channel test có demand hữu hạn và cancellation.
- [ ] Integration test chạy qua Spring `RSocketRequester` hoặc raw RSocket client.
- [ ] Test codec, route metadata, Bean Validation và error mapping.
- [ ] Test authentication, authorization và tenant isolation.
- [ ] Test payload lớn, fragmentation và inbound size limit nếu cần.
- [ ] Test TCP/WebSocket transport mà ứng dụng thực sự triển khai.
- [ ] Test server down/recovery, reconnect và discovery nếu có.
- [ ] Test không rò rỉ payload, socket, scheduler hoặc queue.
- [ ] E2E smoke test chạy qua proxy/TLS trên môi trường gần production.
- [ ] Test contract giữa client/server và version tương thích.
- [ ] Test tải có throughput, latency, memory và error-rate threshold.
- [ ] CI phân tầng test theo thời gian và chi phí phù hợp.

Phân tầng kiểm thử giúp tìm lỗi ở đúng ranh giới. Unit test xác minh logic nhanh; protocol test xác minh semantics RSocket; integration test xác minh Spring, codec, metadata và bảo mật; end-to-end test xác minh hệ thống khi đi qua mạng và hạ tầng thật. Khi kết hợp các tầng cùng với test tải và fault injection có mục tiêu, nhóm phát triển có thể phát hiện sớm lỗi hợp đồng, lỗi reactive lifecycle và lỗi vận hành mà vẫn giữ được vòng phản hồi nhanh.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Boot 3.3 — `@LocalRSocketServerPort`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html)
- [RSocket Java 1.1.5 — `RSocketServer`](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [RSocket Java 1.1.5 — `RSocketConnector`](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [RSocket Java 1.1.5 — `SocketAcceptor`](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/SocketAcceptor.html)
- [RSocket Java 1.1.5 — `Payload`](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/Payload.html)
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor Test — `StepVerifier`](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [Project Reactor Test — `TestPublisher`](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html)
- [Project Reactor Test — `PublisherProbe`](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html)
- [Spring — Getting Started with RSocket: Testing Spring Boot Responders](https://spring.io/blog/2020/05/25/getting-started-with-rsocket-testing-spring-boot-responders/)

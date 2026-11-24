# Kiểm thử RSocket Java bằng truyền tải cục bộ không qua mạng

Khi kiểm thử RSocket, không phải lúc nào cũng cần mở TCP socket hoặc khởi chạy WebSocket server. RSocket Java cung cấp **Local Transport** để nối một RSocket server và client trong cùng tiến trình bằng một kênh truyền tải cục bộ. Cách này cho phép chạy hai đầu RSocket thật, thực hiện SETUP và các interaction qua protocol stack, nhưng không đi qua card mạng, IP stack hay socket TCP của hệ điều hành.

Local Transport phù hợp cho integration test nhanh: kiểm tra request-response, fire-and-forget, request-stream, request-channel, metadata, lỗi, cancellation và flow control. Nó nằm giữa unit test dùng mock và network integration test dùng TCP/WebSocket.

Bài này sử dụng JUnit 5, Reactor Test và hai lớp LocalServerTransport/LocalClientTransport. Các ví dụ dùng API RSocket Java 1.1.x; hãy đồng bộ phiên bản các artifact RSocket theo dependency management của dự án.

## 1. Local Transport là gì?

RSocket Java tách protocol engine khỏi transport. Server và client trao đổi frame thông qua các abstraction ServerTransport, ClientTransport và DuplexConnection. Local Transport cung cấp hai đầu kết nối in-memory:

- LocalServerTransport đăng ký một server dưới một tên cục bộ.
- LocalClientTransport kết nối tới server theo tên đó.
- RSocketServer vẫn xử lý SETUP và tạo responder.
- RSocketConnector vẫn tạo requester và thực hiện các interaction.
- RSocket ở hai phía vẫn trao đổi qua frame và Reactive Streams semantics.

~~~mermaid
flowchart LR
    A[Test / JUnit] --> B[RSocketConnector]
    B --> C[LocalClientTransport]
    C <-->|In-memory duplex connection| D[LocalServerTransport]
    D --> E[RSocketServer]
    E --> F[SocketAcceptor / RSocket Handler]
    F --> G[Mono / Flux]
~~~

Điểm quan trọng là test vẫn dùng RSocket client/server thực. Local Transport thay phần I/O mạng bằng kết nối cục bộ trong bộ nhớ.

### Local Transport kiểm tra được gì?

- Server bind và client connect qua transport abstraction.
- SETUP và vòng đời connection ở cấp RSocket.
- Request-response, fire-and-forget, request-stream và request-channel.
- Payload data/metadata, route hoặc setup payload nếu test cấu hình chúng.
- Response, application error, cancellation và stream completion.
- Demand và flow control ở cấp Reactive Streams/RSocket.
- Logic interceptor hoặc responder được gắn vào RSocket stack.
- Tích hợp handler Spring nếu server được dựng bằng RSocketMessageHandler.

### Local Transport không kiểm tra được gì?

- TCP socket thực, IP routing, DNS, firewall và network policy.
- TLS handshake, certificate, cipher suite hoặc mTLS.
- HTTP Upgrade và WebSocket framing.
- Proxy, load balancer, ingress và timeout trên mạng.
- Packet loss, retransmission, congestion, MTU và network jitter.
- Network partition, reconnect storm hoặc chuyển đổi Wi-Fi/mobile thực tế.
- Độ trễ và throughput đại diện cho môi trường production.

Vì vậy, Local Transport là một lớp integration test nhanh. Vẫn cần một số network test riêng để xác nhận TCP/WebSocket và hạ tầng triển khai.

## 2. Chọn đúng cấp độ kiểm thử

Ba cấp độ thường được kết hợp:

| Cấp độ | Thành phần chạy | Kiểm tra tốt nhất | Giới hạn |
|---|---|---|---|
| Unit test | Handler/service với mock hoặc publisher test | Quy tắc nghiệp vụ, nhánh lỗi, mapping | Không kiểm tra RSocket protocol |
| Local Transport test | RSocket Java client và server trong cùng JVM | SETUP, interaction, frame handling, demand, cancel, metadata | Không có network I/O |
| Network integration test | Client và server qua TCP/WebSocket thật | Transport, TLS, proxy, port, handshake, network behavior | Chậm và cần quản lý tài nguyên mạng |

Không nên mock toàn bộ RSocket trong mọi test. Mock hữu ích cho logic đơn vị, nhưng không phát hiện được lỗi trong việc kết nối requester/responder hoặc xử lý stream qua protocol.

Ngược lại, không cần mở TCP server cho từng test nghiệp vụ đơn giản. Local Transport giúp test nhiều tình huống với ít phụ thuộc môi trường hơn.

## 3. Thêm dependency cho Local Transport

Artifact Local Transport là module riêng của RSocket Java. Nếu dự án chưa quản lý phiên bản qua Spring Boot hoặc RSocket BOM, hãy khai báo các artifact RSocket cùng một version.

Ví dụ Gradle Groovy:

~~~groovy
dependencies {
    implementation "io.rsocket:rsocket-core:1.1.5"

    testImplementation "io.rsocket:rsocket-transport-local:1.1.5"
    testImplementation "io.projectreactor:reactor-test"
    testImplementation "org.junit.jupiter:junit-jupiter"
    testImplementation "org.assertj:assertj-core"
}

test {
    useJUnitPlatform()
}
~~~

Nếu ứng dụng đã dùng Spring Boot dependency management, ưu tiên để BOM quản lý các phiên bản tương thích. Không ép riêng rsocket-transport-local sang một version khác với rsocket-core.

Trong dự án Maven, dependency test tương ứng:

~~~xml
<dependency>
    <groupId>io.rsocket</groupId>
    <artifactId>rsocket-transport-local</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu Maven không dùng BOM hoặc dependency management, khai báo version RSocket đồng bộ với rsocket-core mà ứng dụng đang dùng.

## 4. Khởi tạo Local RSocket server và client

Một bài test cần thực hiện bốn việc:

1. Tạo tên server cục bộ duy nhất cho test.
2. Bind RSocketServer bằng LocalServerTransport.
3. Kết nối RSocketConnector bằng LocalClientTransport.
4. Dispose client và server sau khi test hoàn tất.

Tên server phải duy nhất để test chạy song song không vô tình kết nối nhầm server của test khác.

~~~java
import io.rsocket.AbstractRSocket;
import io.rsocket.Payload;
import io.rsocket.RSocket;
import io.rsocket.SocketAcceptor;
import io.rsocket.core.RSocketConnector;
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.local.LocalClientTransport;
import io.rsocket.transport.local.LocalServerTransport;
import io.rsocket.util.DefaultPayload;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.UUID;

class LocalRSocketTest {

    private String serverName;
    private Disposable server;
    private RSocket client;

    @BeforeEach
    void setUp() {
        serverName = "rsocket-test-" + UUID.randomUUID();

        SocketAcceptor acceptor =
            SocketAcceptor.with(new AbstractRSocket() {
                @Override
                public Mono<Payload> requestResponse(Payload payload) {
                    return Mono.just(
                        DefaultPayload.create(
                            "echo:" + payload.getDataUtf8()));
                }
            });

        server = RSocketServer.create(acceptor)
            .bind(LocalServerTransport.create(serverName))
            .block(Duration.ofSeconds(5));

        client = RSocketConnector.connectWith(
                LocalClientTransport.create(serverName))
            .block(Duration.ofSeconds(5));
    }

    @AfterEach
    void tearDown() {
        if (client != null) {
            client.dispose();
        }

        if (server != null) {
            server.dispose();
        }
    }
}
~~~

Đây là khung khởi tạo. Các test bên dưới có thể đặt trong cùng class hoặc tách thành những class chuyên biệt. Ví dụ rút gọn cần các import bổ sung như Flux, Publisher, StepVerifier và AssertJ.

bind(...).block(...) trả về handle để dừng server. connectWith(...).block(...) trả về RSocket client. Cả hai được tạo trước khi test gửi request.

### Vì sao phải dispose?

Nếu không đóng client/server:

- Local server có thể còn đăng ký dưới tên cũ.
- Connection và stream state có thể tồn tại qua test.
- Test chạy lặp hoặc song song có thể bị nhiễu.
- Buffer và resource có thể bị giữ lại, khiến test suite tăng bộ nhớ.
- Lỗi cleanup có thể bị nhầm thành lỗi của test tiếp theo.

Đặt cleanup trong @AfterEach, hoặc dùng extension quản lý lifecycle nếu có nhiều test cần chung fixture.

## 5. Kiểm thử request-response bằng StepVerifier

Request-response mở một interaction và nhận tối đa một response. Dùng StepVerifier để kiểm tra dữ liệu và terminal signal.

Handler:

~~~java
@Override
public Mono<Payload> requestResponse(Payload payload) {
    String input = payload.getDataUtf8();

    return Mono.just(
        DefaultPayload.create("echo:" + input));
}
~~~

Test:

~~~java
@Test
void requestResponseReturnsExpectedPayload() {
    Mono<String> result = client
        .requestResponse(DefaultPayload.create("hello"))
        .map(Payload::getDataUtf8);

    StepVerifier.create(result)
        .expectNext("echo:hello")
        .verifyComplete();
}
~~~

Test xác nhận:

- Client gửi được request qua Local Transport.
- Server nhận request và gọi handler.
- Response được trả về client.
- Payload được decode thành nội dung mong đợi.
- Interaction hoàn tất bình thường.

verifyComplete() kiểm tra cả giá trị lẫn tín hiệu hoàn tất. Nếu test có nguy cơ chờ vô hạn, có thể dùng verify(Duration.ofSeconds(5)) để đặt timeout cho verification.

## 6. Kiểm thử request-stream

Request-stream mở một interaction nhưng có thể phát nhiều payload. Cần kiểm tra thứ tự, số phần tử và tín hiệu hoàn tất.

Handler:

~~~java
@Override
public Flux<Payload> requestStream(Payload payload) {
    String prefix = payload.getDataUtf8();

    return Flux.range(1, 3)
        .map(index ->
            DefaultPayload.create(prefix + index));
}
~~~

Test:

~~~java
@Test
void requestStreamEmitsAllItemsInOrder() {
    Flux<String> result = client
        .requestStream(DefaultPayload.create("item-"))
        .map(Payload::getDataUtf8);

    StepVerifier.create(result)
        .expectNext("item-1")
        .expectNext("item-2")
        .expectNext("item-3")
        .verifyComplete();
}
~~~

Test này xác nhận responder phát đủ ba phần tử theo thứ tự. Dùng Flux.range tạo nguồn hữu hạn, có thể điều tiết theo demand, phù hợp để kiểm tra stream hoàn tất.

Với stream vô hạn, không chờ verifyComplete(). Hãy dùng take, thenCancel hoặc một điều kiện kết thúc rõ ràng để test có thể dọn tài nguyên.

## 7. Kiểm thử request-channel hai chiều

Request-channel nhận một luồng payload từ requester và trả về một luồng payload từ responder. Cả hai phía có thể phát nhiều phần tử.

Handler:

~~~java
@Override
public Flux<Payload> requestChannel(
        Publisher<Payload> payloads) {

    return Flux.from(payloads)
        .map(Payload::getDataUtf8)
        .map(value ->
            DefaultPayload.create("ack:" + value));
}
~~~

Test:

~~~java
@Test
void requestChannelProcessesInputStream() {
    Flux<Payload> requests = Flux.just("a", "b", "c")
        .map(DefaultPayload::create);

    Flux<String> responses = client
        .requestChannel(requests)
        .map(Payload::getDataUtf8);

    StepVerifier.create(responses)
        .expectNext("ack:a")
        .expectNext("ack:b")
        .expectNext("ack:c")
        .verifyComplete();
}
~~~

Test này kiểm tra một chiều dữ liệu đầu vào và chiều response tương ứng. Với nghiệp vụ phức tạp hơn, hãy kiểm tra riêng:

- Thứ tự request được nhận.
- Response được ghép với đúng command.
- Hành vi khi request publisher hoàn tất sớm.
- Hành vi khi một phía phát lỗi.
- Cancellation khi requester dừng đọc response.
- Backpressure độc lập ở hai hướng.

Request-channel không chỉ là request-stream có nhiều input. Nó là một interaction hai chiều với demand và terminal signal ở cả hai phía.

## 8. Kiểm thử fire-and-forget và hiểu đúng completion

Fire-and-forget gửi request mà không có response payload. Mono<Void> phía client hoàn tất khi thao tác gửi được hoàn tất theo contract của client; điều đó không phải là business acknowledgement chứng minh server đã commit dữ liệu.

Handler có thể ghi nhận event:

~~~java
private final AtomicReference<String> receivedEvent =
    new AtomicReference<>();

@Override
public Mono<Void> fireAndForget(Payload payload) {
    receivedEvent.set(payload.getDataUtf8());
    return Mono.empty();
}
~~~

Nếu test cần chứng minh handler đã được gọi, dùng tín hiệu đồng bộ trong test, chẳng hạn CountDownLatch, hoặc một test sink. Không chỉ kiểm tra Mono gửi phía client hoàn tất rồi kết luận event đã được lưu bền vững.

Ví dụ với latch:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

private final CountDownLatch eventReceived =
    new CountDownLatch(1);
private final AtomicReference<String> receivedEvent =
    new AtomicReference<>();

@Override
public Mono<Void> fireAndForget(Payload payload) {
    receivedEvent.set(payload.getDataUtf8());
    eventReceived.countDown();
    return Mono.empty();
}

@Test
void fireAndForgetReachesResponder() throws Exception {
    client.fireAndForget(DefaultPayload.create("event-1"))
        .block(Duration.ofSeconds(5));

    assertThat(eventReceived.await(5, TimeUnit.SECONDS))
        .isTrue();
    assertThat(receivedEvent.get()).isEqualTo("event-1");
}
~~~

Trong ví dụ thực tế, reset latch và state cho mỗi test instance. Nếu muốn kiểm tra business persistence, hãy chờ tới khi test store/database xác nhận trạng thái đã commit.

## 9. Kiểm thử application error

Một handler có thể trả publisher lỗi. RSocket chuyển lỗi của interaction qua protocol để requester nhận terminal error.

Handler:

~~~java
@Override
public Mono<Payload> requestResponse(Payload payload) {
    String input = payload.getDataUtf8();

    if ("invalid".equals(input)) {
        return Mono.error(
            new IllegalArgumentException("invalid request"));
    }

    return Mono.just(DefaultPayload.create("ok:" + input));
}
~~~

Test:

~~~java
@Test
void requestResponsePropagatesApplicationError() {
    Mono<Payload> result = client.requestResponse(
        DefaultPayload.create("invalid"));

    StepVerifier.create(result)
        .expectErrorSatisfies(error ->
            assertThat(error)
                .hasMessageContaining("invalid request"))
        .verify();
}
~~~

Ở phía client, exception có thể được chuyển thành loại lỗi RSocket thay vì giữ nguyên class exception của server. Nên kiểm tra error code/message theo contract cần thiết, không phụ thuộc vào việc class exception hai phía phải giống nhau.

Phân biệt application error với lỗi connection:

- Application error thường kết thúc interaction hiện tại.
- Connection error có thể ảnh hưởng nhiều stream đang chạy.
- Setup rejection xảy ra trước khi connection RSocket sẵn sàng.
- Timeout phía client có thể xảy ra dù server vẫn đang xử lý.

Mỗi nhóm cần test riêng nếu ứng dụng có logic retry hoặc recovery khác nhau.

## 10. Kiểm thử cancellation

Khi requester hủy subscription, RSocket gửi CANCEL cho stream tương ứng. Responder nên dừng công việc upstream để tránh tiếp tục truy vấn hoặc phát dữ liệu không còn người nhận.

Handler có thể ghi nhận cancellation:

~~~java
private final CountDownLatch streamCancelled =
    new CountDownLatch(1);

@Override
public Flux<Payload> requestStream(Payload payload) {
    String prefix = payload.getDataUtf8();

    return Flux.interval(Duration.ofMillis(10))
        .map(index ->
            DefaultPayload.create(prefix + index))
        .doOnCancel(streamCancelled::countDown);
}
~~~

Test:

~~~java
@Test
void cancellingStreamCancelsResponderPublisher()
        throws Exception {

    Flux<String> result = client
        .requestStream(DefaultPayload.create("tick-"))
        .take(2)
        .map(Payload::getDataUtf8);

    StepVerifier.create(result)
        .expectNext("tick-0")
        .expectNext("tick-1")
        .verifyComplete();

    assertThat(streamCancelled.await(5, TimeUnit.SECONDS))
        .isTrue();
}
~~~

take(2) hủy upstream sau khi nhận đủ hai phần tử. Latch đợi CANCEL truyền tới responder và xác nhận publisher phía server đã được hủy.

Cancellation quan trọng với stream truy vấn database, event subscription, timer và các tác vụ giữ tài nguyên. Nếu handler bỏ qua cancellation, test có thể thấy publisher tiếp tục chạy dù client đã ngừng nhận dữ liệu.

## 11. Kiểm thử demand và backpressure

Local Transport cho phép kiểm tra cách demand của subscriber ảnh hưởng đến stream. Dùng một nguồn có thể điều tiết như Flux.range để tránh tạo dữ liệu vô hạn trong test.

~~~java
@Test
void requestStreamFollowsDownstreamDemand() {
    Flux<String> result = client
        .requestStream(DefaultPayload.create("item-"))
        .map(Payload::getDataUtf8);

    StepVerifier.create(result, 1)
        .expectNext("item-1")
        .thenRequest(2)
        .expectNext("item-2", "item-3")
        .verifyComplete();
}
~~~

Test bắt đầu với demand một phần tử, sau đó mới yêu cầu thêm hai phần tử. Nó xác nhận stream có thể tiếp tục phát theo demand của requester.

Có thể mở rộng test để kiểm tra:

- Consumer yêu cầu theo batch nhỏ.
- Consumer chậm trong khi producer phát nhanh.
- Buffer overflow theo policy ứng dụng.
- Cancellation khi consumer không còn cần dữ liệu.
- Request-channel có tốc độ hai hướng khác nhau.

Không dùng một nguồn vô hạn không có giới hạn buffer trong test backpressure. Nếu nguồn phát không tuân thủ demand, test có thể tạo queue tăng không giới hạn và treo hoặc làm tăng bộ nhớ.

## 12. Kiểm thử data và metadata

Payload của RSocket có thể mang data và metadata. Với raw RSocket API, có thể tạo payload có cả hai phần và kiểm tra responder nhận đúng nội dung.

Handler:

~~~java
@Override
public Mono<Payload> requestResponse(Payload payload) {
    String data = payload.getDataUtf8();
    String metadata = payload.hasMetadata()
        ? payload.getMetadataUtf8()
        : "";

    return Mono.just(DefaultPayload.create(
        "echo:" + data,
        "seen:" + metadata));
}
~~~

Test:

~~~java
@Test
void requestResponsePreservesMetadata() {
    Payload request =
        DefaultPayload.create("hello", "trace-123");

    Mono<String> result = client.requestResponse(request)
        .map(response ->
            response.getDataUtf8()
                + "|"
                + response.getMetadataUtf8());

    StepVerifier.create(result)
        .expectNext("echo:hello|seen:trace-123")
        .verifyComplete();
}
~~~

Đây là test metadata thô. Nếu ứng dụng dùng composite metadata, routing, authentication hoặc tracing extension, hãy kiểm tra cả MIME type và codec tương ứng. Một payload metadata có byte đúng nhưng MIME type sai vẫn có thể không được giải mã như ứng dụng mong đợi.

## 13. Kiểm thử Spring @MessageMapping qua Local Transport

Khi muốn kiểm tra Spring Messaging routing và codec, có thể dùng RSocketMessageHandler làm responder cho RSocketServer, sau đó tạo requester với LocalClientTransport.

Ví dụ controller:

~~~java
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.rsocket.RSocketMessageHandler;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.stereotype.Controller;

@Controller
static class EchoController {

    @MessageMapping("echo")
    Mono<Message> echo(Message request) {
        return Mono.just(
            new Message("echo:" + request.value()));
    }
}

record Message(String value) {}
~~~

Dựng Spring responder:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders ->
        encoders.add(new Jackson2JsonEncoder()))
    .decoders(decoders ->
        decoders.add(new Jackson2JsonDecoder()))
    .build();

SocketAcceptor acceptor =
    RSocketMessageHandler.responder(
        strategies,
        new EchoController());

Disposable server = RSocketServer.create(acceptor)
    .bind(LocalServerTransport.create(serverName))
    .block(Duration.ofSeconds(5));
~~~

Tạo client requester:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .transport(LocalClientTransport.create(serverName));
~~~

Test route:

~~~java
Mono<Message> result = requester
    .route("echo")
    .data(new Message("hello"))
    .retrieveMono(Message.class);

try {
    StepVerifier.create(result)
        .expectNext(new Message("echo:hello"))
        .verifyComplete();
} finally {
    requester.dispose();
    server.dispose();
}
~~~

Khi kết thúc test, gọi requester.dispose() và server.dispose(). RSocketRequester.Builder.transport(ClientTransport) cho phép dùng transport đã khởi tạo, nên không cần mở TCP port để kiểm tra @MessageMapping.

Cách này kiểm tra được Spring route mapping, serialization/deserialization và RSocket interaction cùng nhau. Nếu ứng dụng phụ thuộc vào Spring Boot auto-configuration, security interceptor, codec custom hoặc @ConnectMapping, hãy dựng đúng các bean/configuration đó trong test thay vì chỉ test controller đơn lẻ.

## 14. Kiểm thử SETUP và kết nối bị từ chối

SETUP là bước khởi tạo RSocket connection. Nếu ứng dụng dùng setup data hoặc metadata, có thể kiểm tra bằng SocketAcceptor dạng đầy đủ để quan sát ConnectionSetupPayload.

Ví dụ acceptor có thể nhận setup và tạo responder:

~~~java
SocketAcceptor acceptor = (setup, sendingSocket) -> {
    String setupData = setup.getDataUtf8();

    if (!"test-client".equals(setupData)) {
        return Mono.error(
            new IllegalStateException("unexpected setup data"));
    }

    return Mono.just(new AbstractRSocket() {
        @Override
        public Mono<Payload> requestResponse(Payload payload) {
            return Mono.just(
                DefaultPayload.create("accepted"));
        }
    });
};
~~~

Client có thể gửi setup payload:

~~~java
RSocketConnector connector = RSocketConnector.create()
    .setupPayload(DefaultPayload.create("test-client"));

RSocket client = connector
    .connect(LocalClientTransport.create(serverName))
    .block(Duration.ofSeconds(5));
~~~

Test setup rejection cần kiểm tra connection không được tạo thành công và kiểm tra lỗi theo contract. Không dùng test request-response thông thường để suy ra setup rejection đã được kiểm tra.

Nếu ứng dụng xác thực bằng setup metadata, hãy tạo metadata đúng MIME type và xác minh principal/authorization ở server. Test local kiểm tra logic auth ở protocol/application layer; nó không kiểm tra TLS certificate hay WebSocket Origin.

## 15. Cách ly test và chạy song song

Local Transport dùng tên server để client tìm endpoint cục bộ. Tên cố định như test-server có thể khiến hai test đồng thời dùng chung địa chỉ hoặc va chạm với server còn sót lại từ test trước.

Nên tạo tên duy nhất:

~~~java
String serverName =
    "rsocket-" + UUID.randomUUID();
~~~

Các nguyên tắc cách ly:

- Mỗi test sở hữu server/client riêng, trừ khi test đang kiểm tra nhiều client trên cùng server.
- Dispose requester/client trước khi dừng server.
- Không chia sẻ mutable state giữa test nếu không cần.
- Reset latch, sink, counter và test fixture cho mỗi test.
- Không phụ thuộc thứ tự chạy test.
- Đặt timeout cho connect, block và StepVerifier.
- Khi chạy song song, bảo đảm mỗi server name là duy nhất.

Nếu muốn kiểm tra nhiều client cùng kết nối một server, hãy tạo nhiều client từ cùng một server name một cách có chủ đích và đóng tất cả client sau test.

## 16. Kiểm thử nhiều client và nhiều connection cục bộ

Local Transport có thể dùng để kiểm tra server chấp nhận nhiều connection độc lập. Ví dụ tạo hai requester với cùng một địa chỉ server:

~~~java
RSocket first = RSocketConnector.connectWith(
    LocalClientTransport.create(serverName))
    .block(Duration.ofSeconds(5));

RSocket second = RSocketConnector.connectWith(
    LocalClientTransport.create(serverName))
    .block(Duration.ofSeconds(5));
~~~

Sau đó gửi request từ cả hai client và xác minh state theo từng session. Cách này hữu ích để kiểm tra:

- Session state có bị chia sẻ nhầm giữa client không.
- Metadata SETUP có được xử lý riêng cho từng connection không.
- Một client dispose có làm ảnh hưởng client khác không.
- Server có giải phóng resource khi một connection đóng không.
- Nhiều connection có thể hoạt động đồng thời mà không trộn response.

Không dùng hai requester trên cùng một connection để thay thế test nhiều connection. Một connection multiplex nhiều stream và nhiều connection độc lập là hai kịch bản khác nhau.

## 17. Quản lý Payload và ByteBuf trong test

Payload của RSocket Java dựa trên cơ chế reference counting của Netty. Với PayloadDecoder.DEFAULT, data và metadata được copy độc lập; ứng dụng không cần tự quản lý buffer gốc như chế độ zero-copy.

Nếu test hoặc ứng dụng bật PayloadDecoder.ZERO_COPY, payload giữ retained slice của buffer frame. Khi đó phải quản lý việc release đúng thời điểm. Không giữ Payload sau khi handler kết thúc nếu không retain đúng cách.

Những lỗi thường gặp:

- Đọc payload nhưng không release trong code zero-copy.
- Release payload trước khi publisher bất đồng bộ còn cần dùng nó.
- Trả cùng một Payload instance cho nhiều subscriber mà không quản lý reference count.
- Dùng payload đã release trong assertion.
- Dùng retain() không cần thiết và tạo leak.

Đối với test cơ bản, giữ decoder mặc định giúp code đơn giản hơn. Chỉ thêm zero-copy test khi ứng dụng thực sự dùng chế độ đó và cần xác minh ownership.

## 18. Kiểm thử timeout và lỗi ở cấp connection

Có thể dùng Local Transport để kiểm tra một số lỗi lifecycle ở cấp RSocket:

- Client dispose connection.
- Server dispose hoặc đóng connection.
- Handler trả lỗi.
- Request bị cancel.
- Setup bị reject.
- Stream đang chạy bị ngắt khi connection đóng.

Tuy nhiên, Local Transport không tạo ra network partition thật. Một test gọi client.dispose() mô phỏng việc đóng connection từ phía client, nhưng không mô phỏng packet loss, TCP retransmission hay proxy reset.

Nếu cần kiểm tra retry/reconnect, có thể điều khiển việc dispose và khởi động lại server cục bộ. Nhưng network failure injection, TCP reset hoặc WebSocket close code cần test qua transport tương ứng.

## 19. Dùng StepVerifier để kiểm tra tín hiệu, không chỉ dữ liệu

Một publisher reactive có ba dạng terminal signal quan trọng:

- onComplete: hoàn tất bình thường.
- onError: kết thúc bằng lỗi.
- cancel: subscriber chủ động dừng nhận.

Test nên xác minh signal phù hợp với contract. Một test chỉ dùng block() rồi so sánh một giá trị thường bỏ qua cancellation, thứ tự và số phần tử.

Ví dụ:

~~~java
StepVerifier.create(client.requestStream(
        DefaultPayload.create("item-")))
    .expectNext("item-1")
    .thenCancel()
    .verify();
~~~

Ví dụ trên xác nhận requester chủ động hủy subscription sau item đầu tiên. Nếu cần xác minh responder đã nhận cancellation, bổ sung latch hoặc test sink ở phía server.

Với stream dài hạn, test nên có điều kiện kết thúc xác định để không treo suite.

## 20. Những lỗi thường gặp khi dùng Local Transport

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng cùng server name cho mọi test | Test va chạm hoặc kết nối nhầm server | Tạo tên ngẫu nhiên theo test |
| Không dispose client/server | Giữ resource và state qua test | Cleanup trong @AfterEach |
| Dùng block() không timeout | Test có thể treo vô hạn | Đặt timeout cho connect và verification |
| Chỉ test mock RSocket | Bỏ qua protocol/transport integration | Thêm Local Transport test |
| Coi FNF completion là business ACK | Khẳng định sai server đã commit | Chờ tín hiệu nghiệp vụ riêng |
| Không test cancellation | Upstream có thể tiếp tục chạy | Dùng take/thenCancel và kiểm tra cleanup |
| Dùng nguồn vô hạn không giới hạn | Queue hoặc test runtime tăng mãi | Dùng nguồn hữu hạn hoặc cancellation |
| Bật zero-copy mà không release | Buffer leak | Kiểm tra ownership/reference count |
| Dùng Local Transport để kết luận TCP/TLS tốt | Bỏ sót lỗi network | Bổ sung TCP/WebSocket integration test |
| Chỉ test raw RSocket khi ứng dụng dùng Spring route | Không kiểm tra @MessageMapping/codec | Dựng RSocketMessageHandler và RSocketRequester |

## 21. Ma trận kiểm thử đề xuất

Một test suite cơ bản có thể chia như sau:

| Nhóm | Test tối thiểu | Công cụ |
|---|---|---|
| Connection | Server bind, client connect, dispose | JUnit 5 |
| Request-response | Response đúng, lỗi được truyền | StepVerifier |
| Fire-and-forget | Handler nhận event | CountDownLatch/test sink |
| Request-stream | Thứ tự, số item, complete | StepVerifier |
| Request-channel | Input stream và response stream | StepVerifier |
| Cancellation | CANCEL dừng publisher phía server | StepVerifier + latch |
| Flow control | Demand theo batch | StepVerifier với initial request |
| Metadata | Data và metadata đúng | DefaultPayload |
| SETUP | Setup data/metadata và rejection | SocketAcceptor |
| Spring Messaging | @MessageMapping, codec, route | RSocketMessageHandler + RSocketRequester |
| Multi-client | Session isolation và concurrent connections | Nhiều LocalClientTransport |
| Cleanup | Resource được đóng sau test | JUnit lifecycle |

Không nhất thiết phải viết tất cả test trong một class. Nên chia theo phạm vi: raw protocol, Spring messaging, security, lifecycle và domain behavior.

## 22. Khi nào phải bổ sung network test?

Local Transport không thay thế kiểm thử network. Hãy bổ sung network integration test khi thay đổi liên quan tới:

- TCP/WebSocket transport configuration.
- TLS, certificate, authentication ở handshake.
- WebSocket endpoint và HTTP mapping path.
- Reverse proxy, ingress, load balancer.
- Max frame size, fragmentation hoặc network buffer.
- Keepalive timeout và connection idle timeout.
- Reconnect/resumption qua network interruption.
- Client ở process/container/máy khác.
- Network latency, throughput hoặc packet failure.

Một bộ test cân bằng thường có nhiều unit test, một số Local Transport integration test và ít network test tập trung vào hạ tầng.

## 23. Quy trình viết một Local Transport test

Có thể áp dụng quy trình sau cho mỗi interaction hoặc route mới:

1. Xác định hành vi cần chứng minh: protocol, mapping hay nghiệp vụ.
2. Tạo server name duy nhất cho test.
3. Khởi tạo RSocketServer với responder thật hoặc Spring RSocketMessageHandler.
4. Kết nối bằng LocalClientTransport.
5. Gửi request bằng RSocket hoặc RSocketRequester.
6. Dùng StepVerifier kiểm tra payload và terminal signal.
7. Kiểm tra side effect bằng test sink, latch hoặc fake repository.
8. Kiểm tra cancellation/cleanup nếu route mở stream dài hạn.
9. Dispose client/requester và server trong mọi trường hợp.
10. Chạy test độc lập và chạy lại trong suite song song.

Test nên xác minh observable behavior. Tránh assert vào implementation detail nội bộ như Stream ID cụ thể hoặc timing chính xác của scheduler nếu đó không phải contract của ứng dụng.

## 24. Checklist trước khi merge

- Đã chọn đúng cấp độ unit, Local Transport hay network test.
- Có dependency rsocket-transport-local trong test scope.
- Các artifact RSocket dùng phiên bản tương thích.
- Mỗi test có server name duy nhất.
- Server và client được khởi tạo trong lifecycle rõ ràng.
- Client/requester được dispose sau test.
- Server được dispose sau test.
- Có timeout cho connect và test verification.
- Request-response có test success và error.
- Stream có test order, completion và cancellation.
- Channel có test cả input lẫn output.
- Fire-and-forget không bị hiểu nhầm là business acknowledgement.
- Metadata/SETUP được test nếu ứng dụng sử dụng.
- Spring @MessageMapping được test qua Spring responder nếu ứng dụng dùng annotation.
- Zero-copy ownership được kiểm tra nếu bật.
- Network-specific behavior có test TCP/WebSocket riêng.

## 25. Kết luận

Local Transport của RSocket Java giúp chạy client và server thật trong cùng JVM mà không mở kết nối mạng. Nó phù hợp để kiểm tra SETUP, request-response, fire-and-forget, request-stream, request-channel, metadata, lỗi, cancellation và flow control một cách nhanh chóng.

Kết hợp LocalServerTransport, LocalClientTransport, JUnit 5 và StepVerifier giúp integration test có thể kiểm tra cả dữ liệu lẫn reactive signals. Khi dùng Spring Messaging, có thể dựng RSocketMessageHandler và RSocketRequester trên Local Transport để kiểm tra @MessageMapping và codec mà không cần TCP port.

Hãy tạo server name riêng cho từng test, đặt timeout và luôn dispose tài nguyên. Local Transport không chứng minh TLS, WebSocket handshake hoặc hành vi mạng thực tế; bổ sung network test cho những ranh giới đó để có độ tin cậy đầy đủ.

Tài liệu tham khảo:
- [RSocket Java – Repository and transport modules](https://github.com/rsocket/rsocket-java)
- [RSocket Java – RSocketServer Javadoc](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [RSocket Java – RSocketConnector Javadoc](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [Spring Framework – RSocket Reference](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework – RSocketRequester.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
- [Project Reactor – Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)


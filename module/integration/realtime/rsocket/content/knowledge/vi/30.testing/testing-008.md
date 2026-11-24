# Kiểm thử đủ bốn mô hình tương tác và yêu cầu ngược

RSocket có bốn mô hình tương tác chính: request-response, fire-and-forget, request-stream và request-channel. Cả bốn đều dùng cùng một connection nhưng có vòng đời, hướng dữ liệu, cách hoàn tất và ngữ nghĩa xác nhận khác nhau. Một bộ kiểm thử chỉ xác nhận request-response không đủ để chứng minh ứng dụng RSocket hoạt động đúng.

RSocket còn là giao thức hai chiều: sau khi connection được thiết lập, server cũng có thể khởi tạo request tới client. Muốn kiểm thử chiều ngược, client phải đăng ký responder cho route mà server gọi. Bài này xây dựng cách kiểm thử cả bốn interaction từ client tới server và một request do server chủ động gửi về client, sử dụng Spring RSocket, Reactor Test và một transport thật trong test.

## 1. Mục tiêu của bộ kiểm thử

Một bộ kiểm thử đủ sâu cần xác nhận:

- Request-response trả đúng một response rồi hoàn tất.
- Fire-and-forget gửi được payload và server thực hiện side effect; việc send hoàn tất không tự chứng minh nghiệp vụ đã xử lý xong.
- Request-stream phát nhiều phần tử theo demand, hoàn tất hoặc lỗi đúng cách.
- Request-channel nhận một luồng request và phát luồng response tương ứng, đồng thời xử lý cancellation và backpressure.
- Server có thể khởi tạo request ngược trên cùng connection và nhận response từ client responder.
- Lỗi route, lỗi handler, timeout và đóng connection được truyền về phía gọi đúng cách.
- Các subscription, stream và connection được đóng sau test để không rò rỉ tài nguyên.

## 2. Sơ đồ các tương tác cần kiểm thử

~~~mermaid
flowchart TD
    C[Client requester] -->|REQUEST_RESPONSE| S[Server handler]
    S -->|Một response| C
    C -->|REQUEST_FNF| S
    S -->|Xử lý side effect, không response| S
    C -->|REQUEST_STREAM| S
    S -->|Nhiều PAYLOAD theo demand| C
    C -->|REQUEST_CHANNEL: stream request| S
    S -->|Stream response| C
    S -->|Request ngược qua cùng connection| C
    C -->|Client responder trả response| S
~~~

Các test nên chạy qua transport RSocket thật, ví dụ TCP trên loopback. Unit test cho service hoặc handler vẫn hữu ích, nhưng không kiểm tra được việc đăng ký route, codec, framing, interaction model và responder hai chiều.

## 3. Chuẩn bị test dependencies

Với Maven, dự án Spring Boot thường đã có Reactor Test qua dependency quản lý phiên bản. Nếu chưa có, thêm:

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dùng JUnit 5, cần dependency test tương ứng của Spring Boot, thường là spring-boot-starter-test. Không tự ghim một phiên bản reactor-test khác với Reactor BOM của Spring Boot vì có thể gây lệch API.

## 4. Tạo server và client responder trong integration test

Để kiểm tra cả hai chiều, test cần dựng một RSocket server và kết nối một client có responder riêng. Spring cung cấp RSocketMessageHandler.responder để biến các object có phương thức được đánh dấu MessageMapping thành SocketAcceptor.

Một fixture test có thể khởi tạo như sau:

~~~java
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.CloseableChannel;
import io.rsocket.transport.netty.server.TcpServerTransport;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import io.rsocket.SocketAcceptor;

class RSocketIntegrationFixture {
    private final RSocketStrategies strategies = RSocketStrategies.create();
    private CloseableChannel server;
    private RSocketRequester requester;
    private ServerHandlers serverHandlers;

    void start(
            ServerHandlers serverHandlers,
            ReverseRequestServerHandler reverseHandler,
            ClientHandlers clientHandlers) {
        this.serverHandlers = serverHandlers;
        SocketAcceptor serverAcceptor =
            RSocketMessageHandler.responder(strategies, serverHandlers, reverseHandler);

        server = RSocketServer.create(serverAcceptor)
            .bind(TcpServerTransport.create("localhost", 7000))
            .block();

        SocketAcceptor clientAcceptor =
            RSocketMessageHandler.responder(strategies, clientHandlers);

        requester = RSocketRequester.builder()
            .rsocketConnector(connector -> connector.acceptor(clientAcceptor))
            .rsocketStrategies(strategies)
            .connectTcp("localhost", 7000)
            .block();
    }

    RSocketRequester requester() {
        return requester;
    }

    ServerHandlers serverHandlers() {
        return serverHandlers;
    }

    void stop() {
        if (requester != null && requester.rsocket() != null) {
            requester.rsocket().dispose();
        }
        if (server != null) {
            server.dispose();
        }
    }
}
~~~

Fixture trên minh họa cấu trúc integration test với port dành riêng cho test. Trong suite chạy song song, không dùng một port cố định chung; hãy cấp port riêng cho mỗi fixture hoặc dùng cơ chế test server cấp ephemeral port rồi truyền port thực tế cho client. Cần gọi stop trong finally hoặc @AfterEach ngay cả khi assertion thất bại.

Ví dụ lifecycle JUnit cho fixture:

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class RSocketInteractionTests {
    private final RSocketIntegrationFixture fixture =
        new RSocketIntegrationFixture();

    @BeforeEach
    void setUp() {
        fixture.start(
            new ServerHandlers(),
            new ReverseRequestServerHandler(),
            new ClientHandlers()
        );
    }

    @AfterEach
    void tearDown() {
        fixture.stop();
    }
}
~~~

ServerHandlers và ClientHandlers là các class test có các method MessageMapping được trình bày ở các phần tiếp theo. Cả hai phía dùng RSocketStrategies tương thích để encode/decode cùng DTO. Nếu ứng dụng dùng composite metadata, custom MIME type hoặc codec riêng, fixture phải sử dụng đúng cấu hình production.

## 5. Khai báo các handler server

Ví dụ dưới đây gom bốn route vào một class để dễ nhìn thấy hợp đồng của từng interaction:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
class ServerHandlers {
    final Sinks.One<AuditEvent> receivedEvent = Sinks.one();

    @MessageMapping("test.rr")
    Mono<Reply> requestResponse(Query query) {
        return Mono.just(new Reply("ok:" + query.value()));
    }

    @MessageMapping("test.fnf")
    Mono<Void> fireAndForget(AuditEvent event) {
        return Mono.fromRunnable(() -> receivedEvent.tryEmitValue(event));
    }

    @MessageMapping("test.stream")
    Flux<Integer> requestStream(StreamQuery query) {
        return Flux.range(query.start(), query.count());
    }

    @MessageMapping("test.channel")
    Flux<Reply> requestChannel(Flux<Command> commands) {
        return commands.map(command -> new Reply("done:" + command.id()));
    }
}
~~~

Các DTO Query, Reply, AuditEvent, StreamQuery và Command là record hoặc class Java của test. Handler trả publisher để Spring quản lý subscription. Không gọi subscribe hoặc block bên trong handler.

Các DTO minh họa có thể khai báo dưới dạng record:

~~~java
record Query(String value) {}
record Reply(String value) {}
record AuditEvent(String id, String type) {}
record StreamQuery(int start, int count) {}
record Command(String id) {}
record DeviceCommand(String id) {}
record ClientAck(String commandId, boolean accepted) {}
~~~

## 6. Kiểm thử request-response

Request-response có một request payload và tối đa một response payload. Sau khi response được phát, interaction hoàn tất. Test cần kiểm tra nội dung response và trạng thái complete:

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void requestResponseReturnsOneReply() {
    Query query = new Query("order-17");

    StepVerifier.create(
            fixture.requester()
                .route("test.rr")
                .data(query)
                .retrieveMono(Reply.class)
        )
        .expectNext(new Reply("ok:order-17"))
        .verifyComplete();
}
~~~

Nên bổ sung các trường hợp:

- Handler trả Mono.empty(): requester hoàn tất mà không có response.
- Handler trả Mono.error(): requester nhận lỗi tương ứng.
- Route không tồn tại: requester nhận lỗi route/protocol, không được giả định là response rỗng.
- Payload không giải mã được: test xác nhận lỗi serialization hoặc metadata được truyền về đúng tầng.
- Request vượt timeout: caller nhận timeout và không giữ subscription vô hạn.

## 7. Kiểm thử fire-and-forget

Fire-and-forget chỉ gửi request payload, không có response payload. Với Spring, client dùng send() và nhận Mono<Void> cho thao tác gửi:

~~~java
import java.time.Duration;

@Test
void fireAndForgetDeliversEventToServerHandler() {
    AuditEvent event = new AuditEvent("evt-9", "order-created");

    StepVerifier.create(
            fixture.requester()
                .route("test.fnf")
                .data(event)
                .send()
        )
        .verifyComplete();

    StepVerifier.create(
            fixture.serverHandlers().receivedEvent.asMono()
                .timeout(Duration.ofSeconds(2))
        )
        .expectNext(event)
        .verifyComplete();
}
~~~

Hai assertion có ý nghĩa khác nhau:

- Mono từ send() hoàn tất cho biết thao tác gửi ở phía requester đã hoàn tất theo API.
- Sinks.One ở server xác nhận handler đã quan sát và xử lý event trong test.

Không dùng riêng verifyComplete() trên send() để kết luận side effect nghiệp vụ đã commit. Nếu nghiệp vụ cần xác nhận, hãy dùng request-response hoặc một acknowledgement riêng. Với test fire-and-forget, nên dùng latch, sink hoặc probe có timeout để tránh test treo nếu handler không nhận event.

## 8. Kiểm thử request-stream và demand

Request-stream trả nhiều response payload. Requester điều tiết số phần tử muốn nhận bằng demand. Test bắt đầu với một phần tử rồi tăng demand theo nhóm nhỏ để xác nhận stream không phát vượt lượng đã yêu cầu:

~~~java
@Test
void requestStreamRespectsDemandAndCompletes() {
    Flux<Integer> response = fixture.requester()
        .route("test.stream")
        .data(new StreamQuery(10, 5))
        .retrieveFlux(Integer.class);

    StepVerifier.create(response, 1)
        .expectNext(10)
        .thenRequest(2)
        .expectNext(11, 12)
        .thenRequest(2)
        .expectNext(13, 14)
        .verifyComplete();
}
~~~

Test này xác nhận response stream phát đủ năm phần tử theo các lần request và sau đó complete. Nó không chỉ kiểm tra giá trị mà còn kiểm tra demand được điều khiển từ subscriber.

Một test khác nên hủy stream trước khi nguồn hoàn tất:

~~~java
StepVerifier.create(response, 1)
    .expectNext(10)
    .thenCancel()
    .verify();
~~~

Khi cancel, server nhận cancellation cho stream và publisher upstream cần dừng hoặc giải phóng tài nguyên. Có thể gắn doFinally trong test handler để xác nhận signal CANCEL được quan sát. Không yêu cầu server gửi tiếp các payload sau khi stream đã bị hủy.

## 9. Kiểm thử request-channel

Request-channel nhận một publisher request từ requester và trả một publisher response từ responder. Test phải kiểm tra cả việc gửi nhiều request lẫn nhận nhiều response:

~~~java
@Test
void requestChannelMapsEachCommandToAReply() {
    Flux<Command> commands = Flux.just(
        new Command("c-1"),
        new Command("c-2"),
        new Command("c-3")
    );

    Flux<Reply> replies = fixture.requester()
        .route("test.channel")
        .data(commands)
        .retrieveFlux(Reply.class);

    StepVerifier.create(replies, 1)
        .expectNext(new Reply("done:c-1"))
        .thenRequest(2)
        .expectNext(
            new Reply("done:c-2"),
            new Reply("done:c-3")
        )
        .verifyComplete();
}
~~~

Nếu handler dùng flatMap để xử lý command đồng thời, thứ tự response có thể khác thứ tự request. Khi thứ tự là một phần hợp đồng, dùng concatMap hoặc flatMapSequential và viết test xác nhận thứ tự. Nếu thứ tự không được bảo đảm, assertion nên so sánh tập kết quả hoặc kiểm tra theo command ID.

Các tình huống quan trọng khác:

- Request publisher phát lỗi giữa chừng.
- Client cancel channel khi response stream vẫn còn dữ liệu.
- Server handler lỗi khi xử lý một command.
- Downstream yêu cầu chậm để xác nhận backpressure.
- Client gửi publisher rỗng và server hoàn tất đúng cách.

## 10. Kiểm thử request ngược từ server về client

Đây là phần dễ bị bỏ sót: server là requester của một interaction mới và client là responder. Client phải đăng ký route tương ứng trong SocketAcceptor khi kết nối:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import reactor.core.publisher.Mono;
import org.springframework.stereotype.Controller;

@Controller
class ClientHandlers {
    @MessageMapping("client.command")
    Mono<ClientAck> command(DeviceCommand command) {
        return Mono.just(new ClientAck(command.id(), true));
    }
}
~~~

Server handler nhận RSocketRequester gắn với connection hiện tại rồi gọi route trên client:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.handler.annotation.MessageMapping;
import reactor.core.publisher.Mono;
import org.springframework.stereotype.Controller;

@Controller
class ReverseRequestServerHandler {
    @MessageMapping("test.reverse")
    Mono<ClientAck> reverse(
            DeviceCommand command,
            RSocketRequester requester) {

        return requester.route("client.command")
            .data(command)
            .retrieveMono(ClientAck.class);
    }
}
~~~

Test gửi request tới server; trong khi xử lý, server khởi tạo request ngược trên cùng connection và chờ response từ ClientHandlers:

~~~java
import java.time.Duration;

@Test
void serverCanRequestClientOnTheSameConnection() {
    DeviceCommand command = new DeviceCommand("cmd-12");

    StepVerifier.create(
            fixture.requester()
                .route("test.reverse")
                .data(command)
                .retrieveMono(ClientAck.class)
                .timeout(Duration.ofSeconds(2))
        )
        .expectNext(new ClientAck("cmd-12", true))
        .verifyComplete();
}
~~~

Nếu client không đăng ký route client.command, test phải xác nhận server nhận lỗi route hoặc lỗi interaction. Nếu client handler phát lỗi hoặc không trả lời, test cần xác nhận lỗi được truyền về hoặc timeout được áp dụng.

Request ngược ở đây được compose trong handler MessageMapping thông thường. Với ConnectMapping xử lý SETUP, không nên giữ quá trình chấp nhận setup chờ một request ngược tới client; hãy hoàn tất setup trước rồi khởi chạy tác vụ độc lập theo lifecycle của connection.

## 11. Kiểm thử request ngược chủ động sau SETUP

Một biến thể khác là server lưu requester theo connection sau khi setup hoàn tất rồi chủ động gửi request khi có sự kiện nghiệp vụ. Test cần:

1. Kết nối client có client responder.
2. Hoàn tất SETUP và xác nhận server đã đăng ký session.
3. Kích hoạt một event phía server, ví dụ lệnh refresh.
4. Server lấy requester của đúng connection và gọi route client.
5. Client trả acknowledgement; test xác nhận command ID và kết quả.
6. Đóng connection và xác nhận requester được gỡ khỏi registry.

Không gọi request ngược đồng bộ trong chính pipeline đang chấp nhận SETUP. Ngoài ra, requester được lưu phải gắn với connection ID và principal đã xác thực; không dùng một requester toàn cục cho nhiều client.

## 12. Kiểm thử lỗi, timeout và cancellation

Với từng interaction, nên kiểm tra các đường kết thúc:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Complete | Publisher hoàn tất và tài nguyên được giải phóng. |
| Application error | Requester nhận lỗi hoặc mã lỗi ứng dụng theo hợp đồng. |
| Cancel | Publisher upstream dừng và cleanup được gọi. |
| Timeout | Caller kết thúc đúng deadline; không giữ subscription vô hạn. |
| Connection loss | Các stream đang chạy kết thúc bằng lỗi phù hợp; client có thể reconnect/resume theo chính sách riêng. |
| Missing route | Requester nhận lỗi route, không bị nhầm thành response rỗng. |
| Serialization failure | Lỗi codec được phát hiện và báo về test. |

Ví dụ đặt timeout:

~~~java
import java.time.Duration;

StepVerifier.create(
        fixture.requester()
            .route("test.reverse")
            .data(command)
            .retrieveMono(ClientAck.class)
            .timeout(Duration.ofSeconds(2))
    )
    .expectNextMatches(ack -> ack.accepted())
    .verifyComplete();
~~~

Timeout phía client không chứng minh server hoặc client responder chưa thực hiện side effect. Nếu test retry một command, dùng command ID và idempotency để tránh thực hiện trùng.

## 13. Kiểm thử WebSocket ngoài TCP

Các test interaction không phụ thuộc vào TCP nếu contract payload và route giống nhau. Có thể chạy cùng bộ test trên WebSocket bằng cách kết nối requester tới URI endpoint WebSocket của ứng dụng:

~~~java
import java.net.URI;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .connectWebSocket(URI.create("ws://localhost:8080/rsocket"))
    .block();
~~~

Endpoint server phải được cấu hình WebSocket transport và mapping path tương ứng. Nên có ít nhất một smoke test WebSocket để xác nhận HTTP Upgrade, mapping path, codec và route. Không cần lặp lại toàn bộ ma trận test trên WebSocket nếu transport-specific behavior không thay đổi; có thể dùng test parameterized để chạy cùng contract suite trên TCP và WebSocket.

## 14. Dùng StepVerifier đúng cách

StepVerifier giúp kiểm tra publisher theo từng signal:

- expectNext/expectNextMatches kiểm tra giá trị.
- verifyComplete xác nhận complete.
- expectError/expectErrorMatches xác nhận lỗi.
- thenRequest(n) kiểm soát demand.
- thenCancel kiểm tra cancellation.
- verify(Duration) đặt giới hạn thời gian cho test để tránh treo vô hạn.

Không dùng block() chỉ để lấy kết quả trong test reactive nếu có thể dùng StepVerifier. Với fixture khởi tạo server, việc block() ở ranh giới setup/teardown có thể chấp nhận được vì đó là lifecycle test, không phải trong handler hoặc event loop.

Đối với Fire-and-Forget, hãy kiểm tra side effect riêng bằng sink/probe có timeout. Đối với request-channel, cần kiểm tra cả request publisher và response publisher, không chỉ xác nhận requester Mono/Flux được tạo ra.

## 15. Kiểm thử transport và cleanup

Một integration test đáng tin cậy cần quản lý server và requester:

- Khởi động server trước khi client kết nối.
- Dùng port riêng hoặc ephemeral port để test có thể chạy song song.
- Tạo client responder trước khi connect nếu cần server gọi ngược.
- Dispose requester và server trong finally hoặc @AfterEach.
- Chờ onClose khi cần xác nhận connection thực sự đóng.
- Không chia sẻ một requester giữa các test độc lập nếu test thay đổi state của connection.
- Đặt timeout cho mọi test có khả năng chờ network hoặc handler.

Nếu dùng Spring Boot Test, có thể khởi chạy ApplicationContext với RSocket server thật và inject requester builder đã cấu hình. Test nên dùng đúng RSocketStrategies, authentication và route metadata như production để phát hiện lỗi wiring.

## 16. Ma trận kiểm thử đề xuất

| Interaction | Happy path | Demand/cancel | Error/timeout | Reverse request |
| --- | --- | --- | --- | --- |
| Request-response | Một response đúng | Không áp dụng nhiều phần tử; cancel trước response nếu cần | Handler error, missing route, timeout | Server gọi client và nhận một response |
| Fire-and-Forget | Handler nhận event | Không có response demand | Connection loss hoặc lỗi gửi | Server gửi FNF tới client nếu client có route |
| Request-stream | Nhiều response đúng thứ tự | Request từng phần, cancel giữa stream | Publisher error, timeout | Server mở stream từ client nếu có route |
| Request-channel | Nhiều request và response | Backpressure hai chiều, cancel channel | Request source hoặc handler error | Server mở channel tới client nếu có responder |

Không phải mọi ứng dụng đều cần server khởi tạo cả bốn interaction về phía client. Tuy nhiên, nếu ứng dụng tuyên bố hỗ trợ hai chiều cho một mô hình cụ thể, cần có test tương ứng để xác nhận client đã đăng ký responder và server có thể khởi tạo tương tác đó.

## 17. Những lỗi thường gặp

**Chỉ test request-response.** Bốn interaction có semantics và lifecycle khác nhau; cần test riêng từng loại.

**Dùng send() để khẳng định Fire-and-Forget đã xử lý xong.** send() không trả response nghiệp vụ; cần quan sát handler hoặc dùng acknowledgement.

**Dùng initial demand bằng 0 cho request-stream mà không xét protocol.** Request-stream có initialRequestN ở frame mở stream; dùng initial demand dương (ví dụ 1), rồi gọi thenRequest để kiểm tra các lần bổ sung demand.

**Không test cancellation.** Stream có thể giữ database cursor, subscription hoặc tài nguyên khác nếu cancel không được truyền và cleanup không chạy.

**Quên client responder.** Server gọi route ngược nhưng client chưa đăng ký SocketAcceptor nên interaction thất bại.

**Gọi request ngược trong setup và chờ response.** SETUP phải hoàn tất trước khi request ứng dụng bắt đầu; khởi chạy tác vụ ngược độc lập sau khi connection sẵn sàng.

**Dùng một requester cho nhiều test song song.** State, stream và connection lifecycle có thể ảnh hưởng lẫn nhau; tạo fixture riêng.

**Không dispose server/client.** Test để lại socket hoặc subscription có thể gây flaky test và giữ JVM không thoát.

## 18. Ghi nhớ

- Kiểm thử RSocket cần bao phủ request-response, fire-and-forget, request-stream và request-channel.
- Dùng StepVerifier để kiểm tra value, complete, error, demand và cancellation.
- Fire-and-Forget không có response payload; send() hoàn tất không đồng nghĩa side effect đã commit.
- Request-stream phải kiểm tra demand từng phần và cancel khi subscriber không còn cần dữ liệu.
- Request-channel cần kiểm tra publisher request và publisher response cùng backpressure hai chiều.
- Muốn kiểm thử request ngược, client phải đăng ký responder trong SocketAcceptor khi connect.
- Server có thể nhận RSocketRequester trong handler để gọi route trên đúng connection.
- Không chờ request ngược trong pipeline chấp nhận SETUP; khởi chạy sau khi connection đã sẵn sàng.
- Kiểm thử lỗi route, application error, timeout, connection loss và serialization failure.
- Chạy integration test trên TCP và ít nhất một smoke test WebSocket nếu ứng dụng hỗ trợ cả hai.
- Dispose requester/server và cleanup stream trong mọi đường kết thúc của test.

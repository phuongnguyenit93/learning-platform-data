# WebSocketClient và phối hợp các kết nối trong Spring WebFlux

## 1. Bối cảnh và mục tiêu

Một ứng dụng Spring WebFlux có thể vừa là WebSocket **server** cho browser, vừa là WebSocket **client** của những hệ thống khác. Ví dụ một gateway nhận dữ liệu giá từ ba nguồn, một backend kết nối đến hàng trăm thiết bị, hoặc một dịch vụ chat cần duy trì các kênh hai chiều.

Bài toán không chỉ là "mở kết nối". Cần xác định:

- Có một session hay nhiều session độc lập?
- Client gửi một command rồi nhận một reply, hay gửi và nhận liên tục?
- Kết quả từ nhiều connection cần chờ đủ, lấy kết quả nhanh nhất hay chấp nhận partial success?
- Có bao nhiêu connection được mở cùng lúc?
- Khi một session lỗi, các session khác có phải hủy không?
- Khi mất kết nối, reconnect thế nào để không gửi command trùng?
- Ai chịu trách nhiệm đóng session, giải phóng buffer, timer và subscription?

WebSocketClient của Spring WebFlux cho phép khởi tạo handshake và xử lý phiên bằng API reactive. Mono/Flux của Reactor giúp kết hợp nhiều session, giới hạn fan-out và truyền error/cancellation nhất quán.

## 2. Phân biệt các abstraction

| Thành phần | Nhiệm vụ |
| --- | --- |
| WebClient | Reactive HTTP client cho request/response và HTTP streaming |
| WebSocketClient | Khởi tạo WebSocket handshake rồi chạy WebSocketHandler cho session |
| ReactorNettyWebSocketClient | WebSocketClient dùng Reactor Netty |
| WebSocketHandler | Hàm xử lý vòng đời một session, trả Mono<Void> |
| WebSocketSession | Một phiên WebSocket với receive(), send(), close() |
| WebSocketMessage | Text, binary hoặc control message |
| Mono<Void> từ execute() | Completion/error của phiên, không chứa payload message |

WebSocket khác HTTP thông thường ở chỗ sau handshake, cả hai bên gửi WebSocket messages qua một connection lâu dài, không tạo HTTP request riêng cho từng message.

WebSocket cũng không quy định kiểu business message: JSON envelope, correlation ID, ACK, subscription topic và quy tắc replay phải do ứng dụng hoặc subprotocol như STOMP định nghĩa. WebSocketClient thuần không tự động trở thành STOMP client.

## 3. Khởi tạo WebSocketClient và handshake

### 3.1. Tạo client

~~~java
import java.net.URI;

import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

import reactor.core.publisher.Mono;

WebSocketClient client = new ReactorNettyWebSocketClient();

URI uri = URI.create("ws://localhost:8080/ws/echo");

Mono<Void> lifecycle = client.execute(
        uri,
        session -> session.receive()
                .doOnNext(message ->
                        System.out.println(message.getPayloadAsText()))
                .then());
~~~

Đây là snippet cần đặt bên trong method Java. execute() trả **Mono<Void> lazy**: khi subscriber subscribe, handshake bắt đầu và handler được thực thi. Mono hoàn tất khi handling session hoàn tất. Không có payload nào được phát trực tiếp qua Mono<Void>.

HTTP/1.1 handshake thông thường:

~~~http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
~~~

Server chấp nhận trả 101 Switching Protocols. Sau đó connection dùng WebSocket frames. Với HTTP/2 có cơ chế Extended CONNECT; không phải môi trường nào cũng thực hiện đúng handshake HTTP/1.1 ở trên.

### 3.2. Hai overload execute

~~~java
Mono<Void> execute(URI uri, WebSocketHandler handler);

Mono<Void> execute(URI uri, HttpHeaders headers,
                   WebSocketHandler handler);
~~~

Overload có HttpHeaders dùng để tùy chỉnh handshake từ Java backend client:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.setBearerAuth(accessToken);

Mono<Void> lifecycle = client.execute(
        URI.create("wss://stream.example/ws"),
        headers,
        session -> session.receive().then());
~~~

accessToken là credential lấy từ hệ thống cấp token an toàn, không hardcode. Java client có thể đặt Authorization header, nhưng browser WebSocket constructor không cho tự đặt tùy ý HTTP Authorization header.

### 3.3. Lựa chọn implementation

ReactorNettyWebSocketClient thích hợp trong Spring Boot WebFlux sử dụng Reactor Netty. Spring Framework cũng hỗ trợ các triển khai khác (chẳng hạn Jetty), nhưng chúng có thể khác về lifecycle, TLS, backpressure và cấu hình frame.

Không nhầm interface reactive org.springframework.web.reactive.socket.client.WebSocketClient với WebSocketClient trong Servlet stack hoặc API browser.

## 4. Vòng đời WebSocketSession

### 4.1. Các method cần nhớ

| API | Contract |
| --- | --- |
| receive() | Flux<WebSocketMessage> đầu vào; thường hoàn tất khi session đóng |
| send(Publisher<WebSocketMessage>) | Mono<Void> kết thúc khi nguồn outbound hoàn tất và message đã được ghi |
| textMessage(String) | Tạo text message từ String |
| binaryMessage(...) | Tạo binary message bằng DataBufferFactory |
| close() | Mono<Void> đóng phiên bình thường khi được subscribe |
| close(CloseStatus) | Đóng với code/reason phù hợp |
| closeStatus() | Publisher cho biết trạng thái đóng |
| getHandshakeInfo() | Thông tin handshake |
| getId() | ID của session hiện tại |

Handler phải trả một Mono<Void> phản ánh **toàn bộ công việc của session**. Nếu handler trả Mono.empty() ngay nhưng đồng thời gọi subscribe() cho receive/send riêng, framework có thể coi session đã kết thúc trong khi các tác vụ độc lập chưa hoàn tất.

### 4.2. Echo server đúng kiểu reactive

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> outgoing = session.receive()
            .filter(message ->
                    message.getType() == WebSocketMessage.Type.TEXT)
            .map(message -> session.textMessage(
                    "echo: " + message.getPayloadAsText()));

    return session.send(outgoing);
}
~~~

Một luồng inbound được chuyển thành một luồng outbound. Không có subscribe() thủ công. Đối với text message, getPayloadAsText() được gọi đồng bộ bên trong mapper nên không giữ pooled DataBuffer vượt lifecycle của message.

Nếu cần chuyển một message thô sang tác vụ bất đồng bộ và giữ buffer, phải xem contract retain/release của DataBuffer/WebSocketMessage. Cách đơn giản hơn với text là copy payload thành String rồi mới đưa qua boundary bất đồng bộ.

### 4.3. Hai hướng gửi và nhận độc lập

~~~java
Mono<Void> receive = session.receive()
        .doOnNext(msg -> processText(msg.getPayloadAsText()))
        .then();

Flux<WebSocketMessage> outgoing =
        commands.map(session::textMessage);

Mono<Void> send = session.send(outgoing);

return Mono.when(receive, send);
~~~

Đây là snippet minh họa, processText và commands do ứng dụng cung cấp. Mono.when subscribe cả hai nhánh và đợi completion. Nếu receive là stream vô hạn và commands cũng không bao giờ kết thúc, session sống cho tới khi có close, cancellation hoặc error.

Đừng gọi nhiều session.send độc lập trên cùng session mà không điều phối. Khi có nhiều producer, hợp nhất chúng thành **một outbound Publisher** (có bounded queue và overload policy phù hợp) rồi gửi qua một session.send.

## 5. Phối hợp hai hay nhiều kết nối

### 5.1. Chờ session hoàn tất bằng Mono.when

~~~java
Mono<Void> sessionA = client.execute(uriA, handlerA);
Mono<Void> sessionB = client.execute(uriB, handlerB);

Mono<Void> allDone = Mono.when(sessionA, sessionB);
~~~

Mono.when phối hợp completion của các publisher và propagates error. Nó phù hợp với nhiều tác vụ Mono<Void>. Nếu session được thiết kế sống hàng giờ, allDone cũng chưa hoàn tất cho tới khi các session kết thúc.

**Không dùng Mono.zip(sessionA, sessionB) để lấy hai message** vì Mono<Void> không phát onNext, nên zip không có dữ liệu để tạo tuple.

### 5.2. Lấy một reply nghiệp vụ từ mỗi session, sau đó zip

Nếu mỗi session gửi một command rồi nhận một reply và đóng, ứng dụng có thể tự xây method echo trả Mono<String>. Khi đó:

~~~java
Mono<String> replyA = gateway.echo(uriA, "ping");
Mono<String> replyB = gateway.echo(uriB, "ping");

Mono<String> combined = Mono.zip(
        replyA,
        replyB,
        (left, right) -> "A=" + left + "; B=" + right);
~~~

gateway.echo là method tự viết trong ví dụ cuối bài, không phải method mặc định của Spring. Mono.zip chờ cả hai nguồn phát giá trị; nếu một nguồn lỗi, mặc định zip fail-fast và hủy nguồn còn lại. Nếu một nguồn hoàn tất rỗng, zip cũng không có đủ dữ liệu để kết hợp.

Một session WebSocket có thể nhận nhiều message hoặc trả reply theo thứ tự khác với thứ tự command. Vì vậy, mô hình "gửi một, nhận một" chỉ đúng khi upstream có contract rõ ràng. Với nhiều command đồng thời trên cùng session, cần correlationId và registry các reply đang chờ.

### 5.3. Nhiều URI độc lập: Flux.flatMap

~~~java
Flux<WsReply> replies = Flux.fromIterable(targets)
        .flatMap(target ->
                gateway.echo(target.uri(), "ping")
                        .map(text -> new WsReply(
                                target.label(), text)),
                4);
~~~

Ở đây flatMap với maxConcurrency=4 cho phép tối đa bốn inner Publisher được subscribe đồng thời trong một subscription. Khi mỗi inner Publisher thực hiện một WebSocket exchange ngắn và kết thúc sau reply, đó cũng là giới hạn số session đang chạy qua pipeline này.

Nếu mỗi handler giữ stream vô hạn, bốn slot bị chiếm cho đến lúc bốn session đóng; các target tiếp theo chưa được subscribe. Đây là điều quan trọng khi phối hợp nhiều kết nối **lâu dài**.

### 5.4. flatMap, flatMapSequential và concatMap

| Operator | Nhiều session song song? | Thứ tự output |
| --- | --- | --- |
| flatMap(mapper, 4) | Có, tối đa 4 inner publisher | Theo thời điểm hoàn tất |
| flatMapSequential(mapper, 4, 1) | Có, tối đa 4 inner publisher | Giữ thứ tự target |
| concatMap(mapper) | Không, tuần tự từng inner publisher | Giữ thứ tự target |

Ví dụ source A phản hồi sau 800 ms, B sau 100 ms, C sau 400 ms. Với flatMap, output có thể là B, C, A. Với flatMapSequential, output là A, B, C nhưng B/C có thể phải chờ trong queue. Với concatMap, B chỉ được bắt đầu sau khi A hoàn tất.

Nếu upstream không phụ thuộc thứ tự và muốn giảm thời gian tổng hợp, flatMap là lựa chọn thông dụng. Nếu nghiệp vụ cần đúng thứ tự danh sách, dùng flatMapSequential. Nếu một phiên phải hoàn tất trước khi mở phiên sau, dùng concatMap.

## 6. Per-subscription concurrency không phải quota toàn hệ thống

maxConcurrency áp dụng theo từng subscription của một Flux. Nếu một HTTP endpoint của ứng dụng tạo pipeline flatMap(..., 8), 20 HTTP request đồng thời có thể tạo nhiều hơn 8 WebSocket sessions trên toàn ứng dụng.

Cần phân biệt:

- **Per-batch concurrency:** giới hạn inner publisher của một subscription bằng flatMap.
- **Global bulkhead:** giới hạn số session toàn process bằng limiter dùng chung; permit phải được release khi complete/error/cancel.
- **Rate limit:** giới hạn số handshake hoặc message trên mỗi giây, khác số connection đang mở.
- **Transport resource:** connection, buffer, socket, thread/event loop và file descriptor.
- **Upstream quota:** giới hạn theo tenant, account, token hoặc IP do server áp dụng.

Không dùng Semaphore.acquire() blocking trực tiếp trên event-loop. Nếu cần global limiter, chọn mô hình acquire permit bất đồng bộ, cleanup chắc chắn và test race/cancellation.

Một connection sau WebSocket handshake không tương đương một HTTP keep-alive connection đã sẵn sàng nhận HTTP request tiếp theo. Không suy luận rằng maxConnections trong HTTP pool chính là giới hạn các WebSocket session nghiệp vụ.

## 7. Error, cancellation và partial success

### 7.1. Hành vi lỗi mặc định

Khi một inner publisher trong flatMap phát error, downstream mặc định nhận error và những inner publisher còn lại trong subscription có thể bị cancel.

Đây là hành vi phù hợp nếu batch chỉ có ý nghĩa khi mọi nguồn thành công. Nhưng dashboard tổng hợp thường muốn hiển thị kết quả còn lại ngay cả khi một nguồn offline.

### 7.2. Phục hồi lỗi trong từng mapper

~~~java
Flux<TargetResult> results = Flux.fromIterable(targets)
        .flatMap(target ->
                gateway.echo(target.uri(), "ping")
                        .map(text -> TargetResult.ok(
                                target.label(), text))
                        .onErrorResume(error -> Mono.just(
                                TargetResult.failed(
                                        target.label(),
                                        classify(error)))),
                4);
~~~

Đây là snippet với TargetResult và classify do ứng dụng định nghĩa. Đặt onErrorResume **bên trong** mapper để một endpoint lỗi không làm hủy toàn bộ batch. Không trả raw exception, token hoặc URL chứa credential cho client.

Nếu đặt onErrorResume sau flatMap, lỗi đầu tiên đã có thể hủy các phiên khác trước khi fallback chạy.

Mono.whenDelayError và Mono.zipDelayError trì hoãn error của nhiều nguồn cho tới khi các nguồn khác có cơ hội kết thúc. Chúng không tự biến lỗi thành thành công; với session sống lâu, việc trì hoãn có thể kéo dài không giới hạn nếu thiếu timeout.

### 7.3. Timeout cần phân loại

~~~java
Mono<Void> lifecycle = client.execute(uri, handler)
        .timeout(Duration.ofSeconds(10));
~~~

Đây là timeout cho **toàn bộ Mono<Void>**, không phải chỉ handshake. Nếu handler vốn giữ session hàng giờ, timeout trên sẽ đóng session sau 10 giây ngay cả khi hoàn toàn bình thường.

Hãy phân biệt:

1. Handshake/connection timeout.
2. First-reply timeout sau khi đã gửi command.
3. Idle timeout khi không nhận dữ liệu/heartbeat.
4. Tổng thời gian một exchange ngắn.
5. Lifetime tối đa của session.
6. Shutdown/close timeout.

Ví dụ echo gửi một lần nhận một reply có thể có timeout 5 giây cho toàn exchange. Nhưng client đọc dữ liệu chứng khoán liên tục không nên timeout chỉ vì session đã sống quá 5 giây.

### 7.4. Cancellation

Khi downstream hủy subscription, Reactor truyền cancellation tới inner session và connector có thể chấm dứt I/O. Không mở subscribe() tách rời nếu muốn phép hủy từ HTTP request ban đầu ảnh hưởng tới WebSocket client.

Khi đóng có chủ đích, dùng session.close() trong returned publisher. Khi cần báo close code/reason, dùng close(CloseStatus) và không đưa thông tin nhạy cảm vào reason.

## 8. Reconnect và delivery semantics

### 8.1. retryWhen chỉ chạy khi error

~~~java
Mono<Void> reconnectOnError = client.execute(uri, handler)
        .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
                .maxBackoff(Duration.ofSeconds(20))
                .jitter(0.5));
~~~

retryWhen resubscribe khi source phát lỗi. Nếu server đóng session bình thường và handler hoàn tất thành công, nó **không** tự reconnect. Nếu yêu cầu reconnect cả sau normal close, phải xây vòng lặp kết nối có delay, stop condition và lifecycle shutdown riêng.

Không dùng repeat() vô hạn, không delay: có thể gây reconnect storm khi upstream hoặc proxy liên tục đóng connection.

### 8.2. Message ID, ACK và replay

WebSocket cung cấp transport message nhưng không bảo đảm business command được xử lý đúng một lần. Khi connection đứt ngay sau lúc gửi, client không chắc server đã nhận, đã xử lý hay đã phản hồi.

Với thao tác quan trọng, thiết kế:

- correlationId/messageId duy nhất.
- Server acknowledgement gắn cùng ID.
- Pending request registry với timeout và giới hạn dung lượng.
- Idempotency/deduplication ở server.
- Sequence number và replay log nếu dữ liệu cần phục hồi.
- Chính sách reconnect exponential backoff có jitter.
- Cách xử lý reply đến trễ sau timeout và response bị lặp.

Đừng retry vô điều kiện một command thay đổi dữ liệu nếu server không hỗ trợ idempotency.

### 8.3. Đừng subscribe cùng một cold publisher hai lần

~~~java
Mono<Void> lifecycle = client.execute(uri, handler);

// Minh họa anti-pattern, không dùng trong service:
lifecycle.subscribe();
lifecycle.subscribe();
~~~

Hai subscription có thể tạo hai handshake và hai session khác nhau. Nếu muốn chia sẻ một kết nối giữa nhiều caller, cần connection manager quản lý một session cùng outbound publisher duy nhất và cơ chế phân phối inbound message; share() trên Mono<Void> không phải tự động tạo multiplexer message.

## 9. Một session nhiều message hay nhiều session độc lập?

### 9.1. Một session, nhiều command

Một socket có thể xử lý nhiều command. Khi server phản hồi không theo thứ tự gửi, client cần ghép đúng reply qua correlationId:

~~~json
{"type":"request","correlationId":"req-82","payload":{"symbol":"ABC"}}
~~~

Phản hồi:

~~~json
{"type":"response","correlationId":"req-82","payload":{"price":12.5}}
~~~

Connection manager có thể dùng Map<correlationId, Sinks.One<Reply>> cho những request đang chờ. Phải giới hạn số entry, xóa khi complete/error/cancel, xử lý race giữa timeout và reply, và không chuyển quyền sở hữu raw DataBuffer sang người nhận không có cleanup.

Nên có **một outbound send stream** tổng hợp nhiều producer, thay vì nhiều thành phần cùng gọi session.send() riêng lẻ.

### 9.2. Nhiều session tới các hệ thống khác nhau

Nhiều session phù hợp khi kết nối nhiều upstream, device hoặc tenant độc lập. Nó giúp cô lập trạng thái, lỗi, token và reconnect policy, nhưng tốn thêm handshake, socket, heartbeat và memory.

Dùng flatMap với maxConcurrency cho các exchange **hữu hạn**. Với session sống lâu, cân nhắc manager giữ danh sách connection độc lập, limiter toàn cục, resource quotas, reconnect schedule và API shutdown.

Nếu cần pub/sub quy mô rất lớn hoặc fan-out dữ liệu qua nhiều application instance, cân nhắc message broker; WebSocketClient không tự tạo distributed event log hay đảm bảo replay.

## 10. Ví dụ đầy đủ Java 17+ Spring Boot 3.5.16

Ví dụ tạo một server WebSocket echo tại /ws/echo và một client Java phối hợp nhiều phiên. Gồm:

- EchoWebSocketHandler: server echo text.
- SocketRouteConfiguration: ánh xạ URL.
- ReactiveSocketCoordinator: Java WebSocketClient gửi một text, đợi một reply, đóng session, trả Mono<String>.
- gather: tạo một exchange cho từng target với giới hạn active session.
- gatherOrdered: fan-out có giữ thứ tự.
- Integration test dùng server thật ở random port và StepVerifier.

Trong demo, mỗi exchange là một session **hữu hạn**: gửi một text, nhận một text, close. Không tự động áp dụng cùng lifecycle cho client cần giữ stream vô hạn.

### 10.1. Cấu trúc tệp

~~~text
webflux-ws-client-demo/
├── pom.xml
└── src/
    ├── main/java/example/ws/
    │   ├── DemoApplication.java
    │   ├── EchoWebSocketHandler.java
    │   ├── SocketRouteConfiguration.java
    │   ├── WsTarget.java
    │   ├── WsReply.java
    │   └── ReactiveSocketCoordinator.java
    └── test/java/example/ws/
        └── ReactiveSocketCoordinatorTest.java
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>webflux-ws-client-demo</artifactId>
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
~~~

### 10.3. DemoApplication.java

~~~java
package example.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.4. EchoWebSocketHandler.java

~~~java
package example.ws;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class EchoWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> outgoing = session.receive()
                .filter(message ->
                        message.getType() == WebSocketMessage.Type.TEXT)
                .map(message -> session.textMessage(
                        "echo: " + message.getPayloadAsText()));

        return session.send(outgoing);
    }
}
~~~

Server gửi lại một text message mới cho mỗi text message nhận được. Không tự subscribe; session.send nhận trực tiếp Flux từ receive.

### 10.5. SocketRouteConfiguration.java

~~~java
package example.ws;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;

@Configuration(proxyBeanMethods = false)
public class SocketRouteConfiguration {

    @Bean
    HandlerMapping echoSocketMapping(EchoWebSocketHandler handler) {
        SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
        mapping.setUrlMap(Map.of("/ws/echo", handler));
        mapping.setOrder(-1);
        return mapping;
    }
}
~~~

Spring Boot WebFlux mặc định cung cấp WebSocketHandlerAdapter. Không cần thêm @EnableWebFlux chỉ để tạo URL này.

### 10.6. WsTarget.java

~~~java
package example.ws;

import java.net.URI;

public record WsTarget(String label, URI uri) {
}
~~~

### 10.7. WsReply.java

~~~java
package example.ws;

public record WsReply(String label, String payload) {
}
~~~

### 10.8. ReactiveSocketCoordinator.java

~~~java
package example.ws;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.function.Function;

import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.client.WebSocketClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

public final class ReactiveSocketCoordinator {

    private final WebSocketClient client;

    public ReactiveSocketCoordinator(WebSocketClient client) {
        this.client = client;
    }

    public Mono<String> echo(URI uri, String text) {
        return Mono.defer(() -> {
            Sinks.One<String> answer = Sinks.one();

            Mono<Void> lifecycle = client.execute(uri, session -> {
                Mono<Void> outbound = session.send(
                        Mono.just(session.textMessage(text)));

                Mono<Void> inbound = session.receive()
                        .filter(message ->
                                message.getType()
                                        == WebSocketMessage.Type.TEXT)
                        .next()
                        .switchIfEmpty(Mono.error(
                                new IllegalStateException(
                                        "Peer closed without text reply")))
                        .doOnNext(message ->
                                answer.tryEmitValue(
                                        message.getPayloadAsText()))
                        .then();

                return Mono.when(outbound, inbound)
                        .then(session.close());
            });

            return lifecycle
                    .then(answer.asMono())
                    .timeout(Duration.ofSeconds(5));
        });
    }

    public Flux<WsReply> gather(
            List<WsTarget> targets,
            String text,
            int maxSessions
    ) {
        return bounded(
                targets,
                target -> echo(target.uri(), text)
                        .map(reply -> new WsReply(
                                target.label(), reply)),
                maxSessions
        );
    }

    public Flux<WsReply> gatherOrdered(
            List<WsTarget> targets,
            String text,
            int maxSessions
    ) {
        if (maxSessions < 1) {
            return Flux.error(new IllegalArgumentException(
                    "maxSessions must be positive"));
        }

        return Flux.fromIterable(targets)
                .flatMapSequential(
                        target -> echo(target.uri(), text)
                                .map(reply -> new WsReply(
                                        target.label(), reply)),
                        maxSessions,
                        1
                );
    }

    static <T, R> Flux<R> bounded(
            Iterable<T> items,
            Function<T, Mono<R>> operation,
            int maxSessions
    ) {
        if (maxSessions < 1) {
            return Flux.error(new IllegalArgumentException(
                    "maxSessions must be positive"));
        }

        return Flux.fromIterable(items)
                .flatMap(operation, maxSessions);
    }
}
~~~

**Giải thích cơ chế Sinks.One:**

execute() chỉ trả Mono<Void> của session lifecycle. Nhưng nghiệp vụ cần text reply. Sinks.One<String> cho phép handler phát một giá trị sang caller:

1. Mono.defer tạo sink mới theo mỗi subscription, tránh trộn reply của các lần gọi.
2. Handler bắt đầu send và receive bằng Mono.when.
3. receive().next() lấy text message đầu tiên.
4. doOnNext đọc payload thành String và emit vào sink.
5. session.close() kết thúc phiên sau khi outbound và inbound hoàn tất.
6. lifecycle.then(answer.asMono()) trả kết quả khi session đã đóng.
7. timeout hủy exchange nếu không nhận reply đúng hạn.
8. Nếu peer đóng trước khi gửi text, switchIfEmpty chuyển thành lỗi.

Một Sinks.One phù hợp với **một** reply. Với nhiều command đang chờ trên cùng socket, dùng correlationId và registry có giới hạn thay vì một sink chung.

### 10.9. ReactiveSocketCoordinatorTest.java

~~~java
package example.ws;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveSocketCoordinatorTest {

    @LocalServerPort
    int port;

    private ReactiveSocketCoordinator coordinator;

    @BeforeEach
    void setUp() {
        coordinator = new ReactiveSocketCoordinator(
                new ReactorNettyWebSocketClient());
    }

    private URI endpoint() {
        return URI.create(
                "ws://127.0.0.1:" + port + "/ws/echo");
    }

    @Test
    void sendsAndReceivesOneTextMessage() {
        StepVerifier.create(coordinator.echo(endpoint(), "hello"))
                .expectNext("echo: hello")
                .verifyComplete();
    }

    @Test
    void coordinatesThreeConnections() {
        List<WsTarget> targets = List.of(
                new WsTarget("alpha", endpoint()),
                new WsTarget("beta", endpoint()),
                new WsTarget("gamma", endpoint())
        );

        StepVerifier.create(
                        coordinator.gather(targets, "ping", 2)
                                .collectList())
                .assertNext(replies -> {
                    assertThat(replies).hasSize(3);
                    assertThat(replies)
                            .extracting(WsReply::label)
                            .containsExactlyInAnyOrder(
                                    "alpha", "beta", "gamma");
                    assertThat(replies).allSatisfy(reply ->
                            assertThat(reply.payload())
                                    .isEqualTo("echo: ping"));
                })
                .verifyComplete();
    }

    @Test
    void preservesTargetOrderWhenRequested() {
        List<WsTarget> targets = List.of(
                new WsTarget("one", endpoint()),
                new WsTarget("two", endpoint()),
                new WsTarget("three", endpoint())
        );

        StepVerifier.create(
                        coordinator.gatherOrdered(targets, "ok", 2))
                .assertNext(reply -> assertThat(reply.label())
                        .isEqualTo("one"))
                .assertNext(reply -> assertThat(reply.label())
                        .isEqualTo("two"))
                .assertNext(reply -> assertThat(reply.label())
                        .isEqualTo("three"))
                .verifyComplete();
    }

    @Test
    void boundedOperatorLimitsActiveInnerPublishers() {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();

        List<Integer> ids = IntStream.range(0, 8)
                .boxed()
                .toList();

        StepVerifier.create(
                        ReactiveSocketCoordinator.bounded(
                                ids,
                                id -> Mono.delay(
                                                Duration.ofMillis(60))
                                        .doOnSubscribe(subscription -> {
                                            int current =
                                                    active.incrementAndGet();
                                            maximum.accumulateAndGet(
                                                    current, Math::max);
                                        })
                                        .doOnTerminate(
                                                active::decrementAndGet)
                                        .map(ignored -> id),
                                2))
                .expectNextCount(8)
                .verifyComplete();

        assertThat(maximum.get()).isBetween(1, 2);
    }

    @Test
    void rejectsNonPositiveConcurrency() {
        StepVerifier.create(
                        coordinator.gather(List.of(), "ping", 0))
                .expectError(IllegalArgumentException.class)
                .verify();
    }
}
~~~

Test HTTP server nội bộ được khởi động trên port ngẫu nhiên; client Reactor Netty tạo các WebSocket connections thật. Test bounded dùng Mono.delay để đo số inner Publisher đồng thời, không dựa vào thời gian mạng. Nó kiểm tra operator mà gather đang dùng, không thay thế load test đo toàn bộ TCP connections hoặc quota global.

### 10.10. Chạy project

Chạy tests tại thư mục chứa pom.xml:

~~~bash
mvn test
~~~

Chạy server:

~~~bash
mvn spring-boot:run
~~~

Nếu đã cài websocat, kiểm tra thủ công:

~~~bash
websocat ws://localhost:8080/ws/echo
~~~

Gõ:

~~~text
hello
~~~

Nhận:

~~~text
echo: hello
~~~

Có thể thử bằng JavaScript console của browser:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");
socket.addEventListener("open", () => socket.send("ping"));
socket.addEventListener("message", (event) => {
    console.log(event.data);  // echo: ping
    socket.close();
});
~~~

Đoạn browser là client JavaScript riêng; phần ReactorNettyWebSocketClient và integration tests của project mới minh họa client Java reactive.

## 11. Custom handshake, frame limit và bảo mật

### 11.1. TLS và credential

Dùng wss:// ở production. Xác minh TLS certificate và hostname; không tắt verification vì convenience. Java WebSocketClient cho phép thêm HttpHeaders trong handshake, nhưng phải dùng token từ credential manager an toàn.

Không đưa access token dài hạn trong URI query string vì URI có thể lộ trong access log, tracing hoặc exception.

### 11.2. Origin và authorization

Server WebSocket phải kiểm tra authentication và quyền sử dụng từng resource sau handshake. Origin có ích khi hạn chế browser cross-site connections; tuy nhiên non-browser Java client có thể tự tạo Origin header, nên không coi Origin là credential.

### 11.3. Chống SSRF

Nếu API của bạn cho user nhập arbitrary URI rồi backend mở WebSocket tới URI đó, có nguy cơ SSRF. Dùng allowlist scheme, host, port và path; kiểm soát DNS rebinding, loopback, private networks và metadata service theo chính sách.

### 11.4. Giới hạn frame và message

Reactor Netty WebSocket client có thể tùy chỉnh thông qua WebsocketClientSpec:

~~~java
ReactorNettyWebSocketClient client =
        new ReactorNettyWebSocketClient(
                HttpClient.create(),
                () -> WebsocketClientSpec.builder()
                        .maxFramePayloadLength(64 * 1024));
~~~

Cần imports từ reactor.netty.http.client.HttpClient và WebsocketClientSpec. Giới hạn frame không nhất thiết là tổng kích thước message ứng dụng vì message có thể gồm nhiều frame. Phải giới hạn cả payload đã decode, tốc độ nhận, số pending command và outbound queue.

## 12. Backpressure, pooled buffers và một outbound writer

WebSocket stream được mô hình hóa bằng Flux/Mono, nhưng backpressure không tự làm mọi hệ thống bên ngoài ngừng gửi dữ liệu. Nếu upstream push nhanh hơn client xử lý, cần bounded buffer và chính sách overload:

- Với trạng thái dashboard chỉ cần giá trị mới nhất: drop/coalesce event cũ có chủ đích.
- Với command/audit quan trọng: durable queue, flow control hoặc từ chối tải.
- Với client chậm: giới hạn outbound queue, disconnect hoặc giảm tần suất update theo contract.
- Với nhiều producer: hợp nhất message vào một Publisher rồi gọi session.send một lần.

Các WebSocketMessage có DataBuffer bên dưới; trên Netty có thể là pooled direct memory. Nếu decode ngay trong callback thành String thường không cần giữ buffer. Nếu lưu message để dùng ngoài lifecycle callback, cần retain/release đúng contract, kể cả error và cancellation.

## 13. Monitoring và graceful shutdown

Các metric hữu ích:

- Active sessions theo upstream/tenant, tránh label cardinality cao.
- Handshake time, handshake failures, TLS errors.
- Session duration và close status.
- Reconnect attempts, backoff, retry exhaustion.
- Messages sent/received, message size, payload validation failures.
- Pending command count, timeout count và replay gaps.
- Outbound buffer depth, dropped/coalesced events.
- CPU, heap, direct memory, file descriptors và network traffic.

Reactor Netty có nhóm WebSocket client metrics như reactor.netty.websocket.client.handshake.time, connection.duration, data.sent/received và errors khi metrics được bật.

Khi shutdown: ngừng tạo connection mới, ngừng tạo outbound command, cho pending work một thời gian hoàn tất có giới hạn, đóng session có chủ đích, hủy subscription/timer còn lại và dừng reconnect loop. Nếu nhiều instance cùng restart, thêm jitter để tránh reconnection storm.

## 14. Các lỗi thường gặp

| Sai lầm | Hậu quả | Sửa |
| --- | --- | --- |
| Coi WebSocketClient như WebClient GET | Hiểu sai lifecycle và payload | Dùng execute với WebSocketHandler |
| Mong execute trả Mono<String> | execute chỉ báo completion | Xây result Mono theo message contract |
| Dùng Mono.zip trên Mono<Void> | Không có onNext để combine | Dùng Mono.when cho completion |
| Subscribe riêng trong handler | Handler kết thúc trước công việc thật | Compose inbound/outbound trong returned Mono |
| Subscribe cùng cold execute hai lần | Tạo hai session độc lập | Quản lý ownership của một session |
| Gọi session.send từ nhiều luồng không điều phối | Cạnh tranh outbound và thứ tự | Một outbound publisher có giới hạn |
| flatMap không giới hạn | Tốn connection, buffer, upstream quota | maxConcurrency và global bulkhead |
| Nghĩ maxConcurrency là global | Nhiều caller vẫn tạo quá nhiều sessions | Limiter chia sẻ giữa subscriptions |
| Dùng flatMap khi phải giữ thứ tự | Reply đến đảo thứ tự | flatMapSequential |
| Dùng concatMap khi cần song song | Throughput thấp | flatMap nếu các nguồn độc lập |
| Đặt onErrorResume sau batch | Một nguồn lỗi có thể cancel tất cả | Phục hồi bên trong mapper |
| retryWhen cho graceful close | Không tự reconnect khi onComplete | Chính sách reconnect riêng |
| Retry command không có ACK/idempotency | Có thể tạo duplicate side effects | Correlation ID, ACK, dedupe |
| Timeout cho toàn long-lived session | Đóng session đang hoạt động bình thường | Tách handshake, idle, reply timeout |
| Không xử lý pooled buffer | Use-after-release hoặc leak | Copy payload hoặc retain/release |
| Token trong URI | Rò credential vào log | Handshake headers/credential management |
| Không giới hạn queue/payload | Slow client gây tràn memory | Bounded queue và overload policy |
| Không cleanup khi cancel/shutdown | Rò session/permit/timer | Cleanup trong lifecycle |
| Mở WebSocket tùy ý từ user URI | SSRF | Allowlist và kiểm soát target |

## 15. Checklist production

- [ ] Chọn một hay nhiều connection theo use case, không theo sự tiện của API.
- [ ] Mỗi session có một owner và điều kiện complete/error/cancel/close rõ ràng.
- [ ] Không gọi subscribe() lồng nhau trong reactive handler.
- [ ] Nếu cần reply cho caller, có correlation/result publisher đúng contract.
- [ ] Max concurrency per batch và global quota được phân biệt.
- [ ] Có timeout cho handshake, reply, idle và shutdown.
- [ ] Có reconnect backoff/jitter và stop condition.
- [ ] Nếu cần chắc chắn command được xử lý, có ACK, ID và idempotency.
- [ ] Outbound queue/pending request/message size có giới hạn.
- [ ] Dùng wss:// và kiểm tra TLS, token, authorization.
- [ ] URI được kiểm soát để tránh SSRF.
- [ ] Có metrics active sessions, handshake, close, queue và error.
- [ ] Test nhiều connections, lỗi một target, cancellation và server close.
- [ ] Có graceful shutdown cleanup session, timer và pending resources.

## 16. Ghi nhớ

- WebSocketClient dùng để **mở và xử lý session**; ReactorNettyWebSocketClient là một implementation.
- execute(URI[,HttpHeaders], WebSocketHandler) trả Mono<Void> theo vòng đời session.
- session.receive() là Flux inbound; session.send(Publisher) là outbound Mono<Void>.
- Muốn kết hợp completion của nhiều session Mono<Void>, dùng Mono.when; muốn combine kết quả nghiệp vụ có giá trị, dùng Mono.zip trên Mono kết quả.
- Dùng flatMap(maxConcurrency) cho các session độc lập hữu hạn; flatMapSequential giữ thứ tự; concatMap chạy tuần tự.
- Giới hạn trong một subscription không thay thế quota connection toàn ứng dụng.
- retryWhen chỉ retry khi error, không tự reconnect sau graceful close.
- WebSocket không tự bảo đảm ACK, delivery bền vững hoặc exactly-once.
- Mọi session cần quản lý backpressure, buffer, timeout, security và cleanup.

**Tài liệu chính thức:**
- [Spring Framework 6.2 — WebFlux WebSocket, Client và WebSocketHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-websocket.html)
- [Spring Framework 6.2 — WebSocketClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/web/reactive/socket/client/WebSocketClient.html)
- [Spring Framework 6.2 — Reactive WebSocketSession Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0-RC1/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html)
- [Spring Framework 6.2 — Reactive WebSocketMessage Javadoc](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/web/reactive/socket/WebSocketMessage.html)
- [Project Reactor — Flux and Mono API](https://projectreactor.io/docs/core/release/reference/)
- [Reactor Netty — HTTP Client and WebSocket Metrics](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Spring Boot 3.5.16 Release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
- [RFC 6455 — WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)

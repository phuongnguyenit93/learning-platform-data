# WebSocketHandler, WebSocketSession và HandshakeWebSocketService trong Spring WebFlux

Spring WebFlux cung cấp API WebSocket reactive để xử lý kết nối hai chiều lâu dài. Thay vì tạo một HTTP request rồi nhận một response hoàn chỉnh, client và server giữ một kết nối mở và trao đổi nhiều message theo cả hai hướng. Ứng dụng Spring xử lý mỗi kết nối bằng một WebSocketHandler; WebSocketSession đại diện cho phiên đang hoạt động; còn HandshakeWebSocketService phụ trách kiểm tra HTTP handshake và nâng cấp kết nối sang WebSocket.

Ba thành phần có trách nhiệm riêng:

- WebSocketHandler chứa logic nghiệp vụ của một phiên: nhận message, xử lý và gửi message.
- WebSocketSession cung cấp metadata của phiên, luồng message đi vào, luồng message đi ra và thao tác đóng kết nối.
- HandshakeWebSocketService kiểm tra request bắt tay và dùng RequestUpgradeStrategy phù hợp với server đang chạy để thực hiện upgrade.

Bài học thuộc nhóm **WebSocket**, tập trung vào vòng đời kết nối, cách ánh xạ handler vào URL, cách kết hợp receive/send thành một reactive flow, vai trò của handshake service, bảo mật, backpressure, close status và kiểm thử kết nối thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích khác biệt giữa HTTP request-response và WebSocket connection.
- Mô tả HTTP Upgrade handshake và thời điểm kết nối chuyển sang WebSocket.
- Viết một WebSocketHandler trả Mono<Void>.
- Đọc message từ WebSocketSession.receive().
- Gửi message bằng WebSocketSession.send().
- Lấy session ID, URI, headers, principal, attributes và subprotocol.
- Phân biệt message text, binary, ping và pong.
- Kết hợp inbound và outbound publisher mà không tự subscribe.
- Hiểu vai trò của SimpleUrlHandlerMapping và WebSocketHandlerAdapter.
- Giải thích HandshakeWebSocketService và RequestUpgradeStrategy.
- Tùy chỉnh WebSocketService qua WebFluxConfigurer.
- Xử lý close status, lỗi, cancellation và backpressure.
- Bảo vệ handshake bằng authentication, authorization và kiểm tra Origin.
- Viết ứng dụng echo WebSocket với Java 17+ và Spring Boot.
- Kiểm thử handshake và trao đổi message bằng WebSocketClient.

## 2. WebSocket khác HTTP request-response như thế nào?

HTTP request-response thường có chu trình:

~~~text
Client ---- HTTP request ----> Server
Client <--- HTTP response ---- Server
Kết thúc request
~~~

WebSocket bắt đầu bằng một HTTP handshake. Khi handshake thành công, kết nối được nâng cấp và hai bên có thể gửi nhiều message trên cùng kết nối:

~~~text
Client ---- HTTP Upgrade handshake ----> Server
Client <--- HTTP 101 Switching Protocols - Server

Client <========== WebSocket ===========> Server
Client -------- message A --------------> Server
Client <------- message B --------------- Server
Client -------- message C --------------> Server
                 ...
        Một bên đóng hoặc mất kết nối
~~~

Điểm khác biệt quan trọng:

- Kết nối được giữ mở qua nhiều message.
- Client và server đều có thể chủ động gửi message.
- Server không cần đợi một HTTP request mới để gửi dữ liệu tiếp theo.
- Một phiên có thể tồn tại lâu, vì vậy cần quản lý tài nguyên, timeout, heartbeat và disconnect.
- Sau khi upgrade thành công, dữ liệu được trao đổi theo WebSocket framing, không còn là các HTTP response độc lập.

WebSocket phù hợp với chat, bảng điều khiển realtime, trạng thái trực tiếp, cộng tác nhiều người dùng, game và các ứng dụng cần trao đổi hai chiều liên tục. Với dữ liệu chỉ đi từ server tới client, Server-Sent Events có thể đơn giản hơn; với request-response thông thường, HTTP vẫn phù hợp hơn.

## 3. HTTP handshake và quá trình upgrade

Thông thường, client mở một HTTP GET request với các header dành cho WebSocket. Ví dụ minh họa:

~~~http
GET /ws/echo HTTP/1.1
Host: api.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: https://app.example.com
~~~

Server kiểm tra request và nếu chấp nhận, trả response upgrade thành công. Với handshake HTTP/1.1:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: ...
~~~

Sau đó, hai bên trao đổi WebSocket frame trên kết nối đã được nâng cấp.

Handshake có thể mang thêm thông tin:

- Origin: trang web khởi tạo kết nối.
- Cookie hoặc thông tin xác thực: tùy mô hình authentication.
- Sec-WebSocket-Protocol: các subprotocol mà client muốn thương lượng.
- Sec-WebSocket-Extensions: các extension được đề xuất, chẳng hạn compression.
- Các header phục vụ tracing hoặc correlation nếu hệ thống cho phép.

Không phải mọi request GET đều là WebSocket handshake. Server cần kiểm tra các điều kiện upgrade và handshake key/version hợp lệ. Spring WebFlux giao phần kiểm tra và upgrade cho WebSocketService cùng RequestUpgradeStrategy.

## 4. Ba thành phần cốt lõi và trách nhiệm của chúng

| Thành phần | Trách nhiệm | Thời điểm hoạt động |
| --- | --- | --- |
| WebSocketHandler | Xử lý message và logic của một phiên | Sau khi handshake thành công |
| WebSocketSession | Đại diện cho kết nối, metadata và hai luồng message | Trong toàn bộ vòng đời phiên |
| HandshakeWebSocketService | Kiểm tra handshake và thực hiện upgrade qua server strategy | Trước khi handler bắt đầu |

Một request tới endpoint WebSocket đi qua các thành phần chính:

~~~text
HTTP request có Upgrade: websocket
             |
             v
       HandlerMapping
             |
             v
    WebSocketHandlerAdapter
             |
             v
      WebSocketService
             |
             v
 HandshakeWebSocketService
             |
             v
    RequestUpgradeStrategy
             |
             v
      WebSocketSession
             |
             v
       WebSocketHandler
             |
             v
     receive() / send()
~~~

WebSocketHandlerAdapter là cầu nối để DispatcherHandler của WebFlux gọi được WebSocketHandler. Adapter ủy quyền cho WebSocketService; mặc định service đó là HandshakeWebSocketService. Service thực hiện các kiểm tra handshake cơ bản rồi dùng strategy tương ứng với HTTP server, chẳng hạn Reactor Netty, Tomcat hoặc Jetty.

## 5. WebSocketHandler là gì?

WebSocketHandler là interface đại diện cho logic xử lý một phiên WebSocket. Phương thức chính:

~~~java
Mono<Void> handle(WebSocketSession session);
~~~

Phương thức nhận WebSocketSession và trả Mono<Void>. Publisher này cho Spring biết khi nào logic xử lý phiên đã hoàn tất.

Một handler thường thực hiện các việc sau:

1. Đọc message từ session.receive().
2. Chuyển đổi hoặc kiểm tra payload.
3. Gọi service nghiệp vụ bất đồng bộ nếu cần.
4. Tạo message phản hồi bằng session.textMessage() hoặc session.binaryMessage().
5. Gửi message qua session.send().
6. Kết thúc khi kết nối đóng, lỗi xảy ra hoặc ứng dụng chủ động đóng session.

Ví dụ handler chỉ nhận message và ghi log:

~~~java
@Component
public class LoggingWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.receive()
            .doOnNext(message ->
                System.out.println(message.getPayloadAsText()))
            .then();
    }
}
~~~

Ở ví dụ này, handler không gửi message. then() chuyển Flux nhận dữ liệu thành Mono<Void> hoàn tất khi inbound stream kết thúc.

Không gọi subscribe() bên trong handle(). Spring quản lý subscription dựa trên Mono<Void> mà handler trả về. Nếu tự subscribe rồi trả Mono.empty(), vòng đời xử lý có thể kết thúc trước khi công việc thực sự hoàn tất, lỗi không được truyền đúng và cancellation khó quản lý.

## 6. WebSocketSession cung cấp những gì?

WebSocketSession đại diện cho một kết nối WebSocket đang hoạt động. Các API quan trọng:

| API | Ý nghĩa |
| --- | --- |
| getId() | ID của phiên |
| getHandshakeInfo() | Thông tin HTTP handshake đã tạo phiên |
| getAttributes() | Các attribute gắn với phiên |
| receive() | Flux message đi từ client vào server |
| send(publisher) | Gửi publisher message từ server tới client |
| textMessage(text) | Tạo message dạng text |
| binaryMessage(factory) | Tạo message dạng binary |
| pingMessage(factory) | Tạo ping frame |
| pongMessage(factory) | Tạo pong frame |
| close() | Đóng phiên với close status bình thường |
| close(status) | Đóng phiên với close status chỉ định |
| closeStatus() | Đọc close status khi phiên kết thúc |
| isOpen() | Kiểm tra trạng thái mở của kết nối |

Một số thông tin handshake thường cần dùng:

- URI endpoint.
- HTTP headers.
- Cookies.
- Principal đã xác thực.
- Subprotocol đã thương lượng.
- Remote address ở phía server.
- Attributes được truyền từ handshake.

Ví dụ đọc metadata:

~~~java
public Mono<Void> handle(WebSocketSession session) {
    String sessionId = session.getId();
    URI endpoint = session.getHandshakeInfo().getUri();
    String subProtocol = session.getHandshakeInfo().getSubProtocol();

    log.info(
        "WebSocket connected: sessionId={}, endpoint={}, protocol={}",
        sessionId, endpoint, subProtocol);

    return session.receive()
        .doOnNext(message ->
            log.debug("Received message for session {}", sessionId))
        .then();
}
~~~

Đoạn này cần khai báo logger và import URI. Không ghi payload nhạy cảm vào log chỉ để debug kết nối.

## 7. HandshakeInfo và thông tin xác thực

getHandshakeInfo() trả về HandshakeInfo, một đối tượng chứa thông tin của HTTP handshake đã tạo phiên.

Các method thường dùng:

| API | Kiểu dữ liệu | Ý nghĩa |
| --- | --- | --- |
| getUri() | URI | URL của WebSocket endpoint |
| getHeaders() | HttpHeaders | HTTP headers trong handshake |
| getCookies() | MultiValueMap | Cookie của request handshake phía server |
| getPrincipal() | Mono<Principal> | Principal đã xác thực, nếu có |
| getSubProtocol() | String | Subprotocol được thương lượng |
| getRemoteAddress() | InetSocketAddress | Địa chỉ remote phía server |
| getAttributes() | Map<String, Object> | Attributes được đưa vào phiên |
| getLogPrefix() | String | Prefix hỗ trợ liên kết log |

getPrincipal() trả Mono<Principal>, vì thông tin principal được biểu diễn theo reactive API. Nếu request chưa được xác thực, publisher có thể hoàn tất mà không phát Principal.

Ví dụ:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    return session.getHandshakeInfo().getPrincipal()
        .doOnNext(principal ->
            log.info(
                "Authenticated WebSocket user: {}",
                principal.getName()))
        .then(session.receive().then());
}
~~~

Đây chỉ là quan sát principal đã có. Việc xác thực và phân quyền phải được thực hiện ở HTTP security chain trước khi cho phép upgrade. Không xem một userId gửi trong query string hoặc message đầu tiên là danh tính đã xác thực.

## 8. Hai luồng receive và send

WebSocketSession có hai luồng reactive độc lập:

- receive(): Flux<WebSocketMessage> cho dữ liệu inbound.
- send(Publisher<WebSocketMessage>): Mono<Void> cho dữ liệu outbound.

receive() hoàn tất khi kết nối inbound đóng bình thường hoặc phát lỗi nếu transport gặp sự cố. send() hoàn tất khi publisher message nguồn hoàn tất và việc ghi message đã xong.

Ví dụ echo:

~~~java
@Component
public class EchoWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> replies = session.receive()
            .map(WebSocketMessage::getPayloadAsText)
            .map(text -> session.textMessage("echo: " + text));

        return session.send(replies);
    }
}
~~~

Khi client gửi text message hello, server gửi lại echo: hello. Khi client đóng kết nối, receive() hoàn tất; publisher replies cũng hoàn tất và send() kết thúc.

Đây là một pipeline gắn đầu ra với đầu vào, nên không cần subscribe thủ công cho receive và send.

### Xử lý nghiệp vụ bất đồng bộ

Có thể dùng concatMap để gọi service cho từng message và giữ thứ tự xử lý:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> replies = session.receive()
        .map(WebSocketMessage::getPayloadAsText)
        .concatMap(text ->
            messageService.process(text)
                .map(session::textMessage));

    return session.send(replies);
}
~~~

concatMap chờ xử lý message hiện tại trước khi chuyển sang message kế tiếp. Nếu dùng flatMap với concurrency lớn, nhiều message có thể được xử lý đồng thời và kết quả có thể trở về không theo thứ tự đầu vào.

Chọn operator theo hợp đồng nghiệp vụ: thứ tự có quan trọng không, có cho phép xử lý song song không và giới hạn concurrency là bao nhiêu.

## 9. Kết hợp inbound và outbound độc lập

Không phải lúc nào dữ liệu gửi đi cũng được tạo từ message nhận vào. Một server có thể vừa nhận lệnh từ client, vừa phát dữ liệu realtime từ một publisher khác.

Ví dụ cấu trúc:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Mono<Void> input = session.receive()
        .doOnNext(message ->
            processCommand(message.getPayloadAsText()))
        .then();

    Flux<String> updates = updateService.streamUpdates();

    Mono<Void> output = session.send(
        updates.map(session::textMessage));

    return input.and(output);
}
~~~

input xử lý luồng message từ client. output phát các update từ service. and() kết hợp hai Mono<Void>; flow tổng thể kết thúc khi một nhánh hoàn tất, nhánh còn lại được hủy theo semantics của operator.

Điều này hữu ích khi output là publisher dài hạn hoặc vô hạn và cần dừng ngay khi client disconnect. Nếu cần chờ cả hai nhánh hoàn tất, hãy chọn operator có semantics chờ cả hai và xem xét rõ publisher nào có thể vô hạn.

Không gọi subscribe() cho input hoặc output riêng lẻ. Hãy trả một publisher tổng hợp để Spring quản lý cancellation và lỗi.

## 10. WebSocketMessage: text, binary, ping và pong

WebSocketMessage biểu diễn một message/frame được Spring cung cấp cho handler.

Các loại thường gặp:

- TEXT: nội dung văn bản, thường là JSON hoặc chuỗi.
- BINARY: payload byte, thường dùng cho ảnh, âm thanh hoặc định dạng nhị phân.
- PING: frame kiểm tra kết nối.
- PONG: frame phản hồi ping.

Đọc text:

~~~java
session.receive()
    .map(WebSocketMessage::getPayloadAsText)
    .doOnNext(text -> log.debug("Text received: {}", text))
    .then();
~~~

Gửi text:

~~~java
session.send(
    Flux.just(
        session.textMessage("connected"),
        session.textMessage("ready")));
~~~

Gửi binary:

~~~java
session.send(
    Mono.just(
        session.binaryMessage(factory ->
            factory.wrap(new byte[] {1, 2, 3, 4}))));
~~~

Binary payload sử dụng DataBufferFactory của session. Trong ứng dụng thực tế, cần quản lý kích thước payload và vòng đời DataBuffer đúng cách.

Ping/pong có thể được dùng ở tầng giao thức hoặc transport để phát hiện kết nối không còn hoạt động. Hành vi tự động trả lời ping phụ thuộc server implementation và cấu hình; không giả định mọi application handler phải tự gửi pong cho mọi ping frame.

## 11. Backpressure và xử lý message an toàn

WebSocket là kết nối lâu dài, nhưng không có nghĩa server có thể nhận vô hạn message hoặc gửi vô hạn dữ liệu mà không kiểm soát.

Các nguyên tắc quan trọng:

- Dùng reactive publisher để tận dụng backpressure ở các thành phần hỗ trợ.
- Giới hạn số message được xử lý đồng thời.
- Giới hạn kích thước message và payload.
- Không buffer toàn bộ lịch sử message trong bộ nhớ.
- Tránh block event-loop bằng I/O đồng bộ hoặc công việc CPU nặng.
- Nếu phải gọi API blocking, chuyển sang scheduler phù hợp và giới hạn thread.
- Dùng concatMap nếu cần giữ thứ tự.
- Dùng onBackpressureBuffer có giới hạn nếu thực sự cần buffer; xác định hành vi khi buffer đầy.
- Không tự tạo hàng đợi vô hạn cho mỗi session.

Với Netty, DataBuffer có thể được pooled và reference-counted. Nếu giữ một payload hoặc DataBuffer qua một xử lý bất đồng bộ dài hơn lifecycle mặc định, cần retain đúng lúc và release khi hoàn tất. Cách an toàn nhất cho xử lý text đơn giản là đọc payload thành String ngay trong pipeline rồi tiếp tục xử lý String đó.

### Ví dụ giới hạn hàng đợi nghiệp vụ

~~~java
Flux<WebSocketMessage> replies = session.receive()
    .map(WebSocketMessage::getPayloadAsText)
    .onBackpressureBuffer(
        100,
        dropped -> log.warn("Inbound queue is full"),
        BufferOverflowStrategy.ERROR)
    .concatMap(text ->
        messageService.process(text)
            .map(session::textMessage));
~~~

Đây là minh họa cho giới hạn buffer phía ứng dụng. Khi buffer đầy, policy ERROR kết thúc pipeline. Hãy chọn hành vi phù hợp với giao thức: từ chối message, đóng session hoặc báo lỗi ở tầng ứng dụng. Không bỏ message âm thầm nếu client cần xác nhận xử lý.

## 12. Đóng session và CloseStatus

WebSocketSession có thể đóng kết nối bằng:

~~~java
return session.close();
~~~

close() sử dụng close status bình thường. Có thể truyền close status cụ thể:

~~~java
return session.close(CloseStatus.POLICY_VIOLATION);
~~~

Một số close code tiêu chuẩn:

| Code | Ý nghĩa |
| --- | --- |
| 1000 | Normal Closure |
| 1001 | Going Away |
| 1002 | Protocol Error |
| 1003 | Unsupported Data |
| 1007 | Invalid Payload Data |
| 1008 | Policy Violation |
| 1009 | Message Too Big |
| 1011 | Internal Server Error |

Các code 1005 và 1006 là giá trị dành riêng để mô tả tình huống đóng; không gửi chúng như close frame từ ứng dụng.

closeStatus() trả Mono<CloseStatus>. Publisher có thể hoàn tất rỗng nếu kết nối kết thúc mà không nhận được close status. Dùng nó để quan sát cách phiên kết thúc:

~~~java
session.closeStatus()
    .doOnNext(status ->
        log.info("Session closed with code {}", status.getCode()))
    .then();
~~~

Trong handler thực tế, thường đặt logging ở cuối lifecycle bằng doFinally hoặc kết hợp với closeStatus. Không polling isOpen() để chờ kết nối đóng; reactive receive/send sẽ phát complete, error hoặc cancellation khi phiên kết thúc.

## 13. Xử lý lỗi và cancellation

Các tình huống có thể kết thúc một WebSocket session:

- Client gửi close frame.
- Server chủ động gọi close().
- Network bị ngắt.
- Message không hợp lệ hoặc vượt giới hạn.
- Publisher xử lý nghiệp vụ phát lỗi.
- Server shutdown.
- Client hủy kết nối.

Có thể quan sát lifecycle:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    return session.receive()
        .doOnSubscribe(subscription ->
            log.info("Session started: {}", session.getId()))
        .doOnError(error ->
            log.warn("WebSocket failed: {}", session.getId(), error))
        .doFinally(signal ->
            log.info(
                "Session finished: {}, signal={}",
                session.getId(), signal))
        .then();
}
~~~

doFinally quan sát COMPLETE, ERROR hoặc CANCEL. Đây là nơi phù hợp để ghi metrics và giải phóng tài nguyên gắn với session.

Không chuyển mọi lỗi thành một message text tùy ý. Nếu giao thức ứng dụng có error message schema, hãy phát error message theo schema đó trước khi đóng. Nếu lỗi là protocol violation hoặc payload không hợp lệ, dùng close code thích hợp. Khi socket đã đóng, không thể gửi thêm message.

Nếu có registry lưu session theo user hoặc room, hãy xóa session khi lifecycle kết thúc. Không chỉ xóa ở nhánh onError; client disconnect bình thường cũng cần cleanup.

## 14. HandshakeWebSocketService là gì?

HandshakeWebSocketService triển khai WebSocketService. Nó xử lý HTTP handshake bằng cách:

1. Nhận ServerWebExchange và WebSocketHandler đã được mapping.
2. Kiểm tra request có phải WebSocket handshake hợp lệ hay không.
3. Lấy thông tin cần thiết từ HTTP request, ví dụ URI, headers, cookies, principal và attributes.
4. Chọn hoặc sử dụng RequestUpgradeStrategy phù hợp với server.
5. Thực hiện upgrade từ HTTP sang WebSocket.
6. Tạo WebSocketSession và chuyển quyền xử lý cho WebSocketHandler.

HandshakeWebSocketService có constructor mặc định tự phát hiện RequestUpgradeStrategy phù hợp từ classpath. Có thể truyền một strategy tường minh nếu cần cấu hình đặc thù cho server.

Service này không xử lý từng message trong phiên. Sau khi handshake và upgrade thành công, WebSocketHandler cùng WebSocketSession đảm nhận phần giao tiếp hai chiều.

### WebSocketService và RequestUpgradeStrategy

WebSocketService là abstraction cho quá trình handshake. HandshakeWebSocketService là implementation mặc định của Spring WebFlux.

RequestUpgradeStrategy là abstraction cho phần nâng cấp kết nối phụ thuộc server engine. Các server có cách tích hợp WebSocket khác nhau; Spring cung cấp strategy cho các server được hỗ trợ như Reactor Netty, Tomcat và Jetty.

Nếu cần cấu hình idle timeout, frame size hoặc option riêng của server, hãy xem strategy tương ứng với server đang dùng. Không áp dụng một class strategy của Tomcat cho ứng dụng chạy Reactor Netty.

## 15. WebSocketHandlerAdapter và mapping URL

WebSocketHandlerAdapter giúp DispatcherHandler gọi WebSocketHandler. Adapter nhận WebSocketService, mặc định là HandshakeWebSocketService, rồi ủy quyền việc xử lý handshake.

Trong Spring WebFlux Java configuration, adapter được đăng ký sẵn. Với ứng dụng Spring Boot dùng WebFlux auto-configuration, thông thường không cần tự khai báo bean này.

Cần map URL tới handler bằng HandlerMapping. Cách đơn giản là SimpleUrlHandlerMapping:

~~~java
@Configuration
public class WebSocketMappingConfiguration {

    @Bean
    public HandlerMapping webSocketHandlerMapping(
            EchoWebSocketHandler handler) {

        Map<String, WebSocketHandler> handlers =
            Map.of("/ws/echo", handler);

        SimpleUrlHandlerMapping mapping =
            new SimpleUrlHandlerMapping();

        mapping.setUrlMap(handlers);
        mapping.setOrder(-1);

        return mapping;
    }
}
~~~

Order -1 đặt mapping này trước annotated controller mapping theo ví dụ thông dụng của Spring. Khi request đến /ws/echo, WebFlux tìm thấy WebSocketHandler và gọi WebSocketHandlerAdapter để thực hiện handshake.

Nếu không dùng WebFlux Java configuration, ứng dụng cần khai báo WebSocketHandlerAdapter thủ công. Khi dùng Spring Boot, hãy giữ auto-configuration và chỉ bổ sung WebFluxConfigurer cần thiết; không thêm @EnableWebFlux nếu không có chủ đích thay thế cấu hình mặc định của Boot.

## 16. Tùy chỉnh HandshakeWebSocketService qua WebFluxConfigurer

Trong một số trường hợp, cần tùy chỉnh WebSocketService được WebSocketHandlerAdapter sử dụng. WebFluxConfigurer cung cấp getWebSocketService() để cung cấp service riêng.

Một tính năng của HandshakeWebSocketService là sessionAttributePredicate. Predicate này chọn các attribute từ WebSession để đưa vào attributes của WebSocketSession.

Ví dụ:

~~~java
@Configuration
public class WebSocketConfiguration implements WebFluxConfigurer {

    @Override
    public WebSocketService getWebSocketService() {
        HandshakeWebSocketService service =
            new HandshakeWebSocketService();

        service.setSessionAttributePredicate(
            name -> "userId".equals(name));

        return service;
    }
}
~~~

Trong ví dụ, chỉ attribute có tên userId được chọn để chuyển từ WebSession sang WebSocketSession.

Điều này không tự xác thực user và không tạo userId. Attribute phải được thiết lập ở server sau khi authentication hoặc bước xử lý đáng tin cậy. Không sao chép toàn bộ WebSession attributes nếu không cần thiết; hãy chọn chính xác dữ liệu mà handler cần.

Nếu muốn tùy chỉnh RequestUpgradeStrategy, có thể tạo HandshakeWebSocketService với strategy tương ứng. Strategy phải khớp với HTTP server đang chạy. Khi dùng WebFluxConfigurer, WebFlux configuration sử dụng service do getWebSocketService() trả về để tạo adapter.

## 17. Subprotocol và thương lượng giao thức ứng dụng

WebSocket là transport hai chiều. Ứng dụng có thể định nghĩa subprotocol để thống nhất schema và semantics của message.

Ví dụ:

- chat.v1: message chat phiên bản 1.
- notifications.v1: thông báo realtime.
- telemetry.v2: dữ liệu đo lường phiên bản 2.

WebSocketHandler có method getSubProtocols() trả danh sách subprotocol mà handler hỗ trợ. Client có thể gửi Sec-WebSocket-Protocol trong handshake để đề nghị một hoặc nhiều protocol. Server chọn protocol tương thích trong quá trình handshake.

Ví dụ handler hỗ trợ một subprotocol:

~~~java
@Component
public class ChatWebSocketHandler implements WebSocketHandler {

    @Override
    public List<String> getSubProtocols() {
        return List.of("chat.v1");
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        log.info(
            "Negotiated protocol: {}",
            session.getHandshakeInfo().getSubProtocol());

        return session.receive()
            .map(WebSocketMessage::getPayloadAsText)
            .map(text -> session.textMessage("chat: " + text))
            .as(session::send);
    }
}
~~~

Client cần offer chat.v1. Sau handshake, session.getHandshakeInfo().getSubProtocol() cho biết protocol đã được thương lượng; nếu không có protocol được chọn, giá trị có thể null.

Subprotocol là một phần của hợp đồng giao tiếp, không phải chỉ là tên trang trí. Hai bên phải thống nhất message schema, version, error format, authentication behavior và close semantics.

## 18. Bảo mật WebSocket endpoint

Handshake là một HTTP request trước khi kết nối được nâng cấp. Vì vậy có thể áp dụng authentication và authorization ở HTTP security layer trước khi WebSocketHandler chạy.

Các nguyên tắc quan trọng:

- Yêu cầu authentication trước khi cho phép upgrade nếu endpoint là riêng tư.
- Kiểm tra quyền user được kết nối vào room, tenant hoặc channel nào.
- Kiểm tra Origin theo allowlist phù hợp với browser clients.
- Không xem Origin là thông tin xác thực; nó chỉ giúp xác định website khởi tạo request.
- Với cookie/session authentication, đánh giá nguy cơ cross-site WebSocket hijacking và CSRF theo kiến trúc ứng dụng.
- Dùng WSS trong môi trường production để mã hóa dữ liệu trên đường truyền.
- Giới hạn kích thước message, tốc độ gửi và số session đồng thời.
- Validate mọi payload; không tin dữ liệu client gửi.
- Ghi log session ID, principal ID phù hợp, close code và correlation ID; tránh log token hoặc payload nhạy cảm.

CORS và WebSocket không giống nhau. WebSocket handshake có Origin header, nhưng không hoạt động như một chuỗi fetch request với preflight CORS thông thường. Cấu hình CORS cho REST endpoint không tự động chứng minh WebSocket endpoint an toàn. Hãy kiểm tra Origin và authorization theo cơ chế WebSocket của ứng dụng.

HandshakeWebSocketService chịu trách nhiệm handshake và upgrade, không thay thế security policy của ứng dụng. Nếu dùng Spring Security WebFlux, hãy cấu hình SecurityWebFilterChain để xác thực và phân quyền đường dẫn WebSocket trước khi request được nâng cấp.

## 19. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ này tạo một WebSocket echo endpoint tại /ws/echo. Client gửi text message, server trả lại nội dung với prefix echo. Cấu hình dùng SimpleUrlHandlerMapping và WebFluxConfigurer để tùy chỉnh HandshakeWebSocketService.

### Cấu trúc project

~~~text
webflux-websocket-demo/
├── pom.xml
└── src
    ├── main/java/com/example/websocket
    │   ├── WebSocketDemoApplication.java
    │   ├── WebSocketConfiguration.java
    │   └── EchoWebSocketHandler.java
    └── test/java/com/example/websocket
        └── WebSocketEchoIntegrationTest.java
~~~

### pom.xml

~~~xml
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

  <groupId>com.example</groupId>
  <artifactId>webflux-websocket-demo</artifactId>
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

Spring Boot 3.3.5 quản lý phiên bản Spring Framework 6.1 và Reactor tương thích. Ví dụ dùng Java 17.

### WebSocketDemoApplication.java

~~~java
package com.example.websocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSocketDemoApplication.class, args);
    }
}
~~~

### EchoWebSocketHandler.java

~~~java
package com.example.websocket;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class EchoWebSocketHandler implements WebSocketHandler {

    private static final Logger log =
        LoggerFactory.getLogger(EchoWebSocketHandler.class);

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        log.info("WebSocket connected: {}", session.getId());

        Flux<WebSocketMessage> replies = session.receive()
            .map(WebSocketMessage::getPayloadAsText)
            .map(text -> session.textMessage("echo: " + text));

        return session.send(replies)
            .doFinally(signal ->
                log.info(
                    "WebSocket finished: {}, signal={}",
                    session.getId(), signal));
    }
}
~~~

Handler chỉ xử lý text message. Pipeline nhận text, tạo text message phản hồi và đưa publisher cho session.send(). doFinally ghi nhận khi session hoàn tất, lỗi hoặc bị cancellation.

### WebSocketConfiguration.java

~~~java
package com.example.websocket;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.server.WebSocketService;
import org.springframework.web.reactive.socket.server.support.HandshakeWebSocketService;

@Configuration
public class WebSocketConfiguration implements WebFluxConfigurer {

    @Bean
    public HandlerMapping webSocketHandlerMapping(
            EchoWebSocketHandler handler) {

        Map<String, WebSocketHandler> handlers =
            Map.of("/ws/echo", handler);

        SimpleUrlHandlerMapping mapping =
            new SimpleUrlHandlerMapping();

        mapping.setUrlMap(handlers);
        mapping.setOrder(-1);

        return mapping;
    }

    @Override
    public WebSocketService getWebSocketService() {
        HandshakeWebSocketService service =
            new HandshakeWebSocketService();

        service.setSessionAttributePredicate(
            name -> "userId".equals(name));

        return service;
    }
}
~~~

Mapping đăng ký đường dẫn /ws/echo. getWebSocketService() cung cấp HandshakeWebSocketService tùy chỉnh; service chỉ chuyển attribute userId từ WebSession nếu attribute đó tồn tại. Trong ứng dụng production, userId phải được thiết lập từ server-side authentication/session logic.

Spring Boot WebFlux auto-configuration cung cấp WebSocketHandlerAdapter. Không cần tạo adapter thứ hai trong cấu hình này. Nếu ứng dụng không dùng WebFlux Java configuration, cần khai báo adapter theo cấu hình tương ứng.

### WebSocketEchoIntegrationTest.java

~~~java
package com.example.websocket;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.URI;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.LocalServerPort;
import org.springframework.boot.test.context.SpringBootTest;

import org.springframework.web.reactive.socket.WebSocketClient;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebSocketEchoIntegrationTest {

    @LocalServerPort
    private int port;

    @Test
    void echoesTextMessageOverRealWebSocketConnection() {
        WebSocketClient client =
            new ReactorNettyWebSocketClient();

        AtomicReference<String> received =
            new AtomicReference<>();

        URI uri = URI.create(
            "ws://127.0.0.1:" + port + "/ws/echo");

        Mono<Void> conversation = client.execute(uri, session ->
            session.send(
                    Mono.just(session.textMessage("hello")))
                .thenMany(session.receive().take(1))
                .doOnNext(message ->
                    received.set(message.getPayloadAsText()))
                .then()
        );

        StepVerifier.create(conversation)
            .expectComplete()
            .verify(Duration.ofSeconds(5));

        assertEquals("echo: hello", received.get());
    }
}
~~~

Test khởi động embedded server trên port ngẫu nhiên, dùng ReactorNettyWebSocketClient mở kết nối thật, gửi hello và nhận một message. Kết quả mong đợi là echo: hello.

Chạy test tại thư mục chứa pom.xml:

~~~bash
mvn -q test
~~~

Nếu test pass, Maven kết thúc với exit code 0. Đây là integration test cho handshake và message exchange, không chỉ là unit test của hàm chuyển đổi String.

### Chạy ứng dụng và kết nối thử

Khởi động:

~~~bash
mvn spring-boot:run
~~~

Có thể dùng JavaScript trong browser console:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");

socket.addEventListener("open", () => {
  console.log("connected");
  socket.send("hello");
});

socket.addEventListener("message", event => {
  console.log("server:", event.data);
});

socket.addEventListener("close", event => {
  console.log("closed:", event.code, event.reason);
});

socket.addEventListener("error", error => {
  console.error("websocket error", error);
});
~~~

Kết quả message mong đợi:

~~~text
connected
server: echo: hello
~~~

Browser console là client thử nghiệm. Trong production, URL thường dùng wss:// sau khi triển khai HTTPS.

## 20. Kiểm thử và chẩn đoán WebSocket

Một WebSocket endpoint nên được kiểm thử ở nhiều tầng:

- Handler logic: chuyển đổi message, kiểm tra payload, xử lý lỗi.
- Handshake: URL đúng, upgrade được chấp nhận, subprotocol được thương lượng.
- Session: nhận và gửi message, close status, disconnect.
- Security: unauthenticated request bị từ chối, user không có quyền không thể kết nối.
- Capacity: nhiều session đồng thời, message lớn, tốc độ gửi cao.
- Lifecycle: server shutdown, client disconnect và cleanup.

Các dấu hiệu chẩn đoán:

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| HTTP 404 trước upgrade | URL mapping và HandlerMapping order |
| HTTP 400 khi handshake | Upgrade headers, key/version và request format |
| HTTP 401/403 | Authentication, authorization hoặc Origin policy |
| Handshake thành công nhưng không có message | Handler mapping, receive/send pipeline và client event |
| Message bị mất | Publisher bị cancel, handler hoàn tất sớm hoặc lỗi xử lý |
| Message đảo thứ tự | flatMap concurrency hoặc nhiều producer gửi đồng thời |
| Connection bị đóng sớm | Mono<Void> hoàn tất, exception hoặc timeout |
| Bộ nhớ tăng theo số session | Buffering không giới hạn, session registry hoặc cleanup thiếu |
| Chỉ production bị disconnect | Proxy idle timeout, load balancer, heartbeat hoặc TLS |

Khi dùng reverse proxy, cần bật hỗ trợ WebSocket upgrade và cấu hình timeout phù hợp. Một proxy có thể đóng connection idle dù ứng dụng vẫn giữ session. Với kết nối lâu dài, cân nhắc heartbeat hoặc ping/pong và theo dõi idle timeout trên từng tầng.

## 21. Lỗi thường gặp và cách khắc phục

1. **Nghĩ WebSocketHandler là controller thông thường.** Handler xử lý một phiên kéo dài, trả Mono<Void> phản ánh lifecycle của phiên.
2. **Không map handler vào URL.** Tạo WebSocketHandler bean là chưa đủ; cần HandlerMapping để route handshake.
3. **Tự khai báo WebSocketHandlerAdapter trùng lặp.** WebFlux configuration đã đăng ký adapter; chỉ khai báo thủ công khi không dùng cấu hình đó.
4. **Nhầm HandshakeWebSocketService với message handler.** Service thực hiện handshake và upgrade; WebSocketHandler xử lý message sau upgrade.
5. **Gọi subscribe() trong handle().** Việc này tách công việc khỏi lifecycle mà Spring quản lý; hãy trả publisher đã compose.
6. **Chỉ gọi receive() nhưng không trả publisher.** Handler có thể kết thúc trước khi stream được xử lý; trả Mono<Void> từ pipeline.
7. **Gọi send() nhiều lần đồng thời cho cùng session.** Dễ gây cạnh tranh ghi; gom outbound message vào một publisher và gọi send một lần.
8. **Không xử lý client disconnect.** receive() có thể complete hoặc error; dùng doFinally để cleanup session state.
9. **Dùng flatMap khi cần thứ tự message.** Kết quả có thể về không theo thứ tự; dùng concatMap khi cần tuần tự.
10. **Dùng buffer không giới hạn.** Tải tăng có thể làm cạn bộ nhớ; giới hạn queue và xác định hành vi khi overflow.
11. **Block event loop.** I/O đồng bộ hoặc xử lý CPU nặng làm chậm nhiều session; dùng reactive client hoặc scheduler phù hợp.
12. **Không giới hạn payload.** Message quá lớn có thể làm tăng bộ nhớ và chi phí decode; cấu hình giới hạn theo server strategy và kiểm tra kích thước ở tầng ứng dụng.
13. **Giữ DataBuffer mà không retain/release đúng cách.** Có thể gây lỗi use-after-release hoặc memory leak; quản lý vòng đời buffer theo hướng dẫn WebFlux.
14. **Tin userId trong query string.** Client có thể giả mạo giá trị; dùng Principal hoặc attribute do server xác thực thiết lập.
15. **Không kiểm tra Origin.** Cookie-authenticated WebSocket có thể chịu rủi ro cross-site hijacking; dùng allowlist và security policy.
16. **Dùng CORS thay cho authentication.** CORS không xác thực user và không thay thế authorization.
17. **Không xử lý close code.** Client khó phân biệt đóng bình thường, policy violation và server error; dùng close status có ý nghĩa.
18. **Gửi close code dành riêng.** Không gửi các code 1005 hoặc 1006 trong close frame.
19. **Không có heartbeat cho connection idle.** Proxy/load balancer có thể đóng session; cấu hình ping/pong hoặc heartbeat theo yêu cầu.
20. **Không test handshake thật.** Unit test handler không phát hiện lỗi mapping hoặc upgrade; thêm integration test bằng WebSocketClient.

## 22. Checklist thiết kế WebSocket endpoint

Trước khi phát hành endpoint, hãy xác định:

- **URL mapping:** đường dẫn nào ánh xạ tới handler?
- **Handshake:** server strategy có phù hợp HTTP server đang dùng?
- **Adapter:** WebSocketHandlerAdapter đã được WebFlux config cung cấp chưa?
- **Session lifecycle:** handler hoàn tất khi nào?
- **Inbound:** text, binary hay cả hai?
- **Outbound:** một publisher hay nhiều nguồn cần merge?
- **Ordering:** message có phải giữ đúng thứ tự không?
- **Backpressure:** queue và concurrency có giới hạn không?
- **Payload size:** message lớn nhất được phép là bao nhiêu?
- **Error policy:** lỗi nghiệp vụ được gửi bằng message hay close frame?
- **Close status:** close code và reason có rõ ràng không?
- **Authentication:** handshake được xác thực trước upgrade?
- **Authorization:** user có quyền vào room/channel/resource không?
- **Origin:** browser origin có được kiểm tra không?
- **Subprotocol:** client/server có thống nhất version và message schema?
- **Observability:** log, metrics, session count, duration và close reason có được ghi nhận?
- **Proxy:** load balancer và reverse proxy có hỗ trợ upgrade, idle timeout và heartbeat?
- **Tests:** handshake, echo, disconnect, error và security đã được kiểm thử?

## 23. Bài tập tự kiểm tra

**Bài 1.** WebSocketHandler.handle() nhận đối tượng nào và trả kiểu gì?  
**Đáp án:** Nhận WebSocketSession và trả Mono<Void> để biểu diễn thời gian xử lý phiên.

**Bài 2.** receive() trả về kiểu publisher nào?  
**Đáp án:** Flux<WebSocketMessage> chứa message inbound.

**Bài 3.** send() nhận gì và trả gì?  
**Đáp án:** Nhận Publisher<WebSocketMessage>, trả Mono<Void> hoàn tất khi ghi xong nguồn message.

**Bài 4.** WebSocketSession.getHandshakeInfo() cung cấp gì?  
**Đáp án:** URI, headers, cookies, principal, subprotocol, remote address và attributes của handshake.

**Bài 5.** Ai thực hiện HTTP handshake và upgrade?  
**Đáp án:** WebSocketService, mặc định là HandshakeWebSocketService, sử dụng RequestUpgradeStrategy phù hợp server.

**Bài 6.** WebSocketHandlerAdapter có nhiệm vụ gì?  
**Đáp án:** Cho phép DispatcherHandler gọi WebSocketHandler và ủy quyền request cho WebSocketService.

**Bài 7.** SimpleUrlHandlerMapping dùng để làm gì?  
**Đáp án:** Ánh xạ URL path như /ws/echo tới WebSocketHandler.

**Bài 8.** Vì sao không nên gọi subscribe() trong handle()?  
**Đáp án:** Vì sẽ tách subscription khỏi lifecycle do Spring quản lý và làm khó việc truyền lỗi/cancellation.

**Bài 9.** Khi nào nên dùng concatMap thay flatMap?  
**Đáp án:** Khi cần xử lý tuần tự và giữ thứ tự message đầu vào.

**Bài 10.** HandshakeWebSocketService.setSessionAttributePredicate() làm gì?  
**Đáp án:** Chọn các attribute từ WebSession để đưa vào WebSocketSession attributes.

**Bài 11.** getPrincipal() trả kiểu gì?  
**Đáp án:** Mono<Principal>, vì principal được cung cấp theo reactive API.

**Bài 12.** Khi client disconnect, handler cần làm gì?  
**Đáp án:** Để receive/send phát terminal signal, kết thúc flow và cleanup tài nguyên trong doFinally hoặc lifecycle phù hợp.

**Bài 13.** Subprotocol được đọc ở đâu sau handshake?  
**Đáp án:** HandshakeInfo.getSubProtocol().

**Bài 14.** Vì sao cần kiểm tra Origin với WebSocket dùng cookie authentication?  
**Đáp án:** Để giảm nguy cơ website khác mở kết nối bằng cookie của người dùng và thao tác trên session đã đăng nhập.

**Bài 15.** HTTP status 101 có ý nghĩa gì trong handshake HTTP/1.1?  
**Đáp án:** Switching Protocols; server chấp nhận upgrade sang WebSocket.

## 24. Ghi nhớ

WebSocketHandler chứa logic xử lý phiên và trả Mono<Void>. WebSocketSession đại diện cho kết nối, cung cấp metadata, receive() cho inbound message, send() cho outbound message và close() để kết thúc phiên. Handler phải compose các publisher thành một flow duy nhất; không tự subscribe hoặc block.

WebSocketHandlerAdapter nối WebSocketHandler với DispatcherHandler. HandlerMapping ánh xạ URL tới handler. Adapter mặc định dùng HandshakeWebSocketService để kiểm tra HTTP handshake và gọi RequestUpgradeStrategy của server thực hiện upgrade. WebFluxConfigurer.getWebSocketService() cho phép cung cấp service tùy chỉnh, ví dụ chọn các attribute từ WebSession đưa vào WebSocketSession.

Sau upgrade, dữ liệu được trao đổi bằng WebSocket message chứ không còn là HTTP response độc lập. Hãy kiểm soát thứ tự message, backpressure, payload size, cancellation, close code và tài nguyên của từng session. Bảo vệ handshake bằng authentication, authorization và Origin policy; dùng subprotocol khi cần version hóa hợp đồng message. Kiểm thử cả handshake thật và message exchange để xác nhận endpoint hoạt động xuyên suốt.

### Tài liệu tham khảo

- Spring Framework, [WebSockets in Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html).
- Spring Framework, [WebFlux Configuration – WebSocketService](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).
- Spring Framework Javadoc, [WebSocketHandler](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/WebSocketHandler.html).
- Spring Framework Javadoc, [WebSocketSession](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html).
- Spring Framework Javadoc, [HandshakeInfo](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/HandshakeInfo.html).
- Spring Framework Javadoc, [HandshakeWebSocketService](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/server/support/HandshakeWebSocketService.html).
- Spring Framework Javadoc, [WebSocketHandlerAdapter](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/server/support/WebSocketHandlerAdapter.html).
- Spring Framework, [Reactive Web Application Architecture](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- IETF, [The WebSocket Protocol – RFC 6455](https://www.rfc-editor.org/rfc/rfc6455).

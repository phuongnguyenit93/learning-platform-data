# WebSocketHandler reactive và vòng đời luồng nhận/gửi trong Spring WebFlux

## 1. Mục tiêu: một kết nối, hai luồng bất đồng bộ

Trong HTTP REST thông thường, client gửi một request và nhận một response. Với **WebSocket**, client thực hiện một **HTTP handshake** trước; sau khi server chấp nhận nâng cấp giao thức, client và server có thể **gửi thông điệp theo cả hai hướng** trong một kết nối lâu dài. Điều này rất phù hợp với chat, collaboration, live dashboards, games và event notification hai chiều.

Spring WebFlux có API WebSocket ở package `org.springframework.web.reactive.socket`. Hai kiểu quan trọng nhất là:

- `WebSocketHandler`: xử lý **toàn bộ phiên WebSocket** bằng method `Mono<Void> handle(WebSocketSession session)`.
- `WebSocketSession`: cung cấp **luồng nhận** `Flux<WebSocketMessage> receive()` và **luồng gửi** `Mono<Void> send(Publisher<WebSocketMessage>)`; ngoài ra có handshake info, session ID, tạo text/binary/ping/pong messages và API đóng kết nối.

Đây không phải controller `@GetMapping`, cũng không phải WebFlux.fn `HandlerFunction<ServerResponse>`. WebSocket thường chỉ route theo một endpoint URL **khi handshake**, sau đó ứng dụng phải tự xác định **giao thức thông điệp bên trong phiên**.

Bài sử dụng **Spring Boot 3.3.5, Spring Framework 6.1.x, Java 17 và Reactor**. Phần ví dụ chạy trên `spring-boot-starter-webflux` với Reactor Netty, không cần Servlet MVC hoặc thư viện STOMP.

### Kết quả học tập

Sau bài, bạn có thể:

1. Trình bày WebSocket handshake HTTP 101 và luồng text/binary frames sau upgrade.
2. Phân biệt `WebSocketHandler`, `WebSocketSession`, `WebSocketMessage`, `WebSocketClient`, `HandlerMapping` và `WebSocketHandlerAdapter`.
3. Hiểu `receive()` như inbound Flux và `send(...)` như outbound Mono completion.
4. Ghép inbound và outbound thành **một Publisher** thể hiện chính xác lifecycle của session.
5. Tự xây handler echo và handler phát các thông báo có giới hạn.
6. Hiểu close, error, cancel, half-open connection, ping/pong, graceful shutdown và session scope.
7. Xử lý input/output có giới hạn, không block event loop, không subscribe thủ công.
8. Phân biệt luồng WebSocket với SSE, NDJSON và HTTP response streaming.
9. Hiểu authentication lúc handshake, authorization từng message, Origin/subprotocol và WebSocket security.
10. Viết bài kiểm thử integration qua WebSocket client, xác nhận messages và closure.
11. Biết khi nào cần broker/pub-sub/Sinks để multiplex nhiều producers vào một đường send an toàn.
12. Nhận ra pooled buffer ownership, memory/backpressure, per-connection resource leaks và các rủi ro production.

## 2. Từ HTTP handshake đến WebSocket frames

Một kết nối WebSocket bắt đầu bằng HTTP GET có Upgrade headers (ví dụ HTTP/1.1):

```http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Origin: http://localhost:3000
```

`Sec-WebSocket-Key` bên trên là ví dụ tài liệu; client WebSocket tạo key ngẫu nhiên theo giao thức. Server chấp nhận handshake trả:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

`Sec-WebSocket-Accept` được tính theo RFC 6455 từ key; không nên hardcode trong ứng dụng. Sau status **101**, HTTP request/response theo kiểu REST thông thường đã được nâng cấp thành phiên trao đổi WebSocket frames.

Luồng logic:

```text
Browser / WebSocketClient
       |
       | HTTP GET + Upgrade headers
       v
Reactive HTTP server (ví dụ Reactor Netty)
       |
       v
WebFlux DispatcherHandler
       |
       +--> SimpleUrlHandlerMapping: /ws/echo -> WebSocketHandler
       |
       +--> WebSocketHandlerAdapter
              |
              +--> WebSocketService / HandshakeWebSocketService
                       |
                       +--> kiểm tra handshake
                       +--> chọn server-specific upgrade strategy
                       +--> trả 101 khi hợp lệ
                       +--> tạo WebSocketSession
                                  |
                                  v
                             handle(session)
                                  |
                  +---------------+---------------+
                  |                               |
            receive() Flux                  send(Publisher)
                  |                               |
             inbound frames                 outbound frames
                  |                               |
                  +---------- Mono<Void> ----------+
                                completion/error/cancel
```

**Không nhầm:** Một lần handshake có thể tạo **rất nhiều** tin nhắn hai chiều, không có một HTTP status cho mỗi tin nhắn. Nếu ứng dụng cần trả "lỗi nghiệp vụ" khi client gửi sai JSON, nó phải quy định message error schema hoặc close code — không thể sau upgrade trả một HTTP 400 mới cho từng message.

### Khi nào dùng WebSocket?

- Chat, collaborative editing, multiplayer/game state và command/reply với latency thấp.
- Client vừa cần gửi lệnh, vừa cần nhận events mà không tạo HTTP request mới mỗi lần.
- Tương tác hai chiều hoặc push liên tục với nhiều phản hồi.

Nếu chỉ server đẩy cập nhật tới browser, **SSE** có thể đơn giản hơn. Nếu chỉ export danh sách dữ liệu một chiều, **NDJSON** cũng có thể phù hợp. Cần chọn theo **communication pattern**, không chỉ vì muốn dùng Reactor.

## 3. WebSocketHandler: hợp đồng cốt lõi

Interface ở `org.springframework.web.reactive.socket.WebSocketHandler` có method:

```java
public interface WebSocketHandler {
    Mono<Void> handle(WebSocketSession session);

    // API thực có thêm getSubProtocols() mặc định.
}
```

Đây là đoạn **minh họa chữ ký API**, không phải file cần định nghĩa lại.

`handle(session)` được gọi sau khi handshake thành công. Nó phải **return một `Mono<Void>` phản ánh toàn bộ việc xử lý session**. Publisher đó complete khi phiên được xử lý xong hoặc đóng theo policy; phát error signal khi xảy ra lỗi chưa được xử lý; có thể bị cancel khi kết nối bị hủy/disconnect.

### Mono<Void> không phải "không làm gì"

- Không chứa một DTO Java để serialize thành HTTP JSON response.
- Có các signals **onSubscribe, onComplete, onError, cancel**.
- Server/framework subscribe vào returned Mono; application **không được** tự subscribe một Mono detached rồi lập tức return `Mono.empty()`.
- Khi handler trả `Mono.empty()` ngay, session có thể kết thúc sớm mà bạn chưa đọc/gửi gì.
- Khi handler trả một Mono không bao giờ complete và không xử lý cancellation, connection/resource có thể tồn tại rất lâu không cần thiết.

### Không dùng Servlet WebSocket interface trong WebFlux

| Stack | Kiểu thường dùng | Đầu vào và vòng đời |
| --- | --- | --- |
| WebFlux reactive | `org.springframework.web.reactive.socket.WebSocketHandler` | `handle(WebSocketSession): Mono<Void>` |
| Spring Servlet WebSocket | `org.springframework.web.socket.WebSocketHandler` | Callback như `afterConnectionEstablished`, `handleMessage` |
| Spring messaging/STOMP | `@MessageMapping`, broker abstractions | Giao thức messaging mức cao |
| Browser client | `WebSocket` JavaScript | `onopen`, `onmessage`, `onclose`, `onerror` |

Các interface WebSocketHandler của Servlet và WebFlux **có tên giống nhau nhưng package và execution model khác nhau**. Đừng import `org.springframework.web.socket.WebSocketHandler` vào example reactive này.

## 4. WebSocketSession là ngữ cảnh của một kết nối

API tiêu biểu từ `org.springframework.web.reactive.socket.WebSocketSession`:

| API | Ý nghĩa |
| --- | --- |
| `getId()` | ID phiên do implementation cung cấp, hữu ích để correlation |
| `getHandshakeInfo()` | Metadata handshake (URI, headers, principal, v.v.) |
| `receive()` | `Flux<WebSocketMessage>` của thông điệp đi vào |
| `send(Publisher<WebSocketMessage>)` | Ghi outbound messages, trả `Mono<Void>` khi gửi hoàn tất |
| `textMessage(String)` | Tạo outbound text message |
| `binaryMessage(Function<DataBufferFactory,DataBuffer>)` | Tạo binary message |
| `pingMessage(...)` / `pongMessage(...)` | Tạo control messages nếu cần |
| `close(CloseStatus)` | Yêu cầu đóng phiên với close status |
| `closeStatus()` | `Mono<CloseStatus>` phản ánh close outcome |
| `isOpen()` | Trạng thái tại thời điểm kiểm tra, không nên dựa vào để đồng bộ lifecycle |
| `bufferFactory()` | Factory tạo DataBuffer cho outbound messages |

`WebSocketSession` **chỉ sống cho một kết nối**. Không cất object này vào field mutable của singleton handler rồi dùng chung giữa nhiều clients. Với multi-user notification, registry/cache session state phải có lifecycle cleanup, bounded queues và concurrency policy, không chỉ dùng `HashMap<String,Session>` vô hạn.

### HandshakeInfo không phải HTTP request thông thường

Handshake metadata có thể cung cấp `URI`, headers và principal. Sau khi upgrade, handler không có một HTTP request mới mỗi khi client gửi text. Muốn truyền metadata trên từng message, cần **định nghĩa message envelope riêng** hoặc subprotocol. Không dùng raw query parameter `?user=alice` làm bằng chứng authenticated identity.

## 5. Luồng nhận: Flux<WebSocketMessage> receive()

`session.receive()` trả `Flux<WebSocketMessage>`. Một message có loại TEXT, BINARY, PING hoặc PONG (việc expose/handling control frames tùy server implementation/protocol); payload nằm ở `DataBuffer`.

Ví dụ log chỉ **loại message**:

```java
Mono<Void> inbound = session.receive()
        .doOnNext(message ->
                logger.info("session {} type={}",
                        session.getId(), message.getType()))
        .then();
```

Đây là **snippet** (cần `session` và logger bean). `then()` biến stream nhận nhiều messages thành `Mono<Void>`, complete khi inbound complete. Không log raw payload nếu có credentials, PII hoặc secrets.

### Đọc text ngay trong operator synchronous

```java
Flux<String> textInput = session.receive()
        .filter(message ->
                message.getType() == WebSocketMessage.Type.TEXT)
        .map(WebSocketMessage::getPayloadAsText);
```

Đây là snippet có `session`. `getPayloadAsText()` chuyển bytes từ frame text sang String trong lúc message buffer còn hợp lệ. Nếu muốn xử lý bất đồng bộ **sau** khi giữ lại nguyên `WebSocketMessage`/pooled `DataBuffer`, phải lưu ý `retain`/`release` (mục 16). Ví dụ echo đầy đủ chọn **tách thành String sớm**, không giữ buffer qua async boundary.

### Flux nhận thường kết thúc khi kết nối đóng

Không nên coi mỗi `onComplete` là business "đã nhận đủ N messages" nếu protocol của client là live channel. Nó có thể xảy ra vì close bình thường. `onError` có thể báo network/decoder failure; `cancel` có thể đến khi application trả về/handler bị hủy. Nếu muốn dừng sau một command `stop`, hãy thiết kế close semantics, không dựa vào "client sẽ ngắt socket sau khi gửi" như một hợp đồng ngầm.

## 6. Luồng gửi: Mono<Void> send(Publisher<WebSocketMessage>)

`session.send(outboundPublisher)` nhận một publisher chứa các outbound WebSocketMessage. Khi nguồn hoàn tất và các messages được ghi, returned Mono hoàn tất.

```java
Flux<WebSocketMessage> greeting = Flux.just(
        session.textMessage("hello"),
        session.textMessage("welcome"));

Mono<Void> result = session.send(greeting);
return result;
```

Đây là **snippet** dùng trong `handle(session)`. Nếu handler chỉ cần gửi hai thông báo rồi kết thúc phiên, hoàn tất `send` cũng có thể là điểm kết thúc application handling; framework/runtime quản lý closure theo lifecycle.

### Không gọi send() nhiều lần độc lập

Phản ví dụ:

```java
// PHẢN VÍ DỤ: hai outbound writers cạnh tranh cùng một session.
session.send(streamA).subscribe();
session.send(streamB).subscribe();
return Mono.empty();
```

Điều này tạo subscriptions detached, không gắn với lifecycle/error/cancellation của handler. Hai writers có thể gây race hoặc hỏng thứ tự messages. Khi cần dữ liệu từ nhiều nguồn, **merge/multiplex về một Publisher<WebSocketMessage> rồi gọi session.send(...) một lần**, với giới hạn queue và ordering policy.

### Gửi text

```java
return session.send(
        Flux.just("first", "second")
                .map(session::textMessage));
```

Đây là snippet. `WebSocketSession.textMessage` tạo WebSocket text frame theo encoding chuẩn (UTF-8). Đừng tự thêm delimiter `\n` nếu protocol không quy định; **WebSocket đã có message boundaries**, khác với NDJSON trên HTTP stream.

## 7. Echo: ghép inbound và outbound bằng một flow

Một echo server nhận text và gửi lại:

```java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> outgoing = session.receive()
            .filter(message ->
                    message.getType() == WebSocketMessage.Type.TEXT)
            .map(WebSocketMessage::getPayloadAsText)
            .map(text -> "echo:" + text)
            .map(session::textMessage);

    return session.send(outgoing);
}
```

Đây là một **implementation snippet**; mã class runnable ở mục 14. Cấu trúc quan trọng:

```text
session.receive()
    -> WebSocketMessage
    -> String
    -> transform
    -> session.textMessage(...)
    -> session.send(outgoing)
    -> Mono<Void>
```

Không có `block()`/`subscribe()` thủ công. `session.send(outgoing)` subscribe vào outgoing; outgoing lại subscribe vào inbound. Khi client đóng, inbound complete/error; outgoing tương ứng dừng, send hoàn tất/hủy và framework dọn phiên.

### Vì sao đây là cách đơn giản, an toàn?

- Một inbound subscription.
- Một outbound writer.
- Mỗi text message được phản hồi một lần.
- Không giữ mutable per-session fields.
- Dùng reactive operators và tôn trọng cancellation.
- Không cần create `Sinks.Many`/shared queue khi chưa có broadcast.

### Echo không phải production chat

Echo không có auth, rooms, fan-out, durable messages, replay, unread counts, delivery acknowledgements hoặc multi-node coordination. Nếu chỉ copy echo handler rồi lưu mọi session trong một global map, bạn chưa giải quyết authorization, memory limits, cleanup hay horizontal scaling.

## 8. Khi inbound và outbound độc lập nhau

Một hệ thống thông báo có thể vừa **nhận commands** vừa **gửi events từ nguồn ngoài**. Hai streams không nhất thiết có quan hệ "một input → một output".

Ví dụ khái niệm:

```java
Mono<Void> inbound = session.receive()
        .filter(message ->
                message.getType() == WebSocketMessage.Type.TEXT)
        .map(WebSocketMessage::getPayloadAsText)
        .concatMap(commandService::handle)
        .then();

Flux<WebSocketMessage> outboundMessages =
        eventService.streamForUser(userId)
                .map(session::textMessage);

Mono<Void> outbound = session.send(outboundMessages);

return inbound.and(outbound);
```

Đây là **snippet phụ thuộc** các biến `session`, `commandService`, `eventService`, `userId` giả định. `inbound.and(outbound)` phối hợp completion hai phía theo Reactor, giống cách Spring docs minh họa. **Không đánh đồng điều này với mọi nhu cầu closure**: nếu outbound vô hạn nhưng inbound complete vì client ngắt, cần xác nhận composition chọn có cancel outbound đúng lúc; với một số application, `takeUntilOther(inbound)` hoặc một termination signal rõ hơn có thể phù hợp.

### Các chiến lược kết thúc khác nhau

1. **Echo dependent flow:** outbound phụ thuộc trực tiếp inbound, dừng khi inbound kết thúc; `return session.send(session.receive().map(...))`.
2. **Server finite push:** chỉ gửi N messages rồi dừng, `return session.send(Flux.take(N)...)`.
3. **Long-lived push:** outbound có thể vô hạn, cần gắn completion/cancel từ connection và business shutdown policy.
4. **Command 'stop':** nhận một command ứng dụng, phát acknowledgement, rồi close với status phù hợp; client/server thống nhất semantics.
5. **Server shutdown:** graceful close active sessions, đợi thời hạn nhất định, hủy remaining subscriptions.
6. **Fatal protocol error:** đóng với close code phù hợp, không cố gửi một HTTP 500 sau upgrade.

**Một WebSocket connection là full duplex**, nhưng làm sao *orchestrate* hai flows là quyết định của ứng dụng, không phải `send` tự đọc inbound thay bạn.

## 9. Reactive completion, error và cancellation

`Mono<Void>` từ `handle()` quyết định điểm kết thúc lifecycle. Bảng:

| Signal | Ý nghĩa | Hành động thiết kế |
| --- | --- | --- |
| `onComplete` | Luồng handling hoàn tất bình thường | Dọn state, counters, subscriptions |
| `onError` | Lỗi chưa được xử lý | Log an toàn; đóng phù hợp; không giả JSON HTTP response mới |
| `CANCEL` | Subscription bị hủy bởi disconnect/shutdown/logic khác | Cleanup upstream resources và timers |
| Close frame | WebSocket protocol báo đóng | Ghi nhận close code/reason khi có thể |
| Socket reset không close frame | Network failure bất thường | Không giả định luôn có clean close event |
| Timeout/idle expiry | Không có hoạt động hoặc policy hết hạn | Chọn ping/heartbeat và server/proxy idle settings |

Đừng chỉ viết:

```java
return session.receive()
        .doOnComplete(() -> metrics.connectedMinusOne())
        .then();
```

Nếu connection bị cancel hoặc error, `doOnComplete` có thể không chạy và active connection count bị leak. Dùng `doFinally` trên **một publisher sở hữu lifecycle**, đếm chính xác một lần và tránh double-decrement:

```java
return session.send(outgoing)
        .doOnSubscribe(sub -> active.increment())
        .doFinally(signal -> active.decrement());
```

Đây là **snippet** với `outgoing` và `active` do ứng dụng cấp. Nếu metrics increment chưa chạy hoặc cùng session tái subscribe, phải bảo vệ logic đếm; `doFinally` là nơi phù hợp để xử lý COMPLETE/ERROR/CANCEL, không nhất thiết là nơi đóng mọi resources một cách đồng bộ.

### Không dựa vào isOpen() để quyết định lifecycle

`session.isOpen()` chỉ là snapshot tại một thời điểm, có race với network close. Trong reactive code, hãy dựa vào completion/error/cancellation và `closeStatus()` khi thích hợp. Đừng loop `while(session.isOpen())` rồi `Thread.sleep` để poll WebSocket.

## 10. CloseStatus và quy tắc đóng

WebSocket RFC 6455 có **close frame** với status code và (tùy chọn) reason. Spring WebFlux cung cấp `CloseStatus` và API `session.close(...)`.

Ví dụ:

```java
return session.close(CloseStatus.NORMAL);
```

Đây là snippet bên trong handler. `CloseStatus.NORMAL` biểu thị đóng bình thường (1000). Một số code thường gặp:

| Code | Ý nghĩa tiêu chuẩn | Ghi nhớ |
| --- | --- | --- |
| 1000 | Normal Closure | Kết thúc phiên bình thường |
| 1001 | Going Away | Endpoint rời đi/server shutdown |
| 1002 | Protocol Error | Vi phạm giao thức WebSocket |
| 1003 | Unsupported Data | Loại dữ liệu không được hỗ trợ |
| 1008 | Policy Violation | Policy vi phạm, chẳng hạn authorization policy |
| 1009 | Message Too Big | Frame/message vượt giới hạn server |
| 1011 | Unexpected Condition | Server gặp lỗi ngoài dự kiến |
| 1006 | Abnormal Closure (reserved, không gửi trên wire) | Client nhận khi không có close frame hợp lệ |
| 1015 | TLS failure (reserved, không gửi trên wire) | Không gửi như close code của ứng dụng |

Đừng gửi 1006/1015 trong close frame. Các names/constants của `CloseStatus` hỗ trợ common cases, nhưng cần kiểm tra Javadoc version trước khi dùng constant cho từng code. Custom status không nên thay quy tắc RFC 6455.

### Đóng ở đâu cho hợp lý?

- Khi xử lý command rời room, có thể gửi acknowledgement cuối rồi `then(session.close(...))`.
- Khi input không hợp lệ nghiêm trọng hoặc payload quá lớn, có thể đóng với 1008/1009, tùy layer đã phát hiện lỗi.
- Khi server deploy/shutdown, gửi 1001 khi có thể rồi hủy sau timeout.
- Nếu client đã biến mất, không bảo đảm close frame được giao tận nơi.
- Reason có độ dài giới hạn UTF-8 và không được chứa secrets/stack trace/PII.

**WebSocket close code không giống HTTP status.** Sau HTTP 101, mã 1000/1008/1011 nằm trong WebSocket close frame; không phải một HTTP response `200/403/500` mới.

## 11. Backpressure trong WebSocket: cái gì được bảo đảm?

`session.receive()` là Flux, `session.send(Publisher)` nhận nguồn Reactive Streams. Điều này cho phép composition có demand/cancellation, nhưng không biến TCP/browser/WebSocket protocol thành một hàng đợi thông minh vô hạn.

- Server-side reactive writes có thể chậm theo I/O demand và network.
- Browser `WebSocket.send(...)` không có Reactive Streams `request(n)` API; gửi liên tục có thể tăng `bufferedAmount` phía client.
- Một message broker có thể đẩy nhanh hơn socket write; nếu queue không giới hạn, RAM tăng.
- `Sinks.Many` có thể báo `FAIL_OVERFLOW` khi giới hạn hàng đợi; phải xử lý thay vì bỏ qua.
- `Flux.onBackpressureBuffer()` không giới hạn có thể OOM.
- Một slow client không nên khiến toàn bộ cluster hoặc room lưu events vô hạn.
- `flatMap` có thể thay đổi thứ tự kết quả; dùng `concatMap` nếu thứ tự command/reply phải giữ nguyên.

### Một pipeline luôn có bounds

Đối với chat room:
- Mỗi kết nối có quota message/second và max payload bytes.
- Per-session outbound queue **bounded**.
- Policy khi đầy: drop old presence updates, coalesce status, disconnect slow client hoặc báo backpressure.
- Đừng drop durable business messages một cách im lặng.
- Với pub/sub, tách durable delivery/ACK/replay khỏi best-effort live notifications.
- Dùng transport-level ping/pong và idle eviction, không lưu session "ma" mãi.

**Reactive API không đồng nghĩa mọi downstream non-blocking**: nếu trong `map` gọi JDBC, filesystem hoặc HTTP client đồng bộ, event loop vẫn bị chặn.

## 12. Đừng block WebFlux event loop

Phản ví dụ:

```java
// PHẢN VÍ DỤ: blocking database call trên event-loop.
return session.send(session.receive()
        .map(message -> {
            String text = message.getPayloadAsText();
            return session.textMessage(jdbcService.lookup(text));
        }));
```

`jdbcService.lookup` là giả định và có thể block. Khi hàng nghìn kết nối cùng nhận messages, blocking call ở event loop gây latency toàn server.

Nếu phải dùng API blocking tạm thời:

```java
Flux<WebSocketMessage> outbound = session.receive()
        .filter(m -> m.getType() == WebSocketMessage.Type.TEXT)
        .map(WebSocketMessage::getPayloadAsText)
        .concatMap(text ->
                Mono.fromCallable(() -> jdbcService.lookup(text))
                    .subscribeOn(Schedulers.boundedElastic()))
        .map(session::textMessage);

return session.send(outbound);
```

Đây là snippet cần `jdbcService` và import `Schedulers`. Nó **chuyển blocking work sang bounded workers**, không biến JDBC thành non-blocking. Dùng timeout, giới hạn concurrency, DB pool phù hợp; ưu tiên driver/client reactive nếu có lợi ích thực tế. Với cancellation sau khi blocking task đã chạy, không bảo đảm side effect JDBC tự rollback.

## 13. DataBuffer ownership, binary messages và ping/pong

### 13.1. WebSocketMessage mang payload DataBuffer

`WebSocketMessage` có type và payload. Trên Reactor Netty, một số buffers được **pool và reference-counted**. Nếu chỉ đọc text ngay trong synchronous `map`, chuyển sớm thành String giúp tránh giữ buffer lâu.

Phản ví dụ:

```java
// NGUY HIỂM nếu message/buffer bị giải phóng trước callback.
return session.receive()
        .delayElements(Duration.ofSeconds(1))
        .map(WebSocketMessage::getPayloadAsText)
        .then();
```

Nếu dùng async boundary giữ message gốc, buffer có thể không còn hợp lệ tại thời điểm đọc. Khi thực sự cần giữ buffer, dùng `retain`/`release` đúng ownership theo hướng dẫn Spring, ưu tiên API abstractions hỗ trợ. Đừng tự retain rồi quên release — pooled direct memory có thể leak.

### 13.2. Binary frames khác text frames

`session.binaryMessage(factory -> factory.wrap(byteArray))` tạo binary WebSocketMessage. Với binary payload lớn, tránh gọi `byte[]` khổng lồ không có max size. Khi nhận binary:
- Xác định compression/frame fragmentation policy.
- Validate content length, magic bytes/schema/CRC nếu cần.
- Không hiểu binary data như UTF-8 text.
- Giới hạn max frame/message bytes tại server WebSocket upgrade strategy, proxy và application.

### 13.3. Ping/Pong và heartbeats

WebSocket chuẩn có control frames PING/PONG và CLOSE. Heartbeat có thể giúp:
- Phát hiện half-open sockets.
- Giữ kết nối qua một số intermediary idle timeouts.
- Đo round-trip latency nếu protocol/implementation cho phép.

Nhưng **không giả định mọi Ping frame xuất hiện trong `session.receive()` ở dạng message application**: server runtime có thể xử lý Ping/Pong ở tầng transport và tự pong. Kiểm tra Netty/Jetty/Tomcat strategy tương ứng. Nếu client browser không expose Ping/Pong API, có thể dùng **application-level heartbeat** JSON/text message với type `ping`/`pong` (nhưng đó là protocol riêng, không phải RFC control frame).

## 14. Project Maven runnable: Echo + Ticks WebSocket endpoints

Project minh họa ba đặc điểm:

1. `/ws/echo`: client gửi hai text messages, server echo lại; inbound điều khiển outbound.
2. `/ws/ticks`: server phát đúng ba thông báo định kỳ, không cần message đầu vào.
3. `/api/status`: REST JSON thông thường, giúp thấy WebSocket và REST có thể cùng tồn tại trong một WebFlux application.

Hai WebSocket handlers được đăng ký qua `SimpleUrlHandlerMapping`. Trong Boot WebFlux bình thường, framework đã cấu hình `WebSocketHandlerAdapter`, không cần tự tạo adapter bean thứ hai.

### 14.1. Cấu trúc project

```text
webflux-websocket-demo/
├── pom.xml
└── src/
    ├── main/java/example/ws/
    │   ├── WebSocketDemoApplication.java
    │   ├── EchoSocketHandler.java
    │   ├── TickSocketHandler.java
    │   ├── WebSocketRouting.java
    │   └── StatusController.java
    └── test/java/example/ws/
        └── WebSocketIntegrationTest.java
```

### 14.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
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

Không cần `spring-boot-starter-websocket` dành cho Servlet MVC stack trong ví dụ WebFlux này, và không thêm `spring-boot-starter-web` để tránh Boot ưu tiên MVC application type khi cả hai có mặt.

### 14.3. Main class

**`src/main/java/example/ws/WebSocketDemoApplication.java`**

```java
package example.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebSocketDemoApplication.class, args);
    }
}
```

### 14.4. Reactive echo handler

**`src/main/java/example/ws/EchoSocketHandler.java`**

```java
package example.ws;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class EchoSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {

        Flux<WebSocketMessage> outbound = session.receive()
                .filter(message ->
                        message.getType()
                                == WebSocketMessage.Type.TEXT)
                // Đọc ngay khi DataBuffer còn hợp lệ.
                .map(WebSocketMessage::getPayloadAsText)
                .map(text -> text.length() > 256
                        ? "error:too-long"
                        : "echo:" + text)
                .map(session::textMessage);

        return session.send(outbound);
    }
}
```

**Điểm then chốt:** Chỉ **một** `receive()` và **một** `send(outbound)`, được nối trong cùng reactive pipeline. Không tự subscribe, không giữ WebSocketMessage vào cache, không gọi blocking API. Server giữ connection hoạt động trong lúc client gửi text và đóng khi lifecycle kết thúc.

Demo giới hạn **256 Java UTF-16 code units** để đơn giản, **không phải** giới hạn bytes theo RFC 6455. Trong production, cần max message bytes ở server, kiểm tra encoding/length và policy đóng khi dữ liệu vi phạm. Trả `error:too-long` như một text reply chỉ là ứng dụng demo, không phải chuẩn WebSocket protocol error.

Non-text messages bị filter bỏ qua, không làm echo; production protocol nên định nghĩa rõ binary/control handling và close status khi không hỗ trợ, không âm thầm bỏ mọi loại message mà client cần biết.

### 14.5. Periodic outbound handler

**`src/main/java/example/ws/TickSocketHandler.java`**

```java
package example.ws;

import java.time.Duration;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class TickSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> ticks =
                Flux.interval(Duration.ofMillis(60))
                    .take(3)
                    .map(i -> session.textMessage(
                            "tick-" + (i + 1)));

        return session.send(ticks);
    }
}
```

`Flux.interval` tạo các ticks theo Reactor scheduler, **không dùng `Thread.sleep` hoặc tạo một thread ngủ riêng cho mỗi socket**. `take(3)` bảo đảm finite output; sau ba messages, source complete và `send` hoàn tất. Lifecycle response/connection sẽ được framework xử lý; không kỳ vọng ticks tới client tại chính xác 60/120/180 ms vì scheduling/network jitter.

### 14.6. WebSocket route mapping

**`src/main/java/example/ws/WebSocketRouting.java`**

```java
package example.ws;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;

@Configuration
public class WebSocketRouting {

    @Bean
    HandlerMapping webSocketMapping(
            EchoSocketHandler echo,
            TickSocketHandler ticks) {

        return new SimpleUrlHandlerMapping(
                Map.of("/ws/echo", echo,
                       "/ws/ticks", ticks),
                -1);
    }
}
```

**Đọc cấu hình:** `SimpleUrlHandlerMapping` ánh xạ URL tới các instances `WebSocketHandler`. Order -1 thường cho mapping này ưu tiên trước annotated controller mappings ở cùng DispatcherHandler. Trong app Boot WebFlux có Java config mặc định, `WebSocketHandlerAdapter` đã được đăng ký; **không tạo thêm `WebSocketHandlerAdapter` bean chỉ vì chưa thấy class đó trong source**.

Ở ứng dụng có nhiều custom mappings, tránh giao nhau/overlap `/ws/**` với annotated controllers hoặc static fallback. Kiểm tra mapping order, HTTP handshake đúng và startup logs khi có collision.

### 14.7. REST status endpoint dùng chung application

**`src/main/java/example/ws/StatusController.java`**

```java
package example.ws;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping("/api/status")
    public Map<String, String> status() {
        return Map.of("state", "ready");
    }
}
```

Nó không liên quan trực tiếp WebSocket session nhưng giúp minh họa **REST và WebSocket chung WebFlux DispatcherHandler**. Đối với `/ws/echo`, HTTP request thường thiếu `Upgrade` không biến thành một REST request trả JSON: handshake có thể bị từ chối.

## 15. Chạy project và thử bằng WebSocket client

Từ thư mục `webflux-websocket-demo` với Java 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Hai lệnh chạy theo thứ tự. Khi Boot mở cổng mặc định 8080:

### Test REST endpoint

```bash
curl -i 'http://localhost:8080/api/status'
```

Dự kiến body:

```json
{"state":"ready"}
```

### Vì sao curl GET thường không test được WebSocket?

`curl -i http://localhost:8080/ws/echo` không gửi đầy đủ WebSocket handshake/Upgrade headers và không duy trì WebSocket frame protocol như một WebSocket client. Nó có thể nhận HTTP 4xx thay vì 101. Hãy dùng browser WebSocket API, `websocat`, `wscat` hoặc Spring `WebSocketClient`.

### CLI với websocat

Nếu đã cài `websocat`:

```bash
websocat ws://localhost:8080/ws/echo
```

Gõ:

```text
xin-chao
reactor
```

Client sẽ quan sát các thông điệp echo tương ứng:

```text
echo:xin-chao
echo:reactor
```

Đây là nội dung message expected, không khẳng định terminal client sẽ hiển thị chính xác prompt/local echo như nhau trên mọi OS. Nhấn Ctrl+C hoặc đóng client để kết thúc kết nối.

### CLI periodic ticks

```bash
websocat ws://localhost:8080/ws/ticks
```

Dự kiến server phát ba message:

```text
tick-1
tick-2
tick-3
```

Sau outbound source complete, phiên có thể được framework đóng; client cần xử lý close event. Không có thêm tick-4 vì `take(3)` giới hạn source.

## 16. Browser client: lắng nghe message và close

Ví dụ trên trang HTML chạy tại origin được server cho phép, browser hỗ trợ `WebSocket`:

```javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");

socket.addEventListener("open", () => {
  console.log("socket open");
  socket.send("hello");
  socket.send("Spring WebFlux");
});

socket.addEventListener("message", event => {
  console.log("received:", event.data);
});

socket.addEventListener("close", event => {
  console.log("closed:", event.code, event.reason);
});

socket.addEventListener("error", () => {
  console.error("WebSocket transport error");
});
```

Khi thành công, browser console có thể hiển thị:

```text
socket open
received: echo:hello
received: echo:Spring WebFlux
```

Client chưa chủ động close, nên server echo tiếp tục giữ session cho đến khi browser/tab/network đóng. Trong production nên đóng socket khi component unmount/page close và có connection reconnect/heartbeat policy.

**HTTPS page:** từ một trang `https://`, dùng WebSocket bảo mật `wss://` để tránh mixed-content failure và gửi traffic qua TLS. Browser sẽ tự tạo Upgrade/handshake headers; không tự viết `Sec-WebSocket-Key`.

### Cẩn thận với bufferedAmount

Browser `socket.send(...)` có thể xếp outbound bytes vào buffer; `socket.bufferedAmount` cho biết số bytes đã queue ở thời điểm đọc. Nếu producer phát quá nhanh, không gửi vô hạn không kiểm soát:

```javascript
if (socket.readyState === WebSocket.OPEN &&
    socket.bufferedAmount < 64 * 1024) {
  socket.send("presence:update");
}
```

Đây là ví dụ **policy best-effort** cho một loại message có thể drop/coalesce, không dùng để làm mất durable business commands. Browser API này không cho full Reactive Streams backpressure; cần ứng dụng tự thiết kế ACKs/rate limits khi messages quan trọng.

## 17. Integration tests: handshake, echo, ticks và REST

`WebTestClient` hữu ích cho REST, nhưng WebSocket frames cần **WebSocket client**. Test dưới đây khởi động Spring Boot trên random port rồi dùng `ReactorNettyWebSocketClient` kết nối thật.

**`src/test/java/example/ws/WebSocketIntegrationTest.java`**

```java
package example.ws;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebSocketIntegrationTest {

    @LocalServerPort
    int port;

    private URI ws(String path) {
        return URI.create(
                "ws://localhost:" + port + path);
    }

    @Test
    void echoRepliesForTwoTextMessages() {
        ReactorNettyWebSocketClient client =
                new ReactorNettyWebSocketClient();
        AtomicReference<List<String>> replies =
                new AtomicReference<>();

        client.execute(ws("/ws/echo"), session -> {
            Mono<Void> sending = session.send(
                    Flux.just("hello", "reactor")
                            .map(session::textMessage));

            Mono<Void> receiving = session.receive()
                    .map(WebSocketMessage::getPayloadAsText)
                    .take(2)
                    .collectList()
                    .doOnNext(replies::set)
                    .then();

            return Mono.when(sending, receiving)
                    .then(session.close());
        }).block(Duration.ofSeconds(5));

        assertEquals(
                List.of("echo:hello", "echo:reactor"),
                replies.get());
    }

    @Test
    void periodicHandlerEmitsExactlyThreeTicks() {
        ReactorNettyWebSocketClient client =
                new ReactorNettyWebSocketClient();
        AtomicReference<List<String>> ticks =
                new AtomicReference<>();

        client.execute(ws("/ws/ticks"), session ->
                session.receive()
                        .map(WebSocketMessage::getPayloadAsText)
                        .take(3)
                        .collectList()
                        .doOnNext(ticks::set)
                        .then())
              .block(Duration.ofSeconds(5));

        assertEquals(
                List.of("tick-1", "tick-2", "tick-3"),
                ticks.get());
    }

    @Test
    void ordinaryRestRequestStillWorks() {
        WebTestClient http = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();

        http.get().uri("/api/status")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.state").isEqualTo("ready");
    }

    @Test
    void plainHttpGetCannotReplaceWebSocketHandshake() {
        WebTestClient http = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();

        http.get().uri("/ws/echo")
                .exchange()
                .expectStatus().is4xxClientError();
    }
}
```

Bộ test có **4 methods**. Hai methods kiểm tra WebSocket frames thực tế; một method xác nhận REST/JSON cùng server; một method xác nhận GET thường không tương đương handshake. `block(Duration.ofSeconds(5))` **chỉ chạy trên JUnit test thread**, không nằm trong WebFlux event-loop server code. Trong app production, không dùng `block()` trong handlers.

**Giải thích `Mono.when(sending, receiving)`:** nó subscribe đồng thời vào luồng gửi của client và luồng nhận replies, rồi complete khi cả hai hoàn tất. Sau đó client chủ động gửi close. Nếu chỉ `sending.then(receiving)`, việc subscribe receive sau khi send xong đôi khi làm test phụ thuộc buffering/timing; composition đồng thời rõ lifecycle hơn.

**Không hardcode timing chính xác:** tick có thể trễ do scheduler/network; test khẳng định thứ tự/nội dung chứ không khẳng định mỗi tick xuất hiện đúng 60 ms.

**Không phải một benchmark:** bốn tests không đo thousands concurrent sockets, proxy upgrade, TLS, idle timeouts, memory leaks, backpressure hoặc message delivery guarantee. Đây là runnable project được rà soát API tĩnh; **chưa chạy Maven trong phiên biên soạn Knowledge trên Google Sheets**.

### Nếu WebSocket test timeout

Kiểm tra:
- App thật chạy WebFlux, không phải Spring MVC do dependency selection.
- `/ws/echo` và `/ws/ticks` được `SimpleUrlHandlerMapping` đăng ký.
- `WebSocketHandlerAdapter` do WebFlux configuration cung cấp; custom WebFlux config không thay hỏng.
- Reverse proxy/ingress nếu có đang forward `Upgrade` và `Connection` headers.
- Server đã bind `@LocalServerPort` trước khi Reactor Netty client kết nối.
- Test client có thực sự subscribe vào `receive()` và send publisher hay không.
- Handler có return publisher đúng lifecycle thay vì `Mono.empty()` quá sớm.

## 18. Nhiều publishers outbound: thiết kế multiplex an toàn

Một chat connection có thể phải gửi:
- Direct reply của handler.
- Messages từ room.
- Presence notifications.
- Heartbeat/periodic status.

**Đừng mở bốn `session.send(...)` độc lập.** Một cách tổng quát là hợp nhất các sources thành một `Flux<WebSocketMessage>`:

```java
Flux<String> replies = ...;
Flux<String> roomEvents = ...;
Flux<String> presence = ...;

Flux<WebSocketMessage> output = Flux.merge(
        replies, roomEvents, presence)
        .map(session::textMessage);

return session.send(output);
```

Đây là **snippet kiến trúc**, với các publishers đã có từ application services. `Flux.merge` có thể interleave events; không bảo đảm toàn cục thứ tự giữa nhiều sources. Nếu cần ordering, thiết kế sequence numbers, partition keys hoặc serialize các commands qua một queue.

### Tránh nhận raw receive() hai lần

Sai:

```java
Mono<Void> a = session.receive().doOnNext(this::audit).then();
Mono<Void> b = session.send(session.receive().map(this::reply));
return Mono.when(a, b);
```

Đây là phản ví dụ; nếu nguồn inbound là one-shot/live stream, hai subscriptions có thể cạnh tranh/nhân đôi consumption. Cần **một inbound flow** rồi share/multicast có chủ đích hoặc route commands sang sink/processor đã được kiểm soát.

### Sinks.Many: phù hợp khi nào?

`Sinks.Many<T>` của Reactor có thể kết nối imperative events từ broker/callback tới reactive outbound publisher. Nhưng cần chọn mode:
- `multicast()` cho subscribers đang online.
- `replay()` khi cần giữ history, **có giới hạn retention**.
- `unicast()` với một subscriber khi phù hợp từng session.
- Overflow strategy/quota và xử lý `tryEmitNext` failures.

Không viết `sink.tryEmitNext(event)` rồi luôn giả định success. Nếu một consumer quá chậm, phải có policy do business chấp nhận. Đóng sink khi session kết thúc, cleanup subscriptions/room membership và không giữ references làm memory leak.

## 19. Auth, Origin, CSRF và quyền trên từng message

### Authentication ở handshake

Handshake vẫn là một HTTP request. Spring Security WebFlux có thể áp authentication ở tầng WebFilter/SecurityWebFilterChain và cấp Principal/metadata cho WebSocket handshake/session. Tuy nhiên **không bảo đảm** mọi header/token có cùng điều kiện như HTTP fetch:

- Browser WebSocket constructor **không cho tùy ý đặt Authorization header** như Java HTTP client thông thường.
- Cookies có thể được gửi tự động theo browser policy; phải cân nhắc SameSite, secure flag và session fixation.
- Query string token có nguy cơ lọt vào server/proxy logs/history, nên không đặt secrets dài hạn vào `?token=...`.
- Nếu dùng subprotocol để mang auth metadata, phải có protocol/design rõ và không lạm dụng header cơ chế thương lượng cho secrets.

### Origin và Cross-Site WebSocket Hijacking

WebSocket handshake có `Origin` trong browser. **CORS của WebSocket không phải hoàn toàn giống chính sách `fetch()`**: browser không tự áp cùng cơ chế preflight/response đọc như REST. Server phải kiểm tra Origin theo allowlist phù hợp để giảm rủi ro cross-site WebSocket hijacking (đặc biệt với cookie/session auth).

Spring WebFlux có thể cấu hình CORS/allowed origins cho WebSocket handler mapping, ví dụ thông qua `CorsConfigurationSource` trên handler hoặc `SimpleUrlHandlerMapping` URL CORS configuration theo Spring docs. **Không** cho mọi origins trong production chỉ để browser demo hoạt động. Kiểm tra browser thực tế, reverse proxy và WebSocket handshake response khi thêm origin policy.

### Authorization từng thông điệp

Một user được phép **mở kết nối** chưa chắc có quyền:
- Join một room cụ thể.
- Subscribe private event stream của người khác.
- Thực hiện `deleteDocument`/`transferFunds` message.
- Gửi với tốc độ cao hoặc payload lớn.

Thiết kế message envelope:

```json
{"type":"join","roomId":"room-17","requestId":"r-42"}
```

Đây chỉ là JSON protocol của **ứng dụng**, không phải payload chuẩn bắt buộc bởi WebSocket. Server decode schema, validate input, xác thực principal và **check ACL mỗi action**; tuyệt đối không dùng `userId` client gửi để giả danh. Với multi-tenant, route messages bằng tenant identity tin cậy từ authentication, không chỉ URL/body.

### CSRF và WebSocket

Nếu browser có session cookies, rủi ro cross-site handshake/commands phải được quản lý bằng Origin validation, authentication/session policy và message-level authorization. Không suy luận HTTP CSRF filter luôn kiểm tra every WebSocket message sau upgrade. Với STOMP/Spring Security messaging có những chính sách khác; bài này sử dụng low-level WebSocketHandler và **phải tự xác định protocol security**.

## 20. WebSocket vs HTTP streaming, SSE và NDJSON

| Đặc điểm | WebSocket | SSE | NDJSON qua HTTP |
| --- | --- | --- | --- |
| Giao thức | Upgrade sang WS (thường HTTP 101 với HTTP/1.1) | HTTP response streaming | HTTP response/request streaming |
| Hướng chính | **Hai chiều** | Server → client | Thường một chiều mỗi HTTP exchange |
| Framing | Message frames (text/binary/control) | `data:`/`event:`/blank line | Mỗi JSON record một dòng |
| Browser API | `WebSocket` | `EventSource` | `fetch` + ReadableStream/parser |
| Reconnect | Application quản lý | EventSource có auto-reconnect | Application quản lý |
| Event IDs | Application protocol | `id`/`Last-Event-ID` | Application protocol |
| Status lỗi sau khi kết nối | Message/close code | Streaming HTTP error constraints | Streaming HTTP error constraints |
| Client → server nhiều lệnh | Có trên cùng kết nối | Cần HTTP riêng | POST streaming có thể phù hợp, nhưng không full duplex messaging như WS |
| Binary payload | Có | Thường text/data framing | Có thể raw HTTP stream với media type phù hợp |
| Proxy support | Cần hỗ trợ Upgrade/WS | HTTP streaming, có thể buffer | HTTP streaming, có thể buffer |
| Phức tạp vận hành | Connections/rooms/security/retry | Heartbeat/replay/idle | Parsing/partial errors/resume |

**Không chọn WebSocket chỉ vì trả một Flux.** Với report 100.000 records chỉ download một chiều, NDJSON/HTTP file có thể đơn giản hơn. Với dashboard updates từ server, SSE đôi khi ít phức tạp hơn. Khi cần collaboration với commands hai chiều, WebSocket có lợi hơn.

## 21. Quy tắc xử lý error sau handshake

Sau khi HTTP status 101 thành công:

1. **Không còn một HTTP response 400/500 riêng cho mỗi WebSocket message**.
2. Muốn báo lỗi nghiệp vụ, gửi một message protocol, ví dụ:
   `{"type":"error","code":"invalid_command","requestId":"r-42"}`.
3. Nếu client vi phạm policy/protocol nghiêm trọng, dùng close status thích hợp.
4. Nếu server gặp lỗi bất ngờ, hạn chế leak exception messages/stack traces.
5. Nếu đã gửi một phần sequence rồi connection đứt, client cần biết **đã nhận đến message sequence nào**.
6. Các durable commands cần requestId/idempotency/ACK và retry policy.
7. Bảo đảm server không vô tình broadcast error chứa private room data cho user không được phép.
8. Logs/metrics nên gắn session ID, trace ID, auth/tenant theo chính sách riêng, không dump raw payload.

Ví dụ envelope cho reply:

```json
{"type":"ack","requestId":"r-42","sequence":182,"status":"accepted"}
```

Một ACK protocol cần quy định `accepted` nghĩa server đã queue hay đã commit durable storage. Không hứa exactly-once chỉ vì chạy trên cùng TCP connection; một ACK có thể mất khi network đóng ngay sau side effect, client retry có thể tạo duplicate.

## 22. Per-session state, rooms và horizontal scaling

Mỗi connection có một session riêng. Trong một application process, bạn có thể có hàng nghìn sessions, nhưng đừng chỉ giữ một `List<WebSocketSession>` static rồi broadcast bất kể user/tenant.

Vấn đề production:

- **Identity:** session → authenticated user/tenant/principal.
- **Rooms:** ai được join, subscribe, leave; validate ACL.
- **Presence:** join/leave có thể lặp khi reconnect; dùng TTL/dedup.
- **Memory:** bounded outbound queues, remove disconnected sessions.
- **Ordering:** sequence per room/user, order across producers/instances.
- **Horizontal scale:** message broker/pub-sub để fan-out giữa nodes; một process-local Map chỉ thấy sessions của node đó.
- **Sticky sessions:** WebSocket TCP connection ở node trong suốt phiên, nhưng reconnect có thể vào node khác.
- **Replay:** broker/event log/DB nếu cần không mất messages.
- **Security:** không gửi message riêng cho người nhận chỉ vì roomId client tự khai.
- **Observability:** active connections, handshakes, close code distribution, messages/sec, queue depth, late cancellations.

Nếu mở rộng qua nhiều node, việc dùng `Sinks.Many` local không tự đồng bộ subscriptions và history trên cluster. Cần shared broker hoặc architecture khác. Với durable chat, persistence và ACK protocol quan trọng hơn việc chỉ "đã đẩy WebSocket frame".

## 23. Health, idle timeouts, shutdown và reconnect

### Idle connections

Nếu client/server lâu không gửi:
- Load balancer/proxy có thể đóng idle connection.
- Socket half-open không nhất thiết được phát hiện ngay.
- TCP keepalive thường không đủ để đáp ứng một application heartbeat SLA.

Chọn ping/pong transport hoặc application heartbeat, timeout (ví dụ nếu không có pong/heartbeat sau N chu kỳ thì close). Đừng tạo heartbeat cực dày cho hàng chục nghìn clients khiến tài nguyên tăng không cần thiết.

### Graceful shutdown

Khi rolling deployment:
1. Ngừng chấp nhận handshakes mới.
2. Thông báo going-away/drain nếu ứng dụng cho phép.
3. Đóng các sessions hiện có trong một deadline.
4. Cleanup subscriptions/timers/queues/room memberships.
5. Client retry/reconnect có backoff + jitter.
6. Khôi phục subscriptions/replay theo cursor nếu cần.

### Browser reconnect

Không reconnect ngay lập tức trong một vòng lặp vô hạn khi server lỗi. Dùng exponential backoff + jitter, tối đa số attempts và phân biệt close code do policy từ chối với network failure. Khi user logout, **ngừng reconnect** và xóa state nhạy cảm. Nếu server yêu cầu reauthentication, không reuse expired token vô hạn.

## 24. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân phổ biến | Cách khắc phục |
| --- | --- | --- |
| WebSocket 404 | Chưa đăng ký `SimpleUrlHandlerMapping` hoặc sai path | Đăng ký bean với URL chính xác, test handshake |
| Handshake không được upgrade | Thiếu Upgrade headers, proxy không pass WebSocket | Dùng WebSocket client và cấu hình proxy |
| Import nhầm WebSocketHandler | Dùng Servlet `org.springframework.web.socket` trong WebFlux | Dùng `org.springframework.web.reactive.socket` |
| Handle() return ngay, socket đóng sớm | Trả `Mono.empty()` nhưng work detached | Trả Mono<Void> đại diện lifecycle |
| Client send nhưng không thấy reply | Không return/subscribe đúng outbound `session.send` | Ghép receive→send thành một chain |
| Hai replies bị đảo | `flatMap` xử lý async out-of-order | `concatMap`/sequence IDs |
| Socket double write | Gọi nhiều `session.send(...).subscribe()` | Một outbound publisher/one send |
| Kết nối đứng mãi | Outbound vô hạn không gắn cancellation | Compose inbound close/termination |
| Memory leak khi client disconnect | Không remove registry/sink/timer | `doFinally` cleanup trên owner publisher |
| Duplicate handling | Subscribe receive() nhiều nơi | Một receive flow, multicast đúng |
| DataBuffer lỗi sau async delay | Pooled buffer bị giải phóng | Copy String/bytes sớm hoặc retain/release đúng |
| Direct memory leak | Retain buffer nhưng không release | DataBufferUtils và ownership policy |
| Text message bị bỏ | Filter chỉ chấp nhận TEXT nhưng client gửi binary | Định nghĩa protocol/type và close/error rõ |
| 1006 gửi từ server | Dùng reserved close code | Chỉ gửi hợp lệ RFC 6455 codes |
| HTTP error sau upgrade không tới client | WebSocket khác HTTP response | Message error hoặc close status |
| Browser handshake bị chặn | Origin allowlist/proxy/Security policy | Cấu hình và test đúng origins |
| Browser không đặt được Authorization | Native WebSocket constructor hạn chế headers | Dùng auth flow phù hợp, không query token tùy tiện |
| User truy cập room khác | Chỉ check auth lúc handshake | Authorization mỗi room/action |
| Slow client làm queue tăng | Unbounded Sinks/buffer | Bounded queues và overload policy |
| Event loop lag | Blocking JDBC/API trong handler | Reactive driver hoặc bounded offload |
| Ping không xuất hiện trong receive() | Runtime auto-handles control frames | Kiểm tra implementation; app heartbeat nếu cần |
| Client reconnect tạo duplicate commands | Thiếu requestId/idempotency | Dedup/ACK/persistence |
| WebSocket qua HTTPS lỗi | Dùng `ws://` trên secure page | `wss://` và TLS |
| Test WebTestClient GET không upgrade | HTTP client không làm WS frames | ReactorNettyWebSocketClient/WebSocketClient |
| Multi-node chat mất notifications | Process-local sessions không chia sẻ | Broker/event bus + durable offsets |
| Origin '*' với cookie auth | Cross-site WS hijacking | Strict allowlist và auth/ACL |
| Connection leak ở deploy | Không graceful drain | Close with deadline, cleanup và client reconnect |

## 25. Checklist review production

- [ ] Dùng `spring-boot-starter-webflux`, đúng reactive socket imports.
- [ ] `WebSocketHandlerAdapter` và WebSocket routing được WebFlux config phát hiện.
- [ ] Mỗi handler trả **một** `Mono<Void>` sở hữu lifecycle.
- [ ] `receive()` không bị subscribe nhiều lần ngoài ý định.
- [ ] Một outbound send Publisher/connection với multiplexing có kiểm soát.
- [ ] Không `block()` hoặc `subscribe()` tự phát trên Netty event loop.
- [ ] Không giữ pooled `WebSocketMessage` qua async boundary khi chưa retain/release.
- [ ] Có message type/schema validation và max bytes/frame/message.
- [ ] Authentication handshake và Origin allowlist đúng.
- [ ] Authorization từng command/room/tenant.
- [ ] Không truyền secrets lâu dài trong URL query/logs.
- [ ] Session-scoped resources và room memberships cleanup khi complete/error/cancel.
- [ ] Quy tắc close codes/heartbeats/idle detection rõ ràng.
- [ ] Per-client outbound queues bounded, có backpressure/overload policy.
- [ ] Không gửi HTTP response mới sau 101 upgrade.
- [ ] Retry/reconnect có backoff, idempotency và replay policy nếu cần.
- [ ] App có graceful shutdown/drain với nhiều kết nối lâu dài.
- [ ] Metrics active sockets, close codes, dropped messages, queue sizes và latency.
- [ ] Integration tests thực sự dùng WebSocketClient, không chỉ MockMvc/WebTestClient HTTP.
- [ ] Kiểm thử qua reverse proxy, TLS, load balancer và idle timeouts như production.

## 26. Bài tập thực hành

### Bài 1 — Ping-pong ở tầng application

Thêm lệnh text `"ping"` vào echo protocol, response text `"pong"`. Giải thích tại sao đây **khác** với WebSocket control frame PING/PONG. Test bằng WebSocketClient, gửi `ping` và assert `pong`.

### Bài 2 — Close với thông báo

Khi client gửi `"bye"`:
1. Gửi text acknowledgement `"goodbye"`.
2. Sau khi acknowledgement được ghi, close với `CloseStatus.NORMAL`.
3. Không gửi lại messages nếu session đã đóng.
4. Test close không gây double sends và nguồn inbound được hủy/cleanup.

### Bài 3 — Broadcast room

Thiết kế một room có 3 sessions:
- Authenticated user mới được join.
- Gắn sequence cho mỗi room event.
- Một inbound receive flow mỗi session.
- Một outbound send flow mỗi session.
- Bounded queue và overflow policy khi một user đọc chậm.
- Cleanup đúng khi cancel/error/normal close.
- Nếu scale 2 nodes, mô tả vì sao cần pub/sub hoặc broker.

### Bài 4 — Slow consumer

Giả lập một client không đọc outbound nhanh:
- Đo queue depth, active sessions, send completion latency.
- Thử overload policy (drop presence updates vs disconnect).
- Không làm mất durable payment/chat commands không có ACK.
- Xác minh sự khác biệt giữa backpressure Reactor và browser `bufferedAmount`.

### Bài 5 — Reverse proxy / TLS

Kết nối tới `wss://example.test/ws/echo` qua một trusted proxy có cấu hình Upgrade/Connection, TLS và idle timeout:
- Test HTTP 101 vs các handshake errors.
- Test browser Origin allowlist.
- Quan sát close 1000 vs abnormal disconnect.
- Test reconnect backoff khi server rolling deploy.

## 27. Câu hỏi tự kiểm tra

1. `WebSocketHandler.handle` nhận kiểu gì và trả kiểu gì?
2. `WebSocketSession.receive()` và `send(...)` trả những reactive types nào?
3. Vì sao WebSocket cần handshake 101 trước khi gửi frames?
4. WebSocket text messages có dùng newline delimiter như NDJSON không?
5. `WebSocketHandler` reactive khác Servlet WebSocketHandler ra sao?
6. Vì sao `return Mono.empty()` ngay có thể đóng session quá sớm?
7. Có nên gọi `session.send(...).subscribe()` trong handler không?
8. Nếu outbound là `session.receive().map(...)`, completion phụ thuộc điều gì?
9. Khi inbound/outbound độc lập, phải ghép termination ra sao?
10. Làm sao nhận biết client cancel, network error và normal close?
11. `doFinally` có gì hơn `doOnComplete` khi cleanup?
12. Tại sao `session.isOpen()` snapshot không đủ làm vòng lặp life-cycle?
13. Vì sao chỉ có một outbound writer cho một connection?
14. `flatMap` và `concatMap` khác nhau gì khi xử lý replies có thứ tự?
15. `WebSocketMessage.Type.TEXT` khác BINARY như thế nào?
16. Khi nào cần retain/release WebSocketMessage DataBuffer?
17. HTTP 400 có thể được gửi cho lỗi nghiệp vụ sau khi đã upgrade thành WebSocket không?
18. Code 1006 có được truyền trong close frame không?
19. Có thể dùng WebTestClient HTTP GET thay WebSocket client để kiểm chứng messages không?
20. Vì sao browser WebSocket API không hỗ trợ custom Authorization headers như fetch?
21. Origin validation có tác dụng gì với cookie-auth WebSocket?
22. Kiểm tra quyền ở handshake đã đủ cho room-specific commands chưa?
23. WebSocket có tự chống message floods, slow consumers và memory leak không?
24. `Flux.interval` có nghĩa mỗi session tạo một sleeping Java Thread riêng không?
25. Vì sao `boundedElastic` không biến JDBC thành non-blocking?
26. Với nhiều producer, nên gọi nhiều `send` hay merge về một outbound Flux?
27. Nếu room có nhiều server nodes, local `Map<sessionId,session>` có đủ broadcast không?
28. SSE/NDJSON có lợi thế nào khi client chỉ cần nhận dữ liệu một chiều?
29. Khi client reconnect sau disconnect, làm sao chống duplicate business commands?
30. Khi shutdown, server và client cần những quy tắc nào để không leak state?

**Gợi ý:** (1) WebSocketSession → Mono<Void>. (2) Flux<WebSocketMessage> và Mono<Void>. (3) Đổi từ HTTP sang WS protocol. (4) Không; WS tự có framing. (5) Reactive Mono/Flux vs Servlet callbacks. (6) Lifecycle Mono kết thúc ngay. (7) Không. (8) Inbound close/error/cancel. (9) Một Mono<Void> kết hợp đúng signals. (10) Reactive signals/closeStatus/metrics. (11) Hỗ trợ ERROR/CANCEL. (12) Race/CPU polling. (13) Tránh competing writers và ordering lỗi. (14) concatMap giữ thứ tự. (15) Nội dung/framing/payload handling khác. (16) Giữ pooled buffer qua async boundary. (17) Không, cần WS message/close code. (18) Không. (19) Không. (20) Native browser constructor không cho tùy biến request headers. (21) Chống cross-site WS hijacking. (22) Chưa. (23) Không, cần bounds/policies. (24) Không. (25) Chỉ offload blocking. (26) Một merged Flux. (27) Không, cần bus/broker. (28) Ít phức tạp hơn cho one-way. (29) requestId + ACK + idempotency. (30) Drain/close/cleanup/backoff/replay.

## 28. Tài liệu tham khảo

- [Spring Framework — WebFlux WebSocket API](https://docs.spring.io/spring-framework/reference/6.1/web/webflux-websocket.html)
- [Spring Framework 6.1 — WebSocketHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/WebSocketHandler.html)
- [Spring Framework 6.1 — WebSocketSession Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html)
- [Spring Framework 6.1 — WebSocketMessage Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/WebSocketMessage.html)
- [Spring Framework 6.1 — CloseStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/CloseStatus.html)
- [Spring Framework 6.1 — WebSocketHandlerAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/server/support/WebSocketHandlerAdapter.html)
- [Spring Framework — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [Spring Framework — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Framework — Reactive Data Buffers](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html)
- [MDN — WebSocket Web API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [MDN — Writing WebSocket client applications](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_client_applications)

**Tổng kết:** Spring WebFlux `WebSocketHandler` xử lý **một kết nối WebSocket đã handshake**, nhận `WebSocketSession` và trả **`Mono<Void>` mô tả toàn bộ vòng đời**. `receive()` là `Flux<WebSocketMessage>` inbound; `send(Publisher<WebSocketMessage>)` là outbound writer. Một echo handler dùng `session.send(session.receive().map(...))` để ghép hai hướng thành một flow; các ứng dụng nhiều producer hoặc stream dài hạn phải thiết kế termination, cancellation, close codes, message ordering, backpressure và resource cleanup. WebSocket khác SSE/NDJSON vì là **hai chiều và có message framing riêng**, nhưng không tự cung cấp authentication, authorization, durable delivery hoặc cluster broadcast. Hãy kiểm thử qua WebSocket client thật và bảo vệ mỗi kết nối bằng giới hạn, security và lifecycle policy.

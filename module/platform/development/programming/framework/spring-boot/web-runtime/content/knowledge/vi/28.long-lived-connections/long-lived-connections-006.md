# WebSocketHandler và WebSocketSession trong WebFlux

## 1. WebSocket trong ứng dụng Spring Boot web-runtime

HTTP request–response thích hợp khi client gọi API, đợi response rồi kết thúc tương tác. Với chat, bảng giá cập nhật liên tục, thông báo cộng tác, trạng thái thiết bị hoặc trò chơi, một kết nối hai chiều lâu dài có thể giảm chi phí lặp lại HTTP requests. **WebSocket** theo RFC 6455 cung cấp kênh **full-duplex**: hai đầu cùng có thể gửi message trên một kết nối đã được nâng cấp từ HTTP.

Trong **Spring WebFlux**, có thể xử lý giao thức này ở mức thấp với:

- `org.springframework.web.reactive.socket.WebSocketHandler`: interface nhận một session WebSocket và trả `Mono<Void>` biểu diễn thời gian sống của việc xử lý.
- `org.springframework.web.reactive.socket.WebSocketSession`: abstraction cho kết nối và hai dòng message: `receive()` cùng `send(...)`.
- `WebSocketMessage`: đối tượng chứa loại message (TEXT, BINARY, PING, PONG) và payload `DataBuffer`.
- `SimpleUrlHandlerMapping`: gắn một WebSocketHandler vào URL, ví dụ `/ws/echo`.
- `WebSocketHandlerAdapter`: tích hợp handler vào WebFlux `DispatcherHandler`, thông qua handshake service/upgrade strategy.

**Mục tiêu:** hiểu cách handshake, tạo endpoint, compose hai luồng vào–ra, xử lý kết thúc/hủy/lỗi và bảo vệ tài nguyên của kết nối dài; viết ví dụ Java 17+ chạy được, kiểm thử bằng client WebSocket thật, rồi nắm giới hạn bảo mật/vận hành khi đưa lên production.

**Bối cảnh phiên bản:** ví dụ dùng **Spring Boot 3.3.13, Spring Framework 6.1.x, Java 17+** và `spring-boot-starter-webflux` để tránh nhầm với Servlet WebSocket APIs. Với production nên chọn nhánh Boot/Framework còn hỗ trợ và được vá bảo mật. Ở những phiên bản mới hơn có thể có API/configuration mới, vì vậy không trộn package chỉ vì tên class giống nhau.

## 2. WebSocket khác HTTP, SSE và polling như thế nào?

| Đặc điểm | HTTP API | SSE | WebSocket |
|---|---|---|---|
| Phương thức truyền | Request → Response | Một HTTP response stream từ server → client | Hai chiều trên cùng connection |
| Hình thức bắt đầu | HTTP request thông thường | HTTP GET với `text/event-stream` | HTTP handshake và upgrade (trong kiểu phổ biến HTTP/1.1) |
| Mô hình dữ liệu | Body HTTP/JSON | Event text theo SSE | Text/binary messages/frames theo protocol |
| Client gửi dữ liệu | Gửi HTTP request riêng | Thường HTTP request riêng | `send(...)` trên socket đang mở |
| Hạ tầng | Proxy/cache phổ biến | Cần hỗ trợ response streaming | Proxy cần hỗ trợ WebSocket upgrade và long-lived connection |
| Khi nào hợp | CRUD và API phần lớn ứng dụng | Tin tức, notifications server→browser | Chat, cộng tác, real-time hai chiều |
| Quản lý vòng đời | Theo request | Theo stream | Theo connection/session lâu dài |

Một WebSocket có thể chạy qua `ws://` hoặc `wss://` (TLS). Browser truy cập trang bằng HTTPS thường cần kết nối `wss://` để tránh mixed-content restrictions; trong production nên dùng TLS và kiểm tra certificate bình thường.

**Không nhầm WebSocket low-level với STOMP/SockJS.** Handler trong bài làm việc với protocol WebSocket thô: ứng dụng tự quy định ý nghĩa text/binary messages. Nếu dùng broker STOMP, các destination và `@MessageMapping` thuộc một abstraction khác, không tự xuất hiện khi tạo `WebSocketHandler` reactive.

**Không nhầm reactive với infinite scalability.** Dù xử lý I/O theo Publisher, một connection vẫn tiêu tốn socket, memory, TLS state, metrics, heartbeat và đôi khi session state. Nếu mỗi client tạo nhiều connection, memory/FD và outbound queue vẫn là giới hạn phải quản trị.

## 3. Handshake: HTTP trở thành WebSocket ở đâu?

Ở mô hình phổ biến trên HTTP/1.1, client gửi request có các header:

```http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: <base64-random-key>
Origin: http://localhost:8080
```

Đây là **request minh họa**; `Sec-WebSocket-Key` phải là giá trị base64 hợp lệ do client tạo, không dùng literal placeholder. Nếu thành công, response thường là:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <derived-value>
```

Sau đó client và server trao đổi các **WebSocket frames** trên kết nối, không tiếp tục tạo một HTTP response cho từng message. Trạng thái `101 Switching Protocols` thuộc **handshake**, không phải status được trả mỗi lần app gọi `session.send(...)`.

Luồng bên server WebFlux:

```text
Browser/WebSocket client
           │
           │ GET /ws/echo + Upgrade
           ▼
HTTP server (Reactor Netty trong Boot WebFlux mặc định)
           │
           ▼
WebFilter (authentication, policies nếu có)
           │
           ▼
DispatcherHandler
           │
           ▼
SimpleUrlHandlerMapping: "/ws/echo" → EchoWebSocketHandler
           │
           ▼
WebSocketHandlerAdapter
           │
           ▼
HandshakeWebSocketService
           │
           ▼
RequestUpgradeStrategy (theo HTTP server)
           │
           ▼
HTTP 101 → WebSocketSession được tạo
           │
           ▼
EchoWebSocketHandler.handle(session): Mono<Void>
           │
     ┌─────┴─────┐
     ▼           ▼
 receive()     send(...)
     │           ▲
     └─ xử lý ───┘
```

`WebSocketHandlerAdapter` dùng `WebSocketService`, mặc định có `HandshakeWebSocketService`, để kiểm tra handshake và yêu cầu server adapter nâng cấp. Không tự dựng `101` response trong handler như controller HTTP: framework xử lý negotiation/upgrade. Một GET thông thường không có header upgrade không được coi là một phiên WebSocket.

**Lưu ý HTTP/2:** WebSocket có cơ chế mở rộng cho HTTP/2 theo RFC 8441 trên các stack có hỗ trợ, nhưng không được giả định chỉ bật `server.http2.enabled=true` thì WebSocket qua HTTP/2 tự hoạt động. Bài này dùng handshake HTTP/1.1 cơ bản. Khi chạy qua CDN/ingress, xác minh giao thức và khả năng upgrade thực tế của từng hop.

## 4. Phân biệt WebFlux WebSocket API với Servlet WebSocket API

Tên `WebSocketHandler`/`WebSocketSession` có **hai nhóm package** rất dễ bị import nhầm:

| WebFlux reactive | Servlet/Spring WebSocket |
|---|---|
| `org.springframework.web.reactive.socket.WebSocketHandler` | `org.springframework.web.socket.WebSocketHandler` |
| `org.springframework.web.reactive.socket.WebSocketSession` | `org.springframework.web.socket.WebSocketSession` |
| `handle(WebSocketSession): Mono<Void>` | `handleTextMessage(...), afterConnectionEstablished(...)` và các callback |
| `session.send(Publisher<WebSocketMessage>)` | `session.sendMessage(...)` kiểu synchronous/callback |
| `Flux<WebSocketMessage> receive()` | Callback nhận message, không dùng `receive()` kiểu reactive |
| `org.springframework.web.reactive.socket.server.support.WebSocketHandlerAdapter` | Servlet configuration `WebSocketConfigurer`/registry |

Không đưa một handler implementation của Servlet stack vào `SimpleUrlHandlerMapping` reactive rồi mong Spring tự chuyển đổi. Với WebFlux, phần trọng tâm là **compose Publisher** thay vì gửi từng message từ thread bất kỳ.

`WebSocketSession` của WebFlux cũng **khác `WebSession`** (session state HTTP kiểu reactive). Một WebSocket session là **một kết nối mạng**. Một HTTP WebSession có thể sống qua nhiều HTTP requests và được handshake tham chiếu theo policy; không có quan hệ một-một bắt buộc giữa hai loại session. Cũng không đồng nhất với `HttpSession` của Servlet container.

## 5. Hợp đồng WebSocketHandler và WebSocketSession

### 5.1. Chữ ký quan trọng nhất

```java
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Mono;

class ExampleHandler implements WebSocketHandler {
    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.receive().then();
    }
}
```

Đây là **class Java minh họa có thể compile trong project WebFlux**, nhưng chưa được map vào URL và không gửi output. `Mono<Void>` cho framework biết **khi nào toàn bộ xử lý của phiên kết thúc**; nó không phải body HTTP.

**Hợp đồng quan trọng:** đừng gọi `subscribe()` bên trong `handle` rồi trả ngay `Mono.empty()`. Nếu làm vậy, framework nhìn thấy phiên đã hoàn tất nhưng công việc bạn tự chạy lại tiếp tục ở ngoài lifecycle, dễ bị đóng socket hoặc mất error/cancel propagation.

### 5.2. Các method thường dùng

| API | Type | Ý nghĩa |
|---|---|---|
| `session.receive()` | `Flux<WebSocketMessage>` | Dòng message đến; thường hoàn tất khi kết nối đóng |
| `session.send(messages)` | `Mono<Void>` | Ghi Publisher message đi ra; hoàn tất khi nguồn hoàn tất và ghi xong theo contract |
| `session.textMessage(text)` | `WebSocketMessage` | Tạo outgoing TEXT message từ chuỗi |
| `session.binaryMessage(factory -> buffer)` | `WebSocketMessage` | Tạo outgoing BINARY message từ `DataBuffer` |
| `session.pingMessage(...)`, `pongMessage(...)` | `WebSocketMessage` | Tạo protocol ping/pong message |
| `session.getId()` | `String` | ID của connection session dùng cho logging/correlation nội bộ |
| `session.getHandshakeInfo()` | `HandshakeInfo` | Metadata của HTTP handshake (URI, headers, principal, subprotocol...) |
| `session.getAttributes()` | `Map<String,Object>` | Attributes gắn với WebSocket session theo server/handshake configuration |
| `session.isOpen()` | `boolean` | Snapshot connection open tại thời điểm đọc |
| `session.close()` | `Mono<Void>` | Yêu cầu đóng bình thường |
| `session.close(CloseStatus)` | `Mono<Void>` | Đóng với close code phù hợp |
| `session.closeStatus()` | `Mono<CloseStatus>` | Quan sát close status khi kết nối kết thúc theo contract |

**Cẩn trọng:** `isOpen()` chỉ là snapshot; connection có thể đóng ngay sau khi kiểm tra. Không dùng `isOpen()` như lock bảo đảm send sẽ thành công.

`HandshakeInfo` chứa các giá trị từ request. **Không tin** raw headers/query params từ client như identity được xác thực. Nếu dùng IP qua reverse proxy, cần trusted-forwarded-header boundary riêng. `WebSocketSession.getId()` là internal connection identifier, không phải token đăng nhập.

### 5.3. Loại WebSocketMessage

```java
// Mảnh code trong WebSocketHandler khi xử lý WebSocketMessage message:
WebSocketMessage.Type type = message.getType();
if (type == WebSocketMessage.Type.TEXT) {
    String text = message.getPayloadAsText();
    // Validate text rồi xử lý ngay trong reactive pipeline.
}
```

Các loại phổ biến:
- `TEXT`: chuỗi UTF-8, thường mang JSON hoặc application protocol riêng.
- `BINARY`: payload bytes; cần format/protobuf/file chunk contract rõ ràng.
- `PING`/`PONG`: protocol control frames phục vụ liveness (stack có thể xử lý tự động một phần).
- `CLOSE` là một **WebSocket control frame** của protocol; tùy adapter thường được phản ánh qua lifecycle/`closeStatus()` hơn là một payload message giống TEXT/BINARY.

`getPayloadAsText()` giả định nội dung có thể decode UTF-8, phù hợp với TEXT; không gọi vô điều kiện với arbitrary binary bytes rồi cho rằng đó là JSON text. Với TEXT messages là JSON, cần giới hạn size rồi deserialize/validate theo schema, không chỉ parse kiểu `String.split(...)`.

## 6. Luồng vào–ra: một pipeline echo đúng lifecycle

Mẫu đơn giản nhất kết hợp nhận và gửi:

```java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> responses = session.receive()
            .map(in -> session.textMessage(
                    "echo: " + in.getPayloadAsText()));

    return session.send(responses);
}
```

Mẫu trên tương tự Spring Framework reference; phù hợp để hiểu **TEXT echo** khi client chỉ gửi text. Nếu có binary/ping/pong, không nên decode tất cả thành text; phiên bản chạy được ở mục 7 sẽ lọc TEXT và xử lý discarded messages.

**Vì sao không dùng `session.receive().subscribe(...)`?** `session.send(...)` cần một Publisher làm nguồn output. Bằng cách nối `receive().map(...)` rồi đưa trực tiếp vào `send(...)`, framework giữ kết nối sống trong thời gian nhận/sinh response, quản lý cancellation/errors và biết khi nào Mono xử lý hoàn thành.

Một WebSocket connection có hai hướng độc lập. Với echo, outbound **phụ thuộc inbound**, rất tiện để biểu diễn bằng một flow. Với chat room hoặc thông báo chủ động, outbound có thể là publisher riêng từ event source; cần phối hợp cả input và output, lifecycle và cleanup.

## 7. Dự án hoàn chỉnh: Spring Boot WebFlux WebSocket echo

Project này dùng **Java 17+, Gradle, Spring Boot 3.3.13**, không có `spring-boot-starter-web`. Boot khởi động reactive server (thường Reactor Netty). Server mở `ws://localhost:8080/ws/echo`, chỉ trả lời TEXT messages, đếm connection qua log lifecycle và có chính sách Origin đơn giản cho browser local.

### 7.1. Cấu trúc file

```text
webflux-websocket-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/websocket/WebSocketDemoApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/websocket/WebSocketEchoIntegrationTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8080
spring.application.name=webflux-websocket-demo
logging.level.com.example.websocket=INFO
```

### 7.2. Ứng dụng, mapping, adapter và handler

**`src/main/java/com/example/websocket/WebSocketDemoApplication.java`:**

```java
package com.example.websocket;

import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import org.springframework.web.reactive.socket.server.support.WebSocketHandlerAdapter;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebSocketDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSocketDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class SocketMappingConfig {

    @Bean
    HandlerMapping webSocketMapping(EchoWebSocketHandler handler) {
        SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
        mapping.setUrlMap(Map.of("/ws/echo", handler));
        mapping.setOrder(-1); // Ưu tiên mapping WebSocket trước controller.
        return mapping;
    }

    @Bean
    WebSocketHandlerAdapter webSocketHandlerAdapter() {
        return new WebSocketHandlerAdapter();
    }
}

@Component
class EchoWebSocketHandler
        implements WebSocketHandler, CorsConfigurationSource {

    private static final Logger log =
            LoggerFactory.getLogger(EchoWebSocketHandler.class);

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        String id = session.getId();
        log.info("WebSocket opened: {}", id);

        Flux<WebSocketMessage> outgoing = session.receive()
                .filter(message ->
                        message.getType() == WebSocketMessage.Type.TEXT)
                .map(message -> {
                    // Decode ngay, không giữ DataBuffer qua async boundary.
                    String text = message.getPayloadAsText();
                    if (text.length() > 2048) {
                        // Demo trả lỗi ứng dụng đơn giản; production cần
                        // giới hạn frame/message trước cả bước decode.
                        return session.textMessage("error: too-long");
                    }
                    return session.textMessage("echo: " + text);
                })
                .doOnDiscard(WebSocketMessage.class,
                        WebSocketMessage::release);

        // Không subscribe() thủ công. Framework sở hữu lifecycle.
        return session.send(outgoing)
                .doFinally(signal ->
                        log.info("WebSocket {} finished: {}", id, signal));
    }

    @Override
    public CorsConfiguration getCorsConfiguration(
            ServerWebExchange exchange) {
        CorsConfiguration cors = new CorsConfiguration();
        // Chỉ cho phép browser page ở origin demo.
        cors.setAllowedOrigins(List.of("http://localhost:8080"));
        cors.setAllowedMethods(List.of("GET"));
        return cors;
    }
}
```

**Tại sao code này có cấu trúc hợp lệ?**

- File Java chỉ có một top-level `public class` là `WebSocketDemoApplication`; `SocketMappingConfig` và `EchoWebSocketHandler` package-private hợp lệ vì cùng package.
- `@Component` đăng ký handler để config inject và map.
- `SimpleUrlHandlerMapping` gắn path `/ws/echo` tới bean, đặt order -1 để ưu tiên nó khi xử lý đúng URL.
- `WebSocketHandlerAdapter` cho phép `DispatcherHandler` thực hiện handshake và gọi handler.
- `handle(WebSocketSession)` trả đúng `Mono<Void>` từ `session.send(outgoing)`, nối với upstream `session.receive()`.
- `WebSocketMessage.Type.TEXT` tránh coi binary control frames là JSON/text. `doOnDiscard` release các messages bị Reactor discard bởi operator hỗ trợ discard.
- `getPayloadAsText()` được gọi đồng bộ trước khi downstream async work bắt đầu; trong code này không giữ inbound pooled payload sau operator.
- `CorsConfigurationSource` cho phép đặt chính sách Origin lúc handshake. Đây là một allowlist **lab local**; production phải dùng public origin thật, HTTPS/WSS và authentication. **Origin không phải cơ chế authentication**.

**Giới hạn của `text.length()`:** nó đếm UTF-16 code units đã decode và chỉ là kiểm tra ở tầng ứng dụng. Nó **không giới hạn memory đã dùng để nhận WebSocket frame** và không thay thế giới hạn frame size, tốc độ hoặc số kết nối ở server/proxy. Trong production cần điều chỉnh server-specific message/frame size phù hợp, tránh payload khổng lồ tới được handler.

### 7.3. Khởi động server

Yêu cầu JDK 17+ và Gradle tương thích với Boot 3.3:

```bash
gradle bootRun
```

Nếu project đã có Gradle Wrapper: dùng `./gradlew bootRun` (Linux/macOS) hoặc `.\gradlew.bat bootRun` (Windows PowerShell). Khi chạy server WebFlux mặc định, log có thông tin HTTP server trên cổng 8080.

Thử browser console ở trang cùng origin `http://localhost:8080`:

```javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");

socket.onopen = () => {
  console.log("connected");
  socket.send("Xin chào WebFlux");
};

socket.onmessage = event => {
  console.log("received:", event.data);
  socket.close(1000, "demo done");
};

socket.onerror = event => {
  console.error("WebSocket error", event);
};

socket.onclose = event => {
  console.log("closed:", event.code);
};
```

**Output mong đợi** trong DevTools console khi handshake thành công:

```text
connected
received: echo: Xin chào WebFlux
closed: 1000
```

Dòng log/sequence và close code có thể khác nếu mạng/proxy đóng bất thường. Nếu DevTools được mở từ trang `http://localhost:3000`, Origin là `http://localhost:3000` và cấu hình demo chỉ cho phép `http://localhost:8080` sẽ **không chấp nhận** theo policy; cần sửa allowlist cho origin hợp lệ. Đừng dùng dấu `*` khi có cookie/session hay không hiểu threat model.

**Chú ý:** nhập trực tiếp `ws://localhost:8080/ws/echo` vào thanh URL browser không giống một WebSocket handshake; dùng WebSocket API của browser, công cụ WebSocket client hoặc integration test.

## 8. Integration test với ReactorNettyWebSocketClient

Chỉ test controller qua `WebTestClient.get()` không chứng minh WebSocket handshake/frames hoạt động. Dùng `ReactorNettyWebSocketClient` của Spring Framework để mở WebSocket thật đến server chạy trên random port.

**`src/test/java/com/example/websocket/WebSocketEchoIntegrationTest.java`:**

```java
package com.example.websocket;

import java.net.URI;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebSocketEchoIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void echoTextIsReceivedOverRealWebSocket() {
        AtomicReference<String> received = new AtomicReference<>();
        ReactorNettyWebSocketClient client =
                new ReactorNettyWebSocketClient();

        URI uri = URI.create(
                "ws://localhost:" + port + "/ws/echo");

        Mono<Void> exchange = client.execute(uri, session -> {
            Mono<Void> send = session.send(
                    Mono.just(session.textMessage("hello")));

            Mono<Void> receive = session.receive()
                    .next()
                    .doOnNext(message ->
                            received.set(message.getPayloadAsText()))
                    .then();

            // Duy trì cả hai hướng đến khi send và receive kết thúc.
            return Mono.when(send, receive);
        });

        // Chỉ block trong JUnit thread, KHÔNG trong Netty event-loop.
        exchange.block(Duration.ofSeconds(10));

        assertEquals("echo: hello", received.get());
    }
}
```

Chạy:

```bash
gradle test
```

**Kết quả kỳ vọng:** test pass nếu môi trường và code đúng. Đây là **dự đoán theo contract, không phải kết quả Gradle đã chạy**. Test thực hiện WebSocket connection, không chỉ gọi HTTP GET; `@LocalServerPort` lấy cổng thực do server bind.

`Mono.when(send, receive)` duy trì hai nhánh trong handler client cho đến khi gửi đi và nhận một text response. `receive().next()` lấy một message rồi cancel subscription inbound; handler hoàn tất thì WebSocket client đóng connection. Đó là một vòng đời ngắn hợp lệ cho bài test. Dùng timeout ở JUnit để test không treo vô hạn nếu handshake, send hoặc receive gặp lỗi.

Một số adapter có thể tự xử lý control frames, nên test chỉ assert TEXT payload. Nếu muốn test trường hợp Origin bị chặn, cần truyền handshake headers với `Origin` từ client có thể cấu hình; không kết luận chỉ vì test bằng non-browser client thành công mà browser policy đã an toàn.

## 9. Mono<Void> biểu diễn vòng đời session như thế nào?

`handle(session)` trả về publisher **được framework subscribe**. Mono ấy cần hoàn tất khi việc xử lý session hoàn tất, hoặc ném lỗi nếu session xử lý lỗi theo policy. Vì vậy:

**Mẫu đúng khi outbound phụ thuộc inbound:**

```java
@Override
public Mono<Void> handle(WebSocketSession session) {
    return session.send(
            session.receive()
                    .map(msg ->
                            session.textMessage(
                                    "echo: " + msg.getPayloadAsText())));
}
```

Mẫu này phù hợp text-only echo và thể hiện ý tưởng; production cần phân loại message, validate, giới hạn size và chú ý buffer ownership như mục 7/12.

**Mẫu không nên dùng:**

```java
@Override
public Mono<Void> handle(WebSocketSession session) {
    session.receive().subscribe(message -> {
        // Không gắn vào publisher mà handle() trả về.
    });
    return Mono.empty();
}
```

Ở mẫu sai, `Mono.empty()` báo xử lý hoàn tất ngay trong khi một subscription khác vẫn chạy. Framework có thể đóng session hoặc ngừng quản lý đúng lỗi/cancel. Không dùng `subscribe()` thủ công trong business handler trừ khi bạn xây một lifecycle khác một cách có chủ đích và hiểu rõ hậu quả.

**Mẫu kết hợp inbound và outbound độc lập:**

```java
// Mảnh code đặt trong handle(session):
Mono<Void> inbound = session.receive()
        .doOnNext(message -> {
            // Chuyển đổi nội dung thành dữ liệu ứng dụng
            // và không giữ pooled DataBuffer vô hạn.
        })
        .then();

Flux<String> notifications = someFiniteOrHotSource;
Mono<Void> outbound = session.send(
        notifications.map(session::textMessage));

return Mono.when(inbound, outbound);
```

Đoạn này **không độc lập/chạy ngay** vì cần định nghĩa `someFiniteOrHotSource` và cách quản lý publisher. Nó minh họa hai nguồn dữ liệu riêng. **Điểm then chốt:** nếu `notifications` là Flux **không bao giờ complete**, `Mono.when(inbound,outbound)` sẽ tiếp tục chờ outbound ngay cả khi inbound đã hoàn tất, trừ khi upstream có cancellation/disconnect làm ngừng send. Phải thiết kế completion policy: dừng khi inbound đóng, dừng khi outbound đóng, hay giữ đến khi app chủ động close.

Spring Framework reference có ví dụ dùng `input.and(output)` và giải thích kết hợp hai dòng; điều quan trọng là hiểu chính xác semantics của Reactor operators và không phỏng đoán điều kiện kết thúc từ tên method. Với nguồn infinite/hot, thường cần tín hiệu kết thúc riêng và `takeUntilOther(...)`/lifecycle cleanup phù hợp.

## 10. Client gửi bao nhiêu tin và server xử lý ra sao?

Một WebSocket connection có thể nhận nhiều messages. `session.receive()` là một `Flux`; mỗi onNext tương ứng message ở tầng API, không phải một request HTTP mới. Ví dụ biến đổi text:

```java
Flux<WebSocketMessage> replies = session.receive()
        .filter(msg -> msg.getType() == WebSocketMessage.Type.TEXT)
        .map(msg -> msg.getPayloadAsText())
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .map(s -> session.textMessage("ACK:" + s));

return session.send(replies);
```

Đoạn này là **mảnh code trong `handle(session)`**, không phải một class standalone; với buffers bị filter/discard cần quản lý release theo adapter/operator như bài này hướng dẫn. Khi muốn xử lý một message bất đồng bộ (database/API) và **giữ thứ tự**:

```java
Flux<WebSocketMessage> replies = session.receive()
        .filter(msg -> msg.getType() == WebSocketMessage.Type.TEXT)
        .map(WebSocketMessage::getPayloadAsText)
        .concatMap(text -> service.process(text))
        .map(session::textMessage);

return session.send(replies);
```

Đây cũng là **mảnh minh họa**: cần `service.process(String): Mono<String>` non-blocking và error policy. `concatMap` xử lý tuần tự theo thứ tự, có thể làm giảm throughput khi một message chậm. `flatMap` cho concurrency nhưng cần kiểm soát thứ tự trả về, giới hạn concurrency và buffer. Nếu `service.process` gọi JDBC blocking trực tiếp trên event-loop, WebFlux không tự làm I/O thành non-blocking; dùng driver reactive hoặc offload blocking theo policy.

**Không để incoming message quyết định raw URL/SQL hay function name một cách không validate.** WebSocket frames vẫn là input không đáng tin, cần schema validation và authorization cho từng command.

## 11. Các loại message: TEXT, BINARY, PING, PONG

### 11.1. TEXT

`session.textMessage("hello")` tạo WebSocket TEXT message, API decode text inbound bằng `message.getPayloadAsText()` (UTF-8). Có thể truyền JSON text, ví dụ:

```json
{"type":"chat.send","room":"dev","text":"Xin chào"}
```

Đây là **application payload**. WebSocket protocol không tự parse JSON, không tự phân quyền gửi vào room và không tự áp bean validation như một `@RequestBody` controller. Ứng dụng cần định nghĩa schema/version/maximum size và validate mỗi command.

### 11.2. BINARY

`session.binaryMessage` nhận function tạo `DataBuffer` từ `DataBufferFactory`:

```java
// Mảnh code trong handle(session), cần StandardCharsets import:
byte[] payload = "hello".getBytes(StandardCharsets.UTF_8);
WebSocketMessage binary = session.binaryMessage(factory ->
        factory.wrap(payload));
```

Outgoing buffer/message này nên được **tạo trong publisher thật sự được gửi**, tránh cấp phát trước quá nhiều messages rồi không send vì connection cancel. Nếu stream xử lý binary/file lớn, tránh gom toàn bộ content vào RAM và quản lý memory pressure.

### 11.3. PING và PONG

WebSocket PING/PONG là **control frames**, không phải JSON `{"type":"ping"}` tự định nghĩa. Ví dụ tạo ping:

```java
// Mảnh code trong handler; DataBufferFactory do session cung cấp:
WebSocketMessage ping = session.pingMessage(
        factory -> factory.wrap(new byte[] {1}));
```

Không đảm bảo mọi adapter đều phát PING/PONG lên `receive()` theo cùng cách; nhiều network stacks tự phản hồi ping. **Không tự triển khai hai heartbeat policies xung đột** giữa proxy, transport và application. Nếu cần application-level heartbeat để phát hiện client đã mất, định nghĩa rõ interval, timeout, giới hạn retry và xem liệu proxy có idle timeout riêng không.

### 11.4. CLOSE

Close frame mang close code/reason theo RFC 6455 (ví dụ 1000 normal closure, 1008 policy violation, 1009 message too big). `session.close(CloseStatus)` trả `Mono<Void>` cần được **return/compose**, không chỉ gọi rồi bỏ Publisher.

Ví dụ mảnh code:

```java
// Khi policy xác định phải đóng, có thể trả Publisher này:
return session.close(CloseStatus.POLICY_VIOLATION);
```

Đây là một nhánh của `handle(session)`; cần import `org.springframework.web.reactive.socket.CloseStatus`. Không tin rằng một exception ở application layer chắc chắn trở thành close code cụ thể: việc mapping error → close status phụ thuộc implementation, timing và response đã được gửi hay chưa. Khi mạng mất đột ngột, browser có thể báo close code 1006 (abnormal closure) từ phía client, không phải close frame thật do server gửi.

## 12. DataBuffer lifecycle: tránh rò rỉ pooled memory

Trong WebFlux, inbound `WebSocketMessage.getPayload()` là `DataBuffer`. Trên Reactor Netty, buffer có thể được pool/ref-counted. Vấn đề phổ biến là giữ buffer để đọc **sau** khi consumer/operator ban đầu đã rời đi:

```text
receive() → WebSocketMessage chứa pooled DataBuffer
                  │
                  ├── Đọc text ngay trong map() → String của ứng dụng
                  │        └── Không giữ raw buffer cho async work
                  │
                  └── Đẩy WebSocketMessage sang async queue
                           ├── Khi adapter đã release → use-after-release
                           └── Nếu retain mà quên release → memory leak
```

**Cách an toàn phổ biến:** chuyển message thành dữ liệu ứng dụng bất biến (String hoặc một DTO sau decode/validate) **ngay trong operator đồng bộ**, rồi mới gọi async service. Đừng giữ toàn bộ `WebSocketMessage` trong một external queue.

Khi thực sự cần giữ raw buffer qua async boundary:

```java
// Pseudocode fragment cho một nhánh async sở hữu message:
// Chỉ retain nếu adapter/contract yêu cầu giữ message ngoài
// vòng đời callback nhận ban đầu.
message.retain();
return asyncUse(message.getPayload())
        .doFinally(signal -> message.release());
```

Đoạn trên **không độc lập**: `message` và `asyncUse(DataBuffer)` phải được cung cấp trong handler, và cần hiểu adapter ownership để tránh release hai lần. `retain()`/`release()` là reference-count management, không phải “copy byte an toàn”. Phải release trên success, error **và cancel**. Nếu bạn tự cấp phát/gom queue hoặc lọc bỏ buffers, cần sử dụng `DataBufferUtils.release(...)` / `WebSocketMessage.release()` theo quyền sở hữu.

`doOnDiscard(WebSocketMessage.class, WebSocketMessage::release)` ở ví dụ làm sạch những messages bị operator tương thích discard (như filter) nhưng **không phải catch-all cho mọi đường rò rỉ**. Tương tự, `Flux.buffer` không giới hạn, `onBackpressureBuffer` không bounds, hoặc giữ message không bao giờ tiêu thụ sẽ gây memory pressure dù có doOnDiscard.

Đừng gọi `message.release()` một cách mù quáng khi một codec/transport đã nhận ownership và sẽ release nó, vì double release cũng gây lỗi. Dùng đúng API và test leak detection theo runtime thực tế.

## 13. Backpressure, slow consumers và outbound queue

Reactor `Flux` có backpressure, nhưng **WebSocket protocol/TCP không phải một hệ thống message queue có policy backpressure vô hạn và tự quản lý memory**. Khi producer nhanh hơn tốc độ send của connection:

- Connection bị hạn chế băng thông có thể tích lũy outbound events.
- Reactor operator buffering có thể phình RAM khi thiếu bounds.
- Một client chậm có thể giữ tài nguyên lâu, làm giảm số client phục vụ được.
- Gửi một publisher vô hạn có thể làm `handle()` không bao giờ complete nếu không có lifecycle shutdown.
- Retry/duplicate delivery không được WebSocket low-level xử lý thành “exactly once”.

Phương án tùy sản phẩm:

| Nhu cầu | Policy đề xuất |
|---|---|
| Trạng thái mới nhất (ví dụ vị trí con trỏ) | Có thể gộp/chỉ giữ mới nhất, chấp nhận mất intermediate updates |
| Chat messages phải giao đủ | Lưu nguồn sự thật vào DB/message broker, có sequence/ack/replay sau reconnect |
| Market ticker nhanh | Rate limit, sample/drop/compact có kiểm soát, nêu rõ semantics |
| Per-user notifications | Giới hạn queue và số connections per user, backpressure, timeout |
| File/binary chunks | Bound bytes in-flight, validate chunk sizes, flow control ở application layer |
| Fan-out tới hàng nghìn clients | Message broker/pubsub + per-session queues có limits, đo memory và latency |

Ví dụ sử dụng `Flux.interval(...)` để đẩy số đếm mỗi giây có thể nhìn rất đơn giản:

```java
Flux<WebSocketMessage> ticks = Flux.interval(Duration.ofSeconds(1))
        .map(i -> session.textMessage("tick:" + i));
return session.send(ticks);
```

Đây là **mảnh minh họa** trong `handle(session)`, cần import `Duration` và `Flux`. Vì Flux này vô hạn, producer chỉ dừng nếu subscription bị hủy/connection đóng hoặc bạn thêm điều kiện kết thúc. Không dùng pattern này trong production mà không có cleanup, idle timeout và backpressure policy.

Sử dụng `Sinks.Many` để fan-out cũng cần quyết định **`tryEmitNext` thất bại thì làm gì**. `FAIL_OVERFLOW`, `FAIL_ZERO_SUBSCRIBER` hoặc subscriber chậm không được bỏ qua như thể gửi thành công. Cơ chế sink chỉ là trong-process; khi có nhiều instances và load balancer, cần pub/sub/broker nếu muốn broadcast xuyên nodes.

## 14. Error, cancellation và kết thúc kết nối

Các tín hiệu Reactor quan trọng:

| Tín hiệu | Khi nào | Hành động |
|---|---|---|
| `onComplete` | Inbound/outbound hoàn tất theo Publisher | Kết thúc/đóng session theo contract |
| `onError` | Parsing, business service, transport gửi/nhận báo lỗi | Log an toàn, metrics, cleanup; đóng nếu cần |
| `cancel` | Subscription bị hủy vì peer disconnect/lifecycle timeout/downstream operator | Giải phóng tài nguyên, dừng task khi có thể |
| WebSocket CLOSE | Peer yêu cầu đóng bình thường hoặc có code phù hợp | Tôn trọng close lifecycle; quan sát `closeStatus()` |
| TCP reset/idle timeout | Mất kết nối không clean | Cleanup và hướng dẫn reconnect |

Trong handler có thể quan sát:

```java
return session.send(outbound)
        .doOnError(ex ->
                log.warn("WS {} failed: {}",
                        session.getId(), ex.toString()))
        .doFinally(signal ->
                log.info("WS {} ended with {}",
                        session.getId(), signal));
```

Đây là **mảnh code trong class có `log` và `outbound`**, không chạy độc lập. `doFinally` quan sát `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL` của subscription tại vị trí callback, **không chứng minh toàn bộ việc ghi vào external DB/file đã được rollback**. Nếu bạn khởi động một task nằm ngoài reactive chain, việc WebSocket bị cancel không tự dừng task ấy.

**Không coi tất cả disconnect là lỗi server.** Browser đóng tab, mạng đổi, client reconnect hoặc proxy idle timeout là sự kiện vận hành bình thường. Theo dõi close codes và error categories ở mức tổng hợp, không spam stack trace cho từng client rời đi.

**Không cố gửi message mới sau khi session đã đóng** dựa vào một lần check `isOpen()` trước đó; send có thể fail do race. Hãy tạo publisher gắn lifecycle và xử lý error/cancel.

## 15. Dùng session attributes và handshake metadata đúng cách

`WebSocketSession.getHandshakeInfo()` cung cấp thông tin từ lúc handshake: URI, HTTP headers, thông tin principal, subprotocol, addresses theo adapter. Có thể dùng để log request correlation hoặc tạo context cho phiên.

Nhưng:
- `getHandshakeInfo().getHeaders()` có thể chứa cookies/Authorization; không log nguyên.
- Query params như `?token=...` xuất hiện trong URI và proxy logs; **không khuyến khích đặt bearer token dài hạn trong WebSocket URL**.
- Reverse proxy có thể làm local/remote address phản ánh địa chỉ proxy; dùng `Forwarded`/`X-Forwarded-For` chỉ khi edge đã sanitize và backend tin đúng proxy.
- Session attributes là state **theo connection**, không phải cache toàn cục cho tất cả users; không tùy ý giữ connection object trong static map mà không cleanup.
- Principal ở handshake không phải giấy phép thực thi mọi command. Phải làm authorization theo user, room, tenant, action và thời điểm (token có thể hết hạn hoặc quyền bị revoke sau handshake).

Khi cần mang một vài thuộc tính từ HTTP `WebSession` sang `WebSocketSession`, Spring Framework có `HandshakeWebSocketService.setSessionAttributePredicate(...)` để chọn những attributes hợp lệ. Đừng sao chép toàn bộ HTTP session state nếu nó chứa secrets/objects khó quản lý; chỉ copy những giá trị tối thiểu cần thiết và kiểm tra privacy.

Nếu cần xác thực tại handshake, cấu hình `SecurityWebFilterChain` của WebFlux để bảo vệ path WebSocket, kiểm tra cookie/session/token theo threat model. Đừng tự so sánh `X-User-Id` từ client như identity tin cậy. Ở raw WebSocket handler, bạn cần tự thiết kế application-level authorization cho message commands; `@MessageMapping`/STOMP security không tự áp cho raw TEXT frames.

## 16. Origin policy: WebSocket không giống CORS preflight thông thường

Browser khi mở WebSocket thường gửi `Origin`. Server phải kiểm soát origins để tránh **Cross-Site WebSocket Hijacking** (đặc biệt khi authentication dựa vào cookie tự được browser gửi). Spring WebFlux docs hướng dẫn:
- Handler có thể implement `org.springframework.web.cors.reactive.CorsConfigurationSource` và trả `CorsConfiguration` giới hạn origins.
- Hoặc đặt CORS config trên `SimpleUrlHandlerMapping` theo URL pattern.
- Nếu có cả hai cơ chế, Spring kết hợp cấu hình theo contract.

Ví dụ trong mục 7 chỉ cho phép `http://localhost:8080`. Với production frontend trên `https://app.example.test` thì phải allow chính xác origin đó, không dùng một origin local.

**Cần phân biệt:**
- Browser WebSocket handshake **không thực hiện CORS preflight OPTIONS giống fetch/XHR thông thường**. Kiểm soát Origin của WebSocket xảy ra trong handshake/handler mapping policy.
- Non-browser clients có thể gửi hoặc giả mạo header `Origin`, nên Origin **không phải authentication** hay authorization.
- Khi dùng cookies, phải cân nhắc SameSite/Secure/HttpOnly, CSRF/cross-site WebSocket hijacking, session fixation và identity expiration.
- Nếu có gateway reverse proxy, đảm bảo origin/host headers đã được chuyển đúng policy và không được bypass bằng một đường backend public khác.
- Với multi-tenant, không thể chỉ allow origin của một tenant rồi bỏ qua object-level authorization.

**Không giải quyết lỗi Origin bằng cách cho phép mọi nơi trong production.** Hãy xác định chính xác browser origin, scheme/port, proxies và chính sách xác thực.

## 17. Proxy, HTTPS/WSS và cấu hình kết nối dài

Khi WebSocket đi qua NGINX hoặc ingress, proxy cần hỗ trợ HTTP upgrade. Mảnh NGINX minh họa **bên trong block location của một server đã cấu hình**:

```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;

    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    proxy_set_header Host $host;
    proxy_read_timeout 75s;
}
```

Đây **không phải file NGINX standalone hoặc cấu hình production hoàn chỉnh**. Production cần HTTPS certificate, virtual host allowlist, upstream network policies, giới hạn concurrent connections và trusted proxy forwarded headers. `proxy_read_timeout` liên quan thời gian **không đọc byte từ upstream**, không phải TTL tuyệt đối của kết nối; heartbeat/ping policy cần phù hợp với proxy/network idle timeouts.

**Không dùng trust-all TLS** để làm `wss://` hoạt động. Browser cần chứng chỉ tin cậy và SAN khớp host; Java WebSocket client cũng cần TLS/SSL context theo config của implementation.

**Khi deploy nhiều instances:**
- Một WebSocket connection được giữ ở một backend instance trong suốt lifetime của socket.
- Khi pod chết, connection đứt; browser/app phải reconnect, authenticate lại và khôi phục state.
- Nếu cần broadcast giữa users nằm trên nhiều nodes, dùng Redis Pub/Sub, Kafka hoặc broker phù hợp; một `Sinks.Many` static trong một JVM không truyền sang instance khác.
- Không đảm bảo messages đang ở socket được lưu lại/replay sau reconnect; nếu cần, thiết kế sequence ID, ACK, replay window và idempotency ở application layer.
- Autoscaler/connections drain cần tránh ngắt thô hàng nghìn sessions; có graceful shutdown, rate limiting và retry jitter.

## 18. Phân biệt raw WebSocketHandler, STOMP và RSocket

**Raw WebSocketHandler WebFlux**:
- Làm việc trực tiếp với TEXT/BINARY/PING/PONG của RFC 6455.
- Ứng dụng tự định nghĩa JSON schema, command names, message IDs, ACK, authorization và retry.
- Phù hợp khi cần giao thức nhỏ, kiểm soát chặt hoặc nối tới một protocol/application chuyên biệt.

**STOMP trên WebSocket**:
- Có khái niệm destination, broker relay/simple broker, subscribe/send, thường dùng trong các ứng dụng messaging.
- Spring messaging APIs như `@MessageMapping` thuộc abstraction khác; đừng gắn trực tiếp như annotation controller vào raw `WebSocketHandler` rồi chờ mapping.
- Có thể triển khai trong mô hình Spring Servlet/message broker khác tùy library/stack.

**RSocket**:
- Protocol khác hỗ trợ request-response, fire-and-forget, request-stream và channel với semantics riêng.
- Có thể dùng transport WebSocket hoặc TCP; không đồng nghĩa một `WebSocketHandler` là RSocket endpoint.
- Nếu bài toán cần broker hoặc application-level backpressure/stream semantics phong phú, cân nhắc stack messaging phù hợp thay vì tự phát minh một protocol khó duy trì.

**SSE** có thể đơn giản hơn nếu chỉ cần server→client notifications và browser không cần gửi message trên cùng connection. Chọn WebSocket dựa vào nhu cầu full-duplex và tần suất giao tiếp thật, không chỉ vì từ “real-time”.

## 19. Kiểm thử nhiều tình huống hơn echo thành công

Một integration suite có giá trị nên kiểm tra:

| Tình huống | Kỳ vọng cần kiểm tra |
|---|---|
| Một TEXT message `hello` | Nhận đúng `echo: hello` |
| Nhiều TEXT messages | Nhận đủ theo thứ tự nếu handler dùng pipeline tuần tự |
| Binary message đến text-only handler | Không bị decode như JSON/TEXT, có policy reject/ignore rõ |
| Payload lớn hơn giới hạn | Bị xử lý/reject/close theo policy, không làm server OOM |
| Browser Origin không hợp lệ | Handshake bị từ chối theo allowlist |
| Handshake thiếu hoặc sai authentication | Không nâng cấp thành phiên được cấp quyền |
| User chưa có quyền room | Command bị từ chối ngay cả khi socket đã mở |
| Client gửi CLOSE bình thường | Server cleanup resource và ghi close event phù hợp |
| Client disconnect bất ngờ | Không còn task/background buffer leak hoặc dangling session |
| Slow reader + nhiều events | Outbound queue/bytes in-flight được giới hạn |
| 1.000+ clients (theo năng lực hệ thống) | FD/memory/CPU/pool/latency trong ngưỡng cho phép |
| Đi qua NGINX/ingress thật | Upgrade headers, timeout, TLS/WSS và Origin đúng |
| Deploy/restart một pod | Reconnect/reauth/replay hành vi đã định nghĩa |

`WebTestClient` phù hợp kiểm thử HTTP routes WebFlux, nhưng **không thay thế** WebSocket client thật để kiểm tra handshake/frame. `ReactorNettyWebSocketClient` hoặc các thư viện WebSocket test client phù hợp có thể đảm nhận phần này. Với assertions về timeout, đừng đòi lịch chạy chính xác đến mili-giây trên CI.

Nếu kiểm thử binary và buffer, bật Netty leak detection trong test/staging theo mức hợp lý và đo direct memory. Các lỗi tài nguyên thường không xuất hiện ở một test echo duy nhất.

## 20. Troubleshooting các sự cố hay gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra và xử lý |
|---|---|---|
| `GET /ws/echo` trả HTTP error | Không gửi WebSocket Upgrade handshake | Dùng WebSocket client, không dùng URL HTTP thường |
| HTTP 404 lúc connect | Mapping chưa đúng path hoặc bean không được đăng ký | Kiểm tra `SimpleUrlHandlerMapping`, URL, path rewrite |
| Handler không được gọi | Thiếu `WebSocketHandlerAdapter` trong custom config hoặc conflict mapping | Kiểm tra handler mapping/adapter order |
| Compile lỗi `handleTextMessage` hoặc `sendMessage` | Import Servlet WebSocket API thay WebFlux | Dùng `org.springframework.web.reactive.socket.*` |
| App tự chuyển thành MVC/Tomcat | Có `spring-boot-starter-web` cùng WebFlux | Loại starter MVC nếu muốn reactive server |
| Connection mở rồi đóng ngay | `handle()` trả `Mono.empty()` hoặc nguồn send complete sớm | Return/compose Publisher có lifecycle đúng |
| Server nhận nhưng không gửi reply | Outgoing Publisher chưa đi qua `session.send` | Ghép `session.receive()` vào `send(...)`, không tự subscribe |
| Test timeout | Client không subscribe, mapping sai, origin bị chặn hoặc response không tới | Test với ReactorNettyWebSocketClient, kiểm tra log handshake |
| Client console báo code 1006 | Mất kết nối không clean, proxy timeout/TCP reset | Xem log proxy/TLS, close policy và network |
| `WebSocketMessage.getPayloadAsText` lỗi | Message không phải TEXT hoặc DataBuffer đã bị release | Phân loại type, decode trước async boundary, quản lý retain/release |
| Direct memory tăng | Pooled DataBuffer bị giữ/quên release | Rà retention, discarded buffer cleanup, Netty leak detection |
| Client chậm làm RAM tăng | Outbound queue không bound, broadcast quá nhanh | Áp quota, backpressure/drop/replay policy phù hợp |
| Browser bị từ chối Origin | Origin trang khác allowlist | Dùng public origin đúng, không mở wildcard vô điều kiện |
| Không kết nối được qua reverse proxy | Thiếu Upgrade/Connection headers hoặc idle timeout | Kiểm tra NGINX/ingress WS support, WSS và TLS |
| Gửi JSON nhưng handler không parse thành DTO | Raw WebSocket không có `@RequestBody` tự động | Tự decode/validate JSON và handle errors |
| Client nhận tin trùng sau reconnect | Không có message ID/idempotency/replay contract | Thiết kế ACK/sequence/dedupe ở application layer |
| Tin chỉ đến clients cùng pod | Fan-out bằng in-memory Sink, không có broker | Dùng pub/sub/broker để scale nhiều instances |
| User bị thu hồi quyền nhưng socket vẫn mở | Chỉ authenticate lúc handshake, không recheck | Thiết kế re-auth/expiry/authorization theo command hoặc close session |

## 21. Checklist triển khai an toàn

- [ ] Dùng đúng WebFlux `WebSocketHandler`/`WebSocketSession` và chỉ `spring-boot-starter-webflux` nếu muốn reactive server.
- [ ] Tạo mapping `/ws/...` bằng `SimpleUrlHandlerMapping` và adapter phù hợp.
- [ ] `handle()` trả **Publisher gắn với toàn bộ lifetime**, không fire-and-forget `subscribe()`.
- [ ] Dùng `receive()` để nhận, `send(Publisher)` để ghi, phân loại TEXT/BINARY/control frames.
- [ ] Parse schema/version/authorization cho mỗi application command.
- [ ] Không giữ raw `DataBuffer` qua async boundary nếu chưa retain đúng; release đúng ownership.
- [ ] Đặt giới hạn message/frame size, rate limit và số connection/tenant/user.
- [ ] Kiểm soát outbound queue, slow consumers và producer hot/infinite.
- [ ] Xử lý close/error/cancel và dọn tài nguyên ở mọi đường, cả server shutdown.
- [ ] Enforce Origin allowlist ở handshake; authentication/authorization là lớp riêng.
- [ ] Dùng WSS/TLS, bảo vệ cookie/token, không ghi credential trong query/log.
- [ ] Cấu hình proxy WS upgrade, idle timeout, host allowlist và trusted forwarded headers.
- [ ] Có chiến lược reconnect, backoff/jitter, replay/dedupe nếu business cần.
- [ ] Quan sát active sessions, handshake rejection, close codes, message size, errors và memory.
- [ ] Test bằng WebSocket client thực, cả success và failure cases.
- [ ] Dùng runtime/framework version được vá, kiểm tra thay đổi giữa các major versions.

## 22. Câu hỏi tự kiểm tra

**Câu 1: `WebSocketHandler.handle` trả `Mono<Void>` để làm gì?**  
Để biểu diễn vòng đời bất đồng bộ của session; framework quản lý subscribe/complete/error/cancel và đóng session khi handling kết thúc theo contract.

**Câu 2: `WebSocketSession` khác `WebSession`?**  
`WebSocketSession` là kết nối full-duplex; `WebSession` là nơi lưu session state HTTP reactive, có thể phục vụ nhiều HTTP requests hoặc handshake với policy riêng.

**Câu 3: Vì sao không gọi `session.send(...).subscribe()` rồi trả `Mono.empty()`?**  
Vì send bị tách khỏi lifecycle do framework quản lý; handler có thể kết thúc và đóng socket trước khi send hoàn tất, mất cancellation/error propagation.

**Câu 4: Sau handshake thành công, mỗi WebSocket TEXT message có tạo một HTTP request mới không?**  
Không. Frames/messages trao đổi trên cùng connection WebSocket, không có một HTTP response status cho từng message.

**Câu 5: `getPayloadAsText()` có phù hợp với BINARY không?**  
Không dùng vô điều kiện; cần phân loại message và decode binary theo contract định dạng đã thống nhất.

**Câu 6: Với pooled buffer, khi nào cần retain/release?**  
Nếu cần giữ data sau lúc callback/operator hiện tại đã xử lý hoặc tự sở hữu buffer, phải retain theo contract rồi release đúng một lần trên mọi đường kết thúc. Với dữ liệu text, thường decode ngay thành String để không giữ raw buffer.

**Câu 7: Browser gửi Origin hợp lệ đã được xác thực chưa?**  
Chưa. Origin allowlist giúp giảm cross-site hijacking nhưng không thay login/session/token authentication và phân quyền từng command.

**Câu 8: WebFlux có tự phân phối broadcast WebSocket qua nhiều pod không?**  
Không. In-memory sink/state nằm trong mỗi JVM; nếu muốn broadcast cross-node, cần broker/pubsub và xử lý reconnect/consistency.

**Câu 9: Vì sao HTTP/2 enabled chưa chứng minh WebSocket chạy trên HTTP/2?**  
WebSocket handshake HTTP/2 có cơ chế riêng và phụ thuộc adapter/proxy. Ví dụ này chỉ dựa trên HTTP/1.1 Upgrade.

**Câu 10: Nếu outbound là Flux vô hạn, khi inbound đóng, Mono kết thúc ra sao?**  
Phụ thuộc cách compose, cancellation/close signals và operator. Không mặc định `Mono.when(...)` với một nguồn vô hạn sẽ tự complete; cần thiết kế lifecycle signal và cleanup rõ ràng.

## 23. Tài liệu tham khảo chính thức

1. Spring Framework — **WebFlux WebSockets**, WebSocketHandler, mapping, send/receive, handshake, CORS, client: https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html
2. Spring Framework 6.1 — **WebSocketHandler** JavaDoc: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/reactive/socket/WebSocketHandler.html
3. Spring Framework 6.1 — **WebSocketSession** JavaDoc: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html
4. Spring Framework 6.1 — **WebSocketMessage** JavaDoc, pooled buffer `retain/release`: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/reactive/socket/WebSocketMessage.html
5. Spring Framework 6.1 — **WebSocketHandlerAdapter**: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/reactive/socket/server/support/WebSocketHandlerAdapter.html
6. Spring Framework — **Data Buffers and Codecs**: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
7. Spring Framework — **WebFlux Security** và security filter chain: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
8. IETF RFC 6455 — **The WebSocket Protocol**: https://www.rfc-editor.org/rfc/rfc6455
9. IETF RFC 8441 — **Bootstrapping WebSockets with HTTP/2**, chỉ dùng khi triển khai hỗ trợ: https://www.rfc-editor.org/rfc/rfc8441

**Kết luận:** Trong WebFlux, `WebSocketHandler.handle(WebSocketSession)` là entry point một **connection lâu dài**, `receive()` là inbound Flux, `send(Publisher)` là outbound Mono<Void>. Hãy return/combine publishers để framework quản lý session, phân loại và validate messages, giới hạn queue/size, cleanup buffers khi cancel/error, bảo vệ Origin cùng authentication, rồi kiểm thử qua WebSocket client thực trước khi triển khai proxy/WSS/scale-out.
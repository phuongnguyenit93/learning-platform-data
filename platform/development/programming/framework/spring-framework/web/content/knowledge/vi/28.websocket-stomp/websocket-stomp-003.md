# WebSocketHandler, TextWebSocketHandler và đăng ký endpoint Servlet trong Spring Framework

## Mục tiêu học tập và phạm vi

Bài này trình bày cách tạo **WebSocket endpoint mức thấp (raw WebSocket)** trên **Spring MVC / Servlet stack** bằng giao diện `WebSocketHandler`, lớp tiện ích `TextWebSocketHandler` và cấu hình `@EnableWebSocket` + `WebSocketConfigurer`. Sau khi học, bạn có thể:

- Hiểu luồng **HTTP Upgrade handshake → WebSocketSession → xử lý message → đóng kết nối**.
- Phân biệt `WebSocketHandler` (hợp đồng callback) và `TextWebSocketHandler` (lớp cơ sở chuyên message dạng text).
- Đăng ký endpoint `/ws/echo` trên Servlet stack, hiểu vai trò của `WebSocketHandlerRegistry`, `ServletWebSocketHandlerRegistry` và Servlet container.
- Tạo ứng dụng Spring Boot/Java 17+ với server echo, trang HTML dùng trình duyệt để kết nối và gửi/nhận message.
- Biết nơi đặt xác thực, kiểm tra origin, quản lý session, giới hạn message và đồng bộ việc gửi khi nhiều luồng cùng ghi lên một WebSocket session.

**Phạm vi chính là raw WebSocket trên Servlet stack.** STOMP là giao thức nhắn tin nằm trên WebSocket và thường dùng `@EnableWebSocketMessageBroker`, broker, `@MessageMapping`. Những thành phần STOMP đó có vai trò khác và không cần thiết để xây dựng endpoint raw WebSocket trong bài.

## 1. WebSocket không giống REST HTTP request/response

HTTP REST thông thường là mô hình từng request nhận từng response. WebSocket bắt đầu bằng **một HTTP handshake** yêu cầu nâng cấp giao thức, rồi chuyển sang kết nối hai chiều sống lâu: server và client đều có thể gửi **frame** mà không cần mở HTTP request mới cho mỗi message.

Ví dụ đường đi:

```text
Browser hoặc WebSocket client
        |
        | HTTP GET /ws/echo
        | Upgrade: websocket
        | Connection: Upgrade
        | Sec-WebSocket-Key: ...
        | Sec-WebSocket-Version: 13
        v
Spring MVC HandlerMapping / WebSocketHttpRequestHandler
        |
        | handshake hợp lệ
        v
Servlet container nâng cấp kết nối
        |
        | HTTP 101 Switching Protocols
        v
WebSocketSession được thiết lập
        |
        +--- client -> text frame ---> handleTextMessage(...)
        |
        +--- server -> text frame ---> WebSocketSession.sendMessage(...)
        |
        +--- close / transport error -> callback đóng/lỗi
```

Các bước quan trọng:

1. **Đăng ký URL:** Spring biết `/ws/echo` được xử lý bởi WebSocket handler nào.
2. **Handshake:** HTTP Upgrade được xác nhận, kiểm tra origin/interceptor, thương lượng subprotocol hoặc extensions khi có.
3. **Session:** Sau khi upgrade thành công, hai phía dùng giao thức WebSocket; Spring cung cấp một `WebSocketSession` đại diện cho kết nối hiện tại.
4. **Message:** Callback nhận text/binary/pong; handler tự định nghĩa ngữ nghĩa payload.
5. **Close:** Hai phía trao đổi close frame khi có thể; server nhận callback đóng hoặc lỗi truyền tải và dọn tài nguyên.

Mỗi kết nối có một session riêng. **Một instance handler có thể xử lý nhiều sessions**, nên không lưu trạng thái người dùng của một kết nối trong biến instance thông thường nếu handler là bean singleton dùng chung.

### 1.1. URL HTTP và WebSocket

Trong ví dụ local, trang web là `http://localhost:8080/` còn endpoint WebSocket là `ws://localhost:8080/ws/echo`. Khi chạy qua HTTPS, client nên kết nối bằng `wss://`. Khác với HTTP polling, sau khi nâng cấp thành công không có một mã trạng thái HTTP mới cho từng WebSocket message.

**HTTP 101** báo nâng cấp thành công; tiếp đó dữ liệu đi qua text/binary frames. Nếu một message sai định dạng, ứng dụng có thể gửi thông báo lỗi dưới dạng frame, hoặc đóng session bằng mã close phù hợp; không “trả HTTP 400 cho frame tiếp theo”.

## 2. Giao diện WebSocketHandler

Spring Servlet dùng `org.springframework.web.socket.WebSocketHandler`. Đây là hợp đồng các callback quản lý lifecycle và message:

| Callback | Khi Spring gọi | Việc thường làm |
| --- | --- | --- |
| `afterConnectionEstablished(WebSocketSession)` | Kết nối được thiết lập | Khởi tạo context, ghi nhận session, gửi lời chào |
| `handleMessage(WebSocketSession, WebSocketMessage<?>)` | Có một message đến | Phân phối text/binary/pong hoặc xử lý chung |
| `handleTransportError(WebSocketSession, Throwable)` | Lỗi truyền tải xảy ra | Logging an toàn, đóng kết nối nếu còn mở, dọn tài nguyên |
| `afterConnectionClosed(WebSocketSession, CloseStatus)` | Kết nối đã đóng | Xóa session khỏi bộ nhớ, giải phóng subscription/resource |
| `supportsPartialMessages()` | Framework hỏi khả năng xử lý message phân mảnh | Trả về có hỗ trợ các partial messages không |

Chữ ký các callback chính có thể phát sinh `Exception`. Nếu tự implement trực tiếp, bạn phải xử lý đủ tất cả các phương thức cần thiết. Trong các trường hợp chỉ cần text, kế thừa `TextWebSocketHandler` thường gọn và rõ hơn.

**Không nhầm hai lớp khác package:**

- Servlet: `org.springframework.web.socket.WebSocketHandler`, `WebSocketSession`, `TextMessage`.
- Reactive WebFlux: `org.springframework.web.reactive.socket.WebSocketHandler`, `WebSocketSession` và `WebSocketMessage`; API dùng Reactor `Mono<Void> handle(WebSocketSession)`.

Hai hệ này cùng giải quyết WebSocket nhưng **không thay thế trực tiếp interface cho nhau**. Bài này sử dụng hoàn toàn Servlet stack và các import từ `org.springframework.web.socket.*`.

### 2.1. WebSocketMessage và WebSocketSession

Trong raw Servlet WebSocket:

- `TextMessage` mang chuỗi UTF-8/text payload, lấy bằng `getPayload()`.
- `BinaryMessage` mang dữ liệu nhị phân (tùy API có `ByteBuffer`).
- `PongMessage` biểu diễn pong control message. Ping/pong có thể được container quản lý ở mức thấp; khi cần heartbeat, thiết kế theo container và giao thức cụ thể.
- `WebSocketSession` có `getId()`, `getPrincipal()`, `getAttributes()`, `getHandshakeHeaders()`, `isOpen()`, `sendMessage(...)` và `close(...)`.

`session.getAttributes()` là map thuộc session WebSocket, có thể chứa dữ liệu được truyền vào từ handshake interceptor. Nó không tự động là một Spring HTTP session đầy đủ. `getPrincipal()` phụ thuộc việc HTTP handshake đã được xác thực/thiết lập principal trong hệ thống hay chưa.

## 3. TextWebSocketHandler: lựa chọn tự nhiên cho text frame

`TextWebSocketHandler` thuộc package `org.springframework.web.socket.handler`, kế thừa `AbstractWebSocketHandler` và xử lý callback cho message text thông qua:

```java
@Override
protected void handleTextMessage(WebSocketSession session,
                                 TextMessage message) throws Exception {
    String text = message.getPayload();
    session.sendMessage(new TextMessage("ECHO:" + text));
}
```

Đây là **đoạn nằm trong subclass**, chưa phải file Java chạy độc lập. Client gửi `hello` thì server gửi `ECHO:hello` trở lại **cùng session**. Client khác không nhận frame này vì không có cơ chế broadcast.

`TextWebSocketHandler` nhận những callback lifecycle mặc định từ `AbstractWebSocketHandler`. Nếu đến binary message, handler cơ sở này từ chối với `CloseStatus.NOT_ACCEPTABLE`; do đó không dùng `TextWebSocketHandler` khi endpoint cần upload/broadcast nội dung nhị phân, trừ khi bạn chủ động định nghĩa lại cách xử lý. Trường hợp cần binary, xem `BinaryWebSocketHandler` hoặc implement handler phù hợp.

### 3.1. Vòng đời, dọn dẹp tài nguyên

Một handler thường override thêm:

```java
@Override
public void afterConnectionEstablished(WebSocketSession session)
        throws Exception {
    // Session có thể bắt đầu nhận/gửi WebSocket message.
}

@Override
public void afterConnectionClosed(WebSocketSession session,
                                  CloseStatus status)
        throws Exception {
    // Dọn state, subscriptions hoặc session registry.
}

@Override
public void handleTransportError(WebSocketSession session,
                                 Throwable exception)
        throws Exception {
    // Log lỗi đã loại thông tin nhạy cảm; cân nhắc đóng session.
}
```

**CloseStatus** dùng mã theo giao thức WebSocket. Ví dụ: 1000 = đóng bình thường, 1008 = vi phạm chính sách, 1009 = message quá lớn, 1011 = lỗi server. Không áp dụng HTTP status code vào API `session.close(...)`.

### 3.2. Có cần lưu tất cả WebSocketSession?

- **Echo một người:** không cần map sessions. Callback đã nhận `WebSocketSession`; phản hồi cho chính session đó.
- **Chat/broadcast:** cần quản lý registry các session đang mở (ví dụ `ConcurrentHashMap`), dọn vào callback close/error, kiểm tra `isOpen()` và quyền nhận message.
- **Nhiều instance server:** registry trong RAM chỉ nhìn thấy session của instance hiện tại. Broadcast toàn hệ thống cần cơ chế fan-out qua broker/pub-sub hoặc kiến trúc tương đương; không thể coi một `ConcurrentHashMap` cục bộ là kết nối toàn cluster.

## 4. Đăng ký endpoint trên Servlet stack

Cách chuẩn trên Spring MVC dùng cấu hình sau:

```java
@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {
    private final EchoTextWebSocketHandler echoHandler;

    public WebSocketConfig(EchoTextWebSocketHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/echo");
    }
}
```

Imports cho đoạn này:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
```

Ý nghĩa:

- `@Configuration` khai báo cấu hình Spring.
- `@EnableWebSocket` bật cơ chế cấu hình raw WebSocket trên Servlet stack.
- `WebSocketConfigurer` là callback cấu hình mapping WebSocket handler.
- `WebSocketHandlerRegistry.addHandler(handler, paths...)` gắn instance handler với URL handshake.
- Spring MVC dùng cơ chế registry cho Servlet để tạo các handler mappings và phần xử lý handshake; ứng dụng thường không cần khởi tạo `ServletWebSocketHandlerRegistry` bằng tay.

`ServletWebSocketHandlerRegistry` là implementation của `WebSocketHandlerRegistry` dùng trong môi trường Servlet, nơi các đường dẫn được gắn vào Spring MVC handler mappings. Đây là lớp hạ tầng nội bộ/phần cấu hình, **không phải business handler** và cũng không phải controller REST.

### 4.1. Phân biệt các cách đăng ký

| Cơ chế | Mục đích | Khi dùng |
| --- | --- | --- |
| `@EnableWebSocket` + `WebSocketConfigurer` + `addHandler` | Raw WebSocket qua Spring Servlet | Cần trực tiếp xử lý text/binary frame |
| `@EnableWebSocketMessageBroker` + `registerStompEndpoints` | STOMP over WebSocket | Có destination, subscription, broker, `@MessageMapping` |
| `@ServerEndpoint("/...")` của Jakarta WebSocket | API WebSocket chuẩn Jakarta | Ứng dụng cố ý chọn Jakarta endpoint model |
| Reactive `HandlerMapping` + `WebSocketHandlerAdapter` | Raw WebSocket WebFlux | Ứng dụng chạy reactive HTTP stack |

Không đặt `@GetMapping("/ws/echo")` rồi trả string để “đăng ký WebSocket”. Một controller GET thông thường tạo HTTP response, không tự nâng cấp protocol. `@ServerEndpoint` là cơ chế khác; nếu dùng embedded Servlet container theo Spring Boot thì có yêu cầu registration riêng, không cần cho đường đi `@EnableWebSocket` của bài này.

### 4.2. Vị trí trong request flow

Trong Spring MVC, request handshake `GET /ws/echo` đi qua Servlet container và được định tuyến đến handler mapping cho WebSocket; từ đó Spring dùng đối tượng xử lý handshake như `WebSocketHttpRequestHandler` và tầng `HandshakeHandler`/`RequestUpgradeStrategy` để nâng cấp giao thức. Container thực hiện công việc WebSocket I/O sau upgrade.

Sơ đồ trách nhiệm:

```text
DispatcherServlet / HandlerMappings (HTTP Upgrade GET)
         |
         v
WebSocket registration ("/ws/echo")
         |
         v
WebSocketHttpRequestHandler -> HandshakeHandler
         |
         v
Servlet container adapter nâng cấp protocol
         |
         v
WebSocketSession + WebSocketHandler callbacks
```

`DefaultHandshakeHandler` có thể được tùy biến nếu cần thương lượng subprotocol, origin hoặc chiến lược upgrade riêng. Với ứng dụng Servlet thông thường, cấu hình mặc định qua registry là đủ.

## 5. Ví dụ hoàn chỉnh có thể chạy: Spring Boot WebSocket echo

Ví dụ dùng **Spring Boot 3.3.6, Java 17 và embedded Tomcat**, không cần Redis, STOMP hay broker. Trang HTML được Spring Boot phục vụ cùng origin với endpoint, giúp quan sát chính xác sự khác nhau giữa kết nối HTTP ban đầu và các frame WebSocket tiếp theo.

**Cấu trúc dự án:**

```text
servlet-websocket-demo/
├── build.gradle
└── src/
    └── main/
        ├── java/demo/websocket/
        │   ├── ServletWebSocketDemoApplication.java
        │   ├── EchoTextWebSocketHandler.java
        │   └── WebSocketConfig.java
        └── resources/static/index.html
```

### 5.1. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
}
```

Starter này cung cấp hỗ trợ WebSocket cho ứng dụng Spring MVC và môi trường Servlet container tương ứng. Gradle/Spring Boot quản lý các phiên bản Spring Framework, Jakarta Servlet, Tomcat và websocket modules tương thích. Không cần trộn thủ công các bản `javax.websocket.*` cũ vào dự án Spring Boot 3 (sử dụng hệ `jakarta.*`).

### 5.2. ServletWebSocketDemoApplication.java

```java
package demo.websocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServletWebSocketDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletWebSocketDemoApplication.class, args);
    }
}
```

Main class bật Spring Boot và component scan trong package `demo.websocket`. Lớp handler `@Component` và cấu hình `@Configuration` phía dưới sẽ được Spring phát hiện.

### 5.3. EchoTextWebSocketHandler.java

```java
package demo.websocket;

import java.io.IOException;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class EchoTextWebSocketHandler extends TextWebSocketHandler {

    @Override
    public void afterConnectionEstablished(WebSocketSession session)
            throws IOException {
        session.sendMessage(new TextMessage("READY"));
    }

    @Override
    protected void handleTextMessage(WebSocketSession session,
                                     TextMessage message)
            throws IOException {
        String payload = message.getPayload();

        // Giới hạn minh họa theo Java String length; production còn
        // cần giới hạn bytes/frame và buffer ở WebSocket container.
        if (payload.length() > 1024) {
            session.close(CloseStatus.TOO_BIG_TO_PROCESS);
            return;
        }

        session.sendMessage(new TextMessage("ECHO:" + payload));
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session,
                                      CloseStatus status) {
        System.out.println("CLOSED " + status.getCode());
    }

    @Override
    public void handleTransportError(WebSocketSession session,
                                     Throwable exception)
            throws IOException {
        if (session.isOpen()) {
            session.close(CloseStatus.SERVER_ERROR);
        }
    }
}
```

Giải thích từng callback:

1. Kết nối thành công → `afterConnectionEstablished` gửi `READY`.
2. Client gửi text payload → `handleTextMessage` đọc `message.getPayload()`.
3. Nếu chuỗi vượt quá 1.024 UTF-16 code units trong ví dụ → đóng session bằng 1009. Đây **không phải giới hạn byte mạng hoàn chỉnh**, vì chữ Unicode có độ dài UTF-8 khác nhau; bảo vệ thực tế cần cấu hình giới hạn ở container.
4. Nếu hợp lệ → gửi `ECHO:` cộng nội dung về **chính client đó**.
5. Đóng kết nối → Spring gọi `afterConnectionClosed`. In mã đóng để quan sát; trong ứng dụng thực tế, nếu có registry/subscription hãy dọn ở đây.
6. Lỗi transport → thử đóng session còn mở bằng 1011. Nếu có nhiều công việc background, handler phải dọn dẹp tài nguyên liên quan, không chỉ đóng socket.

**Tại sao handler không giữ session trong field?** Vì ví dụ chỉ phản hồi ngay session nhận được qua callback. Một bean handler có thể dùng cho rất nhiều kết nối; thêm field như `private WebSocketSession currentSession;` sẽ làm các client ghi đè session của nhau.

### 5.4. WebSocketConfig.java

```java
package demo.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final EchoTextWebSocketHandler echoHandler;

    public WebSocketConfig(EchoTextWebSocketHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/echo");
        // Mặc định chính sách origin cùng nguồn phù hợp demo này.
    }
}
```

Đây chính là bước đăng ký **endpoint Servlet**: `/ws/echo` được mapping đến bean handler. Cần đảm bảo configuration được Spring scan; ở đây package trùng với package của `@SpringBootApplication`.

### 5.5. src/main/resources/static/index.html

Trang HTML tĩnh này được Spring Boot phục vụ tại `http://localhost:8080/`. Người dùng nhấn “Connect”, gửi một đoạn text và quan sát khung nhận. JS tự chọn `ws:` hoặc `wss:` phù hợp protocol của trang.

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Spring Servlet WebSocket Echo</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 760px;
           margin: 32px auto; padding: 0 16px; }
    button, input { padding: 8px; margin: 4px 0; }
    #events { white-space: pre-wrap; padding: 12px;
              background: #f3f4f6; min-height: 180px; }
  </style>
</head>
<body>
  <h1>Raw WebSocket Echo</h1>
  <button id="connect">Connect</button>
  <button id="close" disabled>Close</button>
  <p>
    <input id="message" value="hello" aria-label="Message">
    <button id="send" disabled>Send</button>
  </p>
  <pre id="events" aria-live="polite"></pre>

  <script>
    const connectButton = document.querySelector("#connect");
    const closeButton = document.querySelector("#close");
    const sendButton = document.querySelector("#send");
    const input = document.querySelector("#message");
    const output = document.querySelector("#events");

    let socket = null;

    function log(message) {
      output.textContent += message + "\n";
    }

    connectButton.addEventListener("click", () => {
      const scheme = location.protocol === "https:" ? "wss:" : "ws:";
      const url = scheme + "//" + location.host + "/ws/echo";
      socket = new WebSocket(url);

      connectButton.disabled = true;

      socket.onopen = () => {
        log("OPEN");
        sendButton.disabled = false;
        closeButton.disabled = false;
      };

      socket.onmessage = event => {
        log("RECV " + event.data);
      };

      socket.onerror = () => {
        log("ERROR");
      };

      socket.onclose = event => {
        log("CLOSE " + event.code);
        connectButton.disabled = false;
        sendButton.disabled = true;
        closeButton.disabled = true;
        socket = null;
      };
    });

    sendButton.addEventListener("click", () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(input.value);
        log("SEND " + input.value);
      }
    });

    closeButton.addEventListener("click", () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.close(1000, "done");
      }
    });
  </script>
</body>
</html>
```

Sử dụng `textContent` để hiển thị phản hồi giúp message như `<script>` không bị diễn giải thành HTML. Nếu hiển thị thông điệp của người dùng khác, tránh ghép chúng vào `innerHTML` khi chưa xử lý an toàn.

### 5.6. Cách chạy và quan sát

Từ thư mục chứa `build.gradle`, cài JDK 17+ và Gradle phù hợp, chạy:

```bash
gradle bootRun
```

Nếu đã tạo Gradle Wrapper, dùng `./gradlew bootRun` (Unix/macOS) hoặc `gradlew.bat bootRun` (Windows).

1. Mở `http://localhost:8080/` trên trình duyệt.
2. Nhấn **Connect**, quan sát `OPEN` và message `READY` được server gửi về.
3. Giữ input `hello` rồi nhấn **Send**.
4. Quan sát browser hiển thị `SEND hello` và `RECV ECHO:hello`.
5. Nhấn **Close**, quan sát `CLOSE 1000` trên browser và `CLOSED 1000` trong stdout của ứng dụng server khi callback close được xử lý.

**Các dòng ứng dụng dự kiến tạo ra tại UI, theo thứ tự thao tác trên** (log khởi động, timing mạng và event close có thể tạo thêm thông tin riêng):

```text
OPEN
RECV READY
SEND hello
RECV ECHO:hello
CLOSE 1000
```

Không phải các dòng trên đều là stdout của Java; đó là output từ vùng `<pre id="events">` của trang demo. Java chỉ in `CLOSED 1000` khi đóng bình thường. Nếu handshake lỗi hoặc khác origin, bạn có thể thấy `ERROR`/`CLOSE 1006` ở trình duyệt; 1006 là trạng thái trình duyệt báo mất kết nối, không phải close frame được gửi bởi server.

### 5.7. Request thật đi qua các thành phần nào?

Trong lần nhấn **Connect**:

```text
new WebSocket("ws://localhost:8080/ws/echo")
  -> browser gửi HTTP Upgrade
  -> Tomcat nhận kết nối
  -> DispatcherServlet tìm mapping /ws/echo
  -> Spring handshake + Servlet WebSocket upgrade
  -> HTTP 101
  -> EchoTextWebSocketHandler.afterConnectionEstablished
  -> session.sendMessage("READY")
  -> browser.onmessage nhận READY
```

Trong lần nhấn **Send**:

```text
browser.socket.send("hello")
  -> WebSocket text frame trên kết nối hiện hữu
  -> EchoTextWebSocketHandler.handleTextMessage
  -> message.getPayload() == "hello"
  -> session.sendMessage(TextMessage("ECHO:hello"))
  -> browser.onmessage nhận "ECHO:hello"
```

Sau khi upgrade, **không có thêm Servlet HTTP GET cho mỗi frame**. Controller REST hoặc filter HTTP thông thường không được gọi lại mỗi khi WebSocket gửi một message. Nếu cần kiểm tra quyền cho từng lệnh trong raw WebSocket, đặt kiểm tra đó trong logic xử lý message hoặc tầng dịch vụ tương ứng.

## 6. HandshakeInterceptor, Origin và xác thực

Handshake bắt đầu bằng HTTP request nên có thể mang header, cookie, thông tin xác thực, query và origin. Spring cung cấp `HandshakeInterceptor` với hai callback `beforeHandshake(...)` và `afterHandshake(...)`.

Ví dụ cấu hình mở rộng (đây là **biến thể minh họa**, thay thế method đăng ký trong file `WebSocketConfig.java` ở trên nếu áp dụng):

```java
@Override
public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
    registry.addHandler(echoHandler, "/ws/echo")
            .addInterceptors(new HttpSessionHandshakeInterceptor())
            .setAllowedOrigins("https://app.example.com");
}
```

Import thêm `org.springframework.web.socket.server.support.HttpSessionHandshakeInterceptor`.

- `HttpSessionHandshakeInterceptor` có thể đưa các thuộc tính HTTP session vào map attributes của WebSocket session. Nó **không thay thế xác thực**.
- `setAllowedOrigins(...)` chỉ cho phép browser origin đã khai báo; khi vận hành thật phải đặt origin chính xác theo frontend được phép.
- `setAllowedOriginPatterns(...)` hỗ trợ pattern linh hoạt, nhưng phải giới hạn miền rõ ràng.
- Nếu application phục vụ cả trang HTML và WebSocket trên cùng host/port, chính sách same-origin mặc định phù hợp.
- Không coi `Origin` như một cơ chế authentication: non-browser client có thể tự đặt header này. Vẫn phải xác thực người gọi và kiểm tra quyền truy cập.

**Cẩn thận với ví dụ:** nếu thay config bằng `setAllowedOrigins("https://app.example.com")` trong lúc vẫn mở demo từ `http://localhost:8080/`, browser sẽ bị từ chối handshake vì origin không nằm trong danh sách. Muốn chạy demo local hãy giữ cấu hình ban đầu hoặc thêm rõ origin local phù hợp.

### 6.1. Khi cần HandshakeInterceptor tùy chỉnh

Có thể tạo interceptor kiểm tra trạng thái trước khi chấp nhận nâng cấp:

```java
public final class AttributeHandshakeInterceptor
        implements HandshakeInterceptor {

    @Override
    public boolean beforeHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler wsHandler,
            Map<String, Object> attributes) {

        attributes.put("connectedAt", java.time.Instant.now());
        return true;
    }

    @Override
    public void afterHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler wsHandler,
            Exception exception) {
        // Giải phóng tài nguyên hoặc ghi metric nếu cần.
    }
}
```

Đây là **đoạn minh họa cần đặt trong file cùng package và import**:
`org.springframework.web.socket.server.HandshakeInterceptor`,
`org.springframework.http.server.ServerHttpRequest`,
`org.springframework.http.server.ServerHttpResponse`,
`org.springframework.web.socket.WebSocketHandler`,
`java.util.Map`.

Đăng ký bằng `.addInterceptors(new AttributeHandshakeInterceptor())`. Sau handshake, lấy `session.getAttributes().get("connectedAt")` trong handler. Nếu `beforeHandshake` trả `false`, Spring không tiếp tục nâng cấp; response cần được cấu hình phù hợp khi từ chối.

**Bảo mật:** Nếu dùng cookie phiên để tự động xác thực WebSocket từ trình duyệt, cần kiểm tra Origin và authorization cho user/room/resource cụ thể, tránh Cross-Site WebSocket Hijacking. Trong môi trường reverse proxy, phải chuyển tiếp chính xác header Upgrade/Connection và WSS, đồng thời bảo đảm session/routing phù hợp.

## 7. Gửi đồng thời và quản lý session đúng cách

Thông thường session thuộc về một kết nối TCP/WebSocket. Nhiều thread cùng gọi `session.sendMessage(...)` có thể gây race hoặc lỗi với WebSocket container theo chuẩn Jakarta WebSocket. Spring khuyến nghị **đồng bộ việc gửi** nếu có nhiều nguồn phát.

Một cách là bọc session bằng `ConcurrentWebSocketSessionDecorator`:

```java
WebSocketSession safeSession =
        new ConcurrentWebSocketSessionDecorator(
                rawSession,
                10_000,       // giới hạn thời gian send, ms
                64 * 1024);   // giới hạn bộ đệm send, bytes
```

Import `org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator`. Đây là **snippet**, giả định `rawSession` đang có trong callback; không copy snippet vào file demo mà chưa thiết kế vòng đời registry phù hợp.

Decorator bảo đảm tại một thời điểm chỉ một thread thực hiện send trực tiếp; những send kế tiếp có thể vào buffer. Vượt giới hạn thời gian/kích thước buffer sẽ dẫn đến hành vi overflow/đóng session theo cấu hình. Nó **không phải message broker** và không tự đồng bộ session giữa các server node.

### 7.1. Broadcast registry

Nếu xây chat room, cần một cấu trúc dạng:

```java
private final Map<String, WebSocketSession> sessions =
        new ConcurrentHashMap<>();
```

Trong `afterConnectionEstablished`, thêm session; trong `afterConnectionClosed` và đường lỗi, xóa session; khi broadcast, kiểm tra session còn mở, quyền subscribe và thực hiện send tuần tự/qua decorator. Nếu dùng decorator, **đặt session đã bọc vào registry một lần** và dùng chính instance đó để gửi; không tạo decorator mới cho mỗi frame rồi tưởng rằng các lần send được đồng bộ.

**Đây là thiết kế bổ sung**, không cần cho chương trình echo runnable ở trên. Tránh broadcast về mọi session khi chưa xác định room/user/authorization, vì có thể rò dữ liệu giữa người dùng.

### 7.2. Backpressure và giới hạn tài nguyên

Raw Servlet WebSocket API là callback-based, không tự cung cấp reactive backpressure kiểu Reactor `Flux`. Để bảo vệ server cần thiết kế:

- Giới hạn kích thước inbound text/binary message và số kết nối.
- Giới hạn hàng đợi outbound, thời gian gửi, mức độ broadcast và tốc độ message của từng user.
- Đóng session chậm/không còn hợp lệ và dọn session registry.
- Đặt idle timeout/heartbeat theo container và load balancer.
- Hạn chế log payload nhạy cảm, validate message schema và kiểm tra phân quyền ở **mỗi lệnh quan trọng**.

Giới hạn `payload.length() > 1024` trong demo chỉ minh họa kiểm tra ứng dụng; message lớn có thể bị container từ chối **trước khi tới callback**. Với Servlet container dùng Jakarta WebSocket, Spring có `ServletServerContainerFactoryBean` để chỉnh buffer và timeout:

```java
@Bean
ServletServerContainerFactoryBean webSocketContainer() {
    ServletServerContainerFactoryBean container =
            new ServletServerContainerFactoryBean();
    container.setMaxTextMessageBufferSize(8192);
    container.setMaxBinaryMessageBufferSize(8192);
    return container;
}
```

Import `org.springframework.context.annotation.Bean` và `org.springframework.web.socket.server.standard.ServletServerContainerFactoryBean`. Đây là cấu hình tùy chọn đặt trong `@Configuration`; lựa chọn kích cỡ/timeout cần cân đối với payload thật và loại Servlet container đang chạy.

## 8. Raw WebSocket so với STOMP trên WebSocket

Bài đang học trực tiếp xử lý `TextMessage`. Khi client gửi chuỗi `hello`, handler hiểu theo quy ước của ứng dụng và tự gửi `ECHO:hello`. Spring **không tự thêm destination, subscription hay broker** trong cách đăng ký `registry.addHandler(echoHandler, "/ws/echo")`.

STOMP là giao thức tầng ứng dụng có lệnh như `CONNECT`, `SUBSCRIBE`, `SEND` và destination. Khi xây STOMP over WebSocket bằng Spring, thường cấu hình `@EnableWebSocketMessageBroker`, `StompEndpointRegistry` và message broker. Client STOMP gửi frame có headers/body theo chuẩn STOMP, không chỉ raw text tùy ý.

| Đặc điểm | Raw WebSocketHandler | STOMP over WebSocket |
| --- | --- | --- |
| Đăng ký endpoint | `WebSocketConfigurer.registerWebSocketHandlers` | `WebSocketMessageBrokerConfigurer.registerStompEndpoints` |
| Nhận dữ liệu | Callback `handleTextMessage` hoặc `handleMessage` | Broker/messaging routing và `@MessageMapping` |
| Định dạng message | Ứng dụng tự định nghĩa | STOMP frame có command và headers |
| Broadcast | Tự quản lý session/room/queue | Có cơ chế broker destination |
| Phù hợp | Echo, protocol riêng, data stream tùy biến | Chat/pub-sub có destination và subscription |

**Đừng ghép nhầm:** Một client cấu hình STOMP sẽ không tự giao tiếp đúng với echo handler raw nếu server không có logic hiểu frame STOMP. Ngược lại, browser WebSocket raw gửi chuỗi `hello` không thay thế lệnh `SEND` STOMP hợp lệ.

## 9. Lỗi thực tế và cách chẩn đoán

### 9.1. Handshake thất bại, không vào handleTextMessage

Kiểm tra lần lượt:

1. URL có đúng `/ws/echo` không, có sai port/context-path/reverse proxy không?
2. Client đang dùng `ws://` với HTTP và `wss://` với HTTPS đúng không?
3. `@EnableWebSocket` và `WebSocketConfigurer` có nằm trong component scan không?
4. Trên Servlet stack đã có websocket support từ container và dependency đúng chưa?
5. Browser `Origin` có được policy cho phép không?
6. HTTP auth/filter/proxy có chặn GET Upgrade hoặc bỏ `Connection/Upgrade` header không?
7. Có controller route, servlet mapping hoặc endpoint khác chiếm cùng đường dẫn không?

Trong DevTools → Network → WS, handshake thành công thường hiển thị **101 Switching Protocols**. Nếu nhận 400/401/403/404/500, phân biệt rõ **lỗi trước upgrade** với **close code sau upgrade**.

### 9.2. Kết nối thành công nhưng không nhận dữ liệu

- Client chỉ tạo `new WebSocket(...)` mà chưa gọi `send(...)`.
- Handler không override đúng `handleTextMessage(WebSocketSession, TextMessage)`.
- Server gửi phản hồi nhầm session hoặc đã đóng session.
- Client hiển thị message trước khi đăng ký `onmessage` (nên đặt callback ngay sau khi tạo đối tượng).
- Message là binary nhưng handler chỉ nhận text.
- Việc gửi từ nhiều threads làm xung đột. Dùng cơ chế serialize send.
- Client đóng tab hay proxy ngắt kết nối vì idle timeout.

### 9.3. Hiểu sai scope và lifecycle

Không bao giờ giữ một `WebSocketSession` trong field mutable chung như `currentSession` của singleton handler để đại diện toàn bộ người dùng. Một người reconnect sẽ nhận session mới, và session cũ có thể đóng bất kỳ lúc nào. Với broadcast registry phải dọn lifecycle, không giữ session dead vô hạn.

### 9.4. Nhầm lỗi HTTP với lỗi WebSocket

- HTTP 101 = handshake đã upgrade.
- WebSocket close 1000 = đóng bình thường.
- Close 1009 = message quá lớn.
- Close 1011 = server error.
- Browser có thể báo 1006 khi mất kết nối bất thường; 1006 không phải mã close frame gửi ra trên dây.

Không trả JSON HTTP 404 từ `handleTextMessage` sau khi đã nâng cấp kết nối; muốn biểu diễn lỗi nghiệp vụ dùng message schema có mã lỗi của ứng dụng hoặc đóng WebSocket theo hợp đồng.

### 9.5. Quên bảo mật hoặc coi Origin là xác thực

Allowed origins là một lớp bảo vệ cho browser handshake, không thay cho authentication. Kết nối WebSocket có thể sống dài sau khi quyền người dùng thay đổi, nên cân nhắc xác minh session, token expiry, quyền vào room, giới hạn tần suất và việc thu hồi kết nối. Không đưa token vào query nếu có thể tránh vì URL hay bị log; thiết kế phương thức xác thực hợp lý cho browser (cookie/session qua HTTPS với CSRF/origin protections hoặc cơ chế token được xem xét kỹ).

## 10. Bài tập tự luyện

**Bài tập 1 — Theo dõi lifecycle:** Chạy demo, kết nối từ hai tab trình duyệt. Mỗi tab nhận `READY`. Gửi `hello A` ở tab A. Giải thích vì sao tab B không nhận `ECHO:hello A`. Đóng tab A và xem callback close.

**Bài tập 2 — Thêm command:** Trong `handleTextMessage`, nếu payload đúng `PING` thì trả `PONG` theo protocol của ứng dụng; với các chuỗi khác tiếp tục `ECHO:...`. Lưu ý đây là **text message ứng dụng**, không phải WebSocket protocol-level Ping/Pong control frame.

**Bài tập 3 — Kiểm tra giới hạn:** Gửi đoạn text dài hơn 1.024 ký tự Java nhưng dưới giới hạn frame của container. Dự đoán browser nhận close code nào. Thay đổi cấu hình buffer của container và phân tích tại sao lỗi có thể diễn ra trước callback.

**Bài tập 4 — Origin và handshake:** Thêm `setAllowedOrigins("https://app.example.com")` rồi thử lại trang `http://localhost:8080/`. Dự đoán nguyên nhân handshake bị từ chối. Khôi phục cấu hình same-origin cho demo trước khi tiếp tục.

**Bài tập 5 — Thiết kế broadcast:** Không cần viết toàn bộ code, hãy mô tả nơi thêm/xóa session trong lifecycle callbacks, nơi kiểm tra quyền nhận message và lý do phải đồng bộ `sendMessage` khi nhiều producer cùng phát tin.

## Ghi nhớ trọng tâm

- `WebSocketHandler` là hợp đồng các callback lifecycle/message.
- `TextWebSocketHandler` là lớp cơ sở thích hợp để xử lý raw WebSocket **text frames** trên Servlet stack.
- `@EnableWebSocket` + `WebSocketConfigurer` + `WebSocketHandlerRegistry.addHandler(...)` đăng ký URL handshake; hạ tầng Servlet và Spring đảm nhận phần nâng cấp kết nối.
- Sau HTTP 101, xử lý dữ liệu bằng WebSocket frames, không đi qua REST controller cho từng message.
- `WebSocketSession` gắn với một kết nối, handler bean có thể phục vụ nhiều người dùng.
- Khi cần broadcast, xác thực, bảo vệ tài nguyên, đa luồng hoặc nhiều instance server, phải bổ sung quản lý lifecycle, quyền truy cập và đồng bộ send.
- Raw WebSocket và STOMP sử dụng cách cấu hình/lớp xử lý khác nhau; chúng không thể thay thế lẫn nhau nếu chưa thống nhất protocol.

## Tài liệu tham khảo

- Spring Framework — WebSocket API (Servlet): https://docs.spring.io/spring-framework/reference/web/websocket/server.html
- Spring Framework — WebSockets trên Servlet stack: https://docs.spring.io/spring-framework/reference/web/websocket.html
- Spring Framework — `WebSocketHandler` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/socket/WebSocketHandler.html
- Spring Framework — `TextWebSocketHandler` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/socket/handler/TextWebSocketHandler.html
- Spring Framework — `ConcurrentWebSocketSessionDecorator`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/socket/handler/ConcurrentWebSocketSessionDecorator.html
- Spring Boot — WebSockets: https://docs.spring.io/spring-boot/3.3/reference/messaging/websockets.html

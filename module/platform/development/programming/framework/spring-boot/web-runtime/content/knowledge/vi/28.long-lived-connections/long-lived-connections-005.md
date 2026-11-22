# Cấu hình WebSocket trong ứng dụng Servlet

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** Kết nối dài

## 1. Bài toán và mục tiêu học tập

Một ứng dụng Servlet Spring Boot đã có REST API trả JSON theo cơ chế request–response, nhưng nay cần hỗ trợ màn hình cập nhật trạng thái đơn hàng, chat hoặc dashboard gần thời gian thực. Client phải nhận dữ liệu **ngay khi server có sự kiện** và có thể gửi thông điệp ngược lại mà không mở HTTP request mới cho từng sự kiện.

**WebSocket** là giao thức full-duplex (RFC 6455), khởi tạo qua một HTTP handshake rồi duy trì kênh trao đổi hai chiều trên một kết nối. Với Spring Boot Servlet stack, ta có thể sử dụng **Spring Framework WebSocket API** để ánh xạ một URL như **/ws/echo** tới **WebSocketHandler**, hoặc dùng lớp messaging cao hơn như **STOMP over WebSocket**.

Bài này tập trung vào **cấu hình WebSocket trong ứng dụng Servlet (Spring MVC, embedded Tomcat/Jetty/Undertow)**: dependency, cấu hình handler, handshake, allowed origins, server limits, vòng đời kết nối, bảo mật, proxy, deployment và test. Đây không phải hướng dẫn về WebFlux reactive stack.

Sau bài, bạn sẽ:

1. Giải thích vì sao request ban đầu dùng HTTP nhưng các thông điệp sau đó không còn là các request **@GetMapping** thông thường.
2. Biết khi nào dùng **spring-boot-starter-websocket**, **@EnableWebSocket**, **WebSocketConfigurer** và **TextWebSocketHandler**.
3. Chạy ví dụ Java 17+ trả echo qua **ws://localhost:8080/ws/echo** với một trang web kiểm thử và Java standard-library client.
4. Cấu hình **ServletServerContainerFactoryBean** để điều chỉnh buffer/idle timeout của Jakarta WebSocket container, đồng thời có validation ở cấp thông điệp.
5. Nhận diện yêu cầu **Origin**, **ws/wss**, xác thực handshake và authorization ở cấp message.
6. Thiết lập đường qua reverse proxy, giám sát connection lifecycle, reconnect/heartbeat và giới hạn tài nguyên cho production.
7. Phân biệt **raw WebSocket**, **STOMP**, **SockJS**, **SSE** và **WebFlux** để chọn công cụ đúng phạm vi.

## 2. WebSocket khác HTTP request–response như thế nào?

Ở REST truyền thống, client gửi mỗi request và server trả một response:

~~~text
Browser                              Spring MVC
   | GET /api/orders/42                  |
   |------------------------------------>|
   |<------------------- 200 JSON -------|
   |
   | GET /api/orders/42 (poll tiep)      |
   |------------------------------------>|
   |<------------------- 200 JSON -------|
~~~

Với WebSocket, client làm HTTP handshake một lần, sau đó hai chiều cùng có thể chủ động phát thông điệp:

~~~text
Browser                               Servlet container + WebSocketHandler
   | GET /ws/echo HTTP/1.1                 |
   | Upgrade: websocket                   |
   |------------------------------------->|
   |<---------- 101 Switching Protocols --|
   |                                      |
   |--- WebSocket TEXT: "ping" ---------->|
   |<-- WebSocket TEXT: "echo:ping" -------|
   |                                      |
   |<-- WebSocket TEXT: server event ------|
   |--- WebSocket CLOSE ----------------->|
~~~

Sau **101 Switching Protocols**, cùng TCP connection được dùng để trao đổi **WebSocket frames** (text, binary, ping, pong, close), không phải mỗi message lại tạo một HTTP GET hoặc POST. WebSocket có thứ tự truyền dữ liệu trên connection và không tự định nghĩa semantics như "gửi tin vào phòng chat" hay "nhận tài khoản nào": **ứng dụng phải tự đặt message protocol hoặc chọn STOMP**.

### Khi nào WebSocket đáng dùng?

| Yêu cầu | WebSocket | Lựa chọn có thể đơn giản hơn |
| --- | --- | --- |
| Hai chiều liên tục, tần suất cao, tương tác gần thời gian thực | Phù hợp | — |
| Server chỉ đẩy thông báo một chiều | Có thể dùng | **Server-Sent Events (SSE)** có thể đủ |
| Kiểm tra trạng thái vài phút một lần | Có thể phức tạp không cần thiết | Polling HTTP + caching |
| API CRUD thông thường | Không phải lựa chọn mặc định | REST request–response |
| Chat nhiều người, pub/sub, định tuyến theo destination | WebSocket với **STOMP** hoặc messaging layer khác | Broker/message infrastructure |
| Client hoặc proxy không hỗ trợ Upgrade/connection dài | Có thể không dùng trực tiếp | HTTP streaming, long polling hoặc SockJS fallback |

**Không đồng nhất WebSocket với HTTP/2 multiplexing.** HTTP/2 tối ưu nhiều request/response bằng streams trên connection; WebSocket là kênh thông điệp hai chiều có framing riêng. Với luồng HTTP/1.1 thông thường, WebSocket bắt đầu bằng Upgrade; có chuẩn **RFC 8441 extended CONNECT** cho WebSocket trên HTTP/2, nhưng nó đòi hỏi cả hai đầu/hops hỗ trợ và không nên giả định embedded Servlet app hay proxy luôn dùng cách đó.

## 3. HTTP handshake: điểm chuyển từ Servlet request sang WebSocket

Một WebSocket handshake thông dụng trên HTTP/1.1 trông như sau:

~~~http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: http://localhost:8080
~~~

Server chấp nhận có thể trả:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
~~~

Các giá trị **Sec-WebSocket-Key/Sec-WebSocket-Accept** trong ví dụ là cặp mẫu từ giao thức, không phải mật khẩu hay token xác thực. Sau phản hồi 101, client/server trao đổi WebSocket frames.

**Các điểm cần phân biệt:**

- **Upgrade: websocket** yêu cầu chuyển giao thức trên HTTP/1.1; header **Connection: Upgrade** mang tính hop-by-hop và có thể cần proxy forward đúng.
- **Sec-WebSocket-Version: 13** là version giao thức WebSocket phổ biến theo RFC 6455.
- **Sec-WebSocket-Key/Accept** phục vụ xác minh tính nhất quán của WebSocket handshake, **không xác thực danh tính người dùng**.
- **Origin** của browser thể hiện origin trang khởi tạo socket; thường là **http(s)://...**, không phải chuỗi **ws://...**. Server cần tự kiểm tra origin được phép.
- **101 Switching Protocols** không phải một HTTP 200 với body JSON. Sau handshake, ứng dụng làm việc với **WebSocketSession** và **WebSocketMessage**.
- Nếu handshake không hợp lệ hoặc bị cấm, server có thể trả **400/403/404/401**, lỗi HTTP khác hoặc đóng kết nối tùy layer. Browser thường chỉ thông báo WebSocket connection failed; để biết nguyên nhân cần xem Network/WS, access log và proxy.

Trên **HTTPS**, browser thường kết nối qua **wss://**, tức WebSocket trên TLS. Với URL **ws://**, hop đó không được TLS mã hóa. Không biến một kết nối WebSocket công khai thành an toàn chỉ bằng việc thêm chữ wss vào frontend nếu server hoặc proxy chưa có TLS hợp lệ.

## 4. Servlet container và Spring Framework làm những gì?

Trong ứng dụng Spring Boot Servlet:

~~~text
Browser or Java WebSocket client
      |
      v
HTTP connector (Tomcat/Jetty/Undertow)
      |
      v
Servlet filters / security cho handshake HTTP
      |
      v
Spring WebSocket handshake mapping
      |
      v
RequestUpgradeStrategy + Jakarta WebSocket ServerContainer
      |
      v
WebSocketHandler / WebSocketSession
      |
      +--> afterConnectionEstablished
      +--> handleTextMessage / handleBinaryMessage
      +--> handleTransportError
      +--> afterConnectionClosed
~~~

**Spring Boot** cung cấp WebSocket auto-configuration cho các embedded Servlet containers được hỗ trợ, trong đó **Tomcat** là mặc định khi dùng spring-boot-starter-web. **spring-boot-starter-websocket** cung cấp dependency cần thiết để dùng tính năng WebSocket của Spring trên MVC. Container xử lý kết nối/upgrade, còn Spring WebSocket hỗ trợ **WebSocketHandler**, URL mapping, handshake integration và khung lập trình thuận tiện.

**@EnableWebSocket** bật cấu hình WebSocket programmatic ở Spring MVC. **WebSocketConfigurer#registerWebSocketHandlers** ánh xạ URL handshake tới handler. Không cần tự đăng ký một Servlet riêng hoặc viết **@GetMapping("/ws/echo")** để trả 101 thủ công.

Một số lựa chọn API:

| Phương án | Thư viện/API | Ý nghĩa |
| --- | --- | --- |
| Raw Spring WebSocket | **@EnableWebSocket**, **WebSocketConfigurer**, **WebSocketHandler/TextWebSocketHandler** | Tự định nghĩa thông điệp, event và routing. |
| STOMP messaging | **@EnableWebSocketMessageBroker**, **WebSocketMessageBrokerConfigurer**, **@MessageMapping** | Định tuyến publish/subscribe bằng STOMP destinations. |
| Jakarta WebSocket trực tiếp | **@ServerEndpoint**, Jakarta WebSocket API | Một đường đăng ký endpoint khác, không đồng nhất Spring WebSocketHandler. |
| Reactive WebSocket | **WebFlux WebSocketHandler**, **HandlerMapping**, **WebSocketService/Session** reactive | Dành cho WebFlux/Reactive stack. |

**Không trộn lẫn cấu hình raw @EnableWebSocket với STOMP broker như thể hai API là một.** Chọn một style theo nhu cầu, hoặc ánh xạ **hai endpoint tách biệt** nếu hệ thống cần cả hai.

## 5. Dependency và project Spring Boot 3.x

Bài demo dùng **Spring Boot 3.3.13, Java 17+ và Maven**. Đó là phiên bản ổn định thuộc nhánh 3.3 phục vụ tính tương thích của ví dụ; dự án mới cần lựa chọn bản Spring Boot còn được bảo trì và sử dụng bản vá bảo mật hiện hành theo môi trường triển khai.

Cấu trúc:

~~~text
servlet-websocket-demo/
  pom.xml
  src/main/
    java/com/example/wsdemo/
      ServletWebSocketDemoApplication.java
    resources/
      application.properties
      static/index.html
  WebSocketProbe.java
~~~

**pom.xml** đầy đủ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>servlet-websocket-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
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

**spring-boot-starter-websocket** mang các module Spring WebSocket/Spring Messaging và tích hợp embedded server phù hợp. Ta để cả **spring-boot-starter-web** trong pom cho rõ ứng dụng này chạy **Servlet Spring MVC**. Không dùng **spring-boot-starter-webflux** trong demo, không thêm các class Reactor Netty chỉ để nhận WebSocket message.

**application.properties** tại **src/main/resources/application.properties**:

~~~properties
server.port=8080
spring.application.name=servlet-websocket-demo

# Khong co server.websocket.enabled=true chung cho moi endpoint;
# handler duoc dang ky qua @EnableWebSocket + WebSocketConfigurer.
~~~

**Điểm cần ghi nhớ:** Spring Boot hỗ trợ container WebSocket qua auto-configuration, nhưng vẫn cần **đăng ký endpoint/handler**. Không có một property chung mà chỉ bật lên là tự xuất hiện route /ws/echo.

## 6. Ví dụ Java 17+ chạy được: endpoint echo qua WebSocket

Tạo file **src/main/java/com/example/wsdemo/ServletWebSocketDemoApplication.java**:

~~~java
package com.example.wsdemo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import org.springframework.web.socket.server.standard.ServletServerContainerFactoryBean;

@SpringBootApplication
public class ServletWebSocketDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletWebSocketDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableWebSocket
class WebSocketConfiguration implements WebSocketConfigurer {

    private final EchoWebSocketHandler handler;

    WebSocketConfiguration(EchoWebSocketHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/echo")
                .setAllowedOrigins(
                        "http://localhost:8080",
                        "http://localhost:5173");
    }

    @Bean
    ServletServerContainerFactoryBean webSocketContainer() {
        ServletServerContainerFactoryBean container =
                new ServletServerContainerFactoryBean();
        container.setMaxTextMessageBufferSize(8 * 1024);
        container.setMaxBinaryMessageBufferSize(8 * 1024);
        container.setMaxSessionIdleTimeout(60_000L);
        return container;
    }
}

@Component
class EchoWebSocketHandler extends TextWebSocketHandler {

    private static final Logger logger =
            LoggerFactory.getLogger(EchoWebSocketHandler.class);

    private static final int MAX_APP_TEXT_BYTES = 1024;

    @Override
    public void afterConnectionEstablished(WebSocketSession session)
            throws IOException {
        logger.info("WebSocket opened: {}", session.getId());
        session.sendMessage(new TextMessage("ready"));
    }

    @Override
    protected void handleTextMessage(
            WebSocketSession session, TextMessage message)
            throws IOException {

        String payload = message.getPayload();
        int bytes = payload.getBytes(StandardCharsets.UTF_8).length;

        if (bytes > MAX_APP_TEXT_BYTES) {
            session.close(CloseStatus.TOO_BIG_TO_PROCESS);
            return;
        }

        session.sendMessage(new TextMessage("echo:" + payload));
    }

    @Override
    public void handleTransportError(
            WebSocketSession session, Throwable exception)
            throws Exception {
        logger.warn("WebSocket transport error: {}",
                exception.toString());
        if (session.isOpen()) {
            session.close(CloseStatus.SERVER_ERROR);
        }
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session, CloseStatus status) {
        logger.info("WebSocket closed: id={}, code={}",
                session.getId(), status.getCode());
    }
}
~~~

### 6.1. Vì sao mã có thể chạy?

- Chỉ **ServletWebSocketDemoApplication** là public class, đúng tên file. Hai class khác package-private cùng package, được component scan.
- **@EnableWebSocket** kích hoạt WebSocket configuration của Spring MVC.
- **WebSocketConfiguration** nhận bean **EchoWebSocketHandler** bằng constructor; **@Component** giúp Spring tạo handler theo dependency injection.
- **registry.addHandler(handler, "/ws/echo")** tạo endpoint handshake.
- **setAllowedOrigins** chỉ cho phép browser WebSocket kết nối từ **http://localhost:8080** hoặc frontend dev **http://localhost:5173**. Đây là allowlist để thử local, phải thay bằng domain hợp lệ khi triển khai HTTPS.
- **ServletServerContainerFactoryBean** cấu hình server container trên embedded Tomcat/Jakarta WebSocket: text/binary message buffer 8 KiB và idle timeout 60.000 ms. Mức này là giá trị **demo**, không phải lựa chọn tối ưu cho mọi ứng dụng.
- **TextWebSocketHandler** xử lý text message; binary messages không được ứng dụng demo hỗ trợ và Spring sẽ xử lý theo semantics của class.
- Khi kết nối được thiết lập, server gửi **ready**. Khi client gửi **ping**, server trả **echo:ping**.
- Độ dài tối đa application cho text payload là **1.024 bytes UTF-8**, khác buffer 8 KiB của container. Nếu vượt limit, server chủ động đóng bằng status **1009 (TOO_BIG_TO_PROCESS)**. Trong một số tình huống container có thể từ chối trước khi handler nhìn thấy nếu vượt container limit.
- Handler chỉ thực hiện một lần gửi trực tiếp tương ứng một lần nhận; không có nhiều async producers cùng đẩy vào một session. Trong production broadcast hoặc fan-out, cần thêm cơ chế điều phối **concurrent writes**, buffer và slow consumer control.
- **Logger** chỉ ghi ID phiên và code đóng, không in payload hay cookie/token. Trong production cũng cần tránh ghi dữ liệu nhạy cảm hoặc token vào logs.

### 6.2. Những lớp Java API cần hiểu

**WebSocketHandler** là interface cốt lõi; các callback được gọi bởi Spring/container theo vòng đời kết nối. **TextWebSocketHandler** là base class dễ dùng khi chỉ cần text.

| Callback/phương thức | Khi nào xảy ra? | Dùng để làm gì? |
| --- | --- | --- |
| **afterConnectionEstablished(WebSocketSession)** | Sau handshake thành công, session WebSocket đã được tạo | Gửi initial event, đăng ký connection, khởi tạo state tạm. |
| **handleTextMessage(session, TextMessage)** | Khi có text message | Validate message và xử lý command/event. |
| **handleBinaryMessage(...)** | Khi có binary message, nếu handler hỗ trợ | Dùng **BinaryWebSocketHandler** hoặc tự triển khai theo yêu cầu. |
| **handleTransportError(...)** | Có lỗi vận chuyển | Log an toàn, đóng session, cleanup phù hợp. |
| **afterConnectionClosed(session, CloseStatus)** | Kết nối đóng | Release connection-specific resources và registry. |
| **session.sendMessage(new TextMessage(...))** | Khi cần gửi message | Ghi một WebSocket text message trên session. |
| **session.close(CloseStatus.XXX)** | Khi muốn kết thúc kết nối | Gửi close frame khi thực hiện được. |

Callback đóng có thể xảy ra vì client chủ động close, server timeout, proxy đóng hoặc lỗi network. Trong trường hợp mất mạng bất ngờ, application không thể đảm bảo nhận một clean close handshake; cần cleanup timeout/lifecycle linh hoạt.

**WebSocketSession không phải HttpSession**. WebSocketSession đại diện một kết nối đã upgrade, còn HttpSession là state HTTP server-side gắn cookie session. Spring có thể chuyển thông tin xác thực hoặc copy attribute qua **HandshakeInterceptor**, nhưng hai object này có vòng đời và ý nghĩa riêng.

## 7. Trang browser để thử endpoint

Tạo **src/main/resources/static/index.html**. Spring Boot Servlet có thể phục vụ static file này tại **http://localhost:8080/** khi cấu hình static resources mặc định chưa bị thay đổi.

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Servlet WebSocket Echo</title>
</head>
<body>
  <h1>WebSocket Echo</h1>
  <input id="message" value="ping" aria-label="Thông điệp">
  <button id="send" type="button">Gửi</button>
  <button id="disconnect" type="button">Đóng</button>
  <pre id="log" aria-live="polite"></pre>

  <script>
    const input = document.querySelector("#message");
    const logArea = document.querySelector("#log");
    const append = (value) => {
      logArea.textContent += value + "\n";
    };

    const scheme = location.protocol === "https:" ? "wss://" : "ws://";
    const socketUrl = scheme + location.host + "/ws/echo";
    const socket = new WebSocket(socketUrl);

    socket.addEventListener("open", () => append("open"));
    socket.addEventListener("message", (event) =>
      append("received: " + event.data));
    socket.addEventListener("error", () => append("transport error"));
    socket.addEventListener("close", (event) =>
      append("closed: " + event.code));

    document.querySelector("#send").addEventListener("click", () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(input.value);
      } else {
        append("not open");
      }
    });

    document.querySelector("#disconnect").addEventListener("click", () => {
      socket.close(1000, "done");
    });
  </script>
</body>
</html>
~~~

Mở trang, console/log có thể hiển thị:

~~~text
open
received: ready
received: echo:ping
~~~

**open** và **received: ready** có thể đến gần nhau, thứ tự các sự kiện trên connection được giữ, nhưng thời điểm UI hiện phụ thuộc browser. Nhấn **Gửi** với giá trị ping để nhận echo:ping; nhấn Đóng sẽ có code đóng, thông thường là **1000** nếu close handshake hoàn tất.

**Không cần viết fetch POST/GET cho từng message.** Browser **WebSocket API** có **send**, **message**, **open**, **close**, **error**. Việc dùng **location.protocol** để chọn ws/wss giúp trang chạy phù hợp khi chuyển từ local HTTP sang production HTTPS (giả định proxy đã cung cấp WebSocket endpoint qua wss).

**Cảnh báo về cross-origin:** nếu mở HTML từ địa chỉ khác, ví dụ **http://localhost:3000**, origin này **không nằm trong allowlist** của demo. Đừng đổi allowedOrigins thành **"*"** để chữa một lỗi chưa hiểu; thêm origin thực sự được tin cậy, hoặc chạy frontend trên 5173 như cấu hình.

## 8. Chạy ứng dụng và test bằng Java 17 standard library

### 8.1. Build và khởi động

Tại thư mục **servlet-websocket-demo**:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

Giữ server chạy ở terminal thứ nhất. Nếu port 8080 đã bị chiếm, đổi server.port và truy cập đúng URL; trong trường hợp đó cũng cần cập nhật **allowedOrigins** cho trang phục vụ từ origin mới.

### 8.2. Java client WebSocket không cần thư viện ngoài

Java 17 có **java.net.http.HttpClient** và **java.net.http.WebSocket**. Tạo file **WebSocketProbe.java** ở thư mục gốc project (ngoài src/main/java):

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

public class WebSocketProbe {
    public static void main(String[] args) throws Exception {
        CompletableFuture<String> echo = new CompletableFuture<>();

        WebSocket.Listener listener = new WebSocket.Listener() {
            private final StringBuilder parts = new StringBuilder();

            @Override
            public void onOpen(WebSocket socket) {
                socket.request(1);
            }

            @Override
            public CompletionStage<?> onText(
                    WebSocket socket, CharSequence text, boolean last) {
                parts.append(text);
                if (last) {
                    String message = parts.toString();
                    parts.setLength(0);
                    if (message.startsWith("echo:")) {
                        echo.complete(message);
                    }
                }
                socket.request(1);
                return CompletableFuture.completedFuture(null);
            }

            @Override
            public void onError(WebSocket socket, Throwable error) {
                echo.completeExceptionally(error);
            }
        };

        WebSocket socket = HttpClient.newHttpClient()
                .newWebSocketBuilder()
                .buildAsync(
                        URI.create("ws://localhost:8080/ws/echo"),
                        listener)
                .join();

        socket.sendText("ping", true).join();
        System.out.println(echo.get(5, TimeUnit.SECONDS));
        socket.sendClose(WebSocket.NORMAL_CLOSURE, "done").join();
    }
}
~~~

Biên dịch/chạy ở terminal thứ hai:

~~~bash
javac WebSocketProbe.java
java WebSocketProbe
~~~

**Stdout kỳ vọng chính xác** khi server demo đang chạy và không có proxy:

~~~text
echo:ping
~~~

**Vì sao test này có ý nghĩa?**

- Không cần **wscat**, Node.js hay công cụ bên ngoài. Java standard-library client tự làm handshake và WebSocket framing.
- **onOpen** cấp demand bằng **request(1)** để listener nhận messages.
- **onText** ghép các fragments khi **last=true**; nó bỏ qua thông điệp khởi đầu **ready**, chỉ hoàn thành future khi nhận **echo:**.
- **sendText("ping", true)** gửi text message hoàn chỉnh.
- **CompletableFuture.get(5, SECONDS)** cho một giới hạn chờ kiểm thử, giúp nhận biết server không trả lời; đây không phải cấu hình global timeout của service production.
- Client Java không phải browser nên **có thể không gửi Origin**. Việc Java client kết nối thành công không tự chứng minh browser từ một origin không được phép sẽ được chấp nhận.
- **sendClose** gửi close frame chuẩn. Trong môi trường network thất bại, close handshake có thể không hoàn tất như test thành công.

### 8.3. Không kiểm raw WebSocket chỉ bằng curl GET

Gửi một HTTP GET bình thường tới **/ws/echo**:

~~~bash
curl -i http://localhost:8080/ws/echo
~~~

không thực hiện WebSocket handshake hợp lệ, vì thiếu các header Upgrade/Sec-WebSocket-* cần thiết. Có thể nhận **400** hoặc phản hồi lỗi khác. Đừng kết luận endpoint hỏng chỉ vì curl GET không trả JSON.

Bạn có thể dùng **curl** để kiểm một phần HTTP handshake headers, nhưng sau **101** nó không phải giải pháp tiện nhất để gửi/đọc WebSocket frames trong demo. Dùng browser DevTools WebSocket frames hoặc **WebSocketProbe** ở trên sẽ đáng tin cậy hơn.

## 9. Allowed origins: kiểm nguồn trang, không phải xác thực người dùng

Mã demo đăng ký:

~~~java
registry.addHandler(handler, "/ws/echo")
        .setAllowedOrigins(
                "http://localhost:8080",
                "http://localhost:5173");
~~~

**Origin** trong browser WebSocket handshake nói URL trang web khởi tạo kết nối. Với một trang tại **https://app.example.test** mở **wss://api.example.test/ws/echo**, Origin thường là **https://app.example.test**; không phải **wss://api.example.test**.

Spring WebSocket theo mặc định **hạn chế cross-origin WebSocket/SockJS request** (same-origin khi chưa mở thêm). Nếu frontend cần chạy từ một origin khác, thêm chính xác origin đó. Các API cũng có **setAllowedOriginPatterns(...)** cho những trường hợp cần pattern được kiểm soát; không phản chiếu ngẫu nhiên Origin từ client.

**Browser WebSocket không chịu CORS preflight OPTIONS giống fetch/xhr.** Browser gửi Origin trong handshake, và Spring kiểm allowed origins qua chính sách WebSocket. Đừng cho rằng **@CrossOrigin** trên một REST controller hoặc **CorsFilter** đã tự cấp phép WebSocket endpoint. Nếu có SockJS HTTP fallback, các transport HTTP của SockJS có yêu cầu CORS riêng, được Spring/SockJS xử lý theo cấu hình liên quan.

**Origin không chứng minh danh tính.** Một non-browser client có thể bỏ hoặc giả mạo Origin. Vì vậy allowedOrigins là bảo vệ chống nhiều tình huống **cross-site WebSocket hijacking** trong browser, **không thay authentication, authorization, CSRF/CSWSH defense-in-depth và validation ở cấp message**.

### Vì sao không dùng setAllowedOrigins("*")?

Một endpoint sử dụng cookie phiên có thể được browser mở từ trang của attacker nếu app cho phép mọi origin; sau handshake attacker có thể gửi/nhận messages trong ngữ cảnh credential đang có nếu không được bảo vệ. Dùng allowlist chặt, cookie attributes phù hợp, xác thực handshake, kiểm quyền và cân nhắc token chống CSWSH theo threat model.

Nếu dịch vụ là public anonymous chat thật sự, wildcard có thể là lựa chọn nghiệp vụ, nhưng cần rate limit, abuse controls và không dựa trên cookie nhạy cảm; đây không phải mặc định an toàn cho app có login.

## 10. Authentication và authorization qua WebSocket trong Servlet

**HTTP handshake vẫn đi qua Servlet filter chain và có thể được Spring Security bảo vệ.** Nếu ứng dụng đang dùng cookie/session authentication, trình duyệt có thể gửi cookie phù hợp ở handshake; Spring Security xác định Principal trong HTTP request, rồi Spring WebSocket có thể gắn identity đó với **WebSocketSession.getPrincipal()**.

Mô hình:

~~~text
Browser + session cookie
    |
    v
GET /ws/notifications Upgrade: websocket
    |
    v
Spring Security Servlet filters
    |
    +--> authenticated HTTP principal?
    |          |
    |          +--> No: reject handshake
    |          +--> Yes: proceed
    |
    v
WebSocket handshake -> WebSocketSession Principal
    |
    v
Each incoming message:
    handler/message-security checks action and resource scope
~~~

**Demo phần 6 cố ý không thêm Spring Security**, để tập trung WebSocket configuration và cho phép anonymous echo. Đừng mang endpoint anonymous đó nguyên xi vào ứng dụng có tài khoản và dữ liệu nhạy cảm.

### 10.1. Bảo vệ handshake bằng SecurityFilterChain

Đây là **đoạn cấu hình thay thế dành cho project có spring-boot-starter-security**, không nằm trong demo public echo ở phần 6. Ví dụ chỉ minh họa nguyên tắc bảo vệ đường handshake:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/ws/notifications").authenticated()
                    .anyRequest().permitAll())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

Imports tương ứng thuộc **org.springframework.security.web.SecurityFilterChain**, **org.springframework.security.config.annotation.web.builders.HttpSecurity**, **org.springframework.security.config.Customizer** và **org.springframework.context.annotation.Bean**. Cần có cơ chế login/session thực đã cấu hình; đoạn này không phải class độc lập.

Sau 101, Spring Security servlet filters **không chạy lại cho từng WebSocket text frame** như với từng HTTP request mới. Vì thế **handler hoặc messaging layer phải kiểm quyền cho mỗi command/message/subscription** khi cần. Không suy từ "đã login lúc connect" rằng user có quyền thao tác với mọi order ID trong payload.

### 10.2. Principal và HttpSessionHandshakeInterceptor

Có thể thêm **HttpSessionHandshakeInterceptor** của Spring:

~~~java
registry.addHandler(handler, "/ws/notifications")
        .addInterceptors(new HttpSessionHandshakeInterceptor())
        .setAllowedOrigins("https://app.example.test");
~~~

Đây là snippet cấu hình **thay thế trong WebSocketConfigurer** cho app đã có HTTP session; không chép vào demo echo nếu không cần. **HttpSessionHandshakeInterceptor** có thể copy attributes phù hợp từ HTTP session sang map attributes của WebSocketSession, hỗ trợ truy cập context sau handshake.

**Phân biệt:** copy HttpSession attributes **không phải xác thực lại mọi message** và không đảm bảo dữ liệu session trong WebSocket tự đồng bộ liên tục với HTTP session. Đừng copy token/PII không cần thiết; không tin role từ client message. Đối với Principal, ưu tiên thông tin authentication do Spring Security xác thực.

### 10.3. Browser không tự đặt Authorization tùy ý trong WebSocket constructor

Browser WebSocket API thông thường chỉ nhận **URL** và danh sách **subprotocols**; nó không cho JavaScript tự đặt arbitrary **Authorization: Bearer ...** header như fetch. Các cách xác thực phải được thiết kế riêng, ví dụ:

- **Session cookie** nếu là mô hình ứng dụng web same-site, kèm allowed origin, SameSite/Secure/HttpOnly phù hợp và chống CSWSH.
- **Short-lived, single-use connection ticket** được backend cấp theo luồng HTTPS đã xác thực, có TTL ngắn, audience và ràng buộc cần thiết; dùng một cơ chế handshake an toàn để truyền và xác thực ticket.
- **STOMP CONNECT headers** khi dùng messaging STOMP, kết hợp Spring Security messaging/channel interceptors theo mô hình phù hợp.
- **Native clients** có thể linh hoạt thêm headers qua thư viện tương ứng, nhưng không được suy rằng browser có cùng khả năng.

Không đặt access token dài hạn vào query string **/ws?token=...** mà không xét URL/access logs, analytics, browser history, referer exposure, rotation/replay và timeout. Không dùng **Sec-WebSocket-Protocol** như chỗ nhét token tùy ý nếu không có thiết kế subprotocol và xác thực tương thích; dễ lộ hoặc phá giao thức.

## 11. Cấu hình Jakarta Servlet WebSocket server container

Trong demo, bean:

~~~java
@Bean
ServletServerContainerFactoryBean webSocketContainer() {
    ServletServerContainerFactoryBean container =
            new ServletServerContainerFactoryBean();
    container.setMaxTextMessageBufferSize(8 * 1024);
    container.setMaxBinaryMessageBufferSize(8 * 1024);
    container.setMaxSessionIdleTimeout(60_000L);
    return container;
}
~~~

**ServletServerContainerFactoryBean** điều chỉnh **Jakarta WebSocket ServerContainer** có trong ServletContext. Đây là cách được Spring Framework hướng dẫn cho Jakarta WebSocket servers; server thay thế như Jetty có thể có cấu hình upgrade strategy và native container riêng, tùy version.

| Tùy chỉnh | Ý nghĩa | Cần lưu ý |
| --- | --- | --- |
| **setMaxTextMessageBufferSize(8192)** | Giới hạn/kích thước buffer text message của container | Không mặc định coi là limit nghiệp vụ cho mọi dạng stream; handler nên validate payload thật. |
| **setMaxBinaryMessageBufferSize(8192)** | Buffer cho binary payload | TextWebSocketHandler demo không xử lý binary messages; không có nghĩa mọi binary upload đều được hỗ trợ. |
| **setMaxSessionIdleTimeout(60000L)** | Idle timeout tính theo millisecond ở container | Phụ thuộc hoạt động kết nối và triển khai, không thay proxy idle timeout. |
| **setAsyncSendTimeout(...)** | Timeout cho gửi bất đồng bộ khi container hỗ trợ | Không thay HTTP request timeout, cần kiểm API/transport cụ thể. |

**Phân biệt hai mức giới hạn:** 8KiB ở container là cấu hình transport/parser/buffer. 1KiB ở handler là giới hạn nghiệp vụ cho text payload. Nếu client gửi rất lớn, container có thể đóng trước handler; nếu gửi 2KiB, handler có thể đóng với **1009** sau khi nhận.

Cấu hình container **không tự giới hạn tổng số connections**, requests/s, tổng buffer bytes trên JVM hoặc tốc độ client đọc. Những giới hạn đó cần kiểm ở proxy/container và application capacity planning.

### Buffering và memory khi nhiều connections

Nếu một connection có các buffers và metadata vài KiB hoặc hơn, hàng chục nghìn connections đồng thời tạo chi phí memory/file descriptors/socket và hoạt động heartbeat đáng kể. Một WebSocket connection **không đồng nghĩa một Servlet thread bị giữ chờ toàn bộ thời gian kết nối**, nhưng dispatch callbacks và công việc blocking trong handler vẫn sử dụng tài nguyên thread/CPU.

Đừng giữ một thread đang sleep chờ message, không dùng vòng lặp vô hạn trong **handleTextMessage**. Tránh thao tác database blocking quá lâu trong callback nếu throughput/concurrency lớn; chuyển phần xử lý sang worker/broker phù hợp, có deadline, timeout và backpressure/queue budget.

## 12. Vòng đời kết nối, heartbeat và tự kết nối lại

WebSocket là **kết nối dài**, nhưng không bất tử. Nó có thể mất do:

- Browser đóng tab hoặc mất mạng.
- Proxy/load balancer đặt **idle/read timeout**.
- Server restart/rolling deployment, node bị thay.
- Firewall/NAT cắt connection không hoạt động.
- Session bị từ chối/chính sách bảo mật thay đổi.
- Payload quá lớn, invalid frame, protocol error hoặc slow consumer.

Các event quan trọng:

~~~text
CONNECTING -> OPEN -> MESSAGE(s) -> CLOSING -> CLOSED
                  |
                  +---- error / timeout / network failure ----> CLOSED
~~~

**Browser WebSocket readyState** là một state machine cục bộ: **CONNECTING (0)**, **OPEN (1)**, **CLOSING (2)**, **CLOSED (3)**. Browser API có **close(code, reason)** và callback **close**; backend có **afterConnectionEstablished/afterConnectionClosed**.

### Ping/pong và heartbeat ở tầng ứng dụng

RFC 6455 có **Ping** và **Pong** control frames. Browser WebSocket API không expose phương thức gửi Ping frame tùy ý như một message application. Một số servlet containers, WebSocket clients và broker STOMP có cơ chế ping/heartbeat riêng.

Một ứng dụng cũng có thể định nghĩa **application heartbeat message** (ví dụ text **heartbeat**/JSON type **ping**) nếu cả hai phía hiểu giống nhau. **Application heartbeat không đồng nghĩa Ping control frame**. Dùng heartbeat để phát hiện dead connection, nhưng đặt tần suất phù hợp với proxy idle timeout và chi phí ở concurrency thật.

Đừng bật ping mỗi giây cho hàng trăm nghìn clients chỉ vì muốn luôn “online”; cần đo băng thông, CPU và tài nguyên. Server có thể đóng session lâu không hoạt động nhưng nên ghi rõ idle policy cho client.

### Reconnect

Trong production, client nên có **exponential backoff + jitter**, giới hạn số lần/độ dài retry, kiểm authentication session còn hợp lệ, và resubscribe/recover state sau reconnect. Nếu server gửi event liên tục, kết nối bị mất có thể mất các events giữa hai thời điểm; **WebSocket không tự cung cấp replay/ack/durable delivery**. Nếu cần không mất sự kiện, bổ sung event ID, cursor, storage/broker hoặc protocol ack/replay.

**Đừng retry ngay lập tức theo vòng lặp vô hạn** khi backend đang deployment hoặc auth bị từ chối, vì sẽ gây thundering herd. Khi close code thể hiện policy violation/auth failure, hành vi retry cần khác lỗi mạng tạm thời.

## 13. Gửi cùng một WebSocketSession từ nhiều threads: bẫy production

WebSocket transports có quy tắc về **concurrent sends**. Ứng dụng demo chỉ gọi sendMessage trong callback tương ứng nên đơn giản. Nhưng nếu một hệ thống broadcast thông tin từ nhiều scheduler/event listeners đồng thời vào cùng một session, có nguy cơ hai threads cùng send; underlying session có thể không hỗ trợ sends đồng thời.

Spring cung cấp **ConcurrentWebSocketSessionDecorator** để serialize sends và đặt **sendTimeLimit/bufferSizeLimit**, giúp phát hiện slow consumers. Ví dụ minh họa:

~~~java
WebSocketSession safeSession =
        new ConcurrentWebSocketSessionDecorator(
                rawSession,
                10_000,       // sendTimeLimit millisecond
                128 * 1024);  // bufferSizeLimit bytes
~~~

Imports: **org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator** và **org.springframework.web.socket.WebSocketSession**. Đây là snippet **trong connection registry/service** đã quản lý **rawSession**, không phải code chạy độc lập.

**Quan trọng:** tạo decorator một lần cho mỗi connection khi đăng ký vào registry; tất cả producers phải **dùng cùng decorator**. Tạo một decorator mới ở mỗi lời gửi không bảo đảm serialization. Cần cleanup registry khi connection đóng, giới hạn số connections và theo dõi buffer pressure. Một decorator không biến slow consumer thành vô hạn dung lượng; vượt limit cần xử lý đóng/drop/backpressure theo chính sách.

Nếu payload quá lớn hoặc fanout có hàng chục nghìn subscribers, STOMP broker, event backbone hoặc kiến trúc pub/sub chuyên biệt sẽ phù hợp hơn việc broadcast từ một ConcurrentHashMap tự viết mà không có lifecycle/retention.

## 14. Reverse proxy, TLS và các header Upgrade

Trong production, request thường đi qua ingress/proxy:

~~~text
Browser -- wss://api.example.test/ws/echo -->
          Nginx / CDN / Ingress [TLS termination]
             |
             +-- HTTP/1.1 Upgrade websocket -->
                   Spring Boot :8080 /ws/echo
~~~

Nếu proxy không forward đúng **Upgrade** và **Connection** headers trên HTTP/1.1, bạn có thể nhận 400/404/502 hoặc timeout thay vì 101. Web server cần giữ connection mở sau handshake, không coi đó là request HTTP ngắn.

Ví dụ cấu hình Nginx cho **một upstream HTTP/1.1 tới Spring Boot**, trong cấu hình Nginx đã có TLS/public server settings:

~~~nginx
# Dat o HTTP context cua Nginx, khong dat ben trong location.
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

# Dat location ben trong server block phuc vu public domain.
location /ws/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $host;
    proxy_read_timeout 3600s;
}
~~~

Mẫu trên minh họa cách chuyển WebSocket upgrade qua HTTP/1.1; **không phải một tệp nginx.conf đầy đủ** và chưa có cấu hình certificate, upstream load balancing, rate limits, logging policy. Phần **map** phải nằm trong **http context**; **location** nằm trong **server block**. Không copy location này vào một đường public không được xác thực nếu dữ liệu nhạy cảm.

**Một số lưu ý quan trọng:**

- URL browser trên trang HTTPS nên là **wss://...**, tránh mixed content.
- TLS termination ở proxy chỉ mã hóa hop browser–proxy; nếu proxy–Spring Boot qua **http://**, hop đó là cleartext. Với trust boundary không an toàn, cần TLS/mTLS tới origin.
- HTTP/2 ở browser–proxy **không bảo đảm h2 WebSocket tới Spring**. Proxy thường chuyển sang **HTTP/1.1 Upgrade** ở backend; RFC 8441 extended CONNECT chỉ dùng khi các bên hỗ trợ.
- Proxy/ingress có thể giới hạn idle connections, tổng concurrent connections hoặc request header size độc lập với application. **server container idle timeout** và **proxy_read_timeout** cần được xem cùng nhau.
- Khi dùng multiple pods/replicas, mỗi WebSocket connection gắn với một node ở thời điểm đó. **WebSocket không tự phân phối messages giữa nodes**; muốn broadcast toàn cụm cần broker/event bus hoặc routing/state strategy.
- Header **Origin** vẫn đại diện origin browser. Không tự sửa allowedOrigins theo hostname nội bộ của proxy; cấu hình domain frontend public.
- Chỉ tin **Forwarded/X-Forwarded-Proto/X-Forwarded-Host** từ proxy đã được xác thực/cấu hình tin cậy. Header bị giả mạo có thể ảnh hưởng scheme/URL và chính sách bảo mật.

## 15. Xác thực và bảo vệ khi có nhiều instances

Giả sử có hai replicas:

~~~text
                       +--> Pod A: ws session #1, #2
Client --> Load Balancer
                       +--> Pod B: ws session #3, #4
~~~

Client được giữ trên một kết nối đến một pod. Nếu service phát một sự kiện chỉ trong Pod A, clients ở Pod B **không tự nhận**. Có ba thiết kế chính:

1. **Raw WebSocket + event bus:** mỗi node giữ registry connections cục bộ; message domain đến qua Redis Pub/Sub, Kafka, RabbitMQ hoặc nền tảng tương tự; node gửi cho clients của nó. Cần tính tới ordering, duplicates và loss.
2. **STOMP + external broker relay:** dùng Spring Messaging/STOMP và một broker như RabbitMQ/ActiveMQ khi cần pub/sub có tính năng cao hơn; phân biệt broker relay với simple in-memory broker.
3. **Không yêu cầu all-node live broadcast:** nếu chỉ dùng socket để cập nhật một tài khoản đang kết nối với node tương ứng, có thể điều chỉnh sticky/session routing hoặc backplane theo nhu cầu, nhưng phải xử lý reconnect và failover.

**Không mặc định dùng sticky sessions là đủ cho mọi event cross-node.** Sticky chỉ giữ connection/request ở node, không tạo message delivery tới mọi node. Nếu Spring Security session có state server-side, cần session-store strategy phù hợp khi handshake/reconnect đi sang pod khác.

Khi rolling deployment:

- Nên drain connections trước khi dừng node, hoặc gửi tín hiệu reconnect bằng close code do ứng dụng quy định.
- Client phải reconnect với backoff và lấy lại subscription/state.
- Không có cam kết giữ connection qua lần pod bị hủy; **graceful shutdown** giúp giảm tác động nhưng không biến WebSocket thành kênh bền vững.

## 16. Raw WebSocket khác STOMP over WebSocket

Raw handler ở demo có hợp đồng ứng dụng cực đơn giản: text đến → text **echo:** đi. Nếu muốn chat, topic subscription, người nhận riêng hoặc nhiều loại message, phải tự thiết kế thêm message type, routing, authorization và quy tắc ordering. **STOMP** là giao thức nhắn tin text frame hoạt động phía trên WebSocket, cung cấp các command như **CONNECT, SEND, SUBSCRIBE, DISCONNECT** và destination headers.

So sánh:

| Tiêu chí | Raw WebSocket | STOMP over WebSocket |
| --- | --- | --- |
| Cấu hình Spring | **@EnableWebSocket + WebSocketConfigurer** | **@EnableWebSocketMessageBroker + WebSocketMessageBrokerConfigurer** |
| Xử lý business | **WebSocketHandler.handleTextMessage** | **@MessageMapping**, message channels |
| Payload và định tuyến | Tự thiết kế | STOMP destinations, broker routes |
| Frontend client | Browser **new WebSocket(...)** | Thường dùng **stompjs** hoặc STOMP client |
| Broadcast | Tự quản lý sessions/backplane | Built-in simple broker hoặc external broker relay |
| Security messages | Tự kiểm trong handlers | Có Spring Security messaging authorization cho inbound channels |
| SockJS fallback | Có thể bổ sung bằng .withSockJS với kiểu config phù hợp | Thường dùng cho STOMP endpoints khi cần fallback |
| Chi phí/độ phức tạp | Nhỏ ở use case đơn giản, tăng nhanh với pub/sub | Thêm abstraction và broker semantics |

### Cấu hình STOMP là một phương án riêng

Ví dụ **minh họa cho project STOMP riêng**, không đặt trực tiếp vào cùng path **/ws/echo** của raw demo:

~~~java
@Configuration
@EnableWebSocketMessageBroker
class StompMessagingConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws-stomp")
                .setAllowedOrigins("https://app.example.test");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Imports thuộc **org.springframework.context.annotation.Configuration**, **org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker**, **WebSocketMessageBrokerConfigurer**, **StompEndpointRegistry**, **org.springframework.messaging.simp.config.MessageBrokerRegistry**. Đây là **một configuration class**, chưa phải ứng dụng đầy đủ vì còn cần Spring Boot main class và STOMP handlers.

- Client bắt đầu kết nối WebSocket tới **/ws-stomp**.
- STOMP **SEND** tới **/app/...** được route vào các **@MessageMapping** tương ứng.
- Subscriptions tới **/topic/...** hoặc **/queue/...** được built-in simple broker phục vụ theo thiết kế.
- **enableSimpleBroker** là broker trong memory hữu ích khi học/local, không phải giải pháp cluster/durable messaging hoàn chỉnh. Cần relay/external broker hoặc backplane khi triển khai phân tán.
- Nếu thêm **.withSockJS()**, client cũng phải dùng SockJS-compatible library; điều này không biến một raw browser **new WebSocket** thành SockJS client tự động.

**STOMP security** có điểm riêng: Spring Security có thể yêu cầu **CSRF token trong STOMP CONNECT** để chống cross-site WebSocket hijacking. Phải tham khảo Spring Security messaging configuration phù hợp phiên bản. Đừng tắt CSRF toàn cục chỉ vì một SockJS transport gặp lỗi.

## 17. Servlet WebSocket khác WebFlux WebSocket

Trong Spring Boot:

- **Servlet MVC**: **spring-boot-starter-websocket**, **@EnableWebSocket**, **WebSocketConfigurer**, **TextWebSocketHandler**, Jakarta WebSocket container được cấu hình như demo.
- **Reactive WebFlux**: **spring-boot-starter-webflux**, WebFlux **WebSocketHandler** và reactive **WebSocketSession**, các kiểu **Mono/Flux**, **HandlerMapping** và adapter phù hợp với reactive runtime.

Hai stack có những class cùng tên **WebSocketHandler/WebSocketSession** nhưng **package và semantics khác nhau**. Trong Servlet stack, handler nằm tại **org.springframework.web.socket**; trong WebFlux, các API reactive nằm tại **org.springframework.web.reactive.socket**. Đừng import nhầm rồi cố gắn một reactive handler vào **WebSocketHandlerRegistry** của MVC.

Nếu project có cả **spring-boot-starter-web** và **spring-boot-starter-webflux**, Spring Boot thường chọn Servlet MVC theo auto-configuration mặc định; không suy rằng có Reactor trong dependencies là toàn bộ WebSocket server đã chuyển sang WebFlux.

## 18. Embedded Servlet container khác WAR trên standalone server

Spring Boot cung cấp auto-configuration WebSocket với **embedded Tomcat, Jetty, Undertow**. Trong demo executable JAR, Boot quản lý embedded servlet container và WebSocket support.

Khi đóng **WAR** để deploy vào một **standalone Servlet container**, Spring Boot mặc định dựa vào container đó để cung cấp WebSocket runtime và cấu hình phần container-level. Do đó cần:

- Server hỗ trợ Jakarta WebSocket API phù hợp với Spring Boot/Spring Framework version (Spring Boot 3 dùng **jakarta.***, không phải **javax.***).
- Classpath và Servlet initialization đúng khi deploy WAR.
- Handshake mapping của Spring vẫn được đăng ký đúng context path.
- Bảo đảm reverse proxy hoặc application server không chặn Upgrade.
- Kiểm buffer/idle timeout bằng API phù hợp container; **ServletServerContainerFactoryBean** là một lựa chọn khi Jakarta WebSocket ServerContainer đã sẵn sàng.

**Đừng trộn @ServerEndpoint và Spring WebSocketHandler một cách tùy tiện.** Nếu chọn Jakarta **@ServerEndpoint** trực tiếp, embedded runtime thường cần cơ chế đăng ký endpoint tương ứng (ví dụ **ServerEndpointExporter** ở cấu hình Spring phù hợp); khi deploy standalone WAR, container có thể tự scan endpoints và việc thêm exporter trùng có thể gây lỗi. Raw Spring WebSocketConfigurer demo **không yêu cầu tự thêm @ServerEndpoint hay ServerEndpointExporter**.

Cẩn thận với package migration: mã cũ dùng **javax.websocket** không thể được coi là tương thích trực tiếp với Spring Boot 3/Jakarta Servlet stack chỉ bằng thay dependency.

## 19. Test hành vi thực và những trường hợp lỗi

### 19.1. Những bước phải kiểm

1. Khởi động server, truy cập **/**, browser nhận HTML.
2. Kiểm browser tạo WebSocket tới **ws://localhost:8080/ws/echo** và handshake **101**.
3. Kiểm message **ready** và **echo:ping** qua DevTools **Network → WS → Messages/Frames**.
4. Gửi payload >1.024 byte UTF-8, kiểm server đóng theo policy/size; kết quả code có thể là **1009** nếu handler xử lý trước container.
5. Thử Java WebSocketProbe, xác nhận stdout **echo:ping**.
6. Thử frontend ở origin không được allowlist; handshake nên bị từ chối nếu browser gửi Origin không phù hợp.
7. Thử kết nối qua proxy/public HTTPS/wss; so **101** tại edge và origin, xác định header Upgrade/Connection.
8. Ngắt mạng, restart server, kiểm client nhận close/error và reconnect strategy.
9. Kiểm buffer/idle timeout và số active connections khi tải tăng.
10. Với security production, kiểm cookie/session, origin policy, quyền đọc/ghi từng resource và việc revoke session/reconnect.

### 19.2. Test Spring Boot với random port

Với dependency **spring-boot-starter-test** (nếu bổ sung vào pom cho CI), có thể viết **@SpringBootTest(webEnvironment = RANDOM_PORT)** và dùng Java **HttpClient.newWebSocketBuilder()** để test handshake/message thật trên embedded server. Không chỉ dùng **MockMvc** vì mock MVC requests không mô phỏng đầy đủ WebSocket frame lifecycle, browser Origin policy, container buffer hoặc proxy.

Phác thảo test có thể chuyển từ WebSocketProbe:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class EchoWebSocketIntegrationTests {
    @LocalServerPort
    int port;

    // Dung HttpClient.newWebSocketBuilder(), listener va
    // CompletableFuture nhu trong WebSocketProbe.
    // Connect toi "ws://localhost:" + port + "/ws/echo".
    // Send text "ping" va assert response "echo:ping".
}
~~~

Đây là **khung minh họa**, không phải một test đầy đủ để compile riêng. Nếu cần test tự động ngay, chuyển phần listener/CompletableFuture từ **WebSocketProbe** vào test method, thêm imports của **org.springframework.boot.test.context.SpringBootTest**, **org.springframework.boot.test.web.server.LocalServerPort** và **org.junit.jupiter.api.Test**, cùng **spring-boot-starter-test** ở scope test.

Các ứng dụng production còn cần load tests: connections mở/giây, active connections, p95/p99 message latency, throughput, buffer occupancy, reconnect storms, dropped messages và memory per connection.

## 20. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguồn cần kiểm | Cách xử lý |
| --- | --- | --- |
| **404 /ws/echo** | Chưa @EnableWebSocket, registry sai path, context path/proxy rewrite khác | Kiểm WebSocketConfigurer và URL handshake. |
| **400 Bad Request** khi curl GET thông thường | Không phải WebSocket handshake | Dùng browser WebSocket API hoặc Java client hỗ trợ frames. |
| **403 Forbidden** khi mở socket từ frontend khác | Origin không nằm trong allowlist, security rules hoặc proxy policy | Kiểm Origin thật và allowedOrigins; không mở wildcard bừa bãi. |
| **401 Unauthorized** | Servlet security yêu cầu login, cookie/token không tới handshake | Kiểm auth flow, cookie attributes và endpoint matcher. |
| **101 ở localhost, lỗi 502 qua CDN/Nginx** | Proxy không forward Upgrade/Connection hoặc không hỗ trợ WS | Kiểm proxy_http_version 1.1, headers, upstream logs. |
| **wss lỗi chứng chỉ TLS** | TLS termination/certificate/hostname không đúng | Cấu hình HTTPS/TLS hợp lệ, không tắt xác minh certificate để chạy production. |
| **Mixed Content trên trang HTTPS** | Trang https cố mở ws cleartext | Dùng wss và bảo đảm endpoint được TLS phục vụ. |
| **Kết nối đóng sau 60 giây idle** | Bean container idle timeout, proxy/NAT policy, heartbeat thiếu | Đo hop nào đóng, điều chỉnh timeout/heartbeat phù hợp. |
| **Đóng code 1009** | Tệp/message quá kích thước container hoặc app | Giảm payload, dùng chunking có protocol, tăng limit có kiểm soát. |
| **Không thấy afterConnectionClosed ngay khi rút mạng** | TCP disconnect không clean; timeout mới phát hiện | Thiết lập heartbeat/idle timeout và cleanup có khả năng chịu lỗi. |
| **Một người không nhận broadcast khi chạy hai pods** | Node-local registry, không có message backplane | Dùng pub/sub/broker/cross-node events. |
| **Concurrent send gây exception hoặc chậm** | Nhiều producer cùng send trên một raw WebSocketSession | Dùng một ConcurrentWebSocketSessionDecorator mỗi session và buffer limits. |
| **Dùng @MessageMapping nhưng raw handler không nhận** | @MessageMapping dành cho STOMP messaging stack | Dùng đúng STOMP broker config, không trộn raw handler. |
| **WebFlux handler không gắn vào MVC registry** | Import sai package/reactive vs Servlet | Xác định web application type và đúng API stack. |
| **Không inject được Jakarta classes ở WAR cũ** | javax/jakarta migration hoặc container không hỗ trợ đúng version | Đồng bộ Spring Boot/Servlet container dependencies. |
| **GET REST vẫn chạy nhưng WS bị từ chối ở ingress** | Ingress route hỗ trợ HTTP thông thường nhưng không upgrade/giữ lâu | Kiểm WS route, host/headers, idle timeout. |

## 21. Bài tập thực hành và gợi ý mở rộng

**Bài tập 1 – Echo có giới hạn ký tự:** sửa handler để cho phép tối đa 512 bytes UTF-8. Gửi một chuỗi ASCII 512 ký tự rồi 513 ký tự. Dự kiến trường hợp đầu có thể echo, trường hợp thứ hai đóng với code 1009 nếu handler nhận được message.

**Bài tập 2 – Kiểm allowedOrigins:** phục vụ trang HTML tại **http://localhost:5173**, mở **ws://localhost:8080/ws/echo** và kiểm thành công. Thử trang tại **http://localhost:3000**, kiểm bị từ chối nếu origin không được allowlist. Không dùng non-browser client giả Origin để thay kết luận về policy browser.

**Bài tập 3 – Kiểm idle timeout:** để browser không gửi message đủ lâu, quan sát close code và thời điểm đóng. So với cấu hình container 60 giây và proxy nếu có. Không khẳng định thời gian chính xác trên mọi OS/container; phụ thuộc transport activity và lifecycle.

**Bài tập 4 – Client reconnect:** bổ sung backoff + jitter cho frontend. Phân biệt lỗi network tạm thời và close code policy violation. Khi reconnect thành công, yêu cầu khôi phục data state thay vì tin rằng event đã tự được phát lại.

**Bài tập 5 – Per-message auth:** nếu đã có Spring Security session, viết message command **{"type":"subscribeOrder","orderId":42}** (JSON) và kiểm user có quyền xem order đó trước khi subscribe. Không tin orderId hoặc role từ client; server phải lookup owner/ACL.

**Bài tập 6 – Nhiều replicas:** chạy hai instances với load balancer. Kết nối một client vào mỗi instance, phát sự kiện chỉ ở một node, mô tả vì sao node kia chưa phát. Thiết kế một pub/sub backplane và quy tắc gửi một lần hoặc chịu duplicates.

**Bài tập 7 – Chuyển sang STOMP khi cần pub/sub:** ánh xạ endpoint khác **/ws-stomp**, thêm simple broker /topic và một @MessageMapping. Phân biệt STOMP SEND/SUBSCRIBE với WebSocket text frame thô; kiểm bảo mật inbound subscriptions.

## 22. Câu hỏi tự kiểm tra

**1. Có thể dùng @GetMapping("/ws/echo") để xử lý mọi WebSocket message không?**  
Không. GET chỉ thuộc handshake HTTP ban đầu; sau upgrade, messages đi qua WebSocketHandler hoặc messaging layer.

**2. Cần thêm dependency gì trong Spring Boot MVC?**  
Dùng **spring-boot-starter-websocket** cùng cấu hình Servlet MVC; embedded Tomcat/Jetty/Undertow hỗ trợ WebSocket theo platform.

**3. @EnableWebSocket có tự tạo mọi endpoint không?**  
Không. Cần WebSocketConfigurer đăng ký handler ở path cụ thể.

**4. Vì sao WebSocket có response 101 thay vì 200?**  
Đó là kết quả handshake chuyển từ HTTP/1.1 sang WebSocket protocol.

**5. Browser trang HTTPS nên mở ws:// hay wss://?**  
Thông thường **wss://** để có TLS và tránh mixed content; public endpoint phải có TLS hợp lệ.

**6. Allowed origins là authentication hay authorization?**  
Không. Nó giảm nguy cơ cross-site browser initiation; non-browser clients có thể giả Origin. Phải xác thực và kiểm quyền thực.

**7. WebSocketSession và HttpSession có phải một object không?**  
Không. WebSocketSession đại diện connection; HttpSession là state HTTP session. Có thể chuyển context khi handshake nhưng vòng đời khác.

**8. Sau handshake, Spring Security Servlet filter có chạy lại cho mỗi WebSocket message không?**  
Không như một HTTP request mới. Handler/messaging layer phải kiểm quyền message/subscription.

**9. Tại sao không được dùng cùng WebSocketSession để send đồng thời từ nhiều threads?**  
Vì underlying transport có thể không hỗ trợ concurrent writes; nên serialize sends hoặc dùng ConcurrentWebSocketSessionDecorator có buffer/time limits.

**10. Container buffer 8KiB có thay thế business limit 1KiB không?**  
Không. Đây là hai lớp limit khác nhau; demo kiểm payload bytes ở handler và server container có limit riêng.

**11. Vì sao response 101 thành công ở localhost nhưng fail qua Nginx?**  
Có thể proxy không forward Upgrade/Connection, sai route/host hoặc đóng idle connection quá sớm.

**12. Raw WebSocket có sẵn SUBSCRIBE /topic không?**  
Không. Đây là semantics của STOMP/message broker; raw handler phải tự định nghĩa protocol nếu muốn.

**13. Simple STOMP broker có đảm bảo broadcast durable và cross-node không?**  
Không. Simple broker là in-memory và không phù hợp cluster/durable delivery đầy đủ.

**14. WebSocket có tự replay messages sau reconnect không?**  
Không. Ứng dụng phải có event IDs/acks/storage hoặc quy trình resynchronization.

**15. Có nhất thiết WebSocket nhanh hơn HTTP polling cho mọi case không?**  
Không. Cần xét tần suất cập nhật, số clients, proxy compatibility, load và chi phí kết nối dài.

## 23. Checklist triển khai Servlet WebSocket

- [ ] Xác nhận ứng dụng chạy **Spring Boot Servlet MVC**, không import nhầm reactive WebSocket types.
- [ ] Thêm **spring-boot-starter-websocket** và kiểm embedded Tomcat/Jetty/Undertow phù hợp.
- [ ] Dùng **@EnableWebSocket**, **WebSocketConfigurer**, **WebSocketHandler** cho raw endpoint.
- [ ] Chỉ định path ổn định như **/ws/echo**; không dùng @GetMapping để nhận frames.
- [ ] Kiểm handshake **101**, WebSocket text/binary frames và close events bằng browser/Java client.
- [ ] Cấu hình **setAllowedOrigins** chặt theo origin frontend; không nhầm ws:// endpoint với http(s) Origin.
- [ ] Với endpoint nhạy cảm, xác thực handshake, kiểm quyền message/subscription và chống CSWSH.
- [ ] Dùng **wss://** cho client public và TLS đúng certificate/hostname/trust chain.
- [ ] Cấu hình **ServletServerContainerFactoryBean** và application payload limit theo tài nguyên thật.
- [ ] Giới hạn active connections, message size, send buffers, concurrent writes và tốc độ gửi.
- [ ] Có idle timeout/heartbeat và chính sách reconnect/backoff, có cách khôi phục state sau disconnect.
- [ ] Kiểm Nginx/ingress/CDN forward Upgrade/Connection và timeout connection dài.
- [ ] Tách REST/CORS policy khỏi WebSocket Origin/handshake; không suy rằng OPTIONS preflight áp cho WebSocket nguyên bản.
- [ ] Nếu nhiều replicas, thiết kế event bus/broker để đồng bộ messages giữa các nodes.
- [ ] Nếu cần STOMP, dùng **@EnableWebSocketMessageBroker** và security dành cho messaging, không trộn raw handler.
- [ ] Test qua browser, Java WebSocket client, proxy thật và dưới concurrent load.
- [ ] Không log token/cookie/raw payload nhạy cảm, quan sát 101/4xx, active connections, close codes, latency, bytes và reconnect storms.
- [ ] Khi deploy WAR, kiểm Jakarta WebSocket support từ container; không thêm ServerEndpointExporter nếu đang dùng raw Spring WebSocketHandler và không cần @ServerEndpoint.

## 24. Nguồn tài liệu chính thống

- **Spring Boot 3.3 – Messaging / WebSockets:** https://docs.spring.io/spring-boot/docs/3.3.x/reference/html/messaging.html — auto-configuration embedded Servlet WebSocket, starter-websocket và triển khai WAR.
- **Spring Framework – WebSocket Overview (Servlet stack):** https://docs.spring.io/spring-framework/reference/web/websocket.html — HTTP Upgrade, RFC 6455, use cases và WebSocket vs HTTP.
- **Spring Framework – WebSocket Server API:** https://docs.spring.io/spring-framework/reference/web/websocket/server.html — WebSocketHandler, @EnableWebSocket, WebSocketConfigurer, HandshakeInterceptor, allowed origins, ServletServerContainerFactoryBean.
- **Spring Framework – STOMP Enable:** https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html — @EnableWebSocketMessageBroker, STOMP endpoints, broker prefixes.
- **Spring Framework – STOMP Simple Broker:** https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html — in-memory broker, heartbeats và limitations.
- **Spring Framework – STOMP External Broker:** https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html — broker relay và cluster considerations.
- **Spring Security – WebSocket Security (Servlet):** https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html — authentication from HTTP Principal, message authorization, same-origin/CSRF và SockJS.
- **Spring Framework – ServletServerContainerFactoryBean Javadoc:** https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/socket/server/standard/ServletServerContainerFactoryBean.html — max buffer sizes, idle timeout, async send timeout.
- **RFC 6455 – The WebSocket Protocol:** https://www.rfc-editor.org/rfc/rfc6455 — handshake và frames.
- **RFC 8441 – Bootstrapping WebSockets with HTTP/2:** https://www.rfc-editor.org/rfc/rfc8441 — extended CONNECT over HTTP/2.
- **MDN – WebSocket API:** https://developer.mozilla.org/en-US/docs/Web/API/WebSocket — browser WebSocket constructor, events và readyState.

# Phân biệt WebSocket thuần với STOMP và phạm vi hỗ trợ từng stack

## 1. Mục tiêu học tập và ý chính

Trong ứng dụng Spring Boot cần cập nhật dữ liệu theo thời gian thực, hai khái niệm thường xuất hiện cùng nhau: **WebSocket** và **STOMP**. Chúng không phải hai cách gọi đồng nghĩa.

- **WebSocket** là giao thức truyền thông hai chiều (full-duplex) trên một kết nối kéo dài. Giao thức quy định handshake, frame văn bản/nhị phân, ping/pong và đóng kết nối, **không tự quy định** những gì chuỗi `"chat"` hay JSON có nghĩa.
- **STOMP** (Simple Text Oriented Messaging Protocol) là giao thức **thông điệp ở lớp cao hơn**, có các command `CONNECT`, `SUBSCRIBE`, `SEND`, `MESSAGE`, `ACK`, destination, subscription, headers và heartbeat. Nó có thể chạy **trên WebSocket hoặc trên TCP**, không phải một “phiên bản khác” của WebSocket.
- **Spring MVC/Servlet** hỗ trợ cả raw WebSocket handler **lẫn** STOMP-over-WebSocket thông qua message broker infrastructure của Spring Framework.
- **Spring WebFlux** hỗ trợ WebSocket reactive với `WebSocketHandler` và `Mono/Flux`. Bộ tích hợp **STOMP message broker kiểu Servlet MVC** (`@EnableWebSocketMessageBroker`, `@MessageMapping` theo luồng message-broker của MVC) **không phải một tính năng WebFlux tự động có sẵn** chỉ nhờ thêm starter WebFlux. Muốn STOMP trong kiến trúc reactive, cần thiết kế parser/broker adapter/library phù hợp hoặc đặt một dịch vụ messaging riêng.

Bài thuộc nhóm **Kết nối dài** trong module **Spring Boot - web-runtime**. Sau bài học, bạn có thể:

1. Giải thích handshake WebSocket, `ws://`/`wss://` và khác biệt với request-response HTTP thường.
2. Đọc một STOMP frame, phân biệt WebSocket message với STOMP `destination` và subscription.
3. Chọn WebSocket thuần cho giao thức tùy biến nhỏ; STOMP cho routing, pub/sub và broker semantics khi cần.
4. Chạy ví dụ **Java 17 / Spring Boot 3.3.5** với một raw echo endpoint và một STOMP endpoint trong **Spring MVC**.
5. Hiểu cách dùng `WebSocketHandler` reactive trong **WebFlux** bằng dự án riêng.
6. Phân biệt simple broker in-memory với broker relay RabbitMQ/ActiveMQ; biết giới hạn về scale, persistence, acknowledgment và clustering.
7. Kiểm tra kết nối, bảo vệ handshake/Origin, định danh user, phân quyền message, proxy upgrade, heartbeat, buffer, timeout và lỗi thường gặp.

**Quy tắc nhớ nhanh:** WebSocket giải quyết **kênh truyền**; STOMP giải quyết **cấu trúc, đích đến và điều phối thông điệp** chạy trên kênh đó.

## 2. WebSocket thuần là gì?

Ở chế độ WebSocket thông thường, browser hoặc client mở một kết nối:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/raw");

socket.onopen = () => socket.send("hello");
socket.onmessage = event => console.log(event.data);
socket.onclose = event => console.log(event.code, event.reason);
socket.onerror = () => console.log("WebSocket transport error");
~~~

Đoạn trên là **mã browser**; nó chỉ chạy khi server đã đăng ký endpoint `/ws/raw`. Không có quy định rằng thông điệp `hello` phải được echo, lưu DB hay phát cho user khác. Chính server và client phải thống nhất “application protocol”: chuỗi text, JSON envelope hoặc binary format.

### 2.1. Handshake và HTTP Upgrade

Một WebSocket trên HTTP/1.1 thường bắt đầu bằng request upgrade:

~~~http
GET /ws/raw HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: <random-base64>
Sec-WebSocket-Version: 13
Origin: http://localhost:8080
~~~

Nếu server chấp nhận, response điển hình là:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <computed-value>
~~~

Sau handshake, hai bên trao đổi **WebSocket frames** trên kết nối đó. Những giá trị trong dấu ngoặc là minh họa, không phải bytes cần chép để gửi trực tiếp. `Sec-WebSocket-Accept` được tính theo quy tắc RFC 6455, không phải user tự tạo tùy ý.

- `ws://` là WebSocket không có TLS, phù hợp cho localhost lab.
- `wss://` là WebSocket qua TLS, thường dùng khi frontend phục vụ qua HTTPS.
- HTTP request ban đầu dùng cho handshake; sau đó **không** còn mỗi message ứng dụng là một HTTP request với status 200.
- WebSocket là full-duplex: hai bên có thể chủ động gửi message khi kết nối còn mở.
- WebSocket có frame text, binary và control (ping/pong/close); nó không biết `/topic` hay `@MessageMapping` theo giao thức gốc.

**Cẩn trọng với HTTP/2:** hỗ trợ WebSocket qua HTTP/2 có đặc tả extended CONNECT riêng (RFC 8441), nhưng không được giả định mọi proxy, client, container hoặc phiên bản Spring Boot đều tự bật. Lab dùng HTTP/1.1 upgrade để dễ kiểm tra. Một website dùng HTTP/2 cho tài nguyên tĩnh vẫn có thể dùng WebSocket upgrade kiểu HTTP/1.1 qua proxy.

### 2.2. WebSocket là transport, không phải application messaging

Nếu gửi JSON:

~~~json
{"type":"chat","room":"general","body":"Xin chào"}
~~~

Spring raw WebSocket handler có thể nhận một **text message chứa JSON**, nhưng mặc định **không tự route** nó đến subscriber phòng `general`, không tự biết `type=chat` và không có built-in broker. Muốn chat/subscribe/replay/ack, đội phát triển phải tự định nghĩa và thực thi những quy tắc đó.

Nếu gửi bytes binary, client và server còn phải thống nhất serialization, version, size limit và cách xử lý payload lỗi. Raw WebSocket cho sự linh hoạt nhưng đổi lại bạn tự chịu trách nhiệm protocol.

## 3. STOMP là gì? Chạy ở tầng nào?

STOMP là giao thức frame-based cho messaging. Trong STOMP-over-WebSocket:

~~~text
Browser / STOMP client
        |
        | HTTP handshake nâng cấp sang WebSocket
        v
WebSocket connection
        |
        | WebSocket text/binary message
        | chứa nội dung STOMP frame
        v
STOMP decoder + message routing
        |
        +--> /app/...   -> @MessageMapping handlers
        '--> /topic/... -> broker/subscribers
~~~

STOMP định nghĩa các command và các header. Một STOMP frame mô hình:

~~~text
COMMAND
header-name:header-value
other-header:other-value

body<NULL>
~~~

Dòng trống ngăn header và body; ký tự **NUL byte (0x00)** là terminator frame theo quy tắc STOMP. Trong tài liệu thường viết `^@` hoặc `\0` để minh họa. Đây **không phải** một dòng JSON và không phải raw WebSocket frame header; STOMP nằm bên trong payload của WebSocket messages.

Các command cơ bản:

| Command | Ý nghĩa |
| --- | --- |
| `CONNECT` / `STOMP` | Client bắt đầu phiên STOMP, khai báo version, heartbeat, host |
| `CONNECTED` | Server chấp nhận phiên STOMP |
| `SUBSCRIBE` | Client đăng ký nhận messages ở một destination |
| `UNSUBSCRIBE` | Bỏ subscription |
| `SEND` | Client gửi message tới một destination |
| `MESSAGE` | Server/broker chuyển message cho subscriber |
| `ACK` / `NACK` | Xác nhận hoặc từ chối delivery khi broker/mode hỗ trợ |
| `DISCONNECT` | Chủ động kết thúc phiên STOMP |
| `ERROR` | Broker/server thông báo lỗi giao thức hoặc xử lý |
| `BEGIN`/`COMMIT`/`ABORT` | Giao dịch STOMP khi broker hỗ trợ |

STOMP phiên bản 1.2 cũng mô tả **heart-beating**, subscription IDs, `receipt` và `content-length`. Không phải mọi broker/implementation hỗ trợ đầy đủ mọi command; tính năng phải đối chiếu theo server thực sự.

### 3.1. Các frames minh họa

Client gửi kết nối STOMP sau khi WebSocket đã mở:

~~~text
CONNECT
accept-version:1.2
host:localhost
heart-beat:0,0

^@
~~~

Server có thể trả:

~~~text
CONNECTED
version:1.2
heart-beat:0,0

^@
~~~

Client muốn nhận cập nhật:

~~~text
SUBSCRIBE
id:sub-0
destination:/topic/echo
ack:auto

^@
~~~

Client gửi một message vào logic ứng dụng:

~~~text
SEND
destination:/app/echo
content-type:application/json

{"text":"Xin chào"}^@
~~~

Server qua broker gửi cho subscription:

~~~text
MESSAGE
subscription:sub-0
destination:/topic/echo
message-id:<broker-generated>

{"text":"stomp: Xin chào"}^@
~~~

Các đoạn trên dùng `^@` làm ký hiệu cho byte NUL; khi code gửi thực, cần dùng ký tự `\0`/`\u0000`, **không gửi hai ký tự ^ và @**. Tên header/ID tùy broker/version. STOMP frame `MESSAGE` thực tế có thể có `content-type`, `content-length` hoặc headers khác.

**STOMP có thể chạy trên TCP trực tiếp**. WebSocket không phải thành phần bắt buộc của STOMP theo định nghĩa giao thức. Spring MVC thường dùng STOMP over WebSocket để browser truy cập dễ dàng; Spring broker relay có thể nói STOMP qua TCP tới broker bên ngoài.

## 4. So sánh WebSocket thuần và STOMP-over-WebSocket

| Khía cạnh | Raw WebSocket | STOMP over WebSocket |
| --- | --- | --- |
| Tầng giao thức | WebSocket transport | STOMP messaging chạy trên WebSocket |
| Nội dung message | Ứng dụng tự định nghĩa | Frame có command/headers/destination |
| Routing theo destination | Tự triển khai | Có semantics routing |
| Subscribe / publish | Tự thiết kế | `SUBSCRIBE` / `SEND`, broker gửi `MESSAGE` |
| Controller API thường gặp trong MVC | `TextWebSocketHandler` hoặc `WebSocketHandler` | `@MessageMapping`, `@SendTo`, `SimpMessagingTemplate` |
| Config thường gặp trong MVC | `@EnableWebSocket` + `WebSocketConfigurer` | `@EnableWebSocketMessageBroker` + `WebSocketMessageBrokerConfigurer` |
| Broker | Không tự có | Simple broker in-memory hoặc external broker relay |
| Binary payload | Có (WebSocket binary frames) | STOMP payload có thể text/binary nhưng phụ thuộc converter/client/broker |
| Heartbeat | WebSocket ping/pong hoặc app heartbeat | STOMP heartbeat; có thể kết hợp transport keepalive |
| ACK / receipt | Tự định nghĩa | STOMP có, nhưng simple broker của Spring chỉ hỗ trợ một tập con |
| Client JavaScript | Native `WebSocket` đủ cho custom protocol | Thường dùng `@stomp/stompjs` hoặc STOMP client library |
| Overhead | Thấp nếu protocol tối giản | Thêm frame headers, parsing, broker routing |
| Phù hợp | Echo, game/tương tác custom, binary, giao thức nhỏ | Chat rooms, notifications, pub/sub, topic/user destinations |
| Mở rộng qua nhiều instance | Bạn phải thiết kế message bus | Simple broker cũng không tự cluster; relay với external broker phù hợp hơn |

**Đừng suy ra STOMP luôn đáng tin cậy hơn.** STOMP định nghĩa cách diễn tả các nghiệp vụ như subscribe và ACK, nhưng **durability, replay, delivery guarantees, offline queue** phụ thuộc broker, cấu hình, topology và client logic. Simple broker của Spring không phải Kafka/RabbitMQ durable queue tự động.

## 5. Ma trận hỗ trợ theo web stack Spring Boot

Spring Framework có hai web stacks lớn: **Servlet/MVC** và **reactive/WebFlux**. WebSocket hỗ trợ ở cả hai; message broker STOMP tích hợp framework theo kiểu Spring MVC là khả năng riêng của Servlet stack.

| Khả năng | Spring MVC / Servlet | Spring WebFlux / reactive |
| --- | --- | --- |
| HTTP endpoints | `@RestController`, MVC HandlerMapping | Reactive controllers, RouterFunction |
| Raw WebSocket server | `org.springframework.web.socket.WebSocketHandler`; `TextWebSocketHandler` | `org.springframework.web.reactive.socket.WebSocketHandler`; `Mono<Void>` |
| WebSocket session | `org.springframework.web.socket.WebSocketSession` | `org.springframework.web.reactive.socket.WebSocketSession` |
| Nhận message | Callback như `handleTextMessage` | `session.receive(): Flux<WebSocketMessage>` |
| Gửi message | `session.sendMessage(...)` | `session.send(Publisher<WebSocketMessage>)` |
| Mapping raw WebSocket URL | `@EnableWebSocket` / `WebSocketConfigurer` | `SimpleUrlHandlerMapping` và WebSocketHandlerAdapter |
| STOMP message broker built-in | **Có**: `@EnableWebSocketMessageBroker` | **Không có bản auto tương đương trong WebFlux** |
| `@MessageMapping` STOMP với broker | **Có** qua Spring messaging infrastructure | Không tự được bật qua WebFlux handlers |
| Simple broker / STOMP broker relay tích hợp | **Có**, trong cấu hình MVC STOMP | Không phải module broker reactive tích hợp giống MVC |
| SockJS fallback trong Spring STOMP | Có khi chủ động `.withSockJS()` | Không có cùng cấu hình messaging broker tự động |
| Event loop/backpressure | Chủ yếu Servlet threads + WebSocket session send semantics | Reactor `Flux/Mono`, quản lý buffer/backpressure |
| Dependency minh họa | `spring-boot-starter-web` + `spring-boot-starter-websocket` | `spring-boot-starter-webflux` và WebSocket API thích hợp với server |

**Quan trọng về giới hạn:** “WebFlux không có STOMP broker tích hợp kiểu MVC” **không có nghĩa STOMP bị giao thức WebFlux cấm**. Bạn vẫn có thể xử lý STOMP frames theo custom `WebSocketHandler`, tích hợp thư viện STOMP khác, xây service STOMP/messaging tách biệt hoặc dùng broker/bridge phù hợp. Nhưng không thể sao chép nguyên `@EnableWebSocketMessageBroker` vào project WebFlux và mong framework tạo ra cùng cơ chế message broker như MVC.

**Chọn stack dựa trên code đang chạy, không dựa trên thư viện tình cờ có mặt.** Khi Spring Boot 3.3 thấy cả `spring-boot-starter-web` và `spring-boot-starter-webflux` trong classpath, Boot thường chọn **Servlet MVC** theo mặc định. Việc dùng `WebClient` trong MVC không tự làm app chuyển thành WebFlux.

## 6. WebSocket, STOMP, SockJS, SSE và RSocket khác nhau

| Công nghệ | Mô hình chính | Khi cân nhắc |
| --- | --- | --- |
| WebSocket | Full-duplex, kết nối lâu dài | Chat custom, interactive UI, realtime binary |
| STOMP over WebSocket | Message commands + pub/sub + destinations trên WebSocket | Cần broker routing, subscriptions, Spring MVC STOMP |
| SockJS | Fallback transport khi native WebSocket không sẵn hoặc bị chặn | Tương thích môi trường/browser/proxy đặc thù |
| Server-Sent Events (SSE) | HTTP streaming **một chiều từ server tới client** | Notifications/streams chỉ server→browser, ít yêu cầu hai chiều |
| Long polling | Lặp lại HTTP requests để lấy sự kiện | Fallback hoặc client hạn chế WebSocket |
| RSocket | Protocol tương tác request/stream, có backpressure và nhiều interaction models | Hệ thống cần reactive messaging protocol riêng |

**STOMP không bằng SockJS.** SockJS mô phỏng transport dạng WebSocket với fallback HTTP streaming/polling. STOMP định nghĩa messaging. Bạn có thể dùng STOMP trên native WebSocket, hoặc kết hợp STOMP + SockJS khi phía server khai báo `.withSockJS()` và client dùng SockJS tương ứng. Cài dependency SockJS phía browser mà server chỉ đăng ký native WebSocket không tự tạo fallback endpoint.

**SSE không phải WebSocket một chiều bị cắt đi.** SSE là cơ chế khác chạy trên HTTP, có semantics reconnection/event ID riêng; không chọn raw WebSocket chỉ vì muốn một biểu đồ được push cập nhật một chiều.

## 7. Khi nào chọn raw WebSocket? Khi nào chọn STOMP?

Chọn **raw WebSocket** khi:

1. Giao thức ứng dụng nhỏ, ví dụ echo, điều khiển thiết bị, game state, binary telemetry; đội kiểm soát cả client và server.
2. Không cần subscription routing phức tạp; chỉ gửi message trên một kết nối theo JSON schema tự định nghĩa.
3. Cần protocol tối giản và tự quản lý framing/app semantics.
4. Có cơ chế fan-out/queue bên ngoài đã được thiết kế độc lập và không muốn dùng STOMP ở client.

Chọn **STOMP-over-WebSocket trong Spring MVC** khi:

1. Cần `/app/...` để gửi message tới controller, `/topic/...` để fan-out cho nhiều subscribers, hoặc `/user/...` cho message hướng người dùng.
2. Muốn dùng `@MessageMapping`, `@SendTo` và Spring messaging converters.
3. Muốn tích hợp simple broker cho demo/nhỏ, hoặc broker relay khi có external STOMP broker.
4. Các client hỗ trợ STOMP và chấp nhận overhead protocol.

Không chọn dựa trên câu “WebSocket nhanh hơn STOMP nên luôn dùng raw” hoặc “STOMP có broker nên chắc chắn không mất message”. Hãy cân nhắc số kết nối, tần suất, kích thước, guarantees, security, broker infrastructure, chi phí vận hành và khả năng scale.

## 8. Lab A — Spring MVC hỗ trợ đồng thời raw WebSocket và STOMP

Lab này dùng **Java 17+, Spring Boot 3.3.5**, embedded Tomcat. Một ứng dụng có hai endpoint WebSocket **khác nhau**:

- `ws://localhost:8080/ws/raw`: server chỉ nhận text, trả `raw: ...` cho **chính kết nối đó**, không STOMP.
- `ws://localhost:8080/ws/stomp`: server đọc STOMP frames, cho phép subscribe `/topic/echo` và gửi `SEND` tới `/app/echo` để nhận message từ broker.

Đặt hai endpoint trong cùng app giúp so sánh trực tiếp. Trong dự án thực, cấu hình bảo mật và message broker cần cẩn thận hơn; không dùng mã demo làm chat server Internet công khai.

### 8.1. Cấu trúc thư mục

~~~text
mvc-websocket-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/ws/
    │   ├── WebsocketApplication.java
    │   ├── RawEchoHandler.java
    │   ├── RawWebSocketConfig.java
    │   ├── StompWebSocketConfig.java
    │   ├── ChatMessage.java
    │   └── ChatController.java
    └── resources/
        ├── application.properties
        └── static/index.html
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>mvc-websocket-lab</artifactId>
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

`spring-boot-starter-websocket` cung cấp Spring WebSocket/messaging integration cho ứng dụng Servlet/MVC. `spring-boot-starter-web` dùng cho controller MVC, static resources và embedded Tomcat; các transitive dependency trùng được Maven xử lý. Bài **không** thêm `spring-boot-starter-webflux` để tránh đổi mô hình vận hành một cách mơ hồ.

### 8.3. application.properties

~~~properties
server.port=8080

# Demo: không có authentication/broker ngoài.
# Cần giới hạn Origin, message size và TLS trong production.
~~~

Khi dùng browser trên cùng `http://localhost:8080`, các endpoints WebSocket cùng origin với trang HTML; không cần mở `*` cho `allowedOrigins`.

### 8.4. Lớp khởi động

**Tệp `src/main/java/com/example/ws/WebsocketApplication.java`:**

~~~java
package com.example.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebsocketApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebsocketApplication.class, args);
    }
}
~~~

### 8.5. Handler raw WebSocket

**Tệp `src/main/java/com/example/ws/RawEchoHandler.java`:**

~~~java
package com.example.ws;

import java.io.IOException;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class RawEchoHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session, TextMessage message)
            throws IOException {
        String text = message.getPayload();
        session.sendMessage(new TextMessage("raw: " + text));
    }
}
~~~

**Tệp `src/main/java/com/example/ws/RawWebSocketConfig.java`:**

~~~java
package com.example.ws;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class RawWebSocketConfig implements WebSocketConfigurer {

    private final RawEchoHandler echoHandler;

    public RawWebSocketConfig(RawEchoHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/raw");
    }
}
~~~

**Giải thích:**

- `@EnableWebSocket` + `WebSocketConfigurer` đăng ký handshake URL cho **raw** socket.
- `TextWebSocketHandler` nhận WebSocket **text messages**. Nếu browser gửi `hello`, server trả text `raw: hello` vào **cùng WebSocket session**.
- Không có `SUBSCRIBE`, `/topic`, `brokerChannel`, `@MessageMapping` hay STOMP decoding trong handler này.
- `WebSocketSession.sendMessage(...)` thuộc API Servlet WebSocket. Khi nhiều threads cùng gửi một session, phải serialize send hoặc dùng `ConcurrentWebSocketSessionDecorator`; **không tùy tiện gọi send đồng thời** từ nhiều thread.
- Lab không implement binary message handler; đừng coi mọi binary payload đã được support chỉ vì transport WebSocket cho phép binary.

### 8.6. STOMP broker config

**Tệp `src/main/java/com/example/ws/StompWebSocketConfig.java`:**

~~~java
package com.example.ws;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws/stomp");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
~~~

Đây là phần **STOMP dành cho Spring MVC**. Các đường dẫn có vai trò khác nhau:

- `/ws/stomp` là **HTTP handshake endpoint** để nâng cấp thành WebSocket. Đây **không phải destination** mà client dùng khi `SEND` message nghiệp vụ.
- `/app/echo` là **STOMP destination** dành cho ứng dụng. Spring bỏ prefix `/app` và đưa phần còn lại đến method `@MessageMapping("/echo")`.
- `/topic/echo` là **STOMP destination** broker dùng để gửi message tới subscribers đang đăng ký. Không phải URL HTTP GET.
- `enableSimpleBroker("/topic")` bật broker **in-memory** đơn giản. Nó không lưu message bền vững, không tự liên thông nhiều replicas.

### 8.7. DTO và @MessageMapping controller

**Tệp `src/main/java/com/example/ws/ChatMessage.java`:**

~~~java
package com.example.ws;

public record ChatMessage(String text) {
}
~~~

**Tệp `src/main/java/com/example/ws/ChatController.java`:**

~~~java
package com.example.ws;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/echo")
    @SendTo("/topic/echo")
    public ChatMessage echo(ChatMessage incoming) {
        String input = incoming.text() == null
                ? "" : incoming.text();

        return new ChatMessage("stomp: " + input);
    }
}
~~~

**Khác với raw handler:**

1. Không có `@GetMapping` hoặc `@RequestBody` cho message; `@MessageMapping` xử lý **STOMP SEND frames** hướng tới destination đã khai báo.
2. Spring messaging converter giải mã JSON trong STOMP payload thành `ChatMessage` khi headers/content type phù hợp.
3. `@SendTo("/topic/echo")` đưa response payload về broker; broker phát `MESSAGE` cho **những subscribers** của topic, không chỉ nhất thiết người đã gửi.
4. `@Controller` ở đây xử lý **message**, không phải Servlet HTTP request thông thường.
5. Không cần trực tiếp thao tác từng `WebSocketSession` để biết ai subscribe, vì simple broker đã quản lý danh sách subscriptions trong phạm vi instance.

**Giới hạn demo:** không kiểm tra độ dài/loại nội dung, chưa xác thực người dùng, không rate limit và không lưu history. Client có thể gửi message bất kỳ; không triển khai production nguyên trạng.

## 9. Client browser: kiểm tra raw và STOMP không cần thư viện ngoài

Để nhìn thấy sự khác biệt ở mức protocol, lab dùng **native browser WebSocket** cho cả hai, nhưng với STOMP, JavaScript tự ghép vài STOMP frames tối thiểu. Trong dự án production, hãy dùng client STOMP được bảo trì (ví dụ `@stomp/stompjs`) để xử lý reconnect, heartbeat, frame parsing, fragmentation và ACK đúng cách.

**Tệp `src/main/resources/static/index.html`:**

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>WebSocket thuần và STOMP</title>
</head>
<body>
  <h1>Spring Boot WebSocket vs STOMP</h1>
  <button id="rawConnect">Kết nối raw + gửi hello</button>
  <button id="stompConnect">Kết nối STOMP + subscribe</button>
  <button id="stompSend">SEND STOMP /app/echo</button>
  <pre id="output"></pre>

  <script>
    const output = document.querySelector("#output");
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const base = scheme + "//" + location.host;

    const log = message => {
      output.textContent += message + "\n";
    };

    let rawSocket;
    let stompSocket;
    let stompConnected = false;

    document.querySelector("#rawConnect").onclick = () => {
      rawSocket = new WebSocket(base + "/ws/raw");
      rawSocket.onopen = () => {
        log("RAW OPEN");
        rawSocket.send("hello");
      };
      rawSocket.onmessage = event => log("RAW RECV: " + event.data);
      rawSocket.onclose = event => log("RAW CLOSE: " + event.code);
      rawSocket.onerror = () => log("RAW ERROR");
    };

    document.querySelector("#stompConnect").onclick = () => {
      // Đề nghị STOMP subprotocol trong WebSocket handshake.
      stompSocket = new WebSocket(
        base + "/ws/stomp", ["v12.stomp", "v11.stomp", "v10.stomp"]);
      stompConnected = false;

      stompSocket.onopen = () => {
        log("WS STOMP TRANSPORT OPEN");
        stompSocket.send(
          "CONNECT\n" +
          "accept-version:1.2\n" +
          "host:localhost\n" +
          "heart-beat:0,0\n" +
          "\n\0");
      };

      stompSocket.onmessage = event => {
        // Demo in raw STOMP text; parser production phức tạp hơn.
        const text = String(event.data);
        log("STOMP RECV: " + text.replaceAll("\0", "<NUL>"));

        if (text.startsWith("CONNECTED\n")) {
          stompConnected = true;
          stompSocket.send(
            "SUBSCRIBE\n" +
            "id:sub-0\n" +
            "destination:/topic/echo\n" +
            "ack:auto\n" +
            "\n\0");
          log("STOMP SUBSCRIBE sent: /topic/echo");
        }
      };

      stompSocket.onclose = event => {
        stompConnected = false;
        log("STOMP CLOSE: " + event.code);
      };
      stompSocket.onerror = () => log("STOMP ERROR");
    };

    document.querySelector("#stompSend").onclick = () => {
      if (!stompSocket ||
          stompSocket.readyState !== WebSocket.OPEN ||
          !stompConnected) {
        log("Connect STOMP và đợi CONNECTED trước khi SEND.");
        return;
      }

      const body = JSON.stringify({text: "hello"});
      stompSocket.send(
        "SEND\n" +
        "destination:/app/echo\n" +
        "content-type:application/json\n" +
        "\n" + body + "\0");

      log("STOMP SEND: /app/echo");
    };
  </script>
</body>
</html>
~~~

### 9.1. Cách thao tác

1. Chạy ứng dụng (mục 10), mở `http://localhost:8080/` trong browser.
2. Nhấn **Kết nối raw + gửi hello**. Bạn sẽ thấy `RAW OPEN` và `RAW RECV: raw: hello`.
3. Nhấn **Kết nối STOMP + subscribe**. Đợi thấy `WS STOMP TRANSPORT OPEN`, một `CONNECTED` frame và `STOMP SUBSCRIBE sent: /topic/echo`.
4. Nhấn **SEND STOMP /app/echo** sau khi đã subscribe. Bạn sẽ thấy một `MESSAGE` frame với destination `/topic/echo` và body JSON chứa `"stomp: hello"`.
5. Mở trang trong **hai tabs** và subscribe cả hai vào `/topic/echo`. Khi tab A gửi STOMP SEND, cả hai tab có thể nhận MESSAGE, vì simple broker broadcast tới subscribers; raw echo từ tab A chỉ trở về chính raw connection tab A.

**Kỳ vọng mang tính hợp đồng**, không phải stdout byte-for-byte: STOMP frame có thể mang thêm headers/IDs. Demo client chỉ parse bằng `startsWith`, không hỗ trợ nhiều STOMP frames gộp một socket event, chia message, heartbeat, escaping headers, version negotiation phức tạp hoặc reconnect. Điều này **cố ý** để bạn thấy STOMP thêm một lớp protocol. Khi làm sản phẩm, chọn thư viện STOMP đúng version thay vì phát triển parser thủ công như vậy.

### 9.2. Vì sao không gửi JSON thẳng tới /ws/stomp?

Một client làm:

~~~javascript
const w = new WebSocket("ws://localhost:8080/ws/stomp");
w.onopen = () => w.send('{"text":"hello"}');
~~~

sẽ **không tự được map** tới `@MessageMapping("/echo")`, vì endpoint STOMP đòi hỏi **STOMP CONNECT/SEND frames**, có destination và kết thúc frame đúng chuẩn. Browser `WebSocket` chỉ bảo đảm transport; STOMP semantics nằm ở lớp trên.

Ngược lại, gửi STOMP `SEND\n...` vào `/ws/raw` sẽ được raw handler xem là **một text message nguyên xi** và echo lại, không có broker tự parse.

**Đây là phép thử quan trọng nhất để phân biệt hai lớp giao thức.**

## 10. Chạy lab MVC và kiểm tra kết quả

Tạo các tệp chính xác như mục 8–9, dùng JDK 17+ và Maven 3.x. Trong thư mục `mvc-websocket-lab`:

~~~bash
mvn spring-boot:run
~~~

Mở:

~~~text
http://localhost:8080/
~~~

Kiểm tra server HTTP đã chạy:

~~~bash
curl -i http://localhost:8080/
~~~

Kỳ vọng trả trang HTML; nhưng `curl -i` thông thường **không phải một WebSocket/STOMP client đầy đủ**. Chỉ gửi GET `http://localhost:8080/ws/stomp` mà thiếu handshake/upgrade headers sẽ không chứng minh socket hoạt động.

### 10.1. Các quan sát đúng

| Hành động | Điều kiểm chứng |
| --- | --- |
| Browser mở WebSocket `/ws/raw` | Handshake thành công, raw handler được đăng ký |
| Gửi text `hello` | Raw server trả `raw: hello`, không cần broker |
| Browser mở WebSocket `/ws/stomp` với subprotocol phù hợp | Chỉ transport đã mở; còn phải gửi STOMP CONNECT |
| Nhận STOMP `CONNECTED` | STOMP session handshake ở tầng messaging đã được chấp nhận |
| Gửi `SUBSCRIBE destination:/topic/echo` | Broker ghi nhận đăng ký nhận messages |
| Gửi `SEND destination:/app/echo` JSON | `@MessageMapping("/echo")` xử lý và gửi tới topic |
| Hai tab cùng subscribe | Cả hai nhận broker `MESSAGE` nếu đang kết nối/subscribe |
| Không subscribe mà chỉ gửi SEND | Không mặc nhiên nhận message topic |
| Gửi STOMP vào raw URL | Raw echo, không route theo `destination` |

### 10.2. Hai loại handshake độc lập

- **WebSocket handshake**: HTTP Upgrade → 101 Switching Protocols → transport mở.
- **STOMP CONNECT/CONNECTED**: trao đổi STOMP frames **sau khi** WebSocket mở.

Một socket đã `OPEN` trong browser không đảm bảo STOMP session đã `CONNECTED`. Nếu server đóng ngay sau `CONNECT`, phải kiểm tra frame, version, subprotocol, authentication/CSRF và server logs.

### 10.3. Vì sao không thể chỉ nhìn status 101?

WebSocket endpoint raw và STOMP có thể **đều trả 101**. Điều này không cho biết server sẽ xử lý payload là raw text hay STOMP frame. Muốn phân biệt, xem request `Sec-WebSocket-Protocol`/response negotiated protocol, cấu hình server và **nội dung message sau handshake**.

Nếu proxy log chỉ có `101` mà client báo “STOMP not connected”, có thể WebSocket transport thành công nhưng STOMP `CONNECT` sai hoặc bị security channel interceptor từ chối.

## 11. WebFlux raw WebSocket — project riêng

Spring WebFlux dùng API reactive khác Servlet MVC. Ví dụ sau là một **project độc lập**, không copy thêm vào `mvc-websocket-lab`. Nó chỉ có **raw WebSocket echo**, **không** bật STOMP broker.

### 11.1. Cấu trúc thư mục

~~~text
webflux-websocket-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/reactivews/
    │   ├── ReactiveWsApplication.java
    │   ├── ReactiveEchoHandler.java
    │   └── ReactiveWsConfig.java
    └── resources/
        ├── application.properties
        └── static/index.html
~~~

### 11.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>webflux-websocket-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

Với runtime mặc định Reactor Netty, `spring-boot-starter-webflux` cung cấp WebFlux reactive APIs và server đủ để thực hiện lab này. **Nếu chuyển sang WebFlux trên Servlet container** như Tomcat/Jetty hoặc deployment WAR, hãy kiểm tra thêm yêu cầu Jakarta WebSocket API/container và Spring Boot WebSocket auto-configuration của đúng phiên bản. Không lấy dependency dành cho Tomcat WebSocket để khẳng định Reactor Netty bắt buộc cần nó.

### 11.3. Application và cấu hình

**Tệp `src/main/resources/application.properties`:**

~~~properties
server.port=8082
~~~

**Tệp `src/main/java/com/example/reactivews/ReactiveWsApplication.java`:**

~~~java
package com.example.reactivews;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveWsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveWsApplication.class, args);
    }
}
~~~

**Tệp `src/main/java/com/example/reactivews/ReactiveEchoHandler.java`:**

~~~java
package com.example.reactivews;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class ReactiveEchoHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> output = session.receive()
                .map(incoming ->
                        session.textMessage(
                                "reactive: " + incoming.getPayloadAsText()));

        return session.send(output);
    }
}
~~~

**Tệp `src/main/java/com/example/reactivews/ReactiveWsConfig.java`:**

~~~java
package com.example.reactivews;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;

@Configuration
public class ReactiveWsConfig {

    @Bean
    public HandlerMapping reactiveWebSocketMapping(
            ReactiveEchoHandler handler) {
        return new SimpleUrlHandlerMapping(
                Map.of("/ws/echo", handler), -1);
    }
}
~~~

Giải thích:

- `org.springframework.web.reactive.socket.WebSocketHandler` là **interface khác** với `org.springframework.web.socket.WebSocketHandler` trong MVC.
- `session.receive()` tạo `Flux<WebSocketMessage>`, còn `session.send(Publisher<WebSocketMessage>)` trả `Mono<Void>` biểu diễn việc ghi outbound messages.
- `getPayloadAsText()` được đọc trong pipeline ngay khi nhận message. Đừng giữ/reuse buffers Netty sau khi lifecycle đã kết thúc mà chưa quản lý `retain/release`.
- `SimpleUrlHandlerMapping` map **WebSocket handshake URL** `/ws/echo` vào reactive handler, với order `-1` để ưu tiên trước một số HTTP handlers.
- Spring WebFlux Java configuration/Boot auto-configuration cung cấp `WebSocketHandlerAdapter` cho WebSocket handlers. Trong môi trường cấu hình WebFlux thủ công không dùng WebFlux config, cần tự khai báo adapter tương ứng theo tài liệu Spring Framework.
- `Mono<Void>` hoàn thành khi pipeline được kết thúc, ví dụ session đóng; không gọi `subscribe()` thủ công rồi trả response HTTP thành công ngay.

**Đây vẫn là raw WebSocket.** Chuỗi `reactive: hello` được gửi theo ứng dụng, không phải STOMP `MESSAGE` frame; `SimpleUrlHandlerMapping` không tự cung cấp `@MessageMapping` hoặc broker.

### 11.4. Browser client cho WebFlux

**Tệp `src/main/resources/static/index.html`:**

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>WebFlux raw WebSocket</title>
</head>
<body>
  <h1>Reactive WebSocket Echo</h1>
  <button id="send">Gửi hello</button>
  <pre id="log"></pre>
  <script>
    const log = document.querySelector("#log");
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(
      scheme + "//" + location.host + "/ws/echo");

    socket.onopen = () => log.textContent += "OPEN\n";
    socket.onmessage = event =>
      log.textContent += "RECV: " + event.data + "\n";
    socket.onclose = event =>
      log.textContent += "CLOSE: " + event.code + "\n";

    document.querySelector("#send").onclick = () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send("hello");
      }
    };
  </script>
</body>
</html>
~~~

Chạy tại project WebFlux riêng:

~~~bash
mvn spring-boot:run
~~~

Mở `http://localhost:8082/`, đợi `OPEN` rồi nhấn **Gửi hello**. Kỳ vọng:

~~~text
RECV: reactive: hello
~~~

Đó là **raw WebSocket exchange** do Reactor pipeline xử lý, không phải Spring MVC STOMP.

## 12. WebFlux không tự bật STOMP broker: vì sao quan trọng?

Khi bạn nhìn thấy dependency `spring-messaging` hoặc một class có tên `Message` trong project reactive, **điều đó không chứng minh** có đầy đủ STOMP over WebSocket broker cho WebFlux. Bộ cấu hình `@EnableWebSocketMessageBroker` thuộc hệ thống messaging WebSocket của Servlet/MVC và dùng nhiều handler/channel/broker components tương ứng.

Sai lầm thường thấy:

~~~java
// KHÔNG xem đây là cấu hình tương đương cho WebFlux:
// @EnableWebSocketMessageBroker
// class MyReactiveApp { ... }
~~~

Đoạn trên chỉ để nhắc ranh giới, **không phải source file runnable**. Với WebFlux raw WebSocket, bạn phải trực tiếp đọc/ghi messages hoặc dùng framework/adapter chuyên biệt. Nếu cần STOMP destinations trong kiến trúc reactive, cân nhắc:

1. **Tách WebSocket messaging gateway MVC** có STOMP integration thành service độc lập, kết nối hệ thống reactive khác qua broker/API.
2. **Xây hoặc dùng adapter STOMP** xử lý frame và routing trên WebFlux raw WebSocket handler; yêu cầu kiểm soát protocol parser, ACK, subscriptions, heartbeat, security, backpressure.
3. **Chọn protocol khác phù hợp** như RSocket, SSE cho một chiều hoặc WebSocket raw với JSON envelope do ứng dụng định nghĩa.
4. Nếu hệ thống cần bảo đảm durable delivery, dùng message broker với semantics phù hợp; đừng dùng simple in-memory broker như persistence layer.

**Không trộn hai web stacks để mong “được cả hai” miễn phí.** Nếu classpath chứa `starter-web` và `starter-webflux`, Boot 3.3 thông thường chọn Servlet MVC. Bạn có thể sử dụng WebClient reactive trong ứng dụng MVC, nhưng **inbound socket stack** vẫn là MVC/Servlet.

## 13. Broker của Spring STOMP: simple và external relay

### 13.1. Simple broker

Cấu hình trong lab:

~~~java
registry.setApplicationDestinationPrefixes("/app");
registry.enableSimpleBroker("/topic");
~~~

Simple broker:

- Giữ danh sách subscriptions của clients **trong bộ nhớ của một application instance**.
- Nhận message tới broker destinations và broadcast cho matching subscribers.
- Phù hợp demo, prototype, ứng dụng đơn instance có quy mô vừa và yêu cầu đơn giản.
- **Không** tự cung cấp persistent messaging, offline delivery hay routing xuyên nhiều Spring Boot replicas.
- Chỉ hỗ trợ **một tập con STOMP commands**; không đầy đủ ACK/receipt và những khả năng broker chuyên nghiệp.
- Có thể cấu hình scheduler để hỗ trợ STOMP heartbeats.

Nếu deployment có hai replicas A và B, user kết nối A subscribe `/topic/news`, còn application code trên B gửi message vào simple broker B, **user trên A không tự nhận**. Sticky sessions chỉ giúp giữ connection đúng instance; nó không đồng bộ subscriptions/messages giữa broker memories của A và B.

### 13.2. External broker relay

Thay simple broker bằng STOMP broker relay khi muốn broker messaging độc lập, ví dụ RabbitMQ/ActiveMQ đã bật STOMP support. Cấu hình **minh họa**:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("127.0.0.1")
            .setRelayPort(61613);
}
~~~

Đoạn method này **thay thế** `configureMessageBroker` trong `StompWebSocketConfig` của lab khi đã cài broker phù hợp; **không** bật simple broker và broker relay cùng lúc cho cùng destination prefixes. Cần có broker STOMP endpoint ở `127.0.0.1:61613`, credentials/TLS và cấu hình network đúng trước khi chạy; chỉ dán đoạn này vào lab chưa có broker sẽ khiến messaging không hoạt động.

Flow:

~~~text
Browser STOMP over WebSocket
       |
       v
Spring MVC WebSocket/STOMP endpoint
       |
       v
Spring STOMP broker relay (TCP client)
       |
       v
External STOMP broker
       |
       +--> subscriptions across app instances
       '--> routes / queues theo capabilities của broker
~~~

**Giới hạn của relay:**

- Spring không trở thành một broker durable đầy đủ; nó **chuyển tiếp** STOMP frames và phụ thuộc broker bên ngoài.
- Broker phải hỗ trợ STOMP thực sự, không phải chỉ có AMQP/Kafka port. Ví dụ RabbitMQ cần STOMP plugin/config tương ứng.
- Session authentication, destination ACL, subscriber limits và broker permissions phải cấu hình ở đúng tầng; relay không loại bỏ trách nhiệm Spring Security.
- Multi-instance subscriptions có thể sử dụng chung broker, nhưng delivery guarantee/durability/ACK/redelivery vẫn phụ thuộc broker và destination semantics.

### 13.3. `/topic` và `/queue` là những chuỗi prefix theo convention

Trong **simple broker**, `/topic` hoặc `/queue` không tự áp thuật toán publish-subscribe hay competing-consumer khác nhau theo tên. Đây chủ yếu là **prefix conventions** để route messages. Với external broker, tên destination và semantics phải theo chính broker đã chọn.

Không kết luận `/queue/orders` trong simple broker mặc nhiên là hàng đợi công việc durable chỉ dành cho một consumer. Nếu cần order processing chắc chắn, thường cân nhắc một message broker có queue semantics bền vững và transactional/outbox design.

## 14. @MessageMapping, @SendTo và gửi message chủ động

### 14.1. @MessageMapping nhận STOMP SEND

~~~java
@MessageMapping("/echo")
@SendTo("/topic/echo")
public ChatMessage echo(ChatMessage input) {
    return new ChatMessage("stomp: " + input.text());
}
~~~

Đây là method thuộc **controller của MVC STOMP lab**, không phải HTTP controller. Client gửi:

~~~text
SEND
destination:/app/echo
content-type:application/json

{"text":"hi"}^@
~~~

Spring route tới method `/echo` rồi gửi kết quả ra `/topic/echo`. Đừng hiểu `@SendTo` là HTTP redirect hoặc một URL ở browser.

### 14.2. SimpMessagingTemplate gửi từ service hoặc HTTP controller

Khi muốn đẩy một event tạo ra từ tác vụ nền/HTTP request, có thể inject `SimpMessagingTemplate` trong ứng dụng MVC STOMP:

~~~java
package com.example.ws;

import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationPublisher {

    private final SimpMessagingTemplate messaging;

    public NotificationPublisher(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    public void publish(String text) {
        messaging.convertAndSend(
                "/topic/echo",
                new ChatMessage(text));
    }
}
~~~

Đây là **class runnable nếu đặt trong project MVC STOMP lab**; nó **không tự tạo/schedule event**, chỉ cung cấp method `publish` để service khác gọi.

Đừng nhầm `convertAndSend` với gửi message trực tiếp trên một WebSocketSession raw. Nó đi qua Spring messaging infrastructure/broker và có thể broadcast tới mọi subscribers phù hợp.

### 14.3. Message theo user

STOMP trong Spring MVC có mô hình user destinations, thường dùng `/user/queue/...` và `convertAndSendToUser(...)`. Đây là abstraction **cần identity user, session mapping và authorization đúng**.

Không tự suy đoán `/user/queue/private` trong lab tự bảo vệ dữ liệu cá nhân: nếu chưa có authentication, identity mapping và security rule, topic/queue bí mật có thể bị đăng ký trái phép. User destination không phải thay thế kiểm tra quyền.

## 15. Phân biệt handshake, subscribe, broadcast và đóng kết nối

### 15.1. State machine khái quát cho raw WebSocket

~~~text
CLOSED
  |
  | HTTP Upgrade
  v
OPEN <----> TEXT / BINARY frames
  |
  | ping/pong/timeout/network failure
  v
CLOSING -> CLOSED
~~~

Raw handler cần theo dõi session lifecycle, cleanup resources, validate client messages, tránh slow consumer và xử lý close codes.

### 15.2. State machine khái quát cho STOMP-over-WebSocket

~~~text
WebSocket OPEN
    |
    | STOMP CONNECT
    v
STOMP CONNECTED
    |
    +--> SUBSCRIBE destination:/topic/echo
    |         |
    |         '--> MESSAGE events từ broker
    |
    +--> SEND destination:/app/echo
    |         |
    |         '--> @MessageMapping + broker routing
    |
    +--> UNSUBSCRIBE / ACK / NACK (nếu hỗ trợ)
    |
    '--> DISCONNECT / ERROR / broken network
                |
                v
          WebSocket closed
~~~

WebSocket OPEN mà chưa STOMP CONNECTED là trạng thái hợp lệ trong giai đoạn handshake. Browser phải có xử lý reconnect và **re-subscribe** sau khi mất kết nối nếu muốn tiếp tục nhận updates. Simple broker thường không lưu messages đã gửi khi client offline.

## 16. WebSocket ping/pong, STOMP heartbeat và idle timeout

Ba thứ thường bị lẫn:

1. **WebSocket ping/pong:** control frames ở tầng WebSocket. Browser JavaScript không expose API ping trực tiếp theo cách HTTP client native; server/runtime có thể gửi ping.
2. **STOMP heartbeat:** thông thường newline giữa các frames theo negotiation `heart-beat:cx,cy`, do STOMP peers/broker kiểm soát.
3. **Proxy/server idle timeout:** kết nối có thể bị đóng nếu proxy không nhìn thấy traffic trong thời gian quy định.

Các hệ thống thường cần điều chỉnh ping/heartbeat **cùng** proxy idle timeout. Trong Spring simple broker, STOMP heartbeat có thể cần task scheduler. Bật heartbeat ở STOMP client không có nghĩa simple broker sẽ phát heartbeat nếu chưa được cấu hình phù hợp.

**Nếu dùng SockJS**, còn có SockJS heartbeat policy riêng. Khi STOMP client và server đã negotiate heartbeat, SockJS heartbeats có thể được vô hiệu để tránh trùng. Không tự dùng “heartbeat 25 giây SockJS” làm kết luận cho tất cả WebSocket configurations.

Thực hành:

- Đặt một interval heartbeat ngắn hơn proxy idle timeout đủ xa để tránh bị timeout do jitter.
- Đo disconnections và reconnect success rate.
- Không gửi heartbeat quá dày làm tăng CPU/network trên hàng chục nghìn sockets.
- Khi disconnected, ứng dụng phải xử lý trạng thái user, subscriptions và message missed theo business contract.

## 17. Bảo mật WebSocket và STOMP

### 17.1. Origin trong WebSocket handshake

Browser WebSocket gửi `Origin`, nhưng **same-origin policy/CORS của fetch không tự áp dụng cho WebSocket handshake theo cách giống AJAX**. Server/proxy phải chủ động kiểm tra allowed origins. Spring MVC WebSocket/SockJS thường **chỉ cho same-origin mặc định**, có thể cấu hình allowed origins trong registry.

~~~java
// Minh họa config cho một frontend thật sự tin cậy:
registry.addHandler(echoHandler, "/ws/raw")
        .setAllowedOrigins("https://app.example.com");
~~~

Đây là snippet **thay thế** dòng addHandler trong lab; đừng chép literal production domain vào demo localhost rồi tưởng còn truy cập được. Nếu dùng STOMP endpoint, đặt allowed origins tại `StompEndpointRegistry`. Chỉ allow origin bạn quản lý; không dùng `*` cho app chứa cookie riêng tư.

**Origin không phải authentication.** Non-browser WebSocket clients có thể giả `Origin`; cần xác thực request và phân quyền độc lập.

### 17.2. Cookies, handshake và session

WebSocket bắt đầu bằng HTTP handshake. Nếu browser có cookie session phù hợp với host/path/SameSite/Secure, handshake có thể gửi cookie đó. Spring Security có thể xác thực principal trên HTTP handshake rồi chuyển identity vào WebSocket session/STOMP messaging.

Đừng cho browser JS tự gửi nguyên user cookie hoặc token sang origin lạ để “sửa lỗi CORS”. Browser WebSocket API cũng **không cho tùy ý đặt custom Authorization header** như `fetch`. Nếu dùng token trong STOMP `CONNECT` headers, server cần có channel interceptor xác thực token; chỉ ghi header `Authorization: Bearer ...` vào STOMP frame **không** làm Spring Security HTTP tự nhận nó.

### 17.3. CSRF / cross-site WebSocket hijacking

Nếu handshake dùng cookie session và endpoint cho mọi origin, một trang độc hại có thể thử mở socket trong ngữ cảnh nạn nhân. Cần:

- Kiểm tra allowed origins đúng trust boundary.
- Authentication và authorization trên handshake/message.
- Bảo vệ CSRF theo thiết kế Spring Security cho STOMP `CONNECT` khi dùng security messaging tương ứng, không tự loại bỏ vì “chỉ là WebSocket”.
- SameSite/Secure/HttpOnly cookie policy phù hợp và TLS `wss://` ở production.
- Kiểm tra protocol/destination/message headers và dữ liệu truyền theo user quyền.

STOMP destination như `/topic/public` và `/user/queue/private` có mức phân quyền khác nhau. Chỉ chặn handshake chưa đủ nếu người đã login vẫn có thể gửi `SEND` tới bất cứ destination nào hoặc subscribe thông tin của user khác.

### 17.4. Authorization ở tầng message

Với Spring Security WebSocket message security trong Servlet STOMP, dùng authorization manager/channel interceptor phù hợp để quy định ai được `SEND` tới `/app/...` và ai được `SUBSCRIBE` vào `/topic/...`/`/user/...`. Một `@MessageMapping` method không tự chặn người dùng không có quyền.

Một số rủi ro:

- **Spoof người gửi**: không tin username/userId do client gửi trong body; lấy principal đã xác thực ở server.
- **Subscription leak**: cấm subscribe destination chứa dữ liệu của người khác nếu không được phép.
- **Flooding**: giới hạn số connections/subscriptions/messages/byte/s.
- **Slow consumer**: giới hạn send buffer và thời gian gửi, close session quá chậm.
- **Payload injection/XSS**: client render text bằng `textContent` hoặc escaping, không dựng HTML trực tiếp từ message không đáng tin.
- **Secrets trong log**: không log raw cookie/token/nhạy cảm trong STOMP headers, nhất là `CONNECT`.
- **TLS**: dùng `wss://` từ HTTPS frontend và bảo vệ proxy→app nếu policy yêu cầu.

## 18. Reverse proxy, load balancer và nhiều replicas

### 18.1. Proxy phải hỗ trợ WebSocket Upgrade

Một NGINX HTTP/1.1 reverse proxy thường cần thiết lập các header chuyển tiếp WebSocket:

~~~nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    # Cần SSL certificate/key hợp lệ ở đây trong triển khai thật.

    location /ws/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_read_timeout 300s;
    }
}
~~~

Đoạn trên **chưa phải file NGINX hoàn chỉnh runnable**: nó không định nghĩa ssl_certificate, ssl_certificate_key, chính sách security và toàn bộ http context. Ý chính là WebSocket handshake cần proxy chuyển đúng `Upgrade`/`Connection` ở chặng HTTP/1.1 và timeout dài phù hợp.

Nếu proxy không hỗ trợ upgrade hoặc chặn handshake, browser thường báo WebSocket connection failure, 400/404/426/502 hoặc 101 không xuất hiện. Không có nghĩa STOMP logic sai: cần xác minh **transport** trước.

### 18.2. Sticky sessions không đồng nghĩa broker cluster

~~~text
Users A -> App replica 1 -> simple broker 1 (memory)
Users B -> App replica 2 -> simple broker 2 (memory)
~~~

Nếu service có hai Spring Boot instances và mỗi instance dùng simple broker, subscriptions không tự chia sẻ. Load balancer có sticky routing có thể giữ WebSocket của user với cùng replica, nhưng **event trên replica 2 không tự tới subscribers replica 1**.

Để broadcast xuyên replicas, cân nhắc:

- External STOMP broker relay (với broker được triển khai HA phù hợp).
- Publish-subscribe bus riêng để mỗi instance fan-out tới local sockets, nếu bạn làm raw WebSocket.
- Redis pub/sub cho ephemeral broadcast nếu chấp nhận không durable; Redis Streams/Kafka/RabbitMQ nếu cần đảm bảo khác, theo thiết kế phù hợp.
- Application-level event routing theo user/tenant và quyền truy cập.

**Bài toán message durability khác bài toán WebSocket session.** Kết nối bị đứt cần reconnect/resubscribe; durable queue/offline inbox phải được xây riêng theo business requirements.

## 19. Hiệu năng: số kết nối, threads, buffers, backpressure

WebSocket giữ kết nối kéo dài; không giống HTTP request ngắn mà server có thể giải phóng socket ngay sau response.

Trong Spring MVC raw:

- WebSocket callbacks có thể chạy trong threads do Servlet/WebSocket runtime quản lý.
- Khi gọi `WebSocketSession.sendMessage` từ nhiều threads, chú ý serialization/`ConcurrentWebSocketSessionDecorator` để không gửi concurrent trên cùng session.
- Đặt max session idle timeout, max message size, send time/buffer limits phù hợp; tránh lưu message history không giới hạn trong RAM.
- STOMP broker có `clientInboundChannel`, `brokerChannel` và `clientOutboundChannel`, các executor/queues có thể tăng backlog; cần đo chứ không chỉ tăng thread pool.

Trong WebFlux raw:

- `Flux<WebSocketMessage>` và `Mono<Void>` biểu diễn pipeline reactive; tránh `block()`/blocking JDBC/filesystem ở event loop.
- Khi xử lý payload buffer Netty, tôn trọng lifecycle `DataBuffer`; không giữ/reuse sau khi đã release, và phải xử lý error/cancel.
- Reactive API giúp biểu diễn backpressure và tránh chiếm thread cho I/O chờ, **không tự bảo đảm** ứng dụng không vượt RAM khi consumer chậm.
- Một pipeline `session.receive().collectList()` tới khi socket đóng có thể giữ dữ liệu vô hạn; không làm với streams lâu dài.

### 19.1. STOMP có overhead

Một STOMP SEND frame chứa command, headers, terminator bên cạnh payload. Nếu gửi telemetry nhỏ hàng chục nghìn lần/giây, overhead có thể đáng kể. Nhưng broker routing có thể giảm code tự viết và chi phí vận hành ở phía ứng dụng. Không kết luận loại nào nhanh hơn mà không đo:

- số sockets đồng thời;
- message rate và kích thước payload;
- network bandwidth và CPU parse;
- broker queue/backlog;
- p95/p99 end-to-end delivery;
- dropped messages và reconnect;
- memory/send buffer per session.

**Không dùng “WebFlux là reactive” để suy ra STOMP broker của MVC cũng tự chạy reactive.** Mỗi stack có execution model riêng.

## 20. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| WebSocket handshake trả 404 | Sai URL/path hoặc handler chưa đăng ký | So `/ws/raw`, `/ws/stomp` với config |
| Browser không thấy status 101 | Proxy không upgrade, TLS/origin, route hoặc error | Kiểm tra Network WS handshake và proxy logs |
| Raw echo chạy nhưng STOMP không CONNECTED | Gửi JSON/plain text thay vì STOMP frame, thiếu NUL, sai subprotocol | Dùng STOMP client, kiểm tra CONNECT/CONNECTED |
| STOMP CONNECTED nhưng không có message | Chưa SUBSCRIBE, sai destination hoặc gửi quá sớm | So `/app/echo` và `/topic/echo`; subscribe trước |
| `@MessageMapping` không được gọi | SEND tới `/topic` thay vì `/app`, sai prefix | Kiểm tra destination routing |
| `/ws/stomp` trả 101 nhưng send trả lỗi | STOMP frame malformed, auth/CSRF, converter lỗi | Xem STOMP ERROR frame và backend logs |
| `/topic` không broadcast qua 2 replicas | Simple brokers local in-memory | Dùng broker relay hoặc bus fan-out phân tán |
| Có `/queue` nhưng không durable | Prefix chỉ là convention trong simple broker | Dùng external broker/queue semantics phù hợp |
| Thêm `@EnableWebSocketMessageBroker` vào WebFlux nhưng không có routing mong muốn | Nhầm hỗ trợ Servlet STOMP với reactive raw WS | Chọn MVC STOMP hoặc adapter riêng |
| Có cả starter-web và starter-webflux, stack khác dự tính | Boot ưu tiên MVC | Kiểm tra WebApplicationType và dependency tree |
| Client nhận ERROR khi CONNECT | Sai version, auth, security policy, frame headers | Kiểm tra frame từ client và channel interceptors |
| Gửi raw text vào endpoint STOMP | Server kỳ vọng STOMP protocol | Dùng frame CONNECT/SEND đúng |
| Gửi STOMP frame vào raw endpoint | Raw handler xem là text, không route | Chọn đúng endpoint và protocol |
| Client disconnect sau 60s idle | Proxy/load balancer timeout hoặc thiếu heartbeat | Cấu hình heartbeat/ping và proxy read timeout |
| WebSocket chạy localhost nhưng không chạy HTTPS site | Dùng `ws://` từ HTTPS, cert/proxy hoặc origin | Dùng `wss://`, kiểm TLS và allowed origins |
| Không lấy được JWT từ browser custom WS headers | Browser WebSocket API không hỗ trợ arbitrary headers | Dùng cookie handshake hoặc STOMP CONNECT/token strategy có kiểm soát |
| User xem được topic của user khác | Thiếu per-destination authorization | Dùng Spring Security message authorization |
| Server memory tăng khi user gửi nhiều messages | Unbounded queues/buffers, slow consumers | Đặt size/rate limits, backpressure, discard/cleanup |
| Raw session bị lỗi gửi đồng thời | Nhiều threads cùng send trên Servlet session | Serialize sends hoặc decorator |
| Không nhận được message khi offline | WebSocket/simple broker không durable | Thiết kế replay/outbox/offline inbox riêng |

### 20.1. Quy trình debug theo từng lớp

1. **Transport:** client có mở thành công `ws://`/`wss://` không? HTTP Upgrade trả 101 hay error? Proxy có support không?
2. **Protocol:** endpoint đang là raw hay STOMP? Có `CONNECT`/`CONNECTED` không, đã negotiate subprotocol nào?
3. **Routing:** với STOMP, client `SEND` tới `/app/...`, `SUBSCRIBE` tới broker destination đúng chưa?
4. **Converter:** `content-type`, JSON field names, DTO record và message converter có khớp không?
5. **Authorization:** handshake Origin, principal, STOMP CONNECT CSRF, ACL cho SEND/SUBSCRIBE?
6. **Distribution:** simple broker local hay external relay? Nhiều replicas có cùng event bus không?
7. **Resources:** có idle timeout, slow clients, send buffer overflow, heartbeat mismatch hoặc threads/backpressure không?

**Phân tầng vấn đề trước khi sửa.** Một kết nối WebSocket mở thành công chưa chứng minh STOMP routing hoạt động; một `@MessageMapping` được gọi chưa chứng minh user được phép subscribe và nhận message.

## 21. Những nhầm lẫn quan trọng

1. **“STOMP là WebSocket.”** Sai: STOMP là messaging protocol, có thể chạy qua WebSocket hoặc TCP.
2. **“WebSocket tự có subscribe/topic.”** Sai: raw WebSocket không định nghĩa pub/sub; ứng dụng phải tự xây.
3. **“Có broker thì mọi message được lưu lại.”** Sai: simple broker của Spring giữ subscriptions in-memory, không tự lưu message bền vững.
4. **“WebFlux không hỗ trợ WebSocket.”** Sai: WebFlux có reactive WebSocket API.
5. **“WebFlux cũng có @EnableWebSocketMessageBroker giống MVC.”** Không phải tích hợp built-in tương đương trong WebFlux; cần adapter/library/kiến trúc khác nếu muốn STOMP.
6. **“Có @MessageMapping thì URL /app/echo mở được bằng HTTP GET.”** Sai: đó là STOMP destination, không phải HTTP endpoint.
7. **“SockJS chính là STOMP.”** Sai: SockJS là transport fallback, STOMP là lớp messaging.
8. **“/queue trong simple broker tự là hàng đợi durable.”** Sai: prefix không tự định nghĩa tính bền vững.
9. **“Handshake 101 nghĩa là STOMP đã CONNECTED.”** Sai: STOMP cần bước CONNECT/CONNECTED sau WebSocket handshake.
10. **“CORS không cần lo cho WebSocket.”** Không đúng: WebSocket handshake phải có Origin/trust/security policy riêng, không được dựa vào browser CORS logic.
11. **“Dùng wss:// ở edge nghĩa là mọi hop backend đều được mã hóa.”** Không tự đúng: proxy có thể terminate TLS và gửi HTTP nội bộ.
12. **“WebSocket luôn ưu việt hơn SSE/HTTP polling.”** Không: chọn theo hướng dữ liệu, yêu cầu browser, hạ tầng và chi phí vận hành.

## 22. Bài tập tự kiểm tra

**Câu 1.** Client dùng `new WebSocket("ws://...")` và gửi `{"text":"hi"}`. Điều đó có tự bật STOMP messaging không?

**Câu 2.** WebSocket handshake trả `101` nhưng browser không nhận message từ `@MessageMapping`. Vì sao cần kiểm tra thêm STOMP CONNECT và destination?

**Câu 3.** Phân biệt `/ws/stomp`, `/app/echo` và `/topic/echo` trong ví dụ MVC.

**Câu 4.** Khi client `SUBSCRIBE /topic/echo` rồi `SEND /app/echo`, message chạy qua thành phần nào?

**Câu 5.** Project chỉ có `spring-boot-starter-webflux`. Muốn raw echo handler cần API nào? Có thể dùng nguyên `TextWebSocketHandler` của Servlet không?

**Câu 6.** Vì sao `@EnableWebSocketMessageBroker` không thể được xem như chức năng tự động của mọi project WebFlux?

**Câu 7.** Hai replicas MVC dùng simple broker, một user ở A và một user ở B. Event từ A có tự phát tới user ở B không?

**Câu 8.** STOMP có `ACK` nhưng simple broker không có đầy đủ semantics của một durable broker. Điều đó ảnh hưởng đến lời hứa delivery như thế nào?

**Câu 9.** Browser HTTPS mở `ws://` tới production API và gặp lỗi. Cần cân nhắc URL/TLS nào?

**Câu 10.** Vì sao STOMP `/user/queue/private` không tự bảo mật khi chưa cấu hình authentication và authorization?

**Câu 11.** Khi client mất mạng và reconnect, có chắc mọi message bị bỏ lỡ sẽ được phát lại không?

**Câu 12.** Khi gửi raw WebSocket từ hai threads vào cùng Servlet WebSocketSession, cần chú ý gì?

**Đáp án định hướng:**

1. Không. WebSocket payload chỉ là text; STOMP cần đúng frame/CONNECT/destination và STOMP endpoint.
2. Vì WebSocket OPEN khác STOMP CONNECTED; `@MessageMapping` chỉ route các STOMP SEND messages có destination phù hợp.
3. `/ws/stomp` là handshake URL; `/app/echo` là app message destination; `/topic/echo` là broker destination.
4. STOMP inbound channel route `/app/echo` tới `@MessageMapping`, `@SendTo` đưa kết quả vào broker, broker gửi `MESSAGE` cho subscribers.
5. Dùng `org.springframework.web.reactive.socket.WebSocketHandler`, `WebSocketSession`, `Flux/Mono` và `SimpleUrlHandlerMapping`; không copy nguyên Servlet handler.
6. Vì STOMP broker/message channels của Spring thuộc tích hợp messaging Servlet; WebFlux chỉ có raw reactive WebSocket API mặc định.
7. Không mặc định; simple broker mỗi instance lưu subscriptions riêng, cần relay/bus phân tán.
8. Không thể cam kết durable delivery/ack/replay chỉ vì định dạng STOMP hỗ trợ ACK; phải chọn broker có semantics phù hợp.
9. Dùng `wss://` với certificate/proxy/allowed origins đúng; frontend HTTPS thường không được dùng insecure ws scheme.
10. Destination chỉ là routing convention; cần danh tính user và ACL SEND/SUBSCRIBE.
11. Không với raw WebSocket/simple broker; cần replay/offline storage khi nghiệp vụ đòi hỏi.
12. Nên serialize sends hoặc dùng `ConcurrentWebSocketSessionDecorator` và giới hạn buffer/time.

## 23. Checklist triển khai

- [ ] Xác định rõ mục tiêu: raw WebSocket hay STOMP messaging; không trộn endpoint và payload formats.
- [ ] Xác nhận app đang chạy **MVC/Servlet** hay **WebFlux** thực tế.
- [ ] Với MVC STOMP, đã có `spring-boot-starter-websocket`, `@EnableWebSocketMessageBroker` và broker prefixes phù hợp.
- [ ] Với WebFlux, dùng reactive `WebSocketHandler`; không giả định có MVC STOMP broker.
- [ ] Client đã kiểm tra WebSocket OPEN **và** STOMP CONNECTED khi cần.
- [ ] Phân biệt handshake URL, application destination và broker destination.
- [ ] Cân nhắc simple broker chỉ cho phạm vi in-memory/đơn instance; có kế hoạch external relay khi scale.
- [ ] Định nghĩa rõ subscriptions, user destinations, delivery/ACK/replay yêu cầu thực tế.
- [ ] Có TLS `wss://`, proxy Upgrade, timeout và heartbeat theo topology.
- [ ] Kiểm tra Origin allowlist, authentication, session/CSRF và per-message authorization.
- [ ] Giới hạn số connections, subscriptions, message size, rate và slow-consumer buffer.
- [ ] Có cleanup session, reconnect/backoff, resubscribe và hành vi khi server restart.
- [ ] Không log token/cookie và không render message text bằng HTML không an toàn.
- [ ] Có metrics số socket mở, STOMP CONNECT/ERROR, inbound/outbound queue, sends, latency và disconnects.
- [ ] Đã thử hai tabs, hai replicas, client offline, invalid frames, 404/101 và broker downtime.

## 24. Tài liệu tham khảo

- Spring Framework — WebSocket (Servlet), `WebSocketHandler` và handshake: https://docs.spring.io/spring-framework/reference/web/websocket/server.html
- Spring Framework — STOMP over WebSocket overview và protocol: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html
- Spring Framework — Enable STOMP/message broker trong MVC: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html
- Spring Framework — STOMP message flow: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html
- Spring Framework — Simple Broker: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html
- Spring Framework — External Broker Relay: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html
- Spring Framework — STOMP annotated controllers và user destinations: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html
- Spring Framework — Reactive WebFlux WebSocket API: https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html
- Spring Framework — WebFlux config và WebSocketHandlerAdapter: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Boot 3.3 — WebSocket server auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/messaging/websockets.html
- Spring Security — WebSocket/STOMP authorization: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- Spring Security — WebSocket CSRF and same-origin policy: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- RFC 6455 — The WebSocket Protocol: https://www.rfc-editor.org/rfc/rfc6455
- RFC 8441 — Bootstrapping WebSockets with HTTP/2: https://www.rfc-editor.org/rfc/rfc8441
- STOMP Protocol Specification 1.2: https://stomp.github.io/stomp-specification-1.2.html

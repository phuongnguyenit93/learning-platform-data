# Quan hệ giữa HTTP handshake, WebSocket và giao thức ứng dụng

## 1. Bức tranh tổng thể

Một kết nối WebSocket trong ứng dụng Spring thường liên quan đến ba lớp giao thức có nhiệm vụ khác nhau:

1. **HTTP handshake** khởi tạo kết nối. Client gửi một HTTP request yêu cầu chuyển giao thức; server xác nhận bằng response thích hợp.
2. **WebSocket** duy trì kênh hai chiều trên kết nối TCP đã được thiết lập. Client và server có thể gửi frame qua lại mà không phải tạo một HTTP request cho từng message.
3. **Giao thức ứng dụng** quy định ý nghĩa của dữ liệu trao đổi. Có thể dùng STOMP, JSON theo quy ước riêng hoặc một định dạng khác mà cả hai phía cùng hiểu.

WebSocket là giao thức truyền tải. Nó quy định cách mở kết nối, đóng kết nối, gửi text/binary frame, ping/pong và quản lý dữ liệu ở tầng frame. Nó không quy định một message có nghĩa là chat, cập nhật đơn hàng, subscribe vào topic hay gọi một thao tác nghiệp vụ.

STOMP là một ví dụ về giao thức ứng dụng chạy trên WebSocket. STOMP bổ sung các command như CONNECT, SEND, SUBSCRIBE, MESSAGE và DISCONNECT, cùng header destination, content-type, receipt và body. Spring có thể giải mã STOMP frame thành Spring Message, định tuyến qua MessageChannel, gọi @MessageMapping và chuyển kết quả về client.

~~~mermaid
flowchart TD
    A[HTTP request: WebSocket handshake] --> B[HTTP 101 Switching Protocols]
    B --> C[WebSocket connection]
    C --> D[WebSocket text/binary frames]
    D --> E[Application protocol: STOMP or custom JSON]
    E --> F[Spring Message and headers]
    F --> G[Controller, broker or application handler]
    G --> H[Outbound application message]
    H --> I[STOMP or custom protocol encoding]
    I --> J[WebSocket frame to client]
~~~

Nếu nắm rõ ba lớp này, ta sẽ biết nên sửa lỗi ở đâu: lỗi 403 khi bắt tay thuộc HTTP/security/origin; lỗi không nhận được frame thuộc WebSocket transport; lỗi destination không được định tuyến thuộc STOMP hoặc Spring messaging; lỗi JSON không deserialize được thuộc message converter và định dạng ứng dụng.

## 2. HTTP handshake: yêu cầu chuyển sang WebSocket

### 2.1. Vì sao WebSocket bắt đầu bằng HTTP?

Trong mô hình WebSocket truyền thống trên HTTP/1.1, client mở một HTTP request đến endpoint đã đăng ký, ví dụ /ws. Request mang các header yêu cầu nâng cấp kết nối:

~~~http
GET /ws HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Sec-WebSocket-Protocol: v12.stomp
Origin: http://localhost:3000
~~~

Các header quan trọng:

| Header | Vai trò |
|---|---|
| Upgrade: websocket | Yêu cầu chuyển giao thức sang WebSocket |
| Connection: Upgrade | Đánh dấu yêu cầu nâng cấp connection |
| Sec-WebSocket-Key | Giá trị ngẫu nhiên dùng trong quá trình xác minh handshake |
| Sec-WebSocket-Version | Phiên bản WebSocket mà client hỗ trợ; phiên bản phổ biến hiện nay là 13 |
| Sec-WebSocket-Protocol | Danh sách subprotocol mà client muốn thương lượng, ví dụ v12.stomp |
| Origin | Origin của trang web khởi tạo kết nối; server có thể dùng để kiểm tra chính sách origin |

Sec-WebSocket-Key không phải mật khẩu, access token hoặc thông tin xác thực người dùng. Nó tham gia vào phép tính Sec-WebSocket-Accept để client xác nhận server đã thực hiện đúng handshake.

### 2.2. Server trả về 101 Switching Protocols

Nếu server chấp nhận yêu cầu và hai phía thương lượng thành công, response HTTP/1.1 có dạng:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
Sec-WebSocket-Protocol: v12.stomp
~~~

HTTP status 101 cho biết server chấp nhận chuyển giao thức. Sec-WebSocket-Accept được tính từ Sec-WebSocket-Key theo quy tắc của RFC 6455. Nếu có thương lượng subprotocol, server trả về một giá trị mà client đã đề xuất và server chấp nhận.

Sau response này, kết nối TCP tiếp tục được sử dụng cho WebSocket. Các message tiếp theo đi dưới dạng WebSocket frame trên cùng kết nối; chúng không phải các HTTP GET/POST mới.

Đây là handshake HTTP/1.1 cổ điển. WebSocket trên HTTP/2 có thể dùng cơ chế extended CONNECT theo RFC 8441 khi hạ tầng client/server hỗ trợ; không nên giả định mọi proxy hoặc server đều hỗ trợ cơ chế đó.

### 2.3. Điều gì xảy ra nếu handshake thất bại?

Nếu endpoint không tồn tại, origin bị từ chối, người dùng chưa xác thực hoặc proxy không chuyển tiếp yêu cầu Upgrade, server có thể trả về response HTTP lỗi như 400, 403 hoặc 404 thay vì 101.

Các proxy và load balancer đứng trước Spring phải hỗ trợ kết nối WebSocket. Với HTTP/1.1, chúng cần chuyển tiếp các header Upgrade/Connection và giữ kết nối đủ lâu. Nếu proxy đóng connection do idle timeout quá ngắn, WebSocket sẽ bị ngắt dù ứng dụng Spring vẫn chạy.

Khi triển khai sau reverse proxy, cần kiểm tra:

- Proxy có chuyển tiếp WebSocket upgrade request không.
- TLS kết thúc ở proxy hay ở ứng dụng.
- Proxy có cấu hình idle timeout phù hợp với heartbeat/keepalive không.
- Load balancer có duy trì một WebSocket connection trên cùng backend trong suốt vòng đời kết nối không.
- Ứng dụng có xử lý reconnect ở client sau khi mạng hoặc backend bị gián đoạn không.

## 3. WebSocket: kênh truyền tải hai chiều

Sau handshake, WebSocket duy trì một kênh full-duplex. Client có thể gửi dữ liệu bất cứ lúc nào; server cũng có thể chủ động gửi dữ liệu về client mà không cần đợi một HTTP request mới.

WebSocket định nghĩa hai loại message dữ liệu:

- **Text message** chứa dữ liệu dạng văn bản, thường là UTF-8.
- **Binary message** chứa dữ liệu nhị phân.

WebSocket còn có các control frame:

- Ping và Pong hỗ trợ kiểm tra trạng thái kết nối.
- Close dùng để bắt đầu hoặc phản hồi việc đóng kết nối.

Một message có thể được chia thành nhiều frame ở tầng transport. Ứng dụng thường làm việc với message đã được WebSocket implementation ghép lại, thay vì tự xử lý từng byte của frame.

WebSocket không hiểu nội dung text là JSON, STOMP, XML hay chuỗi tùy ý. Nếu server nhận được một text message như:

~~~json
{"type":"chat","text":"Xin chào"}
~~~

thì đó chỉ là text payload ở tầng WebSocket. Ứng dụng phải có quy tắc riêng để parse type, xác định destination, kiểm tra quyền và gọi handler.

### 3.1. WebSocket khác HTTP request-response

| HTTP/REST | WebSocket |
|---|---|
| Thường có một request và một response cho mỗi thao tác | Một kết nối lâu dài mang nhiều message hai chiều |
| Server thường trả lời khi nhận request | Server có thể chủ động gửi message |
| Routing dựa trên URL, method và HTTP headers của từng request | URL chủ yếu dùng cho handshake; message sau đó cần giao thức ứng dụng để định tuyến |
| Phù hợp với thao tác request-response độc lập | Phù hợp với tương tác hai chiều liên tục, cập nhật real-time |
| Mỗi request thường kết thúc sau response | Connection tồn tại đến khi một phía đóng hoặc mạng bị gián đoạn |

WebSocket không thay thế mọi API HTTP. Ứng dụng có thể dùng HTTP cho đăng nhập, truy vấn dữ liệu ban đầu và thao tác CRUD; sau đó dùng WebSocket để nhận thông báo hoặc trao đổi sự kiện theo thời gian thực.

### 3.2. Ping/Pong và heartbeat

WebSocket Ping/Pong là control frame ở tầng transport. STOMP có cơ chế heartbeat riêng được thương lượng qua header heart-beat của CONNECT/CONNECTED frame.

Hai cơ chế này không giống nhau:

- WebSocket Ping/Pong kiểm tra hoạt động của kết nối WebSocket.
- STOMP heartbeat giúp hai phía phát hiện việc ngừng trao đổi ở tầng STOMP.
- Proxy/load balancer có thể có idle timeout riêng, nên cần cấu hình heartbeat và timeout phù hợp.

Nếu dùng STOMP, có thể bật heartbeat ở STOMP client. Không nên coi heartbeat là cơ chế đảm bảo message nghiệp vụ đã được xử lý thành công; nó chỉ giúp phát hiện tình trạng kết nối.

## 4. Giao thức ứng dụng: STOMP hoặc định dạng riêng

### 4.1. Vì sao cần giao thức ứng dụng?

WebSocket chỉ cung cấp khả năng vận chuyển dữ liệu. Hai phía vẫn cần thống nhất:

- Message thuộc loại nào.
- Message gửi đến destination nào.
- Client đăng ký nhận dữ liệu bằng cách nào.
- Cấu trúc header và payload.
- Cách báo lỗi, xác nhận nhận message hoặc đóng phiên ứng dụng.
- Quy tắc tương thích phiên bản giữa client và server.

Có hai hướng thường gặp:

**Dùng giao thức có sẵn**, ví dụ STOMP. Client và server dùng chung command, header và quy tắc frame. Spring có sẵn decoder, encoder, message routing, broker và annotation support.

**Tự định nghĩa giao thức**, ví dụ JSON có trường type, destination, requestId và payload. Cách này linh hoạt nhưng ứng dụng phải tự triển khai parsing, validation, routing, error handling, versioning, authentication và các quy tắc tương thích.

Không nên tự xây giao thức nếu STOMP đã đáp ứng yêu cầu. Nếu dùng JSON riêng, hãy viết tài liệu schema và kiểm thử tương thích giữa các phiên bản client/server.

### 4.2. STOMP là gì?

STOMP (Simple Text Oriented Messaging Protocol) là giao thức nhắn tin hướng text. STOMP có thể chạy qua TCP trực tiếp hoặc được dùng như một subprotocol trên WebSocket.

Một STOMP frame gồm:

1. Command, ví dụ SEND hoặc SUBSCRIBE.
2. Các dòng header dạng key:value.
3. Một dòng trống ngăn cách header và body.
4. Body nếu command có nội dung.
5. Ký tự NUL kết thúc frame.

Ví dụ frame SEND:

~~~text
SEND
destination:/app/chat.send
content-type:application/json

{"from":"Linh","text":"Xin chào"}<NUL>
~~~

<NUL> trong ví dụ là ký hiệu minh họa cho byte NUL kết thúc frame, không phải chuỗi ký tự mà client gửi nguyên văn.

Một số command thường gặp:

| Command | Hướng | Ý nghĩa |
|---|---|---|
| CONNECT | Client → Server | Bắt đầu phiên STOMP trên kết nối WebSocket đã mở |
| CONNECTED | Server → Client | Xác nhận phiên STOMP được thiết lập |
| SEND | Client → Server | Gửi một message đến destination |
| SUBSCRIBE | Client → Server | Đăng ký nhận message từ destination |
| UNSUBSCRIBE | Client → Server | Hủy đăng ký |
| MESSAGE | Server → Client | Gửi message đến subscriber |
| RECEIPT | Server → Client | Xác nhận một frame khi client yêu cầu receipt |
| ERROR | Server → Client | Báo lỗi giao thức hoặc lỗi xử lý |
| DISCONNECT | Client → Server | Yêu cầu kết thúc phiên STOMP |

### 4.3. Thương lượng subprotocol trong handshake

Client có thể gửi Sec-WebSocket-Protocol để đề xuất subprotocol. Với STOMP 1.2, một giá trị phổ biến là v12.stomp.

Ví dụ:

~~~http
Sec-WebSocket-Protocol: v12.stomp, v11.stomp
~~~

Server chọn một phiên bản được hỗ trợ và trả lại trong response handshake. Việc thương lượng này diễn ra ở HTTP handshake, trước khi STOMP CONNECT frame được gửi.

Cần phân biệt hai bước:

- **WebSocket handshake**: mở kênh transport và có thể thương lượng subprotocol.
- **STOMP CONNECT**: bắt đầu phiên STOMP trên kênh WebSocket vừa mở.

Một HTTP handshake thành công với status 101 chưa có nghĩa là STOMP session đã kết nối thành công. Client còn phải gửi CONNECT và nhận CONNECTED.

## 5. Ba lớp giao thức trong một phiên STOMP over WebSocket

~~~mermaid
sequenceDiagram
    participant C as Browser/STOMP client
    participant S as Spring WebSocket
    participant M as Spring Messaging
    participant B as Message broker

    C->>S: HTTP GET /ws + Upgrade: websocket
    S-->>C: HTTP 101 Switching Protocols
    C->>S: WebSocket text frame chứa STOMP CONNECT
    S->>M: Decode STOMP thành Spring Message
    M->>B: CONNECT / đăng ký phiên
    B-->>M: STOMP CONNECTED
    M-->>S: Encode STOMP CONNECTED
    S-->>C: WebSocket frame chứa CONNECTED
    C->>S: WebSocket frame chứa SUBSCRIBE /topic/chat
    S->>M: STOMP SUBSCRIBE
    M->>B: Lưu subscription
    C->>S: WebSocket frame chứa SEND /app/chat.send
    S->>M: STOMP SEND thành Spring Message
    M->>M: Định tuyến đến @MessageMapping
    M->>B: Gửi kết quả đến brokerChannel
    B-->>M: MESSAGE cho subscriber
    M-->>S: Encode STOMP MESSAGE
    S-->>C: WebSocket frame chứa MESSAGE
~~~

HTTP handshake chỉ xuất hiện lúc mở kết nối. Sau đó, STOMP frame được gửi bên trong WebSocket message. Spring giải mã frame thành Spring Message, định tuyến qua các channel nội bộ, rồi mã hóa kết quả thành STOMP frame để gửi ngược lại.

## 6. Spring hỗ trợ WebSocket ở những tầng nào?

Spring Framework cung cấp hai hướng tích hợp thường dùng.

### 6.1. Raw WebSocket API

Dùng WebSocket API trực tiếp khi ứng dụng muốn tự định nghĩa định dạng message và cách xử lý.

Các thành phần chính:

- WebSocketHandler: contract xử lý WebSocket session.
- TextWebSocketHandler: lớp tiện ích xử lý text message.
- BinaryWebSocketHandler: lớp tiện ích xử lý binary message.
- WebSocketSession: đại diện cho phiên WebSocket đã được mở.
- WebSocketConfigurer: đăng ký handler và URL endpoint.
- HandshakeInterceptor: can thiệp trước/sau HTTP handshake.
- DefaultHandshakeHandler: thực hiện thương lượng handshake, origin và subprotocol.

Ví dụ handler echo:

~~~java
package com.example.websocket;

import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

public class EchoHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws Exception {

        String response = "Echo: " + message.getPayload();
        session.sendMessage(new TextMessage(response));
    }
}
~~~

Đăng ký handler:

~~~java
package com.example.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class RawWebSocketConfig implements WebSocketConfigurer {

    @Override
    public void registerWebSocketHandlers(
            WebSocketHandlerRegistry registry) {

        registry.addHandler(new EchoHandler(), "/echo")
            .setAllowedOrigins("http://localhost:3000");
    }
}
~~~

Client kết nối ws://localhost:8080/echo và gửi một text message. Server trả về chuỗi Echo cùng payload.

Đây là ví dụ raw WebSocket. Handler tự định nghĩa nội dung text và không tự có STOMP command, destination hoặc broker subscription.

Nếu gửi message trực tiếp qua WebSocketSession từ nhiều thread, cần đồng bộ thao tác gửi vì chuẩn WebSocket session không bảo đảm nhiều thread có thể gửi đồng thời an toàn. Spring cung cấp ConcurrentWebSocketSessionDecorator để hỗ trợ serialize việc gửi.

### 6.2. STOMP over WebSocket với Spring Messaging

Dùng STOMP khi cần message routing, subscription, publish/subscribe và tích hợp với broker.

Các thành phần chính:

- @EnableWebSocketMessageBroker: bật hạ tầng STOMP message broker.
- WebSocketMessageBrokerConfigurer: cấu hình endpoint, broker và transport.
- StompEndpointRegistry: đăng ký URL mà client dùng để handshake.
- MessageBrokerRegistry: cấu hình destination prefix và broker.
- @MessageMapping: ánh xạ destination đến phương thức controller.
- @SendTo: xác định destination gửi kết quả.
- SimpMessagingTemplate: gửi message từ bất kỳ component Spring nào.
- ChannelInterceptor: can thiệp Spring Message trên inbound/outbound channel.

Với STOMP, Spring chịu trách nhiệm chuyển STOMP frame thành Spring Message, định tuyến, chuyển đổi payload và encode message trả về thành STOMP frame.

## 7. Phân biệt WebSocket endpoint và STOMP destination

Đây là điểm dễ nhầm khi cấu hình Spring.

| Giá trị | Ví dụ | Vai trò |
|---|---|---|
| HTTP/WebSocket endpoint | /ws | URL client dùng để mở kết nối và thực hiện handshake |
| Application destination prefix | /app | Prefix định tuyến STOMP SEND đến controller |
| Broker destination | /topic/chat | Destination client SUBSCRIBE và broker phát MESSAGE |
| @MessageMapping path | /chat.send | Đường dẫn nghiệp vụ được ghép sau prefix /app |

Ví dụ:

- Client mở kết nối đến ws://localhost:8080/ws.
- Client gửi STOMP SEND đến /app/chat.send.
- Spring loại prefix /app và ánh xạ /chat.send đến @MessageMapping("/chat.send").
- Controller trả kết quả đến /topic/chat.
- Broker phát MESSAGE đến các client đã SUBSCRIBE /topic/chat.

Đường dẫn /app/chat.send không phải HTTP endpoint và không thực hiện một HTTP POST. Nó là destination trong STOMP frame chạy bên trong WebSocket connection.

## 8. Cấu hình STOMP broker trong Spring

Spring Framework 6.2 có thể bật STOMP qua hai module spring-messaging và spring-websocket.

Cấu hình cơ bản:

~~~java
package com.example.websocket;

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
        registry.addEndpoint("/ws")
            .setAllowedOrigins("http://localhost:3000");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Giải thích:

- registerStompEndpoints() đăng ký /ws làm endpoint handshake cho WebSocket/STOMP client.
- setAllowedOrigins() cho phép trang web có origin http://localhost:3000 kết nối. Khi triển khai, thay bằng các origin thực tế được phê duyệt.
- setApplicationDestinationPrefixes("/app") định tuyến message gửi đến destination bắt đầu bằng /app cho các phương thức @MessageMapping.
- enableSimpleBroker("/topic", "/queue") bật simple broker trong bộ nhớ để lưu subscription và phát message.

Trong simple broker tích hợp, /topic và /queue chủ yếu là quy ước tên để phân biệt kiểu publish/subscribe và point-to-point. Chúng không phải cú pháp bắt buộc của STOMP. Khi dùng broker bên ngoài, hãy kiểm tra quy tắc destination của broker đó.

## 9. Luồng message trong Spring STOMP

Khi một client gửi STOMP frame vào WebSocket connection, Spring xử lý theo luồng tổng quát:

1. WebSocket transport nhận frame và chuyển payload cho STOMP subprotocol handler.
2. STOMP decoder chuyển frame thành Spring Message gồm header và payload.
3. Message được gửi đến clientInboundChannel.
4. Destination prefix quyết định message được chuyển đến @MessageMapping hay broker.
5. Nếu controller xử lý, kết quả được gửi đến brokerChannel.
6. Broker tìm các subscriber phù hợp.
7. Message được gửi đến clientOutboundChannel.
8. STOMP encoder tạo MESSAGE frame và WebSocket transport gửi frame về client.

Ba channel nội bộ thường gặp:

| Channel | Hướng | Nhiệm vụ |
|---|---|---|
| clientInboundChannel | Client → Spring | Chuyển message nhận từ WebSocket client vào xử lý |
| brokerChannel | Application → Broker | Chuyển message từ code server đến broker |
| clientOutboundChannel | Spring → Client | Chuyển message cần gửi đến WebSocket client |

Có thể cấu hình một broker đơn giản trong ứng dụng hoặc dùng broker relay để chuyển tiếp đến một STOMP broker bên ngoài như RabbitMQ có STOMP plugin hoặc broker hỗ trợ STOMP.

Simple broker phù hợp cho ứng dụng nhỏ hoặc demo; subscription được giữ trong bộ nhớ của từng application instance. Khi chạy nhiều replica, simple broker trên một node không tự chia sẻ subscription với node khác.

Broker relay mở các kết nối TCP từ Spring đến broker bên ngoài để quản lý subscription và broadcast. Client vẫn kết nối WebSocket đến ứng dụng Spring; broker relay là kết nối nội bộ giữa ứng dụng và message broker.

## 10. Ví dụ hoàn chỉnh: Spring Boot, Java 17 và STOMP

Ví dụ này tạo một chat endpoint. Browser kết nối WebSocket đến /ws, STOMP client đăng ký /topic/chat, gửi message đến /app/chat.send và nhận message được server phát lại qua broker.

Ví dụ dùng Java 17, Spring Boot 3.4.x và Spring Framework 6.2.x. Khi chọn phiên bản triển khai, dùng patch Spring Framework đã được cập nhật bảo mật; CVE-2025-41254 liên quan đến STOMP over WebSocket đã được khắc phục từ Spring Framework 6.2.12.

### 10.1. Cấu trúc dự án

~~~text
spring-websocket-stomp-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/websocket/
        │   ├── WebSocketDemoApplication.java
        │   ├── StompWebSocketConfig.java
        │   ├── ChatController.java
        │   └── ChatMessage.java
        └── resources/
            └── application.properties
~~~

### 10.2. Maven dependencies

Tạo pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.12</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-websocket-stomp-demo</artifactId>
    <version>1.0.0</version>

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

spring-boot-starter-web cung cấp web runtime; spring-boot-starter-websocket cung cấp các thành phần WebSocket và messaging. Spring Boot dependency management chọn các phiên bản tương thích.

### 10.3. Lớp khởi động

Tạo WebSocketDemoApplication.java:

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

### 10.4. Cấu hình endpoint và broker

Tạo StompWebSocketConfig.java:

~~~java
package com.example.websocket;

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
        registry.addEndpoint("/ws")
            .setAllowedOrigins("http://localhost:3000");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Địa chỉ origin ở đây giả định trang frontend chạy tại localhost:3000. Nếu trang frontend được phục vụ cùng origin với Spring, có thể giữ chính sách same-origin mặc định thay vì mở thêm origin.

### 10.5. Payload của chat

Tạo ChatMessage.java:

~~~java
package com.example.websocket;

public record ChatMessage(String from, String text) {
}
~~~

Record Java 17 biểu diễn payload chat gồm tên người gửi và nội dung. Spring dùng message converter để chuyển JSON body thành ChatMessage.

### 10.6. Controller xử lý STOMP SEND

Tạo ChatController.java:

~~~java
package com.example.websocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage handle(ChatMessage message) {
        return message;
    }
}
~~~

Khi nhận STOMP SEND đến /app/chat.send, Spring gọi handle(). Giá trị trả về được gửi đến /topic/chat. Broker phát message đến mọi client đã SUBSCRIBE destination đó.

### 10.7. Cấu hình ứng dụng

Tạo application.properties:

~~~properties
spring.application.name=spring-websocket-stomp-demo
server.port=8080
~~~

### 10.8. Chạy ứng dụng

Từ thư mục dự án:

~~~bash
mvn spring-boot:run
~~~

Ứng dụng lắng nghe HTTP tại cổng 8080 và đăng ký WebSocket/STOMP endpoint /ws.

### 10.9. Kết nối từ browser bằng STOMP.js

Trong frontend JavaScript, cài thư viện:

~~~bash
npm install @stomp/stompjs
~~~

Ví dụ client:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "ws://localhost:8080/ws",
    reconnectDelay: 5000,
    heartbeatIncoming: 10000,
    heartbeatOutgoing: 10000,

    onConnect: () => {
        console.log("STOMP connected");

        client.subscribe("/topic/chat", (frame) => {
            const message = JSON.parse(frame.body);
            console.log("received:", message);
        });

        client.publish({
            destination: "/app/chat.send",
            headers: {
                "content-type": "application/json"
            },
            body: JSON.stringify({
                from: "Linh",
                text: "Xin chào từ WebSocket"
            })
        });
    },

    onStompError: (frame) => {
        console.error("STOMP error:", frame.headers["message"]);
        console.error(frame.body);
    },

    onWebSocketError: (event) => {
        console.error("WebSocket transport error:", event);
    }
});

client.activate();
~~~

Client thực hiện các bước:

1. Mở WebSocket đến ws://localhost:8080/ws.
2. Thương lượng STOMP subprotocol trong handshake nếu client và server hỗ trợ.
3. Gửi STOMP CONNECT và đợi CONNECTED.
4. Trong onConnect, gửi SUBSCRIBE đến /topic/chat.
5. Gửi SEND đến /app/chat.send với JSON payload.
6. Nhận MESSAGE từ /topic/chat qua callback subscription.

Nếu có nhiều tab browser hoặc nhiều client kết nối, mỗi client đăng ký /topic/chat sẽ nhận message mà controller phát ra destination đó.

Khi triển khai qua HTTPS, dùng wss:// thay cho ws://. Không dùng địa chỉ ws:// từ trang HTTPS vì trình duyệt thường chặn mixed content.

## 11. HandshakeInterceptor và HandshakeHandler

### 11.1. HandshakeInterceptor

HandshakeInterceptor cho phép can thiệp trước và sau HTTP handshake.

Các trường hợp sử dụng:

- Kiểm tra thông tin request trước khi cho phép nâng cấp.
- Từ chối handshake bằng cách trả false từ beforeHandshake().
- Chuyển một số HTTP session attributes sang WebSocketSession attributes.
- Ghi nhận metadata phục vụ audit hoặc correlation.

Spring cung cấp HttpSessionHandshakeInterceptor để chuyển các thuộc tính HTTP session sang WebSocket session.

Ví dụ đăng ký interceptor cho raw WebSocket handler:

~~~java
registry.addHandler(new EchoHandler(), "/echo")
    .addInterceptors(new HttpSessionHandshakeInterceptor());
~~~

Các attributes được lưu trong WebSocketSession và có thể được đọc ở các bước xử lý message tiếp theo. Chỉ đưa dữ liệu cần thiết vào session attributes; không sao chép toàn bộ object nhạy cảm nếu không có nhu cầu.

Với STOMP, endpoint registry cũng hỗ trợ đăng ký handshake interceptor:

~~~java
registry.addEndpoint("/ws")
    .addInterceptors(new HttpSessionHandshakeInterceptor());
~~~

HandshakeInterceptor chạy ở ranh giới HTTP handshake. Nó không phải interceptor cho từng STOMP SEND hoặc SUBSCRIBE frame.

### 11.2. DefaultHandshakeHandler

DefaultHandshakeHandler thực hiện quá trình handshake. Nó có thể:

- Kiểm tra Origin.
- Thương lượng subprotocol.
- Chọn chiến lược nâng cấp phù hợp với WebSocket server engine.
- Tạo WebSocket session sau khi handshake thành công.

Chỉ cần custom HandshakeHandler khi cần thay đổi cách thương lượng hoặc tích hợp một RequestUpgradeStrategy riêng. Với cấu hình thông thường, Spring tự cung cấp handler phù hợp với Servlet container.

## 12. HandshakeInterceptor khác ChannelInterceptor

Hai interceptor này hoạt động ở hai tầng khác nhau:

| Tiêu chí | HandshakeInterceptor | ChannelInterceptor |
|---|---|---|
| Thời điểm | Trước/sau HTTP WebSocket handshake | Khi Spring Message đi qua MessageChannel |
| Đối tượng | HTTP request/response và attributes của WebSocket session | Spring Message, header và channel |
| Phạm vi | Một lần khi mở kết nối | Nhiều lần, theo từng message hoặc frame được xử lý |
| Có thể từ chối | Từ chối handshake trước khi có WebSocket session | Có thể trả null từ preSend để chặn message |
| Ví dụ | Kiểm tra request, chuyển HTTP session attributes | Xác thực STOMP CONNECT, kiểm tra destination, audit SEND/SUBSCRIBE |

Ví dụ ChannelInterceptor có thể lấy StompHeaderAccessor để kiểm tra command:

~~~java
public class AuditChannelInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        StompHeaderAccessor accessor =
            MessageHeaderAccessor.getAccessor(
                message,
                StompHeaderAccessor.class
            );

        if (accessor != null) {
            StompCommand command = accessor.getCommand();
            // Kiểm tra hoặc ghi audit theo command.
        }

        return message;
    }
}
~~~

Để đăng ký interceptor, dùng configureClientInboundChannel() trong WebSocketMessageBrokerConfigurer:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(new AuditChannelInterceptor());
}
~~~

Đây là nơi phù hợp để kiểm tra các STOMP frame sau khi Spring đã giải mã chúng thành Spring Message.

## 13. Xác thực và phân quyền

### 13.1. Xác thực ở HTTP handshake

Nhiều ứng dụng đã có Spring Security bảo vệ HTTP. Khi browser mở WebSocket, request handshake thường mang cookie/session hiện có. Nếu HTTP request đã được xác thực, Principal từ HttpServletRequest có thể được Spring liên kết với WebSocket/SockJS session và các STOMP message sau đó.

Với cách này:

- Người dùng đăng nhập qua HTTP.
- Browser gửi cookie/session khi mở WebSocket.
- Server xác thực handshake request.
- Spring gắn Principal vào WebSocket session.
- Các STOMP message tiếp theo mang thông tin user đã xác thực.

Đây thường là lựa chọn đơn giản nếu ứng dụng đã dùng cookie-based session.

### 13.2. Xác thực bằng token ở STOMP CONNECT

Browser WebSocket API không cung cấp cách tùy ý thêm custom HTTP headers vào handshake request. Nếu ứng dụng cần bearer token thay vì cookie, có thể gửi token trong STOMP CONNECT headers sau khi WebSocket connection đã mở.

Một ChannelInterceptor có thể:

1. Kiểm tra STOMP command có phải CONNECT không.
2. Đọc token từ native STOMP header.
3. Xác thực token qua hệ thống bảo mật.
4. Tạo Principal tương ứng.
5. Gọi accessor.setUser(principal) để gắn user với phiên STOMP.

Ví dụ minh họa phần lõi:

~~~java
if (StompCommand.CONNECT.equals(accessor.getCommand())) {
    String token = accessor.getFirstNativeHeader("Authorization");

    Authentication authentication =
        tokenAuthenticationService.authenticate(token);

    accessor.setUser(authentication);
}
~~~

tokenAuthenticationService là service xác thực của ứng dụng, không phải API có sẵn của Spring. Cần xử lý token thiếu, hết hạn, sai chữ ký và quyền không hợp lệ trước khi chấp nhận message.

Nếu dùng Spring Security message authorization, interceptor xác thực phải chạy trước interceptor phân quyền của Spring Security để user đã được gắn vào message khi authorization được thực hiện.

### 13.3. STOMP login/passcode

STOMP có header login và passcode trên CONNECT. Tuy nhiên, với STOMP over WebSocket, Spring mặc định dựa vào HTTP-level authentication và bỏ qua/ghi đè login/passcode ở STOMP level. Không nên giả định rằng chỉ gửi login/passcode sẽ tự động xác thực browser client.

### 13.4. CSRF và Origin

Spring Security WebSocket hỗ trợ kiểm tra CSRF token trên STOMP CONNECT khi bật WebSocket message security. Nếu cấu hình bảo mật yêu cầu CSRF, client cần gửi token theo cách Spring Security quy định.

Spring mặc định chỉ chấp nhận same-origin cho WebSocket và SockJS. Có thể cấu hình danh sách origin cụ thể khi frontend và backend chạy ở các origin khác nhau.

Origin là tín hiệu bảo vệ cho browser client, không phải bằng chứng xác thực. Client không phải browser có thể tự đặt Origin header. Luôn xác thực danh tính và phân quyền độc lập với Origin.

## 14. Bảo mật WebSocket/STOMP

Kết nối WebSocket thường sống lâu hơn một HTTP request, vì vậy cần thiết kế bảo mật theo cả vòng đời session và từng message.

Các nguyên tắc quan trọng:

- Dùng WSS trong môi trường production để mã hóa dữ liệu trên đường truyền.
- Xác thực khi handshake hoặc tại STOMP CONNECT theo kiến trúc đã chọn.
- Phân quyền riêng cho SEND, SUBSCRIBE và destination nhạy cảm.
- Không cho client tự khai báo userId/role rồi tin các giá trị đó.
- Kiểm tra payload, kích thước message, content type và schema.
- Giới hạn số connection, tốc độ message và số subscription trên mỗi user.
- Cấu hình allowed origins cụ thể, không mở wildcard tùy tiện khi dùng cookie/session.
- Không ghi access token, cookie hoặc payload nhạy cảm vào log.
- Xử lý session hết hạn, logout và thu hồi quyền khi WebSocket còn mở.
- Cấu hình idle timeout, heartbeat và giới hạn buffer phù hợp.

Một client có thể đã được xác thực ở handshake nhưng vẫn gửi message đến destination mà user đó không có quyền. Xác thực session không thay thế authorization ở từng message.

### 14.1. Lưu ý phiên bản Spring

CVE-2025-41254 liên quan đến STOMP over WebSocket trong Spring Framework. Các phiên bản 6.2.0 đến 6.2.11 bị ảnh hưởng; bản sửa cho nhánh 6.2 bắt đầu từ 6.2.12. Khi dùng Spring Framework 6.2, hãy dùng phiên bản đã được vá và theo dõi security advisories của Spring.

## 15. SockJS và fallback transport

Một số môi trường proxy hoặc mạng doanh nghiệp không hỗ trợ WebSocket đầy đủ. Spring có thể cung cấp SockJS fallback.

SockJS cố gắng dùng WebSocket khi có thể. Nếu không, nó có thể dùng các HTTP transport thay thế như streaming hoặc long polling.

Cấu hình endpoint:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
        .setAllowedOrigins("http://localhost:3000")
        .withSockJS();
}
~~~

Client khi dùng SockJS sẽ tạo SockJS transport thay cho browser WebSocket trực tiếp, sau đó dùng STOMP client trên transport đó.

SockJS thay đổi cách truyền tải khi WebSocket không khả dụng. Nó không thay thế STOMP command, destination hoặc quy tắc message của ứng dụng.

Nếu ứng dụng chỉ chạy trong môi trường đã hỗ trợ WebSocket ổn định, không cần bật SockJS chỉ vì nó tồn tại. Hãy chọn dựa trên yêu cầu tương thích client và mạng.

## 16. Broker đơn giản và broker relay

### 16.1. Simple broker tích hợp

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

Simple broker lưu subscription trong bộ nhớ ứng dụng và phát message đến các client đang subscribe. Nó thuận tiện cho demo, ứng dụng nhỏ hoặc trường hợp không cần broker riêng.

Giới hạn thường gặp:

- Subscription tồn tại trong bộ nhớ của một application instance.
- Không có toàn bộ tính năng của một message broker chuyên dụng.
- Không tự chia sẻ subscription giữa nhiều replica Spring.
- Không thay thế queue persistence, durable subscription hoặc broker-level routing nâng cao.

### 16.2. Broker relay

Khi cần broker đầy đủ, Spring có thể relay STOMP frame đến broker bên ngoài:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
        .setRelayHost("localhost")
        .setRelayPort(61613)
        .setClientLogin("client")
        .setClientPasscode("client-secret");
}
~~~

Ví dụ này giả định broker có STOMP listener tại localhost:61613 và thông tin đăng nhập đã được cấu hình riêng. Không dùng credential minh họa trong production.

Trong kiến trúc broker relay:

- Browser vẫn kết nối WebSocket đến Spring.
- Spring nhận STOMP frame từ client.
- Spring chuyển các destination thuộc broker prefix đến external STOMP broker qua TCP.
- Broker quản lý subscription và phát message.
- Spring nhận message từ broker và gửi lại browser qua WebSocket.

Khi chạy nhiều replica Spring, external broker giúp các node chia sẻ message routing và subscription theo cấu hình broker. Cần cấu hình relay credentials, TLS, heartbeat, virtual host và quyền destination theo broker thực tế.

## 17. Thứ tự message và xử lý đồng thời

WebSocket giữ thứ tự frame trên một kết nối ở tầng transport. Tuy nhiên, sau khi Spring giải mã frame thành message và đưa vào các channel chạy bằng executor, việc xử lý nghiệp vụ có thể diễn ra trên nhiều thread.

Nếu thứ tự xử lý inbound message trong cùng một session là yêu cầu bắt buộc, Spring có tùy chọn preserve receive order. Nếu thứ tự publish đến WebSocket client là yêu cầu bắt buộc, có thể bật preserve publish order trong MessageBrokerRegistry.

Ví dụ:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic");
    registry.setPreservePublishOrder(true);
}
~~~

Tùy chọn này có thể giảm mức song song và throughput. Chỉ bật khi nghiệp vụ cần giữ thứ tự; nếu không, thiết kế handler idempotent và xử lý message độc lập thường mở rộng tốt hơn.

## 18. Giới hạn transport và hiệu năng

WebSocket connection sống lâu và có thể giữ nhiều tài nguyên phía server. Cần cấu hình giới hạn hợp lý:

- Max text message size.
- Max binary message size.
- Send buffer size.
- Send time limit.
- Idle timeout.
- Số session đồng thời.
- Số message/giây trên mỗi client.
- Heartbeat interval.

Với STOMP, Spring cho phép cấu hình WebSocket transport:

~~~java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registry) {
    registry.setMessageSizeLimit(64 * 1024);
    registry.setSendBufferSizeLimit(512 * 1024);
    registry.setSendTimeLimit(15_000);
}
~~~

Các con số trên chỉ là ví dụ ban đầu. Hãy chọn theo kích thước payload, số client, latency và bộ nhớ thực tế. Không tăng giới hạn vô hạn để tránh lỗi message lớn; hãy cân nhắc pagination, streaming hoặc chia nhỏ payload nếu dữ liệu quá lớn.

Nếu một client xử lý chậm, send buffer có thể tăng và gây áp lực bộ nhớ. Cần chính sách giới hạn buffer, timeout và đóng session chậm theo nhu cầu hệ thống.

## 19. Chẩn đoán lỗi theo từng tầng

| Triệu chứng | Tầng cần kiểm tra | Hướng xử lý |
|---|---|---|
| HTTP 404 khi kết nối | Endpoint/HTTP mapping | Kiểm tra registerStompEndpoints hoặc registerWebSocketHandlers |
| HTTP 403 | Authentication, authorization hoặc Origin | Kiểm tra Spring Security, CSRF và allowed origins |
| Không nhận HTTP 101 | Handshake/Proxy | Kiểm tra Upgrade, Connection, TLS và proxy support |
| 101 thành công nhưng không nhận CONNECTED | STOMP protocol | Kiểm tra subprotocol, CONNECT frame, version và broker |
| CONNECTED nhưng SUBSCRIBE không có dữ liệu | STOMP destination/broker | Kiểm tra destination prefix, broker subscription và quyền subscribe |
| SEND không gọi @MessageMapping | Spring routing | Kiểm tra application prefix và đường dẫn @MessageMapping |
| Controller chạy nhưng client không nhận | Outbound routing/broker | Kiểm tra @SendTo, broker destination và client subscription |
| JSON deserialize lỗi | Message converter | Kiểm tra content-type, JSON schema và payload |
| Kết nối tự ngắt sau thời gian idle | Proxy/heartbeat/timeout | Căn chỉnh heartbeat và idle timeout |
| Client không tự kết nối lại | Client lifecycle | Cấu hình reconnect và xử lý trạng thái session mới |
| Nhiều client nhận dữ liệu trùng | Broker/subscription | Kiểm tra subscription id, shared subscription và destination |

Cách chẩn đoán hiệu quả là xác định message cuối cùng đã qua được tầng nào. Ví dụ, nếu không có HTTP 101 thì chưa cần kiểm tra @MessageMapping; nếu đã nhận CONNECTED thì handshake và STOMP CONNECT đã hoàn tất, hãy kiểm tra tiếp SUBSCRIBE/SEND và broker routing.

## 20. Kiểm thử một phiên STOMP end-to-end

Một smoke test thực tế nên xác minh lần lượt:

1. Browser có thể mở /ws và nhận HTTP 101.
2. Client thương lượng được STOMP subprotocol.
3. Client gửi CONNECT và nhận CONNECTED.
4. Client SUBSCRIBE /topic/chat.
5. Client SEND /app/chat.send với content-type application/json.
6. Spring gọi ChatController.handle().
7. Broker phát MESSAGE đến /topic/chat.
8. Client nhận đúng payload.
9. Client gửi DISCONNECT hoặc đóng WebSocket.
10. Server giải phóng session và subscription theo lifecycle.

Đừng chỉ kiểm tra WebSocket handshake thành công rồi kết luận STOMP hoạt động. Cũng đừng chỉ gọi controller bằng unit test mà cho rằng message routing và broker subscription đã được kiểm thử.

## 21. Lỗi thường gặp

- **Cho rằng WebSocket tự hiểu JSON hoặc STOMP**: WebSocket chỉ vận chuyển text/binary frame; ứng dụng cần giao thức định nghĩa nội dung.
- **Nhầm HTTP 101 với STOMP CONNECTED**: 101 mở WebSocket, CONNECTED xác nhận phiên STOMP.
- **Nhầm /ws với /app/chat.send**: /ws là endpoint handshake; /app/chat.send là STOMP destination.
- **Đưa logic destination vào HTTP URL sau khi kết nối**: message routing được xác định bởi protocol frame và header destination.
- **Dùng raw WebSocket nhưng kỳ vọng @MessageMapping hoạt động**: @MessageMapping thuộc STOMP messaging stack.
- **Dùng STOMP nhưng không cấu hình broker prefix**: SUBSCRIBE hoặc SEND không được định tuyến như mong đợi.
- **Cho rằng /topic và /queue là từ khóa bắt buộc của mọi broker**: đây là quy ước; broker bên ngoài có thể có destination semantics riêng.
- **Coi Origin là authentication**: Origin chủ yếu hỗ trợ bảo vệ browser; client khác có thể giả mạo header này.
- **Tin userId/role do client gửi**: danh tính và quyền phải được server xác thực.
- **Dùng STOMP login/passcode mà không hiểu Spring authentication**: Spring mặc định bỏ qua các header đó cho STOMP over WebSocket khi dùng HTTP-level authentication.
- **Không phân biệt HandshakeInterceptor với ChannelInterceptor**: một cái can thiệp HTTP handshake, cái kia xử lý Spring Message.
- **Mở allowed origins thành wildcard tùy tiện**: có thể làm tăng rủi ro cross-site WebSocket.
- **Không cấu hình WSS ở production**: dữ liệu có thể bị nghe lén trên mạng.
- **Bật simple broker cho nhiều replica rồi mong subscription được chia sẻ**: simple broker chỉ giữ state trong bộ nhớ từng instance.
- **Không xử lý reconnect**: WebSocket connection có thể mất do mạng, proxy hoặc restart server.
- **Không giới hạn message size và send buffer**: client gửi payload lớn hoặc đọc chậm có thể gây áp lực bộ nhớ.
- **Không kiểm thử message order**: executor có thể xử lý message song song và làm thay đổi thứ tự hoàn tất.

## 22. Checklist triển khai

- [ ] Xác định endpoint handshake, ví dụ /ws.
- [ ] Xác định client dùng raw WebSocket hay STOMP.
- [ ] Nếu dùng STOMP, thống nhất phiên bản và Sec-WebSocket-Protocol.
- [ ] Đăng ký endpoint qua WebSocketConfigurer hoặc StompEndpointRegistry.
- [ ] Cấu hình destination prefix cho application và broker.
- [ ] Chọn simple broker hay external broker relay.
- [ ] Xác định cơ chế authentication ở HTTP handshake hoặc STOMP CONNECT.
- [ ] Phân quyền SEND, SUBSCRIBE và destination theo người dùng.
- [ ] Kiểm tra Origin và CSRF theo chính sách bảo mật.
- [ ] Dùng WSS khi truyền dữ liệu qua mạng không tin cậy.
- [ ] Cấu hình heartbeat, idle timeout và reconnect.
- [ ] Giới hạn message size, send buffer và số connection.
- [ ] Kiểm thử proxy/load balancer có hỗ trợ WebSocket.
- [ ] Kiểm thử end-to-end từ HTTP 101 đến STOMP MESSAGE.
- [ ] Nếu chạy nhiều replica, đánh giá broker relay và cách chia sẻ subscription.
- [ ] Dùng phiên bản Spring Framework đã cập nhật security fixes.

## 23. Tổng kết

HTTP handshake khởi tạo và chuyển giao kết nối. WebSocket duy trì một kênh full-duplex để truyền text/binary frame. Giao thức ứng dụng như STOMP định nghĩa command, header, destination và ý nghĩa message. Ba lớp phối hợp với nhau nhưng có vòng đời và trách nhiệm riêng.

Trong Spring, raw WebSocket API phù hợp khi ứng dụng muốn tự thiết kế message protocol. STOMP over WebSocket phù hợp khi cần publish/subscribe, destination routing, broker và tích hợp Spring Messaging. @EnableWebSocketMessageBroker, StompEndpointRegistry, MessageBrokerRegistry, @MessageMapping và broker channel tạo thành nền tảng cho mô hình STOMP.

Khi thiết kế, hãy phân biệt URL handshake với destination của message, phân biệt handshake interceptor với channel interceptor, xác thực người dùng ở đúng tầng và kiểm thử toàn bộ luồng từ HTTP 101 đến STOMP MESSAGE. Cấu hình đúng các ranh giới này giúp hệ thống dễ mở rộng, dễ bảo trì và an toàn hơn.

## Tài liệu tham khảo

- Spring Framework 6.2 — WebSocket overview: https://docs.spring.io/spring-framework/reference/6.2/web/websocket.html
- Spring Framework 6.2 — WebSocket API and handshake: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/server.html
- Spring Framework 6.2 — STOMP overview: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp.html
- Spring Framework 6.2 — Enable STOMP: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/enable.html
- Spring Framework 6.2 — Flow of Messages: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/message-flow.html
- Spring Framework 6.2 — Authentication: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/authentication.html
- Spring Framework 6.2 — Token Authentication: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/authentication-token-based.html
- Spring Security — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- Spring Security — CVE-2025-41254: https://spring.io/security/cve-2025-41254/
- RFC 6455 — The WebSocket Protocol: https://www.rfc-editor.org/rfc/rfc6455
- STOMP 1.2 Specification: https://stomp.github.io/stomp-specification-1.2.html
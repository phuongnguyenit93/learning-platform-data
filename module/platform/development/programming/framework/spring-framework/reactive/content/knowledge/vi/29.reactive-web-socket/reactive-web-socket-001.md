# Khác biệt giữa WebSocket, SSE và HTTP thông thường

## 1. Ba mô hình giao tiếp

Một ứng dụng web có thể cần tải dữ liệu, nhận thông báo khi có thay đổi hoặc trao đổi liên tục với server. HTTP thông thường, Server-Sent Events (SSE) và WebSocket đều dùng hạ tầng web nhưng có mô hình khác nhau:

- **HTTP request/response:** client gửi request; server trả response. Mỗi thao tác nghiệp vụ thường là một lần gọi độc lập.
- **SSE:** client mở một HTTP request và giữ response stream để server gửi các event liên tiếp. Dữ liệu ứng dụng trên stream đi một chiều từ server tới client.
- **WebSocket:** client và server thiết lập một kết nối lâu dài; sau đó cả hai phía có thể gửi message bất cứ lúc nào.

Ví dụ một trang dashboard:

- Khi mở trang, browser dùng HTTP GET để tải thông tin tổng quan.
- Khi trạng thái đơn hàng thay đổi, server gửi event SSE để cập nhật giao diện.
- Trong màn hình chat, người dùng gửi message và nhận message mới gần như đồng thời; WebSocket phù hợp hơn.

Không có giao thức nào luôn tốt nhất. Chọn dựa trên hướng dữ liệu, tần suất cập nhật, độ trễ, nhu cầu gửi message từ client, khả năng reconnect/replay, hạ tầng proxy và chi phí giữ kết nối.

## 2. HTTP thông thường: request/response

### 2.1. Mô hình hoạt động

HTTP mô hình hóa giao tiếp thành các request tới URL. Request có method, path, headers và có thể có body. Server xử lý rồi trả status, headers và response body.

~~~text
Client                         Server
  |                               |
  |------- GET /api/orders ------>|
  |                               |
  |<------ 200 + JSON ------------|
  |                               |
  |------- POST /api/orders ----->|
  |                               |
  |<------ 201 + JSON ------------|
~~~

Ví dụ:

~~~http
GET /api/orders/42 HTTP/1.1
Host: shop.example
Accept: application/json
~~~

Response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"PAID"}
~~~

Client thường bắt đầu request khi cần dữ liệu. Server trả lời cho request đó; nếu sau đó trạng thái đơn hàng thay đổi, client không tự biết cho đến khi gửi request khác hoặc dùng một cơ chế cập nhật khác.

### 2.2. Keep-alive không phải WebSocket

HTTP/1.1 thường tái sử dụng một TCP connection cho nhiều request/response bằng persistent connection. HTTP/2 còn cho phép multiplex nhiều stream trên một connection.

Điều đó không biến HTTP thành kênh message hai chiều liên tục ở tầng ứng dụng. Mỗi thao tác vẫn tuân theo semantics request/response của HTTP. Client có thể mở request mới khi cần, còn server không tự gửi message nghiệp vụ tùy ý sau khi response đã hoàn tất.

HTTP cũng hỗ trợ streaming body. Ví dụ download file lớn hoặc response được ghi dần có thể giữ một response mở trong thời gian dài. Đây vẫn là một response stream theo hướng server tới client; nó không cung cấp giao thức message hai chiều như WebSocket.

### 2.3. Polling và long polling

Nếu chỉ dùng HTTP mà muốn biết dữ liệu có thay đổi không, client có thể polling:

~~~text
Client             Server
  |--- GET --------->|
  |<-- 200 data -----|
  |                  |
  |--- GET --------->|  (sau một khoảng thời gian)
  |<-- 200 data -----|
~~~

Polling dễ triển khai, dễ quan sát và tương thích với hầu hết proxy/cache. Tuy nhiên, chu kỳ ngắn tạo nhiều request không cần thiết; chu kỳ dài làm cập nhật chậm.

Long polling giữ request mở cho đến khi có dữ liệu hoặc timeout. Sau khi server trả response, client gửi request tiếp theo. Nó giảm số lần hỏi liên tục nhưng vẫn là nhiều request/response nối tiếp, không phải một kết nối message hai chiều.

### 2.4. Điểm mạnh và giới hạn

**Điểm mạnh:**

- Phù hợp CRUD, REST API, truy vấn và command.
- Có semantics HTTP rõ ràng: method, status, header, cache, conditional request.
- Dễ tích hợp với gateway, proxy, CDN, logging và tracing.
- Dễ retry theo method/idempotency và xử lý lỗi theo status.
- Không cần giữ một kết nối riêng cho mỗi người dùng chỉ để nhận cập nhật.

**Giới hạn:**

- Client phải gửi request để lấy dữ liệu mới.
- Polling tạo request lặp lại và có thể gây độ trễ giữa hai lần hỏi.
- Response thông thường không cho server chủ động gửi message mới sau khi response đã kết thúc.
- Long polling và streaming cần timeout, cleanup và xử lý connection bị ngắt.

## 3. SSE: server gửi event qua HTTP

### 3.1. SSE là gì?

Server-Sent Events là cơ chế streaming một chiều trên HTTP. Browser tạo EventSource tới một URL; server trả response có Content-Type là text/event-stream và giữ response mở để gửi các event.

~~~text
Browser                         Server
  |                               |
  |------- GET /api/events ------>|
  |<------ 200 text/event-stream -|
  |                               |
  |<------ event: status ---------|
  |<------ event: status ---------|
  |<------ event: notification ---|
~~~

Client vẫn có thể gửi request HTTP khác tới server, nhưng chính kết nối SSE chỉ truyền event theo chiều server tới client. SSE phù hợp với notification, feed, tiến độ xử lý, trạng thái job và dashboard live.

### 3.2. Định dạng event stream

SSE là văn bản UTF-8. Mỗi event gồm một hoặc nhiều dòng field và kết thúc bằng một dòng trống. Các field phổ biến:

| Field | Ý nghĩa |
| --- | --- |
| data | Nội dung event; nhiều dòng data được ghép bằng newline |
| event | Tên loại event để client đăng ký listener tương ứng |
| id | ID của event, được lưu làm last event ID |
| retry | Khoảng chờ reconnect tính bằng millisecond |
| comment | Dòng bắt đầu bằng dấu hai chấm; không tạo event cho ứng dụng |

Ví dụ:

~~~text
id: 1042
event: order-status
retry: 3000
data: {"orderId":42,"status":"SHIPPED"}

~~~

Dòng trống sau data kết thúc event. Nếu có nhiều dòng data, browser ghép chúng bằng ký tự newline trước khi gọi listener.

Comment có thể dùng làm heartbeat để giữ connection không bị proxy đóng vì idle timeout:

~~~text
: heartbeat

~~~

Comment bị bỏ qua bởi event handler nhưng vẫn tạo traffic trên đường truyền.

### 3.3. EventSource trong browser

Browser có API EventSource:

~~~javascript
const source = new EventSource("/api/events");

source.addEventListener("order-status", (event) => {
    const update = JSON.parse(event.data);
    console.log("Order update:", update);
});

source.onopen = () => console.log("SSE connected");
source.onerror = (error) => console.warn("SSE interrupted", error);

// Khi rời màn hình, gọi source.close() hoặc EventSource.close().
source.close();
~~~

Event không có field event được phát dưới dạng message event và có thể xử lý bằng onmessage. Event có tên như order-status phải được đăng ký bằng addEventListener("order-status", ...).

EventSource tự thử kết nối lại khi connection bị ngắt ngoài ý muốn. Client có thể gọi EventSource.close() để dừng hoàn toàn và không reconnect nữa.

### 3.4. Reconnect, retry và Last-Event-ID

Nếu server gửi field retry, browser dùng thời gian đó làm khoảng chờ reconnect. Nếu event có id, browser lưu ID cuối cùng đã nhận. Khi reconnect, EventSource gửi header Last-Event-ID để server biết client đã đọc tới đâu.

ID không tự làm server phát lại dữ liệu đã mất. Ứng dụng phải có event log, sequence hoặc storage đủ bền để:

1. Đọc Last-Event-ID từ request reconnect.
2. Tìm event tiếp theo sau ID đó.
3. Phát lại các event còn thiếu theo đúng thứ tự.
4. Xử lý trường hợp ID đã hết hạn hoặc không còn trong event log.

Nếu không có replay, reconnect chỉ tạo lại stream từ thời điểm mới và client có thể bỏ lỡ sự kiện trong khoảng mất kết nối. Nếu server phát lại, client cũng có thể nhận event trùng. Hãy dùng event ID ổn định và xử lý idempotent ở phía client.

### 3.5. SSE có những giới hạn nào?

- Chỉ truyền event server-to-client trên một EventSource connection.
- Nội dung event là text UTF-8; không có binary message native như WebSocket.
- EventSource native dùng GET và không cung cấp API tổng quát để tự đặt Authorization header. Có thể dùng cookie cùng-origin hoặc credentials mode; nếu cần method/header tùy chỉnh, cân nhắc fetch streaming và tự parse SSE.
- Browser tự reconnect nhưng logic replay vẫn do ứng dụng xây dựng.
- Một stream lâu dài cần heartbeat và cấu hình proxy/load balancer phù hợp.
- Với HTTP/1.1, browser có giới hạn số connection đồng thời trên mỗi origin; nhiều tab mở nhiều EventSource có thể chạm giới hạn. HTTP/2 dùng số stream được thương lượng giữa client và server, nên giới hạn thực tế khác nhau.

SSE phù hợp khi client chủ yếu nghe sự kiện và không cần gửi message ứng dụng ngược lại qua chính stream đó.

## 4. WebSocket: kênh message hai chiều

### 4.1. WebSocket là gì?

WebSocket cung cấp kênh full-duplex: client và server đều có thể gửi message bất cứ lúc nào trên cùng một kết nối. Sau khi handshake hoàn tất, dữ liệu được truyền bằng WebSocket frame thay vì các HTTP request/response riêng.

~~~text
Browser                         Server
  |                               |
  |---- HTTP Upgrade request ---->|
  |<--- 101 Switching Protocols --|
  |                               |
  |<========== WebSocket ========>|
  |---- chat message ------------>|
  |<--- chat reply ---------------|
  |<--- new notification ---------|
  |---- typing state ------------>|
  |<--- another user's message ---|
  |                               |
  |---------- close ------------->|
~~~

WebSocket phù hợp với chat, cộng tác nhiều người, game, bảng điều khiển tương tác và ứng dụng cần trao đổi hai chiều liên tục.

### 4.2. Handshake

Với WebSocket truyền thống qua HTTP/1.1, client bắt đầu bằng HTTP GET có Upgrade và Connection headers:

~~~http
GET /ws/chat HTTP/1.1
Host: app.example
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: https://app.example
~~~

Nếu handshake hợp lệ, server trả:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: ...
~~~

Sau đó connection tiếp tục mở và hai bên trao đổi WebSocket frame. WebSocket không phải chỉ là một HTTP response giữ mở: sau khi chuyển giao thức, semantics HTTP request/response không còn áp dụng cho các message ứng dụng trên connection đó.

HTTP/2 có cơ chế Extended CONNECT để thiết lập WebSocket; không phải mọi trường hợp đều dùng status 101 của HTTP/1.1. Khi triển khai qua proxy hoặc gateway, phải xác nhận hạ tầng hỗ trợ cơ chế WebSocket đang được sử dụng.

### 4.3. Message và frame

WebSocket phân biệt frame ở tầng giao thức và message ở tầng ứng dụng. Các loại dữ liệu thường gặp:

- Text message: văn bản UTF-8, thường mang JSON.
- Binary message: dữ liệu nhị phân như ảnh, audio chunk hoặc payload mã hóa.
- Ping/Pong control frame: kiểm tra peer còn phản hồi và hỗ trợ keepalive.
- Close control frame: bắt đầu handshake đóng kết nối có mã trạng thái và lý do tùy chọn.

Một message có thể được chia thành nhiều frame. Ứng dụng không cần tự xử lý fragmentation nếu dùng WebSocket API/framework ở mức message.

WebSocket chỉ cung cấp transport message. Nó không quy định ý nghĩa nghiệp vụ của payload. Client và server phải thống nhất schema, message type, version, correlation ID, acknowledgement và lỗi. Có thể dùng JSON envelope riêng hoặc đàm phán subprotocol như STOMP qua Sec-WebSocket-Protocol.

### 4.4. Reconnect và độ tin cậy

Browser WebSocket API không tự reconnect như EventSource. Ứng dụng phải quyết định:

- Khi nào thử kết nối lại.
- Dùng exponential backoff và jitter ra sao.
- Có giới hạn số lần retry không.
- Khi reconnect có cần xác thực lại không.
- Message gửi trước khi mất kết nối có được xác nhận chưa.
- Làm thế nào để phát lại event hoặc command bị mất.

WebSocket không tự đảm bảo message được lưu bền vững hoặc được xử lý đúng một lần. Nếu nghiệp vụ cần đảm bảo giao nhận, hãy thiết kế message ID, sequence number, acknowledgement, deduplication và replay ở tầng ứng dụng.

### 4.5. WebSocket có những giới hạn nào?

- Mỗi client thường giữ một connection lâu dài; server phải quản lý connection count, memory, heartbeat, timeout và cleanup.
- Proxy/load balancer phải chuyển tiếp handshake và giữ connection mở đủ lâu.
- Browser WebSocket API không cho phép tùy ý đặt HTTP Authorization header trong constructor; dùng cookie an toàn, handshake auth hoặc một cơ chế cấp token phù hợp.
- Nếu dùng cookie authentication, phải xác thực Origin và authorization để tránh Cross-Site WebSocket Hijacking.
- Không có semantics HTTP cache cho các message sau handshake.
- Ứng dụng phải định nghĩa protocol, giới hạn payload, rate limit, thứ tự xử lý và cách phục hồi sau disconnect.

## 5. So sánh trực tiếp HTTP, SSE và WebSocket

| Tiêu chí | HTTP thông thường | SSE | WebSocket |
| --- | --- | --- | --- |
| Mô hình | Request/response | HTTP response stream | Message channel |
| Hướng dữ liệu trên một kết nối | Request client lên server, response server về client | Server → client | Hai chiều |
| Connection | Thường kết thúc logic sau response; transport có thể keep-alive/reuse | Giữ HTTP response mở | Giữ WebSocket session mở |
| Dữ liệu | Body theo media type HTTP | Text UTF-8, text/event-stream | Text hoặc binary |
| Server chủ động gửi event | Cần request/stream đang mở hoặc request mới | Có | Có |
| Client gửi message liên tục | Gửi request HTTP mới | Dùng request HTTP riêng | Có thể gửi trên cùng channel |
| Reconnect | Client tự gọi lại theo chính sách | EventSource tự reconnect | Ứng dụng tự triển khai |
| Event replay | Ứng dụng tự xây dựng | Last-Event-ID hỗ trợ resume; server phải replay | Ứng dụng tự xây dựng |
| Cache/proxy | Hỗ trợ semantics HTTP phổ biến | Cần cấu hình stream và buffering phù hợp | Cần proxy hỗ trợ Upgrade/CONNECT |
| Binary | Có thể qua body | Không native, event là text | Có |
| Phù hợp | CRUD, command, query, download/upload | Notification, feed, progress, live status | Chat, collaboration, game, bidirectional control |

### 5.1. Cây quyết định

~~~text
Client có cần gửi message thường xuyên
trên cùng kết nối với server không?
             |
        +----+----+
        |         |
       Không      Có
        |         |
        v         v
Server có cần    WebSocket
đẩy event ngay
khi có thay đổi?
        |
    +---+---+
    |       |
   Không    Có
    |       |
    v       v
HTTP      SSE
request/
response
~~~

Nếu chỉ cần một lần đọc hoặc ghi, bắt đầu bằng HTTP. Nếu server cần đẩy event một chiều, SSE thường đơn giản hơn. Nếu cả hai bên đều cần trao đổi message liên tục, WebSocket phù hợp hơn.

### 5.2. Các trường hợp cụ thể

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Tạo đơn hàng, cập nhật hồ sơ | HTTP | Command và response có status rõ ràng |
| Tải báo cáo hoặc ảnh | HTTP | Body download/upload theo semantics HTTP |
| Hiển thị tiến độ import | SSE | Server gửi tiến độ, browser chủ yếu nhận |
| Feed giá hoặc trạng thái job | SSE | Luồng cập nhật một chiều |
| Chat hai người | WebSocket | Client và server gửi message liên tục |
| Trình soạn thảo cộng tác | WebSocket | Nhiều client gửi thao tác và nhận thay đổi |
| Game nhiều người | WebSocket | Trao đổi hai chiều với tần suất cao |
| Dashboard refresh mỗi 30 giây | HTTP polling có thể đủ | Đơn giản, không cần connection lâu dài |
| Cập nhật một lần sau thao tác | HTTP response hoặc SSE tùy độ trễ | Không cần WebSocket nếu không có trao đổi liên tục |

## 6. Spring WebFlux hỗ trợ cả ba cách

Spring WebFlux cung cấp các abstraction reactive:

- HTTP controller trả Mono hoặc Flux; codec đọc request và ghi response.
- SSE có thể trả Flux<ServerSentEvent<T>> với media type text/event-stream.
- WebSocket dùng WebSocketHandler và WebSocketSession; receive() là Flux message đầu vào, send(Publisher) ghi message đầu ra và trả Mono<Void>.

Các pipeline Mono/Flux giúp xử lý I/O không blocking, backpressure, cancellation và lỗi. Với WebSocket, handler phải compose inbound và outbound stream thành một Mono<Void> phản ánh vòng đời session.

Không cần tạo thread riêng cho mỗi connection chỉ để chờ I/O. Tuy nhiên, code xử lý CPU nặng hoặc thư viện blocking vẫn phải được cô lập đúng scheduler và giới hạn concurrency.

## 7. Ví dụ Java 17+ chạy được: HTTP, SSE và WebSocket trong một ứng dụng

Ví dụ dùng Spring Boot 3.5.16, Java 17+ và WebFlux. Ứng dụng cung cấp:

- GET /api/status: HTTP request/response trả JSON.
- GET /api/events: SSE stream gửi event status mỗi giây.
- /ws/echo: WebSocket echo server nhận text message và trả lại message có tiền tố echo.

### 7.1. Cấu trúc dự án

~~~text
webflux-realtime-demo/
├── pom.xml
└── src/
    ├── main/java/example/realtime/
    │   ├── DemoApplication.java
    │   ├── RealtimeController.java
    │   ├── StatusResponse.java
    │   ├── StatusEvent.java
    │   ├── EchoWebSocketHandler.java
    │   └── WebSocketConfig.java
    └── test/java/example/realtime/
        └── RealtimeIntegrationTest.java
~~~

### 7.2. pom.xml

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
    <artifactId>webflux-realtime-demo</artifactId>
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

### 7.3. DemoApplication.java

~~~java
package example.realtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.4. StatusResponse.java

~~~java
package example.realtime;

import java.time.Instant;

public record StatusResponse(String status, Instant checkedAt) {
}
~~~

### 7.5. StatusEvent.java

~~~java
package example.realtime;

import java.time.Instant;

public record StatusEvent(long sequence, Instant occurredAt) {
}
~~~

### 7.6. RealtimeController.java

~~~java
package example.realtime;

import java.time.Duration;
import java.time.Instant;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class RealtimeController {

    @GetMapping("/status")
    public Mono<StatusResponse> status() {
        return Mono.just(new StatusResponse("UP", Instant.now()));
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<StatusEvent>> events() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(sequence -> ServerSentEvent
                        .<StatusEvent>builder(
                                new StatusEvent(sequence, Instant.now()))
                        .id(Long.toString(sequence))
                        .event("status")
                        .retry(Duration.ofSeconds(3))
                        .build());
    }
}
~~~

Mỗi event có ID, tên event, khoảng retry và JSON data. Spring dùng ServerSentEventHttpMessageWriter để ghi các event thành text/event-stream. Flux.interval phát một event mỗi giây; khi client disconnect và subscription bị cancel, pipeline có thể dừng theo lifecycle reactive.

Ví dụ này tạo sequence trong bộ nhớ cho mục đích minh họa. Nó không lưu event bền vững và không replay event cũ khi browser reconnect. Production cần event store hoặc cơ chế sequence/replay nếu không được phép mất event.

### 7.7. EchoWebSocketHandler.java

~~~java
package example.realtime;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Mono;

@Component
public class EchoWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.send(
                session.receive()
                        .filter(message ->
                                message.getType() == WebSocketMessage.Type.TEXT)
                        .map(message -> session.textMessage(
                                "echo: " + message.getPayloadAsText()))
        );
    }
}
~~~

Handler đọc inbound stream bằng session.receive(), chuyển text message thành phản hồi và gửi bằng session.send(). Khi inbound stream hoàn tất do connection đóng, outbound stream cũng kết thúc.

Đây là echo server chỉ xử lý text. Nếu ứng dụng nhận binary message, cần định nghĩa cách decode và giới hạn payload phù hợp. Với tác vụ bất đồng bộ lồng nhau, compose Publisher bằng concatMap/flatMap và quản lý DataBuffer lifecycle nếu giữ dữ liệu qua callback.

### 7.8. WebSocketConfig.java

~~~java
package example.realtime;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;

@Configuration(proxyBeanMethods = false)
public class WebSocketConfig {

    @Bean
    HandlerMapping webSocketMapping(EchoWebSocketHandler handler) {
        SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
        mapping.setUrlMap(Map.of("/ws/echo", handler));
        mapping.setOrder(-1);
        return mapping;
    }
}
~~~

SimpleUrlHandlerMapping ánh xạ URL /ws/echo tới WebSocketHandler. Trong ứng dụng Spring Boot WebFlux, cấu hình WebFlux tự cung cấp WebSocketHandlerAdapter. Không thêm @EnableWebFlux chỉ để đăng ký handler vì điều đó có thể làm thay đổi cơ chế auto-configuration của Boot.

### 7.9. RealtimeIntegrationTest.java

~~~java
package example.realtime;

import java.net.URI;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class RealtimeIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @LocalServerPort
    int port;

    @Test
    void returnsOrdinaryHttpJsonResponse() {
        webTestClient.get()
                .uri("/api/status")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.status").isEqualTo("UP")
                .jsonPath("$.checkedAt").isNotEmpty();
    }

    @Test
    void streamsTwoServerSentEvents() {
        Flux<StatusEvent> events = webTestClient.get()
                .uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(StatusEvent.class)
                .getResponseBody()
                .take(2);

        StepVerifier.create(events)
                .expectNextCount(2)
                .verifyComplete();
    }

    @Test
    void echoesWebSocketTextMessage() {
        AtomicReference<String> received = new AtomicReference<>();
        WebSocketClient client = new ReactorNettyWebSocketClient();
        URI uri = URI.create("ws://127.0.0.1:" + port + "/ws/echo");

        Mono<Void> exchange = client.execute(uri, session -> {
            Mono<Void> send = session.send(
                    Mono.just(session.textMessage("hello")));

            Mono<Void> receive = session.receive()
                    .take(1)
                    .filter(message ->
                            message.getType() == WebSocketMessage.Type.TEXT)
                    .doOnNext(message ->
                            received.set(message.getPayloadAsText()))
                    .then();

            return send.and(receive);
        });

        StepVerifier.create(exchange).verifyComplete();
        assertThat(received.get()).isEqualTo("echo: hello");
    }
}
~~~

Test HTTP xác nhận JSON response. Test SSE đọc hai event rồi hủy subscription để không giữ stream vô hạn. Test WebSocket mở session tới server, gửi text message, nhận echo và xác nhận nội dung.

### 7.10. Chạy ứng dụng và kiểm tra

Tại thư mục chứa pom.xml:

~~~bash
mvn test
~~~

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Kiểm tra HTTP thông thường:

~~~bash
curl -i http://localhost:8080/api/status
~~~

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"UP","checkedAt":"2026-11-08T01:00:00Z"}
~~~

Thời gian checkedAt thay đổi theo thời điểm gọi.

Kiểm tra SSE bằng curl. Tham số -N tắt buffering ở phía curl để event hiển thị ngay khi nhận:

~~~bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/api/events
~~~

Output minh họa:

~~~text
id:0
event:status
retry:3000
data:{"sequence":0,"occurredAt":"2026-11-08T01:00:01Z"}

id:1
event:status
retry:3000
data:{"sequence":1,"occurredAt":"2026-11-08T01:00:02Z"}

~~~

Timestamp phụ thuộc thời gian thực. Khi dùng browser, EventSource tự quản lý reconnect.

Kiểm tra WebSocket bằng browser console:

~~~javascript
const scheme = location.protocol === "https:" ? "wss://" : "ws://";
const socket = new WebSocket(scheme + location.host + "/ws/echo");

socket.addEventListener("open", () => {
    socket.send("hello");
});

socket.addEventListener("message", (event) => {
    console.log(event.data); // echo: hello
});

socket.addEventListener("close", (event) => {
    console.log("closed", event.code, event.reason);
});

socket.addEventListener("error", (event) => {
    console.error("websocket error", event);
});
~~~

Có thể dùng một công cụ WebSocket client như websocat nếu đã cài:

~~~bash
websocat ws://localhost:8080/ws/echo
~~~

Nhập hello sẽ nhận echo: hello.

## 8. Bảo mật: HTTP, SSE và WebSocket

### 8.1. TLS

- Dùng HTTPS cho HTTP và SSE.
- Dùng WSS cho WebSocket trên môi trường production.
- Không trộn trang HTTPS với endpoint ws:// không mã hóa; browser thường chặn mixed content.

### 8.2. Authentication và authorization

HTTP thông thường có thể dùng Authorization header, cookie, OAuth2 bearer token hoặc cơ chế xác thực khác.

EventSource native không cho đặt tùy ý Authorization header. Với SSE cùng origin, cookie phiên có thể được gửi theo chính sách browser. Với cross-origin, cần cấu hình CORS và credentials phù hợp; EventSource hỗ trợ withCredentials.

Browser WebSocket API cũng không cho truyền một bộ custom HTTP headers tùy ý trong constructor. Có thể dùng cookie phiên an toàn, xác thực handshake hoặc một protocol cấp token phù hợp. Tránh nhét access token dài hạn vào query string vì URL có thể xuất hiện trong access log, proxy log hoặc telemetry.

Sau handshake, WebSocket vẫn phải kiểm tra quyền cho từng message và từng tài nguyên mà message yêu cầu. Xác thực lúc mở connection không có nghĩa mọi hành động về sau đều được phép.

### 8.3. Origin và Cross-Site WebSocket Hijacking

Với cookie authentication, một website khác có thể cố mở WebSocket tới server của bạn trong browser đang đăng nhập. Server cần kiểm tra Origin theo allowlist và xác thực session đúng cách để ngăn Cross-Site WebSocket Hijacking.

WebSocket handshake có header Origin, nhưng không nên xem đây là thay thế cho authentication. CORS của HTTP không tự động là chính sách bảo vệ đầy đủ cho WebSocket. Hãy cấu hình kiểm tra Origin tại WebSocket endpoint hoặc handshake service.

SSE là HTTP request nên tuân theo chính sách CORS thông thường. Khi cho phép credentials, không dùng wildcard origin; chỉ cho phép origin cụ thể và cấu hình credentials đúng.

### 8.4. Validate payload và giới hạn tài nguyên

Cả SSE lẫn WebSocket đều có thể giữ connection lâu dài. Hãy giới hạn kích thước message và tốc độ gửi, xác thực schema/type/version, kiểm tra quyền theo channel/topic/resource, giới hạn số connection theo user/tenant và đóng connection không còn hoạt động theo chính sách. Không log token, cookie, nội dung cá nhân hoặc payload nhạy cảm.

## 9. Vận hành và mở rộng

### 9.1. Proxy và load balancer

SSE cần response stream được chuyển tiếp liên tục. Proxy buffering có thể khiến event bị gom lại rồi mới gửi, làm mất cảm giác realtime. Tắt buffering cho endpoint SSE khi cần, đặt idle timeout đủ dài và gửi heartbeat định kỳ nếu stream ít event.

WebSocket cần proxy chuyển tiếp handshake Upgrade hoặc hỗ trợ cơ chế WebSocket tương ứng. Load balancer phải giữ connection lâu dài và không đóng vì idle timeout quá ngắn.

### 9.2. Connection count và capacity

HTTP request/response ngắn thường giải phóng tài nguyên sau mỗi thao tác. SSE và WebSocket giữ connection lâu hơn. Khi nhiều chục nghìn client cùng online, server phải quản lý nhiều session, network buffer, heartbeat, scheduler và subscription.

Theo dõi connection đang mở, số SSE stream và WebSocket session, outbound queue size, message rate, latency, reconnect rate, timeout, close code, memory, CPU và network.

Không tạo queue không giới hạn cho mỗi connection. Nếu client chậm, hãy chọn chính sách rõ ràng: backpressure, drop event cũ, gộp trạng thái mới nhất, giới hạn buffer hoặc đóng client quá chậm.

### 9.3. Scale ngang

Nếu ứng dụng có nhiều instance, client có thể kết nối vào các node khác nhau. Một event được tạo ở node A phải tới được những connection đang mở trên node B/C nếu chúng thuộc cùng nhóm nhận.

Thường cần message broker hoặc pub/sub nội bộ để fan-out event giữa các instance. Sticky session chỉ giúp request quay về một node; nó không tự đồng bộ event giữa các node.

Nếu cần replay SSE hoặc WebSocket, lưu event/sequence ở một nơi có thể truy vấn lại. Không dựa vào bộ nhớ của một JVM làm nguồn sự thật khi có nhiều instance hoặc restart.

### 9.4. Heartbeat và timeout

SSE có thể gửi comment heartbeat để giữ stream sống qua proxy. WebSocket có ping/pong control frames để kiểm tra peer còn hoạt động. Ở tầng ứng dụng cũng có thể định nghĩa heartbeat message nếu cần quan sát trạng thái logic.

Đặt timeout phù hợp với proxy, load balancer và client. Heartbeat quá dày làm tăng traffic; quá thưa có thể không ngăn được idle timeout.

## 10. Backpressure và xử lý message trong WebFlux

WebFlux dùng Reactive Streams để điều phối demand và cancellation. Với SSE, controller trả Flux event; với WebSocket, session.receive() và session.send() đều làm việc với Publisher.

- Trả Flux trực tiếp cho framework thay vì gọi subscribe() thủ công.
- Dùng concatMap khi phải xử lý message tuần tự.
- Chỉ dùng flatMap khi xử lý đồng thời có giới hạn.
- Không gọi block() trên event-loop thread.
- Giới hạn queue nếu producer nhanh hơn client.
- Khi client disconnect, cleanup subscription, timer và tài nguyên gắn với session.
- Nếu giữ DataBuffer/WebSocket message qua tác vụ bất đồng bộ trên server dùng pooled buffer, tuân thủ retain/release theo contract.

Backpressure không tự quyết định chính sách nghiệp vụ khi client chậm. Dashboard chỉ cần trạng thái mới nhất có thể gộp nhiều update thành một snapshot. Chat hoặc giao dịch cần giữ từng message có thể cần queue bền vững và acknowledgement.

## 11. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng WebSocket cho mọi endpoint | Tăng độ phức tạp connection và protocol | Dùng HTTP cho request/response thông thường |
| Dùng polling quá ngắn | Nhiều request lặp và tăng tải | Chọn SSE nếu chỉ cần server push |
| Dùng SSE cho chat hai chiều | Client phải gửi message qua HTTP riêng | Dùng WebSocket nếu hai phía cần message liên tục |
| Nghĩ HTTP keep-alive là WebSocket | Nhầm tái sử dụng transport với message channel | Phân biệt request/response và protocol sau handshake |
| Nghĩ SSE tự replay event đã mất | Có thể bỏ lỡ dữ liệu khi disconnect | Lưu event và xử lý Last-Event-ID ở server |
| Không gắn event ID ổn định | Không thể resume có kiểm soát | Dùng sequence/event ID và replay log |
| Nghĩ WebSocket tự reconnect | Client mất kết nối và không phục hồi | Xây dựng backoff, reconnect và resume |
| Nghĩ WebSocket tự bảo đảm giao nhận | Message có thể mất khi connection rớt | Dùng acknowledgement, ID, deduplication và replay |
| Không gửi SSE heartbeat | Proxy có thể đóng stream idle | Gửi comment heartbeat và chỉnh timeout |
| Proxy buffer SSE | Event bị dồn, cập nhật chậm | Tắt buffering cho stream endpoint |
| Proxy không chuyển Upgrade | WebSocket handshake thất bại | Cấu hình chuyển tiếp Upgrade/CONNECT |
| Không kiểm tra Origin | Rủi ro Cross-Site WebSocket Hijacking | Allowlist Origin và xác thực handshake |
| Đặt token trong query string | Token có thể lọt vào log | Dùng cookie an toàn hoặc cơ chế handshake phù hợp |
| Không giới hạn message/queue | Một client có thể làm tăng memory | Đặt payload limit, rate limit và bounded queue |
| Gọi subscribe() trong WebSocket handler | Mất quản lý lifecycle và cancellation | Compose Publisher rồi trả Mono<Void> |
| Giữ connection nhưng không cleanup | Session, timer hoặc subscription bị rò | Cleanup khi complete/error/cancel |
| Coi SSE và WebSocket là cacheable như HTTP GET | Cache/proxy xử lý sai stream | Đặt cache policy phù hợp |

## 12. Checklist chọn giao thức

Trước khi chọn, hãy trả lời:

1. Dữ liệu đi một chiều hay hai chiều?
2. Client có cần gửi message thường xuyên trên cùng connection không?
3. Server có cần đẩy event ngay khi có thay đổi không?
4. Có cần binary message không?
5. Client cần reconnect tự động hay ứng dụng tự kiểm soát?
6. Có cần replay event sau khi mất kết nối không?
7. Có cần acknowledgement hoặc đảm bảo giao nhận không?
8. Browser có cần custom Authorization header không?
9. Proxy, gateway và load balancer hỗ trợ SSE/WebSocket như thế nào?
10. Số lượng connection đồng thời dự kiến là bao nhiêu?
11. Producer xử lý ra sao khi client chậm?
12. Có cần pub/sub giữa nhiều application instance không?
13. Có kiểm tra Origin, authentication và authorization cho từng message không?
14. Có monitoring connection, queue, latency và disconnect không?

## 13. Ghi nhớ

- HTTP thông thường phù hợp với request/response, CRUD, command, query và file transfer.
- HTTP keep-alive tái sử dụng connection nhưng không biến HTTP thành message channel hai chiều.
- SSE giữ HTTP response mở và truyền event một chiều từ server tới client bằng text/event-stream.
- EventSource hỗ trợ named event, reconnect, retry và Last-Event-ID; server phải tự xây dựng event replay.
- WebSocket bắt đầu bằng handshake HTTP rồi chuyển sang protocol frame hai chiều trên connection lâu dài.
- WebSocket hỗ trợ text, binary, ping/pong và close frame; semantics message thuộc về ứng dụng hoặc subprotocol.
- SSE thường đơn giản cho notification/feed/progress; WebSocket phù hợp chat, collaboration và ứng dụng tương tác hai chiều.
- Với Spring WebFlux, SSE dùng Flux<ServerSentEvent<T>>; WebSocket dùng WebSocketHandler, WebSocketSession.receive() và send().
- Cần quản lý timeout, heartbeat, backpressure, queue, connection count, Origin và authentication.
- Với nhiều instance, dùng pub/sub hoặc event broker để phân phối event; sticky session không thay thế đồng bộ dữ liệu.
- Chọn giao thức theo hướng dữ liệu và yêu cầu phục hồi, không chỉ theo độ mới của công nghệ.

**Tài liệu chính thức:**
- [Spring Framework 6.2 — WebFlux WebSocket](https://docs.spring.io/spring/reference/6.2/web/webflux-websocket.html)
- [Spring Framework — WebSocket API and handshake](https://docs.spring.io/spring-framework/reference/web/websocket/server.html)
- [Spring Framework 6.2 Javadoc — ServerSentEvent](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/http/codec/ServerSentEvent.html)
- [Spring Framework 6.2 Javadoc — ServerSentEvent.Builder](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/http/codec/ServerSentEvent.Builder.html)
- [Spring Framework — WebFlux reactive HTTP handling](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [MDN — Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [MDN — EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- [IETF RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)

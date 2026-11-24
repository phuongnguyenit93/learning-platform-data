# Proxy WebSocket hoặc SSE và kiểm chứng truyền dữ liệu liên tục

## 1. Mục tiêu thực hành

Một API Gateway thường xử lý request/response ngắn: client gửi request, Gateway chọn route, upstream trả response rồi kết nối HTTP kết thúc. Nhưng một số tính năng cần **kết nối mở lâu dài**:

Đây là bài thực hành thuộc chương **Thực hành tổng hợp** của module **SPRING_CLOUD_GATEWAY**. **Mô tả module:** Xây dựng API Gateway với Spring Cloud Gateway qua route predicate, filter chain, biến đổi đường dẫn/header và khám phá dịch vụ. Thực hành xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request để vận hành cổng vào microservices an toàn.

- Bảng điều khiển cập nhật trạng thái đơn hàng theo thời gian thực.
- Trang theo dõi tiến trình export hoặc xử lý tác vụ.
- Ứng dụng chat, notification, collaborative editing.
- Dashboard nhận log/metric/event liên tục.

Trong bài này, bạn sẽ dựng một Spring Cloud Gateway WebFlux đứng trước một backend WebFlux và proxy hai kiểu stream:

1. **Server-Sent Events (SSE):** backend gửi sự kiện một chiều qua HTTP response `text/event-stream`; browser dùng `EventSource` để nhận và tự reconnect.
2. **WebSocket:** client và server trao đổi message hai chiều qua một kết nối đã Upgrade từ HTTP.

Topology lab:

~~~mermaid
flowchart LR
    B["Browser / test client"] --> G["Spring Cloud Gateway WebFlux :8080"]
    G -->|"GET /api/events<br/>HTTP stream"| S["Realtime service :9081"]
    G -->|"GET /ws/echo<br/>Upgrade: websocket"| S
    S -->|"text/event-stream"| G
    S <-->|"WebSocket frames"| G
~~~

Sau khi hoàn thành, bạn có thể:

- Phân biệt handshake HTTP với dữ liệu được truyền sau handshake.
- Cấu hình route `http://` cho SSE và `ws://`/`wss://` cho WebSocket.
- Dùng `lb://` hoặc `lb:ws://` khi cần service discovery/load balancing.
- Viết backend reactive phát SSE và xử lý WebSocket messages.
- Kiểm chứng event/frame đi xuyên Gateway, không chỉ kiểm tra HTTP 200/101.
- Xử lý heartbeat, timeout, reconnect, `Last-Event-ID`, Origin, auth và graceful shutdown.
- Nhận biết những filter/policy không phù hợp với stream lâu dài.

**Kết quả cần chứng minh:** dữ liệu phát ở backend đến được client qua Gateway theo thời gian, client nhận nhiều event/frame trên cùng một kết nối, và khi client đóng kết nối thì luồng reactive được hủy phù hợp.

## 2. Chọn đúng giao thức

| Tiêu chí | SSE | WebSocket |
| --- | --- | --- |
| Hướng truyền | Server → client | Hai chiều |
| Transport | HTTP response liên tục | HTTP Upgrade rồi WebSocket frames |
| Content type/handshake | `text/event-stream` | `Upgrade: websocket`, response `101 Switching Protocols` |
| Browser API | `EventSource` | `WebSocket` |
| Reconnect | `EventSource` tự reconnect theo cơ chế SSE | Ứng dụng tự triển khai |
| Resume cursor | `id` và request header `Last-Event-ID` | Ứng dụng tự định nghĩa sequence/cursor |
| Gửi dữ liệu client → server | Dùng HTTP request riêng | Gửi message trên socket |
| Phù hợp | Notification, progress, live feed | Chat, game, collaborative editing, command/response realtime |
| Proxy route | HTTP route thông thường | WebSocket route với scheme `ws`/`wss` |

### 2.1. Khi nào dùng SSE?

Chọn SSE khi server chủ động đẩy event, còn client không cần gửi message liên tục trên cùng kết nối. Ví dụ:

- Trạng thái xử lý `job-42`: queued → running → completed.
- Dashboard hiển thị log mới.
- Trang đơn hàng cập nhật trạng thái giao hàng.
- Notification stream chỉ cần nhận, thao tác xác nhận vẫn gọi REST API.

SSE dùng HTTP nên có thể tận dụng nhiều hạ tầng HTTP hiện có. Browser `EventSource` hỗ trợ reconnect và gửi `Last-Event-ID` nếu server đã phát event có `id`.

### 2.2. Khi nào dùng WebSocket?

Chọn WebSocket khi client và server đều cần gửi message thường xuyên:

- Chat: client gửi tin nhắn, server phát tin nhắn và trạng thái đọc.
- Collaborative editor: client gửi thao tác chỉnh sửa, server broadcast.
- Game: client gửi input, server trả trạng thái.
- Thiết bị realtime: hai phía trao đổi command/event trên một session.

WebSocket không tự định nghĩa message schema, authentication refresh, replay hoặc reconnect. Những phần đó là **application protocol** mà hệ thống phải thiết kế.

### 2.3. Một kết nối lâu dài không phải một chuỗi request độc lập

SSE giữ một HTTP response mở; WebSocket giữ một session sau handshake. Khi đã bắt đầu truyền:

- Không thể đổi backend giữa chừng bằng cách route lại từng event/frame.
- HTTP retry không thể tự phát lại một stream đã gửi một phần mà không có cursor/resume contract.
- Circuit breaker đo việc thiết lập/hoàn tất call theo integration cụ thể; nó không phải cơ chế kiểm tra từng WebSocket frame.
- Client disconnect, proxy idle timeout, backend restart hoặc deploy có thể kết thúc session.

Vì vậy, **reconnect/resume và xử lý trùng/mất event là trách nhiệm của ứng dụng**.

## 3. Chuẩn bị hai ứng dụng Spring Boot riêng

Tạo hai ứng dụng chạy độc lập:

~~~text
realtime-lab/
├── gateway/
│   └── src/main/resources/application.yml
└── realtime-service/
    ├── src/main/java/demo/realtime/
    │   ├── RealtimeApplication.java
    │   ├── EventController.java
    │   ├── EchoWebSocketHandler.java
    │   └── WebSocketConfig.java
    └── src/main/resources/application.yml
~~~

Hai process giúp ta xác minh Gateway thật sự proxy qua mạng thay vì gọi handler cùng process.

### 3.1. Dependencies của Gateway

Với Spring Boot/Spring Cloud BOM tương thích, Maven dependency chính:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Không tự gán version riêng cho starter khi Spring Cloud BOM đã quản lý. Ứng dụng Gateway dùng WebFlux/Reactor Netty; **không ghép Spring Cloud Gateway Server Web MVC vào cùng lab**.

### 3.2. Dependencies của realtime-service

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring WebFlux hỗ trợ `Flux<ServerSentEvent<?>>` để ghi nhiều sự kiện khi chúng đến, và `WebSocketHandler` để ghép inbound/outbound message streams.

### 3.3. Cấu hình port của backend

`realtime-service/src/main/resources/application.yml`:

~~~yaml
server:
  port: 9081

spring:
  application:
    name: realtime-service

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

`RealtimeApplication.java`:

~~~java
package demo.realtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RealtimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RealtimeApplication.class, args);
    }
}
~~~

## 4. Xây SSE endpoint có event ID và heartbeat

SSE là HTTP response có media type `text/event-stream`. Mỗi event có thể chứa:

| Field | Mục đích |
| --- | --- |
| `id` | Cursor để client gửi lại `Last-Event-ID` khi reconnect |
| `event` | Tên event cho `addEventListener` |
| `data` | Payload |
| `retry` | Thời gian browser chờ trước khi reconnect, tính bằng milliseconds |
| comment | Dòng comment, thường dùng heartbeat mà không phát business event |

### 4.1. EventController.java

`realtime-service/src/main/java/demo/realtime/EventController.java`:

~~~java
package demo.realtime;

import java.time.Duration;

import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class EventController {

    @GetMapping(value = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<Flux<ServerSentEvent<String>>> events(
            @RequestHeader(name = "Last-Event-ID", required = false)
            String lastEventId) {

        long resumeAfter = parseEventId(lastEventId);

        Flux<ServerSentEvent<String>> businessEvents =
                Flux.interval(Duration.ofSeconds(1))
                        .map(sequence -> sequence + resumeAfter + 1)
                        .map(sequence -> ServerSentEvent.<String>builder()
                                .id(Long.toString(sequence))
                                .event("tick")
                                .data("event-" + sequence)
                                .retry(Duration.ofSeconds(3))
                                .build());

        Flux<ServerSentEvent<String>> heartbeats =
                Flux.interval(Duration.ofSeconds(15))
                        .map(ignored -> ServerSentEvent.<String>builder()
                                .comment("keepalive")
                                .build());

        Flux<ServerSentEvent<String>> stream =
                Flux.merge(businessEvents, heartbeats)
                        .doFinally(signal -> {
                            // Chỉ log trạng thái/trace ID trong ứng dụng thật.
                            // Không log payload hoặc session credentials.
                        });

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .cacheControl(CacheControl.noCache())
                // Header hữu ích khi phía trước có Nginx.
                .header("X-Accel-Buffering", "no")
                .body(stream);
    }

    private long parseEventId(String lastEventId) {
        if (lastEventId == null || lastEventId.isBlank()) {
            return -1;
        }
        try {
            return Math.max(-1, Long.parseLong(lastEventId));
        } catch (NumberFormatException ignored) {
            return -1;
        }
    }
}
~~~

**Phạm vi resume của lab:** `Last-Event-ID` được đọc để minh họa cursor và tiếp tục số sequence. Trong hệ thống thật, event phải đến từ event log/broker hoặc store có retention; tăng số sequence không có nghĩa đã replay được những event bị lỡ. Chỉ trả event có thật và còn trong retention window.

### 4.2. Heartbeat là comment, không phải business event

Server phát comment:

~~~text
:keepalive

~~~

Browser không phát `message` event cho comment. Heartbeat chỉ giúp một số proxy/load balancer nhận biết kết nối còn hoạt động. Nó không thay thế health check và không chứng minh backend có thể xử lý command.

Đặt heartbeat interval **ngắn hơn idle timeout nhỏ nhất** trong toàn tuyến (browser/mobile network, ingress, Gateway, service mesh, load balancer), có khoảng đệm. Không đoán một con số chung cho mọi môi trường.

### 4.3. Resume thật cần event store

Với production, một flow thường là:

1. Mỗi event có ID tăng đơn điệu hoặc cursor bền vững.
2. Browser nhận event và ghi nhớ `lastEventId`.
3. Khi reconnect, browser gửi `Last-Event-ID`.
4. Server đọc event sau cursor từ store/broker trong thời gian retention.
5. Nếu cursor quá cũ hoặc không hợp lệ, trả tín hiệu reset/resync theo contract.

Nếu event được phát từ nhiều partitions, một số sequence không thể so sánh toàn cục; cursor cần thể hiện partition/offset hoặc opaque token. Không dùng timestamp đơn thuần nếu có thể trùng/thay đổi thứ tự.

## 5. Xây WebSocket echo endpoint

WebSocket bắt đầu bằng HTTP handshake. Sau khi Gateway proxy handshake thành công, kết nối được nâng cấp và message frames được relay qua WebSocket routing infrastructure.

### 5.1. EchoWebSocketHandler.java

`realtime-service/src/main/java/demo/realtime/EchoWebSocketHandler.java`:

~~~java
package demo.realtime;

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
        Flux<WebSocketMessage> replies = session.receive()
                .map(WebSocketMessage::getPayloadAsText)
                .map(text -> session.textMessage("echo: " + text));

        return session.send(replies);
    }
}
~~~

`receive()` là stream inbound; `send()` ghi stream outbound. Khi client đóng session, inbound stream hoàn tất và outbound source được cancel. Không gọi `block()` trên event loop.

Đây là echo handler cho lab, không phải chat server đa người dùng. Để broadcast, cần một broker/topic hoặc một registry session có lifecycle, backpressure, fan-out và cleanup được thiết kế rõ.

### 5.2. WebSocketConfig.java

`realtime-service/src/main/java/demo/realtime/WebSocketConfig.java`:

~~~java
package demo.realtime;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;

@Configuration(proxyBeanMethods = false)
public class WebSocketConfig {

    @Bean
    HandlerMapping webSocketMapping(EchoWebSocketHandler handler) {
        Map<String, WebSocketHandler> handlers =
                Map.of("/ws/echo", handler);

        SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
        mapping.setUrlMap(handlers);
        // WebSocket mapping đứng trước annotated controller mapping.
        mapping.setOrder(-1);
        return mapping;
    }
}
~~~

Spring Boot WebFlux tự cấu hình WebSocket handler adapter cho embedded server được hỗ trợ. Nếu tự xây WebFlux infrastructure ngoài auto-configuration, cần khai báo adapter/service phù hợp.

## 6. Cấu hình Gateway proxy cả hai giao thức

Gateway chạy port `8080`. `gateway/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: realtime-gateway
  cloud:
    gateway:
      server:
        webflux:
          websocket:
            # Lab same-origin: trang test được phục vụ từ http://localhost:8080.
            # Nếu UI dùng origin khác, thêm đúng origin đó.
            allowed-origins:
              - http://localhost:8080
          routes:
            - id: realtime-sse
              uri: http://localhost:9081
              predicates:
                - Path=/api/events

            - id: realtime-websocket
              uri: ws://localhost:9081
              predicates:
                - Path=/ws/**

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Giải thích:

- SSE dùng URI `http://` vì đây là HTTP response streaming.
- WebSocket dùng `ws://`; khi public edge dùng TLS, client kết nối `wss://` tới Gateway và Gateway có thể dùng `ws://` nội bộ trong network tin cậy hoặc `wss://` nếu upstream yêu cầu TLS.
- `Path=/api/events` và `Path=/ws/**` giữ nguyên path tới backend, nên lab không cần `StripPrefix`.
- Gateway WebFlux có WebSocket routing filter nhận diện scheme `ws`/`wss`.
- `allowed-origins` là allowlist cho browser WebSocket handshake. Nếu frontend ở `http://localhost:3000`, thêm đúng origin này thay vì mở tất cả origins.

### 6.1. Đường đi khi dùng service discovery

Khi đã cấu hình discovery/LoadBalancer, có thể đổi upstream:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: realtime-sse
              uri: lb://realtime-service
              predicates:
                - Path=/api/events

            - id: realtime-websocket
              uri: lb:ws://realtime-service
              predicates:
                - Path=/ws/**
~~~

`lb:ws://` cho phép LoadBalancer chọn instance ở **thời điểm thiết lập WebSocket connection**. Sau handshake, session gắn với instance đó trong suốt vòng đời connection; Gateway không chọn lại instance cho từng frame. SSE cũng gắn với một upstream trong suốt response stream.

Không dùng `lb://` nếu chưa có discovery client/LoadBalancer và service instance list phù hợp. Với lab localhost, giữ URI tĩnh.

### 6.2. Cấu hình Gateway 4.x

Nếu dùng Spring Cloud Gateway Server WebFlux 4.x, cấu hình routes thường nằm dưới namespace cũ:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: realtime-sse
          uri: http://localhost:9081
          predicates:
            - Path=/api/events
        - id: realtime-websocket
          uri: ws://localhost:9081
          predicates:
            - Path=/ws/**
~~~

Không đặt đồng thời cả namespace 4.x và 5.x trong một file. Chọn namespace theo starter/BOM thật và kiểm tra routes đã được load trong runtime.

## 7. Thêm trang browser để kiểm tra cả SSE và WebSocket

Để tránh nhầm lẫn Origin, lab phục vụ trang demo qua chính Gateway tại `http://localhost:8080/demo`. Trang và WebSocket handshake vì vậy cùng origin.

### 7.1. DemoPageController.java

`realtime-service/src/main/java/demo/realtime/DemoPageController.java`:

~~~java
package demo.realtime;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoPageController {

    @GetMapping(value = "/demo", produces = MediaType.TEXT_HTML_VALUE)
    public String demo() {
        return """
                <!doctype html>
                <html lang="vi">
                <head>
                  <meta charset="utf-8">
                  <meta name="viewport" content="width=device-width, initial-scale=1">
                  <title>Gateway streaming lab</title>
                </head>
                <body>
                  <h1>WebSocket và SSE qua Gateway</h1>
                  <p>Trang này và Gateway cùng origin: <code id="origin"></code></p>
                  <p>WebSocket: <strong id="ws-state">connecting</strong></p>
                  <input id="message" value="hello gateway" />
                  <button id="send" type="button">Send WebSocket message</button>
                  <p>SSE: <strong id="sse-state">connecting</strong></p>
                  <pre id="log"></pre>
                  <script>
                    const log = (value) => {
                      document.getElementById("log").textContent +=
                        value + "\\n";
                    };
                    document.getElementById("origin").textContent =
                      location.origin;

                    const wsScheme =
                      location.protocol === "https:" ? "wss://" : "ws://";
                    const socket = new WebSocket(
                      wsScheme + location.host + "/ws/echo");

                    socket.addEventListener("open", () => {
                      document.getElementById("ws-state").textContent = "open";
                      log("WebSocket handshake completed");
                    });
                    socket.addEventListener("message", (event) => {
                      log("WS ← " + event.data);
                    });
                    socket.addEventListener("close", (event) => {
                      document.getElementById("ws-state").textContent =
                        "closed (" + event.code + ")";
                    });
                    socket.addEventListener("error", () => {
                      log("WebSocket error; inspect browser Network/Console");
                    });
                    document.getElementById("send").addEventListener(
                      "click", () => {
                        if (socket.readyState !== WebSocket.OPEN) {
                          log("WebSocket is not open");
                          return;
                        }
                        const value =
                          document.getElementById("message").value;
                        socket.send(value);
                        log("WS → " + value);
                      });

                    const events = new EventSource("/api/events");
                    events.addEventListener("open", () => {
                      document.getElementById("sse-state").textContent = "open";
                    });
                    events.addEventListener("tick", (event) => {
                      log("SSE #" + event.lastEventId + " ← " + event.data);
                    });
                    events.addEventListener("error", () => {
                      document.getElementById("sse-state").textContent =
                        "reconnecting or disconnected";
                    });

                    window.addEventListener("beforeunload", () => {
                      socket.close(1000, "page closed");
                      events.close();
                    });
                  </script>
                </body>
                </html>
                """;
    }
}
~~~

### 7.2. Thêm route trang demo vào Gateway

Thêm route này vào `routes` trong `application.yml`:

~~~yaml
- id: realtime-demo-page
  uri: http://localhost:9081
  predicates:
    - Path=/demo
~~~

Route `/demo` chỉ phục vụ HTML lab; SSE và WebSocket vẫn có route riêng. Trong production, trang UI thường được phục vụ từ web server/CDN riêng.

### 7.3. Mở và thao tác

Khởi động cả hai ứng dụng, rồi mở:

~~~text
http://localhost:8080/demo
~~~

Kết quả mong đợi:

- WebSocket state chuyển sang `open`.
- SSE state chuyển sang `open`.
- Mỗi giây log xuất hiện một event `SSE #0`, `SSE #1`, ...
- Nhập message rồi nhấn Send; log xuất hiện `WS → hello gateway` và `WS ← echo: hello gateway`.
- Reload trang sẽ đóng session cũ và thiết lập session mới.

Trong DevTools → Network:

- Request `/ws/echo` có handshake thành công `101 Switching Protocols`; tab Messages/Frames hiển thị echo.
- Request `/api/events` giữ trạng thái pending/open và nhận nhiều event theo thời gian; response có `Content-Type: text/event-stream`.

**Đừng chỉ nhìn `101` hoặc `200`:** handshake thành công chưa chứng minh frame relay, còn SSE 200 chưa chứng minh event tiếp tục được flush tới client.

## 8. Khởi động và kiểm chứng bằng command line

### 8.1. Chạy backend

Trong terminal 1, tại thư mục `realtime-service`:

~~~bash
./mvnw spring-boot:run
~~~

Backend lắng nghe `http://localhost:9081`.

### 8.2. Chạy Gateway

Trong terminal 2, tại thư mục `gateway`:

~~~bash
./mvnw spring-boot:run
~~~

Gateway lắng nghe `http://localhost:8080`.

Nếu dùng Windows PowerShell, Maven Wrapper là `.\mvnw.cmd spring-boot:run`. Đảm bảo hai ứng dụng dùng Spring Boot/Spring Cloud BOM tương thích và không chiếm port của nhau.

### 8.3. Kiểm tra SSE bằng curl

~~~bash
curl -N -i --max-time 5 http://localhost:8080/api/events
~~~

`-N` tắt buffering phía curl; `--max-time 5` kết thúc lệnh sau 5 giây vì server stream không tự hoàn tất. Việc curl kết thúc với timeout sau khi đã in event là **đúng theo lab**, không có nghĩa Gateway trả lỗi.

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

id:0
event:tick
data:event-0
retry:3000

id:1
event:tick
data:event-1
retry:3000
~~~

Header/format có thể được chuẩn hóa khác đôi chút theo encoder/server version; cần xác nhận có nhiều event đến trước khi client timeout.

Kiểm tra cursor của lab:

~~~bash
curl -N -i --max-time 3 \
  -H "Last-Event-ID: 5" \
  http://localhost:8080/api/events
~~~

Event đầu tiên trong fixture này có ID `6`. Đây chỉ là phép thử offset minh họa; production phải replay payload event thật từ event store.

### 8.4. Kiểm tra WebSocket bằng websocat

Nếu đã cài `websocat`:

~~~bash
websocat -v ws://localhost:8080/ws/echo
~~~

Nhập:

~~~text
hello
~~~

Kết quả:

~~~text
echo: hello
~~~

Mỗi dòng nhập phải tạo một frame text và một frame echo. `curl` thông thường không phải WebSocket client đầy đủ; chỉ gửi HTTP GET không có Upgrade không chứng minh WebSocket routing hoạt động.

### 8.5. Kiểm tra endpoint trực tiếp và qua Gateway

SSE trực tiếp:

~~~bash
curl -N --max-time 3 http://localhost:9081/api/events
~~~

SSE qua Gateway:

~~~bash
curl -N --max-time 3 http://localhost:8080/api/events
~~~

WebSocket trực tiếp:

~~~bash
websocat ws://localhost:9081/ws/echo
~~~

WebSocket qua Gateway:

~~~bash
websocat ws://localhost:8080/ws/echo
~~~

So sánh message/event ở hai đường. Đường Gateway phải cho cùng semantics, đồng thời route marker/metrics của Gateway xác nhận traffic đã đi qua edge.

## 9. Smoke tests tự động cho stream

Các tests dưới đây chạy khi cả realtime-service và Gateway đã khởi động. Chúng kiểm tra **dữ liệu thực sự đến từ Gateway**, không chỉ kiểm tra route definition.

### 9.1. Test dependencies

Trong project Gateway, thêm test dependencies nếu chưa có:

~~~xml
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
~~~

Spring WebFlux cung cấp `WebTestClient`; `ReactorNettyWebSocketClient` là client API để mở WebSocket session.

### 9.2. GatewayStreamSmokeTest.java

`gateway/src/test/java/demo/gateway/GatewayStreamSmokeTest.java`:

~~~java
package demo.gateway;

import java.net.URI;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayStreamSmokeTest {

    private final WebTestClient http = WebTestClient.bindToServer()
            .baseUrl("http://localhost:8080")
            .build();

    @Test
    void sseEventsArriveThroughGateway() {
        FluxExchangeResult<ServerSentEvent> result = http.get()
                .uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
                .returnResult(ServerSentEvent.class);

        StepVerifier.create(result.getResponseBody().take(2))
                .assertNext(event -> {
                    assertThat(event.event()).isEqualTo("tick");
                    assertThat(event.id()).isNotBlank();
                    assertThat(event.data()).isNotNull();
                })
                .assertNext(event -> {
                    assertThat(event.event()).isEqualTo("tick");
                    assertThat(event.id()).isNotBlank();
                })
                .verifyComplete(Duration.ofSeconds(5));
    }

    @Test
    void websocketFramesAreRelayedThroughGateway() {
        ReactorNettyWebSocketClient client =
                new ReactorNettyWebSocketClient();
        AtomicReference<String> reply = new AtomicReference<>();

        Mono<Void> conversation = client.execute(
                URI.create("ws://localhost:8080/ws/echo"),
                session -> session.send(Mono.just(
                                session.textMessage("hello")))
                        .then(session.receive()
                                .next()
                                .map(WebSocketMessage::getPayloadAsText)
                                .doOnNext(reply::set)
                                .then()));

        StepVerifier.create(conversation)
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        assertThat(reply.get()).isEqualTo("echo: hello");
    }
}
~~~

Các smoke tests dùng port lab cố định và cần hai process đang chạy. Trong CI, thay bằng dynamic ports/test fixtures và quản lý lifecycle của cả hai server trong test harness. Không để test suite phụ thuộc vào một Gateway đang chạy ngoài CI mà không có health/readiness precondition.

### 9.3. Chạy tests

~~~bash
./mvnw -Dtest=GatewayStreamSmokeTest test
~~~

Kỳ vọng:

- SSE test nhận được hai event `tick` có ID và data.
- WebSocket test nhận được text frame `echo: hello`.
- Test hoàn tất trong thời hạn quy định; stream không bị buffer đến khi hết vô hạn.

Nếu SSE test chỉ nhận response headers nhưng không nhận event, điều tra upstream flush, proxy buffering, codec và timeout. Nếu WebSocket handshake thành công nhưng không có echo, điều tra handler receive/send, Gateway websocket routing và client callback.

## 10. Security: bảo vệ handshake và stream

SSE và WebSocket đều có thể mang dữ liệu riêng tư. Kết nối sống lâu không làm cho authentication/authorization ít quan trọng hơn.

### 10.1. WebSocket Origin không phải authentication

Browser gửi `Origin` trong WebSocket handshake. Gateway WebFlux mặc định chỉ chấp nhận same-origin và handshake không có Origin; cross-origin bị từ chối nếu không nằm trong allowlist.

Ví dụ chỉ cho phép hai frontend cụ thể:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          websocket:
            allowed-origins:
              - https://app.example.test
              - https://admin.example.test
~~~

Origin giúp chống một số kiểu cross-site WebSocket hijacking, nhưng client ngoài browser có thể tự đặt header này. **Không dùng Origin làm danh tính hoặc quyền truy cập**; vẫn phải xác thực principal và authorize endpoint/topic.

Khi Gateway ở sau ingress/reverse proxy, kiểm tra public scheme/host mà Gateway nhìn thấy. Cấu hình forwarded headers chỉ từ proxy tin cậy; nếu không, same-origin check có thể so sánh nhầm origin public với URI nội bộ.

### 10.2. Browser WebSocket và EventSource không đặt được Authorization header tùy ý

Browser constructor `WebSocket` và `EventSource` không cung cấp API chung để tự thêm `Authorization: Bearer ...` header. Các lựa chọn thường dùng:

- Session cookie bảo mật cho browser cùng origin; cookie phải có `Secure`, `HttpOnly`, `SameSite` và scope phù hợp.
- Một one-time connection ticket có TTL rất ngắn, tạo qua HTTPS sau khi xác thực; ticket chỉ dùng một lần và không có quyền rộng.
- Với SSE, dùng `fetch()` streaming nếu cần custom Authorization header và chấp nhận tự xử lý parser/reconnect.
- Native clients có thể dùng client API hỗ trợ Authorization header trong handshake/request.

Tránh đặt access token dài hạn trong query string (`?token=...`): URL thường xuất hiện trong access logs, traces, monitoring và browser history. Nếu bắt buộc dùng ticket query cho browser WebSocket, ticket phải ngắn hạn, một lần, scope hẹp và được redacted khỏi logs.

### 10.3. Xác thực tại handshake, authorize từng hành động

- WebSocket handshake là HTTP request; Security WebFilter chain có thể xác thực trước khi Gateway nâng cấp connection.
- SSE request cũng phải qua authentication/authorization trước khi mở response.
- Kiểm tra quyền theo tenant/resource/topic, không chỉ `authenticated()`.
- Với WebSocket, mỗi inbound command cần được authorize theo user/resource/action; handshake thành công không cho phép mọi message.
- Với SSE, chỉ subscribe vào stream mà principal có quyền đọc; không tin user ID/tenant ID do query/header client tự khai.
- Khi token/session hết hạn, định nghĩa cách đóng/re-auth/reconnect; không giả định connection mở sẽ tự refresh credentials.

### 10.4. CORS cho SSE và Origin cho WebSocket là hai cơ chế khác nhau

SSE dùng HTTP nên cross-origin EventSource cần CORS response headers và browser credentials policy phù hợp. WebSocket handshake không dùng CORS preflight như fetch; Gateway kiểm tra Origin riêng.

Nếu dùng cookie credentials cross-origin:

- Chỉ allowlist origin cụ thể; không dùng wildcard với credentials.
- Cấu hình `Access-Control-Allow-Credentials: true` khi thật sự cần.
- Cookie phải đáp ứng SameSite/Secure theo browser topology.
- Test OPTIONS preflight nếu frontend gửi custom headers qua `fetch()`.

CORS không thay authentication; client native/cURL không bị browser CORS policy ràng buộc.

## 11. Timeout, heartbeat, buffering và resource limits

### 11.1. Timeout của toàn tuyến

Một SSE stream có thể mở hàng phút hoặc hàng giờ. Một HTTP client response timeout quá ngắn, ingress idle timeout hoặc service mesh timeout có thể cắt stream dù backend vẫn hoạt động.

Kiểm tra theo từng hop:

| Hop | Điều cần kiểm tra |
| --- | --- |
| Browser/mobile network | Network change, sleep/background policy, connection lifetime |
| CDN/ingress/reverse proxy | Idle timeout, response buffering, max connection duration |
| Spring Cloud Gateway | HTTP client response timeout, connection pool, graceful shutdown |
| Service mesh/load balancer | Idle timeout, connection draining, TCP keepalive |
| Realtime backend | Session timeout, server shutdown, resource limits |

Gateway WebFlux có property `spring.cloud.gateway.server.webflux.httpclient.response-timeout`. Không đặt một giá trị ngắn toàn cục rồi mong SSE vô hạn hoạt động; cấu hình phải phù hợp với loại route và version. Nếu API ngắn cần timeout thấp nhưng SSE cần sống lâu, tách policy/route hoặc dùng một gateway profile/instance phù hợp.

### 11.2. SSE buffering

Nếu event chỉ xuất hiện thành một cụm sau vài chục giây:

1. Kiểm tra backend thực sự emit event theo interval.
2. Kiểm tra `Content-Type: text/event-stream`.
3. Dùng `curl -N` để loại buffering ở curl.
4. Kiểm tra Nginx/CDN/service mesh có buffering response không.
5. Kiểm tra compression hoặc response-body filter có gom dữ liệu trước khi flush không.
6. Xem proxy logs/packet timing để xác định event bị giữ ở tầng nào.

`X-Accel-Buffering: no` là header riêng hữu ích với Nginx; proxy khác có cơ chế cấu hình riêng. Không giả định header này điều khiển mọi CDN/load balancer.

Tránh dùng `ModifyResponseBody`, local response cache hoặc filter phải buffer toàn bộ body trên SSE route. Một stream vô hạn không có “body hoàn chỉnh” để cache/transform như JSON thông thường.

### 11.3. WebSocket frame size và ping

Gateway WebFlux 5.1 có các property cấu hình HTTP client WebSocket như:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            websocket:
              max-frame-payload-length: 65536
              proxy-ping: true
~~~

Đây là cấu hình ví dụ theo property names của Gateway 5.1; đối chiếu config properties của release thực trước khi dùng. Frame size cần phù hợp contract và giới hạn của backend/ingress. Không nâng lên vô hạn để tránh đóng kết nối; payload lớn nên dùng HTTP/object storage thay vì một WebSocket frame khổng lồ.

Ping/pong ở protocol layer giúp phát hiện kết nối chết trên một số đường truyền. Ứng dụng vẫn có thể cần **application heartbeat** (ví dụ JSON `{"type":"ping"}` / `{"type":"pong"}`) để xác minh backend đang xử lý message. Đừng nhầm TCP/WebSocket ping được proxy trả lời với business service còn khỏe.

### 11.4. Backpressure và giới hạn tài nguyên

Mỗi kết nối mở chiếm socket/file descriptor, buffers, state và một phần tài nguyên ở Gateway lẫn backend. Với hàng chục nghìn connections, cần capacity plan riêng:

- Giới hạn concurrent connections theo tenant/client và node.
- Giới hạn message/frame size, event rate và outbound queue.
- Không tạo unbounded `onBackpressureBuffer()` cho slow consumers.
- Chọn policy theo loại event: drop event cũ, coalesce trạng thái mới nhất, disconnect slow consumer hoặc persist để replay.
- Đóng session khi client không đọc/không heartbeat theo contract.
- Theo dõi memory/direct buffers, file descriptors, active sessions và queue depth.

SSE progress có thể coalesce thành trạng thái mới nhất; chat messages hoặc audit events thường không được drop tùy tiện. Backpressure policy phải theo semantics nghiệp vụ.

### 11.5. Không retry stream như một request JSON

Retry có thể hữu ích trước khi response/handshake được thiết lập nếu policy và semantics cho phép, nhưng **không thể phát lại an toàn một stream đã gửi một phần**:

- SSE: client reconnect và gửi `Last-Event-ID`; server replay từ event store.
- WebSocket: client reconnect và gửi resume cursor/last acknowledged sequence ở application protocol.
- Một command ghi qua WebSocket cần command ID/idempotency key để chống gửi lại khi client không biết server đã xử lý hay chưa.

Không gắn Retry filter toàn cục vào routes SSE/WebSocket. Không giả định CircuitBreaker filter kiểm tra health của từng event/frame trong một session đã được upgrade.

## 12. Reconnect và graceful shutdown

### 12.1. SSE reconnect

Browser `EventSource` tự reconnect khi connection bị đóng ngoài ý muốn. Nếu event có `id`, browser gửi `Last-Event-ID` trong request kế tiếp. Server phải:

- Replay các event còn trong retention sau cursor đó.
- Không gửi lại event vượt quyền principal hiện tại.
- Xử lý cursor không hợp lệ/hết retention bằng resync contract.
- Chấp nhận duplicate delivery; client nên xử lý idempotently theo event ID.
- Có giới hạn tốc độ reconnect/backoff khi backend đang outage.

Lab chỉ tạo sequence tăng dần để quan sát header; chưa có event store nên **không đảm bảo replay dữ liệu đã mất**.

### 12.2. WebSocket reconnect

Browser WebSocket API không tự reconnect. Client phải:

1. Nhận close/error.
2. Chờ backoff có jitter.
3. Tạo connection mới và xác thực lại.
4. Gửi resume cursor/last acknowledged sequence nếu protocol hỗ trợ.
5. Re-subscribe vào topics mà principal còn quyền.
6. Deduplicate message theo ID nếu có thể nhận lại message cũ.

Không retry liên tục ngay lập tức; một outage có thể làm hàng nghìn clients reconnect cùng lúc. Dùng exponential backoff + jitter và cap.

### 12.3. Gateway/backend deploy và draining

Một WebSocket session không thể được chuyển nguyên trạng sang instance khác khi pod bị terminate. SSE cũng bị ngắt khi process đóng. Kế hoạch deploy nên:

- Đánh dấu instance không nhận kết nối mới (readiness/drain) trước khi terminate.
- Cho connections hiện tại một grace period có giới hạn.
- Gửi tín hiệu reconnect/retry hợp lệ nếu ứng dụng có protocol hỗ trợ.
- Cho client reconnect tới instance khỏe và resume từ cursor.
- Đặt `spring.lifecycle.timeout-per-shutdown-phase`/termination grace phù hợp, nhưng không giả định một stream vô hạn sẽ hoàn tất trong grace period.
- Test rolling update với connections đang mở và một lượng traffic đại diện.

Spring Boot hỗ trợ graceful shutdown cho embedded Reactor Netty/Tomcat/Jetty. Graceful shutdown cho phép request hiện có một khoảng thời gian hoàn tất; nó không đảm bảo giữ session mãi mãi hoặc chuyển session sang pod khác.

## 13. Observability cho kết nối lâu dài

HTTP request metrics đơn thuần không đủ để hiểu stream. Cần đo:

| Metric/log | Ý nghĩa |
| --- | --- |
| Active SSE connections | Số response streams đang mở |
| Active WebSocket sessions | Số socket sessions đang mở |
| Handshake success/failure | Tỷ lệ Upgrade thành công, 401/403/5xx |
| Stream duration | Kết nối sống bao lâu trước khi kết thúc |
| Events/frames sent and received | Throughput dữ liệu |
| Bytes per connection | Băng thông và payload size |
| Reconnect/resume count | Tần suất mất kết nối và phục hồi |
| Close code/reason category | Lỗi mạng, client close, server shutdown, policy |
| Slow-consumer/queue depth | Backpressure và memory risk |
| Last-Event-ID replay lag | Số event/offset còn phải replay |

### 13.1. Trace và log an toàn

- Gắn trace/correlation ID vào handshake và context của session nếu framework/application hỗ trợ.
- Với stream dài, cân nhắc span handshake riêng và metrics cho lifetime; không tạo span cho từng frame nếu cardinality/volume quá lớn.
- Không log cookie, Authorization token, one-time ticket hoặc toàn bộ message payload nhạy cảm.
- Không dùng session ID, user ID, topic ID không giới hạn làm Prometheus labels.
- Ghi close reason theo nhóm đã chuẩn hóa, không đưa raw client text vào metric label.

### 13.2. Phân biệt Gateway metrics với ứng dụng metrics

Gateway có thể đo route request/handshake và upstream latency. Nhưng business service mới biết event nào đã được publish/acknowledged, message nào bị duplicate và client nào đã xử lý. Kết hợp cả hai:

~~~text
Gateway:
  route=realtime-websocket
  handshake=success
  connection_duration=...

Realtime service:
  session_opened=...
  messages_received=...
  messages_sent=...
  reconnect_resume=...
  slow_consumer_disconnect=...
~~~

Không kết luận “stream khỏe” chỉ vì Gateway handshake status 101 hoặc SSE status 200.

## 14. Negative tests và troubleshooting

### 14.1. Ma trận kiểm thử

| Test | Cách làm | Kết quả mong đợi |
| --- | --- | --- |
| SSE qua Gateway | `curl -N` hoặc EventSource vào `/api/events` | Nhận nhiều event, ID tăng |
| WebSocket qua Gateway | Mở `/ws/echo`, gửi text | Nhận echo frame |
| Sai path | Gọi `/unknown/stream` | Không route vào realtime service |
| SSE sai method | Gửi POST tới `/api/events` | Backend/Gateway từ chối; không tạo stream |
| WebSocket không Upgrade | Gửi GET thường tới `/ws/echo` | Không có handshake 101 |
| Origin ngoài allowlist | Browser từ origin không được phép mở socket | Gateway từ chối handshake, thường là 403 |
| Client đóng SSE | Gọi `EventSource.close()` | Backend stream bị cancel/cleanup |
| Client đóng WebSocket | `socket.close(1000)` | Backend session hoàn tất và release state |
| Backend restart | Restart realtime-service khi stream đang mở | Connection mất; client reconnect theo contract |
| Gateway restart | Drain/restart Gateway | Client reconnect, SSE resume nếu event store có |
| Event buffer proxy | Bật/tắt response buffering ở test proxy | Phát hiện event có bị gom lại không |
| Slow consumer | Đọc chậm hoặc ngừng đọc | Queue/connection xử lý theo policy, memory không tăng vô hạn |
| Payload quá lớn | Gửi frame vượt max size | Bị giới hạn/từ chối theo config |

### 14.2. Troubleshooting nhanh

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| WebSocket trả 404 | Route predicate sai hoặc backend path sai | `Path`, route ID, mapping `/ws/echo` |
| WebSocket trả 403 | Origin không được allowlist hoặc Security từ chối | Origin thực, forwarded host/scheme, authentication |
| Handshake 101 nhưng không có echo | Handler không nhận/gửi, client callback kết thúc sớm | `session.receive()`, `session.send()`, Network Frames |
| Handshake 400/426 | Request thiếu Upgrade headers hoặc đi nhầm HTTP route | Client dùng `ws://`/`wss://`, route URI scheme |
| WebSocket disconnect sau một khoảng idle cố định | Proxy/LB idle timeout | So sánh disconnect time với heartbeat interval và idle timeout |
| SSE 200 nhưng không thấy event | Backend không emit hoặc response bị buffer | `curl -N`, event controller, proxy buffering |
| SSE event tới theo lô | Compression/proxy response buffering | `X-Accel-Buffering`, CDN/ingress config |
| SSE disconnect sau N giây | Response timeout/idle timeout/connection max age | Gateway HTTP client, ingress, service mesh |
| EventSource reconnect nhưng mất event | Không có replay store hoặc cursor xử lý sai | `Last-Event-ID`, retention, partition/offset |
| EventSource reconnect quá dồn dập | Retry delay thấp hoặc không có backoff | SSE `retry`, proxy outage, client network |
| WebSocket reconnect nhưng command bị lặp | Client retry command không có ID | Command idempotency/deduplication |
| Chỉ một pod nhận toàn bộ sockets | Long-lived sessions bám instance đã chọn | LoadBalancer distribution lúc handshake, connection count |
| Một pod deploy xong còn session cũ bị cắt | Rolling shutdown/drain | Readiness, grace period, reconnect/resume |
| 502/503 khi chọn `lb:ws://` | Discovery không có instance hoặc WS scheme không được route | Discovery client, service ID, LoadBalancer dependency |
| Browser WebSocket cross-origin lỗi | Allowed origins không khớp | Origin chính xác gồm scheme/host/port |
| SSE cross-origin lỗi | CORS/credentials policy sai | OPTIONS, ACAO, credentials, cookie SameSite |
| Gateway memory tăng theo thời gian | Buffer unbounded, sessions leak, slow consumers | Heap/direct memory, queue depth, cleanup hooks |
| Metrics báo 200/101 nhưng user không nhận dữ liệu | Chỉ đo handshake/response status | Events/frames counters, stream duration, browser trace |

### 14.3. Quy trình điều tra theo lớp

1. Kiểm tra client API/URL và scheme (`http`, `https`, `ws`, `wss`).
2. Kiểm tra handshake/HTTP response headers.
3. Xác nhận Gateway route ID và URI scheme thực tế.
4. Gọi trực tiếp backend để tách lỗi Gateway với lỗi handler.
5. Kiểm tra Origin, Security, cookie/token và quyền subscription.
6. Đo thời điểm event/frame đầu tiên và khoảng cách giữa các lần gửi.
7. Kiểm tra timeout/buffering/heartbeat trên từng proxy hop.
8. Kiểm tra close reason, cancellation và cleanup tại backend.
9. Kiểm tra replay cursor/deduplication sau reconnect.
10. Chạy lại positive/negative tests sau khi sửa route hoặc timeout.

## 15. Bài tập mở rộng

### Bài 1 — Thay backend tĩnh bằng service discovery

Đưa realtime-service vào discovery registry với ít nhất hai instances. Đổi routes sang:

~~~yaml
- id: realtime-sse
  uri: lb://realtime-service
  predicates:
    - Path=/api/events

- id: realtime-websocket
  uri: lb:ws://realtime-service
  predicates:
    - Path=/ws/**
~~~

Mở nhiều WebSocket sessions và ghi nhận instance được chọn ở handshake. Chứng minh frame tiếp theo vẫn thuộc session đó; khi reconnect, client có thể được route tới instance khác.

### Bài 2 — SSE replay từ event store

Thay `Flux.interval` bằng một event store có retention:

- Mỗi event có ID bền vững.
- Client gửi `Last-Event-ID`.
- Server replay event sau cursor rồi chuyển sang live tail.
- Nếu cursor hết retention, server yêu cầu client resync snapshot.
- Hai Gateway/backend instances vẫn replay được từ cùng event log.

Test mất kết nối giữa event 10 và 13; khi reconnect, client phải nhận event còn thiếu theo đúng thứ tự hoặc nhận tín hiệu resync.

### Bài 3 — WebSocket resume và deduplication

Thiết kế protocol JSON:

~~~json
{"type":"command","commandId":"cmd-001","sequence":42,"payload":{"text":"hello"}}
~~~

Backend trả acknowledgement có cùng `commandId`. Khi client reconnect và gửi lại command chưa nhận ACK, backend deduplicate theo principal + command ID và không thực hiện side effect hai lần.

### Bài 4 — Cross-origin security

Chạy UI trên origin khác, ví dụ `http://localhost:3000`:

- Cho phép đúng origin này trong WebSocket `allowed-origins`.
- Cấu hình CORS cho SSE nếu dùng EventSource cross-origin.
- Kiểm tra request từ origin thứ ba bị từ chối.
- Thử request không có Origin từ native test client.
- Chứng minh Origin allowlist không thay JWT/session authorization.

### Bài 5 — Kiểm tra timeout và heartbeat

Đặt idle timeout thấp trong reverse proxy test. So sánh:

- SSE không heartbeat.
- SSE có comment heartbeat.
- WebSocket không có app heartbeat.
- WebSocket có app-level ping/pong message.

Đo thời gian disconnect, số reconnect và lượng dữ liệu được truyền. Chọn heartbeat interval nhỏ hơn idle timeout có khoảng đệm, không phát heartbeat quá dày gây tải không cần thiết.

### Bài 6 — Rolling deploy với connections đang mở

Mở nhiều SSE/WebSocket sessions, sau đó rolling restart realtime-service:

- Đo số session bị ngắt.
- Kiểm tra readiness/drain.
- Kiểm tra reconnect/backoff.
- Kiểm tra SSE replay và WebSocket resume.
- Đảm bảo không mất hoặc xử lý trùng business command.

Không dùng môi trường production nếu chưa có kế hoạch load/fault test được phê duyệt.

### Bài 7 — Slow consumer và backpressure

Tạo client đọc chậm hơn tốc độ server phát:

- Đo queue depth, memory và disconnect time.
- So sánh drop/coalesce/disconnect/persist strategies.
- Chứng minh queue có giới hạn.
- Chọn policy riêng cho progress, notification, chat và audit events.

## 16. Câu hỏi tự kiểm tra

**1. SSE và WebSocket khác nhau ở hướng truyền nào?**

SSE chủ yếu server → client trên HTTP response; WebSocket hỗ trợ hai chiều sau HTTP Upgrade.

**2. Gateway dùng URI scheme nào để proxy SSE?**

SSE dùng HTTP route `http://` hoặc `lb://`; response có media type `text/event-stream`.

**3. Gateway dùng URI scheme nào để proxy WebSocket?**

Dùng `ws://` hoặc `wss://`. Khi load balance, có thể dùng prefix `lb:ws://service-id`.

**4. Vì sao handshake 101 chưa đủ chứng minh WebSocket hoạt động?**

101 chỉ xác nhận upgrade. Cần gửi/nhận frames và kiểm tra session lifetime/close behavior.

**5. Vì sao SSE response 200 chưa đủ chứng minh streaming?**

Server có thể trả headers rồi buffer body. Cần xác nhận nhiều event được flush tới client theo thời gian.

**6. Browser EventSource reconnect bằng cách nào?**

Nó tự reconnect theo retry delay và gửi `Last-Event-ID` nếu các event trước có ID.

**7. Tăng sequence sau Last-Event-ID có phải replay thật không?**

Không. Server phải đọc event thực từ event store/broker trong retention; chỉ tăng số sequence không phục hồi payload đã mất.

**8. Browser WebSocket có thể đặt Authorization header tùy ý không?**

Không qua constructor chuẩn. Có thể dùng cookie session hoặc one-time ticket ngắn hạn; vẫn phải xác thực và authorize.

**9. Origin allowlist có thay authentication không?**

Không. Origin là kiểm soát nguồn browser handshake, không phải danh tính; native clients có thể tự đặt Origin.

**10. Vì sao không dùng Retry filter để phục hồi một WebSocket session?**

Retry không thể phát lại frame đã gửi một phần hay tái tạo session state. Client cần reconnect và application-level resume/deduplication.

**11. Vì sao `lb:ws://` không cân bằng từng message?**

LoadBalancer chọn backend khi handshake; connection sau đó gắn với instance đã chọn cho tới khi session đóng.

**12. Vì sao cần heartbeat?**

Heartbeat giúp phát hiện hoặc tránh một số idle timeouts; nó không chứng minh business handler khỏe và phải được đặt theo timeout nhỏ nhất của toàn tuyến.

**13. Vì sao phải giới hạn frame size và outbound queue?**

Để bảo vệ memory, direct buffers và file descriptors khi client chậm hoặc gửi payload lớn.

**14. Graceful shutdown có giữ WebSocket session mãi mãi không?**

Không. Nó chỉ cho request/session đang tồn tại một khoảng grace period; client vẫn cần reconnect/resume khi process kết thúc.

**15. SSE cross-origin và WebSocket cross-origin có cùng cơ chế CORS không?**

Không. SSE là HTTP và dùng CORS; Gateway kiểm tra Origin riêng cho WebSocket handshake.

## 17. Tài liệu tham khảo

1. [Spring Cloud Gateway 5.1 — Global Filters / WebSocket Routing Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html): cách Gateway WebFlux nhận diện `ws`/`wss`, dùng `lb:ws://` và cấu hình Origin.
2. [Spring Cloud Gateway 5.1 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html): WebSocket allowed origins, response timeout, max frame payload length và ping proxy.
3. [Spring Cloud Gateway 4.3 — Global Filters](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/global-filters.html): đối chiếu behavior của dòng 4.x.
4. [Spring Framework — WebFlux WebSocket](https://docs.spring.io/spring-framework/reference/web/webflux/websocket.html): `WebSocketHandler`, `WebSocketSession`, send/receive streams và WebSocket client.
5. [Spring Framework — WebFlux Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): reactive return types và `Flux<ServerSentEvent<?>>`.
6. [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): grace period và `spring.lifecycle.timeout-per-shutdown-phase`.
7. [WHATWG — Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html): event format, `id`, `retry`, reconnect và `Last-Event-ID`.
8. [MDN — Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): EventSource, browser reconnect và event listeners.
9. [MDN — WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket): browser WebSocket lifecycle, send/receive và close.
10. [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html): opening handshake, frames, control frames, close behavior.

**Ghi nhớ:** SSE là HTTP response streaming một chiều; WebSocket là session hai chiều sau HTTP Upgrade. Gateway WebFlux proxy SSE qua route HTTP và WebSocket qua `ws://`/`wss://` (hoặc `lb:ws://` khi có LoadBalancer). Kiểm chứng phải quan sát **event/frame thực sự tới client**, không dừng ở HTTP 200/101. Kết nối lâu dài cần Origin/auth đúng, heartbeat nhỏ hơn idle timeout, backpressure/size limits, reconnect/resume và graceful draining. Với SSE, `Last-Event-ID` chỉ có giá trị khi server replay được event thật từ store; với WebSocket, client cần protocol-level cursor/acknowledgement và deduplication cho command. Đây là trách nhiệm của ứng dụng phối hợp với Gateway, không phải thứ một route filter có thể tự đảm bảo.

## 18. Checklist trước khi đưa stream ra môi trường thật

### Routing và transport

- [ ] SSE route dùng HTTP URI và trả `Content-Type: text/event-stream`.
- [ ] WebSocket route dùng `ws://`/`wss://`; handshake và frames đều được kiểm tra.
- [ ] Nếu dùng discovery, có service instance list và route `lb:ws://` đúng.
- [ ] Không rewrite/strip path ngoài ý muốn; backend mapping khớp public path.
- [ ] Không áp retry/cache/body-transform filter chung lên stream routes.
- [ ] SockJS fallback (nếu dùng) có cả route HTTP và WebSocket tương ứng.

### Security

- [ ] WebSocket Origin allowlist cụ thể; Origin không được coi là authentication.
- [ ] SSE CORS policy riêng nếu cross-origin.
- [ ] Authentication xảy ra trước handshake/stream; subscription/topic có authorization.
- [ ] Browser token không nằm trong URL hoặc logs.
- [ ] Cookie, one-time ticket và token expiry có reconnect/re-auth contract.
- [ ] TLS public edge và TLS/mTLS upstream được xác minh; không dùng insecure trust manager.
- [ ] Forwarded headers chỉ được tin từ proxy đã kiểm soát.

### Reliability và capacity

- [ ] Heartbeat interval nhỏ hơn idle timeout nhỏ nhất trên toàn tuyến.
- [ ] Gateway response timeout không cắt SSE theo một giá trị chung quá ngắn.
- [ ] SSE event store có retention/cursor nếu cần replay.
- [ ] WebSocket command có ID/ack/deduplication nếu có side effect.
- [ ] Frame size, event rate, active connections và outbound queues có giới hạn.
- [ ] Slow consumers có policy; không có unbounded buffers.
- [ ] Reconnect có exponential backoff + jitter và cap.
- [ ] Rolling deploy có readiness/draining và client resume/reconnect.
- [ ] Đã test backend/Gateway restart khi connections đang mở.

### Observability và kiểm thử

- [ ] Đo active connections, duration, events/frames, bytes, reconnect và close reasons.
- [ ] Có dashboard theo route, service instance và deployment revision.
- [ ] Không log secrets, token, cookie hoặc payload nhạy cảm.
- [ ] Có positive tests và negative tests cho SSE/WebSocket.
- [ ] Tests xác nhận nhiều event/frame được nhận qua Gateway.
- [ ] Có test Origin không hợp lệ, auth thất bại và client disconnect.
- [ ] Có test slow consumer, timeout, proxy buffering và rolling shutdown.
- [ ] CI xác nhận số test thực thi, không chỉ build thành công.

## 19. Ghi chú tương thích và mở rộng

### 19.1. SockJS

Nếu ứng dụng dùng SockJS để fallback khi WebSocket không khả dụng, cần route HTTP cho các endpoint SockJS info/polling và route WebSocket cho endpoint upgrade. Không cấu hình một route `ws://` duy nhất rồi kỳ vọng nó xử lý mọi fallback HTTP transport.

### 19.2. Gateway WebFlux và Web MVC

Bài thực hành này dùng **Gateway Server WebFlux**. Gateway Server Web MVC có cách cấu hình WebSocket, buffering và backpressure khác; không copy property `server.webflux.*` sang `server.webmvc.*`. Với Web MVC, phải xem tài liệu riêng về giới hạn buffer/session và cách container xử lý ping/pong.

### 19.3. Metrics trong lab

Gateway route metrics có thể được bật rõ trong profile lab:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          metrics:
            enabled: true
~~~

Actuator `metrics` phải được bảo vệ trong môi trường thật. Gateway request metrics vẫn không thay thế business counters về event/frame/session tại realtime-service.

### 19.4. Graceful shutdown mẫu

Có thể cấu hình rõ grace period cho lab:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

`30s` chỉ là giá trị minh họa. Chọn thời gian theo termination grace, thời gian drain và reconnect policy. Không đặt grace period vô hạn để giữ connections cũ; rolling deploy cần có cách phục hồi sau khi session bị đóng.

### 19.5. TLS trên public edge và upstream

Client production kết nối:

~~~text
https://realtime.example.test/api/events
wss://realtime.example.test/ws/echo
~~~

Gateway terminate TLS ở public edge bằng certificate hợp lệ. Nếu upstream cũng yêu cầu TLS/mTLS, route dùng `https://`/`wss://` với trust/key material được quản lý qua SSL bundles hoặc cấu hình client phù hợp. Không tắt certificate verification để sửa lỗi handshake.

**Hoàn thành lab khi:** bạn mở được `/demo`, thấy SSE events tăng dần, gửi được WebSocket message và nhận echo, xác nhận route qua Gateway bằng DevTools/metrics, và giải thích được cách hệ thống phục hồi khi connection bị ngắt.

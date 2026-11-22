# Thực hành cập nhật thời gian thực: lựa chọn SSE hoặc WebSocket trong Spring Web

Một dashboard cần thấy đơn hàng mới mà không phải Refresh; một ứng dụng chat cần người dùng gửi và nhận tin nhắn liên tục. Cả hai đều là “cập nhật thời gian thực”, nhưng đường truyền có yêu cầu khác nhau. **Server-Sent Events (SSE)** dùng một HTTP response giữ mở để server gửi nhiều sự kiện **một chiều đến client**. **WebSocket** nâng cấp kết nối HTTP thành kênh message **hai chiều**.

Bài này tập trung vào Spring MVC (Servlet stack), Java 17+ và Spring Boot 3.3. Ta viết một ứng dụng mini có cả SSE và WebSocket, dùng chung dữ liệu, rồi kiểm tra cách truyền, reconnect và những giới hạn khi đưa lên môi trường thật. Mục tiêu là chọn giao thức từ nhu cầu thay vì mặc định WebSocket luôn “real-time hơn”.

## 1. Chọn giao thức theo hướng truyền và yêu cầu phục hồi

| Tiêu chí | SSE | WebSocket |
| --- | --- | --- |
| Luồng dữ liệu trên một kết nối | Server → client | Server ⇄ client |
| Transport | HTTP streaming, `text/event-stream` | HTTP handshake, `101 Switching Protocols`, sau đó là WebSocket frames |
| JavaScript browser | `EventSource` | `WebSocket` |
| Client gửi lên server | Dùng POST/PUT/HTTP riêng | `socket.send(...)` trên cùng kết nối |
| Tự reconnect | `EventSource` tự thử lại khi đứt; có `retry`/`Last-Event-ID` | Native WebSocket không tự reconnect; ứng dụng quản lý retry/re-subscribe |
| Nội dung message | UTF-8 text events, có thể mang JSON | Text/binary frame, format do ứng dụng/subprotocol quy định |
| Ví dụ phù hợp | Progress tác vụ, thông báo, feed, dashboard chỉ đọc | Chat, chỉnh sửa cộng tác, điều khiển hai chiều, sự kiện client thường xuyên |
| Khả năng replay | Có trường ID hỗ trợ thiết kế resume, nhưng **server phải lưu và phát lại** | Tự thiết kế id/ack/replay theo nghiệp vụ |
| Hạ tầng | Proxy phải cho streaming, tránh buffering và idle timeout quá ngắn | Proxy/load balancer phải xử lý handshake Upgrade, keepalive và WebSocket timeout |
| Chi phí | Kết nối HTTP tồn tại lâu, có thể chịu giới hạn connection/stream | Mỗi phiên WS giữ tài nguyên kết nối, cần xử lý client chậm và fan-out |

Cần server **chỉ đẩy cập nhật** còn các thao tác gửi lên ít và vốn đã có REST API: ưu tiên thử **SSE + POST**. Cần client gửi nhiều loại message thường xuyên trên cùng channel: thử **WebSocket**. Cần subscriptions, topic, routing người dùng và broker: cân nhắc **STOMP trên WebSocket**, khác với raw handler của bài này. Nếu dữ liệu chỉ đổi mỗi vài phút, HTTP polling có thể đáp ứng với độ phức tạp thấp hơn.

**Quan trọng:** SSE hay WebSocket đều không tự bảo đảm tin nhắn không mất, “exactly once”, phân phối thứ tự toàn hệ thống hoặc lịch sử khi reconnect. Đó là những quyết định của lớp ứng dụng, lưu trữ và event broker.

## 2. HTTP stream SSE khác WebSocket như thế nào?

### SSE: một response mang nhiều sự kiện

Trình duyệt mở HTTP request:

```http
GET /api/updates/stream HTTP/1.1
Accept: text/event-stream
```

Server giữ response mở và lần lượt gửi:

```text
retry: 3000
event: ready
data: connected

id: 17
event: update
data: {"id":17,"source":"http","message":"Có đơn mới","time":"2026-10-21T10:00:00Z"}

: keepalive

```

Mỗi event có thể gồm `id:`, `event:`, `data:`, `retry:` và **kết thúc bằng dòng trống**. Dòng mở đầu `:` là comment/heartbeat. JavaScript dùng `addEventListener("update", ...)` cho named event `update`; `onmessage` chỉ nhận unnamed `message` event.

`EventSource` tự kết nối lại và có thể gửi header `Last-Event-ID` khi đã nhận sự kiện có `id`. Nếu server không lưu lịch sử để tra cứu từ ID ấy thì reconnect chỉ giúp nhận các sự kiện **mới**, hoàn toàn không bảo đảm bù sự kiện đã lỡ.

### WebSocket: handshake rồi hai phía gửi frames

```text
Browser -- HTTP Upgrade /ws/updates --> Spring WebSocket
Browser <-- 101 Switching Protocols --  Spring WebSocket
Browser <--- text/binary frames ---> WebSocketHandler
```

Một raw WebSocket handler không có sẵn cơ chế subscribe topic, ack hay message schema. Bài này quy ước client gửi chuỗi ngắn; server phát JSON đến toàn bộ client đang kết nối. Nếu dùng STOMP, message sẽ có frames/destinations theo STOMP và phải cấu hình `@EnableWebSocketMessageBroker` với client STOMP tương ứng.

## 3. Khởi tạo project demo

Project dùng Spring Boot 3.3 và Java 17+ với dependencies Gradle (version được Boot quản lý):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` hỗ trợ Spring MVC, embedded Servlet server; `spring-boot-starter-websocket` thêm WebSocket. Không cần thay thành WebFlux chỉ để dùng `SseEmitter`.

Cấu trúc tệp:

```text
src/main/java/com/example/realtime/
  RealtimeApplication.java
  LiveHub.java
  UpdatesController.java
  UpdateSocketHandler.java
  WebSocketConfig.java
src/main/resources/static/
  index.html
src/test/java/com/example/realtime/
  UpdatesControllerTest.java
```

Tệp `RealtimeApplication.java`:

```java
package com.example.realtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class RealtimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RealtimeApplication.class, args);
    }
}
```

`@EnableScheduling` phục vụ heartbeat SSE theo lịch. Sử dụng scheduler được Spring quản lý, không tạo thêm một thread riêng cho mỗi subscriber.

## 4. Một trung tâm phát sự kiện cho cả SSE và WebSocket

Tệp `LiveHub.java` dưới đây lưu subscribers trong memory **của một JVM**. Các cập nhật từ REST hoặc WebSocket được serialize cùng kiểu JSON; có một chuỗi `id` để minh họa nhận diện event.

```java
package com.example.realtime;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;

@Component
public class LiveHub {
    private final ObjectMapper mapper;
    private final AtomicLong sequence = new AtomicLong();
    private final ConcurrentMap<String, SseEmitter> emitters =
            new ConcurrentHashMap<>();
    private final Set<WebSocketSession> sockets =
            ConcurrentHashMap.newKeySet();

    public LiveHub(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public record UpdateEvent(
            long id, String source, String message, Instant time) {}

    public SseEmitter subscribeSse() {
        SseEmitter emitter =
                new SseEmitter(TimeUnit.MINUTES.toMillis(5));
        String subscriptionId = UUID.randomUUID().toString();

        emitters.put(subscriptionId, emitter);
        emitter.onCompletion(() -> emitters.remove(subscriptionId));
        emitter.onTimeout(() -> emitters.remove(subscriptionId));
        emitter.onError(error -> emitters.remove(subscriptionId));

        try {
            emitter.send(SseEmitter.event()
                    .name("ready")
                    .reconnectTime(3000)
                    .data("connected"));
        } catch (IOException | IllegalStateException ex) {
            emitters.remove(subscriptionId);
            emitter.completeWithError(ex);
        }
        return emitter;
    }

    public void addSocket(WebSocketSession session) {
        sockets.add(session);
    }

    public void removeSocket(WebSocketSession session) {
        sockets.remove(session);
    }

    public UpdateEvent publish(String raw, String source) {
        if (raw == null || raw.isBlank() || raw.length() > 200) {
            throw new IllegalArgumentException(
                    "message phải chứa 1..200 ký tự");
        }

        UpdateEvent event = new UpdateEvent(
                sequence.incrementAndGet(), source, raw.strip(), Instant.now());
        String json = toJson(event);

        for (Map.Entry<String, SseEmitter> entry : emitters.entrySet()) {
            try {
                entry.getValue().send(SseEmitter.event()
                        .id(Long.toString(event.id()))
                        .name("update")
                        .data(json));
            } catch (IOException | IllegalStateException ex) {
                emitters.remove(entry.getKey());
            }
        }

        for (WebSocketSession session : sockets) {
            if (!session.isOpen()) {
                sockets.remove(session);
                continue;
            }
            try {
                // Việc gửi đồng thời trên cùng một session cần được serialize.
                synchronized (session) {
                    if (session.isOpen()) {
                        session.sendMessage(new TextMessage(json));
                    }
                }
            } catch (IOException | IllegalStateException ex) {
                sockets.remove(session);
            }
        }

        return event;
    }

    @Scheduled(fixedDelay = 20_000)
    public void heartbeat() {
        for (Map.Entry<String, SseEmitter> entry : emitters.entrySet()) {
            try {
                entry.getValue().send(
                        SseEmitter.event().comment("keepalive"));
            } catch (IOException | IllegalStateException ex) {
                emitters.remove(entry.getKey());
            }
        }
    }

    private String toJson(UpdateEvent event) {
        try {
            return mapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Không tạo được JSON", ex);
        }
    }
}
```

Cơ chế: `subscribeSse()` tạo `SseEmitter` giữ HTTP response mở; `onCompletion`, `onTimeout` và `onError` dọn emitter khỏi map. `publish(...)` tạo event rồi gửi cho cả SSE subscribers lẫn WebSocket sessions. `heartbeat()` phát comment định kỳ để hỗ trợ giữ kết nối qua idle timeout. `@Scheduled(fixedDelay=20_000)` không bảo đảm mọi proxy flush stream; phần proxy cần được cấu hình riêng.

Mã demo chủ động giới hạn message 200 ký tự và sử dụng Jackson để xuất JSON hợp lệ. JavaScript parse lại bằng `JSON.parse`. JSON được gửi như **văn bản** khi gọi `.data(json)` cho SSE hoặc `new TextMessage(json)` cho WebSocket. Nếu sau này chuyển sang gửi trực tiếp object và converter JSON, phải kiểm tra cách serialize để tránh double-encoding chuỗi JSON.

**Ba giới hạn đáng nhớ:**

- `AtomicLong` sinh ID khác nhau trong một JVM, không lưu bền, reset khi restart và không tự đảm bảo thứ tự broadcast tuyệt đối khi nhiều publisher đồng thời.
- Vòng lặp fan-out ở `publish` làm việc đồng bộ và có thể chậm khi nhiều client hoặc socket bị nghẽn. Với production, cần broker, worker bất đồng bộ, outbound buffer có giới hạn, timeout/slow-consumer policy; với Spring WebSocket có `ConcurrentWebSocketSessionDecorator` khi phù hợp.
- Map/set là state cục bộ của **một instance**. Khi load balancing qua nhiều instance, không tự động broadcast sang các client đang nối với instance khác.

## 5. Triển khai SSE bằng Spring MVC

Tệp `UpdatesController.java` cung cấp HTTP stream cho browser và POST endpoint để người dùng gửi một cập nhật khi đang ở chế độ SSE:

```java
package com.example.realtime;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
public class UpdatesController {
    private final LiveHub hub;

    public UpdatesController(LiveHub hub) {
        this.hub = hub;
    }

    @GetMapping(
            path = "/api/updates/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream() {
        return hub.subscribeSse();
    }

    @PostMapping(
            path = "/api/updates",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public LiveHub.UpdateEvent publish(@RequestBody UpdateRequest request) {
        try {
            return hub.publish(request.message(), "http");
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, ex.getMessage(), ex);
        }
    }

    public record UpdateRequest(String message) {}
}
```

Browser chỉ nhận SSE qua `GET /api/updates/stream`. Khi cần thực hiện hành động, browser gửi `POST /api/updates` như một HTTP request **khác**, rồi kết quả được broadcast xuống stream của tất cả subscribers. Vì vậy ứng dụng dùng SSE vẫn tương tác theo hai hướng *ở mức toàn hệ thống*; SSE stream vẫn chỉ truyền một chiều.

Đây là **demo localhost không có xác thực**. Không triển khai endpoint POST broadcast công khai ra Internet. Cần xác thực người gửi, kiểm tra quyền phát/nhận sự kiện theo người dùng/tenant, giới hạn tốc độ, CSRF khi dùng cookie-based session, lọc payload nhạy cảm và giới hạn số kết nối.

## 6. Triển khai raw WebSocket handler

Tệp `UpdateSocketHandler.java` xử lý text từ browser. Khi nhận text hợp lệ, nó gọi cùng `hub.publish` nhưng với nguồn `websocket`:

```java
package com.example.realtime;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class UpdateSocketHandler extends TextWebSocketHandler {
    private final LiveHub hub;

    public UpdateSocketHandler(LiveHub hub) {
        this.hub = hub;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        hub.addSocket(session);
    }

    @Override
    protected void handleTextMessage(
            WebSocketSession session, TextMessage message) throws Exception {
        try {
            hub.publish(message.getPayload(), "websocket");
        } catch (IllegalArgumentException ex) {
            session.close(CloseStatus.BAD_DATA);
        }
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session, CloseStatus status) {
        hub.removeSocket(session);
    }

    @Override
    public void handleTransportError(
            WebSocketSession session, Throwable exception)
            throws Exception {
        hub.removeSocket(session);
        if (session.isOpen()) {
            session.close();
        }
    }
}
```

`afterConnectionEstablished` ghi session vào tập đang hoạt động; `afterConnectionClosed`/`handleTransportError` dọn khi kết nối kết thúc. Việc đóng socket với `CloseStatus.BAD_DATA` cho biết dữ liệu client không hợp lệ. Đoạn này chỉ hỗ trợ text frame; nếu bài toán cần binary hoặc protocol phức tạp, phải thiết kế handler tương ứng.

Tệp `WebSocketConfig.java`:

```java
package com.example.realtime;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {
    private final UpdateSocketHandler handler;

    public WebSocketConfig(UpdateSocketHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(
            WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/updates");
    }
}
```

Client dùng `ws://localhost:8080/ws/updates` khi chạy HTTP local; website HTTPS phải dùng `wss://`. Spring kiểm tra Origin của WebSocket handshake theo cấu hình; đừng vô tư thêm `setAllowedOrigins("*")`. Origin chỉ là một kiểm soát phía browser, không thay thế authentication hoặc authorization cho mỗi hành động socket.

Đây là raw handler. Nếu cần nhiều phòng chat, subscription, `@MessageMapping` và `SimpMessagingTemplate`, hãy xây cấu hình STOMP qua `@EnableWebSocketMessageBroker`. STOMP là **protocol ứng dụng chạy trên WebSocket**, nên client STOMP không thể dùng nguyên URL raw handler mà tự nhiên có các destination `/topic/...`.

## 7. Giao diện thử hai cách

Tạo `src/main/resources/static/index.html`. Spring Boot phục vụ tệp này tại `http://localhost:8080/` trong cấu hình web mặc định:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Spring Realtime: SSE và WebSocket</title>
</head>
<body>
  <h1>Cập nhật thời gian thực</h1>
  <button id="open-sse">Dùng SSE</button>
  <button id="open-ws">Dùng WebSocket</button>
  <button id="stop">Ngắt kết nối</button>
  <p id="status">Chưa kết nối</p>

  <label for="input">Thông điệp:</label>
  <input id="input" maxlength="200" value="Cập nhật mới">
  <button id="publish">Phát cập nhật</button>
  <ol id="updates"></ol>

  <script>
    let sse = null;
    let ws = null;
    let mode = null;
    const status = document.getElementById("status");
    const updates = document.getElementById("updates");

    function write(text) {
      const li = document.createElement("li");
      li.textContent = text;
      updates.prepend(li);
    }

    function showEvent(json) {
      const event = JSON.parse(json);
      write("#" + event.id + " [" + event.source + "] " + event.message);
    }

    function disconnect() {
      if (sse !== null) {
        sse.close();
        sse = null;
      }
      if (ws !== null) {
        ws.close();
        ws = null;
      }
      mode = null;
      status.textContent = "Chưa kết nối";
    }

    document.getElementById("open-sse").onclick = () => {
      disconnect();
      mode = "sse";
      sse = new EventSource("/api/updates/stream");
      status.textContent = "SSE đang kết nối";
      sse.addEventListener("ready", () => {
        status.textContent = "SSE sẵn sàng";
      });
      sse.addEventListener("update", e => showEvent(e.data));
      sse.onerror = () => {
        status.textContent = "SSE gián đoạn, browser sẽ thử nối lại";
      };
    };

    document.getElementById("open-ws").onclick = () => {
      disconnect();
      mode = "ws";
      const scheme = location.protocol === "https:" ? "wss:" : "ws:";
      ws = new WebSocket(scheme + "//" + location.host + "/ws/updates");
      status.textContent = "WebSocket đang kết nối";
      ws.onopen = () => status.textContent = "WebSocket sẵn sàng";
      ws.onmessage = e => showEvent(e.data);
      ws.onclose = () => {
        status.textContent = "WebSocket đã đóng, hãy chọn kết nối lại";
      };
      ws.onerror = () => status.textContent = "WebSocket gặp lỗi";
    };

    document.getElementById("stop").onclick = disconnect;

    document.getElementById("publish").onclick = async () => {
      const message = document.getElementById("input").value.trim();
      if (!message || message.length > 200) {
        write("Thông điệp phải chứa 1..200 ký tự");
        return;
      }

      if (mode === "ws") {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          write("WebSocket chưa sẵn sàng");
          return;
        }
        ws.send(message);
      } else if (mode === "sse") {
        try {
          const response = await fetch("/api/updates", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({message})
          });
          if (!response.ok) {
            write("POST lỗi HTTP " + response.status);
          }
        } catch (error) {
          write("Không gửi được POST");
        }
      } else {
        write("Hãy chọn SSE hoặc WebSocket");
      }
    };
  </script>
</body>
</html>
```

**So sánh quan sát được:** khi chọn SSE, JavaScript tạo `EventSource`, nhưng nút phát cập nhật thực hiện `fetch(POST)`. Khi chọn WebSocket, cùng nút gọi `ws.send(message)` ngay trên socket đã mở. Cả hai có thể nhận sự kiện của nhau vì server phát đến cùng một `LiveHub`.

HTML dùng `textContent` để không diễn giải message thành HTML/script. Ứng dụng thật vẫn phải kiểm tra quyền đọc/ghi từng channel và có cơ chế bảo vệ khỏi spam, payload độc hại, thông tin nhạy cảm.

## 8. Chạy thử và kiểm tra bằng trình duyệt/curl

Từ project đã cấu hình Boot:

```bash
./gradlew bootRun
```

Windows PowerShell: `.\gradlew.bat bootRun`. Mở `http://localhost:8080/` ở hai tab. Tab A chọn SSE, tab B chọn WebSocket. Từ tab A gửi “Có đơn mới”, hai tab sẽ nhận sự kiện có `source=http`. Từ tab B gửi “Gửi qua WebSocket”, hai tab sẽ nhận sự kiện có `source=websocket`. Đây là bằng chứng cả hai client đều nhận cùng nguồn phát **trong một JVM**.

Mở terminal Bash A để xem SSE thô:

```bash
curl -N -H "Accept: text/event-stream" \
  http://localhost:8080/api/updates/stream
```

`curl -N` tắt buffer đầu ra của curl, cho thấy sự kiện ngay khi server flush. Từ terminal B phát cập nhật:

```bash
curl -i -X POST http://localhost:8080/api/updates \
  -H "Content-Type: application/json" \
  -d '{"message":"Có đơn mới"}'
```

Trên PowerShell có thể dùng lệnh trên **một dòng**:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/updates" -ContentType "application/json" -Body '{"message":"Có đơn mới"}'
```

Bên nhận SSE dự kiến thấy cấu trúc:

```text
id: 1
event: update
data: {"id":1,"source":"http","message":"Có đơn mới","time":"..."}

```

`id` và `time` thực tế thay đổi theo thứ tự phát và thời gian máy chủ. Đây là ví dụ dạng dữ liệu, **không phải stdout được ghi lại sau khi chạy code**. HTTP response `GET /api/updates/stream` vẫn mở và có thể nhận nhiều sự kiện.

Để kiểm tra handshake WebSocket, mở Developer Tools → Network → WS và chọn **Dùng WebSocket**. Handshake thành công thông thường có status `101 Switching Protocols`; danh sách Frames hiển thị text client gửi và JSON server phát. Nếu URL `ws://` được gọi từ website HTTPS, trình duyệt có thể chặn mixed content; dùng `wss://` và reverse proxy TLS phù hợp.

### Bốn thí nghiệm phân biệt hai giao thức

1. **Hai tab:** dùng SSE ở A, WebSocket ở B, gửi từ từng bên; cùng nhìn thấy update để xác nhận fan-out.
2. **Mất mạng:** ngắt kết nối tạm. `EventSource` có thể tự thử lại theo `retry`; WebSocket trong demo chỉ báo đã đóng và đợi người dùng chọn lại. Ứng dụng WS thực cần backoff/jitter và tái xác thực khi reconnect.
3. **Khởi động lại server:** các ID trong `AtomicLong` reset; sự kiện phát lúc browser offline không được replay. Đây là giới hạn demo, không phải lỗi riêng của SSE.
4. **Thử dữ liệu sai:** POST message chỉ có dấu cách phải trả 400; WebSocket gửi text rỗng có thể bị đóng với close code invalid data. Cả hai đường vào đều kiểm tra độ dài 1..200 ký tự.

## 9. Kiểm thử Spring MVC và ranh giới kiểm thử

Tệp `src/test/java/com/example/realtime/UpdatesControllerTest.java`:

```java
package com.example.realtime;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UpdatesControllerTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publishesValidPayload() throws Exception {
        mvc.perform(post("/api/updates")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"Hello\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello"))
                .andExpect(jsonPath("$.source").value("http"));
    }

    @Test
    void rejectsBlankPayload() throws Exception {
        mvc.perform(post("/api/updates")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"  \"}"))
                .andExpect(status().isBadRequest());
    }
}
```

Chạy:

```bash
./gradlew test --tests com.example.realtime.UpdatesControllerTest
```

Kiểm thử trên nạp context và dùng `MockMvc` để kiểm tra HTTP controller. Nó **không thực hiện TCP streaming hay WebSocket handshake**, nên chưa đủ chứng minh browser thực sự nhận cập nhật. Kiểm thử tích hợp cho transport cần chạy embedded server trên cổng thực, dùng SSE client đọc nhiều chunk và WebSocket client thực sự connect, gửi/nhận/đóng kết nối. Kiểm tra hai subscribers, timeout, disconnect, lỗi, và chậm mạng với timeout hữu hạn; không dùng sleep tùy tiện làm bằng chứng nhận dữ liệu.

## 10. Các vấn đề vận hành cần thiết trước production

### 10.1. Idle timeout, heartbeat, proxy buffering

SSE là HTTP streaming. Reverse proxy có thể giữ dữ liệu trong buffer và chỉ gửi cho browser sau khi đủ kích thước, khiến event đến muộn; cấu hình không buffer stream, timeout đủ lớn và flush thường xuyên. Heartbeat comment `: keepalive` giúp hạn chế kết nối bị coi là idle, nhưng proxy nào cũng có cấu hình riêng. WebSocket cần proxy hỗ trợ handshake Upgrade, connection timeout, ping/pong và termination có kiểm soát. Cần đo trên đúng proxy/load balancer đang dùng thay vì suy từ kết quả chạy localhost.

Browser HTTP/1.1 có thể giới hạn số connection tới cùng origin; nhiều tab mở SSE dùng chung connection budget. HTTP/2 multiplex giúp cải thiện nhưng còn ràng buộc max concurrent streams. WebSocket cũng giữ connection/resource mỗi client, nên cả hai đều có chi phí khi số người dùng lớn.

### 10.2. Security và phân quyền

- Với SSE, native `EventSource` không cho đặt tùy ý header `Authorization`. Cookie-based session có thể dùng; cross-origin cần CORS/credentials đúng cách. Tránh token nhạy cảm trong URL query nếu có giải pháp khác.
- WebSocket bắt đầu bằng HTTP handshake. Kiểm tra origin, principal và quyền vào channel, rồi **tiếp tục kiểm tra quyền từng message** trong handler/protocol. Origin check không thay thế authentication; handshake thành công không có nghĩa mọi message về sau hợp lệ.
- Endpoint POST dùng cookie/session thường cần CSRF token nếu Spring Security bật; thiếu token có thể dẫn tới HTTP 403. Kèm rate limit, giới hạn payload và quyền phát sự kiện.
- Demo broadcast tới tất cả sessions. Hệ thống có nhiều user/tenant phải chia audience, lọc event theo quyền và dọn quyền truy cập khi session không còn hợp lệ.

### 10.3. Reconnect khác replay

Khi stream đứt, client có thể nối lại, nhưng các event xảy ra khi offline không tự xuất hiện. Muốn phục hồi, lưu sự kiện vào event store/broker có offset bền vững; SSE server đọc `Last-Event-ID`, WebSocket app gửi last-seen sequence khi reconnect, rồi phát lại phần thiếu. Client phải xử lý duplicate bằng event ID, vì reconnect/retry có thể khiến một sự kiện được nhận hơn một lần. Chọn delivery semantics và idempotency theo yêu cầu: UI hiển thị trạng thái mới nhất khác với lệnh thanh toán không được xử lý trùng.

### 10.4. Scale, thứ tự và slow consumers

```text
Producer → Event broker / durable log
              ├→ Instance A → SSE + WS clients A
              └→ Instance B → SSE + WS clients B
```

Dùng `ConcurrentHashMap` trong một JVM có nghĩa publisher ở instance A không tự biết clients ở instance B. Sticky session chỉ giúp client tiếp tục đến một node trong lúc còn kết nối, **không giải quyết broadcast đa node**. Dùng Redis pub/sub, Redis Streams, Kafka, RabbitMQ hoặc broker khác tùy nhu cầu fan-out, persistence, ordering, latency và chi phí.

Event ID tăng dần ở một instance không chứng minh thứ tự gửi tuyệt đối khi nhiều threads publish song song. Với dữ liệu quan trọng, định nghĩa ordering theo từng stream/partition và dùng offset/version rõ ràng. Với slow consumers, đặt queue/buffer **có giới hạn**, chính sách drop/terminate/replay, đo độ trễ và memory. Không để một client chậm làm tắc cả luồng phát.

### 10.5. Quan sát hoạt động và dọn tài nguyên

Đo số connection SSE/WS đang mở, thời gian kết nối, reconnect count, tỷ lệ lỗi gửi, fan-out latency, message backlog, slow-client disconnect và số bytes/message. Dọn `SseEmitter` khi complete/timeout/error; dọn `WebSocketSession` khi close/error. Client rời trang nên gọi `EventSource.close()` hoặc `WebSocket.close()`. Với Spring MVC async SSE, thread Servlet có thể được trả lại pool trong lúc connection còn mở, nhưng socket và các tài nguyên khác vẫn tồn tại; số lượng connection lớn phải được capacity plan.

## 11. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân hay gặp | Cách xác minh |
| --- | --- | --- |
| `EventSource` kết nối nhưng JS không nhận event | JS dùng `onmessage` trong khi server phát named `event: update` | Dùng `addEventListener("update", ...)` |
| SSE chỉ hiện dữ liệu sau một lúc | Proxy buffering hoặc không flush | Thử `curl -N` trực tiếp với instance và qua proxy |
| Reconnect rồi mất cập nhật | Server không replay từ event ID | Dùng persistence/offset, tra `Last-Event-ID` |
| WebSocket không handshake | Sai URL, `ws/wss`, Origin, auth, reverse proxy Upgrade | Kiểm tra status và headers ở Network → WS |
| Socket tự đóng | Timeout, payload không hợp lệ, server restart | Kiểm tra close code, server logs, heartbeat |
| POST trả 403 | CSRF/authorization | Gửi CSRF token và xác thực đúng chính sách |
| Một node nhận message, node khác không | Lưu subscribers cục bộ | Kiểm tra routing và broker fan-out |
| Memory tăng theo thời gian | Emitter/socket không cleanup, queue quá lớn | Callback close/error, metrics connections/buffers |
| Trùng/sai thứ tự | Retry và nhiều producer | Event ID/version, ordering và dedup |
| Người dùng thấy dữ liệu người khác | Broadcast không lọc audience | Kiểm tra quyền theo user, tenant, topic |

## 12. Checklist kết thúc bài thực hành

- **SSE:** `GET /api/updates/stream` trả `text/event-stream`, browser nhận `ready` và các event `update`; SSE nhận thông điệp server phát qua POST hoặc WebSocket.
- **WebSocket:** handshake HTTP `101`, client gửi raw text message, nhận JSON text frame và broadcast tới client khác.
- **Độ bền:** reconnect SSE và WebSocket có hành vi khác nhau; demo không replay nên có thể mất sự kiện khi offline.
- **Chọn công nghệ:** SSE cho fan-out một chiều, WebSocket cho nhu cầu hai chiều, STOMP/broker cho topic/subscription phức tạp, polling cho tần suất đổi thấp.
- **Production:** có kế hoạch cho auth, Origin/CSRF, proxy timeout, heartbeat, persistence, scale đa instance, slow consumers và observability.

Một bài thực hành hoàn thành khi có thể **chứng minh bằng browser/Network tab và curl** rằng hai đường truyền hoạt động, giải thích được vì sao mỗi đường phù hợp một nhu cầu và nhận diện những bảo đảm còn phải bổ sung ở cấp ứng dụng.

### Tài liệu tham khảo

- Spring Framework 6.1 — Async MVC và SSE: https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-ann-async.html
- Spring Framework 6.1 — WebSocket Server: https://docs.spring.io/spring-framework/reference/6.1/web/websocket/server.html
- Spring Framework 6.1 — STOMP over WebSocket: https://docs.spring.io/spring-framework/reference/6.1/web/websocket/stomp.html
- Spring Framework API — SseEmitter: https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html
- WHATWG — Server-sent events: https://html.spec.whatwg.org/multipage/server-sent-events.html
- RFC 6455 — WebSocket Protocol: https://www.rfc-editor.org/rfc/rfc6455

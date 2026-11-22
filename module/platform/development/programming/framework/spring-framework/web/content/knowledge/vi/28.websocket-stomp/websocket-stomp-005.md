# WebSocket và STOMP: Giới hạn message, gửi đồng thời, timeout và ngắt kết nối

## 1. Đặt đúng phạm vi: frame, STOMP message và session

Trong Spring Framework, WebSocket tạo một kết nối hai chiều tồn tại lâu giữa client và server; STOMP là giao thức nhắn tin dạng frame chạy bên trên kết nối đó. Ứng dụng Spring dùng `@EnableWebSocketMessageBroker` thường có các chặng:

```text
Trình duyệt/ứng dụng STOMP
    │ HTTP Upgrade (handshake) → WebSocket session
    │ STOMP CONNECT / SUBSCRIBE / SEND / DISCONNECT
    ▼
WebSocket engine (Tomcat/Jetty/...)
    │ xử lý frame WebSocket, giới hạn frame/buffer, idle timeout
    ▼
STOMP sub-protocol handler
    │ ghép/giải mã STOMP message, kiểm tra messageSizeLimit
    ▼
clientInboundChannel → @MessageMapping / broker
    │
    ▼
clientOutboundChannel → phiên WebSocket
    │    tuần tự hóa send; buffer dữ liệu chờ khi client chậm
    ▼
Trình duyệt nhận MESSAGE hoặc socket đóng
```

Phân biệt ba khái niệm:

- **WebSocket frame/message:** đơn vị của giao thức WebSocket, do HTTP upgrade endpoint và thư viện WebSocket bên dưới xử lý. Giới hạn kích thước tùy container và cấu hình engine.
- **STOMP frame/message:** lệnh `CONNECT`, `SEND`, `SUBSCRIBE`, `MESSAGE`, `ERROR`, `DISCONNECT` kèm headers và body. Một STOMP message lớn có thể đến qua nhiều WebSocket messages/chunks, được bộ giải mã Spring ghép lại trước khi chuyển vào ứng dụng.
- **WebSocket/STOMP session:** kết nối có trạng thái đăng ký subscription, heartbeat, thông tin người dùng và hàng đệm outbound. Giới hạn dành cho một session khác với giới hạn tổng số phiên toàn hệ thống.

Bài áp dụng cho **Spring Framework 6.1.x / Spring Boot 3.3.x với Java 17+** dùng Spring WebSocket + STOMP trên Servlet stack. Các ví dụ cấu hình giới hạn là số **dùng để học**; cấu hình thật phải đo tải và cân nhắc giới hạn client, proxy và broker ngoài (nếu có).

## 2. Giới hạn kích thước message: inbound STOMP khác buffer container

Trong `WebSocketMessageBrokerConfigurer`, dùng:

```java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
    registration.setMessageSizeLimit(64 * 1024); // bytes
}
```

`setMessageSizeLimit` giới hạn **STOMP message nhận từ client**, kể cả khi nó được gom từ nhiều WebSocket messages. Mặc định của Spring STOMP transport là **64 KiB** theo Javadoc Spring 6.1. Con số tính theo **byte**, không phải số ký tự Unicode. Trên wire, STOMP headers và body cũng tiêu thụ không gian; một JSON payload có kích thước sát trần vẫn có thể vượt giới hạn sau khi tính thêm overhead.

Luồng với một message quá lớn:

```text
Client gửi STOMP SEND (kèm body lớn)
 → WebSocket engine tiếp nhận các phần
 → STOMP decoder ghép nội dung
 → vượt messageSizeLimit
 → lỗi tại tầng protocol/transport, có thể phát ERROR/đóng session
 → @MessageMapping không được gọi thành công
```

Không giả định mọi container và mọi loại lỗi đều trả cùng **mã đóng** hay cùng chuỗi `ERROR`. Cách phản ánh ở browser/log phụ thuộc phần bị từ chối (WebSocket engine hay STOMP decoder), phiên bản và trạng thái kết nối.

**Giới hạn khác ở cấp WebSocket engine** (ví dụ cấu hình Jakarta WebSocket/Tomcat):

```java
@Bean
ServletServerContainerFactoryBean webSocketContainer() {
    ServletServerContainerFactoryBean factory =
        new ServletServerContainerFactoryBean();
    factory.setMaxTextMessageBufferSize(32 * 1024);
    factory.setMaxBinaryMessageBufferSize(32 * 1024);
    factory.setMaxSessionIdleTimeout(120_000L);
    return factory;
}
```

Cần imports `org.springframework.context.annotation.Bean` và `org.springframework.web.socket.server.standard.ServletServerContainerFactoryBean`. Đây là **mã cấu hình minh họa**, không phải lựa chọn bắt buộc cho mọi ứng dụng. Nó cấu hình khả năng nhận WebSocket text/binary ở server container và idle timeout (ms), trong khi `setMessageSizeLimit` giới hạn message STOMP sau khi được ghép. Với STOMP, Spring có thể điều chỉnh cỡ đệm WebSocket bên dưới để đủ nhận các chunk mà STOMP client gửi; đừng coi hai con số là cùng một giới hạn.

Có thể đặt limit nhỏ để bảo vệ tài nguyên, nhưng phải xét trường hợp legitimate: JSON có trường Unicode dài, message có headers lớn, snapshot gửi ban đầu, v.v. Với file hoặc đối tượng vài MB, tốt hơn là **upload qua HTTP/object storage**, rồi thông báo sự kiện nhỏ qua STOMP kèm URL/id có kiểm soát. Không dùng tăng `setMessageSizeLimit` vô hạn làm cơ chế thay thế quy trình upload.

**Inbound khác outbound:** `setMessageSizeLimit` không phải trần cho mọi `MESSAGE` server đẩy ra. Khi muốn hạn chế dữ liệu outbound, phải chủ động kiểm soát payload tại nghiệp vụ, broker và dung lượng buffer gửi.

## 3. Gửi đồng thời: mỗi WebSocket session cần tuần tự hóa việc send

Một WebSocket session không nên có nhiều thread đồng thời gọi `sendMessage` trên cùng kết nối. Trong mô hình STOMP broker của Spring, gửi tới client đi qua `clientOutboundChannel` (có thể có nhiều worker threads), nhưng Spring đảm bảo ở thời điểm ghi tới **một WebSocket session** chỉ có một luồng gửi.

Vấn đề thực tế xảy ra khi một client nhận chậm hơn tốc độ server phát:

```text
Server phát các MESSAGE #1, #2, #3, #4...
                   │
                   ▼
clientOutboundChannel (đa luồng)
                   │
                   ▼
Session A: send #1 đang chậm
           #2, #3, #4 phải đợi trong buffer
                   │
                   ├─ buffer tiếp tục tăng
                   └─ kiểm tra sendTimeLimit / sendBufferSizeLimit
                       nếu vượt: phiên có thể bị kết thúc
```

Spring dùng cơ chế tương tự `ConcurrentWebSocketSessionDecorator`: wrapper serialize việc gửi trên một session; các send phát sinh khi thread khác đang ghi sẽ được xếp hàng. Vì vậy, *thread-safe send* **không đồng nghĩa với miễn phí về RAM hoặc bảo đảm người nhận theo kịp**.

Cấu hình giới hạn outbound:

```java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
    registration
        .setMessageSizeLimit(64 * 1024)       // inbound STOMP, bytes
        .setSendBufferSizeLimit(512 * 1024)   // outbound buffer / session, bytes
        .setSendTimeLimit(15_000);            // thời gian gửi, milliseconds
}
```

Cơ chế:

- `setSendBufferSizeLimit(512 * 1024)` đặt giới hạn dữ liệu **đang chờ gửi** cho mỗi session khi send bị nghẽn. Đây không phải queue vô hạn và không phải tổng buffer của mọi session.
- `setSendTimeLimit(15_000)` đặt ngưỡng thời gian cho một hoạt động send kéo dài. Nó **không phải** deadline tổng từ lúc publish cho đến khi client ứng dụng xử lý xong.
- Khi một send còn giữ quyền ghi và các send khác đến, wrapper kiểm tra thời gian đang gửi và dung lượng chờ; nếu vượt, có thể ném `SessionLimitExceededException` và đóng phiên với trạng thái không đáng tin cậy.

**Cảnh báo kỹ thuật quan trọng:** send-time limit của cơ chế này không phải timer cứng cắt ngang một lệnh blocking send đúng từng millisecond. Trong triển khai decorator, giới hạn thường được kiểm tra khi có thêm lần gửi hoặc lúc close; một send duy nhất bị chặn lâu có thể chưa được phát hiện ngay tại mốc giới hạn. Cần kết hợp timeout của container/network, giám sát và chính sách backpressure phù hợp. Đừng coi tăng `sendTimeLimit` là giải pháp cho một browser ngừng đọc.

### Khi tự viết WebSocketHandler thuần

Nếu **không** dùng STOMP broker config mà tự gửi trực tiếp từ nhiều thread, bọc `WebSocketSession` bằng `ConcurrentWebSocketSessionDecorator` hoặc thực hiện cơ chế hàng đợi tuần tự tương đương:

```java
WebSocketSession safe = new ConcurrentWebSocketSessionDecorator(
    originalSession, 15_000, 512 * 1024
);

// Các luồng trong ứng dụng chỉ gọi safe.sendMessage(message);
// không gọi lẫn lộn originalSession.sendMessage(message).
```

Đây là đoạn minh họa, cần import `WebSocketSession` và `org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator`. **Không cần bọc thủ công lần nữa** các session đã được Spring STOMP stack quản lý; tăng tầng wrapper sai chỗ có thể làm rối lifecycle và metrics.

### Gửi đồng thời khác với thứ tự nhận

Sự kiện có thể được publish qua `clientOutboundChannel` bằng nhiều thread nên thứ tự **client thấy** có thể khác thứ tự ứng dụng publish. Nếu thứ tự cho từng session là yêu cầu, bật:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setApplicationDestinationPrefixes("/app");
    registry.setPreservePublishOrder(true);
}
```

Từ Spring Framework 6.1 còn có thể bảo toàn **thứ tự xử lý inbound trong một client session**:

```java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws");
    registry.setPreserveReceiveOrder(true);
}
```

Đây là bảo đảm thứ tự **trong session**, không phải global ordering giữa mọi client, và có overhead. Nó không biến STOMP thành giao thức exactly-once hay giải quyết thứ tự do nhiều publisher ngoài Spring tự ghi vào broker.

## 4. Timeout và heartbeat: có nhiều đồng hồ riêng

“WebSocket timeout” có thể nói về hoàn toàn khác nhau:

| Timeout/giám sát | Mục đích | Nơi thường cấu hình |
| --- | --- | --- |
| HTTP handshake/upgrade | Thiết lập kết nối HTTP → WebSocket | HTTP server/proxy/client; không dùng `sendTimeLimit` |
| WebSocket idle timeout | Socket không có traffic trong một thời gian | WebSocket container, ví dụ `setMaxSessionIdleTimeout` |
| STOMP heartbeats | Phát hiện một phía không gửi/nhận traffic như đã thương lượng | STOMP `heart-beat`, TaskScheduler, broker |
| Outbound send time | Một lần gửi về client mất quá lâu | `setSendTimeLimit` |
| Client reconnect delay | Thời gian chờ trước khi thử kết nối lại | Client STOMP/browser hoặc thư viện reconnect |
| Business acknowledgement/receipt | Bên kia đã xử lý/persist nghiệp vụ chưa? | `receipt` của STOMP hoặc application-level ACK/event, tùy contract |

**STOMP heartbeats** dùng cặp số milisecond `heart-beat:cx,cy` trong `CONNECT` và `heart-beat:sx,sy` trong `CONNECTED` để thương lượng nhịp tối thiểu: một bên cho biết tần suất có thể gửi và kỳ vọng nhận. STOMP heartbeat frame có thể là chỉ một byte xuống dòng; khi có các STOMP frame khác, traffic đó cũng có thể đáp ứng nhịp liveness. Chúng không bảo đảm endpoint đã xử lý thành công message nghiệp vụ.

Với simple broker, heartbeat cần `TaskScheduler` được cấu hình:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableSimpleBroker("/topic")
        .setTaskScheduler(heartbeatTaskScheduler)
        .setHeartbeatValue(new long[] {10_000, 10_000});
    registry.setApplicationDestinationPrefixes("/app");
}
```

`heartbeatTaskScheduler` là `TaskScheduler` đã tạo/inject vào cấu hình (ví dụ hoàn chỉnh ở phần 7). Hai số là chu kỳ đề xuất gửi/nhận theo cơ chế Spring broker, **không phải một timeout HTTP request**. Với hệ thống nhiều proxy/load balancer, idle timeout trung gian phải dài hơn nhịp heartbeat có đủ khoảng dư cho jitter/network. Nếu đường truyền proxy cắt socket dù vẫn có heartbeat, kiểm tra chính sách WebSocket Upgrade, TCP idle và cân bằng tải.

**SockJS:** nếu bật SockJS fallback, nó còn có cơ chế heartbeat riêng; khi đã thương lượng STOMP heartbeat, heartbeat SockJS thường được tắt để tránh trùng. Các transport SockJS HTTP streaming/polling có timeout và tài nguyên khác native WebSocket, không thể bê nguyên mọi giả định WebSocket sang.

**Broker relay:** khi Spring dùng external broker (RabbitMQ/ActiveMQ...), heartbeat của kết nối broker relay và heartbeat WebSocket client là hai luồng riêng. Relay có thể tái kết nối broker ở mức hệ thống, **không tự kết nối lại WebSocket client** bị rớt.

## 5. Ngắt kết nối: chủ động, bất thường, đóng do giới hạn

Một session có thể kết thúc vì:

1. **Client chủ động:** gửi STOMP `DISCONNECT` rồi đóng WebSocket (để graceful hơn có thể đợi STOMP `RECEIPT` nếu broker hỗ trợ và client yêu cầu). Tab bị đóng có thể không kịp gửi `DISCONNECT`.
2. **Network/proxy:** mất Wi-Fi, NAT/LB đóng idle connection, client ngủ, mất điện. Server không nhất thiết biết ngay; heartbeat/timeout giúp phát hiện sau một khoảng.
3. **Vượt message size / buffer / send time:** Spring hoặc container từ chối dữ liệu hoặc đóng session.
4. **Protocol/auth/server:** frame STOMP hỏng, subscription không hợp lệ, handshake bị từ chối, lỗi server hoặc restart.
5. **Broker bên ngoài không sẵn sàng:** có thể ảnh hưởng publish/subscription; tùy cấu hình phải xử lý broker availability và reconnection riêng.

Các sự kiện Spring đáng biết:

- `SessionConnectEvent`: server nhận frame STOMP CONNECT, **chưa đủ để khẳng định đã CONNECTED**.
- `SessionConnectedEvent`: broker đã gửi frame CONNECTED; có thể coi STOMP session đã được thiết lập.
- `SessionSubscribeEvent` / `SessionUnsubscribeEvent`: theo dõi thay đổi subscription.
- `SessionDisconnectEvent`: phiên STOMP kết thúc, dù do client hoặc WebSocket transport. **Một session có thể phát sự kiện này hơn một lần**, vì vậy cleanup phải idempotent.

Cách cleanup an toàn thường là thao tác có tính idempotent:

```java
@EventListener
public void onDisconnect(SessionDisconnectEvent event) {
    String sessionId = event.getSessionId();
    SessionState removed = activeSessions.remove(sessionId);
    if (removed != null) {
        releaseResources(removed);
    }
}
```

Đây là **pseudocode Java**: `SessionState`, `activeSessions` và `releaseResources` là thành phần ứng dụng phải định nghĩa. `ConcurrentHashMap.remove` trả `null` ở lần cleanup thứ hai, nên không phát side effect trùng lặp. Nếu cleanup còn liên quan database/ngoại hệ thống, dùng transaction/idempotency key phù hợp. Không giữ một `Set` chứa mọi session ID đã từng disconnect mãi mãi trong heap.

**Khôi phục sau reconnect:** WebSocket/STOMP connection mới thường có **session ID mới**. Client phải tự reconnect, gửi CONNECT và SUBSCRIBE lại; trạng thái subscription in-memory của session cũ không tự được tái tạo. Với chat/notification quan trọng, sử dụng offset/event ID để đồng bộ các message có thể bỏ lỡ, hoặc persistent broker và ACK/transaction theo thiết kế. STOMP heartbeat hay WebSocket TCP connection chỉ xác nhận liveness, không cung cấp exactly-once delivery.

## 6. Chọn số giới hạn theo tải và quan sát hiện tượng

Giả sử một notification trung bình 2 KiB và outbound buffer mỗi session là 64 KiB. Nếu một client bị chậm và có nhiều tin đến, khoảng vài chục message chưa gửi đã có thể áp sát giới hạn (con số cụ thể tùy kích thước frame, serialization, overhead). Với 10.000 client cùng chậm, chỉ riêng buffer ở mức tối đa giả định 64 KiB/session đã tương ứng **khoảng 625 MiB** dữ liệu queue, chưa tính session object, broker, network buffer, TLS và heap overhead. Vì vậy, không tăng buffer để “hết disconnect” trước khi xác định vì sao client chậm.

Khi tải tăng, cân nhắc:

- **Payload:** giảm kích thước message, chỉ gửi các trường cần thiết, tránh gửi snapshot lớn nhiều lần.
- **Outbound:** đồng nhất tài nguyên `clientOutboundChannel` với số slow clients, giảm publish rate, coalesce/throttle các cập nhật chỉ cần giá trị mới nhất.
- **Inbound:** giới hạn số message mỗi user/connection ở gateway hoặc ứng dụng, xác thực quyền destination, kiểm tra schema, giữ `setMessageSizeLimit` vừa đủ hợp đồng.
- **Memory:** số session × buffer mỗi session + inbound decode + broker queue + object/heap trực tiếp; monitor heap và direct memory.
- **Liveness:** heartbeat và idle timeout phối hợp giữa trình duyệt, broker, proxy; đo false disconnect khi network chập chờn.
- **Order:** nếu cần đúng thứ tự trong một session, bật preserve order và kiểm thử hiệu năng; với các message từ nhiều producer, dùng sequence ID/ordering ở domain.
- **Scale:** Spring simple broker giữ subscription trong bộ nhớ của một instance; khi nhiều instance cần routing liên node, cân nhắc broker relay hoặc kiến trúc message broker phù hợp, và load balancer/session routing đúng.

Không dựa vào một “giá trị chuẩn” cho mọi ứng dụng. SLO thực tế bao gồm số kết nối, peak fan-out, message/s, p95/p99 send latency, client di động, tỉ lệ reconnect và điều kiện mạng.

## 7. Ví dụ chạy được: Spring Boot 3.3 + STOMP và WebSocket browser client

Ví dụ có WebSocket endpoint `/ws`, subscription `/topic/echo`, destination gửi `/app/echo`. Tùy chỉnh **1 KiB inbound STOMP**, **64 KiB outbound buffer**, **5 giây gửi**, bật bảo toàn thứ tự và heartbeat. Trang HTML sử dụng native `WebSocket` và **STOMP frame dạng chuỗi** để dễ thấy giao thức, không cần cài thư viện JavaScript STOMP.

Cấu trúc:

```text
stomp-limit-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/StompLimitDemo.java
    └── resources/static/index.html
```

**`settings.gradle`**

```groovy
rootProject.name = 'stomp-limit-demo'
```

**`build.gradle`** — JDK 17+, Gradle 8.x:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
}
```

**`src/main/java/demo/StompLimitDemo.java`**

```java
package demo;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Controller;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@SpringBootApplication
public class StompLimitDemo {
    public static void main(String[] args) {
        SpringApplication.run(StompLimitDemo.class, args);
    }
}

@Configuration
@EnableWebSocketMessageBroker
class SocketConfig implements WebSocketMessageBrokerConfigurer {
    @Autowired
    @Lazy
    @Qualifier("stompHeartbeatScheduler")
    private TaskScheduler heartbeatScheduler;

    @Bean("stompHeartbeatScheduler")
    ThreadPoolTaskScheduler stompHeartbeatScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-heartbeat-");
        return scheduler;
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
        registry.setPreserveReceiveOrder(true);
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic")
            .setTaskScheduler(heartbeatScheduler)
            .setHeartbeatValue(new long[] {10_000, 10_000});
        registry.setPreservePublishOrder(true);
    }

    @Override
    public void configureWebSocketTransport(WebSocketTransportRegistration reg) {
        reg.setMessageSizeLimit(1024)           // 1 KiB inbound STOMP
            .setSendBufferSizeLimit(64 * 1024)  // outbound / session
            .setSendTimeLimit(5_000);           // ms
    }
}

record EchoPayload(String text) {}

@Controller
class EchoController {
    @MessageMapping("/echo")
    @SendTo("/topic/echo")
    public EchoPayload echo(EchoPayload payload) {
        return new EchoPayload("echo: " + payload.text());
    }
}

@Component
class SessionEvents {
    private final ConcurrentMap<String, Boolean> live =
        new ConcurrentHashMap<>();

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        String sessionId = SimpMessageHeaderAccessor
            .wrap(event.getMessage()).getSessionId();
        if (sessionId != null) {
            live.put(sessionId, Boolean.TRUE);
        }
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        if (live.remove(event.getSessionId()) != null) {
            System.out.println("Closed STOMP session: " + event.getSessionId());
        }
    }
}
```

**`src/main/resources/static/index.html`**

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>STOMP connection limits</title>
</head>
<body>
  <h1>STOMP over WebSocket</h1>
  <button id="connect">Connect</button>
  <button id="small">Gửi message nhỏ</button>
  <button id="large">Gửi message vượt giới hạn</button>
  <button id="disconnect">Disconnect</button>
  <pre id="log"></pre>
  <script>
    let socket = null;
    let ready = false;

    const output = document.getElementById("log");
    function log(value) {
      output.textContent += value + "\n";
    }
    function sendFrame(command, headers, body = "") {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        log("Socket chưa mở");
        return;
      }
      const lines = Object.entries(headers)
        .map(([name, value]) => name + ":" + value)
        .join("\n");
      socket.send(command + "\n" + lines + "\n\n" + body + "\0");
    }

    document.getElementById("connect").onclick = () => {
      ready = false;
      socket = new WebSocket(
        "ws://" + location.host + "/ws", "v12.stomp"
      );
      socket.onopen = () => {
        log("WebSocket OPEN");
        sendFrame("CONNECT", {
          "accept-version": "1.2",
          "host": location.hostname,
          "heart-beat": "0,0"
        });
      };
      socket.onmessage = (event) => {
        const frame = event.data;
        if (frame.startsWith("CONNECTED")) {
          ready = true;
          log("STOMP CONNECTED");
          sendFrame("SUBSCRIBE", {
            id: "sub-1", destination: "/topic/echo"
          });
        } else if (frame.startsWith("MESSAGE")) {
          log("MESSAGE: " + frame.split("\n\n")[1].replace(/\0$/, ""));
        } else if (frame.startsWith("ERROR")) {
          log("STOMP ERROR: " + frame);
        }
      };
      socket.onclose = (e) => {
        ready = false;
        log("WebSocket CLOSED: code=" + e.code + ", reason=" + e.reason);
      };
      socket.onerror = () => log("WebSocket transport error");
    };

    function sendText(text) {
      if (!ready) {
        log("Chưa STOMP CONNECTED");
        return;
      }
      sendFrame("SEND", {
        destination: "/app/echo",
        "content-type": "application/json"
      }, JSON.stringify({text}));
    }
    document.getElementById("small").onclick = () => sendText("Xin chào");
    document.getElementById("large").onclick = () => sendText("x".repeat(2048));
    document.getElementById("disconnect").onclick = () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        sendFrame("DISCONNECT", {});
        socket.close(1000, "done");
      }
    };
  </script>
</body>
</html>
```

Trong dự án:

```bash
gradle bootRun
```

Sau khi Spring Boot khởi động, mở `http://localhost:8080/index.html` trong trình duyệt:

1. Bấm **Connect**: log sẽ có `WebSocket OPEN` và, khi broker xác nhận, `STOMP CONNECTED`. Client gửi `SUBSCRIBE` đến `/topic/echo`.
2. Bấm **Gửi message nhỏ**: nếu SUBSCRIBE đã được broker xử lý, trình duyệt nhận MESSAGE có body gần như `{"text":"echo: Xin chào"}` (đúng thứ tự JSON theo Jackson record). Trong trường hợp gửi ngay sau CONNECTED, chờ rất ngắn cho subscription được xử lý trước.
3. Bấm **Gửi message vượt giới hạn**: payload 2 KiB + STOMP headers vượt `setMessageSizeLimit(1024)`. Server phải từ chối message ở tầng STOMP; browser có thể thấy `ERROR`, đóng socket hoặc thông báo transport tùy handler/container. **Không khẳng định mã CLOSE hay chuỗi lỗi cố định.**
4. Bấm **Disconnect** khi kết nối đang mở: gửi `DISCONNECT` rồi đóng WebSocket; server phát event ngắt kết nối và cleanup. Muốn xác minh lặp sự kiện, có thể thử reconnect/đóng tab đột ngột; listener chỉ xử lý thành công một lần cho mỗi phiên đã kết nối.

**Kết quả có thể quan sát ổn định nhất:** request nhỏ tạo payload Echo; request quá lớn bị chặn; đóng kết nối giải phóng session. Log có ID và thứ tự bất đồng bộ, vì vậy không đưa một transcript stdout cố định giả tạo.

Ví dụ HTML cố ý dùng `heart-beat:0,0` để thuận tiện cho việc quan sát frame thủ công; vì vậy browser demo này **không thực hiện client-side liveness check**. Trong ứng dụng thật, dùng thư viện STOMP client hỗ trợ heartbeat, reconnect/backoff, auth token, subscription restore và handling receipt đầy đủ. Nếu trang triển khai trên HTTPS, WebSocket phải dùng `wss://`, không dùng `ws://` như localhost.

## 8. Chẩn đoán từng lỗi theo lớp

| Triệu chứng | Khả năng cao | Cần xem |
| --- | --- | --- |
| Client gửi nội dung lớn rồi socket đóng | Vượt STOMP `messageSizeLimit` hoặc giới hạn container | Kích thước bytes gồm headers, log decoder/close reason, text buffer container |
| Client chậm bị ngắt khi server broadcast nhiều | Outbound buffer tăng hoặc send mất quá lâu | `sendBufferSizeLimit`, `sendTimeLimit`, outbound channel queue, network/client throughput |
| Message của cùng user đến không đúng thứ tự | Xử lý ở executor nhiều thread | `setPreservePublishOrder`, `setPreserveReceiveOrder`, thứ tự publish từ nhiều producer |
| Ngắt kết nối sau một khoảng không hoạt động | STOMP heartbeat, container idle hoặc proxy/LB idle | Heartbeat negotiation, TaskScheduler, close code, timeout proxy |
| Session vẫn hiển thị online khi mất mạng | Chưa phát hiện disconnection | Heartbeat/idle timeout, cleanup event, TTL trạng thái hiện diện |
| Cleanup/presence notification bị lặp | `SessionDisconnectEvent` có thể xuất hiện nhiều lần | Dùng remove-if-present, idempotency, dedupe |
| Session reconnect nhưng không còn subscription | Kết nối mới mang session mới | Client cần CONNECT + SUBSCRIBE lại, phục hồi last-event-id |
| Broker relay khôi phục nhưng browser vẫn offline | System broker connection khác client WebSocket connection | `BrokerAvailabilityEvent` và client reconnect riêng |
| RAM tăng khi fan-out lớn | Nhiều session × buffer, subscriptions, broker queue | Memory/GC, active/pending messages, payload size, slow consumers |

Một số chỉ số thiết yếu: số lượng WebSocket sessions hiện tại/đã đóng, close code theo nguyên nhân, STOMP CONNECTED/DISCONNECT, tỉ lệ oversize message, queue của `clientInboundChannel`/`clientOutboundChannel`, send latency, số client chậm, scheduler heartbeat, lượng memory và số lần reconnect. Spring cung cấp `WebSocketMessageBrokerStats` và các thống kê STOMP/WebSocket; kết hợp monitoring/metrics hạ tầng để nhìn cả proxy và external broker. Không log body hoặc credentials nhạy cảm khi debug.

## 9. Những lỗi thiết kế phổ biến

1. **Nhầm STOMP message limit với một WebSocket frame limit.** Một STOMP message có thể qua nhiều WebSocket chunks; giới hạn khác nhau ở từng tầng.
2. **Coi `sendTimeLimit` là request deadline cứng.** Nó kiểm tra khả năng gửi của session khi có cạnh tranh/buffer, không đo “client đã xử lý xong”.
3. **Bật nhiều luồng ghi vào raw `WebSocketSession` mà không serialize.** Với raw handler, cần wrapper hoặc hàng đợi; STOMP broker Spring đã có cơ chế riêng.
4. **Tăng send buffer để chống disconnect mà không xử lý backpressure.** Nhiều session chậm có thể giữ rất nhiều RAM.
5. **Đồng nhất heartbeat với ACK nghiệp vụ.** Ping/heartbeat chỉ nói về liveness; message loss vẫn có thể xảy ra nếu disconnect/restart.
6. **Dựa vào `SessionConnectEvent` để hiển thị online thành công.** CONNECT mới được tiếp nhận; `SessionConnectedEvent` mới biểu thị STOMP handshake đã hoàn tất.
7. **Không làm cleanup idempotent.** `SessionDisconnectEvent` có thể lặp, làm double-release hay double-notification.
8. **Tưởng broker relay tự reconnect trình duyệt.** Client phải reconnect và subscribe lại.
9. **Đặt heartbeat dài hơn hoặc gần bằng idle timeout của proxy.** Dễ tạo disconnect theo chu kỳ dù app không lỗi; cần đo jitter và các timeout trung gian.
10. **Dùng simple broker một node nhưng kỳ vọng subscriptions chia sẻ qua nhiều node.** Khi cần scale đa instance, thiết kế external broker và routing phù hợp.
11. **Không kiểm soát user destinations và permissions.** Message limit giúp tài nguyên, không thay authentication/authorization tại handshake, inbound channel và destination.
12. **Mặc định mã close/ERROR giống nhau mọi browser.** Giới hạn có thể bị container chặn trước Spring; ghi log theo từng lớp và xây client chịu lỗi.

## 10. Câu hỏi tự kiểm tra

1. **Một STOMP SEND có body 100 KiB chia thành nhiều WebSocket messages 8 KiB, nhưng `setMessageSizeLimit(64 KiB)` thì sao?** → Spring kiểm tra kích thước STOMP message được ghép; chia nhỏ frame không “vượt rào” giới hạn.
2. **Trong cùng một session, thread A đang gửi chậm; thread B phát thêm message?** → B không nên ghi cạnh tranh vào socket; thông điệp được buffer/serialize và có thể khiến session chạm send buffer/time limit.
3. **`sendTimeLimit(5_000)` có bảo đảm một send blocking tự bị cắt chính xác sau 5 giây?** → Không; thời điểm kiểm tra giới hạn phụ thuộc sự kiện gửi/đóng và transport. Dùng monitoring/timeout ở tầng khác nếu cần.
4. **Tại sao mất mạng không luôn sinh DISCONNECT ngay?** → Client không kịp gửi frame; server phải dựa vào lỗi I/O, idle timeout hoặc heartbeat để phát hiện.
5. **Vì sao `SessionDisconnectEvent` cần idempotency?** → Event có thể phát hơn một lần; cleanup cần an toàn khi gọi lặp.
6. **Khi bật `setPreservePublishOrder(true)` có đảm bảo thứ tự global không?** → Không; chủ yếu áp dụng thứ tự publish trong một client session.
7. **Nếu một client mobile reconnect, subscription cũ có tự xuất hiện?** → Không; client cần đăng ký lại trên session mới và đồng bộ message đã bỏ lỡ nếu nghiệp vụ yêu cầu.
8. **Giới hạn 1 KiB inbound có làm client không bao giờ nhận MESSAGE lớn hơn 1 KiB?** → Không; inbound STOMP message limit không phải outbound maximum. Phải áp dụng chính sách payload khác nếu cần.

## 11. Tài liệu chính thức

- Spring Framework — STOMP performance: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html
- Spring Framework — Message ordering: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html
- Spring Framework — STOMP Simple Broker và heartbeat: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html
- Spring Framework — STOMP application-context events: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html
- Spring Framework — STOMP monitoring/statistics: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html
- Spring Framework — WebSocket server container config: https://docs.spring.io/spring-framework/reference/web/websocket/server.html
- Spring Framework 6.1 Javadoc — `WebSocketTransportRegistration`: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketTransportRegistration.html
- Spring Framework 6.1 Javadoc — `ConcurrentWebSocketSessionDecorator`: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/socket/handler/ConcurrentWebSocketSessionDecorator.html

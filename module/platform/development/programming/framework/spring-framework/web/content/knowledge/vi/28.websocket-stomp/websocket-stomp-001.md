# So sánh Polling, Server-Sent Events (SSE) và WebSocket: chọn cơ chế cập nhật trong Spring

## 1. Bài toán cần giải quyết

Một trang web thường phải biết **dữ liệu trên server vừa thay đổi**: đơn hàng chuyển trạng thái, dashboard có số liệu mới, hệ thống phát thông báo, tiến độ xử lý công việc, chat xuất hiện tin nhắn. Có ba cơ chế phổ biến:

- **Polling:** client chủ động gửi HTTP request lặp lại để hỏi xem có thông tin mới không.
- **Server-Sent Events (SSE):** client mở một HTTP connection dài hạn; server gửi liên tiếp các sự kiện văn bản từ server đến client khi có thay đổi.
- **WebSocket:** client và server duy trì kết nối hai chiều; cả hai có thể gửi message bất cứ lúc nào. Trong Spring, **STOMP over WebSocket** thường được dùng để thêm khái niệm destination, subscription và message routing.

Không có cơ chế nào tối ưu cho mọi tình huống. Quyết định đúng phụ thuộc vào **hướng dữ liệu, độ trễ chấp nhận được, số kết nối, tải request, đặc tính mạng/proxy, bảo mật, khả năng phục hồi và yêu cầu scale**.

Ví dụ: ứng dụng hiển thị trạng thái xử lý một tác vụ sau mỗi 10 giây không nhất thiết cần WebSocket. Ngược lại, một phòng chat có nhiều luồng trao đổi hai chiều không nên mặc định dùng polling 1 giây chỉ vì dễ triển khai.

## 2. Ba cơ chế hoạt động như thế nào?

### 2.1. Polling (short polling)

Client thực hiện HTTP GET theo chu kỳ, ví dụ 5 giây/lần:

~~~text
Browser                         Server
   | --- GET /api/status ------> |
   | <------ 200 current -------- |
   |       (đợi 5 giây)          |
   | --- GET /api/status ------> |
   | <------ 200 current -------- |
   |       (đợi 5 giây)          |
   | --- GET /api/status ------> |
   | <------ 200 changed -------- |
~~~

Ưu điểm: tương thích HTTP truyền thống, đi qua các hệ thống auth/proxy/load balancer quen thuộc, dễ cache và monitor, không phải giữ một connection cho mỗi client trong suốt thời gian phiên. Nhược điểm: request có thể trả về dữ liệu không đổi; tần suất càng cao thì HTTP traffic càng lớn, còn tần suất thấp thì người dùng thấy dữ liệu cập nhật chậm.

Nếu khoảng polling là `T` giây, độ trễ từ khi server đổi dữ liệu đến khi client biết có thể gần `T` giây; với thời điểm thay đổi phân bố đều so với lịch hỏi, trung bình xấp xỉ `T/2`, **chưa tính network/server latency**. Có `N` client cùng polling mỗi `T` giây, số request/giây xấp xỉ `N/T`. Ví dụ 10.000 client, 10 giây/lần ≈ 1.000 request/giây, ngay cả khi dữ liệu không đổi.

**Long polling** là biến thể: request được server giữ chờ đến khi có thay đổi hoặc hết timeout; client sau đó gọi lại. Nó giảm lượng response rỗng khi ít sự kiện nhưng phức tạp hơn short polling ở timeout, cancellation, giữ request đang chờ và xử lý burst. Long polling **không phải SSE**: mỗi lần có phản hồi, request HTTP kết thúc; SSE có thể đẩy nhiều event trên một response đang mở.

Khi dùng polling, có thể tối ưu bằng `ETag` + `If-None-Match`, `Last-Modified` + `If-Modified-Since` hoặc trả version/timestamp; nếu không đổi, trả `304 Not Modified` để tiết kiệm body. `304` vẫn tiêu tốn một lượt HTTP request và xử lý request.

### 2.2. SSE (Server-Sent Events)

Browser dùng `EventSource` mở HTTP GET với `Accept: text/event-stream`. Server giữ response đang mở, gửi các dòng văn bản đúng định dạng SSE, phân tách các event bằng dòng trống:

~~~text
Browser                         Server
   | --- GET /api/events -----> |
   | <---- HTTP 200 ------------ |
   |      Content-Type: text/event-stream
   | <---- id: 41 -------------- |
   |       event: update        |
   |       data: {"count":41}   |
   |                            |
   | <---- id: 42 -------------- |
   |       event: update        |
   |       data: {"count":42}   |
   |     (cùng HTTP response)   |
~~~

Mẫu SSE hợp lệ:

~~~text
id: 42
event: update
data: {"count":42}

: heartbeat

retry: 3000

~~~

Trong đó `data:` chứa nội dung (có thể nhiều dòng), `event:` là tên sự kiện, `id:` là ID mà trình duyệt ghi nhớ, `retry:` gợi ý thời gian reconnect tính bằng mili giây và dòng bắt đầu bằng dấu `:` là comment (thường dùng làm heartbeat). Kết thúc một event bằng **dòng trống**.

SSE theo chuẩn browser là **server → client**; khi client muốn gửi command vẫn dùng HTTP POST/fetch riêng. `EventSource` tự kết nối lại sau khi kết nối bị ngắt. Nếu trước đó server gửi `id:`, browser có thể gửi `Last-Event-ID` khi reconnect, **nhưng server phải tự có event log/cursor và logic replay thì mới khôi phục được event bỏ lỡ**. Chỉ thêm `id` vào response không tạo bảo đảm phát lại.

SSE sử dụng HTTP bình thường, đơn giản để tích hợp ứng dụng web hiện có. Tuy nhiên response dài hạn cần xử lý timeout, proxy buffering, heartbeat, giới hạn connection/stream và cleanup khi client rời đi. Với HTTP/1.1, trình duyệt thường giới hạn số connection đồng thời theo origin (hay gặp khoảng 6); HTTP/2 có giới hạn streams khác và cần cấu hình thực tế.

### 2.3. WebSocket và STOMP

WebSocket mở phiên giao tiếp full-duplex. Sau handshake HTTP thích hợp, cùng một kết nối cho phép gửi message **hai chiều** mà không cần mỗi message là một HTTP request/response.

~~~text
Browser                      WebSocket server
   | --- handshake HTTP -----> |
   | <--- switched protocols - |
   | ------ "join room" -----> |
   | <----- "member joined" -- |
   | <----- "new message" ----- |
   | ------ "send text" ------> |
   | <----- "new message" ----- |
   |       (kết nối dài hạn)    |
~~~

**Raw WebSocket** là giao thức truyền frame; nó **không tự cung cấp** model topic/subscription, persistence, queue, replay hay authorization cho từng loại tin. `STOMP` là giao thức messaging cấp ứng dụng có frame như `CONNECT`, `SUBSCRIBE`, `SEND`, `MESSAGE`, `DISCONNECT`; nó có thể chạy **trên WebSocket** và được Spring hỗ trợ bằng `@EnableWebSocketMessageBroker`, `@MessageMapping`, `SimpMessagingTemplate`.

Một ví dụ đường dẫn STOMP trong Spring:

~~~text
Client connects ws://host/ws
  --> CONNECT (STOMP)
  --> SUBSCRIBE destination:/topic/orders
Client sends SEND destination:/app/command
  --> Spring @MessageMapping("/command")
  --> server sends to /topic/orders
  --> broker forwards MESSAGE to subscribers
~~~

**Chú ý:** `new WebSocket("/ws")` kết nối bằng WebSocket thuần không tự tạo hoặc xử lý các STOMP frames. Để nói chuyện với endpoint STOMP, browser phải dùng STOMP client (ví dụ `@stomp/stompjs`) hoặc tự thực hiện giao thức STOMP. Ngược lại, endpoint raw `TextWebSocketHandler` không tự hiểu STOMP.

WebSocket không tự động reconnect/replay ở cấp chuẩn browser WebSocket; cần client library hoặc code tự kết nối lại, heartbeat, resume state và xử lý duplicate/missing event.

## 3. Bảng so sánh thực tế

| Tiêu chí | Polling | SSE | WebSocket / STOMP |
| --- | --- | --- | --- |
| Chiều thông tin cập nhật | Client hỏi, server trả lời | Server → client trên một HTTP response; client gửi lệnh bằng HTTP riêng | Full-duplex hai chiều |
| Kết nối | HTTP request lặp lại | HTTP streaming dài hạn | Kết nối WebSocket dài hạn |
| Độ trễ khi có dữ liệu mới | Phụ thuộc chu kỳ polling | Thường gửi ngay khi có sự kiện | Thường gửi ngay khi có message |
| Traffic khi dữ liệu ít thay đổi | Nhiều request rỗng | Nhỏ nếu heartbeat vừa đủ | Nhỏ nếu heartbeat vừa đủ |
| Tích hợp trình duyệt | `fetch`, thư viện HTTP | `EventSource` | `WebSocket`; STOMP cần thêm client |
| Gửi từ browser lên server | HTTP GET/POST bình thường | HTTP request riêng | Qua WebSocket trực tiếp hoặc STOMP `SEND` |
| Reconnect tự động | Lịch polling do ứng dụng quản lý | `EventSource` tự reconnect | Ứng dụng/thư viện phải quản lý |
| Replay thông tin bỏ lỡ | GET lại current snapshot hoặc version | Dùng `id`/`Last-Event-ID` **nếu backend có replay** | Cần cơ chế replay riêng |
| Proxy/load balancer | Thường đơn giản nhất | Cần hỗ trợ streaming, không buffer, timeout phù hợp | Cần hỗ trợ WebSocket upgrade/tunnel và idle timeout |
| Dữ liệu binary | HTTP hỗ trợ | SSE là văn bản UTF-8 | WebSocket có text và binary frames; STOMP thường dùng payload messaging |
| Scale | Scale HTTP stateless dễ hơn, nhưng tốn request | Scale các stream dài hạn và fan-out | Scale connection, subscription, broker và fan-out |
| Phù hợp | Dữ liệu ít thay đổi, chấp nhận trễ | Thông báo/live feed một chiều | Chat, tương tác hai chiều, cộng tác thời gian thực |

Bảng chỉ mô tả đặc tính nền tảng. **Không nên khẳng định WebSocket luôn nhanh hơn SSE**: khi hai bên đều duy trì connection ổn định và chỉ server gửi update, khác biệt latency có thể nhỏ hơn chi phí thiết kế, vận hành và recovery. Hiệu năng thực tế phải đo cùng payload, số người dùng, mạng và server.

## 4. Quy tắc quyết định theo tình huống

1. **Báo cáo, trạng thái tác vụ, dashboard cập nhật mỗi 10–60 giây:** bắt đầu từ polling. Nếu thay đổi rất thưa, tăng khoảng hỏi, dùng version/ETag và dừng khi tab ẩn nếu phù hợp.
2. **Thống kê trực tiếp, feed tin, log tiến độ, thông báo server gửi tới browser:** cân nhắc SSE trước; browser nhận sự kiện một chiều và vẫn dùng HTTP POST để gửi tác vụ.
3. **Chat, multiplayer, collaborative editing, tương tác thời gian thực hai chiều liên tục:** cân nhắc WebSocket. Với các kênh publish/subscribe và routing, STOMP giúp cấu trúc message theo destination.
4. **Nhiều instance server, yêu cầu broadcast toàn hệ thống:** SSE/WebSocket đều cần kiến trúc pub/sub hoặc event bus chung; STOMP simple broker chỉ sống trong bộ nhớ từng instance, **không đủ cho clustering**. Chọn broker relay hoặc kiến trúc fan-out phù hợp.
5. **Cần chắc chắn không mất message, thứ tự và khả năng resume:** xác định delivery semantics riêng (event ID, log bền vững, cursor, ACK, deduplication). Không cơ chế transport nào mặc định thay thế hàng đợi bền vững/database.
6. **Client có thể offline lâu:** khi quay lại nên đồng bộ snapshot và delta từ nguồn bền vững; duy trì WebSocket không thay thế push notification khi trình duyệt/app không hoạt động.

### Một sơ đồ quyết định

~~~text
Cần cập nhật dữ liệu trên browser?
          |
          v
Client có cần gửi message tương tác liên tục, độ trễ thấp hai chiều?
       /                              \
     Có                              Không
     |                                 |
  WebSocket                       Chấp nhận trễ vài giây/phút?
     |                              /              \
  Cần topic/room?                 Có              Không
   /       \                      |                |
  Có      Không                Polling             SSE
   |        |                  (ETag/version)      (+replay nếu cần)
 STOMP   Raw WebSocket
~~~

Đừng chọn theo tên công nghệ “real-time”. Hãy chốt SLO cụ thể như `p95 update latency < 2s`, số client đồng thời, tỉ lệ event/client, payload mỗi event, mức độ chịu mất dữ liệu, retry và chi phí infra rồi mới thử nghiệm.

## 5. Spring Framework: dùng API nào?

### Polling trong Spring MVC

Một endpoint REST trả current snapshot:

~~~java
@RestController
@RequestMapping("/api")
class StatusController {
    @GetMapping("/status")
    Status status() {
        return statusService.current();
    }
}
~~~

`Status` và `statusService` là thành phần ứng dụng cần có; đoạn trên minh họa thiết kế endpoint. Client gọi `GET /api/status` theo chu kỳ. Controller không cần giữ connection hoặc subscription dài hạn giữa các lần gọi.

### SSE trong Spring MVC và WebFlux

Trong **Spring MVC**, dùng `SseEmitter`:

~~~java
@GetMapping(path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter events() {
    SseEmitter emitter = new SseEmitter(60_000L);
    registerAndSendUpdates(emitter);
    return emitter;
}
~~~

`registerAndSendUpdates` là logic tùy chỉnh; khi client disconnect/error/timeout phải gỡ emitter ra khỏi registry và giải phóng tài nguyên. Spring MVC sử dụng Servlet async để giữ response mở; ghi response SSE trong Servlet stack **vẫn có thể dùng blocking thread**. Không gửi message từ event loop reactive sang một API blocking mà không có chiến lược xử lý phù hợp.

Trong **Spring WebFlux**, có thể trả `Flux<ServerSentEvent<T>>`:

~~~java
@GetMapping(path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<Update>> events() {
    return updatesFlux.map(update ->
            ServerSentEvent.<Update>builder()
                    .id(Long.toString(update.sequence()))
                    .event("update")
                    .data(update)
                    .build());
}
~~~

Đoạn WebFlux trên là minh họa; `updatesFlux` phải là publisher thật do hệ thống quản lý. Cần thiết kế phát sự kiện tới nhiều subscriber, backpressure và xử lý subscriber chậm. Đừng lấy một `Flux` chỉ có một subscriber rồi giả định nó tự broadcast.

### WebSocket STOMP trong Spring

Tạo cấu hình message broker:

~~~java
@Configuration
@EnableWebSocketMessageBroker
class SocketConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
~~~

`/ws` là **đường dẫn handshake WebSocket**, `/app` là tiền tố route message từ client vào các `@MessageMapping` trong Spring, còn `/topic` là tiền tố broker chuyển message tới các subscribers. Tên `/topic` là quy ước ở simple broker, không phải bảo đảm durability.

Message đến `/app/command` có thể được xử lý bằng:

~~~java
@Controller
class CommandHandler {
    private final SimpMessagingTemplate template;

    CommandHandler(SimpMessagingTemplate template) {
        this.template = template;
    }

    @MessageMapping("/command")
    void command(Command cmd) {
        template.convertAndSend("/topic/updates", cmd);
    }
}
~~~

Đây là snippet minh họa; cần model `Command`. Với production, **xác thực/ủy quyền theo user, destination và hành động** trước khi chuyển bất kỳ nội dung client nào sang topic. Không tin rằng một topic có tên khó đoán là một hàng rào bảo mật.

## 6. Demo hoàn chỉnh Java 17+: một server cho cả ba mô hình

Ví dụ dưới dùng **Spring Boot 3.x chạy trên Spring MVC**. Một tác vụ thay đổi trạng thái mỗi 5 giây. Client có thể:

- Poll `GET /api/status` để lấy snapshot mới nhất.
- Subscribe SSE `GET /api/events` để nhận event tự động.
- Dùng STOMP qua WebSocket `/ws`, subscribe `/topic/updates` và gửi command tới `/app/command`.

Các ví dụ chung một state in-memory và phục vụ **học tập trên một instance**, chưa triển khai persistence, authorization, backplane, replay hoặc load balancing.

### 6.1. `pom.xml`

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
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>realtime-demo</artifactId>
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

WebSocket STOMP starter tích hợp với MVC; ví dụ này **không yêu cầu** `spring-boot-starter-webflux`. `SseEmitter` thuộc Spring MVC. Đường dẫn source đặt tại `src/main/java/demo/RealtimeDemoApplication.java`.

### 6.2. `src/main/java/demo/RealtimeDemoApplication.java`

~~~java
package demo;

import java.io.IOException;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;

@SpringBootApplication
@EnableScheduling
public class RealtimeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RealtimeDemoApplication.class, args);
    }
}

record Update(long sequence, String state) {}
record Command(String text) {}

@Component
class UpdatePublisher {
    private final AtomicLong counter = new AtomicLong();
    private final AtomicReference<Update> current =
            new AtomicReference<>(new Update(0, "READY"));
    private final CopyOnWriteArrayList<SseEmitter> emitters =
            new CopyOnWriteArrayList<>();
    private final SimpMessagingTemplate broker;

    UpdatePublisher(SimpMessagingTemplate broker) {
        this.broker = broker;
    }

    Update current() {
        return current.get();
    }

    SseEmitter openStream() {
        // Kết nối SSE tự timeout sau 60 giây;
        // EventSource trên browser có thể mở lại.
        SseEmitter emitter = new SseEmitter(60_000L);
        emitters.add(emitter);
        emitter.onCompletion(() -> emitters.remove(emitter));
        emitter.onTimeout(() -> emitters.remove(emitter));
        emitter.onError(error -> emitters.remove(emitter));

        send(emitter, current());
        return emitter;
    }

    @Scheduled(initialDelay = 5_000, fixedRate = 5_000)
    public void tick() {
        publish("tick");
    }

    void publish(String state) {
        Update update = new Update(counter.incrementAndGet(), state);
        current.set(update);

        for (SseEmitter emitter : emitters) {
            send(emitter, update);
        }

        // Phát tới client STOMP subscribe /topic/updates.
        broker.convertAndSend("/topic/updates", update);
    }

    private void send(SseEmitter emitter, Update update) {
        try {
            emitter.send(SseEmitter.event()
                    .id(Long.toString(update.sequence()))
                    .name("update")
                    .data(update, MediaType.APPLICATION_JSON));
        } catch (IOException | IllegalStateException failure) {
            emitters.remove(emitter);
            emitter.completeWithError(failure);
        }
    }
}

@RestController
class UpdatesController {
    private final UpdatePublisher publisher;

    UpdatesController(UpdatePublisher publisher) {
        this.publisher = publisher;
    }

    @GetMapping("/api/status")
    Update status() {
        return publisher.current();
    }

    @GetMapping(path = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    SseEmitter stream() {
        return publisher.openStream();
    }

    @MessageMapping("/command")
    void command(Command command) {
        publisher.publish("client:" + command.text());
    }
}

@Configuration
@EnableWebSocketMessageBroker
class WebSocketConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
~~~

Giải thích các phần quan trọng:

- `AtomicReference<Update>` lưu snapshot mới nhất cho polling; `AtomicLong` tạo sequence ID trong một tiến trình.
- `CopyOnWriteArrayList` chỉ hợp lý trong demo/số lượng listener nhỏ. Với lượng kết nối lớn, việc copy mảng khi thêm/xóa, broadcast tuần tự và write blocking có thể gây nghẽn; cân nhắc hệ thống fan-out chuyên dụng và kiểm soát slow clients.
- `@Scheduled` phát một update mỗi 5 giây. Trình duyệt SSE kết nối lại sau timeout và nhận snapshot hiện tại.
- Cả SSE và STOMP cùng nhận bản ghi từ `publish(...)`; request HTTP thường nhận snapshot từ `current()`.
- `SseEmitter.send(...)` có thể thất bại khi client rời đi; callback completion/error/timeout gỡ emitter. Với hệ thống thực, cần tránh gửi đồng thời và có chính sách write timeout/heartbeat/backpressure.
- `sequence` tăng để thuận tiện phát hiện khoảng trống. Demo **không lưu lịch sử** nên chưa thể dùng `Last-Event-ID` để phát lại các sequence bị bỏ lỡ.
- `@MessageMapping("/command")` minh họa đường **client → server** chỉ có ở kênh STOMP. Trong production phải validate kích thước/nội dung và kiểm tra quyền phát command.

### 6.3. Chạy và thử polling

Dùng JDK 17+ và Maven trong thư mục dự án:

~~~bash
mvn spring-boot:run
~~~

Trong terminal khác:

~~~bash
curl -s http://localhost:8080/api/status
~~~

Ngay khi server mới khởi động, **trước lần tick đầu tiên**, response dự kiến:

~~~json
{"sequence":0,"state":"READY"}
~~~

Sau một số lần tick, `sequence` và `state` thay đổi; không thể cố định một output sau khi server chạy lâu. Để gọi liên tục từ JavaScript browser:

~~~javascript
let active = true;

async function poll() {
    if (!active) return;
    try {
        const response = await fetch("/api/status");
        if (!response.ok) throw new Error("HTTP " + response.status);
        const update = await response.json();
        console.log("poll", update);
    } catch (error) {
        console.warn("poll failed", error);
    } finally {
        // setTimeout sau khi request kết thúc tránh chồng request
        // nếu server đáp chậm hơn khoảng polling.
        if (active) setTimeout(poll, 5000);
    }
}
poll();
// Khi rời trang/không cần nữa: active = false;
~~~

Với trang browser phục vụ từ **cùng origin** với ứng dụng, relative URL `/api/status` hoạt động trực tiếp. Nếu chạy JavaScript ở origin khác, dùng absolute URL và cấu hình CORS/auth tương ứng; không mở CORS tùy tiện cho hệ thống thật.

### 6.4. Thử SSE

Với command line:

~~~bash
curl -N http://localhost:8080/api/events
~~~

`-N`/`--no-buffer` giúp quan sát nội dung streaming. Một snapshot ban đầu và các update tiếp theo có dạng:

~~~text
id:0
event:update
data:{"sequence":0,"state":"READY"}

id:1
event:update
data:{"sequence":1,"state":"tick"}

~~~

Khoảng trắng/cách serialize của framework có thể khác một chút; trường quan trọng là `id`, `event`, `data` và dòng trống kết thúc event. Nếu kết nối sau lần tick, event đầu có thể không phải sequence 0.

Browser sử dụng:

~~~javascript
const stream = new EventSource("/api/events");
stream.addEventListener("update", event => {
    const update = JSON.parse(event.data);
    console.log("SSE", update.sequence, update.state);
});
stream.onerror = () => console.warn("SSE disconnected; browser may retry");

// Khi không còn cần cập nhật:
// stream.close();
~~~

Browser tự reconnect khi stream lỗi/đóng theo cách cần reconnect. Đừng giả định SSE `onerror` luôn có nghĩa ngừng kết nối vĩnh viễn; hãy xem trạng thái `readyState`. Để đảm bảo không mất sự kiện cần lưu event log và xử lý header `Last-Event-ID` khi client kết nối lại. Demo chỉ gửi **snapshot mới nhất** và không dùng header đó.

### 6.5. Thử STOMP over WebSocket

Cài thư viện frontend `@stomp/stompjs` (ví dụ `npm install @stomp/stompjs` trong ứng dụng JavaScript có bundler), sau đó dùng:

~~~javascript
import { Client } from "@stomp/stompjs";

const scheme = location.protocol === "https:" ? "wss" : "ws";
const client = new Client({
    brokerURL: scheme + "://" + location.host + "/ws",
    reconnectDelay: 3000,
    onConnect: () => {
        client.subscribe("/topic/updates", message => {
            const update = JSON.parse(message.body);
            console.log("STOMP", update.sequence, update.state);
        });

        client.publish({
            destination: "/app/command",
            body: JSON.stringify({ text: "refresh" })
        });
    },
    onStompError: frame => {
        console.error("Broker error", frame.headers["message"]);
    }
});
client.activate();

// Khi rời màn hình: await client.deactivate();
~~~

Khi kết nối và subscribe thành công, client bắt đầu nhận những lần `tick`. Lệnh `SEND` tới `/app/command` sẽ khiến server phát update `state="client:refresh"` lên cả SSE stream và STOMP topic. Nếu client gửi `SEND` trước khi subscribe, có thể bỏ lỡ message đầu tiên; ví dụ subscribe trước rồi mới publish.

**Không gửi STOMP SEND qua `new WebSocket(...)` rồi chỉ viết JSON thuần:** STOMP yêu cầu frame đúng protocol. Nếu cần raw WebSocket cho payload JSON, tạo handler raw khác bằng Spring WebSocket API; đó là thiết kế riêng.

## 7. Reconnect, nhất quán dữ liệu và sự kiện bị bỏ lỡ

Hệ thống cập nhật thật phải định nghĩa điều gì xảy ra khi browser ngủ, mất mạng hoặc server restart.

### Polling: đồng bộ theo phiên bản

Polling thường lấy **current snapshot**. Khi GET mới thành công, client biết trạng thái hiện tại nhưng không biết tất cả chuyển trạng thái trung gian. Nếu cần lịch sử, endpoint nên hỗ trợ `?since=<cursor>` hoặc gọi event history riêng. Cùng một dữ liệu có thể được nhận lặp lại; client có thể so version/ETag để không render thừa.

### SSE: `Last-Event-ID` và replay

Browser ghi nhận `id` và thường gửi `Last-Event-ID` khi tự reconnect. Server cần:

1. Lưu event có ID/offset nhất quán vào storage hoặc event log phù hợp.
2. Khi reconnect, đọc cursor client gửi và phát lại event sau cursor đó.
3. Chống trùng ở client (idempotent update) vì ranh giới disconnect/ack có thể gây gửi lại.
4. Phát hiện cursor đã quá cũ do retention, rồi yêu cầu tải lại snapshot.
5. Đảm bảo trình tự giữa **replay** và **live** để không bỏ mất sự kiện trong lúc chuyển đổi.

Trong Spring MVC, có thể đọc `@RequestHeader(value = "Last-Event-ID", required = false) String lastId` khi mở emitter; ví dụ demo chưa có event store nên không tự tuyên bố chính xác kiểu delivery "exactly once".

### WebSocket/STOMP: reconnect không bằng replay

WebSocket native không tự kết nối lại; `@stomp/stompjs` cho phép `reconnectDelay` và subscribe lại khi `onConnect` được gọi. Nhưng message gửi khi offline không tự xuất hiện sau reconnect nếu không có broker durable queue/replay hoặc API lấy delta. Đừng gán khả năng persistence, acknowledgement, transaction của **một broker STOMP đầy đủ** cho simple broker tích hợp.

Để đạt trải nghiệm ổn định có thể dùng mô hình chung: sau reconnect, client gọi HTTP để lấy snapshot và version hiện tại, rồi subscribe stream hoặc áp dụng delta; server phát sequence để phát hiện gap. Thiết kế thứ tự subscribe/snapshot phải xử lý race, không đơn giản “GET xong mới subscribe” khi event có thể xảy ra giữa hai bước.

## 8. Scale, tài nguyên và proxy

### Polling

Điểm nghẽn là **request rate** chứ không nhất thiết số socket mở. Tính `N / interval`, thêm jitter để tránh hàng vạn browser cùng thức dậy đúng một giây, và có backoff khi server lỗi. Tối ưu cache, ETag và chỉ poll khi tab đang hiện nếu nghiệp vụ cho phép. Polling cùng chu kỳ 1 giây cho hàng trăm nghìn client có thể đắt hơn các stream dài hạn.

### SSE

Mỗi stream giữ tài nguyên kết nối và state đăng ký; reverse proxy có thể buffer response nếu không cấu hình cho streaming. Cần timeout, heartbeat comment, event size giới hạn và cleanup khi disconnect. Spring MVC `SseEmitter` có thể sử dụng thread ghi blocking; thiết kế broadcast lớn hoặc client quá chậm cần cơ chế fan-out tách biệt. Nếu scale nhiều instance, event cần phân phối tới đúng instance đang giữ emitter (thường dùng event bus chung) hoặc một tầng stream gateway.

### WebSocket/STOMP

Mỗi kết nối giữ phiên lâu, có idle timeout, heartbeat, giới hạn message và số subscriber. Các vấn đề phải đo gồm active sessions, outbound channel queue, slow consumers, memory per connection, broker health và thời gian reconnect. Spring **simple broker** là in-memory, hỗ trợ một phần STOMP, không phù hợp clustering. Nếu nhiều node cùng phục vụ, dùng STOMP broker relay tới broker ngoài (ví dụ RabbitMQ/ActiveMQ có hỗ trợ STOMP), hoặc kiến trúc pub/sub khác được thiết kế cho nhiệm vụ.

### Proxy, load balancer và TLS

- Dùng HTTPS/WSS trên Internet, cấu hình certificate, origin, load balancer và idle timeout phù hợp.
- Với SSE, tắt hoặc điều chỉnh proxy buffering theo tuyến streaming; gửi heartbeat để phát hiện connection đã rớt.
- Với WebSocket, proxy phải cho phép handshake/tunnel thích hợp và timeout đủ dài; có thể cần session affinity hoặc broker chia sẻ, phụ thuộc thiết kế.
- Với polling, giữ API stateless nếu có thể; thêm rate limit và conditional requests.
- Với cả ba, **TLS, xác thực, ủy quyền và bảo vệ dữ liệu** là yêu cầu riêng, không do việc chọn transport tự đáp ứng.

## 9. Bảo mật và xử lý input

- **Polling/REST:** bảo vệ endpoint bằng Spring Security như HTTP API thông thường; áp dụng authorization theo user/tenant/resource, rate limit, cache headers để tránh lộ dữ liệu.
- **SSE:** HTTP request dùng session/cookie cùng origin theo chính sách browser; `EventSource` chuẩn không cho set tùy ý custom Authorization header như `fetch`. Nếu dùng cookie, cần kiểm soát CSRF cho thao tác thay đổi trạng thái (các lệnh POST riêng), SameSite, CORS/credentials, và không nhúng token nhạy cảm vào query string/log.
- **WebSocket:** kiểm tra Origin và xác thực ở handshake/messaging phù hợp; origin check **không thay thế** xác thực/ủy quyền. Với STOMP, kiểm soát CONNECT, SUBSCRIBE, SEND và quyền theo destination, user/tenant. Spring Security có cơ chế message authorization; chính sách cho CONNECT/CSRF cần được thiết kế đúng cho ứng dụng trình duyệt.
- **Payload:** giới hạn kích thước, validate JSON/commands, dùng `textContent` thay vì gắn trực tiếp dữ liệu không tin cậy bằng `innerHTML`. Không xem mọi subscriber trên một topic là có quyền đọc dữ liệu nhạy cảm.
- **Replay:** cursor và event history phải được lọc theo quyền người dùng; tránh cho phép client đặt cursor để đọc các event của tenant khác.

Đặc biệt trong hệ thống nhiều khách hàng, một topic toàn cục như `/topic/orders` có thể vô tình phát sự kiện tới sai đối tượng nếu ứng dụng thiếu message authorization hoặc phân tuyến theo người dùng. Quyền xem dữ liệu cần kiểm tra tại **nguồn phát, destination và đường đọc lịch sử**.

## 10. Các lỗi tư duy và lỗi triển khai thường gặp

1. **“Muốn real-time thì phải dùng WebSocket.”** Nếu chỉ server thông báo cho browser, SSE đơn giản hơn và có reconnect tích hợp; nếu update hiếm và chấp nhận trễ, polling càng dễ.
2. **“SSE có `id` là không mất message.”** Chỉ đúng nếu backend cài replay bền vững và xử lý race/cursor.
3. **“WebSocket tự quản lý topic và replay.”** Raw WebSocket không cung cấp broker; STOMP simple broker cũng không cho durable messaging/clustering.
4. **“Một server chạy thì nhiều replica cũng sẽ broadcast đúng.”** Listener SSE và simple STOMP broker là state cục bộ; muốn nhiều instance cần backplane hoặc broker.
5. **“Polling càng nhanh càng tốt.”** Interval nhỏ làm tăng request rate và peak load; cần chọn theo độ trễ nghiệp vụ và dùng jitter/backoff.
6. **“SSE không cần heartbeat.”** Kết nối im lặng có thể bị proxy hoặc mạng đóng; keepalive phù hợp giúp phát hiện ngắt.
7. **“Socket còn mở là client còn hoạt động tốt.”** Client có thể chậm, buffer outbound có thể lớn; phải giới hạn và thu thập metrics.
8. **“Cần song công thì dùng hai SSE connections.”** SSE một chiều; gửi ngược qua POST được nhưng nếu tương tác hai chiều liên tục, WebSocket/STOMP thường tự nhiên hơn.
9. **“Cứ thêm `withSockJS()` là WebSocket nhanh hơn.”** SockJS là lớp fallback transport/compatibility, không phải STOMP hay một tối ưu tốc độ mặc định. Dùng khi môi trường client/proxy cần fallback.
10. **“Trả `Flux` từ controller MVC là non-blocking toàn bộ.”** Servlet MVC vẫn có cơ chế ghi HTTP và executor riêng; hiểu threading model của stack đang dùng.

## 11. Checklist triển khai và đo kiểm

Trước khi release, hãy ghi rõ:

- **Luồng cập nhật:** server → client hay hai chiều? Một người, nhiều người, toàn hệ thống?
- **Độ trễ:** mục tiêu p95/p99 và tỉ lệ update/cấp số client tối đa?
- **Data semantics:** snapshot mới nhất đủ chưa, hay phải phát lại mọi event? Có cần thứ tự, dedup, idempotency?
- **Transport:** HTTP polling, SSE stream hay WebSocket/STOMP; proxy/load balancer hỗ trợ cụ thể ra sao?
- **Recovery:** reconnect, backoff, heartbeat, resubscribe, snapshot/delta, giới hạn retention?
- **Capacity:** request/s; active SSE/WebSocket connections; memory, thread, executor, pending queue và slow consumer?
- **Security:** auth, origin/CORS/CSRF, topic subscription permissions, tenant isolation, input validation?
- **Observability:** p95 update lag, server→client fan-out lag, reconnect count, disconnect errors, dropped/duplicated events, broker queue size?
- **Load test:** mô phỏng client thật, network chậm, proxy, restart, nhiều instance và mất kết nối; đừng chỉ đo localhost một client.

**Cách chọn thực dụng:** bắt đầu bằng polling nếu chấp nhận trễ và tần suất thấp; chọn SSE khi chủ yếu server đẩy thông báo; dùng WebSocket/STOMP khi giao tiếp hai chiều hoặc mô hình subscription phức tạp thực sự cần. Tách riêng bài toán **transport** khỏi bài toán **phát lại dữ liệu đáng tin cậy, bảo mật và scale**.

## 12. Tài liệu tham khảo

- Spring Framework — Asynchronous Requests, SSE/`SseEmitter` (MVC): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — Enable STOMP: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html
- Spring Framework — Message Flow: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html
- Spring Framework — Simple Broker: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html
- Spring Framework — External Broker: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html
- Spring Framework — WebSocket transport configuration: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/server-config.html
- MDN — Using server-sent events: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- MDN — WebSocket API: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket

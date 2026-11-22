# Simple broker, broker relay và lựa chọn khi mở rộng hệ thống

## 1. Vấn đề mà STOMP broker giải quyết

WebSocket mở kênh giao tiếp hai chiều, duy trì lâu dài giữa trình duyệt/client và Spring server. STOMP bổ sung giao thức messaging trên kênh đó: client gửi `CONNECT`, `SUBSCRIBE`, `SEND`, `DISCONNECT`; server hoặc broker phát `MESSAGE` đến các phiên đã subscribe. Khi một client subscribe `/topic/news`, hệ thống cần biết **ai đang subscribe, message phải đi đâu và khi nào được gửi**.

Spring Framework hỗ trợ hai cách triển khai broker:

- **Simple broker**: bộ xử lý subscription nhẹ, chạy **trong JVM Spring**, lưu subscription trong RAM, gửi message đến các WebSocket sessions phù hợp trên instance đó. Bật bằng `enableSimpleBroker(...)`.
- **STOMP broker relay**: Spring chuyển tiếp STOMP traffic đến **message broker bên ngoài hỗ trợ STOMP/TCP** như RabbitMQ (bật STOMP plugin) hoặc ActiveMQ. Bật bằng `enableStompBrokerRelay(...)`. Broker bên ngoài xử lý subscriptions, routing và tính năng messaging của chính nó.

Sự lựa chọn quan trọng khi ứng dụng mở rộng từ một Spring process lên nhiều instances/pods. **Thêm pod với simple broker không tự tạo mạng phân phối messages chung**. Relay giúp nhiều Spring nodes truy cập chung một broker, nhưng không tự mang lại durable delivery, exactly-once hay authorization đúng cho từng người dùng.

Bài học đi từ sơ đồ luồng Spring messaging, cấu hình Java, semantics routing/ACK, mô hình scale, user destinations, connection/heartbeat, fault recovery, security đến ví dụ **Java 17+ + Spring Boot 3.3.x/Spring Framework 6.1.x**. Các code fragment đều được phân biệt với chương trình chạy đầy đủ.

## 2. Sơ đồ luồng: endpoint, application destination và broker destination

Đầu tiên cần phân biệt **URL mở WebSocket** với **STOMP destination**:

| Giá trị | Vai trò | Ai xử lý? |
| --- | --- | --- |
| `/ws` | HTTP handshake / WebSocket endpoint | Servlet container và Spring WebSocket |
| `/app/chat` | Client gửi STOMP `SEND` cho nghiệp vụ | `@MessageMapping("/chat")` sau khi Spring bỏ prefix `/app` |
| `/topic/chat` | Destination dùng để subscribe/broadcast | Broker (simple hoặc external) |
| `/queue/notices` | Destination có tiền tố `/queue` | Simple broker coi là chuỗi routing; external broker tùy policy |
| `/user/queue/notices` | Destination logic dành cho user/session | Spring `UserDestinationMessageHandler` dịch thành destination cụ thể |

Luồng thường gặp:

```text
Client A                        Spring                            Client B
   │                               │                                  │
   ├─ SEND /app/chat ─────────────►│ clientInboundChannel             │
   │                               │ @MessageMapping("/chat")         │
   │                               │ @SendTo("/topic/chat")            │
   │                               ▼                                  │
   │                         brokerChannel                            │
   │                               │                                  │
   │                ┌──────────────┴──────────────┐                   │
   │                ▼                             ▼                   │
   │          SimpleBroker                STOMP Broker Relay           │
   │          (local RAM)                 → External Broker            │
   │                └──────────────┬──────────────┘                   │
   │                               │                                  │
   │                         clientOutboundChannel                    │
   │                               │                                  │
   │◄──── MESSAGE /topic/chat ─────┼───── MESSAGE /topic/chat ───────►│
```

Sơ đồ chứa **hai lựa chọn broker thay thế nhau**. Một cấu hình Spring cho cùng broker destinations thường chỉ bật **một** broker handler. `clientInboundChannel` nhận messages từ WebSocket; `brokerChannel` nhận messages do application code publish qua `SimpMessagingTemplate` hoặc kết quả của controller; `clientOutboundChannel` đưa broker messages ra WebSocket sessions.

**Không nhầm:** `SimpMessagingTemplate.convertAndSend("/topic/chat", value)` publish tới destination. Lời gọi đó **không đồng nghĩa** client đã nhận/đã xử lý, và nó không phải thao tác gọi HTTP endpoint. Tương tự, HTTP status 101 chỉ xác nhận WebSocket Upgrade; client còn cần STOMP CONNECT và SUBSCRIBE mới có subscription.

## 3. Simple broker: cách hoạt động, giới hạn và heartbeat

### 3.1 Cơ chế trong một instance

Với `registry.enableSimpleBroker("/topic", "/queue")`, Spring tạo bộ nhớ quản lý subscriptions từ các STOMP sessions. Khi A và B subscribe `/topic/news`, rồi server publish message vào destination đó, simple broker phát tới hai sessions. Client C không subscribe sẽ không nhận. Khi client offline, bộ nhớ simple broker **không lưu backlog** để giao sau này.

```text
Spring instance A
 ├─ WebSocket session user1 → SUB /topic/news
 ├─ WebSocket session user2 → SUB /topic/news
 ├─ WebSocket session user3 → SUB /topic/alerts
 └─ SimpleBroker (subscription registry trong RAM)
       │
       ├─ publish /topic/news   → user1, user2
       └─ publish /topic/alerts → user3
```

Các thuộc tính cốt lõi:

1. **Nhanh triển khai**: phù hợp bài học, demo, ứng dụng một instance và thông báo realtime có thể refresh/resync.
2. **Không có persistent message store**: restart JVM mất WebSocket sessions/subscriptions; client reconnect và subscribe lại.
3. **Không phải message broker đầy đủ**: hỗ trợ tập con của STOMP, không cung cấp ACK/RECEIPT semantics và các tính năng cao cấp như full broker. Không dựa vào `ack:client-individual` với simple broker để bảo đảm redelivery.
4. **Subscription match trong instance hiện tại**: không tự chia sẻ subscription registry với các instance Spring khác.
5. **Tiền tố chỉ là quy ước**: `/topic` và `/queue` không tự áp đặt durable topic hay competing-consumer queue. Nếu hai client cùng subscribe `/queue/jobs` dưới simple broker, không nên mặc định chỉ một client nhận job.
6. **Heartbeat có thể cấu hình** với một `TaskScheduler`. STOMP heartbeats khác WebSocket Ping/Pong và TCP keepalive.

Đoạn cấu hình nền:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class SocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOriginPatterns("http://localhost:*");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

Đây là **Spring configuration fragment**, không phải chương trình Java tự chạy. `/ws` là URL handshake, còn `/app` và `/topic` là destination prefixes. Origin localhost chỉ phục vụ ví dụ local; production cần HTTPS/WSS, allowlist origins và authorization phù hợp.

### 3.2 Thiết lập heartbeat cho simple broker

Simple broker cần scheduler nếu bật STOMP heartbeat. Trong một `WebSocketMessageBrokerConfigurer` có thể thêm:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Lazy;
import org.springframework.scheduling.TaskScheduler;

// Các thành viên trong class cấu hình (fragment):
private TaskScheduler messageBrokerTaskScheduler;

@Autowired
void setMessageBrokerTaskScheduler(@Lazy TaskScheduler scheduler) {
    this.messageBrokerTaskScheduler = scheduler;
}

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue")
            .setTaskScheduler(messageBrokerTaskScheduler)
            .setHeartbeatValue(new long[] {10_000, 10_000});
}
```

Phải **thay thế** phương thức `configureMessageBroker` cũ, không dán thêm phương thức override trùng tên. Spring WebSocket configuration có thể tạo scheduler phù hợp; `@Lazy` giúp tránh dependency cycle khi configurer inject scheduler. Mảng heartbeat tính bằng mili-giây; client và broker vẫn phải thương lượng header `heart-beat` khi STOMP CONNECT/CONNECTED. Heartbeat chỉ phát hiện sự sống của kết nối, không thêm khả năng clustering/persistence.

## 4. Điều gì xảy ra khi scale simple broker lên nhiều pods?

Giả sử có hai Spring instances A và B phía sau load balancer:

```text
                     Load balancer
                    /             \
Client X ──WebSocket─► Spring A   Spring B ◄─WebSocket── Client Y
                         │           │
                   SimpleBroker A  SimpleBroker B
                   SUB /topic/live SUB /topic/live
                         │           │
REST request → Spring A   │           │
         publish /topic/live           │
                         ▼           (không nhận)
                      Client X
```

Hai simple brokers **không chia sẻ RAM**. REST call đi đến A có thể publish đến những sessions đang subscribe trên A; Y nằm ở B sẽ không tự nhận cùng message. Một WebSocket connection được gắn với một instance trong suốt vòng đời; **sticky sessions không biến hai simple brokers thành một broker cluster**.

Hậu quả vận hành:

- Scale từ một lên nhiều replicas có thể làm notification đến không đầy đủ nếu nghiệp vụ cần fan-out across nodes.
- Một user mở hai thiết bị có thể được load balancing đến hai nodes; gửi tới user đó từ một node cần giải quyết user destination giữa nodes.
- Rolling restart làm WebSocket connections của node cũ đóng; client phải tự reconnect và subscribe lại, kể cả khi có external broker.
- Nếu thêm một event bus tự viết để synchronize nodes, phải xét duplicate, ordering, retries, security và loop suppression. Đó là kiến trúc riêng, không phải hành vi mặc định của simple broker.

**Khi nào simple broker vẫn hợp lý?** Khi chỉ một Spring node hoặc các node được partition có chủ đích và không cần gửi qua nhau, khi business tolerates best-effort notifications và client có đường tải lại trạng thái nguồn từ REST/database.

## 5. STOMP broker relay: các kết nối và vai trò của external broker

`registry.enableStompBrokerRelay("/topic", "/queue")` cấu hình Spring chuyển tiếp message đến một broker STOMP/TCP bên ngoài. Browser/client vẫn kết nối tới WebSocket endpoint của Spring; Spring tiếp tục quản lý handshake, security, STOMP frame decoding và `@MessageMapping`. Broker ngoài chịu trách nhiệm phân phối messages giữa các publishers/subscribers.

```text
WebSocket client 1 ─► Spring A ── STOMP/TCP relay client connection ─┐
                                                                   │
WebSocket client 2 ─► Spring B ── STOMP/TCP relay client connection ─┤
                                                                   ▼
                                                       External STOMP Broker
                                               RabbitMQ STOMP / ActiveMQ / ...
                                                                   ▲
REST publisher ───────► Spring A ── STOMP/TCP system connection ────┘
                                                                   │
             Broker gửi MESSAGE về relay TCP session phù hợp ───────┘
                        → Spring A / Spring B → WebSocket clients
```

### 5.1 Hai kiểu TCP connection

| Kết nối | Số lượng điển hình | Công dụng |
| --- | --- | --- |
| **Client relay connection** | Một TCP connection **cho mỗi** WebSocket/STOMP client session | Truyền `CONNECT`, `SUBSCRIBE`, `SEND` và nhận broker response cho session đó |
| **System connection** | Một connection dùng chung **mỗi Spring relay instance** | App gửi những messages không gắn với client cụ thể, ví dụ phát từ REST/cron/service code |

Theo tài liệu Spring, **system connection chỉ dùng để gửi message bắt nguồn từ ứng dụng**, không phải một channel nhận broadcast cho mọi user. Do đó, 10.000 WebSocket sessions có thể tạo số lượng TCP connections lớn tới broker. Bạn phải đánh giá giới hạn kết nối, file descriptors, memory, heartbeats và network trên broker.

### 5.2 Cấu hình relay, credentials và virtual host

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class RelayConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.org");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");

        registry.enableStompBrokerRelay("/topic", "/queue")
                .setRelayHost("broker.internal")
                .setRelayPort(61613)
                .setVirtualHost("realtime")
                .setSystemLogin("spring-system")
                .setSystemPasscode("set-through-secret-manager")
                .setClientLogin("spring-clients")
                .setClientPasscode("set-through-secret-manager");
    }
}
```

Đây là **fragment cấu hình tham khảo**, không dùng credentials literal trong production. Chúng phải đến từ secret manager, environment/config và phải thuộc accounts có quyền hạn tối thiểu. Broker cần mở đúng **STOMP TCP listener**; ví dụ cổng `61613` là port phổ biến cho STOMP, không phải mặc định của tất cả broker. Port AMQP RabbitMQ `5672` không có nghĩa là port STOMP.

Nếu broker đặt sau TLS, phải cấu hình transport từ **Spring tới broker** cho TLS; `wss://` chỉ mã hóa **browser ↔ Spring**, không tự mã hóa relay TCP.

**Credentials khác nhau ở hai tầng:**

- End user được xác thực ở Spring khi WebSocket handshake/STOMP CONNECT và bị kiểm soát quyền `SEND`/`SUBSCRIBE`.
- STOMP relay thay `login`/`passcode` gửi tới broker bằng các giá trị `clientLogin`/`clientPasscode`, hoặc `systemLogin`/`systemPasscode` với system connection. Broker username **không tự phản ánh user principal thật**.
- Broker xác thực service accounts và thực thi policy broker resources. Cần tiếp tục authorization theo STOMP destinations phía Spring.

Cách cấu hình tính năng có thể thay đổi giữa phiên bản Spring; hãy dùng javadoc đúng BOM đang chạy. Khi chuyển từ simple sang relay, **thay** `enableSimpleBroker` bằng `enableStompBrokerRelay` cho cùng các destination prefixes, tránh chạy hai broker handlers trùng vùng định tuyến.

### 5.3 Kết nối broker bị ngắt

Relay theo dõi system connection và có cơ chế reconnect. Spring phát `BrokerAvailabilityEvent` khi broker có thể/không thể nhận message từ góc nhìn hệ thống:

```java
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;
import org.springframework.stereotype.Component;

@Component
class BrokerStatusListener {
    @EventListener
    void onBrokerChanged(BrokerAvailabilityEvent event) {
        System.out.println("broker available=" + event.isBrokerAvailable());
    }
}
```

Đây là **fragment bean Spring**, không phải chương trình CLI. Event này thích hợp cho monitoring và producer có thể hoãn gửi khi broker xuống. Nó **không xác nhận** rằng từng client TCP session đang hoạt động hoặc message đã được user nhận.

Khi broker restart/network rớt, các relay client connections có thể mất; clients cần **WebSocket/STOMP reconnect, CONNECT, SUBSCRIBE lại**. Không giả định reconnect của system connection tự khôi phục các client subscriptions. Nếu app phải không mất bất kỳ business event nào, hãy dùng durable storage/outbox/queue và xác nhận giao nhận phù hợp thay vì chỉ gọi `convertAndSend(...)`.

## 6. Broker ngoài có nghĩa vụ gì và không hứa điều gì?

Một broker STOMP đầy đủ có thể hỗ trợ ACK/NACK, receipts, topic/queue, persistence, failover, durable subscription, TTL, dead-lettering và clustering. Tuy nhiên khả năng thực tế phụ thuộc **broker, plugin STOMP, cấu hình topology, destination mapping và client headers**.

| Tính chất | Simple broker | Broker relay + external broker |
| --- | --- | --- |
| Subscription location | RAM trong Spring instance | External broker routing/state |
| Cross-node broadcast | Không tự có | Có thể khi tất cả nodes truy cập cùng broker topology |
| Message khi client offline | Không tự lưu | Chỉ khi thiết kế durable queue/topic/replay đúng |
| STOMP ACK/RECEIPT | Không hỗ trợ đầy đủ | Phụ thuộc broker, mode và plugin STOMP |
| Queue delivery cạnh tranh | Prefix `/queue` không bảo đảm | Phụ thuộc broker destination semantics |
| Broker clustering | Không | Có thể nếu broker hỗ trợ và cấu hình |
| Quản trị | Ít phụ thuộc | Cần vận hành broker, credentials, network, HA |
| Chi phí TCP connections | Chủ yếu WebSocket client ↔ Spring | Cộng thêm relay TCP connections tới broker |
| Restart Spring | Mất WebSocket sessions/subscriptions | WebSocket sessions vẫn cần reconnect |
| Exactly-once delivery | Không | Không tự có; cần protocol và idempotent consumer |

**Ví dụ nguy hiểm khi migration:** ứng dụng cũ dùng `/queue/jobs` trên simple broker như tên của một kênh broadcast. Sau khi chuyển sang RabbitMQ/ActiveMQ, external broker có thể định tuyến `/queue/jobs` như hàng đợi với competing consumers. Đây là thay đổi semantics lớn. Phải kiểm tra routing/bindings/ack policy qua integration tests thực tế.

**Một lệnh publish không phải delivery receipt.** `SimpMessagingTemplate.convertAndSend(...)` đưa message tới Spring broker channel. Broker nhận có thể chưa persist, client có thể vừa disconnect, hoặc thiết bị có thể chưa ACK. Nếu yêu cầu delivery guarantees, cần xác định “giao thành công” ở tầng nào và đưa vào thiết kế broker confirmations, ACK, idempotency key, outbox và retry.

## 7. User destination khi chạy nhiều Spring nodes

Spring cho phép client đăng ký `/user/queue/notifications`; Spring `UserDestinationMessageHandler` dịch destination logic thành destination riêng theo session. Server có thể gửi message với:

```java
// Fragment bên trong service đã inject SimpMessagingTemplate messagingTemplate.
messagingTemplate.convertAndSendToUser(
        "alice", "/queue/notifications", "You've got mail");
```

Nếu user `alice` có session trên node B nhưng event được xử lý ở node A, node A có thể không resolve được user destination nếu chỉ thấy registry cục bộ. Spring hỗ trợ settings để phối hợp nhiều nodes:

- `setUserDestinationBroadcast(...)`: broadcast những user destinations không resolve được, để nodes khác thử tìm session phù hợp.
- `setUserRegistryBroadcast(...)`: chia sẻ thông tin user sessions giữa app instances qua broker destination.

Ví dụ **chỉ khi có relay/external broker cùng topology phù hợp**:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.setUserDestinationPrefix("/user");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.internal")
            .setRelayPort(61613);

    registry.setUserDestinationBroadcast("/topic/unresolved-user");
    registry.setUserRegistryBroadcast("/topic/user-registry");
}
```

Đây là **fragment cấu hình**: host/credentials/SSL không được thể hiện đầy đủ. Các destination dùng để broadcast metadata/registry là đường phối hợp **nội bộ**, không cho client bất kỳ `SEND` vào hoặc `SUBSCRIBE` đọc; enforce authorization.

Khi các user destinations giải thành queues riêng trên broker ngoài, chú ý cleanup inactive queues, TTL hoặc auto-delete theo sản phẩm. Một số broker tạo queue tạm cho mỗi WebSocket session; reconnect hàng loạt không được để tích lũy hàng triệu tài nguyên cũ.

## 8. Ra quyết định và lộ trình mở rộng

### 8.1 Bảng quyết định

| Nhu cầu | Lựa chọn gợi ý | Vì sao? |
| --- | --- | --- |
| Học Spring STOMP, một JVM | Simple broker | Gọn, không phải vận hành broker |
| Dashboard đơn node, notification best-effort | Simple broker + REST snapshot/resync | Không cần durable fan-out |
| Nhiều Spring pods cùng broadcast tới một topic | External STOMP broker/relay hoặc message bus chung | Tránh subscriptions bị chia theo node |
| Cần gửi notification cho offline user | Database/outbox và replay; có thể dùng external broker | WebSocket subscription không phải durable inbox |
| Cần ACK, redelivery, dead-letter, retry | Messaging broker đủ tính năng + thiết kế ACK | Simple broker không phải reliable work queue |
| Hàng chục nghìn kết nối và fan-out lớn | Benchmark websocket gateway + relay + broker resources | Relay tạo TCP connections và broker load |
| Cần per-user authorization và privacy | Spring Security trên handshake và STOMP destinations | Loại broker không thay được phân quyền |
| Cần global order | Thiết kế partition/sequence/dedup | Spring outbound order flag chỉ per-session |

Đừng chọn broker chỉ theo số lượng nodes. Hãy định lượng **concurrent WebSocket sessions**, messages/sec, fan-out, payload size, acceptable latency, uptime, RPO/RTO, độ tin cậy khi client offline, thứ tự, chi phí vận hành và security boundaries.

### 8.2 Các bước chuyển simple → relay

1. Liệt kê toàn bộ broker prefixes, topics, queues, publishers/subscribers, user destinations; xác minh semantics hiện tại.
2. Chọn broker có STOMP listener và routing đúng nhu cầu, tạo accounts/permissions, cấu hình TLS/HA, metrics.
3. Bảo toàn WebSocket endpoint và application prefix `/app` khi có thể. Chuyển **một** broker handler từ simple sang relay; tránh trùng prefixes.
4. Test với ít nhất **hai Spring nodes** và các WebSocket clients nối các nodes khác nhau; publish từ từng node và kiểm tra recipients.
5. Kiểm tra user destinations khi user đăng nhập nhiều sessions/nodes, registry broadcasts và cleanup queues.
6. Thử các lỗi: broker restart, DNS/TLS error, mất một node, client reconnect, duplicate/out-of-order messages, slow consumer.
7. Theo dõi backlog, message latency, broker TCP connections, authorization failures, Spring outbound buffer và chuẩn bị rollback.

Bản thân Spring app vẫn xử lý business logic trong `@MessageMapping`, và bạn nên đảm bảo HTTP/WebSocket entrypoints không đổi ngoài các semantics được phê duyệt. External broker **không tự thay thế** database business, REST query hay durable outbox.

## 9. Ví dụ Java 17+ chạy được với simple broker

Ví dụ gồm Spring Boot server phát thông báo lên `/topic/events` và Java JDK WebSocket client gửi trực tiếp STOMP CONNECT/SUBSCRIBE. Không cần Internet khi **chạy HTTP requests nội bộ**; lần build đầu có thể cần tải dependency từ Maven. Đây là một demo subscription đơn node, để hiểu trước khi dùng relay.

### 9.1 Cấu trúc và Gradle

```text
broker-demo/
├── build.gradle
└── src/main/java/demo/
    ├── BrokerDemoApplication.java
    └── StompDemoClient.java
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
}

springBoot {
    mainClass = 'demo.BrokerDemoApplication'
}

tasks.register('runStompClient', JavaExec) {
    group = 'application'
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'demo.StompDemoClient'
}
```

Dùng Gradle đã cài hoặc Gradle Wrapper phù hợp với Spring Boot. Source file thứ nhất chứa server, configuration và REST publisher; file thứ hai chứa client. Có thể sử dụng Spring Boot Gradle plugin theo BOM của project thay vì hard-code version khi tích hợp vào hệ thống sẵn có.

### 9.2 Spring Boot server

`src/main/java/demo/BrokerDemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@SpringBootApplication
public class BrokerDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BrokerDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSocketMessageBroker
class BrokerConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOriginPatterns("http://localhost:*");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}

@RestController
class EventPublisher {
    private final SimpMessagingTemplate messagingTemplate;

    EventPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @PostMapping(
            path = "/api/events",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    String publish(@RequestBody String body) {
        messagingTemplate.convertAndSend("/topic/events", body);
        return "sent: " + body;
    }
}
```

`@EnableWebSocketMessageBroker` tạo messaging infrastructure. REST controller không trực tiếp giữ danh sách WebSocket sessions mà dùng `SimpMessagingTemplate`. Response `sent: hello` có nghĩa HTTP method được xử lý tới dòng return, **không bảo đảm** tất cả subscribers đã nhận. API chưa xác thực và chỉ phù hợp local demo.

### 9.3 JDK WebSocket client gửi STOMP frames

`src/main/java/demo/StompDemoClient.java`:

```java
package demo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public final class StompDemoClient {
    private static final class Receiver implements WebSocket.Listener {
        final BlockingQueue<String> frames = new LinkedBlockingQueue<>();
        private final StringBuilder pending = new StringBuilder();

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket socket, CharSequence chunk, boolean last) {
            synchronized (pending) {
                pending.append(chunk);
                int end;
                while ((end = pending.indexOf("\u0000")) >= 0) {
                    String frame = pending.substring(0, end);
                    pending.delete(0, end + 1);
                    frame = frame.replaceFirst("^[\\r\\n]+", "");
                    if (!frame.isEmpty()) {
                        frames.offer(frame);
                    }
                }
            }
            socket.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            frames.offer("ERROR\n\n" + error.getMessage());
        }
    }

    public static void main(String[] args) throws Exception {
        Receiver receiver = new Receiver();
        WebSocket socket = HttpClient.newHttpClient()
                .newWebSocketBuilder()
                .subprotocols("v12.stomp")
                .buildAsync(URI.create("ws://localhost:8080/ws"), receiver)
                .get(10, TimeUnit.SECONDS);

        try {
            socket.sendText(
                    "CONNECT\naccept-version:1.2\nhost:localhost"
                    + "\nheart-beat:0,0\n\n\u0000", true).join();

            String connected = receiver.frames.poll(10, TimeUnit.SECONDS);
            if (connected == null || !connected.startsWith("CONNECTED")) {
                throw new IllegalStateException(
                        "Expected CONNECTED: " + connected);
            }
            System.out.println("CONNECTED");

            socket.sendText(
                    "SUBSCRIBE\nid:subscription-1"
                    + "\ndestination:/topic/events"
                    + "\nack:auto\n\n\u0000", true).join();

            System.out.println("SUBSCRIBED /topic/events");
            System.out.println("WAITING FOR MESSAGE");

            String message = receiver.frames.poll(60, TimeUnit.SECONDS);
            if (message == null || !message.startsWith("MESSAGE")) {
                throw new IllegalStateException(
                        "Expected MESSAGE: " + message);
            }

            int separator = message.indexOf("\n\n");
            if (separator < 0) {
                throw new IllegalStateException("Missing frame separator");
            }
            System.out.println("MESSAGE: " + message.substring(separator + 2));

            socket.sendText("DISCONNECT\n\n\u0000", true).join();
            socket.sendClose(WebSocket.NORMAL_CLOSURE, "done").join();
        } finally {
            socket.abort();
        }
    }
}
```

Ở đây JDK `WebSocket` chỉ triển khai WebSocket frames, **không có STOMP client library**; chúng ta tự gửi STOMP CONNECT/SUBSCRIBE và tìm byte NUL để tách frames. Việc ghép fragments dùng `StringBuilder` cho trường hợp một STOMP frame bị tách ở WebSocket transport. Demo tắt STOMP heartbeat, giới hạn một message nhận và không xử lý toàn bộ tính năng STOMP như `content-length` chứa byte NUL; production nên dùng một STOMP client library phù hợp.

**Lưu ý:** `.subprotocols("v12.stomp")` ở HTTP/WebSocket handshake khác hoàn toàn frame STOMP `CONNECT` gửi sau khi socket OPEN. Server Spring tự thực hiện negotiation nếu có hỗ trợ STOMP 1.2.

### 9.4 Chạy với ba terminal

Terminal 1 — chạy server, đợi ứng dụng sẵn sàng port 8080:

```bash
gradle bootRun
```

Terminal 2 — client kết nối và subscribe:

```bash
gradle runStompClient
```

Kết quả do chương trình client tự in **trước khi message đến**:

```text
CONNECTED
SUBSCRIBED /topic/events
WAITING FOR MESSAGE
```

Terminal 3 — sau khi client đã in `WAITING FOR MESSAGE`, gửi HTTP POST:

```bash
curl -X POST http://localhost:8080/api/events -H "Content-Type: text/plain" --data-binary "hello"
```

Nếu dùng Windows PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/events' -ContentType 'text/plain' -Body 'hello'
```

REST response body:

```text
sent: hello
```

Client terminal 2 tiếp tục in:

```text
MESSAGE: hello
```

Spring, Gradle, Tomcat có thể in log khác; các dòng trên là **chính xác phần mà ứng dụng demo tự in** nếu chạy theo thứ tự, không bị timeout và server chạy port 8080. Nếu port đổi, phải đổi URI trong Java client. Chương trình demo không dùng `@MessageMapping` vì muốn tập trung vào đường **application publisher → broker → subscriber**. Bạn có thể mở hai client trước khi gửi POST để thấy fan-out trên một Spring instance.

### 9.5 Thử đổi broker mà giữ endpoint

Khi triển khai broker ngoài đã bật STOMP/TCP listener, trong `BrokerConfig.configureMessageBroker` thay:

```java
registry.enableSimpleBroker("/topic", "/queue");
```

bằng cấu hình tương ứng:

```java
registry.enableStompBrokerRelay("/topic", "/queue")
        .setRelayHost("127.0.0.1")
        .setRelayPort(61613)
        .setSystemLogin("configured-system-user")
        .setSystemPasscode("configured-secret")
        .setClientLogin("configured-client-user")
        .setClientPasscode("configured-secret");
```

Đây là **cấu hình minh họa**, không tự chạy nếu chưa có broker hoặc chưa cấp credentials đúng; production đọc secrets từ environment/secret manager, cấu hình TLS. Khi external broker hiểu `/topic/events` và Spring relay hoạt động, client vẫn subscribe cùng endpoint `/ws`. Để **kiểm chứng scale**, khởi tạo **hai Spring instances** ở các ports khác nhau, hai clients trỏ vào từng instance, rồi publish từ chỉ một node; message phải tới các clients theo topology broker đã cấu hình. Một demo một node chưa chứng minh cross-node fan-out.

## 10. Thứ tự, backpressure và vận hành

### 10.1 Thứ tự không tự được bảo đảm toàn hệ thống

Spring inbound/outbound channels sử dụng executor. Khi có nhiều threads, messages có thể được xử lý/đẩy ra không theo thứ tự nhận vào trên **cùng một session** nếu không cấu hình. Spring có tùy chọn:

```java
// Các fragment đặt vào một WebSocketMessageBrokerConfigurer:
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws");
    registry.setPreserveReceiveOrder(true);
}

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic");
    registry.setPreservePublishOrder(true);
}
```

`setPreserveReceiveOrder(true)` giúp xử lý inbound messages cho từng session theo thứ tự nhận. `setPreservePublishOrder(true)` bảo đảm thứ tự publish ra outbound channel cho từng session. Cả hai có overhead và **không bảo đảm global ordering** qua mọi nodes, topics, broker queues hay reconnects. Với dữ liệu bắt buộc đúng thứ tự, cần sequence number, entity version, stable partitioning/ordering key và xử lý duplicate/out-of-order trên client.

### 10.2 Slow consumers, send buffer và message size

Client đọc chậm làm WebSocket outbound buffers tăng, khiến server chạm giới hạn memory/latency. Một cấu hình phù hợp có thể là:

```java
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

// Fragment method của WebSocketMessageBrokerConfigurer:
@Override
public void configureWebSocketTransport(
        WebSocketTransportRegistration registry) {
    registry.setMessageSizeLimit(128 * 1024);
    registry.setSendBufferSizeLimit(512 * 1024);
    registry.setSendTimeLimit(15_000);
}
```

Thông số message/buffer tính theo byte và send time theo mili-giây. Những giới hạn này điều chỉnh **transport giữa Spring và client**, không điều chỉnh capacity external broker. Khi cần hỗ trợ large payloads, phải cân nhắc phương án REST/object storage cho dữ liệu lớn, gửi WebSocket thông báo nhỏ.

### 10.3 Metrics và lỗi có thể gặp

| Dấu hiệu | Khả năng | Cách kiểm tra |
| --- | --- | --- |
| Một số clients ở node khác không nhận | Simple brokers phân tán theo pods | Gắn logs node/session ID, kiểm tra broker topology |
| STOMP connected nhưng subscribe không có message | Sai prefix/destination hoặc gửi trước khi subscribe | Kiểm tra frames, routing, authorization |
| Relay báo broker unavailable | STOMP listener, DNS/TLS/firewall hoặc auth lỗi | BrokerAvailabilityEvent, TCP/broker logs |
| Broker quá tải với nhiều clients | Relay TCP per session, broker limits | Active connections, memory, FD, CPU |
| Không tìm thấy user trên node hiện tại | User registry/resolve phân tán | Cấu hình broadcasts, test multi-node |
| Client nhận chậm/đứt | Send buffer, proxy timeout, heartbeat | Outbound queue, close codes, network |
| Duplicate/lost messages sau retry/reconnect | Không có end-to-end idempotency | Event IDs, outbox/replay, ack policy |
| Trật thứ tự UI updates | Concurrent channels, broker/order semantics | Sequence numbers, per-session order options |

**Giám sát tối thiểu:** active WebSocket sessions, subscriptions, inbound/outbound executor queues, message latency, errors/close codes, outbound send buffer, broker TCP connections, broker memory/disk/backlog, reconnect rate, heartbeat misses, publication/delivery metrics theo yêu cầu SLA. Giám sát `SimpUserRegistry` không tự chứng minh client đã xử lý event.

### 10.4 Giải pháp bền vững cho business events

Với notification chỉ để UI biết “dữ liệu mới xuất hiện”, pattern phổ biến là:

```text
Business transaction
     │
     ├─ persist DB + event/outbox (durable)
     │
     ▼
Reliable delivery/event processing
     │
     ▼
Realtime notification via WebSocket/STOMP
     │
     ▼
Client gọi REST/query để tải snapshot mới nhất
```

Khi client rớt mạng, nó reconnect/re-subscribe rồi tải snapshot hoặc các events theo cursor; không trông chờ WebSocket giữ messages offline. Điều này đặc biệt quan trọng với trạng thái tiền, đơn hàng, công việc có hậu quả lâu dài.

## 11. Bảo mật và các lỗi thường gặp khi migration

- **Không coi broker credential là user authentication:** relay dùng credentials đã cấu hình để nối broker. Phải xác thực user tại HTTP/WebSocket hoặc STOMP CONNECT và authorize SEND/SUBSCRIBE theo từng destination.
- **Không mở public internal user-registry topics:** destinations dùng bởi `setUserDestinationBroadcast`/`setUserRegistryBroadcast` phải được bảo vệ.
- **Không tin rằng sticky sessions giải quyết cross-node fan-out:** subscriptions vẫn trong simple broker RAM riêng.
- **Không giả định `/queue` giữ nghĩa giống nhau:** full broker thường có queue semantics khác simple broker; kiểm tra destination mappings.
- **Không gửi secret dưới dạng STOMP header rồi ghi full frame log:** bảo vệ token, cookies, user details; TLS cho cả client→Spring và Spring→broker.
- **Không dùng simple broker cho ACK/durable workflows:** retry/ack/transaction cần broker và contract được thiết kế đúng.
- **Không coi một lần `convertAndSend` là exactly-once:** có thể mất/dặp do retry/reconnect hoặc client offline; đưa message ID/idempotency vào protocol.
- **Không quên reconnect/resubscribe khi node/broker restart:** WebSocket OPEN sau reconnect chưa có nghĩa subscriptions đã khôi phục.
- **Không đánh đồng STOMP heartbeat với TCP keepalive/WebSocket Ping/Pong:** đây là các tầng khác nhau và timeout phải phù hợp proxy.
- **Không để send buffer/broker connections không giới hạn:** định cỡ theo tải, đặt limits, slow-consumer policy và giám sát broker/node.
- **Không trộn relay và simple cho cùng destination prefixes:** sẽ khó dự đoán handler nào nhận message, hoặc gây phát trùng.
- **Không triển khai broker ngoài trước khi kiểm tra listener STOMP:** RabbitMQ plugin/tài nguyên, broker account, destination permissions và network/TLS đều phải sẵn sàng.

## 12. Câu hỏi kiểm tra hiểu bài

**1. Hai Spring pods đều bật simple broker `/topic/news`. POST publish vào pod A. User ở pod B có tự nhận không?**

Không. Simple broker trong pod A chỉ biết subscribers hiện kết nối với pod A. Nếu business cần toàn hệ thống, phải có broker/bus chung.

**2. `/queue/jobs` trên simple broker có chắc chắn chỉ một trong hai subscribers nhận mỗi job không?**

Không. Với simple broker, `/queue` chỉ là prefix chuỗi; competing-consumer queue semantics không được bảo đảm.

**3. Relay kết nối tới RabbitMQ có tự làm mọi message durable không?**

Không. Phụ thuộc queue/exchange/destination mapping, broker settings, headers, publisher/consumer confirmation và idempotency của ứng dụng.

**4. Relay dùng một connection TCP cho mọi WebSocket clients đúng không?**

Sai. Nó dùng riêng client relay TCP connection cho mỗi STOMP client session và system connection cho message của ứng dụng.

**5. `BrokerAvailabilityEvent` bảo đảm mọi client nhận message gần nhất chưa?**

Chưa. Nó phản ánh broker system availability; không có end-to-end client receipt tự động.

**6. Bật `setPreservePublishOrder(true)` có tạo global exactly-once delivery không?**

Không. Nó xử lý outbound publish order trong phạm vi một client session, có overhead; vẫn cần sequence/dedup và broker contract.

**7. Có một user kết nối hai Spring instances khác nhau; vì sao `/user/queue/notifications` cần thiết kế thêm?**

User destination phải được resolve đúng session. Dùng user registry/broadcast qua broker và test multi-node nếu event có thể đến một node khác node giữ session.

**8. Khi client offline 10 phút, cách khôi phục notification quan trọng là gì?**

Lưu dữ liệu nghiệp vụ bền vững, reconnect/resubscribe, và tải snapshot/replay theo cursor. Simple broker không lưu durable offline messages.

## Tài liệu tham khảo chính thức

- [Spring Framework — STOMP Enable](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework — Connecting to Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Spring Framework — Message Flow](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework — Message Order](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html)
- [Spring Framework — Monitoring](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html)

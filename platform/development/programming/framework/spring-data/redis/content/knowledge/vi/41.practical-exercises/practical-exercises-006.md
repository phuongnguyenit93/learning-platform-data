# Gửi thông báo thời gian thực bằng Pub/Sub

**Redis Pub/Sub** là cơ chế phân phối thông điệp theo mô hình *publish–subscribe*: publisher gửi message vào một **channel**, Redis chuyển message đó tới các subscriber đang đăng ký channel vào thời điểm phát. Trong **Spring Data Redis**, ta có thể dùng `StringRedisTemplate.convertAndSend(...)` để publish và `RedisMessageListenerContainer` kết hợp `MessageListener` để subscribe.

Bài thực hành này xây dựng luồng **Spring Boot → Redis Pub/Sub → Spring listener → Server-Sent Events (SSE) → trình duyệt**. Một notification được phát ở instance ứng dụng A có thể xuất hiện gần như tức thời tại các browser đang kết nối tới cả A và B, nhờ Redis làm *backplane* phân phối sự kiện giữa các ứng dụng.

**Giới hạn cốt lõi:** Redis Pub/Sub là **best-effort/at-most-once**; message **không được lưu để replay** cho subscriber offline. Một response thành công từ `PUBLISH` không đồng nghĩa user đã thấy thông báo trên màn hình. Nếu cần thông báo có lịch sử, ACK, retry và khả năng phục hồi, phải kết hợp data store bền vững hoặc dùng Redis Streams/message broker thích hợp.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích channel, publisher, subscriber và delivery semantics của Redis Pub/Sub.
2. Chạy thử `SUBSCRIBE`/`PUBLISH` bằng Redis CLI.
3. Tạo ứng dụng Spring Boot 3.x/Java 17 với Redis auto-configuration.
4. Định nghĩa JSON notification có `id`, `type`, `text`, `createdAt`.
5. Tạo HTTP endpoint `POST /api/notifications` phát message tới Redis.
6. Đăng ký listener bằng `RedisMessageListenerContainer` và `ChannelTopic`.
7. Đẩy message tới browser qua `SseEmitter` và `EventSource`.
8. Kiểm chứng multi-instance broadcast, ngắt kết nối, subscriber offline, reconnect.
9. Hiểu ACL channel permissions, security, serialization, giới hạn executor và cách đo hiệu năng.
10. Quyết định khi nào Pub/Sub đủ, khi nào cần lịch sử/outbox/Redis Streams.

Trong phạm vi thực hành, các thông báo là **thông báo công khai**, không chứa thông tin riêng tư. Không dùng nguyên mẫu cho thông báo thanh toán, xác thực hoặc dữ liệu cá nhân mà chưa bổ sung authorization và persistence.

## 2. Kiến trúc end-to-end

```text
Browser 1             Browser 2           Browser 3
   ^                      ^                   ^
   | SSE                  | SSE               | SSE
   |                      |                   |
   +---------- App A -----+                   App B
                   ^                         ^
                   |                         |
          RedisMessageListenerContainer (mỗi instance)
                   ^                         ^
                    \                       /
                     \                     /
                      Redis Pub/Sub Channel
                          demo:notifications
                                ^
                                |
                        PUBLISH JSON event
                                ^
                                |
                     POST /api/notifications
```

Mỗi Spring Boot instance tạo Redis subscription riêng và giữ một tập các kết nối SSE **cục bộ**. Redis gửi một message tới các connection đang subscribe; từng instance thực hiện fan-out tới browser mình đang phục vụ.

Từ kiến trúc này rút ra bốn kết luận:

- **Redis subscriber connection không phải browser connection.** Một Redis listener của instance A có thể phục vụ hàng trăm SSE clients.
- **Pub/Sub channel không phải Redis key lưu messages.** Không thể `GET` lại message cũ.
- **Không có replay/ACK.** Instance B offline lúc publish sẽ mất thông báo đó.
- **SSE reconnect không tự phục hồi Pub/Sub events đã bỏ lỡ.** Nếu cần bù, phải có lưu trữ lịch sử riêng.

## 3. Pub/Sub ở cấp giao thức Redis

Lệnh cơ bản:

```text
SUBSCRIBE demo:notifications
PUBLISH demo:notifications "Xin chào"
UNSUBSCRIBE demo:notifications
```

Khi publisher gọi `PUBLISH`, Redis phân phối message đến những subscriber đang kết nối phù hợp với channel.

| Thành phần | Vai trò |
|---|---|
| Channel | Tên kênh logic, ví dụ `demo:notifications` |
| Publisher | Client gọi `PUBLISH` |
| Subscriber | Client đã `SUBSCRIBE` hoặc `PSUBSCRIBE` |
| Message | Payload bytes được phân phối, không phải key-value bền vững |
| Connection | Redis subscription tồn tại theo connection |
| Listener | Code Spring xử lý message Redis đẩy tới |

Không nhầm Pub/Sub với Redis Streams. Pub/Sub không có stream ID, consumer group, Pending Entries List, `XACK` hoặc retention. Redis không có cách “đọc lại 10 messages cuối” chỉ từ một Pub/Sub channel.

### Bảo đảm về thứ tự

Redis phân phối messages theo thứ tự trên luồng subscription tương ứng, nhưng thứ tự xử lý **sau Redis** có thể thay đổi khi ứng dụng dùng nhiều threads, hàng đợi fan-out hoặc reconnect. Không lấy một Redis channel làm cam kết thứ tự toàn cục giữa mọi browser và mọi node nếu chưa thiết kế rõ việc tuần tự hóa.

## 4. Nên dùng Pub/Sub cho loại thông báo nào?

| Nhu cầu | Phù hợp? | Giải thích |
|---|---|---|
| Dashboard cập nhật số liệu mới | Có | Khi lỡ message, client có thể tải lại trạng thái |
| Banner thông báo chung không quan trọng | Có | Bỏ lỡ một message được chấp nhận |
| Tín hiệu “cache đã thay đổi” | Có điều kiện | Cần TTL/version/reconciliation để tránh stale mãi |
| Báo “có tin nhắn mới” từ database | Có | Nội dung thật vẫn được lưu trong database |
| Email phải gửi dù worker offline | Không dùng Pub/Sub đơn lẻ | Cần queue bền vững, ACK/retry |
| Giao dịch thanh toán/ghi số dư | Không dùng Pub/Sub làm nguồn sự thật | Cần transaction, idempotency, audit |
| Notification center có lịch sử | Phải bổ sung store | Pub/Sub chỉ làm tín hiệu realtime |
| Phân phối realtime giữa nhiều app instances | Có | Redis làm backplane fan-out |

Câu hỏi lựa chọn hữu ích: **“Nếu subscriber offline 30 giây, có được phép bỏ qua 30 giây thông báo không?”** Nếu câu trả lời là không, Pub/Sub thuần chưa đủ.

## 5. Pub/Sub, Streams, SSE và WebSocket khác nhau thế nào?

| Công nghệ | Chức năng | Hạn chế chính |
|---|---|---|
| Redis Pub/Sub | Phân phối message tức thời giữa server clients | Không lưu/ACK/replay |
| Redis Streams | Lưu event theo ID, có thể dùng consumer group | Phải quản lý retention, ACK, recovery |
| SSE | HTTP push một chiều app → browser | Bản thân không lưu lịch sử |
| WebSocket | Kết nối hai chiều app ↔ browser | Cần quản lý connection, auth, state |
| Polling | Browser lặp lại HTTP GET | Tăng request overhead, cập nhật chậm hơn interval |

Bài này chọn **SSE** vì notification chỉ đi từ server xuống browser. Browser gửi yêu cầu tạo thông báo qua **HTTP POST** riêng. Redis Pub/Sub nằm ở tầng **giữa các Spring instances**, không phải giao thức mà browser trực tiếp sử dụng.

## 6. Chuẩn bị Redis lab

Có thể chạy Redis riêng bằng Docker:

```bash
docker run --rm --name redis-pubsub-lab -p 127.0.0.1:6379:6379 redis:7.4-alpine
```

Tùy hệ điều hành và mạng Docker, cú pháp port binding có thể cần điều chỉnh. Đây là Redis **thử nghiệm local**, không bật authentication/TLS; **không expose Redis lab ra Internet** hoặc dùng nó chứa dữ liệu thật.

Kiểm tra:

```bash
redis-cli -h 127.0.0.1 -p 6379 PING
```

Kỳ vọng `PONG`. Nếu chưa cài Redis CLI trên host:

```bash
docker exec -it redis-pubsub-lab redis-cli
```

Chỉ sử dụng `redis-cli` kết nối Redis server lab mà mình quản lý.

## 7. Thử Pub/Sub thủ công trước khi viết Java

Ở terminal A:

```bash
redis-cli -h 127.0.0.1 -p 6379 SUBSCRIBE demo:notifications
```

Giữ A mở. Ở terminal B:

```bash
redis-cli -h 127.0.0.1 -p 6379 PUBLISH demo:notifications "Hello Redis"
```

Terminal A sẽ thấy một message chứa `Hello Redis`.

Để thử tính chất **không replay**:

1. Dừng subscriber ở A.
2. Publish thêm hai messages ở B.
3. Khởi động lại subscriber A.
4. Quan sát hai messages phát lúc A offline **không tự xuất hiện**.
5. Publish một message mới khi A đã subscribe, A lại nhận.

Đây là hành vi thiết kế của Redis Pub/Sub, không phải lỗi client.

## 8. Dependencies Spring Boot

Với project Spring Boot đã quản lý plugin/BOM, khai báo Gradle:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.boot:spring-boot-starter-validation")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:testcontainers")
}
```

- Spring Web MVC cung cấp REST Controller và `SseEmitter`.
- Spring Data Redis tích hợp RedisTemplate, Lettuce và Redis listener container.
- Validation xử lý `@NotBlank`, `@Size`.
- Testcontainers giúp chạy Redis thật trong integration tests.

Ví dụ sử dụng Java 17 và Spring Boot 3.x. Dự án dùng Maven/WebFlux hoặc Spring Boot version khác cần điều chỉnh API và dependency metadata.

## 9. Bố cục source files

```text
src/main/java/com/example/notifications/
  NotificationsApplication.java
  NotificationEvent.java
  NotificationRequest.java
  PublishReceipt.java
  NotificationPublisher.java
  RedisPubSubConfiguration.java
  RedisNotificationSubscriber.java
  SseNotificationHub.java
  NotificationController.java

src/main/resources/
  application.yml
  static/index.html
```

Các thành phần được phân chia để **Redis subscriber không phụ thuộc trực tiếp vào HTTP Controller**, và publisher không cần biết browser đang ở instance nào.

## 10. Cấu hình Spring Redis và channel

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s

app:
  notifications:
    channel: demo:notifications
```

`app.notifications.channel` là cấu hình thuộc ứng dụng, không phải property có sẵn của Redis.

Với môi trường thật:

- Redis endpoint phải ở private network.
- Username/password lưu trong secret manager hoặc cấu hình được bảo vệ.
- Bật TLS và kiểm tra certificates nếu Redis endpoint yêu cầu.
- Với Sentinel/Cluster, dùng configuration tương ứng thay vì cố định endpoint primary cũ.
- Publisher và subscriber **phải dùng đúng cùng channel**.

Một lỗi thường gặp là publisher dùng `demo:notifications` nhưng subscriber dùng `demo:notification`. Redis không báo sai chính tả channel: nó chỉ không có recipient phù hợp.

## 11. Entry point và heartbeat scheduling

`NotificationsApplication.java`:

```java
package com.example.notifications;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class NotificationsApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotificationsApplication.class, args);
    }
}
```

`@EnableScheduling` dùng cho heartbeat SSE trong phần sau. Nó không cần cho Redis Pub/Sub tự thân.

Với starter Spring Data Redis, Spring Boot thường tự tạo `StringRedisTemplate`/`RedisConnectionFactory`. Không cần viết Lettuce factory thủ công cho ví dụ standalone đơn giản.

## 12. Hợp đồng JSON thông báo

Mỗi message có schema rõ ràng:

```json
{
  "id": "b16e7484-142b-4e41-a219-fb6170d6d74a",
  "type": "ANNOUNCEMENT",
  "text": "Lịch bảo trì vừa được cập nhật",
  "createdAt": "2026-11-13T03:00:00Z"
}
```

`NotificationEvent.java`:

```java
package com.example.notifications;

import java.time.Instant;

public record NotificationEvent(
        String id,
        String type,
        String text,
        Instant createdAt) {
}
```

- `id` giúp correlation/dedup ở cấp ứng dụng.
- `type` cho phép frontend phân loại thông báo.
- `text` là dữ liệu do người dùng tạo nên phải được kiểm tra/hiển thị an toàn.
- `createdAt` là thời gian publisher tạo event, **không phải** lúc browser nhận.

Record Java 17 có thể serialize/deserialize qua `ObjectMapper` của Spring Boot. Nếu ứng dụng dùng Jackson configuration tùy chỉnh, cần đảm bảo module hỗ trợ `Instant` và thống nhất định dạng giữa các instances.

## 13. Validate HTTP request

`NotificationRequest.java`:

```java
package com.example.notifications;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record NotificationRequest(
        @NotBlank
        @Size(max = 500)
        String text) {
}
```

Trong bài lab, client chỉ gửi nội dung. **Client không được tự chọn Redis channel hoặc loại thông báo nhạy cảm.**

`@NotBlank` và `@Size` là lớp validation tối thiểu; production còn cần authentication, authorization, rate limiting, giới hạn byte payload, chống spam và xác định nội dung nào được broadcast.

## 14. PublishReceipt không phải xác nhận đã giao tới người dùng

`PublishReceipt.java`:

```java
package com.example.notifications;

import java.time.Instant;

public record PublishReceipt(
        String eventId,
        Instant createdAt,
        long redisSubscriberConnections) {
}
```

Redis `PUBLISH` trả về thông tin số subscriber clients ở tầng Redis. Trường `redisSubscriberConnections` minh họa điều đó, nhưng **không phải số browser đang mở SSE, không phải số người dùng đã đọc** và không phải delivery guarantee.

Trong API thật có thể không expose trường này cho user, chỉ ghi metric nội bộ.

## 15. Viết publisher bằng StringRedisTemplate

`NotificationPublisher.java`:

```java
package com.example.notifications;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationPublisher {

    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;
    private final String channel;

    public NotificationPublisher(
            StringRedisTemplate redis,
            ObjectMapper mapper,
            @Value("${app.notifications.channel}") String channel) {

        this.redis = redis;
        this.mapper = mapper;
        this.channel = channel;
    }

    public PublishReceipt publish(NotificationRequest request)
            throws JsonProcessingException {

        NotificationEvent event = new NotificationEvent(
                UUID.randomUUID().toString(),
                "ANNOUNCEMENT",
                request.text().trim(),
                Instant.now());

        String payload = mapper.writeValueAsString(event);
        Long subscribers = redis.convertAndSend(channel, payload);

        return new PublishReceipt(
                event.id(),
                event.createdAt(),
                subscribers == null ? 0L : subscribers);
    }
}
```

`StringRedisTemplate` giúp publisher gửi chuỗi JSON với String serializers. Subscriber phải dùng cùng hợp đồng encoding.

### Trường hợp subscriber count bằng 0

Nếu không có Redis subscriber đang subscribe, `PUBLISH` có thể vẫn chạy thành công và trả về `0`. Redis không lưu message chờ subscriber xuất hiện sau.

### Trường hợp Redis timeout

Nếu caller mất phản hồi sau khi command đã gửi, không thể chắc chắn Redis chưa thực thi PUBLISH. Retry vô điều kiện có thể làm nhận thông báo lặp. `event.id` hỗ trợ dedup trong hệ thống bổ sung, nhưng một UUID mới cho mỗi lần retry lại không tự bảo đảm idempotency. Với notification quan trọng, cần operation ID ổn định và store bền vững.

## 16. Tạo RedisMessageListenerContainer

`RedisPubSubConfiguration.java`:

```java
package com.example.notifications;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class RedisPubSubConfiguration {

    @Bean
    RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory factory,
            RedisNotificationSubscriber listener,
            @Value("${app.notifications.channel}") String channel) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(factory);
        container.addMessageListener(
                listener,
                new ChannelTopic(channel));
        return container;
    }

    @Bean("notificationFanoutExecutor")
    ThreadPoolTaskExecutor notificationFanoutExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(256);
        executor.setThreadNamePrefix("notification-fanout-");
        executor.initialize();
        return executor;
    }
}
```

`RedisMessageListenerContainer` quản lý subscription lifecycle và dispatch messages tới `MessageListener`. `ChannelTopic` đăng ký một channel chính xác; `PatternTopic` dùng khi cần pattern subscription.

Executor ở đây dành cho bước fan-out ứng dụng; nó không biến Pub/Sub thành queue bền vững. Queue 256 và pool 2–4 threads chỉ là giá trị lab, phải đo dưới tải thực.

### Subscription khởi động không nhất thiết đồng bộ hoàn toàn

Container bean đã được tạo **không chứng minh** Redis subscription đã active ngay lập tức. Nếu publish quá sớm, message có thể mất. Integration test nên đợi subscription sẵn sàng thay vì dùng `Thread.sleep` tùy ý.

## 17. Định nghĩa Redis subscriber

`RedisNotificationSubscriber.java`:

```java
package com.example.notifications;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class RedisNotificationSubscriber implements MessageListener {

    private final ObjectMapper mapper;
    private final SseNotificationHub hub;
    private final Executor fanoutExecutor;

    public RedisNotificationSubscriber(
            ObjectMapper mapper,
            SseNotificationHub hub,
            @Qualifier("notificationFanoutExecutor")
            Executor fanoutExecutor) {
        this.mapper = mapper;
        this.hub = hub;
        this.fanoutExecutor = fanoutExecutor;
    }

    @Override
    public void onMessage(Message message, byte[] pattern) {
        try {
            NotificationEvent event = mapper.readValue(
                    message.getBody(),
                    NotificationEvent.class);

            fanoutExecutor.execute(() -> hub.broadcast(event));
        } catch (IOException invalidJson) {
            recordMalformedMessage(invalidJson);
        } catch (RejectedExecutionException overloaded) {
            recordDroppedMessage(overloaded);
        }
    }

    private void recordMalformedMessage(Exception cause) {
        // Thay bằng structured logging/metric thích hợp.
    }

    private void recordDroppedMessage(Exception cause) {
        // Thay bằng metric + cảnh báo; không retry vô hạn.
    }
}
```

Callback chỉ parse payload rồi giao việc fan-out cho executor. Nếu xử lý SSE chậm, không nên giữ thread nhận Redis messages bằng các thao tác network blocking.

**Giới hạn cần nhận thức:** khi queue đầy, code minh họa bỏ fan-out task và ghi nhận drop. Điều này chỉ chấp nhận được khi thông báo mang tính best-effort. `recordMalformedMessage` và `recordDroppedMessage` là hooks chưa triển khai instrumentation, phải hoàn thiện trước production.

## 18. SSE Hub quản lý các browser connections

`SseNotificationHub.java`:

```java
package com.example.notifications;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.http.MediaType;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Component
public class SseNotificationHub {

    private final Map<String, SseEmitter> clients =
            new ConcurrentHashMap<>();

    public SseEmitter connect() {
        String id = UUID.randomUUID().toString();
        SseEmitter emitter = new SseEmitter(30L * 60_000L);

        clients.put(id, emitter);

        emitter.onCompletion(
                () -> clients.remove(id, emitter));

        emitter.onTimeout(() -> {
            clients.remove(id, emitter);
            emitter.complete();
        });

        emitter.onError(error -> clients.remove(id, emitter));

        try {
            emitter.send(SseEmitter.event()
                    .name("connected")
                    .data("ready"));
        } catch (IOException | IllegalStateException error) {
            clients.remove(id, emitter);
            emitter.completeWithError(error);
        }

        return emitter;
    }

    public void broadcast(NotificationEvent notification) {
        for (Map.Entry<String, SseEmitter> entry : clients.entrySet()) {
            SseEmitter emitter = entry.getValue();

            try {
                synchronized (emitter) {
                    emitter.send(SseEmitter.event()
                            .name("notification")
                            .id(notification.id())
                            .data(notification, MediaType.APPLICATION_JSON));
                }
            } catch (IOException | IllegalStateException error) {
                disconnect(entry.getKey(), emitter);
            }
        }
    }

    @Scheduled(fixedDelay = 25_000L)
    public void heartbeat() {
        for (Map.Entry<String, SseEmitter> entry : clients.entrySet()) {
            SseEmitter emitter = entry.getValue();

            try {
                synchronized (emitter) {
                    emitter.send(SseEmitter.event()
                            .comment("heartbeat"));
                }
            } catch (IOException | IllegalStateException error) {
                disconnect(entry.getKey(), emitter);
            }
        }
    }

    private void disconnect(String id, SseEmitter emitter) {
        clients.remove(id, emitter);
        emitter.complete();
    }

    public int localConnections() {
        return clients.size();
    }
}
```

**Vì sao dùng ConcurrentHashMap?** Browser clients có thể connect/disconnect đồng thời trong khi listener fan-out messages. Registry phải hỗ trợ thay đổi đồng thời.

**Vì sao synchronized(emitter)?** Heartbeat và fan-out có thể chạy từ các threads khác nhau. Lock giảm nguy cơ hai `send` cùng ghi vào một emitter. Nó không tạo bảo đảm thứ tự toàn hệ thống và cũng không thay thế backpressure.

**Vì sao có callbacks cleanup?** Nếu browser đóng tab nhưng emitter không bị loại, registry tăng liên tục và gây memory leak. `onCompletion`, `onTimeout`, `onError` và lỗi khi `send` là các đường cần kiểm soát.

**Vì sao có heartbeat?** Dòng SSE comment định kỳ có thể giúp một số reverse proxy không cắt kết nối idle quá sớm. Heartbeat **không** chứng minh Redis subscription đang hoạt động và **không** là ACK của thông báo.

### Giới hạn của bản lab

Một browser rất chậm có thể khiến `emitter.send(...)` lâu, làm fan-out task bị nghẽn. Production nên cân nhắc **per-client bounded queue**, timeout/drop policy, giới hạn số SSE connections, WebFlux SSE hoặc một realtime gateway chuyên dụng khi số clients lớn.

## 19. REST Controller phát và nhận thông báo

`NotificationController.java`:

```java
package com.example.notifications;

import com.fasterxml.jackson.core.JsonProcessingException;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/notifications")
public class NotificationController {

    private final NotificationPublisher publisher;
    private final SseNotificationHub hub;

    public NotificationController(
            NotificationPublisher publisher,
            SseNotificationHub hub) {
        this.publisher = publisher;
        this.hub = hub;
    }

    @PostMapping
    public ResponseEntity<PublishReceipt> publish(
            @Valid @RequestBody NotificationRequest request)
            throws JsonProcessingException {

        PublishReceipt receipt = publisher.publish(request);
        return ResponseEntity.accepted().body(receipt);
    }

    @GetMapping(
            path = "/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream() {
        return hub.connect();
    }
}
```

`POST` trả HTTP 202 sau khi Redis `PUBLISH` phản hồi; điều đó có nghĩa API **đã phát tới Redis**, không phải đã hiển thị trong browser.

Ở sản phẩm thật, cần `@RestControllerAdvice` hoặc cách xử lý lỗi để Redis exception không rò rỉ thông tin nội bộ, và HTTP response phản ánh lỗi kết nối/ACL/timeout phù hợp. Cũng phải thêm authentication/authorization nếu POST không được phép công khai.

## 20. Frontend nhận SSE bằng EventSource

Tạo `src/main/resources/static/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Spring Data Redis Pub/Sub</title>
</head>
<body>
  <h1>Thông báo thời gian thực</h1>
  <input id="text" maxlength="500" value="Xin chào Pub/Sub">
  <button id="send">Gửi</button>
  <p id="status">Đang kết nối...</p>
  <ul id="messages"></ul>

  <script>
    const status = document.getElementById("status");
    const messages = document.getElementById("messages");
    const input = document.getElementById("text");

    const stream = new EventSource("/api/notifications/stream");

    stream.addEventListener("open", () => {
      status.textContent = "SSE connected";
    });

    stream.addEventListener("connected", () => {
      status.textContent = "SSE ready";
    });

    stream.addEventListener("notification", (message) => {
      const event = JSON.parse(message.data);
      const item = document.createElement("li");

      // Không dùng innerHTML với dữ liệu từ Redis.
      item.textContent = event.createdAt + " — " + event.text;
      messages.prepend(item);
    });

    stream.addEventListener("error", () => {
      status.textContent = "Mất kết nối, EventSource đang thử lại";
    });

    document.getElementById("send").addEventListener(
      "click", async () => {
        const response = await fetch("/api/notifications", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({text: input.value})
        });

        if (!response.ok) {
          status.textContent = "Publish failed: " + response.status;
        }
      });

    window.addEventListener("beforeunload", () => stream.close());
  </script>
</body>
</html>
```

`EventSource` duy trì một kết nối HTTP stream. Khi server gửi event `notification`, browser parse JSON và đưa nội dung vào danh sách.

**Bảo vệ XSS:** `textContent` hiển thị text đúng nghĩa, không thực thi HTML từ payload. Không viết `item.innerHTML = event.text` với nội dung không đáng tin.

### Frontend và server cùng origin

HTML trên được Spring Boot static resource server phục vụ ở cùng origin với API. Nếu frontend chạy ở origin khác, cần cấu hình CORS, cookie/session/credentials và CSRF phù hợp. Browser EventSource API không mặc nhiên cho phép đặt các HTTP headers tùy ý như một fetch thông thường; tránh truyền access token bí mật qua query string.

## 21. Chạy bản demo

Bước thực hành:

1. Khởi động Redis lab.
2. Chạy Spring Boot app trên port 8080.
3. Mở `http://localhost:8080/` trong hai tab.
4. Đợi trạng thái `SSE ready`.
5. Nhập một thông báo rồi bấm **Gửi**.
6. Quan sát cả hai tab nhận sự kiện `notification`.

Luồng thực tế:

```text
Browser POST
    |
    v
NotificationController
    |
    v
NotificationPublisher
    |
    v
StringRedisTemplate.convertAndSend
    |
    v
Redis PUBLISH demo:notifications JSON
    |
    v
RedisMessageListenerContainer
    |
    v
RedisNotificationSubscriber
    |
    v
NotificationFanoutExecutor
    |
    v
SseNotificationHub.broadcast
    |
    +--> Browser tab 1
    +--> Browser tab 2
```

Không nên publish ngay khi Spring process mới khởi chạy rồi mặc định subscriber đã sẵn sàng; Redis subscription có thể được thiết lập bất đồng bộ.

## 22. Publish bằng curl và PowerShell

Trên shell Unix:

```bash
curl -i -X POST http://localhost:8080/api/notifications \
  -H "Content-Type: application/json" \
  -d '{"text":"Thong bao den tu HTTP API"}'
```

Trên Windows PowerShell:

```powershell
$body = @{ text = "Thong bao tu PowerShell" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8080/api/notifications" -Method Post -ContentType "application/json" -Body $body
```

Response minh họa:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "eventId": "9e949e39-3033-48ab-91a4-7d5cfcd091cb",
  "createdAt": "2026-11-13T03:00:00Z",
  "redisSubscriberConnections": 1
}
```

UUID và timestamp thật sẽ khác. Nếu subscribers chưa kết nối, count có thể là 0 nhưng Redis không tự lưu message.

## 23. Xem SSE stream bằng terminal

Trên shell có curl:

```bash
curl -N http://localhost:8080/api/notifications/stream
```

Trên Windows PowerShell:

```powershell
curl.exe -N http://localhost:8080/api/notifications/stream
```

Một SSE stream có thể trông như:

```text
event: connected
data: ready

id: 9e949e39-3033-48ab-91a4-7d5cfcd091cb
event: notification
data: {"id":"9e949e39-3033-48ab-91a4-7d5cfcd091cb","type":"ANNOUNCEMENT","text":"Xin chao","createdAt":"2026-11-13T03:00:00Z"}

:heartbeat
```

`id:` trong SSE cho phép browser lưu `Last-Event-ID` khi reconnect theo giao thức SSE, **nhưng không tạo ra Redis Pub/Sub replay**.

Proxy có thể buffer SSE response và làm thông báo bị trễ, hoặc cắt connection khi idle. Production cần kiểm tra reverse-proxy buffering, timeouts và keep-alive.

## 24. Redis CLI kiểm tra Java đã publish gì

Terminal A:

```bash
redis-cli SUBSCRIBE demo:notifications
```

Terminal B publish qua HTTP API. Terminal A phải nhìn thấy JSON giống `NotificationEvent`.

Nếu chạy:

```bash
redis-cli PUBLISH demo:notifications "hello"
```

Redis subscriber sẽ nhận `hello`, nhưng **Spring listener của ví dụ sẽ không broadcast SSE** vì `hello` không phải JSON hợp lệ với schema `NotificationEvent`. Đó là lỗi hợp đồng payload, không phải Redis bỏ message.

Để test Spring listener qua CLI, dùng JSON hợp lệ:

```bash
redis-cli PUBLISH demo:notifications '{"id":"manual-1","type":"ANNOUNCEMENT","text":"Xin chao CLI","createdAt":"2026-11-13T03:00:00Z"}'
```

Quoting của shell Windows có thể khác Unix; có thể dùng `redis-cli` interactive mode để nhập message.

## 25. Tại sao PUBLISH count khác số trình duyệt?

Giả sử:

```text
Spring instance A:
  1 Redis subscriber
  100 SSE browsers

Spring instance B:
  1 Redis subscriber
  50 SSE browsers

Redis PUBLISH:
  thấy các Redis subscriber connections phù hợp,
  không thể đếm trực tiếp 150 browser SSE clients.
```

`convertAndSend` trả thông tin ở tầng Redis, không chứng minh:

- JSON đã được parse.
- Executor còn chỗ để xử lý.
- SSE connection còn sống.
- Browser đã nhận event.
- User đã đọc thông báo.
- Event đã được persist.

Nếu muốn đo *browser delivery* cần callback/ACK của frontend và lưu trạng thái ở data store phù hợp; Redis Pub/Sub tự nó không có ACK.

## 26. Chạy hai Spring Boot instances

Dùng hai JVM processes cùng cấu hình Redis/channel nhưng HTTP port khác:

```text
Instance A:
  server.port = 8080

Instance B:
  server.port = 8081

Cả hai:
  Redis = localhost:6379
  app.notifications.channel = demo:notifications
```

Mở `http://localhost:8080/` và `http://localhost:8081/` trong hai browser tabs.

Publish qua A:

```bash
curl -X POST http://localhost:8080/api/notifications \
  -H "Content-Type: application/json" \
  -d '{"text":"Phat tu instance A"}'
```

Khi cả hai Redis subscriptions và SSE connections active, browser ở **cả A lẫn B** nhận thông báo. Đây là điểm mạnh của Redis Pub/Sub trong kiến trúc nhiều app nodes: publisher không cần biết browser đang gắn với node nào.

**Lưu ý:** chỉ hai instance cùng Redis server nhưng một instance không đăng ký Redis listener thì instance đó không tự nhận message. Mỗi instance cần một subscription hoặc có kiến trúc fan-out khác tương đương.

## 27. Thử subscriber offline để hiểu at-most-once

Quy trình:

1. Khi A và B đang chạy, publish một message, xác nhận cả hai nhận.
2. Dừng B.
3. Publish ba messages vào Redis thông qua A.
4. Khởi động lại B và kết nối browser.
5. B **không** nhận lại ba messages phát trong thời gian offline.
6. Publish message thứ tư khi B đã subscribe; B nhận message mới.

Redis không có hàng đợi riêng theo subscriber. Các messages đã phát trong lúc B offline không thể lấy lại chỉ từ channel.

Nếu sản phẩm yêu cầu “user đăng nhập lại vẫn thấy thông báo chưa đọc”, cần **lưu notification vào database/Streams** và có API tải lịch sử.

## 28. Browser reconnect không có nghĩa replay

SSE EventSource có thể tự reconnect:

```text
T1 Browser nhận event id=10
T2 Network đứt
T3 Redis Pub/Sub phát event 11, 12, 13
T4 Browser reconnect gửi Last-Event-ID=10
```

Ứng dụng hiện tại **không có store** chứa 11–13. Nó chỉ có những events mới từ Redis sau khi subscription/connection sẵn sàng. Do đó không thể trả lại events đã mất dựa trên `Last-Event-ID`.

Một cơ chế replay cần:

- Persistent store (SQL hoặc Redis Streams với retention).
- Cursor/event ID để truy vấn phần chưa nhận.
- API đọc lại sự kiện sau cursor.
- Authentication/authorization theo user.
- Dedup giữa live events và history.
- Quy tắc giới hạn retention và cleanup.

Không nên hứa “không mất thông báo” chỉ vì SSE tự reconnect.

## 29. Khi cần lưu lịch sử: lưu trước rồi phát tín hiệu

Một kiến trúc phù hợp cho notification center:

```text
User action
   |
   v
SQL transaction
   |
   +--> INSERT notification
   +--> INSERT outbox_event
   |
   v
COMMIT
   |
   v
Outbox dispatcher
   |
   v
Redis PUBLISH "notification-created"
   |
   v
Browser receives signal
   |
   v
GET /api/notifications?after=<cursor>
   |
   v
SQL: notifications with authorization
```

Ở đây **database** giữ nguồn sự thật. Pub/Sub chỉ báo browser rằng nên tải dữ liệu mới.

Vì sao cần outbox? Nếu transaction SQL commit xong nhưng process chết trước khi PUBLISH, event signal bị mất. Outbox giúp dispatcher có record để retry sau crash. Nó không tự đảm bảo Pub/Sub listener nhận message khi offline, nhưng UI vẫn có thể tải dữ liệu đúng từ database khi reconnect.

## 30. Bảo mật Redis Pub/Sub bằng ACL

Redis ACL phân biệt **key pattern** và **Pub/Sub channel pattern**.

Ví dụ principal publisher chỉ cần:

```text
+publish
&demo:notifications
```

Principal subscriber chỉ cần:

```text
+subscribe
&demo:notifications
```

Trên Redis lab có ACL (Redis 6+), có thể dùng `redis-cli` interactive dưới tài khoản quản trị:

```text
ACL SETUSER lab_publisher reset on >CHANGE_ME_PUB +ping +publish &demo:notifications
ACL SETUSER lab_subscriber reset on >CHANGE_ME_SUB +ping +subscribe &demo:notifications
```

Các password chỉ là mẫu, không dùng trong production. Nhập trực tiếp trong Redis CLI interactive thay vì dán vào shell nếu ký tự `>`, `&` bị shell hiểu thành toán tử.

### Kiểm thử quyền âm

- Publisher thử `SUBSCRIBE` → từ chối nếu thiếu quyền.
- Subscriber thử `PUBLISH` → từ chối nếu thiếu quyền.
- Cả hai dùng channel `private:secret` → `NOPERM`.
- App dùng user sai/mật khẩu sai → `NOAUTH`/`WRONGPASS`, không phải “message chưa tới”.
- Redis client cần quyền mở connection/command tương ứng của Spring health checks nếu có; kiểm thử với đường app thật.

Trong lab đơn giản một Spring app vừa publish vừa subscribe có thể dùng một user với cả `+publish +subscribe`. Nếu threat model yêu cầu tách, tạo connection factories/templates và listener container dùng credentials riêng, kiểm tra wiring đúng bean.

**Không cấp `+@all ~* &*` chỉ để sửa NOPERM.**

## 31. PatternTopic khi cần nhiều channels

Ví dụ các channels:

```text
demo:notifications:orders
demo:notifications:inventory
demo:notifications:system
```

Nếu cần subscribe theo pattern, Spring Data Redis hỗ trợ:

```java
import org.springframework.data.redis.listener.PatternTopic;

container.addMessageListener(
        listener,
        new PatternTopic("demo:notifications:*"));
```

Đây là `PSUBSCRIBE`, khác `SUBSCRIBE` chính xác tên channel. Khi dùng pattern:

- ACL cần `+psubscribe` và channel patterns phù hợp.
- Không dùng wildcard quá rộng để nghe dữ liệu ngoài trách nhiệm.
- Phải nhận diện channel thực tế từ `Message.getChannel()`.
- Chi phí subscription/matching có thể tăng theo cấu trúc channels và số subscribers.
- Pattern subscription không bổ sung replay.

Đối với thông báo theo user/tenant, không nên đăng ký wildcard rồi broadcast mọi payload cho mọi browser.

## 32. Thông báo cá nhân cần authorization ở tầng ứng dụng

**Demo chỉ phát thông báo chung.** Nếu notification chứa thông tin user-42, các browser của user-43 không được nhìn thấy nó.

Các hướng thiết kế:

1. SSE endpoint xác thực user và liên kết connection với principal được xác minh.
2. Notification data được lưu trong database có authorization theo user/tenant.
3. Redis Pub/Sub chỉ phát event ID hoặc tín hiệu “có dữ liệu mới”, không mang payload nhạy cảm qua global channel.
4. App tìm đúng client sessions cần thông báo, không broadcast toàn bộ.
5. Nếu channel theo tenant/room, server phải quyết định channel từ identity đã xác thực, không tin channel do client gửi.
6. Không đưa token/session secrets vào tên Redis channels.
7. Khi dùng dynamic subscriptions, giới hạn số channel và cleanup lifecycle.

ACL của Redis bảo vệ principal Redis chứ **không tự xác thực browser user**. Kể cả subscriber Redis được phép nghe channel, code Spring vẫn phải thực hiện authorization đúng.

## 33. Tránh XSS và dữ liệu không hợp lệ

Pub/Sub message có thể do nhiều service/producers gửi tới. Subscriber phải coi payload như dữ liệu bên ngoài:

- Dùng JSON schema/type validation.
- Giới hạn kích thước text/payload.
- Không chạy arbitrary code từ payload.
- Không log raw PII/secrets.
- Frontend hiển thị bằng `textContent`.
- Không dùng `innerHTML` với text chưa được sanitize.
- HTTP POST phải có authentication, authorization và rate limit nếu có thể tác động người dùng.
- Với cookie-based session, áp dụng CSRF protection cho POST theo chính sách security.

Payload được Redis chuyển tới **không tự trở thành đáng tin** chỉ vì server nằm trong mạng riêng.

## 34. Sự cố reconnect và listener lifecycle

Một Redis subscription là trạng thái trên connection:

```text
Spring process starts
      |
      v
Connect Redis
      |
      v
SUBSCRIBE
      |
      v
ACTIVE
      |
      +--> messages
      |
      +--> network failure
                  |
                  v
               reconnect
                  |
                  v
               resubscribe
```

Trong khoảng mất subscription, Redis Pub/Sub không lưu messages để phát bù. `RedisMessageListenerContainer` giúp quản lý lifecycle, nhưng ứng dụng phải giám sát subscription errors/reconnect và kiểm thử thực tế.

**PING qua một Redis connection khác không chứng minh subscription connection đang nhận được messages.**

Không cấu hình Kubernetes liveness phụ thuộc vào một Redis subscriber remote để restart mọi pods mỗi khi Redis bị lỗi; restart không chữa được Redis server outage và có thể gây reconnect storm.

## 35. Slow SSE clients và backpressure

Demo có một danh sách emitters trên mỗi instance. Một browser chậm có thể khiến `send` mất lâu, làm backlog trong `notificationFanoutExecutor`.

Dấu hiệu:

- Executor queue depth tăng.
- Fan-out latency p95/p99 tăng.
- Rejected tasks/dropped notifications tăng.
- Servlet async contexts giữ memory lâu.
- SSE connections bị timeout/reconnect liên tục.

Một hướng production:

```text
Redis message
      |
      v
Validate JSON
      |
      v
Bounded dispatcher
      |
      +--> Client A queue (bounded)
      +--> Client B queue (bounded)
      +--> Client C queue (bounded)
                       |
                       +--> Slow client: drop/close theo policy
```

Với lượng browser lớn có thể cân nhắc WebFlux, realtime gateway hoặc nền tảng hỗ trợ broadcast hiệu quả hơn. Không đổi queue capacity thành vô hạn: khi Redis/message rate cao, JVM có thể hết bộ nhớ trước khi vấn đề được phát hiện.

**Giới hạn bảo đảm của bài lab:** một fan-out task bị drop có nghĩa browser có thể mất thông báo. Đó là lý do yêu cầu delivery bắt buộc cần store/replay.

## 36. Redis Cluster và sharded Pub/Sub

Trong Redis Cluster, Pub/Sub truyền thống và **sharded Pub/Sub** là hai mô hình khác nhau. Redis 7 bổ sung các lệnh như `SPUBLISH`, `SSUBSCRIBE` và `SUNSUBSCRIBE` phục vụ phân phối theo shard.

| Mô hình | Các lệnh | Điều cần kiểm tra |
|---|---|---|
| Pub/Sub truyền thống | `PUBLISH`, `SUBSCRIBE`, `PSUBSCRIBE` | Distribution và chi phí fan-out trên cluster |
| Sharded Pub/Sub | `SPUBLISH`, `SSUBSCRIBE` | Channel hash slot, routing và server/client version |
| Redis Streams | `XADD`, `XREADGROUP` | Retention, ACK, PEL và recovery |

Không giả định `RedisMessageListenerContainer` ở mọi Spring Data Redis version tự chuyển sang sharded Pub/Sub. Nếu cần sharded mode, phải xác nhận API/client Lettuce/Redis version hỗ trợ và kiểm thử trên Cluster thật.

Các điểm vận hành:

- Redis Cluster topology/failover có thể khiến subscriptions reconnect.
- Node endpoints được Redis quảng bá phải truy cập được từ các application instances.
- ACL channel rules phải nhất quán theo hạ tầng.
- Subscriber counts từ một node không phải browser delivery metric.
- Failover có thể gây khoảng mất messages.
- Đo network/CPU khi fan-out nhiều channels/subscribers, không chỉ PUBLISH latency.

## 37. Testcontainers để kiểm thử Redis Pub/Sub thật

Mock `StringRedisTemplate` chỉ xác nhận Java gọi `convertAndSend`; nó không chứng minh Redis đã gửi đến subscriber thật.

Khung test:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class RedisPubSubIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port",
                () -> REDIS.getMappedPort(6379));
    }

    // @Autowired NotificationPublisher publisher;
    // @Autowired ObjectMapper mapper;
    // Các test publish/subscribe ở phần tiếp.
}
```

Redis test phải được cô lập. Nếu chạy fault injection, ACL denial hoặc kill container, tuyệt đối không dùng Redis production hoặc Redis của team khác làm nơi thử.

## 38. Integration test: chờ subscription thật bằng Lettuce

Một test nhận message độc lập bằng Lettuce có thể dùng `RedisPubSubAdapter`. Khác với sleep may rủi, test đợi Redis xác nhận subscribe:

```java
import io.lettuce.core.RedisClient;
import io.lettuce.core.pubsub.RedisPubSubAdapter;
import io.lettuce.core.pubsub.StatefulRedisPubSubConnection;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

String channel = "demo:notifications";
String uri = "redis://" + REDIS.getHost() + ":"
        + REDIS.getMappedPort(6379);

RedisClient client = RedisClient.create(uri);
BlockingQueue<String> received = new LinkedBlockingQueue<>();
CountDownLatch subscribed = new CountDownLatch(1);

try (StatefulRedisPubSubConnection<String, String> connection =
        client.connectPubSub()) {

    connection.addListener(new RedisPubSubAdapter<String, String>() {

        @Override
        public void subscribed(String name, long count) {
            if (channel.equals(name)) {
                subscribed.countDown();
            }
        }

        @Override
        public void message(String name, String payload) {
            if (channel.equals(name)) {
                received.add(payload);
            }
        }
    });

    connection.async().subscribe(channel);

    if (!subscribed.await(5, TimeUnit.SECONDS)) {
        throw new AssertionError("SUBSCRIBE not ready");
    }

    publisher.publish(new NotificationRequest("Lab event"));

    String payload = received.poll(5, TimeUnit.SECONDS);
    assertThat(payload).isNotNull();

    NotificationEvent event =
            mapper.readValue(payload, NotificationEvent.class);
    assertThat(event.text()).isEqualTo("Lab event");
} finally {
    client.shutdown();
}
```

Đoạn này là **phần thân integration test**, giả định `REDIS`, `publisher`, `mapper` đã wiring/inject và AssertJ `assertThat` được import. Test chứng minh **Redis publish → một subscriber thật**; chưa chứng minh Spring listener → browser SSE.

Bộ test end-to-end HTTP nên:

1. Kết nối SSE và đợi `connected`.
2. Đảm bảo Redis listener đã subscribe.
3. Publish qua HTTP API.
4. Đọc SSE event `notification`, assert JSON event ID/text.
5. Đóng browser connection, kiểm tra cleanup.
6. Lặp lại với hai instances để kiểm chứng fan-out.

Không dùng `Thread.sleep(100)` làm bằng chứng subscription đã sẵn sàng.

## 39. Ma trận kiểm thử đề xuất

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| PUB-01 | Subscriber online và message hợp lệ | Nhận JSON đúng |
| PUB-02 | Không có subscriber | Không có replay/history; publish có thể trả 0 |
| PUB-03 | Sai channel | Không nhận |
| PUB-04 | Invalid JSON | Parse error được ghi nhận, không broadcast |
| PUB-05 | Redis unavailable | API không báo giao thành công |
| PUB-06 | Timeout sau PUBLISH | Phân biệt kết quả không chắc chắn, có dedup policy nếu cần |
| SUB-01 | Spring listener startup | Subscription được xác nhận trước publish |
| SUB-02 | Redis restart | Reconnect, messages trong outage có thể mất |
| SUB-03 | ACL thiếu SUBSCRIBE/channel | NOPERM được phát hiện |
| SSE-01 | Một browser | Nhận event |
| SSE-02 | Nhiều browser một instance | Tất cả đang kết nối nhận event |
| SSE-03 | Disconnect/timeout | SseEmitter được cleanup |
| SSE-04 | Browser reconnect | Nhận event mới, không replay event cũ |
| SSE-05 | Slow client | Overload/queue/drop policy có metric |
| MULTI-01 | Hai Spring instances | Publish qua A, browser A/B nhận |
| MULTI-02 | B offline | Không nhận bù khi start |
| ACL-01 | Publisher chỉ được publish | Không subscribe/khác channel |
| ACL-02 | Subscriber chỉ được subscribe | Không publish/khác channel |
| SEC-01 | Text rỗng/quá dài | Validation từ chối |
| SEC-02 | Text có HTML/script | Không execute nhờ `textContent` |
| LOAD-01 | N browsers, M msgs/s | Đo fan-out p99, queue, heap, drops |
| STORE-01 | Có DB notification store | Reconnect tải lại lịch sử |

Các nhóm nên được tách thành Redis protocol, Spring integration, browser SSE, multi-instance, ACL/security và load/fault tests. Không khẳng định reliability chỉ từ một test happy path.

## 40. Quan sát production và xử lý sự cố

Các metrics đáng theo dõi:

| Tín hiệu | Ý nghĩa |
|---|---|
| HTTP publish success/error rate | Publisher còn gọi Redis được không |
| Redis PUBLISH latency | Chi phí command/connection |
| Redis subscriber count | Có listener đang subscribe không; không phải browser count |
| Listener reconnect/subscription error | App có mất message window không |
| Invalid JSON count | Publisher/schema không tương thích |
| Executor queue depth/rejections | Fan-out có quá tải không |
| Local SSE connection count | Browser connections theo từng instance |
| SSE send latency p95/p99 | Slow clients/proxy/servlet pressure |
| SSE disconnect/reconnect rate | Kết nối có ổn định không |
| Publish-to-browser latency | Trải nghiệm realtime thật |
| Memory/CPU | Headroom khi fan-out tăng |
| Historical sync errors | Nếu có store/replay, client có tải bù được không |

**Không gắn user ID/token hoặc raw notification text vào metric labels**, tránh lộ dữ liệu và high cardinality.

### Chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Redis PUBLISH trả 0 | Chưa có subscription phù hợp | Channel, listener startup, `PUBSUB NUMSUB` |
| CLI thấy JSON, browser không thấy | SSE/JSON parser/executor lỗi | Logs, invalid count, queue và SSE connection |
| Browser “connected” nhưng không có message | Redis subscribe chưa active | Subscription status, Redis config |
| Chỉ một Spring instance nhận | Instance kia sai Redis/channel/ACL | Endpoints, channel config, reconnect |
| Message bị lặp | HTTP publisher retry hoặc app fan-out logic | Event ID và dedup |
| Message mất khi restart | Redis Pub/Sub không replay | Store/Streams |
| NOPERM | Thiếu Redis channel rule/command | ACL user, ACL LOG |
| NOAUTH/WRONGPASS | Secret/user sai | Spring connection factory |
| Browser nhận chậm | Reverse proxy buffering, slow client, executor | SSE p99, queue, proxy settings |
| Browser disconnect sau idle | SSE timeout/proxy | Heartbeat, keep-alive, reconnect |

## 41. Runbook khi Redis hoặc subscriber mất kết nối

1. Xác định đường lỗi: publisher, Redis, subscriber hay SSE.
2. Kiểm tra Redis connection và đúng channel.
3. Kiểm tra Redis ACL/authentication, tránh in credentials.
4. Xác nhận listener đã reconnect/resubscribe.
5. Kiểm tra executor queue, rejected tasks và số SSE connections.
6. Không giả định thông báo đã phát trong downtime được lưu lại.
7. Nếu có persistent store, yêu cầu browser tải lịch sử sau reconnect.
8. Giới hạn retry PUBLISH khi kết quả không chắc chắn; không spam lại mọi event.
9. Sau phục hồi, gửi một synthetic event trong môi trường được phép và kiểm chứng tới SSE browser.
10. Theo dõi error rate, drop count, fan-out p99 và memory sau sự cố.

Không chữa lỗi Pub/Sub bằng `FLUSHDB`, `FLUSHALL` hay restart toàn bộ pods. Chúng không mang lại messages đã mất, có thể còn làm sự cố nặng hơn.

## 42. Câu hỏi tự đánh giá

**1. Redis Pub/Sub có phải queue bền vững không?**  
Không. Messages chỉ được phân phối tới subscribers đang subscribe, không có ACK/replay.

**2. Spring Data Redis dùng API nào để PUBLISH?**  
`StringRedisTemplate.convertAndSend(channel, payload)`.

**3. Thành phần Spring nào quản lý subscription?**  
`RedisMessageListenerContainer` cùng `MessageListener` và `ChannelTopic`/`PatternTopic`.

**4. Một PUBLISH trả 2 có nghĩa hai browser đã đọc không?**  
Không. Đó là thông tin subscriber connections ở tầng Redis, không phải user acknowledgement.

**5. Vì sao một Redis listener có thể phục vụ 100 browser clients?**  
Vì Spring instance nhận một Redis message rồi fan-out qua các SSE connections cục bộ.

**6. SSE EventSource có thể tự reconnect không?**  
Có, nhưng không tự replay Redis Pub/Sub events bị bỏ lỡ.

**7. Tại sao cần event ID?**  
Để correlate/dedup và hỗ trợ query lịch sử nếu có persistent store, không tự tạo reliability.

**8. Vì sao không broadcast thẳng trong Redis callback?**  
Một browser chậm có thể block subscription callback và gây backlog.

**9. Pub/Sub dùng Redis ACL key pattern hay channel pattern?**  
Channel pattern `&...` và command permissions tương ứng.

**10. Khi muốn notification riêng cho một user, có thể broadcast toàn bộ payload tới mọi browser?**  
Không. Cần authentication/authorization, scope và thường là store có quyền truy cập.

**11. Nếu producer phát lúc subscriber offline thì sao?**  
Thông báo mất đối với subscriber đó, không được Redis lưu để giao lại.

**12. Vì sao Redis CLI PUBLISH chuỗi `hello` nhưng browser demo không hiển thị?**  
Vì subscriber yêu cầu JSON theo `NotificationEvent`; `hello` không đúng schema.

**13. Khi Redis healthy nhưng SSE chậm, phải quan sát gì?**  
Executor queue, servlet/proxy buffering, SSE client send latency, memory và reconnect.

**14. Nếu thông báo phải có lịch sử và không mất, cần gì?**  
Persistent store, cursor/replay API và khi phù hợp outbox/Streams/queue có ACK/recovery.

**15. Redis Pub/Sub khác WebSocket/SSE ở tầng nào?**  
Pub/Sub nối các server với Redis; WebSocket/SSE nối ứng dụng tới browser.

## 43. Checklist hoàn thiện trước production

- [ ] Xác định best-effort notification hay yêu cầu lưu lịch sử/replay.
- [ ] Publisher và subscriber dùng cùng channel và JSON schema.
- [ ] Redis connection có TLS/ACL và secret management phù hợp.
- [ ] Không expose Redis lab không authentication ra mạng công cộng.
- [ ] HTTP publish API có validation, auth, authorization và rate limit.
- [ ] Không chấp nhận channel name tùy ý từ browser.
- [ ] RedisMessageListenerContainer được giám sát reconnect/subscription.
- [ ] Không xử lý blocking fan-out nặng trên Redis listener thread.
- [ ] Executor/queues có giới hạn, drops có metric/alert.
- [ ] SSE clients có timeout, cleanup và heartbeat phù hợp.
- [ ] Browser dùng rendering an toàn (`textContent`).
- [ ] Không để notification chứa PII đi trên global channel.
- [ ] Redis ACL phân biệt command và channel permissions.
- [ ] Đã test khi subscription chưa sẵn sàng và Redis outage.
- [ ] Đã test hai app instances, nhiều SSE browsers và slow clients.
- [ ] Không coi PUBLISH count là browser delivery acknowledgement.
- [ ] Có error classification cho timeout/NOPERM/NOAUTH/WRONGPASS.
- [ ] Có p95/p99 publish-to-browser latency, queue depth, drop count.
- [ ] Nếu có dữ liệu quan trọng, có store/outbox/Streams và replay API.
- [ ] Các fault/ACL tests chỉ chạy trên Redis cô lập.

## 44. Tổng kết

Bằng vài thành phần của Spring Data Redis, ta đã dựng được một hệ thống truyền tín hiệu thời gian thực:

- `StringRedisTemplate.convertAndSend` **publish JSON** vào Redis channel.
- `RedisMessageListenerContainer` và `MessageListener` **subscribe và nhận** message.
- `SseNotificationHub` dùng `SseEmitter` **fan-out** tới những browser đang kết nối với instance.
- `EventSource` hiển thị notifications và tự reconnect SSE.
- Redis làm **backplane giữa nhiều Spring instances**, không cần instance A gọi HTTP trực tiếp sang B.

Tuy nhiên, **Pub/Sub chỉ là phân phối tức thời**. Khi subscriber ngắt mạng, app restart, executor đầy hoặc browser chưa kết nối, những notifications có thể bị mất. Để xây notification center có lịch sử, cần **lưu dữ liệu trước, phát Pub/Sub như tín hiệu cập nhật**, và cho client tải bù từ store theo cursor; nếu cần consumer ACK/recovery, đánh giá Redis Streams/message broker.

Một hệ thống realtime đúng không chỉ khiến message xuất hiện nhanh khi mọi thứ bình thường, mà còn **nói rõ điều gì được phép mất, điều gì phải lưu, người dùng nhận lại thế nào và làm sao quan sát các lần gửi thất bại**.

## Tài liệu tham khảo

- [Spring Data Redis — Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html): RedisMessageListenerContainer, MessageListener và topics.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): Redis operations và `convertAndSend`.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): consumer group/ACK/replay.
- [Spring Framework — SSE với SseEmitter](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html#mvc-ann-async-sse): cách dùng SSE trong Spring MVC.
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/): delivery semantics và channels.
- [Redis — PUBLISH](https://redis.io/docs/latest/commands/publish/): publish và reply.
- [Redis — SUBSCRIBE](https://redis.io/docs/latest/commands/subscribe/): đăng ký channel.
- [Redis — PSUBSCRIBE](https://redis.io/docs/latest/commands/psubscribe/): đăng ký theo pattern.
- [Redis — ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): quyền command và channel patterns.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): cluster và sharded Pub/Sub.
- [MDN — EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource): SSE browser interface.
- [MDN — Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): định dạng SSE và reconnect.
- [Testcontainers for Java](https://java.testcontainers.org/): Redis server cô lập cho integration tests.

# Quản lý vòng đời đăng ký và đóng kết nối

Trong **Redis Pub/Sub**, publisher phát một message tới channel; những subscriber đang đăng ký channel đó và còn kết nối sẽ nhận message. Spring Data Redis cung cấp `RedisMessageListenerContainer` để quản lý quá trình subscribe, phân phối message tới callback Java và dọn tài nguyên khi ứng dụng ngừng hoạt động.

Một subscriber chạy lâu dài không chỉ cần gọi `SUBSCRIBE`. Ứng dụng phải xác định **ai sở hữu đăng ký**, **khi nào được bắt đầu nhận**, **lúc nào cần unsubscribe**, **đóng kết nối ra sao** và **phải làm gì khi Redis bị ngắt kết nối**. Quản lý vòng đời đúng giúp tránh rò rỉ connection, tạo listener trùng lặp và vô tình dừng những chức năng vẫn còn hoạt động.

> Phạm vi bài học: Redis Pub/Sub thông thường và các API listener của Spring Data Redis. Pub/Sub truyền message tức thời; nó không phải hàng đợi bền vững có cơ chế lưu và phát lại message cho subscriber bị offline.

## 1. Phân biệt bốn đối tượng quan trọng

| Đối tượng | Vai trò | Ai quản lý? |
| --- | --- | --- |
| **Channel** | Tên logic để publisher phát message, ví dụ `orders.events` | Quy ước đặt tên của ứng dụng |
| **MessageListener** | Callback Java nhận và xử lý message | Bean Spring hoặc một thành phần đăng ký động |
| **Subscription** | Quan hệ giữa subscriber và channel/pattern đang lắng nghe | Redis connection, thường qua listener container |
| **Redis connection** | Kênh giao tiếp tới Redis để nhận message | `RedisMessageListenerContainer` hoặc mã thủ công tạo connection |

Một listener có thể đăng ký nhiều channel. Một channel cũng có thể có nhiều subscriber. Do đó, **gỡ một subscription** khác với **dừng toàn bộ listener container**, và cũng khác với **đóng một connection**.

Ví dụ hai chức năng dùng chung container:

~~~text
              Publisher                       Redis
                  |                             |
                  +-- PUBLISH orders.events --->|
                  +-- PUBLISH payments.events ->|
                                                |
                               Redis Pub/Sub subscription
                                                |
                                                v
                              RedisMessageListenerContainer
                               /                      \
                              v                        v
                    OrderEventListener          PaymentListener
                     orders.events               payments.events
~~~

Nếu người quản trị tạm tắt chức năng nhận thông báo đơn hàng, ứng dụng nên gỡ đăng ký của `OrderEventListener`. Không nên gọi `container.stop()` nếu `PaymentListener` vẫn cần nhận message.

## 2. Vòng đời trực tiếp ở Redis

Trên một Redis connection dành cho subscriber, client đăng ký channel:

~~~redis
SUBSCRIBE orders.events
~~~

Từ một connection khác, publisher gửi message:

~~~redis
PUBLISH orders.events "created:order-101"
~~~

Subscriber đang online và đã đăng ký sẽ nhận thông báo. Khi không còn cần nghe:

~~~redis
UNSUBSCRIBE orders.events
~~~

Đối với đăng ký theo mẫu:

~~~redis
PSUBSCRIBE orders.*
PUNSUBSCRIBE orders.*
~~~

`SUBSCRIBE`/`UNSUBSCRIBE` thao tác trên **channel chính xác**, còn `PSUBSCRIBE`/`PUNSUBSCRIBE` thao tác trên **pattern**. Nếu cả `orders.events` và `orders.*` cùng khớp một message thì ứng dụng có thể nhận notification qua cả hai loại subscription; không được mặc định luôn chỉ có một callback.

~~~text
             Chưa đăng ký
                  |
          SUBSCRIBE / PSUBSCRIBE
                  |
                  v
              Đang nghe
                  |
           +------+-------+
           |              |
      Có message      Yêu cầu dừng
           |              |
           v              v
       Chạy callback   UNSUBSCRIBE
           |          PUNSUBSCRIBE
           |              |
           v              v
       Tiếp tục nghe   Ngừng đăng ký
                         |
                      Có thể đóng
                      connection
~~~

**Trạng thái subscribe gắn với connection Redis.** Nếu connection bị đóng, server cũng không còn subscription đó. Việc tạo connection mới không tự phát lại các message đã gửi vào lúc kết nối cũ ngắt.

## 3. Vì sao cần `RedisMessageListenerContainer`?

Lệnh `RedisConnection.subscribe(...)` ở mức thấp có thể duy trì một phiên nhận message trong thời gian dài và có đặc điểm blocking tùy driver. Nếu gọi trực tiếp trong HTTP request hoặc tạo một connection cho từng người dùng, ứng dụng có thể gặp:

- Request HTTP bị giữ mở đến khi subscription kết thúc.
- Thread nhận message không có điểm dừng rõ ràng.
- Tạo quá nhiều connection khi số user hoặc channel tăng.
- Quên unsubscribe hoặc quên đóng connection khi một tính năng bị tắt.
- Thiếu logic reconnect và đăng ký lại sau Redis restart/failover.
- Khó phân biệt ai chịu trách nhiệm đóng tài nguyên.

`RedisMessageListenerContainer` cung cấp một điểm quản lý tập trung. Nó kết nối `RedisConnectionFactory` với các listener, thực hiện subscription và dispatch callback; thông thường nó chia sẻ kết nối nhận message giữa nhiều listener thay vì yêu cầu mỗi listener tự mở một connection.

Container tham gia **Spring bean lifecycle**. Với một bean do Spring ApplicationContext tạo và quản lý, ứng dụng thường không phải gọi thủ công `start()` hoặc `destroy()`. Framework điều phối việc khởi động và dừng container cùng context.

## 4. Ví dụ listener cố định trong Spring Boot

Thư viện chính:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Tạo listener nhận message dưới dạng UTF-8:

~~~java
package com.example.redis.pubsub;

import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener implements MessageListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrderEventListener.class);

    @Override
    public void onMessage(Message message, byte[] pattern) {
        String channel = new String(
            message.getChannel(), StandardCharsets.UTF_8
        );
        String payload = new String(
            message.getBody(), StandardCharsets.UTF_8
        );

        log.info("Redis event channel={}, body={}", channel, payload);
    }
}
~~~

Trong ví dụ, publisher và subscriber thống nhất payload là chuỗi UTF-8. Nếu ứng dụng dùng JSON hoặc binary serializer khác, listener phải giải mã đúng định dạng. `message.getChannel()` biểu diễn channel thực tế; đối số `pattern` đặc biệt hữu ích khi lắng nghe bằng `PatternTopic`.

Khai báo container:

~~~java
package com.example.redis.pubsub;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class RedisPubSubConfiguration {

    @Bean
    RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory factory,
            OrderEventListener orderListener) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();
        container.setConnectionFactory(factory);
        container.addMessageListener(
            orderListener, new ChannelTopic("orders.events")
        );

        return container;
    }
}
~~~

Không cần gọi `container.start()` ngay trong `@Bean`. Spring sẽ khởi động bean theo lifecycle khi context sẵn sàng. Việc tự start quá sớm có thể khiến listener hoạt động khi các dependency của ứng dụng còn đang khởi tạo.

Publisher dùng template bình thường:

~~~java
package com.example.redis.pubsub;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long sendCreated(String orderId) {
        Long count = redis.convertAndSend(
            "orders.events", "created:" + orderId
        );
        return count == null ? 0L : count;
    }
}
~~~

`convertAndSend` thực hiện publish; kết quả trả về có thể cho biết số subscriber theo ngữ nghĩa Redis. Nó **không phải xác nhận rằng mọi callback đã xử lý thành công**, cũng không bảo đảm message được lưu để subscriber nhận sau khi online trở lại.

## 5. Các thao tác lifecycle cần chọn đúng phạm vi

| API | Phạm vi tác động | Cách dùng |
| --- | --- | --- |
| `addMessageListener(listener, topic)` | Thêm một đăng ký | Kích hoạt chức năng hoặc đăng ký channel lúc runtime |
| `removeMessageListener(listener, topic)` | Gỡ đúng cặp listener/topic | Tắt một nguồn thông báo cụ thể |
| `removeMessageListener(listener)` | Gỡ toàn bộ topic của listener | Listener không còn được sử dụng |
| `container.start()` | Khởi động toàn container | Để Spring lifecycle quản lý trong phần lớn ứng dụng |
| `container.stop()` | Dừng toàn container | Chỉ khi subsystem/container cần tạm dừng toàn bộ |
| `container.destroy()` | Hủy và giải phóng tài nguyên container | Thường do Spring thực hiện khi bean bị destroy |

Ví dụ một container có cả `orders.events` và `payments.events`. Để ngừng nhận thông báo đơn hàng:

~~~java
ChannelTopic orderTopic = new ChannelTopic("orders.events");
container.removeMessageListener(orderListener, orderTopic);
~~~

Thao tác này chỉ gỡ subscription được chỉ định. Nếu `orderListener` còn đăng ký các topic khác, những đăng ký khác không phải mục tiêu của lời gọi trên.

Nếu muốn gỡ tất cả topic của một listener:

~~~java
container.removeMessageListener(orderListener);
~~~

Nếu dùng pattern:

~~~java
import org.springframework.data.redis.listener.PatternTopic;

PatternTopic pattern = new PatternTopic("orders.*");
container.addMessageListener(auditListener, pattern);

// Khi không còn cần pattern:
container.removeMessageListener(auditListener, pattern);
~~~

Gỡ `ChannelTopic("orders.events")` không đồng nghĩa gỡ `PatternTopic("orders.*")`; cần giữ lại đúng đối tượng logic đã đăng ký.

## 6. Quản lý đăng ký động bằng một registry có chủ sở hữu

Nhiều ứng dụng cần thêm hoặc gỡ listener khi đang chạy. Ví dụ tính năng theo dõi tiến trình báo cáo được bật trong một khoảng thời gian, sau đó tắt mà những kênh khác vẫn hoạt động.

Không nên rải các lời gọi `addMessageListener` khắp nhiều controller rồi không lưu dấu vết. Một registry nên giữ chính xác listener, topic và registration handle để dễ dọn dẹp.

Ví dụ sử dụng **một registration cho mỗi channel** trong registry:

~~~java
package com.example.redis.pubsub;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

import jakarta.annotation.PreDestroy;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class DynamicSubscriptionRegistry {

    private final RedisMessageListenerContainer container;
    private final Map<String, Registration> active = new HashMap<>();

    public DynamicSubscriptionRegistry(
            RedisMessageListenerContainer container) {
        this.container = container;
    }

    public synchronized Registration register(
            String channel, MessageListener listener) {
        Objects.requireNonNull(listener);

        if (channel == null || channel.isBlank()) {
            throw new IllegalArgumentException("Channel is required");
        }
        if (active.containsKey(channel)) {
            throw new IllegalStateException(
                "Already registered: " + channel
            );
        }

        ChannelTopic topic = new ChannelTopic(channel);
        container.addMessageListener(listener, topic);

        Registration registration =
            new Registration(channel, topic, listener);
        active.put(channel, registration);
        return registration;
    }

    private synchronized void unregister(Registration registration) {
        // Chỉ handle hiện tại mới có quyền gỡ registration.
        if (active.get(registration.channel) != registration) {
            return;
        }

        container.removeMessageListener(
            registration.listener, registration.topic
        );
        active.remove(registration.channel);
    }

    @PreDestroy
    public synchronized void cleanup() {
        for (Registration registration : active.values()) {
            container.removeMessageListener(
                registration.listener, registration.topic
            );
        }
        active.clear();
    }

    public final class Registration implements AutoCloseable {
        private final String channel;
        private final ChannelTopic topic;
        private final MessageListener listener;

        private Registration(
                String channel, ChannelTopic topic,
                MessageListener listener) {
            this.channel = channel;
            this.topic = topic;
            this.listener = listener;
        }

        @Override
        public void close() {
            unregister(this);
        }
    }
}
~~~

Sử dụng:

~~~java
MessageListener listener = (message, pattern) ->
    System.out.println("Progress event received");

DynamicSubscriptionRegistry.Registration handle =
    registry.register("reports.progress", listener);

// ... trong thời gian tính năng còn hoạt động ...

handle.close();
handle.close(); // Hủy lần hai không ảnh hưởng registration mới.
~~~

Đoạn mã đảm bảo một channel trong registry có một owner và handle cũ không thể vô tình xóa registration mới cùng tên. Nếu nghiệp vụ cần nhiều listener cho một channel, nên dùng `registrationId` để quản lý **từng cặp listener/topic** thay vì khóa bản đồ chỉ theo tên channel.

Lưu ý: `addMessageListener` **ghi nhận yêu cầu đăng ký tại container**; Redis có thể xác nhận subscription bất đồng bộ. Vừa gọi `register(...)` xong rồi publisher phát ngay trong cùng thời điểm không bảo đảm message đầu tiên luôn được nhận.

Registry cũng nên có chính sách giới hạn số subscription động. Nếu tạo một Redis subscription cho mỗi HTTP request, WebSocket, người dùng hoặc thao tác ngắn mà không giới hạn, ứng dụng có thể tăng số listener và tài nguyên cần quản lý không kiểm soát.

## 7. Container sở hữu connection, listener sở hữu xử lý message

Với `RedisMessageListenerContainer` do Spring quản lý:

~~~text
Spring ApplicationContext
           |
           +-- RedisConnectionFactory
           |
           +-- RedisMessageListenerContainer
           |        |
           |        +-- Channel / Pattern subscriptions
           |        +-- Connection nhận message
           |        +-- Dispatch callback
           |
           +-- MessageListener beans
           |
           +-- DynamicSubscriptionRegistry
                    |
                    +-- Registration handles
~~~

Container quản lý connection subscriber. Khi gỡ một listener, **không tự đóng Redis connection mà container còn dùng chung**. Đóng connection không đúng chỗ có thể làm gián đoạn các subscription khác.

Đối với connection tạo thủ công bằng `RedisConnectionFactory.getConnection()`, mã tạo connection phải sở hữu điểm dừng:

~~~text
Tạo worker nhận message
          |
          v
Lấy RedisConnection dành riêng
          |
          v
SUBSCRIBE / PSUBSCRIBE
          |
          v
Nhận message cho đến khi được yêu cầu dừng
          |
          v
UNSUBSCRIBE / PUNSUBSCRIBE
          |
          v
Kết thúc worker và đóng RedisConnection
~~~

`RedisConnection.subscribe(...)` cấp thấp có thể chiếm luồng trong lúc lắng nghe. API hủy subscription và cách phối hợp thread phụ thuộc driver; cần tuân theo hợp đồng của Lettuce/Jedis thực tế. Vì mục tiêu quản lý tập trung, phần lớn ứng dụng Spring nên dùng listener container.

Trong Pub/Sub truyền thống, connection đang ở trạng thái subscription có thể bị giới hạn các command được phép gửi. Không coi connection dùng để nhận message như connection bình thường cho `GET`, `SET` và các thao tác nghiệp vụ khác.

## 8. Bắt đầu/dừng cùng Spring ApplicationContext

Một container khai báo thành Spring bean thường trải qua:

~~~text
Tạo bean và nhận connection factory
                |
                v
Ghi nhận danh sách listener/topic
                |
                v
Spring start lifecycle
                |
                v
Container subscribe và dispatch message
                |
        ApplicationContext shutdown
                |
                v
Spring stop lifecycle
                |
                v
Container ngừng nhận, dọn subscription
                |
                v
Spring destroy bean / giải phóng tài nguyên
~~~

Không tự gọi `container.start()` từ constructor của service hoặc `@Bean` chỉ vì muốn “chắc chắn chạy”. Khi start/stop được gọi từ nhiều nơi, việc xác định trạng thái thật và xử lý race condition khó hơn.

Khi shutdown có kiểm soát, ứng dụng nên ngừng tiếp nhận công việc tạo subscription mới, gỡ những registration động cần thiết, hạn chế công việc callback đang chờ, rồi để Spring đóng container.

**`stop()` không đồng nghĩa message đã xử lý xong ở tầng nghiệp vụ.** Nếu callback đã nhận payload rồi đẩy sang một executor khác, việc dừng listener container không tự chờ mọi side effect bất đồng bộ hoàn tất. Nếu cần chờ công việc, phải quản lý riêng lifecycle và thời hạn shutdown của executor/hàng đợi đó.

Khi process bị kill đột ngột hoặc mất điện, `@PreDestroy` có thể không chạy; Pub/Sub message đang truyền cũng không được bảo đảm lưu lại. Thiết kế không được phụ thuộc vào graceful shutdown để đảm bảo delivery tuyệt đối.

## 9. Điều chỉnh thread, queue và xử lý lỗi callback

Listener nên xử lý nhanh. Nếu `onMessage` gọi database chậm hoặc HTTP tới dịch vụ bên ngoài, một đợt message dồn dập có thể khiến callback chậm và subscriber không theo kịp publisher.

`RedisMessageListenerContainer` hỗ trợ executor để chạy các callback. Ví dụ khai báo pool có giới hạn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
ThreadPoolTaskExecutor redisListenerExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("redis-listener-");
    return executor;
}
~~~

Trong cấu hình container có thể inject executor và gắn:

~~~java
container.setTaskExecutor(redisListenerExecutor);
~~~

Đoạn trên nằm trong phương thức cấu hình container, với `redisListenerExecutor` là bean đã được inject. Executor dùng cho dispatch và executor phục vụ subscription có nhu cầu khác nhau; không mặc định mọi tác vụ nên chia cùng một pool.

Một pool giới hạn cần có chính sách khi hàng đợi đầy: báo lỗi, từ chối, backpressure hoặc chuyển vào một hàng đợi có hợp đồng delivery rõ ràng. Dùng một `@Async` với executor không giới hạn không tạo ra bảo đảm xử lý bền vững.

Để log lỗi từ listener container:

~~~java
container.setErrorHandler(error ->
    log.error("Redis Pub/Sub listener failed", error)
);
~~~

Đoạn này giả định có logger `log` phù hợp trong cấu hình. Error handler giúp quan sát exception, **không ACK message** và không làm Redis tự gửi lại payload đã mất.

Nếu một message là yêu cầu thanh toán, tạo đơn hàng hoặc thao tác cần thực hiện ít nhất một lần, không nên coi một callback Pub/Sub là hàng đợi đáng tin cậy. Cần chuyển sang cơ chế có lưu trữ và xác nhận xử lý.

## 10. Mất kết nối, reconnect và message bị bỏ lỡ

Redis có thể restart, failover hoặc bị lỗi mạng. Container có khả năng xử lý và khôi phục subscription sau các lỗi kết nối theo lifecycle và cấu hình client. Nhưng hai việc phải được phân biệt:

- **Reconnect/resubscribe:** mở kết nối và đăng ký lại để nhận message mới.
- **Replay missed messages:** lấy lại những message đã publish khi subscriber không hoạt động.

Redis Pub/Sub thông thường hỗ trợ **truyền tới subscriber online**; nó không giữ một log bền vững để tự phát lại message cho subscriber mới.

~~~text
Publisher                Redis                  Subscriber
   |                       |                        |
   +--- event A ---------->|----------------------->| nhận A
   |                       |                        |
   |                       X         kết nối mất    |
   +--- event B ---------->|                        | không nhận B
   +--- event C ---------->|                        | không nhận C
   |                       |                        |
   |                       |<--- kết nối lại --------|
   |                       |<--- SUBSCRIBE ----------|
   +--- event D ---------->|----------------------->| nhận D
~~~

Không nên lấy số subscriber trả về từ `PUBLISH` làm bằng chứng rằng callback đã cập nhật database thành công. Cũng không nên coi sự kiện reconnect là bảo đảm hệ thống đã xử lý đủ mọi thay đổi trong thời gian mất kết nối.

Nếu subscriber phải khôi phục trạng thái, có thể đọc một nguồn dữ liệu bền vững sau khi kết nối lại. Nếu phải lưu từng event và có ACK/retry, hãy cân nhắc Redis Streams hoặc message broker phù hợp.

### So sánh Redis Pub/Sub và Redis Streams

| Yêu cầu | Redis Pub/Sub | Redis Streams |
| --- | --- | --- |
| Phát sự kiện tới subscriber đang online | Phù hợp | Có thể triển khai |
| Người nghe offline rồi lấy lại sự kiện | Không hỗ trợ theo ngữ nghĩa Pub/Sub truyền thống | Có thể qua stream entries và cursor/retention thích hợp |
| Xác nhận message đã được consumer xử lý | Không có ACK xử lý tích hợp | Consumer group và `XACK` |
| Retry công việc chưa xử lý | Ứng dụng tự thiết kế thêm | Có PEL và các cơ chế claim/retry |
| Phân chia công việc giữa consumer trong nhóm | Không; các subscriber đều có thể nhận message | Consumer group có thể phân phối message |

Redis Streams cũng không tự bảo đảm side effect nghiệp vụ “exactly once” khi consumer retry; thiết kế idempotency vẫn cần thiết.

## 11. Đăng ký trong hệ thống nhiều instance

Giả sử ba instance của cùng một ứng dụng đều subscribe `orders.events`:

~~~text
                   Redis orders.events
                    /      |       \
                   v       v        v
                 App A    App B    App C
~~~

Mỗi instance có một subscriber riêng, và một message publish có thể được cả ba instance nhận. Đây là hành vi **broadcast**, không phải cơ chế worker queue phân phối một message cho đúng một instance.

Nếu cả ba listener đều gọi logic “gửi email hóa đơn”, có thể phát sinh ba email. Muốn chỉ một worker thực hiện, cần dùng consumer group/queue hoặc cơ chế điều phối duy nhất phù hợp.

Nếu một instance quản lý nhiều WebSocket client, thường hiệu quả hơn khi có listener ở cấp ứng dụng nhận channel chung rồi định tuyến trong bộ nhớ đến những WebSocket tương ứng. Không nên tạo Redis subscriber vô hạn cho từng WebSocket nếu số lượng client lớn.

Ngoài ra, channel thường là namespace logic; tên channel không tự cấp quyền theo người dùng cuối. Với hệ thống nhiều tenant, cần kiểm tra authorization trước khi đăng ký hoặc chuyển message tới một client cụ thể.

## 12. Kiểm thử với Redis thực, không phụ thuộc chờ cố định

Do việc đăng ký diễn ra bất đồng bộ, test kiểu “add listener, publish một lần ngay lập tức, đợi 100 ms” dễ thất bại ngẫu nhiên. Hãy dùng một điều kiện có timeout để chứng minh callback đã nhận message và gỡ đăng ký trong `finally`.

Ví dụ tích hợp JUnit 5 + Spring Boot + Testcontainers + Awaitility:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.awaitility:awaitility'
}
~~~

~~~java
package com.example.redis.pubsub;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@Testcontainers
@SpringBootTest(classes = PubSubLifecycleTest.TestApp.class)
class PubSubLifecycleTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {

        @Bean
        RedisMessageListenerContainer listenerContainer(
                RedisConnectionFactory connectionFactory) {
            RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();
            container.setConnectionFactory(connectionFactory);
            return container;
        }
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
    }

    @Autowired RedisMessageListenerContainer container;
    @Autowired StringRedisTemplate publisher;

    @Test
    void receivesAndUnregistersDynamicListener() {
        String channel = "it:pubsub:" + UUID.randomUUID();
        ChannelTopic topic = new ChannelTopic(channel);
        CountDownLatch received = new CountDownLatch(1);

        MessageListener listener = (message, pattern) -> {
            String body = new String(
                message.getBody(), StandardCharsets.UTF_8
            );
            if ("hello".equals(body)) {
                received.countDown();
            }
        };

        container.addMessageListener(listener, topic);
        try {
            // Có thể mất một khoảng ngắn trước khi Redis xác nhận SUBSCRIBE.
            // Publish lại theo polling cho tới lúc callback nhận "hello".
            await()
                .atMost(Duration.ofSeconds(8))
                .pollInterval(Duration.ofMillis(100))
                .until(() -> {
                    publisher.convertAndSend(channel, "hello");
                    return received.await(
                        100, TimeUnit.MILLISECONDS
                    );
                });

            assertThat(received.getCount()).isZero();
        } finally {
            container.removeMessageListener(listener, topic);
        }
    }
}
~~~

Test sử dụng một channel độc lập bằng UUID. Khi thành công, nó chứng minh hệ thống đã đăng ký và dispatch ít nhất một message thực sự. `finally` giúp tránh để lại listener trong context test ngay cả khi điều kiện nhận message thất bại.

Phép thử này **không khẳng định unsubscribe đã tạo một hàng rào tuyệt đối đối với mọi callback từng được xếp hàng trước đó**. Nếu nghiệp vụ đòi hỏi không xử lý bất cứ message nào sau một mốc dừng, listener cần kiểm tra thêm trạng thái hoạt động của chính nó; có thể thiết kế một test đồng bộ với barrier hoặc kiểm tra trạng thái subscription phù hợp.

Không nên thay bằng `Thread.sleep(200)` rồi khẳng định không có message sau khi gỡ listener: việc không quan sát được callback trong 200 ms không chứng minh registration đã được gỡ hoàn toàn ở Redis.

## 13. Công cụ chẩn đoán và giám sát

Redis cung cấp một số lệnh kiểm tra Pub/Sub:

~~~redis
PUBSUB CHANNELS
PUBSUB CHANNELS orders.*
PUBSUB NUMSUB orders.events payments.events
PUBSUB NUMPAT
CLIENT LIST
~~~

- `PUBSUB CHANNELS` phản ánh các channel đang có subscriber trực tiếp theo ngữ nghĩa lệnh; không đại diện cho mọi pattern subscription.
- `PUBSUB NUMSUB` cung cấp số subscriber trực tiếp ở các channel được hỏi.
- `PUBSUB NUMPAT` cung cấp số pattern subscriptions.
- `CLIENT LIST` có thể giúp theo dõi client Pub/Sub và tình trạng kết nối/bộ đệm.

Trong Redis Cluster, cách quan sát có thể phụ thuộc node và loại Pub/Sub. Đừng suy luận một lệnh gọi tới một node nhất định sẽ thể hiện đầy đủ mọi subscription trên toàn cluster.

Tại ứng dụng, các metric nên theo dõi gồm:

| Metric | Mục tiêu |
| --- | --- |
| Số subscription channel/pattern đang hoạt động | Phát hiện leak hoặc đăng ký trùng |
| Số message callback nhận mỗi giây | Theo dõi traffic |
| Callback duration p95/p99 | Phát hiện công việc xử lý quá chậm |
| Lỗi khi xử lý message | Phát hiện lỗi mà publisher không thấy |
| Số lần reconnect/resubscribe | Quan sát mạng và Redis availability |
| Executor queue depth/rejection | Phát hiện quá tải subscriber |
| Số message bỏ qua vì ứng dụng đang dừng | Hiểu tradeoff của shutdown và chính sách xử lý |

Tránh gắn nhãn metric theo hàng triệu ID người dùng/channel động vì dễ tạo cardinality không kiểm soát.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Publish thành công nhưng listener không nhận | Subscription chưa sẵn sàng, tên channel khác nhau hoặc Redis mất kết nối | Kiểm tra channel, trạng thái container và thời điểm subscribe |
| Sau restart không nhận lại message cũ | Pub/Sub không lưu message để phát lại | Dùng Redis Streams/queue hoặc đồng bộ trạng thái từ nguồn bền vững |
| Listener được gọi nhiều lần cho một message | Đăng ký trùng, hoặc channel và pattern cùng khớp | Quản lý registration và pattern rõ ràng |
| Tắt tính năng A làm cả B ngừng nghe | Gọi `container.stop()` trên container dùng chung | Gỡ `listener/topic` cụ thể |
| Tăng connection/thread theo số request | Tạo subscriber thủ công nhưng không có cleanup | Dùng container/registry và giới hạn số subscription |
| Callback nhận message nhưng xử lý thất bại | Pub/Sub không có ACK xử lý nghiệp vụ | Log, metric và cơ chế retry bền vững nếu cần |
| `close()` làm mọi listener gián đoạn | Đóng connection do container sở hữu | Để container quản lý connection |
| Subscriber online nhưng không nhận message lúc failover | Connection bị gián đoạn và có khoảng mất subscription | Theo dõi reconnect; không kỳ vọng replay |
| Nhiều instance cùng xử lý một sự kiện | Pub/Sub broadcast | Dùng consumer group hoặc điều phối riêng nếu cần một worker |
| Không thấy channel trong `PUBSUB CHANNELS` | Chỉ có pattern subscription hoặc chưa có subscriber trực tiếp | Dùng lệnh quan sát đúng loại subscription |
| Test đôi khi mất message đầu tiên | Lệnh subscribe bất đồng bộ | Polling có timeout và kiểm thử với Redis thật |
| Sau unregister vẫn thấy một callback chạy | Message đã được dispatch trước khi hủy | Theo dõi in-flight task, có cờ trạng thái nghiệp vụ và shutdown policy |

## 15. Thiết kế vòng đời subscriber đáng tin cậy

Khi triển khai Redis Pub/Sub với Spring Data Redis, hãy quyết định rõ những điểm sau:

1. **Listener tồn tại bao lâu?** Với listener chạy suốt đời ứng dụng, đăng ký trong bean config. Với listener ngắn hạn, dùng registry có handle.
2. **Ai được quyền gỡ đăng ký?** Ghi nhớ đúng cặp listener/topic; không gọi `stop()` trên container dùng chung cho một tính năng đơn lẻ.
3. **Ai đóng connection?** Nếu dùng container, container quản lý connection và Spring quản lý lifecycle bean. Nếu dùng RedisConnection thủ công, chính mã tạo nó phải dọn tài nguyên.
4. **Làm sao biết subscription sẵn sàng?** Không coi `addMessageListener` trả về là bằng chứng Redis đã nhận đăng ký; test hoặc quy trình cần sẵn sàng ngay phải có đồng bộ phù hợp.
5. **Khi ứng dụng dừng thì sao?** Ngừng đăng ký mới, xử lý in-flight task trong ngân sách, gỡ đăng ký thuộc quyền sở hữu và để Spring giải phóng container.
6. **Khi Redis mất kết nối thì sao?** Container có thể kết nối lại và subscribe lại; những message phát trong khoảng offline vẫn không được phát lại.
7. **Thông điệp có quan trọng không?** Nếu bắt buộc xử lý bền vững, dùng Streams hoặc message broker có cơ chế lưu, ACK và retry thay vì chỉ dựa vào Pub/Sub.

Quản lý vòng đời bằng `RedisMessageListenerContainer` giúp subscriber trong Spring Data Redis có ranh giới tài nguyên rõ ràng: **đăng ký đúng nơi, gỡ đúng phạm vi và đóng kết nối khi chủ sở hữu kết thúc**. Cơ chế đó làm ứng dụng dễ vận hành và kiểm soát hơn, đồng thời giữ nguyên sự thật quan trọng của Redis Pub/Sub: message chỉ được truyền tức thời cho những subscriber đang hoạt động.

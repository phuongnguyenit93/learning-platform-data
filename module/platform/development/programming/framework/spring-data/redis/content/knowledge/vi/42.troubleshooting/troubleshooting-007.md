# Listener không nhận thông điệp hoặc sự kiện hết hạn

Trong một ứng dụng Spring Boot sử dụng Spring Data Redis, listener có thể được dùng để nhận **thông điệp Pub/Sub** của ứng dụng, nhận **keyevent/keyspace notifications** của Redis, hoặc xử lý **sự kiện hết hạn của entity** được quản lý bằng Redis Repository. Cả ba đều thường được gọi ngắn gọn là “Redis listener”, nhưng chúng khác nhau về **nguồn phát, channel, cấu hình và điều kiện nhận**.

Khi listener “không chạy”, vấn đề có thể đơn giản là publisher gửi vào channel khác, listener chưa đăng ký xong trước khi thông điệp được phát, Redis không bật thông báo expired, subscriber kết nối nhầm database, hoặc callback đã nhận thông điệp nhưng ném exception ở bước giải mã. Với Redis Cluster/Sentinel, còn có rủi ro kết nối cũ sau failover hoặc đăng ký trên node không phát keyevent cần theo dõi.

Bài học này cung cấp **quy trình chẩn đoán có thể lặp lại** cho Spring Data Redis: tái hiện bằng Redis CLI, kiểm tra trạng thái Redis, cấu hình `RedisMessageListenerContainer`, theo dõi subscriber lifecycle, phân biệt `SUBSCRIBE` với `PSUBSCRIBE`, bật đúng keyspace notifications, xác minh TTL và khám phá những giới hạn của Pub/Sub, expiration events và Redis Repository.

> Nguyên tắc: **chứng minh Redis thực sự đã phát đúng thông điệp trên đúng channel trước, rồi mới tìm lỗi trong Spring listener**. Không sửa timeout, serializer và connection pool cùng một lúc khi chưa xác định nơi tín hiệu bị mất.

## 1. Nhận diện chính xác loại listener

Ba nguồn sự kiện thường gặp:

| Loại | Ai phát? | Ví dụ | Điều kiện nhận |
| --- | --- | --- | --- |
| **Application Pub/Sub** | Code gọi `PUBLISH` hoặc `convertAndSend` | Channel `orders.events` có message `order-created:42` | Subscriber đã đăng ký đúng channel/pattern, kết nối còn sống |
| **Redis keyevent notification** | Redis tự phát khi một key thay đổi theo loại sự kiện đã bật | `__keyevent@0__:expired`, body là tên key | Server bật `notify-keyspace-events` thích hợp; listener ở đúng node/DB/channel |
| **Repository expiration event** | Spring Data Redis lắng nghe Redis expiration rồi phát Spring application event | `RedisKeyExpiredEvent<?>` cho entity `@RedisHash` có TTL | Redis notifications, repository keyspace-event listener và lifecycle ứng dụng đã được cấu hình |

Chúng có thể liên quan, nhưng không hoán đổi cho nhau:

~~~text
                    Application PUBLISH
                            |
                            v
                       orders.events
                            |
                            v
                RedisMessageListenerContainer
                            |
                            v
                   MessageListener callback

       Redis key có TTL, server xóa key lúc hết hạn
                            |
                            v
              __keyevent@0__:expired
                            |
                  +---------+---------+
                  |                   |
                  v                   v
           Listener tự viết    Repository keyspace
                               event listener
                                      |
                                      v
                          RedisKeyExpiredEvent
                                      |
                                      v
                             @EventListener
~~~

Nếu nghiệp vụ yêu cầu **không được bỏ sót thông điệp**, Redis Pub/Sub và keyspace notifications thường không phải lựa chọn đủ mạnh: chúng là cơ chế phát tới những subscriber đang kết nối, **không tự lưu hàng đợi chờ subscriber quay lại**. Cần cân nhắc Redis Streams, một message broker bền vững hoặc nguồn dữ liệu có outbox/đối soát.

## 2. Dấu hiệu và câu hỏi cần kiểm tra trước

| Triệu chứng | Giả thuyết ưu tiên | Kiểm tra đầu tiên |
| --- | --- | --- |
| Listener chưa từng nhận bất cứ message nào | Không subscribe, sai channel, sai endpoint, container chưa start | Thử `SUBSCRIBE`/`PUBLISH` bằng hai Redis CLI |
| Chỉ mất message đầu tiên sau startup | Subscription chưa sẵn sàng, publish quá sớm | Kiểm tra thời điểm registration và publisher |
| Lúc nhận lúc không | Mất connection, failover, subscription lifecycle, callback lỗi | Log reconnect, listener error handler, quan sát Redis connection |
| Có message ở CLI nhưng không ở Spring | Spring config, pattern topic, callback/serializer, executor | Kiểm tra container, `MessageListener` và stack trace |
| Spring nhận Pub/Sub thường, nhưng không nhận expired | `notify-keyspace-events` thiếu `E`/`x` hoặc subscribe sai channel | `CONFIG GET notify-keyspace-events`; thử `SET ... EX` |
| Key không còn mà không có expired event | Key bị `DEL`/overwrite/evict hoặc event bị mất | Kiểm tra lệnh thay đổi key, loại notification |
| Entity `@TimeToLive` đã mất nhưng `@EventListener` không chạy | Repository event listener chưa bật, notification bị tắt hoặc không đúng lifecycle | `@EnableRedisRepositories`, TTL, Redis notifications |
| Một số key Cluster phát event, số khác không | Keyevent phát tại node giữ key, subscriber không phủ đủ node | Xác định slot/node và các subscription |
| Listener “chết” sau một message | Callback ném lỗi, task executor cạn hoặc logic block | Error handler, thread dump, log trước/sau callback |
| `convertAndSend` trả `0` | Không có subscriber nhận tại thời điểm publish hoặc ngữ cảnh subscription không khớp | Kiểm tra listener đã sẵn sàng và cách đếm subscriber |

Hai câu hỏi quan trọng khi nhận báo lỗi:

1. **Không có message được phát?** Redis không tạo notification, publisher không gọi `PUBLISH` hoặc gọi vào endpoint khác.
2. **Message có phát nhưng ứng dụng không xử lý?** Subscription sai, kết nối mất, callback lỗi hoặc application lifecycle chưa đúng.

Không thể giải quyết nhóm thứ nhất chỉ bằng việc tăng thread cho listener; cũng không giải quyết nhóm thứ hai chỉ bằng cách bật thêm Redis notification flags.

## 3. Redis Pub/Sub không lưu message để phát lại

Redis Pub/Sub phát message cho những client đang subscribe tại thời điểm publish:

~~~text
T0  Publisher gửi PUBLISH orders.events "event-1"
T1  Subscriber A mới đăng ký SUBSCRIBE orders.events
T2  Publisher gửi PUBLISH orders.events "event-2"

Subscriber A thấy: event-2
Subscriber A không tự nhận lại event-1
~~~

Điều này đặc biệt dễ gây lỗi trong integration test hoặc khi service vừa restart. Đoạn code tạo `MessageListener` bean **không đồng nghĩa server đã hoàn tất SUBSCRIBE** tại đúng mili giây một publisher khác gửi event.

Các đặc điểm cần ghi nhớ:

- **Fire-and-forget:** message đã publish khi subscriber offline thường không có replay.
- **At-most-once theo mô hình Pub/Sub:** subscriber có thể bỏ lỡ message vì disconnect hoặc không được đăng ký; không có ACK để yêu cầu phát lại.
- **Broadcast:** nếu ba instance cùng subscribe một channel thường, cả ba có thể nhận cùng message, không phải chỉ một worker.
- **Không phải queue:** nếu nghiệp vụ cần một nhóm worker chia nhau xử lý mỗi event, hãy xem Redis Streams consumer groups hoặc queue phù hợp.
- **Không phải durable event log:** ngay cả keyspace notifications cũng dựa trên Pub/Sub và có giới hạn tương tự về việc mất sự kiện.

Chẩn đoán một message bị mất phải luôn ghi **thời điểm publish so với thời điểm subscription đã sẵn sàng**.

## 4. Kiểm tra application Pub/Sub bằng hai Redis CLI

Trước khi sửa Spring, thử một quy trình tối giản trên **chính Redis endpoint/credential/database** mà ứng dụng sử dụng.

### Terminal A: subscribe

~~~bash
redis-cli -h 127.0.0.1 -p 6379 -n 0 SUBSCRIBE orders.events
~~~

Giữ terminal này mở. Lệnh sẽ chờ message tới channel `orders.events`.

### Terminal B: publish

~~~bash
redis-cli -h 127.0.0.1 -p 6379 -n 0 \
  PUBLISH orders.events "diagnostic-event-001"
~~~

Nếu Terminal A hiện message `diagnostic-event-001`, có thể xác nhận **Redis server và đường Pub/Sub cho channel thử nghiệm đang hoạt động**. Nếu không thấy, kiểm tra server/port/TLS/ACL, lệnh đang trỏ tới cùng Redis hay không, và terminal A đã thật sự subscribe chưa.

Lưu ý: với **application Pub/Sub thường**, channel **không được namespace theo database** giống key dữ liệu. Tham số `-n 0` trong ví dụ giúp nhất quán kết nối thử nghiệm, nhưng **không biến `orders.events` thành channel riêng của DB 0**. Ngược lại, tên channel keyevent có `@0` nằm trong chính chuỗi channel và chỉ sự kiện từ Redis database tương ứng.

### Quan sát subscriber

~~~redis
PUBSUB CHANNELS
PUBSUB CHANNELS orders.*
PUBSUB NUMSUB orders.events
PUBSUB NUMPAT
~~~

Giải thích:

| Lệnh | Có thể biết gì? | Giới hạn |
| --- | --- | --- |
| `PUBSUB CHANNELS` | Những channel có subscriber trực tiếp, theo ngữ nghĩa lệnh | Không thay cho việc liệt kê mọi pattern subscription |
| `PUBSUB NUMSUB orders.events` | Số subscriber trực tiếp của channel | Không tính subscriber chỉ theo pattern |
| `PUBSUB NUMPAT` | Số pattern subscription hiện có | Không chỉ ra pattern nào tương ứng channel mong muốn |

Nếu Spring dùng `PatternTopic("orders.*")`, `PUBSUB NUMSUB orders.events` có thể trả `0` dù pattern subscriber đang hoạt động. Không kết luận “không có listener” chỉ từ số `NUMSUB` trong trường hợp đó.

**Hạn chế của số đếm:** các lệnh quan sát có ngữ nghĩa phụ thuộc topology khi dùng Redis Cluster; hãy kiểm tra đúng node/shard và loại regular/sharded Pub/Sub nếu hệ thống dùng cả hai. Với một Redis standalone dùng cho lab, chúng đơn giản hơn nhiều.

### Channel và pattern khác nhau

Redis:

~~~redis
SUBSCRIBE orders.events
PSUBSCRIBE orders.*
~~~

Spring Data Redis:

~~~java
new ChannelTopic("orders.events");
new PatternTopic("orders.*");
~~~

`ChannelTopic` đăng ký channel chính xác. `PatternTopic` đăng ký pattern theo cú pháp pattern của Redis. Nếu publisher gửi `orders.created` nhưng listener dùng `ChannelTopic("orders.*")`, listener chỉ đăng ký **tên channel literal** `orders.*`, không nhận mọi channel có prefix `orders.`.

Tương tự, `PatternTopic("orders.created")` vẫn là một pattern cụ thể; không tự nhận `orders.updated`. Luôn kiểm tra cả **chuỗi channel**, pattern syntax và xem publisher có đang dùng namespace khác nhau theo môi trường không.

## 5. Cấu hình `RedisMessageListenerContainer` trong Spring Boot

`RedisMessageListenerContainer` quản lý việc đăng ký listener lên Redis và chuyển những message nhận được tới callback. So với tự mở connection rồi giữ thread gọi `SUBSCRIBE`, container tích hợp với Spring lifecycle, có thể gắn nhiều listener/topic và cung cấp điểm cấu hình executor/error handler.

Ví dụ dùng Spring Boot 3.x, Java 21 và `spring-boot-starter-data-redis`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Tạo cấu hình:

~~~java
package com.example.redis.diagnostics;

import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.PatternTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class RedisListenerConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(RedisListenerConfiguration.class);

    @Bean("ordersMessageListener")
    MessageListener ordersMessageListener() {
        return (Message message, byte[] pattern) -> {
            String channel = new String(
                message.getChannel(), StandardCharsets.UTF_8
            );
            String body = new String(
                message.getBody(), StandardCharsets.UTF_8
            );

            // Demo: không làm I/O chậm trong callback.
            log.info(
                "Application Pub/Sub received channel={} payloadLength={}",
                channel, body.length()
            );
            // Gọi adapter xử lý payload theo schema nghiệp vụ.
        };
    }

    @Bean("expiredKeyListener")
    MessageListener expiredKeyListener() {
        return (Message message, byte[] pattern) -> {
            String channel = new String(
                message.getChannel(), StandardCharsets.UTF_8
            );
            String key = new String(
                message.getBody(), StandardCharsets.UTF_8
            );

            log.info(
                "Redis expired event received channel={} key={}",
                channel, key
            );
            // Demo local: key chỉ là tên key đã hết hạn.
            // Không mặc định value còn tồn tại để GET.
        };
    }

    @Bean
    RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory connectionFactory,
            @Qualifier("ordersMessageListener")
            MessageListener orders,
            @Qualifier("expiredKeyListener")
            MessageListener expired) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);

        // Kênh ứng dụng: match chính xác tên.
        container.addMessageListener(
            orders, new ChannelTopic("orders.events")
        );

        // Đăng ký theo tên channel keyevent của database 0.
        container.addMessageListener(
            expired,
            new PatternTopic("__keyevent@0__:expired")
        );

        container.setErrorHandler(error ->
            log.error("Redis message listener callback failed", error)
        );

        return container;
    }
}
~~~

Đây là hai listener **khác nhau** để tách việc chẩn đoán. Callback cho `orders.events` xử lý body như payload ứng dụng; callback expired xử lý body như **tên key** đã bị Redis xóa do hết hạn. Không dùng chung một parser JSON cho cả hai.

Trong production, tránh log toàn bộ body nếu nó chứa dữ liệu người dùng, session token hoặc thông tin bí mật. Các bản ghi log nên có channel, loại sự kiện, key namespace đã được ẩn danh, correlation ID và độ dài payload.

### 5.1. Spring lifecycle và thời điểm subscribe

Một `RedisMessageListenerContainer` được khai báo làm Spring bean thường được Spring quản lý start/stop theo lifecycle. Tuy nhiên:

- Bean được khởi tạo **không đồng nghĩa** subscriber đã sẵn sàng trên Redis.
- Listener có thể đang đợi connection hoặc đang đăng ký lại sau lỗi.
- Một service khác có thể publish trong lúc ứng dụng đang khởi động.
- Khi context đóng, container dừng listener và giải phóng tài nguyên subscription theo cơ chế quản lý của nó.

Nếu ứng dụng phải tránh mất message đầu tiên, một lời gọi `ApplicationReadyEvent` không đủ làm bằng chứng chắc chắn subscription đã được Redis ghi nhận. Cần một **điều kiện sẵn sàng có thể quan sát được** hoặc thiết kế event durable thay vì phụ thuộc vào timing.

### 5.2. Vì sao không gọi `SUBSCRIBE` trực tiếp trên shared connection?

Kết nối đang ở chế độ Pub/Sub có những giới hạn về lệnh có thể thực hiện trên cùng connection, phụ thuộc mode và phiên bản Redis. Nếu lấy một connection dùng chung rồi gọi `SUBSCRIBE` và tiếp tục gửi các lệnh khác, ứng dụng dễ gặp lỗi trạng thái connection hoặc chặn thread.

Với Spring Data Redis, nên để `RedisMessageListenerContainer` sở hữu lifecycle subscription. Không gọi `connection.close()` thủ công trên connection do container đang quản lý; hành động đó có thể khiến container mất kết nối, cần reconnect và bỏ lỡ message.

### 5.3. Task executor có thể làm callback xử lý chậm

Mỗi message đến cần được dispatch tới listener. Nếu callback thực hiện một lời gọi HTTP kéo dài, chờ khóa, parse payload cực lớn hoặc chặn một thread trong thời gian dài, throughput và độ trễ callback sẽ bị ảnh hưởng.

Một sơ đồ lỗi điển hình:

~~~text
Redis PUBLISH liên tục
          |
          v
Subscription connection vẫn nhận bytes
          |
          v
Listener dispatch / task executor
          |
          +--> callback A gọi HTTP và chờ lâu
          +--> callback B xử lý JSON lớn
          +--> nhiều callback xếp hàng
          |
          v
Ứng dụng trông như "không nhận message"
~~~

Nếu dự án cấu hình `container.setTaskExecutor(...)`, phải xem:

- Số worker, queue capacity và rejection policy.
- Callback có blocking hay không.
- Tốc độ message tới so với tốc độ xử lý được.
- Số listener và những consumer dùng chung executor.
- Có task executor riêng cho việc quản lý subscription nếu driver/cấu hình cần không.

Không tự tăng thread vô hạn để chữa lỗi callback chậm. Một listener chỉ nên làm công việc ngắn, có giới hạn; đối với xử lý dài hoặc cần retry bền vững, chuyển message sang một queue/Stream phù hợp.

## 6. Publisher trong Spring: kiểm tra chính xác channel và dữ liệu

Một publisher dùng `StringRedisTemplate`:

~~~java
package com.example.redis.diagnostics;

import java.util.Objects;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrdersPublisher {

    public static final String CHANNEL = "orders.events";

    private final StringRedisTemplate redis;

    public OrdersPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long publish(String message) {
        Objects.requireNonNull(message, "message");

        Long receivers = redis.convertAndSend(
            CHANNEL, message
        );
        return receivers == null ? 0L : receivers;
    }
}
~~~

`convertAndSend` chuyển thông điệp theo serializer của template và gửi `PUBLISH`. Giá trị trả về thường biểu thị số subscriber đã được gửi đến tại thời điểm publish, không phải ACK rằng code xử lý của mọi consumer đã chạy thành công.

Với template đồng bộ trong đường gọi trực tiếp, một kết quả bằng `0` cho thấy **không có người nhận được Redis đếm được trong ngữ cảnh publish đó**. Nhưng không dùng con số này làm bảo đảm end-to-end delivery hoặc trạng thái database của consumer. Trong chế độ pipeline/transaction và cấu hình đặc biệt, cần tuân theo hợp đồng API trả về của template thay vì gán nghĩa cứng cho `null`.

### Serializer mismatch có thể làm callback nhìn như bỏ qua message

Giả sử publisher gửi JSON string:

~~~java
redis.convertAndSend(
    "orders.events",
    "{\"eventId\":\"evt-42\",\"type\":\"CREATED\"}"
);
~~~

Nhưng receiver dùng một serializer JDK hoặc parser khác để đọc bytes:

~~~text
Redis đã phát đúng message
          |
          v
Listener nhận byte[] hợp lệ
          |
          v
Deserialize theo format sai
          |
          v
Exception / callback ngừng xử lý
~~~

Nếu chỉ log khi xử lý nghiệp vụ **thành công**, hệ thống có thể báo “không nhận” dù callback đã chạy rồi ném lỗi. Khi chẩn đoán:

1. Ghi log/metric một sự kiện `message_received` **trước bước parse**.
2. Ghi riêng lỗi `decode_failed` sau khi parse không thành công.
3. Đặt serializer/parser và schema version rõ ràng giữa publisher và subscriber.
4. Không để một payload sai khiến listener ngừng nhận các message khác mà không có báo lỗi.

Với listener nhận raw `Message` như ví dụ, `message.getBody()` là byte array; việc gọi `new String(..., UTF_8)` chỉ là ví dụ cho payload text. Nếu dữ liệu là binary hoặc JSON có ràng buộc bảo mật, cần parser có giới hạn kích thước, schema và loại dữ liệu trước khi dùng trong nghiệp vụ.

### Theo dõi lỗi listener

`container.setErrorHandler(...)` giúp ghi nhận exception phát sinh trong quá trình xử lý listener ở container. Nó **không thay thế** instrumentation riêng cho lỗi parse, lỗi nghiệp vụ hoặc các tác vụ bất đồng bộ mà callback tạo ra rồi trả ngay.

Ví dụ callback bắn một `CompletableFuture` rồi không chờ/không gắn handler: exception xảy ra về sau có thể không đi qua error handler của container. Phải gắn error handling và metrics ở chính tầng xử lý bất đồng bộ.

## 7. Kiểm tra kết nối, quyền và topology

Nếu Redis CLI từ máy phát triển nhận được message, nhưng Spring trong Kubernetes không nhận, hãy kiểm tra **từ chính môi trường nơi ứng dụng chạy**:

~~~bash
# Dùng đúng host/port/TLS/credential theo môi trường.
redis-cli -h redis.internal -p 6379 PING

# Thử subscribe ở kết nối tương đương với listener.
redis-cli -h redis.internal -p 6379 SUBSCRIBE orders.events
~~~

Những nguyên nhân thường gặp:

| Lớp | Tình huống | Dấu hiệu |
| --- | --- | --- |
| DNS | DNS service name không phân giải | Connection failure trước SUBSCRIBE |
| TCP/network policy | App không tới Redis endpoint | Timeout, connection refused/reset |
| TLS | Client dùng plaintext trên cổng TLS hoặc ngược lại | SSL handshake/connection error |
| ACL | Redis user thiếu quyền `SUBSCRIBE`, `PSUBSCRIBE` hoặc channel pattern | `NOPERM` hoặc lỗi subscription |
| Role/topology | Client kết nối node cũ sau failover | Reconnect và gián đoạn Pub/Sub |
| Cluster | Đăng ký sai node cho loại notification hoặc sharded Pub/Sub | Chỉ một phần channel/event được quan sát |
| Lifecycle | Container dừng, không start hoặc bị đóng context | Không có subscription còn sống |
| Resource | Executor bị nghẽn, connection bị giữ/chặn | Có message nhưng không tới bước xử lý cuối |

Trong Redis ACL hiện đại, quyền command và **quyền Pub/Sub channel** có thể được kiểm soát riêng. Một Redis user được quyền `GET` và `SET` **không tự động có quyền `SUBSCRIBE` mọi channel**. Việc dùng các pattern channel như `__keyevent@0__:expired` cũng cần đúng permission, không chỉ quyền đọc key.

Không nên “sửa nhanh” bằng cách cấp user `+@all` và toàn bộ key/channel trong production. Hãy xác định chính xác lệnh và channel được phép dùng; không ghi mật khẩu hoặc URI có credential vào log.

### Sentinel, reconnect và khoảng mất message

Khi primary failover, Lettuce/Spring có thể cần khám phá primary mới và tạo subscription lại. Trong khoảng đứt kết nối hoặc chuyển node:

~~~text
Subscriber nhận orders.events
           |
           v
Redis node lỗi / network partition
           |
           v
Subscription tạm thời không khả dụng
           |
           v
Publisher vẫn phát event ở nơi khác
           |
           v
Client reconnect và subscribe lại
           |
           v
Những message đã phát trong khoảng gián đoạn
không tự được Redis Pub/Sub phát lại
~~~

Điều cần kiểm tra là **tốc độ và độ tin cậy của reconnect**, không chỉ việc ứng dụng “cuối cùng đã kết nối trở lại”. Với event không thể mất, dùng cấu trúc durable/offset/ACK phù hợp.

## 8. Sự kiện hết hạn không tự xuất hiện khi Redis chưa bật notifications

Redis có thể tự động xóa key khi TTL hết mà **không phát thông báo** tới listener, nếu `notify-keyspace-events` chưa được cấu hình thích hợp. Một lời gọi `EXPIRE` hoặc `SET ... EX` thành công chỉ cho Redis biết thời điểm hết hạn; nó không đồng nghĩa rằng mọi application subscriber sẽ được gọi.

Redis hỗ trợ hai cách nhìn notification:

| Kiểu | Channel | Body/message | Ví dụ |
| --- | --- | --- | --- |
| **Keyevent** | Gắn loại sự kiện và database | Tên key bị ảnh hưởng | Channel `__keyevent@0__:expired`, body `session:abc` |
| **Keyspace** | Gắn tên key và database | Tên sự kiện | Channel `__keyspace@0__:session:abc`, body `expired` |

Với một key `session:abc` hết hạn trong DB 0:

~~~text
Keyevent:
   channel = __keyevent@0__:expired
   body    = session:abc

Keyspace:
   channel = __keyspace@0__:session:abc
   body    = expired
~~~

Đây là **hai cách biểu diễn cùng một loại hoạt động**, nhưng Redis chỉ phát những nhóm notification được bật. Nếu listener subscribe channel keyevent trong khi server chỉ bật keyspace notification, callback sẽ không chạy dù key có hết hạn.

### 8.1. Hiểu `notify-keyspace-events`

Các flag quan trọng:

| Flag | Ý nghĩa |
| --- | --- |
| `K` | Cho phép phát **keyspace** notifications |
| `E` | Cho phép phát **keyevent** notifications |
| `x` | Nhóm sự kiện **expired** |
| `e` | Nhóm sự kiện **evicted** — khác với TTL expiration |
| `g` | Một số hoạt động tổng quát như delete/expire/persist, tùy event cụ thể |

Để nhận sự kiện hết hạn ở channel `__keyevent@0__:expired`:

~~~text
notify-keyspace-events Ex
~~~

`E` bật kiểu keyevent; `x` bật nhóm expired. Nếu muốn đồng thời theo dõi keyspace và keyevent expired, có thể bật những flag tương ứng, ví dụ `KEx`.

Kiểm tra Redis server hiện tại:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 \
  CONFIG GET notify-keyspace-events
~~~

Nếu kết quả là chuỗi rỗng hoặc thiếu nhóm notification cần thiết, Redis có thể không phát event mà listener đang chờ. Một số môi trường managed Redis hạn chế quyền `CONFIG GET`/`CONFIG SET`; trong trường hợp đó cần xem cấu hình qua control plane, parameter group hoặc người quản trị dịch vụ.

### 8.2. Bật notifications cho môi trường thử nghiệm

Trên Redis dev/test tự quản lý:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 \
  CONFIG SET notify-keyspace-events Ex
~~~

**Cẩn thận:** `CONFIG SET notify-keyspace-events Ex` thay thế toàn bộ chuỗi flag hiện tại. Nếu server đang bật các notification khác, đặt đúng `Ex` có thể vô tình **tắt những nhóm sự kiện khác** mà ứng dụng đang cần.

Quy trình production đúng hơn:

1. Đọc cấu hình hiện có.
2. Xác định nhóm keyspace/keyevent thật sự cần dùng.
3. Hợp nhất flag thay vì ghi đè mù.
4. Cấu hình qua cơ chế bền vững của hạ tầng Redis đang sử dụng.
5. Kiểm chứng giá trị hiệu lực sau deploy/restart.

Không nên cho phép một listener application tự ý nâng quyền Redis chỉ để chạy `CONFIG SET` trong production. Nếu managed Redis không cho phép thay đổi config từ client, hãy yêu cầu cấu hình ở tầng hạ tầng thay vì bỏ kiểm tra quyền.

### 8.3. Thử expired event bằng Redis CLI

**Terminal A — subscribe trước:**

~~~bash
redis-cli -h 127.0.0.1 -p 6379 -n 0 \
  PSUBSCRIBE '__keyevent@0__:expired'
~~~

**Terminal B — tạo key có TTL:**

~~~bash
redis-cli -h 127.0.0.1 -p 6379 -n 0 \
  SET diagnostic:expiry:001 "example" EX 2
~~~

Quan sát TTL:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 -n 0 \
  PTTL diagnostic:expiry:001
~~~

Sau khi Redis thực sự xóa key do hết hạn, Terminal A sẽ có một thông điệp trên channel `__keyevent@0__:expired` với body `diagnostic:expiry:001`.

**Đừng mong thông điệp xuất hiện chính xác ở mili giây thứ 2.** Redis dùng cơ chế expiration chủ động và thụ động; sự kiện phát khi Redis thực sự xóa key đã hết hạn, không phải từ một bộ hẹn giờ bảo đảm phát callback đúng mốc. Trên server đang tải hoặc với key ít được truy cập, thời điểm quan sát có thể trễ.

Nếu sau TTL key chưa còn mà không thấy event:

- Kiểm tra subscription đã hoạt động **trước** khi key hết hạn chưa.
- Kiểm tra Redis ở **cùng node/database** có key.
- Kiểm tra `notify-keyspace-events` và ACL Pub/Sub.
- Kiểm tra key có thực sự bị xóa do **TTL expiration** hay bị lệnh khác xóa.
- Kiểm tra có failover/reconnect trong khoảng này không.

### 8.4. Dùng keyspace thay cho keyevent

Nếu server bật kiểu keyspace tương ứng, có thể subscribe:

~~~redis
PSUBSCRIBE __keyspace@0__:diagnostic:expiry:*
~~~

Với key `diagnostic:expiry:001` hết hạn, channel sẽ chứa **tên key**, còn body là `expired`. Với kiểu keyevent, cách biểu diễn ngược lại: channel là `expired`, body là tên key.

Do đó, không dùng cùng đoạn code tưởng rằng `message.getBody()` luôn là tên key ở cả hai dạng notification.

## 9. TTL đúng nhưng không nhận event: kiểm tra cách key biến mất

**Một key biến mất không chứng minh Redis đã phát `expired`.** Nhiều thao tác có thể làm key không còn tồn tại:

| Thao tác | Điều có thể xảy ra | Có phải sự kiện `expired`? |
| --- | --- | --- |
| `SET k v EX 10` | Tạo key mới, hết hạn khi TTL kết thúc | Có thể phát `expired` khi Redis xóa do TTL nếu notification bật |
| `EXPIRE k 10` | Đặt TTL cho key đang tồn tại | `expired` chỉ về sau khi key thực sự hết hạn |
| `PEXPIRE k 1000` | Đặt TTL theo mili giây | Tương tự |
| `DEL k` | Xóa key trực tiếp | **Không** phải expiration; là delete |
| `UNLINK k` | Xóa key theo cách giải phóng bộ nhớ bất đồng bộ | **Không** phải expiration; thuộc nhóm delete |
| `SET k newValue` | Ghi đè và thường xóa TTL cũ nếu không chỉ định giữ TTL | Không có `expired` cho TTL cũ chỉ vì ghi đè |
| `PERSIST k` | Loại bỏ thời hạn sống | Key có thể tồn tại vô hạn, không phát `expired` vì TTL cũ |
| `EXPIRE k 0` hoặc TTL âm | Key có thể bị xóa ngay | Theo semantics Redis thường là event `del`, **không** phải `expired` |
| Eviction do `maxmemory` | Redis loại key theo policy để thu hồi bộ nhớ | `evicted`, không phải `expired` |
| `RENAME` / cấu trúc key khác | Tên key hoặc dữ liệu thay đổi | Cần xem notification phù hợp, không mặc định `expired` |

Ví dụ lỗi rất thường gặp:

~~~redis
SET session:42 "abc" EX 30
SET session:42 "updated"
TTL session:42
~~~

Lệnh `SET` thứ hai **mặc định loại bỏ TTL cũ** nếu không sử dụng tùy chọn giữ TTL phù hợp. `TTL` có thể trả `-1`. Khi đó listener expired không bao giờ nhận sự kiện như mong đợi, vì key không còn thời hạn để tự hết hạn.

Nếu cần cập nhật value mà vẫn duy trì TTL, Redis có tùy chọn phù hợp như `KEEPTTL` trên các phiên bản hỗ trợ:

~~~redis
SET session:42 "updated" KEEPTTL
~~~

Hoặc ứng dụng có thể xác định TTL mới rõ ràng trong thao tác ghi. Cần hiểu hợp đồng lưu session/cache của ứng dụng để không vô tình gia hạn hoặc loại bỏ thời gian sống.

### Đọc `TTL` và `PTTL` đúng

~~~redis
TTL session:42
PTTL session:42
~~~

| Kết quả | Ý nghĩa |
| --- | --- |
| Số dương | Thời gian sống còn lại theo giây/mili giây |
| `-1` | Key tồn tại nhưng không có TTL |
| `-2` | Key không tồn tại |

Nếu `TTL` trả `-1`, không cần tìm lỗi trong listener expired trước; phải kiểm tra **đường ghi đã đặt TTL chưa**. Nếu `TTL` trả `-2`, cần kiểm tra key đã hết hạn hay bị xóa vì nguyên nhân khác, và subscriber có trực tuyến tại thời điểm đó hay không.

### Có nhận được giá trị của key trong expired callback không?

Thông điệp Redis `__keyevent@0__:expired` thường chỉ chứa **tên key**. Tại thời điểm callback chạy, key chính đã bị Redis xóa. Lệnh:

~~~redis
GET session:42
~~~

thường không thể đọc lại value đã hết hạn. Nếu nghiệp vụ cần dữ liệu để thực hiện cleanup, hãy thiết kế một record/stream riêng, một shadow copy được quản lý hoặc lưu thông tin cần thiết trước khi key biến mất; không coi expired notification là snapshot đầy đủ của entity.

### Sự kiện hết hạn không bảo đảm thời gian chính xác

Một ứng dụng dùng TTL 15 phút cho session có thể biết session sẽ trở thành không hợp lệ sau TTL, nhưng **không nên dùng callback `expired` làm bộ hẹn giờ chính xác cho hành động nghiệp vụ bắt buộc** như trừ tiền hoặc phát hành hóa đơn.

Expiration event có thể phát trễ, mất khi subscriber offline hoặc không đến từ node đang được lắng nghe. Khi cần job phải chạy cuối cùng, hãy dùng scheduler/queue bền vững, trạng thái ở database hoặc cơ chế có recovery/reconciliation.

## 10. Listener hết hạn trong Spring Data Redis

Với bean `RedisMessageListenerContainer` ở phần trên, callback expired đăng ký:

~~~java
container.addMessageListener(
    expiredListener,
    new PatternTopic("__keyevent@0__:expired")
);
~~~

Nếu chỉ cần nhận thông báo từ DB 0, `ChannelTopic` với tên chính xác cũng có thể phù hợp:

~~~java
container.addMessageListener(
    expiredListener,
    new ChannelTopic("__keyevent@0__:expired")
);
~~~

Nếu muốn quan sát mọi logical database trên **một Redis standalone**, có thể cân nhắc pattern:

~~~java
new PatternTopic("__keyevent@*__:expired")
~~~

Nhưng nên giới hạn phạm vi theo nhu cầu. Redis Cluster thường chỉ sử dụng DB 0; keyevent notifications trong Redis Cluster là **node-local**, nên một pattern `@*` trên một node không tự biến subscription thành listener toàn cluster.

### Không nhầm event channel với key prefix

Khi dùng keyevent:

~~~text
Channel: __keyevent@0__:expired
Body:    cache:product:42
~~~

Nếu chỉ quan tâm key thuộc prefix `cache:product:`, listener phải kiểm tra **body** sau khi nhận, ví dụ:

~~~java
String key = new String(
    message.getBody(), StandardCharsets.UTF_8
);

if (!key.startsWith("cache:product:")) {
    return;
}
// Xử lý sự kiện của namespace cache:product:
~~~

Không subscribe `__keyevent@0__:cache:product:*` để lọc tên key; phần sau dấu `:` cuối cùng của keyevent channel là **tên event**, không phải key name.

Nếu muốn lọc theo key ngay ở pattern subscription, keyspace-style channel `__keyspace@0__:cache:product:*` sẽ mang tên key, nhưng body lúc đó là loại sự kiện như `expired`; đồng thời server phải bật kiểu `K` và nhóm event tương ứng. Mỗi lựa chọn có cách parser/cấu hình khác nhau.

## 11. Redis Repository: entity hết TTL nhưng `@EventListener` không chạy

Khi dùng Spring Data Redis Repository, một entity có thể được đánh dấu `@RedisHash` và có TTL qua `@TimeToLive`:

~~~java
package com.example.redis.diagnostics;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("sessions")
public class SessionRecord {

    @Id
    private String id;

    private String userReference;

    @TimeToLive
    private Long ttlSeconds;

    protected SessionRecord() {
    }

    public SessionRecord(
            String id, String userReference, Long ttlSeconds) {
        this.id = id;
        this.userReference = userReference;
        this.ttlSeconds = ttlSeconds;
    }

    public String getId() {
        return id;
    }

    public String getUserReference() {
        return userReference;
    }

    public Long getTtlSeconds() {
        return ttlSeconds;
    }
}
~~~

Repository:

~~~java
package com.example.redis.diagnostics;

import org.springframework.data.repository.CrudRepository;

public interface SessionRepository
        extends CrudRepository<SessionRecord, String> {
}
~~~

Khi gọi:

~~~java
repository.save(
    new SessionRecord("test-session-001", "user-42", 2L)
);
~~~

property `ttlSeconds` đặt TTL cho entity theo semantics `@TimeToLive` của Spring Data Redis (với trường số, đơn vị mặc định là giây). Redis xóa key chính sau TTL khi expiration thực sự được xử lý.

**Nhưng entity hết hạn không tự có nghĩa application đã đăng ký lắng nghe Spring event.** Cần xem cấu hình Redis Repository keyspace events.

### Bật listener cho Redis Repository

Ví dụ cấu hình khởi động listener ngay khi application context được thiết lập:

~~~java
package com.example.redis.diagnostics;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter.EnableKeyspaceEvents;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
    basePackageClasses = SessionRepository.class,
    enableKeyspaceEvents = EnableKeyspaceEvents.ON_STARTUP
)
public class RedisRepositoryConfiguration {
}
~~~

`EnableKeyspaceEvents.ON_STARTUP` yêu cầu hạ tầng repository khởi tạo cơ chế lắng nghe keyspace events lúc startup, giảm nguy cơ listener chỉ được thiết lập sau một thao tác đầu tiên. Đó **không phải một cam kết mọi event sẽ được nhận**: Redis server phải hỗ trợ/cấu hình notifications phù hợp, subscription phải hoạt động và các event phát khi listener offline vẫn có thể bị mất.

### Lắng nghe Spring application event

~~~java
package com.example.redis.diagnostics;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.RedisKeyExpiredEvent;
import org.springframework.stereotype.Component;

@Component
public class RepositoryExpiryObserver {

    private static final Logger log =
        LoggerFactory.getLogger(RepositoryExpiryObserver.class);

    @EventListener
    public void onExpired(RedisKeyExpiredEvent<?> event) {
        log.info(
            "Redis Repository expiry application event received: {}",
            event.getClass().getSimpleName()
        );
        // Sử dụng metadata/id theo API của phiên bản Spring Data
        // đang dùng nếu cần định danh entity để xử lý.
    }
}
~~~

Nếu callback trên không chạy, cần phân biệt:

1. Redis không phát `expired` vì `notify-keyspace-events` chưa bật.
2. Repository keyspace event listener chưa được khởi tạo.
3. Entity không được lưu qua Redis Repository hoặc không có TTL.
4. Key bị xóa trực tiếp, bị overwrite hoặc eviction, không phải TTL expiration.
5. Subscriber không trực tuyến lúc Redis phát notification.
6. Redis Cluster node phát expired event không phải node listener đang nghe.
7. Spring event đã phát nhưng application listener bị cấu hình sai hoặc ném lỗi.

### Shadow copy và value của entity sau khi hết hạn

Spring Data Redis Repository có thể duy trì **shadow copy** của entity có TTL trong một khoảng bổ sung nhằm cung cấp value cho expiration application event. Việc này có chi phí bộ nhớ; có tùy chọn cấu hình liên quan đến shadow copy và cách event mang nội dung entity.

Do vậy, không viết handler chỉ hoạt động khi lấy được **toàn bộ entity** từ expired event rồi mặc định điều đó luôn đúng sau khi thay đổi cấu hình hoặc khi event bị mất. Với xử lý quan trọng, nên thiết kế identity và dữ liệu bắt buộc tồn tại ở một nguồn bền vững riêng.

### Vì sao Redis Repository cần quan tâm index cleanup?

Repository có thể duy trì secondary index Set cho các thuộc tính `@Indexed`. Khi Hash entity hết TTL, các Set index không tự mất thành viên chỉ vì Redis xóa một key khác. Keyspace events là một cơ chế để Spring Data Redis theo dõi và cleanup index.

Nếu notification bị tắt hoặc listener bỏ lỡ event, có thể xuất hiện **stale index reference**. Khi Redis là nguồn dữ liệu quan trọng, cần quy trình đối soát/reindex thay vì giả định mọi key expired luôn kích hoạt cleanup thành công.

Nếu ứng dụng dùng Redis như cache và không cần repository/secondary index, một `StringRedisTemplate` lưu value với TTL có thể đơn giản hơn và ít phụ thuộc vào event lifecycle.

## 12. Redis Cluster: keyevent khác Pub/Sub thường

Trong Redis Cluster, cần phân biệt:

- **Application Pub/Sub thường:** các thông điệp theo regular Pub/Sub có cơ chế phân phối trên cluster theo Redis, khác với giới hạn node-local của keyspace notification. Client và phiên bản Redis quyết định cách subscribe phù hợp.
- **Sharded Pub/Sub:** Redis có nhóm lệnh `SSUBSCRIBE`/`SPUBLISH` và ngữ nghĩa định tuyến theo shard; không giống `SUBSCRIBE`/`PUBLISH` thông thường.
- **Keyspace/keyevent notifications:** Redis phát sự kiện từ node đang xử lý thay đổi key. **Notifications không tự được broadcast tới mọi node trong Redis Cluster** để một subscriber duy nhất trên một node nhìn thấy toàn bộ key của cluster.

Ví dụ:

~~~text
                   Redis Cluster

Key session:1 → hash slot tại Master A
Key session:2 → hash slot tại Master B
Key session:3 → hash slot tại Master C

             +-------------+-------------+
             |             |             |
             v             v             v
          Master A      Master B      Master C
             |             |             |
       expired key 1  expired key 2 expired key 3
             |             |             |
             v             v             v
       local keyevent local keyevent local keyevent

Listener chỉ subscribe event ở Master A:
  Có thể thấy session:1,
  không tự thấy session:2 hoặc session:3.
~~~

Nếu hệ thống cần quan sát key expiration từ **toàn cluster**, phải xem cách client/subscriber kết nối tới từng node có thể phát sự kiện, và cách cập nhật danh sách node sau topology change. Không giả định một `PatternTopic("__keyevent@*__:expired")` trên một connection là đủ.

### Khi gặp sự cố chỉ mất event của một số key

1. Xác định key bị ảnh hưởng và hash slot/node đang sở hữu.
2. Xác định node nào đang phát keyspace notifications và config trên từng node.
3. Kiểm tra subscriber thực sự kết nối vào node nào.
4. Kiểm tra việc chuyển slot, thăng cấp replica hoặc reconnect gần thời điểm event.
5. Nếu dùng managed cluster, kiểm tra provider có hỗ trợ/giới hạn notifications theo node không.
6. Đừng nhầm một kết nối Redis Cluster hoạt động cho `GET`/`SET` với một subscription đã phủ toàn bộ các keyevent trên mọi node.

Một bài test chỉ chạy trên một Redis standalone không chứng minh được khả năng nhận hết keyevent trong Cluster.

## 13. Redis Sentinel/replica và sự kiện bị mất khi failover

Nếu ứng dụng dùng Redis Sentinel để tìm primary, các thao tác ghi và thời hạn sống có thể liên quan tới quá trình failover. Một số tình huống:

~~~text
T0    Listener đang subscribe trên Redis node P
T1    P gặp sự cố
T2    Replica R được thăng cấp thành primary mới
T3    Một số key hết hạn khi listener chưa kết nối lại
T4    Listener reconnect và subscribe

Event phát ở khoảng T2–T4:
  Có thể không được listener nhận.
~~~

Redis Pub/Sub và keyspace notifications không có offset/ACK để replay những message bị mất trong thời gian đứt connection. Dù Spring container có khả năng reconnect/resubscribe, **thành công sau reconnect không bù được lịch sử sự kiện đã bỏ lỡ**.

Ngoài ra, Redis replication bất đồng bộ và các thời điểm failover có thể làm dữ liệu/TTL được quan sát khác nhau giữa các đời primary. Không nên dùng số event expired nhận được như một cam kết tuyệt đối cho số entity đã hết hạn trên toàn hệ thống.

Nếu việc hết hạn dùng để giải phóng một tài nguyên nghiệp vụ:

- Lưu deadline/expiration timestamp ở nơi đủ tin cậy để có thể đối soát.
- Có job rà soát những tài nguyên đã quá hạn nhưng chưa xử lý.
- Thiết kế side effect **idempotent** để xử lý lặp không gây hại.
- Dùng queue/Stream/outbox nếu cần phát lệnh cleanup bền vững, không chỉ Pub/Sub.
- Quy định rõ hành vi khi listener mất kết nối hoặc ứng dụng đang khởi động lại.

**Không mặc định hai instance cùng subscribe expiration channel sẽ chia nhau xử lý**: Pub/Sub thường broadcast, nên cả hai có thể chạy cùng một cleanup action. Nếu chỉ một instance được thực thi, cần điều phối/đảm bảo idempotency riêng.

## 14. Chẩn đoán theo tầng: Redis → container → callback → nghiệp vụ

Khi nhận phản ánh “listener không nhận message”, hãy đi qua những tầng sau thay vì thay đổi cấu hình ngẫu nhiên:

~~~text
                      Có sự kiện cần theo dõi
                                 |
                                 v
                 Redis có phát trên channel đúng?
                        /                 \
                      Không                Có
                        |                  |
                        v                  v
           Publisher / TTL / config    Subscribe đúng topic?
                        |                  |
                        v                  v
           CLI kiểm tra và sửa          Connection/ACL?
                        |                  |
                        +----------+-------+
                                   |
                                   v
                       Container có đang chạy?
                                   |
                                   v
                       Listener callback vào chưa?
                            /              \
                           Có              Không
                           |                 |
                           v                 v
                  Parse/business lỗi?   Registration,
                           |            executor, reconnect
                           v
                       Log + metric
                           |
                           v
                 Kiểm tra end-to-end side effect
~~~

### Tầng A — Redis đã nhận lệnh publish hoặc tạo expiration chưa?

Với application Pub/Sub:

~~~redis
PUBLISH orders.events "probe-001"
PUBSUB NUMSUB orders.events
PUBSUB NUMPAT
~~~

Với expired:

~~~redis
CONFIG GET notify-keyspace-events
SET diagnostic:ttl:001 "value" EX 2
PTTL diagnostic:ttl:001
~~~

Đặt một Redis CLI subscriber trước khi phát, quan sát đúng channel và body. Nếu CLI subscriber cũng không nhận, chưa có lý do kết luận Spring container lỗi.

### Tầng B — Spring có subscribe đúng không?

Kiểm tra code:

~~~java
container.addMessageListener(
    listener, new ChannelTopic("orders.events")
);
~~~

hoặc:

~~~java
container.addMessageListener(
    listener, new PatternTopic("__keyevent@0__:expired")
);
~~~

Hỏi:

- Tên channel có khác dấu chấm, chữ hoa/thường hoặc suffix môi trường không?
- Listener có đang dùng `ChannelTopic` cho một pattern chứa `*` không?
- `RedisMessageListenerContainer` có được đăng ký là Spring bean không?
- Có bị gọi `stop()`, `removeMessageListener(...)` hoặc đóng ApplicationContext quá sớm không?
- Có nhiều `RedisConnectionFactory` hoặc Redis endpoint khác nhau không?
- Subscriber có quyền lệnh/channel hay không?

### Tầng C — Callback đã nhận bytes chưa?

Đặt một điểm ghi nhận nhẹ ngay khi vào callback:

~~~java
MessageListener listener = (message, pattern) -> {
    String channel = new String(
        message.getChannel(), StandardCharsets.UTF_8
    );

    // Đo callback entry trước deserialize hoặc gọi service.
    log.debug(
        "Redis message callback entered, channel={}, bytes={}",
        channel, message.getBody().length
    );

    processMessage(message);
};
~~~

`processMessage(...)` là xử lý nghiệp vụ minh họa. Log trước parse giúp phân biệt “không có callback” với “có callback nhưng xử lý dữ liệu lỗi”.

Với dữ liệu nhạy cảm, không log toàn bộ body hoặc key có thông tin người dùng. Dùng metric label theo namespace/loại message, không theo mỗi key ID.

### Tầng D — Nghiệp vụ đã xử lý thành công chưa?

Một callback được gọi không có nghĩa:

- Event JSON đã deserialize thành công.
- Database transaction đã commit.
- HTTP callback tới hệ thống khác đã thành công.
- Side effect không bị thực hiện hai lần.
- Message sẽ được Redis phát lại sau lỗi.

Nên có ít nhất:

~~~text
redis_listener_received_total
redis_listener_decode_failed_total
redis_listener_processing_failed_total
redis_listener_processed_total
redis_listener_processing_duration
redis_listener_reconnect_total
~~~

Các tên trên là gợi ý instrument, không phải metric tự động xuất hiện khi thêm Spring Data Redis. Giá trị và phân loại nên được ghi theo channel group, listener type và outcome với cardinality hữu hạn.

## 15. Error handler, callback lỗi và “sự im lặng” giả

Không nên bắt mọi exception trong callback rồi bỏ qua:

~~~java
// Anti-pattern: thất bại không có tín hiệu điều tra.
MessageListener listener = (message, pattern) -> {
    try {
        processMessage(message);
    } catch (Exception ignored) {
        // Mất mọi thông tin vì sao dữ liệu không được xử lý.
    }
};
~~~

Một cách có kiểm soát:

~~~java
MessageListener listener = (message, pattern) -> {
    try {
        processMessage(message);
        processedCounter.increment();
    } catch (IllegalArgumentException invalidPayload) {
        decodeFailureCounter.increment();
        log.warn(
            "Invalid Redis Pub/Sub payload: {}",
            invalidPayload.getClass().getSimpleName()
        );
    } catch (RuntimeException processingError) {
        processingFailureCounter.increment();
        log.error(
            "Redis Pub/Sub processing failed",
            processingError
        );
    }
};
~~~

Trong ví dụ, `processedCounter`, `decodeFailureCounter` và `processingFailureCounter` đại diện cho những counter được inject hoặc khởi tạo qua hệ thống metrics; `processMessage` là logic ứng dụng. Đây là mẫu phân tách trạng thái, không phải một class Java độc lập đã khai báo đầy đủ.

**Lưu ý:** callback lỗi của Pub/Sub không khiến Redis gửi lại message. Nếu cần retry sau lỗi xử lý nghiệp vụ, phải tự có cơ chế durable và idempotency. Ghi metric failure chỉ giúp quan sát, không bảo đảm recovery.

### Khi callback đã nhận nhưng task executor nghẽn

Quan sát:

- Thread dump và số task đang chạy.
- Executor queue depth, rejected task count nếu được instrument.
- Các lệnh I/O đồng bộ có nằm trong callback không.
- CPU/GC và lượng bytes mỗi message.
- Tốc độ publish vs tốc độ processed.

Nếu hệ thống nhận được hàng nghìn thông điệp/giây nhưng chỉ xử lý vài trăm/giây, Pub/Sub **không phải queue bền vững** để hấp thụ backlog vô hạn. Cần điều chỉnh kiến trúc thay vì chỉ mở rộng queue trong JVM.

## 16. Công cụ Redis CLI phục vụ điều tra

Một số lệnh an toàn khi có quyền và chạy đúng môi trường:

~~~bash
# Kết nối cơ bản:
redis-cli -h redis.internal -p 6379 PING

# Quan sát subscription:
redis-cli -h redis.internal -p 6379 PUBSUB CHANNELS
redis-cli -h redis.internal -p 6379 PUBSUB NUMSUB orders.events
redis-cli -h redis.internal -p 6379 PUBSUB NUMPAT

# Kiểm tra cấu hình expiration notification:
redis-cli -h redis.internal -p 6379 CONFIG GET notify-keyspace-events

# Kiểm tra key còn sống hay không:
redis-cli -h redis.internal -p 6379 TTL diagnostic:expiry:001
redis-cli -h redis.internal -p 6379 PTTL diagnostic:expiry:001

# Quan sát độ tải:
redis-cli -h redis.internal -p 6379 INFO clients
redis-cli -h redis.internal -p 6379 INFO stats
redis-cli -h redis.internal -p 6379 INFO keyspace
redis-cli -h redis.internal -p 6379 SLOWLOG GET 10
~~~

Không ghi mật khẩu Redis trong history/command line nếu môi trường không cho phép; dùng cơ chế secret phù hợp. Không in raw key/value session hoặc token vào bản ghi công khai.

### Tại sao không dùng `MONITOR` như phép thử đầu tiên?

`MONITOR` có thể thấy command của nhiều client, nhưng trên Redis chịu tải lớn nó có overhead và nguy cơ lộ command arguments/secret. Một `SUBSCRIBE`/`PSUBSCRIBE` test có kiểm soát trên channel riêng cùng các metric phù hợp thường an toàn và đủ để khoanh vùng sự cố.

Trong trường hợp bắt buộc dùng `MONITOR` cho chẩn đoán chuyên sâu, phải có quyền, thời gian ngắn, chính sách xử lý dữ liệu và đánh giá ảnh hưởng tới Redis server.

## 17. Integration test: xác minh listener với Redis thật

Unit test gọi trực tiếp `listener.onMessage(...)` có thể chứng minh callback parse dữ liệu đúng, nhưng **không chứng minh Spring đã thực sự SUBSCRIBE hoặc Redis đã phát expiration event**. Để kiểm tra đầy đủ đường đi:

~~~text
Test → StringRedisTemplate → Redis Testcontainer
                              |
                              v
                    PUBLISH / SET EX
                              |
                              v
                Redis Pub/Sub / keyevent
                              |
                              v
               RedisMessageListenerContainer
                              |
                              v
                       MessageListener
                              |
                              v
                       Assertion test
~~~

Ví dụ dùng Spring Boot 3.x, JUnit 5, Testcontainers và Awaitility. Redis container được khởi động với `notify-keyspace-events Ex`, nên test không phải có quyền gọi `CONFIG SET` trong lúc chạy:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.awaitility:awaitility'
}
~~~

Tạo lớp integration test:

~~~java
package com.example.redis.diagnostics;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.PatternTopic;
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
@SpringBootTest(
    classes = RedisListenerIntegrationTest.TestApp.class
)
class RedisListenerIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(RedisListenerConfiguration.class)
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.2-alpine")
        )
            .withExposedPorts(6379)
            .withCommand(
                "redis-server",
                "--notify-keyspace-events",
                "Ex"
            );

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate redis;

    @Autowired
    RedisMessageListenerContainer container;

    @Test
    void receivesAnApplicationPubSubMessage() {
        String marker = "it-message-" + UUID.randomUUID();
        CountDownLatch received = new CountDownLatch(1);

        MessageListener listener = (message, pattern) -> {
            String body = new String(
                message.getBody(),
                StandardCharsets.UTF_8
            );
            if (marker.equals(body)) {
                received.countDown();
            }
        };

        ChannelTopic topic = new ChannelTopic("orders.events");
        container.addMessageListener(listener, topic);

        try {
            // Listener đăng ký bất đồng bộ; gửi probe lặp
            // trong deadline thay vì publish đúng một lần
            // rồi giả định SUBSCRIBE đã sẵn sàng.
            await()
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(150))
                .until(() -> {
                    redis.convertAndSend("orders.events", marker);
                    return received.getCount() == 0;
                });

            assertThat(received.getCount()).isZero();
        } finally {
            container.removeMessageListener(listener, topic);
        }
    }

    @Test
    void receivesARealExpiredKeyEvent() throws Exception {
        String prefix = "it-expiry-" + UUID.randomUUID();
        String targetKey = prefix + ":target";

        AtomicBoolean subscriptionReady = new AtomicBoolean(false);
        CountDownLatch targetExpired = new CountDownLatch(1);

        MessageListener listener = (message, pattern) -> {
            String key = new String(
                message.getBody(),
                StandardCharsets.UTF_8
            );

            if (key.startsWith(prefix + ":probe:")) {
                subscriptionReady.set(true);
            }
            if (targetKey.equals(key)) {
                targetExpired.countDown();
            }
        };

        PatternTopic topic =
            new PatternTopic("__keyevent@0__:expired");

        container.addMessageListener(listener, topic);

        try {
            // Thăm dò bằng các key thật sự hết hạn.
            // Không tự PUBLISH giả vào channel hệ thống.
            await()
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(200))
                .until(() -> {
                    String probeKey =
                        prefix + ":probe:" + UUID.randomUUID();
                    redis.opsForValue().set(
                        probeKey, "1", Duration.ofMillis(150)
                    );
                    return subscriptionReady.get();
                });

            redis.opsForValue().set(
                targetKey, "payload", Duration.ofMillis(300)
            );

            boolean observed = targetExpired.await(
                10, TimeUnit.SECONDS
            );
            assertThat(observed).isTrue();
        } finally {
            container.removeMessageListener(listener, topic);
            redis.delete(targetKey);
        }
    }
}
~~~

Trong test thứ nhất, marker UUID tránh nhầm với message từ test khác; test có thể gửi **nhiều probe giống nhau** trước khi subscriber sẵn sàng, nên assertion chỉ yêu cầu nhận ít nhất một message, không khẳng định “exactly once”.

Test thứ hai làm hai việc tách biệt:

1. **Xác nhận listener đã quan sát được expired event thật** từ những key probe có TTL ngắn.
2. Sau khi biết đường notification hoạt động, tạo một key đích và chờ đúng tên key xuất hiện trong callback.

Cách này tránh kiểm thử quá phụ thuộc một `Thread.sleep(300)` sát mốc TTL và tránh tình huống target key hết hạn trước khi subscription thực sự có hiệu lực.

Các key probe có namespace UUID và TTL rất ngắn, nên tự hết hạn trên Redis test; chúng không được tạo trên production. `finally` gỡ listener thêm động và dọn target key còn lại.

**Giới hạn:** đây là một Redis standalone với `notify-keyspace-events Ex`. Nó không chứng minh sự kiện qua Cluster node migration, Sentinel failover, mất subscriber network hay keyspace notification bị tắt trên managed Redis. Mỗi yêu cầu đó cần môi trường tích hợp và phép thử riêng.

### Test Repository expiration event cần chuẩn bị gì?

Nếu mục tiêu là `RedisKeyExpiredEvent<?>` của repository, thêm một test tích hợp riêng:

1. Bật `@EnableRedisRepositories(enableKeyspaceEvents = EnableKeyspaceEvents.ON_STARTUP)`.
2. Cấu hình Redis test phát `expired` notification.
3. Lưu một entity `@RedisHash` có TTL ngắn.
4. Đăng ký một Spring application event listener trước khi lưu entity.
5. Poll/await cho đến khi listener ghi nhận sự kiện dự kiến hoặc hết timeout.
6. Kiểm tra riêng việc key đã mất, và nếu có secondary index, kiểm tra riêng cleanup.

Không so sánh toàn bộ object entity hết hạn nếu shadow-copy policy của repository không cung cấp value đó. Không dựa vào thứ tự giữa các callback event và các request Redis độc lập nếu hệ thống không cam kết một thứ tự như vậy.

## 18. Runbook chẩn đoán theo từng tình huống

### Tình huống A — `PUBLISH` có chạy, callback không vào

1. Dùng hai Redis CLI để xác nhận cùng endpoint có thể `SUBSCRIBE` rồi `PUBLISH` đúng channel.
2. Kiểm tra listener dùng `ChannelTopic` hay `PatternTopic` và có đúng chuỗi channel không.
3. Kiểm tra listener container được tạo, start và không bị stop/remove.
4. Kiểm tra ACL lệnh và Pub/Sub channel.
5. Kiểm tra app đang ở Redis instance/topology nào, có thay đổi sau failover không.
6. Bật metric/callback entry để xác định có nhận bytes trước khi parse không.
7. Kiểm tra thread/executor và error handler.

Nếu CLI nhận được nhưng Spring không nhận, trọng tâm là **connection/configuration/lifecycle của Spring listener**, chưa phải TTL hoặc Redis command performance.

### Tình huống B — Listener có lúc nhận, có lúc mất

1. Đo số message đã publish và số callback được gọi theo cửa sổ thời gian.
2. Đánh dấu timestamp publish, thời gian app reconnect và startup.
3. Kiểm tra network, Sentinel/Cluster topology và subscription re-registration.
4. Kiểm tra callback xử lý chậm, executor queue và exception.
5. Nếu message bắt buộc không được mất, thiết kế lại đường delivery có ACK/replay và idempotency; **không tìm cách bắt Pub/Sub thành queue bền vững bằng một cấu hình timeout**.

### Tình huống C — Redis key đã mất nhưng không nhận `expired`

1. Kiểm tra lệnh xóa key là TTL expiration, `DEL`, `UNLINK`, eviction hay overwrite.
2. Dùng `CONFIG GET notify-keyspace-events` để kiểm tra flag `E`/`x`.
3. Subscribe `__keyevent@0__:expired` trước khi tạo key thử `SET ... EX`.
4. Kiểm tra database, node/shard và TTL thực tế.
5. Kiểm tra subscriber có trực tuyến khi key bị Redis xóa không.
6. Nếu Cluster, kiểm tra notification phát trên node nào.
7. Không dùng “key biến mất” làm bằng chứng rằng lẽ ra phải nhận `expired`.

### Tình huống D — `RedisKeyExpiredEvent` của repository không chạy

1. Xác minh entity thật sự lưu qua repository và có `@TimeToLive` hoặc TTL hợp lệ.
2. Xem repository listener đã được bật và start từ khi nào.
3. Kiểm tra cấu hình keyspace notifications trên Redis server.
4. Đặt listener Redis raw trên `__keyevent@0__:expired` để tách Redis notification khỏi Spring application event.
5. Nếu raw listener có nhận nhưng Spring event không được phát, tập trung vào repository event adapter, keyspace mapping và Spring event listener.
6. Kiểm tra shadow-copy configuration nếu handler cần entity value.
7. Đánh giá index cleanup/repair nếu events bị mất trong thời gian downtime.

### Tình huống E — Chỉ mất expired events trên một số key

1. Xác định các key đó thuộc Redis DB/Cluster slot nào.
2. Kiểm tra node đang sở hữu key và `notify-keyspace-events` trên từng node cần thiết.
3. Kiểm tra subscriber có thực sự subscribe tới những node phát keyevent không.
4. Kiểm tra key có bị xóa hoặc overwrite trực tiếp không.
5. Kiểm tra expire/eviction policy và thời điểm failover.
6. Nếu là key do nhiều writer quản lý, xác định writer có vô tình thay đổi TTL không.

## 19. Bảng lỗi phổ biến

| Lỗi thiết kế/chẩn đoán | Vì sao listener không nhận? | Cách khắc phục |
| --- | --- | --- |
| Publish trước khi subscriber đăng ký | Pub/Sub không lưu message chờ | Đợi readiness có thể quan sát hoặc dùng durable queue |
| `ChannelTopic("orders.*")` | Dấu `*` bị coi là literal trong channel topic | Dùng `PatternTopic("orders.*")` khi muốn wildcard |
| Publisher dùng `orders.created` nhưng listener nghe `orders.events` | Không cùng channel | Thống nhất channel constant và cấu hình |
| `PUBSUB NUMSUB` bằng 0 với pattern listener | `NUMSUB` không đếm pattern subscription | Xem `NUMPAT`, log subscription và test publish |
| Nhận message nhưng không có log nghiệp vụ | Deserialize hoặc callback ném lỗi | Log entry trước parse, bật error handler |
| Listener bean tồn tại nhưng container chưa start | Bean creation khác subscription readiness | Kiểm tra lifecycle và trạng thái connection |
| Tự đóng connection của container | Subscription bị đứt | Để container quản lý connection |
| Callback I/O blocking kéo dài | Dispatch bị nghẽn | Giới hạn thời gian, chuyển xử lý nặng sang queue |
| Redis ACL cho GET/SET nhưng chặn SUBSCRIBE | Thiếu quyền command/channel | Cấp quyền tối thiểu đúng subscription |
| Chỉ bật `notify-keyspace-events Kx` nhưng nghe `__keyevent...` | Đã bật kiểu keyspace chứ không phải keyevent | Bật `E` cho keyevent hoặc đổi channel listener |
| Chỉ bật `notify-keyspace-events Ex` nhưng nghe `__keyspace...` | Không bật kiểu keyspace | Thêm `K` hoặc chuyển sang keyevent channel |
| Không bật flag `x` | Redis không phát expired notifications | Cấu hình nhóm expired |
| Subscribe `__keyevent@1__:expired` nhưng key ở DB 0 | Sai channel database | Dùng `@0` hoặc pattern đúng phạm vi |
| Dùng `DEL` rồi chờ event `expired` | Delete không phải TTL expiration | Theo dõi `del` nếu cần hoặc dùng cơ chế khác |
| Ghi đè bằng `SET` và làm mất TTL | Key không còn tự hết hạn | Dùng TTL rõ ràng/`KEEPTTL` theo hợp đồng |
| Key bị eviction chứ không expired | Nhóm sự kiện khác | Quan sát eviction metrics và `evicted` event |
| Mong event đúng mili giây TTL kết thúc | Redis expiration không là timer chính xác | Dùng polling/deadline và event bền vững nếu cần |
| Subscriber offline khi event phát | Không có replay | Thiết kế reconciliation/job bền vững |
| Chỉ subscribe một node Cluster | Keyevent chỉ phát từ node có key | Thiết kế coverage theo node và topology |
| Repository keyspace events chưa bật | Spring không phát application event | Cấu hình `@EnableRedisRepositories` và Redis notifications |
| Redis managed cấm `CONFIG SET` | App không đổi được notifications | Dùng cấu hình provider/admin; không tự tăng quyền |
| Sau TTL, callback `GET` key rồi mong lấy value | Key đã bị xóa | Lưu metadata trước expiration hoặc nguồn bền vững |
| Hai application cùng xử lý một expired message | Pub/Sub broadcast | Idempotency/coordination cho side effect |
| Dùng expired event làm nghiệp vụ phải chạy chính xác một lần | At-most-once và không durable | Queue/Stream/outbox + idempotency |

## 20. Thiết kế một cơ chế hết hạn có thể khôi phục

Trong một số ứng dụng, expired listener chỉ được dùng để **làm sạch cache, giải phóng metadata phụ hoặc cập nhật metric**. Nếu bỏ lỡ một vài sự kiện mà vẫn có cơ chế sửa lại trạng thái, Pub/Sub notifications có thể chấp nhận được.

Nhưng với những hành động có yêu cầu hoàn thành cuối cùng, như đóng một phiên thanh toán quá hạn, hủy reservation hoặc giải phóng hạn mức, chỉ dựa vào một `expired` callback là rủi ro.

Một mẫu đáng cân nhắc:

~~~text
             Tạo reservation có hạn
                        |
                        v
          Lưu expiresAt trong nguồn sự thật
                        |
                        v
          Redis key có TTL để truy cập nhanh
                        |
             +----------+----------+
             |                     |
             v                     v
      Redis expired event    Scheduled reconciliation
             |                     |
             +----------+----------+
                        |
                        v
           Kiểm tra trạng thái hiện tại
                        |
                        v
             Áp dụng thay đổi idempotent
                        |
                        v
                 Ghi nhận hoàn tất
~~~

Trong mô hình này:

- Event hết hạn giúp **kích hoạt nhanh** khi subscriber đang chạy.
- Reconciliation job giúp **bù lại** trường hợp event bị bỏ lỡ.
- `expiresAt` cho phép xác định một reservation đã quá hạn hay chưa mà không cần suy ra từ thứ tự callback.
- Một cập nhật có điều kiện trong nguồn dữ liệu ngăn việc xử lý trùng hoặc xử lý một reservation đã được gia hạn.
- Nếu yêu cầu phát hành side effect ngoài database, dùng outbox/queue và idempotency key phù hợp.

Không tự động hủy một tài nguyên chỉ vì nhận được expired message với cùng ID: key có thể đã được tạo lại hoặc nghiệp vụ đã gia hạn. Handler nên kiểm tra **phiên bản/trạng thái/deadline hiện tại** trước khi áp dụng side effect.

## 21. Checklist khi triển khai listener lên môi trường mới

**Redis và topology**

- Redis endpoint/port/TLS/ACL có đúng với ứng dụng không?
- Listener cần application Pub/Sub, keyevent, keyspace hay Repository event?
- Channel chính xác, pattern và database trong tên event đã được xác định?
- `notify-keyspace-events` có bật đúng `K`/`E` và nhóm event `x` không?
- Cấu hình notifications có được duy trì sau restart/managed Redis deployment không?
- Với Cluster, listener có theo dõi những node thực sự phát keyevent không?

**Spring**

- `RedisMessageListenerContainer` có được tạo thành bean và quản lý start/stop?
- Topic registration đã được thực hiện và có cách xác nhận readiness không?
- Error handler có ghi nhận callback failure không?
- Message serializer/parser của publisher và consumer có cùng hợp đồng không?
- Callback có bị block lâu hoặc executor bị quá tải không?
- Với Redis Repository, keyspace-event listener có thực sự được bật không?

**Nghiệp vụ và test**

- Có thể chứng minh message xuất hiện ở CLI trước khi sửa Spring không?
- Test có tách cache miss, expired và delete/eviction thành tình huống riêng?
- Integration test có tránh publish trước khi subscription sẵn sàng không?
- Handler có idempotent nếu nhiều instance cùng nhận message không?
- Khi listener offline, có cách phát hiện và đối soát event bị bỏ lỡ không?
- Nếu sự kiện bắt buộc xử lý, có durable source/queue/outbox thay cho chỉ Pub/Sub không?
- Metrics có tách `received`, `decode_failed` và `processed` không?

### Mẫu biên bản sự cố

Khi đội vận hành điều tra, nên ghi lại những dữ kiện tối thiểu:

~~~text
Feature:          session expiration cleanup
Redis mode:       standalone / Sentinel / Cluster
Endpoint scope:   environment + node/slot (đã ẩn thông tin nhạy cảm)
Listener type:    keyevent expired / Repository application event
Channel/pattern:  __keyevent@0__:expired
Notifications:    flags đang hiệu lực
Key namespace:    session:* (không ghi raw secret/session token)
Subscription:     đã xác nhận sẵn sàng lúc nào?
TTL observation:  PTTL trước khi key biến mất
Failure window:   có failover/restart/connection reset không?
Redis CLI probe:  nhận / không nhận expired của key test
Spring callback:  received / decode error / processing error
Recovery:         reconciliation chạy / chưa chạy
~~~

Biên bản có những bằng chứng này cho phép phân biệt **Redis không phát**, **subscriber bỏ lỡ** và **handler thất bại** mà không phải đoán qua một log “listener not working”.

## 22. Tổng kết

Khi Spring Data Redis listener không nhận thông điệp hoặc sự kiện hết hạn, hãy tách ba cơ chế trước khi sửa:

1. **Application Pub/Sub:** xác minh `PUBLISH`, `SUBSCRIBE`/`PSUBSCRIBE`, channel/pattern, ACL, subscription readiness và callback. Message đã phát trước khi subscribe hoặc trong lúc disconnect sẽ không tự được gửi lại.
2. **Redis expiration notification:** xác minh TTL, `notify-keyspace-events` với flag phù hợp, channel `__keyevent@0__:expired` hoặc `__keyspace@0__:<key>`, và nguyên nhân key biến mất. `DEL`, eviction, ghi đè và hết hạn TTL là những tình huống **khác nhau**.
3. **Repository expiry event:** kiểm tra `@TimeToLive`, `@EnableRedisRepositories` và lifecycle keyspace-event listener; lưu ý shadow copy, secondary index cleanup và notification Pub/Sub không bền vững.

Thứ tự chẩn đoán hiệu quả nhất là **Redis CLI → trạng thái subscription → Spring listener callback → nghiệp vụ**, kèm metric riêng cho từng tầng. Trong Redis Cluster, phải quan sát keyevent trên đúng node; trong Sentinel, phải tính đến khoảng mất sự kiện khi failover/reconnect.

Cuối cùng, một listener hoạt động bình thường vẫn **không cung cấp tính bền vững hoặc exactly-once processing**. Với những sự kiện quan trọng, cần một nguồn trạng thái đáng tin cậy, cơ chế xử lý bền vững và reconciliation/idempotency để khôi phục sau thời gian ứng dụng hoặc Redis không thể phát/nhận notification.

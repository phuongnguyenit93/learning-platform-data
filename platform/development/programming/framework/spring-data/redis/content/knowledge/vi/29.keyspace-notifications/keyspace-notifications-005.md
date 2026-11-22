# Giới hạn bảo đảm chuyển phát của thông báo khóa trong Spring Data Redis

## 1. Tại sao thông báo khóa không được bảo đảm đến ứng dụng?

Redis hỗ trợ **keyspace notifications** để các client quan sát thao tác trên key: được tạo, cập nhật, xóa, hết hạn TTL hoặc bị eviction do giới hạn bộ nhớ. Trong Spring Data Redis, thông báo có thể đi qua `RedisMessageListenerContainer`, `MessageListener` và các sự kiện Repository như `RedisKeyExpiredEvent`.

Điểm quan trọng nhất: **keyspace notifications được Redis phát qua Pub/Sub với ngữ nghĩa at-most-once**. Redis không lưu một bản ghi message chờ các subscriber xử lý, không yêu cầu ACK của Java handler và không tự phát lại những thông báo đã trôi qua khi ứng dụng offline.

Ví dụ:

```text
09:00  Redis SET session:42 "data" EX 600
09:05  Spring Boot dừng để deploy
09:10  Redis thấy session:42 hết hạn, xóa khóa, phát expired
09:12  Spring Boot chạy lại, mở subscription
09:13  Không có expired event cũ nào được replay
```

Redis đã hết hạn key đúng theo TTL, nhưng Spring callback không được gọi bù. Nếu callback là đường duy nhất để gửi email, hủy booking, dọn index hoặc cập nhật thống kê chính xác, tác vụ có thể bị bỏ sót.

> **Quy tắc thiết kế:** Việc key thay đổi trong Redis và việc application nhận thông báo là hai điều khác nhau. Notification thích hợp làm tín hiệu thời gian thực **best effort**, không phải nhật ký sự kiện bền vững.

## 2. Keyspace và keyevent notification

Redis hỗ trợ hai cách biểu diễn cùng nhóm sự kiện:

| Kiểu thông báo | Channel ví dụ | Nội dung message |
| --- | --- | --- |
| Keyspace | `__keyspace@0__:session:42` | `expired` |
| Keyevent | `__keyevent@0__:expired` | `session:42` |

`0` là logical database index của Redis. Với keyspace channel, tên key là thành phần của channel và message là tên sự kiện. Với keyevent channel, tên sự kiện nằm trong channel và message mang tên key.

Ví dụ khi lệnh `DEL session:42` thực sự xóa khóa:

```text
__keyspace@0__:session:42  -> del
__keyevent@0__:del         -> session:42
```

Thông báo keyevent thường chỉ cho biết tên key đã thay đổi. Nó **không tự chứa dữ liệu nghiệp vụ**, không mang đầy đủ payload vừa bị xóa và không cung cấp token xác nhận handler đã xử lý.

### So sánh với domain event

```text
Redis-generated event:
  __keyevent@0__:expired -> session:42

Application domain event:
  orders.cancelled -> {"orderId":"42","reason":"timeout"}
```

Domain event cần được thiết kế riêng nếu ứng dụng phải lưu lịch sử, truy vết, retry hay xử lý bắt buộc. Không nên sử dụng tên key Redis thay cho một message nghiệp vụ có contract và trạng thái bền vững.

## 3. At-most-once, at-least-once và exactly-once

**At-most-once** là ngữ nghĩa thông điệp có thể được chuyển phát tối đa một lần theo đường Pub/Sub đang xét. Nếu subscriber không tồn tại, bị mất kết nối hoặc không xử lý được, message không được gửi lại bởi Redis. Đây là ngữ nghĩa của Redis Pub/Sub.

**At-least-once** yêu cầu hệ thống lưu thông điệp và có khả năng gửi lại khi chưa có xác nhận thành công. Kết quả là consumer có thể nhận lại một message đã xử lý nhưng ACK thất bại, nên cần idempotency.

**Exactly-once ở cấp nghiệp vụ** là mục tiêu tác dụng phụ được áp dụng đúng một lần ngay cả khi retry, network failure và crash. Không thể suy ra tính chất này chỉ từ framework listener hoặc việc message được publish một lần; cần lưu trạng thái và có cơ chế cập nhật đáng tin cậy.

| Thuộc tính | Redis Pub/Sub / keyspace notification | Durable stream/queue được cấu hình phù hợp |
| --- | --- | --- |
| Lưu message sau publish | Không | Có, theo chính sách lưu trữ |
| Subscriber offline có thể đọc bù | Không | Có thể |
| Consumer ACK | Không | Có |
| Retry do handler lỗi | Không tự động | Có thể |
| Pending/unprocessed state | Không | Có thể |
| Chuyển phát phổ biến | At-most-once | Có thể thiết kế at-least-once |
| Exactly-once tác dụng nghiệp vụ | Không tự có | Vẫn cần idempotency/transaction |

Redis Streams hỗ trợ message tồn tại trong stream, consumer group và cơ chế ACK; nhưng **keyspace notifications không tự biến thành Stream entries**.

### At-most-once không đồng nghĩa handler Java không bao giờ chạy trùng

Nếu nhiều pod subscribe một channel, mỗi pod có thể nhận thông điệp. Nếu một client subscribe cả exact channel và pattern chồng lấn, một publish cũng có thể đến theo nhiều subscription. Ngoài ra, logic nghiệp vụ có thể phát lại yêu cầu. Vì vậy cùng một tác dụng phụ có thể được **thử nhiều lần**, dù Pub/Sub không replay event đã mất.

Cần phân biệt ngữ nghĩa truyền message với ngữ nghĩa xử lý nghiệp vụ.

## 4. Đường đi của một thông báo khóa

```text
Redis command / TTL cleanup
           |
           v
Redis tạo keyspace notification
           |
           v
Redis Pub/Sub chuyển tới các subscriber phù hợp
           |
           v
Network và Redis client
           |
           v
RedisMessageListenerContainer
           |
           v
MessageListener / RedisKeyExpiredEvent
           |
           v
Business handler
           |
           v
Database commit / HTTP call / Email hoàn thành
```

Không có transaction bao trùm toàn bộ đường đi này:

- Redis phát event không đồng nghĩa Java đã nhận.
- Java nhận không đồng nghĩa handler đã hoàn thành.
- Handler hoàn thành method không bảo đảm tác dụng phụ từ một hệ thống khác đã commit.
- Handler lỗi không khiến Redis tự gửi lại message.
- Redis không lưu trạng thái ACK của từng subscriber.

Vì vậy, số key đã hết hạn, số Redis notifications, số callback và số tác vụ hoàn thành có thể hoàn toàn khác nhau.

## 5. Cấu hình notify-keyspace-events

Redis thường tắt notification theo mặc định. Trên Redis thử nghiệm, có thể bật keyevent expiration:

```bash
redis-cli CONFIG SET notify-keyspace-events Ex
redis-cli CONFIG GET notify-keyspace-events
```

Các ký tự phổ biến:

| Ký tự | Nghĩa |
| --- | --- |
| `K` | Keyspace channel |
| `E` | Keyevent channel |
| `g` | Generic command events như `DEL`, `EXPIRE` |
| `x` | Expired events |
| `e` | Evicted events |
| `$` | String operations |
| `h` | Hash operations |
| `s` | Set operations |
| `z` | Sorted set operations |
| `A` | Alias cho nhiều loại event thông dụng |

Phải có ít nhất `K` hoặc `E` thì event mới được phát.

Ví dụ:

```text
Ex  -> expired keyevents
Kx  -> expired keyspace notifications
Egx -> generic keyevents và expired keyevents
KEA -> phần lớn nhóm keyspace/keyevent phổ biến
```

Cấu hình rộng hơn có thể làm tăng số notification và chi phí CPU/network. Không nên bật toàn bộ trên Redis production đang chịu tải chỉ để thử nghiệm.

**Bật `Ex` không nâng mức bảo đảm delivery**: không có ACK, replay hay durable log.

### Redis được quản lý

Một số dịch vụ Redis không cho ứng dụng gọi `CONFIG SET`. Cần cấu hình qua hệ thống quản trị nhà cung cấp. Spring Data Redis Repository có thể được cấu hình để không cố chạy `CONFIG` khi khởi tạo listener.

## 6. Tự quan sát bằng redis-cli

Terminal A:

```bash
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
```

Terminal B:

```bash
redis-cli SET demo:key "value" EX 5
```

Khi Redis thực sự xóa `demo:key`, Terminal A có thể nhận message chứa `demo:key`. Nếu Terminal A bị ngắt kết nối khi Redis publish, lần subscribe sau không nhận lại message.

Để quan sát cả xóa trực tiếp:

```bash
redis-cli CONFIG SET notify-keyspace-events Egx
redis-cli PSUBSCRIBE '__keyevent@0__:*'
```

Trong terminal khác:

```bash
redis-cli SET demo:delete "value"
redis-cli DEL demo:delete
```

Event liên quan việc xóa bằng `DEL` là `del`, không phải `expired`. Các nhóm event phải được bật phù hợp.

## 7. `expire`, `expired`, `del` và `evicted` không giống nhau

| Thao tác hoặc nguyên nhân | Event thường liên quan | Ý nghĩa |
| --- | --- | --- |
| `EXPIRE key 60` | `expire` | Đặt thời hạn trong tương lai |
| Redis thực sự xóa key do TTL | `expired` | Key bị xóa vì hết hạn |
| `DEL key` | `del` | Xóa trực tiếp |
| `EXPIRE key 0` | `del` | Xóa ngay khi hạn không dương |
| Xóa do maxmemory | `evicted` | Giải phóng bộ nhớ, không phải TTL |

Chỉ subscribe `__keyevent@0__:expired` sẽ không nhận mọi thao tác làm key biến mất. Nếu application vừa dùng `DEL` vừa dùng TTL, cần xác định loại event phù hợp với mục tiêu quan sát.

Một lệnh có thể làm thay đổi nhiều phần tử trong một Redis collection, nhưng không đồng nghĩa luôn có một notification cho từng phần tử. Đừng suy ra số lượng thay đổi nghiệp vụ từ số message nếu không có contract tương ứng.

## 8. Sự kiện expired có thể phát muộn

Redis quản lý TTL theo hai cách:

- **Passive expiration:** một lệnh truy cập key đã quá hạn khiến Redis phát hiện và xóa key.
- **Active expiration:** Redis định kỳ kiểm tra, dọn những key có TTL đã hết ngay cả khi không được truy cập.

```text
T0                T_deadline              T_deleted            T_received
|                      |                       |                     |
SET EX 60          Hết hiệu lực          Redis xóa khóa      Spring nhận
                                        và publish          nếu online
```

Redis phát `expired` khi key **thực sự bị xóa**, không bảo đảm chính xác lúc TTL chạm 0. Khi có nhiều key TTL mà không ai truy cập, độ trễ xóa vật lý có thể đáng kể.

Điều cần phân biệt:

- Một key đã qua hạn không còn hợp lệ cho thao tác đọc thông thường.
- Callback không được bảo đảm chạy đúng tại deadline.

Do đó không dùng `expired` làm bộ hẹn giờ chính xác cho việc hủy đơn hay giải phóng tài nguyên phải đúng thời điểm. Hãy lưu deadline nghiệp vụ và dùng worker có thể xử lý bù.

## 9. Mất event khi ứng dụng offline

```text
Spring Boot: RUNNING -------- STOPPED ------------- RUNNING
Redis:       RUNNING ----------------------------- RUNNING
Key TTL:     còn hạn -------- hết hạn / bị xóa
Pub/Sub:                       published
Subscriber:  connected         absent              connected again
```

Các tình huống:

- Deploy/restart hoặc rolling update.
- JVM crash, container bị kill, OOM.
- Network partition, connection timeout.
- Redis failover và client chưa resubscribe.
- Application context đã tạo bean nhưng listener chưa sẵn sàng.
- Redis cấu hình sai event group.
- Subscribe sai channel, database hoặc node.

`RedisMessageListenerContainer` có thể quản lý connection và subscription lifecycle, nhưng **resubscribe chỉ nhận message mới**. Redis không cung cấp lịch sử những event đã phát khi subscriber offline.

### Lỗ hổng khi startup

Việc một bean đã được Spring tạo không chứng minh Redis đã xác nhận subscribe. Nếu event xảy ra trước khi subscription được thiết lập, nó có thể bị mất. Integration test cần bảo đảm subscriber readiness trước khi publish, thay vì chỉ dùng một khoảng `Thread.sleep` cố định.

## 10. Handler đã nhận vẫn có thể thất bại

Ví dụ:

```java
@Override
public void onMessage(Message message, byte[] pattern) {
    String key = decode(message.getBody());
    emailService.sendExpirationNotice(key);
}
```

Nếu `sendExpirationNotice` ném exception hoặc timeout:

- Redis không nhận ACK xử lý.
- Redis không tự gửi lại keyspace event.
- Không có pending queue trong Pub/Sub.
- Một error handler của Spring chỉ giúp xử lý/log exception cục bộ.

Ngay cả khi gửi email thành công nhưng response bị mất, retry thủ công có thể gửi trùng. Vì vậy phải có idempotency hoặc trạng thái tác vụ đáng tin cậy nếu đây là yêu cầu bắt buộc.

## 11. Nhiều subscribers có thể xử lý cùng thông báo

```text
                    Redis expired keyevent
                       /       |       \
                      v        v        v
                    Pod A    Pod B    Pod C
```

Nếu cả ba pod cùng subscribe, cả ba đều có thể nhận callback. Nếu callback ghi metric local, điều đó có thể phù hợp; nếu callback gửi email hay hoàn tiền, có nguy cơ xử lý trùng.

**Hai rủi ro độc lập:**

1. **Mất tác vụ:** toàn bộ subscriber offline lúc Redis publish.
2. **Tác vụ trùng:** nhiều subscriber hoặc nhiều đường retry cùng gây tác dụng phụ.

Đừng coi subscriber count là số tác vụ nghiệp vụ đã được hoàn thành chính xác một lần. Với tác dụng phụ quan trọng, phải dùng idempotency key, điều kiện trạng thái hoặc một queue có cơ chế phân công công việc.

## 12. Spring Data Redis: MessageListener cho expired events

Ví dụ listener nhận keyevent `expired`:

```java
package com.example.redis;

import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class ExpiredKeyObserver implements MessageListener {

    private static final Logger log =
        LoggerFactory.getLogger(ExpiredKeyObserver.class);

    @Override
    public void onMessage(Message message, byte[] pattern) {
        String channel = new String(
            message.getChannel(), StandardCharsets.UTF_8
        );

        String key = new String(
            message.getBody(), StandardCharsets.UTF_8
        );

        log.info("Observed Redis event: channel={}, key={}",
                 channel, key);

        // Chỉ quan sát/tăng metric best effort.
    }
}
```

Đăng ký listener:

```java
package com.example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class ExpirationListenerConfig {

    @Bean
    RedisMessageListenerContainer expirationListenerContainer(
            RedisConnectionFactory factory,
            ExpiredKeyObserver observer) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(factory);

        container.addMessageListener(
            observer,
            new ChannelTopic("__keyevent@0__:expired")
        );

        return container;
    }
}
```

Ví dụ giả định key được mã hóa bằng UTF-8 text. Redis phải bật notification tương ứng, ví dụ `Ex`. `MessageListener` nhận bytes của message, không bảo đảm payload gốc của key còn tồn tại.

Cấu hình listener giúp ứng dụng **có cơ hội** nhận event khi kết nối hoạt động; không chứng minh đã nhận đầy đủ mọi event.

## 13. Repository TTL và RedisKeyExpiredEvent

Spring Data Redis Repository hỗ trợ TTL trên entity qua `@RedisHash(timeToLive = ...)` hoặc `@TimeToLive`.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("login-session")
public class LoginSession {

    @Id
    private String id;

    private String accountId;

    @TimeToLive
    private Long ttlSeconds;

    public LoginSession() { }

    public LoginSession(String id, String accountId, Long ttlSeconds) {
        this.id = id;
        this.accountId = accountId;
        this.ttlSeconds = ttlSeconds;
    }

    public String getId() { return id; }
    public String getAccountId() { return accountId; }
    public Long getTtlSeconds() { return ttlSeconds; }
}
```

Cấu hình bật listener từ lúc application startup:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP
)
public class RepositoryConfig {
}
```

Handler:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.RedisKeyExpiredEvent;
import org.springframework.stereotype.Component;

@Component
public class SessionExpirationObserver {

    private static final Logger log =
        LoggerFactory.getLogger(SessionExpirationObserver.class);

    @EventListener
    public void onExpired(RedisKeyExpiredEvent<?> event) {
        log.info("Repository entity expired: id bytes={}",
                 event.getId().length);
    }
}
```

`RedisKeyExpiredEvent` được phát **sau khi Repository nhận notification từ Redis**. Vì vậy nó chịu cùng giới hạn của Pub/Sub. Nếu event bị mất ở Redis subscription, Spring application event không tự xuất hiện sau restart.

## 14. ON_STARTUP, ON_DEMAND và OFF

| Chế độ | Cách hoạt động | Giới hạn |
| --- | --- | --- |
| `ON_STARTUP` | Khởi tạo listener khi Spring bắt đầu | Không replay event lúc app offline |
| `ON_DEMAND` | Khởi tạo khi cần xử lý entity có TTL | Có thể bỏ lỡ thêm event trước khi listener sẵn sàng |
| `OFF` | Không bật listener Repository | Không có RedisKeyExpiredEvent qua listener này |

`ON_STARTUP` giúp giảm cửa sổ listener chưa đăng ký, nhưng không nâng delivery guarantee từ at-most-once lên at-least-once.

Nếu dịch vụ Redis được quản lý không cho `CONFIG SET`, có thể cấu hình Repository không tự thay đổi notification settings:

```java
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
    keyspaceNotificationsConfigParameter = ""
)
```

Redis server vẫn phải được nhà vận hành bật event group thích hợp. Tùy chọn trên chỉ tránh việc Spring cố chạy `CONFIG` khi khởi tạo.

## 15. Phantom/shadow copy không phải message history

Redis Repository có thể lưu **phantom copy** với TTL dài hơn khóa gốc khoảng 5 phút. Khi listener nhận expiration event, framework có thể lấy nội dung entity từ bản sao dù key chính đã biến mất.

```text
T0       Lưu entity gốc TTL 15 phút
         Lưu phantom copy lâu hơn khoảng 5 phút

T+15     Redis xóa key gốc và publish expired
         Listener online có thể dùng phantom copy

T+20     Phantom copy cũng có thể hết hạn
```

Nếu ứng dụng offline lúc Redis publish ở T+15, phantom copy còn tồn tại ở T+18 **không làm event cũ được replay**. Nó chỉ hỗ trợ payload trong trường hợp notification thực sự đến listener.

Có thể tắt shadow copy khi không cần domain object trong event:

```java
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
    shadowCopy = RedisKeyValueAdapter.ShadowCopy.OFF
)
```

Khi tắt, handler không nên kỳ vọng `getValue()` chứa đầy đủ entity. **Shadow copy không phải durable event log.**

## 16. Missed notification có thể làm secondary index bị cũ

Một entity có thể có secondary index:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("verification")
public class VerificationCode {

    @Id
    private String id;

    @Indexed
    private String accountId;

    @TimeToLive
    private Long ttlSeconds;

    // constructor, getter và setter được triển khai theo ứng dụng
}
```

Redis Repository có thể sử dụng Pub/Sub notification để dọn các tham chiếu index sau khi entity hết hạn.

```text
Trước TTL:
  verification:v-10      entity tồn tại
  index accountId=a-7    chứa ID v-10

Sau khi entity hết hạn, listener offline:
  verification:v-10      entity không còn
  index accountId=a-7    có thể vẫn chứa ID v-10
```

Tài liệu Spring Data Redis cảnh báo rằng missed Pub/Sub messages có thể làm secondary indexes giữ tham chiếu tới entity đã hết hạn.

Hệ quả có thể gồm:

- Truy vấn cần bỏ ID không còn entity.
- Count dựa trực tiếp vào member của index có thể sai.
- Index giữ thêm dữ liệu rác.
- Dọn index chỉ dựa vào expired callback không đầy đủ.

Key chính hết hạn vẫn không hợp lệ; vấn đề nằm ở **dữ liệu phụ thiếu nhất quán**, không phải TTL không hoạt động.

Với index/ZSET do ứng dụng tự xây, Redis cũng không tự xóa member chỉ vì key entity độc lập đã hết TTL.

## 17. Redis Cluster: keyspace events chỉ phát từ node liên quan

Trong Redis Cluster, mỗi node quản lý một tập khóa. Keyspace notifications được phát ở **node sở hữu key**, không tự broadcast sang mọi node.

```text
Redis Cluster

 Node A               Node B               Node C
 keys A               keys B               keys C
  |                    |                    |
 events A             events B             events C
```

Một subscriber chỉ kết nối Node A không thể mặc định nhận đủ notification của key thuộc Node B và C.

Để nhận toàn bộ events:

1. Phải biết các node cần subscribe.
2. Đảm bảo subscription trên từng node liên quan.
3. Theo dõi resharding/topology/failover.
4. Khôi phục subscription khi node thay đổi.
5. Vẫn có cơ chế đối soát vì subscription đầy đủ không tạo ACK hoặc replay.

Hành vi cụ thể của Redis client và cách Spring Data Redis kết nối cluster phải được xem theo driver và phiên bản đang dùng. Không coi “đã kết nối tới Redis Cluster” là tương đương “đã subscribe đầy đủ keyspace notifications trên mọi node”.

## 18. Logical database trong tên channel

Ví dụ:

```text
__keyevent@0__:expired
__keyevent@1__:expired
```

Nếu ứng dụng nghe `@0` trong khi key thuộc database 1, subscription đó không nhận message `@1`.

Redis Pub/Sub channel thông thường không tự được phân vùng theo logical database của subscriber, nhưng **tên keyspace notification channel** có chứa database index nên phải chọn đúng channel.

Trong Redis Cluster, database 0 được sử dụng; Redis standalone có thể có nhiều logical databases theo cấu hình.

## 19. Failover và restart không làm Redis phát lại notification cũ

Khi Redis primary hoặc mạng gặp sự cố:

```text
Spring subscribed
       |
       v
Connection lost
       |
       v
Redis failover
       |
       v
Client reconnects
       |
       v
Subscribe again
```

Những message đã được Redis publish lúc không có subscription thích hợp không trở thành pending events.

RDB/AOF hỗ trợ persistence dữ liệu Redis theo cấu hình, **không phải** lịch sử Pub/Sub cho từng subscriber. Không suy luận Redis được bật persistence thì những expired events bị bỏ lỡ có thể được khôi phục.

## 20. Không có SLA đúng deadline chỉ dựa trên expired event

Một công việc có thể trải qua:

```text
t_deadline  TTL hết theo logic
t_delete    Redis xóa key
t_publish   Redis tạo notification
t_receive   Driver nhận message
t_dispatch  Java callback được gọi
t_complete  Tác dụng nghiệp vụ hoàn thành
```

Độ trễ từ deadline đến hoàn thành phụ thuộc vào:

- Active/passive expiration.
- Network và khả năng reconnect.
- Executor/thread của Spring listener.
- Deserialize payload.
- Database/HTTP calls trong handler.
- Lỗi, timeout và retry.

Nếu notification mất, `t_complete` có thể không xảy ra. Vì vậy không đưa một SLA “xử lý xong trong đúng 1 giây sau TTL” chỉ dựa trên Redis expired events.

## 21. Redis Streams không tự sửa được notification bị mất

Một phương án trông có vẻ mạnh hơn:

```text
Redis key expires
      |
      v
Pub/Sub expired event
      |
      v
Spring listener
      |
      v
XADD event-stream ...
      |
      v
Consumer group xử lý, XACK
```

Nếu Spring listener offline khi Redis publish, **không có callback để ghi XADD**. Stream chỉ lưu những event đã được ghi vào Stream; nó không tái tạo những Pub/Sub messages đã mất trước đó.

Muốn có đường xử lý bền vững, phải ghi metadata nghiệp vụ **ngay khi tạo deadline** hoặc có nguồn dữ liệu chuẩn để đối soát:

```text
Create booking:
  Database ghi (id, status=PENDING, expiresAt)
  Redis ghi key TTL để tối ưu/tín hiệu
  Outbox/job ledger ghi yêu cầu cần xử lý

Worker:
  Đọc booking PENDING đã quá hạn
  Chuyển trạng thái có điều kiện
  Phát tác dụng phụ từ durable queue/outbox
  Retry và đánh dấu đã hoàn thành
```

Notification Redis có thể đánh thức worker sớm, nhưng không được là danh sách công việc duy nhất.

## 22. Nguồn dữ liệu chuẩn và deadline bền vững

Giả sử một booking phải được hủy sau 15 phút. Thay vì chờ chỉ một keyevent, lưu trạng thái và deadline trong database:

```sql
CREATE TABLE booking (
    id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(16) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_booking_pending_deadline
    ON booking (expires_at)
    WHERE status = 'PENDING';
```

Câu lệnh xử lý có điều kiện:

```sql
UPDATE booking
   SET status = 'EXPIRED'
 WHERE id = :id
   AND status = 'PENDING'
   AND expires_at <= CURRENT_TIMESTAMP;
```

Nếu handler expired chạy trước và cập nhật thành công, job chạy sau thấy booking không còn `PENDING`. Nếu job chạy trước và event tới muộn, callback không lặp tác dụng.

Nếu booking được gia hạn, điều kiện `expires_at <= CURRENT_TIMESTAMP` tránh hủy nhầm đối tượng đang còn hạn. Nếu ID có thể được tái sử dụng, cần generation/version để phân biệt event của đời cũ.

### Scheduler phục hồi sau downtime

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class BookingExpirationRecovery {

    private final JdbcTemplate jdbc;

    public BookingExpirationRecovery(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Scheduled(fixedDelay = 30000, initialDelay = 10000)
    public void sweep() {
        int changed = jdbc.update("""
            UPDATE booking
               SET status = 'EXPIRED'
             WHERE status = 'PENDING'
               AND expires_at <= CURRENT_TIMESTAMP
            """);

        System.out.println("Expired bookings recovered: " + changed);
    }
}
```

Bật `@EnableScheduling` trong ứng dụng.

Trong khi Spring Boot offline, scheduler không chạy. Nhưng khi restart, nó có thể tìm toàn bộ booking chưa xử lý từ database dù Redis notification đã mất.

**Giới hạn:** Ví dụ chỉ cập nhật trạng thái. Khi có email, thanh toán hay external API, cần transactional outbox/queue và idempotency. Với nhiều bản ghi, chia batch và điều phối workers.

## 23. Nếu chỉ có Redis: dùng deadline ledger

Nếu Redis là nơi lưu trữ chính, có thể duy trì một **ZSET ledger** không hết hạn cùng lúc với key tạm:

```text
session:42               TTL 15 phút
jobs:deadlines           Sorted Set: member=session:42, score=deadline
jobs:payload:session:42  metadata để xử lý sau khi session:42 biến mất
```

Ví dụ:

```redis
SET session:42 "temporary" EX 900
ZADD jobs:deadlines 1893456000000 session:42

ZRANGE jobs:deadlines -inf 1893456000000 BYSCORE LIMIT 0 100
```

Worker đọc các deadline đã qua rồi xử lý. Chỉ dọn member sau khi hoàn thành:

```redis
ZREM jobs:deadlines session:42
```

Điều kiện cần để giải pháp này đáng tin hơn Pub/Sub:

- Ledger và payload không hết hạn cùng key chính.
- Việc ghi key và ghi ledger có quy tắc nhất quán.
- Có claim/lease hoặc cập nhật trạng thái có điều kiện cho nhiều workers.
- Chỉ đánh dấu hoàn tất sau khi kết quả được ghi nhận.
- Có retry và idempotency.
- Hiểu persistence/failover và ràng buộc hash slot trong Redis Cluster.

ZSET tự nó chưa phải durable queue đầy đủ. Với công việc có hậu quả nghiêm trọng, nên dùng một hệ thống có bảo đảm transaction và retry được thiết kế rõ ràng.

## 24. Phục hồi secondary index khi notification bị mất

Ba cách thực tế:

**1. Xác minh khi đọc:** lấy các ID từ index, tải entity; bỏ ID không còn tồn tại và ghi nhận orphan references.

**2. Dọn theo batch:** với index do ứng dụng tạo, định kỳ quét một số lượng member giới hạn rồi loại bỏ ID rác. Dùng phương pháp duyệt phù hợp; không gọi `KEYS *` thường xuyên trên Redis lớn.

**3. Rebuild từ nguồn chuẩn:** nếu Redis là cache/read model, xây lại index từ database có thẩm quyền, có thể dùng namespace version để chuyển đổi an toàn.

Nếu là index nội bộ của Spring Data Redis Repository, phải hiểu cấu trúc và cơ chế hỗ trợ của phiên bản cụ thể trước khi tự sửa.

## 25. Chỉ số theo dõi và giới hạn

Có thể quan sát:

```bash
redis-cli CONFIG GET notify-keyspace-events
redis-cli INFO stats
redis-cli INFO keyspace
redis-cli PUBSUB CHANNELS
redis-cli PUBSUB NUMSUB __keyevent@0__:expired
```

| Chỉ số | Có thể biết | Không chứng minh |
| --- | --- | --- |
| `notify-keyspace-events` | Redis bật loại event nào | Spring nhận đầy đủ |
| `expired_keys` | Số key Redis đã xóa vì TTL | Số callback thành công |
| `PUBSUB NUMSUB` | Subscription hiện có | Handler đã commit |
| Listener log | Message ứng dụng thực nhận | Message mất khi offline |
| Overdue jobs trong nguồn chuẩn | Công việc còn tồn | Redis event nào bị mất |
| Orphan index count | ID không còn entity | Nguyên nhân chính xác từng orphan |

Để theo dõi quá trình phục hồi, có thể đo:

```text
keyevent_received_total
keyevent_handler_failures_total
listener_disconnect_total
listener_reconnect_total
overdue_work_count
oldest_overdue_age_seconds
reconciliation_processed_total
orphan_index_reference_total
```

Không dùng từng key ID làm metric label có cardinality cao; dùng log/trace có kiểm soát nếu cần chẩn đoán một key cụ thể.

Không có Redis command nào trả đầy đủ danh sách keyspace notifications mà subscriber X đã bỏ lỡ, bởi Redis Pub/Sub không lưu lịch sử đó.

## 26. Thí nghiệm chứng minh không replay

Thực hiện trên Redis **thử nghiệm**.

Bước 1 — Bật event:

```bash
redis-cli CONFIG SET notify-keyspace-events Ex
```

Bước 2 — Terminal A subscribe:

```bash
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
```

Bước 3 — Terminal B tạo key:

```bash
redis-cli SET demo:online "value" EX 3
```

Khi Redis xóa key, Terminal A có thể thấy message `demo:online`.

Bước 4 — Dừng Terminal A và tạo key:

```bash
redis-cli SET demo:offline "value" EX 3
```

Sau hạn, xác nhận:

```bash
redis-cli EXISTS demo:offline
redis-cli TTL demo:offline
```

Khi key đã biến mất, `EXISTS` trả `0`, `TTL` trả `-2`.

Bước 5 — Subscribe lại:

```bash
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
```

Message đã publish khi subscriber offline không được replay.

**Lưu ý timing:** nếu Redis chỉ thực sự xóa key sau lúc subscriber quay lại, event có thể được nhận vì được *publish muộn*. Đó không phải khả năng phát lại message đã publish trước đó.

## 27. Thực hành với nhiều instance

Chạy hai instance Spring Boot cùng subscribe `__keyevent@0__:expired`.

Tạo một key TTL ngắn. Khi event đến, cả hai instance có thể ghi log.

Sau đó dừng cả hai, tạo một key mới, chờ hết hạn rồi khởi động lại. Không instance nào được Redis replay event đã publish trong lúc cả hai offline.

Thí nghiệm chứng minh hai vấn đề khác nhau:

- Có thể **không xử lý lần nào** khi tất cả subscriber offline.
- Có thể **xử lý nhiều lần** ở cấp nghiệp vụ khi nhiều subscriber cùng phản ứng.

Một cơ chế durable work cùng idempotency cần được thiết kế để kiểm soát cả hai.

## 28. Phân loại nhu cầu

| Tác vụ | Có thể chấp nhận mất notification? | Khuyến nghị |
| --- | --- | --- |
| Log expiration để quan sát gần đúng | Có | Pub/Sub best effort |
| Refresh UI | Thường có | Pub/Sub + refresh từ nguồn chuẩn |
| Invalidate local cache | Có nếu TTL/version hạn chế stale | Pub/Sub + TTL/version |
| Đếm chính xác số session hết hạn | Không | Nguồn/bộ đếm đáng tin cậy |
| Dọn secondary index | Không nếu cần chính xác lâu dài | Notification + reconciliation |
| Hủy booking hết hạn | Không | Deadline bền vững + worker |
| Gửi email bắt buộc | Không | Durable queue/outbox |
| Xử lý thanh toán/hoàn tiền | Không | Transaction/idempotency |
| Kiểm soát quyền truy cập | Không | Kiểm tra trạng thái có thẩm quyền |

Câu hỏi nền tảng là: **nếu toàn bộ subscriber tắt 30 phút, sau restart ứng dụng lấy danh sách những công việc đã quá hạn nhưng chưa làm từ đâu?**

Nếu không có câu trả lời, không nên dùng keyspace notification làm nguồn duy nhất cho quy trình bắt buộc.

## 29. Những ngộ nhận phổ biến

### “Bật `Ex` là đủ để không mất expired events”

Không. `Ex` chỉ bật loại thông báo, không tạo lưu trữ và retry.

### “Redis persistence cũng lưu lịch sử notifications”

Không. RDB/AOF dùng để phục hồi dữ liệu Redis theo cấu hình; Pub/Sub không có event log cho subscriber.

### “RedisMessageListenerContainer reconnect sẽ nhận bù”

Không. Kết nối lại chỉ giúp nhận event mới.

### “ON_STARTUP giúp RedisKeyExpiredEvent có bảo đảm mạnh hơn”

Không. Chế độ này chỉ khởi tạo listener sớm hơn.

### “Shadow copy thêm năm phút nghĩa là giữ thông báo năm phút”

Không. Shadow copy có thể giữ payload, không giữ message.

### “`expired` phát đúng khi TTL bằng 0”

Không. Redis publish khi key thực sự bị xóa; có thể trễ.

### “Đã subscribe một Redis Cluster node là đủ”

Không. Keyspace events là node-specific.

### “At-most-once nghĩa là business handler không thể bị gọi trùng”

Không. Có thể có nhiều subscribers/overlapping subscriptions hoặc retry ở tầng application.

### “Handler ném exception thì Redis tự gửi lại”

Không. Pub/Sub không có ACK/retry.

### “Cho XADD vào expired callback là durable tuyệt đối”

Không. Nếu callback không được gọi do mất Pub/Sub message, Stream không có entry để xử lý.

## 30. Câu hỏi thường gặp

**Ứng dụng tắt lúc Redis key hết hạn, key còn hợp lệ sau restart không?**

Không, nếu deadline đã qua và Redis quản lý expiration bình thường. Việc Spring không nhận event không làm key sống lại.

**Có thể lấy lại notification bị bỏ lỡ bằng subscribe lại không?**

Không. Redis Pub/Sub không có lịch sử per-subscriber.

**Tại sao key đã hết TTL nhưng event đến sau vài giây?**

Vì Redis phát khi thực sự xóa key theo active/passive expiration.

**Một sự kiện expired có chứa value cũ không?**

Keyevent payload thường là tên key. Key gốc đã bị xóa; Spring Data Redis Repository có thể dùng phantom copy cho payload khi event đến, nhưng không replay event.

**Redis Cluster chỉ cần một listener trên một node không?**

Không nên giả định. Keyspace notifications phát theo node quản lý key, cần xác định subscription phù hợp topology.

**`expired_keys` có cho biết bao nhiêu thông báo Java nhận được không?**

Không. Nó là thống kê Redis về key bị xóa do TTL.

**Redis Streams có tự thu expired notifications không?**

Không. Ứng dụng cần ghi Stream entries hoặc có nguồn deadline bền vững độc lập.

**Có thể dùng notification để invalidate local cache không?**

Có, nếu chấp nhận best effort và bổ sung TTL/version/refresh để phục hồi khi mất thông báo.

**Spring Redis Repository có thể còn index cũ sau downtime không?**

Có thể. Spring Data Redis nêu rõ missed Pub/Sub expiration messages có thể khiến secondary indexes còn ID của entity đã hết hạn.

**Nhiều subscribers cùng lắng nghe có bảo đảm một tác vụ chỉ làm một lần không?**

Không. Cần idempotency, claim hoặc consumer group/queue phù hợp.

## 31. Ghi nhớ

1. **Thông báo khóa Redis được chuyển bằng Pub/Sub at-most-once**, không có ACK, history hoặc replay.
2. **TTL và delivery của notification độc lập.** Key có thể hết hiệu lực đúng dù Spring callback không chạy.
3. **`expired` được publish khi Redis xóa key**, có thể trễ hơn deadline.
4. **Spring MessageListener, RedisKeyExpiredEvent, ON_STARTUP và phantom copy không nâng bảo đảm delivery**.
5. **Keyspace notifications trong Redis Cluster phát theo node**, cần bao phủ topology.
6. **Có thể mất message hoặc trùng tác dụng nghiệp vụ**, cần reconciliation và idempotency.
7. **Công việc bắt buộc cần deadline/state bền vững, retry và worker xử lý bù**; notification chỉ nên dùng làm tín hiệu hỗ trợ.

## Tài liệu tham khảo chính thức

- [Redis – Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Redis – Pub/Sub Delivery Semantics](https://redis.io/docs/latest/develop/pubsub/)
- [Redis – EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis – Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [Spring Data Redis – Time To Live (Redis Repositories)](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis – Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis – RedisMessageListenerContainer API](https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/listener/RedisMessageListenerContainer.html)

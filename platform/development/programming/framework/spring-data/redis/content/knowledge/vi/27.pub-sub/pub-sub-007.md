# Luồng xử lý, thứ tự và xử lý lỗi của listener trong Spring Data Redis Pub/Sub

**Redis Pub/Sub** là cơ chế gửi thông điệp theo mô hình *publish–subscribe*: publisher phát một message vào channel, Redis phân phối message đó đến những client đang subscribe channel hoặc pattern phù hợp tại thời điểm phát. Trong Spring Data Redis, ứng dụng thường nhận message thông qua **`MessageListener`** và **`RedisMessageListenerContainer`**.

Điều cần phân biệt ngay từ đầu:

- Redis Pub/Sub truyền message đến **subscriber đang kết nối và đăng ký**; nó không phải hàng đợi bền vững có lịch sử để đọc lại.
- Redis có thứ tự xử lý/phát message ở phía server, nhưng **thứ tự hoàn thành logic của listener trong ứng dụng Spring** còn phụ thuộc executor, các thread và những thao tác bất đồng bộ.
- Exception phát sinh khi listener xử lý **không khiến Redis tự gửi lại message**. `ErrorHandler` giúp ghi nhận/xử lý lỗi phía ứng dụng; nó không tạo cơ chế ACK/retry mặc định.
- Redis Pub/Sub không cam kết *exactly-once processing*. Nếu sự kiện quan trọng không được phép mất, cần xem xét **Redis Streams, message broker có lưu trữ** hoặc thiết kế lưu sự kiện khác.

Bài học này giải thích luồng từ publisher đến listener, các mức bảo đảm về thứ tự, cách cấu hình listener container, các kịch bản lỗi và cách chọn chiến lược xử lý phù hợp.

## 1. Mô hình publish–subscribe trong Redis

Giả sử hệ thống catalog thông báo khi một sản phẩm thay đổi:

```text
                         Redis server
                      channel: catalog.events
                             |
                  +----------+----------+
                  |                     |
              Subscriber A          Subscriber B
             (cache service)       (audit service)
                  |                     |
          RedisMessageListener   RedisMessageListener
             Container              Container
                  |                     |
          MessageListener       MessageListener
```

Publisher gửi:

```redis
PUBLISH catalog.events "{\"eventId\":\"evt-101\",\"type\":\"PRODUCT_UPDATED\",\"productId\":\"p-42\"}"
```

Những subscriber đang subscribe `catalog.events` sẽ có cơ hội nhận cùng message. Nếu lúc đó subscriber C chưa kết nối hoặc chưa subscribe, **Redis không giữ message này để C đọc khi kết nối sau**.

Khác với consumer group trong Redis Streams, một channel Pub/Sub:

- Không lưu lịch sử message.
- Không có message ID do Redis cấp để replay.
- Không có offset hay cursor để subscriber khôi phục từ vị trí đã đọc.
- Không có ACK để xác nhận xử lý nghiệp vụ.
- Không có cơ chế retry tự động cho listener bị lỗi.
- Không có hàng đợi dùng chung để tự phân chia mỗi message cho đúng một consumer.

Do đó, hai subscriber cùng channel thường **đều nhận message** chứ không chia nhau mỗi người một nửa. Điều này phù hợp với thông báo cập nhật cache hoặc tín hiệu sự kiện tạm thời, nhưng không tự đáp ứng bài toán xử lý công việc quan trọng chỉ một lần.

## 2. Luồng xử lý đầy đủ từ publisher đến listener

Với Spring Data Redis, luồng điển hình:

```text
1. Application publisher
       |
       | StringRedisTemplate.convertAndSend(channel, payload)
       v
2. Redis server
       |
       | Phân phối message cho subscriber đang đăng ký
       v
3. Redis client connection đang subscribe
       |
       | Nhận frame Pub/Sub trên kết nối
       v
4. RedisMessageListenerContainer
       |
       | Định tuyến theo channel/pattern và dispatch
       v
5. TaskExecutor của container
       |
       | Chạy callback (có thể trên thread riêng)
       v
6. MessageListener.onMessage(message, pattern)
       |
       +--> Deserialize payload
       +--> Kiểm tra kiểu event / dữ liệu đầu vào
       +--> Thực thi logic
       +--> Ghi metric/log hoặc xử lý exception
```

Mỗi bước có ranh giới trách nhiệm riêng:

| Bước | Thành phần | Điều không nên giả định |
|---|---|---|
| Publish | `RedisTemplate.convertAndSend` | Trả thành công không có nghĩa người nhận đã xử lý nghiệp vụ |
| Redis dispatch | Redis Pub/Sub | Không tự lưu message để gửi lại khi subscriber offline |
| Network/subscription | Redis client | Ngắt kết nối có thể gây khoảng trống mất message |
| Container | `RedisMessageListenerContainer` | Không có ACK/replay được tạo ra chỉ vì container quản lý subscription |
| Executor | Thread pool thực thi callback | Không tự bảo đảm thứ tự hoàn thành khi có nhiều worker thread |
| Listener | `onMessage` | Throw exception không tự rollback publisher và không khiến Redis redeliver |
| Business side effect | DB/cache/API bên ngoài | Có thể có lỗi hoặc thay đổi một phần dù callback đã được gọi |

Vì vậy, cần trả lời **ba câu hỏi riêng**: message có đến listener không, listener xử lý theo thứ tự nào, và điều gì xảy ra nếu listener thất bại?

## 3. Tạo publisher với `StringRedisTemplate`

Ví dụ sử dụng message JSON đơn giản. Ứng dụng Spring Boot cần dependency tương thích, chẳng hạn:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-json'
}
```

`spring-boot-starter-json` là ví dụ cho những phiên bản Boot có starter này; nếu ứng dụng đã có Jackson qua các starter khác, không cần khai báo trùng. Các API minh họa dựa trên Spring Data Redis thông thường; chọn dependency và serializer phù hợp phiên bản đang dùng.

Cấu hình Redis ví dụ:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Một kiểu event có thể dùng chung giữa publisher và listener:

```java
package com.example.catalog.events;

public record CatalogEvent(
    String eventId,
    String type,
    String productId
) {
}
```

Publisher:

```java
package com.example.catalog.events;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class CatalogEventPublisher {

    public static final String CHANNEL = "catalog.events";

    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper;

    public CatalogEventPublisher(
        StringRedisTemplate redis,
        ObjectMapper objectMapper
    ) {
        this.redis = redis;
        this.objectMapper = objectMapper;
    }

    public long publish(CatalogEvent event) {
        try {
            String json = objectMapper.writeValueAsString(event);

            Long count = redis.convertAndSend(CHANNEL, json);
            return count == null ? 0 : count;
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                "Không thể serialize CatalogEvent", ex
            );
        }
    }
}
```

Cách gọi:

```java
long subscribers = publisher.publish(
    new CatalogEvent(
        "evt-101",
        "PRODUCT_UPDATED",
        "p-42"
    )
);
```

`convertAndSend` chuyển message theo serializer của template và gửi `PUBLISH`. Với `StringRedisTemplate`, channel/payload chuỗi dùng serialization dạng String phù hợp với ví dụ này.

**Giá trị trả về không phải số listener đã xử lý thành công.** Phản hồi từ lệnh Redis `PUBLISH` phản ánh số subscription client nhận được ở phía Redis theo ngữ nghĩa của Redis, không chờ `onMessage` hoàn thành và không xác nhận các side effect phía ứng dụng.

Ngay cả khi giá trị trả về lớn hơn 0, listener vẫn có thể lỗi parse JSON, bị timeout khi gọi DB hoặc tiến trình bị dừng ngay sau khi nhận message. Không dùng kết quả `publish` để khẳng định công việc nghiệp vụ đã hoàn tất.

## 4. Viết `MessageListener` nhận dữ liệu dạng byte

`MessageListener` cung cấp callback:

```java
void onMessage(Message message, byte[] pattern);
```

`Message` của Spring Data Redis chứa phần thân message và channel ở dạng byte. Khi dùng String serializer ở publisher, có thể chuyển payload sang chuỗi UTF-8 ở listener.

Ví dụ:

```java
package com.example.catalog.events;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class CatalogEventListener implements MessageListener {

    private static final Logger log =
            LoggerFactory.getLogger(CatalogEventListener.class);

    private final ObjectMapper objectMapper;
    private final CatalogEventHandler eventHandler;

    public CatalogEventListener(
        ObjectMapper objectMapper,
        CatalogEventHandler eventHandler
    ) {
        this.objectMapper = objectMapper;
        this.eventHandler = eventHandler;
    }

    @Override
    public void onMessage(Message message, byte[] pattern) {
        String channel = new String(
            message.getChannel(),
            StandardCharsets.UTF_8
        );

        String payload = new String(
            message.getBody(),
            StandardCharsets.UTF_8
        );

        try {
            CatalogEvent event =
                    objectMapper.readValue(payload, CatalogEvent.class);

            if (event.eventId() == null
                    || event.eventId().isBlank()
                    || event.productId() == null
                    || event.productId().isBlank()) {
                throw new IllegalArgumentException(
                    "Thiếu eventId hoặc productId"
                );
            }

            eventHandler.handle(event);

            log.debug(
                "Processed Pub/Sub eventId={} channel={}",
                event.eventId(),
                channel
            );
        } catch (JsonProcessingException ex) {
            // Lỗi payload được biến thành exception để container
            // chuyển cho ErrorHandler. Redis không tự retry.
            throw new IllegalArgumentException(
                "Payload Pub/Sub không hợp lệ trên " + channel,
                ex
            );
        }
    }
}
```

Thành phần xử lý nghiệp vụ:

```java
package com.example.catalog.events;

public interface CatalogEventHandler {
    void handle(CatalogEvent event);
}
```

Ví dụ một implementation làm mất hiệu lực cache:

```java
package com.example.catalog.events;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;

@Component
public class ProductCacheEventHandler implements CatalogEventHandler {

    private final CacheManager cacheManager;

    public ProductCacheEventHandler(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @Override
    public void handle(CatalogEvent event) {
        if (!"PRODUCT_UPDATED".equals(event.type())) {
            return;
        }

        Cache cache = cacheManager.getCache("products");
        if (cache == null) {
            throw new IllegalStateException(
                "Cache 'products' chưa được cấu hình"
            );
        }

        cache.evict(event.productId());
    }
}
```

Ví dụ handler giả định key trong cache `products` chính là `productId`; nếu thực tế dùng SpEL key chứa tenant, locale hoặc key khác, listener phải tạo đúng key như phương thức được cache.

### 4.1. Vai trò của `pattern`

Tham số `pattern` trong `onMessage(message, pattern)` biểu thị thông tin liên quan đến **pattern subscription** khi listener đăng ký qua một pattern. Nếu dùng direct channel subscription, tham số này không nên được mặc định coi là một chuỗi pattern có giá trị.

Để xác định channel thực tế mà publisher đã gửi tới, dùng:

```java
message.getChannel()
```

Đối với `PatternTopic("catalog.*")`, listener có thể nhận message từ `catalog.events`, `catalog.refresh` và các channel khác khớp pattern. Không lấy `pattern` thay thế cho channel thực tế nếu nghiệp vụ phụ thuộc nguồn phát cụ thể.

### 4.2. Serializer của publisher và listener phải tương thích

Trong ví dụ trên, publisher gửi JSON chuỗi qua `StringRedisTemplate`, listener đọc body bằng UTF-8 và `ObjectMapper`.

Nếu publisher dùng JDK serialization, một codec nhị phân hoặc serializer có type metadata khác, listener không thể mặc định:

```java
new String(message.getBody(), StandardCharsets.UTF_8)
```

là payload JSON hợp lệ. Các service cần thống nhất **event schema, encoding, version và serialization contract**.

## 5. Cấu hình `RedisMessageListenerContainer`

Để listener thực sự nhận message, cần đăng ký nó với Redis channel hoặc pattern. `RedisMessageListenerContainer` quản lý kết nối subscribe và phân phối message đến các listener được đăng ký.

Ví dụ cấu hình có hai executor riêng:

```java
package com.example.catalog.events;

import java.util.concurrent.Executor;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class CatalogPubSubConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(CatalogPubSubConfiguration.class);

    @Bean("pubSubDispatchExecutor")
    public ThreadPoolTaskExecutor pubSubDispatchExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        // Một thread cho callback nếu muốn tuần tự hóa
        // quá trình dispatch của container này.
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(1000);
        executor.setThreadNamePrefix("redis-pubsub-handler-");
        executor.initialize();

        return executor;
    }

    @Bean("pubSubSubscriptionExecutor")
    public ThreadPoolTaskExecutor pubSubSubscriptionExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        // Task quản lý subscription có thể sống lâu.
        // Không dùng chung worker duy nhất với callback chậm.
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(0);
        executor.setThreadNamePrefix("redis-pubsub-subscription-");
        executor.initialize();

        return executor;
    }

    @Bean
    public RedisMessageListenerContainer redisMessageListenerContainer(
        RedisConnectionFactory connectionFactory,
        CatalogEventListener listener,
        @Qualifier("pubSubDispatchExecutor") Executor dispatchExecutor,
        @Qualifier("pubSubSubscriptionExecutor") Executor subscriptionExecutor
    ) {
        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setTaskExecutor(dispatchExecutor);
        container.setSubscriptionExecutor(subscriptionExecutor);

        container.addMessageListener(
            listener,
            new ChannelTopic(CatalogEventPublisher.CHANNEL)
        );

        container.setErrorHandler(ex ->
            log.error("Error in Redis Pub/Sub listener", ex)
        );

        return container;
    }
}
```

Đây là một cấu hình minh họa, không phải định mức thread/queue khuyên dùng cho mọi deployment. Trước khi chọn `queueCapacity` và kích thước pool, phải đánh giá throughput, thời gian xử lý listener, memory budget và cách xử lý khi executor hết chỗ.

Vai trò của hai executor:

| Thành phần | Vai trò |
|---|---|
| `setSubscriptionExecutor(...)` | Chạy các công việc liên quan đến subscription có thể chiếm một thread trong thời gian dài |
| `setTaskExecutor(...)` | Dispatch việc gọi listener, có thể thực thi callback bất đồng bộ |
| `ChannelTopic` | Đăng ký một channel chính xác |
| `PatternTopic` | Đăng ký một pattern nhiều channel |
| `setErrorHandler(...)` | Nhận thông báo exception từ cơ chế xử lý listener/container theo hợp đồng của Spring |
| `RedisConnectionFactory` | Tạo kết nối Redis theo cấu hình ứng dụng |

Không dùng một executor duy nhất với chỉ một thread cho **cả subscription và listener processing** nếu điều đó khiến task subscription chiếm hết worker và callback không thể chạy. Việc tách executor giúp làm rõ công việc duy trì subscription và công việc xử lý message.

### 5.1. Channel và pattern subscription

Đăng ký theo tên chính xác:

```java
container.addMessageListener(
    listener,
    new ChannelTopic("catalog.events")
);
```

Đăng ký bằng pattern:

```java
import org.springframework.data.redis.listener.PatternTopic;

container.addMessageListener(
    listener,
    new PatternTopic("catalog.*")
);
```

Pattern subscription giúp nhận message từ nhiều channel tương ứng với biểu thức glob của Redis. Ví dụ `catalog.*` có thể khớp `catalog.events` và `catalog.refresh`.

**Chú ý trùng nhận:** nếu một Redis client đồng thời subscribe channel trực tiếp và một hoặc nhiều pattern khớp cùng message, Redis Pub/Sub có thể tạo nhiều thông báo tương ứng với các subscription. Đừng mặc định một lần `PUBLISH` luôn dẫn đến đúng một lần callback theo mọi sơ đồ đăng ký.

Khi handler có side effect không thể chạy hai lần, cần xem xét topology subscription, cách định tuyến và cơ chế idempotency, thay vì chỉ dựa vào tên channel.

## 6. Thứ tự thông điệp: phải phân biệt nhiều tầng

Câu hỏi “Redis Pub/Sub có bảo đảm thứ tự không?” quá chung chung. Cần phân biệt:

1. **Thứ tự lệnh `PUBLISH` được Redis xử lý.**
2. **Thứ tự message được đưa tới một subscription connection.**
3. **Thứ tự callback được executor bắt đầu thực thi.**
4. **Thứ tự tác vụ nghiệp vụ thực sự hoàn thành.**
5. **Thứ tự trạng thái cuối cùng của database/cache sau nhiều subscriber.**

Các tầng này không đồng nghĩa.

### 6.1. Thứ tự tại Redis server và subscription connection

Một Redis server xử lý các lệnh theo trật tự thực thi của mình. Khi publisher gửi liên tiếp:

```redis
PUBLISH catalog.events "A"
PUBLISH catalog.events "B"
PUBLISH catalog.events "C"
```

trên một kết nối với các lệnh tuần tự, Redis xử lý các `PUBLISH` theo thứ tự đó và phát message theo thứ tự tương ứng cho subscription đang nhận.

Tuy nhiên, với **nhiều publisher độc lập**, không có thứ tự nghiệp vụ toàn cục tự suy ra từ thời gian Java bắt đầu gọi:

```text
Publisher 1 định gửi A lúc 10:00:00
Publisher 2 định gửi B lúc 10:00:00
```

Thứ tự thực tế mà Redis xử lý các lệnh phụ thuộc thứ tự chúng đến server. “Timestamp trong payload” cũng không phải chứng cứ tuyệt đối về thứ tự thực thi khi các máy có đồng hồ, mạng hoặc cơ chế retry khác nhau.

### 6.2. Thứ tự hoàn thành trong Spring có thể khác thứ tự nhận

Giả sử container nhận message theo thứ tự `A`, `B`, `C` nhưng task executor có ba worker:

```text
Redis đưa message đến container: A  ->  B  ->  C

Executor:
    Thread 1: xử lý A (mất 300 ms)
    Thread 2: xử lý B (mất  20 ms)
    Thread 3: xử lý C (mất  50 ms)

Thứ tự hoàn thành nghiệp vụ: B -> C -> A
```

Đây không phải lỗi Redis tự đảo thứ tự message. Nó là hệ quả **xử lý song song trong ứng dụng**.

Nếu mỗi event cập nhật cùng một aggregate và phụ thuộc vào event trước, việc để nhiều listener cùng sửa trạng thái có thể làm dữ liệu cuối cùng phản ánh thứ tự hoàn thành chứ không phải thứ tự phát.

Ví dụ:

```text
Event A: product p-42 status = DRAFT
Event B: product p-42 status = PUBLISHED

A bắt đầu trước nhưng chạy chậm.
B ghi PUBLISHED trước.
A ghi DRAFT sau.

Trạng thái cuối: DRAFT (cũ), dù B là event mới hơn.
```

Cần thiết kế sao cho xử lý **không phụ thuộc thứ tự hoàn thành**, hoặc áp dụng một cơ chế serialize/version khi yêu cầu nghiệp vụ cần có thứ tự.

### 6.3. Executor một thread giúp đến mức nào?

Với:

```java
dispatchExecutor.setCorePoolSize(1);
dispatchExecutor.setMaxPoolSize(1);
```

callback được đưa vào một hàng đợi để chạy tuần tự trên **executor này**, qua đó tránh hai callback trên executor ấy cùng thực thi song song.

Tuy nhiên:

- Điều này chỉ điều khiển các task được gửi vào executor đó **trong một JVM/instance**, không đồng bộ các subscriber ở những JVM khác.
- Thứ tự callback phụ thuộc thứ tự container submit task vào executor. Không nên coi đây là giao thức thứ tự bền vững khi có reconnect, failover hoặc nhiều nguồn message.
- Nếu listener lại tạo `CompletableFuture`, giao việc cho executor khác hoặc gửi yêu cầu HTTP bất đồng bộ rồi trả về ngay, thứ tự **hoàn thành side effect** vẫn có thể khác.
- Một task chậm chặn mọi callback tiếp theo, làm queue tăng nhanh.
- Restart có thể mất message trong khoảng không subscribe; executor một thread không tạo replay.

**Một thread xử lý tuần tự là quyết định concurrency cục bộ**, không biến Redis Pub/Sub thành event log có ordering durable.

## 7. Thứ tự theo key hay thứ tự toàn cục?

Nhiều hệ thống không cần mọi event phải đi theo một thứ tự duy nhất. Thường chỉ cần bảo đảm những event liên quan **cùng một sản phẩm** không bị áp dụng sai thứ tự.

Ví dụ:

```text
p-42: updated v3
p-99: updated v8
p-42: updated v4
p-99: updated v9
```

Không nhất thiết `p-42` phải chờ xử lý toàn bộ `p-99`. Nhưng với `p-42`, cần đảm bảo không áp dụng `v3` sau `v4`.

Một thiết kế là gắn **version tăng đơn điệu** cho mỗi aggregate:

```java
public record CatalogEvent(
    String eventId,
    String type,
    String productId,
    long version
) {}
```

Handler chỉ áp dụng event khi version mới hợp lệ so với version đã xử lý. Ví dụ ý tưởng:

```text
Stored version for p-42 = 4
Received event version = 3
  -> bỏ qua event cũ

Received event version = 5
  -> cập nhật trạng thái và version nếu điều kiện hợp lệ
```

Bước “đọc version → so sánh → cập nhật” cũng phải có tính nguyên tử tại nơi lưu dữ liệu nếu nhiều thread/instance cùng xử lý, chẳng hạn optimistic locking của DB, Redis script/CAS phù hợp hoặc cơ chế giao dịch tương ứng.

**Version chỉ có ích nếu publisher/nguồn dữ liệu định nghĩa version đúng.** Tự sinh `System.currentTimeMillis()` trong các publisher khác nhau không tự tạo ra một version toàn cục đáng tin cậy.

Với Pub/Sub, một version cao hơn có thể đến khi một số version thấp đã bị mất. Khi nghiệp vụ cần xử lý **đủ tất cả event theo thứ tự**, kiểm tra version không thay thế được message log bền vững.

## 8. Listener exception: điều gì thực sự xảy ra?

Xét:

```java
@Override
public void onMessage(Message message, byte[] pattern) {
    CatalogEvent event = parse(message);
    externalService.call(event);  // có thể ném exception
}
```

Giả sử `externalService.call(...)` ném `RuntimeException`.

Cần tách hai việc:

1. **Đã nhận message từ Redis:** message đã đi tới listener theo luồng Pub/Sub.
2. **Xử lý nghiệp vụ thất bại:** code của listener chưa hoàn thành như mong muốn.

Redis Pub/Sub **không có protocol ACK** để biết listener thất bại rồi gửi lại. Ném exception từ `onMessage` không làm publisher quay lại trạng thái “chưa publish” và không tự tạo message redelivery.

Với `RedisMessageListenerContainer`, có thể cấu hình:

```java
container.setErrorHandler(ex ->
    log.error("Redis listener processing error", ex)
);
```

`ErrorHandler` là điểm thu nhận/ghi nhận lỗi trong cơ chế callback/container của Spring. **Nó không phải dead-letter queue, không phải retry policy, không phải transaction rollback và không phải hệ thống giám sát đầy đủ.**

Nếu ứng dụng không cấu hình handler riêng, hành vi logging và xử lý lỗi theo mặc định của container/framework có thể phụ thuộc phiên bản. Nên khai báo cách ghi nhận lỗi và metric rõ ràng cho production.

### 8.1. Phân loại lỗi trước khi quyết định xử lý

| Lỗi | Ví dụ | Cách cân nhắc |
|---|---|---|
| Payload lỗi định dạng | JSON thiếu dấu ngoặc, không parse được | Ghi nhận, cảnh báo producer/schema; không retry vô hạn |
| Payload sai hợp đồng | Thiếu `productId`, sai `type` | Reject theo policy, ghi metric; không coi là lỗi Redis |
| Lỗi nghiệp vụ không thể khắc phục bằng retry | Event vi phạm quy tắc dữ liệu | Ghi nhận, xử lý theo nghiệp vụ |
| Lỗi tạm thời từ DB/API | Timeout, service ngoài unavailable | Cần cơ chế retry có kiểm soát **ngoài** Pub/Sub nguyên bản |
| Mất kết nối Redis | Subscriber không nhận trong một giai đoạn | Khi reconnect, message đã phát trong lúc offline thường không được phát lại |
| JVM bị dừng | Message vừa được nhận nhưng handler chưa xử lý | Có thể mất xử lý; Pub/Sub không có ACK/replay |
| Executor quá tải | Queue đầy, task bị từ chối hoặc đẩy chậm | Cần kiểm soát backpressure, quan sát và thay đổi thiết kế |

Một lỗi parse không nên được retry hàng nghìn lần. Một lỗi tạm thời của database có thể đáng retry nhưng phải chọn **địa điểm lưu công việc cần retry**. Cố retry vô hạn ngay trong callback Pub/Sub có thể giữ worker rất lâu, làm những message khác xếp hàng.

## 9. Retry và dead-letter: tự thiết kế, không tự có

Giả sử listener gọi một API ngoài:

```text
Redis Pub/Sub -> onMessage -> external API
                                  |
                                  +-- timeout
```

Nếu chỉ viết:

```java
try {
    externalApi.send(event);
} catch (RuntimeException ex) {
    log.error("Failed", ex);
}
```

thì message đó **không được Redis tự gửi lại**. Nếu bỏ qua lỗi, ứng dụng cũng không có dữ liệu để replay.

### 9.1. Retry ngắn trong listener có giới hạn

Với nghiệp vụ cho phép bỏ qua khi thất bại và handler chạy nhanh, có thể retry rất ít lần cho lỗi tạm thời. Nhưng phải hiểu:

- Retry làm callback lâu hơn.
- Có thể gây trì hoãn cả queue khi dùng single-thread executor.
- Side effect có thể đã xảy ra dù client nhận timeout.
- Retry có thể tạo **tác động trùng lặp** nếu handler không idempotent.
- Khi JVM chết, trạng thái retry trong bộ nhớ bị mất.

Không nên dùng vòng lặp retry vô hạn hoặc `Thread.sleep()` dài trong listener nếu Redis phục vụ nhiều loại message cần độ trễ thấp.

### 9.2. Chuyển message sang hàng đợi bền vững

Nếu mỗi message phải được xử lý thành công hoặc cần replay, hãy **publish ngay từ nguồn sang hệ thống có lưu trữ**, chẳng hạn Redis Streams với consumer groups hoặc broker tương ứng:

```text
Producer
   |
   | XADD stream:catalog-events ...
   v
Redis Stream
   |
   | XREADGROUP / consumer group
   v
Worker
   |
   +-- Xử lý thành công -> XACK
   |
   +-- Xử lý lỗi       -> giữ pending / retry / dead-letter theo thiết kế
```

Redis Streams cũng không tự bảo đảm exactly-once side effect; consumer vẫn cần idempotency, xử lý pending entries, retry, poison message và giới hạn lưu trữ. Nhưng Streams có cơ sở để **lưu và đọc lại message**, khác biệt quan trọng so với Pub/Sub.

Nếu listener Pub/Sub nhận được message rồi mới `XADD` vào stream, vẫn có **khoảng hở trước khi `XADD`**: tiến trình có thể dừng sau khi nhận Pub/Sub mà chưa lưu vào stream. Muốn tránh khoảng hở đó, publisher hoặc nguồn sự kiện phải ghi vào kênh bền vững ngay từ đầu, hoặc dùng outbox phù hợp.

### 9.3. Dead-letter không xuất hiện chỉ từ `ErrorHandler`

Dead-letter queue là nơi ghi những message đã vượt giới hạn retry hoặc không thể xử lý, kèm metadata lỗi. Redis Pub/Sub nguyên bản không cung cấp điều đó tự động.

Nếu vẫn dùng Pub/Sub cho các thông báo không quan trọng nhưng muốn ghi nhận lỗi, có thể đưa bản payload lỗi vào một hệ thống logging/monitoring hoặc một stream riêng. Cách này **ghi nhận lỗi khi process còn sống**, không làm Pub/Sub trở thành bảo đảm phát và xử lý bền vững.

## 10. Idempotency: vì sao vẫn cần dù Pub/Sub thường không replay?

Pub/Sub không tự redeliver message thất bại, nhưng điều đó **không có nghĩa ứng dụng luôn chỉ xử lý một lần**.

Trùng lặp có thể đến từ:

- Publisher phát cùng event hai lần do retry sau timeout.
- Hai service cùng phát một thay đổi nghiệp vụ.
- Client subscribe cả channel chính xác lẫn pattern khớp.
- Ứng dụng có logic tự retry.
- Một message bị dùng lại trong hai pipeline nghiệp vụ.
- Chuyển sang Streams hoặc broker có replay sau này.

Ví dụ một event:

```json
{
  "eventId": "evt-101",
  "type": "PRODUCT_UPDATED",
  "productId": "p-42"
}
```

Nếu handler chỉ làm:

```java
cache.evict("p-42");
```

thì xử lý lại lần nữa thường không gây thay đổi nghiệp vụ nghiêm trọng. Đó là tác vụ **gần như idempotent** trong nhiều tình huống cache.

Ngược lại:

```java
paymentService.chargeCard(event);
```

xử lý hai lần có thể gây tác động nghiêm trọng. Không nên dùng Pub/Sub không ACK/replay làm cơ chế duy nhất cho một tác vụ bắt buộc thành công như charge payment.

### 10.1. Đánh dấu event đã xử lý không đơn giản chỉ là `SETNX`

Một mẫu thường gặp là:

```redis
SET processed:evt-101 1 NX EX 3600
```

Điều này có thể giúp **chặn nhiều worker bắt đầu xử lý cùng event**, nhưng không tự tạo bảo đảm exactly-once.

Hai tình huống:

1. Đánh dấu **trước** khi làm side effect: nếu đánh dấu thành công rồi process chết, event bị xem là đã xử lý dù side effect chưa hoàn tất.
2. Đánh dấu **sau** side effect: nếu side effect đã thực hiện nhưng process chết trước khi đánh dấu, lần retry có thể chạy side effect lần nữa.

Với nghiệp vụ cần bảo đảm mạnh, cần đặt **kiểm tra event ID và cập nhật trạng thái nghiệp vụ trong cùng một transaction nguyên tử** tại nơi lưu dữ liệu, hoặc dùng cơ chế idempotency của hệ thống đích. Một Redis key phụ trợ không tự tạo transaction nguyên tử với PostgreSQL, thanh toán hoặc external API.

## 11. Khi callback chậm: executor, queue và backpressure

`RedisMessageListenerContainer` có thể dispatch listener qua task executor. Với một executor nhiều thread, có thể tăng khả năng xử lý đồng thời nhưng làm thứ tự hoàn thành khó dự đoán.

Với một executor một thread, ta dễ hiểu thứ tự callback cục bộ hơn, nhưng một callback chậm sẽ trì hoãn tất cả message phía sau:

```text
Message A: HTTP call mất 4 giây
Message B: chỉ cần xóa cache 2 ms
Message C: chỉ cần xóa cache 2 ms

Một thread:
A [---------------- 4 giây ----------------]
                                               B [2 ms]
                                                     C [2 ms]
```

Nếu publisher phát nhanh hơn tốc độ handler xử lý:

```text
Publish rate: 1.000 messages/giây
Handle rate:    100 messages/giây

Mỗi giây có thêm khoảng 900 nhiệm vụ tồn đọng
(nếu queue tiếp tục nhận mà không có giới hạn phù hợp).
```

Đó là vấn đề **backpressure**. Redis Pub/Sub không tự làm chậm publisher theo tốc độ xử lý business listener. Các queue ở client, executor và buffer phía Redis có thể tăng hoặc kết nối bị ảnh hưởng khi subscriber chậm.

Cấu hình:

```java
executor.setQueueCapacity(1000);
```

giới hạn queue của executor ứng dụng, nhưng **không có nghĩa message vượt giới hạn được Redis lưu để gửi lại**. Khi queue đầy, việc từ chối task và hành vi xử lý lỗi phụ thuộc executor/container và chính sách ứng dụng; cần quan sát và không coi đó là một chiến lược retry an toàn.

### 11.1. Các hướng giảm ảnh hưởng của listener chậm

- Giữ callback ngắn, tránh gọi dịch vụ ngoài có timeout rất dài.
- Đối với thông báo vô hiệu cache, thực hiện thao tác tối thiểu và chấp nhận tái tạo từ nguồn khi cần.
- Định nghĩa timeout rõ cho những thao tác I/O trong handler.
- Phân chia workload độc lập theo channel/container/executor khi phù hợp, thay vì để một handler nặng giữ queue của mọi listener.
- Dùng thread pool có giới hạn, queue có giới hạn và metric quan sát độ dài queue.
- Xem xét batch/coalescing với những sự kiện có thể gộp, ví dụ nhiều `PRODUCT_UPDATED` cho cùng ID có thể chỉ cần một lần invalidation.
- Khi backlog không được phép mất, chuyển sang kiến trúc có hàng đợi bền vững và ACK/retry.

**Không coi việc tăng số thread là giải pháp chung:** nó có thể tăng throughput nhưng vẫn gây quá tải DB, gây mất thứ tự nghiệp vụ hoặc làm tăng số request đồng thời đến hệ thống phụ thuộc.

## 12. Reconnect và khoảng trống mất message

`RedisMessageListenerContainer` có thể quản lý vòng đời subscription và cố khôi phục sau những loại lỗi kết nối theo cơ chế của Spring Data Redis/driver. Điều này hỗ trợ hệ thống tiếp tục **nhận message mới** sau khi kết nối phục hồi.

Nhưng cần phân biệt:

```text
t0: Subscriber kết nối và subscribe
t1: Nhận message A
t2: Mất kết nối
t3: Publisher phát message B
t4: Publisher phát message C
t5: Subscriber kết nối và subscribe lại
t6: Nhận message D
```

Với Redis Pub/Sub thông thường, **B và C không được Redis phát lại** chỉ vì subscriber đã reconnect tại `t5`.

Một số điều cần cân nhắc:

- Redis failover có thể làm kết nối subscribe gián đoạn.
- Client có thể timeout hoặc mất mạng mà publisher vẫn hoạt động.
- Container chỉ hoạt động khi ứng dụng khởi động và hoàn tất subscription.
- Trong rolling deployment, instance cũ dừng trước khi instance mới subscribe có thể tạo khoảng trống nhận sự kiện.
- Message đã dispatch nhưng chưa hoàn thành xử lý cũng có thể mất khi JVM bị dừng.
- Nếu cùng channel có nhiều instance đang subscribe, instance còn sống vẫn có thể nhận event trong lúc instance khác offline; tuy nhiên state cục bộ của instance offline không tự được cập nhật khi nó khởi động lại.

Do đó, với các sự kiện chỉ dùng để **invalidation cache cục bộ**, nên bổ sung TTL, version hoặc cơ chế đồng bộ lại từ nguồn. Không dựa hoàn toàn vào Pub/Sub để duy trì tính mới vĩnh viễn của cache qua restart và failover.

### 12.1. Startup và shutdown

Một listener container được Spring quản lý thông thường tham gia lifecycle của application context: khởi tạo, subscribe và dừng khi context đóng.

Vấn đề thực tế không chỉ là “container bean đã tồn tại”, mà là “subscription đã sẵn sàng trước khi publisher bắt đầu gửi những event quan trọng hay chưa”. Pub/Sub không có lịch sử để subscriber đọc lại lúc startup.

Nếu sự kiện trước khi listener sẵn sàng phải được xử lý, hãy đặt chúng vào một nguồn bền vững thay vì chỉ chờ container kết nối.

Khi shutdown, cho phép task đang chạy hoàn tất có thể giảm mất xử lý, nhưng không thể thay thế ACK/durable queue. Một process bị kill hoặc node mất điện không có cơ hội graceful shutdown.

## 13. Nhiều listener và nhiều ứng dụng cùng subscribe

Giả sử có hai ứng dụng:

```text
catalog.events
   |
   +-- App A instance 1
   +-- App A instance 2
   +-- App B instance 1
```

Nếu cả ba đều có subscription hợp lệ, Redis Pub/Sub theo mô hình broadcast: mỗi subscriber đang kết nối có thể nhận message, không phải một message được gán riêng cho một instance.

Điều này hữu ích khi:

- Mỗi instance có **cache cục bộ** cần invalidation.
- Nhiều dịch vụ quan sát cùng sự kiện để cập nhật trạng thái riêng không bắt buộc.
- UI/WebSocket gateway dùng Pub/Sub để chuyển tiếp thông báo realtime đến client đang kết nối.

Nhưng nếu nhiệm vụ là:

```text
“Chỉ một worker trong toàn cụm xử lý đơn hàng này”
```

thì Redis Pub/Sub **không tự cung cấp cơ chế cạnh tranh nhận message theo nhóm consumer**. Dùng Redis Streams consumer groups hoặc hàng đợi công việc tương ứng.

### 13.1. Tăng số instance không bảo đảm tăng throughput xử lý cùng một message

Vì mỗi instance subscribe channel đều nhận thông báo, tăng từ 2 lên 20 instance có thể khiến cùng một sự kiện được xử lý 20 lần. Với invalidation cache cục bộ, điều đó là mong muốn. Với thao tác ghi vào cùng một database, điều đó có thể là sai thiết kế.

Cần xác định mỗi listener làm side effect **theo instance**, **theo service**, hay **chỉ một lần toàn hệ thống**.

## 14. Cập nhật DB rồi publish: vấn đề dual write

Giả sử service xử lý thay đổi sản phẩm:

```java
@Transactional
public void changeProduct(String id, String name) {
    productRepository.updateName(id, name);
    publisher.publish(
        new CatalogEvent("evt-201", "PRODUCT_UPDATED", id)
    );
}
```

Nếu transaction DB chưa commit nhưng message Pub/Sub đã phát, listener khác có thể truy vấn DB và thấy dữ liệu cũ. Nếu transaction DB rollback, message đã publish **không tự bị hoàn tác**.

Đây là một dạng **dual write** giữa database và Redis.

### 14.1. Publish sau commit

Một cách cải thiện là phát sự kiện nội bộ và lắng nghe sau commit:

```java
public record ProductChanged(
    String eventId,
    String productId
) {
}
```

Service:

```java
@Service
public class ProductWriteService {

    private final ProductRepository repository;
    private final ApplicationEventPublisher events;

    public ProductWriteService(
        ProductRepository repository,
        ApplicationEventPublisher events
    ) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void rename(String id, String newName) {
        repository.updateName(id, newName);

        events.publishEvent(
            new ProductChanged("evt-201", id)
        );
    }
}
```

Listener sau commit:

```java
@Component
public class PublishAfterCommit {

    private final CatalogEventPublisher publisher;

    public PublishAfterCommit(CatalogEventPublisher publisher) {
        this.publisher = publisher;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onProductChanged(ProductChanged event) {
        publisher.publish(
            new CatalogEvent(
                event.eventId(),
                "PRODUCT_UPDATED",
                event.productId()
            )
        );
    }
}
```

Các class như `ProductRepository`, `ApplicationEventPublisher`, `@Transactional`, `@TransactionalEventListener` và `TransactionPhase` thuộc tầng ứng dụng/Spring tương ứng; ứng dụng thực tế cần import và cung cấp implementation.

Hướng này tránh phát thông báo trước khi DB commit thành công. Nhưng nó **không bảo đảm sự kiện chắc chắn được publish**: JVM có thể dừng ngay sau commit DB và trước khi callback `AFTER_COMMIT` gửi message.

### 14.2. Khi cần chắc chắn phát sự kiện

Nếu “đã cập nhật DB thì cuối cùng listener bắt buộc phải biết” là một yêu cầu quan trọng, nên cân nhắc:

1. Lưu bản ghi **outbox** trong cùng transaction database với thay đổi nghiệp vụ.
2. Một worker đọc outbox và gửi đến kênh sự kiện **có lưu trữ** phù hợp.
3. Consumer xử lý idempotently và ACK/ghi checkpoint theo cơ chế transport.
4. Retry theo giới hạn, theo dõi backlog và xử lý poison messages.
5. Xóa/đánh dấu outbox sau khi đã đạt điều kiện publish an toàn theo thiết kế.

Nếu outbox worker chỉ publish sang Pub/Sub, vẫn có thể mất message tại subscriber offline. Do đó **outbox + Pub/Sub** giúp tránh một số khoảng hở ở phía producer nhưng **không nâng Pub/Sub thành hàng đợi bền vững ở phía consumer**.

## 15. Lỗi listener và tính nhất quán của cache

Một use case Pub/Sub thường gặp trong Spring Data Redis là **thông báo xóa cache** khi dữ liệu nguồn thay đổi.

Ví dụ:

```text
ProductService cập nhật PostgreSQL
   |
   v
Publish PRODUCT_UPDATED:p-42
   |
   v
Các application instance đang subscribe
   |
   v
Mỗi instance xóa local cache của p-42
```

Nếu một instance không nhận sự kiện do reconnect hoặc listener lỗi, nó có thể giữ giá trị cache cũ. Những biện pháp giảm rủi ro gồm:

- Đặt TTL giới hạn thời gian sống của cache cục bộ.
- Sử dụng version của đối tượng để xác minh tính mới khi cần.
- Làm invalidation idempotent.
- Đồng bộ/clear cache khi instance khởi động lại nếu hợp lý.
- Theo dõi dấu hiệu invalidation thất bại.
- Với dữ liệu cần nhất quán mạnh, đọc lại nguồn sự thật thay vì chỉ tin vào notification.

**Pub/Sub là một tín hiệu**, không phải bằng chứng rằng mọi bản sao cache trong hệ thống đã được cập nhật.

### 15.1. Invalidation và thứ tự đôi khi không cần ràng buộc chặt

Nếu mọi event `PRODUCT_UPDATED` cho cùng ID đều chỉ gọi `cache.evict(id)`, xử lý event B trước A thường vẫn có tác dụng xóa cùng key, không áp dụng dữ liệu cũ vào cache.

Tuy nhiên, cần xem race với **cache refill**:

```text
Listener A xóa cache
Request khác nạp dữ liệu cũ từ replica chậm
Listener B xóa cache
Request kế tiếp nạp dữ liệu mới
```

Với yêu cầu tính mới chặt, vẫn cần hiểu transaction commit, replica lag và cache-aside race. Một handler chỉ làm evict thường ít phụ thuộc thứ tự hơn handler áp dụng trạng thái cụ thể từ payload.

## 16. Quan sát lỗi và độ trễ listener

Pub/Sub không có pending queue như Redis Streams, nên không thể chỉ hỏi Redis “còn bao nhiêu message chưa ACK?” để biết sức khỏe xử lý.

Các metric nên theo dõi ở phía ứng dụng:

| Metric | Mục tiêu |
|---|---|
| `pubsub.publish.total` | Số lần ứng dụng phát sự kiện |
| `pubsub.publish.error` | Lỗi phát từ publisher |
| `pubsub.receive.total` | Số message đến listener |
| `pubsub.decode.error` | Payload sai schema/encoding |
| `pubsub.handler.success` | Callback xử lý thành công |
| `pubsub.handler.error` | Callback ném lỗi nghiệp vụ |
| `pubsub.handler.duration` | p50/p95/p99 thời gian xử lý |
| `pubsub.dispatch.queue.size` | Số task còn chờ trong executor |
| `pubsub.subscription.reconnect` | Dấu hiệu subscription bị gián đoạn/khôi phục |
| `pubsub.event.age` | Chênh lệch thời điểm event và thời điểm xử lý, nếu có timestamp đáng tin |
| `pubsub.duplicate.detected` | Event ID bị phát/nhận trùng theo cơ chế kiểm tra của ứng dụng |

Để đo listener duration:

```java
long started = System.nanoTime();

try {
    handler.handle(event);
    // Tăng metric success.
} catch (RuntimeException ex) {
    // Tăng metric error và ghi ngữ cảnh.
    throw ex;
} finally {
    long elapsed = System.nanoTime() - started;
    // Đưa elapsed vào histogram/Timer.
}
```

Trong production, dùng Micrometer/OpenTelemetry hoặc hệ thống monitoring tương ứng; không log toàn bộ payload ở mọi message vì dễ tăng chi phí I/O và lộ dữ liệu nhạy cảm.

Các nhãn metric nên có cardinality thấp, như `channel`, `eventType`, `result`, không dùng `eventId` làm nhãn vì nó có thể tạo một time series mới cho mỗi message.

### 16.1. Không đồng nhất “đã nhận” với “đã xử lý”

Nên tách ít nhất hai counter:

```text
Received:   listener bắt đầu có message
Succeeded:  handler hoàn thành theo định nghĩa nghiệp vụ
```

Nếu `received` tăng nhưng `succeeded` không tăng và `handler.error` xuất hiện, đó là thất bại xử lý. Nhưng sự kiện **không được gửi đến** khi subscriber offline sẽ không làm `received` tăng; ứng dụng không thể đếm chính xác các message đã bỏ lỡ chỉ dựa vào metric bên trong listener.

Nếu cần kiểm tra không bỏ sót từng event, phải dùng một **nguồn sự kiện có thể đối chiếu** bên ngoài Pub/Sub, như event log/stream bền vững.

## 17. Kiểm tra hành vi bằng Redis CLI và Spring

Trong môi trường phát triển, có thể quan sát thông điệp trực tiếp qua Redis CLI:

Terminal A:

```redis
SUBSCRIBE catalog.events
```

Terminal B:

```redis
PUBLISH catalog.events "{\"eventId\":\"evt-301\",\"type\":\"PRODUCT_UPDATED\",\"productId\":\"p-42\"}"
```

Terminal A sẽ nhận message khi đã subscribe trước thời điểm publish.

Với ứng dụng Spring chạy listener container, có thể tạo cùng event qua `CatalogEventPublisher` để quan sát log của `onMessage`.

### 17.1. Quan sát thứ tự

Gửi ba message có sequence:

```redis
PUBLISH catalog.events "A"
PUBLISH catalog.events "B"
PUBLISH catalog.events "C"
```

Một subscriber CLI trực tiếp thường quan sát theo thứ tự Redis cung cấp. Ở ứng dụng Spring, muốn xem thứ tự xử lý thực tế, đặt log trước và sau business handler:

```text
START A
START B
END   B
END   A
```

Nếu có nhiều worker thread, thứ tự hoàn thành có thể khác thứ tự bắt đầu. Khi chuyển executor sang một thread và không tạo tác vụ bất đồng bộ khác, các callback trên executor đó chạy tuần tự hơn, nhưng vẫn phải xét mất message và nhiều instance.

### 17.2. Mô phỏng listener bị lỗi

Gửi payload không phải JSON:

```redis
PUBLISH catalog.events "this-is-not-json"
```

Ví dụ `CatalogEventListener` sẽ ném exception khi parse, và `ErrorHandler` được cấu hình có thể ghi lỗi. Khi publisher gửi một message hợp lệ sau đó, listener vẫn có thể tiếp tục xử lý theo cơ chế container.

Điều cần quan sát: message lỗi không tự quay lại Redis để chờ ACK; không có replay chỉ từ việc handler ném exception.

### 17.3. Mô phỏng mất kết nối

Nếu dừng subscriber rồi publish một message, sau đó khởi động subscriber lại, message đã phát trong khoảng subscriber offline không có trong một danh sách backlog Pub/Sub để đọc lại.

Thử nghiệm này minh họa giới hạn cốt lõi: **subscribe lại không đồng nghĩa khôi phục lịch sử**.

## 18. Các quyết định thiết kế theo yêu cầu

| Yêu cầu | Pub/Sub + listener có phù hợp? | Ghi chú |
|---|---|---|
| Thông báo realtime cho các client đang online | Thường phù hợp | Chấp nhận mất thông báo khi offline hoặc có cơ chế đồng bộ lại |
| Invalidation cache cục bộ giữa các instance | Thường phù hợp | Kết hợp TTL/version để chịu được mất sự kiện |
| Cập nhật dashboard không cần giữ lịch sử | Thường phù hợp | Dữ liệu gốc phải có cách tải lại |
| Một event gửi đến mọi subscriber hiện có | Phù hợp với mô hình broadcast | Không phải shared work queue |
| Chỉ một worker xử lý mỗi job | Không đủ | Cần consumer group/queue phù hợp |
| Xử lý đủ mọi event sau restart | Không đủ | Cần nguồn sự kiện bền vững và replay |
| Retry tự động khi handler thất bại | Không có sẵn | Dùng hệ thống retry lưu trạng thái hoặc chuyển transport |
| Đảm bảo thứ tự thực hiện nghiệp vụ trên nhiều JVM | Không đủ | Cần partition, version và phối hợp concurrency |
| Exactly-once external side effect | Không đủ | Cần idempotency/transaction ở hệ thống đích |
| Đảm bảo không mất update sau DB commit | Không đủ khi chỉ Pub/Sub | Cân nhắc outbox và delivery bền vững |
| Phát thông điệp rồi biết subscriber có xử lý thành công | Không có sẵn | Phải xây ACK/application protocol hoặc cơ chế hàng đợi thích hợp |

Một câu hỏi quan trọng trước khi chọn công nghệ: **“Nếu listener tắt trong 30 giây, mất hết message phát trong 30 giây ấy có chấp nhận được không?”** Nếu câu trả lời là không, Redis Pub/Sub thuần túy không phải nguồn sự kiện duy nhất phù hợp.

## 19. Những hiểu lầm thường gặp

**“`PUBLISH` trả số lớn hơn 0 là mọi listener đã xử lý xong.”** Sai. Phản hồi không phải business ACK.

**“Một service có hai instance thì Pub/Sub tự chia message cho từng instance.”** Sai. Các subscriber đang đăng ký đều có thể nhận message broadcast.

**“Redis gửi đúng thứ tự nên callback Java luôn hoàn thành đúng thứ tự.”** Sai. Executor và logic bất đồng bộ có thể đảo thứ tự hoàn thành.

**“Dùng một thread là bảo đảm thứ tự toàn cụm.”** Sai. Nó chỉ tuần tự hóa task trên executor cụ thể trong một JVM và không replay message.

**“Exception trong `onMessage` khiến Redis gửi lại message.”** Sai. Pub/Sub không có ACK/retry nguyên bản.

**“`setErrorHandler` là dead-letter/retry.”** Sai. Đây là điểm xử lý exception, không phải message queue.

**“Subscriber reconnect sẽ nhận các message đã bỏ lỡ.”** Sai. Pub/Sub không giữ lịch sử cho subscriber offline.

**“Có thể dùng `@Transactional` để rollback lệnh PUBLISH nếu DB transaction thất bại.”** Không thể mặc định. Redis Pub/Sub không tự tham gia transaction DB; publish sau commit cũng không tạo bảo đảm delivery bền vững.

**“Pub/Sub là cơ chế exactly-once vì Redis không lưu message.”** Sai. Message có thể bị mất, trùng do publisher hoặc subscription topology, và side effect không được Redis phối hợp transaction.

**“Đặt một queue rất lớn trong JVM giải quyết được mọi backlog.”** Sai. Queue lớn tiêu thụ memory, tăng latency và vẫn mất task khi process chết.

**“Payload có timestamp nên có thể áp dụng thứ tự tuyệt đối.”** Sai. Các publisher khác nhau có clock/network khác nhau; dùng sequence/version từ nguồn dữ liệu có quy tắc nhất quán nếu thứ tự quan trọng.

**“Thấy `onMessage` được gọi nghĩa là dữ liệu đã nhất quán.”** Sai. Handler có thể chưa commit side effect, hoặc sự kiện được phát trước khi nguồn dữ liệu commit.

## 20. Nguyên tắc triển khai listener đáng tin cậy

Với Pub/Sub phục vụ sự kiện tạm thời, một thiết kế Spring Data Redis nên theo các nguyên tắc:

1. **Định nghĩa hợp đồng event:** channel, kiểu message, encoding, schema version, event ID và những trường bắt buộc.
2. **Đăng ký subscription rõ ràng:** dùng `ChannelTopic` cho channel xác định, `PatternTopic` khi thật sự cần wildcard; chú ý message trùng khi đăng ký chồng lấp.
3. **Tách executor subscription và dispatch khi cần:** không để task dài chiếm toàn bộ thread callback.
4. **Chọn concurrency theo nhu cầu ordering:** nhiều thread tăng throughput nhưng có thể đảo thứ tự side effect; một thread chỉ cung cấp tuần tự hóa cục bộ.
5. **Giữ callback ngắn và có timeout:** tránh I/O không giới hạn hoặc retry vô hạn trong listener.
6. **Cấu hình `ErrorHandler`:** ghi nhận lỗi rõ ràng, nhưng không nhầm logging với retry.
7. **Làm side effect idempotent:** cân nhắc event ID, version và transaction tại nơi thay đổi dữ liệu.
8. **Thiết kế chịu mất message:** TTL, phiên bản cache, periodic reconciliation hoặc đọc lại nguồn sự thật.
9. **Không dùng Pub/Sub cho công việc bắt buộc replay:** chuyển tới Streams/queue bền vững hoặc outbox khi yêu cầu nghiệp vụ đòi hỏi.
10. **Quan sát production:** số nhận, số xử lý thành công/thất bại, latency handler, executor backlog, reconnect và các chênh lệch dữ liệu.

### 20.1. Mẫu nhận diện ranh giới trách nhiệm

Có thể hình dung hệ thống thành ba phần:

```text
Publisher
    |
    | Phát notification không bền vững
    v
Redis Pub/Sub
    |
    | Chỉ tới subscriber đang đăng ký
    v
Spring listener container
    |
    | Dispatch task, không có durable ACK
    v
Business handler
    |
    +-- Chấp nhận mất/thực hiện lại?
    |         |
    |         +-- Có: idempotent + TTL/reconciliation
    |
    +-- Không chấp nhận mất?
              |
              +-- Chuyển nguồn sự kiện sang
                  Stream/queue/outbox phù hợp
```

Đừng để một lựa chọn thuận tiện ở tầng framework khiến ứng dụng vô tình đặt **nghĩa vụ đảm bảo giao hàng và thứ tự** lên một cơ chế không cung cấp những bảo đảm đó.

## 21. Kết luận

Trong Spring Data Redis, `RedisMessageListenerContainer` quản lý subscription và chuyển message tới `MessageListener.onMessage(...)`. Redis Pub/Sub có khả năng truyền thông báo nhanh cho những subscriber đang kết nối, nhưng **không phải hàng đợi có lưu trữ và ACK**.

Ba ranh giới cốt lõi:

- **Luồng xử lý:** publisher → Redis → subscription connection → container → executor → listener → side effect; thành công ở bước trước không đồng nghĩa bước sau đã thành công.
- **Thứ tự:** Redis cung cấp thứ tự nhận trên kết nối phù hợp, nhưng concurrent executor, nhiều subscriber và xử lý bất đồng bộ có thể làm thứ tự hoàn thành khác; nếu trạng thái phụ thuộc thứ tự, dùng version và đồng bộ tại nơi cập nhật.
- **Xử lý lỗi:** exception của listener có thể được ghi nhận bởi `ErrorHandler`, nhưng **không tự retry/redeliver**; cần idempotency, cơ chế phục hồi và chọn transport bền vững nếu sự kiện quan trọng.

Pub/Sub phù hợp khi mục tiêu là **phát tín hiệu nhanh, chấp nhận subscriber offline và có cách tự đồng bộ lại**. Nếu nghiệp vụ bắt buộc xử lý đủ message, giữ trạng thái pending, retry sau lỗi hoặc replay sau restart, nên thiết kế quanh Redis Streams hoặc một hệ thống message broker có delivery semantics phù hợp ngay từ đầu.

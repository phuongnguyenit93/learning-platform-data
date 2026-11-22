# Nhận thông điệp bằng MessageListener và MessageListenerAdapter trong Spring Data Redis

## 1. Bối cảnh: Spring Boot nhận thông điệp Redis Pub/Sub

Redis Pub/Sub cho phép một ứng dụng **publisher** phát thông điệp lên một **channel**, và các ứng dụng **subscriber** đang đăng ký channel đó nhận dữ liệu gần như tức thời.

Ví dụ: một dịch vụ tạo đơn hàng phát `orders.created`, còn các dịch vụ hiển thị hoặc giám sát nhận thông tin.

~~~text
Order Service
     |
     | PUBLISH orders.created {"orderId":"o-101"}
     v
+------------------------+
| Redis Pub/Sub          |
| channel orders.created |
+-------------+----------+
              |
      +-------+-------------------+
      |                           |
      v                           v
Notification Service         Metrics Service
~~~

Spring Data Redis cung cấp hai cách phổ biến để viết mã nhận thông điệp:

- **`MessageListener`**: callback nhận thông điệp gốc, gồm bytes của payload, channel và thông tin pattern.
- **`MessageListenerAdapter`**: chuyển thông điệp đến method của một Java object thông thường sau bước giải mã bằng serializer.

Cả hai đều được đăng ký và quản lý qua **`RedisMessageListenerContainer`**. Container duy trì kết nối Pub/Sub và chuyển thông điệp tới callback.

> Redis Pub/Sub không lưu message để phát lại. Khi subscriber không kết nối lúc thông điệp được phát, thông điệp đó không nằm trong một hàng đợi chờ subscriber quay lại.

## 2. Những thành phần chính trong Spring Data Redis

| Thành phần | Trách nhiệm |
| --- | --- |
| `RedisTemplate.convertAndSend` | Publish payload lên channel |
| `StringRedisTemplate` | Thuận tiện khi channel/payload là String |
| `MessageListener` | Nhận raw `Message` qua `onMessage(...)` |
| `MessageListenerAdapter` | Giải mã payload rồi gọi method trên delegate object |
| `RedisMessageListenerContainer` | Quản lý subscribe, lifecycle và dispatch |
| `ChannelTopic` | Subscribe chính xác một channel |
| `PatternTopic` | Subscribe các channel khớp một glob pattern |
| `RedisSerializer` | Quy định cách bytes được chuyển thành Java value |

Luồng tương tác:

~~~text
Publisher: Java String / DTO
              |
              v
     Serializer tạo byte[]
              |
              v
        Redis PUBLISH
              |
              v
     Redis Pub/Sub channel
              |
              v
   RedisMessageListenerContainer
              |
        +-----+-----------------+
        |                       |
        v                       v
MessageListener        MessageListenerAdapter
onMessage(raw)         deserialize(payload)
        |                       |
        v                       v
Decode trong Java       Delegate.method(...)
~~~

**Listener quyết định xử lý message thế nào; container quyết định lắng nghe Redis bằng cách nào.** Sự phân chia này giúp tránh viết thủ công một connection `SUBSCRIBE` cho mỗi handler.

## 3. Thử Pub/Sub bằng redis-cli trước khi viết Java

Mở hai terminal, dùng Redis local hoặc môi trường thử nghiệm.

Terminal A đăng ký:

~~~bash
redis-cli SUBSCRIBE orders.created
~~~

Terminal B phát:

~~~bash
redis-cli PUBLISH orders.created '{"eventId":"e-101","orderId":"o-101"}'
~~~

Khi Terminal A đang subscribe, nó nhận message. Nếu dừng Terminal A rồi phát thêm một message, lần subscribe sau **không nhận lại** message đã phát trong lúc bị ngắt.

Một lệnh `PUBLISH` có thể trả số subscriber theo cách Redis tính người nhận, nhưng số này **không có nghĩa** handler Java đã xử lý xong nghiệp vụ hoặc ghi nhận thành công.

Đăng ký theo pattern:

~~~bash
redis-cli PSUBSCRIBE 'orders.*'
~~~

Pattern `orders.*` có thể khớp `orders.created`, `orders.cancelled` và `orders.paid`. Đây là wildcard theo quy tắc Redis Pub/Sub, không phải Java regular expression.

## 4. MessageListener: interface nhận thông điệp thô

Chữ ký của interface:

~~~java
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;

public interface MessageListener {
    void onMessage(Message message, byte[] pattern);
}
~~~

Những gì callback nhận:

- `message.getBody()`: `byte[]` của payload.
- `message.getChannel()`: `byte[]` của tên channel.
- `pattern`: thông tin pattern subscription nếu message đến qua đăng ký pattern; không nên mặc định có giá trị với exact channel subscription.

Spring không tự hiểu payload là UTF-8, JSON, Protobuf hay Java serialized object khi gọi raw listener. Chính listener hoặc decoder mà nó gọi phải biết contract.

### Ví dụ listener nhận String UTF-8

~~~java
package com.example.messaging;

import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class RawOrderListener implements MessageListener {

    private static final Logger log =
        LoggerFactory.getLogger(RawOrderListener.class);

    @Override
    public void onMessage(Message message, byte[] pattern) {
        String channel = new String(
            message.getChannel(), StandardCharsets.UTF_8
        );

        String body = new String(
            message.getBody(), StandardCharsets.UTF_8
        );

        log.info(
            "Redis Pub/Sub: channel={}, payload={}",
            channel, body
        );
    }
}
~~~

Ví dụ giả định publisher gửi String theo UTF-8. Trong môi trường thật, thay việc log payload bằng parse/validation và log metadata vì message có thể chứa dữ liệu nhạy cảm.

**Ưu điểm:** truy cập raw bytes, channel và pattern, nên phù hợp với router, giao thức nhị phân hoặc handler xử lý nhiều channel.

**Đổi lại:** phải tự xử lý serialization, validation, logging lỗi và việc phân tuyến.

## 5. RedisMessageListenerContainer: đăng ký listener với Redis

Chỉ tạo một class `implements MessageListener` chưa có nghĩa Spring sẽ tự subscribe Redis. Cần đăng ký nó vào container.

~~~java
package com.example.messaging;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class RawListenerConfig {

    @Bean
    RedisMessageListenerContainer rawListenerContainer(
            RedisConnectionFactory factory,
            RawOrderListener rawOrderListener) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(factory);

        container.addMessageListener(
            rawOrderListener,
            new ChannelTopic("orders.created")
        );

        return container;
    }
}
~~~

Container là bean do Spring quản lý. Khi ứng dụng chạy và container đã đăng ký, Redis có thể chuyển message của `orders.created` tới `RawOrderListener.onMessage(...)`.

~~~text
ApplicationContext start
          |
          v
Tạo container, gắn connection factory
          |
          v
Subscribe Redis channel
          |
          v
Nhận dữ liệu từ Redis
          |
          v
Dispatch đến listener
~~~

Không nên mở Redis subscription thủ công trong mỗi HTTP request hoặc tạo `RedisMessageListenerContainer` mới cho từng message. Đây là hạ tầng được tái sử dụng trong suốt vòng đời ứng dụng.

## 6. Publisher với StringRedisTemplate

Để thử listener:

~~~java
package com.example.messaging;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long publishOrderCreated(String json) {
        Long receivers = redis.convertAndSend(
            "orders.created",
            json
        );
        return receivers == null ? 0L : receivers;
    }
}
~~~

Ví dụ gọi:

~~~java
publisher.publishOrderCreated(
    "{\"eventId\":\"e-101\",\"orderId\":\"o-101\"}"
);
~~~

Vì dùng `StringRedisTemplate`, payload ở dạng String và decoder UTF-8 tại raw listener là tương thích với mô hình ví dụ.

Lưu ý quan trọng:

- Redis không xác minh event có schema đúng.
- Subscriber phải được đăng ký **trước khi publish** thì mới có cơ hội nhận.
- Giá trị `receivers` không xác nhận việc xử lý nghiệp vụ.
- Nếu Redis có ba instance subscriber, cùng một event có thể được nhận ở cả ba.

## 7. MessageListenerAdapter: gọi method của POJO

Không phải handler nào cũng cần raw `Message`. Với một channel có payload thống nhất, `MessageListenerAdapter` giúp nhận message qua method của một object Java bình thường.

Ví dụ receiver:

~~~java
package com.example.messaging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageReceiver {

    private static final Logger log =
        LoggerFactory.getLogger(OrderMessageReceiver.class);

    public void receiveMessage(String payload) {
        log.info("Received order event: {}", payload);
    }
}
~~~

Tạo adapter:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.listener.adapter.MessageListenerAdapter;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class OrderAdapterConfig {

    @Bean
    MessageListenerAdapter orderMessageAdapter(
            OrderMessageReceiver receiver) {

        MessageListenerAdapter adapter =
            new MessageListenerAdapter(
                receiver, "receiveMessage"
            );

        adapter.setSerializer(new StringRedisSerializer());
        return adapter;
    }
}
~~~

Adapter thực hiện:

~~~text
Message body byte[]
         |
         v
StringRedisSerializer.deserialize(...)
         |
         v
String payload
         |
         v
OrderMessageReceiver.receiveMessage(payload)
~~~

Delegate không phải implement `MessageListener`. Adapter đảm nhiệm lớp kết nối giữa Redis message và lời gọi method.

Nếu không chỉ định tên method khác, adapter có quy ước method mặc định `handleMessage`. Trong ví dụ này, đặt `"receiveMessage"` tường minh để contract dễ đọc.

### Vì sao cần setSerializer?

Publisher và subscriber phải dùng định dạng tương thích. Với payload văn bản UTF-8, `StringRedisSerializer` phù hợp. Nếu publisher ghi JSON theo một binary serializer hoặc Java serialization, dùng String serializer để đọc có thể cho kết quả sai hoặc gây lỗi.

**Adapter không tự suy ra serializer từ Redis.** Redis Pub/Sub chỉ vận chuyển bytes.

## 8. Đăng ký adapter vào RedisMessageListenerContainer

`MessageListenerAdapter` có thể đăng ký với container giống một `MessageListener`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.data.redis.listener.adapter.MessageListenerAdapter;

@Configuration
public class AdaptedListenerConfig {

    @Bean
    RedisMessageListenerContainer adaptedListenerContainer(
            RedisConnectionFactory factory,
            MessageListenerAdapter orderMessageAdapter) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(factory);

        container.addMessageListener(
            orderMessageAdapter,
            new ChannelTopic("orders.created")
        );

        return container;
    }
}
~~~

Đây là **phương án thay thế** cho raw listener ở phần trước. Nếu cùng ứng dụng bật cả hai cấu hình và cả hai subscribe `orders.created`, có thể cùng xử lý một thông điệp hai lần qua hai handler khác nhau.

Trong hệ thống thực tế, thường thuận tiện hơn khi tập trung đăng ký các listener và adapter vào một container chung.

## 9. MessageListener và MessageListenerAdapter: so sánh

| Tiêu chí | `MessageListener` | `MessageListenerAdapter` |
| --- | --- | --- |
| Handler | Implement interface | POJO method |
| Đầu vào | Raw `Message` và pattern | Payload đã giải mã |
| Kiểm soát bytes | Trực tiếp | Qua serializer của adapter |
| Biết channel | Lấy từ `getChannel()` | Phụ thuộc contract method/cấu hình |
| JSON/binary | Tự decode | Có thể deserialize trước khi gọi delegate |
| Lượng boilerplate | Nhiều hơn | Ít hơn |
| Routing nhiều topic | Linh hoạt | Phù hợp khi mỗi adapter có contract rõ |
| Phụ thuộc Redis API trong nghiệp vụ | Cao hơn | Thấp hơn |
| Lỗi thường gặp | Sai encoding, xử lý sai channel | Sai tên method, signature hoặc serializer |

**Chọn MessageListener** khi cần raw bytes/channel/pattern hoặc định tuyến nhiều loại message.

**Chọn MessageListenerAdapter** khi một loại message được xử lý bằng một Java method rõ ràng và serializer thống nhất.

Cả hai đều dùng chung giới hạn vận chuyển của Redis Pub/Sub; adapter không thay đổi độ tin cậy hay tạo replay.

## 10. ChannelTopic và PatternTopic

### Exact channel

~~~java
container.addMessageListener(
    listener,
    new ChannelTopic("orders.created")
);
~~~

`ChannelTopic` chỉ đăng ký tên channel xác định.

### Pattern subscription

~~~java
import org.springframework.data.redis.listener.PatternTopic;

container.addMessageListener(
    listener,
    new PatternTopic("orders.*")
);
~~~

`PatternTopic` dùng wildcard Redis để nhận nhiều channel khớp pattern. Ví dụ `orders.*` khớp `orders.created` hoặc `orders.cancelled`.

Một lỗi thường gặp là viết:

~~~java
new ChannelTopic("orders.*")
~~~

và kỳ vọng nhận mọi message bắt đầu bằng `orders.`. Đó là exact channel có dấu sao trong tên, không phải pattern subscription. Hãy dùng `PatternTopic`.

### Phân biệt channel và pattern trong raw listener

Khi subscribe `orders.*` mà publisher gửi `orders.created`:

~~~text
message.getChannel() = bytes("orders.created")
pattern              = bytes("orders.*")
~~~

Với exact channel subscription, pattern có thể không được cung cấp như trường hợp `PSUBSCRIBE`. Không nên viết code assume mọi callback đều có pattern.

Dùng `message.getChannel()` để biết chính xác event đã phát lên channel nào.

## 11. Một container quản lý nhiều listener

Một container có thể đăng ký nhiều loại handler:

~~~java
@Bean
RedisMessageListenerContainer listenerContainer(
        RedisConnectionFactory factory,
        MessageListenerAdapter createdAdapter,
        MessageListenerAdapter cancelledAdapter,
        MessageListener metricsListener) {

    RedisMessageListenerContainer container =
        new RedisMessageListenerContainer();

    container.setConnectionFactory(factory);

    container.addMessageListener(
        createdAdapter,
        new ChannelTopic("orders.created")
    );

    container.addMessageListener(
        cancelledAdapter,
        new ChannelTopic("orders.cancelled")
    );

    container.addMessageListener(
        metricsListener,
        new PatternTopic("metrics.*")
    );

    return container;
}
~~~

Nếu có nhiều `MessageListenerAdapter` beans cùng kiểu, dùng `@Qualifier` hoặc injection tên bean rõ ràng để tránh mơ hồ.

Container dùng chung giúp tập trung quản lý connection factory, lifecycle, error handler và executor. Tránh tạo container mới trong từng service chỉ vì mỗi service có một listener.

### Pattern trùng exact subscription

Nếu một listener được đăng ký cả `orders.created` và `orders.*`, thông điệp trên `orders.created` có thể đi qua hai tuyến subscription. Vì vậy cần tránh cấu hình chồng lấn không có mục đích hoặc làm logic handler idempotent.

## 12. Adapter với payload JSON có schema rõ ràng

Một kiến trúc dễ bảo trì là để adapter chuyển bytes thành **String**, rồi receiver dùng Jackson parse JSON sang DTO.

Hợp đồng ví dụ:

~~~json
{
  "eventId": "e-101",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 1,
  "orderId": "o-101",
  "createdAt": "2026-11-13T09:00:00Z"
}
~~~

DTO:

~~~java
import java.time.Instant;

public record OrderCreatedEvent(
    String eventId,
    String eventType,
    int schemaVersion,
    String orderId,
    Instant createdAt
) { }
~~~

Service nghiệp vụ được tách khỏi lớp Redis:

~~~java
public interface OrderEventService {
    void onOrderCreated(OrderCreatedEvent event);
}
~~~

Receiver:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class OrderJsonReceiver {

    private static final Logger log =
        LoggerFactory.getLogger(OrderJsonReceiver.class);

    private final ObjectMapper mapper;
    private final OrderEventService service;

    public OrderJsonReceiver(
            ObjectMapper mapper,
            OrderEventService service) {
        this.mapper = mapper;
        this.service = service;
    }

    public void receiveMessage(String json) {
        try {
            OrderCreatedEvent event =
                mapper.readValue(json, OrderCreatedEvent.class);

            if (event.schemaVersion() != 1
                    || !"ORDER_CREATED".equals(event.eventType())
                    || event.eventId() == null
                    || event.eventId().isBlank()
                    || event.orderId() == null
                    || event.orderId().isBlank()) {
                log.warn("Rejected malformed order event");
                return;
            }

            service.onOrderCreated(event);
        } catch (JsonProcessingException ex) {
            log.warn("Invalid order event JSON", ex);
        }
    }
}
~~~

Adapter vẫn là:

~~~java
@Bean
MessageListenerAdapter orderJsonAdapter(OrderJsonReceiver receiver) {
    MessageListenerAdapter adapter =
        new MessageListenerAdapter(receiver, "receiveMessage");

    adapter.setSerializer(new StringRedisSerializer());
    return adapter;
}
~~~

Lợi ích:

- Wire format được thống nhất là UTF-8 JSON.
- Adapter làm việc chuyển bytes thành String.
- DTO/validation do service Java kiểm soát.
- Có `schemaVersion` để hỗ trợ nhiều release.
- Không phải dựa vào Java type metadata được nhúng tự do trong message.

Khi dùng `Instant` với Jackson, bảo đảm ObjectMapper có hỗ trợ Java time phù hợp với cấu hình Spring Boot đang triển khai.

## 13. Khi adapter deserialize trực tiếp sang object

`MessageListenerAdapter` hỗ trợ serializer để giải mã payload thành object, nhưng hai đầu phải thống nhất:

- Serializer của publisher.
- Serializer của adapter.
- Kiểu DTO.
- Quy tắc type metadata.
- Schema và version.
- Chính sách nhận dữ liệu không tin cậy.

Nếu publisher dùng JSON text nhưng adapter dùng `JdkSerializationRedisSerializer`, bytes không tương thích. Nếu một service Java lưu object với JDK serialization nhưng service Python gửi JSON, hai loại dữ liệu không thể được deserialize bằng một quy tắc duy nhất.

Đối với giao tiếp giữa nhiều dịch vụ, định dạng như JSON UTF-8 có schema rõ thường dễ mở rộng và debug. Đối với binary như Protobuf, raw `MessageListener` với decoder cụ thể cũng là lựa chọn phù hợp.

Không bật deserialization đa hình không giới hạn cho payload do client không đáng tin cậy cung cấp.

## 14. Chọn serializer phù hợp

| Nguồn publish | Wire format | Cách nhận thường dùng |
| --- | --- | --- |
| `StringRedisTemplate` | Text UTF-8 | Adapter `StringRedisSerializer` hoặc raw UTF-8 decode |
| Client Node.js/Python gửi JSON | UTF-8 JSON | String + Jackson DTO |
| `RedisTemplate` với JSON serializer | JSON theo serializer | JSON serializer tương thích |
| Protobuf | Binary bytes | Raw listener + Protobuf decoder |
| JDK serialization từ hệ thống Java cũ | Java binary | Serializer tương thích, kiểm soát rủi ro bảo mật |

Một channel tốt có contract như:

~~~text
Channel: orders.created
Encoding: UTF-8
Payload: JSON
Event type: ORDER_CREATED
Schema version: 1
Required fields: eventId, orderId, createdAt
Delivery semantics: Redis Pub/Sub (best effort)
~~~

Không có metadata chung trong Redis Pub/Sub để tự động chọn decoder đúng cho mọi message. Với channel có nhiều publisher, mỗi publisher phải tuân theo contract chung.

## 15. Thực thi callback: thread và thời gian xử lý

Callback Pub/Sub được kích hoạt theo đường subscription/container, không chạy trong HTTP request thread của người gửi.

~~~text
Publisher thread                Subscriber side
----------------                ---------------
convertAndSend(...)              Redis connection
          |                            |
          v                            v
Redis PUBLISH               RedisMessageListenerContainer
                                       |
                                       v
                                executor / listener
                                       |
                                       v
                              service xử lý nghiệp vụ
~~~

Điều này dẫn đến vài quy tắc:

1. Không giả định publisher chờ receiver hoàn thành.
2. Tránh HTTP call lâu, I/O nặng hoặc sleep trong `onMessage`.
3. Không dùng biến mutable không đồng bộ trong listener singleton.
4. Định nghĩa timeout riêng cho các thao tác phụ thuộc.
5. Không phụ thuộc vào thứ tự *hoàn thành* callback nếu executor có nhiều thread.

Một listener có thể nhận nhiều message nhanh hơn khả năng xử lý. Redis Pub/Sub không phải hệ thống queue có ACK và backpressure bền vững. Nếu nhận nhiều message và phải làm việc nặng, cần thiết kế queue/worker phù hợp.

## 16. Cấu hình executor và error handler

Có thể cấu hình executor cho phần dispatch listener:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.data.redis.listener.adapter.MessageListenerAdapter;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class PubSubExecutionConfig {

    private static final Logger log =
        LoggerFactory.getLogger(PubSubExecutionConfig.class);

    @Bean
    public ThreadPoolTaskExecutor redisMessageExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setThreadNamePrefix("redis-msg-");
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.initialize();

        return executor;
    }

    @Bean
    RedisMessageListenerContainer listenerContainer(
            RedisConnectionFactory factory,
            ThreadPoolTaskExecutor redisMessageExecutor,
            MessageListenerAdapter orderMessageAdapter) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(factory);
        container.setTaskExecutor(redisMessageExecutor);

        container.setErrorHandler(ex ->
            log.error("Unhandled Redis listener failure", ex)
        );

        container.addMessageListener(
            orderMessageAdapter,
            new ChannelTopic("orders.created")
        );

        return container;
    }
}
~~~

Tùy driver và phiên bản, container còn có executor dùng cho công việc subscription. Việc chọn pool size phải dựa trên tải thực tế, không tùy tiện tăng thread vô hạn.

**`setErrorHandler` không tạo retry bền vững.** Nó giúp quan sát/ứng phó với exception từ listener. Redis không tự phát lại message vì Java handler ném lỗi.

Nếu nhận message lỗi schema, receiver nên xử lý có kiểm soát. Nếu có tác vụ quan trọng cần retry, lưu công việc ở một cơ chế bền vững khác từ thời điểm đáng tin cậy.

## 17. Thứ tự message và xử lý đồng thời

Giả sử Redis publish:

~~~text
orders.created   order=o-101, version=1
orders.paid      order=o-101, version=2
~~~

Ở receiver có executor đa thread, handler `orders.paid` có thể hoàn thành trước handler `orders.created` nếu callback đầu làm I/O lâu.

~~~text
Thread A: xử lý created ---- I/O chậm ---------- hoàn tất
Thread B:          xử lý paid -- hoàn tất
~~~

Nếu nghiệp vụ cần đảm bảo thứ tự, hãy dùng version/sequence và trạng thái có thẩm quyền. Không coi thứ tự hoàn tất Java handler là chắc chắn trùng thứ tự publish.

Dữ liệu mutable trong listener phải được bảo vệ:

~~~java
// Sai khi listener có thể được gọi đồng thời:
private int count = 0;

public void receiveMessage(String payload) {
    count++;
}
~~~

Dùng metric/counter thread-safe cho thống kê. Với nghiệp vụ như cập nhật đơn hàng, dùng cập nhật có điều kiện trong database hoặc cấu trúc Redis nguyên tử theo yêu cầu.

## 18. Nhiều instance nhận cùng thông điệp

Giả sử ba pod cùng subscribe `orders.created`:

~~~text
                         Redis orders.created
                             /   |   \
                            /    |    \
                           v     v     v
                         Pod A Pod B Pod C
~~~

Redis Pub/Sub có tính chất **broadcast**. Các subscriber đang kết nối đều có thể nhận một bản message. Đây không phải competing consumer group tự phân công một event cho đúng một pod.

Phù hợp:

- Các pod cập nhật bộ nhớ local để làm mới UI.
- Service giám sát nhận broadcast.
- Các gateway cần gửi thông báo tới người dùng đang kết nối tại từng pod.

Có rủi ro:

- Cả ba pod gửi cùng một email.
- Cả ba pod trừ kho hoặc xử lý thanh toán một lần nữa.
- Một pod offline bỏ lỡ event, trong khi pod khác đã xử lý.

Nếu nghiệp vụ yêu cầu **chỉ một worker thực hiện**, dùng queue/stream/claim phù hợp hoặc idempotency ở nguồn dữ liệu chuẩn.

### Idempotency theo eventId

Một event có thể mang ID ổn định:

~~~json
{
  "eventId": "e-101",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 1,
  "orderId": "o-101"
}
~~~

Trong database, có thể lập bảng:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer dùng một giao dịch có điều kiện để claim event trước khi áp dụng thay đổi. Nếu trùng key, không thực hiện tác động thêm.

Tuy nhiên, việc claim và gọi hệ thống ngoài (email, thanh toán) vẫn có thể gặp partial failure, cần outbox/idempotency key cho phần đó. Idempotency chống xử lý lặp, **không khôi phục message bị mất**.

## 19. Pub/Sub không dùng làm nguồn công việc bắt buộc

Thiết kế có rủi ro:

~~~text
Order Service
  |
  +--> Ghi DB order
  |
  +--> Redis PUBLISH orders.created
                  |
                  v
         Notification Service
              gửi email
~~~

Nếu Notification Service offline khi publisher phát message, email có thể không được gửi. Không có API MessageListener nào giúp đọc lại Pub/Sub message đã trôi qua.

Thiết kế cần độ bền:

~~~text
Database transaction
  |
  +--> INSERT order
  +--> INSERT outbox event
  |
  v
COMMIT
  |
  v
Outbox publisher có retry
  |
  v
Durable queue / stream
  |
  v
Consumer nhận, xử lý, ACK và retry
~~~

Spring Data Redis `MessageListenerAdapter` chỉ là phương tiện dispatch đến Java method; nó không thay Redis Pub/Sub thành message queue bền vững. Redis Streams có mô hình consumer group/ACK khác Pub/Sub và cần API xử lý tương ứng.

### Khi nào Pub/Sub vẫn thích hợp?

Khi mất một số thông báo là chấp nhận được, ví dụ:

- “Có sản phẩm mới, hãy refresh UI”.
- “Config đã thay đổi, có thể kiểm tra lại nguồn”.
- “Báo hiệu để các pod làm mới local cache, có TTL dự phòng”.
- “Metric thời gian thực không cần đầy đủ tuyệt đối”.

Với các trường hợp này, cần cho ứng dụng khả năng **tự lấy lại trạng thái đúng** khi bỏ lỡ message.

## 20. Vòng đời và kết nối lại

Sơ đồ lifecycle:

~~~text
Spring ApplicationContext khởi tạo
          |
          v
RedisMessageListenerContainer start
          |
          v
Đăng ký SUBSCRIBE / PSUBSCRIBE
          |
          v
Nhận message và dispatch
          |
          v
Redis/network lỗi -> reconnect/resubscribe khi có thể
          |
          v
Application shutdown -> dừng subscription
~~~

Các vấn đề cần xét:

**Startup:** container đã là bean chưa chứng minh subscriber đã nhận đăng ký xong. Trong integration test, publish quá sớm có thể mất message.

**Reconnect:** container/driver có thể cố khôi phục subscription. Những message Redis đã publish khi kết nối mất không được phát lại.

**Shutdown:** callback đang chạy có thể bị ngắt khi process dừng. Nếu yêu cầu bắt buộc hoàn thành, trạng thái công việc phải được ghi bền vững trước.

**Rolling deployment:** pod cũ/mới cùng subscribe, có thể cùng xử lý. Các phiên bản payload phải tương thích.

**Redis Cluster:** cách triển khai Pub/Sub phụ thuộc chế độ regular/sharded Pub/Sub và driver; các thông báo keyspace expiration có phạm vi node chứa khóa. Không tự suy ra chỉ subscribe một node sẽ quan sát mọi expired event của cluster.

## 21. Đăng ký listener động

Ngoài đăng ký tại startup, container hỗ trợ thêm và gỡ listener khi chạy.

Ví dụ:

~~~java
ChannelTopic topic = new ChannelTopic("tenant.42.events");

container.addMessageListener(listener, topic);

// Khi không còn cần subscription:
container.removeMessageListener(listener, topic);
~~~

Điều này phù hợp khi các topic có vòng đời động, nhưng cần giới hạn số lượng subscription và quản lý cleanup. Không thêm listener mới mỗi lần HTTP request hoặc quên gỡ khi tenant/feature ngừng hoạt động.

Với số channel ổn định, cấu hình một lần tại startup sẽ đơn giản và dễ kiểm soát hơn.

## 22. Kiểm thử raw MessageListener

Logic parse có thể được tách khỏi Redis:

~~~java
public class OrderMessageDecoder {

    public OrderCreatedEvent decode(byte[] body) {
        String json = new String(
            body, StandardCharsets.UTF_8
        );

        // Parse JSON và validate theo DTO của ứng dụng.
        return parseAndValidate(json);
    }
}
~~~

`parseAndValidate` biểu diễn method do ứng dụng triển khai; ví dụ nhấn mạnh việc đưa logic nghiệp vụ/deserialize ra khỏi callback.

Unit test nên xem các trường hợp:

- Payload UTF-8 hợp lệ.
- Channel đúng/sai.
- Payload rỗng.
- JSON không hợp lệ.
- Event version không hỗ trợ.
- Trường bắt buộc thiếu.
- Dữ liệu nhạy cảm không bị log.

Unit test tự gọi `onMessage` không chứng minh Redis subscription đã được thiết lập; cần integration test cho đường truyền end-to-end.

## 23. Kiểm thử adapter với Redis thật

Một bài kiểm thử tốt cần mô phỏng:

~~~text
StringRedisTemplate.convertAndSend(...)
               |
               v
          Redis test server
               |
               v
   RedisMessageListenerContainer
               |
               v
      MessageListenerAdapter
               |
               v
     TestReceiver.receiveMessage(...)
~~~

Có thể dùng Redis chạy riêng cho test hoặc Testcontainers. Dùng một receiver ghi message vào queue:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public class TestOrderReceiver {

    private final BlockingQueue<String> messages =
        new LinkedBlockingQueue<>();

    public void receiveMessage(String payload) {
        messages.offer(payload);
    }

    public String poll(long timeout, TimeUnit unit)
            throws InterruptedException {
        return messages.poll(timeout, unit);
    }
}
~~~

Trong test context, cấu hình adapter cho `TestOrderReceiver` và đăng ký channel `test.orders.created`. Sau khi xác nhận subscription sẵn sàng:

~~~java
String payload = "{\"eventId\":\"test-1\"}";

redis.convertAndSend("test.orders.created", payload);

String actual = testReceiver.poll(3, TimeUnit.SECONDS);

assertThat(actual).isEqualTo(payload);
~~~

Đoạn trên minh họa phần **assertion bên trong một test** đã có Spring Redis bean, container và test receiver. Nó không tự tạo toàn bộ ứng dụng kiểm thử.

### Vì sao tránh Thread.sleep cố định?

Nếu test publish trước khi Redis xác nhận subscription, message có thể mất. Một `Thread.sleep(100)` không bảo đảm tốc độ CI hay môi trường Docker luôn đủ. Cần dựa vào lifecycle/readiness hoặc chờ điều kiện có timeout, phù hợp phiên bản framework.

### Điều gì cần kiểm tra?

- Message tới đúng receiver.
- Tên method trong adapter khớp.
- Serializer giải mã đúng payload.
- Không nhận nhầm channel.
- Timeout có thông báo rõ khi receiver không chạy.
- Nếu muốn đo nhiều message, dùng eventId duy nhất để không nhầm với message còn từ test khác.

## 24. Thí nghiệm mất thông điệp khi subscriber offline

Thực hiện trong Redis thử nghiệm:

1. Khởi động subscriber.
2. Publish `m1` và quan sát receiver nhận.
3. Dừng subscriber/container.
4. Publish `m2` khi subscriber offline.
5. Khởi động lại subscriber.
6. Publish `m3` và quan sát nhận.
7. Xác nhận không có tính năng phát lại `m2`.

~~~text
Time -------------------------------------------------------->

Subscriber: ONLINE ------ OFFLINE ------------ ONLINE
Publisher:      m1          m2                   m3
Kết quả:     nhận m1      bỏ lỡ m2             nhận m3
~~~

Nếu một subscriber khác vẫn online, nó có thể nhận `m2`. Thí nghiệm minh họa **không replay cho subscriber mất kết nối**, không có nghĩa toàn hệ thống không ai nhận.

## 25. Keyspace notifications cũng dùng Pub/Sub

Redis còn có các channel do Redis tự phát khi key thay đổi. Ví dụ:

~~~text
__keyevent@0__:expired
~~~

Có thể bật nhóm event thích hợp trong Redis thử nghiệm:

~~~bash
redis-cli CONFIG SET notify-keyspace-events Ex
~~~

Khi Redis xóa khóa do TTL, listener có thể nhận:

~~~text
channel: __keyevent@0__:expired
payload: session:42
~~~

Đây là **keyspace notification**, khác với domain event `orders.created` do ứng dụng tự publish.

Lưu ý:

- `expired` thường được publish khi Redis **thực sự xóa** key đã hết TTL; có thể trễ hơn deadline.
- Payload trên keyevent expired là tên key, **không phải value đã bị xóa**.
- Vẫn dùng Pub/Sub nên có thể mất khi listener offline.
- Với Redis Cluster, keyspace notifications gắn với node liên quan, cần xét topology.

Một `MessageListenerAdapter` dùng `StringRedisSerializer` có thể nhận tên key dạng String, nhưng không biến notification thành công việc định thời đáng tin cậy.

## 26. Chẩn đoán khi listener không nhận thông điệp

Kiểm tra từng tầng:

**1. Publisher có thực sự gửi?** Kiểm tra channel được truyền vào `convertAndSend`, serializer và lỗi kết nối.

**2. Container đã được Spring tạo?** Bean configuration có được scan không? Bean có lifecycle phù hợp và subscription đang hoạt động không?

**3. Đã addMessageListener đúng topic chưa?** Phân biệt `ChannelTopic("orders.created")` với `PatternTopic("orders.*")`.

**4. Có mismatch serializer không?** Publisher gửi JSON text, adapter lại chờ Java serialized object sẽ không hoạt động như ý.

**5. Method adapter có tồn tại không?** Kiểm tra tên, visibility và chữ ký `receiveMessage(String)`.

**6. Có exception bị bỏ qua không?** Thiết lập logging/error handler có kiểm soát.

**7. Message có được phát khi subscriber offline không?** Redis không replay.

**8. Có nhiều Redis instance/cluster không?** Kiểm tra publisher và subscriber đang dùng đúng môi trường, database/channel theo contract, network và topology.

Redis CLI trong môi trường phù hợp:

~~~bash
redis-cli PUBSUB CHANNELS
redis-cli PUBSUB NUMSUB orders.created
redis-cli PUBSUB NUMPAT
~~~

Các lệnh cho biết subscription hiện tại theo góc nhìn Redis, nhưng không xác minh business handler đã hoàn thành.

### Những metric đáng theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| Publisher send count/error | Khả năng phát message |
| Subscriber received count | Số callback thực nhận |
| Deserialize rejection count | Payload sai schema hoặc encoding |
| Handler duration/error | Tốc độ xử lý và lỗi nghiệp vụ |
| Container reconnect count | Độ ổn định kết nối |
| Durable backlog count (nếu có) | Công việc bắt buộc chưa hoàn thành |

Đừng dùng event ID làm metric label có cardinality cao; dùng event ID trong log/trace và metric tổng hợp theo channel, event type, result.

## 27. Bảo mật khi nhận message

Redis Pub/Sub không chứng minh người gửi là một service có thẩm quyền chỉ vì message xuất hiện trên một channel. Ứng dụng cần:

- Sử dụng Redis ACL phù hợp với channel và command được phép.
- Chặn payload quá lớn nếu ứng dụng có giới hạn.
- Validate JSON và mọi field đầu vào trước khi dùng.
- Xác minh quyền/điều kiện nghiệp vụ ở nguồn có thẩm quyền.
- Không cho payload quyết định trực tiếp lệnh xóa dữ liệu mà không kiểm tra.
- Tránh deserialize Java object không đáng tin cậy.
- Không log secret/token hoặc toàn bộ dữ liệu cá nhân.
- Có schema version và quy tắc tương thích khi publisher thay đổi.

Nếu một message chỉ là tín hiệu “dữ liệu đã thay đổi”, subscriber có thể đọc lại từ nguồn dữ liệu chuẩn trước khi quyết định hành động quan trọng.

## 28. Các lỗi phổ biến

### Có MessageListener bean nhưng quên đăng ký

`@Component` không tự thay thế `container.addMessageListener(listener, topic)`. Cần cấu hình subscriber.

### Dùng ChannelTopic với wildcard

`ChannelTopic("orders.*")` là tên chính xác, không phải wildcard subscribe. Dùng `PatternTopic("orders.*")`.

### Adapter không tìm thấy method

Kiểm tra tên được truyền trong constructor, ví dụ `"receiveMessage"`, và method public có chữ ký phù hợp với dữ liệu sau deserialize.

### Mismatch serializer

Publisher gửi String nhưng adapter đọc bằng JDK serializer, hoặc publisher gửi bytes nhị phân nhưng listener dùng `new String(...)`. Cần thống nhất wire format.

### Handler chặn thread quá lâu

Một callback gọi nhiều API bên ngoài, query database lớn hoặc chờ lock vô hạn sẽ làm xử lý chậm. Giữ callback mỏng và giới hạn công việc.

### Coi Pub/Sub là queue có ACK

Pub/Sub không có message replay sau reconnect. Với tác vụ bắt buộc, dùng durable transport/outbox.

### Mỗi pod thực hiện cùng một tác dụng phụ

Mỗi subscriber có thể nhận cùng message. Dùng cơ chế claim/idempotency hoặc chuyển sang competing consumer.

### Giả định exception tạo retry

Error handler chỉ giúp ứng dụng xử lý lỗi cục bộ. Redis không tự gửi lại message nếu callback Java ném exception.

### Dựa vào thứ tự hoàn tất callback

Các handler có thể chạy đồng thời; nghiệp vụ cần versioning hoặc đồng bộ trạng thái.

### Test publish quá sớm

Subscription chưa sẵn sàng có thể làm mất message đầu tiên. Kiểm tra readiness trước khi publish.

## 29. Bài tập thực hành

### Bài A: Raw MessageListener

Tạo listener cho `demo.raw`, publish `hello-redis` bằng `StringRedisTemplate`, ghi nhận channel và payload UTF-8. Thử khi payload rỗng và channel khác.

### Bài B: MessageListenerAdapter

Tạo receiver:

~~~java
public class DemoReceiver {
    public void receiveMessage(String message) {
        System.out.println(message);
    }
}
~~~

Đăng ký adapter có `StringRedisSerializer` trên `demo.adapter` và phát một chuỗi. Quan sát method nhận đúng payload.

### Bài C: PatternTopic

Đăng ký `PatternTopic("demo.orders.*")`, publish lên `demo.orders.created`, `demo.orders.paid` và `demo.customer.created`. Xác định channel nào được nhận.

### Bài D: Subscriber offline

Dừng listener rồi publish. Khởi động lại và giải thích vì sao không có replay. So sánh với yêu cầu một durable queue.

### Bài E: Nhiều instance

Chạy hai Spring Boot instances cùng subscribe. Publish một event, quan sát cả hai nhận. Thảo luận lựa chọn khi nghiệp vụ chỉ được thực hiện một lần.

### Bài F: Thay đổi schema

Tạo payload v1 và v2, xác định quy tắc receiver hỗ trợ hai phiên bản trong rolling deployment. Test JSON không hợp lệ không làm gián đoạn những event hợp lệ sau đó.

## 30. Câu hỏi thường gặp

**Có cần implement MessageListener nếu dùng MessageListenerAdapter?**

Không. Receiver có thể là POJO; adapter đảm nhận vai trò kết nối và gọi method.

**Có thể dùng @EventListener thay MessageListener không?**

`@EventListener` xử lý Spring application events, không tự subscribe Redis channel. Muốn nhận Redis Pub/Sub cần một integration như `RedisMessageListenerContainer`.

**Khi adapter được gọi, liệu đã có một Redis transaction?**

Không. Pub/Sub chuyển thông điệp và dispatch tới callback. Nó không tạo transaction bao trùm việc publisher và subscriber xử lý dữ liệu.

**Có thể nhận cả channel chính xác và pattern trong một container không?**

Có. Container có thể đăng ký các listener với `ChannelTopic` và `PatternTopic`. Chú ý subscription chồng lấn.

**Vì sao message đầu tiên sau startup bị mất?**

Có thể publisher phát trước khi subscription sẵn sàng. Redis Pub/Sub không đợi listener.

**Tại sao adapter nhận bytes sai kiểu?**

Serializer ở hai đầu không khớp, hoặc delegate method không phù hợp với decoded payload. Kiểm tra publisher wire format, adapter serializer và chữ ký method.

**Nếu có ba subscriber, mỗi event gửi được bao nhiêu lần?**

Redis Pub/Sub có thể phân phối một message đến cả ba subscriber đang kết nối. Không có khái niệm “chọn một subscriber duy nhất” như consumer group.

**Có thể xử lý lỗi bằng cách throw exception để Redis gửi lại?**

Không. Redis không biết Java handler đã xử lý tới đâu và không có replay cho Pub/Sub.

**Có nên dùng MessageListenerAdapter cho binary data?**

Có thể nếu serializer giải mã đúng kiểu, nhưng raw MessageListener thường dễ kiểm soát hơn khi cần thao tác trực tiếp với bytes hoặc metadata.

**Listener có phải luôn nhận được event đúng thứ tự publish?**

Không nên đồng nhất thứ tự Redis chuyển message với thứ tự *hoàn tất* xử lý trong các thread của ứng dụng. Dùng sequence/version cho nghiệp vụ phụ thuộc thứ tự.

## 31. Ghi nhớ

- `MessageListener` nhận `Message` raw, phù hợp khi cần bytes, channel, pattern và routing tùy biến.
- `MessageListenerAdapter` dùng serializer để chuyển thông điệp thành payload Java rồi gọi method POJO như `receiveMessage(String)`.
- `RedisMessageListenerContainer` quản lý subscription và lifecycle, là hạ tầng cần thiết cho cả hai.
- `ChannelTopic` lắng nghe exact channel; `PatternTopic` lắng nghe wildcard pattern.
- Publisher và subscriber phải thống nhất serializer, encoding và schema của payload.
- Callback nên ngắn, dễ quan sát, có kiểm tra lỗi và không chứa nghiệp vụ bắt buộc nếu thiếu cơ chế phục hồi.
- Nhiều subscriber có thể xử lý cùng một message; idempotency giúp chống trùng.
- Redis Pub/Sub **không ACK/replay** cho subscriber offline; các công việc cần độ bền phải dùng queue/stream/outbox hoặc nguồn dữ liệu bền vững khác.

## Tài liệu tham khảo

- [Spring Data Redis – Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis – MessageListener API](https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/connection/MessageListener.html)
- [Spring Data Redis – MessageListenerAdapter API](https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/listener/adapter/MessageListenerAdapter.html)
- [Spring Data Redis – RedisMessageListenerContainer API](https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/listener/RedisMessageListenerContainer.html)
- [Redis – Pub/Sub](https://redis.io/docs/latest/develop/pubsub/)
- [Redis – PUBLISH](https://redis.io/docs/latest/commands/publish/)
- [Redis – PSUBSCRIBE](https://redis.io/docs/latest/commands/psubscribe/)
- [Redis – Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)

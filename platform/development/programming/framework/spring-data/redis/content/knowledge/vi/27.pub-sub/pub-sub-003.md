# Gửi thông điệp bằng RedisTemplate

## 1. Một ứng dụng gửi sự kiện cho nhiều thành phần như thế nào?

Giả sử hệ thống bán hàng có ba dịch vụ Spring Boot:

- **Product Service** cập nhật tên và giá sản phẩm trong cơ sở dữ liệu.
- **Search Service** cập nhật chỉ mục tìm kiếm.
- **Notification Service** phản ứng khi một số loại sản phẩm thay đổi.

Product Service không nhất thiết phải gọi HTTP lần lượt đến từng dịch vụ nhận. Nó có thể **phát một thông điệp** lên một kênh Redis và các thành phần đang đăng ký kênh đó nhận thông điệp.

```text
                  Product Service
                      |
       RedisTemplate.convertAndSend(...)
                      |
                      v
              Redis Pub/Sub channel
              app:products:changed
                      |
             +--------+--------+
             |                 |
             v                 v
      Search Service     Notification Service
      đang SUBSCRIBE     đang SUBSCRIBE
             |                 |
       cập nhật index     xử lý thông báo
```

Đây là mô hình **Publish/Subscribe (Pub/Sub)**:

- **Publisher** là bên gửi thông điệp.
- **Channel** là tên kênh trung gian để định tuyến thông điệp.
- **Subscriber** là bên đăng ký nghe kênh.
- **Redis** chuyển thông điệp mới đến những subscriber **đang kết nối và đăng ký** tại thời điểm phát.

Trong Spring Data Redis, `RedisTemplate` cung cấp phương thức `convertAndSend(...)` để phát thông điệp. Phía nhận có thể dùng `RedisMessageListenerContainer` để duy trì đăng ký và chuyển thông điệp tới `MessageListener`.

**Điểm cần nhớ ngay:** Redis Pub/Sub là cơ chế phát trực tiếp theo thời điểm. Nó **không tự lưu hàng đợi thông điệp để người nhận offline đọc lại**, không có cơ chế xác nhận đã xử lý và không bảo đảm ứng dụng nhận thành công mọi sự kiện nghiệp vụ.

Bài học thuộc chương **Pub/Sub** của **Spring Data Redis**, tập trung vào cách gửi thông điệp bằng `RedisTemplate`, từ thao tác đơn giản với chuỗi tới một payload JSON có cấu trúc, đồng thời giải thích cách người nhận hiểu dữ liệu và những giới hạn của mô hình.

## 2. Channel Pub/Sub khác khóa Redis thông thường

Trong Redis, các lệnh lưu dữ liệu như `SET` và `GET` thao tác trên **khóa**:

```redis
SET product:42:price 120
GET product:42:price
```

Còn Pub/Sub dùng **kênh**:

```redis
PUBLISH app:products:changed "product 42 updated"
SUBSCRIBE app:products:changed
```

Tên `app:products:changed` trong ví dụ là tên kênh, không phải một Redis String chứa thông điệp mới nhất.

| Đặc điểm | Khóa Redis | Kênh Pub/Sub |
|---|---|---|
| Mục đích | Lưu và đọc trạng thái | Phát thông điệp tức thời |
| Lệnh thông dụng | `SET`, `GET`, `HSET`, `EXPIRE` | `PUBLISH`, `SUBSCRIBE`, `PSUBSCRIBE` |
| Có giữ nội dung cho lần đọc sau? | Có, cho đến khi bị xóa/hết hạn | Không, Pub/Sub thông thường không lưu lịch sử |
| Có TTL? | Có thể gắn TTL với khóa | Kênh không phải khóa có TTL |
| Ai nhận? | Client chủ động đọc khóa | Client đang subscribe khi thông điệp được phát |
| Phân phối | Client đọc đúng tên khóa | Redis phát tới subscriber của kênh tương ứng |

Ví dụ:

```redis
PUBLISH app:products:changed "hello"
GET app:products:changed
```

Lệnh `GET` không đọc lại `"hello"` đã phát. Nếu không có khóa cùng tên được lưu riêng, Redis trả `nil`. `PUBLISH` không tạo khóa chứa payload.

Vì vậy, nếu muốn lưu **trạng thái hiện tại**, dùng Redis data types và lệnh lưu trữ phù hợp. Nếu muốn **thông báo đến các thành phần đang hoạt động**, Pub/Sub có thể phù hợp.

## 3. Cơ chế gửi: PUBLISH và convertAndSend

### 3.1. Gửi trực tiếp bằng Redis CLI

Mở cửa sổ terminal A và đăng ký nghe:

```bash
redis-cli SUBSCRIBE app:products:changed
```

Cửa sổ này giữ kết nối ở trạng thái đăng ký. Sau đó, tại terminal B:

```bash
redis-cli PUBLISH app:products:changed "Product 42 changed"
```

Terminal A sẽ hiển thị thông điệp được phát tới kênh.

Tại terminal B, `PUBLISH` trả về số subscriber đã được Redis tính là nhận thông điệp, chẳng hạn `1` nếu có một subscriber phù hợp. Giá trị này **không chứng minh** listener đã hoàn thành công việc nghiệp vụ, đã cập nhật chỉ mục hay đã lưu dữ liệu thành công.

Nếu bạn phát thông điệp **trước khi** terminal A subscribe, terminal A sẽ không tự nhận lại thông điệp cũ. Pub/Sub thông thường không lưu lại lịch sử.

### 3.2. Gửi bằng StringRedisTemplate

`StringRedisTemplate` là biến thể `RedisTemplate<String, String>` được cấu hình cho dữ liệu chuỗi, thuận tiện khi muốn phát nội dung dễ đọc:

```java
package com.example.redis.pubsub;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SimplePublisher {

    public static final String CHANNEL = "app:products:changed";

    private final StringRedisTemplate redis;

    public SimplePublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long publishText(String text) {
        return redis.convertAndSend(CHANNEL, text);
    }
}
```

Ví dụ gọi:

```java
Long subscribers = publisher.publishText("Product 42 changed");
System.out.println("Redis reported receivers: " + subscribers);
```

Phương thức `convertAndSend(channel, message)` nhận:

1. **`channel`**: tên kênh Pub/Sub.
2. **`message`**: nội dung phát, được chuyển thành byte bằng serializer của template.
3. **Kết quả kiểu `Long`**: số subscriber được Redis báo nhận ở mức Pub/Sub. Kết quả này không phải biên nhận xử lý nghiệp vụ.

Đối với thông điệp String, `StringRedisTemplate` giúp nội dung phát ra tương thích với thao tác đọc chuỗi UTF-8 thông thường.

### 3.3. Dùng RedisTemplate thông thường thì sao?

Về bản chất, `StringRedisTemplate` cũng là `RedisTemplate`. Bạn có thể dùng một bean `RedisTemplate<String, MyEvent>`:

```java
redisTemplate.convertAndSend(
        "app:products:changed",
        event
);
```

Nhưng **dữ liệu được phát dưới dạng byte phụ thuộc vào `valueSerializer`** của template:

- `StringRedisSerializer` phù hợp với payload chuỗi.
- Serializer JSON có thể chuyển đối tượng Java thành JSON.
- Serializer JDK có thể tạo byte nhị phân theo cơ chế tuần tự hóa Java.
- Serializer tùy chỉnh có thể tạo một định dạng hoàn toàn khác.

Subscriber phải biết **định dạng tương ứng để giải mã**. Không nên giả định mọi lời gọi `convertAndSend` mặc định phát JSON, hoặc mọi subscriber có thể đọc trực tiếp object Java.

## 4. Chuẩn hóa payload: gửi một sự kiện JSON

Thông điệp chỉ chứa `"Product 42 changed"` phù hợp để thử nghiệm, nhưng hệ thống thực thường cần thông tin có cấu trúc. Có thể dùng một bản ghi Java:

```java
package com.example.redis.pubsub;

public record ProductChangedEvent(
        String eventId,
        long productId,
        long version,
        long occurredAtEpochMillis
) {
}
```

Ý nghĩa:

| Trường | Vai trò |
|---|---|
| `eventId` | Định danh một sự kiện do publisher tạo |
| `productId` | Đối tượng nghiệp vụ bị thay đổi |
| `version` | Phiên bản dữ liệu nguồn, giúp nhận biết thứ tự nghiệp vụ khi cần |
| `occurredAtEpochMillis` | Thời điểm phát sinh sự kiện theo Unix epoch mili giây |

Ví dụ JSON:

```json
{
  "eventId": "evt-731",
  "productId": 42,
  "version": 7,
  "occurredAtEpochMillis": 1762990000000
}
```

Không cần gửi cả `ProductEntity` với mọi thuộc tính, quan hệ JPA và dữ liệu nhạy cảm. Thông điệp nên chứa **thông tin tối thiểu đủ để subscriber xử lý** hoặc truy vấn lại nguồn.

Một kênh thường chứa **một loại thông điệp có hợp đồng rõ ràng**. Nếu nhiều loại cùng kênh, nên thêm `eventType` hoặc một trường phân biệt rõ ràng.

## 5. Publisher hoàn chỉnh: ObjectMapper + StringRedisTemplate

Một cách minh bạch là **tự serialize object thành JSON**, rồi dùng `StringRedisTemplate` phát đúng chuỗi JSON đó. Nhờ vậy, cả publisher và subscriber dùng chung quy ước UTF-8/JSON mà không phụ thuộc vào cấu hình serializer đối tượng mặc định của `RedisTemplate`.

```java
package com.example.redis.pubsub;

import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductChangedPublisher {

    public static final String CHANNEL = "app:products:changed";

    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper;

    public ProductChangedPublisher(
            StringRedisTemplate redis,
            ObjectMapper objectMapper) {
        this.redis = redis;
        this.objectMapper = objectMapper;
    }

    public Long publish(long productId, long version) {
        if (productId <= 0) {
            throw new IllegalArgumentException(
                    "productId phải là số dương"
            );
        }

        ProductChangedEvent event = new ProductChangedEvent(
                UUID.randomUUID().toString(),
                productId,
                version,
                System.currentTimeMillis()
        );

        String json;

        try {
            json = objectMapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Không thể tạo JSON cho sự kiện", ex
            );
        }

        return redis.convertAndSend(CHANNEL, json);
    }
}
```

Ví dụ sử dụng:

```java
Long receivers = productChangedPublisher.publish(42L, 7L);
```

Trong luồng này:

```text
ProductChangedEvent
         |
         | ObjectMapper.writeValueAsString
         v
   JSON String trong Java
         |
         | StringRedisTemplate.convertAndSend
         v
  Redis PUBLISH vào channel
         |
         +----> subscriber đang lắng nghe
```

`ObjectMapper` thường được Spring Boot cấu hình như một bean khi dự án có Jackson phù hợp. `StringRedisTemplate` thường được Spring Boot tạo khi Spring Data Redis và cấu hình kết nối hợp lệ đã có.

Nếu cả publisher và subscriber dùng JSON, cần thống nhất tên trường, kiểu dữ liệu, phiên bản schema và encoding. Việc serialize thành công chưa bảo đảm subscriber có thể xử lý nếu hai bên đang dùng phiên bản message contract khác nhau.

### 5.1. Có nên gửi DTO trực tiếp bằng RedisTemplate JSON?

Có thể, nếu thiết kế rõ template dành riêng cho Pub/Sub:

```java
@Bean("eventRedisTemplate")
RedisTemplate<String, ProductChangedEvent> eventRedisTemplate(
        RedisConnectionFactory factory) {

    RedisTemplate<String, ProductChangedEvent> template =
            new RedisTemplate<>();

    template.setConnectionFactory(factory);
    template.setKeySerializer(new StringRedisSerializer());
    template.setValueSerializer(
            new Jackson2JsonRedisSerializer<>(ProductChangedEvent.class)
    );

    template.afterPropertiesSet();
    return template;
}
```

Khi đó:

```java
eventRedisTemplate.convertAndSend(
        ProductChangedPublisher.CHANNEL,
        event
);
```

Đây là phương án thay thế cách dùng `ObjectMapper + StringRedisTemplate` ở trên. **Không nên tự serialize thành JSON string rồi lại đưa qua một serializer yêu cầu `ProductChangedEvent`**; kiểu đầu vào phải khớp hợp đồng của template.

Trong những dự án có nhiều loại event, có thể định nghĩa envelope chung như `eventType`, `schemaVersion`, `eventId`, `payload` và dùng serializer phù hợp. Đó là lựa chọn thiết kế protocol giữa các dịch vụ, không phải một tính năng Redis tự sinh ra.

## 6. Subscriber nhận thông điệp như thế nào?

Để nhìn được toàn bộ vòng đời một thông điệp, ta tạo một subscriber đơn giản. Phía gửi vẫn chỉ cần `convertAndSend`; phần đăng ký giúp kiểm chứng thông điệp đã đi tới đâu.

### 6.1. MessageListener nhận byte của thông điệp

Spring Data Redis có giao diện `MessageListener`:

```java
void onMessage(Message message, byte[] pattern)
```

Trong đó:

- `message.getBody()` là byte payload.
- `message.getChannel()` là byte tên kênh.
- `pattern` thường có ý nghĩa khi lắng nghe bằng mẫu kênh (`PatternTopic`).
- Code listener có trách nhiệm giải mã và xử lý thông điệp.

Ví dụ subscriber đọc JSON, in log và xóa bản cache phục vụ đọc của sản phẩm đã đổi:

```java
package com.example.redis.pubsub;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class ProductChangedListener implements MessageListener {

    private static final Logger log =
            LoggerFactory.getLogger(ProductChangedListener.class);

    private final ObjectMapper objectMapper;
    private final StringRedisTemplate redis;

    public ProductChangedListener(
            ObjectMapper objectMapper,
            StringRedisTemplate redis) {
        this.objectMapper = objectMapper;
        this.redis = redis;
    }

    @Override
    public void onMessage(Message message, byte[] pattern) {
        String json = new String(
                message.getBody(),
                StandardCharsets.UTF_8
        );

        try {
            ProductChangedEvent event = objectMapper.readValue(
                    json,
                    ProductChangedEvent.class
            );

            if (event.productId() <= 0) {
                log.warn("Bỏ qua event có productId không hợp lệ");
                return;
            }

            String cacheKey =
                    "product:detail:v1:" + event.productId();

            // Xóa cache lặp lại vẫn an toàn về tác dụng trên khóa.
            redis.delete(cacheKey);

            log.info(
                    "Đã xử lý event {}, productId={}, version={}",
                    event.eventId(),
                    event.productId(),
                    event.version()
            );

        } catch (JsonProcessingException ex) {
            // Pub/Sub không cung cấp cơ chế phát lại khi xử lý thất bại.
            log.warn("Payload Pub/Sub không hợp lệ", ex);
        } catch (RuntimeException ex) {
            log.error("Lỗi xử lý thông điệp Pub/Sub", ex);
        }
    }
}
```

Ví dụ sử dụng **xóa cache** vì đây là một thao tác tương đối đơn giản, có thể lặp lại. Nếu nhiều application instance cùng lắng nghe và cùng xóa một khóa Redis, chỉ một lần xóa đầu tiên có tác dụng thực tế; những lần xóa sau không tạo thêm bản ghi bị xóa.

Tuy nhiên, **không đồng nghĩa việc invalidation luôn thành công**. Nếu Redis lỗi hoặc subscriber offline, thông điệp có thể mất. Với dữ liệu cần giới hạn tuổi, nên có TTL và chính sách xử lý tính nhất quán riêng.

### 6.2. RedisMessageListenerContainer duy trì đăng ký

Không nên mở kết nối `SUBSCRIBE` mới mỗi lần có HTTP request. Lệnh `SUBSCRIBE` dùng kết nối ở chế độ đăng ký và listener cần tồn tại lâu dài trong vòng đời ứng dụng.

Spring Data Redis cung cấp `RedisMessageListenerContainer` để quản lý kết nối đăng ký, đăng ký nhiều listener và chuyển thông điệp tới callback.

```java
package com.example.redis.pubsub;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class ProductPubSubConfiguration {

    @Bean
    public RedisMessageListenerContainer productListenerContainer(
            RedisConnectionFactory connectionFactory,
            ProductChangedListener productChangedListener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);

        container.addMessageListener(
                productChangedListener,
                new ChannelTopic(ProductChangedPublisher.CHANNEL)
        );

        return container;
    }
}
```

Với ứng dụng Spring có cấu hình bean/lifecycle thông thường, container được quản lý bởi Spring và có thể khởi động đăng ký lúc ứng dụng chạy. Nó xử lý kết nối đăng ký và phân phối sự kiện tới listener.

`RedisMessageListenerContainer` là lựa chọn thích hợp khi:

- Nhiều thành phần muốn lắng nghe một hoặc nhiều kênh.
- Muốn để Spring quản lý vòng đời đăng ký.
- Cần điều chỉnh executor xử lý callback, giám sát lỗi và kết nối.
- Muốn quản lý danh sách topic một cách rõ ràng.

Listener phải xử lý nhanh hoặc chuyển công việc nặng sang một cơ chế có kiểm soát. Nếu callback chiếm luồng quá lâu, các thông điệp đến tiếp theo có thể bị xử lý chậm hoặc tạo áp lực lên tài nguyên của ứng dụng.

### 6.3. ChannelTopic và PatternTopic

Đăng ký đúng một kênh:

```java
new ChannelTopic("app:products:changed")
```

Đăng ký theo mẫu:

```java
new PatternTopic("app:products:*")
```

Mẫu `app:products:*` có thể khớp các kênh như:

```text
app:products:changed
app:products:deleted
app:products:created
```

Trong cấu hình container:

```java
container.addMessageListener(
        productChangedListener,
        new PatternTopic("app:products:*")
);
```

Nhưng **một listener chỉ giải mã `ProductChangedEvent`** không nên được đăng ký vô điều kiện với mọi loại sự kiện. Nếu dùng `PatternTopic`, phải có cách phân biệt hợp đồng thông điệp hoặc định tuyến đến những handler tương ứng.

Redis dùng `PUBLISH` để gửi đến một kênh cụ thể; subscriber có thể đăng ký tên kênh hoặc mẫu. Publisher không phải dùng wildcard để phát nhiều kênh.

## 7. Luồng hoạt động từ publisher tới subscriber

Với cấu hình JSON và container phía trên:

```text
1. Product Service hoàn tất cập nhật sản phẩm.
2. ProductChangedPublisher tạo ProductChangedEvent.
3. ObjectMapper chuyển record thành JSON.
4. StringRedisTemplate.convertAndSend phát JSON tới kênh.
5. Redis gửi thông điệp đến các kết nối đang SUBSCRIBE.
6. RedisMessageListenerContainer nhận byte thông điệp.
7. ProductChangedListener giải mã JSON thành record Java.
8. Listener xử lý nghiệp vụ phù hợp, ví dụ xóa cache.
```

Biểu diễn luồng:

```text
ProductChangedPublisher               Redis                   ProductChangedListener
          |                              |                               |
          | convertAndSend(CHANNEL, json)|                               |
          |----------------------------->|                               |
          |                              | PUBLISH to subscribers         |
          |                              |------------------------------>|
          |                              |                               |
          | <--- số subscriber ----------|                               |
          |                              |                 deserialize JSON
          |                              |                 process event
          |                              |                               |
```

**Publisher không chờ listener hoàn thành việc xử lý.** Phản hồi `convertAndSend` không phải một kết quả RPC của handler. Nếu listener đọc JSON bị lỗi hoặc gọi dịch vụ phụ thất bại, Redis Pub/Sub không tự gửi báo lỗi đó về publisher.

## 8. Publish khi dữ liệu nguồn thay đổi: thời điểm rất quan trọng

Giả sử Product Service cập nhật database rồi phát sự kiện để Search Service tải thông tin mới. Nếu publish **trước khi transaction commit**, subscriber có thể đọc database khi giá trị mới chưa có sẵn:

```text
Product Service                 Database              Subscriber
      |                             |                       |
      | UPDATE product              |                       |
      |---------------------------->|                       |
      | PUBLISH ProductChanged                              |
      |---------------------------------------------------->|
      |                             |         SELECT product |
      |                             |<-----------------------|
      |                             |--- giá trị cũ -------->|
      | COMMIT                      |                       |
      |---------------------------->|                       |
```

Một cách tổ chức trong Spring là công bố **sự kiện nội bộ ứng dụng** khi thay đổi dữ liệu, rồi chỉ gửi qua Redis Pub/Sub sau khi transaction commit.

Ví dụ kiểu sự kiện nội bộ:

```java
package com.example.redis.pubsub;

public record ProductCommitted(
        long productId,
        long version
) {
}
```

Trong phần ghi database, có thể công bố sự kiện sau khi sửa entity:

```java
@Transactional
public void updatePrice(long id, BigDecimal price) {
    ProductEntity product = productRepository.findById(id)
            .orElseThrow();

    product.changePrice(price);

    applicationEventPublisher.publishEvent(
            new ProductCommitted(id, product.getVersion())
    );
}
```

Ví dụ listener phát Redis sau commit:

```java
package com.example.redis.pubsub;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductChangeRedisBridge {

    private final ProductChangedPublisher publisher;

    public ProductChangeRedisBridge(ProductChangedPublisher publisher) {
        this.publisher = publisher;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void publishAfterCommit(ProductCommitted event) {
        publisher.publish(
                event.productId(),
                event.version()
        );
    }
}
```

Các lớp `ProductEntity`, `ProductRepository`, `BigDecimal`, `@Transactional` và `ApplicationEventPublisher` trong đoạn mô tả phần ghi thuộc hệ thống dữ liệu nguồn, cần được hiện thực với những import và cơ chế transaction của dự án.

**Điểm giới hạn:** `@TransactionalEventListener(AFTER_COMMIT)` giúp chọn thời điểm phát sau commit, nhưng **không làm việc gửi Pub/Sub trở nên bền vững**. Nếu ứng dụng chết ngay sau commit nhưng trước khi publish, sự kiện có thể không được phát. Nếu Redis hoặc mạng lỗi, commit database không tự bị rollback. Khi cần bảo đảm eventual delivery, phải thiết kế outbox hoặc cơ chế công bố bền vững khác.

## 9. Vì sao Redis Pub/Sub không phải hàng đợi đáng tin cậy?

Redis Pub/Sub thông thường có ngữ nghĩa phân phối **at-most-once** ở mức thông điệp: khi Redis đã gửi thông điệp, nó không giữ bản sao và không tự phát lại nếu người nhận lỗi hoặc mất kết nối.

### 9.1. Subscriber đang offline

```text
t0: Subscriber A đang online
t1: Subscriber A mất kết nối
t2: Publisher gửi event-101
t3: Redis không giữ event-101 cho A
t4: Subscriber A kết nối lại
t5: A chỉ nhận những thông điệp mới từ lúc đăng ký lại
```

Nếu không có subscriber, `PUBLISH` vẫn có thể hoàn thành và trả số người nhận bằng 0. Điều đó là bình thường với Pub/Sub.

### 9.2. Handler lỗi sau khi nhận

```text
Redis phát JSON
      |
      v
MessageListener nhận byte
      |
      v
JSON parse thành công
      |
      v
Database hoặc API phụ bị lỗi
      |
      v
Không có ACK/retry tích hợp của Pub/Sub
```

Đăng ký kênh không có nghĩa bạn đã có một **hàng đợi công việc bền vững**. Logging trong handler giúp quan sát sự cố, nhưng không làm Redis phát lại thông điệp.

### 9.3. So sánh Pub/Sub và Redis Streams

| Tiêu chí | Redis Pub/Sub | Redis Streams |
|---|---|---|
| Đối tượng chính | Kênh phát trực tiếp | Stream có các bản ghi |
| Người nhận offline | Bỏ lỡ thông điệp đã phát | Có thể đọc dữ liệu còn được giữ trong stream |
| Lưu lịch sử | Không | Có theo chính sách lưu/trim |
| Theo dõi consumer | Không có ACK chuẩn của Pub/Sub | Consumer groups có pending entries và cơ chế xác nhận |
| Truyền tới nhiều người nhận | Fan-out theo subscriber đang kết nối | Tùy nhóm và cách đọc |
| Mức độ phù hợp | Tín hiệu tức thời, thông báo sống, invalidation có TTL dự phòng | Xử lý bất đồng bộ cần đọc lại, retry hoặc theo dõi tiến độ |

Redis Streams cũng cần thiết kế retention, consumer group, retry và cách xử lý trùng lặp. Nó không tự bảo đảm đúng một lần cho mọi tác dụng phụ. Nếu nhiệm vụ cần độ bền, lựa chọn phải gắn với mức độ mất dữ liệu được phép.

Một số trường hợp thích hợp với Pub/Sub:

- Thông báo thay đổi đến các node đang online.
- Phát tín hiệu làm mới giao diện real-time.
- Vô hiệu hóa local cache có thể phục hồi hoặc hết TTL.
- Thông báo trạng thái tức thời mà người nhận có thể kiểm tra lại sau.

Những trường hợp **không nên chỉ dùng Pub/Sub**:

- Thanh toán, khấu trừ tiền hoặc xử lý đơn hàng không được mất.
- Gửi email phải được retry đến khi ghi nhận kết quả.
- Cập nhật dữ liệu bắt buộc có báo cáo hoàn thành.
- Công việc cần xử lý lại sau khi consumer restart.

## 10. Fan-out: một thông điệp có thể đến nhiều subscriber

Giả sử hai bản sao của Search Service và một Notification Service cùng đăng ký `app:products:changed`:

```text
                    Redis channel
                 app:products:changed
                          |
            +-------------+-------------+
            |             |             |
            v             v             v
         Search A       Search B     Notification
         SUBSCRIBE      SUBSCRIBE    SUBSCRIBE
```

Mỗi kết nối subscriber đang đăng ký có thể nhận cùng thông điệp. Redis Pub/Sub **không tự chia công việc theo nhóm consumer** để bảo đảm chỉ một bản sao Search Service xử lý.

Điều này có thể là hành vi mong muốn khi mỗi instance giữ **local in-memory cache** riêng và tất cả cần được invalidation. Nhưng nếu tác vụ có tác dụng phụ chung, chẳng hạn ghi một thông báo cho khách hàng, mọi instance cùng xử lý có thể gây tác dụng lặp. Khi đó cần thiết kế công việc có chống lặp hoặc dùng cơ chế phân phối công việc thích hợp.

Cũng cần phân biệt:

- **Cache Redis chung:** xóa một khóa Redis là tác động lên dữ liệu dùng chung, có thể lặp an toàn về kết quả xóa.
- **Local cache trên từng instance:** mỗi instance phải nhận và xử lý thông báo nếu muốn xóa local cache riêng.
- **Công việc cần một người xử lý:** Pub/Sub fan-out mặc định không cung cấp phân công độc quyền.

## 11. Thiết kế tên kênh, schema và quyền truy cập

### 11.1. Tên kênh phải dễ hiểu

Có thể xây dựng quy ước:

```text
app:products:changed
app:products:deleted
app:orders:status-changed
app:catalog:refresh
```

Nếu môi trường, hệ thống con hoặc tenant cần cách ly, tên kênh có thể chứa phần nhận diện:

```text
dev:app:products:changed
staging:app:products:changed
prod:app:products:changed
```

Không dùng trùng tên kênh cho thông điệp có schema hoàn toàn khác nhau mà không có cơ chế phân biệt. Cũng không ghép trực tiếp dữ liệu người dùng vào kênh nếu chưa giới hạn hoặc kiểm soát quyền, tránh phát tùy ý sang những channel nhạy cảm.

### 11.2. Định dạng thông điệp nên có phiên bản

Khi nhiều dịch vụ được triển khai độc lập, một publisher phiên bản mới có thể phát trường mà subscriber cũ chưa hiểu. Có thể định nghĩa envelope:

```json
{
  "eventType": "product.changed",
  "schemaVersion": 1,
  "eventId": "evt-731",
  "occurredAtEpochMillis": 1762990000000,
  "payload": {
    "productId": 42,
    "version": 7
  }
}
```

`schemaVersion` cho biết định dạng thông điệp, khác với `version` của sản phẩm.

Một số quy tắc phối hợp:

- Chỉ gửi các trường cần cho sự kiện.
- Định nghĩa cách xử lý trường không biết hoặc trường tùy chọn.
- Giữ các trường bắt buộc có ý nghĩa nhất quán.
- Ghi rõ encoding, chẳng hạn JSON UTF-8.
- Đặt giới hạn kích thước payload.
- Không gửi mật khẩu, access token hoặc dữ liệu nhạy cảm khi không cần.
- Theo dõi phiên bản message contract khi nhiều dịch vụ triển khai khác thời điểm.

### 11.3. Bảo mật

Pub/Sub không tự cung cấp cơ chế phân quyền ứng dụng theo từng loại sự kiện. Redis ACL có thể giới hạn các lệnh và kênh Pub/Sub được phép truy cập, tùy phiên bản và cấu hình Redis.

Khi dùng Redis chung cho nhiều ứng dụng hoặc tenant, phải kiểm soát ai được `PUBLISH` và `SUBSCRIBE` vào kênh nào. Tên kênh có quy ước không thay thế cơ chế xác thực và phân quyền.

Đối với hệ thống qua mạng, cần cấu hình kết nối an toàn theo hạ tầng, có thể gồm TLS, xác thực và chính sách mạng nội bộ.

## 12. Theo dõi việc gửi và nhận thông điệp

### 12.1. Số subscriber trả về có ý nghĩa gì?

```java
Long receiverCount = redis.convertAndSend(
        "app:products:changed",
        json
);
```

Giá trị nhận về giúp quan sát số subscriber được Redis tính là nhận thông điệp. Nó **không bảo đảm**:

- MessageListener đã chạy xong.
- JSON đã giải mã thành công.
- Database/search index đã được cập nhật.
- Người nhận đã ghi thông điệp vào bộ nhớ bền vững.
- Một subscription là một nghiệp vụ hoàn thành đúng một lần.

Với môi trường Redis Cluster, cách tính số subscriber và phạm vi thông tin có thể phụ thuộc topology/chế độ Pub/Sub. Không dùng con số này như biên nhận nghiệp vụ xuyên toàn bộ cụm.

### 12.2. Các chỉ số nên có

| Chỉ số | Nên đo ở đâu | Ý nghĩa |
|---|---|---|
| Số lần publish được gọi | Publisher | Tổng lần ứng dụng cố phát |
| Số lần publish lỗi | Publisher | Lỗi kết nối/serialization khi phát |
| Số receiver được báo | Phản hồi `convertAndSend` | Thông tin Pub/Sub ở mức Redis |
| Số message nhận | Listener | Những thông điệp thực sự đi vào callback |
| Số JSON parse lỗi | Listener | Không tương thích schema/payload |
| Thời gian xử lý handler | Listener | Công việc phía subscriber nhanh/chậm |
| Số lần xử lý thất bại | Listener | Lỗi khi thực hiện tác dụng phụ |
| Trạng thái kết nối subscription | Container/Redis client | Có đang duy trì đăng ký hay không |
| Độ trễ xử lý ứng dụng | Metric/trace | Chậm trễ giữa phát và xử lý, khi đo được |

Không gộp **publish thành công**, **subscriber nhận** và **xử lý nghiệp vụ thành công** thành một chỉ số duy nhất.

### 12.3. Các lệnh quan sát Redis

Trong Redis CLI, có thể xem subscriber theo kênh:

```redis
PUBSUB NUMSUB app:products:changed
```

Hoặc liệt kê kênh có subscriber phù hợp:

```redis
PUBSUB CHANNELS app:products:*
```

Các lệnh này quan sát tình trạng Pub/Sub hiện tại; không cho biết lịch sử những thông điệp đã phát hoặc công việc đã hoàn thành. Trong Redis Cluster, kết quả có thể gắn với phạm vi node hoặc chế độ Pub/Sub cụ thể.

## 13. Những lỗi phổ biến khi dùng convertAndSend

### Lỗi 1: Cho rằng convertAndSend lưu thông điệp

```java
redis.convertAndSend("orders:created", json);
```

Lời gọi gửi thông điệp tức thời. Nó không tự lưu bản ghi để đọc lại bằng `GET` hoặc nhận khi subscriber kết nối sau.

### Lỗi 2: Không thống nhất serializer

Publisher sử dụng serializer JDK, subscriber cố đọc UTF-8 JSON:

```text
Publisher: đối tượng Java -> byte nhị phân
Subscriber: byte -> new String(...) -> ObjectMapper.readValue(...)
```

Hai bên có thể không giải mã được. Chọn format rõ ràng và dùng serializer phù hợp ở cả hai phía.

### Lỗi 3: Đọc số receiver như số tác vụ hoàn thành

`convertAndSend` trả `1` không chứng minh handler xử lý thành công. Redis Pub/Sub không nhận ACK nghiệp vụ từ listener.

### Lỗi 4: Publish trước commit

Subscriber có thể nhận sự kiện rồi đọc database cũ. Đối với thay đổi trong transaction, cần xem xét phát sau commit và nếu yêu cầu độ bền, dùng outbox.

### Lỗi 5: Gửi toàn bộ entity JPA

Entity có thể chứa quan hệ lười tải, trường nhạy cảm hoặc dữ liệu không ổn định giữa các phiên bản. Dùng event DTO nhỏ, có hợp đồng riêng.

### Lỗi 6: Xử lý tác vụ dài trong onMessage

Listener có thể bị nghẽn, làm tăng độ trễ các thông điệp sau. Thiết kế handler ngắn và giới hạn tài nguyên; nếu cần hàng đợi có retry, Pub/Sub thuần túy không đủ.

### Lỗi 7: Giả định mỗi sự kiện chỉ có một consumer

Với nhiều instance cùng subscribe, mỗi instance có thể xử lý cùng sự kiện. Nếu tác dụng phụ không được lặp, cần phương án phân công công việc/chống lặp riêng.

### Lỗi 8: Không có cơ chế khi subscriber offline

Message phát lúc listener mất kết nối sẽ không được phát lại. Chọn loại thông điệp cho phép mất hoặc dùng Stream/queue bền vững.

### Lỗi 9: Dùng cùng tên kênh cho nhiều schema không tương thích

Subscriber có thể đọc sai định dạng. Dùng sự kiện có loại và phiên bản rõ ràng hoặc kênh chuyên biệt.

### Lỗi 10: Tin rằng cache invalidation luôn hoàn tất

Thông điệp làm mới cache có thể mất; TTL hoặc phiên bản dữ liệu giúp giới hạn rủi ro, nhưng yêu cầu nhất quán nghiêm ngặt cần thiết kế mạnh hơn.

### Lỗi 11: Dùng subscribe trong HTTP handler

Mở kết nối `SUBSCRIBE` trong từng request làm khó quản lý vòng đời và tài nguyên. Nên dùng `RedisMessageListenerContainer` được Spring quản lý.

### Lỗi 12: Bỏ qua bảo mật kênh

Tên channel dễ đoán không thay thế xác thực. Phân quyền publish/subscribe và giới hạn dữ liệu gửi ra cần được xem xét trong thiết kế.

## 14. Thực hành với Spring Boot và Redis CLI

### Bước 1: Khởi động Redis dành cho phát triển

Nếu Redis đang chạy tại `localhost:6379`, có thể dùng `redis-cli` để quan sát. Trong cấu hình Spring Boot 3.x, thông tin kết nối ví dụ:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Dự án cần có dependency Spring Data Redis tương ứng, ví dụ starter của Spring Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Ví dụ giả định ứng dụng Spring Boot đã có Jackson để dùng `ObjectMapper`.

### Bước 2: Mở subscriber thủ công

Terminal A:

```bash
redis-cli SUBSCRIBE app:products:changed
```

Terminal B:

```bash
redis-cli PUBLISH app:products:changed '{"eventId":"evt-1","productId":42,"version":7,"occurredAtEpochMillis":1762990000000}'
```

Terminal A thấy JSON được gửi. Sau đó dừng terminal A và publish một thông điệp khác. Khởi động lại terminal A: thông điệp vừa phát khi offline sẽ **không xuất hiện lại**.

### Bước 3: Dùng publisher Java

Chạy ứng dụng với `ProductChangedPublisher` được cấu hình. Từ một đường gọi có chủ đích (ví dụ command nội bộ hoặc bài kiểm tra tích hợp), thực hiện:

```java
Long subscribers = productChangedPublisher.publish(42L, 8L);
System.out.println(subscribers);
```

Nếu terminal A vẫn subscribe, nó có thể thấy JSON. Nếu bean `RedisMessageListenerContainer` của ứng dụng cũng hoạt động, `ProductChangedListener` sẽ nhận sự kiện và gọi `redis.delete("product:detail:v1:42")`.

### Bước 4: Quan sát subscriber và kênh

Terminal khác:

```redis
PUBSUB NUMSUB app:products:changed
PUBSUB CHANNELS app:products:*
```

Số subscription thay đổi khi các listener kết nối hoặc ngắt kết nối. Một số lượng subscriber lớn hơn 0 không chứng minh các handler hoàn thành tác vụ.

### Bước 5: Kiểm tra cache invalidation

Đặt một khóa dùng cho thử nghiệm:

```redis
SET product:detail:v1:42 "stale" EX 120
GET product:detail:v1:42
```

Sau khi phát sự kiện và listener chạy, kiểm tra:

```redis
EXISTS product:detail:v1:42
```

Nếu listener đã xóa khóa, kết quả là `0`. Nếu chưa, cần kiểm tra kết nối subscriber, tên channel, serializer, lỗi JSON hoặc xử lý listener. Việc dùng Redis String `"stale"` chỉ nhằm quan sát thao tác xóa khóa; không phải một `ProductView` hợp lệ cho API đọc cache của ứng dụng.

### Bước 6: Thử khi không có subscriber

Dừng cả CLI subscriber và ứng dụng listener, rồi:

```redis
PUBLISH app:products:changed "event-while-offline"
```

Thông điệp này không được lưu để người nhận xử lý sau khi bật lại. Đây là tình huống thực hành quan trọng để phân biệt Pub/Sub với một message queue bền vững.

## 15. Câu hỏi tự kiểm tra

**1. `RedisTemplate.convertAndSend(channel, message)` làm gì?**

Nó chuyển nội dung thành byte theo serializer của template rồi phát lên kênh Pub/Sub. Người đang subscribe kênh phù hợp có thể nhận thông điệp.

**2. Gọi `convertAndSend` có tạo khóa Redis chứa thông điệp không?**

Không. Channel không phải khóa lưu giá trị; Pub/Sub không tự duy trì lịch sử.

**3. Publisher phát trước khi subscriber kết nối. Subscriber có nhận lại được không?**

Không, với Redis Pub/Sub thông thường. Thông điệp được gửi cho những subscriber đang hoạt động tại thời điểm phát.

**4. Vì sao nên dùng `StringRedisTemplate` với chuỗi JSON trong ví dụ?**

Vì đường đi của payload và định dạng byte rõ ràng: object Java được `ObjectMapper` biến thành JSON, rồi `StringRedisTemplate` phát chuỗi UTF-8.

**5. `convertAndSend` trả số người nhận bằng 2 có nghĩa cả hai handler đã xử lý xong không?**

Không. Nó phản ánh số subscriber được Redis tính là nhận ở mức Pub/Sub, không phải ACK nghiệp vụ.

**6. Tại sao subscriber nên dùng `RedisMessageListenerContainer`?**

Container giúp Spring quản lý kết nối subscribe và vòng đời listener, phù hợp với một đăng ký lâu dài thay vì mở kết nối mới mỗi request.

**7. Nếu hai instance cùng đăng ký một kênh, có thể cả hai cùng xử lý sự kiện không?**

Có. Pub/Sub phát tới từng subscriber đang đăng ký; nó không tự chia công việc sao cho chỉ một instance xử lý.

**8. Phát sự kiện trước khi database commit có rủi ro gì?**

Subscriber có thể phản ứng và đọc dữ liệu nguồn khi bản cập nhật chưa commit, dẫn đến xử lý dựa trên trạng thái cũ.

**9. `@TransactionalEventListener(AFTER_COMMIT)` có bảo đảm sự kiện sẽ được gửi dù ứng dụng chết sau commit không?**

Không. Nó xác định thời điểm callback nhưng không lưu bền vững việc gửi. Cần outbox hoặc cơ chế khác nếu không được mất sự kiện.

**10. Khi nào nên cân nhắc Redis Streams thay vì Pub/Sub?**

Khi consumer phải đọc lại thông điệp sau khi offline, cần theo dõi xử lý, có cơ chế ACK/retry hoặc cần giới hạn mất dữ liệu theo yêu cầu nghiệp vụ.

## 16. Ghi nhớ

- **`RedisTemplate.convertAndSend(...)`** là API Spring Data Redis để gửi thông điệp tới một channel Pub/Sub. `StringRedisTemplate` phù hợp để phát chuỗi hoặc JSON đã được chuyển thành chuỗi.
- **Serializer là hợp đồng dữ liệu.** Publisher và subscriber phải thống nhất cách mã hóa/giải mã payload, không mặc định Redis tự hiểu object Java.
- **`RedisMessageListenerContainer`** quản lý đăng ký kênh và chuyển thông điệp tới `MessageListener`. Một channel có thể được nhiều subscriber cùng lắng nghe.
- **Pub/Sub là phát trực tiếp, không lưu lịch sử/ACK/retry.** Số subscriber do `PUBLISH` hoặc `convertAndSend` trả về không phải số tác vụ nghiệp vụ thành công.
- **Phát sau commit** giúp tránh subscriber đọc dữ liệu chưa cập nhật, nhưng không tự tạo bảo đảm phát bền vững. Với tác vụ không được mất, cần Redis Streams/queue hoặc outbox phù hợp.
- Nên dùng Pub/Sub cho **tín hiệu tức thời, cập nhật giao diện hoặc cache invalidation có cơ chế phục hồi**, đồng thời theo dõi lỗi kết nối, lỗi payload và xử lý phía listener.

### Tài liệu tham khảo

- [Spring Data Redis — Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/).
- [Redis — PUBLISH](https://redis.io/docs/latest/commands/publish/).
- [Redis — SUBSCRIBE](https://redis.io/docs/latest/commands/subscribe/).
- [Redis — PUBSUB NUMSUB](https://redis.io/docs/latest/commands/pubsub-numsub/).
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/).

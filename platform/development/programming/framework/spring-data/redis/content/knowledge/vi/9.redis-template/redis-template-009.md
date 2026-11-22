# Chia sẻ Template giữa nhiều luồng và giữ cấu hình ổn định

Trong ứng dụng Spring Boot, nhiều HTTP request, scheduled job và message consumer có thể cùng thao tác Redis qua một bean `RedisTemplate` hoặc `StringRedisTemplate`. Một câu hỏi thường gặp là: **có nên tạo một `RedisTemplate` cho mỗi request để tránh tranh chấp giữa các luồng không?**

Với Spring Data Redis, **`RedisTemplate` được thiết kế để có thể dùng chung giữa các luồng sau khi đã cấu hình và khởi tạo hoàn tất**. Cách sử dụng thông thường là tạo template một lần dưới dạng Spring singleton bean, inject vào nhiều service và gọi các phương thức thao tác Redis từ nhiều thread.

Nhưng kết luận đó có những ranh giới rõ ràng:

- **Template dùng chung được; cấu hình của template phải ổn định** trong lúc ứng dụng đang sử dụng.
- **Không đồng nghĩa mọi đối tượng liên quan đều thread-safe**: `RedisConnection`, callback, đối tượng Java được serialize và các state tùy biến vẫn có thể gây race condition.
- **An toàn của template không đảm bảo tính nguyên tử cho chuỗi lệnh nghiệp vụ**. Hai thread cùng gọi `GET` rồi `SET` vẫn có thể làm mất cập nhật.
- **Kết nối và pool thuộc `RedisConnectionFactory`/driver**. Không cần tạo template theo từng request chỉ vì có nhiều request đồng thời.

Bài học này giải thích vòng đời template, phạm vi có thể chia sẻ, cách giữ serializer/connection factory nhất quán và những mẫu thiết kế đúng trong Spring Data Redis.

## 1. Đặt `RedisTemplate` đúng vị trí trong kiến trúc

Đường đi của một thao tác như `redis.opsForValue().get(key)`:

~~~text
Request A ----> ProductService ----\
                                    \
Request B ----> OrderService --------> RedisTemplate singleton
                                    /          |
Scheduled job ---------------------/           v
                                      RedisConnectionFactory
                                               |
                                        Lettuce hoặc Jedis
                                               |
                                        Redis server
~~~

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm | Cách sử dụng với nhiều luồng |
|---|---|---|
| `RedisTemplate<K,V>` | Biết connection factory, serializers và nhóm thao tác Redis | **Chia sẻ sau khi cấu hình hoàn tất** |
| `StringRedisTemplate` | Template chuyên cho key/value dạng chuỗi | **Chia sẻ sau khi cấu hình hoàn tất** |
| `ValueOperations`, `HashOperations`, ... | Các API gọi lệnh qua template | Dùng theo ngữ cảnh key/value; tránh lưu state nghiệp vụ mutable chung |
| `RedisConnectionFactory` | Cấp kết nối cho từng lần thực hiện thao tác | Thường là singleton, chịu trách nhiệm phối hợp với driver |
| `RedisConnection` | Thao tác qua connection được cấp, có thể gắn với transaction/pipeline | **Không giữ lại để tự gọi đồng thời giữa các thread** |
| Native Lettuce/Jedis client | Quản lý giao thức, socket, reconnect và topology | Quy tắc dùng chung phụ thuộc driver/loại connection |
| Serializer | Chuyển key/value giữa Java object và byte[] | Phải đủ an toàn khi gọi đồng thời và cấu hình nhất quán |
| Đối tượng nghiệp vụ `V` | Dữ liệu cụ thể để serialize/deserialize | Không tự trở nên thread-safe nhờ template |

**Cần phân biệt chia sẻ template và chia sẻ một connection raw.** Template là API cấp cao có lifecycle do Spring quản lý. Nó lấy/trả connection theo cơ chế của Spring Data Redis và connection factory; việc service giữ một connection cụ thể rồi dùng từ nhiều thread là một vấn đề khác.

## 2. Vì sao `RedisTemplate` có thể là singleton?

`RedisTemplate` thường chứa các tham chiếu cấu hình như:

- `RedisConnectionFactory` để truy cập Redis;
- key/value serializers và hash key/value serializers;
- cấu hình default serializer, transaction support và các lựa chọn thực thi;
- các implementation của nhóm thao tác như `opsForValue()`, `opsForHash()`, `opsForSet()`.

Khi thực hiện `get`, `set`, `increment` hoặc `hGet`, template **không cần sửa các tham chiếu cấu hình này**. Nó chuyển dữ liệu sang byte, thực hiện lệnh qua kết nối được factory cấp, đọc phản hồi và chuyển trở lại kiểu Java.

Điều đó cho phép nhiều caller dùng cùng một template:

~~~text
                  +--> Thread 1: GET product:101
                  |
RedisTemplate ----+--> Thread 2: SET product:102
                  |
                  +--> Thread 3: INCR counter:requests
                  |
                  +--> Thread 4: HGET user:7 name
~~~

Các lệnh có thể được gửi ở thời điểm gần nhau. Redis server xử lý từng lệnh theo đặc tính của Redis, còn driver thực hiện multiplexing hoặc quản lý các kết nối thực tế theo thiết kế của nó.

Trong một ứng dụng Spring Boot thông thường, `@Bean` tạo ra bean có scope **singleton** mặc định. Nếu hai service cùng inject bean đó, cả hai nhận cùng một đối tượng template. Đây chính là cách dùng dự kiến.

### 2.1. Thread-safe sau khi cấu hình khác với “mọi setter gọi lúc nào cũng được”

Template hỗ trợ dùng đồng thời **sau khi khởi tạo**. Không được suy rộng rằng vừa gọi lệnh Redis vừa thay `setValueSerializer`, `setConnectionFactory` hoặc cấu hình transaction là an toàn.

Những setter cấu hình nên được gọi trong lúc tạo bean, trước khi bất kỳ request nào có thể dùng template. Sau đó, chỉ gọi các API thao tác dữ liệu:

~~~text
Giai đoạn khởi tạo:
    new RedisTemplate<>()
    -> setConnectionFactory(...)
    -> setKeySerializer(...)
    -> setValueSerializer(...)
    -> Spring hoàn tất lifecycle của bean

Giai đoạn chạy:
    Service A/B/C cùng gọi opsForValue/opsForHash/...
    -> KHÔNG sửa cấu hình template
~~~

Đây là nguyên tắc “**configure once, use many times**”.

### 2.2. Công việc của Spring ở giai đoạn khởi tạo

`RedisTemplate` triển khai lifecycle của Spring, bao gồm việc thiết lập các thành phần nội bộ khi bean được khởi tạo. Khi khai báo qua `@Bean`, Spring gọi lifecycle callback thích hợp trước khi bean được đưa vào sử dụng bình thường.

Vì vậy không cần gọi `afterPropertiesSet()` trong từng service hay từng request. Nếu tự tạo một template bằng `new RedisTemplate<>()` ở ngoài Spring container, người viết mã phải chủ động đảm bảo nó được cấu hình và khởi tạo đúng theo API/lifecycle.

Đối tượng template đã được khởi tạo cũng cần được **công bố an toàn** cho các thread khác. Spring singleton bean được tạo và inject qua container chính là một cơ chế quản lý lifecycle thích hợp. Không lưu template đang cấu hình dở vào một biến global để các thread dùng ngay.

## 3. Khai báo một template dùng chung trong Spring Boot

Ví dụ minh họa một template JSON có kiểu đích cố định. Ứng dụng có model cache:

~~~java
package com.example.redisexample;

public record ProductCache(
        String id,
        String title,
        long priceInCents) {
}
~~~

Cấu hình một bean dùng lại trong nhiều service (ví dụ API của Spring Data Redis 3.x, Jackson 2):

~~~java
package com.example.redisexample;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisCacheConfiguration {

    @Bean("productCacheTemplate")
    public RedisTemplate<String, ProductCache> productCacheTemplate(
            RedisConnectionFactory connectionFactory,
            ObjectMapper objectMapper) {

        RedisTemplate<String, ProductCache> template =
                new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(
                        objectMapper, ProductCache.class));

        // Cấu hình tại thời điểm tạo bean.
        // Spring hoàn tất initialization trước khi service sử dụng.
        return template;
    }
}
~~~

Hai service có thể inject **cùng bean**:

~~~java
package com.example.redisexample;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheWriter {
    private final RedisTemplate<String, ProductCache> redis;

    public ProductCacheWriter(
            @Qualifier("productCacheTemplate")
            RedisTemplate<String, ProductCache> redis) {
        this.redis = redis;
    }

    public void put(ProductCache product) {
        redis.opsForValue().set(
                key(product.id()), product, Duration.ofMinutes(15));
    }

    private String key(String productId) {
        return "product:cache:" + productId;
    }
}

@Service
public class ProductCacheReader {
    private final RedisTemplate<String, ProductCache> redis;

    public ProductCacheReader(
            @Qualifier("productCacheTemplate")
            RedisTemplate<String, ProductCache> redis) {
        this.redis = redis;
    }

    public ProductCache get(String productId) {
        return redis.opsForValue()
                .get("product:cache:" + productId);
    }
}
~~~

Hai service đều giữ tham chiếu `final` tới bean được cấu hình từ trước. Dù nhiều request cùng chạy `put` và `get`, **không có request nào tự sửa cấu hình serializer hoặc factory**.

Các lớp `ProductCacheWriter` và `ProductCacheReader` cũng là singleton service thông thường. Việc một service là singleton không gây lỗi nếu service chỉ giữ các dependency dùng chung phù hợp và biến cục bộ theo từng lời gọi. Lỗi sẽ xuất hiện khi service giữ **trạng thái request mutable trong field** (ví dụ `currentProductId`) rồi nhiều luồng cùng sửa.

### 3.1. Nếu chỉ cần chuỗi: ưu tiên `StringRedisTemplate`

Với key và value đều là chuỗi, Spring Boot thường tự cấu hình `StringRedisTemplate` từ Redis starter và `RedisConnectionFactory`.

~~~java
package com.example.redisexample;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ApiCounterService {
    private final StringRedisTemplate redis;

    public ApiCounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long increment(String apiName) {
        Long count = redis.opsForValue()
                .increment("metrics:api:" + apiName);

        if (count == null) {
            throw new IllegalStateException("Redis counter returned null");
        }

        return count;
    }
}
~~~

`StringRedisTemplate` cũng là template dùng chung sau khi cấu hình hoàn tất. Không cần tạo instance mới chỉ vì `increment` có thể được 100 request gọi gần như đồng thời. Một lệnh Redis `INCR`/tương đương do `increment()` thực hiện có tính nguyên tử ở cấp lệnh.

## 4. Những đối tượng nào không nên chia sẻ tùy tiện?

Có thể tưởng tượng hệ thống như sau:

~~~text
Shared singleton:
    RedisTemplate
        |
        +---- RedisConnectionFactory
                    |
                    +---- Connection A (request/transaction context)
                    +---- Connection B (request/transaction context)
                    +---- Shared native connection nếu driver cho phép
~~~

An toàn của template **không được kế thừa vô điều kiện** bởi mọi object lấy từ nó.

### 4.1. Không giữ `RedisConnection` trong field service

Ví dụ thiết kế không nên áp dụng:

~~~java
// Không nên: lưu một RedisConnection để nhiều request cùng dùng.
@Service
public class UnsafeRedisService {
    private final RedisConnection connection;

    public UnsafeRedisService(RedisConnectionFactory factory) {
        this.connection = factory.getConnection();
    }

    // Nhiều thread có thể gọi cùng connection,
    // không có lifecycle borrow/release rõ ràng.
}
~~~

Đoạn này có nhiều vấn đề:

- `RedisConnection` không phải abstraction được khuyến nghị để tự chia sẻ tùy ý giữa thread.
- Connection có thể chứa trạng thái session, transaction hoặc pipeline.
- Không thấy cơ chế `close`/trả connection đúng thời điểm.
- Nếu server reconnect, connection được service giữ có thể không tuân theo lifecycle do template/factory dự kiến.

Tốt hơn:

~~~java
@Service
public class SafeRedisService {
    private final StringRedisTemplate redis;

    public SafeRedisService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String load(String id) {
        return redis.opsForValue().get("item:" + id);
    }
}
~~~

Khi cần lệnh thấp cấp, dùng `RedisTemplate.execute(RedisCallback)` trong phạm vi callback và không để connection thoát ra ngoài callback:

~~~java
Long result = stringRedisTemplate.execute(connection ->
        connection.serverCommands().dbSize());
~~~

Callback này chỉ minh họa cách lấy số key trong database qua `RedisConnection` hiện tại; không lưu `connection` vào field, static variable hay hàng đợi để một thread khác dùng về sau.

### 4.2. Không dùng chung state mutable của từng request

Một singleton service có field mutable:

~~~java
@Service
public class UnsafeKeyService {
    private final StringRedisTemplate redis;
    private String currentKey;

    public UnsafeKeyService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String read(String id) {
        currentKey = "user:" + id;   // Thread khác có thể ghi đè.
        return redis.opsForValue().get(currentKey);
    }
}
~~~

Khi thread A đặt `currentKey=user:A`, thread B có thể đổi thành `user:B` trước khi A gọi `get`. A có thể đọc sai dữ liệu. Đây là race condition trong **service**, không phải của template.

Viết lại bằng biến cục bộ:

~~~java
public String read(String id) {
    String key = "user:" + id;
    return redis.opsForValue().get(key);
}
~~~

Không có biến dùng chung bị sửa giữa các request.

### 4.3. Đối tượng `V` khi được serialize cũng phải có trạng thái hợp lệ

Giả sử hai thread chia sẻ một `ArrayList` mutable và một thread thay đổi phần tử trong khi thread kia đang serialize object chứa list đó. Dữ liệu JSON thu được có thể phản ánh trạng thái không nhất quán hoặc phát sinh ngoại lệ.

`RedisTemplate` không khóa đối tượng Java cho bạn. Dùng DTO bất biến khi phù hợp (`record`, các value object), tạo snapshot trước khi ghi, hoặc đồng bộ quyền truy cập vào đối tượng mutable theo nhu cầu.

### 4.4. `Bound*Operations` có thể giữ khóa đã bind

Spring Data Redis có các API như `boundValueOps(key)`, `boundHashOps(key)`. Các đối tượng này gắn với **một key cụ thể**.

~~~java
var cartOps = stringRedisTemplate.boundHashOps("cart:user-42");
cartOps.put("product-7", "2");
~~~

Chúng có thể hữu ích để thao tác nhiều lần với một key. Nhưng không nên lưu `cartOps` trong một singleton rồi mong nó tự đại diện cho giỏ hàng của mọi request: key `cart:user-42` đã được bind từ đầu.

Trong service multi-user, có thể tạo bound operation theo key cục bộ trong từng method:

~~~java
public void addToCart(String userId, String productId, String quantity) {
    String key = "cart:" + userId;
    redis.boundHashOps(key).put(productId, quantity);
}
~~~

Việc dùng bound operations có hay không không làm thay đổi nguyên tắc: **khóa và trạng thái nghiệp vụ của request phải được lựa chọn theo từng request**.

## 5. “Giữ cấu hình ổn định” bao gồm những thuộc tính nào?

Sau khi template đã được đưa vào sử dụng, không tùy ý gọi lại:

| Cấu hình | Ví dụ setter/thao tác | Vì sao phải cố định |
|---|---|---|
| Redis endpoint/factory | `setConnectionFactory(...)` | Đổi đích giữa hai lệnh có thể khiến dữ liệu đi tới hai Redis khác nhau |
| Key serializer | `setKeySerializer(...)` | Cùng key logic có thể trở thành chuỗi byte khác |
| Value serializer | `setValueSerializer(...)` | Dữ liệu ghi mới có thể không đọc được bằng serializer cũ |
| Hash key/value serializer | `setHashKeySerializer(...)`, `setHashValueSerializer(...)` | Cấu trúc Hash có thể không tương thích giữa writer/reader |
| Default serializer | `setDefaultSerializer(...)` | Ảnh hưởng serializer được dùng khi chưa đặt rõ vị trí |
| Enable default serializer | `setEnableDefaultSerializer(...)` | Thay đổi cách xử lý serializer null/chưa đặt |
| Transaction support | `setEnableTransactionSupport(...)` | Thay đổi cách connection được gắn với transaction/thread |
| Cấu hình execute/behavior khác | Các thuộc tính của template/factory | Có thể ảnh hưởng đồng thời đến các luồng đang hoạt động |

Không nên gọi các setter này bên trong controller, `@Scheduled`, một callback hoặc phương thức xử lý request.

### 5.1. Ví dụ lỗi: đổi serializer theo từng request

Giả sử ứng dụng muốn dùng hai định dạng JSON khác nhau:

~~~java
// Không nên: template singleton dùng chung bị thay serializer.
public void saveAsDifferentFormat(String key, Object value) {
    sharedTemplate.setValueSerializer(alternateSerializer);
    sharedTemplate.opsForValue().set(key, value);
}
~~~

Thread A chọn serializer X, thread B đổi thành Y ngay trước khi A thực thi `set`. Dữ liệu được lưu theo định dạng không dự kiến. Khi đọc, deserializer có thể lỗi hoặc ánh xạ sai đối tượng.

**Cách đúng:** khai báo hai template độc lập, mỗi template có serializer được cấu hình cố định; hoặc dùng một schema thống nhất cho cùng một namespace key.

~~~text
Bean A: orderCacheTemplate   -> JSON OrderCache, key order-cache:...
Bean B: metricsTemplate      -> String, key metrics:...
          |
          +-- Cả hai có thể dùng cùng RedisConnectionFactory
~~~

Việc có nhiều template **được cấu hình cố định** khác với việc thay đổi cấu hình một template được chia sẻ tại runtime.

### 5.2. Ví dụ khai báo nhiều template có qualifier

~~~java
@Configuration
public class CacheTemplatesConfig {

    @Bean("metricsTemplate")
    public StringRedisTemplate metricsTemplate(
            RedisConnectionFactory factory) {
        return new StringRedisTemplate(factory);
    }

    @Bean("orderCacheTemplate")
    public RedisTemplate<String, OrderCache> orderCacheTemplate(
            RedisConnectionFactory factory,
            ObjectMapper mapper) {

        RedisTemplate<String, OrderCache> template =
                new RedisTemplate<>();
        template.setConnectionFactory(factory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(
                        mapper, OrderCache.class));
        return template;
    }
}
~~~

Trong ví dụ trên, `OrderCache` là DTO do ứng dụng định nghĩa. `metricsTemplate` dành cho chuỗi, còn `orderCacheTemplate` dành cho giá trị kiểu `OrderCache`. Cả hai có thể chia sẻ connection factory mà vẫn giữ serialization contract độc lập.

Nếu dự án đã có `StringRedisTemplate` do Spring Boot tự cấu hình, **không cần tạo thêm bean cùng mục đích một cách vô ý**. Ví dụ này trình bày trường hợp chủ động quản lý nhiều template; khi đưa vào dự án thật, cần xem bean nào đã tồn tại và dùng `@Qualifier` nếu có nhiều bean cùng type.

### 5.3. Cấu hình serializer phải đồng nhất giữa nhiều phiên bản ứng dụng

Ngay cả khi một template không bao giờ bị mutate trong runtime, service A và service B vẫn có thể dùng hai cấu hình khác nhau cho cùng key.

Ví dụ:

~~~text
Service phiên bản 1:
    key: user:42
    value: JDK serialized bytes

Service phiên bản 2:
    key: user:42
    value: JSON bytes
~~~

Hai template đều “ổn định” trên từng JVM, nhưng hệ thống không có hợp đồng dữ liệu thống nhất. Khi triển khai cuốn chiếu, service cũ có thể không đọc được value do service mới ghi.

Cần quản lý serializer, encoding, tên key, field schema, metadata kiểu, TTL và quy trình migration như một **hợp đồng lưu trữ**. Có thể tách namespace `user-cache:v1:42` và `user-cache:v2:42` trong giai đoạn chuyển đổi hoặc thiết kế format đọc tương thích nếu cần.

## 6. Serializer có thật sự thread-safe không?

Template có thể được gọi đồng thời, nghĩa là cùng một serializer instance có thể bị nhiều thread gọi `serialize`/`deserialize`.

Các serializer chuẩn của Spring Data Redis được thiết kế cho kiểu sử dụng này theo cơ chế tương ứng. Tuy nhiên, một **serializer tự viết** có thể phá hỏng khả năng dùng chung của template nếu nó lưu state tạm vào field không được bảo vệ.

Ví dụ nên tránh:

~~~java
// Ý tưởng minh họa lỗi: giữ một buffer mutable chung.
class UnsafeExampleSerializer {
    private final StringBuilder scratch = new StringBuilder();

    byte[] serialize(String value) {
        scratch.setLength(0);
        scratch.append(value);
        return scratch.toString().getBytes(
                java.nio.charset.StandardCharsets.UTF_8);
    }
}
~~~

Hai thread có thể xen kẽ các lệnh `setLength`/`append` trên cùng `scratch`, tạo byte sai.

Một cách triển khai an toàn hơn là đặt state tạm trong method:

~~~java
byte[] serialize(String value) {
    return value.getBytes(
            java.nio.charset.StandardCharsets.UTF_8);
}
~~~

Khi viết serializer thực tế, cần xử lý `null`, lỗi encoding và hợp đồng của `RedisSerializer<T>`, không chỉ chuyển chuỗi sang byte.

### 6.1. Với Jackson `ObjectMapper`

`ObjectMapper` thường an toàn để đọc/ghi đồng thời **nếu toàn bộ cấu hình được hoàn tất trước lần sử dụng đầu tiên**. Không nên vừa serialize/deserialize qua mapper vừa đăng ký module, thay feature, subtype hoặc default typing của chính mapper đó.

Nếu cần hai chính sách JSON khác nhau, tạo hai mapper hoặc serializer với cấu hình được hoàn thiện trước khi chia sẻ.

~~~text
Tạo mapper A -> cấu hình A -> serializer A -> template A -> sử dụng
Tạo mapper B -> cấu hình B -> serializer B -> template B -> sử dụng
~~~

Đặc biệt chú ý với serializer có type metadata: nếu một service cấu hình allowlist subtype còn service khác bật default typing khác, cùng JSON payload có thể được khôi phục thành kiểu khác hoặc bị từ chối. Đây là vấn đề **tính nhất quán cấu hình**, không chỉ an toàn luồng.

### 6.2. DTO Java cũng cần hợp đồng ổn định

Với Redis cache lâu sống hơn một vòng deploy, khi refactor DTO cần cân nhắc:

- Field được thêm/xóa/đổi tên.
- `record`/constructor yêu cầu những property nào.
- Các subtype đa hình được phép khôi phục.
- Kiểu số, ngày giờ, enum và chiến lược null.
- Thời hạn giữ cache và khả năng đọc dữ liệu cũ.

Tính thread-safe của template không giúp khắc phục dữ liệu đã lưu bằng một schema không tương thích.

## 7. Template singleton không làm chuỗi nhiều lệnh trở thành atomic

Giả sử hai luồng cùng tăng số lượt xem theo mẫu:

~~~java
// Không nên: đọc rồi ghi không nguyên tử.
public void incrementUnsafe(String key) {
    String raw = redis.opsForValue().get(key);
    long current = raw == null ? 0 : Long.parseLong(raw);
    redis.opsForValue().set(key, Long.toString(current + 1));
}
~~~

Diễn biến có thể là:

~~~text
Ban đầu: counter = 5

Thread A                      Thread B
--------                      --------
GET -> 5                      GET -> 5
tính 6                        tính 6
SET 6                         SET 6

Kết quả = 6, kỳ vọng = 7
~~~

Hai luồng sử dụng template đúng cách nhưng **thuật toán nghiệp vụ có lost update**.

Sử dụng lệnh nguyên tử Redis:

~~~java
public long incrementSafely(String key) {
    Long count = redis.opsForValue().increment(key);
    if (count == null) {
        throw new IllegalStateException("Counter unavailable");
    }
    return count;
}
~~~

`INCR` của Redis là nguyên tử ở cấp lệnh. Không cần `synchronized(redis)` chỉ để nhiều thread tăng một bộ đếm.

### 7.1. `synchronized` trên template thường không phải giải pháp đúng

~~~java
synchronized (redis) {
    String old = redis.opsForValue().get(key);
    redis.opsForValue().set(key, transform(old));
}
~~~

Khối `synchronized` chỉ tuần tự hóa các thread **trong cùng JVM** đang khóa trên đúng object. Nó không bảo vệ trước instance ứng dụng khác, microservice khác hoặc process khác truy cập Redis.

Hơn nữa, việc khóa toàn bộ template có thể làm chậm cả những key không liên quan. Khi cần thao tác nhiều bước, cân nhắc atomic command, Redis transaction, Lua script, optimistic locking (`WATCH`) hoặc cơ chế điều phối thích hợp với yêu cầu nghiệp vụ.

### 7.2. Kiểm soát tạo khóa chỉ một lần

Nếu muốn đặt giá trị ban đầu và TTL chỉ khi key chưa tồn tại, dùng lệnh có điều kiện:

~~~java
import java.time.Duration;

Boolean created = redis.opsForValue()
        .setIfAbsent("job:lock:42", "owner-abc", Duration.ofSeconds(30));
~~~

`setIfAbsent` với TTL tương ứng cơ chế đặt giá trị có điều kiện và thời hạn trong cùng một thao tác khi backend hỗ trợ. Nhưng đây mới chỉ là nền tảng cho lock đơn giản; để giải phóng khóa an toàn phải kiểm tra owner token bằng thao tác nguyên tử, xử lý timeout/gia hạn và tính đúng đắn nghiệp vụ. Template thread-safe không tự biến một khóa Redis thành distributed lock hoàn chỉnh.

### 7.3. Lệnh ghi bị timeout và tính đúng đắn của retry

Nếu hai thread cùng gọi `increment()`, Redis có thể xử lý cả hai lệnh đúng. Tuy nhiên, nếu mạng mất sau khi Redis đã thực thi mà trước khi client nhận reply, retry `INCR` có thể tăng hai lần cho **một sự kiện nghiệp vụ**.

Phân biệt:

- **Atomicity:** một lệnh Redis không bị xen kẽ ở giữa các bước của chính lệnh đó.
- **Thread safety:** nhiều thread có thể dùng chung template mà không làm hỏng state nội bộ template.
- **Idempotency:** lặp lại một yêu cầu nghiệp vụ có gây thêm hiệu ứng hay không.
- **Consistency:** dữ liệu đọc/ghi có đáp ứng bất biến nghiệp vụ giữa nhiều key hoặc nhiều hệ thống hay không.

Bốn khái niệm liên quan nhưng không thay thế nhau.

## 8. Transaction trong Spring Data Redis và ranh giới thread

Redis hỗ trợ `MULTI`, `EXEC` và `WATCH` cho những tình huống cần nhóm lệnh hoặc optimistic locking. Spring Data Redis cung cấp `SessionCallback` để những lời gọi liên quan sử dụng cùng ngữ cảnh kết nối.

Ví dụ nhóm hai lệnh trong một Redis transaction:

~~~java
import java.util.List;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public List<Object> incrementTwoCounters(StringRedisTemplate redis) {
    return redis.execute(new SessionCallback<List<Object>>() {
        @Override
        @SuppressWarnings({ "rawtypes", "unchecked" })
        public List<Object> execute(RedisOperations operations) {
            operations.multi();
            operations.opsForValue().increment("counter:a");
            operations.opsForValue().increment("counter:b");
            return operations.exec();
        }
    });
}
~~~

Trong ví dụ trên, `SessionCallback` giữ các thao tác trong cùng session do Spring Data Redis quản lý; `multi()` bắt đầu Redis transaction và `exec()` yêu cầu thực thi lệnh đã xếp hàng. Các kết quả lệnh nằm trong list trả về sau `EXEC`.

**Những giới hạn cần nhớ:**

- Redis transaction không cung cấp rollback như một transaction database quan hệ; lệnh lỗi tại lúc thực thi có những quy tắc riêng và không kéo theo rollback các lệnh khác đã thành công.
- Không đưa `RedisOperations` hay `RedisConnection` đang ở transaction/session ra khỏi callback để thread khác sử dụng.
- Một transaction dùng nhiều connection độc lập sẽ không có cùng ý nghĩa như một `MULTI/EXEC` trên một connection.
- Khi cần optimistic lock, `WATCH` phải nằm trong cùng session phù hợp; không giả định tự động có `WATCH` chỉ vì gọi template trong synchronized block.

### 8.1. `setEnableTransactionSupport(true)` cần cấu hình từ trước

Spring Data Redis có tùy chọn hỗ trợ gắn Redis connection vào Spring-managed transaction khi được bật. Một cách cấu hình (ở giai đoạn tạo bean):

~~~java
@Bean("transactionalRedisTemplate")
public StringRedisTemplate transactionalRedisTemplate(
        RedisConnectionFactory factory) {

    StringRedisTemplate template = new StringRedisTemplate(factory);
    template.setEnableTransactionSupport(true);
    return template;
}
~~~

Tùy chọn này **không nên bật/tắt theo từng request trên một singleton template**. Khi được sử dụng với transaction phù hợp, Spring có thể bind connection vào thread và cần release ở đúng điểm kết thúc transaction.

Trong luồng xử lý có `@Transactional`:

- Một số thao tác ghi Redis có thể được queue cho tới giai đoạn commit của transaction.
- Thao tác đọc có thể sử dụng connection khác để đọc dữ liệu đã commit theo semantics của Redis/Spring Data.
- Giữ connection lâu có thể gây áp lực lên pool nếu transaction kéo dài.
- Redis không tự trở thành một resource XA có rollback atomically cùng database quan hệ.

Nếu công việc nhảy qua thread khác (`@Async`, `CompletableFuture` hoặc executor), đừng tự giả định thread-bound transaction context được truyền sang thread mới. Bởi vậy, **template singleton dùng được đa luồng** không có nghĩa **transaction state được phép chia sẻ giữa các luồng**.

### 8.2. Pipeline cũng gắn với phạm vi callback

Pipelining giúp giảm round-trip khi gửi nhiều lệnh. Spring Data Redis có các API như `executePipelined(...)` và `SessionCallback`.

Pipelining không đảm bảo transaction semantics. Các lệnh được gửi theo pipeline vẫn cần xem xét tính nguyên tử, thứ tự và khả năng đọc kết quả đúng. Không lưu một connection đang bật pipeline vào singleton và dùng chung giữa các request khác nhau.

Nếu cần pipeline, hãy dùng API cấp cao giữ connection trong **phạm vi callback** thay vì tự bật/tắt pipeline trên một connection chia sẻ không kiểm soát.

## 9. Lettuce và Jedis ảnh hưởng thế nào tới việc chia sẻ template?

Hai driver phổ biến của Spring Data Redis có đặc điểm kết nối khác nhau.

| Khía cạnh | Lettuce | Jedis |
|---|---|---|
| `RedisTemplate` đã cấu hình | Có thể chia sẻ | Có thể chia sẻ |
| Native connection thông thường | Có thể được chia sẻ bởi nhiều luồng theo thiết kế của Lettuce trong các điều kiện phù hợp | Không nên tùy ý chia sẻ một `Jedis` connection giữa nhiều thread |
| Pooling | Tùy loại workload và nhu cầu connection riêng | Thường cần cho nhiều request đồng thời |
| Transaction/Blocking/Connection state | Cần chú ý các connection riêng và điều kiện sử dụng | Cần mượn/trả connection và đảm bảo session không rò rỉ |
| Reactive Spring Data Redis | Hỗ trợ | Không dùng như reactive factory trong tích hợp Spring Data Redis thông thường |

Với `LettuceConnectionFactory`, các thao tác bình thường có thể tận dụng native connection được chia sẻ, nhưng Spring Data Redis vẫn cung cấp abstraction `RedisConnection` và xử lý theo lifecycle của nó. Không nên lấy một connection từ factory và cho nhiều thread trực tiếp dùng chỉ vì “Lettuce là thread-safe”.

Với `JedisConnectionFactory`, template vẫn có thể là singleton vì factory chịu trách nhiệm cung cấp connection theo quy tắc sử dụng của Jedis và pool. Không tạo một `RedisTemplate` mới cho mỗi thread để thay thế vai trò của pool.

### 9.1. Phân biệt số template, số connection và số request

~~~text
200 request đồng thời
        |
        v
1 StringRedisTemplate singleton
        |
        v
1 RedisConnectionFactory
        |
        v
Driver quản lý 1 hoặc nhiều native connections theo workload
        |
        v
Redis
~~~

Không có công thức “200 request = 200 RedisTemplate = 200 connection”. Số native connection phù hợp phụ thuộc driver, các lệnh blocking/transaction, giới hạn pool, độ trễ và lượng request thật.

Nếu Redis chậm hoặc pool bị cạn, tạo thêm nhiều template singleton có thể khiến số đối tượng trong JVM tăng mà không giải quyết nguyên nhân. Cần đo pool wait time, timeout, Redis latency và số concurrent commands.

### 9.2. Khi connection hỏng hoặc Redis restart

Một template singleton không nhất thiết trở nên vô dụng sau khi một socket chết. Driver/factory có thể reconnect hoặc tạo connection mới, tùy cấu hình. Service cần xử lý các request đang thất bại, timeout và tính an toàn của retry.

Không xây lối xử lý “Redis timeout -> new RedisTemplate()” ở từng request. Cách đó tạo lifecycle rời rạc, dễ bỏ qua serializers/timeout đã chuẩn hóa và có thể làm tăng áp lực connection lên server.

## 10. ReactiveRedisTemplate và luồng phản ứng

`ReactiveRedisTemplate<K,V>` là abstraction dành cho Reactor `Mono`/`Flux`. Cũng nên cấu hình một lần và chia sẻ qua Spring bean, nhưng nó là API khác với `RedisTemplate` imperative.

~~~java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCounterService {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveCounterService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> increment(String apiName) {
        return redis.opsForValue()
                .increment("metrics:api:" + apiName);
    }
}
~~~

Hai request reactive có thể cùng subscribe và thực hiện lệnh qua cùng template đã cấu hình. Cần phân biệt:

- **Template được chia sẻ:** đối tượng dùng chung an toàn theo cách thiết kế.
- **Publisher:** mỗi subscription có ngữ cảnh chạy và tín hiệu kết quả/lỗi riêng.
- **State mutable trong pipeline:** nếu lambda giữ một collection/biến dùng chung mà nhiều subscriber cùng sửa, race condition vẫn xuất hiện.
- **Blocking:** gọi `StringRedisTemplate` trực tiếp trên WebFlux event loop có thể chặn thread; nên dùng reactive API khi cần luồng xử lý non-blocking.

Đừng dùng `ThreadLocal` để tự lưu trạng thái nghiệp vụ qua các bước của pipeline reactive, vì cùng một logical request có thể chuyển thread. Transaction reactive có cơ chế context riêng khi được hỗ trợ; không suy từ cơ chế imperative sang reactive.

## 11. Các lỗi thiết kế thường gặp trong ứng dụng nhiều luồng

### 11.1. Tạo template trong mỗi request

~~~java
public String readEveryRequest(String key,
                               RedisConnectionFactory factory) {
    RedisTemplate<String, String> template = new RedisTemplate<>();
    template.setConnectionFactory(factory);
    // Dễ thiếu serializer/lifecycle, lặp cấu hình từng request.
    return template.opsForValue().get(key);
}
~~~

Đoạn này vừa lặp cấu hình vừa dễ bỏ sót khởi tạo và serializers, khiến dữ liệu không khớp. Nên inject một bean template đã hoàn tất lifecycle.

### 11.2. Thay serializer ngay trước khi ghi

~~~java
sharedTemplate.setValueSerializer(serializerForCurrentUser);
sharedTemplate.opsForValue().set(key, value);
~~~

Một thread khác có thể đổi serializer trong thời gian thực thi. Khóa theo user/tenant không nên được giải quyết bằng thay serializer trên template singleton.

### 11.3. Để khóa hiện tại trong field singleton

~~~java
this.currentKey = "session:" + sessionId;
return redis.opsForValue().get(currentKey);
~~~

Field mutable có thể bị thread khác ghi đè. Dùng biến cục bộ `String key = ...` trong method.

### 11.4. Lưu raw connection vào static field

~~~java
static RedisConnection connection;
~~~

Connection có thể có state transaction/pipeline, không được quản lý lifetime/borrow/release, và có thể hỏng sau Redis restart. Dùng template hoặc callback ngắn hạn.

### 11.5. Khóa trên đối tượng template để làm transaction

~~~java
synchronized (redisTemplate) {
    // GET -> tính toán -> SET
}
~~~

Cách này chỉ đồng bộ các thread khóa cùng object trong cùng JVM. Nếu hệ thống triển khai nhiều instance, race condition giữa các instance vẫn còn. Dùng primitive nguyên tử của Redis hoặc transaction/script thích hợp.

### 11.6. Đổi `RedisConnectionFactory` khi ứng dụng đang chạy

~~~java
sharedTemplate.setConnectionFactory(newFactory);
~~~

Lệnh trước và sau thời điểm đổi có thể đi tới các Redis khác nhau; callback hoặc transaction đang xử lý có thể dựa trên giả định cũ. Nếu cần chuyển Redis endpoint/topology, thiết kế quy trình thay thế bean/configuration rõ ràng, kiểm chứng tính tương thích dữ liệu và để connection factory/driver hoàn tất lifecycle.

### 11.7. Truyền `SessionCallback` stateful được tái sử dụng đồng thời

Một `SessionCallback` có field mutable để tích lũy dữ liệu qua nhiều lần gọi có thể gây race nếu cùng instance được nhiều thread thực thi. Callback nên là stateless hoặc được tạo theo từng lời gọi và giữ state cục bộ.

## 12. Thiết kế đúng khi cần nhiều Redis hoặc nhiều tenant

Nếu một ứng dụng cần nói chuyện với hai Redis khác nhau, nên có cấu hình tách biệt:

~~~text
RedisConnectionFactory A ---- RedisTemplate A ---- cache products
RedisConnectionFactory B ---- RedisTemplate B ---- sessions
~~~

Đừng dùng một template rồi đổi `setConnectionFactory` theo tenant/request. Mỗi factory/template có endpoint, bảo mật và serializer ổn định.

Ví dụ phương thức chọn template từ danh sách đã được tạo trước:

~~~java
@Service
public class MultiCacheReader {
    private final RedisTemplate<String, String> primary;
    private final RedisTemplate<String, String> secondary;

    public MultiCacheReader(
            @Qualifier("primaryRedisTemplate")
            RedisTemplate<String, String> primary,
            @Qualifier("secondaryRedisTemplate")
            RedisTemplate<String, String> secondary) {
        this.primary = primary;
        this.secondary = secondary;
    }

    public String read(boolean useSecondary, String key) {
        RedisTemplate<String, String> selected =
                useSecondary ? secondary : primary;
        return selected.opsForValue().get(key);
    }
}
~~~

Hai bean `primaryRedisTemplate` và `secondaryRedisTemplate` phải được cấu hình từ trước bằng factory tương ứng. Việc chọn **tham chiếu template đã ổn định** theo request khác với việc mutate một template chung.

Nếu nhiều tenant dùng cùng Redis nhưng dữ liệu được phân tách bằng namespace, thường chỉ cần tạo key prefix theo lời gọi:

~~~java
public String readForTenant(String tenantId, String itemId) {
    String key = "tenant:" + tenantId + ":item:" + itemId;
    return redis.opsForValue().get(key);
}
~~~

Tuy nhiên, key prefix **không phải cơ chế cách ly bảo mật hoàn chỉnh**; cần kiểm soát tenant identity và quyền truy cập ở tầng ứng dụng. Nếu các tenant cần Redis credentials hoặc endpoint khác nhau, cấu hình factory/template riêng hoặc cơ chế quản lý client theo tenant rõ ràng sẽ phù hợp hơn.

## 13. Thay đổi cấu hình khi hệ thống đang chạy

Trong quá trình vận hành, đôi khi cần chuyển Redis endpoint, đổi serializer, thay định dạng cache hoặc thay timeout.

### 13.1. Đổi cấu hình khác với thay dữ liệu

Các thay đổi có thể chia thành:

| Loại thay đổi | Ví dụ | Cách ứng xử |
|---|---|---|
| Tham số kết nối | Host, TLS, auth, timeout | Tạo cấu hình/client/factory mới qua lifecycle được kiểm soát |
| Topology | Standalone -> Sentinel/Cluster | Dùng factory/driver hỗ trợ topology mới, kiểm tra routing |
| Serializer/schema | JDK -> JSON, đổi DTO | Thiết kế migration, key version, rollout tương thích |
| Quy ước key | `cache:user:...` -> `cache:v2:user:...` | Điều phối đọc/ghi giữa phiên bản cũ và mới |
| Logic nghiệp vụ | Cách tăng đếm, TTL, transaction | Đổi code service/command, cân nhắc dữ liệu cũ |

Việc sửa `application.yml` trên đĩa **không đảm bảo** bean singleton đang chạy tự reload cấu hình. Với Spring Boot mặc định, nhiều giá trị được bind vào bean khi khởi tạo. Muốn reload động phải có cơ chế quản lý lifecycle/refresh cụ thể và tránh cho request sử dụng template đang thay đổi dở.

### 13.2. Mẫu triển khai hai phiên bản

Ví dụ nâng schema cache:

~~~text
Phiên bản cũ:
    product-cache:v1:<id> -> JSON schema 1

Phiên bản mới:
    product-cache:v2:<id> -> JSON schema 2
~~~

Trong giai đoạn triển khai:

1. Khai báo serializer và namespace của phiên bản mới thành cấu hình riêng.
2. Các instance mới dùng template/serializer mới đã được khởi tạo hoàn chỉnh.
3. Cân nhắc đọc dữ liệu nguồn và tái tạo cache v2; dữ liệu v1 để hết TTL nếu phù hợp.
4. Theo dõi lỗi deserialization và cache hit/miss.
5. Loại bỏ code/schema cũ sau khi không còn reader phụ thuộc.

Kế hoạch này tốt hơn việc đổi serializer trên cùng template singleton giữa các request. Nếu Redis chứa dữ liệu quan trọng thay vì cache có thể tái tạo, cần migration có bảo đảm và rollback strategy phù hợp hơn.

### 13.3. Một DTO/serializer mới phải được xác thực trong hệ thống nhiều instance

Khi deploy rolling, có thể đồng thời tồn tại nhiều phiên bản service. Nếu hai phiên bản ghi cùng key theo format không tương thích, việc mỗi JVM giữ template cố định **vẫn chưa đủ**. Cần phối hợp phiên bản storage contract giữa các service.

## 14. Quan sát và xử lý vấn đề đồng thời

Khi hệ thống xuất hiện lỗi ngẫu nhiên dưới tải, không nên kết luận ngay “`RedisTemplate` không thread-safe”. Cần xác định chính xác tầng xảy ra lỗi.

| Triệu chứng | Nguyên nhân thường gặp | Hướng phân tích |
|---|---|---|
| Một request đọc nhầm key của request khác | Singleton service giữ mutable `currentKey`/state request | Kiểm tra field mutable và biến local |
| Deserialization lỗi ngẫu nhiên | Serializer bị thay runtime, mapper mutable, format writer/reader khác | Kiểm tra bean initialization, serializer config, schema |
| Giá trị counter thấp hơn kỳ vọng | Logic `GET` + `SET` gây lost update | Dùng atomic Redis command hoặc cơ chế concurrency phù hợp |
| Request Redis chậm theo đợt | Pool cạn, Redis latency, connection timeout | Đo active/idle/waiters, timing và server load |
| Lỗi khi Redis restart | Connection bị ngắt hoặc lệnh timeout | Xử lý reconnect, retry idempotent và fallback đúng |
| Transaction không đúng phạm vi | Connection/session/transaction state dùng sai thread | Dùng `SessionCallback` và transaction context phù hợp |
| Cache đột nhiên có format khác | Hai phiên bản service cấu hình serializer khác nhau | Thống nhất storage contract và rollout |
| Lỗi giữa nhiều tenant | Template/factory thay endpoint runtime hoặc key prefix sai | Tách bean theo endpoint, tính key trong request |
| Kết nối tăng bất thường | Tạo factory/client nhiều lần thay vì sử dụng bean quản lý | Kiểm tra lifecycle và pooling |

### 14.1. Cần theo dõi gì?

- Thời gian thực thi lệnh Redis và tỷ lệ timeout.
- Số connection và mức sử dụng pool (active, idle, waiters) nếu có pool.
- Redis server `connected_clients`, CPU, memory, blocked clients.
- Số lỗi deserialize và loại serializer/schema khi đọc cache.
- Số transaction/pipeline kéo dài và connection giữ lâu.
- Tỷ lệ retry, lỗi sau reconnect và độ trễ request của service.
- Việc deploy phiên bản mới có tương ứng với lỗi format cache hay không.

Không log password Redis, token, dữ liệu cá nhân hoặc toàn bộ payload chỉ để chẩn đoán lỗi serializer.

## 15. Kịch bản minh họa các tình huống đồng thời

### 15.1. Hai thread ghi hai key khác nhau

~~~text
Thread A: redis.opsForValue().set("a", "1")
Thread B: redis.opsForValue().set("b", "2")
~~~

Cùng một `StringRedisTemplate` singleton là cách dùng hợp lý. Mỗi request giữ `key` và `value` riêng.

### 15.2. Hai thread ghi cùng một key

~~~text
Thread A: SET settings:feature "ON"
Thread B: SET settings:feature "OFF"
~~~

Template vẫn dùng chung an toàn. Nhưng **giá trị cuối** tùy lệnh nào được Redis thực hiện sau cùng. Nếu nghiệp vụ cần ngăn ghi đè, dùng điều kiện, version, `WATCH`/transaction hoặc script tùy bài toán.

### 15.3. Hai thread chỉnh serializer

~~~text
Thread A: template.setValueSerializer(JSON_A)
Thread B: template.setValueSerializer(JSON_B)
Thread A: template.opsForValue().set(...)
~~~

Đây là cách sử dụng sai lifecycle. Không chia sẻ một template mà còn thay config. Tách thành hai bean được cấu hình cố định.

### 15.4. Hai request chạy transaction

~~~text
Request A: SessionCallback -> MULTI -> commands -> EXEC
Request B: SessionCallback -> MULTI -> commands -> EXEC
~~~

Cả hai có thể sử dụng cùng template singleton. Nhưng transaction session/connection của A và B cần được quản lý riêng. Không truyền connection hoặc `RedisOperations` của A sang callback B.

### 15.5. Nhiều instance ứng dụng cùng ghi Redis

~~~text
Instance 1 (JVM A) --> template A --\
                                     > Redis
Instance 2 (JVM B) --> template B --/
~~~

Mỗi instance có template singleton riêng, **không chia sẻ cùng object Java qua mạng**. Tính nguyên tử của lệnh Redis áp dụng trên server, còn đồng bộ `synchronized` trong JVM A không ảnh hưởng JVM B. Vì vậy, tính đúng đắn của nghiệp vụ phân tán phải dựa vào primitive/thiết kế phù hợp.

## 16. Câu hỏi thường gặp

**Có cần khai báo `@Scope("prototype")` cho `RedisTemplate` để mỗi thread có một instance không?**

Thông thường không. Singleton được cấu hình hoàn chỉnh là cách dùng phổ biến. Prototype tạo thêm đối tượng template nhưng không tự giải quyết kết nối, pool hay vấn đề lost update.

**Có nên `new RedisTemplate` trong mỗi hàm service không?**

Không. Việc tạo mới lặp lại cấu hình, dễ bỏ sót lifecycle/serializer và khiến hệ thống khó quản lý. Inject bean dùng chung.

**`RedisTemplate` thread-safe thì `RedisConnection` cũng thread-safe đúng không?**

Không được suy như vậy. Kết nối raw có các ràng buộc của driver, session, transaction và pipeline. Dùng API template hoặc callback có lifetime rõ ràng.

**Có thể tạo nhiều `RedisTemplate` không?**

Có. Khi cần các serializer, kiểu value hoặc connection factory khác nhau, tạo các bean có tên và cấu hình riêng. Mỗi bean có thể được dùng chung an toàn sau khi khởi tạo.

**Có thể dùng đồng thời `opsForValue()` và `opsForHash()` trên cùng template không?**

Có, miễn là mỗi key dùng đúng kiểu Redis và serializer tương ứng. `WRONGTYPE` xảy ra nếu thao tác sai kiểu Redis, không phải vì nhiều thread dùng chung template.

**Có thể bật `setEnableTransactionSupport(true)` ngay trước khi một method bắt đầu không?**

Không nên. Đây là cấu hình template, nên thiết lập khi tạo bean. Ngữ cảnh transaction phù hợp được quản lý khi lời gọi chạy, không cần mutate cấu hình toàn cục theo request.

**Tại sao `INCR` đúng khi nhiều thread chạy nhưng `GET` rồi `SET` có thể sai?**

`INCR` là một lệnh nguyên tử do Redis thực hiện. `GET` và `SET` là hai lệnh riêng; nhiều thread/process có thể xen kẽ giữa chúng.

**Nếu Lettuce hỗ trợ chia sẻ native connection thì có cần RedisConnectionFactory nữa không?**

Có. Factory là điểm tích hợp của Spring Data Redis để tạo/quản lý các connection và xử lý topology/lifecycle. Tự quản lý raw connection chỉ nên thực hiện khi biết rõ yêu cầu và giới hạn tương ứng.

**Khi service chuyển Redis endpoint, chỉ thay `setConnectionFactory` trên singleton đang chạy được không?**

Không nên. Cần một quy trình cập nhật bean/configuration có kiểm soát, xử lý các lời gọi đang chạy và đảm bảo dữ liệu ở endpoint mới đúng. Với Sentinel/Cluster, dùng driver/factory có khả năng khám phá topology.

## 17. Mô hình áp dụng trong dự án Spring Data Redis

Một cấu trúc đơn giản và bền vững có thể là:

~~~text
Spring ApplicationContext
    |
    +-- RedisConnectionFactory         (bean cấu hình một lần)
    |
    +-- StringRedisTemplate            (singleton, cấu hình cố định)
    |
    +-- RedisTemplate<String, ProductCache>
    |                                  (singleton, JSON serializer cố định)
    |
    +-- ApiCounterService ---------------> StringRedisTemplate
    |
    +-- ProductCacheWriter -------------> ProductCacheTemplate
    |
    +-- ProductCacheReader -------------> ProductCacheTemplate
    |
    +-- Controller A/B/C / jobs / consumers
                                       (nhiều luồng đồng thời)
~~~

Giữ các quy tắc sau trong quá trình thiết kế:

1. Khai báo template như **Spring bean singleton**, cấu hình connection factory và serializers trước khi sử dụng.
2. Inject template vào service bằng constructor; sử dụng biến local cho key, tham số, kết quả và state request.
3. Không thay serializer, factory, transaction settings hoặc cấu hình template trong các luồng xử lý runtime.
4. Dùng các thao tác nguyên tử Redis cho bộ đếm/ghi có điều kiện; không nhầm thread-safe template với tính đúng đắn của chuỗi lệnh.
5. Giữ `RedisConnection`, transaction và pipeline trong phạm vi lifecycle/callback phù hợp; không chia sẻ connection state giữa các thread.
6. Với nhiều định dạng dữ liệu hoặc nhiều Redis, tạo **nhiều template được cấu hình độc lập** và dùng bean qualifier rõ ràng.
7. Đảm bảo serializer, `ObjectMapper` và DTO không bị mutate thiếu kiểm soát khi nhiều request cùng đọc/ghi.
8. Quản lý schema/serializer giữa các phiên bản ứng dụng để dữ liệu Redis tiếp tục đọc được trong rollout và sau deploy.

**Ý chính cần ghi nhớ:** `RedisTemplate` và `StringRedisTemplate` là những API dùng chung được giữa nhiều thread **sau khi cấu hình hoàn tất**. Sự ổn định đó đến từ việc template giữ cấu hình nhất quán, Spring quản lý lifecycle kết nối và ứng dụng giữ trạng thái request trong phạm vi riêng. Khi cần thay đổi endpoint, serializer hoặc transaction policy, hãy tạo một cấu hình bean riêng có vòng đời rõ ràng thay vì sửa template singleton trong lúc các request đang chạy.

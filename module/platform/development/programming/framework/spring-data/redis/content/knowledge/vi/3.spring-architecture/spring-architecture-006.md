# Các lớp chuyển đổi kiểu và tuần tự hóa dữ liệu trong Spring Data Redis

Khi ứng dụng Java làm việc với Redis, dữ liệu không tự động đi từ một đối tượng Java vào một ô lưu trữ có kiểu tương ứng. Redis nhận và trả về các dãy byte, còn Spring Data Redis cung cấp nhiều lớp để chuyển đổi giữa **đối tượng Java**, **biểu diễn trung gian** và **dữ liệu Redis**. Hiểu ranh giới giữa **conversion** (chuyển đổi kiểu) và **serialization** (tuần tự hóa) giúp chọn đúng cấu hình, tránh lỗi đọc dữ liệu và giữ khả năng tương thích khi thay đổi phiên bản ứng dụng.

Trong kiến trúc Spring Data Redis, ba nhóm cần phân biệt là:

1. **`RedisSerializer` và `RedisSerializationContext`**: quyết định cách key/value/hash field được mã hóa thành byte và giải mã từ byte khi truy cập bằng template, cache hoặc API reactive.
2. **`RedisConverter`, `MappingRedisConverter`, `RedisCustomConversions`**: dùng trong mô hình ánh xạ object sang Redis hash, đặc biệt với **Spring Data Redis Repository**.
3. **Các lớp ứng dụng** như DTO, entity, service và cache: quyết định kiểu dữ liệu, ý nghĩa nghiệp vụ, TTL và quy ước đặt tên key.

Không phải mọi API Spring Data Redis đều đi qua cùng một đường xử lý. Ví dụ, `RedisTemplate.opsForValue().set(...)` sử dụng value serializer; còn repository của một entity `@RedisHash` dùng mapping converter để biến thuộc tính của entity thành các field trong Redis hash.

## 1. Bức tranh tổng thể: Java object đi tới Redis như thế nào?

Với thao tác lưu một giá trị bằng `RedisTemplate`, luồng khái niệm là:

```text
Java service
    |
    | redisTemplate.opsForValue().set(key, product)
    v
RedisTemplate<K, V>
    |-- keySerializer   : K -> byte[]
    |-- valueSerializer : V -> byte[]
    v
RedisConnectionFactory / RedisConnection
    |
    | gửi lệnh SET kBytes vBytes
    v
Redis server
    |
    | lưu cặp key/value ở dạng byte
    v
GET -> byte[] -> valueSerializer.deserialize(...) -> Java object
```

Với repository lưu object dưới dạng Redis hash, luồng xử lý khác:

```text
UserRepository.save(user)
    |
    v
Redis Repository / RedisKeyValueAdapter
    |
    v
MappingRedisConverter
    |-- RedisMappingContext: metadata của entity
    |-- conversion service và RedisCustomConversions
    |-- chuyển thuộc tính thành các hash field/value
    v
Redis hash: HSET profiles:<id> field value ...
    |
    v
HGETALL ... -> MappingRedisConverter.read(...) -> Java entity
```

Như vậy, **serializer** giải quyết biểu diễn byte của một giá trị ở ranh giới client–Redis, còn **converter** trong cơ chế mapping quyết định cách một kiểu Java được thể hiện hoặc khôi phục trong cấu trúc lưu trữ. Một serializer JSON có thể dùng cho `RedisTemplate`, nhưng không đồng nghĩa Redis Repository tự chuyển toàn bộ entity sang JSON.

## 2. Vì sao cần serialization dù Redis có kiểu dữ liệu riêng?

Redis có các cấu trúc như string, hash, list, set, sorted set và stream. Tuy nhiên, các thành phần key và value mà Redis truyền qua giao thức vẫn là dữ liệu nhị phân. Redis không biết một byte sequence là `Product`, `LocalDate`, `UUID` hay một đối tượng Java cụ thể.

Ví dụ service muốn lưu:

```java
public record Product(String id, String name, long priceMinor) {}

Product product = new Product("p42", "Sổ tay", 199000);
```

Có nhiều cách biểu diễn cùng một object:

```text
JSON UTF-8:
{"id":"p42","name":"Sổ tay","priceMinor":199000}

Chuỗi tự thiết kế:
p42|Sổ tay|199000

Java native serialization:
byte[] theo định dạng Java Object Serialization

Redis hash:
HSET catalog:product:p42 id "p42" name "Sổ tay" priceMinor "199000"
```

Các cách này **không tương thích trực tiếp với nhau**. Nếu một ứng dụng ghi JSON nhưng ứng dụng đọc lại dùng Java serialization, việc giải mã sẽ thất bại dù cả hai đều kết nối đúng Redis và dùng cùng tên key.

Vì vậy, hợp đồng dữ liệu cần bao gồm ít nhất: **tên key, Redis data type, serializer/converter, encoding, cấu trúc payload, quy tắc thay đổi schema và TTL**.

## 3. `RedisSerializer<T>`: lớp chuyển giữa Java và `byte[]`

`RedisSerializer<T>` là giao diện thường gặp nhất ở mức template. Hai thao tác nền tảng có dạng khái niệm:

```java
byte[] serialize(T value);
T deserialize(byte[] bytes);
```

Phía ghi gọi `serialize`; phía đọc gọi `deserialize`. Các phương thức có thể phát sinh `SerializationException` khi payload không hợp lệ hoặc không thể chuyển đổi sang kiểu đích. Cách xử lý giá trị `null` phụ thuộc từng serializer và API liên quan; không được mặc định rằng `null`, key vắng mặt và một payload biểu diễn giá trị null luôn mang cùng ý nghĩa.

Các serializer phổ biến:

| Lớp/nhóm | Dữ liệu được lưu | Điểm mạnh | Lưu ý |
|---|---|---|---|
| `StringRedisSerializer` | Chuỗi theo UTF-8 | Dễ đọc bằng `redis-cli`, tương tác tốt giữa các ngôn ngữ | Phù hợp chuỗi; không tự biến Java object tùy ý thành JSON |
| `Jackson2JsonRedisSerializer<T>` | JSON cho kiểu đích xác định | Payload đọc được, hợp đồng kiểu rõ | Cần cấu hình kiểu, mapper/schema phù hợp khi dữ liệu thay đổi |
| `GenericJackson2JsonRedisSerializer` | JSON cho nhiều kiểu Java, thường kèm thông tin kiểu | Tiện với giá trị đa hình hoặc cache có nhiều kiểu | Metadata kiểu và cấu hình Jackson ảnh hưởng tương thích, an toàn |
| `JdkSerializationRedisSerializer` | Java native serialization | Có thể ghi/đọc các object Java phù hợp | Khó tương tác ngoài Java; rủi ro bảo mật khi deserialize dữ liệu không tin cậy; nhạy với thay đổi class |
| `GenericToStringSerializer<T>` | Chuyển object thành chuỗi rồi thành byte | Hữu ích cho kiểu đơn giản có bộ chuyển đổi phù hợp | Không phải giải pháp chung cho object phức tạp |
| Serializer tự viết | Định dạng byte do ứng dụng quy định | Kiểm soát hoàn toàn encoding, hiệu năng, phiên bản | Cần tự bảo đảm tính tương thích và xử lý lỗi |

`RedisTemplate` mặc định có thể dùng `JdkSerializationRedisSerializer` cho nhiều loại giá trị khi không được cấu hình rõ ràng. Vì vậy, trong ứng dụng mới nên **khai báo serializer tường minh** theo hợp đồng dữ liệu. `StringRedisTemplate` là lựa chọn thuận tiện khi cả key và value đều là chuỗi: các serializer của nó được cấu hình cho string.

### Tại sao cách hiển thị trong `redis-cli` khác nhau?

Khi sử dụng serializer chuỗi hoặc JSON UTF-8, `GET` thường cho nội dung dễ quan sát:

```bash
redis-cli --raw GET catalog:product:v1:p42
```

```json
{"id":"p42","name":"Sổ tay","priceMinor":199000}
```

Ngược lại, payload từ Java native serialization là dữ liệu nhị phân, nên `redis-cli` có thể hiển thị ký tự khó đọc. Không nên kết luận key bị hỏng chỉ vì dữ liệu không phải văn bản; cần biết **định dạng ghi ban đầu** và dùng decoder tương ứng.

## 4. Bốn nhóm serializer trong `RedisTemplate`

Một `RedisTemplate<K,V>` phân biệt serializer của key và value tùy loại lệnh Redis:

| Cấu hình của `RedisTemplate` | Áp dụng cho | Ví dụ |
|---|---|---|
| `keySerializer` | Key chính của các lệnh | Key của `SET`, `GET`, key Redis hash |
| `valueSerializer` | Value của các thao tác value, list, set, sorted set… | Giá trị của `SET product:42 <payload>` |
| `hashKeySerializer` | Tên field trong Redis hash | `name`, `price` trong `HSET product:42 name ...` |
| `hashValueSerializer` | Giá trị của field Redis hash | Giá trị `"Sổ tay"` trong `HSET product:42 name ...` |

Trong template còn có các cấu hình serializer khác, chẳng hạn serializer mặc định hoặc string serializer phục vụ một số thao tác. Điểm quan trọng là **key, value, hash field và hash value là bốn vai trò khác nhau**; không nên chỉ cấu hình value serializer rồi giả định toàn bộ cấu trúc Redis sẽ dùng cùng quy tắc đó.

Ví dụ, thao tác:

```java
redisTemplate.opsForHash().put("catalog:inventory", "p42", "50");
```

Ở đây `"catalog:inventory"` đi qua `keySerializer`, `"p42"` đi qua `hashKeySerializer`, còn `"50"` đi qua `hashValueSerializer`. `valueSerializer` của template không quyết định cách `"50"` được lưu trong Redis hash.

## 5. Ví dụ Spring Boot: cấu hình `RedisTemplate` với JSON

Ví dụ dưới đây dùng Spring Boot 3.x, Spring Data Redis, Java 17+ và một `RedisConnectionFactory` đã được auto-configure. Một ứng dụng thường khai báo dependency Spring Data Redis starter và cung cấp cấu hình kết nối Redis riêng cho môi trường chạy.

Định nghĩa object:

```java
package com.example.catalog;

public record Product(String id, String name, long priceMinor) {}
```

Cấu hình template với key là UTF-8 string, value là JSON dành riêng cho `Product`:

```java
package com.example.catalog;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisTemplateConfig {

    @Bean
    public RedisTemplate<String, Product> productRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, Product> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer stringSerializer = new StringRedisSerializer();

        template.setKeySerializer(stringSerializer);
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(Product.class));

        // Nếu sử dụng opsForHash() với tên field và field value là chuỗi.
        template.setHashKeySerializer(stringSerializer);
        template.setHashValueSerializer(stringSerializer);

        template.afterPropertiesSet();
        return template;
    }
}
```

Service sử dụng template:

```java
package com.example.catalog;

import java.time.Duration;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductRedisStore {
    private final RedisTemplate<String, Product> template;

    public ProductRedisStore(RedisTemplate<String, Product> productRedisTemplate) {
        this.template = productRedisTemplate;
    }

    public void save(Product product) {
        String key = "catalog:product:v1:" + product.id();
        template.opsForValue().set(key, product, Duration.ofMinutes(20));
    }

    public Product find(String id) {
        return template.opsForValue().get("catalog:product:v1:" + id);
    }
}
```

Giả sử gọi `save(new Product("p42", "Sổ tay", 199000))`, Redis sẽ nhận:

```text
Key (UTF-8) : catalog:product:v1:p42
Value (JSON): {"id":"p42","name":"Sổ tay","priceMinor":199000}
TTL         : 20 phút tại thời điểm ghi
```

Đây là giá trị **Redis string** chứa JSON, không phải Redis hash. `HGETALL catalog:product:v1:p42` không đọc được giá trị trên vì loại Redis data type của key là string; phải dùng `GET` hoặc API `opsForValue()` tương ứng.

Trong ví dụ, `Product` chỉ gồm string và số nguyên nên serializer JSON có thể thao tác trực tiếp. Với kiểu như `Instant`, `LocalDateTime`, `Optional` hoặc mapping phức tạp, cần cấu hình `ObjectMapper`/module Jackson phù hợp với phiên bản đang dùng và quy ước thời gian mong muốn. Không nên giả định serializer JSON tự sử dụng mọi tùy chỉnh của `ObjectMapper` trong Spring Boot khi bạn tạo serializer bằng constructor riêng.

## 6. Khi nào dùng `StringRedisTemplate`?

Nếu dữ liệu thật sự là chuỗi, số lưu dạng chuỗi hoặc payload JSON đã được ứng dụng chủ động tạo trước, có thể dùng `StringRedisTemplate`:

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class TokenStore {
    private final StringRedisTemplate redis;

    public TokenStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void put(String tokenId, String accountId) {
        redis.opsForValue().set(
                "auth:token:v1:" + tokenId,
                accountId,
                Duration.ofMinutes(10));
    }

    public String get(String tokenId) {
        return redis.opsForValue().get("auth:token:v1:" + tokenId);
    }
}
```

Đối với `StringRedisTemplate`, dữ liệu của `accountId` được lưu dưới dạng UTF-8 string. Một `RedisTemplate<String, Product>` cấu hình JSON và `StringRedisTemplate` có thể cùng tồn tại trong ứng dụng, nhưng nếu chúng đọc cùng key thì **payload phải có định dạng mà phía đọc mong đợi**. Kiểu generic của Java không tự chuyển dữ liệu Redis sang format khác.

## 7. `RedisSerializationContext` và API reactive

Trong Spring Data Redis reactive, `ReactiveRedisTemplate<K,V>` nhận một **`RedisSerializationContext<K,V>`**. Context này tập hợp các quy tắc serialization cho key, value, hash key và hash value, thường qua `SerializationPair`.

Ví dụ khái niệm khi dùng Lettuce reactive connection factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ReactiveRedisConfig {

    @Bean
    ReactiveRedisTemplate<String, Product> reactiveProductRedisTemplate(
            ReactiveRedisConnectionFactory factory) {

        StringRedisSerializer keys = new StringRedisSerializer();
        Jackson2JsonRedisSerializer<Product> values =
                new Jackson2JsonRedisSerializer<>(Product.class);

        RedisSerializationContext<String, Product> context =
                RedisSerializationContext
                    .<String, Product>newSerializationContext(keys)
                    .value(values)
                    .hashKey(keys)
                    .hashValue(values)
                    .build();

        return new ReactiveRedisTemplate<>(factory, context);
    }
}
```

Với context này, `reactiveTemplate.opsForValue().set(key, product)` dùng serializer `values` và trả về `Mono<Boolean>`; việc đọc có thể trả về `Mono<Product>`. Reactive API thay đổi mô hình thực thi bất đồng bộ, **không làm Redis tự hiểu Java object**. Quy tắc byte của cả API đồng bộ và reactive vẫn phải đồng nhất nếu cùng truy cập một keyspace.

Một `ReactiveStringRedisTemplate` thích hợp khi cả key và value đều là string. Cũng như trường hợp `RedisTemplate`, cần chọn template theo định dạng lưu trữ và kiểu dữ liệu thực tế.

## 8. `MappingRedisConverter`: ánh xạ entity sang Redis hash

Trong Spring Data Redis Repository, annotation `@RedisHash` đánh dấu một loại entity sẽ được repository quản lý theo mô hình key–value của Redis. Với cấu hình repository thông thường, Spring Data Redis dùng `MappingRedisConverter` để phân rã object thành các field của Redis hash.

Ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("profiles")
public class UserProfile {
    @Id
    private String id;
    private String displayName;

    public UserProfile() {}

    public UserProfile(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface UserProfileRepository
        extends CrudRepository<UserProfile, String> {
}
```

Sau `repository.save(new UserProfile("u42", "An"))`, cách lưu tương ứng là **Redis hash** với key có dạng `profiles:u42`. Các field của hash biểu diễn thuộc tính và có thể chứa thêm metadata dành cho mapping tùy cấu hình, chẳng hạn trường kiểu `_class`. Không nên mặc định hash chỉ có đúng các field định nghĩa trong class hoặc layout nội bộ sẽ giống nhau giữa mọi phiên bản/cấu hình.

Vai trò của các thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| `RedisMappingContext` | Nắm metadata của entity, thuộc tính và mapping tương ứng |
| `MappingRedisConverter` | Chuyển qua lại giữa object và dữ liệu hash theo mapping |
| `RedisCustomConversions` | Đăng ký converter riêng cho các kiểu không muốn/không thể mapping mặc định |
| `RedisKeyValueAdapter` / Repository | Điều phối lưu, đọc, xóa và các thao tác của repository với Redis |
| `@RedisHash`, `@Id` | Khai báo entity Redis và định danh |

**Ranh giới quan trọng:** `@RedisHash("profiles")` không đơn thuần gọi `StringRedisSerializer` hoặc `Jackson2JsonRedisSerializer` trên cả object. Repository có cơ chế mapping riêng. Cấu hình `valueSerializer` cho một bean `RedisTemplate<String, Product>` cũng không mặc nhiên khiến Redis Repository của `UserProfile` lưu mỗi entity thành một JSON string.

## 9. `RedisCustomConversions`: định nghĩa chuyển đổi kiểu riêng

Giả sử miền nghiệp vụ có kiểu giá trị `EmailAddress`:

```java
public record EmailAddress(String value) {}
```

Trong entity repository:

```java
@RedisHash("profiles")
public class UserProfile {
    @Id
    private String id;
    private EmailAddress email;

    public UserProfile() {}

    // Getter, setter và constructor phù hợp được khai báo tại đây.
}
```

Nếu muốn lưu `EmailAddress` dưới dạng một field byte UTF-8 duy nhất trong Redis hash, có thể đăng ký hai converter có hướng rõ ràng:

```java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.redis.core.convert.RedisCustomConversions;

@WritingConverter
class EmailAddressToBytes implements Converter<EmailAddress, byte[]> {
    @Override
    public byte[] convert(EmailAddress source) {
        return source.value().getBytes(StandardCharsets.UTF_8);
    }
}

@ReadingConverter
class BytesToEmailAddress implements Converter<byte[], EmailAddress> {
    @Override
    public EmailAddress convert(byte[] source) {
        return new EmailAddress(new String(source, StandardCharsets.UTF_8));
    }
}

@Configuration
class RedisConversionConfig {
    @Bean
    RedisCustomConversions redisCustomConversions() {
        return new RedisCustomConversions(List.of(
                new EmailAddressToBytes(),
                new BytesToEmailAddress()));
    }
}
```

Ở chiều ghi:

```text
UserProfile.email: EmailAddress("an@example.com")
       |
       v
EmailAddressToBytes
       |
       v
byte[] UTF-8: "an@example.com"
       |
       v
field "email" trong Redis hash
```

Ở chiều đọc, `BytesToEmailAddress` khôi phục value object từ byte sequence. Mẫu này hữu ích cho **value object**, identifier tùy chỉnh, kiểu dữ liệu cũ hoặc những trường hợp cần kiểm soát biểu diễn của một property. Converter chỉ áp dụng trong ngữ cảnh mapping đã đăng ký; nó không thay thế `valueSerializer` của mọi `RedisTemplate` trong ứng dụng.

### Các nguyên tắc khi viết converter

- Dùng kiểu nguồn và kiểu đích rõ ràng, và khai báo `@ReadingConverter`/`@WritingConverter` để tránh mơ hồ với những kiểu mà hệ thống có thể chuyển theo hai chiều.
- Hai chiều phải thống nhất định dạng, chẳng hạn đều là UTF-8, ISO-8601 hoặc một schema nhị phân có version.
- Với giá trị có quy tắc bất biến, kiểm tra dữ liệu đầu vào và xử lý giá trị không hợp lệ minh bạch; không âm thầm tạo object sai.
- Khi converter cũ đã được dùng để ghi dữ liệu, thay đổi format có thể khiến dữ liệu cũ không đọc được. Cần kế hoạch tương thích hoặc di trú.
- Tránh converter quá tổng quát như chuyển mọi object sang `String`, vì dễ thay đổi ngoài dự kiến cách nhiều thuộc tính được mapping.

Không phải custom type nào cũng cần converter. Spring Data Redis có khả năng mapping thuộc tính đơn giản và object lồng nhau theo quy tắc mặc định. Chỉ thêm converter khi cần một biểu diễn có chủ đích, ví dụ định dạng compact, tương thích với dữ liệu cũ hoặc giữ tính bất biến của value object.

## 10. Phân biệt Redis hash với JSON nằm trong Redis string

Hai cách lưu sau có ý nghĩa khác nhau dù biểu diễn cùng sản phẩm:

**Cách A — JSON dưới Redis string:**

```redis
SET catalog:product:v1:p42 '{"id":"p42","name":"Sổ tay","priceMinor":199000}'
GET catalog:product:v1:p42
```

**Cách B — Redis hash với từng field:**

```redis
HSET catalog:product-hash:v1:p42 id p42 name "Sổ tay" priceMinor 199000
HGET catalog:product-hash:v1:p42 name
HGETALL catalog:product-hash:v1:p42
```

| Tiêu chí | JSON trong Redis string | Redis hash |
|---|---|---|
| Redis command đọc dữ liệu | `GET` | `HGET`, `HMGET`, `HGETALL` |
| Cập nhật một thuộc tính | Thường đọc/sửa/ghi lại toàn payload | Có thể cập nhật một field bằng `HSET` |
| Cách Java mapping | JSON serializer của value | Hash mapping hoặc `opsForHash()` |
| Metadata kiểu | Phụ thuộc serializer/schema JSON | Phụ thuộc converter và mapping metadata |
| TTL | Gắn với toàn bộ Redis key | TTL thông thường gắn với Redis key (không phải từng hash field) |
| Thay đổi schema | Cần xử lý phiên bản JSON | Cần xử lý trường thiếu/thừa và converter |

Chọn Redis hash khi thường xuyên thao tác từng field hoặc dùng Redis Repository. Chọn JSON string khi đơn vị đọc/ghi là toàn object, muốn payload rõ ràng và thuận tiện khi tương tác liên ngôn ngữ. Không có lựa chọn nào luôn tối ưu: kích thước dữ liệu, số lệnh, tần suất cập nhật, TTL và nhu cầu index đều ảnh hưởng quyết định.

## 11. Serialization trong Spring Cache là cấu hình riêng

Khi ứng dụng dùng Spring Cache với Redis, dữ liệu cache thường được xử lý qua `RedisCacheManager` và `RedisCacheConfiguration`. Cấu hình `valueSerializer` cho `RedisTemplate` **không tự động áp dụng cho mọi cache**.

Ví dụ thiết lập riêng cache `products` chỉ lưu `Product`:

```java
import java.time.Duration;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;

@Configuration
public class ProductCacheConfig {

    @Bean
    RedisCacheManager redisCacheManager(RedisConnectionFactory factory) {
        RedisCacheConfiguration productCache =
                RedisCacheConfiguration.defaultCacheConfig()
                    .entryTtl(Duration.ofMinutes(15))
                    .serializeValuesWith(
                        RedisSerializationContext.SerializationPair.fromSerializer(
                            new Jackson2JsonRedisSerializer<>(Product.class)));

        return RedisCacheManager.builder(factory)
                .withInitialCacheConfigurations(
                        Map.of("products", productCache))
                .build();
    }
}
```

Đoạn này chọn serializer JSON theo kiểu `Product` cho **cache có tên `products`**; các cache khác cần cấu hình riêng theo kiểu dữ liệu thực tế. Thao tác cache vẫn tuân theo quy tắc prefix key, TTL và cách đọc/ghi của Spring Cache. Không nên lấy cùng một typed serializer cho nhiều cache chứa các kiểu object không tương thích.

Một số serializer JSON tổng quát hỗ trợ lưu nhiều kiểu object nhờ bổ sung thông tin kiểu. Tiện lợi này cần đi kèm đánh giá cấu hình polymorphism, nơi dữ liệu được đọc và tính ổn định của class name. Nếu chỉ cache một loại value rõ ràng, typed serializer đơn giản thường dễ kiểm soát hơn.

Spring Session, Pub/Sub listener và các thư viện khác cũng có thể sở hữu cơ chế serialization hoặc namespace riêng. Khi chúng chia sẻ Redis, cần kiểm tra serializer **tại chính thành phần tạo dữ liệu**, không suy ra từ một `RedisTemplate` bất kỳ.

## 12. Bảo mật khi deserialize dữ liệu Redis

Redis thường được dùng làm cache hoặc lưu state dùng chung giữa nhiều tiến trình. Dù Redis nằm trong mạng nội bộ, dữ liệu có thể đến từ dịch vụ khác, phiên bản cũ hoặc nguồn không đáng tin cậy. Việc deserialize payload nhị phân thành đối tượng Java vì vậy có thể mở ra rủi ro.

### Cẩn trọng với Java native serialization

`JdkSerializationRedisSerializer` dựa vào Java Object Serialization. Nếu ứng dụng giải mã dữ liệu do bên khác có thể thay đổi hoặc chèn vào Redis, cơ chế Java native deserialization có thể nguy hiểm, đặc biệt khi classpath chứa những loại object có hành vi không mong muốn trong quá trình giải mã.

Với dữ liệu mới, ưu tiên **string, JSON có kiểu rõ ràng hoặc định dạng nhị phân được kiểm soát**. Nếu hệ thống cũ bắt buộc dùng JDK serialization, cần giới hạn nguồn dữ liệu và áp dụng cơ chế lọc class khi deserialization theo khả năng của JVM và thư viện đang sử dụng.

### Cẩn trọng với JSON polymorphic

Một số serializer Jackson tổng quát lưu cả tên class hoặc metadata kiểu vào JSON để khôi phục object. Không bật cơ chế default typing rộng rãi cho dữ liệu không tin cậy mà thiếu chính sách giới hạn kiểu được phép khởi tạo. Đồng thời, việc đưa tên class Java vào payload sẽ làm dữ liệu phụ thuộc vào package/class name, gây khó khăn khi refactor.

### Serializer không thay thế kiểm soát truy cập

JSON dễ đọc không phải mã hóa. Dữ liệu nhạy cảm không nên được bảo vệ chỉ bằng việc dùng định dạng nhị phân khó xem. Cần dùng xác thực, TLS khi phù hợp, ACL theo key pattern, quản lý secret và chính sách lưu trữ/TTL của ứng dụng.

## 13. Thay đổi serializer: vấn đề tương thích dữ liệu

Giả sử phiên bản đầu lưu sản phẩm bằng JDK serializer:

```text
Key: catalog:product:p42
Value: <Java serialization bytes>
```

Phiên bản mới đổi sang Jackson JSON serializer nhưng vẫn đọc cùng key. Redis không tự chuyển dữ liệu cũ sang JSON. Lệnh `GET` vẫn trả byte cũ và `deserialize` của Jackson có thể ném `SerializationException` hoặc lỗi JSON parsing.

Vì vậy, đổi serializer là **thay đổi hợp đồng dữ liệu** tương tự thay đổi schema database.

Một chiến lược dễ kiểm soát là **đổi namespace/version key**:

```text
catalog:product:v1:p42  -> dữ liệu định dạng cũ
catalog:product:v2:p42  -> JSON theo schema mới
```

Ứng dụng mới chỉ ghi `v2`. Trong giai đoạn chuyển đổi, có thể đọc `v2` trước, sau đó đọc `v1` bằng đúng serializer cũ và ghi lại `v2` khi cần. Với cache có thể tái tạo từ nguồn gốc, đôi khi đơn giản hơn là bỏ qua cache cũ và nạp lại cache mới. Với dữ liệu có tính nguồn gốc nghiệp vụ, phải có phương án di trú và xác minh đầy đủ trước khi bỏ dữ liệu cũ.

Quy trình ví dụ:

```text
1. Định nghĩa format v2 và serializer tương ứng.
2. Triển khai code ghi v2; đọc v2 ưu tiên.
3. Với key chỉ có v1, giải mã bằng serializer v1 rồi chuyển sang v2.
4. Giữ TTL còn lại nếu thời hạn dữ liệu có ý nghĩa.
5. Theo dõi lỗi deserialize và key chưa được migrate.
6. Chỉ loại bỏ đường đọc v1 khi dữ liệu/hành vi cũ không còn cần thiết.
```

Không nên dùng cách “thử decode bằng JSON, nếu lỗi thì thử JDK” một cách vô hạn và thiếu kiểm soát; nó khó quan sát, có thể che lỗi payload hỏng và kéo dài việc phải hỗ trợ cơ chế deserialize nguy hiểm. Namespace có version rõ ràng thường giúp giảm mơ hồ hơn.

### Thay đổi field hoặc kiểu Java bên trong JSON

Ngay cả khi vẫn dùng JSON, những thay đổi như đổi tên field `priceMinor` thành `price`, đổi `long` sang kiểu có cấu trúc phức tạp, thay đổi timestamp format hoặc đổi package name (khi payload chứa type metadata) có thể làm reader cũ/mới không tương thích.

Tùy yêu cầu, có thể áp dụng migration DTO, version field, ánh xạ tên cũ hoặc triển khai reader chấp nhận nhiều schema trong một khoảng thời gian hữu hạn. Không nên xem JSON là giải pháp tự động cho mọi thay đổi schema.

## 14. Key serializer ảnh hưởng Redis Cluster và các client khác

Trong Redis Cluster, hash slot được tính trên **byte của key** (có xử lý hash tag `{...}`), không phải trên object Java ở cấp ứng dụng. Nếu hai client mã hóa cùng chuỗi key thành các byte khác nhau, chúng có thể tính ra slot khác nhau và thực chất truy cập hai key khác nhau.

Ví dụ:

```text
Java key: "shop:product:42"
StringRedisSerializer -> byte UTF-8 của chuỗi trên
JdkSerializationRedisSerializer -> header và byte của Java serialization
```

Do đó, nhiều dịch vụ Java hoặc dịch vụ khác ngôn ngữ muốn dùng chung key nên thống nhất `StringRedisSerializer`/UTF-8, cách chuẩn hóa ID, dấu phân tách và prefix. Tên key nên dễ dự đoán; tránh sử dụng byte định dạng của Java object làm Redis key khi không thực sự cần thiết.

Trong Cluster, những lệnh thao tác nhiều key có thể yêu cầu các key ở cùng slot. Hash tag, ví dụ `cart:{u42}:items` và `cart:{u42}:total`, bảo đảm phần `{u42}` được dùng để tính slot nếu hash tag hợp lệ. **Serializer và hash tag là hai vấn đề khác nhau**: serializer quyết định byte key; hash tag điều khiển phần byte dùng khi xác định slot.

Nếu thay đổi key serializer hoặc quy tắc key, cần coi đó là đổi định danh lưu trữ. Key cũ không tự được đổi tên và có thể trở thành dữ liệu không được ứng dụng mới truy cập.

## 15. Lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `SerializationException` khi `GET` | Reader dùng serializer/kiểu khác writer; payload hỏng | Xác định key, `TYPE`, byte/payload mẫu, version và serializer của bên ghi |
| `GET` trả `null` dù có key nhìn thấy trong Redis | Khác tên key do serializer/prefix/DB, hoặc key đã hết TTL | So sánh byte key, namespace, DB/Cluster, `EXISTS`, `TTL` |
| `WRONGTYPE` | Dùng `GET` với Redis hash hoặc `HGET` với Redis string | Kiểm tra `TYPE <key>` trước khi đổi cách đọc |
| `redis-cli` thấy ký tự lạ | Payload là binary hoặc JDK serialization | Xác định serializer nguồn; không tự sửa byte bằng thao tác thủ công |
| Value JSON thiếu trường hoặc sai kiểu | Schema/record/class thay đổi, Jackson config khác | Đối chiếu payload và DTO/`ObjectMapper` đang chạy |
| `opsForHash()` đọc sai field/value | Nhầm `hashKeySerializer` hoặc `hashValueSerializer` | Kiểm tra cấu hình từng serializer trên template |
| Repository lưu ra nhiều hash fields thay vì một JSON | Repository sử dụng `MappingRedisConverter` | Xác định đang gọi Repository hay `opsForValue()` |
| Cache đọc được khi chạy một phiên bản nhưng lỗi khi deploy | Các phiên bản dùng serializer hoặc model khác nhau | Xem cấu hình `RedisCacheManager` và chiến lược schema version |
| Client khác ngôn ngữ không tìm thấy key | Khác encoding hoặc key serializer | Thống nhất key string UTF-8 và prefix |

Một số lệnh thăm dò trên **môi trường được phép**:

```bash
redis-cli TYPE catalog:product:v1:p42
redis-cli TTL catalog:product:v1:p42
redis-cli --raw GET catalog:product:v1:p42

# Với key thực sự có Redis type = hash:
redis-cli HGETALL profiles:u42
```

Với Cluster, cần dùng client/CLI hỗ trợ định tuyến slot (ví dụ `redis-cli -c`); địa chỉ và quyền truy cập tùy môi trường. Không dùng `KEYS *` trong môi trường có khối lượng dữ liệu lớn chỉ để tìm serializer, và không in dữ liệu cá nhân hoặc secret vào log để debug.

### Ví dụ: hai service ghi chung một key nhưng khác serializer

```text
Service A: StringRedisTemplate
  SET shared:flag "true"

Service B: RedisTemplate<String, Boolean>
  valueSerializer = JdkSerializationRedisSerializer
  GET shared:flag -> lỗi deserialize hoặc giá trị không đúng mong đợi
```

Giải pháp là định nghĩa một format chung, chẳng hạn string `"true"`/`"false"`, rồi cấu hình cả hai bên cùng serialization contract. Nếu hai service sở hữu mục đích và vòng đời dữ liệu khác nhau, hãy dùng key namespace khác nhau để tránh tranh chấp writer.

## 16. Thiết kế lớp chuyển đổi có trách nhiệm rõ ràng

Trong ứng dụng có nhiều loại Redis data, việc tạo một `RedisTemplate<Object,Object>` chung cho mọi nghiệp vụ có thể che giấu kiểu dữ liệu và format. Một cách tổ chức dễ bảo trì hơn là:

```text
Application service
   |
   +-- ProductRedisStore
   |       +-- RedisTemplate<String, Product>
   |       +-- String key + Product JSON value
   |
   +-- TokenStore
   |       +-- StringRedisTemplate
   |       +-- String key + String value
   |
   +-- UserProfileRepository
   |       +-- Redis Repository
   |       +-- MappingRedisConverter / RedisCustomConversions
   |
   +-- Spring Cache
           +-- RedisCacheManager
           +-- RedisCacheConfiguration cho từng cache
```

Những thành phần này có thể sử dụng cùng `RedisConnectionFactory` nhưng sở hữu serializer, converter và chính sách dữ liệu riêng. Service nghiệp vụ gọi `ProductRedisStore.save(product)` không cần biết chi tiết Jackson, encoding hoặc cấu trúc byte của Redis. Khi cần đổi format, có thể xử lý trong lớp lưu trữ và quy trình migration thay vì sửa nhiều chỗ trong business logic.

Các nguyên tắc thiết kế thực tế:

- **Chọn Redis data type trước:** string, hash hay cấu trúc khác tùy lệnh và kiểu truy cập cần thiết.
- **Chọn đường mapping đúng:** `RedisTemplate` đi qua serializer của template; Redis Repository đi qua mapping/conversion; Spring Cache dùng cache configuration.
- **Khai báo serializer tường minh:** ưu tiên string key UTF-8 và định dạng value có schema rõ ràng cho dữ liệu chia sẻ.
- **Tách converter theo miền nghiệp vụ:** chỉ dùng `RedisCustomConversions` khi thật sự cần biểu diễn đặc biệt của một value object/property.
- **Version hóa dữ liệu có vòng đời dài:** serializer/schema là một phần hợp đồng giữa các phiên bản ứng dụng và các dịch vụ.
- **Gắn TTL và namespace với mục đích sử dụng:** serializer không tự tạo TTL hay cơ chế cách ly dữ liệu.
- **Giới hạn dữ liệu tin cậy khi deserialize:** cẩn trọng với Java serialization và JSON polymorphism.

## 17. Câu hỏi tự kiểm tra

**1. Tại sao `StringRedisTemplate` đọc được chuỗi nhưng `RedisTemplate` mặc định có thể không đọc được cùng key?**

Vì hai template có thể dùng serializer khác nhau. Cùng một key Redis không bảo đảm payload có định dạng hợp lệ cho mọi decoder. Cần thống nhất serializer hoặc tách key theo namespace.

**2. `RedisTemplate.setValueSerializer(...)` có đổi cách `@RedisHash` Repository ánh xạ entity không?**

Không theo nghĩa tự động thay toàn bộ mapping của repository. Redis Repository sử dụng `MappingRedisConverter` và những custom conversions đã đăng ký để thao tác Redis hash. Cần cấu hình đúng thành phần trực tiếp quản lý entity.

**3. Khi nào dùng `RedisCustomConversions` thay vì `Jackson2JsonRedisSerializer`?**

Dùng custom conversions khi muốn kiểm soát cách một thuộc tính hoặc value object được ánh xạ trong cơ chế Redis Repository. Dùng JSON serializer khi muốn lưu và đọc một value Java thành JSON ở ranh giới template/cache phù hợp.

**4. Vì sao thay serializer có thể làm cache hoặc dữ liệu Redis cũ không đọc được?**

Redis chỉ lưu byte. Reader mới không có khả năng tự hiểu mọi định dạng byte được writer cũ tạo ra. Cần versioning, di trú hoặc chủ động tạo lại cache từ nguồn gốc.

**5. Khi nhiều ngôn ngữ lập trình dùng chung Redis, loại key serializer nào thường dễ phối hợp?**

`StringRedisSerializer` theo UTF-8, đi cùng quy ước prefix và ID nhất quán. Với value nên thống nhất định dạng có hợp đồng rõ ràng như JSON hoặc một schema nhị phân độc lập với class Java.

**6. Vì sao Redis hash và JSON string của cùng một object không thể dùng chung lệnh đọc?**

Vì Redis data type khác nhau. JSON string dùng `GET`, còn Redis hash dùng `HGET`/`HGETALL`. Converter và serializer phù hợp cũng khác nhau theo đường lưu trữ.

### Kết luận

Trong Spring Data Redis, **`RedisSerializer` định nghĩa biểu diễn byte khi thao tác qua template**, **`RedisSerializationContext` tập hợp quy tắc đó cho reactive API**, còn **`MappingRedisConverter` và `RedisCustomConversions` phục vụ ánh xạ object–Redis hash trong repository**. Spring Cache lại có cấu hình serialize riêng. Nhận diện đúng đường dữ liệu của từng API, thống nhất key và value format, kiểm soát version schema và tránh deserialize dữ liệu không tin cậy sẽ giúp Redis hoạt động ổn định khi ứng dụng mở rộng hoặc được triển khai qua nhiều phiên bản.

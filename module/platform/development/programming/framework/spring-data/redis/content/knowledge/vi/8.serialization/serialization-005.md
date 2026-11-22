# Tuần tự hóa JSON và lựa chọn serializer phù hợp phiên bản trong Spring Data Redis

Khi ứng dụng Java ghi một đối tượng vào Redis, Redis không lưu trực tiếp class, record hay object Java. Redis nhận **chuỗi byte (`byte[]`)** do client gửi. **Serialization (tuần tự hóa)** là quá trình biến một giá trị Java thành chuỗi byte có thể lưu; **deserialization (giải tuần tự hóa)** là quá trình diễn giải các byte đó thành dữ liệu Java khi đọc. Việc chọn serializer quyết định cách key xuất hiện trong Redis, định dạng value, khả năng tương thích giữa các lần triển khai và cả rủi ro bảo mật.

Với **Spring Data Redis**, JSON thường được chọn cho dữ liệu ứng dụng và cache vì dễ quan sát, tương đối độc lập ngôn ngữ lập trình và thuận tiện quản lý cấu trúc. Tuy nhiên, **không có một JSON serializer đúng cho mọi dự án và mọi phiên bản**. Đặc biệt, Spring Data Redis 3.x gắn với Jackson 2; từ Spring Data Redis 4.0, các API JSON chính chuyển sang Jackson 3, thay đổi tên class và một số hành vi mặc định quan trọng. Bài học này giúp bạn chọn đúng serializer, viết cấu hình theo từng nhánh phiên bản, kiểm soát type metadata và xây dựng phương án nâng cấp dữ liệu đang tồn tại.

## 1. Sau bài học này cần nắm được gì?

1. Phân biệt **key serializer**, **value serializer**, **hash-key serializer** và **hash-value serializer** trong `RedisTemplate`.
2. Giải thích sự khác nhau giữa `StringRedisSerializer`, `Jackson2JsonRedisSerializer<T>`, `GenericJackson2JsonRedisSerializer`, `JacksonJsonRedisSerializer<T>`, `GenericJacksonJsonRedisSerializer` và `JdkSerializationRedisSerializer`.
3. Quyết định khi nào nên dùng **typed JSON** (một kiểu DTO rõ ràng) và khi nào phải cân nhắc **generic JSON** (nhiều kiểu runtime).
4. Nhận diện khác biệt API giữa Spring Data Redis 3.x/Jackson 2 và 4.x/Jackson 3 để tránh lỗi biên dịch hay đọc sai dữ liệu.
5. Thiết lập JSON serializer cho `RedisTemplate` và cho `RedisCacheManager` theo đúng nơi sử dụng.
6. Hiểu vấn đề metadata như `@class`, type erasure, dữ liệu cache cũ, thay đổi schema và chiến lược migration.
7. Kiểm tra giá trị thực trong Redis và khoanh vùng lỗi serialization, deserialization, key khác định dạng, cache miss hoặc mất tương thích.

Kiến thức đầu vào: biết cách tạo ứng dụng Spring Boot, cấu hình `@Bean`, inject service, dùng `RedisTemplate`/`StringRedisTemplate` ở mức cơ bản và biết Redis có kiểu dữ liệu String, Hash, List, Set.

## 2. Dữ liệu thực sự được lưu trong Redis

Giả sử service Java có một đối tượng:

~~~java
public record ProductSnapshot(
        String id,
        String name,
        java.math.BigDecimal price
) {}

ProductSnapshot p =
        new ProductSnapshot("42", "Bàn phím", new java.math.BigDecimal("590000"));
~~~

Nếu dùng JSON serializer phù hợp, Redis String có thể chứa chuỗi JSON:

~~~json
{"id":"42","name":"Bàn phím","price":590000}
~~~

Sơ đồ đường đi:

~~~text
Java ProductSnapshot
       |
       | value serializer
       v
JSON bytes: {"id":"42", ...}
       |
       | Redis client gửi lệnh SET
       v
Redis key -> chuỗi byte value
       |
       | client GET, nhận byte[]
       v
JSON bytes
       |
       | value deserializer + kiểu đích
       v
Java ProductSnapshot
~~~

JSON ở đây chỉ là một **định dạng bên trong Redis String**. Redis không tự hiểu object `ProductSnapshot` và cũng không tự chuyển JSON thành Redis Hash. Khi sử dụng `opsForValue().set(...)`, Redis lưu giá trị theo kiểu String bất kể value là text, JSON hay binary.

Ví dụ:

~~~redis
TYPE shop:product:42
GET shop:product:42
TTL shop:product:42
~~~

Nếu key được ghi bằng `StringRedisSerializer` và JSON value serializer, Redis CLI có thể đọc tên key và JSON. Nếu key được ghi bằng Java native serialization, tên key có thể chứa byte nhị phân và câu lệnh `GET shop:product:42` sẽ không tìm thấy key mà bạn tưởng là cùng tên.

### 2.1. Key và value có thể dùng hai serializer hoàn toàn khác nhau

Một `RedisTemplate<K, V>` thường có bốn vị trí serializer:

| Thiết lập | Dữ liệu được chuyển đổi | Lựa chọn dễ quản lý |
| --- | --- | --- |
| `setKeySerializer(...)` | Key của các lệnh như `GET`, `SET`, `DEL` | `StringRedisSerializer` |
| `setValueSerializer(...)` | Value của các lệnh theo key như `GET`/`SET` | JSON serializer đúng loại dữ liệu |
| `setHashKeySerializer(...)` | Field trong Redis Hash, ví dụ `name`, `price` | `StringRedisSerializer` |
| `setHashValueSerializer(...)` | Value của field trong Redis Hash | Tùy schema: String, JSON hoặc serializer phù hợp |

**Không nên dùng JSON serializer cho key thông thường chỉ vì value là JSON.** String key có thể đọc trực tiếp qua CLI, dễ theo dõi namespace và có ý nghĩa rõ ràng khi nhiều hệ thống cùng truy cập Redis.

### 2.2. JSON không tự động giữ nguyên mọi đặc tính Java

Ví dụ JSON:

~~~json
{"id":"42","price":590000}
~~~

không nói rõ `price` phải là `BigDecimal` hay `Integer`, không nói class Java nào tạo ra object, và không chứa version schema nếu ứng dụng không thiết kế. Khi deserialization, client phải có một **kiểu đích** hoặc **thông tin kiểu hợp lệ** để tái tạo dữ liệu.

Điều này giải thích tại sao typed serializer và generic serializer hoạt động khác nhau.

## 3. Bản đồ phiên bản: Spring Data Redis 3.x và 4.x

Trước khi sao chép một ví dụ JSON serializer, hãy xác định phiên bản thực tế của **Spring Boot, Spring Data Redis và Jackson** mà build đang sử dụng. Spring Boot thường quản lý các version thông qua BOM/dependency management; không nên chỉ đổi riêng artifact Spring Data Redis hoặc Jackson khi chưa kiểm tra tính tương thích.

| Hạng mục | Spring Data Redis 3.x (thường đi với Boot 3.x) | Spring Data Redis 4.x (thường đi với Boot 4.x) |
| --- | --- | --- |
| Thư viện JSON chính | Jackson 2 | Jackson 3 |
| Package `ObjectMapper` | `com.fasterxml.jackson.databind.ObjectMapper` | `tools.jackson.databind.ObjectMapper` |
| JSON serializer có kiểu đích | `Jackson2JsonRedisSerializer<T>` | `JacksonJsonRedisSerializer<T>` |
| JSON serializer generic | `GenericJackson2JsonRedisSerializer` | `GenericJacksonJsonRedisSerializer` |
| Mapper JSON ↔ Redis Hash | `Jackson2HashMapper` | `JacksonHashMapper` |
| Hành vi generic mặc định | Jackson 2 generic serializer thường bật default typing khi tự khởi tạo | Jackson 3 generic serializer **không tự bật default typing** |
| `RedisSerializer.json()` | Trước 4.0 dùng generic Jackson 2 | Từ 4.0 chuyển sang generic Jackson 3 |
| Trạng thái API Jackson 2 | API chính trên nhánh 3.x | Bị đánh dấu deprecated for removal trên nhánh 4.x |

**Điểm dễ bị nhầm:** Tên serializer Jackson 3 trong Spring Data Redis 4.x là `JacksonJsonRedisSerializer` và `GenericJacksonJsonRedisSerializer`. Một số tài liệu của bản 4.0 milestone cũ từng nhắc đến tên có chữ `Jackson3`; khi viết code cho bản ổn định, phải đối chiếu JavaDoc đúng phiên bản đang dùng.

Trong Jackson 3, phần lớn API chuyển package từ `com.fasterxml.jackson.*` sang `tools.jackson.*`. **Ngoại lệ đáng chú ý:** nhiều annotation Jackson vẫn ở package `com.fasterxml.jackson.annotation.*`, theo hướng dẫn migration. Đừng đổi import annotation theo cảm tính.

### 3.1. Cách xác định phiên bản đang chạy

Với Maven, có thể kiểm tra dependency tree:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.data:spring-data-redis
./mvnw dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
./mvnw dependency:tree -Dincludes=tools.jackson.core:jackson-databind
~~~

Với Gradle, dùng `dependencies` hoặc `dependencyInsight`:

~~~bash
./gradlew dependencyInsight --dependency spring-data-redis --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Đây là các lệnh gợi ý cho người học sử dụng trong dự án thực hành, không yêu cầu chạy trong quá trình soạn bài. Với Windows, sử dụng `mvnw.cmd` hoặc `gradlew.bat` nếu môi trường không hỗ trợ script Unix.

Ngoài tên thư viện, nên xem cả version Spring Boot được khai báo ở parent/BOM, tập starter dùng và Java runtime. **Kết quả dependency tree mới là nguồn cho biết class nào thực sự có mặt trên classpath.**

## 4. Chọn serializer theo loại dữ liệu và mức độ linh hoạt

| Serializer / cách lưu | Dùng cho | Ưu điểm | Giới hạn và lưu ý |
| --- | --- | --- | --- |
| `StringRedisSerializer` | Key, text, mã ngắn, số dạng chuỗi | Đơn giản; Redis CLI đọc được | Không tự chuyển JSON thành object |
| `Jackson2JsonRedisSerializer<T>` (3.x) | Một kiểu DTO/record xác định | JSON rõ ràng, typed khi đọc | Phụ thuộc Jackson 2; biết đúng target type |
| `JacksonJsonRedisSerializer<T>` (4.x) | Một kiểu DTO/record xác định | Tương ứng Jackson 3, dễ kiểm soát schema | Cần cấu hình Jackson 3 đúng version |
| `GenericJackson2JsonRedisSerializer` (3.x) | Nhiều kiểu Java được lưu dưới `Object` | Có cơ chế metadata kiểu runtime | Metadata có thể gắn tên class; rủi ro bảo mật và migration |
| `GenericJacksonJsonRedisSerializer` (4.x) | Dữ liệu generic dùng Jackson 3 | Có builder để kiểm soát typing | **Không bật typing mặc định**; cần quyết định cách khôi phục loại |
| `JdkSerializationRedisSerializer` | Hệ thống Java cũ đã dùng Java binary serialization | Có thể khôi phục object Java trong điều kiện phù hợp | Khó debug, gắn chặt class Java, vấn đề an toàn và tương thích |
| `RedisSerializer.byteArray()` | Dữ liệu đã có codec riêng, binary protocol | Không biến đổi thêm nội dung | Ứng dụng tự chịu trách nhiệm định dạng bytes |
| Redis Hash với string fields | Các thuộc tính nhỏ cần thao tác riêng | `HGET`/`HSET` cho từng field | Cần quy ước schema, kiểu field và TTL của toàn key |

### 4.1. Quyết định đầu tiên: typed JSON hay generic JSON?

**Typed JSON** phù hợp nhất khi một namespace hoặc một cache chứa cùng một dạng DTO:

~~~text
shop:product:42  -> ProductSnapshot
shop:product:43  -> ProductSnapshot
shop:product:44  -> ProductSnapshot
~~~

Ứng dụng biết trước kiểu `ProductSnapshot` khi đọc, nên JSON có thể không cần chứa tên class Java. Điều này thường giúp định dạng gọn, dễ chia sẻ và giảm phụ thuộc vào tên package trong code.

**Generic JSON** hữu ích khi cùng một đường đọc phải xử lý nhiều kiểu runtime:

~~~text
cache:shared:key-A  -> ProductSnapshot
cache:shared:key-B  -> CustomerSummary
cache:shared:key-C  -> InventoryNotice
~~~

Nếu template khai báo `RedisTemplate<String, Object>`, generic deserializer phải biết cách xác định kiểu thực tế. Chỉ có `Object` và JSON thuần thì thường khôi phục thành `Map`/`List`/scalar hoặc một cấu trúc chung, **không tự tái tạo đúng record/class nghiệp vụ**. Muốn khôi phục subtype cần cơ chế có type information được thiết kế chặt chẽ.

**Lựa chọn khởi đầu cho phần lớn hệ thống:** key dạng String, value dùng typed JSON cho DTO có schema rõ ràng, cache được phân vùng theo loại dữ liệu. Chỉ cân nhắc generic khi thật sự phải hỗ trợ đa hình.

### 4.2. Vì sao không dùng một `RedisTemplate<String, Object>` cho mọi chỗ?

Khai báo generic `Object` giúp service nhận nhiều loại dữ liệu, nhưng đánh đổi:

1. Trình biên dịch không kiểm tra được cùng một key luôn chứa đúng DTO.
2. Deserializer có thể trả về `LinkedHashMap` thay vì class mong muốn nếu thiếu type metadata.
3. Type metadata có thể phụ thuộc tên class/package, khiến refactor làm dữ liệu cũ không đọc được.
4. Cấu hình default typing không được kiểm soát có rủi ro deserialization dữ liệu không đáng tin.
5. Một module có thể vô tình ghi đè key của module khác bằng schema khác.

Nếu thiết kế ứng dụng cho phép, **một template typed cho một nhóm dữ liệu có chủ đích** dễ kiểm soát hơn.

## 5. Ví dụ nền tảng dùng chung: ProductSnapshot

Các ví dụ tiếp theo sử dụng Java 17+, Spring Boot có Redis starter và Redis server đang chạy. Model tối giản:

~~~java
package com.example.redis;

import java.math.BigDecimal;

public record ProductSnapshot(
        String id,
        String name,
        BigDecimal price
) {}
~~~

Một số dữ liệu sẽ được lưu dưới key:

~~~text
shop:v1:product:42
shop:v1:product:43
~~~

Prefix `shop:v1` là ví dụ về namespace/version schema; **không bắt buộc phải dùng đúng tên này**. Sản phẩm ví dụ có `BigDecimal` để tránh việc dùng `double` tùy tiện cho giá tiền. Trong hệ thống thật, còn phải thống nhất đơn vị tiền tệ, cách làm tròn, version JSON và quy tắc xử lý thiếu field.

Tập Maven dependency cơ bản khi dùng Spring Boot đã quản lý version:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-json</artifactId>
    </dependency>
</dependencies>
~~~

Đây chỉ là khối dependency; dự án còn cần parent/BOM hoặc cấu hình build Spring Boot thích hợp. Spring Boot 3.x dùng Jackson 2 mặc định trong starter JSON; Spring Boot 4.x chuyển Jackson 3 thành lựa chọn mặc định. Nếu dự án có module JSON khác hoặc BOM tùy biến, phải kiểm tra dependency tree và tính tương thích trước khi dùng code mẫu.

Ví dụ cấu hình Redis local:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Nếu ứng dụng chạy trong Docker cùng Redis, `localhost` bên trong container ứng dụng không trỏ sang container Redis. Dùng hostname/service phù hợp với mạng thực tế. Không ghi thông tin xác thực Redis production trực tiếp vào source code.

## 6. Cấu hình typed JSON cho Spring Data Redis 3.x (Jackson 2)

Đây là nhánh thường gặp trong ứng dụng **Spring Boot 3.x / Spring Data Redis 3.x**. Class cần dùng:

~~~java
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
~~~

**Không thay class này bằng `JacksonJsonRedisSerializer` khi dự án vẫn dùng Spring Data Redis 3.x** vì class mới chưa có trong nhánh tương ứng.

Tạo file `ProductRedisConfig.java`:

~~~java
package com.example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class ProductRedisConfig {

    @Bean("productRedisTemplate")
    public RedisTemplate<String, ProductSnapshot> productRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, ProductSnapshot> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer keySerializer = new StringRedisSerializer();
        Jackson2JsonRedisSerializer<ProductSnapshot> valueSerializer =
                new Jackson2JsonRedisSerializer<>(ProductSnapshot.class);

        template.setKeySerializer(keySerializer);
        template.setValueSerializer(valueSerializer);

        // Nếu thao tác Redis Hash, cần chọn serializer cho field/value.
        template.setHashKeySerializer(keySerializer);
        template.setHashValueSerializer(valueSerializer);

        return template;
    }
}
~~~

**Giải thích:**

- `RedisConnectionFactory` được Spring Boot cấp tự động khi dùng Redis starter và có cấu hình hợp lệ. Không cần tạo thêm factory thủ công cho bài học serializer.
- `keySerializer` chuyển key String thành bytes dễ đọc trong Redis CLI.
- `valueSerializer` chuyển `ProductSnapshot` thành JSON bytes và biết cách khôi phục đúng `ProductSnapshot.class`.
- `hashValueSerializer` ở ví dụ giả định Hash field có value là nguyên object `ProductSnapshot`. Nếu Hash của bạn có field string như `name`/`price`, cần serializer khác phù hợp với schema. Đừng dùng kiểu này cho mọi Hash theo mặc định.
- `@Bean("productRedisTemplate")` giúp service inject đúng bean khi ứng dụng có nhiều `RedisTemplate`. Spring sẽ gọi vòng đời khởi tạo template thích hợp khi bean được quản lý.

Khi muốn tùy chỉnh cách Jackson 2 đọc/ghi, có thể truyền `com.fasterxml.jackson.databind.ObjectMapper` qua constructor (không sử dụng phương thức `setObjectMapper(...)` đã bị deprecated từ nhánh 3.0):

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;

// objectMapper: bean Jackson 2 đã được cấu hình phù hợp bởi ứng dụng.
Jackson2JsonRedisSerializer<ProductSnapshot> valueSerializer =
        new Jackson2JsonRedisSerializer<>(
                objectMapper,
                ProductSnapshot.class
        );
~~~

Với dữ liệu `Instant`, `LocalDateTime`, enum hoặc custom value object, hãy kiểm tra mapper có module/feature cần thiết và các định dạng date/time phải tương thích giữa các lần triển khai. Việc HTTP JSON trả đúng không đảm bảo mapper Redis tự dùng cùng một cấu hình nếu bạn tạo `new ObjectMapper()` riêng.

## 7. Cấu hình typed JSON cho Spring Data Redis 4.x (Jackson 3)

Từ Spring Data Redis 4.0, class tương ứng là:

~~~java
import org.springframework.data.redis.serializer.JacksonJsonRedisSerializer;
~~~

Đây là **JSON typed serializer trên Jackson 3**. Nếu code vẫn import `Jackson2JsonRedisSerializer` ở nhánh 4.x, API cũ hiện được đánh dấu deprecated for removal và nên được thay thế khi có kế hoạch migrate dữ liệu.

Với model `ProductSnapshot` giống phần 5, bean cấu hình:

~~~java
package com.example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.JacksonJsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class ProductRedisConfig {

    @Bean("productRedisTemplate")
    public RedisTemplate<String, ProductSnapshot> productRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, ProductSnapshot> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer keySerializer = new StringRedisSerializer();
        JacksonJsonRedisSerializer<ProductSnapshot> valueSerializer =
                new JacksonJsonRedisSerializer<>(ProductSnapshot.class);

        template.setKeySerializer(keySerializer);
        template.setValueSerializer(valueSerializer);
        template.setHashKeySerializer(keySerializer);
        template.setHashValueSerializer(valueSerializer);

        return template;
    }
}
~~~

**Không khai báo cả hai class `ProductRedisConfig` của phần 6 và 7 trong cùng dự án.** Chọn đúng một cấu hình theo dòng Spring Data Redis đang sử dụng. Về kiến trúc, hai ví dụ đều tạo RedisTemplate có key String và value JSON typed; khác biệt nằm ở API serializer và thư viện JSON bên dưới.

Khi cần tùy chỉnh Jackson 3 mapper, import từ `tools.jackson.databind.*` (ví dụ `tools.jackson.databind.ObjectMapper`) và sử dụng constructor/builder tương ứng mà JavaDoc phiên bản đó hỗ trợ. Trong Spring Boot 4, JSON mapper mặc định thường được auto-configure dưới dạng `tools.jackson.databind.json.JsonMapper`. Không truyền nhầm `com.fasterxml.jackson.databind.ObjectMapper` của Jackson 2 vào serializer Jackson 3.

### 7.1. Vì sao không thể chỉ đổi tên class để hoàn tất migration?

Khác biệt giữa Jackson 2 và Jackson 3 không chỉ là tên:

- Package và một số API mapper/reader/writer khác nhau.
- Default configuration và cách đăng ký module có thể thay đổi.
- Serialized JSON có thể khác ở chi tiết typing, giá trị null, date/time hoặc type metadata.
- Một số class DTO cũ có annotation/config cần kiểm tra lại.
- Dữ liệu Redis còn tồn tại từ phiên bản cũ sẽ được phiên bản mới đọc; chúng không tự đổi định dạng sau khi nâng cấp dependency.

**Muốn nâng cấp an toàn, phải kiểm tra wire format thực tế** và thiết kế cách xử lý key cũ trước khi deploy đồng thời nhiều phiên bản ứng dụng.

## 8. Sử dụng RedisTemplate typed trong service

Service không cần quan tâm ứng dụng dùng Jackson 2 hay Jackson 3 nếu bean `productRedisTemplate` có cùng kiểu:

~~~java
package com.example.redis;

import java.time.Duration;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductSnapshotService {

    private final RedisTemplate<String, ProductSnapshot> redis;

    public ProductSnapshotService(
            @Qualifier("productRedisTemplate")
            RedisTemplate<String, ProductSnapshot> redis) {
        this.redis = redis;
    }

    public void put(ProductSnapshot product) {
        if (product == null || product.id() == null
                || product.id().isBlank()) {
            throw new IllegalArgumentException("Product ID is required");
        }

        redis.opsForValue().set(
                key(product.id()),
                product,
                Duration.ofMinutes(10)
        );
    }

    public Optional<ProductSnapshot> get(String id) {
        return Optional.ofNullable(redis.opsForValue().get(key(id)));
    }

    public boolean remove(String id) {
        return Boolean.TRUE.equals(redis.delete(key(id)));
    }

    private String key(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Product ID is required");
        }
        return "shop:v1:product:" + id;
    }
}
~~~

**Khi chạy:** `put(...)` ghi một Redis String chứa JSON và đặt TTL 10 phút; `get(...)` dùng cùng value serializer để khôi phục `ProductSnapshot`; `remove(...)` xóa key. Trường hợp cache miss trả `Optional.empty()`, không nên coi đó là lỗi JSON.

Ví dụ sử dụng trong một method có inject `ProductSnapshotService`:

~~~java
var product = new ProductSnapshot(
        "42", "Bàn phím", new java.math.BigDecimal("590000")
);
productSnapshotService.put(product);
System.out.println(productSnapshotService.get("42"));
~~~

Không nên đặt đoạn demo ghi dữ liệu vào startup của production. Dữ liệu Redis có thể giữ lâu hơn vòng đời process, nên code thật cần quy ước key namespace và cách xử lý schema cũ.

## 9. Typed JSON với generic JSON khác nhau ở type metadata

### 9.1. Typed serializer có sẵn kiểu đích

~~~java
new Jackson2JsonRedisSerializer<>(ProductSnapshot.class); // Redis 3.x
new JacksonJsonRedisSerializer<>(ProductSnapshot.class);  // Redis 4.x
~~~

Hai đoạn trên thuộc **hai dòng phiên bản khác nhau**, không được sử dụng cùng nhau trong một project. Cả hai đều biết trước `ProductSnapshot.class`. JSON value thường có thể ở dạng:

~~~json
{"id":"42","name":"Bàn phím","price":590000}
~~~

Deserializer có đủ thông tin để tạo object `ProductSnapshot`. Khi toàn bộ dữ liệu trong một namespace là cùng một kiểu, đây là hợp đồng dữ liệu đơn giản và phù hợp.

### 9.2. Generic serializer và trường `@class`

Generic serializer trong Jackson 2 thường dùng dynamic/default typing để kèm thông tin class. Một JSON minh họa có thể trông như:

~~~json
{
  "@class": "com.example.redis.ProductSnapshot",
  "id": "42",
  "name": "Bàn phím",
  "price": 590000
}
~~~

Hình dạng cụ thể có thể khác tùy mapper, kiểu object, cấu hình typing và phiên bản; không được coi `@class` luôn luôn có mặt trong mọi value. Type metadata giúp deserializer biết class thực tế khi template đọc dưới kiểu `Object`, nhưng làm dữ liệu Redis phụ thuộc vào tên package và class phía Java.

Nếu đổi package từ `com.example.redis.ProductSnapshot` sang `com.example.catalog.ProductSnapshot`, dữ liệu cũ chứa tên class trước đó có thể không còn deserialize được. Đây là một lý do cần cân nhắc typed DTO, namespace version và migration.

### 9.3. Thay đổi quan trọng từ Spring Data Redis 4.0

Trên nhánh 3.x:

~~~java
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;

GenericJackson2JsonRedisSerializer serializer =
        new GenericJackson2JsonRedisSerializer();
~~~

Nhà phát triển thường sử dụng class này cho `RedisTemplate<String, Object>` hoặc cấu hình Redis Cache giữ nhiều kiểu object. Constructor không đối số của serializer Jackson 2 có cơ chế dynamic typing mặc định, nhưng **không nên sử dụng một cách thiếu kiểm soát với dữ liệu không đáng tin**.

Trên nhánh 4.x:

~~~java
import org.springframework.data.redis.serializer.GenericJacksonJsonRedisSerializer;

GenericJacksonJsonRedisSerializer serializer =
        GenericJacksonJsonRedisSerializer.builder().build();
~~~

**Đừng giả định hai đoạn này có hành vi giống hệt nhau.** Theo tài liệu nâng cấp Spring Data Redis, generic serializer Jackson 3 **không kích hoạt default typing theo mặc định**. Vì thế, khi chỉ đọc dưới kiểu `Object`, kết quả có thể là cấu trúc chung thay vì DTO Java mong muốn.

Nếu thực sự cần khôi phục nhiều kiểu runtime, phải quyết định rõ cách định danh kiểu và **giới hạn loại class được phép deserialize**.

### 9.4. Bật default typing trong 4.x phải có ràng buộc kiểu

Spring Data Redis 4.x cung cấp:

~~~java
GenericJacksonJsonRedisSerializer.builder()
        .enableDefaultTyping(typeValidator)
        .build();
~~~

Tham số `typeValidator` là `tools.jackson.databind.jsontype.PolymorphicTypeValidator` được ứng dụng tạo với quy tắc cho phép những loại thực sự cần thiết. Có thể dùng `BasicPolymorphicTypeValidator` và allow-list theo package/class nghiệp vụ được tin cậy:

~~~java
import org.springframework.data.redis.serializer.GenericJacksonJsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializer;
import tools.jackson.databind.jsontype.BasicPolymorphicTypeValidator;
import tools.jackson.databind.jsontype.PolymorphicTypeValidator;

PolymorphicTypeValidator validator =
        BasicPolymorphicTypeValidator.builder()
                .allowIfSubType("com.example.redis.dto.")
                .build();

RedisSerializer<Object> serializer =
        GenericJacksonJsonRedisSerializer.builder()
                .enableDefaultTyping(validator)
                .build();
~~~

Đoạn này minh họa ý tưởng **allow-list cho DTO trong package do ứng dụng kiểm soát**, không phải cấu hình đã hoàn chỉnh cho mọi object graph. Nếu DTO chứa collection, wrapper hoặc subtype cần thiết, validator phải được thiết kế và kiểm tra để xử lý đúng các kiểu này. Không dùng validator cho phép tùy ý tất cả class chỉ để tránh lỗi deserialization.

**Rủi ro bảo mật:** Polymorphic/default typing với nguồn JSON không đáng tin có thể gây deserialization nguy hiểm nếu cho phép tùy ý class. Redis không mặc nhiên là nguồn an toàn: attacker có thể tìm cách ghi dữ liệu vào Redis thông qua một lỗ hổng khác, service tích hợp hoặc key bị chia sẻ sai quyền. Cần hạn chế quyền ghi Redis, không cho client cung cấp tùy ý type metadata, và ưu tiên typed DTO nếu có thể.

## 10. Chọn đúng serializer cho Spring Cache Redis

Spring Cache được sử dụng với annotation như `@Cacheable`, `@CachePut` và `@CacheEvict`. Khi backend là Redis, Spring sử dụng `RedisCacheManager`/`RedisCacheConfiguration` để cấu hình key/value serializer cho **cache entries**.

**Điểm dễ sai:** bạn tạo `RedisTemplate<String, ProductSnapshot>` dùng JSON nhưng `@Cacheable` vẫn có thể dùng serializer khác. Việc thay serializer trên một `RedisTemplate` **không tự thay cấu hình `RedisCacheManager`**.

Theo cấu hình mặc định của Spring Data Redis, Redis Cache thường có:

| Thành phần | Mặc định quan trọng |
| --- | --- |
| Key serializer | `StringRedisSerializer` |
| Value serializer | `JdkSerializationRedisSerializer` |
| Prefix cache key | Theo tên cache, thường là `cacheName::key` |
| TTL | Không đặt thời gian hết hạn mặc định nếu chưa cấu hình |
| Cache null | Có thể được phép theo cấu hình mặc định |

Nếu muốn cache value JSON, hãy cấu hình `RedisCacheConfiguration` riêng. Ví dụ dưới đây dành cho **một ứng dụng chỉ cache `ProductSnapshot` bằng CacheManager này**:

### 10.1. Redis Cache JSON cho Spring Data Redis 3.x

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;

@Configuration(proxyBeanMethods = false)
public class ProductCacheConfig {

    @Bean
    RedisCacheManager cacheManager(RedisConnectionFactory factory) {
        var valueSerializer =
                new Jackson2JsonRedisSerializer<>(ProductSnapshot.class);

        RedisCacheConfiguration config =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(10))
                        .disableCachingNullValues()
                        .serializeValuesWith(
                                RedisSerializationContext.SerializationPair
                                        .fromSerializer(valueSerializer)
                        );

        return RedisCacheManager.builder(factory)
                .cacheDefaults(config)
                .build();
    }
}
~~~

### 10.2. Redis Cache JSON cho Spring Data Redis 4.x

Thay riêng phần tạo serializer bằng API Jackson 3:

~~~java
import org.springframework.data.redis.serializer.JacksonJsonRedisSerializer;

var valueSerializer =
        new JacksonJsonRedisSerializer<>(ProductSnapshot.class);
~~~

Các dòng cấu hình `RedisCacheConfiguration` với `serializeValuesWith(...)` giữ cùng ý tưởng. **Hai snippet thuộc hai phiên bản khác nhau**, không đưa đồng thời cả hai serializer vào cùng class.

### 10.3. Vì sao ví dụ trên chỉ dành cho một loại value?

Khi đặt `cacheDefaults(config)`, serializer JSON typed sẽ áp dụng cho các cache không có cấu hình riêng. Nếu ứng dụng có thêm cache trả `CustomerSummary` hoặc `List<OrderDto>`, chúng không tự nhiên phù hợp với `ProductSnapshot.class`.

Ứng dụng thực tế thường chọn một trong các cách:

1. Mỗi cache name có một `RedisCacheConfiguration` với serializer đúng loại trả về, khai báo qua `withInitialCacheConfigurations(...)`.
2. Dùng generic serializer **có kiểm soát type và bảo mật** nếu yêu cầu nhiều kiểu value thật sự không thể tách.
3. Thiết kế một cache DTO/envelope có schema ổn định mà mọi value cùng tuân thủ.

Ví dụ khi dùng `@Cacheable(cacheNames = "productSnapshot", key = "#id")`, method được cache nên trả về đúng kiểu mà serializer của cache `productSnapshot` xử lý. Không cache một phương thức trả `String` vào cùng vùng được cấu hình cố định là `ProductSnapshot`.

### 10.4. Null và cache miss

Cần phân biệt:

- **Key không tồn tại:** Redis GET trả nil, sau đó Spring Cache xem như cache miss.
- **Giá trị method thực sự là `null`:** Có thể được cache thành một marker đặc biệt nếu bật cache-null-values; serializer phải hỗ trợ trường hợp này.
- **JSON literal `null`:** Không nhất thiết giống cách Spring Cache biểu diễn `NullValue`.
- **Key tồn tại nhưng value không deserialize được:** Đó là lỗi dữ liệu/schema, không thể coi là cache miss thành công.

Trong các ví dụ typed ở trên, `disableCachingNullValues()` giúp tránh phức tạp về marker null cho bài thực hành. Nếu nghiệp vụ cần negative caching (cache kết quả “không tồn tại”), phải chọn serializer và chiến lược biểu diễn kết quả vắng mặt một cách rõ ràng.

Với generic Jackson 3, builder có khả năng hỗ trợ Spring Cache null marker khi được cấu hình thích hợp; cần đồng bộ với cơ chế typing. Không nên sao chép cấu hình cache null từ Jackson 2 mà không kiểm tra trên Spring Data Redis 4.x.

## 11. Type erasure và generic collection: tại sao đọc ra List<Map>?

Giả sử muốn lưu:

~~~java
List<ProductSnapshot> products = List.of(
        new ProductSnapshot("42", "Bàn phím", new BigDecimal("590000")),
        new ProductSnapshot("43", "Chuột", new BigDecimal("240000"))
);
~~~

Trong Java, `List<ProductSnapshot>.class` không tồn tại vì generic type bị xóa ở runtime. Nếu chỉ cung cấp `List.class` khi deserialize JSON, phần tử có thể trở thành `LinkedHashMap` thay vì `ProductSnapshot`.

Với **Jackson 2 / Spring Data Redis 3.x**, có thể dùng `JavaType` tường minh:

~~~java
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;

ObjectMapper mapper = new ObjectMapper();
JavaType listType = mapper.getTypeFactory()
        .constructCollectionType(List.class, ProductSnapshot.class);

Jackson2JsonRedisSerializer<List<ProductSnapshot>> serializer =
        new Jackson2JsonRedisSerializer<>(mapper, listType);
~~~

Đây là đoạn cho nhánh Jackson 2. Với Spring Data Redis 4.x, dùng API `JacksonJsonRedisSerializer` và Jackson 3 `JavaType`/mapper tương ứng theo JavaDoc phiên bản đó; **không trộn `com.fasterxml.jackson.databind.JavaType` vào constructor đòi `tools.jackson.databind.JavaType`**.

Nếu nhiều module cần một kiểu collection, cân nhắc tạo DTO wrapper rõ ràng:

~~~java
public record ProductBatch(
        String batchId,
        List<ProductSnapshot> products
) {}
~~~

Khi đó template có thể lưu một `ProductBatch` cụ thể. Wrapper có thể mang thêm version, thời điểm tạo và thông tin nghiệp vụ, đồng thời tránh một số vấn đề type erasure tại ranh giới Redis.

## 12. Redis Hash: serializer khác với hash mapper

Một key Redis Hash có thể trông như:

~~~redis
HSET shop:product:42 name "Bàn phím" price "590000"
HGETALL shop:product:42
~~~

Trong trường hợp này:

- Key tổng `shop:product:42` là String.
- Hash field `name`, `price` là String.
- Hash values `Bàn phím`, `590000` cũng có thể là String.

Một cấu hình đơn giản:

~~~java
template.setKeySerializer(new StringRedisSerializer());
template.setHashKeySerializer(new StringRedisSerializer());
template.setHashValueSerializer(new StringRedisSerializer());
~~~

Nếu template có generic type `RedisTemplate<String, ProductSnapshot>`, phải hiểu rằng cấu hình này dành cho các Hash field có giá trị chuỗi; dùng template riêng cho Hash hoặc `StringRedisTemplate` giúp giảm mơ hồ kiểu Java khi thao tác.

**Hash mapper** như `Jackson2HashMapper` (3.x) hay `JacksonHashMapper` (4.x) là một cơ chế khác: nó biến object thành tập field/value rồi ánh xạ sang Redis Hash. Nó **không tương đương** với đặt một JSON String vào mỗi hash field.

Ví dụ một object:

~~~json
{"id":"42","name":"Bàn phím","price":590000}
~~~

có thể biểu diễn bằng:

~~~text
Redis String key:
  shop:product:42 -> '{"id":"42","name":"Bàn phím","price":590000}'

Redis Hash key:
  shop:product:42 -> { id: '42', name: 'Bàn phím', price: '590000' }
~~~

Hai trường hợp khác loại Redis data structure: ở CLI, `TYPE key` trả `string` hoặc `hash`. Nếu đọc Hash bằng `GET` sẽ gặp lỗi `WRONGTYPE`; nếu đọc JSON String bằng `HGETALL` cũng vậy.

Spring Data Redis 4.x có thay thế `Jackson2HashMapper` bằng `JacksonHashMapper`. Khi migrate Redis Hash, cần kiểm tra định dạng **flattened** hay **hierarchical**, tên field và cách đọc value cũ. Tài liệu migration có tùy chọn compatibility mode cho trường hợp dữ liệu Jackson 2 Hash mapper.

## 13. Mặc định của RedisTemplate khác với mặc định bạn mong muốn

Nhiều lỗi đến từ việc khai báo:

~~~java
RedisTemplate<String, ProductSnapshot> template = new RedisTemplate<>();
template.setConnectionFactory(connectionFactory);
return template;
~~~

và nghĩ rằng generic `<String, ProductSnapshot>` đã tự tạo serializer String/JSON. **Không phải vậy.** Generic type trong Java không tự đổi các serializer mặc định của `RedisTemplate`; các template không cấu hình rõ có thể dùng Java native serialization.

Hệ quả:

- Key được mã hóa theo định dạng nhị phân nên CLI không hiển thị bằng chuỗi mong đợi.
- Value là bytes Java serialization, không phải JSON.
- Một template khác dùng String serializer đọc cùng key hiển thị trong code nhưng gửi bytes khác.
- Sau khi đổi class/package Java, dữ liệu binary cũ khó tương thích hơn.

Để dùng JSON, hãy đặt tường minh ít nhất key và value serializer. Nếu ứng dụng thao tác Hash, xác định luôn hash-key/hash-value serializer phù hợp.

`StringRedisTemplate` là một lựa chọn tốt cho những dữ liệu vốn là String, ví dụ counter, token ngắn hạn, trạng thái đơn giản. Không nên cố đưa object Java tùy ý vào `StringRedisTemplate` rồi quên khâu tự convert JSON khi đọc.

## 14. Lựa chọn serializer theo tình huống thực tế

### Tình huống A: Cache chi tiết sản phẩm

**Yêu cầu:** một cache tên `productSnapshot` lưu một DTO `ProductSnapshot`, có TTL 10 phút.

**Lựa chọn:** typed JSON tương ứng version Spring Data Redis, key String, một cache namespace riêng. Không cần type metadata theo tên class Java nếu value type cố định.

### Tình huống B: Lưu bộ đếm

**Yêu cầu:** tăng lượt xem sản phẩm bằng `INCR`, đọc số bằng CLI.

**Lựa chọn:** `StringRedisTemplate` với String serializer. Redis `INCR` hiểu giá trị biểu diễn số nguyên, không cần JSON DTO. Cũng không nên lưu một JSON như `{"count":5}` rồi đọc/ghi cả object cho mỗi lần tăng.

### Tình huống C: Một CacheManager chứa nhiều kiểu kết quả

**Yêu cầu:** cache nhiều method trả về các loại DTO không đồng nhất.

**Lựa chọn:** ưu tiên cấu hình serializer theo cache name; nếu thật sự cần generic, dùng serializer phù hợp version và cơ chế type metadata chặt chẽ. Trên 4.x phải chú ý generic serializer không bật default typing mặc định.

### Tình huống D: Hai ứng dụng Java và Node.js dùng chung dữ liệu

**Yêu cầu:** cùng đọc/ghi các key sản phẩm.

**Lựa chọn:** JSON có schema ổn định, key String, định nghĩa rõ timestamp, decimal, enum, field naming và version. Tránh metadata phụ thuộc tên class Java, đặc biệt khi Node.js không hiểu các class đó.

### Tình huống E: Redis Hash cập nhật từng field

**Yêu cầu:** thay đổi trạng thái hoặc giá không cần ghi lại toàn bộ JSON lớn.

**Lựa chọn:** Redis Hash với field serializer phù hợp, hoặc một hash mapper được cấu hình rõ. Không mặc định rằng JSON serializer trên `opsForValue()` tự hỗ trợ `HSET` field.

### Tình huống F: Dự án cũ lưu JDK binary

**Yêu cầu:** chuyển dữ liệu sang JSON mà không làm hỏng cache sống.

**Lựa chọn:** xác định cache có tái tạo được không, kiểm kê key cũ, dùng versioned namespace hoặc rollout/migration có kiểm soát. Đổi serializer mà giữ key cũ có thể dẫn tới lỗi đọc dữ liệu trước đó.

## 15. Migration Jackson 2 → Jackson 3: dữ liệu không tự nâng cấp

Khi nâng cấp Spring Data Redis 3.x lên 4.x, mục tiêu không chỉ là **code compile**. Redis có thể chứa hàng triệu key được serializer Jackson 2 ghi vào ngày hôm trước, trong khi process mới bắt đầu đọc bằng Jackson 3.

### 15.1. Rủi ro thường gặp

1. **Định dạng JSON thay đổi:** property naming, null, dates hoặc type metadata khác giữa mapper phiên bản trước/sau.
2. **Generic type metadata khác:** kiểu runtime trước đây được lưu theo cách mà serializer mới không đọc hoặc không diễn giải tương ứng.
3. **Tên class Java thay đổi:** metadata `@class` trỏ đến class đã đổi package.
4. **Rolling deployment:** instance cũ và mới cùng đọc/ghi một key, tạo race giữa hai định dạng.
5. **Cache null marker:** cách encode marker thay đổi, gây lỗi khi đọc cache null.
6. **Hash format:** Hash mapper 3.x và 4.x có thể khác cách ánh xạ field.
7. **Dữ liệu tồn tại lâu:** TTL vô hạn khiến những key cũ khó biến mất nếu chỉ deploy code mới.

### 15.2. Chiến lược đơn giản nhất với cache có thể tái tạo

Nếu Redis chỉ lưu **cache** và database là nguồn chính:

~~~text
Phiên bản cũ:
  shop:v1:product:42  -> Jackson 2 bytes

Phiên bản mới:
  shop:v2:product:42  -> Jackson 3 bytes
~~~

Thay prefix/key namespace để version mới không đọc nhầm dữ liệu cũ. Trong thời gian rolling deployment, version cũ tiếp tục dùng `v1`, version mới dùng `v2`. Sau khi instance cũ đã ngừng, để key cũ hết TTL hoặc xóa có kiểm soát bằng quy trình phù hợp.

Ưu điểm: ít phức tạp hơn so với đọc/ghi đa định dạng trên cùng một key. Nhược điểm: cache mới bắt đầu lạnh, cần đánh giá tải dồn lên database.

**Không tự động `FLUSHALL`/`FLUSHDB` trên production** chỉ vì đổi serializer. Các lệnh đó xóa nhiều dữ liệu ngoài phạm vi tính năng và có thể ảnh hưởng service khác.

### 15.3. Khi dữ liệu không thể xóa và tạo lại

Nếu Redis đang lưu trạng thái cần giữ lại, cần quy trình migration thực sự:

1. Kiểm kê namespace, kiểu Redis (String/Hash/Stream), TTL và định dạng hiện có.
2. Định nghĩa schema JSON mục tiêu độc lập với class Java càng nhiều càng tốt.
3. Chuẩn bị reader cho dữ liệu cũ bằng serializer Jackson 2 tương thích, reader cho định dạng mới bằng Jackson 3.
4. Xây dựng migration job chuyển dữ liệu cũ sang namespace/format mới theo batch, có kiểm soát lỗi.
5. Giữ khả năng rollback và tránh instance cũ ghi lại dữ liệu cũ vào namespace mới.
6. Kiểm tra bằng tập mẫu có dữ liệu thật đã loại bỏ thông tin nhạy cảm, bao gồm null, collection, enum, date và version trước.
7. Chỉ chuyển traffic sang reader mới sau khi quy tắc xử lý dữ liệu còn lại được quyết định rõ.

Trong nhánh 4.x, các API Jackson 2 cũ hiện còn được cung cấp với trạng thái deprecated for removal để hỗ trợ migration, nhưng không nên xem đó là lựa chọn ổn định lâu dài. Tài liệu Spring Data Redis đề xuất dùng `GenericJackson2JsonRedisSerializer` để đọc dữ liệu generic Jackson 2 cũ trong quá trình chuyển đổi.

### 15.4. Tại sao không “try Jackson 3 rồi catch, fallback Jackson 2” cho mọi GET?

Fallback có thể hữu ích ở giai đoạn chuyển tiếp, nhưng cần tính đến:

- Một giá trị JSON có thể parse thành công nhưng sai **semantic type**, nên không phải cứ không ném exception là đúng.
- Đọc hai lần khiến cache miss và dữ liệu cũ chậm hơn, tăng tải.
- Nếu ghi lại cùng key khi hai phiên bản app đang chạy, một instance có thể phá dữ liệu của instance còn lại.
- Phải giới hạn thời gian chuyển tiếp, thống kê số key cũ và có kế hoạch bỏ fallback.

Thường dễ kiểm soát hơn khi dùng key version rõ ràng hoặc pipeline migration tách biệt.

### 15.5. `RedisSerializer.json()` cũng là điểm phải kiểm tra

Một đoạn code viết trước Spring Data Redis 4:

~~~java
RedisSerializer<Object> valueSerializer = RedisSerializer.json();
~~~

có thể vẫn biên dịch sau nâng cấp nhưng **ý nghĩa của factory đã thay đổi từ serializer generic Jackson 2 sang generic Jackson 3**. Không nên suy luận dữ liệu cũ tự tương thích chỉ vì không thấy lỗi compile. Khi dùng factory shortcut, cần xem tài liệu đúng bản, cách xử lý typing và định dạng dữ liệu đang lưu.

## 16. Quản lý schema JSON để nâng cấp nhiều lần

Một hợp đồng JSON rõ ràng giúp việc migrate dễ hơn:

~~~json
{
  "schemaVersion": 2,
  "productId": "42",
  "name": "Bàn phím",
  "priceAmount": "590000",
  "currency": "VND",
  "updatedAt": "2026-11-12T08:15:00Z"
}
~~~

Đây là **schema minh họa**, không phải định dạng Spring Data Redis bắt buộc. Trong ví dụ, tiền được biểu diễn thành chuỗi số thập phân để giảm sự mơ hồ về precision giữa các ngôn ngữ; timestamp theo ISO-8601 UTC; có `schemaVersion` giúp reader phân biệt phiên bản.

Những quyết định cần nhất quán:

| Quy tắc | Ví dụ rõ ràng | Điều xảy ra khi thiếu quy tắc |
| --- | --- | --- |
| Tên field | `productId` thay vì đổi qua lại `id`/`product_id` | Reader cũ có thể bỏ lỡ field |
| Field mới | Có giá trị mặc định hoặc được đánh dấu optional | Object cũ không có field sẽ đọc lỗi hoặc thiếu dữ liệu |
| Field bị xóa | Dùng giai đoạn deprecation/migration | Reader cũ vẫn đòi field không còn |
| Enum | Thống nhất tên/string được lưu | Đổi enum constant làm reader cũ không hiểu |
| Thời gian | UTC/offset/epoch và đơn vị rõ ràng | Sai timezone, sai đơn vị giây-millisecond |
| Tiền | Decimal string hoặc cấu trúc amount/currency | Mất precision và nhầm tiền tệ |
| Type metadata | Có hay không, thuộc tính tên gì, allow-list ra sao | Reader generic khôi phục sai kiểu |
| Version | Field version hoặc key prefix version | Không biết cách đọc schema cũ |
| TTL | Xác định dữ liệu sống bao lâu | Key cũ tồn tại vô hạn hoặc biến mất bất ngờ |

**JSON dễ đọc không có nghĩa không cần thiết kế schema.** Một cache sống 5 phút có thể chỉ cần version key và TTL; trạng thái sống nhiều tháng cần kế hoạch tương thích/phục hồi nghiêm túc hơn.

## 17. Bảo mật khi deserialize JSON từ Redis

Nhiều nhà phát triển nghĩ Redis nội bộ thì dữ liệu luôn đáng tin. Trên thực tế, Redis có thể bị ghi bởi nhiều service, job, công cụ vận hành hoặc qua lỗ hổng ở một API khác.

### 17.1. Nguy cơ khi bật default typing tùy tiện

Generic typing có thể sử dụng tên class Java trong JSON để quyết định class được instantiate. Nếu deserializer chấp nhận metadata từ nguồn không đáng tin và cho phép bất kỳ class nào, nó có thể tạo ra đường tấn công deserialization không an toàn, tùy gadget và môi trường chạy.

Cách giảm rủi ro:

- Ưu tiên serializer **typed** có kiểu đích cố định.
- Nếu bắt buộc dùng polymorphic typing, áp dụng `PolymorphicTypeValidator` với allow-list chặt chẽ.
- Không bật `enableUnsafeDefaultTyping()` chỉ để sửa nhanh lỗi kiểu dữ liệu.
- Không nhận tên class tùy ý từ HTTP request hoặc payload Redis để nạp class.
- Giới hạn ACL Redis: service chỉ được truy cập đúng key/command cần dùng khi khả thi.
- Cách ly dữ liệu Redis giữa môi trường và phạm vi bảo mật; tránh key chia sẻ sai tenant.
- Theo dõi cập nhật bảo mật của Spring Data Redis, Jackson và dependencies liên quan.

### 17.2. Dữ liệu nhạy cảm và log

JSON có thể bị đọc trực tiếp từ CLI hoặc công cụ giám sát. Vì vậy:

- Không lưu mật khẩu plaintext, secret, access token không bảo vệ hoặc dữ liệu cá nhân không cần thiết vào cache.
- Không log toàn bộ JSON value trong production chỉ để debug serializer.
- Không đưa token/số định danh nhạy cảm vào key dễ lộ qua metric hoặc công cụ quản trị.
- Đặt TTL phù hợp và thiết kế xóa cache khi thông tin không còn được phép lưu.
- Áp dụng TLS và xác thực cho Redis ở môi trường yêu cầu.

Serializer không tự mã hóa dữ liệu để bảo mật; JSON và encryption giải quyết hai vấn đề khác nhau.

## 18. Null, dữ liệu thiếu và phiên bản object

Ba tình huống có thể nhìn giống nhau ở phía nghiệp vụ:

1. Redis key chưa được tạo hoặc đã hết TTL.
2. Redis key tồn tại nhưng được ghi đại diện cho null/không có dữ liệu.
3. Redis key tồn tại, JSON parse được nhưng thiếu field cần thiết của object.

Chúng cần xử lý khác nhau:

| Trường hợp | Hành vi mong muốn | Ghi chú |
| --- | --- | --- |
| Key không tồn tại | Cache miss hoặc `Optional.empty()` | Có thể đọc lại nguồn chính |
| Key có marker null hợp lệ | Theo chiến lược negative caching | Cần serializer/CacheManager hỗ trợ marker |
| JSON thiếu field optional | Dùng default rõ ràng | Hạn chế làm thay đổi hành vi bất ngờ |
| JSON thiếu field bắt buộc | Báo lỗi hoặc yêu cầu migration | Không tự giả định có thể dùng object thiếu dữ liệu |
| JSON không tương thích type | Ghi nhận lỗi serialization/deserialization | Có thể xóa cache có thể tái tạo, nhưng không xóa dữ liệu chính |

Với `Jackson2JsonRedisSerializer` và `JacksonJsonRedisSerializer`, null có quy tắc biểu diễn riêng theo API; không nên tự coi chuỗi JSON literal `null`, byte array rỗng, key không tồn tại và Spring Cache `NullValue` là tương đương. Khi thiết kế cache null, hãy dùng semantics của chính `CacheManager` và serializer được chọn.

## 19. Những lỗi thường gặp và nguyên nhân

| Hiện tượng | Nguyên nhân có thể | Cách tiếp cận |
| --- | --- | --- |
| `ClassNotFoundException` cho `JacksonJsonRedisSerializer` | Dự án vẫn dùng Spring Data Redis 3.x | Dùng `Jackson2JsonRedisSerializer` hoặc nâng cả nhánh dependency theo BOM |
| `ClassNotFoundException` cho `GenericJacksonJsonRedisSerializer` | Dòng Spring Data Redis chưa có API mới | Xem version dependency tree |
| Nhầm `ObjectMapper` trong constructor | Trộn Jackson 2 với Jackson 3 | Kiểm tra `com.fasterxml.jackson.databind` và `tools.jackson.databind` |
| `ClassCastException: LinkedHashMap -> ProductSnapshot` | Generic JSON không đủ type information | Chọn typed serializer hoặc chiến lược type metadata có kiểm soát |
| JSON cũ có `@class` nhưng reader mới lỗi | Metadata/type mapping thay đổi hoặc class đã đổi tên | Có migration/compatibility reader, đổi namespace |
| `SerializationException` hoặc `MismatchedInputException` | Dữ liệu cũ sai schema, wrong serializer, không đúng target type | Xem value format, class/field, migration |
| `GET` trả null nhưng thấy key trong GUI | Key bytes/serializer khác, khác DB, namespace, TTL | Kiểm tra key serializer, database, prefix và lifetime |
| `WRONGTYPE Operation against a key` | Gọi `GET` vào Hash hoặc `HGETALL` vào String | Xác định `TYPE key` và lệnh phù hợp |
| DTO có `Instant` không deserialize được | Mapper thiếu module/format phù hợp | Chọn mapper/modules theo Jackson version; kiểm tra date format |
| Object sau upgrade thiếu field | Schema version không tương thích | Thiết kế default/migration, không âm thầm bỏ qua field quan trọng |
| `@Cacheable` vẫn lưu binary | CacheManager giữ JDK serializer mặc định | Cấu hình `RedisCacheConfiguration.serializeValuesWith(...)` |
| Đọc Redis Hash sai field | Hash key/value serializer hoặc hash mapper khác | Kiểm tra `HGETALL`, mapping flatten/hierarchical |
| Value deserialization bị lỗi khi deploy hai phiên bản | Cùng namespace nhưng hai wire formats | Versioned keys, rollout/migration có kiểm soát |
| Type metadata tạo rủi ro bảo mật | Bật default typing không hạn chế class | Dùng typed DTO hoặc PolymorphicTypeValidator allow-list |
| Redis CLI hiển thị ký tự lạ | Serializer đang lưu dạng binary | Kiểm tra bytes; không kết luận Redis bị hỏng |

### 19.1. Đừng dùng `KEYS *` để điều tra trên Redis lớn

Khi cần quan sát:

~~~redis
TYPE shop:v1:product:42
GET shop:v1:product:42
TTL shop:v1:product:42
SCAN 0 MATCH shop:v1:product:* COUNT 100
~~~

`SCAN` trả cursor, cần lặp cho đến cursor 0 để duyệt hết. Tránh `KEYS *` trên production keyspace lớn; tránh `FLUSHDB`/`FLUSHALL` để “sửa cache” khi chưa biết dữ liệu nào bị ảnh hưởng.

### 19.2. Khi nào xóa cache lỗi thay vì sửa dữ liệu?

Nếu key chỉ là **cache có thể tái tạo**, ứng dụng có thể áp dụng chính sách bỏ key lỗi và đọc lại nguồn chính, có metric để biết tần suất. Nhưng không nên bắt mọi exception rồi trả default như thể dữ liệu chính đã tồn tại. Nếu key là trạng thái nghiệp vụ không thể tái tạo, việc xóa key là mất dữ liệu và cần xử lý migration/khôi phục.

## 20. Bài thực hành: so sánh typed JSON 3.x và 4.x

### 20.1. Chuẩn bị

Chạy Redis cục bộ bằng Docker:

~~~bash
docker run --name redis-json-lab -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it redis-json-lab redis-cli PING
~~~

Kỳ vọng `PONG`. Nếu port 6379 đã dùng, thay mapping phía host và cấu hình `spring.data.redis.port`. Chạy Redis thử nghiệm trên loopback, không mở cổng không xác thực ra Internet.

### 20.2. Nhánh thực hành 3.x

1. Tạo Spring Boot 3.x project với Redis starter và JSON/Jackson 2 dependency phù hợp.
2. Dùng `Jackson2JsonRedisSerializer<ProductSnapshot>` trong `productRedisTemplate`.
3. Lưu hai `ProductSnapshot` dưới prefix `shop:v1:product:*` và đặt TTL.
4. Kiểm tra CLI bằng `GET`, `TYPE` và `TTL`.
5. Đọc lại thông qua service typed; quan sát đúng class và kiểu `BigDecimal`.
6. Thử dùng `StringRedisTemplate` đọc raw JSON cùng key (chỉ quan sát, không ghi đè).

### 20.3. Nhánh thực hành 4.x

1. Tạo Spring Boot 4.x project tách biệt với Spring Data Redis 4.x.
2. Dùng `JacksonJsonRedisSerializer<ProductSnapshot>`.
3. Lưu dữ liệu dưới prefix `shop:v2:product:*`.
4. Kiểm tra định dạng JSON và đọc lại bằng template typed.
5. Nếu có nhu cầu thử generic, tạo thêm một key riêng và dùng `GenericJacksonJsonRedisSerializer`; quan sát kết quả khi không bật default typing.
6. Chỉ khi cần polymorphic types và đã giới hạn type validator, thử metadata phù hợp trên dữ liệu do bạn tạo.

Không cần chạy hai project với cùng namespace. Việc tách `v1` và `v2` giúp tránh một project ghi dữ liệu mà project kia không thể đọc.

### 20.4. Thử nghiệm Spring Cache

1. Tạo một method trả `ProductSnapshot` và annotation `@Cacheable(cacheNames = "productSnapshot", key = "#id")`.
2. Cấu hình `RedisCacheManager` với typed JSON serializer tương ứng nhánh đang dùng.
3. Gọi method lần đầu rồi lần hai; xác minh lần hai trả từ cache bằng cách theo dõi số lần đọc repository.
4. Quan sát key theo cache prefix và giá trị JSON từ Redis CLI.
5. Thử đổi giá ở nguồn chính, xóa cache bằng `@CacheEvict` rồi gọi lại.
6. Xác định TTL và giải thích vì sao TTL không thay thế invalidation sau thay đổi nghiệp vụ.

### 20.5. Bảng ghi nhận

| Trường hợp | Serializer | Redis TYPE | Value thấy trong CLI | Đọc lại thành kiểu nào? | Kết quả mong đợi |
| --- | --- | --- | --- | --- | --- |
| Snapshot typed 3.x | `Jackson2JsonRedisSerializer<ProductSnapshot>` | string | JSON object | `ProductSnapshot` | Đúng dữ liệu |
| Snapshot typed 4.x | `JacksonJsonRedisSerializer<ProductSnapshot>` | string | JSON object | `ProductSnapshot` | Đúng dữ liệu |
| Text/counter | `StringRedisSerializer` | string | Text/số | `String` | Đúng giá trị |
| Generic không có type info | Generic JSON | string | JSON | Có thể là Map/List/scalar | Quan sát hạn chế |
| Cache mặc định | `JdkSerializationRedisSerializer` | string | Binary bytes | Java object trong điều kiện phù hợp | Khác JSON |
| Hash fields | String Hash serializer | hash | `HGETALL` trả fields | Chuỗi hoặc schema quy định | Không dùng `GET` |

Đây là bảng kết quả **dự kiến theo cấu hình mô tả**, không phải dữ liệu benchmark hoặc kiểm thử đã chạy. Kết quả thực tế còn phụ thuộc mapper và version đang dùng.

## 21. Tiêu chí tự đánh giá

Bạn nên giải thích được các câu sau:

1. Vì sao `RedisTemplate<String, ProductSnapshot>` không tự động lưu JSON chỉ nhờ generic type?
2. Key serializer khác value serializer như thế nào? Vì sao nên dùng String cho key trong phần lớn use case?
3. Typed JSON và generic JSON khác nhau ở cách xác định loại object khi đọc ra sao?
4. Khi nào dùng `Jackson2JsonRedisSerializer` và khi nào dùng `JacksonJsonRedisSerializer`?
5. Hai tên generic `GenericJackson2JsonRedisSerializer` và `GenericJacksonJsonRedisSerializer` khác nhau ở hành vi default typing mặc định như thế nào?
6. Vì sao `RedisSerializer.json()` cần được xem xét khi nâng cấp từ Spring Data Redis 3.x lên 4.x?
7. Làm thế nào để chọn `PolymorphicTypeValidator` khi phải dùng JSON type metadata?
8. Tại sao không nên cho deserializer nhận tên class tùy ý từ dữ liệu không đáng tin?
9. Vì sao cache annotation có thể vẫn dùng JDK serializer dù application đã tạo RedisTemplate dùng JSON?
10. Khi nào cần tạo riêng `RedisCacheConfiguration` cho từng cache name?
11. Nếu DTO chứa `List<ProductSnapshot>`, tại sao dùng `List.class` khi deserialize có thể tạo phần tử Map?
12. Redis Hash với ba fields và Redis String chứa một JSON object khác nhau như thế nào?
13. Đổi tên package Java ảnh hưởng thế nào đến value có `@class`?
14. Nếu cần nâng cấp Jackson nhưng Redis chỉ là cache có TTL, chiến lược migration đơn giản là gì?
15. Nếu Redis lưu trạng thái không thể tái tạo, tại sao không được chỉ xóa cache cũ để xử lý lỗi deserialization?
16. Khi gặp `WRONGTYPE`, `ClassCastException` và `SerializationException`, các lỗi đó gợi ý những nhóm nguyên nhân khác nhau nào?
17. Cần thống nhất cách biểu diễn thời gian và tiền tệ thế nào giữa các ứng dụng đọc chung JSON?
18. Làm sao kiểm tra class thực tế đang có trên classpath để quyết định API serializer?

## 22. Tài liệu tham khảo chính thức

- [Spring Data Redis — Migration Guides (3.x → 4.x)](https://docs.spring.io/spring-data/redis/reference/upgrading.html): liệt kê các class thay thế, thay đổi `RedisSerializer.json()`, default typing và hướng migration dữ liệu cũ.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): cách cấu hình cache key/value serializer, key prefix, TTL và các mặc định.
- [Spring Data Redis 3.5 — Jackson2JsonRedisSerializer JavaDoc](https://docs.spring.io/spring-data/redis/reference/3.5/api/java/org/springframework/data/redis/serializer/Jackson2JsonRedisSerializer.html): constructor typed, `ObjectMapper` và cấu hình serializer trên nhánh Jackson 2.
- [Spring Data Redis 4.0 — JacksonJsonRedisSerializer JavaDoc](https://docs.spring.io/spring-data/redis/reference/4.0/api/java/org/springframework/data/redis/serializer/JacksonJsonRedisSerializer.html): typed serializer trên Jackson 3.
- [Spring Data Redis 4.0 — GenericJacksonJsonRedisSerializer builder JavaDoc](https://docs.spring.io/spring-data/redis/reference/4.0/api/java/org/springframework/data/redis/serializer/GenericJacksonJsonRedisSerializer.GenericJacksonJsonRedisSerializerBuilder.html): tùy chọn typing, validator và Spring Cache null support.
- [Spring Boot 4.0 — JSON](https://docs.spring.io/spring-boot/4.0/reference/features/json.html): Jackson 3 là mặc định, Jackson 2 phục vụ migration và các thay đổi cấu hình mapper.

**Ghi nhớ:** Hãy **chọn serializer theo phiên bản thư viện thật và hợp đồng dữ liệu của key**. Với DTO có schema rõ ràng, typed JSON serializer tương ứng Spring Data Redis 3.x hoặc 4.x thường dễ quản lý nhất. Với generic JSON, cần hiểu type metadata và giới hạn deserialization. Khi nâng cấp từ Jackson 2 sang Jackson 3, hãy xem dữ liệu Redis đã được lưu là một định dạng có vòng đời riêng: đổi code hoặc dependency không tự làm dữ liệu cũ trở nên tương thích.

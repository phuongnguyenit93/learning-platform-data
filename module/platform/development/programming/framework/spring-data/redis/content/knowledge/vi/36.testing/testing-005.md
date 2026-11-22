# Kiểm thử Template, serializer và dữ liệu đọc chéo trong Spring Data Redis

Một ứng dụng Spring Data Redis có thể ghi và đọc thành công khi sử dụng cùng một `RedisTemplate`, nhưng vẫn thất bại khi một service khác đọc cùng key bằng `StringRedisTemplate`, một phiên bản ứng dụng mới, Redis CLI hoặc một client viết bằng ngôn ngữ khác. Nguyên nhân thường không nằm ở Redis server mà ở **cách Java object, key, hash field và value được chuyển thành byte**.

Ví dụ: hai template đều nhìn thấy chuỗi logic `"customer:42"`, nhưng một template dùng `StringRedisSerializer` còn template kia dùng `JdkSerializationRedisSerializer`. Redis nhận **hai dãy byte khác nhau** làm tên key. Một template đọc lại dữ liệu của chính nó sẽ thành công, trong khi template khác thấy key không tồn tại. Nếu key giống nhau nhưng value serializer khác, kết quả có thể là JSON hiển thị như một chuỗi, lỗi deserialize hoặc giá trị không đúng kiểu.

Vì vậy, kiểm thử Spring Data Redis cần xác minh **hợp đồng lưu trữ** chứ không chỉ kiểm tra một lời gọi Java trả về đúng đối tượng:

1. Đúng **Redis key bytes** và tên key vật lý.
2. Đúng **Redis data type**: String, Hash, List, Set, Sorted Set, Stream...
3. Đúng **value bytes** và định dạng mã hóa.
4. Đúng **serializer/deserializer** trên mỗi đường đọc và ghi.
5. Đúng **schema/version**, charset, TTL và quy tắc xử lý dữ liệu cũ.
6. Đọc chéo thành công giữa những thành phần được thiết kế để chia sẻ dữ liệu; thất bại có kiểm soát với những tổ hợp không tương thích.

Bài học xây dựng chiến lược kiểm thử với JUnit 5, Spring Boot, Testcontainers, Redis CLI và các template của Spring Data Redis. Ví dụ Java hướng tới **Spring Boot 3.x / Spring Data Redis 3.x / Java 17**. Khi dùng Spring Boot 4.x hoặc phiên bản khác, cần đối chiếu API serializer và dependency theo BOM thực tế.

## 1. Redis chỉ lưu byte, không biết Java object là gì

Khi dùng:

```java
redisTemplate.opsForValue().set("customer:42", customer);
```

luồng xử lý cơ bản là:

```text
Java:
  key   = "customer:42"
  value = new CustomerProfile("42", "An", 120)
              |
              v
      RedisTemplate serializers
              |
       +------+------+
       |             |
       v             v
  key byte[]     value byte[]
       |             |
       +------+------+
              |
              v
         Redis command
       SET <key bytes> <value bytes>
              |
              v
       Redis lưu dữ liệu
```

Redis không nhận một `CustomerProfile` hay một `String` theo nghĩa Java. Redis nhận key và value là những dãy byte có thể biểu diễn tùy serializer. Vì vậy:

- Tên key mà ứng dụng log ra chưa chắc là bytes Redis thực sự lưu.
- `GET` từ Redis CLI trả dữ liệu raw, không biết cách tạo lại Java object.
- `StringRedisTemplate` giải mã value theo UTF-8/String, không tự hiểu JSON thành DTO.
- `RedisTemplate<String, CustomerProfile>` chỉ đọc đúng nếu bytes và schema tương thích với serializer cấu hình.
- Một thay đổi serializer có thể thay đổi **key vật lý**, khiến ứng dụng tưởng dữ liệu bị mất.

### 1.1. Hợp đồng kiểm thử gồm bốn phép biến đổi

```text
Write path:
 Java key   --KeySerializer------> Redis key bytes
 Java value --ValueSerializer----> Redis value bytes

Read path:
 Redis key bytes   <--KeySerializer-- Java key
 Redis value bytes --ValueSerializer--> Java value
```

Hai phía chia sẻ Redis key phải thống nhất **cả key serializer và value format**. Nếu chỉ kiểm tra value serializer mà không kiểm tra key, test vẫn có thể bỏ sót lỗi "không tìm thấy dữ liệu".

## 2. Những Template nào thường cần kiểm thử?

| API | Đặc điểm | Câu hỏi kiểm thử |
|---|---|---|
| `StringRedisTemplate` | Key và value theo String serializer | Có giữ nguyên Unicode và byte UTF-8 không? |
| `RedisTemplate<K,V>` | Tùy cấu hình serializer, hỗ trợ thao tác đồng bộ | Key/value/hash có đúng wire format không? |
| `ReactiveStringRedisTemplate` | API reactive cho String key/value | Publisher đã được subscribe, kết quả/byte có tương thích không? |
| `ReactiveRedisTemplate<K,V>` | Reactive với serialization context | Có cùng định dạng key/value với imperative template không? |
| `RedisCacheManager` / Spring Cache | Có key prefix, serializer và cache entry riêng | Cache có đọc được qua template khác hay không, TTL có đúng không? |
| Redis Repository | Có mapping, entity key, index và metadata phụ | Các key tạo ra có đúng như dự kiến, có đọc được qua Repository sau nâng cấp không? |

**Không thể kết luận hai API tương thích chỉ vì chúng cùng dùng `RedisConnectionFactory`.** Connection factory quản lý kết nối; còn serializer thường được cấu hình tại template/cache/mapping layer.

### 2.1. Bốn serializer cần tách riêng

`RedisTemplate` có:

```java
template.setKeySerializer(...);
template.setValueSerializer(...);
template.setHashKeySerializer(...);
template.setHashValueSerializer(...);
```

Chúng không cùng một nhiệm vụ:

| Serializer | Đối tượng được chuyển thành bytes |
|---|---|
| Key serializer | Tên Redis key, ví dụ `customer:42` |
| Value serializer | Value cho String/List/Set/ZSet và các thao tác phù hợp |
| Hash key serializer | **Field** trong Redis Hash, ví dụ `displayName` |
| Hash value serializer | Value của field, ví dụ `"An"` |

Một lỗi rất hay gặp là kiểm tra `opsForValue()` thành công rồi mặc định `opsForHash()` cũng tương thích. Trong thực tế, hash field có thể được mã hóa khác hoàn toàn.

## 3. Xây ma trận tương thích trước khi viết test

Giả sử hệ thống gồm:

- Service A dùng `StringRedisTemplate` để ghi chuỗi.
- Service B dùng `RedisTemplate<String, CustomerProfile>` để ghi DTO dưới dạng JSON.
- Service C là phiên bản cũ dùng Java native serialization.
- Một script Node.js dùng Redis client để đọc JSON.

Ma trận dự kiến:

| Writer | Reader | Kỳ vọng |
|---|---|---|
| String → String | `StringRedisTemplate` | Đọc lại đúng Unicode |
| JSON DTO → JSON DTO | Cùng schema, cùng serializer | Round-trip tương thích |
| JSON DTO → String | `StringRedisTemplate` | Nhận **chuỗi JSON**, không phải DTO |
| Chuỗi JSON hợp lệ → JSON DTO | Serializer typed JSON | Đọc được nếu schema đúng |
| Java native serialization → String | `StringRedisTemplate` | **Không** kỳ vọng chuỗi có ý nghĩa |
| String key → JDK-serialized key | Template cấu hình khác | Có thể nhìn thành **key khác** |
| Hash String fields → Hash String fields | Serializer thống nhất | Field và value tương thích |
| JSON v1 → JSON v2 | Version mới | Cần contract test/migration |
| TTL key → Template đọc dữ liệu | Cùng key, TTL vẫn còn | Đọc không tự thay đổi TTL thông thường |

Test phải biểu diễn chính sách chia sẻ dữ liệu có chủ đích. Không cần ép mọi template đọc được mọi format. Đôi khi **test đúng là phải xác nhận hai format KHÔNG tương thích** và lỗi được xử lý rõ ràng.

## 4. Khi nào dùng unit test, integration test và contract test?

### 4.1. Unit test

Phù hợp cho:

- Logic tạo tên key.
- Logic xác định version/schema.
- Converter thuần Java.
- Xử lý giá trị thiếu, validation và fallback.
- Kiểm tra serializer độc lập với Redis server.

Ví dụ có thể gọi trực tiếp `serialize`/`deserialize` để kiểm tra bytes, Unicode và null. Unit test **không thể chứng minh** Redis server thực sự nhận key đúng, TTL đúng hay lệnh `HSET` hoạt động đúng.

### 4.2. Integration test với Redis thật

Cần cho:

- `SET`/`GET`, `HSET`/`HGET`, TTL, kiểu Redis.
- Đọc chéo hai template qua cùng một Redis key vật lý.
- Đối chiếu raw bytes và Redis CLI.
- Phát hiện `WRONGTYPE` hoặc serializer mismatch.
- Kiểm thử reactive subscription và serialization context.

Một Redis test instance trong **Testcontainers** thường đáng tin hơn mock `RedisTemplate`. Mock chỉ chứng minh Java code gọi `set` với object nào đó, không cho biết Redis thực tế được ghi thành bytes gì.

### 4.3. Contract test giữa service và phiên bản

Cần khi:

- Nhiều service viết bằng Java/Node/Python dùng chung keyspace.
- Deploy rolling update có cả v1 và v2 đang hoạt động.
- Đổi serializer hoặc đổi thư viện Jackson.
- Đọc dữ liệu cũ sau thay đổi DTO.

Contract test giữ một tập **fixture byte/schema ổn định** từ phiên bản writer đã được triển khai, rồi bắt reader mới giải mã chính xác. Nếu chỉ cho bản mới tự ghi rồi tự đọc, cả writer và reader có thể đổi cùng một lỗi và bài test vẫn xanh.

## 5. Môi trường thực hành: Spring Boot + Testcontainers

Các dependency Gradle cho ứng dụng Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
```

Trong một số dự án, starter reactive và starter đồng bộ có dependency trùng; có thể chọn một starter phù hợp mục tiêu và giữ `spring-data-redis`/Lettuce đúng BOM. Phiên bản Testcontainers cũng phải được quản lý bởi BOM phù hợp hoặc khai báo version riêng nếu build chưa có dependency management tương ứng.

Testcontainers cần môi trường Docker/compatible container runtime có thể chạy từ máy thực thi test. Các đoạn mã bên dưới là **mẫu test để đưa vào dự án**, không chạy Gradle hoặc container trong bước viết bài này.

### 5.1. Tạo một Redis container dùng riêng cho bài test

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class RedisTemplateIntegrationTest {

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port",
                () -> redis.getMappedPort(6379));
    }

    @Test
    void contextLoads() {
        // Các test hành vi sẽ được bổ sung ở những phần sau.
    }
}
```

Đây là khung cho một test class khi dự án đã có `@SpringBootApplication` và Spring Data Redis auto-configuration. Redis image là **phiên bản test được cố định**, không phải chỉ dẫn nâng production lên phiên bản đó. Trong CI nên pin image theo version/digest được cho phép và chủ động nâng phiên bản test tương thích với Redis production.

### 5.2. Không sử dụng Redis production trong integration test

Hệ thống kiểm thử nên:

1. Dùng Redis container/instance riêng.
2. Có tên key theo test, ví dụ `it:397:profile:...`.
3. Không dùng `FLUSHALL` trên server dùng chung.
4. Có cleanup chính xác theo từng key test tạo ra.
5. Không phụ thuộc vào thứ tự chạy giữa các test.
6. Không tự nhận rằng Redis Standalone test đã bao phủ hành vi Cluster/Sentinel.

Nếu cần kiểm thử pipeline, Cluster routing hoặc failover, phải có một môi trường Redis test phản ánh **topology** tương ứng. Một container Redis đơn lẻ không phát hiện được lỗi `CROSSSLOT`.

## 6. Cấu hình StringRedisTemplate và JSON RedisTemplate

Ví dụ model:

```java
package example.redis;

public record CustomerProfile(
        String id,
        String displayName,
        int loyaltyPoints) {
}
```

Một template chuyên ghi `CustomerProfile` dưới dạng JSON:

```java
package example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class ProfileRedisConfiguration {

    @Bean("profileJsonTemplate")
    public RedisTemplate<String, CustomerProfile> profileJsonTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, CustomerProfile> template =
                new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer strings = new StringRedisSerializer();
        Jackson2JsonRedisSerializer<CustomerProfile> profiles =
                new Jackson2JsonRedisSerializer<>(CustomerProfile.class);

        template.setKeySerializer(strings);
        template.setValueSerializer(profiles);

        // Nếu dùng Hash, cấu hình field và field-value có chủ đích.
        template.setHashKeySerializer(strings);
        template.setHashValueSerializer(profiles);

        template.afterPropertiesSet();
        return template;
    }
}
```

Ở đây `Jackson2JsonRedisSerializer<CustomerProfile>` được **gắn với một kiểu cụ thể**. Đoạn ví dụ phù hợp với API Spring Data Redis 3.x; ở các phiên bản mới hơn phải đối chiếu constructor/Jackson mapper tương ứng.

Lưu ý về hai hash serializer trong cấu hình này: hash field là String nhưng **hash value cũng được cấu hình để đọc/ghi `CustomerProfile`**, chứ không phải String. Nếu dùng `opsForHash().put(key, "name", "An")` bằng template trên, nó không phù hợp contract hash value của DTO. Để lưu các field String thông thường, sử dụng `StringRedisTemplate` hoặc một template riêng cho hash String.

### 6.1. Không tự suy ra cấu hình của RedisTemplate mặc định

Một `RedisTemplate` không được cấu hình serializer tường minh thường sử dụng `JdkSerializationRedisSerializer` làm default serializer trong Spring Data Redis. `StringRedisTemplate` lại đặt serializer cho String key/value/hash fields. Tuy nhiên, Spring Boot hoặc một dự án có thể tùy chỉnh bean `redisTemplate`; kiểm thử cần xem **configuration thực tế** của ứng dụng, không chỉ đoán dựa trên tên bean.

Chính sách nên thống nhất:

```text
Keys:         UTF-8 String
Hash fields:  UTF-8 String
Values:       JSON DTO có schema/version rõ ràng
Hash values:  Theo contract của từng Hash
```

Đó là một đề xuất dễ tương tác nhiều ngôn ngữ, không phải định dạng bắt buộc cho mọi dự án.

## 7. Test round-trip: cùng Template ghi rồi đọc

Trong một integration test được cấu hình như mục 5, inject:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;

class RoundTripExample {

    @Autowired
    private StringRedisTemplate strings;

    @Autowired
    @Qualifier("profileJsonTemplate")
    private RedisTemplate<String, CustomerProfile> profiles;

    @Test
    void jsonProfileRoundTrip() {
        String key = "it:397:profile:" + UUID.randomUUID();
        CustomerProfile expected =
                new CustomerProfile("42", "An Nguyễn", 120);

        try {
            profiles.opsForValue().set(key, expected);

            CustomerProfile actual =
                    profiles.opsForValue().get(key);

            assertThat(actual).isEqualTo(expected);
        } finally {
            profiles.delete(key);
        }
    }
}
```

Đoạn `RoundTripExample` minh họa **thân bài test**; để chạy độc lập, đưa nó vào class `@SpringBootTest`/`@Testcontainers` đã cấu hình ở mục 5, hoặc thêm đầy đủ annotation/configuration cho test class riêng.

Test này xác minh:

- Serializer có thể mã hóa `CustomerProfile`.
- Redis nhận và giữ một value.
- Deserializer có thể tạo lại object có giá trị tương đương.

Nhưng **chưa chứng minh JSON trên wire tương thích với hệ thống khác**. Nếu writer và reader cùng serializer sai theo một cách giống nhau, round-trip vẫn có thể xanh.

### 7.1. Thêm Unicode để phát hiện lỗi charset

Đừng chỉ thử `"Alice"`. Nên có những mẫu:

```text
"An Nguyễn"
"Tiếng Việt có dấu"
"東京"
"🚀"
"Dấu ngoặc \" và xuống dòng\n"
"Tên có khoảng trắng ở đầu/cuối"
```

Các mẫu này giúp phát hiện sai charset, escaping hoặc bước normalize không được thiết kế. Với Unicode, so sánh **giá trị sau deserialize** và, khi cần hợp đồng đa ngôn ngữ, so sánh **bytes được mã hóa theo UTF-8**.

## 8. Test đọc chéo: JSON Template ghi, StringRedisTemplate đọc

Đây là phép thử quan trọng nhất cho hai API khác nhau dùng chung một key:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;

@Test
void jsonWriterCanBeReadAsRawString() throws Exception {
    String key = "it:397:cross:" + UUID.randomUUID();
    CustomerProfile expected =
            new CustomerProfile("42", "Linh", 27);

    try {
        profiles.opsForValue().set(key, expected);

        String rawJson = strings.opsForValue().get(key);

        assertThat(rawJson).contains("\"id\":\"42\"");
        assertThat(rawJson).contains("\"displayName\":\"Linh\"");

        // Đọc lại bằng typed serializer phải cho cùng giá trị.
        assertThat(profiles.opsForValue().get(key))
                .isEqualTo(expected);
    } finally {
        strings.delete(key);
    }
}
```

Trong trường hợp này cả hai template dùng key serializer tương thích, vì thế chúng **tìm đúng cùng key vật lý**. JSON serializer tạo ra bytes có thể biểu diễn bằng String UTF-8; `StringRedisTemplate` đọc được **chuỗi JSON**. Nhưng nó không tự biến chuỗi JSON thành `CustomerProfile`.

Nếu muốn chứng minh nội dung JSON thực sự đúng mà không phụ thuộc **thứ tự các field**, có thể parse:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
JsonNode tree = mapper.readTree(rawJson);

assertThat(tree.path("id").asText()).isEqualTo("42");
assertThat(tree.path("loyaltyPoints").asInt()).isEqualTo(27);
```

Đây là phương pháp tốt hơn so với so sánh một chuỗi JSON literal toàn bộ khi serializer có thể thay đổi thứ tự property nhưng giữ nguyên semantics.

### 8.1. Đọc chéo theo hướng ngược lại

Nếu một hệ thống khác ghi một **chuỗi JSON hợp lệ theo cùng schema**:

```java
String key = "it:397:external-json";

strings.opsForValue().set(key,
        "{\"id\":\"43\",\"displayName\":\"Bình\",\"loyaltyPoints\":8}");

CustomerProfile profile =
        profiles.opsForValue().get(key);
```

Kỳ vọng `profile` chứa ba field tương ứng. Đây là phép thử giả lập một service Node/Python ghi JSON raw mà Java reader vẫn có thể đọc.

Nhưng nếu writer dùng:

```java
strings.opsForValue().set(key, "not-json");
```

thì JSON deserializer **không thể** đọc object `CustomerProfile` hợp lệ. Lỗi này nên được ghi nhận như **vi phạm hợp đồng dữ liệu**, không tự động xem là “Redis down”.

## 9. Kiểm thử bytes của key: hai Template có thể trỏ tới hai key khác nhau

Giả sử code cũ dùng Java serialization cho key:

```java
import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

String logicalKey = "it:397:legacy-key";

byte[] utf8Key =
        new StringRedisSerializer().serialize(logicalKey);

byte[] javaSerializedKey =
        new JdkSerializationRedisSerializer().serialize(logicalKey);
```

Hai byte array khác nhau. Ví dụ Java native serialization của String thường bắt đầu với magic bytes:

```text
AC ED 00 05 ...
```

String UTF-8 `"it:397:legacy-key"` bắt đầu với bytes của ký tự `i`, `t`, `:`, `3` ... Redis coi chúng là hai Redis key độc lập.

Một unit test kiểm tra bytes:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

@Test
void keySerializerChangesPhysicalKey() {
    String key = "it:397:legacy-key";

    byte[] raw = key.getBytes(StandardCharsets.UTF_8);
    byte[] javaBytes =
            new JdkSerializationRedisSerializer().serialize(key);

    assertThat(raw).isNotEqualTo(javaBytes);
    assertThat(HexFormat.of().formatHex(raw))
            .isNotEqualTo(HexFormat.of().formatHex(javaBytes));
}
```

Không test dựa vào việc Redis CLI in key nhị phân thành ký tự lạ: terminal có thể xử lý bytes không in được khác nhau. Khi cần so sánh chính xác, đọc raw `byte[]` bằng driver hoặc serialize tại phía client và dùng hex dump.

### 9.1. Kiểm thử hai template trên một Redis test instance

Tạo một template legacy **cố tình** dùng JDK cho key/value:

```java
RedisTemplate<String, String> legacy = new RedisTemplate<>();
legacy.setConnectionFactory(connectionFactory);
legacy.setKeySerializer(new JdkSerializationRedisSerializer());
legacy.setValueSerializer(new JdkSerializationRedisSerializer());
legacy.afterPropertiesSet();

String key = "it:397:legacy";
legacy.opsForValue().set(key, "OLD");

// Về mặt key bytes, StringRedisTemplate đi tìm một key khác.
assertThat(strings.opsForValue().get(key)).isNull();

// Nhưng template legacy có thể đọc lại key do chính nó ghi.
assertThat(legacy.opsForValue().get(key)).isEqualTo("OLD");

legacy.delete(key);
```

`connectionFactory` là `RedisConnectionFactory` từ test context. Key phải là key riêng của bài test và được xóa sau khi thử.

Tình huống này thường bị chẩn đoán nhầm thành “Redis mất dữ liệu” trong khi dữ liệu thực tế nằm dưới **tên key đã được serialize khác**. Với Redis Cluster, thay key bytes còn có thể đổi **hash slot** và node đích.

## 10. Kiểm thử Hash: field serializer và value serializer

Một Redis Hash có:

```text
Redis key:     customer:42:settings
Redis field:   locale
Redis value:   vi-VN
```

Nếu dùng `StringRedisTemplate`:

```java
String key = "it:397:hash";

strings.opsForHash().put(key, "locale", "vi-VN");
strings.opsForHash().put(key, "theme", "dark");

assertThat(strings.opsForHash().get(key, "locale"))
        .isEqualTo("vi-VN");
```

Redis CLI:

```redis
TYPE it:397:hash
HGET it:397:hash locale
HGETALL it:397:hash
```

Kỳ vọng:

```text
hash
"vi-VN"
locale => vi-VN
theme  => dark
```

### 10.1. Một lỗi hash field bị mã hóa bằng JDK

Nếu template khác giữ `StringRedisSerializer` cho key nhưng cấu hình `JdkSerializationRedisSerializer` cho **hash key** (field):

```java
RedisTemplate<String, String> mixed = new RedisTemplate<>();
mixed.setConnectionFactory(connectionFactory);
mixed.setKeySerializer(new StringRedisSerializer());
mixed.setValueSerializer(new StringRedisSerializer());
mixed.setHashKeySerializer(new JdkSerializationRedisSerializer());
mixed.setHashValueSerializer(new StringRedisSerializer());
mixed.afterPropertiesSet();
```

Khi đó:

```java
mixed.opsForHash().put("it:397:hash-mixed", "locale", "vi-VN");
```

Redis key vật lý vẫn có thể đọc được như String, nhưng hash field `locale` được gửi thành Java serialized bytes. Lệnh:

```redis
HGET it:397:hash-mixed locale
```

không tìm thấy field có bytes UTF-8 `locale`, vì Redis Hash phân biệt field theo bytes. Bài học: **kiểm tra hash key serializer độc lập với key serializer**.

### 10.2. Không trộn Hash<String,String> với Hash<String,DTO> trên cùng field

Một field chứa JSON:

```text
HSET customers:hash profile '{"id":"42","displayName":"An","loyaltyPoints":120}'
```

`StringRedisTemplate` có thể đọc field `profile` như chuỗi JSON. Một template cấu hình hash value serializer cho `CustomerProfile` có thể giải mã nếu key và hash-field bytes trùng nhau. Nếu hash value của một số field là String thuần như `ACTIVE` và một số field là JSON DTO, không nên dùng một serializer typed DTO cho **mọi field** rồi giả định kết quả luôn đúng.

Chọn một schema rõ ràng cho mỗi Redis Hash, hoặc sử dụng template tách riêng theo kiểu dữ liệu khi cần.

## 11. Kiểm thử dữ liệu đọc chéo bằng Redis CLI

Redis CLI hữu ích vì cho thấy **dữ liệu phía server** độc lập với Java object:

```bash
redis-cli -h 127.0.0.1 -p 6379 \
  TYPE 'it:397:profile:42'

redis-cli -h 127.0.0.1 -p 6379 --raw \
  GET 'it:397:profile:42'

redis-cli -h 127.0.0.1 -p 6379 \
  TTL 'it:397:profile:42'

redis-cli -h 127.0.0.1 -p 6379 \
  HGETALL 'it:397:hash'
```

Không dùng `GET` để đọc một Redis Hash; Redis sẽ trả `WRONGTYPE`. Phép thử nên kiểm tra `TYPE` trước, sau đó chọn lệnh phù hợp.

### 11.1. Đọc JSON raw không đồng nghĩa deserialize thành công

Redis CLI có thể in:

```json
{"id":"42","displayName":"An","loyaltyPoints":120}
```

Nhưng Java class mới có thể yêu cầu một field khác hoặc kiểu không tương thích. Vì vậy cần **hai phép thử**:

1. Raw format đúng JSON/schema mong đợi.
2. Template reader hiện hành thực sự deserialize được thành DTO và sử dụng được.

Với dữ liệu binary native serialization, `redis-cli --raw` không đảm bảo hiển thị có ý nghĩa; không dùng việc terminal in ra ký tự lạ như tiêu chí thất bại duy nhất.

### 11.2. Chẩn đoán key không tìm thấy

Nếu Java thấy `null` nhưng Redis CLI thấy một key tên tương tự:

- Kiểm tra database index (Standalone) hoặc Cluster mode.
- Kiểm tra key namespace/prefix và key generator.
- Kiểm tra bytes sau key serializer.
- Kiểm tra TTL đã hết hạn hay chưa.
- Kiểm tra đang truy cập cùng host/port/TLS/ACL.
- Kiểm tra Redis key type, không chỉ tên logic.

Một khóa JDK serialized không thể tìm bằng `GET "customer:42"` như String UTF-8. Cần dùng đúng serializer hoặc công cụ đọc raw bytes.

## 12. Kiểm thử serialization độc lập: không nhất thiết phải khởi động Redis

`RedisSerializer<T>` có thể được test trực tiếp:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.StringRedisSerializer;

class StringSerializerTest {

    private final StringRedisSerializer serializer =
            new StringRedisSerializer();

    @Test
    void unicodeIsStoredAsUtf8() {
        String value = "Tiếng Việt 🚀";

        byte[] serialized = serializer.serialize(value);

        assertThat(serialized)
                .isEqualTo(value.getBytes(StandardCharsets.UTF_8));
        assertThat(serializer.deserialize(serialized))
                .isEqualTo(value);
    }
}
```

Tương tự với JSON typed:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;

class CustomerSerializerTest {

    @Test
    void jsonRoundTripPreservesFields() {
        Jackson2JsonRedisSerializer<CustomerProfile> serializer =
                new Jackson2JsonRedisSerializer<>(
                        CustomerProfile.class);

        CustomerProfile expected =
                new CustomerProfile("42", "Hà", 5);

        byte[] bytes = serializer.serialize(expected);
        CustomerProfile decoded = serializer.deserialize(bytes);

        assertThat(decoded).isEqualTo(expected);
    }
}
```

### 12.1. So sánh golden fixtures thay vì chỉ so sánh object

Ví dụ một contract chọn JSON:

```json
{"id":"42","displayName":"Hà","loyaltyPoints":5}
```

Hãy lưu một **fixture ổn định** do writer version đã được phê duyệt tạo ra. Test reader mới giải mã fixture và so sánh semantic fields. Nếu định dạng bytes phải tương thích tuyệt đối với một hệ khác, mới thêm assertion chính xác bytes; còn với JSON, so sánh cấu trúc parsed thường tránh lỗi giả do thứ tự thuộc tính.

**Golden fixture phải được cập nhật có kiểm soát.** Không tự ghi đè fixture bằng output của bản mới rồi gọi đó là bằng chứng backward compatibility.

## 13. JSON typed, generic JSON và Java native serialization

Các nhóm serializer thường gặp:

| Serializer | Đặc điểm | Rủi ro cần test |
|---|---|---|
| `StringRedisSerializer` | UTF-8 String rõ ràng | Đọc nhầm binary, key encoding khác |
| `JdkSerializationRedisSerializer` | Java native object stream | Phụ thuộc Java class/serialVersionUID, không thân thiện đa ngôn ngữ |
| `Jackson2JsonRedisSerializer<T>` | JSON dành cho kiểu mục tiêu | Schema và kiểu target phải nhất quán |
| `GenericJackson2JsonRedisSerializer` | JSON có thể mang metadata kiểu để deserialize object tổng quát | Type metadata, tin cậy dữ liệu và thay đổi format |
| Serializer tự viết | CBOR/Protobuf/MessagePack hoặc format nội bộ | Phải có contract byte và backward compatibility |

### 13.1. JSON typed không cần lưu Java class name trong mỗi record

Với `Jackson2JsonRedisSerializer<CustomerProfile>`, reader được cấu hình sẵn target `CustomerProfile.class`. Dạng JSON thường tập trung vào các field của object. Đây là lựa chọn tương đối dễ chia sẻ qua nhiều ngôn ngữ nếu API schema rõ ràng.

### 13.2. Generic serializer và type hint

`GenericJackson2JsonRedisSerializer` có thể đưa type metadata vào JSON để tái tạo object không biết trước target type. Điều đó tiện cho cache có nhiều loại object, nhưng client Node/Python có thể không biết hoặc không muốn xử lý trường metadata phụ. Bản ghi mang Java class name còn dễ bị ảnh hưởng khi đổi package/class.

**Không bật Jackson default typing hoặc polymorphic deserialization một cách tùy tiện với dữ liệu không đáng tin.** Các kiểu được phép deserialize phải được giới hạn theo chính sách an toàn, và payload Redis cần có ACL/nguồn dữ liệu tin cậy.

### 13.3. Java serialization không phải định dạng chia sẻ mặc định

Java native serialization gắn với class name, cấu trúc field và compatibility của Java. Ngoài việc khó đọc chéo đa ngôn ngữ, deserialization từ nguồn không đáng tin có thể mang rủi ro bảo mật. Nếu ứng dụng dự kiến chia sẻ dữ liệu qua nhiều service/ngôn ngữ, hãy ưu tiên một **schema format** được công bố rõ, có version và test tương thích.

Không kết luận JSON luôn tốt hơn binary trong mọi workload. Protobuf/CBOR hoặc format chuyên biệt có thể hiệu quả hơn; vấn đề cốt lõi là **hợp đồng bytes được thống nhất** và có test xuyên phiên bản.

## 14. Schema evolution: kiểm thử đọc dữ liệu v1 bằng reader v2

Giả sử version cũ ghi:

```json
{"id":"42","displayName":"An"}
```

Version mới yêu cầu:

```json
{"id":"42","displayName":"An","loyaltyPoints":0}
```

Một record Java với field `int loyaltyPoints` có thể nhận giá trị `0` khi field JSON bị thiếu, tùy cấu hình Jackson và kiểu model. Nhưng điều đó **không chứng minh mọi phiên bản đều an toàn**, đặc biệt khi dùng kiểu bắt buộc, constructor validation, enum hoặc đổi tên field.

### 14.1. Các thay đổi cần có test

| Thay đổi | Rủi ro |
|---|---|
| Thêm field tùy chọn | Reader cũ có thể bỏ qua hoặc báo lỗi khi có field lạ |
| Thêm field bắt buộc | Reader mới không đọc được dữ liệu cũ |
| Đổi tên property | Dữ liệu cũ không ánh xạ đúng |
| Đổi `String` sang số/enum | Parse failure hoặc semantic mismatch |
| Đổi Java package/class với generic type hint | Không tìm được class cũ |
| Đổi key prefix | Reader mới thấy cache miss thay vì dữ liệu cũ |
| Đổi serializer | Bytes không tương thích |
| Đổi TTL | Những key cũ chưa chắc nhận chính sách mới |

### 14.2. Test fixture nhiều phiên bản

Một bộ kiểm thử nên chứa:

```text
fixtures/
  profile-v1.json
  profile-v2.json
  profile-invalid.json
  profile-unknown-field.json
```

Mỗi fixture có contract rõ:

- Reader v2 đọc v1 và áp dụng default hợp lệ.
- Reader v2 đọc v2 bình thường.
- Reader v2 từ chối invalid schema một cách kiểm soát.
- Reader cũ trong rolling deployment có hành vi được quyết định với dữ liệu v2.

Không cần bắt mọi reader hỗ trợ vô hạn version. Nhưng phải xác định **cửa sổ tương thích** khi hai bản ứng dụng cùng hoạt động và khi dữ liệu Redis có TTL dài.

### 14.3. Khi đổi formatter/serializer

Một chiến lược migration dễ kiểm soát:

```text
Version A:
  legacy:customer:42   -> Java serialized data

Version B:
  v2:customer:42       -> JSON data
```

Reader B:

1. Thử đọc key v2 bằng serializer mới.
2. Nếu key v2 **không tồn tại**, cân nhắc đọc key legacy bằng serializer cũ.
3. Chuyển object theo schema mới và ghi key v2.
4. Đặt TTL v2 theo chính sách đã thống nhất.
5. Không xóa key cũ trước khi mọi reader cần nó đã được thay thế.
6. Có metric số lần fallback để xác định khi nào migration hoàn tất.

**Không âm thầm fallback khi key v2 tồn tại nhưng deserialize lỗi.** Trường hợp đó có thể là corruption hoặc schema mismatch; cần báo lỗi/điều tra, tránh che lấp dữ liệu sai.

## 15. TTL và thao tác ghi: đừng để test serializer vô tình xóa expiration

Hai mẫu khác nhau:

```java
strings.opsForValue().set(
        "it:397:ttl", "READY",
        java.time.Duration.ofMinutes(2));
```

và:

```java
strings.opsForValue().set("it:397:ttl", "UPDATED");
```

`SET` thông thường không giữ TTL cũ trừ khi được gọi với semantics cho phép, vì vậy ghi lại key mà không truyền expiration có thể xóa TTL. Khi kiểm thử migration hoặc “đọc chéo rồi ghi lại”, đừng chỉ kiểm tra value.

Ví dụ integration test:

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.time.Duration;

String key = "it:397:ttl:profile";
try {
    strings.opsForValue().set(key, "READY",
            Duration.ofSeconds(60));

    Duration before = strings.getExpire(key);
    assertThat(before).isGreaterThan(Duration.ZERO);

    String read = strings.opsForValue().get(key);
    assertThat(read).isEqualTo("READY");

    Duration after = strings.getExpire(key);
    assertThat(after).isGreaterThan(Duration.ZERO);
    assertThat(after).isLessThanOrEqualTo(before);
} finally {
    strings.delete(key);
}
```

Vì đồng hồ và thời gian xử lý làm TTL giảm, không assertion `before.equals(after)`. Test TTL nên chấp nhận một khoảng hợp lý; đừng phụ thuộc chính xác tới millisecond trừ khi chủ đích kiểm tra lệnh thời gian cụ thể.

### 15.1. Null, missing và empty khác nhau

Các trạng thái có thể phải phân biệt:

| Trạng thái | Ví dụ | Cách test |
|---|---|---|
| Key không tồn tại | `GET` trả nil | Template trả `null` hoặc reactive `Mono.empty()` |
| Key tồn tại với String rỗng | `SET key ""` | Trả `""`, không phải missing |
| Value JSON `null` | Bytes JSON biểu diễn null | Tùy serializer và API, cần contract rõ |
| Object có field null | `{"name":null}` | DTO hợp lệ hay lỗi tùy schema |
| Key tồn tại nhưng sai type | Redis Hash thay vì String | `WRONGTYPE`, không phải deserialize error |

Đừng dùng `null` kết quả Java như bằng chứng duy nhất rằng Redis key không có dữ liệu. Có thể cần kiểm tra `hasKey`, `TYPE`, raw bytes và serializer semantics.

## 16. Reactive Template: thử nghiệm subscription và dữ liệu đọc chéo

Một API reactive không gửi lệnh theo cách imperative. Các Publisher của lệnh Redis thông thường thường chỉ chạy khi được subscribe.

Ví dụ test bằng `StepVerifier`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.test.StepVerifier;

String key = "it:397:reactive";

StepVerifier.create(
        reactiveStrings.opsForValue().set(key, "ĐÃ GHI")
                .then(reactiveStrings.opsForValue().get(key))
)
    .expectNext("ĐÃ GHI")
    .verifyComplete();

// Đọc chéo từ imperative template cùng key bytes.
assertThat(strings.opsForValue().get(key))
        .isEqualTo("ĐÃ GHI");

strings.delete(key);
```

`reactiveStrings` là bean `ReactiveStringRedisTemplate` từ Spring context. `StepVerifier` chính là subscriber trong test; nếu chỉ tạo Mono mà không chạy `verifyComplete()`, lệnh chưa chắc được thực thi.

### 16.1. Tại sao không gọi subscribe() trong test rồi assert ngay?

Ví dụ dễ gây flakiness:

```java
reactiveStrings.opsForValue().set(key, "READY").subscribe();
assertThat(strings.opsForValue().get(key)).isEqualTo("READY");
```

`subscribe()` không chờ lệnh Redis hoàn tất. Assertion blocking có thể chạy trước khi Redis nhận `SET`. Sửa bằng `StepVerifier` hoặc trả Publisher vào hệ thống test reactive có cơ chế chờ hoàn tất đúng.

### 16.2. Mỗi subscription có thể chạy lệnh lại

```java
Mono<Long> source =
        reactiveStrings.opsForValue().increment("it:397:counter");
```

Nếu test subscribe hai lần, counter có thể tăng hai lần. Do đó, test đọc chéo cần phân biệt **bản ghi được tạo một lần** với **thao tác nguồn bị resubscribe**. Đặc biệt khi dùng `retry` hoặc `repeat`, tránh kết luận serializer lỗi chỉ vì dữ liệu bị thao tác hai lần.

### 16.3. ReactiveRedisTemplate với serializer riêng

Ví dụ ý tưởng cấu hình context:

```java
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

RedisSerializationContext<String, CustomerProfile> context =
        RedisSerializationContext
                .<String, CustomerProfile>newSerializationContext(
                        new StringRedisSerializer())
                .value(new Jackson2JsonRedisSerializer<>(
                        CustomerProfile.class))
                .build();

ReactiveRedisTemplate<String, CustomerProfile> reactiveProfiles =
        new ReactiveRedisTemplate<>(
                reactiveConnectionFactory, context);
```

`reactiveConnectionFactory` là dependency kiểu `ReactiveRedisConnectionFactory`. Khi muốn imperative và reactive cùng đọc một key, **key/value serialization context phải tương thích**. Nếu Hash hoặc Stream cũng dùng, cần kiểm tra serializer tương ứng chứ không chỉ `value(...)`.

## 17. Kiểm thử khi dữ liệu sai định dạng hoặc sai Redis type

Một hệ thống đủ an toàn cần test cả những ca **không hợp lệ**:

### 17.1. JSON hỏng

```java
String key = "it:397:invalid-json";
try {
    strings.opsForValue().set(key, "{broken-json");

    org.assertj.core.api.Assertions.assertThatThrownBy(
            () -> profiles.opsForValue().get(key))
        .isInstanceOf(RuntimeException.class);
} finally {
    strings.delete(key);
}
```

Có thể dùng assertion một lớp cụ thể hơn như `SerializationException` tùy API và phiên bản. Nội dung lỗi cần được ghi lại có kiểm soát nhưng **không log toàn bộ dữ liệu nhạy cảm**.

### 17.2. Redis key sai data type

```java
String key = "it:397:wrongtype";
try {
    strings.opsForHash().put(key, "field", "value");

    org.assertj.core.api.Assertions.assertThatThrownBy(
            () -> strings.opsForValue().get(key))
        .isInstanceOf(RuntimeException.class);
} finally {
    strings.delete(key);
}
```

Lỗi này đến từ Redis command `GET` trên Hash, không phải từ JSON serializer. Trước khi chẩn đoán, dùng `TYPE key`.

### 17.3. Unknown fields và enum không hợp lệ

Một JSON có property lạ:

```json
{"id":"42","displayName":"An","loyaltyPoints":120,"newField":"x"}
```

Reader cũ có thể bỏ qua hoặc báo lỗi tùy Jackson configuration. Test cần xác định **chính sách mong đợi** cho rolling deploy.

Với enum:

```json
{"status":"UNKNOWN_FROM_FUTURE"}
```

đừng im lặng chuyển thành một trạng thái hợp lệ khác nếu điều đó gây sai nghiệp vụ. Có thể dùng unknown-value fallback có chủ đích, nhưng phải kiểm chứng ý nghĩa downstream.

### 17.4. Không chữa lỗi bằng catch-all rồi trả null

Mẫu rủi ro:

```java
try {
    return profiles.opsForValue().get(key);
} catch (Exception ignored) {
    return null;
}
```

Nó khiến dữ liệu hỏng, sai schema, mất kết nối và key không tồn tại đều bị biến thành cùng một biểu hiện `null`. Thiết kế tốt nên:

- Phân biệt **cache miss** với **serialization failure**.
- Log error code và key namespace an toàn.
- Không ghi đè giá trị cũ bằng data mặc định nếu reader chưa hiểu dữ liệu.
- Có cảnh báo cho contract drift.
- Chỉ fallback theo policy đã định nghĩa rõ.

## 18. Đọc chéo qua nhiều phiên bản ứng dụng

Một integration test chạy writer và reader mới trong cùng JVM **chưa chứng minh** tương thích với service thật đang chạy phiên bản cũ. Khi hệ thống deploy rolling:

```text
Service v1 --------> Redis keyspace <-------- Service v2
      |                                       |
  Serializer v1                          Serializer v2
  Schema v1                              Schema v2
```

Cần ít nhất những kịch bản:

1. Writer v1 → reader v1 (baseline).
2. Writer v1 → reader v2 (backward compatibility).
3. Writer v2 → reader v1 (forward compatibility trong rolling window).
4. Writer v2 → reader v2.
5. Writer/reader khác ngôn ngữ qua golden JSON fixture.
6. Key đã lưu trước khi thay serializer và key prefix.

Không yêu cầu v1 đọc v2 mãi mãi nếu hệ thống đã chuyển xong toàn bộ; nhưng trong thời gian cả hai cùng chạy, các data contract phải có ràng buộc rõ.

### 18.1. Đổi Java class nhưng giữ JSON schema

Nếu các service trao đổi JSON với field `id` và `displayName`, việc đổi tên Java class nội bộ không nhất thiết làm đổi wire format nếu typed serializer không lưu class name. Ngược lại, serializer có type metadata phụ thuộc class name có thể không đọc được sau refactor package.

Vì vậy nên test **wire-format contract** chứ không chỉ test object equality trong phiên bản hiện tại.

### 18.2. Thêm schemaVersion khi format cần tiến hóa

Một payload có thể có:

```json
{
  "schemaVersion": 2,
  "id": "42",
  "displayName": "An",
  "loyaltyPoints": 120
}
```

Reader dựa vào version để chọn parser hoặc migration phù hợp. Không nhầm version của JSON payload với Redis server version hay Gradle dependency version.

Nếu schemaVersion nằm trong object, test phải kiểm tra writer điền đúng và reader xử lý được tất cả version nằm trong cửa sổ hỗ trợ.

## 19. Redis Cluster: key serializer còn quyết định hash slot

Redis Cluster tính:

```text
slot = CRC16(serialized_key_bytes) mod 16384
```

Khi key được chuyển từ:

```text
UTF-8("cart:{42}:items")
```

sang Java native serialization của cùng chuỗi logic, **key bytes khác nhau**. Điều đó có thể:

- Tạo một Redis key vật lý mới.
- Đưa key vào hash slot khác.
- Làm một lệnh nhiều key gặp `CROSSSLOT`.
- Làm read-only path nhìn thấy cache miss sau khi deploy serializer mới.

Vì vậy, test trên Redis Standalone có thể không phát hiện mọi sự cố Redis Cluster. Với các key cần cùng slot, dùng cùng serializer String cho key và kiểm tra:

```redis
CLUSTER KEYSLOT cart:{42}:items
CLUSTER KEYSLOT cart:{42}:total
```

Hai key UTF-8 mang cùng hash tag `{42}` chắc chắn cùng slot. Nhưng một serializer khác có thể thay bytes nên không còn quy tắc như dự kiến.

### 19.1. Không chỉ test việc command thành công

Một lệnh `GET` mỗi key có thể thành công trên Cluster dù key được chuyển sang slot khác. Vấn đề có thể chỉ xuất hiện khi:

- `MGET`/`MSET` nhiều key.
- `MULTI`/`EXEC`.
- Lua script thao tác nhiều key.
- Pipeline/adapter có hạn chế theo phiên bản.

Test contract nên xác định **key bytes và slot cùng nhau** khi nghiệp vụ có ràng buộc co-location.

## 20. Spring Cache và Redis Repository có định dạng riêng

### 20.1. RedisCacheManager không tự dùng serializer của StringRedisTemplate

Spring Data Redis Cache có `RedisCacheConfiguration` riêng, gồm:

- Key prefix, thường là tên cache cộng `::`.
- Serializer cho cache key/value.
- TTL và chính sách cache null.

Ví dụ:

```text
Spring Cache logical:
  cacheName = productViews
  key       = "p-100"

Redis key vật lý có thể là:
  productViews::p-100
```

Nhưng value Redis Cache có thể là Java serialized bytes hoặc JSON theo cấu hình CacheManager. Vì thế `StringRedisTemplate.opsForValue().get("productViews::p-100")` **không tự bảo đảm** trả chuỗi JSON có ý nghĩa.

Nếu muốn cache value đọc được qua nhiều ngôn ngữ, hãy cấu hình serializer của **RedisCacheManager**, không chỉ sửa `RedisTemplate` bean. Test phải đi qua một method `@Cacheable` rồi quan sát key/value raw trong Redis test.

### 20.2. Redis Repository có entity mapping và key phụ

Một Redis Repository sử dụng `@RedisHash`, `@Id`, `@Indexed` có thể tạo nhiều key/Set phụ trợ. Mapping của `MappingRedisConverter`/`RedisCustomConversions` không đồng nhất với việc lấy DTO rồi ghi qua `RedisTemplate.opsForValue().set(...)` bằng JSON.

Không test Repository round-trip rồi tuyên bố một `StringRedisTemplate` có thể đọc entity repository như một JSON String. Nếu cần tương tác, phải định nghĩa rõ format và các key mà repository thật sự tạo.

### 20.3. Đừng dùng KEYS * để so sánh toàn Redis production

Khi debug một test, chỉ kiểm tra namespace của chính test bằng `SCAN` có giới hạn hoặc query key cụ thể. `KEYS *` có thể gây ảnh hưởng hiệu năng trên server lớn; với Redis Cluster, quét một node cũng không đại diện toàn bộ cluster.

## 21. Kiểm thử serializer trong pipeline và transaction

Với `RedisTemplate.executePipelined(...)`, nhiều phương thức Redis trong callback có thể trả `null` ngay lúc phát lệnh; danh sách kết quả sau pipeline dùng cơ chế decode/serializer của template hoặc serializer được chỉ định.

Vì thế một phép thử “`get` trong callback trả null” **không chứng minh value không tồn tại**.

Trong môi trường được hỗ trợ:

```java
List<Object> results = strings.executePipelined(
        (org.springframework.data.redis.core.RedisCallback<Object>)
                connection -> {
                    byte[] key = "it:397:pipeline".getBytes(
                            java.nio.charset.StandardCharsets.UTF_8);
                    byte[] value = "READY".getBytes(
                            java.nio.charset.StandardCharsets.UTF_8);

                    connection.stringCommands().set(key, value);
                    connection.stringCommands().get(key);

                    return null;
                });
```

Phải đọc `results` **sau** khi pipeline hoàn thành, không đọc kết quả lệnh `GET` đồng bộ trong callback. Số lượng và kiểu phần tử do API/serializer và loại lệnh quyết định; cần đối chiếu contract phiên bản thực tế. Cleanup key test sau khi xác nhận.

Transaction `MULTI`/`EXEC` cũng có semantics kết quả riêng; serializer mismatch có thể xuất hiện khi Spring giải mã phản hồi. Hãy kiểm thử dưới API đúng thay vì dùng lời gọi tuần tự rồi coi tương đương với pipelining hoặc transaction.

## 22. Một bộ integration test tối thiểu nên có gì?

Có thể tổ chức các test như sau:

| Test | Writer | Reader/Verifier | Tiêu chí |
|---|---|---|---|
| `string_round_trip` | String Template | String Template | Unicode/empty string chính xác |
| `json_round_trip` | JSON DTO Template | JSON DTO Template | DTO bằng giá trị dự kiến |
| `json_raw_read` | JSON DTO Template | String Template / raw parser | JSON schema đúng |
| `external_json_read` | String Template với JSON fixture | JSON DTO Template | Đọc chéo thành DTO |
| `physical_key_bytes` | JDK vs UTF-8 key serializers | So sánh byte[] | Key bytes khác nhau có chủ đích |
| `legacy_key_visibility` | JDK key Template | String Template | Không nhầm key bị mất |
| `hash_field_encoding` | Hash key serializer khác nhau | HGET/Hash operations | Field bytes đúng |
| `wrongtype_handling` | Redis Hash | String GET | Lỗi được phát hiện và phân loại |
| `invalid_json_handling` | Raw malformed JSON | Typed JSON Template | Không âm thầm trả default |
| `ttl_preserved_on_read` | SET có TTL | GET + PTTL | Không đặt lại TTL khi đọc |
| `reactive_cross_read` | Reactive String Template | Imperative String Template | Đúng bytes và hoàn tất |
| `schema_v1_v2` | Golden fixture v1 | Reader v2 | Backward compatibility |
| `cache_serializer` | Method `@Cacheable` | Raw Redis bytes / Cache | Cache format đúng |
| `cluster_hash_slot` | Key formatter | `CLUSTER KEYSLOT` | Các key cần chung slot thực sự chung slot |

Không bắt buộc tất cả test chạy mỗi pull request. Có thể chia:

- Unit tests rất nhanh.
- Integration tests Redis Standalone cho mỗi PR.
- Contract tests các phiên bản serializer khi đổi schema.
- Cluster/upgrade tests theo pipeline release hoặc lịch phù hợp.

Nhưng **một tính năng giao tiếp chéo** phải có ít nhất một phép thử chạy qua cả đường ghi và đường đọc thật, không chỉ mocks.

## 23. Tránh flaky tests và dọn dữ liệu test đúng cách

Các nguyên nhân flaky phổ biến:

1. Dùng chung key giữa hai test chạy song song.
2. Ghi bằng reactive Publisher nhưng không đợi hoàn tất.
3. TTL quá ngắn khiến key hết hạn giữa các assertion.
4. Môi trường test reuse Redis container có dữ liệu từ lần trước.
5. Assertions phụ thuộc thứ tự JSON properties.
6. Dùng `Thread.sleep` cố định để chờ lệnh/replication.
7. Test giả định replica đọc được ngay dữ liệu mới ghi trên master.
8. Test tự động `FLUSHALL` trên Redis dùng chung.

### 23.1. Đặt key riêng cho từng test

```java
String testId = java.util.UUID.randomUUID().toString();
String key = "it:397:" + testId + ":profile";
```

Cleanup bằng `delete(key)` trong `finally` hoặc `@AfterEach`. Nếu test tạo nhiều key phụ, lưu rõ danh sách key và xóa chúng. Với Redis Cluster, bảo đảm cleanup theo đúng key serializer và connection factory.

### 23.2. Đặt timeout và giới hạn dữ liệu thử

Khi test reactive:

```java
StepVerifier.create(
        reactiveStrings.opsForValue().get("it:397:known"))
    .expectNext("READY")
    .expectComplete()
    .verify(java.time.Duration.ofSeconds(5));
```

Ví dụ giả định key đã được chuẩn bị trước. Timeout giúp test không bị treo vô hạn khi Redis không sẵn sàng; chọn thời gian phù hợp CI environment. Không dùng timeout quá ngắn khiến test thất bại ngẫu nhiên dưới tải máy build.

### 23.3. Không test vào Redis replica khi muốn bảo đảm read-after-write

Replication có độ trễ. Nếu test ghi vào master rồi đọc từ replica ngay, thất bại có thể do consistency model chứ không do serializer. Hãy chọn đúng read preference và xác định test nào đang kiểm tra eventual consistency.

## 24. Chẩn đoán lỗi theo triệu chứng

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra |
|---|---|---|
| Ghi thành công, Template khác đọc `null` | Key serializer hoặc prefix khác | So sánh serialized key bytes |
| Redis CLI `GET` thấy ký tự lạ | Binary serialization | Hex dump và xác minh serializer |
| JSON đọc được dưới dạng String nhưng typed DTO lỗi | Schema/target type/Jackson config không khớp | Parse JSON, kiểm tra property/type |
| `SerializationException` hoặc lỗi đọc stream | Dùng sai value serializer | Xác định writer format và consumer config |
| `WRONGTYPE` | Key đã tồn tại với loại Redis khác | `TYPE key`, kiểm tra namespace |
| `HGET` không thấy field nhưng Hash có dữ liệu | Hash key serializer khác | So sánh field bytes/`HGETALL` |
| JSON thay đổi thứ tự field làm test fail | Assertion so sánh toàn bộ chuỗi | So sánh JSON tree/schema |
| Đổi DTO xong không đọc được cache cũ | Schema migration chưa được thiết kế | Golden fixtures + adapter version |
| Redis đọc được nhưng UTF-8 lỗi | Charset khác hoặc double encode | So sánh raw bytes, serializer hai phía |
| Key đã ghi rồi biến mất | TTL/eviction/delete hoặc DB khác | `PTTL`, `INFO memory`, connection config |
| Đọc cùng key hai lần ra số counter khác | Publisher bị subscribe/retry nhiều lần, lệnh ghi có tác dụng phụ | Log subscription và command semantics |
| Test lúc đúng lúc sai | Key collision, TTL, async race | Tách key/container, StepVerifier, deterministic fixtures |
| Đọc được Standalone nhưng Cluster lỗi | Key serialization đổi slot hoặc multi-key cross-slot | `CLUSTER KEYSLOT`, hash tag, driver support |
| Cache format khác template | `RedisCacheManager` có config riêng | Kiểm tra RedisCacheConfiguration |
| Repository không đọc như JSON value | Mapping của Repository không phải RedisTemplate JSON | Kiểm tra entity key/Hash/converter |

## 25. Bài thực hành tổng hợp

### Bài 1 — So sánh StringRedisSerializer với JDK serializer

1. Tạo chuỗi key `it:397:test-key`.
2. Gọi `StringRedisSerializer.serialize` và `JdkSerializationRedisSerializer.serialize`.
3. Chuyển hai kết quả sang hex.
4. Giải thích vì sao cùng chuỗi logic có thể tạo hai Redis key khác nhau.
5. Nếu môi trường có Redis Cluster test, so sánh slot của bytes tương ứng bằng client/API phù hợp.

### Bài 2 — Ghi JSON DTO rồi đọc raw

1. Tạo `CustomerProfile("42", "An Nguyễn", 120)`.
2. Ghi bằng `profileJsonTemplate`.
3. Đọc bằng `StringRedisTemplate`.
4. Parse chuỗi JSON và xác nhận từng field.
5. Đọc lại bằng typed template; so sánh object.
6. Xóa đúng key sau test.

### Bài 3 — Đọc fixture từ ứng dụng khác

1. Dùng `StringRedisTemplate` hoặc Redis CLI ghi JSON fixture:

   ```json
   {"id":"50","displayName":"Bình","loyaltyPoints":17}
   ```

2. Đọc bằng `profileJsonTemplate`.
3. Kiểm tra DTO có đúng.
4. Đổi `loyaltyPoints` thành String không hợp lệ, xác nhận lỗi contract được phát hiện.
5. Không nuốt lỗi bằng cách trả null.

### Bài 4 — Hash key và hash field serializer

1. Dùng String Template `HSET it:397:hash locale vi-VN`.
2. Đọc bằng String Template và Redis CLI.
3. Tạo một template có hash key serializer là JDK.
4. Ghi field `locale` bằng template đó vào Hash khác.
5. Dùng Redis CLI `HGET ... locale`, quan sát field String không khớp.
6. Giải thích tại sao `setKeySerializer(String)` chưa đủ.

### Bài 5 — TTL và kiểm thử đọc chéo

1. Ghi một JSON key với TTL 60 giây.
2. Đọc qua String Template và typed Template.
3. Kiểm tra TTL tiếp tục giảm sau các lần đọc.
4. Ghi đè key mà không chỉ định TTL trong môi trường test.
5. Giải thích vì sao TTL có thể bị xóa và cách migration bảo toàn chính sách expiration.

### Bài 6 — Reactive Template và subscription

1. Tạo một `Mono<Boolean>` từ `set` nhưng chưa subscribe.
2. Xác nhận key chưa được ghi trong Redis test.
3. Dùng `StepVerifier` đợi thao tác hoàn tất.
4. Đọc chéo bằng `StringRedisTemplate`.
5. Tránh `subscribe()` fire-and-forget rồi assert ngay.

### Bài 7 — Compatibility sau nâng version

1. Lấy golden JSON fixture từ writer phiên bản cũ.
2. Chạy reader mới trên fixture.
3. Thêm field mới và unknown field.
4. Kiểm tra quy tắc default/fallback.
5. Giữ fixture cũ trong test resources để lần nâng cấp tiếp theo vẫn có bằng chứng compatibility.

### Bài 8 — Kiểm thử Redis Cache riêng

1. Tạo cache `productViews` với serializer đã được cấu hình.
2. Dùng method `@Cacheable` tạo một entry.
3. Quan sát key prefix và TTL.
4. Đọc value raw và xác định đó là JSON, String hay binary.
5. Thử đọc bằng template tương thích; không mặc định String Template đọc mọi object cache.

## 26. Checklist cho một thay đổi serializer

Trước khi đổi serializer hoặc schema trong hệ thống đang chạy:

1. Đã thống nhất tên key vật lý và key serializer?
2. Có test byte-level để phát hiện key đổi ngoài ý muốn?
3. Key, hash key, value và hash value có contract riêng?
4. Có golden fixtures từ writer version cũ?
5. Reader mới đọc được dữ liệu trong rolling deployment?
6. Reader cũ có cần đọc dữ liệu mới trong thời gian chuyển tiếp?
7. Đã xác định cách xử lý malformed JSON, missing/unknown field và enum lạ?
8. Có tránh Jackson polymorphic typing không an toàn với dữ liệu không đáng tin?
9. Có giữ đúng TTL hoặc xác định phương án làm mới key?
10. Có kiểm thử trên Redis thật bằng Testcontainers?
11. Có phép thử đọc chéo giữa imperative/reactive hoặc giữa các service cần tương tác?
12. Có test Redis Cache và Repository nếu ứng dụng sử dụng các abstraction này?
13. Với Cluster, có kiểm tra hash slot và các thao tác multi-key?
14. Có kế hoạch migration, rollback và metric phát hiện fallback?
15. Có giới hạn dữ liệu test, namespace riêng và cleanup an toàn?

## 27. Kết luận

**Kiểm thử `RedisTemplate` không dừng ở “ghi bằng template nào thì đọc lại bằng template đó”.** Cần kiểm tra wire contract: byte của Redis key, kiểu Redis, value bytes, serializer cho Hash, schema JSON, charset, TTL và những đường đọc chéo thực sự tồn tại trong kiến trúc.

`StringRedisTemplate` thuận tiện cho chuỗi UTF-8 và quan sát bằng Redis CLI. `RedisTemplate<String, CustomerProfile>` với typed JSON serializer phù hợp khi muốn DTO có schema được định nghĩa rõ. Java native serialization và generic JSON type metadata có những đánh đổi về tương thích và bảo mật; không nên mặc định mọi client có thể giải mã giống nhau.

Một bộ test tin cậy kết hợp **unit test serializer bytes**, **integration test với Redis thật**, **contract test golden fixtures từ phiên bản cũ** và các phép thử **đọc chéo** giữa Template/Reactive Template/Redis CLI hoặc service khác. Khi thay serializer hay nâng version, những bài test này giúp phân biệt cache miss do key bytes đổi, lỗi schema của value, lỗi Redis type và sự cố kết nối thật, đồng thời tránh deploy một thay đổi âm thầm làm ứng dụng không đọc được dữ liệu cũ.

## Tài liệu tham khảo

- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): `RedisTemplate`, `StringRedisTemplate` và cấu hình serialization.
- [Spring Data Redis — Serializers](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): Redis mapping/repositories và các lớp serializer liên quan.
- [Spring Data Redis — Reactive Redis Support](https://docs.spring.io/spring-data/redis/reference/redis/redis-reactive.html): `ReactiveRedisTemplate`, `ReactiveStringRedisTemplate` và serialization context.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): cache-specific serializers, key prefixes và TTL.
- [Spring Data Redis API — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/RedisTemplate.html): cấu hình key/value/hash serializers.
- [Spring Data Redis API — RedisSerializer](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/serializer/RedisSerializer.html): hợp đồng chuyển đổi bytes.
- [Testcontainers — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): Redis integration test với container thực.
- [Spring Framework — DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dynamicpropertysource.html): cung cấp endpoint container động cho Spring tests.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): kiểm thử Publisher và subscription có kiểm soát.
- [Redis — TYPE](https://redis.io/docs/latest/commands/type/): xác minh kiểu dữ liệu của key.
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/): kiểm tra thời hạn key.
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): key bytes, hash slot và yêu cầu multi-key cùng slot.

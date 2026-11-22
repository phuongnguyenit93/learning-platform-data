# Kiểm soát dữ liệu đầu vào trước khi giải tuần tự hóa

Trong Spring Data Redis, một thao tác `RedisTemplate.opsForValue().get(key)` có thể trông đơn giản: đọc value, chuyển byte thành object Java rồi trả cho service. Nhưng **giải tuần tự hóa (deserialization) là một ranh giới bảo mật**, vì dữ liệu được lưu trong Redis không đương nhiên đáng tin cậy chỉ vì nó nằm trong hạ tầng nội bộ.

Redis có thể chứa dữ liệu do nhiều ứng dụng ghi, payload được tạo từ request người dùng, dữ liệu cũ từ một phiên bản triển khai trước, bản sao lưu đã được khôi phục hoặc nội dung bị ghi sai bởi một service bị xâm nhập. Nếu ứng dụng giải tuần tự hóa trực tiếp thành object tùy ý, dữ liệu không hợp lệ có thể dẫn đến lỗi kiểu dữ liệu, tiêu tốn quá nhiều CPU/bộ nhớ hoặc, với **những bộ giải tuần tự hóa và cấu hình không an toàn**, tạo rủi ro thực thi hành vi ngoài dự kiến.

Bài học tập trung vào kỹ thuật **kiểm soát dữ liệu đầu vào *trước* khi giải tuần tự hóa** trong Spring Data Redis: xác định ranh giới tin cậy; chọn định dạng an toàn; giới hạn kích thước; kiểm tra schema, version và trường dữ liệu; sử dụng DTO có kiểu cố định; kiểm soát polymorphic deserialization; xử lý dữ liệu lỗi; và kiểm thử cả nhánh bình thường lẫn nhánh payload độc hại hoặc quá lớn.

Một nguyên tắc quan trọng cần phân biệt:

- **Pre-deserialization validation:** kiểm tra điều kiện có thể biết từ byte hoặc metadata *trước* khi gọi parser/object mapper, chẳng hạn kích thước byte và giới hạn nguồn đọc.
- **Constrained parsing:** parser được cấu hình hạn chế độ sâu, độ dài chuỗi và số; không cho phép tự do chọn lớp Java.
- **Post-deserialization validation:** sau khi parse vào **DTO được xác định trước**, kiểm tra tính hợp lệ của trường, phạm vi giá trị và mối liên hệ với key/ngữ cảnh nghiệp vụ.

Không thể kiểm tra đầy đủ nội dung JSON trước khi parse JSON; vì thế cần **kết hợp cả ba lớp** thay vì kỳ vọng một regex hoặc một lệnh `TYPE` có thể bảo vệ toàn bộ đường đi.

## 1. Vì sao dữ liệu từ Redis vẫn là dữ liệu đầu vào?

Redis thường được triển khai ở mạng riêng với ACL/TLS, nhưng mạng riêng **không biến mọi value thành trusted object**. Một số luồng ghi phổ biến:

~~~text
HTTP request của người dùng
           |
           v
      Service A
           |
     SET cache:user:42
           |
           v
          Redis
           ^
           |
  Service B / Batch migration /
  Consumer / Backup restore
           |
           v
      Service C đọc
           |
           v
 Deserialize → Java object → logic nghiệp vụ
~~~

Ngay cả khi Redis được bảo vệ khỏi Internet, dữ liệu có thể:

1. **Bắt nguồn từ input bên ngoài.** Một trường `displayName`, `metadata` hoặc `filters` lấy từ request vẫn là untrusted data khi được cache.
2. **Bị thay đổi bởi ứng dụng khác.** Một service vô tình dùng cùng namespace hoặc serializer khác có thể tạo payload không tương thích.
3. **Bị lỗi do migration.** Bản triển khai cũ và mới có schema khác nhau nhưng đọc cùng key.
4. **Được khôi phục từ backup.** Snapshot có thể chứa dữ liệu cũ hoặc không tương thích với code hiện tại.
5. **Bị sửa bởi một identity có quyền ghi.** Redis ACL giảm bề mặt tấn công, nhưng một writer bị xâm nhập vẫn có thể ghi payload mà reader phải kiểm tra.
6. **Quá lớn so với dự kiến.** Value hợp lệ về byte có thể gây tăng heap/GC hoặc mở rộng mạnh khi parse.

Vì vậy:

> Redis authentication và network isolation giúp kiểm soát **ai được truy cập kho dữ liệu**; validation và serializer policy giúp kiểm soát **dữ liệu nào được phép trở thành object của ứng dụng**.

Hai lớp bảo vệ này bổ sung cho nhau, không thay thế nhau.

## 2. Đường đi của dữ liệu trong Spring Data Redis

Với một template có serializer:

~~~text
                  Application
                      |
                  GET key
                      |
                      v
                 Redis server
                      |
                   raw bytes
                      |
                      v
               Redis driver
                      |
                      v
       RedisSerializer.deserialize(bytes)
                      |
                      v
               Java object
                      |
                      v
             Business validation
                      |
                      v
                   Service
~~~

Điểm dễ bỏ sót: nếu `RedisTemplate<String, SomeObject>` đã cấu hình serializer tự động tạo object, thì khi method `get(...)` **trả về cho service**, deserialization có thể đã diễn ra. Validation sau `get(...)` là **quá muộn** để phòng tránh rủi ro nằm ngay trong quá trình tạo object.

Để kiểm soát **byte đầu vào trước parser**, có hai hướng:

- Dùng template chuyên biệt đọc `byte[]`, sau đó kiểm tra kích thước và gọi một parser có chính sách rõ ràng.
- Triển khai `RedisSerializer<T>` tùy biến, kiểm tra byte trong `deserialize(byte[])` **trước** khi giao cho parser an toàn.

Với code minh họa, hướng thứ nhất dễ thấy ranh giới kiểm tra hơn. Trong ứng dụng lớn, hướng thứ hai giúp tất cả thành phần dùng cùng serializer tuân thủ chính sách tập trung.

### Các serialization API thường gặp

| Cách lưu giá trị | Cách dữ liệu được chuyển đổi | Rủi ro cần chú ý |
| --- | --- | --- |
| `StringRedisSerializer` | Byte UTF-8 thành String | Chuỗi quá lớn, sai encoding, parse ở bước tiếp theo |
| `GenericJackson2JsonRedisSerializer` | JSON thành object, có thể liên quan type metadata | Kiểu được phép tạo, cấu hình polymorphism, schema/version |
| `Jackson2JsonRedisSerializer<T>` hoặc JSON serializer gắn DTO | JSON thành kiểu đích được biết | Kích thước, parser constraints, validation trường |
| `JdkSerializationRedisSerializer` | Luồng Java Object Serialization thành object | Nguy cơ deserialization của đồ thị đối tượng không tin cậy |
| `byte[]` serializer | Trả nguyên byte từ Redis | Cho phép kiểm tra trước khi parse, nhưng phải tự giới hạn và validate |
| Custom serializer | Phụ thuộc code triển khai | Không được bypass giới hạn kích thước, type allowlist, validation |

**Không có serializer nào tự động làm dữ liệu nghiệp vụ trở nên đáng tin cậy.** JSON giúp tách khỏi việc khôi phục Java object graph tùy ý khi cấu hình an toàn; nhưng JSON quá lớn, lồng sâu, sai schema hoặc có metadata polymorphic không kiểm soát vẫn là một đầu vào rủi ro.

## 3. Rủi ro của Java native deserialization

`JdkSerializationRedisSerializer` sử dụng cơ chế Java Object Serialization. Cơ chế này có thể tái tạo **đồ thị các object Java**, không chỉ một DTO dữ liệu đơn giản. Với payload không tin cậy, việc khôi phục object graph tùy ý là một lớp rủi ro bảo mật đã được biết đến trong hệ sinh thái Java, đặc biệt nếu có những class/gadget không phù hợp trên classpath.

Một anti-pattern:

~~~java
RedisTemplate<String, Object> template = new RedisTemplate<>();
template.setValueSerializer(
    new org.springframework.data.redis.serializer.JdkSerializationRedisSerializer()
);

// Khi đọc value, Java Object Serialization có thể chạy
// trước khi code nghiệp vụ có cơ hội validate object.
Object value = template.opsForValue().get("cache:untrusted");
~~~

Nếu payload đã bị sửa trước đó, việc kiểm tra `value instanceof ExpectedDto` **sau** khi `get` trả kết quả không xử lý được rủi ro đã xảy ra trong lúc deserialization.

### Cách lựa chọn khi thiết kế mới

- **Ưu tiên DTO có schema xác định** và serializer chỉ tạo những kiểu dữ liệu cần thiết.
- Nếu cần JSON, khai báo kiểu đích cụ thể như `ProductCacheV1.class`, tránh parse thành một lớp do input chỉ định.
- Không lưu các object graph tùy ý vào Redis chỉ để có thể “đọc lại nguyên trạng” ở một dịch vụ khác.
- Đừng dùng Java native serialization cho dữ liệu có thể bị tác động bởi người dùng, service khác hoặc nguồn chưa được kiểm soát.
- Nếu hệ thống legacy bắt buộc dùng Java serialization, cần đánh giá migration, bảo vệ kho dữ liệu, giới hạn type bằng cơ chế lọc phù hợp như `ObjectInputFilter` ở nơi giải tuần tự hóa và kiểm thử trên phiên bản JDK/Spring đang sử dụng.

Các cơ chế filter của Java có thể giảm rủi ro trong hệ thống legacy, nhưng chúng **không là lý do để tiếp tục dùng deserialization không giới hạn cho input không tin cậy**. Migration sang định dạng có schema rõ và typed DTO thường là định hướng phù hợp hơn.

## 4. JSON cũng cần kiểm soát kiểu: tránh polymorphism không giới hạn

Jackson là công cụ phổ biến để đọc JSON trong Spring. JSON bản thân không mang theo đối tượng Java, nhưng một cấu hình polymorphic deserialization cho phép payload quyết định lớp Java đích có thể đưa ứng dụng trở lại những rủi ro tương tự việc tạo object không được phép.

Đặc biệt thận trọng với:

~~~java
// Anti-pattern trên dữ liệu không tin cậy:
// mapper.activateDefaultTyping(... validator quá rộng ...);

// Hoặc DTO cho phép payload chỉ định tên lớp Java tùy ý
// thông qua type metadata có Id.CLASS mà không có allowlist.
~~~

Những dấu hiệu đáng xem xét:

- Default typing được bật trên `ObjectMapper` dùng chung với nhiều dữ liệu.
- Một value JSON mang metadata kiểu Java mà caller không kiểm soát.
- Bộ kiểm tra subtype (polymorphic type validator) cho phép gói class quá rộng.
- Deserialization target là `Object.class` trong khi nghiệp vụ chỉ cần một DTO.
- Payload của một service có thể yêu cầu class thuộc module khác vốn không dành cho data transfer.

### Mẫu an toàn hơn: DTO cố định

~~~java
public record ProductCacheV1(
    String productId,
    String title,
    long priceCents,
    long version
) {
}
~~~

Hãy parse JSON trực tiếp thành `ProductCacheV1.class` thay vì chấp nhận tên class từ JSON. Nếu nghiệp vụ thật sự cần nhiều subtype, hãy định nghĩa **tập subtype hữu hạn**, có discriminator thuộc schema, không để dữ liệu tự nhập tên Java class.

Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(
        value = FixedDiscount.class,
        name = "FIXED"
    ),
    @JsonSubTypes.Type(
        value = PercentDiscount.class,
        name = "PERCENT"
    )
})
public sealed interface Discount
    permits FixedDiscount, PercentDiscount {
}

public record FixedDiscount(long amountCents)
    implements Discount {
}

public record PercentDiscount(int percent)
    implements Discount {
}
~~~

Trong mẫu này, `kind` chỉ chọn được những subtype đã khai báo (`FIXED` hoặc `PERCENT`). Vẫn cần kiểm tra `amountCents` không âm, `percent` thuộc khoảng cho phép và kích thước payload. `Id.NAME` với allowlist subtype cố định khác với việc dùng input để quyết định tên Java class tùy ý.

## 5. Kiểm tra gì *trước* khi gọi parser?

Trước khi đọc một payload Redis thành DTO, một lớp bảo vệ đầu vào có thể kiểm tra:

1. **Giới hạn độ dài byte.** Từ chối value vượt budget của loại key.
2. **Định dạng dự kiến.** Ví dụ namespace này chỉ chứa JSON UTF-8; không giải mã tùy ý như Java object stream.
3. **Key namespace và nguồn gọi.** Hàm đọc sản phẩm chỉ nhận ID hợp lệ và chỉ truy cập prefix `cache:product:v1:`.
4. **Schema/version envelope** nếu có định dạng tiền tố hoặc metadata độc lập được xác thực.
5. **Giới hạn tài nguyên của parser.** Độ sâu JSON, độ dài string, độ dài number và trailing tokens.
6. **Danh sách kiểu được phép.** Parser chỉ tạo DTO biết trước, không tạo object theo tên class từ payload.

Sau khi parse, còn phải kiểm tra:

- Giá trị bắt buộc có thiếu hay không?
- ID trong value có khớp key hoặc request không?
- Enum, trạng thái và số tiền có thuộc miền hợp lệ không?
- Schema version có đang được hỗ trợ không?
- Có field lạ, field trùng hoặc dữ liệu ngoài hợp đồng không?
- Phải làm gì nếu nội dung sai: fail closed, bỏ cache có điều kiện hay quarantine?

### Giới hạn độ dài là lớp chặn sớm, không phải chặn bộ nhớ tuyệt đối

Khi `GET` trả byte array cho client, **byte của payload đã được Redis/driver truyền và phân bổ** trước khi code Java kiểm tra `bytes.length`. Giới hạn trong application giảm rủi ro parse tạo thêm object lớn, nhưng không loại bỏ hoàn toàn chi phí network, Redis output buffer hoặc phân bổ byte gốc.

Vì thế cũng cần:

- Giới hạn kích thước **khi ghi** value vào namespace.
- Không để endpoint người dùng tùy ý tạo value khổng lồ.
- Tránh các command có khả năng trả toàn bộ tập hợp rất lớn nếu có thể phân trang/giới hạn.
- Thiết kế Redis memory/network/client limits phù hợp.
- Với payload lớn, cân nhắc lưu ở nơi thích hợp hơn và chỉ giữ reference/metadata trong Redis.

Một key `cache:product:v1:42` có budget 16 KiB khác với một entry Stream log hoặc tài liệu báo cáo dài. **Không dùng một giới hạn duy nhất thiếu bối cảnh cho mọi loại key**.

## 6. Phân biệt độ tin cậy của Redis key, value và schema

Một hệ thống có thể có cả key và value được tạo từ input. Nếu chỉ kiểm tra value sau khi tìm được key, vẫn còn vấn đề về key namespace:

~~~text
Input userId: "../admin"
        |
        v
key = "cache:user:" + userId
        |
        v
Truy cập hoặc ghi sai vùng key nếu có logic phân quyền
~~~

Redis không có khái niệm đường dẫn `../` theo nghĩa filesystem, nhưng ví dụ này cho thấy **nối chuỗi không kiểm tra** có thể làm hợp đồng key khó dự đoán, tạo va chạm namespace hoặc phá cấu trúc phân tách tenant. Một identifier chứa dấu phân cách, newline hoặc ký tự điều khiển còn gây khó khăn cho log/monitoring.

Nên quy định rõ:

~~~text
Key template:
  cache:product:v1:{productId}

productId:
  [A-Za-z0-9_-]{1,64}

Serializer:
  UTF-8 key
  JSON value, ProductCacheV1

Maximum value bytes:
  16 KiB

TTL:
  Phù hợp chính sách cache của loại dữ liệu
~~~

Giới hạn identifier **không thay thế kiểm tra quyền**. Nếu Redis chứa dữ liệu theo tenant, service phải xác định tenant từ context đã xác thực, không chỉ tin tenantId do client gửi trong payload.

## 7. Ví dụ Spring Data Redis: đọc byte trước, kiểm tra rồi mới parse DTO

Ví dụ sau triển khai một cache sản phẩm có chính sách:

- Key dạng `cache:product:v1:{productId}`; productId chỉ được gồm chữ, số, gạch dưới và gạch nối, độ dài 1–64 ký tự.
- Value lưu JSON UTF-8, tối đa **16 KiB** trước khi parse.
- Chỉ được giải thành `ProductCacheV1`, không đọc tên class Java từ payload.
- JSON bị giới hạn độ sâu, độ dài string, độ dài số và không chấp nhận duplicate field.
- DTO phải có schema version đang được hỗ trợ, productId khớp với key, tiêu đề hợp lệ và giá trị giá không âm.
- Cache miss là kết quả riêng; payload không hợp lệ phát lỗi có thể đo và xử lý.

Đây là thiết kế **đọc cache bằng raw bytes có kiểm soát**, không phải sự thay đổi hành vi chung của mọi `RedisTemplate` trong ứng dụng.

### 7.1. Dependency

Với Spring Boot 3.x, Java 21 và Gradle Groovy:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'com.fasterxml.jackson.core:jackson-databind'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

Thí dụ sử dụng các API của Jackson có `StreamReadConstraints` (Jackson 2.15 trở lên). Trong dự án Spring Boot, nên dùng **các phiên bản dependency được BOM quản lý** và xác nhận version Jackson thực tế phù hợp trước khi dùng những tùy chọn cụ thể. Không tự thêm nhiều phiên bản Jackson core/databind không tương thích trong cùng classpath.

### 7.2. Tạo một template chỉ đọc/ghi `byte[]`

~~~java
package com.example.redis.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class SafeRedisTemplateConfiguration {

    @Bean("rawJsonRedisTemplate")
    RedisTemplate<String, byte[]> rawJsonRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, byte[]> template =
            new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(RedisSerializer.byteArray());
        template.setHashKeySerializer(new StringRedisSerializer());
        template.setHashValueSerializer(RedisSerializer.byteArray());
        template.setDefaultSerializer(RedisSerializer.byteArray());
        template.afterPropertiesSet();
        return template;
    }
}
~~~

`StringRedisSerializer` giữ key ở UTF-8. Value trả về là `byte[]`, cho phép code kiểm tra `bytes.length` **trước khi gọi Jackson**. Bean này không nhận trách nhiệm parse object tùy ý trong template.

Không nên đổi serializer của mọi `RedisTemplate` hiện có khi chưa xác định key nào đang dùng định dạng cũ. Việc thay serializer cho một namespace có dữ liệu sẵn có là **thay đổi giao thức lưu trữ**, có thể làm hàng loạt key không đọc được hoặc biến thành cache miss.

### 7.3. DTO được phép tạo

~~~java
package com.example.redis.security;

public record ProductCacheV1(
    String productId,
    String title,
    long priceCents,
    int schemaVersion
) {
}
~~~

Không để khách hàng gửi JSON với tên class tùy ý để tạo object ngoài `ProductCacheV1`. Java record là một DTO dữ liệu minh họa; nếu dữ liệu thực có kiểu lồng nhau, từng kiểu con cũng cần schema và giới hạn rõ ràng.

### 7.4. Parser được giới hạn tài nguyên

~~~java
package com.example.redis.security;

import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SafeJsonConfiguration {

    @Bean("productCacheObjectMapper")
    ObjectMapper productCacheObjectMapper() {
        StreamReadConstraints constraints =
            StreamReadConstraints.builder()
                .maxNestingDepth(16)
                .maxStringLength(8192)
                .maxNumberLength(40)
                .build();

        JsonFactory jsonFactory = JsonFactory.builder()
            .streamReadConstraints(constraints)
            .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
            .build();

        ObjectMapper mapper = new ObjectMapper(jsonFactory);
        mapper.enable(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
        );
        mapper.enable(
            DeserializationFeature.FAIL_ON_TRAILING_TOKENS
        );
        return mapper;
    }
}
~~~

Giải thích:

- `maxNestingDepth(16)`: từ chối JSON lồng quá sâu theo mức ứng dụng cho phép.
- `maxStringLength(8192)`: giới hạn độ dài chuỗi trong parser; ràng buộc byte size tổng thể vẫn áp dụng riêng.
- `maxNumberLength(40)`: giới hạn chiều dài biểu diễn số để giảm rủi ro xử lý số cực dài.
- `STRICT_DUPLICATE_DETECTION`: không cho phép nhiều field trùng tên trong cùng một object JSON.
- `FAIL_ON_UNKNOWN_PROPERTIES`: phát hiện payload có field nằm ngoài schema DTO.
- `FAIL_ON_TRAILING_TOKENS`: từ chối dữ liệu có phần JSON dư sau giá trị đầu tiên.

Một `ObjectMapper` được giới hạn riêng cho cache có thể an toàn hơn việc thay đổi mapper toàn ứng dụng mà chưa hiểu tác động đến API khác. Nếu dùng thêm Java Time module hoặc custom format, cần đăng ký chúng có chủ đích và kiểm thử đúng schema.

**Không bật default typing rộng rãi trên mapper này.** Cũng không đặt target là `Object.class` chỉ để chấp nhận mọi hình dạng value.

### 7.5. Exception và tầng đọc có kiểm soát

~~~java
package com.example.redis.security;

public final class InvalidCachedPayloadException
        extends RuntimeException {

    public InvalidCachedPayloadException(String message) {
        super(message);
    }

    public InvalidCachedPayloadException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Service đọc:

~~~java
package com.example.redis.security;

import java.io.IOException;
import java.util.Objects;
import java.util.Optional;
import java.util.regex.Pattern;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SafeProductCacheReader {

    private static final int MAX_VALUE_BYTES = 16 * 1024;
    private static final int SUPPORTED_SCHEMA = 1;
    private static final long MAX_PRICE_CENTS = 100_000_000_000L;

    private static final Pattern PRODUCT_ID =
        Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private final RedisTemplate<String, byte[]> redis;
    private final ObjectMapper mapper;

    public SafeProductCacheReader(
            @Qualifier("rawJsonRedisTemplate")
            RedisTemplate<String, byte[]> redis,
            @Qualifier("productCacheObjectMapper")
            ObjectMapper mapper) {
        this.redis = Objects.requireNonNull(redis);
        this.mapper = Objects.requireNonNull(mapper);
    }

    public Optional<ProductCacheV1> find(String productId) {
        validateProductId(productId);
        String key = "cache:product:v1:" + productId;

        byte[] bytes = redis.opsForValue().get(key);
        if (bytes == null) {
            return Optional.empty();
        }

        // Bước 1: kiểm tra độ dài TRƯỚC KHI parse.
        if (bytes.length == 0 || bytes.length > MAX_VALUE_BYTES) {
            throw new InvalidCachedPayloadException(
                "Cache payload has invalid byte length"
            );
        }

        final ProductCacheV1 value;
        try {
            // Bước 2: parser có giới hạn và DTO cố định.
            value = mapper.readValue(bytes, ProductCacheV1.class);
        } catch (IOException parseError) {
            throw new InvalidCachedPayloadException(
                "Cache payload is not valid ProductCacheV1",
                parseError
            );
        }

        // Bước 3: validate dữ liệu đã parse theo hợp đồng.
        validateValue(value, productId);
        return Optional.of(value);
    }

    public static void validateProductId(String productId) {
        if (productId == null
                || !PRODUCT_ID.matcher(productId).matches()) {
            throw new IllegalArgumentException(
                "Invalid product identifier"
            );
        }
    }

    private static void validateValue(
            ProductCacheV1 value, String expectedProductId) {

        if (value == null) {
            throw new InvalidCachedPayloadException(
                "Cache payload must be an object"
            );
        }
        if (value.schemaVersion() != SUPPORTED_SCHEMA) {
            throw new InvalidCachedPayloadException(
                "Unsupported cache schema version"
            );
        }
        if (!expectedProductId.equals(value.productId())) {
            throw new InvalidCachedPayloadException(
                "Cache object identifier does not match key"
            );
        }
        if (value.title() == null
                || value.title().isBlank()
                || value.title().length() > 200
                || value.title().codePoints()
                    .anyMatch(Character::isISOControl)) {
            throw new InvalidCachedPayloadException(
                "Invalid product title"
            );
        }
        if (value.priceCents() < 0
                || value.priceCents() > MAX_PRICE_CENTS) {
            throw new InvalidCachedPayloadException(
                "Price is out of accepted range"
            );
        }
    }
}
~~~

#### Những ranh giới của ví dụ

1. `get(...)` trên template có value serializer `byte[]` chỉ cung cấp raw payload. Kiểm tra độ dài xảy ra **trước lần parse JSON**, nhưng không trước khi Redis/driver phân bổ byte gốc.
2. `null` từ GET là **cache miss**, không đồng nghĩa dữ liệu bị lỗi.
3. JSON literal `null` không trở thành DTO hợp lệ: `mapper.readValue` có thể trả `null` và `validateValue` sẽ từ chối.
4. Parser chỉ tạo `ProductCacheV1`, không tạo subtype do payload chỉ định.
5. Missing field kiểu primitive có thể thành giá trị mặc định (`0`), vì vậy phải kiểm tra `schemaVersion`, miền giá trị và tính nhất quán dữ liệu; DTO phức tạp hơn có thể thêm Bean Validation hoặc custom validator.
6. Kiểm tra productId khớp key giúp tránh dùng dữ liệu bị ghi nhầm vào namespace/key khác; **nó không thay thế authorization** khi service truy cập dữ liệu người dùng.
7. Không log nội dung `bytes` hoặc JSON raw trong exception; message chỉ nêu loại lỗi.

### 7.6. Kiểm soát đường ghi để giảm payload sai

Đọc an toàn là bước cuối, nhưng hệ thống cũng nên **validate trước khi lưu**:

~~~java
package com.example.redis.security;

import java.time.Duration;
import java.util.Objects;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SafeProductCacheWriter {

    private static final int MAX_VALUE_BYTES = 16 * 1024;

    private final RedisTemplate<String, byte[]> redis;
    private final ObjectMapper mapper;

    public SafeProductCacheWriter(
            @Qualifier("rawJsonRedisTemplate")
            RedisTemplate<String, byte[]> redis,
            @Qualifier("productCacheObjectMapper")
            ObjectMapper mapper) {
        this.redis = Objects.requireNonNull(redis);
        this.mapper = Objects.requireNonNull(mapper);
    }

    public void store(
            ProductCacheV1 value, Duration ttl) {
        Objects.requireNonNull(value);
        Objects.requireNonNull(ttl);
        SafeProductCacheReader.validateProductId(
            value.productId()
        );
        if (ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException(
                "Cache TTL must be positive"
            );
        }

        // Production nên tái sử dụng chính validator DTO của reader
        // thay vì duy trì hai hợp đồng kiểm tra khác nhau.
        if (value.schemaVersion() != 1
                || value.title() == null
                || value.title().isBlank()
                || value.title().length() > 200
                || value.priceCents() < 0) {
            throw new IllegalArgumentException(
                "Invalid cache DTO"
            );
        }

        byte[] bytes;
        try {
            bytes = mapper.writeValueAsBytes(value);
        } catch (JsonProcessingException error) {
            throw new IllegalArgumentException(
                "Cannot serialize cache DTO", error
            );
        }
        if (bytes.length == 0 || bytes.length > MAX_VALUE_BYTES) {
            throw new IllegalArgumentException(
                "Serialized cache payload exceeds limit"
            );
        }

        redis.opsForValue().set(
            "cache:product:v1:" + value.productId(),
            bytes,
            ttl
        );
    }
}
~~~

Trong dự án production, nên tách validator DTO thành một thành phần chung để reader và writer có cùng ràng buộc. Nếu các producer khác cũng ghi namespace này, **tất cả producer cần tuân thủ contract**; writer nội bộ an toàn không có nghĩa reader được bỏ validation.

## 8. Không chỉ value: Redis Hash, Stream và Pub/Sub cũng có input

### 8.1. Redis Hash

Với `HashOperations.entries(key)`, service có thể nhận nhiều field và value. Nếu Hash lớn, việc gọi `HGETALL` có thể đưa **toàn bộ Hash** về client trước khi code có cơ hội kiểm tra số field.

Một số biện pháp:

- Giới hạn số field và kích thước field **khi ghi**.
- Ưu tiên `HGET` với danh sách field cụ thể nếu không cần toàn bộ Hash.
- Không lấy Hash cực lớn về rồi mới kiểm tra tổng số phần tử.
- Nếu phải duyệt nhiều field, cân nhắc scan/pagination theo khả năng API và semantics, đồng thời đặt giới hạn tổng số item được xử lý.
- Với mỗi field chứa JSON, áp dụng cùng chính sách byte size, parser constraints và typed DTO.

Một field `className` hoặc `type` do producer viết không được mặc định trở thành Java class cần khởi tạo. Hãy map mã loại nghiệp vụ vào danh sách subtype hợp lệ.

### 8.2. Redis Streams

Redis Streams lưu các entry có field/value; chúng có thể bắt nguồn từ producer ngoài ứng dụng đang đọc. Một consumer group không bảo đảm payload đúng schema. Trước khi ACK một entry:

1. Giới hạn độ dài từng field/value và số field của event nếu producer có thể kiểm soát.
2. Kiểm tra event type và schema version thuộc tập được hỗ trợ.
3. Parse vào DTO cụ thể; không cho event quyết định tên Java class tùy ý.
4. Validate business identifier, timestamp, range và tenant context.
5. Chỉ ACK theo chính sách sau khi xử lý thành công hoặc đưa dữ liệu lỗi vào dead-letter/quarantine có kiểm soát.

Không nên cứ parse lỗi là ACK và bỏ entry nếu hệ thống yêu cầu lưu bằng chứng hoặc xử lý lại. Ngược lại, để một payload hỏng bị retry vô hạn cũng có thể tạo **poison message** làm nghẽn consumer; cần chính sách số lượt, DLQ và quan sát được.

### 8.3. Redis Pub/Sub

Pub/Sub không phải hàng đợi lưu bền thông điệp. Một message publish vào channel có thể bị nhận bởi subscriber và đưa qua decoder, nhưng không có bảo đảm replay khi subscriber offline.

Nên dùng một listener adapter kiểm tra:

- Channel nằm trong danh sách được xử lý.
- Kích thước message phù hợp.
- Encoding và schema của thông điệp hợp lệ.
- Loại sự kiện được phép; không deserialize arbitrary Java object.
- Một thông điệp lỗi không làm listener/container ngừng phục vụ vĩnh viễn.

Một subscriber không nên nhận payload Pub/Sub và dùng trực tiếp làm tên class, tên bean hoặc lệnh cần thực thi.

## 9. Spring Cache và Redis Repository: validation phải ở đúng nơi

Khi dùng `@Cacheable`, Spring Cache có thể gọi Redis cache manager và serializer **trước khi** method business hoặc controller thực thi. Một lỗi hoặc rủi ro deserialization có thể xuất hiện ngay tại lớp cache lookup:

~~~text
HTTP request
     |
     v
@Cacheable interceptor
     |
     v
RedisCacheManager / RedisCache
     |
     v
Cache value serializer
     |
     +-- deserialization ở đây
     |
     v
Method service có thể không được gọi nếu cache hit
~~~

Do đó, không thể chỉ đặt `@Valid` trên DTO return value của business method rồi mặc định rằng **mọi value cache hit đã được kiểm tra trước khi deserialize**. Với dữ liệu cần bảo vệ, nên:

1. Cấu hình **value serializer an toàn** ngay trong cache manager hoặc cache-specific configuration.
2. Chọn **DTO/kiểu value hữu hạn** thay vì `Object` và type metadata được tin tuyệt đối.
3. Áp dụng giới hạn byte size trong chính serializer `deserialize(byte[])` nếu cache infrastructure tự giải tuần tự hóa.
4. Cấu hình serializer **theo cache name** nếu các cache khác nhau có schema và budget khác nhau.
5. Kiểm tra dữ liệu sau parse ở tầng nghiệp vụ nếu constraint phụ thuộc user/tenant hoặc trạng thái nghiệp vụ.

### 9.1. Ví dụ một serializer bảo vệ đầu vào

Thay vì đưa parser ra ngoài template như phần trước, có thể viết một serializer chỉ dành cho `ProductCacheV1`. Khi infrastructure gọi `deserialize`, serializer kiểm tra byte trước.

~~~java
package com.example.redis.security;

import java.io.IOException;
import java.util.Objects;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.data.redis.serializer.SerializationException;

public final class BoundedProductCacheSerializer
        implements RedisSerializer<ProductCacheV1> {

    private static final int MAX_BYTES = 16 * 1024;
    private final ObjectMapper mapper;

    public BoundedProductCacheSerializer(ObjectMapper mapper) {
        this.mapper = Objects.requireNonNull(mapper);
    }

    @Override
    public byte[] serialize(ProductCacheV1 value)
            throws SerializationException {
        if (value == null) {
            return new byte[0];
        }

        try {
            byte[] bytes = mapper.writeValueAsBytes(value);
            if (bytes.length > MAX_BYTES) {
                throw new SerializationException(
                    "Product cache value exceeds byte limit"
                );
            }
            return bytes;
        } catch (IOException error) {
            throw new SerializationException(
                "Cannot encode ProductCacheV1", error
            );
        }
    }

    @Override
    public ProductCacheV1 deserialize(byte[] bytes)
            throws SerializationException {
        if (bytes == null || bytes.length == 0) {
            return null;
        }
        if (bytes.length > MAX_BYTES) {
            throw new SerializationException(
                "Product cache value exceeds byte limit"
            );
        }

        try {
            ProductCacheV1 value =
                mapper.readValue(bytes, ProductCacheV1.class);

            if (value == null
                    || value.schemaVersion() != 1
                    || value.title() == null
                    || value.title().isBlank()
                    || value.title().length() > 200
                    || value.priceCents() < 0) {
                throw new SerializationException(
                    "Invalid ProductCacheV1 payload"
                );
            }
            return value;
        } catch (IOException error) {
            throw new SerializationException(
                "Cannot decode ProductCacheV1", error
            );
        }
    }
}
~~~

Serializer này:

- Kiểm tra **kích thước byte** trước `mapper.readValue`.
- Parse trực tiếp thành **kiểu cố định**.
- Phát `SerializationException` cho payload không hợp lệ.
- Sử dụng `ObjectMapper` đã cấu hình `StreamReadConstraints` trước đó.

Trong code production, validation các trường nên được tách thành **validator chung** và bổ sung ràng buộc còn thiếu như productId/upper bound giá trị. Serializer không thể tự xác minh `productId` có khớp key đang được đọc hay không nếu API `deserialize(byte[])` chỉ nhận bytes mà không nhận key; kiểm tra liên kết với key/tenant phải đặt ở tầng có đầy đủ context.

`byte[0]` ở ví dụ là cách biểu diễn null khi serialize để phù hợp với cơ chế serializer đơn giản, nhưng cần xác nhận **hợp đồng null/cache miss của cache manager** ở phiên bản Spring Data Redis đang dùng. Không mặc định mọi cache infrastructure diễn giải zero-length value giống nhau. Trong hệ thống thật, nên quy định rõ cache null values có được phép hay không và dùng quy ước phù hợp với Spring Cache.

### 9.2. Những điểm cần lưu ý với repository mapping

Spring Data Redis Repository có thể đọc Hash và map nhiều field thành một entity. Một entity có annotation như `@RedisHash` không làm mọi field trở nên an toàn:

- Đặt constraint ở DTO/entity và kiểm tra **trước khi dùng** trong business logic.
- Với field chứa JSON serialized riêng, áp dụng giới hạn byte/parser cho field đó.
- Hạn chế dữ liệu có thể được ghi vào property nhạy cảm từ đầu vào người dùng.
- Không giải quyết authorization bằng cách chỉ dựa vào việc đọc thành công entity.
- Khi đổi schema, cần version/migration và kiểm tra tương thích giữa các writer/reader.

**Redis repository mapping và Java native object deserialization là hai cơ chế khác nhau**; rủi ro phụ thuộc serializer, mapping configuration và nguồn dữ liệu của từng field. Không tự gộp mọi lỗi mapping vào một nhãn “Redis không đáng tin”.

## 10. Giới hạn tài nguyên và khả năng từ chối dịch vụ

Ngay cả khi parser không cho tạo object tùy ý, payload hợp lệ về cú pháp vẫn có thể tạo áp lực lên CPU, heap hoặc application threads.

### 10.1. Value quá lớn

~~~text
GET cache:small-object
       |
       v
Redis trả 15 MB thay vì <= 16 KiB
       |
       v
Driver đã nhận/phân bổ byte
       |
       v
Application kiểm tra byte size → từ chối parse
~~~

Kiểm tra sau khi nhận byte **giảm rủi ro parse phình bộ nhớ**, nhưng vẫn mất chi phí nhận 15 MB. Phòng thủ cần có cả giới hạn ở đường ghi, mô hình key/value và giám sát size. Nếu Redis là nơi lưu nhiều loại dữ liệu lớn, không nên dùng `GET` toàn bộ rồi hy vọng size check phía Java đủ ngăn resource exhaustion.

### 10.2. JSON lồng sâu

Một JSON nhỏ hơn byte limit vẫn có thể có nhiều tầng array/object lồng nhau. Parser cần giới hạn độ sâu độc lập với byte length. Ví dụ `maxNestingDepth(16)` cho một DTO nông.

### 10.3. Chuỗi và số cực dài

Một field chuỗi dài hoặc số nhiều chữ số có thể tăng chi phí parsing. `maxStringLength` và `maxNumberLength` là lớp chặn parser-level; sau parse còn cần giới hạn nghiệp vụ chặt hơn, chẳng hạn tên sản phẩm tối đa 200 ký tự.

### 10.4. Collection không giới hạn

Nếu dữ liệu chứa một List hoặc Map lớn, byte limit không nhất thiết phản ánh chi phí object graph sau parse. Với DTO có collections, nên giới hạn **số phần tử, tổng số phần tử lồng nhau và cardinality theo nghiệp vụ**. Khi parser API cho phép, đọc streaming và dừng sau số item cho phép thay vì tạo một collection khổng lồ rồi mới kiểm tra.

### 10.5. Decompression bomb

Nếu ứng dụng nén value trước khi lưu Redis rồi giải nén trước JSON parse, một payload nhỏ có thể nở thành dữ liệu rất lớn:

~~~text
Redis value nén 8 KiB
          |
          v
     Giải nén không giới hạn
          |
          v
  Hàng chục/ hàng trăm MB
          |
          v
      JSON deserializer
~~~

Trong trường hợp này, kiểm tra `compressedBytes.length` **chưa đủ**. Cần giới hạn **số byte sau giải nén**, tỷ lệ giải nén, timeout/CPU và độ sâu parser. Giải nén vào một byte buffer không giới hạn rồi mới kiểm tra có thể đã quá muộn.

### 10.6. Tổng tài nguyên theo concurrency

Một payload 16 KiB có thể nhỏ, nhưng 20.000 request đồng thời cùng đọc value vẫn có thể tạo áp lực phân bổ dữ liệu:

~~~text
memory pressure ≈ in-flight payload count × bytes per payload
               + object allocations + driver buffers
               + framework overhead
~~~

Đây là mô hình khái niệm, không phải công thức dự báo chính xác heap. Cần đặt thêm **concurrency limit**, timeout, pool/connection queue, request budget và circuit breaker phù hợp. Bounded parser không thay thế backpressure.

## 11. Chọn hành vi khi gặp payload không hợp lệ

Một payload Redis sai schema không nên luôn bị xử lý giống cache miss. Hành vi phụ thuộc vai trò của Redis:

| Redis đang giữ | Khi payload không hợp lệ | Hành động thường phù hợp |
| --- | --- | --- |
| Cache có thể tái tạo hoàn toàn từ database | Có thể tiếp tục lấy dữ liệu gốc | Ghi metric, fallback có giới hạn và làm mới cache có kiểm soát |
| Session/authentication | Không thể tin dữ liệu session | Fail closed; không tự cấp quyền hoặc coi session hợp lệ |
| Rate limit/quota/lock | Dữ liệu sai có thể làm hỏng tính đúng | Dừng thao tác quan trọng, điều tra/đối soát |
| Stream event chưa xử lý | Payload hỏng có thể gây poison message | DLQ/quarantine theo policy, không ACK tùy tiện |
| Dữ liệu nghiệp vụ chính trong Redis | Có nguy cơ mất dữ liệu nếu xóa | Bảo toàn bytes và metadata, báo sự cố/migration |

### 11.1. Không bắt mọi exception và trả empty

Một anti-pattern:

~~~java
try {
    return Optional.ofNullable(redis.opsForValue().get(key));
} catch (RuntimeException error) {
    return Optional.empty();
}
~~~

Nó có thể biến tất cả các lỗi sau thành một kết quả “không có key”:

- Redis connection/timeout.
- Dữ liệu sai schema.
- Serialization error.
- Thiếu quyền ACL.
- Lỗi lập trình.

Thay vào đó, nên phân biệt **cache miss**, **invalid payload**, **Redis unavailable** và **lỗi nghiệp vụ**. Với cache best-effort, có thể chọn fallback cho một số nhóm lỗi, nhưng hệ thống cần metric và giới hạn tải lên database.

### 11.2. Không xóa nhầm giá trị mới khi dọn cache hỏng

Giả sử:

~~~text
T0   Reader A đọc bytes cache lỗi
T1   Writer B cập nhật key bằng JSON hợp lệ
T2   Reader A gọi DEL key vô điều kiện
T3   Value hợp lệ của B bị xóa
~~~

Nếu muốn tự động evict một entry lỗi, cần cân nhắc cạnh tranh ghi. Với cache có thể tái tạo, việc evict mù có thể chỉ tạo thêm miss nhưng vẫn gây áp lực lên nguồn chính. Có thể chọn:

- Giữ key tới TTL rồi dùng namespace version mới.
- Chỉ evict theo một chiến lược **compare-and-delete** có điều kiện atomically khi payload vẫn khớp với bản đã đọc, nếu nhu cầu bảo đảm điều đó đủ rõ.
- Gửi entry metadata tới quarantine/log an toàn, không in raw payload nhạy cảm.
- Dùng một quy trình migration riêng thay vì xóa hàng loạt ngay trong request path.

Nếu dùng Lua compare-and-delete, cần giới hạn kích thước đối số và hiểu chi phí gửi lại bytes lớn. Với hệ thống có phiên bản dữ liệu hoặc timestamp, cơ chế compare-and-set/version có thể phù hợp hơn.

### 11.3. Poison message và phân loại lỗi

Một message lỗi do schema không hỗ trợ khác lỗi kết nối tạm thời:

- Lỗi kết nối: có thể retry với backoff và deadline phù hợp.
- JSON sai cấu trúc hoặc subtype lạ: retry cùng bytes thường **không sửa được dữ liệu**.
- Schema version mới hơn: cần triển khai consumer hỗ trợ hoặc chính sách chuyển tiếp/versioning.
- Validation nghiệp vụ thất bại: cần quyết định reject, DLQ hay đối soát; không mặc định lỗi parser.

Sự phân loại này giảm nguy cơ một dữ liệu hỏng làm hệ thống thử lại vô hạn hoặc ghi đè giá trị hợp lệ.

## 12. Redis ACL, TLS và phân tách namespace là lớp bảo vệ bổ sung

Validation trong client không thay thế kiểm soát quyền truy cập tới Redis. Một hệ thống nhiều service nên áp dụng:

1. **TLS** cho kết nối giữa application và Redis/Sentinel khi hạ tầng hoặc threat model yêu cầu, đồng thời kiểm chứng chứng chỉ theo chính sách.
2. **Redis ACL với least privilege:** service chỉ được dùng những command và key pattern cần thiết.
3. **Identity tách biệt cho writer và reader** khi phù hợp. Consumer chỉ đọc cache không cần quyền ghi/xóa trên toàn bộ Redis.
4. **Namespace theo chức năng, schema version và tenant** khi có cơ chế phân quyền phù hợp.
5. **Phân tách môi trường:** không chia sẻ Redis test và production hoặc dùng cùng credentials.
6. **Bảo vệ secret:** không hardcode mật khẩu Redis trong code, stack trace hay file cấu hình commit.
7. **Quan sát ghi bất thường:** phát hiện payload vượt size budget, thay đổi key type và lỗi decode tăng đột biến.

Ví dụ một quy ước key:

~~~text
cache:product:v1:<id>
cache:user:v3:<tenant>:<id>
stream:events:v2
lock:job:<jobId>
~~~

Key prefix giúp tránh va chạm và giảm blast radius, nhưng Redis ACL key patterns và tenant authorization cần được thiết kế cẩn thận; **một prefix không tự trở thành một hệ thống phân quyền dữ liệu**.

### Integrity và confidentiality là hai thuộc tính khác nhau

- TLS bảo vệ dữ liệu **trên đường truyền**, không tự bảo đảm value đang lưu trong Redis đúng schema.
- Encryption at rest giúp giảm rủi ro lộ byte trên storage, không khiến payload sau giải mã tự động đáng tin.
- Chữ ký/HMAC có thể giúp phát hiện payload bị sửa nếu có **khóa xác thực độc lập được bảo vệ**, nhưng không ngăn payload quá lớn, thiếu schema hoặc replay nếu không có thiết kế bổ sung.
- Schema validation ngăn nhiều dạng dữ liệu sai, nhưng không chứng minh người ghi có được phép cập nhật bản ghi đó hay không.

Với hệ thống cần kiểm chứng integrity từ producer cụ thể, có thể thiết kế envelope gồm schema version, payload, issuer và MAC/signature được kiểm tra **trước khi deserialize phần payload thành object**, đồng thời bảo vệ bí mật xác thực và chống replay theo threat model. Không nên chỉ thêm một trường `checksum` không có bí mật rồi coi như đã ngăn được người ghi độc hại.

## 13. Unit test: kiểm tra các nhánh trước và sau deserialize

Một bộ test cho lớp `SafeProductCacheReader` cần chứng minh rằng **payload lớn bị từ chối trước khi đưa vào mapper**, và parser/validator từ chối payload không phù hợp. Unit test có thể mock Redis template để đưa dữ liệu byte tùy ý vào service mà không cần Redis server.

Ví dụ JUnit 5, Mockito và AssertJ:

~~~java
package com.example.redis.security;

import java.nio.charset.StandardCharsets;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SafeProductCacheReaderTest {

    private RedisTemplate<String, byte[]> redis;
    private ValueOperations<String, byte[]> values;
    private SafeProductCacheReader reader;

    @BeforeEach
    void setUp() {
        redis = mock(RedisTemplate.class);
        values = mock(ValueOperations.class);
        when(redis.opsForValue()).thenReturn(values);

        reader = new SafeProductCacheReader(
            redis,
            new SafeJsonConfiguration().productCacheObjectMapper()
        );
    }

    @Test
    void returnsEmptyWhenKeyIsMissing() {
        when(values.get("cache:product:v1:p-1"))
            .thenReturn(null);

        assertThat(reader.find("p-1")).isEmpty();
    }

    @Test
    void readsKnownDtoWhenJsonIsValid() {
        byte[] payload = """
            {
              "productId": "p-1",
              "title": "Keyboard",
              "priceCents": 125000,
              "schemaVersion": 1
            }
            """.getBytes(StandardCharsets.UTF_8);

        when(values.get("cache:product:v1:p-1"))
            .thenReturn(payload);

        Optional<ProductCacheV1> result = reader.find("p-1");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().title())
            .isEqualTo("Keyboard");
    }

    @Test
    void rejectsOversizedBytesBeforeJsonParsing() {
        byte[] oversized = new byte[16 * 1024 + 1];
        when(values.get("cache:product:v1:p-1"))
            .thenReturn(oversized);

        assertThatThrownBy(() -> reader.find("p-1"))
            .isInstanceOf(InvalidCachedPayloadException.class)
            .hasMessageContaining("byte length");
    }

    @Test
    void rejectsInvalidJson() {
        byte[] malformed = "{\"productId\":"
            .getBytes(StandardCharsets.UTF_8);
        when(values.get("cache:product:v1:p-1"))
            .thenReturn(malformed);

        assertThatThrownBy(() -> reader.find("p-1"))
            .isInstanceOf(InvalidCachedPayloadException.class);
    }

    @Test
    void rejectsUnexpectedJsonField() {
        byte[] payload = """
            {
              "productId": "p-1",
              "title": "Keyboard",
              "priceCents": 125000,
              "schemaVersion": 1,
              "unexpected": "not-in-schema"
            }
            """.getBytes(StandardCharsets.UTF_8);
        when(values.get("cache:product:v1:p-1"))
            .thenReturn(payload);

        assertThatThrownBy(() -> reader.find("p-1"))
            .isInstanceOf(InvalidCachedPayloadException.class);
    }

    @Test
    void rejectsWrongSchemaVersion() {
        byte[] payload = """
            {
              "productId": "p-1",
              "title": "Keyboard",
              "priceCents": 125000,
              "schemaVersion": 99
            }
            """.getBytes(StandardCharsets.UTF_8);
        when(values.get("cache:product:v1:p-1"))
            .thenReturn(payload);

        assertThatThrownBy(() -> reader.find("p-1"))
            .isInstanceOf(InvalidCachedPayloadException.class)
            .hasMessageContaining("schema");
    }

    @Test
    void rejectsObjectClaimingAnotherProductId() {
        byte[] payload = """
            {
              "productId": "p-999",
              "title": "Keyboard",
              "priceCents": 125000,
              "schemaVersion": 1
            }
            """.getBytes(StandardCharsets.UTF_8);
        when(values.get("cache:product:v1:p-1"))
            .thenReturn(payload);

        assertThatThrownBy(() -> reader.find("p-1"))
            .isInstanceOf(InvalidCachedPayloadException.class)
            .hasMessageContaining("identifier");
    }

    @Test
    void rejectsInvalidIdentifierBeforeRedisAccess() {
        assertThatThrownBy(() -> reader.find("tenant:other:p-1"))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Các test ở đây chứng minh **nhánh ứng dụng đã viết**. Chúng không khẳng định rằng Redis thực sự lưu đúng byte, Redis ACL được cấu hình đúng, hoặc cấu hình serializer của tất cả cache đã an toàn; những yêu cầu đó cần integration test và kiểm tra hạ tầng riêng.

Trong ví dụ, `mock(RedisTemplate.class)` và `mock(ValueOperations.class)` có thể sinh cảnh báo unchecked do Java generic bị xóa ở runtime. Có thể dùng `@SuppressWarnings("unchecked")` cục bộ theo conventions của project. Những cảnh báo generic của mock không phải lý do cho phép deserialization thành `Object.class` trong production.

### Kiểm tra duplicate field và JSON lồng sâu

Khi xây schema nghiêm ngặt, nên có thêm test cho:

~~~json
{
  "productId": "p-1",
  "productId": "p-2",
  "title": "Keyboard",
  "priceCents": 125000,
  "schemaVersion": 1
}
~~~

Với `STRICT_DUPLICATE_DETECTION`, một JSON có hai lần xuất hiện của `productId` phải bị từ chối. Một JSON lồng quá `maxNestingDepth` cũng phải bị parser từ chối. Tương tự, test nên dùng chuỗi/số vượt giới hạn và dữ liệu có trường không thuộc DTO.

Đừng viết test dựa trên cách “field cuối thắng” khi có duplicate field; cách xử lý đó có thể khác nhau giữa những parser hoặc các service, tạo nguy cơ **parser differential** khi một thành phần kiểm tra khác với thành phần thực thi.

## 14. Integration test: byte thật được lưu trong Redis

Unit test kiểm soát byte đầu vào, nhưng không thể bảo đảm template và serializer thật không thực hiện thêm bước chuyển đổi ngoài ý muốn. Với Testcontainers, có thể kiểm tra:

- Dữ liệu JSON hợp lệ được ghi qua writer và đọc qua reader thành DTO.
- Byte lỗi được ghi trực tiếp vào key test có thể khiến reader từ chối.
- Value vượt ngân sách byte không bị parse.
- Một key miss trả empty thay vì làm giả lỗi Redis.
- Cleanup chỉ xóa những key test có namespace riêng.

Ví dụ:

~~~java
package com.example.redis.security;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Testcontainers
@SpringBootTest(
    classes = SafePayloadIntegrationTest.TestApp.class
)
class SafePayloadIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({
        SafeRedisTemplateConfiguration.class,
        SafeJsonConfiguration.class,
        SafeProductCacheReader.class,
        SafeProductCacheWriter.class
    })
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    @Qualifier("rawJsonRedisTemplate")
    RedisTemplate<String, byte[]> rawRedis;

    @Autowired
    SafeProductCacheReader reader;

    @Autowired
    SafeProductCacheWriter writer;

    @Test
    void knownDtoCanRoundTrip() {
        String id = "it-" + UUID.randomUUID();
        String key = "cache:product:v1:" + id;

        try {
            writer.store(
                new ProductCacheV1(id, "Monitor", 400000, 1),
                Duration.ofSeconds(30)
            );

            ProductCacheV1 loaded = reader.find(id).orElseThrow();
            assertThat(loaded.productId()).isEqualTo(id);
            assertThat(loaded.title()).isEqualTo("Monitor");
            assertThat(loaded.schemaVersion()).isEqualTo(1);
        } finally {
            rawRedis.delete(key);
        }
    }

    @Test
    void rejectsMalformedRedisValue() {
        String id = "it-" + UUID.randomUUID();
        String key = "cache:product:v1:" + id;

        try {
            rawRedis.opsForValue().set(
                key,
                "{not valid json".getBytes(StandardCharsets.UTF_8),
                Duration.ofSeconds(30)
            );

            assertThatThrownBy(() -> reader.find(id))
                .isInstanceOf(InvalidCachedPayloadException.class);
        } finally {
            rawRedis.delete(key);
        }
    }

    @Test
    void rejectsPayloadLargerThanPolicy() {
        String id = "it-" + UUID.randomUUID();
        String key = "cache:product:v1:" + id;

        try {
            rawRedis.opsForValue().set(
                key,
                new byte[16 * 1024 + 1],
                Duration.ofSeconds(30)
            );

            assertThatThrownBy(() -> reader.find(id))
                .isInstanceOf(InvalidCachedPayloadException.class);
        } finally {
            rawRedis.delete(key);
        }
    }
}
~~~

Đây là integration test với Redis riêng; máy chạy test cần Docker hoặc container runtime tương thích. `@Import` đăng ký đúng template, mapper, reader và writer của bài học. Mỗi test tạo key có UUID để hạn chế va chạm và dọn chính key đó trong `finally`. Không dùng `FLUSHALL` hoặc `FLUSHDB` trên Redis có thể được chia sẻ.

Ví dụ này không kiểm chứng một policy ACL hay kết nối TLS thật vì Redis container đơn giản chưa cấu hình chúng. Nếu security requirement bao gồm ACL/TLS, phải thêm bài kiểm thử môi trường tương ứng.

### Cần kiểm tra cả đường ghi bằng serializer cũ

Một hệ thống đã tồn tại nhiều năm có thể từng dùng:

~~~text
cache:product:123
  ├── JDK serialization từ phiên bản A
  ├── JSON generic typing từ phiên bản B
  └── JSON DTO cố định từ phiên bản C
~~~

Trong tình huống đó, thay serializer mới cho cùng key **không tự động migrate value cũ**. Integration test cần dùng fixture byte đại diện cho những phiên bản dữ liệu thực sự được hỗ trợ và xác nhận code xử lý hợp đồng migration đúng như dự kiến.

Không cần giữ một deserializer rủi ro trong request path chỉ để đọc mọi định dạng legacy nếu có thể thực hiện migration riêng trong môi trường kiểm soát.

## 15. Migration schema mà không mở lại rủi ro deserialization

Một lý do nhiều hệ thống chấp nhận deserializer quá rộng là “cần đọc được dữ liệu cũ”. Về lâu dài, đây thường là nợ kỹ thuật bảo mật. Để đổi sang DTO schema cố định, nên tách **quá trình đọc dữ liệu cũ** khỏi **đường đọc request mới**.

### 15.1. Namespace theo version

Ví dụ:

~~~text
cache:product:v1:p-42   ← payload JSON ProductCacheV1
cache:product:v2:p-42   ← payload JSON ProductCacheV2
~~~

Quy trình:

1. Định nghĩa `ProductCacheV2` và giới hạn byte/parser rõ ràng.
2. Deploy writer mới chỉ ghi vào namespace `v2`.
3. Reader mới đọc `v2` bằng serializer/validator tương ứng.
4. Nếu cần giữ dữ liệu cache cũ, chạy job migration **riêng** trên tập dữ liệu đã xác định và đọc v1 bằng chính sách an toàn đã đánh giá.
5. Kiểm tra số bản ghi chuyển được, số bản ghi bị từ chối và ảnh hưởng lên hit ratio.
6. Chờ TTL hoặc dọn v1 có kiểm soát khi không còn consumer.
7. Xóa dependency/cấu hình deserializer legacy khỏi đường truy cập thông thường sau khi hoàn tất.

Đối với **cache có thể tái tạo hoàn toàn**, nhiều khi không cần đọc lại dữ liệu v1: đơn giản hơn là bỏ cache v1 và nạp v2 từ nguồn chính theo chính sách chống cache stampede. Với dữ liệu nghiệp vụ không thể tái tạo, cần migration có đối soát đầy đủ thay vì chỉ để TTL trôi qua.

### 15.2. Schema version trong payload

Một envelope JSON minh họa:

~~~json
{
  "schemaVersion": 2,
  "productId": "p-42",
  "title": "Keyboard",
  "priceCents": 125000,
  "currency": "VND"
}
~~~

Không nên để payload tự khai `javaClass` hoặc `serializerClass` rồi dùng reflection tạo object tương ứng. Application có thể đọc một **version field thuộc tập hữu hạn**, chọn reader/DTO tương ứng và từ chối version không được hỗ trợ.

Tuy nhiên, nếu cần biết version **trước khi parse toàn bộ JSON**, ứng dụng phải có một envelope được định nghĩa rõ và parser streaming có giới hạn để đọc version hoặc metadata ngoài payload được bảo vệ. Chỉ parse payload không giới hạn thành `Map<String,Object>` để tìm version thì không thực sự kiểm soát tài nguyên trước deserialization.

### 15.3. Tái sử dụng fixture theo schema

Để tránh parser bị lệch giữa nhiều ngôn ngữ/dịch vụ:

- Lưu các fixture JSON đại diện cho version được hỗ trợ.
- Kiểm tra JSON duplicate fields, unknown fields và thiếu field bắt buộc.
- Kiểm tra dữ liệu chuỗi Unicode và encoding.
- Định nghĩa rõ cách xử lý giá trị số, null và enum không hợp lệ.
- Áp dụng giới hạn tổng byte và collection size trong contract.
- Nếu producer khác ngôn ngữ, xác nhận cả producer và consumer có cùng cách hiểu schema.

Một hợp đồng schema chỉ có giá trị khi **tất cả writer và reader** có thể thực thi/kiểm tra nó một cách nhất quán.

## 16. Telemetry: theo dõi payload bị từ chối mà không rò dữ liệu

Khi có payload không hợp lệ, chỉ ghi stack trace của parser không đủ để biết tác động. Nhưng **log cả raw Redis value** có thể phát lộ thông tin nhạy cảm.

Thông tin nên ghi:

| Trường quan sát | Ví dụ an toàn | Mục đích |
| --- | --- | --- |
| Namespace | `cache:product:v1` | Xác định loại dữ liệu |
| Failure category | `oversize`, `malformed_json`, `schema_mismatch` | Phân loại nguyên nhân |
| Payload byte size | `18752` | Xem có vượt budget |
| Expected schema | `ProductCacheV1` | Xác định contract |
| Schema version | `1` hoặc `unsupported` | Phát hiện rollout lệch |
| Service/producer identity | Tên service đã được phép lưu | Tìm nguồn ghi lỗi |
| Trace/correlation ID | ID kỹ thuật được quản lý | Nối với request flow |
| Redis topology | Standalone/Sentinel/Cluster | Phân biệt lỗi dữ liệu với failover |

Không nên ghi:

- Raw JSON value, byte payload hoặc Java serialized bytes.
- Redis password, session token, API key.
- Toàn bộ key chứa user ID/tenant ID nếu không cần.
- User-provided string không được escape/redact, vì có thể làm nhiễu cấu trúc log.
- Một metric label riêng cho mỗi Redis key, vì sẽ tạo cardinality quá lớn.

Ví dụ metric logic:

~~~text
redis_payload_validation_failed_total{
  namespace="cache_product_v1",
  reason="oversize"
}

redis_payload_validation_failed_total{
  namespace="cache_product_v1",
  reason="schema_mismatch"
}
~~~

Đây là **tên metric gợi ý**, không tự có sẵn trong Spring Boot. Ứng dụng cần instrument bằng Micrometer hoặc hệ thống quan sát tương ứng.

Ngoài số payload bị từ chối, nên theo dõi:

- Tỷ lệ cache miss và fallback sau schema rollout.
- Tốc độ thay đổi value size theo namespace.
- Memory/GC khi decode dữ liệu.
- Redis command latency và số request đang chờ.
- Số producer ghi value lỗi trong thời gian ngắn.
- Số entry DLQ/quarantine của Stream.

Một cảnh báo tăng đột biến `schema_mismatch` sau deployment thường hữu ích hơn một log lẻ chứa stack trace Jackson dài mà không có namespace.

## 17. Quy trình ứng phó khi phát hiện payload bất thường

Khi service báo deserialization failure:

~~~text
             Redis value đọc về
                     |
                     v
          Byte length trong giới hạn?
             /               \
           Không              Có
             |                |
             v                v
        Reject early     Parse theo DTO/constraints
                              |
                    +---------+----------+
                    |                    |
                  Lỗi                 Thành công
                    |                    |
                    v                    v
              Log category       Validate field/range
                    |                    |
                    +---------+----------+
                              |
                              v
                       Áp dụng policy
                   cache / session / stream /
                      dữ liệu nghiệp vụ
                              |
                +-------------+-------------+
                |             |             |
                v             v             v
           Fallback        Fail closed     Quarantine
            có hạn             |          / migration
                |             |             |
                +-------------+-------------+
                              |
                              v
                       Metric + điều tra
~~~

Các bước thực tế:

1. **Xác định phạm vi:** chỉ một key, một namespace hay tất cả ứng dụng vừa deploy?
2. **Thu thập metadata an toàn:** payload byte size, serializer/schema version, exception class và thời điểm.
3. **Kiểm tra producer:** service nào vừa ghi vào namespace này? Có thay đổi serialization library hoặc record schema không?
4. **Đánh giá vai trò dữ liệu:** cache tái tạo được hay dữ liệu không thể mất?
5. **Dừng tác động lan rộng:** giới hạn fallback, consumer retry và tần suất ghi nếu đang có sự cố.
6. **Chọn khôi phục:** sửa writer, migration, đọc namespace mới hoặc quarantine; không mặc định xóa toàn Redis.
7. **Đối soát:** xác nhận key/value mới đáp ứng schema, số lỗi giảm và business flow trở lại bình thường.

### Ví dụ lỗi rollout

Trước deploy:

~~~text
Service A ghi JSON v1 với priceCents là số nguyên.
Service B đọc ProductCacheV1.
~~~

Sau deploy:

~~~text
Service A mới ghi priceCents dạng object { amount, currency }.
Service B cũ vẫn đọc ProductCacheV1.
~~~

Nếu cùng dùng prefix `v1`, deserialization có thể lỗi hàng loạt hoặc diễn giải sai. Một giải pháp tốt hơn là **thay schemaVersion/namespace v2, kiểm thử compatibility và rollout producer–consumer theo kế hoạch**, thay vì tắt `FAIL_ON_UNKNOWN_PROPERTIES` rồi hy vọng mọi trường hợp đều an toàn.

## 18. Các sai lầm thường gặp

| Sai lầm | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Tin Redis value vì Redis ở private network | Writer hoặc input bên ngoài vẫn có thể làm hỏng dữ liệu | Coi value là input, kiểm tra theo contract |
| `RedisTemplate<String,Object>` dùng serializer khôi phục kiểu tùy ý | Có thể tạo object graph ngoài mong muốn | Ưu tiên typed DTO và serializer hạn chế |
| Native Java deserialization với dữ liệu không tin cậy | Rủi ro object graph/gadget và tài nguyên | Tránh dùng; migration hoặc lọc type nghiêm ngặt cho legacy |
| Bật Jackson default typing quá rộng | Payload có thể điều khiển Java subtype | Không dùng `Id.CLASS` tùy ý; allowlist hữu hạn |
| Deserialize rồi mới kiểm tra kích thước | Parser có thể đã phân bổ object lớn | Đọc raw bytes hoặc kiểm tra bên trong serializer trước parser |
| Chỉ kiểm tra compressed byte length | Dữ liệu giải nén có thể phình lớn | Bounded decompression và parser limits |
| Chỉ đặt max byte size | JSON nhỏ nhưng lồng sâu hoặc nhiều field vẫn gây tốn tài nguyên | Thêm depth/string/number/collection limits |
| Parse vào `Map<String,Object>` để “linh hoạt” | Schema không rõ, khó kiểm tra kiểu | DTO có version và validation rõ |
| Tin type metadata do payload tự khai | Parser có thể tạo type không cần thiết | Typed DTO hoặc discriminator + subtype allowlist |
| Lỗi decode nào cũng xóa key | Có thể mất dữ liệu, xóa value mới sau race | Policy theo loại dữ liệu và cleanup có điều kiện |
| Lỗi decode nào cũng retry | Poison message/cache entry không tự sửa | Phân loại malformed/schema lỗi, DLQ/migration |
| Error từ serializer bị nuốt thành cache miss | Che lỗi rollout hoặc dữ liệu không tương thích | Ghi metric và fallback có điều kiện |
| Chỉ validate lúc ghi | Các writer khác hoặc backup có thể đưa payload lỗi vào | Validate cả ở ranh giới đọc |
| Chỉ validate trong controller | `@Cacheable` có thể deserialize trước khi method chạy | Đặt giới hạn ở Redis serializer/cache layer |
| Không kiểm tra ID trong payload khớp key | Dùng nhầm dữ liệu của resource khác | Kiểm tra key và DTO cùng context |
| Dùng Redis key prefix thay authorization | Tenant khác có thể truy cập data nếu code bỏ kiểm tra | Kiểm tra identity và quyền ở service |
| Ghi raw payload vào log khi parse lỗi | Có thể lộ secret/PII | Log reason, namespace, kích thước, trace ID |
| Đổi serializer trên key cũ mà không migration | Cache miss và lỗi decode hàng loạt | Version namespace, rollout và fixture tests |
| Test chỉ với JSON hợp lệ | Không phát hiện nhánh quá lớn/unknown subtype/duplicate field | Unit + integration tests payload lỗi |
| Đặt parser constraint nhưng không giới hạn request đồng thời | Nhiều input hợp lệ vẫn gây heap/CPU pressure | Concurrency/backpressure và memory budget |

## 19. Khi nào validation không đủ?

Một số vấn đề không thể giải quyết chỉ bằng kiểm tra JSON:

**Authorization:** một payload có thể đúng schema nhưng thuộc tài nguyên mà caller không được phép xem. Phải kiểm tra identity/tenant/role tại tầng nghiệp vụ.

**Stale data:** một DTO hợp lệ nhưng chứa dữ liệu cũ từ replica hoặc cache chưa được invalidated. Cần TTL, version, consistency và cache invalidation phù hợp.

**Data integrity:** JSON hợp lệ không chứng minh nó được ghi bởi producer được phép. Cần ACL, kiểm soát writer, và integrity verification nếu threat model yêu cầu.

**Atomicity:** nhiều key hợp lệ không có nghĩa nghiệp vụ cập nhật atomically. Redis transaction/script, database transaction hoặc idempotency cần được thiết kế riêng.

**Availability:** parser từ chối payload quá lớn không cứu được server đang quá tải vì GET khổng lồ. Cần giới hạn ở writer, thiết kế key/value, network, connection và tải toàn hệ thống.

**Schema evolution:** validator nghiêm ngặt sẽ từ chối version mới khi reader chưa được triển khai tương thích. Cần rollout/migration, không đơn giản tắt tất cả kiểm tra.

Bảo mật ở ranh giới deserialization là **một phần của defense in depth**, không thay thế ràng buộc nhất quán và phân quyền.

## 20. Nguyên tắc triển khai trong Spring Data Redis

Đối với một namespace Redis mới, hãy xác định các câu trả lời dưới đây trước khi triển khai:

- **Ai được ghi key này?** Redis user, service identity và nguồn dữ liệu ban đầu.
- **Value là gì?** String, JSON DTO, Hash, Stream event hay bytes?
- **Giới hạn ra sao?** Maximum encoded bytes, depth, string length, collection size và TTL.
- **Kiểu nào được tạo?** DTO hoặc subtype được allowlist; không tạo Java class theo input.
- **Schema version nào được hỗ trợ?** Đổi version thế nào khi deploy nhiều service?
- **Đặt validation ở đâu?** Trước parser, ngay trong parser/serializer và sau DTO mapping.
- **Khi sai thì làm gì?** Cache fallback, fail closed, DLQ/quarantine hay migration.
- **Làm sao kiểm thử?** Unit test bad bytes và integration test Redis thật.
- **Làm sao giám sát?** Theo dõi reason, namespace, kích thước, số lần từ chối và tác động nghiệp vụ.

Một quy trình gọn:

~~~text
            Xác định Redis namespace + schema
                           |
                           v
             Cấp ACL đúng người ghi/đọc
                           |
                           v
            Validate dữ liệu trước khi SET
                           |
                           v
                  Redis lưu raw bytes
                           |
                           v
               Đọc bytes có budget phù hợp
                           |
                           v
                Kiểm tra byte size sớm
                           |
                           v
            Parser có resource constraints
                           |
                           v
                  DTO có kiểu cố định
                           |
                           v
            Kiểm tra version/range/context
                           |
                  +--------+--------+
                  |                 |
                Hợp lệ          Không hợp lệ
                  |                 |
                  v                 v
            Dùng trong service   Policy xử lý lỗi
                                + metric an toàn
~~~

## 21. Tổng kết

**Kiểm soát dữ liệu đầu vào trước khi giải tuần tự hóa** trong Spring Data Redis đòi hỏi thiết kế rõ ràng hơn việc gọi `RedisTemplate.get(...)` rồi kiểm tra kết quả có null hay không. Redis là nơi lưu byte; serializer quyết định byte đó được diễn giải và biến thành object Java như thế nào.

Những biện pháp cốt lõi:

1. **Không mặc định tin Redis value.** Dữ liệu có thể bắt nguồn từ user input, writer khác, migration hoặc bản sao lưu.
2. **Tránh native Java deserialization và polymorphic typing không giới hạn** cho input không tin cậy.
3. **Giới hạn byte trước khi parser chạy**, đồng thời áp dụng resource constraints cho JSON, collection và dữ liệu nén.
4. **Deserialize thành DTO cụ thể**, với schema version và danh sách subtype hữu hạn khi cần.
5. **Validate sau parse** những thuộc tính phụ thuộc nghiệp vụ, identifier, tenant và miền giá trị.
6. **Đặt validation tại ranh giới thật sự deserialization**, nhất là với serializer của RedisTemplate và Spring Cache.
7. **Phân loại lỗi theo vai trò dữ liệu**, không tự retry vô hạn hoặc xóa dữ liệu quan trọng khi parse thất bại.
8. **Kiểm thử bằng raw bytes và Redis thật**, có case quá lớn, JSON lỗi, field không hỗ trợ, sai version và mismatch với key.
9. **Kết hợp ACL, TLS, metrics và migration** để giảm bề mặt lỗi và phát hiện dữ liệu bất thường.

Một ứng dụng an toàn không phải ứng dụng có parser “đọc được mọi thứ”, mà là ứng dụng **chỉ chấp nhận những dữ liệu được phép, trong giới hạn tài nguyên xác định, theo schema mà nghiệp vụ hiểu rõ**. Khi ranh giới đó được đặt trước và trong deserialization, Spring Data Redis có thể lưu và đọc cache/event hiệu quả hơn mà không biến dữ liệu Redis thành con đường khởi tạo object Java không kiểm soát.

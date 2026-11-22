# Cấu hình kiểu tham số và serializer của RedisTemplate

Khi làm việc với **Spring Data Redis**, một câu lệnh như `redisTemplate.opsForValue().set("product:42", product)` trông giống thao tác với một `Map` trong Java. Nhưng Redis không hiểu trực tiếp `Product`, `Long` hay `LocalDateTime`. Redis lưu trữ **các chuỗi byte** dưới những cấu trúc dữ liệu của nó. Vì vậy, ứng dụng phải quyết định:

- Java sẽ coi **key** và **value** có kiểu gì khi lập trình?
- Các giá trị đó được **mã hóa thành byte** và **giải mã từ byte** theo quy tắc nào?
- Key của String, Hash field và Hash value có cần cách serialize khác nhau không?
- Những instance `RedisTemplate` nào có thể đọc dữ liệu do instance khác ghi?
- Điều gì xảy ra khi thay đổi serializer trong một hệ thống đã có dữ liệu?

Hai khái niệm trung tâm của bài học là **kiểu tham số generic `RedisTemplate<K, V>`** và **`RedisSerializer`**. Chúng có liên hệ nhưng không thay thế lẫn nhau: **generic quyết định kiểu sử dụng ở compile time, còn serializer quyết định dữ liệu thực sự được lưu thành byte gì trong Redis**.

## 1. RedisTemplate nằm ở đâu trong luồng dữ liệu?

~~~text
                       Ứng dụng Spring Boot
                                |
                  RedisTemplate<String, Product>
                       (Java API / generics)
                                |
                      RedisSerializer cho:
                key / value / hash key / hash value
                                |
                     byte[] của key và value
                                |
                         RedisConnection
                                |
                         Lettuce / Jedis
                                |
                         Redis server
                                |
                     byte[] được lưu trong Redis
~~~

Khi gọi `opsForValue().set(key, value)`, `RedisTemplate` thường thực hiện các bước:

1. Nhận `key` và `value` là đối tượng Java.
2. Dùng **key serializer** để biến key thành byte.
3. Dùng **value serializer** để biến value thành byte.
4. Gửi lệnh Redis qua `RedisConnectionFactory` và driver.
5. Khi đọc lại, dùng serializer tương ứng để giải mã byte thành đối tượng Java.

Ví dụ cùng một giá trị Java `42L`:

| Serializer | Byte được ghi (mô tả) | Redis CLI nhìn thấy | Đọc bằng serializer khác |
|---|---|---|---|
| `StringRedisSerializer` với chuỗi `"42"` | UTF-8 cho hai ký tự `4` và `2` | `42` | Serializer Java/JDK không hiểu đây là object đã serialize |
| `GenericToStringSerializer<Long>` | Chuỗi biểu diễn số, thường `42` | `42` | Cần serializer chấp nhận chuỗi số |
| `JdkSerializationRedisSerializer` | Binary có header định dạng Java serialization | Không đọc như text thông thường | String/JSON serializer không giải mã được |
| JSON serializer cho object thích hợp | Byte JSON, ví dụ `{"id":42}` | Có thể đọc như JSON | Java/JDK serializer không đọc như object JDK |

Redis không có cơ chế tự phát hiện JSON, Java serialization hay tên lớp. Serializer dùng lúc **đọc** phải tương thích với dữ liệu đã ghi.

## 2. Hiểu đúng hai tham số generic: RedisTemplate<K, V>

Khai báo cơ bản:

~~~java
public class RedisTemplate<K, V> {
    // Các thao tác Redis qua key kiểu K và value kiểu V
}
~~~

Một template:

~~~java
RedisTemplate<String, ProductSnapshot> productRedisTemplate;
~~~

có ý nghĩa:

- `K = String`: những phương thức nhận key chính của Redis được lập trình với `String`.
- `V = ProductSnapshot`: những thao tác làm việc với value trực tiếp thường sử dụng `ProductSnapshot`.

Ví dụ:

~~~java
ProductSnapshot product =
        new ProductSnapshot(42L, "SKU-42", "Bàn phím");

productRedisTemplate.opsForValue()
        .set("shop:product:42", product);

ProductSnapshot loaded = productRedisTemplate.opsForValue()
        .get("shop:product:42");
~~~

Ở đây, kiểu generic giúp compiler kiểm tra lời gọi và IDE gợi ý đúng kiểu. Nhưng **khai báo generic không tự chọn JSON, String hay Java serialization**. RedisTemplate cần serializer phù hợp thì thao tác mới được chuyển đổi chính xác.

### 2.1. Generic là kiểm tra kiểu Java, không phải schema của Redis

Java triển khai generic theo type erasure: khi chương trình chạy, thông tin generic không tự động biến thành một schema Redis. Hai template này có thể cùng truy cập key `shop:product:42`:

~~~java
RedisTemplate<String, ProductSnapshot> productTemplate;
RedisTemplate<String, String> stringTemplate;
~~~

Nhưng chúng **không đương nhiên tương thích**. Nếu `productTemplate` ghi JSON và `stringTemplate` đọc bằng `StringRedisSerializer`, kết quả nhận được có thể chỉ là chuỗi JSON, không phải `ProductSnapshot`. Nếu một template dùng JDK serialization còn template khác dùng JSON, việc deserialize có thể lỗi.

Kiểu generic cũng không tự ngăn một service khác ghi dữ liệu không đúng vào cùng key thông qua Redis CLI hoặc một template khác. **Hợp đồng lưu trữ phải được quy định ở cấp keyspace, serializer và schema dữ liệu**.

### 2.2. Một số kiểu khai báo thường gặp

| Khai báo | Phù hợp với | Điều kiện |
|---|---|---|
| `StringRedisTemplate` | Key và value chuỗi, counter, marker, mã trạng thái | Các thao tác của template dùng string serializers |
| `RedisTemplate<String, String>` | Một template chuyên dùng chuỗi | Cần cấu hình String serializer cho key/value |
| `RedisTemplate<String, ProductSnapshot>` | Value là object của một loại xác định | Value serializer phải xử lý được `ProductSnapshot` |
| `RedisTemplate<String, Long>` | Value Java biểu diễn số | Serializer phải có dạng phù hợp với lệnh Redis cần gọi |
| `RedisTemplate<String, byte[]>` | Value nhị phân đã do ứng dụng encode | Cần byte-array serializer |
| `RedisTemplate<String, Object>` | Nhiều kiểu value khác nhau | Cần chiến lược lưu type metadata/định dạng rõ ràng; dễ tăng rủi ro migration |

**Không nên dùng `RedisTemplate<Object, Object>` cho mọi tính năng chỉ vì nó linh hoạt.** Một template có kiểu cụ thể thường làm hợp đồng dữ liệu dễ hiểu hơn và giảm nhầm serializer.

## 3. Các vị trí serializer trong RedisTemplate

`RedisTemplate` có nhiều thuộc tính serializer độc lập:

| Thuộc tính | Dùng cho | Ví dụ |
|---|---|---|
| `keySerializer` | Key chính của Redis | `shop:product:42` |
| `valueSerializer` | Value của String, thành phần của List/Set/ZSet và các API tương ứng | `ProductSnapshot` được mã hóa JSON |
| `hashKeySerializer` | Field của Redis Hash | `name`, `price`, `stock` |
| `hashValueSerializer` | Giá trị của field trong Redis Hash | `"Bàn phím"`, `"199000"` |
| `stringSerializer` | Một số đối số dạng String trong các thao tác Redis cần chuyển đổi chuỗi | Không phải nút thay thế mọi serializer còn lại |
| `defaultSerializer` | Giá trị dự phòng cho serializer chưa được cấu hình riêng, nếu bật cơ chế mặc định | Có thể là serializer Java/JDK |

Khi làm việc với Hash:

~~~text
Redis key:    shop:product:42
    field:    name
    value:    "Bàn phím"
    field:    stock
    value:    "16"
~~~

`keySerializer` mã hóa `shop:product:42`; `hashKeySerializer` mã hóa `name` và `stock`; `hashValueSerializer` mã hóa các giá trị field.

Không được nhầm `hashKeySerializer` với serializer của **key chính**. Hash key ở đây có nghĩa **tên field nằm trong Hash**, không phải `shop:product:42`.

### 3.1. HashOperations có generic riêng

API:

~~~java
HashOperations<K, HK, HV> hashOps = redisTemplate.opsForHash();
~~~

Trong đó:

- `K`: key chính của Redis.
- `HK`: hash field.
- `HV`: hash field value.

Hai kiểu `HK` và `HV` **không buộc phải trùng với `V` của RedisTemplate**. Ví dụ template `RedisTemplate<String, ProductSnapshot>` vẫn có thể thao tác một Hash với field/value đều là `String`, nếu cấu hình `hashKeySerializer` và `hashValueSerializer` thích hợp:

~~~java
HashOperations<String, String, String> hashOps =
        productRedisTemplate.opsForHash();

hashOps.put("shop:product:42:metrics", "views", "125");
String views = hashOps.get("shop:product:42:metrics", "views");
~~~

Nhưng cần chủ động quyết định kiểu field/value. Vì `opsForHash()` có thể suy luận kiểu generic từ biến nhận kết quả, compiler không tự xác nhận serializer runtime thực sự tương thích.

### 3.2. Các lệnh nào dùng value serializer?

Ở mức khái quát:

- `opsForValue()`: String value.
- `opsForList()`: phần tử List.
- `opsForSet()`: member Set.
- `opsForZSet()`: member Sorted Set; điểm số (score) vẫn là số theo protocol Redis.
- `opsForHash()`: dùng **hash key** và **hash value** serializers riêng.
- Những thao tác low-level qua `RedisConnection` có thể làm việc trực tiếp với byte array, không nhất thiết đi qua serializer của template.

Các API Pub/Sub, Streams, script execution hoặc low-level callback có thể có hợp đồng serializer riêng tùy phương thức. Khi dùng tính năng chuyên biệt, đọc cách API đó nhận và trả byte thay vì suy luận từ `valueSerializer` chung.

## 4. Mặc định của RedisTemplate và StringRedisTemplate

### 4.1. RedisTemplate mặc định không tự biến object thành JSON

Một `RedisTemplate` được khởi tạo theo cấu hình thông thường có thể dùng `JdkSerializationRedisSerializer` làm serializer mặc định cho những vị trí không được cấu hình riêng.

Hệ quả:

- Key `"shop:product:42"` có thể được lưu dưới dạng Java binary serialization thay vì chữ UTF-8 dễ đọc.
- `redis-cli --raw GET ...` có thể thấy byte khó hiểu.
- Dữ liệu ràng buộc vào class Java, cách Java serialization hoạt động và khả năng tương thích khi thay phiên bản.
- Không phù hợp khi Redis cần được đọc trực tiếp từ nhiều ngôn ngữ hoặc dịch vụ dùng định dạng chung.

Trong Spring Boot, việc cấu hình:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
~~~

chỉ xác định cách kết nối Redis; **không có nghĩa bean RedisTemplate của bạn đã được cấu hình JSON**. Cần xem bean thực tế và các customizer mà ứng dụng dùng.

### 4.2. StringRedisTemplate dùng cho key/value dạng chuỗi

`StringRedisTemplate` là lựa chọn đơn giản khi muốn tên key và value có thể đọc được bằng Redis CLI:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class PageViewCounter {

    private final StringRedisTemplate redis;

    public PageViewCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long increment(long productId) {
        return redis.opsForValue()
                .increment("shop:product:views:" + productId);
    }

    public String getStatus(String jobId) {
        return redis.opsForValue()
                .get("shop:job:status:" + jobId);
    }
}
~~~

`StringRedisTemplate` cấu hình serializer dành cho chuỗi đối với key, value, hash field và hash value. Nó rất hữu ích cho:

- Counter sử dụng `INCR`/`DECR`.
- Marker có TTL.
- Trạng thái dạng `"PENDING"`/`"DONE"`.
- Hash với tên field và value đều là chuỗi.
- Những trường hợp không cần object mapper tự động.

Muốn lưu object qua `StringRedisTemplate`, ứng dụng có thể tự chuyển object sang JSON String trước khi gọi `set()` và parse ngược lúc đọc; hoặc dùng `RedisTemplate<String, ProductSnapshot>` với JSON serializer để việc chuyển đổi được thực hiện tại template.

### 4.3. Cẩn thận với counter và JDK serialization

Redis `INCR` yêu cầu value hiện tại biểu diễn một **số nguyên dạng chuỗi phù hợp Redis**, không phải Java object serialization.

Nếu tạo `RedisTemplate<String, Long>` nhưng để value serializer theo JDK binary, sau đó gọi `increment` hoặc trộn với một lệnh `INCR` từ Redis CLI, dữ liệu có thể không tương thích.

Ví dụ đúng và đơn giản nhất cho counter:

~~~java
Long newValue = stringRedisTemplate
        .opsForValue()
        .increment("shop:metric:orders");
~~~

Đừng suy luận từ `V = Long` rằng Redis sẽ lưu chuỗi `"123"`. **Chính serializer và loại lệnh Redis quyết định khả năng tương thích**.

## 5. Cấu hình RedisTemplate<String, ProductSnapshot> với JSON

Giả sử dự án sử dụng **Spring Boot 3.x, Spring Data Redis 3.x và Jackson 2**, một DTO đơn giản:

~~~java
package com.example.shop.redis;

public record ProductSnapshot(
        Long id,
        String sku,
        String name
) {}
~~~

Đây là object đưa vào Redis để ứng dụng đọc lại, không nhất thiết phải là JPA entity. Nên dùng một DTO lưu trữ ổn định, tránh vô tình serialize toàn bộ graph của entity có quan hệ phức tạp.

Cấu hình một template chuyên biệt:

~~~java
package com.example.shop.redis;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ProductRedisTemplateConfig {

    @Bean("productRedisTemplate")
    public RedisTemplate<String, ProductSnapshot> productRedisTemplate(
            RedisConnectionFactory connectionFactory,
            ObjectMapper objectMapper) {

        RedisTemplate<String, ProductSnapshot> template =
                new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer textSerializer =
                new StringRedisSerializer();

        Jackson2JsonRedisSerializer<ProductSnapshot> jsonSerializer =
                new Jackson2JsonRedisSerializer<>(
                        objectMapper, ProductSnapshot.class
                );

        template.setKeySerializer(textSerializer);
        template.setValueSerializer(jsonSerializer);

        // Ví dụ ứng dụng này dùng Hash field và Hash value là String.
        template.setHashKeySerializer(textSerializer);
        template.setHashValueSerializer(textSerializer);

        template.afterPropertiesSet();
        return template;
    }
}
~~~

**Ý nghĩa từng lựa chọn:**

- `RedisTemplate<String, ProductSnapshot>` tạo API Java với key String và value ProductSnapshot.
- `setKeySerializer(new StringRedisSerializer())` lưu key dưới dạng text UTF-8, thuận tiện debug và tương thích với công cụ Redis CLI.
- `setValueSerializer(jsonSerializer)` chuyển `ProductSnapshot` thành JSON bytes và đọc ngược theo kiểu `ProductSnapshot`.
- `setHashKeySerializer(textSerializer)` đặt tên field Hash là chuỗi.
- `setHashValueSerializer(textSerializer)` thể hiện **hợp đồng riêng**: Hash field value sẽ là String nếu sử dụng HashOperations cùng kiểu đó.
- `afterPropertiesSet()` khởi tạo template sau khi đã cấu hình; Spring cũng gọi vòng đời bean khi quản lý bean, việc gọi tường minh ở ví dụ chỉ để thể hiện thao tác khởi tạo.

Mẫu constructor của Jackson serializer ở trên tương ứng nhánh Spring Data Redis sử dụng Jackson 2. API JSON serializer có thể khác giữa các phiên bản Spring Data Redis/Jackson; trong dự án thực tế cần chọn constructor được hỗ trợ bởi dependency đang sử dụng.

### 5.1. Sử dụng qua @Qualifier

Nếu ứng dụng có nhiều RedisTemplate, nên xác định chính xác bean được dùng:

~~~java
package com.example.shop.redis;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductSnapshotStore {

    private final RedisTemplate<String, ProductSnapshot> redis;

    public ProductSnapshotStore(
            @Qualifier("productRedisTemplate")
            RedisTemplate<String, ProductSnapshot> redis) {
        this.redis = redis;
    }

    public void save(ProductSnapshot product) {
        String key = "shop:product:" + product.id();
        redis.opsForValue().set(
                key, product, Duration.ofMinutes(20)
        );
    }

    public ProductSnapshot find(long productId) {
        return redis.opsForValue()
                .get("shop:product:" + productId);
    }

    public void remove(long productId) {
        redis.delete("shop:product:" + productId);
    }
}
~~~

Bài toán ở đây là lưu một snapshot JSON có TTL 20 phút. Trong Redis CLI, nếu giá trị là JSON do serializer ghi, có thể đọc:

~~~bash
redis-cli --raw GET shop:product:42
redis-cli TTL shop:product:42
~~~

Kết quả minh họa của `GET`:

~~~json
{"id":42,"sku":"SKU-42","name":"Bàn phím"}
~~~

Hình dạng JSON thực tế phụ thuộc `ObjectMapper` (naming strategy, date/time modules, inclusion và các cấu hình khác). Đừng ràng buộc hệ thống khác vào một hình dạng JSON chưa được quy định thành hợp đồng.

### 5.2. Tại sao dùng ObjectMapper được inject?

Spring Boot có thể cấu hình `ObjectMapper` chung với module thời gian, naming strategy hoặc quy tắc null. Dùng bean mapper được inject giúp serializer tuân theo các quyết định định dạng đang được ứng dụng quản lý.

Tuy nhiên, **chung ObjectMapper không có nghĩa JSON của Redis nhất thiết phải giống HTTP JSON**. Dữ liệu Redis có yêu cầu tương thích khi deploy và TTL riêng; đôi khi cần một mapper được cấu hình chuyên biệt cho Redis DTO, miễn là được quản lý nhất quán.

Không để những thay đổi nhỏ của REST response vô tình làm dữ liệu lưu Redis mất tương thích nếu Redis lưu lâu dài.

## 6. Cấu hình cho Hash: field serializer khác value serializer

Giả sử cần lưu Hash:

~~~text
HSET shop:product:42:info name "Bàn phím"
HSET shop:product:42:info category "accessories"
~~~

Có thể dùng `StringRedisTemplate`:

~~~java
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

public class ProductHashStore {

    private final HashOperations<String, String, String> hashOps;

    public ProductHashStore(StringRedisTemplate template) {
        this.hashOps = template.opsForHash();
    }

    public void putName(long id, String name) {
        hashOps.put("shop:product:" + id + ":info", "name", name);
    }

    public String getName(long id) {
        return hashOps.get("shop:product:" + id + ":info", "name");
    }
}
~~~

Đối với Hash có value là object, cấu hình `hashValueSerializer` theo loại object:

~~~java
template.setHashKeySerializer(new StringRedisSerializer());
template.setHashValueSerializer(
        new Jackson2JsonRedisSerializer<>(
                objectMapper, ProductSnapshot.class
        )
);
~~~

Khi đó:

~~~java
HashOperations<String, String, ProductSnapshot> hashOps =
        template.opsForHash();

hashOps.put("shop:product:snapshots", "42", product);
ProductSnapshot p =
        hashOps.get("shop:product:snapshots", "42");
~~~

Nếu đổi Hash value từ String sang JSON object, đây là **thay đổi hợp đồng dữ liệu**. Hash field cũ lưu `"Bàn phím"` không tự biến thành `{"name":"Bàn phím"}`, và serializer ProductSnapshot sẽ không nhất thiết đọc được dữ liệu cũ.

### 6.1. Một template có thể có Value kiểu ProductSnapshot nhưng HashValue kiểu String?

Có. Các nhóm serialization độc lập. Ví dụ:

~~~text
SET shop:product:42 <ProductSnapshot JSON>
HSET shop:product:42:metrics views "125"
~~~

Cùng template có thể:

~~~java
RedisTemplate<String, ProductSnapshot> productRedisTemplate;

productRedisTemplate.opsForValue().get("shop:product:42");
// -> ProductSnapshot (valueSerializer JSON)

HashOperations<String, String, String> metrics =
        productRedisTemplate.opsForHash();

metrics.get("shop:product:42:metrics", "views");
// -> String (hashValueSerializer String)
~~~

Điều này hợp lệ khi serializer đã đặt đúng. Nhưng một template chứa quá nhiều chính sách lưu trữ khác nhau sẽ khó bảo trì. Khi hai nhóm dữ liệu có quy tắc serialization/TTL/owner khác biệt đáng kể, dùng **hai template có tên rõ nghĩa** giúp giảm lỗi hơn.

## 7. Các serializer thường gặp và cách chọn

| Serializer | Dữ liệu phù hợp | Ưu điểm | Lưu ý |
|---|---|---|---|
| `StringRedisSerializer` | `String` | UTF-8 dễ quan sát và tương tác với Redis CLI | Không tự chuyển object tùy ý sang JSON |
| `GenericToStringSerializer<T>` | Những kiểu có biểu diễn String ổn định | Có thể chuyển số/kiểu đơn giản thành chuỗi qua conversion | Đòi hỏi converter đọc/ghi nhất quán |
| `JdkSerializationRedisSerializer` | Java object theo Java serialization | Đơn giản khi các class Serializable tương thích | Binary khó đọc, chặt với Java class, rủi ro bảo mật khi deserialize dữ liệu không tin cậy |
| `Jackson2JsonRedisSerializer<T>` | JSON của một kiểu cụ thể (trong nhánh Jackson 2) | Định dạng rõ, API Java typed | Cần quản lý ObjectMapper/schema, class tương thích |
| `GenericJackson2JsonRedisSerializer` | Nhiều kiểu Java động (nhánh Jackson 2) | Có khả năng lưu thông tin type cho kiểu động | Type metadata, dung lượng và an toàn deserialization cần kiểm soát |
| Byte-array serializer | `byte[]` | Giữ dữ liệu nhị phân do ứng dụng kiểm soát | Ứng dụng chịu trách nhiệm định dạng và decode |

Với Spring Data Redis/Jackson mới hơn, tên lớp và constructor serializer JSON có thể khác. Ví dụ trong bài dùng API nhánh Spring Data Redis 3.x/Jackson 2 để minh họa hợp đồng thay vì khẳng định mọi phiên bản đều giống nhau.

### 7.1. StringRedisSerializer: chọn mặc định cho key

Key dạng UTF-8 thường dễ hiểu:

~~~bash
redis-cli GET shop:job:status:123
redis-cli TYPE shop:product:42
redis-cli TTL shop:product:42
~~~

Nếu key dùng JDK binary serialization, gõ `shop:product:42` ở CLI không tìm thấy key vì **byte key khác nhau**. Vấn đề không nằm ở Redis không có key, mà là byte đã được serialize khác với chuỗi gõ vào.

Một quy ước thường dùng cho ứng dụng có nhiều loại dữ liệu:

- Key chính: String serializer.
- Hash field: String serializer.
- Value: tùy loại dữ liệu, có thể String, JSON hoặc bytes.
- Hash field value: chọn độc lập theo ý nghĩa field.

### 7.2. GenericToStringSerializer<T> cho giá trị kiểu đơn giản

Ví dụ muốn Java API sử dụng Long nhưng byte Redis là chuỗi số:

~~~java
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericToStringSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

RedisTemplate<String, Long> numericTemplate = new RedisTemplate<>();
numericTemplate.setConnectionFactory(connectionFactory);
numericTemplate.setKeySerializer(new StringRedisSerializer());
numericTemplate.setValueSerializer(
        new GenericToStringSerializer<>(Long.class)
);
numericTemplate.afterPropertiesSet();
~~~

Ví dụ là đoạn cấu hình bên trong nơi đã có `RedisConnectionFactory connectionFactory`, không phải ứng dụng hoàn chỉnh. Giá trị Long sẽ dùng biểu diễn chuỗi theo converter, có thể phù hợp với các lệnh số của Redis nếu biểu diễn thực tế đúng định dạng Redis chấp nhận.

Với counter thông thường, `StringRedisTemplate.opsForValue().increment()` vẫn là lựa chọn đơn giản và minh bạch hơn.

### 7.3. JDK serialization: hiểu rủi ro khi dùng

Java serialization tạo byte có metadata và quy tắc của JVM. Một số nhược điểm:

- Byte key/value khó đọc bằng công cụ không phải Java.
- Class thay đổi có thể khiến dữ liệu cũ không thể deserialize.
- Liên thông với ứng dụng viết bằng ngôn ngữ khác kém thuận tiện.
- Deserializing dữ liệu nhị phân không tin cậy có thể gây vấn đề bảo mật nghiêm trọng, tùy classpath và cấu hình.

Khi Redis có thể bị ghi từ nguồn không tin cậy, **không dùng Java deserialization mặc định như một cơ chế chấp nhận object bất kỳ**. Giới hạn nguồn dữ liệu, quyền ghi Redis, loại object và chọn định dạng lưu trữ có hợp đồng rõ ràng.

### 7.4. JSON typed và JSON dynamic khác nhau

**JSON typed**:

~~~text
RedisTemplate<String, ProductSnapshot>
  -> Jackson2JsonRedisSerializer<ProductSnapshot>
  -> đọc key này về ProductSnapshot
~~~

**JSON dynamic**:

~~~text
RedisTemplate<String, Object>
  -> serializer có type metadata
  -> đọc về nhiều kiểu object tùy metadata
~~~

Kiểu dynamic có thể tiện cho cache đa hình, nhưng việc gắn tên class Java vào payload làm schema phụ thuộc cách đặt package/class và tăng nguy cơ deserialize type không mong muốn. Không bật default typing rộng rãi cho dữ liệu chưa được kiểm soát. Ưu tiên DTO và danh sách kiểu được cho phép nếu ứng dụng cần polymorphism.

JSON cũng không tự bảo đảm bảo mật: với dữ liệu nhạy cảm, cần thiết kế kiểm soát truy cập, mã hóa theo yêu cầu và chính sách retention độc lập với việc chọn serializer.

## 8. Những loại dữ liệu Redis đòi hỏi nghĩ về định dạng byte

### 8.1. String và counter

~~~text
SET shop:job:status:123 DONE
INCR shop:metric:orders
~~~

Value chuỗi hoặc số nguyên dạng chữ có thể làm việc với `StringRedisTemplate`. Đừng ghi `Long` bằng Java serialization rồi mong `INCR` hiểu nó như số.

### 8.2. List, Set và Sorted Set

Với `RedisTemplate<String, ProductSnapshot>` dùng JSON value serializer:

~~~java
redis.opsForList().rightPush("shop:recent-products", product);
redis.opsForSet().add("shop:featured-products", product);
redis.opsForZSet().add("shop:ranked-products", product, 95.5);
~~~

Thành phần List, Set hoặc ZSet được serialize theo **value serializer** của template. Score của ZSet là số do Redis quản lý, không phải cùng byte với ProductSnapshot.

Lưu ý khi dùng object làm member Set/ZSet: tính duy nhất của Redis dựa vào **byte đã serialize**, không dựa vào `equals()` trong Java. Nếu cùng một sản phẩm có JSON khác thứ tự field hoặc khác metadata, Redis có thể coi đó là hai member khác nhau.

Đối với Set/ZSet có yêu cầu identity ổn định, nhiều hệ thống chọn lưu **ID String** thay vì toàn bộ object JSON rồi lấy chi tiết qua key riêng.

### 8.3. Hash

Hash có hai serializer bổ sung cho field và field value. Một template dùng JSON cho String value nhưng String cho Hash value là cấu hình hợp lệ; ngược lại, quên `setHashValueSerializer` có thể khiến Hash value bị ghi dưới dạng JDK binary dù String value được lưu JSON.

### 8.4. Pub/Sub, Streams và Script

Các API Redis nâng cao có thể dùng quy tắc codec/serialization riêng cho channel, message, stream record, script args và result. Không nên suy luận rằng:

~~~java
template.setValueSerializer(jsonSerializer);
~~~

tự đặt JSON cho **tất cả** channel, field và payload của mọi API Redis. Với mỗi tính năng, xác định dữ liệu nào được serialize bởi template và dữ liệu nào do callback/driver xử lý trực tiếp.

## 9. Cấu hình nhiều RedisTemplate trong cùng ứng dụng

Một hệ thống có thể vừa cần JSON cho product cache, vừa cần String cho counter và marker.

~~~text
                       RedisConnectionFactory
                               |
               +---------------+---------------+
               |                               |
       StringRedisTemplate           productRedisTemplate
       key/value: String             key: String
       hash: String                  value: ProductSnapshot JSON
               |                               |
               +----------------+--------------+
                                |
                             Redis
~~~

Ví dụ service inject hai template:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductMetricsService {

    private final StringRedisTemplate counters;
    private final RedisTemplate<String, ProductSnapshot> snapshots;

    public ProductMetricsService(
            StringRedisTemplate counters,
            @Qualifier("productRedisTemplate")
            RedisTemplate<String, ProductSnapshot> snapshots) {
        this.counters = counters;
        this.snapshots = snapshots;
    }

    public void viewed(long productId) {
        counters.opsForValue()
                .increment("shop:product:views:" + productId);
    }

    public ProductSnapshot snapshot(long productId) {
        return snapshots.opsForValue()
                .get("shop:product:" + productId);
    }
}
~~~

**Chia sẻ RedisConnectionFactory không đồng nghĩa chia sẻ serializer.** Mỗi template có chính sách mã hóa riêng và có thể sử dụng cùng Redis server hoặc topology.

Khi định nghĩa bean tùy biến trong Spring Boot:

- Gắn tên bean rõ nghĩa.
- Dùng `@Qualifier` nếu cần phân biệt.
- Kiểm tra điều kiện auto-configuration để không vô tình thay một bean mặc định đang được thành phần khác sử dụng.
- Không khai báo nhiều bean cùng tên nếu không có chủ đích override.
- Để Spring quản lý lifecycle của factory và template, thay vì tạo template mới mỗi request.

## 10. Redis Cache và Spring Session có tự dùng serializer của RedisTemplate không?

Không được mặc định như vậy.

| Thành phần | Cấu hình serialization chính |
|---|---|
| `RedisTemplate` | `setKeySerializer`, `setValueSerializer`, `setHashKeySerializer`, `setHashValueSerializer` |
| `StringRedisTemplate` | String serializers do template cung cấp |
| Spring Cache với Redis | `RedisCacheManager` và `RedisCacheConfiguration` |
| Spring Session với Redis | Repository và serializer dành riêng cho Spring Session, tùy cấu hình/phiên bản |
| Redis Repository | Keyspace mapping, converter và quy tắc serialization của repository |

Ví dụ bạn thay:

~~~java
productRedisTemplate.setValueSerializer(jsonSerializer);
~~~

thì **không có nghĩa** `@Cacheable` đã chuyển sang JSON hoặc mọi thuộc tính HTTP session đã đổi định dạng. Các thành phần này có abstraction và cấu hình riêng, dù có thể dùng chung RedisConnectionFactory.

Đối với Redis Cache, có thể cấu hình `RedisCacheConfiguration.serializeValuesWith(...)` bằng một `RedisSerializationContext.SerializationPair` phù hợp. Với Spring Session, cơ chế serializer cần được cấu hình theo hợp đồng Spring Session tương ứng, không bằng cách sửa ngẫu nhiên một RedisTemplate.

## 11. Kiểu Java và JSON schema khi thay đổi phiên bản ứng dụng

Giả sử Redis đang lưu:

~~~json
{"id":42,"sku":"SKU-42","name":"Bàn phím"}
~~~

Trong phiên bản mới, DTO thay đổi thành:

~~~java
public record ProductSnapshot(
        Long id,
        String sku,
        String name,
        String category
) {}
~~~

Với một số cấu hình Jackson, field mới thiếu trong JSON có thể nhận null; với cấu hình strict hoặc validation, deserialize có thể thất bại. Đổi tên field, kiểu số, kiểu enum, package/class hay date format cũng có thể gây tương thích ngược không mong muốn.

Hãy xem Redis value như **dữ liệu có schema**, dù Redis không ép schema:

1. Xác định DTO lưu Redis riêng với DTO HTTP nếu vòng đời khác nhau.
2. Quy định serializer và ObjectMapper nào sở hữu keyspace.
3. Giới hạn TTL của dữ liệu tạm để giảm thời gian cùng tồn tại nhiều schema.
4. Nếu cần đổi định dạng mạnh, dùng prefix version như `v2:shop:product:42`.
5. Chọn chiến lược chuyển đổi hoặc đọc kép trong giai đoạn triển khai cuốn chiếu.
6. Chỉ xóa key cũ khi chắc chắn không còn thành phần cần đọc.

### 11.1. Migration từ JDK binary sang JSON

Tình huống:

~~~text
Phiên bản cũ: key được serialize bằng JDK
              value được serialize bằng JDK

Phiên bản mới: key là UTF-8
               value là JSON
~~~

Nếu phiên bản mới gọi:

~~~java
jsonTemplate.opsForValue().get("shop:product:42");
~~~

nó có thể nhận null dù Redis vẫn có dữ liệu cũ. Lý do: byte key của `"shop:product:42"` theo UTF-8 **khác** byte key được serialize bằng JDK.

Nếu key đúng nhưng value cũ là JDK bytes, JSON serializer mới có thể ném lỗi deserialize. Đây là hai kiểu lỗi khác nhau:

- **Không tìm thấy dữ liệu** do byte của key thay đổi.
- **Tìm thấy key nhưng không đọc được value** do serializer value thay đổi.

Chiến lược migration có thể gồm:

~~~text
1. Ghi dữ liệu mới theo schema v2
2. Trong giai đoạn chuyển tiếp, thử đọc v2 trước
3. Nếu v2 miss, đọc qua template/serializer v1 tương ứng
4. Khi đọc v1 thành công, chuyển sang DTO v2 và ghi lại
5. Theo dõi tỷ lệ đọc v1, chờ TTL hoặc cleanup theo kế hoạch
6. Bỏ fallback v1 sau khi không còn key cũ cần phục vụ
~~~

Trong migration dùng Redis Cluster, thay đổi byte key đồng thời có thể thay đổi hash slot. Cần xét topology, multi-key operation và khả năng di chuyển dữ liệu; không chỉ thay serializer Java.

### 11.2. Không ghi nhiều schema vào cùng một key tùy request

Nếu hai phiên bản ứng dụng đang chạy song song, phiên bản cũ ghi JDK còn phiên bản mới ghi JSON vào cùng key, dữ liệu sẽ phụ thuộc request cuối cùng ghi. Một bên có thể đọc được rồi bên kia thất bại.

Khi rolling deployment, schema/serializer phải tương thích theo cả **đọc** và **ghi**, hoặc cần tách namespace key rõ ràng.

## 12. Null, TTL và dữ liệu bị xóa

Serializer không tự quyết định TTL. Ví dụ:

~~~java
redis.opsForValue().set(
        "shop:product:42",
        product,
        Duration.ofMinutes(20)
);
~~~

TTL do lệnh Redis `SET` hoặc cơ chế expiration của template quyết định. Value serializer chỉ mã hóa `product` thành bytes.

Không nên nhầm các trường hợp:

- `GET` của key không tồn tại trả null qua API.
- Serializer nhận bytes biểu diễn JSON `null` theo hợp đồng riêng, nếu được cho phép.
- Spring Cache có thể chọn cache null hoặc bỏ qua null theo `RedisCacheConfiguration`.
- Một phương thức `RedisTemplate` có thể có hành vi khác khi truyền null cho một thao tác ghi cụ thể.

Đặc biệt, **không mặc định mọi `set(key, null)` có nghĩa là xóa key**. Hãy dùng `delete(key)` khi ý đồ là xóa; nếu cần lưu trạng thái "không có giá trị", hãy quy định dạng dữ liệu/marker rõ ràng.

## 13. Đo kích thước và xem byte lưu thực tế

Redis CLI hữu ích để quan sát dữ liệu:

~~~bash
redis-cli TYPE shop:product:42
redis-cli --raw GET shop:product:42
redis-cli STRLEN shop:product:42
redis-cli MEMORY USAGE shop:product:42
redis-cli TTL shop:product:42
~~~

Giải thích:

- `TYPE` trả loại dữ liệu Redis, ví dụ String hoặc Hash.
- `GET` cho phép nhìn value khi key tồn tại và kiểu là String.
- `STRLEN` trả độ dài byte của **value String** trong Redis, không phải độ dài tên key.
- `MEMORY USAGE` trả ước tính bộ nhớ của key/value theo cách Redis đo.
- `TTL` cho biết thời gian còn lại của key có expiration.

Nếu key được serialize bằng JDK, gõ tên text ở CLI có thể không tìm thấy. Nếu value lưu dạng JDK binary, `GET` không hiện JSON dễ đọc. Với JSON serializer, `GET` có thể hiện JSON, nhưng thứ tự field và metadata tùy mapper.

### 13.1. So sánh dung lượng serializer

Hai định dạng của cùng object có thể dùng lượng byte khác nhau. Khi đánh giá thực tế:

1. Lưu cùng dữ liệu mẫu theo những prefix riêng và serializer tương ứng.
2. So sánh `STRLEN` với String value hoặc `MEMORY USAGE` với các key phù hợp.
3. Tính thêm chi phí chuyển đổi CPU, băng thông, kích thước value và cách migration.
4. Thử phân phối payload thật: object nhỏ, object lớn, field null, danh sách dài, Unicode.
5. Không đổi toàn bộ hệ thống sang định dạng khác chỉ vì một mẫu nhỏ tiết kiệm vài byte.

Chọn serializer là quyết định về **khả năng tương thích và tính rõ ràng** trước khi là bài toán vi tối ưu dung lượng.

## 14. Những lỗi thường gặp

### Lỗi 1: Khai báo generic nhưng quên serializer

~~~java
RedisTemplate<String, ProductSnapshot> template = new RedisTemplate<>();
template.setConnectionFactory(factory);
template.afterPropertiesSet();
~~~

Tùy cấu hình, template có thể dùng serializer mặc định không phù hợp với mong muốn JSON. **Generic không cấu hình serialization**.

### Lỗi 2: Chỉ set valueSerializer, quên keySerializer

~~~java
template.setValueSerializer(jsonSerializer);
// Không cấu hình keySerializer
~~~

Key có thể được serialize theo default serializer, dẫn đến CLI không thấy key bằng tên dễ đọc. Cần quy định riêng cho key.

### Lỗi 3: Cấu hình String serializer cho object

~~~java
RedisTemplate<String, ProductSnapshot> template = new RedisTemplate<>();
template.setValueSerializer(new StringRedisSerializer());
~~~

`StringRedisSerializer` không tự nhận object ProductSnapshot rồi serialize thành JSON. Có thể phát sinh lỗi kiểu khi gọi, dù generic của template khai báo ProductSnapshot.

### Lỗi 4: Cùng tên key nhưng hai template dùng encoding khác

~~~text
StringRedisTemplate:              key UTF-8, value UTF-8
RedisTemplate mặc định kiểu JDK:  key binary, value binary
~~~

Một key hiển thị cùng tên trong Java có thể là hai byte key khác nhau; nếu key serializer giống nhau nhưng value khác nhau, dữ liệu đọc ra có thể lỗi.

### Lỗi 5: Quên hashValueSerializer

`opsForHash()` dùng cấu hình hash riêng. Đổi value serializer sang JSON không tự có nghĩa mọi hash value chuyển sang JSON.

### Lỗi 6: Dùng Java object trực tiếp trong Redis counter

`INCR`/`DECR` cần dạng số mà Redis hiểu. Một `Long` được serialize dạng JDK binary không phù hợp. Ưu tiên StringRedisTemplate cho counter.

### Lỗi 7: Dùng Generic JSON serializer với type metadata không kiểm soát

Định dạng object đa hình có thể kèm thông tin class. Với payload đến từ nguồn không tin cậy, cấu hình deserialization không an toàn có thể dẫn đến rủi ro bảo mật; cũng dễ hỏng khi đổi package/class. Hạn chế kiểu được phép và quyền ghi Redis.

### Lỗi 8: Thay serializer production mà không migrate dữ liệu

Đổi byte encoding khiến key cũ không tìm thấy hoặc value cũ không đọc được. Có thể cần versioned key, reader tương thích ngược và kế hoạch dọn key.

### Lỗi 9: Nghĩ cấu hình RedisTemplate tác động tới Cache và Session

`RedisCacheManager` và Spring Session có cấu hình riêng. Sửa bean RedisTemplate không tự áp dụng serializer của mọi Redis-backed abstraction.

### Lỗi 10: Dùng template quá chung cho mọi loại dữ liệu

`RedisTemplate<String,Object>` lưu đủ loại object với nhiều schema khác nhau khiến migration khó kiểm soát. Dùng template chuyên biệt hoặc keyspace có hợp đồng rõ ràng, đặc biệt cho dữ liệu quan trọng.

## 15. Bài tập ứng dụng

### Bài tập A: Chọn template cho dữ liệu đơn giản

Ứng dụng cần lưu:

~~~text
shop:job:status:123 -> "DONE"
shop:metric:orders  -> 125
~~~

Lựa chọn phù hợp: `StringRedisTemplate`. Trạng thái được đọc như String; counter dùng `opsForValue().increment()` để Redis thao tác trên chuỗi số.

### Bài tập B: Lưu DTO product JSON

Yêu cầu `ProductSnapshot` có id/sku/name, key rõ nghĩa và TTL 20 phút.

Hướng giải: `RedisTemplate<String,ProductSnapshot>`, key serializer `StringRedisSerializer`, value serializer JSON typed, `set(key, value, Duration)`. Đọc bằng cùng serializer sau khi đã xác định schema.

### Bài tập C: Hash chứa field chuỗi

~~~text
shop:product:42:metrics
   views  -> "125"
   likes  -> "9"
~~~

Hướng giải: `HashOperations<String,String,String>` và cả `hashKeySerializer` lẫn `hashValueSerializer` đều dùng String. Không phụ thuộc value serializer của DTO ProductSnapshot.

### Bài tập D: Hai service chia sẻ cùng Redis

Service A ghi `ProductSnapshot` bằng Jackson JSON typed; Service B viết bằng ngôn ngữ khác cần đọc cùng dữ liệu.

Hướng giải: ký hợp đồng **byte key UTF-8, JSON schema ổn định, naming convention, version, TTL và chính sách cập nhật**. Đừng dùng Java JDK serialization làm định dạng trao đổi liên ngôn ngữ.

### Bài tập E: Đổi hệ thống đang dùng JDK serializer sang JSON

Không được chỉ đổi `setValueSerializer` rồi deploy tất cả instance. Cần xác định cả key serializer cũ, chuẩn bị v2 namespace hoặc chuyển đổi dữ liệu, bảo đảm hai phiên bản đồng thời đọc/ghi an toàn, theo dõi quá trình chuyển tiếp và dọn dữ liệu cũ.

## 16. Quy trình chọn generic và serializer cho một tính năng

~~~text
                  Cần lưu dữ liệu vào Redis
                             |
                Dữ liệu Java có kiểu gì?
                  /                       \
           String / counter            DTO / object
                  |                       |
          StringRedisTemplate    Có nhiều kiểu tùy ý?
                  |                 /           \
                  |               Không           Có
                  |                 |              |
                  |         Typed JSON            Thiết kế
                  |         serializer            type contract
                  |                 |              |
                  +-----------------+--------------+
                                    |
                       Key chính có dạng String?
                                    |
                           String key serializer
                                    |
                     Có thao tác Redis Hash không?
                           /                \
                         Có                Không
                          |                  |
                  Chọn hash field/           |
                  hash value serializers     |
                          +---------+--------+
                                    |
                         Schema và TTL đã rõ?
                                    |
                         Keyspace có owner?
                                    |
                         Cấu hình bean riêng
                         và gọi qua Spring DI
                                    |
                       Vận hành: quan sát byte,
                       migration và compatibility
~~~

Bốn quy tắc cần ghi nhớ:

1. **`RedisTemplate<K,V>` là hợp đồng kiểu trong Java**. Nó không bảo đảm Redis biết K/V là gì.
2. **Serializer là hợp đồng byte trên Redis**. Định dạng khi ghi và đọc phải tương thích, kể cả giữa các service và phiên bản ứng dụng.
3. **Key, value, hash key và hash value có serializer riêng**. Cần chọn có chủ đích cho từng cấu trúc dữ liệu.
4. **Đừng thay serializer mà bỏ qua dữ liệu hiện có**. Khi thay đổi byte key hoặc schema value, hãy thiết kế migration và quản lý namespace/TTL tương ứng.

Chọn kiểu tham số và serializer đúng ngay từ đầu giúp code Spring Data Redis dễ đọc, key dễ vận hành, dữ liệu có thể chia sẻ một cách kiểm soát và tránh nhiều lỗi khó phát hiện khi nâng cấp ứng dụng.

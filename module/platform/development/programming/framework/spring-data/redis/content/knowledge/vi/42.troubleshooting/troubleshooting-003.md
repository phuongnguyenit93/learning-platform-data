# Khóa có tiền tố nhị phân hoặc thông tin kiểu ngoài dự kiến trong Spring Data Redis

> **Module:** Spring Data Redis  
> **Chương:** Chẩn đoán  
> **Bài học:** Nhận diện Redis keys chứa byte nhị phân, các tiền tố như `AC ED 00 05`, trường `_class` hoặc thuộc tính `@class` không mong đợi; phân biệt serializer, keyspace, Redis data type và metadata do Spring Data Redis tạo ra; điều tra an toàn, cấu hình nhất quán và di chuyển dữ liệu không làm mất khóa.

## 1. Tình huống: Redis key nhìn “lạ” dù ứng dụng vẫn chạy

Một ứng dụng Spring Boot lưu dữ liệu bằng `RedisTemplate`:

```java
redisTemplate.opsForValue()
        .set("customer:101", customer);
```

Khi mở Redis CLI hoặc RedisInsight, lập trình viên kỳ vọng:

```text
customer:101
```

Nhưng công cụ hiển thị một key tương tự:

```text
\xac\xed\x00\x05t\x00\x0ccustomer:101
```

Đôi khi giá trị cũng mở đầu bằng:

```text
\xac\xed\x00\x05...
```

Hoặc một Redis Hash có thêm field:

```text
_class = com.example.customer.Customer
```

Hoặc JSON cache có thuộc tính:

```json
{
  "@class": "com.example.customer.Customer",
  "id": "101",
  "name": "An"
}
```

Ứng dụng có thể vẫn đọc được dữ liệu, nhưng Redis CLI khó thao tác, các công cụ khác không tìm được key, hoặc service mới gặp lỗi khi thay serializer.

Đây thường **không phải do Redis tự gắn tiền tố nhị phân hay tự sinh Java class name**. Nguyên nhân phổ biến nằm ở cơ chế **serialize key/value** hoặc **mapping metadata** của Spring Data Redis.

### 1.1. Ba hiện tượng thường bị nhầm là một

| Hiện tượng | Ví dụ | Tầng chịu trách nhiệm |
|---|---|---|
| **Key có bytes nhị phân** | `AC ED 00 05 ... customer:101` | Key serializer phía ứng dụng |
| **Value có bytes/metadata kiểu Java** | `AC ED ...` trong String value; JSON `@class` | Value serializer/JSON typing |
| **Redis Hash có `_class`** | Field `_class` trong `HGETALL` | Spring Data Redis mapping/type metadata |

Một hiện tượng khác cần tách riêng:

| Hiện tượng | Ví dụ | Tầng chịu trách nhiệm |
|---|---|---|
| **Sai Redis data type** | `WRONGTYPE` khi `GET` một Hash | Redis server data type và command |

Một key có bytes nhị phân **không có nghĩa Redis data type của nó cũng “nhị phân”**. Redis keys vốn là chuỗi bytes; Redis `TYPE` vẫn có thể trả `string`, `hash`, `list`, `set`, `zset` hoặc loại được Redis version hỗ trợ.

### 1.2. Mục tiêu chẩn đoán

Sau bài học, cần có khả năng:

1. Đọc đúng key bytes thay vì chỉ nhìn dạng hiển thị của CLI.
2. Nhận diện dấu hiệu Java/JDK serialization.
3. Phân biệt `RedisTemplate`, `StringRedisTemplate`, Spring Cache và Redis Repository.
4. Giải thích vì sao `GET customer:101` trả nil dù application đọc được dữ liệu.
5. Phân biệt `TYPE`, `OBJECT ENCODING`, `_class` và `@class`.
6. Kiểm tra serializer của key, value, hash key và hash value.
7. Chọn cách đọc dữ liệu cũ khi thay serializer.
8. Tránh xóa toàn Redis hoặc thay serializer đột ngột trong môi trường có nhiều ứng dụng.
9. Kiểm thử format bytes và keyspace để ngăn lỗi quay lại.

## 2. Redis lưu key và value dưới dạng bytes

Một khái niệm nền tảng:

> **Redis không biết `String`, `Customer`, `ProductDto` hay Java package. Redis nhận tên key dưới dạng bytes và lưu data structure tương ứng.**

Với Redis String:

```text
Key bytes   -> Redis String value bytes
```

Với Redis Hash:

```text
Key bytes   -> Hash
               field bytes -> field value bytes
               field bytes -> field value bytes
```

Spring Data Redis chuyển các đối tượng Java thành bytes thông qua `RedisSerializer`.

### 2.1. Key serializer

Key Java:

```java
String key = "customer:101";
```

Nếu dùng `StringRedisSerializer`, Redis key bytes thường là UTF-8:

```text
63 75 73 74 6f 6d 65 72 3a 31 30 31
 c  u  s  t  o  m  e  r  :  1  0  1
```

Nếu dùng `JdkSerializationRedisSerializer`, bytes sẽ có metadata của Java serialization stream:

```text
ac ed 00 05 74 00 0c 63 75 73 74 6f 6d 65 72 3a 31 30 31
```

Ở đây `customer:101` có 12 ký tự ASCII, nên payload mẫu có length `00 0c`. Dạng bytes chính xác thay đổi theo object type và serializer.

Hai keys **khác nhau hoàn toàn** đối với Redis:

```text
UTF-8 bytes of "customer:101"
JDK-serialized bytes of Java String "customer:101"
```

Chúng chỉ tình cờ biểu diễn cùng tên logic ở phía Java.

### 2.2. Value serializer

Với cùng key bytes, Redis String value có thể là:

```text
"An"                       -> UTF-8
{"id":"101","name":"An"}    -> JSON UTF-8
AC ED 00 05 ...            -> Java serialization
binary protocol bytes      -> custom/Protobuf/CBOR/MessagePack
```

Ứng dụng phải biết value serializer/codec phù hợp để giải mã. `GET` thành công ở mức Redis không có nghĩa Java object decode cũng thành công.

### 2.3. Hash key serializer và hash value serializer

`RedisTemplate` có các vị trí serializer khác nhau:

- `keySerializer`: Redis key chính.
- `valueSerializer`: value của Redis String.
- `hashKeySerializer`: field name trong Redis Hash.
- `hashValueSerializer`: field value của Redis Hash.
- `defaultSerializer`: serializer fallback khi các vị trí chưa được cấu hình rõ, tùy `RedisTemplate` setup.

Một template có key UTF-8 nhưng hash fields được JDK serialize sẽ tạo Redis Hash có **tên key chính dễ đọc nhưng field name khó đọc**.

Ví dụ:

```text
Key: customer:101                   (UTF-8)
Hash field bytes: AC ED ... "name" (JDK)
Hash value bytes: AC ED ... "An"   (JDK)
```

Nếu chỉ đổi `keySerializer`, các hash fields và values cũ vẫn có format cũ.

## 3. Tiền tố AC ED 00 05 là gì?

Trong Java Object Serialization Stream Protocol, byte sequence:

```text
AC ED 00 05
```

là một dấu hiệu điển hình của stream header. Khi serialization một Java String, tiếp sau có thể là:

```text
74 00 0c ...
```

Trong đó:

- `AC ED`: Java serialization stream magic.
- `00 05`: stream version.
- `74`: type code `TC_STRING` trong trường hợp String thông thường.
- `00 0c`: byte length của String UTF-8 theo dạng modified UTF-8 của protocol trong ví dụ ngắn.
- Phần sau: serialized String content.

**Không nên nhận diện serializer chỉ dựa vào bốn bytes mà bỏ qua bối cảnh.** Những bytes trùng ngẫu nhiên vẫn có thể xuất hiện trong format khác; để kết luận cần so sánh với serializer thực tế và kiểm chứng decode trong môi trường đáng tin.

### 3.1. Vì sao key có Java serialization header?

Một khả năng phổ biến:

```java
RedisTemplate<String, Object> redisTemplate = ...;
redisTemplate.opsForValue().set("customer:101", customer);
```

Nếu template sử dụng `JdkSerializationRedisSerializer` cho key do default serializer hoặc cấu hình không tường minh, tên key Java String cũng bị Java serialize.

Mặc định trong nhiều phiên bản/configuration, `RedisTemplate` sử dụng Java serialization khi không có serializer cụ thể được đặt. Nhưng **không nên đoán**; hãy đọc bean configuration của đúng ứng dụng.

### 3.2. Redis không tự sinh header

Redis server không thêm `AC ED 00 05` vào key. Driver/Spring đã gửi những bytes đó theo Redis protocol.

Một ứng dụng Java, script ETL hoặc client khác cũng có thể ghi binary keys; key không phải UTF-8 là điều Redis hỗ trợ.

### 3.3. Số byte của Java serialized String khác số ký tự

Không nên tự tính một key serialization bằng cách nối:

```text
AC ED 00 05 + Java String raw UTF-8
```

Vì Java serialization có type code, length, object references và quy tắc Modified UTF-8. Với tên chứa Unicode hoặc object khác String, format có thể phức tạp.

Khi cần thao tác legacy keys, hãy dùng **đúng serializer** hoặc raw bytes đã được client đọc ra, không đoán và ghép tay prefix.

## 4. Dấu hiệu thường gặp trong Redis CLI

### 4.1. Redis key có ký tự escape

CLI có thể hiển thị:

```text
"\xac\xed\x00\x05t\x00\x0ccustomer:101"
```

Đây là cách tool **biểu diễn bytes không in được**. Dấu ngoặc kép và chuỗi `\x..` là representation của tool, không nhất thiết là các ký tự nằm nguyên trong Redis key.

### 4.2. RedisInsight có thể hiển thị ký tự lỗi

Một công cụ UI cố giải mã key bằng UTF-8 có thể hiển thị:

```text
��...customer:101
```

hoặc một chuỗi ký tự không đọc được. Đó không đủ để kết luận dữ liệu hỏng; nó có thể chỉ là **binary key không hợp với text viewer**.

### 4.3. GET theo tên logic trả nil

Chạy:

```bash
redis-cli GET customer:101
```

Redis trả nil, nhưng application lại đọc được dữ liệu.

Các khả năng:

- Key thực là Java-serialized bytes chứ không phải UTF-8.
- Spring Cache thêm prefix như `products::customer:101`.
- Repository dùng keyspace như `customers:101`.
- Application kết nối Redis database/cluster/endpoint khác CLI.
- Key đã hết TTL hoặc dữ liệu đang được tạo lại.
- Tenant/environment prefix khác.
- Java client dùng serializer khác với CLI.

Không lấy một `GET` nil làm bằng chứng key không tồn tại trong toàn Redis.

### 4.4. GET bị WRONGTYPE

CLI trả:

```text
WRONGTYPE Operation against a key holding the wrong kind of value
```

Khi đó key đã tồn tại và **Redis data type không phải String**. Có thể nó là Hash do Spring Data Redis Repository ghi. Hãy dùng `TYPE` trước khi quyết định dùng `GET`, `HGETALL` hay `LRANGE`.

## 5. Phân biệt Redis TYPE, OBJECT ENCODING và Java type metadata

Ba khái niệm khác nhau:

### 5.1. TYPE — Redis data structure

```bash
redis-cli TYPE customer:101
```

Có thể trả:

```text
string
hash
list
set
zset
stream
none
```

Các loại có thể thay đổi theo Redis version/extensions.

`TYPE` xác định **Redis data type** của key đúng bytes được truyền vào. Nó không giải thích Java class hay JSON format.

### 5.2. OBJECT ENCODING — representation nội bộ Redis

```bash
redis-cli OBJECT ENCODING customer:101
```

Kết quả có thể thuộc các internal encodings như `raw`, `embstr`, `listpack`, `hashtable`, `quicklist`, `skiplist`, tùy Redis version, data type và cấu trúc.

Điều này **không** tương đương:

```text
StringRedisSerializer
JdkSerializationRedisSerializer
Jackson JSON serializer
```

Ví dụ Redis String chứa JSON có thể có internal encoding `raw`; Redis String chứa JDK bytes cũng có thể có `raw`. `OBJECT ENCODING` không quyết định value codec của Spring.

### 5.3. `_class` hoặc `@class` — application type metadata

Ví dụ:

```text
Redis Hash field: _class = com.example.Customer
```

hoặc JSON:

```json
{"@class":"com.example.Customer","id":"101"}
```

Đó là metadata **do application mapping/serializer đặt vào Redis value**, không phải kết quả của `TYPE`.

### 5.4. Bảng ghi nhớ

| Thành phần quan sát | Câu hỏi được trả lời | Không trả lời được |
|---|---|---|
| Redis `TYPE` | Key chứa String/Hash/List...? | Java class nào đã serialize |
| Redis `OBJECT ENCODING` | Redis dùng internal layout gì? | Jackson hay JDK serializer |
| Java bytes `AC ED...` | Có dấu hiệu Java serialization? | Redis data type nếu chưa gọi TYPE |
| Hash field `_class` | Mapper lưu loại Java nào? | Redis có thực sự bảo vệ quyền truy cập không |
| JSON `@class` | Serializer ghi type metadata nào? | Redis key serializer là gì |
| Key prefix `cache::` | App/cache namespace nào? | Value format có tương thích không |

## 6. `_class` trong Redis Hash từ đâu ra?

Spring Data Redis Repository có thể map Java entity thành Redis Hash. Ví dụ:

```java
@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    private String name;
}
```

Với một repository, dữ liệu có thể giống:

```text
Key: customers:101
Redis type: hash

Fields:
  _class = com.example.customer.Customer
  id     = 101
  name   = An
```

`_class` thường là type hint do mapping converter ghi để hỗ trợ tái dựng object, đặc biệt với polymorphic/nested structures tùy cấu hình.

### 6.1. `_class` không phải Redis server metadata

Redis không có khái niệm class Java. `_class` chỉ là **một hash field bình thường** ở mức Redis. Redis không tự thêm field này.

Nếu đọc bằng:

```bash
redis-cli HGETALL customers:101
```

bạn có thể nhìn thấy `_class` như một field riêng.

### 6.2. Vì sao cần type hint?

Khi Redis Repository đọc Hash và dựng Java object, type hint có thể hỗ trợ:

- Chọn concrete Java type.
- Phân biệt các subtype trong một hierarchy.
- Khôi phục nested object/polymorphism theo mapping configuration.
- Tương tác với Spring Data mapping metadata.

Nó không phải cơ chế authorization và không tự bảo vệ dữ liệu.

### 6.3. Refactor package/class có thể làm dữ liệu cũ không đọc được

Nếu metadata chứa:

```text
com.oldpkg.Customer
```

nhưng class đã đổi thành:

```text
com.newpkg.Customer
```

mapping layer có thể gặp lỗi hoặc không khôi phục được type như trước, tùy cách type aliases/type mapper được dùng.

Vì vậy repository keyspace/type metadata là **một phần của data contract** và cần tính khi migration.

### 6.4. @TypeAlias và schema độc lập class name

Spring Data mapping có hỗ trợ các cơ chế type alias trong một số trường hợp, ví dụ:

```java
@TypeAlias("customer")
@RedisHash("customers")
public class Customer {
    @Id
    private String id;
}
```

Alias có thể giúp giảm lệ thuộc vào fully qualified Java class name khi mapping configuration nhận diện đúng type. Nhưng:

- Không tự sửa metadata đã ghi từ trước.
- Không đảm bảo mọi class/nested subtype đều được biết tới mapping context.
- Không phải field `_class` biến mất.
- Cần kiểm thử với Spring Data Redis version đang dùng.

Nếu muốn bỏ type metadata, cần thiết kế custom mapping/serializer phù hợp và xác định hậu quả đối với polymorphic reads; không nên chỉ `HDEL _class` trên production.

## 7. `@class` trong JSON từ đâu ra?

Một số JSON serializers có thể thêm type information để giải mã object về loại Java ban đầu.

Ví dụ với generic/polymorphic JSON serialization:

```json
{
  "@class": "com.example.customer.Customer",
  "id": "101",
  "name": "An"
}
```

Điều này có thể xuất hiện khi dùng `GenericJackson2JsonRedisSerializer` hoặc Jackson polymorphic typing configuration tương ứng.

**Không khẳng định mọi JSON serializer đều thêm `@class`.** Cách ghi metadata phụ thuộc serializer, Jackson configuration, root type, default typing, metadata field name và version.

### 7.1. `Jackson2JsonRedisSerializer<T>` khác generic serializer

Với một serializer có kiểu mục tiêu cụ thể như:

```java
Jackson2JsonRedisSerializer<Customer> serializer = ...;
```

decoder đã biết `Customer` là type mục tiêu. Nó có thể không cần ghi fully qualified Java class name vào mỗi JSON value, tùy ObjectMapper/configuration.

Với generic serializer dùng để đọc nhiều loại object, type metadata có thể được bật để xác định loại object.

### 7.2. `@class` không phải field nghiệp vụ

Một service API có thể serialize DTO thành JSON **không có** `@class`, trong khi Redis cache JSON **có** `@class` do generic serializer. Vì vậy:

- Không lấy Redis cache JSON làm API contract một cách mặc định.
- Không coi `@class` là thông tin do Redis Server tự thêm.
- Không xóa field rồi giả định serializer cũ vẫn deserialize được.
- Không để client bên ngoài tự quyết định Java class name để Jackson instantiate.

### 7.3. Bảo mật polymorphic deserialization

Type metadata có thể dẫn tới rủi ro nếu decoder chấp nhận các Java classes không được kiểm soát từ bytes không tin cậy.

Nên:

- Dùng DTO schema cụ thể khi phù hợp.
- Giới hạn loại Java được deserialize.
- Tránh bật default typing rộng mà không có type validator/allowlist.
- Bảo vệ Redis bằng ACL, TLS, network segmentation.
- Không xem dữ liệu Redis là tuyệt đối đáng tin nếu nhiều writers/services có quyền ghi.
- Không phát tán raw serialized payload hoặc fully qualified internal class names qua public APIs.

## 8. RedisTemplate và StringRedisTemplate: khác biệt quan trọng

### 8.1. RedisTemplate

`RedisTemplate<K,V>` là template tổng quát. Trong nhiều cấu hình/phiên bản, nếu không đặt serializer riêng và default serialization được bật, nó sử dụng JDK serializer.

Ví dụ:

```java
RedisTemplate<String, Object> template = ...;

template.opsForValue().set("customer:101", customer);
```

Nếu key serializer vẫn là JDK, một Java String key có thể được mã hóa thành:

```text
AC ED 00 05 ...
```

Nếu value serializer là JDK, value cũng có binary header.

Không suy từ generic parameter `RedisTemplate<String,Object>` rằng key sẽ được lưu dưới dạng UTF-8. **Java generic type không quyết định wire format.**

### 8.2. StringRedisTemplate

`StringRedisTemplate` được thiết kế cho String keys/values và dùng String serialization.

```java
StringRedisTemplate template = ...;

template.opsForValue().set(
        "customer:101",
        "{\"id\":\"101\",\"name\":\"An\"}");
```

Key và String value thường dễ đọc trong Redis CLI.

Nhưng:

- Nếu key thực do service cũ ghi bằng JDK serializer, StringRedisTemplate sẽ tìm **key UTF-8 khác**.
- StringRedisTemplate không tự chuyển dữ liệu legacy.
- Nó không tự làm JSON đúng schema hoặc bảo đảm security.
- Những dữ liệu trong Hash/List/Set cần dùng operations phù hợp.

### 8.3. Spring Boot auto-configuration

Spring Boot thường auto-configure connection factory, RedisTemplate và StringRedisTemplate theo dependencies/properties/beans hiện có. Nhưng:

- Một bean custom `RedisTemplate` có thể đổi defaults.
- Một bean custom `RedisCacheManager` có thể không dùng serializer của RedisTemplate.
- Spring Data Redis/Boot version khác có thể khác cách cấu hình.
- `RedisRepository` mapping có serializer/mapping path riêng.
- `ReactiveRedisTemplate` có `RedisSerializationContext` riêng.

**Hãy xem bean thực sự được inject và serializer properties của bean đó.**

## 9. Cấu hình RedisTemplate tường minh để tránh key nhị phân bất ngờ

Một template Java 17+ dùng String keys/hash fields và JSON values:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisSerializationConfiguration {

    @Bean("jsonRedisTemplate")
    RedisTemplate<String, Object> jsonRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, Object> template =
                new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setHashKeySerializer(new StringRedisSerializer());

        template.setValueSerializer(
                new GenericJackson2JsonRedisSerializer());
        template.setHashValueSerializer(
                new GenericJackson2JsonRedisSerializer());

        template.afterPropertiesSet();
        return template;
    }
}
```

Đây là một **ví dụ cấu hình**. Serializer JSON generic vẫn có thể tạo type metadata; nếu không mong muốn `@class`, cân nhắc kiểu DTO/schema cụ thể, Jackson configuration phù hợp hoặc sử dụng `StringRedisTemplate` với JSON DTO encoding tường minh.

### 9.1. Cấu hình phải phù hợp dữ liệu đã tồn tại

Nếu legacy keys là JDK bytes, bean trên không đọc chúng bằng Java String keys. Chỉ đổi bean trong production mà không có migration có thể làm application tưởng cache rỗng.

### 9.2. `hashKeySerializer` thường bị quên

Một bean như:

```java
template.setKeySerializer(new StringRedisSerializer());
template.setValueSerializer(new GenericJackson2JsonRedisSerializer());
```

chưa chắc đủ. Hash field name/value có thể vẫn dùng default serializer. Đặt tất cả những serializers ứng dụng cần **một cách tường minh**.

### 9.3. StringRedisTemplate cho JSON DTO theo contract

Nếu không muốn generic `@class` metadata:

```java
public record CustomerCache(
        int schemaVersion,
        String customerId,
        String name) {
}
```

Có thể lưu JSON text:

```java
CustomerCache dto = new CustomerCache(1, "101", "An");

String json = objectMapper.writeValueAsString(dto);

stringRedisTemplate.opsForValue()
        .set("customer:v1:101", json);
```

Khi đọc:

```java
String json = stringRedisTemplate.opsForValue()
        .get("customer:v1:101");

if (json != null) {
    CustomerCache dto =
            objectMapper.readValue(json, CustomerCache.class);
}
```

`ObjectMapper` do Spring/application cung cấp; `writeValueAsString`/`readValue` có checked exceptions cần khai báo hoặc xử lý trong code production.

Lợi ích:

- Key bytes UTF-8.
- Payload JSON schema được kiểm soát.
- Schema version tường minh.
- Không phụ thuộc Java package name nếu DTO chỉ có fields nghiệp vụ.
- Dễ kiểm thử golden bytes và tương thích nhiều ngôn ngữ.

## 10. Redis Cache: vì sao tên key có prefix khác dự đoán?

Với Spring Cache:

```java
@Cacheable(cacheNames = "customers", key = "#id")
public CustomerDto findById(String id) {
    return repository.load(id);
}
```

`RedisCacheManager`/RedisCache có thể tạo key dạng:

```text
customers::101
```

Tên key có `customers::` là **cache prefix** do Spring Cache, không phải JDK binary prefix.

Nếu application cấu hình:

```java
RedisCacheConfiguration.defaultCacheConfig()
        .computePrefixWith(
                name -> "app:prod:v2:cache:" + name + "::");
```

key có thể thành:

```text
app:prod:v2:cache:customers::101
```

### 10.1. RedisCacheConfiguration có serializers riêng

Trong nhiều phiên bản Spring Data Redis, Redis Cache configuration mặc định dùng:

- String key serialization.
- JDK value serialization.
- Prefix dựa trên cache name.
- TTL mặc định tùy configuration, thường không giới hạn trừ khi app đặt.

Điều này **khác RedisTemplate bean**. Thay RedisTemplate value serializer không tự làm Cache Manager value serializer đổi theo.

### 10.2. Một key dễ đọc nhưng value nhị phân

Ví dụ:

```text
Key: customers::101
Value: AC ED 00 05 ...
```

Nên kiểm tra **RedisCacheConfiguration.serializeValuesWith(...)** hoặc cache-specific serializer, không sửa key serializer.

### 10.3. Một key có `::` không phải bị hỏng

Prefix là cách tránh collision giữa cache names. Không bỏ prefix bằng cách xóa toàn Redis trừ khi ứng dụng có kế hoạch migration rõ.

### 10.4. @Cacheable key và null/missing values

Một cache key có thể không trùng `id` như dự đoán vì:

- `@Cacheable(key=...)` dùng SpEL.
- Default `KeyGenerator` dùng object parameters.
- Cache prefix/version thay đổi.
- Custom key conversion.
- Tenant environment scope.
- Cache manager khác bean bạn đang nhìn.

Cần xem exact cache key expression và serialized final key bytes.

## 11. Redis Repository khác RedisTemplate và Spring Cache

Một Redis Repository:

```java
@RedisHash("customers")
public class CustomerEntity {

    @Id
    private String id;

    private String name;
}
```

khác với:

```java
redisTemplate.opsForValue().set("customers:101", entity);
```

Repository thường lưu entity theo Redis Hash mapping, trong khi `opsForValue()` lưu Redis String bytes.

### 11.1. Cùng tên logic nhưng Redis TYPE khác

Ví dụ:

```text
Repository:
  Key: customers:101
  TYPE: hash
  HGETALL => id, name, _class

RedisTemplate.opsForValue:
  Key: customers:101
  TYPE: string
  GET => serialized Java object or JSON bytes
```

Nếu hai code paths cùng ghi **cùng raw Redis key**, chúng có thể ghi đè data type hoặc gây `WRONGTYPE`. Cần thống nhất keyspace ownership.

### 11.2. Secondary indexes và metadata

Repository có thể sinh thêm keys cho:

- Secondary indexes.
- Keyspace metadata.
- TTL/expired object handling.
- Entity references theo mapping configuration.

Một Redis scan có thể thấy các keys “không do mình tự đặt” nhưng do Repository infrastructure sử dụng. Không xóa vội nếu chưa biết owner.

### 11.3. `_class` có thể xuất hiện trong Hash lồng nhau

Type hints có thể phục vụ nested/polymorphic mapping. Nếu chúng xuất hiện không mong đợi, kiểm tra `MappingRedisConverter` và entity mapping trước khi quyết định dữ liệu bị lộ/sai.

### 11.4. Đừng coi `_class` là authorization

Một value chứa:

```text
_class = com.example.AdminUser
```

không chứng minh caller có quyền admin. Authorization phải được thực hiện bằng Spring Security/business policy; type metadata là thông tin kỹ thuật của deserialization.

## 12. Chẩn đoán theo Redis CLI: TYPE trước, GET sau

Một quy trình an toàn đối với **key UTF-8 đã biết chính xác**:

```bash
redis-cli EXISTS customer:101
redis-cli TYPE customer:101
redis-cli PTTL customer:101
redis-cli MEMORY USAGE customer:101
redis-cli OBJECT ENCODING customer:101
```

Không phải Redis provider nào cũng cho phép mọi lệnh diagnostic. Hãy dùng quyền tối thiểu và môi trường phù hợp.

### 12.1. Nếu TYPE = string

Có thể đọc:

```bash
redis-cli GET customer:101
```

Nhưng binary value có thể làm terminal hiển thị escape hoặc control bytes. Không copy raw value vào logs/email/public ticket nếu chứa dữ liệu nhạy cảm.

### 12.2. Nếu TYPE = hash

Dùng:

```bash
redis-cli HGETALL customer:101
redis-cli HKEYS customer:101
redis-cli HGET customer:101 _class
```

Với Hash lớn, `HGETALL` có thể trả lượng dữ liệu lớn và làm Redis/client chịu tải. Ưu tiên `HSCAN` với cursor hoặc chọn fields đã biết trong production khi payload lớn.

### 12.3. Nếu TYPE = list/set/zset/stream

Dùng command tương ứng:

- List: `LRANGE` với dải giới hạn.
- Set: `SSCAN`.
- Sorted Set: `ZSCAN` hoặc `ZRANGE` với dải giới hạn.
- Stream: `XRANGE` với `COUNT` giới hạn.

Không dùng `GET` cho các structures này.

### 12.4. Nếu TYPE = none

Có thể:

- Key thực sự không tồn tại/đã hết hạn.
- CLI đang kết nối nhầm endpoint/database/cluster node.
- Key bytes được serialize nhị phân.
- App thêm prefix/cache name/tenant.
- Key bị evict/expired.
- App chỉ ghi khi một condition cụ thể thỏa.

Không kết luận “Redis mất dữ liệu” nếu chưa xác nhận key bytes và connection context.

## 13. SCAN, KEYS và thách thức binary keys

### 13.1. SCAN hoạt động trên bytes

Redis `SCAN` duyệt Redis keys; matching pattern áp dụng ở Redis trên tên key bytes. Nếu key thực có JDK header trước `customer:101`, pattern bắt đầu bằng:

```text
customer:*
```

có thể **không tìm thấy** key đó.

Ví dụ:

```bash
redis-cli --scan --pattern 'customer:*'
```

có thể tìm keys UTF-8 thông thường, nhưng không bắt JDK-serialized names có binary prefix.

### 13.2. Dùng SCAN toàn bộ một cách có giới hạn để xác định key bytes

```bash
redis-cli --scan
```

Dùng để quan sát trên môi trường nhỏ/test. Trên production keyspace lớn, scan cũng tạo tải và có thể có hàng triệu kết quả; không xuất toàn bộ vào terminal hoặc log.

CLI có thể escape hoặc in control bytes theo chế độ output. Kết quả in dạng text **không bảo đảm có thể copy/paste để tạo lại bytes chính xác**.

### 13.3. Không dùng KEYS * tùy tiện

```bash
redis-cli KEYS '*'
```

`KEYS` có thể gây công việc lớn và ảnh hưởng latency khi keyspace nhiều keys. Dùng `SCAN` hoặc công cụ quan sát có giới hạn trong production.

### 13.4. Một cạm bẫy với serialized wildcard

Nếu gọi:

```java
redisTemplate.keys("customer:*");
```

và `redisTemplate` dùng JDK key serializer, chuỗi pattern `"customer:*"` cũng có thể được serialize thành Java object bytes.

Wildcard `*` nằm **sau Java serialization header/length**, nên không có cùng ngữ nghĩa tìm key logical prefix như pattern UTF-8. Vì serialization encoding có length metadata, pattern bytes càng không giống một prefix của serialized `"customer:101"`.

Vì vậy **không dùng `RedisTemplate.keys("prefix*")` với JDK key serializer làm bằng chứng legacy keys không tồn tại**.

### 13.5. SCAN không snapshot

Ngay cả khi pattern đúng, Redis SCAN:

- Có thể trả một key nhiều lần.
- Không bảo đảm snapshot bất biến khi keys đang được thêm/xóa.
- COUNT chỉ là hint.
- Có thể cần quét các primary nodes khi Redis Cluster.
- Không phải công cụ để bảo đảm tuyệt đối tất cả dữ liệu đã migrate trong lúc còn writers.

Đối với chẩn đoán, ghi nhận một mẫu keys có kiểm soát. Đối với migration, thiết kế idempotent scanner và reconciliation.

## 14. Đọc raw key bytes bằng Spring Data Redis

Khi key không thể copy chính xác từ CLI, một cách đáng tin hơn là lấy raw `byte[]` từ `RedisConnection`.

### 14.1. Java 17+ utility minh họa

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

final class RedisByteDebug {

    static String hex(byte[] bytes) {
        return HexFormat.of().formatHex(bytes);
    }

    static String utf8IfValid(byte[] bytes) {
        try {
            return StandardCharsets.UTF_8
                    .newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException ex) {
            return "<non-UTF8>";
        }
    }

    private RedisByteDebug() {}
}
```

Dùng `HexFormat` của Java 17 để in hex thay vì thử hiển thị raw bytes bằng `%s`.

### 14.2. Scan raw bytes trong RedisTemplate callback

```java
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public class RedisKeyInspector {

    private final StringRedisTemplate template;

    public RedisKeyInspector(StringRedisTemplate template) {
        this.template = template;
    }

    public void inspectSample(int maxKeys) {
        template.execute((RedisCallback<Void>) connection -> {
            int inspected = 0;

            ScanOptions options = ScanOptions.scanOptions()
                    .count(200)
                    .build();

            try (Cursor<byte[]> cursor = connection.scan(options)) {
                while (cursor.hasNext() && inspected < maxKeys) {
                    byte[] rawKey = cursor.next();

                    String hex = RedisByteDebug.hex(rawKey);
                    String utf8 =
                            RedisByteDebug.utf8IfValid(rawKey);

                    System.out.println(
                            "keyHex=" + hex
                            + " utf8=" + utf8
                            + " redisType="
                            + connection.type(rawKey));

                    inspected++;
                }
            }

            return null;
        });
    }
}
```

Đây là công cụ **diagnostic tối giản**:

- `connection.scan(options)` trả raw keys từ connection API trong trường hợp được hỗ trợ.
- `connection.type(rawKey)` truyền đúng bytes key, không serialize lại Java String.
- `utf8IfValid` chỉ chấp nhận key UTF-8 hợp lệ.
- Giới hạn `maxKeys` để tránh dump hàng triệu keys.
- Không tự động đọc mọi values.
- Không sử dụng trên production mà chưa có quyền và redaction.
- Trên Redis Cluster, behavior của scan qua connection/API có thể theo node; kiểm tra từng primary hoặc cluster-aware tooling theo Spring Data Redis version.

**Quan trọng:** in hex của key có thể vẫn lộ identifier/PII nếu key chứa dữ liệu nhạy cảm. Không để scanner trở thành logging feature thường trực, và không đưa kết quả thô vào public ticket.

### 14.3. Vì sao không dùng new String(byte[]) để kiểm tra?

Mặc định:

```java
new String(rawKey, StandardCharsets.UTF_8)
```

có thể thay invalid byte sequences bằng ký tự replacement `�`. Điều này khiến binary key **nhìn có vẻ là String** nhưng mất bytes gốc. Nếu dùng giá trị đó để xóa hoặc sửa key, bạn có thể thao tác nhầm.

Muốn thao tác chính xác trên raw binary keys, giữ `byte[]` trong suốt quá trình và chuyển qua Redis low-level connection API.

## 15. Chẩn đoán value bytes an toàn

Nếu đã có **raw key bytes** và biết TYPE = string, có thể đọc raw value:

```java
byte[] rawValue = connection.stringCommands().get(rawKey);
```

Việc này trả bytes từ Redis String. Nó không chạy JDK deserialization hay Jackson.

Cần hạn chế:

- Không đọc values quá lớn không có kiểm soát.
- Không in raw value chứa PII/session/token.
- Không decode bằng class từ nguồn không tin cậy.
- Không dùng `GET` nếu `TYPE` không phải `string`.

### 15.1. Kiểm tra magic bytes

Với value mẫu trong môi trường test, xem vài bytes đầu:

```text
ac ed 00 05 ...  -> nghi JDK serialization
7b 22 ...        -> JSON object UTF-8 thường bắt đầu bằng {"...
5b ...           -> JSON array hoặc format khác
```

Một header không đủ chứng minh format; cần đối chiếu writer/serializer configuration và thử decode đúng schema trong test.

### 15.2. `DUMP` không phải Java serialization

Redis:

```bash
redis-cli DUMP customer:101
```

tạo một Redis-specific internal serialized representation để dùng với `RESTORE`. Nó **không chứng minh** value được lưu bằng `JdkSerializationRedisSerializer`. Không dùng DUMP bytes như JSON hoặc Java serialized DTO.

## 16. Sai serializer có thể tạo ba loại lỗi khác nhau

### 16.1. Không tìm thấy key

V1 ghi JDK key bytes, V2 dùng UTF-8 key:

```text
V1 SET JDK("customer:101") ...
V2 GET UTF8("customer:101")
=> nil
```

Dù Redis còn dữ liệu cũ, tên key bytes khác nhau.

### 16.2. Redis trả WRONGTYPE

Một service ghi Redis Hash:

```redis
HSET customer:101 name An
```

Service khác dùng:

```java
stringRedisTemplate.opsForValue().get("customer:101");
```

Redis trả WRONGTYPE vì raw key đang có kiểu `hash`, không phải `string`.

Đây là lỗi **Redis data structure mismatch**, không nhất thiết liên quan JDK/JSON serializer.

### 16.3. Redis GET thành công nhưng Java deserialization lỗi

V1 ghi JSON:

```json
{"id":"101","name":"An"}
```

V2 đọc bằng JDK serializer:

```text
GET raw bytes: OK
Java deserialize: failed
```

Có thể thấy `SerializationException`, `SerializationFailedException`, Jackson mapping exception hoặc exception được bọc tùy Spring Data Redis API.

Không coi mọi exception đọc cache là connection failure.

### 16.4. JSON parse được nhưng object không đúng type

Ví dụ generic JSON serializer return một `Map` thay vì `Customer`, sau đó code cast:

```java
Customer customer = (Customer) result;
```

có thể gây `ClassCastException`.

Cần kiểm tra target type, type metadata, JSON mapping và version mismatch; không phải Redis server lỗi.

## 17. Một bảng nhận diện triệu chứng nhanh

| Triệu chứng | Giả thuyết đầu tiên | Cách xác nhận |
|---|---|---|
| Key bắt đầu `AC ED 00 05` | JDK key serializer | Xem RedisTemplate key serializer/raw bytes |
| Key có ký tự `��` | Binary key/UI decode UTF-8 sai | Scan raw bytes và hex |
| `GET customer:101` nil nhưng Java get có value | Key bytes khác hoặc prefix khác | So actual key serializer, endpoint, prefix |
| Redis key `customers::101` | Spring Cache prefix | Kiểm tra CacheManager/cache name |
| Redis value bắt đầu `AC ED` | JDK value serialization | Xem value serializer và raw value bytes |
| Redis JSON có `@class` | Generic JSON polymorphic type metadata | Kiểm tra serializer/ObjectMapper |
| HGETALL có `_class` | Redis Repository/MappingRedisConverter | Kiểm tra @RedisHash và mapping |
| Redis `TYPE` = hash, GET lỗi | Data structure mismatch | HGETALL/HSCAN thay vì GET |
| Redis `TYPE` = string nhưng app parse fail | Value codec/schema mismatch | Raw bytes, serializer, DTO |
| Spring Data Repository finder không thấy entity | Keyspace/ID/index metadata khác | Kiểm tra entity keyspace/indexes |
| Chỉ app version mới không đọc được data | Serializer/key schema migration thiếu compatibility | So old/new writer/readers |
| Chỉ cluster node A thấy keys | Endpoint/slot routing/scanning | Kiểm tra Cluster topology |
| Một key biến mất sau TTL | Expiration/eviction | PTTL, INFO stats/memory |
| `OBJECT ENCODING=raw` | Redis internal string encoding | Không suy JSON/JDK từ encoding |

Không kết luận từ một triệu chứng duy nhất; dùng bằng chứng từ raw bytes, Redis type và cấu hình ứng dụng.

## 18. Những default dễ gây hiểu nhầm trong Spring Boot

### 18.1. RedisTemplate không đồng nghĩa StringRedisTemplate

Một template chung có thể serialize Java String key theo JDK format; StringRedisTemplate dùng String format. Vì thế hai bean cùng gọi `get("customer:101")` có thể đọc **hai Redis keys khác nhau**.

### 18.2. RedisCacheManager không mặc định theo custom RedisTemplate

Nếu bạn cấu hình:

```java
@Bean
RedisTemplate<String, Object> redisTemplate(...) {
    // custom serializers
}
```

Spring Cache có thể vẫn dùng `RedisCacheManager` với `RedisCacheConfiguration` riêng. Do đó key hoặc value format từ `@Cacheable` có thể không giống thao tác qua RedisTemplate.

### 18.3. Repository dùng mapping conversion

Một Repository `@RedisHash` không giống `opsForValue().set(entity)`; nó có thể ghi Redis Hash với `_class` và secondary index keys. Thay value serializer không nhất thiết thay Repository mapping metadata.

### 18.4. ReactiveRedisTemplate dùng RedisSerializationContext

Với reactive operations:

```java
ReactiveRedisTemplate<K, V>
```

codec/serializer được cấu hình qua `RedisSerializationContext` tương ứng, không nên đoán nó lấy serializers từ imperative RedisTemplate.

### 18.5. Spring Boot properties thay đổi theo version

Các Redis connection settings như `spring.data.redis.*` trong Spring Boot 3 và `spring.redis.*` trong một số version cũ có thể khác. Điều này liên quan endpoint/connection nhưng **không tự quyết định key/value serializer** của custom beans.

Khi điều tra, xác minh exact application/Boot/Spring Data Redis/driver versions và beans thực tế.

## 19. Khi nào key binary là hợp lệ?

Binary keys không tự là bug. Redis cho phép arbitrary binary-safe key bytes (ngoài các giới hạn độ dài/cấu trúc theo Redis protocol/version).

Một hệ thống có thể cố ý dùng:

- Hash digest bytes.
- Compact binary composite identifiers.
- Custom binary key protocol.
- Non-UTF8 identifiers do client đặc biệt.
- JDK-serialized keys từ legacy application.

Tuy nhiên binary keys có nhược điểm vận hành:

- Redis CLI khó đọc.
- Pattern-based diagnostic/cleanup dễ sai.
- Dễ nhầm key logic và key bytes.
- Khó chia sẻ giữa clients đa ngôn ngữ.
- Cluster hash tag/slot placement có thể khó quan sát.
- Migration serializer dễ tạo duplicate logical keys.
- ACL key patterns cần tính theo raw bytes.

Nếu dự án muốn đặt key dạng text, dùng `StringRedisSerializer` tường minh. Nhưng **không chuyển ngay** khi dữ liệu legacy còn đang được đọc/ghi.

## 20. Redis Cluster: bytes và hash slots

Redis Cluster tính slot dựa trên raw key bytes, với hỗ trợ hash tags `{...}` khi có cặp dấu ngoặc hợp lệ.

Ví dụ:

```text
shop:{tenant-17}:order:101
shop:{tenant-17}:order:102
```

hai keys có cùng hash tag được đưa vào cùng hash slot.

### 20.1. Key serializer ảnh hưởng placement

Nếu serializer đổi raw key bytes, slot có thể thay đổi. Nếu binary serializer vẫn chứa `{tenant-17}` như một dải raw bytes, hash tag mechanism có thể vẫn có hiệu lực, nhưng không nên giả định điều đó từ Java String logic mà không kiểm tra **actual serialized bytes**.

### 20.2. Không đặt tất cả keys cùng global tag

```text
app:{all}:tenant:A:...
app:{all}:tenant:B:...
```

làm keys dồn vào một slot, dễ tạo hot shard. Hash tag nên theo phạm vi atomic multi-key operation cần thiết.

### 20.3. CROSSSLOT không phải sai serializer đơn thuần

Nếu multi-key command gửi các raw keys khác slots, Redis Cluster có thể trả `CROSSSLOT`. Đổi serializer có thể thay slot; cần dùng `CLUSTER KEYSLOT` trên đúng raw keys trong công cụ hỗ trợ hoặc kiểm tra key/tag layout ở mức bytes.

### 20.4. Scan toàn Cluster

Một `SCAN` kết nối tới một primary node thường chỉ thấy keys do node đó quản lý. Tùy Spring Data Redis/driver API, thao tác scan có thể không tự bao phủ mọi primary.

Khi dùng Redis Cluster, hãy xác định node ownership và dùng cluster-aware key enumeration theo API/version, không kết luận “keys đã biến mất” chỉ vì một node không trả kết quả.

## 21. ACL key patterns, binary keys và bảo mật

Redis ACL có thể giới hạn key access theo patterns. Nếu ứng dụng kỳ vọng:

```text
app:prod:customers:*
```

nhưng key serializer thực ghi JDK bytes với binary prefix, pattern đó có thể **không match** actual key bytes.

Kết quả có thể là:

- `NOPERM` dù code tưởng key đúng prefix.
- Service account phải được cấp pattern rộng hơn dự kiến.
- Một deployment vô tình dùng admin credentials để tránh lỗi.
- Quyền truy cập lệch với keyspace mới/cũ khi migration.

**Không giải quyết bằng cách mở `+@all` hoặc `~*` vô điều kiện.** Xác định actual serialized bytes và keyspace, rồi thiết kế ACL theo least privilege.

### 21.1. Redis key names có thể chứa dữ liệu nhạy cảm

Key names đôi khi chứa:

- User identifiers.
- Emails.
- Session tokens.
- Tenant IDs.
- API keys.
- Resource IDs.

Dù key được serialize nhị phân hoặc hiển thị escape, dữ liệu vẫn có thể lộ qua logs, dump, monitoring hoặc raw key scan.

### 21.2. JDK deserialization không được dùng trên dữ liệu không tin cậy

Nếu bạn tìm thấy `AC ED` và muốn “thử deserialize”:

- Chỉ làm với dữ liệu có nguồn gốc đáng tin và trong môi trường kiểm soát.
- Không cho caller chọn class hoặc serializer tùy ý.
- Không chạy generic `ObjectInputStream` trên raw unknown bytes từ Redis dùng chung/untrusted producers.
- Cân nhắc JDK deserialization filters/allowlists và kế hoạch migrate khỏi JDK format nếu có thể.
- Tránh in toàn bộ object/payload trong logs.

Java deserialization là một điểm nhạy cảm bảo mật; việc đọc để debug phải tuân thủ trust boundary.

## 22. Chuyển từ binary key sang UTF-8 key: không phải chỉ đổi một bean

Giả sử legacy:

```text
Legacy key bytes:
  JDK("customer:101")

New key bytes:
  UTF8("app:prod:customers:v2:101")
```

Nếu chỉ deploy new key serializer:

```text
Old data vẫn ở legacy key
New app không tìm được
Old app vẫn có thể ghi lại legacy key
```

Với cache có thể tái tạo, có thể chọn namespace mới và warm lại từ nguồn chuẩn. Với Redis là nguồn dữ liệu duy nhất, phải có migration đúng bytes, consistency và rollback.

### 22.1. Hai cách migration phổ biến

| Chiến lược | Khi phù hợp | Rủi ro |
|---|---|---|
| **Namespace mới và rebuild** | Cache có DB/source | Cache cold, DB stampede |
| **Đọc legacy và ghi new** | Muốn giữ dữ liệu cũ | Decode trusted bytes, concurrent writes, TTL |
| **Dual-reader/bridge** | Nhiều versions cùng chạy | Cần compatibility contract |
| **Background backfill** | Số keys lớn, deadline migration | SCAN không snapshot, memory overhead |
| **In-place replace** | Có reader-first rollout kiểm soát | Old app có thể không đọc được |
| **Resource migration** | Chuyển Redis instance/cluster | Cutover/replication/ownership |

### 22.2. Expand → migrate → contract

Một trình tự an toàn:

1. **Inventory:** xác định old key/value serializers, prefixes, TTL, writers/readers.
2. **Expand:** deploy code đọc được cả old/new formats (nếu cần).
3. **Đặt versioned namespace:** không bắt old readers đọc bytes mới.
4. **Migrate:** rebuild từ source hoặc decode legacy → validate → encode new.
5. **Coexistence:** xử lý invalidation/read/write giữa old/new versions.
6. **Monitor:** legacy reads, conversion failures, Redis memory, eviction, cache hit ratio.
7. **Rollback window:** giữ khả năng quay về phiên bản có dữ liệu tương thích.
8. **Contract:** ngừng legacy writer/reader sau khi đã chắc chắn.
9. **Cleanup:** xóa old keys có scope và rate limit.

### 22.3. Khi nhiều versions cùng chạy

Nếu V1 ghi JDK format vào một key còn V2 ghi JSON vào **cùng key bytes**, các requests xen kẽ sẽ làm format thay đổi qua lại. V1/V2 có thể deserialize fail không ổn định.

Cách tránh: triển khai reader-first hoặc dùng versioned keyspace tách biệt. Với dữ liệu có cập nhật nghiệp vụ, cần **cross-version invalidation** để V2 không trả cache stale khi V1 chỉ xóa key V1.

### 22.4. TTL không được bỏ qua

Khi copy từ old sang new:

- Lấy remaining TTL của old key.
- Tránh tự tạo TTL mới quá dài khiến cache stale.
- Nếu `PTTL = -1`, phải xác định policy có cho phép không TTL không.
- Nếu `PTTL = -2`, key đã mất, cần bỏ qua/re-read.
- GET và PTTL riêng có race nếu old key bị sửa giữa hai calls.
- Với dữ liệu canonical, cần version check/CAS hoặc migration window phù hợp.

Không giả định `RENAME` hay `DUMP/RESTORE` sẽ đổi Java serialization thành JSON; Redis commands không hiểu schema Java.

## 23. Không xóa dữ liệu chỉ vì trông không đọc được

Một phản ứng nguy hiểm:

```bash
redis-cli FLUSHALL
```

hoặc:

```bash
redis-cli KEYS '*' | xargs redis-cli DEL
```

Không thực hiện trên shared Redis/production để “dọn key lạ”.

Rủi ro:

- Xóa sessions, locks, counters, streams, cache của services khác.
- Làm mất idempotency state gây side effects trùng.
- Mất dữ liệu canonical không thể tái tạo.
- Dẫn tới DB stampede khi cache cold.
- Làm downtime hoặc ảnh hưởng tenants khác.

Cần xác định key owner, raw bytes, Redis TYPE, TTL, serializer và dữ liệu là cache hay canonical trước khi thay đổi.

### 23.1. Xóa đúng raw key

Nếu đã xác định binary key cần xóa, dùng exact raw bytes trong low-level Redis connection API được kiểm soát hoặc một migration script biết serializer cũ.

Không thử tự dựng Java serialization prefix và gõ escape text trong CLI rồi xóa — rủi ro tạo sai bytes cao.

### 23.2. Không dùng String key đã bị decode lỗi

Nếu raw key có invalid UTF-8, việc decode thành String thay `�` rồi encode lại không tạo cùng key. Bảo toàn `byte[]`.

### 23.3. Cẩn trọng với Repository metadata/indexes

Một key “lạ” có thể là secondary index, Redis Hash hoặc keyspace metadata do Spring Data Repository tạo. Xóa riêng metadata có thể làm repository queries thiếu dữ liệu. Cần xem model và namespace owner.

## 24. Đọc Redis Hash chứa `_class`: xử lý đúng

Một sample:

```bash
redis-cli TYPE customers:101
# hash

redis-cli HGETALL customers:101
# id -> 101
# name -> An
# _class -> com.example.customer.Customer
```

Nếu app dùng Repository mapper, việc `_class` xuất hiện có thể là bình thường.

### 24.1. Nếu không muốn lưu Java class name

Các lựa chọn phụ thuộc thiết kế:

- Dùng DTO + JSON schema cố định qua `StringRedisTemplate`.
- Dùng alias/type mapper phù hợp trong Spring Data mapping.
- Cấu hình converter/mapping strategy có kiểm soát nếu framework version hỗ trợ.
- Dùng custom representation và không dựa vào automatic polymorphic reconstruction.

**Không xóa `_class` khỏi tất cả Hash ngay**: reader đang chạy có thể cần nó để phân biệt subtype.

### 24.2. Nếu `_class` khác package hiện tại

Cần hỏi:

- Dữ liệu được ghi bởi application version nào?
- Class đã được rename/move package?
- Có alias compatibility?
- Reader version có mapping context chứa old/new classes?
- Có migration DTO tương ứng?
- Dữ liệu là cache hay canonical?
- Có nhiều services cùng ghi một Hash keyspace không?

Nếu không chắc, sao chép một fixture **được phép và đã ẩn dữ liệu nhạy cảm** vào test environment, rồi kiểm thử conversion thay vì sửa production ngay.

## 25. JSON có `@class`: xử lý đúng

Với value:

```json
{
  "@class": "com.example.customer.Customer",
  "id": "101",
  "name": "An"
}
```

Nên xác định:

- Writer đang dùng `GenericJackson2JsonRedisSerializer`?
- Có custom `ObjectMapper.activateDefaultTyping(...)` hoặc annotation `@JsonTypeInfo`?
- Type metadata field name thực sự là gì?
- Có nested object metadata?
- Bản mới có class đó không?
- DTO/schema version hiện tại có compatible không?
- Có allowlist/trust restrictions không?

### 25.1. Không coi @class là chỉ dấu Redis data type

Redis TYPE có thể trả `string` cho JSON text, bất kể JSON có `@class` hay không. Đây là metadata của JSON serializer, không phải Redis internal type.

### 25.2. Không tự xóa @class khỏi cached JSON

Nếu serializer cũ cần type metadata để khôi phục `Object`, việc xóa field có thể làm deserialization fail hoặc trả `Map` thay cho DTO.

Nếu muốn bỏ metadata, hãy migrate bằng reader hiểu old format và writer mới dùng typed DTO schema, với versioned keyspace/cutover tương thích.

### 25.3. Dữ liệu từ nhiều ngôn ngữ

Python/Node/Go clients thường không cần fully qualified Java class name. Nếu Redis được chia sẻ cross-language, nên dùng JSON schema/Protobuf/Avro contract ổn định thay vì JDK serialization hoặc Java-specific polymorphic metadata.

## 26. Đọc sai Redis key do nhầm endpoint, DB hoặc tenant

Không phải tất cả trường hợp key “lạ” là serializer issue.

### 26.1. Redis endpoint và logical database

Có thể:

```text
Spring Boot -> redis-prod:6379, DB 1
redis-cli   -> redis-dev:6379, DB 0
```

thì CLI không thấy key application vừa ghi.

Kiểm tra connection configuration từ app deployment và CLI session, không dựa vào các default.

Redis Cluster chỉ hỗ trợ database 0. Đừng dùng `SELECT 1` làm cách cô lập tenant trong Cluster.

### 26.2. Environment prefix

Ứng dụng có thể đặt:

```text
app:prod:customer:101
```

nhưng CLI đang tìm:

```text
customer:101
```

### 26.3. Tenant prefix

Multi-tenant cache:

```text
app:prod:customers:tenant:t-17:id:101
```

Cần verified tenant context, không suy tenant từ key substring hay user-supplied header chưa xác thực.

### 26.4. TTL/eviction

Một key vừa xuất hiện có thể hết hạn:

```bash
redis-cli PTTL app:prod:customer:101
redis-cli INFO stats
redis-cli INFO memory
```

`PTTL=-2` biểu thị key không tồn tại ở thời điểm kiểm tra; `PTTL=-1` biểu thị key tồn tại nhưng không có expiration. Redis eviction/memory pressure có thể làm key biến mất trước TTL.

Không kết luận serializer sai khi nguyên nhân là expiration hoặc wrong endpoint.

## 27. Kiểm thử ngăn sự cố key/value bytes

### 27.1. Test key serializer

Trong integration test với Redis thật hoặc Testcontainers:

1. Tạo một `RedisTemplate` theo configuration đang deploy.
2. Ghi key logical `"customer:101"`.
3. Dùng raw `RedisConnection.scan(...)` để lấy key bytes thực.
4. So sánh với UTF-8 bytes mong đợi.
5. Đảm bảo không xuất hiện JDK header nếu requirement là readable keys.
6. Đảm bảo data type đúng String/Hash.

Không chỉ assert Java `redisTemplate.opsForValue().get("customer:101")` thành công, vì cùng serializer sai có thể vẫn đọc lại được dữ liệu do chính nó ghi.

### 27.2. Test StringRedisTemplate và template khác

Nếu ứng dụng có nhiều Redis templates, test rằng chúng tạo cùng raw key bytes **khi được thiết kế để chia sẻ keyspace**, hoặc test chúng dùng namespace khác khi format không tương thích.

### 27.3. Test Spring Cache

Với `@Cacheable`:

- Cache name và prefix đúng.
- Key expression có tenant/environment/version.
- Cache value serializer đúng.
- Cache hit không gây `ClassCastException`.
- Old/new serializers không ghi vào cùng namespace nếu không compatible.
- `@CacheEvict` xóa đúng key đã được tạo.
- Cache miss khác lỗi deserialize.

### 27.4. Test Redis Repository

Với `@RedisHash`:

- `TYPE` là Hash như dự kiến.
- Entity id và keyspace đúng.
- `_class` metadata được hiểu đúng hoặc alias tương thích.
- Secondary index queries hoạt động.
- TTL và expiration handling đúng.
- Những ứng dụng khác không dùng cùng key dưới dạng String.

### 27.5. Test migration và rollback

- Old version ghi key/value.
- New version đọc được hoặc chủ động tách namespace.
- New version không ghi format làm old reader bị crash.
- TTL được bảo toàn/giới hạn.
- Concurrent reads/writes không tạo stale vượt policy.
- Rollback target vẫn đọc dữ liệu đang có.
- Key cleanup không xóa metadata của service/tenant khác.

### 27.6. Test dữ liệu không tin cậy

Không lấy arbitrary binary value rồi thử deserialize JDK trong production. Dùng fixtures đã biết nguồn, kiểm tra type/format validators và parser giới hạn classes.

## 28. Một runbook chẩn đoán cho production incident

### Bước 1 — Xác định triệu chứng

Ví dụ:

```text
Symptom:
  RedisInsight shows "\xac\xed..."
  redis-cli GET customer:101 -> nil
  Spring service can read Customer
```

Chưa sửa config.

### Bước 2 — Kiểm tra kết nối

- Redis endpoint/port.
- Standalone vs Cluster.
- Logical DB index nếu có.
- User/ACL.
- TLS.
- Environment/tenant prefixes.

### Bước 3 — Xác định raw key bytes

Dùng một raw SCAN sample với limit hoặc tooling có binary-safe key enumeration. In hex có redaction trong môi trường được phép.

### Bước 4 — Xác định Redis TYPE và TTL

Gửi **exact raw key bytes** đến `TYPE`/`PTTL`. Nếu key `hash`, không gọi GET.

### Bước 5 — Nhận diện serializer

Kiểm tra:

- `RedisTemplate.getKeySerializer()`.
- `RedisTemplate.getValueSerializer()`.
- `getHashKeySerializer()`.
- `getHashValueSerializer()`.
- `RedisCacheConfiguration` cho Spring Cache.
- Repository mapping converter/type mapper.
- Reactive serialization context nếu có.
- Writer version cũ và new version.

Có thể inspect bean configuration, nhưng không tự khởi tạo một serializer mới chỉ để thử trên production data không tin cậy.

### Bước 6 — Phân biệt metadata

- `AC ED`: dấu hiệu JDK serialization bytes.
- `_class` trong Redis Hash: mapping type hint.
- `@class` trong JSON: polymorphic JSON type metadata.
- `TYPE hash`: Redis data type, không phải Java class.
- `OBJECT ENCODING`: Redis internal representation.

### Bước 7 — Phân loại dữ liệu

- Cache có nguồn chuẩn?
- Sessions?
- Idempotency state?
- Distributed locks?
- Counter/quota?
- Stream work queue?
- Repository canonical state?

Không dùng “xóa cache rồi rebuild” cho mọi loại dữ liệu.

### Bước 8 — Chọn hướng xử lý

- Chỉ cần giải thích key: cập nhật dashboard/tooling/docs.
- Cần key UTF-8 cho data mới: cấu hình explicit String key serializer và namespace v2.
- Cần đọc legacy binary keys: dùng legacy serializer/low-level raw access với bảo vệ.
- Không muốn `@class`: dùng typed DTO/new JSON serializer và compatible migration.
- Không muốn `_class`: xem mapping strategy/type alias và convert data có kế hoạch.
- WRONGTYPE: sửa key ownership/operation, không chỉ serializer.

### Bước 9 — Quan sát sau thay đổi

- Cache hit/miss/error.
- Deserialization exceptions.
- Memory/eviction.
- Legacy/new key counts.
- Spring Cache/Repository queries.
- TTL/correctness.
- Security/ACL.
- Rollback behavior.

## 29. Những sai lầm phổ biến

### 29.1. “Key có ký tự lạ nghĩa là Redis bị hỏng”

Không nhất thiết. Redis hỗ trợ binary keys; Java serializer có thể tạo bytes không thể in.

### 29.2. “Chỉ String key trong Java thì Redis chắc chắn lưu UTF-8”

Sai. `RedisTemplate<String,V>` vẫn có thể dùng JDK key serializer. Java generic type không quyết định bytes.

### 29.3. “Đổi sang StringRedisTemplate là đọc được key cũ”

Không nếu key cũ dùng JDK bytes. StringRedisTemplate tìm UTF-8 key khác.

### 29.4. “Thấy AC ED thì dữ liệu là Redis Hash”

Sai. AC ED là dấu hiệu Java serialization trong bytes; Redis data type phải kiểm tra bằng `TYPE`.

### 29.5. “Redis TYPE trả string nghĩa JSON”

Sai. Redis String chứa bất kỳ bytes nào, có thể là UTF-8 text, JSON hoặc JDK serialized object.

### 29.6. “OBJECT ENCODING=raw nghĩa value serializer raw”

Sai. Đây là internal encoding của Redis, không phải Spring serializer.

### 29.7. “_class do Redis server tự thêm”

Sai. Spring Data Redis mapping có thể ghi type hint vào Redis Hash.

### 29.8. “@class là field của DTO nên nên bỏ”

Không chắc. Nó có thể là metadata mà generic JSON serializer cần. Bỏ đi có thể phá deserialization.

### 29.9. “RedisCacheManager tự dùng serializer của RedisTemplate”

Không nên giả định. RedisCacheConfiguration có settings riêng.

### 29.10. “GET trả nil thì key chắc chắn không tồn tại”

Không nếu bạn dùng logical UTF-8 name trong khi actual key bytes JDK-serialized, hoặc khác cache prefix/endpoint.

### 29.11. “KEYS customer:* không thấy nên không có khách hàng”

Sai nếu keys có binary prefix hoặc cache/repository namespace khác; cũng không nên dùng KEYS toàn keyspace production.

### 29.12. “SCAN luôn trả snapshot đầy đủ không lặp”

Sai. SCAN không snapshot khi dataset đang thay đổi và COUNT chỉ là hint.

### 29.13. “Có thể dùng Redis RENAME để đổi JDK sang JSON”

Sai. RENAME đổi key name và giữ value bytes; không chuyển application schema.

### 29.14. “Có thể xóa _class khỏi Hash mà repository vẫn chắc chắn chạy”

Không. Mapping có thể cần type hint, nhất là polymorphic types.

### 29.15. “Chỉ cần tắt serializer metadata là an toàn hơn”

Không nếu data cũ vẫn dùng metadata hoặc decoder cần nó; migration phải tương thích.

### 29.16. “Một lỗi WRONGTYPE do JDK binary prefix”

Không nhất thiết. WRONGTYPE là sai Redis data structure cho đúng raw key. Binary prefix là vấn đề key encoding khác.

### 29.17. “Chụp toàn bộ raw keys/values lên bug ticket là vô hại”

Không. Keys/values có thể chứa PII, tokens, sessions, internal class names và tenant IDs.

### 29.18. “Có thể dùng FLUSHALL để dọn keys khó đọc”

Không trên shared Redis/production. Có thể xóa sessions, locks, counters, streams hoặc data không thể khôi phục.

## 30. Câu hỏi thường gặp

**Câu 1. Vì sao key bắt đầu bằng `\xac\xed\x00\x05`?**

Đó là dấu hiệu điển hình của Java Object Serialization stream. Kiểm tra serializer đang mã hóa key, thường là `JdkSerializationRedisSerializer`.

**Câu 2. Redis tự thêm binary prefix vào key không?**

Không. Redis nhận bytes do client gửi. Prefix thường được tạo ở ứng dụng/serializer.

**Câu 3. Vì sao `StringRedisTemplate` không thấy key do `RedisTemplate` ghi?**

Hai templates có thể dùng key serializers khác nhau, tạo hai raw Redis keys khác nhau cho cùng Java String.

**Câu 4. Có phải RedisTemplate mặc định luôn là JDK serializer?**

Trong nhiều configurations/versions, RedisTemplate sử dụng JDK serialization khi không đặt serializer riêng. Nhưng cần kiểm tra bean được inject vì custom configuration có thể đổi behavior.

**Câu 5. Vì sao `@Cacheable` tạo key `products::101`?**

RedisCacheManager/RedisCache dùng cache-name prefix. Đây là namespace text bình thường, không phải binary prefix.

**Câu 6. Redis Cache mặc định serialize values thế nào?**

Trong nhiều Spring Data Redis configurations, mặc định là JDK value serializer, key thường String serializer. Nhưng xác minh `RedisCacheConfiguration` của đúng ứng dụng/version.

**Câu 7. `_class` trong Redis Hash nghĩa là gì?**

Type hint do Spring Data Redis mapping converter ghi để hỗ trợ khôi phục Java object. Nó là field của Hash, không phải Redis server metadata.

**Câu 8. `@class` trong JSON do đâu?**

Có thể là polymorphic type metadata do `GenericJackson2JsonRedisSerializer` hoặc Jackson configuration thêm. Không phải mọi JSON serializer đều dùng nó.

**Câu 9. `TYPE` và `OBJECT ENCODING` khác nhau gì?**

`TYPE` nói Redis key là String/Hash/List..., còn `OBJECT ENCODING` nói Redis dùng layout nội bộ gì. Cả hai không xác định Java serializer.

**Câu 10. GET bị WRONGTYPE có phải serializer sai không?**

Có thể nguyên nhân code/namespace ghi Redis Hash nhưng reader dùng GET String. Xác nhận bằng `TYPE` đúng raw key bytes.

**Câu 11. Làm sao liệt kê JDK-serialized keys?**

Dùng binary-safe raw key enumeration qua Redis connection/SCAN, in hex và kiểm soát giới hạn/PII. Prefix match `customer:*` có thể không tìm vì bytes bắt đầu bằng Java header.

**Câu 12. Có thể dùng `redis-cli --scan` không?**

Có thể quan sát, nhưng text output không đáng tin để reconstruct arbitrary binary key bytes. Dùng raw byte API cho thao tác chính xác.

**Câu 13. Có thể dùng `new String(keyBytes, UTF_8)` rồi xóa key không?**

Không an toàn nếu bytes không phải UTF-8; decoder có thể thay byte lỗi bằng `�`. Bảo toàn raw bytes khi thao tác key.

**Câu 14. Có thể xóa `_class` để tiết kiệm bộ nhớ không?**

Không tùy tiện. Mapper có thể cần nó; chi phí mất compatibility thường lớn hơn số bytes tiết kiệm.

**Câu 15. Nếu đổi Java package, dữ liệu `_class` cũ có đọc được không?**

Tùy mapping/alias/converter. Cần test migration, có thể dùng type aliases hoặc DTO conversion.

**Câu 16. Có nên dùng JDK serialization cho Redis value lâu dài không?**

Cần đánh giá rủi ro security và độ phụ thuộc Java classes. Với dữ liệu cần interoperability/stable schema, JSON DTO/Protobuf/format rõ thường dễ bảo trì hơn.

**Câu 17. Redis Cluster có ảnh hưởng binary key không?**

Có. Slot calculation dựa trên raw bytes/hash tags, và scan có thể theo node. Đổi serializer có thể đổi placement/behavior.

**Câu 18. Key bị binary prefix có nguy hiểm ngay không?**

Không tự nguy hiểm. Rủi ro chủ yếu là vận hành khó, nhầm serializer/migration, ACL patterns và việc deserialize untrusted bytes.

**Câu 19. Key không còn vì TTL hay vì serializer?**

So actual raw key, endpoint, `TYPE`, `PTTL`, `INFO stats`, keyspace/version prefixes trước khi kết luận.

**Câu 20. Có phải cứ đổi serializer và deploy là xong?**

Không nếu old data và old versions vẫn chạy. Cần expand–migrate–contract, versioned namespace hoặc bridge reader và rollback plan.

## 31. Checklist thực hành chẩn đoán

1. **Xác nhận endpoint/database/cluster** mà CLI và Spring đang dùng.
2. **Xác định raw key bytes** bằng công cụ binary-safe, không chỉ text viewer.
3. **Kiểm tra `TYPE` trước khi GET/HGETALL**.
4. **Kiểm tra `PTTL` và eviction** nếu key không còn.
5. **Nhận diện `AC ED 00 05`** như dấu hiệu JDK serialization, không suy chắc chỉ từ chuỗi hiển thị.
6. **Kiểm tra key/value/hash serializers** của đúng RedisTemplate bean.
7. **Kiểm tra RedisCacheConfiguration** riêng cho Spring Cache.
8. **Kiểm tra Redis Repository mapping** nếu thấy Hash `_class`.
9. **Kiểm tra Jackson polymorphic typing** nếu JSON có `@class`.
10. **Phân biệt Redis TYPE và OBJECT ENCODING** với serializer metadata.
11. **Kiểm tra cache prefix, @Cacheable key expression, tenant scope**.
12. **Không dùng pattern UTF-8 để kết luận thiếu binary keys**.
13. **Đối chiếu raw bytes giữa application versions**.
14. **Thử decode legacy chỉ trong trust boundary** và giữ cause nếu lỗi.
15. **Không đọc/xuất raw PII/session values** để debug tùy tiện.
16. **Không đổi serializer trên shared keyspace khi old readers còn chạy**.
17. **Có migration/rollback cho keyspace mới** khi cần.
18. **Tôn trọng Redis Cluster hash slots, ACL và node-local scans**.
19. **Không xóa dữ liệu do Repository/cache khác sở hữu**.
20. **Kiểm thử byte-level, cache hit/miss, WRONGTYPE và metadata fields**.
21. **Không dùng FLUSHALL/FLUSHDB** để xử lý key lạ trên production.
22. **Đo sau thay đổi:** hit ratio, decode errors, memory, legacy/new key counts.

## 32. Tổng kết

**Key Redis có tiền tố nhị phân hoặc thông tin kiểu ngoài dự kiến không nhất thiết là Redis bị lỗi.** Trong Spring Data Redis, chúng thường bắt nguồn từ các cơ chế serialization và mapping:

- **`AC ED 00 05` ở key/value:** dấu hiệu phổ biến của `JdkSerializationRedisSerializer`.
- **Key không tìm thấy bằng CLI text:** có thể do key bytes khác, Spring Cache prefix, repository keyspace, tenant/environment prefix hoặc endpoint khác.
- **`_class` trong Redis Hash:** type hint do Spring Data Redis mapping/repository ghi.
- **`@class` trong JSON:** type metadata do JSON serializer/Jackson polymorphic typing ghi.
- **`WRONGTYPE`:** Redis key có data structure khác operation đang gọi; xác nhận bằng `TYPE`.
- **`OBJECT ENCODING`:** representation nội bộ của Redis, không phải Jackson/JDK serializer.

Phương pháp xử lý đúng là **xác minh raw key bytes → kiểm tra Redis TYPE/TTL → xác định serializer/mapper thực → đánh giá keyspace owner → chọn cấu hình hoặc migration phù hợp**.

Khi muốn keys dễ đọc và tương thích giữa services, có thể dùng `StringRedisSerializer` cho keys, typed JSON DTO/schema rõ cho values và namespace có version. Nhưng không đổi serializer đột ngột nếu Redis chứa dữ liệu cũ hoặc nhiều phiên bản cùng chạy. Migration cần bảo toàn data correctness, tenant isolation, TTL và rollback.

## Tài liệu tham khảo

- Spring Data Redis — [RedisTemplate & Serialization](https://docs.spring.io/spring-data/redis/reference/redis/template.html): serializer và template operations.
- Spring Data Redis — [Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): cache prefix, key/value serialization.
- Spring Data Redis — [Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): mapping Redis Hash, indexes và type hints.
- Spring Data Redis — [Object Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html): mapping converter.
- Spring Data Redis — [Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html): hash slots và cluster operations.
- Spring Data Redis API — [JdkSerializationRedisSerializer](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/serializer/JdkSerializationRedisSerializer.html).
- Spring Data Redis API — [StringRedisSerializer](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/serializer/StringRedisSerializer.html).
- Spring Data Redis API — [GenericJackson2JsonRedisSerializer](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/serializer/GenericJackson2JsonRedisSerializer.html).
- Spring Framework — [Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): @Cacheable và key generation.
- Java — [Object Serialization Stream Protocol](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/protocol.html): AC ED, TC_STRING và stream format.
- Redis — [TYPE](https://redis.io/docs/latest/commands/type/): Redis data types.
- Redis — [OBJECT ENCODING](https://redis.io/docs/latest/commands/object-encoding/): Redis internal representation.
- Redis — [SCAN](https://redis.io/docs/latest/commands/scan/): cursor-based key iteration.
- Redis — [PTTL](https://redis.io/docs/latest/commands/pttl/): remaining TTL.
- Redis — [DUMP](https://redis.io/docs/latest/commands/dump/): Redis-specific value serialization.
- Redis — [Security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/): ACL, network và credentials.

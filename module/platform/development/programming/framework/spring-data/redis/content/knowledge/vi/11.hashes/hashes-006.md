# Phân biệt serializer của khóa Hash với serializer của giá trị Hash

Trong Spring Data Redis, khi gọi `redisTemplate.opsForHash().put("profile:42", "name", "Lan")`, chúng ta nhìn thấy ba giá trị Java: tên Redis key, tên trường (field) trong Hash và giá trị của trường. Redis không lưu trực tiếp đối tượng Java; các thành phần đó đều được chuyển thành **bytes**. Nếu một trong ba serializer không thống nhất giữa bên ghi và bên đọc, dữ liệu có thể trông như đã biến mất, không giải mã được hoặc không còn tương tác được với lệnh Redis.

Hai serializer trọng tâm của bài học:

- **`hashKeySerializer`**: chuyển **tên field** của Hash thành bytes và giải mã tên field khi đọc.
- **`hashValueSerializer`**: chuyển **nội dung field** của Hash thành bytes và giải mã nội dung field khi đọc.

Điểm dễ nhầm: Hash key ở đây là **field**, không phải Redis key ngoài cùng. Redis key ngoài cùng được xử lý bằng `keySerializer`.

Bài học đặt trong ngữ cảnh Spring Boot 3.3.x, Spring Data Redis 3.3.x và `RedisTemplate`/`StringRedisTemplate`. Các nguyên tắc định dạng bytes áp dụng rộng hơn, nhưng API và cấu hình mặc định cần được đối chiếu khi đổi phiên bản.

## 1. Redis Hash có những thành phần nào?

Trong Redis CLI:

~~~redis
HSET app:user:42 name "Lan" age "28" city "Da Nang"
HGET app:user:42 name
HGETALL app:user:42
~~~

Hình dung dữ liệu:

~~~text
Redis logical database
└── app:user:42            ← key ngoài cùng, Redis type = hash
    ├── name → Lan          ← hash key/field → hash value
    ├── age  → 28
    └── city → Da Nang
~~~

Ba vị trí độc lập:

| Vị trí | Ví dụ | Serializer Spring Data Redis |
|---|---|---|
| Redis key ngoài cùng | `app:user:42` | `keySerializer` |
| Hash key / field name | `name`, `age` | `hashKeySerializer` |
| Hash value / field value | `Lan`, `28` | `hashValueSerializer` |

Redis chỉ quan tâm bytes của key, field và value. Nó không hiểu tên field là Java `String`, một field có nghĩa “tuổi” hay một value là DTO. Nếu hai ứng dụng cùng trỏ tới Redis nhưng mã hóa field khác nhau, Redis xem chúng là hai field khác nhau.

### 1.1. Một lệnh HSET được encode thế nào?

~~~java
redisTemplate.opsForHash().put(
        "app:user:42",  // Redis key
        "name",         // Hash key: field name
        "Lan"           // Hash value: field content
);
~~~

Dòng code này tương đương về mặt ý tưởng:

~~~mermaid
flowchart TD
    A["HashOperations.put(key, field, value)"]
    A --> B["keySerializer → byte[]"]
    A --> C["hashKeySerializer → byte[]"]
    A --> D["hashValueSerializer → byte[]"]
    B --> E["Redis HSET"]
    C --> E
    D --> E
    E --> F["Hash field bytes → value bytes"]
~~~

Khi đọc `HGET`, Spring Data Redis dùng `keySerializer` và `hashKeySerializer` để xác định đúng key/field. Nếu Redis trả value, Spring Data Redis dùng `hashValueSerializer` để diễn giải bytes thành object Java.

### 1.2. Đừng nhầm `valueSerializer` và `hashValueSerializer`

`RedisTemplate` có bốn serializer thường gặp:

| Thuộc tính | Chủ yếu ảnh hưởng | Ví dụ |
|---|---|---|
| `keySerializer` | Redis key trong các nhóm operation | `GET greeting`, `HGET app:user:42 name` |
| `valueSerializer` | Value của `ValueOperations` | `SET greeting hello` |
| `hashKeySerializer` | Field trong `HashOperations` | `name` trong `HGET app:user:42 name` |
| `hashValueSerializer` | Value của field trong `HashOperations` | `Lan` trong `HGET app:user:42 name` |

Vì thế **đã gọi `setValueSerializer(...)` không có nghĩa Hash value sẽ tự dùng serializer đó**. Với Hash, phải kiểm tra `getHashValueSerializer()` hoặc cấu hình `setHashValueSerializer(...)`.

Các loại operation khác như List, Set hay Sorted Set có quy tắc serialization riêng theo API của template. Bài này chỉ tập trung vào Hash.

## 2. Kiểu generic của HashOperations và serializer thực tế

Spring Data Redis định nghĩa:

~~~java
HashOperations<K, HK, HV>
~~~

Trong đó:

- `K` là kiểu Java của Redis key ngoài cùng.
- `HK` là kiểu Java của tên Hash field.
- `HV` là kiểu Java của Hash field value.

Ví dụ:

~~~java
HashOperations<String, String, String> hashes =
        stringRedisTemplate.opsForHash();

hashes.put("app:user:42", "name", "Lan");
String name = hashes.get("app:user:42", "name");
~~~

Ở ví dụ này cả ba giá trị Java là String. Tuy nhiên, generic chỉ hướng dẫn Java compiler. **Kiểu Java không tự quyết định định dạng bytes**. Một `RedisTemplate<String, Object>` vẫn có thể dùng JDK serialization; một `RedisTemplate<String, AddressDto>` không tự tạo JSON serializer nếu không được cấu hình.

Các method Hash cơ bản và vị trí serializer cần đến:

| Method | Redis command | Vai trò |
|---|---|---|
| `put(key, field, value)` | `HSET` | Encode key, field, value |
| `get(key, field)` | `HGET` | Encode key/field; decode value khi tồn tại |
| `putAll(key, map)` | `HSET` nhiều field | Encode từng field/value |
| `entries(key)` | `HGETALL` | Decode **cả field lẫn value** |
| `keys(key)` | `HKEYS` | Decode tên field |
| `values(key)` | `HVALS` | Decode field value |
| `hasKey(key, field)` | `HEXISTS` | Encode key/field |
| `delete(key, fields...)` | `HDEL` | Encode key/các field |
| `increment(key, field, delta)` | `HINCRBY` / `HINCRBYFLOAT` | Giá trị trong Redis phải có biểu diễn số hợp lệ |

Nếu `get()` trả `null` nhưng `entries()` ném lỗi, hãy xem lại việc encode field và việc decode các field trả về: hai lệnh tương tác với bytes khác nhau.

## 3. `hashKeySerializer` thực sự xử lý gì?

### 3.1. Field name được so khớp theo bytes

Với Java String `"name"`:

~~~text
StringRedisSerializer:
  UTF-8 bytes: 6E 61 6D 65

JdkSerializationRedisSerializer:
  Java serialization stream: AC ED 00 05 ...
  (còn có metadata cho Java String)
~~~

Hai biểu diễn trên **khác nhau về bytes**. Nếu ứng dụng A dùng `StringRedisSerializer` để ghi field tên `name`, ứng dụng B dùng `JdkSerializationRedisSerializer` để tìm `name`, Redis không coi chúng là cùng một field.

Hãy tưởng tượng Hash có:

~~~text
app:user:42
  field bytes [6E 61 6D 65]                    → "Lan"
  field bytes [AC ED 00 05 ...String "name"]    → "Mai"
~~~

Cả hai field vẫn có thể cùng tồn tại. Khi mỗi client serialize String `name` theo kiểu của nó, mỗi bên đọc một entry khác. Redis không giải mã Java object để so sánh ý nghĩa của tên field.

### 3.2. Sai serializer field có thể dẫn tới cache miss giả

Giả sử A đã ghi:

~~~java
// A dùng hashKeySerializer = StringRedisSerializer
hashA.put("app:user:42", "name", "Lan");
~~~

B đọc cùng top-level key nhưng field serializer khác:

~~~java
// B dùng hashKeySerializer = JdkSerializationRedisSerializer
Object name = hashB.get("app:user:42", "name");
~~~

`name` có thể là `null` dù Redis Hash vẫn chứa một field tên `name` ở dạng text. Redis chỉ nhận field bytes do B gửi và không tìm thấy chúng.

Đây là lỗi **chọn sai field**, không phải lỗi network hoặc nhất thiết là lỗi `hashValueSerializer`. Nếu B gọi `entries()`, Redis trả tất cả field bytes; B có thể ném lỗi khi cố deserialize field UTF-8 bằng Java deserializer.

### 3.3. Vì sao thường dùng String cho field name?

Tên field thường là các nhãn ổn định:

~~~text
name
email
status
createdAt
shipping
billing
~~~

Với `StringRedisSerializer`:

- Các tên field hiển thị rõ trong Redis CLI.
- Những client khác dùng UTF-8 có thể truy cập cùng field.
- Không phụ thuộc vào tên Java class hoặc `serialVersionUID`.
- Các command `HGET`, `HDEL`, `HEXISTS` dễ dùng từ các ngôn ngữ khác.

Nếu field name được tạo từ nội dung người dùng, phải thống nhất chuẩn hóa ký tự, cách encode và giới hạn độ dài. String serializer không tự thực hiện validation hay bảo mật.

### 3.4. Sai top-level key serializer còn xảy ra sớm hơn

Nếu A ghi bằng `keySerializer = StringRedisSerializer`:

~~~text
Redis key bytes → "app:user:42"
~~~

nhưng B dùng `keySerializer = JdkSerializationRedisSerializer`, chính tên Redis key ngoài cùng đã có bytes khác. Khi đó B đang hỏi một key khác, bất kể `hashKeySerializer` đúng hay sai.

Khi dữ liệu có vẻ mất, hãy kiểm tra **từ ngoài vào trong**:

~~~text
keySerializer       → tìm đúng Redis key?
hashKeySerializer   → tìm đúng Hash field?
hashValueSerializer → giải mã đúng nội dung field?
~~~

## 4. `hashValueSerializer` xử lý nội dung field

### 4.1. Cùng một field có thể chứa các định dạng khác nhau

Giả sử Redis key và field là:

~~~text
app:user:42
  field: profile
~~~

Value có thể được encode dưới nhiều dạng:

| Cách lưu | Ví dụ bytes/biểu diễn | Khi đọc |
|---|---|---|
| String UTF-8 | `Lan` | `StringRedisSerializer` |
| JSON String | `"Lan"` gồm dấu nháy JSON | JSON serializer cho String |
| JSON object | `{"name":"Lan","age":28}` | JSON serializer cho DTO |
| Java Serialization | `AC ED 00 05 ...` | JDK deserializer tương thích |
| Protobuf | bytes theo schema định nghĩa | Parser Protobuf đúng schema |

Redis không lưu thêm nhãn “đây là JSON” cho field. Chính producer và consumer phải thống nhất.

### 4.2. Sai value serializer thường tạo lỗi decode

Giả sử:

~~~text
keySerializer      = StringRedisSerializer
hashKeySerializer  = StringRedisSerializer
~~~

A ghi field `profile` bằng JSON, còn B dùng `JdkSerializationRedisSerializer` để đọc. Redis tìm **đúng field** và trả JSON bytes. Nhưng B cố xử lý chúng như Java serialized stream, nên có thể gặp `SerializationException`, `StreamCorruptedException` hoặc lỗi liên quan.

So sánh các lỗi:

| Thành phần không tương thích | Redis thấy gì? | Biểu hiện phổ biến |
|---|---|---|
| `keySerializer` | Redis key bytes khác | Không tìm thấy top-level key |
| `hashKeySerializer` | Field bytes khác | `HGET` trả nil, phía Java có thể `null` |
| `hashValueSerializer` | Field có thật nhưng value bytes không khớp parser | Lỗi deserialize, kết quả sai kiểu |
| Cùng tên key bị dùng cho Redis type khác | Key tồn tại nhưng không phải HASH | `WRONGTYPE` |

Một số parser có thể xử lý được bytes nhưng trả object sai ngữ nghĩa. Vì vậy “không có exception” chưa đủ để khẳng định tương thích schema.

### 4.3. Hash value chứa dữ liệu số: chú ý lệnh Redis

Một Hash kiểu thống kê:

~~~redis
HSET app:stats:42 views 10
HINCRBY app:stats:42 views 1
HGET app:stats:42 views
~~~

Với field value là decimal text `10`, Redis `HINCRBY` có thể tăng lên `11`.

Nếu value thực sự là bytes Java serialization của Integer `10`, hoặc JSON String có dấu nháy `"10"`, Redis không coi đó là số thập phân hợp lệ và có thể trả lỗi:

~~~text
ERR hash value is not an integer
~~~

Bởi vậy, serializer phải phù hợp **với command Redis cần chạy**, không chỉ thuận tiện khi Java deserialize.

## 5. Khi nào chọn `StringRedisTemplate`?

`StringRedisTemplate` dùng String serializer cho Redis key/value và Hash field/value, nên thích hợp với Hash có dữ liệu text hoặc số được lưu dạng chuỗi.

~~~java
import java.util.Map;

import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class UserProfileHashStore {

    private final HashOperations<String, String, String> hashes;

    public UserProfileHashStore(StringRedisTemplate redis) {
        this.hashes = redis.opsForHash();
    }

    public void save(String userId, String name, String city) {
        hashes.putAll(
                "app:user:" + userId,
                Map.of("name", name, "city", city)
        );
    }

    public String findName(String userId) {
        return hashes.get("app:user:" + userId, "name");
    }

    public Map<String, String> findAll(String userId) {
        return hashes.entries("app:user:" + userId);
    }

    public void removeCity(String userId) {
        hashes.delete("app:user:" + userId, "city");
    }
}
~~~

Sau khi gọi:

~~~java
store.save("42", "Lan", "Da Nang");
~~~

có thể quan sát bằng Redis CLI:

~~~redis
TYPE app:user:42
HGET app:user:42 name
HGET app:user:42 city
HKEYS app:user:42
HGETALL app:user:42
~~~

Các tên field và value đều dễ đọc. `HGET app:user:42 name` trả `"Lan"` nếu key/field chưa bị sửa/xóa/expire.

Với dữ liệu số, `StringRedisTemplate` không tự biến `"28"` thành Java Integer. Ứng dụng phải parse và validate phù hợp:

~~~java
String rawAge = hashes.get("app:user:42", "age");

if (rawAge == null) {
    // Thiếu field, xử lý theo nghiệp vụ.
} else {
    int age = Integer.parseInt(rawAge);
}
~~~

Không nên tự động gán mọi field vắng mặt thành số 0, vì điều đó có thể che giấu lỗi dữ liệu.

## 6. Tự cấu hình bốn serializer của RedisTemplate

Một cấu hình rõ ràng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class TextHashRedisConfiguration {

    @Bean("textHashRedisTemplate")
    RedisTemplate<String, String> textHashRedisTemplate(
            RedisConnectionFactory connectionFactory
    ) {
        RedisTemplate<String, String> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer text = new StringRedisSerializer();

        template.setKeySerializer(text);
        template.setValueSerializer(text);
        template.setHashKeySerializer(text);
        template.setHashValueSerializer(text);

        return template;
    }
}
~~~

Cách đặt bean tên `textHashRedisTemplate` tránh vô tình ghi đè bean `redisTemplate` mặc định. Khi có nhiều template, inject theo `@Qualifier` để service chọn đúng serializer.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class TextHashUsage {

    private final HashOperations<String, String, String> hashes;

    public TextHashUsage(
            @Qualifier("textHashRedisTemplate")
            RedisTemplate<String, String> template
    ) {
        this.hashes = template.opsForHash();
    }

    public void write() {
        hashes.put("app:demo:1", "field", "value");
    }
}
~~~

### 6.1. Một sai lầm rất thường gặp: chỉ set key/value serializer

~~~java
RedisTemplate<String, String> template = new RedisTemplate<>();
template.setConnectionFactory(connectionFactory);

template.setKeySerializer(new StringRedisSerializer());
template.setValueSerializer(new StringRedisSerializer());

// Quên setHashKeySerializer(...)
// Quên setHashValueSerializer(...)
~~~

Người viết có thể tưởng `opsForHash()` cũng dùng String serializer, nhưng `hashKeySerializer` và `hashValueSerializer` là hai cấu hình độc lập. Nếu chúng chưa được chỉ định, cơ chế default serializer của RedisTemplate có thể điền **JdkSerializationRedisSerializer**, tùy cấu hình template.

Khi đó key ngoài cùng có thể đọc bằng Redis CLI vì `keySerializer` là String, nhưng tên field và value lại trông như dữ liệu nhị phân Java. Client dùng `StringRedisTemplate` sẽ không thể đọc theo cùng cách.

**Hãy kiểm tra cả bốn serializer** khi thiết kế một custom RedisTemplate, đặc biệt nếu ứng dụng dùng chung keyspace với service khác.

### 6.2. Tắt default serializer không phải là “dùng String”

`RedisTemplate` có thể dùng default serializer và cờ cho phép/không cho phép sử dụng nó. Nếu tắt cơ chế điền default serializer, các vị trí không được cấu hình có thể dẫn tới xử lý raw bytes hoặc hành vi phụ thuộc API/driver.

Cách ổn định hơn là chỉ định serializer rõ cho những loại operation mà bean sử dụng. Không nên xem cấu hình `enableDefaultSerializer=false` như một cách tự động áp UTF-8.

## 7. Hash field là String, value là DTO JSON

Nếu mỗi field chứa một object cùng kiểu, có thể dùng Hash key bằng String và Hash value bằng JSON typed.

Ví dụ:

~~~text
app:user:42:addresses (HASH)
  shipping → {"city":"Da Nang","street":"12 Tran Phu"}
  billing  → {"city":"Hue","street":"8 Le Loi"}
~~~

### 7.1. DTO

~~~java
public record AddressDto(
        String city,
        String street
) {
}
~~~

### 7.2. Template typed

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class AddressHashConfiguration {

    @Bean("addressHashRedisTemplate")
    RedisTemplate<String, AddressDto> addressHashRedisTemplate(
            RedisConnectionFactory connectionFactory,
            ObjectMapper objectMapper
    ) {
        RedisTemplate<String, AddressDto> template =
                new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer text = new StringRedisSerializer();

        Jackson2JsonRedisSerializer<AddressDto> json =
                new Jackson2JsonRedisSerializer<>(
                        objectMapper,
                        AddressDto.class
                );

        template.setKeySerializer(text);
        template.setHashKeySerializer(text);
        template.setValueSerializer(json);
        template.setHashValueSerializer(json);

        return template;
    }
}
~~~

Ở đây:

- Redis key ngoài cùng và Hash field name được serialize như text UTF-8.
- Hash field value được serialize thành JSON của `AddressDto`.
- `valueSerializer` cũng là JSON vì ứng dụng có thể muốn dùng `opsForValue()` với cùng DTO, nhưng cấu hình này **không thay thế `hashValueSerializer`**.

Sử dụng:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class AddressHashStore {

    private final HashOperations<String, String, AddressDto> hashes;

    public AddressHashStore(
            @Qualifier("addressHashRedisTemplate")
            RedisTemplate<String, AddressDto> template
    ) {
        this.hashes = template.opsForHash();
    }

    public void save(String userId, AddressDto address) {
        hashes.put(
                "app:user:" + userId + ":addresses",
                "shipping",
                address
        );
    }

    public AddressDto find(String userId) {
        return hashes.get(
                "app:user:" + userId + ":addresses",
                "shipping"
        );
    }

    public Map<String, AddressDto> findAll(String userId) {
        return hashes.entries("app:user:" + userId + ":addresses");
    }
}
~~~

Khi gọi:

~~~java
store.save("42", new AddressDto("Da Nang", "12 Tran Phu"));
~~~

`HGET app:user:42:addresses shipping` có thể trả JSON của DTO. Một service khác có thể đọc nó nếu cả hai thống nhất schema JSON, tên key, tên field và encoding.

### 7.3. Không dùng một serializer typed cho mọi kiểu value

Một Hash chứa:

~~~text
name      → "Lan"
age       → 28
profile   → {"city":"Da Nang"}
~~~

không phù hợp với `Jackson2JsonRedisSerializer<AddressDto>` cho tất cả field, vì `name` và `age` không phải AddressDto.

Có thể chọn:

- Lưu toàn bộ field value dưới dạng String, tự parse theo tên field và validate.
- Tách Hash theo kiểu value, mỗi Hash dùng một DTO typed.
- Lưu toàn object thành một JSON value trong Redis STRING nếu không cần thao tác field riêng.
- Xây dựng schema và format riêng nếu có lý do rõ ràng để duy trì nhiều kiểu value trong một Hash.

Dùng JSON serializer generic với type metadata có thể giúp lưu nhiều class, nhưng cũng tăng phức tạp versioning và rủi ro khi deserialize type không đáng tin cậy. Ưu tiên typed DTO với schema cụ thể khi có thể.

## 8. Một bảng lỗi thực tế khi hai service không thống nhất serializer

Giả sử service A đang ghi Hash bằng String serializer, service B định đọc cùng dữ liệu:

| A ghi | B đọc | Kết quả có thể xảy ra |
|---|---|---|
| Key String, field String, value String | Cùng ba serializer | Đọc đúng |
| Key String, field String, value String | Key JDK, field String, value String | Không tìm được Redis key ngoài cùng |
| Key String, field String, value String | Key String, field JDK, value String | `HGET` có thể trả `null` do field bytes khác |
| Key String, field String, value JSON | Key String, field String, value JDK | Tìm đúng field nhưng deserialize lỗi |
| Key String, field String, value String | Key String, field String, value JSON typed | Có thể lỗi parse hoặc tạo value không đúng schema |
| Dùng Redis STRING tại key `app:user:42` | B gọi HashOperations trên key đó | `WRONGTYPE` |

Không phải mọi mismatch đều biểu hiện giống nhau. Nếu cần tìm nguyên nhân, hãy xác định lỗi xảy ra ở **định vị Redis key**, **định vị Hash field**, hay **giải mã Hash value**.

### 8.1. `get()` trả `null`: cần kiểm tra gì?

Ví dụ:

~~~java
String name = hashes.get("app:user:42", "name");
~~~

`null` có thể có nghĩa:

1. Redis key ngoài cùng chưa tồn tại, đã hết TTL hoặc bị eviction.
2. Redis key tồn tại nhưng field `name` chưa được ghi/đã bị xóa.
3. `keySerializer` làm tên Redis key khác với tên bên ghi dùng.
4. `hashKeySerializer` làm bytes field khác với bytes bên ghi dùng.
5. Ứng dụng trỏ sai Redis instance hoặc logical database.

Trong pipeline hoặc transaction đang xếp hàng, nhiều API còn có thể trả `null` **tạm thời vì chưa có response**. Đó là tình huống khác với `HGET` đã thực thi và Redis trả nil.

### 8.2. `entries()` lỗi nhưng `get()` chỉ ra null

`get()` chỉ gửi field bytes được tạo bằng serializer hiện tại. Nếu field bytes không khớp, Redis trả nil. Ngược lại, `entries()` lấy toàn bộ field/value từ Redis rồi deserialize từng phần; field hoặc value lưu từ phiên bản cũ có thể gây lỗi.

Cách điều tra: quan sát Redis key type, các field hiện có bằng Redis CLI và serializer của bean Java thực sự đang sử dụng. Không vội xóa dữ liệu trước khi xác định nguồn gốc.

### 8.3. `WRONGTYPE` không phải lỗi Hash serializer

~~~redis
SET app:user:42 "hello"
HGET app:user:42 name
~~~

Redis key `app:user:42` đang có type STRING, nên gọi `HGET` trả `WRONGTYPE`. Chỉnh `hashValueSerializer` không đổi được type của key; phải giải quyết đụng tên keyspace hoặc migration dữ liệu.

## 9. Thay serializer không tự chuyển dữ liệu đã lưu

Giả sử hệ thống cũ ghi Hash value bằng Java native serialization:

~~~text
Trước deploy:
  key: app:user:42
  field: profile  (UTF-8)
  value: AC ED 00 05 ...  (Java serialized object)

Sau deploy:
  cùng key và field
  app đọc bằng JSON serializer, mong JSON bytes
~~~

Đổi bean sang JSON không làm Redis tự ghi lại dữ liệu cũ. Khi JSON parser gặp value nhị phân Java, việc giải mã có thể thất bại.

Tương tự, đổi `hashKeySerializer` có thể dẫn tới nhiều field biểu diễn cùng tên logic nhưng bytes khác nhau, làm Hash chứa các entry trùng ý nghĩa nghiệp vụ.

### 9.1. Chiến lược migration với cache có thể tái tạo

Nếu database khác là nguồn dữ liệu chuẩn, có thể version keyspace:

~~~text
Legacy: app:user:42:addresses
New:    app:user:v2:42:addresses
~~~

Quy trình:

1. Xác định serializer và schema cho phiên bản mới.
2. Code mới chỉ đọc/ghi key `v2`.
3. Cache miss ở `v2` sẽ đọc nguồn dữ liệu chuẩn rồi tạo cache mới.
4. Key legacy tự hết TTL hoặc được dọn bằng quy trình được phép.
5. Sau khi mọi consumer đã chuyển, loại bỏ serializer và code legacy không còn cần.

Đừng dùng cơ chế “thử JSON, lỗi thì JDK deserialize” trên mọi request đối với bytes có thể bị nguồn không đáng tin cậy sửa. Java native deserialization có rủi ro riêng; migration phải kiểm soát ranh giới tin cậy.

Nếu Redis là nguồn dữ liệu duy nhất và không thể tái tạo, migration cần quy trình đọc dữ liệu cũ trong môi trường kiểm soát, chuyển đổi, đối soát đủ record và kế hoạch phục hồi trước khi xóa.

## 10. Quan sát bằng Redis CLI

Trong môi trường cho phép kiểm tra:

~~~bash
redis-cli TYPE app:user:42
redis-cli HLEN app:user:42
redis-cli HKEYS app:user:42
redis-cli HGET app:user:42 name
redis-cli HGETALL app:user:42
redis-cli TTL app:user:42
~~~

Ý nghĩa:

- `TYPE` xác nhận Redis key ngoài cùng thực sự là HASH.
- `HLEN` cho biết số field; hữu ích khi `get()` trả `null`.
- `HKEYS` trả field name bytes (CLI cố hiển thị chúng).
- `HGET` đọc value của một field cụ thể.
- `HGETALL` trả toàn bộ field/value, có thể khó đọc khi lưu binary.
- `TTL` hiển thị TTL của **Redis key ngoài cùng**.

Trong mô hình thông thường, `EXPIRE app:user:42 ...` đặt TTL cho toàn bộ Hash. Redis có các tính năng field expiration ở những phiên bản mới hơn; việc hỗ trợ cụ thể phụ thuộc Redis server, driver và Spring Data Redis version. Các serializer không phải cơ chế quản lý TTL riêng của field.

### 10.1. Kiểm tra bean serializer đang dùng

Một đoạn code quan sát trong môi trường development:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisSerializerInspector {

    public RedisSerializerInspector(
            @Qualifier("addressHashRedisTemplate")
            RedisTemplate<String, AddressDto> template
    ) {
        System.out.println("key: " + template.getKeySerializer());
        System.out.println("value: " + template.getValueSerializer());
        System.out.println("hash key: " + template.getHashKeySerializer());
        System.out.println("hash value: " + template.getHashValueSerializer());
    }
}
~~~

Đây là ví dụ tạm thời để tìm hiểu bean wiring. Không cần giữ `System.out.println` trong production. Nếu có nhiều `RedisTemplate`, phải xem bean thực sự được inject vào service đang đọc/ghi Hash; kiểm tra một template khác không kết luận được gì về đường truy cập.

Một serializer hiện tại đúng với format mới cũng không chứng minh các key cũ đều đang lưu bytes theo format đó.

## 11. Serializer, Hash mapping và Redis Repository không giống nhau

Spring Data Redis có các cơ chế mapping object sang Hash và Redis Repositories với `@RedisHash`, `@Id`, `@Indexed`. Cần phân biệt:

| Tầng | Mục đích | Ví dụ |
|---|---|---|
| Object-to-Hash mapping | Chuyển Java object thành các cặp field/value logic | `name → Lan`, `age → 28` |
| Hash serialization | Chuyển từng field/value logic thành bytes | UTF-8, JSON, Java serialization |
| Repository mapping | Quản lý keyspace, ID, index và lifecycle của entity | `@RedisHash`, `@Id` |

`HashMapper` có thể cung cấp map của các field/value từ object, nhưng phần giao tiếp với Redis vẫn phải dùng một biểu diễn bytes thống nhất. Với repository, framework có thể quản lý thêm các key metadata/index riêng. Thay serializer ở một `RedisTemplate` tự định nghĩa **không tự động thay mọi định dạng của Redis Repositories**.

Nếu ứng dụng viết trực tiếp vào cùng Hash do repository quản lý, có thể phá vỡ index/metadata hoặc ghi các field với serializer khác. Hãy quyết định ai sở hữu mỗi nhóm key và giữ quy tắc mapping, serialization nhất quán.

## 12. Bảo mật và tương thích liên service

### 12.1. Không nên tùy tiện dùng Java native serialization

`JdkSerializationRedisSerializer` sử dụng Java Object Serialization. Khi deserialize byte stream không đáng tin cậy, mã trong một số class/hook có thể được thực thi hoặc tiêu tốn tài nguyên không mong muốn. Rủi ro phụ thuộc nguồn bytes và classpath của ứng dụng.

Với Hash đọc/ghi bởi nhiều service hoặc chứa dữ liệu từ nguồn bên ngoài, thường nên dùng:

- `StringRedisSerializer` cho tên Redis key và Hash field.
- String cho dữ liệu đơn giản và số cần thao tác trực tiếp bằng Redis command.
- JSON DTO typed hoặc định dạng có schema rõ cho object có cấu trúc.

Ngay cả JSON cũng cần parser, schema, validation và chính sách type resolution phù hợp. Không nên mở cơ chế tạo Java class tùy ý từ metadata trong payload không đáng tin cậy.

### 12.2. Hợp đồng dữ liệu liên ngôn ngữ

Nếu Java, Python và Node.js cùng dùng Redis Hash, tất cả bên phải thống nhất:

~~~text
Redis key encoding: UTF-8
Hash field encoding: UTF-8
Hash value encoding: JSON theo schema định trước
Schema version: 2
~~~

Cần định nghĩa thêm cách xử lý field thiếu, value rỗng, chuỗi `"null"` và JSON `null`, kiểu số, timezone, TTL và phiên bản schema. Đừng giả định mọi ngôn ngữ cùng cách chuyển kiểu.

### 12.3. Generic không thay thế serializer

~~~java
RedisTemplate<String, AddressDto> template;
~~~

không có nghĩa template đang lưu Hash value ở dạng JSON. Chỉ khi `setHashValueSerializer(...)` được cấu hình phù hợp, bytes mới theo định dạng mong muốn. Để xác nhận, phải nhìn serializer runtime và dữ liệu thực tế, không chỉ chữ ký generic.

## 13. Bảng quyết định chọn serializer cho Redis Hash

| Trường hợp | Redis key | Hash key | Hash value |
|---|---|---|---|
| Hồ sơ người dùng với field String đơn giản | String | String | String |
| Thống kê cần `HINCRBY` | String | String | Decimal text |
| Hash chứa nhiều địa chỉ cùng kiểu DTO | String | String | Typed JSON cho `AddressDto` |
| Hash chia sẻ giữa Java/Node/Python | Thống nhất encoding | Thống nhất encoding | JSON/schema liên ngôn ngữ |
| Hệ thống cũ đã lưu Java binary | Kiểm tra dữ liệu đang có | Kiểm tra định dạng thực tế | Lập kế hoạch migration có kiểm soát |

Các nguyên tắc quan trọng:

1. **`hashKeySerializer` quản lý field name**, không quản lý tên Redis key ngoài cùng.
2. **`hashValueSerializer` quản lý bytes của field value**, độc lập với `valueSerializer`.
3. **`opsForHash()` cần ba serializer phù hợp**: key, hash key và hash value.
4. **Dùng String cho field name khi có thể** để dễ quan sát, tích hợp và dùng các command trực tiếp.
5. **Chọn value serializer theo loại dữ liệu và command**: số cần `HINCRBY`, DTO JSON cần schema, text cần encoding thống nhất.
6. **Khi gặp `null`, kiểm tra key và field** trước khi cho rằng value không giải mã được.
7. **Khi gặp lỗi deserialize, kiểm tra schema/value serializer**, sau khi xác nhận key/field đã tìm đúng.
8. **Đổi serializer không tự viết lại Redis**: version keyspace hoặc migration tường minh.
9. **Cấu hình rõ cả bốn serializer nếu tự tạo RedisTemplate**, và inject đúng bean.
10. **Không trộn ghi thủ công với repository** nếu chưa hiểu mapping và các key nội bộ.

Redis Hash chỉ là cấu trúc **Redis key → field bytes → value bytes**. Nắm được ranh giới này giúp bạn giải thích vì sao cùng một field Java có thể biến thành hai field Redis khác nhau, vì sao một lệnh `HGET` trả `null` dù dữ liệu còn đó, và vì sao đổi `hashValueSerializer` có thể làm ứng dụng đọc hỏng dữ liệu cũ.

## Tài liệu tham khảo

- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Serializers](https://docs.spring.io/spring-data/redis/reference/redis/serializers.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis API — RedisTemplate](https://docs.spring.io/spring-data/redis/docs/3.3.x/api/org/springframework/data/redis/core/RedisTemplate.html)
- [Spring Data Redis API — HashOperations](https://docs.spring.io/spring-data/redis/docs/3.3.x/api/org/springframework/data/redis/core/HashOperations.html)
- [Redis — Hashes](https://redis.io/docs/latest/develop/data-types/hashes/)
- [Redis — HGET](https://redis.io/docs/latest/commands/hget/)
- [Redis — HSET](https://redis.io/docs/latest/commands/hset/)
- [Redis — HINCRBY](https://redis.io/docs/latest/commands/hincrby/)

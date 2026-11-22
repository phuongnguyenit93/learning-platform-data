# Dữ liệu trong redis-cli khác kết quả ứng dụng do serializer

## 1. Tình huống: Redis có dữ liệu nhưng hai công cụ nhìn thấy khác nhau

Một lập trình viên dùng Spring Data Redis ghi object thành công:

```java
redisTemplate.opsForValue().set("user:42", user);
```

Ứng dụng sau đó đọc lại:

```java
User user = (User) redisTemplate.opsForValue().get("user:42");
```

Kết quả trong Java là một `User` hợp lệ. Nhưng khi mở terminal:

```bash
redis-cli GET user:42
```

lại nhận:

```text
(nil)
```

Một trường hợp khác: `redis-cli GET product:42` thấy một chuỗi có ký tự lạ hoặc JSON kèm tên lớp Java, trong khi Java trả về object hoàn chỉnh.

Hoặc:

```redis
TYPE person:42
```

trả về:

```text
hash
```

trong khi người dùng cố chạy `GET person:42` rồi gặp `WRONGTYPE`.

Những hiện tượng này không nhất thiết là Redis làm mất dữ liệu, không nhất thiết Redis Server và Spring Boot có cache khác nhau, và cũng không chứng minh Redis bị lỗi. Nguyên nhân thường nằm ở **serializer**, **Redis data type**, hoặc cách tạo tên key.

> Redis lưu **dãy byte của key/value** và các cấu trúc dữ liệu Redis. `redis-cli` không tự biết phải giải mã Java object bằng serializer nào, còn Spring Data Redis có thể mã hóa cả key lẫn value trước khi gửi lệnh.

Bài học thuộc chương **Chẩn đoán** của Spring Data Redis: đi từ những gì người vận hành nhìn thấy trong `redis-cli` đến việc xác định chính xác bytes mà ứng dụng gửi và mong đợi khi đọc.

### Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt dữ liệu logic Java, bytes được serialize và dữ liệu Redis thực lưu.
2. Giải thích vì sao `redis-cli GET key` trả `(nil)` dù `RedisTemplate` đọc được.
3. Nhận biết dấu hiệu Java native serialization, JSON serialization, UTF-8 String, binary codec và Redis Hash.
4. Phân biệt `keySerializer`, `valueSerializer`, `hashKeySerializer`, `hashValueSerializer` và serializer của Spring Cache.
5. Dùng `TYPE`, `EXISTS`, `TTL`, `STRLEN`, `HGETALL` và thông tin kết nối để thu hẹp nguyên nhân.
6. Viết Java code so sánh raw key/value bytes với Redis serializer đang cấu hình.
7. Hiểu vì sao `StringRedisTemplate`, `RedisTemplate`, Redis Repository, Redis Cache và reactive template có thể nhìn cùng Redis theo những cách khác nhau.
8. Phân biệt lỗi serializer với sai Redis instance, logical database, key prefix, TTL, Cluster slot và data format migration.
9. Lập kế hoạch đổi serializer mà không tự phá dữ liệu đã ghi.
10. Thiết kế integration tests đọc dữ liệu do phiên bản ứng dụng cũ tạo để phòng ngừa lỗi khi triển khai.

---

## 2. Redis không lưu Java object như JVM đang nhìn thấy

Khi ứng dụng Java tạo:

```java
record ProductDto(
    String id,
    String name,
    long priceInCents
) {}
```

và muốn lưu đối tượng vào Redis, Spring phải chuyển dữ liệu sang một biểu diễn mà Redis nhận được.

Một đường đi điển hình:

```text
Java object:
  ProductDto("p-42", "Laptop", 1999900)
          |
          v
RedisSerializer<ProductDto>
          |
          v
byte[]:
  [7B, 22, 69, 64, 22, 3A, ...]  (nếu là JSON UTF-8)
          |
          v
Redis protocol: SET <key bytes> <value bytes>
          |
          v
Redis String value (bytes)
```

Khi đọc:

```text
Redis value bytes
          |
          v
RedisSerializer.deserialize(bytes)
          |
          v
Java ProductDto
```

`redis-cli` đứng ở một vị trí khác:

```text
redis-cli GET <key bytes>
          |
          v
Redis response bytes
          |
          v
Hiển thị theo chế độ redis-cli
```

CLI không chạy `ObjectMapper.readValue(...)` hay `JdkSerializationRedisSerializer.deserialize(...)` của ứng dụng trừ khi bạn tự lập trình bước giải mã tương ứng.

### 2.1. Có nhiều phép biến đổi cần phân biệt

| Thành phần | Ví dụ | Có phải Redis tự hiểu Java không? |
|---|---|---|
| Java object | `ProductDto("p-42", ...)` | Không |
| Java key String | `"product:42"` | Chưa phải key bytes |
| Key serializer | `StringRedisSerializer` | Spring/client xử lý |
| Value serializer | JSON/JDK/codec riêng | Spring/client xử lý |
| Redis key | Dãy bytes | Redis dùng để tra cứu |
| Redis String value | Dãy bytes | Redis lưu, không biết Java class |
| Redis Hash field | Dãy bytes | Field cũng cần serializer |
| redis-cli display | Chuỗi in được, escape hoặc binary | Chỉ là cách trình bày |
| Java deserializer | `byte[] -> Java object` | Ứng dụng/driver xử lý |

Điểm quan trọng: **Redis String là một kiểu dữ liệu Redis**, không có nghĩa value là một `java.lang.String` có thể đọc bằng UTF-8.

### 2.2. Redis TYPE không cho biết serializer

```redis
TYPE product:42
```

Nếu trả:

```text
string
```

value có thể là:

- Văn bản UTF-8.
- JSON.
- Byte array từ Java serialization.
- Protobuf/MessagePack.
- Dữ liệu nén gzip/zstd.
- Dữ liệu đã mã hóa.
- Một format binary riêng của công ty.

`TYPE string` chỉ nói Redis đang lưu một **Redis String** (binary-safe), không nói nội dung là UTF-8 hay JSON.

### 2.3. Dữ liệu binary không đồng nghĩa dữ liệu hỏng

Nếu CLI hiển thị:

```text
"\xac\xed\x00\x05..."
```

đó có thể là phần đầu của Java Object Serialization stream. Prefix hexadecimal `AC ED 00 05` là dấu hiệu thường gặp của Java native serialization, nhưng phải kiểm tra cả serializer thực tế trước khi kết luận.

Dữ liệu hiển thị khó đọc chưa chắc là lỗi lưu trữ. Điều cần xác nhận là **đúng bytes, đúng serializer và đúng schema**.

---

## 3. Một lời gọi Spring Data Redis có thể serialize cả key và value

Xét:

```java
redisTemplate.opsForValue().set(
    "customer:42",
    customer
);
```

Ở mức ý tưởng, client thực hiện:

```text
Java key:
    "customer:42"
        |
        v
keySerializer.serialize(...)
        |
        v
Redis key bytes

Java value:
    Customer object
        |
        v
valueSerializer.serialize(...)
        |
        v
Redis value bytes
```

Hai serializer **độc lập**. Có thể ứng dụng dùng:

```text
Key:   JDK serialization
Value: JDK serialization
```

hoặc:

```text
Key:   UTF-8 String
Value: JSON
```

hoặc:

```text
Key:   UTF-8 String
Value: Protobuf binary
```

Vì vậy lỗi khi CLI không tìm được key và lỗi khi CLI nhìn thấy value không đọc được có thể là **hai vấn đề khác nhau**.

### 3.1. Key serializer sai kỳ vọng dẫn đến `(nil)`

Giả sử `RedisTemplate` dùng JDK serialization cho key:

```java
redisTemplate.opsForValue().set("user:42", user);
```

Thực tế key bytes được gửi có thể là một chuỗi binary bắt đầu bằng Java serialization header, không phải chuỗi ASCII/UTF-8:

```text
u s e r : 4 2
```

Khi CLI chạy:

```redis
GET user:42
```

nó gửi **UTF-8 bytes của literal `user:42`**, khác bytes mà Java đã serialize.

Redis so sánh key theo byte; hai dãy bytes không bằng nhau nên trả `(nil)`.

```text
Java client key bytes:
    [AC ED 00 05 ... "user:42" ...]   (minh họa)

redis-cli key bytes:
    [75 73 65 72 3A 34 32]           (UTF-8 "user:42")

Kết quả:
    two different Redis keys
```

**Đừng chỉ đổi `redis-cli --raw` rồi kỳ vọng tìm được key.** `--raw` điều khiển cách CLI hiển thị kết quả, không tự thay key argument thành bytes của `JdkSerializationRedisSerializer`.

### 3.2. Value serializer khác dẫn đến dữ liệu “lạ”

Nếu key dùng String serializer nhưng value dùng Java serialization:

```text
Key bytes:   "user:42"
Value bytes: AC ED 00 05 ...
```

thì:

```redis
GET user:42
```

sẽ tìm được key nhưng trả một chuỗi binary khó đọc.

Khi Java dùng đúng `JdkSerializationRedisSerializer`, bytes đó có thể được chuyển lại thành object.

### 3.3. Hai ứng dụng có thể đọc các giá trị khác nhau vì khác serializer

Ví dụ:

```text
Service A:
    keySerializer = String
    valueSerializer = JSON

Service B:
    keySerializer = String
    valueSerializer = JDK
```

Cả hai dùng Redis Server và key `"product:42"` giống nhau. Service A ghi JSON; service B đọc bytes rồi cố giải mã như Java native serialization.

Kết quả có thể là:

```text
SerializationException
StreamCorruptedException
ClassCastException
```

hoặc lỗi giải mã khác tùy code và cấu hình.

Một Redis Server “healthy” không bảo đảm hai ứng dụng có cùng **data contract**.

---

## 4. Các serializer phổ biến trong Spring Data Redis

### 4.1. StringRedisSerializer

Mục đích:

```text
Java String <-> bytes theo charset được cấu hình
```

Với UTF-8 phổ biến:

```java
new StringRedisSerializer()
```

Ví dụ:

```java
String input = "hello";
byte[] data = new StringRedisSerializer().serialize(input);
```

Redis nhận những bytes phù hợp văn bản. CLI thường có thể đọc:

```redis
GET lab:greeting
```

khi cả key và value dùng String serializer tương ứng.

**Cần lưu ý Unicode:** `String.length()` trong Java không bằng số bytes UTF-8. Các ký tự tiếng Việt có thể chiếm nhiều byte; khi đo payload, hãy dùng `serializedBytes.length`.

### 4.2. JdkSerializationRedisSerializer

Chuyển object theo Java native serialization. Một số cấu hình `RedisTemplate` có thể dùng Java serialization mặc định cho phần lớn operations nếu không được tùy chỉnh, nhưng **phải kiểm tra bean thực tế** thay vì coi đây là mặc định của mọi ứng dụng.

Dấu hiệu thường gặp:

```text
AC ED 00 05 ...
```

Rủi ro:

- Không thân thiện khi đọc trong redis-cli.
- Phụ thuộc class name, `serialVersionUID` và compatibility của Java object graph.
- Có thể lỗi sau đổi package/class/schema.
- Dữ liệu native Java deserialization từ nguồn không đáng tin cần được đánh giá bảo mật nghiêm ngặt.
- Khó chia sẻ contract bytes với ứng dụng không viết bằng Java.

**Không khuyến nghị bật Java native deserialization tùy tiện cho dữ liệu mà bên không đáng tin có thể điều khiển.**

### 4.3. Jackson JSON serializer

Một nhóm serializer dùng Jackson để chuyển Java object thành JSON bytes.

Ví dụ minh họa value:

```json
{"id":"p-42","name":"Laptop","priceInCents":1999900}
```

Trong một số cấu hình polymorphic/generic JSON, JSON còn chứa type metadata, ví dụ một field có dạng `@class` hoặc cơ chế type hint khác. **Tên trường, cấu trúc và nội dung chính xác phụ thuộc serializer, ObjectMapper, Spring Data Redis/Jackson version và cấu hình.**

Một người dùng CLI có thể thấy:

```json
{
  "@class": "com.example.ProductDto",
  "id": "p-42",
  "name": "Laptop",
  "priceInCents": 1999900
}
```

khác với object Java đã được deserialize vì CLI chỉ in JSON, còn Java mapper chuyển JSON thành class.

Không coi việc JSON chứa type metadata là mặc định cho mọi serializer Jackson; cũng không mở rộng polymorphic deserialization để đọc dữ liệu không đáng tin nếu chưa đánh giá an toàn.

### 4.4. Custom binary serializer

Các format có thể gặp:

```text
Protobuf
MessagePack
Avro
Kryo
Compressed JSON
Encrypted binary
Domain-specific binary codec
```

CLI có thể hiện ký tự lạ ngay cả khi dữ liệu hoàn toàn hợp lệ. Không thể xác định chính xác codec chỉ từ vài bytes đầu trong mọi trường hợp.

Phải xem **serializer bean, schema/version và data contract** của ứng dụng.

### 4.5. Serializer và Redis data type là hai trục khác nhau

| Redis type | Spring API điển hình | Serializer liên quan |
|---|---|---|
| String | `opsForValue()` | Key/value serializers |
| Hash | `opsForHash()` | Key/hashKey/hashValue serializers |
| List | `opsForList()` | Key/value serializers và mapping tương ứng |
| Set | `opsForSet()` | Key/value serializers |
| Sorted Set | `opsForZSet()` | Key/value serializers |
| Stream | `opsForStream()` | Stream key/record mapping/serialization theo API |
| Pub/Sub | `convertAndSend`/listeners | Message serializers theo cấu hình |
| Spring Cache | `RedisCacheManager` | Cache key/value serialization pairs |
| Redis Repository | Repository converter/mapping | Có thể khác `opsForValue` serializer |

Không nên suy một bean `RedisTemplate` duy nhất kiểm soát toàn bộ dữ liệu của tất cả abstractions trong project.

---

## 5. StringRedisTemplate và RedisTemplate không giống nhau

### 5.1. StringRedisTemplate

`StringRedisTemplate` được thiết kế cho dữ liệu String:

```java
@Autowired
StringRedisTemplate stringRedisTemplate;
```

Ví dụ:

```java
stringRedisTemplate.opsForValue().set(
    "lab:message",
    "Xin chào"
);
```

Trên đúng Redis database:

```redis
GET lab:message
```

CLI có thể hiển thị văn bản tương ứng nếu terminal/locale xử lý UTF-8 chính xác.

### 5.2. RedisTemplate<K,V>

`RedisTemplate` cho phép cấu hình serializers riêng:

```java
RedisTemplate<String, Object> template;
```

Chỉ thấy generic `<String,Object>` **không đủ** biết key bytes là UTF-8 hay value bytes là JSON. Cần xem:

```text
template.getKeySerializer()
template.getValueSerializer()
template.getHashKeySerializer()
template.getHashValueSerializer()
```

và các serializers được dùng trong execution path liên quan.

### 5.3. Hai beans có thể cùng tồn tại

Ứng dụng có thể khai báo:

```java
@Autowired
StringRedisTemplate stringRedisTemplate;

@Autowired
RedisTemplate<String, Object> redisTemplate;
```

Cùng gọi:

```java
stringRedisTemplate.opsForValue().get("user:42");
redisTemplate.opsForValue().get("user:42");
```

nhưng hai lời gọi có thể dùng key serializers khác nhau. Một lời gọi thấy giá trị; lời gọi kia `null` hoặc lỗi decode.

**Trước khi debug dữ liệu, xác định bean thực sự được inject tại code path đang chạy.**

### 5.4. Ví dụ tạo RedisTemplate dùng key String và value JSON

Một cấu hình minh họa theo nhóm Spring Data Redis sử dụng Jackson 2:

```java
package com.example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisSerializationConfig {

    @Bean
    RedisTemplate<String, Object> jsonRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, Object> template =
            new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(
            new StringRedisSerializer()
        );
        template.setValueSerializer(
            new GenericJackson2JsonRedisSerializer()
        );
        template.setHashKeySerializer(
            new StringRedisSerializer()
        );
        template.setHashValueSerializer(
            new GenericJackson2JsonRedisSerializer()
        );

        template.afterPropertiesSet();
        return template;
    }
}
```

**Lưu ý phiên bản:** API và tên class Jackson serializers có thể khác ở những thế hệ Spring Data Redis/Jackson mới hơn. Đây là ví dụ cho cấu hình có class này; khi triển khai phải dùng serializer phù hợp release đang chạy. Với dữ liệu thuộc một class cụ thể, typed serializer với schema rõ có thể phù hợp hơn generic polymorphic JSON serializer.

Với cấu hình trên, CLI có thể nhìn thấy key String trực tiếp, nhưng value vẫn có thể chứa JSON/type metadata tùy serializer.

### 5.5. Không sửa serializer chỉ để CLI hiển thị đẹp hơn

Nếu production đã có một triệu keys theo JDK serialization, đổi ngay `keySerializer` sang String có thể khiến ứng dụng **không tìm được** những key cũ.

Nếu đổi `valueSerializer` sang JSON trong khi keys còn chứa JDK bytes, ứng dụng có thể báo decode errors.

Serializer là **hợp đồng dữ liệu đang được lưu**, không chỉ lựa chọn hiển thị.

---

## 6. Phân tích câu hỏi: CLI trả `(nil)` là do đâu?

Một kết quả:

```redis
GET user:42
```

```text
(nil)
```

có thể có nhiều nguyên nhân:

1. Key thật sự không tồn tại.
2. Spring dùng key serializer khác, nên raw bytes khác `user:42`.
3. Spring Cache có prefix, chẳng hạn `users::42` thay vì `user:42`.
4. App đang kết nối một Redis host/port khác.
5. App dùng logical database khác (`SELECT`/database index) trên standalone Redis.
6. Redis Cluster key thuộc node/slot khác hoặc CLI không follow redirect đúng.
7. Key đã hết TTL hoặc bị eviction.
8. App đã đổi key naming scheme/version namespace.
9. Một writer khác xóa key trước khi bạn kiểm tra.
10. CLI đang dùng container/network endpoint khác instance mà Spring truy cập.

**Không kết luận nguyên nhân serializer từ một dòng `(nil)` duy nhất.**

### 6.1. Kiểm tra kết nối trước

Ở môi trường được phép:

```redis
PING
INFO server
INFO keyspace
```

Xác minh từ deployment/connection factory:

```text
Redis hostname
Port
TLS enabled
ACL username
Logical database index (standalone)
Cluster/Sentinel configuration
Namespace/prefix
Application environment
```

Không ghi Redis password vào command-line history hoặc logs chỉ để debug.

### 6.2. Redis logical databases

Trên standalone Redis, ứng dụng có thể dùng DB index khác 0:

```text
Spring client -> DB 2
redis-cli mặc định -> DB 0
```

Trong CLI phù hợp:

```bash
redis-cli -n 2
```

Sau đó `GET` lại key.

Nhưng **Redis Cluster không hỗ trợ nhiều logical databases kiểu standalone**; thường chỉ DB 0. Không dùng `SELECT 2` như giải pháp cho lỗi Cluster.

### 6.3. Key prefix

Spring Cache có thể tạo key kiểu:

```text
products::42
```

khi code Java dùng:

```java
@Cacheable(cacheNames = "products", key = "#productId")
```

Tùy cấu hình prefix, serializer và cache manager, key Redis thực **không đơn giản là `"42"`**.

Một Redis Repository có thể dùng:

```text
people:<id>
```

hoặc keyspace được khai báo bởi entity, không phải key do bạn tự đoán.

Nếu CLI dùng tên key sai, việc value serializer đúng hay sai không liên quan.

### 6.4. Key đã hết hạn

```redis
TTL user:42
PTTL user:42
```

Giá trị đặc biệt thường gặp:

```text
-2: key không tồn tại
-1: key tồn tại nhưng không có TTL
>=0: key còn thời gian sống tương ứng
```

Nếu `GET` trả `(nil)` và `TTL` trả `-2`, điều đó xác nhận **key bytes được CLI hỏi không tồn tại tại thời điểm đó**. Nó chưa chứng minh key mà app tạo với serializer khác cũng không tồn tại.

### 6.5. Không dùng `KEYS *` bừa bãi trên production

`KEYS` quét keyspace có thể gây tác động không mong muốn trên dataset lớn. Với quyền phù hợp:

```redis
SCAN 0 MATCH product:* COUNT 100
```

là cách duyệt tăng dần hơn, nhưng cũng cần hiểu:

- `SCAN` có thể trả duplicate hoặc thay đổi khi keyspace đang biến động.
- `MATCH` làm việc trên **key bytes/pattern**, không tự giải Java serialized keys.
- Pattern `product:*` không chắc tìm được key có JDK-serialized prefix binary.
- `COUNT` là hint, không bảo đảm đúng 100 keys.
- Redis Cluster cần xem phạm vi node/primary phù hợp.
- Tên key có thể chứa PII; không xuất raw danh sách vào shared logs.

---

## 7. CLI thấy value binary: xử lý thế nào?

Giả sử:

```redis
GET user:42
```

trả nội dung escape khó đọc.

Nên phân tích theo thứ tự:

1. `TYPE user:42` có phải `string` không?
2. Ứng dụng dùng value serializer nào?
3. Key bytes trong app/CLI có giống nhau không?
4. Có dấu hiệu binary format đã biết (JDK header, gzip, custom prefix...) không?
5. Giá trị có được nén/mã hóa không?
6. Có thay đổi serializer giữa các phiên bản deployment không?
7. Có phải CLI terminal đang hiển thị UTF-8 sai không?
8. Có yêu cầu bảo mật khiến ta không được xem raw payload không?

### 7.1. Chế độ hiển thị của redis-cli

Các cách gọi:

```bash
redis-cli GET lab:message
redis-cli --raw GET lab:message
```

`--raw` thay đổi cách **in response**. Nó không chuyển object bytes thành Java object và không làm server decode JSON.

Với value binary, in raw bytes ra terminal có thể chứa control characters, gây hiển thị sai hoặc rủi ro với terminal/log. Trong lab, có thể chuyển output sang công cụ xem hex:

```bash
redis-cli --raw GET lab:binary | xxd -g 1
```

Lưu ý `redis-cli` có thể thêm dấu xuống dòng để hiển thị; output CLI trong pipeline không nên được coi là byte-for-byte bằng value gốc nếu chưa xác nhận. Với dữ liệu cần so sánh chính xác, ưu tiên đọc raw bytes qua Redis connection API trong test, không dựa trên định dạng stdout.

Không dùng những thao tác in hex/raw payload cho **secret thật trên production** vì hex cũng làm lộ đầy đủ dữ liệu có thể giải mã lại.

### 7.2. Java serialization header

Một Java Object Serialization stream thường bắt đầu:

```text
AC ED 00 05
```

Nếu thấy những bytes đó, đây là **gợi ý** rằng value được Java serialize. Nhưng cần kiểm tra:

```text
Value serializer của writer thực tế
Class type
serialVersionUID
Redis key đúng
Data format ở phiên bản writer trước
```

Không thể giải mã đúng chỉ bằng việc biết header nếu thiếu class/schema tương ứng.

### 7.3. JSON nhìn được trong CLI nhưng Java vẫn không đọc được

Ví dụ CLI hiển thị JSON hợp lệ:

```json
{"id":"p-42","name":"Laptop"}
```

Nhưng `redisTemplate.opsForValue().get("product:42")` ném exception.

Có thể là:

- Java đang dùng JDK deserializer cho value JSON.
- JSON typed serializer yêu cầu type metadata nhưng payload không có.
- Field/class name thay đổi.
- ObjectMapper có custom modules/constructors khác.
- JSON có schema V1 nhưng app kỳ vọng V2.
- Một field chứa số/enum/time format mà mapper mới không xử lý được.
- Generic `Object` được giải mã thành `Map`, rồi code cast sang `ProductDto`.
- Value là JSON String literal nhưng code mong JSON object.

**JSON syntax hợp lệ không bảo đảm Java type mapping hợp lệ.**

---

## 8. Mismatch giữa key serializer và value serializer: bảng nhận diện nhanh

| Tình huống | Trong Java | Trong CLI | Nghi vấn chính |
|---|---|---|---|
| Java đọc được, CLI `GET name` trả nil | Có object | `(nil)` | Key bytes/prefix/DB/host |
| Java đọc được, CLI thấy `\xac\xed...` | Object hợp lệ | Binary/escaped | JDK value serializer |
| Java đọc được, CLI thấy JSON `@class` | Object hợp lệ | JSON metadata | Generic typed JSON serializer |
| `StringRedisTemplate` đọc `null`, `RedisTemplate` đọc được | Template behavior khác | Có key | Key serializer khác |
| `GET` báo WRONGTYPE | App `opsForHash` hoặc Repository | `TYPE hash` | Redis data type mismatch |
| CLI `HGETALL` có fields lạ | App `opsForHash` đọc đúng | Binary field names/values | Hash serializers |
| Java báo JSON parse error, CLI thấy binary | Java lỗi | Binary payload | Value serializer không khớp |
| Java báo invalid class/type | Java lỗi | Dữ liệu có mặt | Old Java/schema serialization |
| CLI thấy JSON nhưng app `null` | Có thể khác key | Có JSON ở key đang hỏi | Key prefix/DB/serializer/transaction/race |
| App và CLI đều thấy key nhưng giá trị khác tại hai thời điểm | Kết quả khác | Value khác | Concurrency, TTL, replica lag, caching |
| Cache `@Cacheable` đọc được, RedisTemplate `GET` không | Khác abstractions | Có dữ liệu | Cache serializer/key prefix |
| Repository `findById` được, CLI `GET` lỗi | Entity được map | `WRONGTYPE` | Redis Hash, không phải Redis String |

Đây là bảng **định hướng chẩn đoán**, không phải chẩn đoán chắc chắn chỉ từ một triệu chứng.

---

## 9. So sánh raw key bytes từ Java

Cách chắc chắn để biết hai serializer tạo cùng key hay không là **so sánh bytes**, không so sánh Java String.

Ví dụ dùng Java 17+:

```java
import java.util.Arrays;
import java.util.HexFormat;

import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

public class KeySerializerComparison {

    public static void main(String[] args) {
        String logicalKey = "user:42";

        byte[] utf8Key =
            new StringRedisSerializer().serialize(logicalKey);

        byte[] jdkKey =
            new JdkSerializationRedisSerializer().serialize(logicalKey);

        System.out.println(
            "Equal bytes? " + Arrays.equals(utf8Key, jdkKey)
        );

        // Chỉ in hex trên dữ liệu giả trong test.
        System.out.println(
            "UTF-8: " + HexFormat.of().formatHex(utf8Key)
        );

        System.out.println(
            "JDK:   " + HexFormat.of().formatHex(jdkKey)
        );
    }
}
```

Kết quả `Arrays.equals` sẽ cho biết hai key có đồng nhất về bytes hay không. Với ví dụ này, hai serializer tạo biểu diễn khác nhau.

Không dùng code này để dump session tokens/PII trong production. Một chuỗi hex là biểu diễn có thể đảo ngược về bytes gốc, **không phải redaction**.

### 9.1. So sánh thực sự phải dùng serializer của bean được inject

Ví dụ trên dùng hai serializer mẫu để giải thích. Trong dự án thực tế, cần xác định serializer do chính code path đang dùng:

```java
RedisSerializer<?> configuredKeySerializer =
    redisTemplate.getKeySerializer();
```

Sau đó sử dụng serializer đó trong test có quyền truy cập đúng dữ liệu.

Nếu ứng dụng có nhiều beans:

```text
default redisTemplate
jsonRedisTemplate
stringRedisTemplate
cacheManager
reactiveTemplate
```

đừng lấy serializer từ bean A để kết luận bytes do bean B sinh ra.

### 9.2. So sánh bytes bằng unit test

Một test định hướng:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.StringRedisSerializer;

class RedisKeyFormatTest {

    private final StringRedisSerializer keySerializer =
        new StringRedisSerializer();

    @Test
    void keyFormatIsStable() {
        byte[] actual =
            keySerializer.serialize("product:v2:p-42");

        assertThat(actual).isEqualTo(
            "product:v2:p-42".getBytes(
                java.nio.charset.StandardCharsets.UTF_8
            )
        );
    }
}
```

Test này bảo vệ **wire format** của key tốt hơn việc chỉ kiểm tra `"product:v2:p-42".equals(...)` ở tầng Java.

---

## 10. Đọc Redis raw bytes qua RedisConnection

Để phân biệt lỗi serializer với dữ liệu lưu, có thể dùng low-level Redis connection trong integration test cô lập.

Ví dụ có key String:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public class RawRedisInspector {

    private final StringRedisTemplate redis;

    public RawRedisInspector(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public int rawValueLength(String key) {
        byte[] rawKey =
            key.getBytes(StandardCharsets.UTF_8);

        byte[] rawValue = redis.execute(
            (RedisCallback<byte[]>) connection ->
                connection.stringCommands().get(rawKey)
        );

        return rawValue == null ? -1 : rawValue.length;
    }
}
```

Ở đây callback dùng bytes key đã định nghĩa và lấy raw bytes của Redis String. Phương thức chỉ trả length, **không in raw value**.

Điều kiện:

- `rawKey` phải trùng chính xác với key bytes trên Redis.
- Key phải là Redis String; nếu là Hash/List/Set, `GET` sẽ gây lỗi `WRONGTYPE`.
- Nếu key writer dùng `JdkSerializationRedisSerializer`, đừng truyền UTF-8 key bytes như ví dụ; phải dùng đúng serializer của writer.
- API/callback có thể thay đổi theo Spring Data Redis version; dùng cách được hỗ trợ trong release đang chạy.

### 10.1. Vì sao cách này hữu ích?

Nó tách hai câu hỏi:

```text
(1) Redis có byte[] cho key bytes chính xác này không?
(2) Serializer Java có giải mã byte[] đó thành object được không?
```

Nếu (1) có bytes nhưng (2) thất bại, vấn đề có thể ở value serializer/schema. Nếu (1) không có bytes, quay lại key serializer/prefix/DB/TTL/endpoint.

### 10.2. Không dùng raw inspector như một admin API công khai

Một endpoint HTTP trả raw Redis bytes hoặc raw hex có thể làm lộ thông tin nghiêm trọng.

Nếu cần công cụ diagnostics, giới hạn:

```text
Môi trường test
Namespace test
Quyền vận hành
Không trả raw payload cho client công khai
Không ghi secrets vào centralized logs
Thời gian bật ngắn
```

---

## 11. Hash serializers: bốn bộ serializer không phải hai

Với một Redis Hash:

```java
redisTemplate.opsForHash().put(
    "user:42",
    "displayName",
    "Alice"
);
```

có nhiều thành phần:

```text
Redis top-level key:
    "user:42"           -> keySerializer

Hash field:
    "displayName"       -> hashKeySerializer

Hash field value:
    "Alice"             -> hashValueSerializer
```

Còn `valueSerializer` thường dùng cho những value operations khác như `opsForValue`, `opsForList`, `opsForSet`, tùy API.

### 11.1. Một Hash có thể có field names binary

Nếu `hashKeySerializer` dùng JDK serialization, CLI:

```redis
HGETALL user:42
```

có thể hiển thị field names khó đọc dù top-level key `user:42` là UTF-8.

Khi đó:

```redis
HGET user:42 displayName
```

có thể trả `(nil)` vì CLI gửi field name `"displayName"` dạng UTF-8, trong khi Java writer gửi field bytes theo JDK serialization.

### 11.2. Hash field value cũng có thể binary

Ví dụ:

```text
Top-level key: String serializer
Hash field:    String serializer
Hash value:    JDK serializer
```

CLI `HGET user:42 displayName` tìm được field nhưng trả binary.

Cần xem đúng `getHashValueSerializer()`, không chỉ `getValueSerializer()`.

### 11.3. Một mẫu cấu hình rõ ràng

Với Hash chỉ chứa các String:

```java
RedisTemplate<String, String> template =
    new RedisTemplate<>();

template.setConnectionFactory(connectionFactory);
template.setKeySerializer(
    new StringRedisSerializer()
);
template.setValueSerializer(
    new StringRedisSerializer()
);
template.setHashKeySerializer(
    new StringRedisSerializer()
);
template.setHashValueSerializer(
    new StringRedisSerializer()
);
template.afterPropertiesSet();
```

Đây là ví dụ cho một Hash String-only, không phải thiết lập phải dùng cho mọi Java object. Nếu Hash value là DTO, cần serializer phù hợp.

### 11.4. Kiểm tra Redis data type trước khi chọn command

```redis
TYPE user:42
```

Nếu là `hash`:

```redis
HGETALL user:42
HLEN user:42
```

Không dùng `GET` trên Hash. Nếu là `string`:

```redis
GET user:42
STRLEN user:42
```

Không dùng `HGETALL` trên String.

`WRONGTYPE` là lỗi **chọn Redis command không phù hợp data type**, khác với lỗi JSON/JDK deserialization.

---

## 12. Spring Data Redis Repository thường lưu entity thành Redis Hash

Với Redis Repository:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("people")
public class Person {

    @Id
    private String id;

    private String name;

    // constructors/getters/setters...
}
```

Spring Data Redis Repository có thể lưu entity bằng Redis Hash thông qua mapping converter, không phải một JSON String nguyên object.

Ở mức ý tưởng:

```text
Key:
    people:<id>

Hash fields:
    _class
    id
    name
```

Tên key, metadata fields, conversion rules và các key phụ thuộc Spring Data Redis mapping version/configuration.

### 12.1. Vì sao GET lỗi?

Người vận hành thử:

```redis
GET people:42
```

và nhận:

```text
WRONGTYPE Operation against a key holding the wrong kind of value
```

Khi đó:

```redis
TYPE people:42
```

có thể trả:

```text
hash
```

Lệnh phù hợp để kiểm tra data type là:

```redis
HGETALL people:42
```

Nhưng **đừng giả định mọi field đọc được như JSON text**. Custom converters hoặc mapping có thể lưu bytes không phải UTF-8.

### 12.2. Repository không dùng cùng đường serializer với opsForValue

Một sai lầm:

> “Tôi đã đặt `redisTemplate.setValueSerializer(JSON)`, vậy toàn bộ Redis Repository sẽ ghi JSON String.”

Không chắc. Redis Repository dùng mapping/conversion layer riêng để ánh xạ entity sang Hash và tạo index/TTL metadata theo thiết kế của nó.

Muốn xác định wire format của Repository, phải xem:

```text
RedisKeyValueAdapter
RedisMappingContext
MappingRedisConverter
Custom converters
@RedisHash / @Indexed / @TimeToLive
Keyspace configuration
```

theo Spring Data Redis version đang sử dụng.

### 12.3. Secondary index và metadata

`@Indexed` có thể tạo key hoặc thành viên Set phụ. Nếu nhìn trong CLI và thấy nhiều key liên quan một entity, đó không nhất thiết là dữ liệu trùng do serializer.

Cần biết entity key, index key, TTL/shadow-copy behavior và các metadata khác; không xóa những key lạ trước khi hiểu vai trò của chúng.

### 12.4. Kiểm tra vòng đời entity

Một integration test nên:

```text
repository.save(person)
repository.findById(id)
repository.existsById(id)
Query indexed field nếu dùng
TTL nếu được cấu hình
repository.deleteById(id)
```

và đối chiếu Redis `TYPE`/fields bằng dữ liệu giả. Việc `findById` đúng là một bước, nhưng không chứng minh mọi index và TTL đều hợp lệ sau đổi serializer.

---

## 13. Spring Cache có serializer và key prefix riêng

Một ứng dụng:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductDto getProduct(String productId) {
    return productService.load(productId);
}
```

có thể dùng `RedisCacheManager`, không nhất thiết cùng bean `RedisTemplate` mà bạn cấu hình thủ công.

Một key Redis có thể trông như:

```text
products::p-42
```

nhưng format/prefix có thể được tùy chỉnh. Khi CLI chạy:

```redis
GET p-42
```

nhận `(nil)` là điều dễ hiểu nếu key thật là `products::p-42`.

### 13.1. Giá trị cache có thể là JDK serialized bytes

Trong những cấu hình Spring Data Redis phổ biến, `RedisCacheConfiguration` mặc định dùng String serializer cho cache keys và Java serialization cho cache values nếu chưa override. **Không dựa vào mặc định này mà bỏ qua kiểm tra actual CacheManager configuration.**

Tùy version và project, cache values có thể dùng JSON, JDK hoặc serializer riêng.

Điều cần kiểm tra là cấu hình của:

```text
RedisCacheManager
RedisCacheConfiguration
Key serialization pair
Value serialization pair
Cache-specific configuration
Null caching behavior
Key prefix
TTL
```

### 13.2. Cấu hình cache JSON minh họa

Theo những phiên bản Spring Data Redis có `GenericJackson2JsonRedisSerializer`:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;

@Configuration
public class RedisCacheConfig {

    @Bean
    RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10))
                .serializeValuesWith(
                    RedisSerializationContext
                        .SerializationPair
                        .fromSerializer(
                            new GenericJackson2JsonRedisSerializer()
                        )
                );

        return RedisCacheManager
            .builder(connectionFactory)
            .cacheDefaults(defaults)
            .build();
    }
}
```

**Lưu ý:** Tên class/API có thể khác theo thế hệ Jackson/Spring Data Redis. Kiểm tra tài liệu version cụ thể; đừng copy một ví dụ phiên bản khác vào project mà không xác minh. Nếu không cần polymorphic type metadata, có thể chọn typed JSON mapping có schema rõ hơn.

### 13.3. Thay serializer cache giữa hai deployment

Giả sử:

```text
App v1:
    products::p-42 = JDK-serialized ProductDto

App v2:
    products::p-42 = JSON ProductDto
```

App v2 đọc old cache entry bằng JSON serializer có thể lỗi. App v1 đọc new entry bằng JDK serializer cũng có thể lỗi.

Đây là **data format migration**, không phải lỗi của redis-cli.

Với cache tái tạo được, có thể chuyển key prefix/version namespace có kế hoạch:

```text
products:v1::p-42
products:v2::p-42
```

Nhưng phải chuẩn bị cold cache, cache stampede, memory tạm và database load. Nếu Redis chứa state không tái tạo được, không được xóa data để “làm sạch cache” theo cách này.

### 13.4. Cache null marker

Spring Cache có thể dùng một biểu diễn đặc biệt cho cached `null` tùy cấu hình. Khi đổi serializer, old null marker có thể không tương thích.

Nếu CLI thấy một value lạ không giống DTO, đó có thể là cache null representation; cần xem CacheManager config, không khẳng định dữ liệu hỏng.

---

## 14. RedisTemplate và StringRedisTemplate có thể đọc cùng key khác nhau như thế nào?

Giả sử một ứng dụng có hai beans:

```text
A: StringRedisTemplate
B: RedisTemplate<String,Object> dùng JDK key serializer
```

Thao tác:

```java
A.opsForValue().set("lab:key", "from-A");
B.opsForValue().set("lab:key", "from-B");
```

Nếu B thực sự dùng JDK key serializer, Redis có thể có **hai key khác bytes** cho cùng logical Java String `"lab:key"`.

```text
Redis:
    UTF-8 key "lab:key"       -> value from-A
    JDK bytes of "lab:key"    -> value from-B
```

CLI:

```redis
GET lab:key
```

nhìn thấy value từ A, nhưng đọc qua B có thể trả value từ B.

Như vậy Java/CLI “khác kết quả” không phải do Redis trả dữ liệu bất nhất mà do **hai client đang hỏi hai key khác nhau**.

### 14.1. Kiểm tra hai bộ key bytes

Trong integration test:

```java
byte[] aKey =
    new StringRedisSerializer().serialize("lab:key");

byte[] bKey =
    new JdkSerializationRedisSerializer().serialize("lab:key");
```

Nếu bytes khác nhau, chúng là hai Redis key names độc lập.

### 14.2. Thử nghiệm chỉ dùng dữ liệu giả

Tình huống này nên được tái hiện ở Redis test với namespace `lab:`. Không cố tình tạo thêm các key có serializer sai trong Redis production để xem điều gì xảy ra.

---

## 15. Sai Redis database, host hoặc Cluster node có thể trông giống lỗi serializer

Trước khi nghi ngờ serializer, xác minh hai công cụ cùng nói chuyện với **cùng nơi**.

### 15.1. Host và port

```text
Spring:
    redis.prod.internal:6379

CLI:
    127.0.0.1:6379
```

Có thể CLI đang nói với Redis local, không phải production Redis.

Trong Kubernetes:

```text
localhost bên trong container app
    !=
localhost trên máy developer
```

Một cổng port-forward cũng có thể đi tới service/namespace khác.

### 15.2. Logical database

Standalone Redis có thể có nhiều logical DB indexes:

```redis
SELECT 0
SELECT 2
```

Spring `LettuceConnectionFactory` có thể được cấu hình DB 2 trong khi CLI mặc định DB 0.

Không suy rằng `(nil)` là key serializer mismatch khi chưa kiểm tra database selection.

### 15.3. Redis Cluster

Redis Cluster phân key theo hash slots. Một CLI không bật cluster redirection hoặc kết nối tới node không sở hữu slot có thể nhận:

```text
MOVED <slot> <host>:<port>
```

Dùng khả năng cluster-aware phù hợp của CLI/driver, ví dụ `redis-cli -c` trong môi trường được phép.

Cần hiểu:

- Một Redis Cluster không có nhiều logical DBs như standalone.
- Key bytes ảnh hưởng trực tiếp hash slot.
- Thay key serializer có thể làm slot đổi.
- Pattern scanning trên một node không phải toàn bộ cluster.
- Client và CLI có thể nhìn hai versions của key khác nhau nếu replication/failover/read routing liên quan.

### 15.4. Replica lag

Nếu ứng dụng đọc từ primary còn CLI đọc replica hoặc ngược lại, giá trị có thể khác trong khoảng replication lag. Đây là vấn đề consistency/routing, **không phải serializer**.

Một diagnosis tốt phải phân biệt:

```text
same key bytes?
same Redis node/primary/replica?
same point in time?
same serializer?
```

---

## 16. Unicode, charset và terminal encoding

Dữ liệu tiếng Việt đặc biệt hữu ích để phát hiện nhầm lẫn giữa ký tự và bytes.

Ví dụ:

```java
String text = "Hà Nội";
```

Nếu dùng UTF-8, một số ký tự dấu chiếm nhiều bytes. Nếu app writer dùng UTF-8 nhưng CLI terminal hoặc reader dùng encoding khác, kết quả có thể trông sai.

### 16.1. Ba vấn đề encoding khác nhau

```text
Java String -> Redis bytes:
    Do serializer/charset quyết định.

Redis bytes -> redis-cli display:
    Do cách CLI hiển thị/escape và terminal quyết định.

Redis bytes -> Java String:
    Do deserializer/charset quyết định.
```

Cần kiểm tra từng bước, không suy ngay “Redis tự chuyển đổi UTF-8 sai”.

### 16.2. Replacement character

Nếu một reader cố decode bytes không hợp lệ thành UTF-8, nó có thể tạo ký tự replacement `�` hoặc ném lỗi tùy decoder policy.

Sau khi chuỗi đã chứa replacement characters, thông tin bytes gốc có thể đã bị mất ở tầng hiển thị. Nếu cần điều tra binary format, lấy **raw byte[]**, không dựa vào một String đã decode sai.

### 16.3. Không lấy `String.length()` làm bytes lưu Redis

```java
String value = "Tiếng Việt";
int chars = value.length();
int bytes =
    value.getBytes(StandardCharsets.UTF_8).length;
```

`chars` và `bytes` có thể khác. Để đo payload thật, dùng `serializer.serialize(value).length` khi serializer đang dùng được xác định.

### 16.4. Byte Order Mark (BOM) và charset không đồng nhất

Một JSON file hoặc String được tạo từ nguồn khác có thể chứa UTF-8 BOM hoặc dùng encoding khác; Java JSON parser và CLI có thể xử lý khác nhau.

Không sửa dữ liệu bằng cách `.trim()` mọi value một cách mù quáng; làm vậy có thể thay đổi hash/signature hoặc nội dung nghiệp vụ.

---

## 17. JSON type metadata: tại sao CLI thấy @class mà Java không?

Một generic JSON serializer có thể lưu thông tin kiểu Java để deserialize polymorphic object.

Ví dụ value dạng:

```json
{
  "@class": "com.example.catalog.ProductDto",
  "id": "p-42",
  "name": "Laptop"
}
```

CLI thấy cả JSON này; Java deserializer có thể tạo lại `ProductDto`.

### 17.1. Metadata không phải field nghiệp vụ

`@class` hoặc type hint có thể là thông tin phục vụ serializer. Không tự trả nguyên Redis JSON cho API công khai nếu nó chứa tên package/lớp nội bộ hoặc metadata không thuộc contract API.

### 17.2. Đổi package Java có thể làm dữ liệu cũ không đọc được

Nếu class đổi:

```text
com.example.catalog.ProductDto
    ->
com.example.product.ProductDto
```

old JSON type hint có thể trỏ tới class không còn tồn tại.

Kết quả Java đọc lỗi dù CLI JSON vẫn hợp lệ.

### 17.3. Không sửa bằng cách bật default typing không kiểm soát

Việc deserialize polymorphic types từ dữ liệu không đáng tin có thể tạo rủi ro bảo mật. Cần lựa chọn:

- DTO schema ổn định.
- Explicit type mapping.
- Allowlist/validator cho polymorphic types.
- Versioned data format.
- Reader migration cho old type hints.

Không nhận mọi Java class name từ Redis như một instruction để instantiate object nếu dữ liệu có thể bị tác động bởi đối tượng không đáng tin.

---

## 18. Compression/encryption làm value khác biệt dù serializer logic đúng

Một ứng dụng có thể dùng pipeline:

```text
ProductDto
    |
    v
JSON serialize
    |
    v
gzip compress
    |
    v
encrypt
    |
    v
Redis SET bytes
```

Khi đó:

```redis
GET product:42
```

trả binary ciphertext, không phải JSON.

Java đọc:

```text
Redis bytes
    |
    v
decrypt
    |
    v
decompress
    |
    v
JSON deserialize
    |
    v
ProductDto
```

### 18.1. Vì sao không thể chỉ dùng CLI GET rồi JSON.parse?

Vì Redis value đang ở **sau các bước compress/encrypt**. CLI không có key giải mã, thuật toán, nonce, version header hoặc schema.

### 18.2. Không log plaintext để debug

Nếu phải kiểm tra codec:

- Dùng dữ liệu giả trong môi trường test.
- So sánh bytes lengths, codec version và round-trip asserts.
- Dùng test vectors không chứa secret.
- Không ghi encryption key hoặc plaintext production vào logs.
- Không đăng ciphertext có thể chứa thông tin nhạy cảm lên diễn đàn/ticket công khai.

### 18.3. Encryption và cache key

Nếu ứng dụng mã hóa cả key, CLI không thể tìm bằng logical key UTF-8. Tuy nhiên, mã hóa key có thể ảnh hưởng deterministic lookup/Cluster routing, vì thế phải hiểu contract của custom key codec.

---

## 19. `DUMP` của Redis không phải Java serializer

Redis có lệnh:

```redis
DUMP key
```

trả một biểu diễn binary serialization nội bộ của **Redis value** (liên quan cơ chế RDB), có thể dùng với các Redis commands/công cụ tương ứng theo điều kiện áp dụng.

Đừng nhầm:

```text
Redis DUMP serialization
    !=
Java JdkSerializationRedisSerializer
```

Ngay cả khi một Redis String chứa plain text `"hello"`, kết quả `DUMP` có thể là binary format Redis, không phải bytes ASCII của `"hello"`.

Vì vậy, để xác định bytes mà Spring đã ghi làm Redis String value, dùng `GET` raw qua Redis connection; **không dùng DUMP và kỳ vọng đó là payload serializer gốc**.

### 19.1. DUMP/RESTORE có thể liên quan version

Khi migrate giữa Redis Server versions, format Redis serialization và compatibility cần kiểm tra theo official documentation. Nó cũng không thay việc migrate JSON/JDK schema của ứng dụng.

### 19.2. Cẩn trọng khi chia sẻ DUMP output

Một Redis DUMP có thể chứa toàn bộ value kể cả thông tin nhạy cảm. Binary không có nghĩa an toàn để đính kèm ticket.

---

## 20. RedisConnectionFactory: nơi xác định connection context

Một Spring Data Redis client đi qua:

```java
RedisConnectionFactory
```

với implementation phù hợp như `LettuceConnectionFactory` hoặc `JedisConnectionFactory`.

Cần xác định:

```text
Host/port
Standalone/Sentinel/Cluster
Database index nếu standalone
TLS
ACL user
Read-from setting/replica reads nếu có
Timeout
Client connection identity
```

Một `StringRedisTemplate` và một `RedisTemplate` có thể dùng **hai connection factories khác nhau** nếu project khai báo custom beans.

Vì vậy:

```java
redisTemplate.getConnectionFactory()
```

là một đầu mối xác minh wiring. Tuy nhiên, đừng in nguyên configuration object nếu `toString()` có thể chứa secret hoặc endpoint nhạy cảm.

### 20.1. Boot auto-configuration và bean overrides

Spring Boot có thể tạo template mặc định theo auto-configuration, nhưng custom bean với tên/loại phù hợp có thể thay thế hoặc thêm template khác.

Nếu một service được inject bean có qualifier:

```java
@Qualifier("secondaryRedisTemplate")
```

nó có thể truy cập Redis khác với bean được người vận hành nghĩ là mặc định.

### 20.2. Quan sát actual bean

Trong code test (không log secrets), xem:

```text
Bean name
Template class
ConnectionFactory class
Serializer class
CacheManager class
```

Sau đó đối chiếu với config chủ động của ứng dụng.

Không suy từ file `application.yml` duy nhất khi project có profile, environment variables, config server và custom bean definitions.

---

## 21. Phân biệt một bài toán đọc khác kết quả do concurrency

Ngay cả khi:

```text
Same key bytes
Same Redis instance
Same Redis type
Same serializer
```

hai lần đọc vẫn có thể cho giá trị khác nếu data đã thay đổi giữa các thời điểm:

```text
t0: Java GET -> status=PENDING
t1: Writer SET -> status=PAID
t2: redis-cli GET -> status=PAID
```

Không nên dành nhiều giờ debug JSON serializer trong tình huống read/write timing khác nhau.

### 21.1. Lỗi do TTL

```text
t0: app reads key
t1: key expires
t2: CLI GET returns nil
```

Nếu key có TTL ngắn, chỉ vài giây chênh có thể tạo hai quan sát khác nhau.

### 21.2. Lỗi do key bị recreate

Một key được `DEL` rồi `SET` lại có value mới. Dù tên key giữ nguyên, nội dung và TTL có thể thay đổi.

### 21.3. Transaction/pipeline

Một `RedisTemplate` đang tham gia Redis transaction có thể queue commands tới `EXEC`; reply tại thời điểm code gọi một method có thể có semantics khác lời gọi ngoài transaction. Không quy mọi `null` trong transaction cho serializer.

### 21.4. Local cache và framework cache

Nếu ứng dụng có thêm Caffeine/local cache trước Redis, Java method có thể trả dữ liệu từ cache local chứ không gọi Redis. CLI đang xem Redis live; hai kết quả có thể khác vì cache nhiều tầng.

Hãy xác định **application read path thực tế**, không chỉ tên field `redisTemplate`.

---

## 22. Quy trình chẩn đoán từng bước, không sửa dữ liệu

Khi người dùng báo:

> “Trong redis-cli tôi thấy X, nhưng Java trả Y.”

Làm theo thứ tự sau.

### Bước 1 — Ghi biểu hiện chính xác

Ví dụ:

```text
Java code path:
    productCache.get("p-42")

Java result:
    ProductDto(...)

CLI:
    GET product:p-42 -> nil
```

Cần phân biệt `(nil)`, `WRONGTYPE`, binary output, JSON khác schema hay Java exception.

### Bước 2 — Xác minh nơi kết nối

Xác định:

```text
Redis instance/endpoint
Logical DB
Cluster/Sentinel topology
Read-from primary/replica
Environment/profile
TLS/auth user
```

Không chia sẻ password trong report.

### Bước 3 — Xác định abstraction

Đang dùng:

```text
StringRedisTemplate?
RedisTemplate<K,V>?
ReactiveRedisTemplate?
Spring Cache RedisCacheManager?
Redis Repository?
Low-level RedisConnection?
Custom codec?
```

### Bước 4 — Lấy key expression thực sự

Kiểm tra:

```text
Key generator
Cache name/prefix
Repository keyspace
Tenant prefix
Hash tag
Schema/version prefix
```

**Không đoán key theo tên method.**

### Bước 5 — Kiểm tra serializer theo từng vị trí

```text
Key serializer
Value serializer
Hash key serializer
Hash value serializer
Cache key/value serialization
Repository converter
Reactive SerializationContext
```

### Bước 6 — So sánh key bytes, không chỉ key String

Lấy một logical key giả và chạy serializer thực tế trong test:

```text
expected raw bytes
actual bytes khi gửi Redis
```

Nếu có quyền và đúng key type, dùng low-level callback để truy vấn raw bytes tương ứng.

### Bước 7 — Kiểm tra Redis TYPE

```redis
TYPE <safe-test-key>
```

Chọn `GET`/`HGETALL`/`LRANGE`/... theo đúng type.

### Bước 8 — Kiểm tra TTL và trạng thái hiện có

```redis
EXISTS <safe-test-key>
TTL <safe-test-key>
```

Nếu key chưa tồn tại hoặc expired, không thể kết luận value serializer từ nó.

### Bước 9 — Tách raw bytes và decode

Trong test:

```text
Redis has raw value bytes?
    |
    +-- Không -> kiểm tra key/DB/TTL/host/race.
    |
    +-- Có -> thử đúng deserializer của writer.
                  |
                  +-- Thành công -> CLI display khác do format.
                  |
                  +-- Thất bại -> serializer/schema/version mismatch.
```

### Bước 10 — Đọc cấu hình và phiên bản writer cũ

Một key có thể được writer version cũ tạo, trong khi phiên bản mới đã đổi serializer.

Tìm:

```text
Artifact version của writer
Serializer version/config
Java class/schema
Data format header/version
ObjectMapper settings
```

### Bước 11 — Lập giải pháp ít xâm lấn

Nếu chỉ debug CLI hiển thị lạ: **không cần sửa data**.

Nếu dữ liệu cache tái tạo được và muốn đổi format: dùng namespace versioned/cold-cache plan.

Nếu là state quan trọng: cần migration, rollback và restore test có kiểm soát.

### Bước 12 — Viết integration test phòng ngừa

Test dữ liệu do writer cũ tạo → reader mới giải mã; sau đó triển khai canary và quan sát serializer errors/cache hit rate.

---

## 23. Sơ đồ quyết định chẩn đoán nhanh

```text
Java và redis-cli khác kết quả
               |
               v
    Cùng Redis endpoint/DB?
          /          \
        Không         Có
         |             |
    Sửa context        v
                  CLI key đúng bytes?
                    /         \
                  Không        Có
                   |            |
             Key serializer     v
             /prefix khác    TYPE key?
                               |
                 +-------------+--------------+
                 |                            |
               string                        hash/...
                 |                            |
                 v                            v
           Value bytes?                 Dùng command đúng
             /      \                   Hash serializers?
           Không     Có                       |
            |        |                        v
        TTL/race     Decode theo writer serializer
        /eviction     |
                     +-------------------+
                     |                   |
                  Thành công           Thất bại
                     |                   |
              CLI display khác      Schema/format/
              do binary/JSON        version mismatch
```

Sơ đồ chỉ là định hướng. Redis Cluster redirects, replicas và nhiều tầng cache có thể khiến chẩn đoán cần thêm bước.

---

## 24. Kiểm chứng trực tiếp bằng round-trip test

Một bài test dùng `StringRedisTemplate`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class StringRedisRoundTripIT {

    @Autowired
    StringRedisTemplate redis;

    @Test
    void cliReadableStringRoundTrip() {
        String key = "lab:string:42";
        String expected = "Xin chào";

        redis.opsForValue().set(key, expected);

        assertThat(
            redis.opsForValue().get(key)
        ).isEqualTo(expected);
    }
}
```

Trong Redis test đúng DB:

```redis
GET lab:string:42
```

CLI nên có thể đọc được văn bản qua terminal có UTF-8 phù hợp.

### 24.1. Round-trip cùng serializer chưa đủ

Nếu writer và reader trong cùng test đều dùng một **serializer sai với production contract**, test vẫn pass.

Cần thêm:

```text
Writer V1 -> Reader V2
Reader V1 -> Writer V2 nếu rollback cần
CLI raw type/key format tests
CacheManager key prefix tests
Repository mapping tests
```

### 24.2. Test trên Redis thật

Mock `RedisTemplate` chỉ chứng minh logic Java mock. Nó không xác minh raw bytes đã ghi, Redis types, TTL, Cluster routing hoặc serializer behavior thực tế.

Nên sử dụng Testcontainers hoặc một Redis integration environment riêng.

---

## 25. Một ví dụ đọc JSON bằng StringRedisTemplate, rõ hợp đồng dữ liệu

Nếu muốn Redis CLI đọc JSON trực tiếp và app chỉ lưu DTO thuộc một schema được kiểm soát, có thể dùng `StringRedisTemplate` cùng Jackson `ObjectMapper`.

```java
package com.example.product;

import java.time.Duration;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductJsonCache {

    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper;

    public ProductJsonCache(
            StringRedisTemplate redis,
            ObjectMapper objectMapper) {
        this.redis = redis;
        this.objectMapper = objectMapper;
    }

    public void put(ProductDto product)
            throws JsonProcessingException {

        String key = "product:v2:" + product.id();
        String json = objectMapper.writeValueAsString(product);

        redis.opsForValue().set(
            key,
            json,
            Duration.ofMinutes(10)
        );
    }

    public ProductDto get(String productId)
            throws JsonProcessingException {

        String key = "product:v2:" + productId;
        String json = redis.opsForValue().get(key);

        if (json == null) {
            return null;
        }

        return objectMapper.readValue(json, ProductDto.class);
    }

    public record ProductDto(
        String id,
        String name,
        long priceInCents
    ) {}
}
```

Trong Redis test:

```redis
GET product:v2:p-42
```

sẽ trả JSON String theo cấu hình `ObjectMapper`, không phải JDK serialized bytes.

### 25.1. Tại sao chọn v2 namespace?

`product:v2:` giúp tách contract JSON mới khỏi những key có thể đã lưu bằng serializer khác dưới prefix cũ.

Nó không tự migrate dữ liệu: app mới cần load lại từ source-of-truth khi miss, hoặc phải có migration theo yêu cầu nghiệp vụ.

### 25.2. DTO chứa dữ liệu không công khai?

Nếu object có trường nhạy cảm, JSON trong CLI dễ đọc cũng đồng nghĩa người có quyền xem Redis key có thể đọc nội dung ấy. **Dễ debug không phải mục tiêu cao hơn bảo mật.**

Nếu cần bảo vệ dữ liệu, xem encryption, ACL, key management và tối thiểu hóa thông tin lưu cache. Không tự chọn String JSON chỉ vì muốn terminal nhìn rõ.

---

## 26. Generic JSON serializer và typed JSON serializer

### 26.1. Generic

Một generic serializer có thể chứa type metadata để biết class nào khi deserialize thành `Object`.

Ưu điểm:

- Một template lưu nhiều kiểu object.
- Có thể round-trip polymorphic data nếu cấu hình tương thích.

Đánh đổi:

- Metadata làm payload lớn hơn.
- Class/package changes gây migration risk.
- Polymorphic deserialization đòi hỏi bảo mật.
- Redis CLI hiển thị metadata trông “lạ”.

### 26.2. Typed

Một typed serializer biết trước target class:

```text
ProductDto
```

Ưu điểm:

- Có thể không cần type metadata class name trong payload.
- Data contract rõ hơn.
- Dễ version hóa schema.

Đánh đổi:

- Không thể tùy tiện lưu mọi type vào cùng template serializer.
- Vẫn cần quản lý schema evolution.
- API Java serializer cụ thể thay đổi theo Spring Data Redis/Jackson version.

### 26.3. Không trộn JSON của nhiều serializer vô ý

Hai serializer cùng tạo JSON chưa chắc có wire format giống nhau:

```text
Serializer A:
    {"id":"42","name":"Alice"}

Serializer B:
    {"@class":"...","id":"42","name":"Alice"}

Serializer C:
    ["com.example.Person",{"id":"42","name":"Alice"}]
```

Đây là các dạng minh họa. Không suy JSON nào là chính xác cho một class thư viện nếu chưa xem actual serializer config.

### 26.4. Schema version hữu ích hơn đoán class qua format

Có thể dùng:

```json
{
  "schemaVersion": 2,
  "id": "p-42",
  "name": "Laptop"
}
```

Một reader có thể chọn decoder/migrator theo `schemaVersion` rõ ràng. Nếu dữ liệu có thể bị điều khiển bởi nguồn không tin cậy, cần validate schema và tránh giải mã vào những Java types không được phép.

---

## 27. ReactiveRedisTemplate cũng có serialization context

Trong reactive API:

```java
ReactiveRedisTemplate<K, V>
```

việc chuyển key/value sang bytes có thể dựa trên `RedisSerializationContext<K,V>`.

Không mặc định:

```text
ReactiveStringRedisTemplate
    ==
ReactiveRedisTemplate<String,Object>
```

về wire format.

### 27.1. ReactiveStringRedisTemplate

Thường phục vụ String keys và String values, tương tự mục tiêu của `StringRedisTemplate`, nhưng API trả `Mono`/`Flux` thay vì synchronous values.

### 27.2. Khi debug reactive, chú ý lazy subscription

Ví dụ:

```java
Mono<String> result =
    reactiveStringRedisTemplate.opsForValue().get("lab:key");
```

Tạo `Mono` không nhất thiết gửi lệnh ngay. Nếu bạn kiểm tra CLI trước khi `Mono` được subscribe, có thể tưởng rằng app đã ghi/đọc nhưng command chưa thực thi.

Một pipeline `.retryWhen(...)` cũng có thể gọi Redis lại khi lỗi; cần phân biệt retry với serializer mismatch.

### 27.3. Không block event-loop để xem dữ liệu

Không dùng `.block()` tùy tiện trong WebFlux request thread để debug. Nó có thể gây performance/deadlock issues tùy context.

Nên dùng integration test hoặc logging metadata an toàn trong reactive chain.

### 27.4. Cấu hình codec cần nhất quán

Nếu blocking template dùng String/JSON nhưng reactive template dùng String/JDK, cùng key có thể gây decode mismatch.

Đảm bảo serializers của hai đường truy cập có cùng data contract khi cần chia sẻ Redis keys.

---

## 28. Redis Streams: field/value serializers cũng tạo khác biệt

Một application có thể ghi Stream record:

```text
XADD orders:events * eventId evt-1 type CREATED payload ...
```

`redis-cli XRANGE` hiển thị raw Stream fields/values theo cách CLI, trong khi Spring Data Redis mapping có thể tạo `MapRecord` hoặc `ObjectRecord` và deserialize dữ liệu thành Java object.

### 28.1. Đừng lấy StringRedisTemplate serializer làm chuẩn cho Stream mapper

Stream API có các cách mapping/serialization riêng theo `StreamOperations`, `StreamReceiver`, `StreamMessageListenerContainer` và `RedisSerializer`/conversion cấu hình.

Cần xác định:

```text
Stream key
Record ID
Field names
Field value bytes
Object mapping
Target Java type
```

### 28.2. Một Stream record có thể chứa Hash-style fields

Trong Redis Streams, record fields/values là dãy bytes với ngữ nghĩa riêng. Không mặc định entire object nằm trong một JSON String field; một mapper có thể tách object thành nhiều field.

Nếu CLI `XRANGE` có một số field binary, phải kiểm tra mapper/serializer cụ thể.

### 28.3. Consumer error không chứng minh Stream data hỏng

Nếu producer V1 và consumer V2 dùng schema khác nhau, consumer có thể deserialize lỗi; Stream entry vẫn tồn tại và có thể đọc qua decoder V1.

Đừng `XDEL` hoặc `XTRIM` production messages chỉ vì Java deserializer mới không hiểu chúng.

### 28.4. Khi schema thay đổi

Sử dụng:

```text
eventId
eventType
schemaVersion
payload
```

hoặc mapping contract tương đương và giữ compatibility trong thời gian các old records còn cần xử lý.

---

## 29. Pub/Sub: redis-cli subscribe thấy text, ứng dụng thấy object hoặc ngược lại

CLI:

```redis
SUBSCRIBE lab:events
```

có thể nhận payload text từ một Spring publisher. Nhưng khi publisher serialize object thành binary, CLI sẽ thấy bytes khó đọc.

Trong Spring:

```java
redisTemplate.convertAndSend(
    "lab:events",
    eventObject
);
```

cách serialize message phụ thuộc RedisTemplate/configuration.

### 29.1. Channel và payload cũng có serializer

Nếu publisher/subscriber dùng channel/topic encoding khác nhau, có thể xảy ra tình huống:

```text
Spring listener subscribed logical channel A
CLI SUBSCRIBE literal channel A
```

nhưng actual bytes/format không trùng như kỳ vọng.

Trước khi quy cho Pub/Sub lỗi, kiểm tra String topic/channel encoding và message serializer.

### 29.2. Pub/Sub không lưu lịch sử message

Nếu CLI subscribe sau khi publisher đã publish, sẽ không nhận lại message cũ theo Redis Pub/Sub thông thường. Đây là đặc tính delivery, không phải lỗi serializer.

### 29.3. Không dùng MONITOR để dump payload production

`MONITOR` có thể lộ command arguments chứa token/PII. Để xác định Pub/Sub hoạt động, dùng metrics về publish/receive count, listener health và event IDs giả trong môi trường test, thay vì ghi nguyên message content.

---

## 30. Các lỗi Java thường gặp khi serializer không tương thích

### 30.1. SerializationException

Một nhóm lỗi phổ biến trong Spring Data Redis khi không serialize/deserialize được dữ liệu. Xem cause chain trong môi trường log bảo mật phù hợp, tránh dump raw value.

### 30.2. StreamCorruptedException

Có thể phát sinh khi Java ObjectInputStream đọc bytes không phải format Java serialization mong đợi.

Ví dụ JSON UTF-8 bắt đầu `{` nhưng Java deserializer mong Java stream header.

### 30.3. InvalidClassException

Có thể do serialVersionUID hoặc class schema không tương thích đối với JDK serialization.

### 30.4. ClassNotFoundException

Có thể xảy ra khi data cũ tham chiếu Java class/package không còn trong runtime mới.

### 30.5. JsonMappingException / MismatchedInputException

Có thể do payload JSON có shape/type khác đối tượng đích hoặc custom mapper settings không phù hợp.

### 30.6. ClassCastException

Deserializer trả `Map` hoặc một object khác class mà code cố cast, ví dụ:

```java
ProductDto product =
    (ProductDto) template.opsForValue().get(key);
```

Nếu thực tế trả `LinkedHashMap`, sẽ lỗi cast.

### 30.7. WRONGTYPE

Là Redis error khi command type không phù hợp, ví dụ `GET` trên Hash. Đây không phải Java object deserialization exception dù cuối cùng có thể được Spring Data Redis chuyển thành exception trong Java.

### 30.8. NPE vì null

Nếu key bytes không tồn tại, Spring có thể trả `null`; code gọi method trên `null` dẫn đến `NullPointerException`.

Cần phân biệt:

```text
Missing key
    !=
Value serialized null marker
    !=
Deserialization error
```

Không coi NPE là bằng chứng serializer hỏng khi chưa kiểm tra raw key presence.

---

## 31. Serializer có thể thay đổi sau nâng cấp ứng dụng

Một service đã chạy nhiều tháng:

```text
App v1 -> JDK serializer
```

rồi deploy:

```text
App v2 -> JSON serializer
```

Redis vẫn chứa key/value cũ cho tới khi chúng được ghi lại hoặc hết TTL.

Tình huống mixed data:

```text
product:1 -> JDK bytes
product:2 -> JSON bytes
product:3 -> JDK bytes
product:4 -> JSON bytes
```

Nếu không có format discriminator/namespace, code mới khó biết key nào cần decoder nào.

### 31.1. Không đồng nhất việc đổi dependency với tự migrate dữ liệu

Một bản Spring Data Redis/driver mới không tự chuyển mọi JDK serialized value cũ thành JSON.

Cần:

- Backward reader.
- Schema version.
- Versioned namespace.
- Batch migration có checkpoint.
- Cache invalidation khi dữ liệu tái tạo được.
- Write freeze/reconciliation nếu dữ liệu là source-of-truth.

### 31.2. Old app có đọc new data không?

Một rollback app về v1 sau khi v2 đã ghi JSON có thể thất bại nếu v1 chỉ hiểu JDK bytes.

Vì thế migration plan phải xét:

```text
V1 reads V1
V2 reads V1
V2 writes V2
V1 reads V2 (nếu rollback được yêu cầu)
```

Không chỉ xác nhận “v2 đọc được v1” rồi coi rollback đã an toàn.

### 31.3. Tránh đổi key bytes trong cùng một bước nếu không cần

Khi vừa đổi key serializer vừa đổi value serializer, nếu CLI trả nil sẽ khó biết nguyên nhân ở key, còn khi Java đọc không được sẽ khó biết nguyên nhân ở value.

Nên thiết kế migration có phase rõ ràng, tách ranh giới data format.

---

## 32. Versioned namespace cho cache tái tạo được

Với cache có source-of-truth là database, một hướng an toàn:

```text
products:v1::<id>  -> old serializer
products:v2::<id>  -> new serializer
```

Quy trình:

1. New app chỉ đọc/ghi v2.
2. V2 miss thì load từ database.
3. Old app vẫn dùng v1 trong thời gian chuyển tiếp.
4. Canary kiểm tra serializer và business behavior.
5. Prewarm hot keys hoặc kiểm soát cache stampede.
6. Dọn v1 keys theo TTL/retention policy.
7. Rollback app cũ vẫn có thể dùng v1 trong cửa sổ cho phép.

### 32.1. Rủi ro cold cache

Nếu 1 triệu cache entries chuyển sang namespace mới:

```text
V2 bắt đầu với 0 cached keys.
```

Ứng dụng có thể dồn tải về database. Cần đo:

```text
Cache hit/miss
Database QPS
HTTP p95/p99
Redis command rate
Memory usage
TTL distribution
```

### 32.2. Không áp dụng cho state không tái tạo được

Session, inventory reservation, queue/Stream messages, counters nghiệp vụ hoặc token revocation có thể không thể rebuild từ một database khác.

Không tự xóa những namespace ấy vì CLI đang hiển thị binary.

---

## 33. Migration in-place với dữ liệu quan trọng

Nếu phải đổi serializer cho dữ liệu không thể tái tạo:

### Bước 1 — Xác định contract cũ

```text
Old key bytes
Old value bytes/codec
Data types
TTL
Secondary indexes
Schema/classes
Writer versions
```

### Bước 2 — Lập backup và restore test

Backup phải có thể phục hồi trên môi trường cách ly. Một file RDB/AOF tồn tại không đủ chứng minh ứng dụng đọc được data sau restore.

### Bước 3 — Phân nhóm key

Ví dụ:

```text
String JSON
String JDK bytes
Hash field values
Repository entities/indexes
Streams
Session/counters
```

### Bước 4 — Thiết kế reader cho cả hai format

Dùng version marker rõ hoặc keyspace version. Tránh “thử JDK, nếu lỗi thì thử JSON” trên dữ liệu tùy ý mà không có kiểm soát, vì có nguy cơ bảo mật và chẩn đoán sai.

### Bước 5 — Giải quyết concurrent writes

Một job:

```text
GET old bytes
Decode
SET new bytes
```

có thể ghi đè update mới từ application trong lúc migration. Cần chiến lược CAS/versioning, pause writes, atomic Lua script cùng key/slot hoặc reconciliation theo đặc thù dữ liệu.

### Bước 6 — Bảo toàn TTL

Không reset deadline session/OTP bằng cách cấp TTL mới dài hơn. Có thể cần lưu deadline tuyệt đối hoặc tính `PTTL` an toàn với race và behavior khi key hết hạn giữa các bước.

### Bước 7 — Validate bằng app mới

So sánh:

```text
Counts
Types
TTL
Sample decoded objects
Business invariants
Indexes
Stream positions/ACK states
```

### Bước 8 — Canary và rollback

Chỉ mở rộng traffic khi new reader không tạo decode errors; quyết định khả năng rollback old app trên new format trước khi bắt đầu.

---

## 34. Những vấn đề khi dùng cùng tên key cho nhiều kiểu dữ liệu

Giả sử một team cũ:

```redis
SET order:42 "<serialized JSON>"
```

Team mới:

```redis
HSET order:42 status PAID
```

Redis key không thể đồng thời là String và Hash. `HSET` trên String gây `WRONGTYPE` cho tới khi key được thay đổi/xóa theo đúng quy trình.

Một implementation mới có thể “sửa” bằng cách:

```redis
DEL order:42
HSET order:42 status PAID
```

Điều đó **xóa dữ liệu cũ** và có thể gây lost updates.

### 34.1. Đổi Redis data type là migration

Đặt key namespace riêng:

```text
order:v1:42  -> String JSON
order:v2:42  -> Hash
```

hoặc có migration strategy rõ ràng. Không coi String→Hash là chỉ đổi Java serializer.

### 34.2. Redis Repository và custom Template cùng namespace

Nếu một Repository lưu `people:42` dưới dạng Hash, một custom `RedisTemplate.opsForValue().set("people:42", ...)` có thể ghi đè/đổi type nếu writer dùng cùng raw key bytes.

Phải phân tách namespace sở hữu data, không để các abstractions vô tình dùng chung key name nhưng khác Redis types.

---

## 35. Dùng Redis ACL/TLS đúng khi chẩn đoán

Khi so sánh app và CLI, không nên tạm tắt TLS hoặc dùng Redis admin password công khai chỉ để “GET cho nhanh”.

Một số lỗi CLI:

```text
NOAUTH
NOPERM
TLS handshake failure
Connection refused
```

là lỗi access/network, không phải serializer.

### 35.1. Không in credentials trong shell history

Nếu cần `redis-cli` trên môi trường bảo vệ, dùng cách truyền credentials theo secret management/runbook được chấp thuận. Đừng paste URL có password vào ticket.

### 35.2. Read-only diagnostic user

Một user chỉ có quyền đọc những key families cần thiết có thể đủ cho `TYPE`, `GET`, `HGETALL`, `TTL` tùy ACL policy, nhưng command permissions/key patterns cần xác nhận theo Redis version.

Không tự cấp `+@all` để xử lý một `NOPERM`.

### 35.3. Chỉ log metadata

Logs nên có:

```text
operation
key family
serializer class
outcome
error class
value byte length (nếu được phép)
trace ID kỹ thuật
```

Không log full key/value, Java object `toString()`, password hoặc JWT.

---

## 36. Một service có hai RedisTemplate khác nhau: cách kiểm tra

Giả sử code:

```java
@Service
public class CartService {

    private final RedisTemplate<String, Object> cartTemplate;

    public CartService(
            @Qualifier("cartRedisTemplate")
            RedisTemplate<String, Object> cartTemplate) {
        this.cartTemplate = cartTemplate;
    }
}
```

Khi debug, phải xác định bean `cartRedisTemplate`, không chỉ bean tên `redisTemplate`.

### 36.1. Kiểm tra tên lớp serializer, không in payload

Một diagnostic nội bộ trong test:

```java
public static String serializerType(
        org.springframework.data.redis.serializer.RedisSerializer<?> s) {
    return s == null ? "<null>" : s.getClass().getName();
}
```

Sau đó:

```java
System.out.println(
    serializerType(cartTemplate.getKeySerializer())
);
System.out.println(
    serializerType(cartTemplate.getValueSerializer())
);
System.out.println(
    serializerType(cartTemplate.getHashKeySerializer())
);
System.out.println(
    serializerType(cartTemplate.getHashValueSerializer())
);
```

Đây chỉ là kiểm tra kiểu serializer; actual behavior còn phụ thuộc config/ObjectMapper/codec/version. Hai instances cùng class có thể được cấu hình khác nhau.

### 36.2. Tránh log `toString()` của serializer ObjectMapper config

Một số custom serializer giữ reference đến mapper hoặc keys. Không tự dump toàn bộ bean/config object vì có thể kéo theo secrets.

---

## 37. Lỗi do khác serialization version mà không đổi serializer class

Hai môi trường đều dùng Jackson serializer nhưng:

```text
Old:
    ObjectMapper A

New:
    ObjectMapper B
```

khác:

- Naming strategy.
- Enum representation.
- Date/time module.
- Type metadata rules.
- Unknown property handling.
- Polymorphic validator.
- Null/default inclusion.
- JSON escaping.
- Custom modules.

Kết quả CLI vẫn thấy JSON, nhưng Java có thể deserialize khác.

### 37.1. Thử round-trip với bytes cũ

Một test nên giữ fixtures bytes đại diện được tạo từ app cũ:

```text
old-value.json
old-value.bin
old-key-bytes
```

với dữ liệu giả đã được scrub. New reader phải pass trước khi rollout.

### 37.2. Kiểm tra golden files

Thay vì chỉ assert:

```java
deserialize(serialize(object)).equals(object)
```

cần kiểm tra **wire format**:

```text
serialize V2 theo contract
deserialize fixture V1
```

Vì một serializer lỗi được dùng cả chiều đọc và ghi có thể vẫn round-trip chính nó nhưng không tương thích dữ liệu production.

### 37.3. Null/missing fields

Các field vắng trong old JSON có thể được new code hiểu là `null`, `0` hoặc default. Đây là vấn đề semantic schema, không chỉ exception.

Cần kiểm tra business invariants của object sau deserialize, không chỉ “không ném lỗi”.

---

## 38. Kiểm tra raw bytes an toàn: phân biệt preview và đo kích thước

Nếu cần quan sát format, có thể dùng:

```java
byte[] serialized =
    serializer.serialize(testObject);

int byteCount = serialized.length;
```

Ở production, ưu tiên ghi:

```text
serializer name
payload bytes
schemaVersion
outcome
```

Trên lab có dữ liệu giả, có thể xem:

```java
HexFormat.of().formatHex(serialized)
```

**Không in hex bytes của token/session/user data thật.** Hex không phải encryption hoặc redaction.

### 38.1. Tại sao không dùng MONITOR cho mọi vấn đề serializer?

MONITOR có thể hiển thị key/value arguments của nhiều service khác, tạo overhead và lộ dữ liệu nhạy cảm. Nhiều câu hỏi đã có thể giải quyết bằng:

- Serializer class/config trong Spring.
- Unit test serialize key/value.
- Low-level read trong Redis lab.
- `TYPE`, `TTL`, `STRLEN`, `HLEN`.
- Logs metadata và exception categories.

Dùng công cụ nhỏ nhất phù hợp với câu hỏi.

---

## 39. Kiểm chứng serializer key có ảnh hưởng hash slot Redis Cluster

Redis Cluster tính hash slot từ key bytes và hash tag (nếu hợp lệ).

Ví dụ code Java định dùng:

```text
cart:{c-42}:items
cart:{c-42}:total
```

Nếu key serializer là String/UTF-8, cả hai raw keys giữ nguyên `{c-42}`, thường được hash cùng slot.

Nếu key serializer là JDK serialization, raw bytes có thể có prefix binary và framing. Cú pháp tag mà Redis thấy ở mức bytes có thể khác ý định của developer; phải kiểm tra **raw bytes và `CLUSTER KEYSLOT` trên actual keys**, không chỉ Java String.

### 39.1. Hai vấn đề khác nhau

```text
CLI không thấy key:
    vì key bytes khác.

CROSSSLOT:
    vì nhiều raw keys được hash vào slots khác nhau.
```

Cả hai có thể xuất hiện sau đổi serializer.

### 39.2. Không giải quyết bằng cách dùng một hash tag global

Gom mọi key vào `{global}` để tránh `CROSSSLOT` tạo hot slot và làm mất lợi ích phân tán của Cluster.

Thiết kế hash tag theo aggregate cần atomic operation; giữ serializer key bytes ổn định.

### 39.3. Không phải mọi Redis client tự encode key giống nhau

Một custom binary key codec có thể tạo bytes mà redis-cli nhập literal string không tái tạo được. Nếu cần truy vấn một raw key nhị phân chính xác, dùng test adapter biết cùng codec thay vì gõ dự đoán tên key.

---

## 40. Một số khác biệt không phải do serializer nhưng dễ bị nhầm

### 40.1. Stale cache trong JVM

Một service đọc local cache, còn CLI đọc Redis mới nhất.

### 40.2. Replica read lag

Spring cấu hình read-from replica, CLI hỏi primary hoặc ngược lại.

### 40.3. Pipeline/transaction

Lệnh chưa thực thi cho tới khi transaction được commit hoặc pipeline được flush theo ngữ nghĩa API.

### 40.4. Connection/timeout

Lệnh write có thể đã thực thi nhưng reply mất; ứng dụng retry hoặc báo lỗi trong khi CLI thấy dữ liệu.

### 40.5. Key expiration/eviction

Một key tồn tại khi app đọc nhưng biến mất trước CLI GET.

### 40.6. Tenant/environment prefix

App dùng `tenant:t-7:user:42`; CLI hỏi `user:42`.

### 40.7. Redis modules

`JSON.GET` chỉ có ý nghĩa khi module/feature tương ứng được cung cấp. Plain JSON String lưu bằng `SET` không tự trở thành RedisJSON document.

### 40.8. Client-side compression

CLI thấy binary, nhưng không phải do Redis Server tự nén `SET` value; ứng dụng hoặc serializer đã nén.

### 40.9. Same logical key, different raw key bytes

Lỗi do serializer key, không phải value.

### 40.10. Same raw bytes, different decoder

Lỗi do value serializer/schema/charset.

### 40.11. Different Redis data types

Lỗi do API `GET`/`HGETALL` không đúng, không phải chỉ đổi JSON mapper là xong.

### 40.12. Same Redis key but changed between reads

Lỗi do concurrency, TTL hoặc replica, không phải do format.

---

## 41. Quy trình triển khai thay đổi serializer an toàn

### Trước thay đổi

- Xác định nguồn dữ liệu có thể tái tạo hay không.
- Liệt kê key families, Redis data types và TTL.
- Xác định Spring beans/serializers đang ghi.
- Thu thập dữ liệu giả đại diện từ writer cũ.
- Kiểm tra serializer version, Java class/schema.
- Tạo backup và thử restore nếu dữ liệu quan trọng.
- Ghi baseline cache hit rate và deserialization errors.
- Xây integration tests old writer → new reader.
- Xác định rollback app có phải đọc new writes hay không.

### Khi thay đổi

- Dùng versioned namespace hoặc dual-reader có kế hoạch.
- Không ghi đè old data nếu app cũ chưa đọc được format mới.
- Giữ TTL/deadline semantics.
- Giới hạn canary writers và cold-cache load.
- Quan sát `SerializationException`, `WRONGTYPE`, `ClassCastException`.
- Không chạy `FLUSHALL` để chữa lỗi format.
- Với Redis Cluster, kiểm tra hash slot/routing.
- Với Streams/Repositories, kiểm tra mapping và index.

### Sau thay đổi

- Xác nhận dữ liệu cũ đọc được hoặc đã migrate.
- Xác nhận dữ liệu mới được ghi đúng contract.
- So sánh cache hit/miss, p99, database load.
- Kiểm tra TTL, keyspace count và memory.
- Kiểm tra recovery và rollback path.
- Chỉ cleanup old keys khi đáp ứng retention/correctness.
- Ghi lại migration version, ngày triển khai, kết quả test.

---

## 42. Bài thực hành 1 — StringRedisTemplate và redis-cli

Trong Redis test cô lập:

```java
stringRedisTemplate.opsForValue().set(
    "lab:hello",
    "Xin chào Redis"
);
```

Dùng CLI trên đúng host/DB:

```redis
TYPE lab:hello
GET lab:hello
STRLEN lab:hello
TTL lab:hello
```

Hãy giải thích:

1. Vì sao `TYPE` trả `string`.
2. Vì sao `GET` hiển thị văn bản nếu terminal hỗ trợ UTF-8.
3. Vì sao `STRLEN` tính bytes thay vì ký tự Java.
4. Nếu CLI dùng DB khác, điều gì xảy ra?

---

## 43. Bài thực hành 2 — JDK key serializer khiến CLI trả nil

Trong lab, tạo hai template:

```text
A: String key serializer
B: JDK key serializer
```

Cả hai ghi cùng logical key `"lab:user:42"` nhưng values giả khác nhau.

Yêu cầu:

1. Java đọc bằng A và B.
2. CLI `GET lab:user:42`.
3. In hexadecimal của **key bytes giả** trong unit test.
4. So sánh bằng `Arrays.equals`.
5. Giải thích vì sao Redis có thể chứa hai keys độc lập.
6. Nêu vì sao `redis-cli --raw` không giải quyết key mismatch.

Không thử nghiệm trên Redis production có dữ liệu khách hàng thật.

---

## 44. Bài thực hành 3 — JDK value serializer

Tạo:

```text
Key serializer: String
Value serializer: JDK
```

Ghi một object `DemoUser` có thể serialize vào Redis test.

1. `TYPE` key.
2. `GET` key trong CLI.
3. Đọc lại bằng đúng RedisTemplate.
4. Thử đọc bằng StringRedisTemplate trên **cùng raw key** và ghi nhận vấn đề.
5. Xác định ý nghĩa prefix bytes `AC ED 00 05` nếu thấy.
6. Giải thích tại sao Redis String không có nghĩa Java String.

---

## 45. Bài thực hành 4 — JSON có type hints

Sử dụng một generic JSON serializer trong phiên bản Spring Data Redis có hỗ trợ.

1. Ghi `ProductDto` giả.
2. Dùng CLI `GET` để xem JSON.
3. Kiểm tra có type metadata không.
4. Chuyển đổi Java class/package trong môi trường test.
5. Đọc lại old entry bằng app mới.
6. Thiết kế schema/version strategy để tránh phụ thuộc tùy tiện vào tên Java class.

Thảo luận rủi ro khi bật polymorphic deserialization không có allowlist.

---

## 46. Bài thực hành 5 — Hash serializers

Cấu hình:

```text
Key: String
Hash field: JDK
Hash value: JSON
```

Ghi:

```java
template.opsForHash().put(
    "lab:hash:42",
    "displayName",
    "Alice"
);
```

Quan sát:

```redis
TYPE lab:hash:42
HGETALL lab:hash:42
HGET lab:hash:42 displayName
```

Giải thích vì sao field literal `displayName` có thể không khớp với field bytes đã serialize.

Sau đó đổi `hashKeySerializer` sang String trong một **namespace lab mới**, không sửa bừa dữ liệu cũ, rồi so sánh kết quả.

---

## 47. Bài thực hành 6 — WRONGTYPE và Repository

Tạo một entity có `@RedisHash` và lưu bằng Redis Repository trong lab.

1. Gọi `repository.save`.
2. Xác định Redis keyspace.
3. Chạy `TYPE`.
4. Thử `GET` và ghi nhận WRONGTYPE nếu Redis Hash.
5. Dùng `HGETALL`.
6. So sánh Hash fields với Java entity.
7. Nếu có `@Indexed`, tìm hiểu secondary index keys.
8. Đọc lại bằng `repository.findById`.

Vì sao `RedisTemplate` value serializer không phải câu trả lời duy nhất cho cách Repository lưu entity?

---

## 48. Bài thực hành 7 — Spring Cache key prefix

Tạo method:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductDto loadProduct(String productId) {
    return database.load(productId);
}
```

Yêu cầu:

1. Tạo một cache entry bằng app.
2. Xác định actual key prefix bằng configuration/test.
3. So sánh CLI `GET p-42` với `GET <actual-key>`.
4. Đọc type/TTL.
5. Xác định CacheManager value serializer.
6. Dự đoán kết quả nếu app khác dùng JDK serializer để đọc JSON value.
7. Đề xuất test bảo vệ cache key format.

---

## 49. Bài thực hành 8 — Sai logical database

Trên standalone Redis **test**:

1. Ghi key vào DB 2.
2. `redis-cli` mặc định kết nối DB 0.
3. Chạy `GET` và quan sát `(nil)`.
4. Chuyển CLI sang DB 2.
5. Đọc lại key.
6. So sánh với serializer thật.

Giải thích tại sao phải xác định host/port/DB **trước** khi đổ lỗi serializer.

Không áp dụng ví dụ `SELECT 2` cho Redis Cluster.

---

## 50. Bài thực hành 9 — Unicode và bytes

Dùng các chuỗi:

```text
hello
Hà Nội
Tiếng Việt
```

Trong Java:

```java
byte[] raw =
    new StringRedisSerializer().serialize(value);
```

Đo:

```text
String.length()
raw.length
```

Lưu bằng StringRedisTemplate, đọc bằng CLI có UTF-8 phù hợp.

Giải thích vì sao các số có thể khác nhau và tại sao một terminal dùng charset sai có thể hiển thị mojibake.

---

## 51. Bài thực hành 10 — Old JSON data, new serializer

Tạo hai phiên bản app thử:

```text
V1: JSON schemaVersion=1
V2: JSON schemaVersion=2
```

Các bước:

1. V1 ghi data.
2. V2 đọc old data.
3. Thêm/bỏ một field có giá trị mặc định.
4. Đổi enum hoặc date format trong test.
5. Kiểm tra schema compatibility.
6. Nếu cần rollback, test V1 đọc value do V2 ghi.
7. Đề xuất expand-and-contract hoặc versioned namespace.

Không chỉ assert deserialize không ném lỗi; cần kiểm tra dữ liệu nghiệp vụ đúng nghĩa.

---

## 52. Bài thực hành 11 — Compression và binary Redis String

Trong test:

1. Tạo JSON mẫu.
2. Nén JSON bằng một codec xác định.
3. Lưu compressed bytes với RedisTemplate được cấu hình phù hợp.
4. Dùng CLI `TYPE` và `GET` trong môi trường test.
5. Dùng application codec để decompress + decode.
6. Đo payload bytes trước/sau nén.
7. Không log raw bytes/key thật.

Giải thích vì sao không thể chỉ nhìn `GET` dạng văn bản để kết luận dữ liệu hỏng.

---

## 53. Bài thực hành 12 — Redis Cluster hash slot và key serializer

Trong Redis Cluster test:

1. Tạo hai logical keys cùng hash tag `{cart-42}`.
2. Serialize bằng StringRedisSerializer.
3. Xem bytes trong unit test.
4. Đối chiếu `CLUSTER KEYSLOT` với actual key bytes.
5. Lặp thử với một key serializer khác trong namespace test.
6. Kiểm tra multi-key script/transaction có còn same-slot không.
7. Giải thích vì sao thay key serializer có thể ảnh hưởng key lookup lẫn routing.

---

## 54. Bài thực hành 13 — Không log dữ liệu nhạy cảm

Tạo một DTO **giả**:

```java
record DemoSession(
    String userId,
    String fakeToken
) {}
```

Thay vì:

```java
log.debug("Redis session={}", session);
```

hãy log:

```text
operation=session-cache-write
serializer=JSON
payloadByteBucket=1-4KiB
result=success
```

Thảo luận:

- Vì sao hex raw payload không phải redaction?
- Vì sao Redis key name cũng có thể chứa PII?
- Vì sao không chạy MONITOR toàn production chỉ để tìm serializer mismatch?
- Có thể kiểm tra serializer class và byte length mà không ghi value không?

---

## 55. Bài thực hành 14 — Xây diagnostic decision tree

Cho tình huống:

```text
App:
    repository.findById("42") trả Person hợp lệ.

CLI:
    GET people:42 -> WRONGTYPE.
```

Hãy viết quy trình:

1. Xác minh endpoint/DB.
2. Xác định Repository vs RedisTemplate.
3. Kiểm tra `TYPE`.
4. Dùng `HGETALL` nếu là Hash.
5. Xác định custom converters.
6. Xác định metadata/index keys.
7. Đối chiếu object Java với fields qua mapping.
8. Chỉ dùng dữ liệu giả hoặc đã được phê duyệt.

Kết luận nào hợp lý hơn: Redis bị lỗi, hay CLI dùng lệnh không phù hợp Redis type?

---

## 56. Bài thực hành 15 — Phân biệt key mismatch và value mismatch

Tạo ba trường hợp test:

```text
Case A:
    Key writer = JDK
    Value writer = JDK

Case B:
    Key writer = String
    Value writer = JDK

Case C:
    Key writer = String
    Value writer = JSON
```

Với mỗi case:

1. Gọi CLI GET bằng literal String key.
2. Kiểm tra CLI tìm thấy key không.
3. Nếu thấy key, xác định value text/binary.
4. Đọc bằng writer's serializer.
5. Đọc bằng một mismatched serializer.
6. Ghi nhận exception/result khác nhau.

Dùng bảng để phân biệt **key addressability** với **value decodability**.

---

## 57. Bài thực hành 16 — Integration test chống lỗi upgrade

Cho một hệ thống dùng Spring Cache và Redis Repository.

Thiết kế CI matrix:

```text
Old app writes -> New app reads
New app writes -> Old app reads (nếu rollback cần)
String key bytes stable?
Cache key prefix stable?
Repository Hash mapping stable?
TTL/deadline preserved?
Indexed queries still correct?
No deserialization exceptions?
```

Sử dụng Redis Testcontainers hoặc môi trường tích hợp tương đương với version được pin. Dùng fixtures giả, không copy raw user/session data vào repo.

---

## 58. Các ngộ nhận phổ biến

### “GET trả nil nghĩa là Redis không có dữ liệu”

Không chắc. CLI có thể dùng khác endpoint, DB, prefix hoặc raw key bytes.

### “Đổi redis-cli --raw là đọc được Java object”

Không. `--raw` thay cách trình bày bytes, không chạy Java serializer.

### “TYPE string nghĩa là value là văn bản”

Không. Redis String có thể chứa binary bytes tùy ý.

### “Tôi dùng RedisTemplate<String,Object> thì key nhất định là UTF-8”

Không. Java generic type không quyết định Redis key serializer.

### “Tôi thấy JSON trong CLI nên Java chắc chắn deserialize được”

Không. Java có thể dùng JDK decoder, schema khác hoặc type metadata không tương thích.

### “JSON có @class là dữ liệu lỗi”

Không nhất thiết. Đó có thể là metadata phục vụ generic JSON serialization.

### “Chỉ cần đổi valueSerializer là sửa mọi thứ”

Không nếu key bytes, hash field serializers, CacheManager hoặc Repository converters khác.

### “StringRedisTemplate và RedisTemplate luôn nhìn một key giống nhau”

Không nếu chúng dùng key serializers khác nhau.

### “GET trên Repository entity trả WRONGTYPE nghĩa là serializer hỏng”

Không. Redis Repository có thể lưu entity dưới dạng Hash.

### “Sửa keySerializer không ảnh hưởng dữ liệu cũ”

Sai. Key bytes thay đổi có thể làm app không tìm được keys đã ghi.

### “Thay JSON serializer là Redis tự migrate dữ liệu”

Không. Redis giữ nguyên bytes cho tới khi dữ liệu được ghi lại/migrate.

### “V1 đọc được V2 thì rollback chắc chắn an toàn”

Phải test cả hướng V1 reader đọc V2 writer nếu rollback cần.

### “Chuỗi hex không nhạy cảm vì khó đọc”

Sai. Hex là cách biểu diễn bytes có thể đảo ngược.

### “MONITOR là cách duy nhất biết Redis nhận key gì”

Không. Có thể kiểm tra serializer, key generator và raw bytes trong lab; MONITOR có rủi ro hiệu năng/bảo mật.

### “FLUSHALL là cách nhanh nhất chữa lỗi serializer”

Không. Nó xóa dữ liệu Redis, có thể gây mất state không thể khôi phục.

### “Cùng tên key Java thì cùng hash slot Cluster”

Không nếu serializer tạo raw bytes khác. Cluster tính slot từ Redis key bytes thực.

### “Spring Boot nâng xong và PING thành công thì mọi dữ liệu đọc được”

Không. Cần test old data, cache, repository, streams, JSON/JDK codecs và TTL.

---

## 59. Checklist chẩn đoán dùng khi gặp lỗi thực tế

- [ ] Đã xác minh app và CLI đang nói cùng Redis endpoint?
- [ ] Đã xác minh logical DB (standalone) hoặc Cluster topology?
- [ ] Có đọc primary/replica khác nhau hoặc có replication lag không?
- [ ] Đã xác định Spring abstraction (`StringRedisTemplate`, `RedisTemplate`, Cache, Repository, Reactive)?
- [ ] Đã xác định bean/qualifier và connection factory thực tế?
- [ ] Đã biết raw logical key, prefix, namespace và KeyGenerator?
- [ ] Đã xem `keySerializer` thực tế?
- [ ] Đã xem `valueSerializer` thực tế?
- [ ] Nếu Hash, đã xem `hashKeySerializer` và `hashValueSerializer`?
- [ ] Nếu Cache, đã xem RedisCacheConfiguration serialization pairs?
- [ ] Nếu Repository, đã xem mapping converter và keyspace?
- [ ] Đã thử `TYPE`, `EXISTS`, `TTL` trên đúng key bytes?
- [ ] Đã phân biệt `(nil)`, `WRONGTYPE`, binary output và decode exception?
- [ ] Đã kiểm tra giá trị có vừa hết hạn/evicted hay bị writer khác thay đổi không?
- [ ] Đã so sánh serializer bytes bằng test dữ liệu giả?
- [ ] Đã xác định old writer version và schema nếu dữ liệu tồn tại từ trước?
- [ ] Đã kiểm tra UTF-8/terminal display?
- [ ] Có compression/encryption/custom codec không?
- [ ] Nếu Cluster, raw key bytes có ảnh hưởng hash tag/slot không?
- [ ] Đã có integration test old writer → new reader?
- [ ] Đã lên kế hoạch migration nếu muốn đổi serializer?
- [ ] Không dùng `KEYS *`, `MONITOR` hoặc dump secrets tùy tiện trên production?
- [ ] Không xóa Redis key/data trước khi hiểu loại dữ liệu và nguồn khôi phục?
- [ ] Nội dung báo cáo chỉ chứa metadata và dữ liệu đã được phép chia sẻ?

---

## 60. Câu hỏi tự đánh giá

1. Redis lưu Java object theo cách nào?
2. Redis `TYPE string` có nói value là UTF-8 không?
3. `StringRedisSerializer` khác `JdkSerializationRedisSerializer` thế nào?
4. Vì sao RedisTemplate dùng JDK key serializer có thể khiến CLI `GET user:42` trả nil?
5. `redis-cli --raw` tác động gì và không tác động gì?
6. Khi CLI thấy `AC ED 00 05`, bạn nên nghĩ đến format nào?
7. Vì sao header đó chưa đủ chứng minh class/schema đọc được?
8. Khác biệt giữa key serializer và value serializer?
9. Redis Hash cần những serializers nào?
10. Vì sao `HGET user:42 displayName` có thể trả nil khi Java đọc được hash field?
11. `WRONGTYPE` liên quan Redis data type hay Java mapper?
12. Vì sao Redis Repository entity thường không đọc được bằng `GET`?
13. Spring Cache có nhất thiết dùng RedisTemplate value serializer không?
14. Vì sao cache key có thể là `products::42` chứ không phải `42`?
15. Tại sao hai RedisTemplate cùng generic types vẫn khác nhau về raw bytes?
16. Nếu Java đọc được nhưng CLI không tìm key, bạn nên kiểm tra bước nào trước?
17. Nếu raw value tồn tại nhưng deserialize lỗi, những nguyên nhân nào cần xem?
18. Kết nối sai Redis DB có thể tạo triệu chứng giống serializer mismatch thế nào?
19. Redis Cluster có nhiều logical DB như standalone không?
20. Key serializer thay đổi có ảnh hưởng hash slot không?
21. Tại sao một `String.length()` không tương đương payload bytes?
22. Khi nào JSON có type metadata và nó gây rủi ro gì khi đổi package Java?
23. Tại sao phải test dữ liệu do bản ứng dụng cũ ghi?
24. Vì sao round-trip test của cùng serializer chưa đủ?
25. Phân biệt cache có thể xóa và state không thể tái tạo ra sao?
26. Có nên `FLUSHDB` nếu vừa đổi JSON format không?
27. RDB `DUMP` khác JDK serialization thế nào?
28. Tại sao hex payload không được coi là đã ẩn dữ liệu?
29. Làm sao xác minh một Redis Hash value mà không log raw PII?
30. Nếu Java và CLI đọc cùng raw key ở hai thời điểm khác nhau, những yếu tố ngoài serializer nào có thể làm kết quả khác?
31. Reactive Redis có thể chưa gửi command khi chưa subscribe không?
32. Một diagnostic runbook hợp lý nên kết thúc bằng loại test hồi quy nào?

## 61. Ghi nhớ

- **Redis lưu bytes, không lưu Java objects.** `redis-cli` hiển thị response bytes còn Spring Data Redis có thể serialize/deserialize theo Java configuration.
- **Một logical key String không nhất thiết bằng raw Redis key bytes.** Key serializer khác nhau có thể tạo hai keys độc lập, khiến CLI `(nil)` dù Java đọc được.
- **Phân biệt key serializer và value serializer.** Key mismatch gây không tìm thấy; value mismatch gây binary khó đọc hoặc deserialize errors.
- **Redis `TYPE string` không nói value là text.** Java JDK serialized bytes, JSON, Protobuf, encrypted/compressed bytes đều có thể nằm trong Redis String.
- **`--raw` không sửa key serializer và không tự decode Java object.** Nó chỉ thay cách CLI biểu diễn output.
- **Hash có serializers riêng cho field và field value.** `opsForHash`/Repository không đồng nghĩa một `GET` String.
- **Spring Cache dùng CacheManager serialization pairs và key prefix**, có thể khác `RedisTemplate`; Redis Repository dùng mapping converter có thể lưu Hash/index metadata.
- **Đọc đúng key bytes, đúng Redis type và đúng DB/node** trước khi kết luận dữ liệu hỏng.
- **Một JSON CLI nhìn hợp lệ vẫn có thể không decode thành Java class**, đặc biệt với type metadata, schema migration và ObjectMapper configuration.
- **Không thay serializer trong production như thay cách hiển thị.** Đây là thay đổi data contract; cần old-data fixtures, integration tests và migration/rollback plan.
- **Một serializer round-trip chính nó chưa chứng minh backward compatibility** với data cũ hoặc ứng dụng khác.
- **Redis Cluster phân slot theo raw key bytes**; đổi key serializer có thể làm mất key lookup, đổi routing hoặc phá multi-key same-slot behavior.
- **Đừng dùng `FLUSHALL`, raw MONITOR hay log binary secrets để debug.** Ưu tiên metadata, Redis `TYPE`/TTL, test serializer bytes với dữ liệu giả và structured diagnostics.
- **Luôn loại trừ nguyên nhân ngoài serializer:** sai endpoint/DB, cache prefix, TTL, eviction, replica lag, concurrency, transaction và local cache.
- **Chẩn đoán đúng là xác nhận đường biến đổi Java object ↔ byte[] ↔ Redis data structure**, rồi viết test bảo vệ hợp đồng đó.

### Tài liệu tham khảo chính thức

- [Spring Data Redis — Serializers](https://docs.spring.io/spring-data/redis/reference/redis/serializers.html)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html)
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html)
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
- [Spring Data Redis — Pub/Sub](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Redis — Data types](https://redis.io/docs/latest/develop/data-types/)
- [Redis — GET](https://redis.io/docs/latest/commands/get/)
- [Redis — TYPE](https://redis.io/docs/latest/commands/type/)
- [Redis — HGETALL](https://redis.io/docs/latest/commands/hgetall/)
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/)
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/)
- [Redis — STRLEN](https://redis.io/docs/latest/commands/strlen/)
- [Redis — DUMP](https://redis.io/docs/latest/commands/dump/)
- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/)
- [Redis — CLUSTER KEYSLOT](https://redis.io/docs/latest/commands/cluster-keyslot/)
- [Redis — redis-cli](https://redis.io/docs/latest/develop/tools/cli/)
- [Redis — Security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/)
- [Spring Boot — Data Redis](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Jackson — Documentation](https://github.com/FasterXML/jackson-docs)

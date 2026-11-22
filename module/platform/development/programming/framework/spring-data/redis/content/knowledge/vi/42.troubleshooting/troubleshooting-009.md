# Giao dịch hoặc pipeline trả kết quả khác thao tác thông thường trong Spring Data Redis

Một tình huống gây nhầm lẫn khi dùng Spring Data Redis: cùng một lệnh `GET`, `INCR` hoặc `HGET`, gọi trực tiếp bằng `StringRedisTemplate` có kết quả ngay; nhưng khi đặt vào `executePipelined(...)` hoặc giữa `multi()` và `exec()`, kết quả trong callback lại là `null`. Đôi khi callback chạy không báo lỗi nhưng danh sách kết quả bên ngoài khác kiểu dự kiến, thứ tự khó hiểu, hoặc một giao dịch có `WATCH` không cập nhật dữ liệu. Cũng có trường hợp thêm `@Transactional` nhưng Redis vẫn ghi ngay, trong khi nhà phát triển tưởng mọi lệnh đang ở trong một transaction chung với SQL.

Phần lớn trường hợp **không phải Redis tự mất kết quả**. Nguyên nhân nằm ở **thời điểm Redis thực thi lệnh, cách driver nhận reply, cơ chế RedisConnection, serializer và việc ràng buộc connection của Spring**. Phân biệt đúng ba đường đi — thao tác thông thường, pipelining và transaction — giúp tránh đọc `null` thành “không có key”, xử lý nhầm kết quả `EXEC`, hoặc vô tình phát lệnh trên connection khác.

Bài chẩn đoán này dùng Spring Boot 3.x, Spring Data Redis 3.x, Java 17 và Redis 7.x làm ngữ cảnh ví dụ. Các API, kiểu trả về và khả năng pipeline trên Cluster có thể thay đổi theo Spring Data Redis/Lettuce/Jedis/Redis version; khi nâng phiên bản, phải kiểm tra **hợp đồng API thực tế**.

## 1. Triệu chứng điển hình

Ví dụ chạy riêng:

```java
String value = strings.opsForValue().get("diag:472:item");
System.out.println(value); // "READY" nếu key tồn tại và serializer đúng
```

Trong pipeline:

```java
List<Object> replies = strings.executePipelined(
        (org.springframework.data.redis.core.RedisCallback<Object>)
                connection -> {
                    byte[] key = "diag:472:item"
                            .getBytes(java.nio.charset.StandardCharsets.UTF_8);
                    byte[] immediate = connection.stringCommands().get(key);

                    System.out.println(immediate); // Thường là null
                    return null;                   // Bắt buộc đối với callback pipeline
                });

System.out.println(replies); // Chứa kết quả lệnh GET sau khi pipeline hoàn tất
```

Nếu dữ liệu có sẵn, `replies` có thể chứa `"READY"`, dù `immediate` bên trong callback là `null`.

Trong transaction:

```text
MULTI
GET diag:472:item
EXEC
```

Redis trả `QUEUED` cho lệnh `GET` sau `MULTI`; giá trị thực chỉ có trong **reply của EXEC**. Spring Data Redis có thể biểu diễn giá trị tạm thời trong callback bằng `null`. Nếu code dựa vào giá trị tạm đó để ra quyết định nghiệp vụ, kết quả sẽ sai.

### 1.1. Bảng nhận diện nhanh

| Dấu hiệu | Nguyên nhân cần kiểm tra trước |
|---|---|
| `GET` bình thường có dữ liệu, `GET` trong pipeline trả `null` | Chưa đọc danh sách trả về từ `executePipelined` |
| Callback pipeline trả `null` nhưng danh sách bên ngoài có dữ liệu | Hành vi được thiết kế: callback chỉ enqueue/send |
| `SET` bên trong `MULTI` chưa nhìn thấy trong `GET` ngay sau đó | Ghi đang `QUEUED`, chưa `EXEC` |
| `EXEC` trả danh sách nhiều phần tử | Mỗi reply tương ứng command được xếp hàng |
| `EXEC` không thực thi khi dùng `WATCH` | Key đã đổi/expire/evict trước khi `EXEC` |
| Có `@Transactional` nhưng Redis ghi ngay | Chưa bật `setEnableTransactionSupport(true)` hoặc không trong Spring-managed transaction |
| Kết quả pipeline là `byte[]`, String hoặc kiểu bất ngờ | Dùng `RedisCallback` raw hay `SessionCallback`; serializer/result deserializer khác |
| `EXEC` có kết quả lỗi dù lệnh trước đã ghi | Redis transaction không rollback lỗi runtime như SQL |
| Transaction/pipeline thành công trên Standalone nhưng lỗi Cluster | Routing/hash slot/driver support khác |
| Kết quả sai lúc có exception giữa `MULTI` và `EXEC` | Connection có thể còn ở transactional state nếu không `DISCARD` |

## 2. Ba cơ chế, ba thời điểm lấy kết quả

```text
A. Lệnh thường
   Java -> GET key -----------------> Redis
   Java <- value -------------------- Redis
   -> Method GET có giá trị ngay

B. Pipeline
   Java -> GET key1 ------+
          GET key2 ------+---------> Redis
          INCR count ----+
   Java <- replies [v1,v2,n] ------- Redis
   -> Giá trị nằm trong kết quả khi pipeline đóng

C. Transaction
   Java -> MULTI -------------------> Redis
          SET key value -----------> QUEUED
          GET key -----------------> QUEUED
          EXEC --------------------> [status, value]
   -> Command chỉ thực thi khi EXEC
```

| Thuộc tính | Lệnh thường | Pipeline | Redis transaction |
|---|---|---|---|
| Mục tiêu | Gửi một lệnh và nhận reply | Giảm round trip khi có nhiều lệnh | Thực thi một nhóm lệnh không xen lẫn command từ client khác |
| Thời điểm thấy reply | Khi method hoàn tất | Sau khi đọc toàn bộ pipeline replies | Tại `EXEC` |
| Có tính nguyên tử nhóm lệnh? | Chỉ tính nguyên tử của từng lệnh | **Không** | Có tính không xen kẽ khi nhóm lệnh được `EXEC` |
| Có thể đọc kết quả lệnh trước để rẽ nhánh tiếp? | Có | Không khi lệnh còn đang buffered | Không ở giữa `MULTI` và `EXEC` |
| Có rollback SQL khi một lệnh runtime lỗi? | Không | Không | **Không** |
| Có thể xung đột optimistic locking? | Không do `WATCH` mặc định | Không do pipeline | Có, nếu dùng `WATCH` |
| Kết quả Spring | Value/Boolean/Long... | `List<Object>` qua `executePipelined` | `List<Object>` qua `exec` khi dùng trực tiếp |

**Pipeline và transaction là hai tính năng độc lập.** Có thể kết hợp nhưng dễ gây hiểu nhầm vì một lớp trì hoãn reply của lớp còn lại. Nếu mục tiêu chỉ là đảm bảo nhiều thao tác có tính nguyên tử, pipeline **không** thay transaction hoặc Lua script.

## 3. Chuẩn bị một baseline có kết quả dễ quan sát

Giả sử ứng dụng được inject `StringRedisTemplate`:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisReadExample {

    private final StringRedisTemplate strings;

    public RedisReadExample(StringRedisTemplate strings) {
        this.strings = strings;
    }

    public String read(String key) {
        return strings.opsForValue().get(key);
    }
}
```

Tạo dữ liệu trên Redis test:

```redis
SET diag:472:first alpha
SET diag:472:second beta
SET diag:472:count 10
```

Với String serializer, kết quả thông thường:

```java
String first = strings.opsForValue().get("diag:472:first");
String second = strings.opsForValue().get("diag:472:second");
Long count = strings.opsForValue().increment("diag:472:count");

// first  = "alpha"
// second = "beta"
// count  = 11
```

Đây là **baseline** để so sánh. Test chẩn đoán nên dùng key riêng, tránh kết quả bị ảnh hưởng bởi những thread hoặc bài test khác. Không dùng Redis production hay `FLUSHALL` chỉ để thử một vài lệnh.

## 4. Pipeline vận hành thế nào?

**Pipelining** là gửi nhiều lệnh mà không chờ từng reply. Redis xử lý các lệnh theo thứ tự nhận được trên connection, còn client thu thập replies sau.

```text
App                                 Redis
 | --- GET k1 ---------------------> |
 | --- GET k2 ---------------------> |
 | --- INCR c ---------------------> |
 |                                  | GET k1
 |                                  | GET k2
 |                                  | INCR c
 | <--- "alpha" ------------------- |
 | <--- "beta" -------------------- |
 | <--- 11 ------------------------ |
```

Trong Spring Data Redis, `executePipelined(...)` mở pipeline trên Redis connection, chạy callback để phát các lệnh, sau đó đọc và deserialze reply. **Callback trả `null`; danh sách do phương thức `executePipelined` trả về mới là kết quả cần dùng.**

### 4.1. Ví dụ an toàn bằng SessionCallback

```java
import java.util.List;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

List<Object> results = strings.executePipelined(
        new SessionCallback<Object>() {
            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public Object execute(RedisOperations operations)
                    throws DataAccessException {

                operations.opsForValue().get("diag:472:first");
                operations.opsForValue().get("diag:472:second");

                // Không trả về kết quả của một Redis command ở đây.
                return null;
            }
        });

// results thường là ["alpha", "beta"]
```

Trong `SessionCallback`, `RedisOperations` dùng cùng session/connection trong callback. Không cần mở, đóng hay tự tạo connection mới cho từng thao tác.

### 4.2. Vì sao không viết điều kiện trong callback?

Sai:

```java
strings.executePipelined(
        (org.springframework.data.redis.core.SessionCallback<Object>)
                operations -> {
                    Object value = operations.opsForValue()
                            .get("diag:472:first");
                    if ("alpha".equals(value)) {
                        operations.opsForValue()
                                .set("diag:472:status", "OK");
                    }
                    return null;
                });
```

Trong pipeline, `value` chưa chắc là reply thật (thường `null`). Nhánh `if` không chạy dù Redis có dữ liệu. Đó là lỗi **phụ thuộc dữ liệu chưa được trả về**, không phải Redis đọc sai.

Sửa bằng một trong ba cách:

1. Đọc key **trước** pipeline (nếu không cần atomicity với phần ghi tiếp theo).
2. Dùng Lua để đọc–kiểm tra–ghi nguyên tử trên Redis server.
3. Nếu yêu cầu CAS dựa trên dữ liệu đọc, dùng `WATCH`/`MULTI`/`EXEC` với retry theo điều kiện nghiệp vụ.

Không dùng một pipeline với hàng loạt `GET` rồi rẽ nhánh dựa vào kết quả của chúng **ngay bên trong cùng callback**.

## 5. RedisCallback raw khác SessionCallback dùng Template

`executePipelined` nhận được cả `RedisCallback` lẫn `SessionCallback`, nhưng hai cách có mức trừu tượng khác nhau.

### 5.1. RedisCallback: làm việc với RedisConnection và byte[]

```java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.data.redis.core.RedisCallback;

List<Object> results = strings.executePipelined(
        (RedisCallback<Object>) connection -> {
            byte[] a = "diag:472:first"
                    .getBytes(StandardCharsets.UTF_8);
            byte[] b = "diag:472:second"
                    .getBytes(StandardCharsets.UTF_8);

            // Kết quả tức thì trong pipeline thường là null.
            byte[] queuedA = connection.stringCommands().get(a);
            byte[] queuedB = connection.stringCommands().get(b);

            // Không xử lý queuedA/queuedB như dữ liệu thật.
            return null;
        });
```

Đây là **connection-level API**: arguments là bytes. Nếu trước đó key được ghi bằng `JdkSerializationRedisSerializer`, mã `UTF-8` phía trên không tìm đúng key vật lý. Phải dùng serializer tương thích với writer.

### 5.2. SessionCallback: dùng RedisOperations

```java
List<Object> results = strings.executePipelined(
        new SessionCallback<Object>() {
            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public Object execute(RedisOperations operations) {
                operations.opsForValue().get("diag:472:first");
                operations.opsForValue().get("diag:472:second");
                return null;
            }
        });
```

Khi dùng `StringRedisTemplate`, các thao tác value/key theo String serializer đã cấu hình. Đó là cách thường dễ dùng hơn khi cần làm việc ở mức object, không muốn tự truyền byte arrays.

### 5.3. Callback phải trả null

API `executePipelined` yêu cầu callback trả `null`. Giá trị callback khác null **không** trở thành giá trị trả về của `executePipelined`; một số phiên bản kiểm tra và báo lỗi. Danh sách result được xây từ các replies thu thập sau pipeline.

Đừng viết:

```java
return operations.opsForValue().get(key); // Sai contract callback pipeline
```

Hãy:

```java
operations.opsForValue().get(key);
return null;
```

Sau đó xử lý `List<Object>` ở bên ngoài.

## 6. Vì sao danh sách pipeline result khác kết quả gọi đơn?

`RedisTemplate` nhận một loạt raw Redis replies rồi deserialize theo cấu hình serializer. Mỗi command có **kiểu reply khác nhau**.

| Redis command | Reply server | Kiểu Java thường gặp sau Spring conversion |
|---|---|---|
| `GET key` | Bulk String hoặc nil | `String`/DTO hoặc `null` nếu key không tồn tại |
| `INCR key` | Integer | `Long` |
| `EXISTS key` | Integer (số key) | Boolean hoặc Long tùy abstraction/overload |
| `SET key value` | Status reply `OK` | Boolean/status-converted value tùy API |
| `HGETALL key` | Các field/value | Map giải mã theo hash serializers |
| `LRANGE key a b` | Array of bulk strings | List dữ liệu đã deserialize |
| `TTL key` | Integer | Long/Duration tùy API |
| `ZADD` | Integer | Boolean/Long tùy method |

Không ép `results.get(i)` luôn là `String`. Nếu pipeline có cả `GET` và `INCR`, một reply có thể là String, reply khác Long.

### 6.1. Thứ tự trong result list

Trên một connection, Redis trả replies theo thứ tự các command được gửi. Nhưng **cách Spring Data Redis chuyển status/transaction replies và nested collections** phụ thuộc command/adapter. Trong bài test phải:

1. Biết chính xác callback đã phát command nào.
2. Biết command đó có server reply dạng gì.
3. Kiểm tra serializer được dùng.
4. Không thêm/loại command trong callback rồi vẫn hardcode index cũ.

Một test tối giản với hai `GET` tránh nhiều loại conversion:

```java
List<Object> result = strings.executePipelined(
        new SessionCallback<Object>() {
            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public Object execute(RedisOperations operations) {
                operations.opsForValue().get("diag:472:first");
                operations.opsForValue().get("diag:472:second");
                return null;
            }
        });

// Với hai key String đã chuẩn bị, result = ["alpha", "beta"].
```

### 6.2. Không nhầm null thật với null bị trì hoãn

Hai tình huống khác nhau:

```text
Trong callback pipeline:
  immediateReply = null
  -> Chưa thể kết luận Redis key có tồn tại.

Sau executePipelined:
  results = [null]
  -> Lệnh GET thực tế có reply nil (hoặc conversion cần kiểm tra).
```

Để chẩn đoán missing key, kiểm tra `EXISTS`/`TYPE`/`GET` bằng thao tác **thông thường ngoài pipeline** trên đúng DB/node và serializer. Không áp dụng nguyên tắc đó cho mọi loại collection khi Redis key là Hash/Stream.

## 7. Serializer: nguyên nhân âm thầm gây kết quả bất ngờ

`StringRedisTemplate` dùng String serializers cho key/value/hash theo mục đích String. Một `RedisTemplate<Object,Object>` không được cấu hình rõ có thể dùng JDK serialization theo default của Spring Data Redis; template dự án cũng có thể override serializer.

```text
Java key       -- keySerializer ------> Redis key bytes
Java value     -- valueSerializer ----> Redis value bytes
Redis reply    -- resultSerializer ---> Java output
```

Khi chạy pipeline hoặc transaction, Spring cần deserialize **tập replies**. Theo tài liệu, RedisTemplate dùng value, hash-key và hash-value serializers cho các kiểu kết quả phù hợp; API còn có overload cho **result serializer** riêng.

### 7.1. Biểu hiện mismatch

Ví dụ dữ liệu trong Redis thật:

```redis
SET diag:472:first alpha
```

`StringRedisTemplate` đọc được `"alpha"`. Nhưng một `RedisTemplate` dùng JDK serializer cho value có thể cố deserialize bytes ASCII `alpha` như Java serialized object và báo `SerializationException`.

Tương tự, dùng raw `RedisConnection.get` với key String nhưng key serializer phía writer là JDK có thể trả nil vì **key bytes khác**, không phải value bị mất.

### 7.2. Chọn đúng result serializer khi cần

RedisOperations có overload:

```java
List<Object> replies = strings.executePipelined(
        (org.springframework.data.redis.core.RedisCallback<Object>)
                connection -> {
                    byte[] key = "diag:472:first"
                            .getBytes(java.nio.charset.StandardCharsets.UTF_8);
                    connection.stringCommands().get(key);
                    return null;
                },
        org.springframework.data.redis.serializer
                .StringRedisSerializer.UTF_8);
```

Đoạn minh họa chọn serializer chuyên cho value String; tên constant/factory method có thể khác giữa các phiên bản, nên nếu muốn tương thích rộng Spring Data Redis 3.x, có thể truyền `new StringRedisSerializer()`.

```java
List<Object> replies = strings.executePipelined(
        (org.springframework.data.redis.core.RedisCallback<Object>) c -> {
            c.stringCommands().get(
                    "diag:472:first".getBytes(
                            java.nio.charset.StandardCharsets.UTF_8));
            return null;
        },
        new org.springframework.data.redis.serializer.StringRedisSerializer());
```

**Chú ý:** Serializer truyền vào overload dùng cho các value replies/collections thích hợp. Các replies kiểu số, boolean/status có cơ chế conversion riêng; không kỳ vọng serializer String biến mọi response thành String.

### 7.3. Hash results cần hash serializers

Nếu trong pipeline có:

```java
operations.opsForHash().entries("diag:472:profile");
```

key Hash và field Hash là hai cấp khác nhau. Spring dùng `hashKeySerializer` và `hashValueSerializer` để diễn giải fields/values. Khi ép dùng một serializer kết quả chuyên biệt, phải hiểu nó tác động thế nào đến Hash field và value theo overload API. Không đọc nhầm `byte[]` JSON/JDK serialization rồi tưởng Redis trả sai.

### 7.4. Golden test giúp xác nhận wire contract

Một test tốt:

1. Ghi String/Hash bằng template đã dùng ở production.
2. Dùng Redis CLI hoặc raw byte API để xác nhận key bytes/value format.
3. Chạy cùng lệnh bình thường.
4. Chạy pipeline/transaction tương đương.
5. So sánh **giá trị semantic sau deserialize** chứ không chỉ `Object.toString()`.

Khi thay serializer trong rolling deploy, lưu fixtures từ phiên bản cũ để phát hiện compatibility break.

## 8. Redis transaction: MULTI, EXEC, DISCARD, WATCH

Transaction Redis sử dụng:

```redis
MULTI
SET diag:472:tx after
GET diag:472:tx
EXEC
```

Phản hồi Redis:

```text
MULTI            -> OK
SET ...          -> QUEUED
GET ...          -> QUEUED
EXEC             -> [OK, "after"]
```

Trước `EXEC`, các lệnh mới chỉ được **xếp hàng**. Redis xử lý các lệnh đã xếp hàng tuần tự, không cho command từ client khác chen vào giữa quá trình `EXEC` của transaction đó.

**Không đồng nghĩa với rollback SQL:** Redis không tự phục hồi những writes đã thực hiện khi một command khác trong danh sách có lỗi ở thời điểm thực thi.

### 8.1. Lệnh gọi bên trong transaction có thể trả null

```java
operations.multi();
Object queued = operations.opsForValue().get("diag:472:tx");
// queued có thể là null; reply thực nằm trong operations.exec().
List<Object> replies = operations.exec();
```

Không viết:

```java
operations.multi();
String value = (String) operations.opsForValue().get(key);
if (value == null) {
    // Sai: không thể coi đây là cache miss.
}
operations.exec();
```

Truy vấn trong transaction đã được `QUEUED`, không phải đang trả dữ liệu mới cho Java.

## 9. Dùng SessionCallback để giữ cùng RedisConnection

Spring Data Redis nêu rõ `RedisTemplate` **không bảo đảm** nhiều method gọi rời rạc luôn dùng cùng connection cho transaction. `SessionCallback` cho phép nhiều `RedisOperations` trong cùng session/connection.

Ví dụ:

```java
import java.util.List;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

List<Object> replies = strings.execute(
        new SessionCallback<List<Object>>() {
            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public List<Object> execute(RedisOperations ops)
                    throws DataAccessException {

                ops.multi();
                boolean transactionOpen = true;
                try {
                    ops.opsForValue().set("diag:472:tx", "after");

                    // Giá trị ở đây chưa phải reply GET thật:
                    Object queued = ops.opsForValue()
                            .get("diag:472:tx");

                    List<Object> result = ops.exec();
                    transactionOpen = false;
                    return result;
                } catch (RuntimeException failure) {
                    if (transactionOpen) {
                        try {
                            ops.discard();
                        } catch (RuntimeException cleanupError) {
                            failure.addSuppressed(cleanupError);
                        }
                    }
                    throw failure;
                }
            }
        });

// replies chứa replies của SET và GET sau EXEC.
// Dùng String serializer và kiểm tra từng phần tử theo loại lệnh.
```

Ở đây biến `queued` chỉ để minh họa hiện tượng; không được dùng nó như dữ liệu hiện thời. Nếu chỉ cần ghi `SET` rồi đọc kết quả, gọi `GET` **sau `EXEC` ở ngoài transaction** thường dễ hiểu hơn.

### 9.1. Vì sao phải DISCARD khi lỗi?

Giả sử:

```text
MULTI    -> OK
SET ...  -> QUEUED
Network timeout trước EXEC
```

Connection có thể ở trạng thái transaction chưa hoàn tất. Nếu connection được đưa lại vào pool mà không dọn, những lệnh khác có nguy cơ bị queued hoặc xuất hiện behavior bất ngờ. Vì vậy tài liệu Spring Data Redis khuyến nghị `DISCARD` khi có exception giữa `MULTI` và `EXEC`.

Tuy nhiên, nếu connection đã chết, `DISCARD` cũng có thể thất bại; cần close/evict connection theo cơ chế của driver/pool thay vì chỉ nuốt lỗi. Và nếu timeout xảy ra **sau khi EXEC đã đến Redis**, client có thể không biết transaction đã thực thi hay chưa; `DISCARD` không phải cách rollback writes đã chạy.

### 9.2. Không gọi MULTI trên một template rồi EXEC trên một connection khác

Mẫu nguy hiểm:

```java
strings.multi();
strings.opsForValue().set(key, "new");
List<Object> values = strings.exec();
```

Nếu không có connection binding phù hợp, nhiều method template độc lập không được bảo đảm sử dụng đúng cùng connection. Dùng `SessionCallback` hoặc tích hợp transaction support được cấu hình đúng, đừng giả định sequence method calls luôn pin cùng connection.

## 10. @Transactional không tự bật Redis transaction

Một hiểu lầm:

```java
@Transactional
public void update() {
    databaseRepository.save(entity);
    redisTemplate.opsForValue().set(key, "new");
}
```

**Mặc định `RedisTemplate` không tự tham gia Spring-managed transaction**. Annotations có thể quản lý JDBC/JPA nhưng Redis vẫn gửi `SET` ngay nếu Redis transaction support chưa bật. SQL rollback không tự quay ngược một `SET` đã thành công.

### 10.1. Bật transaction support cho template

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
public class RedisTxConfiguration {

    @Bean
    public StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory factory) {

        StringRedisTemplate template =
                new StringRedisTemplate(factory);
        template.setEnableTransactionSupport(true);
        return template;
    }
}
```

Điều kiện:

- Có **Spring-managed transaction thực sự đang active**.
- Có `PlatformTransactionManager` phù hợp được cấu hình, ví dụ transaction manager của JDBC.
- Lời gọi đi qua proxy/transaction boundary đúng (self-invocation `this.method()` có thể bỏ qua `@Transactional` trong Spring proxy mode).
- Template này là **đúng bean** ứng dụng dùng; không bật trên một template khác rồi kỳ vọng mọi Redis operation tự tham gia.

Spring Data Redis **không cung cấp một Redis PlatformTransactionManager chuyên biệt**; nó tham gia transaction manager đang được ứng dụng sử dụng bằng connection binding/transaction synchronization.

### 10.2. Read-only commands trong Spring-managed transaction

Đây là chỗ dễ hiểu nhầm nhất:

```java
@Transactional
public String example() {
    strings.opsForValue().set("diag:472:managed", "updated");
    return strings.opsForValue().get("diag:472:managed");
}
```

Với Redis transaction support được bật, **write** được queued để thực thi lúc commit. Những **read-only commands** có thể được Spring Data Redis chuyển sang **connection khác không thuộc transaction** để trả lời ngay. Connection đọc đó **không thấy write chưa commit**.

Vì vậy method có thể trả **giá trị cũ hoặc null**, dù transaction sau đó commit đúng. Điều này khác với kỳ vọng “read your writes” bên trong một SQL transaction.

Không coi đây là bằng chứng `SET` thất bại. Nếu nghiệp vụ cần quyết định dựa trên giá trị mới trong cùng thao tác nguyên tử:

- Dùng Lua cho read-check-write.
- Hoặc đọc trước transaction rồi dùng `WATCH` để bảo vệ optimistic consistency.
- Hoặc thay thiết kế để chỉ đọc sau khi Redis transaction hoàn tất.

### 10.3. Commit Redis và JDBC không phải distributed transaction XA

Khi Redis tham gia một Spring-managed transaction, Spring có thể phối hợp callbacks nhưng điều đó **không tạo atomic commit xuyên Redis và database SQL**. Một tài nguyên có thể commit và tài nguyên còn lại thất bại.

Nếu nghiệp vụ cần đồng bộ SQL và Redis, thường:

1. Chọn SQL là nguồn dữ liệu authoritative.
2. Ghi thay đổi trong SQL transaction.
3. Phát outbox event cùng transaction SQL.
4. Worker cập nhật Redis với idempotency/retry/reconciliation.

Đừng dùng `@Transactional` như lời hứa không bao giờ có trạng thái lệch giữa database và Redis.

## 11. WATCH: tại sao EXEC không cập nhật gì?

`WATCH` triển khai optimistic locking: theo dõi một hoặc nhiều key; nếu key bị thay đổi bởi client khác (hoặc expiration/eviction theo semantics Redis version), `EXEC` sẽ **abort** transaction.

```text
Client A                            Client B
  | WATCH counter                     |
  | GET counter -> "10"                |
  |                                   | SET counter "99"
  | MULTI                             |
  | SET counter "11"                  |
  | EXEC -> aborted                   |
  |                                   |
  +-- Không được coi update của A thành công.
```

Redis trả **nil/Null reply cho EXEC** khi WATCH conflict; Spring abstraction có thể biểu diễn thất bại qua kết quả `null` hoặc một dạng result cần kiểm tra theo version/driver. Không tự xem result rỗng là một transaction đã commit.

### 11.1. Đọc trước MULTI trên cùng session

```java
import java.util.List;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

Boolean changed = strings.execute(
        new SessionCallback<Boolean>() {
            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public Boolean execute(RedisOperations ops) {

                String key = "diag:472:cas";
                ops.watch(key);

                boolean transactionOpen = false;
                try {
                    // GET trước MULTI: đọc được giá trị hiện tại.
                    String current = (String) ops.opsForValue().get(key);
                    if (!"old".equals(current)) {
                        ops.unwatch();
                        return false;
                    }

                    ops.multi();
                    transactionOpen = true;
                    ops.opsForValue().set(key, "new");

                    List<Object> outcome = ops.exec();
                    transactionOpen = false;

                    // WATCH conflict -> transaction không commit.
                    return outcome != null && !outcome.isEmpty();
                } catch (RuntimeException error) {
                    if (transactionOpen) {
                        try {
                            ops.discard();
                        } catch (RuntimeException cleanupError) {
                            error.addSuppressed(cleanupError);
                        }
                    } else {
                        try {
                            ops.unwatch();
                        } catch (RuntimeException cleanupError) {
                            error.addSuppressed(cleanupError);
                        }
                    }
                    throw error;
                }
            }
        });
```

Đây là một ví dụ CAS đơn giản; khi nhiều clients cạnh tranh, ứng dụng phải quyết định **retry** với số lần hữu hạn, backoff phù hợp và business-level idempotency. `WATCH` không làm Java có thể đọc reply của `GET` đã QUEUED sau `MULTI`.

### 11.2. WATCH và expiration

Một key hết hạn hoặc bị evict khi đang được `WATCH` có thể làm `EXEC` bị abort. Redis version trước 6.0.9 có khác biệt về việc expiration được tính như thay đổi cho WATCH. Khi so sánh behavior giữa test/prod, hãy xác định Redis version và TTL thực tế.

### 11.3. Không dùng WATCH trong pipeline như một lối đọc giá trị tức thì

Một WATCH-CAS cần:

1. `WATCH`.
2. `GET` nhận **reply thật trước khi quyết định**.
3. Kiểm tra điều kiện ở client.
4. `MULTI`/queued writes.
5. `EXEC`.

Nếu đưa tất cả vào pipeline rồi đọc `GET` bên trong callback, kết quả bị trì hoãn, nên không thể quyết định đúng ở bước 3. Lua thường đơn giản hơn cho những cập nhật chỉ phụ thuộc Redis data.

## 12. Redis transaction có hai loại lỗi rất khác nhau

### 12.1. Lỗi tại thời điểm queue

Ví dụ command không hợp lệ về cú pháp:

```redis
MULTI
SET mykey             # Thiếu argument; Redis báo lỗi khi queue
SET otherkey ok
EXEC
```

Với Redis hiện đại, lỗi queue làm transaction bị đánh dấu invalid; `EXEC` từ chối chạy toàn bộ queue. Nếu đang gỡ lỗi Java, đừng chỉ xem result của `EXEC` mà bỏ qua exception khi chuẩn bị commands.

### 12.2. Lỗi trong lúc EXEC

```redis
SET diag:472:number hello
MULTI
SET diag:472:before ok
INCR diag:472:number
SET diag:472:after ok
EXEC
```

Lúc `EXEC`, `INCR` lỗi vì value `hello` không phải số nguyên. Tuy nhiên những lệnh khác trong transaction có thể **vẫn đã chạy**. Redis không rollback `SET before` hoặc `SET after` vì một command runtime thất bại.

Đây là khác biệt trọng yếu với SQL transaction:

| Trường hợp | Redis transaction |
|---|---|
 `DISCARD` trước EXEC | Bỏ toàn bộ lệnh chưa thực thi |
| Lỗi cú pháp trước EXEC | Transaction có thể bị abort trước khi chạy |
| WATCH conflict | Không thực thi queued commands |
| Một lệnh runtime lỗi trong EXEC | Không rollback các lệnh khác đã thực thi |
| Mất kết nối trước EXEC | Queue chưa EXEC, thông thường không có effects |
| Mất kết nối khi/đúng sau EXEC | Client có thể không biết transaction đã chạy chưa |

**Không biến `DISCARD` thành “ROLLBACK những Redis writes đã commit”.** Sau `EXEC`, DISCARD không thể đảo ngược trạng thái.

## 13. Kết hợp pipeline với MULTI/EXEC

Spring Data Redis cho phép một số dạng `executePipelined(SessionCallback)` có `MULTI`/`EXEC`. Đây là trường hợp có **hai lớp trễ reply**:

```text
Java callback -> MULTI
              -> SET key A     (Redis QUEUED)
              -> GET key       (Redis QUEUED)
              -> EXEC          (Redis trả một array replies)
Pipeline close -> Java đọc danh sách replies
```

Khi dùng kết hợp:

- Không mong `ops.exec()` bên trong callback lập tức trả list như transaction thông thường ngoài pipeline.
- Không giả định `executePipelined` sẽ luôn flatten kết quả `EXEC` thành cùng cấu trúc của một pipeline không có transaction; hãy đối chiếu Spring Data Redis/driver version.
- Không gửi command khác sau transaction trong cùng callback rồi suy đoán index results nếu chưa biết reply shape.
- Không dùng kết hợp này để xử lý những bước cần **lấy output của EXEC rồi quyết định command tiếp theo trong cùng callback**.

### 13.1. Khi nào nên tránh kết hợp?

Nếu mục tiêu là:

1. **Chỉ muốn throughput cao hơn** khi gửi nhiều command độc lập: dùng pipeline đơn.
2. **Muốn các write trên một Redis node thực thi không xen kẽ:** dùng `SessionCallback` + `MULTI/EXEC`.
3. **Muốn đọc–rẽ nhánh–ghi atomic:** dùng Lua hoặc WATCH-CAS.
4. **Muốn cả throughput và transactional group:** cân nhắc pipeline+transaction nhưng thêm tests cho result shape và failure handling.

Đừng dùng pipeline+transaction như tối ưu mặc định nếu chưa benchmark round trips, connection behavior và kết quả cần dùng.

## 14. Khi @Transactional gặp một RedisTemplate khác

Một ứng dụng có thể inject:

```text
redisTemplate (RedisTemplate<Object,Object>)
stringRedisTemplate (StringRedisTemplate)
customCacheTemplate (RedisTemplate<String,DTO>)
```

Nếu chỉ bật `setEnableTransactionSupport(true)` trên `stringRedisTemplate`, không mặc định mọi template còn lại cũng tham gia. Kết quả có thể:

```text
Template A: queued write, được EXEC lúc commit
Template B: immediate write, đã hoàn tất
Template C: serializer khác, thấy key khác hoặc deserialize lỗi
```

Quy trình chẩn đoán:

1. Xác định **bean name/class** thực tế được inject.
2. Xác định connection factory mà mỗi template dùng.
3. Xác định template nào bật transaction support.
4. Kiểm tra transaction manager đang active và propagation.
5. Kiểm tra serializer/key bytes.
6. So sánh hành vi trong cùng session và ngoài session.

Không chỉ nhìn tên `RedisTemplate` để kết luận nó giống `StringRedisTemplate`.

## 15. Connection, thread và transaction lifecycle

Spring-managed Redis transaction dùng connection binding gắn với **thread-bound transaction** trong mô hình imperative. Lỗi có thể xuất hiện khi chuyển công việc qua thread khác:

```java
@Transactional
public void updateInTwoThreads() {
    strings.opsForValue().set("diag:472:one", "A");

    CompletableFuture.runAsync(() ->
            strings.opsForValue().set("diag:472:two", "B"));
}
```

Task `runAsync` chạy trên thread khác, **không tự thừa hưởng transaction context** được Spring bind với thread gọi. Write B có thể chạy ngoài transaction A. Đây là lỗi propagation, không phải pipeline.

Tương tự, `@Async`, scheduler và custom Executor có thể tách scope. Không chia một Redis transaction/session qua nhiều thread tùy ý; chọn một connection/session có lifecycle rõ hoặc thiết kế đơn vị công việc khác.

### 15.1. Connection pool và transaction kẹt trạng thái

Nếu code vào `MULTI` rồi gặp exception trước `EXEC` mà không `DISCARD`, connection được tái sử dụng có thể gây:

- Những lệnh mới nhận phản hồi bất ngờ do vẫn ở transaction state.
- Kết quả operation bị trì hoãn.
- Lỗi hoặc queue không mong muốn.
- Tác dụng phụ bị gom vào một transaction sai.

Chính sách tốt:

1. Dùng `SessionCallback` để quản lý cùng connection.
2. Cleanup `DISCARD` khi transaction chưa hoàn tất.
3. Không tự close connection mà template đang quản lý trong callback.
4. Khi connection lỗi nặng, để driver/pool loại connection không lành mạnh.
5. Test exception path, không chỉ happy path.

## 16. Lettuce và Jedis khác nhau ở một số khả năng

Spring Data Redis có thể chạy với Lettuce hoặc Jedis. Cùng API `RedisTemplate`, nhưng:

- Việc quản lý connection/pooling và auto-flush có thể khác.
- Redis Cluster pipelining phụ thuộc driver và phạm vi lệnh được hỗ trợ theo Spring Data Redis version.
- Các command không hỗ trợ cross-slot có thể lỗi dù standalone chạy được.
- Retry/timeout/read-from-replica có thể làm **thời điểm nhìn thấy data** khác nhau.

Lettuce có `PipeliningFlushPolicy` cho phép điều khiển mức flush batch trong một số phiên bản Spring Data Redis. Ví dụ minh họa:

```java
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.connection.lettuce
        .LettuceConnection.PipeliningFlushPolicy;

// Chỉ minh họa API ở các phiên bản hỗ trợ:
LettuceConnectionFactory factory = ...;
factory.setPipeliningFlushPolicy(
        PipeliningFlushPolicy.buffered(3));
```

Flush policy ảnh hưởng việc gửi commands, **không biến pipeline thành transaction**. Khi debug, cố định driver/configuration và dùng integration test phù hợp; đừng kết luận behavior từ một adapter khác.

### 16.1. Không đồng nhất pipeline với MGET

`MGET key1 key2` là **một Redis command** trả một array. Pipeline gồm `GET key1` và `GET key2` là **hai commands**; có thể có cùng dữ liệu trong điều kiện bình thường nhưng semantics/ACL/Cluster restrictions khác.

Với Cluster:

- `MGET` trên các keys khác slot có thể bị `CROSSSLOT`.
- Hai `GET` riêng lẻ có thể route tới hai masters tùy driver.
- Pipeline trên nhiều nodes có hỗ trợ/giới hạn driver-specific.

Đừng chỉ nhìn `List<Object>` của Java rồi kết luận “cùng một thao tác”.

## 17. Redis Cluster: vì sao lệnh chạy riêng nhưng transaction lỗi?

Redis Cluster chia key theo **16.384 hash slots**. Transaction hoặc Lua nhiều key có ràng buộc cùng slot.

```text
diag:472:order:{913}:state
diag:472:order:{913}:total
                 |
             hash tag {913}
                 |
              same slot

diag:472:order:{914}:state
                 |
             different slot
```

Nếu transaction bao gồm keys ở các slot khác nhau, Redis có thể trả `CROSSSLOT` hoặc driver từ chối/không hỗ trợ grouping. Dùng hash tag có chủ đích cho dữ liệu cần atomic multi-key, không gom toàn hệ thống vào một hash tag vì sẽ tạo hot slot.

### 17.1. Checklist Cluster

1. Redis connection thực sự là Standalone, Sentinel hay Cluster?
2. Các keys trong `MULTI/EXEC` có cùng slot?
3. Có dùng cùng `StringRedisSerializer` cho key không?
4. Có command cross-slot không được driver hỗ trợ?
5. Redis Cluster topology/slot mapping có vừa thay đổi không?
6. Client có redirect `MOVED`/`ASK` và retry đúng không?
7. Test Standalone có che giấu lỗi Cluster không?

Nếu pipeline trả kết quả khác theo node, kiểm tra read preference. Một `GET` đọc replica có thể thấy dữ liệu cũ hơn master do asynchronous replication; đó là consistency model, không nhất thiết lỗi serialization.

## 18. Reactive Redis không có cùng giả định thread-bound

`ReactiveRedisTemplate`/`ReactiveStringRedisTemplate` trả Publisher. Trong reactive:

```java
Mono<String> mono =
        reactiveStrings.opsForValue().get("diag:472:first");
```

`mono` chưa phải `String`. Lệnh được phát theo subscription; một `StepVerifier` hoặc subscriber sẽ nhận giá trị:

```java
StepVerifier.create(
        reactiveStrings.opsForValue().get("diag:472:first"))
    .expectNext("alpha")
    .verifyComplete();
```

Đừng so sánh trực tiếp `Mono<String>` với `String` hoặc gọi `subscribe()` rồi lập tức assert một biến bên ngoài: đó là lỗi **async sequencing**.

### 18.1. @Transactional imperative không tự bao phủ reactive chain

Spring reactive transaction sử dụng **Reactor Context**, không phải mặc định cùng ThreadLocal của imperative transaction manager. Một method trộn `@Transactional` JDBC, `RedisTemplate` và `ReactiveRedisTemplate` không tự tạo một transaction nhất quán xuyên tất cả tài nguyên.

Muốn nhóm các Redis reactive operations theo một connection/session, phải dùng API/session support được **phiên bản Spring Data Redis reactive** hỗ trợ và kiểm chứng tại Redis thật. Không sao chép nguyên mẫu `RedisTemplate.multi()/exec()` sang reactive rồi giả định semantics giống hệt.

### 18.2. Pipeline khác concurrency của reactive Flux

`flatMap` nhiều Redis commands đồng thời có thể tăng concurrency nhưng không đồng nghĩa với `executePipelined` dùng một connection/batch có kiểm soát. Thứ tự hoàn tất của nhiều Publisher có thể khác thứ tự phát, và `collectList()` có thể gom lượng dữ liệu rất lớn. Dùng `concatMap` hoặc ordering phù hợp khi nghiệp vụ yêu cầu, giới hạn concurrency và đo network.

## 19. Timeout: kết quả không rõ không đồng nghĩa command chưa chạy

Một giao dịch:

```text
Java -------- MULTI/SET/EXEC -------> Redis
Java <--- timeout / connection lost --+
Redis đã thực thi EXEC, nhưng reply không tới Java
```

Từ góc nhìn client, kết quả là **unknown outcome**. Nếu tự retry toàn bộ transaction, có thể thực thi writes hai lần. Với `INCR`, số đếm có thể tăng hai; với `LPUSH`, message có thể bị thêm hai lần. Đừng giải thích exception timeout là “Redis chắc chắn chưa ghi”.

Giải pháp phụ thuộc nghiệp vụ:

- Có `requestId`/idempotency key khi thao tác có side effect.
- Chọn lệnh idempotent khi có thể (ví dụ `SET key sameValue` không giống `INCR`).
- Ghi log transaction ID và thực hiện reconcile.
- Giới hạn số lần retry/backoff.
- Với nhu cầu exactly-once effect xuyên Redis và DB khác, thiết kế authoritative ledger/outbox thay vì chỉ retry Redis.

### 19.1. Tránh retry sau kết quả null trong callback

`null` trong callback pipeline/transaction là **hành vi bình thường**, không phải dấu hiệu cần retry. Retry dựa trên nó có thể làm tăng requests/commands ngoài ý muốn.

Chỉ đánh giá retry sau khi đã nhận reply cuối hoặc exception rõ ở transaction/pipeline boundary, cùng chính sách idempotency.

## 20. ACL và quyền command khi chuyển sang pipeline/transaction

Một service có quyền `+get +set ~app:*` chạy lệnh thường tốt nhưng thêm transaction có thể cần:

```text
+multi
+exec
+discard
+watch
+unwatch
```

Nếu dùng Lua thay transaction, có thể cần `EVAL`/`EVALSHA` và những lệnh script thực thi. Command/key permissions vẫn bị Redis ACL kiểm tra; pipeline không bypass ACL.

### 20.1. Chẩn đoán NOPERM

Phân biệt:

- `NOPERM` ngay khi queue một command thuộc transaction.
- `NOPERM` với `MULTI`/`EXEC` vì tài khoản thiếu command.
- `NOPERM` ở key pattern do key serializer/prefix thay đổi.
- `NOPERM` cho command phụ trợ của driver/health.

Không mở `+@all ~*` chỉ vì migration sang pipeline/transaction gây lỗi. Dùng `ACL LOG` và, với Redis 7+, `ACL DRYRUN` trên môi trường kiểm soát để xác định quyền cần bổ sung.

## 21. Bảng chẩn đoán theo từng bước

Khi phát hiện kết quả khác thao tác thường, dùng quy trình:

### Bước 1 — Ghi lại môi trường

```text
Spring Boot version:
Spring Data Redis version:
Client: Lettuce / Jedis:
Redis server version:
Topology: Standalone / Sentinel / Cluster:
Template bean:
Connection factory:
Key / value / hash serializers:
setEnableTransactionSupport:
Active @Transactional / PlatformTransactionManager:
```

Không có các thông tin này, rất dễ suy đoán sai vì defaults/overloads thay đổi theo phiên bản.

### Bước 2 — Chạy một lệnh đơn làm baseline

Trên Redis test/namespace test:

```java
String expected = strings.opsForValue().get("diag:472:first");
```

Nếu baseline đã sai, hãy kiểm tra **key tồn tại, Redis type, serializer, TTL, host/DB/slot** trước khi kết luận pipeline/transaction có lỗi.

### Bước 3 — Xác nhận command có thực sự được enqueue

Trong pipeline, callback phải phát lệnh và `return null`. Trong transaction, phải thấy `multi`, queued commands rồi `exec`. Nếu exception xảy ra trước `exec`, kiểm tra `DISCARD` cleanup.

### Bước 4 — Quan sát kết quả ở đúng boundary

```text
Pipeline      -> result của executePipelined(...)
Manual TX     -> result của operations.exec()
Managed TX    -> sau transaction completion, đọc ngoài transaction
Reactive      -> subscribe/StepVerifier được hoàn tất
```

Không lấy biến tạm được gán trong callback làm kết quả cuối.

### Bước 5 — Kiểm tra kiểu kết quả

Log **class và index** của từng phần tử trong danh sách test (tránh log payload nhạy cảm):

```java
for (int i = 0; i < replies.size(); i++) {
    Object item = replies.get(i);
    System.out.printf(
            "reply[%d] type=%s%n",
            i,
            item == null ? "null" : item.getClass().getName());
}
```

Nếu reply là `byte[]`, không in thẳng `toString()` (nó tạo chuỗi định danh mảng Java). Dùng serializer tương ứng hoặc hex dump **trên dữ liệu lab**, không in session/token của khách hàng.

### Bước 6 — So sánh kết quả vật lý trên Redis

```redis
TYPE diag:472:first
GET diag:472:first
TYPE diag:472:count
GET diag:472:count
PTTL diag:472:first
```

Nếu key là Hash, dùng `HGET`/`HGETALL` thay cho `GET`. Trong Cluster, CLI phải kết nối tới đúng node/route, ví dụ dùng `redis-cli -c` khi cần redirect.

### Bước 7 — Kiểm tra môi trường cạnh tranh

Với WATCH conflict, kiểm tra writers khác, expiration/eviction và retry. Với pipeline, kiểm tra các command có phụ thuộc nhau không, pipeline có chạy đồng thời với clients khác không. Pipeline **không chặn** clients khác xen giữa các lệnh.

### Bước 8 — Viết integration test tái hiện tối thiểu

Một test có **hai keys String cố định và một `GET`/`INCR`** thường dễ phân lập lỗi hơn toàn bộ nghiệp vụ trong một controller. Sau khi hiểu semantics, mới mở rộng sang pipeline/batch nhiều phần tử.

## 22. Quan sát Redis/driver mà không gây tác động lớn

Các lệnh quan sát phù hợp tài khoản vận hành:

```bash
redis-cli -h 127.0.0.1 -p 6379 INFO server
redis-cli -h 127.0.0.1 -p 6379 INFO clients
redis-cli -h 127.0.0.1 -p 6379 INFO commandstats
redis-cli -h 127.0.0.1 -p 6379 SLOWLOG GET 10
redis-cli -h 127.0.0.1 -p 6379 LATENCY LATEST
```

`SLOWLOG` phản ánh thời gian Redis xử lý command; nó **không bao gồm toàn bộ network latency hoặc thời gian Java deserialize**. Một pipeline lớn có thể làm JVM dùng nhiều memory để gom replies, dù Redis command time từng lệnh thấp.

### 22.1. MONITOR chỉ dùng cẩn thận

`MONITOR` cho luồng commands liên tục, có thể gây overhead và lộ tên key/payload/metadata nhạy cảm. Không bật lâu trên production chỉ để tìm nguyên nhân một `null`. Nếu cần, dùng Redis lab, giới hạn thời gian và dữ liệu test.

### 22.2. Driver logs và trace

Khi cần:

- Bật logging phù hợp cho Spring Data Redis/Lettuce/Jedis ở môi trường test.
- Ghi thời điểm bắt đầu/kết thúc pipeline và `EXEC`.
- Gắn trace ID cho request và Redis command batch.
- Ghi connection endpoint/node và topology events, không ghi credentials.
- Đo số commands/batch, số replies và thời gian deserialize.

Đừng đánh đồng log “command queued” với log “Redis đã thực thi và phản hồi thành công”.

## 23. Testcontainers: kiểm thử ba đường đi trên Redis thật

Mock RedisTemplate không thể xác nhận transaction/pipeline semantics của server. Với Testcontainers, có thể tái hiện `null`, reply list, `WATCH` conflict và loại serializer ngay trên Redis test.

### 23.1. Dependency Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
```

### 23.2. Redis container và Spring properties

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class RedisTxPipelineIntegrationTest {

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
}
```

Đặt các test trong class có application context Spring Boot hợp lệ. Image Redis chỉ để lab; hãy pin/version theo chính sách CI. Testcontainers yêu cầu Docker hoặc container runtime tương thích.

### 23.3. Test 1 — baseline vs pipeline result

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

@Autowired
StringRedisTemplate strings;

@Test
void pipelineReturnsRepliesAfterCallback() {
    String id = UUID.randomUUID().toString();
    String a = "it:472:" + id + ":a";
    String b = "it:472:" + id + ":b";

    strings.opsForValue().set(a, "alpha");
    strings.opsForValue().set(b, "beta");

    try {
        assertThat(strings.opsForValue().get(a)).isEqualTo("alpha");

        List<Object> replies = strings.executePipelined(
                new SessionCallback<Object>() {
                    @Override
                    @SuppressWarnings({"rawtypes", "unchecked"})
                    public Object execute(RedisOperations ops) {
                        Object immediateA = ops.opsForValue().get(a);
                        Object immediateB = ops.opsForValue().get(b);
                        assertThat(immediateA).isNull();
                        assertThat(immediateB).isNull();
                        return null;
                    }
                });

        assertThat(replies).containsExactly("alpha", "beta");
    } finally {
        strings.delete(a);
        strings.delete(b);
    }
}
```

Test này cố tình assert `null` **trong callback** và data chính xác **ngoài callback**. Đây là hành vi cần hiểu, không phải một bug.

### 23.4. Test 2 — manual transaction results

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.List;

@Test
void execReturnsQueuedCommandReplies() {
    String key = "it:472:" + UUID.randomUUID();
    try {
        List<Object> replies = strings.execute(
                new SessionCallback<List<Object>>() {
                    @Override
                    @SuppressWarnings({"rawtypes", "unchecked"})
                    public List<Object> execute(RedisOperations ops) {
                        ops.multi();
                        boolean active = true;
                        try {
                            ops.opsForValue().set(key, "new");
                            Object inside = ops.opsForValue().get(key);
                            assertThat(inside).isNull();

                            List<Object> outcome = ops.exec();
                            active = false;
                            return outcome;
                        } catch (RuntimeException e) {
                            if (active) {
                                try {
                                    ops.discard();
                                } catch (RuntimeException ignored) {
                                    // Connection lỗi vẫn phải để test thất bại
                                    // với root cause gốc.
                                }
                            }
                            throw e;
                        }
                    }
                });

        assertThat(replies).hasSize(2);
        assertThat(replies.get(1)).isEqualTo("new");
        assertThat(strings.opsForValue().get(key)).isEqualTo("new");
    } finally {
        strings.delete(key);
    }
}
```

Không ép `replies.get(0)` của `SET` thành một kiểu status cố định nếu chưa đối chiếu API/version; assertion `GET` và dữ liệu sau commit hữu ích hơn.

### 23.5. Test 3 — WATCH conflict

Trong Redis test riêng:

1. Client A dùng `SessionCallback` gọi `WATCH key` và đọc giá trị cũ.
2. Đồng bộ với Client B bằng `CountDownLatch` để B sửa key sau lúc A đã WATCH.
3. Client A gọi `MULTI`, queue một SET rồi `EXEC`.
4. Kiểm tra A **không** overwrite giá trị B.
5. Đọc lại kết quả EXEC/collision theo Spring/driver version.

**Không dùng sleep cố định** để “hy vọng B ghi đúng lúc”. Latch/barrier làm conflict tái hiện đáng tin; nên dùng hai Redis connections độc lập trong test. Test phải có timeout và cleanup để không treo CI.

### 23.6. Test 4 — lỗi runtime không rollback

1. Set một key String `number` thành `"not-a-number"`.
2. Trong `MULTI`, queue `SET before ok`, `INCR number` và `SET after ok`.
3. `EXEC`.
4. Quan sát lỗi của `INCR` và tình trạng `before`/`after`.
5. Giải thích vì sao Redis transaction không có SQL-style rollback.

Tùy client abstraction, lỗi Redis trong EXEC có thể được thể hiện ở `List<Object>` hoặc được ném dưới dạng exception. Đừng thiết kế test chỉ dựa vào exception type mà chưa biết phiên bản adapter.

### 23.7. Test 5 — serialization và replies

1. Ghi dữ liệu bằng `StringRedisTemplate` và đọc pipeline bằng String serializer.
2. Ghi JSON DTO bằng template typed JSON.
3. Kiểm tra pipeline result deserialization cho key/value/hash.
4. Dùng serializer sai để tái hiện exception.
5. Dùng overload `executePipelined(..., resultSerializer)` và chứng minh kết quả đúng sau khi chọn format phù hợp.

### 23.8. Test 6 — managed @Transactional

1. Tạo một `StringRedisTemplate` có `setEnableTransactionSupport(true)`.
2. Dùng một `PlatformTransactionManager` thực sự và `TransactionTemplate`/Spring proxy.
3. Ghi Redis trong transaction, đọc trước commit bằng connection không thuộc transaction.
4. Sau commit, đọc lại value.
5. Cố ý rollback, xác nhận Redis queued writes không được thực thi nếu transaction chưa đến commit.
6. Nhấn mạnh test không chứng minh atomic commit giữa Redis và SQL.

## 24. Phân tích chi phí: pipeline không phải lúc nào cũng nhanh hơn

Pipeline giảm round trips nhưng vẫn có chi phí:

- Redis phải nhận/xử lý các commands.
- Redis có thể cần buffer nhiều replies khi client chưa đọc.
- Spring Data Redis phải giữ `List<Object>` chứa nhiều kết quả.
- JVM có thể cấp phát nhiều byte arrays, Strings/DTOs và GC.
- Một batch quá lớn có thể tăng memory, gây latency spike.
- Khi script/command O(N) nằm trong batch, pipeline không làm lệnh đó bớt tốn CPU.

Ví dụ batch 100.000 GET value lớn dễ tốn RAM Redis/client. Thay vì tăng batch vô hạn, dùng:

1. Batch vừa phải theo thí nghiệm.
2. Đo throughput và p95/p99, not just average.
3. Giới hạn payload bytes/response.
4. Dọn tài nguyên và xử lý lỗi từng batch.
5. Nếu không cần replies, chọn API phù hợp để tránh gom dữ liệu không sử dụng, theo Spring Data Redis version.

### 24.1. Pipeline không bảo đảm snapshot nhất quán

Một pipeline:

```text
GET account:balance
GET account:status
```

không tự bảo đảm hai giá trị đại diện cho **cùng một thời điểm** nếu writers khác có thể cập nhật giữa các lệnh. Nếu cần consistent view theo semantics Redis, dùng transaction/Lua hoặc thiết kế dữ liệu versioned thích hợp. Pipelining chỉ là tối ưu cách truyền lệnh/reply.

## 25. Ma trận lỗi và cách sửa

| Hiện tượng | Nguyên nhân có khả năng | Cách xác nhận | Cách sửa |
|---|---|---|---|
| `null` từ `get` trong pipeline callback | Reply bị trì hoãn | `executePipelined` trả danh sách có dữ liệu | Đọc kết quả bên ngoài callback |
| Callback pipeline trả object nhưng API lỗi | Callback phải trả null | Xem contract `executePipelined` | `return null` |
| Pipeline list có `Long` thay `String` | Command là `INCR`/`TTL` | In type mỗi reply ở lab | Dùng `Number`/kiểu phù hợp |
| Pipeline list là bytes không decode | RedisCallback raw hoặc sai serializer | So sánh bytes và template serializers | Dùng đúng result serializer |
| `GET` sau `MULTI` là null | Command chỉ QUEUED | `EXEC` trả GET reply | Đọc từ result EXEC |
| `GET` trong @Transactional thấy giá trị cũ | Write deferred, read trên connection khác | Đọc lại sau commit | Không kỳ vọng read-your-writes |
| @Transactional nhưng Redis ghi ngay | Transaction support chưa bật | Xem bean/config | `setEnableTransactionSupport(true)` và manager |
| Lệnh tx trên connection khác nhau | Gọi template rời rạc | Dùng SessionCallback | Gắn connection cùng session |
| EXEC abort | WATCH conflict | Test hai connections | Retry bounded và idempotency |
| Transaction không rollback sau WRONGTYPE | Runtime error trong EXEC | Đọc state sau EXEC | Chọn Lua/validation và compensation |
| Connection có biểu hiện vẫn ở MULTI | Không DISCARD sau exception | Xem lifecycle/log | Cleanup/evict connection lỗi |
| MGET riêng chạy nhưng multi-key lỗi | Cross-slot Redis Cluster | `CLUSTER KEYSLOT` | Same-slot key design |
| Pipeline Cluster không hỗ trợ lệnh | Driver/version limitation | So sánh Lettuce/Jedis/standalone | Chọn API/driver/topology tương thích |
| Chỉ một vài keys trả null | Key bytes/prefix/serializer khác | Redis raw CLI/serialization | Đọc đúng key bytes |
| Redis client NOPERM sau bật tx | Thiếu MULTI/EXEC/WATCH hoặc key rule | ACL LOG/DRYRUN | Cho phép command tối thiểu |
| Timeout rồi retry làm counter tăng đôi | EXEC có thể đã chạy nhưng reply mất | Request ID/reconcile | Idempotency, bounded retry |
| Reactive test lúc đúng lúc sai | Chưa subscribe/chờ Publisher | StepVerifier | Dùng reactive test properly |
| Pipeline batch làm memory tăng | Gom nhiều replies | JVM/Redis memory metrics | Chia batch, giới hạn value |

## 26. Bài thực hành chẩn đoán

### Bài 1 — Null trong callback không phải cache miss

1. Ghi `SET it:472:a alpha`.
2. Đọc bằng `StringRedisTemplate.opsForValue().get`, xác nhận `"alpha"`.
3. Gọi cùng lệnh trong `executePipelined`, in giá trị được trả ngay.
4. In danh sách `executePipelined` trả ra ngoài callback.
5. Giải thích khác biệt về thời điểm nhận reply.

### Bài 2 — Chọn SessionCallback hay RedisCallback

1. Viết pipeline hai GET bằng `SessionCallback`.
2. Viết pipeline tương đương bằng `RedisCallback` với UTF-8 `byte[]`.
3. Thử key được lưu dưới serializer khác.
4. So sánh `List<Object>` và cách decode.
5. Ghi lại khi nào nên dùng callback ở mức template hoặc connection.

### Bài 3 — MULTI/EXEC không trả giá trị ngay

1. Trong một `SessionCallback` gọi `multi()`.
2. Queue `SET` và `GET` cùng key.
3. Ghi nhận kết quả `get()` trong callback.
4. Gọi `exec()` và xem replies.
5. Đọc key lại ngoài transaction.
6. Thử `discard()` trước `exec()` trong một transaction khác để thấy queued write không chạy.

### Bài 4 — @Transactional và read-your-writes

1. Bật Redis transaction support cho đúng template.
2. Đăng ký transaction manager.
3. Ghi và đọc cùng key trong một method transaction.
4. Đọc lại sau commit.
5. Giải thích vì sao read-only Redis command có thể dùng connection khác.
6. Thử rollback trước commit và xác nhận queued write không chạy.

### Bài 5 — WATCH conflict có kiểm soát

1. Client A WATCH một key và đọc giá trị hiện tại.
2. Client B sửa key.
3. Client A MULTI, queue SET và EXEC.
4. Quan sát transaction bị abort, key giữ giá trị của B.
5. Viết bounded retry và so sánh với Lua CAS.

### Bài 6 — Runtime error không rollback

1. Đặt key `number="hello"`.
2. Transaction queue `SET before ok`, `INCR number`, `SET after ok`.
3. Gọi EXEC.
4. Kiểm tra state thực và error reply/exception.
5. Giải thích khác biệt lỗi queue-time và execution-time.

### Bài 7 — Pipeline kết hợp transaction

1. Dùng `executePipelined(SessionCallback)` với `multi()/exec()` trên Redis test.
2. Ghi nhận callback return và danh sách pipeline replies.
3. So sánh với `execute(SessionCallback)` transaction không pipeline.
4. Kiểm tra nested/flat result shape theo version Spring Data Redis đang chạy.
5. Không hardcode indexes nếu chưa xác định mapping replies.

### Bài 8 — Redis Cluster và serialization

1. Dùng Redis Cluster lab với nhiều master.
2. Tạo hai key cùng hash tag và hai key khác hash tag.
3. So sánh `GET` đơn lẻ, `MGET` và transaction multi-key.
4. Kiểm tra `CLUSTER KEYSLOT` và connection routing.
5. Thay key serializer trong lab và xem slot thay đổi thế nào.

### Bài 9 — Timeout và retry

1. Mô phỏng lỗi mất response từ Redis ở môi trường test.
2. Dùng `INCR` để thấy tác dụng phụ có thể đã xảy ra.
3. Retry không idempotent, quan sát counter có thể tăng lần nữa.
4. Thiết kế request ID/ledger phù hợp với nghiệp vụ.
5. Chia các exception thành retryable, non-retryable và unknown outcome.

## 27. Checklist khi sửa lỗi production

**Kết quả và semantics**

1. Đây là lệnh thường, pipeline, manual transaction hay managed @Transactional?
2. Có đọc giá trị của lệnh bên trong callback khi reply vẫn bị trì hoãn không?
3. Có lấy kết quả từ đúng `executePipelined` hoặc `exec` không?
4. Callback pipeline có `return null` không?
5. Có dựa trên một index trong `List<Object>` mà callback vừa thay đổi command không?
6. Có kiểm tra kiểu `Long`/`String`/`byte[]`/`Map` đúng từng command?

**Connection và serialization**

7. Có sử dụng cùng `SessionCallback`/connection cho MULTI/EXEC?
8. Template nào thực sự được inject, nó dùng factory nào?
9. Transaction support đã bật trên **đúng template** chưa?
10. Có active Spring-managed transaction và transaction manager phù hợp?
11. Có thread hop làm mất thread-bound context không?
12. Có cleanup DISCARD khi exception giữa MULTI và EXEC?
13. Key/value/hash serializers và result serializer có nhất quán?

**Tính đúng dữ liệu**

14. WATCH conflict có được phát hiện và xử lý không?
15. Có phân biệt queue-time với execution-time error không?
16. Có tránh giả định Redis transaction rollback như SQL không?
17. Có ý thức về unknown outcome khi timeout quanh EXEC?
18. Có yêu cầu atomic read-check-write mà pipeline không đáp ứng?
19. Có xét Redis replica lag và key expiration khi debug?

**Topology và vận hành**

20. Có đúng Redis Standalone/Sentinel/Cluster topology?
21. Các keys nhiều lệnh có cùng slot khi cần?
22. Driver/Lettuce/Jedis/Spring version có hỗ trợ kiểu pipeline đó?
23. Redis ACL user có quyền MULTI/EXEC/WATCH và các commands bên trong?
24. Có integration test Redis thật và positive/negative cases?
25. Có đo batch size, memory, timeout, p99 và số commands/replies?

## 28. Kết luận

Trong Spring Data Redis, **`null` bên trong pipeline hoặc transaction callback thường chỉ phản ánh “reply chưa đến thời điểm sẵn sàng”**, không nhất thiết là Redis key không tồn tại. Pipeline gom replies vào `executePipelined(...)`; Redis transaction queue commands giữa `MULTI` và `EXEC`, trả reply cuối tại `EXEC`; `SessionCallback` giúp giữ một connection cho cả chuỗi thao tác.

Khi kết quả ngoài callback vẫn sai, hãy kiểm tra **serializer**, kiểu reply, thứ tự lệnh, `@Transactional`/transaction support, connection binding và `WATCH` conflict. Đừng nhầm pipeline với atomicity, đừng kỳ vọng Redis transaction rollback runtime errors như SQL và đừng suy ra Redis đã không thực thi chỉ vì client timeout.

Phương pháp chẩn đoán hiệu quả nhất là xây **baseline một lệnh thường trên Redis test**, đặt cùng command vào pipeline/transaction, lấy reply ở đúng boundary và quan sát key/value thực, rồi bổ sung integration tests cho WATCH, serializer, Cluster và exception paths. Phần lớn lỗi “Redis trả kết quả khác” sẽ trở thành một khác biệt semantics có thể giải thích và kiểm thử được.

## Tài liệu tham khảo

- [Spring Data Redis — Pipelining](https://docs.spring.io/spring-data/redis/reference/redis/pipelining.html): `executePipelined`, `RedisCallback`/`SessionCallback`, kết quả và serializer.
- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): `MULTI/EXEC`, connection binding và `@Transactional`.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): template, RedisConnection và serialization.
- [Spring Data Redis — RedisOperations API](https://docs.spring.io/spring-data/redis/reference/3.5/api/java/org/springframework/data/redis/core/RedisOperations.html): SessionCallback, pipeline, transaction và EXEC.
- [Spring Data Redis — RedisTemplate API](https://docs.spring.io/spring-data/redis/reference/3.5/api/java/org/springframework/data/redis/core/RedisTemplate.html): overload `executePipelined` và serializer.
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/): `MULTI`, `EXEC`, `DISCARD`, `WATCH` và lỗi/rollback.
- [Redis — MULTI](https://redis.io/docs/latest/commands/multi/): queue Redis commands.
- [Redis — EXEC](https://redis.io/docs/latest/commands/exec/): thực thi transaction và reply.
- [Redis — WATCH](https://redis.io/docs/latest/commands/watch/): optimistic locking.
- [Redis — Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/): giảm network round trips.
- [Redis — ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): command permissions và key patterns.
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots, multi-key và routing.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): kiểm thử publisher reactive.
- [Testcontainers — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): integration test với Redis thực.

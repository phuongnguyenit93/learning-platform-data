# Khai báo RedisScript và DefaultRedisScript trong Spring Data Redis

Khi làm việc với Redis, ứng dụng thường phải thực hiện một chuỗi thao tác có điều kiện: đọc một khóa, kiểm tra giá trị rồi cập nhật hoặc xóa khóa đó. Nếu tách thành nhiều lời gọi từ Java, dữ liệu có thể thay đổi **giữa các lệnh**, khiến kết quả không còn đúng dù mỗi lệnh Redis riêng lẻ đều thành công.

**Lua scripting** cho phép gửi một đoạn chương trình ngắn đến Redis để thực hiện nhiều bước liên tiếp theo cơ chế thực thi nguyên tử trên server. Trong Spring Data Redis, hai thành phần quan trọng nhất để gọi Lua script là:

- `RedisScript<T>`: hợp đồng mô tả script và kiểu kết quả mà Java mong đợi;
- `DefaultRedisScript<T>`: implementation thông dụng để khai báo nội dung script, đường dẫn resource và kiểu trả về.

Một lần khai báo `RedisScript` có thể được tái sử dụng từ service, còn `RedisTemplate.execute(...)` chịu trách nhiệm truyền khóa, tham số và chuyển đổi kết quả. Bài này trình bày từ cơ chế Redis đến cách cấu hình và sử dụng thực tế trong ứng dụng Spring.

## 1. Vì sao cần Lua script nếu Redis đã có nhiều lệnh nguyên tử?

Một số lệnh Redis như `INCR`, `SET key value NX EX ...` hoặc `HINCRBY` vốn đã nguyên tử ở cấp **một lệnh**. Với chúng, thông thường không cần tạo Lua script chỉ để làm điều lệnh đơn đã hỗ trợ.

Vấn đề xuất hiện khi kết quả của bước trước quyết định bước sau:

```text
Ứng dụng A                       Redis                     Ứng dụng B
    |                              |                            |
    |--- GET item:stock ---------->|                            |
    |<-- 1 ------------------------|                            |
    |                              |<--- GET item:stock ---------|
    |                              |---- 1 --------------------->|
    |--- DECR item:stock --------->|                            |
    |                              |<--- DECR item:stock --------|
    |                              |
    v                              v                            v
                   Tồn kho có thể bị giảm quá giới hạn
```

Nếu cả hai ứng dụng đều kiểm tra tồn kho còn 1 rồi mới giảm bằng lệnh tiếp theo, kiểm tra và cập nhật **không còn là một đơn vị nguyên tử**. Ngay cả khi Redis xử lý từng lệnh tuần tự, hai chuỗi lệnh từ các client vẫn có thể xen kẽ nhau.

Lua script có thể kết hợp kiểm tra và cập nhật:

```lua
local current = tonumber(redis.call('GET', KEYS[1]) or '0')

if current <= 0 then
    return 0
end

redis.call('DECR', KEYS[1])
return 1
```

Khi Redis thực thi script, các command của client khác không xen vào giữa các bước Redis command do script đó gọi. Vì vậy việc đọc điều kiện rồi giảm tồn kho cùng nằm trong một lần thực thi nguyên tử, với điều kiện các khóa và lệnh tuân theo quy định Redis.

Điểm cần phân biệt: **nguyên tử về khả năng quan sát/xen kẽ** không đồng nghĩa **có rollback như SQL**. Nếu script đã thay đổi một khóa rồi phát sinh lỗi runtime ở bước sau, Redis không tự hoàn tác những thay đổi đã được thực hiện.

## 2. RedisScript và DefaultRedisScript đóng vai trò gì?

Ở phía Redis, Lua được thực thi thông qua các command như `EVAL` và `EVALSHA`. Ở phía Java, Spring Data Redis cung cấp đối tượng biểu diễn script để application không phải tự ghép câu lệnh thô tại từng nơi gọi.

| Thành phần | Vai trò | Cách sử dụng điển hình |
|---|---|---|
| `RedisScript<T>` | Giao diện biểu diễn mã Lua và kiểu kết quả `T` | Khai báo kiểu của bean và tham số service |
| `DefaultRedisScript<T>` | Implementation thông dụng, quản lý source script và SHA1 | Khởi tạo bean, cấu hình resource và result type |
| `ClassPathResource` | Chỉ tới tệp `.lua` đóng gói trong classpath | `new ClassPathResource("redis/scripts/...")` |
| `RedisTemplate<K,V>` | Thực thi script, serialize khóa và tham số | `template.execute(script, keys, args...)` |
| `StringRedisTemplate` | Template với key/value dạng chuỗi | Ví dụ Redis key và `ARGV` là chuỗi UTF-8 |
| Redis server | Chạy Lua trên keyspace được truy cập | `EVALSHA` hoặc `EVAL`, thực thi command trong script |

Ví dụ khai báo typed contract:

```java
RedisScript<Long> script;
```

Kiểu `Long` ở đây nói rằng kết quả cuối cùng, sau khi Redis và Spring Data xử lý, được mong đợi là một số nguyên Java. Đây **không phải** là kiểu của key, cũng không phải kiểu dữ liệu của toàn bộ Redis value đang bị script cập nhật.

Khi dùng `DefaultRedisScript<Long>`, những thuộc tính cần hiểu là:

- **Script source**: nội dung Lua, lấy từ resource hoặc chuỗi;
- **Result type**: lớp Java mà Spring Data dùng để chọn cách giải mã kết quả;
- **SHA1**: dấu vân tay của nội dung script dùng khi thực thi qua `EVALSHA`;
- **Lifecycle**: có thể tạo một bean duy nhất và sử dụng lại trong nhiều lần gọi.

Thực tế nên khai báo script dùng thường xuyên như một **singleton bean**, vì điều đó tránh phải tải và tính lại metadata script không cần thiết ở mỗi lời gọi Java.

## 3. Ví dụ hoàn chỉnh: chỉ xóa khóa khi giá trị còn khớp

Xét một khóa giữ giá trị nhận diện yêu cầu đang sở hữu quyền thao tác:

```text
key   = process:lock:{job-42}
value = request-unique-token-A
```

Khi kết thúc công việc, application chỉ được xóa khóa nếu giá trị hiện tại **vẫn bằng token của chính mình**. Nếu khóa đã hết hạn rồi được một request khác tạo lại với token mới, request cũ không được xóa khóa của request mới.

Cách ngây thơ:

```java
String current = redis.opsForValue().get(key);

if (expectedToken.equals(current)) {
    redis.delete(key);
}
```

Giữa `GET` và `DEL`, khóa có thể hết hạn hoặc bị thay đổi bởi client khác. Lua xử lý kiểm tra và xóa trong **cùng một lần thực thi tại Redis**.

### 3.1. Viết script trong tệp classpath

Tạo tệp tại:

```text
src/main/resources/redis/scripts/delete-if-value-matches.lua
```

Nội dung Lua:

```lua
-- KEYS[1]: tên khóa cần xóa
-- ARGV[1]: token mà bên gọi kỳ vọng khóa đang lưu

if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end

return 0
```

Ở đây:

- `KEYS[1]` là tên Redis key thực sự.
- `ARGV[1]` là giá trị để so sánh.
- `GET` trả về chuỗi đang lưu hoặc `nil` nếu khóa không tồn tại.
- Nếu trùng token, `DEL` xóa khóa và trả số khóa đã xóa.
- Nếu khác token hoặc khóa không tồn tại, script trả `0`.

Kết quả là số nguyên `1` khi xóa thành công khóa đơn, hoặc `0` khi không xóa. Sử dụng kiểu `Long` phía Java sẽ giúp tránh phải đoán giá trị trả về.

> Ví dụ này giải quyết riêng **bước giải phóng khóa có kiểm tra chủ sở hữu**. Nó không tự tạo ra một thuật toán distributed lock hoàn chỉnh: việc cấp khóa, TTL, timeout, gia hạn, fencing token và xử lý công việc quá hạn còn là những yêu cầu riêng của cơ chế lock.

### 3.2. Khai báo DefaultRedisScript là bean

```java
package example.redis.script;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class RedisScriptConfiguration {

    @Bean("deleteIfValueMatchesScript")
    public RedisScript<Long> deleteIfValueMatchesScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();

        script.setLocation(new ClassPathResource(
                "redis/scripts/delete-if-value-matches.lua"));
        script.setResultType(Long.class);

        return script;
    }
}
```

Hai lệnh quan trọng nhất:

```java
script.setLocation(new ClassPathResource(
        "redis/scripts/delete-if-value-matches.lua"));

script.setResultType(Long.class);
```

`setLocation(...)` cho `DefaultRedisScript` biết nguồn Lua lấy từ đâu, còn `setResultType(Long.class)` cho template biết cách diễn giải kết quả. Đường dẫn resource tính từ **classpath**, không phải đường dẫn tuyệt đối trên filesystem của máy chạy Java.

Nếu ứng dụng đóng gói thành JAR, tệp `.lua` vẫn có thể được đọc như tài nguyên classpath trong JAR. Đừng đọc bằng `new File("src/main/resources/...")` ở runtime rồi kỳ vọng đường dẫn nguồn phát triển sẽ luôn tồn tại trong deployment.

### 3.3. Tiêm bean vào service và thực thi

```java
package example.redis.script;

import java.util.Collections;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class LockReleaseService {

    private final StringRedisTemplate redisTemplate;
    private final RedisScript<Long> deleteIfValueMatchesScript;

    public LockReleaseService(
            StringRedisTemplate redisTemplate,
            @Qualifier("deleteIfValueMatchesScript")
            RedisScript<Long> deleteIfValueMatchesScript) {

        this.redisTemplate = redisTemplate;
        this.deleteIfValueMatchesScript = deleteIfValueMatchesScript;
    }

    public boolean releaseIfOwned(
            String key,
            String expectedToken) {

        Long deleted = redisTemplate.execute(
                deleteIfValueMatchesScript,
                Collections.singletonList(key),
                expectedToken
        );

        return Long.valueOf(1L).equals(deleted);
    }
}
```

Với `StringRedisTemplate`, ví dụ này truyền cả tên khóa và token dưới dạng chuỗi. Spring Data Redis serialize chúng theo serializer của template trước khi gửi đến Redis.

Kết quả:

```java
boolean released = lockReleaseService.releaseIfOwned(
        "process:lock:{job-42}",
        "request-unique-token-A"
);
```

Nếu giá trị Redis hiện tại đúng là `request-unique-token-A`, khóa được xóa và `released` là `true`. Nếu giá trị đã thay đổi, script trả `0`; service trả `false`, giữ nguyên khóa thuộc request khác.

Ứng dụng cũng cần xử lý lỗi kết nối Redis, timeout hoặc script execution error theo nghiệp vụ. `false` ở ví dụ nghĩa là **script chạy và không xóa khóa**, không thể dùng để biểu diễn mọi lỗi kết nối.

## 4. Cú pháp RedisTemplate.execute: script, keys và args

Lời gọi thường gặp có dạng:

```java
<T> T execute(
        RedisScript<T> script,
        List<K> keys,
        Object... args
);
```

Đọc từ trái qua phải:

1. `script`: đối tượng `RedisScript<T>` đã khai báo;
2. `keys`: danh sách tên Redis key mà script sẽ truy cập;
3. `args`: các tham số dữ liệu bổ sung mà script nhận qua `ARGV`;
4. kết quả `T`: kiểu Java được khai báo cho script.

Ví dụ:

```java
Long result = stringRedisTemplate.execute(
        deleteIfValueMatchesScript,
        List.of("process:lock:{job-42}"),
        "request-unique-token-A"
);
```

Tương ứng ở phía Lua:

```text
KEYS[1] = "process:lock:{job-42}"
ARGV[1] = "request-unique-token-A"
```

Nếu có nhiều key và nhiều tham số:

```java
template.execute(
        script,
        List.of("account:{42}:balance", "account:{42}:audit"),
        "100",
        "payment-987"
);
```

Phía Lua sẽ nhận:

```text
KEYS[1] = account:{42}:balance
KEYS[2] = account:{42}:audit

ARGV[1] = 100
ARGV[2] = payment-987
```

Cú pháp Lua dùng chỉ số bắt đầu từ **1**, trong khi `List` ở Java có chỉ số từ `0`. Spring Data Redis chuyển danh sách key sang mảng `KEYS` trong Redis script; không trừ hoặc cộng chỉ số bằng tay khi gọi `execute(...)`.

### Vì sao tên khóa phải đặt trong KEYS?

Trong Redis scripting, các **tên Redis key được script truy cập** cần được khai báo tường minh trong danh sách `KEYS`. `ARGV` dành cho giá trị, token, giới hạn, số lượng và các tham số không phải tên key.

Cách đúng:

```lua
local balance = tonumber(redis.call('GET', KEYS[1]) or '0')
local delta = tonumber(ARGV[1])
return redis.call('INCRBY', KEYS[1], delta)
```

Không nên tự tạo tên khóa động từ các tham số dữ liệu như:

```lua
-- Không nên: Redis không được cung cấp trước tên key sẽ truy cập.
local dynamicKey = "account:" .. ARGV[1]
return redis.call('GET', dynamicKey)
```

Lý do không chỉ là phong cách: trong Redis Cluster, key được khai báo giúp hệ thống xác định **hash slot và node** phù hợp với lệnh script. Tạo tên key từ giá trị runtime còn khiến phạm vi truy cập khóa khó kiểm soát và khó đảm bảo tính tương thích khi triển khai phân tán.

Nếu hai key thật sự cần được truy cập, hãy khai báo cả hai trong `keys` của `execute(...)`.

## 5. Một cách khai báo khác: setScriptText

Không phải lúc nào script cũng cần tệp `.lua` riêng. `DefaultRedisScript` còn hỗ trợ chỉ định trực tiếp nội dung bằng `setScriptText(String)`. Cách này hữu ích cho ví dụ rất ngắn hoặc script được đặt cố định cùng cấu hình Java.

Ví dụ chỉ tăng bộ đếm khi chưa vượt giới hạn:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class CounterScriptConfiguration {

    @Bean("increaseIfBelowLimitScript")
    public RedisScript<Long> increaseIfBelowLimitScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();

        script.setScriptText("""
                local current = tonumber(redis.call('GET', KEYS[1]) or '0')
                local limit = tonumber(ARGV[1])

                if current >= limit then
                    return 0
                end

                redis.call('INCR', KEYS[1])
                return 1
                """);

        script.setResultType(Long.class);
        return script;
    }
}
```

Gọi script với key và giới hạn:

```java
Long accepted = stringRedisTemplate.execute(
        increaseIfBelowLimitScript,
        List.of("rate:user:42"),
        "10"
);
```

Ở đây kết quả `1` nghĩa là Redis đã tăng bộ đếm, `0` nghĩa là đã chạm ngưỡng. `INCR` vốn nguyên tử, nhưng **kiểm tra điều kiện giới hạn rồi tăng** cần một đơn vị nguyên tử nếu nhiều client cùng tranh chấp.

**Nên chọn cách nào?**

| `setLocation(Resource)` | `setScriptText(String)` |
|---|---|
| Giữ Lua trong file `.lua` riêng, dễ đọc và sửa | Đặt đoạn Lua trực tiếp cùng khai báo Java |
| Thuận lợi khi script nhiều dòng, có comment và xử lý phức tạp | Gọn cho script ngắn |
| Tài nguyên đóng gói trong classpath | Script được đóng gói trong Java source/bytecode |
| Có thể dùng lại từ nhiều nơi trong module | Tránh phải tạo file cho vài lệnh |
| Cần đảm bảo resource nằm đúng đường dẫn | Cần chú ý Java text block và escaping |

Trong cả hai cách, **mã Lua nên là mã cố định do ứng dụng kiểm soát**. Không tạo script bằng cách nối trực tiếp đầu vào không tin cậy vào source Lua; hãy đưa dữ liệu runtime vào `KEYS` hoặc `ARGV` để tránh lỗi escaping và hành vi khó kiểm soát.

## 6. DefaultRedisScript xử lý SHA1 và việc tải script như thế nào?

Redis có hai cách thực thi liên quan:

- `EVAL`: gửi trực tiếp nội dung script để Redis thực thi;
- `EVALSHA`: gửi mã băm SHA1 của script đã được Redis biết đến.

Spring Data Redis thường thử thực thi script qua `EVALSHA` để tránh gửi toàn bộ source Lua ở mọi lần gọi. Nếu Redis trả lỗi **NOSCRIPT** vì script chưa tồn tại trong script cache của server, executor có thể fallback sang `EVAL`.

Luồng mô tả:

```text
Java service
    |
    v
RedisTemplate.execute(redisScript, keys, args)
    |
    v
Lấy source và SHA1 từ RedisScript
    |
    v
Redis EVALSHA <sha1> ...
    |
    +--- Script đã được server biết --> chạy Lua --> trả kết quả
    |
    +--- NOSCRIPT -------------------> Redis EVAL <source> ...
                                           |
                                           +--> chạy Lua, kết quả
```

Một số điểm quan trọng:

1. `DefaultRedisScript` quản lý thông tin source/SHA1 ở phía Java; **không đồng nghĩa script luôn được nạp sẵn trên mọi Redis node**.
2. Sau Redis restart, failover, script cache flush hoặc chuyển node trong cluster, `EVALSHA` có thể gặp `NOSCRIPT`; đường fallback là một phần cần thiết của scripting client.
3. Script cache là cơ chế của Redis server, có phạm vi theo instance/node; không phải một kho script phân tán do Spring Data Redis quản lý trên toàn cluster.
4. Thay đổi nội dung source khiến SHA1 thay đổi. Không giả định Redis còn biết SHA cũ thì đã thực thi nội dung mới.
5. Dùng bean singleton giúp tái sử dụng đối tượng và việc tính metadata phía Java. Redis vẫn có quyền quên script cache theo vòng đời của nó.

Trong Redis CLI, cách gọi tương đương về mặt ý tưởng là:

```redis
EVAL "return redis.call('GET', KEYS[1])" 1 demo:key
```

Tham số `1` ở đây là **số lượng key**, sau đó là tên key. Với script có một key và một argument:

```redis
EVAL "return redis.call('GET', KEYS[1]) == ARGV[1] and 1 or 0" 1 demo:key expected-value
```

Trong Spring, không cần tự ghép chuỗi `EVAL` gồm số key và lập danh sách tham số; `RedisTemplate.execute(...)` thực hiện việc đó dựa trên danh sách `keys` và `args`.

## 7. Lựa chọn result type: Lua trả gì, Java nhận gì?

Khi tạo `DefaultRedisScript<T>`, `setResultType(...)` định hướng cách executor chọn kiểu Redis reply và chuyển đổi giá trị về Java.

Một số trường hợp thường gặp:

| Lua trả về | Khai báo Java thường dùng | Lưu ý |
|---|---|---|
| Số nguyên `return 1`, `return 0`, `return redis.call('DEL', ...)` | `Long.class` | Phù hợp cho đếm, trạng thái dạng mã số |
| Một bulk string, ví dụ `return redis.call('GET', KEYS[1])` | `String.class` với StringRedisTemplate | Phụ thuộc result serializer, không phải lúc nào cũng là Java String nếu template dùng serializer khác |
| Một danh sách/table phù hợp với Redis script reply | `List.class` | Thành phần trong list cần chuyển đổi theo serializer và cấu trúc trả về |
| Giá trị kiểu boolean được biểu diễn qua Redis protocol | `Boolean.class` | Cần thống nhất quy ước Lua/Redis; đừng đoán từ Lua `true`/`false` như Java |
| Script không cần kết quả | `setResultType(null)` khi phù hợp | Theo hợp đồng API, không trông chờ một kết quả có giá trị |

Ví dụ ổn định nhất cho lệnh có/không là **Lua trả `1` hoặc `0`, Java dùng `Long.class`**:

```lua
if redis.call('EXISTS', KEYS[1]) == 1 then
    return 1
end

return 0
```

```java
DefaultRedisScript<Long> existsScript = new DefaultRedisScript<>();
existsScript.setScriptText("""
        return redis.call('EXISTS', KEYS[1])
        """);
existsScript.setResultType(Long.class);
```

Nếu dùng `Boolean.class`, cần hiểu cách Redis scripting reply và Spring Data chuyển sang boolean. Trong Lua của Redis, `false` thường biểu diễn nil reply ở những phiên bản/protocol tương ứng; `true` không đơn giản tương đương Java `true` trên mọi đường chuyển đổi. Dùng `Long` với `0/1` khi muốn loại bỏ sự mơ hồ trong mã nghiệp vụ.

### Tại sao khai báo result type sai có thể gây lỗi?

Giả sử script trả số nguyên nhưng lại khai báo:

```java
script.setResultType(String.class);
```

Kết quả sẽ được yêu cầu đọc theo đường khác với số nguyên mà Redis trả về. Tùy driver, serializer và cách convert, bạn có thể nhận giá trị không như mong đợi, `null` hoặc exception. Không dùng một lớp Java tùy ý làm result type mà không đối chiếu với kiểu reply thực tế.

Nếu script trả mảng nhiều phần tử, khai báo `List.class` và chủ động xử lý từng phần tử sau khi nhận; Generic Java như `List<String>` không tự động cung cấp đầy đủ thông tin chuyển đổi cho mọi phần tử trên wire.

## 8. Serializer: nguồn lỗi âm thầm phổ biến nhất

`RedisTemplate` thực hiện serialization **trước khi** Redis nhìn thấy `KEYS` và `ARGV`. Vì vậy cùng một đoạn Lua nhưng sử dụng template khác nhau có thể tạo kết quả khác nhau.

Ví dụ trong Redis đã tồn tại khóa chuỗi:

```redis
SET sample:token abc
```

Với `StringRedisTemplate`:

```java
StringRedisTemplate stringRedisTemplate;
```

Chuỗi Java `"sample:token"` được serialize thành tên khóa dạng string tương ứng và `"abc"` thành argument dạng string. Script:

```lua
return redis.call('GET', KEYS[1]) == ARGV[1] and 1 or 0
```

có thể trả `1` như mong đợi.

Nếu dùng một `RedisTemplate<Object, Object>` có JDK serializer cho key/argument, dữ liệu được chuyển thành byte của Java serialized object. Khi đó:

- Tên key truyền từ Java có thể **không trùng** tên `sample:token` đã được tạo bằng Redis CLI.
- Giá trị `ARGV[1]` có thể là chuỗi byte serialized, không tương đương literal `abc` trong Redis.
- Kết quả là script không tìm thấy khóa hoặc so sánh không khớp, dù source Lua hoàn toàn hợp lệ.

Một số overload `execute(...)` của Spring Data Redis cho phép truyền serializer chuyên biệt cho arguments và result. Khi cần tương tác với dữ liệu dùng serializer tùy chỉnh, hãy sử dụng đúng serializer và quy ước mapping của ứng dụng. Không sửa Lua bằng cách tự thêm byte prefix hoặc suffix khi nguyên nhân thực sự nằm ở serialization.

### Khai báo rõ serializer nếu không dùng StringRedisTemplate

Ví dụ một template chủ động dùng serializer chuỗi:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class PlainStringRedisConfiguration {

    @Bean("plainStringRedisTemplate")
    public RedisTemplate<String, String> plainStringRedisTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, String> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);

        StringRedisSerializer serializer = new StringRedisSerializer();
        template.setKeySerializer(serializer);
        template.setValueSerializer(serializer);
        template.setHashKeySerializer(serializer);
        template.setHashValueSerializer(serializer);

        template.afterPropertiesSet();
        return template;
    }
}
```

Với các ví dụ chỉ lưu string key/value, `StringRedisTemplate` thường đơn giản hơn. Đối với dữ liệu JSON, binary, object hash hoặc khóa do Redis Repository quản lý, cần đánh giá cách serializer của template và `RedisConverter` ánh xạ dữ liệu trước khi sửa các khóa đó bằng Lua.

## 9. Ví dụ nghiệp vụ thứ hai: giảm tồn kho nếu còn đủ số lượng

Một script thực tế hơn gồm nhiều điều kiện: số lượng phải dương, khóa tồn kho phải tồn tại và giá trị hiện tại phải đủ để trừ.

Tệp `src/main/resources/redis/scripts/decrease-stock-if-available.lua`:

```lua
-- KEYS[1] = item stock key
-- ARGV[1] = requested amount (> 0)
--
-- Return:
--   -1: stock key does not exist
--   -2: invalid requested amount or stock value
--    0: insufficient stock
--   >0: remaining stock (but remaining stock can be 0, see note below)

local raw = redis.call('GET', KEYS[1])
if not raw then
    return -1
end

local requested = tonumber(ARGV[1])
local stock = tonumber(raw)

if not requested or requested <= 0
        or requested % 1 ~= 0
        or not stock or stock < 0
        or stock % 1 ~= 0 then
    return -2
end

if stock < requested then
    return 0
end

return redis.call('DECRBY', KEYS[1], requested)
```

**Lưu ý về hợp đồng kết quả:** trong ví dụ trên, `0` có thể là **tồn kho còn lại bằng 0 sau khi giảm thành công** hoặc **không đủ tồn kho**. Vì vậy bản script ở trên **chưa phù hợp** nếu ứng dụng cần phân biệt chính xác hai trường hợp chỉ bằng một mã số.

Cách thiết kế trả về rõ nghĩa hơn là trả một mảng có status và số lượng còn lại:

```lua
-- KEYS[1] = stock key
-- ARGV[1] = requested integer amount

local raw = redis.call('GET', KEYS[1])
if not raw then
    return {-1, -1} -- missing key
end

local requested = tonumber(ARGV[1])
local stock = tonumber(raw)

if not requested or requested <= 0
        or requested % 1 ~= 0
        or not stock or stock < 0
        or stock % 1 ~= 0 then
    return {-2, stock or -1}
end

if stock < requested then
    return {0, stock} -- insufficient
end

local remaining = redis.call('DECRBY', KEYS[1], requested)
return {1, remaining} -- success (even if remaining is 0)
```

Với script thứ hai, Java có thể khai báo:

```java
DefaultRedisScript<List> stockScript = new DefaultRedisScript<>();
stockScript.setLocation(new ClassPathResource(
        "redis/scripts/decrease-stock-if-available.lua"));
stockScript.setResultType(List.class);
```

Phần giải mã `List` cần đối chiếu kiểu các phần tử mà Redis driver trả về; không ép kiểu về `List<Long>` một cách mù quáng. Ví dụ dịch vụ có thể kiểm tra mỗi phần tử là `Number` trước khi chuyển sang `longValue()`.

Đoạn script trả về hai số là ví dụ cách tạo **giao thức kết quả rõ ràng**. Trong hệ thống thực, còn cần giới hạn integer/overflow theo Redis, kiểm soát dữ liệu tồn kho ban đầu, việc hoàn/đặt trước hàng và retry nếu client không chắc Redis đã thực hiện script hay chưa.

## 10. Nguyên tử nhưng không phải rollback toàn bộ khi script lỗi

Redis thực thi Lua script theo cách các client khác không xen lệnh vào giữa quá trình script đang chạy. Tuy nhiên, Lua script **không có rollback mặc định** cho những Redis command đã thực hiện thành công trước một lỗi runtime.

Ví dụ:

```lua
redis.call('SET', KEYS[1], 'UPDATED')

-- Cố ý gọi lệnh sai đối với một giá trị không phải số.
redis.call('INCR', KEYS[1])

return 1
```

Lệnh `SET` có thể đã thay giá trị thành `UPDATED`. Bước `INCR` sau đó báo lỗi kiểu dữ liệu vì chuỗi này không phải số nguyên. Redis trả lỗi thực thi script, nhưng **không tự khôi phục giá trị cũ** của khóa.

Điều đó dẫn đến các nguyên tắc:

1. **Kiểm tra trước rồi mới thay đổi**: xác thực `ARGV`, dữ liệu đọc từ Redis và điều kiện nghiệp vụ trước các lệnh ghi nếu có thể.
2. **Không giả định exception đồng nghĩa chưa có side effect**: một script có thể đã ghi vài khóa trước khi lỗi.
3. **Tránh script dài và logic nhiều nhánh khó dự đoán**: càng nhiều lệnh ghi trước khi kiểm tra xong, càng khó phục hồi trạng thái khi có lỗi.
4. **Thiết kế gọi lại an toàn khi cần**: nếu client timeout hoặc mất kết nối, không biết chắc Redis đã thực thi hay chưa; một script tăng/giảm số lượng có thể tạo tác dụng lặp khi retry.
5. **Phân biệt kết quả nghiệp vụ với lỗi thực thi**: trả mã `0`, `1` hoặc đối tượng kết quả có nghĩa rõ ràng cho trường hợp không đạt điều kiện; chỉ dùng Redis/Lua error cho lỗi thực sự.

Redis script có thể chạy chặn xử lý lệnh khác trên server trong thời gian thực thi; một script duyệt quá nhiều dữ liệu, dùng vòng lặp lớn hoặc gọi lệnh nặng có thể gây tăng latency cho cả node. **Nguyên tử là lý do để script ngắn và tập trung**, không phải lý do để dồn mọi nghiệp vụ vào Lua.

## 11. Chạy Lua trong Redis Cluster: key phải thuộc phạm vi hợp lệ

Trong Redis Cluster, mỗi key được ánh xạ đến một **hash slot**. Một lệnh/script làm việc với nhiều key thường phải tuân thủ quy tắc các key liên quan nằm trên **cùng slot**. Spring Data Redis truyền `keys` đến Redis executor nhưng **không biến một script nhiều key khác slot thành giao dịch nguyên tử xuyên cluster**.

Ví dụ hai key:

```text
account:{customer-42}:balance
account:{customer-42}:version
```

Hai key có cùng hash tag `{customer-42}` nên Redis Cluster tính cùng slot. Chúng có thể được dùng trong một script nhiều key khi các điều kiện khác phù hợp.

Ngược lại:

```text
account:customer-42:balance
account:customer-43:balance
```

không có bảo đảm cùng slot; cố chạy một script nhiều key trên các slot khác nhau có thể gặp lỗi `CROSSSLOT` hoặc giới hạn về routing.

Đối với ví dụ `delete-if-value-matches.lua`, script chỉ truy cập **một key**, vì vậy không gặp vấn đề chọn slot cho nhiều key. Với những script phức tạp hơn:

- Liệt kê đầy đủ key cần truy cập trong danh sách `keys` ở phía Java.
- Thiết kế quy ước hash tag ngay khi đặt tên key nếu nghiệp vụ thật sự cần thao tác nguyên tử nhiều key.
- Không dùng một hash tag duy nhất cho **mọi** key trong hệ thống, vì sẽ dồn nhiều tải vào một slot.
- Khi dùng Redis Cluster, kiểm tra hành vi failover, retry và giới hạn script theo driver/phiên bản server.
- Không dùng Lua script trên một node như cách giả định “khóa của toàn cluster đều nằm ở đây”.

## 12. Khi nào nên khai báo một RedisScript dùng chung?

Một `RedisScript` thường nên biểu diễn **một thao tác nghiệp vụ nhỏ, được đặt tên rõ ràng**. Ví dụ:

| Nhiệm vụ | Tên bean/script gợi ý | Input | Output |
|---|---|---|---|
| Xóa khóa khi giá trị còn trùng token | `deleteIfValueMatchesScript` | 1 key, 1 token | `Long` 0/1 |
| Tăng bộ đếm chỉ khi chưa chạm ngưỡng | `increaseIfBelowLimitScript` | 1 key, 1 giới hạn | `Long` 0/1 |
| Giảm tồn kho nếu đủ số lượng | `decreaseStockScript` | 1 key, số lượng yêu cầu | Status + số lượng còn lại |
| Cập nhật giá trị khi version khớp | `compareAndSetVersionScript` | Các key cùng slot, version mới | Mã kết quả |
| Ghi nhiều cấu trúc phải đổi cùng nhau | `updateRelatedFieldsScript` | Danh sách key rõ ràng | Kết quả có nghĩa nghiệp vụ |

Khi lựa chọn giữa một Lua script và các API Redis thông thường:

- Nếu **một lệnh Redis** đã bảo đảm điều kiện và side effect mong muốn, dùng lệnh đó đơn giản hơn.
- Nếu nhiều bước phụ thuộc nhau và có **race condition** giữa client, Lua phù hợp khi mọi key cần thiết có thể được xử lý trong phạm vi server/slot hợp lệ.
- Nếu cần transaction với **SQL/JPA**, Lua không thay thế giao dịch database và không tạo commit phân tán nguyên tử.
- Nếu nhiệm vụ kéo dài, nhiều I/O hoặc cần gọi HTTP/database khác, Lua script trên Redis không phải công cụ phù hợp; Redis Lua không phải môi trường chạy một Java service thu nhỏ.

## 13. Gọi script trong pipeline hoặc Spring transaction có gì khác?

Khi gọi thông thường:

```java
Long deleted = stringRedisTemplate.execute(
        deleteIfValueMatchesScript,
        List.of("process:lock:{job-42}"),
        "request-unique-token-A"
);
```

kết quả có thể được xử lý ngay sau `execute(...)` nếu lệnh đã thực thi và server phản hồi bình thường.

Nhưng nếu đang chạy **Redis pipelining** hoặc **MULTI/EXEC transaction**, lệnh có thể đang được queue. Khi đó, một số API RedisTemplate trả về `null` hoặc chưa có kết quả cuối cùng tại thời điểm gọi; kết quả sẽ được lấy từ danh sách trả về khi pipeline/transaction hoàn thành.

Ví dụ không nên viết:

```java
// Không mặc định giá trị trả ngay trong pipeline/transaction.
Long result = redisTemplate.execute(script, keys, args);
if (result == 1L) {
    // ...
}
```

Trong đường gọi đồng bộ bình thường, cũng cần chú ý `result` có thể là `null` nếu có lỗi hoặc đường thực thi đặc biệt. Với kiểu `Long`, dùng `Long.valueOf(1L).equals(result)` để so sánh an toàn hơn việc unbox tùy ý.

Nếu tích hợp với `@Transactional`, hãy hiểu chính xác template đang tham gia giao dịch Spring như thế nào. **Lua nguyên tử trên Redis không có nghĩa cùng rollback hoặc commit nguyên tử với một giao dịch JPA/JDBC ở hệ thống khác.**

## 14. Những lỗi thường gặp khi khai báo và thực thi

### 14.1. Không tìm thấy tệp Lua

Ví dụ cấu hình:

```java
script.setLocation(new ClassPathResource(
        "redis/scripts/delete-if-value-matches.lua"));
```

nhưng resource thực tế nằm ngoài classpath hoặc bị đặt sai tên. Script không thể được đọc đúng khi chạy. Kiểm tra tệp nằm trong `src/main/resources` và được đóng gói theo đường dẫn dự kiến. Không sử dụng đường dẫn filesystem của IDE làm hợp đồng cho ứng dụng triển khai.

### 14.2. Quên setResultType hoặc chọn nhầm loại

Script trả số đếm Redis nhưng phía Java khai báo `String.class`, làm quá trình xử lý kết quả không khớp. Nên quyết định **Lua sẽ trả loại Redis reply nào** trước, sau đó khai báo `setResultType(...)` và cách đọc tương ứng.

### 14.3. Không nhất quán KEYS và ARGV

Code Java:

```java
template.execute(script, List.of("stock:42"), "5");
```

thì Lua cần đọc `KEYS[1]` cho key và `ARGV[1]` cho số lượng. Nếu Lua lại lấy số lượng ở `KEYS[2]` hoặc tự tạo key từ `ARGV[1]`, logic sẽ sai hoặc không tương thích với Redis Cluster.

### 14.4. Serializer làm script không thấy key

Khóa thực tế được tạo bằng `StringRedisTemplate`, nhưng script gọi thông qua `RedisTemplate<Object,Object>` với JDK serializer. Redis nhận những byte khác nhau, nên `EXISTS` hoặc `GET` không tìm thấy key mong muốn. Cần thống nhất serializer của key, argument và kết quả.

### 14.5. Script có SHA1 nhưng Redis trả NOSCRIPT

SHA1 được biết ở phía Java không có nghĩa server đã nạp script. Redis node có thể restart hoặc script cache bị làm sạch. Trong đường `RedisTemplate.execute(...)` thông thường, script executor xử lý chiến lược `EVALSHA` và fallback `EVAL`. Nếu tự gọi `EVALSHA` qua low-level API, bạn cần tự cân nhắc cách xử lý `NOSCRIPT`.

### 14.6. Script lỗi sau khi đã ghi dữ liệu

Không lầm exception với rollback. Sắp xếp các bước kiểm tra, xác định kiểu dữ liệu trước khi ghi, và thiết kế cách xử lý lỗi/khôi phục cho thao tác nhiều lệnh.

### 14.7. Lua chậm làm tăng latency toàn Redis node

Lua script chạy trên server có thể chặn các thao tác khác trong lúc thực thi. Tránh vòng lặp trên tập dữ liệu rất lớn, `KEYS *` hoặc thao tác tính toán kéo dài. Đo thời gian chạy trên môi trường thích hợp trước khi đưa script thường xuyên vào đường xử lý request.

### 14.8. Script chạy ở một keyslot nhưng dùng thêm key ở slot khác

Redis Cluster yêu cầu key liên quan đến script tuân thủ slot. Nếu dùng nhiều key, đặt hash tag hợp lý hoặc thay đổi thiết kế để tách thao tác, thay vì kỳ vọng một Lua script phối hợp các primary.

### 14.9. Retry gây thực thi lặp

Script thành công ở Redis nhưng client mất kết nối trước khi nhận phản hồi. Nếu retry ngay một script `INCR`/`DECR`, side effect có thể lặp. Với thao tác quan trọng, bổ sung idempotency key, version hoặc một giao thức có kết quả đọc lại được để phân biệt đã xử lý và chưa xử lý.

## 15. Bài thực hành: kiểm tra việc xóa khóa có điều kiện

Ví dụ sau mô tả thí nghiệm trong Redis **riêng cho phát triển**, đã cấu hình `StringRedisTemplate` và bean `deleteIfValueMatchesScript`.

### Bước 1: Lưu token ban đầu

```java
String key = "process:lock:{lab-01}";

stringRedisTemplate.opsForValue()
        .set(key, "owner-A");
```

### Bước 2: Thử xóa bằng token sai

```java
boolean deletedWithWrongToken =
        lockReleaseService.releaseIfOwned(key, "owner-B");
```

Kỳ vọng `false`. Đọc Redis:

```java
String actual = stringRedisTemplate.opsForValue().get(key);
// Vẫn là "owner-A".
```

### Bước 3: Xóa bằng token đúng

```java
boolean deletedWithCorrectToken =
        lockReleaseService.releaseIfOwned(key, "owner-A");
```

Kỳ vọng `true`, khóa không còn tồn tại:

```java
Boolean exists = stringRedisTemplate.hasKey(key);
// Thông thường là false.
```

### Bước 4: Gọi lại khi khóa đã biến mất

```java
boolean deletedAgain =
        lockReleaseService.releaseIfOwned(key, "owner-A");
```

Kỳ vọng `false`: script nhận `GET` bằng `nil` và trả `0`. Điều này giúp đường giải phóng khóa không vô tình báo thành công lần thứ hai.

Các bước này minh họa **hành vi dự kiến của một script có điều kiện**. Khi vận hành thực, kết quả còn phụ thuộc tình trạng server, serializer và việc có client khác ghi cùng khóa trong thời gian thí nghiệm.

## 16. Câu hỏi tự kiểm tra

**1. `RedisScript<Long>` và `DefaultRedisScript<Long>` khác gì nhau?**

`RedisScript<Long>` là giao diện biểu diễn script và kiểu kết quả; `DefaultRedisScript<Long>` là implementation thông dụng để chỉ định nội dung nguồn, resource và result type.

**2. Vì sao khuyến nghị lưu Lua dài trong `src/main/resources`?**

Tệp classpath giúp tách Lua khỏi Java service, dễ đọc, dễ kiểm soát thay đổi và được đóng gói cùng ứng dụng. `ClassPathResource` đọc được tài nguyên mà không phụ thuộc vào đường dẫn thư mục nguồn của máy lập trình.

**3. Lệnh `template.execute(script, List.of(key), token)` đưa `key` và `token` vào đâu?**

`key` trở thành `KEYS[1]`, còn `token` trở thành `ARGV[1]` ở phía Lua.

**4. Tại sao nên truyền tên key trong `KEYS` thay vì ghép từ `ARGV`?**

Redis cần biết những key script truy cập để áp dụng quy tắc định tuyến/phạm vi trong Redis Cluster; `ARGV` được dùng cho dữ liệu không phải tên key.

**5. Chỉ cần `EVALSHA` và SHA1 là Redis luôn chạy script được không?**

Không. Script cache thuộc Redis server/node; nếu server chưa có source, `EVALSHA` có thể trả `NOSCRIPT`. Spring Data Redis thường có cơ chế fallback `EVAL` khi thực thi qua executor.

**6. Một Lua script trả `0` hoặc `1` nên khai báo result type nào để dễ hiểu?**

`Long.class`, với quy ước Java đọc `0L`/`1L` và tự chuyển thành trạng thái nghiệp vụ.

**7. Vì sao script có thể báo lỗi nhưng Redis vẫn bị thay đổi?**

Redis không hoàn tác tự động những lệnh đã thực thi thành công bên trong Lua trước khi phát sinh lỗi runtime.

**8. Lua script nhiều key có chạy nguyên tử trên mọi Redis Cluster node không?**

Không. Redis Cluster giới hạn phạm vi key/slot; nhiều key khác slot không tự trở thành một giao dịch nguyên tử xuyên cluster.

**9. Dùng một Lua script atomic có giải quyết được commit giữa PostgreSQL và Redis không?**

Không. Script chỉ tạo atomicity trong Redis theo phạm vi hợp lệ; transaction của PostgreSQL là tài nguyên khác.

**10. Vì sao script có thể chạy đúng khi dùng `StringRedisTemplate` nhưng sai với một `RedisTemplate` khác?**

Key và argument có thể dùng serializer khác, khiến byte mà Redis nhận không còn giống tên key và giá trị mà script dự kiến.

## 17. Ghi nhớ khi triển khai

- Dùng `RedisScript<T>` trong hợp đồng service, `DefaultRedisScript<T>` để khai báo resource hoặc source và kiểu trả về.
- Đặt script dài ở tệp `.lua` dưới classpath, dùng `ClassPathResource` và cấu hình `setResultType(...)` rõ ràng.
- Thực thi qua `RedisTemplate.execute(script, keys, args...)`; dùng `KEYS` cho tên Redis key và `ARGV` cho tham số dữ liệu.
- Ưu tiên `StringRedisTemplate` khi toàn bộ key/value/argument đều là chuỗi; thống nhất serializer nếu có dữ liệu nhị phân hoặc object.
- Hiểu chiến lược `EVALSHA` và fallback `EVAL`; không nhầm SHA1 phía Java với script cache đã tồn tại trên Redis node.
- Lua giúp tránh race condition giữa các lệnh có điều kiện, nhưng không tự rollback mọi thay đổi khi script lỗi và không thay thế giao dịch liên tài nguyên.
- Script nên ngắn, kiểm tra đầu vào trước khi ghi, xử lý kết quả có nghĩa rõ ràng và cân nhắc tính idempotent khi retry.
- Với Redis Cluster, mọi key dùng trong cùng script phải đáp ứng giới hạn slot; hash tag có thể hữu ích khi thật sự cần nhiều key cùng slot.

Cách hiểu quan trọng nhất là: **`DefaultRedisScript` mô tả đoạn Lua sẽ chạy và kiểu kết quả mong đợi, còn `RedisTemplate.execute` quyết định cách chuyển keys/arguments thành lệnh gửi Redis**. Hai phía cần thống nhất cả cấu trúc `KEYS`/`ARGV`, serializer lẫn hợp đồng kết quả thì script mới thực hiện đúng nghiệp vụ.

## Tài liệu tham khảo

- [Spring Data Redis — Redis Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html): `RedisScript`, `DefaultRedisScript`, `RedisTemplate.execute(...)`, `EVALSHA` và fallback `EVAL`.
- [Spring Data Redis — DefaultRedisScript API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/script/DefaultRedisScript.html): cách khai báo source, resource và result type.
- [Spring Data Redis — RedisScript API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/script/RedisScript.html): hợp đồng typed script.
- [Redis — Programmability / Lua Scripting](https://redis.io/docs/latest/develop/programmability/eval-intro/): cách Redis chạy Lua script, truyền `KEYS`/`ARGV` và giới hạn.
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/): cú pháp, số key và phạm vi script.
- [Redis — EVALSHA](https://redis.io/docs/latest/commands/evalsha/): thực thi script bằng SHA1.
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/): phân biệt nhóm lệnh Redis và rollback.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): quy tắc hash slot, hash tag và thao tác nhiều key.

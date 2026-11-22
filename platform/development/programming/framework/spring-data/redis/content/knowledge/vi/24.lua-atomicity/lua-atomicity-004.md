# Tuần tự hóa tham số và giải tuần tự hóa kết quả script trong Spring Data Redis

## 1. Vấn đề cốt lõi: Java object đi vào Lua dưới dạng gì?

Redis Lua script thường được gọi từ Java thông qua `RedisTemplate.execute(...)`, `StringRedisTemplate.execute(...)` hoặc `RedisScript`. Điểm dễ nhầm là **Lua không nhận trực tiếp object Java**. Spring Data Redis phải chuyển các key và tham số sang **mảng byte** trước khi gửi lệnh `EVAL`/`EVALSHA`. Khi Redis trả kết quả, Spring Data Redis lại phải diễn giải kiểu phản hồi Redis và có thể giải tuần tự hóa phần dữ liệu về kiểu Java.

Luồng cơ bản:

```text
Java:
  RedisScript<T>
  List<K> keys
  Object... args
       |
       | Spring Data Redis serialization
       v
Redis request:
  EVALSHA <sha> <numkeys> <key-bytes>... <arg-bytes>...
       |
       | Redis chuyển các byte tới script
       v
Lua:
  KEYS[1], KEYS[2], ...
  ARGV[1], ARGV[2], ...
       |
       | Script thực thi redis.call(...)
       v
Redis reply:
  integer / bulk string / array / nil / error / ...
       |
       | RedisScript result type + result serializer
       v
Java:
  Long / Boolean / String / List / null / ...
```

Mục tiêu bài học là hiểu chính xác **bên nào chịu trách nhiệm chuyển đổi dữ liệu**, chọn serializer thích hợp và thiết kế hợp đồng dữ liệu ổn định giữa Java và Lua.

Sau bài học, bạn có thể:

- Phân biệt `KEYS` với `ARGV`, cả về mục đích lẫn serializer được dùng.
- Hiểu vì sao `StringRedisTemplate` thường là lựa chọn đơn giản để truyền tham số số học và chuỗi vào Lua.
- Khai báo `RedisScript<T>` với kiểu trả về phù hợp.
- Đọc được kết quả `Long`, `Boolean`, `String`, `List` hoặc `null` và biết khi nào cần JSON.
- Sử dụng overload của `RedisTemplate.execute` để chỉ định serializer của tham số và kết quả.
- Nhận diện lỗi do `JdkSerializationRedisSerializer`, serializer JSON, kiểu số và dữ liệu nhị phân.
- Thiết kế script an toàn trước lỗi đầu vào, kết quả không mong đợi và các vấn đề của Redis Cluster.

## 2. Hiểu KEYS, ARGV và kết quả ở cấp Redis

Một script Lua được Redis gọi bằng cấu trúc tương đương:

```redis
EVAL "<lua script>" <number-of-keys> <key1> ... <keyN> <arg1> ... <argM>
```

Hoặc khi script đã được nhận diện bằng SHA:

```redis
EVALSHA <sha1> <number-of-keys> <key1> ... <keyN> <arg1> ... <argM>
```

Trong script:

- `KEYS[1]`, `KEYS[2]`, ... chứa các tên Redis key được khai báo rõ trong lời gọi.
- `ARGV[1]`, `ARGV[2]`, ... chứa các tham số nghiệp vụ: số lượng, trạng thái, ID request, payload, v.v.
- Lua đánh chỉ số mảng từ **1**, khác với Java đánh từ 0.
- Mỗi `KEYS[i]` và `ARGV[i]` tới Lua về bản chất là chuỗi byte. Redis không biết đó vốn là `BigDecimal`, enum hay DTO Java.

Ví dụ từ Redis CLI:

```redis
EVAL "return {KEYS[1], ARGV[1], ARGV[2]}" 1 demo:counter 5 hello
```

Ý nghĩa:

```text
KEYS[1] = "demo:counter"
ARGV[1] = "5"
ARGV[2] = "hello"
```

Lua không tự động nhận biết `ARGV[1]` là số nguyên. Nếu cần tính toán, script phải chuyển đổi:

```lua
local amount = tonumber(ARGV[1])
```

Nếu chuỗi không biểu diễn được số, `tonumber` trả `nil` trong trường hợp chuyển đổi không hợp lệ. Khi script sử dụng giá trị đó để gọi một phép tính hoặc Redis command, có thể phát sinh lỗi.

### 2.1. Vì sao phải tách KEYS và ARGV?

Sự tách biệt này phục vụ:

1. **Khả năng định tuyến:** trên Redis Cluster, client/server dùng các Redis key đã khai báo để áp dụng quy tắc hash slot.
2. **Hợp đồng script:** script biết tham số nào là tên key để truy cập dữ liệu, tham số nào chỉ là giá trị nghiệp vụ.
3. **Khả năng kiểm soát:** cùng một script có thể chạy trên các key và giá trị khác nhau mà không thay đổi nội dung mã Lua.
4. **Bảo trì:** thay vì ghép tên key trực tiếp vào source Lua, ứng dụng truyền key qua danh sách dành riêng.

Không đưa tên Redis key vào `ARGV` rồi tự dựng key tùy ý trong Lua như một cách né ràng buộc Cluster. Những key script truy cập cần được khai báo đúng và tuân theo yêu cầu cùng hash slot.

## 3. RedisTemplate dùng serializer nào khi thực thi Lua?

Với overload thông dụng:

```java
<T> T execute(RedisScript<T> script, List<K> keys, Object... args);
```

`RedisTemplate` chịu trách nhiệm chuyển đổi đầu vào và kết quả.

Theo cơ chế mặc định của `DefaultScriptExecutor` trong Spring Data Redis:

- Các **key** dùng **key serializer** của template.
- Các **đối số `ARGV`** dùng **value serializer** của template.
- Phần **kết quả dạng dữ liệu byte** dùng **value serializer** của template để giải tuần tự hóa, khi kiểu trả về của script yêu cầu điều đó.
- Một số kiểu trả về như `Long` và `Boolean` được ánh xạ từ kiểu reply Redis bằng cơ chế đặc biệt, thay vì lấy serializer string/JSON để giải mã số.
- Kiểu Java dự kiến được mô tả bằng `RedisScript<T>.getResultType()`.

Vì thế, **serializer cấu hình trên template ảnh hưởng trực tiếp đến dữ liệu Lua nhìn thấy**, chứ không chỉ ảnh hưởng tới lệnh `GET`/`SET` thông thường.

Bảng định hướng:

| Thành phần | Dữ liệu Java | Cách chuyển đổi mặc định |
|---|---|---|
| Danh sách `keys` | `List<String>` hoặc `List<K>` | `template.getKeySerializer()` |
| Các phần tử `args` | `Object...` | `template.getValueSerializer()` |
| Kết quả bulk string | Byte từ Redis | `template.getValueSerializer()` nếu dùng overload mặc định |
| Kết quả integer | Redis integer reply | Thường chuyển trực tiếp thành `Long` khi result type là `Long` |
| Kết quả boolean | Dạng reply phù hợp | Được chuyển theo kiểu `Boolean` mà `RedisScript` khai báo |
| Kết quả array | Redis array reply | Các phần tử được giải tuần tự hóa theo quy tắc kết quả phù hợp |
| Không có kết quả | Redis nil hoặc script không trả giá trị có ý nghĩa | Có thể được biểu diễn bằng `null` tùy loại reply và result type |

**Không giả định template nào cũng dùng UTF-8 String.** `StringRedisTemplate` được cấu hình thiên về chuỗi; một `RedisTemplate<String, Object>` có thể dùng JDK serialization hoặc JSON tùy cách tạo bean và cấu hình của ứng dụng.

## 4. Vì sao StringRedisTemplate thường dễ dùng với Lua?

`StringRedisTemplate` sử dụng serializer chuỗi cho key và value; dữ liệu chuỗi thường được mã hóa UTF-8. Điều này phù hợp với script sử dụng `tonumber`, so sánh String hoặc `redis.call("GET", ...)`.

Ví dụ khởi tạo một key:

```java
import org.springframework.data.redis.core.StringRedisTemplate;

String key = "stock:{sku-42}:available";
stringRedisTemplate.opsForValue().set(key, "20");
```

Lời gọi script:

```java
Long result = stringRedisTemplate.execute(
    script,
    List.of(key),
    "3"
);
```

Dữ liệu Lua nhận được về mặt logic:

```text
KEYS[1] = "stock:{sku-42}:available"
ARGV[1] = "3"
```

Trong Lua:

```lua
local quantity = tonumber(ARGV[1])
```

sẽ nhận giá trị số 3 nếu tham số thật sự là chuỗi `"3"`.

### 4.1. Đừng nhầm `StringRedisTemplate` với truyền object tự động

Nếu đối số là DTO hoặc `BigDecimal`, bạn cần quyết định **định dạng dữ liệu trên wire**. `StringRedisTemplate` không tự hiểu cách biểu diễn mọi DTO Java thành JSON mong muốn. Hãy chuyển đổi rõ:

```java
String quantityText = Integer.toString(quantity);
String idempotencyToken = UUID.randomUUID().toString();

Long result = stringRedisTemplate.execute(
    script,
    List.of(redisKey),
    quantityText,
    idempotencyToken
);
```

Nếu cần truyền object phức tạp, serialize thành JSON có schema rõ ràng bằng Jackson hoặc một codec được hai bên cùng hiểu.

## 5. Ví dụ hoàn chỉnh: đặt giữ hàng bằng script Lua

Ta có key chứa lượng hàng còn lại:

```text
stock:{sku-42}:available = "20"
```

Mục tiêu:

- Nếu yêu cầu giữ hàng không hợp lệ, không thay đổi dữ liệu.
- Nếu hàng không đủ, trả mã `0`.
- Nếu giữ hàng thành công, trừ tồn kho và trả mã `1`.
- Không phát sinh hai bước Java `GET` rồi `DECRBY` có thể xen kẽ bởi request khác.

### 5.1. File Lua

Tạo file `src/main/resources/scripts/reserve-stock.lua`:

```lua
-- KEYS[1] : key tồn kho (Redis String chứa số nguyên)
-- ARGV[1] : số lượng cần giữ, dạng chuỗi thập phân

local requested = tonumber(ARGV[1])

if requested == nil
   or requested <= 0
   or requested ~= math.floor(requested) then
    return -2
end

local rawAvailable = redis.call('GET', KEYS[1])

if rawAvailable == false then
    return -1
end

local available = tonumber(rawAvailable)

if available == nil then
    return -3
end

if available < requested then
    return 0
end

redis.call('DECRBY', KEYS[1], requested)
return 1
```

Các mã kết quả được thỏa thuận:

| Kết quả Lua | Ý nghĩa |
|---:|---|
| `1` | Giữ hàng thành công |
| `0` | Không đủ hàng |
| `-1` | Key không tồn tại |
| `-2` | Tham số số lượng không hợp lệ |
| `-3` | Dữ liệu tồn kho không có định dạng số hợp lệ |

Cần quy định định dạng key tồn kho là **chuỗi số nguyên**. Mã minh họa dùng `tonumber` trong Lua, phù hợp ví dụ số lượng thông thường; với giá trị nguyên 64-bit rất lớn, cần cân nhắc giới hạn chính xác của số Lua và việc Redis command chấp nhận số nguyên.

### 5.2. Định nghĩa RedisScript<Long>

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class RedisScriptConfiguration {

    @Bean
    RedisScript<Long> reserveStockScript() {
        return RedisScript.of(
            new ClassPathResource("scripts/reserve-stock.lua"),
            Long.class
        );
    }
}
```

Ở đây `Long.class` là **loại kết quả Java**, không phải serializer của `ARGV`. Spring Data Redis biết rằng script dự kiến trả một Redis integer reply và chuyển nó thành `Long`.

Đưa script vào resource riêng giúp việc thay đổi, đọc và tái sử dụng thuận tiện hơn so với việc ghép một chuỗi Java rất dài.

### 5.3. Gọi script từ Service

```java
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class StockReservationService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> reserveStockScript;

    public StockReservationService(
            StringRedisTemplate redis,
            RedisScript<Long> reserveStockScript) {
        this.redis = redis;
        this.reserveStockScript = reserveStockScript;
    }

    public long reserve(String productId, long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        // productId phải được kiểm soát để bảo toàn định dạng hash tag.
        String key = "stock:{" + productId + "}:available";

        Long code = redis.execute(
            reserveStockScript,
            List.of(key),
            Long.toString(quantity)
        );

        if (code == null) {
            throw new IllegalStateException(
                "Lua returned no result for reservation"
            );
        }

        return code;
    }
}
```

Trước khi thử:

```java
stringRedisTemplate.opsForValue()
    .set("stock:{sku-42}:available", "20");
```

Ví dụ:

```java
long result = stockReservationService.reserve("sku-42", 3);
// result = 1
```

Sau đó:

```redis
GET stock:{sku-42}:available
```

Kết quả mong đợi là `17` nếu không có thao tác khác tác động.

Điểm kết nối giữa các lớp:

```text
Java long quantity=3
  |
  | Long.toString(quantity)
  v
String "3"
  |
  | StringRedisSerializer
  v
ARGV[1] = bytes UTF-8 của "3"
  |
  | Lua tonumber(ARGV[1])
  v
requested = 3
  |
  | Lua return 1
  v
Redis integer reply 1
  |
  | RedisScript<Long>
  v
Java Long 1
```

### 5.4. Những giả định phải rõ

Ví dụ giả định key tồn kho là Redis String chứa số nguyên không âm, dữ liệu không bị ghi bằng serializer nhị phân không tương thích và mỗi lệnh có thể được thực thi trên node phục vụ key. Nếu sản phẩm có nhiều key liên quan trong Redis Cluster, tất cả key mà script truy cập cần thuộc cùng hash slot.

Nếu chỉ cần một thao tác `DECRBY` đơn giản, bản thân Redis command đã nguyên tử. Script có ích ở đây vì gộp **kiểm tra điều kiện tồn kho** và **trừ số lượng** thành một bước.

## 6. Ánh xạ kiểu trả về của Lua sang Java

Redis script không trả trực tiếp một object Java. Nó trả một **Redis protocol reply**. Spring Data Redis dùng kết quả khai báo trên `RedisScript<T>` để quyết định cách diễn giải.

Một số kiểu phổ biến trong bối cảnh RESP2:

| Lua trả về | Redis reply thường gặp | Loại Java/RedisScript nên dùng |
|---|---|---|
| `return 42` | Integer | `Long.class` |
| `return redis.call('INCRBY', key, 1)` | Integer | `Long.class` |
| `return redis.call('EXISTS', key)` | Integer `0` hoặc `1` | `Long.class`, hoặc `Boolean.class` khi muốn diễn giải như cờ |
| `return 'READY'` | Bulk string | `String.class` với serializer chuỗi |
| `return redis.call('GET', key)` | Bulk string hoặc nil | `String.class`, kiểm tra `null` |
| `return {ARGV[1], ARGV[2]}` | Array | `List.class` |
| `return false` trong quy tắc Lua/RESP2 | Nil/null reply | Xử lý `null` phù hợp |
| `return redis.status_reply('OK')` | Status reply | Diễn giải theo reply và API của client |
| Script trả lỗi bằng `redis.error_reply(...)` | Error reply | Exception phía client, không phải DTO kết quả thông thường |

**Chú ý về RESP3:** Redis có thêm các kiểu phản hồi và quy tắc chuyển đổi giữa Lua và RESP3, nhưng API Spring Data Redis cụ thể vẫn phụ thuộc phiên bản/driver. Tài liệu này tập trung vào các kiểu phổ biến để viết script tương thích tốt.

### 6.1. RedisScript<Long>

```java
DefaultRedisScript<Long> script = new DefaultRedisScript<>();
script.setScriptText("return 15");
script.setResultType(Long.class);

Long value = stringRedisTemplate.execute(script, List.of());
```

Kết quả mong đợi là `15L`.

Đối với integer reply, phần chuyển đổi sử dụng kiểu Redis tương ứng và thường **không đi qua JSON/String result serializer**.

### 6.2. RedisScript<Boolean>

```java
DefaultRedisScript<Boolean> script = new DefaultRedisScript<>();
script.setScriptText("return redis.call('EXISTS', KEYS[1])");
script.setResultType(Boolean.class);

Boolean exists = stringRedisTemplate.execute(
    script,
    List.of("demo:flag")
);
```

`EXISTS` trả integer `0` hoặc `1`. Chuyển thành `Boolean` hữu ích cho logic `true`/`false`, nhưng khi muốn giữ các mã trạng thái `-1`, `0`, `1`, nên dùng `Long` để tránh mất thông tin.

Đừng dùng một tập mã số khác nhau rồi gán tất cả vào `Boolean`: một kiểu boolean chỉ diễn đạt hai trạng thái.

### 6.3. RedisScript<String>

```java
DefaultRedisScript<String> script = new DefaultRedisScript<>();
script.setScriptText("return ARGV[1]");
script.setResultType(String.class);

String value = stringRedisTemplate.execute(
    script,
    List.of(),
    "hello"
);
```

`ARGV[1]` chứa byte của `"hello"`; script trả bulk string và `StringRedisTemplate` giải mã thành Java `String`.

Nếu dùng `RedisTemplate` có value serializer JDK hoặc JSON nhưng script trả chuỗi thô `"hello"`, kết quả có thể bị giải mã sai hoặc báo lỗi. **Định dạng reply và result serializer phải tương thích.**

### 6.4. Lua nil hoặc không có dữ liệu

```java
DefaultRedisScript<String> script = new DefaultRedisScript<>();
script.setScriptText("return redis.call('GET', KEYS[1])");
script.setResultType(String.class);

String value = stringRedisTemplate.execute(
    script,
    List.of("missing:key")
);
```

Nếu key không tồn tại, giá trị có thể là `null`.

Không nên hiểu `null` luôn có nghĩa “business object không tồn tại”. Script có thể `return nil`, trả Lua `false` theo cơ chế RESP2, hoặc được gọi với `resultType` không phù hợp. Hãy quy định rõ **hợp đồng trạng thái trả về**; với logic có nhiều khả năng, dùng mã số hoặc JSON trạng thái rõ ràng.

### 6.5. Script chỉ cần side effect

Khi script chỉ ghi dữ liệu mà Java không cần phản hồi nghiệp vụ, có thể khai báo kiểu kết quả `null` theo cách API `RedisScript` hỗ trợ:

```java
DefaultRedisScript<Void> script = new DefaultRedisScript<>();
script.setScriptText(
    "redis.call('SET', KEYS[1], ARGV[1]); return nil"
);
script.setResultType(null);
```

Cấu hình này diễn đạt rằng ứng dụng không mong kết quả Java cụ thể. Cần xử lý exception khi Redis có lỗi; “không có result” **không đồng nghĩa không có lỗi**.

## 7. Kiểu số: bẫy phổ biến nhất

Lua có thể nhận `"10"` rồi chuyển bằng `tonumber`, nhưng cần phân biệt chuỗi, số Java và kiểu reply Redis.

### 7.1. Truyền số từ Java

Dùng chuỗi thập phân rõ ràng:

```java
String amount = Long.toString(quantity);

Long result = stringRedisTemplate.execute(
    script,
    List.of("counter:{tenant-7}:value"),
    amount
);
```

Lua:

```lua
local n = tonumber(ARGV[1])
if not n then
    return redis.error_reply('quantity must be numeric')
end
```

Nếu ứng dụng sử dụng serializer JSON cho đối số, số `10` có thể được gửi thành chuỗi JSON `"10"` hoặc bytes JSON biểu diễn `10`, tùy loại Java và serializer; byte thực tế cần được kiểm soát. Vì vậy, khi script cần một số, truyền chuỗi số với `StringRedisSerializer` thường dễ kiểm chứng hơn.

### 7.2. Số Lua và số nguyên Redis không hoàn toàn giống nhau

Nhiều môi trường Redis Lua truyền thống dùng kiểu number dựa trên IEEE-754 double. Các integer lớn hơn giới hạn chính xác của double có nguy cơ mất chữ số khi đi qua `tonumber`. Đồng thời, Redis counter như `INCRBY`/`DECRBY` có các giới hạn số nguyên riêng.

Với dữ liệu cần độ chính xác tuyệt đối như tiền tệ:

- Không dùng Lua floating-point một cách tùy ý để cộng trừ tiền.
- Ưu tiên đơn vị nguyên nhỏ nhất (`minor units`, ví dụ số đồng/xu tương ứng với nghiệp vụ) hoặc kiểu dữ liệu có chiến lược tính toán chính xác.
- Cẩn trọng với số nguyên lớn khi chuyển qua `tonumber` và `math.floor`.
- Kiểm tra phạm vi giá trị được phép ở Java và trong script.
- Nếu một command Redis như `INCRBY` đã phù hợp, ưu tiên dùng đúng ngữ nghĩa số nguyên Redis.

### 7.3. Đừng trả số thập phân bằng `return 3.75` rồi mong Java Double

Trong cơ chế Lua/Redis phổ biến, giá trị Lua number khi chuyển sang Redis integer reply có thể bị cắt phần thập phân. `RedisScript<Double>` cũng không phải lựa chọn chuẩn cho một integer reply.

Nếu thực sự cần trả số thực, một phương án rõ ràng là **trả chuỗi có định dạng được định nghĩa trước**, sau đó parse ở Java:

```lua
return tostring(3.75)
```

Java:

```java
DefaultRedisScript<String> script = new DefaultRedisScript<>();
script.setScriptText("return tostring(3.75)");
script.setResultType(String.class);

String raw = stringRedisTemplate.execute(script, List.of());
BigDecimal value = new BigDecimal(raw);
```

Cách này xử lý được định dạng biểu diễn, nhưng **không làm phép tính floating-point trong Lua trở nên chính xác tuyệt đối**. Nếu cần chính xác về tiền, thiết kế phép tính và dữ liệu ngay từ đầu bằng đại lượng nguyên hoặc cơ chế số học phù hợp.

## 8. Trả về nhiều giá trị với Redis array

Lua có thể trả array để Java nhận danh sách:

```lua
return {ARGV[1], ARGV[2], 'OK'}
```

Trong Java:

```java
import java.util.List;
import org.springframework.data.redis.core.script.DefaultRedisScript;

DefaultRedisScript<List> script = new DefaultRedisScript<>();
script.setScriptText("return {ARGV[1], ARGV[2], 'OK'}");
script.setResultType(List.class);

List<?> reply = stringRedisTemplate.execute(
    script,
    List.of(),
    "u-7",
    "42"
);
```

Dữ liệu logic:

```text
reply[0] = "u-7"
reply[1] = "42"
reply[2] = "OK"
```

Đối với các phần tử bulk string, serializer kết quả của template phải đọc đúng byte. Nếu array chứa cả integer, null và nested array, kiểu Java của từng phần tử có thể khác nhau; không nên ép mù mọi phần tử thành `String`.

Ví dụ script trả:

```lua
return {1, 'READY', false}
```

Java có thể nhận một danh sách chứa giá trị số, chuỗi và phần tử nil/null theo quy tắc chuyển đổi reply. Khi thiết kế hợp đồng API, **đừng để phía Java phụ thuộc vào chi tiết ép kiểu ngầm** của một cấu trúc hỗn hợp không được mô tả rõ.

### 8.1. Redis array khác JSON array

```lua
return {'a', 'b', 'c'}
```

trả **Redis array reply**.

```lua
return cjson.encode({'a', 'b', 'c'})
```

trả **bulk string chứa văn bản JSON**.

Hai kết quả khác nhau ở cấp giao thức. Để đọc JSON string, nên khai báo `String.class` rồi dùng Jackson. Nếu muốn đọc Redis array, dùng `List.class` và serializer/result type phù hợp.

## 9. Trả một object phức tạp: hợp đồng JSON rõ ràng

Nếu Java cần trạng thái có nhiều trường:

```text
success
remaining
reason
requestId
```

thì một JSON document với schema ổn định thường dễ mở rộng hơn mảng vị trí hoặc nhiều mã số.

Lua:

```lua
local requested = tonumber(ARGV[1])
if requested == nil then
    return cjson.encode({
        success = false,
        reason = 'INVALID_QUANTITY'
    })
end

local remaining = tonumber(
    redis.call('GET', KEYS[1]) or '0'
)

if remaining < requested then
    return cjson.encode({
        success = false,
        reason = 'INSUFFICIENT_STOCK',
        remaining = remaining
    })
end

local newBalance = redis.call(
    'DECRBY', KEYS[1], requested
)

return cjson.encode({
    success = true,
    reason = 'OK',
    remaining = newBalance
})
```

Java DTO:

```java
public record StockScriptResult(
    boolean success,
    String reason,
    Long remaining
) {}
```

Khai báo script trả `String`:

```java
DefaultRedisScript<String> jsonScript = new DefaultRedisScript<>();
jsonScript.setScriptText(luaSource);
jsonScript.setResultType(String.class);
```

Gọi và parse:

```java
String json = stringRedisTemplate.execute(
    jsonScript,
    List.of("stock:{sku-42}:available"),
    "3"
);

if (json == null) {
    throw new IllegalStateException("Missing JSON response");
}

StockScriptResult result =
    objectMapper.readValue(json, StockScriptResult.class);
```

Giả định `luaSource` là nội dung script ở trên, `objectMapper` là Jackson `ObjectMapper` được ứng dụng cấu hình, và project dùng Java hỗ trợ `record`. Nếu dùng Java cũ hơn, có thể dùng class DTO thường.

**Lợi ích:** phía Lua quyết định cấu trúc JSON; phía Java kiểm soát rõ quá trình giải tuần tự hóa. Nếu thêm trường mới, có thể áp dụng nguyên tắc versioning/schema migration thay vì phụ thuộc vào vị trí phần tử của Redis array.

### 9.1. Không dùng JSON cho mọi trường hợp

Nếu script chỉ cần trả `0`/`1`, kiểu `Long` đơn giản hơn. JSON có chi phí encode, decode, payload và xử lý lỗi. Chọn JSON khi kết quả nhiều trường hoặc cần schema rõ ràng.

### 9.2. Trả JSON và đọc bằng serializer JSON tự động

Một template sử dụng serializer JSON có thể trực tiếp deserialize bulk string JSON về object, nhưng điều đó phụ thuộc **result serializer**, type metadata và cấu hình mapper. Dễ kiểm soát hơn khi:

1. Lua trả JSON text.
2. Spring Data Redis giải mã text bằng `StringRedisSerializer`.
3. Java dùng `ObjectMapper` để parse thành DTO đã biết kiểu.

Cách này phân tách rõ **Redis wire format** và **schema dữ liệu nghiệp vụ**.

## 10. Tùy chỉnh serializer cho args và result

Ngoài overload thông thường, `RedisTemplate` có overload cho phép chỉ định serializer của **tham số** và **kết quả** khi thực thi script.

Dạng API thường dùng:

```java
<T> T execute(
    RedisScript<T> script,
    RedisSerializer<?> argsSerializer,
    RedisSerializer<T> resultSerializer,
    List<K> keys,
    Object... args
);
```

Ví dụ template ứng dụng có value serializer không phải String, nhưng script mong `ARGV[1]` là text và trả text:

```java
import java.util.List;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

RedisSerializer<String> utf8 = new StringRedisSerializer();

DefaultRedisScript<String> echo = new DefaultRedisScript<>();
echo.setScriptText("return ARGV[1]");
echo.setResultType(String.class);

String reply = redisTemplate.execute(
    echo,
    utf8,                  // args serializer
    utf8,                  // result serializer
    List.of("demo:echo"),  // key list
    "Xin chào Lua"
);
```

Trong ví dụ `redisTemplate` là bean `RedisTemplate<String, ?>` được cấu hình phù hợp. Khi truyền một key ở danh sách mà script không sử dụng, vẫn nên cân nhắc bỏ key không cần thiết; ví dụ echo chỉ sử dụng `ARGV`, vì vậy có thể truyền `List.of()`.

Điểm cần ghi nhớ: overload này tùy chỉnh **args serializer** và **result serializer**. **Key serializer vẫn do template quyết định**, vì vậy nếu key cần là chuỗi Redis thông thường, phải cấu hình `template.setKeySerializer(...)` tương ứng hoặc dùng `StringRedisTemplate`.

### 10.1. Trường hợp result type là Long

Với một script `RedisScript<Long>`, kết quả Redis integer được Spring Data Redis chuyển thẳng theo result type. Không nên cố giải mã integer reply như byte UTF-8 hay JSON object.

Vì Java generic của overload yêu cầu result serializer tương ứng với `T`, khi gọi script trả `Long`, đơn giản nhất thường là:

```java
Long count = stringRedisTemplate.execute(
    longScript,
    List.of("counter:{x}:value"),
    "1"
);
```

Nếu phải truyền args bằng serializer riêng, cần chọn cách gọi và cấu hình serializer sao cho đúng contract API của phiên bản Spring Data Redis đang sử dụng. Không tạo một `RedisSerializer<String>` rồi giả định nó là `RedisSerializer<Long>`.

### 10.2. Khi nào cần custom serializer?

- Template chính đang dùng JDK serialization nhưng Lua cần tham số text.
- Template value dùng JSON, còn một script trả chuỗi Redis thô.
- Script trả JSON với schema xác định, muốn deserialize trực tiếp thành DTO.
- Script xử lý một payload nhị phân có định dạng riêng.
- Cần tách serializer của giá trị Redis được lưu với serializer của argument script.

Việc có thể đặt serializer khác trong lần gọi **không tự thay đổi định dạng dữ liệu đã lưu trong Redis**. Script đọc key vẫn nhận byte mà key đó đang lưu. Nếu value gốc được viết bằng JDK serialization, `GET` trong Lua vẫn trả byte nhị phân, dù `ARGV` dùng UTF-8 String.

## 11. Vấn đề khi dùng JdkSerializationRedisSerializer

Một `RedisTemplate` có thể được cấu hình dùng `JdkSerializationRedisSerializer` cho value. Khi đó, một String Java `"10"` không được gửi lên Redis như hai byte ký tự `1`, `0`; nó được đóng gói thành một luồng byte Java serialization.

Nếu script:

```lua
local quantity = tonumber(ARGV[1])
```

thì `ARGV[1]` không còn là chuỗi `"10"` thuần. Chuyển bằng `tonumber` có thể thất bại.

Tương tự, nếu key tồn kho được ghi qua JDK value serializer:

```java
redisTemplate.opsForValue().set("stock:available", 20L);
```

giá trị Redis là dữ liệu nhị phân được serialize, không phải văn bản `"20"`. Lua:

```lua
local n = tonumber(redis.call('GET', KEYS[1]))
```

không thể tự giải mã object `Long` trong Java serialization.

### 11.1. Khắc phục thế nào?

Chọn một trong các chiến lược nhất quán:

- Với counter, balance, stock integer: ghi dữ liệu dạng **Redis String số nguyên** bằng serializer chuỗi và truyền tham số script bằng chuỗi tương ứng.
- Với DTO: lưu JSON có schema rõ ràng và dùng `cjson.decode` ở Lua nếu thực sự cần thao tác nội dung.
- Với dữ liệu nhị phân: chỉ xử lý trong Lua bằng logic phù hợp với định dạng đó, hoặc không đưa logic nghiệp vụ cần giải mã object Java vào Lua.
- Nếu ứng dụng cần cả Java object serialization và Lua script, tách namespace/key phù hợp để tránh dùng sai định dạng.

Tránh trộn `StringRedisTemplate` và `RedisTemplate` khác serializer trên **cùng key** khi hai bên không chia sẻ wire format.

## 12. Sử dụng JSON cho tham số truyền vào Lua

Giả sử Java cần truyền một yêu cầu giữ hàng:

```json
{
  "quantity": 3,
  "requestId": "req-1001"
}
```

Có thể serialize ở Java thành JSON string:

```java
public record ReserveRequest(long quantity, String requestId) {}

ReserveRequest request = new ReserveRequest(3L, "req-1001");
String requestJson = objectMapper.writeValueAsString(request);

String responseJson = stringRedisTemplate.execute(
    jsonScript,
    List.of("stock:{sku-42}:available"),
    requestJson
);
```

Lua:

```lua
local ok, request = pcall(cjson.decode, ARGV[1])

if not ok or type(request) ~= 'table' then
    return cjson.encode({
        success = false,
        reason = 'INVALID_JSON'
    })
end

local quantity = tonumber(request.quantity)

if quantity == nil or quantity <= 0 then
    return cjson.encode({
        success = false,
        reason = 'INVALID_QUANTITY'
    })
end

-- Tiếp tục kiểm tra requestId và xử lý nghiệp vụ.
return cjson.encode({
    success = true,
    acceptedQuantity = quantity
})
```

Đây là ví dụ hợp đồng dữ liệu. `pcall` giúp xử lý lỗi parse JSON mà không lập tức làm script thất bại. Ứng dụng vẫn cần kiểm tra độ dài payload, kiểu trường, khoảng giá trị và idempotency theo yêu cầu nghiệp vụ.

**Không tự mặc định mọi JSON number là số nguyên chính xác tùy ý.** Nếu giá trị có thể vượt giới hạn chính xác của số Lua, nên truyền định dạng và xử lý riêng phù hợp.

### 12.1. Khi nào nên tách nhiều ARGV thay vì một JSON?

Với hai hoặc ba tham số đơn giản:

```java
redis.execute(script, keys, "3", "req-1001", "CONFIRMED");
```

Lua:

```lua
local quantity = tonumber(ARGV[1])
local requestId = ARGV[2]
local state = ARGV[3]
```

cách này ít bước encode/decode hơn. Nhưng cần tài liệu quy định **thứ tự và ý nghĩa từng ARGV**. Khi giao diện script có nhiều trường tùy chọn hoặc thay đổi qua phiên bản, một JSON có schema có thể dễ mở rộng hơn.

## 13. Các kiểu trả về cần tránh hiểu sai

### 13.1. Lua boolean khác Java Boolean

Trong quy tắc chuyển đổi Lua sang Redis reply theo RESP2, `true` có thể được biểu diễn như integer `1`, còn `false` như nil reply. Vì vậy, nếu ứng dụng cần kết quả boolean rõ ràng, một cách dễ đọc là:

```lua
return redis.call('EXISTS', KEYS[1])
```

và khai báo `RedisScript<Boolean>` khi phù hợp. Nếu cần phân biệt “không có kết quả”, “thất bại nghiệp vụ”, “không đủ điều kiện”, nên trả **mã integer** hoặc JSON có trường `status`.

Đừng dùng `false` để biểu diễn cả “không tồn tại” và “script không trả kết quả”; điều đó làm mơ hồ hợp đồng Java.

### 13.2. Số của Lua trả về Redis integer có thể làm mất phần lẻ

```lua
return 2.5
```

không phải cách tin cậy để trả Java `Double` đúng `2.5` trong môi trường Lua/Redis thông dụng. Hãy dùng định dạng chuỗi hoặc JSON khi cần biểu diễn số thực, đồng thời kiểm soát độ chính xác của phép tính.

### 13.3. JSON string không tự thành Java DTO

```lua
return cjson.encode({code='OK', count=3})
```

trả **bulk string JSON**, không tự trả một `Map<String, Object>` Java. Để lấy DTO, sử dụng result serializer thích hợp hoặc nhận `String` rồi dùng Jackson.

### 13.4. Array của Lua không tự thành object có tên trường

```lua
return {'OK', '3'}
```

trả array theo vị trí, không có tên trường `code` hay `count`. Nếu giao diện cần ổn định khi thêm trường, cân nhắc JSON với tên trường.

### 13.5. Redis nil và exception là hai loại kết quả khác nhau

Nếu script:

```lua
return nil
```

thì Java có thể nhận `null`.

Nếu script:

```lua
return redis.error_reply('INVALID_INPUT')
```

thì client thường nhận lỗi Redis và Spring Data Redis chuyển thành exception phù hợp. Không nên xử lý lỗi Redis như một DTO thành công có giá trị `null`.

## 14. Script lỗi: dữ liệu đã ghi trước lỗi có được rollback không?

Lua script thực thi nguyên tử theo nghĩa không có lệnh từ client khác xen giữa quá trình script chạy trên Redis. Nhưng **nguyên tử về khả năng xen lệnh không đồng nghĩa rollback toàn bộ thay đổi nếu script lỗi giữa chừng**.

Ví dụ:

```lua
redis.call('SET', KEYS[1], 'DONE')
redis.call('INCR', KEYS[2])  -- Có thể lỗi nếu value không phải số.
return 1
```

Nếu `SET` thực hiện thành công và `INCR` sau đó lỗi, các tác động đã được thực hiện trước lỗi có thể **không bị hoàn tác**.

Các nguyên tắc thiết kế:

1. **Validate input trước khi ghi.** Kiểm tra `ARGV` có đủ, có đúng kiểu và nằm trong khoảng hợp lệ.
2. **Kiểm tra trạng thái cần thiết trước khi ghi.** Ví dụ lượng tồn kho, trạng thái đơn, version.
3. **Hạn chế lỗi runtime sau lần ghi đầu tiên.** Dùng cấu trúc dữ liệu và kiểu giá trị được kiểm soát.
4. **Xử lý exception phía Java.** Phân biệt lỗi script, lỗi Redis, timeout và kết quả nghiệp vụ hợp lệ.
5. **Thiết kế idempotency/recovery** khi lệnh có thể đã chạy nhưng client mất phản hồi.

`redis.call` thường đưa lỗi Redis thành lỗi script; `redis.pcall` trả về một cấu trúc lỗi để Lua xử lý. Việc bắt lỗi không có nghĩa mọi dữ liệu đã ghi tự rollback. Tránh dùng `pcall` để che giấu một trạng thái không nhất quán.

## 15. Bảo đảm keys của script đúng với Redis Cluster

Khi gọi `RedisTemplate.execute` trên Redis Cluster, danh sách `keys` không chỉ là biến truyền vào Lua. Những key này liên quan đến việc client xác định hash slot và điều kiện thao tác multi-key hợp lệ.

Ví dụ cùng slot:

```java
List<String> keys = List.of(
    "order:{o-101}:state",
    "order:{o-101}:receipt"
);
```

Lua:

```lua
redis.call('SET', KEYS[1], ARGV[1])
redis.call('SET', KEYS[2], ARGV[2])
return 1
```

Hai key có cùng tag `{o-101}` nên được hash về cùng slot. Ngược lại:

```java
List<String> keys = List.of(
    "order:{o-101}:state",
    "inventory:{sku-42}:available"
);
```

không được bảo đảm cùng slot. Script không thể biến các thao tác trên hai primary thành một transaction phân tán.

### 15.1. Key serializer cũng ảnh hưởng hash slot

Đối với Redis Cluster, slot được tính từ **byte của key thực tế**. Nếu template dùng JDK serialization cho key, wire key không phải chuỗi dễ đọc mà bạn nhìn thấy trong Java. Điều đó có thể khiến:

- Key không trùng với key đã tạo bằng `StringRedisTemplate`.
- Hash tag không được nhận diện như mong đợi trong dữ liệu byte.
- `CLUSTER KEYSLOT` trên chuỗi người vận hành nhập vào khác với slot của key nhị phân mà ứng dụng gửi.

Khi làm việc với Redis Cluster và Lua, hãy sử dụng chiến lược key serializer nhất quán, thường là `StringRedisSerializer`, đặc biệt nếu đặt hash tag bằng các ký tự `{` và `}`.

### 15.2. Không lồng key ngẫu nhiên trong JSON ARGV

Nếu script nhận JSON:

```json
{"targetKey":"account:{other}:balance"}
```

rồi gọi:

```lua
redis.call('SET', request.targetKey, '100')
```

thì script đã ẩn một tên key trong ARGV. Điều đó vi phạm mô hình khai báo key rõ ràng cho Cluster và có thể gây lỗi hoặc hành vi định tuyến không hợp lệ. Các Redis key được script truy cập phải được đưa qua danh sách `KEYS` và đáp ứng giới hạn slot.

## 16. EVALSHA, script cache và serializer là hai trách nhiệm khác nhau

Spring Data Redis thường sử dụng `ScriptExecutor` để thực thi RedisScript. Với script đã có trong cache của Redis, client có thể sử dụng `EVALSHA` theo SHA của source script; nếu Redis không nhận biết SHA, cơ chế thực thi có thể fallback sang `EVAL`.

Điều này **không làm thay đổi** cách tuần tự hóa `KEYS`, `ARGV` hoặc giải tuần tự hóa kết quả:

```text
Script source + SHA:
    xác định chương trình Lua nào thực thi.

keySerializer:
    xác định bytes của KEYS.

argsSerializer:
    xác định bytes của ARGV.

RedisScript resultType + resultSerializer:
    xác định Java nhận dạng kết quả như thế nào.
```

Có thể tái sử dụng một `RedisScript` như singleton bean thay vì tạo source mới cho mỗi request. Việc tái sử dụng giúp giảm chi phí xử lý resource/source và phù hợp cơ chế script cache, nhưng không thay thế kiểm tra đầu vào và hợp đồng kết quả.

Khi script được thay đổi, SHA cũng thay đổi theo nội dung; hệ thống cần triển khai đồng nhất giữa các instance để tránh Java mong format kết quả cũ trong khi script mới đã trả schema khác.

## 17. Cách xử lý lỗi ở tầng Service

Một service gọi Lua nên phân biệt:

- **Kết quả nghiệp vụ:** ví dụ `1` thành công, `0` không đủ hàng.
- **Kết quả không hợp lệ:** trả `null`, mã lạ, JSON thiếu trường quan trọng.
- **Lỗi script/serializer:** Redis reply không tương thích hoặc Lua báo lỗi.
- **Lỗi vận hành:** timeout, mất kết nối, failover.
- **Kết quả không xác định vì timeout:** có thể script đã hoàn thành nhưng Java chưa nhận được phản hồi.

Ví dụ xử lý mã:

```java
Long code = stringRedisTemplate.execute(
    reserveStockScript,
    List.of(key),
    Long.toString(quantity)
);

if (code == null) {
    throw new IllegalStateException("Script returned null");
}

switch (code.intValue()) {
    case 1:
        // Reservation thành công.
        break;
    case 0:
        // Không đủ hàng.
        break;
    case -1:
        // Key chưa được khởi tạo.
        break;
    case -2:
        // Tham số không hợp lệ.
        break;
    case -3:
        // Dữ liệu tồn kho không phải số.
        break;
    default:
        throw new IllegalStateException(
            "Unexpected Lua status code: " + code
        );
}
```

Đoạn code minh họa cách phân loại status; trong ứng dụng thật, nên chuyển thành enum/kết quả nghiệp vụ phù hợp thay vì để tầng controller hiểu các mã `-1`, `-2`, `-3`.

**Không retry mù một script có side effect** sau timeout. Nếu script đã trừ tồn kho nhưng response bị mất, retry lại có thể trừ thêm lần nữa. Khi cần bảo đảm, đưa idempotency token vào contract và lưu trạng thái xử lý token theo cơ chế nguyên tử cùng key/slot.

### 17.1. Ví dụ contract idempotency đơn giản

Trong Redis Cluster, có thể colocate hai key:

```text
stock:{sku-42}:available
stock:{sku-42}:request:req-1001
```

Lua kiểm tra request đã xử lý chưa; nếu chưa thì kiểm tra tồn kho, trừ và lưu kết quả xử lý request. Các key cùng tag `{sku-42}`, vì vậy có thể thao tác cùng slot khi client hỗ trợ.

Tuy nhiên phải xác định TTL và tính duy nhất của request ID. Nếu key idempotency hết hạn quá sớm, request cũ được gửi lại có thể bị xử lý thêm lần nữa. Một chiến lược giữ token có giới hạn thời gian không bảo đảm idempotency vĩnh viễn.

## 18. Bảng lỗi thường gặp và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `tonumber(ARGV[1])` trả `nil` | `ARGV` chứa bytes Java serialization, JSON string không mong đợi hoặc text không phải số | Kiểm soát `argsSerializer`, truyền decimal String và validate |
| Java nhận lỗi deserialize khi Lua trả `"OK"` | Template dùng JDK/JSON value serializer nhưng script trả text thuần | Dùng `StringRedisSerializer` cho result hoặc chuyển định dạng trả về |
| Java nhận `null` dù mong String | Key không tồn tại, Lua `false`/`nil`, hoặc khai báo result type không phù hợp | Quy định rõ nil vs error; kiểm tra kết quả |
| Java mong `Double` nhưng nhận giá trị khác | Lua number thường được chuyển thành Redis integer reply trong ngữ cảnh phổ biến | Trả string/JSON khi cần số thực; parse rõ ở Java |
| Java ép `List<String>` gây `ClassCastException` | Redis array chứa integer, nil hoặc nested reply | Dùng `List<?>`, kiểm tra từng phần tử hoặc trả JSON |
| `CROSSSLOT` khi script nhiều key | KEYS không cùng slot | Dùng hash tag theo aggregate và kiểm tra `CLUSTER KEYSLOT` |
| Key tồn tại trong CLI nhưng script GET không đọc được | Key serializer hoặc Redis database khác nhau | Xác nhận byte wire format và cấu hình kết nối |
| Lua `GET` có bytes lạ | Giá trị đã lưu bằng JDK/JSON serializer khác kỳ vọng | Chuẩn hóa định dạng value, không đọc nhị phân như text |
| JSON parse error | Lua trả status khác JSON hoặc payload bị sai schema | Chỉ định script result `String`, kiểm tra/parse JSON có xử lý lỗi |
| Script báo lỗi sau khi đã ghi một phần | Runtime error sau command write | Validate trước, giữ script ngắn, thêm recovery và idempotency |
| `NoScript`/cần tải script lại | Script SHA chưa có trong cache của node | Dùng ScriptExecutor/fallback EVAL phù hợp, không tự đoán cache dùng chung mọi node |
| Timeout sau `execute` | Redis/network/driver, trạng thái thực thi chưa rõ | Dùng request ID và xác minh kết quả trước retry |

## 19. Đo đạc và quan sát thực tế

Để hiểu một script đang truyền gì, hãy chọn key và args thử nghiệm trên môi trường độc lập:

```redis
SET demo:lua:counter 10
EVAL "return {KEYS[1],ARGV[1],redis.call('GET',KEYS[1])}" 1 demo:lua:counter 3
```

So sánh với lời gọi từ `StringRedisTemplate`. Nếu hai bên biểu diễn chuỗi giống nhau, kết quả dễ dự đoán hơn.

Với script production:

1. Ghi metric tỷ lệ thành công, từ chối nghiệp vụ và lỗi vận hành.
2. Ghi latency, số lời gọi và kích thước payload theo nhóm; không log dữ liệu nhạy cảm hoặc object serialization raw.
3. Giới hạn kích thước `ARGV` nếu nhận dữ liệu JSON từ API.
4. Đảm bảo script ngắn, không vòng lặp không giới hạn hay trả mảng kết quả quá lớn.
5. Đo memory và output buffer nếu script trả JSON/array nhiều dữ liệu.
6. Xem xét schema version khi thay đổi format của result.

Lệnh `EVAL` và `EVALSHA` thực thi trên Redis node; script dài có thể làm tăng độ trễ của các request khác vì quá trình thực thi script không cho những lệnh khác xen vào theo cơ chế atomic của Redis.

## 20. Khi nào chọn dạng kết quả nào?

| Yêu cầu | Hướng chọn | Lý do |
|---|---|---|
| Tăng bộ đếm, trả số nguyên mới | `RedisScript<Long>` | Nhận Redis integer trực tiếp |
| Kiểm tra tồn tại hoặc điều kiện yes/no | `RedisScript<Boolean>` hoặc `Long` | Boolean khi chỉ có hai trạng thái; Long cho nhiều mã |
| Trả một chuỗi/trạng thái đơn giản | `RedisScript<String>` với serializer chuỗi | Định dạng ngắn, dễ hiểu |
| Trả danh sách giá trị đơn giản | `RedisScript<List>` | Dùng Redis array; cần kiểm tra kiểu từng phần tử |
| Trả DTO nhiều trường | JSON text + `String` + Jackson | Hợp đồng có tên field, dễ versioning |
| Trả dữ liệu nhị phân có codec riêng | Serializer tương thích được chọn tường minh | Cần kiểm soát bytes và schema |
| Script chỉ ghi, Java không cần value | Result type `null`/`Void` phù hợp | Tránh deserialize không cần thiết; vẫn xử lý lỗi |

Không có một serializer tốt nhất cho mọi loại dữ liệu. Cách phù hợp là xác định **hợp đồng wire format** giữa Java và Lua trước, sau đó cấu hình template, script và result type tuân theo cùng hợp đồng.

## 21. Bài thực hành có hướng dẫn

### Bài 1 — Nhận biết KEYS và ARGV

Gọi từ Redis CLI:

```redis
EVAL "return {KEYS[1],ARGV[1],ARGV[2]}" 1 demo:lua:key 12 READY
```

Hãy xác định từng phần tử được trả về. Sau đó viết lời gọi `StringRedisTemplate.execute` tương đương, dùng `RedisScript<List>` và các đối số `"12"`, `"READY"`.

### Bài 2 — Bẫy serializer

Tạo hai template: một dùng `StringRedisSerializer` cho value, một dùng JDK serialization. Cùng truyền chuỗi `"12"` vào script:

```lua
local n = tonumber(ARGV[1])
if not n then return -1 end
return n + 1
```

Hãy giải thích vì sao byte đầu vào có thể khác nhau, và cách dùng overload `execute` với `argsSerializer` tường minh để script nhận văn bản số. Không cần xem Java object giống nhau thì wire bytes cũng giống nhau.

### Bài 3 — Xử lý kết quả JSON

Viết Lua trả:

```lua
return cjson.encode({
    accepted = true,
    remaining = 7,
    reason = 'OK'
})
```

Dùng `RedisScript<String>` và `ObjectMapper` để parse DTO Java. Sau đó thử đổi `reason` hoặc thêm trường `requestId` để xem vì sao JSON có tên field dễ mở rộng hơn mảng theo vị trí.

### Bài 4 — Kết quả nil và lỗi

Viết hai script:

```lua
return redis.call('GET', KEYS[1])
```

và:

```lua
return redis.error_reply('INVALID_REQUEST')
```

Gọi bằng `StringRedisTemplate` với một key không tồn tại. So sánh trường hợp Java nhận `null` với trường hợp client ném exception.

### Bài 5 — Cluster và hash tag

Khai báo hai key:

```text
order:{o-9}:state
order:{o-9}:receipt
```

Dùng `CLUSTER KEYSLOT` trên Redis Cluster để xác nhận chúng cùng slot. Viết script cập nhật cả hai key bằng `KEYS[1]`, `KEYS[2]`, truyền giá trị qua `ARGV[1]`, `ARGV[2]`. Giải thích vì sao một key thứ ba với tag `{o-10}` không thể tự động tham gia vào cùng giao dịch nguyên tử.

### Bài 6 — Giữ hàng an toàn

Dùng script `reserve-stock.lua` ở phần 5:

1. Khởi tạo tồn kho `"20"` bằng `StringRedisTemplate`.
2. Thử yêu cầu 3 đơn vị, xem kết quả `1` và tồn kho 17.
3. Thử yêu cầu 100 đơn vị, xem kết quả `0` và tồn kho giữ nguyên.
4. Thử số lượng âm hoặc không đúng kiểu ở đầu vào.
5. Xóa key tồn kho rồi gọi lại, kiểm tra mã `-1`.
6. Mô tả cơ chế cần thêm để chống trừ hàng hai lần khi Java timeout và retry cùng request.

## 22. Ghi nhớ

- `KEYS` và `ARGV` trong Lua là dữ liệu Redis nhận ở dạng byte; Lua **không trực tiếp nhận object Java**.
- Mặc định, Spring Data Redis thường dùng **key serializer cho KEYS** và **value serializer cho ARGV**, còn việc giải mã kết quả phụ thuộc `RedisScript<T>` và result serializer.
- `StringRedisTemplate` đơn giản khi script cần văn bản và số biểu diễn bằng chuỗi; `RedisTemplate` với JDK/JSON serializer có thể gửi bytes hoàn toàn khác.
- `RedisScript<Long>`/`Boolean` sử dụng chuyển đổi kiểu reply Redis thích hợp; bulk string và array đòi hỏi serializer và result type phù hợp.
- Với DTO phức tạp, JSON text + Jackson là một hợp đồng rõ ràng. Redis array và JSON array là **hai dạng phản hồi khác nhau**.
- `tonumber(ARGV[i])` cần được kiểm tra, nhất là với đầu vào không hợp lệ và giá trị quá lớn cho tính toán chính xác trong Lua.
- Overload `execute` có thể chọn **args serializer** và **result serializer** riêng; key serializer vẫn do template xác định.
- Script nguyên tử về khả năng xen lệnh, nhưng **không tự rollback các ghi đã xảy ra trước runtime error**.
- Trên Redis Cluster, key mà script truy cập phải được khai báo và tuân thủ ràng buộc hash slot; tham số trong `ARGV` không được dùng để lách ràng buộc đó.
- Hợp đồng trả về phải mô tả rõ `null`, status code, JSON schema và exception; với thao tác có side effect, cần thiết kế idempotency trước khi retry sau timeout.

### Tài liệu tham khảo chính thức

- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Serializers](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html)
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/)
- [Redis — EVALSHA](https://redis.io/docs/latest/commands/evalsha/)
- [Redis — Lua API and scripts](https://redis.io/docs/latest/develop/programmability/lua-api/)
- [Redis — Lua scripts introduction](https://redis.io/docs/latest/develop/programmability/eval-intro/)
- [Redis — Scripting and atomicity](https://redis.io/docs/latest/develop/programmability/eval-intro/)

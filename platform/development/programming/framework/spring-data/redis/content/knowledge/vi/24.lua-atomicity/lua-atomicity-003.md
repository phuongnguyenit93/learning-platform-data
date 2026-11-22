# Truyền danh sách khóa, tham số và kiểu kết quả khi chạy Lua trong Spring Data Redis

## 1. Vì sao phải tách khóa, tham số và kết quả?

Spring Data Redis cho phép chạy Lua script trên Redis thông qua `RedisTemplate.execute(RedisScript<T>, List<K>, Object...)`. Đây là công cụ hữu ích khi một nghiệp vụ cần **đọc điều kiện rồi ghi dữ liệu như một thao tác nguyên tử tại Redis**: ví dụ chỉ xóa khóa nếu token còn đúng, trừ số lượng tồn kho có điều kiện, tăng bộ đếm hoặc cập nhật nhiều khóa theo một quy tắc.

Để script dễ dùng và an toàn, cần phân biệt ba thành phần:

- **Danh sách khóa**: những Redis key mà script sẽ truy cập, truyền qua tham số `keys` của Java và nhận trong bảng Lua `KEYS`.
- **Danh sách tham số nghiệp vụ**: token, số lượng, TTL, trạng thái mong đợi..., truyền qua `args` của Java và nhận trong bảng Lua `ARGV`.
- **Kết quả**: giá trị script `return`, được Spring Data Redis chuyển sang kiểu Java đã khai báo trong `RedisScript<T>` và xử lý bằng serializer phù hợp.

Ví dụ logic: *xóa khóa khóa phiên làm việc chỉ khi giá trị hiện tại trùng token người gọi cung cấp*.

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

Ý nghĩa:

| Biểu thức | Giá trị mẫu | Vai trò |
| --- | --- | --- |
| `KEYS[1]` | `lock:order:42` | Tên Redis key cần đọc và có thể xóa |
| `ARGV[1]` | `request-token-abc` | Giá trị cần so sánh với nội dung khóa |
| `return 1` | `1` | Đã xóa một khóa |
| `return 0` | `0` | Khóa không tồn tại hoặc token không khớp |

Lệnh `GET` và `DEL` được thực hiện bên trong một script chạy tại Redis. Không có tiến trình khác xen vào giữa hai lệnh của script, tránh được khoảng đua của cách `GET` rồi `DEL` qua hai lời gọi riêng.

## 2. Từ `EVAL` của Redis sang `RedisTemplate.execute(...)`

Redis có cú pháp tổng quát:

```redis
EVAL "return {KEYS[1], KEYS[2], ARGV[1], ARGV[2]}" 2 first:key second:key alpha beta
```

Cấu trúc:

```text
EVAL <script> <numkeys> <key1> ... <keyN> <arg1> ... <argM>
                       |-----------------| |---------------|
                              KEYS                  ARGV

Lua:
KEYS[1] = "first:key"
KEYS[2] = "second:key"
ARGV[1] = "alpha"
ARGV[2] = "beta"
```

Ở Redis CLI, `numkeys = 2` cho Redis biết **hai đối số tiếp theo là tên khóa**, các đối số còn lại là tham số thường. Script không cần khai báo `numkeys` một lần nữa.

Trong Spring Data Redis:

```java
List<String> keys = List.of("first:key", "second:key");
List<?> result = redisTemplate.execute(
        script, keys, "alpha", "beta");
```

Spring tự tính số lượng khóa từ `keys.size()` và gửi lệnh tương ứng (thường ưu tiên `EVALSHA` nếu script đã có trong cache, fallback khi cần). Lập trình viên cần giữ **đúng thứ tự** các khóa và tham số mà Lua mong đợi.

Một số quy tắc quan trọng:

1. Lua đánh chỉ số bảng từ **1**, vì vậy dùng `KEYS[1]` và `ARGV[1]`; không dùng `KEYS[0]` như mảng Java.
2. Truyền `keys` bằng `List.of(...)`; truyền các đối số còn lại qua `Object... args` theo đúng thứ tự.
3. `KEYS` chứa **tên khóa**, không phải nội dung của khóa. Dùng `redis.call('GET', KEYS[1])` để đọc dữ liệu.
4. `ARGV` chứa **giá trị tham số**, chẳng hạn token, TTL hay số lượng; không chuyển key name vào `ARGV` rồi tự tạo tên khóa trong Lua.
5. Số lượng khóa và số lượng đối số có thể khác nhau; chúng không phải các cặp key/value tương ứng theo vị trí.
6. Mọi giá trị chuyển qua giao thức Redis đều có dạng được serialize. Trong Lua, dữ liệu lấy từ `ARGV` thông thường là chuỗi/byte string, dù phía Java truyền số.

## 3. Định nghĩa script bằng `DefaultRedisScript<T>`

Spring Data Redis đại diện script qua interface `RedisScript<T>`. Với script tự viết, lớp phổ biến là `DefaultRedisScript<T>`.

Ví dụ dùng script “so sánh token rồi xóa”:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class RedisLuaConfiguration {

    @Bean
    public RedisScript<Boolean> compareAndDeleteScript() {
        DefaultRedisScript<Boolean> script = new DefaultRedisScript<>();

        script.setScriptText("""
                if redis.call('GET', KEYS[1]) == ARGV[1] then
                    return redis.call('DEL', KEYS[1])
                end
                return 0
                """);

        script.setResultType(Boolean.class);
        return script;
    }
}
```

Chúng ta khai báo kiểu `Boolean.class` vì script trả Redis integer `1` khi xóa thành công, `0` khi không xóa; executor của Spring Data Redis có khả năng ánh xạ các giá trị integer đó sang Boolean.

Dùng trong service:

```java
import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class LeaseTokenService {

    private final StringRedisTemplate redis;
    private final RedisScript<Boolean> compareAndDeleteScript;

    public LeaseTokenService(
            StringRedisTemplate redis,
            @Qualifier("compareAndDeleteScript")
            RedisScript<Boolean> compareAndDeleteScript) {
        this.redis = redis;
        this.compareAndDeleteScript = compareAndDeleteScript;
    }

    public boolean releaseIfOwner(String resourceId, String token) {
        if (resourceId == null ||
                !resourceId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("resourceId không hợp lệ");
        }
        if (token == null || token.isBlank()) {
            throw new IllegalArgumentException("token không hợp lệ");
        }

        String key = "lock:resource:" + resourceId;

        Boolean removed = redis.execute(
                compareAndDeleteScript,
                List.of(key),
                token
        );

        return Boolean.TRUE.equals(removed);
    }
}
```

Ở đây:

- `List.of(key)` được đưa vào `KEYS[1]`.
- `token` được đưa vào `ARGV[1]`.
- Script trả `1` hoặc `0`; Java nhận `Boolean.TRUE` hoặc `Boolean.FALSE`.
- `Boolean.TRUE.equals(removed)` còn an toàn khi kết quả `null`, chẳng hạn trong một chế độ thực thi lệnh bị queue hoặc response chưa có.

Đoạn code minh họa **bước giải phóng khóa theo token**, không phải toàn bộ thuật toán distributed lock. Khi dùng lock thật, cần cấp token độc nhất cho mỗi lần sở hữu, TTL, cách xử lý mất kết nối và ràng buộc nghiệp vụ phù hợp. Không cho client khác tùy ý truyền một token dùng chung của hệ thống.

### Lưu script ở resource thay vì viết inline

Với script dài, nên tạo file, ví dụ `src/main/resources/scripts/compare-and-delete.lua`:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

Bean tương ứng:

```java
@Bean
public RedisScript<Boolean> compareAndDeleteScript() {
    DefaultRedisScript<Boolean> script = new DefaultRedisScript<>();
    script.setLocation(
            new ClassPathResource("scripts/compare-and-delete.lua"));
    script.setResultType(Boolean.class);
    return script;
}
```

Import `org.springframework.core.io.ClassPathResource`. Nên khai báo script bean một lần và tái sử dụng; `DefaultRedisScript` tính và cung cấp SHA-1 của nội dung script cho cơ chế chạy script theo hash. Không cần tạo một `DefaultRedisScript` mới mỗi request.

## 4. Quy tắc truyền danh sách `KEYS`

### 4.1. Truyền đúng số và đúng thứ tự

Giả sử script cần đọc số lượng tồn kho tại khóa thứ nhất, ghi số lượng đã đặt tại khóa thứ hai:

```text
KEYS[1] -> stock:{sku42}:available
KEYS[2] -> stock:{sku42}:reserved
ARGV[1] -> 3
```

Java:

```java
List<String> keys = List.of(
        "stock:{sku42}:available",
        "stock:{sku42}:reserved"
);

Long result = redis.execute(reserveScript, keys, "3");
```

Nếu đảo hai khóa, script có thể trừ nhầm bộ đếm. Lập trình viên nên đặt tên biến và chú thích hợp đồng KEYS/ARGV ở đầu script:

```lua
-- KEYS[1]: stock available
-- KEYS[2]: stock reserved
-- ARGV[1]: số đơn vị cần đặt
```

Một cách hữu ích là để Java tạo đủ danh sách `keys` tại một nơi, không xây danh sách lặp rải rác trong nhiều service.

### 4.2. Tất cả key script truy cập phải khai báo trong `KEYS`

Redis yêu cầu tên khóa được script truy cập phải được đưa vào danh sách key arguments. Tránh viết:

```lua
-- Không nên: tên key lại được xây từ ARGV
local key = "stock:" .. ARGV[1]
return redis.call('GET', key)
```

Cách phù hợp:

```lua
-- Java đưa "stock:sku42" vào KEYS[1]
return redis.call('GET', KEYS[1])
```

Quy tắc này quan trọng vì Redis Cluster cần xác định node/hash slot chứa các khóa; Redis cũng cần phân biệt khóa với dữ liệu thường trong command metadata và các chính sách liên quan.

### 4.3. Key serializer

Với `StringRedisTemplate`, tên khóa được mã hóa bằng `StringRedisSerializer` nên Lua thường nhìn thấy chính các tên khóa dạng text như `stock:sku42`.

Với `RedisTemplate<K,V>` dùng serializer khác, chuỗi key có thể được mã hóa thành bytes không giống tên người đọc thấy qua `redis-cli`. Script chạy theo **bytes của Redis key**, không theo cách Java hiển thị đối tượng key.

Nếu dữ liệu được lưu với key serializer A nhưng script truyền key bằng serializer B, Lua có thể truy cập một key hoàn toàn khác dù string Java nhìn giống nhau. Hãy thống nhất key serialization giữa cách lưu dữ liệu và cách gọi script.

## 5. Redis Cluster: các khóa phải nằm trong cùng hash slot

Khi script thao tác nhiều khóa trên Redis Cluster, các khóa cần nằm trong cùng **hash slot**. Hai tên khóa khác nhau thường được phân phối sang slot khác nhau và lệnh nhiều khóa có thể gặp `CROSSSLOT`.

Ví dụ có nguy cơ khác slot:

```text
stock:sku42:available
stock:sku42:reserved
```

Chúng có thể ở hai slot khác nhau vì toàn bộ tên khóa được dùng để tính hash. Cách chủ động gom slot là dùng **hash tag** nằm trong cặp dấu ngoặc nhọn:

```text
stock:{sku42}:available
stock:{sku42}:reserved
       ^^^^^
       cùng phần dùng để tính slot
```

Cả hai key có tag `sku42` nên cùng hash slot. Không dùng một hash tag chung như `{all}` cho mọi sản phẩm trong hệ thống lớn vì có thể dồn tải vào một slot. Chọn tag đại diện chính cho đơn vị cần giao dịch nguyên tử: product ID, order ID hoặc tenant ID tùy bài toán.

Nếu đang dùng Redis standalone, các khóa không chịu hạn chế cluster slot, nhưng tổ chức tên khóa rõ ràng vẫn giúp migration về sau.

**Không truyền một list KEYs lấy trực tiếp từ người dùng** nếu script có thể ghi/xóa. Tạo tên khóa từ định danh đã validate và prefix cố định tại ứng dụng, đồng thời cấu hình ACL theo nhu cầu.

## 6. Truyền `ARGV` và chuyển đổi kiểu trong Lua

`ARGV` giữ các tham số thông thường ở dạng byte/string sau khi Spring serialize. Lua không tự có loại `Long` hay `BigDecimal` của Java:

```lua
local quantity = tonumber(ARGV[1])
local ttlSeconds = tonumber(ARGV[2])
local status = ARGV[3]
```

Ví dụ phía Java:

```java
redis.execute(
        someScript,
        List.of("order:{42}:state"),
        "3",        // ARGV[1]: quantity
        "120",      // ARGV[2]: ttl
        "PENDING"   // ARGV[3]: status
);
```

### Kiểm tra đầu vào trước khi ghi

Không nên giả định `ARGV[1]` luôn hợp lệ:

```lua
local quantity = tonumber(ARGV[1])

if quantity == nil or quantity <= 0 or quantity % 1 ~= 0 then
    return redis.error_reply('ERR quantity must be a positive integer')
end
```

Nếu thiếu tham số, `tonumber(nil)` trả `nil`. Nếu chuỗi không phải số, `tonumber` cũng có thể trả `nil`. Phép kiểm tra trong Lua bảo vệ script dù bên ngoài Java đã validate.

Nhưng cần nhớ số Lua trong Redis scripting truyền thống dùng kiểu số thực hai độ chính xác; thao tác số nguyên rất lớn có thể mất độ chính xác khi chuyển qua `tonumber`. Với bộ đếm Redis kiểu signed 64-bit, ưu tiên dùng trực tiếp các lệnh `INCRBY`/`DECRBY` với chuỗi số nguyên đã validate và tránh tính toán lớn trong Lua.

Không truyền dữ liệu tùy ý đã serialize theo JDK vào `ARGV` rồi gọi `tonumber` hoặc so sánh chuỗi literal; Lua sẽ nhìn thấy byte format của serializer, không phải text mà lập trình viên kỳ vọng.

### ARGV chứa giá trị, không phải tên biến Java

Spring gửi arguments **theo vị trí**. Nếu Lua viết:

```lua
local expected = ARGV[1]
local replacement = ARGV[2]
```

thì gọi:

```java
redis.execute(compareAndSetScript, List.of(key),
        replacement, expected);  // Sai thứ tự
```

có thể gây sai logic, dù Java vẫn biên dịch bình thường. Nên cung cấp một method service với tham số đặt tên rõ để tránh gọi script trực tiếp ở nhiều nơi.

## 7. Ví dụ hoàn chỉnh: đặt số lượng hàng bằng hai khóa và một tham số

Script nhận hai khóa cùng slot: `available` và `reserved`, cùng số lượng cần đặt trong `ARGV[1]`.

File `scripts/reserve-stock.lua`:

```lua
-- KEYS[1]: stock:{sku}:available
-- KEYS[2]: stock:{sku}:reserved
-- ARGV[1]: quantity, số nguyên dương

local requested = tonumber(ARGV[1])
if requested == nil or requested <= 0 or requested % 1 ~= 0 then
    return redis.error_reply('ERR invalid quantity')
end

local availableRaw = redis.call('GET', KEYS[1])
if availableRaw == false then
    return 0
end

local available = tonumber(availableRaw)
if available == nil or available < requested then
    return 0
end

local reservedRaw = redis.call('GET', KEYS[2])
if reservedRaw ~= false and tonumber(reservedRaw) == nil then
    return redis.error_reply('ERR reserved value is not numeric')
end

redis.call('DECRBY', KEYS[1], ARGV[1])
redis.call('INCRBY', KEYS[2], ARGV[1])
return 1
```

Spring configuration:

```java
@Bean
public RedisScript<Long> reserveStockScript() {
    DefaultRedisScript<Long> script = new DefaultRedisScript<>();
    script.setLocation(
            new ClassPathResource("scripts/reserve-stock.lua"));
    script.setResultType(Long.class);
    return script;
}
```

Java service:

```java
@Service
public class StockReservationService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> reserveStockScript;

    public StockReservationService(
            StringRedisTemplate redis,
            @Qualifier("reserveStockScript")
            RedisScript<Long> reserveStockScript) {
        this.redis = redis;
        this.reserveStockScript = reserveStockScript;
    }

    public boolean reserve(String sku, long quantity) {
        if (sku == null || !sku.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }

        String tag = "{" + sku + "}";
        List<String> keys = List.of(
                "stock:" + tag + ":available",
                "stock:" + tag + ":reserved"
        );

        Long result = redis.execute(
                reserveStockScript, keys, Long.toString(quantity));

        return Long.valueOf(1L).equals(result);
    }
}
```

Ý nghĩa kết quả: `1L` = đã thực hiện nhánh đặt hàng; `0L` = không đủ hàng hoặc khóa available không tồn tại. Trường hợp script báo lỗi Redis, Spring sẽ ném exception tương ứng. Không nên diễn giải mọi exception thành “hết hàng”.

**Ranh giới của ví dụ:** bảo đảm các lệnh trong script không bị thao tác khác xen vào; không bảo đảm *rollback toàn bộ* nếu một lệnh lỗi sau khi lệnh trước đã ghi dữ liệu. Chẳng hạn bộ đếm reserved có thể tràn phạm vi số nguyên ở lệnh `INCRBY` sau khi available đã bị `DECRBY`. Với bài toán tồn kho quan trọng, phải kiểm tra điều kiện tràn, kiểu key và trạng thái cần thiết **trước khi bắt đầu ghi**, thêm idempotency key và quy trình xử lý trường hợp kết quả commit không rõ ràng do mất kết nối.

Nếu cần update tồn kho trên nhiều slot khác nhau, không thể biến một script cross-slot thành hợp lệ bằng cách đổi mã Java; cần thiết kế lại partition/key schema hoặc cơ chế nhất quán liên node.

## 8. Kiểu kết quả `RedisScript<T>`: Long, Boolean, String, List, null

Khi khai báo `DefaultRedisScript<T>`, `setResultType(...)` cho Spring biết cách diễn giải giá trị Redis trả về. Kiểu trả về của Lua và serializer phải thống nhất với điều đó.

| Lua `return` | Phản hồi Redis thông thường | Java nên khai báo | Ví dụ |
| --- | --- | --- | --- |
| `return 42` | Integer reply | `Long.class` | `Long count = ...` |
| `return 1` hoặc `return 0` | Integer reply | `Boolean.class` khi mang nghĩa đúng/sai | `Boolean success = ...` |
| `return "READY"` | Bulk string | `String.class` khi dùng String serializer | `String value = ...` |
| `return {1, "OK"}` | Array reply | `List.class` | `List<?> parts = ...` |
| `return nil` hoặc `return false` theo Lua/RESP2 mapping | Null bulk reply | Có thể nhận `null` ở Java | Phải kiểm tra null |
| Script chỉ tạo side effect, không cần kết quả | Bỏ qua output | `setResultType(null)` | Cần kiểm soát lỗi lệnh |

Spring Data Redis không hỗ trợ mọi class Java tùy ý như một result type trực tiếp; cần quy hoạch response về số nguyên, boolean, array hoặc value có thể deserialize. Với object phức tạp, có thể trả một chuỗi JSON do script tạo và parse ở Java.

### 8.1. Integer: dùng `Long.class`

Lua:

```lua
return redis.call('INCR', KEYS[1])
```

Java:

```java
DefaultRedisScript<Long> script = new DefaultRedisScript<>();
script.setScriptText("return redis.call('INCR', KEYS[1])");
script.setResultType(Long.class);

Long count = stringRedisTemplate.execute(
        script,
        List.of("metrics:requests")
);
```

Redis integer reply được ánh xạ thành `Long`. Không khai báo `Integer.class` chỉ vì số nhỏ: API scripting của Spring Data Redis thường dùng `Long.class` cho integer reply.

### 8.2. Điều kiện đúng/sai: dùng `Boolean.class` và trả `1`/`0`

Lua:

```lua
if redis.call('EXISTS', KEYS[1]) == 1 then
    return 1
end
return 0
```

Java:

```java
DefaultRedisScript<Boolean> script = new DefaultRedisScript<>();
script.setScriptText("""
        return redis.call('EXISTS', KEYS[1]) == 1 and 1 or 0
        """);
script.setResultType(Boolean.class);

Boolean exists = stringRedisTemplate.execute(
        script, List.of("session:42"));
```

Trong Lua, `true` và `false` không tương đương với integer `1` và `0` ở mức Redis reply. Với giao thức Lua/RESP2, `return true` được đổi thành integer `1`, nhưng `return false` thành null reply, dễ bị nhầm với không có kết quả. Vì vậy **trả số `1`/`0` một cách tường minh** giúp Java nhận boolean rõ nghĩa.

### 8.3. Chuỗi: dùng serializer phù hợp

Lua:

```lua
return redis.call('GET', KEYS[1])
```

Java:

```java
DefaultRedisScript<String> script = new DefaultRedisScript<>();
script.setScriptText("return redis.call('GET', KEYS[1])");
script.setResultType(String.class);

String status = stringRedisTemplate.execute(
        script, List.of("order:42:status"));
```

Khi key có dữ liệu string, `StringRedisTemplate` có thể deserialize bulk string về `String`. Nếu key không tồn tại, Redis `GET` trả nil, Spring có thể nhận `null`; `null` không nhất thiết báo script đã thất bại.

Nếu dùng `RedisTemplate<Object,Object>` với default JDK serializer, một Lua string trả về có thể không phải dữ liệu serialize hợp lệ cho Java object. Cần chọn hoặc truyền result serializer rõ ràng.

### 8.4. Danh sách: dùng `List.class` và hiểu phần tử

Lua:

```lua
local exists = redis.call('EXISTS', KEYS[1])
local value = redis.call('GET', KEYS[1]) or ""
return { exists, value }
```

Java:

```java
DefaultRedisScript<List> script = new DefaultRedisScript<>();
script.setScriptText("""
        local exists = redis.call('EXISTS', KEYS[1])
        local value = redis.call('GET', KEYS[1]) or ""
        return { exists, value }
        """);
script.setResultType(List.class);

List<?> result = stringRedisTemplate.execute(
        script, List.of("order:42:status"));

if (result != null && result.size() == 2) {
    Long exists = (Long) result.get(0);
    String value = (String) result.get(1);
}
```

Array reply có thể trộn Redis integer và bulk string, vì vậy `List<?>` không đồng nghĩa mọi phần tử đều là `String`. Cách chuyển đổi các phần tử, nhất là nested arrays hoặc custom serializer, cần được thống nhất trong ứng dụng.

Một table Lua dạng map bất kỳ (ví dụ `{status="OK", count=3}`) không tự biến thành Java `Map<String,Object>` theo ý muốn. Nếu cần cấu trúc ổn định nhiều field, có thể trả JSON string rồi deserialize một cách tường minh ở Java.

### 8.5. Không có giá trị trả về

Nếu Lua không `return` hoặc trả `nil`, Java có thể nhận `null`. Nếu script chỉ ghi dữ liệu và ứng dụng không cần output, `setResultType(null)` thể hiện điều đó. Tuy nhiên, **không thể từ `null` kết luận các lệnh ghi đã thành công** trong mọi trường hợp, đặc biệt khi script nằm trong transaction đang queue hoặc kết nối mất trước khi response về.

Nếu nghiệp vụ cần phân biệt “đã làm”, “không làm” và “lỗi”, hãy thiết kế mã kết quả tường minh hoặc dùng status/error reply thích hợp, đừng gộp tất cả về `null`.

## 9. Serializer: chi tiết quyết định script có đọc đúng dữ liệu hay không

Quá trình thực thi có nhiều điểm serialization:

```text
Java keys       --key serializer--> Redis key bytes --> Lua KEYS
Java args       --args serializer-> Redis bytes     --> Lua ARGV
Lua return      --Redis reply------> result deserializer --> Java T
```

`StringRedisTemplate` là lựa chọn dễ hiểu khi khóa, tham số và value Redis đều là chuỗi. Trái lại, `RedisTemplate<String, SomeClass>` có thể dùng JSON, JDK serializer hoặc định dạng tùy biến cho value; lúc đó Lua không nhất thiết đọc được value thành chuỗi mong đợi.

Ví dụ script so sánh:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return 1
end
return 0
```

Nếu key chứa value được encode bằng JDK serialization, `GET` trả chuỗi byte của object; `ARGV[1]` là UTF-8 text sẽ không bằng dù giá trị logic ở Java trông tương đương. Cần thống nhất value format từ đầu.

### Ghi rõ serializer cho đối số và kết quả

`RedisTemplate` có overload:

```java
<T> T execute(
        RedisScript<T> script,
        RedisSerializer<?> argsSerializer,
        RedisSerializer<T> resultSerializer,
        List<K> keys,
        Object... args);
```

Ví dụ script trả String và chấp nhận đối số String:

```java
RedisSerializer<String> text = new StringRedisSerializer();

String result = redisTemplate.execute(
        stringResultScript,
        text,                   // serializer cho ARGV
        text,                   // serializer cho bulk-string result
        List.of("profile:42"),
        "expected-value"
);
```

Điểm cần phân biệt: overload trên cho phép chọn serializer cho **arguments và result**; tên khóa vẫn được serialize theo **key serializer của template**. Nếu đang dùng một RedisTemplate với key serializer không phù hợp, đừng kỳ vọng chỉ thay `argsSerializer` là sửa được đường dẫn đến key.

Với script trả integer `Long` hoặc boolean `Boolean`, Redis response được ánh xạ theo kiểu được `RedisScript.getResultType()` khai báo; result serializer chủ yếu có ý nghĩa với bulk-string và giá trị phức tạp.

## 10. Tính nguyên tử, lỗi script và retry

Redis chạy các lệnh của một script liên tục đối với những lệnh khác đang chờ trên cùng Redis instance/node, nên tổ hợp “đọc kiểm tra + ghi” trong một script tránh race giữa hai lời gọi client. Tuy nhiên:

- **Nguyên tử về không bị xen lệnh không đồng nghĩa rollback tự động.** Nếu script đã ghi một khóa rồi lệnh kế tiếp lỗi, Redis không tự hoàn tác tác dụng đã xảy ra.
- Script dài hoặc có vòng lặp lớn có thể chặn xử lý lệnh khác trên Redis; giữ logic ngắn, giới hạn thao tác và tránh `KEYS` quét toàn keyspace.
- Tất cả Redis key mà script truy cập phải đi qua `KEYS`; không tạo động key từ `ARGV` hoặc từ dữ liệu đọc trong Redis.
- Lua script có lỗi cú pháp hoặc gọi lệnh không hợp lệ sẽ báo lỗi cho client. Spring Data Redis thường chuyển lỗi đó thành exception theo nhóm `DataAccessException`; không chuyển mọi lỗi thành kết quả “false”.
- Nếu script đã thực thi trên Redis nhưng kết nối mất trước khi Java nhận response, ứng dụng có thể không biết chắc kết quả. Retry không có idempotency có thể nhân đôi tác động, nhất là script dùng `INCR`, chuyển số dư hoặc trừ kho.
- Với nhiều Redis node, tính nguyên tử chỉ áp dụng trên node/slot thực thi script, không tạo transaction phân tán giữa các slot.

Khi dùng script để cập nhật dữ liệu quan trọng, nên định nghĩa **operation ID/idempotency token** có kiểm soát để xử lý retry. Cách làm cụ thể phải xét thêm TTL của token và phạm vi khóa cùng hash slot trong Redis Cluster.

### `EVALSHA` và cache script

Khi có `RedisScript` được dùng lại, Spring Data Redis thường thử `EVALSHA` để tránh gửi lại toàn bộ source của script trên mọi lần gọi. Nếu Redis chưa có SHA đó, cơ chế thực thi có thể fallback sang `EVAL` để tải và chạy script.

Điều này là tối ưu truyền tải và caching, **không thay đổi hợp đồng `KEYS`, `ARGV` hoặc result type**. Script cache có thể trống sau restart, `SCRIPT FLUSH` hoặc khi gọi tới node cluster khác; ứng dụng không nên dựa vào việc SHA luôn có sẵn.

## 11. Thao tác script và Spring transaction

Một lời gọi `redisTemplate.execute(script, keys, args)` có thể xuất hiện trong service có `@Transactional`. Nếu chính RedisTemplate đang tham gia Spring-managed Redis transaction, lệnh có thể được queue trong `MULTI` cho tới `EXEC`, thay vì trả giá trị nghiệp vụ cuối cùng ngay tại điểm gọi.

Vì vậy:

- Nếu cần **giá trị trả về của script để quyết định nhánh logic ngay**, hãy biết rõ template/connection hiện có nằm trong transaction queue hay không.
- Một script nguyên tử được thực hiện trực tiếp trên Redis thường không cần bọc thêm bằng `MULTI/EXEC` chỉ để bảo đảm các lệnh **bên trong chính script** không bị xen ngang.
- Không coi script là một phần rollback nguyên tử với SQL chỉ vì đặt trong `@Transactional`. Khi hai tài nguyên cùng tham gia, cần thiết kế nhất quán và xử lý lỗi liên hệ thống riêng.
- Nếu người gọi thấy `null`, hãy xác định đó là nil reply của script, do serializer hay do lệnh còn ở queue; đừng suy đoán chỉ từ giá trị null.

## 12. Thực hành có kiểm soát: từ lệnh Redis CLI đến Java

Chỉ dùng Redis thử nghiệm hoặc namespace do nhóm sở hữu; không dùng key nghiệp vụ thật.

### Bài A — Một key, một argument, trả boolean

Tạo khóa:

```redis
SET demo:lua:lease token-123 EX 60
```

Chạy script:

```redis
EVAL "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('DEL',KEYS[1]) end return 0" 1 demo:lua:lease token-123
```

Kỳ vọng lần đầu trả `(integer) 1`, khóa bị xóa. Lặp lại script tương tự trả `0`. Trong Spring, dùng `RedisScript<Boolean>` và `List.of("demo:lua:lease")`, đối số `"token-123"` để nhận true/false tương ứng.

### Bài B — Hai key, một argument, trả số nguyên

Khởi tạo dữ liệu thử nghiệm:

```redis
SET stock:{demo1}:available 10
SET stock:{demo1}:reserved 2
```

Gọi script dự trữ ở mục 7 với:

```text
KEYS[1] = stock:{demo1}:available
KEYS[2] = stock:{demo1}:reserved
ARGV[1] = "3"
```

Khi thành công, script trả `1`; `available` trở thành 7 và `reserved` thành 5. Nếu yêu cầu vượt số lượng còn lại, script trả `0` và không đi vào nhánh ghi. Nếu dùng Redis Cluster, hai khóa cùng tag `{demo1}` nên cùng slot.

### Bài C — Nhận chuỗi hoặc danh sách

Lưu:

```redis
SET demo:lua:status READY
```

Dùng script `return redis.call('GET', KEYS[1])` với `StringRedisTemplate` và `RedisScript<String>`. Giá trị Java kỳ vọng là `"READY"`. Sau đó đổi script thành:

```lua
return { redis.call('EXISTS', KEYS[1]), redis.call('GET', KEYS[1]) }
```

Dùng `RedisScript<List>`, quan sát phần tử thứ nhất là integer (thường thành `Long`), phần tử thứ hai là String do result serializer. Đừng ép cả danh sách thành `List<String>`.

### Bài D — Nhầm thứ tự keys và args

Thử đổi `List.of(key1, key2)` thành `List.of(key2, key1)` trong môi trường thử nghiệm để hiểu tại sao hợp đồng thứ tự quan trọng. Không thực hiện bài này trên các counter thật vì script có lệnh ghi.

## 13. Lỗi thường gặp và hướng chẩn đoán

| Biểu hiện | Nguyên nhân cần xem xét | Cách xử lý |
| --- | --- | --- |
| `ERR wrong number of arguments` hoặc Lua truy cập `nil` | Thiếu `KEYS[n]`/`ARGV[n]`, nhầm số khóa hoặc thứ tự tham số. | Viết hợp đồng ở đầu script, kiểm tra `keys.size()` và danh sách `args`. |
| Script không thấy key dù Java vừa ghi | Key serializer không khớp, sai keyspace hoặc khác Redis database. | Kiểm tra bytes key, connection, namespace và serializer. |
| `CROSSSLOT Keys in request don't hash to the same slot` | Script dùng nhiều khóa ở các hash slot khác nhau. | Thiết kế hash tag chung cho đơn vị transaction hoặc đổi schema. |
| `ClassCastException` khi đọc result | `getResultType()` hoặc kiểu phần tử `List` khác giả định. | Chọn `Long`/`Boolean`/`String`/`List` đúng reply, xử lý element type. |
| Lỗi deserialize bulk string | Result serializer không phù hợp (ví dụ JDK serializer với Lua text). | Dùng `StringRedisSerializer`/serializer phù hợp; cấu hình tường minh. |
| Java nhận `null` | Script trả nil, lệnh đang queue hoặc lỗi xử lý reply. | Phân biệt đường thực thi, đọc lỗi/log và hợp đồng return. |
| `NOPERM` | User Redis thiếu quyền `EVAL`/`EVALSHA` hoặc lệnh/khóa bên trong script. | Cấp quyền tối thiểu đúng các lệnh và key cần thiết; kiểm tra ACL. |
| Redis tăng latency khi gọi script | Script làm việc quá nhiều hoặc vòng lặp không giới hạn. | Giới hạn số key, đơn giản hóa và đo ở môi trường thử nghiệm. |
| Retry làm tăng counter hai lần | Script đã chạy nhưng response bị mất, caller gọi lại. | Dùng operation ID và idempotency phù hợp. |
| Giá trị số lệch với số nguyên rất lớn | Lua `tonumber` hoặc phép toán số thực làm mất precision. | Giới hạn miền dữ liệu, dùng Redis integer commands và kiểm soát overflow. |

## 14. Nguyên tắc thiết kế script dễ bảo trì

1. Định nghĩa hợp đồng ngay đầu file Lua: `KEYS[1..n]`, `ARGV[1..m]`, tập mã kết quả và lỗi được phép xảy ra.
2. Dùng `KEYS` cho **mọi Redis key truy cập**; dùng `ARGV` cho **mọi giá trị tham số**. Không nội suy trực tiếp input không tin cậy vào source script.
3. Giới hạn và validate định danh từ Java trước khi tạo key; kiểm tra giá trị nghiệp vụ trong Lua trước khi ghi.
4. Chọn `StringRedisTemplate` khi dữ liệu lưu dưới dạng string; nếu dùng serializer khác, khai báo rõ cách mã hóa key/args/result.
5. Đảm bảo tất cả key của script nhiều khóa nằm cùng slot trên Redis Cluster.
6. Trả kết quả nhỏ, tường minh: `Long` cho số, `Boolean` với 1/0, `String` cho text, `List` cho tuple.
7. Thiết kế lỗi và rollback thực tế: Redis script không cung cấp rollback tự động cho những lệnh đã thành công trước khi script lỗi.
8. Dùng một `RedisScript<T>` bean tái sử dụng cho cùng một script, đặt Lua trong file resource khi nội dung lớn.
9. Với thao tác nhạy cảm, xây idempotency cho retry, metric cho thất bại và log chỉ chứa thông tin cần thiết (không ghi token bí mật).
10. Thử đúng serializer, Lua reply type, Redis Cluster slot và điều kiện lệnh trước khi đưa vào nghiệp vụ thật.

## 15. Câu hỏi tự kiểm tra

1. Khi gọi `redisTemplate.execute(script, List.of("a", "b"), "x", "y")`, `KEYS[2]` và `ARGV[1]` là gì?
2. Vì sao một tên Redis key nên được truyền qua `KEYS` thay vì `ARGV`, nhất là trong Redis Cluster?
3. Lua trả integer `1`/`0` thì nên khai báo `RedisScript<Boolean>` hay `RedisScript<Long>` trong từng trường hợp nào?
4. Vì sao script trả `{1, "OK"}` không nên được ép thẳng sang `List<String>`?
5. Khi Java dùng JDK serializer cho Redis value nhưng Lua so sánh với UTF-8 text, lỗi logic nào có thể xảy ra?
6. Script chạy nguyên tử đối với thao tác xen kẽ có tự rollback các lệnh đã thành công nếu lệnh cuối lỗi không?
7. Một request bị mất kết nối sau khi thực thi script `INCR` phải xử lý retry ra sao để tránh tăng hai lần?
8. Khi đang ở Spring-managed Redis transaction, vì sao `execute(...)` có thể không trả kết quả cuối cùng ngay?

**Ghi nhớ:** `RedisTemplate.execute(...)` là cầu nối giữa hợp đồng **`KEYS`/`ARGV`/`return` của Lua** và **`List<K>`/`Object... args`/`RedisScript<T>` của Java**. Tính nguyên tử của Redis Lua chỉ có ý nghĩa đầy đủ khi danh sách khóa đúng, tham số được serialize đúng, kiểu kết quả khớp và mọi ràng buộc về cluster, lỗi thực thi và retry đều được thiết kế rõ ràng.

## Tài liệu tham khảo

- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html): `RedisScript`, `DefaultRedisScript`, cách dùng `RedisTemplate.execute(...)` và kiểu kết quả.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): serializer, Redis operations và callback.
- [Redis — Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/): cách script thực thi và quy tắc `KEYS`/`ARGV`.
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/): cú pháp `numkeys` và key arguments.
- [Redis — Lua API](https://redis.io/docs/latest/develop/programmability/lua-api/): `redis.call`, `redis.pcall` và chuyển đổi kiểu Lua/Redis.
- [Redis — Redis Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slot, hash tag và giới hạn lệnh nhiều khóa.

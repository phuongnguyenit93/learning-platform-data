# Lỗi script và giới hạn rollback đối với ghi đã thực hiện

Khi dùng **Lua script trong Redis** qua Spring Data Redis, nhiều người chọn script vì có thể đọc, kiểm tra điều kiện và cập nhật nhiều khóa trong một lần thực thi ở phía server. Script chạy như một đơn vị xử lý mà lệnh của client khác không chen vào giữa. Đây là ưu điểm lớn đối với các thao tác như trừ tồn kho, giới hạn số lần sử dụng mã khuyến mãi hoặc thay đổi trạng thái.

Tuy nhiên, cần phân biệt hai khái niệm:

- **Tính nguyên tử về lịch thực thi (atomic execution/isolation):** trong lúc script đang chạy, Redis không thực thi xen một lệnh khác từ client khác trên cùng luồng thực thi Redis.
- **Rollback khi lỗi (failure atomicity):** nếu script đã ghi một phần dữ liệu rồi mới gặp lỗi, toàn bộ dữ liệu đã ghi trước đó có được hoàn tác hay không?

**Redis Lua script không có rollback tự động cho các lệnh ghi đã thực hiện.** Nếu script thực hiện thành công lệnh `INCR`, sau đó gọi một lệnh gây lỗi runtime, giá trị vừa tăng vẫn có thể được giữ lại. Điều này cũng đúng khi script phát lỗi chủ động sau khi đã thay đổi dữ liệu.

Bài học này giải thích vì sao, cách tái hiện sự cố, cách thiết kế script giảm nguy cơ cập nhật dở dang, và cách gọi script từ Spring Data Redis để xử lý kết quả và lỗi đúng ranh giới.

## 1. Lua script nguyên tử theo nghĩa nào?

Redis thực thi Lua script trên server. Trong khi script chạy, Redis xử lý các lệnh Redis được gọi từ script theo thứ tự; các yêu cầu khác không được chen giữa những lệnh đó trên cùng instance thực thi.

Ví dụ:

```text
Client A                               Redis                             Client B
   |                                     |                                  |
   | --- EVAL script ------------------> |                                  |
   |                                     |-- GET inventory:sku-1 ---------|
   |                                     |-- kiểm tra điều kiện           |
   |                                     |-- DECRBY inventory:sku-1 2    |
   |                                     |-- SADD reservations ...       |
   | <--- kết quả script --------------- |                                  |
   |                                     |-- sau đó mới phục vụ B ------>| 
```

Khả năng này giúp loại bỏ khoảng trống giữa thao tác `GET` và `DECRBY` do các lệnh client riêng lẻ tạo ra. Nếu nhiều client cùng gọi một script kiểm tra rồi trừ tồn kho, mỗi script nhìn thấy dữ liệu theo một thứ tự thực thi xác định tại Redis.

Nhưng **không có client khác chen vào** không đồng nghĩa **mọi thay đổi đã ghi sẽ biến mất khi script thất bại**.

Hãy hình dung script có ba bước:

```text
Bước 1: tăng bộ đếm                  -> THÀNH CÔNG (dữ liệu đã đổi)
Bước 2: sửa Hash                     -> LỖI vì khóa sai kiểu
Bước 3: ghi trạng thái hoàn tất       -> KHÔNG CHẠY

Kết quả:
- Bước 1 vẫn có hiệu lực.
- Bước 2 báo lỗi.
- Bước 3 chưa được thực hiện.
```

Vì thế, khi thiết kế script có nhiều lệnh ghi, phải xem xét **mọi điểm lỗi có thể xảy ra trước và sau lần ghi đầu tiên**.

## 2. Ví dụ tái hiện: lỗi sau khi INCR không hoàn tác INCR

Có thể quan sát trực tiếp bằng Redis CLI trong môi trường thử nghiệm. Sử dụng tên khóa riêng để không ảnh hưởng dữ liệu khác:

```redis
SET demo:script:counter 0
SET demo:script:invalid-value "not-a-number"
```

Gọi script:

```redis
EVAL "redis.call('INCR', 'demo:script:counter'); return redis.call('INCR', 'demo:script:invalid-value')" 0
```

Trình tự server xử lý:

1. `INCR demo:script:counter` thành công, bộ đếm chuyển từ `0` sang `1`.
2. `INCR demo:script:invalid-value` cố tăng một string không biểu diễn số nguyên hợp lệ.
3. Redis trả lỗi từ lệnh thứ hai, khiến `redis.call(...)` phát lỗi Lua và script dừng.
4. Redis **không tự trừ lại** giá trị bộ đếm đã tăng ở bước 1.

Kiểm tra:

```redis
GET demo:script:counter
GET demo:script:invalid-value
```

Kết quả khái niệm:

```text
GET demo:script:counter
"1"

GET demo:script:invalid-value
"not-a-number"
```

Đây là ví dụ cốt lõi để phân biệt **nguyên tử về thứ tự thực thi** với **rollback khi lỗi**.

### Lỗi là do Lua hay Redis command?

Ở ví dụ trên, vấn đề bắt nguồn từ Redis command `INCR` nhận dữ liệu sai kiểu số. Trong script, `redis.call(...)` biến lỗi command thành lỗi Lua, khiến script dừng.

Ngoài lỗi Redis command, script còn có thể thất bại vì lỗi Lua khi đang chạy:

```lua
redis.call('INCR', KEYS[1])
local value = nil
return value.missingField
```

Nếu lệnh `INCR` đã thành công, lỗi truy cập field trên `nil` ở phần sau **không tạo rollback**. Vì vậy, chỉ kiểm tra kiểu của Redis key là chưa đủ; còn phải tránh các phép tính, chuyển đổi và thao tác Lua có thể lỗi sau khi ghi.

## 3. Những loại lỗi và thời điểm phát sinh

Không phải lỗi nào cũng có tác động giống nhau. Cần phân loại theo **thời điểm script đã bắt đầu thực hiện ghi hay chưa**.

| Tình huống | Ví dụ | Hệ quả lên dữ liệu |
|---|---|---|
| Script không được chấp nhận trước khi thực thi | Cú pháp Lua sai, số lượng khóa không hợp lệ được phát hiện trước | Chưa có lệnh ghi của script được thực hiện |
| Script chủ động từ chối trước ghi | `return redis.error_reply("INVALID_AMOUNT")` trước mọi mutation | Không có thay đổi do script này |
| Lệnh đọc/kiểm tra lỗi trước ghi | `GET` trên khóa sai Redis type trước bất kỳ mutation | Không có thay đổi do script này |
| Redis command lỗi sau một lần ghi | `INCR` thành công rồi `HSET` sai kiểu | Các ghi thành công trước lỗi vẫn có thể tồn tại |
| Lỗi tính toán Lua sau ghi | Gọi hàm nil, truy cập dữ liệu không hợp lệ | Không tự hoàn tác ghi trước đó |
| Script tự trả lỗi sau ghi | `return redis.error_reply("REJECTED")` sau `SET` | Lệnh `SET` trước đó vẫn có tác dụng |
| `redis.pcall` bắt lỗi | Lỗi được biến thành giá trị, script tiếp tục | Không rollback; script có thể tiếp tục ghi thêm |
| Client timeout/mất kết nối khi EVAL chạy | Client không nhận được reply | Có thể không biết chắc script đã chạy đến đâu hoặc đã hoàn tất |
| Redis từ chối `EVALSHA` do thiếu script | Phản hồi `NOSCRIPT` | Script đó chưa chạy qua lời gọi `EVALSHA` bị từ chối |

Lỗi trước khi script được chạy hoặc trước lần ghi đầu tiên thường đơn giản hơn về mặt phục hồi. Lỗi sau ghi phải được xem như một **trạng thái nghiệp vụ cần kiểm tra**.

Không nên xử lý mọi exception bằng một lệnh “retry toàn bộ script” vô điều kiện. Nếu một lần thực thi trước đã tạo tác dụng phụ, retry có thể lặp lại tác dụng đó.

## 4. redis.call, redis.pcall và redis.error_reply

Lua trong Redis có các cơ chế phản hồi khác nhau cần hiểu rõ.

### 4.1. redis.call: lỗi command thường dừng script

```lua
local newCount = redis.call('INCR', KEYS[1])
redis.call('INCR', KEYS[2])  -- lỗi nếu giá trị không phải số
return newCount
```

Khi lệnh thứ hai lỗi, `redis.call` phát lỗi và script dừng. **Lệnh tăng `KEYS[1]` không được hoàn tác**.

### 4.2. redis.pcall: bắt lỗi Redis command để xử lý

```lua
local first = redis.call('INCR', KEYS[1])
local second = redis.pcall('INCR', KEYS[2])

if type(second) == 'table' and second.err then
    return redis.error_reply('SECOND_INCREMENT_FAILED')
end

return first
```

`redis.pcall` không tự vứt lỗi ra khỏi script theo cách `redis.call` thường làm; nó trả một giá trị lỗi để code có thể kiểm tra. Nhưng điều này **không phải một transaction savepoint**. `KEYS[1]` vẫn đã tăng.

Có thể dùng `redis.pcall` để áp dụng chính sách xử lý lỗi được thiết kế rõ ràng, chẳng hạn ghi một trạng thái cảnh báo hoặc trả mã lỗi. Không nên dùng nó để “giả vờ” rằng các ghi cũ chưa từng xảy ra.

### 4.3. redis.error_reply: trả lỗi chủ động

```lua
local quantity = tonumber(ARGV[1])
if not quantity or quantity <= 0 then
    return redis.error_reply('INVALID_QUANTITY')
end

redis.call('DECRBY', KEYS[1], quantity)
return 1
```

Ở đây, lỗi được trả **trước khi thay đổi dữ liệu**, nên phù hợp để chặn input không hợp lệ. Ngược lại:

```lua
redis.call('DECRBY', KEYS[1], 1)
return redis.error_reply('FAILED_AFTER_WRITE')
```

sẽ trả phản hồi lỗi **sau khi đã trừ dữ liệu**. Một caller chỉ nhìn thấy exception mà suy đoán “không có gì được ghi” sẽ xử lý sai.

### 4.4. Trả mã trạng thái và trả lỗi khác nhau thế nào?

Có thể thiết kế script trả số:

```text
 1 = thành công, đã cập nhật
 0 = điều kiện nghiệp vụ không cho phép cập nhật, không ghi
 2 = yêu cầu đã xử lý trước đó, không ghi lặp
```

hoặc trả lỗi Redis bằng `redis.error_reply` cho input/kiểu dữ liệu không hợp lệ. Việc chọn mã trạng thái hay error reply là quyết định API của script, nhưng phải nhất quán: **mã lỗi không thể được hiểu là bảo đảm rollback nếu script đã có ghi trước đó**.

## 5. Nguyên tắc thiết kế: kiểm tra toàn bộ điều kiện trước khi ghi

Cách giảm rủi ro hữu ích nhất là chia script thành hai pha:

1. **Pha kiểm tra (read/validate):** kiểm tra input, key type, định dạng dữ liệu, số dư/tồn kho, trạng thái nghiệp vụ và những điều kiện có thể kiểm tra trước.
2. **Pha mutation:** chỉ thực hiện các lệnh ghi khi toàn bộ kiểm tra đã qua, với số lượng bước ghi càng ít càng tốt.

```text
                  Nhận KEYS / ARGV
                         |
                         v
                  Kiểm tra input
                         |
                         v
              Kiểm tra key type / value
                         |
                         v
             Kiểm tra quy tắc nghiệp vụ
                         |
                +--------+--------+
                |                 |
              Không hợp lệ       Hợp lệ
                |                 |
                v                 v
          Trả lỗi/mã 0       Thực hiện mutation
          (chưa ghi)              |
                                  v
                              Trả kết quả
```

Nhờ Redis thực thi script liên tục trên server, một client khác không thể thay đổi giá trị giữa các bước kiểm tra và bước ghi của cùng script. Đây là điểm mạnh giúp kiểm tra trước rồi ghi trong một script thường phù hợp.

**Giới hạn:** Kiểm tra trước giảm khả năng lỗi dự đoán được, nhưng không tạo rollback. Những lỗi khó dự báo như thiếu bộ nhớ, cạn tài nguyên, một cấu hình Redis không cho phép lệnh, lỗi driver/topology hoặc sai giả định trong code vẫn có thể xảy ra. Với yêu cầu nghiệp vụ rất nghiêm ngặt, không nên xem “đã prevalidate” là một chứng minh giao dịch all-or-nothing.

## 6. Ví dụ script chưa tốt: trừ hàng trước, kiểm tra trạng thái sau

Giả sử hệ thống giữ hàng cho đơn:

```text
inventory:sku-1:available = "10"
order:1001:state = "NEW"
```

Một script thiếu an toàn:

```lua
-- KEYS[1]: inventory key
-- KEYS[2]: order state key
-- ARGV[1]: quantity

redis.call('DECRBY', KEYS[1], ARGV[1])

local state = redis.call('GET', KEYS[2])
if state ~= 'NEW' then
    return redis.error_reply('ORDER_NOT_NEW')
end

redis.call('SET', KEYS[2], 'RESERVED')
return 1
```

Điểm nguy hiểm: script trừ kho **trước** khi kiểm tra trạng thái đơn. Nếu trạng thái là `CANCELLED`, nó trả lỗi nhưng kho vẫn bị trừ. Nếu `GET` gặp sai Redis type, lệnh trừ kho vẫn đã chạy.

Đổi thứ tự xử lý:

```lua
local state = redis.call('GET', KEYS[2])
if state ~= 'NEW' then
    return 0
end

local rawStock = redis.call('GET', KEYS[1])
local stock = tonumber(rawStock)
local quantity = tonumber(ARGV[1])

if not stock or not quantity
        or quantity <= 0
        or quantity ~= math.floor(quantity)
        or stock < quantity then
    return 0
end

redis.call('DECRBY', KEYS[1], ARGV[1])
redis.call('SET', KEYS[2], 'RESERVED')
return 1
```

Thiết kế sau tránh việc trừ tồn kho trước khi phát hiện trạng thái không phù hợp. Tuy nhiên, nó vẫn có **hai lệnh ghi**. Nếu `SET` ở cuối lỗi sau `DECRBY`, không có rollback tự động. Với dữ liệu kiểu không ổn định, cần kiểm tra **kiểu của cả hai khóa**, định dạng số và các điều kiện trước mutation.

Ngoài ra, `tonumber` của Lua dùng biểu diễn số của Lua, cần thận trọng với số nguyên rất lớn hoặc giá trị thập phân. Trong bài toán tiền, số dư và tồn kho phải có giới hạn miền giá trị rõ ràng; các điều kiện cần dùng kiểu số nguyên đủ chính xác cho nghiệp vụ.

## 7. Ví dụ script tốt hơn: đặt kiểm tra trước tất cả mutation

Thiết kế sau mô phỏng một lần giữ tồn kho có mã yêu cầu. Nó dùng:

- `KEYS[1]`: khóa số lượng tồn kho, dạng Redis string chứa số nguyên không âm.
- `KEYS[2]`: khóa Redis Set chứa những `requestId` đã xử lý.
- `ARGV[1]`: số lượng cần giữ.
- `ARGV[2]`: mã yêu cầu duy nhất, do caller quản lý.

### Lua script

```lua
-- KEYS[1] = inventory:{sku-1}:available
-- KEYS[2] = inventory:{sku-1}:processed
-- ARGV[1] = requested quantity
-- ARGV[2] = unique request id

local inventoryKey = KEYS[1]
local processedKey = KEYS[2]
local quantityRaw = ARGV[1]
local requestId = ARGV[2]

local quantity = tonumber(quantityRaw)
if not quantity
        or quantity <= 0
        or quantity > 1000000
        or quantity ~= math.floor(quantity)
        or not requestId
        or requestId == '' then
    return redis.error_reply('INVALID_INPUT')
end

-- Các kiểm tra về Redis key type phải xảy ra trước mutation.
local inventoryType = redis.call('TYPE', inventoryKey).ok
local processedType = redis.call('TYPE', processedKey).ok

if inventoryType ~= 'string' then
    return redis.error_reply('INVALID_INVENTORY_TYPE')
end

if processedType ~= 'set' and processedType ~= 'none' then
    return redis.error_reply('INVALID_PROCESSED_TYPE')
end

local inventoryRaw = redis.call('GET', inventoryKey)
local available = tonumber(inventoryRaw)

-- Giới hạn giá trị ở phạm vi số nguyên biểu diễn chính xác
-- theo cơ chế số của Lua; ứng dụng phải đồng bộ giới hạn này.
if not available
        or available < 0
        or available > 9007199254740991
        or available ~= math.floor(available) then
    return redis.error_reply('INVALID_INVENTORY_VALUE')
end

if processedType == 'set'
        and redis.call('SISMEMBER', processedKey, requestId) == 1 then
    return 2 -- Request đã được xử lý, không trừ kho lần nữa.
end

if available < quantity then
    return 0 -- Không đủ hàng, không ghi.
end

-- Sau điểm này mới có tác dụng ghi.
redis.call('DECRBY', inventoryKey, quantityRaw)
redis.call('SADD', processedKey, requestId)
return 1
```

Hợp đồng kết quả:

| Kết quả | Ý nghĩa | Tác động kỳ vọng |
|---:|---|---|
| `1` | Đã giữ hàng | Tồn kho giảm, request ID được đánh dấu |
| `0` | Không đủ hàng | Không thay đổi dữ liệu |
| `2` | Request ID đã xử lý | Không trừ kho lần nữa |
| Lỗi `INVALID_*` | Input hoặc trạng thái khóa không hợp lệ | Các kiểm tra phát hiện lỗi trước phần ghi |
| Lỗi bất thường sau khi mutation bắt đầu | Không thể kết luận hoàn toàn từ error reply | Phải kiểm tra trạng thái, không retry mù |

**Vì sao ví dụ tốt hơn?** Script xác thực input, khóa và dữ liệu, kiểm tra trùng request, kiểm tra tồn kho rồi mới ghi. `SADD` chỉ được gọi sau khi xác nhận key đích thuộc kiểu `set` hoặc chưa tồn tại; điều này loại bỏ một lỗi `WRONGTYPE` dự đoán được.

**Vì sao vẫn không phải rollback tuyệt đối?** Sau `DECRBY`, `SADD` vẫn có thể gặp lỗi không được kiểm tra trước, ví dụ một tình huống tài nguyên hoặc lỗi hệ thống. Khi đó, thay đổi tồn kho trước đó không tự được khôi phục. Cần theo dõi và đối soát đối với dữ liệu đòi hỏi tính chính xác cao.

Một chi tiết nữa: deduplication chỉ có tác dụng khi `processedKey` được giữ đủ lâu so với cửa sổ retry và toàn bộ caller dùng **requestId ổn định**. Nếu set bị xóa hoặc hết hạn trước khi request cũ được gửi lại, khả năng chống lặp sẽ mất.

### Lưu ý Redis Cluster

Hai khóa dùng cùng hash tag `{sku-1}`:

```text
inventory:{sku-1}:available
inventory:{sku-1}:processed
```

Trong Redis Cluster, script sử dụng nhiều khóa phải tuân thủ ràng buộc hash slot; hai khóa trên cùng tag sẽ nằm cùng slot. Không nhúng tên khóa bổ sung ẩn bên trong script rồi tự giả định chúng vẫn nằm đúng slot. Khai báo các khóa được sử dụng qua `KEYS` theo quy tắc Redis, còn dữ liệu và tham số qua `ARGV`.

## 8. Gọi script từ Spring Data Redis

Spring Data Redis cung cấp `RedisScript<T>` và API `RedisTemplate.execute(...)`. Lớp `DefaultRedisScript<T>` cho phép khai báo Lua source và kiểu kết quả. Spring Data Redis thường dùng cơ chế script cache để gọi `EVALSHA` khi phù hợp và xử lý tình huống script chưa được nạp.

### 8.1. Khai báo script

Trong dự án Spring Boot, có thể lưu Lua của phần trước vào tài nguyên:

```text
src/main/resources/redis/reserve-inventory.lua
```

Ví dụ cấu hình:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class RedisScriptConfiguration {

    @Bean
    public RedisScript<Long> reserveInventoryScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setLocation(
                new ClassPathResource("redis/reserve-inventory.lua"));
        script.setResultType(Long.class);
        return script;
    }
}
```

File `reserve-inventory.lua` chứa toàn bộ Lua script ở mục 7. Tách Lua thành resource giúp dễ đọc, review và version hóa hơn khi script nhiều dòng. Bean `RedisScript` có thể được tái sử dụng thay vì khởi tạo/calculate SHA1 liên tục trong mỗi request.

### 8.2. Service xử lý mã kết quả

```java
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class InventoryReservationService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> reserveInventoryScript;

    public InventoryReservationService(
            StringRedisTemplate redis,
            RedisScript<Long> reserveInventoryScript) {
        this.redis = redis;
        this.reserveInventoryScript = reserveInventoryScript;
    }

    public ReservationOutcome reserve(
            String sku,
            long quantity,
            String requestId) {

        if (quantity <= 0 || quantity > 1_000_000L) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("Request ID is required");
        }

        String stockKey = "inventory:{" + sku + "}:available";
        String dedupKey = "inventory:{" + sku + "}:processed";

        Long result = redis.execute(
                reserveInventoryScript,
                List.of(stockKey, dedupKey),
                Long.toString(quantity),
                requestId);

        if (result == null) {
            throw new IllegalStateException(
                    "Redis script did not return an outcome");
        }

        return switch (result.intValue()) {
            case 1 -> ReservationOutcome.RESERVED;
            case 0 -> ReservationOutcome.INSUFFICIENT_STOCK;
            case 2 -> ReservationOutcome.ALREADY_PROCESSED;
            default -> throw new IllegalStateException(
                    "Unexpected Lua result: " + result);
        };
    }

    public enum ReservationOutcome {
        RESERVED,
        INSUFFICIENT_STOCK,
        ALREADY_PROCESSED
    }
}
```

`StringRedisTemplate` có string serializers phù hợp cho key, `ARGV` và số lượng ví dụ. `DefaultRedisScript<Long>` khai báo `Long.class` vì Lua trả số nguyên `0`, `1` hoặc `2`.

**Quan trọng:** Nếu Redis trả lỗi và Spring Data Redis ném exception, exception đó **không phải một bằng chứng rằng script chưa ghi gì**. Đường catch phải phân biệt lỗi đầu vào đã được script phát trước mutation với lỗi runtime/timeout/connection không xác định kết quả. Đừng tự động xử lý mọi `RedisSystemException` hoặc `DataAccessException` thành `INSUFFICIENT_STOCK`.

### 8.3. Vì sao không nên gọi script theo chuỗi thủ công mỗi request?

Có thể dùng `redisTemplate.execute(script, keys, args)` để tái sử dụng instance của `RedisScript`. Việc nạp và chạy script theo hash giúp giảm gửi lại nội dung Lua dài trong một số trường hợp. Khi Redis khởi động lại hoặc cache script bị xóa, `EVALSHA` có thể gặp `NOSCRIPT` và cơ chế script executor phù hợp sẽ nạp/chạy lại theo đường fallback.

`NOSCRIPT` là lỗi về **sự hiện diện của mã script trong cache**, khác với lỗi runtime sau khi script bắt đầu chạy. Đừng thiết kế logic nghiệp vụ suy luận mọi script exception đều thuộc một loại.

## 9. Khi có lỗi, trạng thái commit có thể không xác định

Xét một yêu cầu trừ 3 đơn vị tồn kho:

```text
Client                         Redis
   |                              |
   | --- EVAL script -----------> |
   |                              |-- DECRBY inventory 3
   |                              |-- SADD processed request-42
   | <--- kết nối bị gián đoạn --- X
   |
   v
Client không nhận được kết quả
```

Từ góc nhìn client, cùng một lỗi kết nối có thể xảy ra trong nhiều tình huống:

1. Lệnh chưa tới Redis, script chưa thực thi.
2. Redis đã thực thi xong, nhưng phản hồi không tới client.
3. Redis đã thực hiện một vài ghi, rồi script gặp lỗi runtime hoặc điều kiện vận hành khác.
4. Có failover/khôi phục khiến trạng thái thấy ở node mới khác với giả định ban đầu.

Vì vậy, **timeout không đồng nghĩa rollback**. Đặc biệt, thời gian chờ phía client hết không có nghĩa Redis đã dừng script.

Đối với yêu cầu có tác dụng phụ, ứng dụng nên có **mã request ổn định**, cách truy vấn trạng thái sau lỗi, chính sách retry theo mã và cơ chế đối soát. Ví dụ, sau lỗi không rõ kết quả, một retry với cùng `requestId` có thể trả `ALREADY_PROCESSED` nếu script trước đã ghi cả kết quả và marker. Nhưng nếu bản ghi tồn kho đã trừ mà marker chưa được ghi do lỗi sau mutation, retry đơn thuần vẫn có nguy cơ trừ lần nữa. Đây là giới hạn phải xét khi thiết kế cơ chế idempotency nhiều khóa.

### Phân biệt lỗi chắc chắn và lỗi không xác định

| Phản hồi | Có thể kết luận gì? | Hướng xử lý |
|---|---|---|
| Script trả `0` trước mutation | Điều kiện không đạt, chưa ghi | Trả kết quả nghiệp vụ |
| Script trả `2` khi dedup đã tồn tại | Yêu cầu đã được ghi nhận | Không trừ lặp |
| Script chủ động báo `INVALID_INPUT` trước mutation | Input không phù hợp, chưa ghi theo nhánh đó | Sửa request hoặc dữ liệu |
| `WRONGTYPE` ở lệnh sau một lệnh ghi | Có thể đã ghi một phần | Đối soát trạng thái thực |
| Timeout/connection reset | Không chắc script đã chạy hay chưa | Đọc trạng thái/idempotency, không retry mù |
| `NOSCRIPT` được xử lý trước chạy script | Script chưa nằm trong cache | Nạp/chạy lại theo cơ chế executor |
| Client nhận `1` | Script trả mã thành công theo logic | Tiếp tục theo hợp đồng, vẫn xét persistence/failover nếu cần độ bền |

Không nên bao mọi exception thành “giao dịch thất bại nên dữ liệu không đổi”.

## 10. Có thể viết lệnh bù để tự rollback không?

Có thể nghĩ tới:

```lua
redis.call('DECRBY', KEYS[1], 3)

local result = redis.pcall('SADD', KEYS[2], ARGV[1])
if type(result) == 'table' and result.err then
    redis.call('INCRBY', KEYS[1], 3)
    return redis.error_reply('RESERVATION_FAILED')
end

return 1
```

Đây là **compensation thủ công**, không phải rollback được Redis bảo đảm. Nó chỉ an toàn nếu mọi giả định đều đúng:

- Lệnh đầu đã chắc chắn thay đổi đúng số lượng mong đợi.
- Lệnh bù không thể thất bại do kiểu dữ liệu, quyền truy cập hoặc tài nguyên.
- Không có tác dụng phụ bên ngoài Redis cần hoàn tác.
- Không có lỗi Lua phát sinh trước khi đến phần bù.
- Không có sai lệch do thay đổi giá trị, TTL hoặc loại dữ liệu.

Những giả định này không luôn đứng vững trong production. Nếu lệnh bù tự lỗi, script có thể kết thúc ở trạng thái dở dang khác. Cơ chế bù chỉ nên được dùng khi đã định nghĩa **bất biến, hướng phục hồi và cách đối soát** rõ ràng.

Với những thao tác cần tính nhất quán cao, hãy giảm số mutation hoặc thiết kế representation sao cho **một Redis command nguyên tử** thực hiện toàn bộ thay đổi cần thiết. Nếu không thể, cân nhắc đưa quyết định chính vào một hệ thống giao dịch hỗ trợ ràng buộc cần thiết và dùng Redis cho cache/projection.

## 11. Tối giản tác dụng phụ và giới hạn miền dữ liệu

Không phải yêu cầu nào cũng cần script có nhiều lệnh ghi. Ví dụ một khóa tồn kho chỉ cần giảm khi đủ số lượng:

```lua
-- KEYS[1]: inventory key
-- ARGV[1]: quantity

local raw = redis.call('GET', KEYS[1])
local available = tonumber(raw)
local requested = tonumber(ARGV[1])

if not available
        or not requested
        or requested <= 0
        or requested > 1000000
        or requested ~= math.floor(requested)
        or available < requested then
    return 0
end

redis.call('DECRBY', KEYS[1], ARGV[1])
return 1
```

Script này có **một mutation**, nên tránh được rủi ro “ghi A thành công rồi ghi B lỗi” trong cùng script. Tuy vậy, caller vẫn phải xử lý timeout/không nhận phản hồi và tính đúng của số nguyên. Nếu chỉ cần một lệnh vốn đã atomic như `INCRBY`, `HINCRBY` hoặc `SET key value NX PX ttl`, không nhất thiết phải dùng Lua.

Đặc biệt với tính toán số trong Lua Redis, cần:

- Kiểm tra `tonumber(...)` không trả `nil`.
- Kiểm tra tính nguyên, miền giá trị và dấu của số lượng.
- Cẩn thận với giới hạn chính xác của biểu diễn số Lua; không dùng số thực để mô phỏng tùy tiện số tiền hoặc định danh nguyên 64-bit.
- Không dùng phép chia hoặc ép kiểu có thể tạo giá trị ngoài miền đã định.
- Đảm bảo Redis command nhận định dạng số mà nó hỗ trợ (chẳng hạn `DECRBY` yêu cầu số nguyên), kể cả khi Lua có thể biểu diễn thêm kiểu khác.

**Đưa càng nhiều validation lên trước mutation càng tốt**, đồng thời giữ các bất biến miền dữ liệu ở nơi có thể kiểm soát và đối soát.

## 12. Redis Lua và giao dịch MULTI/EXEC: cùng thiếu rollback kiểu SQL

Redis transaction bằng `MULTI`/`EXEC` cũng có đặc điểm quan trọng: nếu lệnh lỗi trong lúc `EXEC` thực thi, Redis không tự đảo ngược các lệnh đã thành công trong transaction. Script Lua và transaction Redis đều cho phép gom thao tác theo ranh giới thực thi, nhưng **không phải transaction SQL có rollback khi runtime error**.

| Tiêu chí | Lua script (`EVAL`/`EVALSHA`) | `MULTI`/`EXEC` |
|---|---|---|
| Kiểm tra điều kiện và ghi trong một ranh giới server | Có, script thực hiện logic điều kiện | Chỉ với lệnh queue; cần `WATCH` cho đọc rồi ghi ở client |
| Lệnh client khác chen vào giữa khi nhóm đang thực thi | Không | Không khi EXEC đang chạy |
| Đọc kết quả lệnh trước để quyết định lệnh sau | Có trong Lua | Không thể dựa vào kết quả lệnh đã queue trước EXEC |
| Runtime error sau mutation | Không rollback mutation cũ | Không rollback những lệnh đã thành công |
| Xử lý lỗi trước mutation | Kiểm tra input và state trong Lua | Kiểm tra phía client/`WATCH` trước EXEC khi phù hợp |
| Trường hợp nổi bật | Check-and-update, rate limit, reservation | Nhóm lệnh đã biết trước, optimistic concurrency với WATCH |

Không nên đặt kỳ vọng ACID hoàn chỉnh từ chữ “atomic” trong tài liệu Lua hoặc Redis transaction. Cần kiểm tra cụ thể hệ thống bảo đảm những thuộc tính nào: thứ tự xử lý, tính nhất quán, bền vững, khả năng rollback và phục hồi sau lỗi.

## 13. Giới hạn khi script chạy lâu hoặc bị ngắt

### 13.1. Time limit không có nghĩa Redis tự rollback

Redis có cơ chế phát hiện script chạy quá lâu và có thể tạm thời trả lỗi `BUSY` cho những lệnh khác trong khi script vẫn chiếm thời gian thực thi. Cấu hình ngưỡng thời gian của script **không phải một giới hạn làm script tự dừng kèm rollback**.

Không viết vòng lặp vô hạn, quét toàn bộ dữ liệu lớn hoặc xử lý hàng triệu phần tử trong một Lua script. Script dài có thể chặn các client khác và gây đỉnh độ trễ toàn Redis instance.

### 13.2. SCRIPT KILL có giới hạn

Redis có lệnh `SCRIPT KILL` để yêu cầu dừng script khi có thể dừng an toàn mà không phá dữ liệu đã ghi. Nếu script đã thực hiện thao tác ghi, Redis không thể xem việc kill như rollback và có thể từ chối hủy script theo cơ chế này.

Không sử dụng thao tác tắt server đột ngột như một chiến lược xử lý script lỗi: đó là sự cố vận hành, không phải cơ chế giao dịch.

### 13.3. Script cache và thay đổi phiên bản

`EVALSHA` chạy script dựa trên SHA1. Script không có trong cache có thể tạo `NOSCRIPT`; lỗi này khác hẳn lỗi runtime sau mutation. Trong quá trình failover hoặc restart, script cache có thể không còn như client kỳ vọng, nên executor cần cơ chế nạp lại script.

Cần version hóa script cùng hợp đồng dữ liệu. Nếu một ứng dụng gọi bản Lua cũ còn ứng dụng khác gọi bản mới trên cùng keyspace, chúng có thể áp dụng quy tắc và dữ liệu khác nhau dù mỗi script đều chạy không bị xen ngang.

## 14. Redis Cluster, nhiều key và hành vi lỗi

Trên Redis Cluster, Lua script truy cập nhiều khóa phải tuân thủ các quy định về khai báo khóa và hash slot. Nếu script cần cập nhật hai khóa thuộc hai slot không tương thích, lệnh có thể bị từ chối. Điều này thường dễ tránh nếu biết trước keyspace và dùng hash tag hợp lý:

```text
order:{1001}:state
order:{1001}:reserved-items
order:{1001}:dedup-requests
```

Các khóa mang cùng phần `{1001}` sẽ cùng slot. Không nên dùng một hash tag toàn cục cho mọi đơn hàng vì có thể dồn tải vào một slot.

Nếu script gây lỗi do vi phạm giới hạn cluster hoặc Redis command lỗi sau khi mutation đã bắt đầu, cần đánh giá trạng thái thực chứ không dựa vào giả định “cluster từ chối thì chắc chắn chưa ghi”. Những điều kiện được kiểm tra trước khi chạy script và những lỗi phát sinh trong quá trình thực thi có thời điểm khác nhau.

Script chạy trên node phụ trách những khóa mục tiêu không có nghĩa rằng việc replication và failover tạo thành một transaction bền vững xuyên toàn cluster. **Nguyên tử trong lúc thực thi script và độ bền sau sự cố là hai thuộc tính khác nhau**.

## 15. Tình huống đầy đủ: phát mã giảm giá một lần

Một dịch vụ cần đảm bảo mỗi mã yêu cầu chỉ sử dụng một coupon một lần.

Dữ liệu:

```text
coupon:{CAMP-1}:remaining = "100"
coupon:{CAMP-1}:used-requests = Redis Set
```

Mong muốn:

1. Nếu request đã được xử lý, không dùng coupon thêm lần nữa.
2. Nếu hết lượt, không thay đổi dữ liệu.
3. Nếu còn lượt, giảm bộ đếm và ghi nhận request.
4. Khi kết nối mất, có thể xác định trạng thái càng rõ càng tốt.

### Script dễ lỗi

```lua
redis.call('DECRBY', KEYS[1], 1)

if redis.call('SISMEMBER', KEYS[2], ARGV[1]) == 1 then
    return redis.error_reply('DUPLICATE_REQUEST')
end

redis.call('SADD', KEYS[2], ARGV[1])
return 1
```

Nếu request đã có trong Set, script vẫn giảm `remaining` rồi báo lỗi. Với sai kiểu dữ liệu của Set, nó cũng có thể dừng sau khi đã giảm bộ đếm.

### Thiết kế kiểm tra trước ghi

```text
1. Validate request ID.
2. Validate kiểu dữ liệu của cả hai khóa.
3. Kiểm tra request ID đã dùng hay chưa.
4. Kiểm tra số lượt còn lại và giá trị số hợp lệ.
5. Nếu không đủ điều kiện -> trả mã rõ ràng, chưa ghi.
6. Nếu hợp lệ -> giảm bộ đếm và đánh dấu request.
7. Trả mã thành công.
```

Quy trình này là **một cải thiện thiết kế**, nhưng chưa tạo rollback cho mọi lỗi ở bước 6. Nếu yêu cầu “không bao giờ trừ lượt mà thiếu marker” là bất biến bắt buộc, cần xây mô hình dữ liệu và cơ chế phục hồi phù hợp: ví dụ đặt quyền quyết định vào nguồn giao dịch có ràng buộc tương ứng, bổ sung event log/idempotency bền, hoặc thiết kế lại để giảm số mutation cần phải cùng thành công.

### Xử lý timeout ở phía Spring

Giả sử Redis đã giảm bộ đếm và đánh dấu request nhưng phản hồi bị mất. Nếu client tạo **requestId mới** cho lần retry, script sẽ nhìn thấy như một yêu cầu mới và giảm thêm. Nếu client giữ **cùng requestId**, script có khả năng phát hiện đã xử lý qua Set.

Tuy nhiên, một marker dedup không khắc phục được trường hợp script đã giảm bộ đếm nhưng lỗi trước khi thêm marker. Vì vậy, với workflow quan trọng, cần có log/audit hoặc cơ chế đối soát khác để phát hiện và sửa tình huống này theo quy tắc nghiệp vụ.

## 16. Ghi log, đo lường và xử lý sự cố

Khi một script lỗi trong production, câu hỏi quan trọng không chỉ là “script nào đã lỗi?” mà còn là “**đã có những mutation nào xảy ra trước lỗi?**”.

Những thông tin nên quan sát ở tầng ứng dụng:

| Thông tin | Mục đích |
|---|---|
| Tên/version của script | Biết chính xác logic nào đang chạy |
| Request ID/idempotency key | Liên kết retry và sự kiện trùng |
| Outcome `success`, `business-rejected`, `script-error`, `unknown` | Không gom mọi trường hợp vào cùng một nhãn |
| Độ trễ p50/p95/p99 của lời gọi script | Phát hiện script quá lâu hoặc ảnh hưởng tải |
| Số lần retry và tỷ lệ kết quả không xác định | Phát hiện nguy cơ thao tác lặp |
| Số lần đối soát lệch dữ liệu | Biết liệu lỗi script đã tạo trạng thái dở dang hay không |
| Thay đổi schema/key type | Tìm nguyên nhân `WRONGTYPE` và dữ liệu không tương thích |

Redis cung cấp một số lệnh quan sát tổng thể:

```bash
redis-cli INFO commandstats
redis-cli INFO stats
redis-cli SLOWLOG GET 10
```

`INFO commandstats` có thể cho thấy tần suất gọi `EVAL`/`EVALSHA` ở phạm vi instance. `SLOWLOG` tập trung vào lệnh chạy chậm phía Redis, không bao gồm toàn bộ thời gian mạng hoặc thời gian ứng dụng chờ connection. Không dùng `MONITOR` đại trà trên Redis production bận rộn để thu log mọi lệnh: nó có thể gây tải và lộ giá trị nhạy cảm.

Khi phát hiện script lỗi sau mutation:

1. Xác định script version, tham số và request ID liên quan qua log/trace được phép lưu.
2. Kiểm tra trạng thái dữ liệu hiện tại ở Redis và, nếu có, nguồn nghiệp vụ gốc.
3. Phân biệt lỗi trước mutation với lỗi sau mutation hoặc không xác định.
4. Tạm ngừng retry tự động có thể tạo tác dụng lặp trong phạm vi sự cố.
5. Thực hiện bù/đối soát theo quy tắc nghiệp vụ đã định, lưu dấu vết sự kiện.
6. Sửa nguyên nhân gốc: input, key type, thứ tự kiểm tra, schema, script version hoặc cơ chế concurrency.

Không chạy lệnh “khôi phục” hàng loạt chỉ dựa trên số lượng exception. Một số request có thể đã thành công dù client báo timeout.

## 17. Những sai lầm thường gặp

- **Hiểu “Lua atomic” thành “Lua có rollback”:** script chạy không bị xen ngang nhưng ghi trước lỗi không được tự hoàn tác.
- **Đặt validation sau `DECRBY` hoặc `INCR`:** điều kiện nghiệp vụ thất bại nhưng dữ liệu đã thay đổi.
- **Dùng `redis.pcall` như savepoint:** bắt lỗi không hủy tác dụng phụ của các lệnh trước.
- **Trả `redis.error_reply` sau mutation rồi giả định không có ghi:** error reply không đồng nghĩa rollback.
- **Retry mọi exception cùng request ID mới:** có thể gây giảm tồn kho hoặc tăng bộ đếm lặp.
- **Không kiểm tra Redis key type trước ghi nhiều bước:** lệnh sau có thể phát `WRONGTYPE`.
- **Dùng `tonumber` với số nguyên nghiệp vụ quá lớn:** có nguy cơ sai chính xác khi dùng biểu diễn số Lua.
- **Đưa khóa đa slot vào script Redis Cluster:** có thể không thỏa ràng buộc thực thi nhiều khóa.
- **Xem timeout là script đã bị hủy:** client mất phản hồi không chứng minh server chưa chạy.
- **Xem `NOSCRIPT` như lỗi runtime:** script chưa có trong cache khác với script đã bắt đầu mutation.
- **Viết một script dài để “gộp mọi thứ”:** thời gian chặn Redis và phạm vi lỗi tăng theo độ phức tạp.
- **Dùng lệnh bù không kiểm soát:** lệnh bù cũng có thể lỗi và tạo trạng thái khó khôi phục hơn.
- **Không version hóa script và schema:** nhiều ứng dụng có thể chạy logic khác nhau trên cùng dữ liệu.

## 18. Cách quyết định trước khi triển khai

```text
Cần kiểm tra điều kiện rồi ghi Redis?
                    |
             +------+------+
             |             |
            Không           Có
             |             |
             v             v
       Xem lệnh Redis   Xác định tất cả
       atomic sẵn có    khóa, kiểu, input
                             |
                             v
                    Có thể kiểm tra mọi
                    điều kiện trước ghi?
                             |
                       +-----+-----+
                       |           |
                      Có          Chưa
                       |           |
                       v           v
                 Đặt validation   Thiết kế lại
                 trước mutation   flow/dữ liệu
                       |
                       v
                   Có nhiều mutation?
                       |
                  +----+----+
                  |         |
                 Không      Có
                  |         |
                  v         v
             Script đơn   Phân tích lỗi
             giản hơn     sau từng ghi,
                          bù và đối soát
                  |         |
                  +----+----+
                       |
                       v
                Có retry / timeout?
                       |
                       v
              Idempotency key ổn định,
              quan sát trạng thái thực
                       |
                       v
              Yêu cầu nhất quán/bền vững
              có vượt khả năng Redis?
                       |
                       v
              Chọn nguồn giao dịch và
              cơ chế phục hồi thích hợp
```

**Nguyên tắc cốt lõi:** Redis Lua script đảm bảo một chuỗi thao tác được **thực thi liên tục, không bị lệnh của client khác chen giữa**; nó **không cung cấp rollback cho ghi đã hoàn tất trước lỗi runtime**. Trong Spring Data Redis, cần coi script như một API có hợp đồng kết quả và lỗi rõ ràng, kiểm tra các điều kiện trước mutation, giới hạn số bước ghi, sử dụng idempotency key cho retry và chuẩn bị phương án đối soát khi kết quả không xác định. Khi cần tính nhất quán tuyệt đối trên nhiều thay đổi hoặc nhiều hệ thống, phải chọn mô hình dữ liệu và nguồn giao dịch phù hợp thay vì kỳ vọng chữ “atomic” tự giải quyết mọi trạng thái lỗi.


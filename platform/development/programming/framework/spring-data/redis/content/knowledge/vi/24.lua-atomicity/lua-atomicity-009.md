# Đóng gói, kiểm thử và quản lý phiên bản script Lua trong Spring Data Redis

## 1. Mục tiêu của bài học

Khi một thao tác nghiệp vụ cần **đọc trạng thái, kiểm tra điều kiện rồi cập nhật dữ liệu Redis như một đơn vị không bị lệnh khác chen vào**, Lua script là một công cụ hữu ích. Ví dụ: giữ tồn kho, giới hạn số lần sử dụng mã khuyến mại, kiểm tra và giải phóng khóa theo token, hoặc cập nhật nhiều thành phần có liên quan.

Viết được vài dòng Lua là bước đầu. Để script sống được trong một dự án Spring Boot lâu dài, chúng ta còn phải giải quyết ba vấn đề:

1. **Đóng gói:** đặt script ở đâu, làm sao gọi nó bằng Spring Data Redis, quy định rõ `KEYS`, `ARGV` và giá trị trả về.
2. **Kiểm thử:** xác minh hành vi ở Redis thật, kiểm tra các trường hợp lỗi, retry và đồng thời; hiểu chính xác ranh giới của tính nguyên tử.
3. **Quản lý phiên bản:** bảo đảm mã Java và script được triển khai đồng bộ, hỗ trợ rolling deployment, xử lý thay đổi schema và việc Redis xóa cache script.

Bài này xây dựng một ví dụ xuyên suốt: **giữ số lượng sản phẩm trong kho bằng Lua và Spring Data Redis**. Mục đích là học cách đưa script vào dự án một cách có thể kiểm soát, thay vì chép Lua vào chuỗi Java rồi để mỗi nơi gọi theo một quy ước khác nhau.

## 2. Lua đem lại tính nguyên tử ở phạm vi nào?

Một lệnh Redis đơn lẻ được Redis xử lý theo ngữ nghĩa của lệnh đó. Lua script cho phép gom nhiều thao tác vào một lần gọi `EVAL` hoặc `EVALSHA`. Trong thời gian một script chạy trên Redis, các lệnh của client khác không xen vào giữa các thao tác trong script.

Ví dụ dễ lỗi nếu chỉ gọi lần lượt từ Java:

~~~text
Client A                          Client B
--------                          --------
GET stock -> 5                    GET stock -> 5
thấy đủ 4                         thấy đủ 4
DECRBY stock 4                    DECRBY stock 4

Kết quả: tồn kho có thể thành -3, cả hai client đều nghĩ đã giữ thành công.
~~~

Với Lua:

~~~text
Client A                  Redis                    Client B
--------                  -----                    --------
EVAL reserve.lua --------> đọc stock = 5
                          kiểm tra đủ 4
                          cập nhật stock = 1
                          trả thành công
                                                   EVAL reserve.lua -->
                          đọc stock = 1
                          thấy không đủ 4
                          trả không đủ hàng
~~~

Hai lần chạy được Redis xử lý lần lượt. Client B nhìn thấy trạng thái sau thao tác của A.

**Nhưng nguyên tử ở đây không có nghĩa mọi lỗi đều được rollback.** Nếu script đã thực hiện một lệnh ghi rồi gặp lỗi runtime ở lệnh kế tiếp, những thay đổi trước đó có thể vẫn tồn tại. Redis Lua bảo đảm các lệnh khác không chen vào giữa script, **không cung cấp rollback tự động như một transaction SQL**.

Do đó, thiết kế script tốt nên:

- Kiểm tra dữ liệu và các điều kiện có thể kiểm tra **trước khi ghi**.
- Giảm số bước ghi và hạn chế các lỗi có thể xảy ra sau bước ghi đầu tiên.
- Giữ script ngắn, không có vòng lặp không giới hạn.
- Dùng giá trị trả về rõ ràng và thiết kế xử lý retry theo nghiệp vụ.
- Không dùng script để gọi HTTP, email hay dịch vụ ngoài Redis.

## 3. Quy ước thư mục trong dự án Spring Boot

Thay vì đưa nguyên một đoạn Lua dài vào chuỗi Java, lưu nó như một **resource được quản lý bởi Git**:

~~~text
inventory-service/
├── pom.xml hoặc build.gradle
├── src/
│   ├── main/
│   │   ├── java/com/example/inventory/
│   │   │   ├── config/
│   │   │   │   └── RedisScriptConfig.java
│   │   │   ├── service/
│   │   │   │   └── InventoryReservationService.java
│   │   │   └── model/
│   │   │       └── ReservationOutcome.java
│   │   └── resources/
│   │       └── redis/
│   │           └── scripts/
│   │               ├── reserve-stock-v1.lua
│   │               └── README.md
│   └── test/
│       └── java/com/example/inventory/
│           └── InventoryReservationIntegrationTest.java
~~~

Ưu điểm khi file nằm trong `src/main/resources`:

- Spring có thể tìm qua `ClassPathResource`, kể cả khi ứng dụng được đóng gói thành executable JAR.
- File Lua được review, diff và version cùng Java code.
- Cùng một bản build mang đúng mã Java và nội dung Lua mà Java gọi.
- Có thể đặt kiểm thử tích hợp và contract test cạnh phần code sử dụng.
- Không phụ thuộc vào đường dẫn tuyệt đối trên máy chủ hoặc thư mục làm việc của process.

Ví dụ đường dẫn resource:

~~~text
classpath:redis/scripts/reserve-stock-v1.lua
~~~

Không nên dùng `new File("src/main/resources/...")` trong production. Đường dẫn đó chỉ tồn tại ở cấu trúc source của dự án, chưa chắc còn tồn tại khi chạy từ JAR hoặc container.

### Vì sao tên file có hậu tố v1?

Tên `reserve-stock-v1.lua` thể hiện **phiên bản của contract script**, gồm cách hiểu `KEYS`, `ARGV`, cấu trúc dữ liệu Redis và mã kết quả. Khi đổi một contract làm ảnh hưởng caller hoặc dữ liệu chung, tạo `v2` thay vì âm thầm thay đổi nội dung `v1` đang được nhiều phiên bản ứng dụng gọi.

Nếu chỉ sửa lỗi nhỏ không làm đổi contract, vẫn phải chú ý rằng **thay một byte trong source sẽ tạo SHA script khác**. Việc có cần tăng major contract version hay không được quyết định theo quy ước versioning của đội, không chỉ theo việc SHA thay đổi.

## 4. Thiết kế contract trước khi viết Lua

Xét hệ thống giữ tồn kho theo SKU. Ta chọn **một Redis Hash cho mỗi SKU**:

~~~text
Key: inventory:{sku-42}:state

Hash fields:
  available         -> "10"
  reservation:r-101 -> "3"
  reservation:r-102 -> "2"
~~~

Trong mô hình này:

- `available` là số đơn vị chưa được giữ.
- `reservation:<reservationId>` ghi số lượng đã giữ cho một request duy nhất.
- Gọi lại với **cùng reservationId và cùng số lượng** trả về kết quả "đã thực hiện trước đó" mà không trừ kho thêm lần nữa.
- Gọi lại với **cùng reservationId nhưng số lượng khác** được báo xung đột.
- Một thao tác reserve cập nhật `available` và field reservation trong **cùng một lệnh `HSET` nhiều field**.

Thiết kế một hash giúp ví dụ có **một Redis key** và bước ghi chính là **một lệnh Redis**. Đối với hệ thống thực tế, vẫn cần quy trình giải phóng reservation, trạng thái đơn hàng, chính sách dọn reservation và kiểm soát số field tăng theo thời gian. Ở đây ta tập trung vào contract đóng gói và kiểm thử script.

### Contract v1

| Thành phần | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `KEYS[1]` | `inventory:{sku-42}:state` | Redis Hash chứa trạng thái SKU |
| `ARGV[1]` | `reservationId` | ID của lần giữ kho, dùng cho idempotency |
| `ARGV[2]` | `quantity` | Số lượng nguyên dương cần giữ, truyền dưới dạng chuỗi |
| `return 1` | Thành công mới | Đã trừ số lượng và ghi reservation |
| `return 2` | Retry cùng yêu cầu | Reservation này đã tồn tại với cùng số lượng |
| `return 0` | Không đủ tồn kho | Không ghi gì |
| `return -1` | Chưa có tồn kho | Hash hoặc field `available` chưa được khởi tạo |
| `return -2` | Xung đột idempotency | Reservation ID đã dùng cho quantity khác |
| Redis error reply | Dữ liệu/đối số không hợp lệ | Caller cần xử lý như lỗi, không suy luận thành hết hàng |

Trong Spring Data Redis, `KEYS` chứa **tên key Redis**, còn `ARGV` chứa **đối số không phải key**. Nên khai báo contract theo thứ tự rõ ràng: gọi nhầm `ARGV[1]` và `ARGV[2]` có thể tạo dữ liệu sai mà chương trình vẫn chạy.

### Cấu trúc dữ liệu bắt buộc phải ổn định

Ví dụ script dự kiến:

~~~redis
HSET inventory:{sku-42}:state available 10
HGET inventory:{sku-42}:state available
~~~

Nếu caller khác bất ngờ dùng `SET inventory:{sku-42}:state "10"`, key trở thành Redis String thay vì Hash. Lệnh `HGET` sẽ nhận lỗi `WRONGTYPE`. Chỉ một namespace cần có **một quy ước dữ liệu** và người chịu trách nhiệm quản lý.

## 5. File Lua hoàn chỉnh: reserve-stock-v1.lua

Đặt nội dung sau vào `src/main/resources/redis/scripts/reserve-stock-v1.lua`:

~~~lua
-- reserve-stock-v1.lua
--
-- Contract:
--   KEYS[1]: Redis Hash chứa inventory của một SKU
--   ARGV[1]: reservationId (không được rỗng)
--   ARGV[2]: quantity (số nguyên từ 1 đến 1.000)
--
-- Return:
--    1  = reservation mới thành công
--    2  = request trùng hợp lệ, không trừ kho lần nữa
--    0  = không đủ tồn kho
--   -1  = inventory chưa được khởi tạo
--   -2  = cùng reservationId nhưng quantity khác
--   error reply = đầu vào hoặc trạng thái dữ liệu không hợp lệ

if #KEYS ~= 1 or #ARGV ~= 2 then
    return redis.error_reply("ERR_BAD_ARGUMENT_COUNT")
end

local inventoryKey = KEYS[1]
local reservationId = ARGV[1]
local rawQuantity = ARGV[2]

if not reservationId or reservationId == "" then
    return redis.error_reply("ERR_EMPTY_RESERVATION_ID")
end

-- Giới hạn input giúp tránh số thực không chính xác và thao tác quá lớn.
local quantity = tonumber(rawQuantity)
if not quantity
    or quantity ~= math.floor(quantity)
    or quantity < 1
    or quantity > 1000 then
    return redis.error_reply("ERR_INVALID_QUANTITY")
end

-- HGET sẽ trả false nếu Hash field không tồn tại.
local currentRaw = redis.call("HGET", inventoryKey, "available")
if not currentRaw then
    return -1
end

local available = tonumber(currentRaw)
if not available
    or available ~= math.floor(available)
    or available < 0
    or available > 1000000000 then
    return redis.error_reply("ERR_INVALID_STOCK")
end

local reservationField = "reservation:" .. reservationId
local existingRaw = redis.call("HGET", inventoryKey, reservationField)

if existingRaw then
    if tonumber(existingRaw) == quantity then
        return 2
    end
    return -2
end

if available < quantity then
    return 0
end

local remaining = available - quantity

-- Chỉ một lệnh ghi sau khi đã xác minh các điều kiện.
redis.call(
    "HSET",
    inventoryKey,
    "available", string.format("%.0f", remaining),
    reservationField, string.format("%.0f", quantity)
)

return 1
~~~

Script sử dụng Lua được Redis hỗ trợ (ngôn ngữ Lua 5.1 trong Redis scripting truyền thống). Chỉ số mảng `KEYS` và `ARGV` bắt đầu từ **1**.

### Tại sao dùng một lệnh HSET nhiều field?

Một biến thể dễ mắc lỗi là:

~~~lua
redis.call("HINCRBY", KEYS[1], "available", -quantity)
redis.call("HSET", KEYS[1], reservationField, quantity)
~~~

Nếu lệnh thứ hai phát sinh lỗi, lệnh trừ tồn kho thứ nhất có thể đã được áp dụng; **Lua script không tự rollback**. Ví dụ v1 đã đưa các kiểm tra cần thiết trước lệnh ghi và dùng một `HSET` để cập nhật đồng thời hai field trong Hash.

Trong bài toán thực tế, cần xem xét cả lỗi của toàn bộ thao tác, sự tồn tại của dữ liệu ngoài Redis, giới hạn kích thước Hash và tính đúng của các bước release/confirm. Chỉ một script reserve không tự giải quyết toàn bộ lifecycle đơn hàng.

### Vì sao không dùng TIME bên trong script?

Ví dụ này không cần thời gian. Khi logic cần deadline, có thể truyền mốc thời gian theo contract rõ ràng qua `ARGV`, sau đó kiểm tra tính đúng của nguồn thời gian. Điều này còn giúp viết test tái lập được.

Trong các phiên bản Redis khác nhau, quy tắc replication và một số lệnh có thể thay đổi. Không nên đưa hành vi ngẫu nhiên, phụ thuộc thời gian hoặc gọi lệnh bị hạn chế vào script mà chưa nắm rõ Redis server đang triển khai.

## 6. Gọi script từ Java bằng DefaultRedisScript

Spring Data Redis có lớp `DefaultRedisScript<T>` để mô tả nguồn script và kiểu kết quả. Tạo bean một lần để tái sử dụng:

~~~java
package com.example.inventory.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class RedisScriptConfig {

    @Bean
    public RedisScript<Long> reserveStockV1Script() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setLocation(
            new ClassPathResource(
                "redis/scripts/reserve-stock-v1.lua"
            )
        );
        script.setResultType(Long.class);
        return script;
    }
}
~~~

`Long.class` là lựa chọn phù hợp vì Lua `return 1`, `return 0` hay `return -2` tạo phản hồi số nguyên Redis. Không dùng `String.class` cho các mã integer và kỳ vọng Spring tự ép mọi kết quả theo ý nghĩa nghiệp vụ.

Nên giữ bean script ở singleton scope thông thường, không tạo `DefaultRedisScript` và đọc lại resource theo cách thủ công trong từng request. Spring Data Redis có thể tính và dùng SHA1 của nội dung script khi thực thi.

### Service Spring dùng StringRedisTemplate

~~~java
package com.example.inventory.service;

import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class InventoryReservationService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> reserveStockV1;

    public InventoryReservationService(
            StringRedisTemplate redis,
            RedisScript<Long> reserveStockV1Script) {
        this.redis = redis;
        this.reserveStockV1 = reserveStockV1Script;
    }

    public ReservationOutcome reserve(
            String sku,
            String reservationId,
            int quantity) {

        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (reservationId == null || reservationId.isBlank()) {
            throw new IllegalArgumentException("reservationId is required");
        }

        // Hash tag {sku} giữ key cùng slot nếu cần mở rộng trong Cluster.
        String key = "inventory:{" + sku + "}:state";

        Long code = redis.execute(
            reserveStockV1,
            List.of(key),
            reservationId,
            Integer.toString(quantity)
        );

        if (code == null) {
            throw new IllegalStateException(
                "Lua script returned no result"
            );
        }

        return switch (code.intValue()) {
            case 1 -> ReservationOutcome.CREATED;
            case 2 -> ReservationOutcome.ALREADY_RESERVED;
            case 0 -> ReservationOutcome.INSUFFICIENT_STOCK;
            case -1 -> ReservationOutcome.INVENTORY_MISSING;
            case -2 -> ReservationOutcome.IDEMPOTENCY_CONFLICT;
            default -> throw new IllegalStateException(
                "Unknown Lua result: " + code
            );
        };
    }

    public enum ReservationOutcome {
        CREATED,
        ALREADY_RESERVED,
        INSUFFICIENT_STOCK,
        INVENTORY_MISSING,
        IDEMPOTENCY_CONFLICT
    }
}
~~~

Với `StringRedisTemplate`, keys và các arguments kiểu String được tuần tự hóa theo quy ước string của template. Lua nhận các chuỗi tương ứng ở `KEYS` và `ARGV`; Redis tự xử lý thao tác nội bộ lên Hash.

Trước khi gọi, dữ liệu inventory cần được khởi tạo:

~~~java
String key = "inventory:{sku-42}:state";

redis.opsForHash().put(key, "available", "10");

var result = reservationService.reserve("sku-42", "r-101", 3);
~~~

Sau khi giữ thành công:

~~~redis
HGET inventory:{sku-42}:state available
HGET inventory:{sku-42}:state reservation:r-101
~~~

Kết quả lần lượt là `"7"` và `"3"`. Gọi lại với `r-101` và số lượng 3 sẽ trả `ALREADY_RESERVED`, lượng tồn kho vẫn là 7.

### Kiểu Java nào nhận được phản hồi?

| Lua return | Redis/Spring Data Redis | Cách đọc nên dùng |
| --- | --- | --- |
| `return 1` | Integer reply, Java `Long` khi cấu hình `Long.class` | Map sang enum/mã kết quả |
| `return 0` | `Long(0)` | Không đủ hàng |
| `return -2` | `Long(-2)` | Xung đột idempotency |
| `return redis.error_reply(...)` | Lỗi Redis qua exception | Bắt và phân loại lỗi |
| `return false` | Có thể được ánh xạ thành nil/null tùy contract | Tránh dùng cho result code của ví dụ |
| `return {1, 2}` | Phản hồi danh sách | Cần `resultType` và mapping thích hợp |

Giữ contract trả về **một số nguyên** cho v1 giúp code Java ít mơ hồ hơn việc trả một bảng Lua phức tạp.

## 7. RedisScript, EVAL và EVALSHA

Ở mức Redis, có hai cách thực thi script truyền thống:

~~~redis
EVAL "<Lua source>" 1 inventory:{sku-42}:state r-101 3
EVALSHA <sha1> 1 inventory:{sku-42}:state r-101 3
~~~

- `EVAL` gửi nội dung script trực tiếp.
- `EVALSHA` gửi SHA1 của nội dung đã được Redis biết tới; nếu script chưa có trong cache, Redis trả lỗi `NOSCRIPT`.
- `SCRIPT LOAD` có thể chủ động nạp script vào cache; `SCRIPT EXISTS` kiểm tra cache ở Redis server đang hỏi.
- `SCRIPT FLUSH` xóa script cache tại server; cache cũng có thể thay đổi khi restart, failover hoặc do cơ chế quản lý của phiên bản Redis.

Khi dùng `RedisTemplate.execute(redisScript, keys, args...)`, Spring Data Redis mặc định có cơ chế **thử `EVALSHA` và fallback sang `EVAL` khi script chưa được Redis cache**. Vì thế ứng dụng thường không cần tự gọi `SCRIPT LOAD` trước mỗi lần chạy.

~~~text
Spring RedisScript
     |
     v
Tính/lấy SHA1 của source Lua
     |
     v
EVALSHA -------------------+
     |                     |
     | script đã có         | NOSCRIPT
     v                     v
Redis chạy script        EVAL với full source
                               |
                               v
                         Redis chạy script
~~~

**Không nên xem script cache là nơi lưu trữ bền vững.** Nguồn thật của script vẫn là file resource trong artifact triển khai của ứng dụng. Khi cache trống, app phải có khả năng gửi lại source.

### SHA là danh tính nội dung, không phải phiên bản nghiệp vụ

Giả sử:

~~~text
reserve-stock-v1.lua (nội dung A) -> SHA_A
reserve-stock-v1.lua (nội dung B) -> SHA_B
~~~

Chỉ cần sửa dấu cách hoặc comment, SHA1 cũng có thể thay đổi. Ngược lại, tên file v2 không tự bảo đảm contract khác nếu nội dung trùng nhau.

Phân biệt:

- **SHA1:** nhận dạng chính xác nội dung Lua để Redis tìm trong script cache.
- **Tên/contract version (v1, v2):** quy ước ứng dụng về cách gọi, dữ liệu và ý nghĩa kết quả.
- **Application version:** bản build Spring Boot chứa Java caller và các script resources.

Ba khái niệm này phục vụ ba nhu cầu khác nhau, không thay thế cho nhau.

## 8. Quy tắc KEYS và ARGV trong Redis Cluster

Trong Redis Cluster, tất cả các key mà script truy cập phải tuân thủ quy tắc phân phối key, thông thường các key liên quan trong một lần chạy phải thuộc **cùng hash slot**.

Ví dụ hai key:

~~~text
inventory:{sku-42}:state
inventory:{sku-42}:audit
~~~

Cùng phần hash tag `{sku-42}`, nên cùng slot. Ngược lại:

~~~text
inventory:{sku-42}:state
inventory:{sku-99}:audit
~~~

thường ở hai slot khác nhau, và lệnh script truy cập cả hai có thể bị từ chối trong Cluster.

**Mọi tên Redis key được script truy cập phải được khai báo qua `KEYS` theo contract.** Không dùng `ARGV` để lén truyền key khác, hoặc dựng key Redis động từ một giá trị không được khai báo. Trong ví dụ v1, `"reservation:" .. reservationId` chỉ là **field bên trong một Hash**, không phải key Redis mới.

Những lựa chọn này giúp Redis Cluster định tuyến lệnh, tăng khả năng kiểm soát và giảm lỗi `CROSSSLOT`.

### Khi nào không nên gom nhiều key cùng slot?

Hash tag là công cụ phân phối dữ liệu, không phải lời khuyên đặt toàn bộ ứng dụng vào một slot. Nếu mọi SKU đều dùng cùng một tag, tất cả khóa có thể bị dồn về một node, gây mất cân bằng tải.

Trong ví dụ:

~~~text
inventory:{sku-42}:state
inventory:{sku-99}:state
~~~

mỗi SKU có thể phân phối độc lập; chỉ những key cần thao tác cùng nhau mới dùng chung tag của SKU đó.

## 9. Đóng gói contract để không lệ thuộc vị trí tham số

Một script nhận tham số bằng index. Sau một thời gian, việc xuất hiện nhiều lời gọi:

~~~java
redis.execute(script, List.of(key), "r-101", "3");
redis.execute(script, List.of(key), "r-102", "5");
~~~

có thể khiến người bảo trì vô tình đổi thứ tự đối số, nhập sai kiểu hoặc dùng nhầm phiên bản script.

Giải pháp là tạo **một service/wrapper duy nhất** quản lý:

- Xây key theo namespace và hash tag.
- Validate các đầu vào ở tầng Java để phản hồi lỗi sớm.
- Chọn script version phù hợp.
- Truyền `KEYS` và `ARGV` đúng thứ tự.
- Map return code thành enum hoặc kết quả nghiệp vụ có tên.
- Gắn log/metric với script name và version.
- Xử lý exception, retry và timeout theo quy tắc nghiệp vụ.

Không cần expose `RedisScript<Long>` trực tiếp đến controller. Controller chỉ nên làm việc với API như `reservationService.reserve(sku, requestId, qty)`.

Có thể đặt contract ngắn ngay trong thư mục script:

~~~markdown
# reserve-stock-v1

- Keys: 1 key Hash, inventory:{sku}:state.
- ARGV[1]: reservationId.
- ARGV[2]: positive integer quantity, max 1000.
- Codes: 1 created, 2 already applied, 0 insufficient,
  -1 missing, -2 conflicting request.
- Failure: Redis error reply for malformed input/state.
- Data: field available and reservation:<id>.
- Atomic write: one HSET updating both fields.
- Idempotency: reservationId scoped to inventory key.
- Compatibility: callers using v1 must keep this schema.
~~~

Mẫu trên chỉ là một phần tài liệu cho script, không phải file QA và không cần tự tạo thêm trong lượt viết bài.

## 10. Kiểm thử ở ba tầng

Vì tính đúng của Lua phụ thuộc hành vi của Redis, kiểm thử nên có nhiều mức:

| Tầng | Mục tiêu | Phương pháp |
| --- | --- | --- |
| Kiểm tra contract và cấu hình | File resource tồn tại, result type và cách gọi đúng | Test khởi tạo bean/service |
| Integration test với Redis thật | Xác nhận cú pháp Lua, lệnh Redis, kiểu kết quả và trạng thái | Redis local/Testcontainers |
| Kiểm tra đồng thời và vận hành | Hai hoặc nhiều client không vượt quá tồn kho; xử lý retry, cache miss, failover | Integration/concurrency test có giới hạn và thử nghiệm hệ thống |

Mock `StringRedisTemplate` hữu ích để kiểm tra mapping Java, nhưng **mock không thực thi Lua**. Một test chỉ kiểm tra “đã gọi `redis.execute` với List.of(key)” không chứng minh script đúng, không chứng minh tính nguyên tử, cũng không phát hiện lỗi `WRONGTYPE` hoặc `NOSCRIPT`.

### Vì sao ưu tiên Redis thật trong test?

Lua chạy trong Redis với các quy tắc cụ thể:

- `redis.call` và `redis.pcall` có phản hồi/lỗi theo Redis.
- `KEYS`, `ARGV` là chuỗi theo dạng truyền vào.
- Giá trị nil/false và bảng Lua được chuyển sang Redis replies theo quy tắc Redis scripting.
- Các lệnh Hash, String, Set và TTL có ngữ nghĩa Redis.
- Sự tranh chấp giữa client chỉ có thể quan sát thực tế khi gọi song song.

Vì vậy, một Redis instance dùng riêng cho kiểm thử cho độ tin cậy cao hơn việc cố tái hiện Redis behavior bằng stub Java.

## 11. Các ca kiểm thử bắt buộc của script v1

Bảng tình huống cho ví dụ giữ tồn kho:

| Tình huống | Dữ liệu ban đầu | Kết quả mong đợi | Trạng thái sau |
| --- | --- | --- | --- |
| Giữ thành công | available=10, chưa có r-101 | `1` | available=7, reservation:r-101=3 |
| Retry giống hệt | đã có r-101=3 | `2` | available vẫn 7 |
| Retry xung đột | đã có r-101=3, xin quantity=4 | `-2` | Không đổi |
| Không đủ tồn | available=2, xin 3 | `0` | Không đổi |
| Hash chưa tồn tại | Không có key | `-1` | Không tạo key mới |
| quantity=0 | available=10 | Error | Không đổi |
| quantity âm/không nguyên | available=10 | Error | Không đổi |
| available không phải số | available="abc" | Error | Không đổi |
| Key sai Redis type | key là String | Redis `WRONGTYPE` | Không đổi |
| Hai request cạnh tranh | available=1, hai ID khác nhau, mỗi ID xin 1 | Chỉ một trả `1` | available=0 |
| Retry sau timeout | Client không biết lần đầu có thành công | `1` hoặc `2` tùy lần đầu | Không được trừ hai lần cho một ID |
| Nhiều SKU | Hai key khác nhau | Kết quả độc lập | Không ghi nhầm namespace |

Bảng trên kiểm tra **hành vi chính của contract**, bao gồm cả những trường hợp dễ gây lỗi khi triển khai thực tế.

### Tình huống timeout đặc biệt quan trọng

Client có thể timeout sau khi Redis **đã chạy xong script**, nhưng trước khi nhận phản hồi. Lúc đó client không biết yêu cầu đã thành công hay chưa:

~~~text
Spring ---> Redis chạy reserve ---> stock bị trừ, reservation đã ghi
   ^
   |
   +---- mạng timeout trước khi Java nhận kết quả
~~~

Nếu retry với **reservationId mới**, stock có thể bị trừ lần thứ hai. Nếu retry với **cùng reservationId**, script v1 nhìn thấy field đã ghi và trả mã `2` mà không trừ thêm. Đây là lý do cần thiết kế idempotency trong contract script và caller, không chỉ trông chờ vào việc Redis xử lý atomically.

## 12. Ví dụ integration test với Testcontainers và JUnit 5

Một cấu hình kiểm thử phổ biến là chạy Redis thực trong container và cho Spring kết nối đến cổng ngẫu nhiên được map. Dependencies thường gồm Spring Data Redis Starter, Spring Boot Test, Testcontainers và JUnit Jupiter.

Ví dụ minh họa theo cấu trúc ứng dụng ở trên:

~~~java
package com.example.inventory;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import com.example.inventory.service.InventoryReservationService;
import com.example.inventory.service.InventoryReservationService.ReservationOutcome;

@Testcontainers
@SpringBootTest
class InventoryReservationIntegrationTest {

    private static final String KEY = "inventory:{sku-42}:state";

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void configureRedis(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate redis;

    @Autowired
    InventoryReservationService service;

    @BeforeEach
    void resetInventory() {
        redis.delete(KEY);
        redis.opsForHash().put(KEY, "available", "10");
    }

    @Test
    void reservesStockExactlyOnceForSameRequestId() {
        assertThat(service.reserve("sku-42", "r-101", 3))
            .isEqualTo(ReservationOutcome.CREATED);

        assertThat(service.reserve("sku-42", "r-101", 3))
            .isEqualTo(ReservationOutcome.ALREADY_RESERVED);

        assertThat(redis.opsForHash().get(KEY, "available"))
            .isEqualTo("7");

        assertThat(redis.opsForHash().get(KEY, "reservation:r-101"))
            .isEqualTo("3");
    }

    @Test
    void insufficientStockDoesNotWriteReservation() {
        assertThat(service.reserve("sku-42", "r-102", 11))
            .isEqualTo(ReservationOutcome.INSUFFICIENT_STOCK);

        assertThat(redis.opsForHash().get(KEY, "available"))
            .isEqualTo("10");

        assertThat(redis.opsForHash().get(KEY, "reservation:r-102"))
            .isNull();
    }

    @Test
    void rejectsSameRequestIdWithDifferentQuantity() {
        assertThat(service.reserve("sku-42", "r-103", 2))
            .isEqualTo(ReservationOutcome.CREATED);

        assertThat(service.reserve("sku-42", "r-103", 4))
            .isEqualTo(ReservationOutcome.IDEMPOTENCY_CONFLICT);

        assertThat(redis.opsForHash().get(KEY, "available"))
            .isEqualTo("8");
    }
}
~~~

Test này mô tả Spring Boot dùng các property `spring.data.redis.host` và `spring.data.redis.port`. Tùy phiên bản Spring Boot, container setup, package scan hoặc cấu hình của ứng dụng, bạn sẽ cần điều chỉnh import/dependency và application test context tương ứng.

**Không dùng chung Redis production cho integration test.** Test phải kiểm soát namespace, reset dữ liệu và thứ tự chạy, tránh va chạm với dịch vụ khác.

### Những khẳng định quan trọng trong test

Một test tốt không chỉ khẳng định result code. Nó kiểm tra **trạng thái Redis sau khi chạy**, vì bug có thể khiến script trả mã thành công nhưng cập nhật thiếu field, hoặc trả lỗi sau khi đã thay đổi một phần dữ liệu.

Với retry, hãy xác minh `available` không bị trừ thêm. Với không đủ hàng, hãy xác minh field reservation không được tạo. Đây là các bất biến nghiệp vụ quan trọng hơn bản thân câu chữ trong exception.

## 13. Kiểm thử đồng thời để chứng minh không oversell

Ví dụ tồn kho còn 10 đơn vị, tạo 20 request khác nhau, mỗi request cố giữ 1 đơn vị. Kết quả đúng:

- **Đúng 10** request được tạo mới (mã `1`).
- Các request còn lại trả không đủ hàng (mã `0`).
- `available = 0`.
- Không có tồn kho âm.
- Mỗi `reservationId` thành công xuất hiện đúng một lần.

Pseudocode JUnit:

~~~java
var pool = java.util.concurrent.Executors.newFixedThreadPool(20);
var start = new java.util.concurrent.CountDownLatch(1);
var tasks = new java.util.ArrayList<
    java.util.concurrent.Future<ReservationOutcome>
>();

try {
    for (int i = 0; i < 20; i++) {
        final String requestId = "parallel-" + i;

        tasks.add(pool.submit(() -> {
            start.await();
            return service.reserve("sku-42", requestId, 1);
        }));
    }

    start.countDown();

    long created = 0;

    for (var future : tasks) {
        var outcome = future.get();
        if (outcome == ReservationOutcome.CREATED) {
            created++;
        }
    }

    assertThat(created).isEqualTo(10L);
    assertThat(redis.opsForHash().get(KEY, "available"))
        .isEqualTo("0");
} finally {
    pool.shutdownNow();
}
~~~

Đoạn trên là ví dụ đặt **bên trong một test method** có sẵn `service`, `redis`, `KEY` và các import thích hợp. Nó cần được chạy với Redis thật; một mock `RedisTemplate` chỉ mô phỏng các lời gọi, không chứng minh thứ tự thực thi của server.

Bài test đồng thời cung cấp bằng chứng thực nghiệm cho bất biến “không oversell” ở luồng cụ thể. Nó không thay thế phân tích race condition cho toàn bộ nghiệp vụ, đặc biệt nếu bước thanh toán, hoàn kho hoặc dữ liệu ở hệ thống khác xảy ra ngoài script.

## 14. Kiểm thử lỗi và những giới hạn của tính nguyên tử

Cần cố ý đưa dữ liệu xấu vào Redis trong một Redis test riêng:

~~~redis
DEL inventory:{sku-42}:state
SET inventory:{sku-42}:state "not-a-hash"
~~~

Sau đó gọi script. Khi `HGET` đụng key dạng String, Redis trả lỗi `WRONGTYPE`. Ở Java, Spring Data Redis chuyển lỗi này thành một exception phù hợp qua tầng driver/exception translation.

Test phải khẳng định không có tác dụng phụ không mong muốn.

Một trường hợp khác:

~~~redis
DEL inventory:{sku-42}:state
HSET inventory:{sku-42}:state available invalid
~~~

Script trả `ERR_INVALID_STOCK` trước khi ghi. Mẫu thiết kế này giảm khả năng dữ liệu bị biến đổi do input sai.

### Thao tác atomically nhưng không rollback

Xét script không nên dùng:

~~~lua
redis.call("INCR", KEYS[1])
redis.call("HSET", KEYS[1], "field", "value")
return 1
~~~

`INCR` có thể tăng một String counter thành công. `HSET` trên cùng key kiểu String sẽ gây `WRONGTYPE`. Lúc client nhận lỗi, bộ đếm **đã tăng**. Redis không rollback lệnh `INCR` chỉ vì phần sau của script lỗi.

Từ đó cần phân biệt:

- **Isolation/no interleaving:** các client khác không chen lệnh vào giữa một script đang chạy.
- **Rollback:** hủy tác động đã ghi khi script gặp lỗi — Lua script Redis không cung cấp bảo đảm này.
- **Idempotency:** retry không làm tăng tác dụng phụ nhiều lần — phải tự thiết kế.
- **Durability:** trạng thái được khôi phục sau Redis crash — phụ thuộc persistence/replication, không chỉ Lua.

Đây là bốn tính chất khác nhau. Chỉ việc gọi `EVAL` không tạo đủ cả bốn.

## 15. Quản lý source và script cache qua các lần triển khai

Script Lua là phần của **mã nguồn ứng dụng**, còn cache script ở Redis là **trạng thái runtime**.

~~~text
Git repository
  reserve-stock-v1.lua
          |
          v
CI đóng gói vào JAR / image
          |
          v
Spring RedisScript bean
          |
          v
EVALSHA -> nếu NOSCRIPT -> EVAL
          |
          v
Redis thực thi và có thể cache script
~~~

Các tình huống cần dự liệu:

**Redis restart:** Script cache có thể không còn. Caller phải vẫn có nội dung Lua để fallback.

**Failover:** Node mới có thể không có cùng cache script như node trước. Không nên giả định mọi node đã có SHA.

**SCRIPT FLUSH:** Cache bị xóa. Lệnh tiếp theo phải có đường fallback. Lưu ý script cache và Redis Function library là hai cơ chế khác nhau.

**Redis Cluster:** Các node có thể có trạng thái script cache khác nhau. Kiểm tra `SCRIPT EXISTS` ở một node không chứng minh mọi node đều đã có script.

**Redis server version:** Chính sách giữ hoặc loại bỏ script cache có thể khác nhau giữa các phiên bản (chẳng hạn việc loại bỏ script được tải qua EVAL trong những phiên bản mới). Mã ứng dụng nên dựa vào cơ chế thực thi có fallback chứ không giả định cache tồn tại vô thời hạn.

Không nên viết một startup job yêu cầu `SCRIPT LOAD` hoàn tất trên một node rồi coi đó là bảo đảm vĩnh viễn cho cả cluster. Preload có thể giúp giảm lần fallback đầu tiên, nhưng **không thay thế source trong artifact**.

## 16. Chiến lược versioning cho Lua script

Nên xác định phiên bản theo **contract**, không chỉ theo checksum.

Một lựa chọn đơn giản:

~~~text
src/main/resources/redis/scripts/
  reserve-stock-v1.lua
  reserve-stock-v2.lua
  release-reservation-v1.lua
  README.md
~~~

Với mỗi script, tài liệu contract gồm:

| Thành phần cần version | Câu hỏi |
| --- | --- |
| Số lượng và thứ tự KEYS | Caller cũ còn gọi được không? |
| Số lượng và ý nghĩa ARGV | Tham số mới có bắt buộc không? |
| Kiểu và mã kết quả | Java cũ có hiểu tất cả code không? |
| Cấu trúc Redis key/field | Hai bản ứng dụng có đọc/ghi cùng dữ liệu được không? |
| Thuật toán và bất biến | Có thay đổi semantics của reservation không? |
| Phạm vi idempotency | Request ID cũ có bị hiểu khác không? |
| Timeout và độ phức tạp | Script mới có ảnh hưởng tải Redis không? |
| Redis/Spring version tối thiểu | Có dùng command/API mới không? |

Một ví dụ thay đổi cần cân nhắc tạo v2:

~~~text
v1:
  KEYS[1] = inventory hash
  ARGV[1] = reservationId
  ARGV[2] = quantity
  return = integer code

v2 dự kiến:
  KEYS[1] = inventory hash
  ARGV[1] = reservationId
  ARGV[2] = quantity
  ARGV[3] = expiresAtEpochMillis
  return = mã mới cho reservation expired
~~~

Nếu ghi đè nội dung `reserve-stock-v1.lua` để đòi `ARGV[3]`, các instance Java cũ vẫn truyền hai tham số sẽ bị lỗi. Trong rolling deployment, điều này có thể xảy ra ngay khi một phần instance đã nâng cấp.

Vì vậy, để caller cũ tiếp tục hoạt động:

- Để nguyên v1 nếu chưa thể loại bỏ.
- Tạo file v2 và bean `reserveStockV2Script` riêng.
- Cho code mới gọi v2 thông qua feature flag hoặc deployment configuration.
- Đảm bảo v1 và v2 cùng đọc/ghi dữ liệu theo một chiến lược tương thích.
- Chỉ xóa v1 sau khi không còn client nào cần và kế hoạch rollback không còn phụ thuộc nó.

**Nội dung Lua mới có SHA mới**, nhưng cách đặt v1/v2 giúp con người quản lý tương thích chứ không cần nhớ SHA dài.

## 17. Rolling deployment: nguy cơ từ hai phiên bản ứng dụng

Kịch bản phổ biến:

~~~text
Thời điểm       App instance A              App instance B
---------       --------------              --------------
T0              release 1 gọi Lua v1       release 1 gọi Lua v1
T1              release 2 gọi Lua v2       release 1 gọi Lua v1
T2              release 2 gọi Lua v2       release 2 gọi Lua v2
~~~

Ở `T1`, v1 và v2 **cùng thao tác trên Redis**. Nếu v2 thay đổi field name từ `available` thành `freeUnits` mà không tương thích ngược, v1 và v2 có thể nhìn thấy hai trạng thái khác nhau.

Hệ quả nghiêm trọng: mỗi bản ứng dụng tưởng mình đã kiểm tra tồn kho, nhưng hai bản không sử dụng cùng nguồn số lượng. Đây là vấn đề tương thích **data schema**, không chỉ là vấn đề SHA cache.

### Quy trình expand–migrate–contract

Một cách triển khai cho thay đổi lớn:

1. **Expand:** đưa code có thể đọc schema cũ và schema mới vào hệ thống; không phá hành vi caller cũ.
2. **Migrate:** chuyển hoặc bổ sung dữ liệu theo batch, có thể chạy song song trong giai đoạn tương thích.
3. **Switch:** chuyển traffic sang script v2 thông qua rollout/feature flag.
4. **Observe:** theo dõi result code, lỗi, latency và bất biến nghiệp vụ.
5. **Contract:** khi không còn cần rollback về v1, loại bỏ đường cũ và dữ liệu cũ theo kế hoạch.

Nếu không thể cho v1 và v2 cùng dùng schema, cân nhắc namespace version riêng hoặc dừng ghi có kiểm soát trong thời gian migration. Tuyệt đối không coi "deploy thành công ứng dụng mới" là đủ để đổi ngay cấu trúc dữ liệu mà version cũ vẫn đang sử dụng.

### Chọn thời điểm bỏ script cũ

Script cũ có thể còn cần cho:

- Pod hoặc instance chưa được nâng cấp.
- Job chậm hoặc consumer chạy version cũ.
- Công cụ vận hành/CLI có lời gọi script cố định.
- Kế hoạch rollback ứng dụng.
- Dữ liệu được ghi theo schema cũ cần đọc hoặc giải phóng.

Đặt điều kiện rõ ràng trước khi xóa file v1 để tránh lỗi chỉ xuất hiện sau khi rollback.

## 18. Đặt script version vào Java mà không tạo chuỗi động khó kiểm soát

Một cách khai báo riêng:

~~~java
@Bean
public RedisScript<Long> reserveStockV1Script() {
    DefaultRedisScript<Long> script = new DefaultRedisScript<>();
    script.setLocation(
        new ClassPathResource("redis/scripts/reserve-stock-v1.lua")
    );
    script.setResultType(Long.class);
    return script;
}

@Bean
public RedisScript<Long> reserveStockV2Script() {
    DefaultRedisScript<Long> script = new DefaultRedisScript<>();
    script.setLocation(
        new ClassPathResource("redis/scripts/reserve-stock-v2.lua")
    );
    script.setResultType(Long.class);
    return script;
}
~~~

Khi có hai bean cùng kiểu `RedisScript<Long>`, **phải chỉ định rõ bean được tiêm**, ví dụ `@Qualifier("reserveStockV1Script")` hoặc dùng tên tham số với cấu hình injection phù hợp. Không để lựa chọn script ngầm phụ thuộc vào may rủi khi Spring tìm bean.

Ví dụ:

~~~java
public InventoryReservationService(
        StringRedisTemplate redis,
        @Qualifier("reserveStockV1Script")
        RedisScript<Long> script) {
    this.redis = redis;
    this.reserveStockV1 = script;
}
~~~

Thay vì cho controller trực tiếp nhận `v1`/`v2`, có thể xây một adapter lựa chọn implementation theo cấu hình triển khai. Nếu dùng feature flag, cần bảo đảm cả hai phiên bản cùng tuân thủ contract dữ liệu trong thời gian rollout.

### Version script trong log/metric

Nên ghi thông tin như:

~~~text
redis_script_name=reserve-stock
redis_script_contract=v1
redis_result_code=1
redis_duration_ms=2.3
application_release=2026.11.13
~~~

Thông tin này hữu ích khi lỗi chỉ xảy ra ở một release hoặc một nhóm instance. Không log đầy đủ dữ liệu nhạy cảm trong `ARGV` như token, email, thông tin thanh toán; chỉ giữ correlation ID đã được bảo vệ và metadata đủ chẩn đoán.

## 19. Redis Lua script và Redis Functions khác nhau thế nào?

Ngoài `EVAL`/`EVALSHA`, các phiên bản Redis hiện đại hỗ trợ **Redis Functions**, quản lý những thư viện function có tên và gọi qua `FCALL` hoặc `FCALL_RO` khi phù hợp.

So sánh định hướng:

| Tiêu chí | Lua script truyền thống | Redis Functions |
| --- | --- | --- |
| Gọi thực thi | `EVAL`, `EVALSHA` | `FCALL`, `FCALL_RO` |
| Danh tính thực thi | Nội dung script/SHA | Tên function trong library |
| Nguồn triển khai | Có thể đóng gói cùng Spring application | Cần triển khai và quản lý library trên Redis |
| Cache/nạp mã | Cơ chế script cache và fallback | Cơ chế quản lý function library riêng |
| Nâng cấp | Mã Java + resource + SHA mới | Cần quy trình quản lý library và caller |
| Khi phù hợp | Ít script ngắn, caller đóng gói cùng app | Nhiều function dùng chung, muốn vận hành library như thành phần server |

Redis Functions không tự loại bỏ yêu cầu kiểm thử, version contract, schema migration hoặc xử lý đồng thời. Đây là lựa chọn kiến trúc bổ sung, **không phải lý do để trộn các API Functions và EVALSHA tùy ý**.

Nếu đang dùng `RedisScript` của Spring Data Redis, ví dụ hiện tại đi theo con đường scripting truyền thống. Khi chuyển sang Redis Functions, cần thiết kế lại cách triển khai và gọi functions tương ứng với phiên bản client/server.

## 20. Hiệu năng và giới hạn thời gian chạy script

Lua script chạy bên trong Redis. Khi script thực thi quá lâu, nó có thể cản trở Redis phục vụ các lệnh khác. Do đó, script không nên:

- Quét toàn bộ keyspace bằng `KEYS *`.
- Lặp không giới hạn dựa vào dữ liệu do client điều khiển.
- Gọi hàng chục nghìn lệnh Redis trong một request không kiểm soát.
- Parse payload khổng lồ hoặc tạo Lua table rất lớn.
- Kết hợp các tác vụ không liên quan chỉ vì "một EVAL là atomic".
- Thực hiện tính toán phức tạp vốn phù hợp hơn ở tầng ứng dụng.

Redis có cơ chế cảnh báo script chạy quá thời gian cấu hình, nhưng **không nên xem timeout của client là cơ chế hủy an toàn**. Một request Java timeout không chứng minh Redis chưa thực hiện script.

Đặc biệt, `SCRIPT KILL` có giới hạn khi script đã thực hiện ghi dữ liệu. Vì thế không nên xây quy trình production phụ thuộc vào việc có thể hủy mọi script đang chạy mà không ảnh hưởng trạng thái.

### Mẫu thiết kế tốt

~~~text
Java validate input
       |
       v
EVAL script ngắn:
  đọc một ít key/field
  kiểm tra
  cập nhật có giới hạn
  return code
       |
       v
Java xử lý nghiệp vụ tiếp theo
~~~

Với nhiệm vụ cần quét hàng triệu ID hoặc làm việc qua nhiều hệ thống, nên tách thành worker/batch. Lua phù hợp cho **một đoạn critical section ngắn** ở Redis, không phải một workflow engine.

## 21. Retry, timeout và idempotency khi vận hành

Một script ngắn vẫn có thể gặp:

- Mất kết nối trước khi Redis nhận lệnh.
- Redis đã chạy script nhưng kết quả phản hồi bị mất.
- Failover khiến client không biết chính xác lệnh đã hoàn thành hay chưa.
- Retry tự động ở tầng client hoặc service.
- Hai request có cùng ID chạy gần như đồng thời.

Trạng thái "không nhận được response" không đủ để kết luận script không chạy. Vì vậy:

1. Tạo `reservationId` ổn định cho cùng một nghiệp vụ.
2. Đưa ID vào contract script.
3. Lưu dấu hiệu đã xử lý trong cùng thao tác Redis quan trọng.
4. Khi retry, dùng **cùng ID và cùng các thông số quyết định**.
5. Nếu nhận mã xung đột, điều tra thay vì tự động đổi ID rồi thử lại.

Trong ví dụ v1:

~~~text
Lần 1:
  reserve(sku-42, r-101, 3)
  Redis ghi thành công nhưng client timeout.

Lần 2:
  reserve(sku-42, r-101, 3)
  Redis thấy reservation:r-101 = 3
  -> trả 2, không trừ kho nữa.
~~~

Nếu caller sinh ID mới cho lần retry, cơ chế này không còn bảo vệ khỏi trừ trùng.

### Idempotency chỉ có giá trị trong vòng đời dữ liệu

Nếu Redis Hash bị xóa hoặc hết TTL, dấu hiệu `reservation:r-101` biến mất. Retry với cùng ID ở một inventory Hash mới có thể được hiểu như request mới. Nghiệp vụ quan trọng cần định nghĩa **thời hạn lưu idempotency record** và nguồn sự thật về reservation.

Nếu có release, hoàn tiền, thanh toán hoặc ghi database khác, cần xử lý nhất quán xuyên hệ thống; script reserve chỉ đảm bảo đoạn cập nhật được thực hiện trong Redis.

## 22. Quan sát và xử lý lỗi khi script được triển khai

Khi script chạy lỗi, nên phân biệt:

| Loại lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Lỗi contract | Sai số KEYS/ARGV | Sửa caller, không retry vô hạn |
| Lỗi dữ liệu | `WRONGTYPE`, tồn kho không phải số | Dừng thao tác, điều tra dữ liệu |
| Hết hàng hợp lệ | Return `0` | Trả kết quả nghiệp vụ, không log như exception |
| Retry hợp lệ | Return `2` | Xem là yêu cầu đã được thực hiện |
| Xung đột idempotency | Return `-2` | Kiểm tra request bị reuse sai |
| Script cache miss | `NOSCRIPT` | Executor có fallback `EVAL`; không coi là lỗi dữ liệu |
| Timeout/kết nối | Mất phản hồi | Retry theo idempotency, quan sát trạng thái |
| Script chậm | Redis busy/latency tăng | Giảm độ phức tạp, cân nhắc tách tác vụ |

Giám sát nên có:

- Tên script và **contract version**.
- Số lần gọi, tỉ lệ thành công và mã kết quả.
- Độ trễ phía client và timeout.
- Số lượng lỗi serialization/command/WRONGTYPE.
- Mối tương quan giữa tăng tải script và độ trễ Redis.
- Các bất biến: tồn kho không âm, số reservation và lượng đã trừ tương ứng.
- Tỉ lệ retry và xung đột idempotency.

Không nên chỉ nhìn vào số lượng lỗi Java. Một script luôn trả mã `0` do dữ liệu bị nhập sai cũng có thể khiến API gần như không còn thành công, dù không có exception.

## 23. Lập kế hoạch phát hành v2

Giả sử cần thêm `expiresAt` cho reservation. Một phương án phát hành có thể gồm:

~~~text
Phase 1: Chuẩn bị
  - Định nghĩa contract v2 (ARGV bổ sung deadline).
  - Tạo reserve-stock-v2.lua.
  - Thêm test v2, test so sánh v1/v2 với schema chung.
  - Không thay đổi file v1.

Phase 2: Tương thích
  - Cập nhật tầng đọc/release để hiểu reservation cũ lẫn mới.
  - Bổ sung schema/metadata theo cách v1 vẫn có thể hoạt động.
  - Có phương án rollback.

Phase 3: Chuyển traffic
  - Deploy Java có cả v1 và v2.
  - Bật v2 cho một phần traffic.
  - Quan sát mã lỗi, latency và bất biến dữ liệu.
  - Mở rộng traffic khi ổn định.

Phase 4: Thu dọn
  - Xác nhận không còn caller v1 hoặc nhu cầu rollback.
  - Dọn mã, bean và resource v1 theo lịch.
  - Xử lý dữ liệu cũ còn tồn tại.
~~~

Quan trọng nhất: **test cả giai đoạn có hai release cùng chạy**. Nếu chỉ test v2 trong môi trường trống, có thể bỏ sót lỗi khi v2 đọc dữ liệu do v1 tạo, hoặc khi v1 xử lý dữ liệu mới.

### Tránh nâng version khi chưa có lý do

Không cần tạo v2 chỉ vì chỉnh một comment hoặc format. Tuy vậy, khi sửa code Lua trong file v1, source hash thay đổi và hành vi runtime có thể thay đổi giữa các bản ứng dụng. Quy trình review, test và rollout vẫn cần áp dụng tương ứng. Version naming phải tuân theo mức thay đổi contract, trong khi artifact/build version vẫn nhận diện từng lần phát hành mã nguồn.

## 24. Những sai lầm phổ biến

### Sai lầm 1: Nhúng Lua dài dưới dạng Java String

~~~java
String lua = "local x = redis.call('GET', KEYS[1]); ..."
           + "...";
~~~

Khi script dài, cách này khó diff, khó review và dễ hỏng quote/newline. Nếu có yêu cầu script cực ngắn, inline đôi khi chấp nhận được; với logic nghiệp vụ quan trọng nên dùng resource.

### Sai lầm 2: Xây tên Redis key từ ARGV bên trong script

~~~lua
local key = "inventory:" .. ARGV[1]
redis.call("GET", key)
~~~

Redis scripting yêu cầu các key được truy cập phải được khai báo thích hợp qua `KEYS`. Cách dựng key ngầm gây vấn đề đặc biệt ở Redis Cluster. Hãy xây key tại caller, truyền trong `KEYS` và truyền dữ liệu thường qua `ARGV`.

### Sai lầm 3: Tin rằng Lua tự rollback khi lỗi

Script atomic về interleaving, nhưng có thể để lại các thay đổi trước runtime error. Validate trước khi ghi và giảm bước ghi là biện pháp thiết kế chính.

### Sai lầm 4: Giả định EVALSHA luôn thành công sau lần preload

Cache script có thể biến mất vì restart, failover, flush hoặc chính sách cache. Dùng executor có fallback hoặc tự xử lý `NOSCRIPT` nếu quản lý ở tầng thấp.

### Sai lầm 5: Thay trực tiếp contract v1 bằng v2

Khi rolling deployment, caller cũ có thể vẫn đang gọi v1. Đổi số `ARGV` hoặc field schema đột ngột sẽ gây lỗi không đồng bộ. Duy trì hai phiên bản cho tới khi hoàn tất migration.

### Sai lầm 6: Chỉ test mã return, bỏ qua dữ liệu Redis

Một script có thể trả mã hợp lệ nhưng tạo field sai hoặc cập nhật thiếu dữ liệu. Test cần khẳng định các bất biến ở trạng thái Redis sau lệnh.

### Sai lầm 7: Chỉ test bằng mock RedisTemplate

Mock chứng minh Java gọi đúng phương thức, nhưng không chạy Lua và không chứng minh tính nguyên tử. Dùng Redis thật cho integration test.

### Sai lầm 8: Retry với request ID mới

Mất response không chứng minh thao tác chưa xảy ra. ID mới sẽ làm hệ thống có thể giữ kho lần nữa. Giữ idempotency key ổn định qua retry.

### Sai lầm 9: Coi script là nơi thực hiện mọi workflow

Lua giữ Redis bận khi đang chạy; không nên dùng nó để quét dữ liệu lớn hoặc thực hiện việc nhiều bước, mất nhiều thời gian. Logic gọi dịch vụ ngoài cần chạy ở tầng ứng dụng/worker với cơ chế bền vững riêng.

### Sai lầm 10: Mọi key Cluster được ghép bất kỳ

Script đa key trong Redis Cluster chịu ràng buộc slot. Thiết kế hash tag có chủ đích và kiểm thử trên topology thực tế khi dùng Cluster.

## 25. Quy trình làm việc nhóm cho script Lua

Một vòng đời script rõ ràng có thể gồm:

**Khi tạo script mới**

1. Viết contract `KEYS`, `ARGV`, kiểu trả về, trạng thái dữ liệu và idempotency.
2. Đặt resource có tên ổn định và hậu tố version khi phù hợp.
3. Viết Lua ngắn, validate trước mutation.
4. Tạo `RedisScript<T>` bean có `resultType` rõ ràng.
5. Đặt lời gọi trong một service/adapter duy nhất.
6. Thêm integration tests trên Redis thật, gồm error và concurrency.
7. Kiểm tra compatibility với các release còn được hỗ trợ.
8. Theo dõi script/version/result trong metrics sau deploy.

**Khi sửa một script đang dùng**

1. Xác định thay đổi chỉ ở implementation hay phá contract.
2. Nếu phá contract, tạo v2 và chiến lược chuyển đổi.
3. Thử dữ liệu do bản cũ tạo và dữ liệu do bản mới tạo.
4. Thử chạy đồng thời phiên bản ứng dụng cũ/mới.
5. Đặt ngưỡng quan sát và phương án rollback cụ thể.
6. Chỉ bỏ v1 khi hết caller và dữ liệu liên quan đã được xử lý.

**Khi Redis gặp restart/failover**

Ứng dụng vẫn phải lấy script từ resource và có đường fallback khi cache miss. Không cần rebuild JAR chỉ để nạp lại một SHA đã mất; đó là trách nhiệm của cơ chế script execution thích hợp.

## 26. Bài tập mở rộng

### Bài tập A: Release reservation

Thiết kế `release-reservation-v1.lua` nhận:

~~~text
KEYS[1] = inventory hash
ARGV[1] = reservationId
~~~

Yêu cầu:

- Nếu reservation tồn tại, cộng lại đúng quantity vào `available` và loại field reservation.
- Nếu request release lặp, trả mã riêng và **không cộng hai lần**.
- Không làm available âm hoặc vượt quy tắc nghiệp vụ.
- Kiểm thử request release đồng thời.

Lưu ý: nếu release dùng hai lệnh ghi (`HINCRBY` và `HDEL`), cần hiểu nguy cơ partial writes khi xảy ra lỗi script; có thể tính toán trước rồi dùng lệnh ghi phù hợp, hoặc thiết kế lại representation để giảm rủi ro.

### Bài tập B: Nâng contract lên v2

Thêm `deadline` cho mỗi reservation và thiết kế cách đọc metadata này mà không phá v1. Viết bảng tương thích giữa app v1/v2 và dữ liệu trước/sau migration.

### Bài tập C: Khôi phục sau timeout

Dùng một lớp wrapper mô phỏng việc client mất response sau khi Redis đã thực thi. Gọi lại với cùng ID và xác minh tồn kho chỉ giảm một lần. So sánh với trường hợp retry bằng ID khác.

### Bài tập D: Kiểm tra Redis Cluster

Thiết kế một script dùng hai key `inventory:{sku-42}:state` và `inventory:{sku-42}:audit`. Giải thích vì sao cùng hash slot và điều gì xảy ra nếu chuyển key thứ hai sang `inventory:{sku-99}:audit`.

### Bài tập E: Tối ưu script dài

Một script cũ quét hàng nghìn member và làm nhiều phép kiểm tra cho mỗi request. Tách thuật toán thành bước Java/worker xử lý batch và một script ngắn chỉ thực hiện critical section cuối cùng; so sánh latency khi chạy dưới tải.

## 27. Tài liệu tham khảo chính thức

- [Spring Data Redis – Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis – RedisScript API](https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/core/script/RedisScript.html)
- [Spring Data Redis – DefaultRedisScript API](https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/core/script/DefaultRedisScript.html)
- [Redis – Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/)
- [Redis – EVAL](https://redis.io/docs/latest/commands/eval/)
- [Redis – EVALSHA](https://redis.io/docs/latest/commands/evalsha/)
- [Redis – SCRIPT LOAD](https://redis.io/docs/latest/commands/script-load/)
- [Redis – Redis Functions](https://redis.io/docs/latest/develop/programmability/functions-intro/)
- [Redis – Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)

## 28. Tổng kết

Một Lua script production trong Spring Data Redis cần được quản lý như **một phần của API và dữ liệu**, không chỉ là một đoạn code gửi đến Redis:

- **Đóng gói:** lưu file trong `src/main/resources`, khai báo `DefaultRedisScript`, để caller sử dụng service có contract rõ ràng.
- **Tính nguyên tử:** các lệnh Redis khác không chen vào giữa script; nhưng lỗi sau khi đã ghi **không tự rollback**.
- **Kiểm thử:** chạy Redis thật, khẳng định trạng thái sau thao tác, tình huống lỗi, retry và cạnh tranh đồng thời.
- **Quản lý cache:** `EVALSHA` có thể gặp `NOSCRIPT`; script source phải có trong artifact để fallback.
- **Quản lý phiên bản:** v1/v2 phục vụ tương thích contract, còn SHA dùng nhận dạng nội dung; rolling deployment đòi hỏi v1 và v2 cùng hoạt động trên dữ liệu chung trong thời gian chuyển đổi.
- **Vận hành:** giữ script ngắn, đo latency, bảo vệ idempotency, cân nhắc Redis Cluster và giữ khả năng rollback.

Khi làm đúng các bước này, Lua trở thành một công cụ có thể kiểm soát và bảo trì để bảo vệ critical section trong Redis, đồng thời giúp ứng dụng Spring Boot thay đổi phiên bản mà không làm đứt hợp đồng dữ liệu với Redis.

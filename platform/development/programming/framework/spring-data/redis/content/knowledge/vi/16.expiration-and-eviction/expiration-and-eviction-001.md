# Thiết lập TTL khi tạo khóa và khi cập nhật khóa trong Spring Data Redis

**TTL (Time To Live)** là khoảng thời gian còn lại trước khi một **Redis key** hết hạn. TTL được dùng rộng rãi trong cache, OTP, phiên đăng nhập, idempotency key, bộ đếm giới hạn truy cập và dữ liệu tạm. Việc hiểu chính xác TTL giúp tránh hai lỗi trái ngược:

- **Dữ liệu sống quá lâu** vì ứng dụng tạo key rồi quên đặt hạn, hoặc cập nhật bằng một lệnh xóa TTL cũ.
- **Dữ liệu hết hạn quá sớm hoặc bị gia hạn ngoài ý muốn** vì một lần cập nhật đặt lại TTL, trong khi nghiệp vụ cần giữ thời hạn ban đầu.

Trong **Spring Data Redis**, TTL có thể được thiết lập qua `StringRedisTemplate`, `RedisTemplate`, Spring Cache hoặc metadata của Redis Repository. Mỗi đường lưu có ngữ nghĩa riêng. Không nên suy luận rằng “mọi lệnh ghi đều reset TTL” hoặc “mọi lệnh ghi đều giữ nguyên TTL”.

Ý chính của bài:

> **TTL thuộc về Redis key, không phải về object Java.** Khi tạo key, nên ghi dữ liệu cùng thời hạn trong **một thao tác Redis** nếu có thể. Khi cập nhật, cần chọn rõ: giữ TTL đang có, gia hạn từ hiện tại, đặt deadline cố định hay xóa TTL.

## 1. TTL hoạt động ở tầng nào?

Redis lưu dữ liệu dưới nhiều kiểu: String, Hash, List, Set, Sorted Set, Stream... Với cơ chế `EXPIRE` thông dụng, Redis quản lý **thời hạn cho toàn bộ key**.

Ví dụ:

```text
Redis database
│
├── otp:request-01           string        TTL = 120 giây
├── cache:product:sku-42     string        TTL = 600 giây
├── cart:customer-7          hash          TTL = 1800 giây
├── queue:pending            list          TTL = -1 (không có hạn)
└── ranking:weekly           sorted set    TTL = -1 (không có hạn)
```

`EXPIRE cart:customer-7 1800` đặt thời hạn cho **cả Redis hash** mang key `cart:customer-7`. Nó không chỉ làm hết hạn một field bên trong hash. Một số phiên bản Redis mới có cơ chế hết hạn cấp hash field riêng, nhưng đó là một nhóm lệnh và mô hình khác với TTL key đang được trình bày.

### 1.1. TTL là thời gian còn lại, không phải thời điểm tạo

Nếu tạo key với TTL 300 giây lúc 10:00:00, Redis dự kiến key hết hạn quanh 10:05:00. Sau 40 giây, TTL còn khoảng 260 giây. Redis không gắn khái niệm “cache” hay “OTP” vào key; thời hạn là metadata do ứng dụng đặt.

Các thời điểm có thể được điều khiển theo hai cách:

| Cách thiết lập | Ví dụ | Cách hiểu |
|---|---|---|
| **Thời gian tương đối** | `EXPIRE key 300` | Hết hạn sau khoảng 300 giây tính từ khi lệnh có hiệu lực |
| **Thời điểm tuyệt đối** | `EXPIREAT key <unix-seconds>` | Hết hạn tại một thời điểm Unix xác định |

Redis thực thi expiration bằng cơ chế kiểm tra khi truy cập và dọn các key đã quá hạn trong nền. Vì vậy, thời điểm bộ nhớ vật lý được thu hồi hoặc thời điểm nhận được expiration notification không nhất thiết trùng chính xác từng mili giây với deadline. Tuy nhiên, một key đã hết hạn không được coi là dữ liệu còn hợp lệ để trả về cho các lệnh đọc thông thường.

### 1.2. Phân biệt TTL và eviction

**Expiration** xảy ra khi thời hạn key đã hết. **Eviction** xảy ra khi Redis phải loại dữ liệu theo giới hạn bộ nhớ và chính sách `maxmemory-policy`. Một key có TTL 30 phút vẫn có thể bị eviction trước 30 phút nếu server thiếu bộ nhớ và policy cho phép.

Vì thế TTL **không bảo đảm key tồn tại đủ thời lượng**, mà xác định thời hạn tối đa theo cơ chế hết hạn; ứng dụng phải xử lý cache miss hoặc trạng thái không còn key.

## 2. Quan sát TTL bằng Redis CLI

Hai lệnh kiểm tra phổ biến:

```redis
TTL key
PTTL key
```

`TTL` trả về **số giây**; `PTTL` trả về **số mili giây** còn lại.

| Kết quả | Ý nghĩa |
|---|---|
| Số không âm | Thời hạn còn lại theo đơn vị của lệnh, có thể gần 0 khi sắp hết hạn |
| `-1` | Key tồn tại **nhưng không có thời hạn** |
| `-2` | Key **không tồn tại** (bao gồm trường hợp đã hết hạn) |

Ví dụ:

```redis
SET demo:ttl "hello" EX 120
TTL demo:ttl
# Thường gần 120, giảm theo thời gian

PTTL demo:ttl
# Thường gần 120000, giảm theo thời gian

PERSIST demo:ttl
TTL demo:ttl
# (integer) -1

DEL demo:ttl
TTL demo:ttl
# (integer) -2
```

**Đừng hiểu `TTL = -1` là “đã hết hạn”.** Nó có nghĩa ngược lại: key đang tồn tại mà **không có TTL**. `-2` mới thể hiện key không tồn tại.

Trong thời điểm nhiều client cùng cập nhật, TTL nhìn thấy là **ảnh chụp tại một lần gọi**, không phải cam kết rằng giá trị đó còn nguyên ngay sau khi lệnh hoàn thành.

## 3. Thiết lập TTL ngay khi tạo Redis String

### 3.1. `SET` với `EX` hoặc `PX`

Redis hỗ trợ đặt giá trị và thời hạn trong cùng một lệnh:

```redis
SET otp:request-01 "482913" EX 120
SET cache:product:sku-42 "{\"id\":\"sku-42\"}" EX 600
SET temp:lock:job-7 "owner-123" PX 15000
```

Ý nghĩa:

- `EX 120`: TTL 120 **giây**.
- `PX 15000`: TTL 15.000 **mili giây**.
- Nếu không có `EX`/`PX`/tùy chọn thời hạn khác, `SET key value` tạo một key không có TTL.
- `SET ... EX/PX` là **một lệnh**: giá trị mới và thời hạn được thiết lập cùng một thao tác Redis.

Đặt TTL ngay lúc tạo đặc biệt hữu ích cho OTP hoặc dữ liệu bảo mật tạm thời: tránh khoảng hở giữa hai lệnh riêng lẻ.

### 3.2. Vì sao `SET` rồi `EXPIRE` có thể rủi ro?

Mẫu hai lệnh:

```redis
SET otp:request-02 "731204"
EXPIRE otp:request-02 120
```

có một khoảng thời gian khi key đã được ghi nhưng **chưa có hạn**. Nếu ứng dụng chết, mất mạng hoặc gặp exception giữa hai lệnh, key có thể sống vô hạn.

```text
Ứng dụng                           Redis
   │                                 │
   ├──── SET otp:... ───────────────►│ Ghi key chưa có TTL
   │◄── OK ──────────────────────────┤
   │
   X process chết
   │
   └── EXPIRE ... KHÔNG ĐƯỢC GỬI

Kết quả: key vẫn tồn tại nhưng TTL = -1
```

Đối với **Redis String**, hãy ưu tiên `SET key value EX seconds` hoặc API Spring Data Redis tương đương để có thao tác ghi-kèm-hạn nguyên tử.

### 3.3. Tạo key chỉ khi chưa tồn tại: `NX`

Lệnh:

```redis
SET otp:request-01 "482913" EX 120 NX
```

chỉ tạo key nếu key **chưa tồn tại**. Nếu key đã tồn tại, Redis không ghi đè giá trị và không thiết lập lại TTL bằng lần gọi thất bại đó.

Khi một ứng dụng cần “đăng ký idempotency key một lần” hoặc “chiếm một key tạm”, nên dùng điều kiện `NX` kết hợp TTL trong **cùng lệnh**. Cần lưu ý một key lock chỉ là một phần của giao thức khóa phân tán; việc đặt `NX EX` không tự giải quyết ownership, unlock an toàn, fencing và mọi vấn đề hết hạn trong quá trình xử lý dài.

### 3.4. Cập nhật chỉ khi key đã tồn tại: `XX`

```redis
SET otp:request-01 "902184" EX 120 XX
```

`XX` chỉ cập nhật nếu key còn tồn tại. Nếu key đã hết hạn hoặc bị xóa, lệnh không tạo một key mới. Khi thành công, nó **đặt lại TTL** theo `EX 120` từ lần cập nhật đó.

| Lệnh | Khi key chưa tồn tại | Khi key đã tồn tại |
|---|---|---|
| `SET key v EX 120` | Tạo key, TTL 120s | Ghi đè value, đặt lại TTL 120s |
| `SET key v EX 120 NX` | Tạo key, TTL 120s | Không thay đổi value/TTL |
| `SET key v EX 120 XX` | Không tạo key | Ghi đè value, đặt lại TTL 120s |
| `SET key v` | Tạo key không TTL | Ghi đè value, thường **xóa TTL cũ** |

Các câu lệnh có điều kiện rất hữu ích, nhưng **không phải CAS tổng quát** theo nội dung cũ. `XX` chỉ kiểm tra sự tồn tại, không kiểm tra value hay version có đúng kỳ vọng nghiệp vụ không.

## 4. TTL khi cập nhật khóa: không phải lệnh ghi nào cũng giống nhau

Đây là phần quan trọng nhất khi làm việc với Spring Data Redis.

### 4.1. `SET` thông thường làm mất TTL cũ

```redis
SET demo:update "v1" EX 300
TTL demo:update
# Gần 300

SET demo:update "v2"
TTL demo:update
# (integer) -1
```

Lệnh `SET key value` ghi đè toàn bộ giá trị Redis String và **loại bỏ expiration đang có**, trừ khi sử dụng tùy chọn giữ TTL hoặc thiết lập thời hạn mới trong cùng lệnh.

Điều này dễ xảy ra nếu code ban đầu:

```java
redis.opsForValue().set(key, value, Duration.ofMinutes(5));
```

nhưng sau đó một đường cập nhật khác lại dùng:

```java
redis.opsForValue().set(key, updatedValue);
```

Kết quả: key có thể chuyển từ TTL 5 phút sang **không còn TTL**, làm cache tồn tại lâu hơn dự kiến.

### 4.2. `SET ... EX/PX` đặt lại TTL từ thời điểm cập nhật

```redis
SET demo:update "v1" EX 300
# Sau khoảng 120 giây, TTL còn gần 180

SET demo:update "v2" EX 300
TTL demo:update
# Gần 300 — TTL đã được làm mới
```

Đây là kiểu **refresh TTL on write**. Nó phù hợp khi mỗi lần cập nhật dữ liệu cần kéo dài thời gian sống thêm 300 giây tính từ lần cập nhật cuối.

Nhưng nếu nghiệp vụ là “OTP chỉ có hiệu lực tối đa 5 phút kể từ lần phát đầu tiên”, cập nhật lại value bằng `SET ... EX 300` có thể **gia hạn trái quy định**. Cần chọn chính sách thời hạn dựa trên nghiệp vụ.

### 4.3. `SET ... KEEPTTL` giữ thời hạn đang có

Redis hỗ trợ:

```redis
SET demo:update "v1" EX 300
SET demo:update "v2" KEEPTTL

TTL demo:update
# TTL vẫn đang đếm xuống từ lần SET đầu tiên
```

`KEEPTTL` yêu cầu Redis **giữ nguyên expiration của key hiện có** khi thay giá trị bằng `SET`. Nếu key chưa tồn tại, không có TTL cũ để giữ; key mới được tạo theo lệnh `SET ... KEEPTTL` sẽ không tự có thời hạn.

Đừng sử dụng `KEEPTTL` mà kỳ vọng tạo một key mới luôn có TTL mặc định. Nếu cần bất biến “mọi key đều phải có hạn”, đường tạo key phải có cơ chế đặt hạn rõ ràng.

### 4.4. Lệnh cập nhật tại chỗ thường giữ TTL

Các lệnh thay đổi **nội dung của key đã tồn tại** mà không thay thế toàn bộ key, chẳng hạn `INCR`, `HSET`, `LPUSH`, `ZADD` hoặc `APPEND`, thông thường **không xóa TTL đang có**.

Ví dụ:

```redis
SET demo:counter 10 EX 120
INCR demo:counter
TTL demo:counter
# Vẫn còn TTL, tiếp tục đếm xuống
```

Ví dụ Redis Hash:

```redis
HSET demo:profile name "An"
EXPIRE demo:profile 600
HSET demo:profile city "Hanoi"
TTL demo:profile
# Còn TTL từ lệnh EXPIRE đầu; HSET không tự refresh
```

Lưu ý quan trọng: nếu `HSET`/`LPUSH`/`ZADD` **tạo một key hoàn toàn mới**, key đó **không tự được gắn TTL** chỉ vì loại dữ liệu là Hash/List/ZSet. Khi khởi tạo một cấu trúc mới, ứng dụng phải đặt TTL riêng hoặc dùng một cơ chế kết hợp lệnh phù hợp.

| Thao tác Redis | Trên key đã có TTL | Khi tạo key mới |
|---|---|---|
| `SET key v` | Xóa TTL cũ | Không có TTL |
| `SET key v EX 60` | Đặt TTL mới 60s | TTL 60s |
| `SET key v KEEPTTL` | Giữ TTL còn lại | Không tự có TTL |
| `INCR key` | Thường giữ TTL | Key counter mới không tự có TTL |
| `APPEND key suffix` | Thường giữ TTL | Key String mới không tự có TTL |
| `HSET key field value` | Thường giữ TTL của hash | Hash mới không tự có TTL |
| `LPUSH`/`RPUSH` | Thường giữ TTL của List | List mới không tự có TTL |
| `SADD` | Thường giữ TTL của Set | Set mới không tự có TTL |
| `ZADD`/`ZINCRBY` | Thường giữ TTL của ZSet | ZSet mới không tự có TTL |
| `EXPIRE key 60` | Gán hoặc thay TTL | Không tạo key nếu key không tồn tại |
| `PERSIST key` | Gỡ TTL | Không tạo key nếu key không tồn tại |
| `DEL key` | Xóa hẳn key và metadata TTL | Không có key để giữ TTL |

“Giữ TTL” trong bảng nghĩa là **không chủ động làm mới deadline**, không phải TTL ngừng giảm theo thời gian.

## 5. Dùng `EXPIRE` và các lệnh liên quan để đặt lại hạn

### 5.1. `EXPIRE` và `PEXPIRE`

```redis
EXPIRE demo:key 300
PEXPIRE demo:key 1500
```

- `EXPIRE key seconds` đặt thời hạn tương đối bằng **giây**.
- `PEXPIRE key milliseconds` đặt thời hạn tương đối bằng **mili giây**.
- Lệnh có hiệu lực với key đã tồn tại, bất kể key là String, Hash, List, Set hay Sorted Set.
- Nếu key không tồn tại, Redis không tạo key; kết quả cho biết không đặt được expiration.
- Thời hạn bằng 0 hoặc âm có thể khiến key bị xóa ngay, không phải một cấu hình “không hết hạn”. Với ứng dụng, nên validate `Duration` dương trước khi gọi.

Ví dụ:

```redis
SET demo:manual "hello"
TTL demo:manual
# -1

EXPIRE demo:manual 60
TTL demo:manual
# Gần 60

EXPIRE demo:manual 180
TTL demo:manual
# Gần 180 — thay thời hạn cũ
```

`EXPIRE` hữu ích khi key đã được tạo bằng lệnh không hỗ trợ TTL đồng thời, nhưng hai thao tác riêng lẻ `create → EXPIRE` cần được xem xét về tính nguyên tử.

### 5.2. `EXPIREAT`, `PEXPIREAT` và deadline tuyệt đối

Nếu một phiên chỉ được hợp lệ đến **cùng một deadline**, bất kể có bao nhiêu lần cập nhật, có thể đặt expiration bằng Unix timestamp:

```redis
EXPIREAT demo:session 1893456000
PEXPIREAT demo:session 1893456000000
```

Các số ở ví dụ là timestamp Unix minh họa, không phải mốc thời gian nghiệp vụ cố định. Dạng giây/mili giây tương ứng với hai lệnh.

Redis `SET` cũng hỗ trợ các tùy chọn deadline tuyệt đối như `EXAT`/`PXAT` trên những phiên bản Redis phù hợp:

```redis
SET demo:session "active" EXAT 1893456000
```

Nếu ứng dụng quản lý một mốc hết hạn rõ ràng (ví dụ mã khuyến mãi kết thúc lúc 23:59:59 UTC), deadline tuyệt đối tránh việc mỗi lần cập nhật tự tăng thêm một khoảng TTL tương đối.

**Cần lưu ý đồng hồ:** Expiration tuyệt đối dùng thời gian Unix; đồng hồ server, giá trị timestamp của ứng dụng và việc đồng bộ thời gian là một phần của tính đúng đắn. Khi dùng timestamp đã nằm trong quá khứ, key có thể hết hạn/xóa ngay.

### 5.3. Các tùy chọn điều kiện cho `EXPIRE`

Redis 7.0+ hỗ trợ những điều kiện:

| Điều kiện | Chỉ thay expiration khi... |
|---|---|
| `NX` | Key hiện chưa có expiration |
| `XX` | Key đã có expiration |
| `GT` | Expiration mới **muộn hơn** expiration hiện có |
| `LT` | Expiration mới **sớm hơn** expiration hiện có |

Ví dụ:

```redis
SET demo:deadline "active"
EXPIRE demo:deadline 300 NX
# Thành công nếu key chưa có TTL

EXPIRE demo:deadline 600 GT
# Chỉ gia hạn nếu deadline mới muộn hơn

EXPIRE demo:deadline 120 LT
# Chỉ rút ngắn nếu deadline mới sớm hơn
```

Khi so sánh với `GT`/`LT`, key **không có TTL** được xem như có thời hạn vô hạn. Vì vậy, `EXPIRE key 60 GT` không thể tự biến key vĩnh viễn thành key hết hạn; ngược lại `LT` có thể đặt một hạn hữu hạn ngắn hơn vô hạn.

Những tùy chọn này là khả năng của Redis Server; không phải mọi overload `RedisTemplate.expire(...)` đều biểu diễn trực tiếp tất cả điều kiện. Nếu cần, hãy sử dụng API lệnh được thư viện hỗ trợ ở version đang dùng hoặc một script thích hợp.

## 6. Spring Data Redis: tạo String có TTL trong một thao tác

Trong Spring Boot, `StringRedisTemplate` thường được tự cấu hình khi dependency và kết nối Redis đã sẵn sàng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Ví dụ `application.yml` cho Redis thử nghiệm:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

`StringRedisTemplate` giúp làm việc với key/value kiểu chuỗi UTF-8. Với các đối tượng Java khác, `RedisTemplate<K,V>` cần serializer tương ứng, nhưng ngữ nghĩa TTL ở Redis Server vẫn dựa trên key.

### 6.1. Tạo một key cùng TTL

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

StringRedisTemplate redis = /* Spring inject */;

redis.opsForValue().set(
    "cache:product:sku-42",
    "{\"name\":\"Keyboard\"}",
    Duration.ofMinutes(10)
);
```

Overload `set(key, value, Duration)` tương ứng thao tác ghi giá trị có thời hạn, tránh mẫu `set(key, value)` rồi `expire(key, timeout)`.

### 6.2. Tạo chỉ khi chưa có key

```java
Boolean created = redis.opsForValue().setIfAbsent(
    "idempotency:request-7",
    "IN_PROGRESS",
    Duration.ofMinutes(5)
);

if (Boolean.TRUE.equals(created)) {
    // Lượt này đã tạo được key; tiếp tục giao thức nghiệp vụ tương ứng.
} else {
    // Key đã tồn tại, hoặc không có kết quả tức thời trong execution context đặc biệt.
}
```

`setIfAbsent(key, value, Duration)` dùng ngữ nghĩa tương đương `SET ... NX EX/PX` ở mức Redis và thực hiện **kiểm tra sự tồn tại + ghi giá trị + TTL** trong một thao tác. Trong pipeline/transaction, nhiều thao tác Spring Data Redis có thể trả `null` vì kết quả được hoãn; không nên mặc nhiên đồng nhất `null` với “key đã tồn tại”.

Ví dụ dùng idempotency key chỉ minh họa **một bước chiếm key tạm**. Để bảo đảm request không thực thi side effect hai lần cần thêm quy ước trạng thái, xử lý khi timeout, thời điểm hoàn tất và logic idempotent của nghiệp vụ.

### 6.3. Cập nhật chỉ khi key còn tồn tại và đặt lại TTL

```java
Boolean updated = redis.opsForValue().setIfPresent(
    "cache:product:sku-42",
    "{\"name\":\"New Keyboard\"}",
    Duration.ofMinutes(10)
);

if (Boolean.TRUE.equals(updated)) {
    // Giá trị được cập nhật và TTL được đặt lại theo Duration đã chọn.
}
```

`setIfPresent(key, value, Duration)` tương ứng ngữ nghĩa điều kiện `XX`: chỉ cập nhật khi key tồn tại. **Không** dùng overload không có `Duration` nếu ý định là làm mới TTL, vì `SET` thành công mà không kèm TTL có thể làm mất TTL cũ.

### 6.4. Đặt TTL cho một key đã tồn tại

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

Boolean changed = redis.expire(
    "cache:product:sku-42",
    Duration.ofMinutes(10)
);

Long remainingSeconds = redis.getExpire(
    "cache:product:sku-42",
    TimeUnit.SECONDS
);

// remainingSeconds có thể >= 0, -1, -2 hoặc null ở execution context đặc biệt.
```

`redis.expire(key, duration)` có thể trả:

- `true`: Redis áp dụng lệnh thay thời hạn.
- `false`: ví dụ không áp dụng vì key không tồn tại.
- `null` trong một số ngữ cảnh kết quả được hoãn.

Đối với xử lý nghiệp vụ, nên dùng `Boolean.TRUE.equals(changed)` nếu cần xác nhận. **Không** hiểu `expire(...) == true` như bảo đảm key sẽ tồn tại đủ TTL: key vẫn có thể bị xóa, hết hạn, eviction hoặc ghi đè bởi client khác sau đó.

### 6.5. Xóa TTL để giữ key lâu dài

```java
Boolean persisted = redis.persist("cache:product:sku-42");
```

`persist(key)` tương ứng `PERSIST key`, loại bỏ expiration của key đang tồn tại. Đây là thao tác khác với kéo dài TTL. Với session/OTP/cache có chính sách bắt buộc hết hạn, việc gọi `persist` không chủ đích có thể gây lỗi retention nghiêm trọng.

## 7. Chính sách TTL khi cập nhật: ba kiểu thường gặp

### 7.1. Fixed TTL từ thời điểm tạo

**Mục tiêu:** Dữ liệu chỉ hợp lệ tối đa `T` kể từ lần tạo đầu tiên, dù có cập nhật nội dung.

Ví dụ: OTP có hạn tối đa 2 phút sau khi phát; thử nhập sai không được kéo dài hiệu lực.

```text
10:00:00   tạo OTP có TTL 120s
10:00:40   kiểm tra OTP, không reset TTL
10:01:20   cập nhật metadata, giữ TTL còn lại
10:02:00   hết hạn theo mốc ban đầu
```

Cách áp dụng:

- Tạo String bằng `SET ... EX 120`.
- Khi phải sửa String mà vẫn giữ deadline, dùng `SET ... KEEPTTL` hoặc chiến lược lưu phù hợp có kiểm soát.
- Nếu chỉ thay đổi một field của Redis Hash bằng `HSET`, TTL của hash đã tồn tại thường tiếp tục đếm xuống.
- Nếu hệ thống có deadline tuyệt đối, có thể dùng mốc thời gian đó làm nguồn sự thật và kiểm tra cả ở ứng dụng.

Không dùng `SET ... EX 120` cho mọi lần sửa nếu chính sách yêu cầu **không gia hạn**. Cần kiểm tra dữ liệu ban đầu, quyền cập nhật và race condition.

### 7.2. Refresh TTL on write

**Mục tiêu:** Mỗi lần ứng dụng cập nhật thành công, key được sống thêm `T` kể từ lần cập nhật.

Ví dụ: cache tính toán được làm mới sau mỗi lần sản phẩm thay đổi.

```text
10:00:00  SET EX 600   → deadline khoảng 10:10
10:06:00  SET EX 600   → deadline khoảng 10:16
10:12:00  SET EX 600   → deadline khoảng 10:22
```

Trong Spring:

```java
redis.opsForValue().set(key, newValue, Duration.ofMinutes(10));
```

Vì đây là một lệnh Redis, value mới và thời hạn được gắn nhất quán với lần ghi đó. Tuy nhiên, nó có thể **tạo key mới nếu key cũ đã hết hạn**; khi chỉ được phép cập nhật key còn tồn tại, dùng `setIfPresent(key, value, ttl)`.

### 7.3. Sliding expiration theo lần đọc

**Mục tiêu:** Gia hạn key khi được truy cập, ví dụ phiên đăng nhập được kéo dài khi người dùng còn hoạt động.

Nếu dùng:

```redis
GET session:user-42
EXPIRE session:user-42 1800
```

thì đây là **hai lệnh**. Giữa chúng, key có thể hết hạn, bị xóa hoặc được client khác cập nhật. Thậm chí `GET` không tìm thấy dữ liệu, nhưng một client khác tạo key mới trước `EXPIRE`, làm lệnh expire tác động tới key mới.

Redis 6.2+ hỗ trợ `GETEX` để **đọc value và thay TTL trong một lệnh**:

```redis
GETEX session:user-42 EX 1800
```

Nếu key tồn tại và là Redis String, Redis trả về value và làm mới thời hạn theo yêu cầu. Nếu key không tồn tại, lệnh trả nil và không tự tạo key.

Trong Spring Data Redis, các phiên bản hỗ trợ có phương thức:

```java
String sessionData = redis.opsForValue().getAndExpire(
    "session:user-42",
    Duration.ofMinutes(30)
);
```

API này tương ứng với hành vi đọc và đặt lại expiration. Cần kiểm tra version Spring Data Redis/Redis Server và serializer thực tế của dự án. **Không** gọi `getAndExpire` nếu nghiệp vụ chỉ yêu cầu đọc mà không được gia hạn.

Sliding expiration có chi phí: mỗi lượt đọc gia hạn hạn đều là thao tác **ghi metadata expiration**, có thể làm tăng lưu lượng lệnh thay đổi state và tác động tới replication/persistence tùy cấu hình. Với session hoạt động rất thường xuyên, có thể cần chính sách giảm tần suất refresh, nhưng nếu gộp lượt ghi phải chấp nhận độ chính xác thời điểm hết hạn phù hợp.

### 7.4. Fixed absolute deadline

**Mục tiêu:** Không gia hạn quá một mốc quy định, chẳng hạn chương trình hết hạn vào cuối ngày. Khi mọi lần cập nhật phải giữ cùng deadline, nên lưu/kiểm tra mốc đó ở lớp nghiệp vụ và dùng `expireAt(key, instant)` hoặc `SET ... EXAT/PXAT` khi phù hợp.

Ví dụ Spring:

```java
import java.time.Instant;

Instant deadline = Instant.parse("2030-01-01T00:00:00Z");
Boolean applied = redis.expireAt("promo:campaign-7", deadline);
```

`expireAt` đặt expiration theo mốc tuyệt đối trên key đã có. Nếu ứng dụng cần **tạo String và mốc tuyệt đối cùng một bước**, có thể sử dụng các tùy chọn `SET EXAT/PXAT` ở cấp Redis hoặc một đường API/command tương ứng; `set()` rồi `expireAt()` vẫn là hai lệnh riêng.

## 8. Redis Hash, List, Set, Sorted Set: tạo dữ liệu và TTL có thể là hai lệnh

`StringRedisTemplate.opsForValue().set(key, value, Duration)` giải quyết tốt trường hợp Redis String. Nhưng với một Hash mới:

```java
redis.opsForHash().put("cart:user-42", "itemCount", "3");
redis.expire("cart:user-42", Duration.ofMinutes(30));
```

thì `HSET` và `EXPIRE` là **hai thao tác Redis khác nhau**. Nếu crash xảy ra giữa chúng, Hash có thể bị bỏ lại không có TTL. Tương tự khi khởi tạo List bằng `LPUSH`, Set bằng `SADD` hay Sorted Set bằng `ZADD` rồi mới gắn `EXPIRE`.

### 8.1. Nếu Hash đã tồn tại và có TTL

```redis
HSET cart:user-42 itemCount "1"
EXPIRE cart:user-42 1800
HSET cart:user-42 itemCount "2"
TTL cart:user-42
# Còn thời hạn đã thiết lập, không tự trở về 1800
```

`HSET` cập nhật field mà không chủ động thay thời hạn của hash. Nếu chính sách là **refresh TTL khi cập nhật cart**, hãy gọi `EXPIRE` sau cập nhật, hoặc sử dụng một thao tác kết hợp khi yêu cầu atomic.

### 8.2. Dùng Lua script để ghi Hash và TTL trong một thao tác

Khi cần bảo đảm một Hash được cập nhật đồng thời với thời hạn, Redis Lua script là một lựa chọn:

```lua
-- KEYS[1] = key Hash
-- ARGV[1] = field
-- ARGV[2] = value
-- ARGV[3] = TTL tính bằng giây, đã được ứng dụng validate > 0
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
return redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
```

Script này giúp **không có lệnh từ client khác chen vào giữa `HSET` và `EXPIRE`**. Tuy nhiên, Redis Lua script không mang cơ chế rollback như transaction của cơ sở dữ liệu quan hệ nếu script thực thi một phần rồi gặp lỗi. Cần validate input và kiểu dữ liệu key, chuẩn bị xử lý exception; không đưa script chưa kiểm soát tài nguyên lên môi trường production.

Triển khai bằng Spring Data Redis:

```java
import java.time.Duration;
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class CartHashWriter {

    private static final String LUA = """
        redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
        return redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
        """;

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> script;

    public CartHashWriter(StringRedisTemplate redis) {
        this.redis = redis;
        this.script = new DefaultRedisScript<>();
        this.script.setScriptText(LUA);
        this.script.setResultType(Long.class);
    }

    public void writeWithTtl(
            String key,
            String field,
            String value,
            Duration ttl
    ) {
        if (ttl.isNegative() || ttl.isZero() || ttl.toSeconds() < 1) {
            throw new IllegalArgumentException("TTL must be >= 1 second");
        }

        Long result = redis.execute(
            script,
            List.of(key),
            field,
            value,
            Long.toString(ttl.toSeconds())
        );

        if (!Long.valueOf(1L).equals(result)) {
            throw new IllegalStateException("TTL could not be applied");
        }
    }
}
```

Trong ví dụ trên, `StringRedisTemplate` mã hóa key và arguments dưới dạng string; script trả về kết quả số nguyên của `EXPIRE`. Dùng cùng key và cùng đường serializer là điều kiện quan trọng. Khi số lượng tham số, kiểu key hoặc logic phức tạp, nên đóng gói script thành một thành phần có version và kiểm thử tích hợp riêng.

### 8.3. Redis transaction có giải quyết mọi thứ không?

Redis `MULTI`/`EXEC` có thể nhóm các lệnh, nhưng không phải giải pháp mặc định cho mọi yêu cầu:

- Khi cần bảo vệ logic phụ thuộc vào dữ liệu hiện tại, có thể còn cần `WATCH` hoặc Lua/Redis Function.
- Redis transaction không có rollback theo kiểu RDBMS khi một lệnh đã thực thi và phát sinh lỗi runtime.
- Trong Spring Data Redis, cấu hình transaction và connection binding cần được hiểu đúng; chỉ thêm `@Transactional` không tự biến mọi lệnh Redis thành một giao dịch đúng ý.
- Đối với khóa cần TTL và giá trị trong một thao tác, `SET EX/PX` thường đơn giản hơn ghép `SET` và `EXPIRE` bằng transaction.

Với một key cấu trúc Hash/List/ZSet cần update + TTL thống nhất, script có thể thể hiện ý định rõ; nhưng cần cân nhắc hiệu năng và khả năng bảo trì.

## 9. Bộ đếm có TTL: tránh mất hạn khi tạo mới

Redis thường được dùng làm bộ đếm giới hạn truy cập:

```redis
INCR rate-limit:user-42
EXPIRE rate-limit:user-42 60
```

Đây là hai lệnh riêng. Nếu application chết giữa hai thao tác, bộ đếm có thể tồn tại vĩnh viễn. Ngoài ra, nếu gọi `EXPIRE key 60` **sau mọi lần tăng**, mỗi request sẽ làm mới TTL, tạo hành vi khác với “cửa sổ 60 giây kể từ request đầu tiên”.

### 9.1. Phân biệt hai chiến lược

| Chiến lược | Cách đặt TTL | Hành vi |
|---|---|---|
| Fixed window đơn giản | Đặt TTL khi counter mới được tạo | Hết hạn khoảng 60 giây từ lần tạo counter |
| Refresh-on-increment | Đặt TTL sau mỗi lần tăng | Counter hết hạn nếu không có cập nhật thêm trong 60 giây |

Hai chiến lược **không giống** thuật toán sliding window rate limit chính xác. Để thực thi giới hạn truy cập nghiệp vụ đúng, cần xác định thuật toán, thời điểm bucket, giới hạn đồng thời và yêu cầu phân tán.

### 9.2. Lua: tạo/increment và gắn TTL theo một lệnh nguyên tử

Một script minh họa:

```lua
-- KEYS[1]: key bộ đếm
-- ARGV[1]: TTL giây > 0
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if count == 1 or ttl == -1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return count
```

Ý tưởng:

1. Tăng bộ đếm bằng `INCR`.
2. Khi counter mới đạt 1 hoặc phát hiện key tồn tại nhưng **không có TTL**, đặt hạn.
3. Những lượt tăng khác giữ thời hạn còn lại, không tự kéo dài fixed window.

Điều kiện `ttl == -1` là cơ chế phục hồi tình huống key không TTL (ví dụ dữ liệu cũ). Nó không phải định nghĩa trọn vẹn của rate limiter sản phẩm thật. Với rate limit cửa sổ lịch cố định, cần đưa bucket thời gian vào key, xác định TTL đến cuối cửa sổ và xử lý chênh lệch đồng hồ theo thiết kế.

**Lưu ý:** Số lượt tăng và việc lưu trạng thái chỉ là một phần bài toán giới hạn truy cập. Nếu request đã được xử lý ở hệ thống khác rồi retry, hoặc Redis failover mất một số cập nhật theo cấu hình persistence, cần xem xét mức độ bảo đảm mong muốn.

## 10. TTL trong Redis Cache của Spring

Khi dùng `@Cacheable` với `RedisCacheManager`, TTL thường được cấu hình ở cấp cache:

```java
import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class RedisCacheConfig {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory
    ) {
        RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10))
                .computePrefixWith(name -> "shop:v1:cache:" + name + "::");

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .build();
    }
}
```

Khi một cache entry được ghi qua Redis Cache, cache configuration quyết định TTL tương ứng. Nhưng cần hiểu:

- Một cache entry là dữ liệu Redis được lưu dưới key cache do CacheManager xây dựng.
- Khi entry được ghi lại, CacheManager có thể đặt thời hạn mới theo cấu hình `entryTtl`; không nên tự giả định ghi lại vẫn giữ TTL cũ.
- **`@Cacheable` cache hit** thường đọc cache entry hiện có và **không mặc nhiên làm mới TTL** theo kiểu sliding expiration.
- Nếu muốn TTL thay đổi theo entry hoặc theo thao tác đọc, cần kiểm tra khả năng cấu hình của Spring Data Redis version cụ thể (ví dụ TTL function hoặc time-to-idle emulation ở các phiên bản hỗ trợ) và đánh giá side effect.
- Serializer và prefix của `RedisCacheManager` có thể khác những gì một `RedisTemplate` riêng đang sử dụng.

### 10.1. Time-to-live và time-to-idle không giống nhau

| Khái niệm | Thời hạn tính từ |
|---|---|
| **TTL** | Lần ghi/thiết lập expiration gần nhất theo chính sách cache |
| **TTI (time to idle)** | Lần truy cập gần nhất, nếu hệ thống triển khai cơ chế làm mới khi đọc |

Một số phiên bản Spring Data Redis mới có khả năng mô phỏng time-to-idle bằng những lệnh như `GETEX`. Nhưng nếu ứng dụng trực tiếp dùng `RedisTemplate.opsForValue().get(...)` hoặc Redis CLI để đọc cùng key, các đường đọc khác nhau có thể không làm mới idle timeout như nhau. Cần thống nhất quyền sở hữu key và cơ chế đọc của cache.

### 10.2. Có nên xóa TTL khi cache được làm mới?

Nếu cache định giữ tối đa 10 phút, việc một service khác dùng `SET key value` không kèm TTL trên cùng key vật lý có thể chuyển entry thành key vĩnh viễn. Do đó:

- Không tự ghi đè raw key mà CacheManager đang quản lý nếu không có hợp đồng dữ liệu và serializer rõ ràng.
- Khi cần cập nhật cache entry, dùng `@CachePut` hoặc API `Cache.put` tương ứng và để CacheManager quản lý TTL.
- Với `@CacheEvict`, hiểu rõ phạm vi key bị xóa và cách tạo lại entry.
- Đừng dùng `PERSIST` để “khắc phục lỗi cache miss” nếu dữ liệu cache theo chính sách phải hết hạn.

## 11. TTL trong Spring Data Redis Repository

Redis Repository hỗ trợ metadata TTL trên entity được ánh xạ thành Redis Hash.

### 11.1. TTL cố định ở cấp kiểu entity

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "sessions", timeToLive = 1800)
public class SessionRecord {
    @Id
    private String id;
    private String userId;

    public SessionRecord() {}

    public SessionRecord(String id, String userId) {
        this.id = id;
        this.userId = userId;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
}
```

`timeToLive = 1800` biểu diễn TTL **1800 giây** cho aggregate được lưu. Khi repository save entity, Spring Data Redis có thể thiết lập thời hạn cho key chứa dữ liệu entity dựa trên metadata ánh xạ.

Ví dụ:

```java
SessionRecord saved = repository.save(
    new SessionRecord("session-42", "user-7")
);

// Keyspace mặc định theo annotation, ví dụ:
// sessions:session-42
```

Khi gọi `save` lại, cần hiểu cơ chế persist của repository có thể **thiết lập lại TTL theo cấu hình của entity**. Không dùng repository `save` như một thao tác “chỉ sửa một field và giữ TTL cũ” nếu chính sách nghiệp vụ cần fixed deadline mà chưa kiểm tra đường mapping/update.

### 11.2. TTL động theo entity với `@TimeToLive`

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("sessions")
public class SessionWithTtl {
    @Id
    private String id;

    private String userId;

    @TimeToLive
    private Long ttlSeconds;

    public SessionWithTtl() {}

    public SessionWithTtl(String id, String userId, Long ttlSeconds) {
        this.id = id;
        this.userId = userId;
        this.ttlSeconds = ttlSeconds;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
    public Long getTtlSeconds() { return ttlSeconds; }
    public void setTtlSeconds(Long ttlSeconds) { this.ttlSeconds = ttlSeconds; }
}
```

Với một kiểu số `Long`, giá trị `ttlSeconds` biểu diễn số giây theo cơ chế mapping TTL. Khi cần TTL khác nhau cho mỗi entity, metadata này linh hoạt hơn cấu hình cố định ở `@RedisHash`.

**Lưu ý khi đọc rồi save:** Giá trị TTL khi repository materialize entity có thể phản ánh **thời gian còn lại** của key, tùy cách ánh xạ và cấu hình. Nếu ứng dụng dùng lại object rồi `save`, hãy xác định rõ mong muốn giữ deadline hay refresh TTL; tránh vô tình nạp lại một giá trị TTL gốc và kéo dài session.

### 11.3. Repository có thể có key phụ

Redis Repository có thể quản lý tập ID, secondary index và các key khác liên quan đến mapping/expiration. TTL của aggregate **không có nghĩa mọi key phụ sẽ đồng loạt có cùng TTL** hoặc luôn được dọn ngay khi key hết hạn. Việc xử lý keyspace notifications và expiration events chịu ảnh hưởng cấu hình listener và vận hành Redis.

Nếu yêu cầu đồng bộ index nghiêm ngặt hoặc cần đảm bảo xóa dữ liệu theo chính sách retention, phải hiểu mô hình repository đang dùng, không chỉ dựa vào `TTL sessions:id`.

## 12. Thay TTL khi chỉ cập nhật một phần dữ liệu

Trong một hệ thống thực tế, các thao tác cập nhật thường rơi vào ba trường hợp:

### Trường hợp A — Cập nhật toàn bộ Redis String

Ứng dụng có thể dùng:

```java
redis.opsForValue().set(key, newJson, Duration.ofMinutes(10));
```

Điều này **ghi đè toàn bộ value và refresh TTL**. Nếu muốn giữ TTL còn lại, có thể dùng Redis `SET ... KEEPTTL` qua API/command phù hợp, hoặc một chiến lược atomic đã thiết kế. Không mặc nhiên thay bằng `set(key, value)` vì sẽ bỏ TTL.

### Trường hợp B — Cập nhật field trong Redis Hash

```java
redis.opsForHash().put(key, "status", "PAID");
```

Nếu Hash đã có expiration, TTL tiếp tục giảm. Nếu Hash chưa tồn tại, lệnh có thể tạo Hash mới **không có TTL**.

Khi muốn refresh TTL sau mỗi lần update:

```java
redis.opsForHash().put(key, "status", "PAID");
redis.expire(key, Duration.ofDays(1));
```

Hai lệnh này không atomic với nhau. Khi yêu cầu một trạng thái TTL bất biến, dùng script hoặc workflow đồng thời thích hợp.

### Trường hợp C — Cập nhật bộ đếm

```java
Long views = redis.opsForValue().increment("views:product:42");
```

`INCR` giữ TTL đã gắn trên key. Nhưng nếu counter mới được tạo bởi `INCR`, key sẽ không tự có TTL. Điều này khác với `SET ... EX` và là lý do bộ đếm theo cửa sổ thời gian thường cần script hoặc một key schema theo bucket có expiration được quản lý rõ.

## 13. Bài toán đồng thời và các ranh giới atomic

### 13.1. Tại sao `GET` rồi `EXPIRE` không phải sliding expiration atomic?

Ví dụ:

```text
Client A: GET session:42  → có dữ liệu
Client B: DEL session:42
Client B: SET session:42 "phiên khác"
Client A: EXPIRE session:42 1800
```

Client A đã “làm mới hạn” của **key do B tạo** chứ không nhất thiết còn cùng dữ liệu phiên đã đọc. Dùng `GETEX` giảm khoảng hở cho thao tác đọc + thay TTL của Redis String, nhưng **không thay thế xác minh định danh phiên hoặc quyền truy cập**.

### 13.2. Khi nhiều client cùng đặt TTL

Giả sử:

```redis
EXPIRE shared:key 60
EXPIRE shared:key 600
```

Nếu hai client lần lượt gửi lệnh này, thời hạn cuối phụ thuộc **lệnh nào Redis thực thi sau cùng**. Không có quy tắc tự động “TTL ngắn hơn luôn thắng” hay “TTL dài hơn luôn thắng”.

Khi nghiệp vụ yêu cầu:

- **Không rút ngắn deadline đã có:** cân nhắc `EXPIRE ... GT`.
- **Không gia hạn vượt deadline đã có:** cân nhắc `EXPIRE ... LT`.
- **Chỉ đặt TTL lần đầu:** cân nhắc `EXPIRE ... NX`.
- **Chỉ thay khi đã có TTL:** cân nhắc `EXPIRE ... XX`.

Những tùy chọn điều kiện phải phù hợp phiên bản Redis và cách gọi qua Spring Data Redis. Chúng **không tự giải quyết** mọi cuộc đua logic khi value thay đổi; muốn so cả content/version cần thiết kế thêm.

### 13.3. Retry và kết quả mơ hồ

Khi network timeout, client có thể không biết Redis đã thực thi `SET EX` hoặc `EXPIRE` hay chưa. Nếu retry một `SET ... EX 300`, lệnh retry có thể **gia hạn TTL thêm một khoảng** so với deadline của lệnh đầu tiên.

Nếu deadline bắt buộc phải cố định:

- Tính deadline bất biến từ sự kiện nghiệp vụ.
- Dùng timestamp tuyệt đối hoặc lưu deadline kèm dữ liệu.
- Kiểm tra ownership/version nếu có nhiều client cập nhật cùng key.
- Thiết kế retry idempotent theo mục tiêu, không mặc định “chạy lại đặt TTL” luôn vô hại.

## 14. Kiểm thử TTL khi tạo và cập nhật

Một bài test tốt cần kiểm tra không chỉ giá trị trả về mà cả **thời hạn Redis đang lưu**.

### 14.1. Ví dụ kiểm thử tích hợp với `StringRedisTemplate`

Ví dụ dưới đây giả định một `@SpringBootTest` kết nối tới Redis thử nghiệm riêng. Các assert tránh so TTL bằng chính xác số giây ban đầu vì thời gian đã trôi giữa các lệnh.

```java
package com.example.redis.ttl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class RedisTtlIntegrationTest {

    private static final String KEY = "test:ttl:create-update";

    @Autowired
    StringRedisTemplate redis;

    @AfterEach
    void cleanup() {
        redis.delete(KEY);
    }

    @Test
    void setWithDurationCreatesExpiringKey() {
        redis.opsForValue().set(KEY, "v1", Duration.ofSeconds(120));

        Long ttl = redis.getExpire(KEY, TimeUnit.SECONDS);
        assertNotNull(ttl);
        assertTrue(ttl > 0 && ttl <= 120);
    }

    @Test
    void plainSetRemovesOldExpiration() {
        redis.opsForValue().set(KEY, "v1", Duration.ofSeconds(120));
        redis.opsForValue().set(KEY, "v2");

        assertEquals("v2", redis.opsForValue().get(KEY));
        assertEquals(-1L, redis.getExpire(KEY, TimeUnit.SECONDS));
    }

    @Test
    void writingAgainWithDurationSetsExpiration() {
        redis.opsForValue().set(KEY, "v1", Duration.ofSeconds(120));
        redis.opsForValue().set(KEY, "v2", Duration.ofSeconds(180));

        Long ttl = redis.getExpire(KEY, TimeUnit.SECONDS);
        assertNotNull(ttl);
        assertTrue(ttl > 0 && ttl <= 180);
        assertEquals("v2", redis.opsForValue().get(KEY));
    }

    @Test
    void hashUpdateKeepsExistingTtl() {
        redis.opsForHash().put(KEY, "name", "An");
        redis.expire(KEY, Duration.ofSeconds(120));
        redis.opsForHash().put(KEY, "city", "Hanoi");

        Long ttl = redis.getExpire(KEY, TimeUnit.SECONDS);
        assertNotNull(ttl);
        assertTrue(ttl > 0 && ttl <= 120);
    }

    @Test
    void persistRemovesExpiration() {
        redis.opsForValue().set(KEY, "v1", Duration.ofSeconds(120));
        redis.persist(KEY);
        assertEquals(-1L, redis.getExpire(KEY, TimeUnit.SECONDS));
    }
}
```

Đây là **ví dụ về cách viết test**, không phải kết quả kiểm thử đã được chạy. Khi thực thi ở dự án thực tế, test cần Redis riêng, key riêng cho từng test nếu có chạy song song, và không được xóa dữ liệu ở Redis production.

### 14.2. Các trường hợp cần xem xét thêm

| Tình huống | Điều mong đợi cần xác định |
|---|---|
| Tạo String có TTL | Key tồn tại và `TTL > 0` |
| Tạo bằng `setIfAbsent` khi key chưa có | Value và TTL đều được thiết lập |
| `setIfAbsent` khi key đã có | Value/TTL cũ giữ nguyên |
| `setIfPresent` khi key đã hết hạn | Không tạo key mới |
| Ghi bằng `SET` không TTL | Expiration cũ bị loại |
| Ghi bằng `SET KEEPTTL` | Deadline cũ tiếp tục |
| `HSET` vào Hash có TTL | TTL cũ vẫn đếm xuống |
| `HSET` tạo Hash mới | Cần cơ chế gắn TTL nếu nghiệp vụ bắt buộc |
| `INCR` trên counter có TTL | TTL được giữ |
| `INCR` tạo counter mới | Key không tự có TTL |
| `GETEX` | Trả dữ liệu và refresh TTL trong một thao tác |
| `PERSIST` | Key còn nhưng `TTL = -1` |
| Key đã hết hạn | `TTL = -2` và lệnh đọc không trả dữ liệu |
| Redis eviction | Key có thể mất trước deadline |

Nếu ứng dụng yêu cầu TTL rất ngắn, có thể kiểm tra bằng `PTTL` để có độ phân giải mili giây. Các assertion vẫn cần dung sai phù hợp với thời gian thực, scheduler và overhead mạng; tránh test “phải bằng đúng 1000 ms” dễ thất bại do thời gian trôi.

## 15. Quan sát và xử lý lỗi TTL trong production

### 15.1. Các câu lệnh điều tra

Trên môi trường có quyền quan sát phù hợp:

```redis
EXISTS cache:product:sku-42
TYPE cache:product:sku-42
TTL cache:product:sku-42
PTTL cache:product:sku-42

INFO stats
INFO memory
CONFIG GET maxmemory-policy
```

Cần phân biệt:

- Key còn tồn tại nhưng `TTL = -1`: có thể có đường ghi `SET` làm mất TTL, hoặc key vốn được tạo không có TTL.
- Key đã biến mất (`TTL = -2`): có thể do expiration, eviction, xóa thủ công hoặc chưa từng được tạo.
- `expired_keys` tăng: Redis đã ghi nhận các key bị hết hạn.
- `evicted_keys` tăng: có key bị loại vì chính sách bộ nhớ. **Không** kết luận mọi cache miss là do TTL.
- Redis chưa cấu hình `maxmemory`/eviction như kỳ vọng: TTL và eviction là hai cơ chế riêng, cần điều tra đúng nguyên nhân.

Trong dịch vụ managed Redis, một số lệnh cấu hình/quan sát có thể bị hạn chế bởi quyền hoặc chính sách nhà cung cấp; không đổi cấu hình production chỉ để phục vụ bài tập.

### 15.2. Lỗi thường gặp theo triệu chứng

| Triệu chứng | Khả năng nguyên nhân | Hướng kiểm tra |
|---|---|---|
| Cache giữ dữ liệu cũ mãi | Một lần `SET key value` xóa TTL; hoặc tạo key quên hạn | Xem `TTL = -1`, xác định tất cả đường ghi |
| OTP sống lâu hơn chính sách | Cập nhật bằng `SET EX` đã gia hạn thời hạn | Kiểm tra fixed deadline và quy tắc retry |
| Session hết hạn mặc dù đang được đọc | Chỉ dùng `GET`, không có sliding TTL | Xác định có cần `GETEX` hay không |
| Session không bao giờ hết hạn khi có traffic | `GETEX` gia hạn trong mọi lượt đọc | Xác định yêu cầu absolute max age |
| Counter tăng đều nhưng không bao giờ reset | `INCR` tạo key không TTL hoặc thiếu `EXPIRE` | Kiểm tra đường tạo counter và atomic script |
| Hash bị xóa giữa lúc cập nhật | TTL cũ gần hết, `HSET` không làm mới TTL | Đo `PTTL` và lựa chọn update policy |
| Cache mất trước hạn | Eviction, xóa, failover hoặc cấu hình khác | `INFO stats`, logs, metrics, topology |
| `expire(...)` trả false | Key không còn tồn tại lúc đặt TTL | Xem thời điểm tạo/đổi key và race |
| Mỗi lần deploy là cache miss đồng loạt | Prefix/schema version thay đổi hoặc cache bị xóa | So sánh keyspace và cấu hình CacheManager |
| Dữ liệu mới có TTL khác dữ liệu cũ | Nhiều API/serializer/cấu hình cache khác nhau | Kiểm tra đúng code path ghi key |

### 15.3. Đừng lạm dụng `KEYS *` để tìm key lỗi

Trên Redis lớn, `KEYS *` có thể gây ảnh hưởng hiệu năng. Nếu cần duyệt key theo namespace, dùng `SCAN` có cursor, giới hạn khối lượng xử lý và hiểu đặc tính không tạo snapshot; khi chạy Redis Cluster phải xem topology các node.

Việc đếm key theo prefix trong một lần quét cũng không tự chứng minh tất cả key đều có TTL. Cần lấy mẫu hoặc có cơ chế instrumentation/observability phù hợp để phát hiện key không hạn trong những nhóm dữ liệu bắt buộc phải hết hạn.

## 16. Bài thực hành Redis CLI: so sánh các cách cập nhật

Các bước dưới đây chỉ nên chạy trên Redis dành riêng cho học tập.

### Bước 1 — Tạo String có TTL ngay từ đầu

```redis
DEL lab:ttl:string
SET lab:ttl:string "v1" EX 120
TTL lab:ttl:string
# Gần 120
```

### Bước 2 — Thử cập nhật làm mất TTL

```redis
SET lab:ttl:string "v2"
TTL lab:ttl:string
# (integer) -1
```

Kết quả cho thấy **ghi đè bằng `SET` không kèm tùy chọn TTL** có thể biến key thành không hết hạn.

### Bước 3 — Đặt lại hạn và giữ hạn

```redis
SET lab:ttl:string "v3" EX 120
SET lab:ttl:string "v4" KEEPTTL
TTL lab:ttl:string
# Vẫn đếm xuống từ lúc đặt EX 120, không tự làm mới
```

### Bước 4 — Chủ động refresh TTL khi update

```redis
SET lab:ttl:string "v5" EX 300
TTL lab:ttl:string
# Gần 300
```

### Bước 5 — Thử điều kiện tạo/cập nhật

```redis
DEL lab:ttl:conditional

SET lab:ttl:conditional "first" EX 60 NX
# OK

SET lab:ttl:conditional "second" EX 60 NX
# nil / không thực hiện vì key đã tồn tại

GET lab:ttl:conditional
# "first"

SET lab:ttl:conditional "third" EX 90 XX
# OK

GET lab:ttl:conditional
# "third"

TTL lab:ttl:conditional
# Gần 90
```

### Bước 6 — Cập nhật Hash và xem TTL

```redis
DEL lab:ttl:hash
HSET lab:ttl:hash name "An"
EXPIRE lab:ttl:hash 120

HSET lab:ttl:hash city "Hanoi"
TTL lab:ttl:hash
# TTL vẫn tồn tại; HSET không tự đặt lại 120
```

### Bước 7 — Thử `INCR` có hạn

```redis
DEL lab:ttl:counter
INCR lab:ttl:counter
TTL lab:ttl:counter
# -1 — key được tạo mà không có TTL

EXPIRE lab:ttl:counter 60
INCR lab:ttl:counter
TTL lab:ttl:counter
# Còn TTL và tiếp tục đếm xuống
```

### Bước 8 — Đọc và gia hạn bằng `GETEX`

```redis
SET lab:ttl:session "active" EX 60
GETEX lab:ttl:session EX 180
# "active"

TTL lab:ttl:session
# Gần 180
```

### Bước 9 — Gỡ thời hạn và dọn key thử nghiệm

```redis
PERSIST lab:ttl:string
TTL lab:ttl:string
# -1

DEL lab:ttl:string lab:ttl:conditional lab:ttl:hash lab:ttl:counter lab:ttl:session
```

Không sử dụng `FLUSHDB` hoặc `FLUSHALL` để dọn một vài key thực hành trên Redis chia sẻ.

## 17. Nguyên tắc triển khai TTL trong ứng dụng

Một hệ thống Spring Data Redis ổn định thường cần quy định **chính sách TTL theo loại dữ liệu**, không để từng controller tự chọn bất kỳ thời gian nào.

| Dữ liệu | Chính sách thường phù hợp | Điều cần chú ý |
|---|---|---|
| Cache sản phẩm | TTL tương đối từ lần ghi; có thể refresh khi cập nhật | Tải lại từ nguồn chính khi cache miss |
| OTP | Fixed TTL từ khi phát hoặc deadline tuyệt đối | Không gia hạn khi xác minh thất bại |
| Session | TTL theo chính sách phiên, có thể idle refresh và absolute max age | Phân biệt `GET` và `GETEX`; xác minh session |
| Idempotency key | TTL có giới hạn, tạo có điều kiện | Không hết hạn quá sớm khi side effect còn diễn ra |
| Rate-limit counter | TTL theo bucket/window | Tránh `INCR` rồi `EXPIRE` không atomic |
| Lock tạm | Tạo có điều kiện kèm TTL, có owner token | TTL không giải quyết mọi trường hợp mất khóa/giữ khóa quá hạn |
| Redis Hash cart | TTL cho toàn key, chính sách refresh/giữ rõ | `HSET` không tự refresh khi sửa field |
| Redis Repository aggregate | TTL theo `@RedisHash`/`@TimeToLive` | `save`, expiration event và secondary index có hành vi riêng |

Các nguyên tắc quan trọng:

1. **Tạo String có TTL ngay trong một lệnh** khi có thể: `SET EX/PX` hoặc `opsForValue().set(key, value, Duration)`.
2. **Chọn rõ hành vi cập nhật**: `SET` (xóa TTL), `SET EX` (refresh), `SET KEEPTTL` (giữ deadline).
3. **Không quên key mới từ lệnh cấu trúc**: `HSET`, `INCR`, `LPUSH` và `ZADD` có thể tạo key không hạn.
4. **Đừng nhầm đọc với gia hạn**: `GET` chỉ đọc; `GETEX` có thể đọc và đặt lại TTL.
5. **Đặt deadline cố định khi nghiệp vụ yêu cầu**: đừng để retry hoặc thao tác cập nhật vô tình gia hạn vô hạn.
6. **Kiểm soát đồng thời**: hai lệnh riêng có khoảng hở; dùng API atomic, script hoặc giao thức phiên bản hóa khi cần.
7. **Kiểm tra TTL thực tế**: `TTL`/`PTTL` trả `-1` cho key không hạn và `-2` cho key không tồn tại.
8. **Xử lý key bị mất**: expiration và eviction đều có thể gây cache miss; TTL không phải cam kết tồn tại.
9. **Giữ nhất quán giữa mọi code path**: Spring Cache, Repository, Template và raw Redis command có thể dùng cách lưu/TTL khác nhau.
10. **Không tạo key bí mật hoặc tạm thời bất tử** do đường xử lý lỗi hoặc cập nhật thiếu TTL.

## 18. Câu hỏi tự kiểm tra

**1. `SET key value EX 60` khác gì `SET key value`?**  
Lệnh đầu gắn thời hạn 60 giây cùng giá trị; lệnh thứ hai ghi String mà không gắn TTL và nếu thay thế key cũ có TTL thì thường làm mất hạn đó.

**2. Vì sao `SET` rồi `EXPIRE` có thể làm key tồn tại lâu hơn dự kiến?**  
Vì ứng dụng có thể gặp lỗi giữa hai lệnh, khiến key đã được tạo nhưng `EXPIRE` chưa từng chạy.

**3. `SET key value KEEPTTL` có đảm bảo key mới được tạo có TTL không?**  
Không. `KEEPTTL` chỉ giữ expiration đã có; key mới không tự có deadline.

**4. `HSET` vào một Redis Hash đã có TTL có tự đặt lại TTL không?**  
Thông thường không. Nó cập nhật field trong Hash và thời hạn của key tiếp tục giảm.

**5. `INCR` tạo key chưa có thì TTL bằng bao nhiêu?**  
Key được tạo từ `INCR` thông thường không tự có TTL, nên `TTL` trả `-1` cho key còn tồn tại.

**6. Mỗi lần người dùng mở trang thì session phải sống thêm 30 phút; lệnh Redis nào phù hợp để đọc String và gia hạn trong một thao tác?**  
`GETEX session:key EX 1800` hoặc API Spring Data Redis tương ứng như `getAndExpire(key, Duration.ofMinutes(30))` ở phiên bản hỗ trợ.

**7. Vì sao `GET` rồi `EXPIRE` không tương đương hoàn toàn `GETEX`?**  
Hai lệnh riêng có thể bị client khác thay/xóa key xen vào; `GETEX` kết hợp đọc và cập nhật thời hạn trong một lệnh Redis.

**8. `TTL = -1` và `TTL = -2` khác nhau thế nào?**  
`-1`: key có tồn tại nhưng không có hạn. `-2`: key không tồn tại, có thể do đã hết hạn hoặc chưa được tạo.

**9. Khi update với `SET ... EX 300`, thời hạn cũ còn 20 giây thì chuyện gì xảy ra?**  
Nếu ghi thành công, thời hạn được đặt mới khoảng 300 giây từ thời điểm cập nhật; không giữ 20 giây cũ.

**10. Redis Cache hit có tự reset TTL mặc định không?**  
Không nên mặc định như vậy. Spring Cache TTL thông thường tính theo entry đã được ghi; sliding/TTI cần cơ chế và version hỗ trợ riêng.

**11. Làm sao đặt TTL chỉ khi key chưa có hạn?**  
Redis 7+ cung cấp `EXPIRE key seconds NX`; cần kiểm tra phiên bản và cách gọi từ Spring Data Redis phù hợp.

**12. Redis Repository có `@RedisHash(timeToLive=600)`, gọi `save` lại có chắc giữ nguyên deadline ban đầu?**  
Không nên giả định. Repository có thể ghi và thiết lập TTL từ metadata khi lưu; cần hiểu đường mapping và kiểm tra chính sách fixed deadline so với refresh-on-save.

**13. Vì sao thêm TTL 10 phút không bảo đảm cache giữ đủ 10 phút?**  
Redis có thể eviction key sớm khi thiếu bộ nhớ hoặc key bị xóa bởi tác vụ khác.

**14. Lệnh `PERSIST` dùng để làm gì?**  
Loại bỏ expiration của key đang tồn tại, khiến key không còn tự hết hạn theo TTL trước đó.

**15. Nếu hai service cập nhật TTL của cùng key lần lượt 60 giây và 600 giây, Redis có tự giữ TTL ngắn hơn không?**  
Không. Mặc định thời hạn cuối phụ thuộc thứ tự lệnh. Muốn đặt điều kiện chỉ tăng/rút ngắn hạn, cân nhắc tùy chọn `GT`/`LT` của Redis thích hợp.

### Kết luận

Thiết lập TTL đúng không chỉ là thêm `EXPIRE` vào một chỗ nào đó. Cần xác định **khi tạo khóa có hạn ngay không**, **mỗi lần cập nhật giữ hay reset deadline**, và **khi đọc có gia hạn hay không**. Với Spring Data Redis, hãy ưu tiên các API ghi kèm `Duration` trong một thao tác cho Redis String, hiểu rõ ngữ nghĩa của `SET` so với `HSET`/`INCR`, và dùng cách phối hợp atomic phù hợp cho các cấu trúc dữ liệu phải ghi rồi mới đặt TTL. Khi thống nhất chính sách theo loại dữ liệu và kiểm tra `TTL`/`PTTL` thực tế, ứng dụng sẽ tránh được cả key “bất tử” lẫn dữ liệu hết hạn ngoài dự kiến.

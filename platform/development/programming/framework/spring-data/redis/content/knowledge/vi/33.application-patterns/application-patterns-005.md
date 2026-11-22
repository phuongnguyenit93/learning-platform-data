# Giới hạn tốc độ theo cửa sổ cố định, trượt hoặc token bucket trong Spring Data Redis

## 1. Mục tiêu và bối cảnh

**Rate limiting** (giới hạn tốc độ) là cơ chế quyết định một người dùng, API key, tenant hoặc nguồn yêu cầu được thực hiện bao nhiêu thao tác trong một khoảng thời gian. Nó giúp bảo vệ hệ thống khỏi tải vượt khả năng, ngăn lạm dụng, giảm chi phí những thao tác tốn tài nguyên và thực thi chính sách hạn mức.

Ví dụ một API đơn hàng có các quy tắc:

- Một tài khoản chỉ được gửi tối đa **60 yêu cầu/phút** đến endpoint xem trạng thái.
- Một tài khoản chỉ được thử nhập mã xác thực **5 lần/phút**.
- Endpoint tìm kiếm cho phép **10 yêu cầu liên tiếp**, rồi hồi phục **2 quyền truy cập mỗi giây**.
- Các instance Spring Boot triển khai sau load balancer phải dùng **cùng một hạn mức**, không phải mỗi instance được cấp hạn mức riêng.

Redis phù hợp làm nơi chia sẻ trạng thái rate limit vì hỗ trợ bộ đếm, TTL, Sorted Set, Hash và Lua script thực thi nguyên tử trên một Redis server. Spring Data Redis cung cấp `StringRedisTemplate`/`RedisTemplate` để gửi lệnh hoặc thực thi script từ Java.

Ba thuật toán thường dùng:

1. **Fixed window:** đếm yêu cầu trong một khoảng thời gian có ranh giới cố định.
2. **Sliding window:** tính những yêu cầu rơi vào một khoảng thời gian trượt tính ngược từ hiện tại.
3. **Token bucket:** tạo một số lượng token có giới hạn, tiêu token khi có yêu cầu và nạp lại theo tốc độ xác định.

Bài học hướng dẫn lựa chọn thuật toán theo nghiệp vụ, thiết kế khóa Redis, triển khai Lua để tránh race condition, tích hợp với Spring Boot và xử lý đúng khi Redis gặp sự cố.

> **Phạm vi:** Các ví dụ giới hạn số **yêu cầu được chấp nhận**, không phải đếm số phản hồi HTTP thành công. Nếu chỉ muốn tính quota sau khi xử lý nghiệp vụ thành công, cần thiết kế quy trình đặt chỗ/hoàn trả quota khác với ví dụ chặn trước request.

## 2. Định nghĩa hạn mức trước khi viết code

Một chính sách rate limit thường có những thành phần:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Subject | User `u-42` | Ai đang chịu hạn mức |
| Resource/action | `POST /api/orders` | Thao tác nào bị giới hạn |
| Algorithm | Fixed / Sliding / Bucket | Cách tính quyền thực hiện |
| Limit/capacity | `60` | Số lần tối đa hoặc sức chứa bucket |
| Window/refill | `60 giây` hoặc `2 token/giây` | Khoảng đo hoặc tốc độ nạp |
| Cost | `1 token` | Chi phí mỗi yêu cầu; có thể cao hơn với thao tác nặng |
| Scope | User, API key, tenant, IP | Phân chia hạn mức |
| Failure policy | Fail-open / fail-closed | Cách xử lý khi Redis lỗi |
| HTTP behavior | `429` và `Retry-After` | Phản hồi cho client bị chặn |

Ví dụ “60 yêu cầu/phút” chưa đủ để suy ra hành vi mong muốn. Một người dùng gửi 60 request trong giây cuối của phút hiện tại rồi 60 request ở giây đầu phút tiếp theo có được chấp nhận không? Fixed window có thể cho phép tình huống này; sliding window sẽ giới hạn chặt hơn.

Cần quyết định thêm: hạn mức áp dụng cho **từng người dùng**, **từng địa chỉ IP** hay **toàn tenant**? Với một hệ thống nhiều instance, nếu mỗi instance có bộ đếm trong bộ nhớ JVM thì hạn mức toàn hệ thống sẽ không được chia sẻ chính xác. Redis giải quyết bài toán chia sẻ trạng thái giữa các instance, nhưng cần thiết kế thao tác Redis nguyên tử để không vượt quota khi nhiều request đồng thời.

## 3. So sánh ba thuật toán

| Thuật toán | Cách hoạt động | Ưu điểm | Nhược điểm | Trường hợp phù hợp |
|---|---|---|---|---|
| **Fixed window** | Đếm số request trong một khung thời gian được căn theo mốc cố định | Đơn giản; bộ nhớ O(1) mỗi subject; dễ triển khai | Có thể cho phép burst gần 2 lần hạn mức quanh ranh giới hai cửa sổ | Giới hạn API phổ thông, quota dễ hiểu |
| **Sliding window log** | Lưu thời điểm từng request, xóa phần tử nằm ngoài cửa sổ | Chính xác theo cửa sổ thời gian trượt; không có burst ranh giới kiểu fixed window | Bộ nhớ O(L) mỗi subject khi lưu tối đa L request; chi phí ZSET | Login/OTP, endpoint nhạy với burst |
| **Token bucket** | Bucket có capacity C; token hồi phục tốc độ R/giây; mỗi request tốn cost | Cho phép burst có kiểm soát; tốc độ trung bình ổn định; trạng thái O(1) | Cần quản lý số token phân số, refill và thời gian | API có traffic không đều, ưu tiên trải nghiệm burst ngắn |

Trong bảng, **L** là số request tối đa trong một sliding window. Các biến thể như **sliding-window counter** dùng nhiều bucket thời gian và nội suy để tiết kiệm bộ nhớ, nhưng chúng xấp xỉ hơn sliding log và có những đánh đổi khác. Bài này dùng **sliding log với Redis Sorted Set** để minh họa rõ hành vi thời gian trượt.

### Minh họa burst ở biên cửa sổ

Giới hạn: 5 request mỗi 60 giây.

```text
Phút A:   [.................................xxxxx]
Phút B:   [xxxxx.................................]
          ^ ranh giới hai cửa sổ

Fixed window:
  5 request ngay cuối phút A + 5 request đầu phút B
  => có thể cho phép 10 request trong thời gian rất ngắn.

Sliding window 60 giây:
  5 request đầu đã chiếm quota của 60 giây gần nhất;
  5 request tiếp theo có thể bị từ chối cho đến khi quota cũ rời cửa sổ.

Token bucket:
  Cho phép burst tối đa theo số token sẵn có;
  khi bucket cạn, token được nạp lại theo tốc độ cấu hình.
```

Không có thuật toán luôn tốt nhất. Lựa chọn phụ thuộc rủi ro burst, ngân sách bộ nhớ, số key và yêu cầu giải thích hạn mức cho client.

## 4. Thiết kế Redis key trước khi triển khai

Một subject và một chính sách cần có định danh độc lập.

Ví dụ:

```text
rl:v1:order-read:{tenant42-user17}
rl:v1:checkout:{tenant42-user17}
rl:v1:login:{account-hash}
rl:v1:search:{api-key-hash}
```

Trong Redis Cluster, phần nằm trong dấu ngoặc nhọn `{...}` là **hash tag**, cho phép các key có cùng tag được đưa vào cùng hash slot khi cần thực hiện thao tác nhiều key. Các script trong bài đều thao tác trên **một key**, nhưng dùng tag rõ ràng giúp tránh nhầm khi mở rộng mô hình.

Các nguyên tắc:

1. **Không lấy trực tiếp một header không đáng tin làm subject.** Header `X-User-Id` do client tự gửi không đủ chứng minh danh tính; lấy user ID từ hệ thống xác thực hoặc API key đã xác minh.
2. **Phân tách policy.** Rate limit xem đơn hàng và rate limit thanh toán không nên chia chung key nếu có ngân sách riêng.
3. **Tránh để lộ thông tin cá nhân trong key.** Nếu subject có email, số điện thoại hay API key, hãy dùng một giá trị băm/opaque identifier phù hợp.
4. **Quản lý phiên bản namespace.** Khi thay đổi thuật toán hoặc cấu hình không tương thích, prefix `rl:v2:...` có thể giúp chuyển chính sách an toàn.
5. **Giới hạn độ dài và cardinality.** Mỗi IP/user mới có thể tạo thêm key. TTL là thiết yếu để dọn subject không còn hoạt động.
6. **Chú ý nhiều client/proxy.** Nếu rate limit theo IP, xác định IP từ reverse proxy đã tin cậy; không tin bất kỳ giá trị `X-Forwarded-For` do client bên ngoài tự đặt.
7. **Một subject có thể chịu nhiều lớp hạn mức.** Ví dụ vừa giới hạn theo account vừa giới hạn toàn tenant, nhưng nếu cập nhật nhiều key phải xem xét tính nguyên tử toàn bộ quyết định.

Trong các ví dụ, tên key đã được tạo từ **subject đáng tin cậy và đã chuẩn hóa**. Không cho client lựa chọn tự do tên Redis key mà Lua script sẽ thao tác.

## 5. Vì sao không dùng GET rồi SET một cách ngây thơ?

Xét bộ đếm fixed window lưu ở key `rl:v1:login:{u42}`:

```text
Request A: GET count -> 4
Request B: GET count -> 4

Request A: thấy 4 < 5, SET count = 5 -> cho phép
Request B: thấy 4 < 5, SET count = 5 -> cho phép
```

Với hạn mức 5, cả hai request được chấp nhận, dù chỉ còn một lượt. Nguyên nhân là **read–check–write race condition**.

Redis `INCR` riêng lẻ là thao tác nguyên tử, nhưng nếu ứng dụng làm thêm `EXPIRE`, so sánh quota, đọc thời gian và cập nhật nhiều field bằng nhiều lệnh tách rời thì **toàn bộ quy trình vẫn có thể bị xen giữa hoặc lỗi giữa chừng**.

Các phương án:

- Một thao tác Redis server-side đủ diễn đạt điều kiện.
- Lua script thực thi cả kiểm tra và cập nhật cùng một lượt.
- Redis Function hoặc cơ chế khóa/transaction với retry được thiết kế đúng.
- Đối với quota nghiệp vụ bền vững, có thể cần một nguồn dữ liệu khác đủ khả năng ràng buộc tính nhất quán.

Trong bài này dùng **Lua script** qua `StringRedisTemplate.execute(...)`. Redis chạy script nguyên tử so với các lệnh khác trên cùng server, nên hai request đồng thời không cùng đọc một trạng thái cũ rồi cùng chiếm lượt cuối.

**Giới hạn:** script nguyên tử không đồng nghĩa có rollback tự động nếu một lệnh bên trong script lỗi sau khi đã ghi. Cần xác thực tham số trước và viết script tránh lỗi giữa chừng. Trên Redis Cluster, key mà script truy cập phải được truyền đúng qua `KEYS` và tuân thủ quy tắc hash slot.

## 6. Fixed window: bộ đếm theo khung thời gian cố định

### 6.1. Nguyên lý

Với `limit = 5` và `windowSeconds = 60`, thời gian được chia thành những khung:

```text
[12:00:00, 12:01:00) → window 1
[12:01:00, 12:02:00) → window 2
[12:02:00, 12:03:00) → window 3
```

Mỗi khung giữ một count riêng về mặt logic. Khi sang khung mới, count trở về 0. Request được chấp nhận nếu count hiện tại nhỏ hơn limit.

Có hai cách lưu phổ biến:

- Tạo key mới cho từng khung thời gian, ví dụ `rl:user:123:minute:123456`.
- Dùng **một Redis Hash cố định** cho mỗi subject, gồm `window` và `count`, reset count khi số hiệu khung thay đổi.

Ví dụ trong bài chọn **một hash cố định** để không phải tạo tên key động bên trong Lua script. Cách này cũng thuận tiện dùng `TIME` của Redis server, tránh clock skew giữa các instance ứng dụng.

### 6.2. Cấu trúc Redis Hash

```text
Key: rl:v1:fixed:checkout:{u42}
Type: hash

window = 28400001
count  = 4

TTL: windowSeconds + một khoảng đệm nhỏ kể từ request gần nhất
```

`window` biểu diễn số hiệu cửa sổ, có thể tính bằng:

```text
windowIndex = floor(redisEpochSeconds / windowSeconds)
```

Khi `windowIndex` thay đổi, script reset counter dù Redis key chưa hết TTL.

### 6.3. Lua script: fixed-window.lua

Đầu vào:

- `KEYS[1]`: key state của subject và policy.
- `ARGV[1]`: `limit`, số nguyên dương.
- `ARGV[2]`: `windowSeconds`, số nguyên dương.

Kết quả: `{allowed, remaining, retryAfterMs}`.

```lua
-- redis/fixed-window.lua
-- Input được Java xác thực là limit > 0, windowSeconds > 0.

local key = KEYS[1]
local limit = tonumber(ARGV[1])
local windowSeconds = tonumber(ARGV[2])

-- Dùng đồng hồ của Redis để mọi instance cùng mốc cửa sổ.
local nowSeconds = tonumber(redis.call('TIME')[1])
local windowIndex = math.floor(nowSeconds / windowSeconds)

local storedWindow = redis.call('HGET', key, 'window')
local count

if not storedWindow or tonumber(storedWindow) ~= windowIndex then
    redis.call('HSET', key, 'window', windowIndex, 'count', 0)
    count = 0
else
    count = tonumber(redis.call('HGET', key, 'count') or '0')
end

local allowed = 0

if count < limit then
    count = redis.call('HINCRBY', key, 'count', 1)
    allowed = 1
end

-- Key có thể tồn tại sang cửa sổ kế tiếp, nhưng windowIndex
-- đảm bảo counter reset đúng lúc.
redis.call('EXPIRE', key, windowSeconds + 2)

local remaining = math.max(0, limit - count)
local secondsUntilNextWindow =
    windowSeconds - (nowSeconds % windowSeconds)

local retryAfterMs = 0
if allowed == 0 then
    retryAfterMs = secondsUntilNextWindow * 1000
end

return {allowed, remaining, retryAfterMs}
```

### 6.4. Ví dụ luồng kết quả

```text
Policy: tối đa 3 request / 60 giây
Key: rl:v1:fixed:checkout:{u42}

12:00:10  Request #1 → allowed=1, remaining=2
12:00:20  Request #2 → allowed=1, remaining=1
12:00:30  Request #3 → allowed=1, remaining=0
12:00:40  Request #4 → allowed=0, remaining=0,
                       retryAfter≈20 giây
12:01:00  Request #5 → window mới, allowed=1, remaining=2
```

Script **không tăng count khi bị chặn**, nên state chỉ theo dõi số lượt đã được chấp nhận trong khung hiện tại. Nếu muốn thống kê số request bị từ chối, ghi metric riêng, không dùng count của policy này để suy ra tổng số lần thử.

### 6.5. Chi phí và đặc tính

- Redis lưu **một hash nhỏ cho mỗi subject/policy**: bộ nhớ O(1).
- Mỗi lần kiểm tra chạy một script, đọc và thay đổi vài field của cùng key.
- Reset được căn theo thời gian server, không phụ thuộc instance ứng dụng.
- Có thể xảy ra **burst gần 2 × limit ở ranh giới khung**.
- Nếu policy đổi giữa lúc key còn tồn tại, script dùng limit/window mới; thay đổi kích thước cửa sổ có thể tạo reset bất ngờ. Nên version namespace khi thay chính sách đáng kể.

Nếu nghiệp vụ chỉ cần “xấp xỉ N request mỗi phút” và ưu tiên chi phí thấp, fixed window thường đủ.

## 7. Sliding window log: tính chính xác theo thời gian trượt

### 7.1. Nguyên lý

Sliding window không chia thời gian thành những khung cố định. Tại thời điểm `now`, chỉ tính các request nằm trong khoảng:

```text
(now - windowMs, now]
```

Ví dụ tối đa 5 request trong bất kỳ cửa sổ 60 giây nào. Nếu người dùng vừa thực hiện 5 request vào các thời điểm từ 12:00:50 tới 12:00:54, thì request 12:01:00 vẫn bị chặn; quota không reset chỉ vì đồng hồ chuyển phút.

### 7.2. Dùng Redis Sorted Set

Mỗi request được chấp nhận là một thành viên của Redis Sorted Set:

- **score:** thời điểm request theo milliseconds từ Redis server.
- **member:** ID **duy nhất cho từng lần thử**, chẳng hạn UUID.
- **key:** định danh subject và policy.

```text
Key: rl:v1:sliding:otp:{u42}

Score (ms)       Member
1700000000100    6718d3d2-...
1700000000350    12a9fb10-...
1700000000600    cd1edb9f-...
```

Redis ZSET **không cho hai thành viên trùng member** trong cùng một set. Nếu lấy timestamp làm member và hai request đến cùng mili giây, chúng có thể đè nhau. Vì vậy, ví dụ dùng **UUID mới cho mỗi lần kiểm tra**.

Để kiểm tra quota:

1. Đọc thời gian hiện tại từ Redis `TIME`.
2. Dọn phần tử có score **nhỏ hơn hoặc bằng** `now - windowMs`.
3. Đếm số phần tử còn lại bằng `ZCARD`.
4. Nếu ít hơn limit, thêm member mới bằng `ZADD` và cho phép.
5. Nếu đã đủ limit, từ chối.
6. Đặt TTL để ZSET được dọn sau khi subject không hoạt động.
7. Nếu bị từ chối, dùng thời điểm entry cũ nhất để ước tính lúc quota mở ra.

Toàn bộ được thực hiện **trong một script**.

### 7.3. Lua script: sliding-window.lua

Đầu vào:

- `KEYS[1]`: ZSET của policy.
- `ARGV[1]`: `limit`.
- `ARGV[2]`: `windowMs`.
- `ARGV[3]`: request ID duy nhất do service sinh.

Kết quả: `{allowed, remaining, retryAfterMs}`.

```lua
-- redis/sliding-window.lua
-- Java xác thực limit > 0, windowMs > 0,
-- và sinh UUID mới cho mỗi lần thử.

local key = KEYS[1]
local limit = tonumber(ARGV[1])
local windowMs = tonumber(ARGV[2])
local requestId = ARGV[3]

local time = redis.call('TIME')
local nowMs = tonumber(time[1]) * 1000
    + math.floor(tonumber(time[2]) / 1000)

local cutoff = nowMs - windowMs

-- Cửa sổ (cutoff, nowMs], nên bỏ cả score == cutoff.
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)

local count = redis.call('ZCARD', key)
local allowed = 0

if count < limit then
    -- Mỗi requestId phải duy nhất để không ghi đè thành viên cũ.
    local inserted = redis.call('ZADD', key, 'NX', nowMs, requestId)

    if inserted == 1 then
        count = count + 1
        allowed = 1
    end
end

-- Giữ state tối đa cho đến khi subject ngừng thử
-- đủ lâu. Mỗi request sẽ làm mới thời gian dọn key.
if count > 0 then
    redis.call('PEXPIRE', key, windowMs + 1000)
end

local remaining = math.max(0, limit - count)
local retryAfterMs = 0

if allowed == 0 then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')

    if #oldest >= 2 then
        local oldestMs = tonumber(oldest[2])
        retryAfterMs = math.max(
            1,
            math.ceil(oldestMs + windowMs - nowMs + 1)
        )
    else
        -- Trường hợp bất thường như requestId bị trùng.
        retryAfterMs = 1
    end
end

return {allowed, remaining, retryAfterMs}
```

**Lưu ý về request ID:** code Java phải sinh một UUID mới trên mỗi lần kiểm tra quota. Không dùng một ID chung cho toàn phiên hoặc toàn user. Nếu cùng member được gửi lại, `ZADD NX` không thêm bản ghi mới; ví dụ chọn cách không cấp lượt trong tình huống bất thường đó. Đây là bộ đếm request, không phải giải pháp idempotency nghiệp vụ.

### 7.4. Giải thích retryAfter của sliding window

Nếu key đang chứa 5 request được chấp nhận và request cũ nhất có score `t0`, quota sớm nhất có thể mở lại sau khi:

```text
now > t0 + windowMs
```

Vì script loại bỏ các entry có score `<= now - windowMs`, thời gian chờ gần đúng là:

```text
retryAfterMs = max(1, t0 + windowMs - now + 1)
```

Đây là ước tính theo trạng thái tại **thời điểm kiểm tra**. Những client khác có thể chiếm lượt ngay sau đó, nên server không đảm bảo một yêu cầu gửi lại đúng lúc `Retry-After` luôn được chấp nhận.

### 7.5. Chi phí

- Mỗi subject có thể lưu tối đa gần `limit` member được chấp nhận trong một cửa sổ.
- `ZADD` có độ phức tạp thường gắn với log số phần tử.
- `ZREMRANGEBYSCORE` tốn thêm chi phí theo số phần tử hết hạn cần dọn.
- Bộ nhớ tăng theo số subject nhân với quota, không chỉ theo số subject.
- Với hàng triệu subject hoặc limit rất lớn, cần cân nhắc chi phí Redis memory và CPU.

Nếu cần hạn mức 5 OTP mỗi phút cho từng tài khoản, chi phí O(5) mỗi subject thường chấp nhận được. Nếu cần theo dõi chính xác từng request cho 100.000 request/phút trên hàng triệu user, sliding log có thể quá đắt; cân nhắc sliding-window counter, token bucket hoặc một gateway chuyên dụng.

## 8. Token bucket: cho phép burst rồi nạp lại token

### 8.1. Nguyên lý

Một bucket có:

- **capacity (C):** số token tối đa.
- **refill rate (R):** số token được thêm vào mỗi giây.
- **cost:** số token tiêu cho mỗi yêu cầu.
- **tokens:** số token hiện tại, có thể là số thập phân.
- **lastUpdateMs:** mốc thời gian cập nhật gần nhất.

Trước khi xét request, tính:

```text
elapsedSeconds = max(0, now - lastUpdate) / 1000

tokens = min(
    capacity,
    tokens + elapsedSeconds * refillRate
)

Nếu tokens >= cost:
    tokens = tokens - cost
    ALLOW
Ngược lại:
    DENY
```

Ví dụ policy `capacity=10`, `refillRate=2 token/giây`, `cost=1`:

```text
Ban đầu: 10 token
10 request liên tiếp → dùng hết 10 token
Request thứ 11 ngay lập tức → bị chặn

Sau 0,5 giây: hồi phục khoảng 1 token
Sau 1 giây: hồi phục khoảng 2 token
Sau 5 giây không dùng: bucket có thể đầy 10 token
```

Token bucket hợp lý khi muốn cho phép **burst có giới hạn** nhưng buộc tốc độ trung bình tiến gần tốc độ refill khi lưu lượng kéo dài.

### 8.2. Cấu trúc Redis Hash

```text
Key: rl:v1:bucket:search:{u42}
Type: hash

tokens     = 7.500000000
updated_ms = 1700000000500
```

Không cần một record cho từng request. Một hash chứa trạng thái bucket là đủ.

### 8.3. Lua script: token-bucket.lua

Đầu vào:

- `KEYS[1]`: hash của bucket.
- `ARGV[1]`: `capacity`, số dương.
- `ARGV[2]`: `refillTokensPerSecond`, số dương.
- `ARGV[3]`: `cost`, số dương và không lớn hơn capacity.

Kết quả: `{allowed, remainingMilliTokens, retryAfterMs}`. Giá trị `remainingMilliTokens` là số token còn lại nhân 1.000 để truyền kết quả dưới dạng số nguyên, tiện giải mã qua Spring Data Redis.

```lua
-- redis/token-bucket.lua
-- Java xác thực capacity > 0, rate > 0,
-- 0 < cost <= capacity.

local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])

local time = redis.call('TIME')
local nowMs = tonumber(time[1]) * 1000
    + math.floor(tonumber(time[2]) / 1000)

local state = redis.call(
    'HMGET', key, 'tokens', 'updated_ms'
)

local tokens = tonumber(state[1]) or capacity
local previousMs = tonumber(state[2]) or nowMs

-- Tránh lượng thời gian âm khi đồng hồ bị chỉnh lùi.
if nowMs < previousMs then
    nowMs = previousMs
end

local elapsedMs = nowMs - previousMs

tokens = math.min(
    capacity,
    tokens + elapsedMs * rate / 1000
)

local allowed = 0

if tokens >= cost then
    tokens = tokens - cost
    allowed = 1
end

-- Giữ độ chính xác đủ cho quota API thông thường.
redis.call(
    'HSET',
    key,
    'tokens', string.format('%.9f', tokens),
    'updated_ms', nowMs
)

-- Sau đủ thời gian không có request để bucket hồi đầy,
-- state cũ không còn cần thiết.
local idleTtlSeconds = math.max(
    1,
    math.ceil(capacity / rate) + 1
)

redis.call('EXPIRE', key, idleTtlSeconds)

local retryAfterMs = 0

if allowed == 0 then
    retryAfterMs = math.max(
        1,
        math.ceil((cost - tokens) / rate * 1000)
    )
end

local remainingMilliTokens = math.max(
    0,
    math.floor(tokens * 1000)
)

return {allowed, remainingMilliTokens, retryAfterMs}
```

### 8.4. Vì sao cần TTL cho bucket?

Nếu một user chỉ gửi vài request rồi không quay lại, không nên giữ hash của họ mãi mãi. Sau khi bucket có đủ thời gian để nạp đầy mà không có request, trạng thái cũ tương đương trạng thái khởi tạo `tokens = capacity`. Khi key hết TTL, lần kiểm tra sau được xem như bucket mới đầy.

Ví dụ:

```text
capacity = 10
rate = 2 token/giây

Thời gian nạp đầy từ cạn = 10 / 2 = 5 giây
TTL idle ví dụ = ceil(5) + 1 = 6 giây
```

Nếu ứng dụng thường xuyên nhận request, script refresh TTL và trạng thái được giữ lại; nếu không hoạt động đủ lâu, key được Redis dọn.

**Giới hạn:** Lua sử dụng số thực để tính token. Với quota cần độ chính xác đặc biệt cao hoặc rate rất nhỏ, có thể dùng fixed-point integer và đơn vị phù hợp thay vì biểu diễn số thập phân. Phần demo dùng 9 chữ số sau dấu thập phân cho quota API phổ thông, không phải phép tính tiền hay hạn mức tài chính.

### 8.5. Vấn đề chi phí khác nhau

Không phải yêu cầu nào cũng tiêu 1 token:

```text
GET /api/search?q=...       cost = 1
POST /api/reports/export    cost = 5
POST /api/ai/batch          cost = 10
```

Nếu policy `capacity = 20`, `refillRate = 1 token/giây`, thao tác xuất báo cáo tốn 5 token sẽ bị chặn khi bucket chỉ còn 3 token và có thể được cấp sau khoảng 2 giây.

Chiến lược cost giúp kiểm soát một số tài nguyên theo độ nặng tương đối. Tuy nhiên, nó **không đo lượng CPU, RAM hay chi phí thực tế đã dùng**; với những tác vụ có độ nặng thay đổi sau khi bắt đầu, cần chính sách đặt chỗ/hoàn trả hoặc đo tiêu thụ thực tế.

## 9. So sánh giới hạn trên cùng lưu lượng

Xét một user gửi nhiều request trong thời gian ngắn, rồi nghỉ:

| Tình huống | Fixed window | Sliding log | Token bucket |
|---|---|---|---|
| Burst ngay gần ranh giới phút | Có thể gần 2 × limit | Giữ giới hạn theo cửa sổ thực | Giới hạn bởi token đang có |
| Request đều đặn, kéo dài | Tính quota từng khung | Giới hạn mọi cửa sổ trượt | Tốc độ trung bình bị ràng bởi refill |
| Cần lưu từng timestamp | Không | Có | Không |
| Trả thời gian chờ | Tới ranh giới khung tiếp | Đến khi request cũ nhất rời cửa sổ | Đến khi tích lũy đủ token |
| Bộ nhớ trên mỗi subject | O(1) | O(limit) | O(1) |
| Hành vi khi hệ thống idle lâu | Cửa sổ mới về 0 | ZSET cũ được dọn | Token đầy trở lại |
| Phù hợp hạn mức OTP nghiêm ngặt | Có burst ở biên, cân nhắc kỹ | Thường phù hợp hơn | Có thể phù hợp nếu capacity nhỏ |
| Phù hợp API có request dồn theo đợt | Có burst biên không kiểm soát tốt | Có thể chặn quá gắt | Linh hoạt với burst có giới hạn |

Một API gateway có thể áp dụng **nhiều lớp hạn mức**, chẳng hạn token bucket theo user và fixed window theo tenant. Nhưng nếu hai script cập nhật hai key độc lập, có thể xảy ra trường hợp quota user đã bị trừ dù quota tenant bị từ chối. Khi cần quyết định hợp nhất nguyên tử, nên thiết kế riêng một script thao tác các key cùng slot (trên Redis Cluster) hoặc dùng cơ chế quản trị quota chuyên dụng.

## 10. Tích hợp Spring Boot và Spring Data Redis

### 10.1. Dependencies

Với Spring Boot và REST API MVC:

**Gradle:**

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

**Maven:**

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

Cấu hình Redis local:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

`StringRedisTemplate` phù hợp cho những key và đối số chuỗi của Lua script. Với Spring Boot thông dụng, starter Redis cung cấp `RedisConnectionFactory` và template thích hợp theo auto-configuration. Trong môi trường thật, bổ sung xác thực, TLS, endpoint, topology và timeout phù hợp.

### 10.2. Đặt Lua script trong resources

Tạo ba file resource trong ứng dụng:

```text
src/main/resources/
└── redis/
    ├── fixed-window.lua
    ├── sliding-window.lua
    └── token-bucket.lua
```

Nội dung lần lượt là ba script đã giới thiệu phía trên. Lưu file ở `resources` giúp ứng dụng đóng gói script cùng artifact, dễ version, review và triển khai.

**Lưu ý:** Các đường dẫn trên minh họa cấu trúc dự án mẫu; đây không phải yêu cầu phải tạo thêm file trong bài học này. Có thể dùng `DefaultRedisScript.setScriptText(...)` nếu dự án muốn lưu Lua trực tiếp trong mã Java.

### 10.3. Cấu hình bean RedisScript

**`RateLimitScriptConfig.java`**

```java
package com.example.ratelimit;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class RateLimitScriptConfig {

    @Bean("fixedWindowRateLimitScript")
    public RedisScript<List> fixedWindowRateLimitScript() {
        return load("redis/fixed-window.lua");
    }

    @Bean("slidingWindowRateLimitScript")
    public RedisScript<List> slidingWindowRateLimitScript() {
        return load("redis/sliding-window.lua");
    }

    @Bean("tokenBucketRateLimitScript")
    public RedisScript<List> tokenBucketRateLimitScript() {
        return load("redis/token-bucket.lua");
    }

    private RedisScript<List> load(String path) {
        DefaultRedisScript<List> script =
                new DefaultRedisScript<>();

        script.setLocation(new ClassPathResource(path));
        script.setResultType(List.class);

        return script;
    }
}
```

`DefaultRedisScript` quản lý script và checksum để Spring Data Redis có thể sử dụng cơ chế thực thi script của Redis. `List.class` phù hợp vì cả ba Lua script trả về bảng gồm ba giá trị số.

### 10.4. Kiểu kết quả dùng chung

**`RateLimitDecision.java`**

```java
package com.example.ratelimit;

import java.time.Duration;

public record RateLimitDecision(
        boolean allowed,
        double remaining,
        Duration retryAfter
) {
}
```

Ý nghĩa:

- `allowed`: request có vượt hạn mức không.
- `remaining`: quota còn lại; fixed/sliding tính theo lượt, token bucket tính theo token.
- `retryAfter`: thời gian chờ dự kiến khi bị chặn, không phải cam kết chắc chắn sẽ được cấp lượt ở lần tiếp theo.

### 10.5. Service thực thi cả ba script

**`RedisRateLimiter.java`**

```java
package com.example.ratelimit;

import java.time.Duration;
import java.util.List;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class RedisRateLimiter {

    private final StringRedisTemplate redis;
    private final RedisScript<List> fixedScript;
    private final RedisScript<List> slidingScript;
    private final RedisScript<List> bucketScript;

    public RedisRateLimiter(
            StringRedisTemplate redis,
            @Qualifier("fixedWindowRateLimitScript")
            RedisScript<List> fixedScript,
            @Qualifier("slidingWindowRateLimitScript")
            RedisScript<List> slidingScript,
            @Qualifier("tokenBucketRateLimitScript")
            RedisScript<List> bucketScript
    ) {
        this.redis = redis;
        this.fixedScript = fixedScript;
        this.slidingScript = slidingScript;
        this.bucketScript = bucketScript;
    }

    public RateLimitDecision fixedWindow(
            String redisKey,
            int limit,
            long windowSeconds
    ) {
        if (limit <= 0 || windowSeconds <= 0) {
            throw new IllegalArgumentException("Invalid fixed-window config");
        }

        List<?> result = redis.execute(
                fixedScript,
                List.of(redisKey),
                Integer.toString(limit),
                Long.toString(windowSeconds)
        );

        return decode(result, 1.0);
    }

    public RateLimitDecision slidingWindow(
            String redisKey,
            int limit,
            long windowMs
    ) {
        if (limit <= 0 || windowMs <= 0) {
            throw new IllegalArgumentException("Invalid sliding-window config");
        }

        // Mỗi phép kiểm tra quota có một member riêng trong ZSET.
        String requestId = UUID.randomUUID().toString();

        List<?> result = redis.execute(
                slidingScript,
                List.of(redisKey),
                Integer.toString(limit),
                Long.toString(windowMs),
                requestId
        );

        return decode(result, 1.0);
    }

    public RateLimitDecision tokenBucket(
            String redisKey,
            double capacity,
            double refillPerSecond,
            double cost
    ) {
        if (!Double.isFinite(capacity)
                || !Double.isFinite(refillPerSecond)
                || !Double.isFinite(cost)
                || capacity <= 0
                || refillPerSecond <= 0
                || cost <= 0
                || cost > capacity) {
            throw new IllegalArgumentException("Invalid token-bucket config");
        }

        List<?> result = redis.execute(
                bucketScript,
                List.of(redisKey),
                Double.toString(capacity),
                Double.toString(refillPerSecond),
                Double.toString(cost)
        );

        // Lua trả số token còn lại nhân 1000.
        return decode(result, 1000.0);
    }

    private RateLimitDecision decode(
            List<?> values,
            double remainingDivisor
    ) {
        if (values == null || values.size() != 3) {
            throw new IllegalStateException(
                    "Unexpected Redis rate-limit result"
            );
        }

        long allowedFlag =
                ((Number) values.get(0)).longValue();

        long remainingRaw =
                ((Number) values.get(1)).longValue();

        long retryMs =
                ((Number) values.get(2)).longValue();

        return new RateLimitDecision(
                allowedFlag == 1L,
                remainingRaw / remainingDivisor,
                Duration.ofMillis(Math.max(0L, retryMs))
        );
    }
}
```

Dùng API:

```java
RateLimitDecision fixed = limiter.fixedWindow(
        "rl:v1:fixed:read-order:{u42}",
        60,
        60
);

RateLimitDecision sliding = limiter.slidingWindow(
        "rl:v1:sliding:otp:{u42}",
        5,
        60_000
);

RateLimitDecision bucket = limiter.tokenBucket(
        "rl:v1:bucket:search:{u42}",
        10.0,
        2.0,
        1.0
);
```

Không phải gọi cả ba thuật toán cho cùng một request. Các lệnh trên minh họa **ba chính sách độc lập**. Trong ứng dụng thật, service hoặc middleware chọn đúng policy theo endpoint, người dùng và tenant.

### Tại sao dùng Lua script thay nhiều lệnh StringRedisTemplate?

Nếu service gọi `opsForValue().get`, so sánh count rồi `increment` và `expire` bằng nhiều round trip, những request từ nhiều instance có thể xen kẽ. Trong ví dụ, kiểm tra quota và cập nhật state nằm trong **một lệnh script nguyên tử**, làm quyết định chấp nhận nhất quán ở Redis server tương ứng.

Cũng cần hiểu Redis **không có rollback từng lệnh bên trong script nếu script lỗi sau khi đã ghi**. Các script cần có validation tham số và giới hạn dữ liệu đầu vào; ví dụ Java đã kiểm tra cấu hình trước khi gửi.

## 11. Trả HTTP 429 và Retry-After

Khi client vượt hạn mức, HTTP status thường dùng là **`429 Too Many Requests`**. Header `Retry-After` có thể cho biết khoảng thời gian nên chờ trước khi thử lại.

Ví dụ phản hồi:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 12

{"error":"RATE_LIMITED","message":"Too many requests"}
```

`Retry-After` khi biểu diễn bằng số là **số giây không âm**, không phải milliseconds. Vì vậy, nếu script trả `retryAfterMs=1500` thì thường làm tròn lên 2 giây:

```java
long seconds = Math.max(
        1L,
        (decision.retryAfter().toMillis() + 999L) / 1000L
);
```

Đối với quota hết tại ranh giới fixed window, retry có thể thành công sau mốc đó. Với sliding window hoặc token bucket, thời gian chờ là **ước tính** theo quota tại lúc xét; request cạnh tranh từ client khác có thể tiêu mất quyền vừa được nạp.

Có thể trả các header bổ sung như `X-RateLimit-Limit` hoặc `X-RateLimit-Remaining` theo quy ước API, nhưng đừng hiểu một header tùy biến là đặc tả bảo đảm chung cho mọi client. Nếu sử dụng bộ header tiêu chuẩn hóa theo một phiên bản chuẩn cụ thể, nên tuân thủ cách biểu diễn thời gian, đơn vị và nhiều chính sách của chuẩn đó.

### Một policy ví dụ cho endpoint cần xác thực

Giả sử API `POST /api/orders` chỉ dành cho tài khoản đã đăng nhập. Có thể giới hạn bằng token bucket ở tầng Spring MVC thông qua `HandlerInterceptor`.

**`OrderRateLimitInterceptor.java`**

```java
package com.example.ratelimit;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Principal;
import java.util.HexFormat;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class OrderRateLimitInterceptor implements HandlerInterceptor {

    private final RedisRateLimiter limiter;

    public OrderRateLimitInterceptor(RedisRateLimiter limiter) {
        this.limiter = limiter;
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler
    ) throws IOException {
        Principal principal = request.getUserPrincipal();

        if (principal == null) {
            response.sendError(
                    HttpServletResponse.SC_UNAUTHORIZED,
                    "Authentication required"
            );
            return false;
        }

        String principalTag = sha256(principal.getName());
        String key = "rl:v1:orders:{" + principalTag + "}";

        RateLimitDecision decision;

        try {
            decision = limiter.tokenBucket(
                    key,
                    10.0, // Capacity: 10 request
                    2.0,  // Nạp 2 token mỗi giây
                    1.0   // Mỗi request tốn 1 token
            );
        } catch (DataAccessException ex) {
            // Fail-closed minh họa cho thao tác ghi nhạy cảm:
            // nếu không xác minh được quota, không thực hiện request.
            response.sendError(
                    HttpServletResponse.SC_SERVICE_UNAVAILABLE,
                    "Rate-limit service unavailable"
            );
            return false;
        }

        if (!decision.allowed()) {
            long retryMs = decision.retryAfter().toMillis();
            long retrySeconds = Math.max(
                    1L,
                    (retryMs + 999L) / 1000L
            );

            response.setHeader(
                    "Retry-After",
                    Long.toString(retrySeconds)
            );
            response.setStatus(429);
            response.setContentType("application/json");
            response.getWriter().write(
                    "{\"error\":\"RATE_LIMITED\"}"
            );
            return false;
        }

        return true;
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest
                    .getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));

            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 unavailable",
                    ex
            );
        }
    }
}
```

Điểm quan trọng:

- `request.getUserPrincipal()` cần dựa vào cơ chế authentication đáng tin của ứng dụng. Đây không phải chức năng tự xác thực của interceptor.
- Tên khóa được băm để không đưa trực tiếp user name/email vào Redis key; hash không thay thế chính sách bảo vệ dữ liệu cá nhân hoặc chống suy đoán nếu identifier có entropy thấp.
- Nếu Redis lỗi ở một endpoint ghi quan trọng, ví dụ chọn **fail-closed**, trả 503 thay vì tự cho phép mọi request.
- `DataAccessException` đại diện một nhóm lỗi truy cập dữ liệu Spring; các loại lỗi khi thực thi script cũng cần được xem xét theo version và driver.
- Nếu rate limit áp dụng cho tất cả method trong path, phải kiểm tra chính sách có muốn chặn cả GET hay chỉ POST. Ví dụ này giả định interceptor được đăng ký đúng phạm vi API ghi.

### Đăng ký interceptor

**`RateLimitWebConfig.java`**

```java
package com.example.ratelimit;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class RateLimitWebConfig implements WebMvcConfigurer {

    private final OrderRateLimitInterceptor interceptor;

    public RateLimitWebConfig(
            OrderRateLimitInterceptor interceptor
    ) {
        this.interceptor = interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(interceptor)
                .addPathPatterns("/api/orders/**");
    }
}
```

Trong hệ thống thực tế, nếu muốn giới hạn **chỉ POST**, cần thêm kiểm tra method trong `preHandle` hoặc tách chính sách theo route/handler thay vì áp dụng cùng quota cho mọi method khớp path.

Nếu dùng Spring Security, nên bảo đảm authentication được xử lý trước khi interceptor đọc principal và những endpoint được bảo vệ có cấu hình quyền tương ứng. Rate limiter **không thay thế xác thực hoặc phân quyền**.

## 12. Một request có nhiều mức hạn mức

Ví dụ người dùng `u42` thuộc tenant `companyA`:

```text
User policy:   10 request/giây mỗi user
Tenant policy: 100 request/giây toàn tenant
Global policy: 5000 request/giây toàn hệ thống
```

Giả sử một request được kiểm tra:

1. User còn quota → trừ user 1 token.
2. Tenant hết quota → request bị chặn.
3. User đã mất 1 token dù request không qua được.

Nếu đây là hành vi không mong muốn, **không** chỉ cần viết ba lời gọi `tokenBucket(...)` trong Java. Chúng là ba script nguyên tử **riêng lẻ**, không tạo một transaction chung.

Các lựa chọn thiết kế:

- **Cho phép quota bảo thủ:** chấp nhận rằng một request bị từ chối ở lớp thứ hai vẫn có thể tiêu quota lớp đầu; chính sách phải nêu rõ điều này.
- **Kiểm tra nhiều policy trong một Lua script:** dùng tất cả Redis key cần thiết trong `KEYS`, tính điều kiện trước, rồi cập nhật đồng thời chỉ nếu được phép.
- **Chuyển logic vào gateway/rate-limiting service chuyên biệt:** phù hợp khi nhiều ứng dụng và nhiều cấp hạn mức cùng tồn tại.
- **Dùng Redis Function:** đóng gói xử lý server-side thành logic có thể quản lý theo phiên bản Redis phù hợp.

Với Redis Cluster, nếu Lua script cần truy cập nhiều key, chúng phải tuân thủ giới hạn **cùng hash slot** hoặc chiến lược phân chia thích hợp. Đừng tự tạo tên key mới trong Lua mà không khai báo các key được truy cập qua `KEYS`.

## 13. Time source và sai lệch đồng hồ

Rate limiting là bài toán phụ thuộc thời gian. Nếu mỗi instance tính `System.currentTimeMillis()` rồi gửi timestamp xuống Redis, sai lệch đồng hồ giữa các instance có thể gây kết quả khó hiểu:

```text
Instance A: 12:00:59.900
Instance B: 12:01:00.400
Redis state chung
```

Các script trong bài gọi `TIME` tại Redis để dùng **một nguồn thời gian của node đang xử lý key**. Điều này giúp các request tới cùng key trên một Redis primary được đánh giá theo một đồng hồ nhất quán hơn.

Nhưng vẫn có giới hạn:

- Redis server clock có thể được điều chỉnh bởi hệ điều hành.
- Failover sang node khác có thể thay đổi đồng hồ tham chiếu.
- Script token bucket có xử lý trường hợp thời gian đi lùi bằng cách không tính elapsed âm.
- Fixed window căn theo epoch time; nếu clock thay đổi bất thường, ranh giới cũng có thể dịch.
- Khi triển khai đa region, việc dùng Redis primary khác nhau cho cùng policy có thể làm quota bị chia tách.

Không sử dụng quota Redis như một cơ chế tính tiền tuyệt đối theo thời gian thực mà thiếu nguồn dữ liệu nghiệp vụ bền vững và khả năng đối soát.

### Vì sao không đặt timestamp trên client?

Client có thể tự sửa hoặc giả mạo đồng hồ, đặc biệt nếu dữ liệu timestamp do ứng dụng mobile/browser gửi. Timestamp từ client không nên quyết định trực tiếp quota bảo vệ API.

Một deadline do nghiệp vụ xác định có thể cần mốc thời gian riêng. Nhưng đối với tốc độ request đến server, nguồn thời gian phía hạ tầng đáng tin cậy thường phù hợp hơn.

## 14. TTL và quản lý bộ nhớ

Mỗi subject mới có thể tạo một Redis key. Nếu API phục vụ hàng triệu IP hoặc account, keyspace rate limiting có thể rất lớn dù mỗi key chỉ lưu ít dữ liệu.

Các script đã thiết lập TTL theo ý đồ:

| Algorithm | State | TTL gợi ý | Vì sao |
|---|---|---|---|
| Fixed window | Hash `window/count` | Khoảng window + đệm kể từ request cuối | Dọn subject không hoạt động, vẫn reset đúng khi sang window |
| Sliding log | ZSET timestamp của request được chấp nhận | Window + đệm kể từ request cuối | Dọn các member cũ; key không cần giữ khi user ngừng truy cập |
| Token bucket | Hash `tokens/updated_ms` | Thời gian nạp đầy + đệm | Khi idle đủ lâu, bucket tương đương trạng thái đầy |

Ví dụ:

```text
Fixed window 60s  → TTL khoảng 62s sau lần thử gần nhất
Sliding window 60s → TTL khoảng 61s sau lần thử gần nhất
Bucket C=10, R=2/s → TTL khoảng 6s sau lần thử gần nhất
```

**TTL không đồng nghĩa giới hạn bộ nhớ tối đa.** Một kẻ tấn công có thể tạo rất nhiều subject khác nhau (như IP giả từ proxy không tin cậy hoặc API key không xác thực) và tạo rất nhiều key mới. Hệ thống vẫn cần bảo vệ trước **high-cardinality keys**.

Các cách hạn chế:

- Chỉ lấy subject từ danh tính đã xác minh.
- Rate limit ở gateway theo nguồn kết nối, kết hợp chính sách trong ứng dụng.
- Đặt quota ở phạm vi IP subnet/tenant khi phù hợp.
- Giới hạn số subject mới được phép tạo trong một khoảng thời gian nếu cần.
- Giám sát `used_memory`, số key, eviction policy và tỉ lệ miss/expired.
- Không dùng cùng Redis instance quan trọng cho nhiều workload mà không có đánh giá capacity.

Đừng dựa vào eviction do maxmemory để thực thi quota chính xác. Nếu Redis tự xóa key limiter khi bộ nhớ áp lực, subject có thể được **reset hạn mức sớm** và có thêm quyền truy cập.

## 15. Rate limiting và Redis Cluster

Redis Cluster phân phối key theo hash slot. Những script của bài thao tác **một key**, nên phù hợp với việc route một policy state đến một slot.

Ví dụ:

```text
rl:v1:fixed:read:{u42}
rl:v1:bucket:search:{u42}
```

Hai key có cùng hash tag `{u42}` sẽ rơi vào cùng slot, hữu ích nếu sau này cần một script kết hợp quota nhiều policy cho cùng user.

Nhưng cần tránh một lỗi thiết kế: ép **mọi subject** vào một hash tag cố định như `{rate-limit}` sẽ khiến tất cả key cùng nằm trên một slot, giảm lợi ích phân phối của cluster và tạo hotspot.

Chọn hash tag theo định danh subject hoặc policy hợp lý, không tạo một slot duy nhất cho toàn bộ hệ thống.

### Redis failover ảnh hưởng quota thế nào?

Trong Redis replication thông thường, quá trình failover có thể xảy ra khi state chưa được đồng bộ đầy đủ đến replica. Nếu một primary mới không có tất cả lần cập nhật quota mới nhất, bộ đếm có thể lùi lại và cấp thêm lượt ngoài ý muốn.

Đối với rate limit bảo vệ hệ thống ở mức thông thường, độ sai lệch nhỏ có thể chấp nhận được. Với chống gian lận hoặc hạn mức bắt buộc tuyệt đối, cần thiết kế mức nhất quán, độ bền và hệ thống kiểm soát phù hợp; **Redis replication + Lua atomic không tự cung cấp quyết định quota tuyệt đối xuyên failover**.

## 16. Fail-open và fail-closed khi Redis bị lỗi

Giả sử service gọi script kiểm tra quota nhưng Redis bị timeout:

```text
HTTP request
    |
    v
Redis rate-limit check
    |
    +--> Thành công: ALLOW hoặc DENY
    |
    +--> Lỗi: có cho request đi tiếp?
```

Lựa chọn tùy tác động nghiệp vụ.

| Endpoint | Gợi ý khi Redis rate limiter lỗi | Lý do |
|---|---|---|
| Đọc trang sản phẩm công khai | Có thể fail-open có kiểm soát | Tránh mất dịch vụ vì limiter, nhưng cần bảo vệ downstream |
| Tìm kiếm tốn tài nguyên | Cân nhắc quota cục bộ hoặc giới hạn concurrency; có thể fail-closed khi tải cao | Không cho fallback gây sập database |
| Đăng nhập/OTP | Thường fail-closed hoặc cơ chế giới hạn đáng tin khác | Không được bỏ qua bảo vệ brute force |
| Tạo thanh toán/đặt chỗ | Tùy rủi ro, thường nghiêm ngặt | Không để mất kiểm soát tải/gian lận |
| API nội bộ có xác thực và SLA cao | Có thể dùng hạn mức tầng gateway dự phòng | Đảm bảo tối thiểu một lớp kiểm soát vẫn hoạt động |

**Fail-open** không có nghĩa vô hiệu hóa mọi kiểm soát an ninh. Nếu bỏ qua Redis limiter cho endpoint đọc catalog, hệ thống vẫn cần giới hạn tổng tải, authentication nếu có, circuit breaker và chính sách bảo vệ nguồn dữ liệu.

**Fail-closed** không có nghĩa mọi lỗi đều trả 429. Nếu Redis không thể trả lời nên hệ thống không biết user có vượt quota hay không, phản hồi **503 Service Unavailable** có thể chính xác hơn 429. Chỉ trả 429 khi hạn mức đã được đánh giá và xác định vượt ngưỡng.

### Retry khi Redis script timeout

Một timeout không chứng minh script chưa thực thi. Redis có thể đã trừ quota nhưng response bị mất trên đường mạng.

Nếu client/service retry cùng một phép kiểm tra, quota có thể bị trừ thêm lần nữa. Với endpoint giá trị cao, cần xác định semantics:

- Chấp nhận tiêu token thêm trong trường hợp hiếm.
- Dùng idempotency ID và lưu kết quả đánh giá theo request ID.
- Hoặc đặt một lớp khác kiểm soát việc xử lý trùng của request nghiệp vụ.

Không có thuật toán fixed/sliding/bucket nào tự giải quyết **exactly-once** cho một HTTP request đi qua mạng không đáng tin.

## 17. An toàn khi thiết kế subject theo IP, user và API key

### Theo user ID

Dùng ID lấy từ session/token đã xác thực, không dùng body hoặc query parameter do client tự kiểm soát.

```text
rateLimitKey = hash("tenantId:userId:policy")
```

Khi user có nhiều thiết bị, cùng user ID chia quota. Nếu nghiệp vụ muốn quota riêng cho từng thiết bị, cần định danh thiết bị tin cậy và chống việc client tạo vô hạn device ID mới để né hạn mức.

### Theo API key

Không đưa API key gốc vào Redis key hoặc log. Dùng một ID đã ánh xạ từ API key sau khi xác thực, hoặc băm bằng phương pháp phù hợp.

### Theo IP

IP chỉ là tín hiệu về nguồn truy cập, không nhất thiết là một người dùng. Nhiều người có thể dùng chung NAT; một người có thể thay đổi IP. Nếu dùng proxy, phải cấu hình chuỗi proxy tin cậy trước khi lấy IP thực.

Không tin trực tiếp `X-Forwarded-For` được gửi từ Internet vì attacker có thể đổi header để vượt hạn mức nếu server không chặn header không đáng tin tại gateway.

### Kết hợp nhiều chiều

Ví dụ endpoint login có thể cần quota:

- Theo tài khoản/địa chỉ đăng nhập chuẩn hóa.
- Theo IP hoặc subnet để giảm brute force phân tán.
- Theo tenant hoặc hệ thống để giới hạn tải tổng.

Hạn mức nhiều chiều cần được thiết kế như một chính sách thống nhất. Nếu kiểm tra từng key độc lập mà không chấp nhận việc tiêu quota một phần, cần một thuật toán phối hợp nguyên tử phù hợp.

## 18. Độ chính xác, burst và chi phí nghiệp vụ

Ba thuật toán không chỉ khác ở code; chúng thể hiện những **thỏa thuận với client**.

### Fixed window: dễ dự báo theo mốc thời gian

Một chính sách “tối đa 100 request trong mỗi phút đồng hồ” hợp với fixed window. Nhưng nếu backend không chịu nổi 200 request tập trung tại ranh giới phút, fixed window có thể chưa đủ.

Có thể thêm một **token bucket bảo vệ burst** bên cạnh fixed quota theo phút hoặc chuyển hẳn sang sliding window.

### Sliding window: ràng buộc trong bất kỳ khoảng N giây gần nhất

Nếu một tài khoản chỉ được thử OTP 5 lần trong 60 giây trượt, sliding log diễn đạt yêu cầu sát hơn. Nó chặn burst ở biên cửa sổ nhưng tốn bộ nhớ cho từng lần thử đã chấp nhận.

Lưu ý với OTP: việc gửi lại cùng request ID nghiệp vụ có thể cần trả lại kết quả cũ hoặc không tính lại quota theo chính sách idempotency. Đó là quyết định khác với UUID dùng làm ZSET member cho mỗi lần kiểm tra.

### Token bucket: tốc độ trung bình và burst tối đa

Giả sử:

```text
capacity = 20
refillRate = 5 token/giây
cost = 1

Người dùng đang có 20 token:
  Có thể gửi 20 request ngay.
Sau khi cạn:
  Mỗi 200ms có thể hồi phục khoảng 1 token.
```

Token bucket có tính “mềm dẻo” hơn với những ứng dụng tương tác thời gian thực: người dùng ít hoạt động tích lũy token rồi gửi một burst ngắn; người dùng gửi liên tục bị giới hạn theo refill.

Tuy nhiên, nếu nghiệp vụ yêu cầu “không bao giờ hơn 5 request trong mọi 60 giây”, bucket capacity quá lớn có thể không đáp ứng. Phải thiết lập capacity và refill dựa trên **hạn mức burst được phép**, không chỉ hạn mức trung bình mong muốn.

## 19. Dùng Redis TIME thay vì client clock: trade-off

Các Lua script gọi:

```lua
local time = redis.call('TIME')
```

và sử dụng mốc từ Redis server. Điều này giảm sự lệch nhau giữa các instance Spring Boot.

Vì thời gian được đọc **bên trong script nguyên tử**, hai phép kiểm tra quota không thể xen kẽ việc cập nhật state của cùng Redis server. Nhưng Redis server vẫn không phải đồng hồ nghiệp vụ tuyệt đối không bao giờ thay đổi. Khi cần kiểm soát deadline liên quan tới thanh toán, hợp đồng hoặc pháp lý, nên có nguồn thời gian và trạng thái nghiệp vụ độc lập.

Đồng thời, việc dùng `TIME` ở Lua script ghi state cần Redis server hỗ trợ cơ chế replication tương ứng với các lệnh không xác định trước. Các phiên bản Redis hiện đại hỗ trợ mô hình script như ví dụ; nếu dự án chạy Redis cũ hoặc một dịch vụ tương thích không đầy đủ, cần xác nhận khả năng script thực tế.

## 20. Khi Redis không phải nơi nên giữ quota duy nhất

Redis rate limiter rất hữu ích để **bảo vệ lưu lượng**, nhưng không phải mọi loại hạn mức đều nên lưu duy nhất ở Redis.

Ví dụ:

- Số lượt sử dụng gói trả phí trong tháng.
- Tổng số giao dịch được phép theo hợp đồng.
- Số lần hoàn tiền tối đa theo quy định.
- Số tài liệu đã xuất theo quota tính tiền.

Những hạn mức này có thể cần audit, reconciliation, tính bền vững và giao dịch cùng dữ liệu nghiệp vụ. Redis có thể làm lớp kiểm soát nhanh phía trước, nhưng nguồn chuẩn thường cần ở nơi có ràng buộc giao dịch và lịch sử phù hợp.

Phân biệt:

```text
Rate limit bảo vệ hạ tầng:
  "Không quá 50 req/s trên endpoint."
  → Redis phù hợp.

Quota thương mại có tính phí:
  "Chỉ được dùng tối đa 10.000 lượt theo gói tháng."
  → Cần nguồn bền vững/đối soát; Redis có thể hỗ trợ cache hoặc soft limit.
```

Nếu cần cả hai, ứng dụng có thể kiểm tra rate limit trước khi xử lý, sau đó dùng transaction của nguồn chuẩn để áp dụng quota tính phí.

## 21. Giám sát và đo lường

Một rate limiter hoạt động đúng về thuật toán nhưng cấu hình sai vẫn có thể gây ảnh hưởng lớn: chặn nhầm người dùng, tạo hotspot Redis hoặc quá tải nguồn dữ liệu khi mất limiter.

Các metric nên có:

| Metric | Dùng để làm gì |
|---|---|
| `rate_limit_allowed_total` | Số yêu cầu đã cấp quyền theo policy |
| `rate_limit_denied_total` | Số yêu cầu bị chặn |
| `rate_limit_error_total` | Lỗi Redis/script theo policy |
| Redis command latency | Quan sát độ trễ quyết định quota |
| Key count theo namespace | Phát hiện tăng cardinality |
| Redis memory/CPU | Dự báo capacity và hotspot |
| HTTP 429 rate | Phát hiện endpoint bị giới hạn quá mức |
| HTTP 503 do limiter | Phân biệt Redis lỗi với vượt quota |
| Business request latency | Kiểm tra tác động tổng thể |
| Auth/abuse alerts | Theo dõi thử login bất thường, scraping và DoS |

Tránh gắn nhãn metric bằng **user ID hoặc API key** cho từng chủ thể: cardinality sẽ tăng rất nhanh và có thể rò rỉ dữ liệu nhạy cảm. Thường nên gắn nhãn theo **policy name**, endpoint group, môi trường, kết quả và nhóm lỗi.

### Log sự kiện rate limit

Một log phù hợp có thể chứa:

```text
policy=otp-per-account
decision=DENY
retryAfterMs=18000
redisLatencyMs=3
traceId=...
```

Không cần log Redis key thô hay token xác thực. Nếu cần điều tra abuse theo tài khoản, dùng hệ thống truy vết có kiểm soát quyền truy cập và dữ liệu đã pseudonymize.

## 22. Các tình huống kiểm thử cần hiểu

Bài học này dùng các tình huống để làm rõ semantics. Khi triển khai ứng dụng thật, có thể xây dựng integration test với Redis phù hợp và nhiều client đồng thời.

### 22.1. Fixed window sát ranh giới

```text
Limit = 5/60s

12:00:59.900 → 5 request được chấp nhận
12:01:00.100 → thêm 5 request được chấp nhận
```

Kết quả này có thể đúng với fixed window, dù rất nhiều request xuất hiện trong 200ms. Nếu không chấp nhận hành vi đó, cần thuật toán khác hoặc lớp hạn mức burst.

### 22.2. Sliding window sau khi request cũ hết hiệu lực

```text
Limit = 3 trong 10.000ms

t=1000ms  request A ALLOW
t=2000ms  request B ALLOW
t=3000ms  request C ALLOW
t=4000ms  request D DENY

t=11001ms request E có thể ALLOW
```

Khi `t=11001ms`, entry ở `t=1000ms` đã ngoài khoảng 10.000ms gần nhất nên có thể được dọn. Nếu có request cạnh tranh khác chiếm lượt trước, kết quả có thể thay đổi.

### 22.3. Token bucket hoạt động sau thời gian idle

```text
Capacity = 4
Rate = 1 token/s
Cost = 1

t=0s: có 4 token → 4 request ALLOW
t=0s: request thứ 5 DENY
t≈1s: có gần 1 token → có thể ALLOW
t≈4s không hoạt động: bucket được nạp gần đầy
```

Độ chính xác thời gian phụ thuộc thời điểm Redis chạy script và cách biểu diễn token; không nên kiểm tra bằng điều kiện đồng hồ tuyệt đối quá chặt.

### 22.4. Nhiều instance cùng chiếm lượt cuối

```text
Quota còn một lượt.

Instance A và Instance B cùng gọi Lua script.
Redis thực thi một script trước.
Script đó thấy còn lượt và trừ quota.
Script sau thấy hết lượt và từ chối.
```

Đây là mục đích chính của việc đặt **kiểm tra và cập nhật vào một thao tác server-side nguyên tử**.

### 22.5. Redis timeout sau khi script đã xử lý

```text
Client gửi script.
Redis trừ token thành công.
Kết nối bị ngắt trước khi client đọc reply.
Client không biết request có được cấp quota hay không.
```

Nếu client tự retry script, có thể trừ token lần nữa. Cần quyết định retry/idempotency ở mức hệ thống, nhất là khi phép kiểm tra quota gắn với một thao tác có side effect.

## 23. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách tránh |
|---|---|---|
| Vượt quota khi nhiều request đồng thời | `GET → if → SET` không nguyên tử | Lua script hoặc thao tác server-side có điều kiện |
| Fixed window cho burst gần 2 × limit | Reset tại ranh giới khung | Dùng sliding/token bucket hoặc thêm burst limiter |
| Sliding log ít record hơn số request | Dùng timestamp làm ZSET member, bị trùng | Sinh member ID duy nhất cho mỗi phép kiểm tra |
| Sliding log tốn nhiều RAM | Lưu một member cho mỗi request đã chấp nhận | Giảm limit, xem biến thể counter/token bucket |
| Token bucket nạp sai tốc độ | Nhầm token/giây với token/mili giây | Chuẩn hóa đơn vị và công thức refill |
| Token bucket tăng vô hạn | Không chặn `min(capacity, ...)` | Giới hạn lượng token bằng capacity |
| Nhiều Spring instance tính khác nhau | Dùng state in-memory hoặc đồng hồ lệch | Redis chung và thời gian server trong script |
| TTL làm reset hạn mức quá sớm | EXPIRE quá ngắn so với khoảng theo dõi | TTL khớp cửa sổ/nạp đầy và chính sách |
| Key không bao giờ được dọn | Không đặt TTL cho subject đã ngừng hoạt động | EXPIRE/PEXPIRE theo policy |
| Tên key chứa API key hoặc email | Dùng định danh thô | Dùng opaque ID/hash có kiểm soát |
| Người dùng đổi IP để né hạn mức | Chỉ rate limit theo IP | Kết hợp identity, gateway và policy phù hợp |
| Bỏ qua giới hạn bằng header tự đặt | Tin `X-Forwarded-For`/`X-User-Id` từ client | Chỉ tin proxy và cơ chế auth đã cấu hình |
| Sai HTTP status khi Redis lỗi | Xem lỗi truy cập Redis là vượt quota | Dùng 503 cho lỗi khả dụng, 429 cho quota bị chặn |
| Retry sau timeout trừ token lần hai | Không có idempotency của phép đánh giá | Định nghĩa semantics retry và request ID |
| Quota user và tenant không nhất quán | Kiểm tra nhiều policy bằng script riêng | Chấp nhận trừ một phần hoặc thiết kế atomic multi-key |
| CROSSSLOT trong Redis Cluster | Một script truy cập key khác slot | Hash tag hợp lý và khai báo đúng `KEYS` |
| Redis memory tăng mạnh | Nhiều subject/key, sliding log lớn | Cardinality controls, TTL, metrics, capacity planning |
| Rate limit làm outage lan rộng | Redis lỗi nhưng fail-open không giới hạn | Bảo vệ downstream, fail-closed endpoint nhạy cảm |
| Nhầm rate limit với quota tính phí | Dùng Redis state làm nguồn duy nhất | Nguồn nghiệp vụ bền vững và đối soát |

## 24. Chọn thuật toán cho từng bài toán mẫu

### API đọc dữ liệu phổ thông

Ví dụ danh mục sản phẩm: 300 request/phút mỗi API key.

**Gợi ý:** fixed window nếu rủi ro burst biên thấp và muốn O(1) state. Nếu backend nhạy cảm với burst tức thời, thêm token bucket có capacity phù hợp.

### Thử OTP hoặc mã đăng nhập

Ví dụ tối đa 5 lần/60 giây cho một tài khoản.

**Gợi ý:** sliding window log để hạn chế các request dồn quanh ranh giới phút, kết hợp theo IP/subnet và cơ chế chống brute force khác. Không coi rate limiter là cơ chế bảo mật duy nhất.

### API tìm kiếm hoặc tạo báo cáo

Ví dụ cho phép một burst ngắn 10 request, sau đó mỗi giây phục hồi 2 lượt.

**Gợi ý:** token bucket `capacity=10`, `refill=2/s`. Đối với report nặng, đặt `cost` theo độ nặng ước lượng và giới hạn concurrency ở tầng worker.

### Dịch vụ nhiều tenant

Ví dụ mỗi user 10 request/s, mỗi tenant 100 request/s.

**Gợi ý:** có thể cần nhiều lớp rate limit, nhưng phải định nghĩa rõ cách tính quota khi một request vượt một trong các lớp. Không mặc định nhiều lời gọi Redis script riêng là một quyết định nguyên tử hợp nhất.

### Hạn mức trả phí theo tháng

Ví dụ gói dịch vụ có 10.000 lần xuất tài liệu/tháng.

**Gợi ý:** Redis rate limiter không đủ thay thế ledger nghiệp vụ có audit. Dùng database/event ledger làm nguồn chuẩn, Redis hỗ trợ lớp rate-limit/bảo vệ tải phía trước nếu phù hợp.

## 25. Ghi nhớ

Ba chiến lược có thể tóm tắt bằng **trạng thái được lưu**:

```text
Fixed window:
  key -> {windowIndex, acceptedCount}

Sliding window log:
  key -> ZSET(timestampMs -> uniqueRequestId)

Token bucket:
  key -> {tokensRemaining, lastUpdatedMs}
```

Và bằng **cách quyết định**:

```text
Fixed window:
  ALLOW nếu acceptedCount < limit trong khung hiện tại.

Sliding window:
  Xóa những request quá cũ.
  ALLOW nếu số request còn trong cửa sổ < limit.

Token bucket:
  Nạp lại token theo thời gian đã trôi qua.
  ALLOW nếu tokens >= requestCost.
```

Trong Spring Data Redis, dùng `StringRedisTemplate.execute(RedisScript, ...)` cho phép thực thi phép kiểm tra và cập nhật quota nguyên tử trên Redis. Nhưng một hệ thống rate limiting đáng tin cậy còn cần thiết kế đúng **subject**, **namespace**, **TTL**, **HTTP 429**, **chính sách lỗi Redis**, **Redis Cluster**, **retry**, **giám sát** và **giới hạn tải downstream**.

**Lựa chọn nhanh:** fixed window khi cần đơn giản và tiết kiệm, sliding window khi cần chặt theo khoảng thời gian trượt, token bucket khi muốn cho phép burst có kiểm soát và tốc độ trung bình ổn định.

### Tài liệu tham khảo

- [Spring Data Redis — Redis Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — DefaultRedisScript API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/script/DefaultRedisScript.html)
- [Redis — Rate Limiting](https://redis.io/learn/howtos/ratelimiting/)
- [Redis — Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/)
- [Redis — INCR](https://redis.io/docs/latest/commands/incr/)
- [Redis — ZADD](https://redis.io/docs/latest/commands/zadd/)
- [Redis — ZREMRANGEBYSCORE](https://redis.io/docs/latest/commands/zremrangebyscore/)
- [Redis — TIME](https://redis.io/docs/latest/commands/time/)
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [HTTP Semantics — 429 Too Many Requests (RFC 6585)](https://www.rfc-editor.org/rfc/rfc6585)

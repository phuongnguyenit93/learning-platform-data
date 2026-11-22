# Xây dựng bộ giới hạn tốc độ bằng bộ đếm và Lua trong Spring Data Redis

Một API có thể nhận hàng nghìn yêu cầu trong vài giây, dù mỗi khách hàng chỉ được phép sử dụng một số lượt nhất định. Nếu không có **rate limiter**, một người dùng gọi lặp liên tục có thể gây quá tải database, tiêu thụ tài nguyên không công bằng, làm cạn quota của dịch vụ ngoài hoặc tăng chi phí vận hành. Khi ứng dụng Spring Boot chạy nhiều instance, bộ đếm đặt trong bộ nhớ từng JVM không còn là giới hạn chung: mỗi instance đếm riêng và có thể cho phép vượt ngưỡng toàn hệ thống.

**Redis** phù hợp để chia sẻ trạng thái bộ đếm giữa nhiều instance. Tuy nhiên, mẫu Java gọi `INCR` rồi `EXPIRE` bằng hai lệnh riêng biệt có thể để lại key **không có TTL** nếu ứng dụng chết giữa hai lệnh. Mẫu `GET` rồi `SET` còn có race condition giữa nhiều worker. Ta dùng **Lua script chạy nguyên tử trên Redis server** để đọc trạng thái, kiểm tra hạn mức, tăng bộ đếm và đặt TTL trong cùng một lần gọi từ Spring Data Redis.

Bài thực hành gồm một triển khai **fixed-window counter** hoàn chỉnh với `StringRedisTemplate`, `DefaultRedisScript`, HTTP `429 Too Many Requests`, `Retry-After`, integration test bằng Testcontainers và ví dụ **sliding-window log** bằng Redis Sorted Set. Các phần sau giải thích sự đánh đổi của từng thuật toán, lựa chọn key theo identity, xử lý timeout, Redis Cluster, ACL, failover, memory và giám sát.

> Mục tiêu là **giảm lưu lượng và phân bổ công bằng theo một chính sách cụ thể**. Rate limiting trên một Redis primary không phải cam kết tuyệt đối chống mọi kiểu tấn công hoặc bảo đảm tính nhất quán tuyến tính qua failover bất đồng bộ. Những giới hạn chi phí/quota có hậu quả tài chính nghiêm trọng cần thêm cơ chế kiểm soát giao dịch tại nguồn dữ liệu authoritative.

## 1. Bài toán: giới hạn yêu cầu trên nhiều instance

Giả sử dịch vụ có ba Spring Boot instance và yêu cầu:

**Mỗi tài khoản chỉ được gọi API tạo báo cáo tối đa 5 lần trong 60 giây.**

```text
                 Client / Gateway
                       |
                Load balancer
             /         |         \
            v          v          v
         API-A        API-B       API-C
            \          |         /
             \         |        /
              v        v       v
                   Redis
         key rl:reports:{user42}
          count=3, TTL=41s
```

API-A nhận request 1, API-B nhận request 2, API-C nhận request 3; **cùng một Redis key** phải phản ánh cả ba. Khi số lượt cho phép đã hết, service trả HTTP `429` thay vì thực hiện công việc tốn tài nguyên.

### 1.1. Kết quả mong đợi

Ví dụ cho một cửa sổ:

| Request | Counter đã được chấp nhận | Quyết định | Remaining |
|---|---:|---|---:|
| 1 | 1 | Allow | 4 |
| 2 | 2 | Allow | 3 |
| 3 | 3 | Allow | 2 |
| 4 | 4 | Allow | 1 |
| 5 | 5 | Allow | 0 |
| 6 | 5 | Deny: HTTP 429 | 0 |
| 7 | 5 | Deny: HTTP 429 | 0 |
| Sau khi key hết TTL | 1 trong cửa sổ mới | Allow | 4 |

Trong chính sách của bài này, **yêu cầu bị chặn không làm tăng counter**. Đây là một lựa chọn có chủ đích, giúp bộ đếm không tăng vô hạn khi bị spam. Một số rate limiter khác đếm **mọi attempt**; cần xác định semantics trước khi viết code hoặc so sánh kết quả.

### 1.2. Đặt quota theo tài nguyên thực sự cần bảo vệ

Có nhiều chiều identity:

- `userId`: phân bổ quota theo tài khoản đã xác thực.
- `apiKeyId`: phân bổ quota cho một tích hợp bên ngoài.
- `tenantId`: giới hạn toàn bộ người dùng trong một tenant.
- `routeGroup`: các API nhẹ và API nặng có ngưỡng khác nhau.
- `IP address`: hỗ trợ giới hạn endpoint chưa đăng nhập, nhưng phải tin cậy proxy/gateway.
- `organizationId + plan`: hạn mức theo gói dịch vụ và loại công việc.

Một hệ thống thường cần **nhiều quota đồng thời**, ví dụ 10 req/giây mỗi user và 1.000 req/phút mỗi tenant. Không thể chỉ dùng một bộ đếm chung cho mọi API nếu chi phí tài nguyên khác nhau.

## 2. Chọn thuật toán phù hợp

Trước khi viết Lua, phải định nghĩa **thế nào là một cửa sổ thời gian**.

| Thuật toán | Trạng thái Redis | Đặc điểm | Hạn chế |
|---|---|---|---|
| Fixed-window counter | Một String counter có TTL cho mỗi subject/window | Nhẹ, O(1) memory theo subject đang hoạt động | Có thể dồn burst gần ranh giới hai cửa sổ |
| Sliding-window counter | Hai bucket counter, thường có trọng số | Giảm burst ranh giới, ít memory | Xấp xỉ chứ không đếm đúng mọi request trong cửa sổ trượt |
| Sliding-window log | Sorted Set chứa timestamp từng lượt được chấp nhận | Giới hạn chính xác theo cửa sổ trượt | RAM và chi phí prune tăng theo số request được giữ |
| Token bucket | Số token còn lại + thời điểm refill | Cho burst có kiểm soát, refill liên tục | Cần quản lý số thực/thời gian và TTL |
| Leaky bucket | Trạng thái hàng đợi hoặc mức nước | Làm mượt tốc độ xử lý | Có thể cần queue/scheduling thay vì chỉ trả allow/deny |

**Lựa chọn cho phần thực hành chính:** fixed-window counter vì đơn giản, dễ kiểm thử cạnh tranh và phù hợp nhiều endpoint. Ta bổ sung sliding-window log khi cần giảm tình trạng burst gần ranh giới thời gian.

### 2.1. Fixed window theo lần gọi đầu khác fixed window theo lịch

Trong bài này, cửa sổ **bắt đầu từ request được chấp nhận đầu tiên**:

```text
t=0s     Request 1 tạo key, TTL 60s
t=10s    Request 2; TTL còn ~50s
t=30s    Request 3; TTL còn ~30s
t=59s    Request 4; TTL còn ~1s
t=60s    Key hết hạn; request tiếp theo mở cửa sổ mới
```

Đây là **fixed-duration window gắn với lần truy cập đầu**, không nhất thiết trùng các mốc 00:00, 00:01 của đồng hồ UTC. Một thuật toán calendar-aligned cần key theo số hiệu cửa sổ hoặc thiết kế server-time khác, và có các rủi ro riêng về clock skew nếu phía client tự tính bucket.

### 2.2. Vấn đề burst tại ranh giới

Nếu quota 5 lần/60 giây:

```text
Cửa sổ A              Cửa sổ B
 ... 55 56 57 58 59 | 60 61 62 63 64 ...
             5 req | 5 req
```

Khách hàng có thể dùng 5 lượt sát cuối cửa sổ A rồi 5 lượt sát đầu cửa sổ B. Trong một khoảng thời gian ngắn cắt qua ranh giới, tổng có thể tới **2 × quota**. Lua bảo đảm tính nguyên tử của bộ đếm nhưng **không loại bỏ** đặc tính này của thuật toán.

Nếu endpoint không chấp nhận burst như vậy, dùng sliding window hoặc token bucket với capacity/refill phù hợp.

## 3. Vì sao GET/SET hoặc INCR/EXPIRE riêng lẻ chưa đủ?

### 3.1. Race condition của GET rồi SET

Mẫu sai:

```java
String raw = redis.opsForValue().get(key);
long current = raw == null ? 0 : Long.parseLong(raw);

if (current < limit) {
    redis.opsForValue().set(key, Long.toString(current + 1));
    return true;
}
return false;
```

Hai API instance có thể đọc đồng thời `current=4`, cùng kết luận có thể cho phép, rồi cùng ghi `5`. Kết quả Redis chỉ thấy một lượt tăng dù thực tế có hai request. Đây là **lost update**.

### 3.2. INCR đã nguyên tử, nhưng TTL vẫn có race

`INCR` là lệnh tăng số nguyên nguyên tử trên Redis primary:

```redis
INCR rl:reports:user42
EXPIRE rl:reports:user42 60
```

Giữa hai lệnh, worker có thể crash hoặc mất kết nối. Nếu chưa kịp `EXPIRE`, key mới có thể **không bao giờ tự hết hạn** và khách hàng bị chặn vĩnh viễn khi bộ đếm vượt quota.

Gọi `EXPIRE` sau **mọi** lần `INCR` thì không còn là fixed window: mỗi request có thể làm TTL trở lại 60 giây, tạo semantics gần với idle timeout và khiến client liên tục truy cập giữ key mãi.

### 3.3. MULTI/EXEC và Lua

`MULTI`/`EXEC` có thể chạy một batch lệnh nguyên tử, nhưng logic “chỉ đặt TTL khi counter được tạo lần đầu” cần **rẽ nhánh dựa trên kết quả INCR**. Với transaction thông thường, các command được xếp hàng trước khi đọc response; dùng `WATCH` có thể retry khi có tranh chấp.

Lua cho phép:

```text
Redis server:
  đọc count
  nếu count < limit:
      INCR
      nếu key vừa tạo: PEXPIRE
  trả allowed/count/TTL
```

Không có command từ client khác chen vào giữa các bước của script trên **một Redis node**. Điều này giúp duy trì bộ đếm nhất quán trong điều kiện node bình thường.

## 4. Hợp đồng dữ liệu của fixed-window rate limiter

Giả sử:

```text
Redis key:  rl:reports:{user42}:fixed:v1
Redis type: String chứa số nguyên
Limit:      5
Window:     60000 milliseconds
TTL:        60000ms từ lần request đầu tiên được chấp nhận
```

Input script:

| Tham số | Ví dụ | Ý nghĩa |
|---|---|---|
| `KEYS[1]` | `rl:reports:{user42}:fixed:v1` | Key counter |
| `ARGV[1]` | `5` | Số lượt tối đa được chấp nhận |
| `ARGV[2]` | `60000` | Thời lượng cửa sổ, milliseconds |

Output:

```text
{ allowedFlag, acceptedCount, remainingTtlMs }

{ 1, 1, 60000 }    Allow, lần 1
{ 1, 5, 43000 }    Allow, hết 5 lượt
{ 0, 5, 42000 }    Deny, count không tăng
```

`PTTL` được Redis đo khi script chạy nên con số TTL ví dụ chỉ mang tính minh họa; không nên assert chính xác 60.000 ở mọi lần gọi.

### 4.1. Vì sao key có namespace và phiên bản?

- `rl:`: nhận diện key thuộc hệ thống rate limiting.
- `reports:`: route group/chiều chính sách cần bảo vệ.
- `{user42}`: subject ổn định, với hash tag hữu ích khi có multi-policy trên Redis Cluster.
- `fixed:v1`: phân biệt thuật toán và version chính sách.

Không đưa token bí mật hoặc email/PII raw vào key nếu có thể tránh. Nếu dùng `userId`, chọn internal opaque ID; nếu muốn ẩn subject, có thể dùng HMAC ổn định với secret quản lý riêng (không chỉ hash đơn giản nếu ID dễ đoán). Không để client tự gửi `userId` chưa xác thực rồi tự chọn bộ đếm của người khác.

## 5. Lua script fixed window: kiểm tra và tăng nguyên tử

Script sau **không tăng counter đối với yêu cầu bị từ chối**. Nếu một key cũ bất ngờ tồn tại mà **không có TTL**, script báo lỗi thay vì âm thầm tạo một quota không có vòng đời.

```lua
-- fixed_window.lua
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local windowMs = tonumber(ARGV[2])

if not limit or limit < 1 or limit ~= math.floor(limit) then
    return redis.error_reply('Invalid rate limit')
end
if not windowMs or windowMs < 1
        or windowMs ~= math.floor(windowMs) then
    return redis.error_reply('Invalid window milliseconds')
end

local value = redis.call('GET', key)

if value then
    local count = tonumber(value)
    if not count or count < 0 then
        return redis.error_reply('Corrupted rate-limit counter')
    end

    local ttl = redis.call('PTTL', key)
    if ttl < 0 then
        return redis.error_reply('Counter exists without valid TTL')
    end

    if count >= limit then
        -- Bị chặn: giữ nguyên count và expiration.
        return {0, count, ttl}
    end
end

local current = redis.call('INCR', key)
if current == 1 then
    redis.call('PEXPIRE', key, windowMs)
end

local remainingTtl = redis.call('PTTL', key)
if remainingTtl < 0 then
    return redis.error_reply('Rate-limit TTL invariant violated')
end

return {1, current, remainingTtl}
```

### 5.1. Diễn biến script

**Lượt 1:** `GET` không thấy key, `INCR` tạo giá trị `1`, `PEXPIRE` đặt TTL, trả allow.

**Lượt 2–5:** `GET` thấy `count < 5` và TTL hợp lệ; `INCR` tăng, không đổi thời điểm hết hạn ban đầu.

**Lượt 6 trở đi:** `count >= 5`; script trả deny nhưng **không tăng bộ đếm, không reset TTL**.

**Sau TTL:** Redis coi key là hết hạn; lượt mới tạo counter `1` và mở cửa sổ mới.

### 5.2. Vì sao kiểm tra `PTTL = -1`?

`PTTL key` có các kết quả:

| Giá trị | Ý nghĩa |
|---|---|
| Không âm | Key tồn tại, còn từng ấy milliseconds |
| `-1` | Key tồn tại nhưng không có expiration |
| `-2` | Key không tồn tại |

Một counter không có TTL có thể xuất hiện do code legacy hoặc thao tác thủ công. Thay vì “đếm mãi mãi”, script xem đó là **vi phạm bất biến** và trả lỗi để vận hành điều tra. Một triển khai khác có thể sửa bằng `PEXPIRE`, nhưng phải nêu chính sách rõ và tránh che lỗi dữ liệu cũ.

### 5.3. Lua atomic không có nghĩa Lua là transaction rollback

Redis thực thi script không bị command khác chen vào, nhưng nếu script **đã thay đổi dữ liệu rồi sau đó phát sinh lỗi runtime**, Redis không tự rollback các thay đổi đó như SQL transaction. Vì vậy nên **kiểm tra kiểu dữ liệu, tham số và điều kiện trước khi ghi**, giữ script ngắn và dùng một số ít lệnh O(1).

Ở script này, các kiểm tra và trường hợp deny diễn ra trước `INCR`; lệnh tăng và đặt TTL chỉ thực thi khi cần admit.

## 6. Thử trực tiếp trên Redis CLI

Tạo một Redis lab riêng và dùng key:

```text
rl:lab:{user42}:fixed:v1
```

Trong Redis CLI, `EVAL` nhận source Lua, số lượng key, danh sách key rồi các arguments:

```redis
EVAL "local c=redis.call('INCR',KEYS[1]); if c==1 then redis.call('PEXPIRE',KEYS[1],tonumber(ARGV[2])) end; local ttl=redis.call('PTTL',KEYS[1]); if c>tonumber(ARGV[1]) then return {0,c,ttl} else return {1,c,ttl} end" 1 rl:lab:{user42}:fixed:v1 5 60000
```

Lệnh một dòng này là **biến thể đơn giản đếm cả request bị từ chối** để minh họa EVAL trên CLI; **không cùng semantics** với script đầy đủ ở mục 5. Trong bài thực hành chính, lưu script mục 5 vào `fixed_window.lua` và chạy:

```bash
redis-cli -h 127.0.0.1 -p 6379 \
  --eval fixed_window.lua 'rl:lab:{user42}:fixed:v1' , 5 60000
```

Lặp sáu lần nhanh hơn 60 giây. Kỳ vọng các lần 1–5 có `allowedFlag=1` và lần 6 `allowedFlag=0`. Kiểm tra:

```redis
GET rl:lab:{user42}:fixed:v1
PTTL rl:lab:{user42}:fixed:v1
TYPE rl:lab:{user42}:fixed:v1
```

Theo script đầy đủ, count phải dừng ở `5` khi bị deny. Không chạy `FLUSHALL` để reset chỉ một bài lab; dùng `UNLINK`/`DEL` đúng key test nếu được phép.

### 6.1. Script cache và EVALSHA

`SCRIPT LOAD` có thể nạp script rồi trả SHA1; `EVALSHA` thực thi script đã được cache:

```redis
SCRIPT LOAD "return 1"
```

Spring Data Redis `DefaultRedisScript`/`ScriptExecutor` thường **ưu tiên EVALSHA rồi fallback EVAL** khi cần. Sau `SCRIPT FLUSH` hoặc failover, script cache có thể không còn; ứng dụng phải cho phép đường fallback hoặc dùng cơ chế Redis Functions/version quản lý khác.

Không nhét dynamic request/user ID vào **source code Lua** mỗi lần request. Hãy giữ script cố định, truyền key qua `KEYS`, limit/window/member qua `ARGV`; Redis có thể tái sử dụng script cache và nội dung không phụ thuộc từng client.

## 7. Tạo project Spring Boot cho bài thực hành

Mục tiêu môi trường ví dụ: Java 17, Spring Boot 3.x, Spring Data Redis 3.x, Redis 7.x. Với phiên bản khác, đối chiếu API/dependency thực tế.

### 7.1. Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
```

Nếu dự án có Spring Security, tích hợp quota sau khi xác thực hoặc tại filter/gateway có thể xác định identity đáng tin. Phần demo controller bên dưới sử dụng `Principal` từ cơ chế authentication của ứng dụng; không tự cho phép client chọn ID thay người khác.

### 7.2. application.yml

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

Redis production nên dùng TLS, ACL username/password, secret manager và mạng private phù hợp. Script rate limit phải chạy trên **data node**, không phải Redis Sentinel endpoint.

### 7.3. Có cần thêm bean StringRedisTemplate?

Với Spring Boot starter Redis, auto-configuration thường tạo `StringRedisTemplate` và `RedisConnectionFactory` nếu chưa override. Nếu cấu hình một template riêng, cần bảo đảm key và arguments được mã hóa bằng String/UTF-8 để Redis nhận đúng key `rl:...` và số thập phân trong `ARGV`.

## 8. Spring service hoàn chỉnh: RateLimitService

Đây là triển khai đồng bộ với một script cố định. Kết quả trả về chứa:

- `allowed`: có được đi tiếp tới business logic không;
- `limit`: quota cấu hình;
- `used`: số lượt **đã được chấp nhận** trong cửa sổ;
- `remaining`: số lượt còn lại;
- `resetAfter`: thời gian tới lúc key hết hạn, tính theo phản hồi của Redis.

```java
package example.ratelimit;

import java.time.Duration;
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class RateLimitService {

    private static final String SCRIPT_TEXT = """
        local key = KEYS[1]
        local limit = tonumber(ARGV[1])
        local windowMs = tonumber(ARGV[2])

        if not limit or limit < 1
                or limit ~= math.floor(limit) then
            return redis.error_reply('Invalid rate limit')
        end
        if not windowMs or windowMs < 1
                or windowMs ~= math.floor(windowMs) then
            return redis.error_reply('Invalid window milliseconds')
        end

        local raw = redis.call('GET', key)
        if raw then
            local count = tonumber(raw)
            if not count or count < 0 then
                return redis.error_reply('Corrupted rate-limit counter')
            end
            local ttl = redis.call('PTTL', key)
            if ttl < 0 then
                return redis.error_reply('Counter exists without valid TTL')
            end
            if count >= limit then
                return {0, count, ttl}
            end
        end

        local current = redis.call('INCR', key)
        if current == 1 then
            redis.call('PEXPIRE', key, windowMs)
        end
        local ttl = redis.call('PTTL', key)
        if ttl < 0 then
            return redis.error_reply('Rate-limit TTL invariant violated')
        end
        return {1, current, ttl}
        """;

    // RedisScript<List> trả về mảng các số nguyên Redis.
    @SuppressWarnings("rawtypes")
    private static final DefaultRedisScript<List> SCRIPT =
            new DefaultRedisScript<>(SCRIPT_TEXT, List.class);

    private final StringRedisTemplate redis;

    public RateLimitService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public record Decision(
            boolean allowed,
            int limit,
            long used,
            long remaining,
            Duration resetAfter) {
    }

    public Decision check(
            String subjectId, int limit, Duration window) {

        // Dùng opaque ID ổn định được lấy từ trusted authentication.
        if (subjectId == null ||
                !subjectId.matches("[A-Za-z0-9_-]{1,80}")) {
            throw new IllegalArgumentException("Invalid subject ID");
        }
        if (limit < 1 || limit > 1_000_000) {
            throw new IllegalArgumentException("Invalid limit");
        }
        if (window == null || window.isNegative() ||
                window.isZero()) {
            throw new IllegalArgumentException("Invalid window");
        }

        long windowMs = window.toMillis();
        if (windowMs < 1 ||
                windowMs > Duration.ofDays(1).toMillis()) {
            throw new IllegalArgumentException("Window out of range");
        }

        String key =
                "rl:reports:{" + subjectId + "}:fixed:v1";

        List<?> reply = redis.execute(
                SCRIPT,
                List.of(key),
                Integer.toString(limit),
                Long.toString(windowMs));

        if (reply == null || reply.size() != 3) {
            throw new IllegalStateException(
                    "Unexpected Redis rate-limit reply");
        }

        long allowFlag = asLong(reply.get(0));
        long used = asLong(reply.get(1));
        long ttlMs = asLong(reply.get(2));

        if ((allowFlag != 0 && allowFlag != 1)
                || used < 0 || ttlMs < 0) {
            throw new IllegalStateException(
                    "Invalid rate-limit state");
        }

        return new Decision(
                allowFlag == 1,
                limit,
                used,
                Math.max(0, (long) limit - used),
                Duration.ofMillis(ttlMs));
    }

    private static long asLong(Object raw) {
        if (!(raw instanceof Number number)) {
            throw new IllegalStateException(
                    "Expected Redis integer, got: " + raw);
        }
        return number.longValue();
    }
}
```

**Quan trọng:**

1. `DefaultRedisScript<List>` gắn một source script cố định với kiểu kết quả Redis array. Spring Data Redis 3.x có thể trả những phần tử số dạng `Long`, vì thế đọc qua `Number` thay vì cast `Integer`.
2. `StringRedisTemplate` đảm bảo arguments `"5"`, `"60000"` và key là chuỗi, phù hợp script.
3. `subjectId` được xác nhận theo pattern cho phép. Production có thể dùng ID tài khoản nội bộ, không nhận ID trực tiếp từ request header không đáng tin.
4. `limit` và `window` được kiểm tra cả ở Java và Lua. Java giới hạn API policy, Lua ngăn một caller khác gửi ARGV bất hợp lệ.
5. Với TTL gần hết, `PTTL` vẫn có thể khác 0 theo timing; đừng dùng Duration này như mốc thời gian chính xác tuyệt đối của một giao dịch tài chính.
6. Khi Redis timeout hoặc script lỗi, method **ném exception**. Chọn fail-open/fail-closed ở **tầng policy**; không âm thầm coi lỗi Redis là “còn quota”.

### 8.1. Vì sao không tạo RedisScript mới cho mỗi request?

`DefaultRedisScript` lưu SHA1/source script để executor có thể dùng script cache. Tạo script mới với source có thay đổi theo từng request làm tăng overhead và mất lợi ích cache; một static singleton/bean giữ source ổn định là cách phổ biến.

Nếu ứng dụng cần quản lý script trong classpath, có thể dùng `RedisScript.of(new ClassPathResource("scripts/fixed_window.lua"), List.class)` theo API Spring Data Redis version được sử dụng. Bài minh họa inline để tự chứa trong một đoạn code.

## 9. Tích hợp với HTTP 429 và Retry-After

HTTP `429 Too Many Requests` báo client gửi quá nhiều yêu cầu. Header `Retry-After` có thể chứa số giây nên đợi trước khi thử lại. Ngoài ra có thể phát `X-RateLimit-Limit` và `X-RateLimit-Remaining` để client chủ động điều tiết.

Ví dụ controller khi endpoint đã có authentication đáng tin cậy:

```java
package example.ratelimit;

import java.security.Principal;
import java.time.Duration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reports")
public class ReportController {

    private final RateLimitService limiter;

    public ReportController(RateLimitService limiter) {
        this.limiter = limiter;
    }

    @GetMapping
    public ResponseEntity<String> generate(Principal principal) {
        // Endpoint phải được bảo vệ bởi authentication thật.
        // principal.getName() ở ví dụ phải là opaque ID
        // phù hợp pattern trong RateLimitService.
        if (principal == null) {
            return ResponseEntity.status(401)
                    .body("Authentication required");
        }

        RateLimitService.Decision decision = limiter.check(
                principal.getName(),
                5,
                Duration.ofSeconds(60));

        if (!decision.allowed()) {
            long remainingMs = decision.resetAfter().toMillis();
            long retrySeconds =
                    Math.max(1L, (remainingMs + 999L) / 1000L);

            return ResponseEntity.status(429)
                    .header(HttpHeaders.RETRY_AFTER,
                            Long.toString(retrySeconds))
                    .header("X-RateLimit-Limit",
                            Integer.toString(decision.limit()))
                    .header("X-RateLimit-Remaining", "0")
                    .body("Too many requests");
        }

        // Sau khi được phép mới thực thi công việc tốn chi phí.
        // Đây là payload demo; business service thực tế được gọi ở đây.
        return ResponseEntity.ok()
                .header("X-RateLimit-Limit",
                        Integer.toString(decision.limit()))
                .header("X-RateLimit-Remaining",
                        Long.toString(decision.remaining()))
                .body("Report accepted");
    }
}
```

### 9.1. Gắn limiter ở đâu trong request lifecycle?

Có nhiều lựa chọn:

| Vị trí | Phù hợp | Rủi ro cần xử lý |
|---|---|---|
| API gateway/ingress | Chặn sớm, bảo vệ nhiều service | Identity forwarded phải đáng tin, cấu hình route/quota |
| Servlet filter / Spring Security filter | Giới hạn hầu hết endpoint | Thứ tự authentication, async dispatch, paths miễn trừ |
| HandlerInterceptor | Gắn với MVC route | Cần chuẩn hóa route template, kết quả cho async |
| Controller/service method | Quota nghiệp vụ chi tiết | Dễ bỏ sót endpoint; đã tốn chi phí trước khi đến limiter |
| WebFlux WebFilter | Reactive gateway/app | Không block event loop, cần reactive Redis |

Demo controller dễ hiểu nhưng production thường tách policy thành filter/interceptor hoặc service boundary thống nhất. Nếu dùng Spring Security, đảm bảo limiter **nhận identity sau khi xác thực** khi quota theo user. Endpoint login trước authentication có thể dùng IP hoặc account attempt identifier đã được chuẩn hóa với chính sách riêng.

### 9.2. Retry-After không phải cam kết đặt trước một lượt

`Retry-After` tính từ TTL quan sát trong script; đến lúc client gửi lại, server time/traffic đã thay đổi. Header mang ý nghĩa hướng dẫn, không đặt chỗ quota. Client nên có jitter/backoff, tránh hàng nghìn request cùng quay lại ngay giây reset.

Nếu dùng một API có quota theo nhiều cấp, thời gian chờ có thể phải lấy từ **ràng buộc nào đang bị vi phạm lâu nhất**, không chỉ TTL của một bộ đếm.

## 10. Chọn khóa định danh để không bị lách quota

Một rate limiter đúng về nguyên tử vẫn có thể bị lách nếu người gọi tự chọn key.

### 10.1. Không dùng header tự khai báo làm danh tính

Sai nếu endpoint cho phép:

```text
X-User-Id: user-42
```

rồi dùng thẳng header đó làm Redis key. Client có thể thay thành `user-43` ở request tiếp theo để nhận quota mới.

Đúng hơn:

- Sau đăng nhập: sử dụng subject ID từ token đã xác minh hoặc security context.
- API key: dùng ID của API key đã kiểm chứng, không dùng raw secret làm key.
- IP: chỉ lấy từ trusted proxy/gateway và xử lý `Forwarded`/`X-Forwarded-For` theo danh sách proxy đáng tin. Không tin header do client Internet tự gửi.
- Tenant: xác thực quyền thành viên và scope của user trước khi tính quota tenant.

### 10.2. Giới hạn nhiều chiều

```text
rl:user:{user42}:api:reports
rl:tenant:{tenant7}:api:reports
rl:ip:{ipHash}:login
```

Nếu quota trên user và tenant đều bắt buộc, phải quyết định:

- Cho phép khi **tất cả** quota còn lượt.
- Khi một quota đã cạn, có tăng bộ đếm ở quota khác không?
- Hai policy có cần cập nhật nguyên tử để tránh “đốt quota” không đồng nhất?
- Các key có nằm trên cùng slot khi dùng Redis Cluster không?

Không đơn giản gọi `check(user)` rồi `check(tenant)` và coi đó là một transaction. Nếu user được tính một lượt nhưng tenant bị deny, một quota đã bị tiêu tốn dù request không được xử lý.

## 11. Hai quota trong cùng Lua: ý tưởng mở rộng

Nếu cần **user quota** và **route quota** cùng được cấp hoặc cùng không được cấp, một script có thể kiểm tra hai counters trước khi `INCR` cả hai.

```text
KEYS[1] = rl:{user42}:reports:short
KEYS[2] = rl:{user42}:reports:long

ARGV[1] = 5       (short limit)
ARGV[2] = 10000   (short window ms)
ARGV[3] = 100     (long limit)
ARGV[4] = 600000  (long window ms)
```

Mô hình:

```lua
-- Pseudocode thuật toán, không phải script production hoàn chỉnh.
-- 1. Validate KEYS, ARGV và kiểu/TTL của CẢ HAI keys.
-- 2. GET countShort và countLong.
-- 3. Nếu bất kỳ quota nào đầy:
--      không INCR key nào;
--      trả deny cùng TTL của quota chặn.
-- 4. Nếu cả hai còn quota:
--      INCR hai keys;
--      PEXPIRE key vừa tạo;
--      trả allow và counters/TTLs.
```

Để bảo đảm atomic trên Redis Cluster, các key mà script truy cập phải **cùng hash slot**. Hash tag chung `{user42}` giúp nhóm quota của một user cùng slot, nhưng cũng tập trung traffic của user đó vào một master. Không gom mọi user vào `{global}` nếu cần khả năng mở rộng.

Nếu quota là **user** và **tenant**, hai identity khác nhau thường map tới các slot khác nhau. Không thể giả định một Lua script cross-slot có thể cập nhật cả hai nguyên tử trong Redis Cluster. Các lựa chọn:

1. Dùng một partitioning key chung theo tenant nếu chấp nhận tải tập trung mỗi tenant.
2. Tách limiter theo chiều và chấp nhận semantics/đánh đổi rõ ràng.
3. Đặt tầng gateway/quota authoritative khác khi thật sự cần cập nhật xuyên shard có tính nhất quán mạnh.

Không lách bằng cách build tên Redis keys động trong Lua từ `ARGV` trên Cluster. Các key mà script thao tác phải được khai báo/route theo quy tắc Redis.

## 12. Fixed-window và việc đếm yêu cầu bị từ chối

Hai chính sách thường gặp:

**A. Count accepted only (bài này):**

```text
count < limit  -> INCR rồi allow
count >= limit -> deny, không INCR
```

Ưu điểm: counter giữ ở mức limit, ổn định dù có hàng triệu request bị từ chối. Hạn chế: không thể dùng chính counter để biết tổng số request bị spam; cần metric `rate_limit_rejected_total` riêng.

**B. Count every attempt:**

```text
INCR trước, nếu count > limit -> deny
```

Ưu điểm: counter phản ánh số attempts, kể cả attempts bị chặn. Hạn chế: counter tăng với mọi spam attempt, có nguy cơ overflow cực đoan và mất ý nghĩa nếu muốn quota “số lần đã sử dụng”. Với một fixed window, reject không nên liên tục reset TTL trừ khi chủ đích muốn trừng phạt prolonged attacks.

**Cả hai đều có thể hợp lệ**, nhưng kết quả `remaining`, analytics và retry policy sẽ khác. Phải ghi contract vào test và API docs.

## 13. Xây sliding-window log với Lua và Sorted Set

Nếu không chấp nhận burst ở ranh giới fixed window, lưu timestamp của **mỗi request được chấp nhận** trong một `Sorted Set`.

```text
Redis key: rl:reports:{user42}:rolling:v1

ZSET members:
  score=nowMs of req-1, member=random-uuid-1
  score=nowMs of req-2, member=random-uuid-2
  score=nowMs of req-3, member=random-uuid-3
```

Khi request mới đến:

1. Lấy Redis server time.
2. Xóa mọi member có score đã ra ngoài cửa sổ.
3. Đếm `ZCARD`.
4. Nếu count nhỏ hơn limit, `ZADD` member mới và đặt TTL.
5. Nếu count đã đầy, từ chối và tính thời gian chờ tới khi oldest event rời cửa sổ.

### 13.1. Lua sliding-window script

```lua
-- sliding_window.lua
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local windowMs = tonumber(ARGV[2])
local eventId = ARGV[3]

if not limit or limit < 1 or limit ~= math.floor(limit)
        or not windowMs or windowMs < 1
        or windowMs ~= math.floor(windowMs) then
    return redis.error_reply('Invalid policy')
end
if not eventId or eventId == '' then
    return redis.error_reply('Missing event id')
end

local time = redis.call('TIME')
local nowMs = tonumber(time[1]) * 1000
        + math.floor(tonumber(time[2]) / 1000)
local cutoff = nowMs - windowMs

-- Score <= cutoff không còn trong rolling window.
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)

local count = redis.call('ZCARD', key)
if count < limit then
    local inserted =
            redis.call('ZADD', key, 'NX', nowMs, eventId)
    if inserted ~= 1 then
        return redis.error_reply('Duplicate event id')
    end
    redis.call('PEXPIRE', key, windowMs)
    return {1, count + 1, 0}
end

local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local retryMs = math.max(
        1,
        math.floor(tonumber(oldest[2]) + windowMs - nowMs + 1)
)
return {0, count, retryMs}
```

### 13.2. Khác biệt quan trọng so với fixed window

| Khía cạnh | Fixed counter | Sliding ZSet |
|---|---|---|
| State | Một số nguyên | Một entry cho mỗi request được chấp nhận trong khoảng |
| TTL | Từ request đầu trong cửa sổ | Được đặt lại khi có request được chấp nhận |
| Khử member cũ | Key tự hết hạn | `ZREMRANGEBYSCORE` khi có request |
| Bursts ranh giới | Có | Không theo semantics rolling chính xác |
| Memory | Nhỏ, O(1) / subject | O(số request được chấp nhận còn trong window) |
| Chi phí mỗi request | Vài thao tác String O(1) | ZSet operations và dọn entries cũ |
| Retry-After | TTL key | Theo timestamp oldest member |

Script dùng `redis.call('TIME')` để các Spring instance không phụ thuộc vào đồng hồ từng JVM. Script phải được dùng trên Redis version có hỗ trợ semantics TIME với writing scripts tương ứng; ví dụ này nhắm Redis 7.x và cần kiểm thử trên server thực. Với yêu cầu time cực chính xác hoặc multi-region, cần xét giới hạn clock của Redis primary và replication.

**Cẩn trọng:** `eventId` phải duy nhất cho mỗi admission attempt. Nếu tái dùng member name, `ZADD NX` sẽ không tăng cardinality và script trả lỗi. Có thể dùng UUID v4 từ ứng dụng. Khi response Redis bị mất, retry với eventId mới có thể **đếm request hai lần**; khi dùng lại eventId cũ cần xây semantics idempotency rõ ràng thay vì chỉ mong `NX` tự xử lý mọi case.

### 13.3. Gọi sliding-window script từ Spring Data Redis

```java
import java.util.List;
import java.util.UUID;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

String lua = """
    -- Tại đây dùng nguyên source sliding_window.lua ở trên.
    """;

// Minh họa hình thức gọi; thay placeholder bằng script đầy đủ.
DefaultRedisScript<List> rollingScript =
        new DefaultRedisScript<>(lua, List.class);

String key = "rl:reports:{user42}:rolling:v1";
String eventId = UUID.randomUUID().toString();

List<?> result = strings.execute(
        rollingScript,
        List.of(key),
        "5",
        "60000",
        eventId);
```

`strings` là bean `StringRedisTemplate`. Đoạn trên minh họa API và không phải class chạy độc lập: cần dùng **source script đầy đủ**, khai báo beans/constructor trong class thực tế và đọc response theo cùng nguyên tắc với `RateLimitService`. Với production, thường đặt script ở classpath để tránh copy source thủ công.

### 13.4. Tại sao phải dùng ZSet member duy nhất?

`ZADD` cập nhật score nếu member đã tồn tại. Nếu dùng `userId` làm member thay vì request ID, một user gửi 100 requests vẫn chỉ có **một member** trong ZSet, khiến rate limiter đếm sai nghiêm trọng. Member phải phân biệt **từng request được chấp nhận**.

## 14. Khi nào token bucket tốt hơn?

Ví dụ policy “có thể burst tối đa 20 requests, sau đó phục hồi 5 token mỗi giây” phù hợp với **token bucket**:

```text
State per subject:
  availableTokens = 12.5
  lastRefillMs = 1763000000000

On request:
  nowMs = Redis TIME
  tokens = min(capacity, oldTokens + elapsed * refillRate)
  if tokens >= requestCost:
      tokens -= requestCost
      ALLOW
  else:
      DENY, retryAfter theo tốc độ refill
  persist tokens,lastRefill atomically
```

Với Lua, có thể lưu `tokens` và `lastRefillMs` trong một Hash, validate params trước khi ghi, dùng `HGET`/`HSET` cùng một script và đặt TTL đủ dài để bỏ state khi bucket đã đầy lại. Token bucket phù hợp workload có bursts tự nhiên; nhưng số thực và timestamps cần định nghĩa chính xác, nhất là khi nhiều client dùng cùng identity hoặc Redis failover.

**Không tự coi token bucket là “giới hạn chính xác X requests trong 60 giây”**. Nó giới hạn capacity và refill rate, có thể cho phép số lượt khác một fixed/rolling window dù cả ba được mô tả nôm na là “60 req/phút”.

## 15. Đặt limit và window bằng configuration

Đừng rải số `5` và `60000` khắp controller. Một thiết kế có thể có:

```yaml
app:
  rate-limit:
    reports:
      requests: 5
      window: 60s
    search:
      requests: 100
      window: 1m
```

Gắn với `@ConfigurationProperties`:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.rate-limit.reports")
public record ReportsRateLimitProperties(
        int requests,
        Duration window) {
}
```

Đăng ký qua `@EnableConfigurationProperties(ReportsRateLimitProperties.class)` hoặc configuration properties scanning, tùy dự án. Validate positive limits và durations ở startup bằng Bean Validation/config guard nếu policy từ configuration.

Nếu thay limit từ 5 thành 10 trong khi một counter cũ còn sống, value hiện tại vẫn tồn tại. Nếu giảm limit, cùng count có thể bị deny ngay; nếu đổi duration, TTL cũ không tự biến thành cửa sổ mới. Khi cần chuyển policy **không ảnh hưởng key cũ**, thay key suffix:

```text
rl:reports:{user42}:fixed:v1
rl:reports:{user42}:fixed:v2
```

Điều đó cũng **reset quota** cho mỗi user khi cutover. Hãy quyết định việc reset có chấp nhận được không và triển khai thống nhất giữa các instance; thay key suffix ở những instance khác thời điểm có thể cấp quota song song.

## 16. Retry-After, timeout và quyết định fail-open/fail-closed

Nếu Redis không phản hồi, API phải làm gì?

| Policy | Hành vi khi Redis lỗi | Khi có thể phù hợp | Rủi ro |
|---|---|---|---|
| **Fail-open** | Cho request đi tiếp có kiểm soát | API ít rủi ro, ưu tiên availability | Có thể quá tải downstream, bị abuse trong outage |
| **Fail-closed** | Từ chối/tạm ngừng request | Quota tài nguyên đắt, chống abuse nghiêm ngặt | Redis lỗi gây ảnh hưởng dịch vụ |
| **Degraded fallback** | Dùng limiter local tạm thời với cap thấp | Muốn giảm tải khi Redis lỗi | Mỗi JVM đếm riêng, không còn global cap |

Không biến timeout thành `Decision(allowed=true, remaining=...)` rồi lặng lẽ coi quota còn, nếu business đã yêu cầu fail-closed. Cũng không tự trả `429` cho **mọi lỗi Redis**: `429` thường có nghĩa khách hàng vượt giới hạn; lỗi infrastructure có thể cần `503 Service Unavailable`/`Retry-After` theo policy. Hãy phân biệt **quota exceeded** với **limiter unavailable** trên metric/log và HTTP response.

### 16.1. Unknown result khi command timeout

Trường hợp:

```text
Java ---------- EVAL ---------> Redis
Java <-- response bị mất ------ Redis đã INCR thành công
```

Client không biết lệnh đã tăng counter hay chưa. Nếu tự retry, script có thể được thực thi **lần thứ hai** và đếm hai attempts dù chỉ một HTTP request từ phía client. Với các giới hạn thông thường, hiện tượng này có thể chấp nhận hoặc cần idempotency. Với quota có giá trị tiền, cần cơ chế cấp phát/ghi bền vững hơn, hoặc một request-id ledger có cleanup và semantics rõ.

### 16.2. Timeout/budget trên request path

Lệnh limiter phải nằm trên đường nóng của HTTP request, nên:

- Kết nối Redis qua mạng nội bộ có latency đo được.
- Đặt timeout phù hợp SLO.
- Hạn chế số request đồng thời quá mức.
- Có circuit breaker hoặc fallback theo chính sách.
- Phân biệt script lỗi, connection error, permission denied, quota denied.
- Không retry vô hạn vì tăng tải đúng lúc Redis đang gặp sự cố.

## 17. Redis Cluster và lựa chọn key

Redis Cluster chia key theo hash slot. Script fixed-window chỉ dùng **một key**, nên cluster-aware driver như Lettuce có thể route tới node sở hữu slot đó.

```text
rl:reports:{user42}:fixed:v1
                  |
               hash tag
                  |
               slot S
                  |
            Master của slot S
```

Trong cùng user, hai quota dùng:

```text
rl:reports:{user42}:short
rl:reports:{user42}:long
```

có cùng hash tag và vì vậy cùng slot, thuận tiện nếu muốn dùng một Lua script cập nhật cả hai. Nhưng **không** dùng `{all}` cho mọi user: toàn bộ traffic sẽ dồn vào một slot/master.

### 17.1. Một hot key có thể quá tải một master

Nếu limiter theo một **global key**:

```text
rl:reports:global
```

và mọi request đều gọi script trên key đó, mọi lệnh đi về cùng master. Redis Cluster không tự chia **một key** thành nhiều shard. Khi tổng lưu lượng rất cao:

- Chia theo user/tenant và chỉ dùng global quota ở lớp gateway hoặc hệ thống được thiết kế riêng.
- Dùng local token bucket nhỏ để giảm tần suất gọi Redis khi có thể chấp nhận semantics.
- Không đặt Lua script O(N) trên key chịu hàng chục nghìn requests/giây.
- Đo p99 Redis command latency, CPU per master và bandwidth.

### 17.2. Nhiều key cùng script

Redis Cluster yêu cầu các key mà một script thao tác phải thỏa quy tắc hash slot và khai báo `KEYS`. Nếu user quota và tenant quota thuộc hai slot khác nhau, không thể kỳ vọng `EVAL` cập nhật cả hai nguyên tử trên Redis Cluster như một transaction SQL xuyên shard.

## 18. Redis Sentinel/replication và giới hạn an toàn

Lua script atomic trên **một Redis primary trong lúc nó chạy**. Redis Sentinel/Cluster thường sử dụng replication **bất đồng bộ**:

```text
t0  Master A chạy script, count 4 -> 5, trả ALLOW
t1  Ghi chưa kịp replicate sang Replica B
t2  Master A hỏng
t3  Replica B lên master, counter vẫn là 4
t4  Request mới có thể lại được ALLOW
```

Do đó, limiter Redis một primary có thể **cho phép vượt quota** trong một số cửa sổ failover. `WAIT` hoặc cấu hình durability có thể giảm rủi ro mất ghi ở một số trường hợp nhưng **không tự biến Redis replication thành commit tuyến tính hóa có consensus**.

Nếu quota chỉ để chống tải đột biến, mức sai lệch nhỏ trong lúc failover có thể chấp nhận. Nếu cần bảo vệ tiền, số lượng đơn hàng có quyền hạn hoặc chính sách an toàn không cho phép vượt dù một request, phải cân nhắc một **quota ledger/transactional guard** ở nguồn có bảo đảm phù hợp.

### 18.1. Multi-region

Một limiter đặt tại từng region với Redis riêng có thể cho phép mỗi region quota riêng, khiến tổng quota vượt yêu cầu global. Giải pháp phải chọn rõ:

- Quota **per region**, độc lập.
- Quota **global**, đi qua shared authority có latency/availability trade-off.
- Phân bổ trước quota cho các region, sau đó reconcile theo chính sách.

Không tuyên bố có global rate limit chỉ vì mọi region cùng dùng key string giống nhau trên **những Redis deployments độc lập**.

## 19. ACL cho Lua rate limiter

Tài khoản Redis của Spring Boot phải được phép chạy scripting command và những command mà script dùng trên đúng key:

```text
Key namespace:   ~rl:reports:*
Commands cần:   EVAL/EVALSHA (hoặc script mechanism được dùng),
                 GET, INCR, PEXPIRE, PTTL
```

Nếu sliding-window log:

```text
Key namespace:   ~rl:reports:*
Commands cần:   TIME, ZREMRANGEBYSCORE, ZCARD,
                 ZADD, PEXPIRE, ZRANGE,
                 scripting commands
```

Redis ACL có semantics theo command/key và scripting. Đừng dùng `+@all ~*` chỉ vì script báo `NOPERM`. Kiểm tra trên Redis version thực, kể cả các lệnh framework/driver gửi như `PING`/`CLIENT SETINFO` và script-cache fallback. Tài khoản ứng dụng không nên có `FLUSHALL`, `CONFIG SET` hoặc quyền xem user secrets.

**Lưu ý:** Đừng ghép raw user input vào Redis key pattern mà không xác thực identity. ACL theo `~rl:reports:*` giúp giới hạn blast radius của credential, nhưng không tự bảo vệ quota của từng user khỏi việc application tạo key với subject giả.

## 20. Testcontainers: kiểm thử Redis thật thay vì chỉ mock

Một mock `RedisTemplate` chỉ xác nhận Java code gọi method nào; nó không chứng minh `INCR` và `PEXPIRE` thực sự nguyên tử, TTL hoạt động hay hai JVM có thể chia sẻ counter.

Ví dụ sử dụng JUnit 5 + Testcontainers + Spring Boot:

```java
package example.ratelimit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class RateLimitIntegrationTest {

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

    @Autowired
    RateLimitService limiter;

    @Test
    void contextLoads() {
        // Thêm các test chức năng ở các phần tiếp theo.
    }
}
```

Testcontainers cần Docker/compatible runtime trên máy chạy test. Test class phải nằm trong một Spring Boot application context có `RateLimitService` và Redis auto-configuration. Không dùng Redis production cho load test, và không thay mã dự án chỉ vì ví dụ sử dụng image phiên bản cố định.

### 20.1. Test đơn luồng: đúng limit, remaining và reset

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.time.Duration;
import java.util.UUID;

@Test
void admitsExactlyFiveRequestsPerFreshWindow() {
    String subject = "user" +
            UUID.randomUUID().toString().replace("-", "");

    for (int i = 1; i <= 5; i++) {
        RateLimitService.Decision decision =
                limiter.check(subject, 5, Duration.ofSeconds(60));

        assertThat(decision.allowed()).isTrue();
        assertThat(decision.used()).isEqualTo(i);
        assertThat(decision.remaining()).isEqualTo(5 - i);
        assertThat(decision.resetAfter()).isPositive();
    }

    RateLimitService.Decision blocked =
            limiter.check(subject, 5, Duration.ofSeconds(60));

    assertThat(blocked.allowed()).isFalse();
    assertThat(blocked.used()).isEqualTo(5);
    assertThat(blocked.remaining()).isZero();
    assertThat(blocked.resetAfter()).isPositive();
}
```

Đặt subject mới riêng cho test thay vì dùng chung `user42`, để các test chạy song song không ảnh hưởng nhau. Ở đây `resetAfter` là `Duration`, AssertJ hỗ trợ kiểm tra thời lượng dương qua các API assertion phù hợp version; nếu thư viện dùng không có `isPositive()` cho `Duration`, so sánh `isGreaterThan(Duration.ZERO)`.

### 20.2. Test cạnh tranh: 50 tasks đồng thời, chỉ 10 lượt thành công

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

@Test
void concurrentRequestsNeverExceedLimitOnOneRedisPrimary()
        throws Exception {

    String subject = "user" +
            UUID.randomUUID().toString().replace("-", "");

    int attempts = 50;
    int quota = 10;
    ExecutorService pool = Executors.newFixedThreadPool(20);
    CountDownLatch start = new CountDownLatch(1);

    try {
        List<Future<Boolean>> results = new ArrayList<>();

        for (int i = 0; i < attempts; i++) {
            Callable<Boolean> call = () -> {
                start.await();
                return limiter.check(
                        subject, quota, Duration.ofSeconds(60))
                        .allowed();
            };
            results.add(pool.submit(call));
        }

        start.countDown();

        long allowed = 0;
        for (Future<Boolean> result : results) {
            if (result.get(10, TimeUnit.SECONDS)) {
                allowed++;
            }
        }

        assertThat(allowed).isEqualTo(quota);
    } finally {
        pool.shutdownNow();
    }
}
```

Đây là phép thử **safety dưới concurrency trên một Redis primary bình thường**, không phải bằng chứng an toàn tuyệt đối khi failover. Trong môi trường CI chậm, timeout phải được cấu hình hợp lý; không dùng `Thread.sleep` để tạo “cạnh tranh” rồi coi kết quả không tái hiện race là chứng nhận thuật toán đúng.

### 20.3. Test TTL được tạo và không bị kéo dài khi deny

Một test ý tưởng:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

String subject = "ttlTest" + UUID.randomUUID()
        .toString().replace("-", "");
String key = "rl:reports:{" + subject + "}:fixed:v1";

limiter.check(subject, 1, Duration.ofSeconds(30));
Duration initialTtl = strings.getExpire(key);

RateLimitService.Decision denied =
        limiter.check(subject, 1, Duration.ofSeconds(30));
Duration afterDenied = strings.getExpire(key);

assertThat(denied.allowed()).isFalse();
assertThat(initialTtl).isGreaterThan(Duration.ZERO);
assertThat(afterDenied).isLessThanOrEqualTo(initialTtl);
```

`strings` là bean `StringRedisTemplate`. Đưa đoạn này vào test class đã cấu hình và inject đúng bean. TTL giảm theo thời gian; đừng assert bằng đúng `Duration.ofSeconds(30)`. Không dùng `sleep(30s)` trong mỗi test để chờ expire: có thể dùng window ngắn riêng cho một integration test hoặc Redis test clock theo khả năng môi trường.

### 20.4. Test lỗi không có TTL

Kịch bản:

1. Trên Redis test, đặt `SET rl:reports:{subject}:fixed:v1 2` **không TTL**.
2. Gọi limiter với subject đó.
3. Kỳ vọng script báo lỗi bất biến, không “cho phép vô hạn” hoặc bí mật reset key.
4. Dọn đúng key test bằng tài khoản test có quyền.

Đây là bài test cho corrupt/legacy state. Nó kiểm tra cách code xử lý khi có một writer khác vi phạm contract key, không phải case bình thường.

## 21. Kiểm thử HTTP response và integration boundary

Một test với Spring MVC/MockMvc nên kiểm tra:

1. Lần gọi 1–5 được HTTP 200 (hoặc trạng thái business phù hợp).
2. Lần gọi thứ 6 trả `429`.
3. Header `Retry-After` là số giây dương.
4. `X-RateLimit-Remaining` là 0.
5. Business method **không được gọi** khi limiter deny.

Nếu dùng Spring Security trong test, tạo một authentication principal hợp lệ và subject ID ngắn, không dùng request header tùy ý để giả lập user thật. Với các endpoint authentication failure, nên quyết định rõ request `401` có bị tính quota hay không (ví dụ rate limit theo IP cho login attempt).

### 21.1. Test ba loại response khác nhau

| Điều kiện | Kết quả gợi ý |
|---|---|
| Còn quota | Xử lý request, 2xx/4xx theo business |
| Hết quota | `429 Too Many Requests` + `Retry-After` |
| Redis limiter lỗi | `503` hoặc fallback tùy policy, không ngụy trang thành quota exhausted |

Nếu downstream API trả `500` sau khi rate limiter cho phép, counter đã tiêu một lượt. Việc **hoàn lại quota** là một quyết định nghiệp vụ phức tạp, dễ tạo race nếu chỉ `DECR` sau exception. Thông thường request đã vào hệ thống được tính là một attempt được chấp nhận, ngay cả khi business operation thất bại; nếu tính theo thành công, cần thiết kế reservation/commit/refund có idempotency rõ.

## 22. Kiểm thử cố tình gây ra race ở cách làm sai

Một bài thực hành quan trọng là so sánh:

**A. GET → SET counter:** dùng hai thread và `CountDownLatch` để ép chúng cùng đọc count=4 rồi cùng ghi count=5. Kỳ vọng có hai admissions dù quota chỉ còn một.

**B. INCR → EXPIRE riêng:** trong Redis lab, thực hiện `INCR` rồi mô phỏng app chết trước `EXPIRE`; kiểm tra `PTTL=-1`. Đây là trường hợp lộ key.

**C. Lua fixed window:** 50 threads đồng thời, chỉ 10 admissions; key có TTL sau lần đầu.

Đừng mô phỏng crash bằng cách kill Redis production hoặc thay bộ đếm thật của khách hàng. Mỗi thử nghiệm phải dùng namespace riêng và Redis test riêng.

## 23. Đo hiệu năng của Lua rate limiter

Một Lua script ngắn thường giảm round trips vì đọc/kiểm tra/ghi/TTL được thực hiện trong một request Redis. Nhưng Lua vẫn chạy trong event loop Redis; **script dài hoặc lệnh O(N) có thể chặn những client khác**.

### 23.1. Những chỉ số cần đo

| Chỉ số | Vì sao quan trọng? |
|---|---|
| p50/p95/p99 thời gian `EVALSHA` | Chi phí latency của limiter trên hot path |
| `rate_limit_allowed_total` | Số request được admit theo policy |
| `rate_limit_rejected_total` | Áp lực vượt quota; không suy từ counter accepted-only |
| `rate_limit_error_total` | Redis unavailable, NOPERM, script lỗi, timeouts |
| Active limiter keys | Số subject hiện đang có cửa sổ |
| `used_memory` / memory per key | Key explosion theo user/IP/route |
| SLOWLOG, command stats | Redis script có gây slow command không? |
| CPU per Redis master | Hot key/slot có làm một shard quá tải? |
| API response p99 | Limiter có làm ảnh hưởng SLO? |
| HTTP 429 rate | Có tăng bất thường khi release policy mới không? |

Metric names trong bảng là **đề xuất instrumentation**, không phải mặc định Spring Data Redis tự tạo toàn bộ.

### 23.2. Vì sao benchmark local chưa đủ?

Giả sử một script mất 0,2 ms trên laptop, nhưng Redis production ở vùng khác và phải qua TLS, network RTT, gateway, scheduler JVM, connection pool và hạ tầng container. End-to-end latency có thể cao hơn nhiều.

Cần benchmark cùng cấu hình Redis version, topology, payload, connection pooling, traffic distribution và peak concurrency gần production. Không chạy load test lớn lên production Redis nếu chưa được phê duyệt.

### 23.3. Luôn giữ script ngắn

Tránh:

```lua
-- Phản ví dụ: không viết rate limiter như thế này.
local keys = redis.call('KEYS', 'rl:*')
for _, key in ipairs(keys) do
    -- Duyệt mọi user mỗi request: tốn tài nguyên nghiêm trọng.
end
```

Rate limiter cần O(1) hoặc mức chi phí bounded theo quota nhỏ. Với sliding-window log, `ZREMRANGEBYSCORE` có thể xóa nhiều phần tử và chi phí tăng theo số entry cũ; giới hạn event admission và đo execution time thực tế.

## 24. TTL, key explosion và bộ nhớ

Với rate limit 60 giây theo từng user, trong lý tưởng key sẽ hết hạn một thời gian sau lần truy cập cuối trong cửa sổ. Nhưng nếu một million identities khác nhau cùng gửi một request, Redis có thể tạo một million counter keys.

Ước lượng:

```text
Số subject hoạt động mỗi phút ≈ 200.000
Số keys fixed-window còn sống ≈ 200.000
Memory/key thực tế = payload counter + key bytes + Redis metadata
```

Không dự đoán RAM chỉ bằng `String.length()`. Dùng `MEMORY USAGE key`, `INFO memory`, `INFO keyspace`, `DBSIZE` trên môi trường test với tập key điển hình.

### 24.1. Chống attacker tạo identity vô hạn

Đối với endpoint chưa đăng nhập, một attacker có thể làm thay đổi `X-Forwarded-For` hoặc chuỗi key tùy ý nếu gateway không xác minh nguồn. Đây là kiểu **cardinality attack**:

```text
request-1 -> rl:ip:A
request-2 -> rl:ip:B
request-3 -> rl:ip:C
...
```

Giải pháp:

- Identity được chuẩn hóa từ thông tin đáng tin.
- Chặn abuse thô tại edge trước khi mỗi request vào Redis.
- Đặt giới hạn số key/namespace/tenant và theo dõi key growth.
- TTL ngắn theo policy, không tạo key vô hạn cho input chưa xác thực.
- Có global/range limiter với thiết kế không trở thành hot key.

### 24.2. Không dùng key count để suy ra số request

Một subject active có thể có nhiều quota key. Một key sẽ tự hết hạn. `DBSIZE` bao gồm cả key Redis khác. Key count không phải số request đã được xử lý; dùng application metrics/counters riêng.

## 25. Dữ liệu và atomicity khi failover

Lua đảm bảo **atomic read/check/write trên primary được chọn**, không đảm bảo ghi đã được replicate đến replica được promote. Với Sentinel/Cluster failover, counter gần nhất có thể bị mất.

Ví dụ:

```text
Master A: count=4 --> script admits request, count=5
                         |
                  chưa replicate
                         |
                    A bị sự cố
                         |
Replica B lên master với count=4
                         |
Request tiếp theo có thể lại được admit
```

Redis `WAIT`, `WAITAOF` hoặc persistence có thể cải thiện một số thuộc tính độ bền, nhưng **không biến shared Redis limiter thành quota ledger có đồng thuận tuyệt đối**. Dành quota giao dịch có hậu quả nghiêm trọng cho một hệ có commit/transaction semantics phù hợp.

### 25.1. Rate limiting không phải cơ chế chống mọi tấn công

Một attacker phân tán từ nhiều IP/account có thể đi dưới giới hạn riêng của mỗi identity. Rate limiter cần phối hợp WAF, authentication, abuse detection, concurrency limits, request size limits và giới hạn chi phí downstream.

Một request rất đắt có thể gây quá tải dù quota chỉ 1 req/giây; trong trường hợp đó cần **concurrency limiter**, job queue, resource-cost quota hoặc worker admission control khác.

## 26. Logging, monitoring và bảo vệ dữ liệu

Log mẫu:

```text
policy=reports-v1
subjectHash=4f9c...
decision=DENY
used=5
limit=5
retryAfterMs=29134
redisShard=slot-owner
requestId=...
```

Không log raw email, API key secret, token xác thực hoặc request payload nhạy cảm chỉ để chẩn đoán rate limit. Log metric theo policy và tenant class thay vì subject từng người nếu cardinality metric có thể quá cao.

Một dashboard hữu ích:

- Allowed/rejected/errors theo route group.
- P99 Redis Lua latency và application p99.
- Số active limiter keys; memory/evictions.
- Top N tenants theo số request (được xử lý theo chính sách privacy).
- Sự kiện Redis failover/topology changes.
- Số request được fallback khi limiter unavailable.

Khi Redis bật eviction policy như `allkeys-lru`, rate-limit keys có thể bị evict trước TTL, dẫn đến **reset quota sớm**. Với yêu cầu quota quan trọng, tách Redis deployment/namespace và chọn memory policy phù hợp; không trộn dữ liệu rate limit với cache bị evict tự do mà không đánh giá tác động.

## 27. Những lỗi triển khai phổ biến

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| `GET` rồi `SET` count | Lost update dưới concurrency | Lua atomic hoặc primitive đúng |
| `INCR` rồi `EXPIRE` hai lệnh | Crash giữa hai lệnh làm key không có TTL | Lua `INCR` + `PEXPIRE` |
| `EXPIRE` sau mọi request | TTL luôn reset, semantics khác fixed window | Đặt TTL khi key mới được tạo |
| Dùng Java local `AtomicInteger` | Mỗi instance có quota riêng | Redis shared counter |
| Dùng header `X-User-Id` chưa xác thực | Client tự chọn key để lách hạn mức | Trusted principal/API key ID |
| Dùng raw email/API key trong key | Rò dữ liệu qua Redis key/log | Opaque ID hoặc HMAC |
| Đếm request bị chặn nhưng tài liệu nói accepted-only | Remaining/count sai contract | Quy định rõ semantics và test |
| Mọi policy cùng `rl:{global}` | Hot slot/master | Partition theo subject, gateway layer |
| Hai quotas gọi hai scripts độc lập | Có thể tiêu quota một bên dù bên kia deny | One-script same-slot hoặc policy đánh đổi |
| Lua script sinh tên key từ dữ liệu tùy ý | Vi phạm Cluster key declaration/ACL | Truyền key qua KEYS rõ ràng |
| Time/window phụ thuộc đồng hồ client lệch | Window không đồng nhất giữa instances | TTL-first-hit hoặc server TIME |
| Gọi script sau auth sai vị trí | Anonymous user dùng chung quota, hoặc client giả ID | Xác định identity và vị trí filter |
| Không kiểm tra Redis errors | Vô tình fail-open/fail-closed | Policy lỗi rõ và metric riêng |
| Retry Lua sau timeout không có idempotency | Một request có thể bị đếm hai lần | Xác định retry semantics |
| Xem Redis failover là exact global quota | Có thể mất counter write | Phân tích fault model và ledger nếu cần |
| Dùng sliding ZSet với member=userId | Một user nhiều requests chỉ đếm một | Unique request event ID |
| Sliding log không prune | ZSet tăng vô hạn | Atomic prune/count/add + TTL |
| Dùng `SMEMBERS`/`KEYS *` mỗi request | Block Redis hoặc response lớn | O(1)/bounded Lua |
| Không có TTL/cleanup | Key explosion | TTL + monitoring |
| Redis eviction xóa limiter keys | Quota reset sớm | Memory policy/deployment riêng |
| Script lỗi NOPERM rồi cấp `+@all` | Vỡ least privilege | ACL đúng commands + key pattern |
| Test chỉ mock RedisTemplate | Không phát hiện race/TTL | Testcontainers và concurrency |
| Trả 429 cho lỗi infrastructure | Client hiểu nhầm là hết quota | Phân biệt 429 và 503/fallback |

## 28. Bài thực hành tự triển khai

### Lab 1 — Fixed-window Lua với 5 lần/phút

1. Tạo một Redis Standalone test.
2. Lưu script `fixed_window.lua` từ mục 5.
3. Chạy `redis-cli --eval ... , 5 60000` sáu lần.
4. Ghi lại tuple trả về mỗi lượt.
5. Xác minh lượt thứ sáu bị chặn và count vẫn `5`.
6. Kiểm tra `PTTL` không bị gia hạn do requests bị chặn.
7. Sau khi TTL hết, xác nhận request mới được admit.

### Lab 2 — So sánh GET/SET, INCR/EXPIRE và Lua

1. Viết code GET rồi SET và ép hai threads đọc cùng count trước khi ghi.
2. Quan sát lost update.
3. Chạy INCR không kịp EXPIRE trong Redis lab và xác minh PTTL=-1.
4. Thay bằng Lua; chạy test cạnh tranh 50 requests/limit 10.
5. Giải thích **atomicity** của script không đồng nghĩa bảo đảm failover.

### Lab 3 — Spring Boot HTTP 429

1. Tạo service `RateLimitService` và controller demo.
2. Cấu hình một principal test xác thực hợp lệ, có opaque subject ID.
3. Gọi endpoint năm lần, kỳ vọng còn quota.
4. Gọi lần thứ sáu, kỳ vọng 429 và `Retry-After`.
5. Xác minh business method không chạy khi deny.
6. Đổi limit trong config và xác định cần đổi policy suffix hay không.

### Lab 4 — Khách hàng dùng nhiều Spring instances

1. Chạy hai Spring Boot instances với port khác nhau và **cùng Redis test**.
2. Gọi xen kẽ A/B với cùng subject.
3. Kiểm tra quota tổng cộng vẫn không quá 5 trong cùng cửa sổ.
4. Chứng minh nếu mỗi instance dùng local counter riêng, quota có thể bị nhân đôi.

### Lab 5 — Sliding-window log

1. Tạo `sliding_window.lua` với `TIME`, `ZREMRANGEBYSCORE`, `ZCARD` và `ZADD`.
2. Gửi 5 requests vào gần cuối một khoảng tùy chọn.
3. Thử gửi 5 requests ngay sau đó.
4. So sánh kết quả fixed window và sliding window.
5. Xác nhận mỗi request được accept có **eventId duy nhất**.
6. Dùng `ZCARD`/`MEMORY USAGE` quan sát mức memory tăng theo số event.

### Lab 6 — Redis Cluster

1. Dùng Cluster test có nhiều master.
2. Kiểm tra hash slot của `rl:reports:{user42}:short` và `rl:reports:{user42}:long`.
3. Viết Lua kiểm tra hai counters trước khi commit.
4. Thử một cặp keys khác slot và quan sát hạn chế Cluster.
5. Đổi key schema theo hash tag có chủ đích, không gom mọi subject vào một slot.

### Lab 7 — ACL least privilege

1. Tạo Redis test ACL user chỉ có key pattern `~rl:reports:*`.
2. Cấp scripting, `GET`, `INCR`, `PEXPIRE`, `PTTL` theo command cần.
3. Chạy Spring integration test thành công.
4. Thử `FLUSHALL` qua `ACL DRYRUN` trên Redis 7+, xác nhận bị cấm.
5. Gỡ một command cần thiết để xem lỗi `NOPERM` và phục hồi policy tối thiểu.

### Lab 8 — Failover và fallback policy

1. Trong Sentinel/Cluster test, đo allowed/rejected trước và sau failover có kiểm soát.
2. Quan sát timeout/connection errors và các counter có thể bị rollback.
3. Chọn fail-open, fail-closed hoặc local fallback cho API không quan trọng.
4. Ghi rõ chính sách HTTP response và metric.
5. Giải thích vì sao quota tính tiền không nên chỉ dựa một Redis async-replicated counter.

## 29. Checklist trước khi đưa rate limiter vào production

**Thuật toán và hợp đồng**

1. Quota theo subject nào: user, API key, tenant, IP hay route?
2. Identity lấy từ nguồn xác thực đáng tin?
3. Fixed window bắt đầu lúc nào? Có chấp nhận boundary burst?
4. Counter đếm admitted hay attempted requests?
5. Có cần sliding window hoặc token bucket?
6. Limit và window có thể cấu hình, validate và versioned?
7. Có mô tả 429, Retry-After, remaining cho API clients?

**Redis và Lua**

8. Read/check/write/TTL diễn ra trong một Lua script nguyên tử?
9. Key có TTL và không bị gia hạn sai khi deny?
10. Script được lưu cố định, EVALSHA fallback hoạt động?
11. Không dùng script O(N) trên hot path?
12. Redis ACL chỉ cấp đúng command/key pattern?
13. Với Cluster, mọi script key hợp lệ và cùng slot khi cần?
14. Không để một global hot key quá tải master?
15. Redis memory/eviction policy có bảo vệ limiter keys?

**Tính đúng và khả dụng**

16. Có integration test Redis thật và concurrency test?
17. Có test expiration, corrupted counter, timeout, retry unknown result?
18. Có thiết kế fail-open/fail-closed/fallback có chủ đích?
19. Có chấp nhận giới hạn async replication/failover?
20. Quota tính phí/nghiệp vụ trọng yếu có authority mạnh hơn nếu cần?
21. Có bảo vệ against many-identity key explosion?
22. Có phối hợp WAF, auth, concurrency limit và downstream quotas?

**Vận hành**

23. Theo dõi allowed/rejected/error và p99 Lua latency?
24. Có dashboard active keys, memory và hot slots?
25. Có alert NOPERM, failover, script errors và sudden 429 spikes?
26. Có lịch đánh giá/nghiệm thu ngưỡng với workload thực?
27. Có runbook thay policy mà không tạo quota reset ngoài dự kiến?

## 30. Tổng kết

Bộ giới hạn tốc độ phân tán bằng Redis thường bắt đầu từ một **counter có TTL**. `INCR` tự nó nguyên tử, nhưng tách `INCR` và `EXPIRE` có cửa sổ lỗi nếu worker chết giữa hai lệnh. Một Lua script ngắn có thể **kiểm tra quota, tăng counter khi được phép, đặt `PEXPIRE` khi key mới được tạo và trả remaining TTL** trong một lần gọi từ `StringRedisTemplate`. Đây là nền tảng tốt cho fixed-window rate limiter trên nhiều Spring Boot instances.

Fixed window có ưu điểm đơn giản nhưng vẫn có burst ở ranh giới; khi yêu cầu chặt hơn, dùng sliding-window log với Sorted Set hoặc token bucket theo semantics phù hợp. Bên cạnh thuật toán, phải xác định **identity đáng tin**, cách trả HTTP 429/Retry-After, retry/timeout, multi-policy, Redis Cluster hash slot, memory/eviction và môi trường test cạnh tranh thật.

Cuối cùng, Redis Lua atomic không tự giải quyết async failover hoặc quota toàn cầu qua những Redis deployments độc lập. Với API thông thường, mức sai lệch nhỏ có thể chấp nhận; với quota ảnh hưởng tiền hoặc tài nguyên không thể hoàn tác, hãy bảo vệ quyết định tại hệ thống authoritative có transaction/consistency phù hợp.

## Tài liệu tham khảo

- [Redis — INCR](https://redis.io/docs/latest/commands/incr/): atomic counter và ví dụ rate limiter bằng INCR/EXPIRE/Lua.
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/): chạy script Lua trên Redis server.
- [Redis — PEXPIRE](https://redis.io/docs/latest/commands/pexpire/): TTL theo milliseconds.
- [Redis — PTTL](https://redis.io/docs/latest/commands/pttl/): thời gian sống còn lại và giá trị -1/-2.
- [Redis — Rate Limiting](https://redis.io/docs/latest/develop/use-cases/rate-limiter/): những thiết kế rate limiter và các trade-off.
- [Redis — Rate limiting with Java and Spring](https://redis.io/tutorials/rate-limiting-in-java-spring-with-redis/): ví dụ thực hành Java/Spring và Lua atomic.
- [Redis — ZADD](https://redis.io/docs/latest/commands/zadd/): Sorted Set cho sliding-window log.
- [Redis — ZREMRANGEBYSCORE](https://redis.io/docs/latest/commands/zremrangebyscore/): xóa event ngoài rolling window.
- [Redis — TIME](https://redis.io/docs/latest/commands/time/): lấy timestamp từ Redis server.
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slot và giới hạn multi-key.
- [Redis — Access Control Lists](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): lệnh và key scope của scripting user.
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html): `RedisScript` và `RedisTemplate.execute`.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): truy cập Redis, serializer và connection factory.
- [Spring Boot — Redis configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html): kết nối Spring Boot và Redis.
- [Testcontainers — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): integration test Redis với container.
- [HTTP Semantics — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585#section-4): response khi vượt giới hạn tốc độ.

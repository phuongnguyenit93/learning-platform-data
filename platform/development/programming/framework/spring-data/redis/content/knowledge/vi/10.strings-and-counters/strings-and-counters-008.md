# Phân tích tính nguyên tử khi kết hợp bộ đếm với hết hạn

## 1. Bài toán: một bộ đếm chỉ có giá trị trong khoảng thời gian nhất định

Trong Spring Data Redis, **StringRedisTemplate.opsForValue().increment(...)** là cách phổ biến để tăng bộ đếm: lượt xem, số lần đăng nhập sai, số yêu cầu API hay số lần người dùng thực hiện một thao tác. Redis thực thi phép tăng này như một **lệnh nguyên tử**. Khi hai request đồng thời tăng cùng một key, Redis không làm mất lượt tăng do hai request cùng đọc giá trị cũ rồi ghi đè lên nhau.

Nhưng nhiều bài toán còn yêu cầu **bộ đếm tự hết hạn**:

- Giới hạn tối đa 5 lần yêu cầu mã xác minh trong một khoảng 60 giây.
- Đếm số lần thử đăng nhập thất bại trong 15 phút.
- Đếm lượt truy cập của một phiên hoạt động trong 10 phút.
- Giữ bộ đếm thống kê tạm thời trong 1 ngày rồi tự dọn khỏi Redis.

Một cách viết dễ gặp là:

~~~java
Long count = redis.opsForValue().increment(key);
if (count != null && count == 1L) {
    redis.expire(key, Duration.ofSeconds(60));
}
~~~

Ý định ở đây là: khi key được tạo lần đầu, tăng bộ đếm từ 0 lên 1 và đặt TTL 60 giây; những lần tiếp theo chỉ tăng giá trị, không kéo dài thời hạn. Tuy nhiên, code có **hai lời gọi Redis riêng biệt**. Dù mỗi lời gọi đơn lẻ là nguyên tử, toàn bộ quá trình **INCR rồi EXPIRE không nguyên tử**.

Nếu ứng dụng dừng hoặc mất kết nối sau INCR mà trước EXPIRE, key có thể còn tồn tại **vĩnh viễn** vì không có TTL. Đây là lỗi tính đúng đắn, không chỉ là vấn đề hiệu năng.

Bài học giải thích chính xác phạm vi nguyên tử, các kiểu race condition, cách lựa chọn ngữ nghĩa thời gian và cách kết hợp bộ đếm với expiration một cách an toàn bằng Redis và Spring Data Redis.

## 2. Ba khái niệm cần phân biệt

### 2.1. Một lệnh Redis nguyên tử

Với một Redis key chứa số nguyên, lệnh **INCR key** tăng giá trị và trả giá trị mới. Redis xử lý toàn bộ lệnh như một thao tác không bị lệnh từ client khác chen vào giữa.

Ví dụ:

~~~text
SET lesson:counter:views 10
INCR lesson:counter:views
INCR lesson:counter:views
GET lesson:counter:views
~~~

Nếu không có client khác tác động, giá trị cuối là **12**. Nếu hai client cùng gửi INCR, mỗi INCR vẫn là một lần tăng nguyên tử. Kết quả của từng client được xác định theo thứ tự Redis thực thi.

Trong Java:

~~~java
Long next = stringRedisTemplate.opsForValue()
        .increment("lesson:counter:views");
~~~

**Long** là giá trị sau khi tăng. Ở ngữ cảnh thực thi thông thường, kết quả này có thể dùng để xác định request đang là lượt thứ mấy; trong một số chế độ pipeline/transaction, giá trị trả về có thể là null khi lệnh đang được xếp và chưa lấy kết quả.

### 2.2. Hai lệnh riêng biệt không tự nguyên tử

~~~text
INCR lesson:counter:attempts
EXPIRE lesson:counter:attempts 60
~~~

Mỗi lệnh thực hiện riêng lẻ, nên giữa chúng có thể có lệnh từ client khác, lỗi kết nối hoặc ứng dụng bị dừng. Redis không biết hai lệnh đó phải được xem như **một quy tắc nghiệp vụ duy nhất**.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Redis as Redis Server
    App->>Redis: INCR counter
    Redis-->>App: 1
    Note over App: Lỗi, timeout hoặc tiến trình dừng
    Note over Redis: Key tồn tại nhưng chưa có TTL
    App--xRedis: EXPIRE không được gửi
~~~

Vấn đề này thường được gọi là **khoảng hở giữa các thao tác**. Nó vẫn tồn tại dù Redis rất nhanh, server chỉ có một primary node hay ứng dụng sử dụng connection pool.

### 2.3. Nguyên tử không đồng nghĩa với bền vững hoặc idempotent

Một thao tác được Redis xử lý nguyên tử trước các client đồng thời **không tự bảo đảm**:

- dữ liệu không bao giờ mất khi Redis Server gặp sự cố; độ bền phụ thuộc persistence và replication;
- một request sẽ không bị thực hiện lại sau khi ứng dụng bị timeout nhưng Redis đã xử lý xong;
- Redis và database quan hệ của ứng dụng cùng commit trong một transaction phân tán;
- bộ đếm chính xác tuyệt đối nếu ứng dụng thiếu quy tắc chống xử lý trùng;
- mọi lỗi trong Redis transaction hoặc Lua script đều được rollback.

Đây là những vấn đề có liên quan nhưng cần giải quyết riêng. Khi nói **INCR + đặt TTL nguyên tử**, trước hết ta đang yêu cầu các client khác không quan sát hoặc chen vào giữa việc tăng và đặt hạn, đồng thời không để bước đầu hoàn tất mà bước sau bị bỏ quên trong đường thực thi thông thường.

## 3. Phân tích lỗi khi INCR và EXPIRE được gọi độc lập

### 3.1. Race condition giữa nhiều request

Giả sử ban đầu key **login:attempts:user42** chưa tồn tại. Hai instance Spring Boot cùng xử lý request cho user 42:

| Thời điểm | Instance A | Instance B | Trạng thái Redis |
| --- | --- | --- | --- |
| T0 | | | Key chưa tồn tại |
| T1 | INCR trả **1** | | Key = 1, TTL = -1 |
| T2 | | INCR trả **2** | Key = 2, TTL = -1 |
| T3 | Bị dừng trước EXPIRE | | Key = 2, TTL = -1 |
| T4 | | Vì count = 2 nên bỏ qua EXPIRE | Key = 2, TTL = -1 |

Ở T4, bộ đếm có thể sống mãi. Một request tiếp theo INCR nhận giá trị 3, 4, 5... và không bao giờ vào nhánh **count == 1**, khiến TTL không được sửa.

Điểm đáng chú ý: **INCR vẫn đúng về mặt số học**, nhưng quy tắc *bộ đếm phải tự hết hạn* đã bị vi phạm.

### 3.2. Chưa cần concurrency cũng xảy ra lỗi

Chỉ cần một request:

1. Redis nhận INCR và trả về 1.
2. Spring Boot mất kết nối hoặc process crash.
3. EXPIRE chưa được gửi.
4. Key còn tồn tại với TTL = -1.

Vì vậy **giảm số thread** hay chỉ chạy **một instance** không loại bỏ vấn đề.

### 3.3. Đặt EXPIRE cho mọi lần INCR làm đổi ngữ nghĩa

Để tránh key không có TTL, có người viết:

~~~java
redis.opsForValue().increment(key);
redis.expire(key, Duration.ofSeconds(60));
~~~

Giả sử một request đến mỗi 20 giây. Mỗi request lại đặt TTL thành 60 giây, nghĩa là key sẽ hết hạn **60 giây sau request gần nhất**. Nếu truy cập liên tục, key có thể không bao giờ hết hạn.

Đây là **sliding expiration/idle timeout**: thời gian sống được kéo dài sau mỗi hoạt động. Nó khác với **một cửa sổ 60 giây tính từ lần tăng đầu tiên**.

Hơn nữa, hai lệnh vẫn tách biệt. Nếu code bị gián đoạn giữa INCR và EXPIRE, hành vi của expiration vẫn phụ thuộc lịch sử request và thời điểm lỗi.

### 3.4. Đặt EXPIRE trước INCR cũng không khắc phục

~~~text
EXPIRE lesson:counter:new 60
INCR lesson:counter:new
~~~

Khi key chưa tồn tại, EXPIRE trả 0 vì không có key để đặt TTL. INCR sau đó tạo key nhưng **không có expiration**.

Đảo thứ tự hai lệnh không giải quyết được bài toán tạo key và đặt thời hạn như một đơn vị công việc.

### 3.5. SET NX với TTL rồi INCR vẫn có khoảng hở

Một biến thể khác:

~~~text
SET lesson:counter:attempts 0 EX 60 NX
INCR lesson:counter:attempts
~~~

Lệnh SET có điều kiện và TTL là nguyên tử, nên tránh được key ban đầu không có expiration. Tuy nhiên, nếu ứng dụng chết sau SET mà trước INCR, **lượt truy cập đầu tiên chưa được đếm**. Ở những đường chạy khác, request đồng thời có thể khiến cách xác định lượt đầu tiên hoặc xử lý retry khó theo dõi.

Kỹ thuật này có thể dùng khi chấp nhận ngữ nghĩa riêng của nó, nhưng **không tạo thành một lần “tăng đếm và đặt TTL” nguyên tử**.

## 4. Trước khi chọn giải pháp: cần xác định kiểu cửa sổ thời gian

Một bộ đếm có TTL có thể phục vụ các quy tắc thời gian rất khác nhau. Việc chọn thuật toán quan trọng ngang với việc chọn lệnh Redis.

| Yêu cầu | Ví dụ | Quy tắc TTL |
| --- | --- | --- |
| **Cửa sổ bắt đầu từ lần truy cập đầu** | Tối đa 5 lần trong 60 giây kể từ request đầu tiên | Đặt TTL lúc tạo key, không reset trên các lần tăng sau. |
| **Cửa sổ theo mốc lịch** | Tối đa 100 request trong mỗi phút UTC | Key gắn với phút hiện tại; TTL dùng để dọn key sau khi qua phút. |
| **Hết hạn khi không hoạt động** | Giữ trạng thái đếm tới 10 phút sau hoạt động gần nhất | Có thể chủ động gia hạn TTL sau mỗi thao tác. |
| **Sliding window chính xác hơn** | Tối đa 20 request trong bất kỳ 60 giây liên tiếp | Cần cấu trúc/thuật toán đếm theo thời điểm, không chỉ một INCR + TTL. |
| **Token bucket/leaky bucket** | Cho phép burst có giới hạn nhưng làm mượt tốc độ | Dùng trạng thái bổ sung và phép tính theo thời gian. |

Trong bài, ta tập trung vào yêu cầu đầu tiên:

> Lần đầu tăng bộ đếm tạo ra một cửa sổ sống **60 giây**. Các lần tăng tiếp theo cộng vào cùng cửa sổ và **không kéo dài TTL**. Khi key hết hạn, lần tăng mới tạo một cửa sổ mới.

Đây có thể gọi là **cửa sổ cố định theo thời điểm tạo key**, nhưng nó không nhất thiết trùng với *phút đồng hồ* (ví dụ 10:00:00–10:00:59). Khi thiết kế rate limiter, cần nói rõ mốc thời gian nào được dùng.

## 5. Giải pháp thường dùng: Lua script để INCR và PEXPIRE nguyên tử

Redis chạy Lua script như một đơn vị thực thi mà các lệnh từ client khác **không chen vào giữa các lệnh của script**. Do đó, có thể đưa quy tắc *tăng rồi đặt TTL nếu mới tạo key* vào một script.

### 5.1. Script cơ bản

~~~lua
-- KEYS[1] = key bộ đếm
-- ARGV[1] = thời gian sống tính bằng mili giây, phải > 0

local count = redis.call('INCR', KEYS[1])

if count == 1 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
end

return count
~~~

Ý nghĩa:

1. **INCR** trả giá trị bộ đếm sau khi tăng.
2. Nếu kết quả bằng 1, script biết key vừa bắt đầu một chu kỳ đếm mới trong trường hợp key chưa tồn tại trước lần tăng.
3. **PEXPIRE** đặt TTL bằng mili giây, ngay trong cùng một lần chạy script.
4. Những lần INCR tiếp theo không kéo dài TTL.
5. **return count** trả lại số lượt hiện tại cho ứng dụng để áp dụng ngưỡng cho phép.

Khi nhiều instance cùng gọi script này cho **cùng một key**, Redis xử lý từng lần thực thi theo thứ tự. Request đầu tiên được xử lý vừa tạo bộ đếm vừa đặt TTL trước khi script tiếp theo bắt đầu.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant R as Redis
    participant B as Request B
    A->>R: EVAL script(KEYS[1], 60000)
    Note over R: INCR → 1
    Note over R: PEXPIRE → 60000ms
    R-->>A: 1
    B->>R: EVAL script(KEYS[1], 60000)
    Note over R: INCR → 2, giữ TTL hiện có
    R-->>B: 2
~~~

**Giới hạn cần hiểu:** Redis Lua script không có rollback tự động đối với mọi lỗi phát sinh sau khi một lệnh ghi đã thành công. Ví dụ nếu đã INCR rồi PEXPIRE báo lỗi vì đối số TTL sai, INCR vẫn có thể đã thay đổi dữ liệu. Vì vậy phải **kiểm tra đối số trước khi ghi** và bảo đảm dữ liệu key có kiểu phù hợp.

### 5.2. Script có kiểm tra TTL đầu vào

Một phiên bản phòng vệ tốt hơn khi nhận TTL từ ứng dụng:

~~~lua
local ttlMillis = tonumber(ARGV[1])

if not ttlMillis or ttlMillis <= 0 or ttlMillis ~= math.floor(ttlMillis) then
    return redis.error_reply('TTL must be a positive integer in milliseconds')
end

local count = redis.call('INCR', KEYS[1])

if count == 1 then
    redis.call('PEXPIRE', KEYS[1], ttlMillis)
end

return count
~~~

Việc xác thực TTL thực hiện **trước INCR** để tránh thay đổi bộ đếm khi đối số không hợp lệ. Ứng dụng cũng cần kiểm tra thời gian hợp lệ trước khi gọi Redis.

Script giả định key đang không tồn tại hoặc là Redis **String chứa số nguyên hợp lệ**. Nếu key bị ghi bằng Hash hoặc String không phải số, INCR sẽ trả lỗi và không tăng. Nên dành riêng namespace bộ đếm, tránh dùng chung key với loại dữ liệu khác.

### 5.3. Kiểm chứng bằng redis-cli

Trên Redis dùng để thực hành, mở chế độ tương tác:

~~~bash
redis-cli -h 127.0.0.1 -p 6379
~~~

Chạy script rút gọn cùng với key thử nghiệm:

~~~text
EVAL "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('PEXPIRE',KEYS[1],tonumber(ARGV[1])) end; return n" 1 lesson:counter:atomic:42 60000
GET lesson:counter:atomic:42
PTTL lesson:counter:atomic:42
~~~

Lệnh **EVAL** nhận:

- Nội dung Lua script.
- Số lượng key được khai báo: **1**.
- Tên key: **lesson:counter:atomic:42**.
- ARGV[1]: **60000** mili giây.

Chạy EVAL lần thứ hai trước khi hết hạn:

~~~text
EVAL "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('PEXPIRE',KEYS[1],tonumber(ARGV[1])) end; return n" 1 lesson:counter:atomic:42 60000
GET lesson:counter:atomic:42
PTTL lesson:counter:atomic:42
~~~

Nếu không có client khác tác động, lần đầu trả 1, lần hai trả 2. **PTTL giảm theo thời gian**, thay vì bị reset lại 60000 sau lần thứ hai.

Lệnh dọn dữ liệu thử nghiệm:

~~~text
DEL lesson:counter:atomic:42
~~~

**PTTL và GET là hai lệnh đọc riêng** nên không tạo snapshot nguyên tử của cả value và TTL. Chúng phù hợp để quan sát kết quả trong bài học, nhưng không nên dùng một chuỗi GET rồi PTTL làm cơ sở quyết định nhạy cảm với concurrency.

## 6. Dùng RedisScript và StringRedisTemplate trong Spring Boot

Spring Data Redis có abstraction **RedisScript** để thực thi Lua trên Redis Server. **StringRedisTemplate** phù hợp ở đây vì key và tham số TTL đều được gửi dưới dạng String, còn kết quả INCR là số nguyên mà script trả về.

### 6.1. Cấu hình Redis trong Spring Boot

Ví dụ dùng Gradle và Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

Phải có một Redis Server đang chạy tại endpoint này. Với môi trường container, Redis Cluster, ACL hoặc TLS, thay cấu hình theo hạ tầng thực tế. Không đưa mật khẩu thật vào source.

### 6.2. Khai báo RedisScript làm bean tái sử dụng

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class CounterScriptConfiguration {

    @Bean
    RedisScript<Long> expiringCounterScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText("""
                local ttlMillis = tonumber(ARGV[1])
                if not ttlMillis or ttlMillis <= 0
                   or ttlMillis ~= math.floor(ttlMillis) then
                    return redis.error_reply('Invalid TTL')
                end

                local count = redis.call('INCR', KEYS[1])
                if count == 1 then
                    redis.call('PEXPIRE', KEYS[1], ttlMillis)
                end
                return count
                """);
        script.setResultType(Long.class);
        return script;
    }
}
~~~

Khai báo script một lần giúp Spring Data Redis quản lý nội dung và SHA của script theo cơ chế thực thi được hỗ trợ; với môi trường phù hợp, thư viện có thể tận dụng **EVALSHA** và fallback khi script chưa nằm trong cache của Redis. Đây không phải cache dữ liệu nghiệp vụ; việc Redis lưu cache script không thay thế quy tắc TTL của bộ đếm.

### 6.3. Service tăng và đánh giá ngưỡng

~~~java
import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class LoginAttemptLimiter {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> expiringCounterScript;

    public LoginAttemptLimiter(
            StringRedisTemplate redis,
            RedisScript<Long> expiringCounterScript) {
        this.redis = redis;
        this.expiringCounterScript = expiringCounterScript;
    }

    public AttemptDecision recordAttempt(
            String userId, long maxAttempts, Duration window) {

        if (userId == null || !userId.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid userId");
        }
        if (maxAttempts <= 0) {
            throw new IllegalArgumentException("maxAttempts must be positive");
        }
        if (window == null || window.isNegative() || window.isZero()) {
            throw new IllegalArgumentException("Invalid window");
        }

        long ttlMillis = window.toMillis();
        if (ttlMillis <= 0) {
            throw new IllegalArgumentException("Window too short");
        }

        String key = "login:attempts:user:" + userId;

        Long count = redis.execute(
                expiringCounterScript,
                List.of(key),
                Long.toString(ttlMillis)
        );

        if (count == null) {
            throw new IllegalStateException("Redis returned no counter value");
        }

        return new AttemptDecision(
                count,
                count <= maxAttempts
        );
    }

    public record AttemptDecision(long attempts, boolean allowed) {}
}
~~~

Ví dụ gọi:

~~~java
var decision = limiter.recordAttempt(
        "user42",
        5,
        Duration.ofSeconds(60)
);

if (!decision.allowed()) {
    // Trả HTTP 429 hoặc áp dụng chính sách nghiệp vụ tương ứng
}
~~~

**Ý nghĩa trả về:** nếu **maxAttempts = 5**, các lượt có count từ 1 đến 5 được phép, lượt 6 trở đi bị từ chối cho tới khi cửa sổ hết hạn. Những lần bị từ chối vẫn được đếm; đây là một chính sách cụ thể, có thể thay đổi tùy nghiệp vụ.

Đoạn code giả định ứng dụng chỉ có một bean **RedisScript<Long>** phù hợp, và được gọi từ request path không sử dụng reactive event loop. Các quy tắc xử lý HTTP, audit, bảo mật tài khoản và chiến lược fallback khi Redis lỗi cần được quyết định tại tầng ứng dụng.

### 6.4. Vì sao không dùng GET rồi SET?

Một triển khai tự tăng như sau cũng không an toàn khi có concurrency:

~~~java
String current = redis.opsForValue().get(key);
long count = current == null ? 0 : Long.parseLong(current);
redis.opsForValue().set(key, Long.toString(count + 1));
~~~

Hai request có thể đọc cùng một giá trị rồi ghi đè, làm mất lượt tăng. Lệnh **INCR** giúp loại bỏ kiểu race đó, còn **Lua script** giúp mở rộng thao tác nguyên tử để bao gồm bước đặt TTL.

## 7. Một lựa chọn khác: MULTI/EXEC cùng EXPIRE NX

Trong Redis **7.0 trở lên**, lệnh **EXPIRE** hỗ trợ tùy chọn **NX**, nghĩa là chỉ đặt expiration khi key **chưa có expiration**.

Kết hợp với Redis transaction:

~~~text
MULTI
INCR lesson:counter:tx:42
EXPIRE lesson:counter:tx:42 60 NX
EXEC
~~~

Ý nghĩa:

1. MULTI bắt đầu xếp lệnh; các lời gọi trong transaction thường trả **QUEUED**.
2. INCR tạo hoặc tăng bộ đếm.
3. EXPIRE với NX chỉ gán TTL khi key chưa có TTL; key đã có TTL thì giữ nguyên thời gian hết hạn.
4. EXEC thực thi các lệnh đã xếp theo thứ tự, không cho các lệnh của client khác chen vào giữa.

Trong đường chạy bình thường với key đúng kiểu:

- Lần đầu INCR tạo key, EXPIRE NX gán TTL.
- Lần tiếp theo INCR tăng count, EXPIRE NX không reset TTL.
- Nếu client ngắt kết nối **trước EXEC**, những lệnh mới chỉ được xếp nên chưa chạy.

Vì cả hai lệnh nằm trong cùng EXEC, không còn khoảng hở ứng dụng bị dừng **giữa INCR và EXPIRE** như khi gửi hai lời gọi riêng biệt.

### 7.1. Tại sao vẫn phải phân tích lỗi?

Redis transaction **không rollback mọi lệnh đã chạy nếu có runtime error**. Ví dụ nếu key chứa chuỗi không thể INCR, lệnh INCR có thể lỗi nhưng lệnh EXPIRE vẫn được thực thi trong transaction. Cần bảo đảm key đã được dành riêng cho bộ đếm và có kiểu String hợp lệ.

Nếu client timeout hoặc mất kết nối đúng lúc EXEC được gửi, client có thể **không biết transaction đã chạy hay chưa**. Retry mù có thể làm tăng thêm bộ đếm. Đây là vấn đề **kết quả không chắc chắn sau timeout**, cần xử lý ở tầng nghiệp vụ.

**EXPIRE NX chỉ có ở Redis hỗ trợ tùy chọn này.** Với phiên bản Redis cũ hoặc yêu cầu tương thích rộng hơn, Lua script là cách phổ biến để biểu diễn điều kiện đặt expiration.

### 7.2. EXPIRE NX riêng lẻ có đủ không?

Không. Nếu code gọi:

~~~text
INCR lesson:counter:broken
EXPIRE lesson:counter:broken 60 NX
~~~

thì tuy EXPIRE NX bảo đảm không reset TTL đang có, **vẫn tồn tại khoảng hở giữa hai lệnh**, nơi ứng dụng có thể bị dừng. Chỉ thêm NX mà không dùng MULTI/EXEC hoặc cơ chế thực thi nguyên tử khác **không giải quyết triệt để lỗi key không có TTL**.

### 7.3. Nên chọn Lua hay MULTI/EXEC?

| Tiêu chí | Lua script | MULTI/EXEC + EXPIRE NX |
| --- | --- | --- |
| Redis hỗ trợ | Lua script có sẵn ở Redis hỗ trợ scripting | EXPIRE NX yêu cầu Redis 7.0+ |
| Biểu diễn điều kiện đặt TTL | Có thể đặt TTL khi count = 1 hoặc dùng điều kiện khác | EXPIRE NX đặt TTL khi key chưa có expiration |
| Phạm vi nguyên tử | Script chạy không bị client khác chen giữa các lệnh | Các lệnh trong EXEC không bị client khác chen vào |
| Trả kết quả bộ đếm | Script trả trực tiếp count | Phân tích kết quả của EXEC để lấy giá trị INCR |
| Khả năng mở rộng thuật toán | Thuận tiện khi cần thêm điều kiện trong cùng script | Dễ cho chuỗi lệnh ngắn, không có nhánh điều kiện tùy ý |
| Lỗi trong lúc thực thi | Không tự rollback những ghi đã hoàn tất | Không tự rollback mọi runtime error |

Cả hai cách đều cần chiến lược retry, kiểm tra kiểu key và vận hành Redis phù hợp. Lua thường giúp **đóng gói logic nghiệp vụ tăng và đặt TTL** thành một lời gọi có kiểu kết quả rõ ràng; MULTI/EXEC hữu ích khi điều kiện NX có sẵn và phù hợp ngữ nghĩa yêu cầu.

## 8. Những khác biệt tinh tế về TTL cần hiểu

### 8.1. TTL không phải bộ hẹn giờ ứng dụng

Redis bảo đảm key đã hết hạn không được sử dụng như một key còn sống khi truy cập. Redis cũng có cơ chế xóa key hết hạn chủ động và thụ động. Tuy nhiên, không nên hiểu là có một callback chạy đúng chính xác từng mili giây tại thời điểm TTL chạm 0.

Nếu nghiệp vụ cần **thực hiện tác vụ vào đúng một thời điểm**, TTL và sự kiện key hết hạn không phải cơ chế scheduling tin cậy thay cho job scheduler hoặc message queue thích hợp.

### 8.2. TTL có thể bị reset hoặc gỡ bỏ

Những thao tác thường gặp:

| Thao tác | Tác động thường gặp với TTL |
| --- | --- |
| INCR key | Cập nhật value, thông thường giữ TTL hiện có. |
| EXPIRE key seconds | Đặt lại thời hạn theo số giây được cung cấp. |
| PEXPIRE key milliseconds | Đặt lại thời hạn theo mili giây. |
| PERSIST key | Gỡ expiration, key trở thành không TTL. |
| SET key value | Thay value và thường gỡ TTL nếu không có tùy chọn expiration/giữ TTL. |
| SET key value EX seconds | Ghi value và đặt TTL trong một lệnh. |
| DEL key | Xóa key; TTL không còn ý nghĩa. |

Vì vậy bộ đếm được tạo đúng bởi script vẫn có thể bị một code path khác **SET ghi đè không kèm TTL**. Hãy dành namespace riêng và giới hạn những thành phần có quyền ghi key bộ đếm.

### 8.3. TTL = -1 và TTL = -2 có ý nghĩa khác nhau

Trong redis-cli:

~~~text
TTL lesson:counter:some-key
PTTL lesson:counter:some-key
~~~

Kết quả đặc biệt:

- **-1:** key có tồn tại nhưng không có expiration.
- **-2:** key không tồn tại.
- **Số không âm:** thời gian còn lại (giây với TTL; mili giây với PTTL).

Nếu key đếm mà lẽ ra luôn hết hạn lại có **TTL = -1**, cần điều tra đường ghi đã tạo hoặc gỡ TTL.

### 8.4. Script chỉ đặt TTL khi count == 1 có tự chữa key cũ bị lỗi không?

Không. Nếu một key do phiên bản code cũ tạo ra đã có giá trị **7** nhưng TTL = -1, script cơ bản tiếp tục INCR thành 8 rồi **bỏ qua PEXPIRE** vì count không bằng 1. Key vẫn không có hạn.

Nếu yêu cầu cho phép tự sửa những key không có TTL, có thể chọn biến thể:

~~~lua
local ttlMillis = tonumber(ARGV[1])
if not ttlMillis or ttlMillis <= 0
   or ttlMillis ~= math.floor(ttlMillis) then
    return redis.error_reply('Invalid TTL')
end

local count = redis.call('INCR', KEYS[1])
if count == 1 or redis.call('PTTL', KEYS[1]) == -1 then
    redis.call('PEXPIRE', KEYS[1], ttlMillis)
end
return count
~~~

Biến thể này gán TTL khi key không có hạn, ngay cả nếu count lớn hơn 1. Nó hữu ích để khôi phục trạng thái bất thường nhưng có **thay đổi ngữ nghĩa**: một key trước đó được cố ý thiết kế không hết hạn cũng sẽ được gán TTL. Chỉ dùng khi namespace và chính sách dữ liệu khẳng định **mọi bộ đếm đều phải có expiration**.

Nếu có key cũ với giá trị không hợp lệ hoặc dữ liệu đã bị reset, script không tự biết lịch sử chính xác. Khi đó phải quyết định chính sách sửa hoặc xóa key cũ, thay vì kỳ vọng Lua tự suy ra dữ liệu đã mất.

## 9. Cửa sổ theo phút đồng hồ: khác cửa sổ từ lần đầu

Ví dụ cần **giới hạn 100 request mỗi phút UTC**. Cách đơn giản là tính tên key theo một bucket thời gian:

~~~text
api:minute:2026-11-12T10:30:user42
api:minute:2026-11-12T10:31:user42
~~~

Trong Java, có thể dùng bucket số nguyên:

~~~java
long minuteBucket = Instant.now().getEpochSecond() / 60;
String key = "api:minute:" + minuteBucket + ":user:" + userId;
~~~

**Instant** thuộc **java.time.Instant**. Mỗi phút có key riêng; bộ đếm trong từng key có thể tăng bằng script nguyên tử và tự hết hạn sau một khoảng dọn dẹp, chẳng hạn 2 phút.

Tuy vậy:

- TTL không nên bị nhầm với ranh giới chính xác của phút lịch; **tên bucket** mới xác định các request được tính chung.
- Nếu server ứng dụng dùng đồng hồ lệch nhau, gần ranh giới phút có thể tạo bucket khác nhau; cần đồng bộ thời gian hoặc thiết kế dựa trên thời gian từ nguồn thống nhất.
- Mô hình fixed calendar window có thể cho phép một lượng lớn request ở cuối phút trước và thêm lượng lớn ở đầu phút sau, tạo **boundary burst**. Đây là đặc tính thuật toán, không phải lỗi atomicity.
- Nếu cần giới hạn cho **bất kỳ 60 giây liên tiếp nào**, phải cân nhắc sliding window, token bucket hoặc thuật toán phù hợp hơn.

Hash tag trong Redis Cluster cũng có thể được dùng để gom các key cùng nhóm khi một thuật toán cần nhiều key tại một slot, nhưng không nên gom toàn bộ người dùng vào một tag global gây hot slot.

## 10. Redis Cluster và phạm vi nguyên tử

Redis Cluster phân key qua **16.384 hash slot**. Script và transaction thao tác một key bộ đếm thường dễ định tuyến: client chỉ cần biết slot của key đó.

Ví dụ:

~~~text
login:attempts:{user42}
~~~

Khi thực thi script có **một KEYS[1]**, Redis Cluster có thể xác định node sở hữu slot của key. Nếu script sau này cần thêm key, chẳng hạn marker idempotency:

~~~text
login:attempts:{user42}
login:requests:{user42}:request-abc
~~~

thì các key được dùng chung cần tuân theo ràng buộc **cùng hash slot**. Cặp **{user42}** giúp cả hai key thuộc cùng slot.

Lưu ý:

- **StringRedisTemplate** vẫn cần được kết nối qua client có hiểu Redis Cluster.
- Redis Cluster không cung cấp atomic transaction trải trên nhiều slot tùy ý.
- Script phải khai báo những key cần truy cập qua danh sách **KEYS**, không tùy tiện tự tạo tên key bí mật trong script.
- Chọn hash tag vừa đủ theo nhóm cần thao tác chung. Gắn một tag như **{global}** vào mọi bộ đếm sẽ tập trung dữ liệu và tải vào một slot.
- Slot có thể đổi primary node sau reshard/failover; ứng dụng cần client xử lý topology thay đổi.

Sử dụng cùng hash tag chỉ giải quyết ràng buộc định vị key; **không bảo đảm retry không trùng hoặc độ bền dữ liệu**.

## 11. Retry, timeout và idempotency: nguyên tử chưa chắc đúng nghiệp vụ

Hãy xem trường hợp sau:

1. Spring Boot gọi script, Redis tăng bộ đếm từ 2 lên 3 và đặt/giữ TTL đúng.
2. Phản hồi từ Redis bị mất vì kết nối timeout.
3. Spring Boot không biết thao tác đã thành công hay chưa.
4. Ứng dụng retry cùng thao tác.
5. Redis tăng tiếp từ 3 lên 4.

**Mỗi script vẫn được thực thi nguyên tử**, nhưng một sự kiện nghiệp vụ bị đếm hai lần. Đây là lỗi do **retry khi kết quả chưa rõ**, không phải race giữa INCR và EXPIRE.

### 11.1. Khi nào chấp nhận at-least-once?

Với số lượt click, một vài lần đếm trùng có thể nằm trong sai số chấp nhận được. Với số lần thử OTP, quota hoặc giới hạn thanh toán, đếm trùng có thể làm người dùng bị từ chối sai; lúc này cần chính sách idempotency rõ ràng.

### 11.2. Ý tưởng dùng request ID

Ứng dụng tạo một request ID ổn định cho cùng một sự kiện nghiệp vụ, ví dụ:

~~~text
attempt:id:{user42}:req-abc
attempt:count:{user42}
~~~

Một script có thể:

1. Kiểm tra request ID đã được ghi nhận chưa.
2. Nếu đã có, trả kết quả đã ghi nhận hoặc trạng thái “đã xử lý”, không tăng lại.
3. Nếu chưa có, ghi marker request ID và tăng bộ đếm.
4. Đặt expiration phù hợp cho marker và bộ đếm trong cùng lần thực thi.

Các key phải cùng slot nếu chạy trên Redis Cluster. Đây mới là hướng thiết kế **idempotent counter**; code không nên đơn giản tách marker SETNX và INCR thành hai request độc lập rồi tuyên bố toàn bộ nghiệp vụ nguyên tử.

Nếu request ID mới cho mỗi lần retry, cơ chế idempotency sẽ không hoạt động. Nếu marker hết hạn trước khi một retry trễ tới, thao tác vẫn có thể bị đếm lại; TTL của marker phải phù hợp với cửa sổ retry và yêu cầu dữ liệu.

### 11.3. Khi Redis không khả dụng

Với rate limiter, cần chọn chính sách rõ ràng:

- **Fail-open:** Redis lỗi thì cho request đi tiếp; ưu tiên tính sẵn sàng nhưng có thể bỏ qua giới hạn.
- **Fail-closed:** Redis lỗi thì chặn request; giữ chính sách hạn chế nhưng có thể gây gián đoạn người dùng hợp lệ.
- **Fallback khác:** ví dụ giới hạn cục bộ, hệ thống dự phòng hoặc xử lý riêng cho endpoint quan trọng.

Quyết định tùy rủi ro nghiệp vụ; không nên bắt toàn bộ exception rồi luôn coi như chưa chạm ngưỡng. Lỗi Redis **không đồng nghĩa với GET null hoặc count = 0**.

## 12. Tác động của connection pool và nhiều instance

Ứng dụng có thể dùng RedisConnectionFactory/Lettuce, kết nối dùng chung hoặc pool tùy nhu cầu. Tính nguyên tử của INCR, Lua script hay EXEC được thực thi **trên Redis**, không phụ thuộc việc Spring Boot dùng một hay nhiều thread.

Với code INCR rồi EXPIRE riêng:

~~~text
Instance A -> Redis: INCR
Instance B -> Redis: INCR
Instance A -> Redis: EXPIRE
~~~

Pool lớn hơn không biến ba lệnh thành một transaction. Ngược lại, có nhiều instance khiến những interleaving dễ xuất hiện hơn.

Với script:

~~~text
Instance A -> Redis: EVAL (INCR + PEXPIRE)
Instance B -> Redis: EVAL (INCR + PEXPIRE)
~~~

Redis thực thi từng script như một đơn vị, nên không có client khác chen vào giữa INCR và PEXPIRE thuộc cùng script. Khi scale application horizontally, cần bảo đảm **tất cả instance dùng cùng tên key, cùng TTL policy và cùng Redis deployment**.

### Lưu ý về Redis persistence và replication

Nếu Redis gặp sự cố nghiêm trọng, dữ liệu vừa ghi có thể bị mất tùy cấu hình persistence, replication và failover. Bảo đảm nguyên tử trước các client concurrent **không đồng nghĩa** mỗi giá trị đã tăng sẽ chắc chắn tồn tại sau mọi loại failover.

Nếu bộ đếm có vai trò bảo mật hoặc tài chính quan trọng, cần đánh giá riêng khả năng mất dữ liệu, độ bền cần thiết và nguồn sự thật. Redis có thể phù hợp cho nhiều rate limiter, nhưng không thể suy ra yêu cầu bền vững chỉ từ việc code sử dụng Lua.

## 13. Thực hành phân tích từng cách làm bằng redis-cli

Thực hành trên Redis học tập, không dùng key của hệ thống thật. Những dòng sau chạy trong **redis-cli tương tác**.

### Bài 1: tái tạo key không có TTL

~~~text
INCR lesson:counter:bad
GET lesson:counter:bad
TTL lesson:counter:bad
~~~

Nếu key chưa tồn tại, INCR tạo count = 1 và TTL sẽ là **-1**. Đây chính là trạng thái bị bỏ lại nếu ứng dụng đã tăng nhưng chưa kịp gọi EXPIRE.

Một lần tăng tiếp:

~~~text
INCR lesson:counter:bad
TTL lesson:counter:bad
~~~

Count trở thành 2 nhưng TTL vẫn -1. Nếu code chỉ đặt EXPIRE khi count == 1, các lượt sau không khắc phục được sự cố.

### Bài 2: thấy TTL bị reset khi EXPIRE chạy mỗi lần

~~~text
SET lesson:counter:sliding 0 EX 60
TTL lesson:counter:sliding
INCR lesson:counter:sliding
EXPIRE lesson:counter:sliding 60
TTL lesson:counter:sliding
~~~

Nếu giữa hai lần quan sát có thời gian trôi qua, TTL sau EXPIRE lại trở về gần 60. Cách này phù hợp khi muốn **hết hạn sau lần hoạt động cuối**, nhưng không phù hợp với cửa sổ giữ mốc từ lần đầu.

### Bài 3: quan sát script nguyên tử

~~~text
EVAL "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('PEXPIRE',KEYS[1],60000) end; return n" 1 lesson:counter:lua
PTTL lesson:counter:lua
EVAL "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('PEXPIRE',KEYS[1],60000) end; return n" 1 lesson:counter:lua
PTTL lesson:counter:lua
GET lesson:counter:lua
~~~

Kết quả được kỳ vọng là count tăng, còn PTTL không bị reset ở lần tăng thứ hai. Đoạn này cố định TTL 60000 mili giây để tập trung quan sát tính nguyên tử của lệnh.

### Bài 4: nếu Redis hỗ trợ EXPIRE NX

~~~text
MULTI
INCR lesson:counter:tx
EXPIRE lesson:counter:tx 60 NX
EXEC
TTL lesson:counter:tx
~~~

Lặp lại transaction trước khi hết hạn:

~~~text
MULTI
INCR lesson:counter:tx
EXPIRE lesson:counter:tx 60 NX
EXEC
TTL lesson:counter:tx
~~~

TTL giảm theo thời gian, không bị reset vì key đã có expiration. Nếu Redis phiên bản cũ không hỗ trợ NX của EXPIRE, lệnh sẽ báo lỗi và ví dụ không thể áp dụng nguyên dạng.

### Bài 5: dọn key thử nghiệm

~~~text
DEL lesson:counter:bad lesson:counter:sliding lesson:counter:lua lesson:counter:tx
~~~

Lệnh DEL nhiều key ở ví dụ này phù hợp với standalone Redis. Với Redis Cluster, khi một lệnh DEL có nhiều key, chúng phải tuân thủ ràng buộc slot; có thể xóa từng key riêng hoặc dùng hash tag phù hợp nếu cần gộp nhiều key vào một lệnh.

## 14. Các triệu chứng và nguyên nhân thường gặp trong Spring Data Redis

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Bộ đếm tồn tại mãi, TTL = -1 | INCR hoàn tất nhưng EXPIRE bị bỏ qua; một code path khác gỡ TTL | Dùng Lua/EXEC nguyên tử; tìm và sửa các đường ghi; xử lý key cũ. |
| Lượt truy cập liên tục khiến key không bao giờ hết hạn | EXPIRE được gọi sau mọi INCR | Xác định muốn sliding expiration hay cửa sổ cố định từ lần đầu. |
| Count nhỏ hơn số request thực tế | Dùng GET rồi SET gây lost update, hoặc thao tác đầu chưa đếm khi tách SET NX | Dùng INCR; gộp logic liên quan vào script/transaction. |
| Count lớn hơn số sự kiện nghiệp vụ | Retry sau timeout hoặc event bị gửi trùng | Thiết kế request ID/idempotency và thời hạn marker. |
| INCR báo WRONGTYPE | Key đang là Hash/List/Set hoặc dữ liệu không phải String phù hợp | Dùng TYPE/GET, tách namespace, thống nhất serializer. |
| INCR báo giá trị không phải số nguyên | Key String chứa text/JSON hoặc giá trị sai định dạng | Kiểm tra serializer và quy ước lưu value. |
| Script chạy nhưng PTTL = -1 với key cũ | Script chỉ đặt TTL khi count == 1, key cũ đã có count > 1 | Có kế hoạch sửa key cũ; cân nhắc biến thể phát hiện PTTL -1 nếu phù hợp. |
| EVAL trên Cluster báo CROSSSLOT | Script thao tác các key thuộc slot khác nhau | Dùng KEYS rõ ràng và hash tag theo nhóm liên quan. |
| Client timeout nhưng Redis đã tăng | Không nhận được kết quả từ thao tác đã thực thi | Tránh retry mù; thiết kế idempotency nếu yêu cầu chính xác. |
| Lệnh trả null trong transaction/pipeline | Client đang xếp lệnh, chưa thu kết quả thật | Đọc danh sách kết quả sau EXEC/pipeline; không coi null là count = 0. |
| Hết hạn không phát sự kiện đúng mili giây | Redis expiration không phải scheduler thời gian thực | Không dùng key expiration làm bộ hẹn giờ nghiệp vụ chính xác. |
| Sai thời gian cửa sổ khi nhiều instance | Mỗi instance tạo key bucket khác nhau vì clock lệch | Đồng bộ thời gian hoặc dùng nguồn thời gian thống nhất. |

Khi điều tra, nên quan sát ít nhất ba thông tin **key name – count – PTTL**, đồng thời kiểm tra đường viết trong Spring Boot. Lệnh **TYPE** giúp phát hiện trường hợp cùng một key bị dùng cho cấu trúc Redis khác.

## 15. Câu hỏi phân tích tình huống

### Tình huống A: có thể giữ nguyên đoạn INCR + EXPIRE không?

Một service ghi thống kê lượt truy cập không quan trọng, chỉ chạy một instance, mỗi lượt đầu gọi INCR rồi EXPIRE. Rủi ro là gì?

**Phân tích:** dù một instance, ứng dụng có thể bị crash hoặc gặp timeout giữa hai lệnh, để lại key không có TTL. Nếu chấp nhận dọn bằng batch định kỳ thì có thể là một lựa chọn có chủ đích, nhưng khi yêu cầu rõ *mọi bộ đếm tự hết hạn*, nên gộp thao tác nguyên tử.

### Tình huống B: thêm EXPIRE sau mọi INCR có sửa được rate limiter không?

Giả sử cho tối đa 5 request trong 60 giây tính từ request đầu tiên.

**Phân tích:** EXPIRE mỗi lượt biến thời hạn thành **60 giây kể từ request cuối**, do đó không còn mốc thời gian như đề bài. Nếu request tiếp tục đến, key có thể tồn tại rất lâu và người dùng liên tục bị chặn. Cần giữ TTL ban đầu nếu mục tiêu là cửa sổ tính từ lần đầu.

### Tình huống C: MULTI/EXEC đã đủ cho mọi Redis version chưa?

Một người dùng đề xuất MULTI, INCR, EXPIRE NX, EXEC.

**Phân tích:** chuỗi này tận dụng tùy chọn NX của EXPIRE chỉ có ở Redis 7.0+. Nó phù hợp với quy tắc giữ TTL hiện có, nhưng vẫn cần xử lý key sai kiểu, lỗi lệnh lúc EXEC và kết quả không chắc chắn sau timeout. Với phiên bản Redis không hỗ trợ EXPIRE NX, phải dùng cơ chế khác.

### Tình huống D: Lua script có ngăn mọi lần đếm trùng không?

Một request được gửi, script thực thi thành công nhưng client timeout nên service retry.

**Phân tích:** script làm INCR và expiration nguyên tử, nhưng lần gọi lại là một thao tác mới. Redis không tự biết đây là cùng một sự kiện nghiệp vụ; cần idempotency key hoặc quy tắc xử lý retry phù hợp.

### Tình huống E: có nên dùng chung một key cho tổng lượt xem và quota?

Một endpoint vừa ghi tổng số lượt xem dài hạn, vừa muốn giới hạn lượt xem trong 60 giây.

**Phân tích:** đây là hai ngữ nghĩa dữ liệu khác nhau. Tổng lượt xem có thể không có TTL hoặc cần lưu bền, còn quota window phải tự hết hạn. Nên dùng **hai key/đường xử lý rõ ràng**; không nên gán TTL lên bộ đếm dài hạn chỉ để phục vụ rate limiter.

## 16. Nguyên tắc thiết kế cần ghi nhớ

1. **INCR nguyên tử đối với một lệnh, không có nghĩa INCR + EXPIRE là một thao tác nguyên tử.**
2. Nếu TTL chỉ được đặt khi count == 1, một lỗi giữa hai lệnh có thể làm key tồn tại không thời hạn.
3. Nếu EXPIRE chạy sau mọi lần tăng, đó là chính sách **gia hạn theo hoạt động**, không phải TTL cố định từ lần đầu.
4. **Lua script** cho phép thực hiện logic INCR và đặt expiration trên Redis như một đơn vị, thích hợp với nhiều instance Spring Boot dùng chung một key.
5. **MULTI/EXEC + EXPIRE NX** là lựa chọn phù hợp trong Redis 7.0+ khi muốn đặt TTL nếu key chưa có expiration, nhưng không có rollback cho mọi runtime error.
6. **Kiểm tra đầu vào và kiểu key** trước khi dựa vào script; Lua và transaction không tự sửa dữ liệu sai hoặc mọi lỗi thực thi.
7. **Atomicity, idempotency, durability và consistency giữa các hệ thống là các bảo đảm khác nhau.** Retry sau timeout và failover vẫn cần thiết kế riêng.
8. Cần xác định chính xác **cửa sổ từ lần đầu, cửa sổ theo phút, idle timeout hay sliding window** trước khi chọn thuật toán.
9. Khi dùng **Redis Cluster**, mọi key cùng tham gia một script/transaction phải đáp ứng yêu cầu cùng slot.
10. Theo dõi bộ đếm bằng **GET**, **TTL/PTTL** và **TYPE**, nhưng đừng nhầm các lệnh quan sát riêng lẻ với một ảnh chụp nguyên tử.

Điểm cốt lõi của bài học: **bộ đếm đúng không chỉ là giá trị tăng đúng, mà còn phải có vòng đời đúng**. Trong Spring Data Redis, hãy mô tả rõ quy tắc thời gian rồi gộp những thao tác bắt buộc đi cùng nhau vào cơ chế nguyên tử phù hợp. Sau đó, giải quyết riêng những giới hạn về retry, lỗi hạ tầng và dữ liệu giữa các hệ thống để hành vi bộ đếm nhất quán với yêu cầu nghiệp vụ.

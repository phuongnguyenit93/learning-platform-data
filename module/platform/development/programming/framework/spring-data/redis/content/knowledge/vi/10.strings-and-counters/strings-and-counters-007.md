# Thiết kế bộ đếm theo cửa sổ thời gian

Trong **Spring Data Redis**, một bộ đếm đơn giản thường chỉ cần `StringRedisTemplate.opsForValue().increment(key)`. Nhưng khi yêu cầu trở thành “đếm số request trong 60 giây”, “giới hạn 100 lần gọi API mỗi phút”, “thống kê đơn hàng theo giờ” hoặc “chỉ cho phép 5 lần thử trong 15 phút gần nhất”, việc tăng số nguyên chưa đủ. Ta phải quyết định **cửa sổ thời gian bắt đầu và kết thúc lúc nào, key được tạo theo thời gian ra sao, khi nào hết hạn và những thao tác nào cần nguyên tử**.

Hai cách diễn đạt dễ bị nhầm:

- **Đếm theo khoảng cố định**: “Có bao nhiêu đơn hàng từ 10:00 đến trước 10:01?” Thường dùng cho thống kê, biểu đồ, aggregation hoặc rate limiting chấp nhận làm mới hạn mức tại ranh giới phút.
- **Đếm trong khoảng thời gian trượt**: “Trong đúng 60 giây gần nhất tính tới thời điểm này có bao nhiêu request?” Cần theo dõi lịch sử tương đối với thời điểm hiện tại, không thể chỉ nhìn một bộ đếm của phút hiện hành.

Redis phù hợp với các bài toán này nhờ `INCR` nguyên tử, TTL, các lệnh thao tác String, Sorted Set và Lua script. Spring Data Redis cung cấp các API để kết hợp chúng mà ứng dụng không phải tự quản lý byte protocol.

Bài học tập trung vào **thiết kế bộ đếm có ranh giới thời gian**, bao gồm lựa chọn thuật toán, ví dụ Java/Spring, kiểm soát tính nguyên tử, các giới hạn về bộ nhớ và những tình huống xảy ra khi có nhiều instance ứng dụng.

## 1. Bắt đầu bằng yêu cầu nghiệp vụ

Trước khi tạo key, cần phân biệt những câu hỏi sau.

| Yêu cầu | Cửa sổ | Dữ liệu cần giữ | Độ chính xác cần thiết |
|---|---|---|---|
| Tổng số đơn hàng mỗi phút để vẽ biểu đồ | Phút lịch hoặc bucket 60 giây | Một số đếm trên mỗi phút | Tổng đếm theo bucket |
| Giới hạn 100 request/phút, reset đầu phút | Fixed window | Một counter/actor/bucket | Nguyên tử khi quyết định cho phép |
| Tối đa 5 lần thử trong **15 phút gần nhất** | Sliding window | Timestamp từng lần thử hoặc bucket nhỏ | Cần ranh giới trượt rõ ràng |
| Hiển thị số request trong 5 phút gần đây | Rolling buckets | Các counter phút/giây gần đây | Có thể chấp nhận sai số theo bucket |
| Giữ tốc độ xử lý ổn định, cho phép burst nhỏ | Token bucket | Số token còn lại, mốc refill | Không phải đếm một khung thời gian cố định |

**Một counter có TTL không tự trở thành sliding-window counter.** Nếu chỉ tạo `counter:user:42` rồi đặt TTL 60 giây, kết quả là một cửa sổ bắt đầu từ **thời điểm key được tạo**; nó không tự mô tả đúng 60 giây gần nhất tại mọi thời điểm.

### 1.1. Những điều cần quyết định rõ

1. Cửa sổ dài bao nhiêu: 1 giây, 60 giây, 15 phút, một giờ hay ngày lịch?
2. Khoảng thời gian là **fixed**, **rolling/sliding** hay bắt đầu từ lần hoạt động đầu tiên?
3. Cần đếm **mọi lần thử** hay chỉ những request **được chấp nhận**?
4. Một counter gắn với actor nào: user, IP, API key, tenant, sản phẩm hoặc toàn hệ thống?
5. Có cần chính xác tuyệt đối trước các lỗi mạng, retry và Redis failover hay chỉ cần gần đúng?
6. Cửa sổ cũ được giữ bao lâu để thống kê và khi nào phải xóa?
7. Khi Redis không truy cập được, API xử lý theo chính sách nào?

Các câu trả lời này quyết định cách đặt key và thuật toán. Không nên dùng một cách `INCR + EXPIRE` cho mọi bài toán.

## 2. Những nguyên tắc Redis cơ bản

### 2.1. INCR là phép tăng nguyên tử trên một key

Ví dụ:

~~~bash
redis-cli SET metrics:orders:current 0
redis-cli INCR metrics:orders:current
# (integer) 1
redis-cli INCR metrics:orders:current
# (integer) 2
redis-cli GET metrics:orders:current
# "2"
~~~

Mỗi lệnh `INCR` được Redis xử lý nguyên tử. Nếu nhiều instance Spring Boot cùng tăng **một key**, chúng không cần tải giá trị về Java rồi `set(value + 1)`.

Cách làm sau dễ mất lần tăng vì race condition:

~~~java
// Không dùng read-modify-write để tăng counter đồng thời.
String oldValue = redis.opsForValue().get(key);
long next = Long.parseLong(oldValue == null ? "0" : oldValue) + 1;
redis.opsForValue().set(key, Long.toString(next));
~~~

Hai thread có thể cùng đọc `10` và cùng ghi `11` dù thực tế đã có hai request. Hãy dùng `increment`.

Redis `INCR` thao tác với giá trị biểu diễn số nguyên theo định dạng Redis chấp nhận. Để giữ key và value dưới dạng chuỗi số, `StringRedisTemplate` thường đơn giản hơn một `RedisTemplate<String, Long>` đang dùng binary/JDK serializer.

### 2.2. INCR và EXPIRE là hai lệnh khác nhau

Một cách viết phổ biến:

~~~java
Long count = redis.opsForValue().increment(key);
if (count != null && count == 1L) {
    redis.expire(key, Duration.ofMinutes(1));
}
~~~

Vấn đề: tiến trình có thể dừng **sau INCR nhưng trước EXPIRE**. Khi đó key đầu tiên tồn tại mà không có TTL. Với counter tạo ra liên tục theo thời gian, các key “mồ côi” này có thể tích lũy.

Giải pháp khi cần tính nhất quán của thao tác tăng và gắn TTL: dùng **Lua script** để Redis chạy chúng trong cùng một lượt thực thi nguyên tử, hoặc dùng mô hình lệnh phù hợp có expiration trong cùng thao tác.

### 2.3. Atomicity không đồng nghĩa durability

Redis có thể xử lý `INCR` nguyên tử trên primary, nhưng replication thường bất đồng bộ. Trong failover, một ghi vừa được client nhận thành công vẫn có nguy cơ chưa sang replica mới. Vì thế, “counter nguyên tử” khác với “tổng đếm không bao giờ mất sự kiện”.

Nếu cần số liệu kiểm toán, thanh toán hoặc tính phí chính xác tuyệt đối, Redis có thể là tầng đếm tạm/thời gian thực; nguồn sự kiện đáng tin cậy và cơ chế đối soát vẫn cần được thiết kế riêng.

## 3. Fixed window: một counter cho mỗi khoảng thời gian cố định

Với cửa sổ 60 giây, thời gian được chia thành những bucket:

~~~text
12:00:00                 12:01:00                 12:02:00
   |--------- phút A --------|--------- phút B --------|
   + 1 request              + 1 request
   + 1 request
   + 1 request              + 1 request
   counter[A] = 3           counter[B] = 2
~~~

Cách xác định bucket cho một thời điểm Unix timestamp tính theo giây:

~~~text
bucketIndex = floor(epochSeconds / windowSeconds)

bucketStartEpochSeconds
    = floor(epochSeconds / windowSeconds) * windowSeconds
~~~

Ví dụ `epochSeconds` là một giá trị đã có (không phụ thuộc múi giờ khi dùng Unix epoch). Nếu `windowSeconds = 60`, mọi request từ đầu phút đến ngay trước phút kế tiếp có cùng `bucketStartEpochSeconds`.

Key tham khảo:

~~~text
rate:api:user:42:bucket:1893456000
rate:api:user:42:bucket:1893456060
~~~

Các số epoch ở đây chỉ để minh họa định dạng. Trong code, hãy tính trực tiếp từ timestamp thực, không hardcode.

### 3.1. Ưu và nhược điểm

**Ưu điểm:**

- Một counter trên mỗi actor đang hoạt động trong một bucket.
- Mỗi request cần một phép tăng hoặc một script ngắn.
- Dễ tổng hợp thống kê theo phút/giờ.
- Số key có thể được giữ có giới hạn bằng TTL.
- Dễ quan sát bằng Redis CLI.

**Nhược điểm lớn nhất: burst tại ranh giới cửa sổ.**

Giả sử giới hạn 100 request/phút:

~~~text
12:00:59.900 -> gửi 100 request (hết hạn mức của phút 12:00)
12:01:00.100 -> gửi 100 request (hạn mức phút 12:01 mới bắt đầu)

=> 200 request chỉ cách nhau khoảng 0,2 giây,
   dù mỗi bucket đều không vượt quá 100.
~~~

Nếu API chỉ cần hạn mức theo phút lịch, điều này có thể chấp nhận. Nếu mục tiêu là “không quá 100 request trong **bất kỳ** 60 giây”, fixed window không đáp ứng đúng ý nghĩa đó.

## 4. Thiết kế TTL cho fixed window

Tùy mục đích, TTL của counter có hai dạng.

### 4.1. Rate limiting: giữ đến cuối bucket cộng biên nhỏ

Khi mỗi key chứa counter của một phút, có thể để key hết hạn ngay sau ranh giới phút hoặc giữ thêm ít giây để quan sát.

~~~text
bucketStart = floor(nowSeconds / 60) * 60
bucketEnd   = bucketStart + 60
expireAt    = bucketEnd + 5 giây
ttlSeconds  = expireAt - nowSeconds
~~~

Ví dụ lúc 12:00:45:

~~~text
Còn 15 giây tới cuối phút
Giữ thêm 5 giây
=> TTL cần đặt khi tạo key ≈ 20 giây
~~~

**Không dùng TTL luôn bằng 60 giây** nếu mục tiêu là xóa tại ranh giới bucket. Request đầu tiên đến lúc 12:00:45 sẽ khiến key còn tồn tại đến 12:01:45, dù bucket đã kết thúc. Với key có bucket ID riêng, điều này chủ yếu gây giữ bộ nhớ dư, nhưng cũng làm khó hiểu thời điểm dọn dữ liệu.

### 4.2. Thống kê: giữ theo retention nghiệp vụ

Một counter “đơn hàng mỗi phút” có thể cần lưu 7 ngày để hiển thị biểu đồ:

~~~text
bucketEnd = 12:01:00 ngày N
expireAt  = 12:01:00 ngày N+7
~~~

TTL nên được cố định theo **cuối bucket + retention**, thay vì kéo dài mỗi lần có sự kiện muộn được ghi.

Với số liệu cần lưu lâu hơn, có thể đẩy các bucket đã đóng sang cơ sở dữ liệu phân tích rồi xóa dữ liệu ngắn hạn khỏi Redis.

## 5. Spring Data Redis: fixed-window counter nguyên tử

Ví dụ dưới đây giới hạn **100 request trong mỗi bucket 60 giây**. Chỉ request được chấp nhận mới tăng counter; nếu đã đạt hạn mức, script trả giá trị âm để biểu thị từ chối.

Ứng dụng sử dụng Spring Boot 3.x, Java 17+, Spring Data Redis và `StringRedisTemplate`.

### 5.1. Lua script tăng counter có điều kiện và đặt TTL

~~~lua
-- KEYS[1]: key chứa counter của bucket hiện tại
-- ARGV[1]: limit (> 0)
-- ARGV[2]: TTL theo giây (> 0)

local limit = tonumber(ARGV[1])
local ttlSeconds = tonumber(ARGV[2])
local current = tonumber(redis.call('GET', KEYS[1]) or '0')

if current >= limit then
    return -current
end

local updated = redis.call('INCR', KEYS[1])

if redis.call('TTL', KEYS[1]) < 0 then
    redis.call('EXPIRE', KEYS[1], ttlSeconds)
end

return updated
~~~

Trong ví dụ, key này chỉ thuộc quyền quản lý của bộ đếm, giá trị luôn là số nguyên không âm và `limit > 0`. Kết quả:

- **Số dương**: request được chấp nhận, giá trị là counter sau khi tăng.
- **Số âm**: request bị từ chối, trị tuyệt đối là số đã được chấp nhận.
- `TTL < 0`: key chưa có TTL (hoặc không tồn tại); vì `INCR` đã thực thi trước đó, nhánh này bổ sung expiration nếu thiếu.

Script chạy nguyên tử trên Redis, nên không có request khác chen vào giữa kiểm tra limit, tăng count và đặt TTL. Không cần khóa Java `synchronized`, vốn chỉ đồng bộ trong một JVM và không đủ nếu hệ thống có nhiều instance.

### 5.2. Service Java thực thi script

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class FixedWindowRateLimiter {

    private static final long WINDOW_SECONDS = 60;
    private static final long EXPIRY_GRACE_SECONDS = 5;
    private static final long LIMIT = 100;

    private static final String LUA = """
            local limit = tonumber(ARGV[1])
            local ttlSeconds = tonumber(ARGV[2])
            local current = tonumber(redis.call('GET', KEYS[1]) or '0')

            if current >= limit then
                return -current
            end

            local updated = redis.call('INCR', KEYS[1])

            if redis.call('TTL', KEYS[1]) < 0 then
                redis.call('EXPIRE', KEYS[1], ttlSeconds)
            end

            return updated
            """;

    private static final RedisScript<Long> SCRIPT = createScript();

    private final StringRedisTemplate redis;
    private final Clock clock;

    public FixedWindowRateLimiter(
            StringRedisTemplate redis, Clock clock) {
        this.redis = redis;
        this.clock = clock;
    }

    private static RedisScript<Long> createScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText(LUA);
        script.setResultType(Long.class);
        return script;
    }

    public Decision check(String userId) {
        long nowSeconds = Instant.now(clock).getEpochSecond();
        long bucketStart =
                Math.floorDiv(nowSeconds, WINDOW_SECONDS) * WINDOW_SECONDS;
        long secondsToBoundary =
                bucketStart + WINDOW_SECONDS - nowSeconds;

        String key = "rate:api:user:" + userId
                + ":bucket:" + bucketStart;

        long expiry = secondsToBoundary + EXPIRY_GRACE_SECONDS;

        Long result = redis.execute(
                SCRIPT,
                List.of(key),
                Long.toString(LIMIT),
                Long.toString(expiry)
        );

        if (result == null) {
            throw new IllegalStateException("Redis returned no counter");
        }

        boolean allowed = result > 0;
        long count = Math.abs(result);

        return new Decision(allowed, count, secondsToBoundary);
    }

    public record Decision(
            boolean allowed,
            long acceptedCount,
            long secondsToNextWindow) {}
}
~~~

`Clock` là dependency cần có trong Spring context. Có thể khai báo một bean dùng thời gian hệ thống:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Trong môi trường thực tế, phải giới hạn/chuẩn hóa `userId` để tránh key quá dài, key trùng tên không mong muốn hoặc tiết lộ thông tin cá nhân. Với nhiều instance, cần đồng bộ đồng hồ hệ thống; sai lệch thời gian có thể khiến các instance tính ra bucket khác nhau quanh ranh giới.

### 5.3. Diễn giải luồng một request

~~~text
HTTP request
     |
     v
Xác định userId và thời điểm
     |
     v
Tính bucketStart và tên Redis key
     |
     v
Spring Data Redis execute(Lua)
     |
     +--> Đã đạt LIMIT? ------> Có --> trả số âm, từ chối
     |                          |
     +--> Chưa -----------------+
             |
             v
          INCR key
             |
       TTL đang thiếu?
             |
        Có -> EXPIRE
             |
             v
       Trả số dương
             |
             v
       Cho xử lý request
~~~

Nếu client timeout khi gọi script, không thể tự biết Redis đã tăng count hay chưa. Gửi lại một lần nữa có thể tính thêm một request. Rate limiter kiểu này có thể chấp nhận sai số do retry theo chính sách, nhưng không nên nhầm với đếm sự kiện chính xác phục vụ thanh toán.

### 5.4. Tại sao trả số âm thay vì hai lệnh GET rồi INCR?

Nếu Java đọc count bằng `GET`, kiểm tra `count < LIMIT`, sau đó gọi `INCR`, nhiều instance có thể cùng thấy dưới hạn mức và cùng vượt limit. Lua kết hợp **kiểm tra + ghi** thành một thao tác nguyên tử.

Cách encode kết quả bằng dấu âm chỉ là quy ước minh họa; hệ thống lớn có thể dùng một kết quả Lua nhiều phần tử hoặc trạng thái rõ hơn. Khi xử lý giới hạn, cần phân biệt thêm các trường hợp **chỉ đếm số lần thử**, **chỉ đếm request được nhận**, hoặc **hoàn trả quota khi nghiệp vụ thất bại**. Đó là ba chính sách khác nhau.

## 6. Gắn rate limiter vào API Spring Web

Có thể dùng service trên trong controller hoặc filter/interceptor. Ví dụ controller đơn giản:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final FixedWindowRateLimiter limiter;

    public ProductController(FixedWindowRateLimiter limiter) {
        this.limiter = limiter;
    }

    @GetMapping
    public ResponseEntity<String> listProducts() {
        // Ví dụ minh họa; lấy principal từ security context ở ứng dụng thật.
        String userId = "demo-user-42";
        FixedWindowRateLimiter.Decision result = limiter.check(userId);

        if (!result.allowed()) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                    .header("Retry-After",
                            Long.toString(result.secondsToNextWindow()))
                    .body("Rate limit exceeded");
        }

        return ResponseEntity.ok("Products");
    }
}
~~~

Trong production, không hardcode `userId`. Lấy định danh ổn định từ user đã xác thực, API key hoặc chính sách định danh client. Nếu dùng địa chỉ IP, phải xử lý reverse proxy và header đáng tin cậy; không lấy tùy tiện một header do client tự gửi làm danh tính.

HTTP `429 Too Many Requests` phù hợp với rate limit. `Retry-After` có thể biểu diễn thời gian chờ theo giây. Với cửa sổ cố định, thời gian chờ đến ranh giới bucket là ước tính hợp lý; khi tính toán phải xét thời điểm request được trả lời và độ lệch đồng hồ.

Nếu cần một policy áp dụng cho tất cả endpoint, có thể đặt rate limiter ở filter hoặc interceptor thay vì copy logic vào từng controller. Nếu cần phân biệt chính sách theo endpoint/tenant, chọn key chứa dimension phù hợp.

## 7. Fixed window “từ lần request đầu” khác với bucket lịch

Đôi khi yêu cầu là: “Tối đa 5 lần thử trong 15 phút kể từ lần thử đầu tiên”, không phải “reset vào phút :00, :15, :30, :45”.

Một key ổn định:

~~~text
attempts:login:user:42
~~~

được tạo khi lần thử đầu xảy ra, sau đó `INCR` và TTL 15 phút. Đây là một **cửa sổ bắt đầu từ lần thử đầu** (first-event anchored window).

~~~text
Lần đầu lúc 12:07 -> key hết hạn gần 12:22
Các lần thử 12:09, 12:14 -> vẫn trong cửa sổ ban đầu
Sau 12:22 -> key hết hạn, chu kỳ tiếp theo có thể bắt đầu
~~~

Khác với fixed bucket 15 phút:

~~~text
12:00-12:15: hạn mức A
12:15-12:30: hạn mức B
~~~

Với first-event anchored window, không được gia hạn TTL sau mỗi request nếu yêu cầu là đúng 15 phút từ sự kiện đầu. Ngược lại, nếu mỗi request lại `EXPIRE 15 phút`, đó là **sliding inactivity timeout**, không phải cùng chính sách.

Vì chỉ một key nên thao tác `INCR` + TTL cần đảm bảo nguyên tử như script ở trên; key không chứa bucket thời gian và TTL cần được đặt khi bắt đầu cửa sổ. Cách này đơn giản nhưng **không bảo đảm “không quá N lần trong bất kỳ W giây”** khi key hết hạn rồi được tạo lại ngay sát ranh giới.

## 8. Sliding window: đếm trong đúng W giây gần nhất

Định nghĩa tại thời điểm `t` với độ dài cửa sổ `W`:

~~~text
count(t) = số sự kiện có timestamp trong (t - W, t]
~~~

Ví dụ W = 60 giây, hiện tại 12:01:10:

~~~text
12:00:10 --------------------------- 12:01:10
         |<---- 60 giây gần nhất ---->|
         Sự kiện trước/sát 12:00:10 bị loại
         Sự kiện sau 12:00:10 được tính
~~~

Vì cửa sổ trượt theo từng request, một counter duy nhất của phút hiện tại không đủ. Có ba hướng thiết kế phổ biến:

1. **Sliding log** bằng Redis Sorted Set: lưu timestamp từng sự kiện, chính xác theo mốc đã ghi.
2. **Sliding window counter** bằng hai bucket kề nhau với trọng số: tiết kiệm bộ nhớ nhưng gần đúng.
3. **Bucket nhỏ** (ví dụ mỗi giây) rồi tính tổng trong W giây: độ chính xác phụ thuộc độ rộng bucket.

### Bảng so sánh thuật toán

| Thuật toán | Bộ nhớ theo actor | Phép xử lý chủ yếu | Ưu điểm | Giới hạn |
|---|---|---|---|---|
| Fixed window | O(1) counter trong bucket hiện tại | `INCR`, TTL | Đơn giản, nhẹ | Burst tại ranh giới |
| First-event window | O(1) | `INCR`, TTL | Dễ giới hạn từ lần đầu | Không phải rolling window chính xác |
| Sliding log (ZSet) | O(N) sự kiện được giữ trong cửa sổ | `ZREMRANGEBYSCORE`, `ZCARD`, `ZADD` | Theo đúng thời điểm sự kiện | Tốn RAM và thao tác khi lưu nhiều event |
| Sliding counter hai bucket | O(1) số đếm trên hai bucket | Đọc hai counter, tính trọng số | Ít key, mượt hơn fixed window | Chỉ là ước lượng |
| Rolling buckets nhỏ | O(W / độ rộng bucket) | Nhiều counter và tổng hợp | Điều chỉnh sai số bằng độ rộng bucket | Đọc nhiều key, nhiều TTL và thao tác |
| Token bucket | O(1) trạng thái | Refill theo thời gian + trừ token | Điều hòa tốc độ và burst | Mang semantics khác “đếm chính xác trong W giây” |

## 9. Sliding log với Sorted Set: đếm chính xác theo timestamp

Redis Sorted Set (`ZSET`) lưu các member duy nhất, mỗi member có một `score`. Với bài toán sliding log:

- **Score** = timestamp của request, thường tính bằng millisecond.
- **Member** = định danh duy nhất của request/event.
- **Key** = một actor và một policy, ví dụ `rate:login:user:42`.

Ví dụ:

~~~text
ZSET key = rate:login:user:42

score (milliseconds)    member
--------------------    --------------------
100500                  100500:request-a
102000                  102000:request-b
116300                  116300:request-c
~~~

Mỗi request cần:

1. Xóa các sự kiện đã ra ngoài cửa sổ.
2. Đếm số member còn lại.
3. Nếu đã đủ hạn mức, từ chối.
4. Nếu còn hạn mức, thêm member mới với timestamp hiện tại.
5. Đặt hoặc gia hạn TTL để key rỗng/không hoạt động không tồn tại mãi.

**Ba bước kiểm tra, ghi và đặt TTL phải nguyên tử** nếu giới hạn cần được thực thi đúng trong lúc nhiều request đồng thời. Redis Lua script là lựa chọn tự nhiên.

### 9.1. Lua script cho sliding log

~~~lua
-- KEYS[1] : Sorted Set của actor
-- ARGV[1] : timestamp hiện tại theo millisecond
-- ARGV[2] : độ dài cửa sổ millisecond (> 0)
-- ARGV[3] : limit (> 0)
-- ARGV[4] : định danh sự kiện duy nhất

local now = tonumber(ARGV[1])
local windowMillis = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local eventId = ARGV[4]
local cutoff = now - windowMillis

redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', cutoff)

local current = redis.call('ZCARD', KEYS[1])

if current >= limit then
    return -current
end

local member = ARGV[1] .. ':' .. eventId
redis.call('ZADD', KEYS[1], now, member)
redis.call('PEXPIRE', KEYS[1], windowMillis + 1000)

return current + 1
~~~

Bài toán sử dụng khoảng **(now − W, now]**: các event có score đúng bằng cutoff được loại ra. Nếu nghiệp vụ muốn đóng/mở biên theo cách khác, cần điều chỉnh điều kiện tương ứng.

`eventId` phải thực sự phân biệt các sự kiện. **Không dùng timestamp làm member duy nhất**, vì nhiều request có thể xảy ra trong cùng một millisecond; nếu member trùng, `ZADD` có thể cập nhật member cũ thay vì tăng số sự kiện được lưu.

Script chỉ dùng một key, nên phù hợp giới hạn script một slot của Redis Cluster. Giá trị trả về dùng cùng quy ước số dương = chấp nhận, số âm = từ chối.

### 9.2. Spring Data Redis gọi Lua script sliding log

~~~java
import java.time.Clock;
import java.util.List;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class SlidingLogRateLimiter {

    private static final long WINDOW_MILLIS = 60_000;
    private static final long LIMIT = 100;

    private static final String LUA = """
            local now = tonumber(ARGV[1])
            local windowMillis = tonumber(ARGV[2])
            local limit = tonumber(ARGV[3])
            local eventId = ARGV[4]
            local cutoff = now - windowMillis

            redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', cutoff)

            local current = redis.call('ZCARD', KEYS[1])

            if current >= limit then
                return -current
            end

            local member = ARGV[1] .. ':' .. eventId
            redis.call('ZADD', KEYS[1], now, member)
            redis.call('PEXPIRE', KEYS[1], windowMillis + 1000)

            return current + 1
            """;

    private static final RedisScript<Long> SCRIPT = createScript();

    private final StringRedisTemplate redis;
    private final Clock clock;

    public SlidingLogRateLimiter(StringRedisTemplate redis, Clock clock) {
        this.redis = redis;
        this.clock = clock;
    }

    private static RedisScript<Long> createScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText(LUA);
        script.setResultType(Long.class);
        return script;
    }

    public boolean allow(String userId) {
        String key = "rate:api:sliding:user:" + userId;
        long nowMillis = clock.millis();

        Long result = redis.execute(
                SCRIPT,
                List.of(key),
                Long.toString(nowMillis),
                Long.toString(WINDOW_MILLIS),
                Long.toString(LIMIT),
                UUID.randomUUID().toString()
        );

        if (result == null) {
            throw new IllegalStateException("Redis script returned null");
        }

        return result > 0;
    }
}
~~~

Ví dụ có `Clock` bean như phần fixed-window. Mỗi lần gọi tạo `UUID` mới cho member, phù hợp với tình huống **mỗi lần gọi là một lần thử độc lập**. Nếu hệ thống retry cùng một sự kiện từ message broker, UUID mới ở mỗi retry sẽ làm sự kiện được đếm lại. Khi đó phải có **event ID ổn định** và thiết kế deduplication đúng mục đích.

### 9.3. Vì sao sliding log tiêu tốn bộ nhớ hơn?

Với 100.000 user đang hoạt động, mỗi user được giữ tối đa 100 sự kiện được chấp nhận trong cửa sổ, hệ thống có thể lưu đến hàng triệu member ZSet. Mỗi member gồm timestamp/ID và metadata của cấu trúc Redis. Dùng UUID dạng text làm member dài hơn một số nguyên nhỏ.

Cần ước tính:

~~~text
Tổng member còn sống
≈ tổng số sự kiện được giữ trong các sliding window
≤ số actor đồng thời × limit
  (nếu script từ chối trước khi thêm khi đã đủ quota)
~~~

Đây chỉ là upper bound phần member được chấp nhận; còn chi phí key, ZSet metadata và bộ nhớ Redis. Với limit rất cao hoặc số actor khổng lồ, cần benchmark thật để xem Sorted Set có còn phù hợp hay không.

### 9.4. Vấn đề thời gian khi có nhiều instance

Ví dụ dùng `clock.millis()` phía ứng dụng. Nếu hai instance lệch đồng hồ, các timestamp có thể không phản ánh đúng thứ tự thực tế; một event được ghi với timestamp “tương lai” có thể bị giữ lâu hơn dự kiến.

Có thể giảm sai số bằng đồng bộ đồng hồ (NTP) và giám sát clock skew. Với yêu cầu nghiêm ngặt, cân nhắc lấy timestamp từ **Redis server** hoặc thiết kế script phù hợp với version và cơ chế replication đang dùng, để toàn bộ request cùng dựa vào một nguồn thời gian. Khi dùng Redis Cluster với nhiều primary, vẫn cần cân nhắc thời gian và topology giữa các node.

## 10. Sliding-window counter gần đúng bằng hai bucket

Thay vì giữ từng request, ta có thể lưu **hai counter fixed-window kề nhau**: bucket hiện tại và bucket trước.

Giả sử mỗi bucket dài `W = 60 giây`, hiện tại đã đi qua `20 giây` của bucket hiện tại.

~~~text
[ bucket trước 60s ] [ 20s bucket hiện tại | 40s còn lại ]
                      ^
                   đầu bucket

Sliding window 60 giây gần nhất:
    40 giây cuối của bucket trước + 20 giây đầu bucket hiện tại
~~~

Ta chỉ biết tổng bucket trước, không biết chính xác sự kiện rơi vào giây nào. Phương pháp ước lượng coi phân bố sự kiện trong bucket trước gần như đều:

\[
\text{estimatedCount}
=
\text{currentCount}
+
\text{previousCount}\times
\left(1-\frac{\text{elapsedInCurrentBucket}}{W}\right)
\]

Ví dụ:

~~~text
previousCount = 80
currentCount  = 30
elapsed       = 15 giây
W             = 60 giây

estimatedCount = 30 + 80 × (1 - 15/60)
               = 30 + 60
               = 90
~~~

Đây **không phải số lượng chính xác** trong 60 giây gần nhất, bởi ta không biết 80 request của bucket trước tập trung vào đầu hay cuối bucket.

### 10.1. Ưu điểm

- Chỉ cần giữ vài counter trên mỗi actor.
- Không lưu ID từng sự kiện.
- Làm mượt ranh giới thời gian hơn fixed window thuần.
- Có thể phù hợp rate limiting gần đúng với tải lớn.

### 10.2. Giới hạn

- Có thể **ước lượng thiếu hoặc thừa** nếu traffic không đều.
- Nếu việc kiểm tra và tăng counter không nguyên tử, nhiều instance có thể vượt hạn mức ngoài sai số thuật toán.
- Nếu đọc counter ở hai key trong Redis Cluster, chúng phải nằm ở slot phù hợp khi cần script đa key.
- Cần chọn chính sách làm tròn và cách xử lý ngưỡng; so sánh một ước lượng số thực với limit không giống đếm từng sự kiện.

Ví dụ schema cùng slot cho mỗi user khi phải dùng một script hai key trên Redis Cluster:

~~~text
rate:api:{user42}:bucket:1893456000
rate:api:{user42}:bucket:1893456060
~~~

Hash tag `{user42}` giúp hai key cùng slot. Không dùng hash tag chung như `{api}` cho tất cả user vì sẽ dồn toàn bộ traffic vào một slot.

## 11. Rolling buckets nhỏ: cân bằng giữa độ chính xác và chi phí

Một cách khác là chia W giây thành nhiều bucket nhỏ. Ví dụ giới hạn 100 request trong 60 giây, mỗi bucket dài 5 giây:

~~~text
12 bucket × 5 giây = 60 giây
~~~

Mỗi request tăng counter của bucket 5 giây đang hoạt động. Để ước tính số request gần nhất, đọc và cộng những bucket liên quan.

Nếu mỗi bucket nhỏ hơn, sai số ranh giới thường nhỏ hơn nhưng số key/điểm dữ liệu và chi phí đọc tăng.

| Độ rộng bucket | Số bucket cho 60 giây | Đặc điểm |
|---|---:|---|
| 60 giây | 1 | Fixed window đơn giản, burst rõ |
| 10 giây | 6 | Ít dữ liệu hơn sliding log nhưng còn sai số |
| 5 giây | 12 | Sai số theo bucket nhỏ hơn, nhiều key hơn |
| 1 giây | 60 | Chi tiết cao hơn, tăng thao tác và cardinality |
| Từng timestamp | Tùy số event | Sliding log chính xác hơn nhưng nặng RAM |

Một phép cộng các bucket không bao giờ chính xác tuyệt đối ở ranh giới nếu chỉ giữ tổng của bucket. Có thể áp dụng trọng số cho bucket đầu/cuối để giảm sai số dựa trên giả định phân bố tương đối đều.

Trong Redis, lựa chọn biểu diễn có thể là:

- Một String key cho mỗi actor/bucket thời gian.
- Một Hash cho mỗi actor, field là bucket ID; nhưng cần cơ chế xóa field cũ vì TTL cấp key không tự xóa từng field theo vòng đời riêng.
- Một cấu trúc khác có chiến lược cắt bớt phần tử và tuổi dữ liệu.

Không gom toàn bộ actor vào một Hash khổng lồ chỉ để giảm số key. Một key quá lớn hoặc quá nóng có thể gây nghẽn và khó phân bố trên Redis Cluster.

## 12. Đếm thống kê theo phút, giờ và ngày lịch

Không phải mọi counter theo thời gian đều để giới hạn API. Với thống kê kinh doanh, fixed bucket thường dễ hiểu nhất.

Ví dụ:

~~~text
metrics:orders:minute:1893456000 -> "120"
metrics:orders:minute:1893456060 -> "135"
metrics:orders:minute:1893456120 -> "98"
~~~

Mỗi key chứa số đơn hàng trong khoảng `[bucketStart, bucketStart + 60s)`. Key cần có TTL theo retention, ví dụ 7 ngày kể từ khi bucket đóng.

### 12.1. Lua script tăng và gắn mốc hết hạn tuyệt đối

Nếu bucket phải được giữ đến một timestamp xác định, Redis hỗ trợ `EXPIREAT`. Script có thể tăng counter và đặt chính xác mốc hết hạn:

~~~lua
-- KEYS[1] = key của bucket
-- ARGV[1] = expireAtEpochSeconds

local count = redis.call('INCR', KEYS[1])
redis.call('EXPIREAT', KEYS[1], tonumber(ARGV[1]))
return count
~~~

Nếu sự kiện đến quá muộn, `expireAtEpochSeconds` có thể đã thuộc quá khứ; Redis sẽ xóa key ngay. Vì vậy, cần xác định rõ **policy late events** trước khi dùng dạng này.

### 12.2. Service Java đếm đơn hàng theo phút

~~~java
import java.time.Clock;
import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class MinuteOrderCounter {

    private static final long WINDOW_SECONDS = 60;
    private static final long RETENTION_SECONDS =
            Duration.ofDays(7).getSeconds();

    private static final String LUA = """
            local count = redis.call('INCR', KEYS[1])
            redis.call('EXPIREAT', KEYS[1], tonumber(ARGV[1]))
            return count
            """;

    private static final RedisScript<Long> SCRIPT = createScript();

    private final StringRedisTemplate redis;
    private final Clock clock;

    public MinuteOrderCounter(StringRedisTemplate redis, Clock clock) {
        this.redis = redis;
        this.clock = clock;
    }

    private static RedisScript<Long> createScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText(LUA);
        script.setResultType(Long.class);
        return script;
    }

    public Long recordOrder() {
        long nowSeconds = clock.instant().getEpochSecond();
        long bucketStart =
                Math.floorDiv(nowSeconds, WINDOW_SECONDS) * WINDOW_SECONDS;
        long bucketEnd = bucketStart + WINDOW_SECONDS;
        long expireAt = bucketEnd + RETENTION_SECONDS;

        String key = "metrics:orders:minute:" + bucketStart;

        return redis.execute(
                SCRIPT,
                List.of(key),
                Long.toString(expireAt)
        );
    }
}
~~~

Ví dụ này đếm theo **processing time**: sự kiện được tính vào phút mà service nhận và xử lý. Nếu đơn hàng xảy ra lúc 12:00 nhưng được message consumer xử lý lúc 12:02, nó vào bucket 12:02.

Với thống kê theo **event time**, thay `clock.instant()` bằng timestamp có kiểm chứng của sự kiện. Phải quy định cách chấp nhận sự kiện trễ, xử lý trùng do retry và thời hạn chốt bucket. Redis counter không tự biết một message broker đã redeliver cùng event.

### 12.3. Thống kê theo ngày: ngày lịch khác 86.400 giây cố định

Một “ngày” có thể nghĩa là:

- Một khoảng liên tiếp đúng 24 giờ tính từ mốc nào đó.
- Ngày lịch theo UTC.
- Ngày lịch theo timezone nghiệp vụ, ví dụ `Asia/Ho_Chi_Minh`.

Với quy tắc “đơn hàng ngày hôm nay theo giờ kinh doanh”, hãy tính key từ `ZonedDateTime` hoặc `LocalDate` trong timezone quy định:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate businessDate = Instant.now()
        .atZone(businessZone)
        .toLocalDate();

String key = "metrics:orders:day:" + businessDate;
~~~

Nếu hệ thống hoạt động tại timezone có daylight saving time (DST), một ngày lịch có thể dài 23 hoặc 25 giờ. Không dùng công thức `epochSeconds / 86400` nếu ý nghĩa là ngày lịch theo một timezone tùy ý. Mốc expiration nên tính từ **đầu ngày kế tiếp theo cùng timezone** cộng retention phù hợp.

## 13. Thiết kế key để kiểm soát cardinality

Với rate limit, cardinality là tích của các chiều biến thiên:

~~~text
số actor hoạt động
× số policy/endpoint
× số bucket còn tồn tại đồng thời
~~~

Ví dụ:

~~~text
100.000 user
× 4 chính sách giới hạn
× 2 bucket đồng thời (bucket hiện tại + grace)
≈ 800.000 key
~~~

Đây chỉ là ước lượng khi tất cả actor hoạt động đủ để có key ở từng policy và những bucket trước còn trong thời gian giữ. Thực tế có thể thấp hơn hoặc cao hơn theo traffic và retention.

Schema nên rõ:

~~~text
rate:login:user:42:bucket:1893456000
rate:search:tenant:acme:bucket:1893456000
metrics:orders:minute:1893456000
~~~

Quy tắc:

1. Không đưa toàn bộ URL query, access token hoặc raw request body vào key.
2. Actor ID cần ổn định, được canonicalize và có giới hạn độ dài.
3. Tránh tạo key theo request ID cho fixed counter; mỗi request phải **cùng tăng** key của bucket tương ứng.
4. Nếu dùng nhiều policy, đưa policy vào key để tránh hạn mức của endpoint này ảnh hưởng endpoint khác.
5. Nếu có nhiều tenant, giới hạn số actor và policy động được phép tạo.
6. Nếu lưu bucket cho metrics, có retention và quy trình xuất dữ liệu đã chốt.

### 13.1. TTL ảnh hưởng trực tiếp số key

Quy tắc ước tính đơn giản:

~~~text
Key sống đồng thời ≈ tốc độ sinh key độc nhất × thời gian tồn tại
~~~

Ví dụ một API tạo 300 key mới mỗi giây, mỗi key có TTL 15 phút:

~~~text
300 × 15 × 60 = 270.000 key
~~~

Nếu mỗi request đều dùng cùng key của user/bucket thì tốc độ tạo key mới thấp hơn tốc độ request. Vì vậy cần đo **distinct actors/buckets**, không lấy tổng request/giây nhân TTL một cách máy móc.

### 13.2. Hot key là vấn đề khác với nhiều key

Nếu mọi request tăng cùng key `metrics:orders:minute:...`, một counter có thể trở nên **hot key** dù chỉ chiếm vài byte dữ liệu. Redis xử lý lệnh rất nhanh nhưng một key cực nóng vẫn tạo điểm tập trung tài nguyên.

Các hướng thiết kế tùy yêu cầu:

- Giữ counter chung khi traffic và độ trễ còn chấp nhận được.
- Chia counter thành nhiều shard logic, ví dụ `metrics:orders:minute:<bucket>:shard:<n>`, mỗi event chọn một shard ổn định/ngẫu nhiên; khi đọc phải cộng tất cả shard.
- Dùng stream/broker cho sự kiện và consumer tổng hợp nếu cần xử lý khối lượng lớn và khả năng replay.
- Nếu cần rate limit **nguyên tử toàn cục** trên một actor, không thể tùy tiện shard counter rồi đọc cộng không đồng bộ mà vẫn bảo đảm cùng semantics.

Sharding làm tăng số key và công sức tổng hợp; chỉ áp dụng khi có bằng chứng key đang là điểm nghẽn.

## 14. Redis Cluster và những script chạm nhiều key

Trong Redis Cluster, key được phân vào hash slot. Một Lua script chạm nhiều key thường yêu cầu những key tham gia ở **cùng hash slot**.

Ví dụ sliding-window counter dựa trên hai bucket:

~~~text
rate:api:{user42}:bucket:1893456000
rate:api:{user42}:bucket:1893456060
~~~

Hash tag `{user42}` giúp các key thuộc cùng user nằm cùng slot. Nếu script chỉ chạm **một key**, như fixed-window script và sliding-log script ở trên, không cần cố tình nhóm hash tag cho các key khác.

Tránh dùng:

~~~text
rate:{api}:user:1:bucket:...
rate:{api}:user:2:bucket:...
rate:{api}:user:3:bucket:...
~~~

Vì mọi key có hash tag `{api}` sẽ dồn vào một slot, mất khả năng phân tải qua các primary.

Khi thêm/bớt node hoặc failover, client Spring Data Redis cần cấu hình Cluster-aware. Các lệnh có thể tạm thời gặp timeout/chuyển hướng; atomic script chỉ bảo đảm thực thi theo điều kiện Redis trả lời tại node thích hợp, không phải bảo đảm tất cả request trong suốt sự cố đều được đếm đúng một lần.

## 15. Chọn nguồn thời gian và xử lý clock skew

Bộ đếm cửa sổ phụ thuộc mạnh vào mốc thời gian.

### 15.1. Thời gian từ ứng dụng

Ưu điểm: code đơn giản, dễ kiểm thử với `Clock.fixed(...)` và không cần thêm round trip lấy thời gian. Nhược điểm: nhiều instance có thể lệch đồng hồ, đặc biệt ở ranh giới bucket.

Ví dụ:

~~~text
Instance A nghĩ bây giờ là 12:00:59.990 -> bucket 12:00
Instance B nghĩ bây giờ là 12:01:00.020 -> bucket 12:01
~~~

Hai instance có thể ghi hai key khác nhau cho các request thực tế rất gần nhau. Cần đồng bộ giờ và quan sát drift. Không dùng thời gian sinh từ browser làm nguồn tin cậy cho rate limiter phía server.

### 15.2. Thời gian từ Redis

Redis có lệnh `TIME` để cung cấp thời gian của server. Nếu cần mọi quyết định gắn với cùng nguồn thời gian, có thể thiết kế script hoặc quy trình lấy thời gian từ Redis. Tuy nhiên:

- Phải tính đến Redis version và các quy tắc script/replication.
- Với Redis Cluster, nhiều primary là nhiều host; đồng hồ các host vẫn cần đồng bộ.
- Dùng Redis time không tự giải quyết request bị retry, redelivery hoặc failover làm mất ghi.

Với thống kê theo event-time, timestamp của event và timestamp lúc xử lý có ý nghĩa khác nhau; không nên tự thay thế cái này bằng cái kia.

### 15.3. Dùng epoch cho fixed duration, timezone cho calendar window

- Cửa sổ “mỗi 60 giây kể từ Unix epoch”: tính bằng epoch seconds.
- Cửa sổ “ngày kinh doanh tại Việt Nam”: dùng `ZoneId` và `LocalDate`.
- Cửa sổ “60 giây gần nhất”: trừ duration từ timestamp hiện tại, không làm tròn theo phút.

Làm tròn sai thời điểm là nguồn lỗi thường gặp khó phát hiện bằng các unit test chỉ chạy ở giữa phút.

## 16. Những ràng buộc về nhất quán và retry

### 16.1. Lệnh Redis nguyên tử nhưng request HTTP có thể bị lặp

Luồng:

~~~text
Client -> API -> Redis INCR thành công
                 |
                 +-- API bị timeout trước khi trả response
Client retry cùng request
       -> Redis INCR lần nữa
~~~

Từ phía Redis có hai lần tăng, dù phía client có thể cho rằng đó là một yêu cầu logic. Với rate limiting “đếm mỗi lần gọi”, hành vi này có thể chấp nhận. Với số đơn hàng hoặc hóa đơn, đó là **đếm trùng**.

Muốn đếm mỗi sự kiện nghiệp vụ đúng một lần cần định danh event ổn định, cơ chế deduplication và nguồn sự kiện đáng tin cậy. Có thể dùng Lua kết hợp kiểm tra marker và tăng counter trong một script khi các key cùng slot, nhưng phải xử lý TTL, retry, failover và dữ liệu chuẩn. Không xem một phép `INCR` là hệ thống exactly-once.

### 16.2. INCR không kết hợp nguyên tử với giao dịch DB mặc định

Ví dụ tạo đơn hàng:

~~~text
INSERT order vào PostgreSQL
INCR metrics:orders:minute:...
~~~

Nếu DB commit xong nhưng Redis lỗi, counter bị thiếu. Nếu Redis tăng trước nhưng DB transaction rollback, counter bị thừa. Không có transaction phân tán tự động chỉ vì dùng Spring Data Redis trong cùng Spring Boot app.

Với thống kê có thể tái tạo, cách phổ biến là ghi sự kiện/đơn hàng chắc chắn vào nguồn dữ liệu chuẩn, rồi tổng hợp vào Redis qua event/outbox và có cơ chế đối soát. Tránh dùng Redis counter làm cơ sở duy nhất cho số liệu tài chính cần kiểm toán.

### 16.3. Replication và failover

Nếu primary Redis mất kết nối trước khi replica kịp nhận các lần tăng gần nhất, một số tăng có thể không tồn tại sau failover. Redis Cluster hoặc Sentinel tăng khả năng phục hồi kết nối, nhưng không biến replication mặc định thành ghi đồng bộ không mất dữ liệu.

Bộ đếm hạn mức nghiêm ngặt phải đánh giá nguy cơ cho phép thêm request trong failover. Khi yêu cầu an toàn cao, cần policy bảo vệ khi Redis không có sẵn và thiết kế kiểm soát nhiều lớp.

## 17. Khi Redis lỗi: fail-open hay fail-closed?

Với rate limiting, lỗi Redis đặt ra một quyết định nghiệp vụ:

| Chính sách | Hành vi khi Redis timeout | Trường hợp thường xem xét |
|---|---|---|
| **Fail-open** | Cho phép request đi tiếp và ghi metrics lỗi | Endpoint cần tính sẵn sàng cao, rate limit chỉ để bảo vệ phụ trợ |
| **Fail-closed** | Từ chối hoặc trả lỗi tạm thời | Endpoint nhạy cảm, hạn mức là một phần yêu cầu an toàn |
| **Degraded mode** | Áp dụng giới hạn cục bộ/layer khác, giảm khả năng hoặc dùng quota dự phòng | Hệ thống có nhiều lớp bảo vệ đã thiết kế từ trước |

Không có một lựa chọn đúng cho mọi API. Ví dụ giới hạn chống brute-force khi Redis lỗi có thể cần hành vi khác với giới hạn gợi ý cho endpoint đọc công khai.

**Không nuốt mọi exception rồi trả `allowed = true` mà không có quyết định rõ ràng.** Cũng không retry script tăng counter vô hạn vì một lần timeout có thể xảy ra sau khi Redis đã thực thi. Cần timeout cụ thể, metrics, cảnh báo và số lần retry có giới hạn.

## 18. Thời gian sống, eviction và độ chính xác hạn mức

Redis có `maxmemory` và các `maxmemory-policy`. Nếu counter đang giới hạn request bị evict trước TTL, request tiếp theo có thể tạo counter mới và nhận thêm hạn mức.

Vì vậy:

- Với rate limit quan trọng, cân nhắc Redis deployment và eviction policy phù hợp.
- Không để cache có thể evict tùy ý ảnh hưởng những counter cần giữ đến hết window.
- Theo dõi `evicted_keys` và `expired_keys`; eviction không phải expiration theo lịch.
- Đặt TTL cho key tạm để tránh tích tụ vô hạn, nhưng TTL phải đủ dài cho semantics của thuật toán.
- Khi Redis chạm giới hạn RAM với `noeviction`, lệnh ghi có thể thất bại; ứng dụng cần chính sách xử lý lỗi tương ứng.

Sliding log có thể giữ nhiều member và tạo áp lực memory hơn fixed counter. Đánh giá kết hợp **số actor đồng thời × limit × kích thước member**.

## 19. Quan sát bộ đếm trong Redis và Spring

Redis CLI:

~~~bash
redis-cli GET rate:api:user:42:bucket:1893456000
redis-cli TTL rate:api:user:42:bucket:1893456000

redis-cli ZCARD rate:api:sliding:user:42
redis-cli ZRANGE rate:api:sliding:user:42 0 -1 WITHSCORES
redis-cli PTTL rate:api:sliding:user:42

redis-cli INFO keyspace
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO commandstats
~~~

Giải thích:

- `GET`: đọc counter String; trả null khi key không tồn tại.
- `TTL`: số giây còn lại; `-1` nếu key tồn tại nhưng không có TTL; `-2` nếu key không tồn tại.
- `ZCARD`: số sự kiện/member đang lưu trong sliding log. Nếu key chưa được cleanup trong lúc không có request, số này có thể bao gồm event đã ra ngoài window cho đến khi key hết hạn hoặc có lượt truy cập mới.
- `ZRANGE ... WITHSCORES`: quan sát timestamp và ID để debug trong phạm vi nhỏ.
- `PTTL`: kiểm tra hạn theo millisecond.
- `INFO`: số key, RAM, expired/evicted keys, thống kê command.

Không gọi `KEYS *` thường xuyên trên keyspace production lớn để đếm từng user. Nếu cần điều tra, dùng `SCAN` theo prefix với batch thích hợp, chấp nhận rằng kết quả scan không phải snapshot nhất quán.

### 19.1. Metrics nên có ở phía ứng dụng

| Metric | Cho biết điều gì |
|---|---|
| Số request được chấp nhận/từ chối theo policy | Rate limit có đang ảnh hưởng người dùng không |
| Redis script latency p50/p95/p99 | Độ trễ có tăng theo traffic hoặc chi phí thao tác ZSet không |
| Redis errors/timeouts | Khi nào cần kích hoạt policy fail-open/closed |
| Số actor/key đang hoạt động | Cardinality thực tế |
| Memory dùng cho keyspace | Khi nào cần tăng capacity hoặc đổi thuật toán |
| Clock skew | Ranh giới bucket giữa các instance có đáng tin cậy không |
| Tỷ lệ event duplicate/late | Độ chính xác của thống kê theo thời gian |

Chỉ nhìn latency của `INCR` không đủ để biết hệ thống đang đếm đúng. Cần đo cả tỷ lệ bị từ chối, số key và mức độ trễ/mất event.

## 20. Bài tập: chọn thuật toán đúng yêu cầu

### Bài tập 1 — Giới hạn API theo phút lịch

**Đề:** một user được gửi tối đa 120 request trong mỗi phút UTC. Có thể gửi 120 request sát cuối phút và 120 request ngay đầu phút sau.

**Thiết kế:** fixed window, key theo `userId + bucketStart`, Lua kiểm tra limit và tăng nguyên tử, TTL đến cuối bucket + grace. Mỗi actor/policy dùng tối đa một vài key tồn tại đồng thời.

### Bài tập 2 — Giới hạn số lần thử đăng nhập trong 15 phút gần nhất

**Đề:** không quá 5 lần thử thất bại trong bất kỳ 15 phút liên tiếp.

**Thiết kế:** sliding log ZSet nếu cần semantics timestamp rõ ràng. Member ID duy nhất; score theo nguồn thời gian đã chọn. Cleanup các sự kiện `≤ now − 15 phút`, đếm rồi thêm nguyên tử. Nếu request bị từ chối có cần tiếp tục ghi nhận lần thử hay không là quyết định policy; script minh họa chỉ đếm lần được chấp nhận.

Cần cân nhắc thêm cơ chế bảo vệ chống credential stuffing tại nhiều tầng, xử lý lỗi Redis và clock skew.

### Bài tập 3 — Thống kê số đơn hàng theo giờ để xem dashboard

**Đề:** hiển thị số đơn hàng mỗi giờ trong 7 ngày; sự kiện đến trễ tối đa 10 phút.

**Thiết kế:** fixed bucket một giờ, key theo `bucketStartEpochSeconds`, expiration theo giờ kết thúc + retention. Xác định thống kê theo event-time hay processing-time; cho phép late events trong khoảng 10 phút đã quy định. Nếu đơn hàng cần chính xác, tổng hợp từ dữ liệu chuẩn và có cơ chế sửa lại bucket khi xử lý lại.

### Bài tập 4 — Rate limit mượt nhưng số user rất lớn

**Đề:** hàng triệu actor, cần hạn chế burst gần ranh giới phút nhưng bộ nhớ không đủ cho ZSet từng request.

**Thiết kế:** cân nhắc sliding-window counter hai bucket, rolling bucket nhỏ hoặc token bucket. Chấp nhận sai số định lượng và đo hiệu quả. Với multi-key Lua trên Redis Cluster, cần thiết kế hash tag theo actor.

### Bài tập 5 — Vì sao INCR + EXPIRE hai lệnh có thể tạo key không TTL?

**Đề:** sau nhiều ngày, Redis có hàng nghìn counter tạm với `TTL = -1`.

**Giải thích:** client hoặc tiến trình có thể dừng giữa hai lệnh. Giải pháp là thao tác nguyên tử bằng script, đảm bảo mọi key mới được gắn TTL theo mục đích và có quy trình dọn các key mồ côi đã được xác định owner.

### Bài tập 6 — Ước lượng số key

**Đề:** 50.000 user hoạt động, 3 loại rate limit, giữ counter của bucket hiện tại và một bucket trước.

~~~text
50.000 user × 3 policy × 2 bucket
= 300.000 counter key (ước lượng trần theo giả định)
~~~

Nếu chuyển sang sliding log với 100 event được giữ trên mỗi actor/policy, có thể có tới 15 triệu member theo giả định mọi actor dùng đủ quota. Cần ước tính payload và metadata rồi đo trên Redis thật.

## 21. Bảng chọn nhanh

| Câu hỏi | Hướng lựa chọn |
|---|---|
| Chỉ cần đếm theo từng phút/giờ/ngày | Fixed bucket với key theo thời gian |
| Muốn giới hạn từ lần request đầu | Counter key ổn định + TTL chỉ đặt khi tạo |
| Muốn kiểm tra đúng W giây gần nhất | Sliding log Sorted Set |
| Muốn giảm RAM và chấp nhận sai số | Sliding counter hoặc rolling buckets |
| Muốn tốc độ mượt với burst có kiểm soát | Token bucket có semantics riêng |
| Cần giới hạn đúng khi nhiều instance cùng gọi | Redis atomic operation hoặc Lua script |
| Cần tránh key không TTL | Gắn expiration trong cùng script/thao tác nguyên tử |
| Cần dùng Redis Cluster với script đa key | Tất cả key liên quan phải cùng hash slot |
| Cần đếm sự kiện nghiệp vụ không trùng khi retry | Event ID, deduplication và nguồn dữ liệu chuẩn |
| Redis lỗi có nên cho request qua không | Policy fail-open/closed theo endpoint |
| Counter quan trọng có thể bị eviction không | Cân nhắc policy bộ nhớ, độ tin cậy và tách workload |

## 22. Sơ đồ quyết định thiết kế

~~~text
                      Cần đếm theo thời gian
                                |
                    Có cần thống kê theo lịch?
                         /             \
                       Có              Không
                        |                |
              Fixed time bucket    Có cần đúng W giây
              theo phút/giờ/ngày       gần nhất?
                                      /         \
                                    Có          Không
                                     |             |
                              Chấp nhận RAM       Cửa sổ
                              giữ timestamp?      cố định đủ?
                                 /       \          /     \
                               Có       Không     Có      Không
                                |          |        |        |
                            Sliding ZSet  Sliding  Fixed   Xem lại
                                          counter  window  policy/token bucket
                                \           |        /
                                 +----------+-------+
                                            |
                              Nhiều instance đồng thời?
                                            |
                                  Atomic Redis / Lua
                                            |
                            Key schema + TTL + giới hạn RAM
                                            |
                            Clock + retry + failover policy
                                            |
                                  Metrics và cảnh báo
~~~

**Nguyên tắc cần giữ:** trước hết định nghĩa chính xác **cửa sổ thời gian**; sau đó mới chọn Redis key và lệnh. Với bộ đếm theo bucket, `INCR` và TTL đủ để quản lý số lượng nhưng cần ghép nguyên tử khi lifecycle quan trọng. Với cửa sổ trượt chính xác, cần lưu thông tin sự kiện hoặc một mô hình tương đương; một counter của phút hiện tại không thể tự tái tạo lịch sử trong 60 giây gần nhất.

Spring Data Redis giúp triển khai những lựa chọn này bằng `StringRedisTemplate`, `RedisScript` và các thao tác String/Sorted Set. Độ đúng đắn của hệ thống vẫn phụ thuộc vào lựa chọn thuật toán, thời gian, semantics của retry, khả năng khôi phục dữ liệu và chính sách vận hành Redis.

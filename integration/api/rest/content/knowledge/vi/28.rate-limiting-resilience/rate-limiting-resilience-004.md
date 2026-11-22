# Đếm phân tán và xử lý burst giữa nhiều nút

Trong REST API chạy trên nhiều instance Java/Spring, một giới hạn như **100 yêu cầu/phút cho mỗi tenant** phải có ý nghĩa dù load balancer phân phối request đến instance A, B hay C. Nếu mỗi instance tự tăng biến đếm trong RAM, cùng một client có thể được phục vụ nhiều hơn chính sách dự kiến. Ngược lại, nếu mọi request đều phụ thuộc vào một kho đếm từ xa, hệ thống phải giải quyết thêm độ trễ, điểm nóng, mất kết nối, đồng hồ và khả năng chịu lỗi.

Bài học thuộc nhóm **Giới hạn và chống lỗi** của module thiết kế REST API: ta sẽ thiết kế hạn mức theo danh tính và resource, tính toán burst, sử dụng thao tác đếm nguyên tử trên Redis, tích hợp Spring, trả HTTP 429/`Retry-After` và kiểm thử nhiều nút. Những kỹ thuật này giúp bảo vệ CPU, connection pool và dịch vụ phía sau; chúng **không thay thế** xác thực, phân quyền, idempotency, timeouts hay circuit breaker.

## 1. Bài toán: ba instance, một chính sách

Giả sử hệ thống có ba instance đằng sau load balancer:

~~~mermaid
flowchart LR
    C[Client / tenant T] --> LB[Load balancer]
    LB --> A[API A]
    LB --> B[API B]
    LB --> D[API C]
    A --> R[(Bộ đếm chung)]
    B --> R
    D --> R
~~~

Chính sách ghi trong hợp đồng API là: **tenant T được gửi tối đa 60 request/phút**. Một cách làm sai thường gặp là đặt trên từng instance:

~~~java
// Minh họa lỗi thiết kế: biến đếm local trên mỗi instance.
private final AtomicInteger requestsThisMinute = new AtomicInteger();

boolean allow() {
    return requestsThisMinute.incrementAndGet() <= 60;
}
~~~

Nếu ba instance cùng có quota 60, client có thể đạt khoảng **180 request/phút** khi lưu lượng được chia đều; thêm instance thứ tư thì ngưỡng vô tình tăng. Khi instance khởi động lại, bộ đếm bị đặt về 0. Dùng sticky session không giải quyết triệt để: client có thể mở kết nối khác, instance bị thay thế, hoặc cần scale/failover.

**Mục tiêu của bộ giới hạn phân tán** là các nút đồng ý về *một* ngân sách theo cùng một khóa logic: tenant, người dùng, API key, route group hoặc tổ hợp đã được xác thực. Độ chính xác cần được định nghĩa rõ: có yêu cầu phải giữ ngưỡng rất chặt; có luồng cho phép sai số nhỏ để giảm độ trễ.

### Những khái niệm dễ nhầm

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Rate** | Tốc độ trung bình có thể duy trì | 10 token/giây |
| **Burst capacity** | Lượng việc có thể được chấp nhận trong một đợt ngắn | Tối đa 20 request tức thời khi bucket đầy |
| **Quota** | Ngân sách trong khoảng thời gian dài | 100.000 request/tháng cho tenant |
| **Concurrency limit** | Bao nhiêu tác vụ đang chạy đồng thời | Tối đa 5 truy vấn đắt/tenant |
| **Request cost** | Một request tiêu tốn bao nhiêu đơn vị | Truy vấn báo cáo nặng tính 5 token |
| **Retry budget** | Số lần client được thử lại khi gặp lỗi | Tối đa 2 lần, có backoff và jitter |

Rate limit thường bảo vệ tốc độ vào; concurrency limit bảo vệ **số tác vụ đang chiếm tài nguyên**. Một API chỉ cho 10 request/giây vẫn có thể có hàng trăm tác vụ đồng thời nếu mỗi request chạy rất lâu. Hai loại giới hạn phải được thiết kế cùng nhau.

## 2. Định nghĩa chính sách trước khi chọn thuật toán

Ta dùng ví dụ thống nhất cho `POST /api/v1/orders`, sau khi API xác thực tenant:

| Thuộc tính | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| Bucket key | `tenantId + routeGroup=orders` | Gộp tất cả instance vào cùng quota |
| Refill rate | **10 token/giây** | Tốc độ duy trì |
| Capacity | **20 token** | Cho phép burst tối đa 20 request đơn vị khi đầy |
| Cost của request thường | **1 token** | 1 lệnh tạo đơn |
| Cost của tác vụ phức tạp | **5 token** | Ví dụ phép kiểm tra tồn kho liên vùng |
| Kết quả hết token | **HTTP 429** | Hướng dẫn client đợi |
| Giới hạn đồng thời bổ sung | **5 tác vụ nặng/tenant** | Bảo vệ DB và downstream |

Đây là con số dành cho bài tập, **không phải mặc định của Spring hoặc Redis**. Trong triển khai thật, chọn rate/capacity từ SLO, cấu hình downstream, thử nghiệm tải, phân phối request hợp lệ và điều khoản sản phẩm.

Đừng diễn giải “10 token/giây, burst 20” thành “không có bất kỳ 1 giây nào nhận hơn 10 request”. Khi bucket đầy, 20 request có thể được chấp nhận gần như đồng thời. Sau khi cạn, bucket phục hồi dần; với cost 1 và tốc độ 10 token/giây, mỗi token mới cần khoảng 100 ms.

**Công thức token bucket:**

\[
T_{\text{new}}=\min\!\left(B,\;T_{\text{old}}+r\,\Delta t\right)
\]

Trong đó `B` là dung lượng burst, `r` là tốc độ bổ sung token và `Δt` là thời gian kể từ lần cập nhật trước. Request có chi phí `c` được nhận khi `T_new ≥ c`, sau đó lưu `T_new − c`. Nếu không đủ token, trạng thái không bị trừ; có thể tính thời gian chờ xấp xỉ:

\[
t_{\text{retry}}=\frac{\max(0,c-T_{\text{new}})}{r}.
\]

Ví dụ: lúc `t=0` bucket 20 token nhận đúng 20 request cost 1; request thứ 21 bị từ chối. Sau 0,1 giây có khoảng 1 token; sau 1 giây có khoảng 10 token, nếu chưa có request mới. Nếu client gửi 30 request **cùng lúc**, tại cùng thời điểm logic chỉ 20 request đầu tiên có thể được nhận. Trong môi trường thực, các request được Redis xử lý lần lượt và thời gian vẫn trôi, nên lượng được nhận trong một khoảng dài có thể nhiều hơn 20 theo tốc độ refill.

## 3. Chọn thuật toán: burst được chấp nhận đến đâu?

| Thuật toán | Ý tưởng | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| **Fixed window counter** | Đếm trong từng cửa sổ cố định, ví dụ mỗi phút | Dễ triển khai bằng `INCR` + TTL | Có thể nhân đôi burst sát ranh giới cửa sổ |
| **Sliding log** | Lưu timestamp từng request trong khoảng trượt | Diễn đạt chính xác “N request trong 60 giây gần nhất” | Bộ nhớ và thao tác tăng theo số request |
| **Sliding window counter** | Ước lượng từ cửa sổ hiện tại và trước đó | Chi phí thấp, mượt hơn fixed window | Là xấp xỉ, không đảm bảo chuẩn xác tuyệt đối mọi khoảng trượt |
| **Token bucket** | Bổ sung token theo thời gian đến mức capacity | Điều chỉnh burst rõ ràng, phù hợp API tương tác | Cho burst nhanh tới `B`; phải đồng bộ trạng thái |
| **Leaky bucket / GCRA** | Kiểm soát nhịp theo thời gian lý thuyết được phép | Điều tiết tốc độ mượt và kiểm soát burst | Cần định nghĩa tolerance/burst cho đúng |

Ví dụ vấn đề fixed window: nếu mỗi phút cho 100 request, client có thể gửi 100 request lúc **12:00:59** và 100 request lúc **12:01:00**. Trong gần 2 giây có tới 200 request mà vẫn không vượt bộ đếm của từng phút. Token bucket không phụ thuộc ranh giới lịch kiểu đó, nhưng **chủ động cho burst** theo capacity.

Chọn thuật toán theo lời hứa trong API. Nếu cần “tối đa 100 request trong *bất kỳ* khoảng trượt 60 giây nào”, token bucket chỉ đảm bảo dạng burst/rate, không tự suy ra đúng ràng buộc sliding window đó. Có thể kết hợp nhiều giới hạn: token bucket ngắn hạn, quota giờ/ngày và concurrency limit.

## 4. Vì sao tính nguyên tử là bắt buộc?

Giả sử state của bucket còn đúng 1 token. Hai instance cùng chạy:

~~~text
Instance A: GET tokens -> 1
Instance B: GET tokens -> 1
Instance A: tính đủ, SET tokens -> 0; ACCEPT
Instance B: tính đủ, SET tokens -> 0; ACCEPT
Kết quả: hai request được chấp nhận, nhưng chỉ còn một token ban đầu.
~~~

**Read–modify–write qua nhiều lệnh Redis không nguyên tử**. Chỉ đưa số đếm vào Redis mà không đảm bảo chuỗi thao tác nguyên tử vẫn gặp race condition. Với fixed window, `INCR` là nguyên tử, nhưng thao tác thiết lập TTL riêng cũng cần thiết kế cẩn thận để tránh key không hết hạn. Với token bucket, việc **đọc thời điểm, tính refill, kiểm tra cost, trừ token và ghi state** phải nằm trong một đơn vị nguyên tử.

Những lựa chọn thường dùng:

- Redis **Lua script** hoặc Redis Function thực hiện cùng một giao dịch logic trên một shard.
- Giao dịch compare-and-set/optimistic concurrency nếu kho dữ liệu hỗ trợ, có vòng retry và đo contention.
- Một dịch vụ quota trung tâm làm chủ state; các nút API gọi qua RPC có timeout và giới hạn đồng thời.
- Thuê trước từng phần quota cho các nút (leasing), giảm số lần gọi trung tâm nhưng cần quy tắc cấp phát, hết hạn và trả quota rõ ràng.

Không dùng `synchronized` hay `ReentrantLock` trong một JVM để bảo vệ nhiều instance: chúng chỉ khóa luồng của **một** tiến trình.

## 5. Token bucket nguyên tử bằng Redis Lua

Đoạn Lua dưới đây dùng đúng **một Redis key cho mỗi bucket**, lưu hai field `tokens` và `last_ms` trong hash. Mỗi request gọi script với:

- `KEYS[1]`: khóa bucket, ví dụ `rl:v1:orders:{a9e0c8de}` (mã opaque của tenant đã xác thực).
- `ARGV[1]`: capacity `B=20`.
- `ARGV[2]`: tốc độ refill theo **token/millisecond**: 10 token/giây = `0.01` token/ms.
- `ARGV[3]`: cost của request, ví dụ `1`.

Sử dụng **đồng hồ Redis** từ lệnh `TIME` giúp các instance không dùng thời gian hệ thống riêng để tính refill. Nếu đã lưu timestamp lớn hơn thời gian hiện tại, script giữ timestamp hiệu lực không đi lùi; vận hành vẫn cần đồng bộ thời gian và kiểm thử trường hợp failover.

~~~lua
-- Lưu dưới dạng classpath resource: redis/token-bucket.lua
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refillPerMs = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])

if not capacity or not refillPerMs or not cost
   or capacity <= 0 or refillPerMs <= 0
   or cost <= 0 or cost > capacity then
    return redis.error_reply("invalid token bucket policy")
end

local clock = redis.call("TIME")
local nowMs = tonumber(clock[1]) * 1000
            + math.floor(tonumber(clock[2]) / 1000)

local stored = redis.call("HMGET", key, "tokens", "last_ms")
local tokens = tonumber(stored[1]) or capacity
local lastMs = tonumber(stored[2]) or nowMs

-- Giữ mốc thời gian không lùi nếu đồng hồ bị điều chỉnh.
local effectiveNow = math.max(nowMs, lastMs)
local elapsedMs = effectiveNow - lastMs
tokens = math.min(capacity, tokens + elapsedMs * refillPerMs)

local allowed = 0
local retryAfterMs = 0
if tokens >= cost then
    tokens = tokens - cost
    allowed = 1
else
    retryAfterMs = math.ceil((cost - tokens) / refillPerMs)
end

-- Key tự hết hạn sau khi bucket có đủ thời gian để đầy trở lại.
-- Không gia hạn vô hạn cho tenant ngừng sử dụng.
local ttlMs = math.max(1000, math.ceil(2 * capacity / refillPerMs))
redis.call("HSET", key,
           "tokens", tostring(tokens),
           "last_ms", effectiveNow)
redis.call("PEXPIRE", key, ttlMs)

-- Redis trả về mảng số nguyên [allowed, remaining, retryAfterMs].
return {allowed, math.floor(tokens), retryAfterMs}
~~~

**Điểm quan trọng khi đọc code:**

1. Lua script chạy nguyên tử đối với các lệnh Redis trên cùng primary/shard. Hai instance không thể đồng thời đọc cùng giá trị token rồi cùng trừ vượt ngân sách.
2. Bucket chưa tồn tại bắt đầu đầy `capacity`. Đây là lựa chọn chính sách; một số endpoint nhạy cảm nên khởi tạo quota theo cách hạn chế hơn.
3. `cost > capacity` là **cấu hình/request cost không hợp lệ**, không phải tình huống chờ rồi sẽ có đủ token. Ứng dụng cần xác nhận cost từ nghiệp vụ đáng tin và từ chối sớm.
4. `retryAfterMs` là thời gian ước tính đủ token tại thời điểm quyết định, **không phải một đặt chỗ**. Request khác có thể dùng token trước khi client thử lại.
5. Script lưu số token dạng thực; số thực có thể có sai số làm tròn. Với yêu cầu quota tuyệt đối chính xác hoặc lượng token rất lớn, cân nhắc token dạng số nguyên cố định và giới hạn số học.
6. TTL giới hạn số key tồn tại khi nhiều tenant/identity ngừng gọi. Một tenant đang gửi liên tục vẫn có key sống lâu; vì vậy cần bảo vệ chống **high-cardinality keys** do người gọi gây ra.

**Độ bền của nguyên tử:** Script chỉ đảm bảo thao tác không bị xen kẽ trên primary đang xử lý. Nếu primary Redis hỏng trước khi cập nhật được sao chép đầy đủ, cấu hình replication bất đồng bộ có thể làm mất một số lần tiêu token sau khi failover. Vì vậy **Redis Lua không phải sổ cái quota tuyệt đối bền vững qua mọi sự cố**. Đối với quota thanh toán, tiền hoặc giới hạn pháp lý cần độ chính xác tuyệt đối, phải dùng cơ chế lưu trữ/giao dịch mạnh hơn hoặc giao thức đặt chỗ phù hợp.

Nếu triển khai **Redis Cluster**, mọi key được thao tác bởi cùng một script phải thuộc cùng hash slot. Ví dụ trên chỉ có **một key**, nên tương thích theo nguyên tắc này. Không thêm counter toàn cục ở slot khác vào cùng Lua script mà không thiết kế lại phân vùng dữ liệu.

## 6. Tích hợp Java/Spring với Redis

Với Spring Boot 3.x, Spring Data Redis và Java 17+, lưu đoạn script trên dưới tên `src/main/resources/redis/token-bucket.lua` trong **ứng dụng minh họa**. Không cần tự triển khai read–modify–write bằng nhiều lệnh ở client.

~~~java
import java.util.List;
import java.util.UUID;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public final class DistributedRateLimiter {
    private final StringRedisTemplate redis;
    private final RedisScript<List> script;

    public DistributedRateLimiter(StringRedisTemplate redis) {
        this.redis = redis;
        DefaultRedisScript<List> loaded = new DefaultRedisScript<>();
        loaded.setLocation(new ClassPathResource("redis/token-bucket.lua"));
        loaded.setResultType(List.class);
        this.script = loaded;
    }

    public Decision tryConsume(UUID authenticatedTenantId, int cost) {
        if (authenticatedTenantId == null || cost < 1 || cost > 20) {
            throw new IllegalArgumentException("invalid tenant or cost");
        }

        // ID lấy từ ngữ cảnh đã xác thực, không lấy từ header do client tự đặt.
        // {tenant-id} cũng có thể dùng làm hash tag Redis Cluster.
        String key = "rl:v1:orders:{" + authenticatedTenantId + "}";
        List<?> result = redis.execute(
            script, List.of(key), "20", "0.01", Integer.toString(cost)
        );
        if (result == null || result.size() != 3) {
            throw new IllegalStateException("rate limiter returned no decision");
        }

        boolean allowed = ((Number) result.get(0)).longValue() == 1;
        long remaining = ((Number) result.get(1)).longValue();
        long retryAfterMs = ((Number) result.get(2)).longValue();
        return new Decision(allowed, remaining, retryAfterMs);
    }

    public record Decision(
        boolean allowed, long remaining, long retryAfterMs
    ) {}
}
~~~

`StringRedisTemplate` dùng cùng `RedisScript` cho mọi instance; Spring Data Redis có thể cache script và gọi `EVALSHA`/`EVAL` khi cần. Nếu tên class trong code thực tế khác, cơ chế vẫn giữ nguyên: **một lời gọi Redis atomic cho mỗi lần tiêu token**.

Trong service/controller, chỉ thực hiện công việc đắt sau khi có quyết định cho phép:

~~~java
// tenantId phải lấy từ principal/JWT đã được xác minh bởi Spring Security.
DistributedRateLimiter.Decision decision =
    limiter.tryConsume(tenantId, 1);

if (!decision.allowed()) {
    long seconds = Math.max(
        1, (decision.retryAfterMs() + 999) / 1000
    );
    ProblemDetail problem = ProblemDetail.forStatus(429);
    problem.setTitle("Quá giới hạn tốc độ");
    problem.setDetail("Hãy thử lại sau một khoảng ngắn.");
    problem.setProperty("code", "RATE_LIMITED");

    return ResponseEntity.status(429)
        .header("Retry-After", Long.toString(seconds))
        .header("Cache-Control", "no-store")
        .contentType(MediaType.parseMediaType("application/problem+json"))
        .body(problem);
}

// Tiếp tục validation nghiệp vụ, authorization theo resource,
// idempotency và xử lý tạo đơn bằng service phù hợp.
~~~

Các import bổ sung cho đoạn controller gồm `org.springframework.http.ProblemDetail`, `MediaType` và `ResponseEntity`. Ví dụ là phần logic có thể đặt trong một handler với kiểu trả `ResponseEntity<?>`, không phải toàn bộ ứng dụng Spring có cấu hình authentication.

**Vị trí đặt giới hạn:** Với tenant đã xác thực, giới hạn nên chạy sau bước xác minh principal nhưng trước thao tác truy vấn/ghi đắt. Nếu cần chống flood vào endpoint login hay request không có token, đặt thêm giới hạn ở gateway/trước authentication; khóa theo tín hiệu tin cậy như client IP đã chuẩn hóa ở ingress và/hoặc tên tài khoản, đồng thời tránh coi IP là định danh duy nhất. Không tin `X-Tenant-ID`, `X-User-ID`, `X-Forwarded-For` do client Internet gửi trực tiếp.

**Không nhầm rate limiter với idempotency:** Một request tạo đơn có `Idempotency-Key` bị retry có thể phải trả lại kết quả cũ thay vì tạo đơn thứ hai. Chính sách trừ token cho lần retry hay không là lựa chọn hợp đồng cần định nghĩa; bảo đảm idempotency vẫn phải được xử lý riêng bằng key/request fingerprint và trạng thái nghiệp vụ.

## 7. Hợp đồng HTTP khi bị giới hạn

Khi quota của người gọi đã cạn, API có thể trả **429 Too Many Requests**. Không dùng 403 để thay thế mọi lần hết quota: 403 thường nói đến chính sách quyền truy cập, còn 429 cho client biết cần giảm nhịp. Trả **503 Service Unavailable** khi hệ thống tạm không thể đáp ứng do quá tải chung, không nhất thiết vì client vượt quota.

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 1
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Quá giới hạn tốc độ",
  "status": 429,
  "detail": "Hãy thử lại sau một khoảng ngắn.",
  "code": "RATE_LIMITED"
}
~~~

`Retry-After` có thể là số giây không âm hoặc HTTP-date; trong ví dụ dùng giây và làm tròn lên. Header này là **gợi ý thời điểm retry**, không đảm bảo lúc đó sẽ có token nếu traffic khác tiếp tục đến. Nếu response có `RateLimit`/`RateLimit-Policy` hoặc các header legacy `X-RateLimit-*`, cần nhất quán về tên, đơn vị, ý nghĩa khi có nhiều cửa sổ và dấu thời gian reset. Không đưa chi tiết bảo mật hoặc danh tính tenant khác vào body/header.

**Client xử lý 429 đúng cách:**

1. Đọc `Retry-After` nếu có và hợp lệ; giới hạn tối đa thời gian đợi theo deadline của ứng dụng.
2. Khi server không có gợi ý, dùng backoff tăng dần kèm **jitter** để tránh tất cả client thử lại đúng cùng một thời điểm.
3. Chỉ retry thao tác có thể retry an toàn. Với POST tạo resource, dùng cơ chế idempotency đã được server hỗ trợ; không tự gửi lại vô hạn và tạo bản ghi trùng.
4. Tôn trọng retry budget, cancellation và deadline; hiển thị thông báo phù hợp nếu không thể hoàn thành.

Ví dụ 10.000 client cùng nhận `Retry-After: 1` và thử lại chính xác sau 1 giây có thể tạo **thundering herd**. Thêm jitter có kiểm soát, queue hoặc admission control ở server giúp giãn đợt đến; không tăng capacity tùy ý khiến DB sụp đổ.

## 8. Burst giữa nhiều nút và bảo vệ downstream

Giả sử có **5 API instance**, mỗi instance nhận 10 request đồng thời từ cùng tenant. Nếu bucket tập trung còn 20 token, đúng 20 request với cost 1 có thể qua ở thời điểm ban đầu; các request còn lại nhận 429, kể cả khi chúng đến các instance khác nhau. Đó là ý nghĩa của **global per-tenant limit**.

Nhưng 20 request đi qua trong cùng vài millisecond vẫn có thể làm nghẽn pool DB có 8 connection. Vì vậy cần phân biệt các lớp:

~~~mermaid
flowchart LR
    C[Client] --> G[Gateway: IP / global safety]
    G --> A[API instances]
    A -->|Kiểm tra token| R[(Redis token bucket theo tenant)]
    A -->|Nếu được phép| S[Admission / concurrency limit]
    S --> Q[(DB và downstream)]
~~~

Trong hình, các API instance **gọi Redis để nhận quyết định**, rồi mới xử lý ở tầng concurrency khi được phép. Concurrency limit có thể dùng semaphore dùng chung hoặc triển khai tại tầng nhận job; một semaphore local trên từng instance tạo ra giới hạn **theo instance**, cần cộng ngân sách hoặc dùng cơ chế phối hợp nếu hợp đồng đòi giới hạn toàn hệ thống.

Đối với tác vụ đắt:

- Cho request nhẹ cost 1, request tạo báo cáo cost 5, nhưng chỉ khi cost được tính trên dữ liệu server đã xác minh.
- Đặt **max in-flight**, timeout tại gateway/service/DB, circuit breaker cho downstream dễ lỗi và hàng đợi có giới hạn nếu nghiệp vụ cho phép xử lý bất đồng bộ.
- Nếu nhận job vào queue, phân biệt giới hạn **số job chấp nhận** và **tốc độ worker xử lý**. Trả 202 Accepted cùng URL theo dõi job nếu hợp đồng API thực sự bất đồng bộ.
- Khi downstream nghẽn, cân nhắc 503 hoặc phản hồi từ chối sớm thay vì tiếp tục nhận và giữ hàng nghìn request đang chờ.

**Phân chia quota cho nhiều tầng:** Gateway có thể áp một trần an toàn chung, service áp quota theo tenant, endpoint áp chi phí nghiệp vụ, DB áp giới hạn đồng thời. Mỗi tầng nên có key, cửa sổ và lý do từ chối rõ ràng; nếu nhiều tầng trừ token ở những thời điểm khác nhau, phải định nghĩa cách chúng phối hợp để tránh các lần trừ vô nghĩa, trừ hai lần hoặc gây hiện tượng retry storm.

## 9. Khả năng mở rộng: một bucket nóng và phương án thuê quota

Redis Lua tập trung rất tiện, nhưng **một key của một tenant cực lớn** thường nằm trên một Redis primary/shard. Khi hàng chục nghìn request/giây cùng đụng một key, nó có thể thành điểm nóng. Redis Cluster giúp phân bố **nhiều key khác nhau** lên nhiều shard, nhưng không tự chia một bucket logic duy nhất thành nhiều key mà vẫn đảm bảo chính xác tuyệt đối.

| Thiết kế | Độ chính xác | Chi phí / đánh đổi |
| --- | --- | --- |
| Một bucket chung trên Redis | Nguyên tử trên một shard; chịu tác động failover | Khoảng một round trip Redis/request; hot key |
| Đếm local độc lập trên mỗi node | Tổng quota tăng theo số node | Rẻ nhưng phá hợp đồng global |
| Quota leasing có đặt chỗ trung tâm | Không dùng quá số token đã cấp **nếu cấp phát nguyên tử và tiêu token đúng** | Ít round trip hơn; quota nằm rải rác có thể bị bỏ không, fairness kém tức thời |
| Ước lượng phân tán / đồng bộ theo chu kỳ | Có thể vượt ngưỡng, sai số theo cơ chế | Giảm latency/central load; không hợp quota cần tính chính xác |
| Ghi quota vào DB giao dịch | Có thể mạnh hơn về độ bền và tính nhất quán | Đắt hơn, tăng contention và khó scale ở QPS lớn |

**Quota leasing:** Trung tâm giữ tổng ngân sách, cấp trước cho A 5 token, B 5 token, C 5 token. Mỗi instance chỉ cho phép request khi còn token đã thuê. Nếu cấp phát atomically từ ngân sách chung thì các node không tự tạo thêm token, nhưng request ở A có thể bị từ chối dù B còn token chưa dùng. Khi node chết, lượng token đã thuê có thể bị bỏ phí; cần TTL/thu hồi/lease epoch để tránh node cũ dùng lại token sau khi chuyển quyền.

Đối với nhiều vùng địa lý, một bộ đếm trung tâm tạo latency xuyên vùng; mỗi vùng có Redis riêng rồi đồng bộ bất đồng bộ sẽ có **sai số**. Chọn rõ chính sách “quota toàn cầu gần đúng, ưu tiên availability” hoặc “quota chặt, chấp nhận độ trễ và rủi ro mất availability”. Tránh công bố ràng buộc cứng mà triển khai thực tế chỉ là eventual consistency.

## 10. Mất Redis, failover và quyết định fail-open/fail-closed

Rate limiter cũng có thể trở thành nguồn gây lỗi. Nếu Redis timeout, service phải đưa ra quyết định có chủ đích theo loại endpoint, thay vì ngẫu nhiên do exception:

| Trường hợp | Hướng xử lý cân nhắc | Rủi ro cần công bố |
| --- | --- | --- |
| Trang danh mục công khai, thao tác đọc ít tốn tài nguyên | **Fail-open có bảo vệ**: fallback local giới hạn tạm thời + trần gateway | Có thể vượt global quota trong khoảng lỗi |
| Login/OTP hoặc endpoint chống brute force | **Fail-closed hoặc hạn chế mạnh**; tách policy chống abuse | Giảm availability khi kho đếm lỗi |
| Đặt hàng/giao dịch nhạy cảm | Tùy threat model; dùng admission và transaction/idempotency riêng | Mất Redis không được gây ghi trùng hay vượt quyền |
| Redis chậm/primary failover | Timeout ngắn, circuit breaker, giảm traffic và phục hồi có giám sát | Trả 503 hoặc local fallback theo chính sách |
| Đồng hồ bị chỉnh hoặc replica có state cũ | Theo dõi skew, failover, replica lag, giới hạn refill bất thường | Có thể refill sai hoặc mất lần trừ gần nhất |

**Fail-open** nghĩa là tiếp tục phục vụ khi không kiểm tra được quota; **fail-closed** nghĩa là từ chối hoặc tạm dừng. Hai lựa chọn không có đáp án chung cho mọi API. Ví dụ fallback “mỗi node cho 10 request/giây” trong cụm 10 node có thể cho tổng 100 request/giây; phải đặt mức local đủ thấp và giới hạn thời gian fallback nếu chọn hướng đó.

Không chặn thread HTTP chờ Redis vô thời hạn. Dùng timeout, giới hạn connection pool, metrics, cảnh báo và chính sách trở lại trạng thái bình thường. Khi primary thay thế, lưu ý Redis replication thường bất đồng bộ; atomic script chỉ bảo vệ các race lúc đang chạy, không tự khắc phục mất state sau sự cố.

## 11. Bảo mật key và chống lạm dụng bộ đếm

Việc chọn key quyết định ai chia sẻ quota với ai:

- **Định danh tenant/user:** lấy từ JWT đã kiểm tra chữ ký và claim tin cậy hoặc session/principal server-side. Không lấy từ header `X-Tenant-ID` hay JSON body do client tự khai.
- **Route group:** dùng nhãn cố định như `orders.write` hoặc `reports.read`; tránh đưa path chứa ID ngẫu nhiên thành key riêng cho từng request (`/orders/123`, `/orders/124`), khiến quota bị phân mảnh.
- **Nguồn chưa đăng nhập:** lấy IP đã được proxy đáng tin xác định, có thể kết hợp account/login identifier theo chính sách chống lạm dụng. Chỉ tin `Forwarded`/`X-Forwarded-For` từ hop ingress đã kiểm soát. NAT, IPv6 rotation và người dùng chung IP khiến giới hạn IP đơn thuần có false positive và dễ vượt ngưỡng.
- **Bảo vệ dữ liệu:** không lưu Bearer token nguyên văn, email hoặc số điện thoại trong key Redis; có thể dùng opaque ID hoặc hash có quản lý. Đặt namespace và phiên bản chính sách rõ ràng, ví dụ `rl:v1:orders:{tenantOpaqueId}`.
- **Chống chiếm bộ nhớ:** mọi key có TTL hữu hạn, có giới hạn key cardinality, metric số key, eviction/Redis maxmemory được cấu hình thận trọng. Kẻ tấn công có thể tạo nhiều identity giả để làm nổ bộ nhớ.

Rate limiting còn là một cơ chế **fairness**, không phải điều kiện để bỏ kiểm tra authorization. Hết quota được xử lý bằng 429; vượt quyền vẫn phải trả 401/403 theo hợp đồng, bất kể còn token.

## 12. Kiểm thử phân tán, tính toán ranh giới và quan sát

### 12.1. Ca kiểm thử nên có

| Kiểm thử | Cách tạo tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Nhiều instance cùng bucket | 3 instance gửi request đồng thời với **cùng tenant key** | Tổng quyết định được nhận tuân theo cùng bucket, không nhân ba |
| Cạnh tranh trừ token | Bucket còn 1 token; hai request cost 1 cùng đến | Chỉ một request được nhận trước khi refill |
| Cạn burst | Bucket đầy capacity 20, 25 request gần như đồng thời | Ban đầu tối đa 20 request tại cùng thời điểm logic; request khác bị 429, trừ refill trong lúc kiểm thử |
| Phục hồi token | Cạn bucket rồi tiến đồng hồ mô phỏng 100 ms | Với rate 10/s và cost 1, có khoảng 1 token mới |
| Request có cost lớn | Bucket còn 4 token, request cost 5 | 429; không trừ token; thời gian chờ xấp xỉ 100 ms |
| Chuyển node / restart | Request lần lượt qua A, B, C; restart B | Cùng quota vì state ở Redis |
| Tách tenant | Tenant A cạn token, tenant B còn quota | B vẫn được phục vụ; không khóa chéo |
| Redis không khả dụng | Timeout/kết nối bị từ chối | Đi đúng fail-open/fail-closed policy đã công bố |
| Redis failover | Chuyển primary dưới tải kiểm soát | Không deadlock, có alert; đánh giá mất đếm/overshoot theo RPO |
| API trả 429 | Request bị từ chối qua HTTP thực | Có `Retry-After` hợp lệ, JSON Problem Details, không gọi service đắt |
| Concurrent slow requests | 10 rps nhưng mỗi request chạy 2 giây | In-flight được giới hạn độc lập với rate |

**Lưu ý thời gian kiểm thử:** Nếu dùng Redis `TIME` thật, 25 request đến trong nhiều chục hoặc hàng trăm millisecond có thể khiến token hồi lại ngay trong lúc test. Đừng viết assertion “chắc chắn chỉ 20 được nhận” mà không kiểm soát thời gian. Có thể tạo phiên bản script test nhận đồng hồ giả cố định, hoặc kiểm tra số accepted theo **`B + r × elapsed`** có dung sai do thời gian quan sát. Phần kiểm thử đồng hồ giả phải tách khỏi script production dùng `TIME` tập trung.

Ví dụ kiểm thử concurrency phác họa (Java/JUnit), với một bucket mới và rate cực thấp để token chưa kịp refill trong thời gian chạy test:

~~~java
@Test
void atomicBucketDoesNotMultiplyWithNodeCount() throws Exception {
    UUID tenant = UUID.randomUUID(); // Bucket mới, chưa có state.
    int attempts = 40;
    ExecutorService pool = Executors.newFixedThreadPool(12);
    CountDownLatch start = new CountDownLatch(1);
    try {
        List<Future<Boolean>> results = new ArrayList<>();
        for (int i = 0; i < attempts; i++) {
            DistributedRateLimiter target = instances.get(i % instances.size());
            results.add(pool.submit(() -> {
                start.await();
                return target.tryConsume(tenant, 1).allowed();
            }));
        }
        start.countDown();
        long accepted = 0;
        for (Future<Boolean> future : results) {
            if (future.get(5, TimeUnit.SECONDS)) {
                accepted++;
            }
        }
        // Minh họa: thử với phiên bản policy rate rất thấp,
        // đủ để refill không thêm token trong thời gian test.
        assertEquals(20, accepted);
    } finally {
        pool.shutdownNow();
    }
}
~~~

Đoạn trên giả định `instances` là các client/service kết nối tới **cùng Redis**, nhưng phải được cấu hình rate **rất thấp trong test** thay vì giá trị `0.01 token/ms` của ví dụ production; nếu không có thể xuất hiện refill trong lúc test. Đây là phác họa để xây dựng test integration với Testcontainers Redis hoặc Redis thử nghiệm, không phải code test độc lập đã cấu hình sẵn. Các import cần có: `java.util.UUID`, `java.util.concurrent.*`, `java.util.List`, `java.util.ArrayList` và JUnit Jupiter `@Test`/`assertEquals`.

### 12.2. Metrics để đánh giá

Theo dõi ít nhất:

- Số request **allowed/denied** theo route group và policy, tỷ lệ 429 theo tenant tier (dùng label có cardinality thấp).
- Độ trễ p50/p95/p99 của lời gọi Redis, số timeout, tỷ lệ lỗi script, Redis CPU, memory, evictions, hot keys và replica lag.
- Burst thực tế, request cost, số tác vụ đang xử lý, queue depth, lỗi 503, DB connection pool saturation.
- Số lần fail-open/fail-closed, thời gian vận hành fallback, khác biệt allowed giữa các vùng/instance và retry storm sau khi trả 429.

Không gắn `tenantId`, IP, access token hoặc khóa Redis thô thành metric label cardinality cao; giữ log có giới hạn, ẩn danh hoặc hash khi cần. Điều tra một tenant cụ thể bằng log/tracing truy cập kiểm soát, không tạo hàng triệu time series.

## 13. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — Tính burst.** Bộ giới hạn có capacity 15 token, refill 5 token/giây. Tại `t=0` bucket đầy và 15 request cost 1 được nhận. Giả sử không có yêu cầu khác: (a) khi nào một request cost 1 tiếp theo có thể được nhận? (b) sau 2 giây có thể nhận tối đa bao nhiêu request cost 1 liên tiếp tại cùng thời điểm? (c) request cost 12 đến sau 2 giây được nhận không? (d) một limiter fixed-window 15 request/3 giây có cách ứng xử burst sát ranh giới cửa sổ giống vậy không?

**Bài 2 — Sửa race condition.** Hai instance cùng thấy bucket còn 1 token trước khi ghi. Hãy chỉ ra vì sao `GET` rồi `SET` từng lệnh là sai, và giải thích cách Lua script ở trên ngăn hai lời gọi được nhận cùng lúc. Nếu chuyển sang Redis Cluster và thêm key quota toàn hệ thống vào script, cần lưu ý điều gì về hash slot?

**Bài 3 — Thiết kế hệ thống.** Dịch vụ có 8 instance, ba tenant tier: Free 2 rps/burst 5, Pro 20 rps/burst 40, Enterprise 100 rps/burst 200. Hãy xác định: khóa quota tin cậy, cấu hình burst/rate mỗi tier, khi nào dùng central Redis, cách xử lý một tenant Enterprise tạo hot key và lựa chọn fail-open/fail-closed cho login so với endpoint đọc danh mục.

**Bài 4 — Xử lý 429.** Viết client Java dùng `HttpClient` gửi POST có `Idempotency-Key`, xử lý `Retry-After` và retry tối đa hai lần với backoff/jitter cùng deadline. Giải thích vì sao không thể retry mọi POST một cách an toàn khi server không hỗ trợ idempotency.

**Gợi ý đáp án:** Bài 1: (a) khoảng 0,2 giây; (b) 10 token; (c) không, vì còn 10 token; (d) fixed window có thể cho hai đợt sát ranh giới, còn token bucket refill liên tục. Bài 2: đọc và ghi rời rạc gây lost update; Lua thực thi phần đọc–tính–ghi atomically trên một shard; multi-key script Redis Cluster phải đặt key cùng hash slot. Bài 3: quota theo tenant đã xác thực, capacity khác nhau theo tier, cân nhắc quota leasing khi hot key, có timeout/fallback rõ ràng và chống abuse mạnh hơn ở login. Bài 4: thời gian chờ và retry budget giúp giảm đợt đồng loạt; idempotency bảo vệ không tạo hiệu ứng nghiệp vụ trùng khi client không biết request trước đã hoàn tất hay chưa.

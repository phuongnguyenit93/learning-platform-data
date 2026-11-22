# Rate limiting, quota và giới hạn số yêu cầu đồng thời

Một API báo cáo có thể phục vụ 100 request/giây khi mỗi truy vấn chỉ mất 20 ms. Nhưng cùng tốc độ đó, nếu một truy vấn kéo dài 10 giây, hệ thống có thể có khoảng 1.000 request đang chờ, làm cạn connection pool hoặc bộ nhớ. Ngược lại, một khách hàng gửi rất ít request nhưng mỗi request xuất 500.000 dòng dữ liệu vẫn có thể tiêu tốn quá ngân sách được phép. **Rate limiting, quota và giới hạn số yêu cầu đồng thời giải quyết ba vấn đề khác nhau**: tốc độ đến, tổng quyền sử dụng và số công việc đang chiếm tài nguyên.

Bài thuộc chương **Giới hạn và chống lỗi** của module **INTEGRATION_API_REST**. Ta áp dụng các khái niệm này vào REST API theo resource, URI, HTTP method và status rõ ràng; triển khai với Java/Spring, Redis và database; kết hợp bảo mật, idempotency, thông báo lỗi, kiểm thử và giám sát.

## 1. Mục tiêu và ba loại giới hạn

Sau bài này, bạn có thể:

1. Phân biệt **rate limit**, **quota/usage budget** và **concurrency limit (bulkhead)**; đặt giới hạn theo actor, tenant, endpoint và chi phí.
2. So sánh **fixed window, sliding window, token bucket, leaky bucket** và lựa chọn thuật toán dựa vào burst/fairness.
3. Thiết kế admission control ở gateway/service và bảo vệ bất biến sử dụng ở database.
4. Triển khai một limiter **nguyên tử với Redis Lua**, dùng **Semaphore** trong Spring cho tài nguyên cục bộ, hiểu giới hạn multi-replica.
5. Trả **429 Too Many Requests**, **Retry-After**, 503 và Problem Details đúng ngữ nghĩa; phân biệt việc bị từ chối với dependency đang lỗi.
6. Xử lý queue có giới hạn, lease, timeout/cancellation, idempotency và các chính sách fail-open/fail-closed.
7. Kiểm thử nhiều client/tenant, tranh chấp đồng thời, lỗi Redis, clock skew, retry storm và false positive.

| Cơ chế | Đơn vị thường dùng | Ví dụ | Cái không tự giải quyết |
|---|---|---|---|
| **Rate limiting** | Request/giây, request/phút hoặc token/giây | 30 lượt tìm kiếm/phút/user | Tổng chi phí rất lớn trên một request |
| **Quota** | Tổng operation, byte, SMS, tiền hoặc đơn vị compute | 2 GiB dữ liệu xuất/ngày/tenant | Burst khiến service quá tải ngay tức thì |
| **Concurrency limit** | Số request/job đang chạy hoặc permit | Tối đa 4 export job RUNNING/tenant | Gửi request nối tiếp liên tục vượt ngân sách |

Ví dụ chính sách tổng hợp cho API báo cáo: mỗi user được **60 lần thử/phút**, mỗi tenant tối đa **10.000 cost units/ngày**, và toàn cluster chỉ xử lý **20 export cùng lúc**. Các con số là **giả định minh họa**, không phải ngưỡng an toàn phổ quát; phải hiệu chỉnh theo SLO và capacity thật.

### 1.1. Định luật Little giúp hiểu áp lực concurrency

Ở trạng thái ổn định, số request đang trong hệ thống trung bình xấp xỉ:

\[
L = \lambda W
\]

với **L** là số request đang xử lý/chờ, **λ** là tốc độ đến trung bình, **W** là thời gian mỗi request nằm trong hệ thống. Nếu **100 request/giây** và mỗi request trung bình **2 giây**, trung bình có khoảng **200 request in-flight**. Khi downstream chậm từ 2 lên 8 giây trong lúc lượng đến không giảm, áp lực in-flight có thể tăng nhanh dù RPS giữ nguyên.

Đây là quan hệ trung bình, **không** dự báo p99, burst hoặc giới hạn chính xác của từng pool. Cần đo thực tế **active request, latency, pending queue, connection pool, CPU, heap, GC** và throughput của downstream.

## 2. Chọn ranh giới và danh tính của limit

Trước khi chọn thuật toán, trả lời: **“Ai dùng tài nguyên nào, trong thời gian nào, vượt mức thì điều gì xảy ra?”**

| Phạm vi | Mục đích | Điểm phải lưu ý |
|---|---|---|
| **Global** | Bảo vệ CPU, DB, API upstream hoặc tổng ngân sách | Một tenant lớn không được đẩy cả dịch vụ vào quá tải |
| **Tenant/organization** | Công bằng và đúng gói hợp đồng | Tenant lấy từ token/identity đã được kiểm chứng |
| **User/actor** | Ngăn một account phát quá nhiều request | Người dùng hợp lệ có thể có nhiều thiết bị |
| **Credential/client application** | Bảo vệ kênh tích hợp và billing | Token/key có thể bị cấp lại; không dùng đơn độc cho quota quyền lợi |
| **IP/network** | Giảm abuse trước xác thực | NAT, proxy và mạng chia sẻ gây false positive |
| **Endpoint/operation** | Chi phí khác nhau theo chức năng | GET nhẹ khác POST export/OTP tính phí |
| **Beneficiary/resource** | Giới hạn quyền lợi nghiệp vụ | Không tin ID beneficiary do client tự khai |

Key minh họa cho limiter: **environment + policy version + tenantId + verified userId + operation**. Dữ liệu nhận dạng nên pseudonymize/HMAC nếu chia sẻ rộng trong Redis/metric; tuyệt đối không đưa **JWT, session ID, email hay số điện thoại thô** vào log và key. Xác thực và xác định tenant **trước khi áp quota theo tenant**; pre-auth có thể dùng quota riêng theo mạng/đích OTP và ngân sách chung.

**IP từ X-Forwarded-For không đương nhiên đáng tin**: chỉ dùng khi ingress/proxy biên đã loại bỏ header client tự gửi và thiết lập chuỗi trusted proxies; không xây rate limiter dựa trên IP client có thể tự khai. IP không phải bằng chứng một người: khóa mọi người dùng phía sau một NAT chỉ vì một người spam là sai chính sách.

### 2.1. Giới hạn không thay authorization

Ngay cả request chưa vượt bất kỳ limit nào vẫn phải kiểm tra **scope/role, tenant, owner và trạng thái tài nguyên**. Ngược lại, token hoàn toàn hợp lệ vẫn có thể gửi quá nhiều request hoặc chiếm hàng nghìn slot. Đối với quyền lợi có giá trị, quota theo **người nhận quyền lợi đã xác minh** chứ không chỉ theo số lượng JWT hay IP.

Giới hạn theo user còn cần tính đến **kẻ tấn công cố ý làm nạn nhân hết quota** bằng nhiều request reset password/OTP. Dùng cooldown và chính sách chống lạm dụng tách biệt giữa request chưa xác thực với user đã xác thực; quy trình kháng nghị phải tránh bị chiếm dụng làm DoS.

## 3. Các thuật toán rate limit và tính công bằng

### 3.1. Fixed window counter

Chia thời gian hoặc đếm từ request đầu thành các cửa sổ, giới hạn tối đa **N request/cửa sổ**. Redis **INCR + TTL** dễ triển khai và có chi phí thấp, nhưng tại ranh giới hai cửa sổ, một actor có thể tạo gần **2N request trong thời gian ngắn**. Cửa sổ gắn mốc epoch cho phép nhiều client đồng loạt được reset; cửa sổ tính từ lượt đầu giảm đồng bộ reset nhưng vẫn có burst ở ranh giới riêng.

### 3.2. Sliding window

**Sliding log** lưu timestamp sự kiện rồi đếm trong khoảng trượt, cho giới hạn sát thực tế hơn nhưng tăng bộ nhớ/CPU và phải dọn bản ghi. **Sliding window counter** nội suy giữa hai bucket thời gian giảm chi phí nhưng chỉ xấp xỉ; khi yêu cầu fairness nghiêm ngặt, phải kiểm thử sai số gần ranh giới.

### 3.3. Token bucket

Bucket có **capacity B**, token được bổ sung với tốc độ **r token/giây** đến tối đa B; mỗi request tiêu thụ số token tương ứng chi phí. Nó cho phép một burst nhỏ nhưng giữ tốc độ trung bình. Ví dụ B=20 và r=5/s cho phép burst tới 20 request sau thời gian rảnh; sau đó chỉ khoảng 5 request/s khi ổn định. **Không đồng nghĩa 20 request đang chạy cùng lúc**.

Token bucket có thể dùng **weighted cost**: GET item dùng 1 token, export báo cáo lớn dùng nhiều token. Cần định nghĩa trọng số theo tài nguyên thật, chống client tự khai cost và xử lý trường hợp phát hiện chi phí thực tế sau khi chạy.

### 3.4. Leaky bucket hoặc hàng đợi có giới hạn

Làm mượt tốc độ xử lý bằng cách xếp request vào một queue và giải phóng theo nhịp. Nếu queue không giới hạn, request tăng làm **latency, RAM và deadline** tăng vô hạn: hệ thống chuyển từ lỗi quá tải sang sụp vì bộ nhớ. Đặt **max queue length, wait timeout, fairness và chính sách từ chối sớm**.

| Mục tiêu | Ứng viên | Lý do |
|---|---|---|
| Giới hạn đơn giản per user với chi phí thấp | Fixed window | Dễ vận hành, chấp nhận burst biên |
| Độ công bằng theo 60 giây trượt | Sliding log/counter | Giảm khả năng lợi dụng ranh giới |
| Cho burst UX ngắn nhưng giới hạn bình quân | Token bucket | Phù hợp tương tác người dùng |
| Bảo vệ downstream có tốc độ xử lý ổn định | Leaky bucket/queue bounded | Điều tiết tải nhưng cần giới hạn độ chờ |

Đừng chọn cùng một thuật toán cho mọi route chỉ vì thư viện hỗ trợ sẵn. Giá trị **limit, burst, concurrency, queue** phải đi cùng nhau theo ranh giới chi phí.

## 4. Admission control theo nhiều tầng

~~~mermaid
flowchart LR
    C["HTTP client"] --> G["Gateway: TLS, body/rate global"]
    G --> A["Spring Security: identity/scope"]
    A --> R{"Rate budget actor/tenant"}
    R -->|vượt| E["429 + Retry-After"]
    R -->|được| Q{"Quota / cost budget"}
    Q -->|hết quyền| B["409/422 theo contract"]
    Q -->|còn| S{"Bulkhead: in-flight permits"}
    S -->|hết chỗ| O["429/503 theo nguyên nhân"]
    S -->|có| D["Business service + DB/queue"]
    D --> F["Response + metrics"]
~~~

**Gateway** bảo vệ tải chung trước khi request chiếm tài nguyên đắt; **security filter** xác minh identity; **service** tính entitlement/cost; **bulkhead** bảo vệ connection/worker; **database** giữ bất biến. Không mọi hệ thống bắt buộc có tất cả lớp theo đúng thứ tự trên; việc tra **idempotency record** cho request đã hoàn tất cần được đặt hợp lý để replay không tạo chi phí/quyền lợi mới nhưng vẫn không mở đường spam replay.

**Từ chối sớm (load shedding)** có thể tốt hơn nhận mọi request rồi để timeout sau 20 giây. Chặn càng sát nguồn quá tải, càng ít công việc vô ích. Nhưng cũng cần bảo vệ fairness: một tenant lớn không được tiêu hết global permits khiến tenant khác không còn chỗ; có thể dùng **global + per-tenant bulkhead** và reserved capacity theo policy.

### 4.1. Hàng đợi và công việc bất đồng bộ

Với POST tạo export job: **202 Accepted** chỉ hợp lý khi hệ thống đã **lưu bền vững job/operation** để client theo dõi. Trước đó hãy kiểm tra **quota số job active**, tổng byte/cost và dung lượng queue. Nếu queue đầy hoặc job store lỗi, không trả 202 giả; trả lỗi overload/dependency phù hợp, có thể là **503**. Trả **Location: /v1/jobs/{id}** theo contract, sau đó kiểm soát các trạng thái **QUEUED → RUNNING → COMPLETED/FAILED/CANCELLED**, TTL và cleanup.

## 5. Redis: limiter nguyên tử trên nhiều instance

Một bộ đếm bằng **ConcurrentHashMap** trên từng Spring instance chỉ giới hạn từng process. Nếu có năm replica, user có thể được nhận gấp nhiều lần hạn mức khi load balancer phân phối request. Redis hoặc dịch vụ rate-limit tập trung cho phép kiểm tra cùng **một key trên mọi instance**. Tất nhiên, Redis không biến mạng thành exactly-once và vẫn có tình huống failover/partition cần chính sách.

### 5.1. Fixed window với Lua

Giả sử giới hạn **10 request/60 giây** kể từ request đầu trong cửa sổ, theo **actor + operation**. Lua thực hiện cập nhật và đọc TTL trong **một lời gọi Redis**:

~~~lua
-- KEYS[1]: key tạo bởi server, đã pseudonymize.
-- ARGV[1]: TTL tính bằng milliseconds.
local n = redis.call('INCR', KEYS[1])
if n == 1 then
    redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[1]))
end
local ttl = redis.call('PTTL', KEYS[1])
return {n, ttl}
~~~

**INCR và PEXPIRE nguyên tử trong Lua** tránh tình huống process chết sau khi tăng counter nhưng trước khi đặt TTL. Nếu **n ≤ 10**, cho phép; nếu **n > 10**, trả 429 và gợi ý thời gian chờ tương ứng TTL. **Request bị từ chối vẫn được đếm** theo chính sách này, nhằm giảm spam; nếu cần giới hạn “số lần thành công”, phải dùng quota riêng tại service/DB.

Ví dụ Spring Data Redis:

~~~java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

record RateDecision(boolean allowed, long retryAfterSeconds) {}

@Component
class RedisRequestLimiter {
    private static final long LIMIT = 10;
    private static final long WINDOW_MS = 60_000;
    private static final String LUA = """
            local n = redis.call('INCR', KEYS[1])
            if n == 1 then
                redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[1]))
            end
            local ttl = redis.call('PTTL', KEYS[1])
            return {n, ttl}
            """;

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<List> script;

    RedisRequestLimiter(StringRedisTemplate redis) {
        this.redis = redis;
        this.script = new DefaultRedisScript<>();
        this.script.setScriptText(LUA);
        this.script.setResultType(List.class);
    }

    RateDecision check(String trustedOpaqueKey) {
        // trustedOpaqueKey do server tạo từ verified principal + operation.
        String key = "limit:search:v1:" + trustedOpaqueKey;
        List<?> result = redis.execute(script,
                List.of(key), String.valueOf(WINDOW_MS));
        if (result == null || result.size() != 2) {
            throw new LimiterUnavailable();
        }
        long count = ((Number) result.get(0)).longValue();
        long ttlMs = ((Number) result.get(1)).longValue();
        if (ttlMs < 0) {
            throw new LimiterUnavailable();
        }
        long waitSeconds = Math.max(1, (ttlMs + 999) / 1000);
        return new RateDecision(count <= LIMIT,
                count <= LIMIT ? 0 : waitSeconds);
    }
}

class LimiterUnavailable extends RuntimeException {}
~~~

Đây là **một fixed-window limiter**, không phải token bucket. Bảo đảm atomicity của **một script trên một primary Redis tại thời điểm thực thi**; failover có thể làm mất một số cập nhật chưa được replicate, và Redis Cluster yêu cầu các key dùng trong cùng script nằm đúng slot. Khi cửa sổ hết hạn, việc dùng script với **PTTL gần 0** có thể cho phép retry sát mốc; client vẫn phải áp backoff/jitter để tránh dồn tải.

**Không chấp nhận key tự khai trong HTTP header.** Tạo key từ verified user/tenant và route template, tùy chọn **HMAC** để tránh lộ PII. Đặt TTL cho mọi limiter key, giới hạn cardinality và giám sát memory. Với hàng triệu unique key do attacker tạo, Redis bản thân cũng có thể bị exhaustion; cần bảo vệ đầu vào và admission pre-auth ở edge.

### 5.2. Tính toàn vẹn khác với tính sẵn sàng

Redis không sẵn sàng đặt ra lựa chọn **fail-open hay fail-closed**:

- Với **GET catalog công khai**: có thể cho phép ở mức dự phòng bảo thủ từ gateway, ghi metric và cảnh báo, nếu rủi ro được chấp nhận.
- Với **gửi SMS trả phí, mua hàng giới hạn, lấy voucher**: thường không nên cho tiêu tốn giá trị nếu limiter/quota bắt buộc không được xác minh; trả lỗi hạ tầng như **503**, không giả là user vượt 429.
- Với **kết quả replay idempotent đã commit**: có thể trả lại kết quả nếu xác minh an toàn từ operation store, theo hợp đồng, mà không tạo side effect mới.

Chính sách phải được duyệt trước sự cố, có test và runbook; không lặng lẽ chuyển sang bộ đếm cục bộ khiến giới hạn khác nhau giữa các replica. Cấu hình Redis timeout cũng phải ngắn hơn **request deadline**; limiter không được giữ mọi thread chờ Redis cho đến khi cả service cạn tài nguyên.

## 6. Quota: hạn mức sử dụng có giá trị nghiệp vụ

Rate limiter trả lời “bao nhiêu lần thử?”. **Quota** trả lời “được dùng bao nhiêu quyền hoặc tài nguyên?”. Một tenant có thể được xuất **2 GiB dữ liệu/ngày** dù chỉ gửi ba POST; một khách được nhận **một voucher/chiến dịch** dù gửi request chậm; một account chỉ được có **mười job đang hoạt động**. Quota có thể có **chu kỳ thanh toán, timezone, rollover, top-up và chính sách hoàn trả khi job lỗi**, nên phải được công bố trong contract.

### 6.1. Reservation và quyết toán chi phí

Với export tốn chi phí chỉ biết chính xác sau khi chạy:

1. Ước tính **cost tối đa được phép** từ dữ liệu server, không tin field **estimatedCost** của client.
2. Trong transaction, **reserve** đủ ngân sách bằng cập nhật có điều kiện, ghi operation ID/đơn giá/TTL.
3. Chạy job sau khi đã lưu bền vững; theo dõi thực tế theo giới hạn byte/CPU/thời gian.
4. Khi thành công, **settle** chi phí thực; khi lỗi/hủy đúng policy, **release phần chưa dùng** đúng một lần.
5. Worker crash được reconciler xử lý; không để reservation “treo” vô thời hạn.

Không nhất thiết refund mọi quota nếu API đã tiêu tốn tài nguyên dù client ngắt kết nối; chính sách **charge-on-attempt, charge-on-success, charge-on-usage** phải rõ và nhất quán. Client không được tự tạo request mới để đòi quota quay về bằng cách hủy connection.

### 6.2. Cập nhật nguyên tử tại DB

Một cách đơn giản để trừ quota đã được cấp trước khi tạo job:

~~~sql
-- :cost > 0 được validate server-side trước transaction.
UPDATE tenant_budgets
   SET remaining_units = remaining_units - :cost
 WHERE tenant_id = :tenant_id
   AND period_id = :period_id
   AND remaining_units >= :cost;
~~~

Chỉ khi **affected rows = 1** mới được tạo reservation/job **trong cùng DB transaction**. Hai request đồng thời tranh phần quota cuối sẽ không thể cùng trừ quá mức nếu thao tác atomic. Thêm **unique constraint trên (tenant_id, operation_id)** hoặc idempotency record để request retry không trừ lần hai. Đừng `SELECT remaining; if (enough) UPDATE` không có bảo vệ đồng thời.

Nếu ngân sách **theo số lần thành công**, đừng coi Redis INCR là nguồn sự thật: cần **ledger + constraint** để có thể audit, điều chỉnh/hoàn quota, xử lý duplicate event. Một transaction DB không tự bao trùm thanh toán ở PSP hoặc message broker; dùng **transactional outbox, operation ID và idempotent consumer** khi tác động đi qua ranh giới hệ thống.

### 6.3. Quota hết khác hệ thống quá tải

Quota gói dịch vụ đã hết có thể được thể hiện bằng **403** cho entitlement không có, **409** khi xung đột trạng thái hạn mức, hoặc **422** khi không xử lý được yêu cầu theo hợp đồng nghiệp vụ. Không bắt buộc trả **429** nếu việc chờ vài giây không giúp khắc phục. Ngược lại, request nhanh vượt hạn mức theo phút dùng **429**; server hết capacity không phải lỗi của một actor có thể dùng **503**.

## 7. Hợp đồng HTTP khi từ chối request

~~~http
GET /v1/reports?limit=20 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 34
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/rate-limited",
  "title": "Too many requests",
  "status": 429,
  "detail": "Try again later.",
  "code": "RATE_LIMITED"
}
~~~

**429** chỉ việc client đã gửi quá nhiều request trong khoảng thời gian theo chính sách; **Retry-After** theo HTTP có thể là **delay-seconds hoặc HTTP-date**. Đừng trả 429 với Retry-After lớn hơn thời gian hợp đồng cho phép theo dõi; client vẫn cần jitter/budget. Nếu phát các header biểu thị **limit/remaining/reset**, phải mô tả rõ tên, phạm vi, đơn vị, thuật toán và cách chúng thay đổi khi có nhiều lớp giới hạn. **Header limit không cấp thêm quyền vượt quota nghiệp vụ**.

| Nguyên nhân | Status điển hình | Điều client nên làm |
|---|---|---|
| Không xác thực được | **401** + WWW-Authenticate phù hợp | Xác thực lại |
| Thiếu scope/quyền | **403**, có thể 404 khi che resource | Không retry mù |
| Body quá lớn | **413 Content Too Large** | Giảm dữ liệu |
| Rate limit cho actor/tenant | **429** | Chờ Retry-After/budget, giảm tần suất |
| Quota/gói nghiệp vụ không đủ | **409/403/422** theo contract | Đổi yêu cầu/nâng gói/chờ kỳ mới nếu cho phép |
| Service overload hoặc limiter hỏng | **503** | Backoff, retry có giới hạn nếu an toàn |
| If-Match cũ | **412** | Đọc lại phiên bản, giải quyết conflict |
| Idempotency-Key trùng nhưng payload khác | **409** theo contract | Không đổi payload dưới cùng key |

**Retry-After không bảo đảm lần sau sẽ thành công**: limit có thể áp dụng đồng thời ở user, tenant, global và downstream. Dù request là **GET idempotent**, retry hàng loạt vẫn gây thundering herd. Với POST tạo order, 429/503/timeout không chứng minh lần trước chưa commit; cần **Idempotency-Key có scope và payload fingerprint** hoặc endpoint tra trạng thái để tránh lặp.

## 8. Giới hạn số yêu cầu đồng thời: bulkhead và backpressure

**Concurrency limit** kiểm soát số tác vụ **đang thực thi**, không đếm request đến trong một khoảng thời gian. Nếu mỗi tác vụ giữ một DB connection hoặc đợi một HTTP dependency, số tác vụ in-flight cần nhỏ hơn capacity thực và có **headroom** cho health check, admin, retry và luồng quan trọng.

Ví dụ: upstream có tối đa **40 connections**, service đồng thời gọi upstream từ bốn replica. Đặt **40 permits trên mỗi replica** là sai: tổng có thể lên đến 160. Nếu chỉ cấp **8 permits/replica**, tải phân phối đều thì có khoảng 32 lời gọi, nhưng khi autoscale hoặc tải lệch vẫn phải có **global limit** hoặc upstream-side admission. Giới hạn process-local chỉ là một **bulkhead cục bộ**, hữu ích nhưng không chứng minh tuân thủ hợp đồng trên toàn cluster.

### 8.1. Java Semaphore cho tác vụ đồng bộ

~~~java
import java.util.concurrent.Semaphore;
import org.springframework.stereotype.Service;

class BulkheadFull extends RuntimeException {}

interface ReportEngine {
    ReportView generate(VerifiedActor actor, ExportRequest input);
}

@Service
class SynchronousReportRunner {
    private final Semaphore permits = new Semaphore(8, true);
    private final ReportEngine engine;

    SynchronousReportRunner(ReportEngine engine) {
        this.engine = engine;
    }

    ReportView run(VerifiedActor actor, ExportRequest input) {
        if (!permits.tryAcquire()) {
            throw new BulkheadFull();
        }
        try {
            return engine.generate(actor, input);
        } finally {
            permits.release();
        }
    }
}
~~~

Mã minh họa giả định **VerifiedActor, ExportRequest, ReportView** được định nghĩa ở domain. **tryAcquire()** từ chối tức thời khi hết chỗ, tránh xếp thêm request chờ không kiểm soát. **finally** giải phóng permit kể cả khi business method ném lỗi. Tham số **fair=true** cho semaphore điều tiết tương đối công bằng trong phạm vi process, không tạo fairness xuyên tenant hay cluster.

**Semaphore không bao gồm số lượng request đang QUEUED ở gateway, trong DB pool, ở downstream hoặc trên replica khác.** Nếu engine thực hiện một tác vụ dài sau khi trả HTTP 202, phải giữ trạng thái/permit theo **vòng đời job**, không giải phóng ngay sau khi tạo job. Dùng thread pool/queue có capacity rõ; không dựa vào việc tạo thêm virtual threads để xóa giới hạn tài nguyên thật.

### 8.2. Với WebFlux, giải phóng permit cả khi cancel

Không đặt **Semaphore.acquire()** hay **Thread.sleep()** trên Reactor event loop. Một cách minh họa sử dụng **tryAcquire()** không chặn:

~~~java
import reactor.core.publisher.Mono;
import java.util.concurrent.Semaphore;

class ReactiveBulkhead {
    private final Semaphore permits = new Semaphore(8);

    <T> Mono<T> guard(Mono<T> work) {
        return Mono.defer(() -> {
            if (!permits.tryAcquire()) {
                return Mono.error(new BulkheadFull());
            }
            return Mono.defer(() -> work)
                    .doFinally(signal -> permits.release());
        });
    }
}
~~~

Đoạn này giữ permit **trong vòng đời subscription**, gồm complete, error hoặc cancel. Tuy nhiên **cancel HTTP không bảo đảm server bên kia dừng thực hiện hoặc PSP chưa commit**; nếu bảo vệ tác vụ thật ở ngoài process, cần permit/job record được giải phóng khi công việc xác nhận kết thúc, thay vì xem client disconnect là hoàn tất. Với stream lâu sống như SSE, một subscription có thể giữ permit rất lâu: thiết kế quota connection, heartbeat, max session duration và cleanup riêng.

### 8.3. Giới hạn đồng thời trên toàn cluster

Trong DB, có thể duy trì counter active job và cập nhật khi **nhận job thật**:

~~~sql
UPDATE tenant_job_limits
   SET active_jobs = active_jobs + 1
 WHERE tenant_id = :tenant_id
   AND active_jobs < max_active_jobs;
-- affected_rows = 1: giữ được một slot.
~~~

Cùng transaction đó cần tạo **job/lease record** có operation ID duy nhất. Khi job chuyển **RUNNING/QUEUED → COMPLETED/FAILED/CANCELLED** hợp lệ, cập nhật state có điều kiện để **release slot đúng một lần**. Nếu worker crash, lease có **expiry/heartbeat** và reconciler phải xác minh công việc thực sự không còn chạy trước khi thu hồi; với worker cũ quay lại, dùng **fencing token/version** để không cho hai worker cùng ghi kết quả.

**Không đủ** để dùng Redis **INCR rồi DECR** đơn giản cho permit phân tán: worker chết hoặc mạng đứt có thể làm counter kẹt. Dùng distributed semaphore có lease/owner, fencing và cleanup được chứng minh, hoặc DB-backed active-job record khi tính đúng quan trọng. Nếu job đang chờ trong queue không tốn tài nguyên xử lý, có thể đặt limit riêng **queued** và **running**.

## 9. Spring REST: kết hợp actor limit với HTTP response

Một API đọc báo cáo phải được bảo vệ **Spring Security trước khi áp rate limit theo identity**. Code dưới đây nối các phần trước ở ranh giới HTTP, còn **JWT issuer/audience validator, verified actor resolver, repository và metrics** là các thành phần phải cấu hình thật.

~~~java
import java.util.List;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

record VerifiedActor(String tenantId, String userId, String opaqueLimitKey) {}
record ReportSummary(String id, String title) {}

interface VerifiedActorResolver {
    VerifiedActor fromValidatedJwt(Jwt jwt);
}

interface ReportService {
    List<ReportSummary> findVisible(VerifiedActor actor, int limit);
}

class TooManyRequests extends RuntimeException {
    final long retryAfterSeconds;
    TooManyRequests(long seconds) { this.retryAfterSeconds = seconds; }
}

@RestController
class ReportController {
    private final VerifiedActorResolver actors;
    private final RedisRequestLimiter limiter;
    private final ReportService reports;

    ReportController(VerifiedActorResolver actors,
            RedisRequestLimiter limiter, ReportService reports) {
        this.actors = actors;
        this.limiter = limiter;
        this.reports = reports;
    }

    @GetMapping("/v1/reports")
    ResponseEntity<List<ReportSummary>> list(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam(defaultValue = "20") int limit) {
        if (limit < 1 || limit > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid limit");
        }
        VerifiedActor actor = actors.fromValidatedJwt(jwt);
        RateDecision decision = limiter.check(actor.opaqueLimitKey());
        if (!decision.allowed()) {
            throw new TooManyRequests(decision.retryAfterSeconds());
        }
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(reports.findVisible(actor, limit));
    }
}
~~~

**opaqueLimitKey** phải được tính từ tenant + actor + operation **ở server**, không lấy query/header client. `findVisible` phải tiếp tục kiểm tra **ownership/tenant**; nếu quyền sai, 403/404 theo policy, không trả báo cáo của người khác chỉ vì limiter cho phép.

Thành phần xử lý lỗi:

~~~java
import java.net.URI;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class LimitProblemAdvice {
    @ExceptionHandler(TooManyRequests.class)
    ResponseEntity<ProblemDetail> tooFast(TooManyRequests ex) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.TOO_MANY_REQUESTS, "Try again later.");
        p.setType(URI.create(
                "https://api.example.test/problems/rate-limited"));
        p.setTitle("Too many requests");
        p.setProperty("code", "RATE_LIMITED");
        return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                .contentType(MediaType.valueOf("application/problem+json"))
                .header(HttpHeaders.RETRY_AFTER,
                        Long.toString(ex.retryAfterSeconds))
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(p);
    }

    @ExceptionHandler(LimiterUnavailable.class)
    ResponseEntity<ProblemDetail> unavailable(LimiterUnavailable ex) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Admission control is temporarily unavailable.");
        p.setProperty("code", "ADMISSION_UNAVAILABLE");
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(p);
    }
}
~~~

Trong ứng dụng thực, **SecurityFilterChain** yêu cầu JWT hợp lệ với **SCOPE_reports:read**, xác minh audience/issuer và bảo vệ các route khác. Mã trên không thể tự chạy nếu chưa có các bean/dependency; minh họa phạm vi trách nhiệm **controller – limiter – service – error advice**. Khi dùng **cookie session** thay bearer-only, phải bảo vệ CSRF cho các thao tác ghi; rate limit **không thay CSRF, authentication hay authorization**.

**429 không nên che lỗi Redis/DB.** Nếu limiter timeout, lỗi 503 cần logging/tracing và error budget riêng, không ghi actor là người dùng lạm dụng. Nếu response được cache, metadata rate limit chứa dữ liệu riêng cần xử lý theo cache policy; với dữ liệu user-specific, **Cache-Control: no-store** thường dễ an toàn hơn.

## 10. Retry, cancellation và giới hạn ở client

**Rate limiting là hợp đồng hai chiều**: server chủ động từ chối khi vượt capacity, còn client phải tôn trọng Retry-After và tự giới hạn nhịp gọi. Nếu hàng nghìn client đều retry đúng sau 60 giây, tải sẽ dồn vào một mốc; cần **jitter, exponential backoff, tổng số lần retry và deadline**. Đặc biệt nếu gateway, service và SDK đều tự retry, số attempt có thể bị nhân lên.

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 10
Content-Type: application/problem+json

{"type":"about:blank","title":"Service temporarily unavailable","status":503}
~~~

**Retry-After** trên 503 gợi ý thời gian phục hồi, không bảo đảm thành công. Client không nên retry **401, 403, 400**, và không tự retry operation không idempotent sau timeout chỉ dựa vào status. Với GET có thể retry có giới hạn, nhưng kết quả đã thay đổi giữa các lần thử vẫn là bình thường; với POST, cần operation ID và cơ chế đối soát kết quả sau khi response mất.

**Cancellation không phải rollback**: khi client ngắt kết nối, WebFlux có thể cancel publisher hoặc Servlet worker hoàn tất vòng đời request, nhưng job, truy vấn hoặc tác động payment bên ngoài có thể đã commit. Concurrency permit dành cho **HTTP in-flight** có thể được release khi kết nối ngắt, nhưng permit dành cho **job thực** chỉ release theo state machine của job. Chọn rõ tài nguyên mà mỗi permit đại diện.

### 10.1. Đo lường và cảnh báo vận hành

Theo dõi tối thiểu: **allowed/rejected request**, 429/503, quota remaining, active/queued jobs, permit utilization, wait time, Redis latency/error, DB pool, p95/p99, CPU/memory/GC, tỷ lệ retry, cancellation và cost units thực. Tách **actor-limited** với **global-overload** để biết đó là vấn đề chính sách hay capacity.

Đặt metric label theo **route template, policy name/version, status family và tenant nhóm đã pseudonymize**, không dùng raw URL chứa token, request ID duy nhất hoặc email. Đo **false positive** theo đối tác batch, người dùng có nhu cầu trợ năng và mạng NAT. Quy trình support cần có mã lý do an toàn, thời hạn policy và phương án kháng nghị; không tiết lộ khóa Redis hay detector nội bộ.

## 11. Kiểm thử đúng đơn vị giới hạn

| Test | Tầng phù hợp | Kết quả phải chứng minh |
|---|---|---|
| 10 request hợp lệ trong 60 giây, request 11 | Redis integration | 10 allowed; lần 11 denied và có Retry-After |
| 30 request đồng thời cùng key trên nhiều replica | Redis/real concurrency | Không vượt capacity đã cam kết trong cửa sổ kiểm thử |
| Burst sát hai cửa sổ | Clock-controlled test | Hiểu chính xác sai số của fixed window |
| Hai tenant dùng cùng route | Security + Redis integration | Key/quota tách biệt, tenant A không dùng quota của B |
| IP NAT dùng chung | End-to-end policy | Không tự chặn mọi user chỉ vì IP giống |
| Redis timeout/cluster failover | Fault injection | Chính sách fallback/503 được áp, không báo 429 giả |
| Global semaphore đã đủ permits | Service integration | Từ chối sớm; không có pending queue vô hạn |
| Tác vụ ném exception hoặc client cancel | Unit/reactive test | Permit release đúng một lần theo vòng đời đã chọn |
| Hai export tranh quota cuối | DB concurrency test | Không overdraw, operation record và quota commit atomically |
| Duplicate Idempotency-Key sau response mất | HTTP + DB | Không trừ quota/tạo job lần hai |
| Job worker crash rồi restart | Lease/fencing test | Cleanup không tạo hai worker cùng sở hữu slot |
| Gateway + downstream cùng retry | Load test | Tổng attempt nằm trong retry budget |

Ví dụ integration test cho Redis limiter (cần **Redis test instance hoặc Testcontainers**, JUnit 5 và Spring context riêng, không dùng Redis production):

~~~java
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class RedisRequestLimiterIT {
    @Autowired RedisRequestLimiter limiter;

    @Test
    void rejectsEleventhAttemptWithinWindow() {
        String isolatedKey = "test-" + UUID.randomUUID();
        for (int i = 0; i < 10; i++) {
            assertTrue(limiter.check(isolatedKey).allowed());
        }
        RateDecision rejected = limiter.check(isolatedKey);
        assertFalse(rejected.allowed());
        assertTrue(rejected.retryAfterSeconds() >= 1);
        assertTrue(rejected.retryAfterSeconds() <= 60);
    }
}
~~~

Test này chứng minh **một key** trong một Redis được giới hạn đúng số lần **tuần tự**; **chưa** chứng minh atomicity dưới race trên nhiều instance hoặc fairness giữa tenant. Dùng barrier để kích hoạt nhiều client đồng thời, đo số request allowed ở database/HTTP, chạy với connection pool tương tự production. Đối với quota, test nên assert **remaining không âm, không có hai reservation cùng operationId và count bảng job đúng**, không chỉ assert HTTP 429.

Với **MockMvc + spring-security-test**, kiểm tra request không token trả **401**, token thiếu scope trả **403**, tenant khác không lộ resource và actor vượt budget trả **429 + Retry-After + code**. Test mock JWT chỉ kiểm tra filter/route, **không** chứng minh validation signature/issuer/audience; bổ sung integration test identity thật hoặc JWKS test. Test cancellation cho WebFlux cần StepVerifier hoặc HTTP connection reset, tránh đồng nhất tín hiệu cancel với việc worker đã hoàn tác.

## 12. Bài tập thiết kế giới hạn cho API export

Một dịch vụ có **4 Spring replicas**, **Redis dùng chung** và PostgreSQL. Mỗi tenant được **20.000 cost units/ngày**, mỗi user được **30 lần thử export/phút**, tối đa **3 job RUNNING/tenant**, toàn hệ thống được tối đa **40 job RUNNING**; mỗi export có chi phí thực tế chỉ biết sau khi xử lý. Mobile client có thể retry POST sau timeout.

Hãy thiết kế:

1. **Admission pipeline** từ gateway, xác thực tenant, rate limit, quota reservation tới tạo job.
2. **Key/TTL và thuật toán Redis** cho 30 request/phút, nêu hành vi burst gần ranh giới cửa sổ.
3. **Bất biến SQL và transaction** để giữ quota không âm, slot active không vượt 3/40 khi nhiều replica tranh cùng lúc.
4. **Idempotency-Key và state machine** đảm bảo POST retry không tạo hai job hoặc trừ quota hai lần; cách trả **202 + Location**.
5. **HTTP contract** khi user vượt nhịp, quota hết, hệ thống hết công suất, Redis lỗi hoặc worker chết.
6. **Ma trận kiểm thử** gồm hai tenant, 50 request đồng thời, lỗi Redis, duplicate POST, cancellation và worker crash.

**Gợi ý:** rate limit đặt Redis, quota cost đặt **DB transaction + ledger**; per-tenant/global concurrency cần được tính trên **cùng hệ thống điều phối** hoặc thiết kế lease/fencing phù hợp. Giới hạn active job khác giới hạn request HTTP. Trả 429 khi actor quá nhanh, 503 khi quá tải/hệ thống kiểm soát tạm lỗi, quota hết dùng status nghiệp vụ được công bố. Retry cùng operation ID không tạo side effect mới.

## 13. Checklist và tài liệu tham khảo

- [ ] Phân biệt rate, usage quota, concurrency và cost, kèm đơn vị/chu kỳ rõ.
- [ ] Limit theo identity đáng tin, đúng tenant/operation; IP chỉ là tín hiệu bổ sung.
- [ ] Chọn fixed/sliding/token bucket theo burst và fairness, không dùng một thuật toán cho mọi route.
- [ ] Redis update atomically, có TTL, memory budget và chính sách lỗi/failover.
- [ ] Quota/active job quan trọng được bảo vệ ở DB bằng conditional update, unique key và transaction.
- [ ] Có bounded queue, deadline, backpressure và admission sớm.
- [ ] Không nhầm **429 rate**, **409/422 quota**, **503 overload**; Retry-After và Problem Details nhất quán.
- [ ] POST retry/idempotency, cancellation, lease cleanup và outbox được kiểm thử.
- [ ] Giám sát false positives, NAT, chi phí, p95/p99, Redis/DB pool và retry storm.

Tham khảo: **RFC 6585 (429 Too Many Requests)**, https://www.rfc-editor.org/rfc/rfc6585.html; **RFC 9110 HTTP Semantics**, https://www.rfc-editor.org/rfc/rfc9110.html; **RFC 9457 Problem Details**, https://www.rfc-editor.org/rfc/rfc9457.html; **Spring Security Reference**, https://docs.spring.io/spring-security/reference/; **Spring Data Redis scripting**, https://docs.spring.io/spring-data/redis/reference/redis/scripting.html; **Redis Lua scripts**, https://redis.io/docs/latest/develop/programmability/eval-intro/.

**Kết luận:** Rate limiting bảo vệ **tốc độ request**, quota bảo vệ **tổng quyền sử dụng/chi phí**, concurrency limit bảo vệ **số công việc đồng thời**. REST API có khả năng chống lỗi cần kết hợp cả ba với xác thực/phân quyền, ghi dữ liệu nguyên tử, retry/idempotency, backpressure và quan sát thực tế. **Không một limiter đứng riêng nào có thể thay việc bảo vệ bất biến nghiệp vụ tại nơi commit.**

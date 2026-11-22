# Token bucket, leaky bucket và cửa sổ đếm

## 1. Giới hạn tốc độ là chính sách tài nguyên, không chỉ là trả 429

Một API bán hàng có thể cho phép người dùng xem danh sách sản phẩm, gửi đơn và truy xuất báo cáo. Nếu một client gọi GET 2.000 lần/giây hoặc gửi nhiều POST tạo đơn cùng lúc, tài nguyên CPU, database, connection pool và downstream có thể bị chiếm hết. **Rate limiting** áp dụng ngân sách truy cập theo thời gian nhằm bảo vệ hệ thống, kiểm soát công bằng và giới hạn chi phí. Nó khác với:

- **Authentication**: xác thực danh tính ai đang gọi.
- **Authorization**: kiểm tra người đó có quyền trên resource hay không.
- **Quota**: tổng mức sử dụng trong một kỳ dài, ví dụ 1 triệu bản ghi/ngày.
- **Concurrency limit / bulkhead**: giới hạn số request *đang chạy đồng thời*.
- **Backpressure**: cơ chế điều phối tốc độ sản xuất và tiêu thụ dữ liệu.
- **Circuit breaker**: ngừng gọi tạm thời tới phụ thuộc liên tục lỗi.

Bài thuộc chương **Giới hạn và chống lỗi** của module **INTEGRATION_API_REST**. Người học vận dụng thiết kế REST theo resource, URI, method/status, hợp đồng JSON, xác thực/phân quyền, cache, idempotency và kiểm thử API Java/Spring để chọn **token bucket**, **leaky bucket** hoặc một **cửa sổ đếm** theo tải thực tế.

Sau bài, bạn có thể giải thích toán học của các thuật toán, dự đoán burst và ca biên cửa sổ, thiết kế khóa giới hạn theo principal/tenant/API, triển khai Java/Spring/Redis, trả HTTP 429 đúng nghĩa, tích hợp retry và kiểm thử tính nguyên tử khi nhiều instance cùng xử lý.

**Kịch bản xuyên suốt:** API Orders cho mỗi người dùng tối đa **10 request ngay lập tức**, rồi được cấp lại **2 request/giây**; riêng một tenant có quota tổng và endpoint thanh toán phải chống retry gây tạo giao dịch trùng. Các con số chỉ để học, không phải mức áp dụng mặc định cho production.

## 2. Xác định trước: giới hạn ai, thao tác gì, trong khoảng nào?

Một chính sách rate limit có ít nhất năm yếu tố:

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Identity/key** | Ai chia sẻ ngân sách? | Tenant + principal đã xác thực |
| **Resource group** | Những endpoint nào dùng chung ngân sách? | orders-read, orders-write, exports |
| **Capacity** | Cho phép burst tối đa bao nhiêu? | 10 token |
| **Refill/window** | Ngân sách hồi lại theo thời gian nào? | 2 token/giây |
| **Cost** | Một request dùng bao nhiêu đơn vị? | GET = 1, export = 5 |

Cần thêm giới hạn **global** để bảo vệ cả hệ thống, **per-tenant** để tenant lớn không chiếm tài nguyên của tenant nhỏ, và **per-principal** để một tài khoản không chiếm toàn bộ quota của tenant. Thường request phải qua **mọi tầng giới hạn**; chỉ cần một tầng hết ngân sách là từ chối.

Không lấy khóa giới hạn từ **X-User-Id, tenantId trong JSON hoặc một header client tự đặt**. Ở vùng API đã xác thực, dùng identity đáng tin của Spring Security và tenant được xác minh. Ở vùng chưa xác thực (login/token), có thể kết hợp IP/ASN, device signals, client ID và global guard, nhưng **IP không tương đương một người**: NAT, proxy, mạng di động và IPv6 làm nhiều người dùng chia sẻ hoặc đổi địa chỉ.

Một bản policy mẫu:

~~~yaml
rateLimitPolicy:
  ordersRead:
    principal:
      burst: 10
      refillPerSecond: 2
    tenant:
      burst: 200
      refillPerSecond: 40
  ordersWrite:
    principal:
      burst: 4
      refillPerSecond: 0.2
    globalConcurrency: 100
  reportExport:
    tenant:
      burst: 5
      refillPerSecond: 0.02
~~~

Đây là YAML minh họa cho **policy ứng dụng**, không phải property Spring Boot tự hiểu. Muốn sử dụng phải xây adapter và validation cho policy. Rate limit có thể **weighted**, ví dụ một report export nặng tiêu 5 token, nhưng cách cân trọng số phải được công bố và đo bằng chi phí thực.

## 3. Token bucket: cho phép burst, kiểm soát tốc độ trung bình

Hãy hình dung một xô chứa token, dung tích tối đa **B**, được bơm thêm với tốc độ **r token/giây**. Mỗi request có cost **c** token. Khi request đến:

1. Cập nhật số token tích lũy từ lần trước, không vượt B.
2. Nếu số token hiện tại ít nhất c, trừ c và **cho qua**.
3. Nếu không đủ, **từ chối hoặc chờ theo policy**; không tự cho vượt ngân sách.
4. Với số token thiếu, có thể ước lượng thời gian chờ tới lần đủ token.

Đặt **T(t)** là số token ngay trước một request tại thời điểm t, **t₀** là mốc cập nhật gần nhất:

~~~text
T_before = min(B, T_previous + max(0, t - t0) * r)
allowed  = (T_before >= c)
T_after  = allowed ? T_before - c : T_before
retryAfter = allowed ? 0 : (c - T_before) / r   [giây]
~~~

Chỉ tính **retryAfter** khi **r > 0** và **0 < c ≤ B**. Nếu cost lớn hơn capacity thì *chờ bao lâu cũng không bao giờ đủ*, phải từ chối bằng chính sách khác (validation/quota configuration), không trả Retry-After vô hạn.

### Ví dụ cụ thể: B = 10, r = 2/s, c = 1

<escape>Thời điểm t = 0:</escape> xô đầy 10 token. Nếu 10 request tới cùng lúc, có thể cho qua cả 10 (giả sử xử lý nguyên tử), số token còn 0. Request thứ 11 nhận từ chối. Sau **0,25 giây**, có 0,5 token nên chưa đủ một request; sau **0,5 giây**, có 1 token và có thể cho một request. Sau **5 giây không có request**, xô lại đầy 10 token.

| Thời điểm | Token trước khi xử lý | Cost | Kết quả |
| --- | ---: | ---: | --- |
| t = 0, request thứ 1 | 10 | 1 | Cho qua, còn 9 |
| t = 0, request thứ 10 | 1 | 1 | Cho qua, còn 0 |
| t = 0, request thứ 11 | 0 | 1 | 429; ước lượng chờ 0,5 s |
| t = 0,25 s | 0,5 | 1 | 429; còn khoảng 0,25 s |
| t = 0,5 s | 1 | 1 | Cho qua, còn 0 |
| t = 5,5 s không có request khác | 10 | 1 | Cho qua, còn 9 |

Sự khác biệt cốt lõi: **B quyết định burst tối đa**, còn **r quyết định tốc độ trung bình dài hạn**. Nếu một client liên tục gửi nhanh hơn r, phần dư bị 429; nếu nghỉ, ngân sách được tích lại nhưng không vượt B. Token bucket **không bảo đảm** khoảng cách tối thiểu giữa hai request đã cho qua; 10 request cùng lúc vẫn có thể vào server.

### Trường hợp cần chú ý

- **Giờ hệ thống bị chỉnh lùi** có thể tạo token sai nếu dùng wall clock trực tiếp. Với một tiến trình Java, dùng **System.nanoTime()** (monotonic elapsed time) để đo khoảng cách; không dùng nó làm timestamp audit.
- Với cost phân số hoặc refill tốc độ nhỏ, tránh **integer truncation** làm token không bao giờ hồi. Có thể lưu fixed-point integer hoặc double kèm kiểm soát precision/epsilon.
- Với request cực nặng, cost cần phản ánh **estimated cost trước khi cấp quyền** và có cơ chế tính phí thực tế nếu phù hợp; không để client tự khai cost thấp.
- Nếu trừ token trước khi gọi downstream rồi request lỗi, **có trả lại token không** phải quyết định policy. Tự động hoàn mọi 5xx có thể khuyến khích lặp request gây quá tải; thường tính theo lượt yêu cầu đã nhận hoặc chi phí thực tế, không theo success.

## 4. Leaky bucket: làm phẳng tốc độ thay vì chỉ chặn burst

Thuật ngữ **leaky bucket** có hai cách dùng trong tài liệu: **traffic shaper có hàng đợi và tốc độ thoát cố định**, hoặc **meter dùng mức nước rò dần để quyết định accept/reject**. Meter có cách biểu diễn toán học tương đương một dạng token bucket; vì vậy khi so sánh cần nói rõ **biến thể**. Trong bài này, *leaky bucket* là **hàng đợi có dung lượng Q và tốc độ phục vụ μ tác vụ/giây**.

~~~mermaid
flowchart LR
    A[Request burst] --> B{Queue còn chỗ?}
    B -->|Có| C[Bounded queue]
    B -->|Không| D[429 / Reject]
    C --> E[Worker lấy đều theo tốc độ mu]
    E --> F[Downstream]
~~~

Nếu μ = 2 request/giây, Q = 5 tác vụ chờ, 5 request đồng thời có thể xếp hàng. Một worker phát ra xấp xỉ **một tác vụ mỗi 0,5 giây**. Request thứ 6 có thể bị từ chối nếu hàng đợi đã đầy; thời gian chờ của request ở cuối hàng có thể khoảng **2,5 giây**, chưa tính thời gian xử lý downstream. Công thức đơn giản:

~~~text
pending <= Q
departure interval ≈ 1 / μ
worstQueuedWait ≈ Q / μ
~~~

Thực tế phải tính **job đang chạy**, số worker, deadline của từng client, cancellation và jitter. Với HTTP đồng bộ cần trả nhanh, **giữ kết nối chờ queue nhiều giây** có thể gây cạn thread/socket. Nếu công việc đủ dài để xếp hàng, cân nhắc **202 Accepted + operation resource** và chỉ cho 202 khi job đã được ghi bền vững; không trả 202 rồi làm mất job trong hàng đợi RAM.

| Đặc tính | Token bucket | Leaky bucket dạng queue shaper |
| --- | --- | --- |
| Cho burst vào downstream ngay? | Có, tối đa B nếu đầy | Không, làm phẳng tại tốc độ μ |
| Độ trễ khi quá tải | 429 hoặc chờ theo policy | Queue delay tăng theo số tác vụ |
| Bộ nhớ | Trạng thái nhỏ theo key | Tăng theo queue depth và payload |
| Rủi ro | Burst ngắn có thể vẫn làm downstream nghẽn | Queue đầy, job hết hạn, worker chết |
| Hợp | API online có burst hợp lệ | Batch, API async, webhook/notification dispatch |

**Leaky bucket không tự giải quyết công bằng giữa nhiều tenant.** Một queue FIFO toàn cục có thể bị tenant lớn chiếm hết. Dùng queue per tenant, weighted fair queue hoặc quota admission theo tenant nếu muốn công bằng thực sự.

## 5. Fixed window counter: dễ hiểu nhưng có hiệu ứng ranh giới

Với **fixed window** dài W, giới hạn L request/window, hệ thống tính số request trong mỗi cửa sổ căn theo một mốc chung:

~~~text
windowId = floor(timestamp / W)
key = tenant + principal + routeGroup + windowId
count[key] += 1
allow iff count[key] <= L
~~~

Ví dụ **L = 100 request/phút**. Từ **12:00:59.900 đến 12:00:59.999**, client gửi 100 request; ngay sau **12:01:00.000**, client có thể gửi tiếp 100 request trong cửa sổ mới. Như vậy **200 request có thể nằm trong khoảng thời gian di động rất ngắn** dù từng cửa sổ đồng hồ không vượt 100.

Ưu điểm: một counter/key và TTL dễ triển khai, tính toán O(1). Nhược điểm: burst ở ranh giới, không mô hình hóa chi phí theo thời gian liên tục, phụ thuộc mốc đồng bộ và fairness.

Với Redis, **INCR + EXPIRE phải phối hợp nguyên tử hoặc bằng thiết kế an toàn**. Nếu INCR thành công nhưng tiến trình chết trước EXPIRE, key có thể không bao giờ hết hạn, gây memory leak hoặc chặn mãi. Dùng Lua script/transaction phù hợp thay vì hai lệnh rời không có xử lý lỗi.

### Sliding window log: chính xác hơn, tốn bộ nhớ hơn

Thay vì chia mốc cố định, lưu timestamp từng request **được chấp nhận** trong khoảng (now − W, now]. Khi request đến, loại timestamp quá cũ, đếm số còn lại, chỉ accept nếu nhỏ hơn L rồi thêm timestamp mới.

~~~text
remove timestamps <= now - W
allow = (currentWindowCount < L)
if allow: append timestamp(now)
~~~

Điểm mạnh: tránh gấp đôi ở ranh giới cửa sổ; có thể trả thời điểm slot sớm nhất được giải phóng. Chi phí: **O(số request trong window)** bộ nhớ mỗi key, cần thao tác nguyên tử, quản lý timestamp trùng và dọn dẹp khi traffic cao. Với Redis sorted set, timestamp cần đi kèm **member ID duy nhất**; nếu dùng timestamp làm member duy nhất, nhiều request cùng millisecond sẽ ghi đè nhau và đếm thiếu.

### Sliding window counter: ước lượng thay vì lưu mọi timestamp

Một phương án nhẹ hơn dùng counter của cửa sổ hiện tại C và cửa sổ trước P. Với cửa sổ W đã trôi qua e giây:

~~~text
estimatedCount = C + P * (1 - e / W)
allow if estimatedCount + cost <= L
~~~

Ví dụ W = 60 giây; 15 giây đã trôi qua, P = 80, C = 30. Phần còn lại ước lượng của cửa sổ trước là **80 × 0,75 = 60**, nên estimatedCount = **90**. Với L = 100, có thể nhận tiếp khoảng 10 request cost 1 theo ước lượng.

Thuật toán **giả định** request trong cửa sổ trước được phân bố tương đối đều. Nếu traffic dồn vào cuối hoặc đầu cửa sổ, số thực trong 60 giây gần nhất có thể khác nhiều; kết quả là **xấp xỉ**, không dùng để cam kết một ngưỡng pháp lý/tài chính chính xác tuyệt đối. Cần xác định rõ phép làm tròn, atomic counters và hành vi khi không có key của cửa sổ trước.

## 6. So sánh bằng tiêu chí vận hành

Không có thuật toán “tốt nhất” cho mọi API. Hãy chọn theo **burst, độ chính xác, chi phí trạng thái, độ trễ và yêu cầu phân tán**.

| Tiêu chí | Token bucket | Leaky queue | Fixed window | Sliding log | Sliding counter |
| --- | --- | --- | --- | --- | --- |
| Cho burst ngắn | **Có**, tối đa B | Xếp hàng, không phát burst | Có, đặc biệt tại ranh giới | Giới hạn chính xác theo W | Giảm burst ranh giới, xấp xỉ |
| Mức trung bình dài hạn | Khoảng r | Tốc độ drain μ | Tối đa L mỗi window cố định | Tối đa L trong mọi W di động | Gần L/W |
| Chi phí theo key | O(1) | O(Q) cho queue | O(1) counter/window | O(số event giữ lại) | O(1), thường 2 counter |
| Độ chính xác thời gian | Phụ thuộc độ phân giải refill | Phụ thuộc scheduler/worker | Không chính xác tại ranh giới | Cao, nếu nguyên tử | Xấp xỉ |
| Hành vi khi quá tải | Từ chối/chờ | Chờ có giới hạn hoặc từ chối | Từ chối | Từ chối | Từ chối |
| Phù hợp | REST API request/response | Async worker, webhook dispatch | Quota đơn giản, reporting | Ngưỡng nghiêm cho ít key | Quota công bằng tương đối |

### Ví dụ quyết định cho hệ thống thương mại

- **GET /products** cần cho phép client burst từ màn hình load lại rồi ổn định: **token bucket per principal + global guard**.
- **POST /payment-intents** có tác dụng phụ: token bucket admission, **Idempotency-Key**, authorization và **business invariant** chống duplicate. Rate limit không thay idempotency.
- **POST /exports** tạo job lớn: quota tenant cho số lần tạo + **bounded queue**/concurrency cho worker; 202 chỉ sau khi job bền vững.
- **Login/token endpoint** chưa có principal: nhiều chiều IP + account-identifier đã được normalize/anonymize + global circuit; chống brute force không chỉ bằng một limit IP.
- **Báo cáo quota tháng** cần tính tổng chính xác: durable metering/accounting, không dùng token bucket ngắn hạn để thay hóa đơn.

**Đặt rate limit ở gateway hay service?** Gateway hữu ích để chặn tải sớm và áp chính sách chung; service hiểu business cost, tenant/permission và concurrency nội bộ. Có thể dùng **hai tầng**, nhưng phải công bố rõ ngân sách của từng tầng, tránh trả hai loại 429 mâu thuẫn hoặc giới hạn sai người dùng.

## 7. Java: token bucket nguyên tử trong một tiến trình

Đầu tiên có thể kiểm thử thuật toán mà không phụ thuộc Redis. Dùng **thời gian monotonic**, lưu trạng thái và khóa đồng bộ cho **cùng một bucket**; tách đồng hồ khỏi code để test không phải sleep.

~~~java
public record LimitDecision(
        boolean allowed, long retryAfterMillis, double remaining) {}

public final class LocalTokenBucket {
    private final double capacity;
    private final double refillPerSecond;
    private double tokens;
    private long updatedNanos;

    public LocalTokenBucket(
            double capacity, double refillPerSecond,
            long initialNanos) {
        if (!(capacity > 0) || !(refillPerSecond > 0)) {
            throw new IllegalArgumentException("Invalid policy");
        }
        this.capacity = capacity;
        this.refillPerSecond = refillPerSecond;
        this.tokens = capacity;
        this.updatedNanos = initialNanos;
    }

    public synchronized LimitDecision tryConsume(
            double cost, long nowNanos) {

        if (!(cost > 0) || cost > capacity) {
            throw new IllegalArgumentException("Invalid request cost");
        }

        if (nowNanos > updatedNanos) {
            double elapsedSeconds =
                (nowNanos - updatedNanos) / 1_000_000_000.0;
            tokens = Math.min(
                capacity, tokens + elapsedSeconds * refillPerSecond);
            updatedNanos = nowNanos;
        }

        if (tokens >= cost) {
            tokens -= cost;
            return new LimitDecision(true, 0L, tokens);
        }

        long retryAfterMillis = Math.max(1L,
            (long) Math.ceil(
                (cost - tokens) / refillPerSecond * 1000.0));

        return new LimitDecision(
            false, retryAfterMillis, tokens);
    }
}
~~~

Sử dụng:

~~~java
LocalTokenBucket bucket = new LocalTokenBucket(
    10.0, 2.0, System.nanoTime());

LimitDecision decision =
    bucket.tryConsume(1.0, System.nanoTime());
~~~

Đây là **core algorithm**, không phải đầy đủ production limiter: nó chỉ bảo đảm thread safety **trong một JVM**. Với hai server instance A và B, mỗi instance tạo bucket đầy riêng thì tổng burst có thể thành **2 × B**. Một local ConcurrentHashMap theo tenant/user cũng cần **max size, idle eviction, policy versioning và bảo vệ cardinality**, nếu không attacker có thể làm đầy RAM bằng danh tính giả.

Mẫu này dùng double để minh họa fractional tokens. Với hạn mức chính xác trên lượng lớn request, cân nhắc **fixed-point integer** (ví dụ milli-token) và kiểm tra rounding/overflow. **System.nanoTime() chỉ đo elapsed time nội bộ**; không lưu làm timestamp để đối chiếu giữa máy hoặc sau restart.

Nếu một request bị từ chối, code **không trừ token**. Một số API muốn tính cả failed attempts để chống abuse, khi đó đặt một limiter riêng cho attempt/security event; đừng làm lẫn semantics “request được nhận để xử lý” với “mọi lần thử”.

## 8. Redis: admission phải là phép cập nhật nguyên tử

Trong hệ thống nhiều instance, Redis có thể là nơi giữ trạng thái rate limit chung. Anti-pattern:

~~~text
GET bucket
tính toán ở Java
SET bucket
~~~

Hai instance có thể cùng đọc **10 token**, mỗi instance cho 10 request rồi cùng ghi trạng thái còn 0. Hệ thống đã nhận **20 request** dù capacity chỉ 10. Dùng **Redis Lua script** hoặc cơ chế atomic tương ứng để **đọc trạng thái, tính refill, kiểm tra cost, trừ token và đặt TTL trong một thao tác**.

Ví dụ Lua cho **một bucket một Redis key**. Đầu vào: KEYS[1] là key tin cậy, ARGV[1] capacity, ARGV[2] refill token/giây, ARGV[3] cost:

~~~lua
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])

if not capacity or capacity <= 0 or
   not rate or rate <= 0 or
   not cost or cost <= 0 or cost > capacity then
    return redis.error_reply("invalid rate-limit policy")
end

local clock = redis.call("TIME")
local nowMs = tonumber(clock[1]) * 1000 +
              math.floor(tonumber(clock[2]) / 1000)

local state = redis.call(
    "HMGET", KEYS[1], "tokens", "updatedMs")

local tokens = tonumber(state[1]) or capacity
local previousMs = tonumber(state[2]) or nowMs
local elapsedMs = math.max(0, nowMs - previousMs)
tokens = math.min(
    capacity, tokens + elapsedMs * rate / 1000)

local allowed = 0
local retryMs = 0
if tokens >= cost then
    tokens = tokens - cost
    allowed = 1
else
    retryMs = math.ceil((cost - tokens) / rate * 1000)
end

redis.call(
    "HSET", KEYS[1],
    "tokens", tokens, "updatedMs", nowMs)

local ttlMs = math.max(
    1000, math.ceil(2 * capacity / rate * 1000))
redis.call("PEXPIRE", KEYS[1], ttlMs)

return {allowed, math.floor(tokens * 1000), retryMs}
~~~

Ý nghĩa kết quả: **allowed** là 0/1, **remaining milli-token** là số nguyên làm tròn xuống, **retryMs** là ước lượng thời gian cần để cost có thể được cấp nếu không có request khác. Đây là **một reference implementation**: cần kiểm chứng hiệu năng Redis/Lua, giới hạn TTL/capacity, phiên bản Redis, thao tác TIME trong script và cơ chế replication/cluster trong môi trường thực.

**Vì sao đặt TTL đủ lâu?** Nếu key hết hạn trước khi token có thể tự hồi đầy, bucket sẽ bất ngờ reset về capacity và cấp quá nhiều. TTL ở đây xấp xỉ **hai lần thời gian làm đầy**, nên key không có traffic được dọn sau khi đáng lẽ bucket đã đầy. Cần giới hạn giá trị cấu hình để không tạo TTL quá lớn hoặc overflow.

**Thời gian:** Redis TIME lấy mốc từ server giữ state; giảm khác biệt đồng hồ giữa API nodes. Nhưng Redis failover giữa các máy có clock lệch vẫn có thể làm biến dạng refill. Code chặn elapsed âm; production cần NTP, test clock jumps và quan sát failover. Nếu Redis version/replication mode không hỗ trợ TIME theo cách này, dùng **timestamp từ nguồn tin cậy đồng bộ** theo chiến lược đã test, không lấy giờ từ một header client gửi.

**Cluster và nhiều tầng:** mỗi Lua script nguyên tử trong phạm vi shard/key được truy cập. Nếu muốn trừ **global + tenant + principal** cùng lúc, các key trên Redis Cluster phải cùng hash slot cho một Lua script; nếu khác shard, không có transaction đa key nguyên tử mặc định. Không kiểm tra ba bucket bằng ba lời gọi rồi trừ bucket thứ nhất trước khi biết hai bucket còn lại: request bị chặn ở tầng sau vẫn mất quota tầng trước, làm mất công bằng. Có thể dùng Lua multi-key cùng slot, hai tầng admission có tính đến chi phí không hoàn lại, hoặc thiết kế giới hạn phân cấp với đánh đổi minh bạch.

### Lỗi Redis và yêu cầu an toàn

Khi Redis không khả dụng phải có **failure policy theo endpoint**:

- Hệ thống nội bộ nhạy cảm và endpoint cần hạn chế brute force/cost: ưu tiên **fail closed** hoặc limiter dự phòng nghiêm hơn, không tự mở unlimited.
- Một GET công khai có thể dùng **fail open giới hạn** kèm local emergency limiter để bảo toàn availability, nhưng phải có global concurrency guard và cảnh báo.
- Không khẳng định mọi hệ thống phải fail open hay fail closed. Xác định từ threat model, SLA, tenant isolation và mức chấp nhận mất doanh thu/dịch vụ.
- Dùng circuit breaker/timeout khi gọi Redis; không để mỗi HTTP request đợi Redis vô hạn. Khi fallback sang local limiter, tổng hạn mức **không còn chính xác toàn cluster**; ghi nhận trạng thái degraded.

Không dùng raw access token hoặc email làm Redis key/log. Xây khóa từ ID principal/tenant đã xác minh và route group chuẩn hóa; với danh tính nhạy cảm, có thể dùng HMAC/pseudonymization có quản lý khóa. Không lấy **raw URL** làm key vì ID/path/query cardinality lớn và tạo vô hạn buckets.

## 9. Tích hợp Spring MVC sau authentication, trước nghiệp vụ

Rate limiting có thể nằm ở **API gateway**, filter hoặc Spring MVC interceptor. Với endpoint đã được Spring Security bảo vệ, **HandlerInterceptor** có thể đọc principal đã xác thực để lấy ngân sách theo tenant/user. Đây là ví dụ theo **Servlet Spring MVC**, không phải SecurityWebFilterChain của WebFlux.

Tách giao diện admission khỏi implementation để đổi local bucket thành Redis mà không thay controller:

~~~java
public interface AdmissionPolicy {
    LimitDecision acquire(
        String routeGroup, String tenantId,
        String principalId, double cost);
}

public interface TrustedTenantResolver {
    String requireTenant(Authentication authentication);
}
~~~

**TrustedTenantResolver** chỉ dùng claim đã được resource server xác minh hoặc tenant được kiểm tra với database. Không đọc raw tenantId từ request header/body để tạo khóa giới hạn.

Một interceptor minh họa cho Orders API:

~~~java
@Component
public final class OrdersLimitInterceptor
        implements HandlerInterceptor {

    private final AdmissionPolicy admission;
    private final TrustedTenantResolver tenants;

    public OrdersLimitInterceptor(
            AdmissionPolicy admission,
            TrustedTenantResolver tenants) {
        this.admission = admission;
        this.tenants = tenants;
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws IOException {

        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            throw new AuthenticationCredentialsNotFoundException(
                "Authentication required");
        }

        String tenant = tenants.requireTenant(auth);
        String principal = auth.getName();
        String group = request.getMethod().equals("POST")
            ? "orders-write" : "orders-read";

        LimitDecision result =
            admission.acquire(group, tenant, principal, 1.0);

        if (result.allowed()) {
            return true;
        }

        long seconds = Math.max(
            1L, (result.retryAfterMillis() + 999L) / 1000L);

        response.setStatus(429);
        response.setContentType("application/problem+json");
        response.setCharacterEncoding("UTF-8");
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Retry-After", Long.toString(seconds));
        response.getWriter().write("""
            {"type":"https://api.example.com/problems/rate-limit",
             "title":"Too Many Requests",
             "status":429,
             "code":"RATE_LIMIT_EXCEEDED"}
            """);
        return false;
    }
}
~~~

Đăng ký interceptor với đường dẫn đã được security policy bảo vệ:

~~~java
@Configuration
public class RateLimitMvcConfiguration
        implements WebMvcConfigurer {

    private final OrdersLimitInterceptor ordersLimit;

    public RateLimitMvcConfiguration(
            OrdersLimitInterceptor ordersLimit) {
        this.ordersLimit = ordersLimit;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(ordersLimit)
            .addPathPatterns(
                "/api/v1/orders",
                "/api/v1/orders/**");
    }
}
~~~

**Lưu ý triển khai:**

1. **SecurityFilterChain phải yêu cầu authentication** cho các endpoint được giới hạn theo principal. Interceptor có check dự phòng nhưng không thay filter bảo vệ.
2. **CORS preflight** phải được Spring Security/CORS xử lý đúng trước khi tới logic này; không tự đòi Bearer token ở OPTIONS preflight. Nếu interceptor thực sự nhận OPTIONS, cần chính sách không tính phí hoặc handler CORS phù hợp.
3. Ví dụ gán POST vào **orders-write**, method khác vào **orders-read** chỉ để minh họa. Production phải có **bảng route group/method rõ ràng**; tránh coi DELETE là read hoặc dùng raw path có ID làm khóa.
4. Interceptor chạy trước controller, nhưng object-level authorization tại service có thể chưa diễn ra. Vì thế một request cuối cùng nhận 403 vẫn có thể bị tính quota; quyết định có tính **attempted requests** phải được ghi trong policy.
5. Khi lỗi Redis, **AdmissionPolicy** áp failure policy đã định nghĩa; không nuốt exception rồi cấp unlimited. JSON body minh họa cố định để không phản chiếu tên user/tenant.
6. Đảm bảo policy không trả retryAfterMillis âm/overflow. Đoạn làm tròn giây là một mẫu đơn giản cho các hạn mức ngắn; với giá trị rất lớn cần tính làm tròn an toàn.

Với **Spring WebFlux**, dùng **WebFilter** và ReactiveSecurityContextHolder, không copy trực tiếp HandlerInterceptor hoặc gọi blocking Redis/JDBC trên event loop. Với gateway, áp cùng nguyên tắc identity/trust và trả 429 trước khi request tới service.

## 10. HTTP 429, Retry-After và tính minh bạch hợp đồng

Khi server **từ chối vì vượt rate limit**, status phổ biến là **429 Too Many Requests**. Nó khác **503 Service Unavailable** (phụ thuộc/hạ tầng tạm không sẵn sàng) và **403 Forbidden** (không có quyền). Không dùng rate limiting thay authorization: token sai vẫn cần **401**, thiếu scope có thể **403**; thứ tự kiểm tra ở gateway/security ảnh hưởng status nào trả trước nên cần test.

Ví dụ:

~~~http
GET /api/v1/orders HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 2
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/rate-limit",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Đã vượt giới hạn truy cập tạm thời.",
  "code": "RATE_LIMIT_EXCEEDED"
}
~~~

**Retry-After** có thể là **số giây không âm** hoặc **HTTP-date**. Server có thể làm tròn lên (ví dụ cần 0,2 giây nhưng trả 1) để client không retry quá sớm. Header này là **ước lượng**, không phải bảo đảm request sẽ thành công: nhiều client dùng chung bucket, chính sách có thể thay đổi hoặc tầng global vẫn đang hết ngân sách.

Client nên:

- Đọc status 429, Retry-After và mã lỗi ổn định, **không parse theo detail tiếng Việt**.
- Đợi có **backoff/jitter** và **tổng deadline**, không vô hạn; tránh đồng loạt retry khi nhiều client cùng hết hạn.
- Không mở nhiều connection chờ lâu nếu request đã bị từ chối; với UI, hiển thị thông báo và khóa thao tác tạm thời hợp lý.
- Không dùng một key idempotency mới cho mỗi retry của POST có tác dụng phụ.
- Không hiểu remaining token ước lượng là hợp đồng quyền truy cập cố định.

API có thể công bố các trường **RateLimit** hoặc **X-RateLimit** theo chuẩn/header contract mà hệ thống hỗ trợ; **không trộn định dạng giữa gateway và service** hay xem mọi tên header ngoài Retry-After là phổ quát. Nếu hiển thị remaining, phải tính theo **chính sách thực sự khiến request bị chặn**, chú ý nhiều tầng và thông tin của tenant. Không đưa identity/secret vào header response.

### OpenAPI 3.1: mô tả response bị giới hạn

~~~yaml
openapi: 3.1.0
info: { title: Orders API, version: 1.0.0 }
paths:
  /api/v1/orders:
    get:
      summary: Truy vấn đơn hàng
      security:
        - bearerAuth: []
      responses:
        '200': { description: Thành công theo schema đơn hàng }
        '401':
          description: Cần access token hợp lệ
          headers:
            WWW-Authenticate:
              schema: { type: string }
        '429':
          description: Quá giới hạn truy cập, có thể thử lại sau
          headers:
            Retry-After:
              required: true
              description: Số giây chờ hoặc HTTP-date
              schema: { type: string }
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/RateLimitProblem'
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer }
  schemas:
    RateLimitProblem:
      type: object
      required: [type, title, status, code]
      properties:
        type: { type: string, format: uri-reference }
        title: { type: string }
        status: { type: integer, const: 429 }
        detail: { type: string }
        code: { type: string, const: RATE_LIMIT_EXCEEDED }
~~~

Hợp đồng này giả định **mọi 429 do Orders API phát ra đều có Retry-After**. Nếu một tầng gateway không cam kết header đó, sửa OpenAPI/contract tests tương ứng. Schema chỉ mô tả response; Spring/gateway vẫn phải thực thi limiter và security thực tế.

### REST status khác cũng cần bảo toàn

| Tình huống | Status gợi ý | Lưu ý |
| --- | --- | --- |
| Dư ngân sách, GET thành công | 200 | Quota không làm thay đổi representation |
| Job export được ghi bền vững | 202 | Giới hạn queue/concurrency; GET operation status riêng |
| Client thiếu xác thực | 401 | WWW-Authenticate theo bearer scheme |
| Client không có quyền | 403 hoặc 404 có chủ đích | Không lộ resource tenant khác |
| Vượt tốc độ truy cập | **429** | Retry-After theo thời gian chờ ước lượng |
| Downstream/ngõ vào quá tải | **503** khi đúng bản chất | Có thể có Retry-After; dùng circuit/bulkhead |
| Request sai JSON/validation | 400/422 theo contract | Không báo 429 chỉ vì body sai |

Nếu request qua **nhiều lớp** gateway, load balancer, service, cần thống nhất mã lỗi và header; một lớp có thể chặn trước authentication để bảo vệ login hoặc mạng, nhưng không được suy rằng một 429 chứng minh danh tính đã được xác thực.

## 11. Kết hợp rate limit với khả năng chống lỗi

**Rate limiter trả lời “có cho request này bắt đầu không?”**; nó không trả lời “có bao nhiêu request đang chạy?” hay “downstream có khỏe không?”. Một API an toàn thường kết hợp:

~~~mermaid
flowchart LR
    A[HTTP request] --> B[Authn + route policy]
    B --> C[Rate limit per tenant/user]
    C -->|Cho qua| D[Concurrency bulkhead]
    C -->|Hết quota| E[429]
    D -->|Có slot| F[Business handler]
    D -->|Đầy| G[429 hoặc 503 theo policy]
    F --> H[Timeout / circuit breaker downstream]
~~~

- **Rate limit** giới hạn tốc độ vào hệ thống, thường theo identity/tenant/route group.
- **Concurrency limit** giới hạn số thao tác đang thực hiện, hữu ích cho endpoint phản hồi rất chậm. Một rate 10 request/giây mà mỗi request giữ DB connection 30 giây vẫn có thể tạo **300 request đang chạy**.
- **Timeout/deadline** tránh chiếm tài nguyên vô hạn.
- **Circuit breaker** tạm chặn downstream đang lỗi để tránh khuếch đại sự cố.
- **Queue có giới hạn** chỉ thích hợp nếu client chấp nhận độ trễ hoặc mô hình async được định nghĩa.

Cần tách **quota theo tải** và **retry traffic**. Nếu client tự động retry cả 429 lẫn 503 qua nhiều tầng, 100 request có thể biến thành hàng trăm attempt mới. Retry policy nên giới hạn **số lần, thời gian, jitter, Idempotency-Key** và cân nhắc client đã tiêu bao nhiêu token.

**Rate limit không thay thế idempotency.** Hai POST cùng nội dung có thể đều được phép bởi token bucket nhưng vẫn tạo hai đơn. Dùng unique business key/Idempotency-Key và transaction cho dữ liệu, dùng rate limiter để bảo vệ tải. Ngược lại, một request idempotent có thể vẫn bị 429 nếu quá tải; server cần chính sách có tính đến replay của kết quả đã lưu để tránh buộc client chờ vô ích hoặc chiếm quota quá mức.

### Tương tác với caching

GET có cache hit tại CDN/gateway thường không đi đến service. Do đó limit tính tại service đo **origin requests**, không phải mọi hành vi người dùng. Nếu policy nhằm giới hạn tổng traffic hoặc abuse công khai, cần guard ở edge trước cache hoặc cấu trúc nhiều tầng. Không lấy cache key có user-specific response rồi chia sẻ sai giữa tenant; cache và limiter đều phải xét authentication và Vary/security policy tương ứng.

## 12. Bảo mật và công bằng giữa các tenant

Một thuật toán đúng công thức nhưng sử dụng **identity key không đáng tin** có thể gây bypass hoặc denial-of-service lên người khác.

| Ngữ cảnh | Khóa hạn mức phù hợp | Tránh |
| --- | --- | --- |
| Bearer API đã xác thực | Trusted issuer + tenant + principal/client + route group | Token nguyên văn, tenantId lấy từ JSON |
| API key | ID của key **đã xác minh** + tenant | Lưu plaintext API secret vào Redis/log |
| Login/password reset | Global + IP/network + account identifier có kiểm soát | Chỉ một IP bucket khiến cả mạng NAT bị chặn |
| Public API | Global + network/device signal hợp lệ | Tin X-Forwarded-For do client tự gửi |
| Export/quản trị | Actor + tenant + action/cost + concurrency | Dùng rate GET chung cho thao tác chi phí cao |

Nếu API nằm sau proxy, chỉ lấy IP từ **trusted proxy chain** đã cấu hình. Header Forwarded/X-Forwarded-For từ Internet có thể bị giả để tạo bucket vô hạn hoặc làm hết quota của nạn nhân. Với IPv6, NAT và mạng di động, cần thiết kế grouping phù hợp thay vì coi mỗi IP là một người.

**Denial-of-wallet:** một client không có quyền có thể cố dùng tên tenant của người khác để đốt ngân sách của tenant đó. Cần xác minh principal/tenant, tách **security-attempt limit** khỏi **business quota**, và cân nhắc thứ tự kiểm tra authorization với limiter. Một key Redis có raw URL/query/resource ID còn tạo nguy cơ **key explosion**; sử dụng route template, key prefix có version, max key count/TTL và không lấy ID tùy ý làm nhóm chính sách mới.

Giới hạn đọc API của tenant A không được bộc lộ cho tenant B thông qua headers hay response body. Log hạn mức phải che token, IP/PII theo policy; metric labels dùng route group/tier/status thay vì một nhãn cho từng user. Ngoại lệ cho service account phải có owner, expiry, scope và global guard; không cho bypass vô hạn vì “là service nội bộ”.

**Redis outage:** chọn fail closed/bounded fallback dựa trên threat model. Với endpoint login, phát hành token hoặc nghiệp vụ có chi phí lớn, không tự mở unlimited khi Redis lỗi. Với GET công khai, có thể dùng local emergency limiter và cảnh báo degraded, nhưng khi đó hạn mức **không còn chính xác toàn cụm**.

## 13. Đo lường và thay đổi chính sách có kiểm soát

Các chỉ số nên quan sát:

- Accepted/rejected rate theo **route group, tenant tier và policy version**.
- Retry-After distribution, tỷ lệ client retry quá sớm và lỗi 429/503.
- Redis latency, timeout, memory, số keys, script failures và failover.
- P95/p99 request latency, connection pool wait, concurrency/bulkhead occupancy.
- Queue length, age của job, TTL/eviction và retry amplification.

Nếu 429 tăng nhưng downstream vẫn rảnh, limit có thể quá nghiêm. Nếu 429 thấp nhưng p99/DB saturation tăng mạnh, cần xem concurrency, queue, cost và mức global. Khi thử chính sách mới, có thể chạy **shadow mode** chỉ tính quyết định, không chặn, rồi canary; shadow không được thay trạng thái quota thật gây mất quyền của client.

Các thay đổi **B/r/cost** cần version và quy tắc migrate bucket. Nếu một instance dùng ngưỡng cũ còn instance khác dùng ngưỡng mới, kết quả có thể không nhất quán; cần cơ chế rollout/rollback và kiểm thử chuyển state.

## 14. Kiểm thử: đồng hồ, concurrency, HTTP và Redis thật

### Unit test token bucket không cần sleep

~~~java
@Test
void burstAndRefillArePredictable() {
    LocalTokenBucket bucket =
        new LocalTokenBucket(10.0, 2.0, 0L);

    for (int i = 0; i < 10; i++) {
        assertTrue(bucket.tryConsume(1.0, 0L).allowed());
    }

    LimitDecision denied = bucket.tryConsume(1.0, 0L);
    assertFalse(denied.allowed());
    assertEquals(500L, denied.retryAfterMillis());

    assertFalse(bucket.tryConsume(
        1.0, 250_000_000L).allowed());
    assertTrue(bucket.tryConsume(
        1.0, 500_000_000L).allowed());
}
~~~

Test thêm **thời gian lùi**, cost = capacity, cost lớn hơn capacity, refill đầy nhưng không vượt B, số thập phân và idle TTL. Với sliding log, test hai request cùng millisecond nhưng khác member ID; với sliding counter, dùng traffic dồn ở đầu/cuối cửa sổ để đo sai số.

### Concurrency test trong một JVM

~~~java
@Test
void simultaneousCallsNeverSpendBeyondCapacity()
        throws Exception {

    LocalTokenBucket bucket =
        new LocalTokenBucket(10.0, 1.0, 0L);
    ExecutorService pool =
        Executors.newFixedThreadPool(16);
    CountDownLatch start = new CountDownLatch(1);

    try {
        List<Future<Boolean>> results = new ArrayList<>();
        for (int i = 0; i < 100; i++) {
            results.add(pool.submit(() -> {
                start.await();
                return bucket.tryConsume(1.0, 0L).allowed();
            }));
        }
        start.countDown();
        long passed = 0;
        for (Future<Boolean> f : results) {
            if (f.get()) passed++;
        }
        assertEquals(10L, passed);
    } finally {
        pool.shutdownNow();
    }
}
~~~

Bài test trên chỉ chứng minh thread safety của **một object/JVM**. Chạy integration test với Redis thật (ví dụ Testcontainers), nhiều API nodes và chung key; xác nhận tổng admitted không vượt capacity trong điều kiện cùng thời điểm. Thử Redis failover, key expiration, policy change, latency cao và two-key cross-slot thay vì chỉ mock Redis trả success.

### Kiểm thử HTTP bằng MockMvc

Sử dụng Spring Boot/Security test với interceptor đã đăng ký và mock AdmissionPolicy:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrdersLimitHttpTest {
    @Autowired MockMvc mvc;

    @MockBean AdmissionPolicy admission;
    @MockBean TrustedTenantResolver tenants;

    @Test
    void limitExceededReturns429() throws Exception {
        given(tenants.requireTenant(
            any(Authentication.class))).willReturn("tenant-a");

        given(admission.acquire(
            "orders-read", "tenant-a", "sub-a", 1.0))
            .willReturn(new LimitDecision(false, 1500L, 0.0));

        mvc.perform(get("/api/v1/orders")
                .with(jwt()
                    .jwt(j -> j.subject("sub-a"))
                    .authorities(
                        new SimpleGrantedAuthority(
                            "SCOPE_orders:read"))))
            .andExpect(status().isTooManyRequests())
            .andExpect(header().string("Retry-After", "2"))
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.parseMediaType(
                    "application/problem+json")))
            .andExpect(jsonPath("$.status").value(429))
            .andExpect(jsonPath("$.code")
                .value("RATE_LIMIT_EXCEEDED"));
    }
}
~~~

Ví dụ là **skeleton theo Spring Boot 3.x** với imports/JUnit/Mockito và security route configuration tương ứng. Các phiên bản Boot mới có thể dùng annotation mock khác; **jwt() trong spring-security-test không xác minh JWT signature/issuer/audience**, cần test decoder riêng. Một test 429 chỉ chứng minh interceptor/HTTP mapping, không chứng minh Redis multi-instance đã nguyên tử.

| Trường hợp tích hợp | Kỳ vọng |
| --- | --- |
| 10 request tức thời và request 11 | Chính xác 10 accept khi B=10, từ chối request 11 |
| Fixed window sát ranh giới | Hiểu burst gần 2L trong khoảng rất ngắn |
| Sliding log/trùng timestamp | Không đếm thiếu vì duplicate member |
| Sliding counter traffic dồn | Sai số được đo, chính sách chấp nhận |
| 100 request đồng thời qua Redis | Admission nguyên tử cho cùng bucket |
| Hai tenant và hai user | Không tính chéo quota hoặc lộ dữ liệu |
| Thiếu token, thiếu scope, CORS preflight | 401/403/CORS đúng, không dùng 429 thay security |
| API bị giới hạn | Retry-After hợp lệ, JSON Problem Details, no-store |
| POST bị timeout rồi retry | Giữ Idempotency-Key, không tạo resource trùng |
| Redis outage/failover, clock skew | Failure policy đúng, không unlimited ngoài chủ đích |
| Nhiều key/TTL/idle eviction | Không reset quá sớm hoặc leak memory |
| Queue đầy, job cancel | Không rò task/connection, 202 chỉ sau durable enqueue |

Load test phải có giới hạn và chạy ở môi trường được phép. Đo rate, burst, concurrency và số attempts, không chỉ thông lượng. Với WebFlux cần test reactive scheduler/backpressure riêng; ví dụ này chỉ nhắm Spring MVC.

## 15. Bài tập: hệ thống Orders và Reports ba instance

Hệ thống Spring MVC gồm **3 API instance**, Redis chung, database pool 60. Các route:

- **GET /api/v1/orders:** dashboard cần burst hợp lệ, cache có thể hit.
- **POST /api/v1/orders:** tạo đơn có side effect và **Idempotency-Key**.
- **POST /api/v1/reports:** tạo job nặng, trả 202 và có queue giới hạn.
- **POST /api/v1/auth/login:** caller chưa xác thực, có nguy cơ credential stuffing.

Hãy thực hiện:

1. Chọn token bucket, leaky queue, fixed/sliding window cho từng route; giải thích độ chính xác, fairness, burst và chi phí.
2. Mô phỏng **B=10, r=2/s** với 12 request t=0, sau đó request ở t=0,25 và t=0,5. Tính accepted và Retry-After.
3. Thiết kế Redis keys theo trusted tenant/principal/route group và quota global. Phân tích source IP cho login.
4. Viết Java/Spring interceptor trả **429 + Retry-After + application/problem+json**; bảo vệ 401/403, OPTIONS preflight và token isolation.
5. Cài Lua atomic bucket; kiểm tra TTL, cost nặng, Redis Cluster, failover và fail-closed/bounded fallback.
6. Thiết kế report queue: bounded capacity, μ jobs/s, operation resource và cancellation; chỉ trả 202 khi job bền vững.
7. Viết ít nhất **10 test**: burst, refill, fixed boundary, sliding approximation, concurrency, auth/tenant, 429, Redis outage, POST retry.
8. Đề xuất metrics, canary và rollback khi hạn mức mới gây 429 không mong muốn.

**Sản phẩm:** bảng chính sách, công thức, HTTP transcript, Java/Spring, Redis script, test matrix và ADR trình bày đánh đổi.

## 16. Checklist và kết luận

| Câu hỏi | Tiêu chí |
| --- | --- |
| Khóa limiter có đáng tin? | Tenant/principal/route group từ auth, không raw headers |
| Ngưỡng có định nghĩa? | B, r, cost, window, burst và policy version rõ |
| Thuật toán phù hợp? | Token bucket cho burst; queue shaper cho async; window theo quota |
| Atomic trên nhiều instance? | Redis Lua hoặc cơ chế tương đương, consistency policy rõ |
| Có giới hạn tải đang chạy? | Concurrency, timeout, queue bounded, circuit breaker |
| HTTP đúng? | 429, Retry-After, Problem Details, không nhầm 401/403/503 |
| Retry POST an toàn? | Idempotency-Key và dữ liệu có transaction/đối soát |
| Có đo và test? | Clock-controlled, concurrent, Redis, MockMvc, canary |

**Kết luận:** **Token bucket** cho phép burst trong giới hạn và duy trì tốc độ trung bình; **leaky bucket dạng hàng đợi** làm phẳng công việc nhưng tăng độ trễ; **fixed/sliding windows** kiểm soát số request theo thời gian với đánh đổi giữa ca biên, bộ nhớ và độ chính xác. Rate limiter đáng tin phải có **identity chính xác, cập nhật nguyên tử, HTTP hợp lệ, giới hạn quá tải bổ sung và kiểm thử dưới concurrency**, chứ không chỉ một bộ đếm trong bộ nhớ.







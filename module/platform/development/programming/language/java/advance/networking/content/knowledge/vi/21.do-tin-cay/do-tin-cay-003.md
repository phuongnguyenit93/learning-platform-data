# Thử lại có giới hạn với khoảng chờ tăng dần và độ lệch ngẫu nhiên trong Java Networking

Khi một HTTP request gặp `503 Service Unavailable`, `429 Too Many Requests` hoặc lỗi kết nối tạm thời, gửi lại yêu cầu có thể giúp hệ thống vượt qua sự cố ngắn hạn. Nhưng “cứ lỗi thì thử lại ngay” là chiến lược nguy hiểm: nhiều clients có thể đồng loạt tấn công lại server đang quá tải, làm độ trễ tăng, chiếm worker threads và nhân số request trong toàn hệ thống. Nếu request có side effects, việc retry còn có thể **tạo đơn hàng, thu tiền hoặc ghi dữ liệu trùng** khi server đã xử lý request đầu nhưng client chưa nhận được response.

Bài Knowledge này tập trung vào **bounded retries + capped exponential backoff + jitter**:

1. **Chỉ retry lỗi tạm thời và thao tác có thể lặp lại an toàn**; phân biệt transient transport failure, HTTP status và business failure.
2. **Giới hạn số lần thử** (`maxAttempts` gồm cả lần đầu), thời gian từng attempt, **tổng deadline**, số retries cùng lúc và dung lượng queue.
3. **Tăng khoảng chờ sau các lần lỗi** với exponential backoff có trần (`maxBackoff`), sau đó thêm **jitter** để clients không thức dậy đồng loạt.
4. **Tôn trọng `Retry-After`** của server khi thích hợp; không cắt một yêu cầu đợi 1 giờ xuống 2 giây chỉ vì local backoff cap là 2 giây.
5. **Dừng đúng lúc** khi thành công, gặp lỗi không retryable, hết attempts, hết time budget, bị hủy/interrupt hoặc request body không thể phát lại.
6. **Quan sát và thử nghiệm** bằng Java 17+, với một ví dụ toán học có kết quả cố định, một HTTP server loopback trả 503→503→200, và một ví dụ async dùng `ScheduledExecutorService` thay vì block thread bằng `sleep`.

**Nguyên tắc nền tảng:** retry là một **phương án phục hồi có giới hạn**, không phải bảo đảm request thành công, không phải message delivery “exactly once”, và không thay cho rate limiting, timeout, circuit breaker hoặc backpressure.

## 1. Khi nào retry giúp ích và khi nào làm hại?

### 1.1. Transient failure là gì?

Một lỗi transient có cơ hội tự hết sau một khoảng thời gian ngắn: server tạm quá tải, mạng chập chờn, proxy/gateway bị ngắt trong lúc thay kết nối, rate limit tạm thời hoặc service đang khởi động lại. Nếu client gửi lại **có kiểm soát**, khả năng thành công có thể tăng.

~~~text
Client                       API server
  │ GET /inventory               │
  ├──────────────────────────────>│
  │<──────── 503 + Retry-After ──┤   Server đang bảo trì ngắn
  │                              │
  │    capped backoff + jitter   │
  │    (không spin retry)        │
  │                              │
  ├──────────────────────────────>│
  │<──────── 200 OK ─────────────┤
~~~

Một số lỗi không tự hết bằng lặp request y hệt: endpoint sai (404), token không hợp lệ (401), thiếu quyền (403), request body malformed (400/422), business constraint fail hoặc certificate không tin cậy. Retry liên tục những lỗi này tạo chi phí vô ích và có thể che giấu root cause.

### 1.2. Bảng chính sách retry HTTP khởi điểm

| Tình huống | Retry tự động? | Điều kiện |
| --- | --- | --- |
| `GET/HEAD` nhận `429` | Thường **có thể** | Nếu được phép, tôn trọng rate-limit/Retry-After và tổng deadline |
| `GET/HEAD` nhận `503` | Thường **có thể** | Service unavailable tạm, budget còn |
| `502/504` | Có thể theo policy | Gateway/upstream tạm lỗi; chỉ khi request có semantics retry-safe |
| `500` | **Không mặc định** | Phải biết lỗi server có khả năng transient; lặp một lỗi logic mãi không giúp |
| `408` | Có thể theo semantics/contract | Request timeout tại HTTP layer, xác minh request có thể phát lại |
| `400/401/403/404/422` | **Không** với payload y nguyên | Cần sửa request, credential, permission hoặc resource |
| `409/412` | Không retry mù | Conflict/Precondition Failed cần đọc state mới rồi quyết định |
| `301/302/307/308` | Không phải transient failure mặc định | Redirect là cơ chế riêng; `Retry-After` có thể liên quan redirect |
| TCP connection reset/temporary `IOException` | Có thể | Phân loại lỗi và an toàn idempotency, đừng retry tất cả IOException |
| `UnknownHostException` do host sai | Thường không | DNS/config sai, thử lại vô hạn không tạo host hợp lệ |
| `SSLHandshakeException`/certificate mismatch | Không | Sửa TLS trust/hostname, không bỏ xác thực |
| `InterruptedException`/caller cancel | Không | Tôn trọng cancellation, restore interrupt khi cần |

**Đây là điểm xuất phát, không phải quy tắc HTTP bắt buộc cho mọi API.** Lỗi `429` là tín hiệu rate limiting, có thể kèm `Retry-After`; lỗi `503` là unavailable tạm, cũng có thể kèm hint. Một API có thể cung cấp error codes riêng, quota windows và retry rules nghiêm hơn. Lỗi transport trước khi client nhận response **không chứng minh server chưa xử lý request**.

### 1.3. Ba câu hỏi trước khi retry

Trước khi cho bất kỳ code nào thực hiện thêm một attempt, trả lời:

1. **Retryable?** Lỗi này có khả năng transient theo hợp đồng của dịch vụ?
2. **Safe to replay?** Request có idempotency semantics hoặc cơ chế deduplication, body có thể gửi lại và auth/context vẫn hợp lệ?
3. **Budget available?** Số lần thử, thời gian, concurrency, tài nguyên và policy Retry-After còn cho phép?

**Chỉ khi cả ba câu trả lời là “có” mới lên lịch attempt tiếp theo.** Jitter/backoff không làm một request không idempotent trở thành an toàn.

## 2. Bounded retry: phân biệt attempts, retries và time budget

Hai tham số dễ bị nhầm:

- `maxAttempts = 4`: tổng **tối đa 4 lần gửi**; gồm lần đầu và tối đa **3 lần thử lại**.
- `maxRetries = 4`: nếu dùng tên này thì tổng **tối đa 5 lần gửi**.

Trong bài, các ví dụ luôn dùng **`maxAttempts`**, và `attempt` đếm từ 1.

~~~text
maxAttempts = 4

attempt #1  -- fail --> backoff #1
attempt #2  -- fail --> backoff #2
attempt #3  -- fail --> backoff #3
attempt #4  -- fail --> STOP (hết lượt, không ngủ thêm)

Có nhiều nhất 4 lần network call, 3 lần delay.
~~~

**Không bao giờ sleep sau attempt cuối.** Đây là lỗi implementation phổ biến làm request thất bại vẫn chậm thêm vài giây vô ích.

### 2.1. Ba ranh giới thời gian

Một retry policy hoàn chỉnh nên có cả:

| Tham số | Ý nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| `perAttemptTimeout` | Mỗi network call được phép chạy bao lâu | 1,5 giây |
| `totalDeadline` | Tổng thời gian từ lúc bắt đầu request đến lúc dừng mọi retries | 5 giây |
| `maxBackoff` | Trần khoảng chờ exponential **tự chọn của client** | 1 giây |

Giả sử deadline chung còn 350ms, trong khi retry delay đã chọn 500ms. **Không lên lịch retry nữa**, dù vẫn còn attempt slots: delay sẽ vượt budget trước khi attempt mới bắt đầu. Cần xét thời gian để network call thực sự hoàn thành, không chỉ đủ thời gian cho sleep.

Một triển khai có thể áp đặt:

~~~text
time_remaining = total_deadline - elapsed
if time_remaining <= 0:
    STOP
if proposed_wait >= time_remaining:
    STOP
otherwise:
    schedule next attempt after proposed_wait
    next per-attempt timeout <= remaining time after wait
~~~

Dùng `System.nanoTime()` hoặc time source **monotonic** để đo elapsed/deadline; không trừ `System.currentTimeMillis()` khi đồng hồ hệ thống có thể được chỉnh NTP. `Instant`/wall clock vẫn cần khi xử lý **HTTP-date trong Retry-After**; đây là hai loại thời gian khác nhau.

**Retry budget còn có thể là tài nguyên, không chỉ thời gian**: cho phép tối đa X retry tokens/second, Y concurrent requests và Z pending tasks theo service/tenant. Một deadline đúng nhưng tạo hàng nghìn scheduled futures không giới hạn vẫn có thể gây overload.

## 3. Capped exponential backoff: công thức và cách đếm

Sau **lần thử thứ k thất bại** (`k` bắt đầu từ 1), nếu còn được retry:

\[
\text{capDelay}(k)=\min(\text{maxBackoff},\ \text{baseDelay}\times 2^{k-1})
\]

Lấy ví dụ `baseDelay = 100ms`, `maxBackoff = 500ms`:

| Attempt thất bại | Exponential trước cap | Capped delay |
| --- | ---: | ---: |
| 1 | 100ms | 100ms |
| 2 | 200ms | 200ms |
| 3 | 400ms | 400ms |
| 4 | 800ms | 500ms |
| 5 | 1.600ms | 500ms |

Khoảng đợi **không tăng mãi**. Trần cap bảo vệ latency và tránh overflow khi số lần thử nhiều. Nếu `maxAttempts=5`, chỉ dùng delay sau failures 1,2,3,4 — **không dùng delay sau failure 5**.

### 3.1. Vì sao không dùng `baseDelay << (k-1)` tùy ý?

Trong Java, shift lớn có thể overflow/shift-mask ngoài dự kiến; multiplication `base * (1L << n)` cũng overflow. Dùng thuật toán **saturating multiplication**:

~~~java
long cap = baseMillis;
for (int i = 1; i < failedAttempt; i++) {
    cap = cap > maxMillis / 2
            ? maxMillis
            : cap * 2;
}
~~~

Đoạn này là **minh họa** khi `baseMillis > 0`, `maxMillis >= baseMillis` và các values không vượt khả năng của `long`. Khi cap đã gần trần, phép nhân được thay bằng `maxMillis` mà không overflow.

**Cẩn thận khi tính bounds cho random:** nếu dùng `random.nextLong(cap + 1)` để lấy range bao gồm cap, phải bảo đảm `cap < Long.MAX_VALUE` vì `cap+1` có thể overflow. Trong production chọn config durations hữu hạn/hợp lý (ms đến seconds/minutes tùy workload), không lấy `Long.MAX_VALUE` làm trần delay.

## 4. Jitter: vì sao thêm ngẫu nhiên vào thời gian chờ?

Không jitter:

~~~text
1000 clients gặp lỗi cùng lúc
             |
     1000 clients ngủ đúng 100ms
             |
     1000 clients thức dậy cùng lúc ──> server lại quá tải
             |
     1000 clients ngủ đúng 200ms
             |
     lại đồng loạt thức dậy ─────────> một làn sóng mới
~~~

Đây là **thundering herd**: exponential backoff có thể tạo những **cụm request đồng bộ** dù giảm tần suất trung bình. Jitter làm các clients có delay khác nhau để trải lưu lượng ra thời gian.

Ba biến thể thường gặp (với `B_k` là capped exponential delay):

| Chiến lược | Cách lấy delay | Đặc tính |
| --- | --- | --- |
| **No jitter** | `B_k` | Dễ đồng bộ, retry bursts |
| **Full jitter** | Random đồng đều từ `0` tới `B_k` | Đơn giản, giảm đồng bộ; delay có thể rất ngắn/0 |
| **Equal jitter** | `B_k / 2 + random(0..B_k/2)` | Không giảm dưới nửa cap, ít zero-delay hơn |
| **Decorrelated jitter** | Random trong khoảng dựa trên base và lần đợi trước, rồi cap | Ít phụ thuộc attempts nhưng stateful và khó test hơn |

Theo bài phân tích của AWS về exponential backoff/jitter, **full jitter** có hiệu quả tốt trong nhiều contention scenarios. Không có thuật toán nào bảo đảm mọi request thành công; lựa chọn còn phụ thuộc quota, latency SLA, server hint và workload. Bài dùng **full jitter làm mặc định đơn giản**.

### 4.1. Full jitter lấy số ngẫu nhiên thế nào?

~~~java
long delayMillis = ThreadLocalRandom.current()
        .nextLong(capMillis + 1);
~~~

Đây là **đoạn Java minh họa** với `capMillis` được xác nhận từ 0 tới `Long.MAX_VALUE-1`, cần import `java.util.concurrent.ThreadLocalRandom`. `nextLong(bound)` lấy giá trị **0 đến bound-1**, nên cộng 1 để bao gồm `capMillis`. Delay có thể là 0; trong hệ thống rate-limited, cần kết hợp **server minimum Retry-After**/minimum delay nếu chính sách yêu cầu, không bỏ qua thông điệp của server.

Khi unit test, **đừng phụ thuộc ngẫu nhiên thật để assert stdout**. Truyền vào một strategy/random sampler được kiểm soát, ví dụ luôn chọn `cap/2`, và test thêm rằng random delay luôn nằm trong bounds. Ví dụ 1 thực hiện điều đó.

### 4.2. Full jitter khác random cộng thêm vào exponential

Một anti-pattern:

~~~text
delay = cappedExponential + random(0..cappedExponential)
~~~

Nó đẩy delay từ `B_k` lên tối đa `2B_k`, **vượt cap nếu không cắt lại**, và có xu hướng tăng thời gian chờ. Đây **không phải full jitter**. Nếu muốn random quanh B_k, cần xác định rõ range, cap và thuật toán; không gọi mọi “+ random” là full jitter.

### 4.3. Jitter không được phá `Retry-After` của server

Giả sử server gửi `Retry-After: 30`, nghĩa là nên đợi ít nhất khoảng 30 giây trước khi retry. Local full jitter cho cap 1.000ms ra 125ms **không được dùng để retry ngay sau 125ms**.

Cách phối hợp thường gặp:

~~~text
clientJitter = uniform(0, cappedExponential)
serverMinimum = parsed Retry-After (nếu hợp lệ/đáng tin)
proposedWait = max(clientJitter, serverMinimum)

if proposedWait exceeds remaining total budget:
    fail / defer request; do not silently shorten serverMinimum
else:
    schedule after proposedWait
~~~

`maxBackoff` chỉ giới hạn phần delay **local backoff**, không phải sự cho phép phá giới hạn rate-limit do peer công bố. Khi server bảo chờ quá dài, thường nên **báo retry-deferred/quota exceeded** để caller xử lý thay vì giữ hàng nghìn scheduled tasks trong một service.

## 5. `Retry-After`: hiểu đúng cả số giây lẫn HTTP-date

[RFC 9110 `10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3) định nghĩa `Retry-After` là **một HTTP-date hoặc số nguyên thập phân không âm chỉ delay-seconds**:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 120
Content-Length: 0
~~~

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: Fri, 31 Dec 1999 23:59:59 GMT
Content-Length: 0
~~~

Header có thể xuất hiện với `503`, `429` và cả một số responses `3xx` (với redirection semantics). `429` theo RFC 6585 **có thể** kèm header, không bắt buộc phải có. Không đọc header từ HTTP response lỗi network không có headers.

**Parser production** cần xử lý:
- `delay-seconds`: số nguyên **giây**, không phải millisecond; `Retry-After: 5` nghĩa là khoảng **5 giây**.
- HTTP-date: chuyển sang `Instant` theo UTC; lấy `max(0, date - now)` để xử lý ngày đã qua.
- RFC dùng HTTP-date; `DateTimeFormatter.RFC_1123_DATE_TIME` xử lý dạng phổ biến IMF-fixdate trong Java 17; nếu cần hỗ trợ các obsolete HTTP-date formats còn được chấp nhận theo HTTP spec, dùng parser HTTP chuẩn đã được kiểm chứng, không tự phân tích chuỗi bằng cách cắt ký tự.
- `Long.parseLong`/`Duration.ofSeconds` và phép nhân 1.000 có thể overflow; không để một header xấu crash retry loop.
- Multiple header values/invalid syntax: xác định policy rõ (bỏ qua, reject hoặc fail closed theo trust), không lặp vô hạn.
- Đồng hồ client có thể lệch so với server; nếu cần độ chính xác, xét `Date` response header, round-trip và clock skew thay vì tin tuyệt đối đồng hồ local.
- Header có giá trị rất lớn: nếu vượt deadline/quota, **dừng retry hoặc báo để scheduling tầng cao xử lý**, không spin hay clamp xuống thấp hơn server minimum.

Ví dụ **utility minh họa Java 17** cho các giá trị phổ biến (không xử lý obsolete HTTP-date variants):

~~~java
static Optional<Duration> parseRetryAfter(
        String raw, Clock clock) {
    String value = raw.trim();
    try {
        if (value.matches("[0-9]+")) {
            return Optional.of(
                    Duration.ofSeconds(Long.parseLong(value)));
        }

        Instant target = ZonedDateTime.parse(
                value, DateTimeFormatter.RFC_1123_DATE_TIME)
                .toInstant();
        Duration until =
                Duration.between(clock.instant(), target);
        return Optional.of(
                until.isNegative() ? Duration.ZERO : until);
    } catch (DateTimeParseException
             | ArithmeticException invalid) {
        return Optional.empty();
    }
}
~~~

Đây là **đoạn minh họa trong class/method utility**, cần imports `java.time.*`, `java.time.format.DateTimeFormatter`, `java.time.format.DateTimeParseException`, `java.util.Optional`, và caller chỉ truyền `raw` không null. Chỗ `catch` bao gồm invalid numeric values; không coi `Optional.empty()` là chứng cứ server “cho retry ngay”. Nếu header không parse được và policy yêu cầu tôn trọng, có thể **fail/defer** thay vì fallback delay quá ngắn.

Với `HttpResponse<?>`, lấy header bằng `response.headers().firstValue("Retry-After")`, không dựa vào chính tả chữ hoa/thường. Đừng tin `Retry-After` từ một endpoint không nằm trong trust boundary để enqueue một scheduler vô hạn.

## 6. Retry safety: idempotency quan trọng hơn công thức backoff

[RFC 9110 `9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2) mô tả idempotency là **tác động mong muốn** khi lặp request nhiều lần tương đương một lần. Các HTTP methods safe như GET/HEAD thường idempotent; PUT/DELETE cũng có idempotent semantics. `POST` không mặc định idempotent.

| Method / tác vụ | Retry khi response không tới? | Cần chú ý |
| --- | --- | --- |
| `GET /products` | Thường có thể | Dữ liệu có thể đổi giữa attempts; vẫn cần deadline |
| `HEAD /health` | Thường có thể | Không xem success là transaction guarantee |
| `PUT /resource/42` gán cùng desired state | Có thể theo contract | ETag/version precondition có thể làm attempt sau nhận 412 |
| `DELETE /resource/42` | Thường idempotent về intended effect | Response lần sau có thể 404 dù effect đã đạt |
| `POST /payments` | **Không mặc định** | Có thể thu tiền hai lần |
| `POST /payments` với Idempotency-Key được server hỗ trợ | Có thể **nếu** API có dedupe contract | Key scope, TTL, payload consistency, replay, retry policy |
| Upload streaming từ một `InputStream` đã bị đọc | Không nếu body không tạo lại được | Cần supplier có thể mở stream mới với bytes y hệt |

Ví dụ request POST có thể đã ghi đơn hàng rồi TCP bị ngắt trước response; client chỉ thấy `IOException`. Retry ngay sẽ ghi **đơn thứ hai** nếu backend không deduplicate. Giải pháp không nằm ở jitter:
1. Client tạo `operationId` hoặc **Idempotency-Key** duy nhất cho một logical operation.
2. Backend persist key cùng kết quả/transaction state theo scope và TTL rõ.
3. Retry cùng key và **cùng payload semantics**.
4. Server trả cùng kết quả hoặc trạng thái đã xác nhận theo API contract.
5. Nếu không chắc liệu backend hỗ trợ, **không tự bật retry POST**.

**Idempotency ở HTTP method không đồng nghĩa “mọi hệ thống implement đúng”.** GET ở một API thiết kế sai có thể tạo side effects; client phải biết hợp đồng của endpoint. POST với idempotency key chỉ an toàn trong phạm vi key semantics được server cam kết. Và retry không cấp “exactly-once” cho một hệ phân tán; chỉ giúp quản lý xác suất duplicate.

### 6.1. Request body replayable trong Java 17

`HttpRequest.BodyPublishers.ofString(...)` hoặc `ofByteArray(...)` thường phù hợp khi payload có thể tái sử dụng. Với streaming:

~~~java
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofInputStream(
                () -> Files.newInputStream(path));
~~~

Đây là **minh họa có thể cần xử lý `IOException` trong lambda**: `Files.newInputStream(path)` có checked IOException, nên ví dụ **không phải code hoàn chỉnh để dán biên dịch trực tiếp**; phiên bản dùng trong method Java có thể là:

~~~java
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofInputStream(() -> {
            try {
                return Files.newInputStream(path);
            } catch (IOException failure) {
                throw new UncheckedIOException(failure);
            }
        });
~~~

Đoạn thứ hai là **code minh họa đúng cú pháp** với `path` và imports `java.nio.file.Files`, `java.io.*`, `java.net.http.HttpRequest`. Javadoc `BodyPublishers.ofInputStream(Supplier<? extends InputStream>)` dùng supplier **vì request có thể cần lặp lại**; mỗi lần subscription có thể mở một InputStream mới. Một supplier luôn trả **cùng một InputStream đã dùng hết** là sai.

Để đảm bảo body giống nhau sau retry, file/stream nguồn cần ổn định (snapshot/checksum/version) trong toàn bộ logical request. Nếu file bị thay giữa attempts, cùng idempotency key nhưng payload khác có thể khiến backend reject hoặc gây sai trạng thái. **Không retry một stream không replayable chỉ vì code có thể gọi lại sendAsync.**

## 7. Phân loại lỗi Java thay vì `catch(Exception) { retry(); }`

Có hai đường thất bại của `java.net.http.HttpClient`:

1. **Có HTTP response:** `client.send(req, handler)` trả `HttpResponse<T>` với `statusCode()` (kể cả 429/503). Bản thân HTTP 503 **không ném IOException chỉ vì status là 503**.
2. **Không nhận được response hoàn chỉnh:** `send` có thể ném `IOException`, `InterruptedException`; `sendAsync` có thể complete exceptionally.

Không nên retry đồng loạt mọi exception. Phải xét:

| Exception / trạng thái | Ví dụ nguyên nhân | Gợi ý |
| --- | --- | --- |
| `java.net.http.HttpTimeoutException` | Attempt vượt timeout của request | Có thể transient; xét idempotency và total budget |
| `ConnectException` | Service chưa listen, proxy refused | Có thể tạm hoặc config sai; policy theo endpoint |
| `SocketTimeoutException` | Read/connect timeout ở socket API cũ | Có thể tạm; không chứng minh server chưa xử lý |
| `SocketException: Connection reset` | Mạng/peer reset | Có thể retry safe operation |
| `UnknownHostException` | DNS resolution fail | Thường phải sửa DNS/hostname; tránh thử liên tục |
| `SSLHandshakeException` | Certificate/TLS protocol/identity mismatch | Không retry mù, không tắt TLS validation |
| `InterruptedException` | Caller/thread yêu cầu ngừng | **Dừng**, propagate hoặc restore interrupt |
| `CancellationException` | Request bị hủy | **Dừng**, không tự khởi động lại |
| `CompletionException`/`ExecutionException` | Wrapper của async failure | Bóc cause trước khi phân loại |
| `IllegalArgumentException` từ build request | Request config invalid | Không retry |
| `429/503` response | Server đã trả status | Dùng status policy và `Retry-After` |

Một `IOException` cũng có thể do file request-body đọc lỗi, write-to-file lỗi hoặc filesystem bị đầy, không phải transient network. Nếu transport không xác nhận rõ nguồn, retry toàn bộ `IOException` có thể không an toàn. Bài demo async ở phần 11 chỉ dùng **simulated IOExceptions**, nên policy “IOException thì thử lại” trong demo không đại diện cho production classification.

## 8. Ví dụ Java 17+ số 1: tính capped exponential + full jitter có thể kiểm thử

Ví dụ này **không dùng network**, tách tính toán retry khỏi HTTP. Chính sách:
- `maxAttempts = 5`: tối đa 5 attempts và 4 delays.
- `baseMillis = 100`, `maxMillis = 500`.
- `cappedExponentialMillis` nhân đôi có bão hòa, không overflow.
- `chooseFullJitter` nhận một hàm random sampler, kiểm tra giá trị phải trong `[0, cap]`.
- Trong unit-demo, sampler **cố ý chọn cap/2** để stdout luôn lặp lại chính xác. Nó **không phải random production**.
- Sau đó chương trình thử một lần `ThreadLocalRandom` và chỉ assert range, **không in giá trị ngẫu nhiên**.

Tạo file **`RetryBackoffMathDemo.java`**:

~~~java
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.LongUnaryOperator;

public final class RetryBackoffMathDemo {
    static long cappedExponentialMillis(
            int failedAttempt, long baseMillis, long maxMillis) {
        if (failedAttempt < 1 || baseMillis < 1
                || maxMillis < baseMillis
                || maxMillis == Long.MAX_VALUE) {
            throw new IllegalArgumentException(
                    "Invalid retry policy");
        }

        long cap = baseMillis;
        for (int i = 1; i < failedAttempt; i++) {
            cap = (cap > maxMillis / 2)
                    ? maxMillis
                    : cap * 2;
        }
        return cap;
    }

    static long chooseFullJitter(
            long capMillis, LongUnaryOperator pickExclusive) {
        long candidate =
                pickExclusive.applyAsLong(capMillis + 1);
        if (candidate < 0 || candidate > capMillis) {
            throw new IllegalArgumentException(
                    "Jitter out of range");
        }
        return candidate;
    }

    public static void main(String[] args) {
        int maxAttempts = 5; // 1 initial + at most 4 retries
        long accumulated = 0;

        LongUnaryOperator deterministic =
                bound -> (bound - 1) / 2;

        for (int failed = 1;
                failed < maxAttempts;
                failed++) {
            long cap = cappedExponentialMillis(
                    failed, 100, 500);
            long delay = chooseFullJitter(
                    cap, deterministic);
            accumulated += delay;
            System.out.println(
                    "failure=" + failed
                    + " cap=" + cap
                    + " deterministicDelay=" + delay);
        }

        System.out.println(
                "total deterministic wait=" + accumulated);

        long actualRandom = chooseFullJitter(500,
                bound -> ThreadLocalRandom.current()
                        .nextLong(bound));
        System.out.println(
                "random within 0..500: " +
                (actualRandom >= 0 && actualRandom <= 500));
    }
}
~~~

~~~bash
javac --release 17 RetryBackoffMathDemo.java
java RetryBackoffMathDemo
~~~

Stdout **đã kiểm thử và không phụ thuộc seed ngẫu nhiên**:

~~~text
failure=1 cap=100 deterministicDelay=50
failure=2 cap=200 deterministicDelay=100
failure=3 cap=400 deterministicDelay=200
failure=4 cap=500 deterministicDelay=250
total deterministic wait=600
random within 0..500: true
~~~

**Giải thích:**
- Thất bại lần 1: cap=100, sampler test lấy 50ms.
- Thất bại lần 2: cap=200, lấy 100ms.
- Thất bại lần 3: cap=400, lấy 200ms.
- Thất bại lần 4: exponential ra 800 nhưng cap=500, lấy 250ms.
- Tổng delay test 50+100+200+250=**600ms** nếu có đầy đủ bốn retries. Tổng này **chưa bao gồm thời gian thực hiện từng request**.
- Real jitter sampling với `ThreadLocalRandom` trả một giá trị khác nhau theo lần chạy; chỉ kiểm tra boolean nằm trong bounds để stdout ổn định.
- Hàm `chooseFullJitter` yêu cầu sampler trả số trong range, nhưng **không tự đảm bảo sampler phân phối đồng đều**. Production chọn `ThreadLocalRandom.current().nextLong(bound)` hoặc random generator phù hợp; deterministic sampler chỉ dành cho tests.
- Hàm `cappedExponentialMillis` có complexity O(failedAttempt) và cho phép số attempts hợp lý; không cần tính `Math.pow(2,k)` bằng `double` rồi cast long (có thể mất chính xác/overflow).

Trong production nên test overflow, base/cap invalid, maxAttempts=1, zero/negative duration, source time budgets và không tạo delays sau final attempt.

## 9. Ví dụ Java 17+ số 2: HTTP loopback, retry 503 đúng ba attempts

Ví dụ này dùng `HttpServer` của JDK để tạo server **chỉ nghe loopback**, không gọi API bên ngoài:
- Request 1 trả `503` và `Retry-After: 0`.
- Request 2 cũng trả `503` và `Retry-After: 0`.
- Request 3 trả `200` với body `ready`.
- Client dùng **GET idempotent**, `maxAttempts=3`, đọc toàn bộ response body bằng `BodyHandlers.ofString()` rồi quyết định retry.
- Delay là **deterministic test jitter** `cap/2`: 5ms và 10ms. Mẫu dùng `Thread.sleep` vì chỉ minh họa synchronous retry trong một test console; không dùng kiểu này trên event loop/request-serving thread tải cao.

Tạo file **`HttpBoundedRetryDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

public final class HttpBoundedRetryDemo {
    private static boolean retryableStatus(int code) {
        return code == 429 || code == 503;
    }

    public static void main(String[] args)
            throws Exception {
        AtomicInteger calls = new AtomicInteger();
        InetAddress loopback =
                InetAddress.getLoopbackAddress();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);

        server.createContext("/read", exchange -> {
            int number = calls.incrementAndGet();
            boolean temporary = number <= 2;
            String message =
                    temporary ? "busy" : "ready";
            byte[] body = message.getBytes(
                    StandardCharsets.UTF_8);
            if (temporary) {
                exchange.getResponseHeaders()
                        .set("Retry-After", "0");
            }

            exchange.sendResponseHeaders(
                    temporary ? 503 : 200,
                    body.length);
            try (OutputStream out =
                    exchange.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();

        try {
            URI url = new URI(
                    "http", null, loopback.getHostAddress(),
                    server.getAddress().getPort(),
                    "/read", null, null);

            HttpClient client = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request =
                    HttpRequest.newBuilder(url)
                            .timeout(Duration.ofSeconds(3))
                            .GET().build();

            final int maxAttempts = 3;
            HttpResponse<String> result = null;

            for (int attempt = 1;
                    attempt <= maxAttempts;
                    attempt++) {
                result = client.send(
                        request,
                        HttpResponse.BodyHandlers.ofString());
                System.out.println(
                        "attempt=" + attempt
                        + " status=" + result.statusCode());

                if (!retryableStatus(result.statusCode())
                        || attempt == maxAttempts) {
                    break;
                }

                long capMillis =
                        Math.min(40L, 10L << (attempt - 1));
                long deterministicJitter =
                        capMillis / 2;

                long serverMinMillis = result.headers()
                        .firstValue("Retry-After")
                        .map(Long::parseLong)
                        .map(seconds -> seconds * 1000)
                        .orElse(0L); // test server only sends "0"

                long delayMillis = Math.max(
                        deterministicJitter,
                        serverMinMillis);
                System.out.println(
                        "backoff ms=" + delayMillis);
                Thread.sleep(delayMillis);
            }

            System.out.println(
                    "final body=" + result.body());
            System.out.println(
                    "origin calls=" + calls.get());
        } finally {
            server.stop(0);
        }
    }
}
~~~

~~~bash
javac --release 17 HttpBoundedRetryDemo.java
java HttpBoundedRetryDemo
~~~

Stdout **đã kiểm tra trên JDK cục bộ**:

~~~text
attempt=1 status=503
backoff ms=5
attempt=2 status=503
backoff ms=10
attempt=3 status=200
final body=ready
origin calls=3
~~~

**Điểm học quan trọng:**

1. `HttpResponse<String>` với status 503 được trả như HTTP response bình thường; không cần `catch(IOException)` để nhận biết status.
2. `GET` phù hợp với ví dụ replay vì read-only/idempotent về intended effect theo HTTP semantics. Không tự đổi `GET` thành `POST /payments` và giữ retry loop y nguyên.
3. `maxAttempts=3` nghĩa là nhiều nhất 3 HTTP calls, không có backoff thứ ba sau khi nhận 200.
4. `BodyHandlers.ofString()` tiêu thụ body đầy đủ trước khi có response, tránh bỏ rơi streaming body từ failed attempt. Với body lỗi lớn, production nên dùng bounded response handling thay vì gom vô hạn.
5. `Retry-After: 0` là **0 giây**, nên delay được chọn dựa vào local deterministic jitter. Code trong demo **chỉ parse numeric header bằng Long.parseLong**, **không phải parser production**; nếu server gửi HTTP-date hoặc số quá lớn, cần utility ở phần 5.
6. `Math.max(localJitter,serverMinMillis)` không cắt bớt server wait; trong production còn phải so với **remaining total deadline** trước khi sleep.
7. `Thread.sleep` ở đây dùng vài milliseconds trong one-off console test. Không dùng một worker thread cho mỗi queued retry khi có hàng chục nghìn clients; dùng scheduler/backpressure.
8. Request có `HttpRequest.Builder.timeout(Duration.ofSeconds(3))` cho mỗi attempt, nhưng **không đặt tổng deadline cho cả loop**. Đây là demo minh họa count/status/backoff, không phải retry utility đầy đủ. Mẫu async ở phần 11 thể hiện **totalBudget + watchdog**.

Nếu runtime không có module `jdk.httpserver`, hoặc sandbox không cho bind loopback, chương trình có thể ném lỗi environment. Không cần Internet, DNS ngoài hoặc credentials.

## 10. Backoff bất đồng bộ: vì sao không block thread chờ retry?

Một anti-pattern cho server tải lớn:

~~~java
// Mỗi request trên một worker thread:
while (shouldRetry) {
    Thread.sleep(delayMillis);
    callRemoteService();
}
~~~

Đây là **pseudocode** với `shouldRetry`, `delayMillis` và `callRemoteService` không định nghĩa. Nếu 5.000 requests cùng tạm lỗi và mỗi thread ngủ 10 giây, hệ thống có thể cần rất nhiều blocked threads và memory stacks. Thay vào đó:

~~~text
HTTP async attempt #1
    |
 CompletableFuture exceptionally: transient
    |
 compute jitter + check deadline/count
    |
 ScheduledExecutorService.schedule(nextAttempt, wait)
    |   (không chiếm thread trong lúc đợi)
    v
HTTP async attempt #2
    |
 complete success/failure
~~~

`ScheduledExecutorService.schedule(Runnable,delay,unit)` lên lịch chạy **sau delay tương đối** và trả `ScheduledFuture` có thể cancel. Một scheduler thread có thể quản lý nhiều scheduled tasks, nhưng **scheduler queue vẫn tiêu thụ bộ nhớ**; giới hạn số outstanding retries và không enqueue vô hạn.

Mỗi logical operation cần:
- Một `CompletableFuture<Result>` trả cho caller.
- Một state giữ `attemptNumber` và monotonic deadline.
- Một reference tới in-flight HTTP future để cancel khi caller bỏ yêu cầu.
- Một scheduled timer của attempt kế tiếp và **watchdog total budget**.
- Một nguồn randomness injectable để kiểm thử (hoặc fixed test sampler).
- Một policy phân loại status/exception **trước** khi lên lịch retry.
- Shutdown rõ ràng để không giữ scheduler threads sau ứng dụng dừng.

Không dùng `scheduleAtFixedRate` hay `scheduleWithFixedDelay` như timer chung cho mỗi attempt request: đó là API công việc lặp **định kỳ**, dễ sinh nhiều attempts không liên quan completion request trước. Với retry, chọn **one-shot schedule** sau khi kết quả attempt đã được phân loại.

## 11. Ví dụ Java 17+ số 3: scheduler, bounded attempts, watchdog và cancel

Ví dụ này kiểm thử **state machine async** với một `Supplier<CompletableFuture<String>>`, không gọi network thật. Thử ba nhánh:

1. Hai attempts đầu hoàn thành `IOException("temporary")`; attempt 3 thành công `"ready"`.
2. Một operation luôn thất bại; `maxAttempts=2` làm nó dừng đúng 2 attempts và trả lỗi gốc.
3. Caller hủy operation đang chờ; cancellation được chuyển tới in-flight future.
4. Operation không bao giờ complete; **watchdog totalBudget** làm result kết thúc bằng `TimeoutException` và cancel underlying future.

Để stdout cố định, code dùng delay `cap/2` thay cho random thực; bản production thay sampler bằng full jitter từ phần 8. Code giới hạn `maxAttempts<=8` để việc shift trong demo không overflow; hệ thống thật có thể dùng hàm saturating ở phần 8 và policy attempts nhỏ.

Tạo file **`AsyncRetrySchedulerDemo.java`**:

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.Supplier;

public final class AsyncRetrySchedulerDemo {
    static CompletableFuture<String> retryAsync(
            Supplier<CompletableFuture<String>> action,
            ScheduledExecutorService scheduler,
            int maxAttempts,
            Duration totalBudget) {

        if (maxAttempts < 1 || maxAttempts > 8
                || totalBudget.isNegative()
                || totalBudget.isZero()) {
            throw new IllegalArgumentException(
                    "Invalid retry budget");
        }

        Objects.requireNonNull(action);
        Objects.requireNonNull(scheduler);

        long started = System.nanoTime();
        long allowedNanos = totalBudget.toNanos();
        CompletableFuture<String> result =
                new CompletableFuture<>();

        AtomicReference<CompletableFuture<String>> active =
                new AtomicReference<>();
        AtomicReference<ScheduledFuture<?>> waiting =
                new AtomicReference<>();

        ScheduledFuture<?> watchdog = scheduler.schedule(
                () -> result.completeExceptionally(
                        new TimeoutException(
                                "Total budget exceeded")),
                allowedNanos, TimeUnit.NANOSECONDS);

        class Runner {
            void attempt(int number) {
                if (result.isDone()) return;

                if (System.nanoTime() - started >= allowedNanos) {
                    result.completeExceptionally(
                            new TimeoutException(
                                    "Total budget exceeded"));
                    return;
                }

                CompletableFuture<String> current;
                try {
                    current = Objects.requireNonNull(
                            action.get());
                } catch (RuntimeException failure) {
                    current = CompletableFuture.failedFuture(
                            failure);
                }
                active.set(current);

                current.whenComplete((value, failure) -> {
                    if (result.isDone()) return;

                    if (failure == null) {
                        result.complete(value);
                        return;
                    }

                    Throwable cause =
                            failure instanceof CompletionException
                            ? failure.getCause()
                            : failure;

                    if (!(cause instanceof IOException)
                            || number == maxAttempts) {
                        result.completeExceptionally(cause);
                        return;
                    }

                    long capMs =
                            Math.min(80L,
                                    10L << (number - 1));
                    long delayMs = capMs / 2;
                    // Demo: deterministic test sample.

                    long remaining = allowedNanos -
                            (System.nanoTime() - started);
                    if (remaining <= TimeUnit.MILLISECONDS
                            .toNanos(delayMs)) {
                        result.completeExceptionally(
                                new TimeoutException(
                                        "No retry time left"));
                        return;
                    }

                    try {
                        waiting.set(scheduler.schedule(
                                () -> attempt(number + 1),
                                delayMs,
                                TimeUnit.MILLISECONDS));
                    } catch (RejectedExecutionException rejected) {
                        result.completeExceptionally(rejected);
                    }
                });
            }
        }

        result.whenComplete((value, failure) -> {
            watchdog.cancel(false);

            ScheduledFuture<?> timer =
                    waiting.getAndSet(null);
            if (timer != null) timer.cancel(false);

            if (result.isCancelled()
                    || failure instanceof TimeoutException) {
                CompletableFuture<String> call =
                        active.get();
                if (call != null) call.cancel(true);
            }
        });

        new Runner().attempt(1);
        return result;
    }

    public static void main(String[] args)
            throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        try {
            AtomicInteger started = new AtomicInteger();
            CompletableFuture<String> recovered =
                    retryAsync(() -> {
                        int attempt =
                                started.incrementAndGet();
                        System.out.println(
                                "async start=" + attempt);
                        return attempt < 3
                                ? CompletableFuture.failedFuture(
                                        new IOException("temporary"))
                                : CompletableFuture.completedFuture(
                                        "ready");
                    }, scheduler, 4,
                    Duration.ofSeconds(2));

            System.out.println(
                    "async result=" +
                    recovered.get(
                            3, TimeUnit.SECONDS));

            AtomicInteger failed = new AtomicInteger();
            CompletableFuture<String> stopped =
                    retryAsync(() -> {
                        failed.incrementAndGet();
                        return CompletableFuture.failedFuture(
                                new IOException(
                                        "still unavailable"));
                    }, scheduler, 2,
                    Duration.ofSeconds(2));

            try {
                stopped.get(3, TimeUnit.SECONDS);
            } catch (ExecutionException expected) {
                System.out.println(
                        "exhausted attempts=" +
                        failed.get());
                System.out.println(
                        "last error=" +
                        expected.getCause()
                                .getClass().getSimpleName());
            }

            CompletableFuture<String> never =
                    new CompletableFuture<>();
            CompletableFuture<String> cancelled =
                    retryAsync(() -> never,
                            scheduler, 4,
                            Duration.ofSeconds(2));
            cancelled.cancel(true);
            System.out.println(
                    "cancel reached in-flight: " +
                    never.isCancelled());

            CompletableFuture<String> neverEnds =
                    new CompletableFuture<>();
            CompletableFuture<String> timedOut =
                    retryAsync(() -> neverEnds,
                            scheduler, 1,
                            Duration.ofMillis(30));
            try {
                timedOut.get(1, TimeUnit.SECONDS);
            } catch (ExecutionException expected) {
                System.out.println(
                        "budget timeout: " +
                        expected.getCause()
                                .getClass().getSimpleName());
            }

            System.out.println(
                    "timeout cancelled in-flight: " +
                    neverEnds.isCancelled());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac --release 17 AsyncRetrySchedulerDemo.java
java AsyncRetrySchedulerDemo
~~~

Stdout **đã kiểm tra trên JDK cục bộ**:

~~~text
async start=1
async start=2
async start=3
async result=ready
exhausted attempts=2
last error=IOException
cancel reached in-flight: true
budget timeout: TimeoutException
timeout cancelled in-flight: true
~~~

**Cách code hoạt động:**

- `retryAsync` tạo một future **chung cho cả logical operation**, không trả một future mới cho từng attempt ra caller.
- `Runner.attempt(1)` gọi supplier một lần. Khi future hoàn thành lỗi `IOException`, callback kiểm tra số attempts/budget rồi dùng `scheduler.schedule(...)` để khởi động attempt kế tiếp **sau delay**. Trong khoảng chờ, không có thread bị block bởi `sleep`.
- `watchdog` lên lịch một lần với `totalBudget`. Nếu một in-flight future không bao giờ complete, watchdog **vẫn có thể chấm dứt operation**; check remaining budget trước retry không đủ để bắt một future treo vĩnh viễn.
- Khi `result` hoàn thành, callback cancel watchdog/timer. Với caller cancellation hoặc timeout, nó cố cancel in-flight future. Với `HttpClient.sendAsync` thật, cancel là **best-effort**, server vẫn có thể đã xử lý request.
- Trong test, `CompletableFuture.failedFuture(new IOException(...))` giả lập lỗi transient; **không nên biến toàn bộ IOException ở production thành retryable**. Cần áp policy từ phần 7.
- `result.completeExceptionally(lastError)` bảo tồn nguyên nhân cuối khi hết attempts. `get()` bọc cause bằng `ExecutionException`; caller phải bóc cause.
- `retryAsync` có giới hạn số attempts và deadline; **chưa** giới hạn số lượng *logical calls* đồng thời hoặc độ dài scheduler queue. Khi áp dụng production, bổ sung semaphore/global retry budget và metrics.
- `then/whenComplete` callbacks có thể chạy trên thread hoàn thành future hoặc scheduler; không chạy blocking work trong callback.
- `Duration.toNanos()` có thể overflow với duration khổng lồ; ví dụ dùng durations hợp lý ≤ vài giây. Production validate upper bound trước chuyển đổi.
- `AtomicReference` cho phép chia sẻ handles giữa scheduler/callback/caller; logic cleanup phải xét race khi completion/cancellation xảy ra gần đồng thời. Đây là ví dụ học state machine chứ **không phải một general-purpose retry framework đã chứng minh linearizability trên mọi race**.
- `scheduler.shutdownNow()` chỉ dùng vì chương trình console sở hữu executor. Trong server, truyền scheduler có lifecycle tập trung; không tạo/destroy một thread pool trên từng retry.

### 11.1. Nối state machine async với HttpClient

Một integration ý tưởng:

~~~java
// Đoạn minh họa trong class có HttpClient client và HttpRequest req:
Supplier<CompletableFuture<HttpResponse<String>>> action =
        () -> client.sendAsync(
                req, HttpResponse.BodyHandlers.ofString());
~~~

Để dùng utility generic có kiểu `HttpResponse<String>`, điều chỉnh tham số kiểu và phân loại response **status** ở callback, thay vì chỉ failure exception. Một `HttpResponse` có status `503` vẫn là **successful CompletableFuture completion**, nên nếu chỉ retry khi `failure != null` như demo 3, nó **sẽ không thử lại 503**.

Thiết kế production nên trả một loại `AttemptOutcome<T>` phân biệt:
- `Success(value)`.
- `RetryableStatus(status, headers, bodyAlreadyConsumed)`.
- `RetryableTransportFailure(cause)`.
- `PermanentFailure(status/cause)`.

Dispatcher quyết định ở **một nơi duy nhất** trước khi schedule, để tránh mỗi caller tự retry khác nhau và tạo retry storms.

### 11.2. Cancel futures và deadline

Javadoc Java 17 cho `HttpClient.sendAsync` nêu default implementation trả cancelable futures. `cancel(true)` trên future chưa hoàn thành sẽ **cố** cancel HTTP exchange để giải phóng resources, nhưng **không có bảo đảm chính xác lúc nào**. Với HTTP/1.1 nó có thể đóng connection; với HTTP/2 nó có thể reset stream. Điều này không đảm bảo server chưa xử lý. Nếu operation có idempotency key, retry/reconciliation vẫn phải theo business contract.

Một coroutine/reactive implementation cũng cần cùng quy tắc: khi downstream caller cancel, cancel scheduled retry timer, in-flight HTTP attempt và any retained body buffers; không hồi sinh work đã bị hủy.

## 12. Backoff không giải quyết overload nếu retry nhiều lớp

Giả sử một request đi qua:

~~~text
Web UI -> API Gateway -> Service A -> Service B -> Database
                 │          │          │          │
              3 attempts  3 attempts  3 attempts  3 attempts
~~~

Nếu cả bốn lớp tự retry mỗi downstream call tối đa 3 lần, worst-case số operations ở đáy **có thể nhân thành 3×3×3×3 = 81** cho một logical user request (bỏ qua các giới hạn khác). Chỉ có jitter ở từng lớp chưa giải quyết retry amplification.

Một chiến lược tốt:
1. Xác định **retry owner** ở tầng phù hợp nhất, hoặc một số lớp rất có chủ đích.
2. Chuyển **deadline context** xuống các downstream calls; không cấp lại tổng budget mới vô hạn ở mỗi hop.
3. Dùng **retry budget per service/tenant** (token bucket hoặc tỉ lệ retries/initial calls).
4. Tôn trọng `Retry-After`, server overload/quota hints và circuit breaker.
5. Bounded concurrency + queue + load shedding; không làm một service đang quá tải nhận thêm retries hơn initial traffic.
6. Không retry từ tầng UI khi backend vẫn đang retry nếu không có contract rõ.
7. Truyền correlation ID để nhận diện **attempt 2 của cùng logical call**, không coi là một transaction mới độc lập.

### 12.1. Retry budget khác maxAttempts

`maxAttempts=4` bảo vệ **một logical operation**. Nhưng nếu 100.000 logical operations đồng thời đều retry 3 lần, service vẫn có 300.000 extra requests. **Retry budget tổng thể** bảo vệ cấp system/tenant, ví dụ tối đa 20% requests được phép là retries trong cửa sổ đo lường (giá trị chỉ minh họa).

Cách tính minh họa:

~~~text
Trong một khoảng quota:
  initial attempts = 1000
  retry tokens max = 200
  retries đã dùng = 200

Một logical request còn maxAttempts nhưng không còn retry token:
  -> fail/defer theo policy, không gọi thêm network.
~~~

Có thể dùng token bucket với refill được kiểm soát, có jitter và randomness độc lập, không tự động queue mọi request vô hạn. Tránh tạo retry tokens dựa trên thành công bị méo bởi retries mà không nghĩ tới feedback loop.

### 12.2. Circuit breaker, rate limiter và retry không thay nhau

| Cơ chế | Vai trò |
| --- | --- |
| Bounded retry | Tăng cơ hội qua lỗi ngắn hạn với chi phí có hạn |
| Exponential backoff | Giãn khoảng thử theo số lần thất bại |
| Jitter | Phá sự đồng bộ giữa nhiều retry clients |
| Total deadline/timeout | Không giữ logical operation quá lâu |
| Rate limiting | Giới hạn lưu lượng theo thời gian/tenant |
| Concurrency limiter/bulkhead | Không cho vượt số in-flight/threads/sockets |
| Circuit breaker | Tạm dừng gọi dependency có tỉ lệ lỗi cao |
| Idempotency/dedup | Giảm rủi ro lặp tác động nghiệp vụ |
| Cache/fallback | Có thể phục vụ dữ liệu thay thế khi dependency lỗi (nếu nghiệp vụ cho phép) |

**Retry không phải “bật là khỏe hơn”**: khi downstream quá tải, thêm attempts có thể tăng độ trễ và tỉ lệ thất bại. Nếu circuit đã open, retry attempts cần bị chặn theo circuit policy.

## 13. Các tình huống cần suy nghĩ kỹ

### 13.1. `429 Too Many Requests` và server có quota 60 giây

Nếu nhận:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
~~~

Mà deadline user chỉ còn 3 giây, **không** nên retry sau 200ms vì jitter local thấp. Dừng và trả failure/quota response phù hợp hoặc giao công việc cho job queue có deadline dài được kiểm soát. Đừng giữ request thread/connection vô hạn để chờ 60s.

### 13.2. Kết nối đứt sau khi POST chuyển tiền

Client có thể đã gửi payload, server đã commit và đang trả response thì TCP reset. Client thấy exception nhưng không biết transaction đã xảy ra. **Không retry POST mù**, kể cả nếu delay rất dài. Cần idempotency key, server lookup/reconciliation hoặc event id để xác minh trạng thái. Jitter chỉ giúp phân tán tải, không giảm duplicate side effects.

### 13.3. DNS `UnknownHostException`

Nếu domain sai chính tả, retry hàng trăm lần không giúp. Nếu một service discovery tạm lỗi thì có thể retry ít theo policy, nhưng phải có DNS timeout và kiểm tra fallback; không đặt tất cả `IOException` vào retry bucket mà bỏ qua cấu hình.

### 13.4. Response body bị streaming giữa chừng

Nếu body handler trả `InputStream` từ `HttpClient`, response future có thể hoàn thành **khi headers đến** dù body chưa EOF. Nếu sau đó đọc body ném `IOException`, retry yêu cầu:
- Đóng/cancel body cũ, tránh resource leak.
- Xác định toàn bộ request có thể replay hay không.
- Xác định downstream consumer có nhận một phần dữ liệu rồi tạo side effects hay chưa; nếu có phải rollback/offset/dedupe.
- Xóa file output temp/partial bytes hoặc resume bằng HTTP Range/ETag nếu protocol cho phép, thay vì append trùng byte.
- Tổng deadline và attempt budget vẫn áp dụng.

Dùng `BodyHandlers.ofString()` trong demo để đơn giản hóa vì body rất nhỏ và được tiêu thụ trước khi return.

### 13.5. Authentication/token hết hạn

Khi nhận `401`, thường cần **refresh credential theo auth contract**, không retry y nguyên token 5 lần. Khi refresh, tránh nhiều threads cùng refresh bằng single-flight logic có giới hạn. Không log tokens hoặc bypass TLS verification để “sửa” lỗi HTTP.

### 13.6. Timeout vs request vẫn đang xử lý

Client timeout sau 2 giây trong khi server cần 3 giây. Nếu lập tức retry, server có thể xử lý hai tác vụ cùng lúc. Với REST reads idempotent, có thể chấp nhận tăng tải nhưng cần retry budget; với writes phải có idempotency token. Không xem timeout là tín hiệu server đã hủy tác vụ.

### 13.7. Đóng ứng dụng hoặc user hủy thao tác

Khi ứng dụng shutdown, scheduled retries phải được cancel; không đợi hết `maxAttempts`. Với Java `InterruptedException`:

~~~java
try {
    Thread.sleep(delayMillis);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw interrupted;
}
~~~

Đây là **đoạn minh họa trong method `throws InterruptedException`** với `delayMillis` đã biết. Không nuốt interrupt rồi retry tiếp, vì user/shutdown đã yêu cầu dừng.

## 14. Tuning policy dựa vào SLA và tải, không có con số thần kỳ

Thông số sau là **ví dụ cấu hình khởi điểm để thảo luận**, không phải thông số bắt buộc cho mọi service:

| Loại thao tác | maxAttempts | baseDelay | maxBackoff | Total deadline | Gợi ý |
| --- | ---: | ---: | ---: | ---: | --- |
| GET read nhẹ từ dependency nội bộ | 3 | 50ms | 500ms | 2s | Full jitter, per-attempt timeout theo RTT |
| GET external API bị quota | 2–3 | 500ms | 5s | Theo SLA/quota | Ưu tiên Retry-After; quota quá dài thì defer |
| Background job có khả năng idempotent | 4–6 | 1s | 30s | Theo job deadline | Jitter và persistent queue có giới hạn |
| POST financial command không có dedup | 1 | — | — | Theo business SLA | Không retry tự động |
| POST idempotency key được backend hỗ trợ | Theo hợp đồng | Theo SLA | Có cap | Theo deadline | Same key/payload, reconcile ambiguous results |
| Health checks | 1–2 | Ngắn | Ngắn | Rất ngắn | Không tạo retry storm làm health service quá tải |

**Không tự sao chép các con số** mà chưa đo p50/p95/p99 latency, error duration, quota limits, server capacity, connection pooling, user-facing timeout và downstream retry ownership.

Backoff quá ngắn sẽ gây load spike; quá dài làm latency cao và bỏ lỡ khả năng recovery; `maxAttempts` quá lớn làm request amplification. Jitter hợp lý giúp giảm sự đồng bộ nhưng không thay capacity planning.

### 14.1. Lấy thông số từ telemetry

Quan sát:
- Tỉ lệ transient failures và thời gian server phục hồi.
- Thời gian một attempt thành công/thất bại; p95/p99.
- Distribution `Retry-After` (mức thấp/cao/không có).
- Số retries per logical operation và fraction thành công sau retry.
- Tổng requests do retries sinh ra.
- Queue age/concurrency/memory/cancel counts.
- Số business duplicates/idempotency conflicts.
- Số failures vì hết attempts vs hết deadline vs hết retry budget.

Đối với downstream hay có 503 kéo dài 20 phút, retry trong HTTP request đồng bộ 30 giây không đúng kiến trúc; nên dùng job queue, circuit breaker và deferred processing theo nghiệp vụ.

## 15. Logging và metrics không làm mất ý nghĩa của attempts

Một retry-friendly log nên có:
- `logicalRequestId` / trace ID xuyên suốt **một logical operation**.
- `attemptNumber` và `maxAttempts`.
- `httpMethod`, sanitized target service/operation (không log access tokens).
- `retryDecision`: success, retryable_status, transient_io, permanent, exhausted, deadline, cancelled, circuit_open.
- `backoffCapMillis`, `selectedJitterMillis` và `retryAfterMillis` (nếu có), `effectiveWaitMillis`.
- `elapsedMillis`, `remainingBudgetMillis`.
- `requestBodyReplayable` hoặc idempotency policy (không log toàn bộ body).
- Correlation với server `429/503` và service-side rate limiter metrics.

Metrics hữu ích:

| Metric | Công dụng |
| --- | --- |
| `request_initial_total` | Lượng logical calls ban đầu |
| `retry_attempt_total` | Số extra attempts, phân loại reason |
| `retry_exhausted_total` | Hết số lần thử |
| `retry_deadline_total` | Hết tổng thời gian |
| `retry_budget_rejected_total` | Retry bị từ chối bởi token/concurrency budget |
| `retry_cancelled_total` | Caller/shutdown hủy |
| `retry_delay_ms` histogram | Độ phân tán các lần đợi |
| `retry_success_after_attempt` | Giá trị phục hồi thực sự của retries |
| `inflight_dependency_requests` | Bảo vệ concurrency |
| `server_429_total` / `server_503_total` | Dấu hiệu quota/overload |
| `idempotency_dedup_total` | Phát hiện retries writes được backend deduplicate |

Đừng coi **retry success rate** là performance tốt nếu mỗi success đòi thêm nhiều requests và tăng total latency. Theo dõi tỷ lệ success **trên logical operation** cùng tổng work/amplification và tail latency.

## 16. Checklist test bounded retry

### 16.1. Unit tests deterministic

1. `maxAttempts=1`: đúng **một** call, không sleep.
2. `maxAttempts=3`: đúng **nhiều nhất 3 calls**, tối đa 2 delays.
3. Kiểm tra exponential sequence với cap: base=100ms, max=500ms → 100,200,400,500,500...
4. Full jitter luôn nằm trong `0..cap`; test RNG injectable với fixed function/seed.
5. Saturating arithmetic không overflow với attempt lớn.
6. `Retry-After: 120` được đọc là 120 **giây**, không 120ms.
7. `Retry-After` HTTP-date đã qua → wait 0; tương lai → wait dương.
8. `Retry-After` cực lớn hơn total budget → **không retry sớm**.
9. Retryable status 503/429 được phân loại; nonretry 400/401/403/404 không lặp.
10. Network failure ambiguous với POST không idempotency → không retry.
11. BodyPublisher không replayable → fail/defer, không gửi lại stream đã EOF.
12. Deadline hết trước scheduled attempt → không tạo network call mới.
13. Watchdog hết trong khi in-flight treo → result timeout/cancel underlying.
14. Caller cancel giữa lúc sleep/scheduled timer → timer canceled, không gọi attempt tiếp.
15. Lỗi scheduler `RejectedExecutionException` → result fail, không treo.
16. Thử nhiều concurrent callers: total retries/throttled queue nằm trong budget.

### 16.2. Integration tests

Dựng HTTP loopback/mock server và kịch bản:
- 503→503→200 với Retry-After 0: đúng 3 calls và thành công.
- 503 mãi: dừng ở `maxAttempts`, không sleep sau lần cuối.
- 429 với Retry-After 60 trong deadline 2s: dừng, không gửi lại.
- 404 cố định: 1 call.
- Response body quá lớn/cancel trong streaming: đóng resources sạch.
- Network reset sau khi server nhận POST: idempotency key giúp không duplicate.
- Hai hundred clients gặp 503 cùng lúc: jitter giảm clustering, quan sát request distribution.
- Downstream circuit open: không tự retry ở nhiều tầng.
- Load test với retry budget: khi server overloaded, extra attempts bị giới hạn.
- Sau khi client đóng, không còn scheduled retries/inflight tasks tồn tại ngoài policy.

Trong môi trường test, dùng clocks/RNG được inject và virtual/mock scheduler nếu có để unit tests nhanh và không flaky. Với integration dùng wall time thật, phải đặt timeout đủ rộng cho CI nhưng vẫn bound; không rely vào sleep chính xác đến từng millisecond trên OS.

## 17. Những lỗi phổ biến nhất

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `while(true)` retry vô hạn | Flood server, treo user request | maxAttempts + totalDeadline |
| Đếm `maxRetries` như `maxAttempts` | Gửi dư một lần | Định nghĩa counter rõ ràng |
| Sleep sau attempt cuối | Chậm vô ích | Chỉ sleep khi `attempt < maxAttempts` |
| Exponential không cap | Delay/overflow lớn | Capped saturating arithmetic |
| Không jitter | Clients thức dậy đồng loạt | Full jitter/equal/decorrelated theo policy |
| `random.nextLong(cap)` rồi nghĩ có thể trả cap | Bound exclusive | `nextLong(cap + 1)` với cap an toàn |
| Cộng jitter vào capped delay mà không recalc cap | Vượt maxBackoff local | Dùng full jitter trong `0..cap` |
| Retry dưới `Retry-After` minimum | Vi phạm rate-limit hint | `max(clientDelay,serverMinimum)` |
| Đổi `Retry-After: 30` thành 30ms | Retry sớm 1000 lần | Parse seconds/HTTP-date đúng |
| Cắt server hint 60s xuống maxBackoff 2s | Không tôn trọng peer quota | Dừng/defer nếu > total budget |
| Retry mọi `IOException` | Retry DNS/config/TLS/body file lỗi | Classify exception và context |
| Retry mọi HTTP 5xx | Có thể lặp permanent server failures | Status allowlist per endpoint |
| Retry POST không có idempotency | Duplicate writes/payment | Idempotency/reconcile/không retry |
| Reuse `InputStream` đã đọc cho upload | Gửi body rỗng/partial | New stream mỗi attempt, immutable payload |
| Coi timeout = server chưa xử lý | Lặp side effect | Idempotency key, ambiguity handling |
| Chỉ per-attempt timeout, không total deadline | Tổng thời gian = nhiều attempts × timeout + sleep | Monotonic total budget/watchdog |
| `Thread.sleep` trên event loop | Starvation, throughput thấp | ScheduledExecutorService/async |
| Tạo một scheduler trên mỗi request | Thread/resource explosion | Shared bounded scheduler |
| Nhiều layers cùng retry | Amplification cấp số nhân | Chọn retry owner, shared deadline |
| Không giới hạn retry queue | Memory tăng khi server down | Token/concurrency budget, bulkhead |
| Quên cancel in-flight khi caller hủy | Network work không còn cần | Propagate best-effort cancel |
| Suppress `InterruptedException` | Shutdown không dừng | Propagate/restore interrupt |
| Ghi mọi attempt như logical transaction mới | Metric/tracing méo, duplicate risk | Correlation ID + attempt number |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `maxAttempts=4` có tối đa bao nhiêu retries?  
**Đáp án:** 3 retries sau initial attempt, tổng 4 network calls.

**Câu 2.** Base 100ms, cap 500ms: capped exponential sau lần lỗi thứ 4 là bao nhiêu?  
**Đáp án:** `min(500,100×2^3)=500ms`.

**Câu 3.** Full jitter với cap=500ms có thể cho ra 0ms không?  
**Đáp án:** Có. Với nhu cầu delay tối thiểu, kết hợp policy/server hints.

**Câu 4.** Vì sao 1000 clients dùng fixed 100ms backoff dễ gây vấn đề?  
**Đáp án:** Thức dậy đồng loạt, tạo request spikes; jitter phân tán các lần thử.

**Câu 5.** Server trả `Retry-After: 30` thì nên chờ tối thiểu bao lâu?  
**Đáp án:** Khoảng 30 giây, không phải 30 millisecond.

**Câu 6.** Server yêu cầu chờ 60s, total deadline còn 2s. Có nên clamp wait thành 2s rồi retry?  
**Đáp án:** Không. Nên dừng/defer, không phá server minimum.

**Câu 7.** `HttpClient.send` nhận response `503` có tự ném IOException không?  
**Đáp án:** Không chỉ vì status 503. Phân loại bằng `response.statusCode()`.

**Câu 8.** `POST /payment` gặp timeout, có chắc server chưa thu tiền không?  
**Đáp án:** Không; cần idempotency key/reconciliation hoặc không tự retry.

**Câu 9.** GET có thể retry an toàn khi upstream mất kết nối nhưng file response đang ghi dở?  
**Đáp án:** Có thể theo API semantics, nhưng cần dọn/truncate partial output trước khi bắt đầu từ đầu hoặc resume có kiểm soát.

**Câu 10.** Có nên dùng `Thread.sleep` trong HTTP async callback của server nhiều requests?  
**Đáp án:** Không; sử dụng scheduler, bounded concurrency và cancellation.

**Câu 11.** Jitter và backoff có thay timeout không?  
**Đáp án:** Không. Mỗi attempt và toàn logical operation cần deadline.

**Câu 12.** `HttpRequest.BodyPublishers.ofInputStream` có nên supplier trả lại một InputStream đã đọc hết?  
**Đáp án:** Không. Mỗi subscription/attempt cần stream mở mới cùng payload.

**Câu 13.** Ba tầng có mỗi tầng 3 attempts thì tối đa có thể nhân bao nhiêu lần gọi ở đáy?  
**Đáp án:** 27 trong mô hình lồng không có giới hạn khác; cần tránh multi-layer amplification.

**Câu 14.** Retry delay đã được schedule mà user cancel request, phải làm gì?  
**Đáp án:** Cancel scheduled timer và in-flight operation (best-effort); không tạo attempt mới.

**Câu 15.** `maxAttempts` đã hết nhưng server vẫn 503, có sleep thêm lần cuối không?  
**Đáp án:** Không; dừng và trả lỗi/response theo contract.

**Câu 16.** Vì sao metrics phải phân biệt initial attempts và retry attempts?  
**Đáp án:** Để đo amplification/overload, success per logical operation và thực chi phí hồi phục.

**Câu 17.** Nếu retry sau lỗi network không có response, làm sao biết đã xử lý write chưa?  
**Đáp án:** Không thể biết chỉ từ client exception; cần idempotency/reconciliation protocol.

**Câu 18.** Một CompletableFuture kết thúc bằng `CancellationException` có nên được retry như `IOException` transient?  
**Đáp án:** Không. Cancellation thường là yêu cầu dừng của caller hoặc hệ thống.

## 19. Checklist thiết kế retry trước khi production

1. **Định nghĩa đơn vị logic** của operation: requestId, attemptNo, side effects, caller deadline.
2. **Xác minh idempotency/replayability** trước mọi retry, đặc biệt POST/streaming upload.
3. **Phân loại rõ transient status/exception** theo endpoint, không `catch(Exception)` retry mù.
4. **Dùng maxAttempts rõ**, luôn bao gồm lần gửi đầu, không sleep sau lần cuối.
5. **Tính exponential theo số lần thất bại**, cap và saturating arithmetic để tránh overflow.
6. **Thêm jitter đúng phân phối**, unit test với RNG được inject; không dùng fixed delays production.
7. **Tôn trọng Retry-After** theo seconds/HTTP-date; nếu quá total budget thì dừng/defer.
8. **Giới hạn per-attempt timeout và total deadline** bằng monotonic elapsed/watchdog.
9. **Không block async event loops**; dùng one-shot ScheduledExecutorService và bounded queue.
10. **Hủy timer/in-flight request khi caller cancel**, propagate interruption và đóng response bodies.
11. **Tránh retry nhiều tầng**; dùng retry owner, token budget và bounded concurrency.
12. **Kết hợp rate limit, circuit breaker, bulkhead/backpressure** khi dependency thường xuyên quá tải.
13. **Log logical request ID và attempt number**, không lộ credentials/payload riêng tư.
14. **Theo dõi recovery value vs amplification cost**: retries, latency, quota/exhaustion, dedup.
15. **Test failures có kiểm soát**: 503→200, 429 Retry-After, permanent failure, deadline, cancellation, body replay và nhiều concurrent clients.
16. **Không hứa exactly-once** từ TCP/HTTP retry; business writes phải có idempotency semantics và reconciliation.

## Tài liệu tham khảo chuẩn

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): `9.2.2` idempotent methods, `10.2.3` Retry-After (HTTP-date hoặc seconds), `15.6.4` 503 Service Unavailable.
- [RFC 6585 — HTTP 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html#section-4): rate limiting và tùy chọn Retry-After.
- [AWS Architecture Blog — Exponential Backoff and Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/): full/equal/decorrelated jitter và thundering herd khi các clients cạnh tranh.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, cancellation semantics.
- [Java SE 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): `timeout(Duration)` và request construction.
- [Java SE 17 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): request body replayability và `ofInputStream(Supplier)`.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): `statusCode()` và response headers.
- [Java SE 17 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): `schedule` one-shot delayed tasks và `ScheduledFuture`.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion, `failedFuture`, `whenComplete` và cancel.
- [Java SE 17 — ThreadLocalRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): `nextLong(bound)` để chọn full jitter trong bounded range.
- [Java SE 17 — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html) và [System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): quản lý elapsed time/budget.

**Kết luận:** Một client bền vững không đơn thuần “retry ba lần”. Nó phải hỏi **có nên retry hay không**, **có lặp lại an toàn hay không**, và **còn ngân sách thời gian/tài nguyên hay không**. Khi cần retry, dùng **capped exponential backoff + jitter**, tôn trọng server `Retry-After`, kết thúc rõ ràng và không để retry storm làm hệ thống đang lỗi trở nên quá tải hơn.

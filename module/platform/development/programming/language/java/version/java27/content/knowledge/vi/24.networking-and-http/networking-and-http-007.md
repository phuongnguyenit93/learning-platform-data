# Retry, backoff và idempotency khi gọi dịch vụ ngoài trong Java 27

Trong hệ thống phân tán, một lời gọi HTTP có thể thất bại vì **kết nối tạm thời gián đoạn**, **dịch vụ bị quá tải**, **giới hạn tốc độ**, hoặc **client hết thời gian chờ**. Thử lại (*retry*) có thể phục hồi lỗi thoáng qua nhưng cũng có thể nhân đôi tác dụng phụ, tạo *retry storm* và khiến hệ thống đang quá tải trở nên tệ hơn.

Bài học thuộc chương **Mạng và HTTP** của Java 27, tập trung vào ba quyết định có liên quan chặt chẽ:

1. **Có được phép thử lại không?** Xét HTTP method, semantics nghiệp vụ, trạng thái phản hồi và khả năng phát lại request body.
2. **Thử lại lúc nào và bao nhiêu lần?** Dùng **exponential backoff**, **jitter**, `Retry-After`, giới hạn số lần và deadline chung.
3. **Thử lại có làm lặp giao dịch không?** Thiết kế **idempotency** cho những hành động gây side effect như tạo đơn, thu tiền và gửi lệnh.

Các ví dụ sử dụng `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`, `Duration` và `ThreadLocalRandom` — đều là Java SE API ổn định trong **Java 27**, không cần `--enable-preview`. Kiến thức được đối chiếu với Javadoc Java SE 27 và HTTP Semantics **RFC 9110**. Bài không khuyến nghị cơ chế I/O hoặc thư viện HTTP đã lỗi thời.

## 1. Retry giải quyết lỗi gì và tạo rủi ro gì?

Một hệ thống gồm client và server có thể gặp tình huống:

```text
Client                        Network                      Server
  |-------- POST /orders -------->|-------------------------->|
  |                               |                           | commit order
  |<--------- response -----------X   (connection breaks)     |
  | timeout / IOException         |                           |
  |                                Không biết server đã commit hay chưa
  |-------- POST /orders -------->|-------------------------->| duplicate?
```

Client **không nhận được response** không đồng nghĩa server **chưa xử lý request**. Nếu lệnh ban đầu đã commit, gửi lại một `POST` tạo đơn với ID tự sinh ở server có thể tạo **hai đơn**.

Phân loại các tình huống:

| Tình huống | Có thể thử lại? | Điều kiện cần |
| --- | --- | --- |
| Mất kết nối, connect timeout với GET | Thường có | GET thực sự có semantics an toàn; còn ngân sách thời gian |
| `503 Service Unavailable` | Có thể | Tôn trọng `Retry-After`, giới hạn lần thử, không làm lặp side effect |
| `429 Too Many Requests` | Có thể | Tôn trọng chỉ dẫn rate limit và `Retry-After`; không tăng tải đột ngột |
| `502 Bad Gateway` / `504 Gateway Timeout` | Có thể | Đánh giá lỗi tạm thời, operation có thể phát lại an toàn |
| `400 Bad Request` / `422 Unprocessable Content` | Thường không | Cần sửa input thay vì lặp lại cùng request |
| `401 Unauthorized` / `403 Forbidden` | Không retry mù quáng | Xử lý xác thực/quyền; làm mới thông tin đăng nhập theo hợp đồng riêng |
| `404 Not Found` | Thường không | Chỉ retry nếu nghiệp vụ có **eventual consistency** được ghi rõ |
| `409 Conflict` | Không mặc định | Có thể là conflict do duplicate đang xử lý; phải theo contract API |
| Mất response của `POST` thanh toán | **Không** nếu chưa có bảo đảm idempotency | Cần key và server-side deduplication hoặc xác minh trạng thái giao dịch |

**Retry là quyết định nghiệp vụ**, không phải “bắt mọi Exception rồi gọi lại”. Một thuật toán retry tốt phải có điều kiện dừng và khả năng giải thích **vì sao** một request được phát lại.

## 2. HTTP safe và idempotent: nền tảng của quyết định retry

### 2.1. Safe khác idempotent

Theo **RFC 9110 §9.2**:

- **Safe method:** client không yêu cầu thay đổi trạng thái của tài nguyên như một tác dụng chủ đích. `GET`, `HEAD` và `OPTIONS` là ví dụ safe; server vẫn có thể ghi log, metric hoặc các tác dụng phụ phụ trợ.
- **Idempotent method:** thực hiện **nhiều lần cùng một request** có **hiệu quả dự định trên server giống một lần**. Safe methods, `PUT` và `DELETE` là idempotent theo định nghĩa HTTP.
- **Non-idempotent mặc định:** `POST` và `PATCH` không có bảo đảm idempotent chung, dù một endpoint **cụ thể** có thể thiết kế để idempotent.

| Method | Safe theo HTTP? | Idempotent theo HTTP? | Hướng retry |
| --- | --- | --- | --- |
| `GET` | Có | Có | Thích hợp để retry lỗi thoáng qua nếu endpoint tuân thủ semantics |
| `HEAD` | Có | Có | Tương tự GET nhưng không yêu cầu response body |
| `OPTIONS` | Có | Có | Chỉ retry khi thực sự cần và server hỗ trợ |
| `PUT` | Không | Có | Có thể retry nếu nội dung là cùng trạng thái đích và hợp đồng endpoint phù hợp |
| `DELETE` | Không | Có | Có thể retry; status của lần thứ hai có thể khác lần đầu |
| `POST` | Không | Không mặc định | Chỉ retry khi có cơ chế bảo vệ idempotency hoặc chứng minh request chưa áp dụng |
| `PATCH` | Không | Không mặc định | Chỉ retry nếu patch operation được thiết kế idempotent và có bảo đảm phù hợp |

Ví dụ:

- `PUT /profiles/42` với cùng đại diện đầy đủ thường đưa tài nguyên về **cùng trạng thái đích**. Lần đầu có thể trả `201`, lần sau `200` hoặc `204`; **status không nhất thiết giống nhau**.
- `DELETE /records/42` có thể trả `204` lần đầu và `404` lần sau, nhưng hiệu quả mong muốn “record không còn tồn tại” không đổi.
- `POST /payments` có thể tạo một giao dịch mới **mỗi lần nhận** nếu API không có idempotency key.

**Lưu ý:** idempotent không đồng nghĩa **exactly-once execution**. Server có thể thực thi xử lý lặp lại và tạo log/metric khác nhau; điều được bảo đảm ở cấp semantics là **hiệu quả dự định** của các request tương đương.

### 2.2. Không chỉ kiểm tra tên HTTP method

Ngay cả một method được RFC định nghĩa là idempotent, cần đảm bảo ứng dụng có contract đúng. Ví dụ endpoint sử dụng GET để tăng lượt xem hoặc kích hoạt job là một thiết kế không tuân thủ safe semantics; áp dụng retry chung sẽ gây hành vi khó đoán.

Với `PUT`, payload, điều kiện cập nhật, resource ID và các header liên quan phải **được giữ nhất quán** giữa các lần thử. Dùng `If-Match`/ETag nếu cần bảo vệ không ghi đè các cập nhật đồng thời. Retry một thao tác idempotent vẫn có thể tác động đến **các thao tác của client khác** nếu không có chiến lược concurrency control.

## 3. Phân loại HTTP status và IOException

### 3.1. Chính sách retry có chọn lọc

Một chính sách **minh họa** cho thao tác GET:

```java
static boolean retryableStatus(int status) {
    return status == 429
        || status == 502
        || status == 503
        || status == 504;
}
```

Đây là **chính sách ứng dụng**, không phải một danh sách bắt buộc do `HttpClient` tự áp dụng.

- **429**: bị giới hạn tốc độ; cần giảm tốc độ và tôn trọng `Retry-After` khi có.
- **502**: proxy/gateway nhận phản hồi không hợp lệ từ upstream; có thể thoáng qua.
- **503**: quá tải hoặc bảo trì; có thể có thời gian đề nghị thử lại.
- **504**: gateway chờ upstream quá hạn; cần đặc biệt cảnh giác: upstream có thể đã xử lý request trước khi phản hồi bị mất.

`408 Request Timeout` và một số lỗi `5xx` khác có thể retry trong **một chính sách cụ thể**, nhưng không nên cộng vào mặc định mà chưa đánh giá semantics. `500` không luôn là lỗi thoáng qua. Không thử lại vô hạn với `404`, `401`, `403`, `409` hay mọi `4xx`.

### 3.2. Không retry tất cả IOException

`HttpClient.send(...)` có thể ném `IOException` khi gặp lỗi I/O. Nhưng nhiều lỗi **không** nên lặp lại:

- Chứng chỉ TLS không hợp lệ (`SSLHandshakeException`), cấu hình TLS sai: không sửa được bằng retry thông thường.
- Host/URL không hợp lệ, DNS không thể phân giải do cấu hình sai: kiểm tra môi trường.
- Kết nối bị từ chối, connect timeout, request timeout: có thể chỉ là lỗi thoáng qua, nhưng cần chính sách giới hạn.
- Kết nối bị đóng khi request đang truyền: server có thể đã xử lý toàn bộ hoặc một phần; **không** tự retry POST thiếu bảo đảm.

Trong ví dụ GET, ta chỉ bắt và retry **`HttpTimeoutException` và `ConnectException`**. Những `IOException` khác sẽ được chuyển tiếp để caller xem xét — **không** có logic `catch (IOException e) { retry... }` áp dụng cho mọi lỗi.

Java SE 27 ghi rõ khi thread đang thực hiện `HttpClient.send` bị **interrupted**, implementation mặc định **cố gắng** hủy HTTP exchange rồi ném `InterruptedException`; **không bảo đảm** request chưa được gửi hoặc server chưa xử lý. Vì vậy exception này cần được xử lý như tín hiệu cancellation, **không** tự động retry.

### 3.3. Response đã về không phải exception

`HttpClient.send(request, handler)` **không tự ném exception vì HTTP status là 429/503/404**. Response thành công ở tầng giao thức vẫn có `response.statusCode()` để ứng dụng phân loại. Không bao giờ suy luận rằng `send` không ném exception nghĩa là API nghiệp vụ thành công.

## 4. Backoff: vì sao không retry ngay lập tức?

Nếu 10.000 client cùng nhận 503 và retry ngay, server đang quá tải có thể hứng thêm 10.000 request cùng lúc. Đây là **retry storm/thundering herd**.

Một chiến lược thông dụng là **exponential backoff có giới hạn**:

```text
cap(n) = min(maxBackoff, baseDelay × 2^(n-1))
n = số lần thất bại liên tiếp (bắt đầu từ 1)
```

Với `baseDelay = 200 ms` và `maxBackoff = 3.000 ms`:

| Sau lần lỗi thứ | Cap backoff | Full jitter chọn ngẫu nhiên |
| --- | --- | --- |
| 1 | 200 ms | [0, 200] ms |
| 2 | 400 ms | [0, 400] ms |
| 3 | 800 ms | [0, 800] ms |
| 4 | 1.600 ms | [0, 1.600] ms |
| 5 trở đi | Tăng theo lũy thừa rồi chặn ở 3.000 ms | [0, 3.000] ms sau khi đạt cap |

`full jitter` chọn độ trễ ngẫu nhiên đều từ `0` đến cap hiện tại để các client không đồng loạt gửi lại request. Jitter là ngẫu nhiên **cho điều phối tải**, không phải secret; `ThreadLocalRandom` phù hợp, không cần `SecureRandom`.

### 4.1. Code tính bounded exponential full jitter

```java
import java.util.concurrent.ThreadLocalRandom;

static long jitterMillis(int failedAttempt) {
    if (failedAttempt < 1) {
        throw new IllegalArgumentException("failedAttempt must be >= 1");
    }

    long baseMillis = 200;
    long maxMillis = 3_000;

    // Giới hạn phép shift để không overflow.
    int shift = Math.min(failedAttempt - 1, 4);
    long cap = Math.min(maxMillis, baseMillis << shift);

    return ThreadLocalRandom.current().nextLong(cap + 1);
}
```

Khi `failedAttempt = 1`, thuật toán lấy ngẫu nhiên số mili-giây trong `[0,200]`. Sau nhiều lần, cap không lớn hơn `3_000 ms`. Đây là **full jitter**; có những biến thể khác như equal/decorrelated jitter và lựa chọn tùy workload.

### 4.2. Đừng dùng mỗi backoff để quản lý tải

Backoff chỉ giúp phân tán các lần thử. Cần thêm:

- **max attempts**: tránh vòng lặp vô hạn, ví dụ tối đa 4 lần **bao gồm lần đầu**.
- **total deadline**: giới hạn toàn bộ chuỗi thử và các lần nghỉ.
- **retry budget**: giới hạn phần trăm/tổng số retries trong hệ thống để tránh amplification.
- **rate limiter/bulkhead**: hạn chế kết nối và số call đồng thời đến dịch vụ ngoài.
- **circuit breaker** khi downstream đang lỗi kéo dài: tránh gửi thêm request gây áp lực.
- **metrics**: attempts, retryable status, backoff, budget exhausted, success-after-retry, cancellation.

Một retry policy quá hào phóng ở nhiều tầng có thể nhân số yêu cầu: 3 lần ở gateway × 3 lần ở service × 3 lần ở client thành **27 lượt** tại downstream cho một yêu cầu đầu vào. Nên chọn **tầng sở hữu retry**, hoặc phân bổ budget giữa các tầng.

## 5. Retry-After: khi server yêu cầu client đợi

**RFC 9110 §10.2.3** định nghĩa header `Retry-After` với hai cách biểu diễn:

```http
Retry-After: 120
```

Nghĩa là **đợi 120 giây** sau khi nhận response.

```http
Retry-After: Fri, 27 Nov 2026 14:00:00 GMT
```

Nghĩa là một thời điểm theo định dạng **HTTP-date**.

Server có thể dùng `Retry-After` với `503 Service Unavailable`, `429 Too Many Requests` (RFC 6585) hoặc một số phản hồi chuyển hướng theo semantics HTTP.

### 5.1. Ưu tiên chỉ dẫn server nhưng vẫn tôn trọng deadline

Khi retry một phản hồi có `Retry-After` hợp lệ, nên đợi **ít nhất** khoảng server yêu cầu. Nếu backoff theo jitter của client dài hơn, có thể đợi lâu hơn:

```text
wait = max(clientBackoffWithJitter, serverRetryAfter)
```

Nhưng nếu `wait` **lớn hơn ngân sách request còn lại**, **không** “cắt ngắn `Retry-After` rồi retry sớm” để kịp deadline. Thay vào đó, dừng retry và báo timeout/hết ngân sách cho caller hoặc lên lịch lại ở tầng phù hợp.

Những vấn đề cần xử lý:

- Header có thể vắng mặt hoặc không đúng định dạng → dùng backoff theo chính sách.
- `delay-seconds` có thể rất lớn → chặn overflow khi đổi sang nanosecond và ngừng nếu không đủ deadline.
- HTTP-date trong quá khứ → thời gian chờ từ server có thể coi bằng 0, vẫn dùng backoff của client.
- Giờ server/client có thể lệch → phải có chính sách clock skew; không suy đoán tuyệt đối.
- Nếu API quy định quota hoặc header rate limit riêng, cần theo hợp đồng cụ thể thay vì chỉ dùng một header này.

## 6. Deadline chung và timeout ở hai tầng HttpClient

Một lần retry cần cả **timeout kết nối** và **timeout request**:

```java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(java.time.Duration.ofSeconds(2))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();

HttpRequest request = HttpRequest.newBuilder(uri)
    .timeout(java.time.Duration.ofSeconds(5))
    .GET()
    .build();
```

- `HttpClient.Builder.connectTimeout(...)` đặt hạn cho việc **thiết lập kết nối mới**; không phải thời gian tối đa cho toàn bộ chuỗi requests.
- `HttpRequest.Builder.timeout(...)` đặt timeout **của một lần thực hiện request**. Theo Javadoc Java SE 27, timeout áp dụng ít nhất từ khi bắt đầu request đến khi response được dựng; **JDK implementation mặc định** áp dụng đến khi body subscriber hoàn tất.
- Dùng một `Duration.ofSeconds(5)` cho **mỗi lần** trong 4 attempts có thể dẫn tới tổng thời gian lớn hơn 5 giây, đặc biệt khi cộng backoff.

Do đó, hãy đo **thời gian đã trôi qua** bằng `System.nanoTime()` và truyền **ngân sách còn lại** cho mỗi lần gọi:

```text
deadline tổng: 5 giây
│
├── attempt 1: gửi request (2.2 s)
├── backoff:   đợi (0.2 s)
├── attempt 2: timeout tối đa phần còn lại (2.6 s)
└── trả kết quả hoặc dừng vì hết deadline
```

`System.nanoTime()` là đồng hồ phù hợp để đo thời gian trôi qua **trong cùng JVM**, không phải Unix timestamp và không nên truyền giá trị tuyệt đối này sang máy khác. Deadline giúp giới hạn ý định điều phối, **không** đảm bảo độ chính xác đến từng nano-giây của scheduler hay việc dọn tài nguyên ở tầng I/O.

### 6.1. Interruption không được bị nuốt

`Thread.sleep(...)` và `TimeUnit.NANOSECONDS.sleep(...)` đều có thể ném `InterruptedException`. Nếu request bị hủy khi đang backoff, nên **dừng chờ và chuyển tiếp** tín hiệu thay vì thử lại. Trong method khai báo `throws InterruptedException`, ưu tiên ném tiếp; chỉ khôi phục `Thread.currentThread().interrupt()` tại tầng không thể ném tiếp khi hợp đồng yêu cầu.

## 7. Ví dụ Java 27 hoàn chỉnh: GET với bounded retry, jitter và Retry-After

Chương trình sau là một client minh họa có thể biên dịch với Java 27. Nó chỉ retry **GET** và chỉ với các HTTP status hoặc loại lỗi mạng đã chọn. Để chạy, truyền URL HTTPS thực của API **do bạn quản lý/được phép gọi**; ví dụ không tự chạy request khi thiếu đối số.

**Các chính sách được cài đặt:**

- Tối đa **4 attempts** bao gồm lượt đầu.
- Tổng thời gian tối đa **5 giây** trong ví dụ `main`.
- Trước mỗi attempt, tạo `HttpRequest` mới với timeout bằng thời gian còn lại.
- Retry `429`, `502`, `503`, `504`.
- Với I/O, retry riêng `HttpTimeoutException` hoặc `ConnectException`; các lỗi I/O khác được ném ra ngoài.
- Full jitter với cap và ưu tiên `Retry-After` hợp lệ, không ngủ quá deadline.
- `InterruptedException` được chuyển lên caller; không retry khi bị hủy.
- Trả **HTTP status cuối cùng** nếu hết lượt thử; caller quyết định cách xử lý thành công/thất bại.

Lưu vào `ReliableGetDemo.java`:

```java
import java.io.IOException;
import java.net.ConnectException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.OptionalLong;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

public final class ReliableGetDemo {
    private static final int MAX_ATTEMPTS = 4;

    private ReliableGetDemo() {}

    static boolean retryableStatus(int status) {
        return status == 429 || status == 502
                || status == 503 || status == 504;
    }

    static long remainingNanos(long started, long budgetNanos) {
        return budgetNanos - (System.nanoTime() - started);
    }

    static long fullJitterNanos(int failedAttempt) {
        int shift = Math.min(failedAttempt - 1, 4);
        long capMillis = Math.min(3_000L, 200L << shift);
        long millis = ThreadLocalRandom.current().nextLong(capMillis + 1);
        return TimeUnit.MILLISECONDS.toNanos(millis);
    }

    static OptionalLong retryAfterNanos(String header) {
        if (header == null || header.isBlank()) {
            return OptionalLong.empty();
        }
        String value = header.trim();

        if (value.matches("[0-9]+")) {
            try {
                long seconds = Long.parseLong(value);
                return OptionalLong.of(TimeUnit.SECONDS.toNanos(seconds));
            } catch (NumberFormatException tooLarge) {
                // Số giây rất lớn: không được coi là phải retry ngay.
                return OptionalLong.of(Long.MAX_VALUE);
            }
        }

        try {
            Instant retryAt = ZonedDateTime.parse(
                value, DateTimeFormatter.RFC_1123_DATE_TIME
            ).toInstant();

            Duration delta = Duration.between(Instant.now(), retryAt);
            try {
                return OptionalLong.of(Math.max(0L, delta.toNanos()));
            } catch (ArithmeticException overflow) {
                return OptionalLong.of(
                    delta.isNegative() ? 0L : Long.MAX_VALUE
                );
            }
        } catch (DateTimeParseException invalidDate) {
            return OptionalLong.empty();
        }
    }

    static void waitBeforeRetry(
            long started,
            long budgetNanos,
            int failedAttempt,
            OptionalLong retryAfter)
            throws InterruptedException, HttpTimeoutException {

        long nanos = fullJitterNanos(failedAttempt);
        if (retryAfter.isPresent()) {
            nanos = Math.max(nanos, retryAfter.getAsLong());
        }

        long remaining = remainingNanos(started, budgetNanos);
        if (remaining <= 0L || nanos >= remaining) {
            throw new HttpTimeoutException(
                "Insufficient overall budget for another attempt"
            );
        }

        TimeUnit.NANOSECONDS.sleep(nanos);
    }

    static HttpResponse<String> getWithRetry(
            HttpClient client,
            URI uri,
            Duration budget)
            throws IOException, InterruptedException {

        if (budget.isNegative() || budget.isZero()) {
            throw new IllegalArgumentException("Budget must be positive");
        }

        long started = System.nanoTime();
        long budgetNanos = budget.toNanos();

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            long remaining = remainingNanos(started, budgetNanos);
            if (remaining <= 0L) {
                throw new HttpTimeoutException("Overall GET deadline exceeded");
            }

            HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofNanos(remaining))
                .header("Accept", "application/json")
                .GET()
                .build();

            HttpResponse<String> response;
            try {
                response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8
                    )
                );
            } catch (HttpTimeoutException | ConnectException transientError) {
                if (attempt == MAX_ATTEMPTS) {
                    throw transientError;
                }
                waitBeforeRetry(
                    started, budgetNanos, attempt, OptionalLong.empty()
                );
                continue;
            }

            if (!retryableStatus(response.statusCode())
                    || attempt == MAX_ATTEMPTS) {
                return response;
            }

            OptionalLong serverDelay = retryAfterNanos(
                response.headers()
                    .firstValue("Retry-After")
                    .orElse(null)
            );

            waitBeforeRetry(started, budgetNanos, attempt, serverDelay);
        }

        throw new AssertionError("Unreachable: retry loop exhausted");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                "Usage: java ReliableGetDemo https://your-api.example/v1/items"
            );
            return;
        }

        URI target = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(target.getScheme())
                || target.getHost() == null) {
            throw new IllegalArgumentException(
                "This demo requires an HTTPS URI with a host"
            );
        }

        try (HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build()) {

            HttpResponse<String> response = getWithRetry(
                client, target, Duration.ofSeconds(5)
            );

            System.out.println("Final HTTP status = " + response.statusCode());
            // Tránh ghi log response body thật nếu nó có dữ liệu nhạy cảm.
            System.out.println("Response characters = "
                    + response.body().length());
        }
    }
}
```

**Lưu ý khi sử dụng:**

- Ví dụ sử dụng `BodyHandlers.ofString`: toàn bộ response body được đọc thành String. Với dữ liệu lớn/không đáng tin cậy, cần **giới hạn kích thước** và chọn `BodyHandler`/subscription có chính sách phù hợp để tránh sử dụng quá nhiều bộ nhớ.
- `connectTimeout` là thời gian kết nối; `request.timeout` áp dụng cho từng lần `send`. Cả hai không tự biến thành **một** SLA tổng; code mới tính deadline xuyên các lần thử.
- `fullJitterNanos` có thể cho độ trễ bằng 0, là đặc tính của *full jitter*. Nếu yêu cầu có sàn tối thiểu, có thể dùng biến thể khác và đánh giá cùng chính sách `Retry-After`.
- Nếu server yêu cầu đợi lâu hơn ngân sách, method ném `HttpTimeoutException` thay vì retry **sớm hơn** chỉ dẫn.
- Với `HttpClient` mặc định, `close()` chờ các request đang được client quản lý hoàn tất; hãy dùng client **tái sử dụng** trong vòng đời component/application thay vì tạo/đóng client trong từng attempt.
- Chương trình chỉ retry GET theo hợp đồng mô tả; **không copy nguyên vòng retry này cho POST có side effect**.
- Ví dụ cố ý không bắt `SSLHandshakeException`, `UnknownHostException` và mọi `IOException` khác để tránh che lỗi cấu hình. Mở rộng taxonomy khi đã hiểu API/infra của dịch vụ cụ thể.

### 7.1. Kiểm tra hành vi trên response mẫu

| Lần 1 | Lần tiếp theo | Kết quả |
| --- | --- | --- |
| 200 | Không retry | Trả response 200 |
| 404 | Không retry | Trả response 404 cho tầng nghiệp vụ |
| 429 + `Retry-After: 2` | Chờ ít nhất 2 s nếu deadline cho phép | Thử lại GET |
| 503 + `Retry-After` HTTP-date trong tương lai | Chờ theo chỉ dẫn và jitter | Thử lại nếu còn ngân sách |
| 502, lần 2 là 200 | Backoff, rồi GET lần 2 | Trả 200 |
| `HttpTimeoutException`, chưa hết attempts | Backoff ngẫu nhiên | GET lần tiếp nếu budget đủ |
| `SSLHandshakeException` | Không thử lại | Propagate exception |
| Caller bị interrupt trong `send`/`sleep` | Không retry | Propagate `InterruptedException` |
| Retry hết 4 lần và status 503 | Không có attempt 5 | Trả response 503 cuối cho caller |
| Retry cần chờ vượt deadline | Không gửi attempt mới | Ném `HttpTimeoutException` |

## 8. Gửi POST: idempotency key không phải “phép màu” của HttpClient

### 8.1. Vì sao POST rất dễ bị nhân đôi?

Ví dụ một `POST /orders` gửi payload:

```json
{
  "customerId": "C-42",
  "itemId": "BOOK-27",
  "quantity": 1
}
```

Nếu client gửi lại sau timeout trong khi server đã tạo đơn, có thể sinh hai mã đơn khác nhau. Không có cách nào từ **chỉ một timeout ở client** để chắc chắn request trước chưa commit.

**Idempotency key** là một định danh được tạo **một lần cho một thao tác logic**, và được dùng lại trong các lần retry của đúng thao tác đó. Server phải **thực thi chính sách nhận biết duplicate** để bảo đảm việc gửi lại không tạo thêm hiệu quả nghiệp vụ.

### 8.2. Ví dụ xây POST có key ổn định

Giả sử một API đã **ghi rõ** nó hỗ trợ header `Idempotency-Key` với giá trị UUID dạng chuỗi không dấu ngoặc kép:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;

String payload = """
    {"customerId":"C-42","itemId":"BOOK-27","quantity":1}
    """;

// Tạo key một lần khi bắt đầu thao tác nghiệp vụ, không tạo lại mỗi attempt.
String operationKey = UUID.randomUUID().toString();

HttpRequest post = HttpRequest.newBuilder(
        URI.create("https://orders.example.com/v1/orders"))
    .timeout(Duration.ofSeconds(3))
    .header("Content-Type", "application/json")
    .header("Idempotency-Key", operationKey) // Theo contract server ví dụ
    .POST(HttpRequest.BodyPublishers.ofString(
        payload, StandardCharsets.UTF_8))
    .build();
```

Mảnh code trên chỉ minh họa cách xây request; không tự gửi một đơn hàng. **Chỉ được áp dụng nếu server đã định nghĩa hợp đồng idempotency tương ứng**. Nếu server chỉ ghi nhận header nhưng **không deduplicate giao dịch**, key không giải quyết được nguy cơ nhân đôi.

> **Trạng thái tiêu chuẩn hiện tại (tháng 11/2026):** header `Idempotency-Key` đang được chuẩn hóa trong **Internet-Draft** `draft-ietf-httpapi-idempotency-key-header-09` (21/11/2026), **chưa phải RFC chính thức**. Bản draft sử dụng cú pháp *Structured Field String*, có thể cần giá trị được bao trong dấu ngoặc kép, ví dụ `Idempotency-Key: "uuid..."`. Nhiều API triển khai header theo hợp đồng riêng và dùng raw UUID. **Theo contract của dịch vụ thực tế**, không tự giả định wire format hoặc mức bảo đảm từ tên header.

### 8.3. Quy tắc sử dụng key

- **Tạo một lần cho thao tác nghiệp vụ.** Retry dùng **chính key cũ**, không tạo key mới.
- **Không dùng lại key cho payload khác.** Server có thể trả lỗi khi key trùng nhưng fingerprint payload khác.
- **Scope rõ ràng** theo tenant/account, endpoint và loại thao tác; đừng cho hai khách hàng có thể vô tình chia key.
- **Lưu đủ lâu** để bao phủ cửa sổ retry/recovery; hết TTL của server có thể khiến một retry quá muộn bị xem là thao tác mới.
- **Không nhầm với request ID/trace ID.** Trace ID phục vụ quan sát; idempotency key phục vụ ràng buộc thực thi nghiệp vụ.
- **Không lộ dữ liệu nhạy cảm** trong key; dùng opaque random value/UUID theo contract, không nhúng thông tin cá nhân.
- **Đối chiếu outcome** với trạng thái server khi đã mất response, đặc biệt ở payment/order APIs.

Ngay cả khi dùng UUID ngẫu nhiên tốt, idempotency còn phụ thuộc server: xử lý đồng thời, transaction và persistence. Client **không thể đơn phương bảo đảm exactly-once**.

## 9. Idempotency ở phía server: cần lưu gì?

Một cơ chế server-side tối thiểu nên gồm:

```text
(scope, idempotencyKey) --> state + payloadFingerprint + outcome
                           │
                           ├─ IN_PROGRESS
                           ├─ COMPLETED(result/status)
                           └─ FAILED/EXPIRED theo chính sách
```

Quy trình khuyến nghị:

1. **Nhận request:** kiểm tra key, xác định tenant/endpoint/operation; tính fingerprint nội dung nếu contract yêu cầu.
2. **Đăng ký key nguyên tử:** bảo đảm hai request đồng thời cùng key không cùng bắt đầu side effect. Dùng transaction/unique constraint hoặc cơ chế phân tán đủ mạnh.
3. **Key mới:** xử lý nghiệp vụ; ràng buộc việc ghi outcome với transaction hoặc xây recovery protocol phù hợp.
4. **Duplicate đã hoàn tất:** trả lại kết quả nhất quán với outcome gốc (status/body theo hợp đồng API).
5. **Duplicate còn chạy:** chờ, trả conflict/retry-later hoặc phản hồi theo API; không âm thầm xử lý song song như thao tác mới.
6. **Cùng key nhưng payload khác:** từ chối, không tái sử dụng kết quả gốc cho dữ liệu không tương đương.
7. **Expired key:** công bố chính sách TTL và cách truy vấn giao dịch để client tránh gửi lại sau khi key không còn hiệu lực.

Ví dụ trạng thái:

| Đầu vào | Trạng thái đã lưu | Xử lý |
| --- | --- | --- |
| Key K1 và payload P1 | Chưa có | Reserve K1, chạy P1 một lần theo transaction policy |
| Key K1 và payload P1 | COMPLETED | Trả outcome gốc |
| Key K1 và payload P1 | IN_PROGRESS | Không thực thi hai lần; trả trạng thái chờ/conflict theo contract |
| Key K1 và payload P2 | Bất kỳ trạng thái K1 còn hiệu lực | Báo lỗi key reuse/payload mismatch |
| Key K2 và payload P1 | Key mới | Là một thao tác logic khác, **không** mặc định deduplicate |

**Quan trọng:** chỉ lưu key bằng một cache không có tính nguyên tử, không bền, hoặc lưu trước side effect rồi crash có thể để lại trạng thái kẹt. Tùy nghiệp vụ, cần thiết kế transaction boundary, trạng thái hồi phục và kiểm tra kết quả theo business ID.

Idempotency không bảo đảm bản thân downstream payment gateway, email sender hay message broker đều có cùng semantics. Nếu server gọi các hệ thống con, cần lan truyền transaction ID/idempotency key hoặc dùng cơ chế outbox/deduplication ở từng ranh giới cần thiết.

## 10. Request body có thể phát lại hay không?

Với retry của `POST`/`PUT`, điều kiện **semantics idempotent** chưa đủ; dữ liệu phải **được phát lại đúng**.

### 10.1. BodyPublisher có thể tạo nhiều lần

Một số factory Java SE 27:

```java
HttpRequest.BodyPublisher smallJson =
    HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8);

HttpRequest.BodyPublisher inMemory =
    HttpRequest.BodyPublishers.ofByteArray(payloadBytes);
```

Đây là mảnh code với `json` và `payloadBytes` đã được định nghĩa trong method gọi. Nếu body nhỏ và đã nằm trong bộ nhớ, dùng một nguồn dữ liệu bất biến phù hợp giúp tạo request mới cho từng attempt với **cùng bytes**. Nếu dùng `byte[]`, đừng sửa nội dung của mảng sau khi khởi tạo publisher.

### 10.2. Stream body có thể là one-shot

`HttpRequest.BodyPublishers.ofInputStream(Supplier<InputStream>)` nhận **supplier** để lấy stream mới khi request cần được thực hiện lại:

```java
HttpRequest.BodyPublisher fileBody =
    HttpRequest.BodyPublishers.ofInputStream(
        () -> {
            try {
                return java.nio.file.Files.newInputStream(path);
            } catch (java.io.IOException ex) {
                throw new java.io.UncheckedIOException(ex);
            }
        }
    );
```

Mảnh code giả định `path` đã được định nghĩa. Supplier cần cung cấp **InputStream mới có nội dung tương đương** cho mỗi lần yêu cầu. Trả lại một stream đã đọc hết hoặc trả `null` ở lần tiếp theo làm yêu cầu lặp có thể thất bại.

Đừng dùng một publisher dựa trên stream mạng một lần hoặc nguồn đã bị consume mà giả định nó phát lại y hệt. Với multipart upload hoặc file được sửa trong lúc retry, cần snapshot/versioning và chính sách đảm bảo body không đổi.

### 10.3. Đóng response body đúng cách

`BodyHandlers.ofString` đưa toàn bộ body vào bộ nhớ (phù hợp ví dụ nhỏ), còn `BodyHandlers.ofInputStream` trả stream đọc body, và caller phải đọc hết/đóng khi không dùng nữa để giải phóng tài nguyên HTTP:

```java
HttpResponse<java.io.InputStream> response = client.send(
    request, HttpResponse.BodyHandlers.ofInputStream()
);

try (java.io.InputStream body = response.body()) {
    // Đọc và xử lý hoặc bỏ body theo chính sách.
}
```

**Không** bỏ qua body dạng streaming của một phản hồi lỗi mà không đọc/đóng/cancel subscription; điều đó có thể giữ connection và ảnh hưởng đến việc đóng `HttpClient`. Nếu nội dung trả về rất lớn, đặt giới hạn kích thước và không dùng `ofString` vô điều kiện.

## 11. Async retry, virtual threads và cancellation

### 11.1. send và sendAsync

`HttpClient` hỗ trợ:

- `send(request, bodyHandler)`: caller **chờ** kết quả hoặc exception; khi thread bị interrupt, implementation mặc định cố gắng cancel exchange nhưng không bảo đảm server chưa xử lý.
- `sendAsync(request, bodyHandler)`: trả `CompletableFuture<HttpResponse<T>>` để phối hợp bất đồng bộ.
- Virtual threads phù hợp khi có nhiều task dùng API blocking `send` và chờ I/O. Chúng **không** biến dịch vụ ngoài thành vô hạn capacity.

Khi chọn async, tránh:

```java
client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
    .orTimeout(1, java.util.concurrent.TimeUnit.SECONDS);
```

rồi kết luận **“I/O gốc chắc đã bị hủy”**. `CompletableFuture.orTimeout` chỉ đặt trạng thái exceptional completion cho future khi hết hạn; ranh giới thực tế của HTTP exchange/cancellation cần kiểm tra API và thiết kế vòng đời riêng.

### 11.2. Không block hàng loạt thread chỉ để sleep backoff

Ở hệ thống nhiều request, gọi `Thread.sleep` để backoff chiếm thời gian của **thread hiện tại**; với virtual threads, thao tác chờ thường ít tốn carrier hơn platform threads, nhưng vẫn tạo nhiều task đang tồn tại và chiếm quota/bộ nhớ.

Với mô hình event-driven/async, có thể dùng `ScheduledExecutorService` để lập lịch retry mà không giữ một platform thread đang sleep cho mỗi request. Dù triển khai nào, vẫn phải bảo vệ:

- Tổng số attempts/deadline.
- Cancellation của task được lập lịch khi request bị hủy.
- Truyền context/trace ID đúng scope, không để task chạy sau khi request đã đóng resource.
- Không retry non-idempotent operation khi chưa có hợp đồng.
- Giới hạn số retries đang chờ và connection pool tới downstream.

### 11.3. Vòng đời HttpClient

`HttpClient` là đối tượng immutable sau khi build và có thể dùng để gửi nhiều request. Client thường quản lý connection pooling; tạo **một client mới cho mỗi attempt** có thể làm mất lợi ích tái sử dụng kết nối và tăng tài nguyên.

Từ Java 21, `HttpClient` có API đóng lifecycle như `close()`/`shutdown()`. `close()` là orderly shutdown và có thể **đợi request đang hoạt động hoàn tất**, nhất là nếu body streaming chưa đọc/đóng. Hãy để component/application sở hữu client đóng nó đúng thời điểm; **không** đóng shared client của các request khác chỉ vì một request bị timeout.

## 12. Bảo vệ hệ thống khỏi retry storm

Một chính sách retry production không nên chỉ là vòng `for`:

### 12.1. Giới hạn cả số lần và tổng thời gian

Nếu mỗi tầng có 3 attempts và request đi qua 4 tầng, một request người dùng có thể khiến downstream nhận tối đa `3^4 = 81` lượt trong tình huống triển khai đều retry lồng nhau. Số lần thử **bao gồm lần đầu**; “3 retries” có nghĩa tối đa **4 attempts** nếu được hiểu theo cách đó.

Ghi rõ:

- `maxAttempts` trên từng operation.
- `totalDeadline` cho cả workflow.
- `perAttemptTimeout` nhỏ hơn hoặc bằng thời gian còn lại.
- `maxBackoff` và policy `Retry-After`.
- `retryBudget` ở mức hệ thống, không chỉ từng request.

### 12.2. Circuit breaker, bulkhead, rate limit

| Cơ chế | Bảo vệ điều gì |
| --- | --- |
| **Retry budget** | Ngăn tổng retries chiếm quá nhiều lưu lượng |
| **Backoff + jitter** | Trải đều những lượt thử lại theo thời gian |
| **Circuit breaker** | Ngừng/giảm thử khi downstream lỗi kéo dài, chuyển sang half-open thử hồi phục |
| **Bulkhead/Semaphore** | Giới hạn số call đồng thời tới một upstream |
| **Rate limiter** | Tôn trọng quota trong một khoảng thời gian |
| **Queue backpressure** | Tránh dồn tác vụ vô hạn khi downstream chậm |
| **Cache/stale response/fallback** | Giảm nhu cầu gọi khi nghiệp vụ cho phép dữ liệu dự phòng |

Không phải mọi ứng dụng đều cần cài tất cả cơ chế. Quan trọng là đặt **giới hạn rõ ràng** ở những chỗ retry có thể phóng đại tải.

### 12.3. Retry và observability

Nên ghi metric hoặc event có kiểm soát:

- `service` / `operation` / `HTTP method`, status group và loại exception.
- Attempts đã thực hiện, số lần retry, lý do retry.
- Backoff được chọn, `Retry-After` nhận được, tổng thời gian request.
- Kết quả: success-first-try, success-after-retry, non-retryable failure, max-attempts, deadline-exceeded, cancelled.
- Số requests đang active, số task pending, giới hạn kết nối và retry budget.
- Với tác vụ có side effect: kết quả lookup theo **business operation ID** khi outcome chưa rõ.

**Không ghi log token/Authorization header, request body chứa dữ liệu cá nhân, secret, hoặc idempotency key nếu key có thể được dùng để suy luận giao dịch**. Dùng mã trace an toàn và redaction có chủ đích.

## 13. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Một đơn hàng bị tạo hai lần sau timeout | Retry `POST` khi chưa có idempotency | Key gắn với operation + dedup server hoặc truy vấn outcome |
| Có header `Idempotency-Key` nhưng vẫn trùng giao dịch | Server không enforce/TTL đã hết/race | Thiết kế reservation nguyên tử và transaction/recovery |
| Client tự sinh key mới mỗi attempt | Duplicate được xem là request mới | Sinh key một lần, tái sử dụng cho cùng payload |
| GET cứ lặp mãi với 404 | Retry mọi HTTP status | Chỉ retry status đã được phân loại là transient |
| `SSLHandshakeException` bị retry liên tục | Bắt mọi `IOException` | Dừng cho lỗi TLS/configuration, chỉ retry lỗi thoáng qua |
| GET vẫn retry khi caller bị interrupt | Nuốt `InterruptedException` | Propagate và ngừng retry, cleanup |
| 429 nhưng retry ngay | Không đọc `Retry-After`/quota | Đợi theo chỉ dẫn và giới hạn rate |
| `Retry-After` lớn bị parse tràn rồi bỏ qua | Không xử lý số quá lớn | Giữ trạng thái “chờ rất lâu”; ngừng khi vượt budget |
| 5-second timeout nhưng tổng retries mất 20 giây | Reset timeout mỗi attempt | Deadline chung từ `System.nanoTime()` |
| 503 đến hàng nghìn client, tất cả retry cùng lúc | Backoff cố định không jitter | Bounded exponential + jitter |
| Nhiều tầng đều tự retry | Retry amplification | Xác định một tầng sở hữu retry và ngân sách |
| Server đã commit nhưng client nhận `IOException` | Mất response sau xử lý | Xem outcome là **không chắc chắn**, cần idempotency/status query |
| Upload retry gửi body rỗng | Publisher dựa trên InputStream dùng một lần | Dùng nguồn replayable/new supplier, giữ payload ổn định |
| Dùng `BodyHandlers.ofString` cho response cực lớn | Đọc toàn bộ body vào RAM | Giới hạn kích thước, dùng streaming handler có cleanup |
| Không đóng streaming error response | HTTP connection/tài nguyên chưa giải phóng | Đọc hết/đóng/cancel response body |
| Retry 504 cho thao tác trừ tiền không key | Upstream có thể đã commit | Chỉ retry khi semantics nghiệp vụ bảo vệ |
| Coi `close()` của HttpClient là cancel request tức thì | Close orderly có thể đợi I/O | Quản lý vòng đời app, per-request timeout/cancel |
| Không có metric sau retry | Chỉ log kết quả cuối | Ghi attempts/backoff/status/latency với redaction |

## 14. Checklist thiết kế khi gọi dịch vụ ngoài

1. **Xác định operation:** GET/PUT/DELETE hay POST/PATCH, tác động phụ gì? Có thực sự idempotent không?
2. **Phân loại lỗi:** status nào cho retry, exception nào transient, lỗi nào phải trả ngay?
3. **Bảo đảm body phát lại:** payload/headers không thay đổi theo attempt; stream một lần cần supplier/replay strategy.
4. **Đặt số lần thử tối đa:** tính **bao gồm** lần đầu.
5. **Đặt tổng deadline:** đo bằng monotonic clock; per-attempt timeout dùng phần thời gian còn lại.
6. **Dùng exponential backoff có cap và jitter:** tránh đồng bộ các client.
7. **Tôn trọng `Retry-After`:** số giây hoặc HTTP-date; đừng retry sớm nếu server yêu cầu chờ.
8. **Không nuốt interruption:** dừng retry khi request bị hủy và xử lý tài nguyên.
9. **Nếu có side effect:** phải có server-side idempotency hoặc một cơ chế xác định kết quả trước khi retry.
10. **Giữ key theo operation:** cùng key/cùng payload trong cả chuỗi retry; kiểm tra TTL/scope/fingerprint.
11. **Giới hạn tài nguyên:** rate limit, bulkhead, connection pool, retry budget và circuit breaker khi cần.
12. **Không biến timeout thành “chắc chắn thất bại”:** server có thể đã commit; xử lý outcome chưa rõ.
13. **Đóng body/client đúng scope:** streaming body phải được xử lý đến cuối hoặc đóng; shared client do application quản lý.
14. **Đo lường và kiểm thử:** test 429, 503, 502, 504, connect timeout, TLS failure, caller interrupt, Retry-After lớn, body replay, concurrent duplicate POST.
15. **Đọc contract provider:** đừng coi mọi Idempotency-Key header là tiêu chuẩn hoàn chỉnh hoặc có tác dụng tự động.
16. **Giữ API hiện hành:** Java 27 `java.net.http` và RFC HTTP hiện hành; không dựa trên code cũ giả định `HttpClient` không thể đóng hoặc tự retry an toàn mọi request.

## 15. Tài liệu tham khảo chính thức

- [`HttpClient` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html) — `send`/`sendAsync`, interruption, connection pool và lifecycle.
- [`HttpRequest.Builder` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html) — `timeout(Duration)`, HTTP method, headers và request builder.
- [`HttpRequest.BodyPublishers` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html) — body từ String, byte array hoặc InputStream supplier.
- [`HttpResponse.BodyHandlers` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html) — xử lý body thành String, InputStream hoặc loại khác; vòng đời streaming body.
- [`HttpTimeoutException` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpTimeoutException.html) — timeout request.
- [`ThreadLocalRandom` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html) — jitter không nhạy cảm bảo mật.
- [RFC 9110 — HTTP Semantics, §9.2.2 Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2) — semantics của safe/idempotent methods và điều kiện retry.
- [RFC 9110 — HTTP Semantics, §10.2.3 Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3) — header thời điểm hoặc số giây chờ.
- [RFC 6585 — §4, 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html#section-4) — rate limit và Retry-After.
- [IETF HTTPAPI — Idempotency-Key Header, Internet-Draft -09 (21/11/2026)](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header-09) — đề xuất đang được chuẩn hóa; **chưa phải RFC**, không thay cho hợp đồng nhà cung cấp.
